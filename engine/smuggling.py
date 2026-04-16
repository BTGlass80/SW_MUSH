# -*- coding: utf-8 -*-
"""
engine/smuggling.py  --  Smuggling Job Board Engine
SW_MUSH  |  Economy Phase 2

Implements the contraband cargo run system. Distinct from the general
mission board -- smuggling jobs are available from specific in-world
contacts (Jabba's, docking bay fixers) and carry risk of Imperial
interception during space transit.

Design from economy_design_v02-1.md §3.1:
  Tier | Cargo          | Pay          | Patrol Risk
  ---- | -------------- | ------------ | -----------
  0    | Medical (grey) | 200-500 cr   | 0%  (legal grey area)
  1    | Weapons parts  | 500-1,500 cr | 20%
  2    | Glitterstim    | 1,500-5,000  | 50%
  3    | Raw spice      | 5,000-15,000 | 80%

Patrol encounter:
  - Rolls on Con or Sneak (player's choice) vs difficulty
  - Tier 0: no check
  - Tier 1: difficulty 10
  - Tier 2: difficulty 15
  - Tier 3: difficulty 20
  On failure: cargo confiscated, fine = 50% of reward
  On success: deliver to dropoff room for full reward

Director integration:
  - LOCKDOWN alert adds +1 tier of patrol risk (tier 0 becomes tier 1 risk etc.)
  - Smuggling completion records to director digest

Board:
  - 3–5 jobs, refreshes every 45 minutes
  - Picked up in specific rooms (Jabba's Palace area, Docking Bay contacts)
  - One active smuggling job per character at a time
  - TTL: 2h unclaimed, 4h active
"""

import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

BOARD_SIZE        = 5     # Max jobs on the board at once
BOARD_MIN         = 3     # Minimum jobs to maintain
REFRESH_SECONDS   = 2700  # 45 minutes
JOB_TTL           = 7200  # 2h unclaimed
JOB_ACTIVE_TTL    = 14400 # 4h accepted

# Patrol encounter base difficulty by tier
PATROL_DIFFICULTY = {0: 0, 1: 10, 2: 15, 3: 20}

# Fine = this fraction of the job's reward
FINE_FRACTION = 0.50

# ── Cargo tiers ──────────────────────────────────────────────────────────────

class CargoTier(int, Enum):
    GREY_MARKET = 0   # Technically legal, just irregular
    BLACK_MARKET = 1  # Weapons parts, stolen goods
    CONTRABAND   = 2  # Glitterstim, controlled substances
    SPICE        = 3  # Raw spice — maximum Imperial interest

TIER_NAMES = {
    CargoTier.GREY_MARKET: "Grey Market",
    CargoTier.BLACK_MARKET: "Black Market",
    CargoTier.CONTRABAND:   "Contraband",
    CargoTier.SPICE:        "Spice Run",
}

TIER_PATROL_CHANCE = {
    CargoTier.GREY_MARKET: 0.00,
    CargoTier.BLACK_MARKET: 0.20,
    CargoTier.CONTRABAND:   0.50,
    CargoTier.SPICE:        0.80,
}

TIER_PAY_RANGE = {
    CargoTier.GREY_MARKET: (200, 500),
    CargoTier.BLACK_MARKET: (500, 1500),
    CargoTier.CONTRABAND:   (1500, 5000),
    CargoTier.SPICE:        (5000, 15000),
}

CARGO_TYPES = {
    CargoTier.GREY_MARKET: [
        "medical supplies", "unlicensed foodstuffs", "uncertified droids",
        "untaxed power cells", "surplus military rations",
    ],
    CargoTier.BLACK_MARKET: [
        "weapons components", "stolen ship parts", "black market implants",
        "untraceable credits", "classified Imperial schematics",
    ],
    CargoTier.CONTRABAND: [
        "glitterstim", "ryll spice", "contraband holorecordings",
        "illegal weapons modifications", "Hutt-processed stimulants",
    ],
    CargoTier.SPICE: [
        "raw Kessel spice", "unrefined glitterstim", "bulk ryll",
        "processed andris", "syndicate-grade spice",
    ],
}

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
}

