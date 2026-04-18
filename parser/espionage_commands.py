# -*- coding: utf-8 -*-
"""
parser/espionage_commands.py — Espionage Command Suite for SW_MUSH.

Commands:
  scan <player>         — covert character assessment
  eavesdrop [direction] — listen to adjacent room
  investigate           — search room for hidden info
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
            await ctx.session.send_line("  Scan who? Usage: scan <player>")
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
        for s in ctx.session_mgr.sessions_in_room(char["room_id"]):
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
            # Alert people in the target room
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
    key = "investigate"
    aliases = ["search", "inspect"]
    help_text = (
        "Search the current room for hidden information.\n"
        "Uses Search skill. Finds clues based on room state.\n"
        "\n"
        "USAGE: investigate\n"
        "COOLDOWN: 30 minutes per room"
    )
    usage = "investigate"

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
            await ctx.session.send_line("  Nothing to investigate here.")
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
    )
    usage = "+intel [create|add|seal|discard|read|give]"

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
            for s in ctx.session_mgr.sessions_in_room(char["room_id"]):
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
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  \033[1;33m{char['name']}'s comlink scanner emits "
                    f"a piercing squeal — they were trying to intercept "
                    f"communications!\033[0m",
                    exclude=ctx.session,
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

        # Achievement hook
        try:
            from engine.achievements import check_achievement
            await check_achievement(char, "intercept", ctx.db)
        except Exception as _e:
            log.debug("silent except in parser/espionage_commands.py:636: %s", _e, exc_info=True)


# ── Registration ──────────────────────────────────────────────────────────────

def register_espionage_commands(registry):
    """Register all espionage commands.

    S58 — +spy umbrella registered first; per-verb classes remain at
    their bare keys for backward compatibility.
    """
    registry.register(SpyCommand())
    registry.register(ScanCommand())
    registry.register(EavesdropCommand())
    registry.register(InvestigateCommand())
    registry.register(IntelCommand())
    registry.register(InterceptCommand())


# ═══════════════════════════════════════════════════════════════════════════
# +spy — Umbrella for espionage verbs (S58)
# ═══════════════════════════════════════════════════════════════════════════

_SPY_SWITCH_IMPL: dict = {}

_SPY_ALIAS_TO_SWITCH: dict[str, str] = {
    # Assess (size-up a target) — default (most common)
    "assess": "assess", "size": "assess",
    # Eavesdrop
    "eavesdrop": "eavesdrop", "listen": "eavesdrop",
    # Investigate
    "investigate": "investigate", "search": "investigate", "inspect": "investigate",
    # Intel
    "intel": "intel",
    # Intercept (comms wiretap)
    "intercept": "intercept", "wiretap": "intercept", "comtap": "intercept",
}


class SpyCommand(BaseCommand):
    """`+spy` umbrella — espionage and information-gathering verbs.

    Canonical                Bare aliases (still work)
    ---------------------    ---------------------------
    +spy                     (assess a target — default)
    +spy/assess <target>     assess, size
    +spy/eavesdrop           eavesdrop, listen
    +spy/investigate         investigate, search, inspect
    +spy/intel               intel, +intel
    +spy/intercept <chan>    intercept, wiretap, comtap

    `+spy` with no switch defaults to /assess — the "size up a
    target" action that's the most common first espionage step.
    All five verbs are covered switches.

    NOTE on `scan`: parser.espionage_commands.ScanCommand has
    key="assess" (NOT "scan") — it was renamed pre-sweep to avoid
    collision with parser.space_commands.ScanCommand (the sensor
    scan). The umbrella's /assess switch dispatches to the
    espionage ScanCommand; /scan in +sensors dispatches to the
    space one. Two different commands, two different canonical
    forms, no collision.
    """

    key = "+spy"
    aliases = [
        # Assess
        "assess", "size",
        # Eavesdrop
        "eavesdrop", "listen",
        # Investigate
        "investigate", "search", "inspect",
        # Intel
        "intel",
        # Intercept
        "intercept", "wiretap", "comtap",
    ]
    help_text = (
        "All espionage verbs live under +spy/<switch>. "
        "Bare verbs (assess, listen, search, intel, wiretap) still work."
    )
    usage = "+spy[/switch] [args]  — see 'help +spy' for all switches"
    valid_switches = [
        "assess", "eavesdrop", "investigate", "intel", "intercept",
    ]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _SPY_ALIAS_TO_SWITCH.get(typed, "assess")

        impl = _SPY_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown espionage switch: /{switch}. "
                f"Type 'help +spy' for the full list."
            )
            return
        await impl.execute(ctx)


def _init_spy_switch_impl():
    global _SPY_SWITCH_IMPL
    _SPY_SWITCH_IMPL = {
        "assess":      ScanCommand(),   # key='assess' despite class name
        "eavesdrop":   EavesdropCommand(),
        "investigate": InvestigateCommand(),
        "intel":       IntelCommand(),
        "intercept":   InterceptCommand(),
    }


_init_spy_switch_impl()
