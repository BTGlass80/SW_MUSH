"""
engine/npc_space_traffic.py
NPC Space Traffic System — Drop 1
Zone-based model: ships have a current_zone string, movement is tick-based transitions
between named zones rather than room walking.

Drop 1 content:
  - Zone model (ZoneType, Zone, ZONES dict, SPAWN_ZONES)
  - TrafficArchetype / TrafficState enums
  - TrafficShip dataclass
  - NpcSpaceTrafficManager: spawn, despawn, tick, get_zone_ships
  - Trader archetype (TRANSIT, IDLE, DOCKING states)
  - BAY_PLANET_MAP for launch/land zone lookup
  - Schema v3 migration hook (bounty column) handled in db/database.py
"""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# TUNING CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

MAX_TRAFFIC_SHIPS       = 8      # global cap
SPAWN_INTERVAL_SECS     = 60     # seconds between spawn attempts
ZONE_TRANSIT_SECS       = 30     # seconds to move between adjacent zones
BASE_LIFETIME_MIN       = 600    # 10 min minimum ship lifetime
BASE_LIFETIME_MAX       = 1200   # 20 min maximum ship lifetime
HAIL_TIMEOUT_SECS       = 30     # no-reply treated as refusal after this
PIRATE_FLEE_HULL_PCT    = 30     # pirate flees below this hull %
HUNTER_FLEE_HULL_PCT    = 25     # bounty hunter flees below this hull %
HUNTER_RESPAWN_DELAY    = 300    # seconds before hunter can respawn
PIRATE_CREDIT_MIN       = 500
PIRATE_CREDIT_MAX       = 1500

IDLE_MIN_SECS           = 30     # minimum loiter time in a zone
IDLE_MAX_SECS           = 180    # maximum loiter time in a zone
DOCK_MIN_SECS           = 120    # minimum docking time (trader/smuggler)
DOCK_MAX_SECS           = 300    # maximum docking time

# ─────────────────────────────────────────────────────────────────────────────
# ZONE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class ZoneType(Enum):
    ORBIT           = "orbit"
    DEEP_SPACE      = "deep_space"
    HYPERSPACE_LANE = "hyperspace_lane"
    DOCK            = "dock"


@dataclass
class Zone:
    id:       str
    name:     str
    type:     ZoneType
    adjacent: list          # list of zone id strings
    planet:   Optional[str] = None
    desc:     str = ""


# All zones in the galaxy. Adding a new planet = add entries here, nothing else.
ZONES: dict[str, Zone] = {
    # ── Tatooine ─────────────────────────────────────────────────────────────
    "tatooine_dock": Zone(
        id="tatooine_dock",
        name="Mos Eisley Approach",
        type=ZoneType.DOCK,
        planet="tatooine",
        adjacent=["tatooine_orbit"],
        desc="The approach corridor to Mos Eisley's docking bays. "
             "Customs transponders ping constantly.",
    ),
    "tatooine_orbit": Zone(
        id="tatooine_orbit",
        name="Tatooine Orbit",
        type=ZoneType.ORBIT,
        planet="tatooine",
        adjacent=["tatooine_dock", "tatooine_deep_space"],
        desc="Low orbit above Tatooine's amber deserts. "
             "Twin suns glare off the hull plating.",
    ),
    "tatooine_deep_space": Zone(
        id="tatooine_deep_space",
        name="Tatooine Deep Space",
        type=ZoneType.DEEP_SPACE,
        planet="tatooine",
        adjacent=["tatooine_orbit", "outer_rim_lane_1"],
        desc="The dark space beyond Tatooine's gravity well. "
             "Rocky debris drifts in slow silence.",
    ),
    # ── Hyperspace lanes ─────────────────────────────────────────────────────
    "outer_rim_lane_1": Zone(
        id="outer_rim_lane_1",
        name="Outer Rim Lane — Tatooine Corridor",
        type=ZoneType.HYPERSPACE_LANE,
        adjacent=["tatooine_deep_space"],
        desc="A well-traveled hyperspace corridor along the Outer Rim. "
             "Ships streak past in blue-white flashes.",
    ),
    # ── Future planets (add here when ready) ─────────────────────────────────
    # "nar_shaddaa_dock":       Zone(..., adjacent=["nar_shaddaa_orbit"]),
    # "nar_shaddaa_orbit":      Zone(..., adjacent=["nar_shaddaa_dock", "nar_shaddaa_deep_space"]),
    # "nar_shaddaa_deep_space": Zone(..., adjacent=["nar_shaddaa_orbit", "outer_rim_lane_1"]),
}

