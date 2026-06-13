"""CRAFT.P2 — Gundark Drop A tests (2026-06-10).

Foundation + consumables migration + first Avail-band content, per
gundark_crafting_integration_design_v1.md (§5 rubrics, §8 Drop A, §10
worked sample — signed off) under the mechanical-use mandate
(crafting_integration_design_pass_v1.md §3.2a).

Covers:
  • consumables registry (engine/consumables.py + data/consumables.yaml)
  • registry ↔ _STIM_CATALOG ↔ schematic-output three-way parity
  • the medpac consumer (heal-kind catalog entries + the heal branch) —
    the first mandate fix: crafted medpacs were INERT tokens at HEAD
  • survival_gear → gear fold (decision 2a)
  • armor landing branch (Drop C infrastructure, sanctioned)
  • the two Avail-band weapons, with §5.1 rubric difficulties
    RECOMPUTED in-test (the rubric is mechanical and auditable — so
    audit it)
  • no `contraband:` field ships before Drop G's enforcer
"""
import json
import re
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


# ──────────────────────────────────────────────────────────────────────
# Consumables registry
# ──────────────────────────────────────────────────────────────────────

class TestConsumablesRegistry(unittest.TestCase):
    def test_loads_and_lookups(self):
        from engine.consumables import (get_consumable, get_all_consumables,
                                        consumable_display_name)
        allc = get_all_consumables()
        self.assertGreaterEqual(len(allc), 7)
        row = get_consumable("medpac")
        self.assertEqual(row["name"], "Medpac")
        self.assertEqual(row["category"], "medical")
        self.assertEqual(consumable_display_name("medpac_advanced"),
                         "Advanced Medpac")
        self.assertIsNone(get_consumable("no_such_thing"))
        self.assertEqual(consumable_display_name("no_such_thing"),
                         "no_such_thing")

    def test_cache_poison_safe(self):
        from engine.consumables import get_consumable
        row = get_consumable("medpac")
        row["name"] = "POISONED"
        self.assertEqual(get_consumable("medpac")["name"], "Medpac")

    def test_parser_dict_is_gone(self):
        # The migration is real: the parser-local dict must not return.
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        self.assertNotIn("_CONSUMABLE_STATS = {", code)
        self.assertIn("consumable_display_name", code)


class TestThreeWayConsumableParity(unittest.TestCase):
    """Every consumable output_key must exist in the identity registry
    (data/consumables.yaml) and have a real USE-TIME mechanic — either in
    the stim/medical mechanics catalog (_STIM_CATALOG) OR in a sanctioned
    non-stim consumer (NON_STIM_CONSUMERS below). No inert tokens; the
    catalog must carry no orphans. This pin keeps the bifurcated design
    honest while allowing non-stim consumables (which have their mechanic
    in a dedicated verb, not _STIM_CATALOG)."""

    # Consumables whose use-time mechanic lives OUTSIDE _STIM_CATALOG.
    # Each maps to where its real consumer is — so this stays an explicit,
    # documented exception, not a silent gap.
    NON_STIM_CONSUMERS = {
        # CRAFT.mines_breaching_split (2026-06-13): consumed by the
        # `breach` verb -> engine/breaching.py::attempt_breach.
        "breaching_charge": "engine/breaching.py::attempt_breach",
        # CRAFT.HOOK.restraints (2026-06-13): consumed by the `cuff` verb
        # -> engine/restraints.py::attempt_cuff (spent on a successful cuff).
        "binders": "engine/restraints.py::attempt_cuff",
    }

    def test_schematic_outputs_have_identity_and_mechanics(self):
        from engine.consumables import get_all_consumables
        from parser.medical_commands import _STIM_CATALOG
        identity = set(get_all_consumables())
        mechanics = set(_STIM_CATALOG) | set(self.NON_STIM_CONSUMERS)
        outputs = {s["output_key"] for s in _schematics()
                   if s["output_type"] == "consumable"}
        self.assertEqual(outputs - identity, set(),
                         "craftable consumables missing identity rows")
        self.assertEqual(outputs - mechanics, set(),
                         "craftable consumables with NO use-time "
                         "mechanics (inert tokens — either add to "
                         "_STIM_CATALOG or NON_STIM_CONSUMERS with its "
                         "real consumer)")

    def test_breaching_charge_has_a_real_consumer(self):
        # The non-stim exception must point at a real module/symbol — not
        # a way to smuggle in inert tokens.
        from engine.breaching import attempt_breach, BREACHING_CHARGE_KEY
        self.assertEqual(BREACHING_CHARGE_KEY, "breaching_charge")
        self.assertTrue(callable(attempt_breach))

    def test_binders_has_a_real_consumer(self):
        from engine.restraints import attempt_cuff, BINDERS_KEY
        self.assertEqual(BINDERS_KEY, "binders")
        self.assertTrue(callable(attempt_cuff))

    def test_catalog_has_no_orphans(self):
        from engine.consumables import get_all_consumables
        from parser.medical_commands import _STIM_CATALOG
        identity = set(get_all_consumables())
        self.assertEqual(set(_STIM_CATALOG) - identity, set(),
                         "catalog keys with no identity row")


