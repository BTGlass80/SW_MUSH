"""Regression tests — equipment-instance untangle stragglers (2026-06-10).

The 2026-06 equipment untangle made per-slot ItemInstance JSON canonical and
migrated readers/writers to read_equipment / equipment_keys / write_equipment.
The 2026-06-10 full-suite run on the Windows box exposed one crash and an
audit then found a band of un-migrated sites that all silently misbehaved
under canonical storage:

  * engine/sheet_renderer.render_game_sheet — NameError ('equip_data') when
    rendering the worn-armor line (crashed `+sheet`; 5 smoke failures).
  * combat _resolve_equipped_weapon — read legacy shape-2 "key"; attack
    ignored the equipped weapon.
  * combat _apply_combat_wear — parse_equipment_json → None (wear never
    applied); serialize_equipment write clobbered armor.
  * builtin look ×2, +weapons footer, +armor footer — raw slot reads got an
    instance dict where they expected a key string.
  * builtin sell-equipped — always "Nothing equipped"; sale wiped armor.
  * crafting experiment prep — always "no weapon equipped"; every fumble
    outcome wiped armor.
  * shop _find_in_inventory — equipped weapon could never be stocked.
  * vendor_droids.stock_droid — equipment="{}" wiped armor.
  * force _apply_disarm — residual shape-2 weapon survived the disarm.

These tests pin the canonical-shape behavior at the engine layer (sandbox-
runnable: no aiohttp/aiosqlite imports) and source-pin the parser sites.
"""
import json
import re
import unittest
from pathlib import Path

from engine.items import (
    ItemInstance,
    equipment_keys,
    read_equipment,
    write_equipment,
)

REPO = Path(__file__).resolve().parent.parent


def _canonical_both_slots() -> str:
    """Canonical per-slot column with BOTH slots populated."""
    return write_equipment(
        weapon=ItemInstance(key="blaster_pistol", condition=80, quality=62),
        armor=ItemInstance(key="blast_vest", condition=95, quality=55),
    )


class TestSheetRendererCanonicalEquipment(unittest.TestCase):
    """render_game_sheet must render (not NameError) with canonical
    equipment carrying both slots — the exact crash from the suite run."""

    def _char_dict(self, equipment_raw):
        return {
            "name": "Straggler",
            "species": "Human",
            "credits": 100,
            "wound_level": 0,
            "equipment": equipment_raw,
            "attributes": json.dumps({
                "dexterity": "3D", "knowledge": "2D", "mechanical": "2D",
                "perception": "3D", "strength": "3D", "technical": "2D",
                "skills": {"blaster": "4D"},
            }),
        }

    def test_renders_with_both_slots_canonical(self):
        from engine.sheet_renderer import render_game_sheet
        from engine.character import get_cached_skill_registry
        char = self._char_dict(_canonical_both_slots())
        lines = render_game_sheet(char, get_cached_skill_registry())
        joined = "\n".join(lines)
        self.assertIn("Weapon:", joined)
        self.assertIn("Armor:", joined)

    def test_renders_with_empty_and_legacy_shapes(self):
        from engine.sheet_renderer import render_game_sheet
        from engine.character import get_cached_skill_registry
        reg = get_cached_skill_registry()
        for raw in (
            "{}",
            "",
            json.dumps({"weapon": "blaster_pistol"}),            # shape 1
            json.dumps({"key": "blaster_pistol", "condition": 50}),  # shape 2
        ):
            lines = render_game_sheet(self._char_dict(raw), reg)
            self.assertTrue(lines, f"no output for shape {raw!r}")

    def test_no_equip_data_name_remains(self):
        src = (REPO / "engine" / "sheet_renderer.py").read_text(
            encoding="utf-8")
        self.assertNotIn("equip_data", src)


class TestCanonicalHelpersRoundTrip(unittest.TestCase):
    """The slot-preserving idiom every migrated site now uses."""

    def test_weapon_clear_preserves_armor(self):
        raw = _canonical_both_slots()
        armor = read_equipment(raw)["armor"]
        cleared = write_equipment(weapon=None, armor=armor)
        slots = read_equipment(cleared)
        self.assertIsNone(slots["weapon"])
        self.assertIsNotNone(slots["armor"])
        self.assertEqual(slots["armor"].key, "blast_vest")
        self.assertEqual(slots["armor"].condition, 95)

    def test_weapon_update_preserves_armor(self):
        raw = _canonical_both_slots()
        slots = read_equipment(raw)
        slots["weapon"].apply_wear(2)
        out = write_equipment(weapon=slots["weapon"], armor=slots["armor"])
        back = read_equipment(out)
        self.assertEqual(back["weapon"].condition, 78)
        self.assertEqual(back["armor"].key, "blast_vest")

    def test_equipment_keys_on_all_shapes(self):
        cases = {
            _canonical_both_slots(): ("blaster_pistol", "blast_vest"),
            json.dumps({"weapon": "vibroblade"}): ("vibroblade", ""),
            json.dumps({"key": "vibroblade"}): ("vibroblade", ""),
            "{}": ("", ""),
        }
        for raw, (wk, ak) in cases.items():
            keys = equipment_keys(raw)
            self.assertEqual(keys["weapon"], wk, raw)
            self.assertEqual(keys["armor"], ak, raw)


class TestParserSitesMigrated(unittest.TestCase):
    """Source pinning: no live parser/engine call sites on the legacy
    helpers or raw slot reads remain. (Parser modules import the server
    stack, which the sandbox lacks; ground-truth behavior runs on the
    Windows suite. Source pinning is the sandbox-side guard.)"""

    LIVE_DIRS = ("engine", "parser", "server", "ai")

    def _grep(self, pattern):
        hits = []
        rx = re.compile(pattern)
        for d in self.LIVE_DIRS:
            base = REPO / d
            if not base.exists():
                continue
            for f in base.rglob("*.py"):
                for i, line in enumerate(
                        f.read_text(encoding="utf-8").splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if rx.search(line):
                        hits.append(f"{f.relative_to(REPO)}:{i}: {stripped}")
        return hits

    def test_no_live_parse_equipment_json_callers(self):
        hits = [h for h in self._grep(r"parse_equipment_json")
                if "def parse_equipment_json" not in h
                and "items.py" not in h]
        self.assertEqual(hits, [], "\n".join(hits))

    def test_no_live_serialize_equipment_callers(self):
        hits = [h for h in self._grep(r"serialize_equipment\(")
                if "def serialize_equipment" not in h
                and "items.py" not in h]
        self.assertEqual(hits, [], "\n".join(hits))

    def test_no_bare_equipment_wipe_writes(self):
        # equipment="{}" as a save kwarg wipes both slots; every clear must
        # go through write_equipment(weapon=None, armor=...).
        hits = self._grep(r"equipment\s*=\s*[\"']\{\}[\"']")
        # char["equipment"] = "{}" initializers for brand-new characters
        # (chargen) are legitimate; only flag known live-character paths.
        hits = [h for h in hits
                if "character.py" not in h and "chargen" not in h]
        self.assertEqual(hits, [], "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
