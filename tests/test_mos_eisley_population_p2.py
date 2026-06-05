"""Tests for the CW Mos Eisley population recovery — Phase 2 (utility tier).

Verifies the 6 era-portable GG7 service-anchor NPCs (medic, banker, general
store, speeder dealer, bay operator, food vendor) were ported into the Clone
Wars world with correct rooms, era-clean re-skinned text (notably Lup, who is
no longer Rebel-aligned), no collisions with Phase 1 or the replacements
roster, and live resolution to their intended rooms.
"""

import os
import unittest
from pathlib import Path

import yaml


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "data" / "worlds" / "clone_wars" / "era.yaml").exists():
            return parent
    raise RuntimeError("could not locate repo root from test file")


ROOT = _find_root()
P2_FILE = ROOT / "data/worlds/clone_wars/npcs_mos_eisley_population_p2.yaml"
P1_FILE = ROOT / "data/worlds/clone_wars/npcs_mos_eisley_population_p1.yaml"
REPLACEMENTS_FILE = ROOT / "data/worlds/clone_wars/npcs_cw_replacements.yaml"
ERA_FILE = ROOT / "data/worlds/clone_wars/era.yaml"

ERA_BANNED = (
    "imperial", "empire", "stormtrooper", "rebel", "rebellion",
    "x-wing", "tie fighter", "star destroyer", "moff", "galactic empire",
)

EXPECTED_ROOMS = {
    "Heist": "The Cutting Edge Clinic",
    "Zygian Teller": "Zygian's Banking Concern",
    "Lup": "Lup's General Store",
    "Geordi Hans": "Spaceport Speeders",
    "De Maal": "Docking Bay 94 - Entrance",
    "Gep": "Market Place - Gep's Grill",
}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["npcs"]


def _collect_strings(obj):
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
        self.assertGreaterEqual(len(_load(P2_FILE)), 6)

    def test_all_expected_npcs_present_with_rooms(self):
        by = {n["name"]: n for n in _load(P2_FILE)}
        for name, room in EXPECTED_ROOMS.items():
            with self.subTest(npc=name):
                self.assertIn(name, by)
                self.assertEqual(by[name]["room"], room)

    def test_every_npc_has_nested_char_sheet_and_ai(self):
        for n in _load(P2_FILE):
            with self.subTest(npc=n.get("name")):
                self.assertIn("attributes", n.get("char_sheet", {}),
                              "char_sheet must use nested lowercase attributes")
                self.assertTrue(n.get("ai_config", {}).get("fallback_lines"))


class TestEraCleanliness(unittest.TestCase):
    def test_no_banned_tokens_in_content(self):
        for n in _load(P2_FILE):
            blob = " ".join(_collect_strings(n)).lower()
            for tok in ERA_BANNED:
                with self.subTest(npc=n.get("name"), token=tok):
                    self.assertNotIn(tok, blob)


class TestReskins(unittest.TestCase):
    """Lup was GG7 'Rebel Alliance' and must be re-skinned to a neutral
    Ithorian merchant — the Rebellion does not exist at ~20 BBY."""

    def test_lup_not_rebel_aligned(self):
        lup = next(n for n in _load(P2_FILE) if n["name"] == "Lup")
        self.assertNotIn(lup["ai_config"].get("faction", "").lower(),
                         ("rebel alliance", "rebel"))
        self.assertEqual(lup["ai_config"].get("faction"), "independent")


class TestNoCollisions(unittest.TestCase):
    """Phase-2 names must not duplicate Phase 1 or the replacements roster."""

    def test_no_duplicate_names(self):
        mine = {n["name"] for n in _load(P2_FILE)}
        p1 = {n["name"] for n in _load(P1_FILE)}
        self.assertEqual(mine & p1, set(), f"collision with Phase 1: {mine & p1}")
        if REPLACEMENTS_FILE.exists():
            repl = {n["name"] for n in _load(REPLACEMENTS_FILE)}
            self.assertEqual(mine & repl, set(),
                             f"collision with replacements: {mine & repl}")


class TestRegisteredInEraManifest(unittest.TestCase):
    def test_file_in_npcs_list(self):
        for line in ERA_FILE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("- ") and s[2:].split("#", 1)[0].strip().strip('"\'') \
                    == "npcs_mos_eisley_population_p2.yaml":
                return
        self.fail("Phase-2 file must be registered in era.yaml")


class TestCWWorldLoadResolvesUtilityTier(unittest.TestCase):
    """Integration pin: every Phase-2 NPC resolves to its intended room
    (not the Market Row fallback). Skips if loaders aren't importable."""

    FALLBACK_IDX = 8

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
        planet, _ = load_era_npcs(
            os.path.join(str(ROOT), "data", "worlds", "clone_wars"), cls.room_map)
        cls.by_name = {t[0]: t for t in planet}

    def test_all_utility_npcs_resolve(self):
        for name, want_room in EXPECTED_ROOMS.items():
            with self.subTest(npc=name):
                self.assertIn(name, self.by_name, f"{name} must load in CW")
                idx = self.by_name[name][1]
                self.assertNotEqual(idx, self.FALLBACK_IDX,
                                    f"{name} fell back to Market Row")
                self.assertEqual(self.idx2name.get(idx), want_room)

    def test_de_maal_at_bay_entrance_distinct_from_pit_floor(self):
        """De Maal is at the Bay 94 Entrance; Mak/Venn are on the Pit Floor —
        confirm they're different rooms (a coherent multi-room bay)."""
        de_maal_room = self.idx2name.get(self.by_name["De Maal"][1])
        self.assertEqual(de_maal_room, "Docking Bay 94 - Entrance")
        if "Venn Kator" in self.by_name:
            venn_room = self.idx2name.get(self.by_name["Venn Kator"][1])
            self.assertNotEqual(de_maal_room, venn_room)


if __name__ == "__main__":
    unittest.main(verbosity=2)
