# -*- coding: utf-8 -*-
"""
tests/test_smoke_flagged_resolutions.py — Regression-guards for the
five v42 §6.5 "smoke-flagged design issues" that the architecture
doc lists as open but which are actually resolved at HEAD.

Background
==========

v42 §6.5 lists five smoke-flagged design issues "(unchanged from v41
§6.5; none have been resolved this period.)" Pre-flight audit of
this drop grep'd HEAD for each and found that all five are now
actually resolved at HEAD — the architecture doc note is stale, a
§6.2 phantom-undelivered pattern at the architecture-doc layer.

The five issues, copied verbatim from v39 §6.5 (the last version
that listed them in full before v40/v41/v42 started using
"unchanged" as the body):

  | # | Issue                                                          | Recommendation |
  |---|----------------------------------------------------------------|----------------|
  | 5 | `+ooc` (room-local) vs `ooc` (global) — same display, different scope | Pick one; deprecate or rename |
  | 6 | `page` aliased to `whisper` (same-room only)                   | Either separate `page` or document the behavior in `+help page` |
  | 7 | `whisper` requires `=` separator                                | Accept `whisper Bob hello` form too, or fix help |
  | 8 | Survey cooldown soft warning                                    | Investigate `engine/surveying.py` cooldown logic |
  | D1| Room #3 (Chalmun's Cantina) `zone_id=NULL`                      | Data fix in source YAML; canonical container should not be null |

Status at HEAD (May 18, 2026) per pre-flight audit:

  * **#5** — Was partially resolved by the registration order making
    `channel_commands.OocCommand` (key `ooc`) win the bare-token
    registration. Display tag was still ambiguous: both `[OOC] Name:
    msg` from `server/channels.py::fmt_ooc` (purple, global) and
    `[OOC] Name: msg` from `parser/builtin_commands.py::OocCommand`
    (dim grey, room-local) used the same `[OOC]` prefix. This drop
    changes the room-local display to `[Local OOC]` for unambiguous
    scope identification at the receive end. Help text also rewritten
    to be explicit about local vs global.
  * **#6** — Fully resolved. `parser/mux_commands.py::PageCommand`
    (key `page`) registers after `parser/builtin_commands.py::
    WhisperCommand` (which had `page` in aliases). Registry behavior
    (parser/commands.py L100-106): direct-key registration silently
    overrides alias entries for the same name. Result: `page` invokes
    PageCommand (cross-room private messaging), `whisper` invokes
    WhisperCommand (same-room private messaging). This drop also
    removes the dead `page` alias from WhisperCommand for clarity.
  * **#7** — Already resolved. WhisperCommand.help_text already
    documents the `=` syntax with an example
    (`whisper Tundra = Meet me at bay 94.`).
  * **#8** — Already resolved. `parser/crafting_commands.py::
    SurveyCommand.execute` enforces a 5-minute cooldown via
    `engine/cooldowns.py::CD_SURVEY` + `SURVEY_COOLDOWN_S`. Existing
    test_economy_validation.py::test_survey_has_cooldown locks it.
    The smoke #8 "soft warning" was for the pre-cooldown era.
  * **#D1** — Stale. The original May 1 bug was "live DB room id=3
    (then Chalmun's Cantina) had zone_id=NULL". After F.4c room
    renumbering, room id=3 is now `spaceport_speeders`, and Chalmun's
    rooms (id 12-14 in both CW and GCW tatooine.yaml) all have proper
    zone fields. The fix happened implicitly via room reorganization.

This test file locks all five resolutions so a future drop can't
silently regress them:

  1. ``TestSmokeFive_OocScopeDisambiguation`` — locks the [Local OOC]
     prefix for room-local +ooc and that the global ooc channel
     command exists with the original [OOC] prefix.
  2. ``TestSmokeSix_PageNotAliasedToWhisper`` — locks that `page` is
     a standalone PageCommand (not a WhisperCommand alias) and that
     WhisperCommand no longer carries the dead `page` alias.
  3. ``TestSmokeSeven_WhisperHelpDocumentsEquals`` — locks that
     WhisperCommand.help_text includes the `=` syntax example.
  4. ``TestSmokeEight_SurveyCooldownEnforced`` — locks that
     SurveyCommand.execute references CD_SURVEY and SURVEY_COOLDOWN_S
     (the byte-level signature of cooldown enforcement). Behavioral
     enforcement is already locked by test_economy_validation.py.
  5. ``TestSmokeD1_ChalmunCantinaRoomsHaveZone`` — locks that every
     Chalmun's Cantina room in both CW and GCW tatooine.yaml has a
     non-null ``zone`` field. The original NULL-zone bug surfaced
     because zone-scoped commands (sabacc, perform) silently failed
     for players in unzoned rooms; this test guards against a future
     drop accidentally clearing the zone field again.

If any of these tests fail after a future drop, the §6.5 issue is
regressing and the fix needs to be re-applied before the drop ships.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


BUILTIN_COMMANDS_PY = PROJECT_ROOT / "parser" / "builtin_commands.py"
MUX_COMMANDS_PY = PROJECT_ROOT / "parser" / "mux_commands.py"
CHANNEL_COMMANDS_PY = PROJECT_ROOT / "parser" / "channel_commands.py"
CRAFTING_COMMANDS_PY = PROJECT_ROOT / "parser" / "crafting_commands.py"
COOLDOWNS_PY = PROJECT_ROOT / "engine" / "cooldowns.py"
CW_TATOOINE_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                    / "planets" / "tatooine.yaml")
GCW_TATOOINE_YAML = (PROJECT_ROOT / "data" / "worlds" / "gcw"
                     / "planets" / "tatooine.yaml")


# ═════════════════════════════════════════════════════════════════════
# 1. Smoke #5 — +ooc vs ooc scope disambiguation
# ═════════════════════════════════════════════════════════════════════


class TestSmokeFive_OocScopeDisambiguation(unittest.TestCase):
    """Smoke #5 fix: room-local +ooc renders with [Local OOC] prefix
    to differentiate from the global ooc channel's [OOC] prefix.
    """

    @classmethod
    def setUpClass(cls):
        cls.builtin_src = _read_text(BUILTIN_COMMANDS_PY)
        cls.channel_src = _read_text(CHANNEL_COMMANDS_PY)

    def test_room_local_ooc_renders_local_ooc_prefix(self):
        """parser/builtin_commands.py OocCommand must emit a
        '[Local OOC]' prefix (not the ambiguous '[OOC]') for the
        in-scope text and the scene-log capture."""
        # The send-line text construction:
        self.assertIn(
            "[Local OOC] {name}",
            self.builtin_src,
            "parser/builtin_commands.py::OocCommand.execute should "
            "render text with '[Local OOC]' prefix. If this fails, "
            "the room-local OOC display has regressed to ambiguous "
            "'[OOC]' which collides visually with global ooc."
        )
        # Slice-based: scan the file for any 'capture_pose' call site
        # and inspect a 6-line window for the joint signature of (a)
        # the [Local OOC] prefix and (b) pose_type='ooc' with
        # is_ooc=True. This is the scene-log capture entry that
        # persists OOC chatter into the scene replay log.
        lines = self.builtin_src.splitlines()
        found_local_ooc_scene_log = False
        for i, line in enumerate(lines):
            if "capture_pose(" in line:
                window = "\n".join(lines[i:i + 8])
                if ("[Local OOC]" in window
                        and 'pose_type="ooc"' in window
                        and "is_ooc=True" in window):
                    found_local_ooc_scene_log = True
                    break
        self.assertTrue(
            found_local_ooc_scene_log,
            "parser/builtin_commands.py::OocCommand scene-log capture "
            "should use '[Local OOC]' prefix in the call where "
            "pose_type='ooc' and is_ooc=True — keeping prefix "
            "consistent between live display and replay."
        )

    def test_global_ooc_channel_keeps_ooc_prefix(self):
        """server/channels.py::fmt_ooc owns the global ooc display
        ('[OOC] Name: msg'). The smoke #5 fix changes only the
        room-local prefix; the global one stays as-is so existing
        playerbase muscle memory and chat-log archives don't break."""
        channels_py = PROJECT_ROOT / "server" / "channels.py"
        channels_src = _read_text(channels_py)
        # fmt_ooc must still produce a literal '[OOC]'
        self.assertIn(
            "[OOC]",
            channels_src,
            "server/channels.py::fmt_ooc should still emit '[OOC]' "
            "for global channel ooc. Smoke #5 fix only changes the "
            "room-local prefix to '[Local OOC]'."
        )
        # And it must NOT have been accidentally changed to
        # '[Local OOC]' (which would invert the disambiguation).
        self.assertNotIn(
            "[Local OOC]",
            channels_src,
            "server/channels.py should NOT use '[Local OOC]' — that "
            "tag is reserved for the room-local +ooc command. Global "
            "ooc channel keeps '[OOC]'."
        )

    def test_room_local_ooc_help_text_mentions_scope(self):
        """The +ooc command's help_text should make scope explicit so
        a player typing 'help +ooc' learns the local vs global
        distinction without reading source code."""
        # Slice-based extraction: find the OocCommand line with
        # key='+ooc', then take a bounded ~60-line window after it,
        # then check tokens. Avoids regex catastrophic backtracking
        # on the 4000+ line source.
        lines = self.builtin_src.splitlines()
        ooc_idx = None
        for i, line in enumerate(lines):
            if 'key = "+ooc"' in line:
                # Walk backward up to 5 lines to confirm the
                # enclosing 'class OocCommand'.
                for j in range(max(0, i - 5), i):
                    if 'class OocCommand' in lines[j]:
                        ooc_idx = i
                        break
                if ooc_idx is not None:
                    break
        self.assertIsNotNone(
            ooc_idx,
            "Could not locate OocCommand with key='+ooc' in "
            "parser/builtin_commands.py. The class structure may "
            "have changed; update this test."
        )
        # Bounded window — help_text fits within 60 lines easily.
        window = "\n".join(lines[ooc_idx:ooc_idx + 60]).lower()
        # At least one of these scope-disambiguating markers should
        # be present. Multiple acceptable phrasings — but the help
        # has to communicate scope.
        markers = (
            "room-local", "same room", "local", "co-located",
            "current room",
        )
        self.assertTrue(
            any(m in window for m in markers),
            f"+ooc help_text should mention scope (one of "
            f"{markers!r}). Window: {window[:300]!r}"
        )

    def test_channel_ooc_command_still_registered(self):
        """The global ooc channel command exists at its expected
        location — sanity that smoke #5 fix didn't accidentally
        remove it."""
        self.assertIn(
            'class OocCommand(BaseCommand):',
            self.channel_src,
            "parser/channel_commands.py should still define "
            "OocCommand for the global ooc channel."
        )
        self.assertRegex(
            self.channel_src,
            r'key = "ooc"',
            "channel_commands.py::OocCommand should have key='ooc'."
        )


