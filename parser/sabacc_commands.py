# -*- coding: utf-8 -*-
"""
parser/sabacc_commands.py  --  Sabacc card-game gambling.

Commands:
  sabacc [bet]     Play a hand of Sabacc against the house dealer.

Design:
  - Cantina zone only
  - Bet: 50–2,000cr (default 100cr). cantina_brawl event doubles the max.
  - Opposed Gambling roll: player vs NPC dealer (auto-detected or 3D default)
  - Player rolls via perform_skill_check() with Wild Die
  - Dealer rolls flat (no Wild Die — house is smooth, not lucky)
  - Tie: dealer wins (house edge)
  - Win: player earns the bet minus 10% house cut
  - Loss: player loses the bet
  - Cooldown: 5 min after win, 2 min after loss (stored in attributes JSON)
"""

import json
import time
import random
import logging
from parser.commands import BaseCommand, CommandContext
from server import ansi
from engine.skill_checks import perform_skill_check

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BET_MIN          = 50
BET_MAX_DEFAULT  = 2000
BET_DEFAULT      = 100
HOUSE_CUT        = 0.10       # 10% of winnings goes to the house
WIN_COOLDOWN_S   = 300        # 5 minutes
LOSS_COOLDOWN_S  = 120        # 2 minutes
DEALER_DICE      = 3          # Default NPC dealer Gambling pool
DEALER_PIPS      = 0
GAMBLING_DIFF    = 0          # Opposed roll — difficulty not used directly

