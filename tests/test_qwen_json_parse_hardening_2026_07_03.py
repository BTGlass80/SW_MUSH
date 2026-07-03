# -*- coding: utf-8 -*-
"""Bark JSON-parse hardening for the Qwen3.5 swap (Fable §2, 2026-07-03).

Qwen3.5 Small ships thinking-OFF, and Ollama has a bug (ollama#14645) where
`format:"json"` is *silently ignored* when thinking is off — so the model may
return a JSON array wrapped in a ```json fence, surrounded by prose, or behind a
<think> preamble instead of clean JSON. The bark lanes used a bare
`json.loads(cleaned)` that would raise/return nothing → bark pools silently
starve. `_extract_json_array` makes that path tolerant: strip fences / <think>,
then fall back to the first balanced, string-aware ``[ … ]`` substring. It never
raises — a failure returns None and the caller leaves the pool as-is.
"""
import pytest

from engine.idle_queue import _extract_json_array


def test_clean_array_parses():
    assert _extract_json_array('["a", "b", "c"]') == ["a", "b", "c"]


def test_fenced_json_array():
    raw = "```json\n[\"a\", \"b\"]\n```"
    assert _extract_json_array(raw) == ["a", "b"]


def test_bare_fence_without_lang_tag():
    raw = "```\n[\"only\"]\n```"
    assert _extract_json_array(raw) == ["only"]


def test_prose_before_array():
    # The classic non-json-mode failure: "Here are five lines: [ … ]"
    raw = 'Here are five ambient lines: ["one", "two", "three"]'
    assert _extract_json_array(raw) == ["one", "two", "three"]


def test_array_then_trailing_prose():
    raw = '["one", "two"]  Hope these fit the cantina!'
    assert _extract_json_array(raw) == ["one", "two"]


def test_think_preamble_then_array():
    # Future-proofs a thinking-enabled config: strip <think>…</think> first.
    raw = "<think>let me brainstorm some lines</think>\n[\"a\", \"b\"]"
    assert _extract_json_array(raw) == ["a", "b"]


def test_think_preamble_plus_fence():
    raw = "<think>hmm</think>\n```json\n[\"a\"]\n```"
    assert _extract_json_array(raw) == ["a"]


def test_brackets_inside_strings_dont_fool_the_scan():
    # The balanced scan is string-aware: brackets inside a quip are ignored.
    raw = 'prefix ["watch the [east] door", "clear"] suffix'
    assert _extract_json_array(raw) == ["watch the [east] door", "clear"]


def test_malformed_returns_none_not_raises():
    assert _extract_json_array("not json, no array here") is None
    assert _extract_json_array("[ unclosed, 'oops") is None
    assert _extract_json_array('["trailing", ]') is None  # invalid JSON


def test_object_wrapping_array_is_salvaged():
    # Robustness-first: if the model wraps the array in an object (a common
    # non-json-mode shape), salvage the inner array rather than starve the pool.
    # Downstream era/length filters drop anything junk that slips through.
    assert _extract_json_array('{"lines": ["a", "b"]}') == ["a", "b"]


def test_empty_and_none_inputs():
    assert _extract_json_array("") is None
    assert _extract_json_array(None) is None
    assert _extract_json_array("   \n  ") is None


def test_empty_array_is_a_valid_list():
    # Distinct from None: the model legitimately produced an (empty) array.
    assert _extract_json_array("[]") == []
