# -*- coding: utf-8 -*-
"""
parser/force_commands.py
Force Powers Commands — WEG D6 Revised & Expanded

Commands:
  force <power> [target]  — use a Force power
  powers                  — list available powers
  forcestatus             — show Force attribute totals and DSP

Wires into the existing character system (control/sense/alter DicePool
attributes, force_points, dark_side_points) without touching combat_commands.py.
"""
import json
import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.character import Character, SkillRegistry
from engine.force_powers import (
    POWERS, get_power, list_powers_for_char, resolve_force_power,
    format_power_list, ForcePower,
)
from engine import buffs
from server import ansi

log = logging.getLogger(__name__)

# Achievement hooks (graceful-drop)
async def _ach_force_hook(db, char_id, event, session=None):
    try:
        from engine.achievements import check_achievement
        await check_achievement(db, char_id, event, session=session)
    except Exception as _e:
        log.debug("silent except in parser/force_commands.py:32: %s", _e, exc_info=True)


_SKILL_REG_CACHE: SkillRegistry | None = None


def _get_skill_reg() -> SkillRegistry:
    global _SKILL_REG_CACHE
    if _SKILL_REG_CACHE is None:
        _SKILL_REG_CACHE = SkillRegistry()
        _SKILL_REG_CACHE.load_file("data/skills.yaml")
    return _SKILL_REG_CACHE


def _char_obj(char_dict: dict) -> Character:
    return Character.from_db_dict(char_dict)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def _find_target_char(ctx: CommandContext, target_name: str):
    """
    Find a target character in the same room by partial name match.
    Returns (char_dict, Character) or (None, None).

    W.2 phase 2: source_char filters to wilderness co-located peers.
    """
    char = ctx.session.character
    room_id = char["room_id"]
    chars_in_room = await ctx.db.get_characters_in_room(room_id, source_char=char)
    target_name_lower = target_name.lower()
    for c in chars_in_room:
        c = dict(c)
        if c["id"] == char["id"]:
            continue
        if c["name"].lower().startswith(target_name_lower):
            return c, _char_obj(c)
    return None, None


async def _save_char_after_force(ctx: CommandContext, char_obj: Character):
    """Persist force-related fields back to DB after a power use."""
    char_dict = ctx.session.character
    # Wound level may have changed (accelerate_healing)
    char_dict["wound_level"] = char_obj.wound_level.value
    # DSP always persists
    char_dict["dark_side_points"] = char_obj.dark_side_points
    await ctx.db.save_character(
        char_dict["id"],
        wound_level=char_obj.wound_level.value,
        dark_side_points=char_obj.dark_side_points,
    )


