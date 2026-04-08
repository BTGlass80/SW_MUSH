# -*- coding: utf-8 -*-
"""
World Events — procedural events that change the game state temporarily.

Two activation paths:
  1. Timer-based (deterministic fallback): Random rolls each tick against
     per-event probability. No API required. Always available.
  2. Director-driven: DirectorAI selects event type + zones via API call
     and calls activate_event() directly. Overrides timer path when active.

Events create OPPORTUNITIES, not OBLIGATIONS. A checkpoint can fine you,
not imprison you. A pirate surge creates targets, not unavoidable death.

Files:
  engine/world_events.py   (this file)

Integration:
  - Tick loop: await get_world_event_manager().tick(db, session_mgr)
  - Director: get_world_event_manager().activate_event(type, zones, duration, headline)
"""
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# ── ANSI helpers ──
_YELLOW = "\033[1;33m"
_CYAN = "\033[1;36m"
_RED = "\033[1;31m"
_DIM = "\033[2m"
_RESET = "\033[0m"


# ── Event Types ──

class EventType(str, Enum):
    IMPERIAL_CRACKDOWN = "imperial_crackdown"
    IMPERIAL_CHECKPOINT = "imperial_checkpoint"
    BOUNTY_SURGE = "bounty_surge"
    MERCHANT_ARRIVAL = "merchant_arrival"
    SANDSTORM = "sandstorm"
    CANTINA_BRAWL = "cantina_brawl"
    DISTRESS_SIGNAL = "distress_signal"
    PIRATE_SURGE = "pirate_surge"
    HUTT_AUCTION = "hutt_auction"
    KRAYT_SIGHTING = "krayt_sighting"
    REBEL_PROPAGANDA = "rebel_propaganda"
    TRADE_BOOM = "trade_boom"


# Frozenset for validation
VALID_EVENT_TYPES = frozenset(e.value for e in EventType)


# ── Event Definitions ──

@dataclass
class EventDef:
    """Static definition of an event type."""
    event_type: EventType
    name: str                       # Human-readable name
    announce_text: str              # Broadcast on activation
    expire_text: str                # Broadcast on expiry
    default_duration_min: int       # Minutes
    default_duration_max: int
    timer_probability: float        # Per-tick chance (1/N per second)
    preferred_zones: list[str]      # Zone keys this event favors
    mechanical_effects: dict        # Key-value effects the game can read


