# -*- coding: utf-8 -*-
"""
engine/village_dialogue.py — Village quest dialogue runtime (F.7.b, May 4 2026).

Per ``jedi_village_quest_design_v1.md`` §4.2: Sister Vitha's Gate
test. Three-choice dialogue. Choices [1] and [3] open the Gate;
choice [2] closes it for a 24-hour cooldown. The dialogue is a
single-turn test, not a multi-step tree.

Architecture
============

The dialogue runtime is a small state machine. There are exactly
two PC↔NPC dialogue interventions in this drop:

  1. **Step 3 — The Gate (Sister Vitha):** Pre-AI hook in
     TalkCommand. When a PC at ``village_act = ACT_INVITED`` (act 1)
     initiates ``talk Vitha``, the runtime:
       a) presents the three-choice menu (without firing AI dialogue),
       b) records the player as having an active gate offer,
       c) waits for the player to type ``gate <number>`` to commit.

  2. **Step 4 — First Audience (Master Yarael):** Post-AI hook in
     check_village_quest("talk", ...). When a PC at act 1 with
     ``village_gate_passed = 1`` talks to Master Yarael for the first
     time, the runtime advances them to ``ACT_IN_TRIALS``.

The "gate offer" state is in-memory (process-local) — the player has
to commit within the same session. If they disconnect without
choosing, the offer expires; they re-trigger by talking to Vitha
again, which is fine because the dialogue is itself non-state-
mutating until commit.

Cooldown semantics
==================

When the player chooses answer [2] ("I'm looking for the Master.
Take me to him."), Vitha closes the gate. ``village_gate_lockout_until``
is set to ``time.time() + 24 * 3600``. While that timestamp is in
the future, ``talk Vitha`` produces a closed-gate response (not the
choice menu). The player must wait it out. There is no skill check
or override — patience is the point of the test.

Re-entry after passing
======================

Once ``village_gate_passed = 1``, the gate is permanently open. Re-
visiting Vitha after passing produces a respectful acknowledgment;
the runtime defers to her fallback_lines for ambient flavor.

What this module does NOT do
============================

  - Does not handle the trials themselves (F.7.c/d).
  - Does not handle Path A/B/C choice (Act 3, future drop).
  - Does not handle the Hermit's after_lines emission — that's a
    small extension to engine/village_quest.py::_handle_talk.
  - Does not handle Sister Vitha's "ambient" lines outside the
    quest path — those come from her fallback_lines via the
    standard NPC dialogue surface.
"""
from __future__ import annotations

import logging
import time
from typing import Mapping, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VITHA_NAME: str = "Sister Vitha"
YARAEL_NAME: str = "Master Yarael Tinré"

# 24 hours in seconds. Per design §4.2: "you must wait 24 RL hours and
# try again."
GATE_COOLDOWN_SECONDS: int = 24 * 60 * 60

# Choice numbers. Per design §4.2:
#   [1] honest-receipt → pass
#   [2] demanding      → fail (24h cooldown)
#   [3] honest-doubt   → pass
GATE_CHOICE_PASS_RECEIPT: int = 1
GATE_CHOICE_FAIL_DEMAND: int = 2
GATE_CHOICE_PASS_DOUBT:   int = 3
VALID_GATE_CHOICES = {1, 2, 3}


# ─────────────────────────────────────────────────────────────────────────────
# In-memory state: pending gate offers
# ─────────────────────────────────────────────────────────────────────────────
#
# When a PC initiates `talk Vitha` at the right state, we present the
# three-choice menu and add an entry here. The player commits with
# `gate <number>`. If they disconnect, the offer expires (in-memory
# only). Process-local; not persisted.

_pending_gate_offers: dict[int, float] = {}  # char_id -> timestamp_offered

# Offers older than 30 minutes auto-expire (so a player who walks
# away and returns hours later doesn't accidentally commit on a
# stale `gate` command).
_GATE_OFFER_TTL_SECONDS: int = 30 * 60


def _purge_stale_offers() -> None:
    """Drop offer entries older than _GATE_OFFER_TTL_SECONDS."""
    now = time.time()
    expired = [
        cid for cid, ts in _pending_gate_offers.items()
        if now - ts > _GATE_OFFER_TTL_SECONDS
    ]
    for cid in expired:
        _pending_gate_offers.pop(cid, None)


