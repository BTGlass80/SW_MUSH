# -*- coding: utf-8 -*-
"""
engine/territory_display.py — Region-look render block (SYN.10,
2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.6 + §3.12.

The "region look block" is the body of information rendered when a
character looks at (or queries) a wilderness region. It contains:

  - Region header (name, planet, security tag)
  - Region long description (from YAML)
  - Ownership line (org name + foothold/dominant tier)
  - Influence breakdown (top 3 orgs with progress bars)
  - Weekly resource quality outlook (top vs worst multiplier)
  - Active contest panel (if a contest is in progress)

Two public entry points:

  ``get_region_look_block(db, region_slug, *, viewing_org_code=None,
                          ansi=True)`` — returns a list of pre-formatted
  text lines for direct CLI output. ANSI escape sequences included
  when ``ansi=True``.

  ``get_region_data_block(db, region_slug)`` — returns the same
  information as a structured dict for non-CLI consumers (web
  HUD, REST API, future UI work). Web-first design call: the data
  shape is stable; the CLI renderer just formats it.

UI-pivot note (2026-05-25): the structured dict from
``get_region_data_block`` is the contract for the upcoming web UI
work. New fields can be added; existing fields should not be
renamed or removed without coordination.

All functions are read-only — pure rendering, no state mutation.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── ANSI palette ─────────────────────────────────────────────────────────────
# All color literals centralized here so the UI pivot can swap them
# without searching the render functions. CLI uses these strings; the
# data dict uses semantic tag names (e.g. "security_lawless") that the
# UI can map to its own theme.

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_ITALIC = "\033[3m"

_RED = "\033[1;31m"      # lawless / threat
_YELLOW = "\033[1;33m"   # contested / warning
_GREEN = "\033[1;32m"    # secured / success
_CYAN = "\033[1;36m"     # accent / heading
_MAGENTA = "\033[1;35m"  # contest panel
_BLUE = "\033[1;34m"     # neutral data

# Influence-tier label (mirrors engine.territory thresholds):
TIER_LABELS = {
    "foothold": "FOOTHOLD",
    "dominant": "DOMINANT",
    "no_presence": "no presence",
}


def _security_tag(security: str, ansi: bool = True) -> str:
    """Render the security tag (LAWLESS/CONTESTED/SECURED)."""
    if not security:
        return ""
    sec_upper = security.upper()
    if not ansi:
        return f"[{sec_upper}]"
    color = {
        "LAWLESS": _RED,
        "CONTESTED": _YELLOW,
        "SECURED": _GREEN,
    }.get(sec_upper, "")
    if color:
        return f"{color}[{sec_upper}]{_RESET}"
    return f"[{sec_upper}]"


def _influence_bar(score: int, width: int = 20) -> str:
    """Render a width-N progress bar for an influence score (0-150).

    Foothold threshold is 50; dominant is 100. Bar fills proportionally.
    """
    if score < 0:
        score = 0
    if score > 150:
        score = 150
    filled = int((score / 150.0) * width)
    return ("█" * filled) + ("░" * (width - filled))


def _influence_tier(score: int) -> str:
    """Return the threshold label for an influence score."""
    if score >= 100:
        return "dominant"
    if score >= 50:
        return "foothold"
    return "no_presence"


def _format_secs_short(secs: float) -> str:
    """Format seconds as e.g. '3d 14h 22m'. Used for contest
    countdowns."""
    if secs is None or secs <= 0:
        return "0m"
    s = int(secs)
    days = s // 86400
    s -= days * 86400
    hours = s // 3600
    s -= hours * 3600
    mins = s // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


# ── Data accessor (web-first) ────────────────────────────────────────────────

async def get_region_data_block(
    db, region_slug: str,
) -> dict:
    """Read the region's full state and return a structured dict.

    UI pivot: this is the canonical data contract. Stable shape:

        {
          "region_slug": str,
          "region_name": str,             # human-readable from YAML
          "planet": str | None,           # if known
          "security": str,                # 'lawless' | 'contested' | 'secured'
          "description": str | None,      # long_desc from YAML
          "ownership": {
            "org_code": str | None,
            "org_name": str | None,
            "tier": str,                  # 'foothold' | 'dominant'
            "claimed_at": float | None,
          } | None,
          "influence": [                  # sorted by score desc
            {"org_code": str, "score": int, "tier": str},
            ...
          ],
          "resource_outlook": {
            "best": {"type": str, "multiplier": float} | None,
            "worst": {"type": str, "multiplier": float} | None,
            "all": {type: multiplier, ...},
          },
          "active_contest": {
            "challenger_org": str,
            "defender_org": str | None,
            "phase": str,
            "secs_remaining": float,
            "accumulation": {org_code: score},
          } | None,
        }

    Read-only. Best-effort: any per-section failure returns the
    section as None or empty rather than raising.
    """
    out = {
        "region_slug": region_slug,
        "region_name": _humanize_slug(region_slug),
        "planet": None,
        "security": "lawless",
        "description": None,
        "ownership": None,
        "influence": [],
        "resource_outlook": {"best": None, "worst": None, "all": {}},
        "active_contest": None,
    }

    # Region YAML metadata (region_name, planet, description).
    try:
        rows = await db.fetchall(
            "SELECT name, planet, region_description, security "
            "FROM wilderness_regions WHERE slug = ?",
            (region_slug,),
        )
        if rows:
            r = dict(rows[0])
            if r.get("name"):
                out["region_name"] = r["name"]
            if r.get("planet"):
                out["planet"] = r["planet"]
            if r.get("region_description"):
                out["description"] = r["region_description"]
            if r.get("security"):
                out["security"] = r["security"]
    except Exception:
        # wilderness_regions table may not exist in test harnesses —
        # fall back to the slug-humanized name we already set.
        log.debug("[territory_display] wilderness_regions lookup skipped",
                  exc_info=True)

    # Ownership.
    try:
        from engine.territory import get_region_owner, get_territory_influence
        owner = await get_region_owner(db, region_slug)
        if owner:
            org_code = owner.get("org_code")
            zone_id_for_owner = owner.get("zone_id")
            owner_score = 0
            if zone_id_for_owner is not None and org_code:
                try:
                    owner_score = await get_territory_influence(
                        db, org_code, int(zone_id_for_owner),
                    )
                except Exception:
                    owner_score = 0
            out["ownership"] = {
                "org_code": org_code,
                "org_name": await _resolve_org_name(db, org_code),
                "tier": _influence_tier(int(owner_score or 0)),
                "claimed_at": owner.get("claimed_at"),
            }
    except Exception:
        log.debug("[territory_display] ownership lookup failed",
                  exc_info=True)

    # Influence breakdown (per zone — region anchored to its zone).
    try:
        zone_id = await _resolve_region_zone(db, region_slug)
        if zone_id is not None:
            from engine.territory import get_zone_territory_all
            scores = await get_zone_territory_all(db, zone_id)
            influence_list = []
            for org_code, score in (scores or {}).items():
                influence_list.append({
                    "org_code": org_code,
                    "score": int(score),
                    "tier": _influence_tier(int(score)),
                })
            # Sort highest-first.
            influence_list.sort(key=lambda x: -x["score"])
            out["influence"] = influence_list
    except Exception:
        log.debug("[territory_display] influence lookup failed",
                  exc_info=True)

    # Resource outlook (current week's region_quality).
    try:
        from engine.region_quality import get_region_quality_for
        from engine.region_quality import _outlook_summary
        # Single-region outlook: fetch rows from region_quality for
        # this slug and pass to _outlook_summary.
        rows = await db.fetchall(
            "SELECT region_slug, resource_type, quality_multiplier "
            "FROM region_quality WHERE region_slug = ?",
            (region_slug,),
        )
        if rows:
            outlook = _outlook_summary([dict(r) for r in rows])
            region_outlook = outlook.get(region_slug, {})
            if region_outlook:
                best = region_outlook.get("best")
                worst = region_outlook.get("worst")
                if best:
                    out["resource_outlook"]["best"] = {
                        "type": best[0], "multiplier": float(best[1]),
                    }
                if worst:
                    out["resource_outlook"]["worst"] = {
                        "type": worst[0], "multiplier": float(worst[1]),
                    }
                out["resource_outlook"]["all"] = dict(
                    region_outlook.get("all", {}) or {}
                )
    except Exception:
        log.debug("[territory_display] resource outlook lookup failed",
                  exc_info=True)

    # Active contest.
    try:
        from engine.contest import get_active_region_contest
        contest = await get_active_region_contest(db, region_slug)
        if contest:
            import time as _time
            now = _time.time()
            # Real schema: started_at + ends_at columns. Time remaining
            # is ends_at - now. Accumulation falls back to zone influence
            # (the canonical source the contest tick reads).
            ends_at = float(contest.get("ends_at", 0) or 0)
            secs_remaining = (
                max(0.0, ends_at - now) if ends_at else 0.0
            )
            accumulation = {}
            if out["influence"]:
                for ent in out["influence"]:
                    accumulation[ent["org_code"]] = ent["score"]

            out["active_contest"] = {
                "challenger_org": contest.get("challenger_org_code"),
                "defender_org": contest.get("defender_org_code"),
                "phase": contest.get("status"),
                "started_at": float(contest.get("started_at", 0) or 0),
                "ends_at": ends_at,
                "secs_remaining": secs_remaining,
                "accumulation": accumulation,
            }
    except Exception:
        log.debug("[territory_display] active contest lookup failed",
                  exc_info=True)

    return out


async def _resolve_org_name(db, org_code: Optional[str]) -> Optional[str]:
    """Look up the org's display name. Falls back to the code."""
    if not org_code:
        return None
    try:
        rows = await db.fetchall(
            "SELECT name FROM organizations WHERE code = ?",
            (org_code,),
        )
        if rows:
            return dict(rows[0]).get("name") or org_code
    except Exception:
        log.debug(
            "[territory_display] org name lookup for %s failed; "
            "falling back to code",
            org_code, exc_info=True,
        )
    return org_code


