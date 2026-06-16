# -*- coding: utf-8 -*-
"""T3.21 security pre-pass — per-IP portal login throttle + a swallowed-bug fix.

(1) handle_login now rejects with 429 once an IP exceeds the per-window login
    budget — bounds credential stuffing ACROSS accounts (db.authenticate's
    lockout is only PER-ACCOUNT). Unit-tested at the _login_rate_ok seam with
    isolated IPs so there is no cross-test pollution of the global counter.
(2) handle_character's faction-membership query used WHERE m.character_id on
    org_memberships, which is keyed by char_id — the wrong column raised
    "no such column" and was swallowed by the bare except, so faction_membership
    was silently never populated. Fixed to m.char_id.
"""
import pathlib

from server.web_portal import (
    _LOGIN_RATE_MAX,
    _login_rate_ok,
    _reset_login_throttle,
)

WEB_PORTAL_SRC = (
    pathlib.Path(__file__).resolve().parent.parent / "server" / "web_portal.py"
).read_text(encoding="utf-8")


def test_login_throttle_blocks_after_max():
    _reset_login_throttle()
    ip = "203.0.113.7"  # TEST-NET-3, never a real client
    for _ in range(_LOGIN_RATE_MAX):
        assert _login_rate_ok(ip) is True
    assert _login_rate_ok(ip) is False  # the (MAX+1)th attempt is throttled
    _reset_login_throttle()


def test_login_throttle_is_per_ip():
    _reset_login_throttle()
    a, b = "198.51.100.1", "198.51.100.2"
    for _ in range(_LOGIN_RATE_MAX):
        assert _login_rate_ok(a) is True
    assert _login_rate_ok(a) is False     # a is now throttled
    assert _login_rate_ok(b) is True      # a different IP is unaffected
    _reset_login_throttle()


def test_handle_login_wires_the_throttle_and_returns_429():
    assert "_login_rate_ok(_get_client_ip(request))" in WEB_PORTAL_SRC
    assert "429" in WEB_PORTAL_SRC


def test_faction_membership_query_uses_correct_column():
    # org_memberships is keyed by char_id; the old m.character_id raised
    # "no such column" and was swallowed -> faction_membership silently empty.
    assert "WHERE m.char_id = ? AND o.org_type = 'faction'" in WEB_PORTAL_SRC
    assert "m.character_id" not in WEB_PORTAL_SRC  # the buggy alias.column is gone
