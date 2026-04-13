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


# ── NPC role classification (Ground UX Drop 1) ──

def _classify_npc_role(npc_row: dict) -> str:
    """Determine the display role of an NPC from its ai_config_json.

    Returns one of: 'hostile', 'guard', 'trainer', 'vendor', 'quest',
    'mechanic', 'bartender', 'neutral'.
    """
    ai_cfg = npc_row.get("ai_config_json", "{}")
    if isinstance(ai_cfg, str):
        try:
            ai_cfg = json.loads(ai_cfg)
        except Exception:
            ai_cfg = {}

    # Check explicit hostile flag first
    if ai_cfg.get("hostile"):
        return "hostile"

    # Check for trainer
    if ai_cfg.get("trainer"):
        return "trainer"

    # Check faction-based roles
    name_lower = npc_row.get("name", "").lower()

    # Guard / patrol detection
    if any(kw in name_lower for kw in ("guard", "patrol", "trooper", "sentry",
                                        "soldier", "enforcer")):
        return "guard"

    # Mechanic / shipwright detection
    if any(kw in name_lower for kw in ("mechanic", "shipwright", "technician",
                                        "engineer")):
        return "mechanic"

    # Bartender / cantina staff
    if any(kw in name_lower for kw in ("bartender", "barkeep", "wuher")):
        return "bartender"

    # Combat behavior suggests guard role
    combat_beh = (ai_cfg.get("combat_behavior") or "").lower()
    if combat_beh in ("aggressive", "patrol"):
        return "guard"

    return "neutral"


def _npc_actions(role: str, hostile: bool, in_combat: bool,
                 security_level: str) -> list:
    """Return list of valid action command strings for an NPC based on context."""
    actions = ["look"]

    if role == "hostile":
        actions.append("talk")
        if not in_combat:
            actions.append("attack")
    elif role == "guard":
        actions.append("talk")
        if not in_combat and security_level != "secured":
            actions.append("attack")
    elif role == "trainer":
        actions.extend(["talk", "train"])
    elif role == "vendor":
        actions.extend(["talk", "buy"])
    elif role == "mechanic":
        actions.extend(["talk", "repair"])
    elif role == "bartender":
        actions.append("talk")
    else:
        actions.append("talk")
        if not in_combat and security_level != "secured":
            actions.append("attack")

    return actions


def _derive_room_services(npcs: list, vendor_droids: list,
                          room_props: dict) -> list:
    """Derive service type tags available in the current room.

    Returns a list of strings like ['vendor', 'trainer', 'cantina'].
    """
    services = []

    if vendor_droids:
        services.append("vendor")

    roles_present = set()
    for npc in npcs:
        role = _classify_npc_role(npc)
        roles_present.add(role)

    if "trainer" in roles_present:
        services.append("trainer")
    if "mechanic" in roles_present:
        services.append("mechanic")
    if "bartender" in roles_present:
        services.append("cantina")

    env = (room_props.get("environment") or "").lower()
    if env in ("cantina", "bar", "tavern") and "cantina" not in services:
        services.append("cantina")
    if env in ("medical", "medbay", "hospital"):
        services.append("medical")
    if env in ("docking", "hangar", "spaceport", "bay"):
        services.append("docking")
    if env in ("workshop", "forge", "crafting"):
        services.append("crafting")

    return services


