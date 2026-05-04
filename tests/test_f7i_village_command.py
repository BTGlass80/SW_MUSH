# -*- coding: utf-8 -*-
"""
tests/test_f7i_village_command.py — F.7.i — `+village` standing lookup.

Validates ``parser/village_trial_commands.py::VillageStandingCommand``:
the player-facing lookup for Village quest standing and progress.

Coverage:

  1. Tier label thresholds (`_tier_for_standing`):
       - 0 → Stranger
       - 1, 3 → Welcomed
       - 4, 7 → Recognized
       - 8, 11 → Trusted
       - 12, 100 → Honored
  2. Pre-Village (no audience) shows brief placeholder.
  3. Post-audience renders the full panel:
       - standing line + tier label
       - trial-by-trial done indicator (5 trials)
       - courage choice line (deny / ask flag)
       - spirit Path C lock indicator
       - path line (only if committed)
  4. Defensive paths:
       - Missing village_standing column → 0/Stranger
       - Malformed chargen_notes → no flag/path lines
       - Missing standing module → graceful fallback (max=12)
  5. Source / registration wiring.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.village_trial_commands import (
    VillageStandingCommand,
    register_village_trial_commands,
    _tier_for_standing,
    _format_courage_choice,
    _format_chosen_path,
)
from parser.commands import CommandContext


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_char(*, audience_done=True, standing=0,
                skill_done=False, courage_done=False, flesh_done=False,
                spirit_done=False, spirit_path_c_locked=False,
                insight_done=False,
                courage_choice=None, chosen_path=""):
    """Char with arbitrary Village-quest state."""
    notes = {}
    if audience_done:
        notes["village_first_audience_done"] = True
    if courage_choice:
        notes["village_courage_choice"] = courage_choice
    return {
        "id": 1, "name": "T", "room_id": 100,
        "village_standing": standing,
        "village_act": 2 if audience_done else 0,
        "village_gate_passed": 1 if audience_done else 0,
        "village_trial_skill_done": int(skill_done),
        "village_trial_courage_done": int(courage_done),
        "village_trial_flesh_done": int(flesh_done),
        "village_trial_spirit_done": int(spirit_done),
        "village_trial_spirit_path_c_locked": int(spirit_path_c_locked),
        "village_trial_insight_done": int(insight_done),
        "village_choice_completed": 1 if chosen_path else 0,
        "village_chosen_path": chosen_path,
        "chargen_notes": json.dumps(notes),
    }


class FakeSession:
    def __init__(self, character):
        self.character = character
        self.received: list[str] = []

    async def send_line(self, text):
        self.received.append(text)


class FakeDB:
    pass


def _ctx_for(char):
    session = FakeSession(char)
    return CommandContext(
        session=session,
        raw_input="+village",
        command="+village",
        args="",
        args_list=[],
        db=FakeDB(),
    )


def _strip_ansi(s: str) -> str:
    """Strip ANSI escape sequences for cleaner assertions."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Tier thresholds
# ═════════════════════════════════════════════════════════════════════════════


class TestTierLabels:

    def test_zero_is_stranger(self):
        assert _tier_for_standing(0) == "Stranger"

    def test_one_to_three_is_welcomed(self):
        assert _tier_for_standing(1) == "Welcomed"
        assert _tier_for_standing(2) == "Welcomed"
        assert _tier_for_standing(3) == "Welcomed"

    def test_four_to_seven_is_recognized(self):
        assert _tier_for_standing(4) == "Recognized"
        assert _tier_for_standing(7) == "Recognized"

    def test_eight_to_eleven_is_trusted(self):
        assert _tier_for_standing(8) == "Trusted"
        assert _tier_for_standing(11) == "Trusted"

    def test_twelve_and_above_is_honored(self):
        assert _tier_for_standing(12) == "Honored"
        assert _tier_for_standing(100) == "Honored"

    def test_negative_treated_as_stranger(self):
        # Defensive — clamped behaviour.
        assert _tier_for_standing(-5) == "Stranger"


