"""CRAFT.GUNDARK Drop G — the lane finale: tuition, contraband, the
black market (2026-06-12).

Per decisions CRAFT.schematic_tuition=a (2026-06-12), 3a, and (a)=b:

  • **Tuition (a):** trainer recipes cost 50% of base_cost, min 50 cr,
    charged via adjust_credits tag "schematic_tuition" (a real sink).
    The old grant-the-whole-catalog-free-on-talk behavior is replaced:
    talk grants the trainer's CHEAPEST recipe free once per character
    ("first lesson's on the house" — the tutorial-chain safety, kept as
    diegesis even though no chain turned out to depend on it), lists
    the rest with prices, and the new `learn <name>` command buys them
    one at a time. PC-to-PC teaching (TeachCommand) stays free,
    untouched, pinned.
  • **Contraband (3a):** schematic `contraband: true` flags the LANDED
    item (weapon and gear branches), and the scan hook ships WITH the
    first contraband recipe: patrol boardings (engine/encounter_patrol
    comply path) sweep carried inventory — Con 15 to hide; a failed
    hide means CONFISCATION + a Class-4 infraction.
  • **The black-market band:** disruptor_pistol (6D+2, diff 24),
    predator_rifle (7D, diff capped at Heroic 26), anti_vehicle_grenade
    (7D single-use, 26) — q70, all contraband, taught by **Gundark**
    himself (the catalog's in-fiction compiler), dealing from the Nar
    Shaddaa Undercity Market.
  • **Resolved exclusions, pinned:** thermal_detonator stays
    uncraftable (the X-class icon's mystique — Drop D's pin stands);
    Firegems are natural gems, not recipes (plot device, logged); the
    heavy disruptor (book quirk: weaker than standard), pulse rifle
    (cone-primary unmodeled), and plot-artifact-priced X espionage
    devices stay out.
"""
import asyncio
import json
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

G_KEYS = ["disruptor_pistol", "predator_rifle", "anti_vehicle_grenade"]


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


def _run(coro):
    return asyncio.run(coro)


def _stripped(path):
    src = (REPO / path).read_text(encoding="utf-8")
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))


class FakeSession:
    def __init__(self, char):
        self.character = char
        self.lines = []

    async def send_line(self, line):
        self.lines.append(line)


class FakeDB:
    def __init__(self, npcs=None, inventory=None):
        self.npcs = npcs or []
        self.inventory = list(inventory or [])
        self.credit_calls = []
        self.removed = []

    async def get_npcs_in_room(self, room_id):
        return self.npcs

    async def adjust_credits(self, char_id, delta, tag):
        self.credit_calls.append((char_id, delta, tag))
        self._balance = getattr(self, "_balance", 0) + delta
        return self._balance

    async def save_character(self, char_id, **kw):
        return None

    async def get_inventory(self, char_id):
        return self.inventory

    async def remove_from_inventory(self, char_id, key):
        for i, it in enumerate(self.inventory):
            if isinstance(it, dict) and it.get("key") == key:
                self.inventory.pop(i)
                self.removed.append(key)
                return True
        return False


class FakeCtx:
    def __init__(self, char, db, args=""):
        self.session = FakeSession(char)
        self.db = db
        self.args = args


def _char(credits=10_000):
    return {"id": 5, "name": "Tester", "room_id": 1,
            "credits": credits, "attributes": json.dumps({}),
            "skills": "{}", "inventory": "[]", "equipment": "{}"}


# ──────────────────────────────────────────────────────────────────────
# 1. Tuition math + the reworked talk flow
# ──────────────────────────────────────────────────────────────────────

class TestTuitionMath(unittest.TestCase):
    def test_half_base_floor_fifty(self):
        from engine.crafting import schematic_tuition
        self.assertEqual(schematic_tuition({"base_cost": 3000}), 1500)
        self.assertEqual(schematic_tuition({"base_cost": 100}), 50)
        self.assertEqual(schematic_tuition({"base_cost": 50}), 50)
        self.assertEqual(schematic_tuition({"base_cost": 0}), 50)
        self.assertEqual(schematic_tuition({}), 50)


