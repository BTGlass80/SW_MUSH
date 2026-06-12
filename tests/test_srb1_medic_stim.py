# -*- coding: utf-8 -*-
"""
tests/test_srb1_medic_stim.py — SRB.1 medic stim system.

Per support_role_buffs_design_v1.md §3.

Drop 3 of the May 21 2026 phantom-rebuild wave. Replaces the
phantom SRB.1 surface: missing BUFF_TEMPLATES entries
(stimpack/adrenaline_shot/focus_stim), missing helpers
(is_stim_type/get_active_stim/has_active_stim), and missing parser
commands (StimCommand/StimAcceptCommand/_STIM_CATALOG).

Test sections
=============

Engine (engine/buffs.py additions):
  1.  TestBuffTemplates              — three new stims present, shape sane
  2.  TestIsStimType                 — family membership predicate
  3.  TestGetActiveStim              — returns Buff or None
  4.  TestHasActiveStim              — boolean form
  5.  TestStimAddBuffWiring          — add_buff('stimpack') works

Parser (parser/medical_commands.py additions):
  6.  TestStimCatalogShape           — catalog has expected entries + keys
  7.  TestCanonicalConsumable        — alias resolver
  8.  TestStimCommandSurface         — class attrs
  9.  TestStimAcceptSurface          — class attrs + aliases
 10.  TestRegisterMedicalCommands    — SRB.1 cmds registered alongside Heal*
 11.  TestStimNoArgs                 — empty args → usage
 12.  TestStimUnknownConsumable      — bad 'with' token → error
 13.  TestStimUnknownTarget          — no match in room → error
 14.  TestStimNoSkill                — medic lacks skill → refused
 15.  TestStimCrossTypeBlocked       — target has active stim → refused
 16.  TestStimSelfDisallowed         — adrenaline_shot self → refused
 17.  TestStimSelfAllowed            — stimpack self → resolves immediately
 18.  TestStimOfferStaged            — non-self stages a pending offer
 19.  TestStimAcceptNoOffer          — no pending → friendly error
 20.  TestStimAcceptExpired          — > 60s → expired error
 21.  TestStimAcceptMedicGone        — medic left room → refused
 22.  TestStimSuccessAppliesBuff     — high-roll success → buff present
 23.  TestStimFailureNoBuff          — low-roll failure → no buff
 24.  TestStimFailureAdrenWound      — adrenaline_shot fail → +1 wound
 25.  TestStimFumbleWound            — fumble → +2 wounds
 26.  TestUmbrellaStim               — `+medical stim ...` reaches StimCommand
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── Shared fakes ─────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, line):
        self.sent.append(line)


class _FakeDB:
    """Minimal db fake for SRB.1 stim parser tests. Captures all
    save_character calls so tests can assert mutations precisely."""

    def __init__(self):
        self.writes = []
        self.chars = {}  # id -> dict

    def add_char(self, char):
        self.chars[char["id"]] = char
        return char

    async def save_character(self, char_id, **fields):
        self.writes.append(("save_character", char_id, dict(fields)))
        # Mirror writes into the in-memory dict for downstream reads.
        if char_id in self.chars:
            self.chars[char_id].update(fields)
        return True


class _FakeSessionMgr:
    """Provides sessions_in_room() the same way the real one does."""

    def __init__(self, sessions):
        self.sessions = list(sessions)

    def sessions_in_room(self, room_id, *, source_char=None):
        for s in self.sessions:
            if s.character and s.character.get("room_id") == room_id:
                yield s


def _make_char(*, char_id, name, room_id=1, skills=None,
               attributes=None, wound_level=0, consumables=None):
    """Build a minimal character dict the medical commands accept.

    Per SRB.1 (b) shipped May 24 2026: medics must have stims in
    ``attributes.consumables`` before they can administer them. The
    optional ``consumables`` kwarg merges into attributes. Pass
    ``consumables={"stimpack": 5}`` to seed a typical medic kit.
    """
    attrs = dict(attributes or {})
    if consumables is not None:
        merged = dict(attrs.get("consumables", {}))
        merged.update(consumables)
        attrs["consumables"] = merged
    return {
        "id": char_id,
        "name": name,
        "room_id": room_id,
        "skills": json.dumps(skills or {}),
        "attributes": json.dumps(attrs),
        "wound_level": wound_level,
        "credits": 5000,
    }


# Typical medic kit used across stim tests. Per SRB.1 (b) shipped
# May 24 2026, medics need stims in their kit to administer. Five
# of each is enough for any single-test scenario.
_TYPICAL_MEDIC_KIT = {
    "stimpack": 5,
    "adrenaline_shot": 5,
    "combat_stim": 5,
    "focus_stim": 5,
}


def _make_ctx(db, session, args, *, session_mgr=None):
    """Build a CommandContext-shaped object the commands accept."""
    ctx = MagicMock()
    ctx.session = session
    ctx.db = db
    ctx.session_mgr = session_mgr
    ctx.args = args
    return ctx


def _clear_pending():
    """Reset module-level pending offers between tests."""
    from parser.medical_commands import _pending_stims, _pending_heals
    _pending_stims.clear()
    _pending_heals.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 1. TestBuffTemplates
# ═══════════════════════════════════════════════════════════════════════════

class TestBuffTemplates(unittest.TestCase):
    def test_three_new_stims_present(self):
        from engine.buffs import BUFF_TEMPLATES
        for name in ("stimpack", "adrenaline_shot", "focus_stim"):
            self.assertIn(name, BUFF_TEMPLATES,
                          f"missing template: {name}")

    def test_combat_stim_preserved(self):
        # combat_stim pre-existed SRB.1; must not have been disturbed.
        from engine.buffs import BUFF_TEMPLATES
        self.assertIn("combat_stim", BUFF_TEMPLATES)
        self.assertEqual(BUFF_TEMPLATES["combat_stim"]["duration_seconds"], 300)

    def test_stim_templates_have_required_keys(self):
        from engine.buffs import BUFF_TEMPLATES
        for name in ("stimpack", "adrenaline_shot", "focus_stim"):
            t = BUFF_TEMPLATES[name]
            for k in ("display_name", "stat_modifiers",
                      "duration_seconds", "max_stacks",
                      "positive", "source"):
                self.assertIn(k, t, f"{name} missing {k}")
            self.assertEqual(t["max_stacks"], 1,
                             f"{name} should be single-stack per §3.6")
            self.assertTrue(t["positive"],
                            f"{name} should be a positive buff")

    def test_adrenaline_shot_is_2D(self):
        from engine.buffs import BUFF_TEMPLATES
        # +6 pips = +2D per the dice/pip invariant in buffs.py
        mods = BUFF_TEMPLATES["adrenaline_shot"]["stat_modifiers"]
        total = sum(abs(v) for v in mods.values())
        self.assertEqual(total, 6)


# ═══════════════════════════════════════════════════════════════════════════
# 2. TestIsStimType
# ═══════════════════════════════════════════════════════════════════════════

class TestIsStimType(unittest.TestCase):
    def test_all_four_stims_match(self):
        from engine.buffs import is_stim_type
        for name in ("combat_stim", "stimpack",
                     "adrenaline_shot", "focus_stim"):
            self.assertTrue(is_stim_type(name),
                            f"{name} should be is_stim_type=True")

    def test_non_stim_buffs_do_not_match(self):
        from engine.buffs import is_stim_type
        for name in ("bacta_healing", "cantina_drink", "inspired",
                     "dehydration", "force_control_pain", ""):
            self.assertFalse(is_stim_type(name),
                             f"{name} should not be a stim")


# ═══════════════════════════════════════════════════════════════════════════
# 3. TestGetActiveStim
# ═══════════════════════════════════════════════════════════════════════════

class TestGetActiveStim(unittest.TestCase):
    def test_no_buffs_returns_none(self):
        from engine.buffs import get_active_stim
        char = _make_char(char_id=1, name="Test")
        self.assertIsNone(get_active_stim(char))

    def test_only_non_stim_returns_none(self):
        from engine.buffs import add_buff, get_active_stim
        char = _make_char(char_id=1, name="Test")
        add_buff(char, "inspired")
        self.assertIsNone(get_active_stim(char))

    def test_stim_present_returns_buff(self):
        from engine.buffs import add_buff, get_active_stim
        char = _make_char(char_id=1, name="Test")
        add_buff(char, "stimpack")
        stim = get_active_stim(char)
        self.assertIsNotNone(stim)
        self.assertEqual(stim.buff_type, "stimpack")


# ═══════════════════════════════════════════════════════════════════════════
# 4. TestHasActiveStim
# ═══════════════════════════════════════════════════════════════════════════

class TestHasActiveStim(unittest.TestCase):
    def test_no_buff_false(self):
        from engine.buffs import has_active_stim
        char = _make_char(char_id=1, name="Test")
        self.assertFalse(has_active_stim(char))

    def test_stim_present_true(self):
        from engine.buffs import add_buff, has_active_stim
        char = _make_char(char_id=1, name="Test")
        add_buff(char, "combat_stim")
        self.assertTrue(has_active_stim(char))

    def test_non_stim_buff_false(self):
        from engine.buffs import add_buff, has_active_stim
        char = _make_char(char_id=1, name="Test")
        add_buff(char, "bacta_healing")
        self.assertFalse(has_active_stim(char))


# ═══════════════════════════════════════════════════════════════════════════
# 5. TestStimAddBuffWiring
# ═══════════════════════════════════════════════════════════════════════════

class TestStimAddBuffWiring(unittest.TestCase):
    def test_add_buff_with_stim_template_succeeds(self):
        from engine.buffs import add_buff
        char = _make_char(char_id=1, name="Test")
        result = add_buff(char, "stimpack")
        self.assertTrue(result["ok"],
                        f"add_buff('stimpack') returned: {result}")
        self.assertEqual(result["buff"].buff_type, "stimpack")


# ═══════════════════════════════════════════════════════════════════════════
# 6. TestStimCatalogShape
# ═══════════════════════════════════════════════════════════════════════════

class TestStimCatalogShape(unittest.TestCase):
    def test_catalog_entries(self):
        # 2026-06-12: pin updated WITH attribution — this test was
        # already red in HEAD (pre-existing, verified against the clean
        # upload): the medpac family (medpac, medpac_advanced,
        # medpac_fastflesh) landed in _STIM_CATALOG in a prior drop
        # without updating the four-entry pin. The seven below are the
        # intended catalog; the shape test underneath still guards
        # every entry's required keys.
        from parser.medical_commands import _STIM_CATALOG
        self.assertEqual(
            set(_STIM_CATALOG.keys()),
            {"stimpack", "adrenaline_shot", "combat_stim", "focus_stim",
             "medpac", "medpac_advanced", "medpac_fastflesh"},
        )

    def test_each_entry_has_required_keys(self):
        from parser.medical_commands import _STIM_CATALOG
        for key, spec in _STIM_CATALOG.items():
            for k in ("skill", "difficulty", "buff_type",
                      "self_administration_ok", "fail_msg"):
                self.assertIn(k, spec, f"{key} missing {k}")

    def test_difficulties_match_design(self):
        from parser.medical_commands import _STIM_CATALOG
        # Design §3.2: stimpack=10, adrenaline=15, combat=20
        # Design §3.3: focus_stim=15
        self.assertEqual(_STIM_CATALOG["stimpack"]["difficulty"], 10)
        self.assertEqual(_STIM_CATALOG["adrenaline_shot"]["difficulty"], 15)
        self.assertEqual(_STIM_CATALOG["combat_stim"]["difficulty"], 20)
        self.assertEqual(_STIM_CATALOG["focus_stim"]["difficulty"], 15)

    def test_self_admin_rules_match_design(self):
        from parser.medical_commands import _STIM_CATALOG
        # Design §3.7: adrenaline + combat NOT self-administrable
        self.assertTrue(_STIM_CATALOG["stimpack"]["self_administration_ok"])
        self.assertTrue(_STIM_CATALOG["focus_stim"]["self_administration_ok"])
        self.assertFalse(_STIM_CATALOG["adrenaline_shot"]["self_administration_ok"])
        self.assertFalse(_STIM_CATALOG["combat_stim"]["self_administration_ok"])


# ═══════════════════════════════════════════════════════════════════════════
# 7. TestCanonicalConsumable
# ═══════════════════════════════════════════════════════════════════════════

class TestCanonicalConsumable(unittest.TestCase):
    def test_canonical_keys_round_trip(self):
        from parser.medical_commands import _canonical_consumable
        for key in ("stimpack", "adrenaline_shot", "combat_stim", "focus_stim"):
            self.assertEqual(_canonical_consumable(key), key)

    def test_aliases_resolve(self):
        from parser.medical_commands import _canonical_consumable
        cases = [
            ("adrenaline", "adrenaline_shot"),
            ("adrenshot", "adrenaline_shot"),
            ("combat", "combat_stim"),
            ("focus", "focus_stim"),
            ("pack", "stimpack"),
        ]
        for raw, expected in cases:
            self.assertEqual(_canonical_consumable(raw), expected, raw)

    def test_case_and_space_tolerant(self):
        from parser.medical_commands import _canonical_consumable
        self.assertEqual(_canonical_consumable("Combat Stim"), "combat_stim")
        self.assertEqual(_canonical_consumable("ADRENALINE-SHOT"),
                         "adrenaline_shot")

    def test_unknown_returns_none(self):
        from parser.medical_commands import _canonical_consumable
        self.assertIsNone(_canonical_consumable("morphine"))
        self.assertIsNone(_canonical_consumable(""))


# ═══════════════════════════════════════════════════════════════════════════
# 8. TestStimCommandSurface
# ═══════════════════════════════════════════════════════════════════════════

class TestStimCommandSurface(unittest.TestCase):
    def test_class_attrs(self):
        from parser.medical_commands import StimCommand
        self.assertEqual(StimCommand.key, "stim")
        self.assertTrue(StimCommand.help_text)
        self.assertTrue(StimCommand.usage)


# ═══════════════════════════════════════════════════════════════════════════
# 9. TestStimAcceptSurface
# ═══════════════════════════════════════════════════════════════════════════

class TestStimAcceptSurface(unittest.TestCase):
    def test_class_attrs(self):
        from parser.medical_commands import StimAcceptCommand
        self.assertEqual(StimAcceptCommand.key, "stimaccept")
        self.assertIn("saccept", StimAcceptCommand.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 10. TestRegisterMedicalCommands
# ═══════════════════════════════════════════════════════════════════════════

class TestRegisterMedicalCommands(unittest.TestCase):
    def test_stim_commands_registered_alongside_heal(self):
        from parser.medical_commands import (
            register_medical_commands,
            HealCommand, HealAcceptCommand, HealRateCommand,
            StimCommand, StimAcceptCommand, MedicalCommand,
        )
        registered = []

        class FakeRegistry:
            def register(self, cmd):
                registered.append(cmd)

        register_medical_commands(FakeRegistry())
        types = {type(c) for c in registered}
        for cls in (HealCommand, HealAcceptCommand, HealRateCommand,
                    StimCommand, StimAcceptCommand, MedicalCommand):
            self.assertIn(cls, types,
                          f"{cls.__name__} not registered")


# ═══════════════════════════════════════════════════════════════════════════
# 11. TestStimNoArgs
# ═══════════════════════════════════════════════════════════════════════════

class TestStimNoArgs(unittest.TestCase):
    def test_empty_args_prints_usage(self):
        from parser.medical_commands import StimCommand
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 3})
        sess = _FakeSession(character=medic)
        ctx = _make_ctx(db, sess, "",
                        session_mgr=_FakeSessionMgr([sess]))
        _run(StimCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertIn("Usage", joined)
        self.assertEqual(db.writes, [])


# ═══════════════════════════════════════════════════════════════════════════
# 12. TestStimUnknownConsumable
# ═══════════════════════════════════════════════════════════════════════════

class TestStimUnknownConsumable(unittest.TestCase):
    def test_bad_with_token_errors(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 3})
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient with morphine",
                        session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("Unknown consumable", joined)
        self.assertEqual(_pending_stims, {})


# ═══════════════════════════════════════════════════════════════════════════
# 13. TestStimUnknownTarget
# ═══════════════════════════════════════════════════════════════════════════

class TestStimUnknownTarget(unittest.TestCase):
    def test_target_not_in_room_errors(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        # No consumables seeded — target-not-found check fires
        # before the consumables gate, so this test exercises only
        # the room-lookup path.
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 3})
        medic_sess = _FakeSession(character=medic)
        sm = _FakeSessionMgr([medic_sess])
        ctx = _make_ctx(db, medic_sess, "Phantom", session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("Can't find", joined)
        self.assertEqual(_pending_stims, {})


# ═══════════════════════════════════════════════════════════════════════════
# 14. TestStimNoSkill
# ═══════════════════════════════════════════════════════════════════════════

class TestStimNoSkill(unittest.TestCase):
    def test_no_first_aid_refuses(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        # No consumables seeded — but skill gate fires first so we
        # see "First Aid" not "no kit." Order is skill-then-kit.
        medic = _make_char(char_id=1, name="Medic", skills={})
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient", session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("First Aid", joined)
        self.assertEqual(_pending_stims, {})


# ═══════════════════════════════════════════════════════════════════════════
# 15. TestStimCrossTypeBlocked
# ═══════════════════════════════════════════════════════════════════════════

class TestStimCrossTypeBlocked(unittest.TestCase):
    def test_target_with_active_stim_refused(self):
        from parser.medical_commands import StimCommand, _pending_stims
        from engine.buffs import add_buff
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 3},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient")
        # Pre-existing combat_stim on target
        add_buff(target, "combat_stim")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient", session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("active stim", joined)
        self.assertEqual(_pending_stims, {})


# ═══════════════════════════════════════════════════════════════════════════
# 16. TestStimSelfDisallowed
# ═══════════════════════════════════════════════════════════════════════════

class TestStimSelfDisallowed(unittest.TestCase):
    def test_adrenaline_self_refused(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"medicine": 3})
        medic_sess = _FakeSession(character=medic)
        sm = _FakeSessionMgr([medic_sess])
        ctx = _make_ctx(db, medic_sess, "me with adrenaline_shot",
                        session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("self-administer", joined)
        self.assertEqual(_pending_stims, {})


# ═══════════════════════════════════════════════════════════════════════════
# 17. TestStimSelfAllowed
# ═══════════════════════════════════════════════════════════════════════════

class TestStimSelfAllowed(unittest.TestCase):
    """Self-stim with stimpack resolves immediately (no stimaccept
    needed); the offer is consumed in-line."""

    def test_self_stimpack_resolves_inline(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 5},
                           consumables=_TYPICAL_MEDIC_KIT)
        db.add_char(medic)
        medic_sess = _FakeSession(character=medic)
        sm = _FakeSessionMgr([medic_sess])
        ctx = _make_ctx(db, medic_sess, "self", session_mgr=sm)
        # Force-roll: monkey-patch perform_skill_check to a success
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        original = skill_checks.perform_skill_check
        def _force_success(*a, **kw):
            return SkillCheckResult(
                roll=20, difficulty=10, success=True, margin=10,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="3D",
            )
        skill_checks.perform_skill_check = _force_success
        try:
            _run(StimCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Pending offer should be consumed (empty after resolution)
        self.assertEqual(_pending_stims, {},
                         "self-stim should consume its own offer")
        # Should have attempted to save the modified attributes
        write_kinds = [w[2].keys() for w in db.writes
                       if w[0] == "save_character"]
        self.assertTrue(
            any("attributes" in keys for keys in write_kinds),
            "self-stim success should persist the buff via "
            "save_character(..., attributes=...)",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 18. TestStimOfferStaged
# ═══════════════════════════════════════════════════════════════════════════

class TestStimOfferStaged(unittest.TestCase):
    def test_non_self_stim_stages_pending_offer(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 3},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient", session_mgr=sm)
        _run(StimCommand().execute(ctx))
        self.assertIn(2, _pending_stims)
        offer = _pending_stims[2]
        self.assertEqual(offer["medic_id"], 1)
        self.assertEqual(offer["consumable_key"], "stimpack")
        self.assertFalse(offer["is_self"])
        # Should have prompted both medic and target
        joined_target = "\n".join(target_sess.sent)
        self.assertIn("stimaccept", joined_target)


# ═══════════════════════════════════════════════════════════════════════════
# 19. TestStimAcceptNoOffer
# ═══════════════════════════════════════════════════════════════════════════

class TestStimAcceptNoOffer(unittest.TestCase):
    def test_no_pending_offer_friendly_error(self):
        from parser.medical_commands import StimAcceptCommand
        _clear_pending()
        db = _FakeDB()
        target = _make_char(char_id=2, name="Patient")
        sess = _FakeSession(character=target)
        ctx = _make_ctx(db, sess, "")
        _run(StimAcceptCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertIn("no pending stim offer", joined.lower())
        self.assertEqual(db.writes, [])


# ═══════════════════════════════════════════════════════════════════════════
# 20. TestStimAcceptExpired
# ═══════════════════════════════════════════════════════════════════════════

class TestStimAcceptExpired(unittest.TestCase):
    def test_offer_older_than_60s_expires(self):
        import time as _time
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic")
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1,
            "medic_session": medic_sess,
            "medic_name": "Medic",
            "consumable_key": "stimpack",
            "is_self": False,
            "offered_at": _time.time() - 120.0,  # 2 min old
        }
        ctx = _make_ctx(db, target_sess, "")
        _run(StimAcceptCommand().execute(ctx))
        joined = "\n".join(target_sess.sent)
        self.assertIn("expired", joined.lower())
        self.assertEqual(db.writes, [])


# ═══════════════════════════════════════════════════════════════════════════
# 21. TestStimAcceptMedicGone
# ═══════════════════════════════════════════════════════════════════════════

class TestStimAcceptMedicGone(unittest.TestCase):
    def test_medic_left_room_refused(self):
        import time as _time
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic", room_id=99)  # left
        target = _make_char(char_id=2, name="Patient", room_id=1)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1,
            "medic_session": medic_sess,
            "medic_name": "Medic",
            "consumable_key": "stimpack",
            "is_self": False,
            "offered_at": _time.time(),
        }
        ctx = _make_ctx(db, target_sess, "")
        _run(StimAcceptCommand().execute(ctx))
        joined = "\n".join(target_sess.sent)
        self.assertIn("no longer here", joined.lower())
        self.assertEqual(db.writes, [])


# ═══════════════════════════════════════════════════════════════════════════
# 22. TestStimSuccessAppliesBuff
# ═══════════════════════════════════════════════════════════════════════════

class TestStimSuccessAppliesBuff(unittest.TestCase):
    def test_success_persists_buff(self):
        import time as _time
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 5},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient")
        db.add_char(medic)
        db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1,
            "medic_session": medic_sess,
            "medic_name": "Medic",
            "consumable_key": "stimpack",
            "is_self": False,
            "offered_at": _time.time(),
        }
        original = skill_checks.perform_skill_check
        def _force_success(*a, **kw):
            return SkillCheckResult(
                roll=20, difficulty=10, success=True, margin=10,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="3D",
            )
        skill_checks.perform_skill_check = _force_success
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Should have persisted via save_character(attributes=...)
        attribute_writes = [
            w for w in db.writes
            if w[0] == "save_character" and "attributes" in w[2]
        ]
        self.assertTrue(attribute_writes,
                        "success should persist buff via save_character")
        # And the modified char dict should actually carry the buff
        from engine.buffs import get_active_stim
        self.assertIsNotNone(get_active_stim(target))


# ═══════════════════════════════════════════════════════════════════════════
# 23. TestStimFailureNoBuff
# ═══════════════════════════════════════════════════════════════════════════

class TestStimFailureNoBuff(unittest.TestCase):
    def test_failure_does_not_add_positive_buff(self):
        import time as _time
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        from engine.buffs import get_active_stim
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 1},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient")
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "stimpack",
            "is_self": False, "offered_at": _time.time(),
        }
        original = skill_checks.perform_skill_check
        def _force_fail(*a, **kw):
            return SkillCheckResult(
                roll=5, difficulty=10, success=False, margin=-5,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="2D",
            )
        skill_checks.perform_skill_check = _force_fail
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # No stimpack buff should be on the target
        stim = get_active_stim(target)
        self.assertIsNone(stim,
                          "failure must not apply the positive buff")
        # Should have emitted the failure flavour message
        joined = "\n".join(target_sess.sent)
        self.assertIn("no real benefit", joined.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 24. TestStimFailureAdrenWound
# ═══════════════════════════════════════════════════════════════════════════

class TestStimFailureAdrenWound(unittest.TestCase):
    def test_adrenaline_failure_adds_one_wound(self):
        import time as _time
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"medicine": 1},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient", wound_level=1)
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "adrenaline_shot",
            "is_self": False, "offered_at": _time.time(),
        }
        original = skill_checks.perform_skill_check
        def _force_fail(*a, **kw):
            return SkillCheckResult(
                roll=5, difficulty=15, success=False, margin=-10,
                critical_success=False, fumble=False,
                skill_used="medicine", pool_str="2D",
            )
        skill_checks.perform_skill_check = _force_fail
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Wound level should be 2 (started 1, +1 for adrenaline fail)
        wound_writes = [
            w for w in db.writes
            if w[0] == "save_character" and "wound_level" in w[2]
        ]
        self.assertTrue(wound_writes,
                        "adrenaline failure must escalate wound level")
        # Last write must show wound_level == 2
        last_wound = wound_writes[-1][2]["wound_level"]
        self.assertEqual(last_wound, 2)


# ═══════════════════════════════════════════════════════════════════════════
# 25. TestStimFumbleWound
# ═══════════════════════════════════════════════════════════════════════════

class TestStimFumbleWound(unittest.TestCase):
    def test_fumble_applies_two_wound_levels(self):
        import time as _time
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 1},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient", wound_level=1)
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "stimpack",
            "is_self": False, "offered_at": _time.time(),
        }
        original = skill_checks.perform_skill_check
        def _force_fumble(*a, **kw):
            return SkillCheckResult(
                roll=2, difficulty=10, success=False, margin=-8,
                critical_success=False, fumble=True,
                skill_used="first aid", pool_str="2D",
            )
        skill_checks.perform_skill_check = _force_fumble
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        wound_writes = [
            w for w in db.writes
            if w[0] == "save_character" and "wound_level" in w[2]
        ]
        self.assertTrue(wound_writes,
                        "fumble must escalate wound level")
        # Started at 1, fumble adds 2, expect 3
        last = wound_writes[-1][2]["wound_level"]
        self.assertEqual(last, 3)
        joined = "\n".join(medic_sess.sent)
        self.assertIn("Fumble", joined)


# ═══════════════════════════════════════════════════════════════════════════
# 26. TestUmbrellaStim
# ═══════════════════════════════════════════════════════════════════════════

class TestUmbrellaStim(unittest.TestCase):
    """`+medical stim ...` should dispatch through the umbrella to
    StimCommand."""

    def test_plus_medical_stim_routes(self):
        from parser.medical_commands import (
            MedicalCommand, _pending_stims,
        )
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(char_id=1, name="Medic",
                           skills={"first aid": 3},
                           consumables=_TYPICAL_MEDIC_KIT)
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "stim Patient", session_mgr=sm)
        _run(MedicalCommand().execute(ctx))
        # A pending offer should have been staged
        self.assertIn(2, _pending_stims,
                      "+medical stim Patient should reach StimCommand")


if __name__ == "__main__":
    unittest.main(verbosity=2)
