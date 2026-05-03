# -*- coding: utf-8 -*-
"""F.1d — Era switch regression tests.

After F.1a-c, build_mos_eisley.py has no GCW-specific literals; the era is
selected via the `era` kwarg on build(). F.1d adds the kwarg, era-guards
the GCW-specific seed-room linking, and proves CW builds end-to-end.

These tests are integration-level — they actually run build() against a
temp DB and assert on what landed.
"""
import asyncio
import os
import sqlite3
import tempfile

import pytest

from build_mos_eisley import build


def _run_build(era):
    """Run build() in a fresh temp DB, return path."""
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


# ──────────────────────────────────────────────────────────────────────────


class TestGcwBuildPostF1d:
    """GCW build remains identical to pre-F.1d behaviour."""

    @pytest.fixture(scope="class")
    def gcw_db(self):
        path = _run_build("gcw")
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_room_count(self, gcw_db):
        rows = _query(gcw_db, "SELECT COUNT(*) AS n FROM rooms")
        # F.0 Pass B baseline: 120 YAML + 7 ship bridges = 127 (per summary
        # box). DB row count includes 3 seed rooms created by
        # Database.initialize() before build() runs (Landing Pad / Street /
        # Cantina), so total = 130.
        assert rows[0]["n"] == 130

    def test_npc_count(self, gcw_db):
        rows = _query(gcw_db, "SELECT COUNT(*) AS n FROM npcs")
        # F.1a: 98 planet + 4 hireable = 102
        assert rows[0]["n"] == 102

    def test_ship_count(self, gcw_db):
        rows = _query(gcw_db, "SELECT COUNT(*) AS n FROM ships")
        assert rows[0]["n"] == 7

    def test_test_character_present(self, gcw_db):
        rows = _query(gcw_db, "SELECT name FROM characters WHERE name='Test Jedi'")
        assert len(rows) == 1

    def test_seed_room_linking_applied(self, gcw_db):
        """Seed room 1 (Landing Pad) gets a 'north' exit to spaceport row."""
        rows = _query(
            gcw_db,
            "SELECT direction FROM exits WHERE from_room_id=1 AND direction='north'"
        )
        assert len(rows) >= 1


