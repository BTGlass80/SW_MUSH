# -*- coding: utf-8 -*-
"""
NPC Crew Engine -- hiring board, wages, and crew skill resolution.

Lets players hire NPC crew members from cantina/spaceport hiring boards
and assign them to ship stations (pilot, copilot, gunner, engineer,
navigator, sensors). NPCs auto-act in their role during space combat.

Hiring boards generate NPCs using npc_generator with archetypes and
tiers appropriate to the location. Wages deduct daily.
"""
import json
import logging
import random
from dataclasses import dataclass
from typing import Optional

from engine.character import Character, SkillRegistry, ATTRIBUTE_NAMES
from engine.dice import DicePool
from engine.npc_generator import generate_npc, NPCTier, ARCHETYPES

log = logging.getLogger(__name__)

# How often wages fire in the tick loop (1 tick = 1 second).
# 14400 ticks = 4 real hours.  Six deductions per real day.
WAGE_TICK_INTERVAL = 14400


# ── Crew Roles ──
# Maps station names to the primary skill used and archetype preferences.

@dataclass
class CrewRole:
    """Defines a crew station and how it maps to skills."""
    station: str          # crew JSON key
    skill: str            # primary skill for this station
    assist_skill: str     # skill used for +1D assist (copilot only)
    archetypes: list[str] # preferred NPC archetypes for this role

CREW_ROLES: dict[str, CrewRole] = {
    "pilot": CrewRole(
        station="npc_pilot",
        skill="space transports",
        assist_skill="",
        archetypes=["pilot", "smuggler", "scout"],
    ),
    "copilot": CrewRole(
        station="npc_copilot",
        skill="space transports",
        assist_skill="space transports",
        archetypes=["pilot", "smuggler", "scout"],
    ),
    "gunner": CrewRole(
        station="npc_gunners",
        skill="starship gunnery",
        assist_skill="",
        archetypes=["pilot", "smuggler", "bounty_hunter"],
    ),
    "engineer": CrewRole(
        station="npc_engineer",
        skill="space transports repair",
        assist_skill="",
        archetypes=["mechanic"],
    ),
    "navigator": CrewRole(
        station="npc_navigator",
        skill="astrogation",
        assist_skill="",
        archetypes=["scout", "pilot", "smuggler"],
    ),
    "sensors": CrewRole(
        station="npc_sensors",
        skill="sensors",
        assist_skill="",
        archetypes=["scout", "pilot"],
    ),
}

VALID_STATIONS = set(CREW_ROLES.keys())


# ── Wage Table ──
# Per design doc: affordable but meaningful credit sink.

TIER_WAGES: dict[str, int] = {
    "extra": 30,
    "average": 80,
    "novice": 150,
    "veteran": 400,
    "superior": 1000,
}


# ── Name Generator ──
# Species-appropriate Star Wars names. Functional, not exhaustive.
# Phase 3 will expand this with a full generator.

_SW_FIRST_NAMES = {
    "Human": [
        "Kael", "Mira", "Jorn", "Tyra", "Dren", "Sabel", "Hex", "Lyss",
        "Renn", "Cade", "Thane", "Nyla", "Korr", "Sola", "Vex", "Dara",
        "Fen", "Zara", "Tal", "Asha", "Brin", "Kira", "Rosk", "Jael",
    ],
    "Rodian": [
        "Greedo", "Navik", "Beedo", "Thuku", "Kelko", "Neela", "Ponda",
        "Reelo", "Snaik", "Gotal",
    ],
    "Twi'lek": [
        "Numa", "Aayla", "Hera", "Orn", "Bib", "Lyn", "Tol", "Oola",
        "Alema", "Nima",
    ],
    "Wookiee": [
        "Grrawl", "Tyvokka", "Lowbacca", "Gorneesh", "Ralrra", "Shoran",
        "Dryanta", "Kikkir", "Nawruun", "Wrrlykam",
    ],
    "Trandoshan": [
        "Bossk", "Cradossk", "Ssorku", "Garnac", "Tusserk", "Kreshta",
        "Drolan", "Sskel",
    ],
    "Duros": [
        "Cad", "Baniss", "Ohwun", "Lai", "Nien", "Kadlo", "Ellor",
        "Tomrus",
    ],
    "Sullustan": [
        "Nien", "Dllr", "Sien", "Aril", "Drej", "Nunb", "Syub",
        "Bramsin",
    ],
    "Bothan": [
        "Borsk", "Koth", "Dreyla", "Tav", "Asyr", "Traest", "Fey",
        "Kursk",
    ],
    "Mon Calamari": [
        "Ackbar", "Bant", "Cilghal", "Jesmin", "Nahdar", "Quarren",
        "Rieelo", "Timi",
    ],
}

