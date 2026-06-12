# -*- coding: utf-8 -*-
"""
tests/test_drop4a2_sense_powers.py — Drop 4a.2 (2026-06-04)

Builds on the Drop 4a effect-application substrate. Four further Sense
powers (all light; dark_side=False):

  - telepathy   : mind-to-mind. Between two PCs sharing an active
                  Master-Padawan bond it is a deep communion across
                  distance (reports the partner's condition); otherwise a
                  wordless mind-touch offered to the other player to RP, or
                  a skim of an NPC's surface thoughts.
  - sense_lie   : reveals whether an NPC conceals something (reads real
                  deception / hidden-intent flags); a PC is offered the read.
  - farseeing   : a simple portent tied to real nearby danger (rich,
                  scripted visions are tracked for a later wave — G5).
  - danger_sense: in combat, a one-shot initiative reroll keeping the
                  better result; out of combat, an early warning.

Engine signals are tested deterministically; the parser appliers are
driven directly with synthetic successful results; the combat reroll is
tested with a patched RNG so "keep the better" is an exact assertion.
"""
import asyncio
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.character import Character, SkillRegistry  # noqa: E402
from engine import force_powers as fp  # noqa: E402
from engine.force_powers import POWERS, ForcePowerResult  # noqa: E402
import engine.combat as cb  # noqa: E402
import parser.force_commands as fc  # noqa: E402
import parser.combat_commands as cc  # noqa: E402

_SR = SkillRegistry()
_SR.load_file(os.path.join(PROJECT_ROOT, "data", "skills.yaml"))


def _caster(name="Jedi"):
    return Character.from_db_dict({
        "id": 1, "name": name, "room_id": 10,
        "attributes": json.dumps({"sense": "5D", "perception": "3D"}),
        "skills": "{}",
    })


def _run(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════════
# ENGINE — power table + resolver signals
# ══════════════════════════════════════════════════════════════════════════

class TestNewSensePowers(unittest.TestCase):
    NEW = ("telepathy", "sense_lie", "farseeing", "danger_sense")

    def test_all_present_and_light(self):
        for k in self.NEW:
            self.assertIn(k, POWERS)
            self.assertFalse(POWERS[k].dark_side, f"{k} must be light (no DSP)")

    def test_power_count_is_thirteen(self):
        # 9 after Drop 4a + 4 new = 13.
        self.assertEqual(len(POWERS), 13)

    def test_all_sense_based(self):
        for k in self.NEW:
            self.assertEqual(POWERS[k].skills, ["sense"])

    def _blank(self, key):
        return ForcePowerResult(power=POWERS[key], success=True, roll=20,
                                difficulty=10, margin=10, narrative="")

    def test_telepathy_signal(self):
        r = self._blank("telepathy")
        fp._resolve_telepathy(r, _caster(), _caster("Other"), 8, [])
        self.assertEqual(r.effect_kind, "telepathy")

    def test_sense_lie_signal(self):
        r = self._blank("sense_lie")
        fp._resolve_sense_lie(r, _caster(), _caster("Other"), 8, [])
        self.assertEqual(r.effect_kind, "sense_lie")

    def test_farseeing_signal(self):
        r = self._blank("farseeing")
        fp._resolve_farseeing(r, _caster(), [])
        self.assertEqual(r.effect_kind, "farseeing")

    def test_danger_sense_signal(self):
        r = self._blank("danger_sense")
        fp._resolve_danger_sense(r, _caster(), [])
        self.assertEqual(r.effect_kind, "danger_sense")


# ══════════════════════════════════════════════════════════════════════════
# COMBAT — danger_sense initiative reroll keeps the better result
# ══════════════════════════════════════════════════════════════════════════

class _Roll:
    def __init__(self, total):
        self.total = total

    def display(self):
        return str(self.total)


class TestInitiativeReroll(unittest.TestCase):
    def _combat_with_one(self, reroll):
        char = Character.from_db_dict({
            "id": 1, "name": "Jedi", "room_id": 10,
            "attributes": json.dumps({"perception": "3D"}),
            "skills": "{}", "wound_level": 0})
        combat = cb.CombatInstance(10, _SR)
        cbt = cb.Combatant(id=1, name="Jedi", char=char)
        cbt.initiative_reroll = reroll
        combat.combatants[1] = cbt
        return combat, cbt

    def test_reroll_keeps_higher_second(self):
        seq = [_Roll(5), _Roll(11)]  # first 5, reroll 11 -> keep 11
        orig = cb.roll_d6_pool
        cb.roll_d6_pool = lambda pool: seq.pop(0)
        try:
            combat, cbt = self._combat_with_one(reroll=True)
            combat.roll_initiative()
        finally:
            cb.roll_d6_pool = orig
        self.assertEqual(cbt.initiative, 11)
        self.assertFalse(cbt.initiative_reroll, "flag must be consumed")

    def test_reroll_keeps_higher_first(self):
        seq = [_Roll(11), _Roll(5)]  # first 11, reroll 5 -> keep 11
        orig = cb.roll_d6_pool
        cb.roll_d6_pool = lambda pool: seq.pop(0)
        try:
            combat, cbt = self._combat_with_one(reroll=True)
            combat.roll_initiative()
        finally:
            cb.roll_d6_pool = orig
        self.assertEqual(cbt.initiative, 11)
        self.assertFalse(cbt.initiative_reroll)

    def test_no_reroll_single_roll(self):
        seq = [_Roll(7)]  # only one roll consumed when flag is False
        orig = cb.roll_d6_pool
        cb.roll_d6_pool = lambda pool: seq.pop(0)
        try:
            combat, cbt = self._combat_with_one(reroll=False)
            combat.roll_initiative()
        finally:
            cb.roll_d6_pool = orig
        self.assertEqual(cbt.initiative, 7)
        self.assertEqual(seq, [], "exactly one roll should be consumed")
        self.assertFalse(cbt.initiative_reroll)


# ══════════════════════════════════════════════════════════════════════════
# PARSER — fakes
# ══════════════════════════════════════════════════════════════════════════

class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, line=""):
        self.sent.append(line)


