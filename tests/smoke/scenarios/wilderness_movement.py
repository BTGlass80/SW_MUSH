# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/wilderness_movement.py — Wilderness natural
entry/exit smoke scenarios (W-MV-1, W-MV-2).

End-to-end verification of the natural wilderness entry/exit
pathway through the parser. Pre-W.2.4 the entire wilderness
combat surface was gated; W.2.4 lifted the combat gate but the
underlying movement surface — `_try_wilderness_entry` in
parser/builtin_commands.py + `find_entry_edges_for_room` in
engine/wilderness_movement.py — was assumed working at the unit
level. These scenarios exercise the full pipeline:

  player types `east` from edge room
  → builtin_commands.MoveCommand picks up the direction
  → falls into the no-exit branch
  → calls _try_wilderness_entry
  → matches entry edge
  → transitions char into wilderness at coords
  → broadcasts departure to old room
  → ships the room description / arrival

A regression that broke any link in this chain (room without slug,
edge schema drift, sentinel room missing, character state not
persisted) would be invisible to the wilderness_combat scenarios,
which all use `_drop_into_wilderness` (a synthetic DB-column-write
that bypasses the parser pipeline entirely).

Scenarios
=========

* **W-MV-1** — Natural wilderness entry: PC at
  `jundland_dune_sea_edge`, types `east`, lands in the Dune Sea
  wilderness at coords (0, 20) with `wilderness_region_slug` set.

* **W-MV-2** — Natural wilderness exit: PC standing on coords
  (0, 20) of the Dune Sea, types `west`, returns to the
  sentinel/edge room with `wilderness_region_slug` cleared.

Notes
=====

* Both scenarios assume CW era (the default) and the Dune Sea
  region defined in
  `data/worlds/clone_wars/wilderness/dune_sea.yaml`.

* The edge tuple (room=`jundland_dune_sea_edge`, direction=east,
  coords=(0, 20)) is the only Dune Sea entry edge in the corpus
  as of May 19 2026. If additional edges are added later,
  additional scenarios should pin them. For now, this one edge
  is enough to exercise the pipeline.

* W-MV-1 verifies the entry event WITHOUT touching combat, so
  a regression that broke wilderness movement specifically (not
  combat) would be caught here, distinct from W-CMB-1 (which
  uses synthetic entry).
