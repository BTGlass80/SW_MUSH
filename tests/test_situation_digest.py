# -*- coding: utf-8 -*-
"""tests/test_situation_digest.py — DirectorAI.compile_situation_digest (UX Drop 4).

The lean, player-facing situation snapshot that feeds the web Situation board.
It is a READ-ONLY mirror over state the Director already produced — extends the
digest path, adds no producer, writes nothing. This pins:

  · payload SHAPE: zone / influence / events / uprising / news keys.
  · the news filter: internal/admin event types (faction_turn, era_milestone,
    economic_nudge — INTERNAL_NEWS_EVENTS) are dropped; player-facing ones kept;
    capped at the last 5.
  · world events are ZONE-SCOPED: only events whose zones include the player's
    zone (or global, zone-less, events) are surfaced.
  · the uprising menace passes THROUGH unchanged, and null uprising → None.
  · influence ladder reads the in-memory _zones for the player's zone_key.

Runs over a real in-memory sqlite via the project migration DDL (director_log +
zone_influence in MIGRATIONS[5], communal_objective in MIGRATIONS[43]) — same
_MiniDB idiom as tests/test_drop4b_communal_cult.py.

Resets engine.world_events._manager to None in teardown — the singleton leaks
across tests otherwise (known isolation gotcha).

Run: python -m pytest tests/test_situation_digest.py
(asyncio.run, never get_event_loop — Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import engine.director as DIR
import engine.world_events as WE
from db.database import MIGRATIONS


def _run(coro):
    return asyncio.run(coro)


class _MiniDB:
    """Raw-aiosqlite-shaped wrapper over an in-memory sqlite.

    Carries the REAL director_log / zone_influence / communal_objective DDL so
    get_recent_log and communal_objective_runtime.get_active run their real SQL.
    """
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for sql in MIGRATIONS[5]:       # zone_influence + director_log
            self.conn.execute(sql)
        for sql in MIGRATIONS[43]:      # communal_objective
            self.conn.execute(sql)
        self.conn.commit()

    async def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    async def fetchall(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    async def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    async def commit(self):
        self.conn.commit()


def _reset_world_events():
    """Drop the WorldEventManager singleton (isolation gotcha)."""
    WE._manager = None


def _fresh_director(zone_key, scores):
    """A DirectorAI with one seeded zone in _zones (no full DB load needed)."""
    d = DIR.DirectorAI()
    zs = DIR.ZoneState(zone_key=zone_key)
    for f, v in scores.items():
        zs.set_faction(f, v)
    d._zones[zone_key] = zs
    return d


def _seed_news(db):
    """Mixed director_log rows: internal (dropped) + player-facing (kept)."""
    rows = [
        ("faction_turn",   "Internal: a faction turn ran"),       # internal
        ("news",           "Black Sun couriers active on Nar Shaddaa"),
        ("economic_nudge", "Internal: a merchant caravan was seeded"),  # internal
        ("ambient",        "Sandstorm warning issued for the Dune Sea"),
        ("era_milestone",  "Internal: an era milestone fired"),    # internal
        ("comm_in",        "A coded transmission was intercepted"),
        ("news",           "Republic cruisers converge on Ryloth"),
    ]
    for et, summary in rows:
        db.conn.execute(
            "INSERT INTO director_log (event_type, summary) VALUES (?, ?)",
            (et, summary),
        )
    db.conn.commit()


def _seed_uprising(db, *, cult_key="hollow_sun", zone_label="Mos Eisley",
                   menace=63.0, state="active"):
    db.conn.execute(
        "INSERT INTO communal_objective "
        "(cult_key, zone_key, zone_label, menace, state) VALUES (?, ?, ?, ?, ?)",
        (cult_key, "tatooine", zone_label, menace, state),
    )
    db.conn.commit()


# ════════════════════════════════════════════════════════════════════════════
# Payload shape + news filter + uprising passthrough
# ════════════════════════════════════════════════════════════════════════════

def test_payload_shape_and_news_filter():
    async def go():
        db = _MiniDB()
        _seed_news(db)
        _seed_uprising(db)
        # Seed a zone-scoped + a global world event.
        WE.get_world_event_manager().activate_event(
            "sandstorm", zones=["mos_eisley"], duration_minutes=30,
            headline="A wall of sand rolls in over Mos Eisley.",
        )

        d = _fresh_director("mos_eisley", {
            "republic": 20, "hutt_cartel": 55, "cis": 10,
        })
        digest = await d.compile_situation_digest(db, "mos_eisley", None)

        # Shape: exactly the lean keys, nothing more.
        assert set(digest.keys()) == {"zone", "influence", "events", "uprising", "news"}
        assert digest["zone"] == "mos_eisley"

        # News filter: internal types dropped, player-facing kept, capped at 5.
        types = [r["event_type"] for r in digest["news"]]
        assert "faction_turn" not in types
        assert "economic_nudge" not in types
        assert "era_milestone" not in types
        assert "news" in types and "ambient" in types
        assert len(digest["news"]) <= 5

        # Uprising menace passes through unchanged.
        up = digest["uprising"]
        assert up is not None
        assert up["cult_key"] == "hollow_sun"
        assert up["zone_label"] == "Mos Eisley"
        assert up["menace"] == 63.0
        assert up["state"] == "active"

        # Influence ladder reflects the seeded zone scores.
        infl = {row["faction"]: row["score"] for row in digest["influence"]}
        assert infl["hutt_cartel"] == 55
        assert infl["republic"] == 20
        return digest
    try:
        _run(go())
    finally:
        _reset_world_events()


def test_events_are_zone_scoped():
    async def go():
        db = _MiniDB()
        mgr = WE.get_world_event_manager()
        # One event in the player's zone, one in a DIFFERENT zone, one global.
        mgr.activate_event("sandstorm", zones=["mos_eisley"],
                           duration_minutes=30, headline="local storm")
        # Inject the off-zone + global events directly to bypass the manager's
        # activate cooldown (we only need get_status() to return them).
        from engine.world_events import ActiveEvent, EventType
        import time as _t
        now = _t.time()
        off = ActiveEvent(
            event_type=EventType.BOUNTY_SURGE,
            zones_affected=["coruscant_works"],
            started_at=now, expires_at=now + 1800,
            headline="off-zone surge",
        )
        glob = ActiveEvent(
            event_type=EventType.TRADE_BOOM,
            zones_affected=[],   # global → always shown
            started_at=now, expires_at=now + 1800,
            headline="galaxy-wide boom",
        )
        mgr._active.append(off)
        mgr._active.append(glob)

        d = _fresh_director("mos_eisley", {"republic": 30})
        digest = await d.compile_situation_digest(db, "mos_eisley", None)

        zones_seen = [tuple(e.get("zones") or []) for e in digest["events"]]
        # The local + the global event surface; the off-zone one does NOT.
        assert ("mos_eisley",) in zones_seen
        assert () in zones_seen
        assert ("coruscant_works",) not in zones_seen
        return digest
    try:
        _run(go())
    finally:
        _reset_world_events()


def test_null_uprising_degrades_to_none():
    async def go():
        db = _MiniDB()
        _seed_news(db)
        # No communal_objective rows seeded → get_active returns None.
        d = _fresh_director("mos_eisley", {"republic": 30})
        digest = await d.compile_situation_digest(db, "mos_eisley", None)
        assert digest["uprising"] is None
        # Still a well-formed payload.
        assert digest["zone"] == "mos_eisley"
        assert isinstance(digest["influence"], list)
        assert isinstance(digest["events"], list)
        assert isinstance(digest["news"], list)
    try:
        _run(go())
    finally:
        _reset_world_events()


def test_unknown_zone_yields_empty_influence_no_throw():
    async def go():
        db = _MiniDB()
        d = _fresh_director("mos_eisley", {"republic": 30})
        # Ask for a zone the Director doesn't track.
        digest = await d.compile_situation_digest(db, "nowhere_zone", None)
        assert digest["zone"] == "nowhere_zone"
        assert digest["influence"] == []   # empty, not a crash
    try:
        _run(go())
    finally:
        _reset_world_events()


def test_internal_news_events_constant_is_the_verified_set():
    # Lock the whitelist of internal/admin types to the three verified writers.
    assert DIR.INTERNAL_NEWS_EVENTS == frozenset(
        {"faction_turn", "era_milestone", "economic_nudge"}
    )
