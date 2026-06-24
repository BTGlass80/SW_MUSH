"""Keep the real-browser E2E suite OUT of the default per-push gate — durably.

`tests/e2e/test_e2e_new_player.py` drives real Chromium via a Playwright
subprocess. It is already marked `slow`+`e2e` and `skipif(RUN_E2E != "1")`, so
the canonical gate (`run_all_tests.bat`, default `pytest.ini` addopts with
`-m "not ... and not slow"`) never selects it.

The gap this conftest closes: the **threaded triage command** clears addopts
(`-o addopts=""`, to drop the `-x`), which also drops the `not slow` filter and
RE-SELECTS the e2e test under pytest-xdist — where it HANGS the whole run at 0%
CPU (`--timeout-method=thread` can't kill it). Empirically, *excluding it from
collection* (not merely skipping it) is what reliably prevents the hang, so we
drop the e2e `test_*.py` files before they ever enter the xdist scheduler.

Result: e2e never runs on a push regardless of how the suite is invoked. It is a
separate lane, run only when a change actually touches the web client — opt in
with the SAME env var the test's own `skipif` uses:

    RUN_E2E=1 python -m pytest tests/e2e -m e2e

The standalone scenario scripts (`tests/e2e/play_*.py`, `breakit_*.py`) are not
pytest modules and are unaffected — run them directly:

    NODE_OPTIONS=--use-system-ca python tests/e2e/play_economy.py

Lives in a conftest (not `pytest.ini` addopts) on purpose: the threaded command
strips addopts, so an addopts-based exclusion would not survive it; a conftest
`collect_ignore_glob` does.
"""
import os

if os.environ.get("RUN_E2E") != "1":
    # Drop every e2e pytest module from collection by default; the RUN_E2E
    # opt-in (same var the test's own skipif uses) re-enables them.
    collect_ignore_glob = ["test_*.py"]
