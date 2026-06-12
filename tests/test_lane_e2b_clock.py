# -*- coding: utf-8 -*-
"""
tests/test_lane_e2b_clock.py — Sourcebook Enrichment Lane E2b (Secrets of Tatooine §1).

The Tatooine day/night clock vocabulary + its consumers:
  * world_time.resolve_period_label — planet-keyed period names (First Dawn,
    Second Dawn, High Noon, First Twilight, Second Twilight, ...), layered over
    the SAME day cycle. The renderer is untouched (resolve_time_of_day still
    returns day/dusk/night) — the label only NESTS inside those bands.
  * +weather / +time command (parser/builtin_commands.WeatherCommand) — the
    visible, both-platform consumer; reads the room's inherited `time_vocab`
    zone property (or the wilderness region planet) and the world-event manager.
  * hazards.extreme_heat — graded by the clock (worst at the noon suns, eased
    after dark).
  * data/worlds/clone_wars/zones.yaml — Tatooine zones carry time_vocab: tatooine.
  * build_mos_eisley.py — CLI --era default corrected gcw -> clone_wars (the gcw
    tree was deleted in the 2026-06-06 retirement drop).

No renderer change, no schema change.
"""
from __future__ import annotations
import os
import yaml

from engine.world_time import (
    resolve_period_label, global_time_of_day, PLANET_PERIOD_LABELS,
    DAY_LENGTH_SECONDS as _DAY,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _src(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _at(frac: float):
    """(label, renderer_state) at a given cycle fraction, deterministic."""
    now = frac * _DAY
    return (resolve_period_label("tatooine", now=now, day_length_seconds=_DAY),
            global_time_of_day(now, _DAY))


# ══════════════════════════════════════════════════════════════════════════
# world_time: Tatooine period labels NEST inside the renderer's day/dusk/night
# ══════════════════════════════════════════════════════════════════════════

def test_tatooine_labels_map_to_correct_periods():
    cases = [
        (0.10, "Deep Night", "night"),
        (0.24, "First Dawn", "dusk"),
        (0.28, "Second Dawn", "dusk"),
        (0.40, "Morning", "day"),
        (0.50, "High Noon", "day"),
        (0.62, "Afternoon", "day"),
        (0.72, "First Twilight", "dusk"),
        (0.76, "Second Twilight", "dusk"),
        (0.90, "Night", "night"),
    ]
    for frac, exp_label, exp_state in cases:
        label, state = _at(frac)
        assert label == exp_label, f"frac {frac}: label {label!r} != {exp_label!r}"
        # The label must agree with the renderer band it sits inside.
        assert state == exp_state, f"frac {frac}: renderer {state!r} != {exp_state!r}"


def test_all_five_sun_events_present():
    labels = [lab for _, lab in PLANET_PERIOD_LABELS["tatooine"]]
    for sun_event in ("First Dawn", "Second Dawn", "High Noon",
                      "First Twilight", "Second Twilight"):
        assert sun_event in labels, f"missing SoT sun-event label {sun_event!r}"


def test_unknown_vocab_falls_back_to_generic_band():
    # No idiom -> capitalized renderer band; never raises.
    assert resolve_period_label("kamino", now=0.50 * _DAY, day_length_seconds=_DAY) == "Day"
    assert resolve_period_label(None, now=0.10 * _DAY, day_length_seconds=_DAY) == "Night"
    assert resolve_period_label("", now=0.24 * _DAY, day_length_seconds=_DAY) == "Dusk"


def test_label_does_not_change_renderer_tokens():
    """Belt-and-suspenders: the renderer set is still exactly day/dusk/night —
    the label layer added no new token to global_time_of_day."""
    seen = {global_time_of_day(f * _DAY, _DAY) for f in
            [i / 100 for i in range(100)]}
    assert seen == {"day", "dusk", "night"}, seen


# ══════════════════════════════════════════════════════════════════════════
# hazards: extreme_heat is graded by the clock (noon worst, night eased)
# ══════════════════════════════════════════════════════════════════════════

def test_extreme_heat_time_modifier():
    from engine.hazards import _extreme_heat_time_mod
    assert _extreme_heat_time_mod("day") == 3        # noon suns: worst
    assert _extreme_heat_time_mod("dusk") == 0
    assert _extreme_heat_time_mod("night") == -4     # after dark: relief
    assert _extreme_heat_time_mod("nonsense") == 0   # unknown -> no-op
    assert _extreme_heat_time_mod(None) == 0


def test_heat_grading_is_wired_into_the_check():
    """Structural: check_hazard_for_character resolves time-of-day and applies the
    modifier for extreme_heat (the difficulty isn't returned, so pin the wiring)."""
    src = _src("engine/hazards.py")
    assert "_extreme_heat_time_mod(" in src
    assert "resolve_time_of_day" in src
    # gated to extreme_heat (the modifier sits under the hazard_type guard)
    i_guard = src.index('hazard_type == "extreme_heat"')
    i_mod = src.index("_extreme_heat_time_mod(_tod)")
    assert i_guard < i_mod, "heat modifier is not under the extreme_heat guard"


# ══════════════════════════════════════════════════════════════════════════
# +weather command: registered + reads the right sources
# ══════════════════════════════════════════════════════════════════════════

def test_storm_pips_to_dice_helper():
    from parser.builtin_commands import _storm_pips_to_dice
    assert _storm_pips_to_dice(-3) == "-1D"
    assert _storm_pips_to_dice(-6) == "-2D"
    assert _storm_pips_to_dice(-9) == "-3D"
    assert _storm_pips_to_dice(-1) == "-1 pip"
    assert _storm_pips_to_dice(-2) == "-2 pips"
    assert _storm_pips_to_dice(-4) == "-1D+1"


def test_weather_command_registered():
    from parser.commands import CommandRegistry
    import parser.builtin_commands as bc
    reg = CommandRegistry()
    bc.register_all(reg)
    # the registry resolves the key and its aliases
    for key in ("+weather", "+time", "weather"):
        assert reg.get(key) is not None, f"+weather not registered under {key!r}"


def test_weather_command_reads_expected_sources():
    src = _src("parser/builtin_commands.py")
    assert "class WeatherCommand(" in src
    assert 'get_room_property(room_id, "time_vocab")' in src
    assert "resolve_period_label(" in src
    assert "get_world_event_manager()" in src
    assert "WeatherCommand()," in src   # actually in the register list


# ══════════════════════════════════════════════════════════════════════════
# data: zones + build default
# ══════════════════════════════════════════════════════════════════════════

def test_tatooine_zones_carry_time_vocab():
    with open(os.path.join(_ROOT, "data", "worlds", "clone_wars", "zones.yaml"),
              encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    def find_zone_map(obj):
        if isinstance(obj, dict):
            if any(str(k).startswith("tatooine_") for k in obj):
                return obj
            for v in obj.values():
                r = find_zone_map(v)
                if r:
                    return r
        return None

    zmap = find_zone_map(data)
    assert zmap, "could not locate the zone map in zones.yaml"
    tat = {k: v for k, v in zmap.items() if str(k).startswith("tatooine_")}
    assert len(tat) >= 8, f"expected >=8 Tatooine zones, found {len(tat)}"
    for k, v in tat.items():
        props = v.get("properties") or {}
        assert props.get("time_vocab") == "tatooine", \
            f"{k} missing time_vocab: tatooine (got {props.get('time_vocab')!r})"


def test_build_mos_eisley_era_default_is_clone_wars():
    """The gcw data tree was deleted (2026-06-06 retirement); the CLI default
    must no longer be gcw or a bare run fails."""
    src = _src("build_mos_eisley.py")
    assert '--era", default="clone_wars"' in src
    assert '--era", default="gcw"' not in src
