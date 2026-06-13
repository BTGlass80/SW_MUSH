"""CRAFT.GUNDARK Drop C — non-powered armor + the armorer trainer (2026-06-11).

10 schematics + 10 `type: armor` weapons.yaml rows + 1 trainer NPC
(Sela Tarn, Kayson's Weapon Shop), per
gundark_crafting_integration_design_v1.md §3.1/§5/§8 Drop C, under:
  • the live registry reality — armor rows belong in weapons.yaml (wear /
    soak / sheet all read the weapon registry); the plan's separate
    armor.yaml was superseded by extend-don't-add
  • decision (a)=b — lawful Avail 1–3 via the trainer; q-bands 25/40/55
  • the mechanical-use mandate — primary use = wear → soak (live);
    sub-systems with no consumer (camo, IR alarm, servo, enviro, swim,
    layering, armor mods) are notes; powered/space suits (§3.2) DEFERRED
    (no `powersuit operation` skill, no mount consumer)
  • the §10 worked-sample anchor for the armor difficulty BASE: total
    protection DICE across both tracks, loose pips summing to 3+ round
    up one unit (blast_vest_corondexx +2/+1D → 1 unit → 12 + Avail 2 = 14)

Also covers the FULL LOOP integration: the crafting armor-landing dict →
carried_to_instance → find_carried_gear(want_armor=True) → registry
is_armor → Character soak/dex-penalty reads parsing every new row
(including pip-only protection strings).
"""
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

NEW_KEYS = [
    "koromondain_vest_mk45", "concussion_vest_cv14", "link_armor_supralink",
    "riot_armor_creshaldyne", "camo_armor_creshaldyne", "blast_vest_corondexx",
    "castaan_staad", "coynite_battle_armor", "ubese_raider_armor",
    "flex_armor_ty1",
]

AVAIL = {
    "koromondain_vest_mk45": 1, "concussion_vest_cv14": 1,
    "link_armor_supralink": 1,
    "riot_armor_creshaldyne": 2, "camo_armor_creshaldyne": 2,
    "blast_vest_corondexx": 2,
    "castaan_staad": 3, "coynite_battle_armor": 3,
    "ubese_raider_armor": 3, "flex_armor_ty1": 3,
}

Q_BAND = {1: 25, 2: 40, 3: 55}

# Extraction §3.1 protection per item, as (energy, physical) dice strings.
PROTECTION = {
    "koromondain_vest_mk45": ("+2", "+1D+2"),
    "concussion_vest_cv14": ("", "+1D"),
    "link_armor_supralink": ("+2", "+1D"),
    "riot_armor_creshaldyne": ("+1D", "+2D"),
    "camo_armor_creshaldyne": ("+2", "+1D"),
    "blast_vest_corondexx": ("+1D", "+2"),
    "castaan_staad": ("+1D", "+1D"),
    "coynite_battle_armor": ("+2D", "+2D"),
    "ubese_raider_armor": ("+1D", "+2D"),
    "flex_armor_ty1": ("+1D", "+1D"),
}

DEX_PENALTY = {
    "link_armor_supralink": "-1D",
    "coynite_battle_armor": "-1D",
    "flex_armor_ty1": "-1D",
}


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


def _armor_units(energy: str, physical: str) -> int:
    """§5.1 armor BASE unit, anchored to the §10 sample: total protection
    DICE across both tracks; loose pips summing to 3+ round up one unit."""
    from engine.dice import DicePool
    pools = [DicePool.parse(s) for s in (energy, physical) if s]
    dice = sum(p.dice for p in pools)
    pips = sum(p.pips for p in pools)
    return dice + (1 if pips >= 3 else 0)


def _rubric_difficulty(units: int, avail: int) -> int:
    base = 12 if units <= 2 else (15 if units <= 4 else 18)
    avail_mod = {1: 0, 2: 2, 3: 4, 4: 6}[avail]
    return min(base + avail_mod, 26)


