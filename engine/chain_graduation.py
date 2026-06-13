# -*- coding: utf-8 -*-
"""
engine/chain_graduation.py — F.8.c.2.c chain graduation teleport.

When ``tutorial_chains.advance_step`` flips a chain to
``completion_state="graduated"``, this module:

1. Resolves the chain's ``graduation.drop_room`` slug to a real
   ``rooms.id`` via ``db.get_room_by_slug``.
2. Persists the player's room change (``save_character(room_id=...)``).
3. Stamps a ``pending_drop_room_id`` flag on the chain state so the
   parser hook site can deliver the session-aware UI work
   (broadcast departure / arrival, send a teleport flavor line,
   trigger a synthetic look).

Why split engine / parser concerns
----------------------------------
The engine-layer chain dispatcher (``chain_events._try_advance``)
runs without a parser context — it has ``db`` and ``char``, but
no ``ctx.session_mgr``, no ``LookCommand``, no broadcast channel.
The graduation persistence happens in engine layer; the
session-aware look + teleport flavor happens in parser layer when
control returns from the hook.

Lifecycle
---------
1. Player runs a command that advances a chain (e.g. ``+factions``,
   ``talk Tarrn``, ``move``).
2. Parser hook calls ``chain_events.on_*(db, char, ...)``.
3. ``_try_advance`` calls ``advance_step``; if ``graduated=True``,
   ``apply_graduation`` resolves drop_room, persists room change,
   stamps ``pending_drop_room_id``.
4. Hook returns ``True`` to the parser.
5. Parser sees the True, calls ``execute_pending_teleport(ctx, char)``,
   which: mutates ``ctx.session.character["room_id"]``, broadcasts
   to old + new room, sends a teleport flavor line, runs auto-look,
   clears the pending flag.

If the parser site doesn't call ``execute_pending_teleport`` (e.g.
the ``db.add_to_inventory`` graduation path, which is data-layer
only), the player ends up persisted in the new room but doesn't
get the immediate session UI. The flag stays set; the next
movement / look will surface the correct room because
``session.character["room_id"]`` will re-fetch on the next
session reload.

Failure-tolerant: any exception in graduation processing is
logged and swallowed. A graduation that can't teleport leaves
the chain in ``graduated`` state at the player's pre-graduation
room — they're still graduated, just standing where they were.
This is the right behavior; chains shouldn't fail to advance
because their drop_room slug has a typo.

Tested by tests/test_f8c2c_chain_graduation.py.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


_TUTORIAL_CHAIN_KEY = "tutorial_chain"
_PENDING_DROP_ROOM_KEY = "pending_drop_room_id"
# F.8.c.2.e (2026-06-12): inter-step teleport. Distinct from the
# graduation flag so the parser finisher delivers a light "you move on"
# arrival (synthetic look) instead of the graduation flavor + reward
# summary. Stamped only by apply_step_teleport.
_PENDING_STEP_ROOM_KEY = "pending_step_room_id"


# ── Slug resolution ─────────────────────────────────────────────────


async def resolve_drop_room_id(db, drop_room_slug: str) -> Optional[int]:
    """Resolve a chain ``graduation.drop_room`` slug to a real
    ``rooms.id``.

    Returns the int room id, or None if:
      - The slug is empty or whitespace
      - The DB has no ``get_room_by_slug`` helper
      - No room has ``properties.slug`` matching the slug
      - DB lookup raises any error

    Slug-stamping in ``properties.slug`` was introduced by F.8.c.1
    (the world-writer change). Existing pre-F.8.c.1 rooms need a
    DB rebuild migration to backfill — see the F.8.c.2.c handoff
    for the migration path."""
    if not drop_room_slug or not drop_room_slug.strip():
        return None

    slug = drop_room_slug.strip()

    getter = getattr(db, "get_room_by_slug", None)
    if getter is None:
        log.debug("[chain_graduation] db.get_room_by_slug not "
                  "available; cannot resolve %r", slug)
        return None

    try:
        row = await getter(slug)
    except Exception:
        log.debug("[chain_graduation] get_room_by_slug raised for %r",
                  slug, exc_info=True)
        return None

    if not row:
        return None

    room_id = row.get("id") if isinstance(row, dict) else None
    if room_id is None:
        return None

    try:
        return int(room_id)
    except (TypeError, ValueError):
        log.debug("[chain_graduation] non-int room id %r for slug %r",
                  room_id, slug)
        return None


# ── Engine-layer: persist the room change ──────────────────────────


async def apply_graduation(db, char: dict, attrs: dict,
                           drop_room_slug: str,
                           state_key: str = _TUTORIAL_CHAIN_KEY,
                           ) -> Optional[int]:
    """Engine-layer graduation handler. Resolves slug, persists
    room change, stamps the ``pending_drop_room_id`` flag for the
    parser to pick up.

    Mutates ``attrs`` in place (caller will re-persist). Mutates
    ``char["room_id"]`` to the new id so subsequent in-tick code
    that re-reads ``char`` sees the right room.

    T5-questline arc (2026-06-13): ``state_key`` selects which chain
    slot the pending flag is stamped on — the onboarding
    ``tutorial_chain`` (default) or the mid-game ``active_questline``.
    Stamping the wrong slot would corrupt a graduated onboarding block
    on a veteran finishing a questline, so the caller passes the slot
    whose chain just graduated.

    Returns the new room id on success, or None on failure (no
    teleport happens; the player keeps their pre-graduation room).
    The chain's ``completion_state="graduated"`` is independent
    of teleport success — the chain is graduated either way.
    """
    if not drop_room_slug:
        return None

    new_room_id = await resolve_drop_room_id(db, drop_room_slug)
    if new_room_id is None:
        log.warning(
            "[chain_graduation] drop_room slug %r failed to resolve; "
            "char %s graduates but stays in room %s",
            drop_room_slug, char.get("id"), char.get("room_id"),
        )
        return None

    if int(char.get("room_id") or 0) == new_room_id:
        # Already in the drop room (rare but possible if the chain
        # ends in the room itself). Skip the move; still stamp the
        # pending flag so the parser sends the graduation flavor.
        state = attrs.setdefault(state_key, {})
        state[_PENDING_DROP_ROOM_KEY] = new_room_id
        return new_room_id

    # Persist the room change. Use save_character — same path the
    # boarding module uses for ship-to-ship transfer (see
    # engine/boarding.py::dock_with).
    try:
        await db.save_character(char["id"], room_id=new_room_id)
    except Exception:
        log.warning("[chain_graduation] save_character room_id "
                    "persist failed for char %s", char.get("id"),
                    exc_info=True)
        return None

    # Mutate the in-tick char dict so other code in this tick sees
    # the new room. The parser will also mutate ctx.session.character
    # via execute_pending_teleport.
    char["room_id"] = new_room_id

    # Stamp the pending flag for the parser hook site.
    state = attrs.setdefault(state_key, {})
    state[_PENDING_DROP_ROOM_KEY] = new_room_id

    log.info("[chain_graduation] char %s graduated; teleport %s -> %s "
             "(slug=%r, room_id=%s)",
             char.get("id"), char.get("room_id"), new_room_id,
             drop_room_slug, new_room_id)

    return new_room_id


# ── Engine-layer: inter-step teleport (F.8.c.2.e) ──────────────────


async def apply_step_teleport(db, char: dict, attrs: dict,
                              step_location_slug: str,
                              state_key: str = _TUTORIAL_CHAIN_KEY,
                              ) -> Optional[int]:
    """Engine-layer inter-step move. When a chain advances to a new
    (non-graduation) step whose authored ``location`` differs from the
    player's current room, resolve that slug and move the player there.

    This is the movement the tutorial-room EXIT POLICY always assumed
    (``data/worlds/clone_wars/tutorials/rooms.yaml`` header): tutorial
    rooms carry no walkable exits because the state machine relays the
    player between step rooms. Graduation had this (apply_graduation);
    the inter-step case was missing, which stranded players at the
    first step whose room differed from the chain's ``starting_room``.

    Mirrors apply_graduation: resolves the slug, persists the room
    change, mutates the in-tick ``char`` dict, and stamps a pending
    flag (``pending_step_room_id``) for the parser finisher to deliver
    the session-aware look. Uses a DISTINCT flag from graduation so the
    finisher renders an ordinary arrival, not the graduation summary.

    No-ops (returns None) when: the slug is empty, it fails to resolve,
    or it resolves to the room the player is already in. Failure-
    tolerant by design — a bad slug logs at WARNING and leaves the
    player where they are rather than stranding them in limbo. The
    chain step still advanced; only the convenience move is skipped.
    """
    if not step_location_slug or not str(step_location_slug).strip():
        return None

    new_room_id = await resolve_drop_room_id(db, step_location_slug)
    if new_room_id is None:
        log.warning(
            "[chain_graduation] step location slug %r failed to "
            "resolve; char %s stays in room %s",
            step_location_slug, char.get("id"), char.get("room_id"),
        )
        return None

    if int(char.get("room_id") or 0) == new_room_id:
        # Step's location is the room the player is already standing in
        # (e.g. two consecutive steps share a room). No move, no flag.
        return new_room_id

    try:
        await db.save_character(char["id"], room_id=new_room_id)
    except Exception:
        log.warning("[chain_graduation] step teleport save_character "
                    "failed for char %s", char.get("id"), exc_info=True)
        return None

    prev_room_id = char.get("room_id")
    char["room_id"] = new_room_id

    state = attrs.setdefault(state_key, {})
    state[_PENDING_STEP_ROOM_KEY] = new_room_id

    log.info("[chain_graduation] char %s step-advance teleport %s -> %s "
             "(slug=%r)",
             char.get("id"), prev_room_id, new_room_id,
             step_location_slug)

    return new_room_id


# ── Parser-layer: session-aware finish ─────────────────────────────


async def execute_pending_teleport(ctx, char: dict) -> bool:
    """Parser-layer graduation finisher. Reads the pending flag,
    delivers the session UI: broadcast departure (from the player's
    pre-teleport room — already null since save_character ran in
    apply_graduation), broadcast arrival, send teleport flavor line,
    run synthetic look. Clears the pending flag.

    Returns True iff a teleport UI was delivered.

    No-op (returns False) if no pending teleport flag is set, the
    flag is stale (room id no longer resolves), or anything fails.

    Failure-tolerant: any exception is logged and swallowed. The
    player has already been persisted to the new room by
    apply_graduation; this is the cosmetic finish, and a failure
    here is mildly annoying but not corrupting.
    """
    import json as _gj

    try:
        attrs_raw = char.get("attributes") or "{}"
        if isinstance(attrs_raw, str):
            attrs = _gj.loads(attrs_raw or "{}")
        else:
            attrs = attrs_raw or {}
    except Exception:
        log.debug("[chain_graduation] parse char attrs failed",
                  exc_info=True)
        return False

    # T5-questline arc (2026-06-13): a pending teleport flag may live in
    # EITHER chain slot (onboarding `tutorial_chain` or mid-game
    # `active_questline`). Walk both and act on whichever carries a
    # pending flag — onboarding first, so a graduating onboarding chain
    # is handled before a questline if both somehow stamped at once.
    from engine.tutorial_chains import CHAIN_STATE_KEYS
    state = {}
    pending_state_key = _TUTORIAL_CHAIN_KEY
    is_graduation = False
    pending = None
    for _skey in CHAIN_STATE_KEYS:
        _st = attrs.get(_skey) or {}
        # Graduation takes priority over an inter-step move if both are
        # somehow stamped (graduation is terminal). The two flags drive
        # different player-facing deliveries below. Use KEY PRESENCE (not
        # value truthiness) to classify: a room id of 0 would wrongly read
        # as "no graduation" under bool(). Room ids autoincrement from 1 so
        # 0 never occurs in practice, but key-presence is unambiguous.
        if _PENDING_DROP_ROOM_KEY in _st:
            state, pending_state_key = _st, _skey
            is_graduation = True
            pending = _st.get(_PENDING_DROP_ROOM_KEY)
            break
        if _PENDING_STEP_ROOM_KEY in _st:
            state, pending_state_key = _st, _skey
            is_graduation = False
            pending = _st.get(_PENDING_STEP_ROOM_KEY)
            break
    if not pending:
        return False

    try:
        new_room_id = int(pending)
    except (TypeError, ValueError):
        # Bad data; clear and bail.
        await _clear_pending(ctx.db, char, attrs, pending_state_key)
        return False

    # Verify the room still exists.
    try:
        room = await ctx.db.get_room(new_room_id)
    except Exception:
        log.debug("[chain_graduation] get_room raised for pending "
                  "teleport room %s", new_room_id, exc_info=True)
        room = None

    if not room:
        log.warning("[chain_graduation] pending teleport room %s "
                    "doesn't exist; clearing flag", new_room_id)
        await _clear_pending(ctx.db, char, attrs, pending_state_key)
        return False

    # Sync session state. The engine-side apply_graduation already
    # mutated char["room_id"] AND persisted via save_character. Here
    # we just align ctx.session.character with the same value (in
    # case ctx.session.character is a different dict than char).
    try:
        if ctx.session and ctx.session.character is not None:
            ctx.session.character["room_id"] = new_room_id
    except Exception:
        log.debug("[chain_graduation] session.character sync failed",
                  exc_info=True)

    # Player-facing arrival. Graduation gets the terminal "training
    # complete" flavor; an inter-step move gets a light relocation
    # line. Both precede the synthetic look. Chains can override the
    # graduation flavor later via `graduation.flavor` (Phase 2 polish).
    try:
        room_name = room.get("name") or "your destination"
        await ctx.session.send_line("")
        if is_graduation:
            await ctx.session.send_line(
                "  \033[1;33mYour training is complete. The world opens "
                "before you.\033[0m"
            )
            await ctx.session.send_line("")
            await ctx.session.send_line(
                f"  \033[1;36mYou step out into {room_name}.\033[0m"
            )
        else:
            await ctx.session.send_line(
                f"  \033[1;36mYou make your way to {room_name}.\033[0m"
            )
        await ctx.session.send_line("")
    except Exception:
        log.debug("[chain_graduation] flavor lines failed",
                  exc_info=True)

    # Synthetic look. Build a CommandContext for the look call.
    try:
        registry = getattr(ctx.session_mgr, "_registry", None)
        look_cmd = None
        if registry is not None:
            look_cmd = registry.get("look")
        if look_cmd is not None:
            look_ctx = type(ctx)(
                session=ctx.session, raw_input="look", command="look",
                args="", args_list=[], db=ctx.db,
                session_mgr=ctx.session_mgr,
            )
            await look_cmd.execute(look_ctx)
    except Exception:
        log.debug("[chain_graduation] synthetic look failed",
                  exc_info=True)

    # F.8.c.2.d: graduation reward summary — graduation only. Reads the
    # graduation_summary block stamped onto chargen_notes by
    # apply_graduation_rewards (engine layer) and delivers the
    # multi-line player-visible summary. No-op if no summary block
    # exists. Skipped entirely for an inter-step move (no rewards to
    # summarize there).
    if is_graduation:
        try:
            from engine.chain_rewards import send_graduation_summary
            await send_graduation_summary(ctx.session, char)
        except Exception:
            log.debug("[chain_graduation] reward summary send failed",
                      exc_info=True)

    # Clear the pending flag and persist.
    await _clear_pending(ctx.db, char, attrs)

    return True


async def _clear_pending(db, char: dict, attrs: dict,
                         state_key: str = _TUTORIAL_CHAIN_KEY) -> None:
    """Internal helper. Drops any pending teleport flag
    (``pending_drop_room_id`` and/or ``pending_step_room_id``) from the
    given chain slot and re-persists attrs.

    T5-questline arc (2026-06-13): ``state_key`` selects the slot the
    flag was stamped on (matched by execute_pending_teleport's slot
    walk), so a questline's pending flag is cleared from the questline
    slot — not the onboarding slot."""
    import json as _gj
    try:
        state = attrs.get(state_key) or {}
        removed = False
        for _key in (_PENDING_DROP_ROOM_KEY, _PENDING_STEP_ROOM_KEY):
            if _key in state:
                del state[_key]
                removed = True
        if removed:
            attrs[state_key] = state
            await db.save_character(
                char["id"],
                attributes=_gj.dumps(attrs),
            )
            # Sync the in-tick char dict.
            char["attributes"] = _gj.dumps(attrs)
    except Exception:
        log.debug("[chain_graduation] _clear_pending failed",
                  exc_info=True)
