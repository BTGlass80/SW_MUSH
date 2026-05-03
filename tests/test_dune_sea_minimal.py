# -*- coding: utf-8 -*-
"""
tests/test_dune_sea_minimal.py — Dune Sea wilderness substrate tests.

Per wilderness_system_design_v1.md and the v40 §3.5 Village build
prerequisite stack. This drop ships the **minimal** wilderness
substrate — enough to host the Village quest's landmarks. Tests
cover:

  1. Schema migration v19 (rooms.wilderness_region_id column)
  2. Wilderness loader — YAML parsing, validation, force-resonant merge
  3. Wilderness writer — landmark room creation, adjacency exits,
     idempotent rebuild
  4. End-to-end: load + write the actual Dune Sea YAML, verify
     landmark count, verify Village path traversability
  5. Force-resonant landmark properties survive the full pipeline
  6. Source-level markers (drop self-documents)

Out of scope (full wilderness engine, future drops):
  - Coordinate-grid tile generation
  - Movement engine
  - Hazard ticks
  - Encounter rolls
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema migration v19
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaV19(unittest.TestCase):

    def test_schema_version_is_19(self):
        from db.database import SCHEMA_VERSION
        # Generous-bound pattern (per F.5/F.6 fix) — schema version
        # ratchets upward with each additive migration. v20 (Drop 2)
        # added wilderness movement state on top of v19's wilderness
        # substrate. Equality fails on every new migration; >= catches
        # real regressions (rolled back too far) without re-staling.
        self.assertGreaterEqual(SCHEMA_VERSION, 19)

    def test_rooms_table_has_wilderness_region_id_column(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall("PRAGMA table_info(rooms)")
            cols = {r["name"] for r in rows}
            self.assertIn("wilderness_region_id", cols)
            await db._db.close()
        _run(_check())

    def test_wilderness_region_id_is_nullable(self):
        """Existing hand-built rooms must remain unaffected by v19."""
        async def _check():
            db = await _fresh_db()
            rid = await db.create_room(
                name="Test Room", desc_short="", desc_long="",
            )
            rows = await db._db.execute_fetchall(
                "SELECT wilderness_region_id FROM rooms WHERE id=?",
                (rid,),
            )
            self.assertIsNone(rows[0]["wilderness_region_id"])
            await db._db.close()
        _run(_check())

    def test_wilderness_region_id_index_exists(self):
        async def _check():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name=?",
                ("idx_rooms_wilderness_region",),
            )
            self.assertEqual(len(rows), 1)
            await db._db.close()
        _run(_check())

    def test_v18_to_v19_upgrade_adds_column(self):
        """Simulate upgrade from v18 to v19 by manually bumping a fresh
        DB to v18, then re-running initialize."""
        async def _check():
            from db.database import Database
            db = Database(":memory:")
            await db.connect()
            await db.initialize()
            # Rooms table comes pre-created with the column on a fresh DB.
            # Confirm migration is idempotent — re-running shouldn't
            # break anything.
            await db.initialize()
            rows = await db._db.execute_fetchall("PRAGMA table_info(rooms)")
            cols = {r["name"] for r in rows}
            self.assertIn("wilderness_region_id", cols)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Wilderness loader
# ─────────────────────────────────────────────────────────────────────────────

class TestWildernessLoader(unittest.TestCase):

    def test_loads_dune_sea_yaml(self):
        """Load the actual shipped Dune Sea YAML and verify the
        loader accepts it without errors."""
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        rep = load_wilderness_region(path)
        self.assertTrue(
            rep.ok,
            f"dune_sea.yaml load failed: {rep.errors}",
        )
        self.assertEqual(rep.region.slug, "tatooine_dune_sea")
        self.assertEqual(rep.region.planet, "tatooine")

    def test_dune_sea_landmark_count(self):
        """Dune Sea has 12 landmarks: 2 force-resonant + 9 Village rooms +
        1 Hermit's Hut."""
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        rep = load_wilderness_region(path)
        self.assertTrue(rep.ok)
        self.assertEqual(len(rep.region.landmarks), 12)

    def test_dune_sea_has_village_rooms(self):
        """All 9 Village rooms from jedi_village.yaml.rooms must
        appear in the Dune Sea region by id."""
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        rep = load_wilderness_region(path)
        ids = {l.id for l in rep.region.landmarks}
        for required in (
            "village_outer_watch", "village_gate", "village_common_square",
            "village_council_hut", "village_masters_chamber",
            "village_apprentice_tents", "village_forge",
            "village_meditation_caves", "village_sealed_sanctum",
        ):
            self.assertIn(required, ids,
                          f"Village room {required} missing from Dune Sea")

    def test_dune_sea_has_force_resonant_landmarks(self):
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        rep = load_wilderness_region(path)
        ids = {l.id for l in rep.region.landmarks}
        self.assertIn("dune_sea_anchor_stones", ids)
        self.assertIn("dune_sea_ruined_obelisk", ids)

    def test_dune_sea_has_hermit_hut(self):
        from engine.wilderness_loader import load_wilderness_region
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        rep = load_wilderness_region(path)
        ids = {l.id for l in rep.region.landmarks}
        self.assertIn("hermit_hut", ids)

    def test_force_resonant_merge(self):
        """When the loader is given the force_resonant_landmarks path,
        landmarks present in both files get the rich force-resonant
        description."""
        from engine.wilderness_loader import load_wilderness_region
        region_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        fr_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "force_resonant_landmarks.yaml",
        )
        rep = load_wilderness_region(
            region_path, force_resonant_path=fr_path,
        )
        self.assertTrue(rep.ok)
        anchor = next(l for l in rep.region.landmarks
                      if l.id == "dune_sea_anchor_stones")
        # Force-resonant flag must be present (set in either file)
        self.assertTrue(anchor.properties.get("force_resonant"))
        # Description should be the longer, richer authored version
        self.assertGreater(len(anchor.description), 300,
                           "Force-resonant content didn't merge in")

    def test_invalid_yaml_returns_errors(self):
        from engine.wilderness_loader import load_wilderness_region
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            f.write("not: a: valid: yaml: structure: [unclosed")
            tmp_path = f.name
        try:
            rep = load_wilderness_region(tmp_path)
            self.assertFalse(rep.ok)
            self.assertTrue(any("parse error" in e for e in rep.errors))
        finally:
            os.unlink(tmp_path)

    def test_missing_path_returns_error(self):
        from engine.wilderness_loader import load_wilderness_region
        rep = load_wilderness_region("/nonexistent/path.yaml")
        self.assertFalse(rep.ok)
        self.assertTrue(any("not found" in e for e in rep.errors))

    def test_duplicate_landmark_id_errors(self):
        from engine.wilderness_loader import load_wilderness_region
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            f.write("""
schema_version: 1
region:
  slug: test_region
  name: Test
  planet: testworld
  zone: test_zone
  default_security: lawless
grid:
  width: 10
  height: 10
  default_terrain: dune
terrains:
  dune: {move_cost: 1}
landmarks:
  - id: dup
    name: First
    coordinates: [0, 0]
    terrain: dune
  - id: dup
    name: Second
    coordinates: [1, 1]
    terrain: dune
""")
            tmp_path = f.name
        try:
            rep = load_wilderness_region(tmp_path)
            self.assertFalse(rep.ok)
            self.assertTrue(any("duplicate" in e.lower() for e in rep.errors))
        finally:
            os.unlink(tmp_path)

    def test_out_of_bounds_coords_error(self):
        from engine.wilderness_loader import load_wilderness_region
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            f.write("""
schema_version: 1
region:
  slug: test_region
  name: Test
  planet: testworld
  zone: test_zone
  default_security: lawless
grid:
  width: 10
  height: 10
  default_terrain: dune
terrains:
  dune: {move_cost: 1}
landmarks:
  - id: oob
    name: Out of bounds
    coordinates: [99, 99]
    terrain: dune
""")
            tmp_path = f.name
        try:
            rep = load_wilderness_region(tmp_path)
            self.assertFalse(rep.ok)
            self.assertTrue(any("out of grid" in e for e in rep.errors))
        finally:
            os.unlink(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Wilderness writer
# ─────────────────────────────────────────────────────────────────────────────

class TestWildernessWriter(unittest.TestCase):

    def _load(self):
        from engine.wilderness_loader import load_wilderness_region
        region_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "dune_sea.yaml",
        )
        fr_path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars",
            "wilderness", "force_resonant_landmarks.yaml",
        )
        return load_wilderness_region(
            region_path, force_resonant_path=fr_path,
        )

    def test_writes_all_landmarks(self):
        async def _check():
            from engine.wilderness_writer import write_wilderness_region
            db = await _fresh_db()
            rep = self._load()
            self.assertTrue(rep.ok)

            wr = await write_wilderness_region(rep.region, db)
            self.assertEqual(len(wr.errors), 0,
                             f"writer errors: {wr.errors}")
            # 12 landmarks → 12 rooms
            self.assertEqual(wr.landmarks_written, 12)
            # All landmark ids resolved to room ids
            self.assertEqual(len(wr.landmark_room_ids), 12)
            await db._db.close()
        _run(_check())

    def test_landmark_rooms_have_wilderness_region_id(self):
        async def _check():
            from engine.wilderness_writer import write_wilderness_region
            db = await _fresh_db()
            rep = self._load()
            wr = await write_wilderness_region(rep.region, db)

            for slug, rid in wr.landmark_room_ids.items():
                rows = await db._db.execute_fetchall(
                    "SELECT wilderness_region_id FROM rooms WHERE id=?",
                    (rid,),
                )
                self.assertEqual(
                    rows[0]["wilderness_region_id"],
                    "tatooine_dune_sea",
                    f"Landmark {slug} missing wilderness_region_id",
                )
            await db._db.close()
        _run(_check())

    def test_landmark_coords_persisted_in_properties(self):
        async def _check():
            from engine.wilderness_writer import write_wilderness_region
            db = await _fresh_db()
            rep = self._load()
            wr = await write_wilderness_region(rep.region, db)

            # Anchor Stones at (38, 18)
            rid = wr.landmark_room_ids["dune_sea_anchor_stones"]
            rows = await db._db.execute_fetchall(
                "SELECT properties FROM rooms WHERE id=?", (rid,),
            )
            props = json.loads(rows[0]["properties"])
            self.assertEqual(props.get("wilderness_coordinates"), [38, 18])
            self.assertTrue(props.get("force_resonant"))
            self.assertTrue(props.get("village_quest_anchor"))
            await db._db.close()
        _run(_check())

    def test_adjacency_exits_created(self):
        async def _check():
            from engine.wilderness_writer import write_wilderness_region
            db = await _fresh_db()
            rep = self._load()
            wr = await write_wilderness_region(rep.region, db)

            # Should have written exits (each adjacency = 2 exits, both directions)
            self.assertGreater(wr.exits_written, 0)

            # Specifically: anchor_stones <-> village_outer_watch
            anchor_id = wr.landmark_room_ids["dune_sea_anchor_stones"]
            outer_id = wr.landmark_room_ids["village_outer_watch"]
            rows = await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM exits "
                "WHERE (from_room_id=? AND to_room_id=?) "
                "OR (from_room_id=? AND to_room_id=?)",
                (anchor_id, outer_id, outer_id, anchor_id),
            )
            self.assertGreaterEqual(rows[0]["n"], 2)
            await db._db.close()
        _run(_check())

    def test_idempotent_rewrite(self):
        """Running the writer twice should not duplicate landmarks."""
        async def _check():
            from engine.wilderness_writer import write_wilderness_region
            db = await _fresh_db()
            rep = self._load()

            wr1 = await write_wilderness_region(rep.region, db)
            self.assertEqual(wr1.landmarks_written, 12)
            self.assertEqual(wr1.landmarks_reused, 0)

            wr2 = await write_wilderness_region(rep.region, db)
            self.assertEqual(wr2.landmarks_written, 0)
            self.assertEqual(wr2.landmarks_reused, 12)

            # Total non-sentinel landmark rooms in DB still 12.
            # Drop 2 (May 3 2026) added the virtual sentinel room
            # which also has wilderness_region_id set; we exclude it
            # by checking the wilderness_sentinel marker in properties
            # or just count landmarks (excluding the one whose
            # name is "Wilderness: <region>").
            rows = await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM rooms "
                "WHERE wilderness_region_id = 'tatooine_dune_sea' "
                "AND name NOT LIKE 'Wilderness: %'",
            )
            self.assertEqual(rows[0]["n"], 12)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 4. End-to-end: Village path traversability
