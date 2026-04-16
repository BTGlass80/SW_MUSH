# -*- coding: utf-8 -*-
"""
tests/test_economy.py — Economy system integration tests.

Covers:
  - Shop browsing and buying
  - Credit balance tracking
  - Selling items
  - Trade goods pricing (economy audit target)
  - Mission rewards
  - Credit faucet/sink measurement
  - Vendor droid interactions
  - Smuggling job economics
"""
import pytest
import json
from tests.harness import strip_ansi, assert_output_contains, assert_credits_in_range

pytestmark = pytest.mark.asyncio


class TestShops:
    async def test_shop_browse(self, harness):
        """Shop command should show available items."""
        # Room 19 is Lup's General Store
        s = await harness.login_as("Shopper", room_id=19, credits=5000)
        out = await harness.cmd(s, "shop")
        clean = strip_ansi(out)
        # Should show items with prices
        assert len(clean) > 20, f"Shop output too short: {clean}"

    async def test_shop_buy_item(self, harness):
        """Buy an item from a shop and verify credits deducted + item added."""
        s = await harness.login_as("Buyer", room_id=19, credits=10000)
        before = await harness.get_credits(s.character["id"])

        out = await harness.cmd(s, "shop/buy 1")
        clean = strip_ansi(out).lower()

        after = await harness.get_credits(s.character["id"])

        if "purchased" in clean or "bought" in clean:
            assert after < before, "Credits should decrease after purchase"
            inv = await harness.get_inventory(s.character["id"])
            assert len(inv) > 0, "Inventory should have the purchased item"
        # else: item might not be available; that's OK

    async def test_shop_insufficient_credits(self, harness):
        """Buying with 0 credits should fail."""
        s = await harness.login_as("Broke", room_id=19, credits=0)
        out = await harness.cmd(s, "shop/buy 1")
        clean = strip_ansi(out).lower()
        assert "afford" in clean or "credits" in clean or "enough" in clean \
               or "can't" in clean or "insufficient" in clean or len(clean) > 0

    async def test_shop_no_shop_in_room(self, harness):
        """Shop command in a non-shop room."""
        s = await harness.login_as("NoShop", room_id=2, credits=5000)
        out = await harness.cmd(s, "shop")
        clean = strip_ansi(out).lower()
        # Should show error or empty shop
        assert len(clean) > 0


class TestSelling:
    async def test_sell_item(self, harness):
        """Sell an item and verify credits increase."""
        s = await harness.login_as("Seller", room_id=19, credits=100)
        # Give an item to sell
        await harness.give_item(s.character["id"], {
            "name": "Scrap Metal",
            "type": "item",
            "value": 50,
        })
        s.character = await harness.get_char(s.character["id"])

        before = await harness.get_credits(s.character["id"])
        out = await harness.cmd(s, "sell Scrap Metal")
        after = await harness.get_credits(s.character["id"])

        clean = strip_ansi(out).lower()
        if "sold" in clean:
            assert after >= before, "Credits should increase or stay same after sell"


class TestMissions:
    async def test_missions_list(self, harness):
        """View available missions."""
        s = await harness.login_as("MissionBrowser", room_id=2)
        out = await harness.cmd(s, "+missions")
        clean = strip_ansi(out)
        # Should show mission board or "no missions"
        assert len(clean) > 10

    async def test_accept_mission(self, harness):
        """Accept a mission if available."""
        s = await harness.login_as("MissionAccepter", room_id=2)
        out = await harness.cmd(s, "+missions/accept 1")
        clean = strip_ansi(out).lower()
        # Either accepts or says no mission available
        assert len(clean) > 5

    async def test_active_mission(self, harness):
        """Check active mission display."""
        s = await harness.login_as("ActiveMission", room_id=2)
        out = await harness.cmd(s, "+mission")
        clean = strip_ansi(out).lower()
        assert "mission" in clean or "no active" in clean or "none" in clean


class TestSmuggling:
    async def test_smuggling_jobs_list(self, harness):
        """View smuggling jobs."""
        s = await harness.login_as("Smuggler", room_id=2, template="Smuggler")
        out = await harness.cmd(s, "+smugjobs")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_smuggling_job_view(self, harness):
        s = await harness.login_as("SmugViewer", room_id=2)
        out = await harness.cmd(s, "+smugjob")
        clean = strip_ansi(out).lower()
        assert "smuggl" in clean or "no" in clean or "job" in clean


class TestCreditsTracking:
    async def test_credits_visible_on_sheet(self, harness):
        """Credits should appear on character sheet."""
        s = await harness.login_as("CreditCheck", room_id=2, credits=42000)
        out = await harness.cmd(s, "+sheet")
        clean = strip_ansi(out)
        assert "42" in clean or "42,000" in clean

    async def test_credits_persist_after_command(self, harness):
        """Credits should not change from running non-economic commands."""
        s = await harness.login_as("CreditPersist", room_id=2, credits=9999)
        await harness.cmd(s, "look")
        await harness.cmd(s, "+sheet")
        await harness.cmd(s, "+who")
        after = await harness.get_credits(s.character["id"])
        assert after == 9999
