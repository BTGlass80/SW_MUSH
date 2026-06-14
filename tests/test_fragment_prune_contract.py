# -*- coding: utf-8 -*-
"""
tests/test_fragment_prune_contract.py — guard for the 2026-06-14
`test-fragment-prune` drop (resolves TD.TEST_FRAGMENT_PRUNES_DEFERRED).

That drop removed verified-redundant / tautological test FRAGMENTS that
the test-suite audit surfaced. This module locks the removals in so they
cannot silently creep back, and asserts the canonical guards they were
redundant *against* are still present.

Eliminated:
  * 8 `TestDropMarker` classes (each asserted only that its own module
    docstring contained its own drop id — pure self-reference).
  * s43 `TestEncounterBoardingModule` (a 16-method subset of s40's
    39-method coverage of the SAME engine.encounter_boarding module).
  * s39 `TestSilentExceptInvariant` + s40 `TestNoSilentExceptPass`
    (narrow per-file silent-except guards; the project's actual policy
    is enforced by s38's repo-wide walk, and narrow `except X: pass` is
    intentionally allowed — 7 such blocks exist in production).
  * combat_extended.py's copy of `_find_hostile_npc` (now imported from
    the canonical ground_combat scenario).

Kept (audit overclaimed; verified NOT safe to remove):
  * test_director_adaptive_spend `TestManualFidelityPin` — tests the
    `_apply_governor` heuristic-override path, a different entry point
    from slice2's `set_manual_fidelity` API coverage.
  * test_orphan_wireup xfail tests — live forward-intent markers for a
    still-pending encounter-handler wire-up (not in server/ yet).

See CHANGELOG.md 2026-06-14 `test-fragment-prune`.
"""
from __future__ import annotations

import glob
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")


def _read(rel: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_no_tautological_dropmarker_classes_remain() -> None:
    offenders = []
    for path in glob.glob(os.path.join(TESTS_DIR, "test_*.py")):
        with open(path, encoding="utf-8") as f:
            # Column-0 class definition only — not string mentions like this one.
            if any(ln.startswith("class TestDropMarker") for ln in f.read().splitlines()):
                offenders.append(os.path.basename(path))
    assert not offenders, (
        "TestDropMarker classes only assert their own module docstring "
        f"contains their own drop id (tautological); reintroduced in: {offenders}"
    )


def test_s43_boarding_module_class_removed() -> None:
    assert "class TestEncounterBoardingModule" not in _read(
        os.path.join("tests", "test_session43.py")
    ), "s43's TestEncounterBoardingModule was a subset of s40 coverage; do not re-add."


def test_s40_remains_the_boarding_guard() -> None:
    """The coverage s43's removed class duplicated must still live in s40."""
    s40 = _read(os.path.join("tests", "test_session40.py"))
    assert "class TestBoardingEncounterModule" in s40
    assert "class TestShouldNpcBoard" in s40
    assert "class TestTierCalculation" in s40


def test_narrow_silent_except_guards_removed() -> None:
    assert "class TestSilentExceptInvariant" not in _read(
        os.path.join("tests", "test_session39.py")
    )
    assert "class TestNoSilentExceptPass" not in _read(
        os.path.join("tests", "test_session40.py")
    )


def test_s38_repo_wide_silent_except_guard_remains() -> None:
    """The canonical (kept) guard that the narrow ones were redundant against."""
    s38 = _read(os.path.join("tests", "test_session38.py"))
    assert "class TestSilentExceptInvariant" in s38
    assert "test_no_silent_except_pass_in_production" in s38


def test_combat_extended_uses_shared_find_hostile_npc() -> None:
    src = _read(os.path.join("tests", "smoke", "scenarios", "combat_extended.py"))
    assert "from tests.smoke.scenarios.ground_combat import _find_hostile_npc" in src
    assert "async def _find_hostile_npc" not in src, (
        "combat_extended should import the canonical helper, not redefine it."
    )
