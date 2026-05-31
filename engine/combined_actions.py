"""
engine/combined_actions.py — SRB.3 (May 22 2026)

Combined-action / Command-bonus surface per
`support_role_buffs_design_v1.md` §4.

R&E rule (paraphrased): a Command roll by a leader provides a bonus
to followers in a single joint action.

   Difficulty 10 (Easy)      → +1D (+3 pips)
   Difficulty 15 (Moderate)  → +2D (+6 pips)
   Difficulty 20 (Difficult) → +3D (+9 pips, cap)

Per design §4.2: **no schema.** Combined actions resolve in a single
round and don't persist across server restarts. This module holds an
in-memory dict of active lead-bonus offers; each entry is consumed
on first use or expires after 60 seconds.

**Substrate decision:** the per-process in-memory dict matches
design intent (ephemeral state, no DB cost on hot-path skill checks).
The trade-off is that a server restart drops in-flight leads — which
is acceptable for an MVP and matches the "doesn't persist" design call.
If multi-process scaling ever lands, this needs to move to a shared
store; the API is namespaced via `_LEAD_OFFERS` for that reason.

The state map:

    _LEAD_OFFERS: dict[int, LeadOffer]   # keyed by leader char_id

A LeadOffer carries the leader id, the action description (for
display), the bonus in pips, the maximum followers, the list of
followers who have joined, and the expiry timestamp.

API surface:

    create_lead_offer(leader_id, action, bonus_pips, room_id) -> LeadOffer
    get_lead_offer_for(char_id) -> Optional[LeadOffer]
    join_lead(follower_id, leader_id) -> tuple[bool, str]
    consume_lead_bonus(char_id) -> int
    cancel_lead_offer(leader_id) -> bool
    reap_expired(now: float | None = None) -> int
    DIFFICULTY_TO_BONUS_PIPS: mapping for the standard Easy/Mod/Diff tiers

Design §4.1 limits:
    - Max 5 followers per leader (matches R&E "combined fire").
    - Leader + followers must be in the same room — enforced at the
      parser layer (LeadCommand has the room context; this module
      stores room_id but doesn't re-check on join, since a follower
      could legitimately move into the room between offer creation
      and join — the parser layer validates on each command).
    - Each follower contributes up to +1D of their own skill — NOT
      modeled in this drop. Followers get the LEADER'S Command bonus
      applied to their own skill rolls. The follower-skill-pooling
      is a follow-up (design §4.3 references resolve_combined_fire
      which doesn't yet exist).
    - One lead action per round; leader can't take a separate
      action while leading. Modeled here as: once a leader has an
      active offer, get_lead_offer_for(leader_id) returns it, and
      the LeadCommand refuses a second lead while the first is live.

This module has NO test isolation problem because tests can reset
the module-global dict (per-pattern that other in-memory caches
in the codebase already use).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

# Lead bonus duration before auto-expiry, in seconds. Per design §4
# ("resolve in a single round"), 60 seconds gives the leader and
# followers enough wall-clock time to acknowledge and act, without
# letting a bonus linger indefinitely.
LEAD_OFFER_DURATION_SECS = 60

# Per design §4.1: max 5 followers per leader.
MAX_FOLLOWERS_PER_LEAD = 5

# Standard R&E mapping: Command difficulty → bonus pips.
# 3 pips = 1D in WEG. Cap at 9 pips (3D) per design.
DIFFICULTY_TO_BONUS_PIPS: dict[int, int] = {
    10: 3,   # Easy     → +1D
    15: 6,   # Moderate → +2D
    20: 9,   # Difficult → +3D (cap)
}

# Standard difficulties exposed for the parser's argument parsing.
STANDARD_DIFFICULTIES = sorted(DIFFICULTY_TO_BONUS_PIPS.keys())


# ── LeadOffer dataclass ──────────────────────────────────────────────────


@dataclass
class LeadOffer:
    """A pending lead-bonus offer from one leader to their followers."""
    leader_id: int
    action: str                       # Free-text action description
    difficulty: int                   # Original Command difficulty (10/15/20)
    bonus_pips: int                   # Looked up from DIFFICULTY_TO_BONUS_PIPS
    room_id: int                      # Where the lead was created
    followers: list[int] = field(default_factory=list)
    created_at: float = 0.0
    expires_at: float = 0.0

    def is_expired(self, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.time()
        return now >= self.expires_at

    def has_capacity(self) -> bool:
        """True if more followers can still join."""
        return len(self.followers) < MAX_FOLLOWERS_PER_LEAD

    def is_member(self, char_id: int) -> bool:
        """True if char_id is the leader or one of the followers."""
        return char_id == self.leader_id or char_id in self.followers

    def bonus_dice_str(self) -> str:
        """Format bonus_pips as a +ND/+Npip string for display."""
        d = self.bonus_pips // 3
        p = self.bonus_pips % 3
        if p == 0:
            return f"+{d}D"
        if d == 0:
            return f"+{p} pip{'s' if p > 1 else ''}"
        return f"+{d}D+{p}"


# ── Module-global state ──────────────────────────────────────────────────

# Keyed by leader_id. A character can lead at most one combined
# action at a time (one-action-per-round per §4.1).
_LEAD_OFFERS: dict[int, LeadOffer] = {}


def _reset_for_test() -> None:
    """Clear all in-memory state. Test-only — production never calls this."""
    _LEAD_OFFERS.clear()


# ── Public API ───────────────────────────────────────────────────────────


def create_lead_offer(
    *,
    leader_id: int,
    action: str,
    difficulty: int,
    room_id: int,
    now: Optional[float] = None,
) -> Optional[LeadOffer]:
    """Create a new lead offer for the leader.

    Returns None if `difficulty` is not in DIFFICULTY_TO_BONUS_PIPS
    (the parser should validate first and present a clean error),
    or if the leader already has an active (non-expired) offer (the
    one-action-per-round rule).

    Side effect: stores the offer in _LEAD_OFFERS.
    """
    if difficulty not in DIFFICULTY_TO_BONUS_PIPS:
        return None
    if now is None:
        now = time.time()
    # Reap any expired offer for this leader first
    existing = _LEAD_OFFERS.get(leader_id)
    if existing is not None and not existing.is_expired(now):
        return None
    offer = LeadOffer(
        leader_id=leader_id,
        action=action,
        difficulty=difficulty,
        bonus_pips=DIFFICULTY_TO_BONUS_PIPS[difficulty],
        room_id=room_id,
        followers=[],
        created_at=now,
        expires_at=now + LEAD_OFFER_DURATION_SECS,
    )
    _LEAD_OFFERS[leader_id] = offer
    return offer


def get_lead_offer_for(char_id: int,
                        now: Optional[float] = None) -> Optional[LeadOffer]:
    """Return the active lead offer this character is a member of.

    Searches BOTH for an offer where char_id is the leader AND for
    one where char_id is a follower. Returns None if char_id isn't a
    member of any active offer, or if the only matching offer has
    expired.
    """
    if now is None:
        now = time.time()
    for offer in _LEAD_OFFERS.values():
        if offer.is_expired(now):
            continue
        if offer.is_member(char_id):
            return offer
    return None


def join_lead(*, follower_id: int, leader_id: int,
              now: Optional[float] = None) -> tuple[bool, str]:
    """Add `follower_id` to leader's offer.

    Returns (ok, message). Failure cases:
      - No offer exists for that leader
      - Offer has expired
      - Follower is already in the offer (idempotent message)
      - Follower IS the leader (can't follow yourself)
      - Offer is at capacity (5 followers)

    The room-sharing rule (§4.1) is NOT enforced here — the parser
    layer has the room context and is responsible.
    """
    if now is None:
        now = time.time()
    offer = _LEAD_OFFERS.get(leader_id)
    if offer is None:
        return (False, "No active lead to join.")
    if offer.is_expired(now):
        # Reap the stale offer
        _LEAD_OFFERS.pop(leader_id, None)
        return (False, "That lead has expired.")
    if follower_id == leader_id:
        return (False, "You can't follow your own lead.")
    if follower_id in offer.followers:
        return (True, "You're already part of this lead.")
    if not offer.has_capacity():
        return (False, f"This lead is at the maximum ({MAX_FOLLOWERS_PER_LEAD}) followers.")
    offer.followers.append(follower_id)
    return (True, f"You join {offer.action}.")


def consume_lead_bonus(char_id: int,
                        now: Optional[float] = None) -> int:
    """Return the bonus_pips for char_id's active lead and CONSUME the offer.

    "Consume" means: the offer is removed from _LEAD_OFFERS. Per design
    §4 ("resolve in a single round"), the bonus applies to ONE skill
    roll then ends.

    Returns 0 if no active offer (no bonus).

    Called by `engine.skill_checks.perform_skill_check` when
    `lead_bonus` isn't supplied explicitly — the helper does an
    auto-lookup. (Explicit pass-through still works for test
    isolation.)
    """
    if now is None:
        now = time.time()
    # Find the offer this character is a member of
    target_leader: Optional[int] = None
    for leader_id, offer in _LEAD_OFFERS.items():
        if offer.is_expired(now):
            continue
        if offer.is_member(char_id):
            target_leader = leader_id
            break
    if target_leader is None:
        return 0
    offer = _LEAD_OFFERS.pop(target_leader)
    return offer.bonus_pips


def cancel_lead_offer(leader_id: int) -> bool:
    """Remove the leader's offer. Returns True if one was removed."""
    return _LEAD_OFFERS.pop(leader_id, None) is not None


def reap_expired(now: Optional[float] = None) -> int:
    """Remove all expired offers. Returns count removed.

    Called by a periodic tick handler. Not strictly required (the
    is_expired check in get_lead_offer_for handles it inline), but
    keeps the dict small.
    """
    if now is None:
        now = time.time()
    expired_keys = [k for k, o in _LEAD_OFFERS.items() if o.is_expired(now)]
    for k in expired_keys:
        del _LEAD_OFFERS[k]
    return len(expired_keys)


def get_all_offers_for_test() -> dict[int, LeadOffer]:
    """Return a copy of all current offers. Test-only inspection."""
    return dict(_LEAD_OFFERS)
