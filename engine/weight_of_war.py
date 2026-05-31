# -*- coding: utf-8 -*-
"""
engine/weight_of_war.py — Weight of War substrate (Drop 1).

Per `weight_of_war_design_v1.md`. Cumulative war-strain metric for
Jedi PCs, distinct from Dark Side Points. Range [0, 200].

This module is the **substrate** layer. It exposes:

- Tier mapping and narrative-descriptor lookup (design §6).
- Accrual and decay primitives with the design §4.4 caps and the
  design §5 floors enforced.
- Mechanical modifiers for the willpower-resistance erosion and
  Force-Point award reduction (design §7.1 and §7.2). These are
  pure functions; the *consumers* (engine/skill_checks.py and
  engine/character.py) are not wired in this drop.
- Event-log read and admin-override write.

Drop 1 ships the contract. Drop 2 ships the player-facing surfaces
(`+meditate`, `+counsel`, `+retreat`, `look self`, admin command).
Drop 3 ships the runtime hooks (combat events, passive-decay tick
handler, DSP-resistance and FP-award modifier wiring).

Design references in this module's docstrings cite section numbers
in `weight_of_war_design_v1.md`.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Range invariants (design §4.4 + §6) ───────────────────────────────

WEIGHT_MIN: int = 0
WEIGHT_MAX: int = 200
"""Hard caps. ``set_weight()`` clamps to this range."""

MAX_SINGLE_EVENT: int = 25
"""Per design §4.4: 'No single event can accrue more than +25
Weight.' ``accrue_weight()`` clamps each individual delta to this
ceiling before applying."""

WEEKLY_ACCRUAL_CAP: int = 40
"""Per design §4.4: 'Weekly accrual cap: +40 Weight per in-game
week.' This drop interprets 'in-game week' as 7 wall-clock days,
since the codebase has no current in-game-week clock distinct
from wall-clock. If a campaign-time abstraction is introduced
post-launch, ``weekly_accrual_total`` is the seam to swap.
"""

WEEKLY_WINDOW_SECONDS: int = 7 * 24 * 60 * 60
"""Wall-clock seconds in the rolling window used for
``weekly_accrual_total``."""


# ── Passive decay (design §5.1, WoW.3b) ──────────────────────────────

PASSIVE_DECAY_INTERVAL_SECONDS: int = 7 * 24 * 60 * 60
"""Passive decay fires when the last Weight event (accrual or
decay) was at least this many seconds ago. Per design §5.1: '-1
Weight per in-game day spent... no active missions' — the May 23
handoff scope reading simplifies this to -1 per 7 real-time days
of no events. When zone-tagging for peaceful/campaign rooms
ships post-launch, this constant becomes the floor and a
zone-aware variant applies the design's per-zone rates."""

PASSIVE_DECAY_AMOUNT: int = 1
"""Amount to decay per passive tick. Subject to the same floor
clamp as any other decay (cannot go below WEIGHT_MIN)."""

PASSIVE_DECAY_TRIGGER_TYPE: str = "passive_decay"
"""Trigger-type label written to the weight_of_war_events log
when passive decay fires. Distinct from 'retreat', 'meditate',
'counsel', 'admin_adjust', 'combat_kill' so post-launch
+history weight can group passive-decay events together."""


# ── Tier mapping (design §6) ──────────────────────────────────────────
#
# Each tuple is (low_inclusive, high_inclusive, tier_name, descriptor).
# Tiers must contiguously cover [0, WEIGHT_MAX]; the highest tier's
# upper bound equals WEIGHT_MAX. Order matters — ``get_tier`` /
# ``get_descriptor`` linear-scan in this order and return the first
# tier whose range contains the value.
#
# Descriptors are quoted verbatim from design §6's narrative-descriptor
# table.

_WeightTier = tuple[int, int, str, str]

