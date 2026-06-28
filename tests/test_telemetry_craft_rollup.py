# -*- coding: utf-8 -*-
"""tests/test_telemetry_craft_rollup.py — T3.19 telemetry READ-SIDE: the
``craft`` rollup in ``telemetry.summarize`` + the ``@balance craft`` board.

The PRODUCER half has been wired for a while: ``engine/crafting.py``'s
``resolve_craft`` fires one fail-open ``craft`` event at the unified crafting
completion chokepoint, carrying:

  - ``schematic`` / ``output_key`` — the recipe + its produced item;
  - ``skill`` / ``difficulty``     — the gated skill + its target number;
  - ``success`` / ``partial`` / ``fumble`` — the outcome distribution (a partial
                                     is a success that produced a lower-quality
                                     item, so it carries ``success=True`` AND
                                     ``partial=True``);
  - ``quality``                    — the produced item's quality multiplier
                                     (0 when nothing was produced — a full
                                     failure or a fumble);
  - ``critical`` / ``margin`` / ``experiment`` — the roll context.

But the CONSUMER half was missing: ``summarize`` rolled up grind / cp /
objective / wild_encounter / communal / chain / session / skill_check / economy
/ progression / command and silently DROPPED ``craft`` on the floor, and
``@balance`` had no craft board — so the per-schematic success/partial/fumble +
quality distribution (the direct tuning signal for the ``QUALITY_MULT_*`` knobs
and per-recipe difficulty) appeared nowhere but the generic event-mix count +
the raw dump. This drop adds the consumer: a ``craft`` rollup → ``@balance
craft``.

Mirrors the chain / session / skill_check / economy / progression / command
rollup guards: the rollup buckets the REAL producer field names + tolerates
junk; the new key is additive (siblings unperturbed); the board renders /
aliases / gates / degrades; the REAL ``resolve_craft`` producer feeds the
consumer end-to-end; and a source-scoped contract guard pins the emit-site
field names this rollup reads (no-phantom, both directions).

Run: python -m pytest tests/test_telemetry_craft_rollup.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

os.environ.setdefault("SW_ERA", "clone_wars")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser.commands import CommandContext  # noqa: E402
from parser import director_commands as dc  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeSession:
    def __init__(self):
        self.lines: list = []
        self.char_name = "Admin"
        self.account = {"username": "admin"}
        self.character = None

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


# ── Records mirroring the REAL producer envelope (resolve_craft) ───────────────
def _craft_mix():
    return [
        # full success, mid quality, schematic A (easy DC 8 → "Easy" band).
        {"ev": "craft", "schematic": "blaster_mod", "output_key": "blaster_mod",
         "skill": "armor repair", "difficulty": 8, "success": True,
         "partial": False, "fumble": False, "quality": 60.0,
         "critical": False, "margin": 4, "experiment": False, "char_id": 1},
        # crit success, high quality, schematic A.
        {"ev": "craft", "schematic": "blaster_mod", "output_key": "blaster_mod",
         "skill": "armor repair", "difficulty": 8, "success": True,
         "partial": False, "fumble": False, "quality": 80.0,
         "critical": True, "margin": 12, "experiment": False, "char_id": 2},
        # partial: a near-miss still produces a lower-quality item → success
        # True AND partial True, schematic B (moderate DC 13 → "Moderate" band).
        {"ev": "craft", "schematic": "medpac", "output_key": "medpac",
         "skill": "first aid", "difficulty": 13, "success": True,
         "partial": True, "fumble": False, "quality": 30.0,
         "critical": False, "margin": -2, "experiment": False, "char_id": 1},
        # full failure: nothing produced (quality 0), retryable, schematic B.
        {"ev": "craft", "schematic": "medpac", "output_key": "medpac",
         "skill": "first aid", "difficulty": 13, "success": False,
         "partial": False, "fumble": False, "quality": 0.0,
         "critical": False, "margin": -8, "experiment": False, "char_id": 1},
        # fumble: materials ruined, nothing produced, an EXPERIMENT, schematic B.
        {"ev": "craft", "schematic": "medpac", "output_key": "medpac",
         "skill": "first aid", "difficulty": 13, "success": False,
         "partial": False, "fumble": True, "quality": 0.0,
         "critical": False, "margin": -1, "experiment": True, "char_id": 3},
    ]


# ── 1. The craft rollup buckets the real producer field names ─────────────────
class SummarizeCraftTests(unittest.TestCase):
    def setUp(self):
        self.c = telemetry.summarize(_craft_mix())["craft"]

    def test_outcome_totals(self):
        c = self.c
        self.assertEqual(c["crafts"], 5)
        # a partial carries success=True, so it counts toward successes.
        self.assertEqual(c["successes"], 3)   # full + crit + partial
        self.assertEqual(c["partials"], 1)
        self.assertEqual(c["fumbles"], 1)
        self.assertEqual(c["crits"], 1)
        self.assertEqual(c["experiments"], 1)

    def test_avg_quality_excludes_zero_quality_outcomes(self):
        # Only the three produced items (60 + 80 + 30) count; the full failure
        # and the fumble carry quality 0 and must NOT drag the mean down.
        self.assertAlmostEqual(self.c["avg_quality"], (60.0 + 80.0 + 30.0) / 3)

    def test_distinct_crafters(self):
        self.assertEqual(self.c["crafters"], 3)   # char_id 1, 2, 3

    def test_by_band_is_canonical_order_with_success_rate(self):
        # difficulty 8 → "Easy", difficulty 13 → "Moderate"; canonical order.
        rows = self.c["by_band"]
        self.assertEqual(rows[0], ("Easy", 2, 2))       # both easy crafts ok
        self.assertEqual(rows[1], ("Moderate", 3, 1))   # only the partial ok

    def test_by_schematic_ranked_by_volume_with_quality(self):
        # medpac (3 crafts) outranks blaster_mod (2); each row is
        # (schematic, crafts, successes, mean-quality-over-produced).
        rows = self.c["by_schematic"]
        self.assertEqual(rows[0][0], "medpac")
        self.assertEqual(rows[0][1], 3)
        self.assertEqual(rows[0][2], 1)                 # only the partial ok
        self.assertAlmostEqual(rows[0][3], 30.0)        # one produced item @30
        self.assertEqual(rows[1][0], "blaster_mod")
        self.assertEqual(rows[1][1], 2)
        self.assertEqual(rows[1][2], 2)
        self.assertAlmostEqual(rows[1][3], 70.0)        # (60 + 80) / 2


# ── 2. Edge cases: junk tolerance + additivity ────────────────────────────────
class SummarizeCraftEdgeTests(unittest.TestCase):
    def test_empty(self):
        c = telemetry.summarize([])["craft"]
        self.assertEqual(c["crafts"], 0)
        self.assertEqual(c["successes"], 0)
        self.assertEqual(c["avg_quality"], 0.0)
        self.assertEqual(c["crafters"], 0)
        self.assertEqual(c["by_band"], [])
        self.assertEqual(c["by_schematic"], [])

    def test_junk_tolerated(self):
        # Missing fields must not crash; the event still counts.
        c = telemetry.summarize([
            {"ev": "craft"},                              # no outcome/quality
            {"ev": "craft", "success": True},             # no quality/schematic
        ])["craft"]
        self.assertEqual(c["crafts"], 2)
        self.assertEqual(c["successes"], 1)
        self.assertEqual(c["avg_quality"], 0.0)           # no quality>0 anywhere
        # a malformed difficulty buckets under "?"; a missing schematic under "?"
        self.assertEqual(dict((b, n) for b, n, _ in c["by_band"]).get("?"), 2)
        self.assertEqual(c["by_schematic"][0][0], "?")
        self.assertEqual(c["crafters"], 0)                # no char_id anywhere

    def test_non_numeric_quality_ignored(self):
        c = telemetry.summarize([
            {"ev": "craft", "success": True, "quality": "high", "char_id": 1},
        ])["craft"]
        self.assertEqual(c["crafts"], 1)
        self.assertEqual(c["avg_quality"], 0.0)           # "high" is not >0

    def test_craft_key_additive_other_rollups_intact(self):
        s = telemetry.summarize([
            {"ts": 1.0, "ev": "grind_kill", "char_id": 1, "reward": 12,
             "npc_name": "Swoop Thug"},
            {"ts": 2.0, "ev": "craft", "schematic": "medpac", "success": True,
             "quality": 40.0, "difficulty": 10, "char_id": 1},
        ])
        for key in ("grind", "cp_income", "objective", "chain",
                    "wild_encounter", "communal", "skill_check", "session",
                    "economy", "progression", "command", "craft"):
            self.assertIn(key, s)
        self.assertEqual(s["grind"]["kills"], 1)
        self.assertEqual(s["craft"]["crafts"], 1)
        self.assertEqual(s["craft"]["successes"], 1)

    def test_unknown_event_lands_only_in_by_type(self):
        s = telemetry.summarize([{"ev": "garbage_type", "x": 1}])
        self.assertEqual(s["craft"]["crafts"], 0)
        self.assertIn("garbage_type", dict(s["by_type"]))


# ── 3. The @balance craft board ───────────────────────────────────────────────
class _IsolatedTelemetryTest(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        self._tmp = tempfile.mkdtemp(prefix="swmush_tele_craft_")
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


class BalanceCraftBoardTests(_IsolatedTelemetryTest):
    def _emit_craft_sample(self):
        telemetry.emit("craft", {"schematic": "blaster_mod", "success": True,
                                 "partial": False, "fumble": False,
                                 "quality": 65.0, "difficulty": 8,
                                 "char_id": 1})
        telemetry.emit("craft", {"schematic": "medpac", "success": False,
                                 "partial": False, "fumble": True,
                                 "quality": 0.0, "difficulty": 13,
                                 "char_id": 2})

    def test_craft_subcommand_renders(self):
        self._emit_craft_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "craft")))
        out = "\n".join(sess.lines)
        self.assertIn("CRAFTING", out)
        self.assertIn("Crafts", out)
        self.assertIn("Avg quality", out)
        self.assertIn("blaster_mod", out)     # top schematic
        # other boards are NOT shown under the craft sub
        self.assertNotIn("MOB GRIND", out)

    def test_craft_aliases_accepted(self):
        self._emit_craft_sample()
        for alias in ("craft", "crafting", "crafts"):
            sess = _FakeSession()
            _run(dc.BalanceCommand().execute(_ctx(sess, alias)))
            out = "\n".join(sess.lines)
            self.assertIn("CRAFTING", out,
                          f"alias {alias!r} did not render")

    def test_overview_includes_craft_section(self):
        self._emit_craft_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess)))
        out = "\n".join(sess.lines)
        self.assertIn("CRAFTING", out)
        self.assertIn("COMMAND USAGE", out)   # siblings still render

    def test_craft_section_absent_under_other_sub(self):
        self._emit_craft_sample()
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "grind")))
        out = "\n".join(sess.lines)
        self.assertNotIn("CRAFTING", out)

    def test_craft_board_degrades_with_no_craft_data(self):
        telemetry.emit("grind_kill", {"char_id": 1, "reward": 5,
                                      "npc_name": "Womp Rat"})
        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "craft")))
        out = "\n".join(sess.lines)
        self.assertIn("no craft attempts recorded", out)


# ── 4. Load-bearing contract: the REAL producer feeds the consumer ────────────
class RealProducerEndToEndTests(_IsolatedTelemetryTest):
    def test_real_resolve_craft_reaches_the_board(self):
        # Drive the actual producer (engine.crafting.resolve_craft) — not
        # hand-built records — then read back through the real read-side and
        # render the board. A producer that renames a field or stops emitting
        # is caught. An empty-components schematic keeps base quality at the
        # 50.0 default with no DB/inventory needed.
        from engine import crafting

        char = {"id": 7, "name": "Tinker"}
        schem = {
            "key": "field_medkit", "name": "Field Medkit",
            "output_key": "field_medkit", "skill_required": "first aid",
            "difficulty": 10, "components": [],
        }
        # A clean SUCCESS roll (no fumble, positive margin) → produces an item.
        scr = types.SimpleNamespace(
            success=True, fumble=False, critical_success=False, margin=5)
        outcome = crafting.resolve_craft(char, schem, scr, experiment=False)
        self.assertTrue(outcome["success"])
        self.assertGreater(outcome["quality"], 0)

        events = telemetry.read_recent()
        c = telemetry.summarize(events)["craft"]
        self.assertEqual(c["crafts"], 1)
        self.assertEqual(c["successes"], 1)
        self.assertEqual(c["crafters"], 1)                 # char_id 7
        self.assertGreater(c["avg_quality"], 0)
        # the schematic key the producer emitted reaches the per-recipe board
        self.assertEqual(c["by_schematic"][0][0], "field_medkit")

        sess = _FakeSession()
        _run(dc.BalanceCommand().execute(_ctx(sess, "craft")))
        out = "\n".join(sess.lines)
        self.assertIn("CRAFTING", out)
        self.assertIn("field_medkit", out)


# ── 5. No-phantom, both directions: pin the inline producer field names ────────
class ProducerFieldContractTests(unittest.TestCase):
    """``craft`` is emitted INLINE in ``resolve_craft`` (the fields are built in
    the function body, not in a standalone helper). Pin the exact field names
    this rollup reads — scoped to the function — so a producer that renames
    ``success`` / ``partial`` / ``fumble`` / ``quality`` / ``difficulty`` /
    ``schematic`` / ``critical`` / ``experiment`` fails loudly here.
    """

    @staticmethod
    def _func_block(rel_path: str, marker: str, span: int = 2400) -> str:
        with open(PROJECT_ROOT / rel_path, "r", encoding="utf-8") as fh:
            src = fh.read()
        i = src.index(marker)
        return src[i:i + span]

    def test_craft_emit_fields(self):
        blk = self._func_block("engine/crafting.py", "def resolve_craft")
        self.assertIn('"craft"', blk,
                      "craft telemetry no longer emits the 'craft' event")
        for field in ('"schematic"', '"difficulty"', '"success"', '"partial"',
                      '"fumble"', '"quality"', '"critical"', '"experiment"',
                      '"char_id"'):
            self.assertIn(field, blk,
                          f"craft emit no longer carries {field}")


if __name__ == "__main__":
    unittest.main()
