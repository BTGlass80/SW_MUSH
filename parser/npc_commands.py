# -*- coding: utf-8 -*-
"""
NPC interaction and management commands.

Player commands:
  talk <npc>                   - Start talking to an NPC
  ask <npc> about <topic>      - Ask an NPC about something

Builder commands:
  @npc create <name>           - Create an NPC in the current room
  @npc personality <id> = <text> - Set NPC personality
  @npc knowledge <id> = <text> - Add knowledge to an NPC
  @npc faction <id> = <text>   - Set NPC faction
  @npc style <id> = <text>     - Set dialogue style
  @npc tier <id> = <1|2|3>     - Set model tier
  @npc desc <id> = <text>      - Set NPC description
  @npc fallback <id> = <text>  - Add a fallback line
  @npc delete <id>             - Delete an NPC
  @npc list                    - List NPCs in current room
  @npc info <id>               - Show NPC details

Admin commands:
  @ai status                   - Show AI provider status
  @ai enable / @ai disable     - Toggle AI system
"""
import json
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel
from parser.crafting_commands import handle_trainer_teach
from ai.npc_brain import NPCBrain, NPCData, NPCConfig
from engine.npc_generator import (
    generate_npc, list_archetypes, get_archetype_info,
    format_npc_sheet, NPCTier,
)
from server import ansi
from engine.skill_checks import perform_skill_check
from engine.character import Character
from engine.dice import DicePool

log = logging.getLogger(__name__)


def _safe_json_loads(value, default=None):
    """Parse JSON from a string, returning `default` on malformed input."""
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as _e:
        log.warning("Malformed NPC JSON: %s", _e)
        return default


# Persuasion difficulty for NPC dialogue
_PERSUASION_DIFFICULTY = 10

# Words that mark a message as substantive (triggers skill check)
_QUESTION_WORDS = frozenset([
    "what", "where", "when", "who", "why", "how", "tell",
    "know", "heard", "about", "job", "work", "sell", "buy",
    "hire", "need", "help", "information", "rumor", "rumour",
    "price", "cost", "deal", "discount", "info", "news",
])

# Cache of active NPC brains (npc_id -> NPCBrain)
_npc_brains: dict[int, NPCBrain] = {}


def _get_brain(npc_data: NPCData, ai_manager) -> NPCBrain:
    """Get or create a brain for an NPC."""
    if npc_data.id not in _npc_brains:
        _npc_brains[npc_data.id] = NPCBrain(npc_data, ai_manager)
    return _npc_brains[npc_data.id]


async def _handle_skill_trainer(ctx, npc_data, char) -> bool:
    """
    If this NPC is a skill trainer (ai_config has trainer=True + train_skills),
    display the skills they teach with current values and CP costs, then return True.
    Cost formula matches TrainCommand exactly: total_pool.dice (with guild discount).
    """
    try:
        raw = npc_data.ai_config
        ai_cfg = (json.loads(raw) if isinstance(raw, str) else
                  (raw.__dict__ if hasattr(raw, '__dict__') else {})) or {}
    except Exception:
        log.warning("_handle_skill_trainer: unhandled exception", exc_info=True)
        return False

    if not ai_cfg.get("trainer") or not ai_cfg.get("train_skills"):
        return False

    train_skills = ai_cfg["train_skills"]

    from parser.cp_commands import _get_skill_reg

    char_row = await ctx.db.get_character(char["id"])
    if not char_row:
        return False
    character = Character.from_db_row(char_row)
    skill_reg = _get_skill_reg()
    cp = character.character_points

    # Guild multiplier (matches TrainCommand)
    guild_mult = 1.0
    try:
        from engine.organizations import get_guild_cp_multiplier
        guild_mult = await get_guild_cp_multiplier(char, ctx.db)
    except Exception:
        log.warning("_handle_skill_trainer: unhandled exception", exc_info=True)
        pass

    await ctx.session.send_line(
        f"  {ansi.BRIGHT_CYAN}{npc_data.name}{ansi.RESET} "
        f"{ansi.DIM}offers training in:{ansi.RESET}"
    )
    await ctx.session.send_line("")

    for skill_name in train_skills:
        skill_def = skill_reg.get(skill_name.lower())
        if not skill_def:
            continue
        key = skill_name.lower()
        current_bonus = character.skills.get(key, DicePool(0, 0))
        attr_pool = character.get_attribute(skill_def.attribute)
        total_pool = attr_pool + current_bonus
        cost = max(1, int(total_pool.dice * guild_mult))
        current_str = str(total_pool)
        next_str = str(attr_pool + DicePool(current_bonus.dice, current_bonus.pips + 1))
        affordable = cp >= cost
        status = (f"{ansi.BRIGHT_GREEN}\u2713 can afford{ansi.RESET}"
                  if affordable
                  else f"{ansi.RED}need {cost} CP{ansi.RESET}")
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_WHITE}{skill_name.replace('_', ' ').title():<32}{ansi.RESET}"
            f"  {current_str:<8} {ansi.DIM}\u2192{ansi.RESET} {next_str:<8}"
            f"  {ansi.BRIGHT_YELLOW}{cost} CP{ansi.RESET}  [{status}]"
        )

    await ctx.session.send_line("")
    await ctx.session.send_line(
        f"  {ansi.DIM}You have {ansi.RESET}{ansi.BRIGHT_YELLOW}{cp} CP{ansi.RESET}"
        f"{ansi.DIM}.  Use {ansi.RESET}{ansi.BRIGHT_CYAN}train <skill>{ansi.RESET}"
        f"{ansi.DIM} to spend CP and advance a skill.{ansi.RESET}"
    )
    return True