WEIGHT_TIERS: tuple[_WeightTier, ...] = (
    (
        0, 20, "at_peace",
        "You feel the Force flowing freely around you.",
    ),
    (
        21, 50, "troubled",
        "The Force feels clouded. Small noises startle you. You "
        "sleep poorly.",
    ),
    (
        51, 100, "burdened",
        "You hesitate before drawing your saber. Every clone's "
        "face becomes familiar, and you cannot remember all "
        "their names.",
    ),
    (
        101, 150, "strained",
        "The voices in the Force grow dim. Meditation no longer "
        "calms you. You dream of fire and dying men you could "
        "not save.",
    ),
    (
        151, 200, "crushed",
        "The Force feels distant, withheld. You feel hollow. The "
        "Code is words you recite, not truths you feel. You "
        "understand, now, why Masters have fallen.",
    ),
)


def get_tier(weight: int) -> str:
    """Return the tier name for *weight*.

    Values outside [WEIGHT_MIN, WEIGHT_MAX] are clamped before
    lookup — callers may pass an unclamped value safely.
    """
    w = _clamp(weight)
    for low, high, name, _desc in WEIGHT_TIERS:
        if low <= w <= high:
            return name
    # Unreachable if WEIGHT_TIERS contiguously covers [0, WEIGHT_MAX].
    log.warning("get_tier: no tier matched for weight=%s (clamped=%s)",
                weight, w)
    return WEIGHT_TIERS[0][2]


def get_descriptor(weight: int) -> str:
    """Return the narrative descriptor for *weight* per design §6."""
    w = _clamp(weight)
    for low, high, _name, desc in WEIGHT_TIERS:
        if low <= w <= high:
            return desc
    log.warning("get_descriptor: no tier matched for weight=%s "
                "(clamped=%s)", weight, w)
    return WEIGHT_TIERS[0][3]


# ── Mechanical modifiers (design §7.1 + §7.2) ────────────────────────

def dsp_resistance_modifier(weight: int) -> int:
    """Per design §7.1: willpower-difficulty modifier when resisting a
    dark-side temptation.

    Returns an additive integer to the difficulty target:
      - Weight   0–50:  0  (no modifier)
      - Weight  51–100: +2
      - Weight 101–150: +5
      - Weight 151–200: +10

    Design §7.1 also says: 'a failed willpower roll grants 1 extra
    DSP beyond the baseline DSP award' for Weight 151–200. That
    'extra DSP' rule is *not* part of the difficulty modifier —
    callers needing it should consult ``extra_dsp_on_failed_resist``
    below.
    """
    w = _clamp(weight)
    if w <= 50:
        return 0
    if w <= 100:
        return 2
    if w <= 150:
        return 5
    return 10


def extra_dsp_on_failed_resist(weight: int) -> int:
    """Per design §7.1: '… additionally, a failed willpower roll
    grants 1 extra DSP beyond the baseline DSP award' at Weight
    151–200. Returns the number of extra DSP to award on top of
    the standard penalty (0 or 1)."""
    return 1 if _clamp(weight) >= 151 else 0


def fp_award_multiplier(weight: int) -> float:
    """Per design §7.2: Force-Point award reduction by tier.

    Returns a multiplier in (0, 1]:
      - Weight   0–50: 1.00
      - Weight  51–100: 0.75
      - Weight 101–150: 0.50
      - Weight 151–200: 0.25

    Design §7.2 specifies 'round down, minimum 1' for the resulting
    award. Callers should compute ``max(1, int(award * multiplier))``
    to honor the floor.
    """
    w = _clamp(weight)
    if w <= 50:
        return 1.0
    if w <= 100:
        return 0.75
    if w <= 150:
        return 0.50
    return 0.25


def fp_award_after_weight(base_award: int, weight: int) -> int:
    """Convenience helper combining ``fp_award_multiplier`` with the
    design §7.2 floor ('round down, minimum 1').

    A zero-or-negative ``base_award`` is returned unchanged — the
    floor applies only when the multiplier would have produced 0 from
    a positive base.
    """
    if base_award <= 0:
        return base_award
    return max(1, int(base_award * fp_award_multiplier(weight)))


