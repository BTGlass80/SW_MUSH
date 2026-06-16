"""tests/test_guide_09_cp_progression_rework.py — Guide_09_CP_Progression.md accuracy.

Verifies the guide reflects live engine constants from engine/cp_engine.py (v23):
  - 200 ticks = 1 CP (was 300 before v23)
  - 400-tick weekly cap (was 300 before v23)
  - 10 ticks/day passive (was 5 before v23)
  - Same-room kudos requirement removed (v23)
  - Code string in cp_commands.py uses TICKS_PER_CP constant (not hard-coded 300)
"""

import pathlib
import ast

GUIDE_PATH = pathlib.Path("data/guides/Guide_09_CP_Progression.md")
CP_COMMANDS_PATH = pathlib.Path("parser/cp_commands.py")


def _guide_text():
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_09_CP_Progression.md not found"


def test_ticks_per_cp_correct():
    text = _guide_text()
    assert "200 ticks = 1 Character Point" in text or "200 ticks = 1 CP" in text, (
        "Guide still says 300 ticks = 1 CP; engine constant TICKS_PER_CP = 200"
    )


def test_stale_300_ticks_core_loop_removed():
    text = _guide_text()
    assert "accumulate 300 ticks" not in text, (
        "Guide core-loop sentence still references stale '300 ticks'; should be 200"
    )


def test_weekly_cap_correct():
    text = _guide_text()
    assert "400" in text, "Guide should mention 400-tick weekly cap (was 300 pre-v23)"
    assert "300-tick weekly cap" not in text, (
        "Guide still references stale '300-tick weekly cap'; engine cap is 400"
    )


def test_max_cp_per_week_correct():
    text = _guide_text()
    assert "2 CP/week" in text or "2 CP per week" in text, (
        "Guide should state max 2 CP/week from ticks (400 cap / 200 per CP)"
    )


def test_passive_ticks_per_day_correct():
    text = _guide_text()
    assert "10 ticks/day" in text, (
        "Guide passive rate still shows stale '5 ticks/day'; engine = 10 ticks/day"
    )
    assert "5 ticks/day" not in text, (
        "Guide still mentions stale '5 ticks/day'"
    )


def test_no_same_room_kudos_requirement():
    text = _guide_text()
    assert "Both players must be in the same room" not in text, (
        "Guide still states same-room kudos requirement; this was removed in v23"
    )


def test_kudos_fraction_of_cap_updated():
    text = _guide_text()
    assert "over a third of the 300-tick" not in text, (
        "Guide still references stale '300-tick' cap in kudos section"
    )


def test_anti_farming_cap_correct():
    text = _guide_text()
    assert "400 ticks" in text, (
        "Anti-farming section should mention 400-tick cap"
    )
    assert "Weekly hard cap (300 ticks)" not in text, (
        "Anti-farming section still shows stale '300 ticks'"
    )


def test_cp_commands_display_string_not_hardcoded():
    """cp_commands.py must not hard-code '300 ticks = 1 CP' in the player-visible string."""
    src = CP_COMMANDS_PATH.read_text(encoding="utf-8")
    assert "300 ticks = 1 CP" not in src, (
        "cp_commands.py still has hard-coded '300 ticks = 1 CP' display string; "
        "use TICKS_PER_CP constant"
    )


def test_cp_commands_syntax_valid():
    src = CP_COMMANDS_PATH.read_text(encoding="utf-8")
    try:
        ast.parse(src)
    except SyntaxError as e:
        raise AssertionError(f"cp_commands.py has syntax error: {e}") from e


def test_guide_syntax_no_stale_numbers():
    """Broad check — guide should not contain any of the three stale values."""
    text = _guide_text()
    stale = [
        ("300 ticks = 1 CP", "core-loop sentence"),
        ("300 ticks = 1 Character Point", "§2 header"),
        ("cap of 300 ticks", "weekly-cap phrasing"),
        ("hard cap of 300", "anti-farming section"),
    ]
    for pattern, label in stale:
        assert pattern not in text, (
            f"Stale value '{pattern}' ({label}) still in Guide_09"
        )