EVENT_DEFS: dict[EventType, EventDef] = {
    EventType.IMPERIAL_CRACKDOWN: EventDef(
        event_type=EventType.IMPERIAL_CRACKDOWN,
        name="Imperial Crackdown",
        announce_text=(
            f"{_RED}[ALERT]{_RESET} Imperial reinforcements are deploying across "
            f"{{zone_name}}. Stormtrooper patrols have doubled. "
            f"Smugglers take note: payouts are up, but so is the heat."
        ),
        expire_text=(
            f"{_DIM}The Imperial presence in {{zone_name}} returns to normal levels.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=60,
        timer_probability=1 / (8 * 3600),   # ~1 per 8 hours
        preferred_zones=["spaceport", "streets"],
        mechanical_effects={"smuggling_pay_mult": 1.5, "patrol_spawn_mult": 2.0},
    ),
    EventType.IMPERIAL_CHECKPOINT: EventDef(
        event_type=EventType.IMPERIAL_CHECKPOINT,
        name="Imperial Checkpoint",
        announce_text=(
            f"{_YELLOW}[NOTICE]{_RESET} An Imperial checkpoint has been established "
            f"in {{zone_name}}. All travelers are subject to inspection."
        ),
        expire_text=(
            f"{_DIM}The Imperial checkpoint in {{zone_name}} has been dismantled.{_RESET}"
        ),
        default_duration_min=15, default_duration_max=30,
        timer_probability=1 / (2 * 3600),   # ~1 per 2 hours
        preferred_zones=["spaceport", "streets"],
        mechanical_effects={"contraband_scan": True},
    ),
    EventType.BOUNTY_SURGE: EventDef(
        event_type=EventType.BOUNTY_SURGE,
        name="Bounty Surge",
        announce_text=(
            f"{_YELLOW}[BOUNTY BOARD]{_RESET} The Bounty Hunters' Guild has posted "
            f"increased rewards for all active contracts. Double payouts for 30 minutes."
        ),
        expire_text=(
            f"{_DIM}Bounty board rewards have returned to standard rates.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=30,
        timer_probability=1 / (6 * 3600),   # ~1 per 6 hours
        preferred_zones=[],                   # Global
        mechanical_effects={"bounty_reward_mult": 2.0},
    ),
    EventType.MERCHANT_ARRIVAL: EventDef(
        event_type=EventType.MERCHANT_ARRIVAL,
        name="Traveling Merchant",
        announce_text=(
            f"{_CYAN}[MARKET]{_RESET} A rare goods merchant has set up shop in "
            f"{{zone_name}}. Stock is limited \u2014 first come, first served."
        ),
        expire_text=(
            f"{_DIM}The traveling merchant has packed up and departed.{_RESET}"
        ),
        default_duration_min=20, default_duration_max=20,
        timer_probability=1 / (2 * 3600),
        preferred_zones=["shops", "streets"],
        mechanical_effects={"rare_vendor": True},
    ),
    EventType.SANDSTORM: EventDef(
        event_type=EventType.SANDSTORM,
        name="Sandstorm",
        announce_text=(
            f"{_YELLOW}[WEATHER]{_RESET} A sandstorm sweeps through {{zone_name}}. "
            f"Visibility is near zero. Perception checks are at \u22121D."
        ),
        expire_text=(
            f"{_DIM}The sandstorm subsides. Dust settles on everything.{_RESET}"
        ),
        default_duration_min=10, default_duration_max=20,
        timer_probability=1 / (4 * 3600),
        preferred_zones=["streets"],
        mechanical_effects={"perception_penalty": -3},  # -1D = -3 pips
    ),
    EventType.CANTINA_BRAWL: EventDef(
        event_type=EventType.CANTINA_BRAWL,
        name="Cantina Brawl",
        announce_text=(
            f"{_RED}[CANTINA]{_RESET} A fight has broken out in the cantina! "
            f"Tables are overturning. Jump in or get clear."
        ),
        expire_text=(
            f"{_DIM}The cantina brawl winds down. Someone starts sweeping up glass.{_RESET}"
        ),
        default_duration_min=5, default_duration_max=5,
        timer_probability=1 / (3 * 3600),
        preferred_zones=["cantina"],
        mechanical_effects={"brawl_active": True},
    ),
    EventType.DISTRESS_SIGNAL: EventDef(
        event_type=EventType.DISTRESS_SIGNAL,
        name="Distress Signal",
        announce_text=(
            f"{_CYAN}[COMMS]{_RESET} A distress signal has been detected from "
            f"a ship in orbit. Rescue for reputation and credits \u2014 or ignore it."
        ),
        expire_text=(
            f"{_DIM}The distress signal has gone silent.{_RESET}"
        ),
        default_duration_min=15, default_duration_max=15,
        timer_probability=1 / (4 * 3600),
        preferred_zones=[],
        mechanical_effects={"distress_active": True},
    ),
    EventType.PIRATE_SURGE: EventDef(
        event_type=EventType.PIRATE_SURGE,
        name="Pirate Surge",
        announce_text=(
            f"{_RED}[ALERT]{_RESET} Pirate activity has spiked in the space lanes. "
            f"Triple spawn rate for the next hour. Fly armed."
        ),
        expire_text=(
            f"{_DIM}Pirate activity returns to normal levels.{_RESET}"
        ),
        default_duration_min=60, default_duration_max=120,
        timer_probability=1 / (6 * 3600),
        preferred_zones=[],
        mechanical_effects={"pirate_spawn_mult": 3.0},
    ),
    EventType.HUTT_AUCTION: EventDef(
        event_type=EventType.HUTT_AUCTION,
        name="Hutt Auction",
        announce_text=(
            f"{_YELLOW}[UNDERWORLD]{_RESET} Jabba's agents are running an auction "
            f"in {{zone_name}}. Rare items, questionable provenance. "
            f"Criminal reputation required."
        ),
        expire_text=(
            f"{_DIM}The Hutt auction has concluded. The agents vanish as quickly as they appeared.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=30,
        timer_probability=1 / (8 * 3600),
        preferred_zones=["jabba", "cantina"],
        mechanical_effects={"hutt_auction": True, "criminal_rep_gate": 30},
    ),
    EventType.KRAYT_SIGHTING: EventDef(
        event_type=EventType.KRAYT_SIGHTING,
        name="Krayt Dragon Sighting",
        announce_text=(
            f"{_RED}[DANGER]{_RESET} A krayt dragon has been spotted near the "
            f"outskirts. The bounty board has posted an emergency contract. "
            f"Bring friends."
        ),
        expire_text=(
            f"{_DIM}The krayt dragon has retreated into the deep desert.{_RESET}"
        ),
        default_duration_min=45, default_duration_max=45,
        timer_probability=1 / (12 * 3600),
        preferred_zones=["streets"],  # outskirts rooms are in streets zone
        mechanical_effects={"krayt_bounty": True},
    ),
    EventType.REBEL_PROPAGANDA: EventDef(
        event_type=EventType.REBEL_PROPAGANDA,
        name="Rebel Propaganda",
        announce_text=(
            f"{_CYAN}[RUMORS]{_RESET} Rebel propaganda holos have appeared on the "
            f"walls in {{zone_name}}. The Empire won't be pleased."
        ),
        expire_text=(
            f"{_DIM}Imperial clean-up crews have removed the Rebel propaganda.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=30,
        timer_probability=1 / (8 * 3600),
        preferred_zones=["streets", "cantina"],
        mechanical_effects={"rebel_influence_tick": 1},
    ),
    EventType.TRADE_BOOM: EventDef(
        event_type=EventType.TRADE_BOOM,
        name="Trade Boom",
        announce_text=(
            f"{_CYAN}[MARKET]{_RESET} A trade convoy has arrived in {{zone_name}}. "
            f"Vendor sell prices are up 25% for the next hour."
        ),
        expire_text=(
            f"{_DIM}The trade convoy has departed. Prices return to normal.{_RESET}"
        ),
        default_duration_min=60, default_duration_max=60,
        timer_probability=1 / (6 * 3600),
        preferred_zones=["shops", "streets"],
        mechanical_effects={"sell_price_mult": 1.25},
    ),
}


# ── Active Event ──

@dataclass
class ActiveEvent:
    """A currently running world event."""
    event_type: EventType
    zones_affected: list[str]
    started_at: float
    expires_at: float
    headline: str = ""
    mechanical_effects: dict = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @property
    def remaining_minutes(self) -> int:
        return max(0, int((self.expires_at - time.time()) / 60))

    @property
    def event_def(self) -> EventDef:
        return EVENT_DEFS[self.event_type]


# ── Zone name helpers ──

# Display names for announcement text
_ZONE_DISPLAY_NAMES = {
    "spaceport": "the Spaceport District",
    "streets": "the central streets",
    "cantina": "the Cantina District",
    "shops": "the Commercial District",
    "jabba": "Jabba's territory",
    "government": "the Government Quarter",
}


def _zone_display(zone_key: str) -> str:
    return _ZONE_DISPLAY_NAMES.get(zone_key, zone_key)


# ── Manager ──

class WorldEventManager:
    """
    Singleton managing active world events.

    Transient — all active events are lost on restart (like SpaceGrid).
    This is intentional: events are short-lived and timer-based.

    Two activation paths:
      1. Timer fallback: tick() rolls random chances per event type
      2. Director API: activate_event() called directly

    Constraints:
      - Max 2 concurrent events
      - 15-minute cooldown between any events
      - Same event type cannot repeat within 2 hours
    """

    MAX_CONCURRENT = 2
    COOLDOWN_SECS = 900       # 15 minutes between events
    REPEAT_COOLDOWN = 7200    # 2 hours before same type can repeat

    def __init__(self):
        self._active: list[ActiveEvent] = []
        self._last_event_time: float = 0.0
        self._type_last_fired: dict[str, float] = {}
        self._director_active: bool = False  # True when Director is managing events

    @property
    def active_events(self) -> list[ActiveEvent]:
        """Get list of currently active events (read-only copy)."""
        return list(self._active)

    @property
    def active_event_types(self) -> list[str]:
        """Get list of active event type strings."""
        return [e.event_type.value for e in self._active]

    def set_director_mode(self, active: bool):
        """
        Enable/disable Director control. When Director is active,
        timer-based random events are suppressed. Events can still
        be activated via activate_event().
        """
        self._director_active = active
        log.info("[events] Director mode: %s", "ON" if active else "OFF")

    def get_effect(self, effect_key: str, default=None):
        """
        Check if any active event provides a specific mechanical effect.
        Returns the effect value, or default if no active event has it.
        Useful for other systems to query: e.g. get_effect("smuggling_pay_mult", 1.0)
        """
        for event in self._active:
            val = event.mechanical_effects.get(effect_key)
            if val is not None:
                return val
        return default

    def get_effects_for_zone(self, zone_key: str) -> dict:
        """
        Get all mechanical effects active in a specific zone.
        Returns merged dict of all effects from events affecting that zone.
        Global events (empty zones_affected) apply everywhere.
        """
        effects = {}
        for event in self._active:
            if not event.zones_affected or zone_key in event.zones_affected:
                effects.update(event.mechanical_effects)
        return effects

    def activate_event(
        self,
        event_type: str,
        zones: Optional[list[str]] = None,
        duration_minutes: Optional[int] = None,
        headline: str = "",
    ) -> Optional[ActiveEvent]:
        """
        Activate a world event. Called by Director AI or timer fallback.

        Args:
            event_type: Must be in VALID_EVENT_TYPES
            zones: Zone keys affected (empty = global)
            duration_minutes: Override duration (clamped 5-120)
            headline: News headline for director_log

        Returns:
            ActiveEvent on success, None if validation fails or constraints block it
        """
        # Validate type
        if event_type not in VALID_EVENT_TYPES:
            log.warning("[events] Invalid event type: %s", event_type)
            return None

        etype = EventType(event_type)
        edef = EVENT_DEFS[etype]

        # Check constraints
        now = time.time()

        if len(self._active) >= self.MAX_CONCURRENT:
            log.debug("[events] Max concurrent events reached")
            return None

        if now - self._last_event_time < self.COOLDOWN_SECS:
            log.debug("[events] Event cooldown active")
            return None

        last_same = self._type_last_fired.get(event_type, 0)
        if now - last_same < self.REPEAT_COOLDOWN:
            log.debug("[events] Same-type repeat cooldown for %s", event_type)
            return None

        # Determine duration
        if duration_minutes is not None:
            duration_minutes = max(5, min(120, duration_minutes))
        else:
            duration_minutes = random.randint(
                edef.default_duration_min, edef.default_duration_max
            )

        # Determine zones
        if zones is None:
            zones = list(edef.preferred_zones) if edef.preferred_zones else []

        # Create active event
        event = ActiveEvent(
            event_type=etype,
            zones_affected=zones,
            started_at=now,
            expires_at=now + (duration_minutes * 60),
            headline=headline or edef.name,
            mechanical_effects=dict(edef.mechanical_effects),
        )

        self._active.append(event)
        self._last_event_time = now
        self._type_last_fired[event_type] = now

        log.info(
            "[events] Activated: %s (zones=%s, duration=%dm)",
            edef.name, zones, duration_minutes,
        )
        return event

    async def _broadcast_activation(self, event: ActiveEvent, session_mgr):
        """Broadcast event activation announcement to all online players."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "Mos Eisley"
        text = edef.announce_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\n  {text}")

    async def _broadcast_expiry(self, event: ActiveEvent, session_mgr):
        """Broadcast event expiry announcement."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "Mos Eisley"
        text = edef.expire_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\n  {text}")

    async def tick(self, db, session_mgr):
        """
        Called every tick (1s) from game_server tick loop.

        1. Expire completed events
        2. If Director mode is OFF, roll for random timer events
        """
        now = time.time()

        # ── Expire finished events ──
        expired = [e for e in self._active if e.is_expired]
        for event in expired:
            self._active.remove(event)
            try:
                await self._broadcast_expiry(event, session_mgr)
            except Exception:
                log.debug("[events] Failed to broadcast expiry", exc_info=True)
            log.info("[events] Expired: %s", event.event_def.name)

        # ── Timer-based random events (only when Director is not active) ──
        if self._director_active:
            return

        if len(self._active) >= self.MAX_CONCURRENT:
            return

        if now - self._last_event_time < self.COOLDOWN_SECS:
            return

        # Roll against each event type's probability
        for etype, edef in EVENT_DEFS.items():
            if edef.timer_probability <= 0:
                continue

            # Check same-type cooldown
            last = self._type_last_fired.get(etype.value, 0)
            if now - last < self.REPEAT_COOLDOWN:
                continue

            # Random roll (probability is per-second)
            if random.random() < edef.timer_probability:
                event = self.activate_event(etype.value)
                if event:
                    try:
                        await self._broadcast_activation(event, session_mgr)
                    except Exception:
                        log.debug("[events] Failed to broadcast activation",
                                  exc_info=True)
                    # Only one random event per tick
                    break

    def get_status(self) -> list[dict]:
        """Get status of all active events (for admin commands)."""
        return [
            {
                "type": e.event_type.value,
                "name": e.event_def.name,
                "zones": e.zones_affected,
                "remaining_minutes": e.remaining_minutes,
                "effects": e.mechanical_effects,
                "headline": e.headline,
            }
            for e in self._active
        ]


# ── Module-level singleton ──

_manager: Optional[WorldEventManager] = None


def get_world_event_manager() -> WorldEventManager:
    """Get or create the global WorldEventManager."""
    global _manager
    if _manager is None:
        _manager = WorldEventManager()
    return _manager
