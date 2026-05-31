"""
test_env_substrate_wireup.py — Phase-1 environment substrate wiring.

Guards the seam end-to-end without a live server/browser:
  · server/session.py stamps hud["environment"] = resolve_environment(props)
    inside _hud_area_map (always-sent, before the registry early-returns).
  · static/client.html stores data.environment → window._sw_env, exposes
    _envTime()/_envWeather() with safe fallbacks, and BOTH Tier1aBody render
    sites (mini + modal) pass those accessors — no hardcoded 'day'/'clear'.
The _envTime/_envWeather fallback behaviour is exercised under jsdom.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
SESSION_PY = REPO_ROOT / "server" / "session.py"

from .spa_dom_harness import run_with_dom  # noqa: E402


def test_server_emits_environment_in_hud_area_map():
    src = SESSION_PY.read_text(encoding="utf-8")
    start = src.index("async def _hud_area_map")
    body = src[start: start + 4000]
    assert "from engine.world_time import resolve_environment" in body, (
        "_hud_area_map must import the environment resolver"
    )
    assert re.search(r'hud\["environment"\]\s*=\s*resolve_environment\(', body), (
        "_hud_area_map must stamp hud['environment'] = resolve_environment(props)"
    )
    # must be emitted BEFORE the registry early-return so legacy (non-geometry)
    # areas still get an environment.
    env_pos = body.index('hud["environment"]')
    reg_pos = body.index('registry = getattr(session_mgr')
    assert env_pos < reg_pos, "environment must be stamped before the registry gate"


def test_client_stores_and_consumes_environment():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    # stored on every hud update
    assert "window._sw_env = data.environment" in html, "handleHudUpdate must stash data.environment"
    # accessors exist
    assert "function _envTime()" in html and "function _envWeather()" in html
    # both Tier1aBody render sites use the accessors
    assert html.count("time:    _envTime()") >= 2, "both render sites must use _envTime()"
    assert html.count("weather: _envWeather()") >= 2, "both render sites must use _envWeather()"
    # the old hardcoded placeholders are gone from the Tier1aBody calls
    assert "time:    'day',         // 4.2b" not in html
    assert "time:    'day',                  // 4.2c" not in html


def test_env_accessors_fallback_under_jsdom(tmp_path):
    mod = (
        "function _envTime()    { var e = window._sw_env; return (e && e.time_of_day) ? e.time_of_day : 'day'; }\n"
        "function _envWeather() { var e = window._sw_env; return (e && e.weather)     ? e.weather     : 'clear'; }\n"
        "window._envTime = _envTime; window._envWeather = _envWeather;\n"
    )
    p = tmp_path / "env_accessors.js"
    p.write_text(mod, encoding="utf-8")
    setup_js = r"""
        var out = {};
        // no env set → fallbacks
        out.t0 = window._envTime();
        out.w0 = window._envWeather();
        // env set → live values
        window._sw_env = { time_of_day: 'night', weather: 'sandstorm' };
        out.t1 = window._envTime();
        out.w1 = window._envWeather();
        // partial env → per-field fallback
        window._sw_env = { time_of_day: 'dusk' };
        out.t2 = window._envTime();
        out.w2 = window._envWeather();
        result = out;
    """
    out = run_with_dom([p], setup_js)  # auto-skips without jsdom
    assert out["t0"] == "day" and out["w0"] == "clear"
    assert out["t1"] == "night" and out["w1"] == "sandstorm"
    assert out["t2"] == "dusk" and out["w2"] == "clear"
