# -*- coding: utf-8 -*-
"""T3.18 G13 — Director zone-tagged news + web Zone-Intel feed.

The ground-UX overhaul (ground_ux_overhaul_design_v1.md Drop 10 "Director
Story Feed") surfaces the Director's headlines in a context-panel "Zone Intel"
section that highlights beats about the player's current zone.

Brian's 2026-06-16 ruling: TAG EXISTING NEWS ONLY — no new LLM generation, so
zero new API spend. This drop:
  · adds an optional ``zone`` field to every Director ``news_event`` push;
  · routes the pushes through one helper (DirectorAI._broadcast_news_event);
  · tags Faction-Turn news with the hottest zone (DirectorAI._dominant_alert_zone),
    era beats stay galaxy-wide (zone=None);
  · pushes the API-turn headline live too (it was logged but never pushed —
    the Zone-Intel panel was empty under the funded Director). It reuses the
    ALREADY-generated ``news_headline`` → no extra API call.

These tests pin the dominant-zone selection, the broadcast helper's payload +
telnet-skip, and the client contract.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from engine.director import (
    DirectorAI, ZoneState, AlertLevel, _ALERT_NEWS_RANK, _zone_display,
)

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Fake transport ───────────────────────────────────────────────────────

class _Sess:
    """Captures send_json calls; mimics the websocket/telnet split."""
    def __init__(self, in_game=True, websocket=True):
        self.is_in_game = in_game
        self.websocket = websocket
        self.sent = []

    async def send_json(self, msg_type, data):
        # Mirror Session.send_json: telnet ignores news_event entirely.
        if not self.websocket and msg_type == "news_event":
            return
        self.sent.append((msg_type, data))


class _SessionMgr:
    def __init__(self, sessions):
        self.all = sessions


# ── _dominant_alert_zone ─────────────────────────────────────────────────

class TestDominantAlertZone:
    def _director_with_zones(self, levels: dict) -> DirectorAI:
        d = DirectorAI()
        d._zones = {}
        for key, lvl in levels.items():
            zs = ZoneState(zone_key=key)
            zs.alert_level = lvl
            d._zones[key] = zs
        return d

    def test_all_calm_returns_none(self):
        d = self._director_with_zones({
            "spaceport": AlertLevel.STANDARD,
            "cantina": AlertLevel.LAX,
        })
        assert d._dominant_alert_zone() is None

    def test_picks_hottest_zone(self):
        d = self._director_with_zones({
            "spaceport": AlertLevel.STANDARD,
            "streets": AlertLevel.HIGH_ALERT,   # rank 2
            "cantina": AlertLevel.LOCKDOWN,     # rank 4 — hottest
        })
        assert d._dominant_alert_zone() == _zone_display("cantina")

    def test_unrest_beats_high_alert(self):
        d = self._director_with_zones({
            "streets": AlertLevel.HIGH_ALERT,   # rank 2
            "shops": AlertLevel.UNREST,         # rank 3
        })
        assert d._dominant_alert_zone() == _zone_display("shops")

    def test_empty_zones_returns_none(self):
        d = DirectorAI()
        d._zones = {}
        assert d._dominant_alert_zone() is None

    def test_rank_table_covers_every_alert_level(self):
        # Drift guard: a new AlertLevel must get an explicit news rank or the
        # dominant-zone picker silently treats it as calm.
        for lvl in AlertLevel:
            assert lvl.value in _ALERT_NEWS_RANK


# ── _broadcast_news_event ────────────────────────────────────────────────

class TestBroadcastNewsEvent:
    def test_payload_carries_zone(self):
        s = _Sess(in_game=True, websocket=True)
        mgr = _SessionMgr([s])
        d = DirectorAI()
        _run(d._broadcast_news_event(mgr, text="Hutts move on the docks.",
                                     tag="event", zone="Spaceport"))
        assert len(s.sent) == 1
        msg_type, data = s.sent[0]
        assert msg_type == "news_event"
        assert data["text"] == "Hutts move on the docks."
        assert data["tag"] == "event"
        assert data["zone"] == "Spaceport"

    def test_zone_defaults_to_none(self):
        s = _Sess()
        d = DirectorAI()
        _run(d._broadcast_news_event(_SessionMgr([s]), text="x", tag="era"))
        assert s.sent[0][1]["zone"] is None

    def test_offline_sessions_skipped(self):
        online = _Sess(in_game=True)
        offline = _Sess(in_game=False)
        d = DirectorAI()
        _run(d._broadcast_news_event(_SessionMgr([online, offline]),
                                     text="x", tag="event", zone="Z"))
        assert len(online.sent) == 1
        assert offline.sent == []

    def test_telnet_ignores_news_event(self):
        telnet = _Sess(in_game=True, websocket=False)
        d = DirectorAI()
        _run(d._broadcast_news_event(_SessionMgr([telnet]),
                                     text="x", tag="event", zone="Z"))
        assert telnet.sent == []  # send_json no-ops news_event on telnet

    def test_dead_socket_does_not_abort(self):
        class _Boom:
            is_in_game = True
            async def send_json(self, *a, **k):
                raise RuntimeError("socket closed")
        good = _Sess()
        d = DirectorAI()
        # Must not raise even though one session blows up.
        _run(d._broadcast_news_event(_SessionMgr([_Boom(), good]),
                                     text="x", tag="event"))
        assert len(good.sent) == 1


# ── Client contract ──────────────────────────────────────────────────────

class TestClientContract:
    @pytest.fixture(scope="class")
    def html(self) -> str:
        assert CLIENT_HTML.exists()
        return CLIENT_HTML.read_text(encoding="utf-8")

    def test_panel_present(self, html):
        assert 'id="zoneintel-panel"' in html
        assert 'id="zoneintel-body"' in html

    def test_push_and_render_functions(self, html):
        assert "function pushZoneIntel(" in html
        assert "function renderZoneIntel(" in html
        assert "function zoneMatchesCurrent(" in html

    def test_news_event_feeds_panel(self, html):
        assert "pushZoneIntel(msg)" in html

    def test_zone_match_reads_current_zone(self, html):
        assert "lastHud.zone_name" in html

    def test_zone_intel_css_present(self, html):
        assert ".zi-row" in html
        assert ".zi-local" in html
        assert ".zi-badge" in html

    def test_zone_intel_cleared_on_logout(self, html):
        # The feed must reset on logout / character switch so stale headlines
        # from the prior session don't leak in.
        assert "drop the Zone-Intel feed" in html  # logout-reset marker
        assert html.count("_zoneIntel = []") >= 2   # declaration + logout reset
