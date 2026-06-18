# -*- coding: utf-8 -*-
"""
engine/bounty_board.py  --  Bounty Board Engine
SW_MUSH  |  Economy Phase 2

The Bounty Board is distinct from the Mission Board:
  - Targets are procedurally generated NPCs actually spawned in the world
  - Completion requires finding and defeating the target (combat kill/incap)
  - Investigation phase: track the target across rooms before engaging
  - Rewards scale with target tier per economy_design_v02-1.md §3.2

Bounty lifecycle:
  POSTED -> CLAIMED (accepted by a hunter) -> COLLECTED / EXPIRED / FAILED

Pay ranges by tier (from design doc):
  extra:    100–300 cr
  average:  300–800 cr
  novice:   800–1,500 cr
  veteran:  1,500–3,000 cr
  superior: 3,000–10,000 cr

The board holds 3–5 contracts at any time. Board refreshes every 45 minutes.
Individual bounties expire 3 hours after posting if unclaimed, or 4 hours
after being claimed if the target isn't defeated.

Target archetypes that make sense as fugitives:
  thug, smuggler, bounty_hunter, scout, stormtrooper, imperial_officer

Investigation: the `+bounty/track` command uses Search/Streetwise/Tracking to
reveal the target's current room without direct combat commitment.
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.tunables import get_tunable

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

BOARD_SIZE       = 4     # Target board size
BOARD_MIN        = 2
REFRESH_SECONDS  = 2700  # 45 minutes
BOUNTY_TTL       = 10800 # 3 hours unclaimed
CLAIMED_TTL      = 14400 # 4 hours after claim

# ── Tier definitions ───────────────────────────────────────────────────────────

class BountyTier(str, Enum):
    EXTRA    = "extra"
    AVERAGE  = "average"
    NOVICE   = "novice"
    VETERAN  = "veteran"
    SUPERIOR = "superior"


PAY_RANGES: dict[BountyTier, tuple[int, int]] = {
    BountyTier.EXTRA:    (100,   300),
    BountyTier.AVERAGE:  (300,   800),
    BountyTier.NOVICE:   (800,  1500),
    BountyTier.VETERAN:  (1500, 3000),
    BountyTier.SUPERIOR: (3000, 10000),
}

# Spawn weight: extras are common, superiors are rare
TIER_WEIGHTS: dict[BountyTier, int] = {
    BountyTier.EXTRA:    5,
    BountyTier.AVERAGE:  4,
    BountyTier.NOVICE:   3,
    BountyTier.VETERAN:  2,
    BountyTier.SUPERIOR: 1,
}

# Archetypes appropriate as fugitives
# B.1.g (Apr 29 2026): extended with CW archetype keys so CW boots
# generate era-appropriate fugitives (deserter clones, ARC defectors,
# rogue Jedi). Era selection happens at NPC-spawn time via the npc
# generator; this list is the union of allowed archetypes across both
# eras. The Director / spawn callers can filter by era if needed.
FUGITIVE_ARCHETYPES = [
    # ── GCW / era-agnostic ──
    "thug", "smuggler", "bounty_hunter", "scout",
    "stormtrooper", "imperial_officer",
    # ── CW (B.1.g) ──
    "clone_trooper", "arc_trooper", "republic_officer",
]

# Rooms to avoid placing fugitives (docking bays are too obvious/common)
_AVOID_ROOM_KEYWORDS = ["docking bay", "landing pad", "bay 94", "bay 86",
                         "bay 87", "bay 92"]


class BountyStatus(str, Enum):
    POSTED    = "posted"
    CLAIMED   = "claimed"    # Hunter accepted it
    COLLECTED = "collected"  # Target killed/incapacitated, reward paid
    EXPIRED   = "expired"
    FAILED    = "failed"     # Claimed but hunter didn't finish in time


# ── Flavor tables ──────────────────────────────────────────────────────────────

_CRIME_DESCRIPTIONS = [
    "wanted for armed robbery and assault on Imperial personnel",
    "suspected spice smuggler with three outstanding warrants",
    "wanted for murder — last seen armed and dangerous",
    "debt defaulter wanted by the Hutt Cartel — bring in alive if possible",
    "wanted for slicing into Imperial records and selling secrets",
    "accused of stealing a cargo shipment and assaulting the owner",
    "armed fugitive wanted for multiple counts of fraud and extortion",
    "wanted for impersonating an Imperial officer",
    "wanted for destruction of property and resisting arrest",
    "known associate of Rebel insurgents — capture preferred",
]

_POSTING_ORGS = [
    "Imperial Garrison, Mos Eisley",
    "Hutt Cartel (Jabba's Organization)",
    "Bounty Hunters' Guild — Tatooine Charter",
    "Mos Eisley Port Authority",
    "Anonymous Sponsor (credentials verified)",
    "Interstellar Collections Agency",
]

# B.1.g (Apr 29 2026) — CW-era flavor pools. Selected at posting time
# via `_get_crime_descriptions(era)` / `_get_posting_orgs(era)`. GCW
# pools above remain byte-equivalent.
_CW_CRIME_DESCRIPTIONS = [
    "wanted for armed robbery and assault on Republic personnel",
    "suspected spice smuggler with three outstanding warrants",
    "wanted for murder — last seen armed and dangerous",
    "debt defaulter wanted by the Hutt Cartel — bring in alive if possible",
    "wanted for slicing into Republic military records and selling secrets",
    "accused of stealing a cargo shipment and assaulting the owner",
    "armed fugitive wanted for multiple counts of fraud and extortion",
    "wanted for impersonating a Republic officer",
    "wanted for destruction of property and resisting arrest",
    "known Separatist sympathizer — capture preferred",
]

_CW_POSTING_ORGS = [
    "Republic Garrison, Mos Eisley",
    "Hutt Cartel (Jabba's Organization)",
    "Bounty Hunters' Guild — Tatooine Charter",
    "Mos Eisley Port Authority",
    "Anonymous Sponsor (credentials verified)",
    "Interstellar Collections Agency",
]


def _get_crime_descriptions(era: str | None = None) -> list[str]:
    """Return the era-appropriate crime description pool.

    B.1.g (Apr 29 2026): CW era returns CW-flavored crimes (Republic
    instead of Imperial, Separatist instead of Rebel). Other eras
    (including the GCW default and any unmapped era) return the
    legacy GCW pool, preserving production byte-equivalence.

    Never raises; on any error resolving the era, returns the GCW pool.
    """
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception:
            return _CRIME_DESCRIPTIONS
    if era == "clone_wars":
        return _CW_CRIME_DESCRIPTIONS
    return _CRIME_DESCRIPTIONS


def _get_posting_orgs(era: str | None = None) -> list[str]:
    """Return the era-appropriate posting-org pool. See
    `_get_crime_descriptions` for semantics."""
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception:
            return _POSTING_ORGS
    if era == "clone_wars":
        return _CW_POSTING_ORGS
    return _POSTING_ORGS

_INVESTIGATIVE_TIPS = [
    "Last seen near the cantina district.",
    "Known to frequent the market stalls.",
    "Was spotted near the industrial zone.",
    "Informants place the target in the residential quarter.",
    "Believed to be hiding in the outskirts.",
    "Last confirmed location: the spaceport.",
]


# ── Bounty Contract dataclass ──────────────────────────────────────────────────

@dataclass
class BountyContract:
    id: str
    tier: BountyTier
    target_name: str
    target_species: str
    target_archetype: str
    crime_description: str
    posting_org: str
    tip: str
    reward: int
    reward_alive_bonus: int      # Extra credits for bringing in alive (10–20%)
    target_npc_id: Optional[int] # DB NPC id once spawned
    target_room_id: Optional[int]
    status: BountyStatus = BountyStatus.POSTED
    claimed_by: Optional[str] = None    # character_id
    posted_at: float = field(default_factory=time.time)
    claimed_at: Optional[float] = None
    expires_at: Optional[float] = None
    collected_at: Optional[float] = None
    # F.8.c.2.b₂: Chain-tutorial tag. Set to a chain step's
    # `bounty_id` (e.g. "tutorial_bhg_tarko_vinn") when the contract
    # was authored as part of a tutorial chain. Empty string for
    # ordinary procedurally-generated contracts. The chain_events
    # dispatcher reads this field on board.claim to advance the
    # bounty_hunter tutorial chain.
    chain_bounty_id: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tier": self.tier.value,
            "target_name": self.target_name,
            "target_species": self.target_species,
            "target_archetype": self.target_archetype,
            "crime_description": self.crime_description,
            "posting_org": self.posting_org,
            "tip": self.tip,
            "reward": self.reward,
            "reward_alive_bonus": self.reward_alive_bonus,
            "target_npc_id": self.target_npc_id,
            "target_room_id": self.target_room_id,
            "status": self.status.value,
            "claimed_by": self.claimed_by,
            "posted_at": self.posted_at,
            "claimed_at": self.claimed_at,
            "expires_at": self.expires_at,
            "collected_at": self.collected_at,
            "chain_bounty_id": self.chain_bounty_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BountyContract":
        return cls(
            id=d["id"],
            tier=BountyTier(d["tier"]),
            target_name=d["target_name"],
            target_species=d["target_species"],
            target_archetype=d["target_archetype"],
            crime_description=d["crime_description"],
            posting_org=d["posting_org"],
            tip=d["tip"],
            reward=d["reward"],
            reward_alive_bonus=d.get("reward_alive_bonus", 0),
            target_npc_id=d.get("target_npc_id"),
            target_room_id=d.get("target_room_id"),
            status=BountyStatus(d.get("status", "posted")),
            claimed_by=d.get("claimed_by"),
            posted_at=d.get("posted_at", time.time()),
            claimed_at=d.get("claimed_at"),
            expires_at=d.get("expires_at"),
            collected_at=d.get("collected_at"),
            chain_bounty_id=d.get("chain_bounty_id", ""),
        )


# ── Generation helpers ─────────────────────────────────────────────────────────

def _gen_id() -> str:
    import uuid
    return "b-" + str(uuid.uuid4())[:8]


def _pick_tier() -> BountyTier:
    tiers  = list(TIER_WEIGHTS.keys())
    weights = [TIER_WEIGHTS[t] for t in tiers]
    return random.choices(tiers, weights=weights, k=1)[0]


# Tier order low->high for the krayt-sighting upgrade.
_TIER_ORDER = [
    BountyTier.EXTRA, BountyTier.AVERAGE, BountyTier.NOVICE,
    BountyTier.VETERAN, BountyTier.SUPERIOR,
]


def krayt_upgrade_tier(tier: BountyTier, krayt_active: bool) -> BountyTier:
    """WORLDEVENT.flag_effect_consumers (2026-06-13): KRAYT_SIGHTING /
    `krayt_bounty` consumer. A krayt sighting means a dangerous, high-value
    quarry is loose, so a newly-posted contract during the event is bumped
    one tier toward SUPERIOR (a richer, deadlier hunt). Pure function — the
    flag is read by generate_bounty via
    get_world_event_manager().get_effect('krayt_bounty', False).

    Already-SUPERIOR contracts are unchanged (top of the ladder)."""
    if not krayt_active:
        return tier
    try:
        idx = _TIER_ORDER.index(tier)
    except ValueError:
        return tier
    return _TIER_ORDER[min(idx + 1, len(_TIER_ORDER) - 1)]


def _scale_reward(tier: BountyTier) -> int:
    lo, hi = PAY_RANGES[tier]
    if tier == BountyTier.SUPERIOR:
        # clamp hi >= lo so an out-of-range operator value can't make
        # random.randint raise "empty range" (mission._scale_reward is already
        # min/max-guarded; bounty's randint is not).
        hi = max(lo, get_tunable("bounty.reward_superior_max", hi))
    raw = random.randint(lo, hi)
    # Round to nearest 50cr
    return int(round(raw / 50) * 50)


def _pick_fugitive_room(rooms: list[dict]) -> Optional[dict]:
    """Pick a room that isn't a docking bay or obvious safe zone."""
    candidates = [
        r for r in rooms
        if not any(kw in r.get("name", "").lower() for kw in _AVOID_ROOM_KEYWORDS)
    ]
    if not candidates:
        candidates = rooms
    return random.choice(candidates) if candidates else None


