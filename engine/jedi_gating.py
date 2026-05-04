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

F.7.k (May 4 2026) — extension
------------------------------
Adds the cooldown-bypass seam (env var + era YAML flag) and exposes
``cooldowns_enabled()`` plus the policy-aware predicates
``act_2_gate_passed`` / ``trial_gate_passed`` / ``courage_retry_gate_passed``.

The existing ``*_ready`` / ``*_seconds_remaining`` helpers continue
to evaluate the strict math (so unit tests of the math stay valid).
Callers that want production-correct gating with a dev bypass should
use the new ``*_gate_passed`` predicates.

The bypass exists because pre-launch dev needs to walk the full
Village quest in one sitting; 7-day Act gates and 14-day inter-trial
cooldowns are correct for production but hostile for testing.

Resolution order for ``cooldowns_enabled()``:

  1. ``SW_MUSH_PROGRESSION_COOLDOWNS`` env var, if set:
       - "0" / "false" / "off" / "no" → cooldowns BYPASSED (returns False)
       - "1" / "true" / "on" / "yes"  → cooldowns ENFORCED (returns True)
       - anything else → fail-loud warning, fall through to YAML
  2. era.yaml ``policy.progression_cooldowns_enabled`` (bool), if
     era YAML loaded successfully and key is present.
  3. Default: True (strict — production behavior).

Tested by tests/test_f7k_cooldown_wireup.py.
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


# ═════════════════════════════════════════════════════════════════════════════
# F.7.k — Cooldown bypass policy + policy-aware gate predicates
# ═════════════════════════════════════════════════════════════════════════════
#
# The strict ``*_ready`` helpers above are pure math against schema
# columns. They never look at env vars or YAML; tests of the math can
# rely on them returning the same answer in every environment.
#
# Callers that want "should this player be gated right now?" should use
# the policy-aware ``*_gate_passed`` predicates below. Those consult
# ``cooldowns_enabled()``: if cooldowns are disabled (dev bypass),
# every gate predicate returns True. If enabled, they delegate to the
# strict ``*_ready`` math.
#
# This split lets dev/test environments short-circuit the 35+-day
# Village quest without compromising production correctness.

# Env var name. The single source of truth for the dev override.
COOLDOWN_BYPASS_ENV_VAR: str = "SW_MUSH_PROGRESSION_COOLDOWNS"

# Recognized truthy/falsy spellings for the env var. We accept the
# common conventions and fail loud on anything else.
_ENV_TRUTHY = frozenset({"1", "true", "on", "yes"})
_ENV_FALSY = frozenset({"0", "false", "off", "no"})


def _parse_env_override() -> Optional[bool]:
    """Read the env var. Returns True/False if set to a recognized
    value, None if unset, None with a warning if set to something
    weird."""
    import os
    raw = os.environ.get(COOLDOWN_BYPASS_ENV_VAR)
    if raw is None:
        return None
    norm = raw.strip().lower()
    if norm in _ENV_TRUTHY:
        return True
    if norm in _ENV_FALSY:
        return False
    log.warning(
        "[jedi_gating] %s=%r is not a recognized boolean "
        "(expected one of %s for True, %s for False); "
        "falling through to era.yaml.",
        COOLDOWN_BYPASS_ENV_VAR, raw,
        sorted(_ENV_TRUTHY), sorted(_ENV_FALSY),
    )
    return None


