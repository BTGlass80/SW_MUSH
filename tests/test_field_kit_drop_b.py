"""Field Kit Drop B — pose_event factory + emit-site regression tests.

Per `field_kit_design_decomposition_v2.md` §4. Covers:

  · engine/pose_events.py factory functions: shape, dedup-key
    composition (D5), schema alignment with the live client
  · server/session.py send_json("pose_event", ...) Telnet fallback
    rendering for each event_type — Telnet players still see the
    narration even though they don't get the typed JSON
  · Per-emit-site regression: each migrated narration path uses the
    typed pose_event factory rather than send_line / broadcast_to_room

What the tests intentionally DO NOT verify:
  · End-to-end rendering on the WebSocket client (covered elsewhere
    by the field-kit-drop-a primitives suite + manual QA)
  · Player command paths (say/pose/whisper/mutter) — those are Drop B'
  · combat.py narration outside the posing panel — deferred to a
    follow-up Drop B session

If a previously-migrated site reverts to send_line (intentionally or
accidentally), the per-site regression tests catch it via static
file inspection.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine.pose_events import (
    EVENT_COMM_IN,
    EVENT_DESC_INLINE,
    EVENT_POSE,
    EVENT_SAY,
    EVENT_SYS_EVENT,
    EVENT_WHISPER,
    make_ambient_event,
    make_dedup_key,
    make_npc_pose,
    make_npc_say,
    make_pose_event,
    make_system_event,
)


ROOT = Path(__file__).parent.parent


# ───────────────────────────────────────────────────────────────────────
# Factory shape
# ───────────────────────────────────────────────────────────────────────


class TestPoseEventFactoryShape:

    def test_make_pose_event_basic(self):
        ev = make_pose_event(EVENT_POSE, "looks around", who="Yenn")
        assert ev["event_type"] == "pose"
        assert ev["who"] == "Yenn"
        assert ev["text"] == "looks around"
        # D5: composite dedup key + timestamp_ms always present.
        assert "deduplication_key" in ev
        assert "timestamp_ms" in ev
        assert isinstance(ev["timestamp_ms"], int)

    def test_make_pose_event_drops_empty_optionals(self):
        """Optional fields (mode, to, speaker_id) shouldn't appear in
        the wire payload if not populated — keeps payloads tight and
        the client doesn't end up consuming nulls."""
        ev = make_pose_event(EVENT_POSE, "x", who="Yenn")
        # mode/to/speaker_id are optional and absent here.
        assert "mode" not in ev
        assert "to" not in ev
        assert "speaker_id" not in ev

    def test_make_pose_event_includes_optionals_when_set(self):
        ev = make_pose_event(
            EVENT_WHISPER, "secret",
            who="Yenn",
            speaker_id=42,
            mode="whispers",
            to="Mak",
        )
        assert ev["mode"] == "whispers"
        assert ev["to"] == "Mak"
        assert ev["speaker_id"] == 42

    def test_explicit_timestamp_override(self):
        ev = make_pose_event(EVENT_SAY, "x", who="A", timestamp_ms=12345)
        assert ev["timestamp_ms"] == 12345

    def test_explicit_dedup_key_override(self):
        ev = make_pose_event(
            EVENT_SAY, "x", who="A",
            deduplication_key="custom:key:abc",
        )
        assert ev["deduplication_key"] == "custom:key:abc"


# ───────────────────────────────────────────────────────────────────────
# Dedup key composition (D5)
# ───────────────────────────────────────────────────────────────────────


class TestDedupKey:

    def test_format_is_three_part_colon(self):
        k = make_dedup_key(42, "hello", 1000)
        parts = k.split(":")
        assert len(parts) == 3
        assert parts[0] == "42"
        assert parts[1] == "1000"
        # text hash is sha1[:8] hex
        assert re.fullmatch(r"[0-9a-f]{8}", parts[2])

    def test_speaker_id_none_uses_system(self):
        k = make_dedup_key(None, "hi", 1000)
        assert k.startswith("system:")

    def test_distinct_keys_for_distinct_inputs(self):
        a = make_dedup_key(42, "hello", 1000)
        b = make_dedup_key(42, "hello", 1001)  # diff timestamp
        c = make_dedup_key(42, "world", 1000)  # diff text
        d = make_dedup_key(43, "hello", 1000)  # diff speaker
        assert len({a, b, c, d}) == 4

    def test_same_inputs_yield_same_key(self):
        """Stable for replay / idempotency."""
        a = make_dedup_key(42, "hello", 1000)
        b = make_dedup_key(42, "hello", 1000)
        assert a == b


# ───────────────────────────────────────────────────────────────────────
# Convenience wrappers
# ───────────────────────────────────────────────────────────────────────


