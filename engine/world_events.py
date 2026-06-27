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
    # E1 (2026-06-04): the legacy GCW event types (IMPERIAL_CRACKDOWN /
    # IMPERIAL_CHECKPOINT / REBEL_PROPAGANDA) were renamed to era-clean CW
    # equivalents. Their player-facing strings broadcast "Imperial /
    # Stormtrooper / Rebel / The Empire" — a live B3 era-cleanness leak in
    # the clone_wars production era (tick() fires all defs ungated). The
    # values are internal identifiers; deprecated GCW director_config.yaml
    # references were updated in lock-step.
    SECURITY_CRACKDOWN = "security_crackdown"
    SECURITY_CHECKPOINT = "security_checkpoint"
    BOUNTY_SURGE = "bounty_surge"
    MERCHANT_ARRIVAL = "merchant_arrival"
    SANDSTORM = "sandstorm"
    GRAVEL_STORM = "gravel_storm"   # Lane E2a: worse sandstorm (Secrets of Tatooine §3)
    SANDWHIRL = "sandwhirl"         # Lane E2a: violent sand-funnel set-piece (SoT §3)
    CANTINA_BRAWL = "cantina_brawl"
    DISTRESS_SIGNAL = "distress_signal"
    PIRATE_SURGE = "pirate_surge"
    HUTT_AUCTION = "hutt_auction"
    KRAYT_SIGHTING = "krayt_sighting"
    SEPARATIST_AGITATION = "separatist_agitation"
    TRADE_BOOM = "trade_boom"
    INTELLIGENCE_THAW = "intelligence_thaw"
    SPICE_DEMAND = "spice_demand"
    FLOOD = "flood"                 # Lane D: the E'Y-Akh annual flood (Geonosis & Outer Rim §1.4)


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
    effect_text: str = ""           # Short player-facing effect summary for the
                                    # web-client structured payload (optional;
                                    # empty for events with no metered effect).