async def generate_bounty(db, rooms: Optional[list[dict]] = None) -> Optional[BountyContract]:
    """
    Generate a BountyContract, spawning the target NPC in the world.

    Returns the contract on success, None if NPC creation fails.
    """
    from engine.npc_generator import generate_npc, list_archetypes
    from engine.npc_combat_ai import DEFAULT_ARCHETYPE_WEAPONS, DEFAULT_ARCHETYPE_BEHAVIOR
    from ai.npc_brain import NPCConfig

    tier = _pick_tier()
    # WORLDEVENT.flag_effect_consumers (2026-06-13): a KRAYT_SIGHTING
    # event ('krayt_bounty' flag) means a dangerous high-value quarry is
    # loose — bump a newly-posted contract one tier toward SUPERIOR.
    # Failure-tolerant: a flag-lookup hiccup leaves the rolled tier as-is.
    krayt_active = False
    try:
        from engine.world_events import get_world_event_manager
        krayt_active = bool(
            get_world_event_manager().get_effect("krayt_bounty", False))
        if krayt_active:
            tier = krayt_upgrade_tier(tier, True)
    except Exception:
        log.warning("[bounty] krayt_bounty flag lookup failed",
                    exc_info=True)
    archetype = random.choice(FUGITIVE_ARCHETYPES)

    # Generate stat block
    try:
        npc_data = generate_npc(tier.value, archetype)
    except Exception as e:
        log.warning("[bounty] NPC generation failed: %s", e)
        return None

    target_name = npc_data["name"]
    target_species = npc_data.get("species", "Human")

    # Pick spawn room
    if not rooms:
        try:
            rooms = await db.list_rooms(limit=100)
        except Exception:
            rooms = []

    spawn_room = _pick_fugitive_room(rooms)
    if not spawn_room:
        log.warning("[bounty] No valid spawn room found")
        return None

    room_id = spawn_room["id"]

    # Build NPC AI config — hostile (will fight if confronted)
    weapon_key = DEFAULT_ARCHETYPE_WEAPONS.get(archetype, "blaster_pistol")
    behavior   = DEFAULT_ARCHETYPE_BEHAVIOR.get(archetype, "aggressive")

    npc_data["weapon"] = weapon_key
    config = NPCConfig(
        personality=f"A desperate fugitive with nothing to lose.",
        fallback_lines=[
            f"{target_name} watches you warily.",
            f"{target_name} edges toward the exit.",
            f"{target_name} says nothing, eyes darting around.",
        ],
    )
    ai_cfg = config.to_dict()
    ai_cfg["hostile"] = True
    ai_cfg["combat_behavior"] = behavior
    ai_cfg["weapon"] = weapon_key
    ai_cfg["is_bounty_target"] = True   # Flag for cleanup on collection

    try:
        npc_id = await db.create_npc(
            name=target_name,
            room_id=room_id,
            species=target_species,
            description=f"A hunted {archetype.replace('_', ' ')} with a price on their head.",
            char_sheet_json=json.dumps(npc_data),
            ai_config_json=json.dumps(ai_cfg),
        )
    except Exception as e:
        log.error("[bounty] Failed to create NPC: %s", e)
        return None

    reward = _scale_reward(tier)
    alive_bonus = int(reward * random.uniform(0.10, 0.20))
    alive_bonus = int(round(alive_bonus / 50) * 50)

    now = time.time()
    contract = BountyContract(
        id=_gen_id(),
        tier=tier,
        target_name=target_name,
        target_species=target_species,
        target_archetype=archetype,
        crime_description=random.choice(_get_crime_descriptions()),
        posting_org=random.choice(_get_posting_orgs()),
        tip=random.choice(_INVESTIGATIVE_TIPS),
        reward=reward,
        reward_alive_bonus=alive_bonus,
        target_npc_id=npc_id,
        target_room_id=room_id,
        posted_at=now,
        expires_at=now + BOUNTY_TTL,
    )

    log.info(
        "[bounty] Generated %s: %s (%s %s) in room %d for %dcr",
        contract.id, target_name, tier.value, archetype, room_id, reward,
    )
    return contract


