# -*- coding: utf-8 -*-
"""
tests/test_srb1b_stim_consumable_wiring.py — SRB.1 (b) wiring of stim
consumption to attributes.consumables.

Per T2.10.b in TODO.json: medics must have stims in their kit
(``attributes.consumables[<output_key>]``) to administer them. The
crafting layer (parser/crafting_commands.py for output_type:
consumable) writes there; this drop adds the read+decrement on
the stim path.

Test surface
------------

1. TestConsumableHelpers — engine/buffs.py helpers in isolation:
   has_consumable, get_consumable_count, consume_consumable.
   Covers: empty char, dict attrs, JSON-string attrs, count-to-zero
   key removal, malformed attrs, isolation between keys.

2. TestOfferTimeGate — StimCommand refuses at offer time when the
   medic has no kit of the requested type. Covers: empty
   consumables dict, missing key, key present at zero count.

3. TestConsumptionAtResolveSuccess — _execute_stim_roll decrements
   the medic's consumable count by 1 on success path.

4. TestConsumptionAtResolveFailure — failure path also consumes
   (design §3.5: "target wastes the stim, no benefit").

5. TestConsumptionAtResolveFumble — fumble path also consumes.

6. TestConsumptionAtResolveSelfStim — self-administration
   consumes from the actor's own kit.

7. TestConsumptionPersistsToDb — after consumption, save_character
   is called with attributes=... so the deduction is durable.

8. TestDocumentedBifurcation — the stim section docstring in
   parser/medical_commands.py has been updated to reflect SRB.1.b
   shipped (substrate decision #1 no longer says "abstract").
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import unittest
from unittest.mock import MagicMock

# Test fixtures borrowed from the main stim test suite shape.
from engine.buffs import (
    has_consumable,
    get_consumable_count,
    consume_consumable,
)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(coro):
    return asyncio.run(coro)


# ─── Fixtures (mirror tests/test_srb1_medic_stim.py shapes) ──────────────────


class _FakeDB:
    def __init__(self):
        self.writes = []
        self.chars = {}

    def add_char(self, char):
        self.chars[char["id"]] = char

    async def save_character(self, char_id, **kwargs):
        self.writes.append(("save_character", char_id, kwargs))
        if char_id in self.chars:
            for k, v in kwargs.items():
                self.chars[char_id][k] = v


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []
        self._closed = False

    async def send_line(self, msg):
        self.sent.append(msg)

    async def close(self):
        self._closed = True


class _FakeSessionMgr:
    def __init__(self, sessions):
        self.sessions = list(sessions)

    def sessions_in_room(self, room_id, *, source_char=None):
        for s in self.sessions:
            if s.character and s.character.get("room_id") == room_id:
                yield s


def _make_char(*, char_id, name, room_id=1, skills=None,
               attributes=None, consumables=None, wound_level=0):
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


def _make_ctx(db, session, args, *, session_mgr=None):
    ctx = MagicMock()
    ctx.session = session
    ctx.db = db
    ctx.session_mgr = session_mgr
    ctx.args = args
    return ctx


def _clear_pending():
    from parser.medical_commands import _pending_stims, _pending_heals
    _pending_stims.clear()
    _pending_heals.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 1. TestConsumableHelpers
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumableHelpers(unittest.TestCase):
    """engine/buffs.py consumable helpers in isolation."""

    def test_empty_char_returns_false(self):
        c = {"attributes": "{}"}
        self.assertFalse(has_consumable(c, "stimpack"))
        self.assertEqual(get_consumable_count(c, "stimpack"), 0)
        self.assertFalse(consume_consumable(c, "stimpack"))

    def test_dict_attrs_decrement(self):
        c = {"attributes": {"consumables": {"stimpack": 3}}}
        self.assertTrue(has_consumable(c, "stimpack"))
        self.assertEqual(get_consumable_count(c, "stimpack"), 3)
        self.assertTrue(consume_consumable(c, "stimpack"))
        self.assertEqual(get_consumable_count(c, "stimpack"), 2)

    def test_json_string_attrs_decrement(self):
        c = {
            "attributes": json.dumps({
                "consumables": {"combat_stim": 1},
            }),
        }
        self.assertTrue(consume_consumable(c, "combat_stim"))
        # count was 1 → key should be removed entirely
        attrs = json.loads(c["attributes"])
        self.assertNotIn("combat_stim", attrs.get("consumables", {}))

    def test_isolation_between_keys(self):
        c = {
            "attributes": {
                "consumables": {"stimpack": 2, "focus_stim": 1},
            },
        }
        consume_consumable(c, "stimpack")
        self.assertEqual(get_consumable_count(c, "stimpack"), 1)
        self.assertEqual(get_consumable_count(c, "focus_stim"), 1)

    def test_malformed_attrs_safe(self):
        c = {"attributes": "not-json"}
        self.assertFalse(has_consumable(c, "stimpack"))
        self.assertFalse(consume_consumable(c, "stimpack"))

    def test_missing_consumables_dict_safe(self):
        c = {"attributes": json.dumps({"force_points": 2})}
        self.assertFalse(has_consumable(c, "stimpack"))
        self.assertFalse(consume_consumable(c, "stimpack"))

    def test_count_zero_treated_as_absent(self):
        c = {"attributes": {"consumables": {"stimpack": 0}}}
        self.assertFalse(has_consumable(c, "stimpack"))
        self.assertFalse(consume_consumable(c, "stimpack"))

    def test_negative_count_treated_as_absent(self):
        # Defensive — shouldn't happen but malformed JSON could yield it
        c = {"attributes": {"consumables": {"stimpack": -1}}}
        self.assertFalse(has_consumable(c, "stimpack"))
        self.assertEqual(get_consumable_count(c, "stimpack"), 0)

    def test_consume_to_zero_removes_key(self):
        c = {"attributes": {"consumables": {"stimpack": 2}}}
        consume_consumable(c, "stimpack")
        consume_consumable(c, "stimpack")
        # Both calls returned True; key should be gone now
        consumables = c["attributes"]["consumables"]
        self.assertNotIn("stimpack", consumables)


# ═══════════════════════════════════════════════════════════════════════════
# 2. TestOfferTimeGate
# ═══════════════════════════════════════════════════════════════════════════

class TestOfferTimeGate(unittest.TestCase):
    """StimCommand refuses at offer time when medic has no kit."""

    def test_medic_with_no_kit_refused(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 3},
            # No consumables seeded
        )
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient", session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("don't have any stimpack", joined)
        self.assertEqual(_pending_stims, {})

    def test_medic_with_wrong_kit_refused(self):
        """Medic has stimpacks but the player asked for combat_stim."""
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"medicine": 3},
            consumables={"stimpack": 5},  # has stimpack, not combat_stim
        )
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient with combat_stim",
                        session_mgr=sm)
        _run(StimCommand().execute(ctx))
        joined = "\n".join(medic_sess.sent)
        self.assertIn("don't have any combat stim", joined)
        self.assertEqual(_pending_stims, {})

    def test_medic_with_kit_proceeds(self):
        from parser.medical_commands import StimCommand, _pending_stims
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 3},
            consumables={"stimpack": 1},  # exactly one
        )
        target = _make_char(char_id=2, name="Patient")
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        sm = _FakeSessionMgr([medic_sess, target_sess])
        ctx = _make_ctx(db, medic_sess, "Patient", session_mgr=sm)
        _run(StimCommand().execute(ctx))
        # Offer should be staged
        self.assertIn(2, _pending_stims)


# ═══════════════════════════════════════════════════════════════════════════
# 3. TestConsumptionAtResolveSuccess
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumptionAtResolveSuccess(unittest.TestCase):
    """On success, the consumable is decremented from medic's kit."""

    def test_success_decrements_kit(self):
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 5},
            consumables={"stimpack": 3},
        )
        target = _make_char(char_id=2, name="Patient")
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "stimpack",
            "is_self": False, "offered_at": time.time(),
        }
        original = skill_checks.perform_skill_check
        skill_checks.perform_skill_check = lambda *a, **kw: \
            SkillCheckResult(
                roll=20, difficulty=10, success=True, margin=10,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="3D",
            )
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Kit should now have 2 (started 3, consumed 1)
        self.assertEqual(get_consumable_count(medic, "stimpack"), 2)


