"""
test_combat_inspector_d_prime_client.py — D' client-side regression lock.

Drop 4.3 (Tier 1 #4) · May 26 2026 — landed the original 29-test suite,
using a marker-extract harness that sliced the D' rendering block out of
static/client.html.

Drop 4.4 (Tier 1 #4) · May 27 2026 — D' inspector extracted to a proper
SPA module (static/spa/m3_combat_inspector.js). The 29 tests below
continue to lock the same 14 D' acceptance criteria, now exercising the
module directly via m3_combat_inspector_harness (which loads the module
into jsdom the same way every other m3_* module is tested). The
extraction-marker test (test_extraction_markers_present_and_well_ordered)
was retargeted at the module's IIFE + exports contract.

Pre-flight discovered Drop D' (combat_resolution_event end-to-end) is
already DELIVERED at HEAD — engine factory (engine/combat_events.py,
885 LOC), engine wiring (engine/combat.py:_build_resolution_event),
parser broadcast (parser/combat_commands.py:271-284), client handler
(static/spa/m3_combat_inspector.js:handleCombatResolutionEvent, post-4.4),
full inspector renderer (m3_combat_inspector.js:buildCombatResultRow +
14 helpers), CSS contract (still in static/client.html), dedup, role-
aware expand defaults. 76 engine-side tests pass in
tests/test_field_kit_drop_d_prime.py.

What was MISSING pre-4.3: client-side regression coverage. The 15 D'
rendering functions were exercised by the browser at runtime but not
pinned by any test. A CSS class rename, a refactor that drops the
window export, a schema bump, or a sneaky type bug in buildDieChip
would all ship silently.

Drops 4.3 and 4.4 fill that gap. Each test exercises ONE of D''s 14
acceptance criteria (combat_mechanics_display_design_v1.1.md §12) at
the client layer. The engine ACs (AC1-AC3) are already covered by
test_field_kit_drop_d_prime.py.

Approach:
  · Static parsing checks (CSS class presence, function references,
    schema_version guard) read static/client.html and/or the SPA
    module and assert on byte-level contracts.
  · Runtime checks load m3_combat_inspector.js into jsdom (via
    m3_combat_inspector_harness) and call buildCombatResultRow /
    buildDieChip with fixture payloads, inspecting the returned DOM.

This pattern mirrors the 4.1-4.2 discipline (jsdom-exercised pipeline
tests + static contract checks). It does NOT introduce new behavior —
it only locks the existing D' delivery against regression.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .m3_combat_inspector_harness import (
    run_with_d_prime_block,
    extract_d_prime_block,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


# ─── Fixture payloads — the 5 archetypes from design §9 ──────────────
# These mirror the engine-side archetype tests
# (tests/test_field_kit_drop_d_prime.py::TestArchetype{1..5}) at the
# wire-payload level so the client renders against representative input.

def _arche_ranged_hit_with_explosion() -> dict:
    """Archetype 1: ranged hit with Wild Die explosion."""
    return {
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "arche1-001",
        "timestamp_ms": 1716724800000,
        "round_num": 3,
        "combat_id": 17,
        "actor":  {"id": 100, "name": "Tey Voss", "kind": "pc",
                   "is_force_point_active": False},
        "target": {"id": 200, "name": "B1 #1", "kind": "npc"},
        "action": {"skill": "blaster", "weapon_name": "Heavy Blaster",
                   "range_band": "medium", "stun_mode": False,
                   "is_opposed": False},
        "attacker_pool": {
            "total": 22, "pool_pips": 2,
            "dice": [
                {"value": 5, "source": "skill"},
                {"value": 4, "source": "skill"},
                {"value": 3, "source": "skill"},
                {"value": 7, "source": "weapon"},
                {"value": 11, "source": "skill", "is_wild": True,
                 "exploded": True, "explosion_chain": [6, 5]},
            ],
        },
        "defender_pool": None,
        "difficulty": {"number": 13, "label": "Difficult",
                       "breakdown": [{"name": "range", "mod": 5},
                                     {"name": "cover", "mod": 3}]},
        "damage_pool": {
            "total": 14, "pool_pips": 0,
            "dice": [
                {"value": 4, "source": "skill"},
                {"value": 3, "source": "skill"},
                {"value": 7, "source": "weapon"},
            ],
        },
        "soak": {
            "total": 8,
            "components": [
                {"source": "strength", "label": "Strength",
                 "total": 6, "rolls": [6]},
                {"source": "armor", "label": "Armor",
                 "total": 2, "rolls": []},
            ],
        },
        "hit": True, "margin": 9, "damage_margin": 6,
        "wound_outcome": {"hit": True, "display_name": "Wounded",
                          "outcome_type": "wounded",
                          "wound_level_after": "WOUNDED"},
    }


def _arche_ranged_miss() -> dict:
    """Archetype 2: ranged miss — no damage / soak / wound."""
    return {
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "arche2-001",
        "timestamp_ms": 1716724800000,
        "round_num": 3,
        "combat_id": 17,
        "actor":  {"id": 200, "name": "B1 #2", "kind": "npc",
                   "is_force_point_active": False},
        "target": {"id": 100, "name": "Tey Voss", "kind": "pc"},
        "action": {"skill": "blaster", "weapon_name": "E-5 Blaster",
                   "range_band": "medium", "stun_mode": False,
                   "is_opposed": False},
        "attacker_pool": {
            "total": 11, "pool_pips": 0,
            "dice": [{"value": 4, "source": "skill"},
                     {"value": 3, "source": "skill"},
                     {"value": 4, "source": "skill",
                      "is_wild": True}],
        },
        "defender_pool": None,
        "difficulty": {"number": 14, "label": "Difficult",
                       "breakdown": [{"name": "range", "mod": 5},
                                     {"name": "cover", "mod": 4}]},
        "damage_pool": None,
        "soak": None,
        "hit": False, "margin": -3,
        "wound_outcome": {"hit": False, "outcome_type": "miss"},
    }


def _arche_melee_mishap() -> dict:
    """Archetype 3: melee mishap (Wild Die complication, dropped die)."""
    return {
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "arche3-001",
        "timestamp_ms": 1716724800000,
        "round_num": 4,
        "combat_id": 17,
        "actor":  {"id": 100, "name": "Marek Tan", "kind": "pc",
                   "is_force_point_active": False},
        "target": {"id": 201, "name": "Pirate", "kind": "npc"},
        "action": {"skill": "melee", "weapon_name": "Vibroknife",
                   "range_band": "close", "stun_mode": False,
                   "is_opposed": True},
        "attacker_pool": {
            "total": 7, "pool_pips": 0, "complication": True,
            "removed_die_value": 5,
            "dice": [
                {"value": 4, "source": "skill"},
                {"value": 3, "source": "skill"},
                {"value": 5, "source": "skill", "dropped": True},
                {"value": 0, "source": "skill", "is_wild": True},
            ],
        },
        "defender_pool": {
            "total": 12, "pool_pips": 0,
            "dice": [{"value": 4, "source": "skill"},
                     {"value": 5, "source": "skill"},
                     {"value": 3, "source": "skill", "is_wild": True}],
        },
        "difficulty": None,
        "damage_pool": None,
        "soak": None,
        "hit": False, "margin": -5,
        "wound_outcome": {"hit": False, "outcome_type": "miss"},
    }


def _arche_space_force_point() -> dict:
    """Archetype 4: space combat with Force Point doubling."""
    return {
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "arche4-001",
        "timestamp_ms": 1716724800000,
        "round_num": 2,
        "combat_id": 18,
        "actor":  {"id": 100, "name": "Tey Voss", "kind": "pc",
                   "is_force_point_active": True},
        "target": {"id": 300, "name": "TIE Fighter",
                   "kind": "object"},
        "action": {"skill": "starship gunnery",
                   "weapon_name": "Laser Cannon",
                   "range_band": "short", "stun_mode": False,
                   "is_opposed": False},
        "attacker_pool": {
            "total": 24, "pool_pips": 1,
            "dice": [
                {"value": 4, "source": "skill"},
                {"value": 5, "source": "skill"},
                {"value": 3, "source": "skill"},
                {"value": 4, "source": "fp_double"},
                {"value": 5, "source": "fp_double"},
                {"value": 3, "source": "fp_double",
                 "is_wild": True},
            ],
        },
        "defender_pool": None,
        "difficulty": {"number": 11, "label": "Moderate",
                       "breakdown": []},
        "damage_pool": {
            "total": 18, "pool_pips": 0,
            "dice": [{"value": 6, "source": "weapon"},
                     {"value": 4, "source": "weapon"},
                     {"value": 5, "source": "weapon"},
                     {"value": 3, "source": "weapon"}],
        },
        "soak": {
            "total": 12,
            "components": [
                {"source": "armor", "label": "Hull",
                 "total": 12, "rolls": []},
            ],
        },
        "hit": True, "margin": 13, "damage_margin": 6,
        "wound_outcome": {"hit": True, "display_name": "Wounded",
                          "outcome_type": "wounded"},
    }


def _arche_melee_opposed() -> dict:
    """Archetype 5: melee opposed (no static difficulty; defender pool)."""
    return {
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "arche5-001",
        "timestamp_ms": 1716724800000,
        "round_num": 1,
        "combat_id": 17,
        "actor":  {"id": 100, "name": "Marek Tan", "kind": "pc",
                   "is_force_point_active": False},
        "target": {"id": 201, "name": "Thug", "kind": "npc"},
        "action": {"skill": "brawling", "weapon_name": None,
                   "range_band": "close", "stun_mode": False,
                   "is_opposed": True},
        "attacker_pool": {
            "total": 18, "pool_pips": 0,
            "dice": [{"value": 4, "source": "skill"},
                     {"value": 5, "source": "skill"},
                     {"value": 4, "source": "skill"},
                     {"value": 5, "source": "skill",
                      "is_wild": True}],
        },
        "defender_pool": {
            "total": 11, "pool_pips": 0,
            "dice": [{"value": 4, "source": "skill"},
                     {"value": 3, "source": "skill"},
                     {"value": 4, "source": "skill",
                      "is_wild": True}],
        },
        "difficulty": None,
        "damage_pool": {
            "total": 10, "pool_pips": 0,
            "dice": [{"value": 3, "source": "skill"},
                     {"value": 4, "source": "skill"},
                     {"value": 3, "source": "skill"}],
        },
        "soak": {
            "total": 6,
            "components": [{"source": "strength", "label": "Strength",
                            "total": 6, "rolls": [6]}],
        },
        "hit": True, "margin": 7, "damage_margin": 4,
        "wound_outcome": {"hit": True, "display_name": "Wounded",
                          "outcome_type": "wounded"},
    }


def _arche_stun_unconscious() -> dict:
    """Stun-mode KO routing (AC8)."""
    return {
        "msg_type": "combat_resolution_event",
        "schema_version": 1,
        "event_id": "arche-stun-001",
        "timestamp_ms": 1716724800000,
        "round_num": 5,
        "combat_id": 17,
        "actor":  {"id": 100, "name": "Tey Voss", "kind": "pc",
                   "is_force_point_active": False},
        "target": {"id": 201, "name": "Cantina Goon", "kind": "npc"},
        "action": {"skill": "blaster", "weapon_name": "Blaster Pistol",
                   "range_band": "short", "stun_mode": True,
                   "is_opposed": False},
        "attacker_pool": {
            "total": 19, "pool_pips": 0,
            "dice": [{"value": 5, "source": "skill"},
                     {"value": 4, "source": "skill"},
                     {"value": 5, "source": "skill"},
                     {"value": 5, "source": "skill",
                      "is_wild": True}],
        },
        "defender_pool": None,
        "difficulty": {"number": 10, "label": "Moderate",
                       "breakdown": []},
        "damage_pool": {
            "total": 16, "pool_pips": 0,
            "dice": [{"value": 5, "source": "weapon"},
                     {"value": 5, "source": "weapon"},
                     {"value": 6, "source": "weapon"}],
        },
        "soak": {"total": 4, "components": [
            {"source": "strength", "label": "Strength",
             "total": 4, "rolls": [4]}]},
        "hit": True, "margin": 9, "damage_margin": 12,
        "wound_outcome": {
            "hit": True, "display_name": "Stunned — Unconscious!",
            "outcome_type": "stun_unconscious",
            "stun_unconscious": True,
            "stun_duration_dice": None,
            "stun_duration_unit": None,
        },
    }


# ════════════════════════════════════════════════════════════════════
# AC4 — WebSocket dispatch site
# ════════════════════════════════════════════════════════════════════

def test_ac4_websocket_dispatch_site_present():
    """The WS router must have a case for combat_resolution_event that
    routes to handleCombatResolutionEvent. This is AC4 from the design
    doc §12 — the entry point of the entire client-side D' pipeline."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    assert re.search(
        r"case\s+['\"]combat_resolution_event['\"]\s*:\s*handleCombatResolutionEvent",
        text,
    ), (
        "WebSocket router missing case for combat_resolution_event → "
        "handleCombatResolutionEvent. The entire D' inspector pipeline "
        "is unreachable without this."
    )


