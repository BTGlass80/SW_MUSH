# -*- coding: utf-8 -*-
"""
tests/test_qa_housing_checkout_guest_2026_06_23.py — QA break-it regression
(housing sweep, 2026-06-23).

#1 [CRASH+CORRUPTION, BLOCKER] checkout_room crashed on EVERY vacate path. It
   deleted rooms + player_housing BEFORE clearing the FK cross-references
   (characters.home_room_id -> rooms.id, rooms.housing_id -> player_housing.id),
   so the room DELETE failed silently and the player_housing DELETE then crashed
   UNCAUGHT (FOREIGN KEY constraint failed). The deposit refund had already
   fired -> credit injected with no state cleanup. Blast radius: checkout / sell
   / @evict / faction-quarter revoke / rent-eviction tick. Fix: clear
   home_room_id + rooms.housing_id BEFORE the deletes (mirrors sell_shopfront).

#2 [CORRUPTION] is_on_guest_list always returned False — `char_id in guests`
   where guests is a list of {"id","name"} dicts (int-in-list-of-dicts is always
   False), so invited guests were permanently locked out. Fix: match on g["id"].

The harness DB runs PRAGMA foreign_keys=ON, so the checkout test genuinely
reproduces the FK crash on the unfixed code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import housing  # noqa: E402

HOUSING_SRC = (PROJECT_ROOT / "engine" / "housing.py").read_text(encoding="utf-8")


async def _make_lot(harness, *, planet="tatooine", label="Test Lot",
                    security="contested", max_homes=5):
    room_id = await harness.db.create_room(
        name=label, desc_short="A test housing lobby.",
        desc_long="A test housing lobby.", zone_id=None,
        properties=json.dumps({"security": security}),
    )
    cur = await harness.db.execute(
        """INSERT INTO housing_lots
           (room_id, planet, label, security, max_homes, current_homes)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (room_id, planet, label, security, max_homes),
    )
    await harness.db.commit()
    return cur.lastrowid, room_id


# ── #2 is_on_guest_list (pure) ────────────────────────────────────────────
class TestGuestListMembership:
    def test_member_dicts_are_recognized(self):
        h = {"guest_list": json.dumps(
            [{"id": 42, "name": "Alice"}, {"id": 99, "name": "Bob"}])}
        assert housing.is_on_guest_list(h, 42) is True
        assert housing.is_on_guest_list(h, 99) is True

    def test_non_member_is_rejected(self):
        h = {"guest_list": json.dumps([{"id": 42, "name": "Alice"}])}
        assert housing.is_on_guest_list(h, 7) is False

    def test_empty_or_missing_list(self):
        assert housing.is_on_guest_list({"guest_list": "[]"}, 42) is False
        assert housing.is_on_guest_list({}, 42) is False


# ── #1 checkout_room FK ordering (BLOCKER) ────────────────────────────────
class TestCheckoutFKOrdering:
    async def test_checkout_after_rent_no_fk_crash(self, harness):
        lot_id, _ = await _make_lot(harness, label="CheckoutLot")
        s = await harness.login_as("Checkouter", credits=5000)
        cid = s.character["id"]
        char = dict(s.character)
        rent = await housing.rent_room(harness.db, char, lot_id)
        assert rent["ok"], rent
        # reload (rent set home_room_id in the DB)
        char = dict((await harness.db.fetchall(
            "SELECT * FROM characters WHERE id = ?", (cid,)))[0])
        # THE BLOCKER FIX: this used to raise IntegrityError (FK) and surface
        # "An error occurred"; it must now vacate cleanly.
        result = await housing.checkout_room(harness.db, char)
        assert result.get("ok"), result
        rows = await harness.db.fetchall(
            "SELECT id FROM player_housing WHERE char_id = ?", (cid,))
        assert not rows, "checkout must delete the housing record"
        crow = dict((await harness.db.fetchall(
            "SELECT home_room_id FROM characters WHERE id = ?", (cid,)))[0])
        assert crow["home_room_id"] is None, "checkout must clear home_room_id"

    def test_clears_fk_refs_before_deletes(self):
        # structural guard: the FK NULL-clear must precede the room teardown.
        # The teardown migrated to the canonical db.delete_room() in the housing-
        # telemetry merge (removes exits + the room FK-safely); the multi-home
        # change keeps the home_room_id clear CONDITIONAL (WHERE ... IN deleted
        # rooms), so a multi-home owner selling one home keeps the others' recall.
        i = HOUSING_SRC.index("async def checkout_room")
        j = HOUSING_SRC.index("\nasync def ", i + 1)
        body = HOUSING_SRC[i:j]
        clear = body.find(
            "UPDATE characters SET home_room_id = NULL WHERE home_room_id IN")
        del_rooms = body.find("await db.delete_room(")
        del_ph = body.find("DELETE FROM player_housing WHERE id = ?")
        assert clear != -1, "checkout_room missing the conditional home_room_id pre-clear"
        assert del_rooms != -1 and del_ph != -1, \
            "checkout_room must tear rooms down via db.delete_room then delete player_housing"
        assert clear < del_rooms < del_ph, \
            "FK clear must precede delete_room / DELETE FROM player_housing"