# ═══════════════════════════════════════════════════════════════════════════
# 4. TestConsumptionAtResolveFailure
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumptionAtResolveFailure(unittest.TestCase):
    """Per design §3.5, failure consumes the stim ('target wastes
    the stim, no benefit')."""

    def test_failure_decrements_kit(self):
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 1},
            consumables={"stimpack": 2},
        )
        target = _make_char(char_id=2, name="Patient")
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "stimpack",
            "is_self": False, "offered_at": time.time(),
        }
        original = skill_checks.perform_skill_check
        skill_checks.perform_skill_check = lambda *a, **kw: \
            SkillCheckResult(
                roll=5, difficulty=10, success=False, margin=-5,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="2D",
            )
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Kit should now be 1 (started 2, consumed 1 on failure)
        self.assertEqual(get_consumable_count(medic, "stimpack"), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 5. TestConsumptionAtResolveFumble
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumptionAtResolveFumble(unittest.TestCase):
    """Fumble path also consumes the stim — it went into the target
    even though it went badly."""

    def test_fumble_decrements_kit(self):
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 1},
            consumables={"stimpack": 1},
        )
        target = _make_char(char_id=2, name="Patient", wound_level=0)
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "stimpack",
            "is_self": False, "offered_at": time.time(),
        }
        original = skill_checks.perform_skill_check
        skill_checks.perform_skill_check = lambda *a, **kw: \
            SkillCheckResult(
                roll=2, difficulty=10, success=False, margin=-8,
                critical_success=False, fumble=True,
                skill_used="first aid", pool_str="2D",
            )
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Kit should be 0 (started 1, consumed 1 — key removed)
        self.assertEqual(get_consumable_count(medic, "stimpack"), 0)
        self.assertFalse(has_consumable(medic, "stimpack"))


