# -*- coding: utf-8 -*-
"""
Command framework - parsing, registration, and dispatch.

Commands are classes that inherit from BaseCommand. They register
themselves with the CommandRegistry and are dispatched by the
CommandParser based on player input.

Security features (inspired by TinyMUX/LambdaMOO):
  - Per-session command rate limiting (token bucket)
  - Per-command execution timeout (prevents hangs)
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from server.session import Session

log = logging.getLogger(__name__)

# ── Rate Limiting ──
# Token bucket: refill RATE_LIMIT_REFILL tokens/sec up to RATE_LIMIT_BUCKET max
RATE_LIMIT_BUCKET = 30      # Max burst
RATE_LIMIT_REFILL = 5       # Tokens per second
COMMAND_TIMEOUT = 10.0       # Seconds before a command is killed


class AccessLevel:
    """Permission tiers for command access."""
    ANYONE = 0        # Connected but not logged in
    PLAYER = 1        # Logged in with a character
    BUILDER = 2       # Has builder flag
    ADMIN = 3         # Has admin flag


@dataclass
class CommandContext:
    """
    Everything a command needs to execute.
    Passed to every command handler.
    """
    session: Session
    raw_input: str           # The full raw input string
    command: str             # The matched command name
    args: str                # Everything after the command name
    args_list: list[str]     # Args split by whitespace
    db: object = None        # Database reference
    session_mgr: object = None  # SessionManager reference


class BaseCommand:
    """
    Base class for all game commands.

    Subclass this, set the class attributes, and implement execute().
    """
    key: str = ""                    # Primary command name (e.g., "look")
    aliases: list[str] = []          # Alternate names (e.g., ["l", "ls"])
    access_level: int = AccessLevel.PLAYER
    help_text: str = ""              # Short help description
    usage: str = ""                  # Usage string (e.g., "look [target]")

    async def execute(self, ctx: CommandContext):
        """Override this to implement the command logic."""
        await ctx.session.send_line("This command is not yet implemented.")

    async def check_access(self, ctx: CommandContext) -> bool:
        """Check if the session has permission to run this command."""
        if self.access_level == AccessLevel.ANYONE:
            return True
        if self.access_level == AccessLevel.PLAYER:
            return ctx.session.is_in_game
        if self.access_level == AccessLevel.BUILDER:
            return (
                ctx.session.account
                and ctx.session.account.get("is_builder", 0)
            )
        if self.access_level == AccessLevel.ADMIN:
            return (
                ctx.session.account
                and ctx.session.account.get("is_admin", 0)
            )
        return False


class CommandRegistry:
    """
    Stores all registered commands and handles lookup by name or alias.
    """

    def __init__(self):
        self._commands: dict[str, BaseCommand] = {}
        self._aliases: dict[str, str] = {}  # alias -> primary key

    def register(self, cmd: BaseCommand):
        """Register a command instance."""
        key = cmd.key.lower()
        self._commands[key] = cmd
        for alias in cmd.aliases:
            self._aliases[alias.lower()] = key
        log.debug("Registered command: %s (aliases: %s)", key, cmd.aliases)

    def get(self, name: str) -> Optional[BaseCommand]:
        """Look up a command by name or alias."""
        name = name.lower()
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands[self._aliases[name]]
        # Partial match (prefix matching)
        matches = [
            k for k in self._commands if k.startswith(name)
        ]
        if len(matches) == 1:
            return self._commands[matches[0]]
        return None

    @property
    def all_commands(self) -> list[BaseCommand]:
        return list(self._commands.values())


# Direction aliases - common MUD shortcuts
DIRECTION_ALIASES = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "u": "up",
    "d": "down",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
    "in": "enter",
    "out": "leave",
}


class CommandParser:
    """
    Processes raw input into CommandContext and dispatches to handlers.

    Security:
      - Token bucket rate limiter per session (prevents command flooding)
      - asyncio timeout per command execution (prevents hangs)
    """

    def __init__(self, registry: CommandRegistry, db, session_mgr):
        self.registry = registry
        self.db = db
        self.session_mgr = session_mgr
        # Per-session rate limit state: {session_id: (tokens, last_refill_time)}
        self._rate_buckets: dict[int, list] = {}

    def _check_rate_limit(self, session: Session) -> bool:
        """
        Token bucket rate limiter. Returns True if command is allowed.
        """
        sid = id(session)
        now = time.monotonic()

        if sid not in self._rate_buckets:
            self._rate_buckets[sid] = [RATE_LIMIT_BUCKET, now]

        bucket = self._rate_buckets[sid]
        elapsed = now - bucket[1]
        bucket[1] = now

        # Refill tokens
        bucket[0] = min(RATE_LIMIT_BUCKET, bucket[0] + elapsed * RATE_LIMIT_REFILL)

        # Consume one token
        if bucket[0] >= 1.0:
            bucket[0] -= 1.0
            return True
        return False

    async def parse_and_dispatch(self, session: Session, raw_input: str):
        """Parse a line of input and execute the matching command."""
        raw_input = raw_input.strip()
        if not raw_input:
            await session.send_prompt()
            return

        # Rate limit check
        if not self._check_rate_limit(session):
            await session.send_line("  Slow down! Too many commands.")
            return

        # Expand direction aliases
        first_word = raw_input.split()[0].lower()
        if first_word in DIRECTION_ALIASES:
            raw_input = DIRECTION_ALIASES[first_word] + raw_input[len(first_word):]
            first_word = raw_input.split()[0].lower()

        # Split into command and arguments
        parts = raw_input.split(None, 1)
        cmd_name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        # Build context
        ctx = CommandContext(
            session=session,
            raw_input=raw_input,
            command=cmd_name,
            args=args_str,
            args_list=args_str.split() if args_str else [],
            db=self.db,
            session_mgr=self.session_mgr,
        )

        # Look up command
        cmd = self.registry.get(cmd_name)

        if cmd is None:
            # Try treating it as a direction (movement command)
            if cmd_name in (
                "north", "south", "east", "west", "up", "down",
                "northeast", "northwest", "southeast", "southwest",
                "enter", "leave",
            ):
                move_cmd = self.registry.get("move")
                if move_cmd:
                    ctx.args = cmd_name
                    ctx.args_list = [cmd_name]
                    await self._execute(move_cmd, ctx)
                    return

            # ── Natural Language Combat Intercept ──────────────────────────
            # If the player is in active combat and types something that
            # isn't a registered command, try the IntentParser before giving up.
            if session.character:
                from parser.combat_commands import try_nl_combat_action
                handled = await try_nl_combat_action(ctx, raw_input)
                if handled:
                    return

            await session.send_line(f"Huh? Unknown command: '{cmd_name}'")
            await session.send_prompt()
            return

        await self._execute(cmd, ctx)

    # Commands allowed when the character is dead
    DEAD_ALLOWED = {"respawn", "look", "l", "help", "?", "commands", "who", "quit"}

    async def _execute(self, cmd: BaseCommand, ctx: CommandContext):
        """Check access, dead-state, and run the command with timeout."""
        if not await cmd.check_access(ctx):
            await ctx.session.send_line("You don't have permission to do that.")
            await ctx.session.send_prompt()
            return

        # ── Dead-state intercept ──
        # If the character is dead, only allow whitelisted commands
        char = ctx.session.character if ctx.session else None
        if char and char.get("wound_level", 0) >= 6:  # WoundLevel.DEAD = 6
            cmd_key = cmd.key.lower()
            if cmd_key not in self.DEAD_ALLOWED:
                from server import ansi
                await ctx.session.send_line(
                    ansi.combat_msg(
                        "You are DEAD. Type 'respawn' to return to life, "
                        "or 'look' to see your surroundings."
                    )
                )
                await ctx.session.send_prompt()
                return

        try:
            await asyncio.wait_for(cmd.execute(ctx), timeout=COMMAND_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("Command timed out (%s) for session %s",
                        ctx.command, ctx.session)
            await ctx.session.send_line(
                "  Command timed out. If this persists, please report it."
            )
        except Exception as e:
            log.exception("Command error (%s): %s", ctx.command, e)
            await ctx.session.send_line(
                f"An error occurred processing your command. ({e})"
            )
        await ctx.session.send_prompt()
