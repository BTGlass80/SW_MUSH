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
    check_resources,
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


# CRAFT.P0.2: the former _give_item_to_char helper appended to
# ctx.session.items — an attribute that exists nowhere — inside a swallowed
# AttributeError, so crafted items silently evaporated. All landings now go
# through db.add_to_inventory (which also fires the F.8.c.2.b₂ item_acquired
# tutorial hook the old path bypassed).


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

        # Apply cooldown + save. CRAFT.P1: explicit both-column save —
        # survey mutates inventory (add_resource) AND attributes
        # (set_cooldown) dict-side; the old _save_char persisted neither.
        set_cooldown(char, CD_SURVEY, SURVEY_COOLDOWN_S)
        await ctx.session.send_line(
            f"  You find: {', '.join(added)}. {margin_note}"
        )
        try:
            await ctx.db.save_character(
                char["id"],
                attributes=char["attributes"],
                inventory=char["inventory"],
            )
        except Exception:
            log.warning("survey: save failed", exc_info=True)
        await _push_crafting_state(ctx)


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
            # CRAFT.P0.1 (phantom re-delivery, Bug B2): stacks store
            # 'quantity'; the old r['amount'] bracket-read raised KeyError
            # for any character actually holding resources.
            lines.append(
                f"    {r['type']:16s} x{int(r.get('quantity', 0)):3d}"
                f"  quality {r.get('quality', 0)}"
            )
        await ctx.session.send_line("\n".join(lines))
        await _push_crafting_state(ctx)


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
                # CRAFT.P0.1 (phantom re-delivery, Bug B1): schematics carry
                # 'components' + 'skill_required'; the old code read
                # 'resource_requirements' (no schematic has it) + 'skill',
                # printing "Needs: none" under "[craft]" for all recipes.
                comps = schem.get("components", [])
                req_str = ", ".join(
                    f"{c['quantity']}x {c['type']}"
                    + (f" (q{c['min_quality']}+)" if c.get("min_quality", 1) > 1
                       else "")
                    for c in comps
                )
                craftable, _ = check_resources(char, comps)
                flag = "[*] " if craftable else "    "
                lines.append(
                    f"  {flag}{schem['name']:24s}"
                    f"  [{schem.get('skill_required', 'craft')}]  "
                    f"Needs: {req_str or 'none'}"
                )
        lines.append("  [*] = you have the components to craft this now")

        await ctx.session.send_line("\n".join(lines))
        await _push_crafting_state(ctx)


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

        # CRAFT.P0.1 (phantom re-delivery, Bugs C + D):
        #  C — schematics carry 'skill_required'; the old
        #      schematic.get("skill", "repair") rolled a nonexistent
        #      "repair" skill, dropping every craft to the [auto]
        #      quality-60 path and divorcing quality from crafter skill.
        #  D — resolve_craft requires the SkillCheckResult object; the
        #      old code passed quality_base (a float), so EVERY craft
        #      raised AttributeError('float' has no attribute 'fumble').
        #      The except-branch now builds a clean auto-success result
        #      object instead of None so the fallback path also works.
        skill = schematic.get("skill_required", "repair")
        difficulty = schematic.get("difficulty", 10)
        try:
            result = _skill_check(char, skill, difficulty)
            roll_note = (
                f"[{skill}: {result.pool_str} vs {difficulty} — "
                f"roll {result.roll}, margin {result.margin}]"
            )
        except Exception:
            from types import SimpleNamespace
            log.warning("CraftCommand: skill check failed; using auto path",
                        exc_info=True)
            result = SimpleNamespace(
                success=True, fumble=False, critical_success=False,
                margin=0, roll=0, pool_str="auto",
            )
            roll_note = "[auto]"

        craft_result = resolve_craft(char, schematic, result)

        # CRAFT.P1: resolve_craft consumed components DICT-side
        # (remove_resource → char["inventory"]). Persist that NOW —
        # before _deliver_item, whose db.add_to_inventory does its own
        # DB read-modify-write and must see the post-consumption row.
        # (Saving inventory AFTER delivery would clobber the landed
        # item with this pre-delivery dict.) With the old no-op
        # _save_char, consumption never persisted at all: infinite
        # materials across reload, for every output type.
        try:
            await ctx.db.save_character(
                char["id"], inventory=char["inventory"])
        except Exception:
            log.warning("craft: consumption save failed", exc_info=True)
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

        # Webify UI-8: refresh the crafting panel with the resolved
        # outcome (stocks changed; last_result drives the result banner).
        await _push_crafting_state(ctx, last_result={
            "success": craft_result.get("success", False),
            "partial": craft_result.get("partial", False),
            "fumble":  craft_result.get("fumble", False),
            "quality": craft_result.get("quality", 0),
            "name":    schematic.get("name", ""),
        })
        await _save_char(ctx)


