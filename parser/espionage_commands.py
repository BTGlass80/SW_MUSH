# -*- coding: utf-8 -*-
"""
parser/espionage_commands.py — Espionage Command Suite for SW_MUSH.

Commands:
  assess <player>       — covert character assessment (alias: size)
  eavesdrop [direction] — listen to adjacent room (alias: listen)
  search                — search room for hidden info (alias: inspect)
  +intel                — compose/manage intel reports

All skill checks route through perform_skill_check() per invariant.
Design source: competitive_analysis_feature_designs_v1.md §F
"""

from __future__ import annotations
import json
import logging
import random

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# ── Scan Command ──────────────────────────────────────────────────────────────

class ScanCommand(BaseCommand):
    key = "assess"
    aliases = ["size"]
    help_text = (
        "Covertly assess another character's status.\n"
        "Uses Perception vs. target's Con (opposed roll).\n"
        "\n"
        "USAGE: assess <player>\n"
        "COOLDOWN: 2 minutes per target\n"
        "\n"
        "NOTE: 'scan' in space uses ship sensors. Use 'assess' on the ground."
    )
    usage = "assess <player>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        target_name = (ctx.args or "").strip()
        if not target_name:
            await ctx.session.send_line("  Assess who? Usage: assess <player>")
            return

        # Cooldown check (2 minutes per target)
        from engine.cooldowns import check_cooldown, set_cooldown, remaining_cooldown, format_remaining
        cd_key = f"scan_{target_name.lower()[:20]}"
        if not check_cooldown(char, cd_key):
            rem = remaining_cooldown(char, cd_key)
            await ctx.session.send_line(
                f"  You scanned recently. Wait {format_remaining(rem)}."
            )
            return

        # Find target in room
        target_sess = None
        for s in ctx.session_mgr.sessions_in_room(char["room_id"], source_char=char):
            if (s.character and
                    s.character["name"].lower().startswith(target_name.lower()) and
                    s.character["id"] != char["id"]):
                target_sess = s
                break

        if not target_sess:
            await ctx.session.send_line(f"  '{target_name}' isn't here.")
            return

        target = target_sess.character

        # Opposed roll: scanner's Perception vs target's Con
        from engine.skill_checks import perform_skill_check
        scan_result = perform_skill_check(char, "perception", 0)
        con_result = perform_skill_check(target, "con", 0)

        margin = scan_result.roll - con_result.roll

        # Set cooldown regardless of outcome
        set_cooldown(char, cd_key, 120)  # 2 minutes
        # Persist cooldown
        try:
            await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
        except Exception as _e:
            log.debug("silent except in parser/espionage_commands.py:88: %s", _e, exc_info=True)

        if scan_result.fumble:
            # Fumble: target notices
            await ctx.session.send_line(
                f"  \033[1;31m{target['name']} catches you staring.\033[0m"
            )
            await target_sess.send_line(
                f"\n  \033[1;33m{char['name']} was sizing you up but you caught them.\033[0m\n"
            )
            return

        if margin < 0:
            # Failed — nothing happens, target unaware
            await ctx.session.send_line(
                "  You observe casually but can't read much from a glance."
            )
            return

        # Success — generate scan results
        from engine.espionage import generate_scan_result
        lines = generate_scan_result(char, target, margin)
        for line in lines:
            await ctx.session.send_line(line)


# ── Eavesdrop Command ─────────────────────────────────────────────────────────