class TestDropCRubricRecompute(unittest.TestCase):
    def test_unit_helper_matches_signed_off_anchor(self):
        # blast_vest_corondexx: +2 energy... no — extraction: +1D energy,
        # +2 phys → 1 die + 2 pips → 1 unit → BASE 12 + Avail 2 = 14,
        # the exact number in the signed-off §10 sample.
        e, p = PROTECTION["blast_vest_corondexx"]
        self.assertEqual(_armor_units(e, p), 1)
        self.assertEqual(_rubric_difficulty(1, 2), 14)

    def test_all_ten_recompute(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            e, p = PROTECTION[key]
            want = _rubric_difficulty(_armor_units(e, p), AVAIL[key])
            self.assertEqual(
                sch[key]["difficulty"], want,
                f"{key}: difficulty drifted from the §5.1 armor rubric")

    def test_min_quality_bands(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            band = Q_BAND[AVAIL[key]]
            for comp in sch[key]["components"]:
                self.assertEqual(comp["min_quality"], band, key)

    def test_component_mix_convention(self):
        # §4: non-powered armor = composite primary, metal secondary —
        # nothing else; composite quantity strictly greater.
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            comps = {c["type"]: c["quantity"] for c in sch[key]["components"]}
            self.assertEqual(set(comps), {"composite", "metal"}, key)
            self.assertGreater(comps["composite"], comps["metal"], key)
            total = sum(comps.values())
            self.assertTrue(3 <= total <= 6,
                            f"{key}: {total} units outside the armor band")


class TestDropCArmorRows(unittest.TestCase):
    def setUp(self):
        from engine.weapons import get_weapon_registry
        self.wr = get_weapon_registry()

    def test_rows_exist_and_are_armor(self):
        for key in NEW_KEYS:
            w = self.wr.get(key)
            self.assertIsNotNone(w, f"{key} missing from registry")
            self.assertTrue(w.is_armor, key)

    def test_protection_matches_extraction(self):
        for key, (e, p) in PROTECTION.items():
            w = self.wr.get(key)
            self.assertEqual(w.protection_energy, e, key)
            self.assertEqual(w.protection_physical, p, key)

    def test_dex_penalties(self):
        for key in NEW_KEYS:
            w = self.wr.get(key)
            self.assertEqual(w.dexterity_penalty,
                             DEX_PENALTY.get(key, ""), key)

    def test_book_costs(self):
        want = {
            "koromondain_vest_mk45": 250, "concussion_vest_cv14": 500,
            "link_armor_supralink": 500, "riot_armor_creshaldyne": 500,
            "camo_armor_creshaldyne": 1500, "blast_vest_corondexx": 3000,
            "castaan_staad": 750, "coynite_battle_armor": 150,
            "ubese_raider_armor": 1000, "flex_armor_ty1": 2000,
        }
        for key, cost in want.items():
            self.assertEqual(self.wr.get(key).cost, cost, key)

    def test_soak_reads_parse_every_row(self):
        # Character.get_armor_protection must parse every new protection
        # string — INCLUDING the pip-only forms ("+2") this drop
        # introduces to the armor registry.
        from engine.character import Character
        ch = Character()
        for key, (e, p) in PROTECTION.items():
            ch.worn_armor = key
            ep = ch.get_armor_protection(energy=True)
            pp = ch.get_armor_protection(energy=False)
            from engine.dice import DicePool
            want_e = DicePool.parse(e) if e else DicePool(0, 0)
            want_p = DicePool.parse(p) if p else DicePool(0, 0)
            self.assertEqual((ep.dice, ep.pips),
                             (want_e.dice, want_e.pips), f"{key} energy")
            self.assertEqual((pp.dice, pp.pips),
                             (want_p.dice, want_p.pips), f"{key} physical")

    def test_dex_penalty_read(self):
        from engine.character import Character
        ch = Character()
        ch.worn_armor = "coynite_battle_armor"
        pen = ch.get_armor_dex_penalty()
        self.assertEqual((pen.dice, pen.pips), (1, 0))
        ch.worn_armor = "ubese_raider_armor"
        pen = ch.get_armor_dex_penalty()
        self.assertEqual((pen.dice, pen.pips), (0, 0))

    def test_v22_latent_bh_armor_penalty_now_live(self):
        # DicePool.parse("-1D") is (0,0) — signed penalty strings made
        # EVERY armor dex penalty a silent no-op since v22. The producer
        # now returns the magnitude (consumers subtract). Pin the
        # pre-existing item that proves the fix reaches old data.
        from engine.character import Character
        ch = Character()
        ch.worn_armor = "bounty_hunter_armor"
        pen = ch.get_armor_dex_penalty()
        self.assertEqual((pen.dice, pen.pips), (1, 0),
                         "BH Armor's -1D must finally apply")


class TestDropCFullLoop(unittest.TestCase):
    def test_crafted_landing_dict_wears(self):
        # The Drop A armor landing dict shape → carried_to_instance →
        # find_carried_gear(want_armor=True) → the exact path WearCommand
        # walks. This is the loop the mandate requires.
        from engine.items import carried_to_instance, find_carried_gear
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        landed = {
            "type": "armor", "key": "coynite_battle_armor",
            "name": "Coynite Battle Armor", "quality": 71.5,
            "condition": 100, "crafter": "Tester",
        }
        inst = carried_to_instance(landed)
        self.assertIsNotNone(inst)
        self.assertEqual(inst.key, "coynite_battle_armor")
        self.assertEqual(inst.quality, 71.5)

        idx, d, w = find_carried_gear([landed], "coynite", wr,
                                      want_armor=True)
        self.assertEqual(idx, 0)
        self.assertTrue(w.is_armor)
        # …and the same item must NOT match as a weapon.
        idx2, _, _ = find_carried_gear([landed], "coynite", wr,
                                       want_armor=False)
        self.assertIsNone(idx2)


class TestDropCTrainer(unittest.TestCase):
    NPC_FILE = REPO / "data" / "worlds" / "clone_wars" / \
        "npcs_drop_craft_c_armorer.yaml"

    def _npc(self):
        data = yaml.safe_load(self.NPC_FILE.read_text(encoding="utf-8"))
        return data["npcs"][0]

    def test_npc_file_loads_and_shape(self):
        npc = self._npc()
        self.assertEqual(npc["name"], "Sela Tarn")
        self.assertEqual(npc["room"], "Kayson's Weapon Shop")
        self.assertTrue(npc["ai_config"]["trainer"])
        self.assertIn("armor_repair", npc["ai_config"]["train_skills"])

    def test_room_exists_in_cw_world(self):
        tat = (REPO / "data" / "worlds" / "clone_wars" / "planets" /
               "tatooine.yaml").read_text(encoding="utf-8")
        self.assertIn("Kayson's Weapon Shop", tat)

    def test_era_loads_the_file(self):
        era = (REPO / "data" / "worlds" / "clone_wars" /
               "era.yaml").read_text(encoding="utf-8")
        self.assertIn("npcs_drop_craft_c_armorer.yaml", era)

    def test_all_ten_schematics_bound_to_her(self):
        sch = {s["key"]: s for s in _schematics()}
        for key in NEW_KEYS:
            self.assertEqual(sch[key]["trainer_npc"], "Sela Tarn", key)
            self.assertEqual(sch[key]["skill_required"], "armor_repair", key)
            self.assertEqual(sch[key]["output_type"], "armor", key)
            self.assertEqual(sch[key]["output_key"], key)

    def test_trainer_teach_name_match(self):
        # handle_trainer_teach matches trainer_npc against the talked-to
        # NPC name case-insensitively — pin the binding actually grants.
        from engine.crafting import add_known_schematic, \
            get_known_schematics, get_all_schematics
        import json
        char = {"attributes": json.dumps({})}
        granted = []
        for key, schem in get_all_schematics().items():
            if schem.get("trainer_npc", "").lower() == "sela tarn":
                if add_known_schematic(char, key):
                    granted.append(key)
        # Drop C binds all 10 armor schematics to Sela Tarn. Sela may teach MORE
        # over time (e.g. the powered exo-frame, CRAFT.powered_suit_design drop
        # 50), so assert the drop-C set is a SUBSET of what she grants, not an
        # exact match (which would drift on every new Sela schematic).
        self.assertTrue(set(NEW_KEYS).issubset(set(granted)),
                        f"Sela must teach all drop-C armor; missing "
                        f"{set(NEW_KEYS) - set(granted)}")
        self.assertTrue(set(NEW_KEYS).issubset(set(get_known_schematics(char))))

    def test_train_skill_resolves_post_drop1(self):
        from engine.character import SkillRegistry, canonical_skill_key
        reg = SkillRegistry()
        reg.load_file(str(REPO / "data" / "skills.yaml"))
        sd = reg.get(canonical_skill_key("armor_repair"))
        self.assertIsNotNone(sd)
        self.assertEqual(sd.attribute, "technical")


class TestDropCConventions(unittest.TestCase):
    def test_contraband_field_scope(self):
        # Drop C originally pinned that NO contraband field existed
        # "yet" — Drop G (2026-06-12) is the yet. The pin now guards
        # the field's SCOPE: exactly the black-market band carries it.
        flagged = sorted(s["key"] for s in _schematics()
                         if "contraband" in s)
        self.assertEqual(flagged, ["anti_vehicle_grenade",
                                   "disruptor_pistol", "predator_rifle"])

    def test_no_powered_suits_shipped(self):
        # §3.2 is deferred wholesale: no `powersuit` anything until its
        # design pass (operation skill + mount consumer).
        sch_keys = {s["key"] for s in _schematics()}
        wr_text = (REPO / "data" / "weapons.yaml").read_text(encoding="utf-8")
        self.assertFalse(any("powersuit" in k or "powered_armor" in k
                             for k in sch_keys))
        self.assertNotIn("powersuit_operation", wr_text)


if __name__ == "__main__":
    unittest.main()
