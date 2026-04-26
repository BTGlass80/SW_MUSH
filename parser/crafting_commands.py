"""
parser/crafting_commands.py — SW_MUSH Crafting Commands (Phase 3)

Commands: survey, resources, schematics, craft, experiment, teach, buyresources

All skill checks go through engine.skill_checks.perform_skill_check().
Items created via engine.items.ItemInstance.new_crafted().

NPC sell integration: sell <item> to Kayson (weapons) or Heist (consumables)
is handled by the existing SellCommand in builtin_commands.py, which will
check quality and apply pricing. This module creates the item; selling uses
the existing Bargain pattern.

Fix (Apr 2026): Ported entire file from legacy ctx.character / ctx.send()
API to current CommandContext API (ctx.session.character, ctx.session.send_line).
All commands now inherit BaseCommand with key/aliases. register_crafting_commands
uses registry.register(). _save_char uses ctx.db directly.
TeachCommand target-lookup uses ctx.session_mgr.all.

Session 24: ExperimentCommand rewritten — now operates on equipped weapon,
axis selection, breakdown dice, Cracken's jury-rigging rules (WEG40046).
"""

import json
import logging
import random
from parser.commands import BaseCommand, CommandContext
from engine.crafting import (
    get_all_schematics,
    get_known_schematics,
    add_known_schematic,
    can_craft,
    resolve_craft,
    get_survey_resources,
    survey_quality_from_margin,
    add_resource,
    _get_resource_list,
    quality_to_stats,
    # Experimentation engine (Session 24)
    get_experiment_params,
    get_experiment_axes,
    get_max_experiments,
    get_experiment_difficulty,
    resolve_experiment_result,
    resolve_experiment_failure,
    get_schematic,
)

log = logging.getLogger(__name__)

# Achievement hooks (graceful-drop)
async def _ach_craft_hook(db, char_id, event, session=None, **kw):
    try:
        from engine.achievements import check_achievement
        await check_achievement(db, char_id, event, session=session, **kw)
    except Exception as _e:
        log.debug("silent except in parser/crafting_commands.py:56: %s", _e, exc_info=True)


# ---------------------------------------------------------------------------
# Lazy imports of game infrastructure (avoids circular at load time)
# ---------------------------------------------------------------------------

def _skill_check(char, skill, difficulty):
    from engine.skill_checks import perform_skill_check
    return perform_skill_check(char, skill, difficulty)


def _new_crafted_item(key, quality, crafter, max_condition):
    from engine.items import ItemInstance
    return ItemInstance.new_crafted(key, quality, crafter, max_condition)


def _give_item_to_char(ctx, item):
    """Place an ItemInstance into the character's carried items via game_server registry."""
    try:
        ctx.session.items.append(item)
    except AttributeError as _e:
        log.debug("silent except in parser/crafting_commands.py:78: %s", _e, exc_info=True)


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------

