"""CRAFT.GUNDARK Drop B — lawful Avail 1–3 weapons band (2026-06-11).

14 schematics + 14 weapons.yaml rows per
gundark_crafting_integration_design_v1.md §2.4/§5/§8 Drop B, under:
  • decision 4a (curated breadth) — near-duplicates and items whose
    primary mechanic has no engine consumer are deliberately absent
  • decision (a)=b (2026-06-11) — Kayson teaches the full lawful 1–3
    set; §5.2 quality bands + §5.1 difficulty do the tier gating until
    Drop G ships R/X enforcement
  • the mechanical-use mandate — every item's PRIMARY use (the attack
    path) exists at HEAD; book-only sub-mechanics (hook disarm, misfire,
    suppression, scope, grip) are notes, not phantom fields
  • the §10 worked-sample conventions (skill_required dialect,
    Kayson-binding, STR+nD ≈ (n+2)D-equiv)

Difficulties are RECOMPUTED here from the §5.1 rubric — drift in the
data fails the suite. Also ties to drop 1 (skill-key unification): every
new skill_required must resolve to a registered skill.
"""
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

NEW_KEYS = [
    "vibrosaw_greel", "blaster_pistol_dl22", "heavy_blaster_pistol_dl6h",
    "vibrodagger_talon", "stun_gauntlets_ppg", "contact_stunner_c512",
    "autocaster_drolan", "holdout_blaster_b22", "sniper_rifle_x45",
    "blaster_rifle_firelance", "riot_gun_bt500",
    "satskar_ekkar", "coynskar_ekkar", "flash_pistol_sevari",
]

AVAIL = {
    # §2.4 availability band per item (leading digit; autocaster's
    # book "1,2" treated as 2 — priced 700, see the schematic comment).
    "vibrosaw_greel": 1, "blaster_pistol_dl22": 1,
    "heavy_blaster_pistol_dl6h": 1,
    "vibrodagger_talon": 2, "stun_gauntlets_ppg": 2,
    "contact_stunner_c512": 2, "autocaster_drolan": 2,
    "holdout_blaster_b22": 2, "sniper_rifle_x45": 2,
    "blaster_rifle_firelance": 2, "riot_gun_bt500": 2,
    "satskar_ekkar": 3, "coynskar_ekkar": 3, "flash_pistol_sevari": 3,
}

Q_BAND = {1: 25, 2: 40, 3: 55}


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


def _rubric_difficulty(damage_dice: int, avail: int,
                       complexity: int = 0) -> int:
    """§5.1: BASE(by damage) + AVAIL_MOD + COMPLEXITY_MOD."""
    base = {3: 10, 4: 12, 5: 15, 6: 18, 7: 20}[min(damage_dice, 7)]
    avail_mod = {1: 0, 2: 2, 3: 4, 4: 6}[avail]
    return min(base + avail_mod + complexity, 26)


