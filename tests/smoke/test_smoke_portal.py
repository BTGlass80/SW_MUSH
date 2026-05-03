# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_portal.py — Pytest entry points for the web
portal HTTP smoke scenarios (HX1–HX8). Drop 1 Block E.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import portal


pytestmark = pytest.mark.smoke


class TestPortal:
    """Web portal HTTP API: reference, search, /who, login + /me, ACL."""

    async def test_hx1_reference_index_shows_player_entries(self, harness):
        await portal.hx1_reference_index_shows_player_entries(harness)

    async def test_hx2_reference_search_finds_quest(self, harness):
        await portal.hx2_reference_search_finds_quest(harness)

    async def test_hx3_reference_search_finds_craft(self, harness):
        await portal.hx3_reference_search_finds_craft(harness)

    async def test_hx4_reference_entry_renders(self, harness):
        await portal.hx4_reference_entry_renders(harness)

    async def test_hx5_reference_entry_404(self, harness):
        await portal.hx5_reference_entry_404(harness)

    async def test_hx6_who_returns_online_characters(self, harness):
        await portal.hx6_who_returns_online_characters(harness)

    async def test_hx7_login_then_me_roundtrip(self, harness):
        await portal.hx7_login_then_me_roundtrip(harness)

    async def test_hx8_admin_entries_hidden_from_non_admin(self, harness):
        await portal.hx8_admin_entries_hidden_from_non_admin(harness)
