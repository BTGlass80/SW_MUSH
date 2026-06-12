# -*- coding: utf-8 -*-
"""
tests/test_creature_special_attacks.py — Sourcebook Enrichment **Lane A tail**:
WEG creature special-attack mechanics (poison DoT + grapple/constriction
restraint).

Three layers, mirroring the project pattern:
  1. PURE — parsers (structured + prose fallback), deciders, factories, and a
     B3/Q1-cleanness scan over every player-facing string.
  2. HYDRATION — the spawn pipeline carries the riders end to end
     (build_creature_char_sheet → from_npc_sheet → Character.special_attack_*).
  3. COMBAT — the real CombatInstance round path: on-hit injection, the
     _cleanup poison/restraint ticks (deterministic via a pool-keyed roll
     stub), break-free resolution, grappler-gone cleanup, the flee block, and
     the held-attacker pool penalty.

The deterministic roll stub returns ``pool.dice*4 + pool.pips`` — a fixed,
pool-dependent total — so a 5D poison (20) beats a 2D Strength resist (8)
without any call-order coupling. Live spawn+combat over aiosqlite is the
Windows gate; the substance is pinned here.
"""
from __future__ import annotations

import unittest
from unittest import mock

from engine.character import Character, DicePool, SkillRegistry, WoundLevel
from engine.combat import CombatInstance, CombatAction, ActionType
from engine import creature_library as CL
from engine import creature_special_attacks as SA


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
_BANNED = [
    "imperial", "empire", "rebel", "rebellion", "stormtrooper", "tie ",
    "x-wing", "star destroyer", "moff", "palpatine", "vader", "sith",
    "dooku", "ventress", "grievous", "sidious", "maul", "clone trooper",
]


class _FixedRoll:
    def __init__(self, total): self.total = int(total)
    def display(self): return f"[{self.total}]"


def _det_roll(pool):
    """Deterministic, pool-dependent total: dice*4 + pips."""
    return _FixedRoll(pool.dice * 4 + pool.pips)


def _make_victim(name="Quarry", char_id=2, strength="2D", brawling="2D",
                 dex="2D"):
    c = Character(name=name, species_name="Human")
    c.id = char_id
    c.dexterity = DicePool.parse(dex)
    c.strength = DicePool.parse(strength)
    c.add_skill("brawling", DicePool.parse(brawling))
    return c


def _make_creature_actor(creature_id, char_id=101):
    """Build a creature Character through the real spawn pipeline so the
    special_attack riders are hydrated exactly as in production."""
    creature = CL.get_creature(creature_id)
    sheet = CL.build_creature_char_sheet(creature)
    return Character.from_npc_sheet(char_id, sheet)


def _skill_reg():
    """A registry with the real skills.yaml loaded — combat resolves brawling/
    running pools through it (an empty registry returns 0D for every skill)."""
    import os
    reg = SkillRegistry()
    path = os.path.join(os.path.dirname(__file__), "..", "data", "skills.yaml")
    if os.path.exists(path):
        reg.load_file(path)
    return reg


def _ci():
    return CombatInstance(room_id=1, skill_reg=_skill_reg())


