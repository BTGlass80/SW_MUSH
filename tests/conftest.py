# -*- coding: utf-8 -*-
"""
tests/conftest.py — Fixture surface for the pytest suite.

Re-exports the ``harness`` fixture defined in ``tests/harness.py`` so that
tests can take it as a parameter (e.g. ``async def test_foo(self, harness):``)
without each test file needing its own fixture import.

If/when a real integration harness is built, just replace the fixture body
in ``tests/harness.py`` and every test that takes ``harness`` will start
exercising the live game loop instead of skipping.
"""
from tests.harness import harness  # noqa: F401  (fixture re-export)