# ── Char-dict reads ───────────────────────────────────────────────────

def get_weight(char: dict) -> int:
    """Read Weight of War from a character dict.

    Returns 0 if the column is missing or NULL (defensive — the
    migration sets ``DEFAULT 0`` so this should be the common
    case for any character predating Drop 1).
    """
    if not isinstance(char, dict):
        return 0
    raw = char.get("weight_of_war")
    if raw is None:
        return 0
    try:
        return _clamp(int(raw))
    except (TypeError, ValueError):
        log.warning("get_weight: non-integer weight_of_war %r for "
                    "char %r", raw, char.get("id"))
        return 0


def get_tier_for_char(char: dict) -> str:
    """Convenience: ``get_tier(get_weight(char))``."""
    return get_tier(get_weight(char))


def get_descriptor_for_char(char: dict) -> str:
    """Convenience: ``get_descriptor(get_weight(char))``."""
    return get_descriptor(get_weight(char))


# ── DB reads ──────────────────────────────────────────────────────────

async def get_weight_db(db, char_id: int) -> int:
    """Read Weight of War from the DB for *char_id*.

    Returns 0 if the character does not exist (defensive — callers
    should not normally pass missing ids, but the engine prefers
    'no DSP-equivalent for a deleted char' over a hard raise).
    """
    row = await db.fetchone(
        "SELECT weight_of_war FROM characters WHERE id = ?",
        (char_id,),
    )
    if row is None:
        return 0
    raw = row["weight_of_war"]
    if raw is None:
        return 0
    return _clamp(int(raw))


async def last_event_at(db, char_id: int) -> Optional[float]:
    """Return the Unix timestamp of the most recent Weight event
    for *char_id* — accrual or decay, whichever is later. Returns
    None if no events have ever fired (or if the character does
    not exist).

    Reads both ``weight_last_accrual_at`` and
    ``weight_last_decay_at`` and returns ``max(...)``, treating
    NULLs as missing rather than zero. This is the single
    timestamp passive-decay logic should consult when deciding
    "has anything happened to this character recently?" — both
    accrual and decay reset the "no-event" clock, since the
    design says decay pauses if you're either accruing or
    already-decaying.

    Added WoW.3b (May 24 2026) to support the passive-decay
    tick in ``server.tick_handlers_progression``. Listed on the
    module surface in architecture v48 §10.4 once consolidated.
    """
    row = await db.fetchone(
        "SELECT weight_last_accrual_at, weight_last_decay_at "
        "FROM characters WHERE id = ?",
        (char_id,),
    )
    if row is None:
        return None
    a = row["weight_last_accrual_at"]
    d = row["weight_last_decay_at"]
    candidates: list[float] = []
    for v in (a, d):
        if v is None:
            continue
        try:
            candidates.append(float(v))
        except (TypeError, ValueError):
            continue
    if not candidates:
        return None
    return max(candidates)


async def get_events(
    db,
    char_id: int,
    limit: int = 20,
) -> list[dict]:
    """Return the most recent ``weight_of_war_events`` for *char_id*,
    newest first.

    The Director AI integration in Drop 3 (design §9) uses this for
    prompt context ('the Massacre at Ryloth still haunts you').
    """
    rows = await db.fetchall(
        "SELECT id, event_at, delta, trigger_type, description "
        "FROM weight_of_war_events "
        "WHERE char_id = ? "
        "ORDER BY event_at DESC "
        "LIMIT ?",
        (char_id, int(limit)),
    )
    return [dict(r) for r in rows]


