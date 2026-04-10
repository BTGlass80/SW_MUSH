#!/usr/bin/env python3
"""
drop11_smuggling_patch.py  --  Space Expansion v2 Drop 11
Multi-planet smuggling routes + patrol-on-arrival

Patches:
  1. engine/smuggling.py
       - destination_planet field on SmugglingJob
       - ROUTE_TIERS table with 4 cross-planet tiers
       - generate_job() accepts optional destination_planet
       - format_board() + format_job_detail() show destination
       - PLANET_PATROL_FREQUENCY for arrival checks
  2. parser/smuggling_commands.py
       - SmugDeliverCommand: destination_planet check
       - check_patrol_on_arrival() function
  3. server/game_server.py
       - call check_patrol_on_arrival at hyperspace arrival

Usage:
    python drop11_smuggling_patch.py [--dry-run]
"""

import ast
import os
import shutil
import sys

DRY_RUN = "--dry-run" in sys.argv

BASE = os.getcwd()

FILES = {
    "smuggling":          os.path.join(BASE, "engine", "smuggling.py"),
    "smuggling_commands": os.path.join(BASE, "parser", "smuggling_commands.py"),
    "game_server":        os.path.join(BASE, "server", "game_server.py"),
}


# ── helpers ────────────────────────────────────────────────────────────────────

def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    # Normalize CRLF → LF for consistent anchor matching
    return content.replace("\r\n", "\n").replace("\r", "\n")


