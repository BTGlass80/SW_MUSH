# -*- coding: utf-8 -*-
"""
tests/test_a3_intelligence_thaw.py — Drop 3 A3: the INTELLIGENCE_THAW event.

A3's core (a faction intel handler that buys sealed reports for credits +
influence, priced by quality/freshness, gated by faction, consuming the report,
metered through the ledger) already shipped as SYN.5
(`engine/intel_handlers.py::handover_intel`). The genuinely-undelivered A3 piece
is the spy playstyle's **"holiday"**: the `INTELLIGENCE_THAW` world event that
doubles the intel CREDIT payout while active (parallel to BOUNTY_SURGE →
hunters, CANTINA_BRAWL → entertainers).

Covers (all DB-free):
  * the event definition (enum + EVENT_DEFS + `intel_pay_mult` effect);
  * a fresh `WorldEventManager` activating it and exposing the multiplier via
    `get_effect`, and the default (no event) being a no-op;
  * the pure `apply_intel_thaw` multiplier (doubles; no-op at/below 1.0;
    garbage-safe; rounds);
  * structural pins that `handover_intel` reads the thaw effect, takes an
    injectable `pay_mult`, applies `apply_intel_thaw`, and surfaces the bonus,
    while leaving influence unscaled.
"""

import os
import sys
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.world_events import (                                       # noqa: E402
    EventType, EVENT_DEFS, VALID_EVENT_TYPES, WorldEventManager,
)
from engine.intel_handlers import (                                     # noqa: E402
    apply_intel_thaw, INTEL_THAW_EFFECT_KEY,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Event definition
# ─────────────────────────────────────────────────────────────────────────────
class TestEventDef(unittest.TestCase):
    def test_enum_and_validset(self):
        self.assertEqual(EventType.INTELLIGENCE_THAW.value, "intelligence_thaw")
        self.assertIn("intelligence_thaw", VALID_EVENT_TYPES)

    def test_def_present_with_intel_pay_mult(self):
        edef = EVENT_DEFS[EventType.INTELLIGENCE_THAW]
        self.assertEqual(edef.mechanical_effects.get("intel_pay_mult"), 2.0)
        self.assertGreater(edef.default_duration_min, 0)
        # Global event (intel desks are faction-wide, not zone-local).
        self.assertEqual(edef.preferred_zones, [])

    def test_announce_text_is_era_clean(self):
        # B3 era-cleanness: no GCW terms in the new production string.
        text = (EVENT_DEFS[EventType.INTELLIGENCE_THAW].announce_text +
                EVENT_DEFS[EventType.INTELLIGENCE_THAW].expire_text).lower()
        for banned in ("empire", "imperial", "rebel", "stormtrooper",
                       "tie ", "x-wing"):
            self.assertNotIn(banned, text)


# ─────────────────────────────────────────────────────────────────────────────
# 2. WorldEventManager exposes the effect when active
# ─────────────────────────────────────────────────────────────────────────────
class TestManagerEffect(unittest.TestCase):
    def test_default_no_event_is_neutral(self):
        mgr = WorldEventManager()
        self.assertEqual(mgr.get_effect(INTEL_THAW_EFFECT_KEY, 1.0), 1.0)

    def test_active_thaw_exposes_multiplier(self):
        mgr = WorldEventManager()
        active = mgr.activate_event("intelligence_thaw")
        self.assertIsNotNone(active)   # fresh manager clears cooldowns
        self.assertEqual(mgr.get_effect(INTEL_THAW_EFFECT_KEY, 1.0), 2.0)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pure multiplier
# ─────────────────────────────────────────────────────────────────────────────
class TestApplyThaw(unittest.TestCase):
    def test_doubles(self):
        self.assertEqual(apply_intel_thaw(500, 2.0), 1000)

    def test_at_or_below_one_is_noop(self):
        self.assertEqual(apply_intel_thaw(500, 1.0), 500)
        self.assertEqual(apply_intel_thaw(500, 0.5), 500)

    def test_garbage_safe(self):
        self.assertEqual(apply_intel_thaw(500, None), 500)
        self.assertEqual(apply_intel_thaw(500, "x"), 500)

    def test_rounds(self):
        self.assertEqual(apply_intel_thaw(333, 1.5), 500)   # 499.5 → 500


# ─────────────────────────────────────────────────────────────────────────────
# 4. Structural pins on handover_intel
# ─────────────────────────────────────────────────────────────────────────────
def _src(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_handover_applies_thaw(self):
        src = _src("engine", "intel_handlers.py")
        self.assertIn("pay_mult", src)                     # injectable param
        self.assertIn("apply_intel_thaw(credits", src)     # applied to credits
        self.assertIn('get_effect(', src)                  # reads live effect
        self.assertIn("INTEL_THAW_EFFECT_KEY", src)

    def test_influence_left_unscaled(self):
        # The thaw multiplies credits only; influence sampling must not be
        # passed through apply_intel_thaw.
        src = _src("engine", "intel_handlers.py")
        self.assertNotIn("apply_intel_thaw(influence", src)

    def test_bonus_surfaced(self):
        src = _src("engine", "intel_handlers.py")
        self.assertIn("Intelligence Thaw", src)


if __name__ == "__main__":
    unittest.main()