# ════════════════════════════════════════════════════════════════════
# AC5 — Inspector renders for all 5 archetypes
# ════════════════════════════════════════════════════════════════════

def _build_row_setup(payload: dict, role: str = "self",
                     expanded: bool = True) -> str:
    """Helper: setup_js that builds a row and exports its key structure
    to window.__d_prime_result."""
    return r"""
        var ev = { payload: PAYLOAD_HERE, role: ROLE_HERE, expanded: EXPANDED_HERE };
        var row = window.buildCombatResultRow(ev);
        // Extract structural facts (not raw DOM — has to JSON-serialize)
        function classesOf(el) {
          return el ? Array.prototype.slice.call(el.classList) : [];
        }
        function tagsOf(parent, selector) {
          var nodes = parent.querySelectorAll(selector);
          return Array.prototype.map.call(nodes, function(n) {
            return {
              tag: n.tagName,
              cls: classesOf(n).join(' '),
              text: (n.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80)
            };
          });
        }
        window.__d_prime_result = {
          rowTag:        row.tagName,
          rowClasses:    classesOf(row),
          childCount:    row.children.length,
          summaryClass:  classesOf(row.querySelector('.cri-summary')),
          mechlineText:  (row.querySelector('.cri-mechline') || {}).textContent || '',
          bodyExists:    !!row.querySelector('.cri-body'),
          sectionCount:  row.querySelectorAll('.cri-section').length,
          sectionHeads:  tagsOf(row, '.cri-section-head'),
          dieChips:      tagsOf(row, '.cri-die'),
          dieSources:    Array.prototype.map.call(
                            row.querySelectorAll('.cri-die'),
                            function(d) { return d.getAttribute('data-source'); }
                          ),
          dieValues:     Array.prototype.map.call(
                            row.querySelectorAll('.cri-die'),
                            function(d) { return (d.textContent || '').trim(); }
                          ),
          legendExists:  !!row.querySelector('.cri-legend'),
          outcomeCls:    classesOf(row.querySelector('.cri-outcome')),
        };
    """.replace("PAYLOAD_HERE", json.dumps(payload)) \
       .replace("ROLE_HERE", json.dumps(role)) \
       .replace("EXPANDED_HERE", "true" if expanded else "false")


