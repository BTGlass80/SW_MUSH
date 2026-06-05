# -*- coding: utf-8 -*-
"""
tests/test_e2_dormant_effects.py — E2 (2026-06-04).

Wires three previously-dormant *passive* world-event mechanical effects to their
existing faucets (the proven get_effect() pattern), plus two bookkeeping fixes.
These are CONSUMPTION tests (they activate a real event and assert the metered
mechanic changes) — the kind that would have caught the patrol_spawn_mult shadow
bug this drop fixed — backed by structural source pins.

Wired here:
  * bounty_reward_mult   (BOUNTY_SURGE)  -> bounty payout faucet
  * pirate_spawn_mult    (PIRATE_SURGE)  -> _pick_archetype spawn weighting
  * patrol_spawn_mult    (SECURITY_CRACKDOWN) -> same (REPAIRED: was shadowed/inert)
  * perception_penalty   (SANDSTORM)     -> perform_skill_check (observation skills)
Bookkeeping:
  * director EVENT_TYPES vocab gains intelligence_thaw + spice_demand
  * HUTT_AUCTION / zone-display "Jabba" -> institutional Hutt reference (Q1)

Deferred (NOT wired — they enable NEW player interactions and need a design pass):
  contraband_scan, rare_vendor, hutt_auction/criminal_rep_gate, krayt_bounty,
  brawl_active, distress_active.  See HANDOFF_e2_*.
"""
from __future__ import annotations
import os
import time
import json
import collections
import pytest

from engine.world_events import (
    get_world_event_manager, EventType, EVENT_DEFS, _ZONE_DISPLAY_NAMES,
    ActiveEvent,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _src(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _activate(wem, etype):
    """Inject an active event DIRECTLY into the manager, bypassing
    activate_event()'s global activation cooldown (_last_event_time/COOLDOWN_SECS)
    and same-type repeat cooldown. These are *consumption* tests (does the metered
    mechanic read the effect?), not activation-policy tests, and must not depend on
    test ordering. Global zone scope so the global get_effect() always resolves it."""
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


# ── pirate_spawn_mult + patrol_spawn_mult: spawn weighting (consumption) ─────

def test_only_one_pick_archetype_definition():
    """Regression guard for the shadow bug: a duplicate def silently disabled
    the world-event-aware version (patrol_spawn_mult was inert)."""
    src = _src("engine/npc_space_traffic.py")
    assert src.count("def _pick_archetype(") == 1, "duplicate _pick_archetype reintroduced"


def test_pirate_surge_raises_pirate_spawn_share(clean_events):
    import random
    import engine.npc_space_traffic as nt
    random.seed(20260604)

    def share(n=4000):
        c = collections.Counter(nt._pick_archetype().value for _ in range(n))
        return c.get("pirate", 0) / sum(c.values())

    base = share()
    _activate(clean_events, EventType.PIRATE_SURGE)   # pirate_spawn_mult 3.0
    surged = share()
    assert surged > base * 1.5, f"pirate share did not rise ({base:.3f} -> {surged:.3f})"


def test_security_crackdown_raises_patrol_spawn_share(clean_events):
    """patrol_spawn_mult was the SHADOWED (inert) effect — prove it's live now."""
    import random
    import engine.npc_space_traffic as nt
    random.seed(99)

    def share(n=4000):
        c = collections.Counter(nt._pick_archetype().value for _ in range(n))
        return c.get("patrol", 0) / sum(c.values())

    base = share()
    _activate(clean_events, EventType.SECURITY_CRACKDOWN)  # patrol_spawn_mult 2.0
    surged = share()
    assert surged > base * 1.3, f"patrol share did not rise ({base:.3f} -> {surged:.3f})"


# ── perception_penalty: observation skill checks (consumption) ───────────────

def _char():
    return {"attributes": json.dumps({"perception": "3D"}),
            "skills": json.dumps({"search": "2D", "blaster": "2D"})}

def test_sandstorm_penalises_observation_pool(clean_events):
    from engine.skill_checks import perform_skill_check
    base = perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str
    _activate(clean_events, EventType.SANDSTORM)   # perception_penalty -3
    storm = perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str
    assert base != storm, f"sandstorm did not change the search pool ({base} -> {storm})"
    # -3 pips = exactly -1D off the observation pool
    assert base == "5D" and storm == "4D", (base, storm)

def test_sandstorm_does_not_touch_non_observation_skills(clean_events):
    from engine.skill_checks import perform_skill_check
    base = perform_skill_check(_char(), "blaster", 10, auto_consume_lead=False).pool_str
    _activate(clean_events, EventType.SANDSTORM)
    storm = perform_skill_check(_char(), "blaster", 10, auto_consume_lead=False).pool_str
    assert base == storm, f"sandstorm wrongly affected a non-observation skill ({base} -> {storm})"

def test_no_sandstorm_is_a_noop(clean_events):
    from engine.skill_checks import perform_skill_check
    # no active event -> get_effect default 0 -> pool unchanged from the raw skill
    assert perform_skill_check(_char(), "search", 10, auto_consume_lead=False).pool_str == "5D"


# ── bounty_reward_mult: structural pin at the payout faucet ───────────────────

def test_bounty_reward_mult_wired_before_payout():
    src = _src("parser/bounty_commands.py")
    assert 'get_effect("bounty_reward_mult"' in src, "bounty_reward_mult read missing"
    # the read must precede the metered `bounty` adjust_credits call
    i_read = src.index('get_effect("bounty_reward_mult"')
    i_pay = src.index('adjust_credits(char["id"], reward, "bounty")')
    assert i_read < i_pay, "bounty_reward_mult applied after the payout, not before"


# ── director vocab gap (TD.DIRECTOR_EVENT_VOCAB_GAP) ──────────────────────────

def test_director_event_vocab_includes_newest_cw_events():
    src = _src("engine/director.py")
    assert '"intelligence_thaw"' in src
    assert '"spice_demand"' in src


# ── Q1: no 'Jabba' named-figure in live event strings ────────────────────────

def test_no_jabba_named_figure_in_event_strings():
    offenders = {}
    for et, ed in EVENT_DEFS.items():
        for field in ("name", "announce_text", "expire_text"):
            if "jabba" in (getattr(ed, field, "") or "").lower():
                offenders[f"{et.value}.{field}"] = getattr(ed, field)
    for k, v in _ZONE_DISPLAY_NAMES.items():
        if "jabba" in (v or "").lower():
            offenders[f"_ZONE_DISPLAY_NAMES[{k}]"] = v
    assert not offenders, f"'Jabba' named-figure still in player-facing strings: {offenders}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
