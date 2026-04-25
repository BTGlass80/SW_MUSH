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
    except Exception as _e:
        log.debug("silent except in server/session.py:197: %s", _e, exc_info=True)

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
    except Exception as _e:
        log.debug("silent except in server/session.py:242: %s", _e, exc_info=True)

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

        # Track last sent credits value to detect changes for credit_event (Drop 9)
        self._last_sent_credits: Optional[int] = None

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
        """Send a prose paragraph with word-wrapping.

        Both Telnet and WebSocket get server-side word-wrap so that
        room descriptions display as readable paragraphs in the
        terminal output pane (not one enormous line).
        """
        import textwrap as _tw
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
            elif msg_type == "ambient_bark":
                # Telnet gets the bark as plain styled text
                text = data.get("text", "")
                if text:
                    await self.send_line(text)
            elif msg_type in ("combat_state", "hud_update", "world_event",
                              "news_event", "space_state", "rep_change",
                              "rank_up", "chargen_start"):
                pass  # Telnet clients ignore structured JSON messages
            else:
                await self.send_line(str(data))

    # ── HUD helper methods (Phase 3 C2: decomposed from send_hud_update) ────

    def _hud_base(self) -> dict:
        """Build the base HUD payload from character state. No DB needed."""
        char = self.character
        # Drop C (F8): surface active stun count for the stun-counter strip.
        # Stored as runtime-only state on the Character dataclass (stun_timers
        # list); active_stun_count is a derived property. Lazily fetched via
        # cached get_char_obj() — no extra DB hit.
        active_stun_count = 0
        try:
            char_obj = self.get_char_obj()
            if char_obj is not None:
                active_stun_count = char_obj.active_stun_count
        except Exception:
            active_stun_count = 0  # fail open — strip just stays hidden
        hud = {
            "character_id": char.get("id"),
            "name": char.get("name", ""),
            "wound_level": char.get("wound_level", 0),
            "wound_name": _wound_name(char.get("wound_level", 0)),
            "credits": char.get("credits", 0),
            "room_name": char.get("_room_name", ""),
            "room_id": char.get("room_id"),
            "force_points": char.get("force_points", 0),
            "character_points": char.get("character_points", 0),
            "dark_side_points": char.get("dark_side_points", 0),
            "force_sensitive": bool(char.get("force_sensitive", False)),
            "active_stun_count": active_stun_count,
            "exits": [],
            "zone_name": "",
            "zone_type": "",
            "alert_level": "",
            "alert_faction": "",
            "room_description": "",
            "room_services": [],
            "loadout": None,
        }
        # Attributes (and Force skills if sensitive). Stored as JSON in DB,
        # values are dice strings like "3D+1". The web client renders them
        # directly into the operative panel; absence here leaves the panel
        # showing em-dashes (the long-standing visible bug).
        try:
            attrs_raw = char.get("attributes", "{}")
            if isinstance(attrs_raw, str):
                attrs_dict = json.loads(attrs_raw) if attrs_raw else {}
            elif isinstance(attrs_raw, dict):
                attrs_dict = attrs_raw
            else:
                attrs_dict = {}
        except (json.JSONDecodeError, TypeError):
            attrs_dict = {}
        # Surface the six core attributes by their full names — the client
        # reads data.attributes.dexterity etc. (client.html line ~3413).
        hud["attributes"] = {
            "dexterity":  attrs_dict.get("dexterity",  ""),
            "knowledge":  attrs_dict.get("knowledge",  ""),
            "mechanical": attrs_dict.get("mechanical", ""),
            "perception": attrs_dict.get("perception", ""),
            "strength":   attrs_dict.get("strength",   ""),
            "technical":  attrs_dict.get("technical",  ""),
        }
        # Force skills — only meaningful for sensitive PCs, but always include
        # the keys (empty string when absent) so client code doesn't have to
        # null-check shape.
        hud["force_skills"] = {
            "control": attrs_dict.get("control", ""),
            "sense":   attrs_dict.get("sense",   ""),
            "alter":   attrs_dict.get("alter",   ""),
        }
        return hud

    def _hud_equipped_weapon(self, hud: dict) -> None:
        """Add equipped weapon name to HUD from character equipment."""
        equip = self.character.get("equipment")
        if equip:
            if isinstance(equip, str):
                equip = json.loads(equip)
            weapon_data = equip.get("weapon")
            if weapon_data and isinstance(weapon_data, dict):
                hud["equipped_weapon"] = weapon_data.get("name", "")

    def _hud_loadout(self, hud: dict) -> None:
        """Build loadout summary for sidebar display."""
        hud["loadout"] = _build_loadout(self.character)

    async def _hud_room_row(self, db, room_id) -> tuple:
        """Fetch and cache the room row + parsed properties. Returns (row, props)."""
        room_row = None
        room_props = {}
        if db and room_id:
            room_row = await db.get_room(room_id)
        if room_row:
            raw_props = room_row.get("properties", "{}")
            if isinstance(raw_props, str):
                try:
                    room_props = json.loads(raw_props)
                except Exception:
                    room_props = {}
            elif isinstance(raw_props, dict):
                room_props = raw_props
        return room_row, room_props

    async def _hud_exits(self, hud: dict, db, room_id, room_row) -> None:
        """Fetch exits, filter hidden faction doors, populate HUD."""
        exits = await db.get_exits(room_id)
        try:
            from engine.housing import is_exit_visible
            exits = [e for e in exits
                     if await is_exit_visible(db, e, self.character)]
        except Exception:
            log.warning("_hud_exits: exit visibility filter failed", exc_info=True)
        hud["exits"] = [
            {
                "dir": e["direction"],
                "label": (e.get("name") or "").strip() or e["direction"],
            }
            for e in exits
        ]
        if not hud["room_name"] and room_row:
            hud["room_name"] = room_row.get("name", "")

    async def _hud_zone(self, hud: dict, db, room_row) -> None:
        """Resolve zone name, type, and environment from room's zone."""
        zone_id = room_row.get("zone_id") if room_row else None
        if not zone_id:
            return
        zone = await db.get_zone(zone_id)
        if zone:
            hud["zone_name"] = zone.get("name", "")
            props = zone.get("properties", "{}")
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except Exception:
                    props = {}
            hud["zone_type"] = props.get("environment", "")

    def _hud_room_description(self, hud: dict, room_row) -> None:
        """Set room description from the room row."""
        if room_row:
            desc = room_row.get("desc_long") or room_row.get("desc_short") or ""
            hud["room_description"] = desc

    def _hud_alert_level(self, hud: dict) -> None:
        """Resolve Director AI alert level and dominant faction."""
        from engine.director import get_director
        director = get_director()
        zone_key = hud.get("zone_type", "")
        if zone_key:
            alert = director.get_alert_level(zone_key)
            hud["alert_level"] = alert.value if alert else ""
            zs = director.get_zone_state(zone_key)
            if zs:
                factions = {"imperial": zs.imperial, "rebel": zs.rebel,
                            "criminal": zs.criminal, "independent": zs.independent}
                hud["alert_faction"] = max(factions, key=factions.get)

    async def _hud_security(self, hud: dict, db, room_id) -> str:
        """Resolve effective security level. Returns the level string."""
        security_level = "contested"
        if db and room_id:
            from engine.security import get_effective_security
            sec = await get_effective_security(room_id, db, character=self.character)
            security_level = sec.value
        hud["security_level"] = security_level
        return security_level

    async def _hud_housing(self, hud: dict, db, room_id, room_row) -> None:
        """Add housing panel data if current room is a housing room."""
        hud["is_housing"] = False
        hud["housing_info"] = None
        if not (db and room_id and room_row and room_row.get("housing_id")):
            return
        from engine.housing import get_housing_for_room, get_housing_hud_info
        h = await get_housing_for_room(db, room_id)
        if h:
            hud["is_housing"] = (h.get("char_id") == self.character.get("id"))
            hi = await get_housing_hud_info(db, self.character, room_id)
            if hi:
                hud["housing_info"] = hi

    async def _hud_territory(self, hud: dict, db, room_id) -> None:
        """Add territory claim badge and contest status."""
        hud["territory_claim"] = None
        hud["contest_active"] = False
        if not (db and room_id):
            return
        from engine.territory import get_claim, get_active_contest, get_room_zone_id
        tc = await get_claim(db, room_id)
        if tc:
            hud["territory_claim"] = {
                "org_code": tc["org_code"],
                "org_name": tc["org_code"].replace("_", " ").title(),
                "has_guard": bool(tc.get("guard_npc_id")),
            }
            zone_id = await get_room_zone_id(db, room_id)
            if zone_id:
                contest = await get_active_contest(db, zone_id)
                if contest:
                    hud["contest_active"] = True
                    hud["contest_challenger"] = contest["challenger_org_code"].replace("_", " ").title()
                    hud["contest_ends"] = max(0, int(contest["ends_at"] - time.time()))

    async def _hud_cp_progress(self, hud: dict, db, char_id) -> None:
        """Add CP progression data for sidebar progress bar."""
        hud["cp_progress"] = None
        if not (db and char_id):
            return
        from engine.cp_engine import get_cp_engine, TICKS_PER_CP, WEEKLY_CAP_TICKS
        cp_eng = get_cp_engine()
        status = await cp_eng.get_status(db, char_id)
        ticks_to_next = status.get("ticks_to_next_cp", TICKS_PER_CP)
        hud["cp_progress"] = {
            "ticks_to_next": ticks_to_next,
            "ticks_per_cp": TICKS_PER_CP,
            "ticks_this_week": status.get("ticks_this_week", 0),
            "weekly_cap": WEEKLY_CAP_TICKS,
            "pct": round(
                (TICKS_PER_CP - ticks_to_next) / TICKS_PER_CP * 100
            ) if ticks_to_next < TICKS_PER_CP else 0,
        }

    async def _hud_reputation(self, hud: dict, db, char) -> None:
        """Add faction reputation overview for sidebar panel."""
        hud["reputation"] = {}
        if not (db and char.get("id")):
            return
        from engine.organizations import get_all_faction_reps
        hud["reputation"] = await get_all_faction_reps(char, db)

    async def _hud_zone_influence(self, hud: dict, db, room_row) -> None:
        """Add zone influence percentages for territory context panel."""
        hud["zone_influence"] = {}
        if not room_row:
            return
        zone_id = room_row.get("zone_id")
        if not zone_id:
            return
        from engine.territory import get_zone_territory_all
        inf = await get_zone_territory_all(db, zone_id)
        total = sum(inf.values()) or 1
        hud["zone_influence"] = {
            org: round(score / total * 100)
            for org, score in sorted(inf.items(), key=lambda x: -x[1])
            if score > 0
        }

    async def _hud_room_contents(self, hud: dict, db, room_id,
                                  room_props: dict, security_level: str,
                                  session_mgr) -> None:
        """Build room contents: NPCs, players, vendor droids, services."""
        char = self.character
        npcs = await db.get_npcs_in_room(room_id)

        # Vendor droids
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
            log.debug("_hud_room_contents: vendor droid load failed", exc_info=True)

        # Detect combat
        in_combat = False
        try:
            from engine.combat import get_combat
            in_combat = get_combat(room_id) is not None
        except Exception as e:
            log.debug("_hud_room_contents: combat check failed: %s", e)

        # Enhanced NPC entries
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
            actions = _npc_actions(role, is_hostile, in_combat, security_level)
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
        hud["room_services"] = _derive_room_services(npcs, vendor_droids, room_props)

    async def _hud_area_map(self, hud: dict, db, room_id) -> None:
        """Build area map for minimap context panel."""
        from engine.area_map import build_area_map
        hud["area_map"] = await build_area_map(room_id, db, depth=2)

    async def _hud_nearby_services(self, hud: dict, db, room_id) -> None:
        """BFS for nearby services within 4 rooms."""
        from engine.area_map import find_nearby_services
        hud["nearby_services"] = await find_nearby_services(
            room_id, db, depth=4, max_results=8)

    async def _hud_active_jobs(self, hud: dict, char) -> None:
        """Gather active mission, bounty, smuggling, and quest jobs."""
        jobs = []
        char_id_str = str(char["id"])

        # Active mission
        try:
            from engine.missions import get_mission_board, MissionStatus
            board = get_mission_board()
            for m in board._missions.values():
                if (m.accepted_by == char_id_str and
                        m.status == MissionStatus.ACCEPTED):
                    jobs.append({
                        "type": "mission",
                        "label": m.title,
                        "objective": m.destination or "",
                        "reward": m.reward,
                    })
                    break
        except Exception:
            log.debug("_hud_active_jobs: mission lookup failed", exc_info=True)

        # Active bounty
        try:
            from engine.bounty_board import get_bounty_board
            bboard = get_bounty_board()
            for c in bboard._contracts.values():
                if (getattr(c, "accepted_by", None) == char_id_str and
                        getattr(c, "status", "") == "accepted"):
                    jobs.append({
                        "type": "bounty",
                        "label": f"Bounty: {c.target_name}",
                        "target": getattr(c, "target_name", "Unknown"),
                        "reward": getattr(c, "reward", 0),
                    })
                    break
        except Exception:
            log.debug("_hud_active_jobs: bounty lookup failed", exc_info=True)

        # Active smuggling job
        try:
            from engine.smuggling import get_smuggling_board
            sboard = get_smuggling_board()
            for j in sboard._jobs.values():
                if (getattr(j, "accepted_by", None) == char_id_str and
                        getattr(j, "status", "") == "accepted"):
                    cargo = getattr(j, "cargo_type", "cargo")
                    dropoff = getattr(j, "dropoff_name", "?")
                    jobs.append({
                        "type": "smuggle",
                        "label": f"{cargo.title()} → {dropoff}",
                        "reward": getattr(j, "reward", 0),
                    })
                    break
        except Exception:
            log.debug("_hud_active_jobs: smuggling lookup failed", exc_info=True)

        # Active spacer quest step
        try:
            from engine.spacer_quest import get_step
            attrs = char.get("attributes", "{}")
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            qs = attrs.get("spacer_quest")
            if qs and isinstance(qs, dict):
                step_id = qs.get("step", 0)
                if 1 <= step_id <= 30:
                    step = get_step(step_id)
                    if step:
                        jobs.append({
                            "type": "quest",
                            "label": step.get("title", "Quest"),
                            "objective": step.get("objective_desc", ""),
                        })
        except Exception:
            log.debug("_hud_active_jobs: spacer quest lookup failed", exc_info=True)

        hud["active_jobs"] = jobs

    async def _hud_send_credit_event(self, hud: dict) -> None:
        """Send credit_event message if credits changed since last tick."""
        new_credits = hud.get("credits")
        if (new_credits is not None
                and self._last_sent_credits is not None
                and new_credits != self._last_sent_credits):
            delta = new_credits - self._last_sent_credits
            await self._send(json.dumps({
                "type": "credit_event",
                "credits": new_credits,
                "delta": delta,
            }))
        if new_credits is not None:
            self._last_sent_credits = new_credits

    async def _hud_sidebar_mail(self, db, char_id) -> None:
        """Send mail_status sidebar message."""
        mail_rows = await db.fetchall(
            """SELECT m.id, m.subject, m.sender_name as from_name,
                      mr.is_read
               FROM mail_recipients mr
               JOIN mail_messages m ON m.id = mr.message_id
               WHERE mr.char_id = ? AND mr.is_deleted = 0
               ORDER BY mr.is_read ASC, m.sent_at DESC
               LIMIT 5""",
            (char_id,)
        )
        unread_rows = await db.fetchall(
            "SELECT COUNT(*) as c FROM mail_recipients "
            "WHERE char_id = ? AND is_read = 0 AND is_deleted = 0",
            (char_id,)
        )
        unread = unread_rows[0]["c"] if unread_rows else 0
        await self._send(json.dumps({
            "type": "mail_status",
            "unread": unread,
            "messages": [
                {
                    "id": r["id"],
                    "subject": r["subject"] or "",
                    "from_name": r["from_name"] or "",
                    "is_read": bool(r["is_read"]),
                }
                for r in mail_rows
            ],
        }))

    async def _hud_sidebar_achievements(self, db, char_id) -> None:
        """Send achievements_status sidebar message."""
        from engine.achievements import get_achievements_status
        ach = await get_achievements_status(db, char_id)
        await self._send(json.dumps({
            "type": "achievements_status",
            "completed": ach.get("completed", 0),
            "total": ach.get("total", 0),
            "achievements": [
                {
                    "key": a["key"],
                    "name": a["name"],
                    "icon": a.get("icon", ""),
                    "progress": a.get("progress", 0),
                    "target": a.get("target", 1),
                    "completed": bool(a.get("completed")),
                    "locked": bool(a.get("locked")),
                }
                for a in ach.get("achievements", [])
            ],
        }))

    async def _hud_sidebar_places(self, db, room_id) -> None:
        """Send places_status sidebar message."""
        place_rows = await db.fetchall(
            "SELECT id, name FROM room_places WHERE room_id = ? ORDER BY id",
            (room_id,)
        )
        if not place_rows:
            return
        places_out = []
        for pr in place_rows:
            occ_rows = await db.fetchall(
                """SELECT c.name FROM place_occupants po
                   JOIN characters c ON c.id = po.char_id
                   WHERE po.place_id = ?""",
                (pr["id"],)
            )
            places_out.append({
                "id": pr["id"],
                "name": pr["name"],
                "occupants": [o["name"] for o in occ_rows],
            })
        await self._send(json.dumps({
            "type": "places_status",
            "places": places_out,
        }))

    # ── Main HUD orchestrator ─────────────────────────────────────────────

    async def send_hud_update(self, db=None, session_mgr=None):
        """
        Send structured HUD data to WebSocket clients.

        Phase 3 C2: decomposed into ~20 helper methods. Each block is
        independently try/except guarded so one failure doesn't break
        the entire HUD update.
        """
        if self.protocol != Protocol.WEBSOCKET:
            return
        if not self.character:
            return

        char = self.character
        room_id = char.get("room_id")
        char_id = char.get("id")

        # ── 1. Base payload (no DB) ──
        hud = self._hud_base()

        # ── 2. Equipment & loadout (no DB) ──
        try:
            self._hud_equipped_weapon(hud)
        except Exception:
            log.warning("send_hud_update: equipped_weapon failed", exc_info=True)

        try:
            self._hud_loadout(hud)
        except Exception:
            log.warning("send_hud_update: loadout failed", exc_info=True)

        # ── 3. Room row + properties (single DB fetch, reused below) ──
        room_row = None
        room_props = {}
        try:
            room_row, room_props = await self._hud_room_row(db, room_id)
        except Exception:
            log.debug("send_hud_update: room_row fetch failed", exc_info=True)

        # ── 4. Exits ──
        if db and room_id:
            try:
                await self._hud_exits(hud, db, room_id, room_row)
            except Exception:
                pass  # Non-critical — exits just won't show

        # ── 5. Room description ──
        self._hud_room_description(hud, room_row)

        # ── 6. Zone name + type ──
        if db and room_row:
            try:
                await self._hud_zone(hud, db, room_row)
            except Exception:
                pass  # Non-critical — mood stays default

        # ── 7. Director alert level ──
        try:
            self._hud_alert_level(hud)
        except Exception:
            pass  # Non-critical — alert badge won't show

        # ── 8. Security level ──
        security_level = "contested"
        try:
            security_level = await self._hud_security(hud, db, room_id)
        except Exception:
            hud["security_level"] = "contested"

        # ── 9. Housing ──
        try:
            await self._hud_housing(hud, db, room_id, room_row)
        except Exception:
            log.warning("send_hud_update: housing failed", exc_info=True)

        # ── 10. Territory ──
        try:
            await self._hud_territory(hud, db, room_id)
        except Exception:
            pass  # Non-critical

        # ── 11. CP progress ──
        try:
            await self._hud_cp_progress(hud, db, char_id)
        except Exception:
            log.warning("send_hud_update: cp_progress failed", exc_info=True)

        # ── 12. Reputation ──
        try:
            await self._hud_reputation(hud, db, char)
        except Exception:
            log.warning("send_hud_update: reputation failed", exc_info=True)

        # ── 13. Zone influence ──
        if db and room_row:
            try:
                await self._hud_zone_influence(hud, db, room_row)
            except Exception:
                pass  # Non-critical

        # ── 14. Room contents (NPCs, players, droids, services) ──
        if db and room_id:
            try:
                await self._hud_room_contents(
                    hud, db, room_id, room_props, security_level, session_mgr)
            except Exception:
                pass  # Non-critical

        # ── 15. Area map ──
        if db and room_id:
            try:
                await self._hud_area_map(hud, db, room_id)
            except Exception:
                log.warning("send_hud_update: area_map failed", exc_info=True)

        # ── 16. Nearby services ──
        if db and room_id:
            try:
                await self._hud_nearby_services(hud, db, room_id)
            except Exception:
                log.warning("send_hud_update: nearby_services failed", exc_info=True)
                hud["nearby_services"] = []

        # ── 17. Active jobs ──
        if char_id:
            try:
                await self._hud_active_jobs(hud, char)
            except Exception:
                log.debug("send_hud_update: active_jobs failed", exc_info=True)

        # ── 18. Send main HUD + credit event ──
        try:
            await self._hud_send_credit_event(hud)
            await self._send(json.dumps({"type": "hud_update", **hud}))
        except Exception as e:
            log.warning("HUD update failed on %s: %s", self, e)
            return  # Don't attempt sidebar panels if main HUD failed

        # ── 19. Sidebar panels (separate lightweight messages) ──
        if db and char_id:
            try:
                await self._hud_sidebar_mail(db, char_id)
            except Exception:
                pass  # Mail table may not exist

            try:
                await self._hud_sidebar_achievements(db, char_id)
            except Exception:
                pass  # Achievements may not be initialized

        if db and room_id:
            try:
                await self._hud_sidebar_places(db, room_id)
            except Exception:
                pass  # Places tables may not exist

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