def has_pending_gate_offer(char_id: int) -> bool:
    """True iff this character has an active (non-expired) gate offer."""
    _purge_stale_offers()
    return char_id in _pending_gate_offers


def offer_gate(char_id: int) -> None:
    """Record that this character has been presented the gate menu.

    Called by the Vitha pre-AI hook. Idempotent — a re-presentation
    just refreshes the offer timestamp.
    """
    _pending_gate_offers[char_id] = time.time()


def clear_gate_offer(char_id: int) -> None:
    """Remove this character's pending gate offer."""
    _pending_gate_offers.pop(char_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility checks
# ─────────────────────────────────────────────────────────────────────────────


def is_in_lockout(char: Mapping) -> tuple[bool, float]:
    """Return (in_lockout, seconds_remaining).

    In_lockout is True iff village_gate_lockout_until > current time.
    seconds_remaining is the float seconds until lockout ends (0 if
    not in lockout).
    """
    until = float(char.get("village_gate_lockout_until") or 0)
    now = time.time()
    if until > now:
        return True, until - now
    return False, 0.0


def is_at_gate_test_step(char: Mapping) -> bool:
    """True iff the character is at Step 3 (the Gate test).

    Step 3 means: ``village_act == 1`` (ACT_INVITED) AND gate not yet
    passed. After passing, the character moves to step 4; before
    invitation they're at step 1 or 2.
    """
    act = int(char.get("village_act") or 0)
    if act != 1:  # ACT_INVITED — see engine/village_quest.py
        return False
    if int(char.get("village_gate_passed") or 0) == 1:
        return False  # already passed
    return True


def has_passed_gate(char: Mapping) -> bool:
    """True iff Vitha has already admitted this character."""
    return int(char.get("village_gate_passed") or 0) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Gate dialogue display — the three-choice menu
# ─────────────────────────────────────────────────────────────────────────────


def render_gate_menu() -> list[str]:
    """Return the lines to display when presenting the Gate test.

    Per design §4.2, Vitha's opening line + three options. The
    options are numbered; the player commits with `gate 1` etc.
    """
    return [
        "",
        "  \033[1;33mSister Vitha looks up. Her eyes meet yours and stay there.\033[0m",
        "  \033[1;33m\"You stand at the edge of where you should not be.\"\033[0m",
        "",
        "  How do you answer?",
        "",
        "    \033[1;36m1.\033[0m \"I received a message. I came alone, as instructed.\"",
        "    \033[1;36m2.\033[0m \"I'm looking for the Master. Take me to him.\"",
        "    \033[1;36m3.\033[0m \"I don't know why I'm here. Something told me to come.\"",
        "",
        "  Type \033[1;33mgate 1\033[0m, \033[1;33mgate 2\033[0m, or \033[1;33mgate 3\033[0m to answer.",
        "",
    ]


def render_gate_locked_out(seconds_remaining: float) -> list[str]:
    """Return the lines for a player whose gate is on cooldown."""
    hours = max(1, int(seconds_remaining // 3600) + (1 if seconds_remaining % 3600 else 0))
    return [
        "",
        "  \033[2mSister Vitha does not look up.\033[0m",
        "  \033[2m\"Not today. Not yet. Come back when the desert has had its say.\"\033[0m",
        "",
        f"  \033[2;33m(The Gate is closed. About {hours} hour"
        f"{'s' if hours != 1 else ''} remain on the cooldown.)\033[0m",
        "",
    ]


def render_gate_already_passed() -> list[str]:
    """Lines for a player who has already passed the Gate."""
    return [
        "",
        "  \033[2mSister Vitha gives you a small nod, recognizing you.\033[0m",
        "  \033[2m\"You walk through where most do not. The Master's chamber is along the path.\"\033[0m",
        "",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Choice processing — invoked by the `gate <number>` command
# ─────────────────────────────────────────────────────────────────────────────


async def process_gate_choice(session, db, char: dict, choice: int) -> bool:
    """Process the player's choice in the Gate test.

    Returns True if the choice was processed (success or failure both
    return True — only an *invalid state* returns False, e.g. no
    pending offer, or character not at the right step).

    Side effects:
      - Writes village_gate_passed / village_gate_lockout_until /
        village_gate_attempts to the character row.
      - Advances village_act to 2 (ACT_IN_TRIALS — per design, Step 4
        is "First Audience" with the Master, but the design doc treats
        the Gate test as ending Act 1; on success we advance act to
        2 immediately so Step 4 hooks fire on the next Yarael talk).
      - Clears the pending offer.
      - Sends narrative response lines to the session.
    """
    if choice not in VALID_GATE_CHOICES:
        await session.send_line(f"  Invalid choice: {choice}. Use 1, 2, or 3.")
        return False

    if not has_pending_gate_offer(char["id"]):
        await session.send_line(
            "  You don't have a pending Gate dialogue. "
            "Speak to Sister Vitha first."
        )
        return False

    if not is_at_gate_test_step(char):
        # Defensive — pending offer survived a state change somehow.
        clear_gate_offer(char["id"])
        await session.send_line(
            "  The moment has passed. The Gate is no longer presenting itself."
        )
        return False

    # Increment attempts counter (telemetry — no in-game effect)
    attempts = int(char.get("village_gate_attempts") or 0) + 1
    char["village_gate_attempts"] = attempts

    # Branch on the choice
    if choice == GATE_CHOICE_FAIL_DEMAND:
        # Choice [2]: 24-hour cooldown
        until = time.time() + GATE_COOLDOWN_SECONDS
        char["village_gate_lockout_until"] = until
        await db.save_character(
            char["id"],
            village_gate_attempts=attempts,
            village_gate_lockout_until=until,
        )
        clear_gate_offer(char["id"])

        await session.send_line("")
        await session.send_line(
            "  \033[1;33m\"Many come demanding what they have not earned. "
            "They do not pass.\"\033[0m"
        )
        await session.send_line(
            "  \033[2mSister Vitha returns her gaze to the dunes. "
            "She does not say more.\033[0m"
        )
        await session.send_line("")
        await session.send_line(
            "  \033[2;33m(The Gate has closed. Try again in 24 hours.)\033[0m"
        )
        await session.send_line("")
        return True

    # Choices [1] and [3]: pass — write gate_passed=1, advance act to 2
    char["village_gate_passed"] = 1

    # Advance act to ACT_IN_TRIALS (=2) — the Gate test ends Act 1.
    # Step 4 (First Audience with Master Yarael) becomes the next live
    # transition; check_village_quest fires on the next `talk Yarael`
    # post-talk hook.
    from engine.village_quest import ACT_IN_TRIALS
    char["village_act"] = ACT_IN_TRIALS
    char["village_act_unlocked_at"] = time.time()

    await db.save_character(
        char["id"],
        village_gate_attempts=attempts,
        village_gate_passed=1,
        village_act=ACT_IN_TRIALS,
        village_act_unlocked_at=char["village_act_unlocked_at"],
    )
    clear_gate_offer(char["id"])

    # F.7.f: gate pass grants +1 village_standing
    # (matches yaml step 3 reward).
    try:
        from engine.village_standing import (
            adjust_village_standing, STANDING_DELTA_GATE_PASS,
        )
        await adjust_village_standing(db, char, STANDING_DELTA_GATE_PASS)
    except Exception:
        log.warning("village_standing increment failed at gate pass",
                    exc_info=True)

    # Choice-specific Vitha response
    if choice == GATE_CHOICE_PASS_RECEIPT:
        vitha_line = (
            "\"Many receive messages they cannot trace. "
            "Few choose to follow. You may pass.\""
        )
    else:  # GATE_CHOICE_PASS_DOUBT
        vitha_line = "\"Honesty. Rare. The Master will see you.\""

    await session.send_line("")
    await session.send_line(f"  \033[1;33m{vitha_line}\033[0m")
    await session.send_line(
        "  \033[2mSister Vitha steps aside. The path beyond her is open.\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;32m* You have passed the Gate. The Village is open to you. *\033[0m"
    )
    await session.send_line(
        "  \033[2mSpeak to Master Yarael Tinré in his chamber to begin the trials.\033[0m"
    )
    await session.send_line("")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# TalkCommand pre-AI hook — Vitha intervention
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_intercept_vitha_talk(session, db, char: dict, npc_name: str) -> bool:
    """Pre-AI hook for Sister Vitha. Returns True if intercepted.

    If True, the caller (TalkCommand.execute) skips the AI dialogue
    path entirely. If False, normal NPC dialogue proceeds (Vitha's
    fallback_lines via the Mistral surface).

    Cases:
      - Not Vitha: return False
      - Vitha + already-passed-gate: emit ack, return True
      - Vitha + in lockout: emit lockout message, return True
      - Vitha + at Step 3: present menu + record offer, return True
      - Vitha + other state (act 0, act 2+ after passing, etc.):
        return False (let fallback_lines handle it)
    """
    if (npc_name or "").casefold() != VITHA_NAME.casefold():
        return False

    # Already passed — emit ack, allow fallback to take over after
    if has_passed_gate(char):
        for line in render_gate_already_passed():
            await session.send_line(line)
        # Don't fully intercept — let the fallback_lines flavor follow
        # the ack on subsequent visits. But on this first re-visit, the
        # ack IS the response, so we DO intercept.
        return True

    # In lockout — emit closed-gate message
    in_lockout, remaining = is_in_lockout(char)
    if in_lockout:
        for line in render_gate_locked_out(remaining):
            await session.send_line(line)
        return True

    # At step 3 — present the menu, record the offer
    if is_at_gate_test_step(char):
        offer_gate(char["id"])
        for line in render_gate_menu():
            await session.send_line(line)
        return True

    # Some other state (pre-invitation, post-trials) — let the standard
    # NPC dialogue path take over via fallback_lines.
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — First Audience with Master Yarael
# ─────────────────────────────────────────────────────────────────────────────


async def maybe_handle_yarael_first_audience(
    session, db, char: dict, npc_name: str,
) -> bool:
    """Post-AI hook called from check_village_quest("talk", ...).

    Checks:
      - Target is Master Yarael Tinré.
      - PC has village_gate_passed = 1 (from Step 3) AND
        village_act = ACT_IN_TRIALS (we already advanced).
      - First-audience flag not yet set (we use a property — see below).

    Per design §4.3: the First Audience is when Yarael invites the
    PC to begin the trials. There's no skill check; the act of
    talking to him for the first time is the trigger. After this,
    Yarael remains available for trial-time dialogue.

    For F.7.b we record the first-audience moment via a custom flag
    in the character's chargen_notes (which is JSON). This avoids
    introducing a brand-new schema column for what is effectively
    a one-shot bool. F.7.c can lift this into a proper column if
    repeated such flags accumulate.

    Returns True if the audience fired (one-shot).
    """
    if (npc_name or "").casefold() != YARAEL_NAME.casefold():
        return False

    if not has_passed_gate(char):
        return False  # PC hasn't passed the Gate yet; Yarael ignores them

    # Idempotent — only fire the audience message once per character.
    # Use chargen_notes as a flag store.
    import json
    notes_raw = char.get("chargen_notes") or "{}"
    try:
        notes = json.loads(notes_raw) if isinstance(notes_raw, str) else dict(notes_raw)
    except (json.JSONDecodeError, TypeError):
        notes = {}

    if notes.get("village_first_audience_done"):
        return False  # Audience already happened

    # Mark as done
    notes["village_first_audience_done"] = True
    char["chargen_notes"] = json.dumps(notes)
    await db.save_character(
        char["id"],
        chargen_notes=char["chargen_notes"],
    )

    # F.7.f: first audience grants +1 village_standing
    # (matches yaml step 4 reward).
    try:
        from engine.village_standing import (
            adjust_village_standing, STANDING_DELTA_FIRST_AUDIENCE,
        )
        await adjust_village_standing(
            db, char, STANDING_DELTA_FIRST_AUDIENCE,
        )
    except Exception:
        log.warning("village_standing increment failed at first audience",
                    exc_info=True)

    # Emit the first-audience response
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Yarael sets down his work and turns to face you. "
        "His pale eyes settle on yours and remain there for a long moment.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Young one. So. You arrived. Vitha would not have stepped aside "
        "for the wrong sort. We will see what kind of right sort you are.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m\"There are five trials. You will take them in order. "
        "I will not soften them. The work is the work. Begin when you are ready — "
        "the Forge is the first stop.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;32m* You have begun the Trials. *\033[0m"
    )
    await session.send_line(
        "  \033[2mUse 'quest' to see your progress. The Forge awaits — "
        "Smith Daro will examine your patience first.\033[0m"
    )
    await session.send_line("")
    return True
