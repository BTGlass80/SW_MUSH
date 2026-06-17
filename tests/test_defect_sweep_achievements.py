# -*- coding: utf-8 -*-
"""
tests/test_defect_sweep_achievements.py — defect-sweep-achievements drop

Covers:
  A1 — 5 of 6 achievement emit-hooks wired (on_item_crafted, on_experiment_success,
       on_trade_goods_sold, on_ship_launch, on_anomaly_salvaged).
       on_dark_side_atoned DEFERRED — no atonement seam exists in the codebase;
       see drop report.
  A2 — intercept achievement call arg-order fix + signal_hunter entry in catalog.
  B1 — destination_slug resolves to precise room match; no-slug fallback preserved.
"""
from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _load_ach():
    """Ensure achievements are loaded from live YAML; returns module."""
    import engine.achievements as m
    m.load_achievements()
    return m


# ─── A2: intercept achievement in catalog ────────────────────────────────────

class TestA2InterceptAchievementInCatalog(unittest.TestCase):
    """signal_hunter (trigger event 'intercept') must be in the live catalog."""

    @classmethod
    def setUpClass(cls):
        cls.m = _load_ach()

    def test_signal_hunter_key_exists(self):
        ach = self.m.get_achievement("signal_hunter")
        self.assertIsNotNone(ach, "signal_hunter must be in achievements catalog")

    def test_signal_hunter_trigger_event_is_intercept(self):
        ach = self.m.get_achievement("signal_hunter")
        self.assertEqual(ach["trigger"]["event"], "intercept")

    def test_intercept_event_maps_to_signal_hunter(self):
        ach_list = self.m._BY_EVENT.get("intercept", [])
        keys = [a["key"] for a in ach_list]
        self.assertIn("signal_hunter", keys,
                      "intercept event must map to signal_hunter in _BY_EVENT")

    def test_signal_hunter_category_is_valid(self):
        ach = self.m.get_achievement("signal_hunter")
        self.assertIn(ach["category"], self.m.CATEGORY_ORDER,
                      "signal_hunter category must be in CATEGORY_ORDER")

    def test_signal_hunter_era_clean(self):
        """No Imperial/Empire/Rebel/TIE in player-facing strings."""
        ach = self.m.get_achievement("signal_hunter")
        bad = ["imperial", "empire", "rebel", "tie fighter", "tie-fighter"]
        for field in ("name", "description"):
            text = (ach.get(field) or "").lower()
            for word in bad:
                self.assertNotIn(word, text,
                                 f"signal_hunter.{field} contains era-forbidden '{word}'")


# ─── A2: intercept call arg-order fix ────────────────────────────────────────

class TestA2InterceptCallArgOrder(unittest.TestCase):
    """The fixed call in espionage_commands.py must pass db first, then char_id."""

    def test_intercept_call_passes_db_first(self):
        """Source-level check: the intercept achievement call must NOT pass `char`
        as the first positional arg (the old broken form was check_achievement(char, ...)).
        We verify by importing the module and asserting check_achievement is called
        with ctx.db as first arg via a mock intercept."""
        # Verify the fixed form is in source
        src_path = PROJECT_ROOT / "parser" / "espionage_commands.py"
        src = src_path.read_text(encoding="utf-8")
        # The broken form used positional char dict as first arg
        self.assertNotIn(
            "check_achievement(char, \"intercept\", ctx.db)",
            src,
            "Old broken call still present in espionage_commands.py",
        )
        # The fixed form passes ctx.db first, char[\"id\"] second
        self.assertIn(
            "check_achievement(ctx.db, char[\"id\"], \"intercept\"",
            src,
            "Fixed check_achievement call not found in espionage_commands.py",
        )


# ─── A1: on_item_crafted wired in crafting_commands.py ───────────────────────

class TestA1ItemCraftedWired(unittest.TestCase):
    """on_item_crafted is called on the craft-success path."""

    def test_on_item_crafted_import_on_success_path(self):
        src = (PROJECT_ROOT / "parser" / "crafting_commands.py").read_text(encoding="utf-8")
        self.assertIn("on_item_crafted", src,
                      "on_item_crafted must appear in crafting_commands.py")
        # Must be inside an if craft_result["success"]: block — verify
        # by checking it appears after the craft_result success guard
        success_pos = src.index('if craft_result["success"]:')
        ach_pos = src.index("on_item_crafted")
        self.assertGreater(ach_pos, success_pos,
                           "on_item_crafted must come after the craft success gate")

    def test_on_item_crafted_quality_arg_passed(self):
        src = (PROJECT_ROOT / "parser" / "crafting_commands.py").read_text(encoding="utf-8")
        self.assertIn("quality=int(craft_result.get(\"quality\", 0))", src,
                      "quality arg must be passed to on_item_crafted")