CONTACT_NAMES = [
    "a hooded Twi'lek", "a scarred Weequay", "a nervous Rodian fence",
    "a Hutt agent", "a gruff Devaronian", "an Aqualish middleman",
    "a one-eyed human fixer", "a Sullustan broker",
]

DROPOFF_NAMES = [
    "a contact in the Industrial District",
    "a Hutt warehouse representative",
    "an off-world fence at Docking Bay 94",
    "a nervous merchant in the Market District",
    "a cloaked figure near the Outskirts",
    "a Bothan information broker",
]

# ── Job status ────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    AVAILABLE = "available"
    ACCEPTED  = "accepted"
    COMPLETE  = "complete"
    FAILED    = "failed"
    EXPIRED   = "expired"

# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
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
        )


# ── Generator ────────────────────────────────────────────────────────────────

def _generate_id() -> str:
    return "smug-" + str(uuid.uuid4())[:6]


def generate_job(
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
    )


def generate_board() -> list[SmugglingJob]:
    """Generate a full board of smuggling jobs."""
    count = random.randint(BOARD_MIN, BOARD_SIZE)
    jobs = []
    # Always include at least one tier-0 (accessible entry point)
    jobs.append(generate_job(CargoTier.GREY_MARKET))
    while len(jobs) < count:
        jobs.append(generate_job())
    return jobs


# ── Patrol encounter resolution ───────────────────────────────────────────────

def resolve_patrol_encounter(
    job: SmugglingJob,
    skill_roll: int,
    lockdown_active: bool = False,
) -> dict:
    """
    Resolve an Imperial patrol encounter during transit.

    Args:
        job: The active smuggling job.
        skill_roll: Player's Con or Sneak roll result.
        lockdown_active: True if spaceport zone is at LOCKDOWN alert.

    Returns:
        dict with keys:
            "intercepted": bool — True if patrol stops the player
            "caught": bool — True if the skill check failed
            "difficulty": int — The difficulty rolled against
            "message": str — Narrative text to display
    """
    # Determine effective patrol chance
    patrol_chance = job.patrol_chance
    if lockdown_active and patrol_chance < 1.0:
        # Lockdown: shift up one tier's worth of patrol risk
        patrol_chance = min(1.0, patrol_chance + 0.30)

    # Roll whether patrol intercepts at all
    if random.random() > patrol_chance:
        return {
            "intercepted": False,
            "caught": False,
            "difficulty": 0,
            "message": "",
        }

    # Patrol intercepts — now roll to talk your way through
    difficulty = PATROL_DIFFICULTY[job.tier]
    if lockdown_active:
        difficulty += 5  # Lockdown raises inspection difficulty

    caught = skill_roll < difficulty

    if not caught:
        msg = (
            f"  An Imperial patrol hails you. Your story holds — they wave you through.\n"
            f"  (Roll: {skill_roll} vs difficulty {difficulty})"
        )
    else:
        msg = (
            f"  An Imperial patrol intercepts you. They find the {job.cargo_type}.\n"
            f"  Cargo confiscated. Fine: {job.fine:,} credits.\n"
            f"  (Roll: {skill_roll} vs difficulty {difficulty})"
        )

    return {
        "intercepted": True,
        "caught": caught,
        "difficulty": difficulty,
        "message": msg,
    }


# ── Board manager ─────────────────────────────────────────────────────────────

