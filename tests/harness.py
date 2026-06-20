# -*- coding: utf-8 -*-
"""
tests/harness.py — Smoke test harness (Drop SH1).

This module replaces the prior ``_SkipHarness`` placeholder with a real
in-process integration harness. It boots a full ``GameServer`` against a
temp SQLite DB, drives sessions through the same ``Session.feed_input`` /
``send_callback`` seams the live WebSocket and Telnet handlers use, and
exposes the API contract that ``tests/test_economy_validation.py`` was
originally written against (``login_as``, ``cmd``, ``get_char``,
``get_credits``, ``give_item``, ``db``).

Design reference: ``smoke_test_harness_design_v1.md``.

──────────────────────────────────────────────────────────────────────────────
Backwards-compatibility note
──────────────────────────────────────────────────────────────────────────────

The module-level helpers (``strip_ansi``, ``assert_output_contains``,
``assert_credits_in_range``) are preserved verbatim from the prior
shim — they were re-exported and used by tests other than the harness
fixture itself.

The ``harness`` fixture is now session-scoped via class-fixture
inheritance: per the design doc §6, smoke scenarios share a booted
GameServer per pytest class to amortize the world-build cost (~1-2s
per class). Tests that take ``harness`` from outside ``tests/smoke/``
(notably the ~7 in ``test_economy_validation.py``) still work — they
get a class-scoped harness too.

──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from typing import Any, Optional

import pytest


log = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────
# Module-level helpers (preserved from the prior shim)
# ───────────────────────────────────────────────────────────────────────────

# ANSI CSI escape sequences. Captures both ESC[…m colour codes and other
# ESC[…<letter> control sequences (cursor moves etc.) just in case.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Remove ANSI CSI escapes from *text* so substring assertions work."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return _ANSI_RE.sub("", text)


def assert_output_contains(output: str, expected: str) -> None:
    """Assert that *expected* appears somewhere in *output* (after ANSI
    stripping). Case-insensitive — tests that need a case-sensitive
    match should compare ``strip_ansi(output)`` directly.
    """
    clean = strip_ansi(output).lower()
    needle = expected.lower()
    assert needle in clean, (
        f"Expected substring not found.\n"
        f"  Expected: {expected!r}\n"
        f"  In output: {clean[:500]!r}"
    )


def assert_credits_in_range(actual: int, lo: int, hi: int) -> None:
    """Assert that *actual* (a credit amount) falls within ``[lo, hi]``."""
    assert lo <= actual <= hi, (
        f"Credits {actual} outside expected range [{lo}, {hi}]"
    )


# ───────────────────────────────────────────────────────────────────────────
# Project root resolution — needed so the harness can be run from anywhere
# ───────────────────────────────────────────────────────────────────────────

def _project_root() -> str:
    """Return the absolute path to the project root (where main.py lives).

    The test files live at ``<root>/tests/`` so we go up one level from
    ``__file__``. If the harness is ever moved, fix here.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


# Ensure the project root is importable. This mirrors what ``main.py`` does
# at boot — without it, ``from server.config import Config`` fails when
# pytest is invoked from a working directory other than the project root.
_root = _project_root()
if _root not in sys.path:
    sys.path.insert(0, _root)


# ───────────────────────────────────────────────────────────────────────────
# _ClientSession — per-test client handle
# ───────────────────────────────────────────────────────────────────────────

class _ClientSession:
    """A test-side handle to one logged-in player session.

    Wraps a real ``server.session.Session`` whose ``send_callback`` has
    been redirected into our capture buffers. From the harness's point
    of view, this is "the player." Tests interact with it through
    ``harness.cmd(s, ...)`` etc. — but a few attributes are exposed
    directly because tests assert on them.

    Attributes
    ----------
    character : dict
        The character row, as the live game has it. Mutated by
        ``harness.get_char()`` reload calls.
    text_output : list[str]
        All text frames received since the last drain. Use ``.drain()``
        to consume + clear.
    json_events : list[dict]
        All typed JSON payloads (``hud_update``, ``combat_state``,
        ``space_state``, ``pose_event``, ``combat_resolution_event``,
        etc.) received in this session. NEVER auto-cleared — tests can
        assert on the full event history.
    session : server.session.Session
        The underlying live Session object. Tests should generally
        avoid touching this directly, but it's exposed for advanced
        scenarios (e.g. checking ``session.state``).
    """

    def __init__(self, session, text_buf: list[str], json_buf: list[dict],
                 game_task: asyncio.Task):
        self.session = session
        self._text_buf = text_buf
        self._json_buf = json_buf
        self._game_task = game_task

    @property
    def character(self):
        return self.session.character

    @character.setter
    def character(self, value):
        # Tests do `s.character = await h.get_char(...)` to refresh.
        self.session.character = value
        # Also invalidate the cached parsed Character object.
        self.session.invalidate_char_obj()

    @property
    def text_output(self) -> list[str]:
        return list(self._text_buf)

    @property
    def json_events(self) -> list[dict]:
        return list(self._json_buf)

    def drain_text(self) -> str:
        """Return + clear accumulated text frames as a single string."""
        out = "".join(self._text_buf)
        self._text_buf.clear()
        return out


