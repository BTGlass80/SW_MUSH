"""
Telnet protocol handler.

Uses telnetlib3 for full RFC 854 compliance with option negotiation
(NAWS for terminal size, TTYPE for terminal type detection).

MSSP (Mud Server Status Protocol, option 70) is sent proactively on every
new connection so listing crawlers (MudVerse, MUDStats, Grapevine) can
auto-index the game without manual registration.
"""
import asyncio
import logging
import time as _time
from typing import TYPE_CHECKING

from server.session import Session, Protocol

if TYPE_CHECKING:
    from server.game_server import GameServer

log = logging.getLogger(__name__)

# ── MSSP (Mud Server Status Protocol) telnet option constants ──────────────
_IAC = 255       # Interpret As Command
_SB = 250        # Sub-negotiation Begin
_SE = 240        # Sub-negotiation End
_WILL = 251      # WILL (option consent)
_MSSP_OPT = 70   # MSSP option code (tintin.sourceforge.net/mssp/)
_MSSP_VAR = 1    # Key marker inside MSSP sub-negotiation body
_MSSP_VAL = 2    # Value marker inside MSSP sub-negotiation body


class TelnetHandler:
    """
    Manages the Telnet listener and spawns sessions for each connection.

    telnetlib3 provides a shell callback model: for each new connection,
    our shell coroutine is called with a reader/writer pair.
    """

    def __init__(self, game_server: "GameServer"):
        self.game = game_server
        self._server = None
        self._start_time = _time.time()  # for MSSP UPTIME field

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

    def _build_mssp_payload(self) -> bytes:
        """
        Build MSSP sub-negotiation bytes: IAC WILL MSSP + IAC SB MSSP <body> IAC SE.

        The body is a sequence of MSSP_VAR <key> MSSP_VAL <value> pairs (UTF-8).
        All values are ASCII-safe, so no IAC (0xFF) escaping is needed.
        """
        pairs: list[tuple[str, str]] = [
            ("NAME", self.game.config.game_name),
            ("PLAYERS", str(self.game.session_mgr.count)),
            ("UPTIME", str(int(self._start_time))),
            ("PORT", str(self.game.config.telnet_port)),
            ("STATUS", "Beta"),
            ("CODEBASE", "SW_MUSH"),
            ("LANGUAGE", "English"),
            ("CRAWL DELAY", "300"),
        ]
        body = bytearray()
        for key, val in pairs:
            body.append(_MSSP_VAR)
            body.extend(key.encode("utf-8"))
            body.append(_MSSP_VAL)
            body.extend(val.encode("utf-8"))
        return (
            bytes([_IAC, _WILL, _MSSP_OPT])  # announce WILL MSSP
            + bytes([_IAC, _SB, _MSSP_OPT])  # SB MSSP
            + bytes(body)
            + bytes([_IAC, _SE])              # SE
        )

    async def _shell(self, reader, writer):
        """
        Called for each new Telnet connection.
        Creates a Session and runs the input loop.
        """
        # Proactively send MSSP before the session is added so listing crawlers
        # get correct player counts without inflating them.  Raw transport.write()
        # bypasses telnetlib3's text encoding, which is required for IAC bytes.
        # Wrapped fail-open: MSSP failure must never break a real player session.
        try:
            writer._transport.write(self._build_mssp_payload())
        except Exception:
            log.debug("MSSP: send failed on new connection (non-critical)", exc_info=True)

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

        # Capture the peer IP for the pre-auth connect/create throttle. Telnet
        # is a raw TCP socket (no X-Forwarded-For), so the transport peername
        # is the authoritative, un-spoofable source address.
        try:
            peer = writer.get_extra_info("peername")
            if peer:
                session.client_ip = peer[0]
        except Exception:
            log.debug("telnet: peername capture failed", exc_info=True)

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
