# -*- coding: utf-8 -*-
"""
Ambient Room Events — atmospheric flavor text for occupied rooms.

Fires a random one-liner to all players in a room every 2–5 minutes.
Two pools:
  1. Static pool from data/ambient_events.yaml (always available)
  2. Dynamic pool set by Director AI (refreshed each Faction Turn)

If the dynamic pool is empty, draws exclusively from static.
Draw ratio when dynamic pool exists: 70% static, 30% dynamic.

Zone key mapping:
  The YAML keys match ROOM_ZONES values in build_mos_eisley.py:
    spaceport, streets, cantina, shops, jabba, government
  Rooms whose zone doesn't match any key use the "default" pool.
  Rooms with no zone_id also use "default".

Files:
  engine/ambient_events.py   (this file)
  data/ambient_events.yaml   (static pool data)
"""
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Constants ──

# Timer range per room (seconds)
MIN_INTERVAL = 120   # 2 minutes
MAX_INTERVAL = 300   # 5 minutes

# Ratio: chance of drawing from dynamic pool when it's available
DYNAMIC_DRAW_RATIO = 0.3

# ANSI formatting for ambient text
AMBIENT_COLOR = "\033[2;37m"   # dim white
AMBIENT_RESET = "\033[0m"

# ── Data structures ──

@dataclass
class AmbientLine:
    """A single ambient event line with probability weight."""
    text: str
    weight: float = 1.0


@dataclass
class RoomTimer:
    """Tracks when a room should next fire an ambient event."""
    room_id: int
    next_fire: float = 0.0   # time.time() value

    def reset(self):
        """Set next fire time to a random interval from now."""
        self.next_fire = time.time() + random.uniform(MIN_INTERVAL, MAX_INTERVAL)


# ── Zone key resolution ──

# Maps zone DB names (from create_zone calls in build_mos_eisley.py) to
# ambient YAML keys. This handles the fact that DB zone names are
# descriptive ("Spaceport District") while YAML keys are short ("spaceport").
# The ROOM_ZONES dict in build_mos_eisley.py uses the short keys directly,
# but we resolve via DB zone names since that's what rooms store.

_ZONE_NAME_TO_KEY: dict[str, str] = {
    # These are the zone names created by build_mos_eisley.py
    "spaceport district": "spaceport",
    "spaceport": "spaceport",
    "central streets": "streets",
    "streets": "streets",
    "cantina district": "cantina",
    "cantina": "cantina",
    "commercial district": "shops",
    "shops": "shops",
    "jabba's territory": "jabba",
    "jabba": "jabba",
    "government district": "government",
    "government": "government",
    # Fallback aliases for any naming variation
    "residential": "streets",
    "market": "streets",
    "industrial": "shops",
    "outskirts": "default",
    "docking": "spaceport",
}


def _resolve_zone_key(zone_name: Optional[str]) -> str:
    """Map a DB zone name to a YAML ambient pool key."""
    if not zone_name:
        return "default"
    key = _ZONE_NAME_TO_KEY.get(zone_name.lower().strip())
    if key:
        return key
    # Try substring match as last resort
    name_lower = zone_name.lower()
    for pattern, mapped_key in _ZONE_NAME_TO_KEY.items():
        if pattern in name_lower:
            return mapped_key
    return "default"


# ── Manager ──

