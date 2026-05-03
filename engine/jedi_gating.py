# -*- coding: utf-8 -*-
"""
engine/jedi_gating.py — Progression Gates Phase 3, sub-drop a (PG.3.gates.a).

Implements the two non-Village pieces of the Jedi gating design:

  1. **Predisposition scoring** at chargen — a hidden 0.0–1.0 score
     per character, set once and never modified, that the Director
     uses to weight Force-flavor density (PG.3.gates.b will consume
     it in the Force-sign trigger refactor).
  2. **Play-time accumulation** — incremental update of
     ``characters.play_time_seconds`` driven by the per-minute
     heartbeat in ``server/tick_handlers_progression.py``. Idle
     sessions are filtered by the caller; this module just does
     the math and the DB write.

This module is *pure-ish*: every function takes its inputs explicitly
(no global state, no module-level config). Random seeds are accepted
as parameters so tests are fully deterministic.

What this drop deliberately does NOT do:
  - Refactor the Force-sign trigger (PG.3.gates.b)
  - Consult ``play_time_seconds`` from the Director (PG.3.gates.b)
  - Enforce real-time Act/Trial cooldowns (PG.3.gates.b)
  - Remove the Force Sensitivity checkbox from chargen (PG.3.gates.b)

See ``progression_gates_and_consequences_design_v1.md`` §2.3, §2.4,
§2.8, and the v40 architecture §3.5 prerequisite stack for the full
context.
"""
from __future__ import annotations

import logging
import re
from typing import Mapping, Optional, Sequence

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Predisposition scoring
# ─────────────────────────────────────────────────────────────────────────────

# Species that lore-relevantly skew toward Force sensitivity. These are
# *weights*, not gates: a Sullustan with the right backstory still scores
# high; a Miraluka with no backstory still scores noticeably above zero.
# Keys are lowercased, whitespace-stripped species names; lookups are
# case-insensitive.
#
# Sources used to set these defaults:
#   - WEG R&E core (Force-sensitive species annotations)
#   - WEG TOTJ Companion (Jedi Knights of the Old Republic context)
#   - Wookieepedia extracts (force-sensitive listings) where consistent
#     with WEG-canonical lore
#
# These are starting weights; tune from observed conversion data once
# the gate is live.
SPECIES_PREDISPOSITION_WEIGHTS: Mapping[str, float] = {
    # Strongly Force-attuned species
    "miraluka":     0.50,   # canonically all Force-sensitive
    "kel dor":      0.35,
    "iktotchi":     0.30,
    "zabrak":       0.20,
    "cerean":       0.20,
    "togruta":      0.20,
    "nautolan":     0.15,

    # Mid-tier — recurring lore presence in the Jedi Order
    "twi'lek":      0.15,
    "twilek":       0.15,   # tolerate both spellings
    "human":        0.10,
    "mirialan":     0.10,

    # Baseline — no canonical predisposition either way
    "rodian":       0.05,
    "duros":        0.05,
    "bothan":       0.05,
    "sullustan":    0.05,
    "ithorian":     0.05,
    "trandoshan":   0.05,
    "wookiee":      0.05,

    # Lore-suppressed (don't go negative — just no boost)
    "neimoidian":   0.0,
    "hutt":         0.0,
    "geonosian":    0.0,
}

# Backstory keywords that nudge predisposition upward. Matched as
# whole-word case-insensitive substrings against the backstory text.
# Each match adds its weight; total backstory contribution is capped
# at +0.30 so the field stays a flavor input, not a gameplay knob.
#
# These are intentionally on-theme rather than mechanical: a player
# writing a hero's-journey arc gets a small lift over a player
# writing "I am a smuggler. The end."
BACKSTORY_KEYWORD_WEIGHTS: Mapping[str, float] = {
    # Direct Force / mystic vocabulary
    r"\bforce\b":               0.10,
    r"\bjedi\b":                0.08,
    r"\bsith\b":                0.06,
    r"\bmidi-?chlorian\b":      0.10,
    r"\bmeditat\w*\b":          0.06,  # meditate / meditation
    r"\bvision\w*\b":           0.05,
    r"\bdream\w*\b":            0.04,
    r"\bprophe\w+\b":           0.06,
    r"\bdestin\w+\b":           0.05,  # destiny / destined

    # Mystical-adjacent vocabulary
    r"\bmystic\w*\b":           0.06,
    r"\bspirit\w*\b":           0.04,
    r"\bancien\w+\b":           0.03,
    r"\btemple\w*\b":           0.04,
    r"\bsage\b":                0.04,
    r"\bhermit\w*\b":           0.05,
    r"\bmonast\w+\b":           0.04,
    r"\bmonk\w*\b":             0.04,

    # Trauma + loss + searching arcs (classic Jedi origins)
    r"\borph\w+\b":             0.04,  # orphan / orphaned
    r"\blost\b":                0.02,
    r"\bseeker\w*\b":           0.05,
    r"\bsearch\w+\b":           0.03,
    r"\bcalling\b":             0.05,
    r"\bpurpose\b":             0.03,
}

