"""CRAFT.P0 — crafting remediation drop tests (2026-06-10).

Covers the re-delivered T2.DEF.t5_discoverability fixes (the phantom drop)
plus the new P0 findings, at the engine layer where the sandbox can run
them, with source pins for the parser sites (parser modules import the
server stack; Windows full suite is the behavioral gate there).

Findings under test (crafting_integration_design_pass_v1.md §1.2):
  F1.A  check_resources quantity-vs-quality diagnostics
  F1.C  craft rolls skill_required (source pin)
  F1.D  resolve_craft receives a result object (source pin)
  F1.B1 schematics listing reads components (source pin)
  F1.B2 resources listing reads quantity (source pin)
  F2-F4 all craft landings via db.add_to_inventory (source pin)
  F3    equipment branch exists + no schematic output_type is unhandled
  F5    hazard mitigation reads dict-format inventory + equipment slots
  F6    'electronic' is a declared, harvestable, surveyable type
  F7    stun_pistol / blaster_carbine resolve in the weapon registry
  P0.9  carried-gear helpers round-trip instances
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────────
# F1.A — check_resources diagnostics
# ──────────────────────────────────────────────────────────────────────

class TestCheckResourcesDiagnostics(unittest.TestCase):
    def _char(self, resources):
        return {"inventory": json.dumps({"items": [], "resources": resources})}

    def test_quantity_blocked_names_shortfall(self):
        from engine.crafting import check_resources
        ok, msg = check_resources(
            self._char([{"type": "metal", "quantity": 1, "quality": 80}]),
            [{"type": "metal", "quantity": 3, "min_quality": 40}])
        self.assertFalse(ok)
        self.assertIn("need 3x metal", msg)
        self.assertIn("you have 1x", msg)

    def test_quantity_blocked_none_held(self):
        from engine.crafting import check_resources
        ok, msg = check_resources(
            self._char([]),
            [{"type": "chemical", "quantity": 2, "min_quality": 25}])
        self.assertFalse(ok)
        self.assertIn("you have none", msg)

    def test_quality_blocked_names_best_grade(self):
        from engine.crafting import check_resources
        ok, msg = check_resources(
            self._char([{"type": "kyber_shard_minor", "quantity": 5,
                         "quality": 72.0}]),
            [{"type": "kyber_shard_minor", "quantity": 1, "min_quality": 75}])
        self.assertFalse(ok)
        self.assertIn("have 5x", msg)
        self.assertIn("q75+", msg)
        self.assertIn("best grade q72", msg)
        self.assertIn("kyber_shard_minor", msg)   # type still named (syn6c compat)

    def test_satisfied_passes(self):
        from engine.crafting import check_resources
        ok, msg = check_resources(
            self._char([{"type": "metal", "quantity": 3, "quality": 60}]),
            [{"type": "metal", "quantity": 3, "min_quality": 40}])
        self.assertTrue(ok, msg)


# ──────────────────────────────────────────────────────────────────────
# F6 — electronic resource type
# ──────────────────────────────────────────────────────────────────────

class TestElectronicResourceType(unittest.TestCase):
    def test_declared_and_harvestable(self):
        from engine.crafting import RESOURCE_TYPES, HARVESTABLE_RESOURCE_TYPES
        self.assertIn("electronic", RESOURCE_TYPES)
        self.assertIn("electronic", HARVESTABLE_RESOURCE_TYPES)

    def test_add_resource_accepts_electronic(self):
        from engine.crafting import add_resource, _get_resource_list
        char = {"inventory": json.dumps({"items": [], "resources": []})}
        msg = add_resource(char, "electronic", 3, 50.0)
        self.assertNotIn("Unknown resource type", msg)
        stacks = _get_resource_list(char)
        self.assertTrue(any(s["type"] == "electronic" for s in stacks))

    def test_city_survey_yields_electronic(self):
        from engine.crafting import get_survey_resources
        types = {r["type"] for r in get_survey_resources("Cantina Backroom", 50.0)}
        self.assertIn("electronic", types)

    def test_every_schematic_component_type_is_declared(self):
        # The original F6 failure mode: a recipe consuming an undeclared
        # type is permanently uncraftable. Pin the whole catalog.
        import yaml
        from engine.crafting import RESOURCE_TYPES
        sch = yaml.safe_load(
            (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
        )["schematics"]
        undeclared = sorted({
            c["type"] for s in sch for c in s.get("components", [])
        } - RESOURCE_TYPES)
        self.assertEqual(undeclared, [],
                         f"schematic components use undeclared types: {undeclared}")


# ──────────────────────────────────────────────────────────────────────
# F3 — every output_type in the catalog has a landing branch
# ──────────────────────────────────────────────────────────────────────

class TestOutputTypeCoverage(unittest.TestCase):
    def test_all_catalog_output_types_handled(self):
        import yaml
        sch = yaml.safe_load(
            (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
        )["schematics"]
        catalog_types = {s["output_type"] for s in sch}
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        handled = set(re.findall(r'output_type == "(\w+)"', src))
        # CRAFT.P2: the gear fold uses the tuple-membership form
        # (`output_type in ("gear", "survival_gear")`) — parse those too.
        for grp in re.findall(r'output_type in \(([^)]+)\)', src):
            handled |= set(re.findall(r'"(\w+)"', grp))
        missing = catalog_types - handled
        self.assertEqual(missing, set(),
                         f"output_types with no landing branch: {missing}")

    def test_t5_ship_parts_are_components(self):
        import yaml
        sch = {s["key"]: s for s in yaml.safe_load(
            (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
        )["schematics"]}
        for key in ("t5_hyperdrive_surge_converter",
                    "t5_mil_spec_ion_engine_core"):
            self.assertEqual(sch[key]["output_type"], "component", key)
            self.assertTrue(sch[key].get("stat_target"), key)

    def test_unknown_output_type_guard_exists(self):
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        self.assertIn("unhandled output_type", src)


# ──────────────────────────────────────────────────────────────────────
# F7 — schematic weapon outputs resolve in the registry
# ──────────────────────────────────────────────────────────────────────

class TestWeaponOutputsResolve(unittest.TestCase):
    def test_stun_pistol_and_carbine_in_registry(self):
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        sp = wr.get("stun_pistol")
        bc = wr.get("blaster_carbine")
        self.assertIsNotNone(sp)
        self.assertIsNotNone(bc)
        self.assertTrue(sp.stun_only)
        self.assertTrue(sp.stun_capable)
        self.assertEqual(bc.damage, "5D")

    def test_every_weapon_schematic_output_resolves(self):
        import yaml
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        sch = yaml.safe_load(
            (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
        )["schematics"]
        dangling = [s["key"] for s in sch
                    if s["output_type"] == "weapon"
                    and wr.get(s["output_key"]) is None]
        self.assertEqual(dangling, [], f"dangling weapon outputs: {dangling}")


# ──────────────────────────────────────────────────────────────────────
# F5 — hazard mitigation shape handling
# ──────────────────────────────────────────────────────────────────────

class TestHazardMitigationShapes(unittest.TestCase):
    def test_dict_format_inventory_item_mitigates(self):
        from engine.hazards import _has_mitigation
        char = {"inventory": json.dumps({
            "items": [{"type": "survival_gear", "key": "breath_mask",
                       "quality": 60}],
            "resources": [{"type": "metal", "quantity": 5, "quality": 50}],
        })}
        self.assertTrue(_has_mitigation(char, ["breath_mask"]))

    def test_legacy_list_inventory_still_works(self):
        from engine.hazards import _has_mitigation
        char = {"inventory": json.dumps(
            [{"key": "radiation_suit", "type": "survival_gear"}])}
        self.assertTrue(_has_mitigation(char, ["radiation_suit"]))

    def test_worn_armor_slot_mitigates(self):
        from engine.hazards import _has_mitigation
        from engine.items import ItemInstance, write_equipment
        char = {
            "inventory": json.dumps({"items": [], "resources": []}),
            "equipment": write_equipment(
                armor=ItemInstance(key="radiation_suit")),
        }
        self.assertTrue(_has_mitigation(char, ["radiation_suit"]))

    def test_no_gear_no_mitigation(self):
        from engine.hazards import _has_mitigation
        char = {"inventory": json.dumps({"items": [], "resources": []}),
                "equipment": "{}"}
        self.assertFalse(_has_mitigation(char, ["breath_mask"]))


# ──────────────────────────────────────────────────────────────────────
# P0.9 — carried-gear helpers
# ──────────────────────────────────────────────────────────────────────

class TestCarriedGearHelpers(unittest.TestCase):
    def test_instance_round_trips_through_carried_dict(self):
        from engine.items import (ItemInstance, instance_to_carried,
                                  carried_to_instance)
        item = ItemInstance(key="blaster_pistol", condition=63, quality=88,
                            crafter="Renn")
        d = instance_to_carried(item, name="Blaster Pistol")
        self.assertEqual(d["type"], "weapon")
        back = carried_to_instance(d)
        self.assertEqual(back.key, "blaster_pistol")
        self.assertEqual(back.condition, 63)
        self.assertEqual(back.quality, 88)
        self.assertEqual(back.crafter, "Renn")

    def test_find_carried_gear_matches_by_display_name(self):
        from engine.items import find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        carried = [
            {"type": "ship_component", "key": "engine_booster_basic"},
            {"type": "weapon", "key": "blaster_carbine",
             "name": "Blaster Carbine", "condition": 90},
            {"type": "armor", "key": "blast_vest", "name": "Blast Vest"},
        ]
        idx, d, w = find_carried_gear(carried, "carbine", wr,
                                      want_armor=False)
        self.assertEqual(idx, 1)
        self.assertEqual(w.key if hasattr(w, "key") else d["key"],
                         "blaster_carbine")
        # armor filter
        idx2, d2, a = find_carried_gear(carried, "vest", wr, want_armor=True)
        self.assertEqual(idx2, 2)
        # weapon search must not return the armor
        idx3, _, _ = find_carried_gear(carried, "vest", wr, want_armor=False)
        self.assertIsNone(idx3)

    def test_find_carried_gear_skips_non_gear(self):
        from engine.items import find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        carried = [{"type": "survival_gear", "key": "breath_mask",
                    "name": "Breath Mask"}]
        idx, d, w = find_carried_gear(carried, "breath", wr)
        self.assertIsNone(idx)


# ──────────────────────────────────────────────────────────────────────
# Source pins — parser sites (behavioral gate is the Windows suite)
# ──────────────────────────────────────────────────────────────────────

class TestParserSourcePins(unittest.TestCase):
    SRC = (REPO / "parser" / "crafting_commands.py")

    def _src(self):
        return self.SRC.read_text(encoding="utf-8")

    def _code(self, path=None):
        """Source with full-line comments stripped (pins must not match
        the explanatory comments that describe the OLD bugs)."""
        text = (path or self.SRC).read_text(encoding="utf-8")
        return "\n".join(
            ln for ln in text.splitlines()
            if not ln.lstrip().startswith("#"))

    def test_craft_rolls_skill_required(self):
        code = self._code()
        self.assertIn('schematic.get("skill_required"', code)         # F1.C
        self.assertNotIn('schematic.get("skill",', code)

    def test_resolve_craft_receives_result_object(self):
        # F1.D: the float-passing call shape must not return.
        code = self._code()
        self.assertNotIn("resolve_craft(char, schematic, quality_base)", code)
        self.assertIn("resolve_craft(char, schematic, result)", code)

    def test_listings_read_real_fields(self):
        code = self._code()
        self.assertNotIn("resource_requirements", code)               # F1.B1
        # F1.B2: the resources LISTING must read stack 'quantity'. The
        # survey-result transient dict legitimately uses 'amount'
        # (get_survey_resources contract) — only the stored-stack
        # bracket-read was the crash. Pin the old listing idiom out and
        # the new one in.
        self.assertNotIn("x{r['amount']", code)
        self.assertIn("r.get('quantity'", code)

    def test_no_session_items_landing(self):
        # F2: the evaporation path must not return.
        self.assertNotIn("ctx.session.items", self._code())

    def test_landings_use_add_to_inventory(self):
        # F2-F4: one call per inventory-landing branch
        # (weapon, component, survival_gear, equipment).
        self.assertGreaterEqual(
            self._src().count("add_to_inventory"), 4)

    def test_no_bare_list_inventory_writes(self):
        # F4: the data-destroying reset-to-list idiom must not return.
        self.assertNotIn("if not isinstance(inv, list):", self._src())

    def test_equip_wear_no_longer_mint(self):
        # P0.9: gear verbs must not mint vendor instances; only the
        # credits-charged buy paths may.
        src = (REPO / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8")
        self.assertNotIn("new_from_vendor", src)

    def test_stun_only_forced_in_attack(self):
        src = (REPO / "parser" / "combat_commands.py").read_text(
            encoding="utf-8")
        self.assertIn("stun_only", src)


if __name__ == "__main__":
    unittest.main()


# ──────────────────────────────────────────────────────────────────────
# CRAFT.P1 — persistence no-op class (2026-06-10)
# db.save_character(id) with NO kwargs returns immediately; seven sites
# believed they were saving. E7's first Windows run was the detector
# (craft success, consumables.medpac=0 on re-fetch). These pins make the
# whole CLASS unrepresentable, not just the seven instances.
# ──────────────────────────────────────────────────────────────────────

class TestPersistenceNoOpClass(unittest.TestCase):
    SWEEP_DIRS = ("parser", "engine")

    @staticmethod
    def _code(path):
        text = path.read_text(encoding="utf-8")
        return "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#"))

    def test_no_kwargsless_save_character_anywhere(self):
        # A save_character(...) call with positional args only and NO
        # keywords is ALWAYS a bug — db.save_character persists nothing
        # without field kwargs. AST-walk (not regex) so docstrings and
        # comments describing the old bug can't false-positive, and
        # kwarg-bearing / **splat calls can't either.
        import ast as _ast
        offenders = []
        for d in self.SWEEP_DIRS:
            for p in (REPO / d).rglob("*.py"):
                tree = _ast.parse(p.read_text(encoding="utf-8"))
                for node in _ast.walk(tree):
                    if not isinstance(node, _ast.Call):
                        continue
                    fn = node.func
                    name = (fn.attr if isinstance(fn, _ast.Attribute)
                            else getattr(fn, "id", ""))
                    if name == "save_character" and not node.keywords:
                        offenders.append(
                            f"{p.relative_to(REPO)}:{node.lineno}")
        self.assertEqual(offenders, [],
                         "kwargs-less save_character (a silent no-op):\n"
                         + "\n".join(offenders))

    def test_save_char_is_attributes_only(self):
        # _save_char persists attributes and MUST NOT persist inventory:
        # db.add_to_inventory does its own DB read-modify-write, and a
        # blanket dict-inventory write after delivery clobbers the
        # landed item (F2 evaporation via stale-dict overwrite).
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        body = src.split("async def _save_char", 1)[1].split(
            "\nasync def", 1)[0].split("\nclass ", 1)[0]
        self.assertIn('attributes=char["attributes"]', body)
        self.assertNotIn("inventory=", body)

    def test_craft_consumption_saved_before_delivery(self):
        # Ordering invariant: resolve_craft consumes dict-side, so the
        # inventory save must land BEFORE _deliver_item's DB RMW —
        # saving after would clobber the delivered item.
        code = self._code(REPO / "parser" / "crafting_commands.py")
        i_resolve = code.index("resolve_craft(char, schematic, result)")
        i_save = code.index('inventory=char["inventory"]', i_resolve)
        i_deliver = code.index("_deliver_item(", i_resolve)
        self.assertLess(i_save, i_deliver,
                        "consumption save must precede _deliver_item")

    def test_survey_saves_both_columns_and_pushes(self):
        code = self._code(REPO / "parser" / "crafting_commands.py")
        cls = code.split("class SurveyCommand", 1)[1].split("\nclass ", 1)[0]
        self.assertIn('attributes=char["attributes"]', cls)
        self.assertIn('inventory=char["inventory"]', cls)
        self.assertIn("_push_crafting_state(ctx)", cls)

    def test_teach_target_save_carries_attributes(self):
        code = self._code(REPO / "parser" / "crafting_commands.py")
        self.assertIn(
            'save_character(\n                target_char["id"], '
            'attributes=target_char["attributes"])',
            code)

    def test_salvage_credits_use_ledger_chokepoint(self):
        # Space salvage credits must flow through adjust_credits (the
        # economy-invariant chokepoint), tagged for the @economy ledger.
        code = self._code(REPO / "parser" / "space_commands.py")
        self.assertIn('"space_salvage"', code)
        idx = code.index('"space_salvage"')
        self.assertIn("adjust_credits", code[idx - 200:idx])

    def test_anomaly_award_mutates_real_dict(self):
        code = self._code(REPO / "engine" / "encounter_anomaly.py")
        self.assertNotIn("add_resource(dict(char)", code)
        self.assertIn('inventory=work["inventory"]', code)
