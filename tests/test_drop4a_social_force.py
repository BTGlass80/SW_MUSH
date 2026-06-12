# -*- coding: utf-8 -*-
"""
tests/test_drop4a_social_force.py — Drop 4a (2026-06-04)

Mechanical teeth on the previously narrative-only social / sense / alter
Force powers, plus the mind-trick SPLIT. Per the Part V / Drop 4 locked
decision set (TODO.json design_calls_resolved_recent, 2026-06-04):

  (a) affect_mind = light "suggestion": dark_side=False, NO DSP, resolved
      as an OPPOSED willpower roll vs an NPC (WEG R&E mind influence is
      opposed, not flat-difficulty). dominate_mind = coercion: dark_side
      =True (auto DSP).
  (b) PC target -> OFFERED EFFECT (never auto-override); NPC target ->
      engine resolves deterministically (guard pacify / pry-info).
      telekinesis -> real disarm. life_sense / sense_force -> real info.

Engine surface is tested deterministically (the split, no-DSP, the opposed
difficulty invariant, the disarm-margin gate, the effect_kind signals).
The parser application layer is tested by driving the appliers directly
with synthetic successful results (no dice flakiness) plus one end-to-end
wiring test through ForceCommand.execute with resolve patched.

Structural-negative classes pin the split so a revert turns the board red.
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
from engine.force_powers import (  # noqa: E402
    POWERS, ForcePowerResult, resolve_force_power, MODERATE, DIFFICULT,
)
from engine import buffs  # noqa: E402
import parser.force_commands as fc  # noqa: E402


_SR = SkillRegistry()
_SR.load_file(os.path.join(PROJECT_ROOT, "data", "skills.yaml"))


def _caster(control="5D", sense="5D", alter="5D"):
    return Character.from_db_dict({
        "id": 1, "name": "Jedi", "room_id": 10,
        "attributes": json.dumps(
            {"control": control, "sense": sense, "alter": alter,
             "perception": "3D"}),
        "skills": "{}",
    })


def _npc_obj(willpower=None, perception="1D", weapon=None):
    sheet = {"attributes": {"perception": perception}}
    if willpower is not None:
        sheet.setdefault("skills", {})["willpower"] = willpower
    if weapon:
        sheet["equipment"] = {"weapon": weapon}
        sheet["weapon"] = weapon
    return Character.from_npc_sheet(7, sheet)


# ══════════════════════════════════════════════════════════════════════════
# ENGINE — mind-trick split + no-DSP
# ══════════════════════════════════════════════════════════════════════════

class TestMindTrickSplit(unittest.TestCase):
    def test_affect_mind_is_now_light(self):
        self.assertIn("affect_mind", POWERS)
        self.assertFalse(
            POWERS["affect_mind"].dark_side,
            "affect_mind (suggestion) must be dark_side=False after the split",
        )

    def test_dominate_mind_exists_and_is_dark(self):
        self.assertIn("dominate_mind", POWERS)
        self.assertTrue(
            POWERS["dominate_mind"].dark_side,
            "dominate_mind (coercion) must be dark_side=True",
        )

    def test_dominate_is_harder_than_suggestion(self):
        self.assertEqual(POWERS["affect_mind"].base_diff, MODERATE)
        self.assertEqual(POWERS["dominate_mind"].base_diff, DIFFICULT)
        self.assertGreater(
            POWERS["dominate_mind"].base_diff, POWERS["affect_mind"].base_diff)


class TestNoDspFromSuggestion(unittest.TestCase):
    def test_suggestion_awards_no_dsp(self):
        c = _caster()
        before = c.dark_side_points
        r = resolve_force_power("affect_mind", c, _SR,
                                target_char=_npc_obj(), target_is_npc=True)
        self.assertEqual(r.dsp_gained, 0)
        self.assertEqual(c.dark_side_points, before)

    def test_domination_awards_dsp(self):
        c = _caster()
        before = c.dark_side_points
        r = resolve_force_power("dominate_mind", c, _SR,
                                target_char=_npc_obj(), target_is_npc=True)
        self.assertEqual(r.dsp_gained, 1)
        self.assertEqual(c.dark_side_points, before + 1)


# ══════════════════════════════════════════════════════════════════════════
# ENGINE — opposed willpower roll (WEG-faithful, not flat difficulty)
# ══════════════════════════════════════════════════════════════════════════

class TestOpposedMindRoll(unittest.TestCase):
    def test_difficulty_is_max_of_base_and_resist(self):
        # Exact invariant regardless of the random rolls: against an NPC the
        # effective difficulty is max(base complexity, the NPC's willpower
        # resistance roll).
        c = _caster()
        r = resolve_force_power("affect_mind", c, _SR,
                                target_char=_npc_obj(willpower="2D"),
                                target_is_npc=True)
        resist = r.effect_payload.get("resist_roll")
        self.assertIsNotNone(resist, "an opposed roll must record resist_roll")
        self.assertEqual(r.difficulty, max(MODERATE, resist))

    def test_strong_will_can_raise_difficulty_above_base(self):
        # A very strong-willed NPC's resistance roll exceeds the Moderate
        # floor at least sometimes -> proves the resistance actually feeds
        # the difficulty (it is not a flat number).
        c = _caster()
        raised = 0
        for _ in range(60):
            r = resolve_force_power("affect_mind", c, _SR,
                                    target_char=_npc_obj(willpower="10D"),
                                    target_is_npc=True)
            if r.difficulty > MODERATE:
                raised += 1
        self.assertGreater(
            raised, 0,
            "a 10D-willpower NPC should raise difficulty above the base floor")

    def test_pc_target_uses_base_difficulty_no_resist_roll(self):
        # PC target (target_is_npc False): the engine does NOT auto-roll
        # the other player's mind. No resist roll; difficulty stays base.
        c = _caster()
        r = resolve_force_power("affect_mind", c, _SR,
                                target_char=_npc_obj(willpower="10D"),
                                target_is_npc=False)
        self.assertNotIn("resist_roll", r.effect_payload)
        self.assertEqual(r.difficulty, MODERATE)


# ══════════════════════════════════════════════════════════════════════════
# ENGINE — resolver effect signals (deterministic, no roll)
# ══════════════════════════════════════════════════════════════════════════

class TestResolverEffectKinds(unittest.TestCase):
    def _blank(self, power_key):
        return ForcePowerResult(power=POWERS[power_key], success=True,
                                roll=20, difficulty=10, margin=10, narrative="")

    def test_affect_mind_signals_suggestion(self):
        res = self._blank("affect_mind")
        fp._resolve_affect_mind(res, _caster(), _npc_obj(), 8, [])
        self.assertEqual(res.effect_kind, "suggestion")
        self.assertEqual(res.effect_payload.get("strength"), "moderate")

    def test_dominate_signals_domination(self):
        res = self._blank("dominate_mind")
        fp._resolve_dominate_mind(res, _caster(), _npc_obj(), 12, [])
        self.assertEqual(res.effect_kind, "domination")

    def test_life_sense_signals(self):
        res = self._blank("life_sense")
        fp._resolve_life_sense(res, _caster(), [])
        self.assertEqual(res.effect_kind, "life_sense")

    def test_sense_force_signals(self):
        res = self._blank("sense_force")
        fp._resolve_sense_force(res, _caster(), [])
        self.assertEqual(res.effect_kind, "sense_force")

    def test_telekinesis_disarm_margin_gate(self):
        # margin >= 3 -> real disarm; below -> shove only.
        hi = self._blank("telekinesis")
        fp._resolve_telekinesis(hi, _caster(), _npc_obj(weapon="blaster_pistol"),
                                5, [])
        self.assertTrue(hi.disarm)
        self.assertEqual(hi.effect_kind, "disarm")

        lo = self._blank("telekinesis")
        fp._resolve_telekinesis(lo, _caster(), _npc_obj(weapon="blaster_pistol"),
                                1, [])
        self.assertFalse(lo.disarm)
        self.assertEqual(lo.effect_kind, "")


# ══════════════════════════════════════════════════════════════════════════
# PARSER — fake plumbing
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
        self.broadcasts = []

    def find_by_character(self, char_id):
        return self._by_char.get(char_id)

    async def broadcast_to_room(self, room_id, msg, exclude=None, source_char=None):
        self.broadcasts.append((room_id, msg))


class _FakeDB:
    """Minimal async DB with a mutation log."""
    def __init__(self, pcs=None, npcs=None):
        self._pcs = pcs or []
        self._npcs = npcs or []
        self.saves = []        # (char_id, fields)
        self.npc_updates = []  # (npc_id, fields)

    async def get_characters_in_room(self, room_id, source_char=None):
        return [c for c in self._pcs if c.get("room_id") == room_id]

    async def get_npcs_in_room(self, room_id):
        return [n for n in self._npcs if n.get("room_id") == room_id]

    async def save_character(self, char_id, **fields):
        self.saves.append((char_id, fields))

    async def update_npc(self, npc_id, **fields):
        self.npc_updates.append((npc_id, fields))


def _ctx(session, db, session_mgr, args=""):
    from parser.commands import CommandContext
    return CommandContext(
        session=session, raw_input=f"force {args}".strip(), command="force",
        args=args, args_list=args.split() if args else [], db=db,
        session_mgr=session_mgr,
    )


def _run(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════════
# PARSER — life_sense / sense_force render real room data
# ══════════════════════════════════════════════════════════════════════════

class TestSenseAppliers(unittest.TestCase):
    def test_life_sense_lists_real_beings(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        pcs = [{"id": 2, "name": "Han", "room_id": 10},
               {"id": 1, "name": "Jedi", "room_id": 10}]  # self filtered out
        npcs = [{"id": 50, "name": "Greedo", "species": "Rodian", "room_id": 10}]
        sess = _FakeSession(caster)
        db = _FakeDB(pcs=pcs, npcs=npcs)
        ctx = _ctx(sess, db, _FakeSessionMgr())
        _run(fc._apply_life_sense(ctx, caster))
        joined = "\n".join(sess.sent)
        self.assertIn("Han", joined)
        self.assertIn("Greedo", joined)
        self.assertIn("2 living", joined)  # self excluded -> 2 beings

    def test_life_sense_alone(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
        _run(fc._apply_life_sense(ctx, caster))
        self.assertTrue(any("no other living presence" in s for s in sess.sent))

    def test_sense_force_flags_force_and_dark(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        pcs = [{"id": 2, "name": "Sith", "room_id": 10, "dark_side_points": 5}]
        npcs = [{"id": 50, "name": "Padawan", "room_id": 10,
                 "char_sheet_json": json.dumps({"force_sensitive": True})}]
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(pcs=pcs, npcs=npcs), _FakeSessionMgr())
        _run(fc._apply_sense_force(ctx, caster))
        joined = "\n".join(sess.sent)
        self.assertIn("Padawan", joined)   # force-sensitive
        self.assertIn("Sith", joined)      # dark side echo

    def test_sense_force_quiet(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        npcs = [{"id": 50, "name": "Farmer", "room_id": 10,
                 "char_sheet_json": "{}"}]
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(npcs=npcs), _FakeSessionMgr())
        _run(fc._apply_sense_force(ctx, caster))
        self.assertTrue(any("Force is quiet" in s for s in sess.sent))


# ══════════════════════════════════════════════════════════════════════════
# PARSER — mind influence application (NPC engine-side / PC offered)
# ══════════════════════════════════════════════════════════════════════════

class TestMindInfluenceApplier(unittest.TestCase):
    def _result(self, kind="suggestion"):
        return ForcePowerResult(power=POWERS["affect_mind"], success=True,
                                roll=20, difficulty=12, margin=8, narrative="",
                                effect_kind=kind)

    def test_guard_pacify_applies_buff_and_persists(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10, "attributes": "{}"}
        guard = {"id": 50, "name": "Sentry", "room_id": 10,
                 "ai_config_json": json.dumps({"city_guard_for_city_id": 1})}
        sess = _FakeSession(caster)
        db = _FakeDB()
        ctx = _ctx(sess, db, _FakeSessionMgr())
        _run(fc._apply_mind_influence(ctx, self._result(), caster, guard,
                                      _npc_obj(), True, dominate=False))
        self.assertTrue(
            buffs.has_buff(caster, "mind_trick_unseen"),
            "guard pacify must give the caster the mind_trick_unseen buff")
        self.assertTrue(
            any("attributes" in f for (_id, f) in db.saves),
            "caster attributes must be persisted after the buff")

    def test_generic_npc_pry_reveals_secret(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10, "attributes": "{}"}
        crook = {"id": 51, "name": "Smuggler", "room_id": 10,
                 "char_sheet_json": json.dumps(
                     {"secret": "the spice is hidden under the cantina floor"})}
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
        _run(fc._apply_mind_influence(ctx, self._result(), caster, crook,
                                      _npc_obj(), True, dominate=False))
        joined = "\n".join(sess.sent)
        self.assertIn("spice is hidden", joined)
        self.assertNotIn("mind_trick_unseen",
                         json.loads(caster.get("attributes", "{}")).keys())

    def test_pc_target_is_offered_not_applied(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10, "attributes": "{}"}
        target = {"id": 2, "name": "Lando", "room_id": 10, "attributes": "{}"}
        tgt_sess = _FakeSession(target)
        sess = _FakeSession(caster)
        mgr = _FakeSessionMgr(by_char={2: tgt_sess})
        ctx = _ctx(sess, _FakeDB(), mgr)
        _run(fc._apply_mind_influence(ctx, self._result(), caster, target,
                                      _npc_obj(), False, dominate=False))
        # The target player is *offered* the effect to RP.
        self.assertTrue(any("FORCE" in s for s in tgt_sess.sent))
        # The caster's character is not mechanically mutated.
        self.assertFalse(buffs.has_buff(caster, "mind_trick_unseen"))
        self.assertEqual(caster.get("attributes"), "{}")


# ══════════════════════════════════════════════════════════════════════════
# PARSER — telekinesis disarm application
# ══════════════════════════════════════════════════════════════════════════

class TestDisarmApplier(unittest.TestCase):
    def test_pc_disarm_clears_weapon_and_persists(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        target = {"id": 2, "name": "Boba", "room_id": 10,
                  "equipment": json.dumps({"weapon": "blaster_rifle",
                                           "armor": "vest"})}
        target_obj = Character.from_db_dict(target)
        sess = _FakeSession(caster)
        db = _FakeDB()
        ctx = _ctx(sess, db, _FakeSessionMgr())
        _run(fc._apply_disarm(ctx, caster, target, target_obj, target_is_npc=False))
        eq = json.loads(target["equipment"])
        self.assertNotIn("weapon", eq)
        self.assertIn("armor", eq)  # armor untouched
        self.assertTrue(
            any("equipment" in f for (cid, f) in db.saves if cid == 2),
            "target equipment must be persisted")

    def test_disarm_no_weapon(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        target = {"id": 2, "name": "Unarmed", "room_id": 10, "equipment": "{}"}
        target_obj = Character.from_db_dict(target)
        sess = _FakeSession(caster)
        ctx = _ctx(sess, _FakeDB(), _FakeSessionMgr())
        _run(fc._apply_disarm(ctx, caster, target, target_obj, target_is_npc=False))
        self.assertTrue(any("no weapon" in s for s in sess.sent))

    def test_npc_disarm_updates_sheet(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10}
        npc = {"id": 60, "name": "Thug", "room_id": 10,
               "char_sheet_json": json.dumps(
                   {"attributes": {"dexterity": "3D", "perception": "2D"},
                    "equipment": {"weapon": "vibroblade"}, "weapon": "vibroblade"})}
        from engine.npc_combat_ai import build_npc_character
        npc_obj = build_npc_character(npc)
        self.assertIsNotNone(npc_obj, "fixture sanity: NPC must build")
        self.assertEqual(npc_obj.equipped_weapon, "vibroblade")
        sess = _FakeSession(caster)
        db = _FakeDB()
        ctx = _ctx(sess, db, _FakeSessionMgr())
        _run(fc._apply_disarm(ctx, caster, npc, npc_obj, target_is_npc=True))
        self.assertTrue(db.npc_updates, "NPC disarm must call update_npc")
        _id, fields = db.npc_updates[0]
        self.assertEqual(_id, 60)
        sheet = json.loads(fields["char_sheet_json"])
        self.assertNotIn("weapon", sheet.get("equipment", {}))


# ══════════════════════════════════════════════════════════════════════════
# ENGINE — guard pacify hook (should_city_guard_engage short-circuit)
# ══════════════════════════════════════════════════════════════════════════

class TestGuardPacifyHook(unittest.TestCase):
    def test_buffed_char_is_not_engaged(self):
        from engine.city_guard_runtime import should_city_guard_engage
        guard = {"id": 50, "name": "Sentry",
                 "ai_config_json": json.dumps({"city_guard_for_city_id": 1})}
        entering = {"id": 9, "name": "Sneak", "attributes": "{}"}
        buffs.add_buff(entering, "mind_trick_unseen")
        # The buff check short-circuits before any player_cities lookup, so a
        # bare object suffices for db.
        result = _run(should_city_guard_engage(object(), guard, entering))
        self.assertFalse(
            result,
            "a guard must not engage a character carrying mind_trick_unseen")

    def test_non_guard_npc_never_engages(self):
        from engine.city_guard_runtime import should_city_guard_engage
        not_a_guard = {"id": 51, "name": "Bartender", "ai_config_json": "{}"}
        entering = {"id": 9, "name": "Patron", "attributes": "{}"}
        result = _run(should_city_guard_engage(object(), not_a_guard, entering))
        self.assertFalse(result)


# ══════════════════════════════════════════════════════════════════════════
# WIRING — ForceCommand.execute drives apply + persist (resolve patched)
# ══════════════════════════════════════════════════════════════════════════

class TestExecuteWiring(unittest.TestCase):
    def test_affect_mind_on_guard_persists_buff_end_to_end(self):
        caster = {"id": 1, "name": "Jedi", "room_id": 10,
                  "attributes": json.dumps(
                      {"control": "5D", "sense": "5D", "alter": "5D"}),
                  "skills": "{}", "wound_level": 0, "dark_side_points": 0}
        guard = {"id": 50, "name": "Sentry", "room_id": 10, "species": "Human",
                 "char_sheet_json": json.dumps({"attributes": {"perception": "2D"}}),
                 "ai_config_json": json.dumps({"city_guard_for_city_id": 1})}
        sess = _FakeSession(caster)
        db = _FakeDB(pcs=[], npcs=[guard])
        ctx = _ctx(sess, db, _FakeSessionMgr(), args="affect_mind Sentry")

        # Patch resolve so the test is deterministic (the opposed roll itself
        # is covered by the engine tests above). Return a successful suggestion.
        orig = fc.resolve_force_power

        def _fake_resolve(power_key, char, skill_reg, target_char=None,
                          extra_diff=0, *, weight_difficulty_mod=0,
                          extra_dsp_on_fail=0, target_is_npc=False):
            return ForcePowerResult(
                power=POWERS[power_key], success=True, roll=20, difficulty=12,
                margin=8, narrative="ok", effect_kind="suggestion",
                effect_payload={"strength": "moderate"})

        fc.resolve_force_power = _fake_resolve
        try:
            _run(fc.ForceCommand().execute(ctx))
        finally:
            fc.resolve_force_power = orig

        self.assertTrue(
            buffs.has_buff(caster, "mind_trick_unseen"),
            "end-to-end: affect_mind on a guard should land the buff")
        self.assertTrue(
            any("attributes" in f for (cid, f) in db.saves if cid == 1),
            "end-to-end: caster attributes persisted")


if __name__ == "__main__":
    unittest.main()
