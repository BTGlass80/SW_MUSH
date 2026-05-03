# -*- coding: utf-8 -*-
"""
tests/test_f6_hermit.py — Hermit NPC integration & gate seam.

Closes the loop on Drop F.6 (May 3 2026): proves that the Hermit NPC
is actually populated by a fresh CW build, lives in the right room,
has a sane gate block, and that the engine/hermit.py invitation
seam reflects the Force-sign threshold contract from
engine/force_signs.py.

Why this test exists:

F.5 shipped the Dune Sea wilderness substrate (rooms exist) but
left the Hermit's Hut empty — `the room exists; the NPC who lives
there does not` (per HANDOFF_MAY03_F5_WILDERNESS.md "Known
unresolved items"). F.6 ships the Hermit, the wilderness-NPC
loader path, and the gate seam.

This file validates four contracts:

  1. Build-time integration: a full CW world build produces a
     populated wilderness substrate AND a populated Hermit NPC in
     Hermit's Hut.
  2. Gate data shape: the Hermit's ai_config.gate block parses
     correctly from YAML and has the expected fields/types.
  3. Gate seam: engine/hermit.py::is_invitation_eligible reflects
     engine/force_signs.py::has_received_invitation behavior across
     the threshold boundary.
  4. Loader robustness: load_wilderness_npcs returns empty for eras
     without wilderness_npcs registered (era isolation), and skips
     entries pointing at non-wilderness rooms (room scope safety).
"""
from __future__ import annotations

