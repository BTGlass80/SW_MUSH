"""tests/test_drop4b_communal_cult.py — the dark-side cult communal objective.

Two layers, mirroring the project's sandbox discipline:

  * PURE deciders (no DB): roster CW/Q1-cleanness, the menace state machine,
    cross-playstyle strike pool, strike resolution + margin bands, win/lose
    resolution, and the prestige-domain reward shares.
  * RUNTIME over a real sqlite table (asyncio.run + a _MiniDB wrapper): post /
    strike / escalate / resolve / reward, exercising the ACTUAL migration DDL and
    the ACTUAL SQL in engine/communal_objective_runtime. adjust_rep is stubbed so
    the reward test isolates share computation from the org tables.

Run: python3 -m pytest tests/test_drop4b_communal_cult.py
(asyncio.run, never get_event_loop — Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3

import engine.communal_objective as CO
import engine.communal_objective_runtime as COR
from db.database import MIGRATIONS


# ════════════════════════════════════════════════════════════════════════════
# 1. PURE deciders
# ════════════════════════════════════════════════════════════════════════════

# Era (B3) + canon (Q1) banned substrings in any player-facing cult string.
_BANNED = [
    "imperial", "empire", "rebel", "rebellion", "stormtrooper", "tie ",
    "x-wing", "star destroyer", "moff", "palpatine", "vader", "sith",
    "dooku", "ventress", "grievous", "sidious", "maul",
]


def _all_cult_strings() -> list[str]:
    out = []
    for c in CO.CULT_ROSTER:
        out += [c.name, c.blurb, c.rally_hook, c.world_key]
        label = COR._zone_label(c)
        out += [
            CO.posted_broadcast(c, label),
            CO.escalation_broadcast(c, 50),
            CO.won_broadcast(c, label),
            CO.lost_broadcast(c, label),
            CO.fallback_flavor(c, 50),
        ]
    return out


def test_roster_is_era_and_canon_clean():
    """No Imperial/Rebel/TIE (B3) and no canon figures/Sith (Q1) in any string."""
    for s in _all_cult_strings():
        low = s.lower()
        for bad in _BANNED:
            assert bad not in low, f"banned term {bad!r} in cult string: {s!r}"


def test_roster_nonempty_and_rotation_deterministic():
    assert len(CO.CULT_ROSTER) >= 4
    n = len(CO.CULT_ROSTER)
    assert CO.cult_for_index(0).key == CO.CULT_ROSTER[0].key
    assert CO.cult_for_index(n).key == CO.CULT_ROSTER[0].key  # wraps
    assert CO.cult_for_index(n + 1).key == CO.CULT_ROSTER[1].key
    # keys unique
    keys = [c.key for c in CO.CULT_ROSTER]
    assert len(keys) == len(set(keys))


def test_advance_menace_escalates_and_clamps():
    assert CO.advance_menace(0, 0) == 0.0
    assert CO.advance_menace(10, 10) == 10 + CO.MENACE_PER_MINUTE * 10
    # clamps at MENACE_MAX
    assert CO.advance_menace(CO.MENACE_MAX, 9999) == float(CO.MENACE_MAX)
    # never negative input handling
    assert CO.advance_menace(5, -100) == 5.0


def test_menace_tiers():
    assert CO.menace_tier(0) == "routed"
    assert CO.menace_tier(10) == "stirring"
    assert CO.menace_tier(50) == "rising"
    assert CO.menace_tier(90) == "ascendant"


def test_resolve_state():
    # won the instant menace hits 0
    assert CO.resolve_state(0, now_ms=1000, deadline_ms=9999) == CO.STATE_WON
    # lost if maxed
    assert CO.resolve_state(CO.MENACE_MAX, now_ms=1000, deadline_ms=9999) == CO.STATE_LOST
    # lost if deadline passed while active
    assert CO.resolve_state(50, now_ms=10000, deadline_ms=9999) == CO.STATE_LOST
    # active otherwise
    assert CO.resolve_state(50, now_ms=1000, deadline_ms=9999) == CO.STATE_ACTIVE


def test_best_strike_pool_cross_playstyle():
    # untrained civilian floors at 2D = 6 pips
    assert CO.best_strike_pool_pips({}, {}) == 6
    # a soldier's blaster skill wins
    assert CO.best_strike_pool_pips({"blaster": 15}, {"dexterity": 9}) == 15
    # a slicer with investigation also qualifies (no combat skill needed)
    assert CO.best_strike_pool_pips({"investigation": 12}, {"perception": 6}) == 12
    # a Jedi via control
    assert CO.best_strike_pool_pips({}, {"control": 18}) == 18
    # case-insensitive skill match
    assert CO.best_strike_pool_pips({"Persuasion": 13}, {}) == 13
    # attribute fallback when skill untrained
    assert CO.best_strike_pool_pips({}, {"strength": 11}) == 11


def test_strike_difficulty_scales_with_menace():
    assert CO.strike_difficulty(10) == 10   # stirring
    assert CO.strike_difficulty(50) == 13   # rising
    assert CO.strike_difficulty(90) == 16   # ascendant


def test_strike_menace_reduction_margin_bands():
    assert CO.strike_menace_reduction(-1) == 0.0
    assert CO.strike_menace_reduction(0) == 5.0
    assert CO.strike_menace_reduction(5) == 8.0
    assert CO.strike_menace_reduction(10) == 11.0
    assert CO.strike_menace_reduction(15) == 14.0


def test_apply_strike_success_and_miss():
    # success: total >= difficulty
    out = CO.apply_strike(menace=50, total=18, difficulty=13)
    assert out.success and out.margin == 5
    assert out.menace_after == 50 - 8.0
    # miss: removes nothing
    out2 = CO.apply_strike(menace=50, total=8, difficulty=13)
    assert not out2.success and out2.menace_after == 50.0
    # clamps at 0
    out3 = CO.apply_strike(menace=3, total=99, difficulty=10)
    assert out3.menace_after == 0.0


def test_reward_rep_shares_win_only():
    # loss pays nothing
    assert CO.reward_rep_for_share(100, 100, won=False) == 0
    # zero points pays nothing
    assert CO.reward_rep_for_share(0, 100, won=True) == 0
    # sole contributor earns the max
    assert CO.reward_rep_for_share(100, 100, won=True) == CO.REP_MAX
    # a small share earns at least the floor, less than the max
    small = CO.reward_rep_for_share(5, 100, won=True)
    assert CO.REP_FLOOR <= small < CO.REP_MAX


def test_earns_title_threshold():
    assert CO.earns_title(20, 100, won=True) is True    # 20% >= 10%
    assert CO.earns_title(5, 100, won=True) is False     # 5% < 10%
    assert CO.earns_title(50, 100, won=False) is False   # loss never
    assert CO.earns_title(0, 100, won=True) is False


def test_menace_bar_renders():
    bar = CO.menace_bar(50, width=10)
    assert "/100" in bar and "rising" in bar


# ════════════════════════════════════════════════════════════════════════════
# 2. RUNTIME over a real sqlite communal_objective table
# ════════════════════════════════════════════════════════════════════════════

class _MiniDB:
    """Raw-aiosqlite-shaped wrapper over an in-memory sqlite for the runtime.

    communal_objective uses the REAL migration DDL + the REAL runtime SQL.
    Characters live in an in-memory dict (just enough for the reward path).
    """
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for sql in MIGRATIONS[43]:
            self.conn.execute(sql)
        self.conn.commit()
        self.chars: dict[int, dict] = {}

    async def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    async def fetchall(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    async def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    async def commit(self):
        self.conn.commit()

    async def get_character(self, cid):
        return self.chars.get(int(cid))

    async def save_character(self, cid, **fields):
        c = self.chars.setdefault(int(cid), {"id": int(cid)})
        c.update(fields)


def _run(coro):
    return asyncio.run(coro)


def test_maybe_post_posts_once_and_sets_initial_state():
    async def go():
        db = _MiniDB()
        row = await COR.maybe_post(db, None, now_ms=1_000_000)
        assert row is not None
        assert row["state"] == CO.STATE_ACTIVE
        assert float(row["menace"]) == float(CO.MENACE_START)
        assert float(row["deadline_at"]) > float(row["started_at"])
        # second call does not double-post while one is active
        again = await COR.maybe_post(db, None, now_ms=1_000_001)
        assert again is None
        n = (await db.fetchone("SELECT COUNT(*) AS c FROM communal_objective"))["c"]
        assert n == 1
    _run(go())


def test_repost_cooldown_between_uprisings():
    async def go():
        db = _MiniDB()
        now = 1_000_000
        await COR.maybe_post(db, None, now_ms=now)
        # force-resolve the active one as lost, resolved just now
        await db.execute(
            "UPDATE communal_objective SET state=?, resolved_at=?",
            (CO.STATE_LOST, float(now)),
        )
        await db.commit()
        # within the cooldown: no new post
        assert await COR.maybe_post(db, None, now_ms=now + 1000) is None
        # after the cooldown: a new uprising posts, rotation advances
        later = now + COR.REPOST_COOLDOWN_MS + 1
        row = await COR.maybe_post(db, None, now_ms=later)
        assert row is not None and int(row["rotation"]) == 1
    _run(go())


def test_strike_pushes_menace_and_enforces_cooldown():
    async def go():
        db = _MiniDB()
        await COR.maybe_post(db, None, now_ms=1_000_000)
        # a capable striker (big pool) almost always succeeds
        char = {"id": 7, "skills": json.dumps({"blaster": 18}),
                "attributes": json.dumps({"dexterity": 12})}
        before = float((await COR.get_active(db))["menace"])
        res = await COR.record_strike(db, None, char, now_ms=1_000_000)
        active = await COR.get_active(db)
        after = float(active["menace"])
        if res.ok:
            from engine import staged_event as _SE
            if _SE.is_staged(active["cult_key"]):
                # EVENT staged-scenario rework: a staged cult's strike advances
                # the STAGE; the menace is the timer, untouched by strikes.
                contribs = json.loads(active["contributions_json"])
                assert "_stage" in contribs
            else:
                assert after < before
            # points recorded for the contributor (both paths)
            contribs = json.loads(active["contributions_json"])
            assert contribs["7"]["points"] > 0
        # immediate second strike is on cooldown regardless of hit/miss
        res2 = await COR.record_strike(db, None, char, now_ms=1_000_001)
        assert (not res2.ok) and res2.reason == "cooldown"
        # after the cooldown window, a strike is allowed again
        res3 = await COR.record_strike(
            db, None, char, now_ms=1_000_000 + CO.STRIKE_COOLDOWN_S * 1000 + 1)
        assert res3.reason in ("", "miss")  # allowed (hit or miss), not cooldown
    _run(go())


def test_strike_with_no_active_uprising():
    async def go():
        db = _MiniDB()
        char = {"id": 1, "skills": "{}", "attributes": "{}"}
        res = await COR.record_strike(db, None, char, now_ms=1)
        assert (not res.ok) and res.reason == "no_active"
    _run(go())


def test_advance_resolves_loss_at_deadline():
    async def go():
        db = _MiniDB()
        await COR.maybe_post(db, None, now_ms=1_000_000)
        # jump past the deadline; the cult is still active -> lost
        active = await COR.get_active(db)
        past = int(float(active["deadline_at"])) + 1
        state = await COR.advance_and_resolve(db, None, now_ms=past)
        assert state == CO.STATE_LOST
        assert await COR.get_active(db) is None  # no longer active
    _run(go())


def test_advance_escalates_while_active():
    async def go():
        db = _MiniDB()
        await COR.maybe_post(db, None, now_ms=1_000_000)
        active = await COR.get_active(db)
        before = float(active["menace"])
        # 30 minutes later, still well before deadline -> menace rose, still active
        later = 1_000_000 + 30 * 60 * 1000
        state = await COR.advance_and_resolve(db, None, now_ms=later)
        assert state == CO.STATE_ACTIVE
        after = float((await COR.get_active(db))["menace"])
        assert after > before
    _run(go())


def test_win_pays_rep_by_share_and_title_flag(monkeypatch):
    """A community win pays Republic rep scaled by share + a III.2 flag; loss pays nothing."""
    calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        calls.append((int(char["id"]), faction, int(delta)))
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    async def go():
        db = _MiniDB()
        await COR.maybe_post(db, None, now_ms=1_000_000)
        active = await COR.get_active(db)
        # seed two contributors directly into the row: a whale and a minnow
        contribs = {"100": {"points": 90, "last_strike_at": 1.0},
                    "200": {"points": 10, "last_strike_at": 1.0}}
        await db.execute(
            "UPDATE communal_objective SET menace=0, contributions_json=? WHERE id=?",
            (json.dumps(contribs), int(active["id"])),
        )
        await db.commit()
        # register the two characters so reward writes have somewhere to land
        db.chars[100] = {"id": 100, "attributes": "{}"}
        db.chars[200] = {"id": 200, "attributes": "{}"}
        # resolve as a win (menace already 0)
        state = await COR.advance_and_resolve(db, None, now_ms=1_000_500)
        assert state == CO.STATE_WON

        # rep paid to republic; whale got more than minnow; both >= floor
        by_id = {cid: delta for (cid, fac, delta) in calls if fac == CO.REP_FACTION}
        assert by_id.get(100, 0) > by_id.get(200, 0)
        assert by_id.get(200, 0) >= CO.REP_FLOOR
        assert by_id.get(100, 0) >= CO.REP_MAX - 2  # 90% share ~ near max

        # whale (90% >= 10%) earned the commemorative flag; both did here (10% == threshold)
        a100 = json.loads(db.chars[100]["attributes"])
        assert "communal_objective_wins" in a100

        # finalize is idempotent: re-running does not pay again
        calls.clear()
        await COR.advance_and_resolve(db, None, now_ms=1_000_600)
        assert calls == []
    _run(go())


def test_loss_pays_nothing(monkeypatch):
    calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        calls.append((int(char["id"]), faction, int(delta)))
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    async def go():
        db = _MiniDB()
        await COR.maybe_post(db, None, now_ms=1_000_000)
        active = await COR.get_active(db)
        contribs = {"100": {"points": 50, "last_strike_at": 1.0}}
        await db.execute(
            "UPDATE communal_objective SET contributions_json=? WHERE id=?",
            (json.dumps(contribs), int(active["id"])),
        )
        await db.commit()
        db.chars[100] = {"id": 100, "attributes": "{}"}
        # force a loss by jumping past the deadline
        past = int(float(active["deadline_at"])) + 1
        state = await COR.advance_and_resolve(db, None, now_ms=past)
        assert state == CO.STATE_LOST
        assert calls == []  # opportunities, never penalties — and no reward on a loss
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# 3. Admin / Director force-controls (operability for verification)
# ════════════════════════════════════════════════════════════════════════════

def test_force_post_bypasses_gate_and_picks_cult():
    async def go():
        db = _MiniDB()
        # posts even with no cooldown elapsed
        r1 = await COR.force_post(db, None, now_ms=1_000_000)
        assert r1 is not None and r1["state"] == CO.STATE_ACTIVE
        # posting again while one is active clears the old and leaves exactly one active
        r2 = await COR.force_post(db, None, now_ms=1_000_100)
        assert r2 is not None
        n_active = (await db.fetchone(
            "SELECT COUNT(*) AS c FROM communal_objective WHERE state='active'"))["c"]
        assert n_active == 1
        # an explicit cult_key is honored
        r3 = await COR.force_post(db, None, cult_key="iron_veil", now_ms=1_000_200)
        assert r3["cult_key"] == "iron_veil"
    _run(go())


def test_force_resolve_win_pays(monkeypatch):
    calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        calls.append((int(char["id"]), faction, int(delta)))
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    async def go():
        db = _MiniDB()
        await COR.force_post(db, None, now_ms=1_000_000)
        active = await COR.get_active(db)
        contribs = {"100": {"points": 40, "last_strike_at": 1.0}}
        await db.execute(
            "UPDATE communal_objective SET contributions_json=? WHERE id=?",
            (json.dumps(contribs), int(active["id"])),
        )
        await db.commit()
        db.chars[100] = {"id": 100, "attributes": "{}"}
        # admin forces the win even though menace is still high
        state = await COR.force_resolve(db, None, won=True, now_ms=1_000_500)
        assert state == CO.STATE_WON
        assert any(fac == CO.REP_FACTION and delta > 0 for (_c, fac, delta) in calls)
        assert await COR.get_active(db) is None
    _run(go())


def test_force_clear_silently_cancels():
    async def go():
        db = _MiniDB()
        await COR.force_post(db, None, now_ms=1_000_000)
        ok = await COR.force_clear(db, None, now_ms=1_000_100)
        assert ok is True
        assert await COR.get_active(db) is None
        # nothing left to clear
        assert await COR.force_clear(db, None, now_ms=1_000_200) is False
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# 4. Rally-board UX: deadline countdown + the viewer's own contribution
# ════════════════════════════════════════════════════════════════════════════

def test_time_left_line_formats():
    now = 1_000_000_000
    assert "1h 30m" in CO.time_left_line(now + (90 * 60 * 1000), now)
    assert "h " not in CO.time_left_line(now + (5 * 60 * 1000), now)   # mins only
    assert "passed" in CO.time_left_line(now - 1, now).lower()


def test_viewer_contribution_line():
    now = 2_000_000
    # not participated -> empty
    assert CO.viewer_contribution_line({}, 7, now) == ""
    # cooldown elapsed -> shows points + ready
    contribs = {"7": {"points": 14, "last_strike_at": now - (CO.STRIKE_COOLDOWN_S * 1000 + 1)}}
    line = CO.viewer_contribution_line(contribs, 7, now)
    assert "14" in line and "ready" in line.lower()
    # on cooldown -> shows a wait
    contribs2 = {"7": {"points": 8, "last_strike_at": now - 1000}}
    line2 = CO.viewer_contribution_line(contribs2, 7, now)
    assert "ready" not in line2.lower() and "m" in line2


def test_render_board_includes_time_left():
    async def go():
        db = _MiniDB()
        await COR.maybe_post(db, None, now_ms=1_000_000)
        active = await COR.get_active(db)
        lines = COR.render_board(active, now_ms=1_000_000)
        assert any("time left" in ln.lower() for ln in lines)
        # and the deadline-passed case renders too
        passed = COR.render_board(active, now_ms=int(float(active["deadline_at"])) + 1)
        assert any("passed" in ln.lower() for ln in passed)
    _run(go())