# ───────────────────────────────────────────────────────────────────────────
# _LiveHarness — boots GameServer in-process, drives sessions
# ───────────────────────────────────────────────────────────────────────────

class _LiveHarness:
    """In-process integration harness backed by a real ``GameServer``.

    Boots a full server stack against a temp SQLite DB. Drives test
    sessions by directly instantiating ``Session`` objects with captured
    callbacks and feeding input through ``Session.feed_input``.

    Use via the ``harness`` pytest fixture, NOT directly. The fixture
    handles boot/teardown and the per-class scoping the design calls
    for.
    """

    def __init__(self):
        self._tmpdir: Optional[str] = None
        self._server = None
        self._db_path: Optional[str] = None
        self._sessions: list[_ClientSession] = []
        self._era: str = "gcw"
        # Tracks character names this harness has handed out so each
        # ``login_as("Name")`` call gets a fresh row even when called
        # repeatedly within one class.
        self._created_chars: set[str] = set()

    # ── public attributes the existing test_economy_validation.py reads ──

    @property
    def db(self):
        """The live ``Database`` instance. Tests can call its proxy
        methods (``fetchall``, ``execute``, ``commit``) for direct DB
        assertions.
        """
        return self._server.db

    @property
    def server(self):
        """The live ``GameServer``. Mostly internal — exposed for
        advanced scenarios that need to inspect ``session_mgr``,
        ``parser``, etc.
        """
        return self._server

    @property
    def era(self) -> str:
        return self._era

    # ── boot / teardown ────────────────────────────────────────────────────

    @classmethod
    async def boot(cls, era: str = "gcw") -> "_LiveHarness":
        """Boot a fresh harness against a temp DB. Returns the live
        harness ready to accept ``login_as`` calls.

        The temp DB undergoes the full auto-build path on first use,
        which takes ~1-2 seconds depending on era. Subsequent
        ``login_as`` calls within the same harness are sub-100ms.
        """
        h = cls()
        h._era = era
        h._tmpdir = tempfile.mkdtemp(prefix="sw_mush_smoke_")
        h._db_path = os.path.join(h._tmpdir, f"smoke_{era}.db")

        # Bring up the Config + GameServer in the same order main.py uses.
        # The era_state.set_active_config call MUST precede the GameServer
        # import (see main.py header comment for the F.6a.6 ordering
        # invariant).
        from server.config import Config
        from engine.era_state import set_active_config

        config = Config(
            db_path=h._db_path,
            active_era=era,
            # Bind to localhost on ports we won't actually touch — the
            # in-process harness never opens these listeners.
            telnet_host="127.0.0.1",
            telnet_port=0,
            web_client_host="127.0.0.1",
            web_client_port=0,
            # Trim idle timeout so tests fail fast if the game loop
            # somehow stalls waiting for input.
            idle_timeout=5,
        )
        set_active_config(config)

        # We DO NOT call server.start() — that would open real listeners.
        # Instead, we manually run the boot steps that don't touch
        # network: DB init, world auto-build, schema seeds. This is
        # the in-process boot path the design doc §3.1 describes.
        from server.game_server import GameServer
        h._server = GameServer(config)
        await h._boot_no_listeners()
        return h

    async def _boot_no_listeners(self):
        """Run GameServer.start() steps that don't open sockets.

        Mirrors ``GameServer.start()`` in ``server/game_server.py`` up
        through the data-loading / world-build phase. We deliberately
        skip the ``self.telnet.start(...)`` and ``self.web_client.start(...)``
        calls because the in-process harness drives sessions without a
        transport.
        """
        srv = self._server

        # ── Process-singleton resets (test isolation) ──
        # Module-level singletons survive across harness boots within one
        # pytest process. Reset the ones whose in-memory state would leak
        # between class-scoped harnesses. The bounty board (drop 26) is
        # the canary: a chain bounty spawned + claimed by one test
        # otherwise leaks into the next test's board, where the
        # idempotent-spawn check skips respawn and the next test sees a
        # stale CLAIMED contract. (World-events `_manager` is reset
        # per-test elsewhere; this covers the boot-time board.)
        try:
            from engine.bounty_board import reset_bounty_board
            reset_bounty_board()
        except Exception:
            log.debug("smoke harness: bounty board reset failed",
                      exc_info=True)

        # ── Database ──
        await srv.db.connect()
        await srv.db.initialize()

        # ── Organization seed ──
        try:
            from engine.organizations import seed_organizations
            await seed_organizations(srv.db, era=srv.config.active_era)
        except Exception:
            log.warning("smoke harness: org seed failed", exc_info=True)

        # ── Game data ──
        data_dir = os.path.join(_project_root(), "data")
        srv.species_reg.load_directory(os.path.join(data_dir, "species"))
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            srv.skill_reg.load_file(skills_path)

        # ── World auto-build (the slow part: ~1-2s) ──
        try:
            from build_mos_eisley import auto_build_if_needed
            await auto_build_if_needed(srv.config.db_path,
                                       era=srv.config.active_era)
        except Exception:
            log.warning("smoke harness: world auto-build failed",
                        exc_info=True)

        # ── Housing schema + lots ──
        try:
            from engine.housing import (
                ensure_schema as _hs_schema,
                seed_lots as _hs_lots,
            )
            await _hs_schema(srv.db)
            await _hs_lots(srv.db)
        except Exception:
            log.warning("smoke harness: housing init failed", exc_info=True)

        # ── Territory schema ──
        try:
            from engine.territory import ensure_territory_schema
            await ensure_territory_schema(srv.db)
        except Exception:
            log.warning("smoke harness: territory init failed", exc_info=True)

        # ── Player-cities schema ──
        # GameServer initializes this at boot (server/game_server.py); the
        # smoke harness must mirror it because the death / corpse / security
        # path queries player_cities (room-in-city security lookup). Without
        # it, smoke scenarios that kill a PC fail with "no such table:
        # player_cities" (e.g. the BH insurance loop, BTY-6).
        try:
            from engine.player_cities import ensure_schema as _pc_schema
            await _pc_schema(srv.db)
        except Exception:
            log.warning("smoke harness: player_cities init failed",
                        exc_info=True)

        # ── World lore ──
        try:
            from engine.world_lore import ensure_lore_schema, seed_lore
            from engine.era_state import get_seeding_era
            await ensure_lore_schema(srv.db)
            await seed_lore(srv.db, era=get_seeding_era())
        except Exception:
            log.warning("smoke harness: world lore init failed", exc_info=True)

        # ── Tutorial auto-build ──
        try:
            from build_tutorial import auto_build_if_needed as tb_auto
            await tb_auto(srv.config.db_path)
        except Exception:
            log.warning("smoke harness: tutorial init failed", exc_info=True)

        # NOTE: we do NOT start the tick loop. SH1 scenarios don't need
        # ambient ticks, and disabling them keeps tests deterministic.
        # When ``advance_ticks(n)`` lands in a later drop, it will run
        # tick handlers manually rather than relying on a background
        # task.
        srv._running = True

    async def shutdown(self):
        """Tear down the harness: close all sessions, stop the server,
        delete the temp DB.
        """
        # Close every test session.
        for cs in self._sessions:
            try:
                if not cs._game_task.done():
                    cs._game_task.cancel()
                    try:
                        await cs._game_task
                    except (asyncio.CancelledError, Exception):
                        pass
            except Exception:
                log.warning("smoke harness: session close failed",
                            exc_info=True)
        self._sessions.clear()

        # Stop the server (closes DB, etc.). We bypass ``GameServer.stop()``
        # and call its DB close directly because we never started the
        # listeners — calling ``stop()`` would try to stop them.
        try:
            if self._server and self._server.db:
                await self._server.db.close()
        except Exception:
            log.warning("smoke harness: db close failed", exc_info=True)

        # Drop the temp directory.
        if self._tmpdir and os.path.isdir(self._tmpdir):
            try:
                shutil.rmtree(self._tmpdir, ignore_errors=True)
            except Exception:
                pass

    # ── login_as ───────────────────────────────────────────────────────────

    async def login_as(self, name: str, *, room_id: int = 1,
                       credits: int = 0, is_admin: bool = False,
                       species: str = "Human",
                       template: str = "scout",
                       skills: Optional[dict] = None,
                       protocol: str = "websocket") -> _ClientSession:
        """Create + log in a test character. Returns a ``_ClientSession``
        ready for ``cmd()`` calls.

        Per design §9.2 Q1: the baseline character data comes from
        ``data/worlds/<era>/test_character.yaml`` (when available). The
        per-call kwargs override on top — so by default every test
        character is the test_character.yaml's stat sheet, just renamed
        and re-positioned.

        Parameters
        ----------
        name : str
            Character display name. Must be unique within the harness's
            lifetime; conflicts raise.
        room_id : int
            Starting room. Defaults to room 1 (typically the spawn
            point).
        credits : int
            Starting credits. ``test_character.yaml`` provides 100000
            for the test_jedi build; set to 0 here to start scenarios
            with a clean economy state.
        is_admin : bool
            If True, the character's account gets ``is_admin=1``
            (grants admin command access).
        species : str
            Defaults to "Human".
        template : str
            Chargen template key. Defaults to "scout" (no Force, modest
            skills) for low-noise scenarios. Pass ``"jedi"`` etc. for
            scenarios that need Force.
        protocol : str
            ``"websocket"`` or ``"telnet"``. Both are in-process; the
            Telnet flavor uses ``Protocol.TELNET`` with a plaintext
            ``send_callback`` (no JSON envelope), while WebSocket
            uses ``Protocol.WEBSOCKET`` with the JSON-envelope split
            into text vs. typed-event buffers. Most player-facing
            commands emit DIFFERENT outputs on each protocol (typed
            events on WS, formatted text on Telnet) — see SH2 §3.5.

        Returns
        -------
        _ClientSession
        """
        if protocol not in ("websocket", "telnet"):
            raise ValueError(
                f"login_as protocol={protocol!r} not supported. "
                "Use 'websocket' or 'telnet'."
            )

        if name in self._created_chars:
            raise ValueError(
                f"Character {name!r} already created in this harness. "
                f"Use a different name or boot a fresh harness."
            )
        self._created_chars.add(name)

        from server.session import Session, SessionState, Protocol

        # Build a Session with capture callbacks. The send_callback
        # shape differs by protocol:
        #
        #   WebSocket: payloads arrive as JSON-encoded strings. We
        #     parse and route {"type": "text", "data": "..."} → text_buf
        #     and any other {"type": ...} → json_buf.
        #
        #   Telnet: payloads arrive as raw text (server.session.py
        #     formats pose_event etc. as fallback text on Telnet
        #     sessions, so the smoke harness only needs to capture
        #     the text stream).
        text_buf: list[str] = []
        json_buf: list[dict] = []

        if protocol == "websocket":
            async def _send(payload):
                if isinstance(payload, str):
                    try:
                        obj = json.loads(payload)
                    except (ValueError, TypeError):
                        text_buf.append(payload)
                        return
                    if isinstance(obj, dict):
                        if obj.get("type") == "text":
                            text_buf.append(obj.get("data", ""))
                        else:
                            json_buf.append(obj)
                        return
                text_buf.append(str(payload))
            sess_protocol = Protocol.WEBSOCKET
        else:  # telnet
            async def _send(payload):
                # Telnet sessions get raw text; the typed-event path
                # in server/session.py converts pose_event etc. into
                # formatted text fallbacks before send_callback is
                # invoked. We just capture everything as text.
                text_buf.append(str(payload))
            sess_protocol = Protocol.TELNET

        async def _close():
            return None

        session = Session(
            protocol=sess_protocol,
            send_callback=_send,
            close_callback=_close,
            width=100,
            height=40,
        )
        self._server.session_mgr.add(session)

        # Seed the account directly. Bypassing the on-the-wire
        # ``create <user> <pass>`` flow because that's what F2 covers
        # explicitly — every other scenario short-circuits.
        username = f"test_{name.lower()}"
        password = "smoketestpass"
        account_id = await self.db.create_account(username, password)
        if account_id is None:
            # Already-exists case (shouldn't happen with the unique-name
            # guard above, but defensive).
            raise RuntimeError(
                f"Could not create account for {name!r} — duplicate?"
            )
        account = await self.db.authenticate(username, password)
        if is_admin:
            await self.db._db.execute(
                "UPDATE accounts SET is_admin = 1 WHERE id = ?",
                (account_id,),
            )
            await self.db._db.commit()
            account = await self.db.get_account(account_id)
        session.account = account

        # Build the character payload from test_character.yaml when
        # available, then layer per-call overrides on top.
        char_fields = await self._build_test_character_fields(
            name=name,
            species=species,
            template=template,
            room_id=room_id,
            credits=credits,
            skills_override=skills,
        )
        # Now that the SCHEMA_VERSION drift is fixed (db/database.py:17
        # bumped to 17), we can use the canonical db.create_character()
        # path that the wizard and chargen flows themselves use.
        char_fields["chargen_notes"] = "smoke-harness-seeded"
        char_id = await self.db.create_character(account_id, char_fields)

        # db.create_character's INSERT does not include credits — the
        # column defaults to 1000 in the schema. Apply the requested
        # credits via save_character (also the canonical path the
        # economy engine uses).
        await self.db.save_character(char_id, credits=credits)

        # Reload from DB so we get a complete row (including any
        # default columns the INSERT didn't set).
        chars = await self.db.get_characters(account_id)
        char_row = next((c for c in chars if c["id"] == char_id), None)
        if char_row is None:
            raise RuntimeError(
                f"Character {name!r} created but not found on reload."
            )
        session.character = char_row
        session.state = SessionState.IN_GAME

        # Spin up the game loop for this session as a background task.
        # This mirrors the websocket handler's ``handle_new_session``
        # call, but skips the login-prompt phase since we're already
        # in IN_GAME.
        game_task = asyncio.create_task(self._server._game_loop(session))

        cs = _ClientSession(session, text_buf, json_buf, game_task)
        self._sessions.append(cs)

        # Drain any output the loop emits at start-of-game (room
        # description, prompt, etc.) so the first cmd() call returns
        # only that command's output.
        await asyncio.sleep(0.05)
        cs.drain_text()
        return cs

    async def _build_test_character_fields(self, *, name: str, species: str,
                                            template: str, room_id: int,
                                            credits: int,
                                            skills_override: Optional[dict] = None) -> dict:
        """Build the ``fields`` dict for character creation.

        Loads ``data/worlds/<era>/test_character.yaml`` for the
        attribute / skill baseline, then overrides name, species,
        template, room, credits. Falls back to a minimal default if
        the YAML can't be loaded.

        ``skills_override`` (when provided) replaces the test_character
        skills entirely — used by economy tests that need very specific
        skill levels.
        """
        attributes_json = json.dumps({
            "dexterity": "3D",
            "knowledge": "3D",
            "mechanical": "3D",
            "perception": "3D",
            "strength": "3D",
            "technical": "3D",
        })
        skills_json = json.dumps({})

        try:
            import yaml
            era_dir = os.path.join(
                _project_root(), "data", "worlds", self._era
            )
            tc_path = os.path.join(era_dir, "test_character.yaml")
            if os.path.exists(tc_path):
                with open(tc_path, "r", encoding="utf-8") as f:
                    tc = yaml.safe_load(f) or {}
                ch = tc.get("character") or {}
                attrs = ch.get("attributes") or {}
                # Strip the non-D6 game-state flags (force_sensitive,
                # tutorial_step, etc.) — those don't go in the
                # attributes JSON column. Only the six core attrs +
                # any "<attr>_extra" fields the engine actually reads.
                clean_attrs = {
                    k: v for k, v in attrs.items()
                    if k in {"dexterity", "knowledge", "mechanical",
                             "perception", "strength", "technical"}
                    and isinstance(v, str)
                }
                if clean_attrs:
                    attributes_json = json.dumps(clean_attrs)
                skills = ch.get("skills") or {}
                if isinstance(skills, dict):
                    skills_json = json.dumps(skills)
        except Exception:
            log.debug(
                "smoke harness: test_character.yaml parse failed; "
                "using minimal defaults", exc_info=True,
            )

        # If the caller supplied an explicit skills override, it wins
        # over the test_character baseline.
        if skills_override is not None:
            skills_json = json.dumps(skills_override)

        return {
            "name": name,
            "species": species,
            "template": template,
            "attributes": attributes_json,
            "skills": skills_json,
            "wound_level": 0,
            "character_points": 5,
            "force_points": 1,
            "dark_side_points": 0,
            "credits": credits,
            "room_id": room_id,
            "description": f"A test character named {name}.",
            # All standard character creation fields. Note: we now use
            # db.create_character() directly (the canonical path), so
            # this dict needs to match what create_character expects.
        }

    # ── cmd ────────────────────────────────────────────────────────────────

    async def cmd(self, s: _ClientSession, text: str,
                  *, timeout: float = 2.0,
                  quiet_window: float = 0.1) -> str:
        """Feed input on session *s*, drain output, return text.

        Returns the concatenated text output (ANSI-stripped) emitted
        between this call and the moment the output stream goes quiet
        for ``quiet_window`` seconds. Hard-capped by ``timeout``.

        JSON events received in the same window are appended to
        ``s.json_events`` and NOT included in the returned string.
        Tests that need them inspect ``s.json_events`` directly.
        """
        # Snapshot the json_events pointer so a scenario can see exactly
        # which events came from THIS command (s.json_events[before:]
        # is "events from the last cmd").
        s.session.feed_input(text)
        return await self._drain_text(s, timeout=timeout,
                                      quiet_window=quiet_window)

    async def _drain_text(self, s: _ClientSession, *,
                          timeout: float, quiet_window: float) -> str:
        """Wait until the text buffer goes quiet for *quiet_window*,
        then drain it.

        FLAKE FIX (May 18 [3] 2026, CX4 triage): the original loop
        declared "quiet" as soon as the buffer hadn't changed for
        ``quiet_window`` seconds — including the case where the
        buffer never received any text at all. Under sandbox load
        when the server is still processing a queued command (e.g.
        CX4's ``+combat`` immediately after ``attack`` engages
        combat with NPC auto-declare + initiative + broadcast),
        the drain could fire on an empty buffer and return "" even
        though the command produced output a fraction of a second
        later. The fix: require the buffer to have been non-empty
        at some point before the quiet-window break can fire. If
        the buffer is still empty when the deadline arrives, drain
        whatever's there (probably still nothing) — same behavior
        as before, but the timeout becomes the safety net rather
        than the eager quiet-fire.
        """
        deadline = time.monotonic() + timeout
        last_len = -1
        last_change = time.monotonic()
        ever_nonempty = False
        while time.monotonic() < deadline:
            await asyncio.sleep(quiet_window / 2)
            cur_len = sum(len(t) for t in s._text_buf)
            if cur_len > 0:
                ever_nonempty = True
            if cur_len != last_len:
                last_len = cur_len
                last_change = time.monotonic()
                continue
            if time.monotonic() - last_change >= quiet_window:
                # Only break on "quiet" if we've actually seen text.
                # An empty buffer that never received anything is not
                # "quiet" — it's "hasn't started yet". Keep waiting
                # until the deadline.
                if ever_nonempty:
                    break
        return strip_ansi(s.drain_text())

    # ── DB convenience methods (the existing API contract) ────────────────

    async def room_id_by_slug(self, slug: str) -> int:
        """Resolve a room slug to its runtime DB id.

        SMOKE-SAFETY (May 18 2026, PVF-5 bug-fix drop): smoke
        scenarios MUST use this helper for any semantic dependency
        on a specific room — never hardcode integer DB ids.

        Why: YAML rooms in ``data/worlds/<era>/planets/*.yaml``
        carry author-assigned ``id:`` fields that start at 0 (or
        wherever the file starts), but those YAML ids do NOT survive
        intact into the DB. The world-writer uses ``db.create_room``
        which delegates id assignment to SQLite's ``AUTOINCREMENT``,
        and the schema's ``-- Seed data: starting room`` block in
        ``db/database.py`` pre-inserts a legacy Mos Eisley "Landing
        Pad" at id 1, "Mos Eisley Street" at id 2, and "Chalmun's
        Cantina" at id 3 BEFORE the YAML write runs. The CW YAML
        rooms therefore land at DB id 4 onwards — yaml_id 0
        (``docking_bay_94_entrance``) becomes DB id 4, yaml_id 1
        (``docking_bay_94_pit``) becomes DB id 5, etc.

        The PVF-5 scenario was the canary that surfaced this: it
        logged into ``room_id=1`` expecting ``docking_bay_94_pit``
        (SECURED via S-RES.2 zone walk), but DB id 1 is the legacy
        "Landing Pad" seed with ``zone_id=None`` and ``properties={}``
        — which resolves to CONTESTED by default, so the SECURED
        gate never fires.

        Use this helper to look up rooms by slug at scenario start:

            >>> sec_room = await h.room_id_by_slug("docking_bay_94_pit")
            >>> alice = await h.login_as("Alice", room_id=sec_room)

        Raises ``LookupError`` if the slug isn't in the world.
        """
        if not slug:
            raise LookupError("room_id_by_slug: empty slug")
        row = await self.db.get_room_by_slug(slug)
        if not row:
            raise LookupError(
                f"room_id_by_slug: no room with slug={slug!r} in this world. "
                f"Era: {self._era}. Check the world YAMLs or use a different "
                f"slug. (This helper exists so scenarios don't hardcode DB "
                f"ids — see helper docstring for the rationale.)"
            )
        return int(row["id"])

    async def room_slug_by_id(self, room_id: int) -> Optional[str]:
        """Resolve a room DB id back to its ``properties.slug`` value.

        The inverse of ``room_id_by_slug``. Used by the chain
        walkthrough smoke (drop 25) to assert the player has actually
        been moved (by the product's inter-step teleport) to each
        chain step's authored ``location`` slug before attempting that
        step's completion — the reachability gate. Returns None if the
        room has no slug (legacy / unmigrated room).
        """
        rows = await self.db.fetchall(
            "SELECT json_extract(properties, '$.slug') AS slug "
            "FROM rooms WHERE id = ?",
            (room_id,),
        )
        if not rows:
            return None
        return rows[0]["slug"]

    async def start_chain(self, name: str, chain_id: str, *,
                          skills: Optional[dict] = None,
                          credits: int = 500,
                          **login_kwargs) -> "_ClientSession":
        """Log in a fresh PC placed in `chain_id`'s REAL starting room
        with the tutorial-chain state seeded to step 1.

        This is the entry point for the per-chain walkthrough smoke
        (drop 25). Unlike the `_inject_chain` helper in
        scenarios/chain_attempt.py — which pre-places the player at a
        slugless room (room 1) so the reachability gate short-circuits —
        `start_chain` places the player in the chain's authored
        `starting_room`, so the walkthrough exercises the SAME
        reachability path a real chargen graduate walks.

        Seeds the `tutorial_chain` attrs block by mirroring
        `engine.tutorial_chains.select_chain`'s shape (step 1, active,
        no completed steps). It does NOT call any chain-event hook and
        does NOT pre-place the player at any step beyond 1 — all
        subsequent movement must come from the product (the inter-step
        teleport on advance).

        Raises LookupError if the chain has no starting_room (locked
        stubs) — those are not walkable and the scenario should skip
        them.
        """
        import json as _json
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain,
        )

        corpus = load_tutorial_chains(self._era)
        if corpus is None:
            raise LookupError(
                f"start_chain: era {self._era!r} has no tutorial chains "
                f"corpus (load_tutorial_chains returned None)."
            )
        chain = corpus.by_id().get(chain_id)
        if chain is None:
            raise LookupError(
                f"start_chain: no chain {chain_id!r} in the "
                f"{self._era!r} corpus."
            )
        if not chain.starting_room:
            raise LookupError(
                f"start_chain: chain {chain_id!r} has no starting_room "
                f"(locked stub?) — not walkable."
            )

        start_room_id = await self.room_id_by_slug(chain.starting_room)
        s = await self.login_as(
            name, room_id=start_room_id, credits=credits,
            skills=skills, **login_kwargs,
        )

        char_id = s.character["id"]
        char = await self.get_char(char_id)
        if char is None:
            raise LookupError(
                f"start_chain: character {name!r} (id {char_id}) not "
                f"found after login_as — the row was not created."
            )
        attrs = _json.loads(char.get("attributes") or "{}")
        select_chain(attrs, chain, now=1000000)
        await self.db.save_character(char_id, attributes=_json.dumps(attrs))
        s.character = await self.get_char(char_id)
        try:
            s.session.invalidate_char_obj()
        except AttributeError:
            pass
        return s

    async def get_char(self, char_id: int) -> Optional[dict]:
        """Reload a character row by ID. Used by tests after actions
        that mutate state on the server.

        Returns a plain dict so tests can use ``.get()`` and dict-style
        access uniformly. (The underlying ``aiosqlite.Row`` supports
        index/key access but not ``.get()``.)
        """
        rows = await self.db.fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,),
        )
        return dict(rows[0]) if rows else None

    async def get_credits(self, char_id: int) -> int:
        """Return the character's current credits."""
        row = await self.get_char(char_id)
        if not row:
            return 0
        return int(row.get("credits", 0) or 0)

    async def give_item(self, char_id: int, item: dict) -> None:
        """Insert ``item`` into the character's inventory.

        ``item`` is a dict with at least ``name`` and ``slot`` keys; the
        format matches what ``parser/builtin_commands.py`` produces.
        """
        row = await self.get_char(char_id)
        if not row:
            raise ValueError(f"give_item: no character with id={char_id}")
        # QA H14 (2026-06-20): inventory has two valid on-disk shapes — the
        # canonical dict-form ``{"items": [...], "resources": [...]}`` (written
        # by db.add_to_inventory / the crafting helpers) and the bare-list
        # default. The old ``inv.append(item)`` crashed on dict-form (dicts
        # have no .append), masking real defects by killing test runs. Mirror
        # db.add_to_inventory: coerce to the canonical shape and append to
        # ``items``, so the harness works on either shape.
        from engine.items import coerce_inventory
        inv = coerce_inventory(row.get("inventory"))
        inv["items"].append(item)
        await self.db._db.execute(
            "UPDATE characters SET inventory = ? WHERE id = ?",
            (json.dumps(inv), char_id),
        )
        await self.db._db.commit()

    # ── SH7: tick advancement + two-ship combat fixture ───────────────────

    async def advance_ticks(self, n: int = 1) -> None:
        """Manually advance the simulation by ``n`` ticks.

        The harness boots ``GameServer`` but does NOT start its async
        tick loop (the ``start()`` call is skipped to avoid binding
        sockets). For tests that need tick-driven progression — sublight
        transit countdowns, ion-stun decay, hyperspace arrival, NPC
        space traffic spawning, ship-on-ship combat resolution — call
        this helper to manually drive the scheduler.

        Implementation: builds a synthetic ``TickContext`` with a
        monotonically increasing ``tick_count`` and a fresh
        ``ships_in_space`` snapshot, then calls
        ``server._tick_scheduler.run_tick(ctx)``. Same code path
        production uses.
        """
        from server.tick_scheduler import TickContext

        if n < 1:
            return

        # Track our own tick counter so multiple advance_ticks calls
        # remain monotonic across a single test class run.
        if not hasattr(self, "_smoke_tick_count"):
            self._smoke_tick_count = 0

        for _ in range(n):
            self._smoke_tick_count += 1
            ships = await self.db.get_ships_in_space()
            ctx = TickContext(
                server=self.server,
                db=self.db,
                session_mgr=self.server.session_mgr,
                tick_count=self._smoke_tick_count,
                ships_in_space=list(ships),
            )
            await self.server._tick_scheduler.run_tick(ctx)

    async def setup_two_ship_combat(
        self,
        attacker_name: str,
        defender_name: str,
        *,
        attacker_ship_idx: int = 0,
        defender_ship_idx: int = 1,
    ) -> dict:
        """Set up the canonical two-ship combat fixture.

        Returns a dict with the keys needed by combat scenarios::

            {
              "attacker_session": <_ClientSession>,
              "attacker_ship": (id, name, dock_room, bridge_room),
              "defender_session": <_ClientSession>,
              "defender_ship": (id, name, dock_room, bridge_room),
            }

        Both ships start docked at Mos Eisley bays (so they end up in
        the same ``tatooine_orbit`` zone after launch). The attacker
        pilots their ship, takes a gunner station, and launches; the
        defender pilots their ship and launches. Both ships are now
        in space in the same zone, with the attacker positioned to
        ``lockon <defender>`` and ``fire <defender>``.

        Caller is responsible for cleanup (``land`` + ``vacate`` on
        both, or accept that the harness fixture is class-scoped and
        will tear down at class end).

        ``attacker_ship_idx`` / ``defender_ship_idx`` index into the
        list of docked ships ordered by id; defaults to ships 0 and 1
        which are Rusty Mynock (dock 5) and Dusty Hawk (dock 8).
        """
        rows = await self.db.fetchall(
            "SELECT id, name, docked_at, bridge_room_id FROM ships "
            "WHERE docked_at IS NOT NULL ORDER BY id"
        )
        ships = [
            (int(r["id"]), r["name"], int(r["docked_at"]),
             int(r["bridge_room_id"]))
            for r in rows
        ]
        if len(ships) < 2:
            raise RuntimeError(
                f"setup_two_ship_combat needs at least 2 docked ships, "
                f"world has {len(ships)}."
            )
        if max(attacker_ship_idx, defender_ship_idx) >= len(ships):
            raise IndexError(
                f"ship indices out of range: attacker={attacker_ship_idx}, "
                f"defender={defender_ship_idx}, ships={len(ships)}"
            )
        if attacker_ship_idx == defender_ship_idx:
            raise ValueError("attacker and defender must be different ships")

        att_ship = ships[attacker_ship_idx]
        def_ship = ships[defender_ship_idx]

        # Attacker: log in at the dock, board, take pilot, take gunner,
        # launch. Note: pilot first (to be authorized to launch), THEN
        # gunner (which auto-vacates pilot if same player). So we use
        # a different sequence: launch first, then take gunner.
        att_token = att_ship[1].split()[0].lower()
        att_session = await self.login_as(
            attacker_name, room_id=att_ship[2], credits=5000,
        )
        await self.cmd(att_session, f"board {att_token}")
        await self.cmd(att_session, "pilot")
        await self.cmd(att_session, "launch")
        # After launch, vacate pilot (so we can take gunner). The
        # combat-fire path requires the firing PC to be at a gunner
        # station, not pilot.
        await self.cmd(att_session, "vacate")
        await self.cmd(att_session, "gunner")

        # Defender: same idea but stay at pilot. (No need to be at
        # gunner; they're not firing in the basic fixture.)
        def_token = def_ship[1].split()[0].lower()
        def_session = await self.login_as(
            defender_name, room_id=def_ship[2], credits=5000,
        )
        await self.cmd(def_session, f"board {def_token}")
        await self.cmd(def_session, "pilot")
        await self.cmd(def_session, "launch")

        return {
            "attacker_session": att_session,
            "attacker_ship": att_ship,
            "defender_session": def_session,
            "defender_ship": def_ship,
        }

    # ── failure-triage debug dump (design §9.2 Q5) ────────────────────────

    async def dump_for_failure(self, s: _ClientSession,
                               failures_dir: str,
                               scenario_name: str) -> None:
        """Write a debug bundle to *failures_dir*/*scenario_name*/
        with the session transcript, JSON events, and key DB rows.

        Called from the pytest hook in ``conftest.py`` when a scenario
        fails. The bundle is what Brian needs to repro manually:
        what the player saw, what JSON the client received, and what
        the DB looked like at failure time.
        """
        os.makedirs(failures_dir, exist_ok=True)
        out_dir = os.path.join(failures_dir, scenario_name)
        os.makedirs(out_dir, exist_ok=True)

        # Transcript (text the "player" saw).
        with open(os.path.join(out_dir, "transcript.txt"),
                  "w", encoding="utf-8") as f:
            f.write("".join(s._text_buf) or "(no text captured)")

        # JSON events (typed payloads — combat_state, hud_update, etc.).
        with open(os.path.join(out_dir, "json_events.json"),
                  "w", encoding="utf-8") as f:
            json.dump(s._json_events_or_buf(), f, indent=2, default=str)

        # Character row.
        try:
            if s.session.character:
                char = await self.get_char(s.session.character["id"])
                with open(os.path.join(out_dir, "character.json"),
                          "w", encoding="utf-8") as f:
                    json.dump(dict(char) if char else None, f,
                              indent=2, default=str)
        except Exception:
            pass

        # Room row.
        try:
            if s.session.character:
                rm_id = s.session.character.get("room_id")
                rooms = await self.db.fetchall(
                    "SELECT * FROM rooms WHERE id = ?", (rm_id,),
                )
                with open(os.path.join(out_dir, "room.json"),
                          "w", encoding="utf-8") as f:
                    json.dump([dict(r) for r in rooms], f,
                              indent=2, default=str)
        except Exception:
            pass


