# -*- coding: utf-8 -*-
"""
AI Provider abstraction layer.

Supports local LLM via Ollama (default, free) and optional cloud API.
The game logic calls AIManager.generate() and never knows which backend
is handling the request.

Fallback hierarchy:
  1. Primary provider (Ollama) available -> use it
  2. All providers unavailable -> return fallback text
"""
import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# aiohttp is required for Ollama communication. It is listed in requirements.txt.
# If missing, the Ollama provider will be permanently unavailable and the server
# will fall back to MockProvider (NPC AI disabled). Install with:
#   pip install aiohttp
try:
    import aiohttp as _aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _aiohttp = None  # type: ignore[assignment]
    _AIOHTTP_AVAILABLE = False
    log.error(
        "aiohttp is not installed -- Ollama AI provider will be disabled. "
        "Run: pip install aiohttp"
    )


# ── Claude provider (optional, requires ANTHROPIC_API_KEY) ──
from ai.claude_provider import make_claude_provider

# ── Local model selection (env-driven) ──
#
# The local Ollama model for NPC dialogue / JSON barks / scene summaries. Set the
# OLLAMA_MODEL env var to your EXACT `ollama list` tag to swap models with zero
# code change (the provider abstraction was built for exactly this one-liner).
# Default targets Qwen3.5-9B per the Fable 2026-07-03 review: every current 7-9B
# model beats the Sep-2023 Mistral 7B at the same ~5GB Q4 footprint on an RTX
# 3070. NOTE: a sub-1B model (e.g. qwen3.5:0.8b) is a QUALITY DOWNGRADE from
# Mistral 7B for in-character text — use a ~7-9B tag for the real swap.
_DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"


def _ollama_model() -> str:
    return (os.environ.get("OLLAMA_MODEL") or "").strip() or _DEFAULT_OLLAMA_MODEL


def _ollama_tier2_model() -> str:
    # Premium story NPCs can point at a bigger tag if you have the VRAM;
    # falls back to the primary model.
    return (os.environ.get("OLLAMA_TIER2_MODEL") or "").strip() or _ollama_model()


def _try_autostart_ollama() -> bool:
    """Best-effort: spawn `ollama serve` detached if the daemon isn't reachable.

    Harmless if Ollama is already running (the second `serve` just fails on the
    bound port) or not installed (we skip with a log line). Returns True if we
    launched a process, False otherwise. Never raises into the boot path.
    """
    import shutil
    import subprocess
    exe = shutil.which("ollama")
    if not exe:
        log.warning("autostart_ollama: `ollama` not found on PATH; skipping")
        return False
    try:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP so it outlives us.
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([exe, "serve"], **kwargs)
        log.info("autostart_ollama: launched `ollama serve`")
        return True
    except Exception as e:
        log.warning("autostart_ollama: failed to launch `ollama serve`: %s", e)
        return False


# ── Configuration ──

@dataclass
class AIConfig:
    """Global AI configuration."""
    enabled: bool = True
    default_provider: str = "ollama"       # "ollama", "mock"
    default_model: str = field(default_factory=_ollama_model)  # env OLLAMA_MODEL; default Qwen3.5-9B

    # Ollama settings
    ollama_host: str = "http://localhost:11434"
    ollama_timeout: float = 60.0           # seconds (first call loads the model)

    # Rate limiting
    max_requests_per_minute: int = 10      # per player
    npc_thinking_emote: bool = True        # show "NPC ponders..." while waiting

    # Model tiers (both env-driven via OLLAMA_MODEL / OLLAMA_TIER2_MODEL)
    tier1_model: str = field(default_factory=_ollama_model)         # Fast, most NPCs
    tier2_model: str = field(default_factory=_ollama_tier2_model)   # Premium story NPCs
    tier3_provider: str = ""               # Cloud provider name (empty = disabled)
    tier3_model: str = ""                  # Cloud model name


# ── Provider Base Class ──

