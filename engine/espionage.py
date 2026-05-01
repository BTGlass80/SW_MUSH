# -*- coding: utf-8 -*-
"""
engine/espionage.py — Espionage System for SW_MUSH.

Provides the mechanical backend for the espionage command suite:
  - scan: covert character assessment (Perception vs Con)
  - eavesdrop: listen to adjacent room conversations
  - investigate: search room for hidden information
  - +intel: compose and trade intelligence reports

Design source: competitive_analysis_feature_designs_v1.md §F
"""

from __future__ import annotations
import json
import logging
import random
import re
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Scan Results ──────────────────────────────────────────────────────────────

_DEMEANORS = [
    "calm and collected", "nervous, glancing around frequently",
    "relaxed, leaning against the wall", "tense, hand near weapon",
    "bored, picking at their nails", "alert, watching everyone",
    "distracted, staring into space", "confident, almost cocky",
    "wary, positioned near the exit", "quiet, observing intently",
]


def generate_scan_result(
    scanner: dict, target: dict, margin: int,
) -> list[str]:
    """Generate scan result lines based on skill check margin.

    Args:
        scanner: Scanner's character dict.
        target: Target's character dict.
        margin: Skill check margin (roll - difficulty). Higher = more detail.

    Returns:
        List of formatted result lines.
    """
    name = target.get("name", "Unknown")
    wound = target.get("wound_level", 0)

    # Wound descriptions
    wound_descs = {
        0: "Healthy — no visible injuries",
        1: "Slightly dazed, recovering from a stun",
        2: "Wounded — favoring their left side",
        3: "Seriously wounded — multiple injuries visible",
        4: "Badly hurt — barely standing",
        5: "Critically injured — shouldn't be on their feet",
    }
    condition = wound_descs.get(wound, "Healthy")

    # Equipped weapon
    weapon = target.get("equipped_weapon", "")
    armed = f"Yes ({weapon.replace('_', ' ').title()})" if weapon else "Unarmed"

    demeanor = random.choice(_DEMEANORS)
    species = target.get("species", "Unknown")

    lines = [f"  \033[1;36mYou discreetly size up {name}.\033[0m"]

    # Basic info (margin 0+)
    lines.append(f"  \033[1mCondition:\033[0m  {condition}")
    lines.append(f"  \033[1mArmed:\033[0m      {armed}")
    lines.append(f"  \033[1mDemeanor:\033[0m   {demeanor}")

    # Extended info (margin 5+)
    if margin >= 5:
        credits = target.get("credits", 0)
        if credits < 100:
            credit_desc = "Nearly broke (less than 100 credits)"
        elif credits < 1000:
            credit_desc = "Modest funds (a few hundred credits)"
        elif credits < 5000:
            credit_desc = f"Comfortable ({credits // 1000}K-{(credits // 1000) + 1}K range)"
        elif credits < 20000:
            credit_desc = f"Well-off (roughly {credits // 1000}K credits)"
        else:
            credit_desc = f"Wealthy ({credits // 1000}K+ credits)"
        lines.append(f"  \033[1mCredits:\033[0m    {credit_desc}")

        faction = target.get("faction", "")
        if faction and faction != "independent":
            lines.append(
                f"  \033[1mFaction:\033[0m    Likely {faction.replace('_', ' ').title()} "
                f"affiliated"
            )

        # Check for armor
        armor = target.get("worn_armor", "")
        if armor:
            lines.append(
                f"  \033[1mArmor:\033[0m      {armor.replace('_', ' ').title()}"
            )

    # Deep insight (margin 10+)
    if margin >= 10:
        lines.append(
            f"  \033[1mSpecies:\033[0m    {species}"
        )
        # Check for scars
        try:
            attrs = target.get("attributes", "{}")
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            scars = attrs.get("scars", [])
            if scars:
                latest = scars[-1] if isinstance(scars[-1], dict) else {}
                scar_desc = latest.get("description", "visible scarring")
                lines.append(f"  \033[1mNotable:\033[0m    {scar_desc[:60]}")
        except Exception as _e:
            log.debug("silent except in engine/espionage.py:121: %s", _e, exc_info=True)

    return lines


# ── Eavesdrop ─────────────────────────────────────────────────────────────────

# Active eavesdrop sessions: {char_id: {target_room_id, expires_at}}
_eavesdrop_sessions: dict[int, dict] = {}

EAVESDROP_DURATION = 300  # 5 minutes


def start_eavesdrop(char_id: int, target_room_id: int) -> None:
    """Register an active eavesdrop session."""
    _eavesdrop_sessions[char_id] = {
        "target_room_id": target_room_id,
        "expires_at": time.time() + EAVESDROP_DURATION,
    }