class SmugglingBoard:
    """
    Singleton-style smuggling job board.

    Jobs are available from specific in-world locations.
    Backed by the smuggling_jobs DB table.
    One active job per character at a time.
    """

    def __init__(self):
        self._jobs: dict[str, SmugglingJob] = {}  # id -> job
        self._last_refresh: float = 0.0
        self._loaded: bool = False

    async def ensure_loaded(self, db) -> None:
        if not self._loaded:
            await self._load_from_db(db)
            self._loaded = True
        if time.time() - self._last_refresh > REFRESH_SECONDS:
            await self.refresh(db)

    async def _load_from_db(self, db) -> None:
        try:
            rows = await db.fetchall(
                "SELECT data FROM smuggling_jobs WHERE status IN ('available','accepted')"
            )
            for row in rows:
                d = json.loads(row[0])
                job = SmugglingJob.from_dict(d)
                self._jobs[job.id] = job
            log.info("[smuggling] Loaded %d jobs from DB", len(self._jobs))
        except Exception as e:
            log.warning("[smuggling] Failed to load from DB: %s", e)

    async def refresh(self, db) -> None:
        """Prune expired jobs and top up to BOARD_SIZE."""
        now = time.time()

        # Expire old available jobs
        to_expire = [
            jid for jid, j in self._jobs.items()
            if j.status == JobStatus.AVAILABLE and j.expires_at and j.expires_at < now
        ]
        for jid in to_expire:
            self._jobs[jid].status = JobStatus.EXPIRED
            await self._save_job(db, self._jobs[jid])
            del self._jobs[jid]

        # Count available slots
        available = [j for j in self._jobs.values() if j.status == JobStatus.AVAILABLE]
        needed = max(0, BOARD_MIN - len(available))

        for _ in range(needed):
            job = generate_job()
            self._jobs[job.id] = job
            await self._save_job(db, job)

        self._last_refresh = now
        log.debug("[smuggling] Board refreshed: %d available", len(available) + needed)

    async def _save_job(self, db, job: SmugglingJob) -> None:
        try:
            await db.execute(
                """INSERT OR REPLACE INTO smuggling_jobs
                   (id, status, accepted_by, data)
                   VALUES (?, ?, ?, ?)""",
                (job.id, job.status.value, job.accepted_by, json.dumps(job.to_dict()))
            )
            await db.commit()
        except Exception as e:
            log.warning("[smuggling] Failed to save job %s: %s", job.id, e)

    def available_jobs(self) -> list[SmugglingJob]:
        now = time.time()
        return [
            j for j in self._jobs.values()
            if j.status == JobStatus.AVAILABLE
            and (not j.expires_at or j.expires_at > now)
        ]

    def get_active_job(self, char_id: int) -> Optional[SmugglingJob]:
        """Get the character's currently accepted job, if any."""
        for j in self._jobs.values():
            if j.status == JobStatus.ACCEPTED and j.accepted_by == char_id:
                return j
        return None

    async def accept(self, job_id: str, char_id: int, db) -> Optional[SmugglingJob]:
        """Accept a job. Returns the job on success, None on failure."""
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.AVAILABLE:
            return None
        if self.get_active_job(char_id):
            return None  # Already have one

        job.status = JobStatus.ACCEPTED
        job.accepted_by = char_id
        job.expires_at = time.time() + JOB_ACTIVE_TTL
        await self._save_job(db, job)
        return job

    async def complete(self, char_id: int, db) -> Optional[SmugglingJob]:
        """Mark the character's active job complete. Returns it."""
        job = self.get_active_job(char_id)
        if not job:
            return None
        job.status = JobStatus.COMPLETE
        await self._save_job(db, job)
        del self._jobs[job.id]

        # Notify Director digest
        try:
            from engine.director import get_director
            get_director().digest.record_mission("smuggling", "spaceport")
        except Exception:
            log.warning("complete: unhandled exception", exc_info=True)
            pass

        return job

    async def fail(self, char_id: int, db, reason: str = "caught") -> Optional[SmugglingJob]:
        """Mark the character's active job failed (caught by patrol)."""
        job = self.get_active_job(char_id)
        if not job:
            return None
        job.status = JobStatus.FAILED
        await self._save_job(db, job)
        del self._jobs[job.id]
        return job

    async def dump_cargo(self, char_id: int, db) -> Optional[SmugglingJob]:
        """Jettison cargo mid-flight. Job abandoned, no fine, no reward."""
        job = self.get_active_job(char_id)
        if not job:
            return None
        job.status = JobStatus.FAILED
        await self._save_job(db, job)
        del self._jobs[job.id]
        return job


