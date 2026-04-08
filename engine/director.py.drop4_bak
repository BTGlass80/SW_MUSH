# -*- coding: utf-8 -*-
"""
Director AI — macro-level storytelling engine.

Manages the faction influence model, compiles world-state digests,
computes zone alert levels, and orchestrates the Faction Turn cycle.

This file contains all LOCAL logic (no API calls). The Claude API
integration is in ai/claude_provider.py (Drop 4).

When the Claude provider is not configured, the Director runs in
"local-only" mode: influence scores change from player actions,
alert levels update automatically, and world events fire via the
timer-based fallback in WorldEventManager.

Files:
  engine/director.py          (this file)
  ai/claude_provider.py       (Drop 4 — API calls)
  engine/world_events.py      (Drop 2 — event activation)
  engine/ambient_events.py    (Drop 1 — ambient text)

DB tables (created via migration v5):
  zone_influence   — per-zone faction scores
  director_log     — audit trail, news source, budget tracking
"""
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)

# ── Constants ──

FACTION_TURN_INTERVAL = 1800  # 30 minutes in seconds

# Valid factions and zones
VALID_FACTIONS = frozenset({"imperial", "rebel", "criminal", "independent"})

# Zone keys matching ROOM_ZONES in build_mos_eisley.py
VALID_ZONES = frozenset({
    "spaceport", "streets", "cantina", "shops",
    "jabba", "government",
})

# Starting influence scores for Mos Eisley (from design doc)
DEFAULT_INFLUENCE = {
    "spaceport":  {"imperial": 65, "rebel": 8,  "criminal": 45, "independent": 25},
    "streets":    {"imperial": 55, "rebel": 12, "criminal": 50, "independent": 35},
    "cantina":    {"imperial": 40, "rebel": 15, "criminal": 65, "independent": 40},
    "shops":      {"imperial": 50, "rebel": 10, "criminal": 55, "independent": 40},
    "jabba":      {"imperial": 20, "rebel": 5,  "criminal": 85, "independent": 10},
    "government": {"imperial": 80, "rebel": 5,  "criminal": 20, "independent": 20},
}

# Influence score range
MIN_INFLUENCE = 0
MAX_INFLUENCE = 100

# Max delta per Director adjustment
MAX_DELTA = 5


# ── Alert Levels ──

class AlertLevel(str, Enum):
    LOCKDOWN = "lockdown"       # Imperial >= 70
    HIGH_ALERT = "high_alert"   # Imperial 50-69
    STANDARD = "standard"       # Imperial 30-49
    LAX = "lax"                 # Imperial < 30
    UNDERWORLD = "underworld"   # Criminal >= 70
    UNREST = "unrest"           # Rebel >= 40


@dataclass
class ZoneState:
    """Computed state for a single zone."""
    zone_key: str
    imperial: int = 50
    rebel: int = 10
    criminal: int = 50
    independent: int = 30
    alert_level: AlertLevel = AlertLevel.STANDARD

    def compute_alert(self) -> AlertLevel:
        """Derive alert level from faction influence scores."""
        # Priority order: most dramatic condition wins
        if self.imperial >= 70:
            self.alert_level = AlertLevel.LOCKDOWN
        elif self.criminal >= 70:
            self.alert_level = AlertLevel.UNDERWORLD
        elif self.rebel >= 40:
            self.alert_level = AlertLevel.UNREST
        elif self.imperial < 30:
            self.alert_level = AlertLevel.LAX
        elif self.imperial >= 50:
            self.alert_level = AlertLevel.HIGH_ALERT
        else:
            self.alert_level = AlertLevel.STANDARD
        return self.alert_level

    def get_faction(self, faction: str) -> int:
        return getattr(self, faction, 0)

    def set_faction(self, faction: str, value: int):
        value = max(MIN_INFLUENCE, min(MAX_INFLUENCE, value))
        setattr(self, faction, value)


# ── Player Action Tracking ──

