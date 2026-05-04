# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_progression.py — Pytest entry points for the
progression / Jedi-gating / kudos-recipient scenarios (PR1–PR5).
Drop 3 Block D.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import progression


pytestmark = pytest.mark.smoke


class TestProgression:
    """Chain corpus, Jedi-Path lock, +kudos recipient, playtime gate."""

    async def test_pr1_chain_corpus_loads(self, harness):
        await progression.pr1_chain_corpus_loads_with_jedi_locked(harness)

    async def test_pr2_jedi_locked_message(self, harness):
        await progression.pr2_jedi_locked_message_references_discovery(harness)

    async def test_pr3_kudos_increments_recipient_cp_ticks(self, harness):
        await progression.pr3_kudos_increments_recipient_cp_ticks(harness)

    async def test_pr4_playtime_accumulator_and_gate(self, harness):
        await progression.pr4_playtime_accumulator_and_gate(harness)

    async def test_pr5_playtime_persists_across_fetch(self, harness):
        await progression.pr5_playtime_persists_across_fetch(harness)
