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
COMMAND_TIMEOUT = 30.0       # Seconds before a command is killed

# Direction words an unregistered command is routed to MoveCommand as.
# Compass + enter/leave are static; wilderness regions may add CUSTOM edge
# words (e.g. "deeper") that are merged in data-driven at dispatch time via
# engine.wilderness_movement.get_custom_edge_directions().
_MOVEMENT_DIRECTIONS = frozenset({
    "north", "south", "east", "west", "up", "down",
    "northeast", "northwest", "southeast", "southwest",
    "enter", "leave",
})



class AccessLevel:
    """Permission tiers for command access."""
    ANYONE = 0        # Connected but not logged in
    PLAYER = 1        # Logged in with a character
    BUILDER = 2       # Has builder flag
    ADMIN = 3         # Has admin flag


# ── Admin audit trail (T3.21 Blocker 3) ──
# Shared by the dispatcher's _execute() privilege gate AND the PLAYER-level
# umbrella forwards (+home admin / +shop admin) that invoke an ADMIN command's
# execute() DIRECTLY — those bypass the dispatcher seam, so unless they record
# the row themselves the who-exercised-privilege trail has a hole.

# Commands whose argument string carries a secret that must NEVER reach the
# audit log (e.g. a plaintext password reset). Matched by command key; a
# content-based password guard in _redact_audit_detail catches the rest (e.g. a
# password reset smuggled through @force).
_AUDIT_REDACT_COMMANDS = frozenset({
    "@newpassword", "@passwd", "@password", "@newpass",
})


def _redact_audit_detail(cmd_key: str, args: str) -> str:
    """Sanitize a command's argument string for the audit trail.

    Redacts secret-bearing commands wholesale and any argument string that
    looks like it carries a password, then caps length to keep the audit
    table lean.
    """
    if not args:
        return ""
    lowered = args.lower()
    # Redact if: (a) the command itself is secret-bearing, (b) the args
    # contain a password keyword (catches @newpassword/@passwd smuggled
    # through @force), or (c) any whitespace token is a known redact
    # command (catches a secret-bearing alias smuggled through @force
    # even if it lacks the 'password' substring).
    if (cmd_key.lower() in _AUDIT_REDACT_COMMANDS
            or "passwd" in lowered or "password" in lowered
            or any(tok in _AUDIT_REDACT_COMMANDS
                   for tok in lowered.split())):
        return "[redacted]"
    return args[:500]


async def audit_privileged_invocation(cmd, ctx) -> None:
    """Best-effort write of a privileged (BUILDER/ADMIN) command invocation to
    the admin_audit trail (T3.21 Blocker 3).

    Used by the dispatcher gate in CommandParser._execute() AND by the
    PLAYER-level umbrella admin forwards (+home admin / +shop admin), which
    call an ADMIN command's execute() directly and would otherwise leave no
    trail. Swallows all errors — an audit-write failure must never block the
    operator's command.
    """
    db = ctx.db
    if db is None or not hasattr(db, "record_admin_action"):
        return
    sess = ctx.session
    acct = (sess.account if sess else None) or {}
    char = (sess.character if sess else None) or {}
    try:
        await db.record_admin_action(
            account_id=acct.get("id"),
            username=acct.get("username"),
            char_id=char.get("id"),
            char_name=char.get("name"),
            access_level=cmd.access_level,
            command=cmd.key,
            detail=_redact_audit_detail(cmd.key, ctx.args),
        )
    except Exception:
        log.warning("admin_audit write failed for %s", cmd.key, exc_info=True)


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
    switches: list[str] = field(default_factory=list)  # /switch flags
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
    valid_switches: list[str] = []   # Accepted /switch names (empty = no validation)

    async def execute(self, ctx: CommandContext):
        """Override this to implement the command logic."""
        await ctx.session.send_line("This command is not yet implemented.")

    async def check_access(self, ctx: CommandContext) -> bool:
        """Check if the session has permission to run this command.

        Elevated tiers (BUILDER/ADMIN) are re-validated against the DB on
        every dispatch instead of trusting the cached login snapshot, so a
        revoked privilege loses access immediately rather than persisting
        until disconnect (T3.21 Blocker 3).
        """
        if self.access_level == AccessLevel.ANYONE:
            return True
        if self.access_level == AccessLevel.PLAYER:
            return ctx.session.is_in_game
        if self.access_level == AccessLevel.BUILDER:
            return await self._live_account_flag(ctx, "is_builder")
        if self.access_level == AccessLevel.ADMIN:
            return await self._live_account_flag(ctx, "is_admin")
        return False

    async def _live_account_flag(self, ctx: CommandContext, flag: str) -> bool:
        """Re-read an elevated-privilege flag (``is_admin``/``is_builder``)
        from the DB rather than trusting the login snapshot (T3.21 Blocker 3).

        Keeps the in-memory ``session.account`` snapshot in sync as a side
        effect so other code reading it sees a revocation too. Falls back to
        the snapshot only when no DB handle is present (defensive — dispatch
        always provides one) or on a transient DB error (no worse than the
        pre-fix behaviour).
        """
        acct = ctx.session.account
        if not acct:
            return False
        db = ctx.db
        if db is None:
            return bool(acct.get(flag, 0))
        try:
            is_admin, is_builder = await db.get_account_privileges(acct["id"])
        except Exception:
            log.warning("check_access: live privilege re-read failed", exc_info=True)
            return bool(acct.get(flag, 0))
        # Keep the snapshot consistent with the live DB state. Sync BOTH
        # flags — one DB round-trip already fetched both, so an is_admin
        # check shouldn't leave a stale is_builder behind for any code
        # reading session.account directly.
        acct["is_admin"] = 1 if is_admin else 0
        acct["is_builder"] = 1 if is_builder else 0
        return is_admin if flag == "is_admin" else is_builder


