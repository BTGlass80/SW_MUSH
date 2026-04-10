# -*- coding: utf-8 -*-
"""
parser/party_commands.py  --  Party / Group Commands
SW_MUSH  |  Player Engagement P3

Implements 7 player-facing party commands:
  party invite <player>   -- send an invite
  party accept            -- accept a pending invite
  party leave             -- leave your current party
  party list              -- show party members
  party chat <message>    -- private party channel (alias: pc)
  party kick <player>     -- leader-only: remove a member
  party decline           -- decline a pending invite

Register via: register_party_commands(registry)
Called from game_server.py alongside the other register_*() calls.
"""

import logging

from server import ansi
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mgr():
    from engine.party import get_party_manager
    return get_party_manager()


def _find_online(ctx: CommandContext, name: str):
    """
    Return (session, char_id, char_name) for an online player by name,
    or (None, None, None) if not found.  Case-insensitive partial match.
    """
    name_lower = name.lower()
    for sess in ctx.session_mgr.all:
        char = sess.character
        if char and char["name"].lower().startswith(name_lower):
            return sess, char["id"], char["name"]
    return None, None, None


# ── Commands ───────────────────────────────────────────────────────────────────

class PartyInviteCommand(BaseCommand):
    key = "party"
    aliases = ["p"]
    help_text = (
        "Party system commands.\n"
        "  party invite <player>  -- invite a player\n"
        "  party accept           -- accept a pending invite\n"
        "  party leave            -- leave your party\n"
        "  party list             -- show party members\n"
        "  party chat <msg>       -- party-only chat (alias: pc)\n"
        "  party kick <player>    -- kick a member (leader only)\n"
        "  party decline          -- decline a pending invite"
    )
    usage = "party <subcommand> [args]"

    async def execute(self, ctx: CommandContext):
        args = (ctx.args or "").strip()
        sub, _, rest = args.partition(" ")
        sub = sub.lower()
        rest = rest.strip()

        mgr = _mgr()
        await mgr.ensure_loaded(ctx.db)

        if sub == "invite":
            await _party_invite(ctx, mgr, rest)
        elif sub == "accept":
            await _party_accept(ctx, mgr)
        elif sub == "leave":
            await _party_leave(ctx, mgr)
        elif sub in ("list", "members", ""):
            await _party_list(ctx, mgr)
        elif sub in ("chat", "c"):
            await _party_chat(ctx, mgr, rest)
        elif sub == "kick":
            await _party_kick(ctx, mgr, rest)
        elif sub == "decline":
            await _party_decline(ctx, mgr)
        else:
            await ctx.session.send_line(
                ansi.error(f"Unknown party subcommand '{sub}'. Type 'help party'.")
            )


async def _party_invite(ctx: CommandContext, mgr, name: str):
    if not name:
        await ctx.session.send_line("  Usage: party invite <player name>")
        return

    char = ctx.session.character
    inviter_id = char["id"]
    inviter_name = char["name"]

    # Can't invite yourself
    target_sess, target_id, target_name = _find_online(ctx, name)
    if target_id == inviter_id:
        await ctx.session.send_line(ansi.error("You can't invite yourself."))
        return

    if target_sess is None:
        await ctx.session.send_line(ansi.error(f"No online player named '{name}'."))
        return

    err = mgr.invite(inviter_id, target_id)
    if err:
        await ctx.session.send_line(ansi.error(err))
        return

    await ctx.session.send_line(
        ansi.system_msg(f"You invite {ansi.player_name(target_name)} to your party.")
    )
    await target_sess.send_line(
        ansi.system_msg(
            f"{ansi.player_name(inviter_name)} invites you to join their party.  "
            f"Type '{ansi.highlight('party accept')}' to join or "
            f"'{ansi.highlight('party decline')}' to refuse."
        )
    )


async def _party_accept(ctx: CommandContext, mgr):
    char = ctx.session.character
    invitee_id = char["id"]

    inviter_id = mgr.has_pending_invite(invitee_id)
    if inviter_id is None:
        await ctx.session.send_line(ansi.error("You don't have a pending party invite."))
        return

    # Resolve inviter name (may be offline now)
    inviter_sess = ctx.session_mgr.find_by_character(inviter_id)
    inviter_name = (
        inviter_sess.character["name"] if inviter_sess and inviter_sess.character
        else f"Player#{inviter_id}"
    )

    err, party = await mgr.accept(invitee_id, ctx.db)
    if err:
        await ctx.session.send_line(ansi.error(err))
        return

    await ctx.session.send_line(
        ansi.system_msg(f"You join {ansi.player_name(inviter_name)}'s party.")
    )

    # Notify all party members
    for member_id in party.members:
        if member_id == invitee_id:
            continue
        msess = ctx.session_mgr.find_by_character(member_id)
        if msess:
            await msess.send_line(
                ansi.system_msg(f"{ansi.player_name(char['name'])} has joined the party.")
            )


