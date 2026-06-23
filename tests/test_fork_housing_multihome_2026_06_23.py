# -*- coding: utf-8 -*-
"""
tests/test_fork_housing_multihome_2026_06_23.py — multi-home fork.

Resolves HOUSING.single_home_only (Brian 2026-06-23: "4 homes is good"). Before
this, purchase_home BLOCKED any 2nd Tier-3 home ("You already own a home"), and
the per-planet constants (MAX_TIER3_PER_PLANET / MAX_TIER3_TOTAL) were dead.

This wires the real cap (own up to MAX_TIER3_TOTAL homes) and makes the extra
homes usable: the home OPERATIONS (storage / trophies / checkout / sell) resolve
the home the player is STANDING IN via engine.housing.resolve_active_home,
falling back to their most-recent home (so a single-home owner is unaffected).
Buying another home no longer evicts an existing Tier-3 (only a Tier 1/2 rental
is rolled up). Per-planet capping is intentionally not enforced -- player_housing
has no planet column to filter on; the total cap is the limit.

Run: python -m pytest tests/test_fork_housing_multihome_2026_06_23.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402


async def _make_lot(harness, *, planet="tatooine", label="MH Lot"):
    room_id = await harness.db.create_room(
        name=label, desc_short="A test housing lobby.",
        desc_long="A test housing lobby.", zone_id=None,
        properties=json.dumps({"security": "contested"}),
    )
    cur = await harness.db.execute(
        """INSERT INTO housing_lots
           (room_id, planet, label, security, max_homes, current_homes)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (room_id, planet, label, "contested", 5),
    )
    await harness.db.commit()
    return cur.lastrowid, room_id


async def _buy(harness, char, planet, label):
    lot_id, _ = await _make_lot(harness, planet=planet, label=label)
    return await housing.purchase_home(harness.db, char, lot_id, "small")


class TestMultiHomeCap:

    async def test_can_own_up_to_the_total_cap(self, harness):
        s = await harness.login_as("MultiHome", credits=200_000)
        char = dict(s.character)
        planets = ["tatooine", "coruscant", "nar_shaddaa", "corellia"]
        for i in range(housing.MAX_TIER3_TOTAL):
            r = await _buy(harness, char, planets[i % len(planets)], f"Lot{i}")
            assert r["ok"] is True, f"home {i + 1} should succeed: {r.get('msg')}"
        homes = await housing.get_homes(harness.db, char["id"])
        assert len(homes) == housing.MAX_TIER3_TOTAL

    async def test_one_over_the_cap_is_refused(self, harness):
        s = await harness.login_as("MultiHomeCap", credits=200_000)
        char = dict(s.character)
        for i in range(housing.MAX_TIER3_TOTAL):
            assert (await _buy(harness, char, "tatooine", f"C{i}"))["ok"] is True
        over = await _buy(harness, char, "tatooine", "OneTooMany")
        assert over["ok"] is False
        assert "maximum" in over["msg"].lower()
        homes = await housing.get_homes(harness.db, char["id"])
        assert len(homes) == housing.MAX_TIER3_TOTAL, "the refused buy must not add a home"


class TestNoEvictionOnSecondBuy:

    async def test_buying_a_second_home_keeps_the_first(self, harness):
        s = await harness.login_as("NoEvict", credits=200_000)
        char = dict(s.character)
        r1 = await _buy(harness, char, "tatooine", "First")
        assert r1["ok"] is True
        homes_after_1 = await housing.get_homes(harness.db, char["id"])
        first_id = homes_after_1[0]["id"]

        r2 = await _buy(harness, char, "coruscant", "Second")
        assert r2["ok"] is True
        homes_after_2 = await housing.get_homes(harness.db, char["id"])
        ids = {h["id"] for h in homes_after_2}
        assert len(homes_after_2) == 2, "the first home must survive the second buy"
        assert first_id in ids, "the first home was evicted — multi-home regression"


class TestResolveActiveHome:

    async def test_targets_the_home_you_are_standing_in(self, harness):
        s = await harness.login_as("ActiveHome", credits=200_000)
        char = dict(s.character)
        await _buy(harness, char, "tatooine", "HomeA")
        await _buy(harness, char, "coruscant", "HomeB")
        homes = await housing.get_homes(harness.db, char["id"])   # most-recent first
        latest, oldest = homes[0], homes[1]
        oldest_room = json.loads(oldest["room_ids"])[0]

        # standing inside the older home -> operations target THAT home
        char_in_old = dict(char)
        char_in_old["room_id"] = oldest_room
        active = await housing.resolve_active_home(harness.db, char_in_old)
        assert active["id"] == oldest["id"], "should resolve the home you're inside"

        # standing nowhere special -> falls back to the most-recent home
        char_away = dict(char)
        char_away["room_id"] = -999
        active2 = await housing.resolve_active_home(harness.db, char_away)
        assert active2["id"] == latest["id"], "fallback should be the most-recent home"

    async def test_single_home_owner_unaffected(self, harness):
        s = await harness.login_as("OneHome", credits=200_000)
        char = dict(s.character)
        await _buy(harness, char, "tatooine", "Only")
        only = (await housing.get_homes(harness.db, char["id"]))[0]
        char_away = dict(char)
        char_away["room_id"] = -999
        active = await housing.resolve_active_home(harness.db, char_away)
        assert active["id"] == only["id"]