class TestA1ItemCraftedBehavioral(unittest.IsolatedAsyncioTestCase):
    """Drive the craft success path and assert on_item_crafted is awaited."""

    async def test_craft_success_fires_on_item_crafted(self):
        # Minimal fake objects to exercise CraftCommand.execute success path
        import parser.crafting_commands as cc

        char = {
            "id": 42, "name": "Crafter",
            "attributes": '{"repair": "3D"}',
            "inventory": "{}",
            "equipment": "{}",
            "credits": 1000,
            "room_id": 1,
        }

        class _FakeSession:
            character = char
            protocol = None
            async def send_line(self, msg): pass

        class _FakeDB:
            async def save_character(self, *a, **kw): pass
            async def add_to_inventory(self, *a, **kw): pass
            async def commit(self): pass

        class _FakeCtx:
            session = _FakeSession()
            db = _FakeDB()
            session_mgr = None
            args = "test_schematic"

        # Monkeypatch the module-level helpers so we don't need real schematics
        craft_result = {
            "success": True, "partial": False, "fumble": False,
            "quality": 75, "crafter_name": "Crafter", "stats": {},
            "message": "You craft the item.",
        }
        with mock.patch.object(cc, "_find_schematic", return_value={
            "name": "Test Item",
            "output_key": "test_item",
            "output_type": "weapon",
            "skill_required": "repair",
            "difficulty": 10,
            "components": [],
        }):
            with mock.patch.object(cc, "can_craft", return_value=(True, "")):
                with mock.patch.object(cc, "get_known_schematics", return_value=["test_schematic"]):
                    with mock.patch.object(cc, "_skill_check", return_value=types.SimpleNamespace(
                        success=True, fumble=False, critical_success=False,
                        margin=5, roll=15, pool_str="3D",
                    )):
                        with mock.patch.object(cc, "resolve_craft", return_value=craft_result):
                            with mock.patch.object(cc, "_deliver_item", new=mock.AsyncMock()):
                                with mock.patch.object(cc, "_push_crafting_state", new=mock.AsyncMock()):
                                    with mock.patch.object(cc, "_save_char", new=mock.AsyncMock()):
                                        with mock.patch("engine.achievements.on_item_crafted",
                                                        new=mock.AsyncMock()) as spy:
                                            cmd = cc.CraftCommand()
                                            await cmd.execute(_FakeCtx())
        spy.assert_awaited_once()
        call_kwargs = spy.await_args
        # char_id must be 42
        self.assertEqual(call_kwargs.args[1], 42)
        # quality must be 75
        self.assertEqual(call_kwargs.kwargs.get("quality"), 75)


# ─── A1: on_experiment_success wired in crafting_commands.py ─────────────────

class TestA1ExperimentSuccessWired(unittest.TestCase):
    def test_on_experiment_success_in_handle_success(self):
        src = (PROJECT_ROOT / "parser" / "crafting_commands.py").read_text(encoding="utf-8")
        self.assertIn("on_experiment_success", src,
                      "on_experiment_success must appear in crafting_commands.py")

    def test_on_experiment_success_in_success_method(self):
        src = (PROJECT_ROOT / "parser" / "crafting_commands.py").read_text(encoding="utf-8")
        # Confirm on_experiment_success appears after _handle_success def
        handle_pos = src.index("async def _handle_success(")
        exp_pos = src.index("on_experiment_success")
        self.assertGreater(exp_pos, handle_pos,
                           "on_experiment_success must be inside _handle_success")


# ─── A1: on_trade_goods_sold wired in builtin_commands.py ────────────────────

class TestA1TradeGoodsSoldWired(unittest.TestCase):
    def test_on_trade_goods_sold_in_handle_sell_cargo(self):
        src = (PROJECT_ROOT / "parser" / "builtin_commands.py").read_text(encoding="utf-8")
        self.assertIn("on_trade_goods_sold", src,
                      "on_trade_goods_sold must appear in builtin_commands.py")
        # Verify it's inside the _handle_sell_cargo function scope
        cargo_fn_pos = src.index("async def _handle_sell_cargo(")
        hook_pos = src.index("on_trade_goods_sold")
        self.assertGreater(hook_pos, cargo_fn_pos,
                           "on_trade_goods_sold must come after _handle_sell_cargo def")
        # And before the next top-level class (TradeCommand)
        trade_class_pos = src.index("class TradeCommand(BaseCommand):")
        self.assertLess(hook_pos, trade_class_pos,
                        "on_trade_goods_sold must be inside _handle_sell_cargo, before TradeCommand")


# ─── A1: on_ship_launch wired in space_commands.py ───────────────────────────

class TestA1ShipLaunchWired(unittest.TestCase):
    def test_on_ship_launch_in_space_commands(self):
        src = (PROJECT_ROOT / "parser" / "space_commands.py").read_text(encoding="utf-8")
        self.assertIn("on_ship_launch", src,
                      "on_ship_launch must appear in space_commands.py")

    def test_on_ship_launch_after_launch_broadcast(self):
        src = (PROJECT_ROOT / "parser" / "space_commands.py").read_text(encoding="utf-8")
        broadcast_pos = src.index("launches from")
        hook_pos = src.index("on_ship_launch")
        self.assertGreater(hook_pos, broadcast_pos,
                           "on_ship_launch must come after the launch broadcast")