class TestDropBRubricRecompute(unittest.TestCase):
    # damage-dice equivalent per item: blasters by leading die count
    # (pips never bump the band — Drop A's 6D+2 → 18 precedent);
    # melee STR+nD ≈ (n+2)D per the signed-off §10 sample.
    DICE_EQUIV = {
        "vibrosaw_greel": 4,            # STR+2D+1
        "blaster_pistol_dl22": 4,       # 4D+1
        "heavy_blaster_pistol_dl6h": 5,
        "vibrodagger_talon": 4,         # STR+2D
        "stun_gauntlets_ppg": 4,        # STR+2D
        "contact_stunner_c512": 4,      # 4D+2
        "autocaster_drolan": 3,
        "holdout_blaster_b22": 3,
        "sniper_rifle_x45": 5,
        "blaster_rifle_firelance": 5,
        "riot_gun_bt500": 5,            # 5D+1
        "satskar_ekkar": 5,             # STR+3D+1
        "coynskar_ekkar": 4,            # STR+2D
        "flash_pistol_sevari": 4,       # 4D+2
    }

    def test_all_fourteen_recompute(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            want = _rubric_difficulty(self.DICE_EQUIV[key], AVAIL[key])
            self.assertEqual(
                sch[key]["difficulty"], want,
                f"{key}: difficulty drifted from the §5.1 rubric")

    def test_min_quality_bands(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            band = Q_BAND[AVAIL[key]]
            for comp in sch[key]["components"]:
                self.assertEqual(
                    comp["min_quality"], band,
                    f"{key}: §5.2 Avail-{AVAIL[key]} band is q{band}")

    def test_component_totals_in_size_band(self):
        # §5.2: small/holdout 3–4 total; standard 4–6; rifle/heavy 6–9.
        sizes = {
            "vibrodagger_talon": (3, 4), "holdout_blaster_b22": (3, 4),
            "stun_gauntlets_ppg": (3, 4), "contact_stunner_c512": (3, 4),
            "flash_pistol_sevari": (3, 4),
            "vibrosaw_greel": (4, 6), "blaster_pistol_dl22": (4, 6),
            "heavy_blaster_pistol_dl6h": (4, 6),
            "autocaster_drolan": (4, 6), "satskar_ekkar": (4, 6),
            "coynskar_ekkar": (4, 6),
            "sniper_rifle_x45": (6, 9), "blaster_rifle_firelance": (6, 9),
            "riot_gun_bt500": (6, 9),
        }
        sch = {s["key"]: s for s in _schematics()}
        for key, (lo, hi) in sizes.items():
            total = sum(c["quantity"] for c in sch[key]["components"])
            self.assertTrue(lo <= total <= hi,
                            f"{key}: {total} units outside §5.2 band "
                            f"{lo}–{hi}")


class TestDropBWeaponStats(unittest.TestCase):
    DAMAGE = {
        "vibrosaw_greel": "STR+2D+1", "blaster_pistol_dl22": "4D+1",
        "heavy_blaster_pistol_dl6h": "5D", "vibrodagger_talon": "STR+2D",
        "stun_gauntlets_ppg": "STR+2D", "contact_stunner_c512": "4D+2",
        "autocaster_drolan": "3D", "holdout_blaster_b22": "3D",
        "sniper_rifle_x45": "5D", "blaster_rifle_firelance": "5D",
        "riot_gun_bt500": "5D+1", "satskar_ekkar": "STR+3D+1",
        "coynskar_ekkar": "STR+2D", "flash_pistol_sevari": "4D+2",
    }

    def setUp(self):
        from engine.weapons import get_weapon_registry
        self.wr = get_weapon_registry()

    def test_all_damage_strings_match_extraction(self):
        for key, dmg in self.DAMAGE.items():
            w = self.wr.get(key)
            self.assertIsNotNone(w, f"{key} missing from weapon registry")
            self.assertEqual(w.damage, dmg, key)

    def test_use_skill_and_type_routing(self):
        # Combat routing: brawling ∈ MELEE_SKILLS; "missile weapons" and
        # "firearms" ∈ RANGED_SKILLS; types map to keyed scar flavor.
        self.assertEqual(self.wr.get("stun_gauntlets_ppg").skill,
                         "brawling")
        self.assertEqual(self.wr.get("autocaster_drolan").skill,
                         "missile weapons")
        self.assertEqual(self.wr.get("autocaster_drolan").weapon_type,
                         "bowcaster")
        self.assertEqual(self.wr.get("flash_pistol_sevari").skill,
                         "firearms")
        self.assertEqual(self.wr.get("flash_pistol_sevari").weapon_type,
                         "firearms")
        from engine.combat import is_ranged_skill, is_melee_skill
        self.assertTrue(is_melee_skill("brawling"))
        self.assertTrue(is_ranged_skill("missile weapons"))
        self.assertTrue(is_ranged_skill("firearms"))

    def test_stun_conventions(self):
        cs = self.wr.get("contact_stunner_c512")
        self.assertTrue(cs.stun_capable)
        self.assertTrue(cs.stun_only)       # the P0.7 forced-stun path
        # Standard-pattern blasters keep the registry's stun convention;
        # dedicated lethal hardware does not.
        self.assertTrue(self.wr.get("blaster_pistol_dl22").stun_capable)
        self.assertFalse(self.wr.get("sniper_rifle_x45").stun_capable)
        self.assertFalse(self.wr.get("riot_gun_bt500").stun_capable)

    def test_distinguishing_numbers(self):
        self.assertEqual(self.wr.get("riot_gun_bt500").ammo, 300)
        self.assertEqual(self.wr.get("flash_pistol_sevari").ammo, 1)
        self.assertEqual(self.wr.get("sniper_rifle_x45").ranges,
                         [1, 25, 100, 250])
        self.assertEqual(self.wr.get("vibrodagger_talon").cost, 50)

    def test_melee_difficulty_words(self):
        # Loader key is `difficulty:` → WeaponData.melee_difficulty.
        # Includes the Drop A remediation: vibrorapier was missing its
        # book value ("moderate").
        want = {
            "vibrodagger_talon": "easy", "vibrosaw_greel": "moderate",
            "stun_gauntlets_ppg": "easy",
            "contact_stunner_c512": "very easy",
            "satskar_ekkar": "difficult", "coynskar_ekkar": "moderate",
            "vibrorapier_duelist": "moderate",
        }
        for key, word in want.items():
            self.assertEqual(self.wr.get(key).melee_difficulty, word, key)


class TestDropBConventions(unittest.TestCase):
    def test_kayson_bound_lawful(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            self.assertEqual(sch[key]["trainer_npc"], "Kayson",
                             f"{key}: decision (a)=b — lawful 1–3 via "
                             f"Kayson until Drop G")

    def test_skill_required_dialect(self):
        sch = {s["key"]: s for s in _schematics()}
        want = {"melee_combat", "blaster_repair", "missile_weapons",
                "firearms"}
        got = {sch[k]["skill_required"] for k in NEW_KEYS}
        self.assertEqual(got, want)

    def test_skill_required_resolves_post_drop1(self):
        # Drop 1 tie-in: every new skill_required must canonicalize to
        # a REGISTERED skill — the gate that makes rubric
        # mass-application safe.
        from engine.character import SkillRegistry, canonical_skill_key
        reg = SkillRegistry()
        reg.load_file(str(REPO / "data" / "skills.yaml"))
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            req = sch[key]["skill_required"]
            self.assertIsNotNone(reg.get(canonical_skill_key(req)),
                                 f"{key}: '{req}' unresolved")

    def test_output_keys_resolve_no_dangling(self):
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            self.assertIsNotNone(wr.get(sch[key]["output_key"]),
                                 f"{key}: dangling output_key")

    def test_contraband_field_scope(self):
        # Drop G shipped the enforcer (2026-06-12) — the Drop A "no
        # contraband yet" pin flips to a SCOPE pin: exactly the
        # black-market band carries the field; nothing lawful does.
        flagged = sorted(s["key"] for s in _schematics()
                         if "contraband" in s)
        self.assertEqual(flagged, ["anti_vehicle_grenade",
                                   "disruptor_pistol", "predator_rifle"])

    def test_book_base_costs(self):
        sch = {s["key"]: s for s in _schematics()}
        want = {
            "vibrosaw_greel": 400, "blaster_pistol_dl22": 500,
            "heavy_blaster_pistol_dl6h": 800, "vibrodagger_talon": 50,
            "stun_gauntlets_ppg": 300, "contact_stunner_c512": 575,
            "autocaster_drolan": 700, "holdout_blaster_b22": 300,
            "sniper_rifle_x45": 750, "blaster_rifle_firelance": 1200,
            "riot_gun_bt500": 1500, "satskar_ekkar": 700,
            "coynskar_ekkar": 400, "flash_pistol_sevari": 300,
        }
        for key, cost in want.items():
            self.assertEqual(sch[key]["base_cost"], cost, key)


if __name__ == "__main__":
    unittest.main()
