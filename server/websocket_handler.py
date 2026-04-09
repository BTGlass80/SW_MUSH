"""
WebSocket protocol handler.

Provides a browser-accessible connection to the MUSH.
Messages are JSON-encoded with a 'type' field for rich client rendering.
"""
import asyncio
import json
import logging
from typing import TYPE_CHECKING

import websockets

from server.session import Session, Protocol

if TYPE_CHECKING:
    from server.game_server import GameServer

log = logging.getLogger(__name__)


class WebSocketHandler:
    """Manages the WebSocket listener and spawns sessions for each connection."""

    def __init__(self, game_server: "GameServer"):
        self.game = game_server
        self._server = None

    async def start(self, host: str, port: int):
        """Start the WebSocket listener."""
        self._server = await websockets.serve(
            self._connection_handler,
            host,
            port,
            ping_interval=30,
            ping_timeout=10,
        )
        log.info("WebSocket server listening on %s:%d", host, port)

    async def _connection_handler(self, websocket):
        """
        Called for each new WebSocket connection.
        Creates a Session and bridges input/output.
        """
        async def send_text(text: str):
            await websocket.send(text)

        async def close_conn():
            await websocket.close()

        session = Session(
            protocol=Protocol.WEBSOCKET,
            send_callback=send_text,
            close_callback=close_conn,
            width=72,   # Conservative default; client sends resize on connect
            height=50,
        )

        self.game.session_mgr.add(session)

        try:
            # Start the input reader as a background task
            read_task = asyncio.create_task(
                self._read_loop(websocket, session)
            )
            # Hand off to the game server's login/input handler
            await self.game.handle_new_session(session, reader=None)
            read_task.cancel()
        except (
            websockets.exceptions.ConnectionClosed,
            asyncio.CancelledError,
        ):
            pass
        except Exception as e:
            log.exception("WebSocket session error: %s", e)
        finally:
            self.game.session_mgr.remove(session)

    async def _read_loop(self, websocket, session: Session):
        """
        Continuously reads messages from the WebSocket and feeds
        them into the session's input queue.
        """
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)

                    # Handle resize messages (client reports its char width)
                    if data.get("type") == "resize":
                        w = data.get("width", 78)
                        if isinstance(w, int) and 40 <= w <= 250:
                            session.width = w
                        continue

                    text = data.get("input", data.get("text", ""))
                except (json.JSONDecodeError, AttributeError):
                    text = str(message)

                text = text.strip()
                if text:
                    session.feed_input(text)
        except websockets.exceptions.ConnectionClosed:
            # Signal the session that the connection is gone
            session.feed_input("quit")

    async def stop(self):
        """Shut down the WebSocket listener."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            log.info("WebSocket server stopped.")
