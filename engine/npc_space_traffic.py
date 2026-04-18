"""
engine/npc_space_traffic.py
NPC Space Traffic System — Drop 4
Zone-based model: ships have a current_zone string, movement is tick-based transitions
between named zones rather than room walking.

Drop 1: Zone model, TrafficManager scaffold, Trader archetype.
Drop 2: Smuggler + Imperial Patrol, comms intercept (hail/comms commands).
Drop 3: Pirate tailing, demand hail, credit reward on destroy, PayCommand.
Drop 4 additions:
  - Bounty Hunter archetype: event-driven spawn, navigates to target's zone
  - Personalized hail naming the bounty target by character name
  - Hunter-only tailing: only attacks the bounty target, ignores others
  - Hunter respawn: 5-minute cooldown before re-spawning after flee/destroy
  - NpcSpaceTrafficManager tracks pending respawns per char_id
  - spawn_bounty_hunter() expanded: resolves target zone, sends entry hail
  - @setbounty admin command in space_commands for testing
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
    security: str = ""      # "secured", "contested", "lawless" — empty = derive from type
    hazards:  dict = None   # e.g. {"asteroid_density": "heavy", "nav_modifier": 5, "sensor_penalty": 2}

    def __post_init__(self):
        if self.hazards is None:
            self.hazards = {}


# All zones in the galaxy. Adding a new planet = add entries here, nothing else.
ZONES: dict[str, Zone] = {
    # ── Tatooine ─────────────────────────────────────────────────────────────
    "tatooine_dock": Zone(
        id="tatooine_dock",
        name="Mos Eisley Approach",
        type=ZoneType.DOCK,
        planet="tatooine",
        adjacent=["tatooine_orbit"],
        security="secured",
        desc="The approach corridor to Mos Eisley's docking bays. "
             "Customs transponders ping constantly.",
    ),
    "tatooine_orbit": Zone(
        id="tatooine_orbit",
        name="Tatooine Orbit",
        type=ZoneType.ORBIT,
        planet="tatooine",
        adjacent=["tatooine_dock", "tatooine_deep_space"],
        security="contested",
        desc="Low orbit above Tatooine's amber deserts. "
             "Twin suns glare off the hull plating.",
    ),
    "tatooine_deep_space": Zone(
        id="tatooine_deep_space",
        name="Tatooine Deep Space",
        type=ZoneType.DEEP_SPACE,
        planet="tatooine",
        adjacent=["tatooine_orbit", "outer_rim_lane_1"],
        security="lawless",
        desc="The dark space beyond Tatooine's gravity well. "
             "Rocky debris drifts in slow silence.",
    ),
    # ── Hyperspace lanes ─────────────────────────────────────────────────────
    "outer_rim_lane_1": Zone(
        id="outer_rim_lane_1",
        name="Outer Rim Lane — Tatooine Corridor",
        type=ZoneType.HYPERSPACE_LANE,
        adjacent=["tatooine_deep_space", "outer_rim_lane_2"],
        security="contested",
        desc="A well-traveled hyperspace corridor along the Outer Rim. "
             "Ships streak past in blue-white flashes.",
    ),
    # ── Nar Shaddaa — Smuggler's Moon ────────────────────────────────────────
    "nar_shaddaa_dock": Zone(
        id="nar_shaddaa_dock",
        name="Nar Shaddaa Landing Platform",
        type=ZoneType.DOCK,
        planet="nar_shaddaa",
        adjacent=["nar_shaddaa_orbit"],
        security="contested",
        desc="The grimy docking platforms of Nar Shaddaa. Neon advertisements "
             "flicker over stacked landing pads. Everyone here has a price.",
    ),
    "nar_shaddaa_orbit": Zone(
        id="nar_shaddaa_orbit",
        name="Nar Shaddaa Orbit",
        type=ZoneType.ORBIT,
        planet="nar_shaddaa",
        adjacent=["nar_shaddaa_dock", "nar_shaddaa_deep_space"],
        security="contested",
        desc="Tight orbital lanes above the Smuggler's Moon. Freighters jostle "
             "for position. Hutt patrol barges enforce their own kind of order.",
    ),
    "nar_shaddaa_deep_space": Zone(
        id="nar_shaddaa_deep_space",
        name="Nar Shaddaa Deep Space",
        type=ZoneType.DEEP_SPACE,
        planet="nar_shaddaa",
        adjacent=["nar_shaddaa_orbit", "outer_rim_lane_2"],
        security="lawless",
        desc="The open space beyond Nar Shaddaa's gravity well. "
             "Hutt space sprawls in every direction.",
    ),
    # ── Kessel — Spice Mines ─────────────────────────────────────────────────
    "kessel_dock": Zone(
        id="kessel_dock",
        name="Kessel Spaceport",
        type=ZoneType.DOCK,
        planet="kessel",
        adjacent=["kessel_orbit"],
        security="contested",
        desc="A rough-hewn spaceport carved into Kessel's dark surface. "
             "Imperial garrison towers overlook every pad. "
             "Spice processing plants hum in the distance.",
    ),
    "kessel_orbit": Zone(
        id="kessel_orbit",
        name="Kessel Orbit",
        type=ZoneType.ORBIT,
        planet="kessel",
        adjacent=["kessel_dock", "kessel_approach"],
        security="contested",
        desc="Thin orbit over Kessel's dark surface. The Maw Cluster glows "
             "ominously to port — a wall of swirling gas and gravitational anomalies.",
    ),
    "kessel_approach": Zone(
        id="kessel_approach",
        name="Kessel Approach — The Maw Corridor",
        type=ZoneType.DEEP_SPACE,
        planet="kessel",
        adjacent=["kessel_orbit", "outer_rim_lane_3"],
        security="lawless",
        desc="The treacherous corridor between Kessel and open space. "
             "Asteroid debris and gravitational eddies from the Maw "
             "make navigation a white-knuckle affair.",
        hazards={"asteroid_density": "heavy", "nav_modifier": 5, "sensor_penalty": 2},
    ),
    # ── Corellia — Shipyard Capital ──────────────────────────────────────────
    "corellia_dock": Zone(
        id="corellia_dock",
        name="Coronet City Spaceport",
        type=ZoneType.DOCK,
        planet="corellia",
        adjacent=["corellia_orbit"],
        security="secured",
        desc="One of the galaxy's great spaceports. CEC shipyard gantries frame "
             "the skyline. CorSec patrols keep a firm but negotiable order.",
    ),
    "corellia_orbit": Zone(
        id="corellia_orbit",
        name="Corellia Orbit",
        type=ZoneType.ORBIT,
        planet="corellia",
        adjacent=["corellia_dock", "corellia_deep_space"],
        security="secured",
        desc="Busy orbital lanes around the shipbuilding capital. "
             "CEC drydocks and orbital stations dot the view.",
    ),
    "corellia_deep_space": Zone(
        id="corellia_deep_space",
        name="Corellian System — Deep Space",
        type=ZoneType.DEEP_SPACE,
        planet="corellia",
        adjacent=["corellia_orbit", "corellian_trade_spine"],
        security="contested",
        desc="Open space at the edge of the Corellian system. "
             "The Corellian Trade Spine beckons toward the Core.",
    ),
    # ── Hyperspace lanes (expanded) ──────────────────────────────────────────
    "outer_rim_lane_2": Zone(
        id="outer_rim_lane_2",
        name="Outer Rim Lane — Hutt Space Corridor",
        type=ZoneType.HYPERSPACE_LANE,
        adjacent=["outer_rim_lane_1", "nar_shaddaa_deep_space", "outer_rim_lane_3"],
        security="lawless",
        desc="The hyperspace corridor linking the Outer Rim to Hutt Space. "
             "Smuggler traffic is heavy. Navigation beacons are unreliable.",
    ),
    "outer_rim_lane_3": Zone(
        id="outer_rim_lane_3",
        name="Outer Rim Lane — Kessel Run Approach",
        type=ZoneType.HYPERSPACE_LANE,
        adjacent=["outer_rim_lane_2", "kessel_approach"],
        security="lawless",
        desc="The notorious approach corridor toward the Kessel system. "
             "The Maw's gravity shadows make this stretch genuinely dangerous.",
        hazards={"asteroid_density": "light", "nav_modifier": 2},
    ),
    "corellian_trade_spine": Zone(
        id="corellian_trade_spine",
        name="Corellian Trade Spine",
        type=ZoneType.HYPERSPACE_LANE,
        adjacent=["corellia_deep_space", "outer_rim_lane_1"],
        security="contested",
        desc="One of the galaxy's major trade arteries. Heavy freighter traffic "
             "and Imperial customs interdiction make this a busy corridor.",
    ),
}

# Zones eligible for random traffic spawn
SPAWN_ZONES = [
    "tatooine_deep_space", "outer_rim_lane_1",
    "nar_shaddaa_deep_space", "outer_rim_lane_2",
    "kessel_approach", "corellia_deep_space",
]

# Maps docking bay room names (lowercase substrings) → planet orbit zone id.
# Used by launch command to assign current_zone without hardcoding.
# Add entries when new planets are built.
BAY_PLANET_MAP = {
    "tatooine": "tatooine_orbit",
    "mos eisley": "tatooine_orbit",
    "docking bay": "tatooine_orbit",   # default fallback for Mos Eisley bays
    "nar shaddaa": "nar_shaddaa_orbit",
    "smuggler": "nar_shaddaa_orbit",
    "kessel": "kessel_orbit",
    "coronet": "corellia_orbit",
    "corellia": "corellia_orbit",
}

def get_orbit_zone_for_room(room_name: str) -> str:
    """Return the orbit zone id for the planet this docking bay is on."""
    name_lower = room_name.lower()
    for key, zone_id in BAY_PLANET_MAP.items():
        if key in name_lower:
            return zone_id
    return "tatooine_orbit"  # safe fallback


# ── Space Security ───────────────────────────────────────────────────────────
# Per-zone security levels control encounter rates, PvP rules, and loot
# quality. Mirrors the ground security system (engine/security.py) but
# uses explicit per-zone assignments rather than room property inheritance.
#
# Security hierarchy:
#   secured   — No combat. Defense grid / CorSec / port authority.
#   contested — NPC combat allowed. PvP requires consent.
#   lawless   — Unrestricted PvP. No authority presence.
#
# See space_overhaul_v3_design.md §4 for full design rationale.

_ZONE_TYPE_DEFAULT_SECURITY = {
    ZoneType.DOCK:            "secured",
    ZoneType.ORBIT:           "contested",
    ZoneType.HYPERSPACE_LANE: "contested",
    ZoneType.DEEP_SPACE:      "lawless",
}

# Director-driven transient overrides: zone_id → security string
_space_security_overrides: dict[str, str] = {}


def set_space_security_override(zone_id: str, level: str | None) -> None:
    """Set (or clear with None) a transient Director-driven security override."""
    if level is None:
        _space_security_overrides.pop(zone_id, None)
    else:
        _space_security_overrides[zone_id] = level
    log.info("[space_security] zone %s override → %s", zone_id, level)


def clear_space_security_overrides() -> None:
    """Clear all transient space security overrides (e.g. on restart)."""
    _space_security_overrides.clear()


def get_space_security(zone_id: str) -> str:
    """Return effective security level for a space zone.

    Resolution order:
      1. Transient Director override (set via world events / faction turns)
      2. Explicit zone.security field (per-planet profile)
      3. Fallback: derive from zone type (legacy behavior)

    Returns: "secured" | "contested" | "lawless"
    """
    # 1. Director override
    override = _space_security_overrides.get(zone_id)
    if override:
        return override

    # 2. Zone-level explicit security
    zone = ZONES.get(zone_id)
    if zone and zone.security:
        return zone.security

    # 3. Fallback: derive from zone type
    if zone:
        return _ZONE_TYPE_DEFAULT_SECURITY.get(zone.type, "contested")

    return "lawless"  # unknown zone = fail-open


# ── Security-aware encounter rates ───────────────────────────────────────────
# Keyed by security level. Values are relative weights for archetype selection.
# These replace the flat archetype weights for zone-aware spawning.

ENCOUNTER_RATES_BY_SECURITY = {
    "secured": {
        "patrol":  35,
        "pirate":  2,
        "trader":  25,
        "smuggler": 5,
        "hunter":  3,
    },
    "contested": {
        "patrol":  15,
        "pirate":  15,
        "trader":  15,
        "smuggler": 15,
        "hunter":  10,
    },
    "lawless": {
        "patrol":  5,
        "pirate":  30,
        "trader":  8,
        "smuggler": 20,
        "hunter":  15,
    },
}

# Anomaly quality multiplier by security level.
# Affects salvage value and rare component drop rates.
ANOMALY_QUALITY_MULT = {
    "secured":   0.5,
    "contested": 1.0,
    "lawless":   2.0,
}


def get_archetype_weights_for_zone(zone_id: str) -> dict:
    """Return archetype spawn weights adjusted for zone security level.

    Maps security-level encounter rates to TrafficArchetype weights
    for use by the existing _pick_archetype() weighted random selection.
    Returns a dict of {TrafficArchetype: int_weight}.
    """
    sec = get_space_security(zone_id)
    rates = ENCOUNTER_RATES_BY_SECURITY.get(sec, ENCOUNTER_RATES_BY_SECURITY["contested"])

    return {
        TrafficArchetype.PATROL:        rates["patrol"],
        TrafficArchetype.PIRATE:        rates["pirate"],
        TrafficArchetype.TRADER:        rates["trader"],
        TrafficArchetype.SMUGGLER:      rates["smuggler"],
        TrafficArchetype.BOUNTY_HUNTER: rates["hunter"],
    }


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

def _pick_archetype() -> TrafficArchetype:
    weights = dict(TRAFFIC_WEIGHTS)
    try:
        from engine.world_events import get_world_event_manager
        mult = get_world_event_manager().get_effect('patrol_spawn_mult', 1.0)
        if mult != 1.0:
            weights[TrafficArchetype.PATROL] = int(weights[TrafficArchetype.PATROL] * mult)
    except Exception:
        log.warning("_pick_archetype: unhandled exception", exc_info=True)
        pass
    archetypes = list(weights.keys())
    return random.choices(archetypes, weights=[weights[a] for a in archetypes], k=1)[0]


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
    # Drop 2: comms / hail state
    hail_pending:             bool = False        # True while waiting for player reply
    hail_source_char_id:      Optional[int] = None  # char_id that sent the hail we're waiting on
    patrol_fight_rounds:      int = 0            # smuggler: count rounds of combat before fleeing
    patrol_zone_index:        int = 0            # patrol: index into its circuit list
    # Drop 3: pirate tailing
    tailing_ship_id:          Optional[int] = None  # player ship_id being tailed
    pirate_demand_credits:    int = 0            # credit amount demanded from player
    pirate_paid:              bool = False       # True once player has paid
    # Drop 4: bounty hunter
    bounty_target_name:       str = ""          # character name of the bounty target
    hunter_hail_sent:         bool = False      # True after personalized hail fired
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
            "hail_pending":          self.hail_pending,
            "hail_source_char_id":   self.hail_source_char_id,
            "patrol_fight_rounds":   self.patrol_fight_rounds,
            "patrol_zone_index":     self.patrol_zone_index,
            "tailing_ship_id":       self.tailing_ship_id,
            "pirate_demand_credits": self.pirate_demand_credits,
            "pirate_paid":           self.pirate_paid,
            "bounty_target_name":    self.bounty_target_name,
            "hunter_hail_sent":      self.hunter_hail_sent,
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
            hail_pending=data.get("hail_pending", False),
            hail_source_char_id=data.get("hail_source_char_id"),
            patrol_fight_rounds=data.get("patrol_fight_rounds", 0),
            patrol_zone_index=data.get("patrol_zone_index", 0),
            tailing_ship_id=data.get("tailing_ship_id"),
            pirate_demand_credits=data.get("pirate_demand_credits", 0),
            pirate_paid=data.get("pirate_paid", False),
            bounty_target_name=data.get("bounty_target_name", ""),
            hunter_hail_sent=data.get("hunter_hail_sent", False),
            display_name=data.get("display_name", "Unknown Ship"),
            transponder_type=data.get("transponder_type", "registered"),
            captain_name=data.get("captain_name", "Unknown"),
        )


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: random weighted archetype pick
# ─────────────────────────────────────────────────────────────────────────────

def _pick_archetype(exclude_hunter: bool = True,
                           zone_id: str = "") -> TrafficArchetype:
    # Use zone-aware weights if zone_id provided (Drop 0: space security)
    if zone_id:
        pool = get_archetype_weights_for_zone(zone_id)
        if exclude_hunter:
            pool.pop(TrafficArchetype.BOUNTY_HUNTER, None)
    else:
        pool = {k: v for k, v in TRAFFIC_WEIGHTS.items()
                if not (exclude_hunter and k == TrafficArchetype.BOUNTY_HUNTER)}
    total = sum(pool.values())
    if total <= 0:
        return TrafficArchetype.TRADER
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
        # Drop 4: tracks when a hunter for a given char_id may respawn
        self._hunter_respawns: dict[int, float] = {}  # char_id → earliest respawn time

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

    async def spawn_bounty_hunter(self, char_id: int, db, session_mgr,
                                   target_name: str = "") -> Optional["TrafficShip"]:
        """
        Spawn a bounty hunter targeting char_id.
        Called from game_server (or @setbounty admin command) when a player acquires a bounty.
        Bypasses MAX_TRAFFIC_SHIPS cap. Respawn cooldown enforced.
        """
        now = time.time()
        cooldown_until = self._hunter_respawns.get(char_id, 0.0)
        if now < cooldown_until:
            remaining = int(cooldown_until - now)
            log.info(f"[traffic] bounty hunter for char {char_id} on cooldown ({remaining}s)")
            return None

        ts = await self._spawn(db, session_mgr,
                               archetype=TrafficArchetype.BOUNTY_HUNTER,
                               bounty_target=char_id)
        if ts is None:
            return None

        ts.bounty_target_name = target_name
        ts.bounty_target_char_id = char_id

        # Navigate to the target's current zone if we can find them
        target_zone = await self._find_char_zone(char_id, db)
        if target_zone and target_zone != ts.current_zone:
            path = find_path(ts.current_zone, target_zone)
            if path:
                ts.route = path
                ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)

        # Announce entry to the target's zone (or spawn zone if target unknown)
        announce_zone = target_zone or ts.current_zone
        name_str = f" for {target_name}" if target_name else ""
        await self._announce_to_zone(
            announce_zone,
            f"  {ansi_yellow}[SENSORS]{ansi_reset} A pursuit vessel drops out of hyperspace"
            f"{name_str}. Its transponder reads: {ts.sensors_name()}.",
            session_mgr, db,
        )
        log.info(f"[traffic] bounty hunter '{ts.display_name}' spawned targeting char {char_id}"
                 f" ({target_name})")
        return ts

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

        # ── Bounty hunter respawn check ───────────────────────────────────────
        for char_id, respawn_at in list(self._hunter_respawns.items()):
            if now >= respawn_at:
                del self._hunter_respawns[char_id]
                # Check char still has a bounty (col added in schema v3)
                try:
                    char_row = await db.get_character(char_id)
                    if char_row and dict(char_row).get("bounty", 0):
                        target_name = dict(char_row).get("name", "")
                        await self.spawn_bounty_hunter(char_id, db, session_mgr,
                                                       target_name=target_name)
                except Exception as e:
                    log.error(f"[traffic] hunter respawn check error char {char_id}: {e}")

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
                     bounty_target: Optional[int] = None,
                     force_zone: Optional[str] = None) -> Optional[TrafficShip]:
        spawn_zone = force_zone or random.choice(SPAWN_ZONES)

        if archetype is None:
            archetype = _pick_archetype(zone_id=spawn_zone)

        templates = TRAFFIC_SHIP_TEMPLATES.get(archetype, [])
        if not templates:
            return None
        tmpl = random.choice(templates)

        ship_name    = _make_ship_name(tmpl)
        captain_name = _make_captain_name(tmpl)

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
            # Smugglers avoid ORBIT zones — go straight to DOCK via deep space
            ts.route = ["tatooine_deep_space", "tatooine_dock"]
            ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
        elif ts.archetype == TrafficArchetype.PATROL:
            # Patrol circuit: deep_space → orbit → deep_space → ...
            # Store circuit as a repeating list; patrol_zone_index tracks position
            ts.route = _build_patrol_circuit()
            ts.patrol_zone_index = 0
            if ts.route:
                ts.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
            else:
                idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
                ts.enter_state(TrafficState.IDLE, duration=idle_dur)
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
        elif ship.state == TrafficState.HAILING:
            return await self._tick_hailing(ship, db, session_mgr)
        elif ship.state == TrafficState.TAILING:
            return await self._tick_tailing(ship, db, session_mgr)
        # ATTACKING handled in later drops
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
        # Patrol: scan for players in zone → create encounter (Drop 2)
        if ship.archetype == TrafficArchetype.PATROL and not ship.hail_sent:
            players_in_zone = await self._get_players_in_zone(ship.current_zone, db, session_mgr)
            if players_in_zone:
                player_session, player_ship_name = players_in_zone[0]
                # Use the new encounter system instead of the old hail flow
                created = await self._create_patrol_encounter(
                    ship, player_session, player_ship_name, db, session_mgr)
                if created:
                    ship.hail_sent = True
                    # Patrol enters HAILING state so it doesn't re-trigger
                    ship.enter_state(TrafficState.HAILING, duration=120)
                return False

        # Pirate: spot a player ship in zone → create encounter (Drop 4)
        # Cap: at most 1 pirate actively tailing/hailing per zone.
        if ship.archetype == TrafficArchetype.PIRATE and ship.tailing_ship_id is None:
            _active_pirates = sum(
                1 for _ts in self._ships.values()
                if _ts.ship_id != ship.ship_id
                and _ts.archetype == TrafficArchetype.PIRATE
                and _ts.current_zone == ship.current_zone
                and _ts.state in (TrafficState.TAILING, TrafficState.HAILING)
            )
            player_ships = [] if _active_pirates >= 1 else (
                await self._get_players_in_zone(ship.current_zone, db, session_mgr)
            )
            if player_ships:
                player_session, player_ship_name = player_ships[0]
                target_ship_id = await _get_player_ship_zone_ship_id(player_session, db)
                if target_ship_id:
                    created = await self._create_pirate_encounter(
                        ship, target_ship_id, player_ship_name, db, session_mgr)
                    if created:
                        ship.tailing_ship_id = target_ship_id
                        ship.enter_state(TrafficState.HAILING, duration=120)
                    return False

        # Bounty hunter: navigate toward target's zone
        if ship.archetype == TrafficArchetype.BOUNTY_HUNTER and ship.bounty_target_char_id:
            target_zone = await self._find_char_zone(ship.bounty_target_char_id, db)
            if target_zone and target_zone != ship.current_zone:
                path = find_path(ship.current_zone, target_zone)
                if path:
                    ship.route = path
                    ship.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
                    return False
            elif target_zone == ship.current_zone:
                # Target is here — start tailing immediately
                target_ship_id = await self._find_char_ship_id(ship.bounty_target_char_id, db)
                if target_ship_id:
                    ship.tailing_ship_id = target_ship_id
                    ship.enter_state(TrafficState.TAILING, duration=0)
                    return False

        if ship.state_duration > 0 and ship.state_age() >= ship.state_duration:
            self._plan_next_move(ship)
        return False

    async def _tick_hailing(self, ship: TrafficShip, db, session_mgr) -> bool:
        """Waiting for a player reply. Time out after HAIL_TIMEOUT_SECS."""
        if ship.state_age() >= HAIL_TIMEOUT_SECS:
            # No reply — treat as refusal
            if ship.archetype == TrafficArchetype.PATROL:
                # Drop 2: encounters handle their own timeout via EncounterManager.
                # The patrol just needs to resume its route after the encounter resolves.
                # Check if the encounter is still active:
                from engine.space_encounters import get_encounter_manager
                mgr = get_encounter_manager()
                # If encounter already resolved (player responded), move on
                # If encounter still active, it handles its own deadline
                ship.hail_sent = False
                ship.hail_pending = False
                self._plan_next_move(ship)
                return False
            elif ship.archetype == TrafficArchetype.PIRATE:
                # Drop 4: encounters handle their own timeout via EncounterManager.
                # The pirate just resumes normal behavior after the encounter resolves.
                ship.tailing_ship_id = None
                ship.hail_sent = False
                ship.hail_pending = False
                idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
                ship.enter_state(TrafficState.IDLE, duration=idle_dur)
                return False
            elif ship.archetype == TrafficArchetype.BOUNTY_HUNTER:
                # No surrender → hunter attacks
                await self._announce_to_zone(
                    ship.current_zone,
                    f"  {ansi_yellow}[COMMS]{ansi_reset} {ship.sensors_name()}: "
                    f"\"Surrender refused. Lethal force authorized.\"",
                    session_mgr, db,
                )
                await self._announce_to_zone(
                    ship.current_zone,
                    f"  {ansi_yellow}[ALERT]{ansi_reset} {ship.sensors_name()} "
                    f"locks weapons on you! Use 'fire', 'flee', or 'evade'.",
                    session_mgr, db,
                )
                log.info(f"[traffic] hunter '{ship.display_name}' attacking bounty target")
                ship.tailing_ship_id = None
                ship.hunter_hail_sent = False
                idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
                ship.enter_state(TrafficState.IDLE, duration=idle_dur)
                ship.hail_sent = False
                ship.hail_pending = False
                return False
            elif ship.archetype == TrafficArchetype.SMUGGLER:
                pass
            ship.hail_sent = False
            ship.hail_pending = False
            ship.hail_source_char_id = None
            self._plan_next_move(ship)
        return False

    async def _run_boarding_inspection(
        self, ship: TrafficShip, db, session_mgr
    ) -> None:
        """Imperial patrol boarding inspection after failed hail.

        Finds all player ships in the patrol zone, checks each for
        contraband / false transponder, and applies a WEG40141 infraction
        fine.  Falls back to a Class-5 non-compliance fine on a clean ship.
        """
        import random as _rand
        INFRACTION = {
            5: {"name": "Class Five",  "fine": (100,  500),   "arrest": 0.00},
            4: {"name": "Class Four",  "fine": (1000, 5000),  "arrest": 0.05},
            3: {"name": "Class Three", "fine": (2500, 5000),  "arrest": 0.20},
            2: {"name": "Class Two",   "fine": (5000, 10000), "arrest": 0.40},
            1: {"name": "Class One",   "fine": (0,    0),     "arrest": 1.00},
        }
        RED   = "\033[1;31m"
        AMBER = "\033[1;33m"
        DIM   = "\033[2m"
        RST   = "\033[0m"

        try:
            players = await self._get_players_in_zone(
                ship.current_zone, db, session_mgr
            )
        except Exception as exc:
            log.warning("[traffic] boarding _get_players_in_zone: %s", exc)
            return

        for sess, ship_name in players:
            try:
                char = getattr(sess, "character", None)
                if not char:
                    continue

                sid = await _get_player_ship_zone_ship_id(sess, db)
                ship_row = await db.get_ship(sid) if sid else None
                sys_data = (
                    json.loads(dict(ship_row).get("systems") or "{}")
                    if ship_row else {}
                )

                inf_class = 5
                inf_reason = "Failure to respond to Imperial hail"
                false_tp = sys_data.get("false_transponder")
                smug_job = sys_data.get("smuggling_job")

                if false_tp and isinstance(false_tp, dict):
                    inf_class = 2
                    alias = false_tp.get("alias", "unknown ID")
                    inf_reason = "False transponder detected (" + alias + ")"
                elif smug_job:
                    tier = (
                        smug_job.get("cargo_tier", 1)
                        if isinstance(smug_job, dict) else 1
                    )
                    inf_class = 3 if tier >= 2 else 4
                    inf_reason = "Contraband detected in cargo hold"

                inf = INFRACTION[inf_class]
                fine_lo, fine_hi = inf["fine"]
                fine = _rand.randint(fine_lo, fine_hi)

                await sess.send_line(
                    "\n  " + RED + "[IMPERIAL BOARDING]" + RST
                    + " Stormtroopers board " + ship_name + " for inspection."
                )
                await sess.send_line(
                    "  " + RED + "[IMPERIAL CUSTOMS]" + RST
                    + " " + inf["name"] + " infraction: " + inf_reason + "."
                )

                if fine == 0:
                    await sess.send_line(
                        "  " + RED + "[IMPERIAL CUSTOMS]" + RST
                        + " You are being detained."
                        + " (Roleplay with staff or wait for release.)"
                    )
                    log.info(
                        "[traffic] boarding: char %s detained (%s)",
                        char.get("id"), inf_reason,
                    )
                    continue

                credits = char.get("credits", 0)
                paid = min(credits, fine)
                char["credits"] = credits - paid
                await db.save_character(char["id"], credits=char["credits"])

                if paid < fine:
                    await sess.send_line(
                        "  " + AMBER + "Fine: " + str(fine) + "cr"
                        + " — insufficient credits."
                        + " Partial payment of " + str(paid) + "cr accepted."
                        + RST
                    )
                else:
                    await sess.send_line(
                        "  " + AMBER + "Fine: " + str(fine) + "cr paid."
                        + " Balance: " + str(char["credits"]) + "cr." + RST
                    )

                await sess.send_line(
                    "  " + DIM + "[IMPERIAL BOARDING]"
                    + " Troops withdraw. You are cleared to proceed." + RST
                )
                log.info(
                    "[traffic] boarding: char %s fined %dcr (%s)",
                    char.get("id"), paid, inf_reason,
                )

            except Exception as exc:
                log.warning(
                    "[traffic] boarding player error: %s", exc
                )


    async def _tick_tailing(self, ship: TrafficShip, db, session_mgr) -> bool:
        """
        Pirate is tailing a player ship. After HAIL_TIMEOUT_SECS of tailing,
        send the credit demand. If the target ship changes zone, follow or give up.
        """
        if ship.tailing_ship_id is None:
            # Lost target — go idle
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ship.enter_state(TrafficState.IDLE, duration=idle_dur)
            return False

        # Check whether target is still in the same zone
        try:
            target_row = await db.get_ship(ship.tailing_ship_id)
        except Exception:
            target_row = None

        if target_row:
            target_sys = json.loads(dict(target_row).get("systems") or "{}")
            target_zone = target_sys.get("current_zone", "")
            if target_zone and target_zone != ship.current_zone:
                # Target moved — follow if adjacent, else give up
                zone_obj = ZONES.get(ship.current_zone)
                if zone_obj and target_zone in zone_obj.adjacent:
                    ship.current_zone = target_zone
                    await self._announce_to_zone(
                        target_zone,
                        f"  [SENSORS] {ship.sensors_name()} drops in behind you.",
                        session_mgr, db,
                    )
                else:
                    # Lost them
                    ship.tailing_ship_id = None
                    idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
                    ship.enter_state(TrafficState.IDLE, duration=idle_dur)
                    return False
        else:
            # Target ship gone (landed/destroyed)
            ship.tailing_ship_id = None
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ship.enter_state(TrafficState.IDLE, duration=idle_dur)
            return False

        # After tailing for HAIL_TIMEOUT_SECS, send demand
        if ship.state_age() >= HAIL_TIMEOUT_SECS and not ship.hail_sent:
            if ship.archetype == TrafficArchetype.BOUNTY_HUNTER:
                # Drop 7: create hunter encounter instead of old hail
                created = await self._create_hunter_encounter(
                    ship, ship.tailing_ship_id, db, session_mgr)
                if created:
                    ship.hail_sent = True
                    ship.hunter_hail_sent = True
                    ship.enter_state(TrafficState.HAILING, duration=120)
                else:
                    # Fallback: old personalized hail
                    target_name_str = ship.bounty_target_name or "fugitive"
                    ship.hail_sent = True
                    ship.hunter_hail_sent = True
                    ship.enter_state(TrafficState.HAILING, duration=HAIL_TIMEOUT_SECS)
                    await self._announce_to_zone(
                        ship.current_zone,
                        f"  {ansi_yellow}[COMMS]{ansi_reset} {ship.sensors_name()}: "
                        f"\"{target_name_str}. Surrender or I collect from your wreckage.\"",
                        session_mgr, db,
                    )
            else:
                # Pirate demand → create encounter (Drop 4)
                target_name = dict(target_row).get("name", "your ship") if target_row else "your ship"
                created = await self._create_pirate_encounter(
                    ship, ship.tailing_ship_id, target_name, db, session_mgr)
                if created:
                    ship.hail_sent = True
                    ship.enter_state(TrafficState.HAILING, duration=120)
                else:
                    # Fallback: old behavior
                    demand = random.randint(PIRATE_CREDIT_MIN, PIRATE_CREDIT_MAX)
                    ship.pirate_demand_credits = demand
                    ship.pirate_paid = False
                    ship.hail_sent = True
                    ship.enter_state(TrafficState.HAILING, duration=HAIL_TIMEOUT_SECS)
                    await self._announce_to_zone(
                        ship.current_zone,
                        f"  {ansi_yellow}[COMMS]{ansi_reset} {ship.sensors_name()}: "
                        f"\"Cut your engines. Transfer {demand:,} credits or we start shooting. "
                        f"Use: pay {ship.sensors_name()} to comply.\"",
                        session_mgr, db,
                    )
                    log.info(f"[traffic] pirate '{ship.display_name}' demands {demand} cr (legacy)")

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

        elif ship.archetype == TrafficArchetype.SMUGGLER:
            # Smugglers avoid ORBIT zones — route through deep space only
            if ship.current_zone == "tatooine_dock":
                # Finished docking — head out via deep space, skip orbit
                ship.route = ["tatooine_deep_space", "outer_rim_lane_1"]
                ship.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
            elif ship.current_zone in ("tatooine_deep_space", "outer_rim_lane_1"):
                # Head to dock via deep space only (no orbit)
                ship.route = ["tatooine_deep_space", "tatooine_dock"]
                ship.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
            else:
                self._plan_departure(ship)

        elif ship.archetype == TrafficArchetype.PATROL:
            # Advance to next leg of the patrol circuit
            circuit = _build_patrol_circuit()
            if circuit:
                ship.patrol_zone_index = (ship.patrol_zone_index + 1) % len(circuit)
                next_zone = circuit[ship.patrol_zone_index]
                path = find_path(ship.current_zone, next_zone)
                ship.route = path if path else [next_zone]
                ship.hail_sent = False  # reset so patrol can hail in next zone
                ship.enter_state(TrafficState.TRANSIT, duration=ZONE_TRANSIT_SECS)
            else:
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

    # ── Player zone helpers ───────────────────────────────────────────────────

    async def _get_players_in_zone(self, zone_id: str, db, session_mgr) -> list:
        """Return list of (session, ship_name) tuples for players in zone_id."""
        result = []
        try:
            for session in list(session_mgr.all):
                char = getattr(session, "character", None)
                if not char:
                    continue
                ship_id = await _get_player_ship_zone_ship_id(session, db)
                if ship_id is None:
                    continue
                ship_row = await db.get_ship(ship_id)
                if not ship_row:
                    continue
                systems = json.loads(dict(ship_row).get("systems") or "{}")
                if systems.get("current_zone") == zone_id:
                    result.append((session, dict(ship_row).get("name", "your ship")))
        except Exception as e:
            log.error(f"[traffic] _get_players_in_zone error: {e}")
        return result

    async def _find_char_zone(self, char_id: int, db) -> Optional[str]:
        """Return the current_zone of the ship a character is aboard, or None."""
        try:
            ships = await db.get_ships_in_space()
            for ship in ships:
                ship = dict(ship)
                crew = json.loads(ship.get("crew") or "{}")
                if char_id in crew.values():
                    systems = json.loads(ship.get("systems") or "{}")
                    return systems.get("current_zone")
        except Exception as e:
            log.error(f"[traffic] _find_char_zone error: {e}")
        return None

    async def _find_char_ship_id(self, char_id: int, db) -> Optional[int]:
        """Return the ship_id of the ship a character is aboard, or None."""
        try:
            ships = await db.get_ships_in_space()
            for ship in ships:
                ship = dict(ship)
                crew = json.loads(ship.get("crew") or "{}")
                if char_id in crew.values():
                    return ship["id"]
        except Exception as e:
            log.error(f"[traffic] _find_char_ship_id error: {e}")
        return None

    async def spawn_pirate_for_encounter(self, zone_id: str, db, session_mgr):
        """Spawn a temporary pirate for an anomaly encounter. Returns TrafficShip or None."""
        try:
            return await self._spawn(db, session_mgr,
                                      archetype=TrafficArchetype.PIRATE,
                                      force_zone=zone_id)
        except Exception as e:
            log.warning("[traffic] spawn_pirate_for_encounter: %s", e)
            return None

    async def _create_hunter_encounter(self, ship: TrafficShip,
                                        target_ship_id: int,
                                        db, session_mgr) -> bool:
        """Create a Bounty Hunter encounter (Drop 7). Returns True if created."""
        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()
        target_ship = await db.get_ship(target_ship_id)
        if not target_ship:
            return False
        bridge_room = target_ship.get("bridge_room_id")
        if not bridge_room:
            return False

        # Look up bounty amount from the target character
        bounty_amount = 0
        target_name = ship.bounty_target_name or "fugitive"
        if ship.bounty_target_char_id:
            try:
                char = await db.get_character(ship.bounty_target_char_id)
                if char:
                    bounty_amount = dict(char).get("bounty", 0)
                    target_name = dict(char).get("name", target_name)
            except Exception:
                log.warning("[traffic] hunter encounter target lookup failed", exc_info=True)

        enc = await mgr.create_encounter(
            encounter_type="hunter",
            zone_id=ship.current_zone,
            target_ship_id=target_ship_id,
            target_bridge_room=bridge_room,
            db=db,
            session_mgr=session_mgr,
            npc_ship_id=ship.ship_id,
            context={
                "hunter_name": ship.display_name,
                "target_name": target_name,
                "bounty_amount": bounty_amount,
            },
        )
        if enc:
            log.info("[traffic] hunter '%s' created encounter %s for '%s'",
                     ship.display_name, enc.id, target_name)
            return True
        return False

    # ── Encounter creation (Drop 2) ─────────────────────────────────────────

    async def _create_patrol_encounter(self, ship: TrafficShip,
                                        player_session, player_ship_name: str,
                                        db, session_mgr) -> bool:
        """Create an Imperial Patrol encounter using the new encounter system.

        Returns True if encounter was created, False if blocked by cooldown/cap.
        """
        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()

        # Find the player's ship ID and bridge room
        target_ship_id = await _get_player_ship_zone_ship_id(player_session, db)
        if not target_ship_id:
            return False
        target_ship = await db.get_ship(target_ship_id)
        if not target_ship:
            return False
        bridge_room = target_ship.get("bridge_room_id")
        if not bridge_room:
            return False

        # Check for contraband (smuggling job or false transponder)
        import json as _json
        sys_data = {}
        raw = dict(target_ship).get("systems") or "{}"
        try:
            sys_data = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            log.warning("[traffic] patrol encounter systems JSON parse failed", exc_info=True)

        has_contraband = bool(
            sys_data.get("smuggling_job") or sys_data.get("false_transponder")
        )

        # Check cleared status — recently inspected ships are skipped
        cleared_until = sys_data.get("patrol_cleared_until", 0)
        if cleared_until and time.time() < cleared_until:
            log.debug("[traffic] patrol skipping cleared ship %d", target_ship_id)
            return False

        enc = await mgr.create_encounter(
            encounter_type="patrol",
            zone_id=ship.current_zone,
            target_ship_id=target_ship_id,
            target_bridge_room=bridge_room,
            db=db,
            session_mgr=session_mgr,
            npc_ship_id=ship.ship_id,
            context={
                "patrol_name": ship.display_name,
                "player_ship_name": player_ship_name,
                "has_contraband": has_contraband,
            },
        )

        if enc:
            log.info("[traffic] patrol '%s' created encounter %s for ship '%s'",
                     ship.display_name, enc.id, player_ship_name)
            return True
        return False

    async def _create_pirate_encounter(self, ship: TrafficShip,
                                        target_ship_id: int,
                                        player_ship_name: str,
                                        db, session_mgr) -> bool:
        """Create a Pirate encounter using the new encounter system (Drop 4).

        Returns True if encounter was created, False if blocked.
        """
        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()

        target_ship = await db.get_ship(target_ship_id)
        if not target_ship:
            return False
        target_ship = dict(target_ship)
        bridge_room = target_ship.get("bridge_room_id")
        if not bridge_room:
            return False

        enc = await mgr.create_encounter(
            encounter_type="pirate",
            zone_id=ship.current_zone,
            target_ship_id=target_ship_id,
            target_bridge_room=bridge_room,
            db=db,
            session_mgr=session_mgr,
            npc_ship_id=ship.ship_id,
            context={
                "pirate_name": ship.display_name,
                "player_ship_name": player_ship_name,
            },
        )

        if enc:
            log.info("[traffic] pirate '%s' created encounter %s for ship %d",
                     ship.display_name, enc.id, target_ship_id)
            return True
        return False

    # ── Hail senders ─────────────────────────────────────────────────────────

    async def _send_patrol_hail(self, ship: TrafficShip, player_session,
                                 player_ship_name: str, session_mgr, db):
        """Send an Imperial Patrol hail to a player ship."""
        ship.hail_sent = True
        ship.enter_state(TrafficState.HAILING, duration=HAIL_TIMEOUT_SECS)
        await self._announce_to_zone(
            ship.current_zone,
            f"  {ansi_yellow}[COMMS]{ansi_reset} {ship.display_name}: "
            f"\"Attention {player_ship_name} — this is Imperial Sector Patrol. "
            f"Transmit your identification codes and stand by for inspection. "
            f"Respond with: comms {ship.sensors_name()} <message>\"",
            session_mgr, db,
        )
        log.info(f"[traffic] patrol '{ship.display_name}' hailed player ship '{player_ship_name}'")

    # ── Public comms API (called from space_commands) ─────────────────────────

    async def handle_player_hail(self, player_session, player_ship_name: str,
                                  zone_id: str, db, session_mgr) -> bool:
        """
        Player sent 'hail' with no target. Broadcast to all traffic ships in zone.
        Returns True if any traffic ship was in zone.
        """
        ships_in_zone = self.get_zone_ships(zone_id)
        if not ships_in_zone:
            return False
        for ts in ships_in_zone:
            reply = _build_generic_hail_reply(ts, player_ship_name)
            await player_session.send_line(
                f"  {ansi_yellow}[COMMS]{ansi_reset} {ts.sensors_name()}: \"{reply}\""
            )
        return True

    async def handle_player_comms(self, player_session, player_ship_name: str,
                                   target_name: str, message: str,
                                   zone_id: str, db, session_mgr) -> bool:
        """
        Player sent 'comms <target> <message>'. Find matching traffic ship and respond.
        Returns True if a traffic ship was found and responded.
        """
        ts = self.get_ship_by_name(target_name)
        if ts is None or ts.current_zone != zone_id:
            return False

        # Clear hailing state if they were waiting on this player
        if ts.state == TrafficState.HAILING:
            ts.hail_pending = False
            ts.hail_source_char_id = None
            # Move back to idle so patrol can continue circuit
            idle_dur = random.uniform(IDLE_MIN_SECS, IDLE_MAX_SECS)
            ts.enter_state(TrafficState.IDLE, duration=idle_dur)

        reply = _build_comms_reply(ts, player_ship_name, message)
        await player_session.send_line(
            f"  {ansi_yellow}[COMMS]{ansi_reset} {ts.sensors_name()}: \"{reply}\""
        )
        # Also echo the player's outgoing message to the bridge
        await session_mgr.broadcast_to_zone_bridge(
            zone_id,
            f"  {ansi_cyan}[COMMS OUT]{ansi_reset} {player_ship_name} → "
            f"{ts.sensors_name()}: \"{message}\"",
            exclude_session=player_session,
            db=db,
        ) if hasattr(session_mgr, "broadcast_to_zone_bridge") else None
        log.info(f"[traffic] player '{player_ship_name}' comms → '{ts.display_name}': {message[:40]}")
        return True

    async def handle_pirate_payment(self, player_session, player_char,
                                     target_name: str, zone_id: str,
                                     db, session_mgr) -> tuple[bool, str]:
        """
        Player used 'pay <pirate>' to comply with a demand.
        Returns (success, message) tuple.
        """
        ts = self.get_ship_by_name(target_name)
        if ts is None or ts.current_zone != zone_id:
            return False, f"No ship named '{target_name}' in your zone."
        if ts.archetype != TrafficArchetype.PIRATE:
            return False, f"{ts.sensors_name()} isn't demanding anything from you."
        if ts.state != TrafficState.HAILING or ts.pirate_demand_credits <= 0:
            return False, f"{ts.sensors_name()} hasn't made a demand yet."
        if ts.pirate_paid:
            return False, "You've already paid that demand."

        demand = ts.pirate_demand_credits
        credits = player_char.get("credits", 0)
        if credits < demand:
            return False, (f"You don't have enough credits. "
                           f"Demand: {demand:,} cr, You have: {credits:,} cr.")

        # Deduct credits
        player_char["credits"] = credits - demand
        await db.save_character(player_char["id"], credits=player_char["credits"])

        ts.pirate_paid = True
        ts.hail_sent = False
        ts.hail_pending = False
        ts.tailing_ship_id = None

        # Pirate satisfied — flees
        self._plan_departure(ts)

        await self._announce_to_zone(
            zone_id,
            f"  {ansi_yellow}[COMMS]{ansi_reset} {ts.sensors_name()}: "
            f"\"Smart move. Pleasure doing business.\"",
            session_mgr, db,
        )
        log.info(f"[traffic] player paid pirate '{ts.display_name}' {demand} cr — fleeing")
        return True, f"You transfer {demand:,} credits. {ts.sensors_name()} breaks off."

    async def handle_traffic_ship_destroyed(self, traffic_ship_id: int,
                                             player_char, db, session_mgr) -> int:
        """
        Called when a player kills a traffic ship. Awards credit bounty for pirates.
        Returns credits awarded (0 if not a pirate).
        """
        ts = self._ships.get(traffic_ship_id)
        if ts is None:
            return 0
        awarded = 0
        if ts.archetype == TrafficArchetype.PIRATE:
            awarded = random.randint(PIRATE_CREDIT_MIN, PIRATE_CREDIT_MAX)
            new_credits = player_char.get("credits", 0) + awarded
            player_char["credits"] = new_credits
            await db.save_character(player_char["id"], credits=new_credits)
            log.info(f"[traffic] player destroyed pirate '{ts.display_name}' — awarded {awarded} cr")
        await self._despawn(traffic_ship_id, db, session_mgr)
        return awarded

    # ── Despawn ───────────────────────────────────────────────────────────────

    async def _despawn(self, ship_id: int, db, session_mgr):
        ship = self._ships.pop(ship_id, None)
        if not ship:
            return
        # Bounty hunter: schedule respawn if target still has a bounty
        if ship.archetype == TrafficArchetype.BOUNTY_HUNTER and ship.bounty_target_char_id:
            self._hunter_respawns[ship.bounty_target_char_id] = (
                time.time() + HUNTER_RESPAWN_DELAY
            )
            log.info(f"[traffic] hunter '{ship.display_name}' despawned — "
                     f"respawn in {HUNTER_RESPAWN_DELAY}s for char {ship.bounty_target_char_id}")
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


# ─────────────────────────────────────────────────────────────────────────────
# ANSI shortcuts (avoid importing full server.ansi to keep engine layer clean)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from server import ansi as _ansi
    ansi_yellow = _ansi.BRIGHT_YELLOW
    ansi_cyan   = _ansi.BRIGHT_CYAN
    ansi_reset  = _ansi.RESET
except Exception:
    ansi_yellow = ansi_cyan = ansi_reset = ""


# ─────────────────────────────────────────────────────────────────────────────
# PATROL CIRCUIT
# ─────────────────────────────────────────────────────────────────────────────

def _build_patrol_circuit() -> list[str]:
    """Return the ordered patrol circuit for the current zone config."""
    # tatooine circuit: deep_space → orbit → deep_space → ...
    return ["tatooine_deep_space", "tatooine_orbit"]


# ─────────────────────────────────────────────────────────────────────────────
# COMMS REPLY BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

_TRADER_REPLIES = [
    "Safe travels. We're just passing through.",
    "Nothing to declare. Manifest is clean.",
    "Acknowledged. We're on a tight schedule — good day.",
    "Cargo secured and accounted for. No trouble here.",
]

_SMUGGLER_REPLIES = [
    "We're, uh, just doing routine cargo work. Nothing to see here.",
    "Official business. Can't say more. You understand.",
    "Keep moving, friend. We've got places to be.",
    "Acknowledged. Carry on.",
]

_PATROL_REPLIES_COMPLIANT = [
    "Identification received. You are cleared to proceed. Stay on course.",
    "Codes verified. Move along — and keep your transponder active.",
    "Acknowledged. You're in the clear. Don't make us stop you again.",
]

_PATROL_REPLIES_SUSPICIOUS = [
    "Your codes are... irregular. We'll be watching you.",
    "Technically compliant. Stay visible on our scans.",
    "Noted. Any deviation from approved corridors will be logged.",
]

_PIRATE_REPLIES = [
    "Credits or hull plating. Your choice.",
    "We're not here to talk. Pay up.",
    "Keep talking and we start shooting.",
    "The price just went up. Stop wasting our time.",
]

_HUNTER_REPLIES = [
    "The contract is clear. There is no negotiation.",
    "I've tracked worse than you. Don't make this harder than it needs to be.",
    "Surrender or don't. Either way, I collect.",
]

_GENERIC_HAIL = [
    "This frequency is monitored. State your business.",
    "Go ahead. We're listening.",
    "Received your hail. Keep it brief.",
]


def _build_generic_hail_reply(ts: TrafficShip, player_ship_name: str) -> str:
    """Reply when a player broadcasts 'hail' with no specific target."""
    if ts.archetype == TrafficArchetype.TRADER:
        return random.choice(_TRADER_REPLIES)
    elif ts.archetype == TrafficArchetype.SMUGGLER:
        return random.choice(_SMUGGLER_REPLIES)
    elif ts.archetype == TrafficArchetype.PATROL:
        return (f"This is {ts.display_name}. Identify yourself and state your business, "
                f"{player_ship_name}.")
    elif ts.archetype == TrafficArchetype.PIRATE:
        if ts.pirate_demand_credits > 0:
            return (f"You owe us {ts.pirate_demand_credits:,} credits. "
                    f"Pay now or face the consequences.")
        return random.choice(_PIRATE_REPLIES)
    elif ts.archetype == TrafficArchetype.BOUNTY_HUNTER:
        name_str = ts.bounty_target_name or "fugitive"
        return (f"This transmission is for {name_str}. "
                f"The contract stands. {random.choice(_HUNTER_REPLIES)}")
    else:
        return random.choice(_GENERIC_HAIL)


def _build_comms_reply(ts: TrafficShip, player_ship_name: str, message: str) -> str:
    """Build an NPC reply to a targeted comms message."""
    msg_lower = message.lower()
    if ts.archetype == TrafficArchetype.TRADER:
        return random.choice(_TRADER_REPLIES)
    elif ts.archetype == TrafficArchetype.SMUGGLER:
        return random.choice(_SMUGGLER_REPLIES)
    elif ts.archetype == TrafficArchetype.PATROL:
        compliance_words = ("id", "ident", "code", "clear", "acknowledged", "complying",
                            "here", "transmit", "sending", "affirmative")
        if any(w in msg_lower for w in compliance_words):
            return random.choice(_PATROL_REPLIES_COMPLIANT)
        else:
            return random.choice(_PATROL_REPLIES_SUSPICIOUS)
    elif ts.archetype == TrafficArchetype.PIRATE:
        if ts.pirate_demand_credits > 0:
            return (f"Stop stalling. {ts.pirate_demand_credits:,} credits. "
                    f"Use 'pay {ts.sensors_name()}' to comply.")
        return random.choice(_PIRATE_REPLIES)
    elif ts.archetype == TrafficArchetype.BOUNTY_HUNTER:
        return random.choice(_HUNTER_REPLIES)
    else:
        return random.choice(_GENERIC_HAIL)


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