# Hard cap on the backstory contribution so a wall of keyword-stuffed
# text can't dominate the score.
BACKSTORY_TOTAL_CAP: float = 0.30

# Hard floor and ceiling on the final score. The design says 0.0–1.0;
# we never want a negative value (would be ambiguous downstream) and
# capping at 1.0 keeps the Director's weighting math clean.
PREDISPOSITION_FLOOR: float = 0.0
PREDISPOSITION_CEILING: float = 1.0


def _normalize_species(species: Optional[str]) -> str:
    """Return a normalized species key for the weights map.

    Strips whitespace, lowercases, and collapses internal whitespace
    runs to a single space. Returns empty string for None/empty
    inputs (those just score 0 from species).
    """
    if not species:
        return ""
    return re.sub(r"\s+", " ", species.strip()).lower()


def _backstory_score(backstory: str) -> float:
    """Sum keyword weights present in the backstory, capped.

    Returns 0.0 for empty / very short text. Whole-word matching via
    the regexes in BACKSTORY_KEYWORD_WEIGHTS so substring noise
    ('forced', 'jedidiah', etc.) doesn't fire.
    """
    if not backstory or len(backstory) < 5:
        return 0.0
    text = backstory.lower()
    total = 0.0
    for pattern, weight in BACKSTORY_KEYWORD_WEIGHTS.items():
        if re.search(pattern, text):
            total += weight
    return min(total, BACKSTORY_TOTAL_CAP)


def compute_predisposition(
    species: Optional[str],
    backstory: Optional[str],
    rng_roll: float = 0.0,
) -> float:
    """Compute a per-character force_predisposition score.

    Per design §2.4, predisposition is a hidden 0.0–1.0 value
    informed by:
      - Species (some lore-relevant species weighted up)
      - Backstory keywords parsed from the chargen narrative field
      - A Director RNG roll

    Args:
        species: The character's species name. Case-insensitive
            lookup against SPECIES_PREDISPOSITION_WEIGHTS.
        backstory: Free-text background field captured at chargen
            (``CreationWizard.background``). Empty / short input
            contributes 0.
        rng_roll: A pre-rolled value in [0.0, 0.5] supplied by the
            caller. The caller is expected to draw this from an
            RNG seeded however it wants (test seeds, Director seed,
            stdlib random — this module doesn't care). Capped at
            0.5 so the RNG never single-handedly produces a maxed
            score; species + backstory must contribute too. Values
            outside [0.0, 0.5] are clamped silently (callers
            shouldn't depend on this; it's a safety net).

    Returns:
        A float in [0.0, 1.0]. Never NaN, never negative, never > 1.
    """
    species_score = SPECIES_PREDISPOSITION_WEIGHTS.get(
        _normalize_species(species), 0.0
    )
    text_score = _backstory_score(backstory or "")
    # Clamp the RNG roll silently — defensive against misuse.
    roll = max(0.0, min(0.5, float(rng_roll)))

    raw = species_score + text_score + roll
    return max(PREDISPOSITION_FLOOR, min(PREDISPOSITION_CEILING, raw))


# ─────────────────────────────────────────────────────────────────────────────
# Play-time accumulation
# ─────────────────────────────────────────────────────────────────────────────

# Maximum play_time_seconds increment a single tick handler call may
# write. Sane upper bound on the per-tick interval (60s heartbeat) plus
# generous slack for clock skew / missed ticks. If the caller tries to
# add more than this, we cap and log a warning — strongly suggests a
# bug, but we don't want a runaway tick to instantly mature characters
# past the 50-hour gate.
MAX_PLAYTIME_INCREMENT_SECONDS: int = 600  # 10 minutes


