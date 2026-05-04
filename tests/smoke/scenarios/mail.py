# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/mail.py — In-game mail scenarios (ML1–ML5).
Drop 4.

Mail was unshippable for the entire pre-Drop-4 history of the game:
parser/mail_commands.py (650 LoC, 9 subcommands) referenced `mail`
and `mail_recipients` tables that didn't exist in the schema. Every
@mail subcommand crashed with:

    sqlite3.OperationalError: no such table: mail

Drop 4 adds the schema (db/database.py SCHEMA_SQL + migration v20)
and these scenarios verify the round-trip works. ML4 caught a
secondary bug (sqlite3.Row.get() doesn't exist) which was also
fixed in the same drop.

Scope:
  ML1 — Empty inbox renders cleanly ("No mail.")
  ML2 — `@mail/quick <player>/<subj> = <body>` end-to-end:
        DB row created, recipient row created, in-game NEW MAIL
        notification fires for the recipient
  ML3 — Inbox after send shows the new message with NEW flag
  ML4 — `@mail/read <#>` displays sender + subject + body and
        flips the recipient's is_read to 1 (REGRESSION GUARD for
        the sqlite3.Row.get() fix)
  ML5 — `@mail/delete <#>` then `@mail/purge` removes the row
        AND cascades to the orphan mail row (ON DELETE CASCADE
        check)
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

async def _mail_count(h, char_id: int) -> int:
    """Count non-deleted mail in a character's inbox."""
    rows = await h.db.fetchall(
        "SELECT COUNT(*) AS c FROM mail_recipients "
        "WHERE char_id = ? AND is_deleted = 0",
        (char_id,),
    )
    return rows[0]["c"] if rows else 0


# ──────────────────────────────────────────────────────────────────────────
# ML1 — Empty inbox
# ──────────────────────────────────────────────────────────────────────────

