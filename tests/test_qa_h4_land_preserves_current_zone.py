# -*- coding: utf-8 -*-
"""
tests/test_qa_h4_land_preserves_current_zone.py — QA finding H4 regression.

**The bug (QA_FINDINGS_2026-06-16.md H4):** `LandCommand` popped
``systems["current_zone"]`` on every land. But the docked trade surface
(``market`` / cargo ``buy`` / cargo ``sell``) resolves *which planet you are
docked at* through ``current_zone → ZONES[zone].planet``. With the zone gone,
the next docked trade read an **empty** planet:

  * ``get_planet_price(good, "")`` collapsed to a flat base price — the
    source-discount and demand-premium that make trade routes profitable never
    applied (every market quoted a flat 100%); and
  * ``SUPPLY_POOL.available("", key)`` was gated behind ``if planet:`` → the
    per-planet supply cap (the anti-infinite-farm sink) was **bypassed**.

So the planet-trade economy was silently dead in production while the green
suite stayed green (no end-to-end land→trade test existed).

**The fix:** stop clearing ``current_zone`` on land. A docked ship is already
excluded from all space traffic / targeting by the ``docked_at IS NOT NULL``
filter (``db.get_ships_in_space`` feeds ``npc_space_traffic``), so the zone
never needed clearing — and keeping it lets docked trade resolve the planet.
``launch`` overwrites ``current_zone`` fresh on the next departure.

These tests fly the proven boarding→pilot→launch→land arc against the live
in-process harness (the same path the space-flight smoke uses) and assert the
landed ship still carries a planet-resolvable ``current_zone``.
"""

import os
import sys
import json
import inspect

import pytest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

pytestmark = pytest.mark.smoke


async def _first_docked_ship(h):
    """Return (ship_id, name, dock_room_id) for the lowest-id docked ship."""
    rows = await h.db.fetchall(
        "SELECT id, name, docked_at FROM ships "
        "WHERE docked_at IS NOT NULL ORDER BY id"
    )
    assert rows, "harness world has no docked ships to fly"
    r = dict(rows[0])
    return int(r["id"]), r["name"], int(r["docked_at"])


async def _ship_current_zone(h, ship_id):
    rows = await h.db.fetchall(
        "SELECT systems FROM ships WHERE id = ?", (ship_id,)
    )
    systems = json.loads(dict(rows[0]).get("systems") or "{}")
    return systems.get("current_zone", "")


async def _ship_docked_at(h, ship_id):
    rows = await h.db.fetchall(
        "SELECT docked_at FROM ships WHERE id = ?", (ship_id,)
    )
    return dict(rows[0]).get("docked_at")


async def _fly_and_land(h, name):
    """Board the first docked ship, launch, then land. Return the ship_id and
    the (zone_after_launch, zone_after_land) it reported."""
    ship_id, ship_name, dock_room = await _first_docked_ship(h)
    token = ship_name.split()[0].lower()
    s = await h.login_as(name, room_id=dock_room, credits=5000)
    await h.cmd(s, f"board {token}")
    await h.cmd(s, "pilot")
    await h.cmd(s, "launch")
    zone_launch = await _ship_current_zone(h, ship_id)
    await h.cmd(s, "land")
    zone_land = await _ship_current_zone(h, ship_id)
    docked_at = await _ship_docked_at(h, ship_id)
    # Leave the seat free for sibling tests sharing the class-scoped harness.
    await h.cmd(s, "vacate")
    return ship_id, zone_launch, zone_land, docked_at


class TestH4LandPreservesCurrentZone:
    smoke_era = "clone_wars"

    async def test_launch_sets_a_current_zone(self, harness):
        """Sanity: launching from a dock assigns a non-empty orbit zone (the
        precondition the bug then destroyed)."""
        _id, zone_launch, _zone_land, _docked = await _fly_and_land(
            harness, "H4PreLaunch")
        assert zone_launch, (
            "launch did not assign a current_zone — flight precondition broken")

    async def test_land_preserves_current_zone(self, harness):
        """THE regression: after land the ship still carries the orbit zone it
        launched into (was popped → empty before the fix)."""
        _id, zone_launch, zone_land, docked_at = await _fly_and_land(
            harness, "H4Lander")
        assert docked_at is not None, "ship did not re-dock on land"
        assert zone_land, (
            "current_zone was cleared on land — docked trade can no longer "
            "resolve the planet (QA H4 regression)")
        assert zone_land == zone_launch, (
            f"current_zone changed across land: launched into {zone_launch!r}, "
            f"docked with {zone_land!r}")

    async def test_docked_zone_resolves_to_a_planet(self, harness):
        """The thing the trade code actually needs: the landed ship's
        current_zone resolves to a real planet via the live ZONES graph, so
        market/buy/sell price against that planet (not a flat-100% empty)."""
        from engine.npc_space_traffic import ZONES
        _id, _zl, zone_land, _docked = await _fly_and_land(
            harness, "H4Trader")
        zone_obj = ZONES.get(zone_land)
        assert zone_obj is not None, (
            f"landed current_zone {zone_land!r} is not a known zone")
        assert zone_obj.planet, (
            f"landed zone {zone_land!r} has no planet — trade would read an "
            f"empty planet and quote flat 100% / bypass the supply cap")


class TestH4LandCommandSourceGuard:
    """Cheap drift-guard pinning the specific bug: the LandCommand body must not
    re-introduce a ``current_zone`` pop. Catches a well-meaning future 'cleanup'
    that would silently kill planet trade again without needing a harness boot."""

    def test_landcommand_does_not_pop_current_zone(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert '.pop("current_zone"' not in src and \
               ".pop('current_zone'" not in src, (
            "LandCommand pops current_zone again — this re-breaks docked "
            "planet-trade pricing + the supply cap (QA H4). A docked ship is "
            "already excluded from traffic by docked_at; keep current_zone.")

    def test_landcommand_documents_why_zone_is_kept(self):
        from parser.space_commands import LandCommand
        src = inspect.getsource(LandCommand.execute)
        assert "current_zone" in src, (
            "expected the H4 rationale comment referencing current_zone in "
            "LandCommand.execute")
