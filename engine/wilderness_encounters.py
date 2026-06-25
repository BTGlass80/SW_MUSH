# -*- coding: utf-8 -*-
"""
engine/wilderness_encounters.py — Wilderness encounter selection.

Per ``wilderness_system_design_v1.md`` §5 (Encounters) and
``TODO.json`` item T2.WENC.

This module is the **selector** for wilderness encounters: on each
successful in-tile move, the caller (``parser/builtin_commands.py``
``_execute_wilderness_move``) invokes :func:`roll_encounter` with
the loaded region, destination terrain, and the moving character.
The function:

  1. Honours the per-character 60-second cooldown (design §5.4).
  2. Rolls against the region's ``encounter_chance_per_move``
     (default 4%).
  3. Filters the region's encounter pool by destination terrain,
     ``min_distance_from_edge``, and ``faction_gate``.
  4. Weighted-random-selects from the filtered set.
  5. Records the cooldown and returns the chosen entry.

This drop is the **minimal-substrate** ship for T2.WENC: the
selector + cooldown + region/terrain filters + a faction_gate
hook with always-True default. Actual encounter *firing* is the
caller's job: this module returns the chosen pool entry; the
caller broadcasts the encounter line and (in a follow-up drop)
spawns NPCs / vendors / weather effects. Same minimal-substrate-
first discipline the wilderness regions themselves shipped under.

The cooldown is a transient in-memory dict per design §5.4 (NOT
a DB field). Server restart resets all cooldowns; that's fine —
encounter pacing is a per-session UX concern, not a persistent
mechanic.

T2.WENC follow-ups (not in this drop):
  - NPC spawn integration for ``hostile`` / ``non_hostile`` types
  - Vendor caravan integration for ``trader_caravan``
  - Anomaly salvage flow for ``anomaly``
  - Weather effect application for ``weather``
  - Director-AI faction influence wired into ``faction_gate``
    (currently inert — gate condition strings are stored and
    surfaced for design inspection but always evaluate to True).
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

log = logging.getLogger(__name__)


# Per-character encounter cooldown timestamps: {char_id: last_fired_ts}
# Per design §5.4 — in-memory, transient. Reset on server restart.
_encounter_cooldowns: dict[int, float] = {}

# Default per-character cooldown in seconds (design §5.4).
ENCOUNTER_COOLDOWN_SECONDS = 60

# Default base chance per move if region doesn't override (design §5.1).
DEFAULT_BASE_CHANCE_PER_MOVE = 0.04

# Allowed encounter types per design §5.2. Strict whitelist: unknown
# types are dropped at load time with a warning.
ALLOWED_ENCOUNTER_TYPES = (
    "hostile",
    "non_hostile",
    "trader_caravan",
    "anomaly",
    "weather",
)


@dataclass
class EncounterEntry:
    """One entry in a region's encounter pool.

    Loaded from the region YAML's ``encounters.pool[]`` block by
    :func:`engine.wilderness_loader._parse_encounter_pool`. This
    dataclass is the runtime shape; YAML schema is documented in
    ``wilderness_system_design_v1.md`` §5.
    """

    id: str
    type: str                                  # one of ALLOWED_ENCOUNTER_TYPES
    weight: int = 1                            # weighted-random weight
    terrains: list = field(default_factory=list)  # empty = all terrains
    min_distance_from_edge: int = 0
    faction_gate: str = ""                     # design §5.3 — name only for now
    event_gate: str = ""                       # Lane D: world-event gate (e.g. "flood");
                                               # entry only eligible while that event is
                                               # active in the region's zone. Zone-aware
                                               # (unlike the global storm get_effect path).
    # DIFF.3 (2026-06-13): threat-band eligibility. The entry is eligible
    # only when the destination tile's threat-band RATING (1=Frontier ..
    # 4=Deep Wilds, from engine.threat_band) falls in [min_band, max_band].
    # Defaults (1, 4) = eligible in every band — so an un-banded pool is
    # unchanged. A Frontier tile (rating 1) draws only min_band==1 entries
    # (trivial fauna / low thugs); a Deep Wilds tile (rating 4) unlocks the
    # min_band>=3 minibosses gated out everywhere else. Per
    # difficulty_tiers_design_v1.md §6.
    min_band: int = 1
    max_band: int = 4
    narrative: str = ""                        # player-facing line on fire
    # Forward-compat metadata: spawn refs, item drops, weather config.
    # The selector doesn't read these — they're consumed by follow-up
    # firing drops. Store as opaque dict so the schema can grow without
    # touching this dataclass.
    payload: dict = field(default_factory=dict)


@dataclass
class EncounterPool:
    """Region-level encounter configuration.

    ``base_chance_per_move`` is the percentage roll on each move.
    ``entries`` is the full pool; the selector filters this list per
    destination tile and weighted-picks from what remains.

    A region without an ``encounters:`` block produces an EncounterPool
    with ``base_chance_per_move=0.0`` and an empty ``entries`` list.
    That makes :func:`roll_encounter` a no-op for that region without
    a special case at the call site.
    """

    base_chance_per_move: float = 0.0
    entries: list = field(default_factory=list)


@dataclass
class EncounterRollResult:
    """Result of :func:`roll_encounter`.

    Returned for **every** call so the caller can log what happened
    even when nothing fires. The ``fired`` boolean is the simple
    branch the caller acts on.
    """

    fired: bool
    entry: Optional[EncounterEntry] = None
    reason: str = ""               # debug/diagnostic — why fired or didn't


def evaluate_faction_gate(gate: str, char, db=None) -> bool:
    """Stub for design §5.3 faction gating.

    For T2.WENC this is **always True** (gate strings are stored and
    surfaced for inspection but don't filter). Director-AI faction
    influence wiring lands in a follow-up; the seam exists here so
    the selector path doesn't change when that wiring arrives.

    Per the seam-vs-integration discipline (arch §4.5): the contract
    is shipped (gate string parsed and threaded into the selector),
    the consumer (Director-AI influence) lands later, and this
    stub fails-loud-on-True so behavior change is visible the
    instant the real evaluator replaces this.
    """
    return True


def evaluate_event_gate(gate: str, region) -> bool:
    """Lane D: gate an encounter on an active world event in the region's zone.

    Unlike the storms' mechanical effects (consumed via the GLOBAL
    ``get_effect`` path — the coarse-zone tech-debt), this check is
    ZONE-AWARE: the encounter is eligible only when a world event whose
    ``event_type`` matches ``gate`` is active AND affects this region's
    zone (its ``zones_affected`` contains the region's zone, or is global).

    Empty gate → always eligible (the common case). Any failure resolving
    the manager / region zone fails CLOSED (encounter not eligible) so a
    flood-only encounter never leaks into normal play.
    """
    if not gate:
        return True
    try:
        from engine.world_events import get_world_event_manager
        zone = getattr(region, "zone", None)
        for ev in get_world_event_manager().active_events:
            if ev.event_type.value != gate:
                continue
            zones = getattr(ev, "zones_affected", None) or []
            if not zones or zone in zones:
                return True
    except Exception:
        return False
    return False


def _filter_pool(
    entries: Sequence[EncounterEntry],
    *,
    terrain: str,
    distance_from_edge: int,
    char,
    db=None,
    region=None,
    tile_band_rating: int = 2,
) -> list:
    """Filter the encounter pool by per-tile criteria.

    Per design §5.1 + DIFF.3:
      1. terrain match (empty terrains list = applies to all terrains)
      2. min_distance_from_edge satisfied
      3. faction_gate evaluates True
      4. event_gate evaluates True
      5. threat-band eligibility: the tile's band rating
         (1=Frontier .. 4=Deep Wilds) falls in [min_band, max_band].

    ``tile_band_rating`` defaults to 2 (Settled) so a caller that doesn't
    resolve the band still gets sane mid-tier behavior.
    """
    out = []
    for e in entries:
        # Terrain filter — empty list means "any terrain"
        if e.terrains and terrain not in e.terrains:
            continue
        # Distance-from-edge filter
        if distance_from_edge < e.min_distance_from_edge:
            continue
        # DIFF.3 threat-band eligibility: a too-hot entry is gated out of
        # a low-band tile (no miniboss in Frontier) and a trivial entry
        # capped below the tile's band is gated out of a high-band tile.
        if not (e.min_band <= tile_band_rating <= e.max_band):
            continue
        # Faction gate (currently stub-True)
        if e.faction_gate and not evaluate_faction_gate(e.faction_gate, char, db=db):
            continue
        # Event gate (Lane D) — zone-aware: a flood-only entry is eligible
        # only while its gating world event is active in this region's zone.
        if e.event_gate and not evaluate_event_gate(e.event_gate, region):
            continue
        out.append(e)
    return out


def _distance_from_edge(region, x: int, y: int) -> int:
    """Minimum Manhattan-to-boundary distance.

    Distance from (x, y) to the nearest edge of the region's grid.
    A tile at (0, *) or (*, 0) has distance 0; a tile at the center
    of a 40x40 grid has distance ~19.
    """
    w = getattr(region, "grid_width", 0) or 0
    h = getattr(region, "grid_height", 0) or 0
    return min(x, y, max(0, w - 1 - x), max(0, h - 1 - y))


def _is_on_cooldown(char_id: int, now: Optional[float] = None) -> bool:
    """True iff this character fired an encounter inside the cooldown window."""
    if char_id is None or char_id <= 0:
        return False
    now = now if now is not None else time.time()
    last = _encounter_cooldowns.get(char_id, 0.0)
    return (now - last) < ENCOUNTER_COOLDOWN_SECONDS


def _mark_cooldown(char_id: int, now: Optional[float] = None) -> None:
    """Record the moment an encounter fired for this character."""
    if char_id is None or char_id <= 0:
        return
    _encounter_cooldowns[char_id] = now if now is not None else time.time()


def clear_cooldowns() -> None:
    """Test/admin helper: wipe all in-memory cooldown timers."""
    _encounter_cooldowns.clear()


# ── Animal excluder (Gundark Drop E, 2026-06-11) ────────────────────────
# Merr-Sonn Animal Excluder (extraction §4.4): an ultrasonic deterrent
# field. Modeled as a post-pick AVERSION — when a creature-templated
# encounter is chosen and the character carries the device, it has a
# flat chance to turn the animal away (flavor line via the caller's
# "averted_by_excluder" reason). Cooldown still marks: the animal
# approached and was repelled. The book's three power settings and
# willpower-vs-setting roll stay notes until a willpower-graded
# consumer exists. Tunables → T3.19.
ANIMAL_EXCLUDER_KEY = "animal_excluder"
ANIMAL_EXCLUDER_AVERT_CHANCE = 0.5


def _roll_encounter_impl(
    region,
    *,
    new_x: int,
    new_y: int,
    terrain: str,
    char: dict,
    db=None,
    rng=None,
    now: Optional[float] = None,
    carried_keys: Optional[set] = None,
    tile_band_rating: int = 2,
) -> EncounterRollResult:
    """Roll for a wilderness encounter at ``(new_x, new_y)``.

    Called by the wilderness-movement integration point in
    ``parser/builtin_commands.py`` immediately after coords are
    persisted and broadcasts run. Returns a result the caller can
    branch on:

      - ``fired=False`` (with diagnostic ``reason``): no encounter
        this move. Caller proceeds with normal post-move flow.
      - ``fired=True`` with ``entry``: caller surfaces ``entry.narrative``
        to the player and (in a follow-up drop) dispatches the
        encounter type to the appropriate spawner.

    The function is the only public surface that mutates the
    cooldown table — callers must not poke ``_encounter_cooldowns``
    directly.

    Args:
        region: ``WildernessRegion`` (from wilderness_loader). Reads
            ``encounter_pool`` (an EncounterPool) if present; if the
            attribute is missing (older regions / fixtures), treats
            the region as having no encounters.
        new_x, new_y: the just-moved-to coordinates.
        terrain: the terrain slug at the new tile (the caller already
            has this from move_in_wilderness's MoveResult).
        char: character dict. Must have ``id``; everything else is
            optional and consumed by future faction-gate evaluation.
        db, rng, now: optional injection points for testing.

    Returns:
        EncounterRollResult.
    """
    char_id = (char or {}).get("id", 0)
    pool: Optional[EncounterPool] = getattr(region, "encounter_pool", None)

    # No pool configured → no encounters in this region. Not an error;
    # regions ship at minimal substrate before encounter authoring.
    if pool is None or pool.base_chance_per_move <= 0.0 or not pool.entries:
        return EncounterRollResult(fired=False, reason="no_pool_configured")

    # Cooldown gate
    if _is_on_cooldown(char_id, now=now):
        return EncounterRollResult(fired=False, reason="on_cooldown")

    # Chance roll
    r = (rng or random).random()
    if r >= pool.base_chance_per_move:
        return EncounterRollResult(fired=False, reason="chance_miss")

    # Filter the pool to applicable entries for this tile
    dist = _distance_from_edge(region, new_x, new_y)
    eligible = _filter_pool(
        pool.entries,
        terrain=terrain,
        distance_from_edge=dist,
        char=char,
        db=db,
        region=region,
        tile_band_rating=tile_band_rating,
    )
    if not eligible:
        # Per design §5.1: "If no encounters match filters, move
        # proceeds normally (silence is fine; not every tile is
        # eventful)." We don't cool down here — the chance roll
        # already gates pacing, and a player exploring an edge tile
        # shouldn't be penalised for the pool being thin out there.
        return EncounterRollResult(fired=False, reason="no_eligible_entries")

    # Weighted pick
    total_weight = sum(max(1, e.weight) for e in eligible)
    pick = (rng or random).randint(1, total_weight)
    acc = 0
    chosen = eligible[0]
    for e in eligible:
        acc += max(1, e.weight)
        if pick <= acc:
            chosen = e
            break

    # Animal excluder aversion (Gundark Drop E): applies only to
    # creature-templated entries — hostile/non_hostile picks whose
    # payload names an npc_template (the creature-library spawn path).
    # Caravans, weather, and templateless flavor entries pass through.
    if carried_keys and ANIMAL_EXCLUDER_KEY in carried_keys:
        _etype = getattr(chosen, "type", "")
        _payload = getattr(chosen, "payload", None) or {}
        if (_etype in ("hostile", "non_hostile")
                and _payload.get("npc_template")
                and (rng or random).random() < ANIMAL_EXCLUDER_AVERT_CHANCE):
            _mark_cooldown(char_id, now=now)
            return EncounterRollResult(
                fired=False,
                reason="averted_by_excluder",
            )

    # Record the cooldown and return
    _mark_cooldown(char_id, now=now)
    return EncounterRollResult(
        fired=True,
        entry=chosen,
        reason="ok",
    )


# ─────────────────────────────────────────────────────────────────────────────
# T3.19 telemetry — mob-density (encounter-spawn) funnel
# ─────────────────────────────────────────────────────────────────────────────

def _emit_wild_encounter_telemetry(region, char, result,
                                   tile_band_rating) -> None:
    """Emit one mob-density telemetry event for a wilderness encounter roll.

    The complement to the grind-kill faucet emitter
    (``engine/hunting_rewards.emit_grind_kill``): grind_kill captures what a
    kill PAYS; this captures how often the wilderness even OFFERS a huntable
    encounter — the encounter-spawn DENSITY leg of the grind funnel. Joined to
    ``grind_kill`` on ``char_id`` it closes the loop (rolls → fires → kills →
    reward), so post-launch tuning of encounter pacing
    (``base_chance_per_move``, the 60-second cooldown, threat-band pool
    authoring) rests on real movement data instead of guesses — directly
    answering "does the wilderness the grind loop was just redirected into
    actually spawn enough to grind?" (the 2026-06-24 mob-grind realignment
    stripped 158 civic-core/SECURED placements, concentrating grind into the
    wilderness + dangerous-contested bands).

    The ``reason`` field is the pacing signal:
      - ``chance_miss``        — the dominant base-rate outcome (the denominator)
      - ``on_cooldown``        — the 60-second per-character gate biting
      - ``no_eligible_entries``— chance HIT but a THIN/misconfigured pool had
                                 nothing matching this tile's terrain/band/gates
                                 (the content-gap signal the grind redirect cares
                                 about most)
      - ``averted_by_excluder``— the animal-excluder flavor path
      - ``ok``                 — an encounter fired
    ``band`` + ``region``/``zone``/``planet`` localize it; on a fire,
    ``entry_id``/``entry_type`` say WHAT spawned (a hostile/non_hostile entry
    whose payload names an ``npc_template`` is the creature-library huntable
    path).

    DELIBERATELY SKIPS the ``no_pool_configured`` outcome: a move through a
    region with no encounter system at all is not a roll against a pool and
    carries zero pacing signal; emitting it would swamp the stream (it fires on
    every move through an unpooled region) while pool coverage is already
    derivable from region config. Pacing analysis only wants rolls against a
    LIVE pool. (A documented skip, not a silent drop — ask for it if
    pool-coverage analytics are wanted later.)

    Sampling honours ``telemetry.wild_encounter_sample`` (default 1.0). Uniform
    sampling preserves every relative frequency this exists to show — fire-rate,
    the reason distribution, the per-band split — so a post-launch volume
    dial-down loses absolute counts but not the shape (the same argument as
    ``telemetry.command_sample``). Fail-open: wraps the already-fail-open
    ``emit()`` and guards the field assembly + tunable read, so a telemetry
    break can NEVER sink a wilderness move.
    """
    try:
        reason = getattr(result, "reason", "")
        # Skip the pool-less passthrough — see docstring (flood, no signal).
        if reason == "no_pool_configured":
            return
        char_id = (char or {}).get("id", 0) if isinstance(char, dict) else 0
        try:
            char_id = int(char_id)
        except (TypeError, ValueError):
            char_id = 0
        fields: dict = {
            "char_id": char_id,
            "fired": bool(getattr(result, "fired", False)),
            "reason": reason,
            "band": tile_band_rating,
        }
        slug = getattr(region, "slug", "")
        if slug:
            fields["region"] = slug
        zone = getattr(region, "zone", "")
        if zone:
            fields["zone"] = zone
        planet = getattr(region, "planet", "")
        if planet:
            fields["planet"] = planet
        entry = getattr(result, "entry", None)
        if entry is not None:
            fields["entry_id"] = getattr(entry, "id", "")
            fields["entry_type"] = getattr(entry, "type", "")
        try:
            from engine.tunables import get_tunable
            sample = float(get_tunable("telemetry.wild_encounter_sample", 1.0))
        except Exception:
            sample = 1.0
        from engine.telemetry import emit as _tele_emit
        _tele_emit("wild_encounter", fields, sample=sample)
    except Exception:
        log.debug("[wenc] telemetry emit failed", exc_info=True)


def roll_encounter(
    region,
    *,
    new_x: int,
    new_y: int,
    terrain: str,
    char: dict,
    db=None,
    rng=None,
    now: Optional[float] = None,
    carried_keys: Optional[set] = None,
    tile_band_rating: int = 2,
) -> EncounterRollResult:
    """Roll for a wilderness encounter + emit one mob-density telemetry event.

    Thin chokepoint wrapper over :func:`_roll_encounter_impl` (which holds the
    full selector logic + the cooldown mutation). Splitting the emit out keeps
    a SINGLE telemetry seam observing every outcome — fired or not — without
    threading an ``emit`` into each of the impl's early returns. The return
    value is the impl's result verbatim, so every caller + existing test is
    unaffected. See :func:`_emit_wild_encounter_telemetry` for the T3.19
    rationale.
    """
    result = _roll_encounter_impl(
        region,
        new_x=new_x,
        new_y=new_y,
        terrain=terrain,
        char=char,
        db=db,
        rng=rng,
        now=now,
        carried_keys=carried_keys,
        tile_band_rating=tile_band_rating,
    )
    _emit_wild_encounter_telemetry(region, char, result, tile_band_rating)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# YAML parsing — called by engine.wilderness_loader
# ─────────────────────────────────────────────────────────────────────────────

def parse_encounter_pool(raw: dict, *, terrains: dict, report) -> EncounterPool:
    """Build an EncounterPool from a region YAML's ``encounters:`` block.

    Schema (per wilderness_system_design_v1.md §5):

        encounters:
          base_chance_per_move: 0.04
          pool:
            - id: tusken_war_party
              type: hostile
              weight: 2
              terrains: [deep_dunes, ridge]
              min_distance_from_edge: 2
              faction_gate: "tusken_pressure_high"   # optional
              narrative: "Bantha horns rise on the dune line ahead..."
              payload:
                npc_template: tusken_warrior
                count: [2, 4]

    All keys except ``id`` and ``type`` are optional. Unknown types
    are dropped with a warning. Empty / missing block yields a no-op
    EncounterPool (base_chance_per_move=0.0).

    Per the loader's "warn-don't-fail" pattern: bad individual
    entries are dropped with a warning so a thin or partially-broken
    encounter file doesn't sink the whole region load.
    """
    if not isinstance(raw, dict) or not raw:
        return EncounterPool()

    pool = EncounterPool()
    pool.base_chance_per_move = float(raw.get("base_chance_per_move", 0.0))
    if pool.base_chance_per_move < 0.0 or pool.base_chance_per_move > 1.0:
        report.warnings.append(
            f"encounters.base_chance_per_move={pool.base_chance_per_move} "
            f"outside [0.0, 1.0]; clamping."
        )
        pool.base_chance_per_move = max(0.0, min(1.0, pool.base_chance_per_move))

    entries_raw = raw.get("pool") or []
    if not isinstance(entries_raw, list):
        report.warnings.append("encounters.pool is not a list; ignoring.")
        return pool

    seen_ids: set = set()
    for i, e in enumerate(entries_raw):
        if not isinstance(e, dict):
            report.warnings.append(f"encounter #{i}: not a mapping; skipping")
            continue
        eid = e.get("id")
        etype = e.get("type")
        if not eid or not isinstance(eid, str):
            report.warnings.append(f"encounter #{i}: missing id; skipping")
            continue
        if eid in seen_ids:
            report.warnings.append(
                f"encounter {eid!r}: duplicate id in pool; skipping"
            )
            continue
        if etype not in ALLOWED_ENCOUNTER_TYPES:
            report.warnings.append(
                f"encounter {eid!r}: type {etype!r} not in "
                f"{ALLOWED_ENCOUNTER_TYPES}; skipping"
            )
            continue

        # Terrain references must resolve to defined terrains. Unknown
        # terrains are warned and the entry is kept (with the bad
        # entries dropped from terrains list) so a typo doesn't lose
        # the whole encounter.
        raw_terrains = list(e.get("terrains") or [])
        good_terrains = []
        for t in raw_terrains:
            if t in (terrains or {}):
                good_terrains.append(t)
            else:
                report.warnings.append(
                    f"encounter {eid!r}: terrain {t!r} not defined in "
                    f"region.terrains; dropping that reference."
                )

        # DIFF.3: threat-band eligibility bounds. Clamp to [1, 4] and
        # normalize a reversed pair (min>max) to "eligible everywhere" so
        # a corpus typo can't silently zero out an entry.
        _min_band = max(1, min(4, int(e.get("min_band", 1))))
        _max_band = max(1, min(4, int(e.get("max_band", 4))))
        if _min_band > _max_band:
            report.warnings.append(
                f"encounter {eid!r}: min_band {_min_band} > max_band "
                f"{_max_band}; treating as eligible in all bands."
            )
            _min_band, _max_band = 1, 4

        entry = EncounterEntry(
            id=eid,
            type=etype,
            weight=max(1, int(e.get("weight", 1))),
            terrains=good_terrains,
            min_distance_from_edge=max(0, int(e.get("min_distance_from_edge", 0))),
            faction_gate=str(e.get("faction_gate", "")),
            event_gate=str(e.get("event_gate", "")),
            min_band=_min_band,
            max_band=_max_band,
            narrative=str(e.get("narrative", "")),
            payload=dict(e.get("payload") or {}),
        )
        pool.entries.append(entry)
        seen_ids.add(eid)

    return pool
