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
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.era_validator import era_violations

log = logging.getLogger(__name__)

# ── Constants ──

# Timer range per room (seconds)
MIN_INTERVAL = 120   # 2 minutes
MAX_INTERVAL = 300   # 5 minutes

# Ratio: chance of drawing from a LIVE line (Director dynamic + Ollama idle
# pools) when any exists; otherwise the static YAML pool is used.
DYNAMIC_DRAW_RATIO = 0.3

# Max Ollama-generated ambient lines kept per zone (the idle-queue feeder).
MAX_IDLE_LINES_PER_ZONE = 8

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
    # GCW-era zone names (build_mos_eisley.py descriptive names → short keys)
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
    # CW-era zone slugs (zones.yaml key → ambient_events.yaml pool key).
    # Only needed where slug != pool key; same-name slugs fall through to
    # the direct-name fallback in _resolve_zone_key.
    "kamino_tipoca_city": "kamino_tipoca",
    "kamino_cloning_halls": "kamino_training",
    "kamino_ocean_platform": "kamino_ocean",
    "geonosis_petranaki": "geonosis_arena",
    "geonosis_surface": "geonosis_wastes",
    "geonosis_deep_hive": "geonosis_tunnels",
    "geonosis_barracks": "geonosis_arena",    # gladiator barracks ≈ arena tone
    "geonosis_ey_akh": "geonosis_wastes",    # open desert ≈ wastes tone
    "kdy_orbital_ring": "kuat_orbital",
    "kuat_city_embassy": "kuat_surface",
    "kuat_main_spaceport": "kuat_transit",
    "coruscant_underworld": "southern_underground",
    "entertainment_district": "commercial_district",
}


