# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/wilderness_combat.py — Wilderness combat smoke
scenarios (W-CMB-1, W-CMB-2, W-CMB-3).

W.2.4's handoff doc explicitly called these out as a Tier 2 follow-up:

    > **Does NOT change the smoke-harness combat scenarios.** They
    > exercise regular-room combat and continue to pass unchanged.
    > A wilderness-combat smoke scenario is a Tier 2 follow-up if you
    > want to add one; nothing in W.2.4 requires it.
    >                                       — HANDOFF_MAY17_W24, L373-376

This file is that follow-up.

──────────────────────────────────────────────────────────────────────
Status (post-PVF-5 bugfix drop, May 18 2026)
──────────────────────────────────────────────────────────────────────

Three scenarios ship now:

* **W-CMB-1** — `attack` in wilderness no longer produces the
  pre-W.2.4 `[NO COMBAT]` refusal. Gate-lift verification.

* **W-CMB-2** — Combat broadcasts on TILE_A do NOT reach a bystander
  PC on TILE_B of the same sentinel room. Path B `source_char=`
  threading verification at the live-harness level.

* **W-CMB-3** — Two combats at TILE_A and TILE_B of the same
  sentinel room exist as TWO SEPARATE entries in
  ``parser.combat_commands._active_combats``, not one shared
  CombatInstance. Tuple-keyed `(room_id, wx, wy)` verification.

──────────────────────────────────────────────────────────────────────
Historical: W-CMB-2 / W-CMB-3 were deferred during initial drop
──────────────────────────────────────────────────────────────────────

The initial W-CMB-1 drop attempted to ship W-CMB-2 and W-CMB-3 too
but deferred them because the harness consistently refused the
wilderness PvP attack with "Imperial law prohibits unprovoked assault
here" — the CONTESTED-zone-without-consent error from
``_check_pvp_consent``. The sentinel room used (CW Tatooine
``jundland_dune_sea_edge``) has ``security_level: lawless`` set in
``data/worlds/clone_wars/planets/tatooine.yaml``, and
``_check_pvp_consent`` bypasses consent in LAWLESS zones. The
expected behavior was that A1 can attack A2 at TILE_A without first
running challenge/accept.

The runtime resolved the room as CONTESTED instead — the
``security_level`` YAML field was inert at runtime. That was a
§6.2 dual-source-drift bug closed by Drop S-RES
(``engine/world_writer.py`` writer-merge for top-level
``security_level:``) and Drop S-RES.2 (zone-level security defaults
in ``zones.yaml``).

But un-deferring W-CMB-2 and W-CMB-3 immediately revealed a second
bug: the original W-CMB-1 scenario hardcoded
``DUNE_SEA_SENTINEL_ROOM = 53`` as a DB id, but YAML id 53
(``jundland_dune_sea_edge``) does NOT map to DB id 53 because the
schema's seed-data SQL pre-inserts three legacy Mos Eisley rooms at
DB ids 1-3, offsetting all YAML ids by +N. Coincidence preserved
W-CMB-1: DB id 53 happens to be ``jundland_beggars_canyon``, also
LAWLESS, also in the same zone, so the loose "no `[NO COMBAT]` and
no traceback" assertion still passed against the wrong room. But
W-CMB-2 and W-CMB-3 need precise tile semantics — the harness
helper ``h.room_id_by_slug()`` (added in this drop) is the
permanent fix.

──────────────────────────────────────────────────────────────────────
Wilderness setup mechanics
──────────────────────────────────────────────────────────────────────

The ``in_wilderness(char)`` check (engine/wilderness_movement.py L466)
reads ``char["wilderness_region_slug"]``: if non-empty, the character
is in wilderness regardless of room_id. Dropping a char into
wilderness is three DB column writes — these columns landed in
schema v20 and are in ``_CHARACTER_WRITABLE_COLUMNS``:
``wilderness_region_slug``, ``wilderness_x``, ``wilderness_y``.

