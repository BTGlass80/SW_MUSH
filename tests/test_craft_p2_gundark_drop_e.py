"""CRAFT.GUNDARK Drop E — field gear: the outfitter, the sink, the seam
(2026-06-11).

Three FIXES and two consumer-real items, per gundark plan §4/§8 Drop E:

  1. **Vek Nurren was a dangling trainer** — five existing gear
     schematics (cooling_unit, breath_mask, radiation_suit,
     anti_theft_alarm, water_canteen) named him and he was seeded
     NOWHERE: the whole survival-gear teaching loop was phantom. Seeded
     at Lup's General Store (density-directive co-location).
  2. **`uses` never decremented** — gear landed with uses/max_uses and
     no consumer touched them (radiation_suit's 10 uses were
     decorative). Mitigation gear with max_uses now SPENDS a use when
     it actually averts a hazard, in BOTH stores (db mirror + the live
     session dict the hazard tick re-reads), and is removed at zero.
  3. **anti_theft_alarm had no consumer** — urban_danger's mitigation
     list was empty. Wired; with max_uses: 1 it defeats exactly one
     pickpocket attempt.

New items ride consumers that exist: the **luma flare** (attack path +
Drop D single-use) and the **animal excluder** (a new post-pick aversion
seam in roll_encounter — creature-templated picks only, deterministic
under injected rng, cooldown still marks, flavor via the
"averted_by_excluder" reason).

Deferred with reasons (no consumer): med-aid/medkit (skill-modifier and
surgery-kit gating absent), rope/grapplers/line-throwers (climbing
modifiers), rations (no hunger), organic gill (no aquatic hazard),
automap/comlinks, conveyance packs (movement systems — design-pass
family), restraints (CRAFT.HOOK.restraints, standing).
"""
import asyncio
import json
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

VEK_SCHEMATICS = [
    "cooling_unit", "breath_mask", "radiation_suit", "anti_theft_alarm",
    "water_canteen", "luma_flare", "animal_excluder",
    # CRAFT.HOOK.restraints (drop 49, 2026-06-13): binders (stun-cuffs) are a
    # Security craft Vek Nurren teaches, like the anti-theft alarm. This roster
    # is a complete "what Vek grants" check, so the new schematic belongs here.
    "binders",
]


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


def _run(coro):
    # asyncio.run, not get_event_loop(): Python 3.14 (the Windows
    # suite's interpreter) removed implicit loop creation — the old
    # form raises RuntimeError outside a running loop.
    return asyncio.run(coro)


class FakeDB:
    """Just enough inventory surface for the consume path."""

    def __init__(self, items):
        self.items = list(items)
        self.removed = []
        self.added = []

    async def remove_from_inventory(self, char_id, key):
        for i, it in enumerate(self.items):
            if isinstance(it, dict) and it.get("key") == key:
                self.items.pop(i)
                self.removed.append(key)
                return True
        return False

    async def add_to_inventory(self, char_id, item):
        self.items.append(item)
        self.added.append(item)


# ──────────────────────────────────────────────────────────────────────
# 1. The trainer seed
# ──────────────────────────────────────────────────────────────────────

class TestVekNurrenSeed(unittest.TestCase):
    NPC_FILE = REPO / "data" / "worlds" / "clone_wars" / \
        "npcs_drop_craft_e_outfitter.yaml"

    def _npc(self):
        return yaml.safe_load(
            self.NPC_FILE.read_text(encoding="utf-8"))["npcs"][0]

    def test_seed_shape(self):
        npc = self._npc()
        self.assertEqual(npc["name"], "Vek Nurren")
        self.assertEqual(npc["room"], "Lup's General Store")
        self.assertTrue(npc["ai_config"]["trainer"])
        self.assertIn("survival", npc["ai_config"]["train_skills"])

    def test_room_exists_in_cw_world(self):
        tat = (REPO / "data" / "worlds" / "clone_wars" / "planets" /
               "tatooine.yaml").read_text(encoding="utf-8")
        self.assertIn("Lup's General Store", tat)

    def test_era_loads_the_file(self):
        era = (REPO / "data" / "worlds" / "clone_wars" /
               "era.yaml").read_text(encoding="utf-8")
        self.assertIn("npcs_drop_craft_e_outfitter.yaml", era)

    def test_all_vek_schematics_grant_on_talk(self):
        from engine.crafting import add_known_schematic, \
            get_known_schematics, get_all_schematics
        char = {"attributes": json.dumps({})}
        granted = []
        for key, schem in get_all_schematics().items():
            if schem.get("trainer_npc", "").lower() == "vek nurren":
                if add_known_schematic(char, key):
                    granted.append(key)
        self.assertEqual(sorted(granted), sorted(VEK_SCHEMATICS))
        self.assertEqual(sorted(get_known_schematics(char)),
                         sorted(VEK_SCHEMATICS))

    def test_distinct_from_venn_kator(self):
        # The near-collision in names is probably how the dangle
        # survived audits — pin that BOTH exist as distinct seeds.
        p1 = (REPO / "data" / "worlds" / "clone_wars" /
              "npcs_mos_eisley_population_p1.yaml").read_text(
            encoding="utf-8")
        self.assertIn("Venn Kator", p1)
        self.assertNotIn("Vek Nurren", p1)


