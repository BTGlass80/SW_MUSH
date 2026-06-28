# -*- coding: utf-8 -*-
"""tests/test_encounter_density_tunables.py — T3.19 config breadth for the
wilderness encounter DENSITY levers (engine/wilderness_encounters.py).

The mob-DENSITY complement to the grind-reward faucet (test_grind_reward_tunables):
the ``@balance encounters`` board (wild_encounter events: fire-rate / reason /
threat-band) lets an operator OBSERVE how often the wilderness offers a huntable
encounter, but the two GLOBAL spawn-pacing levers it informs were hardcoded
module constants — ``ENCOUNTER_COOLDOWN_SECONDS`` (the per-character cooldown the
board's own telemetry comment names, "the 60s cooldown") and
``ANIMAL_EXCLUDER_AVERT_CHANCE`` (the deterrent-device turn-away chance). This
drop externalizes the two to data/tunables.yaml under ``encounter.*`` and reads
them at the USE SITE, closing the observe→tune loop. (``base_chance_per_move`` is
already a per-pool DATA field, so it has no global lever; the module-level
``DEFAULT_BASE_CHANCE_PER_MOVE`` has no runtime consumer and is left untouched —
externalizing a dead constant would be a phantom.)

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override flows through the cooldown gate + the
animal-excluder avert path, a fat-fingered negative cooldown clamps to 0 (no
window underflow) and an out-of-range avert chance clamps to [0,1], a
present-but-null key falls back to the default, a corrupt value can't crash an
encounter roll, and the shipped data/tunables.yaml carries the two keys at their
in-code defaults (a drift pin).

Run: python -m pytest tests/test_encounter_density_tunables.py
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import wilderness_encounters as we  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT


class _FakeRNG:
    """Deterministic rng: ``random()`` returns a fixed mid value (passes a
    base_chance=1.0 roll and lets the avert comparison hinge on the tunable);
    ``randint()`` returns the low bound (picks the first/only pool entry)."""

    def __init__(self, rand: float = 0.5):
        self._rand = rand

    def random(self) -> float:
        return self._rand

    def randint(self, a, b):
        return a


def _region():
    """Minimal region: a 40x40 grid with a one-entry pool whose single hostile
    entry names an npc_template (the creature-library path the excluder targets)."""
    entry = we.EncounterEntry(
        id="thug", type="hostile", weight=1,
        payload={"npc_template": "swoop_thug"},
    )
    pool = we.EncounterPool()
    pool.base_chance_per_move = 1.0   # always passes the chance roll
    pool.entries = [entry]
    return types.SimpleNamespace(
        encounter_pool=pool, grid_width=40, grid_height=40, zone="test_zone",
    )


class EncounterDensityTunableAccessors(unittest.TestCase):
    """The use-site accessors: default fallback, override, clamp, null, corrupt."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(we.cooldown_seconds(), we.ENCOUNTER_COOLDOWN_SECONDS)
        self.assertEqual(we.animal_excluder_avert_chance(),
                         we.ANIMAL_EXCLUDER_AVERT_CHANCE)

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "encounter.cooldown_seconds": 20,
            "encounter.animal_excluder_avert_chance": 0.8,
        })
        self.assertEqual(we.cooldown_seconds(), 20)
        self.assertAlmostEqual(we.animal_excluder_avert_chance(), 0.8)

    def test_cooldown_negative_clamps_to_zero(self):
        # A negative cooldown must not underflow the (now - last) < window check.
        tunables._TUNABLES["encounter.cooldown_seconds"] = -5
        self.assertEqual(we.cooldown_seconds(), 0)

    def test_cooldown_float_truncates_to_int(self):
        tunables._TUNABLES["encounter.cooldown_seconds"] = 90.9
        self.assertEqual(we.cooldown_seconds(), 90)

    def test_avert_clamps_to_probability_range(self):
        # It is compared against random() in [0,1) — out-of-range is meaningless.
        tunables._TUNABLES["encounter.animal_excluder_avert_chance"] = 5.0
        self.assertEqual(we.animal_excluder_avert_chance(), 1.0)
        tunables._TUNABLES["encounter.animal_excluder_avert_chance"] = -2.0
        self.assertEqual(we.animal_excluder_avert_chance(), 0.0)

    def test_present_but_null_falls_back_to_default(self):
        # get_tunable coerces a None (operator typo: `encounter.cooldown_seconds:`).
        tunables._TUNABLES["encounter.cooldown_seconds"] = None
        tunables._TUNABLES["encounter.animal_excluder_avert_chance"] = None
        self.assertEqual(we.cooldown_seconds(), we.ENCOUNTER_COOLDOWN_SECONDS)
        self.assertEqual(we.animal_excluder_avert_chance(),
                         we.ANIMAL_EXCLUDER_AVERT_CHANCE)

    def test_corrupt_value_falls_back_to_default(self):
        # A non-numeric YAML value can't crash an encounter roll — _safe_* default.
        tunables._TUNABLES["encounter.cooldown_seconds"] = "soon"
        tunables._TUNABLES["encounter.animal_excluder_avert_chance"] = "half"
        self.assertEqual(we.cooldown_seconds(), we.ENCOUNTER_COOLDOWN_SECONDS)
        self.assertEqual(we.animal_excluder_avert_chance(),
                         we.ANIMAL_EXCLUDER_AVERT_CHANCE)