# Zones eligible for random traffic spawn
SPAWN_ZONES = ["tatooine_deep_space", "outer_rim_lane_1"]

# Maps docking bay room names (lowercase substrings) → planet orbit zone id.
# Used by launch command to assign current_zone without hardcoding.
# Add entries when new planets are built.
BAY_PLANET_MAP = {
    "tatooine": "tatooine_orbit",
    "mos eisley": "tatooine_orbit",
    "docking bay": "tatooine_orbit",   # default fallback for Mos Eisley bays
}

def get_orbit_zone_for_room(room_name: str) -> str:
    """Return the orbit zone id for the planet this docking bay is on."""
    name_lower = room_name.lower()
    for key, zone_id in BAY_PLANET_MAP.items():
        if key in name_lower:
            return zone_id
    return "tatooine_orbit"  # safe fallback


def get_deep_space_zone_for_orbit(orbit_zone_id: str) -> str:
    """Return deep space zone adjacent to a given orbit zone."""
    zone = ZONES.get(orbit_zone_id)
    if zone:
        for adj_id in zone.adjacent:
            adj = ZONES.get(adj_id)
            if adj and adj.type == ZoneType.DEEP_SPACE:
                return adj_id
    return "tatooine_deep_space"


def find_path(start: str, end: str) -> list[str]:
    """BFS shortest path between two zone ids. Returns list of zone ids to visit
    (not including start, including end). Returns [] if no path found."""
    if start == end:
        return []
    from collections import deque
    visited = {start}
    queue = deque([(start, [])])
    while queue:
        current, path = queue.popleft()
        zone = ZONES.get(current)
        if not zone:
            continue
        for adj_id in zone.adjacent:
            if adj_id == end:
                return path + [adj_id]
            if adj_id not in visited:
                visited.add(adj_id)
                queue.append((adj_id, path + [adj_id]))
    return []


# ─────────────────────────────────────────────────────────────────────────────
# ARCHETYPES & STATES
# ─────────────────────────────────────────────────────────────────────────────

class TrafficArchetype(Enum):
    TRADER        = "trader"
    SMUGGLER      = "smuggler"
    PATROL        = "patrol"
    PIRATE        = "pirate"
    BOUNTY_HUNTER = "bounty_hunter"


class TrafficState(Enum):
    TRANSIT   = "transit"    # moving between zones
    IDLE      = "idle"       # loitering
    TAILING   = "tailing"    # following a player ship
    FLEEING   = "fleeing"    # running to exit
    HAILING   = "hailing"    # sent hail, awaiting reply
    ATTACKING = "attacking"  # in active combat
    DOCKING   = "docking"    # simulating docked status


# ─────────────────────────────────────────────────────────────────────────────
# SHIP TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