async def weekly_accrual_total(
    db,
    char_id: int,
    now: Optional[float] = None,
) -> int:
    """Sum of positive deltas in the last ``WEEKLY_WINDOW_SECONDS``,
    *excluding* admin overrides.

    Used by ``accrue_weight`` to enforce the design §4.4 cap of +40
    per in-game week. Admin overrides (``trigger_type='admin_adjust'``)
    are by-design out-of-band staff actions per design §14 and do
    not consume the player-protection weekly headroom.
    """
    if now is None:
        now = time.time()
    window_start = now - WEEKLY_WINDOW_SECONDS
    row = await db.fetchone(
        "SELECT COALESCE(SUM(delta), 0) AS total "
        "FROM weight_of_war_events "
        "WHERE char_id = ? "
        "  AND event_at >= ? "
        "  AND delta > 0 "
        "  AND trigger_type != 'admin_adjust'",
        (char_id, window_start),
    )
    if row is None:
        return 0
    return int(row["total"] or 0)


# ── Writes ────────────────────────────────────────────────────────────

async def accrue_weight(
    db,
    char_id: int,
    delta: int,
    trigger_type: str,
    description: Optional[str] = None,
    now: Optional[float] = None,
) -> int:
    """Apply an accrual to *char_id* with design caps honored.

    *delta* must be a positive integer. The caller's *delta* is
    clamped to ``MAX_SINGLE_EVENT`` (design §4.4). The weekly cap
    is then consulted: if applying the (possibly-clamped) delta
    would exceed ``WEEKLY_ACCRUAL_CAP`` for this character within
    ``WEEKLY_WINDOW_SECONDS``, the delta is further reduced. If the
    weekly cap is already met, the call is a no-op (no event is
    logged — design §4.4: 'additional triggers are narratively
    acknowledged by Director AI but do not add to the numeric
    score').

    Returns the *actual* delta applied (0 if no-op, positive
    otherwise). The character's new total can be read via
    ``get_weight_db`` after the call.

    Raises ValueError if *delta* is not positive.
    """
    if delta <= 0:
        raise ValueError(
            f"accrue_weight: delta must be positive, got {delta}. "
            "Use decay_weight for negative deltas, or "
            "set_weight_admin for arbitrary overrides."
        )

    # §4.4 single-event clamp.
    clamped = min(int(delta), MAX_SINGLE_EVENT)

    # §4.4 weekly cap.
    if now is None:
        now = time.time()
    already = await weekly_accrual_total(db, char_id, now=now)
    headroom = WEEKLY_ACCRUAL_CAP - already
    if headroom <= 0:
        log.info("accrue_weight: weekly cap reached for char_id=%s "
                 "(already=%d), suppressing trigger %s (+%d) — "
                 "Director AI may still acknowledge narratively.",
                 char_id, already, trigger_type, clamped)
        return 0
    applied = min(clamped, headroom)

    # §4.4 hard cap [0, 200]. Reuse the same fetch for the post-
    # write log line.
    current = await get_weight_db(db, char_id)
    new_total = _clamp(current + applied)
    actual = new_total - current
    if actual <= 0:
        log.info("accrue_weight: char_id=%s already at WEIGHT_MAX "
                 "(%d), suppressing trigger %s (+%d).",
                 char_id, current, trigger_type, applied)
        return 0

    await db.execute(
        "UPDATE characters SET weight_of_war = ?, "
        "weight_last_accrual_at = ? WHERE id = ?",
        (new_total, now, char_id),
    )
    await db.execute(
        "INSERT INTO weight_of_war_events "
        "(char_id, event_at, delta, trigger_type, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (char_id, now, actual, trigger_type, description),
    )
    log.info("Weight of War: char_id=%s +%d (trigger=%s) → %d",
             char_id, actual, trigger_type, new_total)
    return actual


