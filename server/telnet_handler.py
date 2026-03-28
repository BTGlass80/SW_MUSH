"""
Telnet protocol handler.

Uses telnetlib3 for full RFC 854 compliance with option negotiation
(NAWS for terminal size, TTYPE for terminal type detection).
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from server.session import Session, Protocol

if TYPE_CHECKING:
    from server.game_server import GameServer

log = logging.getLogger(__name__)


class TelnetHandler:
    """
    Manages the Telnet listener and spawns sessions for each connection.

    telnetlib3 provides a shell callback model: for each new connection,
    our shell coroutine is called with a reader/writer pair.
    """

    def __init__(self, game_server: "GameServer"):
        self.game = game_server
        self._server = None

    async def start(self, host: str, port: int):
        """Start the Telnet listener."""
        import telnetlib3

        self._server = await telnetlib3.create_server(
            host=host,
            port=port,
            shell=self._shell,
            connect_maxwait=0.5,
            encoding="utf-8",
        )
        log.info("Telnet server listening on %s:%d", host, port)

    async def _shell(self, reader, writer):
        """
        Called for each new Telnet connection.
        Creates a Session and runs the input loop.
        """
        # Build the send/close callbacks for the Session
        async def send_text(text: str):
            writer.write(text)
            await writer.drain()

        async def close_conn():
            writer.close()

        # Get terminal size from NAWS negotiation (defaults if not available)
        width = getattr(writer, "get_extra_info", lambda k, d: d)("cols", 80)
        height = getattr(writer, "get_extra_info", lambda k, d: d)("rows", 24)
        if callable(width):
            width = 80
        if callable(height):
            height = 24

        session = Session(
            protocol=Protocol.TELNET,
            send_callback=send_text,
            close_callback=close_conn,
            width=width,
            height=height,
        )

        self.game.session_mgr.add(session)

        try:
            # Hand off to the game server's login/input handler
            await self.game.handle_new_session(session, reader)
        except (ConnectionError, asyncio.CancelledError):
            pass
        except Exception as e:
            log.exception("Telnet session error: %s", e)
        finally:
            self.game.session_mgr.remove(session)

    async def stop(self):
        """Shut down the Telnet listener."""
        if self._server:
            self._server.close()
            log.info("Telnet server stopped.")