class AIProvider(ABC):
    """Abstract base for AI providers."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: str = "",
        options: Optional[dict] = None,
        keep_alive: str = "",
    ) -> str:
        """
        Generate a response.

        Args:
            system_prompt: System/character prompt for the LLM.
            messages: Conversation history as [{"role": "user"|"assistant", "content": "..."}]
            max_tokens: Max response length.
            temperature: Creativity (0.0 = deterministic, 1.0 = creative).
            json_mode: If True, request JSON output (for tactical AI).
            model: Override the default model for this request.

        Returns:
            Generated text string, or empty string on failure.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this provider is reachable."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


# ── Ollama Provider ──

class OllamaProvider(AIProvider):
    """Local LLM via Ollama REST API."""

    def __init__(self, host: str = "http://localhost:11434",
             default_model: str = _DEFAULT_OLLAMA_MODEL,
             timeout: float = 25.0):
        self.host = host.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._available: Optional[bool] = None
        self._last_check: float = 0

    @property
    def name(self) -> str:
        return "ollama"

    async def is_available(self) -> bool:
        """Check if Ollama is running (cached for 30 seconds).

        On state transitions (False→True, None→True) we log at INFO so
        operators can see when the model came online. The "not available"
        line is logged at WARNING only when this is a *change* from a
        previously-good state — first-startup misses log at DEBUG to
        avoid alarming-looking noise during normal Ollama warmup. The
        probe timeout is 8s because Ollama can be slow to reply during
        model load on consumer GPUs.
        """
        if not _AIOHTTP_AVAILABLE:
            self._available = False
            return False

        now = time.time()
        if self._available is not None and (now - self._last_check) < 30:
            return self._available

        prev = self._available
        try:
            async with _aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.host}/api/tags",
                    timeout=_aiohttp.ClientTimeout(total=8),
                ) as resp:
                    self._available = resp.status == 200
        except Exception:
            self._available = False

        self._last_check = now
        if self._available:
            if prev is False:
                # Recovery: explicit signal that Ollama came back online.
                log.info("Ollama recovered and is now available at %s", self.host)
            else:
                log.debug("Ollama is available at %s", self.host)
        else:
            if prev is True:
                # Regression from a previously-good state — surface loudly.
                log.warning(
                    "Ollama became unavailable at %s (NPC dialogue will use fallbacks)",
                    self.host,
                )
            else:
                # First-startup miss or still-down: keep at DEBUG so a slow
                # warmup doesn't read like a fatal error in the log.
                log.debug("Ollama is not available at %s", self.host)
        return self._available

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: str = "",
        options: Optional[dict] = None,
        keep_alive: str = "",
    ) -> str:
        if not _AIOHTTP_AVAILABLE:
            return ""

        model = model or self.default_model

        # Build the Ollama API request. Per-call `options` (num_ctx, top_p,
        # top_k, presence_penalty, …) merge in UNDER the explicit temperature/
        # num_predict, which always win. This is how the idle-queue lanes cap
        # context to fit 8GB VRAM and apply Qwen's anti-repetition sampling.
        # `keep_alive` keeps the (larger) model resident between idle ticks so
        # it doesn't cold-load each time.
        opts = {k: v for k, v in (options or {}).items() if v is not None}
        opts["temperature"] = temperature
        opts["num_predict"] = max_tokens
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "stream": False,
            "options": opts,
        }
        if keep_alive:
            payload["keep_alive"] = keep_alive

        if json_mode:
            payload["format"] = "json"

        try:
            async with _aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.host}/api/chat",
                    json=payload,
                    timeout=_aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        log.error("Ollama error %d: %s", resp.status, error_text[:200])
                        return ""

                    data = await resp.json()
                    content = data.get("message", {}).get("content", "")
                    return content.strip()

        except asyncio.TimeoutError:
            log.warning(
                "Ollama request timed out (%.1fs) -- model may still be loading",
                self.timeout,
            )
            return ""
        except Exception as e:
            log.warning("Ollama request failed: %s", e)
            return ""

    async def preload(self, keep_alive: str = "30m") -> bool:
        """Load the configured model into VRAM ahead of first use.

        An empty-prompt POST to /api/generate is Ollama's documented way to
        resident-load a model without producing tokens; `keep_alive` sets how
        long it stays warm. Returns True once the daemon confirms the load.
        Best-effort: any failure returns False (the caller logs, never raises).
        """
        if not _AIOHTTP_AVAILABLE:
            return False
        payload = {"model": self.default_model, "keep_alive": keep_alive}
        try:
            async with _aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.host}/api/generate",
                    json=payload,
                    # First load of a 9B can take a while; give it real headroom.
                    timeout=_aiohttp.ClientTimeout(total=max(self.timeout, 180.0)),
                ) as resp:
                    if resp.status == 200:
                        await resp.read()
                        return True
                    log.warning(
                        "Ollama preload of %s failed: HTTP %d",
                        self.default_model, resp.status,
                    )
                    return False
        except Exception as e:
            log.warning("Ollama preload of %s failed: %s", self.default_model, e)
            return False

    async def list_models(self) -> list[str]:
        """List models available in Ollama."""
        if not _AIOHTTP_AVAILABLE:
            return []
        try:
            async with _aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.host}/api/tags",
                    timeout=_aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [m["name"] for m in data.get("models", [])]
        except Exception:
            log.debug("providers: model list fetch failed", exc_info=True)
            pass
        return []


