# -*- coding: utf-8 -*-
"""tests/test_telemetry_skill_check_rollup.py — T3.19 telemetry READ-SIDE: the
``skill_check`` rollup in ``telemetry.summarize`` + the ``@balance skills``
sub-board.

The PRODUCER half has been wired since the T3.19 skill-check emitter drop:
``engine.skill_checks.perform_skill_check`` — the SINGLE funnel for ALL
out-of-combat dice — emits one ``skill_check`` event per roll carrying
``skill`` / ``difficulty`` / ``success`` / ``margin`` / ``crit`` / ``fumble``.
The emit-site comment states its whole purpose: "one emit captures skill-check
success rates by skill + difficulty band (catalog D — are DCs calibrated)".

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp_income /
objective / wild_encounter / communal / chain_reward / session but DROPPED
``skill_check`` on the floor, and ``@balance`` had no skills board — so the
highest-frequency instrumented chokepoint, the whole-game DC-calibration
signal, appeared nowhere except the generic event-mix count + the raw dump.
This drop adds the consumer: a ``skill_check`` rollup in ``summarize`` (overall
pass rate, crit/fumble, distinct rollers, success rate by WEG difficulty band
and by skill) and a ``@balance skills`` board.

Mirrors the chain- and session-rollup guards: the rollup buckets the REAL
producer field names + tolerates junk; the skill_check key is additive
(siblings unperturbed); the difficulty bands track ``engine.dice.Difficulty``
(no phantom thresholds); the board renders/gates/degrades; and the REAL
``perform_skill_check`` producer feeds the new consumer end-to-end.

Run: python -m pytest tests/test_telemetry_skill_check_rollup.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SW_ERA", "clone_wars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from engine.dice import Difficulty  # noqa: E402
from parser.commands import CommandContext  # noqa: E402
from parser import director_commands as dc  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeSession:
    def __init__(self):
        self.lines: list = []
        self.char_name = "Admin"
        self.account = {"username": "admin"}

    async def send_line(self, msg=""):
        self.lines.append(msg)


def _ctx(session, args=""):
    return CommandContext(
        session=session,
        raw_input=f"@balance {args}".strip(),
        command="@balance",
        args=args,
        args_list=args.split(),
        switches=[],
        db=None,
        session_mgr=None,
    )


# Mirrors the REAL producer envelope (engine/skill_checks.py:317):
#   {phase-less} {char_id, skill, difficulty, roll, success, margin, crit, fumble}
def _check(*, skill="search", difficulty=10, success=True, crit=False,
           fumble=False, char_id=1):
    return {"ts": 100.0, "ev": "skill_check", "char_id": char_id,
            "skill": skill, "difficulty": difficulty,
            "roll": difficulty if success else difficulty - 1,
            "success": success, "margin": 0 if success else -1,
            "crit": crit, "fumble": fumble}


# ── the difficulty bands track engine.dice.Difficulty (no phantom thresholds) ──
class DifficultyBandTests(unittest.TestCase):
    def test_band_boundaries_match_the_live_enum(self):
        # The rollup must bucket by the SAME difficulty levels the game rolls
        # against — a rebalance in engine.dice.Difficulty must fail here, not
        # silently leave this rollup banding to stale constants.
        bounds = [hi for hi, _ in telemetry._DIFFICULTY_BANDS]
        self.assertEqual(bounds, [
            int(Difficulty.VERY_EASY), int(Difficulty.EASY),
            int(Difficulty.MODERATE), int(Difficulty.DIFFICULT),
            int(Difficulty.VERY_DIFFICULT), int(Difficulty.HEROIC),
        ])

    def test_difficulty_band_mapping(self):
        b = telemetry._difficulty_band
        self.assertEqual(b(1), "Very Easy")
        self.assertEqual(b(int(Difficulty.VERY_EASY)), "Very Easy")   # 5
        self.assertEqual(b(int(Difficulty.VERY_EASY) + 1), "Easy")    # 6
        self.assertEqual(b(int(Difficulty.MODERATE)), "Moderate")     # 15
        self.assertEqual(b(int(Difficulty.DIFFICULT)), "Difficult")   # 20
        self.assertEqual(b(int(Difficulty.VERY_DIFFICULT)), "Very Difficult")
        self.assertEqual(b(int(Difficulty.HEROIC)), "Heroic")         # 30
        self.assertEqual(b(int(Difficulty.HEROIC) + 1), "Heroic+")    # 31
        # non-numeric difficulty never raises — it buckets to "?"
        self.assertEqual(b("nope"), "?")
        self.assertEqual(b(None), "?")


# ── summarize: the skill_check rollup ─────────────────────────────────────────
class SummarizeSkillTests(unittest.TestCase):
    def _mix(self):
        return [
            _check(skill="search", difficulty=10, success=True, char_id=1),
            _check(skill="search", difficulty=10, success=False, char_id=2),
            _check(skill="search", difficulty=20, success=True, crit=True,
                   char_id=1),
            _check(skill="sneak", difficulty=15, success=False, fumble=True,
                   char_id=3),
        ]

    def test_top_level_counts(self):
        sk = telemetry.summarize(self._mix())["skill_check"]
        self.assertEqual(sk["checks"], 4)
        self.assertEqual(sk["successes"], 2)
        self.assertEqual(sk["crits"], 1)
        self.assertEqual(sk["fumbles"], 1)
        # distinct non-None char_ids: {1, 2, 3}
        self.assertEqual(sk["rollers"], 3)

    def test_by_band_ordered_easy_to_heroic(self):
        sk = telemetry.summarize(self._mix())["skill_check"]
        # rows are (band, n, ok) in canonical order, only bands with rolls
        self.assertEqual(sk["by_band"], [
            ("Easy", 2, 1),       # the two difficulty-10 checks (1 ok)
            ("Moderate", 1, 0),   # the difficulty-15 sneak (fail)
            ("Difficult", 1, 1),  # the difficulty-20 crit (ok)
        ])

    def test_by_skill_ranked_by_volume(self):
        sk = telemetry.summarize(self._mix())["skill_check"]
        # rows are (skill, n, ok); search (3 rolls, 2 ok) leads sneak (1, 0)
        self.assertEqual(sk["by_skill"], [
            ("search", 3, 2),
            ("sneak", 1, 0),
        ])

    def test_skill_key_additive_other_rollups_intact(self):
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "session", "phase": "login", "char_id": 9},
            _check(skill="con", difficulty=10, success=True, char_id=9),
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal", "skill_check", "session"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["session"]["logins"], 1)
        self.assertEqual(s["skill_check"]["checks"], 1)
        self.assertEqual(s["skill_check"]["successes"], 1)

    def test_empty_and_junk_tolerated(self):
        sk0 = telemetry.summarize([])["skill_check"]
        self.assertEqual(sk0["checks"], 0)
        self.assertEqual(sk0["by_band"], [])
        self.assertEqual(sk0["by_skill"], [])
        self.assertEqual(sk0["rollers"], 0)
        # a malformed difficulty buckets to "?" (last in band order); a missing
        # skill name buckets to "?" — neither crashes the rollup
        sk1 = telemetry.summarize([
            {"ev": "skill_check", "difficulty": "bad", "success": True},
            {"ev": "skill_check", "difficulty": 10, "success": False},
        ])["skill_check"]
        self.assertEqual(sk1["checks"], 2)
        self.assertEqual(sk1["successes"], 1)
        self.assertEqual(dict((b, (n, ok)) for b, n, ok in sk1["by_band"]),
                         {"?": (1, 1), "Easy": (1, 0)})
        self.assertEqual(dict((s, (n, ok)) for s, n, ok in sk1["by_skill"]),
                         {"?": (2, 1)})

    def test_by_skill_capped_at_twelve(self):
        evs = [_check(skill=f"skill_{i}", difficulty=10, success=True)
               for i in range(20)]
        sk = telemetry.summarize(evs)["skill_check"]
        self.assertEqual(sk["checks"], 20)
        self.assertEqual(len(sk["by_skill"]), 12)   # top-12 by volume only


# ── @balance skills board ─────────────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_skill_")
        self._path = os.path.join(self._tmp, "events.jsonl")
        telemetry.configure(path=self._path, enabled=True)

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
            os.rmdir(self._tmp)
        except OSError:
            pass


class BalanceSkillsBoardTests(_IsolatedTelemetryTest):
    def _emit_skill_sample(self):
        telemetry.emit("skill_check", {"char_id": 1, "skill": "search",
                                       "difficulty": 10, "roll": 12,
                                       "success": True, "margin": 2,
                                       "crit": False, "fumble": False})
        telemetry.emit("skill_check", {"char_id": 2, "skill": "search",
                                       "difficulty": 15, "roll": 9,
                                       "success": False, "margin": -6,
                                       "crit": False, "fumble": True})

    def test_skills_subcommand_renders_funnel(self):
        self._emit_skill_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "skills")))
        out = "\n".join(sess.lines)
        self.assertIn("SKILL CHECKS", out)
        self.assertIn("Success rate", out)
        self.assertIn("search", out)
        # other boards are NOT shown under the skills sub
        self.assertNotIn("MOB GRIND", out)

    def test_skill_alias_accepted(self):
        # singular 'skill' is an accepted alias for the board
        self._emit_skill_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "skill")))
        self.assertIn("SKILL CHECKS", "\n".join(sess.lines))

    def test_overview_includes_skills_section(self):
        self._emit_skill_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("SKILL CHECKS", out)
        self.assertIn("SESSIONS / ENGAGEMENT", out)   # siblings still render

    def test_skills_section_absent_under_other_sub(self):
        self._emit_skill_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        self.assertNotIn("SKILL CHECKS", "\n".join(sess.lines))

    def test_skills_board_degrades_with_no_skill_data(self):
        # Some telemetry exists (so the dashboard renders) but no skill checks.
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "skills")))
        self.assertIn("no skill checks recorded", "\n".join(sess.lines))


# ── producer → consumer round-trip (the load-bearing contract) ────────────────
class ProducerToConsumerTests(_IsolatedTelemetryTest):
    @staticmethod
    def _char(char_id=7):
        # Minimal session-shaped char: untrained 'search' rolls Perception 3D,
        # so a difficulty of 1 is a guaranteed pass and 99 a guaranteed fail —
        # deterministic without mocking the dice.
        return {
            "id": char_id,
            "inventory": json.dumps({"items": [], "resources": []}),
            "attributes": json.dumps({"perception": "3D"}),
            "skills": "{}",
            "equipment": "{}",
        }

    def test_real_perform_skill_check_feeds_the_rollup(self):
        # Drive the REAL chokepoint (the same fn every out-of-combat roll goes
        # through), flush to the isolated sink, read it back through the REAL
        # consumer path (read_recent + summarize), and confirm the admin board
        # surfaces it from the same on-disk record.
        from engine.skill_checks import perform_skill_check
        r_pass = perform_skill_check(self._char(), "search", 1,
                                     auto_consume_lead=False)
        r_fail = perform_skill_check(self._char(), "search", 99,
                                     auto_consume_lead=False)
        self.assertTrue(r_pass.success)
        self.assertFalse(r_fail.success)
        telemetry.get_sink().flush()

        events = telemetry.read_recent()
        sk = telemetry.summarize(events)["skill_check"]
        self.assertEqual(sk["checks"], 2)
        self.assertEqual(sk["successes"], 1)
        # both rolled 'search'; the pass (difficulty 1 = Very Easy) and the fail
        # (difficulty 99 = Heroic+) land in distinct bands
        bands = dict((b, (n, ok)) for b, n, ok in sk["by_band"])
        self.assertEqual(bands.get("Very Easy"), (1, 1))
        self.assertEqual(bands.get("Heroic+"), (1, 0))
        self.assertEqual(dict((s, (n, ok)) for s, n, ok in sk["by_skill"]),
                         {"search": (2, 1)})

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "skills")))
        out = "\n".join(sess.lines)
        self.assertIn("SKILL CHECKS", out)
        self.assertIn("search", out)


if __name__ == "__main__":
    unittest.main()