# Bridge method on _ClientSession that dump_for_failure calls. Defined
# here so the json_events buffer can be accessed without breaking the
# public attribute / private buffer convention.
def _client_session_json_events_or_buf(self):
    return list(self._json_buf)
_ClientSession._json_events_or_buf = _client_session_json_events_or_buf


# ───────────────────────────────────────────────────────────────────────────
# Pytest fixture
# ───────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="class")
async def harness(request):
    """Pytest fixture (class-scoped): live in-process integration harness.

    Per design §9 (Brian's answer): per-class temp DB. All tests in a
    pytest class share one booted GameServer + temp SQLite. Different
    classes get different harnesses.

    Era resolution order (first match wins):
      1. Class attribute ``smoke_era = "..."`` on the test class
      2. ``request.param`` if the class is parameterized via
         ``@pytest.mark.parametrize("harness_era", [...])`` and
         indirectly fed through this fixture (advanced; SH3+ uses a
         different mechanism — see §3 of the SH3 handoff)
      3. ``--smoke-era`` CLI flag
      4. Default ``"clone_wars"``

    The default flipped from ``"gcw"`` to ``"clone_wars"`` in May 2026
    when the project hard-pivoted to Clone Wars as the primary launch
    era. Most engine surfaces (movement, comms, combat, economy,
    missions, factions, housing, medical, tutorial) are era-agnostic
    so the existing scenarios validate the same code paths under
    either era — they just exercise CW content (Republic/CIS NPCs,
    Coruscant rooms, Mu-class shuttles) instead of GCW (Tuskens,
    Mos Eisley, YT-1300s). Era-explicit GCW scenarios are pinned via
    ``smoke_era = "gcw"`` on their class (see TestGCWEra).
    """
    era = "clone_wars"
    # 1. Class attribute
    if request.cls is not None:
        era = getattr(request.cls, "smoke_era", era)
    # 2. Parametrize (best-effort)
    try:
        param = request.param  # raises AttributeError if not parameterized
        if isinstance(param, dict) and "era" in param:
            era = param["era"]
        elif isinstance(param, str):
            era = param
    except AttributeError:
        pass
    # 3. CLI fallback (only if class didn't pin it)
    if not getattr(request.cls, "smoke_era", None):
        try:
            cli_era = request.config.getoption("--smoke-era", default=era)
            era = cli_era or era
        except (ValueError, KeyError):
            pass

    h = await _LiveHarness.boot(era=era)
    try:
        yield h
    finally:
        await h.shutdown()