class AmbientEventManager:
    """
    Singleton that manages ambient flavor text for all occupied rooms.

    Called from the game_server tick loop. On each tick:
      1. Find all rooms with online players
      2. Check if any room's timer has expired
      3. If so, pick a random line from the appropriate zone pool
      4. Broadcast it to the room
      5. Reset that room's timer
    """

    def __init__(self):
        self._static_pool: dict[str, list[AmbientLine]] = {}
        self._dynamic_pool: dict[str, list[AmbientLine]] = {}
        self._room_timers: dict[int, RoomTimer] = {}
        self._zone_cache: dict[int, str] = {}  # zone_id -> zone_key
        self._loaded = False

    def _load_yaml(self):
        """Load static ambient events.

        Drop F.6a.4-int wire-up: reads through `ambient_pools_loader` to
        get an era-aware merged view of the static pool. When the active
        era flag (`Config.use_yaml_director_data`) is off — which is the
        default — `resolve_era_for_seeding` returns None, and the seam
        returns the legacy `data/ambient_events.yaml` byte-for-byte
        unchanged (pinned by tests/test_f6a4_int_byte_equivalence.py).

        When the flag is on, the seam additionally merges the
        era-specific `data/worlds/<era>/ambient_events.yaml` on top of
        legacy. Era-specific zone keys win on collision; legacy zone
        keys not redefined by the era continue to be served from the
        legacy file.
        """
        from engine.ambient_pools_loader import get_ambient_pools
        from engine.era_state import get_seeding_era

        # F.6a.7 Phase 1 (Apr 29 2026): switched from
        # resolve_era_for_seeding() (returned None when
        # use_yaml_director_data was off) to get_seeding_era()
        # (returns the active era unconditionally). The YAML path is
        # now the production path for ambient pools too. The
        # get_ambient_pools() era=None branch falls back to the
        # legacy flat data/ambient_events.yaml if YAML load fails for
        # any reason, so this remains safe.
        era = get_seeding_era()
        try:
            merged = get_ambient_pools(era=era)
        except Exception as e:
            log.error(
                "[ambient] Failed to resolve ambient pools (era=%s): %s",
                era, e,
            )
            self._loaded = True
            return

        # Convert AmbientLineTuple -> AmbientLine for the engine's
        # internal pool representation. Field names match exactly, so
        # the conversion is mechanical.
        total_lines = 0
        for zone_key, lines in merged.pools.items():
            converted = [
                AmbientLine(text=ln.text, weight=ln.weight) for ln in lines
            ]
            if converted:
                self._static_pool[zone_key] = converted
                total_lines += len(converted)

        log.info(
            "[ambient] Loaded %d static lines across %d zones (source=%s)",
            total_lines, len(self._static_pool), merged.source,
        )
        self._loaded = True

    def set_dynamic_pool(self, lines_by_zone: dict[str, list[str]]):
        """
        Replace the dynamic ambient pool. Called by DirectorAI after
        each Faction Turn. Pass an empty dict to clear.

        Args:
            lines_by_zone: {"cantina": ["line1", "line2"], ...}
        """
        self._dynamic_pool.clear()
        for zone_key, lines in lines_by_zone.items():
            validated = []
            for line in lines:
                # Content safety: max length, no game commands
                line = line.strip()
                if not line or len(line) > 120:
                    continue
                validated.append(AmbientLine(text=line))
            if validated:
                self._dynamic_pool[zone_key] = validated
        if self._dynamic_pool:
            total = sum(len(v) for v in self._dynamic_pool.values())
            log.info("[ambient] Dynamic pool updated: %d lines", total)

    def _pick_line(self, zone_key: str) -> Optional[str]:
        """
        Pick a weighted random ambient line for a zone.
        70% chance static pool, 30% chance dynamic pool (if available).
        """
        has_dynamic = zone_key in self._dynamic_pool
        use_dynamic = has_dynamic and random.random() < DYNAMIC_DRAW_RATIO

        if use_dynamic:
            pool = self._dynamic_pool[zone_key]
        else:
            pool = self._static_pool.get(zone_key)
            if not pool:
                pool = self._static_pool.get("default")
            if not pool:
                return None

        # Weighted random selection
        weights = [line.weight for line in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        return chosen.text

    async def _get_zone_key(self, room_id: int, db) -> str:
        """Resolve a room's zone_id to an ambient pool key, with caching."""
        # Check cache first
        if room_id in self._zone_cache:
            return self._zone_cache[room_id]

        room = await db.get_room(room_id)
        if not room or not room.get("zone_id"):
            self._zone_cache[room_id] = "default"
            return "default"

        zone_id = room["zone_id"]
        zone = await db.get_zone(zone_id)
        if not zone:
            self._zone_cache[room_id] = "default"
            return "default"

        key = _resolve_zone_key(zone.get("name", ""))
        self._zone_cache[room_id] = key
        return key

    async def tick(self, db, session_mgr):
        """
        Called every tick (1s) from game_server tick loop.
        Checks occupied rooms and fires ambient events on expired timers.
        """
        if not self._loaded:
            self._load_yaml()

        # No static pool = nothing to do
        if not self._static_pool:
            return

        now = time.time()

        # Find all rooms with online players
        occupied_rooms: set[int] = set()
        for session in session_mgr.all:
            if (session.is_in_game
                    and session.character
                    and session.character.get("room_id")):
                occupied_rooms.add(session.character["room_id"])

        # Clean up timers for rooms no longer occupied
        stale = [rid for rid in self._room_timers if rid not in occupied_rooms]
        for rid in stale:
            del self._room_timers[rid]

        # Check each occupied room
        for room_id in occupied_rooms:
            timer = self._room_timers.get(room_id)
            if timer is None:
                # First time seeing this room — set a timer
                timer = RoomTimer(room_id=room_id)
                timer.reset()
                self._room_timers[room_id] = timer
                continue

            if now < timer.next_fire:
                continue

            # Timer expired — fire an ambient event
            try:
                zone_key = await self._get_zone_key(room_id, db)
                line = self._pick_line(zone_key)
                if line:
                    # Drop B: emit as typed pose_event (mode='ambient')
                    # to all clients in the room. WebSocket gets typed
                    # JSON for proper attribution; Telnet falls back to
                    # styled text via send_json. This replaces the old
                    # broadcast_to_room(formatted) path that hit
                    # classifyAndAppend on the client and risked
                    # mis-rendering ambient flavor as dialogue.
                    from engine.pose_events import make_ambient_event
                    ev = make_ambient_event(line)
                    await session_mgr.broadcast_json_to_room(
                        room_id, "pose_event", ev
                    )
            except Exception:
                log.debug("[ambient] Error firing ambient for room %d", room_id,
                          exc_info=True)

            # Reset timer regardless of success
            timer.reset()


# ── Module-level singleton ──

_manager: Optional[AmbientEventManager] = None


def get_ambient_manager() -> AmbientEventManager:
    """Get or create the global AmbientEventManager."""
    global _manager
    if _manager is None:
        _manager = AmbientEventManager()
    return _manager
