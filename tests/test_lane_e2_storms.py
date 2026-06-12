# -*- coding: utf-8 -*-
"""
tests/test_lane_e2_storms.py — Sourcebook Enrichment Lane E2a (Secrets of Tatooine §3).

Graded sand-weather as world events, layered above the existing live SANDSTORM:
  * SANDSTORM    re-tuned: now also fouls ranged fire (perception -1D, ranged -1D)
  * GRAVEL_STORM (new): worse — perception -2D, ranged -2D
  * SANDWHIRL    (new): the violent set-piece — perception -3D, ranged -3D, short-lived

Two effects, each with a LIVE consumer (no effect declared without one — anti-phantom):
  * perception_penalty -> engine/skill_checks.perform_skill_check (observation family)
  * ranged_penalty     -> engine/combat._resolve_ranged_attack (raises ranged difficulty)

d20 source DCs/damage discarded; D6 re-stat (-1D = -3 pips), graded x1 / x2 / x3.

DEFERRED (flagged, NOT shipped): the sandwhirl's SPACE form (dragging a starship) —
there is no space-weather consumer in HEAD, so flight effects are intentionally not
declared. The Director-fired narration path is separately flagged as a pre-existing
latent bug (activate_event signature mismatch); storms fire via the working timer path.
"""
from __future__ import annotations
import os
import re
import time
import json
import pytest

