"""
tests/test_qa_m_wear_inventory_lie.py — QA MEDIUM regression: wear/equip lie about inventory.

`find_carried_gear` skips items whose key isn't in the weapon registry.
Before this fix, WearCommand / EquipCommand would say "you aren't carrying X"
even when X was in the player's inventory — a lie. The fix adds a raw-scan
fallback that detects the item in carried[] and surfaces an honest message:
"you have it but it can't be equipped — contact an admin."
"""
import inspect
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── find_carried_gear skips items not in the registry (existing contract) ─────

def test_find_carried_gear_skips_unregistered_key():
    """find_carried_gear returns (None, None, None) for items not in the registry."""
    from engine.items import find_carried_gear
    from engine.weapons import get_weapon_registry

    wr = get_weapon_registry()
    unknown_key = "phantom_armor_xyz_not_in_registry"
    carried = [{"key": unknown_key, "name": "Phantom Armor", "type": "armor"}]
    idx, d, w = find_carried_gear(carried, "phantom", wr, want_armor=True)
    assert idx is None and d is None and w is None


def test_find_carried_gear_skips_unregistered_weapon_key():
    """Same contract for weapons."""
    from engine.items import find_carried_gear
    from engine.weapons import get_weapon_registry

    wr = get_weapon_registry()
    unknown_key = "phantom_blaster_xyz_not_in_registry"
    carried = [{"key": unknown_key, "name": "Phantom Blaster", "type": "weapon"}]
    idx, d, w = find_carried_gear(carried, "phantom", wr, want_armor=False)
    assert idx is None and d is None and w is None


# ── WearCommand has the honest-error fallback in source ───────────────────────

def test_wear_command_has_unregistered_item_branch():
    """WearCommand.execute must contain the raw-scan fallback for unregistered items."""
    from parser.builtin_commands import WearCommand

    src = inspect.getsource(WearCommand.execute)
    assert "can't be equipped" in src, (
        "WearCommand.execute missing the honest error for items in inventory "
        "that aren't in the weapon registry"
    )
    assert "contact an admin" in src, (
        "WearCommand.execute should tell the player to contact an admin for "
        "unregistered items"
    )


def test_wear_command_raw_scan_checks_key_and_name():
    """The raw-scan in WearCommand must check both 'key' and 'name' fields."""
    from parser.builtin_commands import WearCommand

    src = inspect.getsource(WearCommand.execute)
    assert 'd.get("key"' in src or "d.get('key'" in src, (
        "WearCommand.execute raw-scan should match on item key"
    )
    assert 'd.get("name"' in src or "d.get('name'" in src, (
        "WearCommand.execute raw-scan should match on item name"
    )


# ── EquipCommand has the honest-error fallback in source ──────────────────────

def test_equip_command_has_unregistered_item_branch():
    """EquipCommand.execute must contain the raw-scan fallback for unregistered items."""
    from parser.builtin_commands import EquipCommand

    src = inspect.getsource(EquipCommand.execute)
    assert "can't be equipped" in src, (
        "EquipCommand.execute missing the honest error for items in inventory "
        "that aren't in the weapon registry"
    )
    assert "contact an admin" in src, (
        "EquipCommand.execute should tell the player to contact an admin for "
        "unregistered items"
    )


def test_equip_command_raw_scan_checks_key_and_name():
    """The raw-scan in EquipCommand must check both 'key' and 'name' fields."""
    from parser.builtin_commands import EquipCommand

    src = inspect.getsource(EquipCommand.execute)
    assert 'd.get("key"' in src or "d.get('key'" in src, (
        "EquipCommand.execute raw-scan should match on item key"
    )
    assert 'd.get("name"' in src or "d.get('name'" in src, (
        "EquipCommand.execute raw-scan should match on item name"
    )


# ── Raw-scan logic is correct (unit test the inline pattern) ─────────────────

def _raw_scan(carried: list, needle_arg: str) -> bool:
    """Mirror of the inline raw-scan logic added to both commands."""
    needle = (needle_arg or "").strip().lower()
    return bool(needle) and any(
        (needle in d.get("key", "").lower() or needle in d.get("name", "").lower())
        for d in carried if isinstance(d, dict) and d.get("key")
    )


def test_raw_scan_finds_by_key():
    carried = [{"key": "mystery_armor", "name": "Mystery Armor"}]
    assert _raw_scan(carried, "mystery_armor")


def test_raw_scan_finds_by_name_substring():
    carried = [{"key": "mystery_armor", "name": "Mystery Armor"}]
    assert _raw_scan(carried, "mystery")


def test_raw_scan_finds_case_insensitive():
    carried = [{"key": "MYSTERY_ARMOR", "name": "Mystery Armor"}]
    assert _raw_scan(carried, "mystery armor")


def test_raw_scan_misses_absent_item():
    carried = [{"key": "totally_different", "name": "Totally Different"}]
    assert not _raw_scan(carried, "mystery")


def test_raw_scan_skips_dicts_without_key():
    carried = [{"name": "No Key Item"}]  # no 'key' field
    assert not _raw_scan(carried, "no key")


def test_raw_scan_skips_non_dicts():
    carried = ["string_item", 42, None]
    assert not _raw_scan(carried, "string")


def test_raw_scan_empty_carried():
    assert not _raw_scan([], "blaster")


def test_raw_scan_empty_needle():
    carried = [{"key": "blaster_pistol", "name": "Blaster Pistol"}]
    assert not _raw_scan(carried, "")
    assert not _raw_scan(carried, "  ")