def test_ac5_archetype_1_ranged_hit_explosion_renders():
    out = run_with_d_prime_block(_build_row_setup(_arche_ranged_hit_with_explosion()))
    assert out["rowTag"] == "DIV"
    assert "row-combat-result" in out["rowClasses"]
    # Summary + mechline + body = 3 children
    assert out["childCount"] == 3, f"Expected 3 row children, got {out['childCount']}"
    # Inspector body present; sections include attacker + difficulty + damage + soak + wound
    assert out["bodyExists"]
    # Section heads include ATTACKER + DIFFICULTY + DAMAGE + SOAK + WOUND
    heads = " | ".join(h["text"] for h in out["sectionHeads"])
    for required in ["ATTACKER", "DIFFICULTY", "DAMAGE", "SOAK", "OUTCOME"]:
        assert required in heads, (
            f"Required section head '{required}' missing. "
            f"Found: {heads}"
        )
    # 5 attacker dice + 3 damage dice = 8 die chips
    assert len(out["dieChips"]) == 8, (
        f"Expected 8 dice rendered, got {len(out['dieChips'])}: "
        f"{out['dieChips']}"
    )


def test_ac5_archetype_2_ranged_miss_renders_no_damage_or_soak():
    out = run_with_d_prime_block(_build_row_setup(_arche_ranged_miss()))
    heads = [h["text"] for h in out["sectionHeads"]]
    # ATTACKER + DIFFICULTY + WOUND should be present
    assert any("ATTACKER" in h for h in heads)
    assert any("DIFFICULTY" in h for h in heads)
    # DAMAGE and SOAK should NOT be present (hit=False short-circuits)
    assert not any("DAMAGE" in h for h in heads), (
        "Miss event should not render DAMAGE section. "
        f"Heads: {heads}"
    )
    assert not any("SOAK" in h for h in heads), (
        "Miss event should not render SOAK section. "
        f"Heads: {heads}"
    )


