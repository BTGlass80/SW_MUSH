"""CRAFT.GUNDARK Drop F — espionage kit + the carried-tool seam
(2026-06-12).

3 schematics riding ONE new mechanic, per gundark plan §5/§8 Drop F:

  • **The seam:** §5's dominant pattern is skill-bonus gear (+1D
    security, +1D first aid, ...) and NO consumer existed — the same
    gap that deferred macrobinoculars, med-aid, and the gyro-grappler
    in earlier drops. `perform_skill_check` now scans carried items for
    `skill_bonus` dicts and applies the single BEST matching tool
    (never stacking), exactly the SRB.3 lead-bonus philosophy: live at
    the chokepoint so every out-of-combat caller benefits without
    knowing the mechanic exists. **Combat is structurally untouched** —
    engine/combat builds its pools directly and never calls the
    chokepoint (pinned).
  • **Roster:** Code Slicer (+1D security, Avail 3, Old-Republic-era
    lock-breaker), UniTech Patch (+1D+2 security, Avail 2), Medscanner
    (+1D first aid, Avail 2). Trainers: Renna Dox ×2 (the existing
    sensor_mask/comm_jammer slicer-tech) and Heist — zero new NPCs.
  • **Out, with reasons:** Force Detector (CRAFT.HOOK.force_detector —
    quest-artifact recast only, pinned never-a-recipe); qualifier-bound
    bonuses (DataSearch "info search", geological scanner "survey
    only") deferred rather than over-broadly granted; plasma cutter
    as-weapon (fixed 7D at 150 cr — economy-breaking book quirk);
    blaster sight (+1D blaster = a combat mod, wrong seam); sniffers/
    autoscan/camo-netting (search-vs-hide and stationary-scanner
    systems absent); Master Command Unit / Voice Box / Master Coder /
    Lock Breaker / Disruption Bubble (Avail 4/X band → Drop G).
"""
import json
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

NEW_KEYS = ["code_slicer", "unitech_patch", "medscanner"]


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


def _char_with(items, attrs=None):
    return {
        "id": 11,
        "inventory": json.dumps({"items": items, "resources": []}),
        "attributes": json.dumps(attrs or {}),
        "skills": "{}",
        "equipment": "{}",
    }


def _tool(key, name, skill, bonus):
    return {"type": "gear", "key": key, "name": name,
            "skill_bonus": {"skill": skill, "bonus": bonus}}


class TestToolSeam(unittest.TestCase):
    def test_best_single_tool_no_stacking(self):
        from engine.skill_checks import _best_tool_bonus
        char = _char_with([
            _tool("code_slicer", "Code Slicer", "security", "+1D"),
            _tool("unitech_patch", "UniTech Patch", "security", "+1D+2"),
        ])
        pips, name = _best_tool_bonus(char, "security")
        self.assertEqual((pips, name), (5, "UniTech Patch"))

    def test_dialect_canonicalization(self):
        # Schematic data writes underscore-form; the check canonicalizes.
        from engine.skill_checks import _best_tool_bonus
        char = _char_with([_tool("medscanner", "Medscanner",
                                 "first_aid", "+1D")])
        pips, name = _best_tool_bonus(char, "first aid")
        self.assertEqual(pips, 3)

    def test_non_matching_skill_unaffected(self):
        from engine.skill_checks import _best_tool_bonus
        char = _char_with([_tool("code_slicer", "Code Slicer",
                                 "security", "+1D")])
        self.assertEqual(_best_tool_bonus(char, "blaster"), (0, None))

    def test_malformed_items_fail_open(self):
        from engine.skill_checks import _best_tool_bonus
        char = _char_with([
            {"key": "junk", "skill_bonus": "not-a-dict"},
            {"key": "junk2", "skill_bonus": {"skill": "security",
                                             "bonus": "garbage"}},
            "legacy_string_item",
        ])
        self.assertEqual(_best_tool_bonus(char, "security"), (0, None))

    def test_full_check_applies_and_surfaces_tool(self):
        from engine.skill_checks import perform_skill_check
        char = _char_with(
            [_tool("code_slicer", "Code Slicer", "security", "+1D")],
            attrs={"technical": "3D"})
        r = perform_skill_check(char, "security", 1,
                                auto_consume_lead=False)
        # technical 3D (9 pips) + 1D tool (3) = 4D
        self.assertEqual(r.pool_str, "4D")
        self.assertEqual(r.tool_pips, 3)
        self.assertEqual(r.tool_name, "Code Slicer")

    def test_no_tool_fields_default(self):
        from engine.skill_checks import perform_skill_check
        char = _char_with([], attrs={"technical": "3D"})
        r = perform_skill_check(char, "security", 1,
                                auto_consume_lead=False)
        self.assertEqual(r.tool_pips, 0)
        self.assertIsNone(r.tool_name)

    def test_combat_never_calls_the_chokepoint(self):
        # The seam is out-of-combat BY CONSTRUCTION: a code slicer must
        # never buff a blaster roll. Pin the structural isolation.
        src = (REPO / "engine" / "combat.py").read_text(encoding="utf-8")
        self.assertNotIn("perform_skill_check", src)


