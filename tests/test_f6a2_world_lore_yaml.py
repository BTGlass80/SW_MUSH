# -*- coding: utf-8 -*-
"""
tests/test_f6a2_world_lore_yaml.py — F.6a.2 + F.6a.7 Phase 2 tests

Exercises engine/world_lore.py's era-aware seeding path:
    seed_lore(db, era=None)     -> defaults to "gcw" YAML (Phase 2 change)
    seed_lore(db, era="gcw")    -> loads from data/worlds/gcw/lore.yaml
    seed_lore(db, era="clone_wars") -> loads from data/worlds/clone_wars/lore.yaml
    seed_lore_from_corpus(db, corpus) -> int

Pre-F.6a.7 Phase 2 (Apr 29 2026), era=None routed through an in-Python
SEED_ENTRIES literal (~490 lines, 61 entries) and YAML load failures
silently fell back to that literal. Phase 2 deleted SEED_ENTRIES; era=None
now defaults to "gcw" and YAML load failures log ERROR + return 0 (no
in-Python fallback).
"""
import asyncio
import logging
import os
import sys
import unittest
from pathlib import Path

import aiosqlite

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.world_loader import (  # noqa: E402
    load_era_manifest, load_lore, LoreCorpus, LoreEntry, ValidationReport,
)
from engine.world_lore import (  # noqa: E402
    ensure_lore_schema, seed_lore, seed_lore_from_corpus, clear_cache,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fake DB
# ══════════════════════════════════════════════════════════════════════════════


class FakeDB:
    def __init__(self):
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        self._conn = await aiosqlite.connect(":memory:")
        self._conn.row_factory = aiosqlite.Row

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()):
        await self._conn.execute(sql, params)

    async def fetchall(self, sql: str, params: tuple = ()):
        cur = await self._conn.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]

    async def fetchone(self, sql: str, params: tuple = ()):
        cur = await self._conn.execute(sql, params)
        r = await cur.fetchone()
        return dict(r) if r else None

    async def commit(self):
        await self._conn.commit()


class _LoreSeedTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = FakeDB()
        await self.db.connect()
        await ensure_lore_schema(self.db)
        clear_cache()

    async def asyncTearDown(self):
        await self.db.close()
        clear_cache()

    async def _all_titles(self) -> set[str]:
        rows = await self.db.fetchall("SELECT title FROM world_lore")
        return {r["title"] for r in rows}

    async def _all_rows(self) -> list[dict]:
        rows = await self.db.fetchall("SELECT * FROM world_lore")
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# Default-path behavior — era=None now defaults to GCW YAML
# ══════════════════════════════════════════════════════════════════════════════


class TestDefaultPath(_LoreSeedTestBase):
    """Pre-F.6a.7 Phase 2, era=None loaded from in-Python SEED_ENTRIES.
    Phase 2 deleted that literal; era=None now defaults to "gcw" and
    sources data from data/worlds/gcw/lore.yaml.
    """

    async def test_era_none_defaults_to_gcw(self):
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "lore.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/lore.yaml not present")

        none_count = await seed_lore(self.db, era=None)
        none_titles = await self._all_titles()

        await self.db.execute("DELETE FROM world_lore")
        await self.db.commit()
        clear_cache()

        gcw_count = await seed_lore(self.db, era="gcw")
        gcw_titles = await self._all_titles()

        self.assertEqual(none_count, gcw_count,
                         "era=None must default to era='gcw' and produce "
                         "the same row count")
        self.assertEqual(none_titles, gcw_titles,
                         "era=None must seed the same titles as era='gcw'")

    async def test_era_none_seeds_canonical_gcw_entries(self):
        """era=None must seed at least the canonical GCW lore entries."""
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "lore.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/lore.yaml not present")

        count = await seed_lore(self.db, era=None)
        self.assertGreater(count, 0)
        titles = await self._all_titles()
        # Sanity: a known-canonical GCW lore entry from the original
        # SEED_ENTRIES list — must still be present in the YAML.
        self.assertIn("The Galactic Empire", titles,
                      "GCW lore.yaml should contain 'The Galactic Empire' "
                      "(canonical entry preserved through F.6a.7 deletion)")

    async def test_seed_lore_default_arg_works(self):
        """server/game_server.py historically called seed_lore(self.db)
        with no era kwarg. Backward compat: still works."""
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "lore.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/lore.yaml not present")
        count = await seed_lore(self.db)  # no kwarg, no positional
        self.assertGreater(count, 0)


# ══════════════════════════════════════════════════════════════════════════════
# Era path — Clone Wars + idempotency
# ══════════════════════════════════════════════════════════════════════════════