class EncounterCooldownTunableEndToEnd(unittest.TestCase):
    """The cooldown override flows through the _is_on_cooldown gate."""

    def setUp(self):
        tunables.reset_tunables()
        we.clear_cooldowns()

    def tearDown(self):
        tunables.reset_tunables()
        we.clear_cooldowns()

    def test_default_window_holds_a_recent_fire_on_cooldown(self):
        # Fired 30s ago, default 60s window → still on cooldown.
        we._encounter_cooldowns[5] = 1000.0
        self.assertTrue(we._is_on_cooldown(5, now=1030.0))

    def test_tightened_window_releases_sooner(self):
        # Same 30s-ago fire, but a 10s window → off cooldown.
        tunables._TUNABLES["encounter.cooldown_seconds"] = 10
        we._encounter_cooldowns[5] = 1000.0
        self.assertFalse(we._is_on_cooldown(5, now=1030.0))

    def test_widened_window_holds_longer(self):
        tunables._TUNABLES["encounter.cooldown_seconds"] = 120
        we._encounter_cooldowns[5] = 1000.0
        self.assertTrue(we._is_on_cooldown(5, now=1090.0))   # 90s < 120s

    def test_zero_cooldown_never_gates(self):
        tunables._TUNABLES["encounter.cooldown_seconds"] = 0
        we._encounter_cooldowns[5] = 1000.0
        self.assertFalse(we._is_on_cooldown(5, now=1000.0))  # elapsed 0 < 0 is False


class EncounterAvertTunableEndToEnd(unittest.TestCase):
    """The avert-chance override flows through the animal-excluder path."""

    def setUp(self):
        tunables.reset_tunables()
        telemetry.reset()
        we.clear_cooldowns()

    def tearDown(self):
        tunables.reset_tunables()
        telemetry.reset()
        we.clear_cooldowns()

    def _roll(self):
        return we._roll_encounter_impl(
            _region(), new_x=20, new_y=20, terrain="desert",
            char={"id": 7}, rng=_FakeRNG(0.5), now=5000.0,
            carried_keys={we.ANIMAL_EXCLUDER_KEY},
        )

    def test_certain_avert_turns_the_creature_away(self):
        # avert=1.0 → 0.5 < 1.0 True → averted (the carrier's device repels it).
        tunables._TUNABLES["encounter.animal_excluder_avert_chance"] = 1.0
        res = self._roll()
        self.assertFalse(res.fired)
        self.assertEqual(res.reason, "averted_by_excluder")

    def test_zero_avert_lets_the_encounter_fire(self):
        # avert=0.0 → 0.5 < 0.0 False → the encounter fires normally.
        tunables._TUNABLES["encounter.animal_excluder_avert_chance"] = 0.0
        res = self._roll()
        self.assertTrue(res.fired)
        self.assertEqual(res.reason, "ok")
        self.assertEqual(res.entry.id, "thug")

    def test_default_avert_behaviour_unchanged_when_unset(self):
        # No tunable loaded + a roll BELOW the 0.5 default → averted (legacy).
        we.clear_cooldowns()
        res = we._roll_encounter_impl(
            _region(), new_x=20, new_y=20, terrain="desert",
            char={"id": 8}, rng=_FakeRNG(0.4), now=5000.0,
            carried_keys={we.ANIMAL_EXCLUDER_KEY},
        )
        self.assertFalse(res.fired)
        self.assertEqual(res.reason, "averted_by_excluder")


class EncounterDensityTunableShipped(unittest.TestCase):
    """Drift pins: the shipped YAML carries the two keys at in-code defaults."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_keys_at_in_code_defaults(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        self.assertEqual(tunables.get_tunable("encounter.cooldown_seconds", -1),
                         we.ENCOUNTER_COOLDOWN_SECONDS)
        self.assertEqual(
            tunables.get_tunable("encounter.animal_excluder_avert_chance", -1),
            we.ANIMAL_EXCLUDER_AVERT_CHANCE)

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("encounter.cooldown_seconds:", ty)
        self.assertIn("encounter.animal_excluder_avert_chance:", ty)

    def test_accessors_read_at_use_site(self):
        # Guard the use-site contract: read through get_tunable, not frozen at
        # import (so an operator edit takes effect on reload).
        src = (REPO / "engine" / "wilderness_encounters.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable("encounter.cooldown_seconds"', src)
        self.assertIn('get_tunable("encounter.animal_excluder_avert_chance"', src)


if __name__ == "__main__":
    unittest.main()