async def _save_target_after_force(ctx: CommandContext,
                                    target_dict: dict, target_obj: Character):
    """Persist wound changes on a Force-affected target."""
    await ctx.db.save_character(
        target_dict["id"],
        wound_level=target_obj.wound_level.value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DROP 4a (2026-06-04): NPC targeting + structured-effect application
# ─────────────────────────────────────────────────────────────────────────────

async def _find_target_npc(ctx: CommandContext, target_name: str):
    """Find an NPC in the caster's room by partial name match.

    Returns (npc_row_dict, Character) or (None, None). The Character is
    built from char_sheet_json via the canonical build_npc_character so
    opposed willpower rolls read the NPC's real stats (a weak-minded
    being resists with its low governing attribute and is easily swayed).
    """
    from engine.npc_combat_ai import build_npc_character
    room_id = ctx.session.character["room_id"]
    try:
        npcs = await ctx.db.get_npcs_in_room(room_id)
    except Exception:
        log.debug("[force] _find_target_npc lookup failed", exc_info=True)
        return None, None
    tl = target_name.lower()
    for n in npcs:
        n = dict(n)
        if str(n.get("name", "")).lower().startswith(tl):
            obj = build_npc_character(n)
            if obj is None:
                # No usable sheet — present but statless; resolves as
                # weak-willed so the power can still land.
                obj = Character.from_npc_sheet(n.get("id", 0), {})
            return n, obj
    return None, None


async def _gather_room_beings(ctx: CommandContext, char_dict: dict):
    """Return (pcs, npcs) in the caster's room, excluding the caster."""
    room_id = char_dict["room_id"]
    pcs = []
    try:
        for c in await ctx.db.get_characters_in_room(room_id, source_char=char_dict):
            c = dict(c)
            if c.get("id") != char_dict.get("id"):
                pcs.append(c)
    except Exception:
        log.debug("[force] gather PCs failed", exc_info=True)
    npcs = []
    try:
        npcs = [dict(n) for n in await ctx.db.get_npcs_in_room(room_id)]
    except Exception:
        log.debug("[force] gather NPCs failed", exc_info=True)
    return pcs, npcs


def _npc_sheet(npc_row: dict) -> dict:
    try:
        cs = npc_row.get("char_sheet_json", "{}")
        return json.loads(cs) if isinstance(cs, str) else (cs or {})
    except Exception:
        return {}


def _npc_ai(npc_row: dict) -> dict:
    try:
        cfg = npc_row.get("ai_config_json", "{}")
        return json.loads(cfg) if isinstance(cfg, str) else (cfg or {})
    except Exception:
        return {}


def _is_force_being(row: dict, is_npc: bool) -> bool:
    if not is_npc:
        # force_sensitive is DERIVED (control/sense/alter) — read it off a parsed
        # Character, not the stale/absent raw row key.
        from engine.character import Character
        return bool(Character.from_db_dict(row).force_sensitive)
    sheet = _npc_sheet(row)
    return bool(sheet.get("force_sensitive") or sheet.get("is_jedi")
                or sheet.get("force_user"))


def _is_dark_being(row: dict, is_npc: bool) -> bool:
    try:
        if not is_npc:
            return int(row.get("dark_side_points", 0) or 0) > 0
        sheet = _npc_sheet(row)
        if int(sheet.get("dark_side_points", 0) or 0) > 0:
            return True
        return bool(sheet.get("dark_side")
                    or _npc_ai(row).get("alignment") == "dark")
    except Exception:
        return False


async def _apply_life_sense(ctx: CommandContext, char_dict: dict):
    pcs, npcs = await _gather_room_beings(ctx, char_dict)
    total = len(pcs) + len(npcs)
    if total == 0:
        await ctx.session.send_line(
            "  You sense no other living presence here — only yourself."
        )
        return
    names = [p.get("name", "someone") for p in pcs]
    names += [f"{n.get('name', 'a being')} ({n.get('species', 'being')})"
              for n in npcs]
    shown = ", ".join(names[:8])
    more = f", and {len(names) - 8} more" if len(names) > 8 else ""
    plural = "presence" if total == 1 else "presences"
    await ctx.session.send_line(
        f"  You feel {total} living {plural} here: {shown}{more}."
    )


async def _apply_sense_force(ctx: CommandContext, char_dict: dict):
    pcs, npcs = await _gather_room_beings(ctx, char_dict)
    force_beings, dark_beings = [], []
    for p in pcs:
        if _is_force_being(p, False):
            force_beings.append(p.get("name", "someone"))
        if _is_dark_being(p, False):
            dark_beings.append(p.get("name", "someone"))
    for n in npcs:
        if _is_force_being(n, True):
            force_beings.append(n.get("name", "a being"))
        if _is_dark_being(n, True):
            dark_beings.append(n.get("name", "a being"))
    if not force_beings and not dark_beings:
        await ctx.session.send_line(
            "  The Force is quiet here. You sense no other Force-sensitive "
            "and no echo of the dark side."
        )
        return
    if force_beings:
        await ctx.session.send_line(
            f"  The Force runs strong in: {', '.join(force_beings)}."
        )
    if dark_beings:
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_RED}A shadow of the dark side clings to: "
            f"{', '.join(dark_beings)}.{ansi.RESET}"
        )


def _pry_fact(npc_row: dict) -> str:
    """A real fact to reveal from an NPC's sheet / AI config / description."""
    sheet = _npc_sheet(npc_row)
    ai = _npc_ai(npc_row)
    for key in ("secret", "knows", "true_intent", "motive", "disposition"):
        v = sheet.get(key) or ai.get(key)
        if v:
            return str(v)
    desc = (npc_row.get("description") or "").strip()
    if desc:
        return f"their surface thoughts echo what you can already see: {desc[:160]}"
    species = npc_row.get("species", "being")
    return (f"little is hidden — only the ordinary worries of a "
            f"{species} going about their day")


