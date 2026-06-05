# -*- coding: utf-8 -*-
"""
tests/test_a5_spice_demand.py — Drop 3 A5 (partial): the SPICE_DEMAND event.

A5's centerpiece (route the sabacc den rake to a controlling Hutt-org treasury —
the "criminal empire" loop) is deferred: it needs a cantina/den room → controlling
org lookup, which the current region-ownership model (wilderness-only) doesn't
provide. This drop ships the self-contained A5 piece: the Hutt/criminal playstyle's
"holiday" — the SPICE_DEMAND world event that doubles smuggling payouts while
active (parallel to INTELLIGENCE_THAW → spy).

Notably, wiring SPICE_DEMAND made `smuggling_pay_mult` LIVE for the first time —
it was previously dormant (declared on the legacy Imperial-crackdown event def but
read by no consumer).

Covers (all DB-free):
  * the event definition (enum + EVENT_DEFS + `smuggling_pay_mult` effect);
  * a fresh `WorldEventManager` activating it and exposing the multiplier;
  * the pure `apply_smuggling_demand` helper (doubles + bonus / no-op ≤1.0 /
    garbage-safe / rounds);
  * structural pins that the smuggling payout reads the effect + applies the
    helper, and a B3 era-cleanness pin on the new strings.
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
from engine.smuggling import (                                          # noqa: E402
    apply_smuggling_demand, SMUGGLING_DEMAND_EFFECT_KEY,
)


class TestEventDef(unittest.TestCase):
    def test_enum_and_validset(self):
        self.assertEqual(EventType.SPICE_DEMAND.value, "spice_demand")
        self.assertIn("spice_demand", VALID_EVENT_TYPES)

    def test_def_present_with_smuggling_mult(self):
        edef = EVENT_DEFS[EventType.SPICE_DEMAND]
        self.assertEqual(edef.mechanical_effects.get("smuggling_pay_mult"), 2.0)
        self.assertGreater(edef.default_duration_min, 0)
        self.assertEqual(edef.preferred_zones, [])   # global

    def test_announce_text_is_era_clean(self):
        text = (EVENT_DEFS[EventType.SPICE_DEMAND].announce_text +
                EVENT_DEFS[EventType.SPICE_DEMAND].expire_text).lower()
        for banned in ("empire", "imperial", "rebel", "stormtrooper",
                       "tie ", "x-wing"):
            self.assertNotIn(banned, text)


class TestManagerEffect(unittest.TestCase):
    def test_default_no_event_is_neutral(self):
        mgr = WorldEventManager()
        self.assertEqual(mgr.get_effect(SMUGGLING_DEMAND_EFFECT_KEY, 1.0), 1.0)

    def test_active_event_exposes_multiplier(self):
        mgr = WorldEventManager()
        active = mgr.activate_event("spice_demand")
        self.assertIsNotNone(active)   # fresh manager clears cooldowns
        self.assertEqual(mgr.get_effect(SMUGGLING_DEMAND_EFFECT_KEY, 1.0), 2.0)


class TestApplyDemand(unittest.TestCase):
    def test_doubles_with_bonus(self):
        new, bonus = apply_smuggling_demand(1000, 2.0)
        self.assertEqual(new, 2000)
        self.assertEqual(bonus, 1000)

    def test_at_or_below_one_is_noop(self):
        self.assertEqual(apply_smuggling_demand(1000, 1.0), (1000, 0))
        self.assertEqual(apply_smuggling_demand(1000, 0.5), (1000, 0))

    def test_garbage_safe(self):
        self.assertEqual(apply_smuggling_demand(1000, None), (1000, 0))
        self.assertEqual(apply_smuggling_demand(1000, "x"), (1000, 0))

    def test_rounds(self):
        new, bonus = apply_smuggling_demand(333, 1.5)   # 499.5 → 500
        self.assertEqual(new, 500)
        self.assertEqual(bonus, 167)


def _src(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestStructural(unittest.TestCase):
    def test_smuggling_payout_reads_and_applies_demand(self):
        src = _src("parser", "smuggling_commands.py")
        self.assertIn("apply_smuggling_demand", src)
        self.assertIn("SMUGGLING_DEMAND_EFFECT_KEY", src)
        self.assertIn("get_effect(", src)
        # Still routed through the ledger under the smuggling tag.
        self.assertIn('"smuggling"', src)


if __name__ == "__main__":
    unittest.main()