@dataclass
class ActionDigest:
    """
    Accumulated player actions since last Faction Turn.
    Reset after each turn. Used to compile the API digest.
    """
    kills_by_faction: dict = field(default_factory=lambda: {
        "imperial": 0, "rebel": 0, "criminal": 0, "independent": 0
    })
    missions_by_type: dict = field(default_factory=dict)
    bounties_claimed: int = 0
    bounties_by_tier: dict = field(default_factory=dict)
    contraband_sold: int = 0
    faction_talks: dict = field(default_factory=lambda: {
        "imperial": 0, "rebel": 0, "criminal": 0, "independent": 0
    })

    def record_kill(self, faction: str, zone: str = ""):
        """Record an NPC kill by faction."""
        if faction in self.kills_by_faction:
            self.kills_by_faction[faction] += 1

    def record_mission(self, mission_type: str, zone: str = ""):
        """Record a mission completion."""
        self.missions_by_type[mission_type] = (
            self.missions_by_type.get(mission_type, 0) + 1
        )

    def record_bounty(self, tier: int = 1):
        """Record a bounty claim."""
        self.bounties_claimed += 1
        self.bounties_by_tier[tier] = self.bounties_by_tier.get(tier, 0) + 1

    def record_contraband_sale(self):
        """Record a contraband/smuggling sale."""
        self.contraband_sold += 1

    def record_faction_talk(self, faction: str):
        """Record a reputation-building NPC conversation."""
        if faction in self.faction_talks:
            self.faction_talks[faction] += 1

    def reset(self):
        """Clear all accumulated data for next cycle."""
        self.kills_by_faction = {f: 0 for f in VALID_FACTIONS}
        self.missions_by_type.clear()
        self.bounties_claimed = 0
        self.bounties_by_tier.clear()
        self.contraband_sold = 0
        self.faction_talks = {f: 0 for f in VALID_FACTIONS}

    def has_activity(self) -> bool:
        """Check if any player activity was recorded."""
        return (
            any(v > 0 for v in self.kills_by_faction.values())
            or bool(self.missions_by_type)
            or self.bounties_claimed > 0
            or self.contraband_sold > 0
        )

    def to_digest_dict(self) -> dict:
        """Convert to compact JSON-ready dict for API payload."""
        actions = []
        for faction, count in self.kills_by_faction.items():
            if count > 0:
                actions.append({
                    "type": "kill",
                    "target_faction": faction,
                    "count": count,
                })
        for mtype, count in self.missions_by_type.items():
            if count > 0:
                actions.append({
                    "type": "mission_complete",
                    "mission_type": mtype,
                    "count": count,
                })
        if self.bounties_claimed > 0:
            actions.append({
                "type": "bounty_claimed",
                "count": self.bounties_claimed,
            })
        if self.contraband_sold > 0:
            actions.append({
                "type": "contraband_sold",
                "count": self.contraband_sold,
            })
        return {"player_actions": actions}


# ── Director AI ──

