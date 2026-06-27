"""parser/questline_commands.py — mid-game questline player commands.

T5-questline arc (2026-06-13). Companion to parser/chain_commands.py:
where `chain` interacts with the chargen-assigned ONBOARDING chain
(the `tutorial_chain` slot), `quests` interacts with the deliberately-
started mid-game QUESTLINE (the `active_questline` slot). Both run on
the same chain engine (engine/tutorial_chains + engine/chain_events);
the only difference is which attributes slot they read/write.

The player verb is `mastery` (NOT `quest`/`quests`/`train` — those keys
are already owned by the Director-AI personal-quest system
(narrative_commands.py), the spacer quest, the CP-spend `train`, and the
tutorial `training`). "Mastery" reads in-fiction as a master-trainer
certification arc and is collision-free.

Surface:

  mastery              — Show your active mastery questline (step +
                         objective) and any offered by an NPC here.
  mastery browse       — Galaxy-wide directory of every questline: what's
                         available now, what's locked (and why), what's
                         done, with the giver + `mastery start <id>` for
                         each. (Aliases: all / directory / catalog.)
  mastery start <id>   — Begin an offered questline (validates the
                         rep/faction gate via is_chain_locked_for_character).
  mastery status       — Detailed status of your active questline.
  mastery abandon      — Abandon your active questline (re-startable later).

Bare `mastery` is an alias for the list/status view. `mastery browse` is
the discoverability surface: the in-room offer only reveals a questline
when you stand with its giver, so `browse` lists the whole catalog and
where each one starts (it surfaces existence only — `start` still
enforces every gate).

Questline STEP progression (talk, combat, travel, skill checks) happens
through the SAME hooks as onboarding chains — they're slot-aware as of
this drop — so there is no separate "advance" command here. Skill-check
steps still use `chain attempt` (it reads whichever slot owns the active
skill-check step). This module only adds the START / LIST / ABANDON
surface that onboarding chains don't need (those are chargen-assigned).
"""

from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)

_SUBCOMMANDS = {"start", "status", "abandon", "list", "browse"}

# `mastery browse` aliases — the galaxy-wide questline directory.
_BROWSE_ALIASES = {"browse", "all", "directory", "catalog"}