class TestCloneWarsErapath(_LoreSeedTestBase):
    async def test_clone_wars_loads_at_least_32_entries(self):
        cw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
                   "lore.yaml")
        if not cw_yaml.is_file():
            self.skipTest("data/worlds/clone_wars/lore.yaml not present")
        count = await seed_lore(self.db, era="clone_wars")
        self.assertGreaterEqual(
            count, 32,
            "CW lore.yaml must contain ≥ 32 entries (per design §8.2 target)"
        )

    async def test_seed_lore_idempotent_on_clone_wars(self):
        cw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
                   "lore.yaml")
        if not cw_yaml.is_file():
            self.skipTest("data/worlds/clone_wars/lore.yaml not present")
        first = await seed_lore(self.db, era="clone_wars")
        second = await seed_lore(self.db, era="clone_wars")
        self.assertGreater(first, 0)
        self.assertEqual(second, 0,
                         "second seed must be a no-op (titles already exist)")
        rows = await self._all_rows()
        self.assertEqual(len(rows), first)

    async def test_seed_lore_idempotent_on_default_path(self):
        """era=None twice produces the same idempotency as era='gcw' twice."""
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "lore.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/lore.yaml not present")
        first = await seed_lore(self.db, era=None)
        second = await seed_lore(self.db, era=None)
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(len(await self._all_rows()), first)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 fail-loud behavior — no in-Python fallback
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase2FailLoud(_LoreSeedTestBase):
    """Pre-Phase-2, YAML load failures silently fell back to the
    SEED_ENTRIES literal. Phase 2 deleted that fallback. The new
    contract: log ERROR and return 0. Real boot misconfigurations
    surface immediately instead of silently masking with stale data.
    """

    async def test_unknown_era_returns_zero(self):
        """Pointing at a nonexistent era directory returns 0."""
        with self.assertLogs("engine.world_lore", level="ERROR"):
            count = await seed_lore(self.db, era="nonexistent_era_xyz")
        self.assertEqual(count, 0,
                         "no in-Python fallback post-Phase-2: missing era "
                         "must return 0, not silently seed stale literals")

    async def test_unknown_era_does_not_seed_anything(self):
        """No rows should appear in the table on a YAML failure."""
        with self.assertLogs("engine.world_lore", level="ERROR"):
            await seed_lore(self.db, era="nonexistent_era_xyz")
        rows = await self._all_rows()
        self.assertEqual(rows, [],
                         "lore table should be empty after a failed YAML load")

    async def test_corpus_with_errors_returns_zero(self):
        """A corpus with hard validation errors → 0 entries seeded.

        Constructed by writing a malformed lore.yaml into a temp era
        directory and pointing seed_lore at it.
        """
        import tempfile
        import textwrap
        with tempfile.TemporaryDirectory() as td:
            era_dir = Path(td) / "data" / "worlds" / "broken_era"
            era_dir.mkdir(parents=True)
            (era_dir / "era.yaml").write_text(textwrap.dedent("""
                schema_version: 1
                era:
                  code: broken_era
                  name: "Broken Era"
                content_refs:
                  zones: zones.yaml
                  lore: lore.yaml
                  planets: []
                  wilderness: []
            """).lstrip("\n"))
            (era_dir / "zones.yaml").write_text("zones: {}\n")
            (era_dir / "lore.yaml").write_text(textwrap.dedent("""
                schema_version: 1
                entries:
                  - keywords: "no title"
                    category: "concept"
                    content: "this entry has no title"
            """).lstrip("\n"))

            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                with self.assertLogs("engine.world_lore", level="ERROR"):
                    count = await seed_lore(self.db, era="broken_era")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(count, 0,
                         "broken corpus must return 0, not silently fall "
                         "back to GCW literals (Phase 2 contract)")
        rows = await self._all_rows()
        self.assertEqual(rows, [])


# ══════════════════════════════════════════════════════════════════════════════
# Direct-corpus path (unchanged by Phase 2)
# ══════════════════════════════════════════════════════════════════════════════


class TestSeedLoreFromCorpus(_LoreSeedTestBase):
    def _corpus(self, *titles: str) -> LoreCorpus:
        return LoreCorpus(
            schema_version=1,
            entries=[
                LoreEntry(
                    title=t,
                    keywords=t.lower(),
                    content=f"Content for {t}.",
                    category="concept",
                    priority=5,
                )
                for t in titles
            ],
            report=ValidationReport(),
        )

    async def test_seed_lore_from_corpus_inserts_entries(self):
        corpus = self._corpus("Alpha", "Beta", "Gamma")
        count = await seed_lore_from_corpus(self.db, corpus)
        self.assertEqual(count, 3)
        titles = await self._all_titles()
        self.assertEqual(titles, {"Alpha", "Beta", "Gamma"})

    async def test_seed_lore_from_corpus_skips_existing_titles(self):
        first = self._corpus("Alpha", "Beta")
        await seed_lore_from_corpus(self.db, first)
        second = self._corpus("Beta", "Gamma")
        count = await seed_lore_from_corpus(self.db, second)
        self.assertEqual(count, 1)
        titles = await self._all_titles()
        self.assertEqual(titles, {"Alpha", "Beta", "Gamma"})


# ══════════════════════════════════════════════════════════════════════════════
# Phase 2 deletion guards
# ══════════════════════════════════════════════════════════════════════════════


class TestPhase2DeletionGuards(unittest.TestCase):
    """Source-level inspection that the deleted symbols are gone."""

    def test_seed_entries_symbol_is_gone(self):
        """SEED_ENTRIES module-level constant must not exist."""
        import engine.world_lore as wl
        self.assertFalse(
            hasattr(wl, "SEED_ENTRIES"),
            "SEED_ENTRIES should be deleted in Phase 2",
        )

    def test_seed_lore_signature_unchanged(self):
        """The function signature must still accept (db, era=None)."""
        import inspect
        sig = inspect.signature(seed_lore)
        params = list(sig.parameters.keys())
        self.assertEqual(params[:2], ["db", "era"])
        # era still defaults to None for backward-compat call signatures;
        # the meaning of None changed (now = "default to gcw"), but the
        # default literal is preserved.
        self.assertIs(sig.parameters["era"].default, None)


if __name__ == "__main__":
    unittest.main()