TRAFFIC_SHIP_TEMPLATES = {
    TrafficArchetype.TRADER: [
        {
            "name_pool": [
                "Starlight Wanderer", "Dusty Horizon", "Bright Passage",
                "Lucky Meridian", "Harvest Wind", "Corellian Promise",
                "Iron Pilgrim", "Safe Harbor",
            ],
            "template": "yt1300",
            "transponder": "registered",   # shown as real name in sensors
            "crew_skill": "3D",
            "captain_name_pool": [
                "Capt. Lenn Tarso", "Capt. Vela Doon", "Capt. Mira Foss",
                "Capt. Okar Neb",  "Capt. Sila Vren",
            ],
        },
    ],
    TrafficArchetype.SMUGGLER: [
        {
            "name_pool": [
                "Void Dancer", "Fast Meridian", "Slippery Chance",
                "Night Runner", "Quick Profit", "Gray Ghost",
            ],
            "template": "yt1300",
            "transponder": "spoofed",
            "crew_skill": "4D",
            "captain_name_pool": [
                "A Smooth Operator", "A Nervous Pilot", "A Gruff Smuggler",
            ],
        },
    ],
    TrafficArchetype.PATROL: [
        {
            "name_pool": [
                "Imperial Patrol TK-{n}", "ISB Patrol {n}", "Sector Patrol {n}",
            ],
            "template": "tie_fighter",
            "transponder": "official",
            "crew_skill": "3D+2",
            "captain_name_pool": ["Lieutenant Varsk", "Sergeant Holt", "Corporal Renn"],
        },
    ],
    TrafficArchetype.PIRATE: [
        {
            "name_pool": [
                "Krag's Fist", "Void Reaper", "Rust Claw",
                "Black Comet", "Screaming Mynock", "Iron Talon",
            ],
            "template": "z95",
            "transponder": "none",
            "crew_skill": "4D",
            "captain_name_pool": [
                "Krag the Terrible", "One-Eye Dozz", "Mara the Knife",
                "Captain Skorn",
            ],
        },
    ],
    TrafficArchetype.BOUNTY_HUNTER: [
        {
            "name_pool": [
                "Shadow Talon", "Crimson Pursuit", "Dust Reaper",
                "Iron Bounty", "Silent Contract",
            ],
            "template": "firespray",
            "transponder": "hunter",
            "crew_skill": "5D",
            "captain_name_pool": [
                "Zek Varro", "Dara Hess", "The Mandalorian", "Boba Fett",
            ],
        },
    ],
}

# Archetype spawn weights (must sum to 100 for clean math, but we normalize anyway)
TRAFFIC_WEIGHTS = {
    TrafficArchetype.TRADER:        40,
    TrafficArchetype.SMUGGLER:      20,
    TrafficArchetype.PATROL:        15,
    TrafficArchetype.PIRATE:        15,
    TrafficArchetype.BOUNTY_HUNTER: 10,  # only used for random; hunters normally event-driven
}


