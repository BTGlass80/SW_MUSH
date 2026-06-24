# -*- coding: utf-8 -*-
"""tests/test_t319_grind_kill_telemetry.py — T3.19 telemetry breadth for the
mob-grind kill-reward SINK (engine/hunting_rewards.on_huntable_kill).

The solo-PvE grind faucet already tags its CREDIT leg on the ledger
(``mob_grind``), but those isolated credit rows could not be rejoined offline
into the grind FUNNEL: the per-kill payout distribution, how fast a grinder hits
the 400 cr/day SOFT CAP + how much of the session runs on the OVER_CAP_FLOOR
trickle tail, what / where is farmed, and engagement depth (lifetime kills,
milestone titles). This drop adds ONE fail-open, sample-tunable ``grind_kill``
event at the resolution seam of ``on_huntable_kill``, AFTER the reward + log are
persisted.

This suite drives the REAL ``on_huntable_kill`` (the same fake-db harness
``tests/test_hunting_rewards.py`` uses) and proves: exactly one event per
huntable kill with the right envelope (char_id / reward / daily_credits / at_cap
/ over_cap / total_kills / npc_name / room_id + the cheap species/faction/
behavior context); the cap-pressure flags track the soft cap (full payout under
cap, floor payout + over_cap past it); a non-huntable NPC emits nothing; a
missing room_id and absent ai context drop cleanly; the
``telemetry.grind_kill_sample`` tunable is honoured; and — the load-bearing
contract — a broken sink NEVER disturbs the completed reward.

Run: python -m pytest tests/test_t319_grind_kill_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import hunting_rewards as hr  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _events(ev_type="grind_kill"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeDB:
    """Serves adjust_credits + save_character (mirrors test_hunting_rewards)."""

    def __init__(self, credits=1000):
        self._credits = credits
        self.saved = {}

    async def adjust_credits(self, cid, delta, tag, *, allow_negative=True):
        self._credits += delta
        return self._credits

    async def save_character(self, cid, **fields):
        self.saved.update(fields)


def _npc(hostile=True, name="Swoop Thug", species="Weequay",
         faction="hutt_cartel", behavior="aggressive", **markers):
    ai = {"hostile": hostile}
    if faction is not None:
        ai["faction"] = faction
    if behavior is not None:
        ai["combat_behavior"] = behavior
    ai.update(markers)
    npc = {"id": 99, "name": name, "ai_config_json": json.dumps(ai)}
    if species is not None:
        npc["species"] = species
    return npc


def _killer(credits=1000, attrs=None, room_id=4207):
    k = {"id": 5, "name": "Hunter", "credits": credits,
         "vanity_titles": "[]", "attributes": json.dumps(attrs or {})}
    if room_id is not None:
        k["room_id"] = room_id
    return k


class GrindKillTelemetryTests(unittest.TestCase):
    DAY = "2026-06-24"

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── success: one event, full envelope on the first kill ──────────────────
    def test_first_kill_emits_one_event(self):
        out = _run(hr.on_huntable_kill(
            _FakeDB(), _killer(), _npc(), day_stamp=self.DAY))
        self.assertIsNotNone(out)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["ev"], "grind_kill")
        self.assertEqual(e["char_id"], 5)
        self.assertEqual(e["reward"], hr.BASE_REWARD)
        self.assertEqual(e["daily_credits"], hr.BASE_REWARD)
        self.assertFalse(e["at_cap"])
        self.assertFalse(e["over_cap"])
        self.assertEqual(e["total_kills"], 1)
        self.assertEqual(e["npc_name"], "Swoop Thug")
        self.assertEqual(e["room_id"], 4207)
        self.assertEqual(e["species"], "Weequay")
        self.assertEqual(e["faction"], "hutt_cartel")
        self.assertEqual(e["behavior"], "aggressive")

    # ── cap pressure: under cap pays base, past cap pays floor + over_cap ────
    def test_at_cap_kill_pays_floor_and_flags_over_cap(self):
        seed = {hr.HUNT_LOG_KEY: {"kills": 50,
                                  "daily_credits": hr.DAILY_SOFT_CAP,
                                  "day": self.DAY}}
        _run(hr.on_huntable_kill(
            _FakeDB(), _killer(attrs=seed), _npc(), day_stamp=self.DAY))
        e = _events()[0]
        self.assertEqual(e["reward"], hr.OVER_CAP_FLOOR)
        self.assertTrue(e["at_cap"])
        self.assertTrue(e["over_cap"])      # already past cap when computed
        self.assertEqual(e["daily_credits"],
                         hr.DAILY_SOFT_CAP + hr.OVER_CAP_FLOOR)

    def test_kill_that_reaches_cap_sets_at_cap_not_over_cap(self):
        # One short of the cap: this kill pays BASE (still under when computed)
        # and tips daily_credits to/over the cap → at_cap true, over_cap false.
        seed = {hr.HUNT_LOG_KEY: {"kills": 9,
                                  "daily_credits": hr.DAILY_SOFT_CAP - 1,
                                  "day": self.DAY}}
        _run(hr.on_huntable_kill(
            _FakeDB(), _killer(attrs=seed), _npc(), day_stamp=self.DAY))
        e = _events()[0]
        self.assertEqual(e["reward"], hr.BASE_REWARD)
        self.assertTrue(e["at_cap"])        # post-kill total is >= cap
        self.assertFalse(e["over_cap"])     # was still under cap when computed

    # ── milestone title rides along when a threshold is crossed ──────────────
    def test_title_key_recorded_on_milestone(self):
        thresh, key = hr.TITLE_THRESHOLDS[0]
        seed = {hr.HUNT_LOG_KEY: {"kills": thresh - 1,
                                  "daily_credits": 0, "day": self.DAY}}
        _run(hr.on_huntable_kill(
            _FakeDB(), _killer(attrs=seed), _npc(), day_stamp=self.DAY))
        e = _events()[0]
        self.assertEqual(e["total_kills"], thresh)
        self.assertEqual(e["title_key"], key)

    def test_no_title_key_between_thresholds(self):
        seed = {hr.HUNT_LOG_KEY: {"kills": 2, "daily_credits": 0,
                                  "day": self.DAY}}
        _run(hr.on_huntable_kill(
            _FakeDB(), _killer(attrs=seed), _npc(), day_stamp=self.DAY))
        self.assertNotIn("title_key", _events()[0])  # None extra dropped

    # ── a non-huntable NPC short-circuits before any emit ────────────────────
    def test_non_huntable_emits_nothing(self):
        out = _run(hr.on_huntable_kill(
            _FakeDB(), _killer(), _npc(is_bounty_target=True),
            day_stamp=self.DAY))
        self.assertIsNone(out)
        self.assertEqual(len(_events()), 0)

    # ── missing room_id / absent ai context drop cleanly ─────────────────────
    def test_missing_room_id_and_context_dropped(self):
        _run(hr.on_huntable_kill(
            _FakeDB(), _killer(room_id=None),
            _npc(species=None, faction=None, behavior=None),
            day_stamp=self.DAY))
        e = _events()[0]
        self.assertNotIn("room_id", e)
        self.assertNotIn("species", e)
        self.assertNotIn("faction", e)
        self.assertNotIn("behavior", e)
        # the core funnel fields are still present
        self.assertEqual(e["reward"], hr.BASE_REWARD)
        self.assertEqual(e["npc_name"], "Swoop Thug")

    # ── sampling honours the tunable; the reward still lands ─────────────────
    def test_sample_zero_suppresses_event_not_the_reward(self):
        tunables._TUNABLES["telemetry.grind_kill_sample"] = 0.0
        db, char = _FakeDB(1000), _killer(1000)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=self.DAY))
        self.assertEqual(len(_events()), 0)
        # reward still credited + log persisted
        self.assertEqual(char["credits"], 1000 + hr.BASE_REWARD)
        self.assertEqual(out["total_kills"], 1)

    def test_sample_default_captures(self):
        _run(hr.on_huntable_kill(_FakeDB(), _killer(), _npc(),
                                 day_stamp=self.DAY))
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the completed reward ──────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        db, char = _FakeDB(1000), _killer(1000)
        with mock.patch.object(telemetry, "emit", _boom):
            out = _run(hr.on_huntable_kill(db, char, _npc(),
                                           day_stamp=self.DAY))
        # No crash; the reward committed (credits + log persisted).
        self.assertIsNotNone(out)
        self.assertEqual(char["credits"], 1000 + hr.BASE_REWARD)
        self.assertEqual(out["total_kills"], 1)

    # ── helper unit: schema + str-id coercion + None-drop ────────────────────
    def test_helper_schema(self):
        telemetry.emit_grind_kill(
            7, reward=15, daily_credits=45, at_cap=False, over_cap=False,
            total_kills=3, npc_name="Tusken Raider", room_id=900,
            species="Tusken", faction=None)
        e = _events()[0]
        self.assertEqual(e["ev"], "grind_kill")
        self.assertEqual(e["char_id"], 7)
        self.assertEqual(e["reward"], 15)
        self.assertEqual(e["daily_credits"], 45)
        self.assertEqual(e["total_kills"], 3)
        self.assertEqual(e["npc_name"], "Tusken Raider")
        self.assertEqual(e["room_id"], 900)
        self.assertEqual(e["species"], "Tusken")
        self.assertNotIn("faction", e)         # None extra dropped

    def test_helper_coerces_str_id(self):
        telemetry.emit_grind_kill("42", reward=3)
        self.assertEqual(_events()[0]["char_id"], 42)

    def test_helper_drops_none_room_id(self):
        telemetry.emit_grind_kill(7, reward=3, room_id=None)
        self.assertNotIn("room_id", _events()[0])

    # ── seam wired + tunable registered (drift pins) ─────────────────────────
    def test_seam_calls_helper(self):
        src = (REPO / "engine" / "hunting_rewards.py").read_text(
            encoding="utf-8")
        self.assertIn("emit_grind_kill(", src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.grind_kill_sample:", ty)


if __name__ == "__main__":
    unittest.main()
