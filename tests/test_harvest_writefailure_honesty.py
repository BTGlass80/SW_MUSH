# -*- coding: utf-8 -*-
"""
tests/test_harvest_writefailure_honesty.py

Per-drop guard for the 2026-06-14 harvest write-failure-honesty drop (from the
engine defect-hunt — docs/design/HANDOFF_engine_defect_hunt_2026-06-14.md):

  * false_success_credit_write_failure (HIGH): perform_harvest set + persisted
    the 30-min cooldown BEFORE granting credits, then if db.adjust_credits raised
    it swallowed the error and still returned ok=True with credits_kept>0 and a
    "+NNNcr" message. The player was told they harvested credits they never got
    AND locked out of the region for 30 min.
  * false_success_resource_grant_failure (MEDIUM): the result reported
    payout['resource_stacks'] as granted even when the resource write failed.

Fix: a FAILED skill check still consumes the cooldown (design-intended), but on
the SUCCESS path the cooldown is consumed only AFTER the credit grant commits; a
credit-write failure returns an honest ok=False and does NOT consume the cooldown
(nothing committed → safe to retry); a resource hiccup after credits commit
reports the resources that ACTUALLY landed (no re-roll for double credits).

These assertions fail against the unfixed code (which returned ok=True + consumed
the cooldown on a credit-write failure).
"""

import asyncio
import contextlib
import json
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


class _FakeDB:
    """Minimal db: perform_harvest only reaches adjust_credits + save_character
    on this (mocked) success path (zone_id None → no security/influence DB,
    owner None → no tax routing)."""

    def __init__(self, credit_raises=False, resource_save_raises=False):
        self.credit_raises = credit_raises
        self.resource_save_raises = resource_save_raises
        self.credit_calls = []
        self.saves = []

    async def adjust_credits(self, char_id, delta, tag):
        self.credit_calls.append((char_id, delta, tag))
        if self.credit_raises:
            raise RuntimeError("simulated aiosqlite failure on credit write")
        return 500 + delta

    async def save_character(self, char_id, **kw):
        if self.resource_save_raises and "inventory" in kw:
            raise RuntimeError("simulated aiosqlite failure on inventory save")
        self.saves.append(kw)

    async def fetchall(self, *a, **k):
        return []

    async def get_organization(self, code):
        return None

    async def adjust_org_treasury(self, *a, **k):
        return None


def _payout_with(stacks):
    def _payout(**kw):
        return {
            "credits_kept": 100,
            "credits_tax": 0,
            "resource_stacks": list(stacks),
            "t5_rare": False,
            "scavenge_bonus": False,
        }
    return _payout


def _ok_skill(char, skill, diff, **kw):
    return types.SimpleNamespace(success=True, margin=5, roll=11, pool_str="3D")


@contextlib.contextmanager
def _harvest_setup(payout_stacks=()):
    """Mock the heavy setup seams so perform_harvest reaches the grant steps
    deterministically: a lawless dune_sea node, no owner, quality 1.0, a passing
    skill check, and a fixed payout."""
    async def _resolve(db, room_id):
        return ("dune_sea", None)          # zone_id None → no security/influence DB

    async def _node(db, room_id, slug):
        return True

    async def _owner(db, char, slug):
        return (False, None)               # owner None → no tax routing

    async def _quality(db, slug):
        return 1.0

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("engine.territory._resolve_room_region", _resolve))
        stack.enter_context(mock.patch("engine.harvest._is_harvest_node", _node))
        stack.enter_context(mock.patch("engine.harvest._is_owner_member", _owner))
        stack.enter_context(mock.patch("engine.harvest._get_region_quality", _quality))
        stack.enter_context(mock.patch("engine.harvest.compute_harvest_payout",
                                       _payout_with(payout_stacks)))
        stack.enter_context(mock.patch("engine.skill_checks.perform_skill_check",
                                       _ok_skill))
        yield


def _fresh_char():
    return {"id": 1, "name": "Harvester", "credits": 500,
            "attributes": "{}", "inventory": "{}"}


def _cooldowns(char):
    return json.loads(char["attributes"] or "{}").get("cooldowns", {})


class TestHarvestCreditWriteFailure(unittest.TestCase):
    def test_credit_failure_returns_ok_false_and_does_not_consume_cooldown(self):
        async def _t():
            from engine.harvest import perform_harvest
            db = _FakeDB(credit_raises=True)
            char = _fresh_char()
            with _harvest_setup():
                res = await perform_harvest(db, char, room_id=10)
            self.assertFalse(res["ok"],
                             f"credit-write failure must be an honest failure: {res}")
            # the failure message must not claim a credit payout
            self.assertNotIn("+", res.get("msg", ""),
                             "failure message must not advertise a payout")
            self.assertEqual(_cooldowns(char), {},
                             "a credit-write failure must NOT consume the cooldown")
            self.assertEqual(char["credits"], 500,
                             "credits must be unchanged when the write raised")
        _run(_t())

    def test_success_consumes_cooldown_and_reports_payout(self):
        async def _t():
            from engine.harvest import perform_harvest
            db = _FakeDB(credit_raises=False)
            char = _fresh_char()
            with _harvest_setup():
                res = await perform_harvest(db, char, room_id=10)
            self.assertTrue(res["ok"], f"{res}")
            self.assertEqual(res["credits_kept"], 100)
            self.assertTrue(_cooldowns(char),
                            "a successful harvest must consume the cooldown")
            self.assertEqual(char["credits"], 600)
        _run(_t())


class TestHarvestResourceGrantFailure(unittest.TestCase):
    def test_resource_failure_after_credits_commit_reports_actual_haul(self):
        async def _t():
            from engine.harvest import perform_harvest
            # credits commit, then the inventory save raises.
            db = _FakeDB(credit_raises=False, resource_save_raises=True)
            char = _fresh_char()
            stacks = [{"type": "metal", "quantity": 2, "quality": 100}]
            with _harvest_setup(payout_stacks=stacks):
                res = await perform_harvest(db, char, room_id=10)
            # Credits already committed → still a success, cooldown consumed,
            # but the reported resource_stacks must be the EMPTY actual haul,
            # never the unpersisted requested stacks.
            self.assertTrue(res["ok"], f"{res}")
            self.assertEqual(res["resource_stacks"], [],
                             "must report the resources that actually landed, "
                             "not the unpersisted requested stacks")
            self.assertTrue(_cooldowns(char))
            self.assertEqual(char["credits"], 600)
        _run(_t())


if __name__ == "__main__":
    unittest.main()