# ─────────────────────────────────────────────────────────────────────────────
# TRAFFIC SHIP DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrafficShip:
    ship_id:                  int
    archetype:                TrafficArchetype
    state:                    TrafficState
    current_zone:             str
    # routing
    route:                    list = field(default_factory=list)  # remaining zone ids to visit
    transit_elapsed:          float = 0.0   # seconds spent in current transit
    # timing
    spawned_at:               float = field(default_factory=time.time)
    max_lifetime:             float = BASE_LIFETIME_MIN
    state_entered_at:         float = field(default_factory=time.time)
    state_duration:           float = 0.0   # how long to stay in current state (0 = indefinite)
    # interaction
    hail_sent:                bool = False
    hail_timeout:             float = 0.0
    bounty_target_char_id:    Optional[int] = None
    # display
    display_name:             str = "Unknown Ship"
    transponder_type:         str = "registered"
    captain_name:             str = "Unknown"

    def age(self) -> float:
        return time.time() - self.spawned_at

    def state_age(self) -> float:
        return time.time() - self.state_entered_at

    def is_expired(self) -> bool:
        return self.age() >= self.max_lifetime

    def enter_state(self, state: TrafficState, duration: float = 0.0):
        self.state = state
        self.state_entered_at = time.time()
        self.state_duration = duration
        self.transit_elapsed = 0.0

    def sensors_name(self) -> str:
        """Return the transponder display name shown in sensors output."""
        if self.transponder_type == "registered":
            return self.display_name
        elif self.transponder_type == "spoofed":
            return "Unknown freighter"
        elif self.transponder_type == "official":
            return self.display_name
        elif self.transponder_type == "none":
            return "Unregistered fighter"
        elif self.transponder_type == "hunter":
            return f"Pursuit vessel ({self.display_name})"
        return self.display_name

    def to_json(self) -> dict:
        return {
            "archetype":             self.archetype.value,
            "state":                 self.state.value,
            "current_zone":          self.current_zone,
            "route":                 self.route,
            "transit_elapsed":       self.transit_elapsed,
            "spawned_at":            self.spawned_at,
            "max_lifetime":          self.max_lifetime,
            "state_entered_at":      self.state_entered_at,
            "state_duration":        self.state_duration,
            "hail_sent":             self.hail_sent,
            "hail_timeout":          self.hail_timeout,
            "bounty_target_char_id": self.bounty_target_char_id,
            "display_name":          self.display_name,
            "transponder_type":      self.transponder_type,
            "captain_name":          self.captain_name,
        }

    @classmethod
    def from_json(cls, ship_id: int, data: dict) -> "TrafficShip":
        return cls(
            ship_id=ship_id,
            archetype=TrafficArchetype(data["archetype"]),
            state=TrafficState(data["state"]),
            current_zone=data["current_zone"],
            route=data.get("route", []),
            transit_elapsed=data.get("transit_elapsed", 0.0),
            spawned_at=data.get("spawned_at", time.time()),
            max_lifetime=data.get("max_lifetime", BASE_LIFETIME_MIN),
            state_entered_at=data.get("state_entered_at", time.time()),
            state_duration=data.get("state_duration", 0.0),
            hail_sent=data.get("hail_sent", False),
            hail_timeout=data.get("hail_timeout", 0.0),
            bounty_target_char_id=data.get("bounty_target_char_id"),
            display_name=data.get("display_name", "Unknown Ship"),
            transponder_type=data.get("transponder_type", "registered"),
            captain_name=data.get("captain_name", "Unknown"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: random weighted archetype pick
# ─────────────────────────────────────────────────────────────────────────────

def _pick_archetype(exclude_hunter: bool = True) -> TrafficArchetype:
    pool = {k: v for k, v in TRAFFIC_WEIGHTS.items()
            if not (exclude_hunter and k == TrafficArchetype.BOUNTY_HUNTER)}
    total = sum(pool.values())
    r = random.randint(1, total)
    cumulative = 0
    for archetype, weight in pool.items():
        cumulative += weight
        if r <= cumulative:
            return archetype
    return TrafficArchetype.TRADER


def _make_ship_name(template: dict) -> str:
    name = random.choice(template["name_pool"])
    if "{n}" in name:
        name = name.replace("{n}", str(random.randint(1000, 9999)))
    return name


def _make_captain_name(template: dict) -> str:
    return random.choice(template["captain_name_pool"])


# ─────────────────────────────────────────────────────────────────────────────
# TRAFFIC MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class NpcSpaceTrafficManager:
    """
    Manages all NPC traffic ships. Called every tick from game_server.py.
    Ships are stored in memory (_ships dict) and persisted to ships.systems_json['traffic'].
    On server restart, _load_from_db() recovers in-flight traffic ships.
    """

    def __init__(self):
        self._ships: dict[int, TrafficShip] = {}   # ship_id → TrafficShip
        self._last_spawn_time: float = 0.0
        self._loaded: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    def get_zone_ships(self, zone_id: str) -> list[TrafficShip]:
        """Return all traffic ships currently in the given zone."""
        return [s for s in self._ships.values() if s.current_zone == zone_id]

    def get_ship(self, ship_id: int) -> Optional[TrafficShip]:
        return self._ships.get(ship_id)

    def get_ship_by_name(self, name: str) -> Optional[TrafficShip]:
        """Case-insensitive name lookup for comms targeting."""
        name_lower = name.lower()
        for ship in self._ships.values():
            if name_lower in ship.display_name.lower():
                return ship
        return None

    async def spawn_bounty_hunter(self, char_id: int, db, session_mgr) -> Optional[TrafficShip]:
        """
        Spawn a bounty hunter targeting char_id.
        Called from game_server when a player acquires a bounty.
        Bypasses MAX_TRAFFIC_SHIPS cap.
        """
        return await self._spawn(db, session_mgr,
                                  archetype=TrafficArchetype.BOUNTY_HUNTER,
                                  bounty_target=char_id)

    async def tick(self, db, session_mgr):
        """Called every second from game_server tick loop."""
        if not self._loaded:
            await self._load_from_db(db)
            self._loaded = True

        now = time.time()

        # ── Spawn attempt ─────────────────────────────────────────────────────
        if now - self._last_spawn_time >= SPAWN_INTERVAL_SECS:
            self._last_spawn_time = now
            if len(self._ships) < MAX_TRAFFIC_SHIPS:
                await self._spawn(db, session_mgr)

        # ── Tick each ship ────────────────────────────────────────────────────
        to_despawn = []
        for ship_id, ship in list(self._ships.items()):
            try:
                should_despawn = await self._tick_ship(ship, db, session_mgr)
                if should_despawn:
                    to_despawn.append(ship_id)
                else:
                    await self._persist_ship(ship, db)
            except Exception as e:
                log.error(f"[traffic] tick error ship {ship_id}: {e}", exc_info=True)

        for ship_id in to_despawn:
            await self._despawn(ship_id, db, session_mgr)

    # ── Spawn ─────────────────────────────────────────────────────────────────

    async def _spawn(self, db, session_mgr,
                     archetype: Optional[TrafficArchetype] = None,
                     bounty_target: Optional[int] = None) -> Optional[TrafficShip]:
        if archetype is None:
            archetype = _pick_archetype()

        templates = TRAFFIC_SHIP_TEMPLATES.get(archetype, [])
        if not templates:
            return None
        tmpl = random.choice(templates)

        ship_name    = _make_ship_name(tmpl)
        captain_name = _make_captain_name(tmpl)
        spawn_zone   = random.choice(SPAWN_ZONES)

        # Create ship in DB
        try:
            ship_id = await db.create_traffic_ship(
                name=ship_name,
                template=tmpl["template"],
            )
        except Exception as e:
            log.error(f"[traffic] failed to create ship record: {e}")
            return None

        # Create captain NPC
        try:
            await db.create_traffic_npc(
                name=captain_name,
                ship_id=ship_id,
                skill=tmpl["crew_skill"],
            )
        except Exception as e:
            log.warning(f"[traffic] failed to create captain NPC: {e}")

        lifetime = random.uniform(BASE_LIFETIME_MIN, BASE_LIFETIME_MAX)

        ts = TrafficShip(
            ship_id=ship_id,
            archetype=archetype,
            state=TrafficState.IDLE,
            current_zone=spawn_zone,
            spawned_at=time.time(),
            max_lifetime=lifetime,
            display_name=ship_name,
            transponder_type=tmpl["transponder"],
            captain_name=captain_name,
            bounty_target_char_id=bounty_target,
        )

        # Set initial route based on archetype
        self._set_initial_route(ts)
        self._ships[ship_id] = ts
        await self._persist_ship(ts, db)

        # Announce to players in spawn zone
        await self._announce_to_zone(
            spawn_zone,
            f"  [SENSORS] A ship drops out of hyperspace nearby.",
            session_mgr, db,
        )

        log.info(f"[traffic] spawned {archetype.value} '{ship_name}' in {spawn_zone}")
        return ts

    def _set_initial_route(self, ts: TrafficShip):
        """Set the initial route for a newly spawned ship based on archetype."""
        if ts.archetype == TrafficArchetype.TRADER:
            # Head to dock, loiter, then leave
            ts.route = ["tatooine_orbit", "tatooine_dock"]
            ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
        elif ts.archetype == TrafficArchetype.SMUGGLER:
            ts.route = ["tatooine_deep_space", "tatooine_dock"]
            ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
        elif ts.archetype == TrafficArchetype.PATROL:
            # Patrol circuit: orbit → deep_space → orbit → ...
            ts.route = ["tatooine_orbit"]
            ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
        elif ts.archetype == TrafficArchetype.PIRATE:
            # Pirates start lurking in deep space
            if ts.current_zone != "tatooine_deep_space":
                ts.route = ["tatooine_deep_space"]
                ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
            else:
                idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
                ts.enter_state(TrafficState.IDLE, duration=idle_dur)
        else:
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ts.enter_state(TrafficState.IDLE, duration=idle_dur)

    # ── Per-ship tick ─────────────────────────────────────────────────────────

    async def _tick_ship(self, ship: TrafficShip, db, session_mgr) -> bool:
        """
        Evaluate one ship for one tick. Returns True if the ship should despawn.
        """
        # Lifetime check
        if ship.is_expired():
            await self._begin_wind_down(ship, db, session_mgr)

        if ship.state == TrafficState.TRANSIT:
            return await self._tick_transit(ship, db, session_mgr)
        elif ship.state == TrafficState.IDLE:
            return await self._tick_idle(ship, db, session_mgr)
        elif ship.state == TrafficState.DOCKING:
            return await self._tick_docking(ship, db, session_mgr)
        elif ship.state == TrafficState.FLEEING:
            return await self._tick_fleeing(ship, db, session_mgr)
        # HAILING, TAILING, ATTACKING handled in later drops
        return False

    async def _tick_transit(self, ship: TrafficShip, db, session_mgr) -> bool:
        ship.transit_elapsed += 1.0  # called once per second

        if ship.transit_elapsed < ZONE_TRANSIT_SECS:
            return False

        # Arrived at next zone in route
        if not ship.route:
            # No more route — go idle
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ship.enter_state(TrafficState.IDLE, duration=idle_dur)
            return False

        destination = ship.route.pop(0)
        ship.current_zone = destination

        await self._announce_to_zone(
            destination,
            f"  [SENSORS] {ship.sensors_name()} enters the area.",
            session_mgr, db,
        )

        # Decide what to do on arrival
        zone = ZONES.get(destination)
        if zone and zone.type == ZoneType.DOCK:
            if ship.archetype in (TrafficArchetype.TRADER, TrafficArchetype.SMUGGLER):
                dock_dur = random.uniform(DOCK_MIN_SECS, DOCK_MAX_SECS)
                ship.enter_state(TrafficState.DOCKING, duration=dock_dur)
                return False

        if ship.route:
            ship.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
        else:
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ship.enter_state(TrafficState.IDLE, duration=idle_dur)

        return False

    async def _tick_idle(self, ship: TrafficShip, db, session_mgr) -> bool:
        if ship.state_duration > 0 and ship.state_age() >= ship.state_duration:
            # Idle timer expired — decide next action
            self._plan_next_move(ship)
        return False

    async def _tick_docking(self, ship: TrafficShip, db, session_mgr) -> bool:
        if ship.state_duration > 0 and ship.state_age() >= ship.state_duration:
            # Done docking — build departure route
            self._plan_departure(ship)
        return False

    async def _tick_fleeing(self, ship: TrafficShip, db, session_mgr) -> bool:
        ship.transit_elapsed += 1.0
        if ship.transit_elapsed < ZONE_TRANSIT_SECS:
            return False

        if not ship.route:
            # Reached exit zone — despawn
            await self._announce_to_zone(
                ship.current_zone,
                f"  [SENSORS] {ship.sensors_name()} accelerates away and jumps to hyperspace.",
                session_mgr, db,
            )
            return True  # signal despawn

        destination = ship.route.pop(0)
        ship.current_zone = destination
        ship.transit_elapsed = 0.0

        if not ship.route:
            await self._announce_to_zone(
                destination,
                f"  [SENSORS] {ship.sensors_name()} accelerates away and jumps to hyperspace.",
                session_mgr, db,
            )
            return True

        return False

    # ── Route planning ────────────────────────────────────────────────────────

    def _plan_next_move(self, ship: TrafficShip):
        """After idle, decide where to go next based on archetype."""
        if ship.archetype == TrafficArchetype.TRADER:
            if ship.current_zone == "tatooine_deep_space":
                # Head to dock
                ship.route = ["tatooine_orbit", "tatooine_dock"]
                ship.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
            else:
                # Head out
                self._plan_departure(ship)

        elif ship.archetype == TrafficArchetype.PIRATE:
            # Pirates just keep lurking
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ship.enter_state(TrafficState.IDLE, duration=idle_dur)

        else:
            # Generic: head toward exit
            self._plan_departure(ship)

    def _plan_departure(self, ship: TrafficShip):
        """Route ship toward the nearest exit zone for wind-down."""
        # Find path to tatooine_deep_space → outer_rim_lane_1
        path = find_path(ship.current_zone, "outer_rim_lane_1")
        if path:
            ship.route = path
        else:
            ship.route = ["tatooine_deep_space"]
        ship.enter_state(TrafficState.FLEEING, duration=0)

    async def _begin_wind_down(self, ship: TrafficShip, db, session_mgr):
        """Start the departure sequence for a ship that's lived long enough."""
        if ship.state not in (TrafficState.FLEEING,):
            self._plan_departure(ship)

    # ── Despawn ───────────────────────────────────────────────────────────────

    async def _despawn(self, ship_id: int, db, session_mgr):
        ship = self._ships.pop(ship_id, None)
        if not ship:
            return
        try:
            await db.delete_traffic_ship(ship_id)
        except Exception as e:
            log.error(f"[traffic] despawn DB error for ship {ship_id}: {e}")
        log.info(f"[traffic] despawned '{ship.display_name}' ({ship.archetype.value})")

    # ── Persistence ───────────────────────────────────────────────────────────

    async def _persist_ship(self, ship: TrafficShip, db):
        """Write current traffic state back to systems_json['traffic'] in DB."""
        try:
            await db.update_traffic_ship_state(ship.ship_id, ship.to_json())
        except Exception as e:
            log.error(f"[traffic] persist error ship {ship.ship_id}: {e}")

    async def _load_from_db(self, db):
        """Load any surviving traffic ships from DB on server start/restart."""
        try:
            rows = await db.get_all_traffic_ships()
            for row in rows:
                row = dict(row)
                systems = json.loads(row.get("systems") or "{}")
                traffic_data = systems.get("traffic")
                if traffic_data:
                    ts = TrafficShip.from_json(row["id"], traffic_data)
                    self._ships[row["id"]] = ts
            if self._ships:
                log.info(f"[traffic] recovered {len(self._ships)} traffic ships from DB")
        except Exception as e:
            log.error(f"[traffic] load_from_db error: {e}")

    # ── Zone messaging ────────────────────────────────────────────────────────

    async def _announce_to_zone(self, zone_id: str, message: str, session_mgr, db):
        """Send a message to all player sessions whose ship is in the given zone."""
        try:
            sessions = list(session_mgr.all)
            for session in sessions:
                char = getattr(session, "character", None)
                if not char:
                    continue
                # Check if player is aboard a ship in this zone
                ship_id = await _get_player_ship_zone_ship_id(session, db)
                if ship_id is None:
                    continue
                ship_row = await db.get_ship(ship_id)
                if not ship_row:
                    continue
                systems = json.loads(dict(ship_row).get("systems") or "{}")
                if systems.get("current_zone") == zone_id:
                    await session.send_line(message)
        except Exception as e:
            log.error(f"[traffic] announce error: {e}")


async def _get_player_ship_zone_ship_id(session, db) -> Optional[int]:
    """Return the ship_id of the ship the player is currently aboard (in space)."""
    char = getattr(session, "character", None)
    if not char:
        return None
    # Check all ships for this player as crew/pilot
    ships = await db.get_ships_in_space()
    for ship in ships:
        ship = dict(ship)
        crew = json.loads(ship.get("crew") or "{}")
        char_id = char["id"]
        if char_id in crew.values():
            return ship["id"]
    return None


# Module-level singleton
_traffic_manager: Optional[NpcSpaceTrafficManager] = None

def get_traffic_manager() -> NpcSpaceTrafficManager:
    global _traffic_manager
    if _traffic_manager is None:
        _traffic_manager = NpcSpaceTrafficManager()
    return _traffic_manager
