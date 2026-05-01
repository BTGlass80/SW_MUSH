# -*- coding: utf-8 -*-
"""
tests/test_f5b2x_housing_rep_gate_enforcement.py — F.5b.2.x tests.

F.5b.2 (Apr 30 2026) shipped the housing_lots_provider module and the
is_lot_rep_visible helper. F.5b.2.x (this drop) wires that helper into:

  1. `engine/housing.py::get_tier3_available_lots(db, char=None)` —
     when `char` is provided, rep-gated lots are filtered out per
     `cw_housing_design_v1.md` §7.1.

  2. `engine/housing.py::get_tier3_listing_lines(db, char)` — passes
     `char` to (1) so `housing tier3` listings hide rep-gated lots
     from unaligned PCs.

  3. `engine/housing.py::purchase_home(db, char, lot_id, home_type)` —
     rep_gate enforcement at purchase-time; an unaligned PC who tries
     to buy a Kuat lot by ID gets "Invalid lot." (the same message as
     a non-existent lot, so the gate's existence isn't leaked).

  4. `engine/housing.py::_get_char_rep_flat(db, char)` — helper that
     converts the {code: {rep, ...}} shape from
     `engine/organizations.get_all_faction_reps` to the flat
     {code: int} shape the provider's is_lot_rep_visible expects.

Tests use AsyncMock for the DB layer following the test_b1d2 pattern.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    """Run an async test body.

    Fixed Apr 30 2026 (test-hygiene drop): on Python 3.14 + Windows
    proactor policy, `asyncio.get_event_loop()` raises if no loop is
    current. asyncio.run() handles loop lifecycle correctly across
    Python 3.10+ on all platforms.
    """
    return asyncio.run(coro)


# Mock active_era for these tests — F.5b.2.x rep_gate logic only
# applies to CW (the lot YAML has rep_gate; GCW hardcodes don't).
def _set_cw_era():
    from engine.era_state import set_active_config

    class _CWConfig:
        active_era = "clone_wars"
        use_yaml_director_data = True

    set_active_config(_CWConfig())


def _clear_era():
    from engine.era_state import set_active_config
    set_active_config(None)


class TestGetCharRepFlat(unittest.TestCase):
    """The DB-shape → flat-shape adapter."""

    def test_no_char_returns_empty(self):
        from engine.housing import _get_char_rep_flat

        async def go():
            db = MagicMock()
            return await _get_char_rep_flat(db, None)

        result = _run(go())
        self.assertEqual(result, {})

    def test_char_without_id_returns_empty(self):
        from engine.housing import _get_char_rep_flat

        async def go():
            db = MagicMock()
            return await _get_char_rep_flat(db, {})

        result = _run(go())
        self.assertEqual(result, {})

    def test_db_error_returns_empty(self):
        """If get_all_faction_reps raises, return empty dict."""
        from engine.housing import _get_char_rep_flat

        async def go():
            db = MagicMock()
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(side_effect=RuntimeError("DB down")),
            ):
                return await _get_char_rep_flat(db, {"id": 1})

        result = _run(go())
        self.assertEqual(result, {})

    def test_unwraps_dict_shape_correctly(self):
        """Real-world DB shape: {code: {rep, tier_key, ...}} → {code: int}."""
        from engine.housing import _get_char_rep_flat

        async def go():
            db = MagicMock()
            mock_rep = {
                "republic": {"rep": 50, "tier_key": "trusted"},
                "cis": {"rep": -10, "tier_key": "hostile"},
                "jedi_order": {"rep": 0, "tier_key": "neutral"},
            }
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value=mock_rep),
            ):
                return await _get_char_rep_flat(db, {"id": 1})

        result = _run(go())
        self.assertEqual(result, {"republic": 50, "cis": -10, "jedi_order": 0})

    def test_handles_int_value_directly(self):
        """If the API ever returns flat ints, handle that too."""
        from engine.housing import _get_char_rep_flat

        async def go():
            db = MagicMock()
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value={"republic": 25}),
            ):
                return await _get_char_rep_flat(db, {"id": 1})

        result = _run(go())
        self.assertEqual(result, {"republic": 25})


class TestGetTier3AvailableLotsFiltering(unittest.TestCase):
    """get_tier3_available_lots(db, char=...) honors rep_gate."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()
        _set_cw_era()

    def tearDown(self):
        _clear_era()
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def _make_db_returning_all_t3_rows(self):
        """Build a mock DB returning rows for all 16 CW T3 lots."""
        from engine.housing_lots_provider import get_tier3_lots
        all_t3 = get_tier3_lots("clone_wars")

        rows = [
            {
                "id": idx + 1,
                "room_id": rid,
                "planet": planet,
                "label": label,
                "security": security,
                "max_homes": max_h,
                "current_homes": 0,
            }
            for idx, (rid, planet, label, security, max_h) in enumerate(all_t3)
        ]
        db = MagicMock()
        db.fetchall = AsyncMock(return_value=rows)
        return db

    def test_no_char_returns_all_lots(self):
        """When char is None, no rep filter applied (backward compat)."""
        from engine.housing import get_tier3_available_lots

        async def go():
            db = self._make_db_returning_all_t3_rows()
            return await get_tier3_available_lots(db)

        result = _run(go())
        self.assertEqual(len(result), 16,
            "char=None should return all 16 T3 lots unfiltered.")

    def test_no_rep_char_hides_kuat_lots(self):
        """An unaligned PC sees 14 lots (16 total minus 2 Kuat rep-gated)."""
        from engine.housing import get_tier3_available_lots

        async def go():
            db = self._make_db_returning_all_t3_rows()
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value={}),
            ):
                return await get_tier3_available_lots(db, char={"id": 1})

        result = _run(go())
        self.assertEqual(len(result), 14,
            f"No-rep char should see 14 lots (16 minus 2 Kuat); got {len(result)}.")
        # No Kuat lots in result
        kuat_visible = [r for r in result if r["planet"] == "kuat"]
        self.assertEqual(len(kuat_visible), 0,
            "Kuat lots leaked into no-rep char's listing.")

    def test_high_rep_char_sees_all_lots(self):
        """Republic-aligned PC at rep≥25 sees all 16 lots."""
        from engine.housing import get_tier3_available_lots

        async def go():
            db = self._make_db_returning_all_t3_rows()
            mock_rep = {"republic": {"rep": 50}}
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value=mock_rep),
            ):
                return await get_tier3_available_lots(db, char={"id": 1})

        result = _run(go())
        self.assertEqual(len(result), 16,
            f"High-rep Republic char should see all 16 lots; got {len(result)}.")

    def test_low_rep_char_still_filtered(self):
        """Republic rep=10 (below threshold of 25) hides Kuat lots."""
        from engine.housing import get_tier3_available_lots

        async def go():
            db = self._make_db_returning_all_t3_rows()
            mock_rep = {"republic": {"rep": 10}}
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value=mock_rep),
            ):
                return await get_tier3_available_lots(db, char={"id": 1})

        result = _run(go())
        self.assertEqual(len(result), 14,
            f"Low-rep char should see 14 lots; got {len(result)}.")

    def test_threshold_exact_visible(self):
        """Republic rep=25 (exactly threshold) shows Kuat lots."""
        from engine.housing import get_tier3_available_lots

        async def go():
            db = self._make_db_returning_all_t3_rows()
            mock_rep = {"republic": {"rep": 25}}
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value=mock_rep),
            ):
                return await get_tier3_available_lots(db, char={"id": 1})

        result = _run(go())
        self.assertEqual(len(result), 16,
            "Char at exactly threshold should see all lots.")


