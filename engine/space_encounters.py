# -*- coding: utf-8 -*-
"""
engine/space_encounters.py — Space Encounter Framework
Space Overhaul v3, Drop 1

Provides the core encounter lifecycle: SpaceEncounter dataclass,
EncounterManager singleton, choice presentation to web/telnet clients,
respond/stationact dispatch, cooldown tracking, and deadline expiry.

Specific encounter types (patrol, pirate, distress, etc.) are implemented
in Drop 2+ by registering handler functions with the manager.

Architecture:
  - EncounterManager is a module-level singleton (like SpaceGrid, TrafficManager)
  - Encounters are transient (in-memory, lost on restart — same as SpaceGrid)
  - Each encounter targets a specific player ship in a specific zone
  - Choices are presented via WebSocket JSON (web) or numbered text menu (telnet)
  - The `respond` command resolves the active choice; handler functions process outcomes
  - Encounter handlers are registered as async callables keyed by encounter_type + phase

No DB tables. No schema changes.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

log = logging.getLogger(__name__)


# ── Tuning Constants ─────────────────────────────────────────────────────────

# Per-ship encounter cooldowns (seconds since last encounter of that type)
ENCOUNTER_COOLDOWNS = {
    "patrol":    600,    # 10 minutes
    "pirate":    900,    # 15 minutes
    "hunter":    1800,   # 30 minutes (event-driven, generous cooldown)
    "distress":  600,    # 10 minutes
    "mechanical": 900,   # 15 minutes
    "contact":   600,    # 10 minutes
    "cargo":     900,    # 15 minutes
}
ENCOUNTER_COOLDOWN_ANY = 180  # 3 minutes between ANY encounter on same ship

# Per-zone caps
MAX_ACTIVE_ENCOUNTERS_PER_ZONE = 1

# Default deadline for choice responses (seconds)
DEFAULT_CHOICE_DEADLINE = 60

# Deadline warning thresholds (fraction of deadline remaining)
DEADLINE_WARN_FRACTIONS = [0.50, 0.25, 0.10]


# ── Choice dataclass ─────────────────────────────────────────────────────────

@dataclass
class EncounterChoice:
    """A single choice option presented to the player during an encounter."""
    key: str                     # "comply", "bluff", "run", "hide"
    label: str                   # "Comply", "Bluff", etc.
    description: str             # Full description of what this choice does
    risk: str = "none"           # "none", "low", "medium", "high"
    icon: str = ""               # Icon hint for web client (lucide icon name)
    station_hint: str = ""       # Which crew station should handle this ("pilot", "engineer", etc.)
    skill: str = ""              # Skill used ("con", "space_transports", etc.)
    difficulty: str = ""         # Display difficulty ("Moderate (15)", etc.)


# ── SpaceEncounter dataclass ─────────────────────────────────────────────────

@dataclass
class SpaceEncounter:
    """A structured space event with branching outcomes."""
    id: str                                # unique encounter ID (enc-XXXXXX)
    encounter_type: str                    # "patrol", "pirate", "distress", etc.
    zone_id: str                           # zone where this is happening
    phase: int = 0                         # current phase of the encounter
    state: str = "pending"                 # pending/active/resolved/expired
    npc_ship_id: Optional[int] = None      # traffic ship driving this encounter
    target_ship_id: Optional[int] = None   # player ship involved
    target_bridge_room: Optional[int] = None  # bridge room ID for broadcasting

    # Choice state
    choices: list = field(default_factory=list)  # list of EncounterChoice
    choices_presented: bool = False
    choice_deadline: float = 0.0           # timestamp, 0 = no deadline
    chosen_key: str = ""                   # key of the choice the player made
    deadline_warnings_sent: set = field(default_factory=set)

    # Crew actions (for multi-station encounters)
    crew_actions: dict = field(default_factory=dict)
    # {station: {"action": str, "char_id": int, "result": dict}}

    # Prompt text (shown above choices)
    prompt: str = ""
    # Station that should decide ("any" = anyone on bridge)
    deciding_station: str = "any"

    # Outcome tracking
    outcome: str = ""                      # final outcome key
    rewards: dict = field(default_factory=dict)
    penalties: dict = field(default_factory=dict)

    # Context data (encounter-type-specific, passed to handler)
    context: dict = field(default_factory=dict)

    # Timing
    created_at: float = field(default_factory=time.time)

    def time_remaining(self) -> float:
        """Seconds remaining before deadline, or 0 if no deadline."""
        if self.choice_deadline <= 0:
            return 0
        return max(0, self.choice_deadline - time.time())

    def is_expired(self) -> bool:
        """True if deadline has passed and no choice was made."""
        if self.choice_deadline <= 0:
            return False
        return time.time() >= self.choice_deadline and not self.chosen_key

    def get_choice_by_key(self, key: str) -> Optional[EncounterChoice]:
        """Find a choice by its key string."""
        for c in self.choices:
            if isinstance(c, EncounterChoice) and c.key == key:
                return c
        return None

    def get_choice_by_index(self, index: int) -> Optional[EncounterChoice]:
        """Find a choice by 1-based index number."""
        if 1 <= index <= len(self.choices):
            c = self.choices[index - 1]
            return c if isinstance(c, EncounterChoice) else None
        return None


def _gen_id() -> str:
    return "enc-" + uuid.uuid4().hex[:8]


# ── Encounter Handler Registry ──────────────────────────────────────────────
#
# Encounter types register handler functions that are called when:
#   1. An encounter is created (setup phase — build choices, set prompt)
#   2. A choice is made (resolution phase — apply outcome)
#   3. A deadline expires (timeout phase — apply default outcome)
#
# Handler signature:
#   async def handler(encounter, manager, db, session_mgr, **kwargs) -> None
#
# Handlers are registered as:
#   encounter_manager.register_handler("patrol", "setup", patrol_setup)
#   encounter_manager.register_handler("patrol", "choice_comply", patrol_comply)
#   encounter_manager.register_handler("patrol", "timeout", patrol_timeout)

HandlerFunc = Callable[..., Any]  # async callable


# ── EncounterManager ─────────────────────────────────────────────────────────

class EncounterManager:
    """
    Central manager for all active space encounters.

    Lifecycle:
      1. create_encounter() — called by traffic system or Director
      2. present_choices() — sends choice panel to player sessions
      3. handle_response() — player selects a choice via 'respond' command
      4. tick() — checks deadlines, sends warnings, expires timed-out encounters
      5. resolve() — called by handler to mark encounter complete

    Encounters are keyed by target_ship_id — one active encounter per player ship.
    """

    def __init__(self):
        # Active encounters: target_ship_id → SpaceEncounter
        self._encounters: dict[int, SpaceEncounter] = {}
        # Per-ship cooldowns: ship_id → {encounter_type: last_time}
        self._cooldowns: dict[int, dict[str, float]] = {}
        # Handler registry: (encounter_type, phase_key) → handler func
        self._handlers: dict[tuple[str, str], HandlerFunc] = {}

    # ── Handler Registration ─────────────────────────────────────────────

    def register_handler(self, encounter_type: str, phase_key: str,
                         handler: HandlerFunc) -> None:
        """Register a handler for an encounter type + phase.

        phase_key examples:
          "setup"           — called on encounter creation
          "choice_<key>"    — called when player chooses <key>
          "timeout"         — called when deadline expires
          "tick"            — called each encounter tick (for ongoing phases)
        """
        self._handlers[(encounter_type, phase_key)] = handler
        log.debug("[encounters] registered handler: %s/%s", encounter_type, phase_key)

    async def _call_handler(self, encounter_type: str, phase_key: str,
                            encounter: SpaceEncounter, db, session_mgr,
                            **kwargs) -> bool:
        """Call a registered handler. Returns True if handler was found."""
        handler = self._handlers.get((encounter_type, phase_key))
        if handler is None:
            return False
        try:
            await handler(encounter, self, db, session_mgr, **kwargs)
        except Exception as e:
            log.error("[encounters] handler %s/%s error: %s",
                      encounter_type, phase_key, e, exc_info=True)
        return True

    # ── Cooldown Management ──────────────────────────────────────────────

    def check_cooldown(self, ship_id: int, encounter_type: str) -> bool:
        """Return True if the ship is clear of cooldown for this encounter type."""
        now = time.time()
        ship_cd = self._cooldowns.get(ship_id, {})

        # Check type-specific cooldown
        type_cd = ENCOUNTER_COOLDOWNS.get(encounter_type, 300)
        last_type = ship_cd.get(encounter_type, 0)
        if now - last_type < type_cd:
            return False

        # Check global any-encounter cooldown
        last_any = ship_cd.get("__any__", 0)
        if now - last_any < ENCOUNTER_COOLDOWN_ANY:
            return False

        return True

    def record_cooldown(self, ship_id: int, encounter_type: str) -> None:
        """Record that an encounter just happened on this ship."""
        now = time.time()
        if ship_id not in self._cooldowns:
            self._cooldowns[ship_id] = {}
        self._cooldowns[ship_id][encounter_type] = now
        self._cooldowns[ship_id]["__any__"] = now

    # ── Encounter Lifecycle ──────────────────────────────────────────────

    def get_encounter(self, ship_id: int) -> Optional[SpaceEncounter]:
        """Get the active encounter for a player ship, if any."""
        return self._encounters.get(ship_id)

    def get_encounter_by_id(self, encounter_id: str) -> Optional[SpaceEncounter]:
        """Find an encounter by its ID string."""
        for enc in self._encounters.values():
            if enc.id == encounter_id:
                return enc
        return None

    def get_zone_encounter_count(self, zone_id: str) -> int:
        """Count active encounters in a zone."""
        return sum(1 for e in self._encounters.values()
                   if e.zone_id == zone_id and e.state in ("pending", "active"))

    async def create_encounter(
        self,
        encounter_type: str,
        zone_id: str,
        target_ship_id: int,
        target_bridge_room: int,
        db,
        session_mgr,
        npc_ship_id: int = None,
        context: dict = None,
    ) -> Optional[SpaceEncounter]:
        """Create and initialize a new encounter.

        Returns the encounter on success, None if blocked by cooldown/cap.
        Calls the registered 'setup' handler to populate choices and prompt.
        """
        # Check zone cap
        if self.get_zone_encounter_count(zone_id) >= MAX_ACTIVE_ENCOUNTERS_PER_ZONE:
            log.debug("[encounters] zone %s at encounter cap", zone_id)
            return None

        # Check if ship already has an active encounter
        if target_ship_id in self._encounters:
            log.debug("[encounters] ship %d already in encounter", target_ship_id)
            return None

        # Check cooldown
        if not self.check_cooldown(target_ship_id, encounter_type):
            log.debug("[encounters] ship %d on cooldown for %s",
                      target_ship_id, encounter_type)
            return None

        enc = SpaceEncounter(
            id=_gen_id(),
            encounter_type=encounter_type,
            zone_id=zone_id,
            target_ship_id=target_ship_id,
            target_bridge_room=target_bridge_room,
            npc_ship_id=npc_ship_id,
            context=context or {},
            state="pending",
        )

        # Call setup handler to populate choices, prompt, deadline
        found = await self._call_handler(encounter_type, "setup", enc, db, session_mgr)
        if not found:
            log.warning("[encounters] no setup handler for type '%s'", encounter_type)
            return None

        # If setup didn't set a deadline, use default
        if enc.choice_deadline <= 0 and enc.choices:
            enc.choice_deadline = time.time() + DEFAULT_CHOICE_DEADLINE

        self._encounters[target_ship_id] = enc
        enc.state = "active"
        self.record_cooldown(target_ship_id, encounter_type)

        log.info("[encounters] created %s encounter %s for ship %d in %s",
                 encounter_type, enc.id, target_ship_id, zone_id)

        # Present choices to the bridge crew
        if enc.choices:
            await self.present_choices(enc, db, session_mgr)

        return enc

    async def present_choices(self, enc: SpaceEncounter, db, session_mgr) -> None:
        """Send the choice panel to all sessions on the ship's bridge."""
        if not enc.target_bridge_room:
            return

        enc.choices_presented = True

        # Build choice data for WebSocket payload
        choice_data = []
        for i, c in enumerate(enc.choices):
            if not isinstance(c, EncounterChoice):
                continue
            choice_data.append({
                "key": c.key,
                "label": c.label,
                "description": c.description,
                "risk": c.risk,
                "icon": c.icon,
                "station_hint": c.station_hint,
                "skill": c.skill,
                "difficulty": c.difficulty,
                "index": i + 1,
            })

        deadline_secs = int(enc.time_remaining()) if enc.choice_deadline > 0 else 0

        # Send to web clients
        payload = {
            "type": "space_choices",
            "encounter_id": enc.id,
            "encounter_type": enc.encounter_type,
            "prompt": enc.prompt,
            "station": enc.deciding_station,
            "deadline_secs": deadline_secs,
            "choices": choice_data,
        }

        # Send to all sessions on the bridge
        try:
            sessions = session_mgr.sessions_in_room(enc.target_bridge_room)
            if sessions:
                for sess in sessions:
                    # Web client: send JSON choice panel
                    await sess.send_json("space_choices", payload)

                    # Telnet: send numbered text menu
                    await self._send_telnet_choices(sess, enc, deadline_secs)
        except Exception as e:
            log.warning("[encounters] present_choices error: %s", e, exc_info=True)

    async def _send_telnet_choices(self, session, enc: SpaceEncounter,
                                   deadline_secs: int) -> None:
        """Send a numbered text menu to a telnet/any session."""
        try:
            from server import ansi
        except ImportError:
            ansi = None

        AMBER = "\033[1;33m"
        CYAN = "\033[0;36m"
        DIM = "\033[2m"
        GREEN = "\033[1;32m"
        RED = "\033[1;31m"
        RST = "\033[0m"

        risk_colors = {"none": GREEN, "low": GREEN, "medium": AMBER, "high": RED}

        lines = [f"\n  {AMBER}{enc.prompt}{RST}", ""]

        for i, c in enumerate(enc.choices):
            if not isinstance(c, EncounterChoice):
                continue
            idx = i + 1
            risk_col = risk_colors.get(c.risk, DIM)
            skill_note = f" ({c.skill}, {c.difficulty})" if c.skill else ""
            lines.append(
                f"    {CYAN}{idx}){RST} {c.label}"
                f" {DIM}—{RST} {c.description}{risk_col}{skill_note}{RST}"
            )

        lines.append("")
        lines.append(f"  {DIM}Type: respond <number> or respond <choice>{RST}")
        if deadline_secs > 0:
            lines.append(
                f"  {AMBER}You have {deadline_secs} seconds to decide.{RST}"
            )
        lines.append("")

        await session.send_line("\n".join(lines))

    async def handle_response(self, ship_id: int, choice_input: str,
                              session, db, session_mgr) -> bool:
        """Process a player's response to an active encounter.

        choice_input: either a number ("2") or a key ("bluff")
        Returns True if the response was handled.
        """
        enc = self._encounters.get(ship_id)
        if enc is None:
            return False

        if enc.state != "active" or not enc.choices:
            return False

        # Already responded
        if enc.chosen_key:
            await session.send_line("  You've already responded to this encounter.")
            return True

        # Resolve choice by number or key
        choice = None
        try:
            idx = int(choice_input)
            choice = enc.get_choice_by_index(idx)
        except ValueError:
            choice = enc.get_choice_by_key(choice_input.lower())

        if choice is None:
            await session.send_line(
                f"  Invalid choice: '{choice_input}'. "
                f"Use a number (1-{len(enc.choices)}) or a choice name."
            )
            return True

        enc.chosen_key = choice.key
        char_id = session.character["id"] if session.character else 0

        log.info("[encounters] ship %d chose '%s' for %s encounter %s (char %d)",
                 ship_id, choice.key, enc.encounter_type, enc.id, char_id)

        # Call the choice handler
        phase_key = f"choice_{choice.key}"
        found = await self._call_handler(
            enc.encounter_type, phase_key, enc, db, session_mgr,
            session=session, choice=choice, char_id=char_id,
        )

        if not found:
            log.warning("[encounters] no handler for %s/%s",
                        enc.encounter_type, phase_key)
            await session.send_line(f"  You chose: {choice.label}.")
            self.resolve(enc, outcome=choice.key)

        # Dismiss the choice panel on web clients
        await self._dismiss_choices(enc, session_mgr)

        return True

    async def handle_timeout(self, enc: SpaceEncounter, db, session_mgr) -> None:
        """Handle an encounter that timed out without a response."""
        log.info("[encounters] encounter %s timed out (type=%s, ship=%d)",
                 enc.id, enc.encounter_type, enc.target_ship_id)

        found = await self._call_handler(
            enc.encounter_type, "timeout", enc, db, session_mgr,
        )

        if not found:
            # Default timeout behavior: just expire silently
            self.resolve(enc, outcome="timeout")

        await self._dismiss_choices(enc, session_mgr)

    async def _dismiss_choices(self, enc: SpaceEncounter, session_mgr) -> None:
        """Send a dismiss signal to web clients to remove the choice panel."""
        if not enc.target_bridge_room:
            return
        try:
            sessions = session_mgr.sessions_in_room(enc.target_bridge_room)
            if sessions:
                for sess in sessions:
                    await sess.send_json("space_choices_dismiss", {
                        "encounter_id": enc.id,
                    })
        except Exception as e:
            log.warning("[encounters] dismiss error: %s", e, exc_info=True)

    def resolve(self, enc: SpaceEncounter, outcome: str = "") -> None:
        """Mark an encounter as resolved and remove it from active tracking."""
        enc.state = "resolved"
        enc.outcome = outcome
        self._encounters.pop(enc.target_ship_id, None)
        log.info("[encounters] resolved %s encounter %s → %s",
                 enc.encounter_type, enc.id, outcome)

    # ── Tick ─────────────────────────────────────────────────────────────

    async def tick(self, db, session_mgr) -> None:
        """Called every tick from the game loop. Checks deadlines and warnings."""
        to_timeout = []

        for ship_id, enc in list(self._encounters.items()):
            if enc.state != "active":
                continue

            # Check deadline expiry
            if enc.is_expired():
                to_timeout.append(enc)
                continue

            # Send deadline warnings
            if enc.choice_deadline > 0 and not enc.chosen_key:
                remaining = enc.time_remaining()
                total = enc.choice_deadline - enc.created_at
                if total > 0:
                    frac = remaining / total
                    for warn_frac in DEADLINE_WARN_FRACTIONS:
                        if frac <= warn_frac and warn_frac not in enc.deadline_warnings_sent:
                            enc.deadline_warnings_sent.add(warn_frac)
                            secs = int(remaining)
                            if secs > 0 and enc.target_bridge_room:
                                await self._send_deadline_warning(
                                    enc, secs, session_mgr)

            # Call per-tick handler if registered (for ongoing encounter phases)
            if enc.chosen_key:
                await self._call_handler(
                    enc.encounter_type, "tick", enc, db, session_mgr,
                )

        for enc in to_timeout:
            await self.handle_timeout(enc, db, session_mgr)

    async def _send_deadline_warning(self, enc: SpaceEncounter,
                                     secs_remaining: int,
                                     session_mgr) -> None:
        """Broadcast a deadline warning to the bridge."""
        AMBER = "\033[1;33m"
        RST = "\033[0m"
        msg = f"  {AMBER}[WARNING] {secs_remaining} seconds remaining to respond.{RST}"

        try:
            sessions = session_mgr.sessions_in_room(enc.target_bridge_room)
            if sessions:
                for sess in sessions:
                    await sess.send_line(msg)
                    # Also send countdown update to web clients
                    await sess.send_json("space_choices_countdown", {
                        "encounter_id": enc.id,
                        "seconds_remaining": secs_remaining,
                    })
        except Exception as e:
            log.warning("[encounters] deadline warning error: %s", e, exc_info=True)

    # ── Broadcast helper ─────────────────────────────────────────────────

    async def broadcast_to_bridge(self, enc: SpaceEncounter,
                                  message: str, session_mgr) -> None:
        """Send a text message to all sessions on the encounter's bridge."""
        if not enc.target_bridge_room:
            return
        try:
            await session_mgr.broadcast_to_room(enc.target_bridge_room, message)
        except Exception as e:
            log.warning("[encounters] broadcast error: %s", e, exc_info=True)


# ── Module-level singleton ───────────────────────────────────────────────────

_encounter_manager: Optional[EncounterManager] = None


def get_encounter_manager() -> EncounterManager:
    """Get or create the global EncounterManager singleton."""
    global _encounter_manager
    if _encounter_manager is None:
        _encounter_manager = EncounterManager()
    return _encounter_manager