_SW_LAST_NAMES = {
    "Human": [
        "Voss", "Tann", "Duul", "Korr", "Dace", "Reth", "Vane", "Torr",
        "Kayl", "Roon", "Stark", "Dreel", "Mox", "Bren", "Zayne", "Kess",
    ],
    "Rodian": [
        "Tansen", "Blissex", "Dansen", "Kelada", "Tansen",
    ],
    "Twi'lek": [
        "Secura", "Syndulla", "Fortuna", "Ransen", "Bansen",
    ],
    "Wookiee": [],  # Wookiees use single names
    "Trandoshan": [],  # Usually single names
    "Duros": [
        "Bane", "Kepp", "Tomrus", "Nansen",
    ],
    "Sullustan": [
        "Nunb", "Nansen", "Snit", "Sovv",
    ],
    "Bothan": [
        "Fey'lya", "Melan", "Sei'lar", "Dansen",
    ],
    "Mon Calamari": [
        "Ackbar", "Eerin", "Vansen", "Dansen",
    ],
}

_ALL_SPECIES = list(_SW_FIRST_NAMES.keys())


def generate_name(species: str = "Human") -> str:
    """Generate a species-appropriate Star Wars name."""
    firsts = _SW_FIRST_NAMES.get(species, _SW_FIRST_NAMES["Human"])
    lasts = _SW_LAST_NAMES.get(species, _SW_LAST_NAMES["Human"])
    first = random.choice(firsts)
    if lasts:
        return f"{first} {random.choice(lasts)}"
    return first


# ── Location Profiles ──
# Controls what the hiring board generates based on room properties.

@dataclass
class LocationProfile:
    """Hiring board flavor for a type of location."""
    tier_weights: dict[str, float]    # tier -> relative weight
    archetype_pool: list[str]         # archetypes that show up here
    species_weights: dict[str, float] # species -> relative weight
    board_size: tuple[int, int]       # (min, max) NPCs on the board

# Default profiles keyed by room property "hiring_profile"
LOCATION_PROFILES: dict[str, LocationProfile] = {
    "backwater_cantina": LocationProfile(
        tier_weights={"extra": 0.4, "average": 0.35, "novice": 0.2, "veteran": 0.05},
        archetype_pool=["smuggler", "mechanic", "thug", "pilot", "scout"],
        species_weights={"Human": 0.4, "Rodian": 0.15, "Twi'lek": 0.15,
                         "Duros": 0.1, "Sullustan": 0.1, "Trandoshan": 0.1},
        board_size=(3, 5),
    ),
    "major_spaceport": LocationProfile(
        tier_weights={"average": 0.2, "novice": 0.45, "veteran": 0.3, "superior": 0.05},
        archetype_pool=["pilot", "mechanic", "scout", "smuggler", "merchant"],
        species_weights={"Human": 0.35, "Duros": 0.15, "Sullustan": 0.15,
                         "Mon Calamari": 0.1, "Bothan": 0.1, "Twi'lek": 0.1,
                         "Rodian": 0.05},
        board_size=(4, 6),
    ),
    "imperial_sector": LocationProfile(
        tier_weights={"novice": 0.3, "veteran": 0.5, "superior": 0.2},
        archetype_pool=["pilot", "mechanic", "imperial_officer", "scout"],
        species_weights={"Human": 0.85, "Duros": 0.1, "Bothan": 0.05},
        board_size=(3, 5),
    ),
    "rebel_base": LocationProfile(
        tier_weights={"average": 0.15, "novice": 0.45, "veteran": 0.35, "superior": 0.05},
        archetype_pool=["pilot", "mechanic", "scout", "medic", "smuggler"],
        species_weights={"Human": 0.3, "Mon Calamari": 0.15, "Sullustan": 0.15,
                         "Bothan": 0.15, "Twi'lek": 0.1, "Wookiee": 0.1,
                         "Duros": 0.05},
        board_size=(3, 5),
    ),
    "default": LocationProfile(
        tier_weights={"extra": 0.2, "average": 0.35, "novice": 0.3, "veteran": 0.15},
        archetype_pool=["pilot", "mechanic", "smuggler", "scout"],
        species_weights={"Human": 0.5, "Rodian": 0.1, "Twi'lek": 0.1,
                         "Duros": 0.1, "Sullustan": 0.1, "Bothan": 0.1},
        board_size=(3, 5),
    ),
}


