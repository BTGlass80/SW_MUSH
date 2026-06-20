"""Regression: difficulty.breakdown is a STRING in the live engine.

`engine/combat.py:464` emits the combat_resolution_event `difficulty.breakdown`
as a PRE-FORMATTED STRING (ctx `defense_display`, e.g. "Short(10) = 10"). The
client's `buildDifficultySection` assumed an ARRAY and called `.map()` on it —
a non-empty string passes the `.length > 1` guard, so `.map()` threw a
TypeError, the inspector render aborted, and `ws.onmessage`'s catch dumped the
RAW event JSON into the player's log (Brian's live bounty-chain finding,
2026-06-20).

The pre-existing AC5 fixtures (test_combat_inspector_d_prime_client.py) only
ever used the ARRAY shape, so the green suite never exercised the real producer
shape. These lock in the string-tolerant render AND keep the array path working.
"""
from __future__ import annotations

import json

from tests.spa.m3_combat_inspector_harness import run_with_d_prime_block


def _payload(breakdown) -> dict:
    """The live bounty-chain event shape, parameterized on difficulty.breakdown."""
    return {
        "type": "combat_resolution_event",
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "strbk-001",
        "round_num": 1,
        "combat_id": None,
        "actor": {"id": 2, "name": "Tundra", "kind": "pc",
                  "is_force_point_active": False},
        "target": {"id": 160, "name": "Tarko Vinn", "kind": "pc"},
        "action": {"skill": "blaster", "weapon_name": "",
                   "range_band": "Short", "stun_mode": True,
                   "is_opposed": False},
        "attacker_pool": {"pool_text": "5D+2", "total": 23, "pool_pips": 2,
                          "dice": [{"value": 6, "source": "skill"}]},
        "defender_pool": None,
        "difficulty": {"number": 10, "label": "Short", "breakdown": breakdown},
        "damage_pool": {"pool_text": "4D", "total": 18, "pool_pips": 0,
                        "dice": [{"value": 3, "source": "weapon"}]},
        "soak": {"total": 10, "components": [
            {"source": "strength", "label": "Strength",
             "value": 10, "rolls": [10]}]},
        "hit": True, "margin": 13, "damage_margin": 8,
        "wound_outcome": {"hit": True, "outcome_type": "stun_unconscious",
                          "display_name": "Stunned — Unconscious! (19 min)",
                          "stun_unconscious": True},
    }


_SETUP = r"""
    var ev = { payload: PAYLOAD_HERE, role: 'self', expanded: true };
    var threw = false, errMsg = '', row = null;
    try {
      row = window.buildCombatResultRow(ev);
    } catch (e) {
      threw = true; errMsg = String((e && e.message) || e);
    }
    var bk = row && row.querySelector('.cri-diff-breakdown');
    window.__d_prime_result = {
      threw: threw,
      errMsg: errMsg,
      breakdownText: bk ? (bk.textContent || '').trim() : null,
    };
"""


def _run(breakdown):
    return run_with_d_prime_block(
        _SETUP.replace("PAYLOAD_HERE", json.dumps(_payload(breakdown)))
    )


def test_string_breakdown_does_not_throw_and_renders_verbatim():
    # The real engine shape. Before the fix this threw and the raw JSON leaked.
    out = _run("Short(10) = 10")
    assert out["threw"] is False, (
        "string difficulty.breakdown must not throw (was: %s)" % out["errMsg"]
    )
    assert out["breakdownText"] == "Short(10) = 10", (
        "the pre-formatted breakdown string should render verbatim; got %r"
        % out["breakdownText"]
    )


def test_array_breakdown_still_renders_joined_modifiers():
    # No regression to the structured-array path the original code targeted.
    out = _run([{"name": "range", "mod": 5}, {"name": "cover", "mod": 3}])
    assert out["threw"] is False, out["errMsg"]
    assert out["breakdownText"] == "range +5 · cover +3", (
        "array breakdown should join {name mod} pairs; got %r" % out["breakdownText"]
    )


def test_empty_string_breakdown_renders_no_breakdown_node():
    out = _run("")
    assert out["threw"] is False, out["errMsg"]
    assert out["breakdownText"] is None, (
        "an empty breakdown string should not produce a breakdown node"
    )