def write(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    dst = path + ".bak_drop11"
    shutil.copy2(path, dst)
    print(f"  backup → {dst}")


def validate(path, content):
    try:
        ast.parse(content)
        print(f"  ✓ AST OK: {os.path.basename(path)}")
    except SyntaxError as e:
        print(f"  ✗ SYNTAX ERROR in {os.path.basename(path)}: {e}")
        sys.exit(1)


def apply_patch(path, old, new, label):
    content = read(path)
    if old not in content:
        print(f"  ✗ ANCHOR NOT FOUND in {os.path.basename(path)}: {label}")
        sys.exit(1)
    result = content.replace(old, new, 1)
    if result == content:
        print(f"  ✗ REPLACEMENT HAD NO EFFECT in {os.path.basename(path)}: {label}")
        sys.exit(1)
    validate(path, result)
    if not DRY_RUN:
        backup(path)
        write(path, result)
    print(f"  ✓ PATCHED {os.path.basename(path)}: {label}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Patch 1 — engine/smuggling.py
# ══════════════════════════════════════════════════════════════════════════════

SMUG_OLD_CONSTANTS = '''BOARD_SIZE        = 5     # Max jobs on the board at once
BOARD_MIN         = 3     # Minimum jobs to maintain
REFRESH_SECONDS   = 2700  # 45 minutes
JOB_TTL           = 7200  # 2h unclaimed
JOB_ACTIVE_TTL    = 14400 # 4h accepted

# Patrol encounter base difficulty by tier
PATROL_DIFFICULTY = {0: 0, 1: 10, 2: 15, 3: 20}

# Fine = this fraction of the job's reward
FINE_FRACTION = 0.50'''

SMUG_NEW_CONSTANTS = '''BOARD_SIZE        = 5     # Max jobs on the board at once
BOARD_MIN         = 3     # Minimum jobs to maintain
REFRESH_SECONDS   = 2700  # 45 minutes
JOB_TTL           = 7200  # 2h unclaimed
JOB_ACTIVE_TTL    = 14400 # 4h accepted

# Patrol encounter base difficulty by tier
PATROL_DIFFICULTY = {0: 0, 1: 10, 2: 15, 3: 20}

# Fine = this fraction of the job's reward
FINE_FRACTION = 0.50

# ── Multi-planet route tiers (Drop 11) ────────────────────────────────────────
# destination_planet=None means local Tatooine run (original behaviour).
# Routes are assigned per tier:
#   Tier 1 (local)     — Tatooine only, same as before
#   Tier 2 (short)     — Tatooine → Nar Shaddaa
#   Tier 3 (spice run) — Nar Shaddaa → Kessel  (or Tatooine → Kessel)
#   Tier 4 (core run)  — Any outer rim → Corellia

ROUTE_TIERS = {
    # (cargo_tier, destination_planet, pay_override, patrol_chance_override)
    # destination_planet=None  → local run, planet check skipped on deliver
    "local":     (CargoTier.GREY_MARKET,  None,         (200,  500),  0.00),
    "blackmkt":  (CargoTier.BLACK_MARKET, None,         (500,  1500), 0.20),
    "interplan": (CargoTier.BLACK_MARKET, "nar_shaddaa",(1500, 3000), 0.30),
    "spicerun":  (CargoTier.CONTRABAND,   "kessel",     (3000, 6000), 0.55),
    "corerun":   (CargoTier.SPICE,        "corellia",   (4000, 8000), 0.65),
}

# How often Imperial patrols intercept at arrival by planet
# (extra check on hyperspace arrival; stacks with launch check)
PLANET_PATROL_FREQUENCY = {
    None:          0.00,   # local — no arrival check
    "tatooine":    0.10,   # Outer Rim — light presence
    "nar_shaddaa": 0.15,   # Hutt space — occasional
    "kessel":      0.40,   # Maw vicinity — heavy
    "corellia":    0.60,   # Core World — very heavy
}

# Dock zone suffixes per planet (orbit / dock zone IDs for arrive check)
PLANET_DOCK_ZONES = {
    "tatooine":    ["tatooine_dock",      "tatooine_orbit"],
    "nar_shaddaa": ["nar_shaddaa_dock",   "nar_shaddaa_orbit"],
    "kessel":      ["kessel_dock",        "kessel_orbit"],
    "corellia":    ["corellia_dock",      "corellia_orbit"],
}'''

# ── SmugglingJob dataclass: add destination_planet field ─────────────────────

SMUG_OLD_DATACLASS = '''@dataclass
class SmugglingJob:
    id: str
    tier: CargoTier
    cargo_type: str
    contact_name: str
    dropoff_name: str
    reward: int
    fine: int             # Credits forfeited if caught
    patrol_chance: float  # 0.0 - 1.0
    status: JobStatus = JobStatus.AVAILABLE
    accepted_by: Optional[int] = None   # character id
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "cargo_type": self.cargo_type,
            "contact_name": self.contact_name,
            "dropoff_name": self.dropoff_name,
            "reward": self.reward,
            "fine": self.fine,
            "patrol_chance": self.patrol_chance,
            "status": self.status.value,
            "accepted_by": self.accepted_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SmugglingJob":
        return cls(
            id=d["id"],
            tier=CargoTier(d["tier"]),
            cargo_type=d["cargo_type"],
            contact_name=d["contact_name"],
            dropoff_name=d["dropoff_name"],
            reward=d["reward"],
            fine=d["fine"],
            patrol_chance=d["patrol_chance"],
            status=JobStatus(d.get("status", "available")),
            accepted_by=d.get("accepted_by"),
            created_at=d.get("created_at", time.time()),
            expires_at=d.get("expires_at"),
        )'''

SMUG_NEW_DATACLASS = '''@dataclass
class SmugglingJob:
    id: str
    tier: CargoTier
    cargo_type: str
    contact_name: str
    dropoff_name: str
    reward: int
    fine: int             # Credits forfeited if caught
    patrol_chance: float  # 0.0 - 1.0
    status: JobStatus = JobStatus.AVAILABLE
    accepted_by: Optional[int] = None   # character id
    destination_planet: Optional[str] = None   # None = local Tatooine run
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "cargo_type": self.cargo_type,
            "contact_name": self.contact_name,
            "dropoff_name": self.dropoff_name,
            "reward": self.reward,
            "fine": self.fine,
            "patrol_chance": self.patrol_chance,
            "status": self.status.value,
            "accepted_by": self.accepted_by,
            "destination_planet": self.destination_planet,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SmugglingJob":
        return cls(
            id=d["id"],
            tier=CargoTier(d["tier"]),
            cargo_type=d["cargo_type"],
            contact_name=d["contact_name"],
            dropoff_name=d["dropoff_name"],
            reward=d["reward"],
            fine=d["fine"],
            patrol_chance=d["patrol_chance"],
            status=JobStatus(d.get("status", "available")),
            accepted_by=d.get("accepted_by"),
            destination_planet=d.get("destination_planet"),
            created_at=d.get("created_at", time.time()),
            expires_at=d.get("expires_at"),
        )'''

# ── generate_job(): expand to multi-planet routes ─────────────────────────────

SMUG_OLD_GENERATE = '''def generate_job(tier: Optional[CargoTier] = None) -> SmugglingJob:
    """Generate a single smuggling job."""
    if tier is None:
        # Weight toward lower tiers: 4/3/2/1
        tier = random.choices(
            list(CargoTier),
            weights=[4, 3, 2, 1],
            k=1,
        )[0]

    lo, hi = TIER_PAY_RANGE[tier]
    reward = random.randint(lo, hi)
    # Round to nearest 50cr
    reward = int(round(reward / 50) * 50)
    fine = int(reward * FINE_FRACTION)

    cargo = random.choice(CARGO_TYPES[tier])
    contact = random.choice(CONTACT_NAMES)
    dropoff = random.choice(DROPOFF_NAMES)
    patrol = TIER_PATROL_CHANCE[tier]

    now = time.time()
    return SmugglingJob(
        id=_generate_id(),
        tier=tier,
        cargo_type=cargo,
        contact_name=contact,
        dropoff_name=dropoff,
        reward=reward,
        fine=fine,
        patrol_chance=patrol,
        created_at=now,
        expires_at=now + JOB_TTL,
    )'''

SMUG_NEW_GENERATE = '''def generate_job(
    tier: Optional[CargoTier] = None,
    route_key: Optional[str] = None,
) -> SmugglingJob:
    """Generate a single smuggling job.

    route_key selects from ROUTE_TIERS (e.g. 'spicerun', 'corerun').
    If None, falls back to weighted random including multi-planet routes.
    """
    destination_planet: Optional[str] = None

    if route_key and route_key in ROUTE_TIERS:
        tier, destination_planet, pay_range, patrol = ROUTE_TIERS[route_key]
        lo, hi = pay_range
    elif tier is not None:
        lo, hi = TIER_PAY_RANGE[tier]
        patrol = TIER_PATROL_CHANCE[tier]
    else:
        # Weighted random: 40% local, 25% black market, 20% interplanetary,
        # 10% spice run, 5% core run
        route_key = random.choices(
            list(ROUTE_TIERS.keys()),
            weights=[40, 25, 20, 10, 5],
            k=1,
        )[0]
        tier, destination_planet, pay_range, patrol = ROUTE_TIERS[route_key]
        lo, hi = pay_range

    reward = random.randint(lo, hi)
    # Round to nearest 50cr
    reward = int(round(reward / 50) * 50)
    fine = int(reward * FINE_FRACTION)

    cargo = random.choice(CARGO_TYPES[tier])
    contact = random.choice(CONTACT_NAMES)

    # Dropoff description varies by destination
    if destination_planet == "nar_shaddaa":
        dropoff = random.choice([
            "a Hutt factor in Nar Shaddaa's Lower Promenade",
            "a Rodian broker at the Smuggler's Moon docks",
            "a Besadii clan representative",
        ])
    elif destination_planet == "kessel":
        dropoff = random.choice([
            "a Pyke Syndicate collector at Kessel Station",
            "an independent spice processor at the Maw approach",
            "a masked buyer near the Kessel mining complex",
        ])
    elif destination_planet == "corellia":
        dropoff = random.choice([
            "a CorSec-connected fence in Coronet City",
            "a corporate buyer at the Corellian Trade Spine exit",
            "a well-dressed human contact at Corellia Orbital",
        ])
    else:
        dropoff = random.choice(DROPOFF_NAMES)

    now = time.time()
    return SmugglingJob(
        id=_generate_id(),
        tier=tier,
        cargo_type=cargo,
        contact_name=contact,
        dropoff_name=dropoff,
        reward=reward,
        fine=fine,
        patrol_chance=patrol,
        destination_planet=destination_planet,
        created_at=now,
        expires_at=now + JOB_TTL,
    )'''

# ── format_board(): show destination column ───────────────────────────────────

SMUG_OLD_FORMAT_BOARD = '''def format_board(jobs: list[SmugglingJob]) -> list[str]:
    lines = [
        f"{_BOLD}{\'=\' * 58}{_RESET}",
        f"{_BOLD}  SMUGGLING CONTACTS  --  Mos Eisley Underground{_RESET}",
        f"{_DIM}  {\'ID\':<10} {\'Tier\':<14} {\'Reward\':>8}  {\'Risk\':<14}  Cargo{_RESET}",
        f"{_DIM}  {\'-\' * 56}{_RESET}",
    ]
    if not jobs:
        lines.append("  No contacts available. Come back later.")
    else:
        for j in jobs:
            color = _TIER_COLOR.get(j.tier, "")
            tier_label = TIER_NAMES[j.tier]
            risk = _RISK_DISPLAY.get(j.tier, "Unknown")
            lines.append(
                f"  {_BOLD}{j.id:<10}{_RESET} "
                f"{color}{tier_label:<14}{_RESET} "
                f"{_BOLD}{j.reward:>7,}cr{_RESET}  "
                f"{risk:<22}  {j.cargo_type}"
            )
    lines.append(
        f"{_DIM}  Type \'smugaccept <id>\' to take the job. "
        f"\'smugjob\' to see your active run.{_RESET}"
    )
    lines.append(f"{_BOLD}{\'=\' * 58}{_RESET}")
    return lines'''

SMUG_NEW_FORMAT_BOARD = '''_DEST_DISPLAY = {
    None:          f"{_DIM}Tatooine (local){_RESET}",
    "nar_shaddaa": f"{_YELLOW}Nar Shaddaa{_RESET}",
    "kessel":      f"{_RED}Kessel{_RESET}",
    "corellia":    f"\033[1;35mCorellia{_RESET}",
}


def format_board(jobs: list[SmugglingJob]) -> list[str]:
    lines = [
        f"{_BOLD}{\'=\' * 66}{_RESET}",
        f"{_BOLD}  SMUGGLING CONTACTS  --  Mos Eisley Underground{_RESET}",
        f"{_DIM}  {\'ID\':<10} {\'Tier\':<14} {\'Reward\':>8}  {\'Destination\':<16}  Cargo{_RESET}",
        f"{_DIM}  {\'-\' * 64}{_RESET}",
    ]
    if not jobs:
        lines.append("  No contacts available. Come back later.")
    else:
        for j in jobs:
            color = _TIER_COLOR.get(j.tier, "")
            tier_label = TIER_NAMES[j.tier]
            dest = _DEST_DISPLAY.get(j.destination_planet, j.destination_planet or "Local")
            lines.append(
                f"  {_BOLD}{j.id:<10}{_RESET} "
                f"{color}{tier_label:<14}{_RESET} "
                f"{_BOLD}{j.reward:>7,}cr{_RESET}  "
                f"{dest:<26}  {j.cargo_type}"
            )
    lines.append(
        f"{_DIM}  Type \'smugaccept <id>\' to take the job. "
        f"\'smugjob\' to see your active run.{_RESET}"
    )
    lines.append(f"{_BOLD}{\'=\' * 66}{_RESET}")
    return lines'''

# ── format_job_detail(): show destination planet ──────────────────────────────

SMUG_OLD_FORMAT_DETAIL = '''        f"  {_BOLD}Deliver to:{_RESET} {j.dropoff_name}",
        f"  {_BOLD}Risk:{_RESET}     {_RISK_DISPLAY.get(j.tier, \'Unknown\')}",'''

SMUG_NEW_FORMAT_DETAIL = '''        f"  {_BOLD}Deliver to:{_RESET} {j.dropoff_name}",
        f"  {_BOLD}Destination:{_RESET} "
        + (_DEST_DISPLAY.get(j.destination_planet, j.destination_planet or "Local")),
        f"  {_BOLD}Risk:{_RESET}     {_RISK_DISPLAY.get(j.tier, \'Unknown\')}",'''


# ══════════════════════════════════════════════════════════════════════════════
# Patch 2 — parser/smuggling_commands.py
# ══════════════════════════════════════════════════════════════════════════════

# A) SmugDeliverCommand: add planet check after docked_at check
CMD_OLD_DELIVER = '''        # Run the patrol check (retroactively on delivery for ground-only runs)
        # For simplicity: patrol check happens here for non-space runs
        # (space runs get checked in the launch hook — Drop 2 patch)
        # If they made it to delivery without a space run, they're clean.
        completed = await board.complete(char_id, ctx.db)'''

CMD_NEW_DELIVER = '''        # ── Destination planet check (Drop 11) ─────────────────────────────
        if job.destination_planet:
            # Verify ship is in the correct planet's zone
            import json as _smj
            _ship_sys = _smj.loads(ship.get("systems") or "{}")
            _current_zone = _ship_sys.get("current_zone", "")
            from engine.smuggling import PLANET_DOCK_ZONES
            _valid_zones = PLANET_DOCK_ZONES.get(job.destination_planet, [])
            if not _current_zone or not any(
                _current_zone.startswith(z) or z.startswith(_current_zone)
                for z in _valid_zones
            ):
                _planet_name = job.destination_planet.replace("_", " ").title()
                await ctx.session.send_line(
                    f"  This cargo is bound for {_planet_name}. "
                    f"You need to be docked there to make the delivery."
                )
                return

        # Run the patrol check (retroactively on delivery for ground-only runs)
        # For simplicity: patrol check happens here for non-space runs
        # (space runs get checked in the launch hook — Drop 2 patch)
        # If they made it to delivery without a space run, they're clean.
        completed = await board.complete(char_id, ctx.db)'''

# B) Add check_patrol_on_arrival() after check_patrol_on_launch()
CMD_OLD_ARRIVAL_ANCHOR = '''async def _get_player_ship(ctx: CommandContext):
    """Get the ship the player is currently aboard, or None."""'''

CMD_NEW_ARRIVAL_ANCHOR = '''async def check_patrol_on_arrival(ctx: CommandContext, dest_planet: str) -> bool:
    """
    Check for an Imperial patrol encounter on hyperspace arrival.
    Call this from the hyperspace arrival tick in game_server.py.

    dest_planet: e.g. "corellia", "kessel", "nar_shaddaa", "tatooine"
    Returns True if the player was caught (cargo confiscated, fine applied).

    Only triggers if the character has an active smuggling run with a
    matching destination_planet. Gracefully no-ops if no run active.
    """
    char_id = ctx.session.character["id"]

    from engine.smuggling import (
        get_smuggling_board, resolve_patrol_encounter,
        PLANET_PATROL_FREQUENCY,
    )
    board = get_smuggling_board()
    job = board.get_active_job(char_id)
    if not job:
        return False
    if job.destination_planet != dest_planet:
        return False  # Different destination — not their stop

    # Roll whether patrol intercepts at this planet
    arrival_chance = PLANET_PATROL_FREQUENCY.get(dest_planet, 0.0)
    import random as _arr_r
    if _arr_r.random() > arrival_chance:
        return False

    # Reuse launch patrol logic (same skill check, same outcome)
    lockdown_active = False
    try:
        from engine.director import get_director, AlertLevel
        lockdown_active = (
            get_director().get_alert_level("spaceport") == AlertLevel.LOCKDOWN
        )
    except Exception:
        pass

    char = ctx.session.character
    from engine.character import Character, SkillRegistry
    from engine.dice import roll_d6_pool
    skill_reg = SkillRegistry()
    skill_reg.load_default()
    try:
        from engine.character import Character as Char
        c = Char.from_dict(char)
        con_pool   = c.get_skill_pool("con", skill_reg)
        sneak_pool = c.get_skill_pool("sneak", skill_reg)
        pool = con_pool if con_pool.total_pips() >= sneak_pool.total_pips() else sneak_pool
        roll_result = roll_d6_pool(pool)
        roll_total = roll_result.total
        skill_name = "Con" if con_pool.total_pips() >= sneak_pool.total_pips() else "Sneak"
    except Exception:
        import random as _r
        roll_total = sum(_r.randint(1, 6) for _ in range(2))
        skill_name = "Con"

    outcome = resolve_patrol_encounter(job, roll_total, lockdown_active)

    if not outcome["intercepted"]:
        return False

    planet_name = dest_planet.replace("_", " ").title()
    _CUSTOMS_BOLD_RED = "\033[1;31m"
    _CUSTOMS_RESET    = "\033[0m"
    _customs_msg = _CUSTOMS_BOLD_RED + "[CUSTOMS]" + _CUSTOMS_RESET + " Imperial customs intercepts your ship on arrival at " + planet_name + "!"
    await ctx.session.send_line("  " + _customs_msg)
    await ctx.session.send_line(f"  {outcome['message']}")

    if outcome["caught"]:
        fine = job.fine
        credits = char.get("credits", 0)
        new_credits = max(0, credits - fine)
        char["credits"] = new_credits
        await ctx.db.save_character(char_id, credits=new_credits)
        await board.fail(char_id, ctx.db)
        await ctx.session.send_line(
            f"  Fine deducted: {fine:,} credits. Balance: {new_credits:,} credits."
        )
        return True
    else:
        await ctx.session.send_line(
            f"  ({skill_name} roll: {roll_total} vs difficulty {outcome['difficulty']} — cleared)"
        )
        return False


async def _get_player_ship(ctx: CommandContext):
    """Get the ship the player is currently aboard, or None."""'''


# ══════════════════════════════════════════════════════════════════════════════
# Patch 3 — server/game_server.py
# ══════════════════════════════════════════════════════════════════════════════
# Insert patrol-on-arrival call right after Space HUD update at hyperspace arrival

GS_OLD_ARRIVAL = '''                        # Space HUD update for all crew on arrival
                        try:
                            from parser.space_commands import broadcast_space_state
                            _hs_fresh = await self.db.get_ship_by_bridge(_hs_ship["bridge_room_id"])
                            if _hs_fresh:
                                await broadcast_space_state(_hs_fresh, self.db, self.session_mgr)
                        except Exception:
                            pass'''

GS_NEW_ARRIVAL = '''                        # Space HUD update for all crew on arrival
                        try:
                            from parser.space_commands import broadcast_space_state
                            _hs_fresh = await self.db.get_ship_by_bridge(_hs_ship["bridge_room_id"])
                            if _hs_fresh:
                                await broadcast_space_state(_hs_fresh, self.db, self.session_mgr)
                        except Exception:
                            pass
                        # Patrol-on-arrival check for smuggling runs (Drop 11)
                        try:
                            from parser.smuggling_commands import check_patrol_on_arrival
                            from parser.commands import CommandContext
                            _arr_sessions = self.session_mgr.sessions_in_room(
                                _hs_ship["bridge_room_id"]
                            )
                            for _arr_sess in (_arr_sessions or []):
                                if not _arr_sess.character:
                                    continue
                                _arr_ctx = CommandContext(
                                    session=_arr_sess,
                                    db=self.db,
                                    session_mgr=self.session_mgr,
                                    args="",
                                )
                                await check_patrol_on_arrival(_arr_ctx, _dest_key)
                        except Exception:
                            pass'''


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n=== Drop 11 — Multi-Planet Smuggling Routes ===\n")

    if DRY_RUN:
        print("DRY RUN — no files will be modified.\n")

    # ── Patch 1a: smuggling.py constants ──────────────────────────────────────
    print("engine/smuggling.py:")
    path = FILES["smuggling"]
    apply_patch(path, SMUG_OLD_CONSTANTS,     SMUG_NEW_CONSTANTS,     "route tiers + patrol frequency tables")
    apply_patch(path, SMUG_OLD_DATACLASS,     SMUG_NEW_DATACLASS,     "destination_planet field on SmugglingJob")
    apply_patch(path, SMUG_OLD_GENERATE,      SMUG_NEW_GENERATE,      "multi-planet generate_job()")
    apply_patch(path, SMUG_OLD_FORMAT_BOARD,  SMUG_NEW_FORMAT_BOARD,  "format_board() destination column")
    apply_patch(path, SMUG_OLD_FORMAT_DETAIL, SMUG_NEW_FORMAT_DETAIL, "format_job_detail() destination line")

    # ── Patch 2: smuggling_commands.py ────────────────────────────────────────
    print("\nparser/smuggling_commands.py:")
    path = FILES["smuggling_commands"]
    apply_patch(path, CMD_OLD_DELIVER,        CMD_NEW_DELIVER,        "SmugDeliverCommand planet check")
    apply_patch(path, CMD_OLD_ARRIVAL_ANCHOR, CMD_NEW_ARRIVAL_ANCHOR, "check_patrol_on_arrival() function")

    # ── Patch 3: game_server.py ────────────────────────────────────────────────
    print("\nserver/game_server.py:")
    path = FILES["game_server"]
    apply_patch(path, GS_OLD_ARRIVAL, GS_NEW_ARRIVAL, "patrol-on-arrival call at hyperspace arrival")

    print("\n=== Drop 11 patch complete ===")
    if DRY_RUN:
        print("(dry run — rerun without --dry-run to apply)")
    else:
        print("Backups written as *.bak_drop11")


if __name__ == "__main__":
    main()