async def decay_weight(
    db,
    char_id: int,
    delta: int,
    trigger_type: str,
    description: Optional[str] = None,
    now: Optional[float] = None,
) -> int:
    """Apply a decay to *char_id*.

    *delta* must be a positive integer (the magnitude of decay).
    The decay is clamped so weight cannot go below ``WEIGHT_MIN``;
    if already at the floor, the call is a no-op (no event logged).

    Returns the *actual* magnitude decayed (0 if no-op, positive
    otherwise). The event is logged with a *negative* delta in the
    event table so the log clearly distinguishes accrual from
    decay.

    Raises ValueError if *delta* is not positive.
    """
    if delta <= 0:
        raise ValueError(
            f"decay_weight: delta magnitude must be positive, got "
            f"{delta}. Use accrue_weight for positive deltas, or "
            "set_weight_admin for arbitrary overrides."
        )

    current = await get_weight_db(db, char_id)
    new_total = _clamp(current - int(delta))
    actual = current - new_total
    if actual <= 0:
        log.debug("decay_weight: char_id=%s already at WEIGHT_MIN, "
                  "suppressing trigger %s (-%d).",
                  char_id, trigger_type, delta)
        return 0

    if now is None:
        now = time.time()
    await db.execute(
        "UPDATE characters SET weight_of_war = ?, "
        "weight_last_decay_at = ? WHERE id = ?",
        (new_total, now, char_id),
    )
    await db.execute(
        "INSERT INTO weight_of_war_events "
        "(char_id, event_at, delta, trigger_type, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (char_id, now, -actual, trigger_type, description),
    )
    log.info("Weight of War: char_id=%s -%d (trigger=%s) → %d",
             char_id, actual, trigger_type, new_total)
    return actual


async def set_weight_admin(
    db,
    char_id: int,
    new_value: int,
    admin_note: str,
    now: Optional[float] = None,
) -> int:
    """Admin override per design §14 ('Staff can manually adjust
    Weight for narrative purposes').

    Bypasses single-event and weekly caps but is still clamped to
    [WEIGHT_MIN, WEIGHT_MAX] and still writes to the event log
    (trigger_type='admin_adjust') for audit. *admin_note* is the
    required reason text logged alongside.

    Returns the value actually written (i.e. *new_value* clamped
    to the range). If the change is a no-op (already at the
    requested value), no event is logged.
    """
    if not admin_note or not admin_note.strip():
        raise ValueError(
            "set_weight_admin: admin_note is required for the "
            "audit log; pass a non-empty reason."
        )

    target = _clamp(int(new_value))
    current = await get_weight_db(db, char_id)
    if target == current:
        log.info("set_weight_admin: char_id=%s already at %d, "
                 "no-op (note=%r).", char_id, target, admin_note)
        return target

    if now is None:
        now = time.time()
    delta = target - current

    # Use the appropriate timestamp column based on direction of
    # the override — keeps the bookkeeping fields meaningful even
    # for admin actions.
    if delta > 0:
        await db.execute(
            "UPDATE characters SET weight_of_war = ?, "
            "weight_last_accrual_at = ? WHERE id = ?",
            (target, now, char_id),
        )
    else:
        await db.execute(
            "UPDATE characters SET weight_of_war = ?, "
            "weight_last_decay_at = ? WHERE id = ?",
            (target, now, char_id),
        )
    await db.execute(
        "INSERT INTO weight_of_war_events "
        "(char_id, event_at, delta, trigger_type, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (char_id, now, delta, "admin_adjust", admin_note),
    )
    log.info("Weight of War: char_id=%s admin override → %d "
             "(delta=%+d, note=%r).",
             char_id, target, delta, admin_note)
    return target


# ── WoW.3b: passive decay tick (design §5.1, May 24 2026) ─────────────
#
# Per architecture v45 §4.5 (seam discipline): the actual work
# lives here in engine/. The tick handler in
# server/tick_handlers_progression is just the scheduler-side
# plumbing. Same pattern as engine.death.run_decay_tick.