def _weighted_choice(weights: dict[str, float]) -> str:
    """Pick a key from a {key: weight} dict using weighted random selection."""
    items = list(weights.items())
    keys = [k for k, _ in items]
    vals = [v for _, v in items]
    return random.choices(keys, weights=vals, k=1)[0]


# ── Hiring Board ──

def generate_hiring_board(profile_key: str = "default") -> list[dict]:
    """
    Generate a set of hireable NPC crew members for a location.

    Returns a list of dicts, each containing:
      - Full NPC stat block (from generate_npc)
      - hire_wage: daily wage in credits
      - crew_role_hint: best-fit station for this NPC

    These get stored via db.create_npc() with char_sheet_json set to
    the stat block and hire_wage set to the wage.
    """
    profile = LOCATION_PROFILES.get(profile_key, LOCATION_PROFILES["default"])
    min_npcs, max_npcs = profile.board_size
    count = random.randint(min_npcs, max_npcs)

    board = []
    used_names: set[str] = set()

    for _ in range(count):
        tier = _weighted_choice(profile.tier_weights)
        archetype = random.choice(profile.archetype_pool)
        species = _weighted_choice(profile.species_weights)

        # Generate unique name
        for _attempt in range(10):
            name = generate_name(species)
            if name not in used_names:
                break
        used_names.add(name)

        # Generate the stat block
        sheet = generate_npc(tier=tier, archetype=archetype,
                             species=species, name=name)

        # Determine wage
        wage = TIER_WAGES.get(tier, 80)

        # Determine best crew role based on archetype
        role_hint = _best_role_for_archetype(archetype)

        board.append({
            "sheet": sheet,
            "wage": wage,
            "role_hint": role_hint,
            "tier": tier,
            "archetype": archetype,
            "species": species,
        })

    return board


def _best_role_for_archetype(archetype: str) -> str:
    """Determine the best crew station for a given archetype."""
    for role_name, role in CREW_ROLES.items():
        if archetype in role.archetypes:
            return role_name
    return "gunner"  # fallback


# ── NPC Skill Resolution ──

def npc_to_character(npc_row: dict) -> Character:
    """
    Convert an NPC database row into a Character object for skill resolution.

    The NPC's char_sheet_json contains the stat block from generate_npc().
    Character.from_db_dict() can parse this directly because both use
    the same {attributes: {}, skills: {}} format.
    """
    sheet_json = npc_row.get("char_sheet_json", "{}")
    if isinstance(sheet_json, str):
        try:
            sheet = json.loads(sheet_json)
        except (json.JSONDecodeError, TypeError):
            sheet = {}
    else:
        sheet = sheet_json

    # from_db_dict expects the same top-level keys that a character row has.
    # NPC sheets from generate_npc() use the same attribute/skill format.
    sheet.setdefault("name", npc_row.get("name", "Unknown"))
    sheet.setdefault("species", npc_row.get("species", "Human"))
    sheet.setdefault("wound_level", 0)

    return Character.from_db_dict(sheet)


def resolve_npc_skill(npc_row: dict, skill_name: str,
                       skill_reg: SkillRegistry) -> DicePool:
    """
    Resolve the effective dice pool for an NPC performing a skill check.

    Used by combat and crew station logic to roll NPC actions.
    """
    char = npc_to_character(npc_row)
    return char.get_skill_pool(skill_name, skill_reg)


def get_station_skill(station: str) -> str:
    """Get the primary skill name for a crew station."""
    role = CREW_ROLES.get(station)
    return role.skill if role else ""


# ── Crew JSON Helpers ──

def get_crew_json(ship: dict) -> dict:
    """Parse the crew JSON from a ship row, safely."""
    crew = ship.get("crew", "{}")
    if isinstance(crew, str):
        try:
            return json.loads(crew)
        except (json.JSONDecodeError, TypeError):
            return {}
    return crew or {}


def set_npc_station(crew: dict, station: str, npc_id: int) -> dict:
    """
    Assign an NPC to a station in the crew JSON.

    Gunners use a list (npc_gunners); all other stations are single slots.
    Returns the modified crew dict (caller must save).
    """
    role = CREW_ROLES.get(station)
    if not role:
        return crew

    key = role.station
    if station == "gunner":
        gunners = crew.get(key, [])
        if npc_id not in gunners:
            gunners.append(npc_id)
        crew[key] = gunners
    else:
        crew[key] = npc_id
    return crew


def remove_npc_from_station(crew: dict, station: str, npc_id: int) -> dict:
    """
    Remove an NPC from a station in the crew JSON.
    Returns the modified crew dict.
    """
    role = CREW_ROLES.get(station)
    if not role:
        return crew

    key = role.station
    if station == "gunner":
        gunners = crew.get(key, [])
        if npc_id in gunners:
            gunners.remove(npc_id)
        crew[key] = gunners
    else:
        if crew.get(key) == npc_id:
            crew[key] = None
    return crew