# ── BountyBoard manager ────────────────────────────────────────────────────────

class BountyBoard:
    """
    Singleton bounty board. DB-backed, in-memory cache.

    Contracts track live NPC targets. When a target is killed,
    combat_commands calls notify_target_killed() to complete the contract.
    """

    def __init__(self):
        self._contracts: dict[str, BountyContract] = {}
        self._last_refresh: float = 0.0
        self._loaded: bool = False

    async def ensure_loaded(self, db, rooms=None) -> None:
        if not self._loaded:
            await self._load_from_db(db)
            self._loaded = True
        if time.time() - self._last_refresh > REFRESH_SECONDS:
            await self.refresh(db, rooms)

    async def _load_from_db(self, db) -> None:
        try:
            rows = await db.get_posted_bounties()
        except Exception as e:
            log.warning("[bounty] DB load failed: %s", e)
            return
        for row in rows:
            try:
                c = BountyContract.from_dict(json.loads(row["data"]))
                self._contracts[c.id] = c
            except Exception as e:
                log.warning("[bounty] Bad contract row: %s", e)
        log.info("[bounty] Loaded %d contracts from DB", len(self._contracts))

    async def refresh(self, db, rooms=None) -> None:
        """Expire old contracts, spawn new ones to fill the board."""
        now = time.time()
        # Expire
        for cid, c in list(self._contracts.items()):
            if c.expires_at and c.expires_at < now:
                c.status = BountyStatus.EXPIRED
                await db.update_bounty(cid, c.to_dict())
                del self._contracts[cid]
                # Clean up orphaned NPC
                if c.target_npc_id:
                    try:
                        await db.delete_npc(c.target_npc_id)
                    except Exception:
                        log.warning("refresh: unhandled exception", exc_info=True)
                        pass

        # Fill
        needed = BOARD_SIZE - len(self._contracts)
        for _ in range(needed):
            try:
                contract = await generate_bounty(db, rooms)
                if contract:
                    self._contracts[contract.id] = contract
                    await db.save_bounty(contract)
            except Exception as e:
                log.warning("[bounty] Failed to generate contract: %s", e)

        self._last_refresh = now
        log.info("[bounty] Board refreshed: %d contracts", len(self._contracts))

    # ── Queries ────────────────────────────────────────────────────────────────

    def posted_contracts(self) -> list[BountyContract]:
        return sorted(
            [c for c in self._contracts.values()
             if c.status == BountyStatus.POSTED],
            key=lambda c: c.reward, reverse=True,
        )

    def get(self, contract_id: str) -> Optional[BountyContract]:
        return self._contracts.get(contract_id)

    def find_by_npc(self, npc_id: int) -> Optional[BountyContract]:
        """Find a claimed contract whose target NPC just died."""
        for c in self._contracts.values():
            if c.target_npc_id == npc_id and c.status == BountyStatus.CLAIMED:
                return c
        return None

    # ── Mutations ──────────────────────────────────────────────────────────────

    async def claim(self, contract_id: str, character_id: str, db) -> Optional[BountyContract]:
        """Claim a bounty contract. One claimed contract per character."""
        # Check character doesn't already have one claimed
        for c in self._contracts.values():
            if c.claimed_by == character_id and c.status == BountyStatus.CLAIMED:
                return None  # Already have one active

        c = self._contracts.get(contract_id)
        if not c or c.status != BountyStatus.POSTED:
            return None

        now = time.time()
        c.status = BountyStatus.CLAIMED
        c.claimed_by = character_id
        c.claimed_at = now
        c.expires_at = now + CLAIMED_TTL

        await db.update_bounty(contract_id, c.to_dict())
        # T3.19 telemetry: objective funnel (catalog C).
        try:
            from engine.telemetry import emit_objective as _tele_obj
            _tele_obj("bounty", "start", character_id, oid=contract_id,
                      reward=c.reward, target=c.target_name)
        except Exception as _e:
            log.debug("objective telemetry emit failed: %s", _e)
        return c

    async def collect(self, contract_id: str, alive: bool, db) -> Optional[BountyContract]:
        """
        Mark a bounty as collected.
        Returns the contract (caller awards credits).
        alive=True gives the alive_bonus on top of base reward.
        """
        c = self._contracts.get(contract_id)
        if not c or c.status != BountyStatus.CLAIMED:
            return None

        c.status = BountyStatus.COLLECTED
        c.collected_at = time.time()
        await db.update_bounty(contract_id, c.to_dict())
        # T3.19 telemetry: objective funnel (catalog C). collect() is the sole
        # completion chokepoint — the auto-collect on kill (notify_target_killed)
        # also routes through here, so one emit covers both paths.
        try:
            from engine.telemetry import emit_objective as _tele_obj
            _tele_obj("bounty", "complete", c.claimed_by, oid=contract_id,
                      reward=c.reward + (c.reward_alive_bonus if alive else 0),
                      alive=bool(alive), target=c.target_name)
        except Exception as _e:
            log.debug("objective telemetry emit failed: %s", _e)
        del self._contracts[contract_id]
        return c

    async def notify_target_killed(self, npc_id: int, killer_char_id: str, db) -> Optional[BountyContract]:
        """
        Called by combat_commands when an NPC with is_bounty_target=True dies.
        Automatically collects the bounty for the killer.
        Returns the collected contract or None.
        """
        contract = self.find_by_npc(npc_id)
        if not contract:
            return None
        if contract.claimed_by != str(killer_char_id):
            # Killed by someone other than the claimer — still collect for killer
            contract.claimed_by = str(killer_char_id)

        return await self.collect(contract.id, alive=False, db=db)

    def total_reward(self, contract: BountyContract, alive: bool) -> int:
        return contract.reward + (contract.reward_alive_bonus if alive else 0)


