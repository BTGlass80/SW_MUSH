# -*- coding: utf-8 -*-
"""
engine/village_choice.py — Village quest Step 10: the Path A/B/C choice.

F.7.d closes the Village quest chain by giving the player a single
irreversible commit between three paths after all five trials are
complete. Per ``jedi_village_quest_design_v1.md`` §7.0–§7.3:

  - **Path A — Report to the Jedi Order.** Master Yarael writes a
    letter of introduction sealed with his old Order signet. The
    character is escorted (off-stage) to the Coruscant Jedi Temple
    and received by Master Mace Windu. Mechanically:
      - sets ``force_sensitive`` on the character (top-level field)
      - sets ``jedi_path_unlocked = True`` in chargen_notes JSON
        (this unblocks the Jedi tutorial chain in F.8.b)
      - records ``village_chosen_path_a = True`` for downstream lore
      - joins ``jedi_order`` org at rank 0 if the org exists
      - teleports the player to ``jedi_temple_main_gate``
      - records ``village_trial_lightsaber_construction_pending``
        marker for a future drop with the lightsaber-construction
        chain (current drop does not consume the crystal — see
        carry-over §F.7.e in handoff)

  - **Path B — Stay with the Village / Independent.** Yarael nods and
    tells the character the Village is theirs as much as anyone's.
    Mechanically:
      - sets ``force_sensitive``
      - sets ``jedi_path_unlocked = True`` (the Jedi tutorial chain
        is available — but the player has chosen not to take it
        right now; engine intent is permissive)
      - records ``village_chosen_path_b = True``
      - joins ``independent`` org if it exists, +50 rep
      - keeps ``village_trial_crystal`` uncommitted (no consumption)
      - teleports the player to ``village_common_square``

  - **Path C — Dark whispers.** ONLY available if the Spirit trial
    locked Path C (``village_trial_spirit_path_c_locked = 1``). Per
    design §7.3, this is the failure mode of the Spirit trial
    repurposed as a deliberate path. Mechanically:
      - sets ``force_sensitive``
      - does NOT set ``jedi_path_unlocked`` (the Order will not have
        them; per design)
      - sets ``dark_path_unlocked = True``
      - records ``village_chosen_path_c = True``
      - records ``dark_contact_freq`` item marker for a future drop
        with the dark-side comlink content (current drop does not
        wire the comlink; design: "static — no answer" at launch)
      - does NOT join any org (Path C is exiled)
      - teleports the player to ``dune_sea_anchor_stones``

The choice is irreversible. Once ``village_choice_completed = 1``,
the engine no longer presents the Path menu and Yarael acknowledges
the road taken.

Player commands
================

  - ``path``                — show the menu (which paths are open;
                              Path C only listed if locked-in)
  - ``path a`` | ``a``      — commit Path A
  - ``path b`` | ``b``      — commit Path B
  - ``path c`` | ``c``      — commit Path C (refused if not locked)

Talk-to-Yarael in Master's Chamber post-Insight
================================================

The audience hook in ``engine/village_dialogue.py`` already gates on
"first audience not yet done." After Insight is complete, this
module's ``maybe_handle_yarael_path_choice`` intercepts in the
Master's Chamber and presents the menu. (Yarael in the Sealed
Sanctum still routes to the Spirit hook.)

If ``path_c_locked`` is True, the menu shows only Path C — Yarael's
sadness-not-anger framing.

Schema
======

v25 columns:
  - ``village_choice_completed``  INTEGER bool
  - ``village_chosen_path``       TEXT 'a' | 'b' | 'c' | ''

Other state lives in chargen_notes JSON (``jedi_path_unlocked``,
``dark_path_unlocked``, ``village_chosen_path_a/b/c``,
``village_trial_lightsaber_construction_pending``,
``dark_contact_freq``).
"""
from __future__ import annotations

import json
import logging
from typing import Mapping, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Master's Chamber room name — this is the room where Yarael holds
# the audience and where the Path choice is delivered. (Yarael in
# the Sealed Sanctum routes to the Spirit hook; that hook is
# room-gated to the Sanctum.)
MASTERS_CHAMBER_ROOM_NAME: str = "Master's Chamber"

# Path landing rooms (live-world slugs in `data/.../wilderness/`
# regions). These names match the actual room slugs in CW data; the
# F.4c rename map (jedi_temple_gates → jedi_temple_main_gate) was
# applied across the codebase, so we use the post-rename slug here.
PATH_A_DROP_SLUG: str = "jedi_temple_main_gate"
PATH_B_DROP_SLUG: str = "village_common_square"
PATH_C_DROP_SLUG: str = "dune_sea_anchor_stones"