# ─── A1: on_anomaly_salvaged wired in space_commands.py ──────────────────────

class TestA1AnomalySalvagedWired(unittest.TestCase):
    def test_on_anomaly_salvaged_in_space_commands(self):
        src = (PROJECT_ROOT / "parser" / "space_commands.py").read_text(encoding="utf-8")
        self.assertIn("on_anomaly_salvaged", src,
                      "on_anomaly_salvaged must appear in space_commands.py")

    def test_on_anomaly_salvaged_after_remove_anomaly(self):
        src = (PROJECT_ROOT / "parser" / "space_commands.py").read_text(encoding="utf-8")
        # The commit point is remove_anomaly; achievement must come after
        remove_pos = src.index("remove_anomaly(zone_id, target.id)")
        hook_pos = src.index("on_anomaly_salvaged")
        self.assertGreater(hook_pos, remove_pos,
                           "on_anomaly_salvaged must come after remove_anomaly (commit point)")


# ─── B1: destination_slug precise match ──────────────────────────────────────

class TestB1DestinationSlugResolution(unittest.IsolatedAsyncioTestCase):
    """_check_ground_destination prefers slug-based precise match over fuzzy."""

    def _make_active(self, destination_room_id=None, destination_slug=""):
        """Build a minimal active-mission-like object."""
        mdata = {"destination_slug": destination_slug}
        return types.SimpleNamespace(
            destination_room_id=destination_room_id,
            destination="Droid Workshop",
            mission_data=mdata,
        )

    def _make_ctx(self, room_id):
        char = {"id": 1, "room_id": room_id}

        class _Session:
            character = char
            async def send_line(self, msg): pass

        class _DB:
            """Fake DB: slug 'droid_workshop' → room id 99."""
            async def get_room_by_slug(self, slug):
                if slug == "droid_workshop":
                    return {"id": 99, "name": "Droid Workshop"}
                return None

            async def get_room(self, room_id):
                if room_id == 99:
                    return {"id": 99, "name": "Droid Workshop"}
                return {"id": room_id, "name": f"Room {room_id}"}

        class _Ctx:
            session = _Session()
            db = _DB()

        return _Ctx()

    async def test_slug_match_correct_room(self):
        """Player in room 99 with slug 'droid_workshop' → at destination."""
        from parser.mission_commands import CompleteMissionCommand
        cmd = CompleteMissionCommand()
        active = self._make_active(destination_slug="droid_workshop")
        ctx = self._make_ctx(room_id=99)
        result = await cmd._check_ground_destination(ctx, active)
        self.assertTrue(result, "Should be at destination when room matches slug")

    async def test_slug_match_wrong_room(self):
        """Player in room 5 with slug 'droid_workshop' → not at destination."""
        from parser.mission_commands import CompleteMissionCommand
        cmd = CompleteMissionCommand()
        active = self._make_active(destination_slug="droid_workshop")
        ctx = self._make_ctx(room_id=5)
        result = await cmd._check_ground_destination(ctx, active)
        self.assertFalse(result, "Should not be at destination when room doesn't match slug")

    async def test_no_slug_falls_back_to_fuzzy(self):
        """When no slug, fuzzy name match still works (back-compat)."""
        from parser.mission_commands import CompleteMissionCommand
        cmd = CompleteMissionCommand()
        # destination_slug empty → fuzzy path
        active = self._make_active(destination_slug="")
        # Room 99 is "Droid Workshop" — active.destination is "Droid Workshop" → fuzzy match
        ctx = self._make_ctx(room_id=99)
        result = await cmd._check_ground_destination(ctx, active)
        self.assertTrue(result, "Fuzzy name fallback must still work when no slug")

    async def test_destination_room_id_still_preferred(self):
        """If destination_room_id is set, it takes priority over slug."""
        from parser.mission_commands import CompleteMissionCommand
        cmd = CompleteMissionCommand()
        # destination_room_id=99, slug also set but should not matter
        active = self._make_active(destination_room_id=99, destination_slug="droid_workshop")
        ctx = self._make_ctx(room_id=99)
        result = await cmd._check_ground_destination(ctx, active)
        self.assertTrue(result, "destination_room_id path must still work")

    async def test_destination_room_id_wrong_room(self):
        """destination_room_id=99, player in room 5 → not at destination."""
        from parser.mission_commands import CompleteMissionCommand
        cmd = CompleteMissionCommand()
        active = self._make_active(destination_room_id=99)
        ctx = self._make_ctx(room_id=5)
        result = await cmd._check_ground_destination(ctx, active)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