class TestTalkFlow(unittest.TestCase):
    def test_first_talk_grants_only_cheapest_free(self):
        from parser.crafting_commands import handle_trainer_teach
        from engine.crafting import get_known_schematics
        char = _char()
        ctx = FakeCtx(char, FakeDB())
        _run(handle_trainer_teach(ctx, "Vek Nurren"))
        known = get_known_schematics(char)
        # Vek's cheapest is water_canteen (50 cr)
        self.assertEqual(known, ["water_canteen"])
        out = "\n".join(ctx.session.lines)
        self.assertIn("on the house", out)
        self.assertIn("learn <name>", out)
        # priced listing present for a known non-free recipe
        self.assertIn("Radiation", out)

    def test_second_talk_grants_nothing_more(self):
        from parser.crafting_commands import handle_trainer_teach
        from engine.crafting import get_known_schematics
        char = _char()
        _run(handle_trainer_teach(FakeCtx(char, FakeDB()), "Vek Nurren"))
        _run(handle_trainer_teach(FakeCtx(char, FakeDB()), "Vek Nurren"))
        self.assertEqual(get_known_schematics(char), ["water_canteen"])


# ──────────────────────────────────────────────────────────────────────
# 2. The learn command
# ──────────────────────────────────────────────────────────────────────

class TestLearnCommand(unittest.TestCase):
    def _learn(self, char, db, arg):
        from parser.crafting_commands import LearnCommand
        ctx = FakeCtx(char, db, args=arg)
        _run(LearnCommand().execute(ctx))
        return ctx

    def _spend_free(self, char):
        # burn the trainer's free lesson via talk
        from parser.crafting_commands import handle_trainer_teach
        _run(handle_trainer_teach(FakeCtx(char, FakeDB()), "Vek Nurren"))

    def test_learn_charges_tuition_and_grants(self):
        from engine.crafting import get_known_schematics
        char = _char(credits=10_000)
        self._spend_free(char)
        db = FakeDB(npcs=[{"name": "Vek Nurren"}])
        ctx = self._learn(char, db, "radiation_suit")
        self.assertIn("radiation_suit", get_known_schematics(char))
        # radiation_suit base_cost is 800 → tuition 400 (recompute live)
        from engine.crafting import get_all_schematics, schematic_tuition
        want = schematic_tuition(get_all_schematics()["radiation_suit"])
        self.assertEqual(db.credit_calls,
                         [(5, -want, "schematic_tuition")])
        out = "\n".join(ctx.session.lines)
        self.assertIn("You pay", out)

    def test_insufficient_credits_refused(self):
        from engine.crafting import get_known_schematics
        char = _char(credits=10)
        self._spend_free(char)
        db = FakeDB(npcs=[{"name": "Vek Nurren"}])
        self._learn(char, db, "radiation_suit")
        self.assertNotIn("radiation_suit", get_known_schematics(char))
        self.assertEqual(db.credit_calls, [])

    def test_trainer_must_be_present(self):
        from engine.crafting import get_known_schematics
        char = _char()
        self._spend_free(char)
        db = FakeDB(npcs=[])  # empty room
        ctx = self._learn(char, db, "radiation_suit")
        self.assertNotIn("radiation_suit", get_known_schematics(char))
        self.assertIn("isn't here", "\n".join(ctx.session.lines))

    def test_learn_can_be_the_free_lesson(self):
        # Skipping talk and going straight to learn: the first lesson
        # from that trainer is still free.
        from engine.crafting import get_known_schematics
        char = _char(credits=0)
        db = FakeDB(npcs=[{"name": "Vek Nurren"}])
        ctx = self._learn(char, db, "water_canteen")
        self.assertIn("water_canteen", get_known_schematics(char))
        self.assertEqual(db.credit_calls, [])
        self.assertIn("on the house", "\n".join(ctx.session.lines))

    def test_pc_teach_stays_free(self):
        # Decision a: PC-to-PC teaching is free — TeachCommand must not
        # reference tuition or charge credits.
        import inspect
        from parser.crafting_commands import TeachCommand
        src = inspect.getsource(TeachCommand)
        self.assertNotIn("schematic_tuition", src)
        self.assertNotIn("adjust_credits", src)


# ──────────────────────────────────────────────────────────────────────
# 3. Contraband: landing flags + the patrol sweep
# ──────────────────────────────────────────────────────────────────────

