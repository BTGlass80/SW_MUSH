"""Field Kit Drop B' — player command narration migration regression.

Per `field_kit_design_decomposition_v2.md` §4 (lines 228-234) and §10:

  Drop B' migrates player-issued narration commands to the typed
  pose_event factory so the entire narration pipeline goes through one
  code path. Player commands were already attributed correctly via the
  classifyAndAppend regex fallback today; this drop is consistency
  work, not bug-fix work, and gates eventual deprecation of the
  fallback (per §8.3).

Scope (this drop):
  · SayCommand (parser/builtin_commands.py)
  · WhisperCommand (parser/builtin_commands.py)
  · EmoteCommand / `:` / `pose` / `em` (parser/builtin_commands.py)
  · MutterCommand (parser/places_commands.py)

Out of scope for B' (deferred):
  · SemiposeCommand (`;`) — the no-space-between-name-and-text
    formatting (`Tundra's lightsaber hums`) doesn't fit the typed
    schema's {who, text} separation cleanly. Adding it would require
    a new event_type or a SemiposeMode flag; ship as a follow-up.
  · CombatPoseCommand (`cpose`) — not a narration emit site. The
    pose text is stored on combat state and emitted by the engine
    during the resolution phase; that's Drop B (combat narration)
    territory, not B'.

What these tests verify:
  · Telnet fallback renders pose-with-`to`-and-`mode` correctly
    (the new path that mutter relies on)
  · broadcast_json_to_room's new `exclude` parameter works (Session,
    list-of-IDs, and None forms)
  · Per-emit-site static regression: each migrated command imports
    and uses the typed factory; the legacy text broadcast is gone
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine.pose_events import (
    EVENT_POSE,
    EVENT_SAY,
    EVENT_WHISPER,
    make_pose_event,
)


ROOT = Path(__file__).parent.parent


# ────────────────────────────────────────────────────────────────────
# Telnet fallback for the new pose-with-`to`-and-`mode` shape
# ────────────────────────────────────────────────────────────────────


@pytest.fixture
def telnet_session():
    """Minimal Session-like object that records Telnet send_line calls.

    Mirrors the fixture in test_field_kit_drop_b.py so the rendering
    contract for both drops stays in lock-step.
    """
    from server.session import Session, Protocol, SessionState

    sess = Session.__new__(Session)
    sess.protocol = Protocol.TELNET
    sess.state = SessionState.IN_GAME
    sess._sent: list[str] = []

    async def _send(text: str):
        sess._sent.append(text)

    async def _send_line(text: str):
        sess._sent.append(text)

    sess._send = _send
    sess.send_line = _send_line
    return sess


class TestTelnetPoseWithTargetFallback:
    """The Telnet branch for `event_type in ('pose', 'emote')` learned to
    render `to`/`mode` in Drop B'. Mutter uses this path; whisper doesn't
    (whisper has its own branch). These tests pin the rendering contract."""

    @pytest.mark.asyncio
    async def test_pose_without_to_renders_legacy_form(self, telnet_session):
        """Plain pose (no `to`) keeps the Drop B rendering exactly:
        `<who> <text>` with no quoting. Mutter's mode awareness must
        not regress NPC poses."""
        ev = make_pose_event(EVENT_POSE, "wipes his hands.", who="Yenn", mode="poses")
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ["Yenn wipes his hands."]

    @pytest.mark.asyncio
    async def test_pose_with_to_and_mutters_renders_quoted(self, telnet_session):
        """Mutter's wire shape: pose+to+mode='mutters'. Renders as
        'Tundra mutters to Han, "..."'."""
        ev = make_pose_event(
            EVENT_POSE, "Meet me at bay 94.",
            who="Tundra", mode="mutters", to="Han",
        )
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ['Tundra mutters to Han, "Meet me at bay 94."']

    @pytest.mark.asyncio
    async def test_pose_with_to_defaults_mode_when_blank(self, telnet_session):
        """If `to` is set but `mode` is empty, the Telnet fallback
        defaults to 'poses'. Defensive — guards against future call
        sites that forget to set mode explicitly."""
        # make_pose_event drops empty `mode` from the payload; rebuild
        # by hand so we can pin the fallback branch directly.
        ev = {"event_type": "pose", "who": "Tundra", "text": "...",
              "to": "Han"}
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ['Tundra poses to Han, "..."']

    @pytest.mark.asyncio
    async def test_emote_with_to_uses_same_branch(self, telnet_session):
        """event_type 'emote' is an alias of 'pose' on the client; the
        Telnet branch handles both identically. Verify the new
        to/mode-aware rendering applies to 'emote' too."""
        ev = make_pose_event(
            EVENT_POSE, "growl.",
            who="Greedo", mode="growls", to="Han",
        )
        # Override to emote variant to confirm symmetry.
        ev["event_type"] = "emote"
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ['Greedo growls to Han, "growl."']


# ────────────────────────────────────────────────────────────────────
# broadcast_json_to_room learned the `exclude` parameter
# ────────────────────────────────────────────────────────────────────


def _read(relpath: str) -> str:
    p = ROOT / relpath
    assert p.exists(), f"missing {p}"
    return p.read_text(encoding="utf-8")


class TestBroadcastJsonExcludeParam:
    """Static-file checks that broadcast_json_to_room signature gained
    an optional `exclude` param mirroring broadcast_to_room's contract."""

    def test_signature_has_exclude(self):
        text = _read("server/session.py")
        # Must accept exclude=None as keyword arg in signature
        m = re.search(
            r"async def broadcast_json_to_room\([^)]*exclude\s*=\s*None",
            text, re.DOTALL,
        )
        assert m, (
            "broadcast_json_to_room signature missing exclude=None — "
            "Drop B' regression"
        )

    def test_exclude_handles_session_and_list(self):
        """The implementation must support both calling conventions:
        a Session object OR a list of character IDs. The MutterCommand
        migration relies on the list-of-IDs form to skip both actor and
        target in one call."""
        text = _read("server/session.py")
        # Find the broadcast_json_to_room body.
        m = re.search(
            r"async def broadcast_json_to_room\([^)]*\):"
            r"(.*?)(?=\n    async def |\n    def |\nclass )",
            text, re.DOTALL,
        )
        assert m, "couldn't isolate broadcast_json_to_room body"
        body = m.group(1)
        # Both branches must be present.
        assert "isinstance(exclude, list)" in body, (
            "broadcast_json_to_room: list-of-IDs exclude path missing"
        )
        assert "excluded_sess" in body, (
            "broadcast_json_to_room: Session-object exclude path missing"
        )


