"""
Web Client — serves the browser UI and handles WebSocket connections.

Runs a single aiohttp HTTP server on port 8080 (default).
  GET /        → client.html
  GET /ws      → WebSocket upgrade (game connection)
  GET /static/ → static files

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

        self._app = web.Application()

        async def serve_client(request):
            resp = web.FileResponse(client_html)
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp

        self._app.router.add_get("/", serve_client)
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_static("/static/", static_dir, show_index=False)

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
                except Exception:
                    pass

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
            except (asyncio.CancelledError, Exception):
                pass
            self._game.session_mgr.remove(session)

        return ws

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            log.info("Web server stopped.")
