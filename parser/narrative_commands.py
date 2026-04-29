# -*- coding: utf-8 -*-
"""
parser/narrative_commands.py — PC narrative memory commands.

Commands:
  +background         — show your background
  +background <text>  — set your background (player-written)
  +recap              — show your narrative recap
  +quests             — list personal quests
  questaccept <id>    — accept a personal quest
  questcomplete <id>  — mark a quest complete
  questabandon <id>   — abandon a personal quest
  @narrative ...      — admin: status / view / update / reset / log
"""
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel

log = logging.getLogger(__name__)


# ── +background ───────────────────────────────────────────────────────────────

class BackgroundCommand(BaseCommand):
    key = "+background"
    aliases = ["background", "+bg", "bg"]
    help_text = (
        "View or set your character background.\n"
        "\n"
        "USAGE:\n"
        "  +background           — show your current background\n"
        "  +background <text>    — set your background (up to 2000 chars)\n"
        "\n"
        "Your background is seen by NPCs during conversation and by the\n"
        "Director AI when generating personal quests. Write it in third\n"
        "person — who you are, where you came from, what drives you.\n"
        "\n"
        "EXAMPLE:\n"
        "  +background A former Imperial TIE pilot who defected after\n"
        "  witnessing the destruction of an innocent colony. Now works\n"
        "  as a freelance pilot, taking jobs that don't involve civilians."
    )
    usage = "+background [<text>]"

    async def execute(self, ctx: CommandContext):
        from engine.narrative import get_background, set_background

        char = ctx.session.character
        text = (ctx.args or "").strip()

        if not text:
            bg = await get_background(ctx.db, char["id"])
            if bg:
                await ctx.session.send_line(
                    f"\n  \033[1;33mYour background:\033[0m\n  {bg}\n"
                )
            else:
                await ctx.session.send_line(
                    "  You haven't written a background yet.\n"
                    "  Use \033[1;33m+background <text>\033[0m to set one."
                )
            return

        await set_background(ctx.db, char["id"], text)
        await ctx.session.send_line(
            f"  \033[1;32mBackground saved.\033[0m "
            f"({len(text)} chars)  NPCs and the Director will take note."
        )
        # Spacer quest: background written
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(
                ctx.session, ctx.db, "use_command",
                command="+background", text_length=len(text),
            )
        except Exception as _e:
            log.debug("silent except in parser/narrative_commands.py:75: %s", _e, exc_info=True)


# ── +chargen_notes ────────────────────────────────────────────────────────────

class ChargenNotesCommand(BaseCommand):
    key = "+chargen_notes"
    aliases = ["chargen_notes", "+cgn", "cgn", "+chargennotes", "chargennotes"]
    help_text = (
        "View or set your chargen rationale — the player-facing 'why I "
        "built this character this way' notes.\n"
        "\n"
        "USAGE:\n"
        "  +chargen_notes           — show your current chargen notes\n"
        "  +chargen_notes <text>    — set your chargen notes (up to 2000 chars)\n"
        "  +chargen_notes /clear    — clear them\n"
        "\n"
        "Distinct from +background (in-character biography) and your "
        "look-at description.  Chargen notes are visible to you in the "
        "GUI sheet panel's right rail and never to other players.  Use "
        "them to remind yourself which advantages you took and why, "
        "what plot hooks you're hoping for, or what build direction "
        "you're aiming at."
    )
    usage = "+chargen_notes [<text>|/clear]"
    valid_switches = ["clear"]

    # Match the +background length cap so the two stay symmetric.
    _MAX_LENGTH = 2000

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        char_id = char.get("id")
        if not char_id:
            return

        # /clear empties the field
        if "clear" in ctx.switches:
            await ctx.db.save_character(char_id, chargen_notes="")
            char["chargen_notes"] = ""
            await ctx.session.send_line(
                "  \033[1;32mChargen notes cleared.\033[0m"
            )
            return

        text = (ctx.args or "").strip()

        if not text:
            current = char.get("chargen_notes", "") or ""
            if current:
                await ctx.session.send_line(
                    f"\n  \033[1;33mYour chargen notes:\033[0m\n  {current}\n"
                )
            else:
                await ctx.session.send_line(
                    "  You haven't written any chargen notes yet.\n"
                    "  Use \033[1;33m+chargen_notes <text>\033[0m to add some."
                )
            return

        if len(text) > self._MAX_LENGTH:
            await ctx.session.send_line(
                f"  \033[1;31mToo long.\033[0m  Max {self._MAX_LENGTH} chars; "
                f"your message was {len(text)}."
            )
            return

        try:
            await ctx.db.save_character(char_id, chargen_notes=text)
        except Exception as _e:
            log.warning("save chargen_notes failed: %s", _e, exc_info=True)
            await ctx.session.send_line(
                "  \033[1;31mCouldn't save chargen notes — try again.\033[0m"
            )
            return

        # Keep the live session dict in sync so the next +sheet shows
        # the new value without a re-fetch.
        char["chargen_notes"] = text
        await ctx.session.send_line(
            f"  \033[1;32mChargen notes saved.\033[0m  ({len(text)} chars)"
        )