# ═══════════════════════════════════════════════════════════════════════════
# 6. TestConsumptionAtResolveSelfStim
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumptionAtResolveSelfStim(unittest.TestCase):
    """Self-stim consumes from the actor's own kit (medic == target)."""

    def test_self_stimpack_decrements_self_kit(self):
        from parser.medical_commands import StimCommand, _pending_stims
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 5},
            consumables={"stimpack": 2},
        )
        db.add_char(medic)
        medic_sess = _FakeSession(character=medic)
        sm = _FakeSessionMgr([medic_sess])
        ctx = _make_ctx(db, medic_sess, "self", session_mgr=sm)
        original = skill_checks.perform_skill_check
        skill_checks.perform_skill_check = lambda *a, **kw: \
            SkillCheckResult(
                roll=20, difficulty=13, success=True, margin=7,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="5D",
            )
        try:
            _run(StimCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # Self-stim should have decremented from 2 to 1
        self.assertEqual(get_consumable_count(medic, "stimpack"), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 7. TestConsumptionPersistsToDb
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumptionPersistsToDb(unittest.TestCase):
    """After consumption, save_character is called with attributes=...
    so the deduction survives a restart."""

    def test_consumption_persists_via_save_character(self):
        from parser.medical_commands import (
            StimAcceptCommand, _pending_stims,
        )
        from engine import skill_checks
        from engine.skill_checks import SkillCheckResult
        _clear_pending()
        db = _FakeDB()
        medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 5},
            consumables={"stimpack": 3},
        )
        target = _make_char(char_id=2, name="Patient")
        db.add_char(medic); db.add_char(target)
        medic_sess = _FakeSession(character=medic)
        target_sess = _FakeSession(character=target)
        _pending_stims[2] = {
            "medic_id": 1, "medic_session": medic_sess,
            "medic_name": "Medic", "consumable_key": "stimpack",
            "is_self": False, "offered_at": time.time(),
        }
        original = skill_checks.perform_skill_check
        skill_checks.perform_skill_check = lambda *a, **kw: \
            SkillCheckResult(
                roll=20, difficulty=10, success=True, margin=10,
                critical_success=False, fumble=False,
                skill_used="first aid", pool_str="3D",
            )
        try:
            ctx = _make_ctx(db, target_sess, "")
            _run(StimAcceptCommand().execute(ctx))
        finally:
            skill_checks.perform_skill_check = original

        # There should be at least one save_character call for char_id=1
        # (the medic) with attributes= in kwargs reflecting the
        # post-consumption state.
        medic_attr_writes = [
            w for w in db.writes
            if w[0] == "save_character"
            and w[1] == 1
            and "attributes" in w[2]
        ]
        self.assertTrue(
            medic_attr_writes,
            "consumption must persist via save_character(medic_id, "
            "attributes=...)",
        )
        # The last such write must show stimpack count of 2 (or no key)
        last_attrs_raw = medic_attr_writes[-1][2]["attributes"]
        if isinstance(last_attrs_raw, str):
            last_attrs = json.loads(last_attrs_raw)
        else:
            last_attrs = last_attrs_raw
        consumables = last_attrs.get("consumables", {})
        # CRAFT.consumable_quality_potency: consumables now store
        # {"count", "quality"} (was a bare int) — read the count via the
        # canonical normalizer (tolerant of both shapes).
        from engine.buffs import _normalize_consumable_entry
        self.assertEqual(
            _normalize_consumable_entry(consumables.get("stimpack", 0))["count"],
            2)


# ═══════════════════════════════════════════════════════════════════════════
# 8. TestDocumentedBifurcation
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentedBifurcation(unittest.TestCase):
    """The stim-section docstring in parser/medical_commands.py must
    no longer claim stims are abstract. SRB.1.b shipped May 24 2026
    moves stims to attributes.consumables; the substrate-decision-1
    block must reflect that.

    Also confirms the storage-bifurcation note is present somewhere
    so a future reader hitting the bifurcation finds the breadcrumb."""

    def test_no_longer_abstract(self):
        path = os.path.join(
            PROJECT_ROOT, "parser", "medical_commands.py",
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Old claim should be gone
        self.assertNotIn(
            "Stims are abstract resources",
            content,
            "Substrate-decision-1 must no longer claim stims are "
            "abstract — SRB.1.b shipped consumption wiring.",
        )

    def test_bifurcation_breadcrumb_present(self):
        path = os.path.join(
            PROJECT_ROOT, "parser", "medical_commands.py",
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Should mention the two-storage-model note
        self.assertTrue(
            "attributes.consumables" in content,
            "Should reference the chosen storage model",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