# ── Module-level singleton ─────────────────────────────────────────────────────

_board: Optional[BountyBoard] = None


def get_bounty_board() -> BountyBoard:
    global _board
    if _board is None:
        _board = BountyBoard()
    return _board


def reset_bounty_board() -> None:
    """Test hook: drop the module-level board singleton so the next
    `get_bounty_board()` builds a fresh, empty board.

    Production code does NOT call this. The board is a process-level
    singleton (`_board`) whose in-memory `_contracts` survive across
    test-harness boots within one pytest process — so a contract spawned
    (and claimed) by one test leaks into the next test's board, where the
    idempotent-spawn check in engine/chain_missions._spawn_bounty then
    skips respawning it and the next test sees a stale CLAIMED contract
    instead of a fresh POSTED one. The smoke harness resets this at boot
    (same model as the world-events `_manager` reset documented in the
    testing protocol). drop 26 (2026-06-13)."""
    global _board
    _board = None


# ── Display helpers ────────────────────────────────────────────────────────────

_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_RESET = "\033[0m"
_RED   = "\033[1;31m"
_YELLOW = "\033[1;33m"
_CYAN  = "\033[0;36m"

_TIER_COLORS = {
    BountyTier.EXTRA:    "\033[0;37m",   # white
    BountyTier.AVERAGE:  "\033[0;33m",   # yellow
    BountyTier.NOVICE:   "\033[1;33m",   # bright yellow
    BountyTier.VETERAN:  "\033[1;31m",   # bright red
    BountyTier.SUPERIOR: "\033[1;35m",   # bright magenta
}