class SurveyCommand(BaseCommand):
    """
    survey
    Search the environment for raw resources. Uses the Search skill.
    Outdoor zones yield metal + organic; city zones yield chemical + energy.
    """
    key = "survey"
    aliases = []
    help_text = (
        "Usage: survey\n"
        "Search your surroundings for raw crafting materials.\n"
        "Outdoor areas yield metal and organic components.\n"
        "City areas yield chemical and energy components.\n"
        "Higher Search skill -> better quality finds."
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in to survey.")
            return

        # Cooldown check: 5 minutes between surveys
        from engine.cooldowns import (
            remaining_cooldown, set_cooldown, format_remaining,
            CD_SURVEY, SURVEY_COOLDOWN_S,
        )
        rem = remaining_cooldown(char, CD_SURVEY)
        if rem > 0:
            await ctx.session.send_line(
                f"  You've surveyed recently. Try again in {format_remaining(rem)}."
            )
            return

        room = await ctx.db.get_room(char["room_id"])
        # Use room name for outdoor/indoor classification — room names contain
        # zone keywords like "Jundland", "Outskirts", "Desert" that
        # get_survey_resources uses to determine resource types.
        room_name = (room or {}).get("name", "city")

        # Skill check: Search vs difficulty 8
        try:
            result = _skill_check(char, "search", 8)
            if result.fumble:
                # Still apply cooldown on fumble
                set_cooldown(char, CD_SURVEY, SURVEY_COOLDOWN_S)
                await ctx.db.save_character(
                    char["id"], attributes=char["attributes"]
                )
                await ctx.session.send_line(
                    "  You search around but find nothing of use."
                    f"  [Search: {result.pool_str} vs 8 — fumble]"
                )
                return
            quality = survey_quality_from_margin(result.margin)
            margin_note = f"[Search: {result.pool_str} vs 8 — roll {result.roll}, margin {result.margin}]"
        except Exception:
            quality = 50
            margin_note = "[auto]"

        resources = get_survey_resources(room_name, quality)
        if not resources:
            await ctx.session.send_line("  Nothing useful here.")
            return

        added = []
        for r in resources:
            add_resource(char, r["type"], r["amount"], r["quality"])
            added.append(f"{r['amount']}x {r['type']} (q{r['quality']})")

        # Apply cooldown + save
        set_cooldown(char, CD_SURVEY, SURVEY_COOLDOWN_S)
        await ctx.session.send_line(
            f"  You find: {', '.join(added)}. {margin_note}"
        )
        await _save_char(ctx)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class ResourcesCommand(BaseCommand):
    """List available crafting resources."""
    key = "resources"
    aliases = ["res"]
    help_text = "List your available crafting resources."

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        res_list = _get_resource_list(char)
        if not res_list:
            await ctx.session.send_line(
                "  You have no crafting resources. Try the 'survey' command."
            )
            return

        lines = ["  Crafting Resources:"]
        for r in res_list:
            lines.append(
                f"    {r['type']:16s} x{r['amount']:3d}  quality {r['quality']}"
            )
        await ctx.session.send_line("\n".join(lines))


# ---------------------------------------------------------------------------
# Schematics
# ---------------------------------------------------------------------------

class SchematicsCommand(BaseCommand):
    """List known crafting schematics."""
    key = "schematics"
    aliases = ["schem"]
    help_text = "List your known crafting schematics."

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        known = get_known_schematics(char)
        all_schem = get_all_schematics()

        if not known:
            await ctx.session.send_line(
                "  You don't know any schematics. Talk to a trainer to learn some."
            )
            return

        lines = ["  Known Schematics:"]
        for key in known:
            schem = all_schem.get(key)
            if schem:
                reqs = schem.get("resource_requirements", {})
                req_str = ", ".join(f"{v}x {k}" for k, v in reqs.items())
                lines.append(
                    f"    {schem['name']:24s}  [{schem.get('skill','craft')}]  "
                    f"Needs: {req_str or 'none'}"
                )

        await ctx.session.send_line("\n".join(lines))


# ---------------------------------------------------------------------------
# Craft
# ---------------------------------------------------------------------------

class CraftCommand(BaseCommand):
    """Craft an item from a known schematic."""
    key = "craft"
    aliases = []
    help_text = (
        "Craft an item from a schematic.\n"
        "Usage: craft <schematic name>\n"
        "See 'schematics' for your known recipes."
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        if not ctx.args:
            await ctx.session.send_line(
                "  Usage: craft <schematic name>  (see 'schematics' for options)"
            )
            return

        known = get_known_schematics(char)
        schematic = _find_schematic(ctx.args, known)
        if schematic is None:
            await ctx.session.send_line(
                f"  You don't know a schematic matching '{ctx.args}'."
            )
            return

        ok, reason = can_craft(char, schematic)
        if not ok:
            await ctx.session.send_line(f"  {reason}")
            return

        # Skill check
        skill = schematic.get("skill", "repair")
        difficulty = schematic.get("difficulty", 10)
        try:
            result = _skill_check(char, skill, difficulty)
            quality_base = survey_quality_from_margin(result.margin)
            roll_note = (
                f"[{skill}: {result.pool_str} vs {difficulty} — "
                f"roll {result.roll}, margin {result.margin}]"
            )
        except Exception:
            result = None
            quality_base = 60
            roll_note = "[auto]"

        craft_result = resolve_craft(char, schematic, quality_base)
        await ctx.session.send_line(
            f"  {roll_note}\n  {craft_result['message']}"
        )

        if craft_result["success"]:
            await _deliver_item(ctx, schematic, craft_result)
            try:
                from engine.narrative import log_action, ActionType as NT
                _q = craft_result.get("quality", 0)
                await log_action(ctx.db, char["id"], NT.CRAFT_COMPLETE,
                                 f"Crafted {schematic['name']} (quality {_q:.0f})",
                                 {"schematic": schematic["name"], "quality": _q})
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
            try:
                from engine.ships_log import log_event as _clog
                await _clog(ctx.db, char, "crafting_complete")
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
            try:
                from engine.tutorial_v2 import check_profession_chains
                await check_profession_chains(ctx.session, ctx.db, "craft_complete")
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
            # From Dust to Stars: craft hook
            try:
                from engine.spacer_quest import check_spacer_quest
                await check_spacer_quest(ctx.session, ctx.db, "craft")
            except Exception:
                pass  # graceful-drop

        await _save_char(ctx)


# ---------------------------------------------------------------------------
# Experiment  (Session 24 — Cracken's Jury-Rigging, WEG40046)
# ---------------------------------------------------------------------------

class ExperimentCommand(BaseCommand):
    """
    Modify your equipped weapon's stats through experimental tuning.

    Each experiment picks a stat axis (damage, accuracy, durability) and
    rolls a skill check. Success boosts the chosen axis with a tradeoff
    on another axis. Each experiment also adds a breakdown die — rolled
    on every combat use. If a breakdown die shows 1, the weapon may
    malfunction, jam, or even explode.

    Based on WEG D6 jury-rigging rules (Cracken's Rebel Field Guide).
    """
    key = "experiment"
    aliases = ["exp"]
    help_text = (
        "Modify your equipped weapon through experimental tuning.\n"
        "\n"
        "USAGE:\n"
        "  experiment              — Show help and equipped weapon status\n"
        "  experiment list         — Show available axes and experiment history\n"
        "  experiment <axis>       — Experiment on the chosen axis\n"
        "\n"
        "AXES (weapons):\n"
        "  damage     — Galven Pattern Upgrade (damage ↑ / durability ↓)\n"
        "  accuracy   — Beam Calibration (accuracy ↑ / damage ↓)\n"
        "  durability — Reinforced Housing (durability ↑ / no tradeoff)\n"
        "\n"
        "Each experiment adds a breakdown die. Modified weapons may\n"
        "malfunction during combat. Max 3 experiments per weapon.\n"
        "\n"
        "EXAMPLES:\n"
        "  experiment list\n"
        "  experiment damage\n"
        "  experiment accuracy"
    )
    usage = "experiment [list | <axis>]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        args = (ctx.args or "").strip().lower()

        # Phase 1: Resolve equipped weapon + schematic + params
        prep = await self._prep_weapon_and_schematic(ctx, char)
        if prep is None:
            return
        item, schematic, axes, max_exp = prep

        # Phase 2: No args / "list" → show status and return
        if not args or args == "list":
            await self._show_experiment_status(
                ctx, item, schematic, axes, max_exp)
            return

        # Phase 3: Cooldown + max-experiments gates
        from engine.cooldowns import (
            remaining_cooldown, set_cooldown, format_remaining,
        )
        CD_EXPERIMENT = "experiment"
        EXPERIMENT_COOLDOWN_S = 60           # 1 minute between experiments
        EXPERIMENT_FAIL_COOLDOWN_S = 300     # 5 minutes on failure

        if not await self._check_gates(
                ctx, char, item, max_exp, CD_EXPERIMENT):
            return

        # Phase 4: Match axis argument
        axis_def = self._match_axis(args, axes)
        if axis_def is None:
            axis_names = ", ".join(a["axis"] for a in axes)
            await ctx.session.send_line(
                f"  Unknown axis '{args}'. Available: {axis_names}\n"
                f"  Type 'experiment list' to see options.")
            return

        # Phase 5: Perform the skill check
        params = get_experiment_params(schematic)
        skill = params.get("skill_override") or schematic.get(
            "skill_required", "repair")
        difficulty = get_experiment_difficulty(
            schematic, item.experiment_count)
        result = await self._run_skill_check(ctx, char, skill, difficulty)
        if result is None:
            return

        # Phase 6: Dispatch by outcome
        if result.fumble or (not result.success and result.margin <= -5):
            await self._handle_fumble(
                ctx, char, item, result, params,
                set_cooldown, format_remaining,
                CD_EXPERIMENT, EXPERIMENT_FAIL_COOLDOWN_S)
            return

        if not result.success:
            await self._handle_regular_failure(
                ctx, char, item, result,
                set_cooldown, format_remaining,
                CD_EXPERIMENT, EXPERIMENT_FAIL_COOLDOWN_S)
            return

        await self._handle_success(
            ctx, char, item, result, axis_def, max_exp,
            set_cooldown, CD_EXPERIMENT, EXPERIMENT_COOLDOWN_S)

    # ── Phase helpers ────────────────────────────────────────────────

    async def _prep_weapon_and_schematic(self, ctx, char):
        """Parse equipment, verify not-broken, locate schematic + params.

        Returns (item, schematic, axes, max_exp) or None (error already sent).
        """
        from engine.items import parse_equipment_json
        item = parse_equipment_json(char.get("equipment", "{}"))
        if not item:
            await ctx.session.send_line(
                "  You don't have a weapon equipped. "
                "Equip one first with 'equip <weapon>'.")
            return None
        if item.is_broken:
            await ctx.session.send_line(
                "  Your weapon is broken. Repair it before experimenting.")
            return None

        schematic = _find_schematic_by_output_key(item.key)
        if not schematic:
            await ctx.session.send_line(
                "  This weapon cannot be experimentally modified "
                "(no schematic found).")
            return None

        params = get_experiment_params(schematic)
        axes = params.get("axes", [])
        max_exp = params.get("max_experiments", 3)
        return item, schematic, axes, max_exp

    async def _check_gates(self, ctx, char, item, max_exp, CD_EXPERIMENT):
        """Cooldown + max-experiments gate. Returns True if cleared."""
        from engine.cooldowns import remaining_cooldown, format_remaining
        rem = remaining_cooldown(char, CD_EXPERIMENT)
        if rem > 0:
            await ctx.session.send_line(
                f"  You need to wait before experimenting again. "
                f"Ready in {format_remaining(rem)}.")
            return False
        if item.experiment_count >= max_exp:
            await ctx.session.send_line(
                f"  This weapon has already been modified "
                f"{item.experiment_count} times "
                f"(max {max_exp}). No further experiments possible.")
            return False
        return True

    def _match_axis(self, args, axes):
        """Match axis by exact name, 1-based index, or prefix of axis/label."""
        for ax in axes:
            if args == ax["axis"] or args == str(axes.index(ax) + 1):
                return ax
            if (ax["axis"].startswith(args)
                    or ax["label"].lower().startswith(args)):
                return ax
        return None

    async def _run_skill_check(self, ctx, char, skill, difficulty):
        """Run the skill check, echo the roll note to the player.
        Returns the result object or None (error already sent)."""
        try:
            result = _skill_check(char, skill, difficulty)
        except Exception:
            log.warning(
                "ExperimentCommand: skill check failed", exc_info=True)
            await ctx.session.send_line(
                "  Something went wrong with the skill check.")
            return None
        roll_note = (
            f"[{skill} (experimental): {result.pool_str} vs {difficulty} — "
            f"roll {result.roll}, margin {result.margin}]")
        await ctx.session.send_line(f"  {roll_note}")
        return result

    async def _handle_fumble(self, ctx, char, item, result, params,
                             set_cooldown, format_remaining,
                             CD_EXPERIMENT, EXPERIMENT_FAIL_COOLDOWN_S):
        """Fumble or margin-≤-5 failure: roll on breakdown table."""
        from engine.items import serialize_equipment
        breakdown_type = params.get("breakdown_type", "lethal")
        outcome = resolve_experiment_failure(result.margin, breakdown_type)
        set_cooldown(char, CD_EXPERIMENT, EXPERIMENT_FAIL_COOLDOWN_S)

        if outcome == "exploded":
            char["equipment"] = "{}"
            await ctx.db.save_character(char["id"], equipment="{}")
            await ctx.session.send_line(
                f"  \033[1;31m*BOOM*\033[0m Your {_weapon_name(item.key)} "
                f"explodes in a shower of sparks and molten metal! "
                f"The weapon is destroyed.")
            await ctx.session.send_line(
                f"  \033[1;33mYou take minor burns from the explosion.\033[0m")
        elif outcome == "broken":
            char["equipment"] = "{}"
            await ctx.db.save_character(char["id"], equipment="{}")
            await ctx.session.send_line(
                f"  \033[1;31m*CRACK*\033[0m Critical components shatter. "
                f"Your {_weapon_name(item.key)} is destroyed beyond repair.")
        elif outcome == "jammed":
            item.apply_jam()
            char["equipment"] = serialize_equipment(item)
            await ctx.db.save_character(
                char["id"], equipment=char["equipment"])
            await ctx.session.send_line(
                f"  \033[1;33m*CLUNK*\033[0m Something goes wrong but you "
                f"catch it. The weapon is damaged but still functional. "
                f"(max condition now {item.max_condition})")
        elif outcome == "quality_loss":
            loss = abs(result.margin) * 2
            item.quality = max(1, item.quality - loss)
            char["equipment"] = serialize_equipment(item)
            await ctx.db.save_character(
                char["id"], equipment=char["equipment"])
            await ctx.session.send_line(
                f"  The experiment fails. Your tinkering degrades the "
                f"weapon's overall quality. (quality now {item.quality})")
        else:
            # "fine" — fumble but lucky on the breakdown table
            await ctx.session.send_line(
                f"  The experiment fails, but the weapon survives intact. "
                f"Close call.")

        await ctx.session.send_line(
            f"  Experiment cooldown: "
            f"{format_remaining(EXPERIMENT_FAIL_COOLDOWN_S)}.")
        await _save_char(ctx)

    async def _handle_regular_failure(self, ctx, char, item, result,
                                      set_cooldown, format_remaining,
                                      CD_EXPERIMENT,
                                      EXPERIMENT_FAIL_COOLDOWN_S):
        """Non-fumble failure: small quality loss, fail-cooldown applied."""
        from engine.items import serialize_equipment
        loss = abs(result.margin) * 2
        item.quality = max(1, item.quality - loss)
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        set_cooldown(char, CD_EXPERIMENT, EXPERIMENT_FAIL_COOLDOWN_S)
        await ctx.session.send_line(
            f"  The experiment doesn't work out. Your tinkering "
            f"slightly degrades the weapon. (quality {item.quality})\n"
            f"  Retry in {format_remaining(EXPERIMENT_FAIL_COOLDOWN_S)}.")
        await _save_char(ctx)

    async def _handle_success(self, ctx, char, item, result, axis_def,
                              max_exp, set_cooldown,
                              CD_EXPERIMENT, EXPERIMENT_COOLDOWN_S):
        """Success (or crit): apply boost + tradeoff, persist, narrate,
        log to narrative memory."""
        from engine.items import serialize_equipment
        exp_result = resolve_experiment_result(
            result.margin, axis_def, is_critical=result.critical_success)

        item.add_experiment(
            exp_result["axis"],
            exp_result["boost"],
            exp_result.get("tradeoff"),
        )

        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        set_cooldown(char, CD_EXPERIMENT, EXPERIMENT_COOLDOWN_S)

        # Narrate the success
        crit_prefix = ""
        if result.critical_success:
            crit_prefix = "\033[1;36m★ CRITICAL SUCCESS ★\033[0m "
        boost_str = f"+{exp_result['boost']:.1f} {exp_result['axis']}"
        tradeoff_str = ""
        if exp_result.get("tradeoff"):
            for taxis, tval in exp_result["tradeoff"].items():
                tradeoff_str = f", {tval:+.1f} {taxis}"

        await ctx.session.send_line(
            f"  {crit_prefix}\033[1;32m⚡ EXPERIMENT SUCCESS\033[0m — "
            f"{exp_result['label']}\n"
            f"  Your {_weapon_name(item.key)} has been modified. "
            f"({boost_str}{tradeoff_str})\n"
            f"  Experiments: {item.experiment_count}/{max_exp} | "
            f"Breakdown dice: {item.breakdown_dice}")

        # Breakdown warning
        if item.breakdown_dice == 1:
            await ctx.session.send_line(
                f"  \033[2m⚠ This weapon now has 1 breakdown die. Each "
                f"combat use risks malfunction.\033[0m")
        elif item.breakdown_dice > 1:
            await ctx.session.send_line(
                f"  \033[1;33m⚠ This weapon now has {item.breakdown_dice} "
                f"breakdown dice. Combat malfunction risk is significant."
                f"\033[0m")

        # Log to narrative memory
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(
                ctx.db, char["id"], NT.CRAFT_COMPLETE,
                f"Experimented on {_weapon_name(item.key)}: "
                f"{exp_result['label']} ({boost_str})",
                {"weapon": item.key, "axis": exp_result["axis"],
                 "boost": exp_result["boost"]},
            )
        except Exception:
            log.warning(
                "ExperimentCommand: narrative log failed", exc_info=True)

        await _save_char(ctx)

    async def _show_experiment_status(self, ctx, item, schematic, axes, max_exp):
        """Display experiment status, available axes, and history for equipped weapon."""
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        wpn = wr.get(item.key)
        wpn_name = wpn.name if wpn else item.key

        lines = [
            f"  \033[1;36m═══════════════════════════════════════════════════\033[0m",
            f"  \033[1mEXPERIMENTATION\033[0m — {wpn_name} "
            f"(Quality: {item.quality}){item.mod_label}",
            f"  Crafter: {item.crafter or 'Unknown'}    "
            f"Experiments: {item.experiment_count}/{max_exp}    "
            f"Breakdown dice: {item.breakdown_dice}",
            f"  \033[1;36m───────────────────────────────────────────────────\033[0m",
        ]

        if item.experiment_count >= max_exp:
            lines.append(
                f"  \033[1;33mThis weapon has reached its modification limit.\033[0m"
            )
        else:
            diff = get_experiment_difficulty(schematic, item.experiment_count)
            lines.append(f"  Next experiment difficulty: {diff}")
            lines.append(f"")
            lines.append(f"  \033[1mAVAILABLE AXES:\033[0m")

            for i, ax in enumerate(axes, 1):
                tradeoff_note = ""
                if ax.get("tradeoff_axis"):
                    tradeoff_note = f" / {ax['tradeoff_axis']} ↓"
                current_mod = item.get_mod(ax["axis"])
                mod_str = ""
                if current_mod != 0:
                    mod_str = f"  (current: {current_mod:+.1f})"
                lines.append(
                    f"    {i}. {ax['label']:25s} [{ax['axis']} ↑{tradeoff_note}]{mod_str}"
                )

        if item.experiment_log:
            lines.append(f"")
            lines.append(f"  \033[1mEXPERIMENT LOG:\033[0m")
            for i, entry in enumerate(item.experiment_log, 1):
                boost_str = f"+{entry['boost']:.1f} {entry['axis']}"
                tradeoff_str = ""
                if entry.get("tradeoff"):
                    for taxis, tval in entry["tradeoff"].items():
                        tradeoff_str = f", {tval:+.1f} {taxis}"
                lines.append(f"    #{i}: {boost_str}{tradeoff_str}")

        # Show accumulated effective modifiers
        if item.effective_mods:
            lines.append(f"")
            lines.append(f"  \033[1mEFFECTIVE MODIFIERS:\033[0m")
            for mod_key, val in sorted(item.effective_mods.items()):
                axis_name = mod_key.replace("_mod", "")
                color = "\033[1;32m" if val > 0 else "\033[1;31m"
                lines.append(f"    {axis_name:12s} {color}{val:+.1f}\033[0m")

        lines.append(
            f"  \033[1;36m═══════════════════════════════════════════════════\033[0m"
        )

        if item.experiment_count < max_exp:
            lines.append(f"  Usage: experiment <axis>  (e.g. experiment damage)")

        await ctx.session.send_line("\n".join(lines))


# ---------------------------------------------------------------------------
# Teach
# ---------------------------------------------------------------------------

class TeachCommand(BaseCommand):
    """Teach a schematic to another player in the room."""
    key = "teach"
    aliases = []
    help_text = (
        "Teach a known schematic to another player.\n"
        "Usage: teach <player> <schematic>"
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        args = (ctx.args or "").strip()
        parts = args.split(None, 1)
        if len(parts) < 2:
            await ctx.session.send_line("  Usage: teach <player> <schematic>")
            return

        target_name, schem_arg = parts[0], parts[1].strip()

        # Find target session in same room via session_mgr
        target_session = None
        for sess in ctx.session_mgr.all:
            if (sess.character and
                    sess.character.get("name", "").lower() == target_name.lower() and
                    sess.character.get("room_id") == char.get("room_id")):
                target_session = sess
                break

        if target_session is None:
            await ctx.session.send_line(
                f"  {target_name} is not here. You need to be in the same room to teach."
            )
            return

        target_char = target_session.character

        # Check teacher knows the schematic
        schematic = _find_schematic(schem_arg, get_known_schematics(char))
        if schematic is None:
            await ctx.session.send_line(
                f"  You don't know a schematic matching '{schem_arg}'."
            )
            return

        added = add_known_schematic(target_char, schematic["key"])
        if not added:
            await ctx.session.send_line(
                f"  {target_char.get('name')} already knows the {schematic['name']} schematic."
            )
            return

        char_name = char.get("name", "Someone")
        tgt_name = target_char.get("name", "them")

        await ctx.session.send_line(
            f"  You take time to teach {tgt_name} the {schematic['name']} schematic."
        )
        try:
            await target_session.send_line(
                f"  {char_name} teaches you the {schematic['name']} schematic. "
                f"[Added to your known schematics]"
            )
        except Exception:
            log.warning("TeachCommand: send to target failed", exc_info=True)

        # Save target character
        try:
            await ctx.db.save_character(target_char["id"])
        except Exception:
            log.warning("TeachCommand: target save failed", exc_info=True)

        await _save_char(ctx)


# ---------------------------------------------------------------------------
# NPC Trainer helper (called by npc_commands.py when player talks to a trainer NPC)
# ---------------------------------------------------------------------------

async def handle_trainer_teach(ctx: CommandContext, npc_name: str) -> bool:
    """
    Called from npc_commands.py TalkCommand when the NPC is a schematic trainer.
    Grants all schematics whose trainer_npc matches this NPC name.
    Returns True if any schematics were taught, False otherwise.
    """
    char = ctx.session.character
    if not char:
        return False

    all_schem = get_all_schematics()
    taught = []
    already_known = []

    for key, schem in all_schem.items():
        if schem.get("trainer_npc", "").lower() == npc_name.lower():
            added = add_known_schematic(char, key)
            if added:
                taught.append(schem["name"])
            else:
                already_known.append(schem["name"])

    if taught:
        await ctx.session.send_line(
            f"  {npc_name} shows you some techniques. You learn: {', '.join(taught)}."
        )
    if already_known:
        await ctx.session.send_line(
            f"  You already know: {', '.join(already_known)}."
        )
    if taught or already_known:
        await _save_char(ctx)
        return True
    return False


# ---------------------------------------------------------------------------
# Consumable item creation helper
# ---------------------------------------------------------------------------

_CONSUMABLE_STATS = {
    "medpac": {
        "name": "Medpac",
        "heal_wounds": 1,
        "description": "A standard bacta medpac.",
    },
    "medpac_advanced": {
        "name": "Advanced Medpac",
        "heal_wounds": 2,
        "description": "A high-grade medpac with concentrated bacta.",
    },
    "stimpack": {
        "name": "Field Stimpack",
        "heal_wounds": 1,
        "stun_only": True,
        "description": "A stimpack for rapid field stabilisation (stun damage only).",
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_schematic(arg: str, known_keys: list) -> dict | None:
    """
    Find a schematic by partial name or exact key match from the player's known list.
    """
    all_schem = get_all_schematics()
    arg_lower = arg.lower().strip()

    matches = []
    for key in known_keys:
        schem = all_schem.get(key)
        if not schem:
            continue
        if arg_lower == key or arg_lower == schem["name"].lower():
            return schem
        if schem and arg_lower in schem["name"].lower():
            matches.append(schem)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        matches.sort(key=lambda s: len(s["name"]))
        return matches[0]
    return None


def _find_schematic_by_output_key(output_key: str) -> dict | None:
    """Find a schematic whose output_key matches the given weapon key."""
    all_schem = get_all_schematics()
    for key, schem in all_schem.items():
        if schem.get("output_key") == output_key:
            return schem
    return None


def _weapon_name(weapon_key: str) -> str:
    """Get display name for a weapon key, falling back to the key itself."""
    try:
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        wpn = wr.get(weapon_key)
        if wpn:
            return wpn.name
    except Exception as _e:
        log.debug("silent except in parser/crafting_commands.py:863: %s", _e, exc_info=True)
    return weapon_key.replace("_", " ").title()


async def _deliver_item(ctx: CommandContext, schematic: dict, craft_result: dict):
    """
    Create the finished item and add it to the character's inventory.
    For consumables, creates a consumable token in attributes.
    For weapons, creates an ItemInstance via items.py.
    """
    char = ctx.session.character
    output_key  = schematic["output_key"]
    output_type = schematic["output_type"]
    quality     = craft_result["quality"]
    crafter     = craft_result["crafter_name"]
    stats       = craft_result["stats"]

    max_condition = stats.get("max_condition", 100)

    if output_type == "weapon":
        try:
            item = _new_crafted_item(output_key, quality, crafter, max_condition)
            try:
                ctx.session.items.append(item)
            except AttributeError as _e:
                log.debug("silent except in parser/crafting_commands.py:888: %s", _e, exc_info=True)
            await ctx.session.send_line(
                f"  The {schematic['name']} has been added to your inventory. "
                f"(max_condition: {max_condition})"
            )
        except Exception as e:
            await ctx.session.send_line(
                f"  Item created but could not be placed in inventory: {e}. "
                f"Contact an admin."
            )

    elif output_type == "consumable":
        attrs = char.get("attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}
        if not isinstance(attrs, dict):
            attrs = {}

        consumables = attrs.setdefault("consumables", {})
        current = consumables.get(output_key, 0)
        consumables[output_key] = current + 1
        char["attributes"] = json.dumps(attrs)

        display_name = _CONSUMABLE_STATS.get(output_key, {}).get("name", output_key)
        await ctx.session.send_line(
            f"  The {display_name} has been added to your consumables. "
            f"(quality {quality:.0f}/100)"
        )

    elif output_type == "component":
        # Ship component — stored as a dict in the character's inventory JSON list.
        # +ship/install reads items where item["type"] == "ship_component".
        # Fields: type, key, name, quality, stat_target, stat_boost,
        #         cargo_weight, craft_difficulty.
        inv_raw = char.get("inventory", "[]")
        try:
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
            if not isinstance(inv, list):
                inv = []
        except Exception:
            inv = []

        component_item = {
            "type":             "ship_component",
            "key":              output_key,
            "name":             schematic["name"],
            "quality":          round(quality, 1),
            "stat_target":      schematic.get("stat_target", ""),
            "stat_boost":       schematic.get("stat_boost", 1),
            "cargo_weight":     schematic.get("cargo_weight", 10),
            "craft_difficulty": schematic.get("difficulty", 16),
            "crafter":          crafter,
        }
        inv.append(component_item)
        char["inventory"] = json.dumps(inv)

        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your inventory as a "
            f"ship component. (quality {quality:.0f}/100)"
        )
        await ctx.session.send_line(
            f"  Use '+ship/install {schematic['name']}' while docked to install it."
        )

    elif output_type == "survival_gear":
        # Survival gear — durable items stored in inventory, mitigate hazards.
        # Checked by engine/hazards.py _has_mitigation() against item key.
        inv_raw = char.get("inventory", "[]")
        try:
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
            if not isinstance(inv, list):
                inv = []
        except Exception:
            inv = []

        gear_item = {
            "type":     "survival_gear",
            "key":      output_key,
            "name":     schematic["name"],
            "quality":  round(quality, 1),
            "crafter":  crafter,
            "uses":     schematic.get("max_uses", 0),  # 0 = unlimited
            "max_uses": schematic.get("max_uses", 0),
        }
        inv.append(gear_item)
        char["inventory"] = json.dumps(inv)

        uses_str = f" ({schematic.get('max_uses', 0)} uses)" if schematic.get("max_uses") else " (durable)"
        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your inventory{uses_str}. "
            f"(quality {quality:.0f}/100)"
        )
        await ctx.session.send_line(
            f"  \033[2mThis item mitigates environmental hazards when carried.\033[0m"
        )


async def _save_char(ctx: CommandContext):
    """Best-effort character save."""
    try:
        char = ctx.session.character
        if char:
            await ctx.db.save_character(char["id"])
    except Exception:
        log.warning("_save_char: unhandled exception", exc_info=True)


def _quality_desc(quality: float) -> str:
    if quality >= 90:
        return "Masterwork"
    if quality >= 80:
        return "Superior"
    if quality >= 65:
        return "Good"
    if quality >= 50:
        return "Standard"
    if quality >= 30:
        return "Poor"
    return "Salvage"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_crafting_commands(registry) -> None:
    """Register all crafting commands with the command registry."""
    for cmd in [
        CraftingCommand(),
        SurveyCommand(),
        ResourcesCommand(),
        SchematicsCommand(),
        CraftCommand(),
        ExperimentCommand(),
        TeachCommand(),
        BuyResourcesCommand(),
    ]:
        registry.register(cmd)


# S56: Switch & alias dispatch tables for the +craft umbrella.
_CRAFT_SWITCH_IMPL: dict = {}

_CRAFT_ALIAS_TO_SWITCH: dict[str, str] = {
    # start (the bare 'craft' verb begins crafting from a schematic)
    "craft":         "start",
    "start":         "start",
    # survey
    "survey":        "survey",
    # resources
    "resources":     "resources",
    "res":           "resources",
    # schematics
    "schematics":    "schematics",
    "schem":         "schematics",
    # experiment
    "experiment":    "experiment",
    "exp":           "experiment",
    # teach
    "teach":         "teach",
    # buyresources
    "buyresources":  "buyresources",
    "buyres":        "buyresources",
    "buy resources": "buyresources",
}


class CraftingCommand(BaseCommand):
    """`+craft` umbrella — full S56 dispatch over crafting verbs."""
    key = "+craft"
    aliases: list[str] = [
        "craft",
        "survey",
        "resources", "res",
        "schematics", "schem",
        "experiment", "exp",
        "teach",
        "buyresources", "buyres",
    ]
    help_text = (
        "Crafting verbs: '+craft/start <schematic>', '+craft/survey', "
        "'+craft/resources', '+craft/schematics', '+craft/experiment', "
        "'+craft/teach', '+craft/buyresources'. Bare verbs (craft/"
        "survey/...) still work. Type 'help +craft' for the full reference."
    )
    usage = "+craft[/<switch>] [args]  — see 'help +craft'"
    valid_switches: list[str] = [
        "start", "survey", "resources", "schematics",
        "experiment", "teach", "buyresources",
    ]

    async def execute(self, ctx: CommandContext):
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            switch = _CRAFT_ALIAS_TO_SWITCH.get(
                ctx.command.lower() if ctx.command else "",
                "survey",
            )
        impl_cls = _CRAFT_SWITCH_IMPL.get(switch)
        if impl_cls is None:
            await ctx.session.send_line(self.help_text)
            return
        await impl_cls().execute(ctx)


def _init_craft_switch_impl():
    _CRAFT_SWITCH_IMPL["start"]        = CraftCommand
    _CRAFT_SWITCH_IMPL["survey"]       = SurveyCommand
    _CRAFT_SWITCH_IMPL["resources"]    = ResourcesCommand
    _CRAFT_SWITCH_IMPL["schematics"]   = SchematicsCommand
    _CRAFT_SWITCH_IMPL["experiment"]   = ExperimentCommand
    _CRAFT_SWITCH_IMPL["teach"]        = TeachCommand
    _CRAFT_SWITCH_IMPL["buyresources"] = BuyResourcesCommand


# NOTE: _init_craft_switch_impl() called at end of file (after
# BuyResourcesCommand is defined).


# ---------------------------------------------------------------------------
# NPC Resource Vendor  (Economy Hardening v23)
# ---------------------------------------------------------------------------

# Fixed vendor prices — establishes a floor so surveying isn't the only
# (free) path to crafting materials. Quality 50 = middling; survey can
# yield better quality for free at the cost of time and skill investment.

NPC_RESOURCE_PRICES = {
    "metal":     15,
    "chemical":  20,
    "electronic": 25,
    "organic":   10,
    "composite": 30,
    "energy":    20,
}
NPC_RESOURCE_QUALITY = 50.0


class BuyResourcesCommand(BaseCommand):
    """Buy crafting resources from an NPC vendor."""
    key = "buyresources"
    aliases = ["buy resources", "buyres", "+buyres"]
    help_text = (
        "Buy crafting resources from an NPC materials vendor.\n"
        "\n"
        "Available at locations with a mechanic or crafting station.\n"
        "Resources are standard quality (50). Survey yields better\n"
        "quality for free, but takes time and skill.\n"
        "\n"
        "USAGE:\n"
        "  buyresources               — show prices\n"
        "  buyresources <type> <qty>  — buy resources\n"
        "\n"
        "TYPES: metal, chemical, electronic, organic, composite, energy\n"
        "\n"
        "EXAMPLES:\n"
        "  buyresources metal 10\n"
        "  buyresources chemical 5"
    )
    usage = "buyresources [<type> <qty>]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be logged in.")
            return

        # Check room has mechanic/crafting service
        has_vendor = False
        try:
            room_id = char.get("room_id")
            npcs = await ctx.db.get_npcs_in_room(room_id) if hasattr(ctx.db, "get_npcs_in_room") else []
            for npc in (npcs or []):
                npc_name = (npc.get("name") or "").lower()
                npc_ai = ""
                try:
                    ai_raw = npc.get("ai_config_json") or npc.get("ai_config") or "{}"
                    if isinstance(ai_raw, str):
                        ai_data = json.loads(ai_raw)
                    else:
                        ai_data = ai_raw if isinstance(ai_raw, dict) else {}
                    npc_ai = str(ai_data.get("role", "")).lower()
                except Exception as _e:
                    log.debug("silent except in parser/crafting_commands.py:1094: %s", _e, exc_info=True)
                if any(kw in npc_name or kw in npc_ai
                       for kw in ("mechanic", "technician", "engineer", "shipwright")):
                    has_vendor = True
                    break
            # Also check room properties for crafting service
            if not has_vendor:
                try:
                    room = await ctx.db.get_room(room_id)
                    if room:
                        props = json.loads(room.get("properties") or "{}")
                        env = props.get("environment", "")
                        if env in ("workshop", "forge", "crafting"):
                            has_vendor = True
                except Exception as _e:
                    log.debug("silent except in parser/crafting_commands.py:1109: %s", _e, exc_info=True)
        except Exception:
            log.warning("BuyResourcesCommand: room check failed", exc_info=True)

        if not has_vendor:
            await ctx.session.send_line(
                "  No materials vendor here. Look for a mechanic or workshop."
            )
            return

        args = (ctx.args or "").strip().split()

        # No args → show price list
        if not args:
            lines = [
                "  \033[1;36m── NPC Resource Vendor ──────────────────\033[0m",
                "  Standard quality (50). Survey can yield better.",
                "",
                f"  {'Type':<14} {'Price':>8}",
                f"  {'────':<14} {'─────':>8}",
            ]
            for rtype, price in sorted(NPC_RESOURCE_PRICES.items()):
                lines.append(f"  {rtype:<14} {price:>6} cr/unit")
            lines.append("")
            lines.append("  Usage: buyresources <type> <quantity>")
            lines.append("  \033[1;36m────────────────────────────────────────\033[0m")
            await ctx.session.send_line("\n".join(lines))
            return

        if len(args) < 2:
            await ctx.session.send_line(
                "  Usage: buyresources <type> <quantity>\n"
                "  Example: buyresources metal 10\n"
                "  Type 'buyresources' to see prices."
            )
            return

        rtype = args[0].lower()
        try:
            qty = int(args[1])
        except ValueError:
            await ctx.session.send_line(f"  '{args[1]}' isn't a valid quantity.")
            return

        if rtype not in NPC_RESOURCE_PRICES:
            await ctx.session.send_line(
                f"  Unknown resource type '{rtype}'.\n"
                f"  Available: {', '.join(sorted(NPC_RESOURCE_PRICES.keys()))}"
            )
            return

        if qty < 1:
            await ctx.session.send_line("  Quantity must be at least 1.")
            return
        if qty > 100:
            await ctx.session.send_line("  Maximum 100 units per purchase.")
            return

        price_per = NPC_RESOURCE_PRICES[rtype]
        total_cost = price_per * qty
        credits = char.get("credits", 0)

        if credits < total_cost:
            await ctx.session.send_line(
                f"  Not enough credits. {qty}x {rtype} costs {total_cost:,} cr, "
                f"you have {credits:,} cr."
            )
            return

        # Execute purchase
        char["credits"] = credits - total_cost
        await ctx.db.save_character(char["id"], credits=char["credits"])

        result_msg = add_resource(char, rtype, qty, NPC_RESOURCE_QUALITY)
        # Save inventory
        try:
            inv_raw = char.get("inventory", "{}")
            if isinstance(inv_raw, str):
                inv_data = json.loads(inv_raw)
            else:
                inv_data = inv_raw if isinstance(inv_raw, dict) else {}
            await ctx.db.save_character(char["id"], inventory=json.dumps(inv_data))
        except Exception:
            log.warning("BuyResourcesCommand: inventory save failed", exc_info=True)

        await ctx.session.send_line(
            f"  \033[1;32m[PURCHASE]\033[0m {qty}x {rtype} (q{NPC_RESOURCE_QUALITY:.0f}) "
            f"for {total_cost:,} cr. Balance: {char['credits']:,} cr."
        )
        await ctx.session.send_line(f"  {result_msg}")

        # Credit log
        try:
            await ctx.db.log_credit(char["id"], -total_cost, "resource_vendor",
                                     char["credits"])
        except Exception:
            log.warning("BuyResourcesCommand: credit log failed", exc_info=True)


# ── S56: populate _CRAFT_SWITCH_IMPL after BuyResourcesCommand is defined ──
_init_craft_switch_impl()