# ── Module-level singleton ────────────────────────────────────────────────────

_board: Optional[SmugglingBoard] = None


def get_smuggling_board() -> SmugglingBoard:
    global _board
    if _board is None:
        _board = SmugglingBoard()
    return _board


# ── ANSI display helpers ──────────────────────────────────────────────────────

_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_RED   = "\033[1;31m"
_YELLOW = "\033[1;33m"
_GREEN = "\033[1;32m"
_CYAN  = "\033[0;36m"
_RESET = "\033[0m"

_TIER_COLOR = {
    CargoTier.GREY_MARKET: _DIM,
    CargoTier.BLACK_MARKET: _YELLOW,
    CargoTier.CONTRABAND:   _RED,
    CargoTier.SPICE:        "\033[1;35m",  # bright magenta
}

_RISK_DISPLAY = {
    CargoTier.GREY_MARKET: f"{_GREEN}None{_RESET}",
    CargoTier.BLACK_MARKET: f"{_YELLOW}Low (20%){_RESET}",
    CargoTier.CONTRABAND:   f"{_RED}High (50%){_RESET}",
    CargoTier.SPICE:        f"\033[1;35mExtreme (80%){_RESET}",
}


_DEST_DISPLAY = {
    None:          f"{_DIM}Tatooine (local){_RESET}",
    "nar_shaddaa": f"{_YELLOW}Nar Shaddaa{_RESET}",
    "kessel":      f"{_RED}Kessel{_RESET}",
    "corellia":    f"[1;35mCorellia{_RESET}",
}


def format_board(jobs: list[SmugglingJob]) -> list[str]:
    lines = [
        f"{_BOLD}{'=' * 66}{_RESET}",
        f"{_BOLD}  SMUGGLING CONTACTS  --  Mos Eisley Underground{_RESET}",
        f"{_DIM}  {'ID':<10} {'Tier':<14} {'Reward':>8}  {'Destination':<16}  Cargo{_RESET}",
        f"{_DIM}  {'-' * 64}{_RESET}",
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
        f"{_DIM}  Type 'smugaccept <id>' to take the job. "
        f"'smugjob' to see your active run.{_RESET}"
    )
    lines.append(f"{_BOLD}{'=' * 66}{_RESET}")
    return lines


def format_job_detail(j: SmugglingJob) -> list[str]:
    color = _TIER_COLOR.get(j.tier, "")
    tier_label = TIER_NAMES[j.tier]
    remaining = ""
    if j.expires_at:
        secs = max(0, int(j.expires_at - time.time()))
        h, rem = divmod(secs, 3600)
        mn = rem // 60
        remaining = f"  {_DIM}Time Remaining: {h}h {mn}m{_RESET}"
    lines = [
        f"{_BOLD}{'=' * 58}{_RESET}",
        f"  {_BOLD}ACTIVE SMUGGLING RUN{_RESET}  [{j.id}]",
        f"  {color}{tier_label}{_RESET}  |  Reward: {_BOLD}{j.reward:,} credits{_RESET}",
        f"  Fine if caught: {_RED}{j.fine:,} credits{_RESET}",
        "",
        f"  {_BOLD}Contact:{_RESET}  {j.contact_name}",
        f"  {_BOLD}Cargo:{_RESET}    {j.cargo_type}",
        f"  {_BOLD}Deliver to:{_RESET} {j.dropoff_name}",
        f"  {_BOLD}Destination:{_RESET} "
        + (_DEST_DISPLAY.get(j.destination_planet, j.destination_planet or "Local")),
        f"  {_BOLD}Risk:{_RESET}     {_RISK_DISPLAY.get(j.tier, 'Unknown')}",
        remaining,
        "",
        f"  {_DIM}Launch your ship and make the run. Type 'smugdeliver' when docked{_RESET}",
        f"  {_DIM}at the destination. 'smugdump' jettisons the cargo (no fine, no pay).{_RESET}",
        f"{_BOLD}{'=' * 58}{_RESET}",
    ]
    return [l for l in lines if l is not None]
