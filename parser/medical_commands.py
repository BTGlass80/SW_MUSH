# -*- coding: utf-8 -*-
"""
parser/medical_commands.py  --  Player-to-player healing for credits.

Commands:
  heal <target>       Offer to heal a wounded player in the same room.
  healaccept          Accept a pending heal offer.
  healrate <credits>  Set your healing rate (persisted in attributes JSON).

Design (from handoff):
  - Healer must have First Aid or Medicine skill (at least 1 pip above attribute)
  - Skill check: perform_skill_check(healer, "first aid", difficulty)
  - Difficulty scales with wound level:
      Stunned: 8, Wounded: 11, Incapacitated: 16, Mortally Wounded: 21
  - Success: reduce target wound level by 1 step; credits transferred
  - Partial (margin >= -4): no improvement, "bleeding stabilised" flavor
  - Critical: reduce wound level by 2 steps (minimum 1 step improvement)
  - Failure: no improvement, no refund
  - Cannot self-heal (use bacta tank)
  - Target must consent via 'healaccept'
"""
import json
import time
import logging
from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)

# In-memory pending heal offers: target_char_id -> offer_dict
# Offers expire after 60 seconds.
_pending_heals: dict[int, dict] = {}

# Wound level constants (matching engine/character.py WoundLevel)
_WL_HEALTHY = 0
_WL_STUNNED = 1
_WL_WOUNDED = 2
_WL_WOUNDED2 = 3      # Second wound (stored as 3 in some paths)
_WL_INCAPACITATED = 4
_WL_MORTALLY_WOUNDED = 5
_WL_DEAD = 6

_WOUND_NAMES = {
    0: "Healthy",
    1: "Stunned",
    2: "Wounded",
    3: "Wounded (x2)",
    4: "Incapacitated",
    5: "Mortally Wounded",
    6: "Dead",
}

_HEAL_DIFFICULTY = {
    1: 8,    # Stunned: Easy
    2: 11,   # Wounded: Moderate
    3: 14,   # Wounded x2: Moderate+
    4: 16,   # Incapacitated: Difficult
    5: 21,   # Mortally Wounded: Very Difficult
}

_DEFAULT_HEAL_RATE = 200


def _get_heal_rate(char: dict) -> int:
    """Read the healer's rate from attributes JSON."""
    try:
        attrs = json.loads(char.get("attributes", "{}"))
        return int(attrs.get("heal_rate", _DEFAULT_HEAL_RATE))
    except Exception:
        log.warning("get_heal_rate failed", exc_info=True)
        return _DEFAULT_HEAL_RATE


def _set_heal_rate(char: dict, rate: int) -> str:
    """Set heal_rate in attributes JSON, return updated JSON string."""
    try:
        attrs = json.loads(char.get("attributes", "{}"))
    except Exception:
        attrs = {}
    attrs["heal_rate"] = rate
    return json.dumps(attrs)


def _has_healing_skill(char: dict) -> tuple[bool, str]:
    """
    Check if char has First Aid or Medicine above raw attribute.
    Returns (has_skill, skill_name).
    Medicine is preferred if both are trained.
    """
    try:
        skills = json.loads(char.get("skills", "{}"))
    except Exception:
        skills = {}

    # Check Medicine first (better skill)
    if skills.get("medicine"):
        return True, "medicine"
    if skills.get("first aid"):
        return True, "first aid"
    return False, ""


def _find_target_session(ctx, target_name: str):
    """Find a player session in the same room by name prefix.

    W.2 phase 2: source_char on sessions_in_room filters to wilderness
    co-located peers when the searcher is in wilderness.
    """
    char = ctx.session.character
    room_id = char["room_id"]
    target_name_lower = target_name.strip().lower()
    matches = []
    for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char):
        if not s.character or s.character["id"] == char["id"]:
            continue
        cname = s.character.get("name", "").lower()
        if cname == target_name_lower or cname.startswith(target_name_lower):
            matches.append(s)
    if len(matches) == 1:
        return matches[0]
    return None


