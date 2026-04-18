# -*- coding: utf-8 -*-
"""
parser/char_commands.py — Multi-Character Management Commands

Allows players to manage their alternate characters from within the game.

Commands:
  +char/list              — List all characters on your account
  +char/switch            — Return to character selection screen
  +char/delete <name>     — Soft-delete a character (requires confirmation)

Design notes:
  - +char/switch sets session.state = CHAR_SWITCH and exits the game loop.
    handle_new_session loops back to _character_select.
  - +char/delete uses is_active=0 (soft delete) so character data is preserved.
    Blocked if the account has only one character.
  - All commands require the session to have an authenticated account.
"""

import logging

from parser.commands import BaseCommand, CommandContext
from server import ansi
from server.session import SessionState

log = logging.getLogger(__name__)

# ── Confirmation state: {session_id: char_name_pending_delete} ──
_pending_deletes: dict[int, str] = {}


class CharCommand(BaseCommand):
    key = "+char"
    aliases = ["+character", "charswitch"]
    help_text = (
        "Manage your alternate characters.\n"
        "\n"
        "USAGE:\n"
        "  +char/list           — List all characters on your account\n"
        "  +char/switch         — Return to character selection screen\n"
        "  +char/delete <name>  — Delete a character (confirmation required)\n"
        "\n"
        "Your account can have up to 3 characters. Characters from different\n"
        "factions are permitted, but two alts may not share the same faction.\n"
        "Characters cannot be used to trade with each other (anti-exploit).\n"
        "\n"
        "EXAMPLES:\n"
        "  +char/list\n"
        "  +char/switch\n"
        "  +char/delete OldChar"
    )
    usage = "+char/list | +char/switch | +char/delete <name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.session.account:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        raw = ctx.args or ""
        # Parse +char/subcommand — the command key is "+char" and
        # ctx.args may be "/list", "/switch", "/delete Name", or empty.
        # The command parser strips the key, so args starts with /subcommand.
        if raw.startswith("/"):
            slash_pos = raw.find(" ")
            if slash_pos == -1:
                sub = raw[1:].lower()
                rest = ""
            else:
                sub = raw[1:slash_pos].lower()
                rest = raw[slash_pos + 1:].strip()
        else:
            # Bare "+char" with no subcommand — default to list
            sub = "list"
            rest = raw.strip()

        if sub == "list":
            await self._list(ctx)
        elif sub == "switch":
            await self._switch(ctx)
        elif sub in ("delete", "retire"):
            await self._delete(ctx, rest)
        elif sub == "confirm":
            await self._confirm_delete(ctx)
        else:
            await ctx.session.send_line(
                "  Usage: +char/list | +char/switch | +char/delete <name>"
            )

    # ── +char/list ────────────────────────────────────────────────────────────

    async def _list(self, ctx: CommandContext):
        chars = await ctx.db.get_characters(ctx.session.account["id"])
        current_id = ctx.session.character["id"] if ctx.session.character else None

        await ctx.session.send_line("")
        await ctx.session.send_line(
            ansi.header("══════════════════ YOUR CHARACTERS ══════════════════")
        )

        for c in chars:
            marker = " \033[1;32m◀ ACTIVE\033[0m" if c["id"] == current_id else ""
            faction = c.get("faction_id", "independent") or "independent"
            species = c.get("species", "Human") or "Human"
            template = c.get("template", "") or ""

            # Credit total
            credits = c.get("credits", 0)
            cp = c.get("character_points", 0)

            # Last seen — room name if available
            room_id = c.get("room_id")
            location = "Unknown"
            if room_id:
                try:
                    room = await ctx.db.get_room(room_id)
                    if room:
                        location = room.get("name", "Unknown")
                except Exception:
                    log.debug("[char_cmd] room lookup failed for %d", room_id, exc_info=True)

            await ctx.session.send_line(
                f"  \033[1;37m{c['name']}\033[0m{marker}"
            )
            await ctx.session.send_line(
                f"    {species} {template}  ·  "
                f"Faction: \033[0;36m{faction.title()}\033[0m  ·  "
                f"{credits:,} cr  ·  {cp} CP"
            )
            await ctx.session.send_line(
                f"    Location: \033[2m{location}\033[0m"
            )
            await ctx.session.send_line("")

        max_chars = 3
        await ctx.session.send_line(
            f"  {len(chars)}/{max_chars} character slots used."
        )
        await ctx.session.send_line(
            ansi.header("═════════════════════════════════════════════════════")
        )
        await ctx.session.send_line("")

    # ── +char/switch ─────────────────────────────────────────────────────────

    async def _switch(self, ctx: CommandContext):
        chars = await ctx.db.get_characters(ctx.session.account["id"])
        if len(chars) <= 1:
            await ctx.session.send_line(
                ansi.error("You only have one character. Create a new one at login.")
            )
            return

        char = ctx.session.character
        if char:
            # Save position before switching
            try:
                await ctx.db.save_character(
                    char["id"],
                    room_id=char.get("room_id"),
                )
            except Exception:
                log.warning("[char_cmd] save before switch failed", exc_info=True)
            await ctx.session.send_line(
                f"  \033[2mSaving {char['name']}...\033[0m"
            )

        await ctx.session.send_line(
            ansi.system_msg("Returning to character selection...")
        )

        # Signal the game loop to exit and re-run character select
        ctx.session.state = SessionState.CHAR_SWITCH

    # ── +char/delete ─────────────────────────────────────────────────────────

    async def _delete(self, ctx: CommandContext, name: str):
        if not name:
            await ctx.session.send_line(
                "  Usage: +char/delete <character name>"
            )
            return

        chars = await ctx.db.get_characters(ctx.session.account["id"])
        if len(chars) <= 1:
            await ctx.session.send_line(
                ansi.error(
                    "You cannot delete your only character. "
                    "Create a new one first."
                )
            )
            return

        # Find target by name (case-insensitive)
        target = None
        for c in chars:
            if c["name"].lower() == name.lower():
                target = c
                break

        if not target:
            await ctx.session.send_line(
                ansi.error(f"No character named '{name}' on your account.")
            )
            return

        # Cannot delete the currently active character
        if (ctx.session.character
                and target["id"] == ctx.session.character["id"]):
            await ctx.session.send_line(
                ansi.error(
                    "You cannot delete your currently active character. "
                    "Use +char/switch first."
                )
            )
            return

        # Set pending confirmation
        _pending_deletes[ctx.session.id] = target["name"]

        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  \033[1;31m[WARNING]\033[0m You are about to permanently delete "
            f"\033[1;37m{target['name']}\033[0m."
        )
        await ctx.session.send_line(
            "  This action cannot be undone. All progress will be lost."
        )
        await ctx.session.send_line(
            "  Type \033[1;37m+char/confirm\033[0m to proceed, "
            "or anything else to cancel."
        )
        await ctx.session.send_line("")

    async def _confirm_delete(self, ctx: CommandContext):
        session_id = ctx.session.id
        char_name = _pending_deletes.pop(session_id, None)
        if not char_name:
            await ctx.session.send_line(
                "  No pending deletion. Use +char/delete <name> first."
            )
            return

        chars = await ctx.db.get_characters(ctx.session.account["id"])
        target = None
        for c in chars:
            if c["name"].lower() == char_name.lower():
                target = c
                break

        if not target:
            await ctx.session.send_line(
                ansi.error(f"Character '{char_name}' not found.")
            )
            return

        # Soft-delete
        try:
            await ctx.db.save_character(target["id"], is_active=0)
            await ctx.session.send_line(
                ansi.success(f"Character '{char_name}' has been deleted.")
            )
            log.info(
                "[char_cmd] Account %d soft-deleted character %d (%s)",
                ctx.session.account["id"], target["id"], char_name,
            )
        except Exception:
            log.warning("[char_cmd] delete failed", exc_info=True)
            await ctx.session.send_line(
                ansi.error("Deletion failed. Please try again.")
            )


# ── Registration ─────────────────────────────────────────────────────────────

def register_char_commands(registry):
    """Register multi-character management commands."""
    registry.register(CharCommand())
