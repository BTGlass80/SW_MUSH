# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/underworld_loop.py — Coruscant Underworld smoke
scenarios (UW1, UW2).

Proves the coruscant_underworld wilderness region is reachable and that
the three exploration verbs (look, anomalies, loot) don't crash inside it.

Scenarios
=========

* **UW1** — Wilderness placement via the synthetic ``_drop_into_wilderness``
  helper (the same pattern used by wilderness_combat.py). A character is
  logged in at the coruscant_underworld virtual sentinel room, then the
  three wilderness DB columns are written directly. Asserts that:
    - ``wilderness_region_slug == "coruscant_underworld"`` after the drop.
    - The region YAML loads cleanly via ``get_or_load_region`` (no crash,
      non-None return — proves the file path resolves and the loader
      accepts the build-out content).

  **Why not natural entry (typing "deeper" from coruscant_uw_surface_entry)?**
  The parser's direction-routing block in ``CommandParser.process`` only
  forwards the standard compass words + "enter"/"leave" to MoveCommand.
  ``deeper`` (the ``direction_from_room`` in coruscant_underworld.yaml's
  edge block) is not in that list, so the parser returns "Unknown command:
  deeper". This is the "natural entry into this region is not wired" case
  the spec anticipates. The synthetic-drop fallback is explicitly allowed
  and this note explains the design gap.

  The gap is reported to the main session for tracking. The fix would be
  to add ``deeper`` (and similar custom direction words from edge YAMLs)
  to the parser's direction routing table — a design call outside this
  drop's scope.

* **UW2** — Exploration verbs: from inside the region (synthetic drop),
  run ``look``, ``anomalies``, and ``loot``; assert no crash and a
  coherent (non-empty or clean-empty) response from each.

  Expected outputs (all acceptable):
    - ``look``: wilderness room render with region name in output.
    - ``anomalies``: either empty-state message or a list. Header always
      present. No crash.
    - ``loot`` (no args): usage prompt. No crash.

Sentinel room used for UW1/UW2
===============================

The wilderness writer creates a virtual sentinel room:
  name: "Wilderness: Coruscant Underworld"
  slug (in properties): "wilderness_coruscant_underworld_virtual"
  wilderness_region_id: "coruscant_underworld"

By logging the test character into that room BEFORE the synthetic drop,
the character's ``room_id`` points to a room with
``wilderness_region_id = 'coruscant_underworld'``. This is required for
the ``anomalies`` command, which resolves the region via
``_resolve_room_region(db, room_id)`` (not from ``wilderness_region_slug``
directly).

Notes
=====

* The ``loot`` probe uses no args (→ usage prompt), since no corpse is
  present in a fresh test harness.
* ``anomalies`` will always return the empty-state message in a fresh
  harness (no anomaly-spawner running).