def test_ac5_archetype_3_melee_mishap_renders_complication():
    out = run_with_d_prime_block(_build_row_setup(_arche_melee_mishap()))
    # Mishap means is_opposed=True so DEFENDER section appears, not DIFFICULTY
    heads = " ".join(h["text"] for h in out["sectionHeads"])
    assert "DEFENDER" in heads
    assert "DIFFICULTY" not in heads, (
        "Opposed roll should show DEFENDER, not DIFFICULTY. "
        f"Heads: {heads}"
    )
    # Wild die shows as 1! when complication (value=0)
    # The dropped die has class is-dropped — check via classes
    chip_classes = [chip["cls"] for chip in out["dieChips"]]
    has_dropped = any("is-dropped" in c for c in chip_classes)
    assert has_dropped, (
        f"Mishap fixture should produce at least one is-dropped die. "
        f"Chip classes: {chip_classes}"
    )


def test_ac5_archetype_4_space_force_point_renders_fp_dice():
    out = run_with_d_prime_block(_build_row_setup(_arche_space_force_point()))
    # FP-doubled dice tagged with source='fp_double'
    sources = out["dieSources"]
    assert "fp_double" in sources, (
        f"FP archetype should produce dice with source='fp_double'. "
        f"Got sources: {sources}"
    )


def test_ac5_archetype_5_melee_opposed_renders_both_pools():
    out = run_with_d_prime_block(_build_row_setup(_arche_melee_opposed()))
    heads = " ".join(h["text"] for h in out["sectionHeads"])
    # Both ATTACKER and DEFENDER sections present; no DIFFICULTY
    assert "ATTACKER" in heads
    assert "DEFENDER" in heads
    assert "DIFFICULTY" not in heads


# ════════════════════════════════════════════════════════════════════
# AC6 — Per-die source visual grouping
# ════════════════════════════════════════════════════════════════════

def test_ac6_per_die_source_grouping_via_data_source_attr():
    """Each die chip must carry data-source so the CSS can render
    distinct styling per source. The 4 source values are skill, weapon,
    modifier, fp_double per design §4 schema."""
    out = run_with_d_prime_block(_build_row_setup(_arche_ranged_hit_with_explosion()))
    # All chips must have a data-source (not null, not empty)
    for src in out["dieSources"]:
        assert src and src in ("skill", "weapon", "modifier", "fp_double"), (
            f"Invalid die source: {src!r}. "
            "Must be skill, weapon, modifier, or fp_double."
        )