class HealCommand(BaseCommand):
    key = "heal"
    aliases = []
    help_text = (
        "Offer to heal a wounded player in the same room. "
        "Requires First Aid or Medicine skill. Target must type 'healaccept'."
    )
    usage = "heal <player name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: heal <player name>")
            await ctx.session.send_line(
                f"  Your heal rate: {_get_heal_rate(ctx.session.character):,} credits"
            )
            return

        char = ctx.session.character

        # Must have First Aid or Medicine
        has_skill, skill_name = _has_healing_skill(char)
        if not has_skill:
            await ctx.session.send_line(
                "  You need First Aid or Medicine skill to heal others."
            )
            return

        # Find target
        target_session = _find_target_session(ctx, ctx.args.strip())
        if not target_session:
            await ctx.session.send_line(
                f"  Can't find '{ctx.args}' in this room."
            )
            return

        target_char = target_session.character
        target_name = target_char.get("name", "Unknown")
        target_wound = target_char.get("wound_level", 0)

        # Validation
        if target_char["id"] == char["id"]:
            await ctx.session.send_line("  You can't heal yourself. Try a bacta tank.")
            return

        if target_wound <= _WL_HEALTHY:
            await ctx.session.send_line(
                f"  {target_name} is perfectly healthy."
            )
            return

        if target_wound >= _WL_DEAD:
            await ctx.session.send_line(
                f"  {target_name} is beyond medical help."
            )
            return

        rate = _get_heal_rate(char)
        target_credits = target_char.get("credits", 0)

        if target_credits < rate:
            await ctx.session.send_line(
                f"  {target_name} only has {target_credits:,} credits "
                f"(your rate is {rate:,})."
            )
            return

        wound_name = _WOUND_NAMES.get(target_wound, "Wounded")
        difficulty = _HEAL_DIFFICULTY.get(target_wound, 16)

        # Store pending offer
        _pending_heals[target_char["id"]] = {
            "healer_id": char["id"],
            "healer_session": ctx.session,
            "healer_name": char.get("name", "Unknown"),
            "skill_name": skill_name,
            "difficulty": difficulty,
            "rate": rate,
            "target_wound": target_wound,
            "timestamp": time.time(),
        }

        # Notify both players
        await ctx.session.send_line(
            f"  You offer to treat {ansi.player_name(target_name)}'s "
            f"injuries ({wound_name}) for {rate:,} credits."
        )
        await ctx.session.send_line(
            f"  {ansi.DIM}Skill: {skill_name.title()} "
            f"({_get_pool_str(char, skill_name)}) vs Difficulty {difficulty}{ansi.RESET}"
        )
        await target_session.send_line(
            f"  {ansi.player_name(char.get('name', 'Someone'))} offers to "
            f"treat your wounds ({wound_name}) for {rate:,} credits."
        )
        await target_session.send_line(
            f"  Type {ansi.BRIGHT_CYAN}healaccept{ansi.RESET} to accept, "
            f"or ignore to decline."
        )

        # Broadcast to room
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {ansi.player_name(char.get('name', 'Someone'))} examines "
            f"{ansi.player_name(target_name)}'s injuries.",
            exclude=ctx.session,
            source_char=char,  # W.2 phase 2
        )


def _get_pool_str(char: dict, skill_name: str) -> str:
    """Quick helper to show the healer's skill pool."""
    try:
        from engine.skill_checks import _get_skill_pool, _pool_to_str
        dice, pips = _get_skill_pool(char, skill_name, None)
        return _pool_to_str(dice, pips)
    except Exception:
        log.warning("get_skill_str failed", exc_info=True)
        return "?"


