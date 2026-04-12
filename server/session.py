# -*- coding: utf-8 -*-
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


# ── Wound level → display name ──

_WOUND_NAMES = {
    0: "healthy",
    1: "stunned",
    2: "wounded",
    3: "wounded twice",
    4: "incapacitated",
    5: "mortally wounded",
    6: "dead",
}

def _wound_name(level: int) -> str:
    """Convert numeric wound level to display name for HUD."""
    return _WOUND_NAMES.get(level, "healthy")


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
        # v22 audit S15: parsed Character object cache.
        # Lazily populated on first access via get_char_obj().
        # Invalidated on save_character() by setting to None.
        self._char_obj = None
        self.width = width
        self.height = height
        self.connected_at = time.time()
        self.last_activity = time.time()

        # Transport callbacks (set by protocol handler)
        self._send = send_callback
        self._close = close_callback

        # Input queue - protocol handlers push lines here
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()

    @property
    def wrap_width(self) -> int:
        """Text wrapping width.

        Telnet: capped at 78 for classic terminal readability.
        WebSocket: uses full reported width (Fmt.prose_width caps at
        MAX_PROSE_WIDTH=100 for readability on ultra-wide viewports).
        """
        if self.protocol == Protocol.WEBSOCKET:
            return self.width   # Client sends resize; Fmt caps prose at 100
        return min(self.width, 78)

    def __repr__(self):
        name = self.character["name"] if self.character else "anonymous"
        return f"<Session #{self.id} {self.protocol.value} {name}>"

    def get_char_obj(self):
        """
        Get a parsed Character object from the raw character dict.

        v22 audit S15: lazily cached — parsed once, reused until
        invalidated by invalidate_char_obj() (called after save_character).
        Eliminates repeated json.loads() of attributes/skills/equipment.

        Returns None if no character is attached.
        """
        if self.character is None:
            return None
        if self._char_obj is None:
            from engine.character import Character
            self._char_obj = Character.from_db_dict(self.character)
        return self._char_obj

    def invalidate_char_obj(self):
        """Clear the cached Character object. Call after save_character()."""
        self._char_obj = None

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
            # Telnet fallback: render as text (or silently drop structured messages)
            if msg_type == "room_description":
                await self.send_line(data.get("text", ""))
            elif msg_type == "combat_log":
                await self.send_line(data.get("text", ""))
            elif msg_type in ("combat_state", "hud_update", "world_event",
                              "news_event", "space_state"):
                pass  # Telnet clients ignore structured JSON messages
            else:
                await self.send_line(str(data))

    async def send_hud_update(self, db=None, session_mgr=None):
        """
        Send structured HUD data to WebSocket clients.

        Reads current character state from self.character dict and
        optionally fetches exits from DB. Telnet clients ignore this.
        """
        if self.protocol != Protocol.WEBSOCKET:
            return
        if not self.character:
            return

        char = self.character
        room_id = char.get("room_id")

        # Build HUD payload
        hud = {
            "character_id": char.get("id"),
            "name": char.get("name", ""),
            "wound_level": char.get("wound_level", 0),
            "wound_name": _wound_name(char.get("wound_level", 0)),
            "credits": char.get("credits", 0),
            "room_name": char.get("_room_name", ""),
            "room_id": room_id,
            "force_points": char.get("force_points", 0),
            "character_points": char.get("character_points", 0),
            "dark_side_points": char.get("dark_side_points", 0),
            "force_sensitive": bool(char.get("force_sensitive", False)),
            "exits": [],
            "zone_name": "",
            "zone_type": "",
            "alert_level": "",
            "alert_faction": "",
        }

        # Equipped weapon for sidebar display
        try:
            equip = char.get("equipment")
            if equip:
                if isinstance(equip, str):
                    import json as _json
                    equip = _json.loads(equip)
                weapon_data = equip.get("weapon")
                if weapon_data and isinstance(weapon_data, dict):
                    hud["equipped_weapon"] = weapon_data.get("name", "")
        except Exception:
            log.warning("send_hud_update: unhandled exception", exc_info=True)
            pass

        # Fetch exits if we have a DB handle
        if db and room_id:
            try:
                exits = await db.get_exits(room_id)
                # Filter hidden faction exits (e.g. Rebel safehouse doors)
                try:
                    from engine.housing import is_exit_visible
                    exits = [e for e in exits
                             if await is_exit_visible(db, e, char)]
                except Exception:
                    log.warning("send_hud_update: unhandled exception", exc_info=True)
                    pass
                hud["exits"] = [
                    {
                        "dir": e["direction"],
                        "label": (e.get("name") or "").strip() or e["direction"],
                    }
                    for e in exits
                ]
                # Also grab room name from DB if not cached
                if not hud["room_name"]:
                    room = await db.get_room(room_id)
                    if room:
                        hud["room_name"] = room.get("name", "")
            except Exception:
                pass  # Non-critical — HUD just won't show exits

        # Resolve zone name and type for ambient mood
        if db and room_id:
            try:
                room = await db.get_room(room_id)
                if room and room.get("zone_id"):
                    zone = await db.get_zone(room["zone_id"])
                    if zone:
                        hud["zone_name"] = zone.get("name", "")
                        # Zone type from properties.environment
                        props = zone.get("properties", "{}")
                        if isinstance(props, str):
                            import json as _json
                            try:
                                props = _json.loads(props)
                            except Exception:
                                props = {}
                        hud["zone_type"] = props.get("environment", "")
            except Exception:
                pass  # Non-critical — mood just stays default — HUD just won't show exits


        # Resolve alert level from Director AI
        try:
            from engine.director import get_director
            director = get_director()
            zone_key = hud.get("zone_type", "")
            if zone_key:
                alert = director.get_alert_level(zone_key)
                hud["alert_level"] = alert.value if alert else ""
                # Determine dominant faction
                zs = director.get_zone_state(zone_key)
                if zs:
                    factions = {"imperial": zs.imperial, "rebel": zs.rebel,
                                "criminal": zs.criminal, "independent": zs.independent}
                    hud["alert_faction"] = max(factions, key=factions.get)
        except Exception:
            pass  # Non-critical — alert badge just won't show

        # Resolve security level
        if db and room_id:
            try:
                from engine.security import get_effective_security
                sec = await get_effective_security(room_id, db, character=char)
                hud["security_level"] = sec.value
            except Exception:
                hud["security_level"] = "contested"

        # Check if this is a housing room owned by the character
        hud["is_housing"] = False
        if db and room_id:
            try:
                from engine.housing import get_housing_for_room
                h = await get_housing_for_room(db, room_id)
                if h and h.get("char_id") == char.get("id"):
                    hud["is_housing"] = True
            except Exception:
                log.warning("send_hud_update: unhandled exception", exc_info=True)
                pass

        # Territory claim badge (Drop 6E)
        hud["territory_claim"] = None
        hud["contest_active"] = False
        if db and room_id:
            try:
                from engine.territory import get_claim, get_active_contest, get_room_zone_id
                _tc = await get_claim(db, room_id)
                if _tc:
                    hud["territory_claim"] = {
                        "org_code": _tc["org_code"],
                        "org_name": _tc["org_code"].replace("_", " ").title(),
                        "has_guard": bool(_tc.get("guard_npc_id")),
                    }
                    _zone_id = await get_room_zone_id(db, room_id)
                    if _zone_id:
                        _contest = await get_active_contest(db, _zone_id)
                        if _contest:
                            import time as _time
                            hud["contest_active"] = True
                            hud["contest_challenger"] = _contest["challenger_org_code"].replace("_", " ").title()
                            hud["contest_ends"] = max(0, int(_contest["ends_at"] - _time.time()))
            except Exception:
                pass  # Non-critical — territory badge just won't show

        # Room contents for clickable sidebar panel
        if db and room_id:
            try:
                npcs = await db.get_npcs_in_room(room_id)
                # Vendor droids in room — for shop browse sidebar panel
                vendor_droids = []
                try:
                    raw_droids = await db.get_objects_in_room(room_id, "vendor_droid")
                    from engine.vendor_droids import _load_data
                    for d in raw_droids:
                        data = _load_data(d)
                        inventory = data.get("inventory", [])
                        vendor_droids.append({
                            "id": d["id"],
                            "name": data.get("shop_name") or d.get("name", "Vendor Droid"),
                            "desc": data.get("shop_desc", ""),
                            "tier": data.get("tier_key", "gn4"),
                            "item_count": len(inventory),
                            "inventory": [
                                {
                                    "slot": i + 1,
                                    "name": slot.get("item_name", "Unknown"),
                                    "price": slot.get("price", 0),
                                    "qty": slot.get("quantity", 1),
                                    "quality": slot.get("quality", 0),
                                    "crafter": slot.get("crafter", ""),
                                }
                                for i, slot in enumerate(inventory)
                                if slot.get("quantity", 0) > 0
                            ],
                        })
                except Exception:
                    pass  # Non-critical, just omit droids
                hud["room_contents"] = {
                    "npcs": [
                        {"id": n["id"], "name": n["name"]}
                        for n in npcs
                    ],
                    "players": [
                        {"id": s.character["id"], "name": s.character["name"]}
                        for s in session_mgr.sessions_in_room(room_id)
                        if s.character and s.character.get("id") != char.get("id")
                    ] if session_mgr else [],
                    "vendor_droids": vendor_droids,
                }
            except Exception:
                pass  # Non-critical

        try:
            await self._send(json.dumps({"type": "hud_update", **hud}))
        except Exception as e:
            log.warning("HUD update failed on %s: %s", self, e)

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
            log.warning("close: unhandled exception", exc_info=True)
            pass
        log.info("Session closed: %s", self)

    @property
    def is_idle(self) -> bool:
        """Check if this session has been idle too long (uses default 3600s).
        Prefer is_idle_for(seconds) when you have a Config available.
        """
        return self.is_idle_for(3600)

    def is_idle_for(self, timeout_seconds: int) -> bool:
        """Check if this session has been idle longer than timeout_seconds."""
        return (time.time() - self.last_activity) > timeout_seconds

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
        self, room_id: int, text: str,
        exclude=None,
    ):
        """Send text to all sessions in a room.

        Args:
            exclude: Session object, list of character IDs to skip, or None.

        v22 audit S16: asyncio.gather isolates slow telnet clients so one
        backed-up send queue can't stall the broadcast for everyone.
        """
        excluded_ids: set[int] = set()
        excluded_sess: Optional["Session"] = None
        if isinstance(exclude, list):
            excluded_ids = set(exclude)
        elif exclude is not None:
            excluded_sess = exclude

        targets = []
        for s in self.sessions_in_room(room_id):
            if excluded_sess is not None and s is excluded_sess:
                continue
            if s.character and s.character.get("id") in excluded_ids:
                continue
            targets.append(s.send_line(text))

        if targets:
            await asyncio.gather(*targets, return_exceptions=True)

    async def broadcast_json_to_room(
        self, room_id: int, msg_type: str, data: dict
    ):
        """Send a typed JSON message to all WebSocket sessions in a room.

        Telnet sessions silently ignore this call.
        Used for combat_state, space_state, and other structured updates.
        """
        targets = [s.send_json(msg_type, data) for s in self.sessions_in_room(room_id)]
        if targets:
            await asyncio.gather(*targets, return_exceptions=True)

    async def broadcast_chat(
        self, channel: str, from_name: str, text: str,
        room_id: int = None, exclude=None,
    ):
        """Send a structured chat message to WebSocket clients.

        Sends a parallel 'chat' JSON message alongside normal text output.
        WebSocket clients route this to the appropriate comms tab.
        Telnet clients ignore it entirely (they already got the text via
        broadcast_to_room or send_line).

        channel: 'ic' | 'ooc' | 'sys'
        """
        payload = {"channel": channel, "from": from_name, "text": text}
        if room_id is not None:
            excluded_ids: set[int] = set()
            excluded_sess = None
            if isinstance(exclude, list):
                excluded_ids = set(exclude)
            elif exclude is not None:
                excluded_sess = exclude
            for s in self.sessions_in_room(room_id):
                if excluded_sess is not None and s is excluded_sess:
                    continue
                if s.character and s.character.get("id") in excluded_ids:
                    continue
                await s.send_json("chat", payload)
        else:
            # Broadcast to all connected sessions
            for s in self._sessions:
                await s.send_json("chat", payload)
