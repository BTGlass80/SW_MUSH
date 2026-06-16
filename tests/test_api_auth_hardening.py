# -*- coding: utf-8 -*-
"""T3.21 HIGH hardening — server/api.py auth surface.

Covers the two HIGH-severity findings from the T3.21 security audit that both
live on the api.py auth/rate-limit surface:

  1. Login-token HMAC secret is persisted to a 0600 key file so a server
     restart no longer invalidates every outstanding token (mass re-auth).
  2. X-Forwarded-For is honored ONLY when the direct peer is a configured
     trusted proxy, so a raw-socket client cannot spoof its source IP and
     defeat the per-IP rate limiters.
"""
import os

import pytest

from server import api


# ──────────────────────────────────────────────────────────────────────
# Mock request (only what _get_client_ip touches)
# ──────────────────────────────────────────────────────────────────────

class _Transport:
    def __init__(self, peername):
        self._peername = peername

    def get_extra_info(self, key):
        assert key == "peername"
        return self._peername


class _Req:
    def __init__(self, *, peer="203.0.113.7", xff=None):
        self.headers = {}
        if xff is not None:
            self.headers["X-Forwarded-For"] = xff
        self.transport = _Transport((peer, 12345) if peer else None)


@pytest.fixture
def isolate_globals(monkeypatch):
    """Restore the module-level secret + trusted-proxy globals after each test."""
    monkeypatch.setattr(api, "_TOKEN_SECRET", None, raising=False)
    monkeypatch.setattr(api, "_TRUSTED_PROXIES", frozenset(), raising=False)
    monkeypatch.delenv(api.TOKEN_SECRET_ENV_VAR, raising=False)
    monkeypatch.delenv(api.TRUSTED_PROXIES_ENV_VAR, raising=False)
    yield


# ──────────────────────────────────────────────────────────────────────
# 1. Token-secret persistence
# ──────────────────────────────────────────────────────────────────────

def test_secret_file_created_with_32_bytes(tmp_path, monkeypatch, isolate_globals):
    path = tmp_path / "tok.key"
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))
    secret = api._load_or_create_token_secret()
    assert len(secret) == 32
    assert path.exists()
    assert path.read_bytes() == secret


def test_secret_is_stable_across_reloads(tmp_path, monkeypatch, isolate_globals):
    path = tmp_path / "tok.key"
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))
    first = api._load_or_create_token_secret()
    second = api._load_or_create_token_secret()
    assert first == second


def test_token_survives_simulated_restart(tmp_path, monkeypatch, isolate_globals):
    """A token minted before a restart still verifies after — the whole point."""
    path = tmp_path / "tok.key"
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))
    token = api.create_login_token(42, ttl=3600)
    # Simulate process restart: drop the cached in-process secret.
    monkeypatch.setattr(api, "_TOKEN_SECRET", None)
    assert api.verify_login_token(token) == 42


def test_too_short_file_is_regenerated(tmp_path, monkeypatch, isolate_globals):
    path = tmp_path / "tok.key"
    path.write_bytes(b"short")  # < 32 bytes
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))
    secret = api._load_or_create_token_secret()
    assert len(secret) == 32
    assert path.read_bytes() == secret


def test_unwritable_path_falls_back_to_ephemeral(tmp_path, monkeypatch, isolate_globals):
    """A directory in place of the file => OSError on read => ephemeral secret,
    not a crash (degrade safely, the pre-hardening behavior)."""
    path = tmp_path / "as_dir"
    path.mkdir()
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))
    secret = api._load_or_create_token_secret()
    assert len(secret) == 32  # still usable, just not persisted


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode bits only")
def test_secret_file_is_0600(tmp_path, monkeypatch, isolate_globals):
    path = tmp_path / "tok.key"
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))
    api._load_or_create_token_secret()
    assert (path.stat().st_mode & 0o777) == 0o600


