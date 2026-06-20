"""
Web Client — serves the browser UI and handles WebSocket connections.

Runs a single aiohttp HTTP server on port 8080 (default).
  GET /           → client.html
  GET /chargen    → chargen.html (web character creation)
  GET /ws         → WebSocket upgrade (game connection)
  GET /static/    → static files
  /api/chargen/*  → REST API for web character creation
  /api/auth/*     → Token-based auth for post-chargen auto-login

Using aiohttp's built-in WebSocket support eliminates the separate
websockets-library server on port 4001, removing all second-port
firewall issues on Windows.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web, WSMsgType

from server.session import Session, Protocol

if TYPE_CHECKING:
    from server.game_server import GameServer

log = logging.getLogger(__name__)


# ── Security hardening (T3.21 — public aiohttp surface) ──────────────────────
# Defence-in-depth response headers applied app-wide. The SPA renders
# server-provided strings and the API returns JSON to unauthenticated clients,
# so these guard the whole surface (HTML, static assets, and JSON alike):
#   * X-Content-Type-Options: nosniff — stop MIME-sniffing of API JSON as HTML.
#   * X-Frame-Options + CSP frame-ancestors — clickjacking, belt-and-suspenders
#     across legacy (XFO) and modern (CSP) browsers. SAMEORIGIN / 'self' (NOT
#     DENY / 'none'): the SPA embeds its own /chargen page in a same-origin
#     iframe (the embedded character-creation flow), so DENY/'none' would block
#     chargen entirely. 'self'/SAMEORIGIN still blocks all CROSS-origin framing,
#     which is the clickjacking vector that matters.
#   * CSP base-uri/object-src — block <base>-tag hijack and plugin/object embeds.
#   * Referrer-Policy — don't leak full URLs to cross-origin destinations.
#   * Permissions-Policy — disable powerful APIs the game never uses.
# The CSP is deliberately MINIMAL: the client relies on inline <script>, inline
# onclick= handlers, and inline style= attributes, so a script-src/default-src
# directive would break it. We restrict only the frame/base/object vectors the
# SPA never uses. (HSTS is intentionally omitted — enabling it is an
# HTTPS/deployment decision for the operator's TLS-terminating proxy, not for
# this plain-HTTP origin.)
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "frame-ancestors 'self'; base-uri 'self'; object-src 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def _resolve_max_request_bytes(default: int = 256 * 1024) -> int:
    """Cap the request body the public endpoints will read. All client bodies
    are small JSON (chargen/login are single-digit KB); aiohttp's own default
    is 1 MiB. Default to 256 KiB — huge headroom over any real payload — so a
    hostile client cannot stream a multi-megabyte body to amplify memory
    pressure on the single shared DB worker. Operator-overridable (raise OR
    lower) via SWMUSH_MAX_REQUEST_BYTES; garbage / non-positive falls back."""
    raw = os.environ.get("SWMUSH_MAX_REQUEST_BYTES")
    if not raw:
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    return val if val > 0 else default


_MAX_REQUEST_BYTES = _resolve_max_request_bytes()


def _apply_security_headers(response) -> None:
    """Add _SECURITY_HEADERS to a not-yet-sent response. Uses setdefault so a
    value a handler set on purpose always wins; skips WebSocket upgrades (their
    headers are already prepared/sent — mutating them is a no-op at best)."""
    if getattr(response, "prepared", False):
        return
    headers = getattr(response, "headers", None)
    if headers is None:
        return
    for name, value in _SECURITY_HEADERS.items():
        headers.setdefault(name, value)


@web.middleware
async def _security_headers_middleware(request, handler):
    """Apply the security headers to every response, including raised HTTP
    errors (404/413/429/500) so error responses carry the same protections."""
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        _apply_security_headers(exc)
        raise
    _apply_security_headers(response)
    return response


class WebClient:
    """Single aiohttp server: serves client.html + handles /ws WebSocket connections."""

    def __init__(self):
        self._runner = None
        self._app = None
        self._game = None

    def set_game(self, game) -> None:
        """Called by GameServer so we can spawn sessions."""
        self._game = game

    async def start(self, host: str = "0.0.0.0", port: int = 8080,
                    static_dir: str = None) -> None:
        if static_dir is None:
            project_root = Path(__file__).resolve().parent.parent
            static_dir = str(project_root / "static")

        if not os.path.isdir(static_dir):
            log.warning("Static directory not found: %s — web client disabled.", static_dir)
            return

        client_html = os.path.join(static_dir, "client.html")
        if not os.path.isfile(client_html):
            log.warning("client.html not found in %s — web client disabled.", static_dir)
            return

        self._app = web.Application(
            client_max_size=_MAX_REQUEST_BYTES,
            middlewares=[_security_headers_middleware],
        )

        async def serve_client(request):
            resp = web.FileResponse(client_html)
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

        # Serve portal.html at / (landing page)
        portal_html = os.path.join(static_dir, "portal.html")

        async def serve_portal(request):
            if not os.path.isfile(portal_html):
                # Fall back to client.html if portal not yet built
                return await serve_client(request)
            resp = web.FileResponse(portal_html)
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

        # Serve chargen.html at /chargen
        chargen_html = os.path.join(static_dir, "chargen.html")

        async def serve_chargen(request):
            if not os.path.isfile(chargen_html):
                return web.Response(text="Chargen page not found", status=404)
            resp = web.FileResponse(chargen_html)
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

        self._app.router.add_get("/", serve_portal)
        self._app.router.add_get("/play", serve_client)
        self._app.router.add_get("/client.html", serve_client)
        self._app.router.add_get("/chargen", serve_chargen)
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_static("/static/", static_dir, show_index=False)

        # Register chargen REST API if game is wired up
        if self._game is not None:
            try:
                from server.api import ChargenAPI
                self._chargen_api = ChargenAPI(
                    species_reg=self._game.species_reg,
                    skill_reg=self._game.skill_reg,
                    db=self._game.db,
                )
                self._chargen_api.register_routes(self._app)
                log.info("Chargen API: %d species, %d skills available",
                         self._game.species_reg.count,
                         self._game.skill_reg.count)
            except Exception as e:
                log.error("Chargen API registration failed: %s", e,
                          exc_info=True)

            # Register portal REST API
            try:
                from server.web_portal import PortalAPI
                self._portal_api = PortalAPI(
                    db=self._game.db,
                    session_mgr=self._game.session_mgr,
                    game=self._game,
                )
                self._portal_api.register_routes(self._app)
            except Exception as e:
                log.error("Portal API registration failed: %s", e,
                          exc_info=True)
        else:
            log.warning("Chargen API: game not wired up, API routes skipped")

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port)
        await site.start()
        log.info("Web server (HTTP + WebSocket) at http://%s:%d/  ws://%s:%d/ws",
                 host, port, host, port)

    async def _ws_handler(self, request):
        """Handle a WebSocket upgrade on GET /ws."""
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        async def send_text(text: str) -> None:
            if not ws.closed:
                try:
                    await ws.send_str(text)
                except Exception as _e:
                    log.debug("silent except in server/web_client.py:149: %s", _e, exc_info=True)

        async def close_conn() -> None:
            if not ws.closed:
                await ws.close()

        session = Session(
            protocol=Protocol.WEBSOCKET,
            send_callback=send_text,
            close_callback=close_conn,
            width=72,
            height=50,
        )

        # Capture the client IP for the pre-auth connect/create throttle,
        # spoof-resistantly: _get_client_ip honors X-Forwarded-For only when
        # the direct peer is a configured trusted proxy, otherwise the raw
        # peer address (so a direct WS client can't forge it).
        try:
            from server.api import _get_client_ip
            session.client_ip = _get_client_ip(request)
        except Exception:
            log.debug("ws: client_ip capture failed", exc_info=True)

        if self._game is None:
            await ws.close()
            return ws

        self._game.session_mgr.add(session)

        game_task = asyncio.create_task(
            self._game.handle_new_session(session, reader=None)
        )

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get("type") == "resize":
                            w = data.get("width", 78)
                            if isinstance(w, int) and 40 <= w <= 250:
                                session.width = w
                            continue
                        if data.get("type") == "token_auth":
                            # Auto-login from web chargen redirect. Hand the
                            # SIGNED token straight to the login loop, which is
                            # the authoritative verifier (game_server's
                            # __token_auth__ branch re-checks it). We deliberately
                            # do NOT resolve the token to an account_id here:
                            # feeding a bare id would let any WS client forge
                            # `__token_auth__ <id>` via the {"input": ...} channel
                            # and seize an account with no password.
                            token = data.get("token", "")
                            if token:
                                session.feed_input(f"__token_auth__ {token}")
                            continue
                        text = data.get("input", data.get("text", ""))
                    except (json.JSONDecodeError, AttributeError):
                        text = msg.data
                    text = text.strip()
                    if text:
                        session.feed_input(text)
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                    break
        except Exception as e:
            log.warning("WebSocket session error: %s", e)
        finally:
            game_task.cancel()
            try:
                await game_task
            except (asyncio.CancelledError, Exception) as _e:
                log.debug("silent except in server/web_client.py:217: %s", _e, exc_info=True)
            self._game.session_mgr.remove(session)

        return ws

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            log.info("Web server stopped.")
