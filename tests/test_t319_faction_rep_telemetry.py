# -*- coding: utf-8 -*-
"""tests/test_t319_faction_rep_telemetry.py — T3.19 telemetry breadth.

Instruments ``engine.organizations.adjust_rep`` — the SINGLE funnel for ALL
faction-reputation movement (member DB ``rep_score`` 0..100 + non-member
attributes ``faction_rep`` -100..100, including the cross-faction penalty
recursion). One ``faction_rep`` telemetry event is emitted per landed change
(``delta != 0``), the progression/affiliation analog of how ``credit_flow``
rides ``db.log_credit`` and ``influence`` rides ``adjust_territory_influence``.
The offline funnel can then answer: which actions drive rep, how fast players
climb tiers, where rep pins at a cap, and member-vs-non-member flows.

The contract under test (Brian, telemetry_purpose_clarified): the emit is
buffer-only (non-blocking), fail-open (NEVER disturbs the rep path it
observes), and the keep-rate is a use-site tunable
(``telemetry.faction_rep_sample``).
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── minimal Database-API surface (just what adjust_rep / check_auto_promote use)
class _FakeDB:
    def __init__(self):
        self.orgs = {}          # code -> org dict
        self.memberships = {}   # (char_id, org_id) -> membership dict
        self.ranks = {}         # org_id -> [rank rows]
        self.saved = []         # [(char_id, attributes)]
        self.rep_updates = []   # [(char_id, org_id, rep_score)]

    def add_org(self, code, oid, name=None):
        self.orgs[code] = {"id": oid, "code": code, "name": name or code.title()}

    def add_membership(self, char_id, org_id, rep_score=0, rank_level=1):
        self.memberships[(char_id, org_id)] = {
            "char_id": char_id, "org_id": org_id,
            "rep_score": rep_score, "rank_level": rank_level,
        }

    async def get_organization(self, code):
        return self.orgs.get(code)

    async def get_membership(self, char_id, org_id):
        return self.memberships.get((char_id, org_id))

    async def update_membership(self, char_id, org_id, **kw):
        m = self.memberships.get((char_id, org_id))
        if m:
            m.update(kw)
        self.rep_updates.append((char_id, org_id, kw.get("rep_score")))

    async def save_character(self, char_id, **kw):
        self.saved.append((char_id, kw.get("attributes")))

    async def get_org_ranks(self, org_id):
        return self.ranks.get(org_id, [])


def _char(cid=1, attrs=None):
    return {"id": cid, "attributes": json.dumps(attrs or {})}


class _FactionRepTelemetryCase(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        self._tmp = tempfile.TemporaryDirectory()
        telemetry.reset()
        telemetry.configure(path=os.path.join(self._tmp.name, "e.jsonl"),
                            enabled=True)
        self.db = _FakeDB()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()
        self._tmp.cleanup()

    def _events(self):
        from engine import telemetry
        recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
        return [r for r in recs if r["ev"] == "faction_rep"]

    def _adjust(self, char, faction_code, **kw):
        from engine.organizations import adjust_rep
        return _run(adjust_rep(char, faction_code, self.db, **kw))

    # ── core: one event per landed change ─────────────────────────────────
    def test_non_member_positive_delta_emits_full_payload(self):
        self.db.add_org("hutt", 30)
        char = _char()
        new = self._adjust(char, "hutt", delta=12, reason="favor")
        self.assertEqual(new, 12)
        evs = self._events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["char_id"], 1)
        self.assertEqual(e["faction"], "hutt")
        self.assertEqual(e["delta"], 12)
        self.assertEqual(e["rep"], 12)
        self.assertEqual(e["prev"], 0)
        self.assertFalse(e["member"])
        self.assertFalse(e["clamped"])
        self.assertEqual(e["reason"], "favor")
        self.assertEqual(e["action"], "")
        # tier fields are populated from get_rep_tier
        self.assertIn("tier", e)
        self.assertIn("prev_tier", e)

    def test_action_key_drives_delta_and_action_field(self):
        # action_key path: delta looked up from REP_GAINS, action passed through.
        from engine.organizations import REP_GAINS
        self.db.add_org("hutt", 30)
        char = _char()
        new = self._adjust(char, "hutt", action_key="complete_bounty")
        self.assertEqual(new, REP_GAINS["complete_bounty"])
        evs = self._events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["action"], "complete_bounty")
        self.assertEqual(evs[0]["delta"], REP_GAINS["complete_bounty"])

    def test_member_positive_delta_emits_member_true(self):
        self.db.add_org("hutt", 30)
        self.db.add_membership(1, 30, rep_score=20)
        char = _char()
        new = self._adjust(char, "hutt", delta=10, reason="mission")
        self.assertEqual(new, 30)
        evs = self._events()
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["member"])
        self.assertEqual(evs[0]["prev"], 20)
        self.assertEqual(evs[0]["rep"], 30)
        self.assertFalse(evs[0]["clamped"])

    # ── clamp flag: ceiling (member 0..100) + floor (non-member -100..100) ─
    def test_member_clamp_at_cap_flagged(self):
        self.db.add_org("hutt", 30)
        self.db.add_membership(1, 30, rep_score=95)
        char = _char()
        new = self._adjust(char, "hutt", delta=20, reason="mission")
        self.assertEqual(new, 100)
        evs = self._events()
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["clamped"])
        self.assertEqual(evs[0]["rep"], 100)

    def test_non_member_clamp_at_floor_flagged(self):
        # Non-members range -100..100; a big negative pins at the floor.
        self.db.add_org("cis", 20)
        char = _char(attrs={"faction_rep": {"cis": -95}})
        new = self._adjust(char, "cis", delta=-20, reason="betrayal")
        self.assertEqual(new, -100)
        evs = self._events()
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["clamped"])
        self.assertEqual(evs[0]["rep"], -100)
        self.assertFalse(evs[0]["member"])

    # ── cross-faction penalty recursion lands + emits its own event ───────
    def test_cross_faction_penalty_emits_second_event(self):
        # Republic +10 to a MEMBER triggers a -5 cross-penalty against CIS
        # (CROSS_FACTION_PENALTIES["republic"] = {"cis": -0.5}); the char is
        # NOT a CIS member so the penalty lands on the non-member faction_rep.
        self.db.add_org("republic", 10)
        self.db.add_org("cis", 20)
        self.db.add_membership(1, 10, rep_score=0)
        char = _char()
        new = self._adjust(char, "republic", delta=10, reason="mission")
        self.assertEqual(new, 10)
        evs = self._events()
        self.assertEqual(len(evs), 2)
        # event 0: the republic member gain
        self.assertEqual(evs[0]["faction"], "republic")
        self.assertTrue(evs[0]["member"])
        self.assertEqual(evs[0]["delta"], 10)
        # event 1: the cross-faction CIS penalty (non-member, -5, tagged)
        self.assertEqual(evs[1]["faction"], "cis")
        self.assertFalse(evs[1]["member"])
        self.assertEqual(evs[1]["delta"], -5)
        self.assertEqual(evs[1]["rep"], -5)
        self.assertIn("Cross-faction", evs[1]["reason"])
        self.assertEqual(evs[1]["action"], "")

    # ── no-op deltas never pollute the funnel ─────────────────────────────
    def test_unknown_action_key_zero_delta_emits_nothing(self):
        # An action_key not in REP_GAINS resolves to delta 0 -> early return,
        # no mutation, no event.
        self.db.add_org("hutt", 30)
        char = _char()
        new = self._adjust(char, "hutt", action_key="not_a_real_action")
        self.assertEqual(new, 0)
        self.assertEqual(self._events(), [])

    def test_explicit_zero_delta_emits_nothing(self):
        self.db.add_org("hutt", 30)
        char = _char()
        self._adjust(char, "hutt", delta=0, reason="touch")
        self.assertEqual(self._events(), [])

    # ── keep-rate wired to telemetry.faction_rep_sample ───────────────────
    def test_sample_zero_suppresses_but_mutation_lands(self):
        self.db.add_org("hutt", 30)
        self.db.add_membership(1, 30, rep_score=0)
        char = _char()
        with mock.patch("engine.tunables.get_tunable", return_value=0.0):
            new = self._adjust(char, "hutt", delta=10, reason="mission")
        # rep still moved; telemetry was sampled out.
        self.assertEqual(new, 10)
        self.assertEqual(self.db.memberships[(1, 30)]["rep_score"], 10)
        self.assertEqual(self._events(), [])

    def test_sample_one_keeps_emit(self):
        self.db.add_org("hutt", 30)
        self.db.add_membership(1, 30, rep_score=0)
        char = _char()
        with mock.patch("engine.tunables.get_tunable", return_value=1.0):
            self._adjust(char, "hutt", delta=10, reason="mission")
        self.assertEqual(len(self._events()), 1)

    # ── fail-open: a broken sink never breaks the rep path ────────────────
    def test_emit_failure_does_not_disturb_rep_path(self):
        self.db.add_org("hutt", 30)
        self.db.add_membership(1, 30, rep_score=0)
        char = _char()
        with mock.patch("engine.telemetry.emit",
                        side_effect=RuntimeError("sink exploded")):
            new = self._adjust(char, "hutt", delta=7, reason="mission")
        # The rep mutation MUST still succeed even though the emitter raised.
        self.assertEqual(new, 7)
        self.assertEqual(self.db.memberships[(1, 30)]["rep_score"], 7)


if __name__ == "__main__":
    unittest.main()