def test_ac6_css_assigns_distinct_colors_per_source():
    """The CSS must define distinct colors for each of the 4 source
    values. Without these rules, the per-die source grouping (AC6)
    becomes invisible."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    for source in ("skill", "weapon", "modifier", "fp_double"):
        assert re.search(
            r'\.cri-die\[data-source="' + source + r'"\]',
            text,
        ), (
            f"CSS rule for .cri-die[data-source=\"{source}\"] missing. "
            "AC6 (per-die source visual grouping) requires distinct "
            "styling per source."
        )


# ════════════════════════════════════════════════════════════════════
# AC7 — Wild Die explosion chain rendering
# ════════════════════════════════════════════════════════════════════

def test_ac7_wild_die_explosion_chain_renders_with_arrow():
    """AC7: explosion chain renders as `6→5=11` (the arrow format).
    Our fixture #1 has a wild die with explosion_chain=[6,5] and
    value=11. Verify the chip text contains an arrow + the value."""
    out = run_with_d_prime_block(_build_row_setup(_arche_ranged_hit_with_explosion()))
    # Find the exploded chip — it's the only one with is-exploded-chain class
    exploded_chips = [
        c for c in out["dieChips"]
        if "is-exploded-chain" in c["cls"]
    ]
    assert len(exploded_chips) == 1, (
        f"Expected exactly 1 exploded-chain chip, got {len(exploded_chips)}. "
        f"All chips: {out['dieChips']}"
    )
    chip_text = exploded_chips[0]["text"]
    # Format per buildDieChip: explosion_chain.join('→') + '=' + value
    assert "→" in chip_text, (
        f"Exploded chip should contain arrow. Got: {chip_text!r}"
    )
    assert "11" in chip_text or "=" in chip_text, (
        f"Exploded chip should show summed value. Got: {chip_text!r}"
    )


def test_ac7_wild_die_complication_renders_as_1_bang():
    """AC7: complication (Wild Die rolled 1) renders as `1!`. Our
    mishap fixture has a wild die with value=0 (the encoded complication
    state per design §4)."""
    out = run_with_d_prime_block(_build_row_setup(_arche_melee_mishap()))
    wild_chips = [
        c for c in out["dieChips"] if "is-wild" in c["cls"]
    ]
    # The actor's wild die has value=0 → '1!'; the defender's wild die
    # has value=3 → '3'. So at least one wild chip has '1!' text.
    has_complication = any(c["text"] == "1!" for c in wild_chips)
    assert has_complication, (
        f"Mishap fixture should render at least one wild die as '1!'. "
        f"Wild chip texts: {[c['text'] for c in wild_chips]}"
    )


def test_ac7_normal_wild_die_renders_just_its_value():
    """AC7: normal wild die (not exploded, not complication) renders as
    just its rolled value."""
    out = run_with_d_prime_block(_build_row_setup(_arche_ranged_miss()))
    wild_chips = [
        c for c in out["dieChips"] if "is-wild" in c["cls"]
    ]
    assert len(wild_chips) >= 1
    # Fixture has wild die value=4
    has_normal_value = any(c["text"] == "4" for c in wild_chips)
    assert has_normal_value, (
        f"Normal wild die should render as its value (4). "
        f"Wild chip texts: {[c['text'] for c in wild_chips]}"
    )


# ════════════════════════════════════════════════════════════════════
# AC8 — Stun-mode KO routing
# ════════════════════════════════════════════════════════════════════

def test_ac8_stun_unconscious_outcome_renders_in_headline():
    """AC8: outcome_type='stun_unconscious' must render 'Stunned —
    Unconscious!' in the headline area, with the outcome class
    matching. The headline has TWO .cri-outcome spans: the first is
    just hit/miss, the second is the wound_outcome class (when hit)."""
    setup = r"""
        var ev = { payload: PAYLOAD_HERE, role: 'self', expanded: true };
        var row = window.buildCombatResultRow(ev);
        var outcomes = row.querySelectorAll('.cri-outcome');
        function classesOf(el) {
          return el ? Array.prototype.slice.call(el.classList) : [];
        }
        window.__d_prime_result = {
          count:         outcomes.length,
          firstClasses:  classesOf(outcomes[0]),
          secondClasses: classesOf(outcomes[1]),
          secondText:    outcomes[1] ? outcomes[1].textContent.trim() : null
        };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_stun_unconscious()))
    out = run_with_d_prime_block(setup)
    # Two outcome spans: hit/miss + wound class
    assert out["count"] == 2, (
        f"Stun-mode hit should produce 2 .cri-outcome spans, got "
        f"{out['count']}"
    )
    # First span = 'hit'
    assert "hit" in out["firstClasses"]
    # Second span = wound class derived from outcome_type
    assert "stun-unconscious" in out["secondClasses"], (
        f"Stun KO outcome class missing on second outcome span. "
        f"Got: {out['secondClasses']}"
    )
    # And the display text matches
    assert "Stunned" in out["secondText"]
    assert "Unconscious" in out["secondText"]


# ════════════════════════════════════════════════════════════════════
# AC9 — Visibility rules (actor/target expanded, bystander collapsed)
# ════════════════════════════════════════════════════════════════════

def test_ac9_actor_role_expanded_class_set():
    """AC9: actor and target see inspector pre-expanded."""
    out = run_with_d_prime_block(
        _build_row_setup(_arche_ranged_hit_with_explosion(),
                         role="self", expanded=True)
    )
    assert "expanded" in out["summaryClass"]
    assert "is-self" in out["rowClasses"]