async def _push_crafting_state(ctx: CommandContext, last_result: dict = None):
    """WS-gated crafting_state push (Webify UI-8). Non-blocking — a push
    failure never breaks the text verbs; Telnet falls through silently.
    Same Protocol gate as the UI-4a/UI-5 pushes."""
    try:
        from server.session import Protocol
        if ctx.session.protocol != Protocol.WEBSOCKET:
            return
        from engine.crafting import build_crafting_state
        payload = build_crafting_state(
            ctx.session.character, last_result=last_result)
        await ctx.session.send_json("crafting_state", payload)
    except Exception:
        log.debug("_push_crafting_state failed", exc_info=True)


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
        # Canonical per-slot read (equipment-instance untangle). The old
        # parse_equipment_json returned None under canonical storage, so
        # `experiment` always reported "no weapon equipped".
        from engine.items import read_equipment
        item = read_equipment(char.get("equipment", "{}"))["weapon"]
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
        from engine.items import read_equipment, write_equipment
        breakdown_type = params.get("breakdown_type", "lethal")
        outcome = resolve_experiment_failure(result.margin, breakdown_type)
        set_cooldown(char, CD_EXPERIMENT, EXPERIMENT_FAIL_COOLDOWN_S)
        # Worn armor must survive every fumble outcome — only the weapon
        # slot is at stake. (The old serialize_equipment / "{}" writes
        # clobbered the armor slot.)
        _armor = read_equipment(char.get("equipment", "{}"))["armor"]

        if outcome == "exploded":
            char["equipment"] = write_equipment(weapon=None, armor=_armor)
            await ctx.db.save_character(
                char["id"], equipment=char["equipment"])
            await ctx.session.send_line(
                f"  \033[1;31m*BOOM*\033[0m Your {_weapon_name(item.key)} "
                f"explodes in a shower of sparks and molten metal! "
                f"The weapon is destroyed.")
            await ctx.session.send_line(
                f"  \033[1;33mYou take minor burns from the explosion.\033[0m")
        elif outcome == "broken":
            char["equipment"] = write_equipment(weapon=None, armor=_armor)
            await ctx.db.save_character(
                char["id"], equipment=char["equipment"])
            await ctx.session.send_line(
                f"  \033[1;31m*CRACK*\033[0m Critical components shatter. "
                f"Your {_weapon_name(item.key)} is destroyed beyond repair.")
        elif outcome == "jammed":
            item.apply_jam()
            char["equipment"] = write_equipment(weapon=item, armor=_armor)
            await ctx.db.save_character(
                char["id"], equipment=char["equipment"])
            await ctx.session.send_line(
                f"  \033[1;33m*CLUNK*\033[0m Something goes wrong but you "
                f"catch it. The weapon is damaged but still functional. "
                f"(max condition now {item.max_condition})")
        elif outcome == "quality_loss":
            loss = abs(result.margin) * 2
            item.quality = max(1, item.quality - loss)
            char["equipment"] = write_equipment(weapon=item, armor=_armor)
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
        from engine.items import read_equipment, write_equipment
        loss = abs(result.margin) * 2
        item.quality = max(1, item.quality - loss)
        _armor = read_equipment(char.get("equipment", "{}"))["armor"]
        char["equipment"] = write_equipment(weapon=item, armor=_armor)
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
        from engine.items import read_equipment, write_equipment
        exp_result = resolve_experiment_result(
            result.margin, axis_def, is_critical=result.critical_success)

        item.add_experiment(
            exp_result["axis"],
            exp_result["boost"],
            exp_result.get("tradeoff"),
        )

        _armor = read_equipment(char.get("equipment", "{}"))["armor"]
        char["equipment"] = write_equipment(weapon=item, armor=_armor)
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

        # Find target session in same room via session_mgr.
        # W.2 phase 2: in wilderness, sessions_in_room with source_char
        # restricts to PCs at the same wilderness tile, so cross-tile
        # teaching is correctly refused.
        target_session = None
        for sess in ctx.session_mgr.sessions_in_room(
            char.get("room_id"), source_char=char,
        ):
            if (sess.character and
                    sess.character.get("name", "").lower() == target_name.lower()):
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

        # Save target character. CRAFT.P1: the no-kwargs form was a
        # no-op — PC-taught schematics never persisted across reload.
        try:
            await ctx.db.save_character(
                target_char["id"], attributes=target_char["attributes"])
        except Exception:
            log.warning("TeachCommand: target save failed", exc_info=True)

        await _save_char(ctx)


