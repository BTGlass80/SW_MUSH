# -*- coding: utf-8 -*-
"""
tests/test_chargen_hardening_2026_07_03.py

SW_MUSH CHARGEN hardening drop (2026-07-03) — 3 launch blockers + 1 minor,
found by a break-it pass on the onboarding entry point.

  (1) S1 — 3 of 9 chargen templates (clone_trooper, republic_officer,
      cis_field_agent) summed to 53/54 attribute pips (WEG-illegal, self-
      blocking finalize via CreationEngine._validate()); clone_trooper
      also overspent skills by 4 pips. Fixed the DATA in
      data/worlds/clone_wars/chargen_templates.yaml (the engine's
      validation was already correct).

  (2) S1, HARD-INVARIANT VIOLATION — force_sensitive was directly
      settable via the web chargen SPA ("STEP 4: THE FORCE") and
      accepted server-side (server/api.py handle_submit /
      handle_create_character), letting a raw POST mint a free
      Jedi-track character. force_sensitive is DERIVED state (from
      control/sense/alter presence in the attributes JSON) — never
      player-set. Closed at three seams:
        - static/chargen.html: removed the Force step entirely (mirrors
          the telnet CreationWizard, which already dropped it per
          PG.3.gates.b).
        - engine/chargen_validator.py: validate_chargen_submission()
          now REJECTS force_sensitive=true or control/sense/alter
          attribute keys.
        - server/api.py: both handlers hard-code
          char_obj.force_sensitive = False regardless of client input
          (defense-in-depth against a validator bypass).

  (3) S1 — server/api.py::handle_submit created the account row BEFORE
      the character-name-collision check, and its except block never
      rolled it back on failure — a taken character name orphaned a
      0-character account squatting the username, with no recovery.
      Fixed with a name-availability pre-check BEFORE account creation
      (the common case never touches the accounts table), plus a
      TOCTOU backstop in the except block that deletes the just-created
      account on ANY character-creation failure.

  (4) S3 minor — engine/creation.py::_match_attribute prefix-matched
      control/sense/alter alongside the 6 real ATTRIBUTE_NAMES, so
      `set control 3D` in the text/freeform chargen wizard silently ate
      the core-attribute budget (both dicts get summed by the same
      _attr_pips_spent/_total helpers) and soft-locked next/done with a
      message that never named Control. Fixed by excluding force attrs
      from _match_attribute — chargen text input can no longer touch
      them at all.

Harness style mirrors tests/test_qa_h7_chargen_skill_cap.py (real
CreationEngine/CreationWizard against real SpeciesRegistry/SkillRegistry)
and tests/test_qa_force_sensitive_chargen_2026_06_22.py (ChargenAPI
against a mocked aiohttp Request + a real in-memory Database).
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEMPLATES_PATH = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "chargen_templates.yaml"
SPECIES_DIR = PROJECT_ROOT / "data" / "species"
SKILLS_PATH = PROJECT_ROOT / "data" / "skills.yaml"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _set_era(era_code: str):
    from engine.era_state import set_active_config
    set_active_config(types.SimpleNamespace(active_era=era_code))


def _clear_era():
    from engine.era_state import clear_active_config
    clear_active_config()


# ── shared real registries (mirrors test_qa_h7_chargen_skill_cap.py) ───────

@pytest.fixture(scope="module")
def species_reg():
    from engine.species import SpeciesRegistry
    reg = SpeciesRegistry()
    reg.load_directory(str(SPECIES_DIR))
    return reg


@pytest.fixture(scope="module")
def skill_reg():
    from engine.character import SkillRegistry
    reg = SkillRegistry()
    reg.load_file(str(SKILLS_PATH))
    return reg


# ═══════════════════════════════════════════════════════════════════════════
# (1) All 9 chargen templates are WEG-D6-legal
# ═══════════════════════════════════════════════════════════════════════════

class TestTemplatesLegal:

    def test_nine_templates_present(self):
        with open(TEMPLATES_PATH, encoding="utf-8") as fh:
            templates = yaml.safe_load(fh)["templates"]
        assert len(templates) == 9

    def test_every_template_pip_math_is_legal(self):
        """Direct pip-math check against the YAML (independent of the
        engine), pinning the exact bug: attributes must sum to EXACTLY
        the species budget (54 pips / 18D for Human) and skills must not
        exceed the skill budget (21 pips / 7D)."""
        from engine.dice import DicePool

        with open(TEMPLATES_PATH, encoding="utf-8") as fh:
            templates = yaml.safe_load(fh)["templates"]

        for key, tmpl in templates.items():
            attr_total = sum(
                DicePool.parse(v).total_pips() for v in tmpl["attributes"].values()
            )
            skill_total = sum(
                DicePool.parse(v).total_pips() for v in tmpl["skills"].values()
            )
            assert attr_total == 54, (
                f"{key}: attributes sum to {attr_total} pips, expected 54 (18D)"
            )
            assert skill_total <= 21, (
                f"{key}: skills sum to {skill_total} pips, budget is 21 (7D)"
            )

    def test_every_template_finalizes_via_creation_engine(self, species_reg, skill_reg):
        from engine.creation import CreationEngine, TEMPLATES

        assert len(TEMPLATES) == 9
        for key in TEMPLATES:
            eng = CreationEngine(species_reg, skill_reg)
            display, _, _ = eng.process_input(f"template {key}")
            assert "Unknown template" not in display, f"{key}: {display}"
            eng.process_input("name Test Character")
            errors = eng._validate()
            assert errors == [], f"{key} failed to finalize cleanly: {errors}"

    def test_every_template_finalizes_via_creation_wizard(self, species_reg, skill_reg):
        """Full guided-wizard walkthrough per template: welcome -> template
        select -> skills -> background/name -> (CW: tutorial chain, skipped
        as an alt) -> review -> done. Pins the SAME finalize gate the real
        telnet wizard uses (engine/creation_wizard.py wraps CreationEngine).
        """
        from engine.creation_wizard import (
            CreationWizard, STEP_TUTORIAL_CHAIN, STEP_REVIEW,
        )
        from engine.creation import TEMPLATES

        _set_era("clone_wars")
        try:
            for key in TEMPLATES:
                w = CreationWizard(species_reg, skill_reg, is_first_character=False)

                # STEP_WELCOME -> choose the template path
                w.process_input("1")
                # STEP_TEMPLATE_SELECT -> pick this template
                display, _, _ = w.process_input(key)
                assert "Unknown template" not in display, f"{key}: {display}"
                # STEP_SKILLS -> next (template already allocated skills)
                w.process_input("next")
                # STEP_BACKGROUND -> name, then next
                w.process_input("name Test Character")
                w.process_input("next")
                # CW inserts STEP_TUTORIAL_CHAIN; an alt (is_first_character=
                # False) may skip it with "next". GCW/no-corpus eras land
                # straight on STEP_REVIEW and this branch is a no-op.
                if w.step == STEP_TUTORIAL_CHAIN:
                    w.process_input("next")

                assert w.step == STEP_REVIEW, (
                    f"{key}: wizard stuck at step {w.step!r} instead of review"
                )
                display, prompt, done = w.process_input("done")
                assert done, f"{key}: did not finalize: {display}"
                assert "Cannot finalize" not in display, f"{key}: {display}"

                # The finalized Character must carry zero core-attribute or
                # skill budget errors per the same validator finalize()
                # trusts.
                assert w.engine._validate() == [], key
        finally:
            _clear_era()


# ═══════════════════════════════════════════════════════════════════════════
# (2) force_sensitive is rejected server-side, never player-settable
# ═══════════════════════════════════════════════════════════════════════════

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


async def _fresh_real_db():
    """Real Database on :memory: with the FULL production schema — needed
    to exercise the actual UNIQUE constraint on characters.name (Part 3)
    and to round-trip Character.from_db_dict (Part 2) faithfully."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


