# -*- coding: utf-8 -*-
"""
tests/test_f7n_force_attribute_seeding.py — F.7.n
(Force-attribute seeding for Path A / B / C commits).

Pre-F.7.n, the three Path commit functions in
``engine/village_choice.py`` set ``char["force_sensitive"] = 1``
in-memory only. The ``force_sensitive`` state is NOT a DB column —
``Character.from_db_dict`` reconstructs it from the presence of
``control`` / ``sense`` / ``alter`` keys in the ``attributes`` JSON
blob (see ``engine/character.py`` L583-586). With no
Force-attribute seeds persisted, the next login reconstructed
``force_sensitive=False`` and silently broke the player's chosen
Jedi or Dark path.

F.7.n closes this by adding ``_seed_force_attributes(db, char)``
to ``engine/village_choice.py`` and wiring it into all three
Path commit flows after the main ``save_character`` call. WEG D6
R&E convention: a freshly-awakened Force-sensitive starts at 1D
in each of control / sense / alter.

Tests
=====

  1. TestSeedHelperPersists — ``_seed_force_attributes`` writes
     the three Force attributes to the attributes JSON and
     persists via save_character.
  2. TestSeedHelperIdempotent — calling the helper twice does
     NOT downgrade an advanced character. Pre-existing Force
     attributes are preserved.
  3. TestSeedHelperFailureTolerant — exceptions inside the
     helper are swallowed and the function returns False.
  4. TestPathACommitSeeds — _commit_path_a fires the seed.
  5. TestPathBCommitSeeds — _commit_path_b fires the seed.
  6. TestPathCCommitSeeds — _commit_path_c fires the seed
     (Path C is Force-sensitive too, just exiled from the
     Order).
  7. TestReloadReconstructsForceSensitive — after Path A
     commit + simulated reload via from_db_dict, the new
     Character has force_sensitive=True. End-to-end pin.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ─────────────────────────────────────────────────────────────────────
# Fixtures — minimal char + DB stub matching the F.7.d pattern
# ─────────────────────────────────────────────────────────────────────


def _make_char(**overrides):
    """A minimal CW character ready for a Path commit. The
    village_choice_completed flag is False — the path-commit
    function sets it. attributes/skills/chargen_notes start
    empty per a freshly-created CW PC.
    """
    char = {
        "id": 42,
        "name": "Test PC",
        "attributes": "{}",
        "skills": "{}",
        "chargen_notes": "{}",
        "village_choice_completed": 0,
        "village_chosen_path": None,
        "room_id": 290,  # Master's Chamber
    }
    char.update(overrides)
    return char


class _FakeDB:
    """Minimal DB stub. save_character mirrors the writable-column
    allowlist behavior but writes back to the char dict."""

    def __init__(self, char):
        self._char = char
        self.saves: list[dict] = []
        self._orgs = {
            "jedi_order": {"id": 100, "code": "jedi_order"},
            "independent": {"id": 101, "code": "independent"},
        }
        self.joined: list[tuple[int, int]] = []
        self.rep_changes: list[tuple[int, str, int]] = []
        self._slug_to_room_id = {}

    async def save_character(self, char_id, **kwargs):
        # Enforce the real allowlist; phantom-column bugs surface here.
        from db.database import Database
        bad = set(kwargs.keys()) - Database._CHARACTER_WRITABLE_COLUMNS
        if bad:
            raise ValueError(
                f"FakeDB.save_character: non-writable kwargs: {bad}"
            )
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v

    async def get_room(self, room_id):
        return {"id": room_id, "name": "Test Room"}

    async def get_organization(self, code):
        return self._orgs.get(code)

    async def join_organization(self, char_id, org_id, specialization=""):
        self.joined.append((char_id, org_id))
        return True

    async def adjust_rep(self, char_id, org_code, delta):
        self.rep_changes.append((char_id, org_code, delta))

    async def get_room_by_slug(self, slug):
        rid = self._slug_to_room_id.get(slug)
        if rid is None:
            return None
        return {"id": rid, "slug": slug}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ═════════════════════════════════════════════════════════════════════
# 1. _seed_force_attributes helper persists
# ═════════════════════════════════════════════════════════════════════


class TestSeedHelperPersists(unittest.TestCase):

    def test_seed_writes_three_force_attributes(self):
        from engine.village_choice import _seed_force_attributes
        char = _make_char()
        db = _FakeDB(char)
        result = _run(_seed_force_attributes(db, char))
        self.assertTrue(result, "Seed helper should report True (wrote)")
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs.get("control"), "1D")
        self.assertEqual(attrs.get("sense"), "1D")
        self.assertEqual(attrs.get("alter"), "1D")

    def test_seed_persists_via_save_character(self):
        from engine.village_choice import _seed_force_attributes
        char = _make_char()
        db = _FakeDB(char)
        _run(_seed_force_attributes(db, char))
        # Exactly one save_character call (or one for this helper —
        # combined with other path-commit saves in the integration tests)
        attrs_saves = [s for s in db.saves if "attributes" in s]
        self.assertEqual(len(attrs_saves), 1)
        persisted = json.loads(attrs_saves[0]["attributes"])
        self.assertEqual(persisted.get("control"), "1D")
        self.assertEqual(persisted.get("sense"), "1D")
        self.assertEqual(persisted.get("alter"), "1D")

    def test_seed_preserves_existing_non_force_attributes(self):
        from engine.village_choice import _seed_force_attributes
        char = _make_char()
        char["attributes"] = json.dumps({
            "dexterity": "3D",
            "knowledge": "2D",
        })
        db = _FakeDB(char)
        _run(_seed_force_attributes(db, char))
        attrs = json.loads(char["attributes"])
        # Non-Force attributes still present.
        self.assertEqual(attrs.get("dexterity"), "3D")
        self.assertEqual(attrs.get("knowledge"), "2D")
        # Force attributes added.
        self.assertEqual(attrs.get("control"), "1D")
        self.assertEqual(attrs.get("sense"), "1D")
        self.assertEqual(attrs.get("alter"), "1D")


# ═════════════════════════════════════════════════════════════════════
# 2. Idempotency
# ═════════════════════════════════════════════════════════════════════


class TestSeedHelperIdempotent(unittest.TestCase):

    def test_seed_skips_if_any_force_attr_present(self):
        """If ANY of control/sense/alter is already in attributes,
        the helper is a no-op. Protects advanced characters from
        being downgraded by a Path-commit replay."""
        from engine.village_choice import _seed_force_attributes
        char = _make_char()
        char["attributes"] = json.dumps({
            "control": "5D+2",  # Advanced character
        })
        db = _FakeDB(char)
        result = _run(_seed_force_attributes(db, char))
        self.assertFalse(result, "Seed helper should report False (no-op)")
        # save_character should not have been called.
        self.assertEqual(len(db.saves), 0)
        # attributes preserved exactly.
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs.get("control"), "5D+2")
        # And sense/alter were NOT auto-added (helper is all-or-nothing).
        self.assertNotIn("sense", attrs)
        self.assertNotIn("alter", attrs)

    def test_seed_skips_with_only_sense_present(self):
        from engine.village_choice import _seed_force_attributes
        char = _make_char()
        char["attributes"] = json.dumps({"sense": "2D"})
        db = _FakeDB(char)
        result = _run(_seed_force_attributes(db, char))
        self.assertFalse(result)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs.get("sense"), "2D")
        self.assertNotIn("control", attrs)


# ═════════════════════════════════════════════════════════════════════
# 3. Failure tolerance
# ═════════════════════════════════════════════════════════════════════


class TestSeedHelperFailureTolerant(unittest.TestCase):

    def test_malformed_attributes_json_swallowed(self):
        """A character with malformed attributes JSON should not
        crash the seed helper — it should log and return False."""
        from engine.village_choice import _seed_force_attributes
        char = _make_char()
        char["attributes"] = "{not valid json"
        db = _FakeDB(char)
        # Must NOT raise.
        result = _run(_seed_force_attributes(db, char))
        # Returns False per failure path.
        self.assertFalse(result)

    def test_save_character_exception_swallowed(self):
        from engine.village_choice import _seed_force_attributes
        char = _make_char()

        class FailingDB(_FakeDB):
            async def save_character(self, char_id, **kwargs):
                raise RuntimeError("simulated DB failure")

        db = FailingDB(char)
        result = _run(_seed_force_attributes(db, char))
        self.assertFalse(result)


# ═════════════════════════════════════════════════════════════════════
# 4. Path A commit fires the seed
# ═════════════════════════════════════════════════════════════════════


class TestPathACommitSeeds(unittest.TestCase):

    def test_path_a_commit_persists_force_attrs(self):
        from engine.village_choice import _commit_path_a, PATH_A_DROP_SLUG
        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_A_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_a(FakeSession(), db, char))

        # Attributes should now contain the three Force keys.
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs.get("control"), "1D")
        self.assertEqual(attrs.get("sense"), "1D")
        self.assertEqual(attrs.get("alter"), "1D")

    def test_path_a_save_character_called_with_attributes(self):
        from engine.village_choice import _commit_path_a, PATH_A_DROP_SLUG
        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_A_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_a(FakeSession(), db, char))

        # At least one save with attributes kwarg.
        attr_saves = [s for s in db.saves if "attributes" in s]
        self.assertGreaterEqual(len(attr_saves), 1)
        persisted = json.loads(attr_saves[-1]["attributes"])
        self.assertEqual(persisted.get("control"), "1D")


# ═════════════════════════════════════════════════════════════════════
# 5. Path B commit fires the seed
# ═════════════════════════════════════════════════════════════════════


class TestPathBCommitSeeds(unittest.TestCase):

    def test_path_b_commit_persists_force_attrs(self):
        from engine.village_choice import _commit_path_b, PATH_B_DROP_SLUG
        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_B_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_b(FakeSession(), db, char))

        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs.get("control"), "1D")
        self.assertEqual(attrs.get("sense"), "1D")
        self.assertEqual(attrs.get("alter"), "1D")


# ═════════════════════════════════════════════════════════════════════
# 6. Path C commit fires the seed (Force-sensitive but exiled)
# ═════════════════════════════════════════════════════════════════════


class TestPathCCommitSeeds(unittest.TestCase):

    def test_path_c_commit_persists_force_attrs(self):
        from engine.village_choice import _commit_path_c, PATH_C_DROP_SLUG
        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_C_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_c(FakeSession(), db, char))

        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs.get("control"), "1D",
                         "Path C is Force-sensitive (Dark Side track); "
                         "Force attributes must persist.")
        self.assertEqual(attrs.get("sense"), "1D")
        self.assertEqual(attrs.get("alter"), "1D")


# ═════════════════════════════════════════════════════════════════════
# 7. Reload via from_db_dict reconstructs force_sensitive=True
# ═════════════════════════════════════════════════════════════════════


class TestReloadReconstructsForceSensitive(unittest.TestCase):
    """The end-to-end pin: after Path A commit + simulated reload
    via Character.from_db_dict, the new Character has
    force_sensitive=True. This is the launch-blocker scenario
    F.7.n was authored to close."""

    def test_path_a_reload_yields_force_sensitive_true(self):
        from engine.village_choice import _commit_path_a, PATH_A_DROP_SLUG
        from engine.character import Character

        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_A_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_a(FakeSession(), db, char))

        # Simulate a fresh login: drop the in-memory dict, build a
        # Character from the DB row state.
        reloaded = Character.from_db_dict(char)
        self.assertTrue(
            reloaded.force_sensitive,
            "After Path A commit and reload, force_sensitive should "
            "be True. F.7.n has regressed — Force attributes are not "
            "being persisted to the attributes JSON.",
        )

    def test_path_b_reload_yields_force_sensitive_true(self):
        from engine.village_choice import _commit_path_b, PATH_B_DROP_SLUG
        from engine.character import Character

        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_B_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_b(FakeSession(), db, char))

        reloaded = Character.from_db_dict(char)
        self.assertTrue(reloaded.force_sensitive)

    def test_path_c_reload_yields_force_sensitive_true(self):
        from engine.village_choice import _commit_path_c, PATH_C_DROP_SLUG
        from engine.character import Character

        char = _make_char()
        db = _FakeDB(char)
        db._slug_to_room_id[PATH_C_DROP_SLUG] = 999

        class FakeSession:
            async def send_line(self, _line):
                pass

        _run(_commit_path_c(FakeSession(), db, char))

        reloaded = Character.from_db_dict(char)
        self.assertTrue(reloaded.force_sensitive)


if __name__ == "__main__":
    unittest.main()