def remove_npc_from_all_stations(crew: dict, npc_id: int) -> dict:
    """Remove an NPC from whatever station they occupy in the crew JSON."""
    for role in CREW_ROLES.values():
        key = role.station
        if key == "npc_gunners":
            gunners = crew.get(key, [])
            if npc_id in gunners:
                gunners.remove(npc_id)
            crew[key] = gunners
        else:
            if crew.get(key) == npc_id:
                crew[key] = None
    return crew


def get_npc_ids_on_ship(crew: dict) -> list[int]:
    """Extract all NPC IDs from a ship's crew JSON."""
    ids = []
    for role in CREW_ROLES.values():
        key = role.station
        val = crew.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            ids.extend(val)
        elif isinstance(val, int):
            ids.append(val)
    return ids


# ── Wage Tick ──

async def process_wage_tick(db, session_mgr) -> dict:
    """
    Process one wage cycle for all characters who have hired crew.

    Called from the game tick loop (e.g., every 60 real minutes = 1 game day).
    Returns a summary dict: {char_id: {"paid": total, "departed": [names]}}.
    """
    # Find all characters who have hired NPCs
    # We query all NPCs with a non-null hired_by
    all_hired = await db._db.execute_fetchall(
        "SELECT DISTINCT hired_by FROM npcs WHERE hired_by IS NOT NULL"
    )
    if not all_hired:
        return {}

    summary = {}
    for row in all_hired:
        char_id = row["hired_by"]
        total_paid, departed = await db.deduct_crew_wages(char_id)
        summary[char_id] = {"paid": total_paid, "departed": departed}

        # Notify the player if they're online
        if departed:
            session = session_mgr.find_by_character(char_id)
            if session:
                for name in departed:
                    await session.send_line(
                        f"  \033[1;33m{name} has left your crew -- unpaid wages.\033[0m"
                    )
        if total_paid > 0:
            session = session_mgr.find_by_character(char_id)
            if session:
                await session.send_line(
                    f"  \033[0;36mCrew wages paid: {total_paid:,} credits.\033[0m"
                )

    return summary


def format_roster_entry(npc_row: dict) -> str:
    """Format a single NPC crew member for the roster display."""
    sheet_json = npc_row.get("char_sheet_json", "{}")
    if isinstance(sheet_json, str):
        try:
            sheet = json.loads(sheet_json)
        except (json.JSONDecodeError, TypeError):
            sheet = {}
    else:
        sheet = sheet_json

    name = npc_row.get("name", "Unknown")
    tier = sheet.get("tier", "?").title()
    template = sheet.get("template", "?")
    station = npc_row.get("assigned_station", "")
    wage = npc_row.get("hire_wage", 0)

    station_display = station.upper() if station else "UNASSIGNED"
    return (f"  {name:20s} {template:12s} ({tier:8s})  "
            f"{station_display:12s}  {wage:,} cr/day")


def format_hire_entry(entry: dict, index: int) -> str:
    """Format a hiring board entry for display."""
    sheet = entry["sheet"]
    name = sheet.get("name", "Unknown")
    tier = entry["tier"].title()
    role = entry["role_hint"].title()
    wage = entry["wage"]

    # Find the primary skill value for display
    role_def = CREW_ROLES.get(entry["role_hint"])
    skill_name = role_def.skill if role_def else ""
    skill_val = sheet.get("skills", {}).get(skill_name, "")

    # Build skill display: attribute + skill bonus
    if skill_val and role_def:
        # Get parent attribute for this skill
        attr_name = _skill_to_attribute(skill_name)
        attr_val = sheet.get("attributes", {}).get(attr_name, "2D")
        display_skill = f"{skill_name.title()} {attr_val}+{skill_val}"
    else:
        display_skill = f"{role} specialist"

    return (f"  {index}. {name:20s} {role:10s} ({tier:8s})  "
            f"{display_skill:30s}  {wage:,} cr/day")


def _skill_to_attribute(skill_name: str) -> str:
    """Map a skill name to its parent attribute. Basic lookup."""
    # These are the crew-relevant skills and their parent attributes
    _MAP = {
        "space transports": "mechanical",
        "starfighter piloting": "mechanical",
        "starship gunnery": "mechanical",
        "astrogation": "mechanical",
        "sensors": "mechanical",
        "space transports repair": "technical",
        "starfighter repair": "technical",
        "droid repair": "technical",
    }
    return _MAP.get(skill_name.lower(), "mechanical")