# ══════════════════════════════════════════════════════════════════════════
# 1. PURE — parsers / deciders / factories / strings
# ══════════════════════════════════════════════════════════════════════════
class TestParsers(unittest.TestCase):
    def setUp(self):
        self.lib = CL.load_creature_library()

    def test_poison_structured_spor_crawler(self):
        p = SA.parse_poison(self.lib["spor_crawler"])
        self.assertIsNotNone(p)
        self.assertEqual(p.damage, "5D")
        self.assertEqual(p.rounds, 3)
        self.assertEqual(p.onset, 0)

    def test_poison_structured_hitcher_crab_slow_acting(self):
        p = SA.parse_poison(self.lib["hitcher_crab"])
        self.assertIsNotNone(p)
        self.assertEqual(p.damage, "2D+2")
        self.assertEqual(p.onset, 1)  # slow-acting → delayed first tick

    def test_restraint_structured_kinds(self):
        self.assertEqual(SA.parse_restraint(self.lib["glim_worm"]).kind, "grapple")
        self.assertEqual(SA.parse_restraint(self.lib["voroos"]).kind, "grapple")
        r = SA.parse_restraint(self.lib["stalker_lizard"])
        self.assertEqual(r.kind, "constriction")
        self.assertEqual(r.hold_damage, "STR+2D+2")
        self.assertTrue(r.is_escalating)
        c = SA.parse_restraint(self.lib["somago"])
        self.assertEqual(c.kind, "choke")
        self.assertEqual(c.hold_damage, "STR+3D")
        self.assertTrue(c.is_escalating)

    def test_plain_creatures_have_no_rider(self):
        for cid in ("worrt", "shredder_bat", "wrix", "winged_xendrite", "magus"):
            self.assertEqual(SA.parse_special_attacks(self.lib[cid]), {})
            self.assertFalse(SA.has_special_attack(self.lib[cid]))

    def test_grapple_not_escalating(self):
        self.assertFalse(SA.parse_restraint(self.lib["glim_worm"]).is_escalating)

    def test_prose_inference_fallback(self):
        """A creature authored with ONLY prose (no structured block) still
        yields a mechanic — the inference safety net."""
        prose_poison = {"natural_attack": {"damage": "Poison 4D"}}
        p = SA.parse_poison(prose_poison)
        self.assertIsNotNone(p)
        self.assertEqual(p.damage, "4D")

        prose_grab = {"natural_attack": {"name": "constriction", "damage": "STR+1D"}}
        r = SA.parse_restraint(prose_grab)
        self.assertEqual(r.kind, "constriction")
        self.assertEqual(r.hold_damage, "STR+1D")  # base dmg = the squeeze

        prose_choke = {"special": ["it chokes the victim"]}
        self.assertEqual(SA.parse_restraint(prose_choke).kind, "choke")

    def test_structured_beats_prose(self):
        """Structured block wins even if prose would infer differently."""
        creature = {
            "natural_attack": {"name": "constriction", "damage": "STR+5D"},
            "special_attack": {"restraint": {"kind": "grapple"}},
        }
        self.assertEqual(SA.parse_restraint(creature).kind, "grapple")


class TestDeciders(unittest.TestCase):
    def test_break_free_holder_wins_ties(self):
        self.assertTrue(SA.break_free_succeeds(11, 10))
        self.assertFalse(SA.break_free_succeeds(10, 10))   # tie → holder keeps
        self.assertFalse(SA.break_free_succeeds(9, 10))

    def test_resolve_damage_pool_str_form(self):
        str_pool = DicePool.parse("3D")
        pool = SA.resolve_damage_pool("STR+2D+2", str_pool)
        self.assertEqual((pool.dice, pool.pips), (5, 2))

    def test_resolve_damage_pool_bare_str(self):
        pool = SA.resolve_damage_pool("STR+3D", DicePool.parse("2D+1"))
        self.assertEqual((pool.dice, pool.pips), (5, 1))

    def test_resolve_damage_pool_absolute(self):
        pool = SA.resolve_damage_pool("5D", DicePool(0, 0))
        self.assertEqual((pool.dice, pool.pips), (5, 0))

    def test_resolve_damage_pool_empty(self):
        pool = SA.resolve_damage_pool("", DicePool.parse("4D"))
        self.assertEqual((pool.dice, pool.pips), (0, 0))

    def test_active_factories(self):
        ap = SA.make_active_poison({"damage": "5D", "rounds": 3, "onset": 1},
                                   source="Spor Crawler")
        self.assertEqual(ap["rounds_left"], 3)
        self.assertEqual(ap["onset_left"], 1)
        self.assertEqual(ap["source"], "Spor Crawler")

        ar = SA.make_active_restraint(
            {"kind": "constriction", "hold_damage": "STR+2D+2"},
            grappler_id=7, source="Stalker Lizard")
        self.assertEqual(ar["grappler_id"], 7)
        self.assertTrue(SA.restraint_is_escalating(ar))
        self.assertFalse(SA.restraint_is_escalating({"kind": "grapple"}))


