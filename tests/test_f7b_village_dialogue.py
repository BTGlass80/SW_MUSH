# -*- coding: utf-8 -*-
"""
tests/test_f7b_village_dialogue.py — Drop F.7.b — Village Quest Step 3 + 4.

Closes the loop on Sister Vitha's Gate test (Step 3) and Master
Yarael's First Audience (Step 4), plus the Hermit after_lines
emission carry-over from W.2 phase 2.

What this suite validates:

  1. Schema v21: village_gate_passed, village_gate_lockout_until,
     village_gate_attempts columns present and writable.
  2. Build-time: Sister Vitha at Village Gate; Master Yarael at
     Master's Chamber; both have the right species/template; both
     are loaded via the new content_refs.jedi_village_npcs path.
  3. Eligibility checks: is_at_gate_test_step / is_in_lockout /
     has_passed_gate truth tables.
  4. Pending offer state: offer_gate / has_pending_gate_offer /
     clear_gate_offer / TTL purge.
  5. Render functions: render_gate_menu / render_gate_locked_out /
     render_gate_already_passed all return non-empty lists with the
     expected content markers.
  6. process_gate_choice:
        - choice 1 (pass-receipt) advances to act 2, sets gate_passed
        - choice 3 (pass-doubt) advances to act 2, sets gate_passed
        - choice 2 (fail-demand) sets 24h cooldown, no act change
        - invalid choices rejected
        - no pending offer → rejected
        - wrong state → rejected
  7. Vitha pre-AI hook: returns True for valid gate-test entry,
     False for non-Vitha and for off-state PCs.
  8. Yarael first-audience: fires once after gate pass; idempotent
     on re-talk.
  9. Hermit after_lines emission: fires for invited PCs (act >= 1),
     does not fire for pre-invitation PCs (act 0).
  10. GateCommand registered.

NOT covered (deferred):
  - Trial mechanics (F.7.c/d).
  - Path A/B/C choice (Act 3, future drop).
  - Live end-to-end via TalkCommand (would need session+session_mgr
    fixtures heavier than necessary; the dialogue runtime is tested
    directly).
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from build_mos_eisley import build
from db.database import Database, SCHEMA_VERSION
from engine.village_dialogue import (
    GATE_COOLDOWN_SECONDS, VITHA_NAME, YARAEL_NAME,
    VALID_GATE_CHOICES,
    GATE_CHOICE_PASS_RECEIPT, GATE_CHOICE_FAIL_DEMAND, GATE_CHOICE_PASS_DOUBT,
    has_pending_gate_offer, offer_gate, clear_gate_offer,
    is_in_lockout, is_at_gate_test_step, has_passed_gate,
    render_gate_menu, render_gate_locked_out, render_gate_already_passed,
    process_gate_choice, maybe_intercept_vitha_talk,
    maybe_handle_yarael_first_audience,
    _pending_gate_offers,
)
from engine.village_quest import (
    ACT_PRE_INVITATION, ACT_INVITED, ACT_IN_TRIALS, ACT_PASSED,
    HERMIT_NAME, check_village_quest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _build_cw():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)
    asyncio.run(build(db_path=db_path, era="clone_wars"))
    return db_path


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def _make_char(
    *, id_=1, act=ACT_PRE_INVITATION,
    gate_passed=0, lockout_until=0,
):
    """Build a minimal char dict for unit tests."""
    return {
        "id": id_,
        "name": f"P{id_}",
        "village_act": act,
        "village_gate_passed": gate_passed,
        "village_gate_lockout_until": lockout_until,
        "village_gate_attempts": 0,
        "village_act_unlocked_at": 0,
        "force_signs_accumulated": 5,
        "play_time_seconds": 200_000,
        "chargen_notes": "{}",
    }


class FakeSession:
    """Minimal session for testing dialogue output."""
    def __init__(self, character):
        self.character = character
        self.received: list[str] = []

    async def send_line(self, text):
        self.received.append(text)


class FakeDB:
    """Minimal DB stub. save_character mutates the in-memory char dict."""
    def __init__(self, char):
        self._char = char
        self.saves: list[dict] = []

    async def save_character(self, char_id, **kwargs):
        self.saves.append(dict(kwargs))
        for k, v in kwargs.items():
            self._char[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema v21
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaV21:

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_schema_version_at_least_21(self):
        rows = _query(self.db_path, "SELECT MAX(version) AS v FROM schema_version")
        assert rows[0]["v"] >= 21

    def test_village_gate_passed_column(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        assert "village_gate_passed" in cols

    def test_village_gate_lockout_until_column(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        assert "village_gate_lockout_until" in cols

    def test_village_gate_attempts_column(self):
        rows = _query(self.db_path, "PRAGMA table_info(characters)")
        cols = {r["name"] for r in rows}
        assert "village_gate_attempts" in cols

    def test_writable_columns_include_gate_state(self):
        from db.database import Database as D
        for col in ("village_gate_passed", "village_gate_lockout_until",
                     "village_gate_attempts"):
            assert col in D._CHARACTER_WRITABLE_COLUMNS


# ─────────────────────────────────────────────────────────────────────────────
# 2. Build-time: Vitha + Yarael placed correctly
# ─────────────────────────────────────────────────────────────────────────────


class TestVillageNPCsPlaced:

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_sister_vitha_present(self):
        rows = _query(
            self.db_path,
            "SELECT n.name, r.name AS room_name FROM npcs n "
            "JOIN rooms r ON r.id = n.room_id WHERE n.name = ?",
            (VITHA_NAME,),
        )
        assert len(rows) == 1
        assert rows[0]["room_name"] == "Village Gate"

    def test_master_yarael_present(self):
        rows = _query(
            self.db_path,
            "SELECT n.name, r.name AS room_name FROM npcs n "
            "JOIN rooms r ON r.id = n.room_id WHERE n.name = ?",
            (YARAEL_NAME,),
        )
        assert len(rows) == 1
        assert rows[0]["room_name"] == "Master's Chamber"

    def test_vitha_species(self):
        rows = _query(
            self.db_path,
            "SELECT species FROM npcs WHERE name = ?",
            (VITHA_NAME,),
        )
        assert rows[0]["species"] == "Twi'lek"

    def test_yarael_species(self):
        rows = _query(
            self.db_path,
            "SELECT species FROM npcs WHERE name = ?",
            (YARAEL_NAME,),
        )
        assert rows[0]["species"] == "Cerean"

    def test_vitha_in_wilderness_landmark_room(self):
        rows = _query(
            self.db_path,
            "SELECT r.wilderness_region_id FROM npcs n "
            "JOIN rooms r ON r.id = n.room_id WHERE n.name = ?",
            (VITHA_NAME,),
        )
        # Village rooms are wilderness landmarks → wilderness_region_id set
        assert rows[0]["wilderness_region_id"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Eligibility / state checks
# ─────────────────────────────────────────────────────────────────────────────


class TestIsAtGateTestStep:
    def test_act_invited_not_passed(self):
        char = _make_char(act=ACT_INVITED, gate_passed=0)
        assert is_at_gate_test_step(char) is True

    def test_act_invited_already_passed(self):
        char = _make_char(act=ACT_INVITED, gate_passed=1)
        assert is_at_gate_test_step(char) is False

    def test_act_pre_invitation(self):
        char = _make_char(act=ACT_PRE_INVITATION)
        assert is_at_gate_test_step(char) is False

    def test_act_in_trials(self):
        char = _make_char(act=ACT_IN_TRIALS)
        assert is_at_gate_test_step(char) is False

    def test_act_passed(self):
        char = _make_char(act=ACT_PASSED)
        assert is_at_gate_test_step(char) is False


class TestIsInLockout:
    def test_no_lockout(self):
        char = _make_char(lockout_until=0)
        in_lo, remaining = is_in_lockout(char)
        assert in_lo is False
        assert remaining == 0.0

    def test_active_lockout(self):
        char = _make_char(lockout_until=time.time() + 3600)
        in_lo, remaining = is_in_lockout(char)
        assert in_lo is True
        assert remaining > 0

    def test_expired_lockout(self):
        char = _make_char(lockout_until=time.time() - 3600)
        in_lo, remaining = is_in_lockout(char)
        assert in_lo is False
        assert remaining == 0.0


class TestHasPassedGate:
    def test_unset_default(self):
        char = _make_char(gate_passed=0)
        assert has_passed_gate(char) is False

    def test_set(self):
        char = _make_char(gate_passed=1)
        assert has_passed_gate(char) is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pending offer state
# ─────────────────────────────────────────────────────────────────────────────


class TestPendingGateOffer:
    def setup_method(self):
        _pending_gate_offers.clear()

    def teardown_method(self):
        _pending_gate_offers.clear()

    def test_no_offer_default(self):
        assert has_pending_gate_offer(42) is False

    def test_offer_then_check(self):
        offer_gate(42)
        assert has_pending_gate_offer(42) is True

    def test_clear_offer(self):
        offer_gate(42)
        clear_gate_offer(42)
        assert has_pending_gate_offer(42) is False

    def test_distinct_chars_independent(self):
        offer_gate(1)
        offer_gate(2)
        clear_gate_offer(1)
        assert has_pending_gate_offer(1) is False
        assert has_pending_gate_offer(2) is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. Render functions
# ─────────────────────────────────────────────────────────────────────────────


class TestRenderGateMenu:
    def test_returns_nonempty_list(self):
        lines = render_gate_menu()
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_includes_vitha_opening(self):
        lines = render_gate_menu()
        joined = "\n".join(lines)
        assert "Sister Vitha" in joined
        assert "edge of where you should not be" in joined

    def test_includes_three_options(self):
        lines = render_gate_menu()
        joined = "\n".join(lines)
        assert "I received a message" in joined
        assert "looking for the Master" in joined
        assert "Something told me to come" in joined

    def test_includes_gate_command_hint(self):
        lines = render_gate_menu()
        joined = "\n".join(lines)
        assert "gate 1" in joined or "gate 2" in joined


class TestRenderGateLockedOut:
    def test_includes_remaining_time(self):
        lines = render_gate_locked_out(3600 * 12)  # 12 hours
        joined = "\n".join(lines)
        assert "12 hours" in joined or "12 hour" in joined

    def test_handles_short_remaining(self):
        # Rounding edge case
        lines = render_gate_locked_out(1)
        joined = "\n".join(lines)
        assert "1 hour" in joined

    def test_includes_vitha_response(self):
        lines = render_gate_locked_out(3600 * 24)
        joined = "\n".join(lines)
        assert "Sister Vitha" in joined or "Vitha" in joined


class TestRenderGateAlreadyPassed:
    def test_returns_nonempty_list(self):
        lines = render_gate_already_passed()
        assert len(lines) > 0

    def test_acknowledges_passing(self):
        lines = render_gate_already_passed()
        joined = "\n".join(lines)
        assert "Master" in joined  # references Master's chamber


# ─────────────────────────────────────────────────────────────────────────────
# 6. process_gate_choice — the commit behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessGateChoice:
    def setup_method(self):
        _pending_gate_offers.clear()

    def teardown_method(self):
        _pending_gate_offers.clear()

    def test_choice_1_passes_advances_to_act_2(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            offer_gate(char["id"])
            session = FakeSession(char)
            db = FakeDB(char)

            ok = await process_gate_choice(session, db, char, GATE_CHOICE_PASS_RECEIPT)
            assert ok is True
            assert char["village_gate_passed"] == 1
            assert char["village_act"] == ACT_IN_TRIALS
            # Pending offer cleared
            assert has_pending_gate_offer(char["id"]) is False
            # DB save called
            assert any("village_gate_passed" in s for s in db.saves)
        asyncio.run(_check())

    def test_choice_3_passes_advances_to_act_2(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            offer_gate(char["id"])
            session = FakeSession(char)
            db = FakeDB(char)

            ok = await process_gate_choice(session, db, char, GATE_CHOICE_PASS_DOUBT)
            assert ok is True
            assert char["village_gate_passed"] == 1
            assert char["village_act"] == ACT_IN_TRIALS
        asyncio.run(_check())

    def test_choice_2_sets_24h_lockout(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            offer_gate(char["id"])
            session = FakeSession(char)
            db = FakeDB(char)

            before = time.time()
            ok = await process_gate_choice(session, db, char, GATE_CHOICE_FAIL_DEMAND)
            after = time.time()

            assert ok is True
            # Gate not passed
            assert char["village_gate_passed"] == 0
            # Act unchanged
            assert char["village_act"] == ACT_INVITED
            # Lockout set ~24 hours from now
            until = char["village_gate_lockout_until"]
            assert before + GATE_COOLDOWN_SECONDS - 1 <= until <= after + GATE_COOLDOWN_SECONDS + 1
            # Pending offer cleared
            assert has_pending_gate_offer(char["id"]) is False
        asyncio.run(_check())

    def test_choice_increments_attempts(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            offer_gate(char["id"])
            session = FakeSession(char)
            db = FakeDB(char)

            await process_gate_choice(session, db, char, GATE_CHOICE_PASS_RECEIPT)
            assert char["village_gate_attempts"] == 1
        asyncio.run(_check())

    def test_invalid_choice_4(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            offer_gate(char["id"])
            session = FakeSession(char)
            db = FakeDB(char)

            ok = await process_gate_choice(session, db, char, 4)
            assert ok is False
            # State unchanged
            assert char["village_gate_passed"] == 0
            assert char["village_act"] == ACT_INVITED
        asyncio.run(_check())

    def test_no_pending_offer(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            # No offer_gate() call
            session = FakeSession(char)
            db = FakeDB(char)

            ok = await process_gate_choice(session, db, char, GATE_CHOICE_PASS_RECEIPT)
            assert ok is False
            assert char["village_gate_passed"] == 0
        asyncio.run(_check())

    def test_wrong_state_act_0(self):
        async def _check():
            char = _make_char(act=ACT_PRE_INVITATION)
            offer_gate(char["id"])  # somehow has an offer
            session = FakeSession(char)
            db = FakeDB(char)

            ok = await process_gate_choice(session, db, char, GATE_CHOICE_PASS_RECEIPT)
            assert ok is False
            # Offer was cleared defensively
            assert has_pending_gate_offer(char["id"]) is False
        asyncio.run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 7. Vitha pre-AI hook
# ─────────────────────────────────────────────────────────────────────────────


class TestVithaInterceptHook:
    def setup_method(self):
        _pending_gate_offers.clear()

    def teardown_method(self):
        _pending_gate_offers.clear()

    def test_non_vitha_returns_false(self):
        async def _check():
            char = _make_char(act=ACT_INVITED)
            session = FakeSession(char)
            ok = await maybe_intercept_vitha_talk(session, FakeDB(char), char, "Hermit")
            assert ok is False
        asyncio.run(_check())

    def test_vitha_at_step_3_intercepts_with_menu(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            session = FakeSession(char)
            ok = await maybe_intercept_vitha_talk(session, FakeDB(char), char, VITHA_NAME)
            assert ok is True
            # Pending offer recorded
            assert has_pending_gate_offer(char["id"]) is True
            # Menu output
            output = "\n".join(session.received)
            assert "I received a message" in output
        asyncio.run(_check())

    def test_vitha_already_passed_acks(self):
        async def _check():
            char = _make_char(act=ACT_IN_TRIALS, gate_passed=1)
            session = FakeSession(char)
            ok = await maybe_intercept_vitha_talk(session, FakeDB(char), char, VITHA_NAME)
            assert ok is True
            output = "\n".join(session.received)
            # Recognises the player; no menu re-prompt
            assert "I received a message" not in output

        asyncio.run(_check())

    def test_vitha_in_lockout_emits_closed(self):
        async def _check():
            char = _make_char(
                act=ACT_INVITED, gate_passed=0,
                lockout_until=time.time() + 3600 * 12,
            )
            session = FakeSession(char)
            ok = await maybe_intercept_vitha_talk(session, FakeDB(char), char, VITHA_NAME)
            assert ok is True
            output = "\n".join(session.received)
            assert "Not today" in output or "closed" in output
        asyncio.run(_check())

    def test_vitha_pre_invitation_passes_through(self):
        async def _check():
            char = _make_char(act=ACT_PRE_INVITATION)
            session = FakeSession(char)
            ok = await maybe_intercept_vitha_talk(session, FakeDB(char), char, VITHA_NAME)
            # Not at step 3 → no intercept; let fallback_lines handle
            assert ok is False
        asyncio.run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 8. Yarael first-audience
# ─────────────────────────────────────────────────────────────────────────────


class TestYaraelFirstAudience:

    def test_non_yarael_returns_false(self):
        async def _check():
            char = _make_char(act=ACT_IN_TRIALS, gate_passed=1)
            session = FakeSession(char)
            ok = await maybe_handle_yarael_first_audience(
                session, FakeDB(char), char, "Hermit",
            )
            assert ok is False
        asyncio.run(_check())

    def test_yarael_without_gate_pass_returns_false(self):
        async def _check():
            char = _make_char(act=ACT_PRE_INVITATION, gate_passed=0)
            session = FakeSession(char)
            ok = await maybe_handle_yarael_first_audience(
                session, FakeDB(char), char, YARAEL_NAME,
            )
            assert ok is False
        asyncio.run(_check())

    def test_yarael_first_audience_fires_after_gate_pass(self):
        async def _check():
            char = _make_char(act=ACT_IN_TRIALS, gate_passed=1)
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_first_audience(
                session, db, char, YARAEL_NAME,
            )
            assert ok is True
            output = "\n".join(session.received)
            assert "Trials" in output or "trials" in output
            # Audience flag set in chargen_notes
            notes = json.loads(char["chargen_notes"])
            assert notes.get("village_first_audience_done") is True
        asyncio.run(_check())

    def test_yarael_audience_idempotent(self):
        async def _check():
            char = _make_char(act=ACT_IN_TRIALS, gate_passed=1)
            char["chargen_notes"] = json.dumps({"village_first_audience_done": True})
            session = FakeSession(char)
            db = FakeDB(char)
            ok = await maybe_handle_yarael_first_audience(
                session, db, char, YARAEL_NAME,
            )
            assert ok is False  # Already done; no re-fire
            assert len(session.received) == 0
        asyncio.run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 9. Hermit after_lines emission (W.2 phase 2 carry-over)
# ─────────────────────────────────────────────────────────────────────────────


class TestHermitAfterLines:
    """The Hermit emits a gate.after_line for invited PCs (act >= 1)."""

    def test_pre_invitation_no_after_lines(self):
        """Pre-invitation PC: no after_line emitted by check_village_quest."""
        async def _check():
            char = _make_char(act=ACT_PRE_INVITATION)
            char["force_signs_accumulated"] = 0  # not eligible
            session = FakeSession(char)
            db = FakeDB(char)

            await check_village_quest(
                session, db, "talk", npc_name=HERMIT_NAME,
            )
            # No after_lines (PC is at act 0, ineligible)
            output = "\n".join(session.received)
            # The Hermit's authored text contains specific phrases — we just
            # check that no after_line was emitted (which always begins with
            # the asterisk-bracketed action). We also accept empty output.
            for line in session.received:
                assert "stands, slowly" not in line
                assert "found your way here" not in line
        asyncio.run(_check())

    def test_invited_pc_gets_after_line(self):
        async def _check():
            char = _make_char(act=ACT_INVITED, gate_passed=0)
            session = FakeSession(char)
            db = FakeDB(char)

            await check_village_quest(
                session, db, "talk", npc_name=HERMIT_NAME,
            )
            # An after_line should have been emitted. The Hermit's
            # authored after_lines mention specific imagery — at least one
            # of the four should appear.
            output = "\n".join(session.received)
            authored_markers = [
                "stands, slowly",
                "found your way here",
                "deep dunes",
                "Anchor Stones",
                "first light",
                "edge of a thread",
            ]
            assert any(m in output for m in authored_markers), \
                f"No Hermit after_line markers found in output: {output!r}"
        asyncio.run(_check())

    def test_after_lines_deterministic_per_day(self):
        """Same char + same day = same line (caching property)."""
        async def _check():
            char = _make_char(act=ACT_INVITED, id_=42)
            session1 = FakeSession(char)
            db = FakeDB(char)
            await check_village_quest(session1, db, "talk", npc_name=HERMIT_NAME)
            line1 = next((s for s in session1.received if "*" in s or "Hermit" in s), "")

            session2 = FakeSession(char)
            await check_village_quest(session2, db, "talk", npc_name=HERMIT_NAME)
            line2 = next((s for s in session2.received if "*" in s or "Hermit" in s), "")

            assert line1 == line2  # same character, same day → same line
        asyncio.run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 10. GateCommand registered + module guards
# ─────────────────────────────────────────────────────────────────────────────


class TestGateCommandRegistered:
    def test_gate_command_class_present(self):
        with open(
            os.path.join(PROJECT_ROOT, "parser", "npc_commands.py"),
            encoding="utf-8",
        ) as fh:
            text = fh.read()
        assert "class GateCommand" in text
        assert "GateCommand()" in text

    def test_vitha_pre_ai_hook_present(self):
        with open(
            os.path.join(PROJECT_ROOT, "parser", "npc_commands.py"),
            encoding="utf-8",
        ) as fh:
            text = fh.read()
        assert "maybe_intercept_vitha_talk" in text


class TestSourceLevelGuards:
    def test_village_dialogue_module_exists(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_dialogue.py")
        assert os.path.exists(path)

    def test_village_quest_imports_yarael_hook(self):
        path = os.path.join(PROJECT_ROOT, "engine", "village_quest.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "maybe_handle_yarael_first_audience" in text

    def test_load_jedi_village_npcs_present(self):
        path = os.path.join(PROJECT_ROOT, "engine", "npc_loader.py")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "load_jedi_village_npcs" in text
        assert "_load_jedi_village_npcs_file" in text

    def test_era_yaml_jedi_village_ref(self):
        path = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "era.yaml")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert "jedi_village_npcs" in text