class _FakeSessionMgr:
    def __init__(self, by_char=None):
        self._by_char = by_char or {}

    def find_by_character(self, char_id):
        return self._by_char.get(char_id)

    async def broadcast_to_room(self, *a, **k):
        pass


class _FakeDB:
    def __init__(self, pcs=None, npcs=None, bonds=None):
        self._pcs = pcs or []
        self._npcs = npcs or []
        self._bonds = bonds or {}  # padawan_id -> bond row

    async def get_characters_in_room(self, room_id, source_char=None):
        return [c for c in self._pcs if c.get("room_id") == room_id]

    async def get_npcs_in_room(self, room_id):
        return [n for n in self._npcs if n.get("room_id") == room_id]

    async def get_active_bond_for_padawan(self, padawan_id):
        return self._bonds.get(padawan_id)


def _ctx(session, db, mgr):
    from parser.commands import CommandContext
    return CommandContext(session=session, raw_input="force", command="force",
                          args="", args_list=[], db=db, session_mgr=mgr)


def _result(kind):
    return ForcePowerResult(power=POWERS.get(kind if kind in POWERS else "telepathy"),
                            success=True, roll=20, difficulty=10, margin=8,
                            narrative="", effect_kind=kind)


# ══════════════════════════════════════════════════════════════════════════
# PARSER — telepathy (bond-aware)
# ══════════════════════════════════════════════════════════════════════════

