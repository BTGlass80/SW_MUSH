# -*- coding: utf-8 -*-
"""tests/test_staged_cult_reward_payout_2026_07_03.py — launch-blocker fix:
the staged-cult scenario WIN paid ZERO reward, and the relic grant (once
reachable) destroyed inventory.

BUG #1: `on_scenario_progress` (engine/communal_objective_runtime.py) advanced
a staged cult's stage cursor on a resolved anomaly but never wrote
`contribs[cid]["points"]`. Only the legacy `record_strike` wrote points, and
`rally strike` is always redirected away once a site is armed — so a REAL
3-stage clear reached `_distribute_rewards` with only the `_stage` bookkeeping
key, `total = sum(points) <= 0`, and every reward (rep, title, the 1000cr
capstone, the relic) silently paid nothing.

The EXISTING staged-scenario tests (test_events_playable_scenarios_2026_06_24,
test_drowned_choir_staged_scenario_2026_07_02, etc.) all hand-inject
`contribs["<cid>"] = {"points": 50, ...}` before calling `on_scenario_progress`
— exactly why they never caught this. This file drives the REAL resolver
signal instead: `WildernessAnomaly.resolved_by`, stamped by the anomaly
substrate at every real resolution path (skill: wilderness_anomalies.py:3847;
combat kill hooks: :4619/:4802).

BUG #2: `_grant_capstone_item` hand-rolled its inventory parse
(`if not isinstance(inv, dict): inv = {}`), silently discarding a bare-LIST
inventory (the DB column's schema default `'[]'` — the shape a fresh
character carries) and replacing it with `{"items": [relic]}`, destroying
every other item. Fixed via the canonical `engine.items.coerce_inventory`.

Run: python -m pytest tests/test_staged_cult_reward_payout_2026_07_03.py -q
(asyncio.run, Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import engine.communal_objective as CO
import engine.communal_objective_runtime as COR
import engine.staged_event as SE
import engine.wilderness_anomalies as WA
from db.database import MIGRATIONS
from engine.items import coerce_inventory

CULT = "hollow_sun"
REGION_SLUG = "tatooine_dune_sea"
_STAGES = SE.stages_for(CULT)
TEMPLATES = [s["anomaly_template"] for s in _STAGES]
SPECS = [(s["anomaly_template"], int(s.get("anomaly_tier", 1))) for s in _STAGES]


def _run(coro):
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════════════
# Runtime scaffold — mirrors tests/test_drowned_choir_staged_scenario_2026_07_02
# ════════════════════════════════════════════════════════════════════════════

class _SceneDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for sql in MIGRATIONS[43]:
            self.conn.execute(sql)
        self.conn.commit()
        self.rooms: dict[int, dict] = {}
        self.chars: dict[int, dict] = {}
        self.credit_tags: dict[int, list] = {}

    async def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    async def fetchall(self, sql, params=()):
        if "FROM rooms" in sql and "wilderness_region_id" in sql:
            region = params[0] if params else None
            return [
                {"id": r["id"]} for r in self.rooms.values()
                if r.get("wilderness_region_id") == region
            ]
        return self.conn.execute(sql, params).fetchall()

    async def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    async def commit(self):
        self.conn.commit()

    async def get_room(self, room_id):
        return self.rooms.get(int(room_id))

    async def get_character(self, cid):
        return self.chars.get(int(cid))

    async def save_character(self, cid, **fields):
        c = self.chars.setdefault(int(cid), {"id": int(cid)})
        c.update(fields)

    async def adjust_credits(self, cid, delta, tag):
        c = self.chars.setdefault(int(cid), {"id": int(cid), "credits": 0})
        c["credits"] = int(c.get("credits", 0)) + int(delta)
        self.credit_tags.setdefault(int(cid), []).append(tag)
        return c["credits"]


def _seed_site(db, region):
    db.rooms[900] = {"id": 900, "name": "Scenario Site",
                     "zone_id": 12, "wilderness_region_id": region}


def _force_post_cult(db, cult_key, now_ms):
    cult = CO.CULT_BY_KEY[cult_key]
    deadline = now_ms + CO.DEADLINE_HOURS * 3600 * 1000
    db.conn.execute(
        "INSERT INTO communal_objective "
        "(cult_key, zone_key, zone_label, menace, state, contributions_json, "
        " rotation, started_at, deadline_at, advanced_at, resolved_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cult.key, cult.world_key, cult.world_key.title(), float(CO.MENACE_START),
         CO.STATE_ACTIVE, "{}", 0, float(now_ms), float(deadline),
         float(now_ms), 0.0),
    )
    db.conn.commit()


def _raw_contribs(db, active_id):
    row = db.conn.execute(
        "SELECT contributions_json FROM communal_objective WHERE id = ?",
        (active_id,),
    ).fetchone()
    return json.loads(row["contributions_json"])


# ════════════════════════════════════════════════════════════════════════════
# Pin #1: a REAL 3-stage clear credits points at every stage and pays the FULL
# reward chain (rep, capstone credits, relic) on the win — the exact path that
# was dead before the fix.
# ════════════════════════════════════════════════════════════════════════════

def test_real_stage_clears_credit_points_and_pay_full_reward(monkeypatch):
    rep_calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        rep_calls.append((int(char["id"]), faction, int(delta or 0)))
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    CHAR_ID = 501

    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
        db.chars[CHAR_ID] = {"id": CHAR_ID, "attributes": "{}", "credits": 0,
                             "inventory": "[]"}

        # arm stage 1
        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        active_id = (await COR.get_active(db))["id"]

        prior_points = 0
        for stage_idx, expect_key in enumerate(TEMPLATES):
            active = await COR.get_active(db)
            assert active is not None, f"objective gone at stage {stage_idx}"
            state = SE.get_stage_state(json.loads(active["contributions_json"]))
            assert state["idx"] == stage_idx
            anom = WA.find_anomaly_globally(state["anomaly_id"])
            assert anom is not None and anom.template_key == expect_key

            # THE REAL RESOLVER SIGNAL — exactly what the skill/combat resolve
            # paths stamp (wilderness_anomalies.py:3847/4619/4802). No
            # hand-injected contribs — that's what let bug #1 hide.
            anom.resolved = True
            anom.resolved_by = CHAR_ID

            result = await COR.on_scenario_progress(db, None, active)

            # regression pin (bug #1): points must have increased after EVERY
            # stage clear, read straight off the persisted row.
            contribs = _raw_contribs(db, active_id)
            pts = int(contribs[str(CHAR_ID)]["points"])
            assert pts > prior_points, (
                f"stage {stage_idx} clear did not credit {CHAR_ID}'s points "
                f"(on_scenario_progress never wrote contribs points)")
            prior_points = pts

            if stage_idx == len(TEMPLATES) - 1:
                assert result == CO.STATE_WON, "final stage clear did not win"

        # the objective resolved (no longer active)
        assert await COR.get_active(db) is None

        # rep paid to the sole contributor
        assert any(cid == CHAR_ID and fac == CO.REP_FACTION and delta > 0
                   for (cid, fac, delta) in rep_calls), "rep payout missing"

        # the capstone credits, paid via the metered adjust_credits faucet
        assert db.chars[CHAR_ID]["credits"] == CO.win_capstone_credits(), (
            "communal_win_capstone credits not paid — bug #1 zero-payout")
        assert db.credit_tags.get(CHAR_ID) == ["communal_win_capstone"]

        # the relic granted to the (sole) top contributor
        inv = coerce_inventory(db.chars[CHAR_ID]["inventory"])
        assert any(it.get("is_capstone_loot") for it in inv["items"]), \
            "capstone relic not granted"
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# Pin #2: the relic grant must not destroy a bare-list inventory
# ════════════════════════════════════════════════════════════════════════════

def test_capstone_relic_preserves_bare_list_inventory():
    async def go():
        db = _SceneDB()
        cid = 900
        db.chars[cid] = {"id": cid,
                         "inventory": json.dumps(
                             [{"key": "old_blaster", "name": "Old Blaster"}])}
        loot = {"key": "test_relic", "name": "Test Relic", "description": "x"}
        await COR._grant_capstone_item(db, cid, loot)
        inv = json.loads(db.chars[cid]["inventory"])
        assert isinstance(inv, dict) and isinstance(inv.get("items"), list)
        keys = [it.get("key") for it in inv["items"]]
        assert "old_blaster" in keys, f"pre-existing item lost: {inv}"
        assert "test_relic" in keys, f"relic not granted: {inv}"
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# Pin #3: multi-contributor share — the bigger contributor is the top
# contributor (gets the relic); both cross the title-share threshold.
# ════════════════════════════════════════════════════════════════════════════

def test_multi_contributor_share_top_gets_relic(monkeypatch):
    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    A, B = 701, 702

    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
        db.chars[A] = {"id": A, "attributes": "{}", "credits": 0, "inventory": "[]"}
        db.chars[B] = {"id": B, "attributes": "{}", "credits": 0, "inventory": "[]"}

        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)

        resolvers = [A, A, B]   # A clears stages 1+2, B clears stage 3
        for cid in resolvers:
            active = await COR.get_active(db)
            state = SE.get_stage_state(json.loads(active["contributions_json"]))
            anom = WA.find_anomaly_globally(state["anomaly_id"])
            anom.resolved = True
            anom.resolved_by = cid
            await COR.on_scenario_progress(db, None, active)

        assert await COR.get_active(db) is None  # won

        inv_a = coerce_inventory(db.chars[A]["inventory"])
        inv_b = coerce_inventory(db.chars[B]["inventory"])
        a_has_relic = any(it.get("is_capstone_loot") for it in inv_a["items"])
        b_has_relic = any(it.get("is_capstone_loot") for it in inv_b["items"])
        assert a_has_relic and not b_has_relic, (
            "the top contributor (A, 2 stage clears) must get the relic, not B")

        # both recorded, both cross TITLE_SHARE_THRESHOLD (2/3 and 1/3 both
        # clear the 0.10 floor) and so both earn the capstone credit
        assert db.chars[A]["credits"] == CO.win_capstone_credits()
        assert db.chars[B]["credits"] == CO.win_capstone_credits()
        WA._reset_state_for_tests()
    _run(go())


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
