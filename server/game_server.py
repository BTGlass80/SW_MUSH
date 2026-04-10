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
from server.session import Session, SessionState, SessionManager
from server.telnet_handler import TelnetHandler
from server.websocket_handler import WebSocketHandler
from server.web_client import WebClient
from server import ansi
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
from parser.narrative_commands import register_narrative_commands
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
        register_narrative_commands(self.registry)

        # ── Help System Init ──
        from data.help_topics import HelpManager
        help_mgr = HelpManager()
        help_mgr.auto_register_commands(self.registry)
        help_mgr.register_topics()
        from parser.builtin_commands import HelpCommand
        HelpCommand._help_mgr = help_mgr
        log.info("Help system initialized: %d entries",
                 len(help_mgr._entries))

        # AI system
        self.ai_manager = AIManager(AIConfig())
        # Attach to session_mgr so commands can reach it
        self.session_mgr._ai_manager = self.ai_manager
        self.parser = CommandParser(self.registry, self.db, self.session_mgr)

        # Protocol handlers
        self.telnet = TelnetHandler(self)
        self.websocket = WebSocketHandler(self)
        self.web_client = WebClient()


        # Tutorial system
        self.tutorial = TutorialManager()

        self._running = False
        self._tick_task: Optional[asyncio.Task] = None
        self._wage_tick_counter: int = 0
        self._asteroid_tick_counter: int = 0
        self._anomaly_tick_counter: int = 0
        self._faction_payroll_counter: int = 0

    async def start(self):
        """Initialize database, load game data, and start all listeners."""
        log.info("Starting %s...", self.config.game_name)

        # Database
        await self.db.connect()
        await self.db.initialize()

        # Seed organizations (factions + guilds) — idempotent
        try:
            from engine.organizations import seed_organizations
            await seed_organizations(self.db)
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
            built = await auto_build_if_needed(self.config.db_path)
            if built:
                log.info("World auto-build completed successfully.")
        except Exception as _build_err:
            log.warning("World auto-build skipped: %s", _build_err)

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

        # Network listeners
        await self.telnet.start(self.config.telnet_host, self.config.telnet_port)
        await self.websocket.start(
            self.config.websocket_host, self.config.websocket_port
        )

        # Web client (browser UI)
        await self.web_client.start(
            self.config.web_client_host, self.config.web_client_port
        )

        # Background tick (idle checks, NPC updates, etc.)
        self._running = True
        self._tick_task = asyncio.create_task(self._game_tick_loop())

        log.info(
            "%s is running. Telnet:%d  WebSocket:%d  WebClient:%d",
            self.config.game_name,
            self.config.telnet_port,
            self.config.websocket_port,
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
            except asyncio.CancelledError:
                pass

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
                pass

        await self.telnet.stop()
        await self.websocket.stop()
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

        # Main game loop
        await self._game_loop(session)

    async def _character_select(self, session: Session):
        """
        Character selection or full D6 character creation.
        """
        characters = await self.db.get_characters(session.account["id"])

        if not characters:
            # ── Full Character Creation ──
            char = await self._run_character_creation(session)
            if char is None:
                await session.close()
                return
        elif len(characters) == 1:
            char = characters[0]
            await session.send_line(
                f"Entering the game as {ansi.player_name(char['name'])}..."
            )
        else:
            # Multiple characters - let them pick
            await session.send_line("")
            await session.send_line(ansi.header("=== Select a Character ==="))
            for i, c in enumerate(characters, 1):
                await session.send_line(f"  {i}. {c['name']} ({c['species']})")
            await session.send_line("")
            await session.send_line("Enter a number:")
            await session.send_prompt()

            choice = await session.receive()
            try:
                idx = int(choice.strip()) - 1
                if 0 <= idx < len(characters):
                    char = characters[idx]
                else:
                    char = characters[0]
            except ValueError:
                char = characters[0]

            await session.send_line(
                f"Entering the game as {ansi.player_name(char['name'])}..."
            )

        # Enter the game
        session.character = char
        session.state = SessionState.IN_GAME

        # Announce arrival
        room_id = char.get("room_id", self.config.starting_room_id)
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

        # Faction intent migration: auto-join if tutorial stored a faction_intent
        try:
            from engine.organizations import faction_intent_migration
            await faction_intent_migration(char, self.db, session)
        except Exception:
            pass  # Non-critical

        await session.send_prompt()

    async def _run_character_creation(self, session: Session) -> Optional[dict]:
        """
        Run the full interactive character creation flow.
        Returns a DB character dict on success, None on disconnect.
        """
        wizard = CreationWizard(self.species_reg, self.skill_reg, width=session.width)

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

                # Place new characters in tutorial Landing Pad if it exists,
                # otherwise fall back to the configured starting room
                tutorial_start_room = self.config.starting_room_id
                try:
                    landing_pad_rows = await self.db._db.execute_fetchall(
                        "SELECT id FROM rooms WHERE name = 'Landing Pad' "
                        "AND properties LIKE '%tutorial_zone%' ORDER BY id LIMIT 1"
                    )
                    if landing_pad_rows:
                        tutorial_start_room = landing_pad_rows[0]["id"]
                except Exception:
                    pass
                char_obj.room_id = tutorial_start_room

                db_fields = char_obj.to_db_dict()

                char_id = await self.db.create_character(
                    account_id=session.account["id"],
                    fields=db_fields,
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
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            # Signal quit if the connection dropped
            if session.state != SessionState.DISCONNECTING:
                session.feed_input("quit")

    async def _game_tick_loop(self):
        """
        Background game tick. Runs once per tick_interval.
        Used for: idle disconnects, NPC AI, weather, regen, etc.
        """
        while self._running:
            await asyncio.sleep(self.config.tick_interval)

            # Check for idle sessions
            for session in list(self.session_mgr.all):
                if (session.is_idle_for(self.config.idle_timeout)
                        and session.state != SessionState.DISCONNECTING):
                    log.info("Idle disconnect: %s", session)
                    await session.send_line(
                        ansi.system_msg("Idle timeout. Disconnecting.")
                    )
                    if session.character:
                        await self.db.save_character(
                            session.character["id"],
                            room_id=session.character.get("room_id"),
                        )
                    await session.close()
                    self.session_mgr.remove(session)

            # ── NPC Space Crew auto-actions ──
            try:
                from engine.npc_space_crew import tick_npc_space_combat
                await tick_npc_space_combat(self.db, self.session_mgr)
            except Exception:
                log.debug("NPC space crew tick skipped", exc_info=True)


            # ── Ion decay & tractor hold tick ──
            try:
                from parser.space_commands import _get_systems
                import json as _gsj
                ships = await self.db.get_all_ships()
                for _ship in (ships or []):
                    if _ship.get("docked_at"):
                        continue
                    _sys = _gsj.loads(_ship.get("systems") or "{}")
                    _dirty = False
                    # Ion decay: R&E p.108 — ion wears off in 2 rounds
                    _ion = _sys.get("ion_penalty", 0)
                    if _ion and _ion != 99:
                        _sys["ion_penalty"] = max(0, _ion - 1)
                        if _sys["ion_penalty"] == 0:
                            _sys.pop("controls_frozen", None)
                        _dirty = True
                    elif _ion == 99:
                        # Fully frozen: decay to half maneuver then clear
                        _sys["ion_penalty"] = 0
                        _sys.pop("controls_frozen", None)
                        _dirty = True
                    # Tractor auto-reel: notify held ship every tick
                    _held_by = _sys.get("tractor_held_by", 0)
                    if _held_by:
                        _holder = await self.db.get_ship(_held_by)
                        if _holder and _holder.get("bridge_room_id"):
                            await self.session_mgr.broadcast_to_room(
                                _ship["bridge_room_id"],
                                "  [TRACTOR] You are being reeled in. Use 'resist' to break free."
                            )
                        else:
                            # Holder gone — release
                            _sys["tractor_held_by"] = 0
                            _dirty = True
                    if _dirty:
                        await self.db.update_ship(_ship["id"], systems=_gsj.dumps(_sys))
            except Exception:
                log.debug("Ion/tractor tick skipped", exc_info=True)




            # ── Asteroid collision tick (every 30 ticks = ~30s) ──
            self._asteroid_tick_counter += 1
            if self._asteroid_tick_counter % 30 == 0:
                try:
                    import json as _asj
                    from server import ansi as _asa
                    from engine.npc_space_traffic import ZONES as _ASZ
                    from engine.starships import roll_hazard_table as _aht
                    _as_ships = await self.db.get_all_ships()
                    for _as_ship in (_as_ships or []):
                        if _as_ship.get("docked_at"):
                            continue
                        _as_sys = _asj.loads(_as_ship.get("systems") or "{}")
                        # Skip ships in any transit
                        if _as_sys.get("in_hyperspace") or _as_sys.get("sublight_transit"):
                            continue
                        _as_zone = _ASZ.get(_as_sys.get("current_zone", ""))
                        if not _as_zone:
                            continue
                        _density = (_as_zone.hazards or {}).get("asteroid_density", "")
                        if _density != "heavy":
                            continue
                        # Heavy asteroid field: Easy piloting check (diff 5)
                        # to avoid collision. Failure = 1 hull damage (light scrape)
                        import random as _asr
                        _pilot_dice = _as_sys.get("_cached_pilot_dice", 2)
                        _roll = sum(_asr.randint(1, 6) for _ in range(max(1, _pilot_dice)))
                        if _roll >= 5:
                            continue  # Avoided
                        # Collision — light hull scrape
                        _existing = _as_ship.get("hull_damage", 0)
                        await self.db.update_ship(
                            _as_ship["id"], hull_damage=_existing + 1)
                        if _as_ship.get("bridge_room_id"):
                            await self.session_mgr.broadcast_to_room(
                                _as_ship["bridge_room_id"],
                                f"  {_asa.BRIGHT_RED}[ASTEROID]{_asa.RESET} "
                                f"A chunk of rock scrapes the hull! "
                                f"(+1 hull damage) Transit through this zone quickly."
                            )
                except Exception:
                    log.debug("Asteroid collision tick skipped", exc_info=True)

            # ── Sublight zone transit arrival tick ──
            try:
                import json as _slj
                from server import ansi as _sla
                from engine.npc_space_traffic import ZONES as _SLZ
                _sl_ships = await self.db.get_all_ships()
                for _sl_ship in (_sl_ships or []):
                    if _sl_ship.get("docked_at"):
                        continue
                    _sl_sys = _slj.loads(_sl_ship.get("systems") or "{}")
                    if not _sl_sys.get("sublight_transit"):
                        continue
                    _sl_ticks = _sl_sys.get("sublight_ticks_remaining", 0)
                    if _sl_ticks > 1:
                        _sl_sys["sublight_ticks_remaining"] = _sl_ticks - 1
                        await self.db.update_ship(
                            _sl_ship["id"], systems=_slj.dumps(_sl_sys))
                        continue
                    # ── Arrival ──────────────────────────────────────────────
                    _dest_id = _sl_sys.get("sublight_dest", "")
                    _dest_zone = _SLZ.get(_dest_id)
                    _dest_name = (
                        _dest_zone.name if _dest_zone
                        else _dest_id.replace("_", " ").title()
                    )
                    _dest_desc = _dest_zone.desc if _dest_zone else ""
                    _sl_sys["sublight_transit"] = False
                    _sl_sys["current_zone"] = _dest_id
                    _sl_sys.pop("sublight_dest", None)
                    _sl_sys.pop("sublight_ticks_remaining", None)
                    await self.db.update_ship(
                        _sl_ship["id"], systems=_slj.dumps(_sl_sys))
                    if _sl_ship.get("bridge_room_id"):
                        _desc_line = (
                            f"\n  {_dest_desc}" if _dest_desc else ""
                        )
                        await self.session_mgr.broadcast_to_room(
                            _sl_ship["bridge_room_id"],
                            f"  {_sla.BRIGHT_CYAN}[HELM]{_sla.RESET} "
                            f"Arrived: {_dest_name}."
                            f"{_desc_line}"
                        )
                        # Space HUD update on arrival
                        try:
                            from parser.space_commands import broadcast_space_state
                            _sl_fresh = await self.db.get_ship_by_bridge(_sl_ship["bridge_room_id"])
                            if _sl_fresh:
                                await broadcast_space_state(_sl_fresh, self.db, self.session_mgr)
                        except Exception:
                            pass
            except Exception:
                log.debug("Sublight transit tick skipped", exc_info=True)

            # ── Hyperspace transit arrival tick ──
            try:
                import json as _hsj
                from server import ansi as _ha
                from engine.starships import get_ship_registry as _hsr
                from parser.space_commands import get_space_grid as _hsg
                _hs_ships = await self.db.get_all_ships()
                for _hs_ship in (_hs_ships or []):
                    if _hs_ship.get("docked_at"):
                        continue
                    _hs_sys = _hsj.loads(_hs_ship.get("systems") or "{}")
                    if not _hs_sys.get("in_hyperspace"):
                        continue
                    _ticks = _hs_sys.get("hyperspace_ticks_remaining", 0)
                    if _ticks > 1:
                        _hs_sys["hyperspace_ticks_remaining"] = _ticks - 1
                        await self.db.update_ship(_hs_ship["id"], systems=_hsj.dumps(_hs_sys))
                        continue
                    # ── Arrival ──────────────────────────────────────────────
                    _dest_key = _hs_sys.get("hyperspace_dest", "tatooine")
                    _dest_name = _hs_sys.get("hyperspace_dest_name", _dest_key.title())
                    from engine.npc_space_traffic import ZONES as _HTZ
                    _arr_zone = (_dest_key + "_orbit"
                                 if (_dest_key + "_orbit") in _HTZ
                                 else "tatooine_orbit")
                    _hs_sys["in_hyperspace"] = False
                    _hs_sys["current_zone"] = _arr_zone
                    _hs_sys["location"] = _dest_key
                    _hs_sys.pop("hyperspace_dest", None)
                    _hs_sys.pop("hyperspace_dest_name", None)
                    _hs_sys.pop("hyperspace_ticks_remaining", None)
                    _hs_sys.pop("hyperspace_roll_str", None)
                    await self.db.update_ship(_hs_ship["id"], systems=_hsj.dumps(_hs_sys))
                    # Re-add to space grid
                    _hs_tmpl = _hsr().get(_hs_ship["template"])
                    _hs_spd = _hs_tmpl.speed if _hs_tmpl else 5
                    _hsg().add_ship(_hs_ship["id"], _hs_spd)
                    # Notify bridge crew
                    if _hs_ship.get("bridge_room_id"):
                        await self.session_mgr.broadcast_to_room(
                            _hs_ship["bridge_room_id"],
                            f"  {_ha.BRIGHT_CYAN}[HYPERSPACE]{_ha.RESET} "
                            f"Reverting to realspace — arriving at {_dest_name}.\n"
                            f"  The star lines collapse back into points. "
                            f"You are in {_arr_zone.replace('_', ' ').title()}."
                        )
                        # Space HUD update for all crew on arrival
                        try:
                            from parser.space_commands import broadcast_space_state
                            _hs_fresh = await self.db.get_ship_by_bridge(_hs_ship["bridge_room_id"])
                            if _hs_fresh:
                                await broadcast_space_state(_hs_fresh, self.db, self.session_mgr)
                        except Exception:
                            pass
                        # Ship's log: zone visited (Drop 19)
                        try:
                            from engine.ships_log import log_event as _zlog
                            _log_sessions = self.session_mgr.sessions_in_room(
                                _hs_ship["bridge_room_id"]
                            )
                            for _ls in (_log_sessions or []):
                                if _ls.character:
                                    await _zlog(self.db, _ls.character,
                                                "zones_visited", _arr_zone)
                        except Exception:
                            pass

                        # Patrol-on-arrival check for smuggling runs (Drop 11)
                        try:
                            from parser.smuggling_commands import check_patrol_on_arrival
                            from parser.commands import CommandContext
                            _arr_sessions = self.session_mgr.sessions_in_room(
                                _hs_ship["bridge_room_id"]
                            )
                            for _arr_sess in (_arr_sessions or []):
                                if not _arr_sess.character:
                                    continue
                                _arr_ctx = CommandContext(
                                    session=_arr_sess,
                                    db=self.db,
                                    session_mgr=self.session_mgr,
                                    args="",
                                )
                                await check_patrol_on_arrival(_arr_ctx, _dest_key)
                        except Exception:
                            pass
            except Exception:
                log.debug("Hyperspace arrival tick skipped", exc_info=True)

            # -- NPC Space Traffic tick --
            try:
                from engine.npc_space_traffic import get_traffic_manager
                await get_traffic_manager().tick(self.db, self.session_mgr)
            except Exception:
                log.debug("NPC space traffic tick skipped", exc_info=True)

            # ── Space Anomaly spawn & expiry tick (every 300 ticks) ──
            self._anomaly_tick_counter += 1
            if self._anomaly_tick_counter % 300 == 0:
                try:
                    from engine.npc_space_traffic import ZONES as _AZONES
                    from engine.space_anomalies import (
                        spawn_anomalies_for_zone, tick_anomaly_expiry
                    )
                    # Collect all zones that have at least one player ship present
                    _active_zones: set = set()
                    _all_ships = await self.db.get_all_ships()
                    for _az_ship in _all_ships:
                        _az_sys_raw = _az_ship.get("systems", "{}")
                        try:
                            import json as _azj
                            _az_sys = _azj.loads(_az_sys_raw) if isinstance(_az_sys_raw, str) else _az_sys_raw
                        except Exception:
                            continue
                        if _az_sys.get("current_zone"):
                            _active_zones.add(_az_sys["current_zone"])
                    # Tick expiry for all known zones, spawn for active ones
                    for _az_zid in list(_active_zones):
                        tick_anomaly_expiry(_az_zid)
                        _az_zone = _AZONES.get(_az_zid)
                        if _az_zone:
                            spawn_anomalies_for_zone(_az_zid, _az_zone.type.value)
                except Exception:
                    log.debug("Anomaly spawn tick skipped", exc_info=True)

            # ── Space mission patrol timer tick (Drop 14) ─────────────────
            try:
                import json as _smj
                from engine.missions import (
                    get_mission_board, MissionType, MissionStatus, SPACE_MISSION_TYPES
                )
                _sm_board = get_mission_board()
                _sm_ships = await self.db.get_all_ships()
                for _sm_ship in (_sm_ships or []):
                    if _sm_ship.get("docked_at"):
                        continue
                    _sm_sys = _smj.loads(_sm_ship.get("systems") or "{}")
                    _sm_zone = _sm_sys.get("current_zone", "")
                    if not _sm_zone:
                        continue
                    # Find the pilot's char_id
                    try:
                        _sm_crew = _smj.loads(_sm_ship.get("crew") or "{}")
                        _sm_pilot_id = str(_sm_crew.get("pilot", ""))
                    except Exception:
                        continue
                    if not _sm_pilot_id:
                        continue
                    # Check if pilot has an active space mission
                    for _sm_m in list(_sm_board._missions.values()):
                        if (_sm_m.accepted_by != _sm_pilot_id or
                                _sm_m.status != MissionStatus.ACCEPTED or
                                _sm_m.mission_type not in SPACE_MISSION_TYPES):
                            continue
                        md = _sm_m.mission_data or {}
                        if _sm_m.mission_type == MissionType.PATROL:
                            target = md.get("target_zone", "")
                            if _sm_zone == target:
                                md["patrol_ticks_done"] = md.get("patrol_ticks_done", 0) + 1
                                _sm_m.mission_data = md
                                # Notify at milestones
                                done = md["patrol_ticks_done"]
                                req  = md.get("patrol_ticks_required", 120)
                                if done == req // 2:
                                    await self.session_mgr.broadcast_to_room(
                                        _sm_ship["bridge_room_id"],
                                        f"  [PATROL] Halfway through patrol. Hold position.",
                                    )
                                elif done >= req:
                                    await self.session_mgr.broadcast_to_room(
                                        _sm_ship["bridge_room_id"],
                                        f"  [PATROL] Patrol complete! Type 'complete' to turn in.",
                                    )
            except Exception:
                log.debug("Space mission patrol tick skipped", exc_info=True)

            # ── Mission & Bounty board expiry cleanup (every tick) ──
            try:
                from engine.missions import get_mission_board
                board = get_mission_board()
                await board.ensure_loaded(self.db)
                await self.db.cleanup_expired_missions()
            except Exception:
                log.debug("Mission board tick skipped", exc_info=True)

            try:
                from engine.bounty_board import get_bounty_board
                bboard = get_bounty_board()
                await bboard.ensure_loaded(self.db)
            except Exception:
                log.debug("Bounty board tick skipped", exc_info=True)

            # -- Smuggling board expiry cleanup --
            try:
                from engine.smuggling import get_smuggling_board
                await get_smuggling_board().ensure_loaded(self.db)
            except Exception:
                log.debug('Smuggling board tick skipped', exc_info=True)
            # ── Ambient room events ──
            try:
                from engine.ambient_events import get_ambient_manager
                await get_ambient_manager().tick(self.db, self.session_mgr)
            except Exception:
                log.debug("Ambient events tick skipped", exc_info=True)
            # ── World events lifecycle ──
            try:
                from engine.world_events import get_world_event_manager
                await get_world_event_manager().tick(self.db, self.session_mgr)
            except Exception:
                log.debug("World events tick skipped", exc_info=True)
            # ── Director AI tick ──
            try:
                from engine.director import get_director
                await get_director().tick(self.db, self.session_mgr)
            except Exception:
                log.debug("Director tick skipped", exc_info=True)
            # ── CP Progression tick ──
            try:
                from engine.cp_engine import get_cp_engine
                await get_cp_engine().tick(self.db, self.session_mgr)
            except Exception:
                log.debug("CP engine tick skipped", exc_info=True)
            # ── NPC crew wages (every 4 real hours) ──
            self._wage_tick_counter += 1
            try:
                from engine.npc_crew import process_wage_tick, WAGE_TICK_INTERVAL
                if self._wage_tick_counter % WAGE_TICK_INTERVAL == 0:
                    await process_wage_tick(self.db, self.session_mgr)
            except Exception:
                log.debug("Crew wage tick skipped", exc_info=True)

            # ── Faction payroll (every 86400 ticks = once per game-day) ──
            self._faction_payroll_counter += 1
            if self._faction_payroll_counter % 86400 == 0:
                try:
                    from engine.organizations import faction_payroll_tick
                    paid = await faction_payroll_tick(self.db)
                    if paid:
                        log.info("[orgs] Faction payroll: %dcr disbursed.", paid)
                except Exception:
                    log.debug("Faction payroll tick skipped", exc_info=True)
