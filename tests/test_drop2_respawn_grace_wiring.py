"""Drop 2 follow-up (audit) — the respawn-grace consumer is now WIRED.

Drop 2 shipped `engine.death.get_respawn_grace_until` plus the `grace_until`
writer inside `on_pc_death`, but never *called* the reader from the combat
layer — so the anti-spawn-camp protection its docstring promised did nothing
(a classic infrastructure-complete-but-unwired gap). This pins the wiring:

  * `parser/combat_commands.py`'s PC-death path consults
    `get_respawn_grace_until` BEFORE finalizing the death, and
  * when the victim is still protected it caps at INCAPACITATED (alive,
    no bleed-out) and skips `on_pc_death` entirely (no corpse / debuff /
    insurance), and
  * the normal death path (`on_pc_death`) is still present, in the
    not-protected branch.

Plus a minimal real-db check of the reader contract the wiring relies on.
The full grace read/write contract is covered by
test_drop2_death_reconciliation.TestRespawnGrace; this module is about the
*consumer* existing and being gated correctly.
"""

import asyncio
import time
import unittest
from pathlib import Path


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "parser" / "combat_commands.py").exists():
            return parent
    raise RuntimeError("could not locate repo root from test file")


ROOT = _find_root()
COMBAT_CMDS = ROOT / "parser" / "combat_commands.py"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _death_block(src: str) -> str:
    """Slice out the PC-death handling region so the structural assertions
    are scoped to it rather than matching incidental mentions elsewhere."""
    start = src.index(">= _WLD.DEAD.value:")
    end = src.index("# ── End PG.1.death hook ──", start)
    return src[start:end]


class TestRespawnGraceConsumerWired(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = COMBAT_CMDS.read_text(encoding="utf-8")
        cls.block = _death_block(cls.src)

    def test_reader_is_called_in_death_path(self):
        self.assertIn(
            "get_respawn_grace_until(ctx.db, c.id)", self.block,
            "the PC-death path must consult get_respawn_grace_until "
            "(the Drop 2 consumer that was left unwired)")

    def test_grace_check_precedes_on_pc_death(self):
        i_grace = self.block.index("get_respawn_grace_until(ctx.db, c.id)")
        i_death = self.block.index("await on_pc_death(")
        self.assertLess(
            i_grace, i_death,
            "grace must be checked BEFORE on_pc_death so a protected "
            "victim's death is refused, not finalized")

    def test_protected_victim_capped_at_incapacitated(self):
        protect = self.block[: self.block.index("else:")]
        self.assertIn(
            "_WLD.INCAPACITATED", protect,
            "a grace-protected victim must be capped at INCAPACITATED "
            "(alive, no bleed-out), not killed")
        # And must NOT be *assigned* a bleed-out / dead level in that branch
        # (checks the assignment, so an explanatory comment may still name it).
        self.assertNotIn("wound_level = _WLD.MORTALLY_WOUNDED", protect)
        self.assertNotIn("wound_level = _WLD.DEAD", protect)

    def test_normal_death_path_still_present(self):
        # The fix must not delete the death flow — on_pc_death stays in the
        # not-protected (else) branch.
        self.assertIn("await on_pc_death(", self.block)
        self.assertIn("else:", self.block)

    def test_grace_read_is_no_throw_guarded(self):
        # The reader call is wrapped so a read error can't blow up the
        # death flow (and death.py fails it open to 0.0 anyway).
        i_grace = self.block.index("get_respawn_grace_until(ctx.db, c.id)")
        preceding = self.block[:i_grace]
        self.assertIn("try:", preceding)


class TestGraceReaderContractForWiring(unittest.TestCase):
    """Minimal real-db confirmation that the reader the wiring depends on
    returns the stored window (so the gate `now < grace_until` is meaningful)
    and fails open to 0.0 for an unprotected character."""

    @staticmethod
    async def _mini_db():
        from db.database import Database
        db = Database(":memory:")
        await db.connect()
        await db._db.execute(
            """CREATE TABLE recent_pvp_deaths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                victim_id INTEGER NOT NULL, killer_id INTEGER NOT NULL,
                died_at REAL NOT NULL, grace_until REAL)"""
        )
        await db._db.commit()
        return db

    def setUp(self):
        try:
            import db.database  # noqa: F401
        except Exception as exc:  # e.g. aiosqlite missing in a bare env
            self.skipTest(f"db backend unavailable: {exc}")

    def test_future_grace_means_protected(self):
        async def go():
            from engine.death import get_respawn_grace_until
            db = await self._mini_db()
            now = time.time()
            await db._db.execute(
                "INSERT INTO recent_pvp_deaths "
                "(victim_id, killer_id, died_at, grace_until) VALUES (?,?,?,?)",
                (1, 2, now, now + 60.0))
            await db._db.commit()
            return await get_respawn_grace_until(db, 1), now
        grace, now = _run(go())
        self.assertGreater(grace, now, "future grace -> victim is protected")
        self.assertTrue(bool(grace) and now < grace)

    def test_expired_grace_means_unprotected(self):
        async def go():
            from engine.death import get_respawn_grace_until
            db = await self._mini_db()
            now = time.time()
            await db._db.execute(
                "INSERT INTO recent_pvp_deaths "
                "(victim_id, killer_id, died_at, grace_until) VALUES (?,?,?,?)",
                (1, 2, now - 120.0, now - 60.0))
            await db._db.commit()
            return await get_respawn_grace_until(db, 1), now
        grace, now = _run(go())
        self.assertFalse(now < grace, "expired grace -> victim is NOT protected")

    def test_no_prior_death_fails_open(self):
        async def go():
            from engine.death import get_respawn_grace_until
            db = await self._mini_db()
            return await get_respawn_grace_until(db, 999)
        self.assertEqual(_run(go()), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
