# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_craft_trainer.py — Pytest entry points for the
crafting trainer lane (CT1-CT3, Gundark Drop G).
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import craft_trainer

pytestmark = pytest.mark.smoke


class TestCraftTrainer:
    """learn verb: usage, trainer-absent gate, trainer-present learn+persist."""

    async def test_ct1_learn_no_arg_shows_usage(self, harness):
        await craft_trainer.ct1_learn_no_arg_shows_usage(harness)

    async def test_ct2_learn_trainer_absent_refused(self, harness):
        await craft_trainer.ct2_learn_trainer_absent_refused(harness)

    async def test_ct3_learn_with_trainer_present(self, harness):
        await craft_trainer.ct3_learn_with_trainer_present(harness)
