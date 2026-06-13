# -*- coding: utf-8 -*-
"""
tests/test_look_examine_inventory.py — Regression tests for look/examine
on carried inventory items (look_examine_inventory drop).

Bug: `look <item in inventory>` (and `examine <item in inventory>`) would
always fall through to "You don't see '...' here." / "You see nothing
special about '...'." because neither LookCommand._look_at nor
ExamineCommand ever checked the player's own inventory.

Fix: _describe_inventory_item() helper (parser/builtin_commands.py) is
called from both command paths after room/fragment checks miss.

Coverage:
  L1 — look <exact key> surfaces the item's description
  L2 — look <name partial> surfaces the item's description
  L3 — look <nonexistent arg> still says "You don't see"
  L4 — look <item with no description in inv dict> falls back to
        EQUIPMENT_CATALOG description
  E1 — examine <exact key> surfaces the item's description
  E2 — examine <nonexistent arg> still says "You see nothing special"
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


# ── helpers ────────────────────────────────────────────────────────────────

_ITEM_KEY = "binder_cuffs"
_ITEM_NAME = "Binder Cuffs"
_EXPECTED_DESC_FRAGMENT = "restraints"     # from EQUIPMENT_CATALOG

# An item with an inline description in the inventory dict (simulates a
# commissary-bought item that copies "description" into the inv entry).
_INLINE_KEY = "slicing_kit"
_INLINE_NAME = "Slicing Kit"
_INLINE_DESC = "Electronic intrusion toolkit. +1D to computer slicing."


# ── smoke scenarios (called by TestLookExamineInventory) ──────────────────

async def _seed_items(h, session):
    """Give the test character both test items via harness.give_item."""
    char = session.character
    # Item 1: carries NO inline description — must fall back to EQUIPMENT_CATALOG
    await h.give_item(char["id"], {
        "key": _ITEM_KEY,
        "name": _ITEM_NAME,
        "slot": "misc",
        # intentionally omitting "description" to test EQUIPMENT_CATALOG fallback
    })
    # Item 2: carries inline description
    await h.give_item(char["id"], {
        "key": _INLINE_KEY,
        "name": _INLINE_NAME,
        "slot": "misc",
        "description": _INLINE_DESC,
    })
    # Reload character so session sees the updated inventory
    char_reloaded = await h.get_char(char["id"])
    session.character = char_reloaded


async def l1_look_exact_key(h):
    """L1 — look <exact key> surfaces item description from EQUIPMENT_CATALOG."""
    s = await h.login_as("L1Looker", room_id=1)
    await _seed_items(h, s)

    out = await h.cmd(s, f"look {_ITEM_KEY}")
    assert _EXPECTED_DESC_FRAGMENT in out.lower(), (
        f"L1: 'look {_ITEM_KEY}' didn't show EQUIPMENT_CATALOG description.\n"
        f"  Expected fragment: {_EXPECTED_DESC_FRAGMENT!r}\n"
        f"  Output: {out[:400]!r}"
    )
    # Must NOT show the "not found" message
    assert "you don't see" not in out.lower(), (
        f"L1: 'look {_ITEM_KEY}' showed 'you don't see' — still falling "
        f"through: {out[:400]!r}"
    )


async def l2_look_name_partial(h):
    """L2 — look <partial name> surfaces item description."""
    s = await h.login_as("L2Looker", room_id=1)
    await _seed_items(h, s)

    # "Binder" is a unique partial match against "Binder Cuffs"
    out = await h.cmd(s, "look Binder")
    assert _EXPECTED_DESC_FRAGMENT in out.lower(), (
        f"L2: 'look Binder' didn't show description.\n"
        f"  Expected fragment: {_EXPECTED_DESC_FRAGMENT!r}\n"
        f"  Output: {out[:400]!r}"
    )
    assert "you don't see" not in out.lower(), (
        f"L2: 'look Binder' fell through to not-found: {out[:400]!r}"
    )


async def l3_look_nonexistent(h):
    """L3 — look <totally unknown arg> still says 'You don't see'."""
    s = await h.login_as("L3Looker", room_id=1)
    await _seed_items(h, s)

    out = await h.cmd(s, "look xyzzy_nonexistent_thing_zz9plural")
    assert "you don't see" in out.lower(), (
        f"L3: Missing 'you don't see' for nonexistent target.\n"
        f"  Output: {out[:400]!r}"
    )


async def l4_look_inline_description(h):
    """L4 — look <item with inline description> uses inline desc, not CATALOG."""
    s = await h.login_as("L4Looker", room_id=1)
    await _seed_items(h, s)

    # The slicing_kit has an inline description seeded in the inventory dict
    out = await h.cmd(s, f"look {_INLINE_KEY}")
    assert _INLINE_DESC.lower()[:20] in out.lower(), (
        f"L4: 'look {_INLINE_KEY}' didn't show inline description.\n"
        f"  Expected fragment: {_INLINE_DESC[:20]!r}\n"
        f"  Output: {out[:400]!r}"
    )
    assert "you don't see" not in out.lower(), (
        f"L4: 'look {_INLINE_KEY}' fell through: {out[:400]!r}"
    )


async def e1_examine_exact_key(h):
    """E1 — examine <exact key> surfaces item description."""
    s = await h.login_as("E1Examiner", room_id=1)
    await _seed_items(h, s)

    out = await h.cmd(s, f"examine {_ITEM_KEY}")
    assert _EXPECTED_DESC_FRAGMENT in out.lower(), (
        f"E1: 'examine {_ITEM_KEY}' didn't show description.\n"
        f"  Expected fragment: {_EXPECTED_DESC_FRAGMENT!r}\n"
        f"  Output: {out[:400]!r}"
    )
    assert "you see nothing special" not in out.lower(), (
        f"E1: 'examine {_ITEM_KEY}' fell through to generic: {out[:400]!r}"
    )


async def e2_examine_nonexistent(h):
    """E2 — examine <nonexistent arg> still says 'You see nothing special'."""
    s = await h.login_as("E2Examiner", room_id=1)
    await _seed_items(h, s)

    out = await h.cmd(s, "examine xyzzy_nonexistent_thing_zz9plural")
    assert "you see nothing special" in out.lower(), (
        f"E2: Missing 'you see nothing special' for nonexistent examine.\n"
        f"  Output: {out[:400]!r}"
    )


# ── pytest class ─────────────────────────────────────────────────────────

class TestLookExamineInventory:
    """look/examine on carried inventory items."""

    async def test_l1_look_exact_key(self, harness):
        await l1_look_exact_key(harness)

    async def test_l2_look_name_partial(self, harness):
        await l2_look_name_partial(harness)

    async def test_l3_look_nonexistent(self, harness):
        await l3_look_nonexistent(harness)

    async def test_l4_look_inline_description(self, harness):
        await l4_look_inline_description(harness)

    async def test_e1_examine_exact_key(self, harness):
        await e1_examine_exact_key(harness)

    async def test_e2_examine_nonexistent(self, harness):
        await e2_examine_nonexistent(harness)
