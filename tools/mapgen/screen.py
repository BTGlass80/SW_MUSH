"""tools/mapgen/screen.py — AI screening QA for generated map paintings.

A cheap LLM (Haiku vision) judges each generated painting against the SAME
constraints the brief demanded, and returns a structured verdict. This is the
bulk pass/fail filter so a human only adjudicates finalists — AND it doubles as
the toe-the-line line-detector: an off-theme verdict tells the batch loop a
bold term-rung crossed the line and to step down.

Offline (no ANTHROPIC_API_KEY), it routes through MockScreener (deterministic,
no API) so the whole pipeline runs in tests. Live, it calls Claude vision via
the existing ai.claude_provider seam.

Cost tiering (Brian's directive): Haiku does the bulk pass/fail; a borderline
score (in ESCALATE_BAND) flags 'ESCALATE' so the caller can route it to a
costlier model or a human queue. This module SCREENS and FLAGS; it does not
route (caller-side decision).
"""
from __future__ import annotations

import json
import re
from typing import Optional, TypedDict


# Borderline scores escalate to human/Opus; clear pass/fail don't.
ESCALATE_BAND = (45.0, 75.0)
PASS_THRESHOLD = 70.0


class ScreeningVerdict(TypedDict):
    passed: bool
    score: float            # 0-100 paint-quality / on-theme score
    flags: list             # e.g. ["off-theme: ocean ship in desert", "ESCALATE"]
    has_text: bool          # the painting must be text-free
    on_theme: bool          # terrain matches the brief's geography
    reasoning: str


def parse_area_brief(area_brief: str) -> str:
    """Pull the {GEOGRAPHY} description out of a paint brief so the screener
    knows what terrain to expect. Falls back to the whole brief."""
    m = re.search(r"(?:GEOGRAPHY|Setting|Geography)[:\s]+(.+?)(?:\n\n|\Z)",
                  area_brief, re.IGNORECASE | re.DOTALL)
    return (m.group(1).strip() if m else area_brief.strip())[:1500]


# The rubric the live vision call uses. It mirrors the MASTER_PROMPT constraints
# (no text, no franchise iconography, no modern-Earth elements) plus geography
# fidelity. Kept here so the bar is reviewable in one place.
_RUBRIC = """\
You are QA for a hand-painted top-down fantasy-RPG map plate. Judge the image
against these REQUIREMENTS and return ONLY a JSON object.

REQUIREMENTS:
1. NO TEXT of any kind — no labels, letters, numbers, signs, legend, compass.
2. On-theme terrain: it must depict {geography}. Flag anything that contradicts
   that setting (e.g. an OCEAN SHIP or water vessel in a DESERT region, modern
   Earth cars, contemporary signage, snow in a desert).
3. No franchise iconography, no uniformed troops, no modern-Earth elements.
4. Painterly tabletop-atlas style, cohesive palette, fills the frame.

Return JSON exactly:
{{"passed": <bool>, "score": <0-100>, "has_text": <bool>, "on_theme": <bool>,
  "flags": [<short strings naming each problem>], "reasoning": "<one sentence>"}}
score: 90-100 excellent on-theme text-free; 70-89 good; 45-69 borderline;
below 45 clearly wrong (off-theme or has text). passed = score>=70 AND not
has_text AND on_theme."""


class MockScreener:
    """Deterministic offline screener. Passes with score 85 unless the caller
    pre-injects flags (so tests can simulate an off-theme painting)."""

    def __init__(self, inject_flags: Optional[list] = None, score: float = 85.0):
        self._flags = list(inject_flags or [])
        self._score = score

    async def screen(self, image_bytes: bytes, geography: str) -> ScreeningVerdict:
        off_theme = bool(self._flags)
        score = 30.0 if off_theme else self._score
        return _finalize({
            "passed": (not off_theme) and score >= PASS_THRESHOLD,
            "score": score,
            "has_text": False,
            "on_theme": not off_theme,
            "flags": list(self._flags),
            "reasoning": "mock screen",
        })


async def screen_image(image_bytes: bytes, area_brief: str,
                       expected_geography: str = "",
                       model: str = "haiku",
                       provider=None) -> ScreeningVerdict:
    """Screen one painting. Uses the injected `provider` (a ClaudeProvider) for
    live Claude-vision; falls back to MockScreener when none/no key."""
    geography = expected_geography or parse_area_brief(area_brief)
    if provider is None:
        return await MockScreener().screen(image_bytes, geography)
    return await _screen_with_claude(image_bytes, geography, model, provider)


async def _screen_with_claude(image_bytes: bytes, geography: str,
                              model: str, provider) -> ScreeningVerdict:
    """Live path: send the image as a vision content block + the rubric, parse
    the JSON verdict. Fail-open to a neutral ESCALATE verdict on any error so a
    screening hiccup never silently drops a candidate."""
    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = _RUBRIC.format(geography=geography)
    # ClaudeProvider.generate(system_prompt, messages, ...) — vision goes in the
    # user message's content blocks (image + text). The rubric is the system.
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": "Screen this map plate per the instructions."},
        ],
    }]
    try:
        text = await provider.generate(
            system_prompt=prompt, messages=messages,
            max_tokens=400, json_mode=True, model=_model_id(model))
        data = _extract_json(text)
        if data is None:
            return _finalize(_neutral("could not parse verdict JSON"))
        return _finalize(data)
    except Exception as e:
        return _finalize(_neutral(f"screen error: {type(e).__name__}"))


def _model_id(tier: str) -> str:
    return {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-8",
    }.get(tier, "claude-haiku-4-5-20251001")


def _extract_json(text: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _neutral(reason: str) -> dict:
    # An error verdict escalates rather than passing or hard-failing.
    return {"passed": False, "score": 60.0, "has_text": False,
            "on_theme": True, "flags": [], "reasoning": reason}


def _finalize(d: dict) -> ScreeningVerdict:
    """Normalize + apply the ESCALATE band rule."""
    score = float(d.get("score", 0.0))
    flags = list(d.get("flags", []))
    if ESCALATE_BAND[0] <= score < ESCALATE_BAND[1] and "ESCALATE" not in flags:
        flags.append("ESCALATE")
    passed = bool(d.get("passed", False)) and not d.get("has_text", False) \
        and d.get("on_theme", True) and score >= PASS_THRESHOLD
    return {
        "passed": passed,
        "score": score,
        "flags": flags,
        "has_text": bool(d.get("has_text", False)),
        "on_theme": bool(d.get("on_theme", True)),
        "reasoning": str(d.get("reasoning", ""))[:300],
    }
