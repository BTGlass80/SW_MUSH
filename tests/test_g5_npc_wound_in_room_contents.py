"""
test_g5_npc_wound_in_room_contents.py — G5 (T3.17/T3.18) verification.

Surfaces each live hostile NPC's wound state in the web client's HERE panel
(room_contents) so a player can see, at a glance, which mob is nearly down in
a multi-enemy fight. Two halves:

  • PRODUCER — server.session._npc_wound_map(): a pure, READ-ONLY marshalling
    helper over the live combat object (no combat.py mutation), keyed by the
    NPC's DB row id. Unit-tested directly against fake combatants carrying the
    real WoundLevel enum so the ``.char.wound_level.value`` contract is pinned.

  • CONSUMER — static/client.html HERE-panel render + badge CSS. Static-parse
    checks (mirrors tests/spa/test_gnd_ux_sidebar_panels.py) that the client
    actually reads the new wound_level/wound_name fields and styles the badge.

Docs/marshalling only: no schema, no faucet/sink, era-clean, engine READ-ONLY.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from engine.character import WoundLevel
from server.session import _npc_wound_map, _wound_name

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _client_html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def _combatant(cid: int, is_npc: bool, wound: WoundLevel):
    """A minimal duck-typed Combatant: id + is_npc + char.wound_level.value."""
    char = SimpleNamespace(id=cid, wound_level=wound)
    return SimpleNamespace(id=cid, is_npc=is_npc, char=char)


def _fake_combat(*combatants):
    return SimpleNamespace(combatants={c.id: c for c in combatants})


# ─────────────────────────── PRODUCER: _npc_wound_map ───────────────────────

def test_no_combat_returns_empty_map():
    """No active combat → no wounds surfaced (every NPC defaults Healthy)."""
    assert _npc_wound_map(None) == {}


def test_maps_live_npc_wound_by_id():
    """A live NPC combatant's wound_level.value is keyed by its DB id."""
    combat = _fake_combat(
        _combatant(101, True, WoundLevel.WOUNDED),
        _combatant(102, True, WoundLevel.INCAPACITATED),
    )
    assert _npc_wound_map(combat) == {101: 2, 102: 4}


def test_non_npc_combatants_excluded():
    """PC combatants are never surfaced as room-NPC wounds."""
    combat = _fake_combat(
        _combatant(5, False, WoundLevel.MORTALLY_WOUNDED),   # the player
        _combatant(101, True, WoundLevel.WOUNDED),           # a mob
    )
    assert _npc_wound_map(combat) == {101: 2}


def test_healthy_npc_maps_to_zero():
    """A live but unhurt NPC reports 0 (Healthy), not absent-by-default."""
    combat = _fake_combat(_combatant(101, True, WoundLevel.HEALTHY))
    assert _npc_wound_map(combat) == {101: 0}


def test_dead_npc_surfaced():
    """A downed NPC in the teardown window still reports its true wound."""
    combat = _fake_combat(_combatant(101, True, WoundLevel.DEAD))
    assert _npc_wound_map(combat) == {101: 6}


def test_combatant_without_char_is_skipped():
    """A combatant with no cached char must not crash / must be skipped."""
    bad = SimpleNamespace(id=101, is_npc=True, char=None)
    combat = _fake_combat(bad)
    assert _npc_wound_map(combat) == {}


def test_combat_internals_hiccup_is_swallowed():
    """A broken combat object degrades to {} (HUD push must never crash)."""
    class _Boom:
        @property
        def combatants(self):
            raise RuntimeError("combat internals changed")
    assert _npc_wound_map(_Boom()) == {}


def test_string_ids_are_normalised_to_int():
    """id/value coercion is defensive against str-typed ids."""
    combat = _fake_combat(_combatant("101", True, WoundLevel.WOUNDED))
    assert _npc_wound_map(combat) == {101: 2}


# ─────────────────────── wound_name label reuse (shared) ────────────────────

def test_wound_name_labels_match_severity():
    """Badge text reuses the HUD's canonical label map."""
    assert _wound_name(0) == "healthy"
    assert _wound_name(2) == "wounded"
    assert _wound_name(4) == "incapacitated"
    assert _wound_name(6) == "dead"


# ─────────────────────────── CONSUMER: client.html ──────────────────────────

def test_client_reads_wound_level_field():
    """The HERE-panel render consumes npc.wound_level (no phantom producer)."""
    html = _client_html()
    assert "npc.wound_level" in html, "client does not read npc.wound_level"


def test_client_reads_wound_name_field():
    """The badge text consumes the server-provided wound_name."""
    assert "npc.wound_name" in _client_html(), "client does not read npc.wound_name"


def test_client_renders_wound_badge_element():
    """A here-wound badge element is created in the NPC render loop."""
    html = _client_html()
    assert "here-wound" in html, "here-wound badge class not rendered"
    # Severity buckets: stun / hurt / crit escalation.
    for sev in ("here-wound-stun", "here-wound-hurt", "here-wound-crit"):
        assert sev in html, f"missing wound severity bucket {sev}"


def test_client_badge_gated_on_positive_wound():
    """Healthy NPCs (wound_level 0) render no badge — gate present in source."""
    html = _client_html()
    assert re.search(r"npc\.wound_level\s*>\s*0", html), (
        "badge is not gated on wound_level > 0"
    )


def test_client_has_wound_badge_css():
    """The .here-wound badge has a style rule (visible affordance)."""
    assert re.search(r"\.here-wound\s*\{", _client_html()), (
        ".here-wound CSS rule missing"
    )
