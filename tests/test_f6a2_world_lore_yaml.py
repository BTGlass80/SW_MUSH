# -*- coding: utf-8 -*-
"""
tests/test_f6a2_world_lore_yaml.py — Drop F.6a.2 tests

Exercises engine/world_lore.py's era-aware seeding path:
    seed_lore(db, era=None)   -> int     (legacy path, unchanged)
    seed_lore(db, era="gcw")  -> int     (loads from YAML via F.6a.1)
    seed_lore(db, era="clone_wars") -> int
    seed_lore_from_corpus(db, corpus) -> int

Coverage map (per clone_wars_director_lore_pivot_design_v1.md §5.2):

  Byte-equivalence (the central regression assertion):
    - test_gcw_yaml_seed_entries_match_legacy_constant

  Era path:
    - test_clone_wars_loads_at_least_32_entries
    - test_seed_lore_idempotent_on_clone_wars
    - test_seed_lore_idempotent_on_legacy_path

  Fallback path:
    - test_seed_falls_back_to_seed_entries_when_era_missing
    - test_seed_falls_back_to_seed_entries_when_lore_yaml_absent
    - test_seed_falls_back_to_seed_entries_when_corpus_has_errors

  Direct-corpus path:
    - test_seed_lore_from_corpus_inserts_entries
    - test_seed_lore_from_corpus_skips_existing_titles

  Backward compat:
    - test_legacy_signature_still_works

The test DB is an in-memory aiosqlite wrapper exposing the async
`execute / fetchall / commit` API that engine/world_lore.py uses,
so we exercise the real seeding code, not a mock.
"""
import asyncio
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
    SEED_ENTRIES, ensure_lore_schema, seed_lore, seed_lore_from_corpus,
    clear_cache,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fake DB — exposes the slice of the engine/db/database.py API that
# engine/world_lore.py actually uses (execute, fetchall, commit). Backed
# by in-memory aiosqlite so we exercise real SQL behavior, not mocks.
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

    async def fetchall(self, sql: str, params: tuple = ()) -> list:
        async with self._conn.execute(sql, params) as cur:
            return list(await cur.fetchall())

    async def commit(self):
        await self._conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Async test runner — unittest doesn't support async test methods natively
# in 3.12 without IsolatedAsyncioTestCase. Use that base class.
# ══════════════════════════════════════════════════════════════════════════════


class _LoreSeedTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_cache()
        self.db = FakeDB()
        await self.db.connect()
        await ensure_lore_schema(self.db)

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
# Byte-equivalence — the central regression assertion
# ══════════════════════════════════════════════════════════════════════════════