def _read_era_policy_flag() -> Optional[bool]:
    """Read ``policy.progression_cooldowns_enabled`` from the active
    era's era.yaml. Returns the bool if present, None otherwise.

    Best-effort: any failure to load era YAML returns None (callers
    fall through to the default). Logs at debug level so a missing
    era.yaml during tests doesn't spam warnings.
    """
    try:
        from engine.era_state import get_active_era
        era = get_active_era()
    except Exception:
        log.debug(
            "[jedi_gating] era_state import failed; "
            "no era YAML policy lookup.", exc_info=True,
        )
        return None

    try:
        from pathlib import Path
        import yaml
    except ImportError:
        log.debug(
            "[jedi_gating] pyyaml not available; "
            "no era YAML policy lookup.",
        )
        return None

    era_path = Path("data") / "worlds" / era / "era.yaml"
    if not era_path.is_file():
        log.debug(
            "[jedi_gating] %s not found; no era YAML policy lookup.",
            era_path,
        )
        return None

    try:
        with open(era_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        log.warning(
            "[jedi_gating] failed to parse %s; "
            "falling through to default cooldown policy.",
            era_path, exc_info=True,
        )
        return None

    policy = (data or {}).get("policy") or {}
    val = policy.get("progression_cooldowns_enabled")
    if val is None:
        return None
    if not isinstance(val, bool):
        log.warning(
            "[jedi_gating] %s::policy.progression_cooldowns_enabled "
            "is %r (expected bool); falling through to default.",
            era_path, val,
        )
        return None
    return val


def cooldowns_enabled() -> bool:
    """Are real-time progression cooldowns enforced right now?

    Resolution order:
      1. ``SW_MUSH_PROGRESSION_COOLDOWNS`` env var (recognized values)
      2. era.yaml ``policy.progression_cooldowns_enabled``
      3. Default: True (strict / production)

    The function is intentionally cheap to call — env var read is a
    dict lookup, era YAML is read once per call but tiny. If a hot
    path needs this and profiling shows it as a bottleneck, the
    obvious cache point is here, not at every caller.
    """
    env = _parse_env_override()
    if env is not None:
        return env

    yaml_flag = _read_era_policy_flag()
    if yaml_flag is not None:
        return yaml_flag

    return True


def act_2_gate_passed(
    char: Mapping, *, now: Optional[float] = None,
) -> bool:
    """Policy-aware predicate: may this PC enter Act 2?

    Honors ``cooldowns_enabled()``. When cooldowns are disabled,
    returns True iff the strict math would consider Act 2 *eligible*
    at all (i.e. ``village_act >= 1``) — we never bypass the
    structural "you must be invited first" requirement, only the
    7-day timer.
    """
    if not cooldowns_enabled():
        # Dev bypass: skip the timer but keep the structural gate.
        # ``act_2_unlock_seconds_remaining`` returns +inf when
        # village_act < 1; we mirror that here so a not-yet-invited
        # PC still can't slip into Act 2.
        return int(char.get("village_act") or 0) >= 1
    return act_2_unlock_ready(char, now=now)


def trial_gate_passed(
    char: Mapping, *, now: Optional[float] = None,
) -> bool:
    """Policy-aware predicate: may this PC attempt the next trial?

    Honors ``cooldowns_enabled()``. When cooldowns are disabled,
    always returns True (no structural gate beyond the trial's own
    per-step prerequisites, which trial code enforces separately).
    """
    if not cooldowns_enabled():
        return True
    return trial_cooldown_ready(char, now=now)


def courage_retry_gate_passed(
    char: Mapping, *, now: Optional[float] = None,
) -> bool:
    """Policy-aware predicate: may this PC retry the Courage trial
    after a failure?

    Honors ``cooldowns_enabled()``. When cooldowns are disabled,
    always returns True. NOTE: the per-Courage 24-hour lockout
    (``village_trial_courage_lockout_until``) is enforced separately
    in ``engine.village_trials`` and is independent of this gate.
    This gate is the (currently unused) inter-trial 24h floor; once
    the Courage trial engine writes ``village_trial_last_attempt`` on
    failure, this gate becomes meaningful.
    """
    if not cooldowns_enabled():
        return True
    return courage_retry_cooldown_ready(char, now=now)


# ═════════════════════════════════════════════════════════════════════════════
# F.7.k — Trial-attempt timestamp helper
# ═════════════════════════════════════════════════════════════════════════════
#
# The 14-day inter-trial cooldown reads ``village_trial_last_attempt``
# but the Village trial-completion paths historically didn't write it.
# This helper is the single canonical writer; trial code calls it at
# completion time with the existing ``save_kwargs`` accumulator.

def stamp_trial_attempt(
    char: dict, save_kwargs: dict, *, now: Optional[float] = None,
) -> float:
    """Stamp ``village_trial_last_attempt`` on the character.

    Mutates both ``char`` (in-memory state) and ``save_kwargs``
    (DB-write accumulator) — the caller is responsible for the
    actual ``db.save_character(**save_kwargs)`` call. Idempotent
    against being called twice in the same path; the new timestamp
    overwrites any earlier one (which is what we want — the most
    recent attempt is the one that gates the next trial).

    Args:
        char: character dict (mutated)
        save_kwargs: dict of pending DB column writes (mutated)
        now: wall-clock override for testing

    Returns:
        The timestamp written.
    """
    ts = now if now is not None else _now()
    char["village_trial_last_attempt"] = ts
    save_kwargs["village_trial_last_attempt"] = ts
    return ts