def format_bounty_board(contracts: list[BountyContract]) -> list[str]:
    lines = [
        f"{_BOLD}{'='*58}{_RESET}",
        f"{_BOLD}  BOUNTY BOARD  --  Mos Eisley{_RESET}",
        f"{_DIM}  {'ID':<10} {'Tier':<10} {'Target':<18} {'Reward':>8}{_RESET}",
        f"{_DIM}  {'-'*56}{_RESET}",
    ]
    if not contracts:
        lines.append("  No active bounties posted. Check back later.")
    else:
        for c in contracts:
            color = _TIER_COLORS.get(c.tier, "")
            tier_label = c.tier.value.title()
            lines.append(
                f"  {_BOLD}{c.id:<10}{_RESET} "
                f"{color}{tier_label:<10}{_RESET} "
                f"{c.target_name:<18} "
                f"{_BOLD}{c.reward:>7,}cr{_RESET}"
                + (f"  +{c.reward_alive_bonus:,}cr alive" if c.reward_alive_bonus else "")
            )
    lines.append(
        f"{_DIM}  Type '+bounty/claim <id>' to accept. '+bounty/track' to hunt your target.{_RESET}"
    )
    lines.append(f"{_BOLD}{'='*58}{_RESET}")
    return lines


def format_contract_detail(c: BountyContract) -> list[str]:
    color = _TIER_COLORS.get(c.tier, "")
    alive_str = f" (+{c.reward_alive_bonus:,}cr alive)" if c.reward_alive_bonus else ""
    lines = [
        f"{_BOLD}{'='*58}{_RESET}",
        f"  {_BOLD}BOUNTY CONTRACT{_RESET}  [{c.id}]",
        f"  {color}{c.tier.value.title()} Target{_RESET}  |  "
        f"Reward: {_BOLD}{c.reward:,} credits{_RESET}{alive_str}",
        "",
        f"  {_BOLD}Target:{_RESET}      {c.target_name} ({c.target_species})",
        f"  {_BOLD}Wanted for:{_RESET} {c.crime_description}",
        f"  {_BOLD}Posted by:{_RESET}  {c.posting_org}",
        f"  {_BOLD}Intel:{_RESET}      {c.tip}",
        "",
    ]
    if c.status == BountyStatus.CLAIMED:
        if c.expires_at:
            remaining = max(0, int(c.expires_at - time.time()))
            h, rem = divmod(remaining, 3600)
            mn = rem // 60
            lines.append(f"  {_YELLOW}Time remaining: {h}h {mn}m{_RESET}")
        lines.append(f"  {_DIM}Use '+bounty/track' to locate your target.{_RESET}")
        lines.append(f"  {_DIM}Engage and defeat them to collect the reward.{_RESET}")
    lines.append(f"{_BOLD}{'='*58}{_RESET}")
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Webify UI-5 (2026-06-10): board_state producer for the web client
# ─────────────────────────────────────────────────────────────────────────────

