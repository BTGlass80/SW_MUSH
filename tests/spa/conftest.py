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

No single test file names the specific flaky trio anywhere in the repo's
history (checked: CHANGELOG.md, TODO.json, the qwen-default-hardening and
hygiene-batch-f6 commit messages/gate notes) — the flake is inherently
box-contention-dependent, not a property of 3 fixed test IDs. Rather than
guess, this was measured directly: a real ``pytest tests/spa -n auto
--dist loadscope --durations=0`` run (this box, 2026-07-03) summed
per-test durations by FILE. The three files with the highest total
Node-subprocess CPU-time — i.e. the three that generate the most
concurrent Node-spawn load on the box, and are therefore statistically
the most likely to have a call tip over ``spa_dom_harness.run_with_dom``'s
20s timeout under real cross-worker contention — were, by a clear margin
over the rest of the ~55-file directory:

  test_m3_assembled_client.py           73.5s / 28 tests (avg 2.62s)
  test_m3_sheet.py                      69.0s / 28 tests (avg 2.47s)
  test_combat_inspector_d_prime_client.py 61.6s / 29 tests (avg 2.12s)

(next-highest, test_m3_cockpit.py, was 59.3s — a real gap below these
three.) All three build/exercise a substantial rendered UI structure
per call (buildAssembledClient's full shell, buildCharacterSheet's tabs,
the D' combat-inspector block) rather than one cheap module load, which
is the actual cost driver — not simply "how many .js files get loaded"
(the original, weaker hypothesis this file started with; the number of
files loaded turned out to correlate poorly with measured cost).

We tag them with pytest-xdist's own ``xdist_group`` marker (an existing
xdist mechanism, not a new one). **Verified limitation, checked against
the installed xdist 3.8.0 source
(``xdist/scheduler/loadscope.py::LoadScopeScheduling._split_scope``):**
``xdist_group`` is honoured ONLY by the ``--dist loadgroup`` scheduler —
``--dist loadscope`` (this repo's actual full-gate invocation, see
``pytest.ini``/HANDOFF docs) derives its scope purely from the nodeid
string (module, or module::class) and never consults markers, so under
``loadscope`` the marker is a documented no-op for cross-FILE grouping
(confirmed empirically: tagging these three still scheduled them onto
three different workers). We keep the marker anyway — it's harmless,
correctly wired (unit-pinned in
``tests/test_fable_addendum_hygiene_2026_07_03.py``), self-documenting,
and becomes fully effective the day the gate ever runs under ``--dist
loadgroup`` — but the mechanism that ACTUALLY fixes the flake under
``loadscope`` is the one-retry-on-``TimeoutExpired`` wrapper added to both
shared Node-subprocess call sites (``spa_dom_harness.
_run_node_with_one_retry``, reused by ``m3_combat_inspector_harness``):
it absorbs one transient CPU-starved spawn regardless of which tests are
unlucky or which scheduler is in play, so a "genuine trio" identity
doesn't even need to be right for the flake to go away. If a future gate
run still shows a DIFFERENT set of files flaking, that's expected —
extend ``_JSDOM_SERIAL_FILES`` below for documentation purposes; the
retry wrapper is what's actually load-bearing.
"""

import pytest

_SPA_DIR = __file__.replace("\\", "/").rsplit("/", 1)[0]  # .../tests/spa

# Fable addendum 2026-07-03 §5b: the three highest-measured-cost jsdom
# files (see module docstring for the actual duration data). Filenames
# only (matched against the collected item's basename), so this stays
# correct regardless of OS path separators.
_JSDOM_SERIAL_GROUP = "spa_jsdom_heaviest"
_JSDOM_SERIAL_FILES = {
    "test_m3_assembled_client.py",
    "test_m3_sheet.py",
    "test_combat_inspector_d_prime_client.py",
}


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Tag every test collected under tests/spa/ with the ``slow`` marker.

    Also xdist-group-serializes the three full-SPA-bundle jsdom files
    (see module docstring) so they never contend with each other for
    Node-subprocess CPU across workers under ``-n auto``.
    """
    for item in items:
        path = str(getattr(item, "fspath", "")).replace("\\", "/")
        if path.startswith(_SPA_DIR):
            item.add_marker(pytest.mark.slow)
            if path.rsplit("/", 1)[-1] in _JSDOM_SERIAL_FILES:
                item.add_marker(pytest.mark.spa_jsdom_serial)
                item.add_marker(pytest.mark.xdist_group(name=_JSDOM_SERIAL_GROUP))