async def _resolve_region_zone(
    db, region_slug: str,
) -> Optional[int]:
    """Find the zone_id for a region. Uses the same lookup logic as
    engine.territory._get_region_zone."""
    try:
        from engine.territory import _get_region_zone
        return await _get_region_zone(db, region_slug)
    except Exception:
        return None


def _humanize_slug(slug: str) -> str:
    """Convert a slug like 'dune_sea' to 'Dune Sea'."""
    return slug.replace("_", " ").title()


# ── CLI renderer ─────────────────────────────────────────────────────────────

async def get_region_look_block(
    db, region_slug: str,
    *, viewing_org_code: Optional[str] = None, ansi: bool = True,
) -> list:
    """Render the region's full display block as a list of CLI lines.

    Per design §2.6:

        ─── The Dune Sea (Tatooine) ─── [LAWLESS]
          (long description)

          Ownership: Hutt Cartel (Foothold)
          Influence: Hutt 65 [FOOTHOLD] · Rebel 22 · Empire 8

          Resource quality this week: Metal 1.2× · Chemical 0.9× · Rare 1.3×

          ── Active contest ───────────────────────
          Rebel Alliance challenges Hutt Cartel
          Time remaining: 3d 14h 22m
          Current accumulation: Hutt 90 · Rebel 80

    ``viewing_org_code``: if provided, the renderer highlights that
    org's row in the influence breakdown (useful for the in-look
    overlay where the viewer should easily spot their own faction's
    standing).

    ``ansi=False`` strips color codes — useful for log dumps,
    test snapshots, and the data-extraction path for web-HUD
    consumers that prefer to do their own coloring.
    """
    data = await get_region_data_block(db, region_slug)

    lines = []
    bold = _BOLD if ansi else ""
    cyan = _CYAN if ansi else ""
    dim = _DIM if ansi else ""
    italic = _ITALIC if ansi else ""
    reset = _RESET if ansi else ""
    magenta = _MAGENTA if ansi else ""

    # Header line
    planet_part = f" ({data['planet']})" if data.get("planet") else ""
    sec_tag = _security_tag(data["security"], ansi=ansi)
    lines.append(
        f"{cyan}─── {data['region_name']}{planet_part} ───{reset}  {sec_tag}"
    )

    # Description (italicized, indented)
    if data.get("description"):
        lines.append(f"  {italic}{data['description']}{reset}")

    # Blank separator
    lines.append("")

    # Ownership line
    ownership = data.get("ownership")
    if ownership:
        org_name = ownership.get("org_name") or ownership.get("org_code")
        tier = ownership.get("tier") or "no_presence"
        tier_label = TIER_LABELS.get(tier, tier).title()
        lines.append(
            f"  {bold}Ownership:{reset} {org_name} ({tier_label})"
        )
    else:
        lines.append(f"  {bold}Ownership:{reset} {dim}Un-owned{reset}")

    # Influence breakdown (top 3 orgs)
    influence = data.get("influence", []) or []
    if influence:
        top3 = influence[:3]
        parts = []
        for ent in top3:
            org = ent["org_code"]
            score = ent["score"]
            tier = ent["tier"]
            # Highlight if this is the viewer's org.
            marker = ""
            if (viewing_org_code
                    and ent["org_code"] == viewing_org_code
                    and ansi):
                marker = f"{cyan}"
            tier_suffix = (
                f" [{TIER_LABELS.get(tier, tier).upper()}]"
                if tier != "no_presence" else ""
            )
            parts.append(
                f"{marker}{org} {score}{tier_suffix}{reset}"
                if marker else f"{org} {score}{tier_suffix}"
            )
        lines.append(
            f"  {bold}Influence:{reset} " + " · ".join(parts)
        )

    # Resource outlook (best + worst this week)
    outlook = data.get("resource_outlook") or {}
    if outlook.get("best") or outlook.get("worst"):
        lines.append("")
        outlook_parts = []
        if outlook.get("best"):
            b = outlook["best"]
            outlook_parts.append(
                f"{b['type'].title()} {b['multiplier']:.1f}×"
            )
        if outlook.get("worst") and (
                not outlook.get("best")
                or outlook["worst"]["type"] != outlook["best"]["type"]):
            w = outlook["worst"]
            outlook_parts.append(
                f"{w['type'].title()} {w['multiplier']:.1f}×"
            )
        if outlook_parts:
            lines.append(
                f"  {bold}Resource quality this week:{reset} "
                + " · ".join(outlook_parts)
            )

    # Active contest panel
    contest = data.get("active_contest")
    if contest:
        lines.append("")
        lines.append(
            f"  {magenta}── Active contest ───────────────────────{reset}"
        )
        challenger = contest.get("challenger_org") or "Challenger"
        defender = contest.get("defender_org") or "Un-owned"
        chal_name = await _resolve_org_name(db, challenger) or challenger
        def_name = await _resolve_org_name(db, defender) or defender
        lines.append(f"  {chal_name} challenges {def_name}")
        secs = contest.get("secs_remaining", 0) or 0
        if secs > 0:
            lines.append(
                f"  Time remaining: {_format_secs_short(secs)}"
            )
        # Accumulation: top contestants by score.
        accum = contest.get("accumulation") or {}
        if accum:
            ranked = sorted(accum.items(), key=lambda kv: -kv[1])
            top = ranked[:3]
            accum_parts = [
                f"{org} {score}" for (org, score) in top
            ]
            lines.append(
                f"  Current accumulation: " + " · ".join(accum_parts)
            )

    return lines