class TestStringsClean(unittest.TestCase):
    def _all_strings(self):
        return [
            SA.poison_inflicted_line("Quarry", "Spor Crawler"),
            SA.poison_tick_line("Quarry", "wounded"),
            SA.poison_tick_line("Quarry", "no damage"),
            SA.poison_faded_line("Quarry"),
            SA.grabbed_line("Quarry", "Stalker Lizard", "constriction"),
            SA.grabbed_line("Quarry", "Glim Worm", "grapple"),
            SA.grabbed_line("Quarry", "Somago", "choke"),
            SA.squeeze_tick_line("Quarry", "constriction", "wounded"),
            SA.squeeze_tick_line("Quarry", "choke", "no damage"),
            SA.break_free_success_line("Quarry"),
            SA.break_free_fail_line("Quarry"),
            SA.restraint_released_line("Quarry"),
            SA.cannot_flee_grappled_line("Quarry"),
        ]

    def test_all_strings_b3_q1_clean(self):
        for s in self._all_strings():
            low = s.lower()
            for bad in _BANNED:
                self.assertNotIn(bad, low, f"banned {bad!r} in {s!r}")

    def test_strings_are_nonempty(self):
        for s in self._all_strings():
            self.assertTrue(s.strip())


# ══════════════════════════════════════════════════════════════════════════
# 2. HYDRATION — spawn pipeline carries the riders end to end
# ══════════════════════════════════════════════════════════════════════════
class TestHydration(unittest.TestCase):
    def test_sheet_includes_special_attack(self):
        sheet = CL.build_creature_char_sheet(CL.get_creature("spor_crawler"))
        self.assertIn("special_attack", sheet)
        self.assertEqual(sheet["special_attack"]["poison"]["damage"], "5D")

    def test_sheet_omits_for_plain_creature(self):
        sheet = CL.build_creature_char_sheet(CL.get_creature("worrt"))
        self.assertNotIn("special_attack", sheet)

    def test_from_npc_sheet_hydrates_poison(self):
        c = _make_creature_actor("spor_crawler")
        self.assertEqual(c.special_attack_poison.get("damage"), "5D")
        self.assertEqual(c.special_attack_restraint, {})

    def test_from_npc_sheet_hydrates_restraint(self):
        c = _make_creature_actor("stalker_lizard")
        self.assertEqual(c.special_attack_restraint.get("kind"), "constriction")
        self.assertEqual(c.special_attack_poison, {})

    def test_ordinary_character_has_empty_specs(self):
        c = _make_victim()
        self.assertEqual(c.special_attack_poison, {})
        self.assertEqual(c.special_attack_restraint, {})


# ══════════════════════════════════════════════════════════════════════════
# 3. COMBAT — on-hit injection
# ══════════════════════════════════════════════════════════════════════════
class TestOnHitInjection(unittest.TestCase):
    def test_hit_injects_poison(self):
        ci = _ci()
        actor = ci.add_combatant(_make_creature_actor("spor_crawler", 101))
        victim = ci.add_combatant(_make_victim(char_id=2))
        note = ci._apply_special_attack_on_hit(actor, victim)
        self.assertEqual(len(victim.poison_stacks), 1)
        self.assertEqual(victim.poison_stacks[0]["damage"], "5D")
        self.assertIn("envenom", note.lower())

    def test_hit_injects_restraint(self):
        ci = _ci()
        actor = ci.add_combatant(_make_creature_actor("glim_worm", 101))
        victim = ci.add_combatant(_make_victim(char_id=2))
        note = ci._apply_special_attack_on_hit(actor, victim)
        self.assertIsNotNone(victim.restraint)
        self.assertEqual(victim.restraint["kind"], "grapple")
        self.assertEqual(victim.restraint["grappler_id"], 101)
        self.assertTrue(note.strip())

    def test_repeat_grab_does_not_re_announce(self):
        ci = _ci()
        actor = ci.add_combatant(_make_creature_actor("glim_worm", 101))
        victim = ci.add_combatant(_make_victim(char_id=2))
        ci._apply_special_attack_on_hit(actor, victim)
        note2 = ci._apply_special_attack_on_hit(actor, victim)
        self.assertEqual(note2, "")  # already held by this grappler

    def test_ordinary_attacker_is_noop(self):
        ci = _ci()
        actor = ci.add_combatant(_make_victim("Soldier", char_id=1))
        victim = ci.add_combatant(_make_victim(char_id=2))
        note = ci._apply_special_attack_on_hit(actor, victim)
        self.assertEqual(note, "")
        self.assertEqual(victim.poison_stacks, [])
        self.assertIsNone(victim.restraint)