# ---------------------------------------------------------------------------
# NPC Trainer helper (called by npc_commands.py when player talks to a trainer NPC)
# ---------------------------------------------------------------------------

def _free_lessons(char: dict) -> dict:
    """Per-trainer first-lesson-free record, stored in the attributes
    blob (the established misc-state home). {trainer_lower: True}."""
    try:
        attrs = json.loads(char.get("attributes", "{}") or "{}")
        rec = attrs.get("trainer_free_lessons", {})
        return rec if isinstance(rec, dict) else {}
    except Exception:
        return {}


def _mark_free_lesson(char: dict, trainer_lower: str) -> None:
    try:
        attrs = json.loads(char.get("attributes", "{}") or "{}")
        if not isinstance(attrs, dict):
            attrs = {}
        rec = attrs.get("trainer_free_lessons")
        if not isinstance(rec, dict):
            rec = {}
        rec[trainer_lower] = True
        attrs["trainer_free_lessons"] = rec
        char["attributes"] = json.dumps(attrs)
    except Exception:
        log.debug("free-lesson mark failed", exc_info=True)


def trainer_curriculum(npc_name: str) -> list[tuple[str, dict]]:
    """All (key, schematic) pairs this trainer teaches, cheapest first."""
    out = [
        (key, s) for key, s in get_all_schematics().items()
        if s.get("trainer_npc", "").lower() == npc_name.lower()
    ]
    out.sort(key=lambda kv: int(kv[1].get("base_cost", 0) or 0))
    return out


async def handle_trainer_teach(ctx: CommandContext, npc_name: str) -> bool:
    """
    Called from npc_commands.py TalkCommand when the NPC is a schematic
    trainer.

    CRAFT.schematic_tuition = a (Gundark Drop G, 2026-06-12): the old
    behavior granted the trainer's ENTIRE catalog free on talk. Now:
      • the trainer's FIRST lesson per character is free — the cheapest
        recipe they teach, granted right here on talk ("first lesson's
        on the house"). This preserves any talk-then-craft flow and is
        good diegesis besides.
      • the rest are LISTED with tuition (50% of base_cost, min 50 cr —
        engine.crafting.schematic_tuition) and bought one at a time via
        `learn <schematic>` (LearnCommand below).
      • PC-to-PC teaching (TeachCommand) stays free, untouched.
    Returns True if the trainer had anything to say about schematics.
    """
    char = ctx.session.character
    if not char:
        return False

    curriculum = trainer_curriculum(npc_name)
    if not curriculum:
        return False

    from engine.crafting import schematic_tuition
    known = set(get_known_schematics(char))
    trainer_lower = npc_name.lower()

    unknown = [(k, s) for k, s in curriculum if k not in known]
    already_known = [s["name"] for k, s in curriculum if k in known]

    taught_free = None
    if unknown and not _free_lessons(char).get(trainer_lower):
        free_key, free_schem = unknown[0]  # cheapest first
        if add_known_schematic(char, free_key):
            _mark_free_lesson(char, trainer_lower)
            taught_free = free_schem["name"]
            unknown = unknown[1:]

    if taught_free:
        await ctx.session.send_line(
            f"  {npc_name} walks you through the {taught_free}. "
            f"\033[2m\"First lesson's on the house.\"\033[0m"
        )
    if unknown:
        await ctx.session.send_line(
            f"  {npc_name} can also teach (tuition, `learn <name>`):"
        )
        for key, s in unknown:
            await ctx.session.send_line(
                f"    {s['name']:<28} {schematic_tuition(s):>6,} cr"
            )
    if already_known:
        await ctx.session.send_line(
            f"  You already know: {', '.join(already_known)}."
        )

    if taught_free:
        await _save_char(ctx)
    return bool(taught_free or unknown or already_known)


