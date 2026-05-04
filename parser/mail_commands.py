# -*- coding: utf-8 -*-
"""
In-Game Mail System — @mail

A TinyMUX-compatible mail system for persistent player-to-player messaging.
Messages persist across sessions and are stored in the mail/mail_recipients tables.

Commands:
  @mail                           List your inbox (unread first)
  @mail <player> = <subject>      Start composing a message
  @mail/send                      Send the composed message (or - on blank line)
  @mail/read <#>                  Read message #N
  @mail/reply <#> [= <text>]      Reply to message #N
  @mail/forward <#> = <player>    Forward message #N
  @mail/delete <#|all>            Mark message(s) for deletion
  @mail/purge                     Permanently delete marked messages
  @mail/unread                    Show unread count
  @mail/sent                      Show sent messages
  @mail/quick <player>/<subj> = <body>   Quick one-line send

On login, players are notified of unread mail count.

DB Tables (migration v14):
  mail           — messages (sender, subject, body, sent_at)
  mail_recipients — per-recipient state (read, deleted flags)
"""
import logging
import time
import json
from datetime import datetime

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ── Compose state per session ─────────────────────────────────────────────────
# {session_id: {"to": [char_id, ...], "to_names": [...], "subject": str, "lines": [str]}}
_compose_state: dict[int, dict] = {}


# ═══════════════════════════════════════════════════════════════════════════════
#  Login notification hook
# ═══════════════════════════════════════════════════════════════════════════════

async def notify_unread_mail(db, session):
    """Called on login to notify of unread mail. Safe to call even if table doesn't exist."""
    if not session.character:
        return
    try:
        char_id = session.character["id"]
        rows = await db.fetchall(
            "SELECT COUNT(*) as cnt FROM mail_recipients "
            "WHERE char_id = ? AND is_read = 0 AND is_deleted = 0",
            (char_id,),
        )
        count = rows[0]["cnt"] if rows else 0
        if count > 0:
            await session.send_line(
                f"\n  \033[1;33m[MAIL]\033[0m You have {count} unread message{'s' if count != 1 else ''}. "
                f"Type '\033[1;37m@mail\033[0m' to read.\n"
            )
    except Exception:
        pass  # Table may not exist yet before migration


# ═══════════════════════════════════════════════════════════════════════════════
#  @mail command — main entry point
# ═══════════════════════════════════════════════════════════════════════════════