# ── Faction-scoped renderers (for +faction contest / resource_outlook) ──────

async def get_faction_contests_lines(
    db, org_code: str, *, ansi: bool = True,
) -> list:
    """Render all active contests involving this org.

    Per design §2.6: ``+faction contest`` shows active contests
    (defender + challenger, time remaining, accumulation).
    Includes contests where this org is the *challenger* AND
    contests where this org is the *defender*.

    UI pivot: data shape returned by ``get_faction_contests_data``
    below — these CLI lines are derived from it.
    """
    data = await get_faction_contests_data(db, org_code)

    lines = []
    cyan = _CYAN if ansi else ""
    bold = _BOLD if ansi else ""
    dim = _DIM if ansi else ""
    reset = _RESET if ansi else ""

    org_name = await _resolve_org_name(db, org_code) or org_code
    lines.append(
        f"{cyan}── Active Contests: {org_name} ──{reset}"
    )

    if not data["contests"]:
        lines.append(
            f"  {dim}(No active contests involving your faction.)"
            f"{reset}"
        )
        return lines

    for entry in data["contests"]:
        region = entry["region_name"]
        role = entry["role"]
        opponent = entry["opponent_name"] or entry["opponent_code"]
        secs = entry["secs_remaining"]
        time_str = _format_secs_short(secs) if secs else "0m"
        lines.append("")
        lines.append(
            f"  {bold}{region}{reset} — "
            f"{('You challenge' if role == 'challenger' else 'You defend against')} "
            f"{opponent} — {time_str} remaining"
        )
        if entry.get("accumulation"):
            ranked = sorted(
                entry["accumulation"].items(), key=lambda kv: -kv[1],
            )
            top = ranked[:3]
            parts = [f"{org} {score}" for (org, score) in top]
            lines.append(
                f"    {dim}Accumulation:{reset} " + " · ".join(parts)
            )

    return lines


