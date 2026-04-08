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

Investigation: the `bountytrack` command uses Search/Streetwise/Tracking to
reveal the target's current room without direct combat commitment.
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
FUGITIVE_ARCHETYPES = [
    "thug", "smuggler", "bounty_hunter", "scout",
    "stormtrooper", "imperial_officer",
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
        )


# ── Generation helpers ─────────────────────────────────────────────────────────

def _gen_id() -> str:
    import uuid
    return "b-" + str(uuid.uuid4())[:8]


def _pick_tier() -> BountyTier:
    tiers  = list(TIER_WEIGHTS.keys())
    weights = [TIER_WEIGHTS[t] for t in tiers]
    return random.choices(tiers, weights=weights, k=1)[0]


def _scale_reward(tier: BountyTier) -> int:
    lo, hi = PAY_RANGES[tier]
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
        crime_description=random.choice(_CRIME_DESCRIPTIONS),
        posting_org=random.choice(_POSTING_ORGS),
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
        f"{_DIM}  Type 'bountyclaim <id>' to accept. 'bountytrack' to hunt your target.{_RESET}"
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
        lines.append(f"  {_DIM}Use 'bountytrack' to locate your target.{_RESET}")
        lines.append(f"  {_DIM}Engage and defeat them to collect the reward.{_RESET}")
    lines.append(f"{_BOLD}{'='*58}{_RESET}")
    return lines
