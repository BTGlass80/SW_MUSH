"""
engine/mail_utils.py — PG2.PL (May 22 2026)

System-mail helper. Lets engine-layer code (tick handlers, death
fulfillment, stipend interceptors) send mail to characters without
having to know about the parser's mail-composition flow.

Per the existing mail schema (mail / mail_recipients tables), a mail
message is two inserts: one row in `mail` for the message body and
sender, one row per recipient in `mail_recipients` linking the mail
to the recipient with read/deleted flags.

This helper is a thin wrapper. It does NOT do recipient validation
(the caller is responsible for passing a valid char_id) and it does
NOT surface in-game notifications (the parser layer's send-side
"new mail" alert is for player-to-player; system mail just sits in
the inbox).

**Substrate decision:** sender_id=0 is reserved for "system" mail,
which mirrors the credit-log convention where char_id=0 means the
NPC/system economy. Player-facing display can show "from System" or
"from BH Guild" based on the subject prefix or a dedicated column
(future work — for now, system mail is identifiable by sender_id=0).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


SYSTEM_SENDER_ID = 0


async def send_system_mail(
    db,
    *,
    recipient_id: int,
    subject: str,
    body: str,
    sender_id: int = SYSTEM_SENDER_ID,
) -> Optional[int]:
    """Send a piece of mail from the system (or a named sender) to
    a single recipient. Returns the mail_id, or None on failure.

    Args:
        db: Database instance (the one with .execute() / .commit()).
        recipient_id: Character id of the recipient.
        subject: Subject line. Will be stored verbatim.
        body: Body text. May contain newlines.
        sender_id: 0 (default) means "system mail". Otherwise the
            char_id of the apparent sender (for "from BH Guild via
            system" style notifications, the caller would still
            normally use 0 — the subject line carries the source
            attribution).

    Returns:
        The mail_id of the inserted message, or None if the insert
        failed.

    The function fails soft — a DB error logs a warning and returns
    None. Callers should treat send-mail as best-effort; the
    underlying mechanic (stipend pay, bounty fulfill) MUST proceed
    regardless of whether the courtesy mail succeeded.
    """
    try:
        # naive-UTC ISO (byte-identical to the long-stored format); the
        # deprecated datetime.utcnow() is gone (slated for removal in a
        # future Python — this box runs 3.14).
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        cursor = await db.execute(
            "INSERT INTO mail (sender_id, subject, body, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (int(sender_id), str(subject), str(body), now),
        )
        mail_id = cursor.lastrowid
        await db.execute(
            "INSERT INTO mail_recipients "
            "(mail_id, char_id, is_read, is_deleted) "
            "VALUES (?, ?, 0, 0)",
            (mail_id, int(recipient_id)),
        )
        await db.commit()
        return int(mail_id) if mail_id is not None else None
    except Exception:
        log.warning(
            "send_system_mail: failed (recipient=%s, subject=%r)",
            recipient_id, subject, exc_info=True,
        )
        return None