def test_failed_persist_does_not_corrupt_existing_file(tmp_path, monkeypatch, isolate_globals):
    """A failed persist (os.replace raises) must NOT truncate the on-disk file
    (atomic temp-then-rename) and must leave no temp turd; the caller still gets
    a usable ephemeral secret instead of crashing."""
    path = tmp_path / "tok.key"
    path.write_bytes(b"short")  # too short => triggers regen + persist
    monkeypatch.setenv(api.TOKEN_SECRET_ENV_VAR, str(path))

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(api.os, "replace", boom)
    secret = api._load_or_create_token_secret()
    assert len(secret) == 32                          # usable ephemeral secret
    assert path.read_bytes() == b"short"              # original NOT clobbered
    assert not (tmp_path / "tok.key.tmp").exists()    # temp cleaned up


# ──────────────────────────────────────────────────────────────────────
# 2. X-Forwarded-For hardening
# ──────────────────────────────────────────────────────────────────────

def test_xff_ignored_with_no_trusted_proxies(isolate_globals):
    """Default deployment: XFF present but ignored => real peer wins."""
    api._TRUSTED_PROXIES = frozenset()
    req = _Req(peer="203.0.113.7", xff="10.0.0.1")
    assert api._get_client_ip(req) == "203.0.113.7"


def test_xff_ignored_when_peer_not_trusted(isolate_globals):
    """Attacker on a raw socket cannot spoof via XFF — peer isn't a proxy."""
    api._TRUSTED_PROXIES = frozenset({"192.168.1.1"})
    req = _Req(peer="203.0.113.7", xff="1.2.3.4")
    assert api._get_client_ip(req) == "203.0.113.7"


def test_xff_honored_from_trusted_proxy(isolate_globals):
    api._TRUSTED_PROXIES = frozenset({"192.168.1.1"})
    req = _Req(peer="192.168.1.1", xff="203.0.113.7")
    assert api._get_client_ip(req) == "203.0.113.7"


def test_xff_chain_returns_rightmost_untrusted(isolate_globals):
    """Two trusted hops in front: the real client sits left of them."""
    api._TRUSTED_PROXIES = frozenset({"192.168.1.1", "192.168.1.2"})
    req = _Req(peer="192.168.1.1", xff="203.0.113.7, 192.168.1.2")
    assert api._get_client_ip(req) == "203.0.113.7"


def test_xff_spoof_through_trusted_proxy_is_resisted(isolate_globals):
    """Client prepends a fake hop; the proxy appends the true client. The
    right-most-untrusted walk returns the appended (true) client, not the
    spoofed leading entry."""
    api._TRUSTED_PROXIES = frozenset({"192.168.1.1"})
    req = _Req(peer="192.168.1.1", xff="6.6.6.6, 203.0.113.7")
    assert api._get_client_ip(req) == "203.0.113.7"


def test_all_trusted_chain_falls_back_to_peer(isolate_globals):
    """If every XFF hop is itself a trusted proxy, trust the un-spoofable direct
    peer, not the attacker-influenceable leading XFF entry."""
    api._TRUSTED_PROXIES = frozenset({"192.168.1.1", "192.168.1.2"})
    req = _Req(peer="192.168.1.1", xff="192.168.1.2, 192.168.1.1")
    assert api._get_client_ip(req) == "192.168.1.1"


def test_no_peername_returns_unknown(isolate_globals):
    api._TRUSTED_PROXIES = frozenset()
    req = _Req(peer=None)
    assert api._get_client_ip(req) == "unknown"


def test_none_transport_returns_unknown(isolate_globals):
    """A request with transport=None (can happen on a dropped conn) must not
    AttributeError through the rate-limiter path."""
    api._TRUSTED_PROXIES = frozenset()
    req = _Req(peer="203.0.113.7")
    req.transport = None
    assert api._get_client_ip(req) == "unknown"


def test_load_trusted_proxies_parses_env(monkeypatch, isolate_globals):
    monkeypatch.setenv(api.TRUSTED_PROXIES_ENV_VAR, " 10.0.0.1 , 10.0.0.2 ,")
    assert api._load_trusted_proxies() == frozenset({"10.0.0.1", "10.0.0.2"})


def test_load_trusted_proxies_empty_when_unset(monkeypatch, isolate_globals):
    monkeypatch.delenv(api.TRUSTED_PROXIES_ENV_VAR, raising=False)
    assert api._load_trusted_proxies() == frozenset()
