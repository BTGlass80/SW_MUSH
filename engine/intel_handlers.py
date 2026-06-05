# -*- coding: utf-8 -*-
"""
engine/intel_handlers.py — Espionage-as-influence (SYN.5, 2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.7. The +intel command's
existing seal + give flow gains a redemption surface: a sealed intel
report given to a **faction handler NPC** converts to:

  * Credits (existing economy)
  * Influence delta in the region the intel describes

Conversion rates per design §2.7:

  | Quality | Credits     | Influence  |
  |---------|-------------|------------|
  | low     | 200–500     | 1–3        |
  | medium  | 600–1500    | 4–8        |
  | high    | 2000–5000   | 10–20      |

Quality is assigned by ``evaluate_intel_quality`` — a heuristic stub
in SYN.5, replaced by the Director AI in T3.15. The stub scores on:

  * Line count (more lines → more substance)
  * Recency (created within the last ~24h vs days ago)
  * Region specificity (a known wilderness region slug mentioned in
    the report body → much higher score; the intel "describes" a
    specific region only when that region is actually named)
  * Faction / NPC specificity (proper-noun-shaped tokens → more
    actionable than vague chatter)

The handler NPC is identified by an ai_config_json marker:
``{"is_intel_handler": true, "faction": "<faction_code>"}``. The
handler must match the handing-over character's faction; cross-faction
handover is a future feature (intel-laundering through a third
party).

Standing discipline: the rep + credits award lives in the caller
(``parser/espionage_commands.py``); this module only does the
classification + influence-delta routing. The credit-side debit goes
through ``db.save_character`` after the handler hand-over.

SYN.6 / SYN.7+ work that may consume this module:
  * Active harvest reward flow may reuse ``evaluate_intel_quality``'s
    heuristic for related "asset valuation" features.
  * Director AI T3.15 will replace ``evaluate_intel_quality`` with
    a real LLM call; this module's function-level seam is what makes
    that swap cheap.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Quality tier rates (design §2.7) ─────────────────────────────────────────
#
# Each tuple is (min_influence, max_influence, min_credits, max_credits).
# Bounds are inclusive on both ends. Random sampling picks uniformly
# within the range — the design's "tunable" language explicitly invites
# variance for replayability.

INTEL_QUALITY_LOW    = (1,   3,   200,  500)
INTEL_QUALITY_MEDIUM = (4,   8,   600,  1500)
INTEL_QUALITY_HIGH   = (10,  20,  2000, 5000)

_QUALITY_TIERS = {
    "low":    INTEL_QUALITY_LOW,
    "medium": INTEL_QUALITY_MEDIUM,
    "high":   INTEL_QUALITY_HIGH,
}

# Heuristic boundaries (used by evaluate_intel_quality stub). Tuned to
# match the rough intent of "low = vague chatter, medium = some
# substance, high = specific + recent + actionable".
_HIGH_SCORE_MIN     = 7
_MEDIUM_SCORE_MIN   = 4

# Report-recency window. Intel created within the last 24h is "fresh";
# stuff older is "stale" — penalty of -1 score.
_FRESHNESS_WINDOW_SECS = 24 * 3600

# AI config marker on handler NPCs.
INTEL_HANDLER_AI_KEY = "is_intel_handler"

# ── A3: INTELLIGENCE_THAW world event ────────────────────────────────────────
# The spy playstyle's "holiday" (engine/world_events.py EventType.INTELLIGENCE_THAW).
# While active it multiplies the CREDIT payout from an intel handover; influence
# is deliberately left unscaled (multiplying influence would distort the
# territory-contest system). handover_intel reads the live multiplier via
# get_effect(INTEL_THAW_EFFECT_KEY, 1.0) unless a caller injects one.
INTEL_THAW_EFFECT_KEY = "intel_pay_mult"


def apply_intel_thaw(credits: int, mult: float) -> int:
    """Apply the INTELLIGENCE_THAW credit multiplier to an intel payout.

    Pure. A multiplier <= 1.0 (or non-positive/garbage) leaves the base payout
    unchanged, so the absence of an active thaw is a no-op. Rounds to int.
    """
    try:
        m = float(mult)
    except (TypeError, ValueError):
        return int(credits)
    if m <= 1.0:
        return int(credits)
    return int(round(int(credits) * m))


# ── Region keyword extraction ────────────────────────────────────────────────

def _extract_mentioned_regions(text: str, known_regions: set[str]) -> list[str]:
    """Find any known wilderness region slugs mentioned in the text.

    Slug match is exact, case-insensitive, word-boundary. Slugs with
    underscores (``dune_sea``) are matched as-is and also as their
    spaced form (``dune sea``). Returns the unique list in
    first-mention order in the source text.

    The iteration order matters: when a report mentions multiple
    regions, the first-mentioned wins for influence routing. So we
    scan each known region for its earliest match position, then
    sort by that position. Regions that don't appear at all are
    excluded.
    """
    if not text or not known_regions:
        return []
    haystack = text.lower()
    # Collect (first_position, slug) tuples for regions actually mentioned
    mentions: list[tuple[int, str]] = []
    for slug in known_regions:
        canonical = slug.lower()
        spaced = canonical.replace("_", " ")
        # Find earliest match (slug-form or spaced-form)
        best_pos = -1
        m1 = re.search(rf"\b{re.escape(canonical)}\b", haystack)
        if m1:
            best_pos = m1.start()
        m2 = re.search(rf"\b{re.escape(spaced)}\b", haystack)
        if m2:
            if best_pos < 0 or m2.start() < best_pos:
                best_pos = m2.start()
        if best_pos >= 0:
            mentions.append((best_pos, slug))
    # First-mention order
    mentions.sort(key=lambda t: t[0])
    return [slug for _, slug in mentions]


# ── Quality evaluation (heuristic stub for T3.15) ────────────────────────────

def evaluate_intel_quality(report: dict, known_regions: set[str],
                            now: Optional[float] = None) -> dict:
    """Score an intel report and return its quality classification.

    SYN.5 ships this as a heuristic stub. T3.15 (Director AI CW-tuning)
    will replace this with a real LLM call that reads the report text
    and returns a structured assessment.

    Inputs:
      * ``report``         — an intel report dict (see engine.espionage's
                             create_intel_report shape).
      * ``known_regions``  — set of wilderness region slugs known to
                             the world. The handler resolves these from
                             the rooms table before calling here.
      * ``now``            — current time, injectable for testing.

    Heuristic scoring (max ~10):
      * +1 per line (capped at 5)
      * +2 if at least one known region is mentioned (region
            specificity)
      * +1 if report has 2+ region mentions or 3+ lines + 1 region
            (depth + specificity)
      * +1 if freshness within 24h
      * -1 if stale (older than 24h)
      * +1 if any line contains a proper-noun-shaped capitalized
            multi-word token (e.g. "Tarkin's Garrison", "Vigo Sethel
            Vask") — proxy for actionability

    Score → tier mapping:
      * >= 7  → high
      * >= 4  → medium
      * else  → low

    Returns:
      ``{"quality": "low|medium|high", "score": int, "region_slug": str|None}``

    ``region_slug`` is the first known region mentioned in the report,
    or None if no known region is mentioned. The handler uses this to
    decide which region the influence delta lands in. If the report
    mentions no known region, influence is zero regardless of score —
    intel must "describe" a region to convert to influence in that
    region.
    """
    if now is None:
        now = time.time()
    if not report:
        return {"quality": "low", "score": 0, "region_slug": None}

    lines = report.get("lines", []) or []
    text_blob = " ".join(lines)

    score = 0

    # Line count contribution (cap at 5)
    score += min(len(lines), 5)

    # Region mentions
    mentioned = _extract_mentioned_regions(text_blob, known_regions)
    if mentioned:
        score += 2
        if len(mentioned) >= 2 or (len(mentioned) >= 1 and len(lines) >= 3):
            score += 1

    # Freshness
    created = float(report.get("created_at", 0) or 0)
    if created > 0:
        age = now - created
        if age <= _FRESHNESS_WINDOW_SECS:
            score += 1
        elif age > _FRESHNESS_WINDOW_SECS * 3:  # older than 3 days
            score -= 1

    # Proper-noun detection: look for capitalized multi-word tokens
    # (rough actionability proxy). Skips line-start single-word
    # capitalization since "The" / "A" / etc. at line start aren't
    # signal.
    for line in lines:
        # Two-or-more consecutive capitalized words
        if re.search(r"\b[A-Z][a-z]+(?:[ '\-][A-Z][a-z]+)+", line):
            score += 1
            break

    # Clamp + classify
    score = max(0, score)
    if score >= _HIGH_SCORE_MIN:
        quality = "high"
    elif score >= _MEDIUM_SCORE_MIN:
        quality = "medium"
    else:
        quality = "low"

    region_slug = mentioned[0] if mentioned else None
    return {
        "quality":     quality,
        "score":       score,
        "region_slug": region_slug,
    }


# ── Reward sampling ──────────────────────────────────────────────────────────

def sample_intel_reward(quality: str,
                         rng: Optional[random.Random] = None) -> tuple[int, int]:
    """Return (influence, credits) sampled uniformly from the quality tier.

    ``rng`` is injectable for deterministic testing. Unknown quality
    falls back to ``low``.
    """
    if rng is None:
        rng = random
    tier = _QUALITY_TIERS.get(quality) or _QUALITY_TIERS["low"]
    min_inf, max_inf, min_cr, max_cr = tier
    influence = rng.randint(min_inf, max_inf)
    credits   = rng.randint(min_cr, max_cr)
    return (influence, credits)


# ── Handler NPC resolution ───────────────────────────────────────────────────

def _is_handler_npc(npc_row: dict, expected_faction: Optional[str] = None) -> bool:
    """Return True if this NPC is an intel handler, optionally
    matching the given faction code.

    Handler NPCs are tagged in ai_config_json:
      ``{"is_intel_handler": true, "faction": "<faction_code>"}``

    A handler with no explicit faction tag is treated as
    independent (accepts intel from any faction — useful for
    information-broker NPCs on the criminal underworld).
    """
    if not npc_row:
        return False
    ai_raw = npc_row.get("ai_config_json") or "{}"
    if isinstance(ai_raw, str):
        try:
            ai = json.loads(ai_raw)
        except Exception:
            return False
    else:
        ai = ai_raw or {}
    if not ai.get(INTEL_HANDLER_AI_KEY):
        return False
    if expected_faction is None:
        return True
    handler_faction = (ai.get("faction") or "").strip().lower()
    # Independent handlers (no faction tag) accept anyone.
    if not handler_faction or handler_faction == "independent":
        return True
    return handler_faction == expected_faction.strip().lower()


async def find_handler_in_room(db, room_id: int,
                                 char_faction: str) -> Optional[dict]:
    """Find an intel handler NPC in the room that accepts the
    character's faction. Returns the NPC row, or None.
    """
    try:
        rows = await db.fetchall(
            "SELECT id, name, room_id, ai_config_json FROM npcs "
            "WHERE room_id = ?",
            (room_id,))
    except Exception:
        log.warning("find_handler_in_room: NPC query failed",
                    exc_info=True)
        return None
    for r in rows:
        npc = dict(r)
        if _is_handler_npc(npc, expected_faction=char_faction):
            return npc
    return None


# ── Known regions lookup ─────────────────────────────────────────────────────

async def _get_known_region_slugs(db) -> set[str]:
    """Return the set of wilderness region slugs known to the world.

    Resolved from the rooms table — any room with a non-null
    wilderness_region_id contributes its slug. Empty result is
    valid (a freshly-bootstrapped DB with no wilderness rooms).
    """
    try:
        rows = await db.fetchall(
            "SELECT DISTINCT wilderness_region_id FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL "
            "  AND wilderness_region_id != ''")
    except Exception:
        log.warning("_get_known_region_slugs: query failed", exc_info=True)
        return set()
    return {r["wilderness_region_id"] for r in rows if r.get("wilderness_region_id")}


async def _resolve_region_zone(db, region_slug: str) -> Optional[int]:
    """Return the parent zone_id for a region slug, or None."""
    if not region_slug:
        return None
    try:
        rows = await db.fetchall(
            "SELECT DISTINCT zone_id FROM rooms "
            "WHERE wilderness_region_id = ? AND zone_id IS NOT NULL "
            "LIMIT 1",
            (region_slug,))
    except Exception:
        return None
    return rows[0]["zone_id"] if rows else None


# ── Handover entry point ─────────────────────────────────────────────────────

async def handover_intel(db, char: dict, handler_npc_id: int,
                          report_id: int, *,
                          session_mgr=None,
                          pay_mult: Optional[float] = None,
                          rng: Optional[random.Random] = None) -> dict:
    """Convert a sealed intel report into credits + influence via a
    faction handler NPC.

    Validation order (each short-circuits with an actionable error):
      1. Character has a faction membership.
      2. Handler NPC exists, is in the same room as the character, is
         tagged as an intel handler, and accepts the character's
         faction.
      3. Character holds the report id.
      4. Report is sealed (drafts can't be handed over).
      5. Report is not expired.

    On success:
      * Report is removed from the character's holdings.
      * Quality is classified via ``evaluate_intel_quality``.
      * Credits + influence are sampled within the tier range.
      * Credits are credited via ``db.save_character`` (in-memory char
        dict also patched so the caller sees the new balance).
      * Influence is granted ONLY if the report describes a known
        wilderness region. The influence delta routes through
        ``engine.territory.adjust_territory_influence(..., region_slug=...)``
        so SYN.3 contest multipliers fire.

    Returns a dict:
      ``{
            "ok": bool,
            "msg": str,                  # for player feedback
            "quality": "low|medium|high",  # only when ok
            "credits": int,              # only when ok
            "influence": int,            # only when ok (0 if no
                                         # known region mentioned)
            "region_slug": str | None,   # the region the influence
                                         # landed in, or None
         }``
    """
    # ── 1. Faction membership ────────────────────────────────────
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return {"ok": False,
                "msg": "Only members of a faction can hand over intel."}

    # ── 2. Handler lookup ────────────────────────────────────────
    try:
        handler = await db.get_npc(handler_npc_id)
    except Exception:
        handler = None
    if not handler:
        return {"ok": False, "msg": "No such handler here."}
    # Same-room check
    char_room = char.get("room_id")
    if char_room is not None and handler.get("room_id") != char_room:
        return {"ok": False, "msg": "That handler isn't here."}
    if not _is_handler_npc(handler, expected_faction=faction_code):
        return {"ok": False,
                "msg": (
                    f"{handler.get('name', 'They')} doesn't handle "
                    f"intel for your faction.")}

    # ── 3. Holdings + 4. sealed + 5. expiry ──────────────────────
    from engine.espionage import get_intel_reports, _set_intel_reports
    reports = get_intel_reports(char)
    target_report = None
    remaining: list[dict] = []
    for r in reports:
        if r.get("id") == report_id:
            target_report = r
        else:
            remaining.append(r)
    if target_report is None:
        return {"ok": False,
                "msg": f"You don't have intel report #{report_id}."}
    if not target_report.get("sealed"):
        return {"ok": False,
                "msg": "That report is still a draft. Seal it first."}
    if time.time() > float(target_report.get("expires_at", 0) or 0):
        return {"ok": False,
                "msg": "That intel has expired — handlers won't take stale reports."}

    # ── Evaluate + sample reward ─────────────────────────────────
    known_regions = await _get_known_region_slugs(db)
    evaluation = evaluate_intel_quality(target_report, known_regions)
    quality = evaluation["quality"]
    region_slug = evaluation["region_slug"]
    influence, credits = sample_intel_reward(quality, rng=rng)

    # ── A3: INTELLIGENCE_THAW boosts the CREDIT payout while active ───
    # (the spy playstyle's "holiday"). A caller may inject the multiplier;
    # otherwise read the live world-event effect defensively. Influence is
    # left unscaled — the thaw is an income opportunity, not a territory lever.
    base_credits = credits
    if pay_mult is None:
        try:
            from engine.world_events import get_world_event_manager
            pay_mult = get_world_event_manager().get_effect(
                INTEL_THAW_EFFECT_KEY, 1.0)
        except Exception:
            pay_mult = 1.0
    credits = apply_intel_thaw(credits, pay_mult)
    thaw_active = credits > base_credits

    # ── Remove the report from the giver's holdings ──────────────
    _set_intel_reports(char, remaining)
    # Persist the holdings change to DB.
    try:
        await db.save_character(char["id"], attributes=char["attributes"])
    except Exception:
        log.warning(
            "[intel_handlers] failed to persist intel-holdings update "
            "for char %s", char.get("id"), exc_info=True,
        )

    # ── Credit award ─────────────────────────────────────────────
    try:
        char["credits"] = await db.adjust_credits(char["id"], credits, "intel_handover")
    except Exception:
        log.warning(
            "[intel_handlers] credit award failed for char %s",
            char.get("id"), exc_info=True,
        )

    # ── Influence delta — wilderness regions only ────────────────
    influence_applied = 0
    if region_slug:
        zone_id = await _resolve_region_zone(db, region_slug)
        if zone_id is not None:
            try:
                from engine.territory import adjust_territory_influence
                await adjust_territory_influence(
                    db, faction_code, zone_id, influence,
                    reason=(
                        f"intel handover by {char.get('name', '?')} "
                        f"[{quality}] re: {region_slug}"),
                    region_slug=region_slug,
                )
                influence_applied = influence
            except Exception:
                log.warning(
                    "[intel_handlers] influence delta failed for "
                    "char %s region %s", char.get("id"), region_slug,
                    exc_info=True,
                )
    else:
        # Intel didn't describe any known wilderness region. The
        # credits still pay out (handlers value any intel a little),
        # but no influence change.
        influence = 0

    log.info(
        "[intel_handlers] handover: char %s gave report #%s "
        "(quality=%s, score=%s, region=%s) for %s cr + %s inf",
        char.get("id"), report_id, quality, evaluation["score"],
        region_slug, credits, influence_applied,
    )

    # Player feedback message
    region_msg = (f" in {region_slug}" if region_slug
                  else " (no specific region — no influence delta)")
    msg_parts = [
        f"Handler accepts your intel — {quality.upper()} quality "
        f"(+{credits} cr"
    ]
    if influence_applied:
        msg_parts.append(f", +{influence_applied} influence{region_msg}")
    else:
        msg_parts.append(region_msg)
    msg_parts.append(").")
    msg = "".join(msg_parts).replace("(no specific region", " — no specific region")
    if thaw_active:
        msg += "  (Intelligence Thaw: double rates!)"

    return {
        "ok":          True,
        "msg":         msg,
        "quality":     quality,
        "credits":     credits,
        "influence":   influence_applied,
        "region_slug": region_slug,
    }


__all__ = [
    # Constants
    "INTEL_QUALITY_LOW",
    "INTEL_QUALITY_MEDIUM",
    "INTEL_QUALITY_HIGH",
    "INTEL_HANDLER_AI_KEY",
    "INTEL_THAW_EFFECT_KEY",
    # Pure rules
    "evaluate_intel_quality",
    "sample_intel_reward",
    "apply_intel_thaw",
    # DB-touching
    "find_handler_in_room",
    "handover_intel",
]
