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
"""

import pytest

_SPA_DIR = __file__.replace("\\", "/").rsplit("/", 1)[0]  # .../tests/spa


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Tag every test collected under tests/spa/ with the ``slow`` marker."""
    for item in items:
        path = str(getattr(item, "fspath", "")).replace("\\", "/")
        if path.startswith(_SPA_DIR):
            item.add_marker(pytest.mark.slow)