# ═════════════════════════════════════════════════════════════════════
# 2. Smoke #6 — page not aliased to whisper
# ═════════════════════════════════════════════════════════════════════


class TestSmokeSix_PageNotAliasedToWhisper(unittest.TestCase):
    """Smoke #6 fix: `page` is a standalone PageCommand in
    mux_commands.py with cross-room scope. The dead `page` alias in
    WhisperCommand has been removed.
    """

    @classmethod
    def setUpClass(cls):
        cls.builtin_src = _read_text(BUILTIN_COMMANDS_PY)
        cls.mux_src = _read_text(MUX_COMMANDS_PY)

    def test_page_command_exists_with_dedicated_key(self):
        """parser/mux_commands.py defines PageCommand with key 'page'.
        This is the cross-room private-messaging command."""
        self.assertIn(
            'class PageCommand(BaseCommand):',
            self.mux_src,
            "parser/mux_commands.py should still define PageCommand."
        )
        # Find PageCommand by line and verify the next non-blank
        # non-docstring line declares key='page'.
        lines = self.mux_src.splitlines()
        page_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class PageCommand(BaseCommand):":
                page_idx = i
                break
        self.assertIsNotNone(page_idx)
        window = "\n".join(lines[page_idx:page_idx + 5])
        self.assertIn(
            'key = "page"', window,
            f"mux_commands.py::PageCommand should declare "
            f"key='page' within 5 lines of class definition. "
            f"Window: {window!r}"
        )

    def test_whisper_does_not_alias_page(self):
        """WhisperCommand must not list 'page' in its aliases — the
        alias was dead code (PageCommand's key registers later and
        wins per parser/commands.py L100-106) and removing it
        eliminates confusion."""
        lines = self.builtin_src.splitlines()
        whisper_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class WhisperCommand(BaseCommand):":
                whisper_idx = i
                break
        self.assertIsNotNone(
            whisper_idx,
            "Could not locate 'class WhisperCommand(BaseCommand):' "
            "in parser/builtin_commands.py. The class may have been "
            "renamed; update this test."
        )
        # WhisperCommand's aliases line should be within the next
        # 5 lines (key + aliases). Find the aliases= line and parse.
        aliases_line = None
        for j in range(whisper_idx, min(whisper_idx + 10, len(lines))):
            stripped = lines[j].strip()
            if stripped.startswith("aliases = ["):
                aliases_line = stripped
                break
        self.assertIsNotNone(
            aliases_line,
            "WhisperCommand has no 'aliases = [...]' line within "
            "10 lines of class definition. Class shape may have "
            "changed; update this test."
        )
        # Parse the list literal.
        m = re.match(r'aliases\s*=\s*(\[[^\]]*\])', aliases_line)
        self.assertIsNotNone(
            m,
            f"WhisperCommand aliases line could not be parsed: "
            f"{aliases_line!r}"
        )
        aliases = eval(m.group(1))  # noqa: S307 — test-only literal
        self.assertNotIn(
            "page", aliases,
            f"WhisperCommand.aliases should not contain 'page' (dead "
            f"code; PageCommand owns that key). Found: {aliases}"
        )

    def test_whisper_help_references_page(self):
        """Help text should point cross-room-needing players at the
        separate `page` command so the missing alias doesn't surprise
        anyone."""
        lines = self.builtin_src.splitlines()
        whisper_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class WhisperCommand(BaseCommand):":
                whisper_idx = i
                break
        self.assertIsNotNone(whisper_idx)
        # 30-line window catches the help_text block.
        window = "\n".join(
            lines[whisper_idx:whisper_idx + 30]
        ).lower()
        self.assertIn(
            "page", window,
            f"WhisperCommand.help_text should mention `page` so "
            f"players looking for cross-room private messaging are "
            f"directed to the right command. Window: {window[:300]!r}"
        )