def _resolve_zone_key(zone_name: Optional[str]) -> str:
    """Map a DB zone name to a YAML ambient pool key.

    Tries in order:
    1. Explicit lookup in _ZONE_NAME_TO_KEY (handles GCW descriptive names
       and CW slug→key mismatches).
    2. Substring fallback against _ZONE_NAME_TO_KEY keys.
    3. Return the normalized zone name directly — CW zone slugs whose slug
       equals their ambient pool key (senate_district, jedi_temple, space_*)
       are resolved this way; _pick_line falls back to "default" if the key
       has no pool entry.
    """
    if not zone_name:
        return "default"
    normalized = zone_name.lower().strip()
    key = _ZONE_NAME_TO_KEY.get(normalized)
    if key:
        return key
    # Substring fallback (handles partial GCW zone name variants)
    for pattern, mapped_key in _ZONE_NAME_TO_KEY.items():
        if pattern in normalized:
            return mapped_key
    # Direct name fallback: CW zone slugs that match their pool key verbatim
    return normalized


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
        # Ollama-generated ambient lines (the idle-queue AmbientFlavorTask).
        # SEPARATE from _dynamic_pool (the Director's Haiku lines) so the two
        # LLM writers never clobber each other; _pick_line draws from both.
        self._idle_pool: dict[str, list[AmbientLine]] = {}
        self._idle_pool_ts: dict[str, float] = {}  # zone_key -> last gen time
        self._room_timers: dict[int, RoomTimer] = {}
        self._zone_cache: dict[int, str] = {}  # zone_id -> zone_key
        # Per-room static ambient lines from wilderness_ambient_lines room property.
        # Cached permanently (wilderness rooms never change their authored lines).
        self._room_ambient_cache: dict[int, list] = {}
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
        dropped = 0
        for zone_key, lines in lines_by_zone.items():
            validated, d = self._validate_lines(lines)
            dropped += d
            if validated:
                self._dynamic_pool[zone_key] = validated
        if dropped:
            log.info("[ambient] Dropped %d off-era dynamic line(s)", dropped)
        if self._dynamic_pool:
            total = sum(len(v) for v in self._dynamic_pool.values())
            log.info("[ambient] Dynamic pool updated: %d lines", total)

    def _validate_lines(self, lines) -> tuple[list[AmbientLine], int]:
        """Validate + era-guard raw LLM ambient lines into AmbientLine objects.

        Returns ``(kept, dropped_count)``. Drops empties, >120-char lines, and
        any line failing the shared `engine.era_validator` guard — these lines
        are LLM-generated and reach every player in a room, so a GCW-era leak
        ("Imperial patrols…") must never enter a pool. Shared by both LLM
        writers: the Director's `set_dynamic_pool` and the Ollama feeder's
        `set_idle_pool`.
        """
        kept: list[AmbientLine] = []
        dropped = 0
        for line in lines:
            line = (line or "").strip()
            if not line or len(line) > 120:
                continue
            if era_violations(line):
                dropped += 1
                continue
            kept.append(AmbientLine(text=line))
        return kept, dropped

    def set_idle_pool(self, zone_key: str, lines: list) -> int:
        """Replace the Ollama-generated idle ambient lines for one zone.

        Called by the idle-queue ``AmbientFlavorTask``. Validated + era-guarded
        through the SAME `_validate_lines` path as the Director pool, and capped
        at ``MAX_IDLE_LINES_PER_ZONE``. Stored in `_idle_pool` (separate from the
        Director's `_dynamic_pool`) so the two writers never clobber; `_pick_line`
        draws from both. Always stamps the refresh timestamp (even when every
        line was dropped) so a garbage batch isn't retried immediately. Returns
        the number of lines kept.
        """
        validated, dropped = self._validate_lines(lines)
        if validated:
            self._idle_pool[zone_key] = validated[:MAX_IDLE_LINES_PER_ZONE]
        else:
            self._idle_pool.pop(zone_key, None)
        self._idle_pool_ts[zone_key] = time.time()
        kept = len(self._idle_pool.get(zone_key, []))
        if dropped:
            log.info("[ambient] Dropped %d off-era idle line(s) for zone %s",
                     dropped, zone_key)
        if kept:
            log.info("[ambient] Idle pool for %s: %d Ollama line(s)",
                     zone_key, kept)
        return kept

    def idle_pool_needs_refresh(self, zone_key: str, max_age_secs: float) -> bool:
        """True if `zone_key` has no Ollama idle lines yet or they're stale."""
        if zone_key not in self._idle_pool_ts:
            return True
        return (time.time() - self._idle_pool_ts.get(zone_key, 0.0)) > max_age_secs

    async def _get_room_ambient_lines(self, room_id: int, db) -> list:
        """Return authored AmbientLine objects from a room's wilderness_ambient_lines property.

        Result is cached permanently (wilderness rooms don't change their authored lines).
        Returns an empty list for non-wilderness rooms or rooms with no authored lines.
        """
        if room_id in self._room_ambient_cache:
            return self._room_ambient_cache[room_id]
        lines: list[AmbientLine] = []
        try:
            room = await db.get_room(room_id)
            if room:
                raw_props = room.get("properties") or "{}"
                try:
                    props = json.loads(raw_props) if isinstance(raw_props, str) else (raw_props or {})
                except Exception:
                    props = {}
                for text in (props.get("wilderness_ambient_lines") or []):
                    text = str(text).strip()
                    if text:
                        lines.append(AmbientLine(text=text))
        except Exception as _e:
            log.debug("_get_room_ambient_lines: failed to load room %s ambient lines: %s", room_id, _e)
        self._room_ambient_cache[room_id] = lines
        return lines

    def _pick_line(self, zone_key: str, room_lines: Optional[list] = None) -> Optional[str]:
        """
        Pick a weighted random ambient line for a zone.
        70% chance static pool, 30% chance a LIVE line — the Director's dynamic
        pool and the Ollama idle pool combined — when any live line exists.
        Per-room authored lines (room_lines) are merged into the static pool.
        """
        live = (self._dynamic_pool.get(zone_key, [])
                + self._idle_pool.get(zone_key, []))
        use_live = bool(live) and random.random() < DYNAMIC_DRAW_RATIO

        if use_live:
            pool = live
        else:
            pool = list(self._static_pool.get(zone_key) or self._static_pool.get("default") or [])
            if room_lines:
                pool = pool + list(room_lines)
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
                room_lines = await self._get_room_ambient_lines(room_id, db)
                line = self._pick_line(zone_key, room_lines=room_lines)
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
