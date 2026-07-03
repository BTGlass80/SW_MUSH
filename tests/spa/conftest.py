"""Directory-level pytest config for the SPA (web client) test suite.

Every test under ``tests/spa/`` validates client-side JavaScript by spawning
a Node.js subprocess (via ``spa_dom_harness.run_with_dom`` or a direct
``subprocess.run(['node', ...])``). That per-test process spawn — not engine
or DB work — is the dominant wall-clock cost in the whole suite, and none of
these tests touch ``engine/`` or the database.

To keep the inner dev loop fast, every test in THIS directory is tagged
``slow`` so the default ``pytest`` invocation deselects it (see ``pytest.ini``
addopts: ``-m "not ... and not slow"``). Run the SPA suite explicitly with
``pytest tests/spa -m slow`` (or ``-m ""``), and the full gate
(``run_all_tests.bat``, which clears addopts) still runs it.

Implementation notes (two non-obvious pytest gotchas):
  * ``pytest_collection_modifyitems`` in a sub-directory conftest still
    receives the ENTIRE session's ``items``, not just this directory's — so
    we must path-filter to ``tests/spa/`` ourselves or we would mark the
    whole suite slow.
  * ``-m`` deselection also happens inside ``pytest_collection_modifyitems``;
    ``tryfirst=True`` guarantees our marks are applied BEFORE the built-in
    marker filter runs, so ``-m "not slow"`` actually deselects them.

Fable addendum 2026-07-03 §5b — jsdom-subprocess cross-worker contention
----------------------------------------------------------------------
A full-suite gate under ``-n auto --dist loadscope`` observed "3 SPA/jsdom
parallel-contention flakes, green in isolation" — every jsdom test spawns
its own ``node`` subprocess bounded by a fixed timeout
(``spa_dom_harness.run_with_dom``: 20s), and with many xdist workers each
spawning Node concurrently, a handful of calls can get CPU-starved past
that bound on a busy box, even though nothing is actually hung.

That gap was closed in drop ``fable-addendum-hygiene`` with the ``serial``
pytest marker (registered in ``pytest.ini``) + the skip-under-xdist-worker
hook in the top-level ``tests/conftest.py`` (checks ``PYTEST_XDIST_WORKER``
and skips ``serial``-marked items only when running as an xdist worker —
they still execute, and must pass, under the real serial
``run_all_tests.bat`` gate). Three modules were marked directly via
``pytestmark = pytest.mark.serial``.

This file EXTENDS that same mechanism (not a parallel one) to a second,
independently-measured set: a real ``pytest tests/spa -n auto --dist
loadscope --durations=0`` run (this box, 2026-07-03) summed per-test
durations by file. The three highest-total-duration files — the ones
generating the most concurrent Node-spawn CPU load, and therefore
statistically the ones most likely to tip a call over the 20s ceiling under
contention — were, by a clear margin over the rest of the ~55-file
directory:

  test_m3_assembled_client.py             73.5s / 28 tests (avg 2.62s)
  test_m3_sheet.py                        69.0s / 28 tests (avg 2.47s)
  test_combat_inspector_d_prime_client.py 61.6s / 29 tests (avg 2.12s)

(next-highest, test_m3_cockpit.py, was 59.3s — a real gap below these
three.) Auto-applying ``pytest.mark.serial`` to these here (rather than
adding another ``pytestmark`` line to each file) reuses the SAME
filename-driven auto-tag pattern this conftest already uses for ``slow``,
and reuses the top-level ``tests/conftest.py`` skip-hook verbatim — no new
marker, no new skip mechanism, no new xdist behavior. (An earlier version
of this fix tried pytest-xdist's own ``xdist_group`` marker instead;
verified against the installed xdist 3.8.0 source
(``xdist/scheduler/loadscope.py::LoadScopeScheduling._split_scope``) that
``xdist_group`` is honoured ONLY under ``--dist loadgroup`` — this repo's
actual ``--dist loadscope`` gate ignores it for cross-file grouping
(confirmed empirically with a worker-id probe). The ``serial``-marker +
skip-under-xdist-worker approach above doesn't have that limitation, which
is why it's the one this file extends.)

As additional, independent defense-in-depth (not a replacement — belt and
suspenders), both shared Node-subprocess call sites
(``spa_dom_harness.run_with_dom`` / ``m3_combat_inspector_harness.
run_with_d_prime_block``) now retry once on ``subprocess.TimeoutExpired``
via ``spa_dom_harness._run_node_with_one_retry`` — this protects every
jsdom test in the directory, not just the ``serial``-marked ones, and still
lets a genuine hang fail (only ONE retry).
"""

import pytest

_SPA_DIR = __file__.replace("\\", "/").rsplit("/", 1)[0]  # .../tests/spa

# Fable addendum 2026-07-03 §5b: the three highest-measured-duration jsdom
# files not already covered by the `serial` pytestmark applied directly to
# test_fun2_onboard_checklist.py / test_m3_asset_catalog_after_41c.py /
# test_m3_asset_catalog_after_41d.py (see module docstring for the actual
# duration data). Filenames only (matched against the collected item's
# basename), so this stays correct regardless of OS path separators.
_SERIAL_MARKED_FILES = {
    "test_m3_assembled_client.py",
    "test_m3_sheet.py",
    "test_combat_inspector_d_prime_client.py",
}


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Tag every test collected under tests/spa/ with the ``slow`` marker.

    Also applies the ``serial`` marker (defined in pytest.ini, honored by
    tests/conftest.py's skip-under-xdist-worker hook) to the additional
    heaviest-measured jsdom files (see module docstring) — same marker,
    same skip mechanism as the three files marked directly via
    ``pytestmark``, just applied here instead of duplicated per-file.
    """
    for item in items:
        path = str(getattr(item, "fspath", "")).replace("\\", "/")
        if path.startswith(_SPA_DIR):
            item.add_marker(pytest.mark.slow)
            if path.rsplit("/", 1)[-1] in _SERIAL_MARKED_FILES:
                item.add_marker(pytest.mark.serial)
