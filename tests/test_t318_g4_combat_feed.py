# -*- coding: utf-8 -*-
"""T3.18 G4 — compact combat damage feed.

The ground-UX overhaul (ground_ux_overhaul_design_v1.md §3.3 "Damage Feed")
adds a small ``events`` array to the ``combat_state`` push so the web combat
panel can render an at-a-glance recap of the last few attack outcomes — the
lightweight cousin of the per-hit ``combat_resolution_event`` inspector.

These tests pin:
  · the per-outcome ``result`` enum derivation in CombatInstance._record_feed_event
    (hit / soaked / miss / parried / dodged), including the gate that drops
    validation no-ops (no real attack roll → no feed record);
  · the ring-buffer cap;
  · that to_hud_dict surfaces the trailing window on ``events``;
  · the client contract (client.html renders the feed from combat_state.events).

Web-only: telnet ignores combat_state, so nothing here touches the text path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.character import Character, DicePool, SkillRegistry
from engine.combat import (
    CombatInstance, CombatAction, ActionType, Combatant, ActionResult,
    _FEED_RING_MAX, _FEED_RING_SHOWN,
)

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"


# ── Helpers ──────────────────────────────────────────────────────────────

def _skill_reg() -> SkillRegistry:
    import os
    reg = SkillRegistry()
    p = os.path.join(os.path.dirname(__file__), "..", "data", "skills.yaml")
    if os.path.exists(p):
        reg.load_file(p)
    return reg


def _fighter(name, char_id, *, dex="4D", blaster="4D", dodge="2D",
             strength="3D", brawling="3D") -> Character:
    c = Character(name=name, species_name="Human")
    c.id = char_id
    c.dexterity = DicePool.parse(dex)
    c.strength = DicePool.parse(strength)
    c.add_skill("blaster", DicePool.parse(blaster))
    c.add_skill("dodge", DicePool.parse(dodge))
    c.add_skill("brawling", DicePool.parse(brawling))
    c.add_skill("brawling parry", DicePool.parse("2D"))
    return c


def _combat_with_two():
    combat = CombatInstance(room_id=1, skill_reg=_skill_reg())
    combat.add_combatant(_fighter("Han", 1))
    combat.add_combatant(_fighter("Greedo", 2, dex="2D", blaster="1D"))
    return combat


def _result(*, success, wound, defense="11"):
    """Build a synthetic ActionResult for the feed-derivation unit tests."""
    return ActionResult(
        actor_id=1,
        action=CombatAction(action_type=ActionType.ATTACK, skill="blaster",
                            weapon_key="blaster_pistol", target_id=2),
        success=success,
        wound_inflicted=wound,
        defense_display=defense,
    )


# ── _record_feed_event: result-enum derivation ───────────────────────────

class TestFeedResultDerivation:
    def setup_method(self):
        self.combat = _combat_with_two()
        self.actor = self.combat.combatants[1]
        self.target = self.combat.combatants[2]
        self.action = CombatAction(action_type=ActionType.ATTACK,
                                   skill="blaster", weapon_key="blaster_pistol",
                                   target_id=2)

    def _record(self, result, *, ranged=True, defense_action=None):
        self.combat.recent_events.clear()
        self.combat._record_feed_event(
            self.actor, self.target, self.action, result,
            ranged=ranged, defense_action=defense_action,
        )
        return self.combat.recent_events

    def test_hit_with_wound(self):
        ev = self._record(_result(success=True, wound="Wounded"))
        assert len(ev) == 1
        assert ev[0]["result"] == "hit"
        assert ev[0]["wound"] == "Wounded"
        assert ev[0]["attacker"] == "Han"
        assert ev[0]["target"] == "Greedo"
        assert ev[0]["weapon"] == "blaster pistol"  # weapon_key humanized

    def test_hit_no_wound_is_soaked(self):
        ev = self._record(_result(success=True, wound="No Damage"))
        assert ev[0]["result"] == "soaked"

    def test_ranged_miss(self):
        ev = self._record(_result(success=False, wound=""), ranged=True,
                          defense_action=None)
        assert ev[0]["result"] == "miss"

    def test_ranged_miss_with_dodge_is_dodged(self):
        dodge = CombatAction(action_type=ActionType.DODGE, skill="dodge")
        ev = self._record(_result(success=False, wound=""), ranged=True,
                          defense_action=dodge)
        assert ev[0]["result"] == "dodged"

    def test_melee_miss_with_parry_is_parried(self):
        parry = CombatAction(action_type=ActionType.PARRY, skill="brawling parry")
        ev = self._record(_result(success=False, wound=""), ranged=False,
                          defense_action=parry)
        assert ev[0]["result"] == "parried"

    def test_melee_miss_no_defense_is_miss(self):
        # A melee swing that fails a STATIC weapon difficulty (no parry
        # declared) is a miss, NOT a parry — nobody parried.
        ev = self._record(_result(success=False, wound=""), ranged=False,
                          defense_action=None)
        assert ev[0]["result"] == "miss"

    def test_validation_noop_is_skipped(self):
        # No real attack roll happened → empty defense_display → no record.
        ev = self._record(_result(success=False, wound="", defense=""))
        assert ev == []

    def test_weapon_falls_back_to_skill(self):
        a = CombatAction(action_type=ActionType.ATTACK, skill="brawling",
                         weapon_key="", target_id=2)
        self.combat.recent_events.clear()
        self.combat._record_feed_event(
            self.actor, self.target, a,
            _result(success=True, wound="Wounded"),
            ranged=False, defense_action=None,
        )
        assert self.combat.recent_events[0]["weapon"] == "brawling"


# ── Ring buffer + payload surface ────────────────────────────────────────

class TestFeedRingAndPayload:
    def test_ring_buffer_caps_history(self):
        combat = _combat_with_two()
        actor, target = combat.combatants[1], combat.combatants[2]
        action = CombatAction(action_type=ActionType.ATTACK, skill="blaster",
                              weapon_key="blaster", target_id=2)
        for _ in range(_FEED_RING_MAX + 6):
            combat._record_feed_event(
                actor, target, action,
                _result(success=True, wound="Wounded"),
                ranged=True, defense_action=None,
            )
        assert len(combat.recent_events) == _FEED_RING_MAX

    def test_to_hud_dict_surfaces_trailing_window(self):
        combat = _combat_with_two()
        actor, target = combat.combatants[1], combat.combatants[2]
        action = CombatAction(action_type=ActionType.ATTACK, skill="blaster",
                              weapon_key="blaster", target_id=2)
        for i in range(_FEED_RING_SHOWN + 3):
            combat._record_feed_event(
                actor, target, action,
                _result(success=True, wound="Wounded%d" % i),
                ranged=True, defense_action=None,
            )
        payload = combat.to_hud_dict(viewer_id=1)
        assert "events" in payload
        assert len(payload["events"]) == _FEED_RING_SHOWN
        # Trailing window = the most recent records, newest last.
        assert payload["events"][-1]["wound"].startswith("Wounded")

    def test_events_empty_before_any_attack(self):
        combat = _combat_with_two()
        payload = combat.to_hud_dict(viewer_id=1)
        assert payload["events"] == []


# ── End-to-end: a resolved round populates the feed ──────────────────────

class TestFeedEndToEnd:
    def test_resolved_attack_populates_feed(self):
        combat = _combat_with_two()
        combat.roll_initiative()
        combat.declare_action(1, CombatAction(
            action_type=ActionType.ATTACK, skill="blaster",
            target_id=2, weapon_damage="5D"))
        combat.declare_action(2, CombatAction(
            action_type=ActionType.DODGE, skill="dodge"))
        combat.resolve_round()
        # At least Han's attack on Greedo should have produced a feed record.
        assert len(combat.recent_events) >= 1
        rec = combat.recent_events[-1]
        assert set(rec.keys()) == {"attacker", "target", "result", "wound", "weapon"}
        assert rec["result"] in ("hit", "soaked", "miss", "parried", "dodged")
        # And it is visible on the combat_state push.
        assert combat.to_hud_dict(viewer_id=1)["events"]


# ── combat_state schema uniformity (combat-ended sentinel) ───────────────

class TestCombatEndedSchema:
    def test_ended_push_carries_empty_events(self):
        # The active=False termination push must keep the events key so the
        # combat_state schema is uniform (client clears the feed regardless,
        # but consumers shouldn't have to special-case the sentinel shape).
        import asyncio
        from parser.combat_commands import _send_combat_ended

        captured = []

        class _Sess:
            async def send_json(self, mtype, data):
                captured.append((mtype, data))

        class _Mgr:
            def sessions_in_room(self, room_id, source_char=None):
                return [_Sess()]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_send_combat_ended(1, _Mgr(), source_char=None))
        finally:
            loop.close()

        assert captured
        mtype, data = captured[0]
        assert mtype == "combat_state"
        assert data["active"] is False
        assert data["events"] == []


# ── Client contract ──────────────────────────────────────────────────────

class TestClientContract:
    @pytest.fixture(scope="class")
    def html(self) -> str:
        assert CLIENT_HTML.exists()
        return CLIENT_HTML.read_text(encoding="utf-8")

    def test_feed_element_present(self, html):
        assert 'id="combat-feed"' in html

    def test_render_function_present(self, html):
        assert "function renderCombatFeed(" in html

    def test_render_reads_events(self, html):
        assert "renderCombatFeed(data.events)" in html

    def test_feed_css_present(self, html):
        assert ".combat-feed" in html
        assert ".cf-you-hit" in html
        assert ".cf-you-took" in html
