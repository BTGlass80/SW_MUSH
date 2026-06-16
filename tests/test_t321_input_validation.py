# -*- coding: utf-8 -*-
"""T3.21 input-validation sweep — type/length bounds on the chargen + portal
POST bodies before they reach handler logic or the DB.

Before this drop, the chargen/portal JSON endpoints assumed the parsed body
(and several of its fields) were well-typed. A malformed body — a JSON array
instead of an object, a numeric `name`, a list `username`, a quarter-megabyte
`background` — would either crash a handler with an unhandled AttributeError /
TypeError (-> opaque 500) or write an unbounded blob into the character's
description column. These are reachable on UNAUTHENTICATED endpoints
(`/api/chargen/submit`, `/api/portal/login`) so they double as a thin DoS /
storage-amplification surface.

This drop hardens the pure validators (graceful error lists, never raise) and
the handler/storage seams (non-dict body -> 400; background coerced + capped to
MAX_BACKGROUND_LEN). All fixes are behavior-preserving for well-formed input.
"""
import json
import pathlib

from engine.chargen_validator import (
    MAX_BACKGROUND_LEN,
    MAX_PASSWORD_LEN,
    validate_account_fields,
    validate_character_name,
    validate_chargen_submission,
)

API_SRC = (
    pathlib.Path(__file__).resolve().parent.parent / "server" / "api.py"
).read_text(encoding="utf-8")
WEB_PORTAL_SRC = (
    pathlib.Path(__file__).resolve().parent.parent / "server" / "web_portal.py"
).read_text(encoding="utf-8")


# ── validate_chargen_submission: non-dict body never raises ───────────────

class _StubReg:
    """Minimal registry stub — these tests only exercise the early type
    guards, which return before any registry lookup happens."""

    def get(self, _key):
        return None


def test_submission_non_dict_returns_error_not_raise():
    reg = _StubReg()
    for bad in ([], "a string", 42, None, 3.14, True):
        errors = validate_chargen_submission(bad, reg, reg)
        assert errors, f"expected an error list for {bad!r}"
        assert isinstance(errors, list)
        assert "JSON object" in errors[0]


def test_submission_dict_still_validates_normally():
    # An empty dict is a well-typed-but-incomplete submission: it must reach
    # the species check (not the non-dict guard) and report unknown species.
    reg = _StubReg()
    errors = validate_chargen_submission({}, reg, reg)
    assert any("species" in e.lower() for e in errors)


# ── validate_character_name: non-string never raises ──────────────────────

def test_character_name_non_string_returns_error():
    for bad in (123, ["a"], {"x": 1}, 3.5):
        errors = validate_character_name(bad)
        assert errors == ["Name must be text."]


def test_character_name_valid_still_passes():
    assert validate_character_name("Kaelin Voss") == []


# ── validate_account_fields: non-string + length bounds ───────────────────

def test_account_fields_non_string_returns_errors_not_raise():
    errors = validate_account_fields(["list"], {"dict": 1})
    assert "Username must be text." in errors
    assert "Password must be text." in errors


def test_account_password_upper_bound_enforced():
    errors = validate_account_fields("gooduser", "x" * (MAX_PASSWORD_LEN + 1))
    assert any("at most" in e for e in errors)


def test_account_password_at_cap_is_accepted():
    errors = validate_account_fields("gooduser", "x" * MAX_PASSWORD_LEN)
    assert errors == []


def test_account_fields_valid_still_passes():
    assert validate_account_fields("gooduser", "secret123") == []


# ── Constants sane ────────────────────────────────────────────────────────

def test_caps_are_sane():
    assert MAX_BACKGROUND_LEN == 2000  # codebase description norm
    assert 72 <= MAX_PASSWORD_LEN <= 256


# ── Handler seams: non-dict top-level body -> 400, not 500 ────────────────

class _NonDictRequest:
    """Mock request whose JSON body is a non-dict (a list)."""

    def __init__(self, ip="203.0.113.55"):
        self.headers = {}
        self.query = {}
        from unittest.mock import MagicMock
        self.transport = MagicMock()
        self.transport.get_extra_info = MagicMock(return_value=(ip, 12345))

    async def json(self):
        return ["not", "a", "dict"]


def test_portal_login_non_dict_body_is_400_not_500():
    import asyncio
    from server.web_portal import PortalAPI, _reset_login_throttle

    _reset_login_throttle()
    portal = PortalAPI.__new__(PortalAPI)  # skip __init__; handler is self-contained
    resp = asyncio.run(portal.handle_login(_NonDictRequest()))
    assert resp.status == 400
    body = json.loads(resp.body.decode("utf-8"))
    assert "error" in body
    _reset_login_throttle()


# ── Source-level guards present at every seam (defense-in-depth grep) ─────

def test_submit_handler_guards_non_dict_body():
    assert "Request body must be a JSON object." in API_SRC


def test_background_is_capped_in_both_api_paths():
    # Both char-build paths (handle_submit + handle_create_character) must
    # truncate background to MAX_BACKGROUND_LEN before it becomes description.
    assert API_SRC.count("background[:MAX_BACKGROUND_LEN]") == 2


def test_portal_login_guards_non_dict_body_in_source():
    assert "Invalid request body" in WEB_PORTAL_SRC


def test_create_character_char_body_coerced_to_dict():
    # The chain-path force_sensitive probe must not call .get on a non-dict.
    assert "_char_body = _cb if isinstance(_cb, dict) else {}" in API_SRC


def test_create_character_guards_non_string_chain_id():
    # An unhashable chain_id (list/dict) would crash corpus.by_id().get(chain_id)
    # with a TypeError -> 500. The handler must reject non-str chain_id with 400.
    assert "chain_id must be a string." in API_SRC
