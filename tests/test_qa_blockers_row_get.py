# -*- coding: utf-8 -*-
"""QA blockers — B1/B2/B3 (docs/design/QA_FINDINGS_2026-06-16.md).

These run against a REAL ``Database`` (not a dict-returning stub) — which is the
exact gap that hid B1: the suite's DB stubs convert rows to dicts, so the
production ``aiosqlite.Row`` (== ``sqlite3.Row``, which has NO ``.get()``) was
never exercised, and ~163 ``row.get(...)`` call sites silently crashed in
production while the suite stayed green.
"""
import pathlib

import pytest

from db.database import Database, _dict_row_factory

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent


async def _mkdb(tmp_path) -> Database:
    db = Database(str(tmp_path / "qa.db"))
    await db.connect()
    await db.initialize()
    return db


# ── B1: reads return dict rows that support .get() (the root fix) ──────────

async def test_fetchone_row_supports_get(tmp_path):
    db = await _mkdb(tmp_path)
    try:
        acct_id = await db.create_account("reader", "password123")
        row = await db.fetchone(
            "SELECT username FROM accounts WHERE id=?", (acct_id,))
        # .get() must work — a raw sqlite3.Row raises AttributeError here (B1).
        assert row.get("username") == "reader"
        assert row.get("nope", "dflt") == "dflt"
        assert row["username"] == "reader"          # named access still works
        assert isinstance(row, dict)
    finally:
        await db.close()


async def test_fetchall_rows_support_get(tmp_path):
    db = await _mkdb(tmp_path)
    try:
        await db.create_account("a", "password123")
        rows = await db.fetchall("SELECT username FROM accounts")
        assert rows
        assert all(hasattr(r, "get") for r in rows)
        assert rows[0].get("username")
    finally:
        await db.close()


async def test_read_pool_rows_support_get(tmp_path):
    db = await _mkdb(tmp_path)
    try:
        await db.create_account("b", "password123")
        row = await db.read_fetchone("SELECT username FROM accounts LIMIT 1")
        assert row.get("username") == "b"
        assert isinstance(row, dict)
    finally:
        await db.close()


async def test_get_wound_state_cluster_does_not_raise(tmp_path):
    # get_wound_state calls row.get() on a real row -> AttributeError pre-B1.
    from engine.character import Character
    db = await _mkdb(tmp_path)
    try:
        acct_id = await db.create_account("wounded", "password123")
        char = Character(name="Woundy", species_name="Human")
        char_id = await db.create_character(acct_id, char.to_db_dict())
        state, clear_at = await db.get_wound_state(char_id)   # must not raise
        assert state in ("healthy", "wounded")
        assert isinstance(clear_at, float)
    finally:
        await db.close()


def test_dict_row_factory_keys_by_column_name():
    # Unit-level: the factory maps cursor.description names -> values.
    class _Col:
        def __init__(self, n): self._n = n
        def __getitem__(self, i): return self._n if i == 0 else None
    class _Cursor:
        description = [_Col("a"), _Col("b")]
    out = _dict_row_factory(_Cursor(), ("x", 7))
    assert out == {"a": "x", "b": 7}
    assert out.get("a") == "x"


# ── B2: NPC `vendor` flag survives the load into ai_config (vendors live) ──

class TestB2VendorPassthrough:
    def test_vendor_flag_passed_through(self):
        from engine.npc_loader import _build_ai_config
        cfg = _build_ai_config({"vendor": True}, name="Kayson")
        assert cfg.get("vendor")

    def test_no_vendor_flag_absent(self):
        from engine.npc_loader import _build_ai_config
        cfg = _build_ai_config({}, name="Civilian")
        assert not cfg.get("vendor")


# ── B3: faction comms resolve membership from faction_id (reach recipients) ─

class TestB3FactionId:
    def test_faction_id_resolves(self):
        from server.channels import get_faction
        # Real member: faction_id set, NO top-level 'faction' key (the live shape).
        assert get_faction({"faction_id": "republic"}) == "republic"

    def test_faction_id_independent_falls_through(self):
        from server.channels import get_faction
        assert get_faction({"faction_id": "independent"}) == "independent"

    def test_legacy_faction_key_still_works(self):
        from server.channels import get_faction
        assert get_faction({"faction": "cis"}) == "cis"

    def test_faction_id_preferred_over_nothing(self):
        from server.channels import get_faction
        # No faction_id, no faction key, empty attrs -> independent.
        assert get_faction({"attributes": "{}"}) == "independent"