class HealAcceptCommand(BaseCommand):
    key = "healaccept"
    aliases = ["haccept"]
    help_text = "Accept a pending heal offer."
    usage = "healaccept"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        char_id = char["id"]

        # Check for pending offer
        offer = _pending_heals.pop(char_id, None)
        if not offer:
            await ctx.session.send_line("  No pending heal offer.")
            return

        # Check expiry (60 seconds)
        if time.time() - offer["timestamp"] > 60:
            await ctx.session.send_line("  That heal offer has expired.")
            return

        # Verify healer is still in the room
        healer_session = offer["healer_session"]
        if (not healer_session.character
                or healer_session.character.get("room_id") != char.get("room_id")):
            await ctx.session.send_line("  The healer is no longer nearby.")
            return

        # Verify credits
        rate = offer["rate"]
        credits = char.get("credits", 0)
        if credits < rate:
            await ctx.session.send_line(
                f"  Not enough credits ({credits:,} < {rate:,})."
            )
            return

        # Re-check wound level (may have changed)
        target_wound = char.get("wound_level", 0)
        if target_wound <= _WL_HEALTHY:
            await ctx.session.send_line("  You're already healthy!")
            return
        if target_wound >= _WL_DEAD:
            await ctx.session.send_line("  You're beyond medical help.")
            return

        difficulty = _HEAL_DIFFICULTY.get(target_wound, offer["difficulty"])
        skill_name = offer["skill_name"]
        healer_char = healer_session.character

        # ── Perform the skill check ──
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(healer_char, skill_name, difficulty)

        healer_name = healer_char.get("name", "Someone")
        room_id = char["room_id"]
        wound_name = _WOUND_NAMES.get(target_wound, "Wounded")

        if result.success:
            # Reduce wound level
            if result.critical_success and target_wound >= 2:
                # Critical: reduce by 2 steps (min result = Healthy)
                new_wound = max(0, target_wound - 2)
                heal_msg = "Expert treatment! Two levels of injury healed."
            else:
                new_wound = max(0, target_wound - 1)
                heal_msg = "Treatment successful."

            new_wound_name = _WOUND_NAMES.get(new_wound, "Healthy")

            # Transfer credits
            new_patient_credits = credits - rate
            healer_credits = healer_char.get("credits", 0) + rate
            char["credits"] = new_patient_credits
            char["wound_level"] = new_wound
            healer_char["credits"] = healer_credits

            # Ledger chokepoint (F1): the patient->healer payment as two
            # logged legs (sink + faucet) instead of raw credit writes.
            await ctx.db.save_character(char_id, wound_level=new_wound)
            await ctx.db.adjust_credits(char_id, -rate, "medical")
            await ctx.db.adjust_credits(healer_char["id"], rate, "medical")

            # Notify
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[MEDICAL]{ansi.RESET} {heal_msg} "
                f"{wound_name} → {new_wound_name}. "
                f"Paid {rate:,} credits."
            )
            await healer_session.send_line(
                f"  {ansi.BRIGHT_GREEN}[MEDICAL]{ansi.RESET} {heal_msg} "
                f"({skill_name.title()} {result.pool_str}: {result.roll} vs {difficulty}) "
                f"Earned {rate:,} credits."
            )
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  {ansi.player_name(healer_name)} treats "
                f"{ansi.player_name(char.get('name', 'someone'))}'s wounds.",
                exclude=[ctx.session, healer_session],
                source_char=char,  # W.2 phase 2
            )

        elif result.margin >= -4:
            # Partial: no wound improvement, flavor text, no payment
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[MEDICAL]{ansi.RESET} "
                f"The treatment stabilises the bleeding but doesn't fully take. "
                f"No charge."
            )
            await healer_session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[MEDICAL]{ansi.RESET} "
                f"Close, but the treatment doesn't hold. "
                f"({skill_name.title()} {result.pool_str}: {result.roll} vs {difficulty}) "
                f"No charge."
            )

        else:
            # Failure: no improvement, no payment
            fumble_extra = " Something went wrong!" if result.fumble else ""
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[MEDICAL]{ansi.RESET} "
                f"The treatment fails.{fumble_extra} No charge."
            )
            await healer_session.send_line(
                f"  {ansi.BRIGHT_RED}[MEDICAL]{ansi.RESET} "
                f"Treatment failed. "
                f"({skill_name.title()} {result.pool_str}: {result.roll} vs {difficulty})"
                f"{fumble_extra}"
            )


class HealRateCommand(BaseCommand):
    key = "+healrate"
    aliases = ["healrate", "hrate"]
    help_text = "Set your healing rate in credits."
    usage = "healrate <credits>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character

        if not ctx.args:
            rate = _get_heal_rate(char)
            await ctx.session.send_line(
                f"  Your heal rate: {rate:,} credits per treatment."
            )
            await ctx.session.send_line(
                f"  Usage: healrate <amount> to change it."
            )
            return

        try:
            rate = int(ctx.args.strip())
        except ValueError:
            await ctx.session.send_line("  Usage: healrate <number>")
            return

        if rate < 0:
            await ctx.session.send_line("  Rate must be positive.")
            return
        if rate > 100000:
            await ctx.session.send_line("  That's... ambitious. Max 100,000.")
            return

        new_attrs = _set_heal_rate(char, rate)
        char["attributes"] = new_attrs
        await ctx.db.save_character(char["id"], attributes=new_attrs)

        await ctx.session.send_line(
            f"  Heal rate set to {rate:,} credits per treatment."
        )