# ──────────────────────────────────────────────────────────────────────
# 2. The consumption sink
# ──────────────────────────────────────────────────────────────────────

class TestMitigationConsumption(unittest.TestCase):
    def _char(self, items):
        return {"id": 7,
                "inventory": json.dumps({"items": items, "resources": []}),
                "equipment": "{}"}

    def test_multi_use_decrements_both_stores(self):
        from engine.hazards import _consume_mitigation_use
        item = {"type": "gear", "key": "radiation_suit",
                "name": "Radiation Shielding Suit",
                "uses": 10, "max_uses": 10}
        char = self._char([item])
        db = FakeDB([dict(item)])
        _run(_consume_mitigation_use(char, item, db))
        # db mirror: removed then re-added with 9 uses
        self.assertEqual(db.removed, ["radiation_suit"])
        self.assertEqual(db.added[0]["uses"], 9)
        # session-dict sync: the live char dict sees 9 too
        inv = json.loads(char["inventory"])
        self.assertEqual(inv["items"][0]["uses"], 9)

    def test_last_use_removes_from_both_stores(self):
        from engine.hazards import _consume_mitigation_use
        item = {"type": "gear", "key": "anti_theft_alarm",
                "name": "Anti-Theft Alarm", "uses": 1, "max_uses": 1}
        char = self._char([item])
        db = FakeDB([dict(item)])
        _run(_consume_mitigation_use(char, item, db))
        self.assertEqual(db.removed, ["anti_theft_alarm"])
        self.assertEqual(db.added, [])
        self.assertEqual(json.loads(char["inventory"])["items"], [])

    def test_durable_untouched(self):
        from engine.hazards import _consume_mitigation_use
        item = {"type": "gear", "key": "water_canteen",
                "name": "Water Canteen", "uses": 0, "max_uses": 0}
        char = self._char([item])
        db = FakeDB([dict(item)])
        _run(_consume_mitigation_use(char, item, db))
        self.assertEqual(db.removed, [])
        self.assertEqual(len(json.loads(char["inventory"])["items"]), 1)

    def test_find_matches_dict_and_legacy_shapes(self):
        from engine.hazards import _find_mitigation_item
        char = self._char([{"key": "breath_mask", "max_uses": 0}])
        src, item = _find_mitigation_item(char, ["breath_mask"])
        self.assertEqual(src, "inventory")
        self.assertEqual(item["key"], "breath_mask")
        # legacy bare-list inventory
        char2 = {"id": 8, "inventory": json.dumps(["breath_mask"]),
                 "equipment": "{}"}
        src2, item2 = _find_mitigation_item(char2, ["breath_mask"])
        self.assertEqual(src2, "inventory")
        self.assertEqual(item2, "breath_mask")  # string = durable by shape

    def test_fire_site_consumes_through_real_check(self):
        # End-to-end: a hazardous room + a 2-use mask → mitigated AND a
        # use spent, through check_hazard_for_character itself.
        import engine.hazards as hz
        hz._hazard_timers.clear()
        item = {"type": "gear", "key": "breath_mask",
                "name": "Breath Mask", "uses": 2, "max_uses": 2}
        char = self._char([item])
        db = FakeDB([dict(item)])
        room = {"id": 99, "properties": json.dumps(
            {"environment_hazard": {"type": "toxic_atmosphere",
                                    "severity": 1}})}
        res = _run(hz.check_hazard_for_character(char, room, db))
        self.assertTrue(res["mitigated"])
        self.assertEqual(json.loads(char["inventory"])["items"][0]["uses"], 1)
        hz._hazard_timers.clear()

    def test_urban_danger_consumes_the_alarm(self):
        from engine.hazards import HAZARD_TYPES
        self.assertEqual(HAZARD_TYPES["urban_danger"]["mitigation_items"],
                         ["anti_theft_alarm"])


