# -*- coding: utf-8 -*-
"""
tests/test_qa_m1_l4_land_safety.py — QA M1 + L4 regression.

**M1 (QA_FINDINGS_2026-06-16.md M1):** A pilot who spends credits in space and
lands with < 25cr (the base docking fee) is permanently stranded — LandCommand
refused with a hard error and returned without docking. Fix: emergency landing
allows docking even with 0cr (no fee collected), warning the pilot instead.

**L4 (QA_FINDINGS_2026-06-16.md L4):** LandCommand had no ``in_hyperspace``
guard. A ship mid-jump could set ``docked_at`` while ``in_hyperspace=True``
simultaneously — an impossible state that would mis-teleport on the next tick.
Fix: LandCommand rejects landing attempts while in hyperspace.
"""
from __future__ import annotations

import inspect
import json
import os
import sys

import pytest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

pytestmark = pytest.mark.smoke


# ── Source inspection drift-guards ──────────────────────────────────────────

class TestL4HyperspaceGuardPresent:
    """LandCommand.execute must guard in_hyperspace before attempting to land."""

    def test_landcommand_checks_in_hyperspace(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "in_hyperspace" in src, (
            "LandCommand.execute does not check in_hyperspace — "
            "landing mid-jump sets docked_at AND in_hyperspace=True simultaneously "
            "(impossible ship state; QA L4)")

    def test_landcommand_hyperspace_guard_returns_early(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "Cannot land while in hyperspace" in src, (
            "LandCommand.execute is missing the 'Cannot land while in hyperspace' "
            "rejection message — the hyperspace guard may have been removed (QA L4)")


class TestM1EmergencyLandingPresent:
    """LandCommand.execute must allow emergency landing when credits < docking fee."""

    def test_no_hard_refusal_on_insufficient_credits(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "Not enough credits for docking fee" not in src, (
            "LandCommand.execute hard-refuses landing on insufficient credits — "
            "pilot becomes permanently stranded in space (QA M1). "
            "Replace with emergency landing (allow docking, warn, charge what's available).")

    def test_emergency_landing_message_present(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "Emergency landing" in src, (
            "LandCommand.execute has no 'Emergency landing' path — "
            "pilots with < docking fee are still stranded (QA M1)")

    def test_actual_fee_used_not_hard_docking_fee(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "actual_fee" in src, (
            "LandCommand.execute does not use an 'actual_fee' variable — "
            "the emergency-landing path that charges min(credits, docking_fee) "
            "appears to be absent (QA M1)")

    def test_success_message_uses_actual_fee(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "Docking fee: {actual_fee}" in src, (
            "LandCommand.execute success message does not use {actual_fee} — "
            "emergency landings would report the wrong fee (QA M1)")


# ── Harness regression: normal land still works after changes ────────────────

async def _first_docked_ship(h):
    rows = await h.db.fetchall(
        "SELECT id, name, docked_at FROM ships "
        "WHERE docked_at IS NOT NULL ORDER BY id"
    )
    assert rows, "harness world has no docked ships"
    r = dict(rows[0])
    return int(r["id"]), r["name"], int(r["docked_at"])


async def _ship_docked_at(h, ship_id):
    rows = await h.db.fetchall(
        "SELECT docked_at FROM ships WHERE id = ?", (ship_id,)
    )
    return dict(rows[0]).get("docked_at")


class TestLandCommandRegression:
    """Normal launch+land arc still works (regression after M1/L4 changes)."""

    async def test_land_with_sufficient_credits_docks_ship(self, harness):
        ship_id, ship_name, dock_room = await _first_docked_ship(harness)
        token = ship_name.split()[0].lower()
        s = await harness.login_as("M1L4Reg", room_id=dock_room, credits=5000)
        await harness.cmd(s, f"board {token}")
        await harness.cmd(s, "pilot")
        await harness.cmd(s, "launch")
        await harness.cmd(s, "land")
        docked_at = await _ship_docked_at(harness, ship_id)
        assert docked_at is not None, (
            "Ship did not re-dock after launch+land with sufficient credits — "
            "regression in LandCommand (QA M1/L4 changes broke normal landing)")
        await harness.cmd(s, "vacate")