async def ml1_empty_inbox_renders(h):
    """ML1 — `@mail` for a fresh character shows the empty-inbox
    message cleanly.

    REGRESSION GUARD for the schema fix. Pre-Drop-4 this command
    returned:

      An error occurred processing your command. (no such table: mail)

    Post-fix it shows "No mail." in a formatted header.
    """
    s = await h.login_as("ML1Empty", room_id=1)
    out = await h.cmd(s, "@mail")
    assert "traceback" not in out.lower(), (
        f"@mail raised: {out[:500]!r}"
    )
    # The schema-missing failure leaked "no such table" through
    # the exception handler. Explicit catch.
    assert "no such table" not in out.lower(), (
        f"Mail tables still missing — schema migration didn't apply. "
        f"Output: {out[:300]!r}"
    )
    out_lc = out.lower()
    assert "mail" in out_lc, (
        f"@mail output doesn't mention 'mail'. Output: {out[:400]!r}"
    )
    assert "no mail" in out_lc or "0 message" in out_lc, (
        f"@mail empty-inbox message not found. Output: {out[:400]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# ML2 — Quick send creates DB rows + notifies recipient
# ──────────────────────────────────────────────────────────────────────────

async def ml2_quick_send_creates_rows(h):
    """ML2 — `@mail/quick Recipient/Subject = body` creates a row
    in `mail` AND a row in `mail_recipients` AND fires the in-game
    NEW MAIL notification to the online recipient.

    This is the cross-table consistency check — both rows must
    exist for inbox lookup to work. The recipient-side notification
    flows through `session_mgr.find_by_character` and is observable
    in the recipient's session output (the harness keeps both
    sessions live).
    """
    sender = await h.login_as("ML2Sender", room_id=1)
    recipient = await h.login_as("ML2Recip", room_id=1)
    rid = recipient.character["id"]

    pre_count = await _mail_count(h, rid)
    assert pre_count == 0, (
        f"ML2Recip starts with {pre_count} mail; expected 0"
    )

    # Drain any pre-test buffered output on the recipient session
    # so the NEW MAIL notification check below isn't fooled by
    # earlier login lines.
    recipient.drain_text()

    out = await h.cmd(
        sender, "@mail/quick ML2Recip/Hello = Test message body."
    )
    assert "traceback" not in out.lower(), (
        f"@mail/quick raised: {out[:500]!r}"
    )
    assert "mail sent" in out.lower(), (
        f"@mail/quick didn't surface success message. "
        f"Output: {out[:300]!r}"
    )

    # mail row created
    mail_rows = await h.db.fetchall(
        "SELECT id, sender_id, subject, body FROM mail "
        "WHERE sender_id = ? ORDER BY id DESC LIMIT 1",
        (sender.character["id"],),
    )
    assert mail_rows, (
        f"@mail/quick didn't create a mail row for sender "
        f"{sender.character['id']}"
    )
    assert mail_rows[0]["subject"] == "Hello", (
        f"mail subject mismatch: got {mail_rows[0]['subject']!r}"
    )
    assert mail_rows[0]["body"] == "Test message body.", (
        f"mail body mismatch: got {mail_rows[0]['body']!r}"
    )

    # mail_recipients row created
    post_count = await _mail_count(h, rid)
    assert post_count == 1, (
        f"After @mail/quick, ML2Recip should have 1 mail; got {post_count}"
    )

    # In-game NEW MAIL notification fired on recipient session.
    # drain_text returns the text accumulated since the last drain
    # (which was just before sender's command, so the only new
    # output here should be the NEW MAIL push).
    recip_buf = recipient.drain_text()
    assert "NEW MAIL" in recip_buf, (
        f"NEW MAIL notification didn't reach the recipient session. "
        f"Recipient buffer (last 400 chars): {recip_buf[-400:]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# ML3 — Inbox after send shows NEW
# ──────────────────────────────────────────────────────────────────────────

async def ml3_inbox_after_send_shows_unread(h):
    """ML3 — After receiving a mail, `@mail` lists it with the
    NEW (unread) marker.

    The inbox query joins mail × mail_recipients × characters and
    sorts unread-first. ML3 verifies that join works AND the
    is_read flag flows into the formatter.
    """
    sender = await h.login_as("ML3Sender", room_id=1)
    recip = await h.login_as("ML3Recip", room_id=1)
    rid = recip.character["id"]

    await h.cmd(
        sender, "@mail/quick ML3Recip/Subject Three = Body three."
    )

    out = await h.cmd(recip, "@mail")
    assert "traceback" not in out.lower(), (
        f"@mail (post-receive) raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Expected fields: sender name, subject, NEW flag, count
    assert "ml3sender" in out_lc, (
        f"Inbox missing sender name 'ML3Sender'. Output: {out[:500]!r}"
    )
    assert "subject three" in out_lc, (
        f"Inbox missing subject 'Subject Three'. Output: {out[:500]!r}"
    )
    assert "new" in out_lc, (
        f"Inbox missing NEW (unread) marker. Output: {out[:500]!r}"
    )
    assert "1 unread" in out_lc or "1 message" in out_lc, (
        f"Inbox count line missing/wrong. Output: {out[:500]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# ML4 — Read flips is_read AND renders body
# ──────────────────────────────────────────────────────────────────────────

async def ml4_read_displays_body_and_marks_read(h):
    """ML4 — `@mail/read <#>` displays the body AND updates
    `mail_recipients.is_read = 1`.

    REGRESSION GUARD for the sqlite3.Row.get() fix shipped in
    Drop 4. Pre-fix, even after the schema landed, @mail/read
    crashed at line 226 of mail_commands.py with:

      AttributeError: 'sqlite3.Row' object has no attribute 'get'

    The body never displayed and the is_read flag never flipped.
    """
    sender = await h.login_as("ML4Sender", room_id=1)
    recip = await h.login_as("ML4Recip", room_id=1)
    rid = recip.character["id"]

    body_text = "First line of body.\nSecond line."
    await h.cmd(
        sender, f"@mail/quick ML4Recip/Read Test = {body_text}"
    )

    # Find the mail id we just created (ID is auto-increment but
    # not guaranteed to be 1 in a class-scoped harness with prior
    # mail traffic from earlier scenarios).
    rows = await h.db.fetchall(
        "SELECT mr.mail_id FROM mail_recipients mr "
        "JOIN mail m ON m.id = mr.mail_id "
        "WHERE mr.char_id = ? AND m.subject = 'Read Test' "
        "ORDER BY mr.id DESC LIMIT 1",
        (rid,),
    )
    assert rows, (
        f"ML4Recip didn't receive 'Read Test' mail for "
        f"char_id={rid}"
    )
    mail_id = rows[0]["mail_id"]

    # Pre-state: is_read = 0
    pre = await h.db.fetchall(
        "SELECT is_read FROM mail_recipients "
        "WHERE mail_id = ? AND char_id = ?",
        (mail_id, rid),
    )
    assert pre[0]["is_read"] == 0, (
        f"Pre-read state should be is_read=0; got {pre[0]['is_read']}"
    )

    out = await h.cmd(recip, f"@mail/read {mail_id}")
    assert "traceback" not in out.lower(), (
        f"@mail/read raised: {out[:500]!r}"
    )
    # Specific catch for the Row.get() bug.
    assert "no attribute 'get'" not in out.lower(), (
        f"sqlite3.Row.get() AttributeError leaked through. "
        f"Output: {out[:300]!r}"
    )
    # Body must render
    assert "First line of body" in out, (
        f"@mail/read didn't render body. Output: {out[:500]!r}"
    )
    assert "Second line" in out, (
        f"@mail/read didn't render second-line content. "
        f"Output: {out[:500]!r}"
    )

    # Post-state: is_read = 1
    post = await h.db.fetchall(
        "SELECT is_read FROM mail_recipients "
        "WHERE mail_id = ? AND char_id = ?",
        (mail_id, rid),
    )
    assert post[0]["is_read"] == 1, (
        f"Post-read state should be is_read=1; got {post[0]['is_read']}"
    )


# ──────────────────────────────────────────────────────────────────────────
# ML5 — Delete + purge cascades to orphan mail rows
# ──────────────────────────────────────────────────────────────────────────

async def ml5_delete_purge_cascades(h):
    """ML5 — `@mail/delete <#>` flips is_deleted=1; `@mail/purge`
    removes the recipient row AND the orphan mail row.

    Two-step lifecycle: soft delete, then hard purge. The orphan
    cleanup happens via the manual DELETE statement in _purge
    (defensive — the FK ON DELETE CASCADE makes it redundant but
    harmless). ML5 verifies both rows are gone.
    """
    sender = await h.login_as("ML5Sender", room_id=1)
    recip = await h.login_as("ML5Recip", room_id=1)
    rid = recip.character["id"]

    await h.cmd(
        sender, "@mail/quick ML5Recip/Delete Me = Body."
    )
    rows = await h.db.fetchall(
        "SELECT mr.mail_id FROM mail_recipients mr "
        "JOIN mail m ON m.id = mr.mail_id "
        "WHERE mr.char_id = ? AND m.subject = 'Delete Me' "
        "ORDER BY mr.id DESC LIMIT 1",
        (rid,),
    )
    assert rows, "ML5Recip didn't receive 'Delete Me' mail"
    mail_id = rows[0]["mail_id"]

    # Soft delete
    out = await h.cmd(recip, f"@mail/delete {mail_id}")
    assert "traceback" not in out.lower(), (
        f"@mail/delete raised: {out[:500]!r}"
    )
    after_delete = await h.db.fetchall(
        "SELECT is_deleted FROM mail_recipients "
        "WHERE mail_id = ? AND char_id = ?",
        (mail_id, rid),
    )
    assert after_delete and after_delete[0]["is_deleted"] == 1, (
        f"After @mail/delete, is_deleted should be 1; got "
        f"{after_delete!r}"
    )

    # Hard purge
    out2 = await h.cmd(recip, "@mail/purge")
    assert "traceback" not in out2.lower(), (
        f"@mail/purge raised: {out2[:500]!r}"
    )
    after_purge_recip = await h.db.fetchall(
        "SELECT id FROM mail_recipients "
        "WHERE mail_id = ? AND char_id = ?",
        (mail_id, rid),
    )
    assert not after_purge_recip, (
        f"After @mail/purge, mail_recipients row should be gone; "
        f"got {after_purge_recip!r}"
    )
    # Orphan mail row should also be gone — this mail had only one
    # recipient, who just purged it.
    after_purge_mail = await h.db.fetchall(
        "SELECT id FROM mail WHERE id = ?", (mail_id,)
    )
    assert not after_purge_mail, (
        f"After @mail/purge, orphan mail row {mail_id} should be "
        f"gone (no recipients reference it). got "
        f"{after_purge_mail!r}"
    )