class MailCommand(BaseCommand):
    key = "@mail"
    aliases = ["mail", "+mail"]
    help_text = (
        "In-game mail system for persistent player-to-player messaging.\n"
        "\n"
        "USAGE:\n"
        "  @mail                             — list your inbox\n"
        "  @mail <player> = <subject>        — compose a message\n"
        "    (type your message, then '-' or @mail/send to send)\n"
        "  @mail/quick <player>/<subj> = <body> — send in one line\n"
        "  @mail/read <#>                    — read message #N\n"
        "  @mail/reply <#>                   — reply to message #N\n"
        "  @mail/forward <#> = <player>      — forward message #N\n"
        "  @mail/delete <#|all>              — mark for deletion\n"
        "  @mail/purge                       — permanently delete\n"
        "  @mail/sent                        — show sent messages\n"
        "  @mail/unread                      — show unread count"
    )
    usage = "@mail [player = subject]"
    valid_switches = ["read", "reply", "forward", "delete", "purge",
                      "send", "unread", "sent", "quick"]

    async def execute(self, ctx: CommandContext):
        sw = ctx.switches

        if "read" in sw:
            await self._read(ctx)
        elif "reply" in sw:
            await self._reply(ctx)
        elif "forward" in sw:
            await self._forward(ctx)
        elif "delete" in sw:
            await self._delete(ctx)
        elif "purge" in sw:
            await self._purge(ctx)
        elif "send" in sw:
            await self._send(ctx)
        elif "unread" in sw:
            await self._unread(ctx)
        elif "sent" in sw:
            await self._sent(ctx)
        elif "quick" in sw:
            await self._quick(ctx)
        elif ctx.args and "=" in ctx.args:
            await self._compose_start(ctx)
        else:
            await self._list_inbox(ctx)

    # ── List inbox ────────────────────────────────────────────────────────

    async def _list_inbox(self, ctx):
        char_id = ctx.session.character["id"]
        rows = await ctx.db.fetchall(
            "SELECT m.id, m.sender_id, m.subject, m.sent_at, "
            "       mr.is_read, mr.is_deleted, "
            "       c.name as sender_name "
            "FROM mail_recipients mr "
            "JOIN mail m ON m.id = mr.mail_id "
            "LEFT JOIN characters c ON c.id = m.sender_id "
            "WHERE mr.char_id = ? AND mr.is_deleted = 0 "
            "ORDER BY mr.is_read ASC, m.sent_at DESC "
            "LIMIT 30",
            (char_id,),
        )

        await ctx.session.send_line("")
        await ctx.session.send_line(ansi.header("═══ MAIL ═══════════════════════════════════════════════════"))
        await ctx.session.send_line(
            f"  {'#':>4s}  {'Status':6s}  {'From':<16s} {'Subject':<30s} {'Date':>10s}"
        )
        await ctx.session.send_line(
            f"  {'─'*4}  {'─'*6}  {'─'*16} {'─'*30} {'─'*10}"
        )

        if not rows:
            await ctx.session.send_line("  No mail.")
        else:
            for r in rows:
                num = r["id"]
                read_flag = "  " if r["is_read"] else "\033[1;33mNEW\033[0m"
                sender = (r["sender_name"] or "Unknown")[:16]
                subject = (r["subject"] or "(no subject)")[:30]
                try:
                    dt = datetime.fromisoformat(r["sent_at"])
                    date_str = dt.strftime("%m/%d %H:%M")
                except Exception:
                    date_str = str(r["sent_at"])[:10]
                await ctx.session.send_line(
                    f"  {num:>4d}  {read_flag:6s}  {sender:<16s} {subject:<30s} {date_str:>10s}"
                )

        unread = sum(1 for r in rows if not r["is_read"]) if rows else 0
        total = len(rows) if rows else 0
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  \033[2m{total} message(s), {unread} unread. "
            f"Type '@mail/read <#>' to read.\033[0m"
        )
        await ctx.session.send_line(
            ansi.header("═══════════════════════════════════════════════════════════════")
        )
        await ctx.session.send_line("")

    # ── Read message ──────────────────────────────────────────────────────

    async def _read(self, ctx):
        if not ctx.args or not ctx.args.strip().isdigit():
            await ctx.session.send_line("  Usage: @mail/read <#>")
            return
        mail_id = int(ctx.args.strip())
        char_id = ctx.session.character["id"]

        rows = await ctx.db.fetchall(
            "SELECT m.*, c.name as sender_name "
            "FROM mail m "
            "JOIN mail_recipients mr ON mr.mail_id = m.id "
            "LEFT JOIN characters c ON c.id = m.sender_id "
            "WHERE m.id = ? AND mr.char_id = ? AND mr.is_deleted = 0",
            (mail_id, char_id),
        )
        if not rows:
            await ctx.session.send_line(f"  Message #{mail_id} not found.")
            return
        msg = rows[0]

        # Mark as read
        await ctx.db.execute(
            "UPDATE mail_recipients SET is_read = 1 "
            "WHERE mail_id = ? AND char_id = ?",
            (mail_id, char_id),
        )
        await ctx.db.commit()

        # Display
        sender = msg["sender_name"] or f"#{msg['sender_id']}"
        try:
            dt = datetime.fromisoformat(msg["sent_at"])
            date_str = dt.strftime("%B %d, %Y at %H:%M")
        except Exception:
            date_str = str(msg["sent_at"])

        w = min(ctx.session.wrap_width, 78)
        bar = "─" * w

        await ctx.session.send_line("")
        await ctx.session.send_line(f"  \033[1;36m{bar}\033[0m")
        await ctx.session.send_line(f"  \033[1mMessage #{mail_id}\033[0m")
        await ctx.session.send_line(f"  \033[1mFrom:\033[0m    {sender}")
        await ctx.session.send_line(f"  \033[1mSubject:\033[0m {msg['subject']}")
        await ctx.session.send_line(f"  \033[1mDate:\033[0m    {date_str}")
        await ctx.session.send_line(f"  \033[1;36m{bar}\033[0m")
        await ctx.session.send_line("")

        # DROP-4 MAIL FIX (May 2026): sqlite3.Row supports __getitem__
        # via column name but does NOT support .get() like a dict.
        # The original .get("body", "") raised AttributeError on every
        # @mail/read call (after the schema fix made the row reachable
        # at all). The columns are NOT NULL in the schema so a raw
        # subscript is safe; the dict-style fallback was never doing
        # anything useful.
        body = msg["body"]
        for line in body.split("\n"):
            await ctx.session.send_line(f"  {line}")

        await ctx.session.send_line("")
        await ctx.session.send_line(f"  \033[1;36m{bar}\033[0m")
        await ctx.session.send_line(
            f"  \033[2m@mail/reply {mail_id}  |  @mail/forward {mail_id} = <player>  |  "
            f"@mail/delete {mail_id}\033[0m"
        )
        await ctx.session.send_line("")

    # ── Compose start ─────────────────────────────────────────────────────

    async def _compose_start(self, ctx):
        if "=" not in ctx.args:
            await ctx.session.send_line("  Usage: @mail <player> = <subject>")
            return

        to_part, subject = ctx.args.split("=", 1)
        to_names = [n.strip() for n in to_part.split() if n.strip()]
        subject = subject.strip()

        if not to_names:
            await ctx.session.send_line("  Who do you want to mail?")
            return
        if not subject:
            await ctx.session.send_line("  You must provide a subject.")
            return

        # Resolve all recipients
        resolved_ids = []
        resolved_names = []
        for name in to_names:
            char_row = await ctx.db.get_character_by_name(name)
            if not char_row:
                await ctx.session.send_line(f"  Player '{name}' not found.")
                return
            resolved_ids.append(char_row["id"])
            resolved_names.append(char_row["name"])

        sid = id(ctx.session)
        _compose_state[sid] = {
            "to": resolved_ids,
            "to_names": resolved_names,
            "subject": subject,
            "lines": [],
        }

        to_display = ", ".join(resolved_names)
        await ctx.session.send_line(
            f"\n  \033[1;33m[COMPOSING MAIL]\033[0m\n"
            f"  To:      {to_display}\n"
            f"  Subject: {subject}\n"
            f"\n"
            f"  Type your message. When finished, type '\033[1;37m-\033[0m' alone "
            f"on a line or '\033[1;37m@mail/send\033[0m'.\n"
            f"  Type '\033[1;37m~q\033[0m' to cancel.\n"
        )

        # Set input intercept to capture message body lines
        async def _compose_intercept(line: str):
            state = _compose_state.get(sid)
            if not state:
                ctx.session._input_intercept = None
                return
            if line.strip() == "-" or line.strip().lower() == "@mail/send":
                ctx.session._input_intercept = None
                await self._do_send(ctx, state)
                _compose_state.pop(sid, None)
                return
            if line.strip().lower() == "~q":
                ctx.session._input_intercept = None
                _compose_state.pop(sid, None)
                await ctx.session.send_line("  Mail cancelled.")
                return
            state["lines"].append(line)
            # Echo back with line number
            ln = len(state["lines"])
            await ctx.session.send_line(f"  \033[2m{ln:>3d}|\033[0m {line}")

        ctx.session._input_intercept = _compose_intercept

    # ── Send composed message ─────────────────────────────────────────────

    async def _send(self, ctx):
        sid = id(ctx.session)
        state = _compose_state.pop(sid, None)
        if not state:
            await ctx.session.send_line("  No message being composed. Use '@mail <player> = <subject>' first.")
            return
        ctx.session._input_intercept = None
        await self._do_send(ctx, state)

    async def _do_send(self, ctx, state: dict):
        char_id = ctx.session.character["id"]
        body = "\n".join(state["lines"])
        subject = state["subject"]
        to_ids = state["to"]
        to_names = state["to_names"]
        now = datetime.utcnow().isoformat()

        # Insert the mail message
        cursor = await ctx.db.execute(
            "INSERT INTO mail (sender_id, subject, body, sent_at) VALUES (?, ?, ?, ?)",
            (char_id, subject, body, now),
        )
        mail_id = cursor.lastrowid

        # Insert recipient entries
        for rid in to_ids:
            await ctx.db.execute(
                "INSERT INTO mail_recipients (mail_id, char_id, is_read, is_deleted) "
                "VALUES (?, ?, 0, 0)",
                (mail_id, rid),
            )
        await ctx.db.commit()

        to_display = ", ".join(to_names)
        line_count = len(state["lines"])
        await ctx.session.send_line(
            f"\n  \033[1;32m[MAIL SENT]\033[0m To: {to_display}  "
            f"Subject: {subject}  ({line_count} line{'s' if line_count != 1 else ''})\n"
        )

        # Notify online recipients
        sender_name = ctx.session.character["name"]
        for rid in to_ids:
            target_sess = ctx.session_mgr.find_by_character(rid)
            if target_sess:
                await target_sess.send_line(
                    f"\n  \033[1;33m[NEW MAIL]\033[0m From {sender_name}: {subject}\n"
                    f"  Type '\033[1;37m@mail/read {mail_id}\033[0m' to read.\n"
                )

    # ── Quick send (one line) ─────────────────────────────────────────────

    async def _quick(self, ctx):
        # @mail/quick Player/Subject = Body text here
        args = (ctx.args or "").strip()
        if "/" not in args or "=" not in args:
            await ctx.session.send_line(
                "  Usage: @mail/quick <player>/<subject> = <body>"
            )
            return
        slash_idx = args.index("/")
        eq_idx = args.index("=", slash_idx)
        to_name = args[:slash_idx].strip()
        subject = args[slash_idx + 1:eq_idx].strip()
        body = args[eq_idx + 1:].strip()

        if not to_name or not subject or not body:
            await ctx.session.send_line(
                "  Usage: @mail/quick <player>/<subject> = <body>"
            )
            return

        char_row = await ctx.db.get_character_by_name(to_name)
        if not char_row:
            await ctx.session.send_line(f"  Player '{to_name}' not found.")
            return

        state = {
            "to": [char_row["id"]],
            "to_names": [char_row["name"]],
            "subject": subject,
            "lines": [body],
        }
        await self._do_send(ctx, state)

    # ── Reply ─────────────────────────────────────────────────────────────

    async def _reply(self, ctx):
        args = (ctx.args or "").strip()
        # @mail/reply <#> or @mail/reply <#> = <quick body>
        if "=" in args:
            num_part, body = args.split("=", 1)
            num_str = num_part.strip()
            body = body.strip()
        else:
            num_str = args
            body = ""

        if not num_str.isdigit():
            await ctx.session.send_line("  Usage: @mail/reply <#> [= <quick reply>]")
            return

        mail_id = int(num_str)
        char_id = ctx.session.character["id"]

        rows = await ctx.db.fetchall(
            "SELECT m.sender_id, m.subject, c.name as sender_name "
            "FROM mail m "
            "JOIN mail_recipients mr ON mr.mail_id = m.id "
            "LEFT JOIN characters c ON c.id = m.sender_id "
            "WHERE m.id = ? AND mr.char_id = ?",
            (mail_id, char_id),
        )
        if not rows:
            await ctx.session.send_line(f"  Message #{mail_id} not found.")
            return
        orig = rows[0]

        re_subject = orig["subject"]
        if not re_subject.lower().startswith("re:"):
            re_subject = f"Re: {re_subject}"

        if body:
            # Quick reply
            state = {
                "to": [orig["sender_id"]],
                "to_names": [orig["sender_name"] or f"#{orig['sender_id']}"],
                "subject": re_subject,
                "lines": [body],
            }
            await self._do_send(ctx, state)
        else:
            # Open compose editor
            sid = id(ctx.session)
            _compose_state[sid] = {
                "to": [orig["sender_id"]],
                "to_names": [orig["sender_name"] or f"#{orig['sender_id']}"],
                "subject": re_subject,
                "lines": [],
            }
            await ctx.session.send_line(
                f"\n  \033[1;33m[REPLYING]\033[0m To: {orig['sender_name']}  "
                f"Subject: {re_subject}\n"
                f"  Type your reply. '-' or '@mail/send' to send, '~q' to cancel.\n"
            )

            async def _reply_intercept(line: str):
                state = _compose_state.get(sid)
                if not state:
                    ctx.session._input_intercept = None
                    return
                if line.strip() == "-" or line.strip().lower() == "@mail/send":
                    ctx.session._input_intercept = None
                    await self._do_send(ctx, state)
                    _compose_state.pop(sid, None)
                    return
                if line.strip().lower() == "~q":
                    ctx.session._input_intercept = None
                    _compose_state.pop(sid, None)
                    await ctx.session.send_line("  Reply cancelled.")
                    return
                state["lines"].append(line)
                await ctx.session.send_line(f"  \033[2m{len(state['lines']):>3d}|\033[0m {line}")

            ctx.session._input_intercept = _reply_intercept

    # ── Forward ───────────────────────────────────────────────────────────

    async def _forward(self, ctx):
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line("  Usage: @mail/forward <#> = <player>")
            return
        num_str, to_name = ctx.args.split("=", 1)
        num_str = num_str.strip()
        to_name = to_name.strip()

        if not num_str.isdigit():
            await ctx.session.send_line("  Usage: @mail/forward <#> = <player>")
            return
        mail_id = int(num_str)
        char_id = ctx.session.character["id"]

        # Get original message
        rows = await ctx.db.fetchall(
            "SELECT m.*, c.name as sender_name "
            "FROM mail m "
            "JOIN mail_recipients mr ON mr.mail_id = m.id "
            "LEFT JOIN characters c ON c.id = m.sender_id "
            "WHERE m.id = ? AND mr.char_id = ?",
            (mail_id, char_id),
        )
        if not rows:
            await ctx.session.send_line(f"  Message #{mail_id} not found.")
            return
        orig = rows[0]

        # Resolve target
        target = await ctx.db.get_character_by_name(to_name)
        if not target:
            await ctx.session.send_line(f"  Player '{to_name}' not found.")
            return

        fwd_subject = f"Fwd: {orig['subject']}"
        fwd_body = (
            f"--- Forwarded message from {orig['sender_name'] or 'Unknown'} ---\n"
            f"{orig['body']}\n"
            f"--- End forwarded message ---"
        )

        state = {
            "to": [target["id"]],
            "to_names": [target["name"]],
            "subject": fwd_subject,
            "lines": fwd_body.split("\n"),
        }
        await self._do_send(ctx, state)

    # ── Delete ────────────────────────────────────────────────────────────

    async def _delete(self, ctx):
        char_id = ctx.session.character["id"]
        arg = (ctx.args or "").strip().lower()

        if arg == "all":
            cursor = await ctx.db.execute(
                "UPDATE mail_recipients SET is_deleted = 1 "
                "WHERE char_id = ? AND is_deleted = 0",
                (char_id,),
            )
            await ctx.db.commit()
            await ctx.session.send_line(
                ansi.success(f"  {cursor.rowcount} message(s) marked for deletion. "
                             f"Type '@mail/purge' to permanently remove.")
            )
            return

        if not arg.isdigit():
            await ctx.session.send_line("  Usage: @mail/delete <#|all>")
            return

        mail_id = int(arg)
        cursor = await ctx.db.execute(
            "UPDATE mail_recipients SET is_deleted = 1 "
            "WHERE mail_id = ? AND char_id = ? AND is_deleted = 0",
            (mail_id, char_id),
        )
        await ctx.db.commit()

        if cursor.rowcount:
            await ctx.session.send_line(
                ansi.success(f"  Message #{mail_id} marked for deletion. '@mail/purge' to remove permanently.")
            )
        else:
            await ctx.session.send_line(f"  Message #{mail_id} not found or already deleted.")

    # ── Purge ─────────────────────────────────────────────────────────────

    async def _purge(self, ctx):
        char_id = ctx.session.character["id"]
        cursor = await ctx.db.execute(
            "DELETE FROM mail_recipients WHERE char_id = ? AND is_deleted = 1",
            (char_id,),
        )
        await ctx.db.commit()
        await ctx.session.send_line(
            ansi.success(f"  {cursor.rowcount} message(s) permanently deleted.")
        )

        # Clean orphaned mail records (no recipients left)
        await ctx.db.execute(
            "DELETE FROM mail WHERE id NOT IN (SELECT DISTINCT mail_id FROM mail_recipients)"
        )
        await ctx.db.commit()

    # ── Unread count ──────────────────────────────────────────────────────

    async def _unread(self, ctx):
        char_id = ctx.session.character["id"]
        rows = await ctx.db.fetchall(
            "SELECT COUNT(*) as cnt FROM mail_recipients "
            "WHERE char_id = ? AND is_read = 0 AND is_deleted = 0",
            (char_id,),
        )
        count = rows[0]["cnt"] if rows else 0
        await ctx.session.send_line(
            f"  You have {count} unread message{'s' if count != 1 else ''}."
        )

    # ── Sent messages ─────────────────────────────────────────────────────

    async def _sent(self, ctx):
        char_id = ctx.session.character["id"]
        rows = await ctx.db.fetchall(
            "SELECT m.id, m.subject, m.sent_at, "
            "  GROUP_CONCAT(c.name, ', ') as recipients "
            "FROM mail m "
            "JOIN mail_recipients mr ON mr.mail_id = m.id "
            "LEFT JOIN characters c ON c.id = mr.char_id "
            "WHERE m.sender_id = ? "
            "GROUP BY m.id "
            "ORDER BY m.sent_at DESC LIMIT 20",
            (char_id,),
        )

        await ctx.session.send_line("")
        await ctx.session.send_line(ansi.header("═══ SENT MAIL ══════════════════════════════════════════════"))
        if not rows:
            await ctx.session.send_line("  No sent messages.")
        else:
            await ctx.session.send_line(
                f"  {'#':>4s}  {'To':<20s} {'Subject':<30s} {'Date':>10s}"
            )
            await ctx.session.send_line(
                f"  {'─'*4}  {'─'*20} {'─'*30} {'─'*10}"
            )
            for r in rows:
                recip = (r["recipients"] or "?")[:20]
                subject = (r["subject"] or "(no subject)")[:30]
                try:
                    dt = datetime.fromisoformat(r["sent_at"])
                    date_str = dt.strftime("%m/%d %H:%M")
                except Exception:
                    date_str = str(r["sent_at"])[:10]
                await ctx.session.send_line(
                    f"  {r['id']:>4d}  {recip:<20s} {subject:<30s} {date_str:>10s}"
                )
        await ctx.session.send_line(
            ansi.header("═══════════════════════════════════════════════════════════════")
        )
        await ctx.session.send_line("")


# ═══════════════════════════════════════════════════════════════════════════════
#  Registration
# ═══════════════════════════════════════════════════════════════════════════════

def register_mail_commands(registry):
    """Register mail commands."""
    registry.register(MailCommand())
