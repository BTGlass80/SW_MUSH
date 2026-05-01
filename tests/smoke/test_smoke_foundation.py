# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_foundation.py — Pytest entry points for F1-F5.

These are thin wrappers around ``scenarios/foundation.py``. The actual
scenario logic lives in scenarios/ so it can be reused (e.g. an F4
reconnect scenario calls F1's login_and_look as setup).

Marked ``@pytest.mark.smoke`` — opt in via ``pytest -m smoke``. Also
excluded from the default run by ``pytest.ini``'s ``addopts``.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import foundation


pytestmark = pytest.mark.smoke


class TestFoundation:
    """Foundation scenarios — must pass for the harness itself to be
    considered working. If any of these fail, every other smoke
    scenario will likely fail too.

    Class-scoped harness per design §6 — all five tests share a single
    booted GameServer + temp SQLite. That amortizes the ~1-2s
    world-build cost across the full class.
    """

    async def test_f1_login_and_look(self, harness):
        await foundation.f1_login_and_look(harness)

    async def test_f1_who_lists_self(self, harness):
        await foundation.f1_who_lists_self(harness)

    async def test_f2_account_creation_flow(self, harness):
        await foundation.f2_account_creation_flow(harness)

    async def test_f4_reconnect_preserves_state(self, harness):
        await foundation.f4_reconnect_preserves_state(harness)

    async def test_f5_char_switch_alt(self, harness):
        await foundation.f5_char_switch_alt(harness)


# F3 (Telnet text-wizard chargen) was deferred from SH1; it now lives
# in tests/smoke/test_smoke_telnet.py::TestTelnetChargen as part of
# drop SH3.