class LearnCommand(BaseCommand):
    key = "learn"
    aliases = []
    help_text = (
        "Pay tuition to learn a schematic from a trainer in the room.\n"
        "Tuition is half the schematic's base cost (minimum 50 cr).\n"
        "Each trainer's first lesson is free — just `talk` to them.\n"
        "\n"
        "USAGE: learn <schematic name>"
    )
    usage = "learn <schematic name>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        arg = (ctx.args or "").strip().lower()
        if not arg:
            await ctx.session.send_line(
                "  Learn what? Usage: learn <schematic name>")
            return

        # Resolve against EVERY trainer-bound schematic (not just known
        # ones — that's the point), exact key/name first, then prefix.
        all_schem = get_all_schematics()
        candidates = [(k, s) for k, s in all_schem.items()
                      if s.get("trainer_npc")]
        match = None
        for k, s in candidates:
            if arg == k or arg == s["name"].lower():
                match = (k, s)
                break
        if match is None:
            pref = [(k, s) for k, s in candidates
                    if k.startswith(arg) or s["name"].lower().startswith(arg)]
            if len(pref) == 1:
                match = pref[0]
            elif len(pref) > 1:
                names = ", ".join(s["name"] for _, s in pref[:5])
                await ctx.session.send_line(
                    f"  Which one? Matches: {names}.")
                return
        if match is None:
            await ctx.session.send_line(
                f"  No trainer teaches a schematic matching '{arg}'.")
            return

        key, schem = match
        if key in get_known_schematics(char):
            await ctx.session.send_line(
                f"  You already know the {schem['name']} schematic.")
            return

        trainer = schem["trainer_npc"]
        # The teacher must actually be here.
        npcs = await ctx.db.get_npcs_in_room(char["room_id"])
        present = any(
            (n.get("name") or "").lower() == trainer.lower() for n in npcs
        )
        if not present:
            await ctx.session.send_line(
                f"  {trainer} teaches that, and {trainer} isn't here.")
            return

        from engine.crafting import schematic_tuition
        trainer_lower = trainer.lower()
        free = not _free_lessons(char).get(trainer_lower)
        tuition = 0 if free else schematic_tuition(schem)

        if tuition and int(char.get("credits", 0) or 0) < tuition:
            await ctx.session.send_line(
                f"  Tuition for the {schem['name']} is {tuition:,} cr — "
                f"you have {int(char.get('credits', 0) or 0):,}.")
            return

        if tuition:
            char["credits"] = await ctx.db.adjust_credits(
                char["id"], -tuition, "schematic_tuition")
        if free:
            _mark_free_lesson(char, trainer_lower)

        add_known_schematic(char, key)
        await _save_char(ctx)

        if free:
            await ctx.session.send_line(
                f"  {trainer} walks you through the {schem['name']}. "
                f"\033[2m\"First lesson's on the house.\"\033[0m")
        else:
            await ctx.session.send_line(
                f"  You pay {tuition:,} cr. {trainer} walks you through "
                f"the {schem['name']}. "
                f"\033[2m(Balance: {int(char.get('credits', 0) or 0):,} cr)\033[0m")