async def _apply_mind_influence(ctx: CommandContext, result, char_dict: dict,
                                 target_dict: dict, target_obj, target_is_npc: bool,
                                 dominate: bool):
    verb = "command" if dominate else "suggestion"
    tname = target_dict.get("name", "they") if target_dict else "they"

    # ── PC target: OFFERED EFFECT — never auto-override another player. ──
    if not target_is_npc:
        offered = (
            f"{char_dict['name']} reaches toward your mind with a Force "
            f"{verb}. You feel the nudge — it is yours to play out or resist."
        )
        delivered = False
        try:
            tsess = ctx.session_mgr.find_by_character(target_dict["id"])
            if tsess is not None:
                await tsess.send_line(
                    f"  {ansi.BRIGHT_BLUE}[FORCE]{ansi.RESET} {offered}"
                )
                delivered = True
        except Exception:
            log.debug("[force] offered-effect delivery failed", exc_info=True)
        await ctx.session.send_line(
            f"  Your {verb} is laid before {tname} — "
            + ("they will choose how it lands." if delivered
               else "(they are not connected right now to feel it).")
        )
        return

    # ── NPC target: the engine resolves the effect deterministically. ──
    is_guard = False
    try:
        from engine.city_guard_runtime import is_city_guard
        is_guard = is_city_guard(target_dict)
    except Exception:
        log.debug("[force] is_city_guard check failed", exc_info=True)

    if is_guard:
        try:
            buffs.add_buff(char_dict, "mind_trick_unseen")
            await ctx.db.save_character(
                char_dict["id"], attributes=char_dict["attributes"]
            )
        except Exception:
            log.debug("[force] applying mind_trick_unseen failed", exc_info=True)
        await ctx.session.send_line(
            f"  {tname}'s attention slides off you. For a few minutes they "
            f"see no reason to challenge you."
            + ("  Their guard breaks utterly — they would wave you past anything."
               if dominate else "")
        )
        return

    # Generic NPC: pry a fact loose (a command pries harder, and truer).
    fact = _pry_fact(target_dict)
    lead = ("Compelled, they answer truthfully" if dominate
            else "Loose-tongued, they let slip")
    await ctx.session.send_line(f"  {lead}: {fact}")


async def _apply_disarm(ctx: CommandContext, char_dict: dict, target_dict: dict,
                        target_obj, target_is_npc: bool):
    tname = target_dict.get("name", "your target") if target_dict else "your target"
    weapon = getattr(target_obj, "equipped_weapon", "") if target_obj else ""
    if not weapon:
        await ctx.session.send_line(
            f"  {tname} held no weapon for the Force to tear away."
        )
        return
    if not target_is_npc:
        try:
            # Canonical per-slot write: clear the weapon slot, keep armor.
            # (The old raw pop("weapon") left a legacy shape-2 top-level
            # instance untouched, so the weapon stayed equipped.)
            from engine.items import read_equipment, write_equipment
            _slots = read_equipment(target_dict.get("equipment", "{}"))
            target_dict["equipment"] = write_equipment(
                weapon=None, armor=_slots["armor"])
            await ctx.db.save_character(
                target_dict["id"], equipment=target_dict["equipment"]
            )
        except Exception:
            log.debug("[force] PC disarm persist failed", exc_info=True)
        try:
            tsess = ctx.session_mgr.find_by_character(target_dict["id"])
            if tsess is not None:
                await tsess.send_line(
                    f"  {ansi.BRIGHT_BLUE}[FORCE]{ansi.RESET} Your weapon is "
                    f"ripped from your hands and clatters away!"
                )
        except Exception:
            log.debug("[force] disarm notify failed", exc_info=True)
    else:
        try:
            sheet = _npc_sheet(target_dict)
            eq = sheet.get("equipment", {})
            if isinstance(eq, dict):
                eq.pop("weapon", None)
                sheet["equipment"] = eq
            sheet.pop("weapon", None)
            await ctx.db.update_npc(
                target_dict["id"], char_sheet_json=json.dumps(sheet)
            )
        except Exception:
            log.debug("[force] NPC disarm persist failed", exc_info=True)
    await ctx.session.send_line(
        f"  {tname}'s weapon is torn from their grip and skitters away across "
        f"the ground."
    )


