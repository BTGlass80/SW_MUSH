# -*- coding: utf-8 -*-
"""
engine/narrative.py — PC Narrative Memory System for SW_MUSH.

Phase 1 (this file): Data collection.
  - log_action()  — write events to pc_action_log (zero AI cost)
  - +background   — player sets their own backstory
  - +recap        — shows recent actions + background (stub for AI summary)
  - Nightly summarization pipeline (Phase 2/3 — Haiku Batch API)

Action types logged:
  combat_victory   combat_defeat   mission_complete   mission_fail
  bounty_collect   smuggle_deliver smuggle_caught     craft_complete
  skill_train      planet_visit    faction_join       faction_leave
  guild_join       purchase        travel

The short_record (~200 tokens) is injected into NPC brain prompts.
The long_record (~800 tokens) is passed to Director AI faction turn.
Both are regenerated nightly from the raw action log + background.
"""

import json
import logging
import time

log = logging.getLogger(__name__)

# ── AI feature toggle ─────────────────────────────────────────────────────────
# Off by default during development. Enable via @director narrative enable
# Action *logging* is always on (zero cost, just DB writes).
# What the flag gates:
#   - short_record injection into NPC brain prompts (Mistral context)
#   - nightly summarization via Haiku Batch API (Phase 3, not yet implemented)
_narrative_ai_enabled: bool = False


def set_narrative_ai(enabled: bool) -> None:
    global _narrative_ai_enabled
    _narrative_ai_enabled = enabled
    log.info("[narrative] AI features %s", "ENABLED" if enabled else "DISABLED")


def is_narrative_ai_enabled() -> bool:
    return _narrative_ai_enabled


# ── Action type constants ──────────────────────────────────────────────────────

class ActionType:
    COMBAT_VICTORY   = "combat_victory"
    COMBAT_DEFEAT    = "combat_defeat"
    MISSION_COMPLETE = "mission_complete"
    MISSION_FAIL     = "mission_fail"
    BOUNTY_COLLECT   = "bounty_collect"
    SMUGGLE_DELIVER  = "smuggle_deliver"
    SMUGGLE_CAUGHT   = "smuggle_caught"
    CRAFT_COMPLETE   = "craft_complete"
    SKILL_TRAIN      = "skill_train"
    PLANET_VISIT     = "planet_visit"
    FACTION_JOIN     = "faction_join"
    FACTION_LEAVE    = "faction_leave"
    GUILD_JOIN       = "guild_join"
    PURCHASE         = "purchase"
    TRAVEL           = "travel"


# ── Core logging helper ────────────────────────────────────────────────────────

async def log_action(db, char_id: int, action_type: str,
                      summary: str, details: dict = None):
    """
    Write a player action to pc_action_log. Non-blocking, no AI calls.
    summary: short human-readable description (<= 120 chars ideal)
    details: optional structured data (item names, amounts, targets, etc.)
    """
    try:
        await db.log_action(
            char_id=char_id,
            action_type=action_type,
            summary=summary,
            details=json.dumps(details or {}),
        )
    except Exception as e:
        log.warning("[narrative] log_action failed for char %s: %s", char_id, e)


# ── Background text helpers ───────────────────────────────────────────────────

async def get_background(db, char_id: int) -> str:
    """Return the player-written background for a character, or empty string."""
    rec = await db.get_narrative(char_id)
    return rec["background"] if rec else ""


async def set_background(db, char_id: int, text: str) -> None:
    """Store the player-written background."""
    text = text.strip()
    if len(text) > 2000:
        text = text[:2000]
    await db.upsert_narrative(char_id, background=text)


# ── Short record injection for NPC brain ──────────────────────────────────────

async def get_short_record(db, char_id: int, char_name: str) -> str:
    """
    Return a short narrative record for injection into NPC dialogue prompts.
    Returns empty string if narrative AI is disabled (default during dev).
    """
    if not _narrative_ai_enabled:
        return ""

    rec = await db.get_narrative(char_id)
    if rec and rec.get("short_record"):
        return rec["short_record"]

    # Synthesise from raw log + background (no AI cost)
    actions = await db.get_recent_actions(char_id, limit=10)
    bg = rec["background"] if rec else ""

    parts = []
    if bg:
        parts.append(f"Background: {bg[:200]}")
    if actions:
        recent = [a["summary"] for a in actions[:5]]
        parts.append(f"Recent activity: {'; '.join(recent)}")

    if parts:
        return f"{char_name}: " + " | ".join(parts)
    return ""


# ── Recap display ─────────────────────────────────────────────────────────────

async def format_recap(db, char: dict) -> str:
    """
    Format a character recap for the +recap command.
    Shows: background, recent actions, active personal quests.
    Phase 3 will replace the actions section with an AI-generated summary.
    """
    char_id = char["id"]
    char_name = char.get("name", "Unknown")

    rec = await db.get_narrative(char_id)
    actions = await db.get_recent_actions(char_id, limit=15)
    quests = await db.get_personal_quests(char_id, status="active")

    lines = [
        "\033[1;36m══════════════════════════════════════════\033[0m",
        f"  \033[1;37mNARRATIVE RECAP — {char_name.upper()}\033[0m",
        "\033[1;36m══════════════════════════════════════════\033[0m",
    ]

    # Background
    bg = rec["background"] if rec else ""
    if bg:
        lines += [
            "  \033[1;33mBackground:\033[0m",
            f"  {bg[:400]}",
            "\033[1;36m──────────────────────────────────────────\033[0m",
        ]
    else:
        lines += [
            "  \033[2mNo background set. Use +background <text> to add yours.\033[0m",
            "\033[1;36m──────────────────────────────────────────\033[0m",
        ]

    # Recent actions
    if actions:
        lines.append("  \033[1;33mRecent Activity:\033[0m")
        for a in actions[:8]:
            ts = a.get("logged_at", "")[:10]
            lines.append(f"  \033[2m{ts}\033[0m  {a['summary']}")
    else:
        lines.append("  \033[2mNo recorded activity yet.\033[0m")

    # AI summary stub
    if rec and rec.get("long_record"):
        lines += [
            "\033[1;36m──────────────────────────────────────────\033[0m",
            "  \033[1;33mDirector Summary:\033[0m",
            f"  {rec['long_record'][:600]}",
        ]

    # Personal quests
    if quests:
        lines += [
            "\033[1;36m──────────────────────────────────────────\033[0m",
            "  \033[1;33mPersonal Quests:\033[0m",
        ]
        for q in quests:
            lines.append(f"  \033[1;35m▸\033[0m {q['title']}")
            if q.get("description"):
                lines.append(f"    \033[2m{q['description'][:100]}\033[0m")

    lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
    return "\n".join(lines)