# ────────────────────────────────────────────────────────────────────
# Per-emit-site regression: each migrated command uses the factory
# ────────────────────────────────────────────────────────────────────


class TestSayMigration:
    """SayCommand emits typed pose_event to room observers (excluding
    actor) and keeps the actor's send_line self-echo."""

    def test_uses_make_pose_event_with_event_say(self):
        text = _read("parser/builtin_commands.py")
        # The migration block sits inside SayCommand.execute. Check both
        # the import line and the EVENT_SAY constant are referenced.
        assert "EVENT_SAY" in text, (
            "SayCommand no longer references EVENT_SAY — Drop B' regression"
        )
        assert "make_pose_event" in text, (
            "SayCommand no longer imports make_pose_event — Drop B' regression"
        )

    def test_uses_broadcast_json_to_room(self):
        text = _read("parser/builtin_commands.py")
        # SayCommand should now hit broadcast_json_to_room with pose_event.
        assert "broadcast_json_to_room" in text, (
            "builtin_commands.py no longer uses broadcast_json_to_room — "
            "Drop B' regression"
        )

    def test_drops_old_text_broadcast(self):
        """The pre-migration path called broadcast_to_room with `full_text`.
        That call site must be gone from SayCommand specifically. We
        scope by extracting SayCommand.execute's body."""
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class SayCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        assert m, "couldn't isolate SayCommand body"
        body = m.group(1)
        # Old pattern: broadcast_to_room(room_id, full_text, exclude=...)
        offending = re.compile(
            r"broadcast_to_room\(\s*\n?\s*room_id\s*,\s*full_text\b"
        )
        assert not offending.search(body), (
            "Old broadcast_to_room(full_text) path still present in "
            "SayCommand — Drop B' regression"
        )

    def test_keeps_self_echo(self):
        """The actor's local 'You say, "..."' confirmation must remain.
        Self-echo is a command-acknowledgement, not narration; it stays
        as send_line per Drop B's narration-vs-system distinction."""
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class SayCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        body = m.group(1)
        assert 'You say, "' in body, (
            "SayCommand self-echo lost during Drop B' migration"
        )