def build_board_state(posted: list["BountyContract"],
                      claimed: "BountyContract | None" = None,
                      now: "float | None" = None) -> dict:
    """Assemble the `board_state` push for the web bounty-board modal.

    Pinned ABI (web_client_vision_and_protocol — Webify UI-5)::

        { "contracts": [ BountyContract.to_dict()
                         + {"expires_in_secs": int|None} ],
          "claimed_id": str|None }

    `posted` is the caller's already-visibility-filtered POSTED list
    (the chain-tutorial filter in BountiesCommand applies before this).
    `claimed` is the viewer's active CLAIMED contract, if any — it is
    prepended to the list so the card renders inline with its TRACK
    action, and its id becomes `claimed_id`.

    `expires_in_secs` is derived server-side (remaining seconds,
    clamped ≥ 0; None when the contract has no expiry) so the client
    never has to trust its own clock against `expires_at` epochs.

    Pure + sync: no DB, no singletons; never raises on a malformed
    contract (it is skipped). This keeps the NPC contract board only —
    Dark-Side Notoriety (prestige, no credits) is a different surface
    on the PC bounty board and is NOT part of this message.
    """
    ts = time.time() if now is None else now

    def _entry(c) -> "dict | None":
        try:
            d = c.to_dict()
            exp = d.get("expires_at")
            d["expires_in_secs"] = (
                max(0, int(exp - ts)) if isinstance(exp, (int, float)) and exp
                else None
            )
            return d
        except Exception:
            log.debug("build_board_state: skipping malformed contract",
                      exc_info=True)
            return None

    contracts: list[dict] = []
    claimed_id = None
    if claimed is not None:
        e = _entry(claimed)
        if e is not None:
            contracts.append(e)
            claimed_id = e.get("id")
    for c in posted or []:
        if claimed is not None and getattr(c, "id", None) == claimed_id:
            continue  # never duplicate the viewer's own contract
        e = _entry(c)
        if e is not None:
            contracts.append(e)

    return {"contracts": contracts, "claimed_id": claimed_id}


