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
        """CW loads at least the foundational additions + replacements roster.

        Originally asserted == 8 (Drop A: 1 addition + 7 replacements). The
        CW.NPCS sweep through Drop H + C1 + DEF + G1/G2 + B + C2 grew the
        roster well past 100; F.6 (Hermit) adds a wilderness-anchored NPC.
        Generous lower bound catches a real regression (CW NPC pipeline
        broken / replacement protocol stripped roster to nothing) without
        re-staling on every additive content drop. Same pattern as the
        PG.1 schema-version fix in F.5.
        """
        rows = _query(cw_db, "SELECT COUNT(*) AS n FROM npcs")
        # Sanity: at least the foundational 8 (Drop A) and at most a
        # large generous ceiling that catches accidental cross-era leakage.
        assert rows[0]["n"] >= 8, (
            f"CW build produced {rows[0]['n']} NPCs; expected at least 8 "
            "(Drop A foundational additions + replacements). If lower, "
            "the CW NPC pipeline has regressed."
        )
        assert rows[0]["n"] < 1000, (
            f"CW build produced {rows[0]['n']} NPCs; expected < 1000. "
            "If this fails high, GG7 base may be leaking into CW era "
            "or content_refs.npcs has accidentally referenced a "
            "GCW-only roster."
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

    def test_cw_no_ships_loaded(self, cw_db):
        """CW ships count: was 0 pre-CW.SHIPS, now ~7 post-CW.SHIPS.

        Per HANDOFF_FOR_COMPACTION_MAY1 / userMemory: CW.SHIPS landed
        with 7 ships across the four player-facing CW planets. This
        test originally asserted == 0; relaxed to a generous ceiling
        so it catches accidental GCW-ship leakage without re-staling
        on every additive ship drop.
        """
        rows = _query(cw_db, "SELECT COUNT(*) AS n FROM ships")
        # Generous ceiling: the GCW production build has many more
        # ships than CW; a count > 100 would indicate cross-era leakage.
        assert rows[0]["n"] < 100, (
            f"CW build produced {rows[0]['n']} ships; expected < 100. "
            "If this fails high, GCW ship roster may be leaking into CW."
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
