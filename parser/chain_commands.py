"""parser/chain_commands.py — Tutorial-chain player commands (F.8.c.2.b₆).

Per cw_tutorial_chains_design_v1.md §6 step 3 and the F.8.c.2.b₆
design call (May 20 2026):

The launch-day surface for tutorial-chain interaction:

  chain attempt   — Trigger the active step's `skill_check_passed`
                    roll. The step's authored skill + difficulty
                    are read from the chain corpus; the result is
                    dispatched to chain_events.on_skill_check_passed
                    for chain advancement.

  chain status    — Show the active chain, current step, and the
                    completion type/objective so the player knows
                    what to do next.

Other completion types (talk_to_npc, combat_won, command_executed,
…) advance automatically when the player performs the
corresponding action — `chain attempt` is specifically for the
six `skill_check_passed` steps in chains.yaml that need an
explicit roll trigger.

The seam decision history is in
``engine/chain_events.py::F.8.c.2.b₆ design note``.
"""

from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


# Subcommands recognized by the top-level `chain` command. New
# subcommands (e.g. `chain skip` for admin testing) can be added
# here without re-registering with the parser.
_SUBCOMMANDS = {"attempt", "status"}


class ChainCommand(BaseCommand):
    """``chain`` — tutorial-chain interaction.

    Subcommands:
      chain attempt   Trigger the active step's skill roll.
      chain status    Show active chain + current step info.

    Bare ``chain`` is an alias for ``chain status``.
    """
    key = "chain"
    aliases: list = []
    help_text = (
        "Tutorial-chain interaction.\n"
        "\n"
        "USAGE:\n"
        "  chain attempt   Try the current step's skill check. Use "
        "this when the step's\n"
        "                  objective is a skill roll (e.g. sneak "
        "past a patrol).\n"
        "  chain status    Show your active chain, current step, "
        "and what completes it.\n"
        "  chain           Alias for `chain status`.\n"
        "\n"
        "Other chain progress happens automatically when you talk "
        "to the right NPC, enter\nthe right room, win a fight, etc."
    )
    usage = "chain [attempt | status]"

    async def execute(self, ctx: CommandContext):
        if not ctx.session.is_in_game or not ctx.session.character:
            await ctx.session.send_line(
                "  You must be in the game to use chain commands."
            )
            return

        sub = (ctx.args or "").strip().lower()
        if not sub:
            sub = "status"
        if sub not in _SUBCOMMANDS:
            await ctx.session.send_line(
                f"  Unknown chain subcommand: {sub!r}\n"
                f"  Usage: {self.usage}"
            )
            return

        if sub == "status":
            await self._handle_status(ctx)
            return
        if sub == "attempt":
            await self._handle_attempt(ctx)
            return

    # ─── status ──────────────────────────────────────────────────────────

    async def _handle_status(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        try:
            from engine.chain_events import get_active_step_info
        except ImportError:
            await ctx.session.send_line(
                "  Chain progression engine unavailable.")
            return

        info = get_active_step_info(char)
        if info is None:
            await ctx.session.send_line(
                "  You have no active tutorial chain.")
            return

        await ctx.session.send_line(
            f"  \033[1;36m{info['chain_name']}\033[0m  "
            f"(step {info['step']})"
        )
        await ctx.session.send_line(
            f"  \033[1m{info['title']}\033[0m"
        )
        if info.get("objective"):
            await ctx.session.send_line(
                f"    {info['objective']}"
            )
        ctype = info.get("completion_type") or "(unknown)"
        await ctx.session.send_line(
            f"  \033[2mCompletes when:\033[0m {ctype}"
        )
        # If this is a skill_check_passed step, tell them they
        # can `chain attempt`.
        if ctype == "skill_check_passed":
            comp = info.get("completion") or {}
            skill = comp.get("skill", "?")
            diff = comp.get("difficulty", "?")
            await ctx.session.send_line(
                f"  \033[2mWhen ready, type \033[0m"
                f"\033[1;33mchain attempt\033[0m\033[2m to roll "
                f"\033[0m\033[1m{skill}\033[0m\033[2m vs "
                f"difficulty \033[0m\033[1m{diff}\033[0m\033[2m.\033[0m"
            )

    # ─── attempt ─────────────────────────────────────────────────────────

    async def _handle_attempt(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        try:
            from engine.chain_events import (
                get_active_step_info, on_skill_check_passed,
            )
            from engine.skill_checks import perform_skill_check
        except ImportError:
            await ctx.session.send_line(
                "  Chain progression engine unavailable.")
            return

        info = get_active_step_info(char)
        if info is None:
            await ctx.session.send_line(
                "  You have no active tutorial chain.")
            return

        ctype = info.get("completion_type")
        if ctype != "skill_check_passed":
            # Tell the player what they actually need to do.
            type_hint_msg = {
                "talk_to_npc": "Talk to the appropriate NPC to "
                "advance.",
                "combat_won": "Defeat the appropriate target to "
                "advance.",
                "command_executed": "Run the indicated command to "
                "advance.",
                "room_entered": "Travel to the indicated location "
                "to advance.",
                "mission_accepted": "Accept the indicated mission "
                "to advance.",
                "mission_completed": "Complete the indicated "
                "mission to advance.",
                "bounty_accepted": "Accept the indicated bounty to "
                "advance.",
                "item_acquired": "Acquire the indicated item to "
                "advance.",
                "item_used": "Use the indicated item to advance.",
                "prerequisite": "A specific game-state event "
                "advances this step automatically.",
            }.get(ctype, "")
            await ctx.session.send_line(
                f"  \033[1;33mThis step does not use 'chain "
                f"attempt'.\033[0m"
            )
            if type_hint_msg:
                await ctx.session.send_line(f"  {type_hint_msg}")
            await ctx.session.send_line(
                "  (Type \033[1;33mchain status\033[0m for "
                "details.)"
            )
            return

        comp = info.get("completion") or {}
        skill = (comp.get("skill") or "").strip().lower()
        difficulty = comp.get("difficulty")

        if not skill or not isinstance(difficulty, int):
            log.warning(
                "[F.8.c.2.b₆] chain attempt: malformed completion "
                "on step %s of chain %s: %r",
                info.get("step"), info.get("chain_id"), comp,
            )
            await ctx.session.send_line(
                "  This step's skill check is misconfigured. "
                "Please notify staff."
            )
            return

        # Location guard. If the step authored a `location` slug, the
        # player must be in that room to attempt. This prevents
        # `chain attempt` from being spammable from anywhere; the
        # skill check is supposed to represent an in-fiction
        # attempt at a specific moment.
        #
        # Best-effort: if location resolution fails, fall through
        # and allow the attempt (don't soft-lock players on a
        # location lookup quirk).
        location_slug = (info.get("location") or "").strip()
        if location_slug:
            try:
                # The room slug lives in properties JSON. The
                # _get_active_step matcher already knows how to
                # resolve a slug to a room id; we re-do the check
                # here without touching the matcher.
                from engine.chain_events import _match_room_entered
                # We can fake the room-match by reading the
                # player's current room properties.
                row = await ctx.db._db.execute_fetchall(
                    "SELECT properties FROM rooms WHERE id = ?",
                    (char.get("room_id"),),
                )
                if row:
                    import json as _j
                    try:
                        props = _j.loads(row[0]["properties"] or "{}")
                        cur_slug = props.get("slug", "")
                    except Exception:
                        cur_slug = ""
                    if cur_slug and cur_slug != location_slug:
                        await ctx.session.send_line(
                            f"  \033[1;33mThis isn't the right "
                            f"place.\033[0m"
                        )
                        await ctx.session.send_line(
                            f"  The step expects you at: "
                            f"\033[1m{location_slug}\033[0m. "
                            f"You're at: \033[1m{cur_slug}\033[0m."
                        )
                        return
            except Exception:
                log.debug(
                    "[F.8.c.2.b₆] location guard skipped: lookup "
                    "failed", exc_info=True,
                )

        # Roll.
        try:
            result = perform_skill_check(char, skill, int(difficulty))
        except Exception:
            log.warning(
                "[F.8.c.2.b₆] perform_skill_check raised on "
                "skill=%s diff=%s for char_id=%s",
                skill, difficulty, char.get("id"), exc_info=True,
            )
            await ctx.session.send_line(
                "  The roll could not be resolved. Please notify "
                "staff."
            )
            return

        # Player-facing render of the roll.
        outcome_str = (
            "\033[1;32mSUCCESS\033[0m" if result.success
            else "\033[1;31mFAILURE\033[0m"
        )
        await ctx.session.send_line(
            f"  You attempt {skill} (vs difficulty {difficulty}) "
            f"with {result.pool_str}: rolled "
            f"\033[1m{result.roll}\033[0m — {outcome_str}."
        )
        if result.critical_success:
            await ctx.session.send_line(
                "  \033[1;36mWild Die exploded — "
                "critical success!\033[0m"
            )
        elif result.fumble:
            await ctx.session.send_line(
                "  \033[1;31mWild Die fumbled — "
                "complication!\033[0m"
            )

        # Dispatch to chain_events. Success advances; failure is a
        # hard no-match (we handle the on_fail / fallback path
        # below, not the dispatcher).
        try:
            advanced = await on_skill_check_passed(
                ctx.db, char, skill, result.success,
                difficulty=difficulty,
            )
        except Exception:
            log.warning(
                "[F.8.c.2.b₆] on_skill_check_passed dispatch "
                "raised", exc_info=True,
            )
            advanced = False

        if result.success and advanced:
            # Chain advanced. Render the standard graduation hint;
            # the next step's narration shows on the next look.
            await ctx.session.send_line(
                "  \033[1;36mYou advance to the next step of "
                "your chain.\033[0m"
            )
            # F.8.c.2.c: graduation teleport hook (no-op if no
            # graduation pending).
            try:
                from engine.chain_graduation import (
                    execute_pending_teleport,
                )
                await execute_pending_teleport(ctx, char)
            except Exception:
                log.debug(
                    "[F.8.c.2.b₆] graduation teleport hook "
                    "raised", exc_info=True,
                )
            return

        if result.success and not advanced:
            # Should not happen on a correctly-authored chain; log
            # and let the player retry.
            log.warning(
                "[F.8.c.2.b₆] skill_check_passed succeeded but "
                "no chain step advanced — chain authoring "
                "mismatch? char_id=%s skill=%s",
                char.get("id"), skill,
            )
            await ctx.session.send_line(
                "  (The roll succeeded but no chain step advanced. "
                "If this persists, notify staff.)"
            )
            return

        # FAILURE path — drive on_fail / fallback.
        await self._handle_failure(ctx, char, comp, result)

    async def _handle_failure(
        self, ctx: CommandContext, char: dict, comp: dict, result,
    ) -> None:
        """Render failure consequences per the authored completion.

        completion dict supports:
          on_fail: "abort_step_no_retry"
                   — step cannot be retried; player must seek
                     alternative path (typically narrated by the
                     step's `npc_complete` text for the failure
                     route).
          fallback: { type: <other_completion_type>, ... }
                   — secondary completion path; the player should
                     pursue that path instead. We narrate the
                     fallback to the player; it advances via its
                     own hook when satisfied.
          on_fail_narrative: "<text>"
                   — flavor line shown after the fallback hint.

        With none of the above, the player can simply re-roll (run
        `chain attempt` again).
        """
        on_fail = comp.get("on_fail")
        fallback = comp.get("fallback")
        narrative = comp.get("on_fail_narrative")

        if on_fail == "abort_step_no_retry":
            await ctx.session.send_line(
                "  \033[1;31mThis attempt cannot be retried.\033[0m"
            )
            if narrative:
                await ctx.session.send_line(f"  \033[2m{narrative}\033[0m")
            return

        if isinstance(fallback, dict) and fallback:
            ftype = fallback.get("type", "")
            ftype_msg = {
                "combat_won": "Defeat the relevant target to "
                "complete this step the hard way.",
                "skill_check_passed": (
                    f"Try a different skill: "
                    f"\033[1m{fallback.get('skill', '?')}\033[0m "
                    f"vs difficulty "
                    f"\033[1m{fallback.get('difficulty', '?')}\033[0m. "
                    f"Type \033[1;33mchain attempt\033[0m to "
                    f"roll it."
                ),
            }.get(ftype, f"Pursue the {ftype} fallback path.")
            await ctx.session.send_line(
                f"  \033[1;33mFallback available:\033[0m {ftype_msg}"
            )
            if narrative:
                await ctx.session.send_line(f"  \033[2m{narrative}\033[0m")
            return

        # Default: retry permitted, no narration constraint.
        await ctx.session.send_line(
            "  \033[2mYou can try again when you're ready.\033[0m"
        )


# ─── registration ─────────────────────────────────────────────────────────


def register_chain_commands(registry) -> None:
    """Register the `chain` command with the given CommandRegistry.

    Called from server/game_server.py during registry init. No
    collisions with existing keys.
    """
    registry.register(ChainCommand())