# ═══════════════════════════════════════════════════════════════════════════
# SRB.1 — Medic stim commands
# ═══════════════════════════════════════════════════════════════════════════
#
# Per support_role_buffs_design_v1.md §3. Adds two top-level commands
# (`stim`, `stimaccept`) and a `_STIM_CATALOG` mapping consumable
# tokens to (skill, difficulty, buff_type, side_effect_token).
#
# The Heal* commands and `_pending_heals` are unchanged — SRB.1 is
# purely additive. Stim and Heal share the same room-coloc pattern
# (`_find_target_session`), and stim has its own `_pending_stims`
# offers dict matching `_pending_heals`'s shape.
#
# Substrate decisions
# -------------------
#
# 1. **Stims consume from attributes.consumables.** Per SRB.1 (b) shipped
#    May 24 2026 (T2.10.b in TODO.json). The crafting layer
#    (parser/crafting_commands.py) writes crafted stims under
#    ``attributes.consumables[output_key]`` as a count. StimCommand
#    refuses at offer-time if the medic's count is 0; _execute_stim_roll
#    decrements at attempt-time (success/failure/fumble all consume,
#    per design §3.5 "target wastes the stim, no benefit" on failure).
#
#    See engine/buffs.py::has_consumable / consume_consumable for the
#    helpers and the storage-bifurcation note (this codebase has two
#    parallel consumable storage models; stims use the
#    attributes.consumables one; bacta packs etc. use the
#    inventory.items + consumable:true flag one. Unification is tracked
#    as tech debt in TODO.json).
#
# 2. **Buff substrate, not a separate active_stims table.** Design §3.8
#    spec'd a dedicated table; the BUFF substrate (engine/buffs.py)
#    already provides timed status effects with stacking, expiry, and
#    persistence in `characters.attributes->active_buffs` JSON. SRB.2
#    morale aura uses the same substrate. Adding a parallel
#    `active_stims` table would create two sources of truth for "what
#    bonuses apply to this roll." We piggyback on BUFF instead.
#
# 3. **Cross-type stim stacking prevented at the parser, not at add_buff.**
#    Within-type stacking is blocked by `max_stacks: 1` on each
#    BUFF_TEMPLATE. Cross-type ("medic gives stimpack while combat_stim
#    is active") is prevented here: StimCommand checks
#    `engine.buffs.has_active_stim(target)` before the roll. Per design
#    §3.6, a "force" path with +5 difficulty (overdose risk) is the
#    next iteration; this drop ships the simple block-and-warn.
#
# 4. **Self-administration is allowed for stimpack/focus_stim, blocked
#    for adrenaline_shot/combat_stim.** Per design §3.7: "Combat stim
#    and adrenaline shot CANNOT be self-administered." Self-stim
#    takes the -1D penalty (in pips: -3) on the medic roll, per the
#    same section.
#
# 5. **Fumble path: 2 wound levels.** Per design §3.5. We cap at WL_DEAD.
#    Failure-without-fumble side effect varies by consumable (per
#    design §3.5). For SRB.1 MVP, the failure path applies the
#    side-effect *debuff* (e.g. -1D Willpower for combat_stim) and
#    no positive buff. The wound-level escalation only fires on a
#    true fumble (Wild Die 1).
#
# 6. **`stimaccept` mirrors `healaccept` exactly.** The target consents
#    via the same prompt-and-accept flow. Offers expire after 60
#    seconds (same as heal). One pending stim per target at a time;
#    a fresh stim offer overwrites a stale one (same as heal).


# In-memory pending stim offers: target_char_id -> offer_dict.
_pending_stims: dict[int, dict] = {}

# Catalog of consumable tokens → (skill_name, difficulty, buff_type,
# side_effect_buff_type_or_None).
# Per design §3.3 + §3.5.
_STIM_CATALOG: dict[str, dict] = {
    "stimpack": {
        "skill": "first aid",
        "difficulty": 10,
        "buff_type": "stimpack",
        "self_administration_ok": True,
        "side_effect_buff_type": None,  # waste only, no debuff
        "fail_msg": "  The stim takes hold weakly. No real benefit.",
    },
    "adrenaline_shot": {
        "skill": "medicine",
        "difficulty": 15,
        "buff_type": "adrenaline_shot",
        "self_administration_ok": False,
        "side_effect_buff_type": None,  # wound damage handled separately
        "fail_msg": (
            "  The adrenaline shock hits wrong. The target takes a "
            "wound from the chemistry."
        ),
        # On failure (not fumble), also escalate wound by 1 level.
        "failure_wound_levels": 1,
    },
    "combat_stim": {
        "skill": "medicine",
        "difficulty": 20,
        "buff_type": "combat_stim",
        "self_administration_ok": False,
        "side_effect_buff_type": "intimidated",  # -1 dex/per ≈ jitter
        "fail_msg": (
            "  The combat stim misfires — jitter sets in instead of "
            "the kick."
        ),
    },
    "focus_stim": {
        "skill": "medicine",
        "difficulty": 15,
        "buff_type": "focus_stim",
        "self_administration_ok": True,
        "side_effect_buff_type": "intimidated",  # tunnel vision ≈ -per
        "fail_msg": (
            "  The focus stim overshoots — the target's awareness "
            "narrows badly."
        ),
    },
}