async def _find_npc_in_room(ctx, name: str):
    """Find an NPC by name in the current room using centralized matcher."""
    from engine.matching import match_in_room, MatchResult
    match = await match_in_room(
        name,
        ctx.session.character["room_id"],
        ctx.session.character["id"],
        ctx.db,
        include_characters=False,
        include_objects=False,
    )
    if match.found and match.candidate.obj_type == "npc":
        return match.candidate.data
    if match.result == MatchResult.AMBIGUOUS:
        await ctx.session.send_line(f"  {match.error_message(name)}")
    return None


class TalkCommand(BaseCommand):
    key = "talk"
    aliases = []
    help_text = "Talk to an NPC in the room."
    usage = "talk <npc> <message>  |  talk <npc> (starts conversation)"

    async def execute(self, ctx: CommandContext):
        """Orchestrator: list NPCs / resolve target / tutorial or dialogue path."""
        if not ctx.args:
            await self._list_npcs(ctx)
            return

        parts = ctx.args.split(None, 1)
        npc_name = parts[0]
        message = parts[1] if len(parts) > 1 else "Hello."

        npc_row = await _find_npc_in_room(ctx, npc_name)
        if not npc_row:
            await ctx.session.send_line(f"  You don't see '{npc_name}' here.")
            return

        ai_manager = self._resolve_ai_manager(ctx)
        if not ai_manager:
            await ctx.session.send_line(
                f"  {ansi.npc_name(npc_row['name'])} stares at you blankly.")
            return

        npc_data = NPCData.from_db_row(npc_row)
        brain = _get_brain(npc_data, ai_manager)

        char = ctx.session.character
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f'  {ansi.player_name(char["name"])} says to {ansi.npc_name(npc_data.name)}, "{message}"',
        )

        # Tutorial NPC fast-path
        result = await self._handle_tutorial_npc(
            ctx, char, npc_row, npc_data, brain, message)
        if result is not None:
            return

        # Trainer hooks — fires before Persuasion gate
        if await handle_trainer_teach(ctx, npc_name):
            return
        if await _handle_skill_trainer(ctx, npc_data, char):
            return

        # Persuasion + faction standing → AI dialogue
        persuasion_context = await self._run_persuasion_check(ctx, char, message)
        persuasion_context = await self._inject_faction_context(
            ctx, char, npc_data, persuasion_context)

        await self._generate_and_display(
            ctx, char, npc_data, brain, ai_manager, message, persuasion_context)

        await self._post_talk_hooks(ctx, char, npc_row)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _list_npcs(self, ctx):
        """List NPCs in the room when no argument given."""
        room_id = ctx.session.character["room_id"]
        npcs = await ctx.db.get_npcs_in_room(room_id)
        if not npcs:
            await ctx.session.send_line("  There's no one to talk to here.")
            return
        await ctx.session.send_line("  NPCs here:")
        for npc in npcs:
            await ctx.session.send_line(f"    {ansi.npc_name(npc['name'])}")
        await ctx.session.send_line("  Usage: talk <npc> <message>")

    def _resolve_ai_manager(self, ctx):
        """Get AI manager from context or session_mgr."""
        ai_manager = getattr(ctx, '_ai_manager', None)
        if not ai_manager:
            ai_manager = getattr(ctx.session_mgr, '_ai_manager', None)
        return ai_manager

    async def _run_persuasion_check(self, ctx, char, message):
        """Run persuasion skill check for substantive questions. Returns context string."""
        words = message.lower().split()
        is_substantive = (
            len(words) > 3
            or "?" in message
            or bool(_QUESTION_WORDS & set(words))
        )
        if not is_substantive:
            return ""

        try:
            result = perform_skill_check(
                char, "persuasion", _PERSUASION_DIFFICULTY)
            if result.fumble:
                await ctx.session.send_line(
                    f"  {ansi.DIM}[Persuasion: {result.pool_str} vs {_PERSUASION_DIFFICULTY} "
                    f"— roll {result.roll}, fumble]{ansi.RESET}")
                return (
                    "SOCIAL CONTEXT: The player approached this very poorly. "
                    "You are offended or suspicious. Be curt, dismissive, or "
                    "openly hostile. Give nothing away. End the conversation "
                    "if your character would.")
            elif not result.success:
                await ctx.session.send_line(
                    f"  {ansi.DIM}[Persuasion: {result.pool_str} vs {_PERSUASION_DIFFICULTY} "
                    f"— roll {result.roll}, failed]{ansi.RESET}")
                return (
                    "SOCIAL CONTEXT: The player did not make a strong impression. "
                    "Be guarded and non-committal. Give only the bare minimum. "
                    "Do not volunteer extra information.")
            elif result.critical_success:
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_GREEN}[Persuasion: {result.pool_str} vs {_PERSUASION_DIFFICULTY} "
                    f"— roll {result.roll}, critical!]{ansi.RESET}")
                return (
                    "SOCIAL CONTEXT: The player is exceptionally charming or "
                    "persuasive. Be unusually open and forthcoming. Volunteer "
                    "extra detail, a useful rumour, or hint at a discount if "
                    "you are a vendor. Treat them as someone you genuinely "
                    "want to help.")
            else:
                return (
                    "SOCIAL CONTEXT: The player communicated clearly and "
                    "respectfully. Answer their question fully and in good faith. "
                    "Normal cooperative tone.")
        except Exception:
            pass  # Graceful-drop — dialogue still fires without context
        return ""

    async def _inject_faction_context(self, ctx, char, npc_data, persuasion_context):
        """Add faction standing context to persuasion_context. Returns updated string."""
        try:
            npc_faction_raw = (npc_data.ai_config.faction or "").lower()
            if npc_faction_raw:
                _fac_map = {
                    "imperial": "empire", "empire": "empire",
                    "galactic empire": "empire",
                    "rebel": "rebel", "rebel alliance": "rebel",
                    "hutt": "hutt", "hutt cartel": "hutt",
                    "bounty hunter": "bh_guild", "bounty hunters": "bh_guild",
                    "bounty hunters' guild": "bh_guild",
                }
                npc_fc = _fac_map.get(npc_faction_raw, "")
                if npc_fc:
                    from engine.organizations import (
                        get_char_faction_rep, get_faction_standing_context,
                    )
                    _player_rep = await get_char_faction_rep(char, npc_fc, ctx.db)
                    _standing_ctx = get_faction_standing_context(
                        npc_faction_raw, _player_rep)
                    if _standing_ctx:
                        persuasion_context = (
                            (persuasion_context + "\n" + _standing_ctx)
                            if persuasion_context else _standing_ctx)
        except Exception:
            log.warning("_inject_faction_context: failed", exc_info=True)
        return persuasion_context

    async def _generate_and_display(self, ctx, char, npc_data, brain,
                                     ai_manager, message, persuasion_context):
        """Show thinking emote, call AI brain, display NPC response."""
        if ai_manager.config.npc_thinking_emote:
            await ctx.session.send_line(
                f"  {ansi.dim(f'{npc_data.name} considers...')}")

        room = await ctx.db.get_room(char["room_id"])
        room_desc = room.get("desc_short", "") if room else ""

        response = await brain.dialogue(
            player_input=message,
            player_name=char["name"],
            player_char_id=char["id"],
            room_desc=room_desc,
            db=ctx.db,
            persuasion_context=persuasion_context,
        )

        response = response.strip().strip('"').strip("'").strip('\u201c').strip('\u201d')
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f'  {ansi.npc_name(npc_data.name)} says, "{response}"',
        )

    async def _handle_tutorial_npc(self, ctx, char, npc_row, npc_data, brain, message):
        """Handle tutorial NPC fast-path: scripted greetings + AI response."""
        # ── Tutorial NPC fast path ────────────────────────────────────
        # Tutorial NPCs bypass persuasion and get a scripted first-contact
        # line prepended to the AI response so new players get immediate
        # actionable guidance without waiting on Ollama.
        ai_cfg_raw = npc_row.get("ai_config_json", "{}")
        ai_cfg_dict = _safe_json_loads(ai_cfg_raw, default={}) or {}
        is_tutorial_npc = ai_cfg_dict.get("tutorial_npc", False)

        if is_tutorial_npc:
            persuasion_context = ""  # no persuasion gate for tutorial NPCs
            tutorial_role = ai_cfg_dict.get("tutorial_role", "guide")
            tutorial_module = ai_cfg_dict.get("tutorial_module", "")

            # Scripted first-contact lines by role+module
            _TUTORIAL_GREETINGS = {
                ("guide", "core"): (
                    "Good -- you made it. "
                    "I'm Kessa. Walk east with me and I'll show you how things work out here. "
                    "Ask me anything: \033[1;33mtalk kessa <question>\033[0m"
                ),
                ("guide", "space"): (
                    "Glad you came. Sit down. "
                    "We're starting with the basics -- ship types, zones, what kills you first. "
                    "When you're ready to move to the simulator, head \033[1;33mforward\033[0m."
                ),
                ("guide", "combat"): (
                    "You want to fight. Good. "
                    "First thing: forget everything you think you know. "
                    "We do this right or we do it again."
                ),
                ("guide", "economy"): (
                    "Credits! You've come to the right place. "
                    "I'm going to show you how money actually moves in this sector. "
                    "Ask me anything -- I love talking about this."
                ),
                ("guide", "crafting"): (
                    "Good. Follow the process, don't skip steps. "
                    "That's the only rule here. "
                    "Tell me what you want to make and we'll start."
                ),
                ("guide", "bounty"): (
                    "You're here to learn the trade. Smart. "
                    "Most hunters don't last because they didn't do their homework. "
                    "Ask your questions."
                ),
                ("guide", "crew"): (
                    "Pull up a chair. I've been running crews for forty years "
                    "and I've got opinions. "
                    "What do you want to know?"
                ),
                ("guide", "factions"): (
                    "Welcome. I am programmed to provide impartial information "
                    "on all major factions operating in this sector. "
                    "Which faction would you like to learn about first?"
                ),
                ("guide", "hub"): (
                    "Welcome to the Training Grounds. "
                    "I can direct you to any module. "
                    "Type \033[1;33mtraining list\033[0m to see your progress, "
                    "or ask me about any module."
                ),
                ("opponent", "core"): None,   # Raiders don't talk
                ("opponent", "space"): None,  # Sim drone doesn't talk
            }
            greeting = _TUTORIAL_GREETINGS.get(
                (tutorial_role, tutorial_module),
                _TUTORIAL_GREETINGS.get(("guide", "hub"), None),
            )

            # Only show greeting on first contact (message is default "Hello.")
            if greeting and message.strip().lower() in ("hello.", "hello", "hi",
                                                         "hey", "greetings", ""):
                await ctx.session.send_line(
                    f'  {ansi.npc_name(npc_data.name)} says, "{greeting}"'
                )
                # Fire tutorial quest hook then return -- no AI call needed for hello
                try:
                    from engine.tutorial_v2 import check_starter_quest
                    await check_starter_quest(
                        ctx.session, ctx.db, trigger="talk",
                        npc_name=npc_row["name"],
                    )
                except Exception:
                    log.warning("execute: unhandled exception", exc_info=True)
                    pass
                try:
                    from engine.tutorial_v2 import check_profession_chains
                    _nname = npc_row["name"].lower()
                    if "kessa" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_kessa")
                    elif "dash" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_dash")
                    elif "ssk" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_sskrath")
                    elif "vek" in _nname or "nurren" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_vek")
                    elif "gep" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_gep")
                    elif "kreel" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_kreel")
                    elif "rebel" in _nname or "fulcrum" in _nname or "contact" in _nname:
                        await check_profession_chains(ctx.session, ctx.db, "talk_rebel_contact")
                except Exception:
                    log.warning("execute: unhandled exception", exc_info=True)
                    pass
                return

            # For substantive questions, let AI handle it but skip persuasion roll
            if ai_manager.config.npc_thinking_emote:
                await ctx.session.send_line(
                    f"  {ansi.dim(f'{npc_data.name} considers...')}"
                )
            room = await ctx.db.get_room(char["room_id"])
            room_desc = room.get("desc_short", "") if room else ""
            response = await brain.dialogue(
                player_input=message,
                player_name=char["name"],
                player_char_id=char["id"],
                room_desc=room_desc,
                db=ctx.db,
                persuasion_context="",
            )
            # Strip any quotes the LLM wrapped around its response
            response = response.strip().strip('"').strip("'").strip('\u201c').strip('\u201d')
            await ctx.session_mgr.broadcast_to_room(
                char["room_id"],
                f'  {ansi.npc_name(npc_data.name)} says, "{response}"',
            )
            try:
                from engine.tutorial_v2 import check_starter_quest
                await check_starter_quest(
                    ctx.session, ctx.db, trigger="talk",
                    npc_name=npc_row["name"],
                )
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass
            try:
                from engine.tutorial_v2 import check_profession_chains
                _nname2 = npc_row["name"].lower()
                if "kessa" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_kessa")
                elif "dash" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_dash")
                elif "ssk" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_sskrath")
                elif "vek" in _nname2 or "nurren" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_vek")
                elif "gep" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_gep")
                elif "kreel" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_kreel")
                elif "rebel" in _nname2 or "fulcrum" in _nname2 or "contact" in _nname2:
                    await check_profession_chains(ctx.session, ctx.db, "talk_rebel_contact")
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass
            return
        # ── End tutorial NPC fast path ────────────────────────────────

        # ── Persuasion skill gate ──────────────────────────────────────


    async def _post_talk_hooks(self, ctx, char, npc_row):
        """Post-talk effects: tutorial quest + spacer quest checks."""
        # Tutorial starter quest: talking to an NPC
        try:
            from engine.tutorial_v2 import check_starter_quest
            await check_starter_quest(
                ctx.session, ctx.db,
                trigger="talk",
                npc_name=npc_row["name"],
            )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Spacer quest: talking to an NPC
        try:
            from engine.spacer_quest import check_spacer_quest
            _nroom = await ctx.db.get_room(ctx.session.character.get("room_id", 0))
            await check_spacer_quest(
                ctx.session, ctx.db, "talk",
                npc_name=npc_row["name"],
                room_name=_nroom.get("name", "") if _nroom else "",
                room_id=ctx.session.character.get("room_id", 0),
            )
        except Exception as _e:
            log.debug("silent except in parser/npc_commands.py:513: %s", _e, exc_info=True)



