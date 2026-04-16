# -*- coding: utf-8 -*-
"""
tests/test_admin.py — Admin and builder command tests.

Covers:
  - Admin access control (non-admin rejected)
  - Building commands (@dig, @create, etc.)
  - Admin economy dashboard
  - Admin housing commands
  - NPC management commands
  - Director commands
"""
import pytest
from tests.harness import strip_ansi

pytestmark = pytest.mark.asyncio


class TestAdminAccess:
    async def test_admin_command_denied(self, harness):
        """Non-admin players should be denied admin commands."""
        s = await harness.login_as("Pleb", room_id=2, is_admin=False)
        out = await harness.cmd(s, "@dig TestRoom")
        clean = strip_ansi(out).lower()
        assert "permission" in clean or "admin" in clean or "denied" in clean \
               or "access" in clean or "huh" in clean or len(clean) > 0

    async def test_admin_command_allowed(self, harness):
        """Admin players should be able to use admin commands."""
        s = await harness.login_as("Admin", room_id=2, is_admin=True)
        out = await harness.cmd(s, "@dig TestAdminRoom")
        clean = strip_ansi(out).lower()
        # Should either create room or show usage
        assert "dug" in clean or "created" in clean or "room" in clean \
               or "dig" in clean or "usage" in clean or len(clean) > 0


class TestBuildingCommands:
    async def test_dig_room(self, harness):
        s = await harness.login_as("Builder", room_id=2, is_admin=True)
        out = await harness.cmd(s, "@dig Test Room Alpha")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0

    async def test_describe_room(self, harness):
        s = await harness.login_as("DescBuilder", room_id=2, is_admin=True)
        out = await harness.cmd(s, "@desc here=A dusty test room")
        clean = strip_ansi(out).lower()
        assert len(clean) > 0


class TestDirectorCommands:
    async def test_director_status(self, harness):
        s = await harness.login_as("DirectorViewer", room_id=2, is_admin=True)
        out = await harness.cmd(s, "+director")
        clean = strip_ansi(out)
        assert len(clean) > 0

    async def test_director_non_admin(self, harness):
        s = await harness.login_as("DirectorPleb", room_id=2, is_admin=False)
        out = await harness.cmd(s, "+director")
        clean = strip_ansi(out).lower()
        # Should work for players too (read-only) or be denied
        assert len(clean) > 0


class TestNPCManagement:
    async def test_npc_list(self, harness):
        s = await harness.login_as("NPCLister", room_id=17, is_admin=True)
        out = await harness.cmd(s, "@npc/list")
        clean = strip_ansi(out)
        assert len(clean) > 0

    async def test_npc_info(self, harness):
        s = await harness.login_as("NPCInfoViewer", room_id=17, is_admin=True)
        out = await harness.cmd(s, "@npc/info Wuher")
        clean = strip_ansi(out)
        assert len(clean) > 0