# ── +recap ────────────────────────────────────────────────────────────────────

class RecapCommand(BaseCommand):
    key = "+recap"
    aliases = ["recap", "+history"]
    help_text = (
        "Show your narrative recap — background, recent actions, and personal quests.\n"
        "The Director AI uses this information to generate story hooks tailored to you."
    )
    usage = "+recap"

    async def execute(self, ctx: CommandContext):
        from engine.narrative import format_recap
        char = ctx.session.character
        await ctx.session.send_line(await format_recap(ctx.db, char))


# ── +quests ───────────────────────────────────────────────────────────────────

class QuestsCommand(BaseCommand):
    key = "+quests"
    aliases = ["quests", "+pq", "personalquests"]
    help_text = (
        "Show your active personal quests.\n"
        "Personal quests are generated by the Director AI based on your history.\n"
        "\n"
        "USAGE:\n"
        "  +quests              — show active quests\n"
        "  +quests completed    — show completed quests\n"
        "  questaccept <id>     — accept a pending quest\n"
        "  questcomplete <id>   — mark a quest complete\n"
        "  questabandon <id>    — abandon a quest"
    )
    usage = "+quests [completed]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        args = (ctx.args or "").strip().lower()
        status = "complete" if args == "completed" else "active"

        quests = await ctx.db.get_personal_quests(char["id"], status=status)

        if not quests:
            label = "completed" if status == "complete" else "active"
            await ctx.session.send_line(
                f"  You have no {label} personal quests.\n"
                f"  The Director AI generates quests based on your recent activity.\n"
                f"  Keep playing — quests appear as your story develops."
            )
            return

        lines = [
            "\033[1;36m══════════════════════════════════════════\033[0m",
            f"  \033[1;37mPERSONAL QUESTS — {'ACTIVE' if status == 'active' else 'COMPLETED'}\033[0m",
            "\033[1;36m──────────────────────────────────────────\033[0m",
        ]
        for q in quests:
            icon = "\033[1;32m✓\033[0m" if q["status"] == "complete" else "\033[1;35m▸\033[0m"
            lines.append(f"  {icon} [{q['id']}] \033[1;37m{q['title']}\033[0m")
            if q.get("description"):
                lines.append(f"    \033[2m{q['description'][:120]}\033[0m")
        lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
        await ctx.session.send_line("\n".join(lines))


# ── questaccept ───────────────────────────────────────────────────────────────

class QuestAcceptCommand(BaseCommand):
    key = "questaccept"
    aliases = ["acceptquest", "pqaccept"]
    help_text = "Accept a personal quest by its ID number.\n  questaccept <id>"
    usage = "questaccept <id>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        arg = (ctx.args or "").strip()

        if not arg.isdigit():
            await ctx.session.send_line("  Usage: questaccept <quest id>")
            return

        quest_id = int(arg)
        quest = await ctx.db.get_quest_by_id(quest_id)

        if not quest or quest["char_id"] != char["id"]:
            await ctx.session.send_line("  Quest not found.")
            return

        if quest["status"] != "active":
            await ctx.session.send_line(
                f"  That quest is already {quest['status']}."
            )
            return

        # Quest is already active when created — accepting just acknowledges
        await ctx.session.send_line(
            f"  \033[1;32mQuest accepted:\033[0m \033[1;37m{quest['title']}\033[0m\n"
            f"  {quest.get('description', '')[:200]}"
        )


# ── questcomplete ─────────────────────────────────────────────────────────────

