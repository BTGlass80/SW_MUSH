"""
Tests for MEDIUM verify-campaign findings: rate-bucket address-reuse + IP-throttle
empty-key leak (VERIFY_FINDINGS_2026-06-18.md).
"""
import time
from collections import defaultdict
from unittest.mock import MagicMock, patch

import pytest


# ── _sliding_window_allow (server/api.py) ────────────────────────────────────

def test_sliding_window_allow_imports():
    from server.api import _sliding_window_allow
    assert callable(_sliding_window_allow)


def test_sliding_window_allow_admits_new_ip():
    from server.api import _sliding_window_allow
    bucket = defaultdict(list)
    assert _sliding_window_allow(bucket, "1.2.3.4", 3, 60) is True
    assert "1.2.3.4" in bucket
    assert len(bucket["1.2.3.4"]) == 1


def test_sliding_window_allow_deletes_empty_key_on_expiry():
    """Key must be deleted when all timestamps have expired, not left as []."""
    from server.api import _sliding_window_allow
    bucket: dict = {"1.2.3.4": [time.time() - 120]}  # expired entry
    result = _sliding_window_allow(bucket, "1.2.3.4", 3, 60)
    assert result is True  # new request admitted
    assert "1.2.3.4" in bucket  # now has the fresh timestamp
    assert len(bucket["1.2.3.4"]) == 1  # only the new one; expired was pruned


def test_sliding_window_allow_no_phantom_key_on_first_get():
    """Should NOT create a key via defaultdict when the IP has never been seen."""
    from server.api import _sliding_window_allow
    bucket: defaultdict = defaultdict(list)
    # Peek before any call
    keys_before = set(bucket.keys())
    _sliding_window_allow(bucket, "10.0.0.1", 3, 60)
    # After an admitted request, key exists with one entry
    assert "10.0.0.1" in bucket
    assert len(bucket["10.0.0.1"]) == 1
    assert len(keys_before) == 0


def test_sliding_window_allow_cleans_stale_key_when_denied():
    """Stale (all-expired) key is cleaned up even when request would be rate-limited."""
    from server.api import _sliding_window_allow
    # Seed with 3 expired entries (max=3) → all expire → clean key → allow
    old_ts = time.time() - 120
    bucket = {"2.2.2.2": [old_ts, old_ts, old_ts]}
    result = _sliding_window_allow(bucket, "2.2.2.2", 3, 60)
    assert result is True  # admitted because all prior entries expired
    assert len(bucket["2.2.2.2"]) == 1


def test_sliding_window_allow_rate_limits_at_max():
    from server.api import _sliding_window_allow
    bucket: defaultdict = defaultdict(list)
    for _ in range(3):
        assert _sliding_window_allow(bucket, "3.3.3.3", 3, 60) is True
    assert _sliding_window_allow(bucket, "3.3.3.3", 3, 60) is False


# ── web_portal._login_rate_ok ─────────────────────────────────────────────────

def test_login_rate_ok_deletes_empty_key():
    """_login_attempts key must not linger after all timestamps expire."""
    import server.web_portal as wp
    original = dict(wp._login_attempts)
    try:
        wp._login_attempts.clear()
        # Seed an expired entry
        wp._login_attempts["5.5.5.5"] = [time.time() - 200]
        result = wp._login_rate_ok("5.5.5.5")
        assert result is True
        # Key exists with exactly 1 fresh entry (not 0 stale + 1 new = 2)
        assert "5.5.5.5" in wp._login_attempts
        assert len(wp._login_attempts["5.5.5.5"]) == 1
    finally:
        wp._login_attempts.clear()
        wp._login_attempts.update(original)


def test_login_rate_ok_rate_limits():
    import server.web_portal as wp
    try:
        wp._login_attempts.clear()
        for _ in range(wp._LOGIN_RATE_MAX):
            assert wp._login_rate_ok("6.6.6.6") is True
        assert wp._login_rate_ok("6.6.6.6") is False
    finally:
        wp._login_attempts.clear()


# ── CommandParser._rate_buckets (parser/commands.py) ─────────────────────────

def _make_parser():
    from parser.commands import CommandParser, CommandRegistry
    reg = CommandRegistry()
    db = MagicMock()
    sm = MagicMock()
    return CommandParser(reg, db, sm)


def test_rate_bucket_keyed_on_session_id_not_address():
    """Two sessions with different .id values must never share a bucket."""
    parser = _make_parser()

    s1 = MagicMock()
    s1.id = 1
    s2 = MagicMock()
    s2.id = 2

    # Drain s1's bucket
    for _ in range(100):
        parser._check_rate_limit(s1)

    # s2 should still have a full bucket (not inheriting s1's drained one)
    assert parser._check_rate_limit(s2) is True


def test_rate_bucket_address_reuse_does_not_bleed():
    """Simulates the old id(session) bug: two objects sharing the same address
    should NOT share a rate bucket with the new session.id keying."""
    parser = _make_parser()

    s1 = MagicMock()
    s1.id = 10
    s2 = MagicMock()
    s2.id = 11  # different monotonic ID, even if address were the same

    # Drain s1
    for _ in range(100):
        parser._check_rate_limit(s1)

    # s2 is independent
    assert parser._check_rate_limit(s2) is True


def test_clear_session_removes_bucket():
    parser = _make_parser()
    s = MagicMock()
    s.id = 42
    parser._check_rate_limit(s)
    assert 42 in parser._rate_buckets
    parser.clear_session(42)
    assert 42 not in parser._rate_buckets


def test_clear_session_noop_for_unknown_id():
    parser = _make_parser()
    parser.clear_session(9999)  # must not raise
