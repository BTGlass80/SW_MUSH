# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/give_command.py — end-to-end `give` command.

`give <item> to <player-or-NPC>` is a one-way item hand-off (distinct
from `trade`, which is two-party/consented/taxed). These scenarios
drive it through the live harness with real sessions:

* **GV-1** — give an item to another PC in the room: it leaves the
             giver's inventory and lands in the recipient's.
* **GV-2** — `give <n> credits …` redirects to `trade` (the taxed,
             consented credit channel) and moves nothing.
* **GV-3** — giving to yourself is refused.
* **GV-4** — giving to someone not present says so cleanly.
* **GV-5** — give an item to an NPC: it leaves the giver (the NPC
             accepts it) — the mechanism the Smuggler chain's
             "give crate to Dyn" step rides.
"""
from __future__ import annotations

import json


async def _seed_item(h, char_id: int, key: str, name: str) -> None:
    await h.db.add_to_inventory(char_id, {"key": key, "name": name})


def _keys(inv) -> set:
    return {
        (it.get("key") or "")
        for it in (inv or []) if isinstance(it, dict)
    }


# ── GV-1 — PC → PC item transfer ─────────────────────────────────────


async def gv_1_give_item_to_player(h):
    giver = await h.login_as("Gv1Giver", room_id=1)
    recv = await h.login_as("Gv1Recv", room_id=1)
    await _seed_item(h, giver.character["id"], "smoke_widget",
                     "Smoke Widget")

    out = await h.cmd(giver, "give Smoke Widget to Gv1Recv")
    out_lc = out.lower()
    assert "traceback" not in out_lc, f"`give` raised: {out[:400]!r}"
    assert "give" in out_lc and "smoke widget" in out_lc, (
        f"`give` did not confirm the hand-off. Output: {out[:300]!r}")

    giver_keys = _keys(await h.db.get_inventory(giver.character["id"]))
    recv_keys = _keys(await h.db.get_inventory(recv.character["id"]))
    assert "smoke_widget" not in giver_keys, (
        "item should have left the giver's inventory")
    assert "smoke_widget" in recv_keys, (
        "item should have landed in the recipient's inventory")


# ── GV-2 — credits redirect to `trade` ───────────────────────────────


async def gv_2_credits_redirect_to_trade(h):
    giver = await h.login_as("Gv2Giver", room_id=1, credits=1000)
    await h.login_as("Gv2Recv", room_id=1)

    out = await h.cmd(giver, "give 500 credits to Gv2Recv")
    out_lc = out.lower()
    assert "traceback" not in out_lc
    assert "trade" in out_lc, (
        f"credit give should redirect to `trade`. Output: {out[:300]!r}")
    # Nothing moved: giver keeps their credits.
    char = await h.get_char(giver.character["id"])
    assert int(char.get("credits") or 0) == 1000, (
        "no credits should move on a redirected give")


# ── GV-3 — give to self refused ──────────────────────────────────────


async def gv_3_give_to_self_refused(h):
    solo = await h.login_as("Gv3Solo", room_id=1)
    await _seed_item(h, solo.character["id"], "gv3_widget", "Gv3 Widget")

    out = await h.cmd(solo, "give Gv3 Widget to Gv3Solo")
    out_lc = out.lower()
    assert "traceback" not in out_lc
    assert "yourself" in out_lc, (
        f"self-give should be refused. Output: {out[:300]!r}")
    # Item retained.
    assert "gv3_widget" in _keys(
        await h.db.get_inventory(solo.character["id"]))


# ── GV-4 — give to absent target ─────────────────────────────────────


async def gv_4_give_to_absent_target(h):
    solo = await h.login_as("Gv4Solo", room_id=1)
    await _seed_item(h, solo.character["id"], "gv4_widget", "Gv4 Widget")

    out = await h.cmd(solo, "give Gv4 Widget to Nobody_Here_42")
    out_lc = out.lower()
    assert "traceback" not in out_lc
    assert "don't see" in out_lc or "do not see" in out_lc, (
        f"give to absent target should say so. Output: {out[:300]!r}")
    # Item retained (nothing transferred).
    assert "gv4_widget" in _keys(
        await h.db.get_inventory(solo.character["id"]))


# ── GV-5 — give item to an NPC (hand-off) ────────────────────────────


async def gv_5_give_item_to_npc(h):
    giver = await h.login_as("Gv5Giver", room_id=1)
    await h.db.create_npc(
        name="DynSmoke",
        room_id=1,
        species="Twi'lek",
        description="A smoke-test underworld contact.",
        char_sheet_json=json.dumps({"skills": {}}),
        ai_config_json=json.dumps({}),
    )
    await _seed_item(h, giver.character["id"], "smoke_crate",
                     "Smoke Crate")

    out = await h.cmd(giver, "give Smoke Crate to DynSmoke")
    out_lc = out.lower()
    assert "traceback" not in out_lc, f"`give` to NPC raised: {out[:400]!r}"
    assert "hand" in out_lc and "smoke crate" in out_lc, (
        f"give-to-NPC should narrate the hand-off. Output: {out[:300]!r}")
    # Item left the giver (the NPC accepted it).
    assert "smoke_crate" not in _keys(
        await h.db.get_inventory(giver.character["id"])), (
        "item should leave the giver when handed to an NPC")