"""
from __future__ import annotations


# ── Region constants ───────────────────────────────────────────────────────────

# The region slug persisted to characters.wilderness_region_slug.
REGION_SLUG = "coruscant_underworld"

# The virtual sentinel room slug created by the wilderness writer.
# Used as the character's room_id during the synthetic drop so that
# anomalies / territory commands can resolve the region from the room.
SENTINEL_SLUG = "wilderness_coruscant_underworld_virtual"

# Tile coords to drop the character at (arbitrary in-bounds coords for
# coruscant_underworld's 40x40 grid).
DROP_TILE = (20, 17)  # matches the declared entry edge coords


# ── Shared synthetic-drop helper ───────────────────────────────────────────────


async def _drop_into_underworld(h, session, x: int = DROP_TILE[0],
                                y: int = DROP_TILE[1]):
    """Write wilderness state directly to DB columns.

    Mirrors the ``_drop_into_wilderness`` pattern from wilderness_combat.py.
    Refreshes the session character cache so subsequent ``in_wilderness``
    checks see the new state.
    """
    char_id = session.character["id"]
    await h.db.save_character(
        char_id,
        wilderness_region_slug=REGION_SLUG,
        wilderness_x=x,
        wilderness_y=y,
    )
    session.character = await h.get_char(char_id)


# ── UW1: Synthetic entry — region loads ────────────────────────────────────────


async def uw1_synthetic_entry(h):
    """UW1 — Synthetic drop into coruscant_underworld; assert region loads.

    Uses the ``_drop_into_underworld`` helper to set the three wilderness
    DB columns on a fresh character, then verifies:
      1. ``wilderness_region_slug`` is persisted correctly.
      2. The region YAML resolves via ``get_or_load_region`` (file exists,
         loads clean, returns a WildernessRegion with the expected slug).

    This is the canonical "new-region-no-driver" smoke probe: it confirms
    the region data is wired into the engine's YAML-load path and that the
    build-out content (20 landmarks from Drop 18) doesn't introduce any
    YAML parse error.

    The synthetic pattern is used (rather than natural MoveCommand entry)
    because the parser's direction-dispatch only routes standard compass
    words to MoveCommand; the coruscant_underworld edge uses the custom
    direction ``deeper`` which is outside that set. See module docstring.
    """
    sentinel_room = await h.room_id_by_slug(SENTINEL_SLUG)
    player = await h.login_as("UW1Player", room_id=sentinel_room)

    # Precondition: not in wilderness yet.
    char_pre = await h.get_char(player.character["id"])
    assert (char_pre.get("wilderness_region_slug") or "") == "", (
        f"UW1Player started with wilderness_region_slug set: {char_pre!r}"
    )

    # Synthetic drop.
    await _drop_into_underworld(h, player)

    char_post = player.character
    assert char_post.get("wilderness_region_slug") == REGION_SLUG, (
        f"After synthetic drop, wilderness_region_slug != {REGION_SLUG!r}. "
        f"Char: {char_post!r}"
    )
    assert char_post.get("wilderness_x") == DROP_TILE[0], (
        f"wilderness_x != {DROP_TILE[0]}. Char: {char_post!r}"
    )
    assert char_post.get("wilderness_y") == DROP_TILE[1], (
        f"wilderness_y != {DROP_TILE[1]}. Char: {char_post!r}"
    )

    # Verify region loads from YAML (proves file exists and parse succeeds).
    from engine.wilderness_movement import get_or_load_region
    region = await get_or_load_region(h.db, REGION_SLUG)
    assert region is not None, (
        f"get_or_load_region returned None for {REGION_SLUG!r}. "
        f"Expected the YAML at "
        f"data/worlds/clone_wars/wilderness/coruscant_underworld.yaml "
        f"to resolve. Check the file exists and loads without errors."
    )
    assert region.slug == REGION_SLUG, (
        f"Loaded region slug {region.slug!r} != expected {REGION_SLUG!r}"
    )
    # Sanity: 20 landmarks expected (8 anchors + 12 build-out from Drop 18).
    assert len(region.landmarks) >= 8, (
        f"Region has {len(region.landmarks)} landmarks; expected >= 8. "
        f"The Drop 18 build-out may not have loaded."
    )


# ── UW2: Exploration verbs ──────────────────────────────────────────────────────


async def uw2_exploration_verbs(h):
    """UW2 — From inside coruscant_underworld, run look / anomalies / loot.
    Assert no crash and a coherent (non-empty or clean-empty) response.

    The character is placed via synthetic drop into the coruscant_underworld
    region and then the three exploration verbs are exercised.
    """
    sentinel_room = await h.room_id_by_slug(SENTINEL_SLUG)
    player = await h.login_as("UW2Player", room_id=sentinel_room)

    # Synthetic drop.
    await _drop_into_underworld(h, player)

    # Sanity: character is in wilderness.
    assert player.character.get("wilderness_region_slug") == REGION_SLUG, (
        f"UW2 precondition: synthetic drop did not land. "
        f"Char: {player.character!r}"
    )

    # ── look ──────────────────────────────────────────────────────────────
    look_out = await h.cmd(player, "look")
    look_lc = look_out.lower()
    assert "traceback" not in look_lc, (
        f"`look` in wilderness raised: {look_out[:500]!r}"
    )
    assert "error occurred" not in look_lc, (
        f"`look` in wilderness returned error: {look_out[:500]!r}"
    )
    # Wilderness look always emits at least the region name header and coords.
    assert look_out.strip(), "`look` returned empty output in wilderness."
    # "coruscant" must appear in the "Coruscant Underworld — Coordinates x, y"
    # header line emitted by _look_wilderness.
    assert "coruscant" in look_lc, (
        f"`look` output in coruscant_underworld doesn't contain 'coruscant'. "
        f"Output: {look_out[:400]!r}"
    )

    # ── anomalies ─────────────────────────────────────────────────────────
    anom_out = await h.cmd(player, "anomalies")
    anom_lc = anom_out.lower()
    assert "traceback" not in anom_lc, (
        f"`anomalies` in wilderness raised: {anom_out[:500]!r}"
    )
    assert "error occurred" not in anom_lc, (
        f"`anomalies` in wilderness returned error: {anom_out[:500]!r}"
    )
    # The command always emits at least a header line or empty-state text.
    assert anom_out.strip(), "`anomalies` returned empty output."

    # ── loot (no args → usage prompt) ─────────────────────────────────────
    loot_out = await h.cmd(player, "loot")
    loot_lc = loot_out.lower()
    assert "traceback" not in loot_lc, (
        f"`loot` in wilderness raised: {loot_out[:500]!r}"
    )
    assert "error occurred" not in loot_lc, (
        f"`loot` in wilderness returned error: {loot_out[:500]!r}"
    )
    # With no args, LootCommand always emits a non-empty response.
    assert loot_out.strip(), "`loot` returned empty output in wilderness."
