# -*- coding: utf-8 -*-
"""
engine/harvest.py — Active wilderness harvest (SYN.6.a, 2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.5.2 / §2.5.3.

The active harvest is the larger of the two income levers in the
wilderness power-projection economy (passive yield is the smaller,
shipped in SYN.1.a and tick-wired in SYN.1.b). A character standing
in a wilderness room runs ``harvest`` to:

  * Roll a Survival skill check.
  * Sample credits + resource stacks from a yield table keyed by
    (security tier × owning org's influence tier).
  * If the harvester is NOT a member of the owning faction, pay a
    15% credit tax to the owning org's treasury (resource stacks are
    untaxed; the visitor walks off with the full count).
  * Sit on a 30-minute personal cooldown per region.

Integration with engine/crafting.py
-----------------------------------

Resources land in the character's existing ``inventory.resources``
list via ``engine.crafting.add_resource``. This is the same storage
the crafting system already uses for SWG-style resource stacks
(``{"type", "quantity", "quality"}`` per stack). Region quality
becomes resource stack quality on a 1..100 scale — a 1.0×
multiplier maps to quality 50 (median), and SYN.6.b's weekly
variance (eventually 0.7×..1.3×) will roll quality into ~35..65
plus a skill-margin bonus. Crafting recipes already gate on
``min_quality``; this gives the harvest economy a meaningful
quality dimension without inventing a new column.

T5 rare handling: a Control-tier T5-rare roll grants 1 extra "rare"
stack at quality 100 (the top of the band). When T5 crafting lands,
its recipes will gate on min_quality ≥ 95 (or similar) and these
q100 rares will be the only qualifying inputs. No new resource type
is needed for SYN.6.a.

What this module ships in SYN.6.a:

  * Pure helpers:
      - ``_yield_table_lookup(security, influence_tier)``  →  yield row
      - ``_apply_skill_margin(base_min, base_max, margin)``  →  scaled
      - ``_quality_to_resource_quality(quality, margin)``  →  1..100
      - ``_compute_tax(credits, is_owner_member)``  →  (kept, taxed)
      - ``compute_harvest_payout(...)``  →  full deterministic computation
  * DB-touching wrappers:
      - ``_get_region_quality(db, region_slug)``  — SEAM, returns 1.0
        in SYN.6.a (SYN.6.b wires actual weekly variance).
      - ``perform_harvest(db, char, room_id, *, rng=None, now=None)``
        — main entry point used by parser.

Two-tier reward gate (per §4.25 wilderness-only influence invariant):

  * Active harvest is wilderness-only by construction — the resolver
    rejects city-map rooms by returning ``region_slug=None`` from
    ``_resolve_room_region``. No second check is needed.

  * Active harvest does NOT grant org influence directly. The
    design's §2.7 reward table covers npc_kill / mission_complete /
    pvp_win + intel handover; harvesting earns credits + resources
    instead. (Owner orgs get the 15% tax on visitor harvests as
    their influence-economy payoff.) This is intentional — if
    harvest also granted influence per harvest, the visitor-economy
    pressure would invert (no one would visit if it shored up the
    owner's contest position too).

Seam status — SYN.6.b will land:

  * ``_get_region_quality`` will read the per-region weekly variance
    that the Monday-midnight tick writes to a new schema column.
    For SYN.6.a it always returns 1.0 — the seam exists, the
    consumer is wired, and SYN.6.b is a one-function swap.

  * The Director ``faction resource_outlook`` digest is a parser-
    side surface that reads the same per-region quality data. Not
    in SYN.6.a scope.

Test-fixture posture — SYN.6.a uses the same ``_MiniDB`` pattern
established by the SYN.5 tests: an in-memory sqlite with rooms,
zones, characters, organizations, region_ownership. See
``tests/test_syn6a_active_harvest.py``.
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Constants (design §2.5.2 verbatim) ───────────────────────────────────────

# Yield table — keyed by (security, influence_tier).
# Each entry: (cr_min, cr_max, resources_template)
# Where resources_template is {resource_type: count} for the base award,
# and may include "_t5_rare_chance" (float 0..1) for top-band T5 chance.
#
# Per design §2.5.2:
#
#   | Region base | Owning org's influence | Harvest (cr) | Resources |
#   |-------------|------------------------|--------------|-----------|
#   | Contested | Foothold | 100-200 | 1 metal |
#   | Contested | Dominant | 150-300 | 2 metal + 1 organic |
#   | Contested | Control  | 200-400 | 2 metal + 1 organic + chance T5 rare |
#   | Lawless   | Foothold | 150-300 | 2 metal + 1 chemical |
#   | Lawless   | Dominant | 250-500 | 3 metal + 2 chemical + 1 rare |
#   | Lawless   | Control  | 400-800 | 4 metal + 3 chemical + 2 rare + T5 chance |
#
# All resource types here are in engine.crafting.RESOURCE_TYPES:
# {metal, chemical, organic, energy, composite, rare}. The "T5 rare"
# is granted as a +1 "rare" stack at quality 100 (the top of the
# band) — see module docstring.

_T5_RARE_CHANCE = 0.10  # 10% at Control tier; SYN.6.b can tune

YIELD_TABLE: dict[tuple[str, str], tuple[int, int, dict]] = {
    ("contested", "foothold"):
        (100, 200, {"metal": 1}),
    ("contested", "dominant"):
        (150, 300, {"metal": 2, "organic": 1}),
    ("contested", "control"):
        (200, 400, {"metal": 2, "organic": 1,
                    "_t5_rare_chance": _T5_RARE_CHANCE}),
    ("lawless", "foothold"):
        (150, 300, {"metal": 2, "chemical": 1}),
    ("lawless", "dominant"):
        (250, 500, {"metal": 3, "chemical": 2, "rare": 1}),
    ("lawless", "control"):
        (400, 800, {"metal": 4, "chemical": 3, "rare": 2,
                    "_t5_rare_chance": _T5_RARE_CHANCE}),
}

# Un-owned region falls back to a baseline yield (security-only).
# Design §2.5.2 doesn't enumerate this case — it implicitly assumes
# an owning org exists. We treat un-owned regions as "foothold-tier"
# for the security level present, on the principle that the absence
# of an owner is morally similar to a weak (foothold) ownership: no
# one has projected enough power to extract more than baseline. This
# gives un-owned regions a coherent yield rather than a hard-fail.
_UNOWNED_FALLBACK_TIER = "foothold"

# Skill check difficulty — Survival is the per-design skill.
# Tatooine-style frontier survival sits around Easy-Moderate per the
# WEG D6 R&E ladder (Easy 6, Moderate 11). We use Easy 6: harvest is
# a routine action, not a gauntlet. The reward scaling lives in the
# margin multiplier (better roll → more credits + higher quality).
HARVEST_DIFFICULTY = 6
HARVEST_SKILL = "survival"

# Margin scaling — every 5 points of margin above DC gives +20% credits
# and +10 to the resource stack quality (capped at +50). This matches
# WEG margin tradition (5-point success-quality bands).
_MARGIN_BAND_SIZE = 5
_MARGIN_CREDIT_BONUS_PER_BAND = 0.20
_MARGIN_QUALITY_BONUS_PER_BAND = 10
_MARGIN_QUALITY_BONUS_CAP = 50

# Quality scaling: a 1.0× region quality maps to baseline resource
# quality 50 (mid-band). Region quality 0.7× → 35, 1.3× → 65.
_QUALITY_BASELINE = 50.0
_QUALITY_BAND_SPAN = 50.0  # so 0..2.0× maps to 0..100 quality

# T5 rare hit grants 1 extra "rare" stack at this quality. The top
# of the band ensures future T5 crafting can gate on min_quality≥95.
_T5_RARE_QUALITY = 100.0

# 30-minute personal cooldown per region (design §2.5.2).
HARVEST_COOLDOWN_SECS = 30 * 60

# Non-owner tax — design §2.5.3 fixes this at 15% of credits only.
NON_OWNER_TAX_RATE = 0.15

# Cooldown key prefix — namespaced by region slug so a harvester can
# cycle between multiple regions without waiting on a single global
# cooldown.
COOLDOWN_KEY_PREFIX = "harvest_"

# Resource types that have a "rare" semantic in the T5 path. Used to
# decide which stack receives the +1 T5-rare bonus.
_T5_RARE_TARGET = "rare"


# ── Pure helpers (no DB) ─────────────────────────────────────────────────────

def _yield_table_lookup(
    security: str, influence_tier: str,
) -> tuple[int, int, dict]:
    """Look up the base yield row for a (security, influence_tier) pair.

    Falls back to the foothold yield for the same security level if
    the influence tier is unknown (e.g. un-owned region — see
    ``_UNOWNED_FALLBACK_TIER``).

    Falls back to ``("lawless", "foothold")`` if security is unknown.
    """
    sec = (security or "lawless").lower()
    tier = (influence_tier or _UNOWNED_FALLBACK_TIER).lower()
    if sec not in ("contested", "lawless"):
        # Secured zones never reach harvest — the resolver rejects
        # them before getting here — but if a misconfigured room
        # slips through, treat as lawless. (Secured wilderness is
        # impossible by design §2.5.5; defensive only.)
        sec = "lawless"
    row = YIELD_TABLE.get((sec, tier))
    if row is None:
        row = YIELD_TABLE.get((sec, _UNOWNED_FALLBACK_TIER))
    return row


def _apply_skill_margin(
    base_min: int, base_max: int, margin: int,
) -> tuple[tuple[int, int], int]:
    """Apply skill-check margin to a (cr_min, cr_max) credit band.

    Returns a ``(scaled_band, quality_bonus)`` pair:

      * ``scaled_band``    = (min, max) credit endpoints after margin
                             scaling. (0, 0) if margin < 0 (failed).
      * ``quality_bonus``  = integer quality bonus to apply to the
                             resource stack (0..50, in 10-pt steps
                             per 5-pt margin band).

    A negative margin (failed check) returns ((0, 0), 0) — no payout.
    A zero margin (exact-DC success) returns the base band unchanged
    and zero quality bonus.

    Margins are quantised into 5-point bands; the first band (0..4)
    gives +0%/+0Q, the second (5..9) gives +20%/+10Q, the third
    (10..14) gives +40%/+20Q, etc.
    """
    if margin < 0:
        return ((0, 0), 0)
    bands = max(0, margin // _MARGIN_BAND_SIZE)
    multiplier = 1.0 + bands * _MARGIN_CREDIT_BONUS_PER_BAND
    scaled_min = int(base_min * multiplier)
    scaled_max = int(base_max * multiplier)
    quality_bonus = min(bands * _MARGIN_QUALITY_BONUS_PER_BAND,
                        _MARGIN_QUALITY_BONUS_CAP)
    return ((scaled_min, scaled_max), quality_bonus)


def _quality_to_resource_quality(
    region_quality: float, margin_quality_bonus: int,
) -> float:
    """Convert (region_quality multiplier, margin bonus) → 1..100 quality.

    Region quality 1.0× → baseline 50. Each margin band adds
    ``_MARGIN_QUALITY_BONUS_PER_BAND`` directly. The final value is
    clamped to (1.0, 100.0) — the band the crafting system expects.
    """
    # Map 0..2.0× region quality linearly to 0..100. 1.0× → 50.
    base = region_quality * _QUALITY_BAND_SPAN
    final = base + float(margin_quality_bonus)
    return round(max(1.0, min(100.0, final)), 1)


def _compute_tax(
    credits: int, is_owner_member: bool, owner_exists: bool = True,
) -> tuple[int, int]:
    """Compute the (kept, taxed) split for a credit award.

    The tax exists only when there is a recipient. Three cases:

      * No owner at all (``owner_exists=False``) → harvester keeps
        everything, no tax. The 15% would otherwise vanish into the
        void.
      * Harvester IS a member of the owning org → harvester keeps
        everything, no tax.
      * Harvester is a non-member visiting an owned region → 15%
        routed to owner treasury.

    Returns ``(kept_credits, taxed_credits)`` such that
    ``kept + taxed == credits``.
    """
    if credits <= 0:
        return (0, 0)
    if not owner_exists:
        return (credits, 0)
    if is_owner_member:
        return (credits, 0)
    tax = int(round(credits * NON_OWNER_TAX_RATE))
    # Clamp tax — guard against rounding edge cases.
    tax = max(0, min(credits, tax))
    return (credits - tax, tax)


def compute_harvest_payout(
    *,
    security: str,
    influence_tier: str,
    margin: int,
    quality=1.0,
    is_owner_member: bool = True,
    owner_exists: bool = True,
    rng: Optional[random.Random] = None,
) -> dict:
    """Full deterministic harvest payout computation (no DB writes).

    The ``owner_exists`` flag is independent of ``is_owner_member``:
    a region may have no owner at all (``owner_exists=False``), in
    which case no tax is routed and the harvester keeps everything.
    The default ``owner_exists=True, is_owner_member=True`` is the
    owner-self-harvest case (no tax). The expensive case is
    ``owner_exists=True, is_owner_member=False`` — a non-member
    visiting an owned region pays the 15% tax.

    The ``quality`` parameter accepts either form:

      * **float** — single multiplier applied to every resource type.
        This is the SYN.6.a back-compat form (and the form that
        ``_get_region_quality`` returned before SYN.6.b).
      * **dict[type, float]** — per-resource-type multipliers per
        SYN.6.b weekly-variance design §2.5.5 ('metal might be 1.3×
        while chemical is 0.8× the same week'). Each stack's quality
        is computed against its own type's multiplier.

    Missing types in the dict fall back to 1.0 — defensive against
    partial rolls.

    Returns a dict:
      ``{
          "credits_gross":     int,    # before tax
          "credits_kept":      int,    # harvester's take
          "credits_tax":       int,    # owner's cut (0 if owner-member)
          "resource_stacks":   list,   # [{type, quantity, quality}, ...]
          "t5_rare":           bool,   # rolled t5_rare bonus?
          "yield_band":        (min, max),  # post-skill-margin band
          "stack_qualities":   dict,   # {type: 1..100 quality, ...}
                                       # NEW in SYN.6.b — per-type
                                       # qualities. ``stack_quality``
                                       # (legacy single value) is the
                                       # mean for back-compat display.
          "stack_quality":     float,  # mean of stack_qualities
                                       # (legacy; one quality bucket).
      }``

    The RNG is injectable for deterministic testing. If None, uses
    a fresh ``random.Random()`` seeded from the system entropy pool.
    """
    if rng is None:
        rng = random.Random()

    row = _yield_table_lookup(security, influence_tier)
    cr_min, cr_max, resources_template = row

    # Skill-margin scaling: credit band + quality bonus
    scaled_band, quality_bonus = _apply_skill_margin(cr_min, cr_max, margin)
    scaled_min, scaled_max = scaled_band

    if scaled_band == (0, 0):
        # Failed check — empty payout, no tax, no resources.
        return {
            "credits_gross":   0,
            "credits_kept":    0,
            "credits_tax":     0,
            "resource_stacks": [],
            "t5_rare":         False,
            "yield_band":      (0, 0),
            "stack_qualities": {},
            "stack_quality":   0.0,
        }

    # Credit sampling — uniform inside the band.
    credits_gross = rng.randint(scaled_min, scaled_max)

    # Resolve per-type quality lookup. Accept legacy float form OR
    # SYN.6.b dict form. The lookup callable defends against missing
    # types (falls back to 1.0).
    def _quality_for(rtype: str) -> float:
        if isinstance(quality, dict):
            return float(quality.get(rtype, 1.0))
        return float(quality)

    # Build stacks from the template:
    #   - "_t5_rare_chance" entries roll for a bonus rare stack
    #   - all other entries map type → quantity at the per-type quality
    resource_stacks: list[dict] = []
    stack_qualities: dict[str, float] = {}
    t5_rare = False

    for key, val in resources_template.items():
        if key == "_t5_rare_chance":
            chance = float(val)
            if rng.random() < chance:
                t5_rare = True
            continue
        try:
            qty = int(val)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        type_quality = _quality_for(key)
        sq = _quality_to_resource_quality(type_quality, quality_bonus)
        stack_qualities[key] = sq
        resource_stacks.append({
            "type":     key,
            "quantity": qty,
            "quality":  sq,
        })

    if t5_rare:
        # +1 "rare" stack at q100. If the template already has a
        # "rare" stack at the per-type quality, the crafting
        # add_resource call will merge them (within tolerance) on
        # the DB-write side — but at q100 vs lesser quality they
        # likely won't merge, which is exactly what we want for
        # T5-gating.
        resource_stacks.append({
            "type":     _T5_RARE_TARGET,
            "quantity": 1,
            "quality":  _T5_RARE_QUALITY,
        })

    credits_kept, credits_tax = _compute_tax(
        credits_gross, is_owner_member, owner_exists=owner_exists,
    )

    # Legacy single-quality field: mean of the per-type qualities for
    # display/back-compat. 0.0 if no stacks awarded.
    if stack_qualities:
        legacy_stack_quality = round(
            sum(stack_qualities.values()) / len(stack_qualities), 1,
        )
    else:
        legacy_stack_quality = 0.0

    return {
        "credits_gross":   credits_gross,
        "credits_kept":    credits_kept,
        "credits_tax":     credits_tax,
        "resource_stacks": resource_stacks,
        "t5_rare":         t5_rare,
        "yield_band":      scaled_band,
        "stack_qualities": stack_qualities,
        "stack_quality":   legacy_stack_quality,
    }


# ── Region-quality seam (SYN.6.b consumer) ───────────────────────────────────

async def _get_region_quality(db, region_slug: str):
    """Return the region's current per-resource-type quality multipliers.

    **SYN.6.b (2026-05-25):** swap of the SYN.6.a seam from a constant
    1.0× to a real per-resource-type dict read from the
    ``region_quality`` table (populated by the weekly Monday-midnight
    tick — see ``engine.region_quality.tick_weekly_region_quality``).

    Returns ``dict[resource_type, float]``. Every key in
    ``engine.crafting.RESOURCE_TYPES`` is present; missing rolls
    default to 1.0×.

    Pre-SYN.6.b call sites passed the return value into
    ``compute_harvest_payout(..., quality=)``, which now accepts
    either a float OR a dict — so no caller-side changes are needed.
    """
    try:
        from engine.region_quality import get_region_quality_for
        return await get_region_quality_for(db, region_slug)
    except Exception:
        # Fail-soft: if the region_quality module/table is unavailable
        # for any reason, fall back to the SYN.6.a constant. Better to
        # let harvest run at baseline than block it on a missing seam.
        log.debug(
            "[harvest] region_quality lookup failed for %s; "
            "falling back to 1.0× baseline", region_slug,
        )
        return 1.0


# ── Owner-membership lookup ──────────────────────────────────────────────────

async def _is_owner_member(
    db, char: dict, region_slug: str,
) -> tuple[bool, Optional[str]]:
    """Check whether ``char`` is a member of the org owning the region.

    Returns ``(is_member, owner_org_code)``. ``owner_org_code`` is
    None when the region is un-owned (in which case ``is_member`` is
    False — there's no one to tax to, and no preferential treatment).

    The membership check uses the character's ``faction_id`` field —
    that's the org-code-as-faction model used throughout the SYN.5
    influence hooks. Cross-membership (a char belongs to multiple
    orgs) isn't represented; ``faction_id`` is the canonical
    "primary org" for the harvester. This matches how
    ``on_npc_kill`` / ``on_mission_complete`` decide which org gets
    the influence delta.
    """
    try:
        from engine.territory import get_region_owner
        owner_row = await get_region_owner(db, region_slug)
    except Exception:
        log.warning("[harvest] get_region_owner failed for %s",
                    region_slug, exc_info=True)
        return (False, None)
    if not owner_row:
        return (False, None)
    owner_code = owner_row.get("org_code")
    char_faction = char.get("faction_id") or "independent"
    is_member = (
        owner_code is not None
        and char_faction == owner_code
        and char_faction != "independent"
    )
    return (is_member, owner_code)


# ── Harvest-node gating (SYN.6.c, May 25 2026) ───────────────────────────────

async def _is_harvest_node(db, room_id: int, region_slug: str) -> bool:
    """Decide whether ``room_id`` is a valid spot to run ``harvest``.

    Per ``contestable_wilderness_design_v2.md`` §2.5.2 / SYN.6.c:
    harvest is *intended* to be gated on specific landmarks within a
    region (a "harvest node" — a tile authored to surface resources),
    not on every wilderness room. SYN.6.a deferred this; SYN.6.c
    wires it.

    **Gating rule with back-compat fallback:**

      * If the region has ANY room with ``properties.harvest_node:
        true``, only those rooms are harvest nodes.
      * If the region has NO ``harvest_node`` flags anywhere, EVERY
        room in the region is a harvest node (the SYN.6.a behavior).

    This lets content authors opt regions into landmark-gated harvest
    one region at a time, without breaking the existing harvest
    experience in regions that haven't been audited yet. When all
    regions have been flagged (post-launch content pass), the
    fallback path goes dormant.

    Returns True if the room is a valid harvest node.
    """
    # Check if THIS room is flagged
    try:
        room = await db.get_room(room_id)
    except Exception:
        log.warning("[harvest] _is_harvest_node: get_room failed",
                    exc_info=True)
        return False
    if not room:
        return False
    this_room_flagged = _room_has_harvest_node_flag(room)
    if this_room_flagged:
        return True

    # Check if ANY room in this region is flagged (the fallback test).
    # If yes, this room is gated out. If no, we're in fallback mode
    # (every room counts) and this room qualifies.
    try:
        rows = await db.fetchall(
            "SELECT properties FROM rooms "
            "WHERE wilderness_region_id = ? AND properties IS NOT NULL "
            "  AND properties != ''",
            (region_slug,),
        )
    except Exception:
        log.warning("[harvest] _is_harvest_node: region scan failed for %s",
                    region_slug, exc_info=True)
        # On scan failure, fall back to the SYN.6.a behavior (allow).
        return True

    any_flagged = False
    for r in rows:
        props_raw = r.get("properties") if hasattr(r, "get") else r["properties"]
        if not props_raw:
            continue
        try:
            props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(props, dict) and props.get("harvest_node") is True:
            any_flagged = True
            break

    if any_flagged:
        # Region has authored harvest nodes; this room isn't one.
        return False
    # Region has no harvest_node flags anywhere → fallback to
    # SYN.6.a behavior, every room qualifies.
    return True


def _room_has_harvest_node_flag(room: dict) -> bool:
    """Read ``room['properties']['harvest_node']`` defensively."""
    props_raw = room.get("properties")
    if not props_raw:
        return False
    if isinstance(props_raw, str):
        try:
            props = json.loads(props_raw)
        except (json.JSONDecodeError, TypeError):
            return False
    elif isinstance(props_raw, dict):
        props = props_raw
    else:
        return False
    return props.get("harvest_node") is True


# ── Main entry point ─────────────────────────────────────────────────────────

async def perform_harvest(
    db, char: dict, room_id: int,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict:
    """Run an active harvest at ``room_id`` for ``char``.

    Returns a result dict:

      ``{
          "ok":              bool,
          "msg":             str,    # human-readable result line
          "credits_kept":    int,
          "credits_tax":     int,
          "resource_stacks": list,   # [{type, quantity, quality}, ...]
          "t5_rare":         bool,
          "region_slug":     str,
          "owner_code":      str | None,
          "skill_roll":      int,
          "skill_pool":      str,
          "margin":          int,
          "security":        str,
          "influence_tier":  str,
      }``

    On failure, ``ok=False`` and ``msg`` carries the reason. The
    parser layer translates this to a user-facing line.

    Failure conditions (in order):
      1. Room not found / no wilderness_region_id → 'not a harvest node'
      2. Zone secured (rare; defensive) → 'too tightly policed'
      3. Cooldown still active → 'recently harvested; wait <duration>'
      4. Skill check engine error → 'survey instruments hiccup'

    Success-with-no-payout (cooldown still sets):
      * Skill check failed → 'you find nothing of value'

    Success conditions:
      * Apply skill margin scaling to base band.
      * Apply region quality multiplier (SYN.6.a: always 1.0).
      * Roll credit amount + resource stacks at quality 1..100.
      * If non-owner: route 15% of credits to owner treasury.
      * Award credits + resource stacks to harvester (DB writes).
      * Set 30-minute regional cooldown.

    Influence: NONE — see module docstring for rationale.
    """
    if now is None:
        now = time.time()
    if rng is None:
        rng = random.Random()

    # ── Step 1: room → region resolution ────────────────────────────────────
    from engine.territory import _resolve_room_region, get_zone_security
    region_slug, zone_id = await _resolve_room_region(db, room_id)
    if region_slug is None:
        return {
            "ok": False,
            "msg": "This isn't a harvest node. Find a wilderness region.",
        }

    # ── Step 1.5: harvest-node gating (SYN.6.c) ─────────────────────────────
    # Per design §2.5.2: harvest happens at specific landmarks ("harvest
    # nodes"), not on every wilderness tile. SYN.6.c wires this with a
    # region-scoped fallback — if no rooms in the region are flagged,
    # every room qualifies (SYN.6.a back-compat).
    if not await _is_harvest_node(db, room_id, region_slug):
        return {
            "ok": False,
            "msg": ("There's nothing harvestable right here. Look "
                    "for a landmark — somewhere the region's resources "
                    "actually surface."),
        }

    # ── Step 2: zone security check ─────────────────────────────────────────
    security = "lawless"
    if zone_id is not None:
        try:
            security = await get_zone_security(db, zone_id) or "lawless"
        except Exception:
            log.warning("[harvest] get_zone_security failed for zone %s",
                        zone_id, exc_info=True)
            security = "lawless"
    if security == "secured":
        # Defensive — secured wilderness shouldn't exist per design
        # §2.5.5 (wilderness is CONTESTED by default), but if a
        # misconfigured region claims secured status, refuse.
        return {
            "ok": False,
            "msg": "This region is too tightly policed to harvest.",
        }

    # ── Step 3: cooldown check ──────────────────────────────────────────────
    from engine.cooldowns import (
        check_cooldown, remaining_cooldown, set_cooldown, format_remaining,
    )
    cd_key = f"{COOLDOWN_KEY_PREFIX}{region_slug}"
    if not check_cooldown(char, cd_key):
        rem = remaining_cooldown(char, cd_key)
        return {
            "ok": False,
            "msg": (f"You harvested recently. Wait "
                    f"{format_remaining(rem)} before another sweep."),
        }

    # ── Step 4: owner resolution + influence tier ───────────────────────────
    is_owner_member, owner_code = await _is_owner_member(db, char, region_slug)
    influence_tier = _UNOWNED_FALLBACK_TIER  # un-owned default
    if owner_code is not None and zone_id is not None:
        # Look up the owning org's influence in the parent zone.
        try:
            rows = await db.fetchall(
                "SELECT score FROM territory_influence "
                "WHERE zone_id = ? AND org_code = ?",
                (zone_id, owner_code),
            )
            score = int(rows[0]["score"]) if rows else 0
        except Exception:
            log.warning("[harvest] influence lookup failed",
                        exc_info=True)
            score = 0
        from engine.territory import _get_influence_tier
        influence_tier = _get_influence_tier(score)
        # _get_influence_tier returns "none" for sub-foothold scores.
        # Map that to our fallback — the owner has the region but
        # no real influence in its parent zone, treat as foothold.
        if influence_tier == "none":
            influence_tier = _UNOWNED_FALLBACK_TIER

    # ── Step 5: skill check ─────────────────────────────────────────────────
    from engine.skill_checks import perform_skill_check
    try:
        sc = perform_skill_check(char, HARVEST_SKILL, HARVEST_DIFFICULTY)
    except Exception:
        log.warning("[harvest] perform_skill_check raised", exc_info=True)
        # Cooldown is NOT set if the engine itself errors — a real
        # bug shouldn't farm the player's cooldown.
        return {
            "ok": False,
            "msg": "Your survey instruments hiccup. Try again.",
        }

    # ── Step 6: payout computation ──────────────────────────────────────────
    quality = await _get_region_quality(db, region_slug)
    payout = compute_harvest_payout(
        security=security,
        influence_tier=influence_tier,
        margin=sc.margin if sc.success else -1,
        quality=quality,
        is_owner_member=is_owner_member,
        owner_exists=(owner_code is not None),
        rng=rng,
    )

    # ── Step 7: cooldown set (even on failed check) ─────────────────────────
    # A failed skill check still consumes the cooldown — otherwise a
    # player could spam-roll until they nail a Wild Die. Design
    # intent is for harvest to feel like a measured action, not a
    # slot-machine pull.
    set_cooldown(char, cd_key, HARVEST_COOLDOWN_SECS)
    try:
        await db.save_character(char["id"], attributes=char["attributes"])
    except Exception:
        log.warning("[harvest] cooldown save failed", exc_info=True)
        # Continue — the in-memory cooldown is set, the DB write
        # didn't take. Logged for ops, not a hard fail.

    # ── Step 8: handle failed-check exit ────────────────────────────────────
    if not sc.success:
        return {
            "ok":              True,   # cooldown set, no payout
            "msg":             "You search but turn up nothing of value.",
            "credits_kept":    0,
            "credits_tax":     0,
            "resource_stacks": [],
            "t5_rare":         False,
            "region_slug":     region_slug,
            "owner_code":      owner_code,
            "skill_roll":      sc.roll,
            "skill_pool":      sc.pool_str,
            "margin":          sc.margin,
            "security":        security,
            "influence_tier":  influence_tier,
        }

    # ── Step 9: route credits ───────────────────────────────────────────────
    # Harvester gets credits_kept; owner org (if non-member harvest)
    # gets credits_tax routed to treasury.
    try:
        cur_credits = int(char.get("credits") or 0)
    except (TypeError, ValueError):
        cur_credits = 0
    new_credits = cur_credits + payout["credits_kept"]
    try:
        await db.save_character(char["id"], credits=new_credits)
        char["credits"] = new_credits
    except Exception:
        log.warning("[harvest] credit save failed for char %s",
                    char.get("id"), exc_info=True)
        # Credits failed to write; we proceed but log loud. The
        # cooldown is set, so the player can't immediately retry —
        # they should report this and an admin can compensate.

    # Owner treasury tax routing — only if non-member AND owner exists.
    if payout["credits_tax"] > 0 and owner_code is not None:
        try:
            owner_org = await db.get_organization(owner_code)
            if owner_org:
                await db.adjust_org_treasury(
                    owner_org["id"], payout["credits_tax"],
                )
                log.info(
                    "[harvest] tax: %s pays %dcr to %s for harvest in %s",
                    char.get("name", "?"), payout["credits_tax"],
                    owner_code, region_slug,
                )
        except Exception:
            log.warning("[harvest] owner-treasury tax routing failed",
                        exc_info=True)
            # The harvester is unaffected by tax-routing failures —
            # they keep their credits_kept regardless. The owner just
            # doesn't see the tax this round. Logged for ops.

    # ── Step 10: grant resource stacks to harvester ─────────────────────────
    # Use engine.crafting.add_resource so the harvested stacks land in
    # the existing inventory.resources list with proper merging.
    if payout["resource_stacks"]:
        try:
            from engine.crafting import add_resource
            for stack in payout["resource_stacks"]:
                add_resource(char, stack["type"],
                             stack["quantity"], stack["quality"])
            await db.save_character(char["id"], inventory=char["inventory"])
        except Exception:
            log.warning("[harvest] resource grant failed", exc_info=True)
            # Same posture as credits — log and continue.

    # ── Step 11: assemble success result ────────────────────────────────────
    return {
        "ok":              True,
        "msg":             _format_success_msg(payout, region_slug,
                                                owner_code),
        "credits_kept":    payout["credits_kept"],
        "credits_tax":     payout["credits_tax"],
        "resource_stacks": payout["resource_stacks"],
        "t5_rare":         payout["t5_rare"],
        "region_slug":     region_slug,
        "owner_code":      owner_code,
        "skill_roll":      sc.roll,
        "skill_pool":      sc.pool_str,
        "margin":          sc.margin,
        "security":        security,
        "influence_tier":  influence_tier,
    }


def _format_success_msg(
    payout: dict, region_slug: str, owner_code: Optional[str],
) -> str:
    """Compose the human-readable success line for a harvest payout."""
    parts = [f"Harvested {region_slug}:"]
    parts.append(f"+{payout['credits_kept']:,}cr")
    stacks = payout.get("resource_stacks") or []
    if stacks:
        stack_parts = []
        # Bucket by type to consolidate same-type stacks at the same
        # quality (e.g. 2 metal q50 + the T5 rare-only delta).
        for s in stacks:
            stack_parts.append(
                f"{s['quantity']} {s['type']} (q{int(s['quality'])})"
            )
        parts.append("+ " + ", ".join(stack_parts))
    if payout.get("credits_tax") and owner_code:
        parts.append(f"(tax {payout['credits_tax']:,}cr → {owner_code})")
    if payout.get("t5_rare"):
        parts.append("[T5 rare!]")
    return " ".join(parts)
