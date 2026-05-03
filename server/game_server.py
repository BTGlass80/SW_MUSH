# -*- coding: utf-8 -*-
"""
GameServer - the central orchestrator.

Ties together the networking layer (Telnet + WebSocket), session management,
command parsing, and database. Handles the login flow and main input loop.
"""
import asyncio
import logging
from typing import Optional

from server.config import Config
from server.session import Session, SessionState, SessionManager, Protocol
from server.telnet_handler import TelnetHandler
from server.web_client import WebClient
from server import ansi
from server.tick_scheduler import TickScheduler, TickContext
from server.tick_handlers_ships import (
    ion_and_tractor_tick,
    sublight_transit_tick,
    asteroid_collision_tick,
    hyperspace_arrival_tick,
    space_anomaly_tick,
)
from server.tick_handlers_economy import (
    npc_space_crew_tick,
    npc_space_traffic_tick,
    space_mission_patrol_tick,
    board_housekeeping_tick,
    ambient_events_tick,
    world_events_tick,
    director_tick,
    cp_engine_tick,
    crew_wages_tick,
    faction_payroll_tick,
    vendor_recall_tick,
    housing_rent_tick,
    hq_maintenance_tick,
    debt_payment_tick,
    territory_presence_tick,
    territory_decay_tick,
    territory_claim_tick,
    territory_resources_tick,
    territory_contests_tick,
    docking_fee_tick,
    idle_queue_tick,
    bark_seed_tick,
    buff_expiry_tick,
    hazard_tick,
)
from server.tick_handlers_progression import (
    playtime_heartbeat_tick,
    force_sign_emit_tick,
)
# ── S40 boarding party encounter wiring ────────────────────────────────────
# ``boarding_encounter_tick`` is the periodic check; it takes (db, session_mgr)
# rather than the standard TickContext so we wrap it below for the scheduler.
# ``boarding_party_startup_cleanup`` runs once at boot to clear stale boarding
# state left over from an unclean shutdown.
from engine.encounter_boarding import (
    boarding_encounter_tick as _boarding_encounter_tick_impl,
    boarding_party_startup_cleanup,
)


async def boarding_encounter_tick(ctx: "TickContext") -> None:
    """TickContext adapter for ``engine.encounter_boarding.boarding_encounter_tick``.

    The engine handler predates the scheduler and takes positional ``db`` and
    ``session_mgr`` arguments; wrap it so the scheduler can dispatch with a
    ``TickContext`` like every other handler.
    """
    await _boarding_encounter_tick_impl(ctx.db, ctx.session_mgr)
from parser.commands import CommandRegistry, CommandParser, CommandContext
from parser.builtin_commands import register_all
from parser.d6_commands import register_d6_commands
from parser.building_commands import register_building_commands
from parser.building_tier2 import register_building_tier2
from parser.combat_commands import register_combat_commands
from parser.force_commands import register_force_commands
from parser.npc_commands import register_npc_commands
from parser.space_commands import register_space_commands
from parser.crew_commands import register_crew_commands
from parser.mission_commands import register_mission_commands
from parser.bounty_commands import register_bounty_commands
from parser.director_commands import register_director_commands
from parser.news_commands import register_news_commands
from parser.smuggling_commands import register_smuggling_commands
from parser.medical_commands import register_medical_commands
from parser.entertainer_commands import register_entertainer_commands
from parser.cp_commands import register_cp_commands
from parser.sabacc_commands import register_sabacc_commands
from parser.crafting_commands import register_crafting_commands
from parser.tutorial_commands import register_tutorial_commands
from parser.faction_commands import register_faction_commands
from parser.faction_leader_commands import register_faction_leader_commands
from parser.narrative_commands import register_narrative_commands
from parser.shop_commands import register_shop_commands
from parser.housing_commands import register_housing_commands
from parser.spacer_quest_commands import register_spacer_quest_commands
from parser.mux_commands import register_mux_commands
from parser.places_commands import register_places_commands
from parser.attr_commands import register_attr_commands
from parser.char_commands import register_char_commands
from parser.scene_commands import register_scene_commands
from parser.espionage_commands import register_espionage_commands
from parser.achievement_commands import register_achievement_commands
from parser.event_commands import register_event_commands
from parser.plot_commands import register_plot_commands
from parser.mail_commands import register_mail_commands
from parser.channel_commands import register_channel_commands
from parser.party_commands import register_party_commands
from parser.encounter_commands import register_encounter_commands
from engine.space_encounters import get_encounter_manager
from engine.bounty_board import get_bounty_board
from engine.missions import get_mission_board
from engine.smuggling import get_smuggling_board
from engine.party import get_party_manager
from engine.ambient_events import get_ambient_manager
from engine.world_events import get_world_event_manager
from engine.director import get_director
from engine.npc_space_traffic import get_traffic_manager
from engine.npc_space_combat_ai import get_npc_combat_manager
from engine.starships import get_space_grid, get_ship_registry
from engine.weapons import get_weapon_registry
from ai.providers import AIManager, AIConfig
from db.database import Database
from engine.species import SpeciesRegistry
from engine.character import SkillRegistry, Character
from engine.tutorial import TutorialManager
from engine.creation import CreationEngine
from engine.creation_wizard import CreationWizard

log = logging.getLogger(__name__)


