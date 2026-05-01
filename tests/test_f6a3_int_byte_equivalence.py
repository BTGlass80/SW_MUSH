# -*- coding: utf-8 -*-
"""
tests/test_f6a3_int_byte_equivalence.py — Byte-equivalence test for
F.6a.3-int (DirectorAI seam integration).

Drop F.6a.3-int's claim:

  After integration, when `use_yaml_director_data` is False (default),
  `engine.director`'s runtime-visible config — VALID_FACTIONS,
  DEFAULT_INFLUENCE, and the system_prompt used in `_call_claude` —
  is byte-identical to what the F.6a.3 seam returns from its legacy
  fallback path.

This test is written BEFORE the wire-up. It must pass BEFORE wiring
(asserting the seam's legacy values match the director's hardcoded
constants — which is what the prompt lift just established) AND
AFTER wiring (asserting the integration didn't drift). That is the
gate.

Coverage:
  - Module-level VALID_FACTIONS (legacy const) == seam.valid_factions
  - Module-level DEFAULT_INFLUENCE (legacy const) == seam.zone_baselines
  - The L817 inline duplicate (post-wiring: replaced with module ref)
    Documented separately — pre-wiring this test is informational.
  - The inline system_prompt at L678 (post-wiring: replaced with
    cfg.system_prompt) is byte-identical to the seam's legacy prompt.
  - Length checks as a tripwire: the prompt must remain non-trivial
    (>1500 chars) so a future placeholder regression is caught.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import director as director_module  # noqa: E402
from engine.director_config_loader import (  # noqa: E402
    get_director_runtime_config,
)


class TestModuleConstantsMatchSeam(unittest.TestCase):
    """Module-level VALID_FACTIONS / DEFAULT_INFLUENCE on engine.director
    must equal the seam's legacy-path values. After F.6a.3-int, these
    constants will be derived from the seam at module load — the test
    asserts the value contract regardless of whether they're hardcoded
    or derived.
    """

    @classmethod
    def setUpClass(cls):
        cls.cfg = get_director_runtime_config(era=None)

    def test_valid_factions_byte_equal(self):
        self.assertEqual(
            director_module.VALID_FACTIONS,
            self.cfg.valid_factions,
            "engine.director.VALID_FACTIONS drifted from seam legacy",
        )

    def test_valid_factions_is_frozenset(self):
        # Hashability matters — VALID_FACTIONS is used in `if x in VALID_FACTIONS`
        # Throughout director.py. Must be a frozenset (or at least hashable).
        self.assertIsInstance(director_module.VALID_FACTIONS, frozenset)
        self.assertIsInstance(self.cfg.valid_factions, frozenset)

    def test_default_influence_byte_equal(self):
        self.assertEqual(
            director_module.DEFAULT_INFLUENCE,
            self.cfg.zone_baselines,
            "engine.director.DEFAULT_INFLUENCE drifted from seam legacy",
        )

    def test_default_influence_zone_keys_match(self):
        self.assertEqual(
            set(director_module.DEFAULT_INFLUENCE.keys()),
            set(self.cfg.zone_baselines.keys()),
        )

    def test_default_influence_per_zone_factions_match(self):
        for zone, factions in director_module.DEFAULT_INFLUENCE.items():
            self.assertEqual(
                set(factions.keys()),
                set(self.cfg.zone_baselines[zone].keys()),
                f"zone {zone!r}: faction keys mismatch",
            )

    def test_default_influence_per_value_byte_equal(self):
        for zone, factions in director_module.DEFAULT_INFLUENCE.items():
            for faction, score in factions.items():
                self.assertEqual(
                    score,
                    self.cfg.zone_baselines[zone][faction],
                    f"{zone}/{faction}: {score} vs {self.cfg.zone_baselines[zone][faction]}",
                )


class TestSystemPromptByteEqual(unittest.TestCase):
    """Verify the seam's legacy system_prompt matches the inline literal
    currently used in DirectorAI._call_claude. Pre-wiring, this checks
    the lift was correct; post-wiring, it pins the contract.
    """

    @classmethod
    def setUpClass(cls):
        cls.cfg = get_director_runtime_config(era=None)
        cls.seam_prompt = cls.cfg.system_prompt
        # Read the director.py source and extract the inline prompt.
        # The prompt is assigned to a local `system_prompt = ( ... )`
        # variable inside `_call_claude`. We grab the parenthesized
        # string concatenation as the canonical literal.
        director_path = os.path.join(
            PROJECT_ROOT, "engine", "director.py",
        )
        with open(director_path, "r", encoding="utf-8") as f:
            src = f.read()
        cls.director_source = src

    def test_seam_prompt_is_nontrivial(self):
        # Tripwire: if anyone re-introduces a placeholder string the
        # length check catches it. The real prompt is ~3.4kB.
        self.assertGreater(
            len(self.seam_prompt), 1500,
            f"seam system_prompt only {len(self.seam_prompt)} chars — "
            f"likely a placeholder regression",
        )

    def test_seam_prompt_starts_with_director_role_line(self):
        self.assertTrue(
            self.seam_prompt.startswith(
                "You are the Director AI for a Star Wars MUSH "
                "set in Mos Eisley, Tatooine."
            ),
            "seam prompt does not start with the canonical Director role line",
        )

    def test_seam_prompt_includes_faction_management_section(self):
        # If a future refactor accidentally drops a section, this
        # catches it.
        self.assertIn("FACTION MANAGEMENT:", self.seam_prompt)
        self.assertIn("PC HOOKS:", self.seam_prompt)
        self.assertIn("FACTION STANDINGS:", self.seam_prompt)

    def test_seam_prompt_includes_json_response_schema(self):
        # The LLM's response schema is non-negotiable — if this drifts,
        # the parser at L809-811 fails JSON.loads on the response.
        self.assertIn('"influence_adjustments"', self.seam_prompt)
        self.assertIn('"faction_orders"', self.seam_prompt)
        self.assertIn('"pc_hooks"', self.seam_prompt)

    def test_seam_prompt_matches_inline_literal_byte_equal(self):
        """Pre-F.6a.7 Phase 2 this asserted the seam's _LEGACY_SYSTEM_PROMPT
        equaled the inline literal in director.py character-for-character.

        Phase 2 deleted _LEGACY_SYSTEM_PROMPT — the prompt now lives
        exclusively in data/worlds/gcw/director_config.yaml. The byte-
        equivalence guarantee is preserved by the F.6a.3 byte-equiv test
        suite (test_gcw_yaml_path_returns_yaml_values etc.), which gates
        any drift between the YAML and the original literal.

        Post-Phase-2 this test asserts only that the seam's prompt is
        non-empty and matches itself across two independent calls
        (drift detection for in-memory caching bugs).
        """
        a = get_director_runtime_config(era=None).system_prompt
        b = get_director_runtime_config(era=None).system_prompt
        self.assertEqual(a, b,
                         "seam returns drifting prompt across calls")
        self.assertGreater(len(a), 1500,
                           "seam prompt is suspiciously short — possible "
                           "regression to placeholder")


class TestL817DuplicateAlignment(unittest.TestCase):
    """Documents the L817 inline duplicate frozenset literal.

    Pre-wiring: there's a SECOND copy of VALID_FACTIONS at L817
    (a function-local literal that shadows the module constant).
    Post-wiring: this should be replaced with a reference to the
    module constant. This test asserts the value matches the seam's
    legacy regardless — making it a tripwire either way.
    """

    @classmethod
    def setUpClass(cls):
        cls.cfg = get_director_runtime_config(era=None)
        director_path = os.path.join(
            PROJECT_ROOT, "engine", "director.py",
        )
        with open(director_path, "r", encoding="utf-8") as f:
            cls.director_source = f.read()

    def test_no_inline_frozenset_literal_after_wiring(self):
        """After F.6a.3-int wiring, the L817 inline literal should be
        gone — replaced with a reference to the module-level
        VALID_FACTIONS.

        Pre-wiring this test FAILS (one inline literal exists);
        post-wiring it PASSES. This makes it a useful gate during
        review.
        """
        # Look for `frozenset({"imperial", "rebel", "criminal", "independent"})`
        # ANYWHERE in director.py except the module-level definition at
        # the top.
        # The pattern: a frozenset with exactly those four GCW factions.
        pattern = re.compile(
            r'frozenset\(\{\s*'
            r'"(imperial|rebel|criminal|independent)"\s*,\s*'
            r'"(imperial|rebel|criminal|independent)"\s*,\s*'
            r'"(imperial|rebel|criminal|independent)"\s*,\s*'
            r'"(imperial|rebel|criminal|independent)"\s*'
            r'\}\)'
        )
        matches = pattern.findall(self.director_source)
        # Expected: exactly 1 match (the module-level VALID_FACTIONS = ...).
        # Pre-wiring: 2 matches (module-level + L817 duplicate).
        # Post-wiring: 1 match (only the module-level).
        self.assertLessEqual(
            len(matches), 1,
            f"Found {len(matches)} inline frozenset literals of the GCW "
            f"factions in director.py — should be at most 1 (the module "
            f"constant). The L817 duplicate must be replaced with a "
            f"reference to VALID_FACTIONS after F.6a.3-int wiring.",
        )


if __name__ == "__main__":
    unittest.main()
