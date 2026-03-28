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
from server import ansi
from parser.commands import CommandRegistry, CommandParser, CommandContext
from parser.builtin_commands import register_all
from parser.d6_commands import register_d6_commands
from parser.building_commands import register_building_commands
from parser.building_tier2 import register_building_tier2
from parser.combat_commands import register_combat_commands
from parser.npc_commands import register_npc_commands
from parser.space_commands import register_space_commands
from parser.crew_commands import register_crew_commands
from ai.providers import AIManager, AIConfig
from db.database import Database
from engine.species import SpeciesRegistry
from engine.character import SkillRegistry, Character
from engine.creation import CreationEngine

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

        # AI system
        self.ai_manager = AIManager(AIConfig())
        # Attach to session_mgr so commands can reach it
        self.session_mgr._ai_manager = self.ai_manager
        self.parser = CommandParser(self.registry, self.db, self.session_mgr)

        # Protocol handlers
        self.telnet = TelnetHandler(self)
        self.websocket = WebSocketHandler(self)

        self._running = False
        self._tick_task: Optional[asyncio.Task] = None

    async def start(self):
        """Initialize database, load game data, and start all listeners."""
        log.info("Starting %s...", self.config.game_name)

        # Database
        await self.db.connect()
        await self.db.initialize()

        # Load game data
        import os
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.species_reg.load_directory(os.path.join(data_dir, "species"))
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            self.skill_reg.load_file(skills_path)
        log.info("Game data loaded: %d species, %d skills",
                 self.species_reg.count, self.skill_reg.count)

        # Network listeners
        await self.telnet.start(self.config.telnet_host, self.config.telnet_port)
        await self.websocket.start(
            self.config.websocket_host, self.config.websocket_port
        )

        # Background tick (idle checks, NPC updates, etc.)
        self._running = True
        self._tick_task = asyncio.create_task(self._game_tick_loop())

        log.info(
            "%s is running. Telnet:%d  WebSocket:%d",
            self.config.game_name,
            self.config.telnet_port,
            self.config.websocket_port,
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

        await session.send_prompt()

    async def _run_character_creation(self, session: Session) -> Optional[dict]:
        """
        Run the full interactive character creation flow.
        Returns a DB character dict on success, None on disconnect.
        """
        engine = CreationEngine(self.species_reg, self.skill_reg)

        # Show initial screen
        display, prompt = engine.get_initial_display()
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

            display, prompt, done = engine.process_input(line)

            if display:
                await session.send_line(display)

            if done:
                break

            if prompt:
                await session.send_prompt(prompt)

        # Build Character object and save to DB
        while True:
            try:
                char_obj = engine.get_character()
                char_obj.room_id = self.config.starting_room_id
                db_fields = char_obj.to_db_dict()

                cursor = await self.db._db.execute(
                    """INSERT INTO characters
                       (account_id, name, species, template, attributes, skills,
                        wound_level, character_points, force_points,
                        dark_side_points, room_id, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session.account["id"],
                        db_fields["name"],
                        db_fields["species"],
                        db_fields.get("template", ""),
                        db_fields["attributes"],
                        db_fields["skills"],
                        db_fields["wound_level"],
                        db_fields["character_points"],
                        db_fields["force_points"],
                        db_fields["dark_side_points"],
                        db_fields["room_id"],
                        db_fields.get("description", ""),
                    ),
                )
                await self.db._db.commit()

                # Fetch back as a dict
                char = await self.db.get_character(cursor.lastrowid)
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
                        display, prompt, done = engine.process_input(line)
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
                if session.is_idle and session.state != SessionState.DISCONNECTING:
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
