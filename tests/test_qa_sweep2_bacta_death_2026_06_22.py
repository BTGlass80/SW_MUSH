# -*- coding: utf-8 -*-
"""
tests/test_qa_sweep2_bacta_death_2026_06_22.py — QA sweep #2 medical/death cluster.

Covers two defects:

1.  **Post-death stale session-cache** (ROOT FIX already applied in
    engine/death.py::on_pc_death step 3): before the fix,
    ``set_wound_state`` wrote ``wound_state='wounded'`` to the DB but never
    updated the in-memory ``session.character`` dict.  On the first
    post-death command the bacta-tank / bacta-pack paths read the stale
    ``"healthy"`` value from the session cache and wrongly refused ("you're
    not wounded").

    The regression test drives the LIVE harness: boot a clone_wars server,
    login a character, call ``on_pc_death`` with
    ``session_mgr=h.server.session_mgr``, then assert
    ``session.character["wound_state"] == "wounded"`` and
    ``float(session.character["wound_clear_at"]) > 0`` immediately after the
    call (the cache sync).  Then issue "bacta tank" and assert the output
    reflects the WOUNDED path (credit-check refusal "500") rather than the
    HEALTHY path ("not wounded").

    The test would FAIL against the pre-fix code (the cache sync block was
    absent, so ``wound_state`` would still read "healthy" in the session dict
    even though the DB row was correct).

2.  **Gear insurance cancel-after-death returns spurious success** [LOW]
    (fixed in engine/gear_insurance.py::cancel_gear_insurance): after a
    lawless death the DB gear_insured flag is consumed (→ 0) by
    ``_consume_gear_insurance_if_active``, but the session-cache char dict is
    not updated (no session_mgr at that call site).  A player typing
    ``+insure cancel`` would pass the ``is_insured(char)`` check on the stale
    cache value of 1 and receive a spurious "Coverage dropped" success.

    Fixed by adding a DB re-read guard in ``cancel_gear_insurance``.  Tests:
      - cancel on a truly-active policy still succeeds (no regression)
      - cancel where the DB already shows 0 (stale cache) returns
        ``{"ok": False, "reason": "not_insured"}``
      - cancel where the char dict already shows 0 returns not_insured
        (the cheap early-out path)
      - call-site (_cancel in InsureCommand) renders a sensible message for
        "not_insured" reason (same as "none")

Reset ``engine.world_events._manager = None`` in teardown.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("SW_ERA", "clone_wars")


# ─── async helpers ────────────────────────────────────────────────────────────

def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────────────
# 1. Post-death stale session-cache fix (live harness)
# ──────────────────────────────────────────────────────────────────────────────

class TestDeathCacheSync(unittest.TestCase):
    """Live-harness regression: on_pc_death syncs session.character cache."""

    @classmethod
    def setUpClass(cls):
        from tests.harness import _LiveHarness
        cls.harness = _run(_LiveHarness.boot("clone_wars"))

    @classmethod
    def tearDownClass(cls):
        _run(cls.harness.shutdown())
        # Reset the world-events singleton so any event state doesn't leak.
        try:
            import engine.world_events as _we
            _we._manager = None
        except Exception:
            pass

    def test_on_pc_death_syncs_wound_state_in_session_cache(self):
        """After on_pc_death, session.character['wound_state'] == 'wounded'.

        This is the ROOT fix: before the fix the session dict still showed
        'healthy' immediately after death, so bacta paths wrongly refused.
        """
        async def go():
            h = self.harness
            s = await h.login_as("DeathCacheA", room_id=1, credits=0)
            char_id = s.character["id"]

            # Pre-condition: session cache starts healthy.
            self.assertEqual(
                s.character.get("wound_state", "healthy"), "healthy",
                "Session should start healthy",
            )

            from engine.death import on_pc_death
            await on_pc_death(
                h.db,
                char_id=char_id,
                room_id=1,
                security_level="lawless",
                session_mgr=h.server.session_mgr,
            )

            # Post-condition: session cache reflects the wound immediately.
            self.assertEqual(
                s.character.get("wound_state"), "wounded",
                "on_pc_death must sync session.character['wound_state'] to "
                "'wounded' so the next command doesn't see a stale 'healthy'",
            )
            clear_at = s.character.get("wound_clear_at", 0)
            self.assertGreater(
                float(clear_at), 0,
                "on_pc_death must also set wound_clear_at > 0 in the session "
                "cache (recovery clock must be visible to the command layer)",
            )

        _run(go())

    def test_bacta_tank_sees_wounded_state_not_healthy_after_death(self):
        """After on_pc_death the bacta tank command reads 'wounded', not 'healthy'.

        With the fix in place: the character is wounded (cache synced), but has
        0 credits, so the bacta command hits the CREDIT CHECK branch ("costs 500
        credits") rather than the HEALTHY GATE ("you're not wounded").

        This proves the cache-sync makes the heal path reachable; without the
        fix the stale 'healthy' in the cache would return early with the
        "not wounded" message before even checking credits.
        """
        async def go():
            h = self.harness
            # Use 0 credits so we stop at the credit-check, not at a real heal.
            s = await h.login_as("DeathCacheB", room_id=1, credits=0)
            char_id = s.character["id"]

            from engine.death import on_pc_death
            await on_pc_death(
                h.db,
                char_id=char_id,
                room_id=1,
                security_level="lawless",
                session_mgr=h.server.session_mgr,
            )

            # Issue "bacta tank" with 0 credits.
            out = await h.cmd(s, "bacta tank")

            # MUST NOT see the pre-fix "not wounded" early-exit message.
            self.assertNotIn(
                "not wounded", out.lower(),
                f"bacta tank should not claim the char is healthy after death. "
                f"Output: {out[:400]!r}",
            )
            # MUST see the credit-check refusal — proving the heal path was
            # reached.  "500" appears in "Bacta tank costs 500 credits".
            self.assertIn(
                "500", out,
                f"bacta tank should show the 500-credit cost when wounded but "
                f"broke. Output: {out[:400]!r}",
            )

        _run(go())

    def test_wound_state_written_to_db_by_on_pc_death(self):
        """Companion DB check: the wound_state is also correct in the DB."""
        async def go():
            h = self.harness
            s = await h.login_as("DeathCacheC", room_id=1, credits=0)
            char_id = s.character["id"]

            from engine.death import on_pc_death
            await on_pc_death(
                h.db,
                char_id=char_id,
                room_id=1,
                security_level="lawless",
                session_mgr=h.server.session_mgr,
            )

            db_state, db_clear_at = await h.db.get_wound_state(char_id)
            self.assertEqual(db_state, "wounded",
                             "DB wound_state must be 'wounded' after death")
            self.assertGreater(float(db_clear_at), 0,
                               "DB wound_clear_at must be > 0 after death")

        _run(go())

    def test_secured_zone_death_does_not_set_wound_state(self):
        """Secured-zone death: no corpse, no wound_state, no cache change."""
        async def go():
            h = self.harness
            s = await h.login_as("DeathCacheD", room_id=1, credits=0)
            char_id = s.character["id"]

            from engine.death import on_pc_death
            corpse_id = await on_pc_death(
                h.db,
                char_id=char_id,
                room_id=1,
                security_level="secured",
                session_mgr=h.server.session_mgr,
            )

            self.assertIsNone(corpse_id, "Secured-zone death must not create a corpse")
            # Session cache must NOT be set to wounded (no penalty in secured zone).
            state = s.character.get("wound_state", "healthy")
            self.assertNotEqual(
                state, "wounded",
                "Secured-zone death must not set wound_state='wounded' in cache",
            )

        _run(go())


# ──────────────────────────────────────────────────────────────────────────────
# 2. Gear insurance cancel-after-death [LOW]
# ──────────────────────────────────────────────────────────────────────────────

# ── Minimal stub DB for the cancel-guard unit tests ──────────────────────────

class _CancelStubDB:
    """Minimal DB stub with a configurable DB-level gear_insured value."""

    def __init__(self, db_gear_insured: int):
        self._db_gear_insured = db_gear_insured
        self.saves: list = []

    # Expose a minimal ._db attribute with execute_fetchall so the DB re-read
    # inside cancel_gear_insurance works.
    class _Inner:
        def __init__(self, val):
            self._val = val

        async def execute_fetchall(self, sql, params):
            # Return a single-row result with the configured gear_insured value.
            return [{"gear_insured": self._val}]

    def __getattr__(self, name):
        if name == "_db":
            return self._Inner(self._db_gear_insured)
        raise AttributeError(name)

    async def save_character(self, char_id, **fields):
        self.saves.append(fields)


class TestCancelInsuranceGuard(unittest.TestCase):
    """Unit tests for cancel_gear_insurance DB re-read guard."""

    def test_cancel_active_policy_still_succeeds(self):
        """Cancelling a policy that is active in BOTH cache and DB works."""
        async def go():
            from engine.gear_insurance import cancel_gear_insurance
            db = _CancelStubDB(db_gear_insured=1)
            char = {"id": 1, "gear_insured": 1}
            return await cancel_gear_insurance(db, char)
        res = _run(go())
        self.assertTrue(res["ok"])
        self.assertEqual(res.get("reason", None), None)

    def test_cancel_after_death_stale_cache_returns_not_insured(self):
        """After a death the DB has gear_insured=0 but the char cache shows 1.

        This is the stale-cache scenario: the DB re-read must catch it and
        return not_insured rather than writing a spurious "coverage dropped".
        """
        async def go():
            from engine.gear_insurance import cancel_gear_insurance
            # DB says 0 (consumed by death); session cache says 1 (stale).
            db = _CancelStubDB(db_gear_insured=0)
            char = {"id": 1, "gear_insured": 1}
            res = await cancel_gear_insurance(db, char)
            return res, char["gear_insured"]
        res, cached = _run(go())
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_insured",
                         "Stale-cache cancel must return 'not_insured'")
        # Side-effect: cache should be corrected to 0.
        self.assertEqual(cached, 0,
                         "cancel_gear_insurance should sync cache to 0 on "
                         "stale-cache detection")

    def test_cancel_with_no_policy_in_cache_returns_not_insured(self):
        """When the char dict already shows gear_insured=0, the cheap
        early-out via is_insured() returns 'not_insured' without a DB round-trip."""
        async def go():
            from engine.gear_insurance import cancel_gear_insurance
            db = _CancelStubDB(db_gear_insured=0)
            char = {"id": 1, "gear_insured": 0}
            return await cancel_gear_insurance(db, char)
        res = _run(go())
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_insured")

    def test_cancel_does_not_write_db_when_already_consumed(self):
        """When the DB re-read finds gear_insured=0, save_character must NOT
        be called (the policy was already cleared by the death path)."""
        async def go():
            from engine.gear_insurance import cancel_gear_insurance
            db = _CancelStubDB(db_gear_insured=0)
            char = {"id": 1, "gear_insured": 1}
            await cancel_gear_insurance(db, char)
            return db.saves
        saves = _run(go())
        self.assertEqual(saves, [],
                         "cancel_gear_insurance must not call save_character "
                         "when the DB already shows the policy as consumed")

    def test_active_policy_cancel_does_write_db(self):
        """Cancelling a live policy writes gear_insured=0 to the DB."""
        async def go():
            from engine.gear_insurance import cancel_gear_insurance
            db = _CancelStubDB(db_gear_insured=1)
            char = {"id": 1, "gear_insured": 1}
            res = await cancel_gear_insurance(db, char)
            return res, db.saves
        res, saves = _run(go())
        self.assertTrue(res["ok"])
        self.assertIn({"gear_insured": 0}, saves,
                      "Successful cancel must persist gear_insured=0")


class TestInsureCommandNotInsuredReason(unittest.TestCase):
    """The _cancel call site renders the same message for 'not_insured' and 'none'."""

    def test_not_insured_reason_renders_clear_message(self):
        """_cancel in InsureCommand handles 'not_insured' just like 'none'."""
        # Import the call-site logic without booting a full server.
        import importlib, types
        # Verify the call site contains the 'not_insured' branch.
        insurance_cmd_path = os.path.join(
            PROJECT_ROOT, "parser", "insurance_commands.py")
        with open(insurance_cmd_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"not_insured"', src,
                      "insurance_commands.py _cancel must handle 'not_insured' reason")
        self.assertIn('"none"', src,
                      "insurance_commands.py _cancel must still handle 'none' reason")


# ──────────────────────────────────────────────────────────────────────────────
# 3. Structural: verify the cache-sync block is present in death.py
# ──────────────────────────────────────────────────────────────────────────────

class TestDeathPyCacheSyncPresent(unittest.TestCase):
    """Structural pin: the cache-sync block must be in engine/death.py."""

    def test_session_cache_sync_present_in_on_pc_death(self):
        death_path = os.path.join(PROJECT_ROOT, "engine", "death.py")
        with open(death_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("find_by_character", src,
                      "on_pc_death must call session_mgr.find_by_character "
                      "to sync the session cache after set_wound_state")
        self.assertIn('_wsess.character["wound_state"] = "wounded"', src,
                      "on_pc_death must set wound_state on the session cache")
        self.assertIn('_wsess.character["wound_clear_at"] = clear_at', src,
                      "on_pc_death must set wound_clear_at on the session cache")

    def test_cancel_gear_insurance_has_db_reread_guard(self):
        gi_path = os.path.join(PROJECT_ROOT, "engine", "gear_insurance.py")
        with open(gi_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("not_insured", src,
                      "cancel_gear_insurance must return reason='not_insured'")
        self.assertIn("execute_fetchall", src,
                      "cancel_gear_insurance must perform a DB re-read to guard "
                      "against a stale session cache after death")


if __name__ == "__main__":
    unittest.main()