async def accumulate_play_time(
    db,
    char_id: int,
    seconds: int,
) -> int:
    """Atomically increment ``characters.play_time_seconds`` for one PC.

    Called by ``server.tick_handlers_progression.playtime_heartbeat_tick``
    once per minute per active non-idle session. Pure DB-level
    increment — no idle filtering, no session lookup. The caller
    decides whether the character is currently playing and what the
    increment is.

    Args:
        db: a connected ``db.database.Database`` instance.
        char_id: the PC's character row id.
        seconds: increment to add. Typically 60 (one heartbeat). Negative
            values are rejected (raises ValueError); excessive values
            are capped to MAX_PLAYTIME_INCREMENT_SECONDS with a warning.

    Returns:
        The new total ``play_time_seconds`` for the character after the
        update, or -1 if the character was not found.
    """
    if seconds < 0:
        raise ValueError(
            f"accumulate_play_time: negative increment {seconds!r} rejected"
        )
    if seconds > MAX_PLAYTIME_INCREMENT_SECONDS:
        log.warning(
            "accumulate_play_time: increment %d capped to %d for char_id=%d",
            seconds, MAX_PLAYTIME_INCREMENT_SECONDS, char_id,
        )
        seconds = MAX_PLAYTIME_INCREMENT_SECONDS

    # The schema column was added in migration 18 (PG.1.schema). We
    # rely on it being present; if it isn't, this errors loudly which
    # is the correct behavior — running PG.3 against a v17 DB is a
    # configuration error.
    await db._db.execute(
        "UPDATE characters SET play_time_seconds = play_time_seconds + ? "
        "WHERE id = ?",
        (seconds, char_id),
    )
    await db._db.commit()

    rows = await db._db.execute_fetchall(
        "SELECT play_time_seconds FROM characters WHERE id = ?",
        (char_id,),
    )
    if not rows:
        return -1
    return int(rows[0]["play_time_seconds"])


# ─────────────────────────────────────────────────────────────────────────────
# Gate consultation helpers (read-only)
# ─────────────────────────────────────────────────────────────────────────────

# The 50-hour playtime gate threshold from the design. Centralized so
# PG.3.gates.b's Director refactor has a single number to consult.
# Adjustable via config in a future drop; for v1 this is the canonical
# value (50 hours = 180,000 seconds).
PLAY_TIME_GATE_SECONDS: int = 50 * 60 * 60  # 180,000


def is_force_gate_passed(char: Mapping) -> bool:
    """True iff this character has cleared the 50-hour play-time gate.

    Pure read of ``char['play_time_seconds']``. Returns False if the
    column is missing (defensive: a v17 DB against v18 code shouldn't
    silently behave as "gate passed").

    Used by PG.3.gates.b's Force-sign trigger refactor and by
    ``+sheet`` / Director digests that want to surface gate state.
    """
    val = char.get("play_time_seconds")
    if val is None:
        return False
    try:
        return int(val) >= PLAY_TIME_GATE_SECONDS
    except (TypeError, ValueError):
        return False


def force_gate_progress(char: Mapping) -> float:
    """Return a 0.0–1.0 fraction of the playtime gate completed.

    Useful for admin/debug surfaces and future Director consultation.
    Caps at 1.0 once gate is passed.
    """
    val = char.get("play_time_seconds")
    if val is None:
        return 0.0
    try:
        return min(1.0, max(0.0, int(val) / PLAY_TIME_GATE_SECONDS))
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Village quest cooldown helpers (PG.3.gates.b)
# ─────────────────────────────────────────────────────────────────────────────
#
# Per design §2.3 the Village quest has three real-time wall-clock
# cooldowns that must elapse for the next narrative step to unlock:
#
#   - 7 days between Act 1 (invitation accepted) and Act 2 (first
#     trial allowed). Roleplay buffer; the Hermit's invitation should
#     feel weighty, not transactional.
#
#   - 14 days between successful trials. The biggest behavioral lever
#     — turns the Village from a checklist into spiritual training
#     where each trial gets its own week of anticipation.
#
#   - 24 hours between Trial of Courage retries on failure. Failure
#     should be meaningful but recoverable.
#
# These helpers are pure read-only consultations against the schema
# columns landed in PG.1.schema. They return both a boolean (allowed
# / not allowed) AND the seconds remaining, so callers can render
# user-facing "wait N hours" messages without re-deriving the math.
#
# The Village quest engine (separate future drop) consumes these.
# This module just owns the math.

# Cooldown durations in seconds. Centralized so PG.4.polish can move
# them to era.yaml without touching call sites.
ACT_1_TO_ACT_2_COOLDOWN_SECONDS:    int = 7  * 24 * 60 * 60   # 604,800
INTER_TRIAL_COOLDOWN_SECONDS:       int = 14 * 24 * 60 * 60   # 1,209,600
TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS: int = 24 * 60 * 60      # 86,400


def _now() -> float:
    """Wall-clock time, factored out so tests can monkeypatch."""
    import time
    return time.time()