class AskCommand(BaseCommand):
    key = "ask"
    aliases = []
    help_text = "Ask an NPC about a topic."
    usage = "ask <npc> about <topic>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or " about " not in ctx.args.lower():
            await ctx.session.send_line("Usage: ask <npc> about <topic>")
            await ctx.session.send_line("  ask wuher about the cantina")
            await ctx.session.send_line("  ask trooper about the imperial garrison")
            return

        # Split on "about"
        idx = ctx.args.lower().index(" about ")
        npc_name = ctx.args[:idx].strip()
        topic = ctx.args[idx + 7:].strip()

        npc_row = await _find_npc_in_room(ctx, npc_name)
        if not npc_row:
            await ctx.session.send_line(f"  You don't see '{npc_name}' here.")
            return

        # Rewrite as a talk with a question
        ctx.args = f"{npc_name} What can you tell me about {topic}?"
        talk = TalkCommand()
        await talk.execute(ctx)


# ── Builder NPC Management ──

class NPCManageCommand(BaseCommand):
    key = "@npc"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Create and manage NPCs."
    usage = "@npc <subcommand> [args]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await self._show_help(ctx)
            return

        parts = ctx.args.split(None, 1)
        subcmd = parts[0].lower()
        subargs = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "create": self._create, "delete": self._delete,
            "list": self._list, "info": self._info,
            "generate": self._generate, "gen": self._generate,
            "personality": self._set_field, "knowledge": self._add_knowledge,
            "faction": self._set_field, "style": self._set_field,
            "tier": self._set_tier, "desc": self._set_desc,
            "fallback": self._add_fallback, "move": self._move,
            "hostile": self._set_hostile, "behavior": self._set_behavior,
            "weapon": self._set_weapon, "heal": self._heal_npc, "heal": self._heal_npc, "heal": self._heal_npc,
        }
        handler = handlers.get(subcmd)
        if handler:
            await handler(ctx, subargs, subcmd)
        else:
            await ctx.session.send_line(f"  Unknown subcommand: '{subcmd}'")
            await self._show_help(ctx)

    async def _show_help(self, ctx):
        archetypes = ", ".join(list_archetypes())
        lines = [
            "  @npc create <name>             - Create blank NPC here",
            "  @npc gen <tier> <type> [name]   - Auto-generate NPC with stats",
            "    Tiers: extra, average, novice, veteran, superior",
            f"    Types: {archetypes}",
            "  @npc list                      - List NPCs in this room",
            "  @npc info <#id>                - Show NPC details",
            "  @npc personality <#id> = <text> - Set personality",
            "  @npc knowledge <#id> = <text>  - Add knowledge",
            "  @npc faction <#id> = <text>    - Set faction",
            "  @npc style <#id> = <text>      - Set dialogue style",
            "  @npc tier <#id> = <1|2|3>      - Set model tier",
            "  @npc desc <#id> = <text>       - Set description",
            "  @npc fallback <#id> = <text>   - Add fallback line",
            "  @npc move <#id> = <#room_id>   - Move NPC to room",
            "  @npc hostile <#id> = on|off    - Toggle hostile (attacks on sight)",
            "  @npc behavior <#id> = <type>   - Set combat AI (aggressive/defensive/cowardly/berserk)",
            "  @npc weapon <#id> = <key>      - Set NPC weapon (e.g. blaster_pistol)",
            "  @npc heal <#id>                - Heal NPC to full health",
            "  @npc delete <#id>              - Delete NPC",
        ]
        for line in lines:
            await ctx.session.send_line(line)

    async def _create(self, ctx, args, subcmd):
        if not args:
            await ctx.session.send_line("  Usage: @npc create <name>")
            return
        room_id = ctx.session.character["room_id"]
        default_config = NPCConfig(
            fallback_lines=[
                f"{args} grunts.",
                f"{args} shrugs.",
                f"{args} looks away.",
            ]
        )
        npc_id = await ctx.db.create_npc(
            name=args, room_id=room_id,
            ai_config_json=json.dumps(default_config.to_dict()),
        )
        await ctx.session.send_line(
            ansi.success(f"  NPC '{args}' created as #{npc_id} in this room.")
        )
        await ctx.session.send_line(
            f"  Set personality: @npc personality #{npc_id} = <description>"
        )

    async def _generate(self, ctx, args, subcmd):
        """Auto-generate an NPC using Universe Standard dice budgets."""
        parts = args.split(None, 2) if args else []
        if len(parts) < 2:
            await ctx.session.send_line(
                "  Usage: @npc gen <tier> <archetype> [name]"
            )
            await ctx.session.send_line(
                "  Tiers: extra, average, novice, veteran, superior"
            )
            await ctx.session.send_line(
                "  Types: " + ", ".join(list_archetypes())
            )
            return

        tier_str = parts[0].lower()
        arch_str = parts[1].lower()
        npc_name = parts[2] if len(parts) > 2 else ""

        # Validate tier
        valid_tiers = [t.value for t in NPCTier]
        if tier_str not in valid_tiers:
            await ctx.session.send_line(
                f"  Unknown tier '{tier_str}'. Valid: {', '.join(valid_tiers)}"
            )
            return

        # Validate archetype
        if not get_archetype_info(arch_str):
            await ctx.session.send_line(
                f"  Unknown archetype '{arch_str}'. Valid: {', '.join(list_archetypes())}"
            )
            return

        # Generate stats
        try:
            npc_data = generate_npc(tier_str, arch_str, name=npc_name)
        except Exception as e:
            await ctx.session.send_line(f"  Generation error: {e}")
            return

        # Assign default weapon based on archetype
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_WEAPONS
        weapon_key = DEFAULT_ARCHETYPE_WEAPONS.get(arch_str, "blaster_pistol")
        npc_data["weapon"] = weapon_key

        # Create the NPC in the database
        room_id = ctx.session.character["room_id"]
        final_name = npc_data["name"]

        # Build AI config with archetype personality + combat behavior
        arch = get_archetype_info(arch_str)

        # Determine default combat behavior from archetype
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_BEHAVIOR
        behavior = DEFAULT_ARCHETYPE_BEHAVIOR.get(arch_str, "defensive")

        config = NPCConfig(
            personality=f"A {tier_str} {arch.name}.",
            fallback_lines=[
                f"{final_name} grunts.",
                f"{final_name} shrugs.",
                f"{final_name} says nothing.",
            ],
        )

        # Add combat behavior to ai_config
        ai_dict = config.to_dict()
        ai_dict["combat_behavior"] = behavior
        ai_dict["hostile"] = arch_str in (
            "stormtrooper", "scout_trooper", "dark_jedi", "creature",
        )

        # Store the generated stats as description + char_sheet_json
        stats_summary = []
        for attr_name in ["dexterity", "knowledge", "mechanical",
                          "perception", "strength", "technical"]:
            val = npc_data["attributes"].get(attr_name, "2D")
            stats_summary.append(f"{attr_name[:3].upper()}:{val}")
        skills_summary = "; ".join(
            f"{k} +{v}" for k, v in sorted(npc_data.get("skills", {}).items())
        )
        desc = (
            f"[{tier_str.title()} {arch.name}] "
            + " ".join(stats_summary)
            + f" | Skills: {skills_summary}"
        )

        npc_id = await ctx.db.create_npc(
            name=final_name, room_id=room_id,
            species=npc_data.get("species", "Human"),
            description=desc,
            char_sheet_json=json.dumps(npc_data),
            ai_config_json=json.dumps(ai_dict),
        )

        # Show the result
        await ctx.session.send_line(
            ansi.success(f"  NPC '{final_name}' generated as #{npc_id}")
        )
        for line in format_npc_sheet(npc_data):
            await ctx.session.send_line(line)

    async def _delete(self, ctx, args, subcmd):
        npc_id = self._parse_id(args)
        if not npc_id:
            await ctx.session.send_line("  Usage: @npc delete <#id>")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        await ctx.db.delete_npc(npc_id)
        _npc_brains.pop(npc_id, None)
        await ctx.session.send_line(ansi.success(f"  NPC '{npc['name']}' deleted."))

    async def _list(self, ctx, args, subcmd):
        room_id = ctx.session.character["room_id"]
        npcs = await ctx.db.get_npcs_in_room(room_id)
        if not npcs:
            await ctx.session.send_line("  No NPCs in this room.")
            return
        await ctx.session.send_line(ansi.header("=== NPCs Here ==="))
        for n in npcs:
            cfg = _safe_json_loads(n.get("ai_config_json"), default={}) or {}
            tier = cfg.get("model_tier", 1)
            personality = cfg.get("personality", "(not set)")[:30]
            hostile_flag = ansi.color(" [H]", ansi.BRIGHT_RED) if cfg.get("hostile") else ""
            behavior = cfg.get("combat_behavior", "")
            beh_tag = f" [{behavior[:3]}]" if behavior else ""
            await ctx.session.send_line(
                f"  #{n['id']:4d}  {ansi.npc_name(n['name']):20s}  "
                f"T{tier}{hostile_flag}{beh_tag}  {ansi.dim(personality)}"
            )

    async def _info(self, ctx, args, subcmd):
        npc_id = self._parse_id(args)
        if not npc_id:
            await ctx.session.send_line("  Usage: @npc info <#id>")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        await ctx.session.send_line(ansi.header(f"=== NPC #{npc['id']}: {npc['name']} ==="))
        await ctx.session.send_line(f"  Species: {npc.get('species', 'Human')}")
        await ctx.session.send_line(f"  Room: #{npc['room_id']}")
        await ctx.session.send_line(f"  Description: {npc.get('description', '(none)')}")
        await ctx.session.send_line(f"  Tier: {cfg.get('model_tier', 1)}")
        await ctx.session.send_line(f"  Personality: {cfg.get('personality', '(not set)')}")
        await ctx.session.send_line(f"  Faction: {cfg.get('faction', '(none)')}")
        await ctx.session.send_line(f"  Style: {cfg.get('dialogue_style', '(default)')}")
        # Combat fields
        hostile = cfg.get("hostile", False)
        behavior = cfg.get("combat_behavior", "(not set)")
        await ctx.session.send_line(
            f"  Hostile: {ansi.color('YES', ansi.BRIGHT_RED) if hostile else 'no'}"
            f"  |  Combat AI: {behavior}"
        )
        # Weapon
        cs = _safe_json_loads(npc.get("char_sheet_json"), default={}) or {}
        weapon = cs.get("weapon", "")
        if weapon:
            from engine.weapons import get_weapon_registry
            wr = get_weapon_registry()
            w = wr.get(weapon)
            wname = w.name if w else weapon
            await ctx.session.send_line(f"  Weapon: {wname} ({weapon})")
        has_stats = bool(cs.get("attributes"))
        await ctx.session.send_line(
            f"  Combat stats: {'yes' if has_stats else ansi.dim('none (use @npc gen)')}"
        )
        knowledge = cfg.get("knowledge", [])
        if knowledge:
            await ctx.session.send_line(f"  Knowledge:")
            for k in knowledge:
                await ctx.session.send_line(f"    - {k}")
        fallbacks = cfg.get("fallback_lines", [])
        if fallbacks:
            await ctx.session.send_line(f"  Fallback lines: {len(fallbacks)}")

    async def _set_field(self, ctx, args, subcmd):
        """Set personality, faction, or style."""
        if "=" not in args:
            await ctx.session.send_line(f"  Usage: @npc {subcmd} <#id> = <value>")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        value = value.strip()
        if not npc_id:
            await ctx.session.send_line(f"  Usage: @npc {subcmd} <#id> = <value>")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return

        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        field_map = {
            "personality": "personality",
            "faction": "faction",
            "style": "dialogue_style",
        }
        field_name = field_map.get(subcmd, subcmd)
        cfg[field_name] = value
        await ctx.db.update_npc(npc_id, ai_config_json=json.dumps(cfg))
        _npc_brains.pop(npc_id, None)  # Clear cached brain
        await ctx.session.send_line(ansi.success(f"  {subcmd.capitalize()} set for '{npc['name']}'."))

    async def _add_knowledge(self, ctx, args, subcmd):
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc knowledge <#id> = <fact>")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        value = value.strip()
        if not npc_id:
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        knowledge = cfg.get("knowledge", [])
        knowledge.append(value)
        cfg["knowledge"] = knowledge
        await ctx.db.update_npc(npc_id, ai_config_json=json.dumps(cfg))
        _npc_brains.pop(npc_id, None)
        await ctx.session.send_line(ansi.success(f"  Knowledge added ({len(knowledge)} total)."))

    async def _set_tier(self, ctx, args, subcmd):
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc tier <#id> = <1|2|3>")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        try:
            tier = int(value.strip())
            assert tier in (1, 2, 3)
        except (ValueError, AssertionError):
            await ctx.session.send_line("  Tier must be 1, 2, or 3.")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        cfg["model_tier"] = tier
        await ctx.db.update_npc(npc_id, ai_config_json=json.dumps(cfg))
        _npc_brains.pop(npc_id, None)
        await ctx.session.send_line(ansi.success(f"  Tier set to {tier}."))

    async def _set_desc(self, ctx, args, subcmd):
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc desc <#id> = <description>")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        if not npc_id:
            return
        await ctx.db.update_npc(npc_id, description=value.strip())
        await ctx.session.send_line(ansi.success("  Description set."))

    async def _add_fallback(self, ctx, args, subcmd):
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc fallback <#id> = <line>")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        if not npc_id:
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        lines = cfg.get("fallback_lines", [])
        lines.append(value.strip())
        cfg["fallback_lines"] = lines
        await ctx.db.update_npc(npc_id, ai_config_json=json.dumps(cfg))
        await ctx.session.send_line(ansi.success(f"  Fallback line added ({len(lines)} total)."))

    async def _move(self, ctx, args, subcmd):
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc move <#npc_id> = <#room_id>")
            return
        id_part, room_part = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        room_id = self._parse_id(room_part.strip())
        if not npc_id or not room_id:
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        room = await ctx.db.get_room(room_id)
        if not room:
            await ctx.session.send_line(f"  Room #{room_id} not found.")
            return
        await ctx.db.update_npc(npc_id, room_id=room_id)
        _npc_brains.pop(npc_id, None)
        await ctx.session.send_line(
            ansi.success(f"  '{npc['name']}' moved to '{room['name']}' (#{room_id}).")
        )

    async def _set_hostile(self, ctx, args, subcmd):
        """Toggle hostile flag (NPC attacks players on sight)."""
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc hostile <#id> = on|off")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        value = value.strip().lower()
        if not npc_id:
            await ctx.session.send_line("  Usage: @npc hostile <#id> = on|off")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        cfg["hostile"] = value in ("on", "true", "yes", "1")
        await ctx.db.update_npc(npc_id, ai_config_json=json.dumps(cfg))
        state = "HOSTILE" if cfg["hostile"] else "non-hostile"
        await ctx.session.send_line(
            ansi.success(f"  '{npc['name']}' is now {state}.")
        )

    async def _set_behavior(self, ctx, args, subcmd):
        """Set NPC combat AI behavior profile."""
        if "=" not in args:
            await ctx.session.send_line(
                "  Usage: @npc behavior <#id> = aggressive|defensive|cowardly|berserk|sniper"
            )
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        value = value.strip().lower()
        if not npc_id:
            await ctx.session.send_line(
                "  Usage: @npc behavior <#id> = aggressive|defensive|cowardly|berserk|sniper"
            )
            return
        valid = ["aggressive", "defensive", "cowardly", "berserk", "sniper"]
        if value not in valid:
            await ctx.session.send_line(
                f"  Unknown behavior '{value}'. Valid: {', '.join(valid)}"
            )
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cfg = _safe_json_loads(npc.get("ai_config_json"), default={}) or {}
        cfg["combat_behavior"] = value
        await ctx.db.update_npc(npc_id, ai_config_json=json.dumps(cfg))
        await ctx.session.send_line(
            ansi.success(f"  '{npc['name']}' combat behavior set to {value}.")
        )

    async def _set_weapon(self, ctx, args, subcmd):
        """Set NPC equipped weapon key."""
        if "=" not in args:
            await ctx.session.send_line("  Usage: @npc weapon <#id> = <weapon_key>")
            await ctx.session.send_line("  e.g.: @npc weapon #5 = blaster_rifle")
            return
        id_part, value = args.split("=", 1)
        npc_id = self._parse_id(id_part.strip())
        weapon_key = value.strip().lower()
        if not npc_id:
            await ctx.session.send_line("  Usage: @npc weapon <#id> = <weapon_key>")
            return
        # Validate weapon exists
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        weapon = wr.get(weapon_key)
        if not weapon and weapon_key:
            await ctx.session.send_line(f"  Unknown weapon '{weapon_key}'.")
            available = ", ".join(sorted(w.key for w in wr.all_weapons())[:10])
            await ctx.session.send_line(f"  Some options: {available}")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        # Update char_sheet_json
        cs = _safe_json_loads(npc.get("char_sheet_json"), default={}) or {}
        cs["weapon"] = weapon_key
        await ctx.db.update_npc(npc_id, char_sheet_json=json.dumps(cs))
        wname = weapon.name if weapon else "unarmed"
        await ctx.session.send_line(
            ansi.success(f"  '{npc['name']}' weapon set to {wname}.")
        )

    async def _heal_npc(self, ctx, args, subcmd):
        """Reset NPC wound level to healthy."""
        npc_id = self._parse_id(args.strip())
        if not npc_id:
            await ctx.session.send_line("  Usage: @npc heal <#id>")
            return
        npc = await ctx.db.get_npc(npc_id)
        if not npc:
            await ctx.session.send_line(f"  NPC #{npc_id} not found.")
            return
        cs = _safe_json_loads(npc.get("char_sheet_json"), default={}) or {}
        if not cs.get("attributes"):
            await ctx.session.send_line(
                f"  '{npc['name']}' has no combat stats to heal."
            )
            return
        cs["wound_level"] = 0
        await ctx.db.update_npc(npc_id, char_sheet_json=json.dumps(cs))
        await ctx.session.send_line(
            ansi.success(f"  '{npc['name']}' healed to full health.")
        )

    def _parse_id(self, text: str) -> int:
        try:
            return int(text.lstrip("#"))
        except (ValueError, TypeError):
            return 0