class TestConvenienceWrappers:

    def test_make_ambient_event(self):
        ev = make_ambient_event("Dust drifts through the doorway.")
        assert ev["event_type"] == EVENT_DESC_INLINE
        assert ev["who"] == ""
        assert ev["text"] == "Dust drifts through the doorway."

    def test_make_system_event(self):
        ev = make_system_event("Targeting lock acquired")
        assert ev["event_type"] == EVENT_SYS_EVENT
        assert ev["who"] == ""
        assert ev["text"] == "Targeting lock acquired"

    def test_make_npc_say(self):
        ev = make_npc_say("Yenn", "Move along.", npc_id=42)
        assert ev["event_type"] == EVENT_SAY
        assert ev["who"] == "Yenn"
        assert ev["mode"] == "says"
        assert ev["speaker_id"] == 42

    def test_make_npc_pose(self):
        ev = make_npc_pose("Yenn", "wipes his hands.", npc_id=42)
        assert ev["event_type"] == EVENT_POSE
        assert ev["who"] == "Yenn"
        assert ev["mode"] == "poses"
        assert ev["speaker_id"] == 42


# ───────────────────────────────────────────────────────────────────────
# Telnet fallback rendering (server/session.py send_json("pose_event"))
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def telnet_session():
    """Build a minimal Session-like object that records Telnet
    send_line calls. We exercise the live send_json codepath
    (Protocol.TELNET branch) without standing up a real socket.
    """
    from server.session import Session, Protocol, SessionState

    sess = Session.__new__(Session)
    sess.protocol = Protocol.TELNET
    sess.state = SessionState.IN_GAME
    sess._sent: list[str] = []

    async def _send(text: str):
        sess._sent.append(text)

    async def _send_line(text: str):
        # Mirror real send_line: append text + newline-equivalent.
        sess._sent.append(text)

    sess._send = _send
    sess.send_line = _send_line
    return sess


class TestTelnetFallback:

    @pytest.mark.asyncio
    async def test_say_renders_with_quote(self, telnet_session):
        ev = make_npc_say("Yenn", "Move along.")
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ['Yenn says, "Move along."']

    @pytest.mark.asyncio
    async def test_pose_renders_with_speaker(self, telnet_session):
        ev = make_npc_pose("Yenn", "wipes his hands.")
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ["Yenn wipes his hands."]

    @pytest.mark.asyncio
    async def test_whisper_renders_with_to(self, telnet_session):
        ev = make_pose_event(
            EVENT_WHISPER, "secret",
            who="Yenn", mode="whispers", to="Mak",
        )
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ['Yenn whispers to Mak, "secret"']

    @pytest.mark.asyncio
    async def test_ambient_renders_text_only(self, telnet_session):
        ev = make_ambient_event("Dust drifts through.")
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ["Dust drifts through."]

    @pytest.mark.asyncio
    async def test_system_event_renders_text_only(self, telnet_session):
        ev = make_system_event("BOARDING ALERT")
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ["BOARDING ALERT"]

    @pytest.mark.asyncio
    async def test_empty_text_drops_silently(self, telnet_session):
        """Empty text == nothing to render. Don't spam the Telnet
        client with blank lines."""
        ev = make_system_event("")
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == []

    @pytest.mark.asyncio
    async def test_unknown_event_type_renders_bare_text(self, telnet_session):
        """If we add a new event_type later and forget to wire its
        Telnet branch, we should still render the text — never silently
        drop narration."""
        ev = {"event_type": "future-event-type", "who": "", "text": "still visible"}
        await telnet_session.send_json("pose_event", ev)
        assert telnet_session._sent == ["still visible"]


# ───────────────────────────────────────────────────────────────────────
# Per-emit-site regression: each migrated path uses the typed factory
# ───────────────────────────────────────────────────────────────────────


