# -*- coding: utf-8 -*-
"""tests/test_serializer_roundtrip_extra.py — T3.20 state-preservation.

Completes the reload-round-trip coverage (scope_notes c) of the codebase's
persisted (de)serializer pairs, beyond Character (test_character_reload_roundtrip)
and the board/inventory/buff set (test_persisted_entity_roundtrip): the two
remaining persisted serializers, each with a different shape —

  * TrafficShip (engine/npc_space_traffic.py) — to_json / from_json, persisted via
    db.update_traffic_ship_state(ship.ship_id, ship.to_json()) and reloaded via
    TrafficShip.from_json(row["id"], data). NOTE: the row id is threaded into
    from_json SEPARATELY (it is NOT carried in to_json), so the round trip passes
    ship_id explicitly.
  * NPCConfig (ai/npc_brain.py) — to_dict / from_dict, persisted in the
    npcs.ai_config JSON blob.

Both are plain @dataclasses, so value __eq__ pins the WHOLE entity across the pure
dict contract AND the real json.dumps/json.loads path, plus to_json/to_dict
stability and (for TrafficShip) enum-TYPE survival. Also pins NPCConfig's
documented knowledge str->list tolerance.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


_SHIP_ID = 7704


def _rich_traffic_payload():
    # Every to_json key, non-default, with valid enum string values.
    return {
        "archetype": "bounty_hunter",
        "state": "tailing",
        "current_zone": "tatooine_orbit",
        "route": ["kessel_run_1", "kessel_run_2"],
        "transit_elapsed": 12.5,
        "spawned_at": 1700000000.0,
        "max_lifetime": 3600.0,
        "state_entered_at": 1700000100.0,
        "state_duration": 45.0,
        "hail_sent": True,
        "hail_timeout": 1700000200.0,
        "bounty_target_char_id": 9001,
        "hail_pending": True,
        "hail_source_char_id": 9002,
        "patrol_fight_rounds": 3,
        "patrol_zone_index": 2,
        "tailing_ship_id": 8800,
        "pirate_demand_credits": 1500,
        "pirate_paid": False,
        "bounty_target_name": "Vex Tarn",
        "hunter_hail_sent": True,
        "display_name": "Pursuit Vessel Korda",
        "transponder_type": "hunter",
        "captain_name": "a hulking Trandoshan",
    }


class TestTrafficShipRoundTrip(unittest.TestCase):
    def setUp(self):
        from engine.npc_space_traffic import TrafficShip
        self.orig = TrafficShip.from_json(_SHIP_ID, _rich_traffic_payload())
        self.pure = TrafficShip.from_json(_SHIP_ID, self.orig.to_json())
        self.jrt = TrafficShip.from_json(
            _SHIP_ID, json.loads(json.dumps(self.orig.to_json())))

    def test_pure_round_trip_equals_original(self):
        self.assertEqual(self.pure, self.orig)

    def test_json_round_trip_equals_original(self):
        self.assertEqual(self.jrt, self.orig)

    def test_to_json_stable_under_round_trip(self):
        self.assertEqual(self.pure.to_json(), self.orig.to_json())
        self.assertEqual(self.jrt.to_json(), self.orig.to_json())

    def test_ship_id_threaded_through_reload(self):
        # ship_id is the DB row key, passed to from_json separately (not in
        # to_json) — confirm the reload keeps it on the rebuilt object.
        self.assertEqual(self.pure.ship_id, _SHIP_ID)
        self.assertEqual(self.jrt.ship_id, _SHIP_ID)

    def test_enum_types_survive(self):
        from engine.npc_space_traffic import TrafficArchetype, TrafficState
        for rt in (self.pure, self.jrt):
            self.assertIsInstance(rt.archetype, TrafficArchetype)
            self.assertIsInstance(rt.state, TrafficState)


class TestNPCConfigRoundTrip(unittest.TestCase):
    def setUp(self):
        from ai.npc_brain import NPCConfig
        self.orig = NPCConfig(
            enabled=True,
            model_tier=2,
            model_override="claude-haiku-4-5",
            provider_override="anthropic",
            personality="A jittery Sullustan dock clerk who talks too fast.",
            knowledge=["docking fees", "smuggler gossip", "ship registries"],
            faction="neutral",
            dialogue_style="fast, clipped, nervous",
            temperature=0.55,
            max_tokens=200,
            fallback_lines=["...busy right now.", "Talk to the harbormaster."],
        )
        self.pure = NPCConfig.from_dict(self.orig.to_dict())
        self.jrt = NPCConfig.from_dict(json.loads(json.dumps(self.orig.to_dict())))

    def test_pure_round_trip_equals_original(self):
        self.assertEqual(self.pure, self.orig)

    def test_json_round_trip_equals_original(self):
        self.assertEqual(self.jrt, self.orig)

    def test_to_dict_stable_under_round_trip(self):
        self.assertEqual(self.pure.to_dict(), self.orig.to_dict())
        self.assertEqual(self.jrt.to_dict(), self.orig.to_dict())

    def test_string_knowledge_coerces_to_list(self):
        # PIN the documented tolerance: a tutorial NPC may store `knowledge` as a
        # bare string; from_dict coerces it to a one-element list so downstream
        # list handling is uniform. Empty string -> empty list (not [""]).
        from ai.npc_brain import NPCConfig
        self.assertEqual(
            NPCConfig.from_dict({"knowledge": "knows the cantina"}).knowledge,
            ["knows the cantina"])
        self.assertEqual(NPCConfig.from_dict({"knowledge": ""}).knowledge, [])


if __name__ == "__main__":
    unittest.main()
