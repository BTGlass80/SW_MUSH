# -*- coding: utf-8 -*-
"""
engine/narrative.py — PC Narrative Memory System for SW_MUSH.

Drops delivered:
  Drop 1  Schema + +background / +recap / +quests (commands in narrative_commands.py)
  Drop 2  Action log hooks wired throughout parser/ and engine/
  Drop 3  Nightly summarization via Claude Haiku + asyncio scheduler
  Drop 6  short_record injection into npc_brain.py (gated by _narrative_ai_enabled)

Action types logged:
  combat_victory   combat_defeat   mission_complete   mission_fail
  bounty_collect   smuggle_deliver smuggle_caught     craft_complete
  skill_train      planet_visit    faction_join       faction_leave
  guild_join       purchase        travel             tutorial_complete

Two-tier records:
  short_record  (~150 words) — injected into NPC brain prompts (Mistral context)
  long_record   (~800 words) — passed to Director AI faction digest

Both regenerated nightly from raw action log + player_background via Haiku.
"""

import asyncio
import json
import logging
import time

log = logging.getLogger(__name__)

# ── AI feature toggle ─────────────────────────────────────────────────────────
_narrative_ai_enabled: bool = False


def set_narrative_ai(enabled: bool) -> None:
    global _narrative_ai_enabled
    _narrative_ai_enabled = enabled
    log.info("[narrative] AI features %s", "ENABLED" if enabled else "DISABLED")


def is_narrative_ai_enabled() -> bool:
    return _narrative_ai_enabled


# ── Action type constants ──────────────────────────────────────────────────────

class ActionType:
    COMBAT_VICTORY    = "combat_victory"
    COMBAT_DEFEAT     = "combat_defeat"
    MISSION_COMPLETE  = "mission_complete"
    MISSION_FAIL      = "mission_fail"
    BOUNTY_COLLECT    = "bounty_collect"
    SMUGGLE_DELIVER   = "smuggle_deliver"
    SMUGGLE_CAUGHT    = "smuggle_caught"
    CRAFT_COMPLETE    = "craft_complete"
    SKILL_TRAIN       = "skill_train"
    PLANET_VISIT      = "planet_visit"
    FACTION_JOIN      = "faction_join"
    FACTION_LEAVE     = "faction_leave"
    GUILD_JOIN        = "guild_join"
    PURCHASE          = "purchase"
    TRAVEL            = "travel"
    TUTORIAL_COMPLETE = "tutorial_complete"


# ── Summarization prompt ───────────────────────────────────────────────────────

_SUMMARIZATION_SYSTEM_PROMPT = """\
You are a Star Wars campaign journal keeper for a tabletop RPG set during the
Galactic Civil War. Your job is to maintain two narrative records for a player
character based on their background and recent actions.

You must respond ONLY with a valid JSON object — no preamble, no markdown
fences, no commentary. The JSON must have exactly two keys: "long_record" and
"short_record".

LONG_RECORD guidelines (max 800 words):
Update the narrative record. Preserve the player's background faithfully.
Integrate new actions into the RECENT EVENTS section (keep last 14 days,
summarize older events into the character arc). Update RELATIONSHIPS if any
NPC interactions occurred. Update SKILL TRAJECTORY if training happened.
Add or update QUEST HOOKS — note unresolved threads, emerging patterns, or
narrative opportunities the Director could act on. Write in concise,
third-person campaign-journal style.

SHORT_RECORD guidelines (max 150 words):
Distill the long record into a briefing card — what a well-connected NPC
in a cantina would know about this person. Focus on: name, species, visible
occupation, reputation, recent notable actions (last 3-5 days only), known
associates, any outstanding debts or conflicts. Do NOT include internal
motivations or quest hooks. Write as a dossier, not a story.

Respond in JSON:
{"long_record": "...", "short_record": "..."}"""


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
    rec = await db.get_narrative(char_id)
    return rec["background"] if rec else ""


async def set_background(db, char_id: int, text: str) -> None:
    text = text.strip()
    if len(text) > 2000:
        text = text[:2000]
    await db.upsert_narrative(char_id, background=text)


# ── Short record injection for NPC brain ──────────────────────────────────────

async def get_short_record(db, char_id: int, char_name: str) -> str:
    """
    Return a short narrative record for injection into NPC dialogue prompts.
    Returns empty string if narrative AI is disabled.
    Falls back to a background-only stub if no AI record exists yet.
    """
    if not _narrative_ai_enabled:
        return ""

    rec = await db.get_narrative(char_id)
    if rec and rec.get("short_record"):
        return rec["short_record"]

    # Synthesise minimal stub from raw log + background (no API cost)
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