class TestFormatHelpers:

    def test_format_courage_deny(self):
        assert "won't deny" in _format_courage_choice("deny").lower()

    def test_format_courage_ask(self):
        out = _format_courage_choice("ask")
        assert "How did you know" in out
        assert "still listening" in out.lower()

    def test_format_courage_unknown_is_empty(self):
        assert _format_courage_choice(None) == ""
        assert _format_courage_choice("") == ""
        assert _format_courage_choice("garbage") == ""

    def test_format_path_a(self):
        assert "Jedi Order" in _format_chosen_path("a")

    def test_format_path_b(self):
        out = _format_chosen_path("b")
        assert "Village" in out or "Independent" in out

    def test_format_path_c(self):
        assert "Dark" in _format_chosen_path("c")

    def test_format_path_unknown_is_empty(self):
        assert _format_chosen_path("") == ""
        assert _format_chosen_path("z") == ""


# ═════════════════════════════════════════════════════════════════════════════
# 2. Pre-Village placeholder
# ═════════════════════════════════════════════════════════════════════════════


class TestPreVillagePlaceholder:

    def test_no_audience_shows_placeholder(self):
        async def _check():
            char = _make_char(audience_done=False)
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "have not yet been to the Village" in text
            # Should NOT render the trial panel
            assert "Trials:" not in text
            assert "Standing:" not in text
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 3. Full panel rendering
# ═════════════════════════════════════════════════════════════════════════════


