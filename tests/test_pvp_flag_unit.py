# -*- coding: utf-8 -*-
"""
tests/test_pvp_flag_unit.py — Unit tests for the +pvp opt-in flag.

Background
==========

The userMemory note "+pvp on/off opt-in flag (WoW-Outland-style)"
became this drop. Schema v27 adds a ``pvp_flagged`` column to the
characters table. ``parser/combat_commands.py::_check_pvp_consent``
gets a new branch: if either party is flagged AND the zone is
CONTESTED, the attack proceeds without challenge/accept. SECURED
zones remain absolute (the early-return at L1243-1244 fires before
any flag check, so the flag does NOT override SECURED).

A new ``PvpCommand`` parser command (``+pvp on``/``+pvp off``/
``+pvp status``) provides the player surface. An unflag cooldown
(``CD_PVP_UNFLAG`` / ``PVP_UNFLAG_COOLDOWN_S = 300``) prevents
tag-and-flee griefing — once a flagged character engages in a
combat, they cannot unflag for 5 minutes.

This file holds the fast unit-level guards. End-to-end smoke
scenarios live in ``tests/smoke/scenarios/pvp_flag.py``.

Test sections
=============

  1. ``TestSchemaV27Migration`` — SCHEMA_VERSION = 27, MIGRATIONS[27]
     ALTERs the characters table with pvp_flagged.
  2. ``TestWritableColumnsAllowsPvpFlagged`` — save_character can
     write pvp_flagged.
  3. ``TestCooldownConstants`` — CD_PVP_UNFLAG, PVP_UNFLAG_COOLDOWN_S
     are exported and have sensible values.
  4. ``TestPvpConsentGateSignature`` — the byte-level shape of the
     flag-branch in _check_pvp_consent: reads pvp_flagged from both
     parties, calls set_cooldown on engagement, gated only on
     CONTESTED zones.
  5. ``TestPvpCommandRegistered`` — PvpCommand is in the registry
     list with the +pvp key.
  6. ``TestPvpCommandHelp`` — help text documents the three
     subcommands and the SECURED-zones-protected invariant.
  7. ``TestSecuredZoneInvariant`` — the early-return in
     _check_pvp_consent fires BEFORE any flag check, so SECURED
     zones cannot be overridden by flagging.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


DATABASE_PY = PROJECT_ROOT / "db" / "database.py"
COMBAT_PY = PROJECT_ROOT / "parser" / "combat_commands.py"
COOLDOWNS_PY = PROJECT_ROOT / "engine" / "cooldowns.py"


# ═════════════════════════════════════════════════════════════════════
# 1. Schema v27 migration
# ═════════════════════════════════════════════════════════════════════


class TestSchemaV27Migration(unittest.TestCase):
    """The pvp_flagged column ships as schema v27."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(DATABASE_PY)

    def test_schema_version_bumped_to_27(self):
        m = re.search(r'^\s*SCHEMA_VERSION\s*=\s*(\d+)',
                      self.src, re.MULTILINE)
        self.assertIsNotNone(
            m, "SCHEMA_VERSION declaration missing from db/database.py."
        )
        # Original assertion was `== 27` with a note to rewrite when
        # bumping past 27. P-M.1 (May 19 2026) bumped to 28; the
        # invariant this test cares about is "the pvp_flagged column
        # migration shipped at version 27 or later" — which is
        # preserved by SCHEMA_VERSION >= 27. The migration 27 entry
        # is then independently asserted in test_migration_27_present
        # below.
        self.assertGreaterEqual(
            int(m.group(1)), 27,
            "SCHEMA_VERSION should be at least 27 (the pvp_flagged "
            "migration version). It can be higher if later migrations "
            "have shipped."
        )

    def test_migration_27_present(self):
        """MIGRATIONS dict has an entry for version 27 that adds the
        pvp_flagged column."""
        # We slice the MIGRATIONS dict literal. Looking for a `27: [`
        # entry that contains an ALTER for pvp_flagged.
        m = re.search(
            r'27:\s*\[\s*(.+?)\s*\],',
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "MIGRATIONS[27] entry missing from db/database.py."
        )
        block = m.group(1)
        self.assertIn(
            "ALTER TABLE characters", block,
            "MIGRATIONS[27] should ALTER the characters table."
        )
        self.assertIn(
            "pvp_flagged", block,
            "MIGRATIONS[27] should add the pvp_flagged column."
        )
        # Default 0 — existing characters keep pre-drop behavior.
        self.assertIn(
            "DEFAULT 0", block,
            "pvp_flagged column should DEFAULT 0 — existing "
            "characters keep the pre-drop challenge/accept flow."
        )