def _reset_rate_limits():
    from server import api as api_mod
    api_mod._rate_limits.clear()


def _valid_char_body(name="Kayla Vyn"):
    return {
        "name": name,
        "species": "Human",
        "attributes": {
            "dexterity": "3D+1",
            "knowledge": "2D+1",
            "mechanical": "4D",
            "perception": "3D+1",
            "strength": "2D+2",
            "technical": "2D+1",
        },
        "skills": {},
        "background": "",
    }


class TestForceSensitiveRejected(unittest.TestCase):
    """A chargen submission carrying force_sensitive=true, or control/
    sense/alter attribute keys, must be REJECTED — no character is ever
    created carrying them, and a from_db_dict reload re-derives False."""

    def setUp(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        self.db = _run(_fresh_real_db())

    def tearDown(self):
        _clear_era()

    def _build_api(self):
        from server.api import ChargenAPI
        from engine.species import SpeciesRegistry
        from engine.character import SkillRegistry
        species_reg = SpeciesRegistry()
        species_reg.load_directory(str(SPECIES_DIR))
        skill_reg = SkillRegistry()
        skill_reg.load_file(str(SKILLS_PATH))
        return ChargenAPI(species_reg=species_reg, skill_reg=skill_reg, db=self.db)

    def test_submit_force_sensitive_true_rejected(self):
        api = self._build_api()
        char_body = _valid_char_body("Kayla Vyn")
        char_body["force_sensitive"] = True

        body = {
            "username": "fsattempt",
            "password": "pw123456",
            "character": char_body,
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        result = _resp_json(resp)

        self.assertFalse(result.get("success"), f"must reject: {result}")
        errors_blob = " ".join(
            m for msgs in result.get("errors", {}).values() for m in msgs
        ).lower()
        self.assertIn("force_sensitive", errors_blob)

        # No account, no character.
        self.assertIsNone(_run(self.db.authenticate("fsattempt", "pw123456")))
        self.assertIsNone(_run(self.db.get_character_by_name("Kayla Vyn")))

    def test_submit_control_attribute_key_rejected(self):
        """Smuggling 'control' into attributes (force_sensitive omitted)
        is rejected too — the derived-state guard is key-presence-based,
        not just the boolean flag."""
        api = self._build_api()
        char_body = _valid_char_body("Sly Attempt")
        char_body["attributes"]["control"] = "1D"

        body = {
            "username": "sneakattempt",
            "password": "pw123456",
            "character": char_body,
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        result = _resp_json(resp)

        self.assertFalse(result.get("success"), f"must reject: {result}")
        errors_blob = " ".join(
            m for msgs in result.get("errors", {}).values() for m in msgs
        ).lower()
        self.assertIn("control", errors_blob)
        self.assertIsNone(_run(self.db.get_character_by_name("Sly Attempt")))

    def test_create_character_force_sensitive_true_rejected(self):
        """Same rejection via the embedded create-character endpoint."""
        from server.api import create_login_token

        api = self._build_api()
        account_id = _run(self.db.create_account("embeduser", "pw123456"))
        token = create_login_token(account_id, ttl=3600)

        char_body = _valid_char_body("Embedded Attempt")
        char_body["force_sensitive"] = True
        body = {"token": token, "character": char_body}

        resp = _run(api.handle_create_character(_MockRequest(json_body=body)))
        result = _resp_json(resp)

        self.assertFalse(result.get("success"), f"must reject: {result}")
        errors_blob = " ".join(
            m for msgs in result.get("errors", {}).values() for m in msgs
        ).lower()
        self.assertIn("force_sensitive", errors_blob)
        self.assertIsNone(_run(self.db.get_character_by_name("Embedded Attempt")))

    def test_non_force_sensitive_submit_still_succeeds_and_reloads_false(self):
        """Regression: a normal (non-FS) submission is unaffected, and
        Character.from_db_dict re-derives force_sensitive=False with no
        control/sense/alter and the default (non-FS) force_points."""
        from engine.character import Character

        api = self._build_api()
        body = {
            "username": "normaluser",
            "password": "pw123456",
            "character": _valid_char_body("Roark Brewer"),
        }
        resp = _run(api.handle_submit(_MockRequest(json_body=body)))
        result = _resp_json(resp)
        self.assertTrue(result.get("success"), f"normal chargen must succeed: {result}")

        row = _run(self.db.get_character_by_name("Roark Brewer"))
        self.assertIsNotNone(row)
        attrs = json.loads(row["attributes"])
        for fa in ("control", "sense", "alter"):
            self.assertNotIn(fa, attrs)

        char = Character.from_db_dict(row)
        self.assertFalse(char.force_sensitive)
        self.assertEqual(char.force_points, 1)  # non-FS default


# ═══════════════════════════════════════════════════════════════════════════
# (3) A name-collision submit leaves no orphaned account row (transactional)
# ═══════════════════════════════════════════════════════════════════════════

class TestTransactionalAccountCreation(unittest.TestCase):
    """handle_submit must not leave a 0-character account squatting a
    username when character creation fails."""

    def setUp(self):
        _set_era("clone_wars")
        _reset_rate_limits()
        self.db = _run(_fresh_real_db())

    def tearDown(self):
        _clear_era()

    def _build_api(self):
        from server.api import ChargenAPI
        from engine.species import SpeciesRegistry
        from engine.character import SkillRegistry
        species_reg = SpeciesRegistry()
        species_reg.load_directory(str(SPECIES_DIR))
        skill_reg = SkillRegistry()
        skill_reg.load_file(str(SKILLS_PATH))
        return ChargenAPI(species_reg=species_reg, skill_reg=skill_reg, db=self.db)

    def test_name_collision_precheck_never_creates_account(self):
        """The common case: a taken name is caught by the pre-check, so
        the accounts table is never touched at all for the retry."""
        api = self._build_api()

        # First chargen succeeds and claims the name.
        first = _run(api.handle_submit(_MockRequest(json_body={
            "username": "firstuser",
            "password": "pw123456",
            "character": _valid_char_body("Popular Name"),
        })))
        self.assertTrue(_resp_json(first).get("success"))

        # Second chargen, different username, SAME character name -> reject.
        second_resp = _run(api.handle_submit(_MockRequest(json_body={
            "username": "seconduser",
            "password": "pw123456",
            "character": _valid_char_body("Popular Name"),
        })))
        second = _resp_json(second_resp)
        self.assertFalse(second.get("success"), f"collision must be rejected: {second}")

        # The username from the failed attempt must NOT exist — no orphan.
        self.assertIsNone(
            _run(self.db.authenticate("seconduser", "pw123456")),
            "a rejected chargen must not leave a usable account behind",
        )

    def test_toctou_race_backstop_deletes_orphaned_account(self):
        """Simulates the race the pre-check can't catch: a character row
        holds the name but is invisible to get_character_by_name's
        is_active=1 filter (e.g. a soft-deleted/inactive row occupying the
        UNIQUE slot), so the pre-check reports the name available and the
        account gets created — then the real INSERT still hits the UNIQUE
        constraint. The except-block backstop must delete the just-created
        account rather than leaving it orphaned."""
        api = self._build_api()

        # Seed an INACTIVE character occupying the name — invisible to the
        # pre-check (is_active=1 filter) but still UNIQUE-constrained at
        # the DB level, reproducing the TOCTOU window.
        seed_account_id = _run(self.db.create_account("seedowner", "pw123456"))
        _run(self.db._db.execute(
            "INSERT INTO characters (account_id, name, is_active) "
            "VALUES (?, ?, 0)",
            (seed_account_id, "Race Condition"),
        ))
        _run(self.db._db.commit())

        # Pre-check must report it as available (is_active=0 is invisible).
        self.assertIsNone(_run(self.db.get_character_by_name("Race Condition")))

        resp = _run(api.handle_submit(_MockRequest(json_body={
            "username": "raceuser",
            "password": "pw123456",
            "character": _valid_char_body("Race Condition"),
        })))
        result = _resp_json(resp)
        self.assertFalse(result.get("success"), f"the real INSERT must still fail: {result}")

        # No orphaned account: the backstop must have deleted it.
        self.assertIsNone(
            _run(self.db.authenticate("raceuser", "pw123456")),
            "the except-block backstop must roll back the orphaned account "
            "on a UNIQUE-constraint race",
        )


# ═══════════════════════════════════════════════════════════════════════════
# (4) `set control/sense/alter` cannot corrupt the attribute budget
# ═══════════════════════════════════════════════════════════════════════════

class TestSetForceAttrRejectedInFreeform:

    def test_set_control_is_rejected_not_silently_absorbed(self, species_reg, skill_reg):
        from engine.creation import CreationEngine

        eng = CreationEngine(species_reg, skill_reg)
        display, _, _ = eng.process_input("set control 3D")
        assert "unknown attribute" in display.lower(), display
        assert "control" not in eng.state.attributes

    def test_budget_uncorrupted_after_set_control_attempt(self, species_reg, skill_reg):
        """Spend the full legitimate 18D budget across the 6 real
        attributes, THEN attempt `set control 3D` — the budget must
        still read exactly spent (0 remaining), not polluted."""
        from engine.creation import CreationEngine

        eng = CreationEngine(species_reg, skill_reg)
        eng.process_input("species human")
        for attr, dice in (
            ("dexterity", "3D"), ("knowledge", "3D"), ("mechanical", "3D"),
            ("perception", "3D"), ("strength", "3D"), ("technical", "3D"),
        ):
            eng.process_input(f"set {attr} {dice}")
        assert eng._attr_pips_total() - eng._attr_pips_spent() == 0

        eng.process_input("set control 3D")

        # The illegitimate attempt must not have touched the budget.
        assert eng._attr_pips_total() - eng._attr_pips_spent() == 0
        assert "control" not in eng.state.attributes

        eng.process_input("name Budget Check")
        errors = eng._validate()
        assert not any("control" in e.lower() for e in errors)
        assert errors == [] or all("skill" in e.lower() for e in errors)

    def test_set_sense_and_alter_also_rejected(self, species_reg, skill_reg):
        from engine.creation import CreationEngine

        eng = CreationEngine(species_reg, skill_reg)
        for fa in ("sense", "alter"):
            display, _, _ = eng.process_input(f"set {fa} 2D")
            assert "unknown attribute" in display.lower(), (fa, display)
            assert fa not in eng.state.attributes


if __name__ == "__main__":
    unittest.main()
