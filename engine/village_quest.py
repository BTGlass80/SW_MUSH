# -*- coding: utf-8 -*-
"""
engine/village_quest.py — Jedi Village quest state machine (Drop F.7.a, May 3 2026).

State-machine engine that owns transitions on the
``characters.village_act`` and ``characters.village_trial_*`` columns
(landed in PG.1.schema). Mirrors the architecture of
``engine/spacer_quest.py``: a single ``check_village_quest()`` entry
called from command-handler post-hooks, dispatching to per-step
trigger handlers.

Architecture
============

State lives in dedicated columns on the ``characters`` table (per
PG.1.schema, NOT in attributes JSON like spacer_quest):

  - ``village_act``               INTEGER 0–3
                                  0 = pre-invitation
                                  1 = invited (post-Hermit)
                                  2 = in-trials
                                  3 = passed (Padawan)
  - ``village_act_unlocked_at``   REAL    Unix timestamp of last act transition
  - ``village_trial_courage_done`` 0|1
  - ``village_trial_insight_done`` 0|1
  - ``village_trial_flesh_done``   0|1
  - ``village_trial_last_attempt`` REAL    Unix timestamp of last trial attempt

The column-based design is deliberate: progression-gate state is
queryable for admin/debug commands and integrates with the existing
``engine/jedi_gating.py`` cooldown read-helpers.

Step layout (per data/worlds/clone_wars/quests/jedi_village.yaml)
================================================================

  Step  Act  Title                Completion type
  ----  ---  -------------------  ----------------------------------
  1     1    The Invitation       command_executed (or Hermit talk)
  2     2    Crossing the Dunes   room_entered
  3     2    The Gate             dialogue_completion        (TODO F.7.b)
  4     2    First Audience       talk_to_npc                (TODO F.7.b)
  5     2    Trial of Skill       skill_check_passed         (TODO F.7.c)
  6     2    Trial of Courage     dialogue_completion        (TODO F.7.c)
  7     2    Trial of Flesh       timed_room_dwell           (TODO F.7.c)
  8     2    Trial of Spirit      multi_turn_dialogue        (TODO F.7.d)
  9     2    Trial of Insight     targeted_choice            (TODO F.7.c)
  10    3    The Choice           path_choice                (TODO F.7.d)

Drop F.7.a wires steps 1 and 2 only. Steps 3–10 are stubbed: the
state machine recognizes them as "the next step" and returns
status-only descriptions rather than firing transitions. Each
stubbed step has a clear seam where its runtime handler will
plug in (``_step_N_handle_*``).

Hooks
=====

``check_village_quest(session, db, trigger, **kw)`` is called from:

  - parser/npc_commands.py::TalkCommand._post_talk_hooks
      trigger="talk", npc_name=...
      Drives Step 1 (Hermit invitation delivery).
  - parser/builtin_commands.py::MoveCommand._post_move_hooks
      trigger="room_entered", room_id=..., room_slug=...
      Drives Step 2 (Crossing the Dunes — arrival at village_outer_watch).

Future drops (F.7.b+) add additional triggers as needed:
  - trigger="dialogue_choice", dialogue_id=..., choice=...   (steps 3, 6, 9)
  - trigger="skill_check", skill=..., difficulty=..., success=...  (step 5)
  - trigger="room_dwell_complete", room_slug=..., duration_s=...  (step 7)
  - trigger="multi_turn_complete", dialogue_id=..., outcome=...   (step 8)
  - trigger="path_chosen", branch=...                       (step 10)

Idempotency
===========

The state machine is idempotent: calling ``check_village_quest()``
with the same trigger multiple times after the transition has
already fired is a no-op. The ``village_act`` column is the
single source of truth; transitions only fire when the current
state is the predecessor state.

Gate consultation
=================

Step 1 consults ``engine.hermit.is_invitation_eligible()`` to
decide whether the Hermit's after_lines fire. Step 2 consults
``engine.jedi_gating.act_2_unlock_ready()`` to enforce the 7-day
Act 1→2 cooldown (per progression_gates_and_consequences §2.5).

What this drop does NOT do
==========================

  - Does not fire the talk-to dialogue runtime that selects
    ``gate.before_lines`` vs ``gate.after_lines``. The Hermit's
    fallback_lines still serve as the talk-to surface; the
    invitation delivery is recorded as a state-machine fact via
    village_act = 1, but the Hermit's authored "after_lines"
    aren't yet displayed in the talk-to flow. F.7.b will do that.
  - Does not implement the trial runtimes (steps 5–9). The
    completion types are diverse enough that each warrants its
    own contained drop.
  - Does not implement the graduation choice (step 10). Path
    branching has its own design weight.

See ``HANDOFF_MAY03_F7A_VILLAGE_QUEST.md`` for the full drop scope.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants — act state values
# ─────────────────────────────────────────────────────────────────────────────

ACT_PRE_INVITATION: int = 0
ACT_INVITED: int = 1
ACT_IN_TRIALS: int = 2
ACT_PASSED: int = 3


# Fixed slug strings for room-arrival recognition. These match the
# ``id:`` field on the corresponding landmark in
# ``data/worlds/clone_wars/wilderness/dune_sea.yaml``. The wilderness
# writer (post-F.7.a) emits them as ``properties.slug`` on each
# landmark room, so room-entered hooks can match by slug rather
# than display name.
HERMIT_HUT_SLUG: str = "hermit_hut"
ANCHOR_STONES_SLUG: str = "dune_sea_anchor_stones"
VILLAGE_OUTER_WATCH_SLUG: str = "village_outer_watch"


# Hermit name as authored in
# ``data/worlds/clone_wars/wilderness_npcs.yaml``. Compared
# case-insensitively at the call site.
HERMIT_NAME: str = "the Hermit"


# ─────────────────────────────────────────────────────────────────────────────
# Public API: read-helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_village_state(char: Mapping) -> dict:
    """Summarize a character's Village quest progression.

    Useful for admin/debug commands and quest-status display.
    All values are read-only snapshots; nothing here mutates state.

    Args:
        char: a character dict with the village_* PG.1.schema columns.
            Missing fields default safely.

    Returns:
        dict with keys:
          - ``act``                int   (0–3)
          - ``act_label``          str   ('pre_invitation' | 'invited' | 'in_trials' | 'passed')
          - ``act_unlocked_at``    float (Unix timestamp, or 0 if never)
          - ``current_step``       int|None  (1–10, or None if not in quest)
          - ``trial_courage_done`` bool
          - ``trial_insight_done`` bool
          - ``trial_flesh_done``   bool
          - ``trials_completed``   int   (0–3)
          - ``trial_last_attempt`` float
    """
    act = int(char.get("village_act") or 0)
    return {
        "act": act,
        "act_label": _act_label(act),
        "act_unlocked_at": float(char.get("village_act_unlocked_at") or 0),
        "current_step": current_step(char),
        "trial_courage_done": bool(char.get("village_trial_courage_done")),
        "trial_insight_done": bool(char.get("village_trial_insight_done")),
        "trial_flesh_done": bool(char.get("village_trial_flesh_done")),
        "trials_completed": _trials_completed(char),
        "trial_last_attempt": float(char.get("village_trial_last_attempt") or 0),
    }


def current_step(char: Mapping) -> Optional[int]:
    """Return the step number this character is currently on, or None.

    Mapping from (act, trials_done) to step number (per the YAML's
    step ordering):

      act 0                     -> step 1 (waiting for invitation)
      act 1                     -> step 2 (Crossing the Dunes)
      act 2, 0 trials done      -> step 3 (The Gate)
      act 2, with first audience -> step 4–9 (trials in any order; design TODO)
      act 3                     -> step 10 (The Choice — already passed)

    For F.7.a, this returns 1 or 2 reliably; for higher acts it returns
    a representative step but does not yet distinguish between the
    in-progress trial sub-steps (that's F.7.b–c).
    """
    act = int(char.get("village_act") or 0)
    if act == ACT_PRE_INVITATION:
        return 1
    if act == ACT_INVITED:
        return 2
    if act == ACT_IN_TRIALS:
        # Pending refinement in F.7.b — for now, just signal "in trials".
        # Returning the lowest unfinished trial step approximates state.
        if not char.get("village_trial_courage_done"):
            return 6  # Trial of Courage
        if not char.get("village_trial_flesh_done"):
            return 7  # Trial of Flesh
        if not char.get("village_trial_insight_done"):
            return 9  # Trial of Insight
        return 10  # all trials done, awaiting Choice
    if act == ACT_PASSED:
        return None  # quest complete
    return None  # unknown state — defensive


def is_in_quest(char: Mapping) -> bool:
    """True iff the character has at least received the invitation.

    A convenience wrapper for code that wants 'has the player engaged
    with the Village quest at all?' without having to compare integers.
    """
    return int(char.get("village_act") or 0) >= ACT_INVITED


def has_completed(char: Mapping) -> bool:
    """True iff the character has completed the Village quest (ACT_PASSED)."""
    return int(char.get("village_act") or 0) >= ACT_PASSED


# ─────────────────────────────────────────────────────────────────────────────
# Public API: state transitions
# ─────────────────────────────────────────────────────────────────────────────

async def deliver_invitation(char: dict, db) -> bool:
    """Flip village_act 0 -> 1 (pre-invitation -> invited).

    Idempotent: returns True if the transition fired this call,
    False if it was already past act 0 (or higher). The character
    dict is mutated in place to reflect the new state, AND the DB
    row is updated.

    Per progression_gates_and_consequences_design_v1.md §2.5:
    delivering the invitation also stamps ``village_act_unlocked_at``,
    which drives the 7-day cooldown before Act 2 entry is allowed.

    Caller is expected to have verified
    ``engine.hermit.is_invitation_eligible(char)`` is True. This
    function does NOT re-check, so it can also be used by admin
    commands to grant the invitation directly.

    Args:
        char: character dict (mutated in place)
        db: Database instance with save_character()

    Returns:
        True if the transition fired this call; False if no-op.
    """
    current = int(char.get("village_act") or 0)
    if current >= ACT_INVITED:
        return False  # already invited or further along

    now = time.time()
    char["village_act"] = ACT_INVITED
    char["village_act_unlocked_at"] = now
    await db.save_character(
        char["id"],
        village_act=ACT_INVITED,
        village_act_unlocked_at=now,
    )
    log.info(
        "Village quest: character %d (%s) received the invitation; "
        "village_act 0->1 at %.0f",
        char.get("id", -1), char.get("name", "?"), now,
    )
    return True


async def enter_trials(char: dict, db) -> bool:
    """Flip village_act 1 -> 2 (invited -> in-trials).

    Fires when the character arrives at village_outer_watch (Step 2
    completion). Stamps ``village_act_unlocked_at`` to the current
    time so any future inter-act cooldown read-helpers measure from
    this instant.

    Note: per ``progression_gates_and_consequences_design_v1.md``
    §2.5, the 7-day cooldown is *between Act 1 and Act 2*. F.7.a
    implements arrival as the Act 2 trigger (with a soft cooldown
    check); a stricter "you must wait 7 days after invitation"
    enforcement can be added in F.7.b without changing this seam.

    Args:
        char: character dict (mutated in place)
        db: Database instance with save_character()

    Returns:
        True if the transition fired this call; False if no-op.
    """
    current = int(char.get("village_act") or 0)
    if current >= ACT_IN_TRIALS:
        return False
    if current < ACT_INVITED:
        return False  # must be invited first

    now = time.time()
    char["village_act"] = ACT_IN_TRIALS
    char["village_act_unlocked_at"] = now
    await db.save_character(
        char["id"],
        village_act=ACT_IN_TRIALS,
        village_act_unlocked_at=now,
    )
    log.info(
        "Village quest: character %d (%s) entered Act 2 (in trials); "
        "village_act 1->2 at %.0f",
        char.get("id", -1), char.get("name", "?"), now,
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Main hook entry — called from command-handler post-hooks
# ─────────────────────────────────────────────────────────────────────────────

async def check_village_quest(session, db, trigger: str, **kw) -> None:
    """Main hook entry. Dispatches to per-trigger handlers.

    Mirrors the signature of ``engine.spacer_quest.check_spacer_quest``
    so call-site integration is uniform across quest systems.

    Robustness: every handler call is wrapped in a try/except inside
    this dispatcher. A bug in one trigger handler must not break
    movement, talking, or other commands. Non-fatal errors are
    logged and swallowed.

    Args:
        session: the player session (must have .character)
        db: Database instance
        trigger: one of "talk", "room_entered", and (future)
                 "dialogue_choice", "skill_check", "room_dwell_complete",
                 "multi_turn_complete", "path_chosen"
        **kw: trigger-specific arguments. See module docstring.

    Returns:
        None. Side effects only (state transitions, in-band messages).
    """
    char = getattr(session, "character", None)
    if not char:
        return

    try:
        if trigger == "talk":
            await _handle_talk(session, db, char, kw)
        elif trigger == "room_entered":
            await _handle_room_entered(session, db, char, kw)
        # Future triggers: dialogue_choice, skill_check, etc. The
        # else branch is a silent no-op so unknown triggers don't
        # poison call sites.
        else:
            return
    except Exception as exc:
        # Same defensive posture as spacer_quest: non-fatal, log, swallow.
        log.warning(
            "check_village_quest(trigger=%r) failed: %s",
            trigger, exc, exc_info=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: The Invitation (act 0 -> 1)
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_talk(session, db, char: dict, kw: dict) -> None:
    """Talk-to handler. Step 1: Hermit delivers the invitation.

    Triggered when the player talks to any NPC. We only act if:
      - The NPC is the Hermit (case-insensitive name match)
      - The player is at act 0 (pre-invitation)
      - The player is invitation-eligible per the F.6 gate seam
        (i.e. force_signs_accumulated >= FORCE_SIGNS_FOR_INVITATION)

    On success, fires ``deliver_invitation()`` and sends a one-time
    invitation-delivered message to the player. Future F.7.b will
    replace this with the Hermit's authored after_lines from the
    gate block.
    """
    npc_name = (kw.get("npc_name") or "").strip()
    if not npc_name:
        return
    if npc_name.casefold() != HERMIT_NAME.casefold():
        return  # not talking to the Hermit; no-op

    act = int(char.get("village_act") or 0)
    if act != ACT_PRE_INVITATION:
        return  # already invited or past; no re-fire

    # Eligibility gate — F.6 contract.
    from engine.hermit import is_invitation_eligible
    if not is_invitation_eligible(char):
        return  # Hermit doesn't deliver the invitation yet

    fired = await deliver_invitation(char, db)
    if fired:
        # One-time invitation-delivered message. Kept short and
        # state-machine-facing; the Hermit's authored "after_lines"
        # are still being delivered through the standard talk-to
        # flow alongside this. F.7.b replaces the talk-to flow
        # itself with the gate-aware dialogue runtime.
        try:
            await session.send_line(
                "\n  \033[1;33m* The Hermit's words have meaning now. "
                "You have been invited to the Village. *\033[0m\n"
                "  \033[2mWalk west from the Anchor Stones at first light. "
                "(Use 'quest' to view your progress.)\033[0m\n"
            )
        except Exception:
            log.debug("send_line failed for invitation message", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Crossing the Dunes (act 1 -> 2)
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_room_entered(session, db, char: dict, kw: dict) -> None:
    """Room-entered handler. Step 2: arrival at village_outer_watch.

    Triggered when the player enters any room. We only act if:
      - The room's slug is village_outer_watch
      - The player is at act 1 (invited but not yet in trials)

    On success, fires ``enter_trials()`` and sends a one-time
    arrival message.
    """
    room_slug = (kw.get("room_slug") or "").strip()
    if not room_slug:
        # Caller didn't pass the slug — try to look it up from the room_id.
        room_id = kw.get("room_id")
        if room_id:
            room_slug = await _lookup_room_slug(db, room_id) or ""
        if not room_slug:
            return

    if room_slug != VILLAGE_OUTER_WATCH_SLUG:
        return  # not the trigger room

    act = int(char.get("village_act") or 0)
    if act != ACT_INVITED:
        return  # not at the right act state

    fired = await enter_trials(char, db)
    if fired:
        try:
            await session.send_line(
                "\n  \033[1;36m* You have crossed into the Village's outer watch. *\033[0m\n"
                "  \033[2mAhead lies the Gate. The Village will decide if "
                "you may pass.\033[0m\n"
            )
        except Exception:
            log.debug("send_line failed for arrival message", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _act_label(act: int) -> str:
    """Map village_act integer to human-readable label."""
    return {
        ACT_PRE_INVITATION: "pre_invitation",
        ACT_INVITED: "invited",
        ACT_IN_TRIALS: "in_trials",
        ACT_PASSED: "passed",
    }.get(act, "unknown")


def _trials_completed(char: Mapping) -> int:
    """Count of completed trials (0–3)."""
    return (
        int(bool(char.get("village_trial_courage_done")))
        + int(bool(char.get("village_trial_insight_done")))
        + int(bool(char.get("village_trial_flesh_done")))
    )


async def _lookup_room_slug(db, room_id: int) -> Optional[str]:
    """Resolve a room's slug from its properties JSON.

    Returns None if the room doesn't exist, or has no properties.slug
    field. Used by the room-entered handler when the caller doesn't
    pre-resolve the slug. Best-effort and silent on errors so a
    room-lookup failure cannot poison the room-entered hook chain.
    """
    try:
        rows = await db._db.execute_fetchall(
            "SELECT properties FROM rooms WHERE id = ? LIMIT 1",
            (room_id,),
        )
        if not rows:
            return None
        props_raw = rows[0]["properties"]
        if not props_raw:
            return None
        props = json.loads(props_raw)
        return props.get("slug")
    except Exception:
        log.debug("_lookup_room_slug failed for room_id=%r", room_id, exc_info=True)
        return None
