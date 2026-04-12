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

    async def compile_digest(self, session_mgr, db=None) -> dict:
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
            log.warning("compile_digest: unhandled exception", exc_info=True)
            pass

        digest = {
            "time_period": "last_30_minutes",
            "zone_influence": zone_influence,
            "active_events": active_events,
            "player_count": player_count,
        }
        digest.update(self._digest.to_digest_dict())

        # ── Online PC short records (narrative AI, gated) ──────────────────
        # Inject short_record for each online player so the Director can
        # generate personalised pc_hooks. Only included when narrative AI
        # is enabled and at least one record exists.
        try:
            from engine.narrative import is_narrative_ai_enabled
            if is_narrative_ai_enabled() and db is not None:
                online_pcs = []
                for sess in session_mgr.all:
                    if not sess.is_in_game:
                        continue
                    char = getattr(sess, "character", None)
                    if not char:
                        continue
                    char_id = char.get("id")
                    char_name = char.get("name", "unknown")
                    rec = await db.get_narrative(char_id)
                    short = rec.get("short_record", "") if rec else ""
                    if short:
                        online_pcs.append({
                            "char_id": char_id,
                            "name": char_name,
                            "short_record": short[:300],  # cap at 300 chars
                        })
                if online_pcs:
                    digest["online_pcs"] = online_pcs
        except Exception as _narr_exc:
            log.debug("[director] PC digest skipped: %s", _narr_exc)

        # ── Faction status for Director-managed orgs ───────────────────────
        # Provides member counts, pending promotions, treasury, violations
        # so the Director can issue meaningful faction_orders.
        try:
            if db is not None:
                faction_status = {}
                # Only director-managed factions
                rows = await db._db.execute_fetchall(
                    "SELECT id, code, name, treasury FROM organizations "
                    "WHERE org_type = 'faction' AND director_managed = 1"
                )
                for org_row in rows:
                    org_id   = org_row["id"]
                    org_code = org_row["code"]
                    members  = await db.get_org_members(org_id)

                    # Recent activity: members active in last 24h via action log
                    import time as _t
                    cutoff = _t.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        _t.gmtime(_t.time() - 86400),
                    )
                    active_rows = await db._db.execute_fetchall(
                        """SELECT DISTINCT char_id FROM pc_action_log
                           WHERE logged_at > ?
                             AND char_id IN (
                               SELECT char_id FROM org_memberships
                               WHERE org_id = ?
                             )""",
                        (cutoff, org_id),
                    )
                    active_24h = len(active_rows)

                    # Pending promotions: good standing, rep meets next rank
                    ranks = await db.get_org_ranks(org_id)
                    rank_map = {r["rank_level"]: r for r in ranks}
                    pending_promotions = []
                    for m in members:
                        if m.get("standing") != "good":
                            continue
                        next_level = m["rank_level"] + 1
                        next_rank  = rank_map.get(next_level)
                        if next_rank and m.get("rep_score", 0) >= next_rank["min_rep"]:
                            pending_promotions.append(m["char_id"])

                    # Recent violations: probation/expelled in faction_log
                    viol_rows = await db._db.execute_fetchall(
                        """SELECT m.char_id, c.name
                           FROM org_memberships m
                           JOIN characters c ON c.id = m.char_id
                           WHERE m.org_id = ? AND m.standing != 'good'""",
                        (org_id,),
                    )
                    violations = [r["name"] for r in viol_rows]

                    # Open requisitions from faction_log
                    req_rows = await db._db.execute_fetchall(
                        """SELECT c.name || ': ' || fl.details AS req
                           FROM faction_log fl
                           JOIN characters c ON c.id = fl.char_id
                           WHERE fl.org_id = ?
                             AND fl.action_type = 'requisition_request'
                             AND fl.logged_at > ?""",
                        (org_id, cutoff),
                    )
                    open_requisitions = [r["req"][:60] for r in req_rows]

                    # Unassigned faction missions
                    unassigned = await db._db.execute_fetchall(
                        "SELECT COUNT(*) AS cnt FROM missions "
                        "WHERE faction_id = ? AND status = 'available'",
                        (org_code,),
                    )
                    unassigned_count = unassigned[0]["cnt"] if unassigned else 0

                    faction_status[org_code] = {
                        "member_count":        len(members),
                        "active_last_24h":     active_24h,
                        "treasury":            org_row["treasury"],
                        "pending_promotions":  pending_promotions,
                        "recent_violations":   violations,
                        "unassigned_missions": unassigned_count,
                        "open_requisitions":   open_requisitions[:3],
                    }
                if faction_status:
                    digest["faction_status"] = faction_status
        except Exception as _fac_exc:
            log.debug("[director] faction_status skipped: %s", _fac_exc)

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


    async def _run_api_turn(
        self,
        db,
        session_mgr,
        ai_mgr,
    ) -> bool:
        """
        Attempt a Faction Turn via the Claude API.

        Compiles the world-state digest, sends it to ClaudeProvider,
        parses and validates the JSON response, then applies:
          - influence_adjustments to zone influence scores
          - narrative_event to WorldEventManager (if present)
          - ambient_pool to AmbientEventManager (if present)
          - news_headline to director_log

        Returns True if the API turn succeeded, False if fallback needed.
        """
        import json as _json

        # Check provider availability
        claude = ai_mgr.providers.get("claude") if ai_mgr else None
        if not claude:
            return False
        if not await claude.is_available():
            return False

        # Build the director system prompt (static, cacheable)
        system_prompt = (
            "You are the Director AI for a Star Wars MUSH set in Mos Eisley, Tatooine.\n"
            "Your role is to evaluate the current state of the galaxy and decide what\n"
            "happens next at the MACRO level. You never narrate player actions or\n"
            "describe what individual characters do. You move the unseen pieces:\n"
            "faction responses, economic shifts, atmospheric changes, and emerging\n"
            "threats.\n\n"
            "You are guided by these principles:\n"
            "- The Empire reacts to resistance with escalation, not retreat.\n"
            "- The criminal underworld fills any vacuum the Empire leaves.\n"
            "- The Rebel Alliance operates in shadows; their influence is felt\n"
            "  through sabotage and propaganda, not open warfare on Tatooine.\n"
            "- Tatooine is a backwater. The Empire cares about order, not ideology.\n"
            "  The Hutts care about profit. Neither wants open war here.\n"
            "- Events should create OPPORTUNITIES for players, never OBLIGATIONS.\n"
            "- Consequences should feel proportional and narratively logical.\n\n"
            "FACTION MANAGEMENT:\n"
            "If the digest includes 'faction_status', you manage those factions.\n"
            "You may issue up to 3 faction_orders total per turn. Guidelines:\n"
            "- Promote conservatively. Players must EARN rank.\n"
            "- Post missions that reflect current world state, not random jobs.\n"
            "- Discipline escalates: warn → probation → expel. Never skip steps.\n"
            "- Approve requisitions unless the member negligently caused the loss.\n"
            "- Never promote past pending_promotions list — only promote listed chars.\n\n"
            "PC HOOKS:\n"
            "If the digest includes 'online_pcs', you may generate up to 2\n"
            "personalised story hooks for specific players based on their short_record.\n"
            "Hooks must be brief (1-2 sentences), in-universe, and create opportunity\n"
            "not obligation. Deliver via comlink_message unless NPC context warrants whisper.\n\n"
            "Respond with ONLY a JSON object in this exact format:\n"
            "{\n"
            "  \"influence_adjustments\": [\n"
            "    {\"zone\": \"...\", \"faction\": \"...\", \"delta\": <int>}\n"
            "  ],\n"
            "  \"narrative_event\": {\n"
            "    \"type\": \"...\",\n"
            "    \"headline\": \"...\",\n"
            "    \"duration_minutes\": <int>,\n"
            "    \"zones_affected\": [\"...\"],\n"
            "    \"mechanical_effects\": {\"...\": \"...\"}\n"
            "  } OR null,\n"
            "  \"ambient_pool\": [\"line1\", \"line2\", \"line3\"] OR null,\n"
            "  \"news_headline\": \"One-sentence summary for the world events board.\",\n"
            "  \"faction_orders\": [\n"
            "    {\n"
            "      \"faction\": \"empire\" | \"rebel\" | \"cartel\" | \"bhg\" | \"traders\",\n"
            "      \"action\": \"promote\" | \"warn\" | \"probation\" | \"expel\" | \"pardon\"\n"
            "               | \"post_mission\" | \"faction_announcement\",\n"
            "      \"target_char_id\": <int> | null,\n"
            "      \"new_rank\": <int> | null,\n"
            "      \"reason\": \"...\",\n"
            "      \"mission_type\": \"patrol\" | \"delivery\" | \"combat\" | \"investigation\" | null,\n"
            "      \"zone\": \"...\" | null,\n"
            "      \"reward\": <int 100-5000> | null,\n"
            "      \"description\": \"...\" | null,\n"
            "      \"message\": \"...\" | null\n"
            "    }\n"
            "  ] OR null,\n"
            "  \"pc_hooks\": [\n"
            "    {\n"
            "      \"char_id\": <int>,\n"
            "      \"hook_type\": \"rumor\" | \"opportunity\" | \"encounter\",\n"
            "      \"content\": \"Brief in-universe message (1-2 sentences max)\",\n"
            "      \"delivery\": \"comlink_message\" | \"npc_whisper\" | \"news_item\" | \"ambient\"\n"
            "    }\n"
            "  ] OR null\n"
            "}"
        )

        # Compile digest
        digest = await self.compile_digest(session_mgr, db=db)
        user_message = _json.dumps(digest, ensure_ascii=False)

        # Call API
        try:
            raw = await claude.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=1000,
                temperature=0.7,
            )
        except Exception as exc:
            log.warning("[director] Claude API call failed: %s", exc)
            return False

        if not raw:
            log.debug("[director] Claude returned empty response — using local fallback.")
            return False

        # Parse JSON response
        try:
            # Strip possible markdown fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(
                    l for l in lines if not l.strip().startswith("```")
                )
            resp = _json.loads(cleaned)
        except _json.JSONDecodeError as exc:
            log.warning("[director] JSON parse failed: %s — raw: %.200s", exc, raw)
            return False

        # ── Validate & apply influence adjustments ─────────────────────────
        VALID_ZONES    = frozenset(self._zones.keys())
        VALID_FACTIONS = frozenset({"imperial", "rebel", "criminal", "independent"})
        EVENT_TYPES    = frozenset({
            "imperial_crackdown", "imperial_checkpoint", "bounty_surge",
            "merchant_arrival", "sandstorm", "cantina_brawl", "distress_signal",
            "pirate_surge", "hutt_auction", "krayt_sighting",
            "rebel_propaganda", "trade_boom",
        })

        adjustments = resp.get("influence_adjustments", [])
        if isinstance(adjustments, list):
            for adj in adjustments:
                zone    = adj.get("zone", "")
                faction = adj.get("faction", "")
                delta   = adj.get("delta", 0)
                if zone not in VALID_ZONES:
                    log.debug("[director] Skipping invalid zone '%s'", zone)
                    continue
                if faction not in VALID_FACTIONS:
                    log.debug("[director] Skipping invalid faction '%s'", faction)
                    continue
                delta = max(-5, min(5, int(delta)))  # clamp ±5
                await self._apply_influence_delta(db, zone, faction, delta)

        # ── Apply narrative event ──────────────────────────────────────────
        narrative_event = resp.get("narrative_event")
        if isinstance(narrative_event, dict):
            evt_type = narrative_event.get("type", "")
            if evt_type in EVENT_TYPES:
                duration = int(narrative_event.get("duration_minutes", 30))
                duration = max(15, min(120, duration))
                zones    = narrative_event.get("zones_affected", [])
                if isinstance(zones, str):
                    zones = [zones]
                headline = narrative_event.get("headline", evt_type)
                try:
                    from engine.world_events import get_world_event_manager
                    wem = get_world_event_manager()
                    activated = await wem.activate_event(
                        db, session_mgr,
                        event_type=evt_type,
                        zones_affected=zones,
                        duration_minutes=duration,
                        headline=headline,
                        source="director",
                    )
                    if activated:
                        log.info(
                            "[director] Narrative event activated: %s (zones: %s)",
                            evt_type, zones,
                        )
                except Exception as exc:
                    log.warning("[director] Failed to activate narrative event: %s", exc)
            else:
                log.debug("[director] Invalid event type '%s' — ignored.", evt_type)

        # ── Update dynamic ambient pool ────────────────────────────────────
        ambient_pool = resp.get("ambient_pool")
        if isinstance(ambient_pool, list):
            online_names = set()
            try:
                online_names = {
                    s.char_name.lower()
                    for s in session_mgr.sessions.values()
                    if getattr(s, "char_name", None)
                }
            except Exception:
                log.warning("_run_api_turn: unhandled exception", exc_info=True)
                pass
            BAD_KEYWORDS = frozenset({"roll", "attack", "skill check", "dice"})
            valid_lines = []
            for line in ambient_pool:
                if not isinstance(line, str):
                    continue
                line = line.strip()
                if not line or len(line) > 120:
                    continue
                lower = line.lower()
                if any(kw in lower for kw in BAD_KEYWORDS):
                    continue
                if any(name in lower for name in online_names):
                    continue
                valid_lines.append(line)
            if valid_lines:
                try:
                    from engine.ambient_events import get_ambient_manager
                    get_ambient_manager().set_dynamic_pool(valid_lines)
                    log.debug(
                        "[director] Dynamic ambient pool updated (%d lines).",
                        len(valid_lines),
                    )
                except Exception as exc:
                    log.warning("[director] Failed to update ambient pool: %s", exc)

        # ── Parse and execute faction_orders ──────────────────────────────
        faction_orders = resp.get("faction_orders")
        if isinstance(faction_orders, list) and faction_orders:
            VALID_FACTION_ACTIONS = frozenset({
                "promote", "warn", "probation", "expel", "pardon",
                "post_mission", "faction_announcement",
            })
            VALID_MISSION_TYPES = frozenset({
                "patrol", "delivery", "combat", "investigation",
                "bounty", "smuggling", "social",
            })
            VALID_FACTION_CODES = frozenset({
                "empire", "rebel", "hutt", "bh_guild",
            })
            orders_applied = 0
            for order in faction_orders[:3]:  # Hard cap: 3 orders per turn
                if not isinstance(order, dict):
                    continue
                faction_code = order.get("faction", "")
                action       = order.get("action", "")
                if faction_code not in VALID_FACTION_CODES:
                    log.debug("[director] faction_order: invalid faction '%s'", faction_code)
                    continue
                if action not in VALID_FACTION_ACTIONS:
                    log.debug("[director] faction_order: invalid action '%s'", action)
                    continue

                try:
                    await self._apply_faction_order(
                        db, session_mgr, faction_code, action, order
                    )
                    orders_applied += 1
                except Exception as _ord_exc:
                    log.warning("[director] faction_order failed: %s", _ord_exc)

            if orders_applied:
                log.info("[director] Applied %d faction_order(s).", orders_applied)

        # ── Parse and deliver pc_hooks ─────────────────────────────────────
        pc_hooks = resp.get("pc_hooks")
        if isinstance(pc_hooks, list) and pc_hooks:
            VALID_DELIVERIES = frozenset({
                "comlink_message", "npc_whisper", "news_item", "ambient"
            })
            VALID_HOOK_TYPES = frozenset({
                "rumor", "opportunity", "encounter", "personal_quest"
            })
            delivered = 0
            for hook in pc_hooks[:2]:  # Hard cap: max 2 hooks per turn
                if not isinstance(hook, dict):
                    continue
                char_id   = hook.get("char_id")
                content   = str(hook.get("content", "")).strip()[:300]
                delivery  = hook.get("delivery", "comlink_message")
                hook_type = hook.get("hook_type", "opportunity")

                if not char_id or not content:
                    continue
                if delivery not in VALID_DELIVERIES:
                    delivery = "comlink_message"
                if hook_type not in VALID_HOOK_TYPES:
                    hook_type = "opportunity"

                try:
                    await self._deliver_pc_hook(
                        db, session_mgr,
                        char_id=int(char_id),
                        content=content,
                        delivery=delivery,
                        hook_type=hook_type,
                    )
                    delivered += 1
                except Exception as _hook_exc:
                    log.warning("[director] pc_hook delivery failed: %s", _hook_exc)

            if delivered:
                log.info("[director] Delivered %d pc_hook(s) this turn.", delivered)

        # ── Write director log ─────────────────────────────────────────────
        news_headline = str(resp.get("news_headline", "Faction Turn complete."))[:200]
        details_json  = _json.dumps(resp, ensure_ascii=False)[:4000]

        # Get token counts from ClaudeProvider budget stats
        stats      = claude.get_budget_stats()
        # Approximate call tokens — ClaudeProvider tracks cumulatively.
        # For the log we store 0/0 (exact per-call tracking would require
        # returning from generate(); good enough for audit purposes).
        tok_in  = 0
        tok_out = 0

        await self.log_event(
            db,
            event_type="faction_turn",
            summary=news_headline,
            details=json.loads(details_json) if details_json else None,
            input_tokens=tok_in,
            output_tokens=tok_out,
        )

        # Apply security overlays after API turn too
        try:
            await self._apply_security_overlays(db, session_mgr)
        except Exception:
            pass  # Non-critical

        return True

    async def _apply_faction_order(
        self, db, session_mgr,
        faction_code: str, action: str, order: dict,
    ) -> None:
        """
        Execute one Director faction_order.

        Handles: promote, warn, probation, expel, pardon,
                 post_mission, faction_announcement.
        All state changes are logged to faction_log.
        Invalid targets are silently skipped.
        """
        from server import ansi
        from server.channels import get_channel_manager

        org = await db.get_organization(faction_code)
        if not org:
            return

        reason  = str(order.get("reason", "Director directive"))[:200]
        message = str(order.get("message", ""))[:300]

        # ── promote ────────────────────────────────────────────────────────
        if action == "promote":
            char_id  = order.get("target_char_id")
            new_rank = order.get("new_rank")
            if not char_id:
                return
            rows = await db._db.execute_fetchall(
                "SELECT id, name FROM characters WHERE id = ?", (int(char_id),)
            )
            if not rows:
                return
            char_row = dict(rows[0])
            mem = await db.get_membership(char_row["id"], org["id"])
            if not mem:
                return
            # Validate: cannot skip more than 1 rank
            current = mem["rank_level"]
            target  = new_rank if new_rank else current + 1
            if target > current + 1:
                log.debug("[director] promote skipped: rank skip %d→%d", current, target)
                return
            await db.update_membership(char_row["id"], org["id"], rank_level=target)
            await db.log_faction_action(
                char_row["id"], org["id"], "promote",
                f"Promoted to rank {target} by Director. {reason}"
            )
            # Notify the PC if online
            sess = session_mgr.find_by_character(char_row["id"])
            if sess:
                await sess.send_line(
                    f"  {ansi.color('[FACTION]', ansi.BRIGHT_CYAN)} "
                    f"You have been promoted to rank {target} in {org['name']}. "
                    f"{reason}"
                )
            log.info("[director] Promoted char %d to rank %d in %s",
                     char_row["id"], target, faction_code)

        # ── warn ───────────────────────────────────────────────────────────
        elif action == "warn":
            char_id = order.get("target_char_id")
            if not char_id:
                return
            await db.log_faction_action(
                int(char_id), org["id"], "warn", reason
            )
            sess = session_mgr.find_by_character(int(char_id))
            if sess:
                await sess.send_line(
                    f"  {ansi.color('[FACTION WARNING]', ansi.BRIGHT_YELLOW)} "
                    f"{org['name']}: {reason}"
                )

        # ── probation ──────────────────────────────────────────────────────
        elif action == "probation":
            char_id = order.get("target_char_id")
            if not char_id:
                return
            await db.update_member_standing(int(char_id), org["id"], "probation")
            await db.log_faction_action(
                int(char_id), org["id"], "probation", reason
            )
            sess = session_mgr.find_by_character(int(char_id))
            if sess:
                await sess.send_line(
                    f"  {ansi.color('[FACTION]', ansi.BRIGHT_RED)} "
                    f"You have been placed on probation in {org['name']}. {reason}"
                )

        # ── expel ──────────────────────────────────────────────────────────
        elif action == "expel":
            char_id = order.get("target_char_id")
            if not char_id:
                return
            await db.update_member_standing(int(char_id), org["id"], "expelled")
            await db.log_faction_action(
                int(char_id), org["id"], "expel", reason
            )
            sess = session_mgr.find_by_character(int(char_id))
            if sess:
                await sess.send_line(
                    f"  {ansi.color('[FACTION]', ansi.BRIGHT_RED)} "
                    f"You have been expelled from {org['name']}. {reason}"
                )

        # ── pardon ─────────────────────────────────────────────────────────
        elif action == "pardon":
            char_id = order.get("target_char_id")
            if not char_id:
                return
            await db.update_member_standing(int(char_id), org["id"], "good")
            await db.log_faction_action(
                int(char_id), org["id"], "pardon", reason
            )
            sess = session_mgr.find_by_character(int(char_id))
            if sess:
                await sess.send_line(
                    f"  {ansi.color('[FACTION]', ansi.BRIGHT_GREEN)} "
                    f"Your probation in {org['name']} has been lifted. {reason}"
                )

        # ── post_mission ───────────────────────────────────────────────────
        elif action == "post_mission":
            mission_type = order.get("mission_type", "patrol")
            zone         = str(order.get("zone", ""))[:60]
            reward       = max(100, min(5000, int(order.get("reward", 500))))
            desc         = str(order.get("description", ""))[:200]
            title        = f"{faction_code.title()} Directive: {mission_type.title()}"
            if zone:
                title += f" ({zone})"
            mission_id = await db.post_faction_mission(
                faction_code,
                mission_type=mission_type,
                title=title,
                description=desc,
                reward=reward,
                difficulty="moderate",
                skill_required="",
            )
            await db.log_faction_action(
                None, org["id"], "post_mission",
                f"Posted mission #{mission_id}: {title} ({reward}cr)"
            )
            log.info("[director] Posted faction mission #%d for %s",
                     mission_id, faction_code)

        # ── faction_announcement ───────────────────────────────────────────
        elif action == "faction_announcement":
            if not message:
                return
            try:
                cm = get_channel_manager()
                sender = f"{org['name']} Command"
                await cm.broadcast_fcomm(session_mgr, sender, faction_code, message)
            except Exception as exc:
                log.warning("[director] faction_announcement failed: %s", exc)

    async def _deliver_pc_hook(
        self, db, session_mgr,
        char_id: int, content: str,
        delivery: str, hook_type: str,
    ) -> None:
        """
        Deliver a Director-generated story hook to a specific online PC.

        delivery options:
          comlink_message  — private IC message to the player's session
          npc_whisper      — if PC is in a room with any NPC, that NPC
                             delivers it; otherwise downgrades to comlink
          news_item        — broadcast to all via world_events news channel
          ambient          — injected into the ambient pool for the PC's zone
        """
        from server import ansi

        # Validate content — no raw game commands, no player names
        BAD_WORDS = frozenset({"roll ", "attack ", "/attack", "skill check"})
        if any(bw in content.lower() for bw in BAD_WORDS):
            log.debug("[director] pc_hook content rejected (bad words): %.80s", content)
            return

        # Find the target session (must be online)
        sess = session_mgr.find_by_character(char_id)

        # ── comlink_message ────────────────────────────────────────────────
        if delivery == "comlink_message" or sess is None:
            if sess is None:
                log.debug("[director] pc_hook char %d offline — dropped.", char_id)
                return
            prefix = ansi.color("[COMLINK] ", ansi.BRIGHT_CYAN)
            await sess.send_line(f"{prefix}{content}")
            return

        # ── npc_whisper ───────────────────────────────────────────────────
        if delivery == "npc_whisper":
            char = getattr(sess, "character", None)
            room_id = char.get("room_id") if char else None
            whispered = False
            if room_id:
                try:
                    npcs = await db.get_npcs_in_room(room_id)
                    if npcs:
                        npc = npcs[0]
                        prefix = ansi.color(
                            f"{npc['name']} whispers to you: ", ansi.BRIGHT_YELLOW
                        )
                        await sess.send_line(f"{prefix}\"{content}\"")
                        whispered = True
                except Exception:
                    log.warning("_deliver_pc_hook: unhandled exception", exc_info=True)
                    pass
            if not whispered:
                # Downgrade to comlink
                prefix = ansi.color("[COMLINK] ", ansi.BRIGHT_CYAN)
                await sess.send_line(f"{prefix}{content}")
            return

        # ── news_item ─────────────────────────────────────────────────────
        if delivery == "news_item":
            try:
                from engine.world_events import get_world_event_manager
                wem = get_world_event_manager()
                await wem.broadcast_news(db, session_mgr, content, source="director")
            except Exception as exc:
                log.debug("[director] news_item fallback to comlink: %s", exc)
                if sess:
                    prefix = ansi.color("[COMLINK] ", ansi.BRIGHT_CYAN)
                    await sess.send_line(f"{prefix}{content}")
            return

        # ── ambient ───────────────────────────────────────────────────────
        if delivery == "ambient":
            try:
                from engine.ambient_events import get_ambient_manager
                get_ambient_manager().inject_once(content)
            except Exception as exc:
                log.debug("[director] ambient fallback to comlink: %s", exc)
                if sess:
                    prefix = ansi.color("[COMLINK] ", ansi.BRIGHT_CYAN)
                    await sess.send_line(f"{prefix}{content}")

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
            log.warning("get_recent_log: unhandled exception", exc_info=True)
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
            log.warning("get_budget_stats: unhandled exception", exc_info=True)
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

        # Attempt API-driven Faction Turn first
        try:
            _ai_mgr = getattr(session_mgr, '_ai_manager', None)
            if _ai_mgr and await self._run_api_turn(db, session_mgr, _ai_mgr):
                self._digest.reset()
                self._last_turn_time = time.time()
                return  # API turn handled everything
        except Exception as _api_exc:
            log.warning('[director] API turn error: %s — using local fallback', _api_exc)

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
            details=await self.compile_digest(session_mgr),
        )

        # Reset digest for next cycle
        self._digest.reset()
        self._last_turn_time = time.time()

        log.info("[director] Faction Turn complete: %s", headline)

        # ── Apply security zone overlays based on influence ──────────────
        try:
            await self._apply_security_overlays(db, session_mgr)
        except Exception as _sec_exc:
            log.warning("[director] Security overlay update failed: %s", _sec_exc)

        # Broadcast headline to web clients as news_event
        try:
            import json as _json
            for _s in session_mgr.all:
                if (_s.is_in_game and hasattr(_s, 'protocol')
                        and _s.protocol.value == 'websocket'):
                    await _s._send(_json.dumps({
                        "type": "news_event",
                        "tag": "event",
                        "text": headline,
                    }))
        except Exception:
            pass  # Non-critical — news just won't appear in feed

    # ── Dynamic security overlays (design doc §6) ───────────────────────

    # Maps Director zone keys to DB zone name substrings for matching.
    # Director tracks 6 Mos Eisley zones; outer planets retain their
    # base security level (no Director influence tracking yet).
    _DIRECTOR_ZONE_TO_DB_NAME = {
        "spaceport":  "Spaceport",
        "streets":    "Streets",     # matches "Streets & Markets"
        "cantina":    "Cantina",     # matches "Chalmun's Cantina"
        "shops":      "Commercial",  # matches "Residential & Commercial"
        "jabba":      "Civic",       # Jabba's + Government share civic zone
        "government": "Civic",
    }

    # Base security for each Director zone (matches build_mos_eisley.py)
    _BASE_SECURITY = {
        "spaceport":  "secured",
        "streets":    "secured",
        "cantina":    "secured",
        "shops":      "secured",
        "jabba":      "secured",     # but has faction_override: hutt
        "government": "secured",
    }

    async def _apply_security_overlays(self, db, session_mgr) -> int:
        """
        Apply transient security overrides based on Director zone influence.

        Rules (from security_zones_design_v1.md §6):
          - Criminal influence ≥ 80: downgrade one tier
              secured → contested, contested → lawless
          - Imperial crackdown event active: upgrade contested → secured
          - Imperial influence < 30 (LAX alert): downgrade secured → contested

        Overlay is transient (in-memory via set_security_override).
        Cleared and recomputed each faction turn.

        Returns count of zones that had their security shifted.
        """
        from engine.security import SecurityLevel, set_security_override

        # Load all DB zones for name→id mapping
        all_zones = await db.get_all_zones()
        # Build a lookup: lowercase zone name → zone_id
        zone_name_to_id: dict[str, int] = {}
        for z in all_zones:
            zone_name_to_id[z["name"].lower()] = z["id"]

        # Check for active Imperial crackdown events
        crackdown_zones: set[str] = set()
        try:
            from engine.world_events import get_world_event_manager, EventType
            wem = get_world_event_manager()
            for evt in wem.active_events:
                if evt.event_type == EventType.IMPERIAL_CRACKDOWN:
                    crackdown_zones.update(evt.zones_affected)
        except Exception:
            log.warning("_apply_security_overlays: unhandled exception", exc_info=True)
            pass

        changes = 0

        for dir_zone_key, zs in self._zones.items():
            # Find the DB zone ID(s) that match this Director zone
            db_name_substr = self._DIRECTOR_ZONE_TO_DB_NAME.get(dir_zone_key, "")
            if not db_name_substr:
                continue

            # Find all DB zones whose name contains the substring
            matched_zone_ids = [
                zid for zname, zid in zone_name_to_id.items()
                if db_name_substr.lower() in zname
            ]
            if not matched_zone_ids:
                continue

            # Determine the base security level
            base_str = self._BASE_SECURITY.get(dir_zone_key, "contested")
            base = SecurityLevel(base_str)

            # Compute effective security from influence
            effective = base

            # Rule 1: Criminal surge (criminal ≥ 80) → downgrade one tier
            if zs.criminal >= 80:
                if effective == SecurityLevel.SECURED:
                    effective = SecurityLevel.CONTESTED
                elif effective == SecurityLevel.CONTESTED:
                    effective = SecurityLevel.LAWLESS

            # Rule 2: Imperial collapse (imperial < 30, LAX) → downgrade one tier
            elif zs.alert_level == AlertLevel.LAX:
                if effective == SecurityLevel.SECURED:
                    effective = SecurityLevel.CONTESTED

            # Rule 3: Imperial crackdown event → upgrade contested to secured
            if dir_zone_key in crackdown_zones:
                if effective == SecurityLevel.CONTESTED:
                    effective = SecurityLevel.SECURED

            # Apply or clear the override on all matched DB zones
            for zid in matched_zone_ids:
                if effective != base:
                    set_security_override(zid, effective)
                    changes += 1
                else:
                    # Clear any previous override — security returns to base
                    set_security_override(zid, None)

        if changes:
            log.info("[director] Applied %d security overlay(s) this turn.", changes)

            # Notify online players about security shifts
            try:
                shifted_names = []
                for dir_zone_key, zs in self._zones.items():
                    base_str = self._BASE_SECURITY.get(dir_zone_key, "contested")
                    base = SecurityLevel(base_str)
                    if zs.criminal >= 80:
                        shifted_names.append(
                            f"{_zone_display(dir_zone_key)} "
                            f"(\033[1;31mdowngraded — criminal surge\033[0m)"
                        )
                    elif zs.alert_level == AlertLevel.LAX:
                        if base == SecurityLevel.SECURED:
                            shifted_names.append(
                                f"{_zone_display(dir_zone_key)} "
                                f"(\033[1;33mdowngraded — weak Imperial presence\033[0m)"
                            )
                if shifted_names and session_mgr:
                    msg = (
                        "\033[1;33m[SECURITY SHIFT]\033[0m "
                        + "; ".join(shifted_names)
                    )
                    for s in session_mgr.all:
                        if s.is_in_game:
                            try:
                                await s.send_line(msg)
                            except Exception:
                                log.warning("_apply_security_overlays: unhandled exception", exc_info=True)
                                pass
            except Exception:
                pass  # Notification is non-critical

        return changes

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

        v22 audit S18: faction_turn is spawned as asyncio.create_task so
        the Claude API roundtrip (up to several seconds) doesn't block the
        entire tick loop.  _last_turn_time is set immediately to prevent
        re-firing while the task is still running.
        """
        if not self._enabled:
            return

        await self.ensure_loaded(db)

        self._tick_counter += 1
        now = time.time()

        # Faction Turn check — spawn as background task, don't await
        if now - self._last_turn_time >= self._turn_interval:
            self._last_turn_time = now  # Set immediately to prevent re-fire
            import asyncio
            asyncio.create_task(self._safe_faction_turn(db, session_mgr))

    async def _safe_faction_turn(self, db, session_mgr):
        """Wrapper for faction_turn that catches and logs all errors."""
        try:
            await self.faction_turn(db, session_mgr)
        except Exception:
            log.exception("[director] Faction Turn failed")

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
