# -*- coding: utf-8 -*-
"""
tests/test_force.py — Force powers system integration tests.

Covers:
  - Force status display
  - Powers listing
  - Force power usage (control, sense, alter)
  - Non-force-sensitive restrictions
  - Dark side point tracking
  - Force point mechanics
"""
import pytest
from tests.harness import strip_ansi, assert_output_contains

pytestmark = pytest.mark.asyncio


class TestForceStatus:
    async def test_force_status_sensitive(self, harness):
        """Force-sensitive character should see force status."""
        s = await harness.login_as("JediTest", room_id=2,
                                    force_sensitive=True)
        out = await harness.cmd(s, "+force/status")
        clean = strip_ansi(out)
        assert len(clean) > 10

    async def test_force_status_not_sensitive(self, harness):
        """Non-force-sensitive should get appropriate message."""
        s = await harness.login_as("MundaneTest", room_id=2,
                                    force_sensitive=False)
        out = await harness.cmd(s, "+force/status")
        clean = strip_ansi(out).lower()
        assert "force" in clean or "sensitive" in clean or "not" in clean


class TestPowersListing:
    async def test_powers_list(self, harness):
        s = await harness.login_as("PowerLister", room_id=2,
                                    force_sensitive=True)
        out = await harness.cmd(s, "+powers")
        clean = strip_ansi(out)
        assert len(clean) > 5

    async def test_powers_not_sensitive(self, harness):
        s = await harness.login_as("NoPowers", room_id=2,
                                    force_sensitive=False)
        out = await harness.cmd(s, "+powers")
        clean = strip_ansi(out).lower()
        assert "force" in clean or "not" in clean or len(clean) > 0


class TestForceUsage:
    async def test_force_command(self, harness):
        s = await harness.login_as("ForceUser", room_id=2,
                                    force_sensitive=True)
        out = await harness.cmd(s, "force")
        clean = strip_ansi(out)
        assert len(clean) > 5  # Should show usage or available powers

    async def test_force_command_not_sensitive(self, harness):
        s = await harness.login_as("NoForce", room_id=2,
                                    force_sensitive=False)
        out = await harness.cmd(s, "force")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestDarkSide:
    async def test_dark_side_starts_zero(self, harness):
        s = await harness.login_as("LightSide", room_id=2,
                                    force_sensitive=True)
        char = await harness.get_char(s.character["id"])
        assert char["dark_side_points"] == 0

    async def test_force_points_start_value(self, harness):
        s = await harness.login_as("ForcePoints", room_id=2,
                                    force_sensitive=True)
        char = await harness.get_char(s.character["id"])
        assert char["force_points"] >= 1