class TestPurchaseHomeRepGateEnforcement(unittest.TestCase):
    """purchase_home refuses rep-gated lots without leaking gate info."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()
        _set_cw_era()

    def tearDown(self):
        _clear_era()
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def _build_purchase_mocks(self, lot_room_id: int, planet: str = "kuat"):
        """Build mocks for purchase_home — db, char, lot row.

        Sets up mocks so all checks before rep_gate pass (no existing
        housing, no per-planet limit hit, lot has slots), so rep_gate
        is the deciding factor.
        """
        db = MagicMock()
        # get_housing returns None (no existing housing)
        # Patched at module level below
        char = {
            "id": 1,
            "name": "TestChar",
            "credits": 100_000,
        }
        lot_row = {
            "id": 99,
            "room_id": lot_room_id,
            "planet": planet,
            "label": "Test Lot",
            "security": "secured",
            "max_homes": 4,
            "current_homes": 0,
        }
        # Mock fetchall for the per-planet count check (returns 0 existing)
        db.fetchall = AsyncMock(return_value=[{"cnt": 0}])
        return db, char, lot_row

    def test_rep_gated_lot_refused_for_no_rep_char(self):
        """An unaligned PC trying to buy a Kuat lot gets 'Invalid lot.'

        Crucially, the message is the SAME as for a non-existent lot —
        the gate's existence is not leaked.
        """
        from engine.housing import purchase_home
        from engine.housing_lots_provider import get_tier3_rep_gates

        gates = get_tier3_rep_gates("clone_wars")
        kuat_lot_room = next(iter(gates.keys()))

        async def go():
            db, char, lot_row = self._build_purchase_mocks(kuat_lot_room)
            with patch("engine.housing.get_housing", AsyncMock(return_value=None)):
                with patch("engine.housing.get_lot", AsyncMock(return_value=lot_row)):
                    with patch(
                        "engine.organizations.get_all_faction_reps",
                        AsyncMock(return_value={}),  # no rep
                    ):
                        return await purchase_home(db, char, lot_id=99, home_type="standard")

        result = _run(go())
        self.assertFalse(result["ok"], "Purchase must be refused for no-rep char.")
        self.assertEqual(result["msg"], "Invalid lot.",
            "Refusal message must NOT leak rep_gate existence; "
            "must match the non-existent-lot message.")

    def test_rep_gated_lot_refused_for_low_rep_char(self):
        """Republic rep=10 gets the same 'Invalid lot.' refusal."""
        from engine.housing import purchase_home
        from engine.housing_lots_provider import get_tier3_rep_gates

        gates = get_tier3_rep_gates("clone_wars")
        kuat_lot_room = next(iter(gates.keys()))

        async def go():
            db, char, lot_row = self._build_purchase_mocks(kuat_lot_room)
            with patch("engine.housing.get_housing", AsyncMock(return_value=None)):
                with patch("engine.housing.get_lot", AsyncMock(return_value=lot_row)):
                    with patch(
                        "engine.organizations.get_all_faction_reps",
                        AsyncMock(return_value={"republic": {"rep": 10}}),
                    ):
                        return await purchase_home(db, char, lot_id=99, home_type="standard")

        result = _run(go())
        self.assertFalse(result["ok"])
        self.assertEqual(result["msg"], "Invalid lot.")

    def test_rep_gated_lot_proceeds_for_high_rep_char(self):
        """Republic rep≥25 passes the rep gate (purchase will then proceed
        through other checks; we only assert the rep gate didn't refuse)."""
        from engine.housing import purchase_home
        from engine.housing_lots_provider import get_tier3_rep_gates

        gates = get_tier3_rep_gates("clone_wars")
        kuat_lot_room = next(iter(gates.keys()))

        async def go():
            db, char, lot_row = self._build_purchase_mocks(kuat_lot_room)
            # Mock get_room → None to make purchase fail at a LATER stage,
            # not at the rep_gate. This proves the gate didn't trip.
            db.get_room = AsyncMock(return_value=None)
            with patch("engine.housing.get_housing", AsyncMock(return_value=None)):
                with patch("engine.housing.get_lot", AsyncMock(return_value=lot_row)):
                    with patch(
                        "engine.organizations.get_all_faction_reps",
                        AsyncMock(return_value={"republic": {"rep": 50}}),
                    ):
                        return await purchase_home(db, char, lot_id=99, home_type="standard")

        result = _run(go())
        self.assertFalse(result["ok"])
        # Should fail at "Lot room not found." NOT at "Invalid lot."
        self.assertNotEqual(result["msg"], "Invalid lot.",
            "High-rep char hit the rep_gate refusal — should have passed it.")
        self.assertEqual(result["msg"], "Lot room not found.",
            "Test setup expected purchase to fail at the room-fetch step.")

    def test_non_gated_lot_proceeds_for_no_rep_char(self):
        """A non-rep-gated lot (e.g., Coco Town) is purchasable by anyone."""
        from engine.housing import purchase_home
        from engine.housing_lots_provider import get_tier3_lots, get_tier3_rep_gates

        # Pick a non-gated CW T3 lot
        gates = get_tier3_rep_gates("clone_wars")
        non_gated = [
            t for t in get_tier3_lots("clone_wars")
            if t[0] not in gates
        ]
        self.assertGreater(len(non_gated), 0)
        non_gated_room = non_gated[0][0]

        async def go():
            db, char, lot_row = self._build_purchase_mocks(
                non_gated_room, planet=non_gated[0][1],
            )
            db.get_room = AsyncMock(return_value=None)
            with patch("engine.housing.get_housing", AsyncMock(return_value=None)):
                with patch("engine.housing.get_lot", AsyncMock(return_value=lot_row)):
                    with patch(
                        "engine.organizations.get_all_faction_reps",
                        AsyncMock(return_value={}),
                    ):
                        return await purchase_home(db, char, lot_id=99, home_type="standard")

        result = _run(go())
        self.assertFalse(result["ok"])
        # Should fail at the room-fetch step, NOT at "Invalid lot."
        self.assertNotEqual(result["msg"], "Invalid lot.",
            "Non-gated lot triggered rep_gate refusal — should not have.")

    def test_invalid_lot_id_returns_invalid_lot(self):
        """Sanity: a truly-invalid lot id still returns 'Invalid lot.'

        This is the message we coopted for rep-gate refusals; verify the
        original semantic still works.
        """
        from engine.housing import purchase_home

        async def go():
            db = MagicMock()
            char = {"id": 1, "credits": 100_000}
            with patch("engine.housing.get_housing", AsyncMock(return_value=None)):
                with patch("engine.housing.get_lot", AsyncMock(return_value=None)):
                    return await purchase_home(db, char, lot_id=9999, home_type="standard")

        result = _run(go())
        self.assertFalse(result["ok"])
        self.assertEqual(result["msg"], "Invalid lot.")


class TestGCWBackwardsCompatibility(unittest.TestCase):
    """Under GCW era, F.5b.2.x changes are no-ops because there are no
    rep-gated lots in the legacy GCW T3 hardcodes."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()
        # Don't set active era — defaults to GCW.

    def tearDown(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_gcw_no_filter_applied(self):
        """In GCW era, get_tier3_rep_gates returns {} so no lots filtered."""
        from engine.housing import get_tier3_available_lots
        from engine.housing_lots_provider import get_tier3_lots

        gcw_t3 = get_tier3_lots("gcw")

        async def go():
            db = MagicMock()
            rows = [
                {
                    "id": idx + 1,
                    "room_id": rid,
                    "planet": planet,
                    "label": label,
                    "security": security,
                    "max_homes": max_h,
                    "current_homes": 0,
                }
                for idx, (rid, planet, label, security, max_h) in enumerate(gcw_t3)
            ]
            db.fetchall = AsyncMock(return_value=rows)
            with patch(
                "engine.organizations.get_all_faction_reps",
                AsyncMock(return_value={}),
            ):
                return await get_tier3_available_lots(db, char={"id": 1})

        result = _run(go())
        self.assertEqual(len(result), len(gcw_t3),
            f"GCW char with no rep should see all {len(gcw_t3)} GCW T3 lots; "
            f"got {len(result)}.")


if __name__ == "__main__":
    unittest.main()
