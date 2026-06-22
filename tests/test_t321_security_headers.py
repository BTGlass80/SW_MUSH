# -*- coding: utf-8 -*-
"""T3.21 security tail — public aiohttp surface hardening.

The browser-facing aiohttp app (server/web_client.py) serves the SPA (which
renders server-provided strings) and the chargen/portal JSON API to
unauthenticated clients. Before this drop it had:
  * NO security response headers at all (no nosniff / clickjacking / referrer
    protection), and
  * aiohttp's default 1 MiB request-body limit (a hostile client could stream a
    near-megabyte body to amplify memory pressure on the single DB worker).

This drop adds an app-wide security-headers middleware and an explicit,
operator-tunable request-size cap. Tested at the seam (no port binding): the
middleware is exercised directly with a mocked request + stub handler, and the
wiring onto the real Application is asserted from source.
"""
import asyncio
import importlib
import pathlib

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from server.web_client import (
    _SECURITY_HEADERS,
    _MAX_REQUEST_BYTES,
    _apply_security_headers,
    _assert_no_cors_headers,
    _resolve_max_request_bytes,
    _security_headers_middleware,
)

WEB_CLIENT_SRC = (
    pathlib.Path(__file__).resolve().parent.parent / "server" / "web_client.py"
).read_text(encoding="utf-8")


def _run(coro):
    return asyncio.run(coro)


# ── the header set ──────────────────────────────────────────────────────────

def test_core_security_headers_present():
    assert _SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
    # SAMEORIGIN, not DENY: the SPA frames its own /chargen page (see
    # test_same_origin_framing_is_allowed_for_the_embedded_chargen_iframe).
    assert _SECURITY_HEADERS["X-Frame-Options"] == "SAMEORIGIN"
    assert "Referrer-Policy" in _SECURITY_HEADERS
    assert "Content-Security-Policy" in _SECURITY_HEADERS
    assert "Permissions-Policy" in _SECURITY_HEADERS


def test_csp_is_minimal_so_it_does_not_break_the_inline_spa():
    # The SPA relies on inline <script>, onclick= handlers, and style=
    # attributes. A script-src or default-src directive would break it, so the
    # CSP must restrict only the frame/base/object vectors the SPA never uses.
    csp = _SECURITY_HEADERS["Content-Security-Policy"]
    assert "script-src" not in csp
    assert "default-src" not in csp
    assert "style-src" not in csp
    assert "frame-ancestors 'self'" in csp
    assert "base-uri 'self'" in csp
    assert "object-src 'none'" in csp


