# -*- coding: utf-8 -*-
"""
tests/test_slow_marker_contract.py — guard for the 2026-06-14
`test-suite-prune` drop.

That drop activated the previously-defined-but-unused `slow` pytest
marker as the inner-loop time lever, and deleted a small set of
verified-dead test files. This module locks in that contract so it
cannot silently regress:

  * The SINGLE root `pytest.ini` deselects `slow` by default — if it
    drops `not slow`, the inner loop silently re-runs the heavy tests.
    `tests/pytest.ini` was removed (TD.DUAL_PYTEST_INI, 2026-06-17):
    the root config now governs both no-arg and targeted runs.
  * `tests/spa/conftest.py` marks the SPA suite slow, and does so
    ONLY for tests under tests/spa/ (a naive
    `pytest_collection_modifyitems` would mark the whole suite).
  * the `slow` marker is actually applied to a meaningful number of
    non-SPA files (the marker is not "defined but unused" again).
  * the deleted dead-weight files stay deleted, and the obsolete
    stale-duplicate-tree `collect_ignore` guard stays removed.
  * the f7c1 brittle whole-table NPC-count canary stays pruned.

See CHANGELOG.md 2026-06-14 `test-suite-prune` and TODO.json
TD.DUAL_PYTEST_INI (RESOLVED) / TD.TEST_FRAGMENT_PRUNES_DEFERRED.
"""
from __future__ import annotations

import glob
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")


def _read(rel: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── both configs deselect slow by default ──────────────────────────────────

def test_root_pytest_ini_excludes_slow_by_default() -> None:
    ini = _read("pytest.ini")
    assert "addopts" in ini
    assert "not slow" in ini, (
        "root pytest.ini addopts must keep `not slow` — otherwise the "
        "no-arg root run re-includes every slow-marked test."
    )


def test_single_pytest_ini_no_duplicate() -> None:
    """Tombstone guard: tests/pytest.ini was removed (TD.DUAL_PYTEST_INI,
    2026-06-17). The root pytest.ini is now the sole config, governing
    both no-arg and targeted runs. Ensure it stays that way."""
    assert not os.path.exists(os.path.join(PROJECT_ROOT, "tests", "pytest.ini")), (
        "tests/pytest.ini must not exist — the root pytest.ini is the "
        "single config (TD.DUAL_PYTEST_INI RESOLVED). Delete any "
        "reintroduced tests/pytest.ini to prevent inner-loop divergence."
    )


# ── the SPA directory marks itself slow, and ONLY itself ────────────────────

def test_spa_conftest_marks_slow_and_path_filters() -> None:
    conf = _read(os.path.join("tests", "spa", "conftest.py"))
    assert "pytest.mark.slow" in conf, (
        "tests/spa/conftest.py must add the slow marker to SPA tests "
        "(every SPA test spawns a Node subprocess)."
    )
    # It MUST path-filter — pytest_collection_modifyitems in a subdir
    # conftest still receives the WHOLE session's items, so an unfiltered
    # loop would mark the entire suite slow.
    assert "tests/spa" in conf or "_SPA_DIR" in conf, (
        "tests/spa/conftest.py must path-filter to tests/spa/ so it does "
        "not mark the whole suite slow."
    )


def test_this_contract_file_is_not_marked_slow() -> None:
    """This guard must itself run in the default (fast) inner loop, so it
    must not carry a module-level slow marker. It also lives outside
    tests/spa/, so the SPA conftest must not sweep it into slow either."""
    plain = _read(os.path.join("tests", "test_slow_marker_contract.py"))
    # Look for a real module-level assignment (column 0), not the string
    # literals that appear inside this file's own assertions.
    module_level_pytestmark = [
        ln for ln in plain.splitlines() if ln.startswith("pytestmark")
    ]
    assert not module_level_pytestmark, module_level_pytestmark


# ── the marker is actually used (not "defined but unused" again) ────────────

def test_slow_marker_is_actually_used_by_many_files() -> None:
    hits = 0
    for path in glob.glob(os.path.join(TESTS_DIR, "test_*.py")):
        with open(path, encoding="utf-8") as f:
            if "pytest.mark.slow" in f.read():
                hits += 1
    assert hits >= 20, (
        f"expected the `slow` marker applied across many heavy files; "
        f"found only {hits}. The test-suite-prune drop tagged ~37."
    )


# ── deleted dead weight stays deleted ──────────────────────────────────────

def test_deleted_dead_weight_stays_deleted() -> None:
    gone = [
        os.path.join("tests", "tests"),  # stale-duplicate tree
        os.path.join("tests", "spa", "combat_inspector_extract.py"),
        os.path.join("tests", "test_session46_ws_frame_parse.py"),
        os.path.join("tests", "test_security_level_yaml_audit.py"),
    ]
    still_here = [p for p in gone if os.path.exists(os.path.join(PROJECT_ROOT, p))]
    assert not still_here, f"these were eliminated and must stay gone: {still_here}"


def test_stale_duplicate_collect_ignore_guard_removed() -> None:
    conf = _read(os.path.join("tests", "conftest.py"))
    assert "collect_ignore" not in conf, (
        "the tests/tests/ stale-duplicate tree is deleted, so its "
        "belt-and-suspenders collect_ignore guard must be removed too."
    )


# ── the brittle canary stays pruned ────────────────────────────────────────

def test_f7c1_brittle_npc_count_canary_pruned() -> None:
    f7c1 = _read(os.path.join("tests", "test_f7c1_village_trials.py"))
    assert "test_total_npc_count_includes_all_seven_village" not in f7c1, (
        "the brittle whole-table NPC COUNT(*) canary was pruned (it drifted "
        "10× and its own comment conceded the by-name checks are the real "
        "guard); it must not return."
    )
