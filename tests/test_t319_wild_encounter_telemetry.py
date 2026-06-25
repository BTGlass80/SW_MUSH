# -*- coding: utf-8 -*-
"""tests/test_t319_wild_encounter_telemetry.py — T3.19 telemetry breadth for the
mob-DENSITY (encounter-spawn) leg of the grind funnel
(engine/wilderness_encounters.roll_encounter).

The grind-kill emitter (engine/hunting_rewards) captures what a kill PAYS; this
drop captures how often the wilderness even OFFERS a huntable encounter — the
spawn-DENSITY leg. ``roll_encounter`` already returns an ``EncounterRollResult``
for EVERY move (fired or not, with a diagnostic ``reason``), so a thin chokepoint
wrapper over the renamed ``_roll_encounter_impl`` can emit ONE fail-open,
sample-tunable ``wild_encounter`` event observing every outcome — without
threading an emit into each of the impl's early returns.

This suite drives the REAL ``roll_encounter`` with constructed regions + pools
and proves: a fire emits ``fired=True``/``reason=ok`` with the chosen entry +
band + region/zone/planet; each non-firing outcome emits its ``reason``
(``chance_miss`` / ``on_cooldown`` / ``no_eligible_entries`` /
``averted_by_excluder``); the pool-less passthrough (``no_pool_configured``) is
DELIBERATELY NOT emitted; char-id coercion + missing region fields drop cleanly;
the ``telemetry.wild_encounter_sample`` tunable is honoured; and — the
load-bearing contract — a broken sink NEVER changes the roll's result.

Run: python -m pytest tests/test_t319_wild_encounter_telemetry.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from engine import wilderness_encounters as we  # noqa: E402

REPO = PROJECT_ROOT


def _events(ev_type="wild_encounter"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeRng:
    """Deterministic stand-in for the ``random`` module used by roll_encounter.

    ``random()`` and ``randint()`` pop scripted values (falling back to a
    miss-safe default when the script runs dry)."""

    def __init__(self, rand=None, randint=None):
        self._rand = list(rand or [])
        self._randint = list(randint or [])

    def random(self):
        return self._rand.pop(0) if self._rand else 0.99

    def randint(self, a, b):
        return self._randint.pop(0) if self._randint else a


def _entry(eid="tusken_war_party", etype="hostile", weight=1, terrains=None,
           min_band=1, max_band=4, npc_template="tusken_warrior"):
    payload = {"npc_template": npc_template} if npc_template else {}
    return we.EncounterEntry(
        id=eid, type=etype, weight=weight, terrains=list(terrains or []),
        min_band=min_band, max_band=max_band,
        narrative="Bantha horns rise on the dune line ahead...",
        payload=payload,
    )


def _pool(chance=0.04, entries=None):
    p = we.EncounterPool()
    p.base_chance_per_move = chance
    p.entries = entries if entries is not None else [_entry()]
    return p


def _region(pool=None, slug="dune_sea", zone="dune_sea_wastes",
            planet="Tatooine", grid=40):
    return SimpleNamespace(slug=slug, zone=zone, planet=planet,
                           grid_width=grid, grid_height=grid,
                           encounter_pool=pool)


def _roll(region, *, terrain="open_desert", char=None, rng=None, now=1000.0,
          carried_keys=None, band=2):
    return we.roll_encounter(
        region, new_x=20, new_y=20, terrain=terrain,
        char=char if char is not None else {"id": 7},
        rng=rng, now=now, carried_keys=carried_keys, tile_band_rating=band,
    )


class WildEncounterTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()
        we.clear_cooldowns()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()
        we.clear_cooldowns()

    # ── a fire: one event with the full envelope ─────────────────────────────
    def test_fire_emits_one_full_event(self):
        res = _roll(_region(_pool()),
                    rng=_FakeRng(rand=[0.0], randint=[1]), band=3)
        self.assertTrue(res.fired)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["ev"], "wild_encounter")
        self.assertEqual(e["char_id"], 7)
        self.assertTrue(e["fired"])
        self.assertEqual(e["reason"], "ok")
        self.assertEqual(e["band"], 3)
        self.assertEqual(e["region"], "dune_sea")
        self.assertEqual(e["zone"], "dune_sea_wastes")
        self.assertEqual(e["planet"], "Tatooine")
        self.assertEqual(e["entry_id"], "tusken_war_party")
        self.assertEqual(e["entry_type"], "hostile")

    # ── chance miss: emitted, no entry fields ────────────────────────────────
    def test_chance_miss_emits_without_entry(self):
        res = _roll(_region(_pool()), rng=_FakeRng(rand=[0.99]))
        self.assertFalse(res.fired)
        e = _events()[0]
        self.assertFalse(e["fired"])
        self.assertEqual(e["reason"], "chance_miss")
        self.assertNotIn("entry_id", e)
        self.assertNotIn("entry_type", e)

    # ── on cooldown: a second immediate roll reports the 60s gate ────────────
    def test_on_cooldown_emits(self):
        region = _region(_pool())
        _roll(region, rng=_FakeRng(rand=[0.0], randint=[1]), now=1000.0)  # fire
        telemetry.get_sink().drain()  # discard the fire event
        res = _roll(region, now=1010.0)  # 10s later → still on cooldown
        self.assertFalse(res.fired)
        e = _events()[0]
        self.assertEqual(e["reason"], "on_cooldown")
        self.assertFalse(e["fired"])

    # ── chance hit but the pool filters empty for this tile ──────────────────
    def test_no_eligible_entries_emits(self):
        # The only entry is terrain-gated to "ridge"; we move onto "dunes".
        pool = _pool(entries=[_entry(terrains=["ridge"])])
        res = _roll(_region(pool), terrain="dunes", rng=_FakeRng(rand=[0.0]))
        self.assertFalse(res.fired)
        e = _events()[0]
        self.assertEqual(e["reason"], "no_eligible_entries")

    # ── the pool-less passthrough is DELIBERATELY NOT emitted ────────────────
    def test_no_pool_configured_emits_nothing(self):
        res = _roll(_region(pool=None))
        self.assertFalse(res.fired)
        self.assertEqual(res.reason, "no_pool_configured")
        self.assertEqual(len(_events()), 0)

    def test_empty_pool_also_silent(self):
        # base_chance > 0 but no entries → still no_pool_configured → silent.
        res = _roll(_region(_pool(chance=0.04, entries=[])))
        self.assertEqual(res.reason, "no_pool_configured")
        self.assertEqual(len(_events()), 0)

    # ── animal-excluder aversion path ────────────────────────────────────────
    def test_averted_by_excluder_emits(self):
        # chance hit (0.0), pick entry (1), excluder avert roll (0.1 < 0.5).
        res = _roll(_region(_pool()),
                    rng=_FakeRng(rand=[0.0, 0.1], randint=[1]),
                    carried_keys={"animal_excluder"})
        self.assertFalse(res.fired)
        e = _events()[0]
        self.assertEqual(e["reason"], "averted_by_excluder")
        self.assertFalse(e["fired"])
        self.assertNotIn("entry_id", e)   # averted result carries no entry

    # ── char-id coercion + missing region fields drop cleanly ────────────────
    def test_str_char_id_coerced(self):
        # The impl requires an int char-id (production always supplies one), so
        # exercise the emitter's defensive str->int coercion at the helper.
        res = we.EncounterRollResult(fired=False, reason="chance_miss")
        we._emit_wild_encounter_telemetry(
            _region(_pool()), {"id": "42"}, res, 2)
        self.assertEqual(_events()[0]["char_id"], 42)

    def test_missing_region_fields_dropped(self):
        region = _region(_pool(), slug="", zone="", planet="")
        _roll(region, rng=_FakeRng(rand=[0.99]))
        e = _events()[0]
        self.assertNotIn("region", e)
        self.assertNotIn("zone", e)
        self.assertNotIn("planet", e)
        self.assertEqual(e["reason"], "chance_miss")  # core fields intact

    def test_bad_char_id_falls_back_to_zero(self):
        _roll(_region(_pool()), char={"name": "no-id"},
              rng=_FakeRng(rand=[0.99]))
        self.assertEqual(_events()[0]["char_id"], 0)

    # ── sampling honours the tunable; the roll result is unchanged ───────────
    def test_sample_zero_suppresses_event_not_the_roll(self):
        tunables._TUNABLES["telemetry.wild_encounter_sample"] = 0.0
        res = _roll(_region(_pool()), rng=_FakeRng(rand=[0.0], randint=[1]))
        self.assertTrue(res.fired)                  # the roll still fired
        self.assertEqual(res.entry.id, "tusken_war_party")
        self.assertEqual(len(_events()), 0)         # but nothing emitted

    def test_sample_default_captures(self):
        _roll(_region(_pool()), rng=_FakeRng(rand=[0.99]))
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never changes the roll ───────────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        with mock.patch.object(telemetry, "emit", _boom):
            res = _roll(_region(_pool()),
                        rng=_FakeRng(rand=[0.0], randint=[1]))
        # No crash; the roll's result is intact.
        self.assertTrue(res.fired)
        self.assertEqual(res.entry.id, "tusken_war_party")

    # ── exactly one event per roll (no double-emit) ──────────────────────────
    def test_exactly_one_event_per_roll(self):
        _roll(_region(_pool()), rng=_FakeRng(rand=[0.99]))
        self.assertEqual(len(_events()), 1)

    # ── drift pins: the wrapper seam + tunable registration ──────────────────
    def test_wrapper_calls_impl_and_emitter(self):
        src = (REPO / "engine" / "wilderness_encounters.py").read_text(
            encoding="utf-8")
        self.assertIn("def _roll_encounter_impl(", src)
        self.assertIn("def roll_encounter(", src)
        self.assertIn("_emit_wild_encounter_telemetry(", src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.wild_encounter_sample:", ty)


if __name__ == "__main__":
    unittest.main()
