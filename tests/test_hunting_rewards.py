# -*- coding: utf-8 -*-
"""
tests/test_hunting_rewards.py — solo-PvE mob-grind reward trickle (2026-06-21).

Pins engine/hunting_rewards.py + the engine/titles.py earned-title grant:
  * the huntable predicate (hostile AND no special-reward marker — no
    double-reward of bounty/anomaly/creature/chain/vendor/intel NPCs);
  * the credit trickle (flat BASE_REWARD, daily soft cap -> token floor,
    day-roll reset);
  * the prestige axis (lifetime kill count + milestone title grant);
  * NO character points are ever awarded (advancement stays RP-primary);
  * the producer hook + +hunting command are wired.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from engine import hunting_rewards as hr


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeDB:
    def __init__(self, credits=1000):
        self._credits = credits
        self.saved = {}

    async def adjust_credits(self, cid, delta, tag, *, allow_negative=True):
        self._credits += delta
        return self._credits

    async def save_character(self, cid, **fields):
        self.saved.update(fields)


def _npc(hostile=True, **markers):
    ai = {"hostile": hostile}
    ai.update(markers)
    return {"id": 99, "name": "Swoop Thug",
            "ai_config_json": json.dumps(ai)}


def _killer(credits=1000, attrs=None):
    return {"id": 5, "name": "Hunter", "credits": credits,
            "vanity_titles": "[]",
            "attributes": json.dumps(attrs or {})}


class TestHuntablePredicate(unittest.TestCase):
    def test_plain_hostile_is_huntable(self):
        self.assertTrue(hr.is_huntable_mob(_npc(hostile=True)))

    def test_non_hostile_is_not_huntable(self):
        self.assertFalse(hr.is_huntable_mob(_npc(hostile=False)))

    def test_every_special_marker_excludes(self):
        for m in hr._SPECIAL_MARKERS:
            self.assertFalse(
                hr.is_huntable_mob(_npc(hostile=True, **{m: True})),
                f"a hostile with {m} must NOT be huntable (double-reward)"
            )

    def test_empty_or_garbage_ai_is_not_huntable(self):
        self.assertFalse(hr.is_huntable_mob({"ai_config_json": "{}"}))
        self.assertFalse(hr.is_huntable_mob({"ai_config_json": "not json"}))
        self.assertFalse(hr.is_huntable_mob({}))


class TestOnHuntableKill(unittest.TestCase):
    DAY = "2026-06-21"

    def test_first_kill_awards_and_logs(self):
        db, char = _FakeDB(1000), _killer(1000)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=self.DAY))
        self.assertIsNotNone(out)
        self.assertEqual(out["reward"], hr.BASE_REWARD)
        self.assertEqual(out["total_kills"], 1)
        self.assertEqual(out["daily_credits"], hr.BASE_REWARD)
        self.assertEqual(char["credits"], 1000 + hr.BASE_REWARD)
        log_d = json.loads(char["attributes"])[hr.HUNT_LOG_KEY]
        self.assertEqual(log_d["kills"], 1)
        self.assertEqual(log_d["day"], self.DAY)

    def test_non_huntable_returns_none_and_no_charge(self):
        db, char = _FakeDB(1000), _killer(1000)
        out = _run(hr.on_huntable_kill(
            db, char, _npc(is_bounty_target=True), day_stamp=self.DAY))
        self.assertIsNone(out)
        self.assertEqual(char["credits"], 1000)

    def test_daily_cap_drops_to_floor(self):
        # Pre-seed the log at the cap so the next kill pays the token floor.
        seed = {hr.HUNT_LOG_KEY: {"kills": 50,
                                  "daily_credits": hr.DAILY_SOFT_CAP,
                                  "day": self.DAY}}
        db, char = _FakeDB(1000), _killer(1000, seed)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=self.DAY))
        self.assertEqual(out["reward"], hr.OVER_CAP_FLOOR)
        self.assertTrue(out["at_cap"])

    def test_day_roll_resets_daily_meter(self):
        seed = {hr.HUNT_LOG_KEY: {"kills": 50,
                                  "daily_credits": hr.DAILY_SOFT_CAP,
                                  "day": "2026-06-20"}}
        db, char = _FakeDB(1000), _killer(1000, seed)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=self.DAY))
        # New day → meter reset → full reward again.
        self.assertEqual(out["reward"], hr.BASE_REWARD)
        self.assertEqual(out["daily_credits"], hr.BASE_REWARD)
        self.assertEqual(out["total_kills"], 51)  # lifetime kills persist

    def test_milestone_title_granted_at_threshold(self):
        thresh, key = hr.TITLE_THRESHOLDS[0]
        seed = {hr.HUNT_LOG_KEY: {"kills": thresh - 1,
                                  "daily_credits": 0, "day": self.DAY}}
        db, char = _FakeDB(1000), _killer(1000, seed)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=self.DAY))
        self.assertEqual(out["total_kills"], thresh)
        self.assertEqual(out["title_key"], key)
        self.assertIsNotNone(out["title_label"])
        self.assertIn(key, json.loads(char["vanity_titles"]))

    def test_no_title_between_thresholds(self):
        seed = {hr.HUNT_LOG_KEY: {"kills": 2, "daily_credits": 0, "day": self.DAY}}
        db, char = _FakeDB(1000), _killer(1000, seed)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=self.DAY))
        self.assertIsNone(out["title_key"])

    def test_newly_earned_title_logic(self):
        self.assertEqual(hr.newly_earned_title(24, 25), "hunter")
        self.assertIsNone(hr.newly_earned_title(25, 26))
        self.assertEqual(hr.newly_earned_title(99, 100), "seasoned_hunter")


class TestNoCharacterPoints(unittest.TestCase):
    def test_module_never_touches_cp(self):
        """Advancement stays RP-primary: the grind engine must not award CP."""
        src = (PROJECT_ROOT / "engine" / "hunting_rewards.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("adjust_character_points", "cp_engine",
                          "award_milestone_cp", "character_points",
                          "award_scene_bonus", "award_kudos"):
            self.assertNotIn(
                forbidden, src,
                f"hunting_rewards must NOT award character points (found "
                f"{forbidden!r}) — grinding pays credits + prestige, never CP."
            )


class TestEarnedTitleGrant(unittest.TestCase):
    def test_grant_is_idempotent_and_resolves_label(self):
        from engine import titles
        db = _FakeDB()
        char = _killer()
        ok = _run(titles.grant_earned_title(db, char, "hunter"))
        self.assertTrue(ok)
        self.assertIn("hunter", json.loads(char["vanity_titles"]))
        # second grant is a no-op
        self.assertFalse(_run(titles.grant_earned_title(db, char, "hunter")))
        # label resolves to the catalog label, not the bare key
        self.assertEqual(titles.title_by_key("hunter")["label"], "the Hunter")

    def test_unknown_key_not_granted(self):
        from engine import titles
        self.assertFalse(_run(titles.grant_earned_title(_FakeDB(), _killer(),
                                                        "not_a_title")))

    def test_earned_titles_not_in_buy_catalog(self):
        """Earned titles must never appear in the +title BUY catalog."""
        from engine import titles
        catalog_keys = {t["key"] for t in titles.VANITY_TITLES}
        for t in titles.EARNED_TITLES:
            self.assertNotIn(t["key"], catalog_keys)


class TestView(unittest.TestCase):
    def test_view_reports_kills_and_next_milestone(self):
        char = _killer(attrs={hr.HUNT_LOG_KEY: {"kills": 10,
                                                "daily_credits": 30,
                                                "day": "2026-06-21"}})
        v = hr.hunting_log_view(char, day_stamp="2026-06-21")
        self.assertEqual(v["kills"], 10)
        self.assertEqual(v["daily_credits"], 30)
        self.assertEqual(v["next_threshold"], hr.TITLE_THRESHOLDS[0][0])

    def test_view_day_rolls_stale_daily_meter(self):
        """After midnight the view must show 0 today, not yesterday's total /
        a stale 'cap reached'."""
        char = _killer(attrs={hr.HUNT_LOG_KEY: {"kills": 10,
                                                "daily_credits": hr.DAILY_SOFT_CAP,
                                                "day": "2026-06-20"}})
        v = hr.hunting_log_view(char, day_stamp="2026-06-21")
        self.assertEqual(v["daily_credits"], 0)


class TestWiring(unittest.TestCase):
    def test_combat_hook_calls_engine(self):
        src = (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("on_huntable_kill", src)
        self.assertIn("is_huntable_mob", src)
        # The reward fires from the dedicated helper at the resolve_round call
        # site (NOT the inert _apply_combat_wear loop — see the seam fix).
        self.assertIn("_award_mob_grind_rewards", src)
        self.assertEqual(
            src.count("await _award_mob_grind_rewards(combat, ctx, _pre_npcs)"), 2,
            "the reward must fire at BOTH resolve_round call sites (normal + admin)"
        )

    def test_command_registered(self):
        gs = (PROJECT_ROOT / "server" / "game_server.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("register_hunting_commands", gs)


# ─────────────────────────────────────────────────────────────────────
# Seam integration — prove the reward ACTUALLY fires on a real NPC death.
# (resolve_round() runs _cleanup() which removes dead combatants before
# _apply_combat_wear, so the reward fires from _award_mob_grind_rewards on
# the pre-resolution snapshot; this drives that helper end to end.)
# ─────────────────────────────────────────────────────────────────────
import types  # noqa: E402


class _FakeSess:
    def __init__(self, char):
        self.character = char
        self.lines = []

    async def send_line(self, text):
        self.lines.append(text)


class _FakeMgr:
    def __init__(self, killer_id, sess):
        self._kid, self._sess = killer_id, sess

    def find_by_character(self, cid):
        return self._sess if int(cid) == self._kid else None


class _SeamDB(_FakeDB):
    def __init__(self, npc_ai=None, credits=1000):
        super().__init__(credits)
        self._npc_ai = npc_ai if npc_ai is not None else {"hostile": True}

    async def get_npc(self, nid):
        return {"id": nid, "name": "Swoop Thug",
                "ai_config_json": json.dumps(self._npc_ai)}


def _dead_npc(npc_id=99, killer_id=5):
    from engine.character import WoundLevel
    return types.SimpleNamespace(
        id=npc_id, is_npc=True, name="Swoop Thug",
        last_attacker_id=killer_id,
        char=types.SimpleNamespace(wound_level=WoundLevel.DEAD),
    )


class TestSeamFires(unittest.TestCase):
    """The _award_mob_grind_rewards helper on the pre-resolution snapshot."""

    def _run_seam(self, *, pre, combatants, npc_ai=None, killer_id=5,
                  online=True):
        from parser.combat_commands import _award_mob_grind_rewards
        killer = _killer(1000)
        sess = _FakeSess(killer)
        mgr = _FakeMgr(killer_id, sess) if online else _FakeMgr(-1, sess)
        combat = types.SimpleNamespace(combatants=combatants)
        ctx = types.SimpleNamespace(db=_SeamDB(npc_ai), session_mgr=mgr)
        _run(_award_mob_grind_rewards(combat, ctx, pre))
        return killer, sess

    def test_killed_huntable_npc_pays_the_killer(self):
        npc = _dead_npc()
        killer, sess = self._run_seam(pre=[npc], combatants={})  # npc removed=killed
        self.assertEqual(killer["credits"], 1000 + hr.BASE_REWARD)
        self.assertEqual(json.loads(killer["attributes"])[hr.HUNT_LOG_KEY]["kills"], 1)
        self.assertTrue(sess.lines, "the killer should be notified")

    def test_survivor_is_not_rewarded(self):
        npc = _dead_npc()
        # npc still in combat.combatants → it survived → no reward
        killer, _ = self._run_seam(pre=[npc], combatants={npc.id: npc})
        self.assertEqual(killer["credits"], 1000)

    def test_special_npc_not_rewarded(self):
        npc = _dead_npc()
        killer, _ = self._run_seam(pre=[npc], combatants={},
                                   npc_ai={"hostile": True,
                                           "is_bounty_target": True})
        self.assertEqual(killer["credits"], 1000)

    def test_offline_killer_not_rewarded(self):
        npc = _dead_npc()
        killer, _ = self._run_seam(pre=[npc], combatants={}, online=False)
        self.assertEqual(killer["credits"], 1000)


if __name__ == "__main__":
    unittest.main()
