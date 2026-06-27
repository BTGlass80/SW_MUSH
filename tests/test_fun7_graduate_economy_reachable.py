# -*- coding: utf-8 -*-
"""
tests/test_fun7_graduate_economy_reachable.py — regression guard for the CW
PROFESSION-CHAIN graduate reward-loop (drop: fun7-reward-loop, 2026-06-27).

Sibling to test_seed_pocket_economy_reachable.py, which guards only the LEGACY
core-tutorial seed pocket. The CW profession chains are a SEPARATE path: each
chain's graduation.drop_room used to be a 0-exit `tutorial_zone` pocket with no
vendor, so a graduate landed with ~400-800 credits, could not reach any shop,
AND (7 of 8) was physically stranded (no exits) — a graduation-stranding
soft-lock found by the 2026-06-27 fun re-run.

The fix retargets each profession chain's drop_room to a live navigable hub and
authors starter vendors (npcs_drop_fun7_starter_vendors.yaml) so every graduate
both escapes into the world AND can reach a vendor to spend credits. This test
builds the production CW world, resolves each chain's drop_room slug to a room,
and asserts reachability to a vendor NPC (the two Jedi chains are whitelisted
from the vendor bar — Jedi gear comes through the questline, not a buyable
vendor — but must still not be stranded).
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

CHAINS_YAML = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "tutorials", "chains.yaml")

# New-player profession chains whose graduate MUST reach a vendor (the reward
# loop). The T5 master chains + Jedi chains are out of this bar (see below).
PROFESSION_CHAINS = {
    "republic_soldier", "republic_intelligence", "separatist_commando",
    "separatist_agent", "bounty_hunter", "smuggler", "shipwright_trader",
}
# Graduate to a live room but NOT held to the buyable-vendor bar (Jedi gear is
# questline-granted, not vendor-bought). Still must not be a 0-exit dead-end.
VENDOR_EXEMPT_CHAINS = {"jedi_path", "jedi_path_independent"}


def _is_vendor(ai_config_json: str) -> bool:
    try:
        ai = json.loads(ai_config_json or "{}")
    except (ValueError, TypeError):
        return False
    return bool(ai.get("vendor") or ai.get("vendor_kind"))


def _chain_drop_rooms() -> dict:
    """chain_id -> graduation.drop_room slug, parsed from chains.yaml."""
    import yaml
    with open(CHAINS_YAML, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    out = {}
    # chains.yaml top-level is a list of chain dicts (or under a key); handle both.
    chains = doc if isinstance(doc, list) else (
        doc.get("chains") or doc.get("tutorial_chains") or [])
    for ch in chains:
        if not isinstance(ch, dict):
            continue
        cid = ch.get("chain_id")
        grad = ch.get("graduation") or {}
        room = grad.get("drop_room")
        if cid and room:
            out[cid] = room
    return out


class TestFun7GraduateEconomyReachable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def _build_and_read():
            fd, tmp = tempfile.mkstemp(suffix="_fun7.db")
            os.close(fd)
            os.remove(tmp)
            await build_mos_eisley.build(db_path=tmp, era="clone_wars")
            db = Database(tmp)
            await db.connect()
            rooms = await db.fetchall(
                "SELECT id, name, json_extract(properties,'$.slug') AS slug "
                "FROM rooms")
            exit_rows = await db.fetchall(
                "SELECT from_room_id, to_room_id FROM exits")
            npc_rows = await db.fetchall(
                "SELECT room_id, ai_config_json FROM npcs")
            await db.close()
            return rooms, exit_rows, npc_rows, tmp

        cls.rooms, exit_rows, npc_rows, cls.tmp_db = asyncio.run(_build_and_read())
        cls.id_to_name = {r["id"]: r["name"] for r in cls.rooms}
        cls.slug_to_id = {r["slug"]: r["id"] for r in cls.rooms if r["slug"]}
        cls.adj = {}
        for e in exit_rows:
            cls.adj.setdefault(e["from_room_id"], []).append(e["to_room_id"])
        cls.vendor_rooms = {n["room_id"] for n in npc_rows
                            if _is_vendor(n["ai_config_json"])}
        cls.drop_rooms = _chain_drop_rooms()

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.tmp_db)
        except OSError:
            pass

    def _reachable_from(self, start: int) -> set:
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
        self.assertTrue(self.vendor_rooms, "built CW world has no vendor NPCs")

    def test_profession_drop_rooms_resolve(self):
        """Every profession chain's graduation drop_room slug must resolve to a
        real built room (guards a typo'd retarget)."""
        for cid in PROFESSION_CHAINS | VENDOR_EXEMPT_CHAINS:
            slug = self.drop_rooms.get(cid)
            self.assertIsNotNone(slug, f"chain {cid} has no graduation.drop_room")
            self.assertIn(
                slug, self.slug_to_id,
                f"chain {cid} drop_room {slug!r} resolves to no built room")

    def test_profession_graduate_reaches_a_vendor(self):
        """THE regression: each profession-chain graduate can reach a vendor NPC
        from their drop_room — the reward loop (earn -> spend) is playable."""
        for cid in PROFESSION_CHAINS:
            slug = self.drop_rooms.get(cid)
            start = self.slug_to_id.get(slug)
            self.assertIsNotNone(start, f"{cid}: drop_room {slug!r} unresolved")
            reachable = self._reachable_from(start)
            self.assertTrue(
                self.vendor_rooms & reachable,
                f"chain {cid} graduate (drop_room {slug!r}, room {start}) "
                f"reaches NO vendor — reward loop unreachable")

    def test_no_profession_graduate_is_stranded(self):
        """No profession/Jedi graduate may land in a 0-exit dead-end (the
        original soft-lock: 7/8 pockets had zero exits)."""
        for cid in PROFESSION_CHAINS | VENDOR_EXEMPT_CHAINS:
            slug = self.drop_rooms.get(cid)
            start = self.slug_to_id.get(slug)
            if start is None:
                continue
            reachable = self._reachable_from(start)
            self.assertGreater(
                len(reachable), 1,
                f"chain {cid} graduate stranded in 0-exit room "
                f"{slug!r} ({self.id_to_name.get(start)!r})")


if __name__ == "__main__":
    unittest.main()
