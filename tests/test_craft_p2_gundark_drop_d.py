"""CRAFT.GUNDARK Drop D — ordnance + single-use consumption (2026-06-11).

3 schematics (demolitions, per decision b=a) + 2 new grenade rows + the
single-use consumption mechanic, per gundark plan §2.5/§5/§8 Drop D:

  • PRE-FLIGHT FACTS that shaped the drop: `blast_radius` loads into
    WeaponData but has NO combat consumer (frag/thermal precedent is
    single-target), and ammo is COMPLETELY unmodeled — grenades at HEAD
    were infinite-use weapons. Faucets and sinks land together, so the
    drop ships consumption: `single_use: true` rows are cleared from the
    equipment slot at attack DECLARATION (the throw is committed; round
    resolution rolls the action's captured strings, never a live
    equipment re-read). frag_grenade and thermal_detonator gain the flag
    retroactively. The Merr-Sonn stun grenade is the book-sanctioned
    rechargeable exception (`single_use: false`).
  • Deferred wholesale: gas/spore/glop/smoke (effect-primary, no
    consumer), mines/breaching/detonite (demolition-placement
    mechanics), nets (restraint-gated), missiles (launcher-gated),
    anti-vehicle + Firegems (contraband band → Drop G).
"""
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

NEW_SCHEMATICS = ["incendiary_grenade", "frag_grenade",
                  "stun_grenade_merr_sonn"]


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


class TestDropDRubric(unittest.TestCase):
    # weapons damage BASE (≤3D→10, 4D→12, 5D→15, 6D→18) + avail mod
    EXPECTED = {
        "incendiary_grenade": (4, 1, 12),
        "frag_grenade": (5, 2, 17),
        "stun_grenade_merr_sonn": (6, 2, 20),
    }

    def test_difficulties_recompute(self):
        base = {3: 10, 4: 12, 5: 15, 6: 18}
        avail_mod = {1: 0, 2: 2, 3: 4}
        sch = {s["key"]: s for s in _schematics()}
        for key, (dice, avail, want) in self.EXPECTED.items():
            self.assertEqual(base[dice] + avail_mod[avail], want)
            self.assertEqual(sch[key]["difficulty"], want, key)

    def test_q_bands(self):
        sch = {s["key"]: s for s in _schematics()}
        bands = {"incendiary_grenade": 25, "frag_grenade": 40,
                 "stun_grenade_merr_sonn": 40}
        for key, band in bands.items():
            for c in sch[key]["components"]:
                self.assertEqual(c["min_quality"], band, key)

    def test_explosives_mix_chemical_primary(self):
        # §4: chemical primary, rare secondary, metal casing.
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_SCHEMATICS:
            comps = {c["type"]: c["quantity"] for c in sch[key]["components"]}
            self.assertIn("chemical", comps, key)
            self.assertIn("rare", comps, key)
            self.assertEqual(max(comps, key=comps.get), "chemical", key)
            self.assertTrue(3 <= sum(comps.values()) <= 4, key)

    def test_demolitions_skill_and_kayson(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_SCHEMATICS:
            self.assertEqual(sch[key]["skill_required"], "demolitions", key)
            self.assertEqual(sch[key]["trainer_npc"], "Kayson", key)

    def test_demolitions_resolves_post_drop1(self):
        from engine.character import SkillRegistry, canonical_skill_key
        reg = SkillRegistry()
        reg.load_file(str(REPO / "data" / "skills.yaml"))
        sd = reg.get(canonical_skill_key("demolitions"))
        self.assertIsNotNone(sd)
        self.assertEqual(sd.attribute, "technical")


class TestDropDWeaponRows(unittest.TestCase):
    def setUp(self):
        from engine.weapons import get_weapon_registry
        self.wr = get_weapon_registry()

    def test_new_rows(self):
        inc = self.wr.get("incendiary_grenade")
        self.assertEqual(inc.damage, "4D")
        self.assertEqual(inc.weapon_type, "grenade")
        self.assertEqual(inc.skill, "grenade")
        self.assertTrue(inc.single_use)
        self.assertEqual(inc.cost, 300)
        stun = self.wr.get("stun_grenade_merr_sonn")
        self.assertEqual(stun.damage, "6D")
        self.assertTrue(stun.stun_only)
        self.assertFalse(stun.single_use,
                         "book-rechargeable — the sanctioned exception")
        self.assertEqual(stun.cost, 450)

    def test_existing_explosives_flagged_single_use(self):
        # Retroactive sink: frag/thermal were infinite-use weapons.
        self.assertTrue(self.wr.get("frag_grenade").single_use)
        self.assertTrue(self.wr.get("thermal_detonator").single_use)

    def test_single_use_defaults_false_elsewhere(self):
        # The flag is explicit per-row, never type- or default-derived:
        # ordinary weapons must not start vanishing.
        for key in ("blaster_pistol", "vibrorapier_duelist",
                    "heavy_blaster_pistol_dl6h"):
            self.assertFalse(self.wr.get(key).single_use, key)

    def test_thermal_detonator_not_craftable(self):
        # X-class icon stays out of the lawful catalog (Drop G at best).
        sch_keys = {s["key"] for s in _schematics()}
        self.assertNotIn("thermal_detonator", sch_keys)


class TestConsumptionMechanic(unittest.TestCase):
    def _code(self):
        src = (REPO / "parser" / "combat_commands.py").read_text(
            encoding="utf-8")
        return "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))

    def test_consumption_hook_present(self):
        code = self._code()
        self.assertIn('getattr(equipped_weapon, "single_use", False)', code)
        self.assertIn("write_equipment(", code)

    def test_consumption_guarded_by_default_damage(self):
        # An explicit `with <skill> damage <dice>` override is some OTHER
        # attack and must not eat the grenade.
        code = self._code()
        idx = code.index('getattr(equipped_weapon, "single_use", False)')
        window = code[idx - 200:idx + 400]
        self.assertIn("damage == default_damage", window)

    def test_declare_returns_success(self):
        # The hook keys off a successful declaration — the method must
        # report it (it returned None-always before this drop).
        import inspect
        from parser.combat_commands import AttackCommand
        src = inspect.getsource(AttackCommand._declare_and_broadcast)
        self.assertIn("return False", src)
        self.assertIn("return True", src)

    def test_slot_cleared_preserves_armor(self):
        # The consumption write must be the canonical per-slot form —
        # weapon cleared, armor slot carried through.
        code = self._code()
        idx = code.index('getattr(equipped_weapon, "single_use", False)')
        window = code[idx:idx + 600]
        self.assertIn('weapon=None, armor=_slots["armor"]', window)


if __name__ == "__main__":
    unittest.main()