EVENT_DEFS: dict[EventType, EventDef] = {
    EventType.SECURITY_CRACKDOWN: EventDef(
        event_type=EventType.SECURITY_CRACKDOWN,
        name="Security Crackdown",
        announce_text=(
            f"{_RED}[ALERT]{_RESET} Security forces are flooding "
            f"{{zone_name}}. Patrols have doubled and inspections are "
            f"everywhere. Smugglers take note: payouts are up, but so is "
            f"the heat."
        ),
        expire_text=(
            f"{_DIM}The security presence in {{zone_name}} eases back to normal levels.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=60,
        timer_probability=1 / (8 * 3600),   # ~1 per 8 hours
        preferred_zones=["spaceport", "streets"],
        mechanical_effects={"smuggling_pay_mult": 1.5, "patrol_spawn_mult": 2.0},
    ),
    EventType.SECURITY_CHECKPOINT: EventDef(
        event_type=EventType.SECURITY_CHECKPOINT,
        name="Security Checkpoint",
        announce_text=(
            f"{_YELLOW}[NOTICE]{_RESET} A security checkpoint has gone up "
            f"in {{zone_name}}. All travelers are subject to inspection."
        ),
        expire_text=(
            f"{_DIM}The checkpoint in {{zone_name}} has been taken down.{_RESET}"
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
            f"Visibility drops to near zero and blowing grit fouls ranged fire "
            f"(Perception \u22121D, ranged attacks \u22121D)."
        ),
        expire_text=(
            f"{_DIM}The sandstorm subsides. Dust settles on everything.{_RESET}"
        ),
        default_duration_min=10, default_duration_max=20,
        timer_probability=1 / (4 * 3600),
        preferred_zones=["streets"],
        # Lane E2a re-tune (SoT §3): sandstorms block vision AND cripple ranged
        # energy/missile fire. -1D = -3 pips on each. perception_penalty is
        # consumed by skill_checks.perform_skill_check (observation family);
        # ranged_penalty by combat._resolve_ranged_attack.
        mechanical_effects={"perception_penalty": -3, "ranged_penalty": -3},
        effect_text="Perception \u22121D, ranged fire \u22121D",
    ),
    # ── Lane E2a (Secrets of Tatooine §3): graded sand-weather above SANDSTORM ──
    # Three tiers, ×1 / ×2 / ×3 the -1D base, on the two effects that have live
    # consumers (perception_penalty → skill_checks; ranged_penalty → combat).
    # d20 source DCs/damage discarded; re-stat to D6 per the WEG mandate. The
    # space form of the sandwhirl (dragging a starship) is DEFERRED to the space
    # lane — there is no space-weather consumer in HEAD; flight effects are not
    # declared here so no effect ships without a consumer (anti-phantom).
    EventType.GRAVEL_STORM: EventDef(
        event_type=EventType.GRAVEL_STORM,
        name="Gravel Storm",
        announce_text=(
            f"{_YELLOW}[WEATHER]{_RESET} A gravel storm scours {{zone_name}} — a sandstorm "
            f"shot through with flying stone. Even shorter sightlines, even worse shooting "
            f"(Perception \u22122D, ranged attacks \u22122D)."
        ),
        expire_text=(
            f"{_DIM}The gravel storm blows itself out, leaving grit and dented plating behind.{_RESET}"
        ),
        default_duration_min=10, default_duration_max=18,
        timer_probability=1 / (8 * 3600),   # rarer than a plain sandstorm
        preferred_zones=["streets", "spaceport"],
        mechanical_effects={"perception_penalty": -6, "ranged_penalty": -6},  # -2D / -2D
        effect_text="Perception \u22122D, ranged fire \u22122D",
    ),
    EventType.SANDWHIRL: EventDef(
        event_type=EventType.SANDWHIRL,
        name="Sandwhirl",
        announce_text=(
            f"{_RED}[WEATHER]{_RESET} A sandwhirl tears across {{zone_name}} without warning — "
            f"a towering funnel of sand with winds ten times a storm's, strong enough to drag a "
            f"light freighter off its struts and fling a bantha like chaff. Find solid shelter NOW "
            f"(Perception \u22123D, ranged attacks \u22123D)."
        ),
        expire_text=(
            f"{_DIM}The sandwhirl wanders off as fast as it came, its roar fading to the hiss of settling sand.{_RESET}"
        ),
        default_duration_min=3, default_duration_max=6,   # short-lived but violent
        timer_probability=1 / (10 * 3600),                # rarest
        preferred_zones=["streets", "spaceport"],
        mechanical_effects={"perception_penalty": -9, "ranged_penalty": -9},  # -3D / -3D
        effect_text="Perception \u22123D, ranged fire \u22123D",
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
            f"{_YELLOW}[UNDERWORLD]{_RESET} A Hutt kajidic is running an auction "
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
    EventType.SEPARATIST_AGITATION: EventDef(
        event_type=EventType.SEPARATIST_AGITATION,
        name="Separatist Agitation",
        announce_text=(
            f"{_CYAN}[RUMORS]{_RESET} Separatist agitprop has appeared on the "
            f"walls in {{zone_name}} \u2014 pro-Confederacy slogans, anti-war "
            f"screeds. Someone is stirring sympathies."
        ),
        expire_text=(
            f"{_DIM}Local authorities have scrubbed the Separatist holos from {{zone_name}}.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=30,
        timer_probability=1 / (8 * 3600),
        preferred_zones=["streets", "cantina"],
        # Dormant effect (no live consumer) \u2014 renamed from the legacy
        # GCW rebel-influence key as part of the E1 era-cleanness pass.
        mechanical_effects={"cis_influence_tick": 1},
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
    EventType.INTELLIGENCE_THAW: EventDef(
        event_type=EventType.INTELLIGENCE_THAW,
        name="Intelligence Thaw",
        announce_text=(
            f"{_CYAN}[INTEL]{_RESET} The war's loose talk is everywhere right now "
            f"\\u2014 leaked dispatches, careless comm traffic, defectors with "
            f"stories to sell. Faction handlers are paying top credit for fresh, "
            f"actionable intelligence. Double rates for the next 30 minutes."
        ),
        expire_text=(
            f"{_DIM}Intelligence channels go quiet again. Handlers return to "
            f"standard rates.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=30,
        timer_probability=1 / (6 * 3600),   # ~1 per 6 hours (cf. Bounty Surge)
        preferred_zones=[],                   # Global \u2014 intel desks are faction-wide
        # A3 (report): the spy playstyle's "holiday". 2x the credit payout from
        # handing sealed intel to a faction handler (engine/intel_handlers.py
        # reads this via get_effect("intel_pay_mult", 1.0)). Influence is NOT
        # multiplied \u2014 that would distort the territory-contest system; the
        # thaw is an income opportunity, never a territory lever.
        mechanical_effects={"intel_pay_mult": 2.0},
    ),
    EventType.SPICE_DEMAND: EventDef(
        event_type=EventType.SPICE_DEMAND,
        name="Spice Demand",
        announce_text=(
            f"{_CYAN}[UNDERWORLD]{_RESET} Spice is moving fast right now \\u2014 "
            f"the kajidic are paying a premium and every cartel fixer wants "
            f"product on the move. Smuggling runs are paying double for the "
            f"next 30 minutes."
        ),
        expire_text=(
            f"{_DIM}The spice rush cools off. Smuggling payouts return to "
            f"standard rates.{_RESET}"
        ),
        default_duration_min=30, default_duration_max=30,
        timer_probability=1 / (6 * 3600),   # ~1 per 6 hours (cf. Bounty Surge)
        preferred_zones=[],                   # Global \u2014 the spice trade is galaxy-wide
        # A5 (report): the Hutt/criminal playstyle's "holiday". 2x the smuggling
        # payout while active (parser/smuggling_commands.py reads this via
        # get_effect("smuggling_pay_mult", 1.0)). NOTE: this is the FIRST live
        # consumer of smuggling_pay_mult \u2014 it was previously dormant (defined on
        # the legacy crackdown def but never read). Bounded temporary
        # multiplier on the already-ledger-metered `smuggling` faucet.
        mechanical_effects={"smuggling_pay_mult": 2.0},
    ),

    # ── Lane D (Geonosis & Outer Rim §1.4): the E'Y-Akh annual flood ──────────
    # A rare, region-specific weather set-piece. Like the storms it broadcasts
    # globally naming its locale (the world-event audience is not yet zoned —
    # the same coarse-zone tech-debt the storms carry; flagged in TODO). Its one
    # declared effect, perception_penalty, has a LIVE consumer
    # (skill_checks.perform_skill_check, observation family) — the flooded
    # desert is murk, spray, and thrashing drowning creatures. Mechanical
    # flood->encounter wiring (drowning merdeths, shell-salvage) is a follow-up
    # for when the zone-aware effect model lands.
    EventType.FLOOD: EventDef(
        event_type=EventType.FLOOD,
        name="E'Y-Akh Flood",
        announce_text=(
            f"{_CYAN}[WEATHER]{_RESET} The aquifers beneath the E'Y-Akh overflow and the "
            f"annual flood rolls out across the low desert. Geonosian drones drive merdeths "
            f"down into the rising water to drown them; the flood churns with the things it "
            f"has caught, and murk and spray foul sight across the wastes (Perception \u22121D)."
        ),
        expire_text=(
            f"{_DIM}The flood drains back out of the E'Y-Akh, leaving a glitter of bleached "
            f"merdeth shells strewn across the drying sand.{_RESET}"
        ),
        default_duration_min=60, default_duration_max=120,   # a long event, not a squall
        timer_probability=1 / (18 * 3600),                   # rarest weather — the season comes round
        preferred_zones=["geonosis_ey_akh"],
        mechanical_effects={"perception_penalty": -3},       # -1D; consumed by skill_checks
        effect_text="Perception \u22121D",
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
    "jabba": "the Hutt quarter",
    "government": "the Government Quarter",
    "geonosis_ey_akh": "the E'Y-Akh",
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
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "the galaxy"
        text = edef.announce_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\n  {text}")
        # Send structured world_event to web clients
        try:
            import json as _json
            for _s in session_mgr.all:
                if (_s.is_in_game and hasattr(_s, 'protocol')
                        and _s.protocol.value == 'websocket'):
                    await _s._send(_json.dumps({
                        "type": "world_event",
                        "action": "start",
                        "title": edef.name,
                        "effects": edef.effect_text,
                        "event_type": event.event_type,
                    }))
        except Exception:
            pass  # Non-critical

    async def _broadcast_expiry(self, event: ActiveEvent, session_mgr):
        """Broadcast event expiry announcement."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "the galaxy"
        text = edef.expire_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\n  {text}")
        # Send structured world_event end to web clients
        try:
            import json as _json
            for _s in session_mgr.all:
                if (_s.is_in_game and hasattr(_s, 'protocol')
                        and _s.protocol.value == 'websocket'):
                    await _s._send(_json.dumps({
                        "type": "world_event",
                        "action": "end",
                        "title": edef.name,
                        "event_type": event.event_type,
                    }))
        except Exception:
            pass  # Non-critical

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
                log.warning("[events] Failed to broadcast expiry", exc_info=True)
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


# ── Flag consumers (thin modulators over existing systems) ──
#
# WORLDEVENT.flag_effect_consumers (2026-06-13): the MERCHANT_ARRIVAL /
# HUTT_AUCTION / KRAYT_SIGHTING / CANTINA_BRAWL / DISTRESS_SIGNAL events
# set boolean FLAG effects that were fired but never consumed. Per the
# design call these wire as THIN consumers over existing systems
# (extend-don't-add), mirroring the contraband_scan precedent
# (engine/smuggling.py): read the flag at one existing seam, modulate a
# deterministic outcome. Each consumer is a pure function so it unit-tests
# without the manager (the manager-driven path is integration-tested).

# A "rare merchant has arrived" event discounts open-vendor stock for the
# duration. First-guess tunable (post-launch telemetry tunes it).
RARE_VENDOR_DISCOUNT = 0.15  # 15% off the pre-haggle base price


def apply_rare_vendor_discount(base_price: int,
                               rare_vendor_active: bool) -> int:
    """MERCHANT_ARRIVAL / `rare_vendor` consumer. When the event is
    active, knock RARE_VENDOR_DISCOUNT off the vendor's pre-haggle base
    price (the haggle + faction mods then work from the lower base).
    Returns the (possibly discounted) price, floored at 1.

    Pure function — pass the flag in; the buy command reads it via
    get_world_event_manager().get_effect('rare_vendor', False)."""
    if not rare_vendor_active or base_price <= 0:
        return base_price
    return max(1, int(round(base_price * (1.0 - RARE_VENDOR_DISCOUNT))))


# A live Hutt auction lets a sufficiently-connected criminal buy a
# normally-unstocked item at a premium markup (the simplified rep-gated
# purchase, NOT a bidding loop — per the WORLDEVENT design call).
HUTT_AUCTION_MARKUP = 0.40  # +40% over book for auction access


def hutt_auction_purchase_allowed(criminal_rep: int,
                                  hutt_auction_active: bool,
                                  rep_gate: int = 30) -> bool:
    """HUTT_AUCTION / `hutt_auction` consumer (gate half). True iff the
    auction is active AND the player's criminal (hutt_cartel) rep meets
    the event's criminal_rep_gate. Pure function — the buy command reads
    the flags + rep and passes them in."""
    if not hutt_auction_active:
        return False
    try:
        return int(criminal_rep) >= int(rep_gate)
    except (TypeError, ValueError):
        return False


def apply_hutt_auction_markup(base_price: int,
                              hutt_auction_active: bool) -> int:
    """HUTT_AUCTION / `hutt_auction` consumer (price half). Auction access
    costs a premium: marks up the base price by HUTT_AUCTION_MARKUP while
    active. Pure function. Returns the marked-up price (floored at 1)."""
    if not hutt_auction_active or base_price <= 0:
        return base_price
    return max(1, int(round(base_price * (1.0 + HUTT_AUCTION_MARKUP))))