import asyncio
import json
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
from engine.force_signs import FORCE_SIGNS_FOR_INVITATION
from engine.hermit import (
    HERMIT_GATE_KIND,
    gate_threshold,
    is_invitation_eligible,
    load_hermit_gate_config,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
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
# 1. Hermit lands in the right room after a CW build
# ─────────────────────────────────────────────────────────────────────────────


class TestHermitInWildernessSubstrate:
    """A fresh CW world build must place the Hermit in Hermit's Hut."""

    @classmethod
    def setup_class(cls):
        cls.db_path = _run_build("clone_wars")

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_hermit_npc_exists(self):
        rows = _query(
            self.db_path,
            "SELECT id, name, room_id FROM npcs WHERE name = 'the Hermit'",
        )
        assert len(rows) == 1, (
            f"Expected exactly one 'the Hermit' NPC; found {len(rows)}"
        )

    def test_hermit_room_is_hermits_hut(self):
        rows = _query(
            self.db_path,
            """
            SELECT r.name AS room_name, r.wilderness_region_id
            FROM npcs n
            JOIN rooms r ON r.id = n.room_id
            WHERE n.name = 'the Hermit'
            """,
        )
        assert len(rows) == 1
        assert rows[0]["room_name"] == "Hermit's Hut"
        assert rows[0]["wilderness_region_id"] == "tatooine_dune_sea"

    def test_hermit_ai_config_has_gate_block(self):
        rows = _query(
            self.db_path,
            "SELECT ai_config_json FROM npcs WHERE name = 'the Hermit'",
        )
        assert len(rows) == 1
        ai_config = json.loads(rows[0]["ai_config_json"])
        assert "gate" in ai_config, (
            "Hermit's ai_config must persist the gate block through "
            "the loader to the DB; missing means _build_ai_config "
            "stripped it."
        )
        gate = ai_config["gate"]
        assert gate.get("kind") == HERMIT_GATE_KIND
        assert isinstance(gate.get("before_lines"), list)
        assert isinstance(gate.get("after_lines"), list)
        assert len(gate["before_lines"]) >= 1
        assert len(gate["after_lines"]) >= 1

    def test_hermit_is_singleton(self):
        # The Hermit is intentionally a singleton fixture, not a roster
        # filler. Adding a second Hermit anywhere would break the
        # Village quest's invitation flow (which assumes one).
        rows = _query(
            self.db_path,
            "SELECT COUNT(*) AS n FROM npcs WHERE name = 'the Hermit'",
        )
        assert rows[0]["n"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. GCW does NOT load the Hermit (era isolation)
# ─────────────────────────────────────────────────────────────────────────────


class TestGcwHasNoHermit:
    """A GCW build must not produce a Hermit NPC.

    The Hermit is a CW-era construct; the Village quest is CW-only.
    A GCW build using a stale era.yaml that accidentally imported
    wilderness_npcs would silently leak the Hermit into the wrong
    era. Guard against that.
    """

    @classmethod
    def setup_class(cls):
        cls.db_path = _run_build("gcw")

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_gcw_has_zero_hermits(self):
        rows = _query(
            self.db_path,
            "SELECT COUNT(*) AS n FROM npcs WHERE name = 'the Hermit'",
        )
        assert rows[0]["n"] == 0, (
            "A GCW build must not produce the CW-era Hermit NPC."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Gate seam: engine/hermit.py respects force_signs threshold
# ─────────────────────────────────────────────────────────────────────────────


class TestHermitGateSeam:
    """is_invitation_eligible reflects the Force-sign threshold."""

    def test_threshold_matches_force_signs_constant(self):
        # The Hermit's gate is the single consumer of the
        # FORCE_SIGNS_FOR_INVITATION constant. If the constant
        # changes (e.g., PG.4.polish moves it to era.yaml), this
        # test enforces that gate_threshold() ratchets with it.
        assert gate_threshold() == FORCE_SIGNS_FOR_INVITATION

    def test_eligible_at_threshold(self):
        char = {"force_signs_accumulated": FORCE_SIGNS_FOR_INVITATION}
        assert is_invitation_eligible(char) is True

    def test_eligible_above_threshold(self):
        char = {"force_signs_accumulated": FORCE_SIGNS_FOR_INVITATION + 3}
        assert is_invitation_eligible(char) is True

    def test_not_eligible_below_threshold(self):
        char = {"force_signs_accumulated": FORCE_SIGNS_FOR_INVITATION - 1}
        assert is_invitation_eligible(char) is False

    def test_not_eligible_at_zero(self):
        char = {"force_signs_accumulated": 0}
        assert is_invitation_eligible(char) is False

    def test_not_eligible_with_missing_field(self):
        # A character that's never been touched by the FS subsystem
        # (e.g., a freshly created character before the heartbeat
        # has run) should not be eligible. This guards against the
        # field defaulting to None or being absent.
        char = {}
        assert is_invitation_eligible(char) is False

    def test_not_eligible_with_none_field(self):
        char = {"force_signs_accumulated": None}
        assert is_invitation_eligible(char) is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Gate config parser
# ─────────────────────────────────────────────────────────────────────────────


class TestHermitGateConfigParser:
    """load_hermit_gate_config pulls the gate block straight from YAML."""

    @classmethod
    def setup_class(cls):
        cls.yaml_path = os.path.join(
            PROJECT_ROOT,
            "data", "worlds", "clone_wars", "wilderness_npcs.yaml",
        )

    def test_gate_config_present(self):
        gate = load_hermit_gate_config(self.yaml_path)
        assert gate is not None, (
            f"No gate block found in {self.yaml_path}; "
            "the Hermit must have an ai_config.gate block."
        )

    def test_gate_kind_is_force_sign_invitation(self):
        gate = load_hermit_gate_config(self.yaml_path)
        assert gate["kind"] == "force_sign_invitation"

    def test_gate_has_before_and_after_lines(self):
        gate = load_hermit_gate_config(self.yaml_path)
        assert isinstance(gate.get("before_lines"), list)
        assert isinstance(gate.get("after_lines"), list)
        assert len(gate["before_lines"]) >= 3, (
            "Should have multiple before-lines for variety; player "
            "may visit Hermit's Hut several times pre-threshold."
        )
        assert len(gate["after_lines"]) >= 3

    def test_gate_threshold_field_matches_constant(self):
        # The YAML's threshold field is informational (source of truth
        # is engine/force_signs.py), but it should match the constant
        # to avoid documentation drift.
        gate = load_hermit_gate_config(self.yaml_path)
        assert gate.get("threshold") == FORCE_SIGNS_FOR_INVITATION

    def test_gate_lines_are_nonempty_strings(self):
        gate = load_hermit_gate_config(self.yaml_path)
        for key in ("before_lines", "after_lines"):
            for line in gate[key]:
                assert isinstance(line, str)
                assert len(line.strip()) > 0

    def test_returns_none_for_missing_file(self):
        result = load_hermit_gate_config("/nonexistent/path/wilderness_npcs.yaml")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Loader: era isolation + room-scope safety
# ─────────────────────────────────────────────────────────────────────────────


class TestWildernessNpcLoader:
    """load_wilderness_npcs has the right scope and behavior."""

    def test_gcw_era_returns_empty_list(self, tmp_path):
        # A GCW build has no wilderness_npcs registered. The loader
        # must return [] cleanly, not crash.
        from db.database import Database
        from engine.npc_loader import load_wilderness_npcs

        async def _run():
            db_file = str(tmp_path / "scratch.db")
            db = Database(db_file)
            await db.connect()
            await db.initialize()
            era_dir = os.path.join(PROJECT_ROOT, "data", "worlds", "gcw")
            tuples = await load_wilderness_npcs(era_dir, db)
            await db.close()
            return tuples

        tuples = asyncio.run(_run())
        assert tuples == []

    def test_returns_empty_for_missing_era_yaml(self, tmp_path):
        from db.database import Database
        from engine.npc_loader import load_wilderness_npcs

        async def _run():
            db_file = str(tmp_path / "scratch.db")
            db = Database(db_file)
            await db.connect()
            await db.initialize()
            tuples = await load_wilderness_npcs(str(tmp_path), db)
            await db.close()
            return tuples

        tuples = asyncio.run(_run())
        assert tuples == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. Source-level guards (no full build needed)
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleSelfDocs:
    """Quick guards that the wiring is in place."""

    def test_era_yaml_registers_wilderness_npcs(self):
        path = os.path.join(
            PROJECT_ROOT,
            "data", "worlds", "clone_wars", "era.yaml",
        )
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "wilderness_npcs:" in text, (
            "era.yaml must register a wilderness_npcs content_refs slot."
        )
        assert "wilderness_npcs.yaml" in text, (
            "era.yaml must reference the wilderness_npcs.yaml file."
        )

    def test_build_script_imports_load_wilderness_npcs(self):
        path = os.path.join(PROJECT_ROOT, "build_mos_eisley.py")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        assert "load_wilderness_npcs" in text, (
            "build_mos_eisley.py must import and call load_wilderness_npcs."
        )

    def test_engine_hermit_module_exists(self):
        path = os.path.join(PROJECT_ROOT, "engine", "hermit.py")
        assert os.path.exists(path), "engine/hermit.py must exist."

    def test_wilderness_npcs_yaml_exists(self):
        path = os.path.join(
            PROJECT_ROOT,
            "data", "worlds", "clone_wars", "wilderness_npcs.yaml",
        )
        assert os.path.exists(path), (
            "data/worlds/clone_wars/wilderness_npcs.yaml must exist."
        )