class EavesdropCommand(BaseCommand):
    key = "eavesdrop"
    aliases = ["listen"]
    help_text = (
        "Listen to conversations in an adjacent room.\n"
        "Uses Perception skill check. Active for 5 minutes.\n"
        "\n"
        "USAGE: eavesdrop <direction>\n"
        "       eavesdrop stop\n"
        "COOLDOWN: 10 minutes"
    )
    usage = "eavesdrop <direction>  |  eavesdrop stop"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        args = (ctx.args or "").strip().lower()

        from engine.espionage import stop_eavesdrop, get_eavesdrop_target

        if args == "stop":
            stop_eavesdrop(char["id"])
            await ctx.session.send_line("  You stop listening.")
            return

        if not args:
            # Check if currently eavesdropping
            current = get_eavesdrop_target(char["id"])
            if current:
                await ctx.session.send_line(
                    f"  You're currently eavesdropping on room #{current}. "
                    f"Type 'eavesdrop stop' to stop."
                )
            else:
                await ctx.session.send_line("  Eavesdrop in which direction? Usage: eavesdrop <direction>")
            return

        # Cooldown check
        from engine.cooldowns import check_cooldown, set_cooldown, remaining_cooldown, format_remaining
        if not check_cooldown(char, "eavesdrop"):
            rem = remaining_cooldown(char, "eavesdrop")
            await ctx.session.send_line(f"  Still recovering. Wait {format_remaining(rem)}.")
            return

        # Find exit in that direction
        exits = await ctx.db.get_exits(char["room_id"])
        target_exit = None
        for e in exits:
            direction = (e.get("direction") or e.get("name") or "").lower()
            if direction.startswith(args) or args in direction:
                target_exit = e
                break

        if not target_exit:
            await ctx.session.send_line(f"  No exit '{args}' to eavesdrop through.")
            return

        target_room_id = target_exit.get("destination_id") or target_exit.get("to_room_id")
        if not target_room_id:
            await ctx.session.send_line("  That exit doesn't lead anywhere.")
            return

        # Perception check
        from engine.skill_checks import perform_skill_check
        # Difficulty based on room type
        difficulty = 15  # Moderate for adjacent room
        result = perform_skill_check(char, "perception", difficulty)

        set_cooldown(char, "eavesdrop", 600)  # 10 minutes
        try:
            await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
        except Exception as _e:
            log.debug("silent except in parser/espionage_commands.py:189: %s", _e, exc_info=True)

        if result.fumble:
            # Fumble: make noise
            await ctx.session.send_line(
                "  \033[1;31mYou stumble against the wall, making a loud thud.\033[0m"
            )
            # Alert people in the target room.
            #
            # W.2.3.1 note: this broadcast goes to `target_room_id`, a
            # DIFFERENT room from char. source_char filtering would key
            # to char's coords, which is meaningless for the target
            # room's PCs. Eavesdrop targets are regular indoor rooms
            # today (housing/cantina walls), not wilderness tiles, so
            # there's no active leak. If a future drop adds wilderness-
            # tile-to-wilderness-tile eavesdropping, this site needs a
            # `target_char` (someone known to be in target_room_id) so
            # the helper can filter by target-side coords.
            for s in ctx.session_mgr.sessions_in_room(target_room_id):
                if s.is_in_game:
                    await s.send_line(
                        "\n  \033[2mYou hear a faint shuffling sound from beyond the wall.\033[0m"
                    )
            return

        if not result.success:
            await ctx.session.send_line(
                "  You press your ear to the wall but hear nothing useful."
            )
            return

        # Success — start eavesdrop session
        from engine.espionage import start_eavesdrop
        start_eavesdrop(char["id"], target_room_id)

        target_room = await ctx.db.get_room(target_room_id)
        room_name = target_room.get("name", "unknown") if target_room else "unknown"

        await ctx.session.send_line(
            f"\n  \033[1;36mYou press your ear to the wall and listen...\033[0m\n"
            f"  \033[2m[Eavesdropping on: {room_name}]\033[0m\n"
            f"  \033[2mYou'll overhear fragments for the next 5 minutes.\033[0m\n"
            f"  \033[2mType 'eavesdrop stop' to stop or move rooms to break it.\033[0m"
        )


# ── Investigate Command ───────────────────────────────────────────────────────