# ═════════════════════════════════════════════════════════════════════
# 2. Writable columns
# ═════════════════════════════════════════════════════════════════════


class TestWritableColumnsAllowsPvpFlagged(unittest.TestCase):
    """save_character must accept pvp_flagged as a writable column;
    otherwise PvpCommand will hit
    'unknown/disallowed columns' at runtime."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(DATABASE_PY)

    def test_pvp_flagged_in_writable_set(self):
        # The set is a frozenset literal; we just check membership at
        # the source level. The byte-level shape is `"pvp_flagged"`
        # appearing inside the _CHARACTER_WRITABLE_COLUMNS literal.
        # We scope the search to a window after the literal opens to
        # avoid false positives from other matches.
        idx = self.src.find("_CHARACTER_WRITABLE_COLUMNS = frozenset({")
        self.assertNotEqual(
            idx, -1,
            "_CHARACTER_WRITABLE_COLUMNS frozenset declaration not "
            "found in db/database.py."
        )
        # The frozenset literal is ~2000 chars long; bound the window.
        window = self.src[idx:idx + 4000]
        self.assertIn(
            '"pvp_flagged"', window,
            "pvp_flagged not in _CHARACTER_WRITABLE_COLUMNS. "
            "save_character will reject the write. Add "
            "'pvp_flagged' to the frozenset literal."
        )


# ═════════════════════════════════════════════════════════════════════
# 3. Cooldown constants
# ═════════════════════════════════════════════════════════════════════


class TestCooldownConstants(unittest.TestCase):
    """engine/cooldowns.py exports CD_PVP_UNFLAG + PVP_UNFLAG_COOLDOWN_S."""

    def test_cd_pvp_unflag_constant(self):
        from engine.cooldowns import CD_PVP_UNFLAG
        self.assertEqual(
            CD_PVP_UNFLAG, "pvp_unflag",
            "CD_PVP_UNFLAG should be the string 'pvp_unflag'. "
            "PvpCommand and _check_pvp_consent both reference this "
            "key — drift would silently break the cooldown."
        )

    def test_pvp_unflag_cooldown_duration(self):
        from engine.cooldowns import PVP_UNFLAG_COOLDOWN_S
        self.assertIsInstance(
            PVP_UNFLAG_COOLDOWN_S, int,
            "PVP_UNFLAG_COOLDOWN_S should be an int seconds value."
        )
        self.assertGreater(
            PVP_UNFLAG_COOLDOWN_S, 0,
            "PVP_UNFLAG_COOLDOWN_S must be positive (a zero or "
            "negative cooldown disables anti-tag-and-flee)."
        )
        # 5 minutes is the documented design value. We tolerate a
        # later tweak to 240 or 360 without breaking this test —
        # the assertion is "in the right order of magnitude."
        self.assertGreaterEqual(
            PVP_UNFLAG_COOLDOWN_S, 60,
            "PVP_UNFLAG_COOLDOWN_S is unusually short "
            f"({PVP_UNFLAG_COOLDOWN_S}s). Anti-tag-and-flee needs "
            "at least a minute to actually deter the abuse pattern."
        )
        self.assertLessEqual(
            PVP_UNFLAG_COOLDOWN_S, 3600,
            "PVP_UNFLAG_COOLDOWN_S is unusually long "
            f"({PVP_UNFLAG_COOLDOWN_S}s). A cooldown over an hour "
            "punishes players who unflagged legitimately."
        )


# ═════════════════════════════════════════════════════════════════════
# 4. _check_pvp_consent flag-branch signature
# ═════════════════════════════════════════════════════════════════════


class TestPvpConsentGateSignature(unittest.TestCase):
    """Byte-level signature of the flag-branch in _check_pvp_consent.

    Behavioral correctness is locked by the live-harness scenarios in
    tests/smoke/scenarios/pvp_flag.py. This test catches refactor
    drift that would silently remove the branch without breaking the
    smoke (the smoke uses real DB state; a regression that bypasses
    the flag check might still let the attack through via a different
    code path).
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(COMBAT_PY)

    def _consent_body(self) -> str:
        """Return the source of _check_pvp_consent.

        Sliced from `async def _check_pvp_consent` to the next method
        boundary (`async def _check_bh_override`).
        """
        start = self.src.find("async def _check_pvp_consent(")
        self.assertNotEqual(
            start, -1,
            "_check_pvp_consent not found in parser/combat_commands.py."
        )
        end = self.src.find("async def _check_bh_override(", start)
        self.assertNotEqual(end, -1)
        return self.src[start:end]

    def test_reads_attacker_and_target_pvp_flagged(self):
        body = self._consent_body()
        self.assertIn(
            'char.get("pvp_flagged")', body,
            "_check_pvp_consent should read attacker's pvp_flagged "
            "via char.get(...) (defensive against missing column "
            "in older fixtures)."
        )
        self.assertIn(
            'target_char.get("pvp_flagged")', body,
            "_check_pvp_consent should read target's pvp_flagged "
            "via target_char.get(...)."
        )

    def test_either_party_flagged_unlocks(self):
        """Mutual-or-unilateral interpretation: EITHER party flagged
        unlocks. The byte-level signature is `flagged or flagged`."""
        body = self._consent_body()
        # We want to see an `or` between attacker_flagged and
        # target_flagged (in some order). The check is loose enough
        # to allow rewording.
        self.assertRegex(
            body,
            r'attacker_flagged\s+or\s+target_flagged'
            r'|target_flagged\s+or\s+attacker_flagged',
            "_check_pvp_consent should unlock if EITHER party is "
            "flagged (not require both). Pattern: "
            "`attacker_flagged or target_flagged`."
        )

    def test_sets_cooldown_on_flag_use(self):
        body = self._consent_body()
        self.assertIn(
            "set_cooldown", body,
            "_check_pvp_consent flag-branch should call set_cooldown "
            "to apply the anti-tag-and-flee unflag cooldown to both "
            "parties."
        )
        self.assertIn(
            "CD_PVP_UNFLAG", body,
            "_check_pvp_consent flag-branch should reference "
            "CD_PVP_UNFLAG for the cooldown key."
        )
        self.assertIn(
            "PVP_UNFLAG_COOLDOWN_S", body,
            "_check_pvp_consent flag-branch should reference "
            "PVP_UNFLAG_COOLDOWN_S for the cooldown duration."
        )