class QuestCompleteCommand(BaseCommand):
    key = "questcomplete"
    aliases = ["finishquest", "pqcomplete", "completequest"]
    help_text = (
        "Mark a personal quest as complete.\n"
        "The Director will verify your progress.\n"
        "  questcomplete <id>"
    )
    usage = "questcomplete <id>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        arg = (ctx.args or "").strip()

        if not arg.isdigit():
            await ctx.session.send_line("  Usage: questcomplete <quest id>")
            return

        quest_id = int(arg)
        quest = await ctx.db.get_quest_by_id(quest_id)

        if not quest or quest["char_id"] != char["id"]:
            await ctx.session.send_line("  Quest not found.")
            return

        if quest["status"] == "complete":
            await ctx.session.send_line("  That quest is already complete.")
            return

        if quest["status"] != "active":
            await ctx.session.send_line(
                f"  That quest cannot be completed (status: {quest['status']})."
            )
            return

        await ctx.db.update_quest_status(quest_id, "complete")
        await ctx.session.send_line(
            f"  \033[1;32mQuest complete:\033[0m \033[1;37m{quest['title']}\033[0m\n"
            f"  The Director takes note of your accomplishment."
        )

        # Fire on-demand narrative update for quest completion
        try:
            from engine.narrative import trigger_on_demand_summarization
            import asyncio
            asyncio.get_event_loop().create_task(
                trigger_on_demand_summarization(ctx.db, char["id"], "quest_complete")
            )
        except Exception:
            pass  # Non-critical


# ── questabandon ──────────────────────────────────────────────────────────────

class QuestAbandonCommand(BaseCommand):
    key = "questabandon"
    aliases = ["abandonquest", "pqdrop"]
    help_text = "Abandon a personal quest.\n  questabandon <id>"
    usage = "questabandon <id>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        arg = (ctx.args or "").strip()

        if not arg.isdigit():
            await ctx.session.send_line("  Usage: questabandon <quest id>")
            return

        quest_id = int(arg)
        quest = await ctx.db.get_quest_by_id(quest_id)

        if not quest or quest["char_id"] != char["id"]:
            await ctx.session.send_line("  Quest not found.")
            return

        if quest["status"] in ("complete", "abandoned"):
            await ctx.session.send_line(
                f"  That quest is already {quest['status']}."
            )
            return

        await ctx.db.update_quest_status(quest_id, "abandoned")
        await ctx.session.send_line(
            f"  Quest abandoned: \033[2m{quest['title']}\033[0m\n"
            f"  Some stories are left unfinished."
        )


# ── @narrative (admin) ────────────────────────────────────────────────────────

class AdminNarrativeCommand(BaseCommand):
    key = "@narrative"
    aliases = ["@narr"]
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin: manage the PC narrative memory system.\n"
        "\n"
        "USAGE:\n"
        "  @narrative status          — system stats (PCs, log size, last batch)\n"
        "  @narrative view <player>   — view a PC's full narrative records\n"
        "  @narrative update <player> — force immediate summarization\n"
        "  @narrative reset <player>  — clear narrative records (keeps background)\n"
        "  @narrative log <player>    — view raw action log entries\n"
        "  @narrative enable          — enable AI narrative features\n"
        "  @narrative disable         — disable AI narrative features\n"
        "  @narrative runnow          — run nightly summarization immediately"
    )
    usage = "@narrative <sub-command> [args]"

    async def execute(self, ctx: CommandContext):
        from engine.narrative import (
            is_narrative_ai_enabled, set_narrative_ai,
            run_nightly_summarization,
        )

        args = (ctx.args or "").strip().split(None, 1)
        sub  = args[0].lower() if args else "status"
        rest = args[1].strip() if len(args) > 1 else ""

        # ── status ──
        if sub == "status":
            enabled = is_narrative_ai_enabled()
            chars = await ctx.db.get_chars_with_new_actions()
            await ctx.session.send_line(
                f"\n  \033[1;33mNarrative System Status\033[0m\n"
                f"  AI enabled : {'YES' if enabled else 'NO'}\n"
                f"  PCs pending: {len(chars)}\n"
                f"  Use @narrative enable/disable to toggle AI features.\n"
                f"  Use @narrative runnow to force a batch run."
            )
            return

        # ── enable / disable ──
        if sub == "enable":
            set_narrative_ai(True)
            await ctx.session.send_line("  Narrative AI features ENABLED.")
            return
        if sub == "disable":
            set_narrative_ai(False)
            await ctx.session.send_line("  Narrative AI features DISABLED.")
            return

        # ── runnow ──
        if sub == "runnow":
            await ctx.session.send_line("  Running nightly summarization batch...")
            stats = await run_nightly_summarization(ctx.db)
            await ctx.session.send_line(
                f"  Done — processed={stats['processed']} "
                f"ok={stats['succeeded']} failed={stats['failed']}"
            )
            return

        # ── commands needing a player name ──
        if not rest:
            await ctx.session.send_line(f"  Usage: @narrative {sub} <player>")
            return

        # Find character by name
        rows = await ctx.db.fetchall(
            "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
            (rest,),
        )
        if not rows:
            await ctx.session.send_line(f"  Character '{rest}' not found.")
            return
        target_id   = rows[0]["id"]
        target_name = rows[0]["name"]

        # ── view ──
        if sub == "view":
            rec = await ctx.db.get_narrative(target_id)
            if not rec:
                await ctx.session.send_line(f"  {target_name} has no narrative record yet.")
                return
            lines = [
                f"\n  \033[1;33mNarrative — {target_name}\033[0m",
                f"  Background    : {(rec.get('background','') or '(none)')[:200]}",
                f"  Short record  : {(rec.get('short_record','') or '(none)')[:200]}",
                f"  Long record   : {(rec.get('long_record','') or '(none)')[:400]}",
                f"  Last summarized: {rec.get('last_summarized','never')}",
            ]
            await ctx.session.send_line("\n".join(lines))
            return

        # ── log ──
        if sub == "log":
            actions = await ctx.db.get_recent_actions(target_id, limit=20)
            if not actions:
                await ctx.session.send_line(f"  No action log entries for {target_name}.")
                return
            lines = [f"\n  \033[1;33mAction Log — {target_name}\033[0m"]
            for a in actions:
                lines.append(
                    f"  {a.get('logged_at','')[:16]}  [{a['action_type']}]  {a['summary']}"
                )
            await ctx.session.send_line("\n".join(lines))
            return

        # ── update ──
        if sub == "update":
            from engine.narrative import trigger_on_demand_summarization
            await ctx.session.send_line(f"  Triggering summarization for {target_name}...")
            ok = await trigger_on_demand_summarization(ctx.db, target_id, "admin_update")
            await ctx.session.send_line("  Done." if ok else "  Failed (AI disabled or unavailable?).")
            return

        # ── reset ──
        if sub == "reset":
            await ctx.db.upsert_narrative(
                target_id,
                short_record="",
                long_record="",
                last_summarized="",
            )
            await ctx.session.send_line(
                f"  Narrative records cleared for {target_name}. Background preserved."
            )
            return

        await ctx.session.send_line(f"  Unknown sub-command: {sub}")