async def _apply_telepathy(ctx: CommandContext, result, char_dict: dict,
                           target_dict: dict, target_obj, target_is_npc: bool):
    tname = target_dict.get("name", "they") if target_dict else "they"

    # NPC: skim surface thoughts (receptive telepathy reuses the pry read).
    if target_is_npc:
        await ctx.session.send_line(
            f"  You brush against {tname}'s surface thoughts: {_pry_fact(target_dict)}"
        )
        return

    # PC: deep communion if an active Master-Padawan bond links the two.
    cid = char_dict.get("id")
    tid = target_dict.get("id")
    bonded = False
    try:
        b = await ctx.db.get_active_bond_for_padawan(cid)
        if b and b.get("master_char_id") == tid:
            bonded = True  # caster is the padawan, target the master
        if not bonded:
            b2 = await ctx.db.get_active_bond_for_padawan(tid)
            if b2 and b2.get("master_char_id") == cid:
                bonded = True  # target is the padawan, caster the master
    except Exception:
        log.debug("[force] telepathy bond lookup failed", exc_info=True)

    if bonded:
        wl = getattr(target_obj, "wound_level", None)
        status = getattr(wl, "name", "present")
        status = str(status).replace("_", " ").lower()
        await ctx.session.send_line(
            f"  Through your shared bond you reach {tname} clearly across any "
            f"distance. You feel their presence — {status}."
        )
        try:
            ts = ctx.session_mgr.find_by_character(tid)
            if ts is not None:
                await ts.send_line(
                    f"  {ansi.BRIGHT_BLUE}[FORCE]{ansi.RESET} {char_dict['name']} "
                    f"reaches you through your bond — a warmth at the edge of thought."
                )
        except Exception:
            log.debug("[force] telepathy bond notify failed", exc_info=True)
        return

    # No bond: a wordless mind-touch, offered for the other player to answer.
    delivered = False
    try:
        ts = ctx.session_mgr.find_by_character(tid)
        if ts is not None:
            await ts.send_line(
                f"  {ansi.BRIGHT_BLUE}[FORCE]{ansi.RESET} {char_dict['name']} "
                f"brushes your mind with a wordless thought — it is yours to answer."
            )
            delivered = True
    except Exception:
        log.debug("[force] telepathy touch delivery failed", exc_info=True)
    await ctx.session.send_line(
        f"  You reach toward {tname}'s mind — "
        + ("they will sense the touch." if delivered
           else "(they are not connected right now to feel it).")
    )


async def _apply_sense_lie(ctx: CommandContext, result, char_dict: dict,
                           target_dict: dict, target_obj, target_is_npc: bool):
    tname = target_dict.get("name", "they") if target_dict else "they"

    # PC: offered read — the player decides what their tell reveals.
    if not target_is_npc:
        try:
            ts = ctx.session_mgr.find_by_character(target_dict.get("id"))
            if ts is not None:
                await ts.send_line(
                    f"  {ansi.BRIGHT_BLUE}[FORCE]{ansi.RESET} {char_dict['name']} "
                    f"weighs the sincerity of your words — answer as you will."
                )
        except Exception:
            log.debug("[force] sense_lie offered delivery failed", exc_info=True)
        await ctx.session.send_line(
            f"  You reach for the truth of {tname}'s words — what their face "
            f"shows is theirs to play."
        )
        return

    # NPC: read real deception / hidden-intent flags.
    sheet = _npc_sheet(target_dict)
    ai = _npc_ai(target_dict)
    deceptive = bool(sheet.get("lying") or sheet.get("deceptive")
                     or ai.get("lying") or ai.get("deceptive"))
    hidden = None
    for k in ("secret", "true_intent", "motive"):
        v = sheet.get(k) or ai.get(k)
        if v:
            hidden = str(v)
            break
    if deceptive or hidden:
        line = f"  You sense {tname} is hiding something."
        if hidden:
            line += f" Beneath their words: {hidden}"
        await ctx.session.send_line(line)
    else:
        await ctx.session.send_line(
            f"  You sense no deceit in {tname} — they believe what they say."
        )


