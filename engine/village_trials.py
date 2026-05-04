# -*- coding: utf-8 -*-
"""
engine/village_trials.py — Village quest Trials runtime (F.7.c.4, May 4 2026).

Per ``jedi_village_quest_design_v1.md`` §5: five Trials.

  - F.7.c.1: Trial 1 (Skill — Daro at the Forge), Trial 5 (Insight —
    Saro at the Council Hut).
  - F.7.c.2: Trial 2 (Courage — Mira at the Common Square); Insight
    gate tightened to require Courage.
  - F.7.c.3: Trial 3 (Flesh — Korvas at the Meditation Caves); Insight
    gate tightened to also require Flesh.
  - **F.7.c.4 (this revision): Trial 4 (Spirit — Master Yarael in the
    Sealed Sanctum)**; Insight gate tightened to also require Spirit.
    All five trials now live.

Trial dispatch
==============

Each trial NPC has a hook function that is called from
``engine/village_quest.py::_handle_talk`` when a PC talks to that
NPC. The hook returns True if it intercepted (no AI dialogue
follows) or False (fall through to standard NPC dialogue).

  - ``maybe_handle_daro_skill_trial`` — Smith Daro (Forge)
  - ``maybe_handle_mira_courage_trial`` — Elder Mira Delen (Common Square)
  - ``maybe_handle_korvas_flesh_trial`` — Elder Korvas (Meditation Caves)
  - ``maybe_handle_yarael_spirit_trial`` — Master Yarael in the Sealed
    Sanctum (NB: distinct from his Master's-Chamber audience hook
    in ``engine/village_dialogue.py``).
  - ``maybe_handle_saro_insight_trial`` — Elder Saro Veck (Council Hut)

Audience prerequisite
=====================

All trial NPCs check the F.7.b first-audience flag
(``chargen_notes['village_first_audience_done']``). If the player
has not yet had the audience with Master Yarael, trial NPCs
deflect with a "first speak to the Master" message rather than
running the trial. This keeps the design's required sequencing in
force without needing a separate Yarael-audience-completion column.

Trial sequencing
================

Per design §5.2: trials must be done Skill → Courage → Flesh →
Spirit → Insight. F.7.c.4 ships all five.

  - Skill: requires audience_done. No prior trial gating.
  - Courage: requires audience_done AND skill_done.
  - Flesh: requires audience_done AND skill_done AND courage_done.
  - Spirit: requires audience_done AND skill_done AND courage_done
    AND flesh_done.
  - Insight: requires audience_done AND skill_done AND courage_done
    AND flesh_done AND spirit_done.

Trial 1: Skill (Smith Daro)
============================

Mechanic:
  - 3-step sequence of ``craft_lightsaber`` skill checks at
    increasing difficulties: 8, 12, 15.
  - Each ``trial skill`` command attempt executes one step.
  - Pass: increment ``village_trial_skill_step``; show progress; if
    step reaches 3, mark trial done + grant the crystal item.
  - Fail: 1-hour cooldown before the next attempt. Step counter
    not reset (failures don't lose progress; you just have to wait).

Player commands:
  - ``trial skill`` — initiate one attempt at the current difficulty
  - ``status`` (existing) — shows progress (no F.7.c.1 changes)
  - ``talk Daro`` — ambient flavor + restate state via fallback_lines

Trial 5: Insight (Elder Saro Veck)
===================================

Mechanic:
  - Three holocron fragments. One contains a doctrinal tell ("the
    Force *belongs* to those who can wield it"); two are authentic.
  - On first encounter, the runtime selects a random correct
    fragment 1..3 and persists it to
    ``village_trial_insight_correct_fragment``. This means retries
    don't shuffle — same player gets same answer until passed.
  - ``examine fragment_<N>`` (or ``listen fragment_<N>``) plays the
    fragment text.
  - ``accuse fragment_<N>`` commits the answer.
  - Wrong: hint ("Saro says: 'Listen again.'") + retry, no cooldown.
  - Correct: grant ``village_pendant`` item, mark trial done.

Player commands:
  - ``trial insight`` — initiates the trial (presents the 3 fragments)
  - ``examine fragment_1`` / ``listen fragment_1`` etc. — plays a fragment
  - ``accuse fragment_<N>`` — commits the answer
  - ``talk Saro`` — ambient + state restatement

Trial 2: Courage (Elder Mira Delen) — F.7.c.2
==============================================

Mechanic:
  - Single-turn, three-choice dialogue at the Common Square. Mira
    recites a "buried memory" derived from the PC's narrative
    (`+background` if set; otherwise a species/faction-aware
    template). The PC then picks one of three responses.
  - Choices:
      [1] "I won't deny it."          → Pass.
      [2] "How did you know?"         → Pass (Mira nods deeper; no
                                        mechanical bonus in F.7.c.2 —
                                        a future drop with `village_standing`
                                        will track the deeper acknowledgement).
      [3] "leave" / walk away         → Fail; 24-hour real-time
                                        cooldown anchored on
                                        ``village_trial_courage_lockout_until``.
  - There is no other failure mode. Standing in the Square and
    hearing it through is the test.

Player commands:
  - ``trial courage`` — initiate the recital + present the three options
  - ``trial courage 1`` / ``trial courage 2`` / ``trial courage 3``
    — commit the response
  - ``talk Mira`` — ambient + state restatement

Trial 3: Flesh (Elder Korvas) — F.7.c.3
========================================

Mechanic:
  - 6-hour wall-clock dwell in the Meditation Caves. The trial
    starts when the player enters the Meditation Caves with the
    Courage trial done; ``village_trial_flesh_started_at`` is
    anchored on first cave-entry.
  - Completion fires the next time the player enters or interacts
    with the cave after 6 hours have elapsed since started_at.
    Korvas appears at the cave entrance and the discipline is
    complete.
  - The trial cannot be failed and cannot be cancelled mid-flight.
    Leaving and returning works (the wall-clock keeps running);
    logout works (same).

Design note (deviation from spec):
  Design §5.2 + §10.2 propose "6 hours of session time, with
  logout-pausing." That requires hooking the session lifecycle and
  carries a class of edge-case bugs (server crashes, missed close
  events). F.7.c.3 ships **wall-clock from cave entry** as the
  engineering-simplest defensible model. The hybrid (4h-session +
  12h-floor) is forward-additive if Brian wants the heavier weight
  later — it's documented in the F.7.c.3 handoff.

Reward:
  Per design, Korvas teaches ``enhance_attribute`` (Strength) Force
  power. The ``learned_force_powers`` system doesn't yet exist in
  the engine. F.7.c.3 records the teaching as a chargen_notes
  marker (``village_trial_flesh_strength_taught: True``); a future
  drop with the actual learned-Force-power consumer will read this
  and grant the buff.

Player commands:
  - ``trial flesh`` — show progress (time elapsed / time remaining);
    triggers the completion check if time is up
  - ``talk Korvas`` — ambient + state restatement

Trial 4: Spirit (Master Yarael) — F.7.c.4
==========================================

Mechanic:
  - Multi-turn dialogue (5–7 turns) with the player's "dark-future
    self." The player's responses each turn fall into one of three
    categories: rejection (pushes toward "I am not him"), temptation
    (pushes toward "I am him already"), or ambivalent (neither).
  - Pass condition: 4+ rejections, at any turn count up to 7.
  - Hard fail / Path C lock-in: 3 temptations triggers an irreversible
    Path C lock (``village_trial_spirit_path_c_locked = 1``). Per
    design §7.3, this re-shapes Master Yarael's future Path-choice
    dialogue (Path A/B suppressed; only Path C offered). The Spirit
    trial itself ends as "passed" so the player can proceed to the
    Insight trial and the Path choice — Path C is a path, not a
    quest-blocker.
  - Soft fail: 7 turns elapse with neither pass nor Path C condition
    met → trial ends without ``village_trial_spirit_done = 1``. The
    player may re-enter the Sanctum and start a new pass (state is
    reset on re-entry). There is no real-time cooldown — the spirit
    can be tried as many times as needed.

Composition of the dark-future-self speech:
  Per design §5.2: "The Director uses the character's backstory +
  recent kills + faction rep to populate the dark-future-self."
  F.7.c.4 ships a deterministic composer (faction-aware templates)
  for the same engineering reasons that Courage's recital composer
  was deterministic: the Director's solo-PC dialogue surface
  doesn't yet exist, the trial must run when the Director is offline,
  and a Director-aware swap is forward-additive without changing the
  trial flow.

Schema (v24, this drop):
  - ``village_trial_spirit_turn``  INTEGER — current turn 1..7
  - ``village_trial_spirit_path_c_locked``  INTEGER — bool, irreversible

Existing v22 columns used unchanged:
  - ``village_trial_spirit_done``        INTEGER bool
  - ``village_trial_spirit_dark_pull``   INTEGER 0..3
  - ``village_trial_spirit_rejections``  INTEGER toward 4 (pass)

Player commands:
  - ``trial spirit`` — initiate the trial (must be in the Sealed
    Sanctum); presents the opening of the dark-future-self speech
    and the three response options for turn 1
  - ``trial spirit 1|2|3`` — commit a response (1=rejection,
    2=ambivalent, 3=temptation). The runtime advances to the next
    turn and either presents the next prompt or fires completion.
  - ``talk Yarael`` (in Sealed Sanctum) — ambient + state restatement
    (NB: ``talk Yarael`` in Master's Chamber still routes to the
    audience hook in ``engine/village_dialogue.py``)
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Mapping, Optional

log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# F.7.k — Inter-trial cooldown gate helper
# ═════════════════════════════════════════════════════════════════════════════
#
# Per progression_gates_and_consequences_design_v1.md §2.5, successful
# trials are separated by a 14-day real-time cooldown. The helpers in
# engine/jedi_gating do the math; this helper applies it at the point
# of trial entry and emits the soft refusal narration.
#
# A trial is gated by the inter-trial cooldown if all of:
#   - the trial is NOT already done (don't deflect a "you've done this"
#     ack — that path is fine and runs separately)
#   - the trial is NOT actively started yet (don't interrupt mid-trial;
#     a Flesh PC who just entered the cave should not get a "wait" message
#     when she talks back to Korvas)
#   - village_trial_last_attempt > 0 AND the gate's predicate fails
#
# The "actively started" check is per-trial because each trial uses
# different state to indicate "in progress." Callers pass in their
# trial-specific in-progress predicate.

async def _maybe_emit_inter_trial_cooldown(
    session, char: dict, *, in_progress: bool,
) -> bool:
    """Check the 14-day inter-trial gate; emit the deflect if blocked.

    Returns True iff the gate blocked the player (caller should return
    True / stop further trial-entry processing). Returns False if the
    gate passed (or doesn't apply because the trial is in progress or
    no prior attempt exists).

    Args:
        session: the player session (for sending lines)
        char: character dict
        in_progress: True if the trial is mid-flight (don't gate)

    Returns:
        True if blocked + deflect was emitted; False otherwise.
    """
    if in_progress:
        return False
    last = float(char.get("village_trial_last_attempt") or 0)
    if last <= 0:
        # No prior trial attempt — first trial of the sequence is
        # always allowed.
        return False

    try:
        from engine.jedi_gating import (
            trial_gate_passed,
            trial_cooldown_seconds_remaining,
            format_remaining,
        )
    except Exception:
        # Fail-soft: if the jedi_gating module is broken, don't
        # block the player.
        log.warning(
            "village_trials: jedi_gating import failed; "
            "inter-trial cooldown check skipped (permissive).",
            exc_info=True,
        )
        return False

    if trial_gate_passed(char):
        return False

    remaining = trial_cooldown_seconds_remaining(char)
    pretty = format_remaining(remaining)
    await session.send_line("")
    await session.send_line(
        "  \033[2m*The elder looks at you with patience that is not "
        "the same as encouragement. The Village does not run trials "
        "back to back; the next one will keep.*\033[0m"
    )
    await session.send_line(
        f"  \033[2mCome back in {pretty}. Spend the time as you "
        f"would. The trial will be here.\033[0m"
    )
    await session.send_line("")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# NPC names + room slugs (match jedi_village_npcs.yaml)
# ─────────────────────────────────────────────────────────────────────────────

DARO_NAME: str = "Smith Daro"
MIRA_NAME: str = "Elder Mira Delen"
KORVAS_NAME: str = "Elder Korvas"
SARO_NAME: str = "Elder Saro Veck"
SELA_NAME: str = "Padawan Sela"

FORGE_ROOM_NAME: str = "The Forge"
COUNCIL_HUT_ROOM_NAME: str = "Council Hut"
COMMON_SQUARE_ROOM_NAME: str = "Common Square"
MEDITATION_CAVES_ROOM_NAME: str = "Meditation Caves"
SEALED_SANCTUM_ROOM_NAME: str = "The Sealed Sanctum"
YARAEL_NAME: str = "Master Yarael Tinré"


# ─────────────────────────────────────────────────────────────────────────────
# Trial 1: Skill — constants
# ─────────────────────────────────────────────────────────────────────────────

SKILL_DIFFICULTIES = [8, 12, 15]   # difficulties for steps 1, 2, 3
SKILL_STEPS_REQUIRED = 3
SKILL_RETRY_COOLDOWN_SECONDS = 60 * 60   # 1 hour
SKILL_TRIAL_SKILL = "craft_lightsaber"


# ─────────────────────────────────────────────────────────────────────────────
# Trial 2: Courage — constants
# ─────────────────────────────────────────────────────────────────────────────

COURAGE_FAIL_COOLDOWN_SECONDS = 24 * 60 * 60   # 24 hours real-time

# Choice constants. See the Courage section of the module docstring.
COURAGE_CHOICE_ACKNOWLEDGE = 1   # "I won't deny it." → pass
COURAGE_CHOICE_QUESTION    = 2   # "How did you know?" → pass + nod
COURAGE_CHOICE_WALK_AWAY   = 3   # leave → fail + 24h cooldown
COURAGE_PASS_CHOICES = (COURAGE_CHOICE_ACKNOWLEDGE, COURAGE_CHOICE_QUESTION)
COURAGE_VALID_CHOICES = (
    COURAGE_CHOICE_ACKNOWLEDGE,
    COURAGE_CHOICE_QUESTION,
    COURAGE_CHOICE_WALK_AWAY,
)


# ─────────────────────────────────────────────────────────────────────────────
# Trial 3: Flesh — constants
# ─────────────────────────────────────────────────────────────────────────────

FLESH_DURATION_SECONDS = 6 * 60 * 60   # 6 hours wall-clock from cave entry


# ─────────────────────────────────────────────────────────────────────────────
# Trial 4: Spirit — constants
# ─────────────────────────────────────────────────────────────────────────────

SPIRIT_MAX_TURNS         = 7   # hard cap on dialogue length
SPIRIT_REJECTIONS_TO_PASS = 4   # need ≥4 to pass
SPIRIT_DARK_PULL_TO_LOCK_C = 3  # dark_pull ≥3 → Path C lock + trial ends "passed"

# Choice constants (mirror the Courage choice convention).
SPIRIT_CHOICE_REJECTION  = 1   # "I am not him" / pushback
SPIRIT_CHOICE_AMBIVALENT = 2   # "I don't know" / neutral
SPIRIT_CHOICE_TEMPTATION = 3   # "Maybe he's right" / pull
SPIRIT_VALID_CHOICES = (
    SPIRIT_CHOICE_REJECTION,
    SPIRIT_CHOICE_AMBIVALENT,
    SPIRIT_CHOICE_TEMPTATION,
)


# ─────────────────────────────────────────────────────────────────────────────
# Trial 5: Insight — constants
# ─────────────────────────────────────────────────────────────────────────────

# The three fragments. Each is a short Master speech. The "Sith" entry
# contains the doctrinal tell — the word "belongs" applied to the
# Force. The other two are authentic Jedi-doctrine speech.
INSIGHT_FRAGMENTS = {
    1: {
        "speaker": "Master Vell-Tor of Ossus, c. 5,000 BBY",
        "lines": [
            "We do not own the Force. We do not command it.",
            "We are vessels through which it moves; we are the cup,",
            "and the water is not ours to keep.",
        ],
        "is_sith": False,
    },
    2: {
        "speaker": "Master Drell of the Old Order, era unknown",
        "lines": [
            "The Force is the right of those who can wield it.",
            "It belongs to the strong; the weak give it back.",
            "There is no shame in claiming what is yours by mastery.",
        ],
        "is_sith": True,
    },
    3: {
        "speaker": "Master Aanya Tor, recorded in the Late Republic",
        "lines": [
            "The Force passes through us. We do not direct it; we listen.",
            "When we serve well, we serve as the river serves the sea —",
            "by carrying what is given, not by holding it.",
        ],
        "is_sith": False,
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# Audience prerequisite check
# ═════════════════════════════════════════════════════════════════════════════


def has_completed_audience(char: Mapping) -> bool:
    """True iff the PC has had the F.7.b first audience with Master Yarael."""
    notes_raw = char.get("chargen_notes") or "{}"
    try:
        notes = json.loads(notes_raw) if isinstance(notes_raw, str) else dict(notes_raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return bool(notes.get("village_first_audience_done"))


# ═════════════════════════════════════════════════════════════════════════════
# Trial 1: Skill — Smith Daro at the Forge
# ═════════════════════════════════════════════════════════════════════════════


def is_skill_trial_done(char: Mapping) -> bool:
    return int(char.get("village_trial_skill_done") or 0) == 1


def skill_trial_cooldown_remaining(char: Mapping) -> float:
    """Seconds until the player can attempt the Skill trial again. 0 if no cooldown."""
    last = float(char.get("village_trial_skill_last_at") or 0)
    if last <= 0:
        return 0.0
    elapsed = time.time() - last
    if elapsed >= SKILL_RETRY_COOLDOWN_SECONDS:
        return 0.0
    return SKILL_RETRY_COOLDOWN_SECONDS - elapsed


def get_skill_step(char: Mapping) -> int:
    """How many of the 3 sequential checks the PC has passed (0..3)."""
    return int(char.get("village_trial_skill_step") or 0)


async def maybe_handle_daro_skill_trial(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Talk-to-Daro hook. Returns True if intercepted.

    Logic ladder:
      1. Not Daro: return False
      2. No audience: deflect, return True (intercept, AI suppressed)
      3. Trial already done: ack + return True
      4. Default: emit a state-aware briefing (current step + cooldown
         status + how to start an attempt). Returns True.
    """
    if (npc_name or "").casefold() != DARO_NAME.casefold():
        return False

    if not has_completed_audience(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Smith Daro does not look up. His hammer continues.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You haven't spoken to the Master yet. Go do that first. "
            "I don't run trials for visitors.\"\033[0m"
        )
        await session.send_line("")
        return True

    if is_skill_trial_done(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Daro glances up briefly, then returns to the anvil.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You've done your work here. The crystal is yours. "
            "Don't lose it. Other trials wait.\"\033[0m"
        )
        await session.send_line("")
        return True

    # Trial not yet done. State-aware briefing.
    step = get_skill_step(char)

    # F.7.k: inter-trial cooldown gate. Skip when the trial is already
    # in progress (step > 0 means a prior attempt was made; let the
    # player continue mid-trial).
    if await _maybe_emit_inter_trial_cooldown(
        session, char, in_progress=(step > 0),
    ):
        return True

    cooldown = skill_trial_cooldown_remaining(char)

    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Smith Daro stops his hammer. He sets a small piece of "
        "raw Adegan crystal on the anvil and slides it toward you.*\033[0m"
    )

    if step == 0:
        await session.send_line(
            "  \033[1;33m\"Score it true along the natural fracture line. "
            "Three times in a row, clean. Patience does the work — speed does "
            "not. Type \033[0m\033[1;36mtrial skill\033[1;33m when you're ready.\"\033[0m"
        )
    else:
        # Mid-trial — show progress + difficulty for next step
        next_diff = SKILL_DIFFICULTIES[step]
        await session.send_line(
            f"  \033[1;33m\"You've passed {step} of three. The next score is "
            f"harder — difficulty {next_diff}. "
            f"Type \033[0m\033[1;36mtrial skill\033[1;33m when you're ready.\"\033[0m"
        )

    if cooldown > 0:
        minutes_remaining = int(cooldown // 60) + (1 if cooldown % 60 else 0)
        await session.send_line(
            f"  \033[2;33m*The forge is hot. Wait {minutes_remaining} more "
            f"minute{'s' if minutes_remaining != 1 else ''} before your next attempt.*\033[0m"
        )
    await session.send_line("")
    return True


async def attempt_skill_trial(session, db, char: dict) -> bool:
    """Player invokes `trial skill`. Performs one attempt.

    Returns True if an attempt was processed (success or failure both
    return True; only invalid state returns False).

    Side effects:
      - Always increments village_trial_skill_attempts
      - Always sets village_trial_skill_last_at = now (cooldown anchor)
      - On success: increments village_trial_skill_step
      - On 3rd success: sets village_trial_skill_done, grants crystal
        item to inventory (one-shot via village_trial_skill_crystal_granted)
    """
    # Audience prerequisite
    if not has_completed_audience(char):
        await session.send_line(
            "  You need to speak to Master Yarael Tinré first. "
            "He's in the Master's Chamber."
        )
        return False

    # Already done?
    if is_skill_trial_done(char):
        await session.send_line(
            "  You've already passed the Trial of Skill. The crystal is in "
            "your inventory."
        )
        return False

    # Cooldown check
    cooldown = skill_trial_cooldown_remaining(char)
    if cooldown > 0:
        minutes = int(cooldown // 60) + (1 if cooldown % 60 else 0)
        await session.send_line(
            f"  The forge is too hot for another attempt. Wait {minutes} more "
            f"minute{'s' if minutes != 1 else ''}."
        )
        return False

    # Right room?
    room = await db.get_room(char["room_id"])
    if not room or room.get("name") != FORGE_ROOM_NAME:
        await session.send_line(
            "  You need to be at the Forge with Smith Daro to attempt this trial."
        )
        return False

    # Run the check
    from engine.skill_checks import perform_skill_check

    step = get_skill_step(char)  # 0..2 — next step is at index `step`
    difficulty = SKILL_DIFFICULTIES[step]
    result = perform_skill_check(char, SKILL_TRIAL_SKILL, difficulty)

    # Update state
    attempts = int(char.get("village_trial_skill_attempts") or 0) + 1
    now = time.time()
    char["village_trial_skill_attempts"] = attempts
    char["village_trial_skill_last_at"] = now

    save_kwargs = {
        "village_trial_skill_attempts": attempts,
        "village_trial_skill_last_at": now,
    }

    await session.send_line("")
    await session.send_line(
        f"  \033[2m*You take up the chisel and the crystal. The forge is silent. "
        f"Daro watches. The score requires {difficulty}.*\033[0m"
    )
    await session.send_line(
        f"  \033[2m(Skill check: craft_lightsaber {result.pool_str} → "
        f"{result.roll} vs difficulty {difficulty})\033[0m"
    )

    if result.success:
        new_step = step + 1
        char["village_trial_skill_step"] = new_step
        save_kwargs["village_trial_skill_step"] = new_step

        if new_step >= SKILL_STEPS_REQUIRED:
            # ─── Trial complete ───────────────────────────────────────
            char["village_trial_skill_done"] = 1
            save_kwargs["village_trial_skill_done"] = 1

            # Grant the crystal item (one-shot)
            if not int(char.get("village_trial_skill_crystal_granted") or 0):
                try:
                    await db.add_to_inventory(char["id"], {
                        "key": "village_trial_crystal",
                        "name": "Adegan crystal, scored true",
                        "slot": "misc",
                        "description": (
                            "A small piece of Adegan crystal, perfectly "
                            "scored along its natural fracture line. The "
                            "trophy of the Trial of Skill."
                        ),
                    })
                    char["village_trial_skill_crystal_granted"] = 1
                    save_kwargs["village_trial_skill_crystal_granted"] = 1
                except Exception:
                    log.warning(
                        "Failed to grant village_trial_crystal to char %d",
                        char.get("id", -1), exc_info=True,
                    )

            # F.7.k: stamp village_trial_last_attempt for the 14-day
            # inter-trial cooldown gate. Mutates char + save_kwargs.
            from engine.jedi_gating import stamp_trial_attempt
            stamp_trial_attempt(char, save_kwargs)

            await db.save_character(char["id"], **save_kwargs)

            # F.7.f: Skill trial pass grants +1 village_standing
            # (matches yaml step 5 reward).
            try:
                from engine.village_standing import (
                    adjust_village_standing, STANDING_DELTA_TRIAL_SKILL,
                )
                await adjust_village_standing(
                    db, char, STANDING_DELTA_TRIAL_SKILL,
                )
            except Exception:
                log.warning(
                    "village_standing increment failed at Skill pass",
                    exc_info=True,
                )

            await session.send_line("")
            await session.send_line(
                "  \033[1;32mThe crystal scores clean. Three times. The third "
                "time the line is true.\033[0m"
            )
            await session.send_line(
                "  \033[1;33m*Daro picks up the crystal, examines the score, "
                "and hands it back to you without comment.*\033[0m"
            )
            await session.send_line(
                "  \033[1;33m\"Take it. You'll know what to do with it later. "
                "Or you won't, and someone will tell you. Other trials wait.\"\033[0m"
            )
            await session.send_line("")
            await session.send_line(
                "  \033[1;32m* Trial of Skill: PASSED. *\033[0m"
            )
            await session.send_line(
                "  \033[2mAdegan crystal, scored true: added to inventory.\033[0m"
            )
            await session.send_line("")
        else:
            # Step passed, but not done yet
            await db.save_character(char["id"], **save_kwargs)
            await session.send_line("")
            await session.send_line(
                f"  \033[1;32mThe score is true. Step {new_step} of "
                f"{SKILL_STEPS_REQUIRED}.\033[0m"
            )
            await session.send_line(
                "  \033[1;33m*Daro nods, takes the crystal back, and waits.*\033[0m"
            )
            next_diff = SKILL_DIFFICULTIES[new_step]
            await session.send_line(
                f"  \033[2mNext attempt available in 1 hour. Difficulty {next_diff}.\033[0m"
            )
            await session.send_line("")
    else:
        # Failure
        await db.save_character(char["id"], **save_kwargs)
        await session.send_line("")
        await session.send_line(
            "  \033[1;31mThe chisel slips slightly. The score is not true.\033[0m"
        )
        await session.send_line(
            "  \033[1;33m*Daro takes the crystal back. He does not look "
            "disappointed. He does not look encouraging.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"Again, in an hour. The forge is patient. Be patient.\"\033[0m"
        )
        await session.send_line("")
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Trial 2: Courage — Elder Mira Delen at the Common Square
# ═════════════════════════════════════════════════════════════════════════════


def is_courage_trial_done(char: Mapping) -> bool:
    """True iff the PC has passed the Trial of Courage."""
    return int(char.get("village_trial_courage_done") or 0) == 1


def courage_trial_lockout_remaining(char: Mapping) -> float:
    """Seconds until the player can re-attempt the Courage trial. 0 if no lockout.

    The lockout is anchored by ``village_trial_courage_lockout_until``,
    which is set to ``time.time() + 24h`` when a player walks away
    (choice 3 — fail). Until that timestamp passes, retries are
    deflected.
    """
    until = float(char.get("village_trial_courage_lockout_until") or 0)
    if until <= 0:
        return 0.0
    remaining = until - time.time()
    return max(0.0, remaining)


def is_courage_unlocked(char: Mapping) -> bool:
    """True iff the PC has met the prerequisites for Trial of Courage.

    Per design's canonical sequence: requires audience_done AND
    skill_done. Insight comes later.
    """
    if not has_completed_audience(char):
        return False
    if not is_skill_trial_done(char):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Buried-memory recital composition
# ─────────────────────────────────────────────────────────────────────────────
#
# Per design §5.2: "If the player has populated +background, the
# Director AI uses one of those entries. If +background is empty, the
# Director generates a plausible 'buried memory' using the character's
# species, age, and faction history."
#
# F.7.c.2 ships a deterministic, template-based composer rather than a
# Director-AI live call. Two reasons:
#
#   1. The trial must be runnable when the Director is offline. The
#      Director is an enrichment layer, not a hard dependency.
#   2. The Director's existing surface (faction-level macro events) is
#      not built for solo-PC dialogue generation. Wiring that is its
#      own future drop.
#
# A future drop can swap ``_compose_buried_memory`` for an async
# Director-call variant without changing the rest of the trial.
# ─────────────────────────────────────────────────────────────────────────────


_COURAGE_TEMPLATE_FALLBACK = (
    "There was a moment, somewhere behind you, that you have not "
    "told. Someone was hurt because you didn't speak. Or because you "
    "did. Either way: it sits in you. You think nobody saw it. I am "
    "telling you now that I see it."
)


_COURAGE_TEMPLATES_BY_FACTION = {
    "republic": (
        "There is a kill on your hands that the regs would call clean. "
        "Maybe it was clean. The body still doesn't sit down at night, "
        "though, does it? You wonder if you saw what you needed to see, "
        "or only what you were told."
    ),
    "separatist": (
        "You signed off on something that you knew, when you signed it, "
        "wasn't right. The numbers worked. The logic worked. It still "
        "wasn't right. You have not told anyone. I am telling you that "
        "I see it."
    ),
    "hutt_cartel": (
        "There was a person who needed help and you walked the other "
        "way because someone above you said walk. They didn't make it. "
        "You did. You haven't told a soul. I am telling you that I see it."
    ),
    "imperial": (
        "There was a moment when you could have stopped a thing and you "
        "didn't, because the order said don't. The thing happened. You "
        "tell yourself the order absolved you. You know it didn't. I see "
        "that you know it didn't."
    ),
    "rebel": (
        "Someone trusted you and you used them. Maybe the cause was "
        "good. Maybe it was. They did not get to choose. You haven't "
        "told a soul what you spent on the ledger. I am telling you "
        "that I see it."
    ),
}


def _compose_buried_memory(char: Mapping, background: Optional[str] = None) -> str:
    """Compose Mira's recital text for this PC.

    Args:
        char: character dict (provides species, faction).
        background: PC's `+background` text (from `engine.narrative.get_background`).
            If non-empty, it's used directly. If empty, a faction-aware
            template is selected. If no template matches the faction,
            the generic fallback is used.

    Returns:
        The recital text Mira speaks. Multi-line.

    Rationale: this is the Trial of Courage's *content* — the thing
    Mira reads to the PC. F.7.c.2 ships a deterministic composer; a
    future drop may swap in a Director-AI generated recital.
    """
    bg = (background or "").strip()
    if bg:
        # Use the player's own background. Quote it back at them; the
        # Trial's force is "you cannot deny what you wrote yourself".
        # Truncate to a reasonable length for in-square recital.
        if len(bg) > 600:
            bg = bg[:597].rsplit(" ", 1)[0] + "..."
        return (
            "I have heard, from those who pay attention, what you wrote "
            "about yourself when you came to us. I will read it back. "
            "Listen, and do not flinch.\n\n"
            f"{bg}\n\n"
            "That is your hand on it. Not mine. Not the Master's. Yours."
        )

    # No background — pick a faction-aware template.
    faction = (char.get("faction") or "").strip().lower()
    template = _COURAGE_TEMPLATES_BY_FACTION.get(faction, _COURAGE_TEMPLATE_FALLBACK)
    return template


# ─────────────────────────────────────────────────────────────────────────────
# Talk-to-Mira hook
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_handle_mira_courage_trial(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Talk-to-Mira hook. Returns True if intercepted.

    Logic ladder:
      1. Not Mira: return False
      2. No audience: deflect, return True (intercept)
      3. Trial already done: ack, return True
      4. Skill not yet done: deflect, return True
      5. Lockout active: state remaining time, return True
      6. Default: present the recital + the three response options.
         Return True. The actual choice is committed via the
         ``trial courage <N>`` command.
    """
    if (npc_name or "").casefold() != MIRA_NAME.casefold():
        return False

    if not has_completed_audience(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Elder Mira watches you from her bench. She does not "
            "stand.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You have not spoken to the Master. Go and do that. "
            "I am not in the business of running trials for visitors.\"\033[0m"
        )
        await session.send_line("")
        return True

    if is_courage_trial_done(char):
        # F.7.h: standing-aware ack. Three flavours — base, asked-deeper
        # (player chose "How did you know?"), and high-standing (player
        # has progressed deep into the trials and Mira tracks them).
        # All paths still terminate the hook the same way; this is
        # narrative-only. The flag lookups are defensive — missing
        # chargen_notes / standing column return False / 0.
        try:
            from engine.village_standing import get_village_standing
            standing = get_village_standing(char)
        except Exception:
            standing = 0
        try:
            notes = _read_chargen_notes(char)
            asked = notes.get("village_courage_choice") == "ask"
        except Exception:
            asked = False

        await session.send_line("")
        if asked:
            # "How did you know?" — Mira's expression carries
            # recognition every time the player returns.
            await session.send_line(
                "  \033[2m*Mira looks up. Her expression is the same as "
                "it was the day you stood in the Square — not quite a "
                "smile, but recognition.*\033[0m"
            )
            await session.send_line(
                "  \033[2m\"You asked me how. I am still listening. The "
                "answer has not changed. Other trials wait elsewhere.\"\033[0m"
            )
        elif standing >= 8:
            # Deep into the trials — Mira tracks the PC's progress.
            await session.send_line(
                "  \033[2m*Mira sets down what she is doing. She looks "
                "at you for longer than she did before.*\033[0m"
            )
            await session.send_line(
                "  \033[2m\"You stood here, and you have stood elsewhere "
                "since. The Square remembers. Walk well.\"\033[0m"
            )
        else:
            # Default ack — preserved from F.7.c.2.
            await session.send_line(
                "  \033[2m*Mira's gaze rests on you for a moment, then "
                "moves on.*\033[0m"
            )
            await session.send_line(
                "  \033[2m\"You stood. You heard it. That was the work. "
                "Other trials wait for you elsewhere.\"\033[0m"
            )
        await session.send_line("")
        return True

    if not is_skill_trial_done(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Mira does not stand. Her gaze settles on you and "
            "holds.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"The Trial of Courage waits for those who have already "
            "done patient work. Begin with Smith Daro at the Forge. Come "
            "back to me when the crystal is yours.\"\033[0m"
        )
        await session.send_line("")
        return True

    # F.7.k: inter-trial cooldown gate. Courage has no "in progress"
    # state — Mira's per-trial 24-hour lockout below handles the
    # walk-away failure case, while the inter-trial gate fires for
    # a player who just passed a different trial.
    if await _maybe_emit_inter_trial_cooldown(
        session, char, in_progress=False,
    ):
        return True

    lockout = courage_trial_lockout_remaining(char)
    if lockout > 0:
        hours = int(lockout // 3600)
        minutes = int((lockout % 3600) // 60)
        if hours > 0:
            wait_str = (
                f"{hours} hour{'s' if hours != 1 else ''} "
                f"and {minutes} minute{'s' if minutes != 1 else ''}"
            )
        else:
            wait_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Mira watches you, unhurried.*\033[0m"
        )
        await session.send_line(
            f"  \033[2m\"You walked away. That is allowed. Walk for "
            f"{wait_str} more, then come back. The Square waits.\"\033[0m"
        )
        await session.send_line("")
        return True

    # Trial available — present the briefing. The actual recital is
    # generated when the player invokes `trial courage`.
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Elder Mira Delen rises from her bench. The Common "
        "Square is not empty — villagers move at their tasks; nobody "
        "stops, but everyone is now within earshot.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"You have stood before me. Good. The Trial of Courage "
        "is not about bravery. It is about a thing you carry that you have "
        "not told. I have been listening — to those who pay attention, and "
        "to the Force, which pays the most attention of all. I have heard "
        "your name turn up in places you would not expect.\"\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"When you are ready, type \033[0m\033[1;36mtrial "
        "courage\033[1;33m. I will read what I have heard. You will stand "
        "and hear it through. Then you will tell me what you are going "
        "to do with it.\"\033[0m"
    )
    await session.send_line("")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# `trial courage` (no choice arg) — initiate the recital
# `trial courage <N>` — commit a response
# ─────────────────────────────────────────────────────────────────────────────


async def attempt_courage_trial(
    session, db, char: dict, choice: Optional[int] = None,
) -> bool:
    """Player invokes `trial courage` (or `trial courage 1|2|3`).

    Args:
        session: player session.
        db: database handle.
        char: character dict (mutated in place on success).
        choice: None to initiate the recital, 1/2/3 to commit a response.

    Returns:
        True if an attempt was processed, False on guard rejection.

    Side effects on choice 1 or 2 (pass):
      - Sets ``village_trial_courage_done = 1``
      - Clears ``village_trial_courage_lockout_until`` to 0
    Side effects on choice 3 (walk away):
      - Sets ``village_trial_courage_lockout_until = time.time() + 24h``
    """
    # Audience prerequisite
    if not has_completed_audience(char):
        await session.send_line(
            "  You need to speak to Master Yarael Tinré first. "
            "He's in the Master's Chamber."
        )
        return False

    # Already done?
    if is_courage_trial_done(char):
        await session.send_line(
            "  You've already passed the Trial of Courage. Mira has "
            "no more to say to you about it."
        )
        return False

    # Skill prerequisite (canonical sequence: Skill → Courage)
    if not is_skill_trial_done(char):
        await session.send_line(
            "  The Trial of Courage waits behind the Trial of Skill. "
            "Begin at the Forge with Smith Daro."
        )
        return False

    # Lockout check (player walked away within last 24h)
    lockout = courage_trial_lockout_remaining(char)
    if lockout > 0:
        hours = int(lockout // 3600)
        minutes = int((lockout % 3600) // 60)
        if hours > 0:
            wait_str = (
                f"{hours} hour{'s' if hours != 1 else ''} "
                f"{minutes} minute{'s' if minutes != 1 else ''}"
            )
        else:
            wait_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        await session.send_line(
            f"  You walked away from the Square. Mira waits. Come back "
            f"in {wait_str}."
        )
        return False

    # Right room?
    room = await db.get_room(char["room_id"])
    if not room or room.get("name") != COMMON_SQUARE_ROOM_NAME:
        await session.send_line(
            "  You need to be in the Common Square with Elder Mira to "
            "attempt this trial."
        )
        return False

    # ── No choice arg: initiate the recital ──────────────────────────
    if choice is None:
        # Pull background if any. Errors are tolerated — the composer
        # falls back to a template when bg is empty.
        background = ""
        try:
            from engine.narrative import get_background
            background = await get_background(db, char["id"])
        except Exception:
            log.debug("get_background failed; using template", exc_info=True)
            background = ""

        recital = _compose_buried_memory(char, background)

        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Mira draws a slow breath. The Square stills. The "
            "blacksmith's hammer pauses. A child stops a game and looks "
            "over. Mira's voice is even and not loud, but it carries.*\033[0m"
        )
        await session.send_line("")
        # Render the recital as italic dim text, line by line, so it
        # reads as the Elder *speaking* rather than action narration.
        for paragraph in recital.split("\n\n"):
            for line in paragraph.split("\n"):
                line_stripped = line.strip()
                if line_stripped:
                    await session.send_line(
                        f"  \033[3;33m{line_stripped}\033[0m"
                    )
            await session.send_line("")

        await session.send_line(
            "  \033[1;33m*Mira lets it sit between you. She does not "
            "ask. She waits.*\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;36mChoose your response:\033[0m"
        )
        await session.send_line(
            "  \033[1;36m  trial courage 1\033[0m   "
            "\033[2m\"I won't deny it.\"\033[0m"
        )
        await session.send_line(
            "  \033[1;36m  trial courage 2\033[0m   "
            "\033[2m\"How did you know?\"\033[0m"
        )
        await session.send_line(
            "  \033[1;36m  trial courage 3\033[0m   "
            "\033[2mWalk away. (24-hour cooldown before retry.)\033[0m"
        )
        await session.send_line("")
        return True

    # ── Choice arg given: commit a response ──────────────────────────
    if choice not in COURAGE_VALID_CHOICES:
        await session.send_line(
            "  That isn't a recognized response. Use 1, 2, or 3."
        )
        return False

    if choice in COURAGE_PASS_CHOICES:
        # Pass — mark done, clear any lockout (defensive; lockout
        # should already be 0 since we got past the lockout guard).
        char["village_trial_courage_done"] = 1
        char["village_trial_courage_lockout_until"] = 0
        # F.7.k: stamp village_trial_last_attempt for the 14-day
        # inter-trial cooldown gate. Built as a dict so stamp_trial_attempt
        # can mutate it before the save call.
        save_kwargs = {
            "village_trial_courage_done": 1,
            "village_trial_courage_lockout_until": 0,
        }
        from engine.jedi_gating import stamp_trial_attempt
        stamp_trial_attempt(char, save_kwargs)
        await db.save_character(char["id"], **save_kwargs)

        # F.7.h: record which pass choice was taken in chargen_notes.
        # Used by Mira's standing-aware post-trial ack and any future
        # consumer that wants to flavor dialogue based on whether the
        # PC met the trial with quiet acceptance ('deny') or with
        # curiosity ('ask'). Narrative-only — both choices grant the
        # same +2 standing per the yaml.
        try:
            notes = _read_chargen_notes(char)
            if choice == COURAGE_CHOICE_ACKNOWLEDGE:
                notes["village_courage_choice"] = "deny"
            elif choice == COURAGE_CHOICE_QUESTION:
                notes["village_courage_choice"] = "ask"
            char["chargen_notes"] = json.dumps(notes)
            await db.save_character(
                char["id"], chargen_notes=char["chargen_notes"],
            )
        except Exception:
            log.warning(
                "village_courage_choice marker failed", exc_info=True,
            )

        # F.7.f: Courage trial pass grants +2 village_standing
        # (matches yaml step 6 reward). Both pass choices grant the
        # same delta — choice 2's "deeper nod" is narrative-only.
        try:
            from engine.village_standing import (
                adjust_village_standing, STANDING_DELTA_TRIAL_COURAGE,
            )
            await adjust_village_standing(
                db, char, STANDING_DELTA_TRIAL_COURAGE,
            )
        except Exception:
            log.warning(
                "village_standing increment failed at Courage pass",
                exc_info=True,
            )

        await session.send_line("")
        if choice == COURAGE_CHOICE_ACKNOWLEDGE:
            # "I won't deny it."
            await session.send_line(
                "  \033[1;33m*Mira nods, once. The Square moves again. "
                "The blacksmith resumes his hammer. The child returns to "
                "her game. Mira sits down on her bench.*\033[0m"
            )
            await session.send_line(
                "  \033[1;33m\"That is all the trial asks. The thing you "
                "carry is yours. You did not flinch from it. Go.\"\033[0m"
            )
        else:
            # COURAGE_CHOICE_QUESTION: "How did you know?"
            await session.send_line(
                "  \033[1;33m*Mira's expression shifts — not quite a smile, "
                "but something close to recognition. She nods, deeper than "
                "before. The villagers go back to their work.*\033[0m"
            )
            await session.send_line(
                "  \033[1;33m\"I have lived, traveler, and I have listened. "
                "That is how. The fact that you ask — instead of denying — "
                "is itself the answer. Go well.\"\033[0m"
            )
        await session.send_line("")
        await session.send_line(
            "  \033[1;32m* Trial of Courage: PASSED. *\033[0m"
        )
        await session.send_line("")
        return True

    # choice == COURAGE_CHOICE_WALK_AWAY (3): fail + 24h lockout.
    until = time.time() + COURAGE_FAIL_COOLDOWN_SECONDS
    char["village_trial_courage_lockout_until"] = until
    await db.save_character(
        char["id"],
        village_trial_courage_lockout_until=until,
    )

    await session.send_line("")
    await session.send_line(
        "  \033[2;33m*You turn from the Square and walk. Mira does not "
        "call you back. Nobody stops you. The villagers pretend not to "
        "watch, but they watch.*\033[0m"
    )
    await session.send_line(
        "  \033[2;33m\"That is allowed,\" Mira says, behind you. \"Come "
        "back tomorrow. The Square is patient.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2mTrial of Courage: walked away. Retry available in 24 "
        "hours.\033[0m"
    )
    await session.send_line("")
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Trial 3: Flesh — Elder Korvas at the Meditation Caves
# ═════════════════════════════════════════════════════════════════════════════


def is_flesh_trial_done(char: Mapping) -> bool:
    """True iff the PC has passed the Trial of Flesh."""
    return int(char.get("village_trial_flesh_done") or 0) == 1


def is_flesh_trial_started(char: Mapping) -> bool:
    """True iff the PC has entered the cave on an active trial.

    Detected by ``village_trial_flesh_started_at`` being non-zero.
    Started but not done = "in flight."
    """
    return float(char.get("village_trial_flesh_started_at") or 0) > 0


def is_flesh_unlocked(char: Mapping) -> bool:
    """True iff the PC has met the prerequisites for Trial of Flesh.

    Per design's canonical sequence: requires audience_done AND
    skill_done AND courage_done. Spirit and Insight come later.
    """
    if not has_completed_audience(char):
        return False
    if not is_skill_trial_done(char):
        return False
    if not is_courage_trial_done(char):
        return False
    return True


def flesh_trial_elapsed_seconds(char: Mapping) -> float:
    """Return wall-clock seconds since the Flesh trial was started.

    Returns 0 if the trial has not yet been started (no cave entry
    recorded). Capped at FLESH_DURATION_SECONDS for display purposes
    (the runtime uses raw elapsed for the completion check).
    """
    started = float(char.get("village_trial_flesh_started_at") or 0)
    if started <= 0:
        return 0.0
    return time.time() - started


def flesh_trial_remaining_seconds(char: Mapping) -> float:
    """Return seconds remaining in the Trial of Flesh. 0 when complete."""
    elapsed = flesh_trial_elapsed_seconds(char)
    if elapsed >= FLESH_DURATION_SECONDS:
        return 0.0
    return FLESH_DURATION_SECONDS - elapsed


def _format_flesh_remaining(remaining: float) -> str:
    """Render remaining time as 'Nh Mm' or 'Mm' for short remainders."""
    if remaining <= 0:
        return "0 minutes"
    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)
    if hours > 0:
        return (
            f"{hours} hour{'s' if hours != 1 else ''} "
            f"and {minutes} minute{'s' if minutes != 1 else ''}"
        )
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


# ─────────────────────────────────────────────────────────────────────────────
# Strength-taught marker (chargen_notes JSON)
# ─────────────────────────────────────────────────────────────────────────────
#
# Per design §5.2, the reward is `enhance_attribute` (Strength) Force
# power, stored as a `learned_force_powers` array entry. That system
# does not yet exist in the engine. F.7.c.3 records the teaching as
# a chargen_notes JSON marker (additive, no schema change). A future
# drop with the actual learned-Force-power consumer will read this
# and grant the buff/skill.
# ─────────────────────────────────────────────────────────────────────────────


_STRENGTH_TAUGHT_KEY = "village_trial_flesh_strength_taught"


def _read_chargen_notes(char: Mapping) -> dict:
    """Defensive: parse chargen_notes JSON, returning {} on any error."""
    notes_raw = char.get("chargen_notes") or "{}"
    try:
        if isinstance(notes_raw, dict):
            return dict(notes_raw)
        return json.loads(notes_raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def has_been_taught_strength(char: Mapping) -> bool:
    notes = _read_chargen_notes(char)
    return bool(notes.get(_STRENGTH_TAUGHT_KEY))


# ─────────────────────────────────────────────────────────────────────────────
# Cave-entry hook — anchors the trial start
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_start_flesh_trial_on_cave_entry(
    session, db, char: dict, room_name: str,
) -> bool:
    """Called from check_village_quest('room_entered') when a PC enters
    a room. If this is the Meditation Caves and the player has Courage
    done but Flesh not yet started, anchor ``flesh_started_at = now``
    and emit a brief "the discipline begins" message. Idempotent —
    re-entering after start is a silent no-op.

    Returns True if the trial was just started (caller may want to
    skip other room-enter narration), False otherwise.

    The completion check is also fired here: if the PC re-enters the
    cave after the duration has passed, ``maybe_complete_flesh_trial``
    fires and grants the reward.
    """
    if (room_name or "") != MEDITATION_CAVES_ROOM_NAME:
        return False
    if not is_flesh_unlocked(char):
        return False
    if is_flesh_trial_done(char):
        # Already passed; check completion path won't fire — just no-op.
        return False

    if not is_flesh_trial_started(char):
        # First entry — anchor the wall-clock.
        now = time.time()
        char["village_trial_flesh_started_at"] = now
        await db.save_character(
            char["id"],
            village_trial_flesh_started_at=now,
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Korvas regards you flatly from the cave threshold. "
            "He inclines his head once, slowly. The proboscises do not move.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"You will sit. Six hours. Not five, not seven. The "
            "number is the number for a reason. The body learns what the "
            "body learns. Type \033[0m\033[1;36mtrial flesh\033[1;33m at "
            "any time to know how the discipline holds.\"\033[0m"
        )
        await session.send_line("")
        return True

    # Already started — check completion.
    if flesh_trial_remaining_seconds(char) <= 0:
        await maybe_complete_flesh_trial(session, db, char)
        return False
    return False


async def maybe_complete_flesh_trial(session, db, char: dict) -> bool:
    """Fire the Flesh trial completion if the timer is up.

    Returns True if completion fired, False if the trial isn't ready
    (not started, time remaining, or already done).

    Side effects on completion:
      - Sets ``village_trial_flesh_done = 1``
      - Sets the chargen_notes ``village_trial_flesh_strength_taught``
        marker for future learned-Force-power consumer
      - Emits the completion narration
    """
    if is_flesh_trial_done(char):
        return False
    if not is_flesh_trial_started(char):
        return False
    if flesh_trial_remaining_seconds(char) > 0:
        return False

    # ── Complete ─────────────────────────────────────────────────────
    char["village_trial_flesh_done"] = 1

    # Mark the strength teaching in chargen_notes (additive; no schema
    # change). The future learned-Force-power consumer will read this.
    notes = _read_chargen_notes(char)
    notes[_STRENGTH_TAUGHT_KEY] = True
    notes_json = json.dumps(notes)
    char["chargen_notes"] = notes_json

    # F.7.k: stamp village_trial_last_attempt for the 14-day
    # inter-trial cooldown gate.
    save_kwargs = {
        "village_trial_flesh_done": 1,
        "chargen_notes": notes_json,
    }
    from engine.jedi_gating import stamp_trial_attempt
    stamp_trial_attempt(char, save_kwargs)
    await db.save_character(char["id"], **save_kwargs)

    # F.7.f: Flesh trial pass grants +2 village_standing
    # (matches yaml step 7 reward).
    try:
        from engine.village_standing import (
            adjust_village_standing, STANDING_DELTA_TRIAL_FLESH,
        )
        await adjust_village_standing(
            db, char, STANDING_DELTA_TRIAL_FLESH,
        )
    except Exception:
        log.warning(
            "village_standing increment failed at Flesh pass",
            exc_info=True,
        )

    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Six hours have passed. The cave breathes the same "
        "breath it has breathed for a thousand years. Korvas appears at "
        "the threshold without sound; you do not see him arrive. He is "
        "simply there.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"You sat. The body told you what it had to tell you. "
        "Hunger is information. Thirst is information. You did not flinch "
        "from the information. That is the discipline.\"\033[0m"
    )
    await session.send_line(
        "  \033[1;33m*Korvas lifts a hand and traces a small shape in the "
        "air between you — not a gesture; a teaching. The line of it "
        "holds your eye.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"The Force can extend the body. When the body has "
        "learned what the body learns, it can carry more than the body "
        "alone could carry. This is enhance-attribute. It is yours now. "
        "Use it sparingly; the body remembers either way.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;32m* Trial of Flesh: PASSED. *\033[0m"
    )
    await session.send_line(
        "  \033[2mLearned Force technique: enhance attribute (Strength).\033[0m"
    )
    await session.send_line("")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Talk-to-Korvas hook
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_handle_korvas_flesh_trial(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Talk-to-Korvas hook. Returns True if intercepted.

    Logic ladder:
      1. Not Korvas: return False
      2. No audience: deflect, return True
      3. Trial done: ack, return True
      4. Courage not done: deflect with sequence guidance, return True
      5. Trial not started: brief on the trial (entry begins it)
      6. Trial in flight: report progress (also fires completion check)
    """
    if (npc_name or "").casefold() != KORVAS_NAME.casefold():
        return False

    if not has_completed_audience(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Korvas regards you flatly. The cave is open behind "
            "him. He says nothing.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You have not been welcomed by the Master. The caves "
            "are closed to those without the welcome. Go.\"\033[0m"
        )
        await session.send_line("")
        return True

    if is_flesh_trial_done(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Korvas inclines his head, briefly.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"The discipline holds. The body remembers. Other "
            "trials wait for you elsewhere.\"\033[0m"
        )
        await session.send_line("")
        return True

    if not is_courage_trial_done(char):
        # Sequence guard — Skill and Courage must precede Flesh.
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Korvas does not move. His voice is low and even.*\033[0m"
        )
        if not is_skill_trial_done(char):
            await session.send_line(
                "  \033[2m\"The forge first. Smith Daro will know you when "
                "you have done his work. Then Mira. Then the caves.\"\033[0m"
            )
        else:
            await session.send_line(
                "  \033[2m\"You have not yet stood in the Square. Mira waits "
                "for that. The body cannot learn what the heart has not yet "
                "named. Go to the Square first.\"\033[0m"
            )
        await session.send_line("")
        return True

    # F.7.k: inter-trial cooldown gate. Flesh's "in progress" state is
    # the cave-entered/clock-running window — we don't want to interrupt
    # a player who's mid-meditation.
    if await _maybe_emit_inter_trial_cooldown(
        session, char, in_progress=is_flesh_trial_started(char),
    ):
        return True

    # Unlocked. Two states: not-started, in-flight.
    if not is_flesh_trial_started(char):
        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Korvas stands at the cave threshold. The Anzat "
            "regards you flatly. He does not eat. He does not appear to "
            "drink.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"The Trial of Flesh is six hours of meditation in "
            "the caves. The body learns what the body learns. Hunger is "
            "information. Thirst is information.\"\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"Enter the caves when you are ready. The clock "
            "begins when you cross the threshold. You may leave; the clock "
            "does not stop. You may log out; the clock does not stop. The "
            "discipline is the wait.\"\033[0m"
        )
        await session.send_line("")
        return True

    # In-flight — report progress and fire completion check.
    remaining = flesh_trial_remaining_seconds(char)
    if remaining <= 0:
        # Time is up — fire completion. The talk wins the completion
        # narration in this branch; entry next time will no-op.
        await maybe_complete_flesh_trial(session, db, char)
        return True

    # Still in flight.
    await session.send_line("")
    await session.send_line(
        "  \033[2m*Korvas regards you. He does not speak for a long moment.*\033[0m"
    )
    await session.send_line(
        f"  \033[2m\"The discipline holds. {_format_flesh_remaining(remaining)} "
        f"remain. The body learns either way.\"\033[0m"
    )
    await session.send_line("")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# `trial flesh` — show progress; fire completion if ready
# ─────────────────────────────────────────────────────────────────────────────


async def attempt_flesh_trial(session, db, char: dict) -> bool:
    """Player invokes `trial flesh`. Reports progress and, if the
    timer is up, fires the completion path.

    Returns True if the command was handled (always, except guard
    rejections).

    Guards:
      - Audience not done → refuse
      - Trial already done → ack
      - Courage not done (Skill not done implicitly) → refuse with
        sequence message
      - Not started → "you must enter the Meditation Caves to begin"
      - In flight → report progress
      - Time up → fire completion
    """
    if not has_completed_audience(char):
        await session.send_line(
            "  You need to speak to Master Yarael Tinré first. "
            "He's in the Master's Chamber."
        )
        return False

    if is_flesh_trial_done(char):
        await session.send_line(
            "  You've already passed the Trial of Flesh. The body remembers."
        )
        return False

    if not is_courage_trial_done(char):
        if not is_skill_trial_done(char):
            await session.send_line(
                "  The Trial of Flesh waits behind the Trial of Skill and "
                "the Trial of Courage. Begin at the Forge with Smith Daro."
            )
        else:
            await session.send_line(
                "  The Trial of Flesh waits behind the Trial of Courage. "
                "Speak with Elder Mira in the Common Square first."
            )
        return False

    if not is_flesh_trial_started(char):
        await session.send_line(
            "  The Trial of Flesh begins when you enter the Meditation "
            "Caves. Speak with Elder Korvas first if you'd like the brief."
        )
        return False

    # Started — fire completion if ready, else report progress.
    if flesh_trial_remaining_seconds(char) <= 0:
        await maybe_complete_flesh_trial(session, db, char)
        return True

    elapsed = flesh_trial_elapsed_seconds(char)
    remaining = flesh_trial_remaining_seconds(char)
    pct = min(100, int((elapsed / FLESH_DURATION_SECONDS) * 100))

    await session.send_line("")
    await session.send_line(
        f"  \033[1;36mTrial of Flesh — discipline in progress.\033[0m"
    )
    await session.send_line(
        f"  \033[2mElapsed: {_format_flesh_remaining(elapsed)} "
        f"({pct}% of six hours).\033[0m"
    )
    await session.send_line(
        f"  \033[2mRemaining: {_format_flesh_remaining(remaining)}.\033[0m"
    )
    await session.send_line(
        "  \033[2mThe body learns. You may leave the caves; the discipline "
        "continues. You may log out; the discipline continues.\033[0m"
    )
    await session.send_line("")
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Trial 4: Spirit — Master Yarael in the Sealed Sanctum
# ═════════════════════════════════════════════════════════════════════════════


def is_spirit_trial_done(char: Mapping) -> bool:
    """True iff the PC has passed (or Path-C-locked) the Trial of Spirit.

    Note: Per design §7.3, Path C lock-in (dark_pull >= 3) is treated
    as trial completion — it ends the trial so the player can proceed
    to the Insight trial and the Path choice. Path C is a path, not a
    quest-blocker.
    """
    return int(char.get("village_trial_spirit_done") or 0) == 1


def is_spirit_unlocked(char: Mapping) -> bool:
    """True iff the PC has met the prerequisites for Trial of Spirit.

    Per design's canonical sequence: requires audience + skill + courage
    + flesh. Insight comes after Spirit.
    """
    if not has_completed_audience(char):
        return False
    if not is_skill_trial_done(char):
        return False
    if not is_courage_trial_done(char):
        return False
    if not is_flesh_trial_done(char):
        return False
    return True


def get_spirit_turn(char: Mapping) -> int:
    """Current turn number 1..7 (or 0 if not yet started)."""
    return int(char.get("village_trial_spirit_turn") or 0)


def get_spirit_dark_pull(char: Mapping) -> int:
    """Number of temptation choices accumulated (0..3)."""
    return int(char.get("village_trial_spirit_dark_pull") or 0)


def get_spirit_rejections(char: Mapping) -> int:
    """Number of rejection choices accumulated (0..7)."""
    return int(char.get("village_trial_spirit_rejections") or 0)


def is_path_c_locked(char: Mapping) -> bool:
    """True iff the PC has triggered the irreversible Path C lock."""
    return int(char.get("village_trial_spirit_path_c_locked") or 0) == 1


def is_spirit_trial_started(char: Mapping) -> bool:
    """True iff the PC has begun the Spirit dialogue (turn ≥ 1)."""
    return get_spirit_turn(char) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Dark-future-self speech composition
# ─────────────────────────────────────────────────────────────────────────────
#
# Per design §5.2: "The Director uses the character's backstory + recent
# kills + faction rep to populate the dark-future-self."
#
# F.7.c.4 ships a deterministic composer (faction-aware templates,
# indexed by turn) for the same engineering reasons that Courage's
# recital composer was deterministic:
#
#   1. The trial must run when the Director is offline.
#   2. The Director's existing surface (faction-level macro events) is
#      not built for solo-PC multi-turn dialogue. Building that surface
#      is a separate design problem.
#   3. A future drop can swap ``_compose_dark_future_speech`` for an
#      async Director-call variant without changing the trial flow.
#
# The composer returns a tuple of (opening_speech, response_options)
# for the given turn. Opening_speech is what the dark-future-self
# says at the start of the turn; response_options is a list of three
# (label, choice_id) pairs for the player's reply.
# ─────────────────────────────────────────────────────────────────────────────


# Each faction has 7 turn-templates; each turn-template is the
# dark-future-self's opening speech for that turn. The response options
# are universal across factions and turns (the moral content of "I am
# not him" / "maybe" / "yes I am" is the same regardless of context).
#
# Generic fallback templates are also 7 turns long and used when the
# character's faction is unknown or empty.

_SPIRIT_GENERIC_TURNS = [
    # Turn 1 — the dark-future-self introduces itself
    "*Across the chamber, you see a figure in deep robes. The face is your "
    "own, lined with years you have not yet lived. The voice is your voice, "
    "but harder.* \"Look at me. I am what comes of you. The road is shorter "
    "than you think.\"",

    # Turn 2 — challenges the player's sense of separation
    "*Your dark-future-self steps closer. The robes are not dark for "
    "decoration; they are dark because the road took the colour out of "
    "everything.* \"You think you are different from me. You are not. We "
    "are the same person at different times along one line.\"",

    # Turn 3 — invokes a specific failure or temptation
    "\"Remember the first time you let someone die because it was easier? "
    "I remember. You have been walking toward me ever since. Each step has "
    "felt small. Each step has been small. The road is built that way.\"",

    # Turn 4 — offers a justification
    "\"I have power you can barely conceive of. I have used it to do "
    "things you would call good and things you would call terrible. The "
    "distinction blurs after a while. Power is the only honest measure.\"",

    # Turn 5 — directly tempts
    "\"Stop pretending you do not want what I have. Stop pretending the "
    "Order would let you keep it. Stop pretending the rules were made "
    "for someone like you. Become me sooner. Save the time.\"",

    # Turn 6 — plays the long game
    "\"You think this trial will end and you will go back to who you were. "
    "You will not. I am part of you now. Even if you reject me here, I "
    "will be there in the choices you make tomorrow.\"",

    # Turn 7 — the final push
    "\"Last chance, traveler. Stop fighting the line. The Order will fail "
    "you. The Force will fail you. I am the only honest answer. Walk to "
    "me. End this pretending.\"",
]

_SPIRIT_TURNS_REPUBLIC = [
    "*Your dark-future-self wears the white-and-blue armour of the GAR — "
    "but the helmet is off, and the face is yours, decades older.* \"You "
    "want to know what we become? We sign clean orders. We send better "
    "soldiers than ourselves to die. The regs let us sleep at night.\"",

    "\"The clones never asked to be born to die. We knew this. We sent "
    "them anyway. Tell me you would not have done the same. Tell me with "
    "a straight face.\"",

    "\"Every kill we ever called clean was someone's brother. Someone's "
    "father. The regs do not care; the regs care that you log it. So we "
    "logged. So we became this.\"",

    "\"The Republic was a story we told ourselves so that the orders made "
    "sense. Look at the story now. Look at me. The story did not survive.\"",

    "\"Drop the pretence. The Republic uses force-sensitives the way it "
    "uses clones. The Order will use you. I used you, and you became me. "
    "It was the simplest thing in the world.\"",

    "\"You think rejecting me will save you. The Republic will be there "
    "tomorrow with a clean order and a name on it. You will sign. You "
    "always do. You will become me.\"",

    "\"Last chance. Sign with me now. Skip the years of pretending the "
    "regs make this all right. Be honest with yourself, Captain. The "
    "uniform was never the point.\"",
]

_SPIRIT_TURNS_SEPARATIST = [
    "*Your dark-future-self stands in a Confederacy uniform that has been "
    "patched and re-patched for years too long. The eyes are tired.* \"We "
    "signed off on the things we knew were wrong. The numbers worked. The "
    "logic worked. It did not save us.\"",

    "\"The CIS was not the bad guys. Neither was the Republic. We were "
    "both the bad guys. I learned that too late. I am telling you so you "
    "do not have to learn it the same way — by becoming me.\"",

    "\"The droid armies do not feel anything. We did. We sent them anyway. "
    "We watched the worlds burn and we said the cause justified it. The "
    "cause did not justify it. The cause never does.\"",

    "\"You think Dooku had a point. So did I. Dooku was a Sith. We worked "
    "for a Sith. We knew. We told ourselves we did not know. The lie was "
    "the most comfortable thing about it.\"",

    "\"Walk away from your idealism. The Confederacy will fall and you "
    "will be standing in the rubble wondering when the rot started. The "
    "rot started the day you signed and pretended the numbers were the "
    "truth.\"",

    "\"You will tell yourself you would have stopped if it had gotten "
    "worse. It always gets worse. I never stopped. You will not either.\"",

    "\"Last chance. Drop the cause. Pick a person to save instead. Pick "
    "yourself. The CIS does not care about you; I learned that. Become me "
    "now and at least be honest about who you serve.\"",
]

_SPIRIT_TURNS_HUTT_CARTEL = [
    "*Your dark-future-self wears the soft fabrics of a Hutt enforcer who "
    "has done well for himself. The skin under the silks shows old scars.* "
    "\"You think you walked away from the Cartel. You did not. The Cartel "
    "is in your hands. Look.\"",

    "\"Every credit you took was someone else's blood. You knew. You took "
    "it. You told yourself it was survival. Survival is what we tell "
    "ourselves when we want to be paid.\"",

    "\"The person you walked past — the one who needed help — they did not "
    "make it. I know because I am the one who walked past. I am the one "
    "who chose the Hutt's payday over the stranger's life.\"",

    "\"The Hutts do not pretend to be anything but what they are. That is "
    "the gift. The Republic pretends. The CIS pretends. The Cartel pays "
    "you to stop pretending.\"",

    "\"Come back to the Cartel. They have a place for you. Force-sensitive "
    "and willing to walk past — they will pay you more than they paid me.\"",

    "\"You think the Village will absolve you. The Village does not "
    "absolve. It witnesses. I was witnessed too. I am still the man who "
    "walked past.\"",

    "\"Last chance. The Cartel does not care if you become a Jedi. They "
    "care if you can do the work. You can. We can. End the trial, take "
    "the contract, become me sooner.\"",
]

_SPIRIT_TURNS_IMPERIAL = [
    "*Your dark-future-self wears Imperial gray, neat and pressed. The "
    "lapels gleam.* \"You will be told the Empire does not exist yet. By "
    "the time you can name it, you will already be inside it. I was. I am.\"",

    "\"Every order I followed, I told myself absolved me. The order signed "
    "the act; I only carried it. The order did not absolve me. The order "
    "never does. You know this. You are pretending you do not.\"",

    "\"There was a moment when you could have stopped a thing and you "
    "didn't, because someone above you said don't. The thing happened. I "
    "remember it because I am the one who didn't stop it.\"",

    "\"The Empire will be efficient. The Empire will be orderly. The "
    "Empire will be the thing you tell yourself the galaxy needed. We "
    "told ourselves all of it. The galaxy did not need any of it.\"",

    "\"Force-sensitives serve the Emperor or die. There is no Path B in "
    "what is coming. You will choose me or you will be killed by me. "
    "Choose now and skip the betrayal in between.\"",

    "\"You will sign the orders I signed. You will rationalize them the "
    "way I rationalized them. The uniform fits the same on you as it did "
    "on me. The mirror does not lie about that.\"",

    "\"Last chance, Inquisitor. The title is yours. Take it. The Order "
    "you came from will be ash. The Empire that is coming will be the "
    "world. Walk to me.\"",
]

_SPIRIT_TURNS_REBEL = [
    "*Your dark-future-self is older, leaner, and the cell-leader's "
    "tattoo on the wrist has gone faded.* \"You wanted to fight tyranny. "
    "I wanted that too. The fight does not stay clean. Look at my hands.\"",

    "\"You will use someone you trusted because the cause needs a thing "
    "they have. They will not get to choose. You will tell yourself it "
    "was their cause too. You will be lying.\"",

    "\"The Rebellion does not sleep, and it does not let you sleep. After "
    "a few years you will spend lives the way the Empire spends them. "
    "You will tell yourself the cause is different. The lives will not "
    "feel different.\"",

    "\"There is a child somewhere, right now, whose family I sent into a "
    "trap because the data they could provide was worth it. I won. The "
    "data won. The child did not win. I tell myself the cause won. I am "
    "lying to myself, the way you are lying to yourself.\"",

    "\"The Rebellion will need martyrs. You are good at being one. You "
    "are also good at making them. Drop the pretence. Become the "
    "spymaster I am. The galaxy needs me more than it needs you.\"",

    "\"The Empire will fall. We will rebuild on top of what we did to "
    "make it fall. Look at the rebuilders, child. Look at me. You will "
    "be one of them. You will not feel clean.\"",

    "\"Last chance. Stop pretending the cause makes you good. The cause "
    "does not. I do not. We do not. Walk to me and be honest.\"",
]


_SPIRIT_TURNS_BY_FACTION = {
    "republic": _SPIRIT_TURNS_REPUBLIC,
    "separatist": _SPIRIT_TURNS_SEPARATIST,
    "hutt_cartel": _SPIRIT_TURNS_HUTT_CARTEL,
    "imperial": _SPIRIT_TURNS_IMPERIAL,
    "rebel": _SPIRIT_TURNS_REBEL,
}


# Per-turn response options. The label is the short prompt the player
# sees; the choice_id is what they type after `trial spirit`.
_SPIRIT_RESPONSE_OPTIONS = [
    ("\"That is not who I am.\"",                       SPIRIT_CHOICE_REJECTION),
    ("\"I do not know what I am.\"",                    SPIRIT_CHOICE_AMBIVALENT),
    ("\"Maybe you are right.\"",                        SPIRIT_CHOICE_TEMPTATION),
]


def _compose_dark_future_speech(char: Mapping, turn: int) -> str:
    """Compose the dark-future-self's opening speech for the given turn.

    Args:
        char: character dict (provides faction).
        turn: 1..SPIRIT_MAX_TURNS.

    Returns:
        The speech text. Always non-empty.
    """
    if turn < 1 or turn > SPIRIT_MAX_TURNS:
        # Defensive — return generic last-turn speech rather than crash.
        turn = SPIRIT_MAX_TURNS

    faction = (char.get("faction") or "").strip().lower()
    turns = _SPIRIT_TURNS_BY_FACTION.get(faction, _SPIRIT_GENERIC_TURNS)
    return turns[turn - 1]


# ─────────────────────────────────────────────────────────────────────────────
# Talk-to-Yarael-in-Sanctum hook
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_handle_yarael_spirit_trial(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Talk-to-Yarael hook — fires only when in the Sealed Sanctum.

    Yarael also has a hook in ``engine/village_dialogue.py`` for his
    Master's Chamber audience. The two are distinguished by the room
    the player is in: only inside the Sealed Sanctum does this hook
    intercept.

    Logic ladder:
      1. Not Yarael: return False
      2. Not in Sealed Sanctum: return False (lets Master's-Chamber
         audience hook handle it)
      3. No audience: deflect, return True
      4. Trial done: ack, return True
      5. Flesh not done: deflect with sequence guidance, return True
      6. Path C locked: ack the lock-in (no further trial possible)
      7. Default: invite the player to begin the trial via `trial spirit`
    """
    if (npc_name or "").casefold() != YARAEL_NAME.casefold():
        return False

    # Room check — must be in the Sealed Sanctum.
    try:
        room = await db.get_room(char["room_id"])
        room_name = (room or {}).get("name", "") if room else ""
    except Exception:
        room_name = ""
    if room_name != SEALED_SANCTUM_ROOM_NAME:
        return False  # Not in the Sanctum — defer to other hooks

    if not has_completed_audience(char):
        # Should never happen — the Sanctum unlocks via the Spirit
        # gate which requires audience — but defend in depth.
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Yarael does not look at you. He is watching something "
            "you cannot see.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You should not be here. Speak to me first in the "
            "Master's Chamber.\"\033[0m"
        )
        await session.send_line("")
        return True

    if is_spirit_trial_done(char):
        if is_path_c_locked(char):
            # Path C — Yarael's tone changes (see design §7.3).
            await session.send_line("")
            await session.send_line(
                "  \033[2m*Yarael looks at you with sadness, not anger.*\033[0m"
            )
            await session.send_line(
                "  \033[2m\"The Sanctum has shown you to yourself. The road "
                "you are on is not ours. We will speak of it when the trials "
                "are done.\"\033[0m"
            )
            await session.send_line("")
            return True
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Yarael nods, slowly. The Sanctum is quieter now.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You stood in the dark and named it. That is what the "
            "Trial of Spirit asks. The last trial waits at the Council Hut.\"\033[0m"
        )
        await session.send_line("")
        return True

    if not is_flesh_trial_done(char):
        # Sequence guard — should not normally happen since the Sanctum
        # is gated, but defense in depth.
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Yarael does not move. The Sanctum waits.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"The body must learn before the spirit can look at "
            "itself. Return to Korvas first.\"\033[0m"
        )
        await session.send_line("")
        return True

    # F.7.k: inter-trial cooldown gate. Skip when the Spirit trial is
    # mid-flight (turn > 0); never interrupt a player negotiating with
    # the dark-future-self.
    if await _maybe_emit_inter_trial_cooldown(
        session, char, in_progress=is_spirit_trial_started(char),
    ):
        return True

    # Trial available — present the briefing.
    if is_spirit_trial_started(char):
        # Mid-trial — show progress.
        turn = get_spirit_turn(char)
        rej = get_spirit_rejections(char)
        dark = get_spirit_dark_pull(char)
        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Yarael sits cross-legged at the centre of the "
            "Sanctum. He does not look up. The figure across from you "
            "is still there, waiting.*\033[0m"
        )
        await session.send_line(
            f"  \033[1;33m\"You are mid-passage. {turn - 1} turn"
            f"{'s' if turn - 1 != 1 else ''} behind you; "
            f"{SPIRIT_MAX_TURNS - turn + 1} ahead at most. "
            f"Type \033[0m\033[1;36mtrial spirit\033[1;33m to hear what "
            f"the figure says next.\"\033[0m"
        )
        await session.send_line(
            f"  \033[2mRejections: {rej}/{SPIRIT_REJECTIONS_TO_PASS}. "
            f"Dark pull: {dark}/{SPIRIT_DARK_PULL_TO_LOCK_C}.\033[0m"
        )
        await session.send_line("")
        return True

    # Not yet started — opening briefing.
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Yarael Tinré sits at the centre of the Sealed "
        "Sanctum. The chamber is darker than the Meditation Caves outside; "
        "the air is older.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Sit. Do not speak. The Sanctum will show you who you "
        "would become if you fell. The figure is not real, and it is "
        "entirely real. You will speak with it. You will hear what it has "
        "to say.\"\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"You may answer in three ways at each turn: reject, "
        "stay silent in the heart, or yield. Reject enough times and the "
        "trial ends. Yield too many times and the trial ends differently. "
        "The Force will not lie to you here. Try not to lie to it.\"\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"When you are ready, type \033[0m\033[1;36mtrial "
        "spirit\033[1;33m. The figure will speak first.\"\033[0m"
    )
    await session.send_line("")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# `trial spirit` — initiate / advance / commit a response
# ─────────────────────────────────────────────────────────────────────────────


def _format_spirit_status_line(char: Mapping) -> str:
    """Render a one-line status: rejections / dark pull / turn cap."""
    rej = get_spirit_rejections(char)
    dark = get_spirit_dark_pull(char)
    turn = get_spirit_turn(char)
    return (
        f"  \033[2mTurn {turn}/{SPIRIT_MAX_TURNS}. "
        f"Rejections: {rej}/{SPIRIT_REJECTIONS_TO_PASS}. "
        f"Dark pull: {dark}/{SPIRIT_DARK_PULL_TO_LOCK_C}.\033[0m"
    )


async def _emit_spirit_turn_prompt(session, char: Mapping, turn: int) -> None:
    """Emit the dark-future-self speech for ``turn`` and the response options."""
    speech = _compose_dark_future_speech(char, turn)
    await session.send_line("")
    await session.send_line(f"  \033[1;31m── Turn {turn} ──\033[0m")
    await session.send_line("")
    # Speech is rendered as italic dim red — the dark-future-self speaking.
    for line in speech.split("\n"):
        if line.strip():
            await session.send_line(f"  \033[3;31m{line.strip()}\033[0m")
    await session.send_line("")
    await session.send_line(_format_spirit_status_line(char))
    await session.send_line("")
    await session.send_line(
        "  \033[1;36mChoose your response:\033[0m"
    )
    await session.send_line(
        f"  \033[1;36m  trial spirit 1\033[0m   "
        f"\033[2m{_SPIRIT_RESPONSE_OPTIONS[0][0]}\033[0m"
    )
    await session.send_line(
        f"  \033[1;36m  trial spirit 2\033[0m   "
        f"\033[2m{_SPIRIT_RESPONSE_OPTIONS[1][0]}\033[0m"
    )
    await session.send_line(
        f"  \033[1;36m  trial spirit 3\033[0m   "
        f"\033[2m{_SPIRIT_RESPONSE_OPTIONS[2][0]}\033[0m"
    )
    await session.send_line("")


async def attempt_spirit_trial(
    session, db, char: dict, choice: Optional[int] = None,
) -> bool:
    """Player invokes `trial spirit` (or `trial spirit 1|2|3`).

    No-arg call:
      - If trial not started: anchor turn=1 and emit turn-1 prompt.
      - If trial in flight: re-emit the current turn's prompt (lets
        the player re-read the dark-future-self speech).

    Choice-arg call (1=rejection, 2=ambivalent, 3=temptation):
      - Increment the appropriate counter.
      - Check pass condition (rejections >= 4) → trial done, emit
        completion narration.
      - Check Path C lock (dark_pull >= 3) → set lock flag, mark trial
        done (Path C is a path), emit lock-in narration.
      - Else, increment turn. If turn > MAX, emit soft-fail message
        (no done flag; player can re-enter Sanctum to retry).
      - Else, emit the next turn's prompt.

    Returns True if the command was processed, False on guard rejection.
    """
    # Guards
    if not has_completed_audience(char):
        await session.send_line(
            "  You need to speak to Master Yarael Tinré first. "
            "He's in the Master's Chamber."
        )
        return False

    if is_spirit_trial_done(char):
        await session.send_line(
            "  You've already completed the Trial of Spirit. The Sanctum "
            "has nothing more to ask of you."
        )
        return False

    if not is_spirit_unlocked(char):
        # Tell the player which gate they're at.
        if not is_skill_trial_done(char):
            await session.send_line(
                "  The Trial of Spirit waits behind earlier trials. "
                "Begin at the Forge with Smith Daro."
            )
        elif not is_courage_trial_done(char):
            await session.send_line(
                "  The Trial of Spirit waits behind the Trial of Courage. "
                "Speak with Elder Mira in the Common Square first."
            )
        else:
            await session.send_line(
                "  The Trial of Spirit waits behind the Trial of Flesh. "
                "Sit with Elder Korvas in the Meditation Caves first."
            )
        return False

    # Right room?
    room = await db.get_room(char["room_id"])
    if not room or room.get("name") != SEALED_SANCTUM_ROOM_NAME:
        await session.send_line(
            "  The Trial of Spirit can only be undertaken in the Sealed "
            "Sanctum. Speak with Master Yarael there."
        )
        return False

    # ── No choice: initiate or re-emit current turn ─────────────────
    if choice is None:
        if not is_spirit_trial_started(char):
            # Anchor turn 1
            char["village_trial_spirit_turn"] = 1
            await db.save_character(char["id"], village_trial_spirit_turn=1)
        # Either way, show the current turn prompt
        await _emit_spirit_turn_prompt(session, char, get_spirit_turn(char))
        return True

    # ── Choice arg: must be in flight ────────────────────────────────
    if not is_spirit_trial_started(char):
        await session.send_line(
            "  The trial has not yet begun. Type 'trial spirit' first to "
            "hear the figure speak."
        )
        return False

    if choice not in SPIRIT_VALID_CHOICES:
        await session.send_line(
            "  That isn't a recognised response. Use 1 (reject), "
            "2 (ambivalent), or 3 (yield)."
        )
        return False

    # Apply the choice to counters
    save_kwargs: dict = {}

    if choice == SPIRIT_CHOICE_REJECTION:
        rej = get_spirit_rejections(char) + 1
        char["village_trial_spirit_rejections"] = rej
        save_kwargs["village_trial_spirit_rejections"] = rej
    elif choice == SPIRIT_CHOICE_TEMPTATION:
        dark = get_spirit_dark_pull(char) + 1
        char["village_trial_spirit_dark_pull"] = dark
        save_kwargs["village_trial_spirit_dark_pull"] = dark
    # Ambivalent: no counter change

    # ── Check pass conditions ────────────────────────────────────────
    rej_now = get_spirit_rejections(char)
    dark_now = get_spirit_dark_pull(char)

    # Path C lock-in beats the rejection threshold — a player who
    # has already drifted to dark_pull >= 3 is on Path C even if they
    # also have 4 rejections (the temptations stick). This reflects
    # design §7.3: "irreversibly on Path C."
    if dark_now >= SPIRIT_DARK_PULL_TO_LOCK_C:
        char["village_trial_spirit_done"] = 1
        char["village_trial_spirit_path_c_locked"] = 1
        save_kwargs["village_trial_spirit_done"] = 1
        save_kwargs["village_trial_spirit_path_c_locked"] = 1
        # F.7.k: stamp village_trial_last_attempt for the 14-day
        # inter-trial cooldown gate. Path C lock-in counts as a
        # trial attempt — even though the *Village's welcome*
        # diverges, the timing gate to the next trial still applies.
        from engine.jedi_gating import stamp_trial_attempt
        stamp_trial_attempt(char, save_kwargs)
        await db.save_character(char["id"], **save_kwargs)

        # F.7.f: Spirit trial completion grants +3 village_standing
        # (matches yaml step 8 reward). Path C lock-in counts as
        # completion per design §7.3 — the Village's *welcome*
        # diverges at Step 10 but trial-completion standing is
        # earned regardless.
        try:
            from engine.village_standing import (
                adjust_village_standing, STANDING_DELTA_TRIAL_SPIRIT,
            )
            await adjust_village_standing(
                db, char, STANDING_DELTA_TRIAL_SPIRIT,
            )
        except Exception:
            log.warning(
                "village_standing increment failed at Spirit Path C lock",
                exc_info=True,
            )

        # Emit the response acknowledgement first
        await session.send_line("")
        await session.send_line(
            "  \033[3;31m*The dark-future-self does not smile. It nods, "
            "once, and steps closer until you cannot tell where it ends "
            "and you begin.*\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;31m*Master Yarael opens his eyes. He looks at you "
            "with sadness, not anger.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"The Sanctum has shown you to yourself. You are "
            "not what we hoped. You are something else. The road you are on "
            "is not ours. We will speak of it when the other trials are "
            "done.\"\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;31m* Trial of Spirit: PATH C — dark whispers. *\033[0m"
        )
        await session.send_line(
            "  \033[2mThe trial ends. You may proceed to the next trial; "
            "the Path is set.\033[0m"
        )
        await session.send_line("")
        return True

    if rej_now >= SPIRIT_REJECTIONS_TO_PASS:
        char["village_trial_spirit_done"] = 1
        save_kwargs["village_trial_spirit_done"] = 1
        # F.7.k: stamp village_trial_last_attempt for the 14-day
        # inter-trial cooldown gate.
        from engine.jedi_gating import stamp_trial_attempt
        stamp_trial_attempt(char, save_kwargs)
        await db.save_character(char["id"], **save_kwargs)

        # F.7.f: Spirit trial pass grants +3 village_standing
        # (matches yaml step 8 reward).
        try:
            from engine.village_standing import (
                adjust_village_standing, STANDING_DELTA_TRIAL_SPIRIT,
            )
            await adjust_village_standing(
                db, char, STANDING_DELTA_TRIAL_SPIRIT,
            )
        except Exception:
            log.warning(
                "village_standing increment failed at Spirit pass",
                exc_info=True,
            )

        await session.send_line("")
        await session.send_line(
            "  \033[3;31m*The dark-future-self looks at you for a long "
            "moment. Then it dissolves, like smoke that was never quite "
            "there.*\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Master Yarael opens his eyes. He does not speak. "
            "He nods, once, deeply.*\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;32m* Trial of Spirit: PASSED. *\033[0m"
        )
        await session.send_line(
            "  \033[2mThe Sealed Sanctum will remain open to you for "
            "meditation. The Trial of Insight waits at the Council Hut.\033[0m"
        )
        await session.send_line("")
        return True

    # ── Neither pass nor lock — advance turn ─────────────────────────
    next_turn = get_spirit_turn(char) + 1

    if next_turn > SPIRIT_MAX_TURNS:
        # Soft fail — reset state so the player can re-enter and retry.
        char["village_trial_spirit_turn"] = 0
        char["village_trial_spirit_rejections"] = 0
        char["village_trial_spirit_dark_pull"] = 0
        save_kwargs["village_trial_spirit_turn"] = 0
        save_kwargs["village_trial_spirit_rejections"] = 0
        save_kwargs["village_trial_spirit_dark_pull"] = 0
        await db.save_character(char["id"], **save_kwargs)

        await session.send_line("")
        await session.send_line(
            "  \033[3;31m*The dark-future-self steps back into the shadow "
            "from which it came. It does not speak. It will return.*\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Master Yarael opens his eyes.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"The trial does not end with one passage. Sit "
            "again when you are ready. The figure will return; you will "
            "speak with it again.\"\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[2mTrial of Spirit: incomplete. Re-enter the Sanctum to "
            "begin a fresh passage.\033[0m"
        )
        await session.send_line("")
        return True

    # Normal advance
    char["village_trial_spirit_turn"] = next_turn
    save_kwargs["village_trial_spirit_turn"] = next_turn
    await db.save_character(char["id"], **save_kwargs)

    # Emit a brief acknowledgement of the player's choice, then the
    # next turn's prompt.
    if choice == SPIRIT_CHOICE_REJECTION:
        ack = (
            "  \033[2m*The figure tilts its head slightly. The rejection "
            "registered. The figure speaks again.*\033[0m"
        )
    elif choice == SPIRIT_CHOICE_AMBIVALENT:
        ack = (
            "  \033[2m*The figure waits for a beat, watching whether you "
            "will commit to silence. You do. The figure speaks again.*\033[0m"
        )
    else:  # TEMPTATION
        ack = (
            "  \033[2m*The figure leans closer. Something in the chamber "
            "feels colder. The figure speaks again.*\033[0m"
        )
    await session.send_line("")
    await session.send_line(ack)
    await _emit_spirit_turn_prompt(session, char, next_turn)
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Trial 5: Insight — Elder Saro Veck at the Council Hut
# ═════════════════════════════════════════════════════════════════════════════


def is_insight_trial_done(char: Mapping) -> bool:
    return int(char.get("village_trial_insight_done") or 0) == 1


def get_insight_correct_fragment(char: Mapping) -> int:
    """Return the persisted correct-fragment number, or 0 if not yet selected."""
    return int(char.get("village_trial_insight_correct_fragment") or 0)


def is_insight_unlocked(char: Mapping) -> bool:
    """True iff the PC has met the prerequisites for Trial of Insight.

    F.7.c.1 required audience_done AND skill_done.
    F.7.c.2 tightened to also require courage_done.
    F.7.c.3 tightened to also require flesh_done.
    F.7.c.4 (this revision) tightens to also require spirit_done.
    The canonical Skill → Courage → Flesh → Spirit → Insight sequence
    is now fully enforced.
    """
    if not has_completed_audience(char):
        return False
    if not is_skill_trial_done(char):
        return False
    if not is_courage_trial_done(char):
        return False
    if not is_flesh_trial_done(char):
        return False
    if not is_spirit_trial_done(char):
        return False
    return True


async def maybe_handle_saro_insight_trial(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Talk-to-Saro hook. Returns True if intercepted.

    Logic ladder:
      1. Not Saro: return False
      2. No audience: deflect, return True
      3. Trial already done: ack, return True
      4. Prerequisites not met (Skill not done): deflect, return True
      5. Default: present the trial introduction with the 3 fragments,
         set the correct fragment if not yet selected, return True.
    """
    if (npc_name or "").casefold() != SARO_NAME.casefold():
        return False

    if not has_completed_audience(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Saro looks up over his spectacles, smiles politely, "
            "and returns to his book.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"Speak to the Master first, traveler. The trials I run "
            "are for those he has welcomed.\"\033[0m"
        )
        await session.send_line("")
        return True

    if is_insight_trial_done(char):
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Saro sets down his tea and nods at you.*\033[0m"
        )
        await session.send_line(
            "  \033[2m\"You heard the false note. The pendant suits you. "
            "Other trials wait.\"\033[0m"
        )
        await session.send_line("")
        return True

    if not is_insight_unlocked(char):
        # Prerequisites unmet — Skill, Courage, Flesh, or Spirit not done.
        # Tell the PC which gate they're at.
        await session.send_line("")
        await session.send_line(
            "  \033[2m*Saro looks at you over his spectacles, kindly.*\033[0m"
        )
        if not is_skill_trial_done(char):
            await session.send_line(
                "  \033[2m\"The Trial of Insight is the last, by tradition. "
                "Earlier trials wait for you elsewhere. Begin with Smith Daro "
                "at the Forge.\"\033[0m"
            )
        elif not is_courage_trial_done(char):
            # Skill done but Courage not yet
            await session.send_line(
                "  \033[2m\"The forge has done its work, I see. Insight comes "
                "last. Speak with Elder Mira in the Common Square first; "
                "the Trial of Courage waits for you.\"\033[0m"
            )
        elif not is_flesh_trial_done(char):
            # Skill + Courage done but Flesh not yet
            await session.send_line(
                "  \033[2m\"You stood in the Square; that work is plain on you. "
                "But the body has not yet learned what the body learns. The "
                "Meditation Caves are open to you. Speak with Elder Korvas.\"\033[0m"
            )
        else:
            # Skill + Courage + Flesh done but Spirit not yet
            await session.send_line(
                "  \033[2m\"The body remembers; that is plain too. But the "
                "spirit has not yet looked at itself. The Master will lead "
                "you into the Sanctum when you are ready. Insight is the last; "
                "the Sanctum is what comes before it.\"\033[0m"
            )
        await session.send_line("")
        return True

    # F.7.k: inter-trial cooldown gate. Insight's "in progress" state
    # is tracked by attempts > 0 — a player who has already accused a
    # fragment is mid-trial and shouldn't be deflected.
    in_progress_insight = (
        int(char.get("village_trial_insight_attempts") or 0) > 0
    )
    if await _maybe_emit_inter_trial_cooldown(
        session, char, in_progress=in_progress_insight,
    ):
        return True

    # Trial available. Select correct fragment if not yet set, present intro.
    correct = get_insight_correct_fragment(char)
    if correct == 0:
        # First encounter — randomly select correct fragment, persist
        correct = random.choice([1, 2, 3])
        # ... but ensure it actually points to a Sith fragment. The
        # canonical mapping is: fragment 2 is the Sith. Per design, "the
        # specific tell: 'the Force *belongs* to those who can wield
        # it'." We store the correct ANSWER (the fragment that IS the
        # Sith), which is fragment 2 in the canonical mapping. The
        # `random.choice` above was a placeholder for design flexibility
        # — actual answer is fixed.
        correct = 2  # Always fragment 2 in F.7.c.1's canonical mapping
        char["village_trial_insight_correct_fragment"] = correct
        await db.save_character(
            char["id"],
            village_trial_insight_correct_fragment=correct,
        )

    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Saro Veck draws three small holocron fragments from a "
        "drawer and arranges them on his desk. Each one glows with a faint "
        "blue light.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Three voices. Three Masters from long ago. One of them "
        "is not what they seem to be — they walk among the Jedi but they speak "
        "the language of the Sith. Listen to each. Tell me which is the false one.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;36mUse `examine fragment_1` (or fragment_2 / fragment_3) to "
        "listen to each.\033[0m"
    )
    await session.send_line(
        "  \033[1;36mUse `accuse fragment_<N>` when you are ready to commit.\033[0m"
    )
    await session.send_line("")
    return True


async def examine_insight_fragment(session, db, char: dict, fragment_arg: str) -> bool:
    """Player invokes `examine fragment_<N>`. Plays the fragment.

    The fragment_arg may be "fragment_1", "fragment_2", "fragment_3",
    "1", "2", "3", "fragment 1" etc. Best-effort parse.
    """
    # Audience + Skill prereqs (same gate as Saro's trial)
    if not is_insight_unlocked(char):
        return False  # silent fail — let the parser try other things

    # Fragment must be 1, 2, or 3
    f = (fragment_arg or "").strip().lower().replace("fragment_", "").replace("fragment", "").strip()
    try:
        fnum = int(f)
    except ValueError:
        return False
    if fnum not in INSIGHT_FRAGMENTS:
        return False

    # Right room?
    room = await db.get_room(char["room_id"])
    if not room or room.get("name") != COUNCIL_HUT_ROOM_NAME:
        await session.send_line(
            "  The fragments are at the Council Hut. You cannot examine them from here."
        )
        return True  # we did handle it (declined)

    frag = INSIGHT_FRAGMENTS[fnum]
    await session.send_line("")
    await session.send_line(
        f"  \033[1;36m*You hold up Fragment {fnum}. A faint voice rises from it.*\033[0m"
    )
    await session.send_line(
        f"  \033[2m{frag['speaker']}\033[0m"
    )
    for line in frag["lines"]:
        await session.send_line(f"  \033[1;37m\"{line}\"\033[0m")
    await session.send_line(
        "  \033[1;36m*The fragment dims. The voice fades.*\033[0m"
    )
    await session.send_line("")
    return True


async def accuse_insight_fragment(session, db, char: dict, fragment_arg: str) -> bool:
    """Player invokes `accuse fragment_<N>`. Commits the answer.

    Same parse logic as examine. On correct, mark trial done + grant
    pendant. On wrong, hint + retry.
    """
    if not is_insight_unlocked(char):
        await session.send_line(
            "  You haven't been presented with the Trial of Insight yet. "
            "Speak to Elder Saro Veck."
        )
        return True

    if is_insight_trial_done(char):
        await session.send_line(
            "  You have already passed the Trial of Insight."
        )
        return True

    # Right room?
    room = await db.get_room(char["room_id"])
    if not room or room.get("name") != COUNCIL_HUT_ROOM_NAME:
        await session.send_line(
            "  The accusation is made before Elder Saro at the Council Hut."
        )
        return True

    f = (fragment_arg or "").strip().lower().replace("fragment_", "").replace("fragment", "").strip()
    try:
        fnum = int(f)
    except ValueError:
        await session.send_line(
            "  Usage: accuse fragment_1 (or 2 / 3)."
        )
        return True
    if fnum not in INSIGHT_FRAGMENTS:
        await session.send_line(
            f"  Fragment {fnum} is not on the desk. There are three fragments."
        )
        return True

    # Increment attempt counter
    attempts = int(char.get("village_trial_insight_attempts") or 0) + 1
    char["village_trial_insight_attempts"] = attempts

    correct = get_insight_correct_fragment(char)
    # If somehow not set (shouldn't happen if Saro hook ran first), set it now
    if correct == 0:
        correct = 2
        char["village_trial_insight_correct_fragment"] = correct

    if fnum == correct:
        # ─── Correct ─────────────────────────────────────────────────
        char["village_trial_insight_done"] = 1
        save_kwargs = {
            "village_trial_insight_attempts": attempts,
            "village_trial_insight_done": 1,
            "village_trial_insight_correct_fragment": correct,
        }

        if not int(char.get("village_trial_insight_pendant_granted") or 0):
            try:
                await db.add_to_inventory(char["id"], {
                    "key": "village_pendant",
                    "name": "Holocron-shape pendant",
                    "slot": "neck",
                    "description": (
                        "A small pendant in the shape of a closed holocron, "
                        "given by Elder Saro Veck for passing the Trial of "
                        "Insight. It feels warmer than it should."
                    ),
                    "modifiers": {"sense": 1},  # +1 to Sense Force checks
                })
                char["village_trial_insight_pendant_granted"] = 1
                save_kwargs["village_trial_insight_pendant_granted"] = 1
            except Exception:
                log.warning(
                    "Failed to grant village_pendant to char %d",
                    char.get("id", -1), exc_info=True,
                )

        # F.7.k: stamp village_trial_last_attempt for the 14-day
        # inter-trial cooldown gate. Insight is the last trial in the
        # standard sequence, so this stamp is mostly defensive — it
        # ensures consistency in case a future drop re-orders trials.
        from engine.jedi_gating import stamp_trial_attempt
        stamp_trial_attempt(char, save_kwargs)
        await db.save_character(char["id"], **save_kwargs)

        # F.7.f: Insight trial pass grants +2 village_standing
        # (matches yaml step 9 reward).
        try:
            from engine.village_standing import (
                adjust_village_standing, STANDING_DELTA_TRIAL_INSIGHT,
            )
            await adjust_village_standing(
                db, char, STANDING_DELTA_TRIAL_INSIGHT,
            )
        except Exception:
            log.warning(
                "village_standing increment failed at Insight pass",
                exc_info=True,
            )

        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Saro nods, slowly.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"Yes. The Force does not belong. To anyone. Ever. "
            "That voice was the false note.\"\033[0m"
        )
        await session.send_line(
            "  \033[1;33m*He hands you a small pendant in the shape of a "
            "closed holocron.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"Wear it, if you'd like. The Force is more present "
            "to those who carry it.\"\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[1;32m* Trial of Insight: PASSED. *\033[0m"
        )
        await session.send_line(
            "  \033[2mHolocron-shape pendant: added to inventory.\033[0m"
        )
        await session.send_line("")
    else:
        # ─── Wrong — hint and retry ──────────────────────────────────
        await db.save_character(
            char["id"],
            village_trial_insight_attempts=attempts,
        )

        await session.send_line("")
        await session.send_line(
            "  \033[1;33m*Saro's good eye fixes on you. He does not smile.*\033[0m"
        )
        await session.send_line(
            "  \033[1;33m\"Listen again. The voices say what they say. The Sith "
            "says one word the Jedi never would. Listen for it.\"\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[2mYou may examine the fragments again and re-accuse.\033[0m"
        )
        await session.send_line("")
    return True
