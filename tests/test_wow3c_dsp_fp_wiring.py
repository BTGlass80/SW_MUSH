# -*- coding: utf-8 -*-
"""
tests/test_wow3c_dsp_fp_wiring.py — WoW.3c DSP + FP wiring.

Three runtime wirings, per weight_of_war_design_v1.md §7.1 + §7.2.

1. **DSP-resistance modifier** — the fall-check willpower roll
   in `engine.force_powers._resolve_fall_check` adds a Weight-
   based modifier (+0 / +2 / +5 / +10) to the standard
   ``DSP × 3`` difficulty. The parser site
   `parser/force_commands.py::ForceCommand` reads the Jedi's
   Weight and passes it through as a keyword-only param to
   `resolve_force_power`.

2. **Extra DSP on failed resist** — when a Jedi at Weight ≥ 151
   fails the fall check, they accrue 1 additional DSP on top of
   the baseline +1.

3. **FP-award reduction** — two surfaces apply the
   ``fp_award_after_weight`` multiplier:
   - The Knighting ceremony in
     ``parser/padawan_master_trials.py`` (no-op for the standard
     +1 grant due to minimum-1 floor; pinned for future variants)
   - The ``@weight <name> fp <delta>`` subform of the existing
     ``@weight`` admin command (WoW.4 consolidation, May 24
     2026): staff grants of any positive delta are scaled by
     the recipient's Weight tier. Folded into the existing
     ``@weight`` umbrella rather than a separate ``@fp`` command,
     since both are staff WoW management.

Test sections
=============

Engine substrate (already covered by WoW.1; here we just pin
the call surface):
  1.  TestResolveFallCheckSignature        — kw-only `weight_difficulty_mod`
  2.  TestResolveForcePowerSignature       — kw-only `weight_difficulty_mod`,
                                              `extra_dsp_on_fail`

Fall-check modifier behavior:
  3.  TestFallCheckBaseDifficulty          — mod=0, difficulty = DSP*3
  4.  TestFallCheckWithModifier            — mod=10, difficulty = DSP*3 + 10
  5.  TestFallCheckResistVsFail            — high-roll resists, low-roll falls

Extra DSP on failed resist:
  6.  TestExtraDspOnFailZero               — extra_dsp_on_fail=0 → DSP only +1
  7.  TestExtraDspOnFailOne                — extra_dsp_on_fail=1 + failed → +2 DSP total
  8.  TestExtraDspOnFailButResisted        — extra_dsp_on_fail=1 + resisted → +1 DSP only
  9.  TestExtraDspNarrativeMentionsWeight  — "Weight of War" appears on fail

Parser-side Weight read (force_commands.py):
 10.  TestForceCommandReadsJediWeight      — Jedi PC's Weight is passed to engine
 11.  TestForceCommandNonJediNoMod         — Non-Jedi PC sends weight_mod=0

Knighting FP grant (padawan_master_trials.py):
 12.  TestKnightingFpGrantUsesMultiplier   — function-level coverage that the
                                              call site references fp_award_after_weight
 13.  TestKnightingFpGrantNoOpAtMinimum    — +1 grant for Weight 200 still = +1
                                              (floor)
 14.  TestKnightingFpGrantNoOpForNonJedi   — non-Jedi gets raw grant

@weight FP subform (admin_weight_commands.py, May 24 2026
consolidation: WoW.4 folded the standalone @fp command into
@weight to reduce admin surface):
 15.  TestWeightFpShowSurfacesFp           — show form prints FP value
 16.  TestWeightFpGrantPositiveOnJediLowWt — +2 → +2 (Weight 0, no reduction)
 17.  TestWeightFpGrantPositiveOnJediHighWt — +4 on Weight 200 → +1 (25% floored)
 18.  TestWeightFpGrantPositiveOnNonJedi   — +3 on non-Jedi → +3 (no reduction)
 19.  TestWeightFpGrantNegativeOnJedi      — -1 on Jedi unmodified (punishment, not award)
 20.  TestWeightFpGrantZeroDelta           — refuses with no-op message
 21.  TestWeightFpFloorAtZero              — -99 caps at 0, not negative
 22.  TestWeightFpReasonSurfaced           — 'for <reason>' appears in confirmation
 23.  TestWeightFpScaledNotePresent        — when delta is scaled, requested-vs-effective shown
 24.  TestWeightFpMissingDelta             — `@weight Anakin fp` → friendly error
 25.  TestWeightFpUnknownChar              — `@weight Nobody fp +1` → not-found

Phantom prevention (Pattern 8):
 26.  TestSubstrateImportsStable           — surface symbols importable
 27.  TestNoLeftoverAdminFpModule          — old admin_fp_commands.py is GONE
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ── Real-DB harness ──────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_char(
    db, char_id: int, name: str,
    faction: str = "independent",
    weight: int = 0,
    fp: int = 1,
    chargen_flags: dict | None = None,
) -> dict:
    notes = json.dumps(chargen_flags) if chargen_flags else ""
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (id, username, password_hash) "
        "VALUES (1, 'u', 'p')",
    )
    await db._db.execute(
        "INSERT INTO characters "
        "(id, account_id, name, room_id, faction_id, "
        "force_points, weight_of_war, chargen_notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (char_id, 1, name, 1, faction, fp, weight, notes),
    )
    await db._db.commit()
    return await db.get_character(char_id)


class _FakeSession:
    def __init__(self):
        self.lines: list[str] = []

    async def send_line(self, line):
        self.lines.append(str(line))

    def text_contains(self, needle: str) -> bool:
        return any(needle in line for line in self.lines)


def _make_ctx(args: str, db):
    ctx = MagicMock()
    ctx.args = args
    ctx.db = db
    ctx.session = _FakeSession()
    return ctx


# ═════════════════════════════════════════════════════════════════════
# 1-2. Engine signature pins
# ═════════════════════════════════════════════════════════════════════


class TestResolveFallCheckSignature(unittest.TestCase):
    """The Weight modifier parameter must remain on the
    _resolve_fall_check signature. If a future refactor drops
    it, the parser site silently passes through without effect."""

    def test_param_exists(self):
        import inspect
        from engine.force_powers import _resolve_fall_check
        params = inspect.signature(_resolve_fall_check).parameters
        self.assertIn("weight_difficulty_mod", params)
        # Default must be 0 so legacy callers (and the WoW.1
        # substrate's pure functions) work unmodified.
        self.assertEqual(
            params["weight_difficulty_mod"].default, 0
        )


class TestResolveForcePowerSignature(unittest.TestCase):
    def test_kw_only_params_exist(self):
        import inspect
        from engine.force_powers import resolve_force_power
        params = inspect.signature(resolve_force_power).parameters
        self.assertIn("weight_difficulty_mod", params)
        self.assertIn("extra_dsp_on_fail", params)
        # Both must be keyword-only so positional callers don't
        # accidentally drift into the WoW params.
        for name in ("weight_difficulty_mod", "extra_dsp_on_fail"):
            self.assertEqual(
                params[name].kind,
                inspect.Parameter.KEYWORD_ONLY,
            )
            self.assertEqual(params[name].default, 0)


# ═════════════════════════════════════════════════════════════════════
# 3-5. Fall-check difficulty math
# ═════════════════════════════════════════════════════════════════════


def _build_test_char(dsp: int = 6, weight: int = 0):
    """Build a Character object with controllable DSP and an
    auto-passing willpower roll for deterministic resist/fail
    testing via patching."""
    from engine.character import Character
    c = Character()
    c.id = 1
    c.name = "Anakin"
    c.dark_side_points = dsp
    return c


class TestFallCheckBaseDifficulty(unittest.TestCase):
    def test_base_dsp_times_three(self):
        from engine.force_powers import _resolve_fall_check
        from engine.character import SkillRegistry
        c = _build_test_char(dsp=6)
        # Patch the dice roll to return a known value
        with patch("engine.force_powers.roll_d6_pool") as mock_roll:
            mock_roll.return_value = MagicMock(total=20)
            # Difficulty = 6*3 = 18; roll=20 → resist
            sr = SkillRegistry()
            result = _resolve_fall_check(c, sr, 0)
        self.assertTrue(result, "Roll 20 vs diff 18 → resist")


class TestFallCheckWithModifier(unittest.TestCase):
    def test_modifier_added_to_difficulty(self):
        from engine.force_powers import _resolve_fall_check
        from engine.character import SkillRegistry
        c = _build_test_char(dsp=6)
        with patch("engine.force_powers.roll_d6_pool") as mock_roll:
            mock_roll.return_value = MagicMock(total=20)
            # Base diff = 18, modifier = +10, total = 28
            # roll=20 → FAIL
            sr = SkillRegistry()
            result = _resolve_fall_check(c, sr, 10)
        self.assertFalse(
            result, "Roll 20 vs diff 28 → fall")


class TestFallCheckResistVsFail(unittest.TestCase):
    def test_threshold_boundary(self):
        from engine.force_powers import _resolve_fall_check
        from engine.character import SkillRegistry
        c = _build_test_char(dsp=6)
        with patch("engine.force_powers.roll_d6_pool") as mock_roll:
            # Diff = 18, roll = 18 → exactly meets, resist
            mock_roll.return_value = MagicMock(total=18)
            sr = SkillRegistry()
            r1 = _resolve_fall_check(c, sr, 0)
            # Diff = 18, roll = 17 → fall
            mock_roll.return_value = MagicMock(total=17)
            r2 = _resolve_fall_check(c, sr, 0)
        self.assertTrue(r1, "Meets = resist")
        self.assertFalse(r2, "Misses = fall")


# ═════════════════════════════════════════════════════════════════════
# 6-9. Extra DSP on failed resist
# ═════════════════════════════════════════════════════════════════════


class TestExtraDspOnFailZero(unittest.TestCase):
    """When extra_dsp_on_fail=0 (Weight < 151), failed resist
    grants only the baseline +1 DSP from the dark-power use,
    not an additional one."""

    def test_no_extra_dsp_at_low_weight(self):
        from engine.force_powers import resolve_force_power
        from engine.character import Character, SkillRegistry
        c = Character()
        c.id = 1; c.name = "Anakin"
        c.dark_side_points = 5  # one below threshold
        # Boost a dark-side skill so the power resolves
        from engine.dice import DicePool
        c.set_attribute("alter", DicePool(4, 0))

        # Build a target with low STR so injure_kill bites
        target = Character()
        target.id = 2; target.name = "Target"
        target.set_attribute("strength", DicePool(1, 0))

        roll_calls = [0]

        def roll_side_effect(*a, **k):
            roll_calls[0] += 1
            n = roll_calls[0]
            if n == 1:
                return MagicMock(total=20)  # power roll
            if n == 2:
                return MagicMock(total=1)   # target resist
            if n == 3:
                return MagicMock(total=1)   # fall check fails
            return MagicMock(total=1)       # any subsequent

        with patch(
            "engine.force_powers.roll_d6_pool",
            side_effect=roll_side_effect,
        ):
            sr = SkillRegistry()
            result = resolve_force_power(
                "injure_kill", c, sr,
                target_char=target,
                weight_difficulty_mod=0,
                extra_dsp_on_fail=0,
            )
        # Started at DSP=5, +1 baseline = 6 (no extra)
        self.assertEqual(c.dark_side_points, 6)
        self.assertEqual(result.dsp_gained, 1)


class TestExtraDspOnFailOne(unittest.TestCase):
    def test_extra_dsp_applied_on_fail(self):
        from engine.force_powers import resolve_force_power
        from engine.character import Character, SkillRegistry
        from engine.dice import DicePool
        c = Character()
        c.id = 1; c.name = "Anakin"
        c.dark_side_points = 5
        c.set_attribute("alter", DicePool(4, 0))
        target = Character()
        target.id = 2; target.name = "Target"
        target.set_attribute("strength", DicePool(1, 0))

        roll_calls = [0]

        def roll_side_effect(*a, **k):
            roll_calls[0] += 1
            n = roll_calls[0]
            if n == 1:
                return MagicMock(total=20)
            if n == 2:
                return MagicMock(total=1)
            if n == 3:
                return MagicMock(total=1)  # fall check fails
            return MagicMock(total=1)

        with patch(
            "engine.force_powers.roll_d6_pool",
            side_effect=roll_side_effect,
        ):
            sr = SkillRegistry()
            result = resolve_force_power(
                "injure_kill", c, sr, target_char=target,
                weight_difficulty_mod=10,
                extra_dsp_on_fail=1,
            )
        # 5 + 1 baseline + 1 extra = 7
        self.assertEqual(c.dark_side_points, 7)
        self.assertEqual(result.dsp_gained, 2)


class TestExtraDspOnFailButResisted(unittest.TestCase):
    def test_no_extra_dsp_when_resisted(self):
        from engine.force_powers import resolve_force_power
        from engine.character import Character, SkillRegistry
        from engine.dice import DicePool
        c = Character()
        c.id = 1; c.name = "Anakin"
        c.dark_side_points = 5
        c.set_attribute("alter", DicePool(4, 0))
        c.set_attribute("knowledge", DicePool(5, 0))
        target = Character()
        target.id = 2; target.name = "Target"
        target.set_attribute("strength", DicePool(1, 0))

        roll_calls = [0]

        def roll_side_effect(*a, **k):
            roll_calls[0] += 1
            n = roll_calls[0]
            if n == 1:
                return MagicMock(total=20)
            if n == 2:
                return MagicMock(total=1)
            if n == 3:
                return MagicMock(total=99)  # fall check passes
            return MagicMock(total=1)

        with patch(
            "engine.force_powers.roll_d6_pool",
            side_effect=roll_side_effect,
        ):
            sr = SkillRegistry()
            result = resolve_force_power(
                "injure_kill", c, sr, target_char=target,
                weight_difficulty_mod=10,
                extra_dsp_on_fail=1,
            )
        # 5 + 1 baseline (no extra since resisted) = 6
        self.assertEqual(c.dark_side_points, 6)
        self.assertEqual(result.dsp_gained, 1)


class TestExtraDspNarrativeMentionsWeight(unittest.TestCase):
    def test_narrative_includes_weight_explanation(self):
        from engine.force_powers import resolve_force_power
        from engine.character import Character, SkillRegistry
        from engine.dice import DicePool
        c = Character()
        c.id = 1; c.name = "Anakin"
        c.dark_side_points = 5
        c.set_attribute("alter", DicePool(4, 0))
        target = Character()
        target.id = 2; target.name = "Target"
        target.set_attribute("strength", DicePool(1, 0))

        roll_calls = [0]

        def roll_side_effect(*a, **k):
            roll_calls[0] += 1
            n = roll_calls[0]
            if n == 1:
                return MagicMock(total=20)
            if n == 2:
                return MagicMock(total=1)
            if n == 3:
                return MagicMock(total=1)
            return MagicMock(total=1)

        with patch(
            "engine.force_powers.roll_d6_pool",
            side_effect=roll_side_effect,
        ):
            sr = SkillRegistry()
            result = resolve_force_power(
                "injure_kill", c, sr, target_char=target,
                weight_difficulty_mod=10,
                extra_dsp_on_fail=1,
            )
        self.assertIn(
            "Weight of War", result.narrative,
            "Failed-resist-with-extra-DSP narrative must "
            "mention Weight of War so the player understands "
            "why the DSP penalty is larger than usual",
        )


# ═════════════════════════════════════════════════════════════════════
# 10-11. Parser-side weight read
# ═════════════════════════════════════════════════════════════════════


class TestForceCommandReadsJediWeight(unittest.TestCase):
    """The parser site must read the Jedi's Weight from the
    char_dict and pass it through to resolve_force_power. We
    don't need to drive the full force command end-to-end —
    just confirm the call signature.

    This is a static test: grep the source for the resolve_force_
    power call and confirm it passes weight_difficulty_mod and
    extra_dsp_on_fail."""

    def test_call_site_has_weight_params(self):
        with open(
            os.path.join(
                PROJECT_ROOT, "parser", "force_commands.py"
            ),
            encoding="utf-8",
        ) as f:
            src = f.read()
        # The call must include both keyword params
        self.assertIn("weight_difficulty_mod=", src,
                      "force_commands.py must pass "
                      "weight_difficulty_mod to "
                      "resolve_force_power")
        self.assertIn("extra_dsp_on_fail=", src,
                      "force_commands.py must pass "
                      "extra_dsp_on_fail to resolve_force_power")
        # And must use the WoW substrate functions
        self.assertIn("dsp_resistance_modifier", src)
        self.assertIn("extra_dsp_on_failed_resist", src)


class TestForceCommandNonJediNoMod(unittest.TestCase):
    """For a non-Jedi PC, is_jedi_pc returns False and the
    weight_mod stays 0. Read this directly from the source —
    the conditional is `if is_jedi_pc(char_dict):`."""

    def test_non_jedi_path_gates_on_is_jedi_pc(self):
        with open(
            os.path.join(
                PROJECT_ROOT, "parser", "force_commands.py"
            ),
            encoding="utf-8",
        ) as f:
            src = f.read()
        # Confirm the is_jedi_pc gate is present in the WoW.3c
        # block
        self.assertIn("is_jedi_pc(char_dict)", src)


# ═════════════════════════════════════════════════════════════════════
# 12-14. Knighting FP grant
# ═════════════════════════════════════════════════════════════════════


class TestKnightingFpGrantUsesMultiplier(unittest.TestCase):
    """The Knighting call site must reference
    ``fp_award_after_weight``. The +1 grant is a no-op at every
    Weight tier (substrate floor), but the contract must be
    pinned for future multi-FP variants."""

    def test_knighting_calls_fp_award_helper(self):
        with open(
            os.path.join(
                PROJECT_ROOT, "parser",
                "padawan_master_trials.py",
            ),
            encoding="utf-8",
        ) as f:
            src = f.read()
        self.assertIn("fp_award_after_weight", src)


class TestKnightingFpGrantNoOpAtMinimum(unittest.TestCase):
    """fp_award_after_weight(1, weight) returns 1 at every
    tier due to the minimum-1 floor for positive base."""

    def test_min_one_floor_universal(self):
        from engine.weight_of_war import fp_award_after_weight
        for w in (0, 50, 51, 100, 101, 150, 151, 200):
            self.assertEqual(
                fp_award_after_weight(1, w), 1,
                f"+1 grant at Weight {w} must yield +1 "
                "(minimum-1 floor)",
            )


class TestKnightingFpGrantNoOpForNonJedi(unittest.TestCase):
    """Non-Jedi can't be Knighted via the bond surface (the
    code path gates earlier), but if any non-bond grant path
    fires, the is_jedi_pc check skips the WoW reduction. The
    test reads the source for the gate."""

    def test_is_jedi_pc_gate_present(self):
        with open(
            os.path.join(
                PROJECT_ROOT, "parser",
                "padawan_master_trials.py",
            ),
            encoding="utf-8",
        ) as f:
            src = f.read()
        # The WoW.3c block uses is_jedi_pc to gate
        self.assertIn("is_jedi_pc(padawan)", src)


# ═════════════════════════════════════════════════════════════════════
# 15-25. @weight FP subform (WoW.4 consolidation, May 24 2026)
#
# The standalone @fp admin command was retired and folded into the
# existing @weight umbrella as a `fp <delta>` subform. The same §7.2
# multiplier rules apply; the entry point is now @weight, mirroring
# the existing @weight set / history pattern.
# ═════════════════════════════════════════════════════════════════════


class TestWeightFpShowSurfacesFp(unittest.TestCase):
    """The @weight <name> show form now surfaces Force Points
    alongside Weight + tier (the consolidation merged the @fp
    show form into @weight's existing show form)."""

    def test_show_includes_fp(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order",
                weight=60, fp=3,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin", db)
            await AdminWeightCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("Force Points", joined)
        self.assertIn("3", joined)


class TestWeightFpGrantPositiveOnJediLowWt(unittest.TestCase):
    def test_low_weight_grant_unmodified(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order",
                weight=20, fp=2,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin fp +2 for rescue", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row, ctx.session.lines

        row, lines = _run(go())
        self.assertEqual(int(row["force_points"]), 4)
        joined = "\n".join(lines)
        self.assertNotIn("scaled", joined.lower())


class TestWeightFpGrantPositiveOnJediHighWt(unittest.TestCase):
    def test_high_weight_grant_scaled_to_one(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order",
                weight=200, fp=2,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin fp +4 for valor", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row, ctx.session.lines

        row, lines = _run(go())
        # 4 * 0.25 = 1 (int) → minimum-1 floor → 1
        self.assertEqual(int(row["force_points"]), 3)
        joined = "\n".join(lines)
        self.assertIn("scaled", joined.lower())


class TestWeightFpGrantPositiveOnNonJedi(unittest.TestCase):
    def test_non_jedi_unmodified(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Greedo", "bh_guild",
                weight=200, fp=1,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Greedo fp +3 for greed", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row, ctx.session.lines

        row, lines = _run(go())
        self.assertEqual(int(row["force_points"]), 4)
        joined = "\n".join(lines)
        self.assertNotIn("scaled", joined.lower())


class TestWeightFpGrantNegativeOnJedi(unittest.TestCase):
    """Negative deltas are not affected by the §7.2 multiplier.
    The reduction is about awards, not punishment."""

    def test_negative_delta_unmodified(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order",
                weight=200, fp=5,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin fp -2 for selfish use", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row, ctx.session.lines

        row, lines = _run(go())
        self.assertEqual(int(row["force_points"]), 3)
        joined = "\n".join(lines)
        self.assertNotIn("scaled", joined.lower())


class TestWeightFpGrantZeroDelta(unittest.TestCase):
    def test_zero_delta_is_no_op(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order", fp=3,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin fp +0", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row, ctx.session.lines

        row, lines = _run(go())
        self.assertEqual(int(row["force_points"]), 3)
        joined = "\n".join(lines)
        self.assertIn("no-op", joined.lower())


class TestWeightFpFloorAtZero(unittest.TestCase):
    def test_large_negative_floors_at_zero(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order", fp=2,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin fp -99 for testing", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row

        row = _run(go())
        self.assertEqual(int(row["force_points"]), 0)


class TestWeightFpReasonSurfaced(unittest.TestCase):
    def test_reason_in_confirmation(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order", fp=1,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx(
                "Anakin fp +1 for heroic rescue", db,
            )
            await AdminWeightCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        self.assertTrue(
            any("heroic rescue" in line for line in lines)
        )


class TestWeightFpScaledNotePresent(unittest.TestCase):
    def test_scaled_note_when_reduction_applies(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order",
                weight=120, fp=1,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            # +4 at Weight 120 (strained tier, 50%) = +2
            ctx = _make_ctx("Anakin fp +4 for valor", db)
            await AdminWeightCommand().execute(ctx)
            row = await db.get_character(100)
            return row, ctx.session.lines

        row, lines = _run(go())
        # 1 + 2 = 3
        self.assertEqual(int(row["force_points"]), 3)
        joined = "\n".join(lines)
        # Confirms requested vs effective shown
        self.assertIn("+4", joined)
        self.assertIn("+2", joined)


class TestWeightFpMissingDelta(unittest.TestCase):
    """`@weight Anakin fp` without a delta → friendly error,
    not a stack trace."""

    def test_missing_delta_error(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 100, "Anakin", "jedi_order", fp=1,
            )
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Anakin fp", db)
            await AdminWeightCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("Missing delta", joined)


class TestWeightFpUnknownChar(unittest.TestCase):
    def test_unknown_char_not_found(self):
        async def go():
            db = await _fresh_db()
            from parser.admin_weight_commands import AdminWeightCommand
            ctx = _make_ctx("Nobody fp +1", db)
            await AdminWeightCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("No character named", joined)


# ═════════════════════════════════════════════════════════════════════
# 26-27. Phantom prevention
# ═════════════════════════════════════════════════════════════════════


class TestSubstrateImportsStable(unittest.TestCase):
    """Pattern 8: every documented surface must be importable.
    The WoW.3c wiring depends on three substrate functions; if
    any disappears, the parser sites silently fall through."""

    def test_substrate_symbols(self):
        from engine.weight_of_war import (
            dsp_resistance_modifier,
            extra_dsp_on_failed_resist,
            fp_award_after_weight,
            is_jedi_pc,
            get_weight,
        )
        for fn in (dsp_resistance_modifier,
                   extra_dsp_on_failed_resist,
                   fp_award_after_weight,
                   is_jedi_pc,
                   get_weight):
            self.assertTrue(callable(fn))


class TestNoLeftoverAdminFpModule(unittest.TestCase):
    """The standalone @fp command was retired. A leftover
    `parser/admin_fp_commands.py` would mean the consolidation
    is incomplete (Pattern 1 risk — duplicate surface).
    Confirm the old module is gone."""

    def test_admin_fp_module_removed(self):
        path = os.path.join(
            PROJECT_ROOT, "parser", "admin_fp_commands.py",
        )
        self.assertFalse(
            os.path.exists(path),
            "parser/admin_fp_commands.py should have been "
            "removed as part of the WoW.4 consolidation; @fp "
            "was folded into @weight as the `fp` subform.",
        )
        # And it should NOT be imported in game_server.py
        with open(
            os.path.join(PROJECT_ROOT, "server", "game_server.py"),
            encoding="utf-8",
        ) as f:
            src = f.read()
        self.assertNotIn(
            "register_admin_fp_commands", src,
            "game_server.py still references "
            "register_admin_fp_commands — orphan import after "
            "consolidation",
        )
        self.assertNotIn(
            "admin_fp_commands", src,
            "game_server.py still references the deleted "
            "admin_fp_commands module",
        )


if __name__ == "__main__":
    unittest.main()