from engine.world_events import (
    get_world_event_manager, EventType, EVENT_DEFS, VALID_EVENT_TYPES,
    ActiveEvent,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _src(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _activate(wem, etype):
    """Inject an active event DIRECTLY (bypass activate_event's cooldowns).
    Global zone scope so the global get_effect() always resolves it. These are
    consumption tests (does the metered mechanic read the effect?), order-free."""
    edef = EVENT_DEFS[etype]
    now = time.time()
    wem._active.append(ActiveEvent(
        event_type=etype,
        zones_affected=[],
        started_at=now,
        expires_at=now + 3600,
        headline=edef.name,
        mechanical_effects=dict(edef.mechanical_effects),
    ))


@pytest.fixture
def clean_events():
    """Isolate the world-event singleton: snapshot active events, clear, restore."""
    wem = get_world_event_manager()
    saved = list(wem._active)
    wem._active = []
    try:
        yield wem
    finally:
        wem._active = saved


# ══════════════════════════════════════════════════════════════════════════
# Declarative pins — three graded tiers, only consumed effects declared
# ══════════════════════════════════════════════════════════════════════════

def test_three_storm_tiers_declared_and_graded():
    """x1 / x2 / x3 the -1D base on BOTH effects (negative pips: worse = lower)."""
    s = EVENT_DEFS[EventType.SANDSTORM].mechanical_effects
    g = EVENT_DEFS[EventType.GRAVEL_STORM].mechanical_effects
    w = EVENT_DEFS[EventType.SANDWHIRL].mechanical_effects
    assert s["perception_penalty"] == -3 and s["ranged_penalty"] == -3
    assert g["perception_penalty"] == -6 and g["ranged_penalty"] == -6
    assert w["perception_penalty"] == -9 and w["ranged_penalty"] == -9


def test_only_consumed_effects_declared():
    """Anti-phantom: each storm declares EXACTLY the two effects that have a live
    consumer. No flight_penalty / sandwhirl_active orphan (space form deferred)."""
    for et in (EventType.SANDSTORM, EventType.GRAVEL_STORM, EventType.SANDWHIRL):
        keys = set(EVENT_DEFS[et].mechanical_effects.keys())
        assert keys == {"perception_penalty", "ranged_penalty"}, \
            f"{et.value} declares un-consumed effect(s): {keys}"


def test_new_storm_types_in_valid_set():
    assert "gravel_storm" in VALID_EVENT_TYPES
    assert "sandwhirl" in VALID_EVENT_TYPES


def test_sandwhirl_is_short_lived():
    """SoT: 'short-lived but violent' — its max duration is below a slow storm's min."""
    w = EVENT_DEFS[EventType.SANDWHIRL]
    s = EVENT_DEFS[EventType.SANDSTORM]
    assert w.default_duration_max <= s.default_duration_min


def test_director_vocab_has_new_storms():
    """The Director's EVENT_TYPES validation frozenset accepts the new storms
    (readiness; the Director-fire dispatch bug is flagged separately)."""
    src = _src("engine/director.py")
    assert '"gravel_storm"' in src
    assert '"sandwhirl"' in src


def test_new_storm_strings_are_b3_clean():
    """No Galactic-Civil-War residue in the new/re-tuned event strings."""
    banned = ("imperial", "empire", "stormtrooper", "rebel", "tie ", "x-wing", "x wing")
    for et in (EventType.SANDSTORM, EventType.GRAVEL_STORM, EventType.SANDWHIRL):
        ed = EVENT_DEFS[et]
        blob = f"{ed.name} {ed.announce_text} {ed.expire_text}".lower()
        for tok in banned:
            assert tok not in blob, f"{et.value} string carries banned token {tok!r}"


def test_new_storm_strings_are_q1_clean():
    """No canon named figures in the new/re-tuned event strings (Q1 policy)."""
    canon = ("jabba", "anakin", "obi-wan", "obi wan", "yoda", "dooku",
             "grievous", "palpatine", "mace windu", "tatooine's hutt lord")
    for et in (EventType.SANDSTORM, EventType.GRAVEL_STORM, EventType.SANDWHIRL):
        ed = EVENT_DEFS[et]
        blob = f"{ed.name} {ed.announce_text} {ed.expire_text}".lower()
        for tok in canon:
            assert tok not in blob, f"{et.value} string names canon figure {tok!r}"


# ══════════════════════════════════════════════════════════════════════════
# Consumption — perception_penalty on the observation skill family
# ══════════════════════════════════════════════════════════════════════════

def _char():
    # perception 3D + search 2D -> search pool 5D (matches the E2 economy suite).
    return {"attributes": json.dumps({"perception": "3D"}),
            "skills": json.dumps({"search": "2D", "blaster": "2D"})}


def test_gravel_storm_drops_observation_pool(clean_events):
    from engine.skill_checks import perform_skill_check
    base = perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str
    _activate(clean_events, EventType.GRAVEL_STORM)   # perception -6 = -2D
    storm = perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str
    assert base == "5D" and storm == "3D", (base, storm)   # 5D - 2D


def test_sandwhirl_drops_observation_pool_hardest(clean_events):
    from engine.skill_checks import perform_skill_check
    base = perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str
    _activate(clean_events, EventType.SANDWHIRL)       # perception -9 = -3D
    storm = perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str
    assert base == "5D" and storm == "2D", (base, storm)   # 5D - 3D


def test_storms_do_not_touch_non_observation_skill(clean_events):
    from engine.skill_checks import perform_skill_check
    base = perform_skill_check(_char(), "blaster", 10, auto_consume_lead=False).pool_str
    _activate(clean_events, EventType.SANDWHIRL)
    storm = perform_skill_check(_char(), "blaster", 10, auto_consume_lead=False).pool_str
    assert base == storm, f"storm wrongly hit a non-observation skill check ({base} -> {storm})"


def test_no_storm_observation_is_a_noop(clean_events):
    from engine.skill_checks import perform_skill_check
    assert perform_skill_check(_char(), "search", 10,
                               auto_consume_lead=False).pool_str == "5D"


# ══════════════════════════════════════════════════════════════════════════
# Consumption — ranged_penalty raises ranged difficulty (real combat round)
# ══════════════════════════════════════════════════════════════════════════

def _combat_reg():
    from engine.character import SkillRegistry
    reg = SkillRegistry()
    p = os.path.join(_ROOT, "data", "skills.yaml")
    if os.path.exists(p):
        reg.load_file(p)
    return reg


def _fighter(name, char_id, dex="2D", blaster="2D"):
    from engine.character import Character, DicePool
    c = Character(name=name, species_name="Human")
    c.id = char_id
    c.dexterity = DicePool.parse(dex)
    c.strength = DicePool.parse("2D")
    c.add_skill("blaster", DicePool.parse(blaster))
    c.add_skill("dodge", DicePool.parse("1D"))
    return c


def _ranged_difficulty(clean_events, storm=None):
    """Drive ONE real ranged attack at LONG range with a 1D attacker (guaranteed
    miss vs base diff 20). Target ATTACKS (does not dodge) and has no cover, so
    the difficulty is deterministic: base 20 (+ storm). Returns (difficulty, display)."""
    from engine.combat import CombatInstance, CombatAction, ActionType, RangeBand
    combat = CombatInstance(room_id=1, skill_reg=_combat_reg())
    combat.add_combatant(_fighter("Att", 1, dex="1D", blaster="1D"))
    combat.add_combatant(_fighter("Tgt", 2, dex="2D", blaster="1D"))
    combat.roll_initiative()
    combat.set_range(1, 2, RangeBand.LONG)        # base difficulty = 20
    combat.declare_action(1, CombatAction(
        action_type=ActionType.ATTACK, skill="blaster", target_id=2, weapon_damage="4D"))
    combat.declare_action(2, CombatAction(
        action_type=ActionType.ATTACK, skill="blaster", target_id=1, weapon_damage="4D"))
    if storm is not None:
        _activate(clean_events, storm)
    combat.resolve_round()
    res = combat._round_results[1][0]             # attacker's ranged result
    assert res.success is False, "attacker unexpectedly hit; test assumes a guaranteed miss"
    disp = (res.defense_display or "").strip()
    m = re.search(r"=\s*(\d+)\s*$", disp)
    assert m, f"could not parse difficulty from {disp!r}"
    return int(m.group(1)), disp


def test_ranged_no_storm_baseline(clean_events):
    diff, disp = _ranged_difficulty(clean_events, None)
    assert diff == 20, disp                        # LONG base; no dodge/cover/storm
    assert "Storm" not in disp


def test_ranged_sandstorm_plus_one_die(clean_events):
    diff, disp = _ranged_difficulty(clean_events, EventType.SANDSTORM)
    assert diff == 23, disp                         # 20 + 3 (-1D)
    assert "Storm 3" in disp


def test_ranged_gravel_plus_two_dice(clean_events):
    diff, disp = _ranged_difficulty(clean_events, EventType.GRAVEL_STORM)
    assert diff == 26, disp                          # 20 + 6 (-2D)
    assert "Storm 6" in disp


def test_ranged_sandwhirl_plus_three_dice(clean_events):
    diff, disp = _ranged_difficulty(clean_events, EventType.SANDWHIRL)
    assert diff == 29, disp                          # 20 + 9 (-3D)
    assert "Storm 9" in disp


# ══════════════════════════════════════════════════════════════════════════
# Structural pin — the ranged consumer wiring (belt-and-suspenders)
# ══════════════════════════════════════════════════════════════════════════

def test_combat_reads_ranged_penalty_before_difficulty():
    """Mirrors test_bounty_reward_mult_wired_before_payout: the get_effect read
    must exist AND precede the total_difficulty it feeds, in the ranged path."""
    src = _src("engine/combat.py")
    assert 'get_effect("ranged_penalty"' in src, "ranged_penalty read missing"
    i_read = src.index('get_effect("ranged_penalty"')
    i_apply = src.index("total_difficulty += _storm_diff")
    assert i_read < i_apply, "ranged_penalty read does not precede the difficulty bump"
