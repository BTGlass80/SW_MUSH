# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/ — Reusable scenario building blocks.

Scenarios are plain async functions that take a harness and a
``_ClientSession`` (or build their own). They are NOT pytest tests
themselves; pytest entry points in ``tests/smoke/test_smoke_*.py``
wrap them. This separation lets one scenario call another (e.g.
the reconnect scenario calls login_basic, sets state, then re-logs).
"""