# Synonyms / canonicalization for consumable names entered by the user.
_STIM_ALIAS: dict[str, str] = {
    "stim": "stimpack",
    "pack": "stimpack",
    "adrenaline": "adrenaline_shot",
    "adrenalineshot": "adrenaline_shot",
    "adrenshot": "adrenaline_shot",
    "combat": "combat_stim",
    "combatstim": "combat_stim",
    "focus": "focus_stim",
    "focusstim": "focus_stim",
}


def _canonical_consumable(token: str) -> str | None:
    """Resolve a user-typed consumable to a canonical catalog key.

    Returns None if the token can't be resolved.
    """
    if not token:
        return None
    key = token.strip().lower().replace(" ", "_").replace("-", "_")
    if key in _STIM_CATALOG:
        return key
    return _STIM_ALIAS.get(key)


def _has_stim_skill(char: dict, skill_name: str) -> bool:
    """Check the medic has at least 1 pip above attribute in the
    relevant skill. Mirrors `_has_healing_skill` shape but parameterized."""
    try:
        skills = char.get("skills", "{}")
        if isinstance(skills, str):
            skills = json.loads(skills)
        pips = skills.get(skill_name, 0) or skills.get(skill_name.replace(" ", "_"), 0)
        return int(pips) > 0
    except Exception:
        log.warning("_has_stim_skill failed", exc_info=True)
        return False


class StimCommand(BaseCommand):
    key = "stim"
    aliases = []
    help_text = (
        "Administer a stim to a player in the same room. Default is "
        "stimpack (Easy First Aid). Other forms: 'stim <player> with "
        "adrenaline_shot', '... with combat_stim', '... with "
        "focus_stim'. Target must type 'stimaccept'."
    )
    usage = "stim <player> [with <stimpack|adrenaline_shot|combat_stim|focus_stim>]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return

        char = ctx.session.character

        # Parse: "<player>" or "<player> with <consumable>"
        raw = ctx.args.strip()
        consumable_key = "stimpack"  # default
        target_token = raw
        if " with " in raw.lower():
            # Case-preserving split on the first " with "
            idx = raw.lower().index(" with ")
            target_token = raw[:idx].strip()
            consumable_token = raw[idx + len(" with "):].strip()
            resolved = _canonical_consumable(consumable_token)
            if not resolved:
                await ctx.session.send_line(
                    f"  Unknown consumable '{consumable_token}'. "
                    f"Try: stimpack, adrenaline_shot, combat_stim, "
                    f"focus_stim."
                )
                return
            consumable_key = resolved

        if not target_token:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return

        spec = _STIM_CATALOG[consumable_key]

        # Find target
        target_token_clean = target_token.strip()
        # Allow self-stim explicitly via own name or "me" / "self"
        is_self = target_token_clean.lower() in ("me", "self") or \
            target_token_clean.lower() == char.get("name", "").lower()

        if is_self:
            target_session = ctx.session
            target_char = char
        else:
            target_session = _find_target_session(ctx, target_token_clean)
            if not target_session:
                await ctx.session.send_line(
                    f"  Can't find '{target_token_clean}' in this room."
                )
                return
            target_char = target_session.character

        target_name = target_char.get("name", "Unknown")

        # Self-administration rules
        if is_self and not spec["self_administration_ok"]:
            await ctx.session.send_line(
                f"  You can't self-administer {consumable_key.replace('_', ' ')} — "
                "you need someone else to give you that shot. "
                "(See 'help stim'.)"
            )
            return

        # Skill check — must have at least 1 pip in the relevant skill.
        if not _has_stim_skill(char, spec["skill"]):
            await ctx.session.send_line(
                f"  You need at least 1 pip in {spec['skill'].title()} "
                f"to administer this stim."
            )
            return

        # ── SRB.1 (b): consumables check ───────────────────────────
        # Per support_role_buffs_design_v1.md §3.4: medic must have
        # the stim in their kit. Storage model is attributes.consumables
        # (the crafting layer writes there for output_type: consumable).
        # See engine/buffs.py::has_consumable for the storage-model note.
        # Ordered after the skill check so a non-medic typing `stim`
        # by mistake sees "you need First Aid" rather than the
        # supply-chain message; this matches "do I know how → do I
        # have the kit" mental flow.
        try:
            from engine.buffs import has_consumable
            if not has_consumable(char, consumable_key):
                display = consumable_key.replace("_", " ")
                await ctx.session.send_line(
                    f"  You don't have any {display} in your kit. "
                    f"Craft one, buy one from a medic, or have one "
                    f"transferred to you."
                )
                return
        except Exception:
            # Defense-in-depth: if the consumables check itself
            # explodes, log and refuse rather than letting the stim
            # proceed unaccounted-for. The point of the check is
            # to gate consumption; bypassing it on an exception
            # would silently let players stim from empty kits.
            log.warning(
                "StimCommand: has_consumable check raised; refusing",
                exc_info=True,
            )
            await ctx.session.send_line(
                "  Stim system temporarily unavailable. Try again."
            )
            return

        # Cross-type stim block (design §3.6)
        try:
            from engine.buffs import get_active_stim
            existing = get_active_stim(target_char)
        except Exception:
            log.warning("StimCommand: get_active_stim failed",
                        exc_info=True)
            existing = None
        if existing is not None:
            await ctx.session.send_line(
                f"  {target_name} already has an active stim "
                f"({existing.display_name}). Wait for it to clear "
                "before applying another."
            )
            return

        # Wound guard — refuse to stim the dead
        target_wound = target_char.get("wound_level", 0)
        if target_wound >= _WL_DEAD:
            await ctx.session.send_line(
                f"  {target_name} is beyond stim help."
            )
            return

        # Stage the offer
        _pending_stims[target_char["id"]] = {
            "medic_id": char["id"],
            "medic_session": ctx.session,
            "medic_name": char.get("name", "Unknown"),
            "consumable_key": consumable_key,
            "is_self": is_self,
            "offered_at": time.time(),
        }

        display = consumable_key.replace("_", " ").title()
        if is_self:
            # Self-stim: the medic is also the target — immediately
            # accept on their behalf (no need for a second prompt).
            await self._resolve(ctx, target_session, target_char)
            return

        # Cross-room — prompt
        await target_session.send_line(
            f"\033[1;36m{char.get('name', 'A medic')} offers you a "
            f"{display}. Type 'stimaccept' within 60 seconds to "
            f"accept, or wait for it to expire.\033[0m"
        )
        await ctx.session.send_line(
            f"  Offered {display} to {target_name}. "
            "Waiting for stimaccept."
        )

    async def _resolve(self, ctx: CommandContext, target_session,
                        target_char):
        """Self-stim shortcut: bypass stimaccept and resolve immediately."""
        # Find the offer we just staged
        offer = _pending_stims.pop(target_char["id"], None)
        if offer is None:
            return  # Race / cleared offer
        await _execute_stim_roll(ctx, target_session, target_char, offer)