async def _party_leave(ctx: CommandContext, mgr):
    char = ctx.session.character
    char_id = char["id"]
    char_name = char["name"]

    party = mgr.get_party(char_id)
    if not party:
        await ctx.session.send_line(ansi.error("You're not in a party."))
        return

    # Snapshot members before leaving
    remaining = [mid for mid in party.members if mid != char_id]

    err, new_leader_id_str = await mgr.leave(char_id, ctx.db)
    if err:
        await ctx.session.send_line(ansi.error(err))
        return

    await ctx.session.send_line(ansi.system_msg("You leave the party."))

    # Notify remaining members
    for member_id in remaining:
        msess = ctx.session_mgr.find_by_character(member_id)
        if msess:
            await msess.send_line(
                ansi.system_msg(f"{ansi.player_name(char_name)} has left the party.")
            )

    # Announce new leader if leadership transferred
    if new_leader_id_str:
        try:
            new_leader_id = int(new_leader_id_str)
        except ValueError:
            new_leader_id = None

        if new_leader_id:
            nl_sess = ctx.session_mgr.find_by_character(new_leader_id)
            nl_name = (
                nl_sess.character["name"]
                if nl_sess and nl_sess.character
                else f"Player#{new_leader_id}"
            )
            for member_id in remaining:
                msess = ctx.session_mgr.find_by_character(member_id)
                if msess:
                    await msess.send_line(
                        ansi.system_msg(
                            f"{ansi.player_name(nl_name)} is now the party leader."
                        )
                    )


async def _party_list(ctx: CommandContext, mgr):
    char_id = ctx.session.character["id"]

    party = mgr.get_party(char_id)
    if not party:
        await ctx.session.send_line(
            ansi.system_msg("You are not in a party.  Use 'party invite <player>' to start one.")
        )
        return

    await ctx.session.send_line(ansi.header("=== Party Members ==="))
    for member_id in party.members:
        msess = ctx.session_mgr.find_by_character(member_id)
        if msess and msess.character:
            name = msess.character["name"]
            status = "(leader)" if party.is_leader(member_id) else ""
            online_tag = ansi.success("online")
        else:
            name = f"Player#{member_id}"
            status = "(leader)" if party.is_leader(member_id) else ""
            online_tag = ansi.error("offline")

        leader_tag = f"  {ansi.highlight('[Leader]')} " if party.is_leader(member_id) else "    "
        await ctx.session.send_line(
            f"{leader_tag}{ansi.player_name(name)}  [{online_tag}]"
        )
    await ctx.session.send_line(
        f"  {party.size}/{6} members"
    )


async def _party_chat(ctx: CommandContext, mgr, message: str):
    if not message:
        await ctx.session.send_line("  Usage: party chat <message>  (alias: pc <message>)")
        return

    char = ctx.session.character
    char_id = char["id"]
    char_name = char["name"]

    party = mgr.get_party(char_id)
    if not party:
        await ctx.session.send_line(ansi.error("You're not in a party."))
        return

    formatted = f"[Party] {ansi.player_name(char_name)}: {message}"

    for member_id in party.members:
        msess = ctx.session_mgr.find_by_character(member_id)
        if msess:
            await msess.send_line(ansi.system_msg(formatted))


async def _party_kick(ctx: CommandContext, mgr, name: str):
    if not name:
        await ctx.session.send_line("  Usage: party kick <player name>")
        return

    char = ctx.session.character
    leader_id = char["id"]

    target_sess, target_id, target_name = _find_online(ctx, name)
    if target_id is None:
        # Player might be offline; check party by name prefix
        party = mgr.get_party(leader_id)
        if party:
            for member_id in party.members:
                msess = ctx.session_mgr.find_by_character(member_id)
                if msess and msess.character:
                    mname = msess.character["name"]
                    if mname.lower().startswith(name.lower()):
                        target_id = member_id
                        target_name = mname
                        target_sess = msess
                        break
        if target_id is None:
            await ctx.session.send_line(ansi.error(f"No player named '{name}' found in party."))
            return

    err = await mgr.kick(leader_id, target_id, ctx.db)
    if err:
        await ctx.session.send_line(ansi.error(err))
        return

    await ctx.session.send_line(
        ansi.system_msg(f"You kick {ansi.player_name(target_name)} from the party.")
    )
    if target_sess:
        await target_sess.send_line(
            ansi.system_msg(f"You have been kicked from the party by {ansi.player_name(char['name'])}.")
        )

    # Notify remaining members
    party = mgr.get_party(leader_id)
    if party:
        for member_id in party.members:
            msess = ctx.session_mgr.find_by_character(member_id)
            if msess and member_id != leader_id:
                await msess.send_line(
                    ansi.system_msg(
                        f"{ansi.player_name(target_name)} was kicked from the party."
                    )
                )


async def _party_decline(ctx: CommandContext, mgr):
    char_id = ctx.session.character["id"]
    inviter_id = mgr.has_pending_invite(char_id)

    err = mgr.decline(char_id)
    if err:
        await ctx.session.send_line(ansi.error(err))
        return

    await ctx.session.send_line(ansi.system_msg("You decline the party invite."))

    # Notify inviter if online
    if inviter_id:
        isess = ctx.session_mgr.find_by_character(inviter_id)
        if isess:
            await isess.send_line(
                ansi.system_msg(
                    f"{ansi.player_name(ctx.session.character['name'])} declined your party invite."
                )
            )


class PartyChatShortcut(BaseCommand):
    """Alias: pc <message> -> party chat <message>"""
    key = "pc"
    aliases = []
    help_text = "Party chat shortcut.  Equivalent to: party chat <message>"
    usage = "pc <message>"

    async def execute(self, ctx: CommandContext):
        mgr = _mgr()
        await mgr.ensure_loaded(ctx.db)
        await _party_chat(ctx, mgr, ctx.args or "")


# ── Registration ───────────────────────────────────────────────────────────────

def register_party_commands(registry):
    registry.register(PartyInviteCommand())
    registry.register(PartyChatShortcut())
    log.info("[party] Party commands registered (party, pc).")
