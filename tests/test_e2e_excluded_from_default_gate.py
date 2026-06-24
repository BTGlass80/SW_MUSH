# -*- coding: utf-8 -*-
"""Regression guard: the real-browser E2E suite must stay OUT of the default gate.

2026-06-24: `tests/e2e/test_e2e_new_player.py` launches Chromium and deadlocks
pytest-xdist, hanging the whole threaded gate. `tests/e2e/conftest.py` excludes
the e2e `test_*.py` files from collection unless `RUN_E2E=1` (the same opt-in env
var the e2e test's own `skipif` uses). If someone deletes or weakens that guard,
the gate will hang again on the next run — this test fails loudly first, at unit
speed, so the breakage is caught before a gate ever hangs.
"""
from __future__ import annotations

import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
E2E_DIR = os.path.join(HERE, "e2e")
CONFTEST = os.path.join(E2E_DIR, "conftest.py")


class TestE2EExcludedFromDefaultGate(unittest.TestCase):
    def test_e2e_conftest_guard_exists(self):
        self.assertTrue(
            os.path.isfile(CONFTEST),
            "tests/e2e/conftest.py is missing — the e2e gate-exclusion guard is gone; "
            "the default threaded gate will hang on the Chromium e2e test.",
        )

    def test_guard_gates_on_optin_env_var(self):
        src = open(CONFTEST, encoding="utf-8").read()
        self.assertIn(
            "RUN_E2E", src,
            "e2e exclusion must key off the RUN_E2E opt-in env var "
            "(the same one the e2e test's own skipif uses).",
        )
        self.assertIn(
            "collect_ignore_glob", src,
            "e2e conftest must use collect_ignore_glob to drop the e2e test files "
            "from default collection (survives `-o addopts=''`).",
        )

    def test_every_e2e_pytest_module_is_covered_by_the_glob(self):
        # The guard globs `test_*.py`. Any e2e pytest module using a different
        # filename prefix would slip past it and re-enter the default gate.
        strays = [
            f for f in os.listdir(E2E_DIR)
            if f.endswith(".py")
            and f != "conftest.py"
            and _looks_like_pytest_module(f)
            and not f.startswith("test_")
        ]
        self.assertEqual(
            strays, [],
            f"e2e pytest modules not covered by the `test_*.py` exclusion glob: "
            f"{strays} — rename them to `test_*.py` or widen the glob in "
            f"tests/e2e/conftest.py, or they will re-enter the default gate.",
        )


def _looks_like_pytest_module(filename: str) -> bool:
    """True if pytest would collect this file by default naming rules.

    pytest collects `test_*.py` and `*_test.py`. The standalone scenario scripts
    (`play_*.py`, `breakit_*.py`) match neither and are run directly, not via
    pytest — so they are correctly NOT pytest modules.
    """
    return filename.startswith("test_") or filename.endswith("_test.py")


if __name__ == "__main__":
    unittest.main()
