# -*- coding: utf-8 -*-
"""
parser/channel_commands.py  --  Communication Channel Commands
SW_MUSH  |  Player Engagement P4

Commands:
  ooc <message>              -- Global OOC chat (alias: newbie)
  comlink <message>          -- Planet-wide IC comlink (alias: cl)
  fcomm <message>            -- Faction IC channel (alias: fc)
  faction [set <faction>]    -- Show or change your faction affiliation
  commfreq <freq> <message>  -- Transmit on a custom frequency (alias: cf)
  tune <freq>                -- Tune into a custom frequency
  untune <freq>              -- Untune from a custom frequency
  freqs                      -- List your tuned frequencies
  channels                   -- Show channel overview + online count
  who                        -- List online players with location + status

Register via: register_channel_commands(registry)
"""

import json
import logging

from server import ansi
from server.channels import get_channel_manager, FACTIONS, FACTION_LABELS, get_faction
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _save_faction(ctx: CommandContext, char_id: int, faction: str) -> None:
    """Persist faction into character attributes JSON."""
    char = ctx.session.character
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs) if attrs else {}
        attrs["faction"] = faction
        await ctx.db._db.execute(
            "UPDATE characters SET attributes = ? WHERE id = ?",
            (json.dumps(attrs), char_id),
        )
        await ctx.db._db.commit()
        char["attributes"] = json.dumps(attrs)
    except Exception as e:
        log.warning("[channels] Failed to save faction for char %d: %s", char_id, e)


# ── OOC ───────────────────────────────────────────────────────────────────────

class OocCommand(BaseCommand):
    key = "ooc"
    aliases = ["newbie", "oocsay"]
    help_text = (
        "Global out-of-character chat. Visible to all online players.\n"
        "  Alias 'newbie' is the new-player help channel.\n"
        "  Usage: ooc <message>"
    )
    usage = "ooc <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        message = (ctx.args or "").strip()
        if not message:
            await ctx.session.send_line("  Usage: ooc <message>")
            await ctx.session.send_line("  Example: ooc Does anyone know where the mission board is?")
            return
        cm = get_channel_manager()
        count = await cm.broadcast_ooc(ctx.session_mgr, char["name"], message)
        if count == 1:
            await ctx.session.send_line(ansi.dim("  (No other players online to hear you.)"))


# ── Comlink ───────────────────────────────────────────────────────────────────

class ComlinkCommand(BaseCommand):
    key = "comlink"
    aliases = ["cl", "clink"]
    help_text = (
        "Planet-wide in-character comlink. Broadcasts to all online players.\n"
        "  Note: 'comm'/'comms' are ship-to-ship space comms. This is the ground channel.\n"
        "  Usage: comlink <message>"
    )
    usage = "comlink <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        message = (ctx.args or "").strip()
        if not message:
            await ctx.session.send_line("  Usage: comlink <message>")
            await ctx.session.send_line("  Example: comlink Anyone in the spaceport district?")
            return
        cm = get_channel_manager()
        count = await cm.broadcast_comlink(ctx.session_mgr, char["name"], message)
        if count == 1:
            await ctx.session.send_line(ansi.dim("  (No other players online to hear you.)"))


# ── Faction Chat ──────────────────────────────────────────────────────────────

class FcommCommand(BaseCommand):
    key = "fcomm"
    aliases = ["fc", "faction-comm"]
    help_text = (
        "Faction-only in-character comms channel.\n"
        "  Reaches only online members of your faction.\n"
        "  Use 'faction' to view or change your affiliation.\n"
        "  Usage: fcomm <message>"
    )
    usage = "fcomm <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        message = (ctx.args or "").strip()
        if not message:
            await ctx.session.send_line("  Usage: fcomm <message>")
            await ctx.session.send_line("  Tip: use 'faction' to see your current affiliation.")
            return
        faction = get_faction(char)
        label = FACTION_LABELS.get(faction, faction.title())
        cm = get_channel_manager()
        count = await cm.broadcast_fcomm(ctx.session_mgr, char["name"], faction, message)
        if count == 1:
            await ctx.session.send_line(ansi.dim(f"  (No other {label} members online.)"))


# ── Faction Management ────────────────────────────────────────────────────────