"""
from __future__ import annotations

import asyncio


# Region / edge constants from
# data/worlds/clone_wars/wilderness/dune_sea.yaml
SENTINEL_SLUG = "jundland_dune_sea_edge"
ENTRY_DIRECTION = "east"
EXIT_DIRECTION = "west"
ENTRY_COORDS = (0, 20)
REGION_SLUG = "tatooine_dune_sea"


# ──────────────────────────────────────────────────────────────────────────
# W-MV-1 — Natural wilderness entry
# ──────────────────────────────────────────────────────────────────────────


async def w_mv_1_natural_entry(h):
    """W-MV-1 — Player types `east` from `jundland_dune_sea_edge`,
    transitions into the Dune Sea wilderness at the entry coords.

    Pins the full natural-entry pipeline through the parser. A
    regression in any of the following breaks this test:

      - parser/builtin_commands.py::MoveCommand direction routing
      - parser/builtin_commands.py::_try_wilderness_entry
        edge match
      - engine/wilderness_movement.py::find_entry_edges_for_room
      - Region YAML schema (edges block, room_slug field,
        coords field, direction_from_room field)
      - db.save_character writing wilderness_region_slug +
        wilderness_x + wilderness_y columns
      - in_wilderness() character-state check
    """
    sentinel = await h.room_id_by_slug(SENTINEL_SLUG)
    player = await h.login_as("WMv1Player", room_id=sentinel)

    # Precondition: player is NOT in wilderness yet.
    char_pre = await h.get_char(player.character["id"])
    assert (char_pre.get("wilderness_region_slug") or "") == "", (
        f"WMv1Player started with wilderness_region_slug already "
        f"set. Schema migration or login flow may be polluting "
        f"state. Char: {char_pre!r}"
    )

    out = await h.cmd(player, ENTRY_DIRECTION)
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`{ENTRY_DIRECTION}` from sentinel raised: {out[:500]!r}"
    )
    # The "you can't go that way" fall-through means
    # _try_wilderness_entry returned False — regression marker.
    assert "can't go" not in out_lc and "cannot go" not in out_lc, (
        f"Direction `{ENTRY_DIRECTION}` from {SENTINEL_SLUG!r} fell "
        f"through to the no-exit message. _try_wilderness_entry "
        f"did not match the entry edge. "
        f"Likely cause: region YAML schema drift, room.properties "
        f"missing slug, or sentinel room missing from "
        f"wilderness_regions table. Output: {out[:400]!r}"
    )

    # Wait a beat for the entry transition to land in DB.
    await asyncio.sleep(0.1)

    char_post = await h.get_char(player.character["id"])
    assert char_post.get("wilderness_region_slug") == REGION_SLUG, (
        f"Post-entry wilderness_region_slug != {REGION_SLUG!r}. "
        f"Char: {char_post!r}"
    )
    assert char_post.get("wilderness_x") == ENTRY_COORDS[0], (
        f"Post-entry wilderness_x != {ENTRY_COORDS[0]}. "
        f"Char: {char_post!r}"
    )
    assert char_post.get("wilderness_y") == ENTRY_COORDS[1], (
        f"Post-entry wilderness_y != {ENTRY_COORDS[1]}. "
        f"Char: {char_post!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# W-MV-2 — Natural wilderness exit
# ──────────────────────────────────────────────────────────────────────────


async def w_mv_2_natural_exit(h):
    """W-MV-2 — Player standing in wilderness at the entry coords,
    types `west`, exits back to the sentinel room.

    The exit pathway is `_execute_wilderness_exit` in
    parser/builtin_commands.py. Pins:

      - Detection of an exit edge based on wilderness coords +
        direction
      - Reverse-direction mapping (west = back to sentinel)
      - DB clear of wilderness_region_slug / wilderness_x /
        wilderness_y
      - room_id restoration to the sentinel room

    Setup: drive natural entry first, then issue the exit
    direction. This composes W-MV-1's pipeline with the exit
    pipeline — a regression in either is caught.
    """
    sentinel = await h.room_id_by_slug(SENTINEL_SLUG)
    player = await h.login_as("WMv2Player", room_id=sentinel)

    # Enter naturally (W-MV-1 path).
    await h.cmd(player, ENTRY_DIRECTION)
    await asyncio.sleep(0.1)

    char_mid = await h.get_char(player.character["id"])
    # Precondition for the exit test — confirm we actually entered.
    assert char_mid.get("wilderness_region_slug") == REGION_SLUG, (
        f"W-MV-2 entry precondition failed — natural entry did "
        f"not land. Char: {char_mid!r}. This means W-MV-1 itself "
        f"is broken; fix that first."
    )

    # Exit.
    out = await h.cmd(player, EXIT_DIRECTION)
    out_lc = out.lower()
    assert "traceback" not in out_lc, (
        f"`{EXIT_DIRECTION}` from wilderness raised: {out[:500]!r}"
    )
    await asyncio.sleep(0.1)

    char_post = await h.get_char(player.character["id"])
    # wilderness_region_slug should be cleared.
    assert not (char_post.get("wilderness_region_slug") or ""), (
        f"Post-exit wilderness_region_slug not cleared. "
        f"Char: {char_post!r}"
    )
    # room_id should match the sentinel.
    assert char_post.get("room_id") == sentinel, (
        f"Post-exit room_id={char_post.get('room_id')} != "
        f"sentinel={sentinel}. Char: {char_post!r}"
    )