# ---------------------------------------------------------------------------
# Consumable item creation helper
# ---------------------------------------------------------------------------

# _CONSUMABLE_STATS migrated to data/consumables.yaml + engine/consumables.py
# (CRAFT.P2 / Gundark Drop A, 2026-06-10 — design pass §3.3). The old dict's
# `heal_wounds` field was a phantom (nothing read it); the migrated family
# now has a REAL mechanical consumer: the medpac entries in
# parser/medical_commands.py::_STIM_CATALOG, whose `heal_wound_levels` the
# stim success path applies to the wound ladder.


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
        # CRAFT.P0.2: persist via db.add_to_inventory — the old
        # ctx.session.items.append() raised a swallowed AttributeError
        # (no Session.items exists), so the weapon EVAPORATED while the
        # player was told it was added. add_to_inventory also fires the
        # item_acquired tutorial hook the old path bypassed.
        try:
            item = _new_crafted_item(output_key, quality, crafter, max_condition)
            item_dict = item.to_dict()
            item_dict["type"] = "weapon"
            item_dict["name"] = schematic["name"]
            # Gundark Drop G (2026-06-12, decision 3a): contraband
            # recipes flag the LANDED item — patrol boardings sweep
            # carried inventory for this (engine/encounter_patrol).
            if schematic.get("contraband"):
                item_dict["contraband"] = True
            await ctx.db.add_to_inventory(char["id"], item_dict)
            await ctx.session.send_line(
                f"  The {schematic['name']} has been added to your inventory. "
                f"(max_condition: {max_condition})"
            )
            await ctx.session.send_line(
                f"  \033[2mUse 'equip {schematic['name']}' to wield it.\033[0m"
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

        from engine.consumables import consumable_display_name
        display_name = consumable_display_name(output_key)
        await ctx.session.send_line(
            f"  The {display_name} has been added to your consumables. "
            f"(quality {quality:.0f}/100)"
        )

    elif output_type == "component":
        # Ship component — +ship/install reads items where
        # item["type"] == "ship_component".
        # CRAFT.P0.3: persist via db.add_to_inventory. The old branch
        # parsed the inventory column expecting a bare list; under the
        # current dict format it reset to [] and wrote a bare list back,
        # DESTROYING the character's items and resource stacks.
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
        await ctx.db.add_to_inventory(char["id"], component_item)

        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your inventory as a "
            f"ship component. (quality {quality:.0f}/100)"
        )
        await ctx.session.send_line(
            f"  Use '+ship/install {schematic['name']}' while docked to install it."
        )

    elif output_type in ("gear", "survival_gear"):
        # Field/utility gear — durable items; hazard-mitigating entries
        # are matched by KEY (engine/hazards.py _has_mitigation), so the
        # CRAFT.P2 type fold below is hazard-safe.
        # CRAFT.P2 / Gundark Drop A (decision 2a): `survival_gear` FOLDS
        # into `gear`. The branch accepts both spellings (existing
        # schematics re-typed in the same drop; the legacy alias stays
        # so a stale data file can't strand a craft), and new landings
        # carry type "gear". Existing player inventories holding
        # {"type": "survival_gear"} items are untouched — every reader
        # of these items matches by key, not type.
        # CRAFT.P0.3: persist via db.add_to_inventory (same bare-list
        # data-loss bug as the component branch).
        gear_item = {
            "type":     "gear",
            "key":      output_key,
            "name":     schematic["name"],
            "quality":  round(quality, 1),
            "crafter":  crafter,
            "uses":     schematic.get("max_uses", 0),  # 0 = unlimited
            "max_uses": schematic.get("max_uses", 0),
        }
        # Gundark Drop F: tool gear carries its skill bonus on the item
        # dict (gear has no stat registry — the carried dict IS the
        # record). engine.skill_checks._best_tool_bonus reads it.
        if isinstance(schematic.get("skill_bonus"), dict):
            gear_item["skill_bonus"] = dict(schematic["skill_bonus"])
        if schematic.get("contraband"):
            gear_item["contraband"] = True
        await ctx.db.add_to_inventory(char["id"], gear_item)

        uses_str = f" ({schematic.get('max_uses', 0)} uses)" if schematic.get("max_uses") else " (durable)"
        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your inventory{uses_str}. "
            f"(quality {quality:.0f}/100)"
        )
        await ctx.session.send_line(
            f"  \033[2mThis item mitigates environmental hazards when carried.\033[0m"
        )

    elif output_type == "equipment":
        # CRAFT.P0.4: durable gear (comlink bug, lockpick, lectroticker,
        # tracker, ...). This branch DID NOT EXIST — equipment-type
        # schematics rolled the skill check, consumed components on
        # success, and produced NOTHING, silently. Each item's gameplay
        # consumer is named in its schematics.yaml use_hook comment
        # (mechanical-use mandate, design pass §3.2a).
        gear_item = {
            "type":     "equipment",
            "key":      output_key,
            "name":     schematic["name"],
            "quality":  round(quality, 1),
            "crafter":  crafter,
        }
        await ctx.db.add_to_inventory(char["id"], gear_item)
        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your inventory. "
            f"(quality {quality:.0f}/100)"
        )

    elif output_type == "armor":
        # CRAFT.P2 / Gundark Drop A foundation: armor landing branch.
        # Mirrors the weapon branch — an ItemInstance-shaped carried
        # dict so `wear` (the P0.9 inventory-aware path) can slot it
        # with condition/quality/crafter intact. Content shipped in
        # Gundark Drop C (2026-06-11): armor rows live in
        # data/weapons.yaml as `type: armor` (the live registry that
        # wear/soak/sheet read — the plan's separate armor.yaml was
        # superseded by extend-don't-add); trainer is Sela Tarn.
        armor_item = {
            "type":      "armor",
            "key":       output_key,
            "name":      schematic["name"],
            "quality":   round(quality, 1),
            "condition": 100,
            "crafter":   crafter,
        }
        await ctx.db.add_to_inventory(char["id"], armor_item)
        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your "
            f"inventory. (quality {quality:.0f}/100 — `wear` it to "
            f"don it)"
        )

    else:
        # Unknown output_type: components were already consumed by
        # resolve_craft — never swallow that silently again.
        log.error("craft: schematic %r has unhandled output_type %r",
                  schematic.get("key"), output_type)
        await ctx.session.send_line(
            f"  The {schematic['name']} was assembled, but its type "
            f"({output_type}) has no delivery path. Contact an admin — "
            f"your components were consumed."
        )


