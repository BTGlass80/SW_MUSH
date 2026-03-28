"""
Session - the protocol-agnostic connection abstraction.

Every connected client gets a Session, regardless of whether they
arrived via Telnet or WebSocket. The rest of the codebase only
interacts with Session objects, never raw sockets.
"""
import asyncio
import enum
import json
import logging
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from db.database import Database

log = logging.getLogger(__name__)


class Protocol(enum.Enum):
    TELNET = "telnet"
    WEBSOCKET = "websocket"


class SessionState(enum.Enum):
    """Tracks where the player is in the login flow."""
    CONNECTED = "connected"          # Just connected, at login screen
    AUTHENTICATED = "authenticated"  # Logged in, selecting/creating character
    IN_GAME = "in_game"              # Playing with an active character
    DISCONNECTING = "disconnecting"


class Session:
    """
    Unified session wrapping either a Telnet or WebSocket connection.

    Attributes:
        protocol:   Which transport this session uses.
        state:      Current login/play state.
        account:    Account dict after authentication (None before login).
        character:  Active character dict (None until selected).
        width:      Terminal width (negotiated or default).
        height:     Terminal height (negotiated or default).
    """

    _next_id = 1

    def __init__(
        self,
        protocol: Protocol,
        send_callback,
        close_callback,
        width: int = 80,
        height: int = 24,
    ):
        self.id = Session._next_id
        Session._next_id += 1
        self.protocol = protocol
        self.state = SessionState.CONNECTED
        self.account: Optional[dict] = None
        self.character: Optional[dict] = None
        self.width = width
        self.height = height
        self.connected_at = time.time()
        self.last_activity = time.time()

        # Transport callbacks (set by protocol handler)
        self._send = send_callback
        self._close = close_callback

        # Input queue - protocol handlers push lines here
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()

    def __repr__(self):
        name = self.character["name"] if self.character else "anonymous"
        return f"<Session #{self.id} {self.protocol.value} {name}>"

    # ── Output ──

    async def send(self, text: str):
        """Send text to the client. Handles protocol-specific encoding."""
        self.last_activity = time.time()
        try:
            if self.protocol == Protocol.TELNET:
                await self._send(text)
            else:
                # WebSocket: send as JSON message
                await self._send(json.dumps({"type": "text", "data": text}))
        except Exception as e:
            log.warning("Send failed on %s: %s", self, e)

    async def send_line(self, text: str = ""):
        """Send text followed by a newline."""
        await self.send(text + "\r\n")

    async def send_prompt(self, prompt: str = "> "):
        """Send a prompt string (no trailing newline)."""
        await self.send(prompt)

    async def send_json(self, msg_type: str, data: dict):
        """Send a typed JSON message (primarily for WebSocket clients)."""
        if self.protocol == Protocol.WEBSOCKET:
            try:
                await self._send(json.dumps({"type": msg_type, **data}))
            except Exception as e:
                log.warning("JSON send failed on %s: %s", self, e)
        else:
            # Telnet fallback: render as text
            if msg_type == "room_description":
                await self.send_line(data.get("text", ""))
            elif msg_type == "combat_log":
                await self.send_line(data.get("text", ""))
            else:
                await self.send_line(str(data))

    # ── Input ──

    def feed_input(self, line: str):
        """Called by protocol handler when a line of input arrives."""
        self.last_activity = time.time()
        self._input_queue.put_nowait(line)

    async def receive(self) -> str:
        """Await the next line of input from the player."""
        return await self._input_queue.get()

    # ── Lifecycle ──

    async def close(self):
        """Gracefully disconnect this session."""
        self.state = SessionState.DISCONNECTING
        try:
            await self.send_line("Disconnecting. May the Force be with you.")
            await self._close()
        except Exception:
            pass
        log.info("Session closed: %s", self)

    @property
    def is_idle(self) -> bool:
        """Check if this session has been idle too long."""
        return (time.time() - self.last_activity) > 3600

    @property
    def is_authenticated(self) -> bool:
        return self.state in (SessionState.AUTHENTICATED, SessionState.IN_GAME)

    @property
    def is_in_game(self) -> bool:
        return self.state == SessionState.IN_GAME


class SessionManager:
    """
    Central registry of all active sessions.
    Provides lookup by session ID, account, character, and room.
    """

    def __init__(self):
        self._sessions: dict[int, Session] = {}

    def add(self, session: Session):
        self._sessions[session.id] = session
        log.info("Session added: %s (total: %d)", session, len(self._sessions))

    def remove(self, session: Session):
        self._sessions.pop(session.id, None)
        log.info("Session removed: %s (total: %d)", session, len(self._sessions))

    def get(self, session_id: int) -> Optional[Session]:
        return self._sessions.get(session_id)

    @property
    def all(self) -> list[Session]:
        return list(self._sessions.values())

    @property
    def count(self) -> int:
        return len(self._sessions)

    def find_by_account(self, account_id: int) -> Optional[Session]:
        """Find an active session for a given account."""
        for s in self._sessions.values():
            if s.account and s.account["id"] == account_id:
                return s
        return None

    def find_by_character(self, character_id: int) -> Optional[Session]:
        """Find the session associated with a character."""
        for s in self._sessions.values():
            if s.character and s.character["id"] == character_id:
                return s
        return None

    def sessions_in_room(self, room_id: int) -> list[Session]:
        """Get all sessions with characters in a given room."""
        return [
            s for s in self._sessions.values()
            if s.is_in_game and s.character and s.character.get("room_id") == room_id
        ]

    async def broadcast(self, text: str, exclude: Optional[Session] = None):
        """Send a message to all in-game sessions."""
        for s in self._sessions.values():
            if s.is_in_game and s is not exclude:
                await s.send_line(text)

    async def broadcast_to_room(
        self, room_id: int, text: str, exclude: Optional[Session] = None
    ):
        """Send a message to all sessions in a specific room."""
        for s in self.sessions_in_room(room_id):
            if s is not exclude:
                await s.send_line(text)