class InvestigateCommand(BaseCommand):
    # Command-syntax rework Drop 7 (type-3 genuine-conflict resolution): this
    # espionage room-search command's bare key was 'investigate', which
    # collided with anomaly_commands.InvestigateCommand (`investigate <id>` —
    # resolve a wilderness anomaly). The anomaly verb keeps bare 'investigate';
    # this one is canonicalized to 'search' (it already aliased search/inspect,
    # but those routed to the anomaly key while it was shadowed, so the room
    # search was only reachable via +spy investigate). Now `search`/`inspect`
    # cleanly reach it, and +spy investigate still dispatches it by class.
    key = "search"
    aliases = ["inspect"]
    help_text = (
        "Search the current room for hidden information.\n"
        "Uses Search skill. Finds clues based on room state.\n"
        "\n"
        "USAGE: search\n"
        "COOLDOWN: 30 minutes per room"
    )
    usage = "search"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        room_id = char["room_id"]

        # Cooldown (30 min per room)
        from engine.cooldowns import check_cooldown, set_cooldown, remaining_cooldown, format_remaining
        cd_key = f"investigate_{room_id}"
        if not check_cooldown(char, cd_key):
            rem = remaining_cooldown(char, cd_key)
            await ctx.session.send_line(
                f"  You've already searched here recently. Wait {format_remaining(rem)}."
            )
            return

        # Get room
        room = await ctx.db.get_room(room_id)
        if not room:
            await ctx.session.send_line("  Nothing to search here.")
            return

        # Determine difficulty based on room type
        props = room.get("properties", "{}")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except Exception:
                props = {}

        env = props.get("environment", "").lower()
        if "official" in env or "military" in env:
            difficulty = 25  # Very Difficult
        elif "residential" in env or "underground" in env:
            difficulty = 15  # Moderate
        else:
            difficulty = 20  # Difficult (public areas)

        # Search check
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(char, "search", difficulty)

        set_cooldown(char, cd_key, 1800)  # 30 minutes
        try:
            await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
        except Exception as _e:
            log.debug("silent except in parser/espionage_commands.py:285: %s", _e, exc_info=True)

        await ctx.session.send_line(
            "\n  \033[1;36mYou methodically search the area...\033[0m"
        )

        if not result.success:
            await ctx.session.send_line(
                "  You search carefully but find nothing of note."
            )
            return

        # Generate findings
        from engine.espionage import generate_investigation_findings
        findings = await generate_investigation_findings(
            ctx.db, char, room, result.margin,
        )

        if findings:
            await ctx.session.send_line("\n  \033[1;37mFINDINGS:\033[0m")
            for f in findings:
                await ctx.session.send_line(f"  \033[1;33m●\033[0m {f}")
        else:
            await ctx.session.send_line("  Nothing notable found.")

        await ctx.session.send_line(
            f"\n  \033[2m[Search: {result.pool_str} vs diff {difficulty}, "
            f"rolled {result.roll}, margin {result.margin:+d}]\033[0m"
        )


# ── Intel Command ─────────────────────────────────────────────────────────────