class TestTelepathyApplier(unittest.TestCase):
    def _target_obj(self):
        return Character.from_db_dict({
            "id": 2, "name": "Padawan", "attributes": "{}", "skills": "{}",
            "wound_level": 0})

    def test_bonded_pcs_get_communion(self):
        caster = {"id": 1, "name": "Master", "room_id": 10}
        target = {"id": 2, "name": "Padawan", "room_id": 10}
        # target (2) is the padawan, caster (1) the master.
        bonds = {2: {"master_char_id": 1, "padawan_char_id": 2,
                     "bond_status": "active"}}
        tgt_sess = _FakeSession(target)
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(bonds=bonds), _FakeSessionMgr(by_char={2: tgt_sess}))
        _run(fc._apply_telepathy(ctx, _result("telepathy"), caster, target,
                                 self._target_obj(), target_is_npc=False))
        joined = "\n".join(sess.sent)
        self.assertIn("bond", joined.lower())
        self.assertTrue(any("bond" in s.lower() for s in tgt_sess.sent))

    def test_unbonded_pc_is_offered(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        target = {"id": 2, "name": "Stranger", "room_id": 10}
        tgt_sess = _FakeSession(target)
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(bonds={}), _FakeSessionMgr(by_char={2: tgt_sess}))
        _run(fc._apply_telepathy(ctx, _result("telepathy"), caster, target,
                                 self._target_obj(), target_is_npc=False))
        self.assertTrue(any("wordless" in s.lower() for s in tgt_sess.sent))
        self.assertTrue(any("reach toward" in s.lower() for s in sess.sent))

    def test_npc_surface_thoughts(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        npc = {"id": 50, "name": "Mook", "room_id": 10,
               "char_sheet_json": json.dumps({"secret": "the boss is bluffing"})}
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
        _run(fc._apply_telepathy(ctx, _result("telepathy"), caster, npc,
                                 None, target_is_npc=True))
        self.assertTrue(any("boss is bluffing" in s for s in sess.sent))


# ══════════════════════════════════════════════════════════════════════════
# PARSER — sense_lie
# ══════════════════════════════════════════════════════════════════════════

class TestSenseLieApplier(unittest.TestCase):
    def test_deceptive_npc_revealed(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        liar = {"id": 50, "name": "Crook", "room_id": 10,
                "char_sheet_json": json.dumps(
                    {"true_intent": "he plans to double-cross you"})}
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
        _run(fc._apply_sense_lie(ctx, _result("sense_lie"), caster, liar,
                                 None, target_is_npc=True))
        joined = "\n".join(sess.sent)
        self.assertIn("hiding something", joined)
        self.assertIn("double-cross", joined)

    def test_honest_npc(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        honest = {"id": 51, "name": "Farmer", "room_id": 10,
                  "char_sheet_json": "{}"}
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
        _run(fc._apply_sense_lie(ctx, _result("sense_lie"), caster, honest,
                                 None, target_is_npc=True))
        self.assertTrue(any("no deceit" in s for s in sess.sent))

    def test_pc_is_offered(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        target = {"id": 2, "name": "Lando", "room_id": 10}
        tgt_sess = _FakeSession(target)
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr(by_char={2: tgt_sess}))
        _run(fc._apply_sense_lie(ctx, _result("sense_lie"), caster, target,
                                 None, target_is_npc=False))
        self.assertTrue(any("sincerity" in s.lower() for s in tgt_sess.sent))


# ══════════════════════════════════════════════════════════════════════════
# PARSER — farseeing
# ══════════════════════════════════════════════════════════════════════════

class TestFarseeingApplier(unittest.TestCase):
    def test_danger_vision_with_hostile(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        npcs = [{"id": 50, "name": "Raider", "room_id": 10,
                 "ai_config_json": json.dumps({"hostile": True})}]
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(npcs=npcs), _FakeSessionMgr())
        _run(fc._apply_farseeing(ctx, caster))
        self.assertTrue(any("danger close" in s.lower() for s in sess.sent))

    def test_calm_vision(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        npcs = [{"id": 51, "name": "Vendor", "room_id": 10, "ai_config_json": "{}"}]
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(npcs=npcs), _FakeSessionMgr())
        _run(fc._apply_farseeing(ctx, caster))
        self.assertTrue(any("quiet" in s.lower() for s in sess.sent))


# ══════════════════════════════════════════════════════════════════════════
# PARSER — danger_sense applier sets the combatant flag (via _ensure_in_combat)
# ══════════════════════════════════════════════════════════════════════════

class TestDangerSenseApplier(unittest.TestCase):
    def test_sets_reroll_in_combat(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        fake_cbt = cb.Combatant(id=1, name="Jedi")
        orig = cc._ensure_in_combat
        cc._ensure_in_combat = lambda char: (object(), fake_cbt)
        try:
            sess = _FakeSession(caster)
            ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
            _run(fc._apply_danger_sense(ctx, caster))
        finally:
            cc._ensure_in_combat = orig
        self.assertTrue(fake_cbt.initiative_reroll,
                        "danger_sense in combat must flag an initiative reroll")

    def test_warning_out_of_combat(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        orig = cc._ensure_in_combat
        cc._ensure_in_combat = lambda char: (None, None)
        try:
            sess = _FakeSession(caster)
            ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
            _run(fc._apply_danger_sense(ctx, caster))
        finally:
            cc._ensure_in_combat = orig
        self.assertTrue(any("still" in s.lower() or "nothing threatens" in s.lower()
                            for s in sess.sent))


if __name__ == "__main__":
    unittest.main()