class QuestCommand(BaseCommand):
    """``mastery`` — mid-game master-trainer questline interaction."""
    key = "mastery"
    aliases = ["masteries", "mastertrials"]
    help_text = (
        "Master-trainer mastery questlines.\n"
        "\n"
        "USAGE:\n"
        "  mastery              Show your active mastery questline and "
        "any offered by\n"
        "                       an NPC in this room.\n"
        "  mastery browse       Galaxy-wide directory: every questline, "
        "what's open\n"
        "                       now / locked / done, with the giver and "
        "start id.\n"
        "  mastery start <id>   Begin an offered questline.\n"
        "  mastery status       Detailed status of your active "
        "questline.\n"
        "  mastery abandon      Abandon your active questline (you can "
        "re-start it later).\n"
        "\n"
        "Questlines are opt-in mid-game arcs you start deliberately. Two "
        "kinds:\nfreelance side-jobs (open to anyone — talk to a broker in "
        "a cantina or\nmarket) and master-trainer trials (talk to a trainer "
        "in a dangerous zone;\ncompleting one helps unlock that trainer's "
        "tier-5 schematics). Steps\nadvance as you act (talk, fight, travel); "
        "skill-check steps use `chain\nattempt`. Can't find a giver? "
        "`mastery browse` lists them all."
    )
    usage = "mastery [browse | start <id> | status | abandon]"

    async def execute(self, ctx: CommandContext):
        if not ctx.session.is_in_game or not ctx.session.character:
            await ctx.session.send_line(
                "  You must be in the game to use quest commands."
            )
            return

        raw = (ctx.args or "").strip()
        parts = raw.split(None, 1)
        sub = parts[0].lower() if parts else "list"
        rest = parts[1].strip() if len(parts) > 1 else ""

        # `mastery all`/`directory`/`catalog` are spellings of `browse`.
        if sub in _BROWSE_ALIASES:
            sub = "browse"

        if sub not in _SUBCOMMANDS:
            # A bare `mastery` (no args) defaults sub="list" above and
            # never reaches here. Only a real unknown subcommand token
            # lands here — show the usage rather than guessing.
            await ctx.session.send_line(
                f"  Unknown mastery subcommand: {sub!r}\n"
                f"  Usage: {self.usage}"
            )
            return

        if sub in ("list", "status"):
            await self._handle_status(ctx, detailed=(sub == "status"))
            return
        if sub == "browse":
            await self._handle_browse(ctx)
            return
        if sub == "start":
            await self._handle_start(ctx, rest)
            return
        if sub == "abandon":
            await self._handle_abandon(ctx)
            return

    # ─── status / list ──────────────────────────────────────────────────

    async def _handle_status(self, ctx: CommandContext,
                             *, detailed: bool) -> None:
        char = ctx.session.character
        try:
            from engine.chain_events import (
                get_questline_status, get_questline_offer,
            )
        except ImportError:
            await ctx.session.send_line(
                "  Questline engine unavailable.")
            return

        info = get_questline_status(char)
        if info is not None:
            await ctx.session.send_line(
                f"  \033[1;36m{info['chain_name']}\033[0m  "
                f"(step {info['step']}/{info.get('chain_total_steps', '?')})"
            )
            await ctx.session.send_line(
                f"  \033[1m{info['title']}\033[0m"
            )
            if info.get("objective"):
                await ctx.session.send_line(f"    {info['objective']}")
            ctype = info.get("completion_type") or "(unknown)"
            await ctx.session.send_line(
                f"  \033[2mCompletes when:\033[0m {ctype}"
            )
            if info.get("next_hint"):
                await ctx.session.send_line(
                    f"  \033[2mNEXT:\033[0m {info['next_hint']}"
                )
            if ctype == "skill_check_passed":
                comp = info.get("completion") or {}
                await ctx.session.send_line(
                    f"  \033[2mWhen ready, type \033[0m"
                    f"\033[1;33mchain attempt\033[0m\033[2m to roll "
                    f"\033[0m\033[1m{comp.get('skill', '?')}\033[0m"
                    f"\033[2m vs difficulty \033[0m"
                    f"\033[1m{comp.get('difficulty', '?')}\033[0m\033[2m.\033[0m"
                )
            await ctx.session.send_line(
                "  \033[2m(Type \033[0m\033[1;33mmastery abandon\033[0m"
                "\033[2m to give it up.)\033[0m"
            )
            return

        # No active questline — show any offer from an NPC in this room.
        await ctx.session.send_line(
            "  You have no active questline."
        )
        offers = await self._offers_in_room(ctx, char, get_questline_offer)
        if offers:
            await ctx.session.send_line(
                "  \033[1;33mAvailable here:\033[0m"
            )
            for off in offers:
                if off.get("locked"):
                    await ctx.session.send_line(
                        f"    \033[2m— {off['chain_name']} "
                        f"(locked: {off.get('reason', '')})\033[0m"
                    )
                else:
                    await ctx.session.send_line(
                        f"    \033[1m{off['chain_name']}\033[0m — "
                        f"\033[2mmastery start \033[0m"
                        f"\033[1;33m{off['chain_id']}\033[0m"
                    )
        else:
            await ctx.session.send_line(
                "  \033[2mNothing offered in this room. Talk to a cantina or "
                "market broker for a freelance job, or a master trainer in a "
                "dangerous zone for a tier-5 craft — or type \033[0m"
                "\033[1;33mmastery browse\033[0m\033[2m to see every "
                "questline in the galaxy and where each one starts.\033[0m"
            )

    async def _handle_browse(self, ctx: CommandContext) -> None:
        """`mastery browse` — the galaxy-wide questline directory.

        Lists every questline the catalog holds, partitioned by the
        character's standing (active / available now / locked / done),
        with the giver, the starting zone, and the exact `mastery start
        <id>` to begin it. `mastery start` already validates the gate and
        teleports from anywhere, so this only surfaces existence — it
        never reveals a shortcut past a lock."""
        char = ctx.session.character
        try:
            from engine.chain_events import list_questline_directory
        except ImportError:
            await ctx.session.send_line(
                "  Questline engine unavailable.")
            return

        directory = list_questline_directory(char)
        if not directory:
            await ctx.session.send_line(
                "  No questlines are available right now.")
            return

        def _pretty_zone(slug: str) -> str:
            return (slug or "").replace("_", " ").strip().title()

        await ctx.session.send_line(
            "  \033[1;36mGALAXY QUESTLINE DIRECTORY\033[0m"
        )
        await ctx.session.send_line(
            "  \033[2mOpt-in arcs you start deliberately. "
            "\033[0m\033[1;33mmastery start <id>\033[0m\033[2m begins one "
            "and takes you to its giver — you hold one at a time.\033[0m"
        )

        # An active questline is reported first, with the one-at-a-time
        # caveat, so the directory explains why `start` will refuse below.
        active = [e for e in directory if e["status"] == "active"]
        available = [e for e in directory if e["status"] == "available"]
        locked = [e for e in directory if e["status"] == "locked"]
        completed = [e for e in directory if e["status"] == "completed"]

        if active:
            e = active[0]
            await ctx.session.send_line("")
            await ctx.session.send_line(
                "  \033[1;32mACTIVE\033[0m \033[2m(finish or "
                "`mastery abandon` before starting another)\033[0m"
            )
            await ctx.session.send_line(
                f"    \033[1m{e['chain_name']}\033[0m"
                + (f"  \033[2m[{e['archetype_label']}]\033[0m"
                   if e['archetype_label'] else "")
            )

        if available:
            await ctx.session.send_line("")
            await ctx.session.send_line(
                "  \033[1;33mAVAILABLE NOW\033[0m"
            )
            for e in available:
                await self._render_directory_entry(ctx, e, _pretty_zone,
                                                    startable=not active)

        if locked:
            await ctx.session.send_line("")
            await ctx.session.send_line(
                "  \033[2mLOCKED — requirements not yet met\033[0m"
            )
            for e in locked:
                zone = _pretty_zone(e["start_zone"])
                where = f" \033[2m({zone})\033[0m" if zone else ""
                await ctx.session.send_line(
                    f"    \033[2m— {e['chain_name']}{where}: "
                    f"{e['reason']}\033[0m"
                )

        if completed:
            await ctx.session.send_line("")
            names = ", ".join(e["chain_name"] for e in completed)
            await ctx.session.send_line(
                f"  \033[2mCOMPLETED ({len(completed)}): {names}\033[0m"
            )

    async def _render_directory_entry(self, ctx, e, pretty_zone,
                                      *, startable: bool) -> None:
        """Render one AVAILABLE-NOW questline line group."""
        label = (f"  \033[2m[{e['archetype_label']}]\033[0m"
                 if e['archetype_label'] else "")
        await ctx.session.send_line(
            f"    \033[1m{e['chain_name']}\033[0m{label}"
        )
        zone = pretty_zone(e["start_zone"])
        giver = e["giver_npc"]
        bits = []
        if zone:
            bits.append(zone)
        if giver:
            bits.append(giver)
        if bits:
            await ctx.session.send_line(
                f"      \033[2m{' — '.join(bits)}\033[0m"
            )
        if startable:
            await ctx.session.send_line(
                f"      \033[2m→ \033[0m\033[1;33mmastery start "
                f"{e['chain_id']}\033[0m"
            )
        else:
            await ctx.session.send_line(
                f"      \033[2m(finish your active questline first)\033[0m"
            )

    async def _offers_in_room(self, ctx, char, get_questline_offer) -> list:
        """Collect questline offers from every NPC in the player's room."""
        offers: list = []
        try:
            room_id = char.get("room_id")
            npcs = await ctx.db.get_npcs_in_room(room_id)
        except Exception:
            return offers
        seen = set()
        for npc in (npcs or []):
            name = (npc.get("name") if isinstance(npc, dict) else None) or ""
            if not name:
                continue
            try:
                offer = get_questline_offer(char, name)
            except Exception:
                offer = None
            if offer and offer.get("chain_id") not in seen:
                seen.add(offer.get("chain_id"))
                offers.append(offer)
        return offers

    # ─── start ──────────────────────────────────────────────────────────

    async def _handle_start(self, ctx: CommandContext, chain_id: str) -> None:
        char = ctx.session.character
        if not chain_id:
            await ctx.session.send_line(
                "  Usage: mastery start <id>   "
                "(type `mastery` to see what's offered here)."
            )
            return
        try:
            from engine.chain_events import start_questline
        except ImportError:
            await ctx.session.send_line(
                "  Questline engine unavailable.")
            return
        ok, msg = await start_questline(ctx.db, char, chain_id.strip())
        color = "\033[1;36m" if ok else "\033[1;33m"
        await ctx.session.send_line(f"  {color}{msg}\033[0m")
        if ok:
            # Land the player at step 1's narration on their next look;
            # surface the immediate objective now.
            try:
                from engine.chain_events import get_questline_status
                info = get_questline_status(char)
                if info and info.get("objective"):
                    await ctx.session.send_line(
                        f"  \033[1m{info['title']}\033[0m: {info['objective']}"
                    )
            except Exception:
                log.debug("questline start objective render failed",
                          exc_info=True)

    # ─── abandon ────────────────────────────────────────────────────────

    async def _handle_abandon(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        try:
            from engine.chain_events import abandon_questline
        except ImportError:
            await ctx.session.send_line(
                "  Questline engine unavailable.")
            return
        ok, msg = await abandon_questline(ctx.db, char)
        color = "\033[1;36m" if ok else "\033[1;33m"
        await ctx.session.send_line(f"  {color}{msg}\033[0m")


# ─── registration ───────────────────────────────────────────────────────


def register_questline_commands(registry) -> None:
    """Register the `mastery` command with the CommandRegistry.

    Called from server/game_server.py during registry init alongside
    register_chain_commands. No collisions with existing keys (the
    `quest`/`quests`/`train` namespaces are owned by other systems —
    see this module's docstring).
    """
    registry.register(QuestCommand())