class IntelCommand(BaseCommand):
    key = "+intel"
    aliases = ["intel"]
    help_text = (
        "Compose and manage intelligence reports.\n"
        "\n"
        "  +intel                  — list your reports\n"
        "  +intel create <title>   — start a new report\n"
        "  +intel add <text>       — add a line to current draft\n"
        "  +intel seal             — seal report (makes it tradeable)\n"
        "  +intel discard          — discard current draft\n"
        "  +intel read <id>        — read a report\n"
        "  +intel give <player> <id> — give a sealed report\n"
        "  +intel handover [<id>]  — hand a sealed report to your\n"
        "                            faction's intel handler in this\n"
        "                            room (SYN.5; converts to credits\n"
        "                            + influence per intel quality)\n"
    )
    usage = "+intel [create|add|seal|discard|read|give|handover]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        from engine.espionage import (
            get_intel_reports, create_intel_report, add_intel_line,
            seal_intel_report, discard_intel_draft, give_intel_report,
            format_intel_report,
        )

        args = (ctx.args or "").strip()
        parts = args.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "create":
            if not rest:
                await ctx.session.send_line("  Usage: +intel create <title>")
                return
            result = create_intel_report(char, rest)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            if result["ok"]:
                await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
            return

        if sub == "add":
            if not rest:
                await ctx.session.send_line("  Usage: +intel add <text>")
                return
            result = add_intel_line(char, rest)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            if result["ok"]:
                await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
            return

        if sub == "seal":
            result = seal_intel_report(char)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            if result["ok"]:
                await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
            return

        if sub == "discard":
            result = discard_intel_draft(char)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            if result["ok"]:
                await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
            return

        if sub == "read":
            if not rest:
                await ctx.session.send_line("  Usage: +intel read <id>")
                return
            try:
                report_id = int(rest)
            except ValueError:
                await ctx.session.send_line("  Invalid report ID.")
                return
            reports = get_intel_reports(char)
            report = next((r for r in reports if r.get("id") == report_id), None)
            if not report:
                await ctx.session.send_line("  Report not found.")
                return
            lines = format_intel_report(report)
            for line in lines:
                await ctx.session.send_line(line)
            return

        if sub == "give":
            give_parts = rest.split(None, 1)
            if len(give_parts) < 2:
                await ctx.session.send_line("  Usage: +intel give <player> <id>")
                return
            target_name = give_parts[0]
            try:
                report_id = int(give_parts[1])
            except ValueError:
                await ctx.session.send_line("  Invalid report ID.")
                return

            # Find target in room
            target_sess = None
            for s in ctx.session_mgr.sessions_in_room(char["room_id"], source_char=char):
                if (s.character and
                        s.character["name"].lower().startswith(target_name.lower()) and
                        s.character["id"] != char["id"]):
                    target_sess = s
                    break
            if not target_sess:
                await ctx.session.send_line(f"  '{target_name}' isn't here.")
                return

            result = give_intel_report(char, target_sess.character, report_id)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            if result["ok"]:
                await ctx.db.save_character(char["id"], attributes=char.get("attributes", "{}"))
                await ctx.db.save_character(
                    target_sess.character["id"],
                    attributes=target_sess.character.get("attributes", "{}"),
                )
                await target_sess.send_line(
                    f"\n  \033[1;33m[INTEL]\033[0m {char['name']} gave you an intel report.\n"
                    f"  Type '+intel' to view your reports.\n"
                )
            return

        if sub == "handover":
            # SYN.5 (2026-05-25): hand a sealed report to a faction
            # intel handler NPC in the room. Converts to credits +
            # influence per design v2 §2.7.
            #
            # Usage: +intel handover [<id>]
            #   With no id: pick the player's first sealed report.
            #   With id: hand that specific sealed report.
            from engine.intel_handlers import (
                handover_intel, find_handler_in_room,
            )
            # Resolve report id (optional — default to first sealed)
            handover_parts = rest.split(None, 1) if rest else []
            target_report_id = None
            if handover_parts:
                try:
                    target_report_id = int(handover_parts[0])
                except ValueError:
                    await ctx.session.send_line(
                        "  Usage: +intel handover [<report_id>]\n"
                        "  (Omit the id to hand over your first sealed "
                        "report.)"
                    )
                    return
            if target_report_id is None:
                reports = get_intel_reports(char)
                sealed = [r for r in reports if r.get("sealed")]
                if not sealed:
                    await ctx.session.send_line(
                        ansi.error(
                            "  You have no sealed intel to hand over. "
                            "Seal a draft first with +intel seal."
                        )
                    )
                    return
                target_report_id = sealed[0]["id"]
            # Find a handler in the room that accepts the player's
            # faction.
            faction = char.get("faction_id") or "independent"
            handler = await find_handler_in_room(
                ctx.db, char.get("room_id"), faction,
            )
            if not handler:
                await ctx.session.send_line(
                    ansi.error(
                        "  No intel handler for your faction is here. "
                        "Travel to your faction's HQ to find one."
                    )
                )
                return
            result = await handover_intel(
                ctx.db, char, handler["id"], target_report_id,
                session_mgr=ctx.session_mgr,
            )
            if result.get("ok"):
                await ctx.session.send_line(
                    ansi.success(f"  {result['msg']}")
                )
            else:
                await ctx.session.send_line(
                    ansi.error(f"  {result['msg']}")
                )
            return

        # Default: list reports
        reports = get_intel_reports(char)
        if not reports:
            await ctx.session.send_line(
                "  \033[2mNo intel reports. Use +intel create <title> to start one.\033[0m"
            )
            return

        w = 50
        await ctx.session.send_line(f"\n  \033[1;36m{'═' * w}\033[0m")
        await ctx.session.send_line(f"  \033[1;37m  Intelligence Reports ({len(reports)})\033[0m")
        await ctx.session.send_line(f"  \033[1;36m{'─' * w}\033[0m")
        import time as _t
        for r in reports:
            status = "\033[1;32mSEALED\033[0m" if r.get("sealed") else "\033[1;33mDRAFT\033[0m"
            remaining = r.get("expires_at", 0) - _t.time()
            exp = f"{int(remaining // 86400)}d" if remaining > 0 else "\033[1;31mEXPIRED\033[0m"
            lines_count = len(r.get("lines", []))
            await ctx.session.send_line(
                f"  [{r['id']}] \033[1m{r['title']}\033[0m  "
                f"{status}  {lines_count} lines  {exp}"
            )
        await ctx.session.send_line(f"  \033[1;36m{'═' * w}\033[0m\n")


# ── Eavesdrop Hook (for SayCommand integration) ──────────────────────────────

async def relay_to_eavesdroppers(
    session_mgr, room_id: int, speaker_name: str, text: str,
) -> None:
    """Relay say/emote text to anyone eavesdropping on this room.

    Called from SayCommand and EmoteCommand after broadcasting to the room.
    """
    from engine.espionage import get_eavesdrop_target, muffle_for_eavesdrop

    for s in session_mgr.all:
        if not s.is_in_game or not s.character:
            continue
        target = get_eavesdrop_target(s.character["id"])
        if target == room_id:
            muffled = muffle_for_eavesdrop(text)
            if muffled and muffled != "... ... ...":
                await s.send_line(
                    f"  \033[2m[Overheard] {speaker_name}: \"{muffled}\"\033[0m"
                )