# ─────────────────────────────────────────────────────────────────────────────
# Drop 4b (2026-06-04): Dark-Side Notoriety — auto-DSP bounty
# ─────────────────────────────────────────────────────────────────────────────
#
# Per the Part V / Drop 4 locked decision (c): a high-DSP character draws a
# bounty automatically. This is DETERMINISTIC and DSP-DERIVED (no new table,
# no AI cost) — the "wanted" state is computed from dark_side_points exactly
# the way force_sensitive is derived from the force attributes. It is
# FACTION-AGNOSTIC (it tracks the dark side, not any player faction) and the
# reward is STATUS / PRESTIGE only (never credits, never the insurance/claim
# flow that the credit-bounty pc_bounties system carries).
#
# This module provides the pure helpers; the parser surfaces them on the BH
# board (parser/pc_bounty_commands.py) and fires the threshold-crossing
# notice (parser/force_commands.py).

# A bounty appears once a Jedi reaches the "Danger Zone" (DSP 4) — the same
# band the forcestatus display flags as dangerous.
DSP_BOUNTY_THRESHOLD = 4

# Mirror of force_powers.DSP_FALL_THRESHOLD (kept local to avoid an
# engine-module import here): at/over this the notoriety reads as "Hunted".
DSP_FALL_THRESHOLD = 6