# ──────────────────────────────────────────────────────────────────────
# 3. The excluder seam
# ──────────────────────────────────────────────────────────────────────

class _RNG:
    """Scripted rng: .random() pops from a queue; .randint() returns lo."""

    def __init__(self, randoms):
        self.q = list(randoms)

    def random(self):
        return self.q.pop(0)

    def randint(self, lo, hi):
        return lo


def _region_with(entry):
    from engine.wilderness_encounters import EncounterPool

    class _R:
        pass

    r = _R()
    r.width = 10
    r.height = 10
    r.encounter_pool = EncounterPool(
        base_chance_per_move=1.0, entries=[entry])
    return r


class TestAnimalExcluderSeam(unittest.TestCase):
    def setUp(self):
        import engine.wilderness_encounters as we
        we._encounter_cooldowns.clear()
        self.we = we

    def tearDown(self):
        self.we._encounter_cooldowns.clear()

    def _entry(self, etype="hostile", template="womp_rat"):
        from engine.wilderness_encounters import EncounterEntry
        payload = {"npc_template": template} if template else {}
        return EncounterEntry(id="e1", type=etype, weight=1,
                              payload=payload, narrative="A thing!")

    def _roll(self, entry, carried, randoms):
        return self.we.roll_encounter(
            _region_with(entry), new_x=5, new_y=5, terrain="dune_sea",
            char={"id": 42}, rng=_RNG(randoms), carried_keys=carried)

    def test_averted_with_excluder(self):
        # chance roll 0.0 fires; aversion roll 0.1 < 0.5 averts.
        res = self._roll(self._entry(), {"animal_excluder"}, [0.0, 0.1])
        self.assertFalse(res.fired)
        self.assertEqual(res.reason, "averted_by_excluder")
        # the animal approached and was repelled — cooldown marks.
        res2 = self._roll(self._entry(), {"animal_excluder"}, [0.0, 0.1])
        self.assertEqual(res2.reason, "on_cooldown")

    def test_fires_without_excluder(self):
        res = self._roll(self._entry(), None, [0.0])
        self.assertTrue(res.fired)
        self.assertEqual(res.entry.id, "e1")

    def test_aversion_roll_can_fail(self):
        res = self._roll(self._entry(), {"animal_excluder"}, [0.0, 0.9])
        self.assertTrue(res.fired)

    def test_non_creature_entries_unaffected(self):
        # A templateless flavor entry passes straight through even with
        # the device carried — it deters animals, not weather.
        res = self._roll(self._entry(etype="flavor", template=None),
                         {"animal_excluder"}, [0.0])
        self.assertTrue(res.fired)

    def test_caller_wires_the_seam(self):
        src = (REPO / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        self.assertIn("carried_keys=_carried_keys", code)
        self.assertIn('"averted_by_excluder"', code)


# ──────────────────────────────────────────────────────────────────────
# 4. The two new schematics + rows
# ──────────────────────────────────────────────────────────────────────

class TestDropESchematics(unittest.TestCase):
    def test_luma_flare_row(self):
        from engine.weapons import get_weapon_registry
        w = get_weapon_registry().get("luma_flare")
        self.assertEqual(w.damage, "4D")
        self.assertEqual(w.weapon_type, "grenade")
        self.assertTrue(w.single_use)
        self.assertEqual(w.cost, 100)

    def test_rubric_and_bindings(self):
        sch = {s["key"]: s for s in _schematics()}
        lf = sch["luma_flare"]
        self.assertEqual(lf["difficulty"], 14)   # 4D→12 + Avail2 +2
        self.assertEqual(lf["skill_required"], "demolitions")
        self.assertEqual(lf["trainer_npc"], "Vek Nurren")
        ae = sch["animal_excluder"]
        self.assertEqual(ae["difficulty"], 14)
        self.assertEqual(ae["output_type"], "gear")
        self.assertEqual(ae["trainer_npc"], "Vek Nurren")
        types = {c["type"] for c in ae["components"]}
        self.assertEqual(types, {"electronic", "composite"})
        for c in lf["components"] + ae["components"]:
            self.assertEqual(c["min_quality"], 40)

    def test_excluder_key_matches_seam_constant(self):
        from engine.wilderness_encounters import ANIMAL_EXCLUDER_KEY
        sch = {s["key"]: s for s in _schematics()}
        self.assertEqual(sch["animal_excluder"]["output_key"],
                         ANIMAL_EXCLUDER_KEY)


if __name__ == "__main__":
    unittest.main()
