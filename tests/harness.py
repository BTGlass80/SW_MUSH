# -*- coding: utf-8 -*-
"""
tests/harness.py — SW_MUSH Integration Test Harness

Provides:
  - MockSession:  A fake Session that captures all output and lets tests
                  feed input lines programmatically.
  - TestHarness:  Boots the full GameServer stack (DB, parser, registries,
                  world build) against a temp SQLite file, then exposes
                  helper methods to create accounts/characters, run commands,
                  and inspect game state — all without network listeners.
  - Assertion helpers for output matching, economy validation, etc.

Usage:
    @pytest.fixture
    async def harness(tmp_path):
        h = TestHarness(tmp_path)
        await h.setup()
        yield h
        await h.teardown()

    async def test_look(harness):
        s = await harness.login_as("TestPlayer")
        out = await harness.cmd(s, "look")
        assert "Landing Pad" in out or len(out) > 0
"""
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from server.session import Session, SessionState, Protocol, SessionManager
from server.config import Config
from parser.commands import (
    CommandRegistry, CommandParser, CommandContext, BaseCommand,
)
from db.database import Database
from engine.character import Character, SkillRegistry, DicePool

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# MockSession — captures output, feeds input without real sockets
# ═══════════════════════════════════════════════════════════════════

class MockSession(Session):
    """
    A Session subclass that needs no real network connection.

    All output sent via send()/send_line() is captured in self.output_lines.
    Input can be fed via feed_input() (inherited) or pre-queued.

    Also captures structured WebSocket events (JSON payloads) separately
    so tests can inspect HUD updates, combat sidebar data, etc.
    """

    def __init__(self, protocol: Protocol = Protocol.WEBSOCKET,
                 width: int = 80, height: int = 24):
        # Dummy callbacks — we override send/close below
        super().__init__(
            protocol=protocol,
            send_callback=self._mock_send,
            close_callback=self._mock_close,
            width=width,
            height=height,
        )
        self.output_lines: list[str] = []
        self.output_events: list[dict] = []  # structured WS events
        self.closed: bool = False
        self._raw_sends: list = []  # everything passed to send()

    async def _mock_send(self, data):
        """Capture all outgoing data."""
        self._raw_sends.append(data)
        if isinstance(data, str):
            self.output_lines.append(data)
        elif isinstance(data, dict):
            self.output_events.append(data)
            # Also stringify for text matching
            self.output_lines.append(json.dumps(data))
        else:
            self.output_lines.append(str(data))

    async def _mock_close(self):
        self.closed = True

    # ── Convenience ──

    def get_output(self) -> str:
        """Return all captured output as a single string."""
        return "\n".join(self.output_lines)

    def get_output_since(self, marker: int) -> str:
        """Return output captured after line index `marker`."""
        return "\n".join(self.output_lines[marker:])

    def mark(self) -> int:
        """Return current output position for later get_output_since()."""
        return len(self.output_lines)

    def clear_output(self):
        """Reset captured output."""
        self.output_lines.clear()
        self.output_events.clear()
        self._raw_sends.clear()

    def find_in_output(self, pattern: str, since: int = 0) -> bool:
        """Check if a regex pattern appears in output since `since`."""
        text = self.get_output_since(since)
        return bool(re.search(pattern, text, re.IGNORECASE))

    def count_in_output(self, pattern: str, since: int = 0) -> int:
        """Count regex matches in output since `since`."""
        text = self.get_output_since(since)
        return len(re.findall(pattern, text, re.IGNORECASE))

    def extract_credits(self, since: int = 0) -> Optional[int]:
        """Try to extract a credits value from output."""
        text = self.get_output_since(since)
        m = re.search(r'(\d[\d,]*)\s*credits?', text, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))
        return None


# ═══════════════════════════════════════════════════════════════════
# TestHarness — boots the full game stack for integration testing
# ═══════════════════════════════════════════════════════════════════