class TestWhisperMigration:
    """WhisperCommand emits typed pose_event with event_type=whisper,
    mode=whispers, to=<target_name> to the target only."""

    def test_uses_make_pose_event_with_event_whisper(self):
        text = _read("parser/builtin_commands.py")
        assert "EVENT_WHISPER" in text, (
            "WhisperCommand no longer references EVENT_WHISPER — "
            "Drop B' regression"
        )

    def test_drops_old_target_send_line(self):
        """Pre-migration: target_session.send_line(f'{name} whispers to
        you, "..."'). That literal pattern must be gone from
        WhisperCommand."""
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class WhisperCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        assert m, "couldn't isolate WhisperCommand body"
        body = m.group(1)
        # The old pattern was a target_session.send_line with the
        # 'whispers to you' string.
        offending = re.compile(
            r"target_session\.send_line\([^)]*whispers to you",
            re.DOTALL,
        )
        assert not offending.search(body), (
            "Old target_session.send_line(whispers to you) path still "
            "present in WhisperCommand — Drop B' regression"
        )

    def test_target_now_receives_send_json(self):
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class WhisperCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        body = m.group(1)
        # The migrated path sends a typed pose_event to target_session.
        assert re.search(
            r'target_session\.send_json\(\s*"pose_event"',
            body,
        ), (
            "WhisperCommand: target_session.send_json('pose_event', ...) "
            "missing — Drop B' regression"
        )


class TestEmoteMigration:
    """EmoteCommand (key='emote', aliases=':', 'pose', 'em') broadcasts
    typed pose_event to the room (including actor — preserves legacy
    behavior of the per-session send_line loop)."""

    def test_uses_make_pose_event_with_event_pose(self):
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class EmoteCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        assert m, "couldn't isolate EmoteCommand body"
        body = m.group(1)
        assert "EVENT_POSE" in body, (
            "EmoteCommand no longer references EVENT_POSE — Drop B' regression"
        )
        assert "make_pose_event" in body, (
            "EmoteCommand no longer references make_pose_event — "
            "Drop B' regression"
        )

    def test_drops_per_session_send_line_loop(self):
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class EmoteCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        body = m.group(1)
        # Old pattern: 'for s in ctx.session_mgr.sessions_in_room(room_id):'
        # immediately followed by 'await s.send_line(text)'. Both lines
        # together is the offending regression.
        offending = re.compile(
            r"for s in ctx\.session_mgr\.sessions_in_room\(room_id\):"
            r"\s*\n\s*await s\.send_line\(text\)",
        )
        assert not offending.search(body), (
            "EmoteCommand still uses per-session send_line loop — "
            "Drop B' regression"
        )


