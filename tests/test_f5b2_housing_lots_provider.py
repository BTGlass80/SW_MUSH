# -*- coding: utf-8 -*-
"""
tests/test_f5b2_housing_lots_provider.py — F.5b.2 lots-provider tests

F.5b.2 (Apr 30 2026) introduces engine/housing_lots_provider.py — an
era-aware bridge between the F.5a.{1,2,3} YAML lot corpus and the legacy
5-tuple shape that engine/housing.py's six call sites have always
consumed.

Tests cover:

  - GCW era path: returns the legacy hardcoded constants verbatim
    (byte-equivalence with HOUSING_LOTS_DROP1, HOUSING_LOTS_TIER3,
    HOUSING_LOTS_TIER4, HOUSING_LOTS_TIER5)

  - CW era path: returns YAML-derived 5-tuples with:
      - host_room slugs resolved to numeric room IDs
      - label derived from room name (planet prefix stripped)
      - security tier derived from zone via _ZONE_SECURITY mapping
      - max_homes from `slots` (T1) or `max_homes` (T3/T4/T5)
      - tuple shape identical to legacy

  - Counts match design (13 T1 / 16 T3 / 8 T4 / 9 T5)

  - rep_gate map populated from CW T3 lots (Kuat KDY + Embassy)

  - is_lot_rep_visible: lot with no rep_gate is always visible;
    lot with rep_gate respects char's faction reputation

  - get_tier3_lots_filtered: hides rep-gated lots from low-rep chars

  - Cache: per-era cached, cleared by clear_lots_cache()

  - Resilience: graceful fallback to legacy if YAML fails to load
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestGCWPath(unittest.TestCase):
    """F.5b.3.b (Apr 30 2026): GCW now flows through the YAML corpus,
    same as CW. The YAML records carry `display_label` and
    `security_override` that match the legacy hand-authored values, so
    the provider's output is byte-equivalent to the legacy constants
    on (planet, label, security, max_homes). Room IDs may differ
    because YAML resolves slugs to current IDs (correcting the legacy
    drift documented in F.5b.3.a's audit).

    Pre-F.5b.3.b: this class asserted GCW == legacy verbatim, which
    documented the transitional pass-through. Post-F.5b.3.b: it
    asserts the new contract — id-stripped equivalence.
    """

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    @staticmethod
    def _strip_id(tuples):
        """Return list of (planet, label, security, max_homes) — drop room_id."""
        return sorted([(p, l, s, m) for (rid, p, l, s, m) in tuples])

    def test_gcw_t1_id_stripped_matches_legacy(self):
        from engine.housing_lots_provider import get_tier1_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_DROP1
        t1 = get_tier1_lots("gcw")
        self.assertEqual(
            self._strip_id(t1), self._strip_id(list(LEGACY_HOUSING_LOTS_DROP1)),
            "GCW T1 from YAML must match legacy snapshot on (planet, label, "
            "security, max_homes) after F.5b.3.b",
        )

    def test_gcw_t3_id_stripped_matches_legacy(self):
        from engine.housing_lots_provider import get_tier3_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER3
        t3 = get_tier3_lots("gcw")
        self.assertEqual(
            self._strip_id(t3), self._strip_id(list(LEGACY_HOUSING_LOTS_TIER3)),
            "GCW T3 from YAML must match legacy snapshot on (planet, label, "
            "security, max_homes) after F.5b.3.b",
        )

    def test_gcw_t4_id_stripped_matches_legacy(self):
        from engine.housing_lots_provider import get_tier4_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER4
        t4 = get_tier4_lots("gcw")
        self.assertEqual(
            self._strip_id(t4), self._strip_id(list(LEGACY_HOUSING_LOTS_TIER4)),
            "GCW T4 from YAML must match legacy snapshot on (planet, label, "
            "security, max_homes) after F.5b.3.b",
        )

    def test_gcw_t5_id_stripped_matches_legacy(self):
        from engine.housing_lots_provider import get_tier5_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER5
        t5 = get_tier5_lots("gcw")
        self.assertEqual(
            self._strip_id(t5), self._strip_id(list(LEGACY_HOUSING_LOTS_TIER5)),
            "GCW T5 from YAML must match legacy snapshot on (planet, label, "
            "security, max_homes) after F.5b.3.b",
        )

    def test_gcw_room_ids_resolve_to_correct_rooms(self):
        """F.5b.3.b: the YAML path corrects the legacy ID drift.
        Spaceport Hotel is room 25, not legacy's stale 29. This test
        guards against a future regression where the YAML path
        accidentally re-introduces the wrong IDs."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        by_label = {label: rid for rid, _, label, _, _ in t1}
        # Spaceport Hotel is now correctly resolved (was stale ID 29 in legacy)
        self.assertEqual(by_label.get("Spaceport Hotel"), 25)
        # Mos Eisley Inn is now correctly resolved (was stale ID 21 in legacy)
        self.assertEqual(by_label.get("Mos Eisley Inn"), 17)

    def test_gcw_has_no_rep_gates(self):
        """GCW housing has no rep_gate concept (CW Kuat lots only)."""
        from engine.housing_lots_provider import get_tier3_rep_gates
        gates = get_tier3_rep_gates("gcw")
        self.assertEqual(gates, {})

    def test_gcw_lot_count_matches_legacy_cardinality(self):
        """The YAML must produce the same total lot count as legacy.
        If a YAML record's host_room failed to resolve, the count
        would be lower than legacy — guard against that."""
        from engine.housing_lots_provider import (
            get_tier1_lots, get_tier3_lots, get_tier4_lots, get_tier5_lots,
        )
        from tests._legacy_housing_lots_snapshot import (
            LEGACY_HOUSING_LOTS_DROP1, LEGACY_HOUSING_LOTS_TIER3,
            LEGACY_HOUSING_LOTS_TIER4, LEGACY_HOUSING_LOTS_TIER5,
        )
        self.assertEqual(len(get_tier1_lots("gcw")), len(LEGACY_HOUSING_LOTS_DROP1))
        self.assertEqual(len(get_tier3_lots("gcw")), len(LEGACY_HOUSING_LOTS_TIER3))
        self.assertEqual(len(get_tier4_lots("gcw")), len(LEGACY_HOUSING_LOTS_TIER4))
        self.assertEqual(len(get_tier5_lots("gcw")), len(LEGACY_HOUSING_LOTS_TIER5))


class TestCWPath(unittest.TestCase):
    """CW era resolves YAML corpus to legacy 5-tuple shape."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_cw_t1_count(self):
        """CW T1 must have 13 entries per design §6."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("clone_wars")
        self.assertEqual(len(t1), 13)

    def test_cw_t3_count(self):
        """CW T3 must have 16 entries per design §7."""
        from engine.housing_lots_provider import get_tier3_lots
        t3 = get_tier3_lots("clone_wars")
        self.assertEqual(len(t3), 16)

    def test_cw_t4_count(self):
        """CW T4 must have 8 entries per design §8."""
        from engine.housing_lots_provider import get_tier4_lots
        t4 = get_tier4_lots("clone_wars")
        self.assertEqual(len(t4), 8)

    def test_cw_t5_count(self):
        """CW T5 must have 9 entries per design §9."""
        from engine.housing_lots_provider import get_tier5_lots
        t5 = get_tier5_lots("clone_wars")
        self.assertEqual(len(t5), 9)

    def test_cw_tuples_have_legacy_shape(self):
        """Each CW lot tuple must be (room_id, planet, label, security, max_homes)."""
        from engine.housing_lots_provider import (
            get_tier1_lots, get_tier3_lots, get_tier4_lots, get_tier5_lots,
        )
        for getter, tier_name in [
            (get_tier1_lots, "T1"),
            (get_tier3_lots, "T3"),
            (get_tier4_lots, "T4"),
            (get_tier5_lots, "T5"),
        ]:
            for tup in getter("clone_wars"):
                self.assertEqual(
                    len(tup), 5,
                    f"{tier_name} tuple has wrong arity: {tup}"
                )
                rid, planet, label, security, max_h = tup
                self.assertIsInstance(rid, int, f"{tier_name} room_id not int: {tup}")
                self.assertIsInstance(planet, str)
                self.assertIsInstance(label, str)
                self.assertIn(security, ("secured", "contested", "lawless"))
                self.assertIsInstance(max_h, int)
                self.assertGreaterEqual(max_h, 1)

    def test_cw_room_ids_resolve_to_live_rooms(self):
        """Every resolved room_id must be live in the CW world."""
        from engine.housing_lots_provider import (
            get_tier1_lots, get_tier3_lots, get_tier4_lots, get_tier5_lots,
        )
        from engine.world_loader import load_world_dry_run
        b = load_world_dry_run("clone_wars")
        live_ids = set(b.rooms.keys())
        for getter, tier_name in [
            (get_tier1_lots, "T1"),
            (get_tier3_lots, "T3"),
            (get_tier4_lots, "T4"),
            (get_tier5_lots, "T5"),
        ]:
            for rid, planet, label, security, max_h in getter("clone_wars"):
                self.assertIn(
                    rid, live_ids,
                    f"{tier_name} lot room_id {rid!r} ({label!r}) not in CW world."
                )

    def test_cw_t1_max_homes_is_slots(self):
        """T1 lots' fifth tuple element must come from `slots`, not max_homes
        (which T1 records don't have). All design T1 records have slots
        between 3 and 6."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("clone_wars")
        for rid, planet, label, security, slots in t1:
            self.assertGreaterEqual(slots, 3)
            self.assertLessEqual(slots, 6)

    def test_cw_kuat_lots_are_secured(self):
        """All Kuat host rooms are in secured zones per the design table."""
        from engine.housing_lots_provider import get_tier1_lots, get_tier3_lots
        for tup in get_tier1_lots("clone_wars") + get_tier3_lots("clone_wars"):
            rid, planet, label, security, _ = tup
            if planet == "kuat":
                self.assertEqual(
                    security, "secured",
                    f"Kuat lot {label!r} has security {security!r}; "
                    f"expected 'secured' per design §4."
                )

    def test_cw_geonosis_lots_are_lawless(self):
        """All Geonosis surface lots are lawless per design §4."""
        from engine.housing_lots_provider import (
            get_tier1_lots, get_tier3_lots, get_tier5_lots,
        )
        for getter in (get_tier1_lots, get_tier3_lots, get_tier5_lots):
            for rid, planet, label, security, _ in getter("clone_wars"):
                if planet == "geonosis":
                    self.assertEqual(
                        security, "lawless",
                        f"Geonosis lot {label!r} has security {security!r}; "
                        f"expected 'lawless'."
                    )

    def test_cw_t4_lots_not_lawless(self):
        """No T4 lots in lawless zones per design invariant §3.4."""
        from engine.housing_lots_provider import get_tier4_lots
        for rid, planet, label, security, _ in get_tier4_lots("clone_wars"):
            self.assertNotEqual(
                security, "lawless",
                f"T4 lot {label!r} is in lawless zone — violates §3.4."
            )


class TestRepGateFiltering(unittest.TestCase):
    """rep_gate field on T3 lots filters visibility by character reputation."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_cw_has_two_rep_gated_lots(self):
        """Per design §7.1, both Kuat T3 lots are rep-gated."""
        from engine.housing_lots_provider import get_tier3_rep_gates
        gates = get_tier3_rep_gates("clone_wars")
        self.assertEqual(len(gates), 2,
            f"Expected 2 rep-gated T3 lots (both Kuat), got {len(gates)}.")

    def test_rep_gates_are_republic_25(self):
        """Both Kuat T3 lots gate on Republic ≥ 25 per design."""
        from engine.housing_lots_provider import get_tier3_rep_gates
        gates = get_tier3_rep_gates("clone_wars")
        for room_id, gate in gates.items():
            self.assertEqual(gate["faction"], "republic",
                f"Rep gate on room {room_id} has wrong faction: {gate}")
            self.assertEqual(gate["min_value"], 25,
                f"Rep gate on room {room_id} has wrong min_value: {gate}")

    def test_no_rep_lot_always_visible(self):
        """Lots without a rep_gate are visible to all characters."""
        from engine.housing_lots_provider import is_lot_rep_visible
        # Pick a known non-gated room id (Coco Town residential walk)
        # — get it from the actual T3 list
        from engine.housing_lots_provider import (
            get_tier3_lots, get_tier3_rep_gates,
        )
        gates = get_tier3_rep_gates("clone_wars")
        for rid, planet, label, security, _ in get_tier3_lots("clone_wars"):
            if rid not in gates:
                # Should be visible to char with no rep
                self.assertTrue(
                    is_lot_rep_visible(rid, {}, era="clone_wars"),
                    f"Non-gated lot {label!r} not visible to no-rep char."
                )
                break

    def test_rep_gated_lot_invisible_to_low_rep(self):
        """A rep-gated lot must NOT be visible to a char below the threshold."""
        from engine.housing_lots_provider import (
            is_lot_rep_visible, get_tier3_rep_gates,
        )
        gates = get_tier3_rep_gates("clone_wars")
        any_gated_room = next(iter(gates.keys()))
        # Char with no rep: not visible
        self.assertFalse(
            is_lot_rep_visible(any_gated_room, {}, era="clone_wars"),
            "Rep-gated lot must be invisible to no-rep char."
        )
        # Char with low rep (10 < 25): not visible
        self.assertFalse(
            is_lot_rep_visible(
                any_gated_room, {"republic": 10}, era="clone_wars"
            ),
            "Rep-gated lot must be invisible to low-rep char."
        )

    def test_rep_gated_lot_visible_to_high_rep(self):
        """A rep-gated lot is visible to a char at/above the threshold."""
        from engine.housing_lots_provider import (
            is_lot_rep_visible, get_tier3_rep_gates,
        )
        gates = get_tier3_rep_gates("clone_wars")
        any_gated_room = next(iter(gates.keys()))
        # Exactly at threshold: visible
        self.assertTrue(
            is_lot_rep_visible(
                any_gated_room, {"republic": 25}, era="clone_wars"
            ),
            "Rep-gated lot must be visible to char at exactly threshold."
        )
        # Above threshold: visible
        self.assertTrue(
            is_lot_rep_visible(
                any_gated_room, {"republic": 50}, era="clone_wars"
            ),
            "Rep-gated lot must be visible to high-rep char."
        )

    def test_filtered_t3_hides_kuat_lots_for_no_rep(self):
        """get_tier3_lots_filtered hides Kuat lots from a no-rep char."""
        from engine.housing_lots_provider import (
            get_tier3_lots, get_tier3_lots_filtered,
        )
        all_t3 = get_tier3_lots("clone_wars")
        visible = get_tier3_lots_filtered({}, era="clone_wars")
        # 16 total; 2 hidden (the Kuat rep-gated pair) → 14 visible
        self.assertEqual(
            len(visible), len(all_t3) - 2,
            f"Expected 14 visible T3 lots for no-rep char; got {len(visible)}"
        )
        # No Kuat lots in the visible set
        kuat_visible = [t for t in visible if t[1] == "kuat"]
        self.assertEqual(
            len(kuat_visible), 0,
            "Kuat T3 lots leaked through filter for no-rep char."
        )

    def test_filtered_t3_shows_all_for_high_rep(self):
        """get_tier3_lots_filtered shows all T3 to a Republic-aligned char."""
        from engine.housing_lots_provider import (
            get_tier3_lots, get_tier3_lots_filtered,
        )
        all_t3 = get_tier3_lots("clone_wars")
        visible = get_tier3_lots_filtered(
            {"republic": 100}, era="clone_wars"
        )
        self.assertEqual(
            len(visible), len(all_t3),
            f"Expected all {len(all_t3)} T3 lots for high-rep char; "
            f"got {len(visible)}"
        )


class TestCaching(unittest.TestCase):
    """Per-era caching of the resolved corpus."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_cache_returns_same_data_on_repeated_calls(self):
        """Two calls return equal lists (the cache shouldn't mutate)."""
        from engine.housing_lots_provider import get_tier3_lots
        a = get_tier3_lots("clone_wars")
        b = get_tier3_lots("clone_wars")
        self.assertEqual(a, b)

    def test_cache_returns_distinct_lists(self):
        """Caller mutating the returned list shouldn't pollute the cache."""
        from engine.housing_lots_provider import get_tier3_lots
        a = get_tier3_lots("clone_wars")
        a.clear()
        b = get_tier3_lots("clone_wars")
        self.assertEqual(len(b), 16,
            "Mutating returned list polluted the cache.")

    def test_clear_cache_forces_reload(self):
        """clear_lots_cache() invalidates the cache."""
        from engine.housing_lots_provider import (
            get_tier3_lots, clear_lots_cache, _lots_cache,
        )
        get_tier3_lots("clone_wars")
        self.assertIn("clone_wars", _lots_cache)
        clear_lots_cache()
        self.assertNotIn("clone_wars", _lots_cache)


class TestActiveEraDefault(unittest.TestCase):
    """When era is omitted, get_active_era() resolves it."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()
        from engine.era_state import set_active_config
        set_active_config(None)

    def tearDown(self):
        from engine.era_state import set_active_config
        set_active_config(None)
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_no_active_config_falls_back_to_gcw(self):
        """Default behavior: with no Config registered, era resolves to gcw.

        F.5b.3.b (Apr 30 2026): GCW now flows through YAML, so the
        result matches the legacy constants on (planet, label,
        security, max_homes) but not on room_id (YAML uses corrected
        slug-resolved IDs).

        F.5b.3.c (Apr 30 2026): legacy constants deleted; reference is
        now the static snapshot.
        """
        from engine.housing_lots_provider import get_tier3_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER3
        # No era param → falls back to gcw default
        t3 = get_tier3_lots()
        # Strip ID for comparison (per F.5b.3.b contract).
        def _strip_id(lots):
            return sorted([(p, l, s, m) for (rid, p, l, s, m) in lots])
        self.assertEqual(
            _strip_id(t3), _strip_id(list(LEGACY_HOUSING_LOTS_TIER3)),
            "Default gcw path must produce id-stripped equivalent of legacy",
        )
        self.assertEqual(len(t3), len(LEGACY_HOUSING_LOTS_TIER3))

    def test_active_cw_config_returns_cw_data(self):
        """With CW Config registered, era-omitted call returns CW data."""
        from engine.housing_lots_provider import get_tier3_lots
        from engine.era_state import set_active_config

        class _MockCfg:
            active_era = "clone_wars"
            use_yaml_director_data = True

        set_active_config(_MockCfg())
        t3 = get_tier3_lots()
        self.assertEqual(len(t3), 16, "Active CW config should yield 16 T3 lots.")


if __name__ == "__main__":
    unittest.main()
