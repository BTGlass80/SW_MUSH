"""Tests for the CW Mos Eisley population recovery — Phase 1.

Verifies the era-portable GG7 Mos Eisley locals were ported into the Clone
Wars world (the GG7 roster itself never loads in CW), with correct rooms,
a functional Venn-Kator crafting trainer, era-clean re-skinned text, no
collisions with the existing CW replacements roster, and live resolution
(every NPC lands in its intended room, not the Market Row fallback).
"""

import os
import unittest
from pathlib import Path

import yaml


# ── locate the repo root (walk up until we find data/worlds/clone_wars) ──
def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "data" / "worlds" / "clone_wars" / "era.yaml").exists():
            return parent
    raise RuntimeError("could not locate repo root from test file")


ROOT = _find_root()
POP_FILE = ROOT / "data/worlds/clone_wars/npcs_mos_eisley_population_p1.yaml"
REPLACEMENTS_FILE = ROOT / "data/worlds/clone_wars/npcs_cw_replacements.yaml"
ERA_FILE = ROOT / "data/worlds/clone_wars/era.yaml"

# Tokens that must never appear in CW-era NPC *content* (the Empire and the
# Rebellion do not exist at ~20 BBY). Multi-char/distinctive to avoid naive
# substring false positives. Checked against parsed field values only — the
# file HEADER documents the GCW source, so a raw-text scan would (correctly)
# trip on the documentation; the live strings the player sees must be clean.
ERA_BANNED = (
    "imperial", "empire", "stormtrooper", "rebel", "rebellion",
    "x-wing", "tie fighter", "star destroyer", "moff", "galactic empire",
)

EXPECTED_ROOMS = {
    "Wuher": "Chalmun's Cantina - Main Bar",
    "Chalmun": "Chalmun's Cantina - Main Bar",
    "Muftak": "Chalmun's Cantina - Main Bar",
    "Kabe": "Chalmun's Cantina - Main Bar",
    "Djas Puhr": "Chalmun's Cantina - Main Bar",
    "Hem Dazon": "Chalmun's Cantina - Main Bar",
    "M'iiyoom Onith": "Chalmun's Cantina - Main Bar",
    "Bom Vimdin": "Chalmun's Cantina - Main Bar",
    "Figrin D'an": "Chalmun's Cantina - Back Hallway",
    "Cantina Bouncer": "Chalmun's Cantina - Entrance",
    "Venn Kator": "Docking Bay 94 - Pit Floor",
    "Kayson": "Kayson's Weapon Shop",
}


def _load_npcs():
    with open(POP_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)["npcs"]


def _collect_strings(obj):
    """Recursively gather all string values from an NPC dict (descriptions,
    personality, dialogue, knowledge, fallback_lines, directed_responses)."""
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_collect_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_collect_strings(v))
    return out


class TestFileLoadsAndRoster(unittest.TestCase):
    def test_file_parses(self):
        npcs = _load_npcs()
        self.assertGreaterEqual(len(npcs), 12)

    def test_all_expected_npcs_present_with_rooms(self):
        by = {n["name"]: n for n in _load_npcs()}
        for name, room in EXPECTED_ROOMS.items():
            with self.subTest(npc=name):
                self.assertIn(name, by, f"{name} must be seeded")
                self.assertEqual(by[name]["room"], room)

    def test_every_npc_has_char_sheet_and_ai(self):
        for n in _load_npcs():
            with self.subTest(npc=n.get("name")):
                self.assertIn("char_sheet", n)
                self.assertIn("attributes", n["char_sheet"],
                              "char_sheet must use the nested lowercase "
                              "attributes form the loader actually reads")
                self.assertIn("ai_config", n)
                self.assertTrue(n["ai_config"].get("fallback_lines"),
                                "scripted fallback_lines required")


class TestEraCleanliness(unittest.TestCase):
    """Re-skinned content must contain no Empire/Rebellion references."""

    def test_no_banned_tokens_in_content(self):
        for n in _load_npcs():
            blob = " ".join(_collect_strings(n)).lower()
            for tok in ERA_BANNED:
                with self.subTest(npc=n.get("name"), token=tok):
                    self.assertNotIn(
                        tok, blob,
                        f"{n.get('name')} content contains era-broken "
                        f"token {tok!r}")