class TestHarness:
    """
    Integration test harness for SW_MUSH.

    Sets up:
      - Fresh SQLite database (in tmp_path)
      - Full schema + migrations
      - World build (Mos Eisley + tutorial zones)
      - Command registry with ALL command modules
      - Species + skill registries
      - CommandParser ready to dispatch

    Does NOT start:
      - Telnet/WebSocket listeners
      - Game tick loop
      - AI providers (uses MockProvider)

    This means tests exercise the exact same code paths as live play,
    minus network I/O and AI inference.
    """

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.db_path = str(tmp_path / "test_game.db")
        self.db: Optional[Database] = None
        self.session_mgr: Optional[SessionManager] = None
        self.registry: Optional[CommandRegistry] = None
        self.parser: Optional[CommandParser] = None
        self.skill_reg: Optional[SkillRegistry] = None
        self.config: Optional[Config] = None
        self._sessions: list[MockSession] = []
        self._next_account_num = 1

    async def setup(self, *, build_world: bool = True):
        """
        Initialize the full game stack.

        Args:
            build_world: If True, run auto_build for Mos Eisley + tutorial.
                         Set False for unit-level tests that don't need rooms.
        """
        self.config = Config(db_path=self.db_path)
        self.db = Database(self.db_path)
        await self.db.connect()
        await self.db.initialize()

        # Seed organizations
        try:
            from engine.organizations import seed_organizations
            await seed_organizations(self.db)
        except Exception as e:
            log.debug("Org seed skipped in test: %s", e)

        # Load game data registries
        from engine.species import SpeciesRegistry
        self.species_reg = SpeciesRegistry()
        data_dir = os.path.join(_PROJECT_ROOT, "data")
        self.species_reg.load_directory(os.path.join(data_dir, "species"))

        self.skill_reg = SkillRegistry()
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            self.skill_reg.load_file(skills_path)

        # Build world
        if build_world:
            try:
                from build_mos_eisley import auto_build_if_needed
                await auto_build_if_needed(self.db_path)
            except Exception as e:
                log.warning("World build failed in test: %s", e)

            try:
                from build_tutorial import auto_build_if_needed as tut_build
                await tut_build(self.db_path)
            except Exception as e:
                log.warning("Tutorial build failed in test: %s", e)

            # Reconnect after builders (they open their own connections)
            await self.db.close()
            self.db = Database(self.db_path)
            await self.db.connect()
            await self.db.initialize()

        # Housing schema + lot seeding
        try:
            from engine.housing import ensure_schema, seed_lots
            await ensure_schema(self.db)
            await seed_lots(self.db)
        except Exception as e:
            log.debug("Housing init skipped: %s", e)

        # Territory schema
        try:
            from engine.territory import ensure_territory_schema
            await ensure_territory_schema(self.db)
        except Exception as e:
            log.debug("Territory init skipped: %s", e)

        # World lore
        try:
            from engine.world_lore import ensure_lore_schema, seed_lore
            await ensure_lore_schema(self.db)
            await seed_lore(self.db)
        except Exception as e:
            log.debug("Lore init skipped: %s", e)

        # Command registry — register ALL command modules
        self.session_mgr = SessionManager()
        self.registry = CommandRegistry()

        from parser.builtin_commands import register_all
        from parser.d6_commands import register_d6_commands
        from parser.building_commands import register_building_commands
        from parser.building_tier2 import register_building_tier2
        from parser.combat_commands import register_combat_commands
        from parser.npc_commands import register_npc_commands
        from parser.space_commands import register_space_commands
        from parser.crew_commands import register_crew_commands
        from parser.mission_commands import register_mission_commands
        from parser.bounty_commands import register_bounty_commands
        from parser.director_commands import register_director_commands
        from parser.news_commands import register_news_commands
        from parser.smuggling_commands import register_smuggling_commands
        from parser.force_commands import register_force_commands
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
        from parser.scene_commands import register_scene_commands
        from parser.mail_commands import register_mail_commands
        from parser.espionage_commands import register_espionage_commands

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
        register_scene_commands(self.registry)
        register_mail_commands(self.registry)
        register_espionage_commands(self.registry)

        # Help system
        from data.help_topics import HelpManager
        help_mgr = HelpManager()
        help_mgr.auto_register_commands(self.registry)
        help_mgr.register_topics()
        from parser.builtin_commands import HelpCommand
        HelpCommand._help_mgr = help_mgr

        self.parser = CommandParser(self.registry, self.db, self.session_mgr)

        log.info("TestHarness ready: %d commands, %d species, %d skills",
                 len(self.registry._commands), self.species_reg.count,
                 self.skill_reg.count)

    async def teardown(self):
        """Clean up database and sessions."""
        for s in self._sessions:
            if not s.closed:
                try:
                    await s.close()
                except Exception:
                    pass
        if self.db:
            await self.db.close()

    # ─── Account & Character Helpers ─────────────────────────────

    async def create_account(self, username: str = None,
                              password: str = "testpass123",
                              is_admin: bool = False) -> dict:
        """Create an account and return the account dict."""
        if username is None:
            username = f"testuser{self._next_account_num}"
            self._next_account_num += 1

        account_id = await self.db.create_account(username, password)
        assert account_id is not None, f"Failed to create account '{username}'"

        if is_admin:
            await self.db._db.execute(
                "UPDATE accounts SET is_admin = 1, is_builder = 1 WHERE id = ?",
                (account_id,)
            )
            await self.db._db.commit()

        account = await self.db.authenticate(username, password)
        assert account is not None
        return account

    async def create_character(
        self,
        account_id: int,
        name: str = None,
        *,
        species: str = "Human",
        template: str = "Smuggler",
        room_id: int = None,
        credits: int = 1000,
        force_sensitive: bool = False,
        attributes: dict = None,
        skills: dict = None,
    ) -> dict:
        """
        Create a character with sensible defaults and return the DB dict.

        Default attributes: 3D across the board (18D total for Human).
        Override with `attributes` dict like {"dexterity": "4D", ...}.
        """
        if name is None:
            name = f"TestChar_{int(time.time() * 1000) % 100000}"

        if room_id is None:
            # Default to Mos Eisley Street (room 2) — past the tutorial
            room_id = 2

        # Build a Character object for proper serialization
        char = Character(name=name, species_name=species)
        char.force_sensitive = force_sensitive

        # Set attributes
        default_attrs = {
            "dexterity": "3D", "knowledge": "3D", "mechanical": "3D",
            "perception": "3D", "strength": "3D", "technical": "3D",
        }
        if attributes:
            default_attrs.update(attributes)

        for attr_name, dice_str in default_attrs.items():
            pool = DicePool.parse(dice_str)
            setattr(char, attr_name, pool)

        # Set skills
        if skills:
            for skill_name, dice_str in skills.items():
                char.add_skill(skill_name, DicePool.parse(dice_str))

        # Force attributes
        if force_sensitive:
            char.control = DicePool(1, 0)
            char.sense = DicePool(1, 0)
            char.alter = DicePool(1, 0)

        db_dict = char.to_db_dict()
        db_dict["template"] = template
        db_dict["room_id"] = room_id

        char_id = await self.db.create_character(account_id, db_dict)

        # Set credits
        await self.db.save_character(char_id, credits=credits)

        # Fetch the full row back
        char_row = await self.db.get_character(char_id)
        assert char_row is not None
        return char_row

    async def make_session(self, account: dict, character: dict,
                            protocol: Protocol = Protocol.WEBSOCKET) -> MockSession:
        """
        Create a MockSession that's fully logged in and in-game.
        Registers it with the SessionManager so broadcasts work.
        """
        session = MockSession(protocol=protocol)
        session.account = account
        session.character = character
        session.state = SessionState.IN_GAME
        self.session_mgr.add(session)
        self._sessions.append(session)
        return session

    async def login_as(
        self,
        name: str = "TestPlayer",
        *,
        is_admin: bool = False,
        room_id: int = None,
        credits: int = 1000,
        species: str = "Human",
        template: str = "Smuggler",
        force_sensitive: bool = False,
        attributes: dict = None,
        skills: dict = None,
    ) -> MockSession:
        """
        One-liner: create account + character + session, return the session.
        The most common test setup pattern.
        """
        account = await self.create_account(is_admin=is_admin)
        char = await self.create_character(
            account["id"], name,
            species=species, template=template,
            room_id=room_id, credits=credits,
            force_sensitive=force_sensitive,
            attributes=attributes, skills=skills,
        )
        session = await self.make_session(account, char)
        return session

    # ─── Command Execution ───────────────────────────────────────

    async def cmd(self, session: MockSession, command: str,
                  timeout: float = 5.0) -> str:
        """
        Execute a command and return ALL output generated.

        This calls parse_and_dispatch directly — same path as the game loop.
        """
        marker = session.mark()
        await asyncio.wait_for(
            self.parser.parse_and_dispatch(session, command),
            timeout=timeout,
        )
        return session.get_output_since(marker)

    async def cmd_sequence(self, session: MockSession,
                           commands: list[str],
                           delay: float = 0.0) -> list[str]:
        """Run multiple commands in order, returning output for each."""
        results = []
        for command in commands:
            out = await self.cmd(session, command)
            results.append(out)
            if delay > 0:
                await asyncio.sleep(delay)
        return results

    async def cmd_with_input(self, session: MockSession, command: str,
                              inputs: list[str],
                              timeout: float = 5.0) -> str:
        """
        Execute a command that prompts for input (like chargen, editors).
        Pre-queues the input lines before dispatching.
        """
        marker = session.mark()
        # Pre-queue the responses
        for inp in inputs:
            session.feed_input(inp)
        await asyncio.wait_for(
            self.parser.parse_and_dispatch(session, command),
            timeout=timeout,
        )
        return session.get_output_since(marker)

    # ─── State Inspection ────────────────────────────────────────

    async def get_credits(self, char_id: int) -> int:
        """Get a character's current credit balance from DB."""
        row = await self.db.get_character(char_id)
        return row["credits"] if row else 0

    async def get_char(self, char_id: int) -> Optional[dict]:
        """Fetch fresh character data from DB."""
        return await self.db.get_character(char_id)

    async def get_room(self, room_id: int) -> Optional[dict]:
        """Fetch room data."""
        return await self.db.get_room(room_id)

    async def get_inventory(self, char_id: int) -> list:
        """Get parsed inventory list for a character."""
        row = await self.db.get_character(char_id)
        if not row:
            return []
        inv = row.get("inventory", "[]")
        if isinstance(inv, str):
            return json.loads(inv)
        return inv

    async def get_char_attrs(self, char_id: int) -> dict:
        """Get parsed attributes dict for a character."""
        row = await self.db.get_character(char_id)
        if not row:
            return {}
        attrs = row.get("attributes", "{}")
        if isinstance(attrs, str):
            return json.loads(attrs)
        return attrs

    async def move_char(self, session: MockSession, room_id: int):
        """Teleport a character to a specific room (bypasses exits)."""
        session.character["room_id"] = room_id
        await self.db.save_character(session.character["id"], room_id=room_id)

    async def set_credits(self, session: MockSession, amount: int):
        """Set a character's credits directly."""
        session.character["credits"] = amount
        await self.db.save_character(session.character["id"], credits=amount)

    async def give_item(self, char_id: int, item: dict):
        """Add an item to a character's inventory."""
        inv = await self.get_inventory(char_id)
        inv.append(item)
        await self.db.save_character(char_id, inventory=json.dumps(inv))

    async def set_admin(self, session: MockSession, is_admin: bool = True):
        """Grant or revoke admin privileges."""
        await self.db._db.execute(
            "UPDATE accounts SET is_admin = ?, is_builder = ? WHERE id = ?",
            (1 if is_admin else 0, 1 if is_admin else 0,
             session.account["id"])
        )
        await self.db._db.commit()
        session.account["is_admin"] = 1 if is_admin else 0
        session.account["is_builder"] = 1 if is_admin else 0

    # ─── Room / World Queries ────────────────────────────────────

    async def find_room_by_name(self, name: str, zone_id: int = None) -> Optional[dict]:
        """Find a room by name (case-insensitive partial match).
        If zone_id given, prefer that zone."""
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM rooms WHERE name LIKE ?", (f"%{name}%",)
        )
        if not rows:
            return None
        if zone_id is not None:
            for r in rows:
                if dict(r).get("zone_id") == zone_id:
                    return dict(r)
        return dict(rows[0])

    async def find_exit(self, from_room: int, direction: str) -> Optional[dict]:
        """Find an exit from a room in a given direction."""
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM exits WHERE from_room_id = ? AND direction = ?",
            (from_room, direction),
        )
        return dict(rows[0]) if rows else None

    async def get_npcs_in_room(self, room_id: int) -> list:
        """Get all NPCs in a room."""
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM npcs WHERE room_id = ?", (room_id,)
        )
        return [dict(r) for r in rows]

    # ─── Economy Helpers ─────────────────────────────────────────

    async def measure_credits_delta(self, session: MockSession,
                                     command: str) -> int:
        """Run a command and return the net change in credits."""
        before = await self.get_credits(session.character["id"])
        await self.cmd(session, command)
        # Refresh character from DB
        after = await self.get_credits(session.character["id"])
        return after - before

    # ─── Ship Helpers ────────────────────────────────────────────

    async def get_ships_at_dock(self, room_id: int) -> list:
        """Get all ships docked at a room."""
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM ships WHERE docked_at = ?", (room_id,)
        )
        return [dict(r) for r in rows]

    async def get_player_ships(self, char_id: int) -> list:
        """Get all ships owned by a character."""
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM ships WHERE owner_id = ?", (char_id,)
        )
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════
# ANSI stripping utility
# ═══════════════════════════════════════════════════════════════════

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for clean assertion matching."""
    return _ANSI_RE.sub('', text)


# ═══════════════════════════════════════════════════════════════════
# Assertion helpers
# ═══════════════════════════════════════════════════════════════════

def assert_output_contains(output: str, *patterns: str):
    """Assert that output contains all given patterns (case-insensitive)."""
    clean = strip_ansi(output)
    for pat in patterns:
        assert re.search(pat, clean, re.IGNORECASE), \
            f"Expected pattern '{pat}' not found in output:\n{clean[:500]}"


def assert_output_not_contains(output: str, *patterns: str):
    """Assert that output does NOT contain any of the given patterns."""
    clean = strip_ansi(output)
    for pat in patterns:
        assert not re.search(pat, clean, re.IGNORECASE), \
            f"Unexpected pattern '{pat}' found in output:\n{clean[:500]}"


def assert_credits_in_range(actual: int, expected: int,
                             tolerance_pct: float = 10.0):
    """Assert credits are within tolerance% of expected value."""
    lo = expected * (1 - tolerance_pct / 100)
    hi = expected * (1 + tolerance_pct / 100)
    assert lo <= actual <= hi, \
        f"Credits {actual} not within {tolerance_pct}% of {expected} (range {lo:.0f}-{hi:.0f})"
