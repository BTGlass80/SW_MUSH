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

from engine.json_safe import safe_json_loads

if TYPE_CHECKING:
    from db.database import Database

log = logging.getLogger(__name__)


def _bearing_from_attributes(char) -> Optional[int]:
    """Phase-1 bearing substrate: pull ``attributes.bearing`` (screen-space
    degrees, set by MoveCommand from the last planar move) off a character
    dict. Returns ``None`` when absent/unparseable so the renderer keeps its
    default (0). ``attributes`` may be a JSON string or an already-parsed dict.
    """
    if not char:
        return None
    attrs = char.get("attributes")
    if isinstance(attrs, str):
        attrs = safe_json_loads(attrs, {}) if attrs else {}
    if not isinstance(attrs, dict):
        return None
    b = attrs.get("bearing")
    return b if isinstance(b, (int, float)) else None


class Protocol(enum.Enum):
    TELNET = "telnet"
    WEBSOCKET = "websocket"


class SessionState(enum.Enum):
    """Tracks where the player is in the login flow."""
    CONNECTED = "connected"          # Just connected, at login screen
    AUTHENTICATED = "authenticated"  # Logged in, selecting/creating character
    IN_GAME = "in_game"              # Playing with an active character
    # CHAR_SWITCH (S44): in-game request to drop the current character and
    # return to character select. handle_new_session checks for this state
    # at the end of the game loop and re-enters _character_select instead
    # of disconnecting.
    CHAR_SWITCH = "char_switch"
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
        # The equipment column stores per-slot ItemInstances whose to_dict()
        # emits key/condition/quality/crafter — NOT name/damage/type. The old
        # code read those never-present keys, so the web loadout sidebar was
        # always blank. Resolve the display fields from the weapon REGISTRY (by
        # key) and the per-instance state (condition/quality/crafter) from the
        # ItemInstance (TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES Stage 1).
        from engine.items import read_equipment
        from engine.weapons import get_weapon_registry
        slots = read_equipment(char.get("equipment", "{}"))
        wr = get_weapon_registry()

        # Emit ONLY the name the SPA actually consumes (client.html reads
        # loadout.weapon.name / loadout.armor.name). Resolve it from the weapon
        # REGISTRY by key — the old code read name/damage/type off the equipment
        # JSON, but that's the ItemInstance.to_dict() shape (key/condition/
        # quality/crafter), so the name was always blank. Richer per-instance
        # display (condition/quality/crafter) is deferred to a drop that ships
        # the SPA consumer alongside it — no phantom producer fields here.
        winst = slots.get("weapon")
        if winst:
            wdef = wr.get(winst.key)
            loadout["weapon"] = {
                "name": (wdef.name if wdef
                         else winst.key.replace("_", " ").title()),
            }

        ainst = slots.get("armor")
        if ainst:
            adef = wr.get(ainst.key)
            loadout["armor"] = {
                "name": (adef.name if adef
                         else ainst.key.replace("_", " ").title()),
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


# ── Webify UI-6: one-line objective from the active_jobs list ──

_OBJECTIVE_MAX_LEN = 96


def _objective_line(jobs: list) -> str:
    """Derive the single `hud_update.objective` string from active_jobs.

    The FIRST job in the list wins (the producer orders them by
    orientation priority: tutorial step → mission → bounty → smuggle →
    spacer quest). Returns "" when there is nothing to surface, which
    the client treats as hide-the-box. Pure + sync; never raises.
    """
    for j in jobs or []:
        try:
            jtype = j.get("type", "")
            label = str(j.get("label", "") or "").strip()
            obj = str(j.get("objective", "") or "").strip()
            reward = j.get("reward")
            if jtype == "tutorial":
                line = obj or label
            elif jtype == "bounty":
                target = str(j.get("target", "") or "").strip() or label
                line = f"Hunt {target}"
                if reward:
                    line += f" — {reward:,} cr bounty"
            elif jtype == "mission":
                line = label
                if obj:
                    line += f" — {obj}"
            elif jtype == "smuggle":
                line = label
                if reward:
                    line += f" — {reward:,} cr"
            elif jtype == "quest":
                line = obj or label
            else:
                line = obj or label
            line = line.strip()
            if not line:
                continue
            if len(line) > _OBJECTIVE_MAX_LEN:
                line = line[:_OBJECTIVE_MAX_LEN - 1].rstrip() + "…"
            return line
        except Exception:
            continue
    return ""


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

        # Source IP of the connecting client, captured at the transport seam
        # (telnet/WS peername; the aiohttp web port resolves it spoof-
        # resistantly via api._get_client_ip, honoring X-Forwarded-For only
        # from a configured trusted proxy). Used by the pre-auth connect/create
        # per-IP throttle in handle_new_session (T3.21 Blocker 2, protocol
        # half). Defaults to "unknown" until a handler sets it.
        self.client_ip: str = "unknown"

        # Transport callbacks (set by protocol handler)
        self._send = send_callback
        self._close = close_callback

        # Input queue - protocol handlers push lines here
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()

        # Track last sent credits value to detect changes for credit_event (Drop 9)
        self._last_sent_credits: Optional[int] = None

        # Webify UI-7: last (chain_id, step) pushed as onboarding_state.
        # Gates the graduation payload to push exactly once (only when the
        # chain was active THIS session) — a reconnect after graduation
        # pushes nothing.
        self._last_chain_step: Optional[tuple] = None

        # F.MAP.2: Track the last AreaGeometry we pushed to this session.
        # The full payload (~22KB) only ships on area transitions; per-tick
        # HUD updates send only `player_position` (lightweight). Set to None
        # when no AreaGeometry has been pushed yet.
        self._last_sent_area_key: Optional[str] = None

    @property
    def wrap_width(self) -> int:
        """Text wrapping width.

        Telnet caps at 80 (classic terminal width) so decorative bars,
        prose, and sheet output line up consistently in any terminal
        emulator. WebSocket caps at 100 — modern browsers can show wider
        lines comfortably and the in-game web client uses a monospace
        font with elastic columns. The session reports its raw width
        from the negotiated NAWS / window size; we just clamp it.
        """
        cap = 100 if self.protocol == Protocol.WEBSOCKET else 80
        return min(self.width, cap)

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
            elif msg_type == "pose_event":
                # Drop B: pose_event Telnet fallback. Render the typed
                # narration as styled text so Telnet players still see it
                # (they just don't get client-side dedup or attribution
                # styling). event_type determines the prefix; text is
                # the narration body. Schema mirrors the live client's
                # handlePoseEvent consumer (event_type/who/text/mode/to)
                # — see engine/pose_events.py for the full contract.
                text = data.get("text", "")
                if not text:
                    return
                who = data.get("who", "")
                et = data.get("event_type", "")
                if et == "say" and who:
                    await self.send_line(f'{who} says, "{text}"')
                elif et == "whisper" and who:
                    to = data.get("to")
                    suffix = f" to {to}" if to else ""
                    await self.send_line(f'{who} whispers{suffix}, "{text}"')
                elif et in ("pose", "emote") and who:
                    # Drop B': pose-with-target-and-mode is how mutter is
                    # carried (event_type='pose', mode='mutters', to=tname).
                    # Render as: 'Tundra mutters to Han, "..."' on Telnet.
                    # Plain pose without `to` keeps the legacy Drop B
                    # rendering: 'Tundra wipes his hands.'
                    to = data.get("to")
                    if to:
                        verb = data.get("mode") or "poses"
                        await self.send_line(f'{who} {verb} to {to}, "{text}"')
                    else:
                        await self.send_line(f"{who} {text}")
                elif et in ("desc-inline", "sys-event", "sys-ok",
                            "sys-arrival", "comm-in"):
                    await self.send_line(text)
                else:
                    # Unknown event_type — render bare so we don't drop
                    # the narration entirely.
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
        """Add equipped weapon name to HUD from character equipment.

        Tolerant of all equipment shapes, and resolves the display NAME from
        the weapon registry (the stored ItemInstance carries only the key, not
        a name — the old code read a "name" field that was never serialized,
        so the HUD weapon name was effectively always blank).
        """
        from engine.items import read_equipment
        weapon = read_equipment(self.character.get("equipment")).get("weapon")
        if not weapon:
            return
        name = weapon.key
        try:
            from engine.weapons import get_weapon_registry
            w = get_weapon_registry().get(weapon.key)
            if w and w.name:
                name = w.name
        except Exception:
            log.debug("_hud_equipped_weapon: registry lookup failed", exc_info=True)
        hud["equipped_weapon"] = name

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
        from engine.director import get_director, VALID_FACTIONS
        director = get_director()
        zone_key = hud.get("zone_type", "")
        if zone_key:
            alert = director.get_alert_level(zone_key)
            hud["alert_level"] = alert.value if alert else ""
            zs = director.get_zone_state(zone_key)
            if zs:
                # Dominant faction across the era's native faction set
                # (DIRECTOR.zonestate_cw_faction_axis).
                factions = {f: zs.get_faction(f) for f in VALID_FACTIONS}
                if factions and any(v for v in factions.values()):
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
        """Add region-ownership badge and active region-contest status.

        SYN.3 (2026-05-25): retargeted from zone-keyed Drop 6D contest
        surfaces (now physically deleted) to region-keyed SYN.3
        contest surfaces. Per-room claims are also gone (SYN.1.b
        retirement) — the badge now reflects region ownership instead
        of per-room claim ownership.
        """
        hud["territory_claim"] = None
        hud["contest_active"] = False
        if not (db and room_id):
            return
        # Resolve the room's wilderness region (if any). City-map
        # rooms (no wilderness_region_id) have neither a territory
        # claim nor a contest — they're neutral commons per the
        # Contestable Wilderness pivot (design v2 §0 + §1.3).
        try:
            room = await db.get_room(room_id)
        except Exception:
            room = None
        region_slug = (room or {}).get("wilderness_region_id")
        if not region_slug:
            return

        from engine.territory import get_region_owner
        from engine.contest import get_active_region_contest

        owner = await get_region_owner(db, region_slug)
        if owner:
            org_code = owner["org_code"]
            hud["territory_claim"] = {
                "org_code": org_code,
                "org_name": org_code.replace("_", " ").title(),
                "region_slug": region_slug,
                # Per-room guard_npc_id is gone (SYN.1.b); region
                # garrisons live in region_garrison and span the
                # whole region rather than one room.
                "has_guard": False,
            }

        contest = await get_active_region_contest(db, region_slug)
        if contest:
            hud["contest_active"] = True
            hud["contest_region"] = region_slug
            hud["contest_challenger"] = (
                contest["challenger_org_code"].replace("_", " ").title()
            )
            defender = contest.get("defender_org_code")
            hud["contest_defender"] = (
                defender.replace("_", " ").title()
                if defender else "(un-owned)"
            )
            hud["contest_ends"] = max(
                0, int(contest["ends_at"] - time.time()))
            # Are we in the culminating-fight phase?
            hud["contest_culminating"] = (
                time.time() >= float(contest["accumulation_ends_at"])
            )

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

    async def _hud_city(self, hud: dict, db, char,
                         room_id) -> None:
        """Phase 6 web UI: assemble the city sidebar payload.

        Sets ``hud["city"]`` to a summary dict when the player is
        in a city room OR is a member of an org with an active
        city. For admins (``is_admin=1``), additionally attaches
        ``hud["city"]["admin"]`` with the all-cities list.

        Payload shape:
            hud["city"] = {
                "name":            "Sunshine Outpost",
                "id":              7,
                "role":            "founder" | "mayor" | "citizen" | "guest" | "visitor",
                "hq_tier":         "outpost" | "chapter_house" | "fortress",
                "state":           "active" | "dissolved",
                "grace_stage":     "active" | "week1" | "week2" | "week3" | "week4" | "expired",
                "is_in_grace":     bool,
                "treasury":        int,
                "tax_rate":        float (0.0-0.10),
                "rate_cap":        float,
                "motd":            str,
                "revenue_week":    int,
                "revenue_total":   int,
                "expansion_rooms": int,
                "max_expansion":   int,
                "guard_slots_used":  int,
                "guard_slots_total": int,
                "citizens_count":  int,
                "guests_count":    int,
                "banishments_count": int,
                "founder_id":      int,
                "mayor_id":        int,
                "founder_name":    str,
                "mayor_name":      str,
                # Lists (truncated to 25; modal does the full read)
                "citizens":     [{id, name, rank, online}, ...],
                "guests":       [{id, name}, ...],
                "banishments":  [{id, name, until, issued_by}, ...],
                "guards":       [{npc_id, room_id, assigned_at, ai_active}, ...],
                # Admin-only block
                "admin": {
                    "is_admin":   True,
                    "all_cities": [{id, name, planet, mayor, hq_tier,
                                    rooms, treasury, state}, ...],
                },
            }

        If the player has no city context AND is not an admin,
        ``hud["city"]`` is not set (the JS renders the panel
        only when the key is present).

        Failure-tolerant per the standing HUD contract: any
        exception falls through with a partial payload (caller
        wraps in try/except).
        """
        # Late import — engine.player_cities is the engine of
        # record for everything here.
        try:
            from engine import player_cities as pc
        except Exception:
            return

        is_admin = bool(char.get("is_admin"))

        # Resolve the candidate city: (a) the room the player is
        # in, falling back to (b) the player's org's active city.
        city = None
        if room_id:
            try:
                city = await pc.get_city_for_room(db, int(room_id))
            except Exception:
                log.debug("[_hud_city] room lookup failed",
                          exc_info=True)
        if city is None:
            faction = char.get("faction_id") or "independent"
            if faction and faction != "independent":
                try:
                    org = await db.get_organization(faction)
                    if org:
                        city = await pc.get_city_by_org(
                            db, int(org["id"]))
                except Exception:
                    log.debug(
                        "[_hud_city] org lookup failed",
                        exc_info=True,
                    )

        if city is None and not is_admin:
            return  # No payload — JS hides the panel

        if city is not None:
            payload = await self._hud_city_payload(db, char, city)
        else:
            # Admin with no city context — still ship admin block
            payload = {"admin_only": True}

        if is_admin:
            try:
                admin_block = await self._hud_city_admin_block(
                    db, char)
                payload["admin"] = admin_block
            except Exception:
                log.debug(
                    "[_hud_city] admin block build failed",
                    exc_info=True,
                )

        hud["city"] = payload

    async def _hud_city_payload(
        self, db, char, city: dict,
    ) -> dict:
        """Build the per-city payload dict.

        Centralized so the admin "viewing another city" surface
        (if added later) can call the same builder.

        Lists are TRUNCATED to 25 entries; the click-to-modal
        flow uses the same data shape and the v2 of this
        payload will accept a query param to page beyond 25.
        """
        from engine import player_cities as pc

        city_id = int(city["id"])
        # Role of this character vs this city
        try:
            role = await pc.get_city_role(db, city, char)
        except Exception:
            role = "outsider"

        # Pure-helper-driven derived values
        try:
            grace_stage = pc.grace_stage(city)
        except Exception:
            grace_stage = "active"
        try:
            is_grace = pc.is_in_grace(city)
        except Exception:
            is_grace = False
        try:
            guard_slots_total = pc.compute_city_guard_slots(city)
        except Exception:
            guard_slots_total = 0
        try:
            guards_used = await pc.count_city_guards(db, city_id)
        except Exception:
            guards_used = 0
        try:
            expansion_rooms = await pc.get_city_expansion_count(
                db, city_id)
        except Exception:
            expansion_rooms = 0
        max_expansion = pc.MAX_EXPANSION_ROOMS.get(
            city.get("hq_tier") or "outpost", 0)

        # Treasury (org's wallet)
        treasury = 0
        try:
            org_id = int(city.get("org_id") or 0)
            if org_id:
                rows = await db.fetchall(
                    "SELECT treasury FROM organizations "
                    "WHERE id = ?",
                    (org_id,),
                )
                if rows:
                    treasury = int(rows[0].get("treasury") or 0)
        except Exception:
            log.debug("[_hud_city] treasury read failed",
                      exc_info=True)

        # Founder / mayor names
        founder_name = ""
        mayor_name = ""
        try:
            f = await db.get_character(
                int(city.get("founder_id") or 0))
            if f:
                founder_name = f.get("name", "")
            m = await db.get_character(
                int(city.get("mayor_id") or 0))
            if m:
                mayor_name = m.get("name", "")
        except Exception:
            log.debug(
                "[_hud_city] founder/mayor name lookup failed",
                exc_info=True,
            )

        # Citizens (members of the founding org). Show top 25
        # ordered by rank desc then name asc — matches the
        # underlying get_org_members ordering.
        citizens: list = []
        try:
            members = await db.get_org_members(
                int(city.get("org_id") or 0))
            for m in members[:25]:
                citizens.append({
                    "id": int(m.get("char_id") or 0),
                    "name": m.get("char_name") or "",
                    "rank": int(m.get("rank_level") or 0),
                    # Online flag not yet wired — Phase 6 UI v1
                    # leaves this field present but False.
                    "online": False,
                })
        except Exception:
            log.debug("[_hud_city] citizens read failed",
                      exc_info=True)
        citizens_count = len(citizens)
        try:
            # If the truncated list IS the truncated list, the
            # count is at least 25 — but the underlying call
            # gave us the full member list anyway, so:
            if 'members' in locals():
                citizens_count = len(members)
        except Exception:
            log.debug(
                "[_hud_city] citizens_count recovery failed",
                exc_info=True,
            )

        # Guests
        guests: list = []
        guests_count = 0
        try:
            from engine.player_cities import list_guests
            guest_ids = await list_guests(db, city_id)
            guests_count = len(guest_ids)
            for gid in guest_ids[:25]:
                gname = f"id={gid}"
                try:
                    g = await db.get_character(int(gid))
                    if g:
                        gname = g.get("name") or gname
                except Exception:
                    log.debug(
                        "[_hud_city] guest name lookup failed "
                        "for %s (best-effort)", gid,
                        exc_info=True,
                    )
                guests.append({"id": int(gid), "name": gname})
        except Exception:
            log.debug("[_hud_city] guests read failed",
                      exc_info=True)

        # Banishments (active only)
        banishments: list = []
        banishments_count = 0
        try:
            from engine.player_cities import list_active_banishments
            bans = await list_active_banishments(db, city_id)
            banishments_count = len(bans)
            for b in bans[:25]:
                cid = int(b.get("char_id") or 0)
                bname = f"id={cid}"
                try:
                    c = await db.get_character(cid)
                    if c:
                        bname = c.get("name") or bname
                except Exception:
                    log.debug(
                        "[_hud_city] banishment name lookup "
                        "failed for %s (best-effort)", cid,
                        exc_info=True,
                    )
                banishments.append({
                    "id": cid, "name": bname,
                    "until": float(b.get("until") or 0.0),
                    "issued_by": int(b.get("issued_by") or 0),
                })
        except Exception:
            log.debug("[_hud_city] banishments read failed",
                      exc_info=True)

        # Guards (use the engine helper)
        guards: list = []
        try:
            assigns = await pc.list_city_guards(db, city_id)
            for a in assigns[:25]:
                guards.append({
                    "npc_id": int(a.get("npc_id") or 0),
                    "room_id": int(a.get("room_id") or 0),
                    "assigned_at": float(
                        a.get("assigned_at") or 0.0),
                    # AI active iff city not in grace. The Phase
                    # 7b helper lives in engine.city_guard_runtime
                    # but uses the same predicate.
                    "ai_active": not is_grace,
                })
        except Exception:
            log.debug("[_hud_city] guards read failed",
                      exc_info=True)

        return {
            "name":   city.get("name", ""),
            "id":     city_id,
            "role":   role,
            "hq_tier": city.get("hq_tier", "outpost"),
            "state":   city.get("state", "active"),
            "grace_stage": grace_stage,
            "is_in_grace": is_grace,
            "treasury": treasury,
            "tax_rate": float(city.get("tax_rate") or 0.0),
            "rate_cap": float(city.get("rate_cap") or 0.10),
            "motd":     city.get("motd") or "",
            "revenue_week":  int(city.get("revenue_week") or 0),
            "revenue_total": int(city.get("revenue_total") or 0),
            "expansion_rooms": expansion_rooms,
            "max_expansion":   max_expansion,
            "guard_slots_used":  guards_used,
            "guard_slots_total": guard_slots_total,
            "citizens_count":    citizens_count,
            "guests_count":      guests_count,
            "banishments_count": banishments_count,
            "founder_id":   int(city.get("founder_id") or 0),
            "mayor_id":     int(city.get("mayor_id") or 0),
            "founder_name": founder_name,
            "mayor_name":   mayor_name,
            "citizens":    citizens,
            "guests":      guests,
            "banishments": banishments,
            "guards":      guards,
        }

    async def _hud_city_admin_block(
        self, db, char,
    ) -> dict:
        """Admin-only block: list of every active city for the
        @city admin view."""
        from engine import player_cities as pc

        all_cities: list = []
        try:
            rows = await pc.list_all_cities(db)
            for row in rows[:200]:  # client-side cap; admin view paginates
                if row.get("state") == "dissolved":
                    continue
                all_cities.append({
                    "id":       int(row.get("id") or 0),
                    "name":     row.get("name") or "",
                    "hq_tier":  row.get("hq_tier") or "outpost",
                    "treasury": 0,  # filled below per-org
                    "state":    row.get("state") or "active",
                    "org_id":   int(row.get("org_id") or 0),
                })
        except Exception:
            log.debug(
                "[_hud_city] admin list_all_cities failed",
                exc_info=True,
            )

        # Bulk-fetch treasuries for the org_ids we collected
        try:
            org_ids = sorted({c["org_id"] for c in all_cities
                              if c.get("org_id")})
            if org_ids:
                placeholders = ",".join("?" * len(org_ids))
                rows = await db.fetchall(
                    f"SELECT id, treasury FROM organizations "
                    f"WHERE id IN ({placeholders})",
                    tuple(org_ids),
                )
                trez = {int(r["id"]): int(r.get("treasury") or 0)
                        for r in rows}
                for c in all_cities:
                    c["treasury"] = trez.get(
                        int(c.get("org_id") or 0), 0)
        except Exception:
            log.debug(
                "[_hud_city] admin treasury bulk-fetch failed",
                exc_info=True,
            )

        return {
            "is_admin":   True,
            "all_cities": all_cities,
        }


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

    async def _hud_area_map(self, hud: dict, db, room_id, session_mgr=None) -> None:
        """Build area map for minimap context panel.

        Always emits the legacy ``area_map`` payload (used by the
        existing client.html ``renderAreaMap`` minimap renderer).

        F.MAP.2: when an ``AreaGeometryRegistry`` is attached to
        session_mgr (via ``session_mgr._area_registry``) AND the
        current room's ``properties.slug`` resolves to an
        AreaGeometry-covered room, ALSO emits:

          - ``area_geometry``: full AreaGeometry-as-dict, ONLY on the
            first push to this session OR when the player crosses
            into a different area. Per-tick steady-state pushes
            omit this field. Saves ~22KB per HUD tick.
          - ``player_position``: lightweight {area_key, room_id, x, y}
            stamped on every push so the client marker layer can
            interpolate to the new position without re-rendering
            the rest of the map.

        F.MAP.6: when the area is covered, ALSO emits:

          - ``contacts``: list of {kind, name, x, y} entries — every
            other PC in any covered room, plus every NPC in any
            covered room, mapped to render coords. Self excluded
            (already in player_position). Stamped on every push so
            the renderer can update markers in place.

        If the registry is absent, the room's slug isn't in the
        index, or any other failure occurs, only the legacy
        ``area_map`` is sent. The client falls back to the legacy
        renderer transparently.
        """
        # ── Legacy path (always runs) ──────────────────────────────────
        from engine.area_map import build_area_map
        hud["area_map"] = await build_area_map(room_id, db, depth=2)

        # Fetch the player's room row once — used by the environment
        # substrate (below) AND the F.MAP.2 slug/registry path. Best-effort:
        # the HUD push must never crash (see TestFailureTolerance), so a DB
        # read failure here degrades to the legacy area_map already emitted.
        try:
            row = await db.get_room(room_id)
        except Exception:
            log.warning("[hud_area_map] get_room failed; legacy area_map only",
                        exc_info=True)
            return
        props = row.get("properties") if row else None
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (ValueError, TypeError):
                props = {}
        if not isinstance(props, dict):
            props = {}

        # ── Phase-1 environment substrate (always sent; best-effort) ───
        # time-of-day + weather scalars the SPA map renderer consumes. Room
        # `properties.time_of_day` / `.weather` override the global day cycle;
        # absent => the living day->dusk->night loop and 'clear'.
        try:
            from engine.world_time import resolve_environment
            hud["environment"] = resolve_environment(props)
        except Exception:
            log.warning("[hud_area_map] environment resolve failed", exc_info=True)

        # ── Drop 4.22: wilderness region key (always sent when present) ──
        # `rooms.wilderness_region_id` is a top-level column (NULL for
        # hand-built city/interior rooms, == region.slug for wilderness
        # landmarks; set by engine/wilderness_writer.py). The SPA's
        # M3Adapter.regionKeyForArea prefers this explicit field to decide
        # WHICH wilderness region the ⊕ Tier-1b map renders, so the painted
        # wilderness substrate (Drop 4.21) becomes reachable by a live player.
        #
        # This MUST ride the always-present path, NOT player_position below:
        # wilderness rooms are not covered by any AreaGeometry (their overview
        # YAMLs carry `landmarks:` but no `rooms:`), so the F.MAP.2 path that
        # emits player_position never fires for them. Emitted only when the
        # room actually carries the field, so city/interior HUDs are byte-
        # identical to before.
        if row and row.get("wilderness_region_id"):
            hud["wilderness_region_id"] = row["wilderness_region_id"]

        # ── F.MAP.2/F.MAP.6 augmentation (best-effort, never raises) ───
        registry = getattr(session_mgr, "_area_registry", None) if session_mgr else None
        if registry is None:
            return  # No registry attached; legacy path only.
        try:
            if not row:
                return
            slug = props.get("slug")
            if not slug:
                return
            entry = registry.lookup(slug)
            if entry is None:
                # Room is in production but not covered by an
                # authored AreaGeometry. Legacy minimap renders.
                # Drop the cached area_key so the next entry into a
                # covered area triggers a fresh `area_geometry` push.
                self._last_sent_area_key = None
                return
            # Always send a lightweight player_position
            hud["player_position"] = {
                "area_key":      entry.area_key,
                "render_room_id": entry.render_room_id,
                "x":             entry.x,
                "y":             entry.y,
                # Phase-1 bearing substrate: the player's own facing from
                # their last planar move, so the self-chevron points that way.
                "bearing":       _bearing_from_attributes(self.character),
            }
            # Drop 4.22: consistency with the always-present hud field above.
            # No-op for the city/interior areas that are actually registry-
            # covered today (their rooms carry no wilderness_region_id); it
            # populates here only if a wilderness region ever gains an
            # AreaGeometry, keeping M3Adapter.regionKeyForArea correct whether
            # it reads the top-level hud field or the player_position payload.
            if row.get("wilderness_region_id"):
                hud["player_position"]["wilderness_region_id"] = \
                    row["wilderness_region_id"]
            # On area transition (or first push), include the full geometry
            if self._last_sent_area_key != entry.area_key:
                payload = registry.get_payload(entry.area_key)
                if payload is not None:
                    hud["area_geometry"] = payload
                    self._last_sent_area_key = entry.area_key
            # F.MAP.6: build contacts list (every other PC + every NPC
            # in any covered room, mapped to render coords). Failure
            # here doesn't kill the rest of the augmentation.
            try:
                contacts = await self._build_area_contacts(
                    db, registry, entry.area_key, session_mgr,
                )
                hud["contacts"] = contacts
            except Exception:
                log.warning("[hud_area_map] contacts assembly failed",
                            exc_info=True)
            # Dynamic POI feed: live entities (bounty targets, …) for the
            # map's L_Entities layer. Separate from static authored landmarks.
            try:
                pois = await self._build_area_pois(db, registry, entry.area_key)
                hud["pois"] = pois
            except Exception:
                log.warning("[hud_area_map] pois assembly failed",
                            exc_info=True)
        except Exception:
            log.warning("[hud_area_map] area_geometry augmentation failed",
                        exc_info=True)

    async def _build_area_contacts(self, db, registry, area_key: str,
                                   session_mgr) -> list:
        """F.MAP.6: assemble the ``contacts`` list for the player's
        current area.

        Returns a list of dicts shaped for the F.MAP.1 MapView
        renderer's marker layer:
          [{kind: "pc"|"npc_friend"|"npc_hostile"|"npc_neutral",
            name: str, x: float, y: float}, ...]

        Self is EXCLUDED — the caller already stamped the player on
        ``hud["player_position"]`` and the renderer draws that
        separately (with the pulsing self-marker).

        NPCs are role-classified via the existing _classify_npc_role
        path:
          hostile               → "npc_hostile"
          guard / quest         → "npc_friend"   (allies/allies-of-the-state)
          trainer / vendor /    → "npc_neutral"
          mechanic / bartender    (service NPCs)
          other                 → "npc_neutral"

        Failure-tolerant: any per-NPC or per-PC failure is logged at
        DEBUG and skipped — better to ship a partial roster than a
        broken HUD.
        """
        # Resolve the area's slugs to db room_ids (cached after first call).
        try:
            room_id_map = await registry.resolve_area_room_ids(area_key, db)
        except Exception:
            log.warning("[hud_area_map] resolve_area_room_ids failed for %s",
                        area_key, exc_info=True)
            return []
        if not room_id_map:
            return []

        contacts: list = []

        # ── PCs in covered rooms (excluding self) ───────────────────────
        if session_mgr is not None:
            try:
                self_id = (self.character or {}).get("id")
                for sess in session_mgr._sessions.values():
                    if not getattr(sess, "is_in_game", False):
                        continue
                    sc = sess.character
                    if not sc:
                        continue
                    if sc.get("id") == self_id:
                        continue
                    sroom = sc.get("room_id")
                    e = room_id_map.get(sroom) if sroom else None
                    if e is None:
                        continue
                    contacts.append({
                        "kind": "pc",
                        "name": sc.get("name", "?"),
                        "x":    e.x,
                        "y":    e.y,
                        # Phase-1 bearing substrate: facing from the PC's last
                        # move (attributes.bearing), so their chevron points
                        # the way they walked. Absent => renderer defaults 0.
                        "bearing": _bearing_from_attributes(sc),
                        # +pvp display surface (May 18 2026): surface
                        # opt-in flag status to the HUD contact roster
                        # so observers can see at a glance which PCs
                        # are flagged before approaching. Web-first;
                        # rendering choice (color, badge) is a UI
                        # concern. SECURED zones still block PvP
                        # regardless of flag, so this is informational.
                        "pvp_flagged": bool(sc.get("pvp_flagged") or False),
                    })
            except Exception:
                log.debug("[hud_area_map] pc roster sweep failed",
                          exc_info=True)

        # ── NPCs in covered rooms ───────────────────────────────────────
        # Single SQL: SELECT * FROM npcs WHERE room_id IN (?, ?, ...).
        # The IN-clause is constructed from the resolved room ids only,
        # so the ? count is bounded by the number of authored rooms in
        # the area (53 for Mos Eisley).
        room_ids = list(room_id_map.keys())
        if room_ids:
            try:
                placeholders = ",".join(["?"] * len(room_ids))
                rows = await db._db.execute_fetchall(
                    f"SELECT * FROM npcs WHERE room_id IN ({placeholders})",
                    tuple(room_ids),
                )
                for r in rows:
                    rd = dict(r)
                    if rd.get("hired_by") is not None:
                        # Hired NPC — already conceptually with the player
                        # who hired them. Skip to avoid stacking icons.
                        continue
                    rid = rd.get("room_id")
                    e = room_id_map.get(rid)
                    if e is None:
                        continue
                    role = _classify_npc_role(rd)
                    if role == "hostile":
                        kind = "npc_hostile"
                    elif role in ("guard", "quest"):
                        kind = "npc_friend"
                    else:
                        # trainer / vendor / mechanic / bartender / neutral
                        kind = "npc_neutral"
                    contacts.append({
                        "kind": kind,
                        "name": rd.get("name", "NPC"),
                        "x":    e.x,
                        "y":    e.y,
                    })
            except Exception:
                log.debug("[hud_area_map] npc roster sweep failed",
                          exc_info=True)

        return contacts

    async def _build_area_pois(self, db, registry, area_key: str) -> list:
        """F.MAP — dynamic POI feed: live entities (bounty targets, …) in the
        player's current area, mapped to render coords for L_Entities.

        Returns a list shaped for the composition engine's ``dynamic.poi``:
          [{kind: "bounty"|"vendor"|"mission"|"objective"
                   |"anomaly_t1"|"anomaly_t2"|"anomaly_t3",
            x: float, y: float}, ...]

        These are RUNTIME entities, distinct from the static authored
        ``landmarks`` the adapter already turns into POIs. Same render-id
        bridge as contacts: ``resolve_area_room_ids`` maps a DB room_id to its
        AreaGeometry render coords. Best-effort — never raises into the HUD.

        v1 source: posted bounty contracts whose ``target_room_id`` falls in a
        covered room. Also wired: wilderness anomalies — anchored to a landmark
        ``room_id`` and tiered (``anomaly_t1/t2/t3``, incl. the Tier-3 world
        boss). They're enumerated per-region via
        ``wilderness_anomalies.get_anomalies_for_region``, so we first derive
        the covered regions from the room map (``region_slug`` is captured on
        each ``_RoomLookupEntry`` at no extra DB cost), then map each anomaly's
        ``anchor_room_id`` to render coords the same way bounties are mapped.

        Also wired (see the sweep below): the player's accepted-mission
        objective(s) — ``destination_room_id`` → ``{kind:"objective"}``.
        Still not wired: mission-giver pins (``giver`` is a name, not a room).
        """
        pois: list = []
        try:
            room_id_map = await registry.resolve_area_room_ids(area_key, db)
        except Exception:
            log.warning("[hud_area_map] resolve_area_room_ids failed for %s "
                        "(pois)", area_key, exc_info=True)
            return pois
        if not room_id_map:
            return pois

        # ── Bounty targets in covered rooms ─────────────────────────────
        try:
            from engine.bounty_board import get_bounty_board
            board = get_bounty_board()
            for c in board.posted_contracts():
                troom = getattr(c, "target_room_id", None)
                if troom is None:
                    continue
                e = room_id_map.get(troom)
                if e is None:
                    continue  # bounty target isn't in this area's view
                pois.append({"kind": "bounty", "x": e.x, "y": e.y})
        except Exception:
            log.debug("[hud_area_map] bounty poi sweep failed", exc_info=True)

        # ── Wilderness anomalies in covered regions ─────────────────────
        # Anomalies are keyed by region, so first collect the distinct
        # regions this area covers (region_slug rides along on each room
        # entry, captured at no extra DB cost in resolve_area_room_ids).
        # Empty for city areas (region is None) → no anomaly glyphs there.
        try:
            from engine.wilderness_anomalies import get_anomalies_for_region
            regions = {
                e.region_slug
                for e in room_id_map.values()
                if getattr(e, "region_slug", None)
            }
            for region in regions:
                for a in get_anomalies_for_region(region):
                    anchor = getattr(a, "anchor_room_id", None)
                    if anchor is None:
                        continue
                    e = room_id_map.get(int(anchor))
                    if e is None:
                        continue  # anchored outside this area's view
                    tier = getattr(a, "tier", 1) or 1
                    tier = 1 if tier < 1 else (3 if tier > 3 else tier)
                    pois.append({
                        "kind": "anomaly_t{}".format(tier),
                        "x": e.x, "y": e.y,
                    })
        except Exception:
            log.debug("[hud_area_map] anomaly poi sweep failed", exc_info=True)

        # ── Placed vendor droids in covered rooms ───────────────────────
        # Area-state, like bounty/anomaly: every shopfront in view, for
        # everyone. Vendor droids are player-owned objects (type=
        # 'vendor_droid') anchored to a room when deployed (`shop place`);
        # unplaced ones sit in inventory with room_id=NULL and are excluded
        # by the room_id IN-filter automatically. One batched SQL keyed on
        # the covered room ids — the SAME no-storm pattern the contacts NPC
        # sweep uses (the ? count is bounded by the area's authored rooms),
        # so this adds a single indexed query per push, not one-per-room.
        room_ids = list(room_id_map.keys())
        if room_ids:
            try:
                placeholders = ",".join(["?"] * len(room_ids))
                rows = await db._db.execute_fetchall(
                    "SELECT room_id FROM objects "
                    "WHERE type = 'vendor_droid' "
                    f"AND room_id IN ({placeholders})",
                    tuple(room_ids),
                )
                for r in rows:
                    rd = dict(r)
                    e = room_id_map.get(rd.get("room_id"))
                    if e is None:
                        continue  # shouldn't happen (IN-filtered), but be safe
                    pois.append({"kind": "vendor", "x": e.x, "y": e.y})
            except Exception:
                log.debug("[hud_area_map] vendor poi sweep failed", exc_info=True)

        # ── The player's accepted-mission objective(s) ──────────────────
        # Unlike bounty/anomaly, which are area-state (everything huntable /
        # anomalous in view, for everyone), an objective is personal: it's the
        # destination of a mission THIS character accepted. So this sweep reads
        # self.character and places a green-star "objective" glyph on each
        # accepted mission's destination room that falls in the current view.
        #
        # destination_room_id is populated by the board generator from a real
        # DB room (MissionBoard.refresh lazily fetches the room list when it
        # fills the board) and stored as a string. Missions without one —
        # space missions (they target a zone, not a ground room) and any not
        # generated with a room list — carry None and are simply skipped, so a
        # missing destination degrades to "no marker", never an error.
        try:
            char = getattr(self, "character", None)
            if char is not None:
                char_id_str = str(char["id"])
                from engine.missions import get_mission_board, MissionStatus
                mboard = get_mission_board()
                for m in mboard._missions.values():
                    if (getattr(m, "accepted_by", None) != char_id_str or
                            getattr(m, "status", None) != MissionStatus.ACCEPTED):
                        continue
                    drid = getattr(m, "destination_room_id", None)
                    if drid is None:
                        continue
                    try:
                        rid = int(drid)
                    except (TypeError, ValueError):
                        continue
                    e = room_id_map.get(rid)
                    if e is None:
                        continue  # objective room isn't in this area's view
                    pois.append({"kind": "objective", "x": e.x, "y": e.y})
        except Exception:
            log.debug("[hud_area_map] objective poi sweep failed", exc_info=True)

        return pois
    async def _hud_nearby_services(self, hud: dict, db, room_id) -> None:
        """BFS for nearby services within 4 rooms."""
        from engine.area_map import find_nearby_services
        hud["nearby_services"] = await find_nearby_services(
            room_id, db, depth=4, max_results=8)

    async def _hud_active_jobs(self, hud: dict, char) -> None:
        """Gather active mission, bounty, smuggling, and quest jobs."""
        jobs = []
        char_id_str = str(char["id"])

        # Active tutorial-chain step (Webify UI-6) — FIRST: a player in
        # the tutorial is the player who most needs the objective line.
        # Corpus access goes through chain_events' cached loader (the
        # chain subsystem's runtime facade) so the HUD tick never
        # re-reads chains.yaml.
        try:
            from engine.chain_events import _get_corpus
            from engine.tutorial_chains import get_current_step
            attrs = char.get("attributes", "{}")
            if isinstance(attrs, str):
                attrs = json.loads(attrs) if attrs else {}
            corpus = _get_corpus()
            if corpus is not None and isinstance(attrs, dict):
                step = get_current_step(attrs, corpus)
                if step is not None:
                    jobs.append({
                        "type": "tutorial",
                        "label": step.title,
                        "objective": step.objective,
                    })
        except Exception:
            log.debug("_hud_active_jobs: tutorial chain lookup failed",
                      exc_info=True)

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
                # Webify UI-6 fix: BountyContract's fields are
                # `claimed_by` + status "claimed" (BountyStatus.CLAIMED,
                # a str-enum). The old `accepted_by`/"accepted" check
                # matched no contract ever, so the bounty job never
                # appeared in the HUD.
                if (getattr(c, "claimed_by", None) == char_id_str and
                        getattr(c, "status", "") == "claimed"):
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
        # Webify UI-6: single orientation line for the vitals card.
        # "" = nothing to surface (client hides the box).
        hud["objective"] = _objective_line(jobs)

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

    async def _hud_sidebar_onboarding(self, char) -> None:
        """Webify UI-7: push onboarding_state for the training panel.

        Active chain → push every tick (idempotent render). Graduated →
        push ONCE, gated on the `_last_chain_step` memo showing the chain
        was active this session; then clear the memo so reconnects after
        graduation stay silent. No chain ever → nothing.
        """
        from engine.chain_events import build_onboarding_state
        payload = build_onboarding_state(char)
        if payload is None:
            self._last_chain_step = None
            return
        if payload.get("active"):
            self._last_chain_step = (payload.get("chain_id"),
                                     payload.get("step"))
            await self.send_json("onboarding_state", payload)
            return
        # Graduated payload: only on the active→graduated transition.
        if payload.get("graduated") and self._last_chain_step is not None:
            self._last_chain_step = None
            await self.send_json("onboarding_state", payload)

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

    async def _hud_sidebar_region(self, db, room_id) -> None:
        """Send a region_state sidebar message when the player stands in a
        wilderness region (UI-2 Region panel).

        City / ship / interior rooms carry no ``wilderness_region_id`` and so
        emit nothing — the web Region panel hides itself. This is add-beside:
        the region description prose still flows through the live stream and
        the ``region`` text command, so the Telnet path is untouched.
        """
        try:
            room = await db.get_room(room_id)
        except Exception:
            room = None
        region_slug = (room or {}).get("wilderness_region_id")
        if not region_slug:
            return
        from engine.territory_display import get_region_data_block
        viewer_org = (self.character or {}).get("faction_id") or None
        block = await get_region_data_block(
            db, region_slug, viewer_org_code=viewer_org,
        )
        await self._send(json.dumps({
            "type": "region_state",
            "region": block,
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

        # ── 13b. City (Phase 6 web UI) ──
        if db:
            try:
                await self._hud_city(hud, db, char, room_id)
            except Exception:
                log.warning("send_hud_update: city failed",
                            exc_info=True)

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
                await self._hud_area_map(hud, db, room_id, session_mgr=session_mgr)
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
        # Webify UI-7: onboarding/training panel (needs only char — no db).
        if char_id:
            try:
                await self._hud_sidebar_onboarding(char)
            except Exception:
                log.debug("send_hud_update: sidebar onboarding failed",
                          exc_info=True)
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

            try:
                await self._hud_sidebar_region(db, room_id)
            except Exception:
                pass  # Wilderness-region tables may not exist

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

    def sessions_in_room(self, room_id: int, *, source_char=None) -> list["Session"]:
        """Get all sessions with characters in a given room.

        Args:
            room_id: the room id to filter on.
            source_char: optional character dict. If provided AND that
                character is in wilderness, results are further filtered
                to sessions whose character has matching wilderness coords.
                Path B (W.2 phase 2): every PC↔PC ground interaction
                that calls this with `source_char=char` automatically
                respects wilderness co-location. Default behavior
                (no source_char) is unchanged.
        """
        sessions = [
            s for s in self._sessions.values()
            if s.is_in_game and s.character and s.character.get("room_id") == room_id
        ]
        if source_char is None:
            return sessions
        try:
            from engine.wilderness_movement import filter_by_source_location
            return filter_by_source_location(
                sessions, source_char, get_char=lambda s: s.character,
            )
        except Exception:
            # Defensive fallback: if the helper isn't available, return
            # the room-only filtered list. Better to over-broadcast than
            # to silently break.
            return sessions

    async def broadcast(self, text: str, exclude: Optional[Session] = None):
        """Send a message to all in-game sessions."""
        for s in self._sessions.values():
            if s.is_in_game and s is not exclude:
                await s.send_line(text)

    async def broadcast_to_room(
        self, room_id: int, text: str,
        exclude=None,
        source_char=None,
    ):
        """Send text to all sessions in a room.

        Args:
            exclude: Session object, list of character IDs to skip, or None.
            source_char: optional character dict. When the source is in
                wilderness, broadcast is restricted to characters at the
                same wilderness tile (Path B / W.2 phase 2). Without
                this kwarg, every PC in the wilderness sentinel would
                receive the message regardless of their tile, which is
                exactly the bug we're closing.

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
        for s in self.sessions_in_room(room_id, source_char=source_char):
            if excluded_sess is not None and s is excluded_sess:
                continue
            if s.character and s.character.get("id") in excluded_ids:
                continue
            targets.append(s.send_line(text))

        if targets:
            await asyncio.gather(*targets, return_exceptions=True)

    async def broadcast_json_to_room(
        self, room_id: int, msg_type: str, data: dict,
        exclude=None,
        source_char=None,
    ):
        """Send a typed JSON message to all WebSocket sessions in a room.

        Telnet sessions render typed messages with a known fallback (e.g.
        pose_event becomes formatted text); see Session.send_json. Other
        msg_types may be silently dropped on Telnet.

        Used for combat_state, space_state, pose_event, and other
        structured updates.

        Args:
            exclude: Session object, list of character IDs to skip, or
                None. Mirrors broadcast_to_room's contract so callers can
                avoid echoing a typed event back to the originating
                session (e.g. the actor of a `say` doesn't need to receive
                their own pose_event — they already got the self-echo).
            source_char: optional character dict. Same semantics as
                broadcast_to_room — wilderness-aware co-location filter.

        Drop B': `exclude` parameter added so the player-narration
        migration (say/whisper/emote/mutter) can broadcast the typed
        pose_event to observers while the actor's send_line self-echo
        remains the only thing they see locally. Mirrors broadcast_to_room.

        W.2 phase 2: `source_char` parameter added for wilderness
        co-location filtering.
        """
        excluded_ids: set[int] = set()
        excluded_sess: Optional["Session"] = None
        if isinstance(exclude, list):
            excluded_ids = set(exclude)
        elif exclude is not None:
            excluded_sess = exclude

        targets = []
        for s in self.sessions_in_room(room_id, source_char=source_char):
            if excluded_sess is not None and s is excluded_sess:
                continue
            if s.character and s.character.get("id") in excluded_ids:
                continue
            targets.append(s.send_json(msg_type, data))
        if targets:
            await asyncio.gather(*targets, return_exceptions=True)

    async def broadcast_chat(
        self, channel: str, from_name: str, text: str,
        room_id: int = None, exclude=None,
        source_char=None,
    ):
        """Send a structured chat message to WebSocket clients.

        Sends a parallel 'chat' JSON message alongside normal text output.
        WebSocket clients route this to the appropriate comms tab.
        Telnet clients ignore it entirely (they already got the text via
        broadcast_to_room or send_line).

        channel: 'ic' | 'ooc' | 'sys'

        Args:
            source_char: optional. When set and the source is in wilderness,
                room-scoped chat is restricted to PCs at the same tile
                (W.2 phase 2). For OOC channels and global broadcasts,
                source_char is ignored.
        """
        payload = {"channel": channel, "from": from_name, "text": text}
        if room_id is not None:
            excluded_ids: set[int] = set()
            excluded_sess = None
            if isinstance(exclude, list):
                excluded_ids = set(exclude)
            elif exclude is not None:
                excluded_sess = exclude
            for s in self.sessions_in_room(room_id, source_char=source_char):
                if excluded_sess is not None and s is excluded_sess:
                    continue
                if s.character and s.character.get("id") in excluded_ids:
                    continue
                await s.send_json("chat", payload)
        else:
            # Broadcast to all connected sessions
            for s in self._sessions:
                await s.send_json("chat", payload)
