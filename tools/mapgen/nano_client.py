"""tools/mapgen/nano_client.py — async wrapper around Google Gemini 2.5 Flash
Image ("Nano Banana") for automated map painting, + an offline MockNanoClient.

Modeled on ai/claude_provider.py: env-key gated, aiohttp, graceful return-None
on any failure, a factory that hands back the Mock when no key is present so
the whole pipeline runs offline. The live HTTP body is written but only
exercised when GOOGLE_API_KEY / GEMINI_API_KEY is set.

Returns a GenResult so the toe-the-line loop can DISTINGUISH a content-filter
REFUSAL (back off to a safer rung) from a transient error (retry/skip) from a
clean image (keep). That distinction is the whole point of the bold→back-off
ladder.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import aiohttp  # noqa: F401
    _AIOHTTP_AVAILABLE = True
except Exception:
    _AIOHTTP_AVAILABLE = False


# A real 1x1 transparent PNG — what MockNanoClient returns so downstream code
# (PIL open, byte length, file write) all work without a live API.
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000100ffff0306000020"
    "0001e221bc330000000049454e44ae426082"
)

# Gemini status we read as a content-filter refusal (the toe-the-line signal).
_REFUSAL_MARKERS = ("SAFETY", "BLOCKED", "PROHIBITED_CONTENT", "RECITATION")


@dataclass
class GenResult:
    """Outcome of one generation attempt."""
    image: Optional[bytes]      # PNG bytes on success, else None
    refused: bool = False       # True iff a content-filter refusal (back off!)
    error: str = ""             # transient/other error detail (retry/skip)

    @property
    def ok(self) -> bool:
        return self.image is not None


class MockNanoClient:
    """Offline stand-in: returns a placeholder PNG, never refuses, no network.
    Lets the entire batch→screen→rank→select pipeline run with no API key."""

    def __init__(self, *_a, **_k):
        pass

    async def is_available(self) -> bool:
        return True

    async def generate_image(self, seed_path: Path,
                             style_ref_path: Optional[Path],
                             brief_text: str) -> GenResult:
        return GenResult(image=_PLACEHOLDER_PNG)


class NanoClient:
    """Live Gemini image client. Only used when an API key is present."""

    ENDPOINT = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-image:generateContent"
    )

    def __init__(self, api_key: str, timeout: float = 60.0,
                 project_id: Optional[str] = None):
        self.api_key = api_key
        self.timeout = timeout
        self.project_id = project_id

    async def is_available(self) -> bool:
        # No network ping — key + aiohttp present is enough; a bad key surfaces
        # on the first real call (same as ClaudeProvider).
        return _AIOHTTP_AVAILABLE and bool(self.api_key)

    async def generate_image(self, seed_path: Path,
                             style_ref_path: Optional[Path],
                             brief_text: str) -> GenResult:
        """POST seed (+ optional style ref) + prompt to Gemini; return the
        painted PNG. Distinguishes a content-filter refusal from a transient
        error so the caller can step down the term ladder vs. retry.

        NOTE: the exact multipart shape (does one call accept BOTH seed and
        style-ref, or must we chain two img2img passes?) is an open question
        for go-live — see docs/design/map_automation_framework_v1.md. The
        single-call form is written here; revisit before first real use.
        """
        if not _AIOHTTP_AVAILABLE:
            return GenResult(image=None, error="aiohttp unavailable")
        import base64
        import aiohttp

        def _b64(p: Optional[Path]) -> Optional[str]:
            if not p or not Path(p).exists():
                return None
            return base64.b64encode(Path(p).read_bytes()).decode("ascii")

        parts: list[dict] = [{"text": brief_text}]
        seed_b64 = _b64(seed_path)
        if seed_b64:
            parts.append({"inline_data": {"mime_type": "image/png", "data": seed_b64}})
        style_b64 = _b64(style_ref_path)
        if style_b64:
            parts.append({"inline_data": {"mime_type": "image/png", "data": style_b64}})

        payload = {"contents": [{"parts": parts}]}
        headers = {"x-goog-api-key": self.api_key, "content-type": "application/json"}

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.ENDPOINT, json=payload,
                                        headers=headers) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        upper = text.upper()
                        if any(m in upper for m in _REFUSAL_MARKERS):
                            return GenResult(image=None, refused=True,
                                             error="content filter")
                        return GenResult(image=None,
                                         error=f"HTTP {resp.status}: {text[:200]}")
                    import json as _json
                    data = _json.loads(text)
                    return self._extract_image(data)
        except Exception as e:  # network/timeout/parse — transient, caller retries
            return GenResult(image=None, error=f"{type(e).__name__}: {e}")

    @staticmethod
    def _extract_image(data: dict) -> GenResult:
        import base64
        # Refusal can also arrive as a 200 with a blockReason / finishReason.
        fb = data.get("promptFeedback", {})
        if str(fb.get("blockReason", "")).upper() in _REFUSAL_MARKERS:
            return GenResult(image=None, refused=True, error="blockReason")
        for cand in data.get("candidates", []):
            if str(cand.get("finishReason", "")).upper() in _REFUSAL_MARKERS:
                return GenResult(image=None, refused=True, error="finishReason")
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if inline and inline.get("data"):
                    try:
                        return GenResult(image=base64.b64decode(inline["data"]))
                    except Exception as e:
                        return GenResult(image=None, error=f"decode: {e}")
        return GenResult(image=None, error="no image in response")


async def create_nano_client(monthly_budget_cents: float = 500.0):
    """Factory: real NanoClient when a Google key is in env, else MockNanoClient
    (graceful offline). `monthly_budget_cents` reserved for future cost gating
    (per-image Nano cost is ~0.08¢; a 6-candidate city paint is ~0.5¢)."""
    key = (os.environ.get("GOOGLE_API_KEY", "").strip()
           or os.environ.get("GEMINI_API_KEY", "").strip())
    if key and _AIOHTTP_AVAILABLE:
        return NanoClient(api_key=key)
    return MockNanoClient()
