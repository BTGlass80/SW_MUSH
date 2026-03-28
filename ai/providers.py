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
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ── Configuration ──

@dataclass
class AIConfig:
    """Global AI configuration."""
    enabled: bool = True
    default_provider: str = "ollama"       # "ollama", "mock"
    default_model: str = "mistral:latest"  # Match ollama pull name exactly

    # Ollama settings
    ollama_host: str = "http://localhost:11434"
    ollama_timeout: float = 60.0           # seconds (first call loads the model)

    # Rate limiting
    max_requests_per_minute: int = 10      # per player
    npc_thinking_emote: bool = True        # show "NPC ponders..." while waiting

    # Model tiers
    tier1_model: str = "mistral:latest"    # Fast, most NPCs
    tier2_model: str = "mistral:latest"    # Premium story NPCs (upgrade if you have a bigger model)
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
                 default_model: str = "mistral:7b",
                 timeout: float = 15.0):
        self.host = host.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._available: Optional[bool] = None
        self._last_check: float = 0

    @property
    def name(self) -> str:
        return "ollama"

    async def is_available(self) -> bool:
        """Check if Ollama is running (cached for 30 seconds)."""
        now = time.time()
        if self._available is not None and (now - self._last_check) < 30:
            return self._available

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.host}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    self._available = resp.status == 200
        except Exception:
            self._available = False

        self._last_check = now
        if self._available:
            log.debug("Ollama is available at %s", self.host)
        else:
            log.warning("Ollama is not available at %s", self.host)
        return self._available

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: str = "",
    ) -> str:
        model = model or self.default_model

        # Build the Ollama API request
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if json_mode:
            payload["format"] = "json"

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.host}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        log.warning("Ollama error %d: %s", resp.status, error_text[:200])
                        print(f"[AI] Ollama error {resp.status}: {error_text[:200]}")
                        return ""

                    data = await resp.json()
                    content = data.get("message", {}).get("content", "")
                    return content.strip()

        except asyncio.TimeoutError:
            log.warning("Ollama request timed out (%.1fs)", self.timeout)
            print(f"[AI] Ollama request timed out ({self.timeout}s) - model may still be loading")
            return ""
        except Exception as e:
            log.warning("Ollama request failed: %s", e)
            print(f"[AI] Ollama request failed: {e}")
            return ""

    async def list_models(self) -> list[str]:
        """List models available in Ollama."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.host}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return [m["name"] for m in data.get("models", [])]
        except Exception:
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
    ) -> str:
        self.last_system_prompt = system_prompt
        self.last_messages = messages
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

    def get_provider(self, name: str = "") -> AIProvider:
        """Get a provider by name, or the default."""
        name = name or self.config.default_provider
        return self.providers.get(name, self.providers.get("mock"))

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