class FactionCommand(BaseCommand):
    key = "faction"
    aliases = ["affiliation"]
    help_text = (
        "View or set your faction affiliation.\n"
        "  Valid factions: Imperial, Rebel, Criminal, Independent\n"
        "  Usage: faction              -- show current faction\n"
        "         faction set <name>   -- change faction"
    )
    usage = "faction [set <faction>]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        args = (ctx.args or "").strip()
        if not args:
            faction = get_faction(char)
            label = FACTION_LABELS.get(faction, faction.title())
            valid = ", ".join(FACTION_LABELS.values())
            await ctx.session.send_line(ansi.header("=== Faction ==="))
            await ctx.session.send_line(f"  Current affiliation: {ansi.highlight(label)}")
            await ctx.session.send_line(f"  Valid factions: {valid}")
            await ctx.session.send_line("  Change with: faction set <name>")
            return
        sub, _, rest = args.partition(" ")
        if sub.lower() != "set" or not rest.strip():
            await ctx.session.send_line("  Usage: faction set <faction name>")
            return
        new_faction = rest.strip().lower()
        if new_faction not in FACTIONS:
            valid = ", ".join(FACTION_LABELS.values())
            await ctx.session.send_line(ansi.error(f"Unknown faction '{rest.strip()}'. Valid: {valid}"))
            return
        old_faction = get_faction(char)
        if new_faction == old_faction:
            await ctx.session.send_line(f"  You are already {FACTION_LABELS[new_faction]}.")
            return
        await _save_faction(ctx, char["id"], new_faction)
        await ctx.session.send_line(
            ansi.success(f"Faction set to {ansi.highlight(FACTION_LABELS[new_faction])}.")
        )


# ── Custom Frequency ──────────────────────────────────────────────────────────

class TuneCommand(BaseCommand):
    key = "tune"
    aliases = ["tunein"]
    help_text = (
        "Tune your comlink to a custom frequency channel (1-9999).\n"
        "  Agree on a number with your crew for encrypted-feeling comms.\n"
        "  Usage: tune <frequency>"
    )
    usage = "tune <frequency>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line("  Usage: tune <frequency>  (e.g. tune 1138)")
            return
        try:
            freq = int(args)
            if not (1 <= freq <= 9999):
                raise ValueError
        except ValueError:
            await ctx.session.send_line(ansi.error("Frequency must be a number between 1 and 9999."))
            return
        cm = get_channel_manager()
        if cm.is_tuned(char["id"], freq):
            await ctx.session.send_line(f"  Already tuned to frequency {ansi.highlight(str(freq))}.")
            return
        cm.tune(char["id"], freq)
        await ctx.session.send_line(ansi.success(f"Tuned to frequency {ansi.highlight(str(freq))}."))
        await ctx.session.send_line(f"  Transmit with: commfreq {freq} <message>")


class UntuneCommand(BaseCommand):
    key = "untune"
    aliases = ["tuneout"]
    help_text = "Untune from a custom frequency.  Usage: untune <frequency>"
    usage = "untune <frequency>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line("  Usage: untune <frequency>")
            return
        try:
            freq = int(args)
        except ValueError:
            await ctx.session.send_line(ansi.error("Frequency must be a number."))
            return
        cm = get_channel_manager()
        if not cm.is_tuned(char["id"], freq):
            await ctx.session.send_line(f"  You are not tuned to frequency {freq}.")
            return
        cm.untune(char["id"], freq)
        await ctx.session.send_line(ansi.success(f"Untuned from frequency {freq}."))


class FreqsCommand(BaseCommand):
    key = "freqs"
    aliases = ["frequencies", "myfreqs"]
    help_text = "List the custom frequencies you are currently tuned to."
    usage = "freqs"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        cm = get_channel_manager()
        freqs = cm.tuned_freqs(char["id"])
        if not freqs:
            await ctx.session.send_line("  You are not tuned to any custom frequencies.")
            await ctx.session.send_line("  Use 'tune <number>' to subscribe.")
            return
        await ctx.session.send_line(ansi.header("=== Tuned Frequencies ==="))
        for f in freqs:
            await ctx.session.send_line(
                f"  {ansi.highlight(str(f))}  -- transmit: commfreq {f} <message>"
            )