# ── Mock Provider (for testing) ──

class MockProvider(AIProvider):
    """Returns canned responses. Used for testing and when no LLM is available."""

    def __init__(self):
        self.responses: list[str] = []  # Queue of responses to return
        self.last_system_prompt: str = ""
        self.last_messages: list[dict] = []
        self.call_count: int = 0

    @property
    def name(self) -> str:
        return "mock"

    async def is_available(self) -> bool:
        return True

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: str = "",
        options: Optional[dict] = None,
        keep_alive: str = "",
    ) -> str:
        self.last_system_prompt = system_prompt
        self.last_messages = messages
        self.last_options = options
        self.last_keep_alive = keep_alive
        self.call_count += 1

        if self.responses:
            return self.responses.pop(0)

        # Default generic response
        if json_mode:
            return '{"action": "none", "dialogue": "..."}'
        return "I have nothing to say about that."

    def queue_response(self, text: str):
        """Queue a response for the next generate() call."""
        self.responses.append(text)


# ── Rate Limiter ──

class RateLimiter:
    """Per-player rate limiting for AI requests."""

    def __init__(self, max_per_minute: int = 10):
        self.max_per_minute = max_per_minute
        self._requests: dict[int, list[float]] = {}  # char_id -> [timestamps]

    def check(self, char_id: int) -> bool:
        """Returns True if the request is allowed."""
        now = time.time()
        cutoff = now - 60.0

        if char_id not in self._requests:
            self._requests[char_id] = []

        # Prune old entries
        self._requests[char_id] = [
            t for t in self._requests[char_id] if t > cutoff
        ]

        if len(self._requests[char_id]) >= self.max_per_minute:
            return False

        self._requests[char_id].append(now)
        return True

    def time_until_next(self, char_id: int) -> float:
        """Seconds until the next request is allowed."""
        if char_id not in self._requests or not self._requests[char_id]:
            return 0.0
        oldest = min(self._requests[char_id])
        return max(0.0, (oldest + 60.0) - time.time())


# ── AI Manager ──