class TestLandingPassthrough(unittest.TestCase):
    def test_gear_branch_copies_skill_bonus(self):
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        self.assertIn('gear_item["skill_bonus"]', code)
        self.assertIn('schematic.get("skill_bonus")', code)


class TestDropFSchematics(unittest.TestCase):
    EXPECTED = {
        # key: (avail, diff, q, trainer, bonus_skill, bonus, cost)
        "code_slicer": (3, 16, 55, "Renna Dox", "security", "+1D", 2000),
        "unitech_patch": (2, 14, 40, "Renna Dox", "security", "+1D+2", 5200),
        "medscanner": (2, 14, 40, "Heist", "first_aid", "+1D", 3000),
    }

    def test_rubric_and_bindings(self):
        sch = {s["key"]: s for s in _schematics()}
        avail_mod = {1: 0, 2: 2, 3: 4}
        for key, (avail, diff, q, trainer, bskill, bonus,
                  cost) in self.EXPECTED.items():
            s = sch[key]
            self.assertEqual(12 + avail_mod[avail], diff)
            self.assertEqual(s["difficulty"], diff, key)
            self.assertEqual(s["trainer_npc"], trainer, key)
            self.assertEqual(s["output_type"], "gear", key)
            self.assertEqual(s["base_cost"], cost, key)
            self.assertEqual(s["skill_bonus"]["skill"], bskill, key)
            self.assertEqual(s["skill_bonus"]["bonus"], bonus, key)
            self.assertEqual(s["skill_required"], "computer_prog", key)
            for c in s["components"]:
                self.assertEqual(c["min_quality"], q, key)

    def test_spy_gear_mix_electronic_primary(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            comps = {c["type"]: c["quantity"] for c in sch[key]["components"]}
            self.assertEqual(max(comps, key=comps.get), "electronic", key)
            self.assertTrue(set(comps) <= {"electronic", "energy", "rare"},
                            key)

    def test_trainers_are_seeded(self):
        # Both bind to ALREADY-SEEDED NPCs — the Vek Nurren lesson.
        p2 = (REPO / "data" / "worlds" / "clone_wars" /
              "npcs_mos_eisley_population_p2.yaml").read_text(
            encoding="utf-8")
        self.assertIn("name: Heist", p2)
        found_renna = False
        for f in (REPO / "data" / "worlds" / "clone_wars").glob("npcs_*.yaml"):
            if "Renna Dox" in f.read_text(encoding="utf-8"):
                found_renna = True
                break
        self.assertTrue(found_renna, "Renna Dox must be seeded somewhere")

    def test_grant_on_talk(self):
        from engine.crafting import add_known_schematic, get_all_schematics
        for trainer, want in (("renna dox",
                               {"sensor_mask", "comm_jammer",
                                "code_slicer", "unitech_patch"}),
                              ("heist", {"medscanner"})):
            char = {"attributes": json.dumps({})}
            granted = set()
            for key, schem in get_all_schematics().items():
                if schem.get("trainer_npc", "").lower() == trainer:
                    if add_known_schematic(char, key):
                        granted.add(key)
            # Superset: Heist already teaches the medpac/stim family;
            # the drop ADDS to a trainer's list, never owns it.
            self.assertTrue(want <= granted,
                            f"{trainer}: missing {want - granted}")

    def test_force_detector_stays_out(self):
        # CRAFT.HOOK.force_detector: never a recipe, never a row. Check
        # PARSED data, not raw text — the file's own comments rightly
        # mention the exclusion.
        for s in _schematics():
            blob = (s["key"] + " " + s.get("name", "")).lower()
            self.assertNotIn("force", blob.replace("force_pike", ""),
                             s["key"])
        wr_data = yaml.safe_load(
            (REPO / "data" / "weapons.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("force_detector", wr_data)


if __name__ == "__main__":
    unittest.main()