def _npc_is_hostile(npc_row: dict) -> bool:
    ai = _npc_ai(npc_row)
    if ai.get("hostile") is True:
        return True
    return str(ai.get("disposition", "")).lower() in ("hostile", "aggressive")


async def _apply_farseeing(ctx: CommandContext, char_dict: dict):
    # Simple portent: tied to real nearby danger if any (rich visions: G5).
    _pcs, npcs = await _gather_room_beings(ctx, char_dict)
    if any(_npc_is_hostile(n) for n in npcs):
        await ctx.session.send_line(
            "  A vision sharpens for an instant: danger close at hand. Something "
            "near you means you harm."
        )
    else:
        await ctx.session.send_line(
            "  Images drift past — shapes, shadows, nothing certain. The path "
            "ahead is quiet, for now."
        )


async def _apply_danger_sense(ctx: CommandContext, char_dict: dict):
    combatant = None
    try:
        from parser.combat_commands import _ensure_in_combat
        _combat, combatant = _ensure_in_combat(char_dict)
    except Exception:
        log.debug("[force] danger_sense combat lookup failed", exc_info=True)
    if combatant is not None:
        combatant.initiative_reroll = True
        await ctx.session.send_line(
            "  Danger flares at the edge of your senses — you will move to meet "
            "it. (Your next initiative is rerolled, keeping the better.)"
        )
    else:
        await ctx.session.send_line(
            "  You cast your senses outward for danger. Nothing threatens you "
            "here and now — the Force is still."
        )


