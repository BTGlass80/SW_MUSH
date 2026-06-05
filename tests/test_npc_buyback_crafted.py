"""Economy audit v2 §1.3 — NPC vendors stop price-supporting crafted goods.

A player could craft a Tier-1 item from ~55 cr (or free, surveyed) materials
and sell it to an NPC for ~200 cr — a >250 cr/craft credit engine that needs
no buyer, and which set the floor price for the whole crafted-goods market so
player vendor droids never had to discover their own. The fix (the audit's
preferred "indirect" option): NPCs refuse well-made player crafts, pushing
them to the player vendor market; low-quality crafts and factory items still
sell as salvage.

Tests the policy helper, its tunable threshold, and that the sell command is
actually gated by it.
"""

import unittest
from pathlib import Path

from engine.items import (
    ItemInstance, npc_refuses_buyback, CRAFTED_NPC_BUYBACK_MAX_QUALITY,
)


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "parser" / "builtin_commands.py").exists():
            return parent
    raise RuntimeError("could not locate repo root")


ROOT = _find_root()


class TestNpcRefusesBuyback(unittest.TestCase):
    def test_high_quality_craft_is_refused(self):
        self.assertTrue(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", 50, "Venn")))
        self.assertTrue(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", 80, "Venn")))
        self.assertTrue(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", 100, "Venn")))

    def test_low_quality_craft_still_sells_as_salvage(self):
        self.assertFalse(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", 49, "Venn")))
        self.assertFalse(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", 0, "Venn")))

    def test_factory_item_unaffected(self):
        # Vendor/factory items (no crafter) are quality 50 but must still be
        # resellable to NPCs — they're not the exploit.
        self.assertFalse(npc_refuses_buyback(
            ItemInstance.new_from_vendor("blaster_pistol")))

    def test_boundary_is_at_threshold(self):
        q = CRAFTED_NPC_BUYBACK_MAX_QUALITY
        self.assertTrue(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", q, "Venn")))
        self.assertFalse(npc_refuses_buyback(
            ItemInstance.new_crafted("blaster_pistol", q - 1, "Venn")))

    def test_threshold_is_canonical_50(self):
        # Tunable; pinned so a change is a deliberate decision.
        self.assertEqual(CRAFTED_NPC_BUYBACK_MAX_QUALITY, 50)


class TestSellCommandGated(unittest.TestCase):
    def test_sell_command_calls_the_gate(self):
        src = (ROOT / "parser" / "builtin_commands.py").read_text(encoding="utf-8")
        self.assertIn("npc_refuses_buyback", src,
                      "sell command must consult the §1.3 buyback gate")
        # the gate must short-circuit (return) before the credit write
        gate = src.index("npc_refuses_buyback(item)")
        adjust = src.index('adjust_credits(\n            char["id"], sale_price')
        self.assertLess(gate, adjust,
                        "the refusal gate must precede the item_sale credit write")


if __name__ == "__main__":
    unittest.main(verbosity=2)
