# -*- coding: utf-8 -*-
"""OLLAMA_MODEL env-driven local-model selection (Fable 2026-07-03 review).

The NPC-dialogue model is no longer hard-pinned to Mistral 7B. `AIConfig`'s three
model fields read the `OLLAMA_MODEL` env var at instantiation (default Qwen3.5-9B),
so swapping models is a one-line env change with no code edit. `OLLAMA_TIER2_MODEL`
optionally points the premium story-NPC tier at a bigger tag.
"""
import pytest

from ai.providers import AIConfig, _DEFAULT_OLLAMA_MODEL


def test_default_retires_mistral_as_the_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TIER2_MODEL", raising=False)
    cfg = AIConfig()
    for m in (cfg.default_model, cfg.tier1_model, cfg.tier2_model):
        assert m == _DEFAULT_OLLAMA_MODEL
        assert "mistral" not in m.lower()  # the Sep-2023 model is no longer the default


def test_ollama_model_env_drives_all_tiers(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    monkeypatch.delenv("OLLAMA_TIER2_MODEL", raising=False)
    cfg = AIConfig()
    assert cfg.default_model == "qwen3.5:9b"
    assert cfg.tier1_model == "qwen3.5:9b"
    assert cfg.tier2_model == "qwen3.5:9b"


def test_tier2_env_overrides_only_tier2(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("OLLAMA_TIER2_MODEL", "qwen3.5:14b")
    cfg = AIConfig()
    assert cfg.tier1_model == "qwen3.5:9b"
    assert cfg.tier2_model == "qwen3.5:14b"


def test_blank_or_whitespace_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "   ")
    monkeypatch.delenv("OLLAMA_TIER2_MODEL", raising=False)
    cfg = AIConfig()
    assert cfg.default_model == _DEFAULT_OLLAMA_MODEL


def test_ollama_provider_default_param_is_the_shared_default():
    # A bare OllamaProvider() (no config) also uses the shared default, not mistral.
    from ai.providers import OllamaProvider
    prov = OllamaProvider()
    assert prov.default_model == _DEFAULT_OLLAMA_MODEL
    assert "mistral" not in prov.default_model.lower()