# ══════════════════════════════════════════════════════════════════════════
# 3. COMBAT — _cleanup poison tick
# ══════════════════════════════════════════════════════════════════════════
class TestPoisonTick(unittest.TestCase):
    def test_poison_tick_wounds_and_decrements(self):
        ci = _ci()
        victim = ci.add_combatant(_make_victim(char_id=2, strength="2D"))
        victim.poison_stacks = [SA.make_active_poison(
            {"damage": "5D", "rounds": 3, "onset": 0}, source="Spor Crawler")]
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            ci._cleanup()
        self.assertGreater(victim.char.wound_level.value, WoundLevel.HEALTHY.value)
        self.assertEqual(victim.poison_stacks[0]["rounds_left"], 2)

    def test_onset_delays_first_tick(self):
        ci = _ci()
        victim = ci.add_combatant(_make_victim(char_id=2, strength="6D"))
        victim.poison_stacks = [SA.make_active_poison(
            {"damage": "5D", "rounds": 2, "onset": 1}, source="Hitcher Crab")]
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            ci._cleanup()
        # onset consumed, rounds untouched
        self.assertEqual(victim.poison_stacks[0]["onset_left"], 0)
        self.assertEqual(victim.poison_stacks[0]["rounds_left"], 2)

    def test_poison_expires_and_announces(self):
        ci = _ci()
        # high STR → each tick is harmless, so the victim survives all rounds
        victim = ci.add_combatant(_make_victim(char_id=2, strength="6D"))
        victim.poison_stacks = [SA.make_active_poison(
            {"damage": "5D", "rounds": 1, "onset": 0}, source="Spor Crawler")]
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            events = ci._cleanup()
        self.assertEqual(victim.poison_stacks, [])
        self.assertTrue(any("runs its course" in e.text for e in events))


# ══════════════════════════════════════════════════════════════════════════
# 3. COMBAT — _cleanup restraint tick
# ══════════════════════════════════════════════════════════════════════════
class TestRestraintTick(unittest.TestCase):
    def test_constriction_squeezes_and_holds(self):
        ci = _ci()
        grappler = ci.add_combatant(_make_creature_actor("stalker_lizard", 101))
        # victim: high enough STR to survive the squeeze, low brawling to lose break-free
        victim = ci.add_combatant(_make_victim(char_id=2, strength="4D", brawling="2D"))
        victim.restraint = SA.make_active_restraint(
            grappler.char.special_attack_restraint, grappler_id=101,
            source="Stalker Lizard")
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            events = ci._cleanup()
        self.assertGreater(victim.char.wound_level.value, WoundLevel.HEALTHY.value)
        self.assertIsNotNone(victim.restraint)  # lost the break-free, still held
        self.assertTrue(any("constriction" in e.text for e in events))

    def test_break_free_success_clears_hold(self):
        ci = _ci()
        grappler = ci.add_combatant(_make_creature_actor("glim_worm", 101))
        # strong brawler easily wins the opposed break-free
        victim = ci.add_combatant(_make_victim(char_id=2, strength="3D", brawling="6D"))
        victim.restraint = SA.make_active_restraint(
            grappler.char.special_attack_restraint, grappler_id=101,
            source="Glim Worm")
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            events = ci._cleanup()
        self.assertIsNone(victim.restraint)
        self.assertTrue(any("wrenches free" in e.text for e in events))

    def test_grappler_gone_releases_hold(self):
        ci = _ci()
        victim = ci.add_combatant(_make_victim(char_id=2, brawling="2D"))
        victim.restraint = SA.make_active_restraint(
            {"kind": "grapple"}, grappler_id=999, source="Glim Worm")  # no such combatant
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            events = ci._cleanup()
        self.assertIsNone(victim.restraint)
        self.assertTrue(any("goes slack" in e.text for e in events))

    def test_downed_victim_does_not_get_squeezed(self):
        ci = _ci()
        grappler = ci.add_combatant(_make_creature_actor("stalker_lizard", 101))
        victim = ci.add_combatant(_make_victim(char_id=2, strength="3D"))
        victim.char.wound_level = WoundLevel.INCAPACITATED  # cannot act
        victim.restraint = SA.make_active_restraint(
            grappler.char.special_attack_restraint, grappler_id=101,
            source="Stalker Lizard")
        with mock.patch("engine.combat.roll_d6_pool", _det_roll):
            events = ci._cleanup()
        # hold persists (grappler present) but no squeeze/break-free fired
        self.assertIsNotNone(victim.restraint)
        self.assertFalse(any("constriction" in e.text for e in events))