async def get_faction_contests_data(
    db, org_code: str,
) -> dict:
    """Structured data for the faction-contests command.

    Returns:
        {
          "org_code": str,
          "contests": [
            {
              "region_slug": str,
              "region_name": str,
              "role": "challenger" | "defender",
              "opponent_code": str,
              "opponent_name": str,
              "phase": str,
              "secs_remaining": float,
              "accumulation": {org_code: score},
            },
            ...
          ]
        }
    """
    out = {"org_code": org_code, "contests": []}

    try:
        from engine.contest import get_org_region_contests
        contests = await get_org_region_contests(db, org_code) or []
    except Exception:
        log.debug("[territory_display] get_org_region_contests failed",
                  exc_info=True)
        contests = []

    # get_org_region_contests already returns both challenger AND
    # defender contests (filtered by WHERE defender_org_code = ? OR
    # challenger_org_code = ?), so no separate fallback fetch needed.
    import time as _time
    now = _time.time()

    for c in contests:
        slug = c.get("region_slug") or ""
        challenger_org = c.get("challenger_org_code") or ""
        defender_org = c.get("defender_org_code")

        # Determine role from the row itself (real schema has explicit
        # challenger_org_code and defender_org_code).
        if challenger_org == org_code:
            role = "challenger"
            opponent_code = defender_org
        elif defender_org == org_code:
            role = "defender"
            opponent_code = challenger_org
        else:
            # Edge case — not our contest at all. Skip.
            continue

        # Time remaining = ends_at - now.
        ends_at = float(c.get("ends_at", 0) or 0)
        secs_remaining = (
            max(0.0, ends_at - now) if ends_at else 0.0
        )

        # Accumulation from zone influence.
        accumulation = {}
        try:
            zone_id = await _resolve_region_zone(db, slug)
            if zone_id is not None:
                from engine.territory import get_zone_territory_all
                scores = await get_zone_territory_all(db, zone_id) or {}
                for k, v in scores.items():
                    accumulation[k] = int(v)
        except Exception:
            log.debug(
                "[territory_display] zone-territory aggregation for "
                "region %s failed; rendering with empty accumulation",
                slug, exc_info=True,
            )

        out["contests"].append({
            "region_slug": slug,
            "region_name": _humanize_slug(slug),
            "role": role,
            "opponent_code": opponent_code,
            "opponent_name": (
                await _resolve_org_name(db, opponent_code)
            ) if opponent_code else None,
            "phase": c.get("status"),
            "secs_remaining": secs_remaining,
            "accumulation": accumulation,
        })

    return out