PATH_A: str = "a"
PATH_B: str = "b"
PATH_C: str = "c"
VALID_PATHS = (PATH_A, PATH_B, PATH_C)


# ─────────────────────────────────────────────────────────────────────────────
# Accessors
# ─────────────────────────────────────────────────────────────────────────────


def is_choice_completed(char: Mapping) -> bool:
    """True iff the character has committed a Path."""
    return int(char.get("village_choice_completed") or 0) == 1


def get_chosen_path(char: Mapping) -> str:
    """Return 'a' | 'b' | 'c' | '' (uncommitted)."""
    return (char.get("village_chosen_path") or "").strip().lower()


def is_path_choice_unlocked(char: Mapping) -> bool:
    """True iff the character has finished all five trials and may
    commit a Path. Insight is the last trial; if Insight is done,
    all four upstream trials must also be (the gate enforces it)."""
    return int(char.get("village_trial_insight_done") or 0) == 1


def is_path_c_locked(char: Mapping) -> bool:
    """True iff the Spirit trial accumulated 3+ temptations.
    Re-export of the Spirit accessor for ergonomics — callers in this
    module read it locally instead of importing the trials module."""
    return int(char.get("village_trial_spirit_path_c_locked") or 0) == 1


def _read_chargen_notes(char: Mapping) -> dict:
    """Return chargen_notes as a dict (defensive against missing /
    malformed JSON)."""
    raw = char.get("chargen_notes") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def has_chargen_flag(char: Mapping, flag: str) -> bool:
    """Convenience: True iff chargen_notes[flag] is truthy."""
    return bool(_read_chargen_notes(char).get(flag))


# ─────────────────────────────────────────────────────────────────────────────
# Menu rendering
# ─────────────────────────────────────────────────────────────────────────────