def _build_loadout(char: dict) -> dict:
    """Build loadout summary from character equipment and inventory.

    Returns dict with weapon, armor, and consumables fields.
    """
    loadout = {
        "weapon": None,
        "armor": None,
        "consumables": [],
    }

    try:
        equip = char.get("equipment")
        if equip:
            if isinstance(equip, str):
                equip = json.loads(equip)

            weapon_data = equip.get("weapon")
            if weapon_data and isinstance(weapon_data, dict):
                loadout["weapon"] = {
                    "name": weapon_data.get("name", ""),
                    "damage": weapon_data.get("damage", ""),
                    "type": weapon_data.get("type", ""),
                }

            armor_data = equip.get("armor")
            if armor_data and isinstance(armor_data, dict):
                loadout["armor"] = {
                    "name": armor_data.get("name", ""),
                    "location": armor_data.get("location", ""),
                    "bonus": armor_data.get("bonus", ""),
                }
    except Exception:
        pass

    try:
        inv = char.get("inventory")
        if inv:
            if isinstance(inv, str):
                inv = json.loads(inv)
            if isinstance(inv, list):
                consumable_types = {}
                for item in inv:
                    if isinstance(item, dict):
                        itype = (item.get("type") or "").lower()
                        iname = item.get("name", "Unknown")
                        if itype in ("healing", "medical", "stim", "grenade",
                                     "consumable", "tool"):
                            key = iname
                            if key not in consumable_types:
                                consumable_types[key] = {
                                    "name": iname, "count": 0, "type": itype
                                }
                            consumable_types[key]["count"] += 1
                        elif any(kw in iname.lower() for kw in
                                 ("medpac", "stim", "grenade", "bacta",
                                  "ration", "tool kit")):
                            key = iname
                            if key not in consumable_types:
                                ctype = ("healing"
                                         if "med" in iname.lower()
                                            or "bacta" in iname.lower()
                                         else "consumable")
                                consumable_types[key] = {
                                    "name": iname, "count": 0, "type": ctype
                                }
                            consumable_types[key]["count"] += 1
                sorted_consumables = sorted(
                    consumable_types.values(),
                    key=lambda c: (
                        0 if c["type"] == "healing" else
                        1 if c["type"] == "stim" else
                        2 if c["type"] == "grenade" else 3,
                        -c["count"]
                    )
                )
                loadout["consumables"] = sorted_consumables[:4]
    except Exception:
        pass

    return loadout


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

        Capped at 80 for both Telnet and WebSocket — classic MUSH terminal
        width. This ensures decorative bars, prose, and sheet output all
        line up consistently regardless of browser window size.
        """
        return min(self.width, 80)

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

    async def send_prose(self, text: str, indent: str = "  "):
        """Send a prose paragraph.

        WebSocket: send as a single line with indent prefix — the browser
        reflows the text naturally, giving a true paragraph with no
        artificial mid-sentence line breaks.

        Telnet: server-side word-wrap at wrap_width, one send_line per
        wrapped chunk (classic terminal behaviour).
        """
        import textwrap as _tw
        if self.protocol == Protocol.WEBSOCKET:
            await self.send_line(f"{indent}{text}")
        else:
            w = self.wrap_width - len(indent)
            for chunk in _tw.wrap(text, width=max(20, w)):
                await self.send_line(f"{indent}{chunk}")

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

        Ground UX Drop 1: adds room_description, room_services,
        enhanced NPC entries with role/hostile/actions, and loadout.
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
            # Ground UX Drop 1 — new fields
            "room_description": "",
            "room_services": [],
            "loadout": None,
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

        # Build loadout for sidebar (Ground UX Drop 1)
        try:
            hud["loadout"] = _build_loadout(char)
        except Exception:
            log.warning("send_hud_update: loadout build failed", exc_info=True)

        # ── Room data (exits, description, zone, services) ──

        # Cache the room row — we read it in multiple blocks below
        _room_row = None
        _room_props = {}

        if db and room_id:
            try:
                _room_row = await db.get_room(room_id)
            except Exception:
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
                if not hud["room_name"] and _room_row:
                    hud["room_name"] = _room_row.get("name", "")
            except Exception:
                pass  # Non-critical — HUD just won't show exits

        # Room description for context panel (Ground UX Drop 1)
        if _room_row:
            desc = _room_row.get("desc_long") or _room_row.get("desc_short") or ""
            hud["room_description"] = desc

        # Resolve zone name and type for ambient mood
        if db and room_id and _room_row:
            try:
                if _room_row.get("zone_id"):
                    zone = await db.get_zone(_room_row["zone_id"])
                    if zone:
                        hud["zone_name"] = zone.get("name", "")
                        # Zone type from properties.environment
                        props = zone.get("properties", "{}")
                        if isinstance(props, str):
                            try:
                                props = json.loads(props)
                            except Exception:
                                props = {}
                        hud["zone_type"] = props.get("environment", "")
            except Exception:
                pass  # Non-critical — mood just stays default

        # Parse room properties for service detection
        if _room_row:
            raw_props = _room_row.get("properties", "{}")
            if isinstance(raw_props, str):
                try:
                    _room_props = json.loads(raw_props)
                except Exception:
                    _room_props = {}
            elif isinstance(raw_props, dict):
                _room_props = raw_props

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
        security_level = "contested"
        if db and room_id:
            try:
                from engine.security import get_effective_security
                sec = await get_effective_security(room_id, db, character=char)
                security_level = sec.value
                hud["security_level"] = security_level
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
        # Ground UX Drop 1: enhanced with NPC roles, hostile flags, and
        # context-sensitive action lists
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

                # Detect if combat is active in this room
                _in_combat = False
                try:
                    from engine.combat import get_combat
                    _in_combat = get_combat(room_id) is not None
                except Exception:
                    pass

                # Build enhanced NPC entries (Ground UX Drop 1)
                npc_entries = []
                for n in npcs:
                    role = _classify_npc_role(n)
                    ai_cfg = n.get("ai_config_json", "{}")
                    if isinstance(ai_cfg, str):
                        try:
                            ai_cfg = json.loads(ai_cfg)
                        except Exception:
                            ai_cfg = {}
                    is_hostile = ai_cfg.get("hostile", False)
                    actions = _npc_actions(role, is_hostile, _in_combat,
                                          security_level)
                    npc_entries.append({
                        "id": n["id"],
                        "name": n["name"],
                        "role": role,
                        "hostile": is_hostile,
                        "actions": actions,
                    })

                hud["room_contents"] = {
                    "npcs": npc_entries,
                    "players": [
                        {"id": s.character["id"], "name": s.character["name"]}
                        for s in session_mgr.sessions_in_room(room_id)
                        if s.character and s.character.get("id") != char.get("id")
                    ] if session_mgr else [],
                    "vendor_droids": vendor_droids,
                }

                # Derive room services (Ground UX Drop 1)
                hud["room_services"] = _derive_room_services(
                    npcs, vendor_droids, _room_props)

            except Exception:
                pass  # Non-critical

        # Area map for context panel minimap (Ground UX Drop 2)
        if db and room_id:
            try:
                from engine.area_map import build_area_map
                hud["area_map"] = await build_area_map(room_id, db, depth=2)
            except Exception:
                log.warning("send_hud_update: area_map build failed",
                            exc_info=True)

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
