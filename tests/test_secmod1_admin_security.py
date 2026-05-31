# -*- coding: utf-8 -*-
"""
tests/test_secmod1_admin_security.py — SECMOD.1 admin layer + engine
faction-override resolver step.

Per security_zones_design_v1.md §3.2 (the engine resolver branch)
and §9 (the @security admin command).

Drop 2 of the May 21 2026 phantom-rebuild wave. Replaces the
phantom `parser/admin_security_commands` module and the missing
`_apply_faction_override` branch inside `engine/security.py`.

Test sections
=============

Engine (faction-override resolver):
  1.  TestFactionOverrideNoOp           — no override → no change
  2.  TestFactionOverrideBaseGuard      — only SECURED gets downgraded
  3.  TestFactionOverrideNoCharacter    — None character → passthrough
  4.  TestFactionOverrideHostile        — rep ≤ -50 → LAWLESS
  5.  TestFactionOverrideUnfriendly     — rep -49..-25 → LAWLESS
  6.  TestFactionOverrideWary           — rep -24..-1 → no change
  7.  TestFactionOverrideMember         — member (rep>0) → no change
  8.  TestFactionOverrideFailSoft       — orgs lookup raise → no change

Engine (full resolver integration):
  9.  TestResolverIntegration           — get_effective_security end-to-end
 10.  TestClaimUpgradeCompose           — faction-override then claim-upgrade

Parser (AdminSecurityCommand):
 11.  TestCommandSurface                — class attrs, registration
 12.  TestParseLevel                    — _parse_level lenient + invalid
 13.  TestResolveRoom                   — id, slug, missing
 14.  TestZoneShowHappy                 — @security <zone> renders
 15.  TestZoneShowUnknown               — unknown zone → error
 16.  TestZoneSetHappy                  — @security <zone> = <level> writes
 17.  TestZoneSetInvalidLevel           — bad level → error, no write
 18.  TestZoneSetEmptyName              — empty zone → error
 19.  TestOverrideSetHappy              — set to a known faction
 20.  TestOverrideClearHappy            — = none clears
 21.  TestOverrideClearSynonyms         — null/clear/off/- accepted
 22.  TestOverrideUnknownFaction        — rejects, no write
 23.  TestOverrideMissingEquals         — error, no write
 24.  TestOverrideMissingRoom           — error, no write
 25.  TestOverrideMissingFaction        — error, no write
 26.  TestOverrideUnknownRoom           — error, no write
 27.  TestUsageOnEmptyArgs              — prints help, no crash
 28.  TestSubcommandDispatch            — first-token routing
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ═════════════════════════════════════════════════════════════════════
# Engine fakes (used by sections 1–10)
# ═════════════════════════════════════════════════════════════════════


class _FakeDB:
    """Minimal db fake for the engine resolver and parser. Implements
    only what SECMOD.1 actually calls; other attribute access raises
    AssertionError to catch accidental coupling."""

    def __init__(self):
        # Rooms keyed by id; each row is a dict with id/zone_id/name/
        # faction_override/properties.
        self.rooms = {}
        # Zones keyed by id; rows include name + properties json string.
        self.zones = {}
        self.zone_name_index = {}  # lowercase name → id
        # Room slugs (separate index because get_room_by_slug reads JSON).
        self.room_slug_index = {}
        # Org codes -> dict
        self.orgs = {}
        # Char attribute-rep lookups keyed by (char_id, faction_code) → int
        self.attribute_reps = {}
        # Membership rep keyed by (char_id, org_id) → int (or None)
        self.memberships = {}
        # Whether the next get_organization call should raise (set per test)
        self.raise_on_org_lookup = False
        # Mutation log for write-no-write assertions
        self.writes = []

    def add_room(self, room_id, *, name="Test Room", zone_id=1,
                 faction_override=None, slug=None, security=None):
        props = {}
        if slug:
            props["slug"] = slug
            self.room_slug_index[slug] = room_id
        if security:
            props["security"] = security
        import json
        self.rooms[room_id] = {
            "id": room_id,
            "name": name,
            "zone_id": zone_id,
            "faction_override": faction_override,
            "properties": json.dumps(props) if props else "{}",
        }
        return self.rooms[room_id]

    def add_zone(self, zone_id, name, *, security=None,
                  environment=None):
        import json
        props = {}
        if security:
            props["security"] = security
        if environment:
            props["environment"] = environment
        self.zones[zone_id] = {
            "id": zone_id,
            "name": name,
            "properties": json.dumps(props),
        }
        self.zone_name_index[name.lower()] = zone_id
        return self.zones[zone_id]

    def add_org(self, code, *, name=None):
        self.orgs[code] = {
            "id": len(self.orgs) + 1,
            "code": code,
            "name": name or code.title(),
            "org_type": "faction",
        }
        return self.orgs[code]

    # ── read methods consumed by the gate / parser ──

    async def get_room(self, room_id):
        return self.rooms.get(int(room_id)) if room_id else None

    async def get_room_by_slug(self, slug):
        room_id = self.room_slug_index.get(slug)
        return self.rooms.get(room_id) if room_id else None

    async def get_zone(self, zone_id):
        return self.zones.get(int(zone_id)) if zone_id else None

    async def get_zone_by_name(self, name):
        if not name:
            return None
        zid = self.zone_name_index.get(name.strip().lower())
        return self.zones.get(zid) if zid else None

    async def get_organization(self, code):
        if self.raise_on_org_lookup:
            raise RuntimeError("simulated DB failure")
        return self.orgs.get(code)

    async def get_membership(self, char_id, org_id):
        rep = self.memberships.get((char_id, org_id))
        if rep is None:
            return None
        return {"rep_score": rep}

    async def get_room_property(self, room_id, prop_name, default=None):
        room = self.rooms.get(int(room_id)) if room_id else None
        if not room:
            return default
        import json
        try:
            props = json.loads(room.get("properties") or "{}")
        except Exception:
            return default
        return props.get(prop_name, default)

    # ── write methods used by the parser only ──

    async def set_zone_property(self, zone_id, key, value):
        zone = self.zones.get(int(zone_id))
        if not zone:
            return False
        import json
        try:
            props = json.loads(zone.get("properties") or "{}")
        except Exception:
            props = {}
        if value is None:
            props.pop(key, None)
        else:
            props[key] = value
        zone["properties"] = json.dumps(props)
        self.writes.append(("set_zone_property", zone_id, key, value))
        return True

    async def set_room_faction_override(self, room_id, faction):
        room = self.rooms.get(int(room_id))
        if not room:
            return False
        room["faction_override"] = faction
        self.writes.append(("set_room_faction_override", room_id, faction))
        return True


def _make_char(char_id=42, faction_id="independent",
               attribute_reps=None):
    """Build a minimal character dict matching what get_effective_security
    + get_char_faction_rep consume."""
    import json
    attrs = {}
    if attribute_reps:
        attrs["faction_rep"] = dict(attribute_reps)
    return {
        "id": char_id,
        "faction_id": faction_id,
        "attributes": json.dumps(attrs),
    }


# ═════════════════════════════════════════════════════════════════════
# 1. TestFactionOverrideNoOp
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideNoOp(unittest.TestCase):
    def test_no_override_returns_base(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        room = db.add_room(1, faction_override=None)
        char = _make_char()
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.SECURED)


# ═════════════════════════════════════════════════════════════════════
# 2. TestFactionOverrideBaseGuard
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideBaseGuard(unittest.TestCase):
    def test_contested_passes_through(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -75})
        result = _run(_apply_faction_override(
            SecurityLevel.CONTESTED, room, char, db))
        self.assertEqual(result, SecurityLevel.CONTESTED)

    def test_lawless_passes_through(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -75})
        result = _run(_apply_faction_override(
            SecurityLevel.LAWLESS, room, char, db))
        self.assertEqual(result, SecurityLevel.LAWLESS)


# ═════════════════════════════════════════════════════════════════════
# 3. TestFactionOverrideNoCharacter
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideNoCharacter(unittest.TestCase):
    def test_none_character_passes(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, None, db))
        self.assertEqual(result, SecurityLevel.SECURED)


# ═════════════════════════════════════════════════════════════════════
# 4. TestFactionOverrideHostile
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideHostile(unittest.TestCase):
    def test_rep_minus_50_downgrades(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -50})
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_rep_minus_100_downgrades(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -100})
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.LAWLESS)


# ═════════════════════════════════════════════════════════════════════
# 5. TestFactionOverrideUnfriendly
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideUnfriendly(unittest.TestCase):
    def test_rep_minus_25_downgrades(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -25})
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_rep_minus_49_downgrades(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -49})
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.LAWLESS)


# ═════════════════════════════════════════════════════════════════════
# 6. TestFactionOverrideWary
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideWary(unittest.TestCase):
    def test_rep_minus_24_no_downgrade(self):
        """Wary tier (-24..-1) is NOT downgraded — only Hostile or
        Unfriendly per design §3.2 wording 'Hostile or Unfriendly'."""
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -24})
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.SECURED)

    def test_rep_zero_no_downgrade(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": 0})
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.SECURED)


# ═════════════════════════════════════════════════════════════════════
# 7. TestFactionOverrideMember
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideMember(unittest.TestCase):
    def test_member_with_good_rep_no_downgrade(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        org = db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(char_id=99)
        db.memberships[(99, org["id"])] = 50  # honored tier
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        self.assertEqual(result, SecurityLevel.SECURED)


# ═════════════════════════════════════════════════════════════════════
# 8. TestFactionOverrideFailSoft
# ═════════════════════════════════════════════════════════════════════

class TestFactionOverrideFailSoft(unittest.TestCase):
    def test_org_lookup_raise_returns_base(self):
        from engine.security import _apply_faction_override, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(attribute_reps={"empire": -100})
        db.raise_on_org_lookup = True
        result = _run(_apply_faction_override(
            SecurityLevel.SECURED, room, char, db))
        # Fail-soft: even with notional hostile rep, lookup raise → base.
        self.assertEqual(result, SecurityLevel.SECURED)


# ═════════════════════════════════════════════════════════════════════
# 9. TestResolverIntegration
# ═════════════════════════════════════════════════════════════════════

class TestResolverIntegration(unittest.TestCase):
    """End-to-end through get_effective_security on the property
    inheritance path — proves the resolver wires through _finalize."""

    def test_secured_zone_no_override_secured(self):
        from engine.security import (
            get_effective_security, SecurityLevel, clear_all_overrides,
        )
        clear_all_overrides()
        db = _FakeDB()
        db.add_zone(1, "civic", security="secured")
        db.add_room(7, zone_id=1, security="secured")
        char = _make_char()
        result = _run(get_effective_security(7, db, character=char))
        self.assertEqual(result, SecurityLevel.SECURED)

    def test_secured_zone_with_override_hostile_lawless(self):
        from engine.security import (
            get_effective_security, SecurityLevel, clear_all_overrides,
        )
        clear_all_overrides()
        db = _FakeDB()
        db.add_org("empire")
        db.add_zone(1, "civic", security="secured")
        db.add_room(7, zone_id=1, security="secured",
                    faction_override="empire")
        char = _make_char(attribute_reps={"empire": -75})
        result = _run(get_effective_security(7, db, character=char))
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_secured_zone_with_override_friendly_secured(self):
        from engine.security import (
            get_effective_security, SecurityLevel, clear_all_overrides,
        )
        clear_all_overrides()
        db = _FakeDB()
        db.add_org("empire")
        db.add_zone(1, "civic", security="secured")
        db.add_room(7, zone_id=1, security="secured",
                    faction_override="empire")
        char = _make_char(attribute_reps={"empire": 30})  # trusted
        result = _run(get_effective_security(7, db, character=char))
        self.assertEqual(result, SecurityLevel.SECURED)


# ═════════════════════════════════════════════════════════════════════
# 10. TestClaimUpgradeCompose
# ═════════════════════════════════════════════════════════════════════

class TestClaimUpgradeCompose(unittest.TestCase):
    """SYN.1.b stubbed the per-room claim-upgrade mechanic to a no-op;
    SYN.2 (2026-05-24) physically deleted ``_apply_claim_upgrade`` and
    removed its call from ``_finalize``. The faction-override step
    still runs (SECMOD.1, unaffected by the wilderness pivot), so the
    SECURED → LAWLESS downgrade still fires; the LAWLESS → CONTESTED
    upgrade no longer happens.

    Pre-SYN.1.b expected: SECURED → faction_override → LAWLESS →
                          claim_upgrade → CONTESTED.
    Post-SYN.1.b expected: SECURED → faction_override → LAWLESS
                          (no-op claim_upgrade kept the LAWLESS result).
    Post-SYN.2 expected: SECURED → faction_override → LAWLESS
                          (no claim_upgrade step at all).
    """

    def test_faction_override_runs_claim_upgrade_now_noop(self):
        from engine.security import _finalize, SecurityLevel
        db = _FakeDB()
        db.add_org("empire")
        room = db.add_room(1, faction_override="empire")
        char = _make_char(faction_id="rebel",
                          attribute_reps={"empire": -75})
        # SYN.2: _apply_claim_upgrade was deleted from _finalize.
        # The faction-override step alone produces LAWLESS.
        result = _run(_finalize(
            SecurityLevel.SECURED, room, 1, char, db))
        self.assertEqual(result, SecurityLevel.LAWLESS)


# ═════════════════════════════════════════════════════════════════════
# 11. TestCommandSurface
# ═════════════════════════════════════════════════════════════════════

class TestCommandSurface(unittest.TestCase):
    def test_class_attrs(self):
        from parser.admin_security_commands import AdminSecurityCommand
        from parser.commands import AccessLevel
        self.assertEqual(AdminSecurityCommand.key, "@security")
        self.assertEqual(AdminSecurityCommand.access_level,
                         AccessLevel.ADMIN)
        self.assertTrue(AdminSecurityCommand.help_text)
        self.assertTrue(AdminSecurityCommand.usage)

    def test_register(self):
        from parser.admin_security_commands import (
            register_admin_security_commands, AdminSecurityCommand,
        )
        registered = []

        class FakeRegistry:
            def register(self, cmd):
                registered.append(cmd)

        register_admin_security_commands(FakeRegistry())
        self.assertEqual(len(registered), 1)
        self.assertIsInstance(registered[0], AdminSecurityCommand)


# ═════════════════════════════════════════════════════════════════════
# 12. TestParseLevel
# ═════════════════════════════════════════════════════════════════════

class TestParseLevel(unittest.TestCase):
    def test_all_levels(self):
        from parser.admin_security_commands import _parse_level
        for level in ("secured", "contested", "lawless"):
            self.assertEqual(_parse_level(level), level)

    def test_case_insensitive(self):
        from parser.admin_security_commands import _parse_level
        self.assertEqual(_parse_level("SECURED"), "secured")
        self.assertEqual(_parse_level("Contested"), "contested")

    def test_whitespace_tolerant(self):
        from parser.admin_security_commands import _parse_level
        self.assertEqual(_parse_level("  lawless  "), "lawless")

    def test_invalid_returns_none(self):
        from parser.admin_security_commands import _parse_level
        self.assertIsNone(_parse_level("dangerous"))
        self.assertIsNone(_parse_level(""))
        self.assertIsNone(_parse_level("   "))


# ═════════════════════════════════════════════════════════════════════
# 13. TestResolveRoom
# ═════════════════════════════════════════════════════════════════════

class TestResolveRoom(unittest.TestCase):
    def test_by_id(self):
        from parser.admin_security_commands import _resolve_room
        db = _FakeDB()
        db.add_room(42, name="Garrison Foyer")
        room = _run(_resolve_room(db, "42"))
        self.assertIsNotNone(room)
        self.assertEqual(room["id"], 42)

    def test_by_slug(self):
        from parser.admin_security_commands import _resolve_room
        db = _FakeDB()
        db.add_room(42, name="Garrison Foyer",
                    slug="imperial_garrison_foyer")
        room = _run(_resolve_room(db, "imperial_garrison_foyer"))
        self.assertIsNotNone(room)
        self.assertEqual(room["id"], 42)

    def test_unknown_returns_none(self):
        from parser.admin_security_commands import _resolve_room
        db = _FakeDB()
        self.assertIsNone(_run(_resolve_room(db, "999")))
        self.assertIsNone(_run(_resolve_room(db, "no_such_slug")))
        self.assertIsNone(_run(_resolve_room(db, "")))


# ═════════════════════════════════════════════════════════════════════
# Parser fixture
# ═════════════════════════════════════════════════════════════════════


class _FakeSession:
    def __init__(self):
        self.sent = []
        self.char_id = 1
        self.char_name = "AdminGM"

    async def send_line(self, line):
        self.sent.append(line)


def _make_ctx(db, args, *, session=None):
    """Build a CommandContext-shaped object the command will accept."""
    sess = session or _FakeSession()
    ctx = MagicMock()
    ctx.session = sess
    ctx.db = db
    ctx.args = args
    ctx.args_list = args.split() if args else []
    return ctx


# ═════════════════════════════════════════════════════════════════════
# 14. TestZoneShowHappy
# ═════════════════════════════════════════════════════════════════════

class TestZoneShowHappy(unittest.TestCase):
    def test_show_renders_current_level(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_zone(1, "tatooine_market", security="lawless")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "tatooine_market")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("tatooine_market", joined)
        self.assertIn("lawless", joined)
        self.assertEqual(db.writes, [])

    def test_show_default_contested_when_unset(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_zone(1, "newzone")  # no security in props
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "newzone")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("contested", joined)


# ═════════════════════════════════════════════════════════════════════
# 15. TestZoneShowUnknown
# ═════════════════════════════════════════════════════════════════════

class TestZoneShowUnknown(unittest.TestCase):
    def test_unknown_zone_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "nowhere_zone")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("No zone", joined)
        self.assertEqual(db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 16. TestZoneSetHappy
# ═════════════════════════════════════════════════════════════════════

class TestZoneSetHappy(unittest.TestCase):
    def test_set_writes_property(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_zone(1, "tatooine_market", security="contested")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "tatooine_market = secured")
        _run(cmd.execute(ctx))
        self.assertEqual(len(db.writes), 1)
        op, zid, key, val = db.writes[0]
        self.assertEqual(op, "set_zone_property")
        self.assertEqual(zid, 1)
        self.assertEqual(key, "security")
        self.assertEqual(val, "secured")
        joined = "\n".join(ctx.session.sent)
        self.assertIn("secured", joined)


# ═════════════════════════════════════════════════════════════════════
# 17. TestZoneSetInvalidLevel
# ═════════════════════════════════════════════════════════════════════

class TestZoneSetInvalidLevel(unittest.TestCase):
    def test_bad_level_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_zone(1, "tatooine_market", security="contested")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "tatooine_market = dangerous")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])
        joined = "\n".join(ctx.session.sent)
        self.assertIn("Invalid level", joined)


# ═════════════════════════════════════════════════════════════════════
# 18. TestZoneSetEmptyName
# ═════════════════════════════════════════════════════════════════════

class TestZoneSetEmptyName(unittest.TestCase):
    def test_empty_zone_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, " = secured")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])
        joined = "\n".join(ctx.session.sent)
        self.assertIn("zone name", joined.lower())


# ═════════════════════════════════════════════════════════════════════
# 19. TestOverrideSetHappy
# ═════════════════════════════════════════════════════════════════════

class TestOverrideSetHappy(unittest.TestCase):
    def test_override_set_writes(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_org("empire")
        db.add_room(42, name="Garrison Foyer")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 42 = empire")
        _run(cmd.execute(ctx))
        self.assertEqual(len(db.writes), 1)
        op, room_id, faction = db.writes[0]
        self.assertEqual(op, "set_room_faction_override")
        self.assertEqual(room_id, 42)
        self.assertEqual(faction, "empire")

    def test_override_set_by_slug(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_org("empire")
        db.add_room(42, name="Garrison Foyer",
                    slug="imperial_garrison_foyer")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override imperial_garrison_foyer = empire")
        _run(cmd.execute(ctx))
        self.assertEqual(len(db.writes), 1)


# ═════════════════════════════════════════════════════════════════════
# 20. TestOverrideClearHappy
# ═════════════════════════════════════════════════════════════════════

class TestOverrideClearHappy(unittest.TestCase):
    def test_override_clear_with_none(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_room(42, name="Garrison Foyer", faction_override="empire")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 42 = none")
        _run(cmd.execute(ctx))
        self.assertEqual(len(db.writes), 1)
        op, room_id, faction = db.writes[0]
        self.assertEqual(op, "set_room_faction_override")
        self.assertEqual(room_id, 42)
        self.assertIsNone(faction)


# ═════════════════════════════════════════════════════════════════════
# 21. TestOverrideClearSynonyms
# ═════════════════════════════════════════════════════════════════════

class TestOverrideClearSynonyms(unittest.TestCase):
    def test_synonyms_all_clear(self):
        from parser.admin_security_commands import AdminSecurityCommand
        for keyword in ("none", "null", "clear", "off", "-"):
            db = _FakeDB()
            db.add_room(42, faction_override="empire")
            cmd = AdminSecurityCommand()
            ctx = _make_ctx(db, f"override 42 = {keyword}")
            _run(cmd.execute(ctx))
            self.assertEqual(len(db.writes), 1,
                             f"keyword {keyword!r} did not produce a write")
            _, _, faction = db.writes[0]
            self.assertIsNone(faction,
                              f"keyword {keyword!r} did not clear override")


# ═════════════════════════════════════════════════════════════════════
# 22. TestOverrideUnknownFaction
# ═════════════════════════════════════════════════════════════════════

class TestOverrideUnknownFaction(unittest.TestCase):
    def test_unknown_faction_rejected_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_room(42, name="Foyer")
        # No org added — "empire" is unknown in this fake DB.
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 42 = empire")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])
        joined = "\n".join(ctx.session.sent)
        self.assertIn("Unknown faction", joined)


# ═════════════════════════════════════════════════════════════════════
# 23. TestOverrideMissingEquals
# ═════════════════════════════════════════════════════════════════════

class TestOverrideMissingEquals(unittest.TestCase):
    def test_missing_equals_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_room(42)
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 42 empire")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])
        joined = "\n".join(ctx.session.sent)
        self.assertIn("=", joined)


# ═════════════════════════════════════════════════════════════════════
# 24. TestOverrideMissingRoom
# ═════════════════════════════════════════════════════════════════════

class TestOverrideMissingRoom(unittest.TestCase):
    def test_missing_room_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override = empire")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 25. TestOverrideMissingFaction
# ═════════════════════════════════════════════════════════════════════

class TestOverrideMissingFaction(unittest.TestCase):
    def test_missing_faction_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_room(42)
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 42 = ")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 26. TestOverrideUnknownRoom
# ═════════════════════════════════════════════════════════════════════

class TestOverrideUnknownRoom(unittest.TestCase):
    def test_unknown_room_errors_no_write(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_org("empire")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 999 = empire")
        _run(cmd.execute(ctx))
        self.assertEqual(db.writes, [])
        joined = "\n".join(ctx.session.sent)
        self.assertIn("No room", joined)


# ═════════════════════════════════════════════════════════════════════
# 27. TestUsageOnEmptyArgs
# ═════════════════════════════════════════════════════════════════════

class TestUsageOnEmptyArgs(unittest.TestCase):
    def test_empty_args_prints_help(self):
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "")
        _run(cmd.execute(ctx))
        self.assertGreater(len(ctx.session.sent), 0)
        joined = "\n".join(ctx.session.sent)
        self.assertIn("@security", joined)


# ═════════════════════════════════════════════════════════════════════
# 28. TestSubcommandDispatch
# ═════════════════════════════════════════════════════════════════════

class TestSubcommandDispatch(unittest.TestCase):
    """'override' is the only special first-token; anything else is a
    zone reference."""

    def test_override_routes_to_override_handler(self):
        # No '=' → override handler errors with the missing-= message
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "override 1 empire")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("=", joined)

    def test_non_override_routes_to_zone_handler(self):
        # Existing zone, no '=' → show
        from parser.admin_security_commands import AdminSecurityCommand
        db = _FakeDB()
        db.add_zone(1, "myzone", security="secured")
        cmd = AdminSecurityCommand()
        ctx = _make_ctx(db, "myzone")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("security", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