# ──────────────────────────────────────────────────────────────────────
# Medpac consumer (the mandate fix)
# ──────────────────────────────────────────────────────────────────────

class TestMedpacConsumer(unittest.TestCase):
    def test_heal_entries_shape(self):
        from parser.medical_commands import _STIM_CATALOG
        for key, levels, diff in (("medpac", 1, 10),
                                  ("medpac_advanced", 2, 12),
                                  ("medpac_fastflesh", 1, 8)):
            spec = _STIM_CATALOG[key]
            self.assertEqual(spec["heal_wound_levels"], levels, key)
            self.assertEqual(spec["difficulty"], diff, key)
            self.assertIsNone(spec["buff_type"], key)
            self.assertEqual(spec["skill"], "first aid", key)
            self.assertTrue(spec["self_administration_ok"], key)

    def test_aliases_resolve(self):
        from parser.medical_commands import _canonical_consumable
        self.assertEqual(_canonical_consumable("medpac"), "medpac")
        self.assertEqual(_canonical_consumable("medkit"), "medpac")
        self.assertEqual(_canonical_consumable("fastflesh"),
                         "medpac_fastflesh")
        self.assertEqual(_canonical_consumable("advanced medpac"),
                         "medpac_advanced")

    def test_heal_branch_runs_before_buff_and_floors_at_zero(self):
        # Source-order + behavior pins on _execute_stim_roll: the heal
        # branch must come BEFORE add_buff (buff_type is None for
        # medpacs — reaching the buff line would crash), and must floor
        # at 0, not go negative.
        src = (REPO / "parser" / "medical_commands.py").read_text(
            encoding="utf-8")
        body = src.split("async def _execute_stim_roll", 1)[1]
        i_heal = body.index('heal_wound_levels')
        i_buff = body.index('add_buff(target_char, spec["buff_type"])')
        self.assertLess(i_heal, i_buff)
        self.assertIn("max(0, old_wound - heal_levels)", body)

    def test_heal_kind_bypasses_active_stim_gate(self):
        # A medpac applies no buff; an active stim must not block it
        # and it must not trigger the overdose path.
        src = (REPO / "parser" / "medical_commands.py").read_text(
            encoding="utf-8")
        gate = src.split("get_active_stim(target_char)", 1)[1][:800]
        self.assertIn('spec.get("heal_wound_levels", 0)', gate)


# ──────────────────────────────────────────────────────────────────────
# Gear fold + armor branch
# ──────────────────────────────────────────────────────────────────────