class TestVennIsFunctionalTrainer(unittest.TestCase):
    """schematics.yaml has `trainer_npc: Venn Kator` recipes; he must be a
    real trainer with a non-empty train_skills list (the GG7 entry set
    trainer:true but listed no skills, so it taught nothing)."""

    def _venn(self):
        return next(n for n in _load_npcs() if n["name"] == "Venn Kator")

    def test_venn_trainer_flag_and_skills(self):
        ai = self._venn()["ai_config"]
        self.assertTrue(ai.get("trainer"))
        skills = set(ai.get("train_skills") or [])
        self.assertTrue(
            {"starship_repair", "space_transports_repair"} <= skills,
            f"Venn must teach the ship-repair skills, got {skills}")

    def test_venn_schematics_skill_is_teachable(self):
        """data/schematics.yaml ship-component recipes require
        space_transports_repair — Venn must teach exactly that."""
        ai = self._venn()["ai_config"]
        self.assertIn("space_transports_repair", ai.get("train_skills") or [])


class TestNoCollisionWithReplacements(unittest.TestCase):
    """Phase-1 names must not duplicate the npcs_cw_replacements roster
    (clones, liaisons, Renn Sallow, Het Nkik)."""

    def test_no_duplicate_names(self):
        if not REPLACEMENTS_FILE.exists():
            self.skipTest("npcs_cw_replacements.yaml not present")
        with open(REPLACEMENTS_FILE, encoding="utf-8") as f:
            repl = {n["name"] for n in yaml.safe_load(f)["npcs"]}
        mine = {n["name"] for n in _load_npcs()}
        overlap = repl & mine
        self.assertEqual(overlap, set(),
                         f"name collision with replacements roster: {overlap}")


class TestRegisteredInEraManifest(unittest.TestCase):
    def test_file_in_npcs_list(self):
        raw = ERA_FILE.read_text(encoding="utf-8")
        # the list-item value (before any inline comment) must be the file
        found = False
        for line in raw.splitlines():
            s = line.strip()
            if not s.startswith("- "):
                continue
            item = s[2:].split("#", 1)[0].strip().strip('"\'')
            if item == "npcs_mos_eisley_population_p1.yaml":
                found = True
                break
        self.assertTrue(found, "population file must be registered in era.yaml")


class TestCWWorldLoadResolvesMosEisleyPopulation(unittest.TestCase):
    """Integration pin: load the real Clone Wars world and confirm every
    Phase-1 NPC resolves to its intended room (NOT the Market Row fallback),
    and that Chalmun's Cantina Main Bar is now actually populated.

    Skips if the dry-run loaders aren't importable (Windows is ground truth)."""

    FALLBACK_IDX = 8  # Market Row

    @classmethod
    def setUpClass(cls):
        try:
            from engine.world_loader import load_world_dry_run
            from engine.npc_loader import load_era_npcs
        except Exception as exc:  # pragma: no cover - env-dependent
            raise unittest.SkipTest(f"CW dry-run loaders unavailable: {exc}")
        bundle = load_world_dry_run("clone_wars")
        cls.room_map = {r.name: r.id for r in bundle.rooms.values()}
        cls.idx2name = {v: k for k, v in cls.room_map.items()}
        era_dir = os.path.join(str(ROOT), "data", "worlds", "clone_wars")
        planet, _ = load_era_npcs(era_dir, cls.room_map)
        cls.by_name = {t[0]: t for t in planet}
        cls.planet = planet

    def test_all_phase1_npcs_resolve(self):
        for name, want_room in EXPECTED_ROOMS.items():
            with self.subTest(npc=name):
                self.assertIn(name, self.by_name,
                              f"{name} must load in CW")
                idx = self.by_name[name][1]
                self.assertNotEqual(
                    idx, self.FALLBACK_IDX,
                    f"{name} fell back to Market Row (room mismatch)")
                self.assertEqual(self.idx2name.get(idx), want_room)

    def test_cantina_main_bar_now_populated(self):
        """Was 1 NPC (Renn Sallow) before this drop; Phase 1 adds 8 Main Bar
        denizens, so it should now hold several."""
        bar_idx = self.room_map.get("Chalmun's Cantina - Main Bar")
        self.assertIsNotNone(bar_idx)
        n_in_bar = sum(1 for t in self.planet if t[1] == bar_idx)
        self.assertGreaterEqual(
            n_in_bar, 8,
            f"cantina main bar should be populated, has {n_in_bar}")

    def test_venn_trainer_flag_survives_load(self):
        venn = self.by_name.get("Venn Kator")
        self.assertIsNotNone(venn)
        ai = venn[5]  # ai_config dict
        self.assertTrue(ai.get("trainer"))
        self.assertIn("space_transports_repair", ai.get("train_skills") or [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
