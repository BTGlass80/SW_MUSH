"""
test_fun16_ambient_audio.py — fun16 ambient audio system (zone-keyed loops).

Static-parse assertions (no node/jsdom needed):

  1. ZONE_AUDIO map exists and contains the expected zone-type keys.
  2. ambientAudioReact() is defined and hooked into both handleHudUpdate
     (ground) and handleSpaceState (space).
  3. Toggle default is OFF (sw_ambient_enabled absent/falsy).
  4. Missing-file guard: .catch() swallow present on the play() call so
     a 404 or autoplay-block never throws.
  5. try/catch wraps the Audio constructor + play() call.
  6. The UI button (#ambient-audio-btn) exists in the HTML.
  7. The toggle only auto-starts after the user gesture (button click) —
     never on page load (no ambientAudioReact call outside event handler
     and init's button.addEventListener block).
  8. Era-clean: no Imperial/Empire/Rebel/TIE in new audio-manager code.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
AUDIO_DIR   = REPO_ROOT / "static" / "audio"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def _extract_fn(html: str, fn_name: str) -> str:
    """Extract a top-level JS function body by brace-counting."""
    needle = "function " + fn_name + "("
    start = html.find(needle)
    if start == -1:
        return ""
    depth = 0
    i = start
    in_fn = False
    while i < len(html):
        ch = html[i]
        if ch == "{":
            depth += 1
            in_fn = True
        elif ch == "}":
            depth -= 1
            if in_fn and depth == 0:
                return html[start : i + 1]
        i += 1
    return html[start : start + 8000]


# ── 1. ZONE_AUDIO map ───────────────────────────────────────────────────────

def test_zone_audio_map_defined():
    assert "var ZONE_AUDIO" in _html(), "ZONE_AUDIO map not declared in client.html"


def test_zone_audio_map_contains_expected_keys():
    html = _html()
    start = html.find("var ZONE_AUDIO")
    assert start != -1
    # Grab the object literal up to the closing brace
    brace_open = html.find("{", start)
    brace_close = html.find("}", brace_open)
    obj_text = html[brace_open : brace_close + 1]
    for key in ("cantina", "spaceport", "landing", "market", "space", "deep_space", "urban", "city"):
        assert f"'{key}'" in obj_text or f'"{key}"' in obj_text, (
            f"ZONE_AUDIO missing key '{key}'"
        )


def test_zone_audio_map_has_expected_basenames():
    html = _html()
    start = html.find("var ZONE_AUDIO")
    brace_open = html.find("{", start)
    brace_close = html.find("}", brace_open)
    obj_text = html[brace_open : brace_close + 1]
    for basename in ("cantina", "spaceport", "market", "deep-space", "city"):
        assert basename in obj_text, f"ZONE_AUDIO missing basename '{basename}'"


# ── 2. ambientAudioReact defined and hooked ─────────────────────────────────

def test_ambient_audio_react_defined():
    assert re.search(r"function\s+ambientAudioReact\s*\(", _html()), (
        "ambientAudioReact() not defined in client.html"
    )


def test_ambient_audio_react_hooked_in_handle_hud_update():
    block = _extract_fn(_html(), "handleHudUpdate")
    assert "ambientAudioReact" in block, (
        "ambientAudioReact not called from handleHudUpdate (ground HUD path)"
    )


def test_ambient_audio_react_hooked_in_handle_space_state():
    block = _extract_fn(_html(), "handleSpaceState")
    assert "ambientAudioReact" in block, (
        "ambientAudioReact not called from handleSpaceState (space HUD path)"
    )


def test_ambient_audio_react_reads_zone_type():
    block = _extract_fn(_html(), "ambientAudioReact")
    assert "zone_type" in block or "zoneType" in block, (
        "ambientAudioReact must read zone_type / zoneType"
    )
    assert "ZONE_AUDIO" in block, (
        "ambientAudioReact must look up the ZONE_AUDIO map"
    )


# ── 3. Toggle defaults OFF ───────────────────────────────────────────────────

def test_ambient_enabled_var_defaults_false():
    html = _html()
    # The module-level declaration must default to false (not true)
    m = re.search(r"var\s+_ambientEnabled\s*=\s*(\w+)", html)
    assert m, "_ambientEnabled variable not declared"
    assert m.group(1) == "false", (
        "_ambientEnabled must default to false (audio OFF by default)"
    )


def test_localStorage_key_is_sw_ambient_enabled():
    html = _html()
    assert "sw_ambient_enabled" in html, (
        "localStorage key 'sw_ambient_enabled' not found in client.html"
    )


def test_ambient_not_auto_started_at_load():
    """ambientAudioReact must not be called at module/page load time —
    only after the user gesture (toggle click) or a subsequent zone push."""
    html = _html()
    # The init() function must not call ambientAudioReact directly at startup;
    # it wires the button listener which calls it on click.
    init_block = _extract_fn(html, "init")
    # The only permitted references inside init() are: the toggle event-listener
    # setup (addEventListener click) and the restore block (label only, no play).
    # We assert the call inside init is nested inside an addEventListener
    # (i.e. inside a function expression), not at the top level of init.
    react_idx = init_block.find("ambientAudioReact(")
    assert react_idx == -1 or "addEventListener" in init_block[:react_idx], (
        "ambientAudioReact must not be invoked at module load time (autoplay policy)"
    )


# ── 4 & 5. Fail-safe: try/catch + .catch() swallow ─────────────────────────

def test_audio_constructor_wrapped_in_try_catch():
    html = _html()
    # Find the _ambientCrossfadeTo function
    block = _extract_fn(html, "_ambientCrossfadeTo")
    assert "try" in block, "_ambientCrossfadeTo must wrap Audio() in a try block"
    assert "new Audio(" in block, "_ambientCrossfadeTo must create a new Audio element"


def test_play_promise_has_catch_swallow():
    html = _html()
    block = _extract_fn(html, "_ambientCrossfadeTo")
    # The .play() call must have a .catch() so a rejected promise (missing file
    # or autoplay block) is swallowed rather than propagated as an unhandled rejection.
    assert ".catch(" in block or ".catch(function" in block, (
        "_ambientCrossfadeTo must attach .catch() to the audio.play() promise "
        "so a missing file or autoplay block stays silent"
    )


def test_missing_file_produces_silence_not_error():
    """Composite: Audio() in try, play() with .catch — together these mean a
    404 never surfaces as an unhandled rejection or console error."""
    html = _html()
    block = _extract_fn(html, "_ambientCrossfadeTo")
    has_try      = "try" in block
    has_catch_fn = ".catch(" in block
    assert has_try and has_catch_fn, (
        "Missing-file guard requires both try/catch around Audio() and "
        ".catch() on play() — one or both are absent"
    )


# ── 6. UI button in HTML ────────────────────────────────────────────────────

def test_ambient_audio_button_in_html():
    assert 'id="ambient-audio-btn"' in _html(), (
        "#ambient-audio-btn button not found in client.html"
    )


def test_ambient_audio_button_has_sound_label():
    html = _html()
    idx = html.find('id="ambient-audio-btn"')
    assert idx != -1
    # Grab a small window around the button tag to check the text content
    snippet = html[idx : idx + 200]
    assert "SOUND" in snippet, (
        "#ambient-audio-btn should display 'SOUND' as its default label"
    )


# ── 7. static/audio/ dir + README exist ────────────────────────────────────

def test_audio_dir_exists():
    assert AUDIO_DIR.is_dir(), "static/audio/ directory must exist"


def test_audio_readme_exists():
    readme = AUDIO_DIR / "README.md"
    assert readme.is_file(), "static/audio/README.md must exist"


def test_audio_readme_documents_zone_map():
    readme = (AUDIO_DIR / "README.md").read_text(encoding="utf-8")
    for basename in ("cantina", "spaceport", "market", "deep-space", "city"):
        assert basename in readme, (
            f"static/audio/README.md must document track basename '{basename}'"
        )


def test_audio_readme_documents_license_requirement():
    readme = (AUDIO_DIR / "README.md").read_text(encoding="utf-8")
    assert "CC0" in readme, "README must mention CC0 license requirement"


# ── 8. Era-clean ────────────────────────────────────────────────────────────

def test_era_clean_audio_manager():
    html = _html()
    # Collect all new audio-manager functions
    combined = (
        _extract_fn(html, "ambientAudioReact")
        + _extract_fn(html, "_ambientCrossfadeTo")
        + _extract_fn(html, "_ambientFadeOut")
        + _extract_fn(html, "_ambientStop")
        + _extract_fn(html, "_ambientGetVolume")
    )
    for token in (r"\bempire\b", r"\brebel\b", r"\bimperial\b", r"\bTIE\b"):
        assert not re.search(token, combined, re.IGNORECASE), (
            f"Era token '{token}' found in ambient audio manager code"
        )
