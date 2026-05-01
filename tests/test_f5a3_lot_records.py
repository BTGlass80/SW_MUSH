# -*- coding: utf-8 -*-
"""
tests/test_f5a3_lot_records.py — F.5a.3 lot-record integrity tests

F.5a.3 (Apr 30 2026) populated `data/worlds/clone_wars/housing_lots.yaml`
with 46 lot records (13 T1 + 16 T3 + 8 T4 + 9 T5). The F.5a.2 loader
parses them; F.5a.2.x.1 confirmed all design-doc host_room slugs are
live in the CW world.

This test file is the integrity guard between the two: it walks
every lot record and confirms its `host_room` slug actually resolves
to a live CW room (not just an EXPECTED_HOSTS list). If F.5a.2.x.1's
EXPECTED_HOSTS list goes stale, or if a future F.5a.3.x drop adds a
lot record pointing at a slug that doesn't exist, this test fires.

Tests:
  - Every T1 lot's host_room is a live CW room
  - Every T3 lot's host_room is a live CW room
  - Every T4 lot's host_room is a live CW room
  - Every T5 lot's host_room is a live CW room
  - Total record count matches design (13 T1 / 16 T3 / 8 T4 / 9 T5)
  - Per-tier-per-planet counts match cw_housing_design_v1.md tables
  - Cross-tier reference invariants hold (e.g., Coruscant T4 lots all
    in non-lawless zones per §3.4)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestLotRecordIntegrity(unittest.TestCase):
    """Every F.5a.3 lot record's host_room resolves to a live CW room."""

    @classmethod
    def setUpClass(cls):
        from engine.world_loader import (
            load_era_manifest, load_housing_lots, load_world_dry_run,
        )
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars"
        )
        cls.corpus = load_housing_lots(manifest)
        b = load_world_dry_run("clone_wars")
        cls.live_slugs = {r.slug for r in b.rooms.values()}
        cls.rooms_by_slug = {r.slug: r for r in b.rooms.values()}

    def _check_tier_host_rooms(self, lots, tier_name):
        unresolved = []
        for lot in lots:
            if lot.host_room not in self.live_slugs:
                unresolved.append((lot.id, lot.host_room, lot.planet))
        if unresolved:
            lines = [
                f"  {lid:<35} -> {hr:<35} (planet={p})"
                for lid, hr, p in unresolved
            ]
            self.fail(
                f"{len(unresolved)} {tier_name} lot host_rooms do not "
                f"resolve to live CW rooms:\n" + "\n".join(lines)
            )

    def test_tier1_host_rooms_all_resolve(self):
        self._check_tier_host_rooms(self.corpus.tier1_rentals, "T1")

    def test_tier3_host_rooms_all_resolve(self):
        self._check_tier_host_rooms(self.corpus.tier3_lots, "T3")

    def test_tier4_host_rooms_all_resolve(self):
        self._check_tier_host_rooms(self.corpus.tier4_lots, "T4")

    def test_tier5_host_rooms_all_resolve(self):
        self._check_tier_host_rooms(self.corpus.tier5_lots, "T5")

    def test_record_counts_match_design(self):
        """The design specifies 13 T1 / 16 T3 / 8 T4 / 9 T5 = 46 lots."""
        self.assertEqual(len(self.corpus.tier1_rentals), 13)
        self.assertEqual(len(self.corpus.tier3_lots), 16)
        self.assertEqual(len(self.corpus.tier4_lots), 8)
        self.assertEqual(len(self.corpus.tier5_lots), 9)
        total = (len(self.corpus.tier1_rentals)
                 + len(self.corpus.tier3_lots)
                 + len(self.corpus.tier4_lots)
                 + len(self.corpus.tier5_lots))
        self.assertEqual(total, 46)

    def test_per_planet_t1_distribution(self):
        """T1 distribution per design §6: Coruscant 4, Kuat 2, Kamino 1,
        Geonosis 1, Tatooine 2, Nar Shaddaa 3."""
        from collections import Counter
        c = Counter(lot.planet for lot in self.corpus.tier1_rentals)
        self.assertEqual(c["coruscant"], 4)
        self.assertEqual(c["kuat"], 2)
        self.assertEqual(c["kamino"], 1)
        self.assertEqual(c["geonosis"], 1)
        self.assertEqual(c["tatooine"], 2)
        self.assertEqual(c["nar_shaddaa"], 3)

    def test_per_planet_t3_distribution(self):
        """T3 distribution per design §7: Coruscant 6, Kuat 2, Geonosis 1,
        Tatooine 3, Nar Shaddaa 4 (3 GCW reskin + 1 NEW Warrens)."""
        from collections import Counter
        c = Counter(lot.planet for lot in self.corpus.tier3_lots)
        self.assertEqual(c["coruscant"], 6)
        self.assertEqual(c["kuat"], 2)
        self.assertEqual(c["geonosis"], 1)
        self.assertEqual(c["tatooine"], 3)
        self.assertEqual(c["nar_shaddaa"], 4)

    def test_kuat_t3_lots_are_rep_gated(self):
        """Per design §7.1, both Kuat T3 lots require Republic rep ≥ 25."""
        kuat_t3 = [lot for lot in self.corpus.tier3_lots
                   if lot.planet == "kuat"]
        self.assertEqual(len(kuat_t3), 2)
        for lot in kuat_t3:
            self.assertIsNotNone(
                lot.rep_gate,
                f"Kuat T3 lot {lot.id!r} must have rep_gate set."
            )
            self.assertEqual(lot.rep_gate.get("faction"), "republic",
                f"Kuat T3 lot {lot.id!r} rep_gate.faction must be republic.")
            self.assertGreaterEqual(lot.rep_gate.get("min_value"), 25,
                f"Kuat T3 lot {lot.id!r} rep_gate.min_value must be ≥ 25.")

    def test_kamino_t1_has_stay_cap(self):
        """Per design §6, the single Kamino T1 lot has max_stay_weeks: 2."""
        kamino_t1 = [lot for lot in self.corpus.tier1_rentals
                     if lot.planet == "kamino"]
        self.assertEqual(len(kamino_t1), 1)
        self.assertEqual(kamino_t1[0].max_stay_weeks, 2)

    def test_coco_town_market_arcade_is_flagship(self):
        """Per design §8, coco_town_market_arcade is the flagship CW
        shopfront and must have market_search_priority: 100."""
        flagship = [lot for lot in self.corpus.tier4_lots
                    if lot.id == "coco_town_market_arcade"]
        self.assertEqual(len(flagship), 1)
        self.assertEqual(flagship[0].market_search_priority, 100)

    def test_t4_lots_not_in_lawless_zones(self):
        """Per design §3.4 (housing invariant), no T4 shopfronts in
        lawless zones. Verify each T4 lot's host_room zone is not
        lawless. We check by zone name keyword since lawless tagging
        lives on the room (not the lot)."""
        lawless_zones = {
            "coruscant_lower",       # Southern Underground = lawless
            "geonosis_surface",      # Stalgasin Hive Surface = lawless
            "tatooine_jundland",     # Jundland Wastes = lawless
            "nar_shaddaa_undercity", # Undercity = lawless
            "nar_shaddaa_warrens",   # Warrens = lawless
        }
        violations = []
        for lot in self.corpus.tier4_lots:
            r = self.rooms_by_slug.get(lot.host_room)
            if r is None:
                continue
            if r.zone in lawless_zones:
                violations.append((lot.id, lot.host_room, r.zone))
        if violations:
            lines = [
                f"  {lid:<35} -> {hr:<35} (lawless zone={z})"
                for lid, hr, z in violations
            ]
            self.fail(
                f"{len(violations)} T4 lots are in lawless zones, "
                f"violating design §3.4:\n" + "\n".join(lines)
            )

    def test_corpus_has_no_load_errors(self):
        """The lot YAML must parse without validation errors."""
        self.assertEqual(
            self.corpus.report.errors, [],
            f"CW housing_lots.yaml load produced {len(self.corpus.report.errors)} "
            f"errors: {self.corpus.report.errors[:3]}"
        )

    def test_t1_lot_npcs_are_unique_per_lot(self):
        """Each T1 rental host has a distinct rental clerk NPC slug."""
        npcs = [lot.npc for lot in self.corpus.tier1_rentals]
        from collections import Counter
        c = Counter(npcs)
        dupes = [(npc, n) for npc, n in c.items() if n > 1]
        if dupes:
            self.fail(
                f"T1 lots have duplicate NPC slugs: {dupes}. "
                f"Each rental host should have its own clerk NPC."
            )

    def test_lot_ids_are_globally_unique(self):
        """Lot IDs across all four tiers must be unique (the loader
        scopes uniqueness per-tier, but we want global uniqueness for
        cross-tier reference clarity)."""
        all_ids = (
            [lot.id for lot in self.corpus.tier1_rentals]
            + [lot.id for lot in self.corpus.tier3_lots]
            + [lot.id for lot in self.corpus.tier4_lots]
            + [lot.id for lot in self.corpus.tier5_lots]
        )
        from collections import Counter
        c = Counter(all_ids)
        dupes = [(lid, n) for lid, n in c.items() if n > 1]
        if dupes:
            self.fail(f"Lot IDs collide across tiers: {dupes}")


if __name__ == "__main__":
    unittest.main()