def test_ac9_target_role_expanded_class_set():
    out = run_with_d_prime_block(
        _build_row_setup(_arche_ranged_hit_with_explosion(),
                         role="target", expanded=True)
    )
    assert "expanded" in out["summaryClass"]
    assert "is-target" in out["rowClasses"]


def test_ac9_bystander_role_collapsed_no_expanded_class():
    """Bystanders see the inspector collapsed by default. Verified by
    absence of .expanded on .cri-summary."""
    out = run_with_d_prime_block(
        _build_row_setup(_arche_ranged_hit_with_explosion(),
                         role="bystander", expanded=False)
    )
    assert "expanded" not in out["summaryClass"]
    # And NO is-self / is-target classes
    assert "is-self" not in out["rowClasses"]
    assert "is-target" not in out["rowClasses"]


def test_ac9_css_collapses_body_by_default():
    """The CSS contract: .cri-body must be display:none by default,
    and .cri-summary.expanded must use the sibling combinator to flip
    .cri-body to display:block. Static check — if either CSS rule
    drifts, the runtime expand/collapse breaks silently."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    # Default-collapsed contract
    assert re.search(r"\.cri-body\s*\{[^}]*display:\s*none", text), (
        ".cri-body must default to display:none (collapsed). "
        "AC9 visibility rules silently break without this CSS rule."
    )
    # Sibling-combinator expand contract
    assert re.search(
        r"\.cri-summary\.expanded\s*~\s*\.cri-body\s*\{[^}]*display:\s*block",
        text,
    ), (
        ".cri-summary.expanded ~ .cri-body { display: block } CSS rule "
        "missing. AC9 expand-on-click silently breaks without this rule."
    )


def test_ac9_summary_click_toggles_expanded_class():
    """Static check: buildCombatResultRow must add a click handler on
    .cri-summary that toggles the 'expanded' class. Runtime: load the
    extracted block and synthesize a click."""
    setup = r"""
        var ev = { payload: PAYLOAD_HERE, role: 'bystander', expanded: false };
        var row = window.buildCombatResultRow(ev);
        document.body.appendChild(row);
        var summary = row.querySelector('.cri-summary');
        var beforeClick = summary.classList.contains('expanded');
        // Synthesize click — jsdom supports MouseEvent dispatch
        var ev2 = new window.MouseEvent('click', { bubbles: true });
        summary.dispatchEvent(ev2);
        var afterClick = summary.classList.contains('expanded');
        window.__d_prime_result = {
          beforeClick: beforeClick,
          afterClick:  afterClick
        };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    assert out["beforeClick"] is False
    assert out["afterClick"] is True


# ════════════════════════════════════════════════════════════════════
# AC10 — Dedup of parallel two-line narrative
# ════════════════════════════════════════════════════════════════════

def test_ac10_dedup_fingerprint_helpers_exist():
    """AC10: client suppresses redundant two-line narrative when a
    combat_resolution_event arrived in the prior 250ms. Static check
    on the helper functions + the constant — these live in the SPA
    module as of Drop 4.4."""
    module_text = (REPO_ROOT / "static" / "spa" / "m3_combat_inspector.js").read_text(encoding="utf-8")
    assert "function recordCombatEventFingerprint" in module_text
    assert "function isDuplicateOfRecentCombatEvent" in module_text
    assert re.search(r"COMBAT_DEDUP_WINDOW_MS\s*=\s*250", module_text), (
        "Dedup window constant missing or not set to 250ms"
    )
    # Also assert client.html still has the delegators that forward to
    # the module — both call sites in client.html (WS router and legacy
    # text suppressor) depend on these wrappers.
    client_text = CLIENT_HTML.read_text(encoding="utf-8")
    assert "function isDuplicateOfRecentCombatEvent(" in client_text, (
        "client.html must keep a delegator named isDuplicateOfRecentCombatEvent — "
        "the legacy pose-text suppressor calls it by bare name."
    )
    assert "function handleCombatResolutionEvent(" in client_text, (
        "client.html must keep a delegator named handleCombatResolutionEvent — "
        "the WS router calls it by bare name."
    )


