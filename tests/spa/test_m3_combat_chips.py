"""
test_m3_combat_chips.py — Webify Drop UI-3 (combat condition chips) contract.

Loads static/spa/m3_combat_inspector.js under jsdom and exercises
M3CombatInspector.buildConditionChips() against the per-combatant condition
fields the engine now puts on the combat_state push (engine/combat.py
to_hud_dict): poison_stacks[{source,damage,onset,ticks_left}] +
restraint{grappler_id,kind,hold_damage,source}|null.

Pins:
  · biting poison (onset 0) → pulsing chip, worst-stack damage·ticks
  · pre-onset poison        → non-pulsing chip, soonest onset countdown
  · restraint kinds         → GRAPPLED / CONSTRICTED / CHOKED + hold damage
  · the held PLAYER gets the can't-flee note; others don't
  · DISPLAY-ONLY            → the rail stages NO command (no <button>) —
                              ground break-free is automatic at round end
  · no conditions           → returns null (zero DOM in ordinary combat)

Plus static guards on the producer (to_hud_dict), the client wiring, the CSS,
and the absence of a ground breakfree button.
"""
from __future__ import annotations

import re
from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INSPECTOR = str(REPO_ROOT / "static" / "spa" / "m3_combat_inspector.js")


_DRIVER = """
function summarize(rail) {
  if (rail === null) return { isNull: true };
  var poison = rail.querySelector('.cmb-chip.poison');
  var restraint = rail.querySelector('.cmb-chip.restraint');
  var note = rail.querySelector('.combatant-restraint-note');
  return {
    isNull: false,
    railClass: rail.getAttribute('class'),
    buttons: rail.querySelectorAll('button').length,
    poison: poison ? {
      text: poison.textContent,
      biting: poison.classList.contains('biting'),
    } : null,
    restraint: restraint ? { text: restraint.textContent } : null,
    note: note ? note.textContent : null,
  };
}

var CI = window.M3CombatInspector;

// A: biting poison (onset 0), single stack.
var a = CI.buildConditionChips({
  poison_stacks: [{ source: 'acklay', damage: '4D', onset: 0, ticks_left: 3 }],
  restraint: null,
}, false);

// B: pre-onset poison (not yet biting).
var b = CI.buildConditionChips({
  poison_stacks: [{ source: 'kouhun', damage: '2D', onset: 2, ticks_left: 4 }],
  restraint: null,
}, false);

// C: choke restraint, this is YOU (note expected).
var c = CI.buildConditionChips({
  poison_stacks: [],
  restraint: { grappler_id: 9, kind: 'choke', hold_damage: 'STR+2D', source: 'dianoga' },
}, true);

// D: grapple restraint, NOT you (no note).
var d = CI.buildConditionChips({
  poison_stacks: [],
  restraint: { grappler_id: 5, kind: 'grapple', hold_damage: '', source: 'gundark' },
}, false);

// E: no conditions → null.
var e = CI.buildConditionChips({ poison_stacks: [], restraint: null }, false);

// F: multi-stack biting — worst (most ticks) wins the detail.
var f = CI.buildConditionChips({
  poison_stacks: [
    { source: 'x', damage: '2D', onset: 0, ticks_left: 2 },
    { source: 'y', damage: '3D', onset: 0, ticks_left: 5 },
  ],
  restraint: null,
}, false);

result = {
  a: summarize(a), b: summarize(b), c: summarize(c),
  d: summarize(d), e: summarize(e), f: summarize(f),
};
"""


def test_condition_chip_render_contract():
    out = run_with_dom([INSPECTOR], _DRIVER)

    # A — biting poison: pulsing chip, ×1, worst-stack damage·ticks.
    assert out["a"]["isNull"] is False
    assert out["a"]["poison"]["biting"] is True
    assert "POISON" in out["a"]["poison"]["text"]
    assert "\u00D71" in out["a"]["poison"]["text"]      # ×1
    assert "4D\u00B73t" in out["a"]["poison"]["text"]   # 4D·3t
    assert out["a"]["restraint"] is None
    assert out["a"]["buttons"] == 0                      # display-only

    # B — pre-onset poison: NOT pulsing, shows soonest onset.
    assert out["b"]["poison"]["biting"] is False
    assert "onset 2" in out["b"]["poison"]["text"]

    # C — choke + you: CHOKED + hold damage + the can't-flee note; no button.
    assert "CHOKED" in out["c"]["restraint"]["text"]
    assert "STR+2D" in out["c"]["restraint"]["text"]
    assert out["c"]["note"] and "can't flee" in out["c"]["note"]
    assert out["c"]["buttons"] == 0                      # NO breakfree button

    # D — grapple, not you: GRAPPLED, no hold-damage suffix, no note.
    assert "GRAPPLED" in out["d"]["restraint"]["text"]
    assert out["d"]["note"] is None
    assert out["d"]["buttons"] == 0

    # E — nothing: null (zero DOM in ordinary fights).
    assert out["e"]["isNull"] is True

    # F — multi-stack biting: worst (5 ticks / 3D) wins.
    assert "\u00D72" in out["f"]["poison"]["text"]       # ×2
    assert "3D\u00B75t" in out["f"]["poison"]["text"]    # 3D·5t


# ── static guards (no node needed) ───────────────────────────────────

def test_producer_exposes_conditions_on_combat_push():
    src = (REPO_ROOT / "engine" / "combat.py").read_text(encoding="utf-8")
    # to_hud_dict normalizes the Lane-A fields onto each combatant.
    assert "def _conditions(cb)" in src, "condition normalizer missing from to_hud_dict"
    assert "**_conditions(c)" in src, "conditions not spread onto combatant dicts"
    # the engine→push key remap (onset_left→onset, rounds_left→ticks_left)
    assert '"onset": int(s.get("onset_left"' in src
    assert '"ticks_left": int(s.get("rounds_left"' in src
    # both loops (initiative + new joiners) must carry it
    assert src.count("**_conditions(c)") >= 2


def test_chips_wired_into_client_and_styled():
    html = (REPO_ROOT / "static" / "client.html").read_text(encoding="utf-8")
    for needle in (
        "M3CombatInspector.buildConditionChips(c, isYou)",
        ".combatant-chips",
        ".cmb-chip.poison",
        ".cmb-chip.restraint",
        "@keyframes m3-chip-pulse",
        ".combatant-restraint-note",
    ):
        assert needle in html, f"combat-chip wiring/CSS missing: {needle!r}"


def test_no_ground_breakfree_button_is_staged():
    """Q5: ground break-free is automatic at round end — the restraint chip
    must stage no command. Guard the buildConditionChips BODY specifically
    (the file's comment legitimately *mentions* breakfree to document the
    decision; the runtime test above already proves zero <button>s)."""
    inspector = (REPO_ROOT / "static" / "spa" / "m3_combat_inspector.js").read_text(encoding="utf-8")
    start = inspector.index("function buildConditionChips(")
    depth, started, end = 0, False, None
    for k in range(start, len(inspector)):
        ch = inspector[k]
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                end = k + 1
                break
    assert end, "could not brace-match buildConditionChips"
    body = inspector[start:end]
    for forbidden in ("sendCmd", "stageCommand", "addEventListener", "onclick",
                      "createElement('button')", 'createElement("button")', "breakfree"):
        assert forbidden not in body, \
            f"condition chips must be display-only — {forbidden!r} found in buildConditionChips"
    # The module still documents the display-only decision somewhere.
    assert "display-only" in inspector.lower()