# ── Registration ──────────────────────────────────────────────────────────────

# S55: Switch & alias dispatch tables for the +quest umbrella.
_QUEST_SWITCH_IMPL: dict = {}

_QUEST_ALIAS_TO_SWITCH: dict[str, str] = {
    # list
    "quests":         "list",
    "personalquests": "list",
    "list":           "list",
    # accept
    "questaccept":    "accept",
    "acceptquest":    "accept",
    "pqaccept":       "accept",
    "accept":         "accept",
    # complete
    "questcomplete":  "complete",
    "finishquest":    "complete",
    "pqcomplete":     "complete",
    "completequest":  "complete",
    "complete":       "complete",
    # abandon
    "questabandon":   "abandon",
    "abandonquest":   "abandon",
    "pqdrop":         "abandon",
    "abandon":        "abandon",
}


class QuestCommand(BaseCommand):
    """`+quest` umbrella — full S55 dispatch over narrative quests."""
    key = "+quest"
    aliases: list[str] = [
        "quests", "personalquests",
        "questaccept", "acceptquest", "pqaccept",
        "questcomplete", "finishquest", "pqcomplete", "completequest",
        "questabandon", "abandonquest", "pqdrop",
    ]
    help_text = (
        "Quest verbs: '+quest/list', '+quest/accept <id>', "
        "'+quest/complete', '+quest/abandon'. Bare verbs (quests/"
        "questaccept/...) still work. Type 'help +quest' for the "
        "full reference."
    )
    usage = "+quest[/<switch>] [args]  — see 'help +quest'"
    valid_switches: list[str] = ["list", "accept", "complete", "abandon"]

    async def execute(self, ctx: CommandContext):
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            switch = _QUEST_ALIAS_TO_SWITCH.get(
                ctx.command.lower() if ctx.command else "",
                "list",
            )
        impl_cls = _QUEST_SWITCH_IMPL.get(switch)
        if impl_cls is None:
            await ctx.session.send_line(self.help_text)
            return
        await impl_cls().execute(ctx)


def _init_quest_switch_impl():
    _QUEST_SWITCH_IMPL["list"]     = QuestsCommand
    _QUEST_SWITCH_IMPL["accept"]   = QuestAcceptCommand
    _QUEST_SWITCH_IMPL["complete"] = QuestCompleteCommand
    _QUEST_SWITCH_IMPL["abandon"]  = QuestAbandonCommand


_init_quest_switch_impl()


def register_narrative_commands(registry):
    registry.register(QuestCommand())
    registry.register(BackgroundCommand())
    registry.register(ChargenNotesCommand())
    registry.register(RecapCommand())
    registry.register(QuestsCommand())
    registry.register(QuestAcceptCommand())
    registry.register(QuestCompleteCommand())
    registry.register(QuestAbandonCommand())
    registry.register(AdminNarrativeCommand())