def stop_eavesdrop(char_id: int) -> None:
    """End an eavesdrop session."""
    _eavesdrop_sessions.pop(char_id, None)


def get_eavesdrop_target(char_id: int) -> Optional[int]:
    """Return the room_id being eavesdropped, or None if not active/expired."""
    session = _eavesdrop_sessions.get(char_id)
    if not session:
        return None
    if time.time() > session["expires_at"]:
        _eavesdrop_sessions.pop(char_id, None)
        return None
    return session["target_room_id"]


def muffle_for_eavesdrop(text: str, skill_margin: int = 0) -> str:
    """Apply muffling to overheard text. Higher margin = more clarity.

    Base: 30% word survival. +5% per margin point, max 60%.
    Quoted text always leaks through.
    """
    survival_rate = min(0.60, 0.30 + skill_margin * 0.05)

    parts = re.split(r'(".*?")', text)
    result = []
    for part in parts:
        if part.startswith('"') and part.endswith('"'):
            result.append(part[1:-1])
        else:
            words = part.split()
            muffled = []
            for w in words:
                if random.random() < survival_rate:
                    muffled.append(w)
                else:
                    muffled.append("...")
            result.append(" ".join(muffled))

    return " ".join(result).strip()


# ── Investigate Findings ──────────────────────────────────────────────────────

_GENERIC_FINDINGS = [
    "Scuff marks on the floor suggest heavy foot traffic recently.",
    "A faint chemical smell lingers in the air — cleaning solvents.",
    "Scratch marks near the door lock indicate amateur tampering.",
    "A crumpled flimsi in the corner — the text is too faded to read.",
    "Dust patterns suggest something heavy was moved recently.",
    "Bootprints from at least 3 individuals — military-grade soles.",
]

_SECURITY_FINDINGS = [
    "A concealed compartment behind the wall panel (Security diff 18).",
    "The door lock can be bypassed from the outside with a code slicer.",
    "Security cameras have a blind spot in the far corner.",
    "An old ventilation shaft could fit a small being.",
]

_FACTION_FINDINGS = {
    # ── GCW factions (era=gcw) ──────────────────────────────────────
    "empire": [
        "Imperial insignia scratched into the underside of a table.",
        "A coded frequency list tucked behind a wall panel — ISB standard.",
        "Boot polish residue — Imperial regulation formula.",
    ],
    "rebel": [
        "A scratched starbird symbol on the inside of a cabinet door.",
        "Alliance code cylinders hidden in a false-bottom container.",
        "Rebel recruitment flimsi concealed behind a loose tile.",
    ],
    "hutt": [
        "Hutt Cartel accounting ledger fragments — mostly credits owed.",
        "Spice residue in the cracks between floor plates.",
        "A Hutt clan tattoo sketched on the wall — recent.",
    ],
    # ── B.1.f (Apr 29 2026) — CW faction findings ───────────────────
    # Lookup is keyed by `claim.org_code` which already varies by era;
    # extending the dict keeps the lookup site (line ~242) era-agnostic
    # and additive — GCW orgs (empire/rebel/hutt) keep their pools
    # byte-identical, CW orgs (republic/cis/jedi_order/hutt_cartel/
    # bounty_hunters_guild) get era-themed clues.
    "republic": [
        "Republic seal stamped on a discarded ration tin — fresh print.",
        "An encrypted clone-trooper tactical frequency list, partially burned.",
        "Phase II armor sealant residue on the floor near the doorway.",
    ],
    "cis": [
        "A Separatist hex-pattern decal peeled from a console.",
        "Battle-droid foot-servo lubricant smeared along the wall.",
        "Confederacy currency chits hidden in a hollow chair leg.",
    ],
    "jedi_order": [
        "A meditation candle stub in a corner, recently extinguished.",
        "Faintly scorched flooring in a triangular pattern — saber katas.",
        "A scrap of Jedi-cipher flimsi tucked behind a loose panel.",
    ],
    "hutt_cartel": [
        "Cartel ledger fragments — debts owed, mostly to Black Sun.",
        "Spice residue in the cracks between floor plates.",
        "A clan-allegiance tattoo sketched on the wall — Desilijic.",
    ],
    "bounty_hunters_guild": [
        "A Guild marker etched into the lintel — territory claim.",
        "Spent slug-thrower casings of an unusual caliber.",
        "A laminated bounty puck stuffed behind a loose tile.",
    ],
}


