# -*- coding: utf-8 -*-
"""
tests/test_lane_d_ey_akh_flood.py

Lane D — the E'Y-Akh annual flood, a Geonosis-region world event (Geonosis &
Outer Rim §1.4) riding the existing world_events machinery exactly like the
Lane E graded storms.

Contract:
  * FLOOD is a registered, valid event type.
  * Its EventDef is region-scoped (preferred_zones == ["geonosis_ey_akh"]), a
    long/rare set-piece (longer than a storm, rarer than the rarest storm), and
    declares ONLY a consumed mechanical effect (perception_penalty — read by
    skill_checks; anti-phantom, mirroring the storm contract).
  * activate_event("flood") works and scopes its zone; the ZONED effect query
    (get_effects_for_zone) returns the penalty in the E'Y-Akh and NOT in an
    unrelated zone. (The global get_effect path remains coarse — the same
    tech-debt the storms carry — but the zoned path is correctly scoped.)
  * The flood text is B3/Q1 clean and carries the faithful lore (the E'Y-Akh,
    the drowning merdeths, the shells).
  * The +weather command surfaces the flood (it is in the command's weather set).

unittest-based (no pytest) so it runs in the sandbox.
"""
import os
import unittest

from engine.world_events import (
    EventType, EVENT_DEFS, VALID_EVENT_TYPES, WorldEventManager,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Effect keys with a live consumer in the engine (storms use both; the flood
# uses perception_penalty). Declaring anything outside this set would be an
# orphan mechanical field.
CONSUMED_EFFECT_KEYS = {"perception_penalty", "ranged_penalty"}

B3_BANNED = ("imperial", "empire", "stormtrooper", "rebel", "tie ",
             "x-wing", "x wing", "death star", "tie fighter")
Q1_FORBIDDEN = ("poggle", "sun fac", "hadiss", "dooku", "sidious", "grievous",
                "padme", "padmé", "anakin", "obi-wan", "obi wan", "jango")


def _src(rel):
    with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
        return f.read()


class TestFloodEventDef(unittest.TestCase):
    def test_flood_is_a_valid_event_type(self):
        self.assertEqual(EventType.FLOOD.value, "flood")
        self.assertIn("flood", VALID_EVENT_TYPES)
        self.assertIn(EventType.FLOOD, EVENT_DEFS)

    def test_flood_is_region_scoped(self):
        fd = EVENT_DEFS[EventType.FLOOD]
        self.assertEqual(
            fd.preferred_zones, ["geonosis_ey_akh"],
            "the flood must favor the E'Y-Akh zone, not fire as generic weather.",
        )

    def test_flood_declares_only_consumed_effects(self):
        """Anti-phantom: no mechanical-effect key without a live consumer."""
        keys = set(EVENT_DEFS[EventType.FLOOD].mechanical_effects.keys())
        self.assertTrue(
            keys.issubset(CONSUMED_EFFECT_KEYS),
            f"flood declares un-consumed effect(s): {keys - CONSUMED_EFFECT_KEYS}",
        )
        self.assertIn(
            "perception_penalty", keys,
            "the flood should impose a perception penalty (murk/spray/chaos).",
        )

    def test_perception_penalty_has_a_live_consumer(self):
        """Prove the declared effect is actually read somewhere."""
        self.assertIn(
            'get_effect("perception_penalty"', _src("engine/skill_checks.py"),
            "skill_checks must consume perception_penalty for the flood effect to be live.",
        )

    def test_flood_is_long_and_rare(self):
        fd = EVENT_DEFS[EventType.FLOOD]
        storm = EVENT_DEFS[EventType.SANDSTORM]
        sandwhirl = EVENT_DEFS[EventType.SANDWHIRL]
        # A flood lasts longer than an ordinary sandstorm...
        self.assertGreaterEqual(fd.default_duration_min, storm.default_duration_max)
        # ...and is rarer than the rarest storm (smaller per-tick probability).
        self.assertLess(fd.timer_probability, sandwhirl.timer_probability)

    def test_flood_has_effect_text(self):
        self.assertTrue(EVENT_DEFS[EventType.FLOOD].effect_text.strip())


class TestFloodActivation(unittest.TestCase):
    def test_activation_and_zone_scope(self):
        m = WorldEventManager()
        ev = m.activate_event("flood")
        self.assertIsNotNone(ev, "activate_event('flood') should succeed")
        self.assertEqual(ev.zones_affected, ["geonosis_ey_akh"])

    def test_effect_is_zoned_not_leaking_via_zoned_query(self):
        m = WorldEventManager()
        m.activate_event("flood")
        in_zone = m.get_effects_for_zone("geonosis_ey_akh")
        out_zone = m.get_effects_for_zone("streets")
        self.assertEqual(in_zone.get("perception_penalty"), -3,
                         "flood perception penalty must apply in the E'Y-Akh.")
        self.assertEqual(
            out_zone, {},
            "via the zoned query the flood must NOT affect unrelated zones.",
        )


class TestFloodTextAndDisplay(unittest.TestCase):
    def _blob(self):
        fd = EVENT_DEFS[EventType.FLOOD]
        return f"{fd.name} {fd.announce_text} {fd.expire_text}"

    def test_text_is_b3_clean(self):
        low = self._blob().lower()
        for tok in B3_BANNED:
            self.assertNotIn(tok, low, f"flood text carries banned era token {tok!r} (B3).")

    def test_text_is_q1_clean(self):
        low = self._blob().lower()
        for tok in Q1_FORBIDDEN:
            self.assertNotIn(tok, low, f"flood text names canon figure {tok!r} (Q1).")

    def test_text_carries_faithful_lore(self):
        low = self._blob().lower()
        self.assertIn("e'y-akh", low, "the flood should name its locale.")
        self.assertIn("merdeth", low, "the flood should reference the drowning merdeths.")
        self.assertIn("shell", low, "the receding flood should leave merdeth shells.")

    def test_weather_command_surfaces_flood(self):
        src = _src("parser/builtin_commands.py")
        self.assertIn(
            '"flood"', src,
            "the +weather command's weather set must include 'flood' so it displays.",
        )


if __name__ == "__main__":
    unittest.main()