# ── Drop 3: Single-character summarization ────────────────────────────────────

async def summarize_character(db, claude, char_row: dict) -> bool:
    """
    Run a single Haiku summarization for one character.

    char_row keys: id, name, last_summarized, background, long_record,
                   short_record, credits.
    Returns True on success, False on any failure.
    """
    char_id   = char_row["id"]
    char_name = char_row.get("name", f"char#{char_id}")
    last_ts   = char_row.get("last_summarized", "")

    new_actions = await db.get_actions_since(char_id, last_ts, limit=50)
    if not new_actions:
        return True  # Nothing new to summarize

    action_lines = []
    for a in new_actions:
        ts = a.get("logged_at", "")[:16]
        action_lines.append(f"  [{ts}] {a['action_type']}: {a['summary']}")
    action_block = "\n".join(action_lines)

    user_message = (
        f"CHARACTER BACKGROUND (player-written, preserve tone and intent):\n"
        f"{char_row.get('background', '(none set)')}\n\n"
        f"CURRENT LONG RECORD (your previous summary, may be empty):\n"
        f"{char_row.get('long_record', '(no prior record)')}\n\n"
        f"NEW ACTIONS SINCE LAST UPDATE:\n"
        f"{action_block}\n\n"
        f"CURRENT GAME STATE:\n"
        f"  Credits: {char_row.get('credits', 0)}\n"
    )

    try:
        raw = await claude.generate(
            system_prompt=_SUMMARIZATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1400,
            temperature=0.5,
        )
    except Exception as exc:
        log.warning("[narrative] Haiku call failed for %s: %s", char_name, exc)
        return False

    if not raw:
        log.warning("[narrative] Empty Haiku response for %s", char_name)
        return False

    # Parse JSON — strip markdown fences if present
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(clean)
        long_record  = str(data.get("long_record",  "")).strip()
        short_record = str(data.get("short_record", "")).strip()
    except (json.JSONDecodeError, KeyError) as exc:
        log.warning("[narrative] JSON parse failed for %s: %s — raw: %s",
                    char_name, exc, raw[:200])
        return False

    if not long_record:
        log.warning("[narrative] Empty long_record for %s", char_name)
        return False

    # Enforce length caps
    if len(long_record)  > 4800:  long_record  = long_record[:4800]
    if len(short_record) > 900:   short_record = short_record[:900]

    now_ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        await db.upsert_narrative(
            char_id,
            long_record=long_record,
            short_record=short_record,
            last_summarized=now_ts,
        )
        log.info("[narrative] Summarized %s — %d actions", char_name, len(new_actions))
        return True
    except Exception as exc:
        log.warning("[narrative] DB write failed for %s: %s", char_name, exc)
        return False


# ── Nightly batch runner ───────────────────────────────────────────────────────

