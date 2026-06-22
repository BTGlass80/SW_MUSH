# -*- coding: utf-8 -*-
"""
tests/test_qa_force_sensitive_chargen_2026_06_22.py

QA drop: Force-sensitive chargen BLOCKER + cluster fixes (2026-06-22).

Root insight: WEG R&E requires a Force-sensitive character to START with at
least 1D in control/sense/alter ("Ana receives control at 1D and learns one
power"). 0D means you do NOT have the Force skill; from_db_dict correctly
rejects 0D as non-sensitive (pool.is_zero() check). The bugs were purely in
the PRODUCERS writing 0D.

Fixes tested here:
  (a) BLOCKER — server/api.py handle_submit + handle_create_character both
      wrote DicePool(0,0) for force_sensitive chars; changed to DicePool(1,0).
      Round-trip via Character.from_db_dict must yield force_sensitive=True
      and list_powers_for_char non-empty.
  (b) HIGH — parser/padawan_master_training_commands.py _ensure_padawan_skills_one_die
      wrote skill_key into the SKILLS dict; Force skills are ATTRIBUTES so it
      must write to the attrs dict and save via attributes= kwarg.
  (c) MEDIUM — parser/cp_commands.py TrainCommand silently hit "Unknown skill"
      for control/sense/alter; must return a clear teacher-redirect message.

The L2 lockout test (test_qa_l2_force_0d_lockout.py) remains correct and
must not be modified — 0D still means non-sensitive.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _set_era(era_code: str):
    from engine.era_state import set_active_config
    set_active_config(types.SimpleNamespace(active_era=era_code))


def _clear_era():
    from engine.era_state import clear_active_config
    clear_active_config()


# ─────────────────────────────────────────────────────────────────────────────
# Mock infrastructure (mirrors test_drop2b pattern)
# ─────────────────────────────────────────────────────────────────────────────

class _MockDB:
    """Minimal async DB stand-in recording create_character calls."""

    def __init__(self):
        self.accounts = {1}
        self.characters_by_account = {}
        self.fetchall_returns = {}
        self.next_id = 100
        self.created = []       # list of (account_id, fields)
        self.save_calls = []    # list of (cid, kwargs)
        self.inventory = {}

    async def get_account(self, account_id):
        return {"id": account_id} if account_id in self.accounts else None

    async def get_characters(self, account_id):
        return list(self.characters_by_account.get(account_id, []))

    async def fetchall(self, sql, params=()):
        param_blob = " ".join(str(p) for p in (params or ()))
        for needle, rows in self.fetchall_returns.items():
            if needle in sql or needle in param_blob:
                return list(rows)
        return []

    async def create_account(self, username, password_hash):
        aid = max(self.accounts or {0}) + 1
        self.accounts.add(aid)
        return aid

    async def get_account_by_username(self, username):
        return None  # no pre-existing accounts

    async def create_character(self, account_id, fields):
        cid = self.next_id
        self.next_id += 1
        self.created.append((account_id, dict(fields)))
        self.characters_by_account.setdefault(account_id, []).append(
            {"id": cid, "name": fields.get("name")}
        )
        return cid

    async def save_character(self, char_id, **fields):
        self.save_calls.append((char_id, dict(fields)))

    async def add_to_inventory(self, char_id, item):
        self.inventory.setdefault(char_id, []).append(dict(item))

    async def execute(self, *a, **kw):
        pass

    async def commit(self):
        pass


def _build_human_species():
    from engine.character import ATTRIBUTE_NAMES
    from engine.species import Species, AttributeRange
    from engine.dice import DicePool
    return Species(
        name="Human",
        attribute_dice=DicePool(12, 0),
        skill_dice=DicePool(7, 0),
        move=10,
        attributes={
            a: AttributeRange(min_pool=DicePool(2, 0), max_pool=DicePool(4, 0))
            for a in ATTRIBUTE_NAMES
        },
        special_abilities=[],
        story_factors=[],
    )


class _SpeciesRegMini:
    def __init__(self):
        self._sp = _build_human_species()

    def get(self, name):
        return self._sp if (name or "").lower() == "human" else None

    def list_all(self):
        return [self._sp]


class _SkillRegMini:
    def skills_for_attribute(self, attr):
        return []

    def all_skills(self):
        return []


def _build_api(db):
    from server.api import ChargenAPI
    return ChargenAPI(
        species_reg=_SpeciesRegMini(),
        skill_reg=_SkillRegMini(),
        db=db,
    )


class _MockRequest:
    def __init__(self, *, json_body=None, ip="127.0.0.1"):
        self._json_body = json_body or {}
        self.query = {}
        self.headers = {}
        self.transport = MagicMock()
        self.transport.get_extra_info = MagicMock(return_value=(ip, 12345))

    async def json(self):
        return dict(self._json_body)


def _resp_json(resp):
    return json.loads(resp.body.decode("utf-8"))


def _make_token(account_id):
    from server.api import create_login_token
    return create_login_token(account_id, ttl=3600)


def _reset_rate_limits():
    from server import api as api_mod
    api_mod._rate_limits.clear()


def _valid_fs_char_body():
    """A Force-sensitive character payload."""
    return {
        "name": "Kayla Vyn",
        "species": "Human",
        "attributes": {
            "dexterity": "2D",
            "knowledge": "2D",
            "mechanical": "2D",
            "perception": "2D",
            "strength": "2D",
            "technical": "2D",
        },
        "skills": {},
        "force_sensitive": True,
        "background": "",
    }


def _make_db_row_from_fields(fields: dict, char_id: int = 1) -> dict:
    """Build a minimal DB row from create_character field dict."""
    return {
        "id": char_id,
        "account_id": 1,
        "name": fields.get("name", "TestChar"),
        "species": fields.get("species", "Human"),
        "template": fields.get("template", ""),
        "room_id": fields.get("room_id", 1),
        "description": fields.get("description", ""),
        "character_points": fields.get("character_points", 5),
        "force_points": fields.get("force_points", 1),
        "credits": fields.get("credits", 1000),
        "dark_side_points": fields.get("dark_side_points", 0),
        "wound_level": fields.get("wound_level", 0),
        "in_combat": 0,
        "in_hyperspace": 0,
        "docked_at": None,
        "is_active": 1,
        "village_chosen_path": None,
        "attributes": fields.get("attributes", "{}"),
        "skills": fields.get("skills", "{}"),
        "inventory": fields.get("inventory", "[]"),
        "equipped_weapon": "",
        "worn_armor": "",
        "faction_id": fields.get("faction_id", "independent"),
        "chargen_notes": fields.get("chargen_notes", "{}"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# (a) BLOCKER: handle_submit writes 1D, roundtrip yields force_sensitive=True
# ─────────────────────────────────────────────────────────────────────────────

class TestHandleSubmitForceSensitive(unittest.TestCase):
    """BLOCKER: handle_submit force-sensitive char gets 1D attrs; reloads True."""

    def setUp(self):
        _set_era("clone_wars")
        _reset_rate_limits()

    def tearDown(self):
        _clear_era()

    def test_submit_writes_1d_control_sense_alter(self):
        """handle_submit must write '1D' (not '0D') for control/sense/alter
        when force_sensitive=True.  From the DB roundtrip, from_db_dict must
        reconstruct force_sensitive=True."""
        db = _MockDB()
        api = _build_api(db)

        body = {
            "username": "fsuser",
            "password": "pw1234",
            "character": _valid_fs_char_body(),
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        result = _resp_json(resp)
        self.assertTrue(result.get("success"), f"handle_submit failed: {result}")

        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes", "{}"))

        for fa in ("control", "sense", "alter"):
            self.assertIn(fa, attrs, f"'{fa}' missing from persisted attributes")
            self.assertEqual(
                attrs[fa], "1D",
                f"'{fa}' must be '1D' (not '0D') for a force-sensitive chargen char; got {attrs[fa]!r}",
            )

    def test_submit_roundtrip_force_sensitive_true(self):
        """After a submit, reloading the persisted attribute blob via
        Character.from_db_dict must yield force_sensitive=True."""
        from engine.character import Character

        db = _MockDB()
        api = _build_api(db)

        body = {
            "username": "fsuser2",
            "password": "pw1234",
            "character": _valid_fs_char_body(),
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        self.assertTrue(_resp_json(resp).get("success"))

        _aid, fields = db.created[0]
        row = _make_db_row_from_fields(fields)
        char = Character.from_db_dict(row)

        self.assertTrue(
            char.force_sensitive,
            "Reloaded character must be force_sensitive=True after handle_submit "
            f"chargen; attributes JSON was {fields.get('attributes')!r}",
        )

    def test_submit_roundtrip_list_powers_nonempty(self):
        """force_sensitive=True + 1D pools → list_powers_for_char non-empty."""
        from engine.character import Character
        from engine.force_powers import list_powers_for_char

        db = _MockDB()
        api = _build_api(db)

        body = {
            "username": "fsuser3",
            "password": "pw1234",
            "character": _valid_fs_char_body(),
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        self.assertTrue(_resp_json(resp).get("success"))

        _aid, fields = db.created[0]
        row = _make_db_row_from_fields(fields)
        char = Character.from_db_dict(row)

        powers = list_powers_for_char(char)
        self.assertGreater(
            len(powers), 0,
            "A freshly-created force-sensitive character must have at least "
            "one available Force power (all three pools are 1D).",
        )


# ─────────────────────────────────────────────────────────────────────────────
# (a) BLOCKER: handle_create_character (same fix, second endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class TestHandleCreateCharacterForceSensitive(unittest.TestCase):
    """BLOCKER: handle_create_character force-sensitive char gets 1D attrs."""

    def setUp(self):
        _set_era("clone_wars")
        _reset_rate_limits()

    def tearDown(self):
        _clear_era()

    def test_create_character_writes_1d_force_attrs(self):
        """handle_create_character must write '1D' for control/sense/alter."""
        db = _MockDB()
        api = _build_api(db)

        body = {
            "token": _make_token(1),
            "character": _valid_fs_char_body(),
        }
        resp = _run(api.handle_create_character(_MockRequest(json_body=body)))
        result = _resp_json(resp)
        self.assertTrue(result.get("success"), f"handle_create_character failed: {result}")

        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes", "{}"))

        for fa in ("control", "sense", "alter"):
            self.assertIn(fa, attrs, f"'{fa}' missing from persisted attributes")
            self.assertEqual(
                attrs[fa], "1D",
                f"'{fa}' must be '1D'; got {attrs[fa]!r}",
            )

    def test_create_character_roundtrip_force_sensitive_true(self):
        """Reload via Character.from_db_dict after handle_create_character
        must yield force_sensitive=True."""
        from engine.character import Character

        db = _MockDB()
        api = _build_api(db)

        body = {
            "token": _make_token(1),
            "character": _valid_fs_char_body(),
        }
        resp = _run(api.handle_create_character(_MockRequest(json_body=body)))
        self.assertTrue(_resp_json(resp).get("success"))

        _aid, fields = db.created[0]
        row = _make_db_row_from_fields(fields)
        char = Character.from_db_dict(row)

        self.assertTrue(
            char.force_sensitive,
            "handle_create_character round-trip must yield force_sensitive=True; "
            f"attributes JSON was {fields.get('attributes')!r}",
        )

    def test_create_character_roundtrip_list_powers_nonempty(self):
        """list_powers_for_char must be non-empty after create-character chargen."""
        from engine.character import Character
        from engine.force_powers import list_powers_for_char

        db = _MockDB()
        api = _build_api(db)

        body = {
            "token": _make_token(1),
            "character": _valid_fs_char_body(),
        }
        resp = _run(api.handle_create_character(_MockRequest(json_body=body)))
        self.assertTrue(_resp_json(resp).get("success"))

        _aid, fields = db.created[0]
        row = _make_db_row_from_fields(fields)
        char = Character.from_db_dict(row)

        powers = list_powers_for_char(char)
        self.assertGreater(len(powers), 0, "list_powers_for_char must be non-empty")


# ─────────────────────────────────────────────────────────────────────────────
# (b) HIGH: _ensure_padawan_skills_one_die writes to attrs, not skills
# ─────────────────────────────────────────────────────────────────────────────

class TestEnsurePadawanSkillsWritesToAttributes(unittest.TestCase):
    """HIGH: +teach Force power must write the raised skill to attributes blob."""

    def _make_padawan_row(self, *, attrs=None, skills=None, cp=30):
        """Build a minimal padawan DB row dict."""
        return {
            "id": 77,
            "name": "Cadet Ren",
            "attributes": json.dumps(attrs or {"dexterity": "2D", "strength": "2D"}),
            "skills": json.dumps(skills or {}),
            "character_points": cp,
        }

    def _make_power_stub(self, skill_keys):
        """Minimal ForcePower-like stub with a .skills list."""
        p = types.SimpleNamespace()
        p.skills = list(skill_keys)
        return p

    def _make_ctx_with_save_capture(self):
        """Build a minimal ctx whose db.save_character captures kwargs."""
        saved = {}

        class _DB:
            async def save_character(self_db, char_id, **fields):
                saved["char_id"] = char_id
                saved.update(fields)

        ctx = types.SimpleNamespace(db=_DB())
        return ctx, saved

    def test_teach_writes_control_to_attributes(self):
        """When control is raised from 0 → 1D by +teach, the saved column
        must be 'attributes', NOT 'skills'."""
        from parser.padawan_master_training_commands import _ensure_padawan_skills_one_die

        ctx, saved = self._make_ctx_with_save_capture()
        padawan = self._make_padawan_row(attrs={"dexterity": "2D"}, cp=30)
        power = self._make_power_stub(["control"])

        result = _run(_ensure_padawan_skills_one_die(ctx, padawan, power))
        self.assertNotIn("error", result, f"Unexpected error: {result.get('error')}")
        self.assertIn("control", result.get("skills_raised", []))

        # The save must have gone through attributes=, NOT skills=
        self.assertIn(
            "attributes", saved,
            "save_character must receive 'attributes' kwarg when a Force skill is raised",
        )
        self.assertNotIn(
            "skills", saved,
            "save_character must NOT receive 'skills' kwarg for a Force-attr raise",
        )

        # Verify the value is correct
        persisted_attrs = json.loads(saved["attributes"])
        self.assertEqual(
            persisted_attrs.get("control"), "1D",
            f"control must be '1D' in persisted attributes; got {persisted_attrs!r}",
        )

    def test_teach_force_sensitive_reconstructed_after_teach(self):
        """After a +teach persists control=1D in attributes, a Character
        loaded from the updated row must be force_sensitive=True."""
        from engine.character import Character
        from parser.padawan_master_training_commands import _ensure_padawan_skills_one_die

        ctx, saved = self._make_ctx_with_save_capture()
        initial_attrs = {"dexterity": "3D", "strength": "2D"}
        padawan = self._make_padawan_row(attrs=initial_attrs, cp=30)
        power = self._make_power_stub(["control"])

        result = _run(_ensure_padawan_skills_one_die(ctx, padawan, power))
        self.assertNotIn("error", result)

        # Simulate reloading character from DB with the updated attributes
        updated_attrs_json = saved["attributes"]  # what was written
        row = {
            "id": 77, "account_id": 1, "name": "Cadet Ren",
            "species": "Human", "template": "", "room_id": 1,
            "description": "", "character_points": 20, "force_points": 1,
            "credits": 500, "dark_side_points": 0, "wound_level": 0,
            "in_combat": 0, "in_hyperspace": 0, "docked_at": None,
            "is_active": 1, "village_chosen_path": None,
            "attributes": updated_attrs_json,
            "skills": json.dumps({}),
            "inventory": "[]", "equipped_weapon": "", "worn_armor": "",
            "faction_id": "independent", "chargen_notes": "{}",
        }
        char = Character.from_db_dict(row)
        self.assertTrue(
            char.force_sensitive,
            "After +teach writes control=1D to attributes, reloaded char "
            "must be force_sensitive=True",
        )

    def test_teach_skill_already_present_in_attrs_skipped(self):
        """If the Force skill is already at 1D in attrs, no CP is spent
        and no save is issued."""
        from parser.padawan_master_training_commands import _ensure_padawan_skills_one_die

        ctx, saved = self._make_ctx_with_save_capture()
        # Padawan already has control at 2D in attrs
        padawan = self._make_padawan_row(
            attrs={"dexterity": "2D", "control": "2D"}, cp=10
        )
        power = self._make_power_stub(["control"])

        result = _run(_ensure_padawan_skills_one_die(ctx, padawan, power))
        self.assertNotIn("error", result)
        self.assertEqual(result.get("cp_spent", 0), 0, "No CP spent if skill already 1D+")
        self.assertEqual(result.get("skills_raised", []), [], "No skills raised")
        # save_character must NOT be called
        self.assertNotIn("attributes", saved, "No save issued when skill already present")


# ─────────────────────────────────────────────────────────────────────────────
# (c) MEDIUM: train control|sense|alter returns teacher-redirect message
# ─────────────────────────────────────────────────────────────────────────────

class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, line):
        self.sent.append(line)


class TestTrainForceSkillRedirect(unittest.TestCase):
    """MEDIUM: `train control/sense/alter` must produce a teacher-redirect message."""

    def _make_ctx(self, skill_name, character=None):
        from parser.commands import CommandContext
        char = character or {"id": 1, "name": "TestChar"}
        session = _FakeSession(character=char)
        ctx = CommandContext(
            session=session,
            raw_input=f"train {skill_name}",
            command="train",
            args=skill_name,
            args_list=[skill_name],
            db=None,
            session_mgr=MagicMock(),
        )
        return ctx, session

    def test_train_control_returns_redirect(self):
        """train control must not say 'Unknown skill'; must explain +teach."""
        from parser.cp_commands import TrainCommand

        ctx, session = self._make_ctx("control")
        _run(TrainCommand().execute(ctx))

        combined = " ".join(session.sent).lower()
        self.assertNotIn(
            "unknown skill",
            combined,
            "train control must not produce 'Unknown skill' message",
        )
        self.assertTrue(
            "teach" in combined or "master" in combined or "teacher" in combined,
            f"train control must mention +teach or master/teacher bond; got: {session.sent}",
        )

    def test_train_sense_returns_redirect(self):
        """train sense must produce the teacher-redirect, not an error."""
        from parser.cp_commands import TrainCommand

        ctx, session = self._make_ctx("sense")
        _run(TrainCommand().execute(ctx))

        combined = " ".join(session.sent).lower()
        self.assertNotIn("unknown skill", combined)
        self.assertTrue(
            "teach" in combined or "master" in combined or "teacher" in combined,
            f"train sense must mention +teach/master; got: {session.sent}",
        )

    def test_train_alter_returns_redirect(self):
        """train alter must produce the teacher-redirect, not an error."""
        from parser.cp_commands import TrainCommand

        ctx, session = self._make_ctx("alter")
        _run(TrainCommand().execute(ctx))

        combined = " ".join(session.sent).lower()
        self.assertNotIn("unknown skill", combined)
        self.assertTrue(
            "teach" in combined or "master" in combined or "teacher" in combined,
            f"train alter must mention +teach/master; got: {session.sent}",
        )

    def test_train_normal_skill_still_works(self):
        """The Force-skill guard must not accidentally intercept normal skills.
        train blaster must not produce the Force-redirect message.
        (It may fail for other reasons — no CP etc. — but not Force redirect.)"""
        from parser.cp_commands import TrainCommand

        # For a normal skill, execute goes past our guard and needs a DB.
        # Give it a stub that returns a minimal character row so the command
        # can proceed to the CP-check stage (and fail there, not at the guard).
        from engine.character import Character
        from engine.dice import DicePool

        char_row = {
            "id": 1, "account_id": 1, "name": "TestChar",
            "species": "Human", "template": "", "room_id": 1,
            "description": "", "character_points": 0,  # no CP → cost check fails
            "force_points": 1, "credits": 500, "dark_side_points": 0,
            "wound_level": 0, "in_combat": 0, "in_hyperspace": 0,
            "docked_at": None, "is_active": 1, "village_chosen_path": None,
            "attributes": json.dumps({
                "dexterity": "3D", "knowledge": "2D", "mechanical": "2D",
                "perception": "2D", "strength": "2D", "technical": "2D",
            }),
            "skills": "{}", "inventory": "[]",
            "equipped_weapon": "", "worn_armor": "",
            "faction_id": "independent", "chargen_notes": "{}",
        }

        class _StubDB:
            async def get_character(self_db, char_id):
                return char_row

        from parser.commands import CommandContext
        char = {"id": 1, "name": "TestChar"}
        session = _FakeSession(character=char)
        ctx = CommandContext(
            session=session,
            raw_input="train blaster",
            command="train",
            args="blaster",
            args_list=["blaster"],
            db=_StubDB(),
            session_mgr=MagicMock(),
        )

        _run(TrainCommand().execute(ctx))

        combined = " ".join(session.sent).lower()
        # The Force redirect message must NOT appear for a normal skill
        self.assertNotIn(
            "force skills",
            combined,
            "Normal skills must not get the Force-redirect message",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Non-sensitive chargen is unaffected (regression pin)
# ─────────────────────────────────────────────────────────────────────────────

class TestNonForceSensitiveChargenUnchanged(unittest.TestCase):
    """Regression: non-force-sensitive chargen must not get Force attrs."""

    def setUp(self):
        _set_era("clone_wars")
        _reset_rate_limits()

    def tearDown(self):
        _clear_era()

    def test_non_fs_submit_no_force_attrs(self):
        """force_sensitive=False → no control/sense/alter in attributes."""
        from engine.character import Character

        db = _MockDB()
        api = _build_api(db)

        char_body = _valid_fs_char_body()
        char_body["force_sensitive"] = False
        char_body["name"] = "Roark Brewer"

        body = {
            "username": "normuser",
            "password": "pw1234",
            "character": char_body,
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        self.assertTrue(_resp_json(resp).get("success"))

        _aid, fields = db.created[0]
        attrs = json.loads(fields.get("attributes", "{}"))
        for fa in ("control", "sense", "alter"):
            self.assertNotIn(
                fa, attrs,
                f"Non-force-sensitive char must not have '{fa}' in attributes",
            )

        row = _make_db_row_from_fields(fields)
        char = Character.from_db_dict(row)
        self.assertFalse(
            char.force_sensitive,
            "Non-force-sensitive chargen must produce force_sensitive=False after reload",
        )


if __name__ == "__main__":
    unittest.main()
