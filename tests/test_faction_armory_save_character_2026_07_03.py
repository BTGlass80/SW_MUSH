# -*- coding: utf-8 -*-
"""
tests/test_faction_armory_save_character_2026_07_03.py

Regression guard for the phantom ``db.update_character`` API call.

Four runtime sites called ``db.update_character(char_id, inventory=...)`` —
a method that does **not** exist on ``db.database.Database`` (there is no
``__getattr__`` forwarding; the real writer is ``save_character``). Every
call raised ``AttributeError`` at runtime:

  * ``engine.territory.armory_deposit_item``  (faction armory deposit)
  * ``engine.territory.armory_withdraw_item``  (faction armory withdraw <item>)
  * ``engine.territory.armory_withdraw_resources`` (faction armory withdraw <res> <qty>)
  * ``engine.housing.attempt_theft``  (home-theft success path)

The armory paths became live-reachable when the region-ownership gate was
un-stubbed (QA 2026-06-21, see ``parser/faction_commands._cmd_armory``) — so
``faction armory deposit/withdraw`` has crashed for every player since. The
housing site was worse: the theft-success branch removes the trophy from the
home and **commits** that removal before the crash, so a successful theft
*destroyed* the item (gone from the home, never credited to the thief).

No test exercised any of these functions, which is why the crash passed the
green suite. Fix: all four sites now call ``db.save_character(char_id,
inventory=...)`` — the established idiom used across ``engine/buildings.py``
and ``engine/communal_objective_runtime.py``.

Guards:
  1. Behavioral round-trip of the three armory fns against a real in-memory
     DB — each would raise AttributeError before the fix.
  2. API existence — Database has ``save_character`` and NOT ``update_character``.
  3. Source guard — no ``db.update_character(`` remains in the two engine files
     (pins the housing site, which is awkward to drive end-to-end here).

Drop label: ``faction-armory-save-character``.
"""
import asyncio
import json
import os

import engine.territory as territory
from engine.territory import (
    armory_deposit_item,
    armory_withdraw_item,
    armory_withdraw_resources,
    ensure_territory_schema,
    _get_org_storage,
    _save_org_storage,
)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(coro):
    return asyncio.run(coro)


# ─── fixtures ─────────────────────────────────────────────────────────────

async def _fresh_db():
    """In-memory DB with core + housing + territory schema."""
    from db.database import Database
    from engine.housing import ensure_schema as _hs_schema

    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await _hs_schema(db)
    await ensure_territory_schema(db)
    return db


async def _seed_room_in_region(db, region_slug: str) -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long, wilderness_region_id) "
        "VALUES ('Owned Outpost', 1, '', '', ?)",
        (region_slug,),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_char(db, room_id: int, inv: dict) -> dict:
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts (username, password_hash, email) "
        "VALUES ('t', 'h', 't@e.com')"
    )
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(account_id, name, species, room_id, credits, faction_id, inventory) "
        "VALUES (1, 'Trooper', 'Human', ?, 1000, 'republic', ?)",
        (room_id, json.dumps(inv)),
    )
    await db._db.commit()
    return await db.get_character(cur.lastrowid)


async def _seed_org(db, code: str = "republic") -> None:
    await db._db.execute(
        "INSERT INTO organizations "
        "(code, name, org_type, director_managed, treasury, properties) "
        "VALUES (?, 'Galactic Republic', 'faction', 0, 0, '{}')",
        (code,),
    )
    await db._db.commit()


async def _always_owned(db, region_slug, org_code):  # gate stand-in
    return True


class _GatePatch:
    """Force the armory region-ownership gate open for the scenario."""

    def __enter__(self):
        self._orig = territory.is_region_owned_by
        territory.is_region_owned_by = _always_owned
        return self

    def __exit__(self, *exc):
        territory.is_region_owned_by = self._orig
        return False


# ─── behavioral: deposit ──────────────────────────────────────────────────

