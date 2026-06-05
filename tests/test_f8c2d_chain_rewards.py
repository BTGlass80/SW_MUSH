# -*- coding: utf-8 -*-
"""
tests/test_f8c2d_chain_rewards.py — F.8.c.2.d chain graduation
reward delivery tests.

F.8.c.2.d (May 4 2026) closes the chain reward gap. The
``Graduation`` dataclass exposes ``credits``, ``faction_rep``,
``items``, ``achievements``, ``follow_up_hint`` — pre-this-drop
no engine consumer read any of them. After this drop:

  * Credits are added via ``save_character(credits=...)``
  * Faction rep is adjusted per entry via
    ``engine.organizations.adjust_rep``
  * Items are granted as inline-stub dicts via
    ``db.add_to_inventory`` (each marked ``chain_grad: <chain_id>``)
  * Achievements are stamped onto
    ``chargen_notes.graduation_achievements`` (with optional
    catalog-mark via ``engine.achievements`` if registered)
  * A ``chargen_notes.graduation_summary`` block is stamped for
    parser-side summary line delivery + later audit
  * Parser layer (``chain_graduation.execute_pending_teleport``)
    reads the summary back and sends graduation flavor lines

This drop adds:
  * ``engine/chain_rewards.py`` — engine-side reward delivery +
    parser-side summary line delivery
  * Hooks reward delivery into ``chain_events._try_advance``
    graduated branch
  * Hooks summary delivery into
    ``chain_graduation.execute_pending_teleport`` after look

Test sections
-------------
   1. TestHumanizeKey         — _humanize_item_key formatting
   2. TestBuildItem           — _build_graduation_item shape
   3. TestRewardsCredits      — credits award via save_character
   4. TestRewardsRep          — faction rep delivery
   5. TestRewardsItems        — item grants via add_to_inventory
   6. TestRewardsAchievements — chargen_notes stamping + catalog
   7. TestRewardsSummary      — graduation_summary block + lines
   8. TestRewardsErrorPaths   — failure tolerance
   9. TestEndToEnd            — full graduation via _try_advance
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


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


class _MockGraduation:
    """Stand-in for ``tutorial_chains.Graduation`` dataclass."""
    def __init__(self, drop_room="test_drop", credits=0,
                 faction_rep=None, items=None, achievements=None,
                 follow_up_hint=""):
        self.drop_room = drop_room
        self.credits = credits
        self.faction_rep = faction_rep or {}
        self.items = items or []
        self.achievements = achievements or []
        self.follow_up_hint = follow_up_hint


class _MockDB:
    """Records save_character + add_to_inventory + adjust_rep calls."""
    def __init__(self, fail_credits=False, fail_inventory=False):
        self.save_calls = []
        self.inventory_calls = []
        self.rep_calls = []
        self.notes_save_calls = []
        self.credit_calls = []
        self.balances = {}
        self.fail_credits = fail_credits
        self.fail_inventory = fail_inventory
        self.organizations = {}
        self.memberships = {}

    async def save_character(self, char_id, **kwargs):
        if self.fail_credits and "credits" in kwargs:
            raise RuntimeError("save_character credits fail")
        if "chargen_notes" in kwargs:
            self.notes_save_calls.append((char_id, kwargs["chargen_notes"]))
        self.save_calls.append((char_id, kwargs))

    async def adjust_credits(self, char_id, delta, source, *, allow_negative=True):
        # Chokepoint shim: credit moves now route here instead of
        # save_character(credits=...). Preserve the fail_credits failure path,
        # track a running balance (seed via .balances in tests that assert a
        # specific total), and mirror the legacy save_character(credits=total)
        # record so existing save_calls assertions still hold.
        if self.fail_credits:
            raise RuntimeError("adjust_credits credits fail")
        self.credit_calls.append((char_id, delta, source))
        if char_id == 0:
            return 0
        total = self.balances.get(char_id, 0) + delta
        self.balances[char_id] = total
        self.save_calls.append((char_id, {"credits": total}))
        return total

    async def add_to_inventory(self, char_id, item):
        if self.fail_inventory:
            raise RuntimeError("add_to_inventory fail")
        self.inventory_calls.append((char_id, item))

    async def get_organization(self, code):
        return self.organizations.get(code)

    async def get_membership(self, char_id, org_id):
        return self.memberships.get((char_id, org_id))


def _char(char_id=1, credits=100, attrs=None, notes=None):
    return {
        "id": char_id,
        "name": "TestPC",
        "credits": credits,
        "room_id": 10,
        "attributes": json.dumps(attrs or {}),
        "chargen_notes": json.dumps(notes or {}) if notes else "",
        "faction_id": "independent",
    }


# ─────────────────────────────────────────────────────────────────────
# 1. _humanize_item_key
# ─────────────────────────────────────────────────────────────────────


class TestHumanizeKey(unittest.TestCase):

    def test_uses_override_when_present(self):
        from engine.chain_rewards import _humanize_item_key
        self.assertEqual(
            _humanize_item_key("dc15_blaster_rifle"),
            "DC-15 Blaster Rifle",
        )
        self.assertEqual(
            _humanize_item_key("e5_blaster_rifle"),
            "E-5 Blaster Rifle",
        )
        self.assertEqual(
            _humanize_item_key("kdy_apprentice_pass"),
            "KDY Apprentice Pass",
        )

    def test_falls_back_to_title_case(self):
        from engine.chain_rewards import _humanize_item_key
        self.assertEqual(
            _humanize_item_key("comlink_basic"),
            "Comlink Basic",
        )
        self.assertEqual(
            _humanize_item_key("tracking_fob"),
            "Tracking Fob",
        )

    def test_handles_empty(self):
        from engine.chain_rewards import _humanize_item_key
        self.assertEqual(_humanize_item_key(""), "")


# ─────────────────────────────────────────────────────────────────────
# 2. _build_graduation_item
# ─────────────────────────────────────────────────────────────────────


class TestBuildItem(unittest.TestCase):

    def test_item_dict_has_required_fields(self):
        from engine.chain_rewards import _build_graduation_item
        item = _build_graduation_item(
            "comlink_basic", "republic_soldier", "Republic Soldier")
        self.assertEqual(item["key"], "comlink_basic")
        self.assertEqual(item["name"], "Comlink Basic")
        self.assertIn("graduation gift", item["description"].lower())
        self.assertEqual(item["chain_grad"], "republic_soldier")
        self.assertIn("acquired_at", item)


# ─────────────────────────────────────────────────────────────────────
# 3. Credits delivery
# ─────────────────────────────────────────────────────────────────────


class TestRewardsCredits(unittest.TestCase):

    def test_credits_added_to_existing_total(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char(credits=200)
        db.balances[char["id"]] = 200
        attrs = {}
        grad = _MockGraduation(credits=500)
        report = _run(apply_graduation_rewards(
            db, char, attrs, grad, "test_chain"))
        self.assertEqual(report["credits_awarded"], 500)
        # save_character called with new total = 200 + 500 = 700
        credit_calls = [
            c for c in db.save_calls if "credits" in c[1]
        ]
        self.assertEqual(len(credit_calls), 1)
        self.assertEqual(credit_calls[0][1]["credits"], 700)
        # char dict mutated
        self.assertEqual(char["credits"], 700)

    def test_zero_credits_no_save(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char(credits=200)
        grad = _MockGraduation(credits=0)
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test"))
        self.assertEqual(report["credits_awarded"], 0)
        credit_calls = [c for c in db.save_calls if "credits" in c[1]]
        self.assertEqual(len(credit_calls), 0)
        self.assertEqual(char["credits"], 200)

    def test_credits_failure_recorded_in_report(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB(fail_credits=True)
        char = _char(credits=200)
        grad = _MockGraduation(credits=500)
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test"))
        self.assertEqual(report["credits_awarded"], 0)
        self.assertTrue(any("credits" in e for e in report["errors"]))


# ─────────────────────────────────────────────────────────────────────
# 4. Faction rep delivery
# ─────────────────────────────────────────────────────────────────────


class TestRewardsRep(unittest.TestCase):

    def test_rep_calls_adjust_rep_per_faction(self):
        from engine.chain_rewards import apply_graduation_rewards
        from unittest.mock import patch, AsyncMock
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(faction_rep={
            "republic": 50, "hutt_cartel": -10,
        })

        async def fake_adjust(char, faction_code, db, **kwargs):
            return {"republic": 50, "hutt_cartel": -10}.get(
                faction_code, 0)

        with patch("engine.organizations.adjust_rep",
                   AsyncMock(side_effect=fake_adjust)):
            report = _run(apply_graduation_rewards(
                db, char, {}, grad, "test_chain"))

        self.assertEqual(report["rep_awarded"]["republic"], 50)
        self.assertEqual(report["rep_awarded"]["hutt_cartel"], -10)

    def test_zero_delta_skipped(self):
        from engine.chain_rewards import apply_graduation_rewards
        from unittest.mock import patch, AsyncMock
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(faction_rep={"republic": 0})
        mock = AsyncMock(return_value=0)
        with patch("engine.organizations.adjust_rep", mock):
            report = _run(apply_graduation_rewards(
                db, char, {}, grad, "test"))
        self.assertNotIn("republic", report["rep_awarded"])
        self.assertEqual(mock.call_count, 0)

    def test_rep_partial_failure_other_factions_succeed(self):
        from engine.chain_rewards import apply_graduation_rewards
        from unittest.mock import patch, AsyncMock
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(faction_rep={
            "republic": 50, "hutt_cartel": 10,
        })

        async def fake_adjust(char, faction_code, db, **kwargs):
            if faction_code == "republic":
                raise RuntimeError("rep adjust fail")
            return 10

        with patch("engine.organizations.adjust_rep",
                   AsyncMock(side_effect=fake_adjust)):
            report = _run(apply_graduation_rewards(
                db, char, {}, grad, "test"))

        # hutt_cartel still succeeded
        self.assertEqual(report["rep_awarded"]["hutt_cartel"], 10)
        # republic recorded as error
        self.assertTrue(
            isinstance(report["rep_awarded"]["republic"], str)
            and "error" in report["rep_awarded"]["republic"]
        )


# ─────────────────────────────────────────────────────────────────────
# 5. Item grants
# ─────────────────────────────────────────────────────────────────────


class TestRewardsItems(unittest.TestCase):

    def test_each_item_added_to_inventory(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(items=[
            "dc15_blaster_rifle", "republic_light_armor",
            "comlink_basic",
        ])
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "republic_soldier",
            chain_label="Republic Soldier"))
        self.assertEqual(len(report["items_granted"]), 3)
        self.assertEqual(len(db.inventory_calls), 3)
        # Each item dict carries chain_grad tag
        for char_id, item in db.inventory_calls:
            self.assertEqual(item["chain_grad"], "republic_soldier")

    def test_inventory_failure_recorded(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB(fail_inventory=True)
        char = _char()
        grad = _MockGraduation(items=["test_item"])
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test"))
        self.assertEqual(report["items_granted"], [])
        self.assertEqual(report["items_failed"], ["test_item"])

    def test_skips_empty_or_non_string_keys(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(items=[
            "good_item", "", None, 123, "another_item",
        ])
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test"))
        self.assertEqual(set(report["items_granted"]),
                         {"good_item", "another_item"})


# ─────────────────────────────────────────────────────────────────────
# 6. Achievements
# ─────────────────────────────────────────────────────────────────────


class TestRewardsAchievements(unittest.TestCase):

    def test_achievements_stamped_to_chargen_notes(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(achievements=[
            "sworn_to_the_republic", "first_deployment",
        ])
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "republic_soldier"))
        self.assertEqual(len(report["achievements"]), 2)

        # chargen_notes was saved with graduation_achievements list
        self.assertGreater(len(db.notes_save_calls), 0)
        notes_json = db.notes_save_calls[-1][1]
        notes = json.loads(notes_json)
        self.assertIn("graduation_achievements", notes)
        self.assertEqual(set(notes["graduation_achievements"]),
                         {"sworn_to_the_republic", "first_deployment"})

    def test_achievements_idempotent_on_existing(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        # char already has one achievement
        char = _char(notes={
            "graduation_achievements": ["sworn_to_the_republic"],
        })
        grad = _MockGraduation(achievements=[
            "sworn_to_the_republic", "new_one",
        ])
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test"))
        # Only the new one is in this run's report
        self.assertEqual(report["achievements"], ["new_one"])
        # But chargen_notes should have both
        notes_json = db.notes_save_calls[-1][1]
        notes = json.loads(notes_json)
        self.assertEqual(set(notes["graduation_achievements"]),
                         {"sworn_to_the_republic", "new_one"})


# ─────────────────────────────────────────────────────────────────────
# 7. graduation_summary block + summary lines
# ─────────────────────────────────────────────────────────────────────


class TestRewardsSummary(unittest.TestCase):

    def test_graduation_summary_stamped(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(
            credits=500,
            items=["comlink_basic"],
            achievements=["test_ach"],
            follow_up_hint="Report to the duty officer.",
        )
        _run(apply_graduation_rewards(
            db, char, {}, grad, "test_chain",
            chain_label="Test Chain"))

        notes_json = db.notes_save_calls[-1][1]
        notes = json.loads(notes_json)
        self.assertIn("graduation_summary", notes)
        gs = notes["graduation_summary"]
        self.assertEqual(gs["chain_id"], "test_chain")
        self.assertEqual(gs["chain_label"], "Test Chain")
        self.assertEqual(gs["credits_awarded"], 500)
        self.assertEqual(gs["items_granted"], ["comlink_basic"])
        self.assertEqual(gs["achievements"], ["test_ach"])
        self.assertEqual(gs["follow_up_hint"],
                         "Report to the duty officer.")
        self.assertIn("graduated_at", gs)


class _MockSession:
    def __init__(self):
        self.lines = []

    async def send_line(self, line):
        self.lines.append(line)


class TestRewardsSummaryLines(unittest.TestCase):

    def test_send_summary_no_op_without_block(self):
        from engine.chain_rewards import send_graduation_summary
        char = _char()  # no chargen_notes
        sess = _MockSession()
        result = _run(send_graduation_summary(sess, char))
        self.assertFalse(result)
        self.assertEqual(len(sess.lines), 0)

    def test_send_summary_emits_credits_rep_items_ach_hint(self):
        from engine.chain_rewards import send_graduation_summary
        char = _char(notes={
            "graduation_summary": {
                "chain_id": "republic_soldier",
                "chain_label": "Republic Soldier",
                "credits_awarded": 500,
                "rep_awarded": {"republic": 50},
                "items_granted": ["dc15_blaster_rifle"],
                "achievements": ["sworn_to_the_republic"],
                "follow_up_hint": "Report for duty.",
            }
        })
        sess = _MockSession()
        result = _run(send_graduation_summary(sess, char))
        self.assertTrue(result)
        all_lines = "\n".join(sess.lines)
        self.assertIn("Graduation Rewards", all_lines)
        self.assertIn("500", all_lines)
        self.assertIn("republic", all_lines)
        self.assertIn("DC-15 Blaster Rifle", all_lines)
        self.assertIn("Sworn To The Republic", all_lines)
        self.assertIn("Report for duty", all_lines)


# ─────────────────────────────────────────────────────────────────────
# 8. Failure tolerance
# ─────────────────────────────────────────────────────────────────────


class TestRewardsErrorPaths(unittest.TestCase):

    def test_none_graduation_returns_empty_report(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        report = _run(apply_graduation_rewards(
            db, char, {}, None, "test"))
        self.assertEqual(report["credits_awarded"], 0)
        self.assertEqual(report["items_granted"], [])

    def test_empty_graduation_safe(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation()
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test"))
        self.assertEqual(report["credits_awarded"], 0)
        self.assertEqual(report["items_granted"], [])
        self.assertEqual(report["achievements"], [])


# ─────────────────────────────────────────────────────────────────────
# 9. End-to-end via _try_advance
# ─────────────────────────────────────────────────────────────────────


class TestEndToEndGraduation(unittest.TestCase):
    """A graduation triggered by _try_advance fires reward
    delivery and stamps graduation_summary."""

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.chain_events import _reset_corpus_cache
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        _reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.chain_events import _reset_corpus_cache
        clear_active_config()
        _reset_corpus_cache()

    def test_republic_soldier_graduation_delivers_rewards(self):
        from engine.chain_events import on_command_executed

        db = _MockDB()
        # Add the room so the teleport resolves
        db_rooms = {500: {"id": 500, "name": "Coruscant Works LZ",
                          "properties": json.dumps({
                              "slug": "coruscant_works_landing_zone"
                          })}}
        db.rooms = db_rooms

        async def get_room(rid):
            return db.rooms.get(int(rid))

        async def get_room_by_slug(slug):
            for r in db.rooms.values():
                p = json.loads(r["properties"])
                if p.get("slug") == slug.strip():
                    return r
            return None

        db.get_room = get_room
        db.get_room_by_slug = get_room_by_slug

        # Stub out adjust_rep so it doesn't try to look up
        # organizations table (which our mock doesn't have).
        from unittest.mock import patch, AsyncMock

        attrs = {
            "tutorial_chain": {
                "chain_id": "republic_soldier",
                "step": 5,
                "started_at": 1000000,
                "completed_steps": [1, 2, 3, 4],
                "completion_state": "active",
            }
        }
        char = {
            "id": 7, "name": "Trooper", "room_id": 100,
            "credits": 100,
            "attributes": json.dumps(attrs),
            "chargen_notes": "",
            "faction_id": "independent",
        }
        db.balances[char["id"]] = char["credits"]

        with patch("engine.organizations.adjust_rep",
                   AsyncMock(return_value=50)):
            result = _run(on_command_executed(
                db, char, "+factions", ""))

        self.assertTrue(result)
        # Char teleported
        self.assertEqual(char["room_id"], 500)
        # Credits awarded (republic_soldier: +500)
        self.assertEqual(char["credits"], 600)
        # Items granted (republic_soldier: 3 items)
        self.assertEqual(len(db.inventory_calls), 3)
        # graduation_summary stamped on chargen_notes
        notes = json.loads(char["chargen_notes"])
        self.assertIn("graduation_summary", notes)
        gs = notes["graduation_summary"]
        self.assertEqual(gs["chain_id"], "republic_soldier")
        self.assertEqual(gs["credits_awarded"], 500)


# ─────────────────────────────────────────────────────────────────────


class TestDropMarker(unittest.TestCase):
    def test_module_docstring_marks_drop_id(self):
        import tests.test_f8c2d_chain_rewards as mod
        self.assertIn("F.8.c.2.d", mod.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
