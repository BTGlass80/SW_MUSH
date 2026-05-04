# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_mail.py — Pytest entry points for the mail
smoke scenarios (ML1–ML5). Drop 4.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import mail


pytestmark = pytest.mark.smoke


class TestMail:
    """In-game mail: empty inbox, quick send, read, delete, purge."""

    async def test_ml1_empty_inbox_renders(self, harness):
        await mail.ml1_empty_inbox_renders(harness)

    async def test_ml2_quick_send_creates_rows(self, harness):
        await mail.ml2_quick_send_creates_rows(harness)

    async def test_ml3_inbox_after_send_shows_unread(self, harness):
        await mail.ml3_inbox_after_send_shows_unread(harness)

    async def test_ml4_read_displays_body_and_marks_read(self, harness):
        await mail.ml4_read_displays_body_and_marks_read(harness)

    async def test_ml5_delete_purge_cascades(self, harness):
        await mail.ml5_delete_purge_cascades(harness)