class CommFreqCommand(BaseCommand):
    key = "commfreq"
    aliases = ["cf", "freq"]
    help_text = (
        "Transmit on a custom comlink frequency.\n"
        "  You must tune in first with 'tune <frequency>'.\n"
        "  Usage: commfreq <frequency> <message>"
    )
    usage = "commfreq <frequency> <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        args = (ctx.args or "").strip()
        if not args or " " not in args:
            await ctx.session.send_line(
                "  Usage: commfreq <frequency> <message>\n"
                "  Example: commfreq 1138 Meet at docking bay in 5 minutes."
            )
            return
        freq_str, _, message = args.partition(" ")
        message = message.strip()
        try:
            freq = int(freq_str)
            if not (1 <= freq <= 9999):
                raise ValueError
        except ValueError:
            await ctx.session.send_line(ansi.error("Frequency must be a number between 1 and 9999."))
            return
        if not message:
            await ctx.session.send_line("  Please include a message to transmit.")
            return
        cm = get_channel_manager()
        count = await cm.broadcast_freq(ctx.session_mgr, char["name"], freq, message, char["id"])
        if count == -1:
            await ctx.session.send_line(
                ansi.error(f"Not tuned to frequency {freq}. Use 'tune {freq}' first.")
            )
        elif count == 1:
            await ctx.session.send_line(ansi.dim(f"  (No other listeners on frequency {freq}.)"))


# ── Channel Overview ──────────────────────────────────────────────────────────

class ChannelsCommand(BaseCommand):
    key = "channels"
    aliases = ["chan", "channellist"]
    help_text = "Show available communication channels and your current settings."
    usage = "channels"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        cm = get_channel_manager()
        online = cm.online_count(ctx.session_mgr)
        faction = get_faction(char)
        faction_label = FACTION_LABELS.get(faction, faction.title())
        freqs = cm.tuned_freqs(char["id"])
        await ctx.session.send_line(ansi.header("=== Communication Channels ==="))
        await ctx.session.send_line(
            f"  {ansi.highlight('ooc')} / newbie      Global OOC chat  ({online} player(s) online)"
        )
        await ctx.session.send_line(
            f"  {ansi.highlight('comlink')} / cl      Planet-wide IC comlink"
        )
        await ctx.session.send_line(
            f"  {ansi.highlight('fcomm')} / fc        Faction channel  "
            f"(your faction: {ansi.highlight(faction_label)})"
        )
        await ctx.session.send_line(
            f"  {ansi.highlight('commfreq')} / cf     Custom frequency  "
            f"(tuned: {', '.join(str(f) for f in freqs) if freqs else 'none'})"
        )
        await ctx.session.send_line("")
        await ctx.session.send_line("  faction set <name>       change affiliation")
        await ctx.session.send_line("  tune <n> / untune <n>    manage frequencies")
        await ctx.session.send_line("  comms <ship> <msg>       ship-to-ship (space only)")


# ── Who (enhanced) ────────────────────────────────────────────────────────────

class WhoCommand(BaseCommand):
    key = "who"
    aliases = ["players", "online"]
    help_text = "List online players with their current location and status."
    usage = "who"

    async def execute(self, ctx: CommandContext):
        sessions = [s for s in ctx.session_mgr.all if s.character]
        await ctx.session.send_line(ansi.header("=== Players Online ==="))
        if not sessions:
            await ctx.session.send_line("  No players online.")
            return
        for sess in sessions:
            char = sess.character
            room_id = char.get("room_id", 0)
            room_name = "Unknown"
            try:
                room_row = await ctx.db.get_room(room_id)
                if room_row:
                    room_name = room_row.get("name", f"Room #{room_id}")
            except Exception:
                room_name = f"Room #{room_id}"
            status = _get_player_status(sess, char["id"])
            await ctx.session.send_line(
                f"  {ansi.player_name(char['name']):<22}"
                f"  {ansi.dim(room_name):<28}"
                f"  {ansi.yellow('[' + status + ']')}"
            )
        await ctx.session.send_line(f"  {len(sessions)} player(s) online.")


def _get_player_status(sess, char_id: int) -> str:
    try:
        from parser.combat_commands import _active_combats
        for combat in _active_combats.values():
            if combat.get_combatant(char_id):
                return "In Combat"
    except (ImportError, Exception):
        pass
    return "Online"


# ── Registration ───────────────────────────────────────────────────────────────

def register_channel_commands(registry):
    registry.register(OocCommand())
    registry.register(ComlinkCommand())
    registry.register(FcommCommand())
    registry.register(FactionCommand())
    registry.register(TuneCommand())
    registry.register(UntuneCommand())
    registry.register(FreqsCommand())
    registry.register(CommFreqCommand())
    registry.register(ChannelsCommand())
    registry.register(WhoCommand())
    log.info(
        "[channels] Registered: ooc, comlink, fcomm, faction, "
        "tune, untune, freqs, commfreq, channels, who"
    )