async def run_passive_decay_tick(
    db,
    *,
    now: Optional[float] = None,
    is_in_retreat_attr_key: str = "wow_retreat_active",
) -> dict:
    """Apply passive Weight decay to all eligible Jedi PCs.

    Eligible = a character with:
      - ``weight_of_war > 0`` (nothing to decay at floor),
      - is a Jedi PC by the standard predicate (membership in
        the jedi_order faction OR the jedi_path_unlocked
        chargen flag),
      - has NOT had any Weight event (accrual or decay) in the
        last ``PASSIVE_DECAY_INTERVAL_SECONDS`` (default 7 days),
        OR has never had any Weight event,
      - is NOT currently in WoW retreat (the +return path applies
        retreat decay at a separate cap; double-dipping would be
        wrong per design §5.2's "-2 Weight per day of retreat
        with a cap of -30 per retreat").

    For each eligible character, applies -1 Weight via the
    standard ``decay_weight`` substrate. The event is logged
    with trigger_type='passive_decay' for grouping.

    Returns a summary dict with keys: ``scanned`` (total Jedi
    PCs considered), ``decayed`` (count actually decayed),
    ``skipped_recent`` (count skipped because a recent event
    existed), ``skipped_retreat`` (count skipped because in
    retreat), ``skipped_floor`` (count skipped because at
    WEIGHT_MIN — should be 0 given the SQL filter, but logged
    for safety). Failure-tolerant per-character: a failure on
    one character logs and continues.

    Cadence reminder: this is designed to be called HOURLY (the
    7-day eligibility check means hourly granularity is plenty
    of resolution; once-per-day would also work). Hourly was
    chosen for restart-tolerance: a server restart on day-7
    won't miss anyone's decay by more than an hour.
    """
    import json
    if now is None:
        now = time.time()
    cutoff = now - PASSIVE_DECAY_INTERVAL_SECONDS

    summary = {
        "scanned": 0, "decayed": 0,
        "skipped_recent": 0, "skipped_retreat": 0,
        "skipped_floor": 0, "errors": 0,
    }

    # Single query for all Jedi PCs with weight > 0. We grab the
    # union of faction='jedi_order' and chargen_notes containing
    # jedi_path_unlocked. The chargen_notes filter is a LIKE on
    # the JSON blob — the proper predicate is is_jedi_pc, but
    # we pre-filter at the SQL layer so we don't scan all
    # characters.
    rows = await db.fetchall(
        "SELECT id, name, weight_of_war, "
        "weight_last_accrual_at, weight_last_decay_at, "
        "attributes, faction_id, chargen_notes "
        "FROM characters "
        "WHERE weight_of_war > ? "
        "AND (faction_id = ? OR chargen_notes LIKE ?)",
        (WEIGHT_MIN, "jedi_order", "%jedi_path_unlocked%"),
    )

    for raw_row in rows:
        row = dict(raw_row)
        summary["scanned"] += 1
        char_id = row.get("id")
        if char_id is None:
            continue

        # Predicate check — the LIKE filter above can yield
        # false positives if some other field happens to
        # mention 'jedi_path_unlocked'. is_jedi_pc on the row
        # is the authoritative check.
        if not is_jedi_pc(row):
            continue

        # Recent-event check. The "no event in 7+ days" criterion
        # respects both accrual and decay timestamps — any
        # recent activity defers passive decay.
        a = row.get("weight_last_accrual_at")
        d = row.get("weight_last_decay_at")
        candidates = []
        for v in (a, d):
            if v is None:
                continue
            try:
                candidates.append(float(v))
            except (TypeError, ValueError):
                continue
        if candidates and max(candidates) > cutoff:
            summary["skipped_recent"] += 1
            continue

        # Retreat check — passive decay shouldn't double-dip with
        # the +return retreat decay path. The retreat flag lives
        # in attributes JSON.
        attrs_raw = row.get("attributes") or "{}"
        try:
            if isinstance(attrs_raw, str):
                attrs = json.loads(attrs_raw)
            elif isinstance(attrs_raw, dict):
                attrs = attrs_raw
            else:
                attrs = {}
        except (json.JSONDecodeError, TypeError, ValueError):
            attrs = {}
        if isinstance(attrs, dict) and attrs.get(
            is_in_retreat_attr_key,
        ):
            summary["skipped_retreat"] += 1
            continue

        # Apply decay. The substrate clamps at WEIGHT_MIN, so
        # passing 1 on a character at 1 lands at 0 (and is
        # counted in `decayed`). A character at 0 won't reach
        # this code since they're filtered out at the SQL level.
        try:
            actual = await decay_weight(
                db,
                char_id=int(char_id),
                delta=PASSIVE_DECAY_AMOUNT,
                trigger_type=PASSIVE_DECAY_TRIGGER_TYPE,
                description=(
                    f"Passive decay after "
                    f"{int(PASSIVE_DECAY_INTERVAL_SECONDS / 86400)} "
                    f"days of no Weight events."
                ),
                now=now,
            )
            if actual > 0:
                summary["decayed"] += 1
            else:
                # Race: someone modified weight between the SQL
                # SELECT and the decay write, leaving us at floor.
                summary["skipped_floor"] += 1
        except Exception:
            summary["errors"] += 1
            log.warning(
                "run_passive_decay_tick: decay failed for "
                "char_id=%s", char_id, exc_info=True,
            )

    if summary["decayed"] or summary["errors"]:
        log.info(
            "[wow_passive_decay] scanned=%d decayed=%d "
            "skipped_recent=%d skipped_retreat=%d "
            "skipped_floor=%d errors=%d",
            summary["scanned"], summary["decayed"],
            summary["skipped_recent"], summary["skipped_retreat"],
            summary["skipped_floor"], summary["errors"],
        )
    return summary


