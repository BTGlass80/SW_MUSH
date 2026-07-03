# -*- coding: utf-8 -*-
"""Ollama `options`/`keep_alive` passthrough + startup warmup (Fable §3–§5, §7).

The Qwen3.5 swap needs per-call `num_ctx` (VRAM caps) and Qwen's anti-repetition
sampling, plus `keep_alive` so the 9B doesn't cold-load between idle ticks. The
provider's `generate()` grew an `options: dict` + `keep_alive: str` passthrough:
explicit temperature/max_tokens still win, extra options merge under them, and a
call that passes neither produces a byte-identical payload to before the swap
(regression pin). A startup `warmup()` preloads the model; it is fully guarded
and a no-op when disabled or when Ollama isn't the provider.
"""
import pytest

import ai.providers as providers
from ai.providers import AIConfig, AIManager, MockProvider, OllamaProvider


# ── Fake aiohttp so we can inspect the exact payload without a live daemon ──

class _FakeResp:
    def __init__(self, captured):
        self.status = 200
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return {"message": {"content": "ok"}}

    async def read(self):
        return b""

    async def text(self):
        return ""


class _FakeSession:
    def __init__(self, captured):
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, timeout=None):
        self._captured["url"] = url
        self._captured["payload"] = json
        return _FakeResp(self._captured)


class _FakeAiohttp:
    def __init__(self, captured):
        self._captured = captured

    def ClientSession(self):
        return _FakeSession(self._captured)

    def ClientTimeout(self, total=None):
        return total


@pytest.fixture
def captured(monkeypatch):
    cap = {}
    monkeypatch.setattr(providers, "_aiohttp", _FakeAiohttp(cap))
    monkeypatch.setattr(providers, "_AIOHTTP_AVAILABLE", True)
    return cap


async def _gen(prov, **kw):
    return await prov.generate(
        system_prompt="sys",
        messages=[{"role": "user", "content": "hi"}],
        **kw,
    )


# ── §3 payload shape ──

@pytest.mark.asyncio
async def test_absent_options_payload_is_unchanged(captured):
    # Regression pin: no options/keep_alive ⇒ same payload shape as pre-swap.
    prov = OllamaProvider(default_model="qwen3.5:9b")
    await _gen(prov, max_tokens=250, temperature=0.85)
    payload = captured["payload"]
    assert payload["options"] == {"temperature": 0.85, "num_predict": 250}
    assert "keep_alive" not in payload
    assert "format" not in payload


@pytest.mark.asyncio
async def test_options_merge_under_explicit_temperature(captured):
    prov = OllamaProvider(default_model="qwen3.5:9b")
    await _gen(
        prov,
        max_tokens=200,
        temperature=0.7,
        options={"num_ctx": 2048, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5},
    )
    opts = captured["payload"]["options"]
    assert opts["num_ctx"] == 2048
    assert opts["top_p"] == 0.8
    assert opts["top_k"] == 20
    assert opts["presence_penalty"] == 1.5
    # Explicit args win over any same-named option.
    assert opts["temperature"] == 0.7
    assert opts["num_predict"] == 200


@pytest.mark.asyncio
async def test_explicit_temperature_beats_options_temperature(captured):
    prov = OllamaProvider(default_model="qwen3.5:9b")
    await _gen(prov, temperature=0.7, options={"temperature": 0.1})
    assert captured["payload"]["options"]["temperature"] == 0.7


@pytest.mark.asyncio
async def test_none_valued_options_are_dropped(captured):
    prov = OllamaProvider(default_model="qwen3.5:9b")
    await _gen(prov, options={"num_ctx": None, "top_p": 0.8})
    opts = captured["payload"]["options"]
    assert "num_ctx" not in opts
    assert opts["top_p"] == 0.8


@pytest.mark.asyncio
async def test_keep_alive_present_when_set(captured):
    prov = OllamaProvider(default_model="qwen3.5:9b")
    await _gen(prov, keep_alive="30m")
    assert captured["payload"]["keep_alive"] == "30m"


@pytest.mark.asyncio
async def test_json_mode_still_sets_format(captured):
    prov = OllamaProvider(default_model="qwen3.5:9b")
    await _gen(prov, json_mode=True, options={"num_ctx": 2048}, keep_alive="30m")
    assert captured["payload"]["format"] == "json"


# ── §3 dispatch: AIManager threads the kwargs through to the provider ──

@pytest.mark.asyncio
async def test_manager_threads_options_and_keep_alive_to_provider():
    ai = AIManager(AIConfig(enabled=True))
    await ai.generate(
        system_prompt="s",
        messages=[{"role": "user", "content": "x"}],
        provider="mock",
        options={"num_ctx": 4096},
        keep_alive="30m",
    )
    mock = ai.providers["mock"]
    assert isinstance(mock, MockProvider)
    assert mock.last_options == {"num_ctx": 4096}
    assert mock.last_keep_alive == "30m"


# ── §4/§5 bark-lane defaults (Qwen sampling + VRAM ctx caps) ──

def test_bark_helpers_carry_qwen_defaults():
    from engine.idle_queue import _bark_temperature, _bark_options, _keep_alive
    assert _bark_temperature() == 0.7
    o = _bark_options()
    assert o == {"num_ctx": 2048, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}
    assert _keep_alive()  # non-empty duration string


def test_lane_ctx_caps_fit_vram_budget():
    from engine.idle_queue import _ctx_options
    # Talk is the biggest steady-state lane; scene is the deepest single-shot.
    assert _ctx_options("ai.num_ctx_talk", 4096)["num_ctx"] == 4096
    assert _ctx_options("ai.num_ctx_scene", 8192)["num_ctx"] == 8192


# ── warmup guard rails (never raises into boot) ──

@pytest.mark.asyncio
async def test_warmup_noop_when_ai_disabled():
    ai = AIManager(AIConfig(enabled=False))
    await ai.warmup()  # must simply return, no exception


@pytest.mark.asyncio
async def test_warmup_noop_when_provider_is_not_ollama():
    ai = AIManager(AIConfig(enabled=True, default_provider="mock"))
    # No ollama provider registered ⇒ warmup returns without touching anything.
    await ai.warmup()


@pytest.mark.asyncio
async def test_preload_posts_model_and_keep_alive(captured):
    prov = OllamaProvider(default_model="qwen3.5:9b")
    ok = await prov.preload(keep_alive="30m")
    assert ok is True
    assert captured["url"].endswith("/api/generate")
    assert captured["payload"] == {"model": "qwen3.5:9b", "keep_alive": "30m"}
