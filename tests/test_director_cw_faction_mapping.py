# -*- coding: utf-8 -*-
"""
tests/test_director_cw_faction_mapping.py — DIRECTOR.faction_model_cw_mapping
(2026-06-13).

The LLM Director's faction_order boundary historically validated against
GCW ORG codes {empire, rebel, hutt, bh_guild}, so it could never issue
era-correct Clone Wars orders (the orgs are republic / cis / hutt_cartel /
bounty_hunters_guild) — _apply_faction_order's get_organization(code)
would miss every time. This drop adds a MAPPING LAYER at the order
boundary (accept CW code OR legacy GCW alias, normalize to the CW code)
and a CW faction legend in the digest, leaving the sanctioned ZoneState
zone-tone AXIS keys (imperial/rebel/criminal/independent) untouched.

Pins:
  1. normalize_faction_order_code — CW codes pass through, GCW aliases map
     forward, garbage -> "".
  2. The digest carries faction_order_codes (the CW org codes) +
     faction_axis_to_org (the back-compat legend) — and zone_influence now
     uses the NATIVE CW factions (DIRECTOR.zonestate_cw_faction_axis,
     Option A, 2026-06-13 — supersedes the drop-39 "axis untouched"
     contract; ZoneState was rewritten to hold the era faction set).
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestNormalizeFactionOrderCode(unittest.TestCase):
    def test_cw_codes_pass_through(self):
        from engine.director import normalize_faction_order_code
        for c in ("republic", "cis", "hutt_cartel", "bounty_hunters_guild"):
            self.assertEqual(normalize_faction_order_code(c), c)

    def test_gcw_aliases_map_forward(self):
        from engine.director import normalize_faction_order_code
        self.assertEqual(normalize_faction_order_code("empire"), "republic")
        self.assertEqual(normalize_faction_order_code("rebel"), "cis")
        self.assertEqual(normalize_faction_order_code("hutt"), "hutt_cartel")
        self.assertEqual(
            normalize_faction_order_code("bh_guild"), "bounty_hunters_guild")

    def test_case_insensitive(self):
        from engine.director import normalize_faction_order_code
        self.assertEqual(normalize_faction_order_code("EMPIRE"), "republic")
        self.assertEqual(normalize_faction_order_code("Republic"), "republic")

    def test_garbage_returns_empty(self):
        from engine.director import normalize_faction_order_code
        for bad in ("", "bogus", None, "jedi_order", "imperial"):
            # NB: 'imperial' is a zone-tone AXIS key, NOT an order org code
            # — it must NOT validate as a faction_order target.
            self.assertEqual(normalize_faction_order_code(bad), "")

    def test_axis_keys_are_not_order_codes(self):
        # The sanctioned zone-tone axis keys must never resolve as order
        # targets (they're a different surface).
        from engine.director import normalize_faction_order_code
        for axis in ("imperial", "rebel", "criminal", "independent"):
            res = normalize_faction_order_code(axis)
            # 'rebel' is a legacy GCW ORG alias too -> maps to cis; the
            # others are axis-only and must be empty.
            if axis == "rebel":
                self.assertEqual(res, "cis")
            else:
                self.assertNotIn(res, ("imperial", "criminal"))


@pytest.mark.slow  # heavy: async
class TestDigestFactionLegend(unittest.TestCase):
    def _run(self, coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    def _director(self):
        from engine.director import get_director
        return get_director()

    class _StubSessionMgr:
        all = []

    def test_digest_has_cw_legend_and_native_axis(self):
        from engine.director import CW_FACTION_ORDER_CODES
        d = self._director()
        digest = self._run(d.compile_digest(self._StubSessionMgr()))
        # The CW order codes are advertised to the LLM.
        self.assertEqual(set(digest["faction_order_codes"]),
                         set(CW_FACTION_ORDER_CODES))
        # The back-compat legend (GCW axis -> CW org) is retained as a hint.
        legend = digest["faction_axis_to_org"]
        self.assertEqual(legend["imperial"], "republic")
        self.assertEqual(legend["rebel"], "cis")
        self.assertEqual(legend["criminal"], "hutt_cartel")
        self.assertEqual(legend["independent"], "independent")
        # DIRECTOR.zonestate_cw_faction_axis (Brian 2026-06-13, Option A):
        # zone_influence now carries the NATIVE CW factions, not the legacy
        # GCW axis labels. (Supersedes the drop-39 "axis untouched" contract.)
        zi = digest["zone_influence"]
        if zi:  # at least one zone loaded
            sample = next(iter(zi.values()))
            for f in ("republic", "cis", "jedi_order", "hutt_cartel",
                      "bhg", "independent"):
                self.assertIn(f, sample)
            self.assertNotIn("imperial", sample)
            self.assertNotIn("criminal", sample)


if __name__ == "__main__":
    unittest.main()