class TestGearFoldAndArmorBranch(unittest.TestCase):
    def test_no_survival_gear_output_type_remains(self):
        leftovers = [s["key"] for s in _schematics()
                     if s["output_type"] == "survival_gear"]
        self.assertEqual(leftovers, [],
                         "decision 2a: survival_gear folds into gear")

    def test_gear_family_retyped_intact(self):
        gear = {s["key"] for s in _schematics()
                if s["output_type"] == "gear"}
        for k in ("breath_mask", "radiation_suit", "cooling_unit",
                  "water_canteen", "anti_theft_alarm"):
            self.assertIn(k, gear)

    def test_branch_accepts_both_and_lands_gear_type(self):
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        self.assertIn('output_type in ("gear", "survival_gear")', src)
        branch = src.split('output_type in ("gear", "survival_gear")',
                           1)[1][:900]
        self.assertIn('"type":     "gear"', branch)

    def test_armor_branch_is_instance_shaped(self):
        src = (REPO / "parser" / "crafting_commands.py").read_text(
            encoding="utf-8")
        self.assertIn('elif output_type == "armor":', src)
        branch = src.split('elif output_type == "armor":', 1)[1][:900]
        for field in ('"type":      "armor"', '"condition": 100',
                      '"crafter":'):
            self.assertIn(field, branch)


# ──────────────────────────────────────────────────────────────────────
# Avail-band weapons — rubric audited, not eyeballed
# ──────────────────────────────────────────────────────────────────────

def _rubric_difficulty(damage_dice: int, avail: int,
                       complexity: int = 0) -> int:
    """§5.1: BASE(by damage) + AVAIL_MOD + COMPLEXITY_MOD."""
    base = {3: 10, 4: 12, 5: 15, 6: 18, 7: 20}[min(damage_dice, 7)]
    avail_mod = {1: 0, 2: 2, 3: 4, 4: 6}[avail]
    return min(base + avail_mod + complexity, 26)


class TestAvailBandWeapons(unittest.TestCase):
    def test_rubric_difficulties_recompute(self):
        sch = {s["key"]: s for s in _schematics()}
        # Thunderer: 6D+2 → BASE 18; Avail 2 → +2 = 20
        self.assertEqual(sch["heavy_blaster_pistol_t6"]["difficulty"],
                         _rubric_difficulty(6, 2))
        # Vibrorapier: STR+3D ≈ 5D-equiv → BASE 15; Avail 2 → +2 = 17
        self.assertEqual(sch["vibrorapier_duelist"]["difficulty"],
                         _rubric_difficulty(5, 2))

    def test_avail2_min_quality_band(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in ("heavy_blaster_pistol_t6", "vibrorapier_duelist"):
            for comp in sch[key]["components"]:
                self.assertEqual(comp["min_quality"], 40,
                                 f"{key}: §5.2 Avail-2 band is q40")

    def test_weapon_stats_match_extraction(self):
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        t6 = wr.get("heavy_blaster_pistol_t6")
        self.assertEqual(t6.damage, "6D+2")
        self.assertEqual(t6.cost, 750)
        self.assertFalse(t6.stun_capable)
        vr = wr.get("vibrorapier_duelist")
        self.assertEqual(vr.damage, "STR+3D")
        self.assertEqual(vr.skill, "melee combat")
        self.assertEqual(vr.cost, 300)

    def test_trainer_and_skill_conventions(self):
        sch = {s["key"]: s for s in _schematics()}
        self.assertEqual(sch["heavy_blaster_pistol_t6"]["trainer_npc"],
                         "Kayson")
        self.assertEqual(sch["heavy_blaster_pistol_t6"]["skill_required"],
                         "blaster_repair")
        self.assertEqual(sch["vibrorapier_duelist"]["skill_required"],
                         "melee_combat")

    def test_contraband_only_with_its_enforcer(self):
        # Drop G (2026-06-12) shipped the gating: landed items carry
        # the flag and patrol boardings sweep for it. The phantom-guard
        # flips to a scope pin — exactly the black-market band, all
        # taught by the underworld trainer, none lawlessly teachable.
        flagged = sorted(s["key"] for s in _schematics()
                         if "contraband" in s)
        self.assertEqual(flagged, ["anti_vehicle_grenade",
                                   "disruptor_pistol", "predator_rifle"])
        for s in _schematics():
            if "contraband" in s:
                self.assertEqual(s["trainer_npc"], "Gundark", s["key"])


if __name__ == "__main__":
    unittest.main()
