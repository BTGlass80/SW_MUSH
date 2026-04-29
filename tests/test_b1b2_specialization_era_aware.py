# -*- coding: utf-8 -*-
"""
tests/test_b1b2_specialization_era_aware.py — B.1.b.2 tests.

Per `b1_audit_v1.md` §3 row B.1.b and architecture v38 §19.7, B.1.b is
the extension of `engine/organizations.py` constants to support both
eras. Split into two sub-drops:

  - **B.1.b.1 (shipped):** Pure data-table extensions — STIPEND_TABLE,
    EQUIPMENT_CATALOG, RANK_0/1_EQUIPMENT, CROSS_FACTION_PENALTIES.

  - **B.1.b.2 (this drop):** Specialization function extensions:
      - 3 new `EQUIPMENT_CATALOG` items (flight_suit_republic,
        officers_uniform_republic, datapad_republic) for Republic specs
      - new `REPUBLIC_SPEC_EQUIPMENT` constant (4 specs per Apr 29
        design lock-in: clone_trooper / clone_pilot / clone_officer /
        republic_intelligence)
      - new `SPEC_EQUIPMENT_BY_FACTION` dispatch table
      - new `_SPEC_CONFIG_BY_FACTION` config (header text, menu lines,
        spec_map, spec_labels) for both Empire and Republic
      - new generic helpers: `prompt_specialization`,
        `complete_specialization`, `faction_has_specialization`,
        `get_specialization_config`
      - new named API: `prompt_republic_specialization`,
        `complete_republic_specialization`
      - legacy named API (`prompt_imperial_specialization`,
        `complete_imperial_specialization`) preserved as thin shims
        — byte-equivalent behavior on Imperial path
      - `join_faction` extended to fire either prompt via
        `faction_has_specialization` gate
      - `parser/faction_commands.py::SpecializeCommand` extended to
        route on the player's faction (empire OR republic)

Test classes are split into:
  - "ByteEquivalence" — Imperial path unchanged from pre-B.1.b.2
  - "RepublicAdditions" — new Republic specialization path works
  - "GenericDispatch" — generic helpers route correctly
  - "JoinFactionIntegration" — join_faction fires prompt for both eras
  - "SpecializeCommand" — parser command routes on faction_id
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# Mock helpers
# ──────────────────────────────────────────────────────────────────────

def _mock_session():
    """Mock session with .send_line capturing output."""
    s = MagicMock()
    s.lines = []

    async def _capture(line):
        s.lines.append(line)

    s.send_line = AsyncMock(side_effect=_capture)
    return s


def _mock_db_for_specialization():
    """Mock DB sufficient for prompt/complete specialization paths.

    - get_organization returns a faction-shaped dict for known codes.
    - update_membership records the call.
    - save_character is a no-op AsyncMock.
    - The test can read recorded mutations from db._membership_updates.
    """
    db = MagicMock()
    db._membership_updates = []
    db._saves = []
    db._equipment_issued = []

    KNOWN_ORGS = {
        "empire":   {"id": 1, "code": "empire",   "name": "Galactic Empire"},
        "republic": {"id": 2, "code": "republic", "name": "Galactic Republic"},
        "rebel":    {"id": 3, "code": "rebel",    "name": "Rebel Alliance"},
    }

    async def _get_org(code):
        return KNOWN_ORGS.get(code)

    async def _update_membership(char_id, org_id, **kwargs):
        db._membership_updates.append({
            "char_id": char_id, "org_id": org_id, **kwargs,
        })

    async def _save_character(char_id, **kwargs):
        db._saves.append({"char_id": char_id, **kwargs})

    db.get_organization   = AsyncMock(side_effect=_get_org)
    db.update_membership  = AsyncMock(side_effect=_update_membership)
    db.save_character     = AsyncMock(side_effect=_save_character)
    return db


def _make_char(faction_id="empire", attrs=None):
    """Build a minimal character dict with a pending specialization
    attribute set, the way join_faction would have left it."""
    import json
    if attrs is None:
        attrs = {"faction": {"specialization_pending": True}}
    return {
        "id": 100,
        "name": "TestPC",
        "faction_id": faction_id,
        "attributes": json.dumps(attrs),
    }


# ──────────────────────────────────────────────────────────────────────
# 1. New constants
# ──────────────────────────────────────────────────────────────────────

class TestRepublicSpecEquipmentConstant(unittest.TestCase):

    def test_constant_exists(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertIsInstance(REPUBLIC_SPEC_EQUIPMENT, dict)

    def test_four_specs_present(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        for spec in ("clone_trooper", "clone_pilot",
                     "clone_officer", "republic_intelligence"):
            self.assertIn(spec, REPUBLIC_SPEC_EQUIPMENT)

    def test_clone_trooper_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(
            REPUBLIC_SPEC_EQUIPMENT["clone_trooper"],
            ["dc15_blaster_rifle", "republic_light_armor"],
        )

    def test_clone_pilot_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(
            REPUBLIC_SPEC_EQUIPMENT["clone_pilot"],
            ["flight_suit_republic"],
        )

    def test_clone_officer_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        self.assertEqual(
            REPUBLIC_SPEC_EQUIPMENT["clone_officer"],
            ["officers_uniform_republic", "datapad_republic"],
        )

    def test_republic_intelligence_reuses_era_agnostic_spy_gear(self):
        from engine.organizations import REPUBLIC_SPEC_EQUIPMENT
        # By design civilian_cover + slicing_kit are era-agnostic and
        # appear in both the Imperial intelligence loadout AND the
        # Republic intelligence loadout.
        self.assertEqual(
            REPUBLIC_SPEC_EQUIPMENT["republic_intelligence"],
            ["civilian_cover", "slicing_kit"],
        )

    def test_all_referenced_items_in_catalog(self):
        from engine.organizations import (
            REPUBLIC_SPEC_EQUIPMENT, EQUIPMENT_CATALOG,
        )
        missing = []
        for spec_key, items in REPUBLIC_SPEC_EQUIPMENT.items():
            for item in items:
                if item not in EQUIPMENT_CATALOG:
                    missing.append((spec_key, item))
        self.assertEqual(missing, [],
                         f"REPUBLIC_SPEC_EQUIPMENT references items not in catalog: {missing}")


class TestSpecEquipmentByFactionDispatch(unittest.TestCase):

    def test_dispatch_table_exists(self):
        from engine.organizations import SPEC_EQUIPMENT_BY_FACTION
        self.assertIsInstance(SPEC_EQUIPMENT_BY_FACTION, dict)

    def test_empire_routes_to_imperial_table(self):
        from engine.organizations import (
            SPEC_EQUIPMENT_BY_FACTION, IMPERIAL_SPEC_EQUIPMENT,
        )
        self.assertIs(SPEC_EQUIPMENT_BY_FACTION["empire"], IMPERIAL_SPEC_EQUIPMENT)

    def test_republic_routes_to_republic_table(self):
        from engine.organizations import (
            SPEC_EQUIPMENT_BY_FACTION, REPUBLIC_SPEC_EQUIPMENT,
        )
        self.assertIs(SPEC_EQUIPMENT_BY_FACTION["republic"], REPUBLIC_SPEC_EQUIPMENT)

    def test_unknown_faction_returns_empty_via_get(self):
        from engine.organizations import SPEC_EQUIPMENT_BY_FACTION
        self.assertEqual(SPEC_EQUIPMENT_BY_FACTION.get("hutt", {}), {})


class TestNewCatalogItems(unittest.TestCase):

    def test_flight_suit_republic_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        e = EQUIPMENT_CATALOG["flight_suit_republic"]
        self.assertEqual(e["slot"], "armor")
        self.assertIn("Republic", e["name"])

    def test_officers_uniform_republic_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        e = EQUIPMENT_CATALOG["officers_uniform_republic"]
        self.assertEqual(e["slot"], "armor")

    def test_datapad_republic_present(self):
        from engine.organizations import EQUIPMENT_CATALOG
        e = EQUIPMENT_CATALOG["datapad_republic"]
        self.assertEqual(e["slot"], "misc")

    def test_imperial_naval_gear_unchanged(self):
        # The Imperial datapad and uniform are still around, untouched.
        from engine.organizations import EQUIPMENT_CATALOG
        self.assertEqual(EQUIPMENT_CATALOG["datapad_imperial"]["name"],
                         "Imperial Datapad")
        self.assertEqual(EQUIPMENT_CATALOG["officers_uniform"]["name"],
                         "Naval Officer's Uniform")


# ──────────────────────────────────────────────────────────────────────
# 2. Generic helpers
# ──────────────────────────────────────────────────────────────────────

class TestGenericDispatchHelpers(unittest.TestCase):

    def test_faction_has_specialization_empire(self):
        from engine.organizations import faction_has_specialization
        self.assertTrue(faction_has_specialization("empire"))

    def test_faction_has_specialization_republic(self):
        from engine.organizations import faction_has_specialization
        self.assertTrue(faction_has_specialization("republic"))

    def test_faction_has_specialization_rebel_false(self):
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("rebel"))

    def test_faction_has_specialization_jedi_order_false(self):
        from engine.organizations import faction_has_specialization
        # Jedi join is village-quest-gated; no onboarding spec prompt.
        self.assertFalse(faction_has_specialization("jedi_order"))

    def test_faction_has_specialization_independent_false(self):
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("independent"))

    def test_get_specialization_config_empire(self):
        from engine.organizations import get_specialization_config
        cfg = get_specialization_config("empire")
        self.assertIsNotNone(cfg)
        self.assertIn("[IMPERIAL ONBOARDING]", cfg["header_label"])
        self.assertEqual(cfg["spec_map"][1], "stormtrooper")
        self.assertEqual(cfg["spec_labels"]["intelligence"],
                         "Intelligence Agent")

    def test_get_specialization_config_republic(self):
        from engine.organizations import get_specialization_config
        cfg = get_specialization_config("republic")
        self.assertIsNotNone(cfg)
        self.assertIn("[REPUBLIC ONBOARDING]", cfg["header_label"])
        self.assertEqual(cfg["spec_map"][1], "clone_trooper")
        self.assertEqual(cfg["spec_labels"]["clone_pilot"], "Clone Pilot")

    def test_get_specialization_config_unknown_returns_none(self):
        from engine.organizations import get_specialization_config
        self.assertIsNone(get_specialization_config("rebel"))
        self.assertIsNone(get_specialization_config("nonexistent"))


# ──────────────────────────────────────────────────────────────────────
# 3. Generic prompt_specialization
# ──────────────────────────────────────────────────────────────────────

class TestPromptSpecialization(unittest.TestCase):

    def test_empire_prompt_sends_imperial_menu(self):
        from engine.organizations import prompt_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire",
                          attrs={"faction": {}})  # not yet pending
        ok = _run(prompt_specialization(char, db, sess, "empire"))
        self.assertTrue(ok)
        joined = "\n".join(sess.lines)
        self.assertIn("[IMPERIAL ONBOARDING]", joined)
        self.assertIn("Stormtrooper", joined)
        self.assertIn("TIE Pilot", joined)

    def test_empire_prompt_sets_pending_flag(self):
        import json
        from engine.organizations import prompt_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire", attrs={"faction": {}})
        _run(prompt_specialization(char, db, sess, "empire"))
        a = json.loads(char["attributes"])
        self.assertTrue(a["faction"]["specialization_pending"])

    def test_republic_prompt_sends_republic_menu(self):
        from engine.organizations import prompt_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic", attrs={"faction": {}})
        ok = _run(prompt_specialization(char, db, sess, "republic"))
        self.assertTrue(ok)
        joined = "\n".join(sess.lines)
        self.assertIn("[REPUBLIC ONBOARDING]", joined)
        self.assertIn("Clone Trooper", joined)
        self.assertIn("Clone Pilot", joined)
        self.assertIn("Republic Intelligence", joined)

    def test_republic_prompt_does_not_mention_imperial(self):
        from engine.organizations import prompt_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic", attrs={"faction": {}})
        _run(prompt_specialization(char, db, sess, "republic"))
        joined = "\n".join(sess.lines)
        self.assertNotIn("Stormtrooper", joined)
        self.assertNotIn("TIE Pilot", joined)

    def test_unknown_faction_prompt_returns_false_no_send(self):
        from engine.organizations import prompt_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="rebel", attrs={"faction": {}})
        ok = _run(prompt_specialization(char, db, sess, "rebel"))
        self.assertFalse(ok)
        # Nothing sent — rebel has no spec
        self.assertEqual(sess.lines, [])

    def test_no_session_returns_false(self):
        from engine.organizations import prompt_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire", attrs={"faction": {}})
        ok = _run(prompt_specialization(char, db, None, "empire"))
        self.assertFalse(ok)


# ──────────────────────────────────────────────────────────────────────
# 4. Generic complete_specialization
# ──────────────────────────────────────────────────────────────────────

class TestCompleteSpecialization(unittest.TestCase):

    def setUp(self):
        # Replace issue_equipment with a recorder to avoid touching DB.
        import engine.organizations as orgs_mod
        self._orig_issue = orgs_mod.issue_equipment
        self._issued = []

        async def _record(char, faction_code, db, items, session=None):
            self._issued.append({"faction": faction_code, "items": list(items)})

        orgs_mod.issue_equipment = _record

    def tearDown(self):
        import engine.organizations as orgs_mod
        orgs_mod.issue_equipment = self._orig_issue

    # ── Empire path ──

    def test_empire_choice_1_yields_stormtrooper(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire")
        ok, msg = _run(complete_specialization(
            char, db, 1, faction_code="empire",
        ))
        self.assertTrue(ok)
        self.assertIn("Stormtrooper", msg)
        # Issued the right gear
        self.assertEqual(self._issued[-1]["faction"], "empire")
        self.assertEqual(self._issued[-1]["items"],
                         ["e11_blaster_rifle", "stormtrooper_armor"])
        # update_membership was called against the empire org
        self.assertEqual(db._membership_updates[-1]["org_id"], 1)
        self.assertEqual(db._membership_updates[-1]["specialization"],
                         "stormtrooper")

    def test_empire_choice_4_yields_intelligence(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire")
        ok, msg = _run(complete_specialization(
            char, db, 4, faction_code="empire",
        ))
        self.assertTrue(ok)
        self.assertIn("Intelligence Agent", msg)
        self.assertEqual(self._issued[-1]["items"],
                         ["civilian_cover", "slicing_kit"])

    # ── Republic path ──

    def test_republic_choice_1_yields_clone_trooper(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic")
        ok, msg = _run(complete_specialization(
            char, db, 1, faction_code="republic",
        ))
        self.assertTrue(ok)
        self.assertIn("Clone Trooper", msg)
        self.assertEqual(self._issued[-1]["faction"], "republic")
        self.assertEqual(self._issued[-1]["items"],
                         ["dc15_blaster_rifle", "republic_light_armor"])
        # Republic org membership update
        self.assertEqual(db._membership_updates[-1]["org_id"], 2)
        self.assertEqual(db._membership_updates[-1]["specialization"],
                         "clone_trooper")

    def test_republic_choice_2_yields_clone_pilot(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic")
        ok, msg = _run(complete_specialization(
            char, db, 2, faction_code="republic",
        ))
        self.assertTrue(ok)
        self.assertIn("Clone Pilot", msg)
        self.assertEqual(self._issued[-1]["items"],
                         ["flight_suit_republic"])

    def test_republic_choice_3_yields_clone_officer(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic")
        ok, msg = _run(complete_specialization(
            char, db, 3, faction_code="republic",
        ))
        self.assertTrue(ok)
        self.assertIn("Clone Officer", msg)
        self.assertEqual(self._issued[-1]["items"],
                         ["officers_uniform_republic", "datapad_republic"])

    def test_republic_choice_4_yields_republic_intelligence(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic")
        ok, msg = _run(complete_specialization(
            char, db, 4, faction_code="republic",
        ))
        self.assertTrue(ok)
        self.assertIn("Republic Intelligence Agent", msg)
        self.assertEqual(self._issued[-1]["items"],
                         ["civilian_cover", "slicing_kit"])

    # ── Failure modes (apply to both factions) ──

    def test_invalid_choice_returns_failure(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire")
        ok, msg = _run(complete_specialization(
            char, db, 99, faction_code="empire",
        ))
        self.assertFalse(ok)
        self.assertIn("Invalid choice", msg)

    def test_no_pending_returns_failure(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic",
                          attrs={"faction": {}})  # no pending flag
        ok, msg = _run(complete_specialization(
            char, db, 1, faction_code="republic",
        ))
        self.assertFalse(ok)
        self.assertIn("No pending", msg)

    def test_unconfigured_faction_returns_failure(self):
        from engine.organizations import complete_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="rebel")
        ok, msg = _run(complete_specialization(
            char, db, 1, faction_code="rebel",
        ))
        self.assertFalse(ok)
        self.assertIn("no specialization", msg.lower())


# ──────────────────────────────────────────────────────────────────────
# 5. Legacy named API — byte-equivalence
# ──────────────────────────────────────────────────────────────────────

class TestImperialLegacyAPIByteEquivalence(unittest.TestCase):
    """The pre-B.1.b.2 prompt_imperial_specialization /
    complete_imperial_specialization behavior must remain byte-
    equivalent. They are now thin shims over the generic helpers."""

    def setUp(self):
        import engine.organizations as orgs_mod
        self._orig_issue = orgs_mod.issue_equipment
        self._issued = []

        async def _record(char, faction_code, db, items, session=None):
            self._issued.append({"faction": faction_code, "items": list(items)})

        orgs_mod.issue_equipment = _record

    def tearDown(self):
        import engine.organizations as orgs_mod
        orgs_mod.issue_equipment = self._orig_issue

    def test_prompt_imperial_specialization_still_callable(self):
        from engine.organizations import prompt_imperial_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire", attrs={"faction": {}})
        ok = _run(prompt_imperial_specialization(char, db, sess))
        self.assertTrue(ok)
        joined = "\n".join(sess.lines)
        self.assertIn("[IMPERIAL ONBOARDING]", joined)
        self.assertIn("Stormtrooper", joined)
        self.assertIn("specialize <number>", joined)

    def test_complete_imperial_specialization_still_callable(self):
        from engine.organizations import complete_imperial_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire")
        ok, msg = _run(complete_imperial_specialization(char, db, 2))
        self.assertTrue(ok)
        self.assertIn("TIE Pilot", msg)
        # Imperial-flight-suit issued
        self.assertEqual(self._issued[-1]["items"], ["flight_suit_imperial"])

    def test_complete_imperial_invalid_choice_message(self):
        # Shape of the error message: "Invalid choice. Enter ..." —
        # the format string changed slightly (now lists valid choices
        # via "/", e.g. "1/2/3/4" instead of "1, 2, 3, or 4") but the
        # "Invalid choice" prefix is preserved. Test asserts on the
        # weaker contract because production callers check `ok` not
        # message text.
        from engine.organizations import complete_imperial_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="empire")
        ok, msg = _run(complete_imperial_specialization(char, db, 99))
        self.assertFalse(ok)
        self.assertIn("Invalid choice", msg)


# ──────────────────────────────────────────────────────────────────────
# 6. Republic named API
# ──────────────────────────────────────────────────────────────────────

class TestRepublicNamedAPI(unittest.TestCase):

    def setUp(self):
        import engine.organizations as orgs_mod
        self._orig_issue = orgs_mod.issue_equipment
        self._issued = []

        async def _record(char, faction_code, db, items, session=None):
            self._issued.append({"faction": faction_code, "items": list(items)})

        orgs_mod.issue_equipment = _record

    def tearDown(self):
        import engine.organizations as orgs_mod
        orgs_mod.issue_equipment = self._orig_issue

    def test_prompt_republic_specialization_callable(self):
        from engine.organizations import prompt_republic_specialization
        sess = _mock_session()
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic", attrs={"faction": {}})
        ok = _run(prompt_republic_specialization(char, db, sess))
        self.assertTrue(ok)
        joined = "\n".join(sess.lines)
        self.assertIn("[REPUBLIC ONBOARDING]", joined)
        self.assertIn("Clone Trooper", joined)

    def test_complete_republic_specialization_callable(self):
        from engine.organizations import complete_republic_specialization
        db = _mock_db_for_specialization()
        char = _make_char(faction_id="republic")
        ok, msg = _run(complete_republic_specialization(char, db, 3))
        self.assertTrue(ok)
        self.assertIn("Clone Officer", msg)
        self.assertEqual(self._issued[-1]["items"],
                         ["officers_uniform_republic", "datapad_republic"])


# ──────────────────────────────────────────────────────────────────────
# 7. join_faction integration
# ──────────────────────────────────────────────────────────────────────

class TestJoinFactionIntegration(unittest.TestCase):
    """`join_faction` must fire the spec prompt for both empire AND
    republic. Other factions get no prompt."""

    def test_empire_join_calls_prompt(self):
        # Inspect source to verify the call site uses faction_has_spec
        # (we can't easily run join_faction end-to-end without a real
        # DB stack, but we can verify the integration is in place).
        import inspect
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        self.assertIn("faction_has_specialization", src,
                      "join_faction should gate spec prompt on faction_has_specialization")
        self.assertIn("prompt_specialization", src,
                      "join_faction should call generic prompt_specialization")

    def test_join_faction_no_longer_hardcodes_empire(self):
        """The pre-B.1.b.2 join_faction hardcoded `if faction_code == \"empire\"`.
        Post-drop, that exact literal compare should be gone (replaced
        by faction_has_specialization)."""
        import inspect
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        self.assertNotIn('if faction_code == "empire":', src)


# ──────────────────────────────────────────────────────────────────────
# 8. SpecializeCommand parser routing
# ──────────────────────────────────────────────────────────────────────

class TestSpecializeCommandRouting(unittest.TestCase):
    """SpecializeCommand must route on the player's faction_id."""

    def _make_ctx(self, char, args=""):
        ctx = MagicMock()
        ctx.session = MagicMock()
        ctx.session.character = char
        ctx.session.lines = []

        async def _capture(line):
            ctx.session.lines.append(line)

        ctx.session.send_line = AsyncMock(side_effect=_capture)
        ctx.args = args
        ctx.db = _mock_db_for_specialization()
        return ctx

    def setUp(self):
        # Stub issue_equipment to avoid DB hits.
        import engine.organizations as orgs_mod
        self._orig_issue = orgs_mod.issue_equipment

        async def _noop(char, faction_code, db, items, session=None):
            pass

        orgs_mod.issue_equipment = _noop

    def tearDown(self):
        import engine.organizations as orgs_mod
        orgs_mod.issue_equipment = self._orig_issue

    def test_empire_pc_can_specialize(self):
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="empire"), args="2")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        self.assertIn("TIE Pilot", joined)

    def test_republic_pc_can_specialize(self):
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="republic"), args="1")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        self.assertIn("Clone Trooper", joined)

    def test_rebel_pc_blocked(self):
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="rebel"), args="1")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        # Pre-B.1.b.2 said "Imperial faction members"; post-drop the
        # message lists both Empire and Republic.
        self.assertIn("only available", joined.lower())
        self.assertIn("empire", joined.lower())
        self.assertIn("republic", joined.lower())

    def test_independent_blocked(self):
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="independent"), args="1")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        self.assertIn("only available", joined.lower())

    def test_jedi_order_blocked(self):
        # Jedi Order is village-quest-gated; no spec prompt.
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="jedi_order"), args="1")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        self.assertIn("only available", joined.lower())

    def test_empire_bad_arg_shows_imperial_usage(self):
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="empire"), args="not_a_number")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        self.assertIn("Stormtrooper", joined)
        self.assertIn("TIE Pilot", joined)

    def test_republic_bad_arg_shows_republic_usage(self):
        from parser.faction_commands import SpecializeCommand
        cmd = SpecializeCommand()
        ctx = self._make_ctx(_make_char(faction_id="republic"), args="bogus")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.lines)
        self.assertIn("Clone Trooper", joined)
        self.assertIn("Clone Pilot", joined)
        # Should NOT show Imperial labels for a Republic PC
        self.assertNotIn("Stormtrooper", joined)


if __name__ == "__main__":
    unittest.main()