# ═════════════════════════════════════════════════════════════════════
# 3. Smoke #7 — whisper help documents = separator
# ═════════════════════════════════════════════════════════════════════


class TestSmokeSeven_WhisperHelpDocumentsEquals(unittest.TestCase):
    """Smoke #7 fix: WhisperCommand.help_text includes the `=` syntax
    with a concrete example. Resolved at HEAD before this drop; locked
    here as a regression-guard.
    """

    @classmethod
    def setUpClass(cls):
        cls.builtin_src = _read_text(BUILTIN_COMMANDS_PY)

    def test_whisper_help_shows_equals_separator_in_example(self):
        lines = self.builtin_src.splitlines()
        whisper_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class WhisperCommand(BaseCommand):":
                whisper_idx = i
                break
        self.assertIsNotNone(
            whisper_idx,
            "Could not locate 'class WhisperCommand(BaseCommand):'."
        )
        # 30-line window covers the help_text block.
        window = "\n".join(lines[whisper_idx:whisper_idx + 30])
        # The EXAMPLE or USAGE line must show the `=` separator in
        # syntax form. We don't pin the exact example text — the
        # structural check is that `whisper X = Y` shape appears
        # somewhere in the help block. Either:
        #   1. "whisper <player> = <message>" (usage form)
        #   2. "whisper Tundra = Meet me at bay 94" (example form)
        equals_in_syntax = re.search(
            r'whisper\s+\S+\s*=\s*\S',
            window,
            re.IGNORECASE,
        )
        self.assertIsNotNone(
            equals_in_syntax,
            "WhisperCommand.help_text should show the `=` separator "
            "in a 'whisper X = Y' shape — usage or example form. "
            f"Window: {window[:400]!r}"
        )

    def test_whisper_execute_still_requires_equals(self):
        """The execute method should still treat absence of `=` as a
        usage error, matching what the help text documents. Smoke #7's
        alternative resolution would have accepted `whisper Bob hello`
        positionally; current HEAD chose 'fix the help' instead."""
        lines = self.builtin_src.splitlines()
        whisper_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class WhisperCommand(BaseCommand):":
                whisper_idx = i
                break
        self.assertIsNotNone(whisper_idx)
        # Find the next 'class ' definition to bound the search.
        next_class = len(lines)
        for j in range(whisper_idx + 1, len(lines)):
            if lines[j].startswith("class "):
                next_class = j
                break
        body = "\n".join(lines[whisper_idx:next_class])
        # The classic shape: `if "=" not in ctx.args:` early-return
        # with a usage message.
        self.assertIn(
            '"=" not in ctx.args',
            body,
            "WhisperCommand.execute should still gate on '=' being "
            "present in args. The help text documents this; a "
            "regression that silently accepts positional form would "
            "diverge from the documented behavior."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. Smoke #8 — Survey cooldown enforced
# ═════════════════════════════════════════════════════════════════════


class TestSmokeEight_SurveyCooldownEnforced(unittest.TestCase):
    """Smoke #8 fix: SurveyCommand enforces a 5-minute cooldown via
    the engine.cooldowns module. Resolved at HEAD; behavioral
    enforcement is locked by tests/test_economy_validation.py::
    test_survey_has_cooldown. This test locks the byte-level
    signature of the cooldown wire-up so a future refactor that
    removes the call sites without removing the test fixture catches
    here.
    """

    @classmethod
    def setUpClass(cls):
        cls.survey_src = _read_text(CRAFTING_COMMANDS_PY)
        cls.cooldowns_src = _read_text(COOLDOWNS_PY)

    def test_cooldown_constants_defined(self):
        """engine/cooldowns.py defines CD_SURVEY and SURVEY_COOLDOWN_S
        as the survey-cooldown key and duration."""
        self.assertRegex(
            self.cooldowns_src,
            r'CD_SURVEY\s*=\s*"survey"',
            "engine/cooldowns.py must define CD_SURVEY='survey'. "
            "Without it, SurveyCommand's import will fail at run time."
        )
        # SURVEY_COOLDOWN_S must be a positive int (5 minutes = 300s
        # is the v42-locked value, but we don't pin the literal — a
        # future drop tweaking the value to 240 or 360 should not
        # break this test).
        m = re.search(
            r'SURVEY_COOLDOWN_S\s*=\s*(\d+)',
            self.cooldowns_src,
        )
        self.assertIsNotNone(
            m,
            "engine/cooldowns.py must define SURVEY_COOLDOWN_S as an "
            "integer-literal seconds value."
        )
        value = int(m.group(1))
        self.assertGreater(
            value, 0,
            f"SURVEY_COOLDOWN_S must be positive (got {value}). A "
            f"zero or negative cooldown disables enforcement."
        )

    def test_survey_command_calls_remaining_cooldown(self):
        """SurveyCommand.execute imports remaining_cooldown and uses
        it as the gate check before resource collection."""
        self.assertIn(
            "remaining_cooldown",
            self.survey_src,
            "parser/crafting_commands.py should reference "
            "remaining_cooldown (from engine.cooldowns) for the "
            "survey cooldown gate. Without this, the smoke #8 fix "
            "is reverted."
        )
        self.assertRegex(
            self.survey_src,
            r'remaining_cooldown\(char,\s*CD_SURVEY\)',
            "SurveyCommand should call remaining_cooldown(char, "
            "CD_SURVEY) — that's the byte-level signature of the "
            "cooldown gate."
        )

    def test_survey_command_sets_cooldown_on_success(self):
        """SurveyCommand sets the cooldown after a successful survey.
        Otherwise the cooldown never starts and gate is a no-op."""
        self.assertRegex(
            self.survey_src,
            r'set_cooldown\(char,\s*CD_SURVEY,\s*SURVEY_COOLDOWN_S\)',
            "SurveyCommand should call set_cooldown(char, CD_SURVEY, "
            "SURVEY_COOLDOWN_S) to start the cooldown after surveying."
        )


# ═════════════════════════════════════════════════════════════════════
# 5. Smoke #D1 — Chalmun's Cantina rooms have non-null zone
# ═════════════════════════════════════════════════════════════════════


class TestSmokeD1_ChalmunCantinaRoomsHaveZone(unittest.TestCase):
    """Smoke #D1 fix: every Chalmun's Cantina room in both CW and GCW
    tatooine.yaml has a non-null ``zone`` field.

    The original May 1 bug surfaced as 'room id=3 (then Chalmun's
    Cantina) has zone_id=NULL'. After F.4c room renumbering,
    Chalmun's rooms moved to ids 12-14 and zone fields were
    explicitly populated. This test guards against a future drop
    accidentally clearing the zone field again — zone-scoped
    commands (sabacc, perform) silently fail for unzoned-room
    players.
    """

    def _chalmun_rooms(self, planet_yaml: Path):
        data = _read_yaml(planet_yaml)
        rooms = data.get("rooms") or []
        # We identify Chalmun's rooms by either name (display) or
        # slug (stable id). The CW slug is "chalmuans_*" (legacy
        # typo, intentional per AreaGeometry slug-stability rules);
        # the GCW slug is "chalmuns_*" (corrected). Either pattern
        # plus the display-name regex catches them.
        out = []
        for r in rooms:
            name = r.get("name", "") or ""
            slug = r.get("slug", "") or ""
            if "Chalmun" in name or "chalmun" in slug.lower():
                out.append(r)
        return out

    def test_cw_chalmun_rooms_all_have_zone(self):
        chalmun_rooms = self._chalmun_rooms(CW_TATOOINE_YAML)
        self.assertGreaterEqual(
            len(chalmun_rooms), 3,
            f"Expected at least 3 Chalmun's Cantina rooms in CW "
            f"tatooine.yaml (entrance, main bar, back hallway). "
            f"Found {len(chalmun_rooms)}."
        )
        unzoned = [
            (r.get("id"), r.get("slug"))
            for r in chalmun_rooms
            if not r.get("zone")
        ]
        self.assertEqual(
            unzoned, [],
            f"CW Chalmun's Cantina rooms with NULL/missing zone: "
            f"{unzoned}. Every room in this complex must have a "
            f"non-null `zone` field — zone-scoped commands like "
            f"sabacc and perform silently fail otherwise. Restore "
            f"the `zone: tatooine_cantina` field on each affected "
            f"room."
        )

    def test_gcw_chalmun_rooms_all_have_zone(self):
        chalmun_rooms = self._chalmun_rooms(GCW_TATOOINE_YAML)
        self.assertGreaterEqual(
            len(chalmun_rooms), 3,
            f"Expected at least 3 Chalmun's Cantina rooms in GCW "
            f"tatooine.yaml. Found {len(chalmun_rooms)}."
        )
        unzoned = [
            (r.get("id"), r.get("slug"))
            for r in chalmun_rooms
            if not r.get("zone")
        ]
        self.assertEqual(
            unzoned, [],
            f"GCW Chalmun's Cantina rooms with NULL/missing zone: "
            f"{unzoned}. Restore the `zone: cantina` field on each "
            f"affected room."
        )

    def test_cw_chalmun_rooms_all_share_a_zone(self):
        """Sanity: every Chalmun's room should share the same zone
        value (it's a single building). Mixed zone fields would
        indicate a hand-editing error."""
        chalmun_rooms = self._chalmun_rooms(CW_TATOOINE_YAML)
        zones = {r.get("zone") for r in chalmun_rooms}
        self.assertEqual(
            len(zones), 1,
            f"CW Chalmun's Cantina rooms span multiple zones: "
            f"{zones}. All rooms in the cantina complex should share "
            f"one zone."
        )

    def test_gcw_chalmun_rooms_all_share_a_zone(self):
        chalmun_rooms = self._chalmun_rooms(GCW_TATOOINE_YAML)
        zones = {r.get("zone") for r in chalmun_rooms}
        self.assertEqual(
            len(zones), 1,
            f"GCW Chalmun's Cantina rooms span multiple zones: "
            f"{zones}. All rooms in the cantina complex should share "
            f"one zone."
        )


# ═════════════════════════════════════════════════════════════════════
# 6. Meta — chalmuans_* slug stability (intentional CW typo)
# ═════════════════════════════════════════════════════════════════════


class TestChalmuansSlugStability(unittest.TestCase):
    """The CW Chalmun's Cantina slugs are spelled 'chalmuans_*' (typo
    of 'chalmuns'). Per AreaGeometry's slug-stability rule, the slug
    is the stable identity contract and must not be silently
    'corrected' — multiple consumers reference the typoed form
    (housing_lots.yaml, mos_eisley.yaml map, four test files).

    Renaming the slug to 'chalmuns_*' requires a coordinated drop
    that updates all consumers in the same commit. This test locks
    the current spelling so a future Claude session doesn't
    accidentally break the consumer chain by 'fixing' the typo.
    """

    def test_cw_chalmun_slugs_are_chalmuans_typo(self):
        """Lock the typoed CW spelling — `chalmuans_*` (the legacy
        typo) is the stable slug. If a future drop renames it to
        `chalmuns_*`, it must also update housing_lots.yaml,
        mos_eisley.yaml, and the four test files that reference the
        typo."""
        data = _read_yaml(CW_TATOOINE_YAML)
        rooms = data.get("rooms") or []
        chalmun_rooms = [
            r for r in rooms
            if "Chalmun" in (r.get("name") or "")
        ]
        for r in chalmun_rooms:
            slug = r.get("slug") or ""
            # Confirm the CW typo spelling.
            self.assertTrue(
                slug.startswith("chalmuans_"),
                f"CW Chalmun's room slug {slug!r} no longer matches "
                f"the locked-typo spelling 'chalmuans_*'. If this is "
                f"a deliberate rename, also update: "
                f"data/worlds/clone_wars/housing_lots.yaml (2 refs), "
                f"data/worlds/clone_wars/maps/mos_eisley.yaml (1 ref), "
                f"tests/test_fmap2_session_hud.py, "
                f"tests/test_fmap2_area_geometry_registry.py, "
                f"tests/test_fmap6_session_contacts.py (2 refs)."
            )


if __name__ == "__main__":
    unittest.main()
