# -*- coding: utf-8 -*-
"""tests/test_persisted_entity_roundtrip.py — T3.20 state-preservation.

Reload-round-trip INVARIANTS for the persisted board / inventory / buff entities
that serialize through a ``to_dict`` / ``from_dict`` pair, extending the Character
contract pinned in tests/test_character_reload_roundtrip.py to the rest of the
durable-state surface:

  * ItemInstance   (engine/items.py)        — equipment-slot + carried-inventory JSON
  * Mission        (engine/missions.py)     — missions.data JSON column
  * BountyContract (engine/bounty_board.py) — bounties.data JSON column
  * SmugglingJob   (engine/smuggling.py)    — smuggling_jobs.data JSON column
  * Buff           (engine/buffs.py)        — characters.attributes->active_buffs JSON

Each is a plain @dataclass, so value-based ``__eq__`` lets us assert the WHOLE
entity survives a round trip. Two round trips are exercised per entity:

  1. the pure dict contract    from_dict(x.to_dict())
  2. the REAL production path   from_dict(json.loads(json.dumps(x.to_dict())))

plus the strongest single guard — ``to_dict`` is stable under the round trip
(re-serializing the reloaded entity reproduces the exact same dict). Together these
catch the silent save-data-loss class: a field added to one serializer but not the
other, a column key renamed, an enum that stops round-tripping, or a precision change.

SCOPE: production persists each entity by ``json.dumps(x.to_dict())`` into a TEXT
column and reloads via ``from_dict(json.loads(col))`` — so the json round trip here
reproduces the exact transform the DB applies; a live-DB write/read would add only
async plumbing, not contract coverage. That boundary is the contract, pinned here.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _RoundTripMixin:
    """Round-trip assertions shared by every persisted-entity test below.

    NOT a ``TestCase`` subclass, so pytest/unittest never collects it standalone.
    Each entity subclass provides ``_build()`` returning a fully-populated instance
    with a NON-DEFAULT value in every meaningful field.
    """

    def _build(self):  # pragma: no cover - overridden by each entity subclass
        raise NotImplementedError

    def setUp(self):
        self.orig = self._build()
        cls = type(self.orig)
        self.pure = cls.from_dict(self.orig.to_dict())
        # The real production persist path: json.dumps -> TEXT column -> json.loads.
        self.jrt = cls.from_dict(json.loads(json.dumps(self.orig.to_dict())))

    def test_pure_round_trip_equals_original(self):
        self.assertEqual(self.pure, self.orig,
                         "pure to_dict/from_dict round trip lost or changed a field")

    def test_json_round_trip_equals_original(self):
        self.assertEqual(self.jrt, self.orig,
                         "json (production) round trip lost or changed a field")

    def test_to_dict_stable_under_round_trip(self):
        # Asymmetry guard: to_dict emitting a field from_dict cannot restore (or
        # vice-versa) shows up here even when __eq__ would miss it.
        self.assertEqual(self.pure.to_dict(), self.orig.to_dict(),
                         "to_dict not stable under the pure round trip")
        self.assertEqual(self.jrt.to_dict(), self.orig.to_dict(),
                         "to_dict not stable under the json round trip")


class TestItemInstanceRoundTrip(_RoundTripMixin, unittest.TestCase):
    def _build(self):
        from engine.items import ItemInstance
        return ItemInstance(
            key="blaster_rifle",
            condition=73,
            max_condition=95,
            quality=68,
            crafter="Vex Tannor",
            experiment_count=2,
            breakdown_dice=2,
            experiment_log=[
                {"axis": "damage", "boost": 3.2, "tradeoff": {"durability": -0.96}},
                {"axis": "accuracy", "boost": 1.8},
            ],
            effective_mods={"damage_mod": 3.2, "durability_mod": -0.96,
                            "accuracy_mod": 1.8},
        )

    def test_experiment_block_survives(self):
        # to_dict OMITS the experiment block when experiment_count == 0; here it is
        # forced on, so all four jury-rig fields must survive both round trips.
        for rt in (self.pure, self.jrt):
            self.assertEqual(rt.experiment_count, 2)
            self.assertEqual(rt.breakdown_dice, 2)
            self.assertEqual(rt.experiment_log, self.orig.experiment_log)
            self.assertEqual(rt.effective_mods, self.orig.effective_mods)

    def test_unmodified_instance_round_trips_through_omission(self):
        # An unmodified/uncrafted instance has its crafter + experiment block
        # OMITTED by to_dict; from_dict's defaults must reproduce it identically.
        from engine.items import ItemInstance
        plain = ItemInstance(key="vibroblade")
        self.assertNotIn("crafter", plain.to_dict())
        self.assertEqual(ItemInstance.from_dict(plain.to_dict()), plain)


class TestMissionRoundTrip(_RoundTripMixin, unittest.TestCase):
    def _build(self):
        from engine.missions import Mission, MissionType, MissionStatus
        return Mission(
            id="m-deadbeef",
            mission_type=MissionType.SMUGGLING,
            title="Smuggling: Mos Eisley Spaceport",
            giver="Watto",
            objective="Move a crate of spice to Mos Eisley without getting caught.",
            destination="Mos Eisley Spaceport Control Tower",
            destination_room_id="4271",
            reward=3500,
            required_skill="con",
            status=MissionStatus.ACCEPTED,
            accepted_by="char-9001",
            created_at=1700000000.5,
            accepted_at=1700000123.25,
            expires_at=1700007200.75,
            mission_data={"zone": "tatooine_orbit", "kills": 3,
                          "escort_ship": "Twin Pod"},
            faction_code="hutt_cartel",
            faction_rep_required=25,
        )

    def test_enum_types_survive(self):
        from engine.missions import MissionType, MissionStatus
        for rt in (self.pure, self.jrt):
            self.assertIsInstance(rt.mission_type, MissionType)
            self.assertIsInstance(rt.status, MissionStatus)

    def test_nested_mission_data_survives(self):
        for rt in (self.pure, self.jrt):
            self.assertEqual(rt.mission_data, self.orig.mission_data)


class TestBountyContractRoundTrip(_RoundTripMixin, unittest.TestCase):
    def _build(self):
        from engine.bounty_board import BountyContract, BountyTier, BountyStatus
        return BountyContract(
            id="b-cafef00d",
            tier=BountyTier.SUPERIOR,
            target_name="Vex Tarn",
            target_species="Trandoshan",
            target_archetype="bounty_hunter",
            crime_description="wanted for murder - last seen armed and dangerous",
            posting_org="Bounty Hunters' Guild - Tatooine Charter",
            tip="Last confirmed location: the spaceport.",
            reward=7500,
            reward_alive_bonus=1500,
            target_npc_id=4242,
            target_room_id=1337,
            status=BountyStatus.CLAIMED,
            claimed_by="char-99",
            posted_at=1700000000.0,
            claimed_at=1700000100.0,
            expires_at=1700014500.0,
            collected_at=1700000200.0,
            chain_bounty_id="tutorial_bhg_tarko_vinn",
        )

    def test_enum_types_survive(self):
        from engine.bounty_board import BountyTier, BountyStatus
        for rt in (self.pure, self.jrt):
            self.assertIsInstance(rt.tier, BountyTier)
            self.assertIsInstance(rt.status, BountyStatus)

    def test_chain_bounty_id_survives(self):
        # Regression guard: the existing test_bounty_board_unit round-trip test
        # omits chain_bounty_id from its field loop. Pin it here — the chain_events
        # dispatcher reads it on board.claim to advance the BHG tutorial chain.
        for rt in (self.pure, self.jrt):
            self.assertEqual(rt.chain_bounty_id, "tutorial_bhg_tarko_vinn")


class TestSmugglingJobRoundTrip(_RoundTripMixin, unittest.TestCase):
    def _build(self):
        from engine.smuggling import SmugglingJob, CargoTier, JobStatus
        return SmugglingJob(
            id="smug-abc123",
            tier=CargoTier.SPICE,
            cargo_type="raw Kessel spice",
            contact_name="a scarred Weequay",
            dropoff_name="a Hutt factor in Nar Shaddaa's Lower Promenade",
            reward=12000,
            fine=3000,
            patrol_chance=0.65,
            status=JobStatus.ACCEPTED,
            accepted_by=4242,
            destination_planet="coruscant",
            created_at=1700000000.0,
            expires_at=1700007200.0,
        )

    def test_enum_types_survive(self):
        # CargoTier is an int-Enum, JobStatus a str-Enum: assert the ENUM type
        # survives, not merely the scalar (which would compare == anyway).
        from engine.smuggling import CargoTier, JobStatus
        for rt in (self.pure, self.jrt):
            self.assertIsInstance(rt.tier, CargoTier)
            self.assertIsInstance(rt.status, JobStatus)

    def test_float_patrol_chance_survives(self):
        for rt in (self.pure, self.jrt):
            self.assertEqual(rt.patrol_chance, 0.65)


class TestBuffRoundTrip(_RoundTripMixin, unittest.TestCase):
    def _build(self):
        from engine.buffs import Buff
        return Buff(
            buff_type="cantina_drink",
            source="item:drink",
            stat_modifiers={"perception": -1, "con": 2},
            duration_seconds=1800,
            started_at=1718323200.5,
            stacks=2,
            max_stacks=3,
            display_name="Cantina Buzz Deluxe",
            positive=False,
        )

    def test_explicit_display_name_survives(self):
        for rt in (self.pure, self.jrt):
            self.assertEqual(rt.display_name, "Cantina Buzz Deluxe")

    def test_empty_display_name_normalizes_to_title(self):
        # PIN the intentional producer quirk: to_dict substitutes a title-cased
        # buff_type for an EMPTY display_name, so a buff saved with display_name=""
        # reloads with the derived label. Documented behavior — change consciously.
        from engine.buffs import Buff
        b = Buff(buff_type="combat_stim", source="item:stimpack",
                 stat_modifiers={"dexterity": 3}, duration_seconds=300)
        self.assertEqual(b.display_name, "")
        reloaded = Buff.from_dict(b.to_dict())
        self.assertEqual(reloaded.display_name, "Combat Stim")


if __name__ == "__main__":
    unittest.main()
