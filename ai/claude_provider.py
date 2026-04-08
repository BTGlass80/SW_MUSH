# -*- coding: utf-8 -*-
"""
ai/claude_provider.py
---------------------
Anthropic Claude API provider with monthly budget tracking and circuit breaker.

Used exclusively by the Director AI system for Faction Turn calls.
NPC dialogue remains on OllamaProvider.

Model: claude-haiku-4-5-20251001
Pricing: $1/MTok input, $5/MTok output
Budget: $20/month (2000 cents), circuit breaker at 90% ($18)
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

try:
    import aiohttp as _aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _aiohttp = None  # type: ignore[assignment]
    _AIOHTTP_AVAILABLE = False
    log.error("aiohttp not installed — ClaudeProvider will be permanently unavailable.")

# Lazy import to avoid circular dependency at module load time.
# AIProvider is imported inside the class body reference only.
from ai.providers import AIProvider

# ── Pricing constants ──────────────────────────────────────────────────────────
# Cents per token (fractional)
_INPUT_CENTS_PER_TOKEN  = 1.0 / 1_000_000    # $1 / MTok
_OUTPUT_CENTS_PER_TOKEN = 5.0 / 1_000_000    # $5 / MTok


class ClaudeProvider(AIProvider):
    """
    Anthropic Claude API provider.

    Implements the AIProvider interface.  The Director calls this via
    ai_manager.generate(provider="claude") — it never goes through the
    default Ollama path.

    Budget tracking:
    - Monthly spend tracked in memory (resets 1st of month UTC).
    - Circuit breaker fires at 90% of monthly_budget_cents.
    - Over-budget calls return "" immediately (graceful fallback).
    - Token counts read from response["usage"] on every successful call.
    """

    ENDPOINT = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        monthly_budget_cents: float = 2000.0,   # $20.00
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.model = model
        self.monthly_budget_cents = monthly_budget_cents
        self.timeout = timeout

        # Budget tracking state
        self._month_key: str = ""           # "2026-04"
        self._month_spent_cents: float = 0.0
        self._call_count: int = 0
        self._lock = asyncio.Lock()

    # ── AIProvider interface ───────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "claude"

    async def is_available(self) -> bool:
        """Return True if API key is configured and aiohttp is installed."""
        return _AIOHTTP_AVAILABLE and bool(self.api_key)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1000,
        temperature: float = 0.7,
        json_mode: bool = False,
        model: str = "",
    ) -> str:
        """
        Send a request to the Anthropic Messages API.

        Returns generated text, or empty string on failure/over-budget.
        """
        if not _AIOHTTP_AVAILABLE:
            log.warning("ClaudeProvider: aiohttp not available.")
            return ""

        if not self.api_key:
            log.warning("ClaudeProvider: no API key configured.")
            return ""

        # Circuit breaker check (thread-safe)
        async with self._lock:
            if self._is_over_budget():
                log.warning(
                    "ClaudeProvider: monthly budget exhausted (%.2f / %.2f cents). "
                    "Falling back to deterministic logic.",
                    self._month_spent_cents,
                    self.monthly_budget_cents,
                )
                return ""

        use_model = model or self.model

        payload: dict = {
            "model": use_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }

        if temperature != 1.0:
            payload["temperature"] = temperature

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

        try:
            async with _aiohttp.ClientSession() as session:
                async with session.post(
                    self.ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=_aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        error_body = await resp.text()
                        log.error(
                            "ClaudeProvider: API error %d: %s",
                            resp.status,
                            error_body[:300],
                        )
                        return ""

                    data = await resp.json()

        except asyncio.TimeoutError:
            log.warning("ClaudeProvider: request timed out (%.1fs).", self.timeout)
            return ""
        except Exception as exc:
            log.warning("ClaudeProvider: request failed: %s", exc)
            return ""

        # Extract text
        content_blocks = data.get("content", [])
        if not content_blocks:
            log.warning("ClaudeProvider: empty content in response.")
            return ""

        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text = block.get("text", "")
                break

        if not text:
            log.warning("ClaudeProvider: no text block in response.")
            return ""

        # Track token usage for budget accounting
        usage = data.get("usage", {})
        input_tokens  = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        call_cost_cents = (
            input_tokens  * _INPUT_CENTS_PER_TOKEN
            + output_tokens * _OUTPUT_CENTS_PER_TOKEN
        )

        async with self._lock:
            self._refresh_month()
            self._month_spent_cents += call_cost_cents
            self._call_count += 1

        log.debug(
            "ClaudeProvider: call #%d — %d in / %d out tokens — "
            "%.4f¢ this call — %.2f¢ month-to-date",
            self._call_count,
            input_tokens,
            output_tokens,
            call_cost_cents,
            self._month_spent_cents,
        )

        return text.strip()

    # ── Budget helpers ─────────────────────────────────────────────────────────

    def _refresh_month(self) -> None:
        """Reset monthly spend counter on calendar month rollover (UTC)."""
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if current_month != self._month_key:
            if self._month_key:
                log.info(
                    "ClaudeProvider: month rollover %s → %s. "
                    "Resetting spend (was %.2f¢).",
                    self._month_key,
                    current_month,
                    self._month_spent_cents,
                )
            self._month_key = current_month
            self._month_spent_cents = 0.0
            self._call_count = 0

    def _is_over_budget(self) -> bool:
        """True if monthly spend has hit the 90% circuit-breaker threshold."""
        self._refresh_month()
        threshold = self.monthly_budget_cents * 0.9
        return self._month_spent_cents >= threshold

    # ── Status / introspection ─────────────────────────────────────────────────

    def get_budget_stats(self) -> dict:
        """
        Return a snapshot of current budget state for @director budget command.

        Returns:
            {
                "month": "2026-04",
                "spent_cents": 142.3,
                "budget_cents": 2000.0,
                "remaining_cents": 1857.7,
                "pct_used": 7.1,
                "over_budget": False,
                "call_count": 38,
                "spent_dollars": 1.42,
                "budget_dollars": 20.00,
            }
        """
        self._refresh_month()
        spent = self._month_spent_cents
        budget = self.monthly_budget_cents
        remaining = max(0.0, budget - spent)
        pct = (spent / budget * 100.0) if budget > 0 else 0.0
        return {
            "month": self._month_key,
            "spent_cents": round(spent, 4),
            "budget_cents": budget,
            "remaining_cents": round(remaining, 4),
            "pct_used": round(pct, 1),
            "over_budget": self._is_over_budget(),
            "call_count": self._call_count,
            "spent_dollars": round(spent / 100.0, 4),
            "budget_dollars": round(budget / 100.0, 2),
        }

    def reset_budget_for_testing(self) -> None:
        """Dev/test helper: reset spend to zero without waiting for month rollover."""
        self._month_spent_cents = 0.0
        self._call_count = 0
        log.warning("ClaudeProvider: budget manually reset (testing only).")


# ── Module-level factory ───────────────────────────────────────────────────────

def make_claude_provider(
    monthly_budget_cents: float = 2000.0,
    timeout: float = 30.0,
) -> Optional["ClaudeProvider"]:
    """
    Construct a ClaudeProvider if ANTHROPIC_API_KEY is in the environment.

    Returns None if no API key is set (keeps AIManager setup clean).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        log.info("ClaudeProvider: ANTHROPIC_API_KEY not set — provider disabled.")
        return None
    return ClaudeProvider(
        api_key=api_key,
        monthly_budget_cents=monthly_budget_cents,
        timeout=timeout,
    )