# ═════════════════════════════════════════════════════════════════════
# 5. PvpCommand registered
# ═════════════════════════════════════════════════════════════════════


class TestPvpCommandRegistered(unittest.TestCase):
    """register_combat_commands includes PvpCommand."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(COMBAT_PY)

    def test_pvp_command_class_exists(self):
        self.assertIn(
            "class PvpCommand(BaseCommand):",
            self.src,
            "PvpCommand class missing from parser/combat_commands.py. "
            "Without it, `+pvp` will fall through to no-such-command."
        )

    def test_pvp_command_key(self):
        # Find the class block and verify the key declaration. The
        # window has to be generous because PvpCommand has a long
        # docstring before the `key = ` line.
        lines = self.src.splitlines()
        idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class PvpCommand(BaseCommand):":
                idx = i
                break
        self.assertIsNotNone(idx)
        window = "\n".join(lines[idx:idx + 60])
        self.assertIn(
            'key = "+pvp"', window,
            "PvpCommand.key should be '+pvp'. Window did not "
            "contain the key declaration."
        )

    def test_pvp_command_in_register_list(self):
        """register_combat_commands should include PvpCommand()."""
        # Slice the register_combat_commands function body.
        m = re.search(
            r'def register_combat_commands\(registry\):.*?'
            r'for cmd in cmds:',
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "register_combat_commands not found or shape changed."
        )
        body = m.group(0)
        self.assertIn(
            "PvpCommand()", body,
            "PvpCommand not in register_combat_commands. The +pvp "
            "command would not be registered at boot."
        )


# ═════════════════════════════════════════════════════════════════════
# 6. PvpCommand help text
# ═════════════════════════════════════════════════════════════════════


class TestPvpCommandHelp(unittest.TestCase):
    """+pvp help text must document the three subcommands and the
    SECURED-zones-protected invariant. Players reading `help +pvp`
    should not be surprised by either."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(COMBAT_PY)
        # Slice the PvpCommand help_text block.
        lines = cls.src.splitlines()
        idx = None
        for i, line in enumerate(lines):
            if line.strip() == "class PvpCommand(BaseCommand):":
                idx = i
                break
        assert idx is not None, "PvpCommand not found"
        # Take a 60-line window — generous, but PvpCommand's
        # help_text is multi-line.
        cls.window = "\n".join(lines[idx:idx + 60]).lower()

    def test_help_documents_on_subcommand(self):
        self.assertIn("+pvp on", self.window,
                      "help text should document `+pvp on`.")

    def test_help_documents_off_subcommand(self):
        self.assertIn("+pvp off", self.window,
                      "help text should document `+pvp off`.")

    def test_help_documents_status_subcommand(self):
        self.assertIn("+pvp status", self.window,
                      "help text should document `+pvp status`.")

    def test_help_mentions_secured_zones_protected(self):
        """The flag does NOT override SECURED zones. Players reading
        `help +pvp` should learn this directly."""
        self.assertIn(
            "secured", self.window,
            "help text should mention that SECURED zones remain "
            "protected — otherwise players will be surprised when "
            "their flag doesn't unlock PvP in the Jedi Temple."
        )

    def test_help_mentions_unflag_cooldown(self):
        self.assertIn(
            "cooldown", self.window,
            "help text should mention the unflag cooldown — "
            "otherwise the 5-minute lockout will surprise players "
            "trying to unflag after a fight."
        )