class TestCloneWarsBuildPostF1d:
    """CW build runs end-to-end. NPC replacements apply. No seed-room
    linking (era != gcw). Hireable/ships/test-character files don't exist
    yet for CW — skipped without crashing."""

    @pytest.fixture(scope="class")
    def cw_db(self):
        path = _run_build("clone_wars")
        yield path
        if os.path.exists(path):
            os.unlink(path)

    def test_build_produced_rooms(self, cw_db):
        rows = _query(cw_db, "SELECT COUNT(*) AS n FROM rooms")
        # F.4 (Apr 30 2026) wired in 4 additional CW planets beyond the
        # original Tatooine + Nar Shaddaa pair: Coruscant, Kuat, Kamino,
        # Geonosis. CW build now produces ~256 rooms (was ~80 pre-F.4).
        # Still less than full GCW production build (which has Tatooine
        # only at full GG7 fidelity plus seed rooms).
        assert rows[0]["n"] > 200, (
            f"CW build produced {rows[0]['n']} rooms; expected > 200 "
            "post-F.4 (Tatooine + Nar Shaddaa + Coruscant + Kuat + "
            "Kamino + Geonosis)"
        )
        assert rows[0]["n"] < 400, (
            f"CW build produced {rows[0]['n']} rooms; expected < 400. "
            "If this fails high, a new planet was added to CW era.yaml "
            "content_refs.planets — bump the upper bound."
        )

    def test_cw_npcs_loaded(self, cw_db):
        """CW NPC roster is populated across all six player-facing planets.

        History: pre-CW.NPCS this was 8 (Vela Niree addition + 7
        Imperial replacements). The CW.NPCS track (May 2026) shipped
        eight content drops registering 7 planet-specific NPC YAMLs in
        ``data/worlds/clone_wars/era.yaml``: Mos Eisley, Coruscant
        Senate + Temple, Coruscant lower / Coco Town / Underworld,
        Kamino + Geonosis + Kuat civilians, Nar Shaddaa topside,
        Nar Shaddaa lower, and the Drop H combat templates seeded
        across multiple planets. Reality is now ~144 NPCs.

        We assert a generous floor (>120) rather than a hard equality
        because future content drops will move the number up; CW.NPCS
        is a content-lane track and the count grows without engine
        contracts changing. A regression *down* from this floor would
        signal a content-ref or loader regression worth investigating.
        """
        rows = _query(cw_db, "SELECT COUNT(*) AS n FROM npcs")
        n = rows[0]["n"]
        assert n > 120, (
            f"CW build produced {n} NPCs; expected > 120 post-CW.NPCS "
            "(8 content drops registered 7 planet-specific YAMLs in "
            "era.yaml). Did a content_ref get removed or did the "
            "replaces: protocol over-suppress?"
        )
        # Sanity ceiling — way above expected, just guards against
        # accidental duplicate-load loops.
        assert n < 1000, (
            f"CW build produced {n} NPCs; expected < 1000. "
            "Possible duplicate-load loop or runaway replicator NPC."
        )

    def test_cw_replacement_names_present(self, cw_db):
        """The Clone Trooper replacement loaded in place of Imperial Stormtrooper."""
        rows = _query(cw_db, "SELECT name FROM npcs WHERE name LIKE 'Clone Trooper%'")
        assert len(rows) >= 1

    def test_cw_no_imperial_stormtrooper(self, cw_db):
        """Imperial Stormtrooper is suppressed by the replaces: protocol."""
        rows = _query(
            cw_db,
            "SELECT name FROM npcs WHERE name='Imperial Stormtrooper'"
        )
        assert len(rows) == 0

    def test_cw_ships_loaded(self, cw_db):
        """CW docked-ship roster is populated.

        History: pre-CW.SHIPS this was 0 (no ``ships.yaml`` existed for
        CW). CW.SHIPS shipped a ``data/worlds/clone_wars/ships.yaml``
        roster of 7 era-correct ships (per memory + content_refs),
        registered via ``content_refs.ships`` in era.yaml. Reality is
        now 7 ships.

        We assert presence (> 0) and a reasonable ceiling rather than
        a hard equality so future ship additions don't immediately
        re-stale this test. A drop to 0 signals a content_refs or
        ship_loader regression.
        """
        rows = _query(cw_db, "SELECT COUNT(*) AS n FROM ships")
        n = rows[0]["n"]
        assert n > 0, (
            f"CW build produced 0 ships; expected > 0 post-CW.SHIPS "
            "(content_refs.ships in era.yaml should point at "
            "ships.yaml and ship_loader should populate the table)."
        )
        assert n < 100, (
            f"CW build produced {n} ships; expected < 100. "
            "Possible duplicate-load loop."
        )

    def test_cw_no_test_character(self, cw_db):
        """CW has no test_character.yaml yet — loader skips silently."""
        rows = _query(cw_db, "SELECT name FROM characters")
        # No test characters created — only a fresh world's tables.
        assert len(rows) == 0

    def test_cw_seed_rooms_not_linked(self, cw_db):
        """Era != gcw: the GCW seed-room linking is skipped, so seed
        room 1 (which Database.initialize() creates) won't have the
        north→spaceport exit applied."""
        rows = _query(
            cw_db,
            """SELECT e.direction FROM exits e
               WHERE e.from_room_id=1 AND e.direction='north'
               AND e.to_room_id IN (SELECT id FROM rooms
                                     WHERE name LIKE '%Spaceport Row%')"""
        )
        assert len(rows) == 0


class TestBuildSignature:
    """The build() signature is the F.1d contract surface."""

    def test_default_era_is_gcw(self):
        import inspect
        sig = inspect.signature(build)
        assert "era" in sig.parameters
        assert sig.parameters["era"].default == "gcw"

    def test_db_path_default_unchanged(self):
        import inspect
        sig = inspect.signature(build)
        assert sig.parameters["db_path"].default == "sw_mush.db"