def test_ac10_dedup_records_fingerprint_for_received_event():
    """When handleCombatResolutionEvent is invoked, the dedup
    fingerprint store must record entries for both the headline and
    the mechline so the parallel text broadcast can be suppressed."""
    setup = r"""
        // Provide capturing appendEvent so handleCombatResolutionEvent
        // doesn't fail. The dedup state is the global combatEventFingerprints.
        var __captured = [];
        appendEvent = function(ev) { __captured.push(ev); };
        var msg = PAYLOAD_HERE;
        // Simulate a session where the viewer IS the actor
        lastHud.character_id = msg.actor.id;
        window.handleCombatResolutionEvent && window.handleCombatResolutionEvent(msg);
        // The function isn't exposed on window; reach it from the eval scope
        if (typeof handleCombatResolutionEvent === 'function') {
          handleCombatResolutionEvent(msg);
        }
        window.__d_prime_result = {
          fingerprintCount: combatEventFingerprints.length,
          captured: __captured.length
        };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    # handleCombatResolutionEvent calls recordCombatEventFingerprint
    # twice (once for headline, once for mechline). May get called once
    # or twice depending on which dispatch path the harness takes; ≥2
    # fingerprints either way.
    assert out["fingerprintCount"] >= 2, (
        f"Dedup fingerprint store should have ≥2 entries after "
        f"handleCombatResolutionEvent. Got {out['fingerprintCount']}."
    )
    assert out["captured"] >= 1, (
        f"appendEvent should have been called at least once. "
        f"Got {out['captured']} calls."
    )


def test_ac10_isDuplicate_matches_recently_recorded_fingerprint():
    """The duplicate check must positive-match a string that was just
    recorded."""
    setup = r"""
        recordCombatEventFingerprint('Tey Voss blasts B1 #1 with blaster — HIT — Wounded');
        var isDup = isDuplicateOfRecentCombatEvent('Tey Voss blasts B1 #1 with blaster — HIT — Wounded');
        var notDup = isDuplicateOfRecentCombatEvent('Some unrelated text');
        window.__d_prime_result = { isDup: isDup, notDup: notDup };
    """
    out = run_with_d_prime_block(setup)
    assert out["isDup"] is True, "Recently recorded fingerprint should match"
    assert out["notDup"] is False, "Unrelated text should not match"


# ════════════════════════════════════════════════════════════════════
# Schema version guard
# ════════════════════════════════════════════════════════════════════

def test_schema_version_guard_drops_mismatched_version():
    """handleCombatResolutionEvent must early-return when
    schema_version != 1 (the current version). This guards against
    showing wrong data when the server has a newer factory than the
    client knows about. Verified by passing a version=999 msg and
    confirming appendEvent was NOT called."""
    bad_msg = _arche_ranged_hit_with_explosion()
    bad_msg["schema_version"] = 999
    setup = r"""
        var __captured = [];
        appendEvent = function(ev) { __captured.push(ev); };
        handleCombatResolutionEvent(PAYLOAD_HERE);
        window.__d_prime_result = { captured: __captured.length };
    """.replace("PAYLOAD_HERE", json.dumps(bad_msg))
    out = run_with_d_prime_block(setup)
    assert out["captured"] == 0, (
        f"handleCombatResolutionEvent should silent-drop schema "
        f"v999 messages. Got {out['captured']} captured calls."
    )


def test_schema_version_guard_accepts_v1():
    """The current schema_version is 1 — messages at version 1 must
    flow through (positive control for the above negative test)."""
    setup = r"""
        var __captured = [];
        appendEvent = function(ev) { __captured.push(ev); };
        handleCombatResolutionEvent(PAYLOAD_HERE);
        window.__d_prime_result = { captured: __captured.length };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    assert out["captured"] == 1, (
        f"schema v1 message should pass through and append exactly 1 "
        f"event. Got {out['captured']}."
    )


# ════════════════════════════════════════════════════════════════════
# Role assignment (the heart of AC9's visibility rule)
# ════════════════════════════════════════════════════════════════════

def test_role_assignment_self_when_viewer_is_actor():
    """When lastHud.character_id matches msg.actor.id, role='self' and
    the event is appended with expanded=true."""
    setup = r"""
        var __captured = [];
        appendEvent = function(ev) { __captured.push(ev); };
        var msg = PAYLOAD_HERE;
        lastHud.character_id = msg.actor.id;  // viewer = actor
        handleCombatResolutionEvent(msg);
        window.__d_prime_result = {
          role:     __captured[0] && __captured[0].role,
          expanded: __captured[0] && __captured[0].expanded
        };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    assert out["role"] == "self"
    assert out["expanded"] is True


def test_role_assignment_target_when_viewer_is_target():
    setup = r"""
        var __captured = [];
        appendEvent = function(ev) { __captured.push(ev); };
        var msg = PAYLOAD_HERE;
        lastHud.character_id = msg.target.id;  // viewer = target
        handleCombatResolutionEvent(msg);
        window.__d_prime_result = {
          role:     __captured[0] && __captured[0].role,
          expanded: __captured[0] && __captured[0].expanded
        };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    assert out["role"] == "target"
    assert out["expanded"] is True


def test_role_assignment_bystander_when_viewer_is_neither():
    """Bystander role: viewer's id matches neither actor nor target.
    Inspector starts collapsed."""
    setup = r"""
        var __captured = [];
        appendEvent = function(ev) { __captured.push(ev); };
        var msg = PAYLOAD_HERE;
        lastHud.character_id = 999;  // not actor, not target
        handleCombatResolutionEvent(msg);
        window.__d_prime_result = {
          role:     __captured[0] && __captured[0].role,
          expanded: __captured[0] && __captured[0].expanded
        };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    assert out["role"] == "bystander"
    assert out["expanded"] is False


# ════════════════════════════════════════════════════════════════════
# composeCombatHeadline / composeCombatMechline (dedup matching)
# ════════════════════════════════════════════════════════════════════

def test_composeCombatHeadline_renders_actor_verb_target():
    """The headline composer must produce a string containing actor,
    verb, and target. Used for dedup matching against the parallel
    text broadcast."""
    setup = r"""
        var msg = PAYLOAD_HERE;
        var headline = composeCombatHeadline(msg);
        window.__d_prime_result = { headline: headline };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    h = out["headline"]
    assert "Tey Voss" in h, f"Actor name missing from headline: {h}"
    assert "B1 #1" in h,    f"Target name missing from headline: {h}"
    assert "HIT" in h,      f"Hit outcome missing from headline: {h}"


