# -*- coding: utf-8 -*-
"""
tests/test_datetime_utcnow_hardening.py — launch hardening (2026-06-20).

`datetime.utcnow()` is deprecated (Python 3.12+) and slated for removal; the
launch box runs Python 3.14. The three production sites that built mail/bounty
`sent_at` timestamps with `datetime.utcnow().isoformat()` now use the
behavior-preserving `datetime.now(timezone.utc).replace(tzinfo=None).isoformat()`
so the STORED string stays byte-identical (naive-UTC ISO, no `+00:00` offset)
while the deprecated call is gone.

These guards keep it from regressing.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_TIMESTAMP_SITES = [
    "engine/mail_utils.py",
    "parser/mail_commands.py",
    "parser/pc_bounty_commands.py",
]


class TestNoDeprecatedUtcnow(unittest.TestCase):

    def test_no_utcnow_in_production(self):
        """No production module may call the deprecated datetime.utcnow()."""
        offenders = []
        for sub in ("engine", "parser", "server", "db", "ai"):
            for p in (PROJECT_ROOT / sub).rglob("*.py"):
                txt = p.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(txt.splitlines(), 1):
                    if "utcnow()" in line and not line.lstrip().startswith("#") \
                            and "--" not in line:
                        offenders.append(f"{p.relative_to(PROJECT_ROOT)}:{i}")
        self.assertEqual(
            offenders, [],
            "datetime.utcnow() is deprecated (removal-slated; box runs 3.14). "
            "Use datetime.now(timezone.utc)[.replace(tzinfo=None)]: "
            + "; ".join(offenders)
        )

    def test_timestamp_sites_use_naive_utc_pattern(self):
        for rel in _TIMESTAMP_SITES:
            txt = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(
                "datetime.now(timezone.utc).replace(tzinfo=None).isoformat()", txt,
                f"{rel} must build its timestamp with the naive-UTC pattern."
            )

    def test_naive_utc_pattern_is_format_preserving(self):
        """The replacement yields a NAIVE ISO string (no tz offset), identical
        in shape to the old datetime.utcnow().isoformat() output — so stored
        rows and `fromisoformat` / string-ORDER-BY consumers are unaffected."""
        s = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self.assertNotIn("+00:00", s, "stored timestamp must stay naive (no offset)")
        self.assertIsNone(re.search(r"[+-]\d{2}:\d{2}$", s),
                          "stored timestamp must carry no timezone offset")
        # Round-trips and parses back to a naive datetime, like the old format.
        parsed = datetime.fromisoformat(s)
        self.assertIsNone(parsed.tzinfo)
        self.assertTrue(s.startswith(str(parsed.year)))


if __name__ == "__main__":
    unittest.main()