class DirectorAI:
    """
    Singleton orchestrating the macro-level storytelling.

    Responsibilities:
      - Track per-zone faction influence scores (DB-backed)
      - Apply player action deltas to influence
      - Compute zone alert levels (local, every tick)
      - Compile world-state digests for API calls
      - Manage the Faction Turn cycle timer
      - Log all Director decisions for the news board

    Does NOT make API calls — that's ClaudeProvider in Drop 4.
    """

    def __init__(self):
        self._zones: dict[str, ZoneState] = {}
        self._digest = ActionDigest()
        self._loaded = False
        self._enabled = False
        self._tick_counter = 0
        self._last_turn_time = 0.0
        self._turn_interval = FACTION_TURN_INTERVAL

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def zones(self) -> dict[str, ZoneState]:
        return dict(self._zones)

    @property
    def digest(self) -> ActionDigest:
        return self._digest

    def enable(self):
        self._enabled = True
        log.info("[director] Enabled")

    def disable(self):
        self._enabled = False
        log.info("[director] Disabled")

    # ── DB Load/Save ──

    async def ensure_loaded(self, db):
        """Load zone influence from DB, seeding defaults if needed."""
        if self._loaded:
            return

        for zone_key in VALID_ZONES:
            zs = ZoneState(zone_key=zone_key)
            defaults = DEFAULT_INFLUENCE.get(zone_key, {})
            for faction in VALID_FACTIONS:
                score = await self._get_influence(db, zone_key, faction)
                if score is not None:
                    zs.set_faction(faction, score)
                else:
                    # Seed default
                    default_val = defaults.get(faction, 30)
                    zs.set_faction(faction, default_val)
                    await self._set_influence(db, zone_key, faction, default_val)
            zs.compute_alert()
            self._zones[zone_key] = zs

        self._loaded = True
        log.info(
            "[director] Loaded %d zones from DB", len(self._zones)
        )

    async def _get_influence(self, db, zone_id: str, faction: str) -> Optional[int]:
        """Read a single influence score from DB."""
        try:
            rows = await db._db.execute_fetchall(
                "SELECT score FROM zone_influence WHERE zone_id = ? AND faction = ?",
                (zone_id, faction),
            )
            if rows:
                return rows[0]["score"]
        except Exception:
            pass  # Table may not exist yet
        return None

    async def _set_influence(self, db, zone_id: str, faction: str, score: int):
        """Write a single influence score to DB (upsert)."""
        try:
            await db._db.execute(
                """INSERT INTO zone_influence (zone_id, faction, score, last_updated)
                   VALUES (?, ?, ?, datetime('now'))
                   ON CONFLICT(zone_id, faction) DO UPDATE SET
                     score = excluded.score,
                     last_updated = excluded.last_updated""",
                (zone_id, faction, score),
            )
            await db._db.commit()
        except Exception as e:
            log.debug("[director] Failed to write influence: %s", e)

    async def save_all_influence(self, db):
        """Persist all zone influence scores to DB."""
        for zone_key, zs in self._zones.items():
            for faction in VALID_FACTIONS:
                await self._set_influence(
                    db, zone_key, faction, zs.get_faction(faction)
                )

    # ── Influence Modification ──

    def apply_player_action_deltas(self):
        """
        Apply accumulated player action deltas to zone influence.
        Called during the Faction Turn. Uses simple deterministic rules.
        When the Director API is active (Drop 4), it overrides this
        with AI-chosen adjustments.
        """
        d = self._digest

        # Kills shift influence in all zones (simplified — full Director
        # will be zone-aware via the API digest)
        for faction, count in d.kills_by_faction.items():
            if count <= 0:
                continue
            delta = min(count, MAX_DELTA)
            for zs in self._zones.values():
                # Killing faction NPCs reduces that faction's influence
                current = zs.get_faction(faction)
                zs.set_faction(faction, current - delta)

        # Smuggling missions boost criminal influence
        smuggling = d.missions_by_type.get("smuggling", 0)
        if smuggling > 0:
            delta = min(smuggling * 2, MAX_DELTA)
            for zs in self._zones.values():
                zs.set_faction("criminal", zs.criminal + delta)
                zs.set_faction("imperial", zs.imperial - 1)

        # Imperial missions boost imperial influence
        imperial_missions = d.missions_by_type.get("combat", 0)
        if imperial_missions > 0:
            delta = min(imperial_missions, MAX_DELTA)
            for zone_key in ["spaceport", "government"]:
                if zone_key in self._zones:
                    zs = self._zones[zone_key]
                    zs.set_faction("imperial", zs.imperial + delta)

        # Contraband sales boost criminal
        if d.contraband_sold > 0:
            delta = min(d.contraband_sold, MAX_DELTA)
            for zone_key in ["cantina", "shops"]:
                if zone_key in self._zones:
                    zs = self._zones[zone_key]
                    zs.set_faction("criminal", zs.criminal + delta)

        # Recompute all alert levels
        for zs in self._zones.values():
            zs.compute_alert()

    # ── Digest Compilation ──

    def compile_digest(self, session_mgr) -> dict:
        """
        Compile the full world-state digest for the API payload.
        This is what gets sent to Claude in the Faction Turn.
        """
        # Zone influence snapshot
        zone_influence = {}
        for zone_key, zs in self._zones.items():
            zone_influence[zone_key] = {
                "imperial": zs.imperial,
                "rebel": zs.rebel,
                "criminal": zs.criminal,
                "independent": zs.independent,
            }

        # Active world events
        try:
            from engine.world_events import get_world_event_manager
            active_events = get_world_event_manager().active_event_types
        except Exception:
            active_events = []

        # Player count
        player_count = 0
        try:
            player_count = len([
                s for s in session_mgr.all
                if s.is_in_game
            ])
        except Exception:
            pass

        digest = {
            "time_period": "last_30_minutes",
            "zone_influence": zone_influence,
            "active_events": active_events,
            "player_count": player_count,
        }
        digest.update(self._digest.to_digest_dict())
        return digest

    # ── Director Log ──

    async def log_event(self, db, event_type: str, summary: str,
                        details: Optional[dict] = None,
                        input_tokens: int = 0, output_tokens: int = 0):
        """Write an entry to the director_log table."""
        try:
            await db._db.execute(
                """INSERT INTO director_log
                   (event_type, summary, details_json,
                    token_cost_input, token_cost_output)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    event_type,
                    summary,
                    json.dumps(details) if details else None,
                    input_tokens,
                    output_tokens,
                ),
            )
            await db._db.commit()
        except Exception as e:
            log.debug("[director] Failed to write log: %s", e)

    async def get_recent_log(self, db, limit: int = 10) -> list[dict]:
        """Fetch recent director_log entries (for news command)."""
        try:
            rows = await db._db.execute_fetchall(
                """SELECT timestamp, event_type, summary
                   FROM director_log
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    async def get_budget_stats(self, db) -> dict:
        """Get current month's API token usage from director_log."""
        try:
            rows = await db._db.execute_fetchall(
                """SELECT
                     COALESCE(SUM(token_cost_input), 0) as total_input,
                     COALESCE(SUM(token_cost_output), 0) as total_output,
                     COUNT(*) as call_count
                   FROM director_log
                   WHERE timestamp >= date('now', 'start of month')
                     AND event_type = 'faction_turn'""",
            )
            if rows:
                r = dict(rows[0])
                # Haiku 4.5: $1/MTok input, $5/MTok output
                cost_input = (r["total_input"] / 1_000_000) * 1.0
                cost_output = (r["total_output"] / 1_000_000) * 5.0
                r["estimated_cost_usd"] = round(cost_input + cost_output, 4)
                return r
        except Exception:
            pass
        return {"total_input": 0, "total_output": 0, "call_count": 0,
                "estimated_cost_usd": 0.0}

    # ── Faction Turn ──

    async def faction_turn(self, db, session_mgr):
        """
        Execute one Faction Turn cycle.

        In local-only mode (no Claude API):
          1. Apply player action deltas to influence
          2. Recompute alert levels
          3. Save to DB
          4. Log a summary to director_log
          5. Reset the action digest

        When Claude API is active (Drop 4), step 1 is replaced by
        an API call that returns intelligent adjustments.
        """
        await self.ensure_loaded(db)

        # Apply local deltas
        has_activity = self._digest.has_activity()
        if has_activity:
            self.apply_player_action_deltas()
            await self.save_all_influence(db)

        # Generate a news headline
        headline = self._generate_local_headline()

        # Log it
        await self.log_event(
            db,
            event_type="faction_turn",
            summary=headline,
            details=self.compile_digest(session_mgr),
        )

        # Reset digest for next cycle
        self._digest.reset()
        self._last_turn_time = time.time()

        log.info("[director] Faction Turn complete: %s", headline)

    def _generate_local_headline(self) -> str:
        """
        Generate a simple headline from current zone states.
        Used when the Director API is not active.
        """
        # Find the most interesting zone state
        for zs in self._zones.values():
            if zs.alert_level == AlertLevel.LOCKDOWN:
                return f"Imperial forces maintain lockdown in {_zone_display(zs.zone_key)}."
            if zs.alert_level == AlertLevel.UNDERWORLD:
                return f"Criminal activity surges in {_zone_display(zs.zone_key)}."
            if zs.alert_level == AlertLevel.UNREST:
                return f"Rebel sympathizers grow bolder in {_zone_display(zs.zone_key)}."
            if zs.alert_level == AlertLevel.LAX:
                return f"Imperial presence wanes in {_zone_display(zs.zone_key)}."

        return "Mos Eisley continues under the twin suns. Business as usual."

    # ── Tick ──

    async def tick(self, db, session_mgr):
        """
        Called every tick (1s) from game_server tick loop.

        - Ensures zone influence is loaded
        - Increments the Faction Turn timer
        - Fires a Faction Turn when the interval elapses
        """
        if not self._enabled:
            return

        await self.ensure_loaded(db)

        self._tick_counter += 1
        now = time.time()

        # Faction Turn check
        if now - self._last_turn_time >= self._turn_interval:
            try:
                await self.faction_turn(db, session_mgr)
            except Exception:
                log.exception("[director] Faction Turn failed")
                self._last_turn_time = now  # Don't retry immediately

    # ── Query API ──

    def get_zone_state(self, zone_key: str) -> Optional[ZoneState]:
        """Get the current state of a zone."""
        return self._zones.get(zone_key)

    def get_alert_level(self, zone_key: str) -> AlertLevel:
        """Get the alert level for a zone."""
        zs = self._zones.get(zone_key)
        return zs.alert_level if zs else AlertLevel.STANDARD

    def get_all_zone_states(self) -> dict[str, dict]:
        """Get all zone states as a serializable dict."""
        return {
            zk: {
                "imperial": zs.imperial,
                "rebel": zs.rebel,
                "criminal": zs.criminal,
                "independent": zs.independent,
                "alert_level": zs.alert_level.value,
            }
            for zk, zs in self._zones.items()
        }

    async def reset_influence(self, db):
        """Reset all zone influence to starting values. Admin command."""
        for zone_key in VALID_ZONES:
            defaults = DEFAULT_INFLUENCE.get(zone_key, {})
            zs = self._zones.get(zone_key)
            if not zs:
                zs = ZoneState(zone_key=zone_key)
                self._zones[zone_key] = zs
            for faction in VALID_FACTIONS:
                zs.set_faction(faction, defaults.get(faction, 30))
            zs.compute_alert()
        await self.save_all_influence(db)
        log.info("[director] All zone influence reset to defaults")


# ── Zone display name helper ──

_ZONE_DISPLAY = {
    "spaceport": "the Spaceport District",
    "streets": "the central streets",
    "cantina": "the Cantina District",
    "shops": "the Commercial District",
    "jabba": "Jabba's territory",
    "government": "the Government Quarter",
}

def _zone_display(zone_key: str) -> str:
    return _ZONE_DISPLAY.get(zone_key, zone_key)


# ── Module-level singleton ──

_director: Optional[DirectorAI] = None


def get_director() -> DirectorAI:
    """Get or create the global DirectorAI."""
    global _director
    if _director is None:
        _director = DirectorAI()
    return _director