class TestEmitSiteRegression:
    """Static-file checks that each migrated emit path uses the typed
    pose_event factory. If any of these regress to send_line /
    broadcast_to_room, narration falls back to the legacy regex path
    on the client and risks mis-attribution."""

    def _read(self, relpath: str) -> str:
        p = ROOT / relpath
        assert p.exists(), f"missing {p}"
        return p.read_text(encoding="utf-8")

    def test_ambient_events_uses_pose_event(self):
        text = self._read("engine/ambient_events.py")
        assert "make_ambient_event" in text, (
            "ambient_events.py no longer imports make_ambient_event — "
            "Drop B regression"
        )
        assert "broadcast_json_to_room" in text, (
            "ambient_events.py no longer uses broadcast_json_to_room — "
            "Drop B regression"
        )

    def test_ambient_events_dropped_old_broadcast(self):
        """The pre-migration path used broadcast_to_room with a
        formatted ANSI string. That call site must be gone."""
        text = self._read("engine/ambient_events.py")
        # Search for the specific old pattern: broadcast_to_room with a
        # variable named `formatted` (the old f-string).
        offending = re.compile(
            r"broadcast_to_room\(\s*room_id\s*,\s*formatted\b"
        )
        assert not offending.search(text), (
            "Old broadcast_to_room(formatted) path still present — Drop B regression"
        )

    def test_hazards_uses_pose_event(self):
        text = self._read("engine/hazards.py")
        assert "make_system_event" in text, (
            "hazards.py no longer imports make_system_event — Drop B regression"
        )
        # The pickpocket narrative line uses make_ambient_event.
        assert "make_ambient_event" in text, (
            "hazards.py pickpocket narrative no longer uses make_ambient_event"
        )

    def test_hazards_passed_send_line_now_typed(self):
        """The hazard-passed atmospheric message no longer calls send_line
        with a multi-line ANSI string."""
        text = self._read("engine/hazards.py")
        # The old pattern was: msg = f"\n  {DIM}[...]{RST} {GREEN}...{RST}"
        # then await session.send_line(msg). Look for the f-string pattern
        # combined with send_line in the hazard_check function area.
        # If we see the literal `pass_text` interpolated into a send_line
        # f-string, the migration regressed.
        pattern = re.compile(
            r"send_line\([^)]*pass_text", re.MULTILINE | re.DOTALL
        )
        assert not pattern.search(text), (
            "Hazard pass_text still routed through send_line — regression"
        )

    def test_director_pc_hook_uses_pose_event(self):
        text = self._read("engine/director.py")
        # All three delivery branches (comlink_message, npc_whisper,
        # news_item fallback) should now emit pose_event.
        assert "EVENT_COMM_IN" in text, (
            "director.py no longer references EVENT_COMM_IN — comlink "
            "delivery may have regressed"
        )
        assert "EVENT_WHISPER" in text, (
            "director.py no longer references EVENT_WHISPER — npc_whisper "
            "delivery may have regressed"
        )
        # The old pattern was: prefix = ansi.color("[COMLINK] "...) +
        # send_line(f"{prefix}{content}"). That should be gone.
        assert "ansi.color(\"[COMLINK] \"" not in text, (
            "Old [COMLINK] send_line prefix still present — Drop B regression"
        )

    def test_space_encounters_broadcast_uses_pose_event(self):
        text = self._read("engine/space_encounters.py")
        assert "make_system_event" in text, (
            "space_encounters.broadcast_to_bridge no longer uses "
            "make_system_event — encounter narration regression"
        )
        assert "broadcast_json_to_room" in text, (
            "space_encounters no longer uses broadcast_json_to_room"
        )
        # The pre-migration path called session_mgr.broadcast_to_room
        # directly. That should be gone from broadcast_to_bridge.
        # We check for the specific text pattern of the old call.
        old_pattern = re.compile(
            r"broadcast_to_room\(enc\.target_bridge_room,\s*message\b"
        )
        assert not old_pattern.search(text), (
            "Old broadcast_to_room path in broadcast_to_bridge — regression"
        )

    def test_npc_dialogue_uses_make_npc_say(self):
        text = self._read("parser/npc_commands.py")
        assert "make_npc_say" in text, (
            "npc_commands.py no longer uses make_npc_say — NPC dialogue "
            "regression"
        )
        # Both NPC dialogue emit sites should be migrated. Count the
        # invocations to detect partial regression.
        n = text.count("make_npc_say(")
        assert n >= 2, (
            f"Expected >= 2 make_npc_say calls in npc_commands.py "
            f"(primary + tutorial fast-path), got {n}"
        )

    def test_npc_dialogue_dropped_old_says_format(self):
        """Old pattern: broadcast_to_room with f-string like
        `f'  {ansi.npc_name(npc_data.name)} says, "{response}"'`
        That should be gone from the AI-response emit sites."""
        text = self._read("parser/npc_commands.py")
        # If we see the literal f-string pattern combining
        # ansi.npc_name(npc_data.name) + 'says,' + response, regression.
        pattern = re.compile(
            r'ansi\.npc_name\(npc_data\.name\)[^)]*says,[^)]*response',
            re.DOTALL,
        )
        assert not pattern.search(text), (
            "Old NPC dialogue f-string still routes through broadcast_to_room"
        )


# ───────────────────────────────────────────────────────────────────────
# Foundation file shape
# ───────────────────────────────────────────────────────────────────────


class TestFoundationFileShape:

    def test_pose_events_module_exists(self):
        assert (ROOT / "engine" / "pose_events.py").exists()

    def test_pose_events_exports_key_symbols(self):
        """All public symbols documented in the module docstring should
        be importable. Guards against accidental rename / removal."""
        from engine import pose_events as pe
        for sym in (
            "make_pose_event", "make_dedup_key",
            "make_ambient_event", "make_system_event",
            "make_npc_say", "make_npc_pose",
            "EVENT_SAY", "EVENT_POSE", "EVENT_WHISPER",
            "EVENT_SYS_EVENT", "EVENT_DESC_INLINE", "EVENT_COMM_IN",
        ):
            assert hasattr(pe, sym), f"engine.pose_events missing {sym}"