class AIManager:
    """
    Central AI manager. The game server creates one of these.
    All NPC dialogue and tactical AI goes through here.
    """

    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config or AIConfig()
        self.providers: dict[str, AIProvider] = {}
        self.rate_limiter = RateLimiter(self.config.max_requests_per_minute)
        self._setup_providers()

    def _setup_providers(self):
        """Initialize configured providers."""
        if self.config.default_provider == "ollama":
            self.providers["ollama"] = OllamaProvider(
                host=self.config.ollama_host,
                default_model=self.config.default_model,
                timeout=self.config.ollama_timeout,
            )
        # Always have a mock as fallback
        self.providers["mock"] = MockProvider()
        # Optional: Claude API provider (Director AI)
        _claude = make_claude_provider()
        if _claude is not None:
            self.providers["claude"] = _claude
            log.info("ClaudeProvider registered (Director AI).")

    def get_provider(self, name: str = "") -> AIProvider:
        """Get a provider by name, or the default."""
        name = name or self.config.default_provider
        return self.providers.get(name, self.providers.get("mock"))

    async def warmup(self) -> None:
        """Preload the local model at server startup so the first player `talk`
        isn't a cold multi-second load.

        Best-effort and fully guarded — never raises into the boot path. Honors
        ai.warmup_on_startup / ai.autostart_ollama (default both on). If Ollama
        is unreachable it optionally spawns `ollama serve`, re-probes, then loads
        the configured model with the configured keep_alive.
        """
        if not self.config.enabled:
            return
        try:
            from engine.tunables import get_tunable
        except Exception:
            def get_tunable(_k, _d=None):
                return _d
        if not bool(get_tunable("ai.warmup_on_startup", True)):
            return

        prov = self.get_provider("ollama")
        if not isinstance(prov, OllamaProvider):
            return
        keep_alive = str(get_tunable("ai.ollama_keep_alive", "30m"))

        if not await prov.is_available() and bool(get_tunable("ai.autostart_ollama", True)):
            log.info("[ai] Ollama not reachable at %s — attempting autostart…", prov.host)
            _try_autostart_ollama()
            for _ in range(15):
                await asyncio.sleep(1.0)
                prov._available = None  # force a fresh probe past the cached flag
                if await prov.is_available():
                    break

        if not await prov.is_available():
            log.warning(
                "[ai] Ollama not reachable at %s — NPC dialogue will use canned "
                "in-era fallbacks. Start it with `ollama serve` and pull the "
                "model (`ollama pull %s`).", prov.host, prov.default_model,
            )
            return

        log.info("[ai] warming up Ollama model %s (keep_alive=%s)…",
                 prov.default_model, keep_alive)
        ok = await prov.preload(keep_alive)
        if ok:
            log.info("[ai] Ollama model %s is resident and warm.", prov.default_model)
        else:
            log.warning(
                "[ai] Ollama model %s did not confirm preload; first talk may "
                "cold-load. Is the tag pulled? `ollama pull %s`.",
                prov.default_model, prov.default_model,
            )

    async def is_available(self, provider: str = "") -> bool:
        """Quick availability check for the default (or named) provider.

        Used by callers that want to surface a one-time UX signal when
        the LLM backend is offline. Wraps the provider's own probe and
        treats any exception as unavailable so callers don't need to
        handle errors themselves.
        """
        prov = self.get_provider(provider)
        if prov is None:
            return False
        try:
            return await prov.is_available()
        except Exception:
            log.debug("is_available probe raised", exc_info=True)
            return False

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        char_id: int = 0,
        max_tokens: int = 200,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: str = "",
        provider: str = "",
        fallback_text: str = "",
        options: Optional[dict] = None,
        keep_alive: str = "",
    ) -> str:
        """
        Generate AI text with rate limiting and fallback.

        Args:
            system_prompt: The NPC's personality/context prompt.
            messages: Conversation history.
            char_id: Player character ID (for rate limiting).
            model: Override model (e.g. tier2 for important NPCs).
            provider: Override provider name.
            fallback_text: Text to return if AI is unavailable.

        Returns:
            Generated text, or fallback_text on failure.
        """
        if not self.config.enabled:
            return fallback_text or "..."

        # Rate limit check
        if char_id and not self.rate_limiter.check(char_id):
            wait = self.rate_limiter.time_until_next(char_id)
            log.debug("Rate limited char %d (wait %.1fs)", char_id, wait)
            return fallback_text or "..."

        # Get provider
        prov = self.get_provider(provider)

        # Check availability
        if not await prov.is_available():
            log.debug("Provider '%s' unavailable, using fallback", prov.name)
            return fallback_text or "..."

        # Generate
        result = await prov.generate(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
            model=model,
            options=options,
            keep_alive=keep_alive,
        )

        if not result:
            return fallback_text or "..."

        return result

    async def check_status(self) -> dict:
        """Check status of all providers."""
        status = {}
        for name, prov in self.providers.items():
            available = await prov.is_available()
            info = {"available": available, "name": name}
            if isinstance(prov, OllamaProvider) and available:
                info["models"] = await prov.list_models()
            status[name] = info
        return status