def test_armory_deposit_persists_and_moves_item():
    """Deposit succeeds, removes the item from the char's *persisted*
    inventory, and lands it in org storage — pre-fix this raised
    AttributeError on db.update_character."""
    async def scenario():
        db = await _fresh_db()
        region = "kuat_lowlands"
        room_id = await _seed_room_in_region(db, region)
        item = {"key": "blaster_pistol", "name": "Blaster Pistol"}
        char = await _seed_char(db, room_id, {"items": [item], "resources": []})
        await _seed_org(db, "republic")

        with _GatePatch():
            res = await armory_deposit_item(db, char, "republic", "blaster")

        assert res["ok"] is True, res
        reloaded = await db.get_character(char["id"])
        inv = json.loads(reloaded["inventory"])
        assert not any(
            "blaster" in it.get("key", "").lower() for it in inv.get("items", [])
        ), "item should be gone from the persisted char inventory"
        storage = await _get_org_storage(db, "republic")
        assert any(
            it.get("key") == "blaster_pistol" for it in storage["items"]
        ), "item should now be in org armory storage"

    _run(scenario())


# ─── behavioral: withdraw item ────────────────────────────────────────────

def test_armory_withdraw_item_persists_to_char():
    async def scenario():
        db = await _fresh_db()
        region = "kuat_lowlands"
        room_id = await _seed_room_in_region(db, region)
        char = await _seed_char(db, room_id, {"items": [], "resources": []})
        await _seed_org(db, "republic")
        # pre-seed the armory with an item
        await _save_org_storage(
            db, "republic",
            {"items": [{"key": "vibroblade", "name": "Vibroblade"}], "resources": []},
        )

        with _GatePatch():
            res = await armory_withdraw_item(db, char, "republic", "vibroblade")

        assert res["ok"] is True, res
        reloaded = await db.get_character(char["id"])
        inv = json.loads(reloaded["inventory"])
        assert any(
            it.get("key") == "vibroblade" for it in inv.get("items", [])
        ), "withdrawn item should be persisted into char inventory"
        storage = await _get_org_storage(db, "republic")
        assert not any(
            it.get("key") == "vibroblade" for it in storage["items"]
        ), "item should be gone from armory storage"

    _run(scenario())


# ─── behavioral: withdraw resources ───────────────────────────────────────

def test_armory_withdraw_resources_persists_to_char():
    async def scenario():
        db = await _fresh_db()
        region = "kuat_lowlands"
        room_id = await _seed_room_in_region(db, region)
        char = await _seed_char(db, room_id, {"items": [], "resources": []})
        await _seed_org(db, "republic")
        await _save_org_storage(
            db, "republic",
            {"items": [],
             "resources": [{"type": "durasteel", "quantity": 10, "quality": 55}]},
        )

        with _GatePatch():
            res = await armory_withdraw_resources(
                db, char, "republic", "durasteel", 4
            )

        assert res["ok"] is True, res
        reloaded = await db.get_character(char["id"])
        inv = json.loads(reloaded["inventory"])
        got = [r for r in inv.get("resources", []) if r.get("type") == "durasteel"]
        assert got and got[0]["quantity"] == 4, "resource should be persisted to char"
        storage = await _get_org_storage(db, "republic")
        left = [r for r in storage["resources"] if r.get("type") == "durasteel"]
        assert left and left[0]["quantity"] == 6, "armory should retain the remainder"

    _run(scenario())


# ─── API existence guard ──────────────────────────────────────────────────

def test_database_has_save_character_not_update_character():
    from db.database import Database
    assert hasattr(Database, "save_character"), "save_character is the real writer"
    assert not hasattr(Database, "update_character"), (
        "update_character does not exist on Database — no code may call it"
    )


# ─── source guard: no phantom API remains ─────────────────────────────────

def test_no_update_character_calls_remain():
    for rel in ("engine/territory.py", "engine/housing.py"):
        path = os.path.join(_REPO_ROOT, rel)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "db.update_character(" not in src, (
            f"{rel} still calls the phantom db.update_character(...)"
        )