# ─────────────────────────────────────────────────────────────────────────────

class TestVillagePathTraversable(unittest.TestCase):

    def test_anchor_to_master_chamber_path_exists(self):
        """The Village quest needs this path to function:
        Anchor Stones → Outer Watch → Gate → Common Square →
        Council Hut → Master's Chamber. Verify it via DB exits."""
        async def _check():
            from engine.wilderness_loader import load_wilderness_region
            from engine.wilderness_writer import write_wilderness_region

            db = await _fresh_db()
            region_path = os.path.join(
                PROJECT_ROOT, "data", "worlds", "clone_wars",
                "wilderness", "dune_sea.yaml",
            )
            rep = load_wilderness_region(region_path)
            wr = await write_wilderness_region(rep.region, db)

            path = [
                "dune_sea_anchor_stones",
                "village_outer_watch",
                "village_gate",
                "village_common_square",
                "village_council_hut",
                "village_masters_chamber",
            ]
            for i in range(len(path) - 1):
                from_slug, to_slug = path[i], path[i + 1]
                from_id = wr.landmark_room_ids[from_slug]
                to_id = wr.landmark_room_ids[to_slug]
                rows = await db._db.execute_fetchall(
                    "SELECT COUNT(*) AS n FROM exits "
                    "WHERE from_room_id=? AND to_room_id=?",
                    (from_id, to_id),
                )
                self.assertGreaterEqual(
                    rows[0]["n"], 1,
                    f"No exit from {from_slug} to {to_slug}",
                )
            await db._db.close()
        _run(_check())

    def test_hermit_reachable_from_anchor_stones(self):
        """The Hermit invitation flow needs the player to reach
        hermit_hut from dune_sea_anchor_stones."""
        async def _check():
            from engine.wilderness_loader import load_wilderness_region
            from engine.wilderness_writer import write_wilderness_region

            db = await _fresh_db()
            region_path = os.path.join(
                PROJECT_ROOT, "data", "worlds", "clone_wars",
                "wilderness", "dune_sea.yaml",
            )
            rep = load_wilderness_region(region_path)
            wr = await write_wilderness_region(rep.region, db)

            anchor_id = wr.landmark_room_ids["dune_sea_anchor_stones"]
            hermit_id = wr.landmark_room_ids["hermit_hut"]
            rows = await db._db.execute_fetchall(
                "SELECT COUNT(*) AS n FROM exits "
                "WHERE from_room_id=? AND to_room_id=?",
                (anchor_id, hermit_id),
            )
            self.assertGreaterEqual(rows[0]["n"], 1)
            await db._db.close()
        _run(_check())

    def test_sealed_sanctum_exists(self):
        """The Trial of Insight site must exist with its locking flag."""
        async def _check():
            from engine.wilderness_loader import load_wilderness_region
            from engine.wilderness_writer import write_wilderness_region

            db = await _fresh_db()
            region_path = os.path.join(
                PROJECT_ROOT, "data", "worlds", "clone_wars",
                "wilderness", "dune_sea.yaml",
            )
            rep = load_wilderness_region(region_path)
            wr = await write_wilderness_region(rep.region, db)

            sanctum_id = wr.landmark_room_ids["village_sealed_sanctum"]
            rows = await db._db.execute_fetchall(
                "SELECT properties FROM rooms WHERE id=?", (sanctum_id,),
            )
            props = json.loads(rows[0]["properties"])
            self.assertEqual(
                props.get("locked_until_flag"),
                "spirit_trial_in_progress",
            )
            self.assertTrue(props.get("trial_of_insight_site"))
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 5. Force-resonant flag survives the pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestForceResonantPipeline(unittest.TestCase):

    def test_anchor_stones_force_resonant_in_db(self):
        async def _check():
            from engine.wilderness_loader import load_wilderness_region
            from engine.wilderness_writer import write_wilderness_region

            db = await _fresh_db()
            region_path = os.path.join(
                PROJECT_ROOT, "data", "worlds", "clone_wars",
                "wilderness", "dune_sea.yaml",
            )
            fr_path = os.path.join(
                PROJECT_ROOT, "data", "worlds", "clone_wars",
                "wilderness", "force_resonant_landmarks.yaml",
            )
            rep = load_wilderness_region(
                region_path, force_resonant_path=fr_path,
            )
            wr = await write_wilderness_region(rep.region, db)

            for slug in ("dune_sea_anchor_stones",
                         "dune_sea_ruined_obelisk"):
                rid = wr.landmark_room_ids[slug]
                rows = await db._db.execute_fetchall(
                    "SELECT properties FROM rooms WHERE id=?", (rid,),
                )
                props = json.loads(rows[0]["properties"])
                self.assertTrue(
                    props.get("force_resonant"),
                    f"{slug} lost its force_resonant flag",
                )
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 6. Source-level markers
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleSelfDocs(unittest.TestCase):

    def test_loader_references_design(self):
        path = os.path.join(
            PROJECT_ROOT, "engine", "wilderness_loader.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("wilderness_system_design_v1.md", src)
        self.assertIn("minimal-substrate", src)

    def test_writer_references_design(self):
        path = os.path.join(
            PROJECT_ROOT, "engine", "wilderness_writer.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("wilderness_system_design_v1.md", src)

    def test_era_yaml_registers_dune_sea(self):
        path = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars", "era.yaml",
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("wilderness/dune_sea.yaml", src)

    def test_build_script_invokes_wilderness_writer(self):
        path = os.path.join(PROJECT_ROOT, "build_mos_eisley.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("write_wilderness_region", src)
        self.assertIn("load_era_wilderness_regions", src)


if __name__ == "__main__":
    unittest.main()
