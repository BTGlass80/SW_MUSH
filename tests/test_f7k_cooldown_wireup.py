# -*- coding: utf-8 -*-
"""
tests/test_f7k_cooldown_wireup.py — F.7.k cooldown wire-up tests.

F.7.k (May 4 2026) wires the previously-isolated cooldown helpers in
engine.jedi_gating into the village-quest engine. This file tests:

  1. Env var parsing               — `_parse_env_override`
  2. Era YAML policy reading       — `_read_era_policy_flag`
  3. `cooldowns_enabled()`         — resolution order (env > yaml > default)
  4. `act_2_gate_passed`           — bypass preserves structural guard
  5. `trial_gate_passed`           — bypass short-circuits to True
  6. `courage_retry_gate_passed`   — bypass short-circuits to True
  7. `stamp_trial_attempt`         — writes column + save_kwargs
  8. `enter_trials` integration    — gate blocks transition under cooldown
  9. Source markers                — F.7.k tag in module + era.yaml

The strict math (act_2_unlock_ready, trial_cooldown_ready,
courage_retry_cooldown_ready) is unchanged and tested by
test_pg3b_gates.py; this file exercises only the new bypass + gate
predicates and the wire-up.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────
# Test helpers
# ──────────────────────────────────────────────────────────────────────

class _CleanEnvBase(unittest.TestCase):
    """Base that always runs with the cooldown env var unset.

    Tests that want to set the env var should use a `patch.dict`
    context manager. tearDown is defensive — ensures no test
    leaks state into the next.
    """

    ENV_VAR = "SW_MUSH_PROGRESSION_COOLDOWNS"

    def setUp(self):
        self._saved = os.environ.pop(self.ENV_VAR, None)

    def tearDown(self):
        os.environ.pop(self.ENV_VAR, None)
        if self._saved is not None:
            os.environ[self.ENV_VAR] = self._saved


# ──────────────────────────────────────────────────────────────────────
# 1. Env var parsing
# ──────────────────────────────────────────────────────────────────────

class TestEnvVarParsing(_CleanEnvBase):

    def test_unset_returns_none(self):
        from engine.jedi_gating import _parse_env_override
        self.assertIsNone(_parse_env_override())

    def test_truthy_values_return_true(self):
        from engine.jedi_gating import _parse_env_override
        for raw in ("1", "true", "TRUE", "True", "on", "ON", "yes", "YES"):
            with patch.dict(os.environ, {self.ENV_VAR: raw}):
                self.assertTrue(
                    _parse_env_override(),
                    f"Expected True for {raw!r}",
                )

    def test_falsy_values_return_false(self):
        from engine.jedi_gating import _parse_env_override
        for raw in ("0", "false", "FALSE", "False", "off", "OFF", "no", "NO"):
            with patch.dict(os.environ, {self.ENV_VAR: raw}):
                self.assertFalse(
                    _parse_env_override(),
                    f"Expected False for {raw!r}",
                )

    def test_whitespace_tolerated(self):
        from engine.jedi_gating import _parse_env_override
        with patch.dict(os.environ, {self.ENV_VAR: "  true  "}):
            self.assertTrue(_parse_env_override())
        with patch.dict(os.environ, {self.ENV_VAR: "\tno\n"}):
            self.assertFalse(_parse_env_override())

    def test_unrecognized_value_returns_none_with_warning(self):
        """Bad values fail loud (logged warning) but fall through to
        the next layer rather than raising."""
        from engine.jedi_gating import _parse_env_override
        for raw in ("maybe", "2", "TRUEISH", ""):
            with patch.dict(os.environ, {self.ENV_VAR: raw}):
                self.assertIsNone(
                    _parse_env_override(),
                    f"Expected None for {raw!r}",
                )


# ──────────────────────────────────────────────────────────────────────
# 2. Era YAML policy reading
# ──────────────────────────────────────────────────────────────────────

class TestEraYamlPolicy(_CleanEnvBase):
    """The CW era.yaml ships with progression_cooldowns_enabled: true.
    These tests verify the loader picks that up correctly."""

    def test_cw_era_yaml_returns_true(self):
        from engine.jedi_gating import _read_era_policy_flag
        from engine.era_state import set_active_config, clear_active_config

        class _Cfg:
            active_era = "clone_wars"
            use_yaml_director_data = True

        try:
            set_active_config(_Cfg())
            self.assertTrue(_read_era_policy_flag())
        finally:
            clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# 3. cooldowns_enabled() resolution order
# ──────────────────────────────────────────────────────────────────────

class TestCooldownsEnabled(_CleanEnvBase):

    def test_default_strict_when_no_overrides(self):
        from engine.jedi_gating import cooldowns_enabled
        from engine.era_state import clear_active_config
        # Ensure no era yaml lookup succeeds (default era is gcw, no
        # progression policy key set there).
        clear_active_config()
        # With no env var AND no era yaml flag found, default is True.
        # GCW era.yaml exists but does NOT have the F.7.k flag, so the
        # YAML lookup returns None and we fall through to the True
        # default. Production-correct.
        self.assertTrue(cooldowns_enabled())

    def test_env_var_false_overrides_yaml(self):
        from engine.jedi_gating import cooldowns_enabled
        from engine.era_state import set_active_config, clear_active_config

        class _Cfg:
            active_era = "clone_wars"
            use_yaml_director_data = True

        try:
            set_active_config(_Cfg())
            with patch.dict(os.environ, {self.ENV_VAR: "0"}):
                # Env var wins — bypass even though CW yaml says strict.
                self.assertFalse(cooldowns_enabled())
        finally:
            clear_active_config()

    def test_env_var_true_overrides_default(self):
        from engine.jedi_gating import cooldowns_enabled
        from engine.era_state import clear_active_config
        clear_active_config()
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            self.assertTrue(cooldowns_enabled())

    def test_yaml_used_when_env_var_invalid(self):
        """A bad env var value falls through to YAML. CW yaml says True."""
        from engine.jedi_gating import cooldowns_enabled
        from engine.era_state import set_active_config, clear_active_config

        class _Cfg:
            active_era = "clone_wars"
            use_yaml_director_data = True

        try:
            set_active_config(_Cfg())
            with patch.dict(os.environ, {self.ENV_VAR: "garbage"}):
                self.assertTrue(cooldowns_enabled())
        finally:
            clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# 4. act_2_gate_passed
# ──────────────────────────────────────────────────────────────────────

class TestActGate(_CleanEnvBase):
    """Bypass preserves the structural 'must be invited first' guard
    even when timer is short-circuited."""

    def test_bypass_blocks_pre_invitation(self):
        from engine.jedi_gating import act_2_gate_passed
        with patch.dict(os.environ, {self.ENV_VAR: "0"}):
            # village_act = 0 (not yet invited) → still blocked even
            # under bypass.
            self.assertFalse(act_2_gate_passed({"village_act": 0}))

    def test_bypass_passes_invited(self):
        from engine.jedi_gating import act_2_gate_passed
        with patch.dict(os.environ, {self.ENV_VAR: "0"}):
            # village_act = 1 with no unlocked_at — strict math would
            # block on bad data; bypass should allow.
            self.assertTrue(act_2_gate_passed(
                {"village_act": 1, "village_act_unlocked_at": 0},
            ))

    def test_bypass_passes_under_strict_cooldown(self):
        """Even with a freshly-set village_act_unlocked_at (strict
        math says 7 days remaining), bypass returns True."""
        from engine.jedi_gating import act_2_gate_passed
        import time
        with patch.dict(os.environ, {self.ENV_VAR: "0"}):
            self.assertTrue(act_2_gate_passed({
                "village_act": 1,
                "village_act_unlocked_at": time.time(),
            }))

    def test_strict_blocks_inside_cooldown(self):
        from engine.jedi_gating import act_2_gate_passed
        import time
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            # Just-set unlocked_at → 7 days remaining → strict blocks.
            self.assertFalse(act_2_gate_passed({
                "village_act": 1,
                "village_act_unlocked_at": time.time(),
            }))

    def test_strict_allows_after_cooldown(self):
        from engine.jedi_gating import act_2_gate_passed
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            # 8 days ago → strict allows.
            self.assertTrue(act_2_gate_passed({
                "village_act": 1,
                "village_act_unlocked_at": 1.0,  # epoch — long ago
            }))


# ──────────────────────────────────────────────────────────────────────
# 5. trial_gate_passed
# ──────────────────────────────────────────────────────────────────────

class TestTrialGate(_CleanEnvBase):

    def test_bypass_always_passes(self):
        from engine.jedi_gating import trial_gate_passed
        import time
        with patch.dict(os.environ, {self.ENV_VAR: "0"}):
            # Inside strict cooldown but bypass returns True.
            self.assertTrue(trial_gate_passed({
                "village_trial_last_attempt": time.time(),
            }))

    def test_strict_blocks_inside_cooldown(self):
        from engine.jedi_gating import trial_gate_passed
        import time
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            self.assertFalse(trial_gate_passed({
                "village_trial_last_attempt": time.time(),
            }))

    def test_strict_allows_no_prior_attempt(self):
        from engine.jedi_gating import trial_gate_passed
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            self.assertTrue(trial_gate_passed({
                "village_trial_last_attempt": 0,
            }))


# ──────────────────────────────────────────────────────────────────────
# 6. courage_retry_gate_passed
# ──────────────────────────────────────────────────────────────────────

class TestCourageRetryGate(_CleanEnvBase):

    def test_bypass_always_passes(self):
        from engine.jedi_gating import courage_retry_gate_passed
        import time
        with patch.dict(os.environ, {self.ENV_VAR: "0"}):
            self.assertTrue(courage_retry_gate_passed({
                "village_trial_last_attempt": time.time(),
            }))

    def test_strict_blocks_inside_cooldown(self):
        from engine.jedi_gating import courage_retry_gate_passed
        import time
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            self.assertFalse(courage_retry_gate_passed({
                "village_trial_last_attempt": time.time(),
            }))


# ──────────────────────────────────────────────────────────────────────
# 7. stamp_trial_attempt
# ──────────────────────────────────────────────────────────────────────

class TestStampTrialAttempt(unittest.TestCase):

    def test_writes_to_char_and_save_kwargs(self):
        from engine.jedi_gating import stamp_trial_attempt
        char = {"id": 99}
        save_kwargs = {"village_trial_skill_done": 1}
        ts = stamp_trial_attempt(char, save_kwargs, now=1234567890.0)
        self.assertEqual(ts, 1234567890.0)
        self.assertEqual(char["village_trial_last_attempt"], 1234567890.0)
        self.assertEqual(save_kwargs["village_trial_last_attempt"], 1234567890.0)
        # Pre-existing save_kwargs entries are preserved.
        self.assertEqual(save_kwargs["village_trial_skill_done"], 1)

    def test_idempotent_overwrites_with_latest(self):
        from engine.jedi_gating import stamp_trial_attempt
        char = {}
        save_kwargs = {}
        stamp_trial_attempt(char, save_kwargs, now=1.0)
        stamp_trial_attempt(char, save_kwargs, now=2.0)
        self.assertEqual(char["village_trial_last_attempt"], 2.0)
        self.assertEqual(save_kwargs["village_trial_last_attempt"], 2.0)

    def test_default_now_uses_wall_clock(self):
        """Without a now override, uses time.time()."""
        from engine.jedi_gating import stamp_trial_attempt
        import time
        char = {}
        save_kwargs = {}
        before = time.time()
        ts = stamp_trial_attempt(char, save_kwargs)
        after = time.time()
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)


# ──────────────────────────────────────────────────────────────────────
# 8. enter_trials integration — gate blocks transition
# ──────────────────────────────────────────────────────────────────────

class _MockDB:
    """Minimal db stub for enter_trials integration tests."""
    def __init__(self):
        self.saved_chars = []

    async def save_character(self, char_id, **kwargs):
        self.saved_chars.append((char_id, kwargs))


class TestEnterTrialsIntegration(_CleanEnvBase):

    def _run(self, coro):
        # asyncio.run() creates and tears down its own loop per call
        # — clean across Python 3.12 / 3.14 without the deprecated
        # get_event_loop() warning.
        return asyncio.run(coro)

    def test_bypass_allows_transition_immediately(self):
        from engine.village_quest import enter_trials
        import time
        char = {
            "id": 1,
            "name": "Tester",
            "village_act": 1,
            "village_act_unlocked_at": time.time(),  # just invited
        }
        db = _MockDB()
        with patch.dict(os.environ, {self.ENV_VAR: "0"}):
            ok = self._run(enter_trials(char, db))
        self.assertTrue(ok)
        self.assertEqual(char["village_act"], 2)  # ACT_IN_TRIALS
        self.assertEqual(len(db.saved_chars), 1)

    def test_strict_blocks_transition_inside_cooldown(self):
        from engine.village_quest import enter_trials
        import time
        char = {
            "id": 1,
            "name": "Tester",
            "village_act": 1,
            "village_act_unlocked_at": time.time(),  # just invited
        }
        db = _MockDB()
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            ok = self._run(enter_trials(char, db))
        self.assertFalse(ok)
        self.assertEqual(char["village_act"], 1)  # unchanged
        self.assertEqual(len(db.saved_chars), 0)

    def test_strict_allows_transition_after_cooldown(self):
        from engine.village_quest import enter_trials
        char = {
            "id": 1,
            "name": "Tester",
            "village_act": 1,
            "village_act_unlocked_at": 1.0,  # epoch — long ago
        }
        db = _MockDB()
        with patch.dict(os.environ, {self.ENV_VAR: "1"}):
            ok = self._run(enter_trials(char, db))
        self.assertTrue(ok)
        self.assertEqual(char["village_act"], 2)


# ──────────────────────────────────────────────────────────────────────
# 9. Source markers — defensive against accidental revert
# ──────────────────────────────────────────────────────────────────────

class TestSourceMarkers(unittest.TestCase):
    """A future drop that accidentally reverts the F.7.k wire-up will
    have a source-level tripwire here."""

    def test_jedi_gating_carries_marker(self):
        from engine import jedi_gating
        with open(jedi_gating.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("F.7.k", src)
        self.assertIn("cooldowns_enabled", src)
        self.assertIn("stamp_trial_attempt", src)

    def test_village_quest_consults_act_gate(self):
        from engine import village_quest
        with open(village_quest.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("act_2_gate_passed", src)
        self.assertIn("F.7.k", src)

    def test_village_trials_writes_last_attempt(self):
        from engine import village_trials
        with open(village_trials.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("stamp_trial_attempt", src)
        self.assertIn("F.7.k", src)
        # All five trial completion paths should reference the helper.
        # We don't count exact occurrences (a single import + 5 calls
        # is the floor), but require >= 6 mentions total.
        self.assertGreaterEqual(src.count("stamp_trial_attempt"), 6)

    def test_era_yaml_carries_progression_flag(self):
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("progression_cooldowns_enabled", src)
        self.assertIn("F.7.k", src)


if __name__ == "__main__":
    unittest.main()