def test_composeCombatMechline_renders_roll_and_damage():
    """The mechline composer must produce 'Roll: X vs Y · Damage A vs
    Soak B → wound' for hits."""
    setup = r"""
        var msg = PAYLOAD_HERE;
        var mech = composeCombatMechline(msg);
        window.__d_prime_result = { mech: mech };
    """.replace("PAYLOAD_HERE", json.dumps(_arche_ranged_hit_with_explosion()))
    out = run_with_d_prime_block(setup)
    m = out["mech"]
    assert "Roll: 22" in m, f"Attack total missing/wrong in mechline: {m}"
    assert "vs 13" in m,    f"Defense total missing/wrong in mechline: {m}"
    assert "Damage 14" in m, f"Damage total missing/wrong in mechline: {m}"
    assert "Soak 8" in m,   f"Soak total missing/wrong in mechline: {m}"


# ════════════════════════════════════════════════════════════════════
# Window exposure contract (the harness depends on this)
# ════════════════════════════════════════════════════════════════════

def test_window_exposure_for_test_reach():
    """The D' regression suite reaches buildCombatResultRow and friends
    via window._sw_* exposures (Drop 4.3 added these for test reach).
    If these get dropped in a refactor, this whole regression suite
    silently bypasses the production code."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    for name in (
        "_sw_buildCombatResultRow",
        "_sw_buildDieChip",
        "_sw_buildCombatHeadlineHtml",
        "_sw_composeCombatHeadline",
        "_sw_composeCombatMechline",
        "_sw_combatVerbForSkill",
    ):
        assert f"window.{name}" in text, (
            f"window.{name} exposure missing. The D' regression suite "
            "depends on these exposures to reach production functions."
        )


# ════════════════════════════════════════════════════════════════════
# SPA module contract (Drop 4.4 replaces the marker-based extraction)
# ════════════════════════════════════════════════════════════════════

def test_extraction_markers_present_and_well_ordered():
    """Drop 4.4 moved the D' rendering block out of static/client.html
    into static/spa/m3_combat_inspector.js. The marker pair
    (DROP-D'-TEST-EXTRACT-START / END) is gone. This test now asserts
    the SPA module is well-formed: it exists, it's an IIFE, it exports
    window.M3CombatInspector with the expected surface, and the 15
    function names the regression suite relies on are all defined.

    Test name preserved from Drop 4.3 to keep the regression-fixture
    set stable; the semantics are the post-4.4 equivalent.
    """
    module_path = REPO_ROOT / "static" / "spa" / "m3_combat_inspector.js"
    assert module_path.exists(), (
        f"Drop 4.4 module missing at {module_path}. The 4.4 modularization "
        "either didn't ship or was reverted."
    )
    src = module_path.read_text(encoding="utf-8")

    # IIFE shape — opens with (function(){ and closes with })();
    assert "(function(){" in src or "(function () {" in src, (
        "m3_combat_inspector.js must be wrapped in an IIFE — module pattern."
    )
    assert "})();" in src, "IIFE not closed at end of m3_combat_inspector.js"

    # window.M3CombatInspector export — single namespaced export per SPA convention.
    assert "window.M3CombatInspector" in src, (
        "m3_combat_inspector.js must export window.M3CombatInspector — "
        "the single-namespace pattern from /static/spa/README.md."
    )

    # The 14+ function names the regression suite relies on must all be defined.
    for fname in ("buildCombatResultRow", "buildDieChip",
                  "handleCombatResolutionEvent", "composeCombatHeadline",
                  "composeCombatMechline", "appendPoolRow",
                  "buildAttackerSection", "buildDefenderSection",
                  "buildDifficultySection", "buildDamageSection",
                  "buildSoakSection", "buildWoundSection",
                  "buildSourceLegend", "combatVerbForSkill",
                  "recordCombatEventFingerprint",
                  "isDuplicateOfRecentCombatEvent",
                  "buildCombatHeadlineHtml"):
        assert f"function {fname}" in src, (
            f"m3_combat_inspector.js missing function {fname}. The module "
            "may have been refactored; update this test or the module."
        )

    # init() function must be present + exported — it's how client.html
    # wires the ambient helpers (escapeHtml, appendEvent, lastHud etc.)
    # into the module.
    assert "function init(" in src, "Module must define init() for DI"
    assert re.search(r"init\s*:\s*init\b", src), (
        "Module must export init in the window.M3CombatInspector namespace "
        "(expected an `init: init` entry in the exports object)"
    )