async def get_faction_resource_outlook_lines(
    db, org_code: str, *, ansi: bool = True,
) -> list:
    """Render the weekly resource quality outlook for regions owned
    by this org.

    Per design §2.6: ``+faction resource_outlook`` shows weekly
    region quality digests.

    UI pivot: data shape returned by
    ``get_faction_resource_outlook_data``.
    """
    data = await get_faction_resource_outlook_data(db, org_code)

    lines = []
    cyan = _CYAN if ansi else ""
    bold = _BOLD if ansi else ""
    dim = _DIM if ansi else ""
    reset = _RESET if ansi else ""

    org_name = await _resolve_org_name(db, org_code) or org_code
    lines.append(
        f"{cyan}── Weekly Resource Outlook: {org_name} ──{reset}"
    )

    if not data["regions"]:
        lines.append(
            f"  {dim}(Your faction owns no wilderness regions this "
            f"week.){reset}"
        )
        return lines

    for entry in data["regions"]:
        region = entry["region_name"]
        best = entry.get("best")
        worst = entry.get("worst")
        lines.append("")
        lines.append(f"  {bold}{region}{reset}")
        if best:
            lines.append(
                f"    Best: {best['type'].title()} "
                f"{best['multiplier']:.2f}×"
            )
        if worst and (not best or worst["type"] != best["type"]):
            lines.append(
                f"    Worst: {worst['type'].title()} "
                f"{worst['multiplier']:.2f}×"
            )
        # All multipliers, compact.
        all_mults = entry.get("all") or {}
        if all_mults:
            compact = " · ".join(
                f"{t.title()} {m:.2f}×"
                for (t, m) in sorted(all_mults.items())
            )
            lines.append(f"    {dim}All:{reset} {compact}")

    return lines


