# -*- coding: utf-8 -*-
"""
tests/test_newpassword_bcrypt.py — regression for the @newpassword
admin password-reset defect (external audit DEV-1 / P0-1).

Before the fix, ``NewPasswordCommand`` hashed the new password with raw
SHA-256 and wrote the 64-char hex digest into ``accounts.password_hash``,
while ``Database.authenticate`` verifies with ``bcrypt.checkpw``.
``bcrypt.checkpw`` RAISES ``ValueError("Invalid salt")`` on a non-bcrypt
hash, so every account an admin reset became permanently un-loginable
(Telnet: the exception killed the login coroutine; web portal: HTTP 500).

This pins:
  1. ``@newpassword`` -> the target authenticates with the NEW password.
  2. The OLD password no longer works after a reset.
  3. The stored hash is a bcrypt hash, not a raw SHA-256 hex digest.
  4. The reset honours the 6-char minimum (parity with account creation).
  5. ``authenticate`` fails CLOSED (returns ``None``) on a legacy/garbage
     hash instead of raising — defends accounts already bricked by the
     old bug.

Uses the in-process ``harness`` fixture (re-exported via
``tests/conftest.py``), driving ``@newpassword`` through the real command
dispatch path. The harness seeds every account as ``test_<name>`` with
password ``smoketestpass`` (see ``tests/harness.py::login_as``).
"""
from __future__ import annotations

import hashlib


class TestNewPasswordBcrypt:
    """Admin @newpassword reset must use the same bcrypt path as login."""

    async def test_reset_then_authenticate_roundtrip(self, harness) -> None:
        h = harness
        admin = await h.login_as("Resetwarden", is_admin=True)
        await h.login_as("Resetvictim")

        # Sanity: the seeded password works before the reset.
        assert await h.db.authenticate(
            "test_resetvictim", "smoketestpass"
        ) is not None

        # Admin resets the victim's password via the real command path.
        await h.cmd(admin, "@newpassword Resetvictim = brandnew-pw-99")

        # The NEW password authenticates...
        assert await h.db.authenticate(
            "test_resetvictim", "brandnew-pw-99"
        ) is not None
        # ...and the OLD password no longer does.
        assert await h.db.authenticate(
            "test_resetvictim", "smoketestpass"
        ) is None

        # Stored hash is bcrypt, not a raw SHA-256 hex digest.
        rows = await h.db.fetchall(
            "SELECT password_hash FROM accounts WHERE username = ?",
            ("test_resetvictim",),
        )
        ph = rows[0]["password_hash"]
        assert ph.startswith(("$2a$", "$2b$", "$2y$")), f"not bcrypt: {ph!r}"
        is_sha256_hex = len(ph) == 64 and all(
            c in "0123456789abcdef" for c in ph.lower()
        )
        assert not is_sha256_hex, "stored hash still looks like a SHA-256 hex"

    async def test_reset_enforces_six_char_minimum(self, harness) -> None:
        h = harness
        admin = await h.login_as("Lenwarden", is_admin=True)
        await h.login_as("Lenvictim")

        # 5 chars: allowed by the old <4 floor, refused by the new <6 floor.
        await h.cmd(admin, "@newpassword Lenvictim = abcde")

        # The reset was refused: seeded password still works, short one fails.
        assert await h.db.authenticate(
            "test_lenvictim", "smoketestpass"
        ) is not None
        assert await h.db.authenticate("test_lenvictim", "abcde") is None

    async def test_authenticate_fails_closed_on_legacy_sha256(
        self, harness
    ) -> None:
        """A pre-fix account (SHA-256 hex in password_hash) must fail
        login cleanly (return None), never raise ValueError."""
        h = harness
        await h.login_as("Legacyvictim")
        bad = hashlib.sha256(b"whatever").hexdigest()
        await h.db._db.execute(
            "UPDATE accounts SET password_hash = ? WHERE username = ?",
            (bad, "test_legacyvictim"),
        )
        await h.db._db.commit()

        # Must return None, not raise.
        assert await h.db.authenticate(
            "test_legacyvictim", "whatever"
        ) is None