# ══════════════════════════════════════════════════════════════════════════
# 3. COMBAT — flee block + held-attacker penalty
# ══════════════════════════════════════════════════════════════════════════
class TestRestraintActionEffects(unittest.TestCase):
    def test_flee_blocked_while_restrained(self):
        ci = _ci()
        actor = ci.add_combatant(_make_victim("Captive", char_id=1, brawling="2D"))
        ci.add_combatant(_make_creature_actor("glim_worm", 101))
        actor.restraint = SA.make_active_restraint(
            {"kind": "grapple"}, grappler_id=101, source="Glim Worm")
        action = CombatAction(action_type=ActionType.FLEE, skill="running")
        res = ci._resolve_flee(actor, action, num_actions=1)
        self.assertFalse(res.success)
        self.assertIn("held fast", res.narrative.lower())

    def test_held_attacker_gets_pool_penalty(self):
        ci = _ci()
        actor = ci.add_combatant(_make_victim("Captive", char_id=1,
                                              strength="3D", brawling="4D"))
        ci.add_combatant(_make_creature_actor("glim_worm", 101))
        actor.restraint = SA.make_active_restraint(
            {"kind": "grapple"}, grappler_id=101, source="Glim Worm")

        recorded = []
        real = __import__("engine.dice", fromlist=["apply_wound_penalty"]).apply_wound_penalty

        def _spy(pool, dice):
            recorded.append(dice)
            return real(pool, dice)

        action = CombatAction(action_type=ActionType.ATTACK, skill="brawling",
                              target_id=101)
        with mock.patch("engine.combat.apply_wound_penalty", _spy):
            ci._resolve_attack(actor, action, num_actions=1)
        self.assertIn(SA.GRAPPLE_ATTACK_PENALTY_DICE, recorded)

    def test_unheld_attacker_no_penalty(self):
        ci = _ci()
        actor = ci.add_combatant(_make_victim("Free", char_id=1,
                                              strength="3D", brawling="4D"))
        ci.add_combatant(_make_creature_actor("glim_worm", 101))  # not grabbing

        recorded = []
        real = __import__("engine.dice", fromlist=["apply_wound_penalty"]).apply_wound_penalty

        def _spy(pool, dice):
            recorded.append(dice)
            return real(pool, dice)

        action = CombatAction(action_type=ActionType.ATTACK, skill="brawling",
                              target_id=101)
        with mock.patch("engine.combat.apply_wound_penalty", _spy):
            ci._resolve_attack(actor, action, num_actions=1)
        self.assertNotIn(SA.GRAPPLE_ATTACK_PENALTY_DICE, recorded)


if __name__ == "__main__":
    unittest.main()
