# -*- coding: utf-8 -*-
"""
tests/test_seed_pocket_economy_reachable.py — regression guard for the CW
economy-access blocker (drop: seed-pocket economy linkage, 2026-06-24).

A new Clone-Wars player who graduates the LEGACY core tutorial lands in the
bootstrap seed-room pocket — DB rooms 1/2/3 (Landing Pad - Mos Eisley
Spaceport / Mos Eisley Street / Chalmun's Cantina), created by the schema in
db/database.py. build_mos_eisley links that pocket into the live Mos Eisley
map so a graduate can reach the market/cantina vendors.

The bug: that linking was gated on `era == "gcw"` — the RETIRED Galactic-Civil-
War era (T2.CW.gcw_retirement). Production runs on `clone_wars`, so the gate
was never true and the pocket stayed disconnected: graduates were stranded in
a vendorless 3-room pocket and the ENTIRE economy loop (buy/sell at a vendor)
was unreachable. Found by the 2026-06-23 normal-play E2E "economy" journey
(reachable rooms = ['Chalmun's Cantina', 'Landing Pad - Mos Eisley Spaceport',
'Mos Eisley Street'], all vendor=False).

The fix runs the seed-room linking for `clone_wars` too, with .get()-guarded
yaml-id lookups. This test builds the production CW world and asserts the seed
pocket reaches a real vendor NPC in the connected room graph.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import build_mos_eisley  # noqa: E402
from db.database import Database  # noqa: E402

# DB ids of the schema-bootstrap seed rooms (db/database.py seed INSERTs).
SEED_POCKET = (1, 2, 3)


def _is_vendor(ai_config_json: str) -> bool:
    try:
        ai = json.loads(ai_config_json or "{}")
    except (ValueError, TypeError):
        return False
    return bool(ai.get("vendor") or ai.get("vendor_kind"))


class TestSeedPocketEconomyReachable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _build_and_read():
            fd, tmp = tempfile.mkstemp(suffix="_seed_pocket.db")
            os.close(fd)
            os.remove(tmp)  # build creates it fresh
            await build_mos_eisley.build(db_path=tmp, era="clone_wars")

            db = Database(tmp)
            await db.connect()
            rooms = {r["id"]: r["name"]
                     for r in await db.fetchall("SELECT id, name FROM rooms")}
            exit_rows = await db.fetchall(
                "SELECT from_room_id, to_room_id FROM exits")
            npc_rows = await db.fetchall(
                "SELECT room_id, ai_config_json FROM npcs")
            await db.close()
            return rooms, exit_rows, npc_rows, tmp

        cls.rooms, exit_rows, npc_rows, cls.tmp_db = asyncio.run(_build_and_read())

        # Directed adjacency (exits are one-way rows; both directions are
        # written as separate rows by the builder).
        cls.adj: dict[int, list[int]] = {}
        for e in exit_rows:
            cls.adj.setdefault(e["from_room_id"], []).append(e["to_room_id"])

        cls.vendor_rooms = {n["room_id"] for n in npc_rows
                            if _is_vendor(n["ai_config_json"])}

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.tmp_db)
        except OSError:
            pass

    def _reachable_from(self, start: int) -> set[int]:
        seen = {start}
        q = deque([start])
        while q:
            cur = q.popleft()
            for nxt in self.adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        return seen

    def test_world_has_vendors(self):
        """Guard against a vacuous reachability assertion: the built world
        must actually contain vendor NPCs."""
        self.assertTrue(self.vendor_rooms,
                        "built CW world has no vendor NPCs at all")

    def test_seed_pocket_escapes_into_city(self):
        """Each bootstrap seed room must reach well beyond the 3-room pocket
        (the bug left it reaching only its own 3 rooms)."""
        for start in SEED_POCKET:
            reachable = self._reachable_from(start)
            self.assertGreater(
                len(reachable), len(SEED_POCKET),
                f"seed room {start} ({self.rooms.get(start)!r}) is walled "
                f"into a {len(reachable)}-room pocket: "
                f"{sorted(self.rooms.get(r) for r in reachable)}")

    def test_seed_pocket_reaches_a_vendor(self):
        """The core regression: a tutorial graduate standing in the seed
        pocket can reach at least one vendor NPC -> the economy loop is
        playable."""
        for start in SEED_POCKET:
            reachable = self._reachable_from(start)
            reachable_vendors = self.vendor_rooms & reachable
            self.assertTrue(
                reachable_vendors,
                f"seed room {start} ({self.rooms.get(start)!r}) reaches NO "
                f"vendor — economy loop unreachable for a tutorial graduate")


if __name__ == "__main__":
    unittest.main()
