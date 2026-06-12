# -*- coding: utf-8 -*-
"""
tests/test_t5_scavenge_hook.py — Drop 14 (2026-06-12).

Pins the Coruscant Underworld scavenge faucet for ``scavenged_republic_tech``
implemented in ``engine/harvest.py::compute_harvest_payout`` via the new
``region_slug`` kwarg and ``_REGION_SCAVENGE_BONUS`` table.

Test sections
─────────────
  1. TestScavengeFires          — success path, roll forced to hit
  2. TestScavengeMisses         — same call but roll forced to miss
  3. TestScavengeRegionScoped   — wrong region → never fires
  4. TestScavengeTierIndependent — foothold (un-owned) tier still fires
  5. TestScavengeQualityPin     — output quality is exactly 75.0, not 100
  6. TestScavengeFailedCheckShape — margin=-1 → scavenge_bonus False in dict
  7. TestScavengeStructuralPins — RESOURCE_TYPES membership; tunable band
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────
# Deterministic stub RNG
# ──────────────────────────────────────────────────────────────────────

class _StubRng:
    """Minimal RNG stub for compute_harvest_payout injection.

    ``randint`` returns a fixed in-band value so credit sampling is
    deterministic. ``random`` returns a queued float so scavenge-roll
    outcomes are controlled precisely.

    Usage::

        rng = _StubRng(credit_val=200, random_vals=[0.01])
        # credit_val lands in any lawless/foothold band (150..300)
        # random_vals[0] = 0.01  < 0.07  → scavenge fires
    """

    def __init__(self, *, credit_val: int = 200,
                 random_vals: list[float] | None = None):
        self._credit_val = credit_val
        self._random_vals = list(random_vals or [])
        self._random_idx = 0

    def randint(self, a: int, b: int) -> int:  # noqa: N802
        # Clamp to the actual band so it never produces an out-of-range value.
        return max(a, min(b, self._credit_val))

    def random(self) -> float:  # noqa: N802
        if self._random_idx < len(self._random_vals):
            val = self._random_vals[self._random_idx]
            self._random_idx += 1
            return val
        # Fall through: return a value that will NOT hit any bonus (safe default).
        return 0.99


# ──────────────────────────────────────────────────────────────────────
# 1. TestScavengeFires — roll forced to succeed
# ──────────────────────────────────────────────────────────────────────

class TestScavengeFires(unittest.TestCase):
    """With rng.random() = 0.01 < 0.07, the bonus fires."""

    def setUp(self):
        from engine.harvest import compute_harvest_payout
        # lawless/foothold has NO _t5_rare_chance, so only ONE rng.random()
        # call is made (the scavenge roll).  0.01 < 0.07 → fires.
        self.out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=5,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=200, random_vals=[0.01]),
        )

    def test_scavenge_bonus_true(self):
        self.assertTrue(self.out["scavenge_bonus"])

    def test_stack_present(self):
        types = [s["type"] for s in self.out["resource_stacks"]]
        self.assertIn("scavenged_republic_tech", types)

    def test_stack_quantity_is_one(self):
        stacks = [s for s in self.out["resource_stacks"]
                  if s["type"] == "scavenged_republic_tech"]
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]["quantity"], 1)

    def test_stack_quality_is_75(self):
        stacks = [s for s in self.out["resource_stacks"]
                  if s["type"] == "scavenged_republic_tech"]
        self.assertEqual(stacks[0]["quality"], 75.0)


# ──────────────────────────────────────────────────────────────────────
# 2. TestScavengeMisses — roll forced to fail
# ──────────────────────────────────────────────────────────────────────

class TestScavengeMisses(unittest.TestCase):
    """With rng.random() = 0.50 > 0.07, the bonus does not fire."""

    def setUp(self):
        from engine.harvest import compute_harvest_payout
        self.out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=5,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=200, random_vals=[0.50]),
        )

    def test_scavenge_bonus_false(self):
        self.assertFalse(self.out["scavenge_bonus"])

    def test_no_scavenged_republic_tech_stack(self):
        types = [s["type"] for s in self.out["resource_stacks"]]
        self.assertNotIn("scavenged_republic_tech", types)


# ──────────────────────────────────────────────────────────────────────
# 3. TestScavengeRegionScoped — wrong region never fires
# ──────────────────────────────────────────────────────────────────────

class TestScavengeRegionScoped(unittest.TestCase):
    """Bonus is Coruscant-only; other regions + None are unaffected even
    if the RNG would have rolled under 0.07."""

    def _check_no_fire(self, region_slug):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=5,
            region_slug=region_slug,
            # 0.01 < 0.07 — would fire IF the region matched.
            rng=_StubRng(credit_val=200, random_vals=[0.01]),
        )
        self.assertFalse(out["scavenge_bonus"],
                         f"scavenge_bonus should be False for {region_slug!r}")
        types = [s["type"] for s in out["resource_stacks"]]
        self.assertNotIn("scavenged_republic_tech", types,
                         f"no srt stack for {region_slug!r}")

    def test_dune_sea_no_fire(self):
        self._check_no_fire("dune_sea")

    def test_none_no_fire(self):
        self._check_no_fire(None)

    def test_empty_string_no_fire(self):
        self._check_no_fire("")


# ──────────────────────────────────────────────────────────────────────
# 4. TestScavengeTierIndependent — fires at foothold (un-owned) tier
# ──────────────────────────────────────────────────────────────────────

class TestScavengeTierIndependent(unittest.TestCase):
    """The bonus fires regardless of influence_tier, including foothold
    (the tier used for un-owned regions via _UNOWNED_FALLBACK_TIER).
    Contrast: the generic _t5_rare_chance only exists on Control-tier rows."""

    def test_fires_at_foothold(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",   # un-owned / weakest tier
            margin=5,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=200, random_vals=[0.01]),
        )
        self.assertTrue(out["scavenge_bonus"],
                        "scavenge bonus must fire even at foothold tier")
        types = [s["type"] for s in out["resource_stacks"]]
        self.assertIn("scavenged_republic_tech", types)

    def test_fires_at_dominant(self):
        from engine.harvest import compute_harvest_payout
        # lawless/dominant has no _t5_rare_chance → single rng.random() call
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="dominant",
            margin=5,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=300, random_vals=[0.01]),
        )
        self.assertTrue(out["scavenge_bonus"])
        types = [s["type"] for s in out["resource_stacks"]]
        self.assertIn("scavenged_republic_tech", types)


# ──────────────────────────────────────────────────────────────────────
# 5. TestScavengeQualityPin — quality must be exactly 75.0, NOT 100
# ──────────────────────────────────────────────────────────────────────

class TestScavengeQualityPin(unittest.TestCase):
    """Quality 75.0 is the T5 min-quality floor.
    Quality 100 is reserved for SYN.8 anomaly drops — must NOT appear here."""

    def test_quality_is_75_not_100(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=5,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=200, random_vals=[0.01]),
        )
        stacks = [s for s in out["resource_stacks"]
                  if s["type"] == "scavenged_republic_tech"]
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]["quality"], 75.0)
        self.assertNotEqual(stacks[0]["quality"], 100.0,
                             "q100 is reserved for SYN.8 anomaly drops")


# ──────────────────────────────────────────────────────────────────────
# 6. TestScavengeFailedCheckShape — margin=-1 → consistent dict shape
# ──────────────────────────────────────────────────────────────────────

class TestScavengeFailedCheckShape(unittest.TestCase):
    """A failed skill check (margin < 0) returns an empty payout dict
    that still contains scavenge_bonus=False for shape consistency."""

    def test_failed_check_has_scavenge_bonus_key(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=-1,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=200, random_vals=[0.01]),
        )
        self.assertIn("scavenge_bonus", out)
        self.assertFalse(out["scavenge_bonus"])
        self.assertEqual(out["resource_stacks"], [])
        self.assertEqual(out["credits_kept"], 0)

    def test_failed_check_no_srt_stack(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=-1,
            region_slug="coruscant_underworld",
            rng=_StubRng(credit_val=200, random_vals=[0.01]),
        )
        types = [s["type"] for s in out["resource_stacks"]]
        self.assertNotIn("scavenged_republic_tech", types)


# ──────────────────────────────────────────────────────────────────────
# 7. TestScavengeStructuralPins — module-level invariants
# ──────────────────────────────────────────────────────────────────────

class TestScavengeStructuralPins(unittest.TestCase):
    """Module-level invariants that must not regress."""

    def test_srt_in_resource_types(self):
        """add_resource accepts scavenged_republic_tech (it is in RESOURCE_TYPES)."""
        from engine.crafting import RESOURCE_TYPES
        self.assertIn("scavenged_republic_tech", RESOURCE_TYPES)

    def test_srt_in_t5_wilderness_materials(self):
        """Excluded from normal harvest yield table (T5-gated)."""
        from engine.crafting import T5_WILDERNESS_MATERIALS
        self.assertIn("scavenged_republic_tech", T5_WILDERNESS_MATERIALS)

    def test_coruscant_scavenge_chance_in_band(self):
        """TUN.harvest.coruscant_scavenge_chance is within the 5-10% band."""
        from engine.harvest import _CORUSCANT_SCAVENGE_CHANCE
        self.assertGreaterEqual(_CORUSCANT_SCAVENGE_CHANCE, 0.05)
        self.assertLessEqual(_CORUSCANT_SCAVENGE_CHANCE, 0.10)

    def test_region_scavenge_bonus_table_has_coruscant(self):
        from engine.harvest import _REGION_SCAVENGE_BONUS
        self.assertIn("coruscant_underworld", _REGION_SCAVENGE_BONUS)
        entry = _REGION_SCAVENGE_BONUS["coruscant_underworld"]
        self.assertEqual(entry["target"], "scavenged_republic_tech")
        self.assertEqual(entry["quality"], 75.0)

    def test_success_payout_has_scavenge_bonus_key(self):
        """Success-path dict always contains scavenge_bonus key."""
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=5,
            region_slug=None,
            rng=_StubRng(credit_val=200, random_vals=[0.99]),
        )
        self.assertIn("scavenge_bonus", out)

    def test_failed_payout_has_scavenge_bonus_key(self):
        """Failed-path dict always contains scavenge_bonus key."""
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless",
            influence_tier="foothold",
            margin=-1,
            region_slug=None,
            rng=_StubRng(),
        )
        self.assertIn("scavenge_bonus", out)


if __name__ == "__main__":
    unittest.main()