async def _save_char(ctx: CommandContext):
    """Persist the session character's ATTRIBUTES column.

    CRAFT.P1 (2026-06-10): this was `save_character(char["id"])` with no
    kwargs — which `db.save_character` treats as a NO-OP (`if not fields:
    return`). Every caller believed it was saving; nothing was. E7 caught
    it on its first Windows run (craft reported success, consumable count
    stayed 0 on re-fetch).

    Deliberately attributes-only: `inventory` is NOT saved here because
    `db.add_to_inventory` does its own DB read-modify-write — blanket-
    writing the session dict's inventory string after a delivery would
    clobber the just-landed item (the F2 evaporation, reborn as a stale-
    dict overwrite). Sites that mutate inventory dict-side (survey's
    add_resource, craft's component consumption) save that column
    explicitly at the correct moment.
    """
    try:
        char = ctx.session.character
        if char and char.get("attributes") is not None:
            await ctx.db.save_character(
                char["id"], attributes=char["attributes"])
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
        LearnCommand(),
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

        # Execute purchase (through the credit chokepoint)
        char["credits"] = await ctx.db.adjust_credits(char["id"], -total_cost, "resource_vendor")

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

        # Credit movement recorded via adjust_credits at the purchase site.


# ── S56: populate _CRAFT_SWITCH_IMPL after BuyResourcesCommand is defined ──
_init_craft_switch_impl()