class TestMutterMigration:
    """MutterCommand emits typed pose_event with event_type=pose,
    mode=mutters, to=<target>. Target gets full message; room observers
    get muffled message; actor gets send_line confirmation."""

    def test_uses_make_pose_event(self):
        text = _read("parser/places_commands.py")
        assert "make_pose_event" in text, (
            "places_commands.py no longer imports make_pose_event — "
            "Drop B' regression (MutterCommand)"
        )
        assert "EVENT_POSE" in text, (
            "places_commands.py no longer references EVENT_POSE — "
            "Drop B' regression (MutterCommand)"
        )

    def test_uses_mutters_mode_string(self):
        text = _read("parser/places_commands.py")
        # Must explicitly set mode='mutters' — that's the verb the
        # Telnet fallback and the client header both render.
        assert 'mode="mutters"' in text or "mode='mutters'" in text, (
            "MutterCommand no longer sets mode='mutters' — Drop B' regression"
        )

    def test_drops_old_target_send_line(self):
        text = _read("parser/places_commands.py")
        m = re.search(
            r"class MutterCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b|\n# ═)",
            text, re.DOTALL,
        )
        assert m, "couldn't isolate MutterCommand body"
        body = m.group(1)
        # Old pattern: target_sess.send_line(f"... mutters to you ...")
        offending = re.compile(
            r"target_sess\.send_line\([^)]*mutters to you",
            re.DOTALL,
        )
        assert not offending.search(body), (
            "Old target_sess.send_line(mutters to you) path still "
            "present in MutterCommand — Drop B' regression"
        )

    def test_drops_old_room_muffled_loop(self):
        text = _read("parser/places_commands.py")
        m = re.search(
            r"class MutterCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b|\n# ═)",
            text, re.DOTALL,
        )
        body = m.group(1)
        # Old pattern: a per-session loop that called s.send_line(muffled_msg).
        # We assert the literal old construction is gone.
        offending = re.compile(
            r"for s in ctx\.session_mgr\.sessions_in_room\(room_id\):"
            r"\s*\n\s*if s is ctx\.session or s is target_sess:",
        )
        assert not offending.search(body), (
            "Old per-session muffled send_line loop still present in "
            "MutterCommand — Drop B' regression"
        )

    def test_uses_broadcast_json_to_room_with_exclude(self):
        text = _read("parser/places_commands.py")
        m = re.search(
            r"class MutterCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b|\n# ═)",
            text, re.DOTALL,
        )
        body = m.group(1)
        # The migrated room broadcast uses broadcast_json_to_room with
        # exclude= (so actor and target both get skipped).
        assert "broadcast_json_to_room" in body, (
            "MutterCommand: muffled-room path no longer uses "
            "broadcast_json_to_room — Drop B' regression"
        )
        assert "exclude=" in body, (
            "MutterCommand: broadcast_json_to_room call no longer passes "
            "exclude= — Drop B' regression"
        )

    def test_keeps_self_echo(self):
        """Actor confirmation 'You mutter to <X>, "..."' must remain —
        it's a command echo, not narration."""
        text = _read("parser/places_commands.py")
        m = re.search(
            r"class MutterCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b|\n# ═)",
            text, re.DOTALL,
        )
        body = m.group(1)
        assert "You mutter to" in body, (
            "MutterCommand self-echo lost during Drop B' migration"
        )


# ────────────────────────────────────────────────────────────────────
# Out-of-scope reminder: SemiposeCommand intentionally NOT migrated
# ────────────────────────────────────────────────────────────────────


class TestSemiposeIntentionallyNotMigrated:
    """SemiposeCommand (`;`) is deferred from Drop B'. The no-space-
    between-name-and-text formatting (`Tundra's lightsaber hums`)
    doesn't fit the typed schema's {who, text} separation cleanly —
    the client renders `<who> <mode>` then `<body>`, which inserts a
    space between the name and what should be glued text. Adding
    semipose support would require a new event_type or a SemiposeMode
    flag; ship as a follow-up. This test pins the deferral so a
    casual reviewer doesn't 'fix' it accidentally."""

    def test_semipose_still_uses_send_line(self):
        text = _read("parser/builtin_commands.py")
        m = re.search(
            r"class SemiposeCommand\(BaseCommand\):"
            r"(.*?)(?=\nclass [A-Z]\w*Command\b)",
            text, re.DOTALL,
        )
        assert m, "couldn't isolate SemiposeCommand body"
        body = m.group(1)
        # If someone migrates this, they need to also handle the no-space
        # rendering on Telnet. Until that lands, the legacy path is
        # deliberate.
        assert "send_line(text)" in body, (
            "SemiposeCommand was migrated — re-evaluate Telnet rendering "
            "for the no-space-between-name-and-text formatting before "
            "removing this test."
        )