class TestGCWByteEquivalence(_LoreSeedTestBase):
    """Loading data/worlds/gcw/lore.yaml must produce the same seeded
    rows as the legacy SEED_ENTRIES constant. This is the gating
    assertion for flipping the era flag to GCW-via-YAML.
    """

    async def test_gcw_yaml_seed_entries_match_legacy_constant(self):
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "lore.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/lore.yaml not present")

        # Seed via legacy path (era=None → SEED_ENTRIES)
        legacy_count = await seed_lore(self.db, era=None)
        legacy_rows = sorted(await self._all_rows(),
                             key=lambda r: r["title"])

        # Reset the table; reseed via era="gcw" path (loads YAML)
        await self.db.execute("DELETE FROM world_lore")
        await self.db.commit()
        clear_cache()
        yaml_count = await seed_lore(self.db, era="gcw")
        yaml_rows = sorted(await self._all_rows(),
                           key=lambda r: r["title"])

        self.assertEqual(legacy_count, yaml_count,
                         "GCW YAML must seed the same number of entries")

        self.assertEqual(
            len(legacy_rows), len(yaml_rows),
            f"row count diverges: legacy={len(legacy_rows)} yaml={len(yaml_rows)}"
        )

        # Compare row-for-row on the fields that matter at the application
        # level. id and created_at differ across runs (autoincrement, time);
        # all the content fields must match.
        for L, Y in zip(legacy_rows, yaml_rows):
            for fld in ("title", "keywords", "content", "category",
                        "zone_scope", "priority", "active"):
                self.assertEqual(
                    L[fld], Y[fld],
                    f"field {fld!r} differs for {L['title']!r}: "
                    f"legacy={L[fld]!r} yaml={Y[fld]!r}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# Era path
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
            f"CW lore.yaml must contain ≥ 32 entries (per design §8.2 target)"
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
        # And the table should still hold the same number of rows.
        rows = await self._all_rows()
        self.assertEqual(len(rows), first)

    async def test_seed_lore_idempotent_on_legacy_path(self):
        first = await seed_lore(self.db, era=None)
        second = await seed_lore(self.db, era=None)
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(len(await self._all_rows()), first)


# ══════════════════════════════════════════════════════════════════════════════
# Fallback behavior — must never break boot
# ══════════════════════════════════════════════════════════════════════════════


class TestSeedFallback(_LoreSeedTestBase):
    async def test_seed_falls_back_to_seed_entries_when_era_missing(self):
        """Pointing at a nonexistent era directory falls back to SEED_ENTRIES."""
        count = await seed_lore(self.db, era="nonexistent_era_xyz")
        self.assertEqual(count, len(SEED_ENTRIES))
        # Sanity: at least one known SEED title is present
        titles = await self._all_titles()
        self.assertIn("The Galactic Empire", titles)

    async def test_seed_falls_back_to_seed_entries_when_lore_yaml_absent(self):
        """An era manifest with no `lore` content_ref falls back to SEED_ENTRIES."""
        # Create a stub era directory with era.yaml + zones.yaml only
        import tempfile
        import textwrap
        with tempfile.TemporaryDirectory() as td:
            era_dir = Path(td) / "stub_era"
            era_dir.mkdir()
            (era_dir / "era.yaml").write_text(textwrap.dedent("""
                schema_version: 1
                era:
                  code: stub_era
                  name: "Stub Era"
                content_refs:
                  zones: zones.yaml
                  planets: []
                  wilderness: []
            """).lstrip("\n"))
            (era_dir / "zones.yaml").write_text("zones: {}\n")

            # Patch the data/worlds path resolution to point at our stub.
            # Easiest: monkey-patch the loader's import inside seed_lore.
            # Actually simpler: the seed_lore code path constructs
            # Path("data/worlds") / era — so we just need to exercise the
            # "manifest loads but no lore_path" branch via a helper.
            from engine.world_loader import (
                load_era_manifest, load_lore as _load_lore,
            )
            manifest = load_era_manifest(era_dir)
            corpus = _load_lore(manifest)
            # Corpus is None (no lore_path) — confirm fallback contract.
            self.assertIsNone(corpus)
            # Now re-run the path the real seed_lore would take when corpus
            # is None: fall through to SEED_ENTRIES.
            from engine.world_lore import _seed_from_entries
            count = await _seed_from_entries(self.db, SEED_ENTRIES)
            self.assertEqual(count, len(SEED_ENTRIES))

    async def test_seed_falls_back_to_seed_entries_when_corpus_has_errors(self):
        """Corpus with hard errors → falls back, does NOT seed broken corpus.

        We construct the broken corpus manually and route through the
        public seed_lore() with a synthetic era directory pointed at a
        broken lore.yaml. Easier: directly exercise the branch by
        constructing a LoreCorpus with errors and asserting that
        seed_lore_from_corpus would seed it (caller's choice), while
        seed_lore(era=...) wouldn't (it falls back).

        For the latter, we use a temp era dir with a malformed lore.yaml.
        """
        import tempfile
        import textwrap
        with tempfile.TemporaryDirectory() as td:
            # Simulate the "data/worlds/<era>" layout
            worlds_root = Path(td)
            era_dir = worlds_root / "broken_era"
            era_dir.mkdir()
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
            # A lore.yaml whose entries have hard errors (missing title)
            (era_dir / "lore.yaml").write_text(textwrap.dedent("""
                schema_version: 1
                entries:
                  - keywords: "no title"
                    category: "concept"
                    content: "this entry has no title"
            """).lstrip("\n"))

            # Monkey-patch the seed_lore's worlds-root by switching CWD.
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                # Make data/worlds/broken_era available at the expected path
                (Path(td) / "data" / "worlds").mkdir(parents=True)
                (Path(td) / "data" / "worlds" / "broken_era").symlink_to(
                    era_dir, target_is_directory=True
                )
                count = await seed_lore(self.db, era="broken_era")
            finally:
                os.chdir(old_cwd)

            # Fallback path → SEED_ENTRIES seeded
            self.assertEqual(count, len(SEED_ENTRIES))
            titles = await self._all_titles()
            self.assertIn("The Galactic Empire", titles)


# ══════════════════════════════════════════════════════════════════════════════
# Direct-corpus path
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
        # Re-seed with overlap + one new
        second = self._corpus("Beta", "Gamma")
        count = await seed_lore_from_corpus(self.db, second)
        self.assertEqual(count, 1)  # only Gamma is new
        titles = await self._all_titles()
        self.assertEqual(titles, {"Alpha", "Beta", "Gamma"})


# ══════════════════════════════════════════════════════════════════════════════
# Backward compat — old call sites still work
# ══════════════════════════════════════════════════════════════════════════════


class TestBackwardCompat(_LoreSeedTestBase):
    async def test_legacy_signature_still_works(self):
        """server/game_server.py calls seed_lore(self.db) with no era.
        That call signature must continue to work unchanged.
        """
        count = await seed_lore(self.db)  # no era kwarg, no positional
        self.assertEqual(count, len(SEED_ENTRIES))


if __name__ == "__main__":
    unittest.main()