class StimAcceptCommand(BaseCommand):
    key = "stimaccept"
    aliases = ["saccept"]
    help_text = "Accept a pending stim offer from a medic in this room."
    usage = "stimaccept"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        offer = _pending_stims.pop(char["id"], None)
        if offer is None:
            await ctx.session.send_line(
                "  You have no pending stim offer."
            )
            return

        # Expiry check
        if time.time() - offer["offered_at"] > 60.0:
            await ctx.session.send_line(
                "  That stim offer has expired."
            )
            return

        # Re-validate room co-location: medic must still be in the
        # same room. If they walked away, refuse.
        medic_session = offer.get("medic_session")
        if (medic_session is None
                or not medic_session.character
                or medic_session.character.get("room_id") != char.get("room_id")):
            await ctx.session.send_line(
                "  The medic is no longer here."
            )
            return

        await _execute_stim_roll(ctx, ctx.session, char, offer)


async def _execute_stim_roll(ctx: CommandContext, target_session,
                              target_char, offer: dict):
    """Common roll + apply logic for both the StimAccept and self-stim
    paths.

    Reads the medic from the offer (NOT from ctx.session — for the
    stimaccept path, ctx.session is the target). Posts the resolution
    to both medic and target sessions.
    """
    from engine.skill_checks import perform_skill_check
    from engine.buffs import add_buff

    spec = _STIM_CATALOG[offer["consumable_key"]]
    is_self = offer.get("is_self", False)

    medic_session = offer["medic_session"]
    medic_name = offer["medic_name"]
    medic_char = medic_session.character
    if medic_char is None:
        await target_session.send_line(
            "  The medic disappeared mid-application."
        )
        return

    # ── SRB.1 (b): consume the stim ─────────────────────────────────
    # Per support_role_buffs_design_v1.md §3.5: even on failure the
    # target "wastes the stim, no benefit." So consumption is at
    # attempt-time, not at success-time. Fumble and failure both
    # consume; the only path that doesn't consume is one where we
    # never get here (e.g. offer expired, target out of room — those
    # bail in StimCommand.execute or StimAcceptCommand.execute before
    # reaching _execute_stim_roll).
    #
    # Re-check at consume time defends against the rare case where
    # the medic offered, then somehow lost the stim (admin tool,
    # crash recovery, etc.) before the target accepted.
    try:
        from engine.buffs import consume_consumable
        consumed = consume_consumable(medic_char, offer["consumable_key"])
        if not consumed:
            display = offer["consumable_key"].replace("_", " ")
            msg = (
                f"  {medic_name} reaches for the {display} — but "
                f"the kit is empty. Nothing happens."
            )
            await medic_session.send_line(msg)
            if not is_self:
                await target_session.send_line(msg)
            log.info(
                "[stim] consume-failed-at-resolve: medic=%s "
                "consumable=%s (offer was placed but stim now missing)",
                medic_char.get("id"), offer["consumable_key"],
            )
            return
        # Persist the deduction. If this fails, the in-memory char
        # has the deduction but the DB doesn't — better than the
        # reverse (player gets free stim).
        try:
            await ctx.db.save_character(
                medic_char["id"],
                attributes=medic_char.get("attributes", "{}"),
            )
        except Exception:
            log.warning(
                "_execute_stim_roll: save_character consume-persist failed",
                exc_info=True,
            )
    except Exception:
        # If the consume helper itself raises (not just returns False),
        # refuse rather than proceed — same reasoning as the offer-time
        # check in StimCommand.execute.
        log.warning(
            "_execute_stim_roll: consume_consumable raised; refusing",
            exc_info=True,
        )
        await medic_session.send_line(
            "  Stim system temporarily unavailable. Try again."
        )
        return

    difficulty = spec["difficulty"]
    if is_self:
        # Per design §3.7: self-stim takes -1D (-3 pips) penalty;
        # we model this by raising effective difficulty by 3.
        difficulty += 3

    result = perform_skill_check(
        medic_char, spec["skill"], difficulty,
        auto_consume_lead=False,  # stims don't consume +lead bonuses
    )

    target_name = target_char.get("name", "Unknown")
    display = offer["consumable_key"].replace("_", " ").title()

    # ── Fumble (Wild Die 1): 2 wound levels, no buff ────────────────
    if result.fumble:
        new_wound = min(
            target_char.get("wound_level", 0) + 2, _WL_DEAD,
        )
        try:
            await ctx.db.save_character(
                target_char["id"], wound_level=new_wound,
            )
            target_char["wound_level"] = new_wound  # local cache
        except Exception:
            log.warning(
                "_execute_stim_roll: save_character fumble-wound failed",
                exc_info=True,
            )
        msg = (
            f"  \033[1;31mFumble.\033[0m {medic_name}'s {display} "
            f"application went badly wrong. {target_name} takes 2 "
            f"wound levels of chemistry shock."
        )
        await medic_session.send_line(msg)
        if not is_self:
            await target_session.send_line(msg)
        log.info(
            "[stim] fumble: medic=%s target=%s consumable=%s",
            medic_char.get("id"), target_char.get("id"),
            offer["consumable_key"],
        )
        return

    # ── Failure (not fumble) ────────────────────────────────────────
    if not result.success:
        # Optional wound escalation (adrenaline shot)
        wound_levels = spec.get("failure_wound_levels", 0)
        if wound_levels:
            new_wound = min(
                target_char.get("wound_level", 0) + wound_levels,
                _WL_DEAD,
            )
            try:
                await ctx.db.save_character(
                    target_char["id"], wound_level=new_wound,
                )
                target_char["wound_level"] = new_wound
            except Exception:
                log.warning(
                    "_execute_stim_roll: save_character failure-wound failed",
                    exc_info=True,
                )

        # Optional side-effect debuff
        side_buff = spec.get("side_effect_buff_type")
        if side_buff:
            try:
                add_buff(target_char, side_buff)
                # Persist the modified attributes
                await ctx.db.save_character(
                    target_char["id"],
                    attributes=target_char.get("attributes", "{}"),
                )
            except Exception:
                log.warning(
                    "_execute_stim_roll: add_buff side-effect failed",
                    exc_info=True,
                )

        await medic_session.send_line(spec["fail_msg"])
        if not is_self:
            await target_session.send_line(spec["fail_msg"])
        log.info(
            "[stim] failure: medic=%s target=%s consumable=%s margin=%s",
            medic_char.get("id"), target_char.get("id"),
            offer["consumable_key"], result.margin,
        )
        return

    # ── Success: apply the buff ────────────────────────────────────
    try:
        add_buff(target_char, spec["buff_type"])
        await ctx.db.save_character(
            target_char["id"],
            attributes=target_char.get("attributes", "{}"),
        )
    except Exception:
        log.warning(
            "_execute_stim_roll: success add_buff failed",
            exc_info=True,
        )
        # Still report success to user; the buff just didn't persist.

    msg = (
        f"  \033[1;32m{display} takes hold.\033[0m {target_name} "
        f"will feel the effect on their next roll within 5 minutes."
    )
    await medic_session.send_line(msg)
    if not is_self:
        await target_session.send_line(msg)
    log.info(
        "[stim] success: medic=%s target=%s consumable=%s margin=%s",
        medic_char.get("id"), target_char.get("id"),
        offer["consumable_key"], result.margin,
    )


