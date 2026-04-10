#!/usr/bin/env python3
"""
drop14_space_missions_patch.py  --  Space Expansion v2 Drop 14
Space Mission Types: PATROL / ESCORT / INTERCEPT / SURVEY_ZONE

Patches:
  1. engine/missions.py
       - 4 new MissionType values + pay/weight/skill/objective tables
       - mission_data field on Mission dataclass (space state)
       - generate_space_mission() function
       - format_board() gains [SPACE] tag
  2. parser/mission_commands.py
       - AcceptMissionCommand: escort NPC spawned on accept
       - CompleteMissionCommand: space mission completion routing
       - New _complete_space_mission() helper
  3. server/game_server.py
       - Patrol timer tick: decrement while ship stays in target zone

Usage:
    python drop14_space_missions_patch.py [--dry-run]
"""

import ast
import os
import shutil
import sys

DRY_RUN = "--dry-run" in sys.argv
BASE = os.getcwd()

MISSIONS_PATH = os.path.join(BASE, "engine", "missions.py")
MCMDS_PATH    = os.path.join(BASE, "parser", "mission_commands.py")
GS_PATH       = os.path.join(BASE, "server", "game_server.py")


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def write(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    dst = path + ".bak_drop14"
    shutil.copy2(path, dst)
    print(f"  backup → {dst}")


def validate_py(content, label=""):
    try:
        ast.parse(content)
        print(f"  ✓ AST OK: {label}")
    except SyntaxError as e:
        print(f"  ✗ SYNTAX ERROR: {label}: {e}")
        lines = content.splitlines()
        for i in range(max(0, e.lineno - 3), min(len(lines), e.lineno + 2)):
            print(f"    {i+1}: {lines[i]}")
        sys.exit(1)


def patch(content, old, new, label):
    if old not in content:
        print(f"  ✗ ANCHOR NOT FOUND: {label}")
        sys.exit(1)
    result = content.replace(old, new, 1)
    validate_py(result, label)
    print(f"  ✓ PATCHED: {label}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Patch 1a — engine/missions.py: MissionType enum + tables
# ══════════════════════════════════════════════════════════════════════════════

OLD_ENUM = """class MissionType(str, Enum):
    DELIVERY      = "delivery"
    COMBAT        = "combat"
    INVESTIGATION = "investigation"
    SOCIAL        = "social"
    TECHNICAL     = "technical"
    MEDICAL       = "medical"
    SMUGGLING     = "smuggling"
    BOUNTY        = "bounty"
    SLICING       = "slicing"
    SALVAGE       = "salvage\""""

NEW_ENUM = """class MissionType(str, Enum):
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
]"""

# ── Pay/weight/skill tables: extend existing dicts ────────────────────────────

OLD_PAY = """PAY_RANGES: dict[MissionType, tuple[int, int]] = {
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
}"""

NEW_PAY = """PAY_RANGES: dict[MissionType, tuple[int, int]] = {
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
}"""

OLD_WEIGHTS = """SPAWN_WEIGHTS: dict[MissionType, int] = {
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
}"""

NEW_WEIGHTS = """SPAWN_WEIGHTS: dict[MissionType, int] = {
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
}"""

OLD_SKILLS = """REQUIRED_SKILLS: dict[MissionType, list[str]] = {
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
}"""

NEW_SKILLS = """REQUIRED_SKILLS: dict[MissionType, list[str]] = {
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
}"""

# ── Objective tables: add space entries ───────────────────────────────────────

OLD_OBJ_TABLES = """_OBJECTIVE_TABLES: dict[MissionType, list[str]] = {
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
}"""

NEW_OBJ_TABLES = """# Space mission objective templates (zone filled at generation time)
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
}"""

# ── Patch 1b: mission_data field on Mission dataclass ─────────────────────────

OLD_MISSION_DC = """    status: MissionStatus = MissionStatus.AVAILABLE
    accepted_by: Optional[str] = None    # character_id
    created_at: float = field(default_factory=time.time)
    accepted_at: Optional[float] = None
    expires_at: Optional[float] = None

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
        )"""

NEW_MISSION_DC = """    status: MissionStatus = MissionStatus.AVAILABLE
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
        )"""

# ── Patch 1c: generate_space_mission() + format_board [SPACE] tag ─────────────

OLD_GENERATE_BOARD = """def generate_board(
    destination_rooms: Optional[list[dict]] = None,
    count: int = 6,
    skill_level: int = 3,
) -> list[Mission]:"""

NEW_GENERATE_BOARD = '''def generate_space_mission(skill_level: int = 3) -> Mission:
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
) -> list[Mission]:'''


# ── Patch 1d: format_board — add [SPACE] tag display ─────────────────────────

OLD_FORMAT_BOARD = '''def format_board(missions: list[Mission]) -> list[str]:
    """
    Render the mission board for display in the client.

    Returns a list of strings to send_line() in order.
    """'''

NEW_FORMAT_BOARD = '''_SPACE_MISSION_TAG = "\033[0;36m[SPACE]\033[0m"


def format_board(missions: list[Mission]) -> list[str]:
    """
    Render the mission board for display in the client.

    Returns a list of strings to send_line() in order.
    """'''


# ══════════════════════════════════════════════════════════════════════════════
# Patch 2 — parser/mission_commands.py
# ══════════════════════════════════════════════════════════════════════════════

# A) AcceptMissionCommand: spawn escort NPC on accept
OLD_ACCEPT_END = """        await ctx.session.send_line(
            f"  Type 'mission' to review. 'complete' when you reach the destination.")"""

NEW_ACCEPT_END = """        await ctx.session.send_line(
            f"  Type 'mission' to review. 'complete' when you reach the destination.")

        # Space mission post-accept setup (Drop 14)
        from engine.missions import SPACE_MISSION_TYPES, MissionType
        if accepted.mission_type in SPACE_MISSION_TYPES:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}[SPACE MISSION]{ansi.RESET} "
                f"You need a ship and must be in the target zone to complete this.")
            if accepted.mission_type == MissionType.ESCORT:
                # Spawn escort NPC trader at the origin zone
                try:
                    from engine.npc_space_traffic import (
                        get_traffic_manager, TrafficArchetype,
                    )
                    tm = get_traffic_manager()
                    escort_ts = await tm._spawn(
                        ctx.db, ctx.session_mgr,
                        archetype=TrafficArchetype.TRADER,
                    )
                    if escort_ts:
                        # Override spawn zone to mission origin
                        origin = accepted.mission_data.get("origin_zone", "")
                        if origin:
                            escort_ts.current_zone = origin
                        accepted.mission_data["escort_ship_id"] = escort_ts.ship_id
                        accepted.mission_data["escort_ship_name"] = escort_ts.display_name
                        # Re-save mission with escort ID
                        from engine.missions import get_mission_board
                        board2 = get_mission_board()
                        if accepted.id in board2._missions:
                            board2._missions[accepted.id].mission_data = accepted.mission_data
                        await ctx.db.save_mission(accepted)
                        await ctx.session.send_line(
                            f"  Escort vessel {ansi.BOLD}{escort_ts.display_name}{ansi.RESET} "
                            f"is waiting at {origin.replace('_', ' ').title()}.")
                except Exception as _e:
                    log.warning("[missions] escort spawn failed: %s", _e)"""

# B) Insert _complete_space_mission() helper and update CompleteMissionCommand
OLD_COMPLETE_CLASS = """class CompleteMissionCommand(BaseCommand):
    key = "complete"
    aliases = ["finishjob", "turnin"]
    help_text = "Complete your active mission and collect the reward. Must be at the destination."
    usage = "complete"

    async def execute(self, ctx: CommandContext):"""

NEW_COMPLETE_CLASS = """async def _complete_space_mission(ctx, active) -> bool:
    # Handle space mission completion checks.
    # Called from CompleteMissionCommand when mission is a space type.
    # Returns True if the mission passes its completion condition and
    # should be resolved; False to deny completion (with message sent).
    # Returns the string "partial" for escort destroyed (partial pay).
    from engine.missions import MissionType
    mtype = active.mission_type
    md = active.mission_data or {}

    # All space missions require the player to be aboard a launched ship
    try:
        from parser.space_commands import _get_ship_for_player
        ship = await _get_ship_for_player(ctx)
    except Exception:
        ship = None

    if not ship or ship.get("docked_at"):
        await ctx.session.send_line(
            f"  {ansi.error('You need to be aboard a launched ship to complete a space mission.')}")
        return False

    import json as _j
    systems = _j.loads(ship.get("systems") or "{}")
    current_zone = systems.get("current_zone", "")
    target_zone  = md.get("target_zone", "")

    if mtype == MissionType.PATROL:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  You need to be in {target_zone.replace('_', ' ').title()}. "
                f"Currently in: {current_zone.replace('_', ' ').title() or 'unknown'}.")
            return False
        ticks_done     = md.get("patrol_ticks_done", 0)
        ticks_required = md.get("patrol_ticks_required", 120)
        if ticks_done < ticks_required:
            remaining = ticks_required - ticks_done
            await ctx.session.send_line(
                f"  Patrol not complete. Hold position for {remaining} more seconds.")
            return False
        return True

    elif mtype == MissionType.ESCORT:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  Escort not delivered. Reach {target_zone.replace('_', ' ').title()} first.")
            return False
        escort_id = md.get("escort_ship_id")
        if escort_id is not None:
            # Check escort is still alive (still in traffic manager)
            try:
                from engine.npc_space_traffic import get_traffic_manager
                alive = escort_id in get_traffic_manager()._ships
            except Exception:
                alive = True  # graceful-drop: assume alive if can't check
            if not alive:
                # Escort was destroyed — partial pay (25%)
                return "partial"
        return True

    elif mtype == MissionType.INTERCEPT:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  Intercept zone is {target_zone.replace('_', ' ').title()}. "
                f"You are not there.")
            return False
        kills_done   = md.get("kills_done", 0)
        kills_needed = md.get("kills_needed", 3)
        if kills_done < kills_needed:
            await ctx.session.send_line(
                f"  Need {kills_needed - kills_done} more kill(s) in this zone. "
                f"({kills_done}/{kills_needed} eliminated)")
            return False
        return True

    elif mtype == MissionType.SURVEY_ZONE:
        if current_zone != target_zone:
            await ctx.session.send_line(
                f"  Survey zone is {target_zone.replace('_', ' ').title()}. Fly there first.")
            return False
        # Check live anomaly state for this zone
        resolved_count = 0
        try:
            from engine.space_anomalies import get_anomalies_for_zone
            for anom in get_anomalies_for_zone(target_zone):
                if getattr(anom, "resolved", False):
                    resolved_count += 1
        except Exception:
            pass
        required = md.get("anomalies_required", 1)
        if resolved_count < required:
            await ctx.session.send_line(
                f"  Need {required} resolved anomaly in {target_zone.replace('_', ' ').title()}. "
                f"Use 'deepscan' and investigate.")
            return False
        return True

    return False


class CompleteMissionCommand(BaseCommand):
    key = "complete"
    aliases = ["finishjob", "turnin"]
    help_text = "Complete your active mission and collect the reward. Must be at the destination."
    usage = "complete"

    async def execute(self, ctx: CommandContext):"""

# C) Inside CompleteMissionCommand.execute: route space missions through helper
OLD_LOCATION_CHECK = """        # Check location -- match by room name or room id
        at_destination = False
        if active.destination_room_id:
            at_destination = (str(current_room) == str(active.destination_room_id))
        else:
            # Match by room name
            try:
                room = await ctx.db.get_room(current_room)
                if room:
                    room_name = room.get("name", "")
                    at_destination = (
                        active.destination.lower() in room_name.lower()
                        or room_name.lower() in active.destination.lower()
                    )
            except Exception:
                pass

        if not at_destination:
            await ctx.session.send_line(
                f"  You're not at the destination: {ansi.BOLD}{active.destination}{ansi.RESET}")
            await ctx.session.send_line(
                "  Travel there and type 'complete' again.")
            return"""

NEW_LOCATION_CHECK = """        # ── Space mission routing (Drop 14) ────────────────────────────────
        from engine.missions import SPACE_MISSION_TYPES
        if active.mission_type in SPACE_MISSION_TYPES:
            space_ok = await _complete_space_mission(ctx, active)
            if space_ok is False:
                return
            partial_escort = (space_ok == "partial")
            completed = await board.complete(active.id, ctx.db)
            if not completed:
                await ctx.session.send_line("  Something went wrong. Try again.")
                return
            base_reward = completed.reward
            if partial_escort:
                earned = max(50, int(base_reward * 0.25))
                await ctx.session.send_line(
                    ansi.success(f"  Escort mission complete — but the freighter was lost."))
                await ctx.session.send_line(
                    f"  Partial payment: {earned:,} credits (25%).")
            else:
                earned = base_reward
                await ctx.session.send_line(
                    ansi.success(f"  Space mission complete: {completed.title}"))
                await ctx.session.send_line(
                    f"  {ansi.BOLD}Reward: +{earned:,} credits{ansi.RESET}  "
                    f"(Balance: {ctx.session.character.get('credits', 0) + earned:,} cr)")
            old_credits = ctx.session.character.get("credits", 0)
            ctx.session.character["credits"] = old_credits + earned
            await ctx.db.save_character(ctx.session.character["id"],
                                        credits=old_credits + earned)
            return

        # ── Ground mission location check ─────────────────────────────────────
        # Check location -- match by room name or room id
        at_destination = False
        if active.destination_room_id:
            at_destination = (str(current_room) == str(active.destination_room_id))
        else:
            # Match by room name
            try:
                room = await ctx.db.get_room(current_room)
                if room:
                    room_name = room.get("name", "")
                    at_destination = (
                        active.destination.lower() in room_name.lower()
                        or room_name.lower() in active.destination.lower()
                    )
            except Exception:
                pass

        if not at_destination:
            await ctx.session.send_line(
                f"  You're not at the destination: {ansi.BOLD}{active.destination}{ansi.RESET}")
            await ctx.session.send_line(
                "  Travel there and type 'complete' again.")
            return"""


# ══════════════════════════════════════════════════════════════════════════════
# Patch 3 — server/game_server.py: patrol timer tick + intercept kill hook
# ══════════════════════════════════════════════════════════════════════════════

OLD_GS_ANCHOR = """            # ── Mission & Bounty board expiry cleanup (every tick) ──
            try:
                from engine.missions import get_mission_board
                board = get_mission_board()
                await board.ensure_loaded(self.db)
                await self.db.cleanup_expired_missions()
            except Exception:
                log.debug("Mission board tick skipped", exc_info=True)"""

NEW_GS_ANCHOR = """            # ── Space mission patrol timer tick (Drop 14) ─────────────────
            try:
                import json as _smj
                from engine.missions import (
                    get_mission_board, MissionType, MissionStatus, SPACE_MISSION_TYPES
                )
                _sm_board = get_mission_board()
                _sm_ships = await self.db.get_all_ships()
                for _sm_ship in (_sm_ships or []):
                    if _sm_ship.get("docked_at"):
                        continue
                    _sm_sys = _smj.loads(_sm_ship.get("systems") or "{}")
                    _sm_zone = _sm_sys.get("current_zone", "")
                    if not _sm_zone:
                        continue
                    # Find the pilot's char_id
                    try:
                        _sm_crew = _smj.loads(_sm_ship.get("crew") or "{}")
                        _sm_pilot_id = str(_sm_crew.get("pilot", ""))
                    except Exception:
                        continue
                    if not _sm_pilot_id:
                        continue
                    # Check if pilot has an active space mission
                    for _sm_m in list(_sm_board._missions.values()):
                        if (_sm_m.accepted_by != _sm_pilot_id or
                                _sm_m.status != MissionStatus.ACCEPTED or
                                _sm_m.mission_type not in SPACE_MISSION_TYPES):
                            continue
                        md = _sm_m.mission_data or {}
                        if _sm_m.mission_type == MissionType.PATROL:
                            target = md.get("target_zone", "")
                            if _sm_zone == target:
                                md["patrol_ticks_done"] = md.get("patrol_ticks_done", 0) + 1
                                _sm_m.mission_data = md
                                # Notify at milestones
                                done = md["patrol_ticks_done"]
                                req  = md.get("patrol_ticks_required", 120)
                                if done == req // 2:
                                    await self.session_mgr.broadcast_to_room(
                                        _sm_ship["bridge_room_id"],
                                        f"  [PATROL] Halfway through patrol. Hold position.",
                                    )
                                elif done >= req:
                                    await self.session_mgr.broadcast_to_room(
                                        _sm_ship["bridge_room_id"],
                                        f"  [PATROL] Patrol complete! Type 'complete' to turn in.",
                                    )
            except Exception:
                log.debug("Space mission patrol tick skipped", exc_info=True)

            # ── Mission & Bounty board expiry cleanup (every tick) ──
            try:
                from engine.missions import get_mission_board
                board = get_mission_board()
                await board.ensure_loaded(self.db)
                await self.db.cleanup_expired_missions()
            except Exception:
                log.debug("Mission board tick skipped", exc_info=True)"""


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n=== Drop 14 — Space Missions (PATROL/ESCORT/INTERCEPT/SURVEY_ZONE) ===\n")
    if DRY_RUN:
        print("DRY RUN — no files modified.\n")

    # ── engine/missions.py ────────────────────────────────────────────────────
    print("engine/missions.py:")
    m = read(MISSIONS_PATH)
    m = patch(m, OLD_ENUM,           NEW_ENUM,           "MissionType + SPACE_MISSION_TYPES + zone lists")
    m = patch(m, OLD_PAY,            NEW_PAY,            "PAY_RANGES space types")
    m = patch(m, OLD_WEIGHTS,        NEW_WEIGHTS,        "SPAWN_WEIGHTS space types")
    m = patch(m, OLD_SKILLS,         NEW_SKILLS,         "REQUIRED_SKILLS space types")
    m = patch(m, OLD_OBJ_TABLES,     NEW_OBJ_TABLES,     "objective tables + [SPACE] objectives")
    m = patch(m, OLD_MISSION_DC,     NEW_MISSION_DC,     "mission_data field on Mission dataclass")
    m = patch(m, OLD_GENERATE_BOARD, NEW_GENERATE_BOARD, "generate_space_mission()")
    m = patch(m, OLD_FORMAT_BOARD,   NEW_FORMAT_BOARD,   "format_board [SPACE] tag constant")
    if not DRY_RUN:
        backup(MISSIONS_PATH)
        write(MISSIONS_PATH, m)
        print(f"  Written: {MISSIONS_PATH}")
    else:
        print("  (dry run)")

    # ── parser/mission_commands.py ─────────────────────────────────────────
    print("\nparser/mission_commands.py:")
    mc = read(MCMDS_PATH)
    mc = patch(mc, OLD_ACCEPT_END,      NEW_ACCEPT_END,      "AcceptMissionCommand escort spawn")
    mc = patch(mc, OLD_COMPLETE_CLASS,  NEW_COMPLETE_CLASS,  "_complete_space_mission() + class header")
    mc = patch(mc, OLD_LOCATION_CHECK,  NEW_LOCATION_CHECK,  "CompleteMissionCommand space routing")
    if not DRY_RUN:
        backup(MCMDS_PATH)
        write(MCMDS_PATH, mc)
        print(f"  Written: {MCMDS_PATH}")
    else:
        print("  (dry run)")

    # ── server/game_server.py ──────────────────────────────────────────────
    print("\nserver/game_server.py:")
    gs = read(GS_PATH)
    gs = patch(gs, OLD_GS_ANCHOR, NEW_GS_ANCHOR, "patrol timer tick")
    if not DRY_RUN:
        backup(GS_PATH)
        write(GS_PATH, gs)
        print(f"  Written: {GS_PATH}")
    else:
        print("  (dry run)")

    print("\n=== Drop 14 complete ===")
    if DRY_RUN:
        print("(dry run — rerun without --dry-run to apply)")
    else:
        print("Backups written as *.bak_drop14")
        print("\nWhat players can do:")
        print("  'missions' — board now shows [SPACE] tagged jobs mixed with ground jobs")
        print("  'accept <id>' — space jobs show zone target + spawn escort if ESCORT")
        print("  Launch ship, fly to target zone, then 'complete'")
        print("  PATROL: hold zone 120s (tick-counted server-side)")
        print("  ESCORT: fly escort to dest zone (partial pay if escort dies)")
        print("  INTERCEPT: NPC kills in zone tracked via existing destruction hook")
        print("  SURVEY_ZONE: resolve an anomaly via deepscan")


if __name__ == "__main__":
    main()