# Sabacc flavour: outcomes by margin band
_WIN_LINES = [
    "The cards align. You rake in the credits.",
    "A perfect Sabacc! The dealer stares in disbelief.",
    "Your read was right. You take the pot.",
    "The dealer flips his final card — and loses.",
    "Pure calculation. The credits slide your way.",
]
_LOSS_LINES = [
    "The dealer turns over a full Sabacc. You lose.",
    "So close. Your hand collapses at the last moment.",
    "The dealer grins. Your credits disappear.",
    "Bad luck. The cards weren't with you tonight.",
    "You misread the dealer. It costs you.",
]
_TIE_LINES = [
    "A draw — but the house always breaks ties. You lose.",
    "Matched hands. House rule: dealer wins ties.",
    "Equal Sabaccs. The dealer pockets the pot.",
]
_CRIT_LINES = [
    "An Idiot's Array! The rarest hand in the game — the table goes silent.",
    "Pure Sabacc on the first deal. Even the bartender stops to watch.",
    "You called it perfectly. The Force was with you this hand.",
]
_FUMBLE_LINES = [
    "You bomb out. Your hand is worthless. The dealer looks almost sorry.",
    "A bust on the shift — your cards scatter. Embarrassing.",
    "The worst hand possible. Even the Jawas in the corner laugh.",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_zone_name(ctx) -> str:
    """Return lowercase zone name for current room."""
    try:
        room = await ctx.db.get_room(ctx.session.character["room_id"])
        if not room or not room.get("zone_id"):
            return ""
        zone = await ctx.db.get_zone(room["zone_id"])
        return (zone.get("name") or "").lower() if zone else ""
    except Exception:
        log.warning("_get_zone_name: unhandled exception", exc_info=True)
        return ""


def _get_last_sabacc(char: dict) -> float:
    """Read last_sabacc timestamp from attributes JSON."""
    try:
        attrs = json.loads(char.get("attributes", "{}") or "{}")
        return float(attrs.get("last_sabacc", 0))
    except Exception:
        log.warning("get_last_sabacc failed", exc_info=True)
        return 0.0


def _set_last_sabacc(char: dict, timestamp: float) -> str:
    """Set last_sabacc in attributes JSON, return updated JSON string."""
    try:
        attrs = json.loads(char.get("attributes", "{}") or "{}")
    except Exception:
        attrs = {}
    attrs["last_sabacc"] = timestamp
    return json.dumps(attrs)


def _dealer_pool_str(dice: int, pips: int) -> str:
    if pips == 0:
        return f"{dice}D"
    return f"{dice}D+{pips}"


def _roll_flat(dice: int, pips: int) -> int:
    """Flat roll (no Wild Die) — house dealer is consistent, not lucky."""
    import random as _r
    total = sum(_r.randint(1, 6) for _ in range(max(1, dice)))
    total += pips // 3  # pips to bonus (3 pips = 1 point, like D6 rounding)
    return max(1, total)


async def _get_dealer_pool(ctx, char) -> tuple[int, int]:
    """Auto-detect Gambling skill from room NPCs, or use default 3D."""
    try:
        npcs = await ctx.db.get_npcs_in_room(char["room_id"])
        for npc in npcs:
            sheet = json.loads(npc.get("char_sheet_json", "{}") or "{}")
            skills = sheet.get("skills", {})
            gambling_str = skills.get("gambling", "")
            if gambling_str:
                from engine.skill_checks import _parse_dice_str
                d, p = _parse_dice_str(gambling_str)
                if d > 0:
                    return d, p
    except Exception:
        log.warning("_get_dealer_pool: unhandled exception", exc_info=True)
        pass
    return DEALER_DICE, DEALER_PIPS


# ── Command ───────────────────────────────────────────────────────────────────

class SabaccCommand(BaseCommand):
    key = "sabacc"
    # S58 — `+sabacc` canonical form added as alias (single-action
    # module; no umbrella class needed).
    aliases = ["gamble", "cards", "+sabacc"]
    help_text = "Play a hand of Sabacc against the house. Cantina only."
    usage = "sabacc [bet amount]"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        # ── Zone gate ─────────────────────────────────────────────────────────
        zone_name = await _get_zone_name(ctx)
        if "cantina" not in zone_name:
            await ctx.session.send_line(
                ansi.error("  You need to be in a cantina to play Sabacc.")
            )
            await ctx.session.send_line(
                ansi.dim("  Head to Chalmun's Cantina.")
            )
            return

        # ── Bet parsing ───────────────────────────────────────────────────────
        # Check cantina_brawl event for double-bet ceiling
        bet_max = BET_MAX_DEFAULT
        try:
            from engine.world_events import get_world_event_manager
            if get_world_event_manager().is_active("cantina_brawl"):
                bet_max = BET_MAX_DEFAULT * 2
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        arg = (ctx.args or "").strip()
        if arg:
            try:
                bet = int(arg.replace(",", ""))
            except ValueError:
                await ctx.session.send_line(
                    ansi.error(f"  Invalid bet amount: '{arg}'. Usage: sabacc [credits]")
                )
                return
        else:
            bet = BET_DEFAULT

        if bet < BET_MIN:
            await ctx.session.send_line(
                ansi.error(f"  Minimum bet is {BET_MIN:,}cr.")
            )
            return
        if bet > bet_max:
            await ctx.session.send_line(
                ansi.error(f"  Maximum bet is {bet_max:,}cr.")
            )
            return

        credits = char.get("credits", 0)
        if credits < bet:
            await ctx.session.send_line(
                ansi.error(
                    f"  Not enough credits. Bet: {bet:,}cr, you have {credits:,}cr."
                )
            )
            return

        # ── Cooldown check ────────────────────────────────────────────────────
        now = time.time()
        last = _get_last_sabacc(char)
        # Win cooldown is stored as a positive timestamp;
        # loss cooldown as (now - WIN_COOLDOWN_S + LOSS_COOLDOWN_S) so same field works.
        if now - last < WIN_COOLDOWN_S:
            remaining = int(WIN_COOLDOWN_S - (now - last))
            if remaining > 0:
                await ctx.session.send_line(
                    ansi.dim(
                        f"  The dealer is shuffling. "
                        f"Play again in {remaining // 60}m {remaining % 60}s."
                    )
                )
                return

        # ── Skill rolls ───────────────────────────────────────────────────────
        player_result = perform_skill_check(char, "gambling", 1)  # diff=1 → always hits threshold; we compare totals
        dealer_dice, dealer_pips = await _get_dealer_pool(ctx, char)
        dealer_roll = _roll_flat(dealer_dice, dealer_pips)
        dealer_pool_str = _dealer_pool_str(dealer_dice, dealer_pips)

        player_roll = player_result.roll
        pool_str    = player_result.pool_str

        # ── Determine outcome ─────────────────────────────────────────────────
        if player_result.fumble:
            outcome = "fumble"
        elif player_result.critical_success and player_roll > dealer_roll:
            outcome = "critical"
        elif player_roll > dealer_roll:
            outcome = "win"
        elif player_roll == dealer_roll:
            outcome = "tie"   # House wins ties
        else:
            outcome = "loss"

        # ── Apply credits ─────────────────────────────────────────────────────
        if outcome in ("win", "critical"):
            gross_win = bet
            house_rake = max(5, int(gross_win * HOUSE_CUT))
            net_win    = gross_win - house_rake
            new_credits = credits + net_win
            flavour = random.choice(_CRIT_LINES if outcome == "critical" else _WIN_LINES)
            result_line = (
                f"  {ansi.BRIGHT_GREEN}YOU WIN{ansi.RESET}  "
                f"+{net_win:,}cr  (house takes {house_rake:,}cr)"
            )
            cooldown_ts = now  # Full WIN_COOLDOWN
        else:
            new_credits = credits - bet
            new_credits = max(0, new_credits)
            if outcome == "fumble":
                flavour = random.choice(_FUMBLE_LINES)
            elif outcome == "tie":
                flavour = random.choice(_TIE_LINES)
            else:
                flavour = random.choice(_LOSS_LINES)
            result_line = f"  {ansi.BRIGHT_RED}YOU LOSE{ansi.RESET}  -{bet:,}cr"
            # Loss cooldown: store shifted timestamp so WIN_COOLDOWN check
            # naturally becomes LOSS_COOLDOWN effective wait
            cooldown_ts = now - (WIN_COOLDOWN_S - LOSS_COOLDOWN_S)

        # ── Persist ───────────────────────────────────────────────────────────
        char["credits"] = new_credits
        new_attrs = _set_last_sabacc(char, cooldown_ts)
        char["attributes"] = new_attrs
        await ctx.db.save_character(
            char["id"],
            credits=new_credits,
            attributes=new_attrs,
        )

        # ── Output ────────────────────────────────────────────────────────────
        margin = player_roll - dealer_roll
        sign   = "+" if margin >= 0 else ""
        await ctx.session.send_line(
            f"\n  {ansi.BRIGHT_YELLOW}=== Sabacc ==={ansi.RESET}  "
            f"Bet: {bet:,}cr"
        )
        await ctx.session.send_line(
            f"  You:    {ansi.BRIGHT_WHITE}{pool_str}{ansi.RESET} "
            f"→ roll {player_result.roll}"
            + (f"  {ansi.BRIGHT_RED}[FUMBLE]{ansi.RESET}" if player_result.fumble else "")
            + (f"  {ansi.BRIGHT_GREEN}[CRITICAL]{ansi.RESET}" if player_result.critical_success else "")
        )
        await ctx.session.send_line(
            f"  Dealer: {ansi.DIM}{dealer_pool_str}{ansi.RESET} "
            f"→ roll {dealer_roll}  {ansi.DIM}(margin: {sign}{margin}){ansi.RESET}"
        )
        await ctx.session.send_line(f"  {ansi.DIM}{flavour}{ansi.RESET}")
        await ctx.session.send_line(result_line)
        await ctx.session.send_line(
            f"  Balance: {new_credits:,}cr\n"
        )

        # Room broadcast (brief, no credits shown to bystanders)
        broadcast_outcome = "wins" if outcome in ("win", "critical") else "loses"
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {ansi.player_name(char.get('name', 'Someone'))} "
            f"plays a hand of Sabacc and {broadcast_outcome}.",
            exclude=ctx.session,
        )
        # Spacer quest: sabacc played
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(ctx.session, ctx.db, "sabacc")
        except Exception as _e:
            log.debug("silent except in parser/sabacc_commands.py:318: %s", _e, exc_info=True)
        # Achievement: sabacc_win
        if outcome in ("win", "critical"):
            try:
                from engine.achievements import on_sabacc_win
                await on_sabacc_win(ctx.db, char["id"], session=ctx.session)
            except Exception as _e:
                log.debug("silent except in parser/sabacc_commands.py:325: %s", _e, exc_info=True)


# ── Registration ──────────────────────────────────────────────────────────────

def register_sabacc_commands(registry) -> None:
    registry.register(SabaccCommand())