async def _apply_force_effects(ctx: CommandContext, result, char_dict: dict,
                                char_obj, target_dict, target_obj,
                                target_is_npc: bool):
    """Turn a resolved power's effect_kind into a real, applied outcome."""
    if not result.success:
        return
    kind = result.effect_kind
    try:
        if kind == "life_sense":
            await _apply_life_sense(ctx, char_dict)
        elif kind == "sense_force":
            await _apply_sense_force(ctx, char_dict)
        elif kind in ("suggestion", "domination"):
            await _apply_mind_influence(
                ctx, result, char_dict, target_dict, target_obj,
                target_is_npc, dominate=(kind == "domination"),
            )
        elif kind == "disarm":
            await _apply_disarm(ctx, char_dict, target_dict, target_obj, target_is_npc)
        elif kind == "telepathy":
            await _apply_telepathy(ctx, result, char_dict, target_dict, target_obj, target_is_npc)
        elif kind == "sense_lie":
            await _apply_sense_lie(ctx, result, char_dict, target_dict, target_obj, target_is_npc)
        elif kind == "farseeing":
            await _apply_farseeing(ctx, char_dict)
        elif kind == "danger_sense":
            await _apply_danger_sense(ctx, char_dict)
    except Exception:
        log.debug("[force] _apply_force_effects failed (kind=%s)", kind, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

class ForceCommand(BaseCommand):
    key = "force"
    aliases = ["useforce"]
    help_text = (
        "Use a Force power. Usage: force <power name> [target]\n"
        "Examples: force control_pain\n"
        "          force telekinesis R2\n"
        "          force life_sense\n"
        "Type 'powers' to see available powers."
    )
    usage = "force <power> [target]"

    async def execute(self, ctx: CommandContext):
        char_dict = ctx.session.character
        char_obj = _char_obj(char_dict)

        # Drop 4b: snapshot DSP before the power resolves so we can detect a
        # first crossing into "dark-side wanted" and fire the notice once.
        dsp_before = char_dict.get("dark_side_points", 0)

        # ── Force-sensitive check ──────────────────────────────────────────
        if not char_obj.force_sensitive:
            await ctx.session.send_line(
                "  You are not Force-sensitive. "
                "The Force flows through you but you cannot grasp it."
            )
            return

        # ── Parse args: power [target] ─────────────────────────────────────
        if not ctx.args:
            await ctx.session.send_line(
                "  Usage: force <power name> [target]\n"
                "  Type 'powers' to see available powers."
            )
            return

        parts = ctx.args.strip().split(None, 1)
        raw_key = parts[0]
        target_name = parts[1].strip() if len(parts) > 1 else None

        power = get_power(raw_key)
        if power is None:
            await ctx.session.send_line(
                f"  Unknown Force power '{raw_key}'. Type 'powers' to see options."
            )
            return

        # ── Skill check — does the char have the required skills? ──────────
        sr = _get_skill_reg()
        missing = []
        for skill in power.skills:
            pool = char_obj.get_attribute(skill)
            if pool.dice == 0 and pool.pips == 0:
                missing.append(skill.title())
        if missing:
            await ctx.session.send_line(
                f"  You lack the Force skill(s) needed: {', '.join(missing)}. "
                f"You must develop {', '.join(missing)} to use {power.name}."
            )
            return

        # ── Resolve target if needed ───────────────────────────────────────
        target_dict = None
        target_obj = None
        target_is_npc = False
        if power.target == "target":
            if not target_name:
                await ctx.session.send_line(
                    f"  '{power.name}' requires a target. "
                    f"Usage: force {raw_key} <target name>"
                )
                return
            target_dict, target_obj = await _find_target_char(ctx, target_name)
            if target_obj is None:
                # Drop 4a: fall back to an NPC in the room (guards,
                # merchants, bystanders). The opposed mind roll and the
                # disarm both read the NPC's real sheet.
                npc_row, target_obj = await _find_target_npc(ctx, target_name)
                if target_obj is not None:
                    target_is_npc = True
                    target_dict = npc_row
            if target_obj is None:
                await ctx.session.send_line(
                    f"  No one named '{target_name}' is here."
                )
                return

        # ── WoW.3c (May 24 2026): Weight-aware fall check ──────────────
        # If this Jedi has accrued Weight of War, the design §7.1
        # tier modifier applies to fall-check difficulty (+0 / +2
        # / +5 / +10 at Weight 0-50 / 51-100 / 101-150 / 151-200)
        # and Weight ≥ 151 grants 1 extra DSP on a failed fall.
        # Compute both at the parser site (char_dict has the DB
        # row) and pass them in keyword-only so older callers and
        # tests are unaffected.
        weight_mod = 0
        extra_dsp = 0
        try:
            from engine.weight_of_war import (
                dsp_resistance_modifier,
                extra_dsp_on_failed_resist,
                is_jedi_pc,
                get_weight,
            )
            if is_jedi_pc(char_dict):
                w = get_weight(char_dict)
                weight_mod = dsp_resistance_modifier(w)
                extra_dsp = extra_dsp_on_failed_resist(w)
        except Exception:
            log.debug(
                "[WoW.3c] Weight modifier lookup failed for "
                "force-power resolution; falling back to "
                "Weight=0", exc_info=True,
            )

        # ── Resolve the power ──────────────────────────────────────────────
        result = resolve_force_power(
            power_key=power.key,
            char=char_obj,
            skill_reg=sr,
            target_char=target_obj,
            weight_difficulty_mod=weight_mod,
            extra_dsp_on_fail=extra_dsp,
            target_is_npc=target_is_npc,
        )

        # ── Announce to room ───────────────────────────────────────────────
        room_id = char_dict["room_id"]
        if result.success:
            color = ansi.BRIGHT_BLUE
            tag = "FORCE"
        else:
            color = ansi.DIM
            tag = "FORCE"

        # Personal result
        for line in result.narrative.split("\n"):
            await ctx.session.send_line(f"  {color}[{tag}]{ansi.RESET} {line}")

        # Broadcast to room
        if result.success:
            broadcast_msg = _build_room_broadcast(char_dict["name"], power, target_dict)
            await ctx.session_mgr.broadcast_to_room(
                room_id, broadcast_msg, exclude=ctx.session,
                source_char=char_dict,  # W.2 phase 2
            )

        # ── Persist changes ────────────────────────────────────────────────
        await _save_char_after_force(ctx, char_obj)
        # injure_kill applies a wound to the target — persist it for a PC
        # target only (NPC ids index a different table; NPC damage
        # persistence is out of this drop's scope and unchanged).
        if (target_dict and target_obj and not target_is_npc
                and result.damage_dealt > 0):
            await _save_target_after_force(ctx, target_dict, target_obj)

        # ── Drop 4b: dark-side notoriety — auto bounty on crossing ─────────
        # When this power pushes the Jedi across the wanted threshold for
        # the first time, they pick up a faction-agnostic, prestige-only
        # bounty (surfaced on the BH board). Deterministic; no AI cost. The
        # notice fires once, on the crossing.
        try:
            from engine.bounty_board import crossed_into_wanted, dsp_bounty_tier
            if crossed_into_wanted(dsp_before, char_obj.dark_side_points):
                tier = dsp_bounty_tier(char_obj.dark_side_points)
                await ctx.session.send_line(
                    f"  {ansi.BRIGHT_RED}[BOUNTY]{ansi.RESET} The dark side leaves "
                    f"a mark on you. Hunters will know it — you are now "
                    f"{ansi.BOLD}{tier}{ansi.RESET} on the boards. (No credits ride "
                    f"on you; only the prestige of bringing you down.)"
                )
        except Exception:
            log.debug("[force] dsp-bounty crossing check failed", exc_info=True)

        # ── Drop 4a: apply structured social / sense / alter effects ───────
        await _apply_force_effects(
            ctx, result, char_dict, char_obj,
            target_dict, target_obj, target_is_npc,
        )

        # ── Pain suppression: store flag on session char for combat system ─
        if result.pain_suppressed:
            char_dict["_pain_suppressed"] = True
            log.info(f"[force] {char_dict['name']} activated control_pain")

        # ── Fall notification ──────────────────────────────────────────────
        if result.fall_check:
            fall_color = ansi.BRIGHT_RED if result.fall_failed else ansi.BRIGHT_YELLOW
            await ctx.session.send_line(
                f"  {fall_color}[DARK SIDE]{ansi.RESET} "
                + ("You have fallen to the dark side." if result.fall_failed
                   else "You resist the pull of the dark side.")
            )

        # ── Achievement hooks ─────────────────────────────────────────────
        try:
            if result.success and hasattr(ctx.session, "game_server"):
                from engine.achievements import on_force_power_used, on_dark_side_point
                await on_force_power_used(ctx.db, char_dict["id"], session=ctx.session)
                if result.dsp_gained if hasattr(result, "dsp_gained") else False:
                    await on_dark_side_point(ctx.db, char_dict["id"], session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/force_commands.py:229: %s", _e, exc_info=True)


def _build_room_broadcast(char_name: str, power: ForcePower,
                           target_dict: dict | None) -> str:
    """Build the message other players in the room see."""
    target_str = f" on {target_dict['name']}" if target_dict else ""
    templates = {
        "accelerate_healing": f"  {char_name} closes their eyes and focuses. Their wounds visibly improve.",
        "control_pain":       f"  {char_name}'s expression hardens — they push past pain through sheer will.",
        "remain_conscious":   f"  {char_name} staggers but forces themselves upright through the Force.",
        "life_sense":         f"  {char_name}'s eyes go distant. They reach out with the Force.",
        "sense_force":        f"  {char_name} goes still, eyes half-closed, feeling something unseen.",
        "telekinesis":        f"  Objects {target_str} move by themselves — {char_name} extends a hand.",
        "injure_kill":        f"  {char_name} thrusts a hand forward. Dark energy crackles{target_str}!",
        "affect_mind":        f"  {char_name} stares intently at {target_dict['name'] if target_dict else 'nothing'}...",
        "dominate_mind":      f"  {char_name} fixes {target_dict['name'] if target_dict else 'the air'} with a piercing, unblinking stare.",
        "telepathy":          f"  {char_name}'s gaze softens, focused inward and outward at once.",
        "sense_lie":          f"  {char_name} studies {target_dict['name'] if target_dict else 'the room'} with quiet, measuring attention.",
        "farseeing":          f"  {char_name} goes still, eyes unfocused, seeing something far away.",
        "danger_sense":       f"  {char_name} tenses, suddenly alert, as if hearing a sound no one else can.",
    }
    return templates.get(power.key, f"  {char_name} reaches out with the Force{target_str}.")


class PowersCommand(BaseCommand):
    key = "+powers"
    aliases = ["powers", "forcepowers", "listpowers"]
    help_text = "List available Force powers for your character."
    usage = "powers"

    async def execute(self, ctx: CommandContext):
        char_obj = _char_obj(ctx.session.character)
        if not char_obj.force_sensitive:
            await ctx.session.send_line(
                "  You are not Force-sensitive and have no access to Force powers."
            )
            return

        available = list_powers_for_char(char_obj)
        if not available:
            await ctx.session.send_line(
                "  You are Force-sensitive but have no developed Force skills yet. "
                "Increase Control, Sense, or Alter to unlock powers."
            )
            return

        await ctx.session.send_line(
            f"\n  {ansi.BOLD}{ansi.BRIGHT_BLUE}Force Powers Available{ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{'-' * 52}{ansi.RESET}")
        for line in format_power_list(available):
            await ctx.session.send_line(line)

        # Show locked powers (have wrong skills)
        locked = [p for p in POWERS.values() if p not in available]
        if locked:
            await ctx.session.send_line(
                f"\n  {ansi.DIM}Locked (requires further training):{ansi.RESET}"
            )
            for p in locked:
                skills_needed = " + ".join(s.title() for s in p.skills)
                await ctx.session.send_line(
                    f"  {ansi.DIM}  {p.name:<28s} (needs: {skills_needed}){ansi.RESET}"
                )
        await ctx.session.send_line("")


class ForceStatusCommand(BaseCommand):
    key = "+forcestatus"
    aliases = ["forcestatus", "fstatus", "forcesheet", "+fstatus"]
    help_text = "Display your Force attributes, points, and Dark Side status."
    usage = "forcestatus"

    async def execute(self, ctx: CommandContext):
        char_dict = ctx.session.character
        char_obj = _char_obj(char_dict)

        if not char_obj.force_sensitive:
            await ctx.session.send_line(
                "  You are not Force-sensitive."
            )
            return

        fp = char_dict.get("force_points", 0)
        dsp = char_dict.get("dark_side_points", 0)

        await ctx.session.send_line(
            f"\n  {ansi.BOLD}{ansi.BRIGHT_BLUE}Force Status — {char_obj.name}{ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{'-' * 40}{ansi.RESET}")
        await ctx.session.send_line(
            f"  Control : {ansi.BRIGHT_YELLOW}{char_obj.control}{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  Sense   : {ansi.BRIGHT_YELLOW}{char_obj.sense}{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  Alter   : {ansi.BRIGHT_YELLOW}{char_obj.alter}{ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{'-' * 40}{ansi.RESET}")
        await ctx.session.send_line(
            f"  Force Points : {ansi.BRIGHT_BLUE}{fp}{ansi.RESET}"
        )

        # DSP display
        if dsp == 0:
            dsp_display = f"{ansi.BRIGHT_GREEN}0 — Light Side{ansi.RESET}"
        elif dsp < 4:
            dsp_display = f"{ansi.BRIGHT_YELLOW}{dsp} — Touched by Darkness{ansi.RESET}"
        elif dsp < 6:
            dsp_display = f"{ansi.BRIGHT_RED}{dsp} — Danger Zone{ansi.RESET}"
        else:
            dsp_display = f"{ansi.BRIGHT_RED}{dsp} — FALLEN{ansi.RESET}"
        await ctx.session.send_line(f"  Dark Side Pts: {dsp_display}")

        # Available powers
        available = list_powers_for_char(char_obj)
        await ctx.session.send_line(
            f"\n  Powers available: {ansi.BRIGHT_CYAN}{len(available)}{ansi.RESET} "
            f"of {len(POWERS)}  (type 'powers' for details)"
        )
        await ctx.session.send_line("")


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

def register_force_commands(registry):
    """Register Force Power commands."""
    cmds = [
        ForceCommand(),
        PowersCommand(),
        ForceStatusCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