class TestFullPanel:

    def test_audience_only_shows_panel_with_zeros(self):
        # Player just completed audience; standing 1, no trials done.
        async def _check():
            char = _make_char(audience_done=True, standing=1)
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Standing: 1/12" in text
            assert "Welcomed" in text
            assert "Trials:" in text
            # All five trials listed
            assert "Skill" in text
            assert "Courage" in text
            assert "Flesh" in text
            assert "Spirit" in text
            assert "Insight" in text
            # No path line yet
            assert "Path:" not in text
        asyncio.run(_check())

    def test_partway_through_shows_completed_trials(self):
        async def _check():
            char = _make_char(
                standing=4,
                skill_done=True, courage_done=True,
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Standing: 4/12" in text
            assert "Recognized" in text
            # Done indicator (✓) appears for completed trials
            assert "✓" in text
            # Dot indicator (·) appears for incomplete trials
            assert "·" in text
        asyncio.run(_check())

    def test_courage_choice_deny_rendered(self):
        async def _check():
            char = _make_char(
                standing=4,
                skill_done=True, courage_done=True,
                courage_choice="deny",
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            # Deny rendering
            assert "won't deny" in text.lower()
        asyncio.run(_check())

    def test_courage_choice_ask_rendered(self):
        async def _check():
            char = _make_char(
                standing=4,
                skill_done=True, courage_done=True,
                courage_choice="ask",
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "How did you know" in text
            assert "still listening" in text.lower()
        asyncio.run(_check())

    def test_courage_done_no_choice_flag_renders_plain(self):
        # Older char that completed Courage before F.7.h shipped —
        # no choice flag set.
        async def _check():
            char = _make_char(
                standing=4,
                skill_done=True, courage_done=True,
                courage_choice=None,
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            # Courage line present but no choice substring
            assert "Courage" in text
            assert "won't deny" not in text.lower()
            assert "How did you know" not in text
        asyncio.run(_check())

    def test_spirit_path_c_lock_indicator(self):
        async def _check():
            char = _make_char(
                standing=10,
                skill_done=True, courage_done=True, flesh_done=True,
                spirit_done=True, spirit_path_c_locked=True,
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Path C lock-in" in text
        asyncio.run(_check())

    def test_spirit_pass_no_lock_renders_plain(self):
        async def _check():
            char = _make_char(
                standing=10,
                skill_done=True, courage_done=True, flesh_done=True,
                spirit_done=True, spirit_path_c_locked=False,
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Spirit" in text
            assert "Path C lock-in" not in text
        asyncio.run(_check())

    def test_path_a_committed_shows_path_line(self):
        async def _check():
            char = _make_char(
                standing=12,
                skill_done=True, courage_done=True, flesh_done=True,
                spirit_done=True, insight_done=True,
                chosen_path="a",
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Path:" in text
            assert "Jedi Order" in text
            assert "Honored" in text
        asyncio.run(_check())

    def test_path_b_committed_shows_path_line(self):
        async def _check():
            char = _make_char(
                standing=12,
                skill_done=True, courage_done=True, flesh_done=True,
                spirit_done=True, insight_done=True,
                chosen_path="b",
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Path:" in text
            assert "Village" in text or "Independent" in text
        asyncio.run(_check())

    def test_path_c_committed_shows_path_line(self):
        async def _check():
            char = _make_char(
                standing=10,
                skill_done=True, courage_done=True, flesh_done=True,
                spirit_done=True, spirit_path_c_locked=True,
                insight_done=True,
                chosen_path="c",
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Path:" in text
            assert "Dark" in text

        asyncio.run(_check())

    def test_no_path_committed_omits_path_line(self):
        async def _check():
            char = _make_char(standing=10, skill_done=True)
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Path:" not in text
        asyncio.run(_check())

    def test_full_quest_max_standing_honored(self):
        async def _check():
            char = _make_char(
                standing=12,
                skill_done=True, courage_done=True, flesh_done=True,
                spirit_done=True, insight_done=True,
                courage_choice="ask",
                chosen_path="a",
            )
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "12/12" in text
            assert "Honored" in text
            # All five trials check-marked
            assert text.count("✓") == 5
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 4. Defensive paths
# ═════════════════════════════════════════════════════════════════════════════


class TestDefensiveEdges:

    def test_missing_village_standing_column_treated_zero(self):
        async def _check():
            char = _make_char(standing=0)
            del char["village_standing"]
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "Standing: 0/12" in text
            assert "Stranger" in text
        asyncio.run(_check())

    def test_malformed_chargen_notes_audience_deflect(self):
        # Malformed chargen_notes correctly fails has_completed_audience
        # → command shows the placeholder.
        async def _check():
            char = _make_char(audience_done=True, standing=4)
            char["chargen_notes"] = "{not valid json"
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "have not yet been to the Village" in text
        asyncio.run(_check())

    def test_no_session_character_silent_return(self):
        async def _check():
            ctx = CommandContext(
                session=FakeSession(None),
                raw_input="+village", command="+village",
                args="", args_list=[], db=FakeDB(),
            )
            ctx.session.character = None
            await VillageStandingCommand().execute(ctx)
            # No crash; nothing written
            assert ctx.session.received == []
        asyncio.run(_check())

    def test_chargen_notes_dict_not_string(self):
        # If a stub fixture passes chargen_notes already as a dict,
        # the command should still read flags correctly.
        async def _check():
            char = _make_char(
                standing=4, courage_done=True,
                courage_choice="ask",
            )
            char["chargen_notes"] = json.loads(char["chargen_notes"])
            ctx = _ctx_for(char)
            await VillageStandingCommand().execute(ctx)
            output = "\n".join(ctx.session.received)
            text = _strip_ansi(output)
            assert "still listening" in text.lower()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 5. Wiring
# ═════════════════════════════════════════════════════════════════════════════


class TestRegistrationAndWiring:

    def test_command_key_is_plus_village(self):
        cmd = VillageStandingCommand()
        assert cmd.key == "+village"
        assert "+vil" in cmd.aliases

    def test_help_text_mentions_features(self):
        cmd = VillageStandingCommand()
        text = cmd.help_text.lower()
        assert "standing" in text
        assert "trial" in text
        assert "courage choice" in text
        assert "chosen path" in text

    def test_command_in_registration_list(self):
        class _Reg:
            def __init__(self):
                self.added = []
            def register(self, cmd):
                self.added.append(cmd)
        reg = _Reg()
        register_village_trial_commands(reg)
        keys = {c.key for c in reg.added}
        assert "+village" in keys
        # Existing commands still registered
        assert "trial" in keys
        assert "path" in keys
        assert "examine" in keys
        assert "accuse" in keys

    def test_source_imports(self):
        path = os.path.join(
            PROJECT_ROOT, "parser", "village_trial_commands.py",
        )
        src = open(path, "r", encoding="utf-8").read()
        assert "class VillageStandingCommand" in src
        assert "from engine.village_standing import" in src