def act_2_unlock_seconds_remaining(
    char: Mapping,
    *,
    now: Optional[float] = None,
) -> float:
    """How long until this character may attempt the first Village trial?

    Reads ``village_act`` and ``village_act_unlocked_at``:

      - If ``village_act`` < 1, the character hasn't even been invited
        yet (Act 1 not complete). Returns +infinity to signal "not
        eligible yet by a different gate." Callers should check the
        Force-sign invitation state separately first.

      - If ``village_act`` >= 2, the cooldown is already cleared (or
        irrelevant — they're past Act 2 entry). Returns 0.0.

      - Otherwise: returns max(0, unlock_at - now) where
        unlock_at = village_act_unlocked_at + ACT_1_TO_ACT_2_COOLDOWN_SECONDS.

    Args:
        char: character dict.
        now: wall-clock override for testing.
    """
    act = int(char.get("village_act") or 0)
    if act < 1:
        return float("inf")
    if act >= 2:
        return 0.0
    unlocked_at = float(char.get("village_act_unlocked_at") or 0.0)
    if unlocked_at <= 0:
        # Defensive: Act 1 should always have set this. If it's
        # missing, treat as "cooldown already cleared" rather than
        # blocking the player due to bad data.
        return 0.0
    deadline = unlocked_at + ACT_1_TO_ACT_2_COOLDOWN_SECONDS
    current = now if now is not None else _now()
    return max(0.0, deadline - current)


def act_2_unlock_ready(char: Mapping, *, now: Optional[float] = None) -> bool:
    """True iff the 7-day Act 1→Act 2 cooldown has cleared.

    Convenience wrapper around ``act_2_unlock_seconds_remaining``.
    Returns False for characters who haven't been invited at all.
    """
    remaining = act_2_unlock_seconds_remaining(char, now=now)
    return remaining == 0.0


def trial_cooldown_seconds_remaining(
    char: Mapping,
    *,
    now: Optional[float] = None,
) -> float:
    """How long until the next Village trial may be attempted?

    The 14-day inter-trial cooldown reads
    ``village_trial_last_attempt`` and applies uniformly between any
    two trials.

    Returns 0.0 if no trial has been attempted yet (clean slate),
    or if the cooldown has already cleared.

    Args:
        char: character dict.
        now: wall-clock override for testing.
    """
    last = float(char.get("village_trial_last_attempt") or 0.0)
    if last <= 0:
        return 0.0
    deadline = last + INTER_TRIAL_COOLDOWN_SECONDS
    current = now if now is not None else _now()
    return max(0.0, deadline - current)


def trial_cooldown_ready(
    char: Mapping, *, now: Optional[float] = None,
) -> bool:
    """True iff the 14-day inter-trial cooldown has cleared."""
    return trial_cooldown_seconds_remaining(char, now=now) == 0.0


def courage_retry_cooldown_seconds_remaining(
    char: Mapping,
    *,
    now: Optional[float] = None,
) -> float:
    """How long until the Trial of Courage may be retried on failure?

    Per design §2.3 the Trial of Courage is the only trial with an
    explicit retry cooldown (24 hours). The other two trials follow
    the standard 14-day inter-trial cooldown.

    The trial-engine drop will record a failure timestamp distinct
    from the success timestamp; for now this helper is structurally
    in place for that engine to consume. The 14-day inter-trial
    cooldown still applies on top — this is a *minimum additional*
    cooldown for failed Courage attempts.

    Implementation note: until the trial engine ships, the design
    leaves the per-trial failure timestamp implicit. We use
    ``village_trial_last_attempt`` as the reference; once the trial
    engine adds a more granular schema (failure-specific timestamp),
    this helper should be updated to consult that instead.
    """
    last = float(char.get("village_trial_last_attempt") or 0.0)
    if last <= 0:
        return 0.0
    deadline = last + TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS
    current = now if now is not None else _now()
    return max(0.0, deadline - current)


def courage_retry_cooldown_ready(
    char: Mapping, *, now: Optional[float] = None,
) -> bool:
    """True iff the 24-hour Courage retry cooldown has cleared."""
    return courage_retry_cooldown_seconds_remaining(char, now=now) == 0.0


def format_remaining(seconds: float) -> str:
    """Render a remaining-cooldown duration as 'Xd Yh Zm'.

    Used for player-facing messages from Village dialogue. Designed
    to be terse but readable: '6d 23h 45m', '1h 12m', '5m', 'Now'.
    """
    if seconds <= 0:
        return "Now"
    if seconds == float("inf"):
        return "—"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m or not parts:
        parts.append(f"{m}m")
    return " ".join(parts)
