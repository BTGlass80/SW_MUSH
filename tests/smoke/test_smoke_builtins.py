# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_builtins.py — Pytest entry points for H6-H8.

Help, sheet, and where commands — the "every player uses these in
their first 30 seconds" surface.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import builtins


pytestmark = pytest.mark.smoke


class TestBuiltins:
    """Help, sheet, where — basic player utility commands."""

    async def test_h6_help_index_and_topic(self, harness):
        await builtins.h6_help_index_and_topic(harness)

    async def test_h6b_help_unknown_topic(self, harness):
        await builtins.h6b_help_unknown_topic(harness)

    async def test_h7_sheet_displays(self, harness):
        await builtins.h7_sheet_displays(harness)

    async def test_h8_where_command(self, harness):
        await builtins.h8_where_command(harness)
