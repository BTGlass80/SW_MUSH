# -*- coding: utf-8 -*-
"""
engine/missions.py  --  Mission Board Generation Engine
SW_MUSH  |  Economy Phase 2

Generates and manages the Mission Board: a persistent pool of 5-8 procedurally
created jobs covering all archetypes. Every player has access regardless of
build; specialists earn more in their primary lane but nobody is locked out.

Design targets (from economy_design_v02-1.md):
  - Active player earns 500-2,000 cr/hr
  - Living expenses run 200-400 cr/hr
  - Net accumulation 300-1,600 cr/hr depending on risk and skill
  - Board holds 5-8 missions, refreshes every 30 minutes
  - Completed missions replaced immediately

Mission lifecycle:
  AVAILABLE  ->  ACCEPTED (by a character)  ->  COMPLETE / EXPIRED
  Board maintains AVAILABLE pool. One active mission per character at a time.

Dependencies (all standard library or already in the project):
  random, time, dataclasses, enum, json, logging
  No new pip packages required.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

BOARD_MIN       = 5     # Minimum missions on the board at any time
BOARD_MAX       = 8     # Maximum missions on the board
REFRESH_SECONDS = 1800  # 30 minutes: full board refresh interval
MISSION_TTL     = 3600  # 1 hour: individual mission expiry if not accepted
MISSION_ACTIVE_TTL = 7200  # 2 hours: accepted mission expiry if not completed

# ── Mission types ──────────────────────────────────────────────────────────────

class MissionType(str, Enum):
    DELIVERY      = "delivery"
    COMBAT        = "combat"
    INVESTIGATION = "investigation"
    SOCIAL        = "social"
    TECHNICAL     = "technical"
    MEDICAL       = "medical"
    SMUGGLING     = "smuggling"
    BOUNTY        = "bounty"
    SLICING       = "slicing"
    SALVAGE       = "salvage"
    # ── Space mission types (Drop 14) ────────────────────────────────────────
    PATROL        = "patrol"        # Hold a zone for 120 ticks
    ESCORT        = "escort"        # Protect NPC trader to destination zone
    INTERCEPT     = "intercept"     # Destroy N hostile ships in a zone
    SURVEY_ZONE   = "survey_zone"   # Resolve at least 1 anomaly in a zone

# Space mission type set — used for routing in complete/accept logic
SPACE_MISSION_TYPES = {
    MissionType.PATROL, MissionType.ESCORT,
    MissionType.INTERCEPT, MissionType.SURVEY_ZONE,
}

# Zone targets for space missions (cycles; new zones can be added freely)
_PATROL_ZONES = [
    "tatooine_orbit", "tatooine_deep_space",
    "nar_shaddaa_orbit", "nar_shaddaa_deep_space",
    "kessel_approach", "kessel_orbit",
    "corellia_orbit", "corellia_deep_space",
    "outer_rim_lane_1", "outer_rim_lane_2",
]
_SURVEY_ZONES = [
    "tatooine_deep_space", "tatooine_orbit",
    "nar_shaddaa_deep_space", "kessel_approach",
    "corellia_deep_space", "outer_rim_lane_1",
]
_INTERCEPT_ZONES = [
    "tatooine_deep_space", "nar_shaddaa_deep_space",
    "kessel_approach", "outer_rim_lane_3",
    "corellia_deep_space",
]
# Escort: origin zone → destination zone pairs
_ESCORT_ROUTES = [
    ("tatooine_orbit",      "nar_shaddaa_orbit"),
    ("nar_shaddaa_orbit",   "tatooine_orbit"),
    ("tatooine_orbit",      "corellia_orbit"),
    ("corellia_orbit",      "tatooine_orbit"),
    ("nar_shaddaa_orbit",   "kessel_orbit"),
    ("outer_rim_lane_1",    "corellia_orbit"),
]


class MissionStatus(str, Enum):
    AVAILABLE = "available"
    ACCEPTED  = "accepted"
    COMPLETE  = "complete"
    EXPIRED   = "expired"
    FAILED    = "failed"


# ── Pay ranges by type (min, max) in credits ──────────────────────────────────
# These match the economy design doc §4.1 targets.

PAY_RANGES: dict[MissionType, tuple[int, int]] = {
    MissionType.DELIVERY:      (100,  300),
    MissionType.COMBAT:        (300, 1000),
    MissionType.INVESTIGATION: (200,  800),
    MissionType.SOCIAL:        (500, 2000),
    MissionType.TECHNICAL:     (300, 1500),
    MissionType.MEDICAL:       (200, 1000),
    MissionType.SMUGGLING:     (500, 5000),
    MissionType.BOUNTY:        (300, 3000),
    MissionType.SLICING:       (400, 2000),
    MissionType.SALVAGE:       (200, 1000),
    # Space missions (Drop 14)
    MissionType.PATROL:        (600,  1000),
    MissionType.ESCORT:        (1500, 2500),
    MissionType.INTERCEPT:     (2000, 3000),
    MissionType.SURVEY_ZONE:   (1200, 1800),
}

# Relative spawn weight: delivery is always available, social and slicing are rare.
SPAWN_WEIGHTS: dict[MissionType, int] = {
    MissionType.DELIVERY:      10,
    MissionType.COMBAT:         8,
    MissionType.INVESTIGATION:  6,
    MissionType.SOCIAL:         2,
    MissionType.TECHNICAL:      6,
    MissionType.MEDICAL:        8,
    MissionType.SMUGGLING:      5,
    MissionType.BOUNTY:         5,
    MissionType.SLICING:        2,
    MissionType.SALVAGE:        6,
    # Space missions — intentionally lower weight (need a ship to take these)
    MissionType.PATROL:         4,
    MissionType.ESCORT:         3,
    MissionType.INTERCEPT:      3,
    MissionType.SURVEY_ZONE:    3,
}

# Primary skills required for each type (used for flavor and difficulty scaling).
REQUIRED_SKILLS: dict[MissionType, list[str]] = {
    MissionType.DELIVERY:      ["stamina"],
    MissionType.COMBAT:        ["blaster", "melee combat", "brawling"],
    MissionType.INVESTIGATION: ["search", "streetwise", "perception"],
    MissionType.SOCIAL:        ["persuasion", "bargain", "con"],
    MissionType.TECHNICAL:     ["space transports repair", "blaster repair", "droid programming"],
    MissionType.MEDICAL:       ["first aid", "medicine"],
    MissionType.SMUGGLING:     ["space transports", "con", "sneak"],
    MissionType.BOUNTY:        ["search", "tracking", "blaster"],
    MissionType.SLICING:       ["computer programming/repair", "security"],
    MissionType.SALVAGE:       ["search", "perception", "survival"],
    # Space missions
    MissionType.PATROL:        ["sensors", "space transports"],
    MissionType.ESCORT:        ["space transports", "starship gunnery"],
    MissionType.INTERCEPT:     ["starship gunnery", "space transports"],
    MissionType.SURVEY_ZONE:   ["sensors", "search"],
}


# ── Flavor text tables ─────────────────────────────────────────────────────────

_GIVERS = [
    "A grizzled dockworker", "A nervous Rodian merchant", "A hooded Twi'lek",
    "A portly Aqualish factor", "A harried Imperial clerk",
    "An anonymous data packet", "A scarred human veteran",
    "A Sullustan freighter captain", "A Bothan information broker",
    "A cantina patron nursing a drink", "An aged Mon Calamari trader",
    "A Duros navigator between jobs",
]

_DELIVERY_OBJECTIVES = [
    "Deliver a sealed crate to {dest}. No questions asked.",
    "Transport medical supplies to {dest}. Time-sensitive.",
    "Carry this datapad to the contact at {dest}.",
    "Deliver machine components to {dest}. Handle with care.",
    "Run this package to {dest}. Don't open it.",
    "Courier a diplomatic pouch to {dest}.",
]
_COMBAT_OBJECTIVES = [
    "Clear the hostile gang that's taken over {dest}.",
    "Eliminate the bounty target last seen near {dest}.",
    "Drive off the pirates threatening the route to {dest}.",
    "Deal with the mercenaries blocking access to {dest}.",
    "Neutralize the armed squatters at {dest}.",
]
_INVESTIGATION_OBJECTIVES = [
    "Find out who's been stealing from the warehouses near {dest}.",
    "Track down a missing contact last seen at {dest}.",
    "Investigate the strange signals coming from {dest}.",
    "Identify the Imperial informant operating around {dest}.",
    "Locate a lost droid somewhere near {dest}.",
]
_SOCIAL_OBJECTIVES = [
    "Negotiate a trade agreement at {dest} on our behalf.",
    "Convince the merchant at {dest} to honor his contract.",
    "Broker a ceasefire between the factions near {dest}.",
    "Persuade the docking authority at {dest} to waive fees.",
    "Smooth things over with a Hutt contact at {dest}.",
]
_TECHNICAL_OBJECTIVES = [
    "Repair the malfunctioning generator at {dest}.",
    "Calibrate the docking bay sensors at {dest}.",
    "Restore the communication array near {dest}.",
    "Fix the life support system at {dest}.",
    "Overhaul the speeder bikes stored at {dest}.",
]
_MEDICAL_OBJECTIVES = [
    "Treat the wounded settlers at {dest}.",
    "Administer bacta treatment to the injured crew at {dest}.",
    "Deliver and apply medications to the sick at {dest}.",
    "Stabilize the critically wounded person at {dest}.",
    "Run a medical check on the NPC workers at {dest}.",
]
_SMUGGLING_OBJECTIVES = [
    "Move a restricted cargo through the checkpoint near {dest}. Don't get scanned.",
    "Deliver this contraband to the contact at {dest}. Avoid patrols.",
    "Run a gray-market shipment to {dest}. The less paperwork, the better.",
    "Smuggle documents past the Imperial blockade to {dest}.",
    "Transport live cargo to {dest}. No manifest. No record.",
]
_BOUNTY_OBJECTIVES = [
    "Bring in the fugitive hiding somewhere near {dest}. Alive preferred.",
    "Track down the debt defaulter last spotted at {dest}.",
    "Locate and apprehend the criminal wanted near {dest}.",
    "Collect on the warrant for the armed fugitive near {dest}.",
    "Hunt down the deserter believed to be at {dest}.",
]
_SLICING_OBJECTIVES = [
    "Slice into the security system at {dest} and extract the data.",
    "Decrypt the locked datacron recovered near {dest}.",
    "Forge transit documents for a contact. Deliver via dead drop at {dest}.",
    "Access the Imperial records terminal near {dest} without tripping alarms.",
    "Erase the criminal file from the local database near {dest}.",
]
_SALVAGE_OBJECTIVES = [
    "Salvage useful components from the crash site near {dest}.",
    "Recover cargo from the derelict ship near {dest} before rivals get there.",
    "Survey the debris field near {dest} for recoverable materials.",
    "Scavenge parts from the wrecked vehicles at {dest}.",
    "Recover the black box from the crashed shuttle near {dest}.",
]

# Space mission objective templates (zone filled at generation time)
_PATROL_OBJECTIVES = [
    "Establish sensor presence in {dest}. Hold position for 2 minutes.",
    "Run a patrol sweep through {dest}. Maintain position for 120 seconds.",
    "Provide deterrence in {dest}. Any pirate activity must be reported.",
]
_ESCORT_OBJECTIVES = [
    "Escort the freighter {escort_ship} from {origin} to {dest}. Keep it alive.",
    "Protect {escort_ship} on the run from {origin} to {dest}. Pirates are likely.",
    "Shepherd {escort_ship} safely through hostile space to {dest}.",
]
_INTERCEPT_OBJECTIVES = [
    "Eliminate {count} pirate ships operating in {dest}.",
    "Clear the hostile traffic from {dest}. Destroy {count} targets.",
    "Take out {count} armed ships raiding shipping lanes near {dest}.",
]
_SURVEY_OBJECTIVES = [
    "Probe {dest} for anomalies. Resolve at least one contact.",
    "Conduct a survey sweep of {dest}. Report anything unusual.",
    "Run deep-space sensors over {dest} and document what you find.",
]

_OBJECTIVE_TABLES: dict[MissionType, list[str]] = {
    MissionType.DELIVERY:      _DELIVERY_OBJECTIVES,
    MissionType.COMBAT:        _COMBAT_OBJECTIVES,
    MissionType.INVESTIGATION: _INVESTIGATION_OBJECTIVES,
    MissionType.SOCIAL:        _SOCIAL_OBJECTIVES,
    MissionType.TECHNICAL:     _TECHNICAL_OBJECTIVES,
    MissionType.MEDICAL:       _MEDICAL_OBJECTIVES,
    MissionType.SMUGGLING:     _SMUGGLING_OBJECTIVES,
    MissionType.BOUNTY:        _BOUNTY_OBJECTIVES,
    MissionType.SLICING:       _SLICING_OBJECTIVES,
    MissionType.SALVAGE:       _SALVAGE_OBJECTIVES,
    MissionType.PATROL:        _PATROL_OBJECTIVES,
    MissionType.ESCORT:        _ESCORT_OBJECTIVES,
    MissionType.INTERCEPT:     _INTERCEPT_OBJECTIVES,
    MissionType.SURVEY_ZONE:   _SURVEY_OBJECTIVES,
}

# ── Destination rooms (static fallback; generator also uses live room graph) ───

_FALLBACK_DESTINATIONS = [
    "Chalmun's Cantina",
    "Docking Bay 94",
    "Docking Bay 86",
    "Mos Eisley Market",
    "Lucky Despot Hotel",
    "Jabba's Townhouse",
    "Mos Eisley Police Station",
    "Industrial District",
    "Residential Quarter",
    "Mos Eisley Outskirts",
]


# ── Mission dataclass ──────────────────────────────────────────────────────────

@dataclass
class Mission:
    """
    A single mission on the board or held by a character.

    Stored in the DB missions table as a JSON blob (data column).
    The row-level columns are: id, status, accepted_by, created_at,
    accepted_at, expires_at, mission_type, reward.
    """

    id: str                      # UUID-style string key
    mission_type: MissionType
    title: str
    giver: str
    objective: str
    destination: str             # Room name (display)
    destination_room_id: Optional[str]  # DB room id if known
    reward: int                  # Credits on completion
    required_skill: str          # Primary skill hint for the player
    status: MissionStatus = MissionStatus.AVAILABLE
    accepted_by: Optional[str] = None    # character_id
    created_at: float = field(default_factory=time.time)
    accepted_at: Optional[float] = None
    expires_at: Optional[float] = None
    # Space mission state (Drop 14): zone ID, kill counts, escort NPC ship ID, etc.
    mission_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mission_type": self.mission_type.value,
            "title": self.title,
            "giver": self.giver,
            "objective": self.objective,
            "destination": self.destination,
            "destination_room_id": self.destination_room_id,
            "reward": self.reward,
            "required_skill": self.required_skill,
            "status": self.status.value,
            "accepted_by": self.accepted_by,
            "created_at": self.created_at,
            "accepted_at": self.accepted_at,
            "expires_at": self.expires_at,
            "mission_data": self.mission_data,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Mission":
        return cls(
            id=d["id"],
            mission_type=MissionType(d["mission_type"]),
            title=d["title"],
            giver=d["giver"],
            objective=d["objective"],
            destination=d["destination"],
            destination_room_id=d.get("destination_room_id"),
            reward=d["reward"],
            required_skill=d["required_skill"],
            status=MissionStatus(d.get("status", "available")),
            accepted_by=d.get("accepted_by"),
            created_at=d.get("created_at", time.time()),
            accepted_at=d.get("accepted_at"),
            expires_at=d.get("expires_at"),
            mission_data=d.get("mission_data", {}),
        )


# ── Mission generator ──────────────────────────────────────────────────────────

def _generate_id() -> str:
    """Generate a short unique mission ID."""
    import uuid
    return "m-" + str(uuid.uuid4())[:8]


def _pick_type() -> MissionType:
    """Weighted random mission type selection, biased by zone alert level."""
    weights = dict(SPAWN_WEIGHTS)  # mutable local copy
    # Bias weights based on Director zone alert level
    try:
        from engine.director import get_director, AlertLevel
        director = get_director()
        # Use the most dramatic alert level across all zones
        alert_levels = [zs.alert_level for zs in director._zones.values()]
        if AlertLevel.LOCKDOWN in alert_levels:
            # Lockdown: smuggling pays more (risk premium)
            weights[MissionType.SMUGGLING] = weights.get(MissionType.SMUGGLING, 5) + 10
        elif AlertLevel.UNDERWORLD in alert_levels:
            # Underworld: criminal jobs abundant
            weights[MissionType.SMUGGLING] = weights.get(MissionType.SMUGGLING, 5) + 5
            weights[MissionType.BOUNTY]    = weights.get(MissionType.BOUNTY, 5) + 5
        elif AlertLevel.UNREST in alert_levels:
            # Unrest: rebel-adjacent combat jobs
            weights[MissionType.COMBAT] = weights.get(MissionType.COMBAT, 8) + 5
    except Exception:
        pass  # director not loaded yet — use base weights
    types = list(weights.keys())
    wlist = [weights[t] for t in types]
    return random.choices(types, weights=wlist, k=1)[0]


def _scale_reward(mission_type: MissionType, skill_level: int = 3) -> int:
    """
    Scale reward within the type's pay range based on the board's current
    difficulty level (approximated by skill_level, range 1-6 dice).

    skill_level 1-2 = easy missions (bottom 40% of range)
    skill_level 3-4 = moderate missions (middle 50%)
    skill_level 5-6 = hard missions (top 30%)
    """
    lo, hi = PAY_RANGES[mission_type]
    span = hi - lo
    # Position within range: clamp skill_level to 1-6
    sl = max(1, min(6, skill_level))
    # Curve: easy -> bottom, hard -> top
    fraction = ((sl - 1) / 5.0) * 0.7 + random.uniform(0, 0.3)
    raw = lo + int(span * fraction)
    # Round to nearest 50cr for cleanliness
    return max(lo, min(hi, int(round(raw / 50) * 50)))


def generate_mission(
    destination_rooms: Optional[list[dict]] = None,
    skill_level: int = 3,
) -> Mission:
    """
    Generate a single random mission.

    destination_rooms: list of room dicts from DB (used for realistic locations).
                       Falls back to static list if None.
    skill_level: approximate difficulty tier (1-6 dice equivalent).
    """
    mtype = _pick_type()

    # Pick destination
    dest_room_id = None
    if destination_rooms:
        room = random.choice(destination_rooms)
        dest_name = room["name"]
        dest_room_id = str(room["id"])
    else:
        dest_name = random.choice(_FALLBACK_DESTINATIONS)

    # Build objective text
    obj_template = random.choice(_OBJECTIVE_TABLES[mtype])
    objective = obj_template.format(dest=dest_name)

    # Pick primary skill hint
    skill_hint = random.choice(REQUIRED_SKILLS[mtype])

    # Giver
    giver = random.choice(_GIVERS)

    # Title
    type_display = mtype.value.replace("_", " ").title()
    title = f"{type_display}: {dest_name}"

    reward = _scale_reward(mtype, skill_level)

    now = time.time()
    return Mission(
        id=_generate_id(),
        mission_type=mtype,
        title=title,
        giver=giver,
        objective=objective,
        destination=dest_name,
        destination_room_id=dest_room_id,
        reward=reward,
        required_skill=skill_hint,
        created_at=now,
        expires_at=now + MISSION_TTL,
    )


def generate_space_mission(skill_level: int = 3) -> Mission:
    """
    Generate a single space mission (PATROL / ESCORT / INTERCEPT / SURVEY_ZONE).
    These missions require the player to be in a ship and in the correct zone.
    mission_data holds zone IDs, kill counts, escort ship name, etc.
    """
    import random as _r
    mtype = _r.choice([
        MissionType.PATROL, MissionType.ESCORT,
        MissionType.INTERCEPT, MissionType.SURVEY_ZONE,
    ])
    giver = _r.choice(_GIVERS)
    reward = _scale_reward(mtype, skill_level)
    skill_hint = _r.choice(REQUIRED_SKILLS[mtype])
    now = time.time()
    mission_data: dict = {}

    if mtype == MissionType.PATROL:
        zone_id = _r.choice(_PATROL_ZONES)
        zone_display = zone_id.replace("_", " ").title()
        obj_tmpl = _r.choice(_PATROL_OBJECTIVES)
        objective = obj_tmpl.format(dest=zone_display)
        title = f"[SPACE] Patrol: {zone_display}"
        mission_data = {
            "target_zone": zone_id,
            "patrol_ticks_required": 120,
            "patrol_ticks_done": 0,
        }
        destination = zone_display

    elif mtype == MissionType.ESCORT:
        route = _r.choice(_ESCORT_ROUTES)
        origin_zone, dest_zone = route
        origin_display = origin_zone.replace("_", " ").title()
        dest_display   = dest_zone.replace("_", " ").title()
        # Escort ship name generated at accept time (when NPC is spawned)
        escort_ship_name = "the convoy freighter"
        obj_tmpl = _r.choice(_ESCORT_OBJECTIVES)
        objective = obj_tmpl.format(
            escort_ship=escort_ship_name,
            origin=origin_display,
            dest=dest_display,
        )
        title = f"[SPACE] Escort to {dest_display}"
        mission_data = {
            "origin_zone":    origin_zone,
            "target_zone":    dest_zone,
            "escort_ship_id": None,   # filled on accept when NPC spawns
        }
        destination = dest_display

    elif mtype == MissionType.INTERCEPT:
        zone_id = _r.choice(_INTERCEPT_ZONES)
        zone_display = zone_id.replace("_", " ").title()
        kills_needed = _r.randint(2, 4)
        obj_tmpl = _r.choice(_INTERCEPT_OBJECTIVES)
        objective = obj_tmpl.format(dest=zone_display, count=kills_needed)
        title = f"[SPACE] Intercept: {zone_display}"
        mission_data = {
            "target_zone":  zone_id,
            "kills_needed": kills_needed,
            "kills_done":   0,
        }
        destination = zone_display

    else:  # SURVEY_ZONE
        zone_id = _r.choice(_SURVEY_ZONES)
        zone_display = zone_id.replace("_", " ").title()
        obj_tmpl = _r.choice(_SURVEY_OBJECTIVES)
        objective = obj_tmpl.format(dest=zone_display)
        title = f"[SPACE] Survey: {zone_display}"
        mission_data = {
            "target_zone":       zone_id,
            "anomalies_required": 1,
            "anomalies_resolved": 0,
        }
        destination = zone_display

    return Mission(
        id=_generate_id(),
        mission_type=mtype,
        title=title,
        giver=giver,
        objective=objective,
        destination=destination,
        destination_room_id=None,
        reward=reward,
        required_skill=skill_hint,
        mission_data=mission_data,
        created_at=now,
        expires_at=now + MISSION_TTL,
    )


def generate_board(
    destination_rooms: Optional[list[dict]] = None,
    count: int = 6,
    skill_level: int = 3,
) -> list[Mission]:
    """
    Generate a full board of missions.

    Guarantees at least one delivery (floor mission for everyone) and
    at least one combat mission. Fills remaining slots randomly.
    """
    count = max(BOARD_MIN, min(BOARD_MAX, count))
    missions: list[Mission] = []

    # Guarantee one delivery (always available)
    delivery = generate_mission(destination_rooms, skill_level=max(1, skill_level - 1))
    delivery.mission_type = MissionType.DELIVERY
    lo, hi = PAY_RANGES[MissionType.DELIVERY]
    delivery.reward = random.randint(lo, hi // 2)  # delivery always low-end
    delivery.title = f"Delivery: {delivery.destination}"
    delivery.objective = random.choice(_DELIVERY_OBJECTIVES).format(dest=delivery.destination)
    delivery.required_skill = "stamina"
    missions.append(delivery)

    # Guarantee one combat
    combat = generate_mission(destination_rooms, skill_level=skill_level)
    combat.mission_type = MissionType.COMBAT
    lo, hi = PAY_RANGES[MissionType.COMBAT]
    combat.reward = _scale_reward(MissionType.COMBAT, skill_level)
    combat.title = f"Combat: {combat.destination}"
    combat.objective = random.choice(_COMBAT_OBJECTIVES).format(dest=combat.destination)
    combat.required_skill = random.choice(REQUIRED_SKILLS[MissionType.COMBAT])
    missions.append(combat)

    # Fill the rest
    attempts = 0
    while len(missions) < count and attempts < count * 4:
        attempts += 1
        m = generate_mission(destination_rooms, skill_level=skill_level)
        # Avoid duplicating mission types when board is small
        existing_types = {x.mission_type for x in missions}
        if m.mission_type in existing_types and len(existing_types) < len(MissionType):
            continue
        missions.append(m)

    return missions


# ── Board manager (in-memory cache, backed by DB) ──────────────────────────────

class MissionBoard:
    """
    Singleton-style mission board manager.

    The board holds the live AVAILABLE missions. The DB is the persistent store.
    On server start, the board is loaded from DB. On refresh, stale missions
    are purged and new ones generated to fill up to BOARD_MAX.

    Usage:
        board = get_mission_board()
        await board.ensure_loaded(db, rooms)
        missions = board.available_missions()
    """

    def __init__(self):
        self._missions: dict[str, Mission] = {}   # id -> Mission
        self._last_refresh: float = 0.0
        self._loaded: bool = False

    # ── Load / refresh ──

    async def ensure_loaded(self, db, rooms: Optional[list[dict]] = None) -> None:
        """Load board from DB on first call. Refresh if stale."""
        if not self._loaded:
            await self._load_from_db(db)
            self._loaded = True

        if time.time() - self._last_refresh > REFRESH_SECONDS:
            await self.refresh(db, rooms)

    async def _load_from_db(self, db) -> None:
        """Pull available missions from DB into memory."""
        rows = await db.get_available_missions()
        self._missions = {}
        for row in rows:
            try:
                data = json.loads(row["data"])
                m = Mission.from_dict(data)
                if m.status == MissionStatus.AVAILABLE:
                    self._missions[m.id] = m
            except Exception as e:
                log.warning("Failed to load mission row: %s", e)
        log.info("[missions] Loaded %d available missions from DB", len(self._missions))

    async def refresh(self, db, rooms: Optional[list[dict]] = None) -> None:
        """
        Purge expired missions, then fill the board up to BOARD_MAX.
        Called automatically by ensure_loaded() when the refresh interval passes.
        """
        now = time.time()

        # Expire stale missions
        expired_ids = [
            mid for mid, m in self._missions.items()
            if m.expires_at and m.expires_at < now
        ]
        for mid in expired_ids:
            del self._missions[mid]
            await db.expire_mission(mid)

        # Fill up
        needed = BOARD_MAX - len(self._missions)
        if needed > 0:
            new_missions = generate_board(
                destination_rooms=rooms,
                count=needed,
            )
            for m in new_missions:
                self._missions[m.id] = m
                await db.save_mission(m)

        self._last_refresh = now
        log.info("[missions] Board refreshed: %d missions available", len(self._missions))

    # ── Queries ──

    def available_missions(self) -> list[Mission]:
        """Return all available (unaccepted) missions, sorted by reward desc."""
        return sorted(
            [m for m in self._missions.values() if m.status == MissionStatus.AVAILABLE],
            key=lambda m: m.reward,
            reverse=True,
        )

    def get(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    # ── Mutations ──

    async def accept(self, mission_id: str, character_id: str, db) -> Optional[Mission]:
        """
        Accept a mission. Returns the Mission on success, None if unavailable.
        """
        m = self._missions.get(mission_id)
        if not m or m.status != MissionStatus.AVAILABLE:
            return None

        now = time.time()
        m.status = MissionStatus.ACCEPTED
        m.accepted_by = character_id
        m.accepted_at = now
        m.expires_at = now + MISSION_ACTIVE_TTL

        await db.accept_mission(mission_id, character_id, m.expires_at, m.to_dict())
        return m

    async def complete(self, mission_id: str, db) -> Optional[Mission]:
        """
        Mark a mission complete. Returns the Mission on success.
        Caller is responsible for awarding credits.
        """
        m = self._missions.get(mission_id)
        if not m or m.status != MissionStatus.ACCEPTED:
            return None

        m.status = MissionStatus.COMPLETE
        await db.complete_mission(mission_id, m.to_dict())
        del self._missions[mission_id]

        # Immediately spawn a replacement
        return m

    async def abandon(self, mission_id: str, db) -> Optional[Mission]:
        """Return an accepted mission to the board (no penalty, just resets status)."""
        m = self._missions.get(mission_id)
        if not m or m.status != MissionStatus.ACCEPTED:
            return None

        now = time.time()
        m.status = MissionStatus.AVAILABLE
        m.accepted_by = None
        m.accepted_at = None
        m.expires_at = now + MISSION_TTL   # reset TTL

        await db.abandon_mission(mission_id, m.to_dict())
        return m


# ── Module-level singleton ─────────────────────────────────────────────────────

_board: Optional[MissionBoard] = None


def get_mission_board() -> MissionBoard:
    global _board
    if _board is None:
        _board = MissionBoard()
    return _board


# ── Display helpers ────────────────────────────────────────────────────────────

_TYPE_COLORS = {
    MissionType.DELIVERY:      "\033[0;37m",    # white
    MissionType.COMBAT:        "\033[1;31m",    # bright red
    MissionType.INVESTIGATION: "\033[0;36m",    # cyan
    MissionType.SOCIAL:        "\033[1;35m",    # bright magenta
    MissionType.TECHNICAL:     "\033[0;33m",    # yellow
    MissionType.MEDICAL:       "\033[1;32m",    # bright green
    MissionType.SMUGGLING:     "\033[1;33m",    # bright yellow
    MissionType.BOUNTY:        "\033[1;31m",    # bright red
    MissionType.SLICING:       "\033[0;34m",    # blue
    MissionType.SALVAGE:       "\033[0;33m",    # yellow
}
_RESET = "\033[0m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"


_SPACE_MISSION_TAG = "[0;36m[SPACE][0m"


def format_board(missions: list[Mission]) -> list[str]:
    """
    Render the mission board for display in the client.

    Returns a list of strings to send_line() in order.
    """
    lines: list[str] = []
    lines.append(f"{_BOLD}{'='*58}{_RESET}")
    lines.append(f"{_BOLD}  MISSION BOARD  --  Mos Eisley{_RESET}")
    lines.append(f"{_DIM}  {'ID':<10} {'Type':<14} {'Reward':>8}  Objective{_RESET}")
    lines.append(f"{_DIM}  {'-'*56}{_RESET}")

    if not missions:
        lines.append("  No missions available. Check back soon.")
    else:
        for m in missions:
            color = _TYPE_COLORS.get(m.mission_type, "")
            type_label = m.mission_type.value.replace("_", " ").title()
            lines.append(
                f"  {_BOLD}{m.id:<10}{_RESET} "
                f"{color}{type_label:<14}{_RESET} "
                f"{_BOLD}{m.reward:>7,}cr{_RESET}  "
                f"{m.objective[:45]}"
                + ("..." if len(m.objective) > 45 else "")
            )

    lines.append(f"{_DIM}  Type 'accept <id>' to take a job. 'mission' to see your active job.{_RESET}")
    lines.append(f"{_BOLD}{'='*58}{_RESET}")
    return lines


def format_mission_detail(m: Mission) -> list[str]:
    """Render full detail for a single mission (shown on 'mission' command)."""
    color = _TYPE_COLORS.get(m.mission_type, "")
    type_label = m.mission_type.value.replace("_", " ").title()
    lines = [
        f"{_BOLD}{'='*58}{_RESET}",
        f"  {_BOLD}ACTIVE MISSION{_RESET}  [{m.id}]",
        f"  {color}{type_label}{_RESET}  |  Reward: {_BOLD}{m.reward:,} credits{_RESET}",
        "",
        f"  {_BOLD}Client:{_RESET}      {m.giver}",
        f"  {_BOLD}Objective:{_RESET}   {m.objective}",
        f"  {_BOLD}Destination:{_RESET} {m.destination}",
        f"  {_BOLD}Skill:{_RESET}       {m.required_skill.title()}",
    ]
    if m.expires_at:
        remaining = max(0, int(m.expires_at - time.time()))
        h, rem = divmod(remaining, 3600)
        mn = rem // 60
        lines.append(f"  {_BOLD}Time Left:{_RESET}   {h}h {mn}m")
    lines.append("")
    lines.append(f"  {_DIM}Type 'complete' when you are at the destination.{_RESET}")
    lines.append(f"  {_DIM}Type 'abandon' to return this mission to the board.{_RESET}")
    lines.append(f"{_BOLD}{'='*58}{_RESET}")
    return lines