def is_dsp_wanted(dsp: int) -> bool:
    """True iff this Dark Side Point total draws an automatic bounty."""
    try:
        return int(dsp or 0) >= DSP_BOUNTY_THRESHOLD
    except (TypeError, ValueError):
        return False


def crossed_into_wanted(old_dsp: int, new_dsp: int) -> bool:
    """True iff a DSP change pushes a character across the wanted threshold
    for the first time (so the parser fires the notice exactly once)."""
    return (not is_dsp_wanted(old_dsp)) and is_dsp_wanted(new_dsp)


def dsp_bounty_tier(dsp: int) -> str:
    """Status tier label for a DSP total (prestige, not credits)."""
    d = int(dsp or 0)
    if d >= 9:
        return "Darkest of the Dark"
    if d >= 6:
        return "Hunted"          # at/over the fall threshold
    return "Marked"              # 4-5: Danger Zone


# Faction-agnostic poster: the hunt for a fallen Force-user is its own
# pull, not any one organization's contract.
DSP_BOUNTY_POSTER = "Anonymous — a standing call among hunters"


def format_dsp_notoriety_line(name: str, dsp: int, suffix: str = "") -> str:
    """One board line for a dark-side-wanted character (status reward).

    ``suffix`` (optional) appends the live roaming-hunter pursuit state
    (Drop 4b hunter.1), e.g. "— hunter closing".
    """
    tier = dsp_bounty_tier(dsp)
    color = _RED if int(dsp or 0) >= DSP_FALL_THRESHOLD else _YELLOW
    return (
        f"  {color}{tier:<20}{_RESET} "
        f"on {_BOLD}{name:<20s}{_RESET} "
        f"{_DIM}(prestige — no credits){_RESET}{suffix or ''}"
    )


def format_dsp_notoriety_section(wanted: list, pursuits: "dict | None" = None) -> list:
    """Render the Dark-Side Notoriety section for the BH board.

    ``wanted`` is a list of rows/dicts with 'id', 'name' and 'dark_side_points'.
    ``pursuits`` (optional) maps char_id -> a pursuit row (with a 'stage'); when
    supplied, each line is annotated with that character's roaming-hunter
    pursuit state (Drop 4b hunter.1). Returns [] when no one is wanted, so the
    caller can skip the header.
    """
    rows = [w for w in (wanted or [])
            if is_dsp_wanted((w or {}).get("dark_side_points", 0))]
    if not rows:
        return []
    rows.sort(key=lambda w: int(w.get("dark_side_points", 0) or 0), reverse=True)

    # Lazy import to avoid a module-load cycle (dsp_hunter imports this module).
    _board_suffix = None
    if pursuits:
        try:
            from engine.dsp_hunter import board_suffix as _board_suffix
        except Exception:
            _board_suffix = None

    lines = [
        f"{_BOLD}  Dark-Side Notoriety{_RESET}  "
        f"{_DIM}(auto-posted; reward is prestige, not credits){_RESET}",
        f"{_DIM}  {'-'*56}{_RESET}",
    ]
    for w in rows:
        suffix = ""
        if _board_suffix is not None:
            p = pursuits.get(w.get("id"))
            if p:
                suffix = _board_suffix(p.get("stage", ""))
        lines.append(format_dsp_notoriety_line(
            w.get("name", "?"), w.get("dark_side_points", 0), suffix))
    return lines