class TestContraband(unittest.TestCase):
    def test_landing_branches_flag_contraband(self):
        code = _stripped("parser/crafting_commands.py")
        self.assertIn('item_dict["contraband"] = True', code)
        self.assertIn('gear_item["contraband"] = True', code)

    def test_carried_sweep_finds_flagged_only(self):
        from engine.encounter_patrol import _carried_contraband
        db = FakeDB(inventory=[
            {"key": "disruptor_pistol", "name": "Disruptor Pistol",
             "contraband": True},
            {"key": "water_canteen", "name": "Water Canteen"},
            "legacy_string",
        ])
        names = _run(_carried_contraband(db, 5))
        self.assertEqual(names, ["Disruptor Pistol"])

    def test_comply_branch_confiscates_class4(self):
        code = _stripped("engine/encounter_patrol.py")
        self.assertIn("_carried_contraband(db, char_id)", code)
        self.assertIn('"Restricted goods on person"', code)
        idx = code.index("Restricted goods on person")
        window = code[idx - 1600:idx + 200]
        self.assertIn("remove_from_inventory", window)
        self.assertIn("inf_class=4", window)


# ──────────────────────────────────────────────────────────────────────
# 4. The black-market roster + Gundark
# ──────────────────────────────────────────────────────────────────────

class TestBlackMarketRoster(unittest.TestCase):
    EXPECTED = {
        # key: (diff, base_cost, damage, craft_skill)
        "disruptor_pistol": (24, 3000, "6D+2", "blaster_repair"),
        "predator_rifle": (26, 7000, "7D", "blaster_repair"),
        "anti_vehicle_grenade": (26, 750, "7D", "demolitions"),
    }

    def test_rows(self):
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        for key, (_, cost, dmg, _s) in self.EXPECTED.items():
            w = wr.get(key)
            self.assertIsNotNone(w, key)
            self.assertEqual(w.damage, dmg, key)
            self.assertEqual(w.cost, cost, key)
        self.assertTrue(wr.get("anti_vehicle_grenade").single_use)
        self.assertFalse(wr.get("disruptor_pistol").single_use)

    def test_schematics_rubric_and_band(self):
        sch = {s["key"]: s for s in _schematics()}
        for key, (diff, cost, _d, skill) in self.EXPECTED.items():
            s = sch[key]
            self.assertEqual(s["difficulty"], diff, key)
            self.assertLessEqual(s["difficulty"], 26, key)  # Heroic cap
            self.assertEqual(s["base_cost"], cost, key)
            self.assertEqual(s["skill_required"], skill, key)
            self.assertEqual(s["trainer_npc"], "Gundark", key)
            self.assertTrue(s.get("contraband"), key)
            for c in s["components"]:
                self.assertEqual(c["min_quality"], 70, key)

    def test_tuition_on_the_band(self):
        from engine.crafting import schematic_tuition
        sch = {s["key"]: s for s in _schematics()}
        self.assertEqual(schematic_tuition(sch["disruptor_pistol"]), 1500)
        self.assertEqual(schematic_tuition(sch["predator_rifle"]), 3500)
        self.assertEqual(schematic_tuition(sch["anti_vehicle_grenade"]), 375)

    def test_resolved_exclusions(self):
        keys = {s["key"] for s in _schematics()}
        self.assertNotIn("thermal_detonator", keys)
        for absent in ("heavy_disruptor", "pulse_rifle",
                       "lowickan_firegem", "master_coder_chip",
                       "voice_box", "electronic_lock_breaker"):
            self.assertFalse(any(absent in k for k in keys), absent)


class TestGundarkSeed(unittest.TestCase):
    NPC_FILE = REPO / "data" / "worlds" / "clone_wars" / \
        "npcs_drop_craft_g_gundark.yaml"

    def test_seed_shape(self):
        npc = yaml.safe_load(
            self.NPC_FILE.read_text(encoding="utf-8"))["npcs"][0]
        self.assertEqual(npc["name"], "Gundark")
        self.assertEqual(npc["room"], "Nar Shaddaa - Undercity Market")
        self.assertTrue(npc["ai_config"]["trainer"])

    def test_room_exists(self):
        nar = (REPO / "data" / "worlds" / "clone_wars" / "planets" /
               "nar_shaddaa.yaml").read_text(encoding="utf-8")
        self.assertIn("Nar Shaddaa - Undercity Market", nar)

    def test_era_loads_the_file(self):
        era = (REPO / "data" / "worlds" / "clone_wars" /
               "era.yaml").read_text(encoding="utf-8")
        self.assertIn("npcs_drop_craft_g_gundark.yaml", era)

    def test_binding_grants(self):
        from engine.crafting import add_known_schematic, get_all_schematics
        char = {"attributes": json.dumps({})}
        granted = set()
        for key, schem in get_all_schematics().items():
            if schem.get("trainer_npc", "").lower() == "gundark":
                if add_known_schematic(char, key):
                    granted.add(key)
        self.assertEqual(granted, set(G_KEYS))


if __name__ == "__main__":
    unittest.main()