async def run_nightly_summarization(db, session_mgr=None) -> dict:
    """
    Summarize all PCs that have new action log entries.
    Returns stats dict: {processed, succeeded, failed, skipped}.
    Gracefully no-ops if API unavailable or AI disabled.
    """
    stats = {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    if not _narrative_ai_enabled:
        log.debug("[narrative] Nightly summarization skipped — AI disabled.")
        stats["skipped"] = -1
        return stats

    try:
        from ai.providers import get_ai_manager
        claude = get_ai_manager().get_provider("claude")
        if not claude or not await claude.is_available():
            log.warning("[narrative] Nightly summarization — Claude unavailable.")
            return stats
    except Exception as exc:
        log.warning("[narrative] Could not get ClaudeProvider: %s", exc)
        return stats

    chars = await db.get_chars_with_new_actions()
    if not chars:
        log.debug("[narrative] Nightly summarization: no PCs need updating.")
        return stats

    log.info("[narrative] Nightly summarization — %d PCs to process.", len(chars))

    for char_row in chars:
        stats["processed"] += 1
        try:
            ok = await summarize_character(db, claude, char_row)
            if ok:
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1
        except Exception as exc:
            log.warning("[narrative] Error summarizing char %s: %s",
                        char_row.get("id"), exc)
            stats["failed"] += 1
        await asyncio.sleep(0.5)  # Throttle between API calls

    log.info("[narrative] Nightly summarization complete — %s", stats)
    return stats


# ── On-demand trigger ─────────────────────────────────────────────────────────

async def trigger_on_demand_summarization(db, char_id: int,
                                           reason: str = "on_demand") -> bool:
    """
    Immediate summarization for one PC outside the nightly window.
    Used for: death/respawn, first planet change, quest completion.
    """
    if not _narrative_ai_enabled:
        return False

    try:
        from ai.providers import get_ai_manager
        claude = get_ai_manager().get_provider("claude")
        if not claude or not await claude.is_available():
            return False
    except Exception:
        log.warning("trigger_on_demand_summarization: unhandled exception", exc_info=True)
        return False

    rec = await db.get_narrative(char_id)
    char_rows = await db.get_chars_with_new_actions()
    char_row = next((r for r in char_rows if r["id"] == char_id), None)

    if char_row is None:
        # No new actions — build stub for background-only refresh
        rows = await db._db.execute_fetchall(
            "SELECT id, name, room_id, credits FROM characters WHERE id = ?",
            (char_id,),
        )
        if not rows:
            return False
        base = dict(rows[0])
        base.update({
            "last_summarized": "",
            "background":  rec["background"]  if rec else "",
            "long_record":  rec["long_record"]  if rec else "",
            "short_record": rec["short_record"] if rec else "",
        })
        char_row = base

    log.info("[narrative] On-demand summarization: char %s (%s)", char_id, reason)
    return await summarize_character(db, claude, char_row)


# ── Nightly scheduler ─────────────────────────────────────────────────────────

async def _nightly_scheduler(db, session_mgr):
    """Background task: wake at 03:00 each day, run batch summarization."""
    import datetime
    log.info("[narrative] Nightly scheduler started.")
    while True:
        try:
            now = datetime.datetime.now()
            target = now.replace(hour=3, minute=0, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            log.debug("[narrative] Next run at %s (%.0fs)",
                      target.strftime("%Y-%m-%d %H:%M"), wait_secs)
            await asyncio.sleep(wait_secs)
            await run_nightly_summarization(db, session_mgr)
        except asyncio.CancelledError:
            log.info("[narrative] Nightly scheduler cancelled.")
            return
        except Exception as exc:
            log.warning("[narrative] Scheduler error: %s — retrying in 1h.", exc)
            await asyncio.sleep(3600)


_scheduler_task = None


def schedule_nightly_job(db, session_mgr) -> None:
    """Start the nightly scheduler. Safe to call multiple times."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(_nightly_scheduler(db, session_mgr))
    log.info("[narrative] Nightly summarization scheduler registered.")


# ── Recap display ─────────────────────────────────────────────────────────────

async def format_recap(db, char: dict) -> str:
    """Format the +recap output for a character."""
    char_id   = char["id"]
    char_name = char.get("name", "Unknown")

    rec     = await db.get_narrative(char_id)
    actions = await db.get_recent_actions(char_id, limit=15)
    quests  = await db.get_personal_quests(char_id, status="active")

    lines = [
        "\033[1;36m══════════════════════════════════════════\033[0m",
        f"  \033[1;37mNARRATIVE RECAP — {char_name.upper()}\033[0m",
        "\033[1;36m══════════════════════════════════════════\033[0m",
    ]

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

    short = rec["short_record"] if rec else ""
    if short and _narrative_ai_enabled:
        lines += [
            "  \033[1;33mWhat the Galaxy Knows About You:\033[0m",
            f"  \033[2m{short[:600]}\033[0m",
            "\033[1;36m──────────────────────────────────────────\033[0m",
        ]
    elif actions:
        lines.append("  \033[1;33mRecent Activity:\033[0m")
        for a in actions[:8]:
            ts = a.get("logged_at", "")[:10]
            lines.append(f"  \033[2m{ts}\033[0m  {a['summary']}")
        lines.append("\033[1;36m──────────────────────────────────────────\033[0m")
    else:
        lines += [
            "  \033[2mNo recorded activity yet.\033[0m",
            "\033[1;36m──────────────────────────────────────────\033[0m",
        ]

    if rec and rec.get("long_record") and _narrative_ai_enabled:
        lines += [
            "  \033[1;33mDirector Summary:\033[0m",
            f"  {rec['long_record'][:600]}",
            "\033[1;36m──────────────────────────────────────────\033[0m",
        ]

    if quests:
        lines.append("  \033[1;33mPersonal Quests:\033[0m")
        for q in quests:
            lines.append(f"  \033[1;35m▸\033[0m {q['title']}")
            if q.get("description"):
                lines.append(f"    \033[2m{q['description'][:100]}\033[0m")
        lines.append("\033[1;36m──────────────────────────────────────────\033[0m")

    if not _narrative_ai_enabled:
        lines.append(
            "  \033[2m[Narrative AI offline — @director narrative enable to activate]\033[0m"
        )

    lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
    return "\n".join(lines)