async def generate_investigation_findings(
    db, char: dict, room: dict, margin: int,
) -> list[str]:
    """Generate investigation findings based on room state and check margin.

    Uses actual game state — territory claims, recent visitors, room properties.
    """
    findings = []
    room_id = room.get("id", 0)

    # Generic finding (always at least one on success)
    findings.append(random.choice(_GENERIC_FINDINGS))

    # Check territory claim for faction-specific findings
    if margin >= 3:
        try:
            from engine.territory import get_claim
            claim = await get_claim(db, room_id)
            if claim:
                org = claim.get("org_code", "")
                faction_finds = _FACTION_FINDINGS.get(org, [])
                if faction_finds:
                    findings.append(random.choice(faction_finds))
        except Exception as _e:
            log.debug("silent except in engine/espionage.py:245: %s", _e, exc_info=True)

    # Security vulnerability (margin 5+)
    if margin >= 5:
        findings.append(random.choice(_SECURITY_FINDINGS))

    # Check for recent visitors via action log (margin 7+)
    if margin >= 7:
        try:
            rows = await db.fetchall(
                "SELECT DISTINCT c.name, c.faction FROM pc_action_log a "
                "JOIN characters c ON c.id = a.char_id "
                "WHERE a.room_id = ? AND a.logged_at > datetime('now', '-24 hours') "
                "ORDER BY a.logged_at DESC LIMIT 5",
                (room_id,),
            )
            if rows:
                names = [r["name"] for r in rows[:3]]
                findings.append(
                    f"Signs of recent activity from: {', '.join(names)}."
                )
        except Exception as _e:
            log.debug("silent except in engine/espionage.py:267: %s", _e, exc_info=True)

    # Hazard info (margin 3+)
    if margin >= 3:
        try:
            from engine.hazards import get_room_hazard, HAZARD_TYPES
            hazard = get_room_hazard(room)
            if hazard:
                ht = HAZARD_TYPES.get(hazard["type"], {})
                findings.append(
                    f"Environmental hazard detected: {ht.get('display_name', hazard['type'])} "
                    f"(severity {hazard.get('severity', 1)})."
                )
        except Exception as _e:
            log.debug("silent except in engine/espionage.py:281: %s", _e, exc_info=True)

    return findings


# ── Intel Reports ─────────────────────────────────────────────────────────────

def get_intel_reports(char: dict) -> list[dict]:
    """Get all intel reports from character attributes."""
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        return attrs.get("intel_reports", [])
    except Exception:
        return []


def _set_intel_reports(char: dict, reports: list[dict]) -> None:
    """Write intel reports back to character attributes."""
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        attrs["intel_reports"] = reports
        char["attributes"] = json.dumps(attrs)
    except Exception as e:
        log.warning("[espionage] _set_intel_reports failed: %s", e)


def create_intel_report(char: dict, title: str) -> dict:
    """Start a new intel report. Returns {ok, msg, report_id}."""
    reports = get_intel_reports(char)

    # Check for existing draft
    for r in reports:
        if not r.get("sealed"):
            return {"ok": False, "msg": "You already have an unsealed draft. Seal or discard it first."}

    if len(reports) >= 10:
        return {"ok": False, "msg": "You can hold at most 10 intel reports. Give or discard some."}

    report = {
        "id": int(time.time() * 1000) % 1_000_000,
        "title": title[:80],
        "lines": [],
        "sealed": False,
        "created_at": time.time(),
        "expires_at": time.time() + 7 * 86400,  # 7 days
        "author": char.get("name", "Unknown"),
    }
    reports.append(report)
    _set_intel_reports(char, reports)
    return {"ok": True, "msg": f"Intel report '{title}' created. Use +intel add <text> to add content.", "report_id": report["id"]}


def add_intel_line(char: dict, text: str) -> dict:
    """Add a line to the current unsealed report."""
    reports = get_intel_reports(char)
    draft = None
    for r in reports:
        if not r.get("sealed"):
            draft = r
            break
    if not draft:
        return {"ok": False, "msg": "No open draft. Use +intel create <title> first."}

    if len(draft["lines"]) >= 20:
        return {"ok": False, "msg": "Report is full (20 lines max). Seal it with +intel seal."}

    draft["lines"].append(text[:200])
    _set_intel_reports(char, reports)
    return {"ok": True, "msg": f"Line added. ({len(draft['lines'])}/20 lines)"}


def seal_intel_report(char: dict) -> dict:
    """Seal the current draft report, making it tradeable."""
    reports = get_intel_reports(char)
    for r in reports:
        if not r.get("sealed"):
            if not r["lines"]:
                return {"ok": False, "msg": "Report is empty. Add content first."}
            r["sealed"] = True
            _set_intel_reports(char, reports)
            quality = "Basic" if len(r["lines"]) <= 2 else "Detailed" if len(r["lines"]) <= 5 else "Critical"
            return {"ok": True, "msg": f"Report '{r['title']}' sealed ({quality} quality). It can now be given to others."}
    return {"ok": False, "msg": "No unsealed draft to seal."}


