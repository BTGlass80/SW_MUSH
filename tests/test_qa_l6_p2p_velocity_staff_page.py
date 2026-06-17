"""QA L6: P2P velocity alert pages online admin/builder staff.

The `evaluate_p2p_velocity_alert` ring-buffer path was already wired in the
trade-accept handler. This drop adds the real-time staff page (mirrors the
server-wide credit_velocity_alert_tick paging behavior) so admins are notified
immediately on a velocity breach, not only when they run `@economy alerts`.
"""
import asyncio
import pytest

from engine.economy_alerts import (
    evaluate_p2p_velocity_alert,
    record_alert,
    format_alert_line,
    clear_alerts,
    recent_alerts,
    P2P_VELOCITY_CAUTION_24H,
)
from server.tick_handlers_economy import page_economy_alert_staff


# ── helpers ──────────────────────────────────────────────────────────────────

class _FakeSession:
    def __init__(self, is_in_game=True, is_admin=False, is_builder=False):
        self.is_in_game = is_in_game
        self.character = {"is_admin": is_admin, "is_builder": is_builder}
        self.received = []

    async def send_line(self, msg):
        self.received.append(msg)


class _FakeSessionMgr:
    def __init__(self, sessions):
        self.all = sessions


# ── unit: evaluate_p2p_velocity_alert ────────────────────────────────────────

def test_p2p_alert_below_caution_returns_none():
    assert evaluate_p2p_velocity_alert("Alice", 1, "Bob", 100) is None


def test_p2p_alert_at_caution_returns_dict():
    a = evaluate_p2p_velocity_alert("Alice", 1, "Bob", P2P_VELOCITY_CAUTION_24H)
    assert a is not None
    assert a["severity"] == "caution"
    assert a["kind"] == "p2p_velocity"
    assert a["sender"] == "Alice"
    assert a["recipient"] == "Bob"
    assert a["rolling_24h"] == P2P_VELOCITY_CAUTION_24H


def test_p2p_alert_bad_input_returns_none():
    assert evaluate_p2p_velocity_alert("Alice", 1, "Bob", "oops") is None


def test_format_alert_line_p2p():
    a = evaluate_p2p_velocity_alert("Alice", 1, "Bob", P2P_VELOCITY_CAUTION_24H, amount=500)
    line = format_alert_line(a)
    assert "Alice" in line
    assert "Bob" in line
    assert "p2p-volume" in line


# ── unit: ring buffer ─────────────────────────────────────────────────────────

def test_record_and_recent_alerts():
    clear_alerts()
    a = evaluate_p2p_velocity_alert("Alice", 1, "Bob", P2P_VELOCITY_CAUTION_24H)
    record_alert(a)
    alerts = recent_alerts()
    assert any(al.get("kind") == "p2p_velocity" for al in alerts)
    clear_alerts()


# ── unit: page_economy_alert_staff ────────────────────────────────────────────

def test_page_none_session_mgr_is_noop():
    asyncio.run(page_economy_alert_staff(None, "test alert"))


def test_page_sends_to_admin_sessions():
    admin = _FakeSession(is_in_game=True, is_admin=True)
    builder = _FakeSession(is_in_game=True, is_builder=True)
    player = _FakeSession(is_in_game=True, is_admin=False, is_builder=False)
    spectator = _FakeSession(is_in_game=False)
    mgr = _FakeSessionMgr([admin, builder, player, spectator])

    asyncio.run(page_economy_alert_staff(mgr, "CAUTION p2p-volume: Alice sent 1500 cr"))

    assert len(admin.received) == 1
    assert "[ECONOMY ALERT]" in admin.received[0]
    assert len(builder.received) == 1
    assert len(player.received) == 0
    assert len(spectator.received) == 0


def test_page_tolerates_broken_session():
    class _BrokenSession:
        is_in_game = True
        character = {"is_admin": True, "is_builder": False}

        async def send_line(self, msg):
            raise RuntimeError("boom")

    good = _FakeSession(is_in_game=True, is_admin=True)
    mgr = _FakeSessionMgr([_BrokenSession(), good])
    asyncio.run(page_economy_alert_staff(mgr, "alert"))
    assert len(good.received) == 1


def test_page_economy_alert_staff_is_public():
    from server.tick_handlers_economy import page_economy_alert_staff as fn
    assert callable(fn)