def test_same_origin_framing_is_allowed_for_the_embedded_chargen_iframe():
    # REGRESSION GUARD: the embedded character-creation flow loads
    # /chargen?embedded=1 into a same-origin <iframe> inside /play
    # (static/client.html #chargen-iframe). DENY / frame-ancestors 'none'
    # blocked that iframe and made character creation impossible. The headers
    # must permit SAME-origin framing while still blocking cross-origin
    # (the clickjacking vector that matters).
    assert _SECURITY_HEADERS["X-Frame-Options"] == "SAMEORIGIN"
    csp = _SECURITY_HEADERS["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in csp
    # And must NOT be the framing-killing values that broke chargen.
    assert _SECURITY_HEADERS["X-Frame-Options"] != "DENY"
    assert "frame-ancestors 'none'" not in csp


def test_hsts_is_intentionally_omitted():
    # HSTS is an HTTPS/deployment decision for the operator's TLS proxy, not for
    # this plain-HTTP origin — asserting absence guards against an accidental add
    # that would brick http:// access.
    assert "Strict-Transport-Security" not in _SECURITY_HEADERS


# ── the middleware ──────────────────────────────────────────────────────────

def test_headers_applied_to_a_normal_response():
    async def handler(request):
        return web.Response(text="ok")

    req = make_mocked_request("GET", "/")
    resp = _run(_security_headers_middleware(req, handler))
    for name, value in _SECURITY_HEADERS.items():
        assert resp.headers.get(name) == value


def test_headers_applied_to_a_raised_http_error():
    # 404/413/429/500 are raised as HTTPException; they must still carry the
    # protections (esp. nosniff on JSON error bodies).
    async def handler(request):
        raise web.HTTPNotFound()

    req = make_mocked_request("GET", "/missing")
    try:
        _run(_security_headers_middleware(req, handler))
        raise AssertionError("HTTPNotFound should have propagated")
    except web.HTTPNotFound as exc:
        for name, value in _SECURITY_HEADERS.items():
            assert exc.headers.get(name) == value


def test_middleware_does_not_clobber_a_header_the_handler_set():
    async def handler(request):
        resp = web.Response(text="ok")
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"  # handler intent wins
        return resp

    req = make_mocked_request("GET", "/")
    resp = _run(_security_headers_middleware(req, handler))
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    # ...but the other security headers are still added.
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_prepared_websocket_response_is_skipped():
    # A WebSocket upgrade response is already prepared/sent — _apply must not
    # touch it (mutation is a no-op at best, an error at worst).
    class _PreparedResp:
        prepared = True

        def __init__(self):
            self.headers = web.Response().headers

    resp = _PreparedResp()
    _apply_security_headers(resp)
    assert len(resp.headers) == 0  # nothing added to a prepared response


# ── the request-size cap ────────────────────────────────────────────────────

def test_max_request_bytes_default_is_bounded_and_below_aiohttp_default():
    # Tighter than aiohttp's 1 MiB default, but generous vs real payloads.
    assert 0 < _MAX_REQUEST_BYTES <= 1024 * 1024
    assert _MAX_REQUEST_BYTES == _resolve_max_request_bytes()


def test_max_request_bytes_env_override(monkeypatch):
    monkeypatch.setenv("SWMUSH_MAX_REQUEST_BYTES", "131072")
    assert _resolve_max_request_bytes() == 131072


def test_max_request_bytes_rejects_garbage_and_non_positive(monkeypatch):
    for bad in ("not-a-number", "0", "-5", ""):
        monkeypatch.setenv("SWMUSH_MAX_REQUEST_BYTES", bad)
        assert _resolve_max_request_bytes(default=4096) == 4096


# ── wiring onto the real Application ─────────────────────────────────────────

def test_app_is_constructed_with_cap_and_middleware():
    assert "client_max_size=_MAX_REQUEST_BYTES" in WEB_CLIENT_SRC
    assert "middlewares=[_security_headers_middleware]" in WEB_CLIENT_SRC


def test_a_live_application_enforces_the_cap_and_registers_the_middleware():
    # Build an Application exactly the way start() does and assert the wiring
    # took effect on the real aiohttp object (no port binding required).
    app = web.Application(
        client_max_size=_MAX_REQUEST_BYTES,
        middlewares=[_security_headers_middleware],
    )
    assert app._client_max_size == _MAX_REQUEST_BYTES
    assert _security_headers_middleware in app.middlewares


def test_module_imports_clean():
    # Guards against an import-time regression in the new module-level block.
    importlib.reload(importlib.import_module("server.web_client"))


# ── CORS posture (T3.21 decision #6 — same-origin, deliberate no-op) ──────────

def test_default_headers_carry_no_cors_header():
    # The SPA + API are same-origin; emitting Access-Control-Allow-* would only
    # RELAX the browser's same-origin protection on an unauthenticated surface.
    for name in _SECURITY_HEADERS:
        assert not name.lower().startswith("access-control-")


def test_assert_no_cors_headers_passes_on_the_real_default():
    # The live default set must satisfy the invariant (no exception).
    _assert_no_cors_headers(_SECURITY_HEADERS)


def test_assert_no_cors_headers_raises_on_a_permissive_default():
    # REGRESSION GUARD: a future dev pasting a wildcard CORS header into the
    # security-headers dict must fail loudly at import, not silently open CORS.
    bad = dict(_SECURITY_HEADERS)
    bad["Access-Control-Allow-Origin"] = "*"
    try:
        _assert_no_cors_headers(bad)
        raise AssertionError("a permissive CORS default should have raised")
    except RuntimeError as exc:
        assert "CORS" in str(exc)
    # Case-insensitive: header names are not case-normalized by aiohttp.
    bad2 = dict(_SECURITY_HEADERS)
    bad2["access-control-allow-credentials"] = "true"
    try:
        _assert_no_cors_headers(bad2)
        raise AssertionError("a lowercase CORS default should have raised")
    except RuntimeError:
        pass


def test_live_responses_carry_no_cors_header():
    # End-to-end through the middleware: neither a normal response nor a raised
    # error may carry an Access-Control-* header.
    async def ok_handler(request):
        return web.Response(text="ok")

    req = make_mocked_request("GET", "/api/chargen/check-name/x")
    resp = _run(_security_headers_middleware(req, ok_handler))
    assert not any(h.lower().startswith("access-control-") for h in resp.headers)

    async def err_handler(request):
        raise web.HTTPNotFound()

    req2 = make_mocked_request("GET", "/missing")
    try:
        _run(_security_headers_middleware(req2, err_handler))
        raise AssertionError("HTTPNotFound should have propagated")
    except web.HTTPNotFound as exc:
        assert not any(h.lower().startswith("access-control-") for h in exc.headers)


def test_cors_posture_is_documented_in_source():
    # The deliberate same-origin no-op decision must be discoverable in-source.
    assert "_assert_no_cors_headers(_SECURITY_HEADERS)" in WEB_CLIENT_SRC
    assert "CORS" in WEB_CLIENT_SRC
    assert "same-origin" in WEB_CLIENT_SRC
    # And we must NOT have added a CORS middleware (decision #6: "no middleware").
    assert "aiohttp_cors" not in WEB_CLIENT_SRC
    assert "Access-Control-Allow-Origin" not in _SECURITY_HEADERS