# ═════════════════════════════════════════════════════════════════════
# 7. SECURED zone invariant — early-return fires BEFORE flag check
# ═════════════════════════════════════════════════════════════════════


class TestSecuredZoneInvariant(unittest.TestCase):
    """The flag-branch is below the `sec != SecurityLevel.CONTESTED`
    early-return. SECURED (and LAWLESS) zones return before any flag
    check. This test locks the ordering so a refactor that
    accidentally moves the flag check above the early-return doesn't
    silently break the SECURED-zones-are-absolute invariant.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(COMBAT_PY)

    def test_early_return_before_flag_check(self):
        # Locate both line numbers and assert the early-return is
        # ABOVE the flag check.
        start = self.src.find("async def _check_pvp_consent(")
        self.assertNotEqual(start, -1)
        end = self.src.find("async def _check_bh_override(", start)
        self.assertNotEqual(end, -1)
        body = self.src[start:end]

        early_return_idx = body.find("if sec != SecurityLevel.CONTESTED")
        flag_check_idx = body.find('char.get("pvp_flagged")')
        self.assertNotEqual(
            early_return_idx, -1,
            "_check_pvp_consent has lost its 'sec != CONTESTED' "
            "early-return. Without it, the flag could override "
            "SECURED zones — a launch-blocking break of the "
            "SECURED-is-absolute invariant."
        )
        self.assertNotEqual(
            flag_check_idx, -1,
            "_check_pvp_consent has lost its pvp_flagged check."
        )
        self.assertLess(
            early_return_idx, flag_check_idx,
            "The 'sec != CONTESTED' early-return must appear "
            "BEFORE the pvp_flagged check. If the flag check is "
            "above the early-return, flagged characters can attack "
            "each other in SECURED zones — violates the design "
            "invariant 'SECURED zones remain absolute'."
        )


if __name__ == "__main__":
    unittest.main()