class GameServer:
    """
    The main game server. Start this and everything else comes up.
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.db = Database(self.config.db_path)
        self.session_mgr = SessionManager()

        # Game data registries
        self.species_reg = SpeciesRegistry()
        self.skill_reg = SkillRegistry()

        # Command system
        self.registry = CommandRegistry()
        register_all(self.registry)
        register_d6_commands(self.registry)
        register_building_commands(self.registry)
        register_building_tier2(self.registry)
        register_combat_commands(self.registry)
        register_npc_commands(self.registry)
        register_space_commands(self.registry)
        register_crew_commands(self.registry)
        register_mission_commands(self.registry)
        register_bounty_commands(self.registry)
        register_director_commands(self.registry)
        register_news_commands(self.registry)
        register_smuggling_commands(self.registry)
        register_force_commands(self.registry)
        register_medical_commands(self.registry)
        register_entertainer_commands(self.registry)
        register_cp_commands(self.registry)
        register_sabacc_commands(self.registry)
        register_crafting_commands(self.registry)
        register_tutorial_commands(self.registry)
        register_faction_commands(self.registry)
        register_faction_leader_commands(self.registry)
        register_narrative_commands(self.registry)
        register_shop_commands(self.registry)
        register_housing_commands(self.registry)
        register_spacer_quest_commands(self.registry)
        register_mux_commands(self.registry)
        register_places_commands(self.registry)
        register_attr_commands(self.registry)
        register_char_commands(self.registry)
        register_scene_commands(self.registry)
        register_mail_commands(self.registry)
        register_espionage_commands(self.registry)
        register_achievement_commands(self.registry)
        register_event_commands(self.registry)
        register_plot_commands(self.registry)
        register_channel_commands(self.registry)
        register_party_commands(self.registry)
        register_encounter_commands(self.registry)

        # ── Achievement System Init ──
        from engine.achievements import load_achievements
        _ach_count = load_achievements()
        log.info("Loaded %d achievements", _ach_count)

        # ── Help System Init ──
        from data.help_topics import HelpManager
        help_mgr = HelpManager()
        help_mgr.auto_register_commands(self.registry)
        help_mgr.register_topics()
        from parser.builtin_commands import HelpCommand
        HelpCommand._help_mgr = help_mgr
        # Bind to the GameServer instance so the web portal's
        # /api/portal/reference handler can resolve it via getattr(self._game,
        # "help_mgr", None). Without this, the handler returns 503 and the
        # portal Reference page spins forever.
        self.help_mgr = help_mgr
        log.info("Help system initialized: %d entries",
                 len(help_mgr._entries))

        # AI system
        self.ai_manager = AIManager(AIConfig())
        # Attach to session_mgr so commands can reach it
        self.session_mgr._ai_manager = self.ai_manager

        # Ollama idle queue — GPU utilization for ambient barks, scene summaries
        from engine.idle_queue import IdleQueue
        self._idle_queue = IdleQueue(self.ai_manager)
        self.session_mgr._idle_queue = self._idle_queue
        self.ai_manager._idle_queue = self._idle_queue

        self.parser = CommandParser(self.registry, self.db, self.session_mgr)

        # Protocol handlers
        self.telnet = TelnetHandler(self)
        self.web_client = WebClient()
        self.web_client.set_game(self)


        # Tutorial system
        self.tutorial = TutorialManager()

        # ── Singleton manager bindings (cw_preflight_checklist §A.2) ─────
        # These expose engine singletons on the GameServer instance so
        # the portal (web_portal.py) can access them via
        # `getattr(self._game, "encounter_mgr", None)` etc. Without
        # these, portal routes 503 on unbound singletons.

        self.encounter_mgr   = get_encounter_manager()
        self.bounty_board     = get_bounty_board()
        self.mission_board    = get_mission_board()
        self.smuggling_board  = get_smuggling_board()
        self.party_mgr        = get_party_manager()
        self.ambient_mgr      = get_ambient_manager()
        self.world_event_mgr  = get_world_event_manager()
        self.director         = get_director()
        self.traffic_mgr      = get_traffic_manager()
        self.npc_combat_mgr   = get_npc_combat_manager()
        self.space_grid       = get_space_grid()
        self.ship_registry    = get_ship_registry()
        self.weapon_registry  = get_weapon_registry()

        self._running = False
        self._tick_task: Optional[asyncio.Task] = None
        self._tick_count: int = 0  # monotonic tick counter, drives the scheduler

        # ── Tick scheduler (review fix — full migration) ──────────────────────
        # All tick sub-systems are registered here. Intervals are in ticks
        # (1 tick ≈ 1 s). Offsets spread load so nothing piles up at tick 0.
        # Handler isolation: one failing handler never blocks the others.
        # See server/tick_handlers_ships.py and server/tick_handlers_economy.py
        # for implementations.
        from engine.npc_crew import WAGE_TICK_INTERVAL
        self._tick_scheduler = TickScheduler()
        # ── NPC behaviour (every tick, before ship physics) ──
        self._tick_scheduler.register("npc_space_crew",    npc_space_crew_tick,    interval=1)
        self._tick_scheduler.register("npc_space_traffic", npc_space_traffic_tick, interval=1)
        # ── ship physics (every tick) ──
        self._tick_scheduler.register("ion_and_tractor",   ion_and_tractor_tick,   interval=1)
        self._tick_scheduler.register("sublight_transit",  sublight_transit_tick,  interval=1)
        self._tick_scheduler.register("hyperspace_arrival", hyperspace_arrival_tick, interval=1)
        # ── ship hazards (every 30 ticks ≈ 30 s) ──
        self._tick_scheduler.register("asteroid_collision", asteroid_collision_tick, interval=30)
        # ── environment (every 300 ticks ≈ 5 min) ──
        self._tick_scheduler.register("space_anomaly",     space_anomaly_tick,      interval=300)
        # ── missions & boards (every tick) ──
        self._tick_scheduler.register("space_mission_patrol", space_mission_patrol_tick, interval=1)
        self._tick_scheduler.register("board_housekeeping",   board_housekeeping_tick,   interval=60)
        # ── world simulation (every tick) ──
        self._tick_scheduler.register("ambient_events",    ambient_events_tick,    interval=1)
        self._tick_scheduler.register("world_events",      world_events_tick,      interval=1)
        self._tick_scheduler.register("director",          director_tick,          interval=1)
        self._tick_scheduler.register("cp_engine",         cp_engine_tick,         interval=1)
        # ── economy / admin (infrequent, offset to spread load) ──
        self._tick_scheduler.register("crew_wages",        crew_wages_tick,        interval=WAGE_TICK_INTERVAL)
        self._tick_scheduler.register("faction_payroll",   faction_payroll_tick,   interval=86400)
        self._tick_scheduler.register("vendor_recall",     vendor_recall_tick,     interval=86400, offset=1)
        self._tick_scheduler.register("housing_rent",      housing_rent_tick,      interval=604800, offset=432000)
        self._tick_scheduler.register("hq_maintenance",    hq_maintenance_tick,    interval=604800, offset=460000)
        # ── territory (hourly / daily / weekly) ──
        self._tick_scheduler.register("territory_presence",  territory_presence_tick,  interval=3600,   offset=1800)
        self._tick_scheduler.register("territory_decay",     territory_decay_tick,     interval=86400,  offset=43200)
        self._tick_scheduler.register("territory_claim",     territory_claim_tick,     interval=604800, offset=518400)
        self._tick_scheduler.register("debt_payment",        debt_payment_tick,        interval=604800, offset=345600)
        self._tick_scheduler.register("territory_resources", territory_resources_tick, interval=86400,  offset=64800)
        self._tick_scheduler.register("territory_contests",  territory_contests_tick,  interval=3600,   offset=2700)
        self._tick_scheduler.register("docking_fee",         docking_fee_tick,         interval=86400,  offset=21600)
        # ── Ollama idle queue (every 30s, offset 15 to avoid pile-up) ──
        self._tick_scheduler.register("idle_queue",           idle_queue_tick,          interval=30,     offset=15)
        self._tick_scheduler.register("bark_seed",            bark_seed_tick,           interval=14400,  offset=60)
        # ── Buff expiry (every 60s) ──
        self._tick_scheduler.register("buff_expiry",          buff_expiry_tick,         interval=60,     offset=45)
        # ── Environmental hazards (every 5 min) ──
        self._tick_scheduler.register("hazard_check",          hazard_tick,             interval=300,    offset=120)
        # ── S40 boarding encounters: every 5 ticks (~5s) — checks ships
        #    with active boarding parties and resolves defeated boarders.
        self._tick_scheduler.register("boarding_encounters",   boarding_encounter_tick, interval=5,      offset=2)
        # ── PG.3.gates.a (May 2026): playtime heartbeat. Every 60 ticks
        #    (~60s); increments characters.play_time_seconds for every
        #    in-game non-idle session by 60. Foundation of the 50-hour
        #    Force-gate per progression_gates_and_consequences_design_v1.md
        #    §2.3. Idle filter (5min) inside the handler.
        self._tick_scheduler.register("playtime_heartbeat",    playtime_heartbeat_tick, interval=60,     offset=30)
        # ── PG.3.gates.b (May 2026): Force-sign emission. Every 60 ticks
        #    (~60s, offset 45 to spread tick load with playtime_heartbeat
        #    at offset 30). For each post-gate active session, rolls for
        #    a Force-sign emission scaled by predisposition. At 5 signs,
        #    invitation threshold hits and the Hermit-invitation flow
        #    becomes eligible (future Village quest engine consumes that
        #    signal). Per progression_gates_and_consequences_design_v1.md
        #    §2.3 / §2.4.
        self._tick_scheduler.register("force_sign_emit",       force_sign_emit_tick,    interval=60,     offset=45)

    async def start(self):
        """Initialize database, load game data, and start all listeners."""
        log.info("Starting %s...", self.config.game_name)

        # Database
        await self.db.connect()
        await self.db.initialize()

        # Seed organizations (factions + guilds) — idempotent
        try:
            from engine.organizations import seed_organizations
            await seed_organizations(self.db, era=self.config.active_era)
        except Exception as _org_err:
            log.warning("Organization seed skipped: %s", _org_err)

        # Load game data
        import os
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.species_reg.load_directory(os.path.join(data_dir, "species"))
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            self.skill_reg.load_file(skills_path)
        log.info("Game data loaded: %d species, %d skills",
                 self.species_reg.count, self.skill_reg.count)

        # Auto-build world if only seed rooms exist
        built = False
        try:
            from build_mos_eisley import auto_build_if_needed
            built = await auto_build_if_needed(self.config.db_path,
                                               era=self.config.active_era)
            if built:
                log.info("World auto-build completed successfully (era=%s).",
                         self.config.active_era)
        except Exception as _build_err:
            log.warning("World auto-build skipped: %s", _build_err)
        # Housing schema + lot seeding
        try:
            from engine.housing import ensure_schema as _hs_schema, seed_lots as _hs_lots
            await _hs_schema(self.db)
            await _hs_lots(self.db)
        except Exception as _hs_err:
            log.warning("Housing init skipped: %s", _hs_err)

        # Territory control schema
        try:
            from engine.territory import ensure_territory_schema
            await ensure_territory_schema(self.db)
        except Exception as _terr_err:
            log.warning("Territory init skipped: %s", _terr_err)

        # World lore schema + seed data
        try:
            from engine.world_lore import ensure_lore_schema, seed_lore
            from engine.era_state import get_seeding_era
            await ensure_lore_schema(self.db)
            # F.6a.7 Phase 1 (Apr 29 2026): pass the active era so GCW
            # production boot routes through data/worlds/gcw/lore.yaml
            # instead of the legacy hardcoded SEED_ENTRIES list. The
            # seed_lore() era=None branch falls back to SEED_ENTRIES if
            # YAML load fails for any reason, so this remains safe.
            _lore_seeded = await seed_lore(self.db, era=get_seeding_era())
            if _lore_seeded:
                log.info("World lore: seeded %d entries", _lore_seeded)
        except Exception as _lore_err:
            log.warning("World lore init skipped: %s", _lore_err)

        # ── S40 boarding-party startup cleanup ──────────────────────────
        # Sweep any "boarding_party_active" ships left over from an
        # unclean shutdown so the next session starts with a clean slate.
        # Runs after schemas are ready but before listeners come up so a
        # stale boarder NPC can never be present when players reconnect.
        try:
            cleaned = await boarding_party_startup_cleanup(self.db)
            if cleaned:
                log.info("Boarding startup cleanup: removed %d stale boarders", cleaned)
        except Exception as _bpsc_err:
            log.warning("Boarding startup cleanup skipped: %s", _bpsc_err)

        # Auto-build tutorial zones if not yet present.
        # If the world was just built above, wait 1s to let the DB flush cleanly.
        try:
            from build_tutorial import auto_build_if_needed as tutorial_build_if_needed
            if built:
                await asyncio.sleep(1)
            tbuilt = await tutorial_build_if_needed(self.config.db_path)
            if tbuilt:
                log.info("Tutorial auto-build completed successfully.")
        except Exception as _tbuild_err:
            log.warning("Tutorial auto-build skipped: %s", _tbuild_err)

        # Narrative memory nightly summarization scheduler (03:00 daily).
        try:
            from engine.narrative import schedule_nightly_job
            schedule_nightly_job(self.db, self.session_mgr)
        except Exception as _narr_err:
            log.warning("Narrative scheduler skipped: %s", _narr_err)

        # Network listeners
        await self.telnet.start(self.config.telnet_host, self.config.telnet_port)

        # Web client serves both HTTP (/) and WebSocket (/ws) on one port.
        # The separate websockets-library server (port 4001) is no longer used.
        await self.web_client.start(
            self.config.web_client_host, self.config.web_client_port
        )

        # Background tick (idle checks, NPC updates, etc.)
        self._running = True
        self._tick_task = asyncio.create_task(self._game_tick_loop())

        log.info(
            "%s is running. Telnet:%d  WebClient:%d  (WebSocket at ws://host:%d/ws)",
            self.config.game_name,
            self.config.telnet_port,
            self.config.web_client_port,
            self.config.web_client_port,
        )

    async def stop(self):
        """Gracefully shut down everything."""
        log.info("Shutting down %s...", self.config.game_name)
        self._running = False

        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError as _e:
                log.debug("silent except in server/game_server.py:348: %s", _e, exc_info=True)

        # Disconnect all sessions
        for session in list(self.session_mgr.all):
            try:
                await session.send_line(
                    ansi.system_msg("Server is shutting down. Saving your character...")
                )
                if session.character:
                    await self.db.save_character(
                        session.character["id"],
                        room_id=session.character.get("room_id", 1),
                    )
                await session.close()
            except Exception:
                log.warning("stop: unhandled exception", exc_info=True)
                pass

        await self.telnet.stop()
        await self.web_client.stop()
        await self.db.close()
        log.info("Shutdown complete.")

    # ── Session Handling ──

    async def handle_new_session(self, session: Session, reader=None):
        """
        Entry point for every new connection. Runs the login flow,
        then the main input loop.

        For Telnet: `reader` is the telnetlib3 reader.
        For WebSocket: `reader` is None (input comes via the session queue).
        """
        await session.send(self.config.welcome_banner)
        await session.send_prompt()

        # If Telnet, start a background task to feed input from the reader
        if reader is not None:
            asyncio.create_task(self._telnet_read_loop(reader, session))

        # Login loop
        while session.state == SessionState.CONNECTED:
            try:
                line = await asyncio.wait_for(session.receive(), timeout=300)
            except asyncio.TimeoutError:
                await session.send_line("Connection timed out.")
                await session.close()
                return

            line = line.strip()
            if not line:
                await session.send_prompt()
                continue

            parts = line.split()
            cmd = parts[0].lower()

            # ── Never log raw input during pre-auth (passwords are in plaintext here) ──
            # Only log the command verb, never the full line.

            if cmd == "quit":
                await session.close()
                return

            elif cmd == "__token_auth__" and len(parts) >= 2:
                # Auto-login from web chargen — account already verified
                # by token in web_client.py before this synthetic command
                try:
                    account_id = int(parts[1])
                    account = await self.db.get_account(account_id)
                    if account:
                        existing = self.session_mgr.find_by_account(account["id"])
                        if existing:
                            await existing.close()
                            self.session_mgr.remove(existing)
                        session.account = account
                        session.state = SessionState.AUTHENTICATED
                        await session.send_line(
                            ansi.success(f"Welcome, {account['username']}!")
                        )
                        await self._character_select(session)
                    else:
                        await session.send_prompt()
                except (ValueError, Exception):
                    await session.send_prompt()

            elif cmd == "connect" and len(parts) >= 3:
                username = parts[1]
                password = parts[2]
                account = await self.db.authenticate(username, password)
                if account:
                    # Check for existing session
                    existing = self.session_mgr.find_by_account(account["id"])
                    if existing:
                        await session.send_line(
                            "That account is already connected. Disconnecting old session."
                        )
                        await existing.close()
                        self.session_mgr.remove(existing)

                    session.account = account
                    session.state = SessionState.AUTHENTICATED
                    await session.send_line(
                        ansi.success(f"Welcome back, {username}!")
                    )
                    await self._character_select(session)
                else:
                    await session.send_line(
                        ansi.error("Invalid username or password.")
                    )
                    await session.send_prompt()

            elif cmd == "create" and len(parts) >= 3:
                username = parts[1]
                password = parts[2]

                # Validate
                if len(username) < self.config.min_username_len:
                    await session.send_line(
                        ansi.error(
                            f"Username must be at least {self.config.min_username_len} characters."
                        )
                    )
                    await session.send_prompt()
                    continue

                if len(password) < self.config.min_password_len:
                    await session.send_line(
                        ansi.error(
                            f"Password must be at least {self.config.min_password_len} characters."
                        )
                    )
                    await session.send_prompt()
                    continue

                account_id = await self.db.create_account(username, password)
                if account_id:
                    account = await self.db.authenticate(username, password)
                    session.account = account
                    session.state = SessionState.AUTHENTICATED
                    await session.send_line(
                        ansi.success(f"Account '{username}' created! Welcome to the galaxy.")
                    )
                    await self._character_select(session)
                else:
                    await session.send_line(
                        ansi.error("That username is already taken.")
                    )
                    await session.send_prompt()
            else:
                await session.send_line(
                    "Commands: 'connect <user> <pass>', 'create <user> <pass>', 'quit'"
                )
                await session.send_prompt()

        # ── Main game loop with CHAR_SWITCH support (S44) ──
        # When the player runs `+char/switch <name>`, the CharCommand sets
        # session.state = SessionState.CHAR_SWITCH and the game loop
        # returns. We then save & clear the current character, reset to
        # AUTHENTICATED, and re-enter _character_select so they can pick a
        # new character without disconnecting. Anything other than
        # CHAR_SWITCH falls through and the connection ends normally.
        while True:
            await self._game_loop(session)
            if session.state != SessionState.CHAR_SWITCH:
                break
            # Persist the outgoing character's position so the switched-to
            # body shows up exactly where it logged off.
            try:
                if session.character:
                    await self.db.save_character(
                        session.character["id"],
                        room_id=session.character.get("room_id"),
                    )
            except Exception:
                log.warning("CHAR_SWITCH: failed to save outgoing character",
                            exc_info=True)
            # Drop the character cleanly and re-enter character select.
            session.character = None
            session.invalidate_char_obj()
            session.state = SessionState.AUTHENTICATED
            await self._character_select(session)

    async def _character_select(self, session: Session):
        """
        Character selection or full D6 character creation.
        Supports up to max_characters_per_account alts.
        """
        characters = await self.db.get_characters(session.account["id"])
        max_chars = self.config.max_characters_per_account
        can_create = len(characters) < max_chars

        if not characters:
            # ── First character — go straight to creation ──
            if session.protocol == Protocol.WEBSOCKET:
                char = await self._run_web_chargen(session)
            else:
                char = await self._run_character_creation(session)
            if char is None:
                await session.close()
                return
        elif len(characters) == 1 and not can_create:
            # Single char at cap — just enter
            char = characters[0]
            await session.send_line(
                f"Entering the game as {ansi.player_name(char['name'])}..."
            )
        else:
            # Multiple characters or can create more — show picker
            if session.protocol == Protocol.WEBSOCKET:
                # Web client: send JSON character picker
                char_list = [
                    {"id": c["id"], "name": c["name"], "species": c.get("species", "Human"),
                     "template": c.get("template", "")}
                    for c in characters
                ]
                await session.send_json("char_select", {
                    "characters": char_list,
                    "can_create": can_create,
                    "max_characters": max_chars,
                })
                # Wait for selection
                while True:
                    try:
                        line = await asyncio.wait_for(session.receive(), timeout=300)
                    except asyncio.TimeoutError:
                        await session.send_line("Selection timed out.")
                        await session.close()
                        return
                    line = line.strip()
                    if line.lower() == "quit":
                        await session.close()
                        return
                    if line == "__chargen_done__":
                        # New character created via web chargen
                        characters = await self.db.get_characters(session.account["id"])
                        if characters:
                            char = characters[-1]
                            await session.send_line(
                                ansi.success(f"Welcome to the galaxy, {char['name']}!")
                            )
                            break
                        continue
                    if line.startswith("__char_select__"):
                        try:
                            char_id = int(line.split("__")[-1])
                            char = None
                            for c in characters:
                                if c["id"] == char_id:
                                    char = c
                                    break
                            if char:
                                await session.send_line(
                                    f"Entering the game as {ansi.player_name(char['name'])}..."
                                )
                                break
                        except (ValueError, IndexError) as _e:
                            log.debug("silent except in server/game_server.py:580: %s", _e, exc_info=True)
                    if line == "__request_chargen__" and can_create:
                        # Launch web chargen for new alt
                        from server.api import create_login_token
                        token = create_login_token(session.account["id"], ttl=1800)
                        await session.send_json("chargen_start", {
                            "account_id": session.account["id"],
                            "token": token,
                        })
                        continue
                    # Ignore other input during selection
            else:
                # Telnet: text menu
                await session.send_line("")
                await session.send_line(ansi.header("=== Select a Character ==="))
                for i, c in enumerate(characters, 1):
                    await session.send_line(f"  {i}. {c['name']} ({c['species']})")
                if can_create:
                    await session.send_line(
                        f"  {len(characters) + 1}. \033[92mCreate New Character\033[0m"
                        f" ({len(characters)}/{max_chars})"
                    )
                await session.send_line("")
                await session.send_line("Enter a number:")
                await session.send_prompt()

                choice = await session.receive()
                try:
                    idx = int(choice.strip())
                    if can_create and idx == len(characters) + 1:
                        # Create new character
                        new_char = await self._run_character_creation(session)
                        if new_char is None:
                            await session.close()
                            return
                        char = new_char
                    elif 1 <= idx <= len(characters):
                        char = characters[idx - 1]
                    else:
                        char = characters[0]
                except ValueError:
                    # Try matching by name
                    name_input = choice.strip().lower()
                    char = None
                    for c in characters:
                        if c["name"].lower().startswith(name_input):
                            char = c
                            break
                    if char is None:
                        char = characters[0]

                await session.send_line(
                    f"Entering the game as {ansi.player_name(char['name'])}..."
                )

        # Enter the game
        session.character = char
        session.invalidate_char_obj()  # v22: clear cached Character object
        session.state = SessionState.IN_GAME

        # Push the skill-descriptions catalog to WS clients so the
        # sheet panel's right-rail can render rich tooltips without
        # a per-skill round-trip.  Sent once at session start; cached
        # client-side until reconnect.  Telnet skips this — the catalog
        # only matters to the GUI sheet panel.
        if session.protocol == Protocol.WEBSOCKET:
            try:
                from engine.sheet_renderer import (
                    build_skill_descriptions_payload,
                )
                desc_payload = build_skill_descriptions_payload()
                await session.send_json(
                    "skill_descriptions",
                    {"payload": desc_payload},
                )
            except Exception:
                # Non-critical — the sheet panel falls back to plain
                # skill names if the catalog never arrives.
                pass

        # Announce arrival
        room_id = char.get("room_id", self.config.starting_room_id)

        # Clear sleeping flag and report theft events (Tier 3 Feature #16)
        try:
            from engine.sleeping import clear_sleeping
            theft_events = await clear_sleeping(char, self.db)
            if theft_events:
                await session.send_line(
                    "\n  \033[1;31m⚠ While you were asleep...\033[0m")
                total_stolen = 0
                for evt in theft_events:
                    total_stolen += evt.get("credits_stolen", 0)
                    await session.send_line(
                        f"  \033[0;31m  {evt.get('thief_name', 'Someone')} "
                        f"stole {evt['credits_stolen']:,} credits from you."
                        f"\033[0m")
                await session.send_line(
                    f"  \033[1;31mTotal stolen: {total_stolen:,} credits."
                    f"\033[0m\n"
                    f"  \033[2mRent an apartment in a secured zone to "
                    f"sleep safely.\033[0m\n")
        except Exception:
            pass  # Non-critical

        await self.session_mgr.broadcast_to_room(
            room_id,
            ansi.system_msg(f"{char['name']} has connected."),
            exclude=session,
        )

        # Auto-look
        await session.send_line("")
        look_cmd = self.registry.get("look")
        if look_cmd:
            ctx = CommandContext(
                session=session, raw_input="look", command="look",
                args="", args_list=[], db=self.db,
                session_mgr=self.session_mgr,
            )
            await look_cmd.execute(ctx)

        # Tutorial init: if player is in a tutorial zone, seed state and show
        # Landing Pad guidance immediately (movement hook never fires for spawn room)
        try:
            room_row = await self.db.get_room(room_id)
            if room_row:
                import json as _tj
                rprops = room_row.get("properties", "{}")
                if isinstance(rprops, str):
                    try:
                        rprops = _tj.loads(rprops)
                    except Exception:
                        rprops = {}
                from engine.tutorial_v2 import (
                    is_tutorial_zone, get_tutorial_state, set_tutorial_core,
                    check_core_tutorial_step, start_hint_timer,
                )
                if is_tutorial_zone(rprops):
                    ts = get_tutorial_state(char)
                    if ts["core"] == "not_started":
                        set_tutorial_core(char, "in_progress", step=-1)
                        await self.db.save_character(
                            char["id"], attributes=char.get("attributes", "{}")
                        )
                    # Show immediate guidance for current room (Landing Pad on first login)
                    await check_core_tutorial_step(
                        session, self.db, room_row.get("name", "")
                    )
                    start_hint_timer(session, room_row.get("name", ""))
        except Exception:
            pass  # Non-critical

        # B.5 (Apr 29 2026) — Organization-axis legacy rewicker. Runs
        # FIRST so any subsequent faction_intent_migration sees the
        # rewickered intent (not the stale legacy code). When era=gcw
        # the rewicker map is empty and this is a no-op; behavior is
        # byte-equivalent to pre-B.5 production.
        try:
            from engine.organizations import apply_org_rewicker
            await apply_org_rewicker(char, self.db,
                                      era=self.config.active_era,
                                      session=session)
        except Exception:
            pass  # Non-critical

        # Faction intent migration: auto-join if tutorial stored a faction_intent
        try:
            from engine.organizations import faction_intent_migration
            await faction_intent_migration(char, self.db, session)
        except Exception:
            pass  # Non-critical

        # Notify unread mail on login
        try:
            from parser.mail_commands import notify_unread_mail
            await notify_unread_mail(self.db, session)
        except Exception:
            pass  # Non-critical

        await session.send_prompt()

        # If player is aboard a ship bridge in space, send initial space_state
        # so the radar and zone map populate without requiring a zone transition.
        try:
            from parser.space_commands import broadcast_space_state
            from db.database import Database as _DB
            _login_ship = await self.db.get_ship_by_bridge(char.get("room_id", -1))
            if _login_ship and not _login_ship.get("docked_at"):
                await broadcast_space_state(_login_ship, self.db, self.session_mgr)
        except Exception:
            pass  # Non-critical — ground players have no ship bridge

    async def _run_web_chargen(self, session: Session) -> Optional[dict]:
        """
        Web chargen flow for WebSocket clients.

        Sends a chargen_start message to the client, which shows an
        embedded chargen UI. Waits for a __chargen_done__ signal
        indicating the character has been created via the REST API.
        Returns the DB character dict, or None on timeout/disconnect.
        """
        from server.api import create_login_token

        # Generate a session token so the embedded chargen can create
        # the character under this account via the REST API
        token = create_login_token(session.account["id"], ttl=1800)  # 30 min

        await session.send_json("chargen_start", {
            "account_id": session.account["id"],
            "token": token,
        })

        # Wait for the client to signal completion
        while True:
            try:
                line = await asyncio.wait_for(session.receive(), timeout=1800)
            except asyncio.TimeoutError:
                await session.send_line("Character creation timed out.")
                return None

            line = line.strip()
            if line.lower() == "quit":
                return None

            if line == "__chargen_done__":
                # Character was created via REST API — load it
                characters = await self.db.get_characters(session.account["id"])
                if characters:
                    char = characters[-1]  # Most recently created
                    await session.send_line(
                        ansi.success(f"Welcome to the galaxy, {char['name']}!")
                    )
                    return char
                else:
                    await session.send_line(
                        ansi.error("Character creation failed. Please try again.")
                    )
                    return None

            # Ignore any other input while chargen is active

    async def _run_character_creation(self, session: Session) -> Optional[dict]:
        """
        Run the full interactive character creation flow.
        Returns a DB character dict on success, None on disconnect.
        """
        wizard = CreationWizard(self.species_reg, self.skill_reg, width=session.wrap_width)

        # Show initial screen
        display, prompt = wizard.get_initial_display()
        await session.send_line(display)
        await session.send_prompt(prompt)

        # Creation loop
        while True:
            try:
                line = await asyncio.wait_for(session.receive(), timeout=600)
            except asyncio.TimeoutError:
                await session.send_line("Character creation timed out.")
                return None

            line = line.strip()
            if line.lower() == "quit":
                return None

            # Keep formatter width synced with session (resize messages)
            wizard.fmt.width = max(40, session.width)

            display, prompt, done = wizard.process_input(line)

            if display:
                await session.send_line(display)

            if done:
                break

            if prompt:
                await session.send_prompt(prompt)

        # Build Character object and save to DB
        while True:
            try:
                char_obj = wizard.get_character()

                # ── F.8.c.1 (Apr 30 2026): Tutorial-chain start routing ──
                # CW chargen has an extra step where the player picks a
                # tutorial chain (republic_soldier, smuggler, etc.) or
                # skips. If a chain was selected, the character starts
                # in that chain's starting_room (resolved by slug); if
                # not, we fall through to the legacy GCW Landing Pad
                # logic below. This block runs unconditionally — for
                # GCW the wizard's get_selected_chain_id() returns None
                # because GCW has no chains.yaml.
                tutorial_start_room = self.config.starting_room_id
                chain_starting_slug = None
                try:
                    chain_starting_slug = wizard.get_tutorial_chain_starting_room_slug()
                except AttributeError:
                    # Pre-F.8.c.1 wizards don't expose this method;
                    # treat as "no chain selected" and fall through.
                    chain_starting_slug = None

                if chain_starting_slug:
                    # Resolve the slug to a room_id. F.8.c.1 stores the
                    # slug in the room's properties JSON (see
                    # engine/world_writer.py); we look it up via a
                    # JSON-substring LIKE query. The pattern is
                    # tight enough to avoid false matches because
                    # `"slug": "<slug>"` is unique per room.
                    chain_room_rows = await self.db.fetchall(
                        "SELECT id FROM rooms WHERE properties LIKE ? "
                        "ORDER BY id LIMIT 1",
                        (f'%"slug": "{chain_starting_slug}"%',),
                    )
                    if chain_room_rows:
                        tutorial_start_room = chain_room_rows[0]["id"]
                        log.info(
                            "[F.8.c.1] Routing %s to tutorial chain starting "
                            "room %s (id=%d)",
                            char_obj.name, chain_starting_slug,
                            tutorial_start_room,
                        )
                    else:
                        log.warning(
                            "[F.8.c.1] Tutorial chain starting room slug "
                            "%r did not resolve; falling back to default "
                            "starting room.", chain_starting_slug,
                        )
                else:
                    # Legacy GCW Landing Pad placement
                    try:
                        landing_pad_rows = await self.db.fetchall(
                            "SELECT id FROM rooms WHERE name = 'Landing Pad' "
                            "AND properties LIKE '%tutorial_zone%' ORDER BY id LIMIT 1"
                        )
                        if landing_pad_rows:
                            tutorial_start_room = landing_pad_rows[0]["id"]
                    except Exception:
                        log.warning("_run_character_creation: unhandled exception", exc_info=True)
                        pass
                char_obj.room_id = tutorial_start_room

                db_fields = char_obj.to_db_dict()

                # ── F.8.c.1: Merge tutorial_chain block into attributes JSON ──
                # The wizard's get_tutorial_chain_block() returns the
                # state shape from engine/tutorial_chains.select_chain()
                # (chain_id, step=1, started_at, completed_steps=[],
                # completion_state="active"). Merge it into the
                # serialized attributes JSON before DB save so the
                # runtime can read tutorial_chain state via the same
                # _get_attrs() helper that engine/tutorial_v2.py uses.
                # Also persists faction_intent based on the chain's
                # faction_alignment so runtime faction-prereq checks
                # against the new character's intent.
                try:
                    chain_block = wizard.get_tutorial_chain_block()
                except AttributeError:
                    chain_block = None

                if chain_block:
                    import json
                    try:
                        attrs_dict = json.loads(db_fields.get("attributes") or "{}")
                    except json.JSONDecodeError:
                        attrs_dict = {}
                    attrs_dict["tutorial_chain"] = chain_block
                    # Persist faction_intent from the selected chain's
                    # faction_alignment so runtime prereq checks resolve.
                    try:
                        chain_id = chain_block.get("chain_id")
                        if chain_id and wizard._chains_corpus is not None:
                            chain_obj = wizard._chains_corpus.by_id().get(chain_id)
                            if chain_obj and chain_obj.faction_alignment:
                                attrs_dict["faction_intent"] = chain_obj.faction_alignment
                    except Exception:
                        log.warning(
                            "[F.8.c.1] Failed to read chain faction_alignment "
                            "for %s", char_obj.name, exc_info=True,
                        )
                    db_fields["attributes"] = json.dumps(attrs_dict)

                char_id = await self.db.create_character(
                    account_id=session.account["id"],
                    fields=db_fields,
                )

                # ── PG.3.gates.a: stamp force_predisposition at chargen ──
                # Per progression_gates_and_consequences_design_v1.md §2.4
                # (May 2026). Predisposition is a hidden 0.0–1.0 score
                # set ONCE at character creation, never modified.
                # `engine.jedi_gating.compute_predisposition` combines:
                #   - species weight  (lore-relevant species nudged up)
                #   - backstory keywords (capped at +0.30)
                #   - an RNG roll (caller-supplied; 0.0–0.5)
                #
                # We seed the roll with the stdlib RNG here. The
                # Director-RNG-seeded variant is a PG.3.gates.b concern
                # (the Director isn't otherwise involved in chargen).
                # Failures here MUST NOT break chargen — predisposition
                # defaults to 0.0 from the schema migration, so we
                # tolerate it staying at 0.0 if scoring fails for any
                # reason.
                try:
                    import random as _random
                    rng_roll = _random.uniform(0.0, 0.5)
                    predisposition = wizard.get_predisposition(rng_roll=rng_roll)
                    await self.db._db.execute(
                        "UPDATE characters SET force_predisposition = ? "
                        "WHERE id = ?",
                        (predisposition, char_id),
                    )
                    await self.db._db.commit()
                    log.info(
                        "[PG.3.gates.a] Set force_predisposition=%.3f for "
                        "char_id=%d (%s)",
                        predisposition, char_id, char_obj.name,
                    )
                except Exception:
                    # Don't break chargen if predisposition scoring
                    # fails — it's flavor data, not load-bearing.
                    log.warning(
                        "[PG.3.gates.a] predisposition scoring failed for %s; "
                        "leaving at default 0.0", char_obj.name, exc_info=True,
                    )

                # Fetch back as a dict
                char = await self.db.get_character(char_id)
                if not char:
                    await session.send_line(ansi.error("Failed to load character after save."))
                    return None

                await session.send_line(
                    ansi.success(f"Welcome to the galaxy, {char['name']}!")
                )
                return char

            except Exception as e:
                if "UNIQUE constraint" in str(e) and "name" in str(e).lower():
                    await session.send_line(
                        ansi.error(f"The name '{db_fields['name']}' is already taken. Pick a different name.")
                    )
                    await session.send_prompt("create> ")
                    # Let them fix the name and re-done
                    while True:
                        try:
                            line = await asyncio.wait_for(session.receive(), timeout=600)
                        except asyncio.TimeoutError:
                            return None
                        line = line.strip()
                        if line.lower() == "quit":
                            return None
                        display, prompt, done = wizard.process_input(line)
                        if display:
                            await session.send_line(display)
                        if done:
                            break
                        if prompt:
                            await session.send_prompt(prompt)
                    continue  # Try saving again with the new name
                else:
                    log.exception("Character creation DB save failed: %s", e)
                    await session.send_line(
                        ansi.error(f"Failed to save character: {e}")
                    )
                    return None

    async def _game_loop(self, session: Session):
        """Main input loop for an authenticated, in-game session."""
        while session.state == SessionState.IN_GAME:
            try:
                line = await asyncio.wait_for(
                    session.receive(),
                    timeout=self.config.idle_timeout,
                )
            except asyncio.TimeoutError:
                await session.send_line(
                    ansi.system_msg("You have been idle too long. Disconnecting.")
                )
                if session.character:
                    await self.db.save_character(
                        session.character["id"],
                        room_id=session.character.get("room_id"),
                    )
                await session.close()
                return

            if session.state != SessionState.IN_GAME:
                return

            await self.parser.parse_and_dispatch(session, line)

    async def _telnet_read_loop(self, reader, session: Session):
        """
        Background task: reads lines from the telnetlib3 reader
        and feeds them into the session's input queue.
        """
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                line = line.strip()
                session.feed_input(line)
        except (ConnectionError, asyncio.CancelledError) as _e:
            log.debug("silent except in server/game_server.py:933: %s", _e, exc_info=True)
        finally:
            # Signal quit if the connection dropped
            if session.state != SessionState.DISCONNECTING:
                session.feed_input("quit")

    async def _game_tick_loop(self):
        """
        Background game tick. Runs once per tick_interval (~1 s).

        Structure (fully migrated — review fix v3):
          1. Idle disconnect check — touches session objects directly; stays
             inline so it runs even if the scheduler itself errors.
          2. Scheduler dispatch — fetches ships_in_space once, then runs all
             22 registered handlers via TickScheduler.run_tick(). Each handler
             is isolated: one failure never blocks the others, and every failure
             is logged at WARNING/EXCEPTION level (not silently swallowed).

        All subsystems are registered in GameServer.__init__ and implemented in:
          server/tick_handlers_ships.py   — ship physics, hazards, transit
          server/tick_handlers_economy.py — NPC AI, boards, economy, territory
        """
        import time as _time
        _next_deadline = _time.monotonic() + self.config.tick_interval

        while self._running:
            # v22 audit S10: deadline-based tick scheduling.
            # If a tick takes 600ms, the next fires at t+1.0s, not t+1.6s.
            # Prevents game time from drifting behind real time under load.
            _now = _time.monotonic()
            _sleep_for = max(0, _next_deadline - _now)
            if _sleep_for > 0:
                await asyncio.sleep(_sleep_for)
            _next_deadline += self.config.tick_interval

            # If we've fallen behind by more than 5 ticks, skip ahead
            # rather than trying to catch up (which would make things worse)
            _now2 = _time.monotonic()
            if _now2 - _next_deadline > self.config.tick_interval * 5:
                _skipped = int((_now2 - _next_deadline) / self.config.tick_interval)
                log.warning("Tick loop fell behind by %d ticks — skipping ahead", _skipped)
                _next_deadline = _now2 + self.config.tick_interval

            # ── Idle session disconnect ───────────────────────────────────────
            for session in list(self.session_mgr.all):
                if (session.is_idle_for(self.config.idle_timeout)
                        and session.state != SessionState.DISCONNECTING):
                    log.info("Idle disconnect: %s", session)
                    await session.send_line(
                        ansi.system_msg("Idle timeout. Disconnecting.")
                    )
                    if session.character:
                        _idle_room = session.character.get("room_id")
                        await self.db.save_character(
                            session.character["id"],
                            room_id=_idle_room,
                        )
                        # Flag as sleeping (Tier 3 Feature #16)
                        if _idle_room:
                            try:
                                from engine.sleeping import set_sleeping
                                _slept = await set_sleeping(
                                    session.character, self.db, _idle_room)
                                if _slept:
                                    await self.session_mgr.broadcast_to_room(
                                        _idle_room,
                                        ansi.system_msg(
                                            f"{session.character['name']} "
                                            f"falls asleep here."),
                                        exclude=session,
                                    )
                            except Exception as _e:
                                log.debug("silent except in server/game_server.py:1005: %s", _e, exc_info=True)
                    await session.close()
                    self.session_mgr.remove(session)

            # ── Scheduler dispatch ────────────────────────────────────────────
            try:
                self._tick_count += 1
                _sched_ships = await self.db.get_ships_in_space()
                _sched_ctx = TickContext(
                    server=self,
                    db=self.db,
                    session_mgr=self.session_mgr,
                    tick_count=self._tick_count,
                    ships_in_space=list(_sched_ships or []),
                )
                await self._tick_scheduler.run_tick(_sched_ctx)
            except Exception:
                log.exception("Tick scheduler dispatch failed")