For W-CMB-2 and W-CMB-3, the attack DOES need to engage — both
scenarios verify combat-level mechanics, not just the gate. The
LAWLESS resolution of ``jundland_dune_sea_edge`` (post-S-RES)
bypasses PvP consent so the attack engages cleanly.

──────────────────────────────────────────────────────────────────────
Note on _ClientSession attributes
──────────────────────────────────────────────────────────────────────

Per ``tests/harness.py`` L154-177:
  * ``s.character`` — property; setter also invalidates the cached
    Character object (no need to call invalidate_char_obj() manually).
  * ``s.json_events`` — property returning a snapshot of the JSON
    events buffer. NEVER auto-cleared; scenarios snapshot length
    before an action and slice from there to see what arrived.
"""
from __future__ import annotations


# Pinned-by-design wilderness fixture. Mirrors the unit-test fixture
# in test_w_2_4_combat_wilderness.py.
WILDERNESS_REGION = "dune_sea"
TILE_A = (12, 18)
TILE_B = (15, 22)

# CW Tatooine dune_sea sentinel room slug. The harness resolves this
# to a DB id at runtime via ``h.room_id_by_slug()``. NEVER hardcode
# the DB id — see the harness helper's docstring for the rationale
# (the schema's "Landing Pad" seed at DB id 1 offsets all YAML ids).
SENTINEL_SLUG = "jundland_dune_sea_edge"


async def _drop_into_wilderness(h, session, x: int, y: int,
                                region: str = WILDERNESS_REGION):
    """Move a logged-in test character into a wilderness tile.

    Uses ``db.save_character`` to set the three wilderness columns
    (writable per schema v20). Refreshes the session's character
    cache so subsequent ``in_wilderness(char)`` checks see the new
    state. The ``s.character = ...`` setter on _ClientSession also
    calls invalidate_char_obj() internally — no explicit invalidation
    needed.
    """
    char_id = session.character["id"]
    await h.db.save_character(
        char_id,
        wilderness_region_slug=region,
        wilderness_x=x,
        wilderness_y=y,
    )
    session.character = await h.get_char(char_id)


async def w_cmb_1_attack_in_wilderness_not_refused(h):
    """W-CMB-1 — `attack` in wilderness no longer produces the
    pre-W.2.4 `[NO COMBAT]` refusal.

    Pre-W.2.4, ``AttackCommand.execute`` had an early-return path:

        if in_wilderness(char):
            await ctx.session.send_line(
                "  [NO COMBAT] Combat is not supported in wilderness yet."
            )
            return

    W.2.4 removed this gate. Today, an attack in wilderness flows
    through the normal AttackCommand pipeline (target match, PvP
    consent check, combat setup, initiative, declare, broadcast).

    The unit-level test that proves the W.2.4 gate lift at the
    function level lives at
    ``test_w_2_4_combat_wilderness.py::TestAttackGateLifted``; this
    scenario verifies the same invariant exercising the live server
    path including session manager + parser + Path B
    ``source_char=`` threading.
    """
    sentinel = await h.room_id_by_slug(SENTINEL_SLUG)
    striker = await h.login_as("WCmb1Striker", room_id=sentinel)
    target = await h.login_as("WCmb1Target", room_id=sentinel)

    # Drop both into the same wilderness tile.
    await _drop_into_wilderness(h, striker, *TILE_A)
    await _drop_into_wilderness(h, target, *TILE_A)

    out = await h.cmd(striker, f"attack {target.character['name']}")
    assert out and out.strip(), "`attack` produced no output."

    # The pre-W.2.4 refusal text. If the wilderness gate has been
    # silently re-added, this is the smoking gun.
    assert "[NO COMBAT]" not in out, (
        f"AttackCommand refused with pre-W.2.4 '[NO COMBAT]' marker "
        f"after the wilderness gate lift. Output: {out[:500]!r}"
    )

    # And no exception. A traceback in command output would mean the
    # wilderness keying refactor broke a downstream code path.
    assert "traceback" not in out.lower(), (
        f"`attack` raised an exception in wilderness. "
        f"Output: {out[:500]!r}"
    )


async def w_cmb_2_tile_isolated_broadcasts(h):
    """W-CMB-2 — Combat broadcasts on TILE_A do NOT reach a bystander
    PC on TILE_B of the same sentinel room.

    The W.2.4 contract: every combat-broadcast site threads
    ``source_char=`` through to
    ``server.session.SessionManager.broadcast_to_room``, which
    filters via ``filter_by_source_location`` when the source is in
    wilderness. The filter restricts the receiver list to
    co-located peers — same sentinel room AND same wilderness
    coords.

    Without this filter, a wilderness combat at TILE_A would spill
    its broadcasts to every PC in the sentinel room regardless of
    their tile — defeating the entire point of wilderness as
    coord-keyed space.

    The scenario:
      * Striker + Target on TILE_A
      * Bystander on TILE_B (same sentinel room, different coords)
      * Striker attacks Target
      * Bystander should see ZERO combat-state events
    """
    import asyncio
    sentinel = await h.room_id_by_slug(SENTINEL_SLUG)
    striker = await h.login_as("WCmb2Striker", room_id=sentinel)
    target = await h.login_as("WCmb2Target", room_id=sentinel)
    bystander = await h.login_as("WCmb2Bystander", room_id=sentinel)

    # Striker + Target co-located at TILE_A; Bystander at TILE_B.
    await _drop_into_wilderness(h, striker, *TILE_A)
    await _drop_into_wilderness(h, target, *TILE_A)
    await _drop_into_wilderness(h, bystander, *TILE_B)

    # Snapshot the bystander's event pointer BEFORE the attack so we
    # can slice to "events that arrived during/after the attack."
    bystander_pre = len(bystander.json_events)

    out = await h.cmd(striker, f"attack {target.character['name']}")
    assert "traceback" not in out.lower(), (
        f"attack raised in W-CMB-2: {out[:400]!r}"
    )

    # Give async events a beat to flush through.
    await asyncio.sleep(0.2)

    # Bystander should have received NO combat-shaped events. The
    # exact event types vary by stage of combat (declare, resolve,
    # narrate, etc.) but anything carrying combat semantics should
    # be tile-filtered out. Inspect everything that arrived after
    # the snapshot.
    new_events = bystander.json_events[bystander_pre:]
    combat_types = {"combat_state", "combat_declare", "combat_narrate",
                    "combat_ended", "combat_event"}
    leaked = [e for e in new_events
              if e.get("type") in combat_types]
    assert not leaked, (
        f"W-CMB-2: Bystander at TILE_B={TILE_B} received "
        f"{len(leaked)} combat event(s) from combat at TILE_A={TILE_A} "
        f"in the same sentinel room. This is the wilderness "
        f"co-location leak W.2.4's source_char= threading is meant "
        f"to prevent. Leaked: "
        f"{[e.get('type') for e in leaked]!r}"
    )


async def w_cmb_3_separate_combat_instances_per_tile(h):
    """W-CMB-3 — Two combats at TILE_A and TILE_B of the same
    sentinel room exist as TWO SEPARATE entries in ``_active_combats``,
    not one shared CombatInstance.

    The W.2.4 contract: ``_combat_key_for`` returns
    ``(room_id, wilderness_x, wilderness_y)`` so two wilderness
    combats at different tiles of the same sentinel room don't
    collide on a single shared CombatInstance. Pre-W.2.4 the key
    was just ``room_id`` (an int), so two wilderness combats at the
    same sentinel collapsed into one CombatInstance — which mixed
    their combatant rosters, broadcasts, and ranges.

    The scenario:
      * Pair 1 (Striker1 + Target1) on TILE_A
      * Pair 2 (Striker2 + Target2) on TILE_B
      * Striker1 attacks Target1 → creates combat at TILE_A
      * Striker2 attacks Target2 → creates combat at TILE_B
      * Inspect ``_active_combats``: at least two entries should
        exist, keyed by (sentinel_db_id, TILE_A) and
        (sentinel_db_id, TILE_B), and the two CombatInstances
        should be distinct objects.

    The scenario imports ``_active_combats`` directly from
    ``parser.combat_commands`` because the W.2.4 invariant is
    module-level state. (This is a standard smoke pattern — see
    ``space_combat_gating.py`` for similar module-state inspection.)
    """
    sentinel = await h.room_id_by_slug(SENTINEL_SLUG)

    striker1 = await h.login_as("WCmb3Striker1", room_id=sentinel)
    target1 = await h.login_as("WCmb3Target1", room_id=sentinel)
    striker2 = await h.login_as("WCmb3Striker2", room_id=sentinel)
    target2 = await h.login_as("WCmb3Target2", room_id=sentinel)

    # Pair 1 at TILE_A, Pair 2 at TILE_B.
    await _drop_into_wilderness(h, striker1, *TILE_A)
    await _drop_into_wilderness(h, target1, *TILE_A)
    await _drop_into_wilderness(h, striker2, *TILE_B)
    await _drop_into_wilderness(h, target2, *TILE_B)

    # Fire both attacks.
    out1 = await h.cmd(striker1, f"attack {target1.character['name']}")
    assert "traceback" not in out1.lower(), (
        f"W-CMB-3: striker1 attack raised: {out1[:300]!r}"
    )
    out2 = await h.cmd(striker2, f"attack {target2.character['name']}")
    assert "traceback" not in out2.lower(), (
        f"W-CMB-3: striker2 attack raised: {out2[:300]!r}"
    )

    # Inspect _active_combats. Both keys should be present, both
    # values should be distinct CombatInstance objects.
    from parser.combat_commands import _active_combats

    key_a = (sentinel, TILE_A[0], TILE_A[1])
    key_b = (sentinel, TILE_B[0], TILE_B[1])

    combat_a = _active_combats.get(key_a)
    combat_b = _active_combats.get(key_b)

    assert combat_a is not None, (
        f"W-CMB-3: no CombatInstance at key={key_a!r} after attack "
        f"at TILE_A. Active keys: {list(_active_combats.keys())!r}"
    )
    assert combat_b is not None, (
        f"W-CMB-3: no CombatInstance at key={key_b!r} after attack "
        f"at TILE_B. Active keys: {list(_active_combats.keys())!r}"
    )
    assert combat_a is not combat_b, (
        f"W-CMB-3: TILE_A and TILE_B combat resolved to the SAME "
        f"CombatInstance object. The tuple-keyed _active_combats "
        f"is collapsing wilderness tiles back into a shared "
        f"sentinel-room combat — the exact bug W.2.4 was meant to "
        f"fix. key_a={key_a!r} key_b={key_b!r} "
        f"combat_a={combat_a!r}"
    )

    # And the CombatInstance objects should carry the correct
    # wilderness anchors (W.2.4 invariant: instance fields match
    # the key).
    assert combat_a.wilderness_x == TILE_A[0], (
        f"W-CMB-3: combat_a.wilderness_x={combat_a.wilderness_x} "
        f"doesn't match TILE_A x={TILE_A[0]}"
    )
    assert combat_a.wilderness_y == TILE_A[1], (
        f"W-CMB-3: combat_a.wilderness_y={combat_a.wilderness_y} "
        f"doesn't match TILE_A y={TILE_A[1]}"
    )
    assert combat_b.wilderness_x == TILE_B[0], (
        f"W-CMB-3: combat_b.wilderness_x={combat_b.wilderness_x} "
        f"doesn't match TILE_B x={TILE_B[0]}"
    )
    assert combat_b.wilderness_y == TILE_B[1], (
        f"W-CMB-3: combat_b.wilderness_y={combat_b.wilderness_y} "
        f"doesn't match TILE_B y={TILE_B[1]}"
    )