class AIStatusCommand(BaseCommand):
    key = "@ai"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = "Check AI provider status or toggle AI."
    usage = "@ai status  |  @ai enable  |  @ai disable"

    async def execute(self, ctx: CommandContext):
        ai_manager = getattr(ctx.session_mgr, '_ai_manager', None)
        if not ai_manager:
            await ctx.session.send_line("  AI system not initialized.")
            return

        if not ctx.args or ctx.args.strip().lower() == "status":
            status = await ai_manager.check_status()
            await ctx.session.send_line(ansi.header("=== AI Status ==="))
            await ctx.session.send_line(
                f"  Enabled: {'Yes' if ai_manager.config.enabled else 'No'}"
            )
            await ctx.session.send_line(
                f"  Default provider: {ai_manager.config.default_provider}"
            )
            await ctx.session.send_line(
                f"  Default model: {ai_manager.config.default_model}"
            )
            for name, info in status.items():
                avail = ansi.green("ONLINE") if info["available"] else ansi.red("OFFLINE")
                await ctx.session.send_line(f"  Provider '{name}': {avail}")
                if "models" in info:
                    models = ", ".join(info["models"][:10])
                    await ctx.session.send_line(f"    Models: {models}")
        elif ctx.args.strip().lower() == "enable":
            ai_manager.config.enabled = True
            await ctx.session.send_line(ansi.success("  AI system enabled."))
        elif ctx.args.strip().lower() == "disable":
            ai_manager.config.enabled = False
            await ctx.session.send_line(ansi.success("  AI system disabled."))
        else:
            await ctx.session.send_line("  Usage: @ai status  |  @ai enable  |  @ai disable")


def register_npc_commands(registry):
    """Register NPC and AI commands."""
    cmds = [
        TalkCommand(), AskCommand(),
        NPCManageCommand(), AIStatusCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
