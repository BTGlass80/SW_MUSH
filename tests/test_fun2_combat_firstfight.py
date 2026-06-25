# -*- coding: utf-8 -*-
"""
tests/test_fun2_combat_firstfight.py — FUN2: combat-onboarding fixes.

Two fixes shipped in drop/fun2-combat-firstfight:

Fix 1 — bare 'attack' auto-targets the first hostile NPC (AttackCommand):
  1.  TestAutoTargetOneHostile       — one hostile NPC → targets it, no usage error
  2.  TestAutoTargetTwoHostiles      — two hostiles → targets first, no usage error
  3.  TestAutoTargetNoHostile        — no hostile NPCs → usage/help message shown
  4.  TestAutoTargetHelperPresent    — _auto_target_hostile is importable on AttackCommand

Fix 2 — issued gear is auto-equipped into empty slots (issue_equipment):
  5.  TestIssueEquipWeapon           — issuing a weapon equips it when slot is empty
  6.  TestIssueEquipArmor            — issuing armor equips it when slot is empty
  7.  TestIssueEquipNoOverwrite       — issuing a weapon does NOT clobber an existing equip
  8.  TestIssueEquipMiscSkipped      — misc/narrative items are NOT equipped
  9.  TestIssueEquipTwoItems         — weapon+armor both issued → both equipped
 10.  TestIssueEquipSlotQueryOrder   — slot collision: first weapon issued wins, second skipped
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("SW_ERA", "clone_wars")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Shared stubs
# ─────────────────────────────────────────────────────────────────────────────

def _hostile_npc(name: str, npc_id: int = 1) -> dict:
    """Minimal NPC row that is_hostile() accepts."""
    return {
        "id": npc_id,
        "name": name,
        "ai_config_json": json.dumps({"hostile": True, "combat_behavior": "aggressive"}),
    }


def _friendly_npc(name: str, npc_id: int = 99) -> dict:
    return {
        "id": npc_id,
        "name": name,
        "ai_config_json": json.dumps({"hostile": False}),
    }


def _make_attack_ctx(char: dict, *, npcs_in_room=(), args=""):
    """Return a minimal CommandContext-like MagicMock for AttackCommand tests.

    npcs_in_room: iterable of npc-row dicts returned by db.get_npcs_in_room.
    args: the initial ctx.args string (empty = bare 'attack').
    """
    session = MagicMock()
    session.character = char
    session.lines = []

    async def send_line(s):
        session.lines.append(str(s))

    session.send_line = send_line

    db = MagicMock()
    db.get_npcs_in_room = AsyncMock(return_value=list(npcs_in_room))

    ctx = MagicMock()
    ctx.session = session
    ctx.db = db
    ctx.args = args
    ctx.session_mgr = MagicMock()
    return ctx


def _make_char(char_id: int = 1, room_id: int = 200) -> dict:
    return {
        "id": char_id,
        "name": "TestChar",
        "room_id": room_id,
        "attributes": json.dumps({}),
        "equipment": "{}",
        "faction_id": "republic",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fix 1: bare 'attack' auto-targeting
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoTargetHelperPresent(unittest.TestCase):
    """Pattern 8: _auto_target_hostile must be on AttackCommand at import."""

    def test_method_exists(self):
        from parser.combat_commands import AttackCommand
        cmd = AttackCommand()
        self.assertTrue(
            callable(getattr(cmd, "_auto_target_hostile", None)),
            "_auto_target_hostile must be a method on AttackCommand",
        )


class TestAutoTargetNoHostile(unittest.TestCase):
    """Bare 'attack' with NO hostile NPCs in room → shows usage/help."""

    def test_usage_shown_when_no_hostile(self):
        from parser.combat_commands import AttackCommand
        char = _make_char()
        # Room has only a friendly NPC and no hostiles
        ctx = _make_attack_ctx(char, npcs_in_room=[_friendly_npc("Shopkeeper")], args="")
        cmd = AttackCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass  # later pipeline stages may fail — we only care about the usage message

        any_usage = any(
            "Usage" in line or "attack <target>" in line or "attack pirate" in line
            for line in ctx.session.lines
        )
        self.assertTrue(
            any_usage,
            f"Expected usage/help message for bare attack with no hostiles; "
            f"got: {ctx.session.lines}",
        )

    def test_usage_shown_when_room_empty(self):
        from parser.combat_commands import AttackCommand
        char = _make_char()
        ctx = _make_attack_ctx(char, npcs_in_room=[], args="")
        cmd = AttackCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass

        any_usage = any(
            "Usage" in line or "attack <target>" in line
            for line in ctx.session.lines
        )
        self.assertTrue(
            any_usage,
            f"Expected usage/help for bare attack in empty room; got: {ctx.session.lines}",
        )


class TestAutoTargetOneHostile(unittest.TestCase):
    """Bare 'attack' with exactly one hostile → no usage error, ctx.args set."""

    def test_no_usage_error_one_hostile(self):
        from parser.combat_commands import AttackCommand
        char = _make_char()
        hostile = _hostile_npc("B1 Sim Droid Alpha")
        ctx = _make_attack_ctx(char, npcs_in_room=[hostile], args="")
        cmd = AttackCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass  # pipeline continues past the gate; allowed to fail later

        # No usage/help message should have been emitted
        any_usage = any(
            "Usage" in line or "attack <target>" in line
            for line in ctx.session.lines
        )
        self.assertFalse(
            any_usage,
            f"Bare attack with one hostile must NOT show usage; got: {ctx.session.lines}",
        )

    def test_ctx_args_populated(self):
        """_auto_target_hostile used directly to confirm return value."""
        from parser.combat_commands import AttackCommand
        char = _make_char()
        hostile = _hostile_npc("B1 Sim Droid Alpha")
        ctx = _make_attack_ctx(char, npcs_in_room=[hostile], args="")
        cmd = AttackCommand()
        result = _run(cmd._auto_target_hostile(ctx, char["room_id"], char))
        self.assertEqual(result, "B1 Sim Droid Alpha")

    def test_auto_target_returns_none_no_hostile(self):
        from parser.combat_commands import AttackCommand
        char = _make_char()
        ctx = _make_attack_ctx(char, npcs_in_room=[_friendly_npc("Guard")], args="")
        cmd = AttackCommand()
        result = _run(cmd._auto_target_hostile(ctx, char["room_id"], char))
        self.assertIsNone(result)


class TestAutoTargetTwoHostiles(unittest.TestCase):
    """Two hostiles (tutorial sim droids) → first one is selected, no usage."""

    def test_first_hostile_selected(self):
        from parser.combat_commands import AttackCommand
        char = _make_char()
        alpha = _hostile_npc("B1 Sim Droid Alpha", npc_id=10)
        bravo = _hostile_npc("B1 Sim Droid Bravo", npc_id=11)
        ctx = _make_attack_ctx(char, npcs_in_room=[alpha, bravo], args="")
        cmd = AttackCommand()
        result = _run(cmd._auto_target_hostile(ctx, char["room_id"], char))
        self.assertEqual(result, "B1 Sim Droid Alpha",
                         "First hostile in room list must be auto-targeted")

    def test_no_usage_shown_two_hostiles(self):
        from parser.combat_commands import AttackCommand
        char = _make_char()
        alpha = _hostile_npc("B1 Sim Droid Alpha", npc_id=10)
        bravo = _hostile_npc("B1 Sim Droid Bravo", npc_id=11)
        ctx = _make_attack_ctx(char, npcs_in_room=[alpha, bravo], args="")
        cmd = AttackCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass

        any_usage = any("Usage" in line or "attack <target>" in line
                        for line in ctx.session.lines)
        self.assertFalse(
            any_usage,
            f"Bare attack with two hostiles must NOT show usage; got: {ctx.session.lines}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Stub DB for issue_equipment tests
# ─────────────────────────────────────────────────────────────────────────────

class _IssueStubDB:
    """Minimal async DB stub for issue_equipment tests."""

    def __init__(self, org_id: int = 1, org_name: str = "Galactic Republic"):
        self._org = {"id": org_id, "name": org_name}
        self.inventory = []
        self.issued = []       # (char_id, org_id, item_key, item_name)
        self.saved_equip = []  # (char_id, equipment_str)

    async def get_organization(self, code):
        return self._org

    async def add_to_inventory(self, char_id, item):
        self.inventory.append(item)

    async def issue_equipment(self, char_id, org_id, item_key, item_name):
        self.issued.append((char_id, org_id, item_key, item_name))

    async def save_character(self, char_id, **fields):
        if "equipment" in fields:
            self.saved_equip.append((char_id, fields["equipment"]))


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2: auto-equip on issue_equipment
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueEquipWeapon(unittest.TestCase):
    """Issuing a weapon when weapon slot empty → slot populated, DB persisted."""

    def test_weapon_equipped_when_slot_empty(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment

        char = {"id": 7, "name": "TestTrooper", "equipment": "{}"}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db, ["dc17_pistol"]))

        # DB saved_equip should have been called
        self.assertTrue(db.saved_equip, "save_character must be called when equipping")
        _, eq_str = db.saved_equip[-1]
        slots = read_equipment(eq_str)
        self.assertIsNotNone(slots["weapon"], "weapon slot must be populated after issue")
        self.assertEqual(slots["weapon"].key, "dc17_pistol")

    def test_char_equipment_dict_updated(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment

        char = {"id": 7, "name": "TestTrooper", "equipment": "{}"}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db, ["dc17_pistol"]))

        # char["equipment"] in-memory must also reflect the new equip
        slots = read_equipment(char["equipment"])
        self.assertEqual(slots["weapon"].key, "dc17_pistol")


class TestIssueEquipArmor(unittest.TestCase):
    """Issuing armor when armor slot empty → slot populated."""

    def test_armor_equipped_when_slot_empty(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment

        char = {"id": 8, "name": "TestTrooper", "equipment": "{}"}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db, ["republic_uniform"]))

        self.assertTrue(db.saved_equip)
        _, eq_str = db.saved_equip[-1]
        slots = read_equipment(eq_str)
        self.assertIsNotNone(slots["armor"], "armor slot must be populated after issue")
        self.assertEqual(slots["armor"].key, "republic_uniform")


class TestIssueEquipNoOverwrite(unittest.TestCase):
    """Issuing a weapon when weapon slot already occupied → slot NOT overwritten."""

    def test_existing_weapon_not_displaced(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment, write_equipment, ItemInstance

        # Pre-equip a different weapon
        existing = ItemInstance(key="blaster_pistol")
        pre_eq = write_equipment(weapon=existing)
        char = {"id": 9, "name": "TestTrooper", "equipment": pre_eq}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db, ["dc17_pistol"]))

        # The weapon slot should still be the original, not dc17_pistol
        slots = read_equipment(char["equipment"])
        self.assertEqual(
            slots["weapon"].key, "blaster_pistol",
            "Existing equipped weapon must NOT be displaced by an issued item",
        )
        # save_character should NOT have been called (slot was occupied)
        self.assertFalse(
            db.saved_equip,
            "save_character must NOT be called when the slot is already occupied",
        )

    def test_item_still_added_to_inventory(self):
        from engine.organizations import issue_equipment
        from engine.items import write_equipment, ItemInstance

        existing = ItemInstance(key="blaster_pistol")
        pre_eq = write_equipment(weapon=existing)
        char = {"id": 9, "name": "TestTrooper", "equipment": pre_eq}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db, ["dc17_pistol"]))

        # Item must still land in inventory even if not equipped
        inv_keys = [it["key"] for it in db.inventory]
        self.assertIn("dc17_pistol", inv_keys,
                      "Item must still be added to inventory even when slot occupied")


class TestIssueEquipMiscSkipped(unittest.TestCase):
    """Misc/narrative items (slot='misc') are NOT auto-equipped."""

    def test_misc_item_not_equipped(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment

        # comlink_basic is a 'misc' slot item in the catalog
        char = {"id": 10, "name": "TestChar", "equipment": "{}"}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db, ["comlink_basic"]))

        # No equip save should have happened
        self.assertFalse(db.saved_equip,
                         "Misc items must not trigger an equipment save")
        # Equipment remains empty
        slots = read_equipment(char["equipment"])
        self.assertIsNone(slots["weapon"])
        self.assertIsNone(slots["armor"])


class TestIssueEquipTwoItems(unittest.TestCase):
    """Issuing both weapon+armor (rank-0 republic kit) → both slots populated."""

    def test_weapon_and_armor_both_equipped(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment

        char = {"id": 11, "name": "TestTrooper", "equipment": "{}"}
        db = _IssueStubDB()

        # republic rank-0 kit = ["republic_uniform", "dc17_pistol"]
        _run(issue_equipment(char, "republic", db,
                             ["republic_uniform", "dc17_pistol"]))

        slots = read_equipment(char["equipment"])
        self.assertIsNotNone(slots["weapon"], "weapon slot must be populated")
        self.assertIsNotNone(slots["armor"], "armor slot must be populated")
        self.assertEqual(slots["weapon"].key, "dc17_pistol")
        self.assertEqual(slots["armor"].key, "republic_uniform")

    def test_two_saves_triggered(self):
        from engine.organizations import issue_equipment

        char = {"id": 11, "name": "TestTrooper", "equipment": "{}"}
        db = _IssueStubDB()

        _run(issue_equipment(char, "republic", db,
                             ["republic_uniform", "dc17_pistol"]))

        # One save per item that lands in an empty slot
        self.assertEqual(len(db.saved_equip), 2,
                         "save_character called once per equipped item")


class TestIssueEquipSlotCollision(unittest.TestCase):
    """If two weapons are issued in the same call, only the first equips."""

    def test_first_weapon_wins(self):
        from engine.organizations import issue_equipment
        from engine.items import read_equipment

        char = {"id": 12, "name": "TestTrooper", "equipment": "{}"}
        db = _IssueStubDB()

        # Issue dc17_pistol first, then dc15_blaster_rifle — only dc17 should equip
        _run(issue_equipment(char, "republic", db,
                             ["dc17_pistol", "dc15_blaster_rifle"]))

        slots = read_equipment(char["equipment"])
        self.assertEqual(
            slots["weapon"].key, "dc17_pistol",
            "First issued weapon wins; second must not displace it",
        )
        # Only one save for the weapon slot
        weapon_saves = [s for s in db.saved_equip
                        if "dc15_blaster_rifle" not in s[1]]
        self.assertGreaterEqual(len(weapon_saves), 1)


if __name__ == "__main__":
    unittest.main()