def discard_intel_draft(char: dict) -> dict:
    """Discard the current unsealed draft."""
    reports = get_intel_reports(char)
    new_reports = [r for r in reports if r.get("sealed")]
    if len(new_reports) == len(reports):
        return {"ok": False, "msg": "No unsealed draft to discard."}
    _set_intel_reports(char, new_reports)
    return {"ok": True, "msg": "Draft discarded."}


def give_intel_report(giver: dict, receiver: dict, report_id: int) -> dict:
    """Transfer a sealed report to another character."""
    giver_reports = get_intel_reports(giver)
    report = None
    remaining = []
    for r in giver_reports:
        if r.get("id") == report_id and r.get("sealed"):
            report = r
        else:
            remaining.append(r)

    if not report:
        return {"ok": False, "msg": "Report not found or not sealed."}

    # Check expiry
    if time.time() > report.get("expires_at", 0):
        return {"ok": False, "msg": "That report has expired (intel goes stale after 7 days)."}

    receiver_reports = get_intel_reports(receiver)
    if len(receiver_reports) >= 10:
        return {"ok": False, "msg": f"{receiver.get('name', 'They')} can't hold more reports (max 10)."}

    receiver_reports.append(report)
    _set_intel_reports(giver, remaining)
    _set_intel_reports(receiver, receiver_reports)
    return {"ok": True, "msg": f"Report '{report['title']}' given to {receiver.get('name', 'them')}."}


def format_intel_report(report: dict) -> list[str]:
    """Format a single intel report for display."""
    B, DIM, CYAN, RST = "\033[1m", "\033[2m", "\033[1;36m", "\033[0m"
    sealed = "SEALED" if report.get("sealed") else "DRAFT"
    lines = [
        f"  {CYAN}── Intel Report: {report['title']} ──{RST}",
        f"  {B}ID:{RST} {report['id']}  {B}Status:{RST} {sealed}  "
        f"{B}Author:{RST} {report.get('author', '?')}",
    ]

    # Expiry
    remaining = report.get("expires_at", 0) - time.time()
    if remaining > 0:
        days = int(remaining // 86400)
        lines.append(f"  {DIM}Expires in {days} day(s){RST}")
    else:
        lines.append(f"  \033[1;31mEXPIRED{RST}")

    lines.append(f"  {CYAN}{'─' * 40}{RST}")
    for i, line in enumerate(report.get("lines", []), 1):
        lines.append(f"  {i:>2}. {line}")
    if not report.get("lines"):
        lines.append(f"  {DIM}(empty){RST}")
    lines.append(f"  {CYAN}{'─' * 40}{RST}")
    return lines


# ── Comlink Intercept (Tier 3 Feature #19) ───────────────────────────────
# In-memory tracking of active intercept sessions. Players with the
# `intercept` command active receive muffled versions of comlink and
# faction comms from adjacent rooms.

_intercept_sessions: dict[int, dict] = {}

INTERCEPT_DURATION = 300  # 5 minutes


def start_intercept(char_id: int, room_id: int) -> None:
    """Register an active comlink intercept session."""
    _intercept_sessions[char_id] = {
        "room_id": room_id,
        "expires_at": time.time() + INTERCEPT_DURATION,
        "intercepted_count": 0,
    }


def stop_intercept(char_id: int) -> None:
    """End a comlink intercept session."""
    _intercept_sessions.pop(char_id, None)


def get_intercept_session(char_id: int) -> Optional[dict]:
    """Return intercept session dict if active and not expired."""
    session = _intercept_sessions.get(char_id)
    if not session:
        return None
    if time.time() > session["expires_at"]:
        _intercept_sessions.pop(char_id, None)
        return None
    return session


def get_all_active_interceptors() -> list[tuple[int, dict]]:
    """Return list of (char_id, session_dict) for all active interceptors.
    Cleans up expired sessions."""
    now = time.time()
    expired = [cid for cid, s in _intercept_sessions.items()
               if now > s["expires_at"]]
    for cid in expired:
        _intercept_sessions.pop(cid, None)
    return list(_intercept_sessions.items())


def muffle_for_intercept(text: str) -> str:
    """Apply heavier muffling for intercepted comms.
    20% word survival rate — intercepted comms are fragmented."""
    survival_rate = 0.20
    words = text.split()
    muffled = []
    for w in words:
        if random.random() < survival_rate:
            muffled.append(w)
        else:
            muffled.append("...")
    return " ".join(muffled).strip()


def increment_intercept_count(char_id: int) -> None:
    """Increment the intercepted message counter."""
    session = _intercept_sessions.get(char_id)
    if session:
        session["intercepted_count"] = session.get("intercepted_count", 0) + 1
