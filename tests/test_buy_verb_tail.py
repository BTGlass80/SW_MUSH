"""Drop 13 — Buy-verb tail: tracking_fob search seam + ground ledger tag
(2026-06-12).

Tests for two independent changes:

  1. tracking_fob now carries ``skill_bonus`` on both landing paths
     (EQUIPMENT_CATALOG via issue_equipment; COMMISSARY_STOCK via
     purchase_commissary) so the item actually grants +1D Search through
     ``perform_skill_check``.  Both source catalogs must agree on the field.

  2. ``ship_weapon_purchase`` ledger tag renamed to ``ground_weapon_purchase``
     at parser/space_commands.py — the buy-verb path only sells
     character-scale ground commons after market segmentation (drop 10).
"""
import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SW_ERA", "clone_wars")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _char_with(items, attrs=None):
    return {
        "id": 42,
        "inventory": json.dumps({"items": items, "resources": []}),
        "attributes": json.dumps(attrs or {}),
        "skills": "{}",
        "equipment": "{}",
    }


def _fob_item():
    return {
        "key": "tracking_fob",
        "name": "Tracking Fob",
        "slot": "misc",
        "skill_bonus": {"skill": "search", "bonus": "+1D"},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Catalog data pins
# ─────────────────────────────────────────────────────────────────────────────
class TestCatalogData(unittest.TestCase):
    def test_equipment_catalog_has_skill_bonus(self):
        from engine.organizations import EQUIPMENT_CATALOG
        fob = EQUIPMENT_CATALOG["tracking_fob"]
        self.assertEqual(fob.get("skill_bonus"),
                         {"skill": "search", "bonus": "+1D"})

    def test_commissary_stock_has_skill_bonus(self):
        from engine.commissary import COMMISSARY_STOCK
        items = COMMISSARY_STOCK["bounty_hunters_guild"]
        fob = next((it for it in items if it["key"] == "tracking_fob"), None)
        self.assertIsNotNone(fob, "tracking_fob not in BH commissary stock")
        self.assertEqual(fob.get("skill_bonus"),
                         {"skill": "search", "bonus": "+1D"})

    def test_catalogs_agree_on_skill_bonus(self):
        """Both source catalogs must carry identical skill_bonus for the fob."""
        from engine.organizations import EQUIPMENT_CATALOG
        from engine.commissary import COMMISSARY_STOCK
        cat_sb = EQUIPMENT_CATALOG["tracking_fob"].get("skill_bonus")
        stock_items = COMMISSARY_STOCK["bounty_hunters_guild"]
        fob = next((it for it in stock_items if it["key"] == "tracking_fob"),
                   None)
        self.assertIsNotNone(fob)
        self.assertEqual(cat_sb, fob.get("skill_bonus"),
                         "EQUIPMENT_CATALOG and COMMISSARY_STOCK tracking_fob "
                         "skill_bonus must be identical")


# ─────────────────────────────────────────────────────────────────────────────
# 2. End-to-end seam: tracking_fob grants +1D to Search only
# ─────────────────────────────────────────────────────────────────────────────
class TestTrackingFobSeam(unittest.TestCase):
    def test_fob_grants_plus_1d_to_search(self):
        from engine.skill_checks import perform_skill_check
        # perception 3D (9 pips) + 1D tool (3) = 4D
        char = _char_with([_fob_item()], attrs={"perception": "3D"})
        r = perform_skill_check(char, "search", 1, auto_consume_lead=False)
        self.assertEqual(r.tool_pips, 3)
        self.assertEqual(r.tool_name, "Tracking Fob")

    def test_fob_does_not_buff_non_search_skill(self):
        from engine.skill_checks import perform_skill_check
        char = _char_with([_fob_item()], attrs={"dexterity": "3D"})
        r = perform_skill_check(char, "blaster", 1, auto_consume_lead=False)
        self.assertEqual(r.tool_pips, 0)
        self.assertIsNone(r.tool_name)

    def test_fob_does_not_buff_brawling(self):
        from engine.skill_checks import perform_skill_check
        char = _char_with([_fob_item()], attrs={"strength": "3D"})
        r = perform_skill_check(char, "brawling", 1, auto_consume_lead=False)
        self.assertEqual(r.tool_pips, 0)
        self.assertIsNone(r.tool_name)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Structural source pins: passthrough is wired in both functions
# ─────────────────────────────────────────────────────────────────────────────
class TestPassthroughStructural(unittest.TestCase):
    def _code(self, filepath):
        src = (REPO / filepath).read_text(encoding="utf-8")
        # Strip comment lines so we pin executable code, not documentation
        return "\n".join(
            ln for ln in src.splitlines()
            if not ln.lstrip().startswith("#")
        )

    def test_issue_equipment_passes_skill_bonus(self):
        code = self._code("engine/organizations.py")
        self.assertIn('inv_item["skill_bonus"]', code,
                      "issue_equipment must assign skill_bonus to inv_item")
        self.assertIn('catalog_entry.get("skill_bonus")', code,
                      "issue_equipment must read skill_bonus from catalog_entry")

    def test_purchase_commissary_passes_skill_bonus(self):
        code = self._code("engine/commissary.py")
        self.assertIn('inv_item["skill_bonus"]', code,
                      "purchase_commissary must assign skill_bonus to inv_item")
        self.assertIn('item.get("skill_bonus")', code,
                      "purchase_commissary must read skill_bonus from stock item")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ledger tag rename pin
# ─────────────────────────────────────────────────────────────────────────────
class TestLedgerTagRename(unittest.TestCase):
    def _space_commands_src(self):
        return (REPO / "parser" / "space_commands.py").read_text(
            encoding="utf-8")

    def test_new_tag_present(self):
        self.assertIn('"ground_weapon_purchase"', self._space_commands_src(),
                      "BuyCommand must use ground_weapon_purchase tag")

    def test_old_tag_absent(self):
        src = self._space_commands_src()
        # Allow the old tag inside comments only (the rename comment references
        # it), but not as a string literal in executable code.
        import re
        # Find occurrences that are NOT inside comment lines
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            self.assertNotIn('"ship_weapon_purchase"', line,
                             "No non-comment line should contain "
                             "'ship_weapon_purchase' string literal")


if __name__ == "__main__":
    unittest.main()