async def _emit_path_menu(session, char: Mapping) -> None:
    """Render the Path A/B/C menu. If path_c_locked, show only Path C
    with the design §7.3 framing."""
    await session.send_line("")
    if is_path_c_locked(char):
        # Path C only — Yarael's sadness, not anger.
        await session.send_line(
            "  \033[1;33m*Master Yarael Tinré looks at you with sadness, "
            "not anger.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"You are not what we hoped. You are something "
            "else. The Order would turn you away. The Sith — they would "
            "not. There is a contact. I will not stop you from finding "
            "him. You may not return here.\"\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;31mAvailable path:\033[0m"
        )
        await session.send_line(
            f"  \033[1;31m  path c\033[0m   "
            f"\033[2mAccept the comlink frequency. Leave the Village.\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[2mThis choice is final.\033[0m"
        )
        await session.send_line("")
        return

    # Normal A / B / (C if locked) menu
    await session.send_line(
        "  \033[1;33m*Master Yarael Tinré rises slowly. The Sanctum and "
        "the Council Hut are behind you now. The trials are done.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"You have stood in five places and you are still "
        "yourself. There is one passage left, and it is not a trial — "
        "it is a road. Three roads lie before you. Pick one.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line("  \033[1;36mAvailable paths:\033[0m")
    await session.send_line(
        f"  \033[1;36m  path a\033[0m   "
        f"\033[2mReport to the Jedi Order. The Master writes a letter; "
        f"you go to Coruscant.\033[0m"
    )
    await session.send_line(
        f"  \033[1;36m  path b\033[0m   "
        f"\033[2mStay with the Village. Independent. The Force is yours; "
        f"the Order has no claim.\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2mThis choice is final.\033[0m"
    )
    await session.send_line("")


# ─────────────────────────────────────────────────────────────────────────────
# Talk-to-Yarael-in-Master's-Chamber hook (post-Insight)
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_handle_yarael_path_choice(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Talk-to-Yarael hook — fires only when the Path choice is the
    next thing on the table.

    Logic ladder:
      1. Not Yarael: return False
      2. Not in Master's Chamber: return False (audience hook handles
         pre-trials; Spirit hook handles in-Sanctum)
      3. Choice already committed: ack (whichever path), return True
      4. Insight not done: return False (audience hook / fallback
         dialogue handles it)
      5. Default: emit the Path menu, return True
    """
    from engine.village_trials import YARAEL_NAME
    if (npc_name or "").casefold() != YARAEL_NAME.casefold():
        return False

    try:
        room = await db.get_room(char["room_id"])
        room_name = (room or {}).get("name", "") if room else ""
    except Exception:
        room_name = ""
    if room_name != MASTERS_CHAMBER_ROOM_NAME:
        return False

    if is_choice_completed(char):
        chosen = get_chosen_path(char)
        # F.7.h: read standing for high-standing flavor lines.
        # Defensive — missing column / module returns 0.
        try:
            from engine.village_standing import get_village_standing
            standing = get_village_standing(char)
        except Exception:
            standing = 0
        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Master Yarael nods, gravely.*\033[0m"
        )
        if chosen == PATH_A:
            await session.send_line(
                "  \033[1;33m\"The road to Coruscant is long but you have "
                "walked it. The Order has you now.\"\033[0m"
            )
            if standing >= 12:
                # Player completed every trial cleanly.
                await session.send_line(
                    "  \033[2m*He pauses, then adds:*\033[0m"
                )
                await session.send_line(
                    "  \033[1;33m\"You stood in every place you were asked "
                    "to stand. The Village will speak of you. Tell Master "
                    "Windu — and remember it.\"\033[0m"
                )
        elif chosen == PATH_B:
            await session.send_line(
                "  \033[1;33m\"The Village is yours. The Force is yours. "
                "Walk well.\"\033[0m"
            )
            if standing >= 12:
                await session.send_line(
                    "  \033[2m*He smiles — small, real.*\033[0m"
                )
                await session.send_line(
                    "  \033[1;33m\"You did the work fully. The Square will "
                    "have a place for you whenever you walk through it.\"\033[0m"
                )
        elif chosen == PATH_C:
            await session.send_line(
                "  \033[1;33m\"You should not have come back here. Go.\"\033[0m"
            )
            # No high-standing flavor for Path C — Yarael's tone is
            # "go" regardless of how the trials went.
        await session.send_line("")
        return True

    if not is_path_choice_unlocked(char):
        # Insight not done yet — the audience hook will handle the
        # pre-Insight dialogue. We don't intercept.
        return False

    # Insight done, choice not yet committed. Show the menu.
    await _emit_path_menu(session, char)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# `path` command — initiate / commit
# ─────────────────────────────────────────────────────────────────────────────


async def attempt_choose_path(
    session, db, char: dict, path: Optional[str] = None,
) -> bool:
    """Player invokes `path` (no arg) or `path a|b|c`.

    No-arg call:
      - Show the Path menu (or refuse if Insight not done / choice
        already committed).

    Path-arg call:
      - Validate path is one of a/b/c.
      - Refuse if Insight not done.
      - Refuse if choice already committed.
      - Refuse Path C if not locked-in via Spirit.
      - Commit the chosen path: apply side effects, save, emit
        narration, teleport to landing room.

    Returns True if the command was processed, False on guard rejection.
    """
    # Normalize the path argument
    if path is not None:
        path = (path or "").strip().lower()

    # ── Guards ──────────────────────────────────────────────────────
    if is_choice_completed(char):
        chosen = get_chosen_path(char)
        await session.send_line(
            f"  You have already chosen Path {chosen.upper()}. "
            f"The road is set."
        )
        return False

    if not is_path_choice_unlocked(char):
        await session.send_line(
            "  The Path choice is the end of the Village quest. You must "
            "complete all five trials first — including the Trial of "
            "Insight at the Council Hut."
        )
        return False

    # ── No-arg: show menu ───────────────────────────────────────────
    if not path:
        await _emit_path_menu(session, char)
        return True

    if path not in VALID_PATHS:
        await session.send_line(
            "  Usage: path <a|b|c>. Use 'path' (no argument) to see the menu."
        )
        return False

    # ── Path-specific guards ────────────────────────────────────────
    if path == PATH_A and is_path_c_locked(char):
        await session.send_line(
            "  The Order will not have you. The road you walked in the "
            "Sanctum closed Path A. Speak with Master Yarael; only one "
            "path remains."
        )
        return False

    if path == PATH_B and is_path_c_locked(char):
        await session.send_line(
            "  The Village will not keep you. The road you walked in the "
            "Sanctum closed Path B. Speak with Master Yarael; only one "
            "path remains."
        )
        return False

    if path == PATH_C and not is_path_c_locked(char):
        await session.send_line(
            "  Path C is not open to you. The dark whispers come only to "
            "those who already heard them in the Sanctum."
        )
        return False

    # ── Commit ──────────────────────────────────────────────────────
    if path == PATH_A:
        await _commit_path_a(session, db, char)
    elif path == PATH_B:
        await _commit_path_b(session, db, char)
    else:  # PATH_C
        await _commit_path_c(session, db, char)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Path commit helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _set_chargen_flags(db, char: dict, **flags) -> None:
    """Update chargen_notes JSON with the given flags and persist."""
    notes = _read_chargen_notes(char)
    notes.update(flags)
    serialized = json.dumps(notes)
    char["chargen_notes"] = serialized
    await db.save_character(char["id"], chargen_notes=serialized)


async def _teleport(db, char: dict, slug: str) -> bool:
    """Resolve a room slug to room_id and move the character there.

    Returns True on success. If the slug can't be resolved, leaves the
    character in place and returns False (logged but non-fatal — the
    Path is still committed).
    """
    room_id = None
    try:
        # Most CW DBs store the slug in properties JSON. Try that first.
        getter = getattr(db, "get_room_by_slug", None)
        if getter is not None:
            row = await getter(slug)
            if row:
                room_id = row.get("id")
        if room_id is None:
            # Fallback: scan rooms for a properties.slug match. This is
            # O(N) but only runs once per Path commit, so the cost is
            # negligible (and the canonical slugs are guaranteed to
            # exist for CW worlds).
            scanner = getattr(db, "find_room_by_property", None)
            if scanner is not None:
                row = await scanner("slug", slug)
                if row:
                    room_id = row.get("id")
    except Exception:
        log.warning("Path teleport: room lookup failed for slug=%s",
                    slug, exc_info=True)

    if room_id is None:
        log.warning("Path teleport: could not resolve slug=%s; leaving "
                    "character at room %s", slug, char.get("room_id"))
        return False

    char["room_id"] = room_id
    await db.save_character(char["id"], room_id=room_id)
    return True


async def _commit_path_a(session, db, char: dict) -> None:
    """Path A — Jedi Order. Force-sensitive + jedi_path_unlocked +
    join jedi_order at rank 0 + teleport to Coruscant Temple gate."""
    char["village_choice_completed"] = 1
    char["village_chosen_path"] = PATH_A
    char["force_sensitive"] = 1
    await db.save_character(
        char["id"],
        village_choice_completed=1,
        village_chosen_path=PATH_A,
        force_sensitive=1,
    )
    await _set_chargen_flags(
        db, char,
        jedi_path_unlocked=True,
        village_chosen_path_a=True,
        village_trial_lightsaber_construction_pending=True,
    )

    # Best-effort org join. If the org or the API is missing, log and
    # continue — the path commit itself isn't blocked by the
    # organizations subsystem.
    try:
        get_org = getattr(db, "get_organization", None)
        join = getattr(db, "join_organization", None)
        if get_org and join:
            org = await get_org("jedi_order")
            if org and org.get("id"):
                await join(char["id"], org["id"])
    except Exception:
        log.warning("Path A: jedi_order join failed", exc_info=True)

    # Narration
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Yarael takes a small wooden box from a "
        "shelf at the back of the chamber. Inside is a tarnished bronze "
        "signet ring. He presses it onto a folded letter and places the "
        "letter in your hands.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Take this to Master Mace Windu at the Coruscant "
        "Temple. He will know the seal. He will recognise the lineage "
        "even if it has been cold for forty years. The road is short "
        "if you make it short.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2m*Days pass off-stage. A small Republic transport. A "
        "uniformed escort who does not speak. The Coruscant skyline "
        "rises through the viewport.*\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Mace Windu meets you at the Temple gate. "
        "He turns the signet over in his hand and looks at you for a "
        "long moment. Then he nods, once.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Yarael lives. Good. Come inside, late-Padawan. "
        "We have a great deal of catching up to do.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;32m* Path A — Jedi Order. *\033[0m"
    )

    # F.7.g: lightsaber construction scene at the Coruscant Apprentice
    # Forge. Best-effort: construction failure (missing crystal,
    # write error, etc.) does not block the Path A commit. The
    # construction module records its own failure marker for a
    # future retry path.
    try:
        from engine.lightsaber_construction import construct_lightsaber
        await construct_lightsaber(session, db, char)
    except Exception:
        log.warning(
            "Path A: lightsaber construction failed",
            exc_info=True,
        )

    moved = await _teleport(db, char, PATH_A_DROP_SLUG)
    if moved:
        await session.send_line(
            f"  \033[2mYou arrive at the Coruscant Jedi Temple gate. "
            f"The Tutorial Jedi Path will guide you from here.\033[0m"
        )
    else:
        await session.send_line(
            f"  \033[2m(Engine note: Temple gate room not yet wired in "
            f"this world; you remain in the Master's Chamber. "
            f"Path A flags are set.)\033[0m"
        )
    await session.send_line("")


async def _commit_path_b(session, db, char: dict) -> None:
    """Path B — Independent. Force-sensitive + jedi_path_unlocked +
    join independent (+50 rep) + teleport to Common Square. Crystal
    is preserved (uncommitted)."""
    char["village_choice_completed"] = 1
    char["village_chosen_path"] = PATH_B
    char["force_sensitive"] = 1
    await db.save_character(
        char["id"],
        village_choice_completed=1,
        village_chosen_path=PATH_B,
        force_sensitive=1,
    )
    await _set_chargen_flags(
        db, char,
        jedi_path_unlocked=True,
        village_chosen_path_b=True,
    )

    try:
        get_org = getattr(db, "get_organization", None)
        join = getattr(db, "join_organization", None)
        adjust = getattr(db, "adjust_rep", None)
        if get_org and join:
            org = await get_org("independent")
            if org and org.get("id"):
                await join(char["id"], org["id"])
                if adjust:
                    await adjust(char["id"], "independent", 50)
    except Exception:
        log.warning("Path B: independent join failed", exc_info=True)

    # Narration
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Yarael smiles, slowly. He does not move "
        "from his seat.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"The Village is yours as much as it is mine. The "
        "Force is yours; the Order has no claim it can press without "
        "your asking. Walk well. Come back, when you can.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2m*The crystal stays where it is, on the cord at your "
        "neck. It is yours; it has not yet been asked to be anything in "
        "particular. Master Yarael does not name it.*\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;32m* Path B — Independent. *\033[0m"
    )

    moved = await _teleport(db, char, PATH_B_DROP_SLUG)
    if moved:
        await session.send_line(
            f"  \033[2mYou step into the Common Square. The Village is "
            f"open to you. So is the rest of the galaxy.\033[0m"
        )
    else:
        await session.send_line(
            f"  \033[2m(Engine note: Common Square room not resolved in "
            f"this world; you remain in the Master's Chamber. "
            f"Path B flags are set.)\033[0m"
        )
    await session.send_line("")


async def _commit_path_c(session, db, char: dict) -> None:
    """Path C — Dark whispers. Force-sensitive + dark_path_unlocked
    + dark_contact_freq item marker + teleport to anchor stones. NO
    org join (Path C is exiled). NOT jedi_path_unlocked."""
    char["village_choice_completed"] = 1
    char["village_chosen_path"] = PATH_C
    char["force_sensitive"] = 1
    await db.save_character(
        char["id"],
        village_choice_completed=1,
        village_chosen_path=PATH_C,
        force_sensitive=1,
    )
    await _set_chargen_flags(
        db, char,
        dark_path_unlocked=True,
        village_chosen_path_c=True,
        dark_contact_freq=True,  # item marker; future drop will wire the comlink
    )

    # Narration
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Yarael writes something on a small slip of "
        "flimsi. He folds it twice and presses it into your hand. He "
        "does not look at you. The expression on his face is not anger; "
        "it is something quieter and worse.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"This is a comlink frequency. Do not open it here. "
        "Do not open it where any of us can hear. The road you are on "
        "does not return through this door. Go.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2m*The Village's Apprentice Tents are quiet as you "
        "leave. Sister Vitha is at the Gate. She does not stop you. "
        "She does not say goodbye. The dunes outside are the same dunes "
        "you walked weeks ago, and they are not the same at all.*\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;31m* Path C — Dark whispers. *\033[0m"
    )

    moved = await _teleport(db, char, PATH_C_DROP_SLUG)
    if moved:
        await session.send_line(
            f"  \033[2mYou come to a clearing of standing stones in the "
            f"Dune Sea. The frequency in your hand has not yet answered "
            f"when called. It will, in time. Or it will not.\033[0m"
        )
    else:
        await session.send_line(
            f"  \033[2m(Engine note: Anchor Stones room not resolved in "
            f"this world; you remain in the Master's Chamber. "
            f"Path C flags are set.)\033[0m"
        )
    await session.send_line("")
