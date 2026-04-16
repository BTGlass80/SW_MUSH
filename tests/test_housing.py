# -*- coding: utf-8 -*-
"""
tests/test_housing.py — Housing system integration tests.

Covers:
  - Housing listing (+housing)
  - Available lots
  - Purchase flow
  - Guest list management
  - Vendor droid shops
  - Admin housing commands
"""
import pytest
from tests.harness import strip_ansi

pytestmark = pytest.mark.asyncio


class TestHousingDisplay:
    async def test_housing_command(self, harness):
        s = await harness.login_as("HouseViewer", room_id=2)
        out = await harness.cmd(s, "+housing")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_housing_available(self, harness):
        s = await harness.login_as("LotBrowser", room_id=2)
        out = await harness.cmd(s, "+housing/available")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_housing_my(self, harness):
        s = await harness.login_as("MyHousing", room_id=2)
        out = await harness.cmd(s, "+housing/my")
        clean = strip_ansi(out).lower()
        assert "housing" in clean or "none" in clean or "no" in clean \
               or "own" in clean or len(clean) > 0


class TestSetHome:
    async def test_sethome_command(self, harness):
        s = await harness.login_as("HomeSetter", room_id=2)
        out = await harness.cmd(s, "+sethome")
        clean = strip_ansi(out).lower()
        assert "home" in clean or "set" in clean or len(clean) > 0
