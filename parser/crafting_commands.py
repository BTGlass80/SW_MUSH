"""
parser/crafting_commands.py — SW_MUSH Crafting Commands (Phase 3)

Commands: survey, resources, schematics, craft, experiment, teach

All skill checks go through engine.skill_checks.perform_skill_check().
Items created via engine.items.ItemInstance.new_crafted().

NPC sell integration: sell <item> to Kayson (weapons) or Heist (consumables)
is handled by the existing SellCommand in builtin_commands.py, which will
check quality and apply pricing. This module creates the item; selling uses
the existing Bargain pattern.
"""

import json
import random
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
)

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
    except AttributeError:
        # Fallback: store in server item registry if session doesn't expose items directly.
        # Commands that need to display the item can rely on the returned item reference.
        pass


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------

class SurveyCommand:
    """
    survey
    Search the environment for raw resources. Uses the Search skill.
    Outdoor zones yield metal + organic; city zones yield chemical + energy.
    """
    names = ["survey"]
    help_category = "Economy"
    help_text = (
        "Usage: survey\n"
        "Search your surroundings for raw crafting materials.\n"
        "Outdoor areas yield metal and organic components.\n"
        "City areas yield chemical and energy components.\n"
        "Higher Search skill → better quality finds."
    )

    async def execute(self, ctx):
        char = ctx.character
        if not char:
            await ctx.send("You must be logged in to survey.")
            return

        # Cooldown: 5 minutes between surveys (stored in attributes)
        import time
        attrs = char.get("attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}
        if not isinstance(attrs, dict):
            attrs = {}

        last_survey = attrs.get("last_survey", 0)
        now = time.time()
        cooldown = 300  # 5 min
        if now - last_survey < cooldown:
            remaining = int(cooldown - (now - last_survey))
            await ctx.send(
                f"You've already surveyed recently. Wait {remaining}s before surveying again."
            )
            return

        # Determine zone
        room = ctx.room
        zone_name = room.get("zone", "") if room else ""

        resource_types = get_survey_resources(zone_name)
        is_outdoor = "metal" in resource_types  # outdoor → metal+organic

        # Skill check: Search, difficulty 12 (Moderate)
        difficulty = 12
        result = _skill_check(char, "search", difficulty)

        # Update cooldown regardless of outcome
        attrs["last_survey"] = now
        char["attributes"] = json.dumps(attrs)

        if result.fumble:
            await ctx.send(
                f"You search the area carefully but disturb something. "
                f"A patrol passes by — better lay low for a while."
            )
            return

        if not result.success and result.margin < -4:
            await ctx.send(
                f"You search the area but come up empty-handed. "
                f"[Roll: {result.roll}, needed {difficulty}]"
            )
            return

        # Determine quality and quantity from margin
        quality = survey_quality_from_margin(result.margin, is_outdoor)
        quantity = 1
        if result.critical_success:
            quantity = random.randint(2, 3)
        elif result.success and result.margin >= 5:
            quantity = 2
        elif not result.success:  # partial (margin ≥ -4)
            quality = max(1.0, quality * 0.7)
            quantity = 1

        # Pick which resource type to find (random from zone list)
        rtype = random.choice(resource_types)

        msg = add_resource(char, rtype, quantity, quality)

        tier = _quality_desc(quality)
        if result.critical_success:
            prefix = "Excellent find! "
        elif result.success:
            prefix = ""
        else:
            prefix = "Thin pickings, but: "

        await ctx.send(
            f"{prefix}You survey the area and uncover {quantity}x {rtype} "
            f"({tier}, quality {quality:.0f}/100). [{msg}]"
        )

        # Save character
        await _save_char(ctx)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class ResourcesCommand:
    """
    resources
    Display your resource inventory.
    """
    names = ["resources", "res"]
    help_category = "Economy"
    help_text = (
        "Usage: resources\n"
        "List all raw crafting resources you currently carry."
    )

    async def execute(self, ctx):
        char = ctx.character
        if not char:
            await ctx.send("You must be logged in.")
            return

        resources = _get_resource_list(char)
        if not resources:
            await ctx.send("You have no crafting resources. Try the 'survey' command.")
            return

        # Sort by type then quality desc
        resources_sorted = sorted(resources, key=lambda s: (s["type"], -float(s.get("quality", 0))))
        lines = [f"{'TYPE':<12} {'QTY':>4}  {'QUALITY':>7}  TIER"]
        lines.append("-" * 38)
        total_stacks = 0
        for s in resources_sorted:
            rtype   = s.get("type", "?")
            qty     = int(s.get("quantity", 0))
            quality = float(s.get("quality", 0))
            tier    = _quality_desc(quality)
            lines.append(f"{rtype:<12} {qty:>4}  {quality:>6.0f}/100  {tier}")
            total_stacks += 1
        lines.append("-" * 38)
        lines.append(f"{total_stacks} stack(s) total.")
        await ctx.send("\n".join(lines))


# ---------------------------------------------------------------------------
# Schematics
# ---------------------------------------------------------------------------

class SchematicsCommand:
    """
    schematics
    List known schematics and show which you can currently craft.
    """
    names = ["schematics", "schem"]
    help_category = "Economy"
    help_text = (
        "Usage: schematics\n"
        "List schematics you have learned. Schematics marked [READY] can be\n"
        "crafted right now with your current resource inventory."
    )

    async def execute(self, ctx):
        char = ctx.character
        if not char:
            await ctx.send("You must be logged in.")
            return

        known_keys = get_known_schematics(char)
        if not known_keys:
            await ctx.send(
                "You don't know any schematics yet.\n"
                "Seek out Kayson at the weapon shop or Heist at the clinic to learn some."
            )
            return

        all_schem = get_all_schematics()
        lines = ["Known Schematics:", "-" * 52]
        for key in known_keys:
            schem = all_schem.get(key)
            if not schem:
                continue
            ok, _ = can_craft(char, schem)
            ready = "[READY]" if ok else "      "
            lines.append(
                f"  {ready}  {schem['name']:<32}  diff {schem['difficulty']}"
            )
        lines.append("-" * 52)
        lines.append("Use 'craft <schematic>' to attempt assembly.")
        await ctx.send("\n".join(lines))


# ---------------------------------------------------------------------------
# Craft
# ---------------------------------------------------------------------------

class CraftCommand:
    """
    craft <schematic>
    Attempt to assemble an item from your resource inventory.
    """
    names = ["craft"]
    help_category = "Economy"
    help_text = (
        "Usage: craft <schematic name or key>\n"
        "Attempt to craft an item using your current resource inventory.\n"
        "Critical success: quality bonus + crafter name on item.\n"
        "Partial success (near-miss): lower quality, no crafter name.\n"
        "Fumble: materials consumed, nothing produced.\n"
        "Use 'schematics' to see what you know."
    )

    async def execute(self, ctx):
        char = ctx.character
        if not char:
            await ctx.send("You must be logged in.")
            return

        args = ctx.args.strip() if ctx.args else ""
        if not args:
            await ctx.send("Usage: craft <schematic name>  (see 'schematics' for options)")
            return

        schematic = _find_schematic(args, get_known_schematics(char))
        if schematic is None:
            await ctx.send(
                f"You don't know a schematic matching '{args}'. "
                f"See 'schematics' for your known list."
            )
            return

        ok, reason = can_craft(char, schematic)
        if not ok:
            await ctx.send(reason)
            return

        skill = schematic["skill_required"]
        difficulty = schematic["difficulty"]
        result = _skill_check(char, skill, difficulty)

        await ctx.send(
            f"You begin assembling {schematic['name']}... "
            f"[{skill.title()} roll: {result.roll} vs difficulty {difficulty}]"
        )

        craft_result = resolve_craft(char, schematic, result, experiment=False)

        await ctx.send(craft_result["message"])

        if craft_result["success"]:
            await _deliver_item(ctx, schematic, craft_result)

        await _save_char(ctx)


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

class ExperimentCommand:
    """
    experiment <schematic>
    High-risk, high-reward crafting. Adds +1D bonus to the skill roll,
    but a fumble destroys all materials. Critical quality bonus is doubled.
    """
    names = ["experiment", "exp"]
    help_category = "Economy"
    help_text = (
        "Usage: experiment <schematic name or key>\n"
        "Like 'craft' but adds +1D to the assembly roll.\n"
        "Critical success: quality bonus x2 (instead of x1.5).\n"
        "Fumble: all materials consumed, nothing produced.\n"
        "Full failure still doesn't destroy materials."
    )

    async def execute(self, ctx):
        char = ctx.character
        if not char:
            await ctx.send("You must be logged in.")
            return

        args = ctx.args.strip() if ctx.args else ""
        if not args:
            await ctx.send("Usage: experiment <schematic name>  (see 'schematics')")
            return

        schematic = _find_schematic(args, get_known_schematics(char))
        if schematic is None:
            await ctx.send(
                f"You don't know a schematic matching '{args}'."
            )
            return

        ok, reason = can_craft(char, schematic)
        if not ok:
            await ctx.send(reason)
            return

        skill = schematic["skill_required"]
        difficulty = schematic["difficulty"]

        # +1D bonus for experiment mode
        from engine.skill_checks import perform_skill_check
        from engine.dice import roll_d6_pool

        base_result = _skill_check(char, skill, difficulty)

        # Add the +1D bonus directly to the roll total
        bonus_die = roll_d6_pool(1)  # one extra die, no wild die
        boosted_roll = base_result.roll + max(bonus_die)

        # Re-evaluate against difficulty with boosted roll
        new_margin = boosted_roll - difficulty

        # Create a patched result object with the boosted values
        class _BoostedResult:
            def __init__(self, base, boosted_roll, new_margin):
                self.roll = boosted_roll
                self.difficulty = base.difficulty
                self.margin = new_margin
                self.success = boosted_roll >= base.difficulty
                # Critical: margin >= 10 after boost; fumble: Wild Die was 1 on base roll
                self.critical_success = base.critical_success or new_margin >= 10
                self.fumble = base.fumble  # fumble is still from wild die
                self.skill_used = base.skill_used
                self.pool_str = base.pool_str + "+1D(exp)"

        boosted = _BoostedResult(base_result, boosted_roll, new_margin)

        await ctx.send(
            f"You push your technique to the limit on {schematic['name']}... "
            f"[{skill.title()}: {base_result.roll}+{max(bonus_die)}(exp) = {boosted_roll} "
            f"vs difficulty {difficulty}]"
        )

        craft_result = resolve_craft(char, schematic, boosted, experiment=True)
        await ctx.send(craft_result["message"])

        if craft_result["success"]:
            await _deliver_item(ctx, schematic, craft_result)

        await _save_char(ctx)


# ---------------------------------------------------------------------------
# Teach
# ---------------------------------------------------------------------------

class TeachCommand:
    """
    teach <player> <schematic>
    Share a known schematic with another player in the same room.
    """
    names = ["teach"]
    help_category = "Economy"
    help_text = (
        "Usage: teach <player> <schematic>\n"
        "Teach another player a crafting schematic you already know.\n"
        "Both you and the target must be in the same room.\n"
        "You cannot teach a schematic to someone who already knows it."
    )

    async def execute(self, ctx):
        char = ctx.character
        if not char:
            await ctx.send("You must be logged in.")
            return

        args = (ctx.args or "").strip()
        parts = args.split(None, 1)
        if len(parts) < 2:
            await ctx.send("Usage: teach <player> <schematic>")
            return

        target_name, schem_arg = parts[0], parts[1].strip()

        # Find target session in same room
        target_session = None
        try:
            for sess in ctx.server.sessions.values():
                if (sess.character and
                        sess.character.get("name", "").lower() == target_name.lower() and
                        sess.character.get("room_id") == char.get("room_id")):
                    target_session = sess
                    break
        except AttributeError:
            pass

        if target_session is None:
            await ctx.send(
                f"{target_name} is not here. You need to be in the same room to teach."
            )
            return

        target_char = target_session.character

        # Check teacher knows the schematic
        schematic = _find_schematic(schem_arg, get_known_schematics(char))
        if schematic is None:
            await ctx.send(
                f"You don't know a schematic matching '{schem_arg}'."
            )
            return

        added = add_known_schematic(target_char, schematic["key"])
        if not added:
            await ctx.send(
                f"{target_char.get('name')} already knows the {schematic['name']} schematic."
            )
            return

        char_name = char.get("name", "Someone")
        tgt_name  = target_char.get("name", "them")

        await ctx.send(
            f"You take time to teach {tgt_name} the {schematic['name']} schematic."
        )
        try:
            await target_session.send(
                f"{char_name} teaches you the {schematic['name']} schematic. "
                f"[Added to your known schematics]"
            )
        except Exception:
            pass

        # Save target character
        try:
            db = ctx.server.db
            await db.save_character(target_char)
        except Exception:
            pass

        await _save_char(ctx)


# ---------------------------------------------------------------------------
# NPC Trainer helper (called by NpcCommands when player talks to a trainer NPC)
# ---------------------------------------------------------------------------

async def handle_trainer_teach(ctx, npc_name: str):
    """
    Called from npc_commands.py TalkCommand when the NPC is a schematic trainer.
    Grants all schematics whose trainer_npc matches this NPC name.
    Returns True if any schematics were taught, False otherwise.
    """
    char = ctx.character
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
        await ctx.send(
            f"{npc_name} shows you some techniques. You learn: {', '.join(taught)}."
        )
    if already_known:
        await ctx.send(
            f"You already know: {', '.join(already_known)}."
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
        "heal_wounds": 1,    # wound levels healed on use
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

    # 1. Exact key match
    if arg_lower in all_schem and arg_lower in known_keys:
        return all_schem[arg_lower]

    # 2. Partial name match among known schematics
    matches = []
    for key in known_keys:
        schem = all_schem.get(key)
        if schem and arg_lower in schem["name"].lower():
            matches.append(schem)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Return closest match (fewest extra chars)
        matches.sort(key=lambda s: len(s["name"]))
        return matches[0]
    return None


async def _deliver_item(ctx, schematic: dict, craft_result: dict):
    """
    Create the finished item and add it to the character's inventory.
    For consumables, creates a consumable token in attributes.
    For weapons, creates an ItemInstance via items.py.
    """
    char = ctx.character
    output_key  = schematic["output_key"]
    output_type = schematic["output_type"]
    quality     = craft_result["quality"]
    crafter     = craft_result["crafter_name"]
    stats       = craft_result["stats"]

    max_condition = stats.get("max_condition", 100)

    if output_type == "weapon":
        try:
            item = _new_crafted_item(output_key, quality, crafter, max_condition)
            # Add to character's session item list
            try:
                ctx.session.items.append(item)
            except AttributeError:
                pass
            await ctx.send(
                f"The {schematic['name']} has been added to your inventory. "
                f"(max_condition: {max_condition})"
            )
        except Exception as e:
            await ctx.send(
                f"Item created but could not be placed in inventory: {e}. "
                f"Contact an admin."
            )

    elif output_type == "consumable":
        # Consumables: store in character attributes as a simple count
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
        await ctx.send(
            f"The {display_name} has been added to your consumables. "
            f"(quality {quality:.0f}/100)"
        )


async def _save_char(ctx):
    """Best-effort character save."""
    try:
        await ctx.server.db.save_character(ctx.character)
    except Exception:
        pass


def _quality_desc(quality: float) -> str:
    if quality >= 90:
        return "Masterwork"
    if quality >= 80:
        return "Superior"
    if quality >= 60:
        return "Good"
    if quality >= 40:
        return "Standard"
    return "Poor"


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------

def register_crafting_commands(registry):
    """Register all crafting commands with the command registry."""
    for cmd_class in [
        SurveyCommand,
        ResourcesCommand,
        SchematicsCommand,
        CraftCommand,
        ExperimentCommand,
        TeachCommand,
    ]:
        instance = cmd_class()
        for name in instance.names:
            registry[name] = instance