# ═══════════════════════════════════════════════════════════════════════════
# +medical — Leaf umbrella (S58)
# ═══════════════════════════════════════════════════════════════════════════
#
# `+medical` is a thin leaf umbrella for the three medical verbs:
# heal (offer), accept (haccept the offer), rate (set healing rate).
# All three stay at their bare keys for backward compatibility; the
# umbrella adds the canonical +-prefix and discovery surface.

_MEDICAL_SWITCH_IMPL: dict = {}

_MEDICAL_ALIAS_TO_SWITCH: dict[str, str] = {
    "":            "heal",
    "healaccept":  "accept",
    "haccept":     "accept",
    "healrate":    "rate",
    "hrate":       "rate",
    # SRB.1 (May 21 2026): wire stim/stimaccept into the umbrella so
    # `+medical stim foo with adrenaline_shot` works alongside the
    # bare `stim foo with adrenaline_shot` form.
    "stim":        "stim",
    "stimaccept":  "stimaccept",
    "saccept":     "stimaccept",
}


class MedicalCommand(BaseCommand):
    """`+medical` umbrella — heal/accept/rate/stim/stimaccept."""
    key = "+medical"
    aliases: list[str] = [
        "heal", "healaccept", "haccept", "healrate", "hrate",
    ]
    help_text = (
        "Medical verbs: 'heal <player>' (offer), 'healaccept' (haccept) "
        "to accept an offer, 'healrate <credits>' to set your rate, "
        "'stim <player> [with <consumable>]' to administer a stim, "
        "'stimaccept' to accept a stim. "
        "Type 'help +medical' for the full reference."
    )
    usage = "+medical [verb] [args]  — see 'help +medical'"
    valid_switches: list[str] = [
        "heal", "accept", "rate", "stim", "stimaccept",
    ]

    async def execute(self, ctx: CommandContext):
        args = ctx.args.strip() if ctx.args else ""
        first, _, rest = args.partition(" ")
        switch = _MEDICAL_ALIAS_TO_SWITCH.get(first.lower(), first.lower())

        impl = _MEDICAL_SWITCH_IMPL.get(switch)
        if impl is not None:
            await impl(ctx, rest)
            return

        await ctx.session.send_line(self.help_text)


def _init_medical_switch_impl():
    """Wire forwarding handlers into _MEDICAL_SWITCH_IMPL."""
    async def _heal(ctx, rest):
        cmd = HealCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _accept(ctx, rest):
        cmd = HealAcceptCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _rate(ctx, rest):
        cmd = HealRateCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    # SRB.1
    async def _stim(ctx, rest):
        cmd = StimCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    async def _stimaccept(ctx, rest):
        cmd = StimAcceptCommand()
        ctx.args = rest
        await cmd.execute(ctx)

    _MEDICAL_SWITCH_IMPL["heal"] = _heal
    _MEDICAL_SWITCH_IMPL["accept"] = _accept
    _MEDICAL_SWITCH_IMPL["rate"] = _rate
    _MEDICAL_SWITCH_IMPL["stim"] = _stim
    _MEDICAL_SWITCH_IMPL["stimaccept"] = _stimaccept


_init_medical_switch_impl()


def register_medical_commands(registry):
    """Register medical commands with the command registry."""
    for cmd in [
        MedicalCommand(),
        HealCommand(), HealAcceptCommand(), HealRateCommand(),
        # SRB.1
        StimCommand(), StimAcceptCommand(),
    ]:
        registry.register(cmd)