class CommandRegistry:
    """
    Stores all registered commands and handles lookup by name or alias.
    """

    def __init__(self):
        self._commands: dict[str, BaseCommand] = {}
        self._aliases: dict[str, str] = {}  # alias -> primary key
        # Command-syntax rework Drop 0 (command_syntax_rework_design_v2.md §
        # "Enforcement guard"): record every key/alias collision so the silent
        # last-wins binding is no longer invisible. The binding still happens
        # exactly as before (behaviour unchanged) — we only make it observable
        # for the convention-invariant ratchet test and the boot summary. Each
        # entry is a ``(kind, name)`` tuple where kind ∈ {"key", "alias"}.
        self._collisions: list[tuple[str, str]] = []

    def register(self, cmd: BaseCommand):
        """Register a command instance.

        Last-wins on a duplicate key/alias (unchanged), but any collision — a
        name already bound to a *different* command — is recorded in
        ``self._collisions`` so the canonicalization phases can ratchet them to
        zero instead of being bitten by a silent overwrite.
        """
        key = cmd.key.lower()
        prior = self._commands.get(key)
        if prior is not None and prior is not cmd:
            # A different command already owns this primary key; registering
            # this one hides the prior command entirely.
            self._collisions.append(("key", key))
        self._commands[key] = cmd
        for alias in cmd.aliases:
            a = alias.lower()
            prior_target = self._aliases.get(a)
            if prior_target is not None and prior_target != key:
                # The alias previously routed to a different command's key.
                self._collisions.append(("alias", a))
            elif a in self._commands and self._commands[a] is not cmd:
                # The alias is shadowed by a different command's primary key —
                # get() resolves primary keys first, so this alias is dead.
                self._collisions.append(("alias", a))
            self._aliases[a] = key
        log.debug("Registered command: %s (aliases: %s)", key, cmd.aliases)

    @property
    def collision_signatures(self) -> list[str]:
        """Sorted, de-duplicated ``"kind:name"`` strings for every recorded
        key/alias collision. The convention-invariant test and the game_server
        boot summary both read this."""
        return sorted({f"{kind}:{name}" for kind, name in self._collisions})

    def has_exact(self, name: str) -> bool:
        """True if ``name`` resolves as an exact primary key or alias (no
        prefix matching). Used by the run-on regression ratchet."""
        n = name.lower()
        return n in self._commands or n in self._aliases

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

    def clear_session(self, session_id: int) -> None:
        """Remove rate-bucket entry for a disconnected session (prevent leak)."""
        self._rate_buckets.pop(session_id, None)

    def _check_rate_limit(self, session: Session) -> bool:
        """
        Token bucket rate limiter. Returns True if command is allowed.
        """
        sid = session.id  # was id(session): memory address reused after GC → cross-session bleed
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

        # ── Input intercept (e.g. description editor) ─────────────────────
        # If session has a pending input handler, route this line to it
        # instead of normal command dispatch.
        _intercept = getattr(session, "_input_intercept", None)
        if _intercept is not None:
            try:
                await _intercept(raw_input)
            except Exception as _ie:
                import logging as _ilog
                _ilog.getLogger(__name__).warning("Input intercept error: %s", _ie)
                session._input_intercept = None
            return

        if not raw_input:
            await session.send_prompt()
            return

        # Cancel any active tutorial hint timer on player activity
        try:
            from engine.tutorial_v2 import on_player_input
            on_player_input(session)
        except Exception:
            log.warning("parse_and_dispatch: unhandled exception", exc_info=True)
            pass

        # Rate limit check
        if not self._check_rate_limit(session):
            await session.send_line("  Slow down! Too many commands.")
            return

        # ── Prefix extraction ──────────────────────────────────────────
        # Single-char prefixes that glue to their arguments with no space:
        #   'hello  →  command "'", args "hello"
        #   :waves  →  command ":", args "waves"
        #   ;'s     →  command ";", args "'s"
        # The + and @ prefixes are part of the command word and need no
        # special extraction — "+sheet" splits normally on whitespace.
        GLUED_PREFIXES = {"'", '"', ":", ";"}
        first_char = raw_input[0]

        if first_char in GLUED_PREFIXES:
            cmd_name = first_char
            args_str = raw_input[1:].strip()
        else:
            # Expand direction aliases before splitting
            first_word = raw_input.split()[0].lower()
            if first_word in DIRECTION_ALIASES:
                raw_input = (DIRECTION_ALIASES[first_word]
                             + raw_input[len(first_word):])

            # Split into command and arguments
            parts = raw_input.split(None, 1)
            cmd_name = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""

        # ── Switch extraction ──────────────────────────────────────────
        # "+sheet/brief"  →  cmd_name="+sheet", switches=["brief"]
        # "+help/search"  →  cmd_name="+help",  switches=["search"]
        # Glued prefixes never have switches (no such thing as ":/foo").
        switches = []
        if "/" in cmd_name and first_char not in GLUED_PREFIXES:
            switch_parts = cmd_name.split("/")
            cmd_name = switch_parts[0]
            switches = [s.lower() for s in switch_parts[1:] if s]

        # ── Build context ──────────────────────────────────────────────
        ctx = CommandContext(
            session=session,
            raw_input=raw_input,
            command=cmd_name,
            args=args_str,
            args_list=args_str.split() if args_str else [],
            switches=switches,
            db=self.db,
            session_mgr=self.session_mgr,
        )

        # ── Look up command ────────────────────────────────────────────
        cmd = self.registry.get(cmd_name)

        if cmd is None:
            # Try treating it as a direction (movement command). Compass
            # words + enter/leave always route; wilderness regions may also
            # declare a CUSTOM edge word (e.g. the Coruscant Underworld's
            # "deeper") that must route to MoveCommand so wilderness entry
            # runs — loaded data-driven (PARSER.custom_edge_directions).
            from engine.wilderness_movement import get_custom_edge_directions
            if (cmd_name in _MOVEMENT_DIRECTIONS
                    or cmd_name in get_custom_edge_directions()):
                move_cmd = self.registry.get("move")
                if move_cmd:
                    ctx.args = cmd_name
                    ctx.args_list = [cmd_name]
                    await self._execute(move_cmd, ctx)
                    return

            # ── Natural Language Combat Intercept ──────────────────────
            # If the player is in active combat and types something that
            # isn't a registered command, try the IntentParser before
            # giving up.
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
    DEAD_ALLOWED = {
        "respawn", "look", "l",
        "help", "+help", "?", "commands", "+commands",
        "who", "+who", "quit", "@quit", "logout",
    }

    async def _execute(self, cmd: BaseCommand, ctx: CommandContext):
        """Check access, dead-state, and run the command with timeout."""
        if not await cmd.check_access(ctx):
            await ctx.session.send_line("You don't have permission to do that.")
            await ctx.session.send_prompt()
            return

        # ── Switch validation ──
        if cmd.valid_switches and ctx.switches:
            bad = [s for s in ctx.switches if s not in cmd.valid_switches]
            if bad:
                valid_str = ", ".join("/" + s for s in cmd.valid_switches)
                await ctx.session.send_line(
                    f"  Unknown switch: /{bad[0]}. Valid: {valid_str}"
                )
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

        # ── Audit trail for elevated commands (T3.21 Blocker 3) ──
        # Record every BUILDER/ADMIN command that passes the access gate so
        # there is a durable trail of who exercised privilege. Best-effort:
        # an audit failure must never block the command.
        if cmd.access_level >= AccessLevel.BUILDER:
            await self._audit_privileged(cmd, ctx)

        try:
            await asyncio.wait_for(cmd.execute(ctx), timeout=COMMAND_TIMEOUT)
            _cmd_succeeded = True
        except asyncio.TimeoutError:
            _cmd_succeeded = False
            log.warning("Command timed out (%s) for session %s",
                        ctx.command, ctx.session)
            await ctx.session.send_line(
                "  Command timed out. If this persists, please report it."
            )
        except Exception as e:
            _cmd_succeeded = False
            log.exception("Command error (%s): %s", ctx.command, e)
            await ctx.session.send_line(
                f"An error occurred processing your command. ({e})"
            )

        # ── F.8.c.2.b: CW tutorial chain — command_executed completion ──
        # Fires once per successful command from an in-game character.
        # Talk- and move-driven chain advances are handled by their own
        # dedicated hooks (_post_talk_hooks, _post_move_hooks); this
        # path covers the 16 chain steps whose completion is a generic
        # command (e.g. `+factions`, `+sheet`, `examine subsystem`,
        # `say "yes"`).
        if _cmd_succeeded and ctx.session.is_in_game and ctx.session.character:
            try:
                from engine.chain_events import on_command_executed
                _adv = await on_command_executed(
                    ctx.db, ctx.session.character,
                    ctx.command, ctx.args,
                )
                if _adv:
                    # F.8.c.2.c: deliver graduation teleport UI if
                    # the chain just completed. No-op when no
                    # graduation is pending.
                    from engine.chain_graduation import (
                        execute_pending_teleport,
                    )
                    await execute_pending_teleport(
                        ctx, ctx.session.character,
                    )
            except Exception as _ce:
                log.debug("chain_events command hook error: %s", _ce,
                          exc_info=True)

        # ── HUD update for WebSocket clients ──
        # Send structured state after every command so the browser
        # sidebar stays current without regex-parsing output text.
        if ctx.session.is_in_game:
            # Refresh character data from DB to catch any mutations
            if ctx.session.character:
                try:
                    fresh = await ctx.db.get_character(
                        ctx.session.character["id"]
                    )
                    if fresh:
                        # Preserve room_name cache
                        rn = ctx.session.character.get("_room_name", "")
                        ctx.session.character.update(fresh)
                        if rn:
                            ctx.session.character["_room_name"] = rn
                except Exception:
                    pass  # Non-critical
            await ctx.session.send_hud_update(db=ctx.db, session_mgr=ctx.session_mgr)

        await ctx.session.send_prompt()

    def _redact_audit_detail(self, cmd_key: str, args: str) -> str:
        """Back-compat instance shim → module-level ``_redact_audit_detail``.

        The implementation moved to module scope so the +home/+shop admin
        umbrella forwards can share it; this preserves the existing
        ``parser._redact_audit_detail(...)`` call surface (tests + callers).
        """
        return _redact_audit_detail(cmd_key, args)

    async def _audit_privileged(self, cmd: BaseCommand, ctx: CommandContext):
        """Back-compat instance shim → module-level
        ``audit_privileged_invocation``. See that function for behaviour.
        """
        await audit_privileged_invocation(cmd, ctx)