# ── Drop 2a: Jedi-PC gating ────────────────────────────────────────────
#
# Per design §3: "Weight of War applies only to Jedi PCs." This
# predicate centralizes the membership check so player-facing
# surfaces (look self, +meditate, +counsel, +retreat) and admin
# surfaces (@weight) all agree on who is a Jedi.
#
# Two paths into "Jedi" status:
#   1. `faction_id == 'jedi_order'` — formal CW-era Order membership
#      (joined via village quest Path A, or staff-set).
#   2. `chargen_notes.jedi_path_unlocked == True` — the village quest
#      unlocked the Jedi tutorial chain (Path A OR Path B). Path B
#      Jedi are independent-faction Force-sensitives who walked away
#      from the Order; design §3 doesn't draw a line between them
#      and Order Jedi for Weight purposes, since both are "Jedi" in
#      the design-§1 sense ("the Anakin trajectory, mechanically
#      modeled").
#
# A character matching either path is "Jedi" for Weight purposes.
# Bounty hunters, soldiers, and smugglers (`faction_id == 'bh_guild'`
# / `republic_army` / `independent` without `jedi_path_unlocked`)
# are not.
#
# Design call (locked here): a fallen Jedi who has been removed from
# the Order (`faction_id` changed away from `jedi_order`) but still
# carries `jedi_path_unlocked == True` is still considered Jedi for
# Weight purposes. They earned the burden; they don't get to shed it
# by leaving the Order. This is consistent with the Anakin model the
# design is built around.

def is_jedi_pc(char: dict) -> bool:
    """Return True iff *char* is a Jedi PC for Weight-of-War purposes.

    Defensive — returns False if *char* is not a dict, or lacks both
    the faction membership and the chargen flag. This is the
    canonical predicate; surfaces should not invent their own.
    """
    if not isinstance(char, dict):
        return False
    if char.get("faction_id") == "jedi_order":
        return True
    # Late import to avoid a hard cycle with engine/village_choice
    # (which itself imports from a handful of engine modules).
    try:
        from engine.village_choice import has_chargen_flag
    except ImportError:
        log.warning(
            "is_jedi_pc: engine.village_choice import failed; "
            "falling back to faction-only check.",
        )
        return False
    return has_chargen_flag(char, "jedi_path_unlocked")


# ── Internal helpers ──────────────────────────────────────────────────

def _clamp(value: int) -> int:
    """Clamp *value* to [WEIGHT_MIN, WEIGHT_MAX]."""
    if value < WEIGHT_MIN:
        return WEIGHT_MIN
    if value > WEIGHT_MAX:
        return WEIGHT_MAX
    return value
