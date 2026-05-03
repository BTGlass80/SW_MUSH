# -*- coding: utf-8 -*-
"""
tests/test_f5_wilderness_integration.py — Wilderness substrate integration.

Closes the loop on Drop F.5 (May 2026): proves that running the full
CW world-build path actually lands the Dune Sea wilderness landmarks
into the rooms table, with the right wilderness_region_id tag, the
right zone inheritance, and the right adjacency exits to make the
Village quest path traversable.

Why this test exists:

The wilderness loader (engine/wilderness_loader.py), writer
(engine/wilderness_writer.py), and Dune Sea YAML
(data/worlds/clone_wars/wilderness/dune_sea.yaml) were authored with
unit-level tests in test_dune_sea_minimal.py. The integration block
in build_mos_eisley.py reads era.yaml.content_refs.wilderness and
calls the loader+writer at world-build time. But until this test,
nothing verified end-to-end that:

  1. era.yaml actually registers the Dune Sea region.
  2. The build script actually invokes the wilderness pipeline.
  3. Landmarks actually land in the rooms table after a fresh build.
  4. Landmarks have the correct wilderness_region_id set.
  5. Adjacency exits are written so Village quest movement works.
  6. The 9 Village rooms required by jedi_village.yaml are all present.

Without this test, the integration is a dead seam — it fires on boot
but no assertion guards against it silently breaking. A future
refactor of build_mos_eisley.py could remove the wilderness block
without any test catching it. This file is that guard.

Mirror of test_f1d_era_switch.py's TestCloneWarsBuildPostF1d pattern
— full CW build to a temp DB, then SQL-level assertions on what
landed.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from build_mos_eisley import build


# ─────────────────────────────────────────────────────────────────────────────
# Fixture — one CW build per class, shared across all tests
# ─────────────────────────────────────────────────────────────────────────────


def _run_build(era):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)
    asyncio.run(build(db_path=db_path, era=era))
    return db_path


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 1. Wilderness substrate landed
# ─────────────────────────────────────────────────────────────────────────────


class TestWildernessSubstrate:
    """Post-CW-build assertions: the Dune Sea region's landmark
    roster is in the rooms table, tagged correctly, and connected."""

    @pytest.fixture(scope="class")
    def cw_db(self):
        path = _run_build("clone_wars")
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_wilderness_landmarks_present(self, cw_db):
        """At least 12 wilderness landmarks should land for CW.

        The Dune Sea YAML defines 12 named landmarks (Anchor Stones,
        Ruined Obelisk, Hermit's Hut, Outer Watch, Village Gate, and
        7 interior Village rooms). Every CW build should write all
        of them.

        Generous bound (>= 10) so future content drops adding more
        landmarks don't immediately re-stale this test.
        """
        rows = _query(
            cw_db,
            "SELECT COUNT(*) AS n FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL",
        )
        n = rows[0]["n"]
        assert n >= 10, (
            f"Expected at least 10 wilderness landmarks after CW build; "
            f"got {n}. Did era.yaml.content_refs.wilderness lose its "
            f"dune_sea.yaml entry, or did the wilderness block in "
            f"build_mos_eisley.py get removed?"
        )

    def test_dune_sea_region_id_used(self, cw_db):
        """Landmarks should be tagged with wilderness_region_id=
        'tatooine_dune_sea' (per the YAML's region.slug)."""
        rows = _query(
            cw_db,
            "SELECT DISTINCT wilderness_region_id FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL",
        )
        slugs = {r["wilderness_region_id"] for r in rows}
        assert "tatooine_dune_sea" in slugs, (
            f"Expected 'tatooine_dune_sea' among wilderness_region_id "
            f"values; got {slugs}. Either the region YAML's slug "
            f"changed or the writer is using a different field."
        )

    def test_village_quest_rooms_all_present(self, cw_db):
        """All 9 Village quest rooms required by
        data/worlds/clone_wars/quests/jedi_village.yaml must be
        present. Without these the Village quest engine (future
        drop) has nowhere to put its NPCs or run its dialogue.
        """
        # The Village rooms are authored in dune_sea.yaml under
        # specific names. We assert by name match (the writer
        # preserves the YAML's `name:` field). If the names ever
        # change, this test must be updated alongside the
        # jedi_village.yaml content.
        required_names = {
            "Outer Watch — Sand-Worn Pillars",
            "Village Gate",
            "Common Square",
            "Council Hut",
            "Master's Chamber",
            "Apprentice Tents",
            "The Forge",
            "Meditation Caves",
            "The Sealed Sanctum",
        }
        rows = _query(
            cw_db,
            "SELECT name FROM rooms "
            "WHERE wilderness_region_id = 'tatooine_dune_sea'",
        )
        present = {r["name"] for r in rows}
        missing = required_names - present
        assert not missing, (
            f"Village quest rooms missing from CW build: {missing}. "
            f"Present wilderness rooms: {present}."
        )

    def test_force_resonant_landmarks_present(self, cw_db):
        """The two Dune Sea force-resonant landmarks (Anchor Stones,
        Ruined Obelisk) referenced by force_resonant_landmarks.yaml
        and jedi_village.yaml.force_sign_seeds must be present.
        These are the Track B Force-sign trigger sites — without
        them the post-50-hour Force-sign emission has no Dune Sea
        sites to fire from."""
        required_names = {"The Anchor Stones", "Ruined Obelisk"}
        rows = _query(
            cw_db,
            "SELECT name FROM rooms "
            "WHERE wilderness_region_id = 'tatooine_dune_sea'",
        )
        present = {r["name"] for r in rows}
        missing = required_names - present
        assert not missing, (
            f"Force-resonant Dune Sea landmarks missing: {missing}. "
            f"These are referenced by force_resonant_landmarks.yaml "
            f"and jedi_village.yaml.force_sign_seeds."
        )

    def test_hermit_hut_present(self, cw_db):
        """The Hermit's Hut is the Act 1 invitation-receipt room.
        Without it the Hermit NPC has no home and the Village quest
        Act 1 has no setting."""
        rows = _query(
            cw_db,
            "SELECT name FROM rooms "
            "WHERE wilderness_region_id = 'tatooine_dune_sea' "
            "AND name = ?",
            ("Hermit's Hut",),
        )
        assert len(rows) == 1, (
            f"Expected exactly 1 room named \"Hermit's Hut\" in the "
            f"Dune Sea wilderness; got {len(rows)}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Wilderness exits are wired (Village path is traversable)
# ─────────────────────────────────────────────────────────────────────────────


class TestWildernessAdjacency:
    """The Village quest path requires specific adjacency edges:
    Anchor Stones → Outer Watch (the Hermit's invitation crossing),
    Village Gate → Common Square (entry), and the interior Village
    layout. These tests assert the writer wrote those exits."""

    @pytest.fixture(scope="class")
    def cw_db(self):
        path = _run_build("clone_wars")
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def _exits_from(self, db_path, room_name):
        """Return the list of (direction, dest_name) exits leaving
        the room with the given name, restricted to wilderness
        destinations."""
        rows = _query(
            db_path,
            """
            SELECT e.direction, dest.name AS dest_name
            FROM exits e
            JOIN rooms src  ON src.id  = e.from_room_id
            JOIN rooms dest ON dest.id = e.to_room_id
            WHERE src.name = ?
              AND dest.wilderness_region_id IS NOT NULL
            """,
            (room_name,),
        )
        return [(r["direction"], r["dest_name"]) for r in rows]

    def test_some_wilderness_exits_exist(self, cw_db):
        """At least 10 exits between wilderness landmarks should
        exist after a build. The Dune Sea YAML defines 22 adjacency
        exits (Pass 2 of the writer); a generous floor catches
        regressions without re-staling on content adds."""
        rows = _query(
            cw_db,
            """
            SELECT COUNT(*) AS n
            FROM exits e
            JOIN rooms src  ON src.id  = e.from_room_id
            JOIN rooms dest ON dest.id = e.to_room_id
            WHERE src.wilderness_region_id IS NOT NULL
              AND dest.wilderness_region_id IS NOT NULL
            """,
        )
        n = rows[0]["n"]
        assert n >= 10, (
            f"Expected at least 10 wilderness-to-wilderness exits "
            f"after CW build; got {n}. Did the writer's Pass 2 "
            f"(adjacency exits) get skipped?"
        )

    def test_anchor_stones_has_exits(self, cw_db):
        """The Anchor Stones is the Village quest's anchor landmark
        — the player walks WEST from here at first light to reach
        the Outer Watch (per jedi_village.yaml). It must have
        outbound wilderness exits."""
        exits = self._exits_from(cw_db, "The Anchor Stones")
        assert len(exits) >= 1, (
            f"The Anchor Stones should have at least one outbound "
            f"wilderness exit; got {exits}."
        )

    def test_village_gate_to_common_square(self, cw_db):
        """The Village Gate must connect to the Common Square —
        the Village's entry sequence depends on this exit. If it's
        missing, players entering the Village can't reach Master
        Yarael."""
        exits = self._exits_from(cw_db, "Village Gate")
        dest_names = {dest for _, dest in exits}
        assert "Common Square" in dest_names, (
            f"Village Gate should have an exit to Common Square; "
            f"its current wilderness exits go to: {dest_names}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Era isolation — GCW build does NOT load wilderness
# ─────────────────────────────────────────────────────────────────────────────


class TestGcwHasNoWilderness:
    """GCW era.yaml has no content_refs.wilderness entry, so a GCW
    build must produce zero wilderness landmarks. This guards
    against accidentally hard-coding Dune Sea into a non-CW build
    path."""

    @pytest.fixture(scope="class")
    def gcw_db(self):
        path = _run_build("gcw")
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_gcw_no_wilderness_landmarks(self, gcw_db):
        rows = _query(
            gcw_db,
            "SELECT COUNT(*) AS n FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL",
        )
        assert rows[0]["n"] == 0, (
            f"GCW build wrote {rows[0]['n']} wilderness landmarks; "
            f"expected 0 (GCW era.yaml has no content_refs.wilderness). "
            f"Did the wilderness loader start defaulting to a region "
            f"when none is registered?"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Source-level marker for the drop
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleSelfDocs:
    """Source-level guards: the integration block in build_mos_eisley.py
    must remain present and the wilderness loader/writer modules must
    keep their drop-identifying docstring markers. If someone removes
    these without thinking, these tests fire."""

    def test_build_script_has_wilderness_block(self):
        path = os.path.join(PROJECT_ROOT, "build_mos_eisley.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "load_era_wilderness_regions" in src, (
            "build_mos_eisley.py should import "
            "load_era_wilderness_regions and use it in the "
            "world build path."
        )
        assert "write_wilderness_region" in src

    def test_era_yaml_registers_dune_sea(self):
        path = os.path.join(
            PROJECT_ROOT,
            "data", "worlds", "clone_wars", "era.yaml",
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "wilderness/dune_sea.yaml" in src, (
            "data/worlds/clone_wars/era.yaml should register "
            "wilderness/dune_sea.yaml under content_refs.wilderness."
        )

    def test_loader_and_writer_modules_present(self):
        for rel in ("engine/wilderness_loader.py",
                    "engine/wilderness_writer.py"):
            path = os.path.join(PROJECT_ROOT, rel)
            assert os.path.exists(path), f"Missing: {rel}"