# ── Comlink Intercept Command (Tier 3 Feature #19) ───────────────────────────

class InterceptCommand(BaseCommand):
    """
    intercept — Tap into nearby comlink and faction communications.
    Uses Perception vs. Security contested roll.
    Active for 5 minutes. You'll receive muffled fragments of comlink
    and faction comms sent by players in your room or adjacent rooms.
    """
    key = "intercept"
    aliases = ["wiretap", "comtap"]
    help_text = (
        "Tap into nearby comlink and faction communications.\n"
        "\n"
        "USAGE:\n"
        "  intercept        — start intercepting (5 minutes)\n"
        "  intercept stop   — stop intercepting\n"
        "  intercept status — check active intercept\n"
        "\n"
        "Perception skill check (difficulty 15). On success, you\n"
        "receive muffled fragments of comlink and faction comms\n"
        "from players in your room and adjacent rooms.\n"
        "Fumble reveals your surveillance to the room.\n"
        "COOLDOWN: 10 minutes"
    )
    usage = "intercept  |  intercept stop"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        args = (ctx.args or "").strip().lower()

        from engine.espionage import (
            start_intercept, stop_intercept, get_intercept_session,
        )

        if args == "stop":
            sess = get_intercept_session(char["id"])
            if sess:
                count = sess.get("intercepted_count", 0)
                stop_intercept(char["id"])
                await ctx.session.send_line(
                    f"  You power down your comlink scanner. "
                    f"({count} transmission(s) intercepted)"
                )
            else:
                await ctx.session.send_line("  You're not intercepting anything.")
            return

        if args == "status":
            sess = get_intercept_session(char["id"])
            if sess:
                import time as _t
                remaining = max(0, int(sess["expires_at"] - _t.time()))
                await ctx.session.send_line(
                    f"  \033[1;36m[INTERCEPT ACTIVE]\033[0m "
                    f"{remaining}s remaining, "
                    f"{sess.get('intercepted_count', 0)} caught"
                )
            else:
                await ctx.session.send_line("  No active intercept.")
            return

        # Check if already intercepting
        existing = get_intercept_session(char["id"])
        if existing:
            import time as _t
            remaining = max(0, int(existing["expires_at"] - _t.time()))
            await ctx.session.send_line(
                f"  Already intercepting ({remaining}s remaining). "
                f"Type 'intercept stop' to cancel."
            )
            return

        # Cooldown check
        from engine.cooldowns import check_cooldown, set_cooldown, remaining_cooldown, format_remaining
        if not check_cooldown(char, "intercept"):
            rem = remaining_cooldown(char, "intercept")
            await ctx.session.send_line(
                f"  Scanner still cooling down. Wait {format_remaining(rem)}.")
            return

        # Perception check — difficulty 15
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(char, "perception", 15)

        set_cooldown(char, "intercept", 600)  # 10 minutes
        try:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}"))
        except Exception as _e:
            log.debug("silent except in parser/espionage_commands.py:596: %s", _e, exc_info=True)

        if result.fumble:
            await ctx.session.send_line(
                "  \033[1;31mFumble!\033[0m Your scanner emits a loud feedback "
                "squeal. Everyone nearby knows you were trying to listen in."
            )
            room_id = char.get("room_id")
            if room_id:
                # W.2.3.1: source_char filters squeal to co-located peers.
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  \033[1;33m{char['name']}'s comlink scanner emits "
                    f"a piercing squeal — they were trying to intercept "
                    f"communications!\033[0m",
                    exclude=ctx.session,
                    source_char=char,
                )
            return

        if not result.success:
            await ctx.session.send_line(
                "  You tune your scanner but can't lock onto any signals. "
                "Too much interference."
            )
            return

        # Success — start intercept
        start_intercept(char["id"], char.get("room_id", 0))

        await ctx.session.send_line(
            f"\n  \033[1;36m[COMLINK INTERCEPT ACTIVE]\033[0m\n"
            f"  \033[2mScanner locked. You'll receive fragments of comlink\n"
            f"  and faction comms for the next 5 minutes.\033[0m\n"
            f"  \033[2mType 'intercept stop' to end or move to break.\033[0m"
        )

        # Achievement hook — args fixed: db first, then char_id, then event
        try:
            from engine.achievements import check_achievement
            await check_achievement(ctx.db, char["id"], "intercept", session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/espionage_commands.py:636: %s", _e, exc_info=True)


# ── Registration ──────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════
# +spy — Espionage umbrella (S58)
# ═══════════════════════════════════════════════════════════════════════════
#
# `+spy` consolidates the five espionage verbs (assess/eavesdrop/
# investigate/intel/intercept) under a single +-prefix. Each verb's
# bare form is preserved in the umbrella's aliases list so existing
# muscle memory continues to work — `assess <player>` still routes
# correctly via the alias→switch map below.

_SPY_SWITCH_IMPL: dict = {}

_SPY_ALIAS_TO_SWITCH: dict[str, str] = {
    "":            "assess",
    "assess":      "assess",
    "size":        "assess",
    "eavesdrop":   "eavesdrop",
    "listen":      "eavesdrop",
    "investigate": "investigate",
    "search":      "investigate",
    "inspect":     "investigate",
    "intel":       "intel",
    "intercept":   "intercept",
    "wiretap":     "intercept",
    "comtap":      "intercept",
}


class SpyCommand(BaseCommand):
    """`+spy` umbrella — espionage verbs."""
    key = "+spy"
    # Command-syntax rework Drop 4 (command_syntax_rework_design_v2.md): the
    # DUPLICATE aliases that a standalone command already owns
    # (size→ScanCommand, search/inspect→InvestigateCommand, intel→IntelCommand,
    # wiretap/comtap→InterceptCommand) are DELETED — they were dead duplicates
    # (the standalone registers later and wins), so each still resolves to the
    # same handler. The _SPY_ALIAS_TO_SWITCH dispatch map is left intact (it
    # drives the arg-keyed `+spy <verb>` form).
    # Command-syntax rework Drop 7 (type-3 genuine-conflict resolution):
    # 'listen' and 'investigate' DELETED. 'listen' is owned by the standalone
    # EavesdropCommand (bare 'listen' = listen to an adjacent room); 'investigate'
    # is owned by anomaly_commands.InvestigateCommand (`investigate <id>`). The
    # espionage room-search lives at bare 'search'/'inspect'. All three are still
    # reachable through the umbrella: +spy eavesdrop / +spy investigate (the
    # _SPY_SWITCH_IMPL forwards dispatch the espionage handlers by class).
    aliases: list[str] = [
        "assess", "eavesdrop",
        "investigate",
        "intercept",
    ]
    help_text = (
        "Espionage verbs: '+spy assess <player>', '+spy eavesdrop', "
        "'+spy investigate', '+spy intel', '+spy intercept'. Type "
        "'help +spy' for the full reference."
    )
    usage = "+spy <verb> [args]  — see 'help +spy'"
    valid_switches: list[str] = [
        "assess", "eavesdrop", "investigate", "intel", "intercept",
    ]

    async def execute(self, ctx: CommandContext):
        args = ctx.args.strip() if ctx.args else ""
        first, _, rest = args.partition(" ")
        switch = _SPY_ALIAS_TO_SWITCH.get(first.lower(), first.lower())

        impl = _SPY_SWITCH_IMPL.get(switch)
        if impl is not None:
            await impl(ctx, rest)
            return

        await ctx.session.send_line(self.help_text)


def _init_spy_switch_impl():
    """Wire forwarding handlers into _SPY_SWITCH_IMPL."""
    async def _assess(ctx, rest):
        cmd = ScanCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _eavesdrop(ctx, rest):
        cmd = EavesdropCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _investigate(ctx, rest):
        cmd = InvestigateCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _intel(ctx, rest):
        cmd = IntelCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _intercept(ctx, rest):
        cmd = InterceptCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    _SPY_SWITCH_IMPL["assess"] = _assess
    _SPY_SWITCH_IMPL["eavesdrop"] = _eavesdrop
    _SPY_SWITCH_IMPL["investigate"] = _investigate
    _SPY_SWITCH_IMPL["intel"] = _intel
    _SPY_SWITCH_IMPL["intercept"] = _intercept


_init_spy_switch_impl()


def register_espionage_commands(registry):
    """Register all espionage commands."""
    registry.register(SpyCommand())
    registry.register(ScanCommand())
    registry.register(EavesdropCommand())
    registry.register(InvestigateCommand())
    registry.register(IntelCommand())
    registry.register(InterceptCommand())