async def get_faction_resource_outlook_data(
    db, org_code: str,
) -> dict:
    """Structured data for +faction resource_outlook.

    Returns:
        {
          "org_code": str,
          "regions": [
            {
              "region_slug": str,
              "region_name": str,
              "best": {"type": str, "multiplier": float} | None,
              "worst": {"type": str, "multiplier": float} | None,
              "all": {type: multiplier, ...},
            },
            ...
          ]
        }
    """
    out = {"org_code": org_code, "regions": []}
    try:
        from engine.region_quality import get_outlook
        outlook = await get_outlook(db, org_code=org_code)
    except Exception:
        log.debug("[territory_display] get_outlook failed",
                  exc_info=True)
        outlook = {}

    for slug, region_outlook in (outlook or {}).items():
        entry = {
            "region_slug": slug,
            "region_name": _humanize_slug(slug),
            "best": None,
            "worst": None,
            "all": {},
        }
        best = region_outlook.get("best")
        worst = region_outlook.get("worst")
        if best:
            entry["best"] = {
                "type": best[0], "multiplier": float(best[1]),
            }
        if worst:
            entry["worst"] = {
                "type": worst[0], "multiplier": float(worst[1]),
            }
        entry["all"] = dict(region_outlook.get("all", {}) or {})
        out["regions"].append(entry)

    # Sort regions alphabetically by name for stable display.
    out["regions"].sort(key=lambda r: r["region_name"])

    return out


# ── News digest helpers ──────────────────────────────────────────────────────
#
# Per design §2.6, news digest expansions cover: ownership change,
# contest start/resolve, anomaly spawn/defeat, building completion/
# demolition. These helpers compose the news text consistently;
# the actual broadcast call lives in the originating engine (e.g.
# territory.claim_region calls broadcast_ownership_change_news).

def format_ownership_change_news(
    region_slug: str, *, org_name: str, action: str = "claimed",
) -> str:
    """Format the news text for a region ownership change.

    ``action`` ∈ {'claimed', 'lost', 'unclaimed'}.
    """
    region = _humanize_slug(region_slug)
    if action == "claimed":
        return f"{org_name} has claimed {region}."
    if action == "lost":
        return f"{org_name} has lost their hold on {region}."
    if action == "unclaimed":
        return f"{org_name} has relinquished {region}."
    return f"{region} ownership has changed."


def format_contest_start_news(
    region_slug: str, *, challenger_name: str,
    defender_name: Optional[str] = None,
) -> str:
    """Format the news text for a contest declaration."""
    region = _humanize_slug(region_slug)
    if defender_name:
        return (
            f"{challenger_name} has challenged {defender_name} for "
            f"control of {region}!"
        )
    return f"{challenger_name} contests the un-owned {region}!"


def format_contest_resolve_news(
    region_slug: str, *, victor_name: str, defender_won: bool,
) -> str:
    """Format the news text for a contest resolution."""
    region = _humanize_slug(region_slug)
    if defender_won:
        return (
            f"{victor_name} has held {region} against the challenger."
        )
    return f"{victor_name} has prevailed in the contest for {region}."


def format_anomaly_defeat_news(
    region_slug: str, *, anomaly_name: str, killer_org: Optional[str] = None,
) -> str:
    """Format the news text for an anomaly defeat."""
    region = _humanize_slug(region_slug)
    if killer_org:
        return (
            f"The {anomaly_name} in {region} has been put down by "
            f"{killer_org}."
        )
    return f"The {anomaly_name} in {region} has been put down."


def format_building_completion_news(
    region_slug: str, *, building_category: str, owner_name: str,
) -> str:
    """Format the news text for a building completion."""
    region = _humanize_slug(region_slug)
    return (
        f"A {building_category.replace('_', ' ')} has been "
        f"completed by {owner_name} in {region}."
    )


def format_building_demolition_news(
    region_slug: str, *, building_category: str,
    reason: str = "demolished",
) -> str:
    """Format the news text for a building demolition / eviction.

    ``reason`` ∈ {'demolished', 'evicted'}.
    """
    region = _humanize_slug(region_slug)
    verb = "demolished" if reason == "demolished" else "removed by eviction"
    return (
        f"A {building_category.replace('_', ' ')} in {region} has "
        f"been {verb}."
    )
