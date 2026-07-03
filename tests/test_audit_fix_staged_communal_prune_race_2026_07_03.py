# -*- coding: utf-8 -*-
"""tests/test_audit_fix_staged_communal_prune_race_2026_07_03.py — LANE B of
the signal-producer audit (findings #8, #9, #10):
engine/wilderness_anomalies.py + engine/communal_objective_runtime.py +
engine/communal_objective.py.

F8/F9 (MAJOR x2) — prune-race silently discarded staged-cult stage clears.
A stage anomaly resolved by the real substrate (resolved=True, resolved_by
stamped) was LOST if any region prune (the hourly T1 spawn tick, or a
player typing `anomalies` in that region — WA._prune_expired_region /
_prune_expired_region_with_cleanup) removed it from the in-memory table
before the communal orchestrator's poll (COR.on_scenario_progress)
consumed it: no reward, silent re-arm of the SAME stage; on the FINAL
stage the whole multi-stage win was discarded (no rep/title/1000cr
capstone/relic) and the boss re-armed.

Fixed via two extends:
  (a) `scenario_hold` prune exemption (WA.spawn_scenario_anomaly /
      WA._prune_expired_region) + explicit consumption
      (WA.delete_anomaly_by_id, called from on_scenario_progress) — a
      resolved, scenario_hold anomaly now survives prune until the
      orchestrator explicitly deletes it.
  (b) an inline push-notify (WA._dispatch_site_cleared /
      WA._notify_communal_stage_clear, fired from every resolution path
      — T1/T2/T3 combat payout AND the skill path) that invokes
      COR.on_scenario_progress synchronously at resolve time, so the
      advance lands even if a poll never comes.
Consumption is made idempotent on the anomaly id (WA.delete_anomaly_by_id
+ a fresh-state recheck in on_scenario_progress) so (a) and (b) — or two
racing polls — can never double-credit the same stage clear.

F10 (MINOR, Brian-ruled) — cult rewards went only to the resolved_by
finisher. Fixed by stamping `anomaly.resolved_participants` (the SAME
list WA._dispatch_site_cleared already fans the site_cleared chain hook
over) at every resolution path, and crediting every OTHER participant a
reduced share of the stage-clear points
(communal.staged_participant_share, default 0.5) in on_scenario_progress
— extending Brian's Fork-4B participant fan-out ruling to the communal
reward, not just the chain hook.

All tests drive the REAL production seams — WA.spawn_scenario_anomaly /
COR.arm_stage_site (real spawn), WA._prune_expired_region /
_prune_expired_region_with_cleanup (the REAL prune paths the `anomalies`
command / hourly tick use), WA._payout_combat_anomaly /
WA._resolve_anomaly_skill (the REAL resolution paths that stamp
resolved/resolved_by/resolved_participants and fire the push-notify), and
COR.on_scenario_progress / COR.arm_stage_site (the real orchestrator).
Only the resolved/resolved_by/resolved_participants fields the real
resolve paths themselves stamp are ever hand-set directly on a live
WildernessAnomaly (mirrors the precedent set by
tests/test_staged_cult_reward_payout_2026_07_03.py) — the
contributions_json POINTS LEDGER itself is never hand-injected; every
point value asserted here is computed by the real
on_scenario_progress / _distribute_rewards code under test.

Run: python -m pytest tests/test_audit_fix_staged_communal_prune_race_2026_07_03.py -q
(asyncio.run, Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import json
import random
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


def _run(coro):
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════════════
# Scaffold — mirrors tests/test_staged_cult_reward_payout_2026_07_03.py,
# extended with get_characters_in_room for the F10 multi-participant payout.
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
        self.room_occupants: dict[int, list] = {}

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
        return None

    async def adjust_credits(self, cid, delta, tag):
        c = self.chars.setdefault(int(cid), {"id": int(cid), "credits": 0})
        c["credits"] = int(c.get("credits", 0)) + int(delta)
        self.credit_tags.setdefault(int(cid), []).append(tag)
        return c["credits"]

    async def get_characters_in_room(self, room_id):
        return [dict(c) for c in self.room_occupants.get(int(room_id), [])]


def _seed_site(db, region, room_id=900):
    db.rooms[room_id] = {"id": room_id, "name": "Scenario Site",
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
# F8 — mid-stage prune-race: a resolved-but-unconsumed stage anomaly must
# survive BOTH real prune paths and still credit + advance exactly once
# once the (delayed) poll reaches it. A redundant later poll must not
# double-credit (idempotent consumption).
# ════════════════════════════════════════════════════════════════════════════

def test_mid_stage_prune_race_survives_and_credits_once(monkeypatch):
    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
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

        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        active = await COR.get_active(db)
        active_id = active["id"]
        state = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state["idx"] == 0

        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom is not None and anom.template_key == TEMPLATES[0]
        assert anom.scenario_hold is True, (
            "arm_stage_site must spawn the stage anomaly with "
            "scenario_hold=True (F8/F9 prune exemption)")

        # THE REAL RESOLVER SIGNAL, stamped exactly as the real resolve
        # paths do (no push-notify triggered here — this isolates fix
        # (a): the prune exemption + idempotent consumption gate, alone).
        anom.resolved = True
        anom.resolved_by = CHAR_ID

        # Drive the REAL prune path an in-region `anomalies` command uses
        # (WA.get_anomalies_for_region -> _prune_expired_region, pure) —
        # well past the anomaly's old 30s resolved-linger window.
        removed = WA._prune_expired_region(REGION_SLUG, anom.expiry + 3600)
        assert removed == 0, (
            "a resolved scenario_hold anomaly must NOT be pruned before "
            "the orchestrator consumes it (F8/F9 regression)")
        assert WA.find_anomaly_globally(anom.id) is not None, (
            "the resolved stage anomaly was evicted by prune — the "
            "exact F8/F9 bug")

        # Also drive the DB-touching tick variant (the hourly T1 tick's
        # real path) — must likewise be a no-op removal.
        removed2 = await WA._prune_expired_region_with_cleanup(
            db, REGION_SLUG, anom.expiry + 3600)
        assert removed2 == 0
        assert WA.find_anomaly_globally(anom.id) is not None

        # NOW the (delayed) poll consumes it.
        result = await COR.on_scenario_progress(db, None, active)
        assert result != CO.STATE_WON  # not the final stage

        contribs = _raw_contribs(db, active_id)
        pts = int(contribs[str(CHAR_ID)]["points"])
        assert pts == CO.stage_clear_points(), (
            "the prune-surviving stage clear must credit full points "
            f"exactly once; got {pts}")

        # The consumed anomaly is gone (explicit deletion), stage 2 armed.
        assert WA.find_anomaly_globally(anom.id) is None
        active2 = await COR.get_active(db)
        state2 = SE.get_stage_state(json.loads(active2["contributions_json"]))
        assert state2["idx"] == 1

        # A REDUNDANT poll racing on the OLD (stale, pre-advance) active
        # snapshot must be a pure no-op — idempotency between (a)/(b)/a
        # racing second poll, and it must NOT stomp the already-advanced
        # stage with a duplicate re-arm.
        result_stale = await COR.on_scenario_progress(db, None, active)
        assert result_stale is None
        contribs_after = _raw_contribs(db, active_id)
        assert contribs_after[str(CHAR_ID)]["points"] == pts, (
            "a redundant/stale poll on an already-consumed anomaly must "
            "not double-credit")
        state_after = SE.get_stage_state(contribs_after)
        assert state_after["idx"] == 1, (
            "a stale redundant poll must not stomp the already-advanced "
            "stage index with a duplicate re-arm")

        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# F9 — same prune-race on the FINAL stage: the whole multi-stage win must
# still finalize (rep/title/capstone/relic) instead of being silently
# discarded with the objective stuck 'active'.
# ════════════════════════════════════════════════════════════════════════════

def test_final_stage_prune_race_still_wins_and_pays_capstone(monkeypatch):
    rep_calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        rep_calls.append((int(char["id"]), faction, int(delta or 0)))
        return int(delta or 0)
    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    CHAR_ID = 601

    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
        db.chars[CHAR_ID] = {"id": CHAR_ID, "attributes": "{}", "credits": 0,
                             "inventory": "[]"}

        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)

        # Clear stages 1 and 2 cleanly (no race) — the real resolver
        # signal, no push-notify race.
        for stage_idx in range(len(TEMPLATES) - 1):
            active = await COR.get_active(db)
            state = SE.get_stage_state(json.loads(active["contributions_json"]))
            assert state["idx"] == stage_idx
            anom = WA.find_anomaly_globally(state["anomaly_id"])
            anom.resolved = True
            anom.resolved_by = CHAR_ID
            result = await COR.on_scenario_progress(db, None, active)
            assert result != CO.STATE_WON

        # Now the FINAL stage — race it exactly as above.
        active = await COR.get_active(db)
        state = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state["idx"] == len(TEMPLATES) - 1
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom.scenario_hold is True
        anom.resolved = True
        anom.resolved_by = CHAR_ID

        removed = WA._prune_expired_region(REGION_SLUG, anom.expiry + 3600)
        assert removed == 0
        assert WA.find_anomaly_globally(anom.id) is not None, (
            "the FINAL stage's resolved anomaly was evicted by prune — "
            "the entire multi-stage win would have been discarded "
            "(F9 regression)")

        result = await COR.on_scenario_progress(db, None, active)
        assert result == CO.STATE_WON, (
            "the prune-surviving FINAL stage clear must still finalize "
            "the win")

        # objective no longer active
        assert await COR.get_active(db) is None

        # rep paid
        assert any(cid == CHAR_ID and fac == CO.REP_FACTION and delta > 0
                   for (cid, fac, delta) in rep_calls), "rep payout missing"

        # capstone credits paid exactly once via the metered faucet
        assert db.chars[CHAR_ID]["credits"] == CO.win_capstone_credits()
        assert db.credit_tags.get(CHAR_ID) == ["communal_win_capstone"]

        # relic granted
        inv = coerce_inventory(db.chars[CHAR_ID]["inventory"])
        assert any(it.get("is_capstone_loot") for it in inv["items"]), \
            "capstone relic not granted after a prune-raced final clear"

        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# F10 — participant fan-out: a real T2 combat payout's OTHER room-occupant
# participant (never the resolved_by finisher) must earn a reduced share
# of the stage-clear points, not zero.
# ════════════════════════════════════════════════════════════════════════════

def test_combat_payout_credits_other_participants_a_reduced_share(monkeypatch):
    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        return int(delta or 0)
    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    RESOLVER, COFIGHTER = 701, 702

    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
        db.chars[RESOLVER] = {"id": RESOLVER, "attributes": "{}",
                              "credits": 0, "inventory": "[]"}
        db.chars[COFIGHTER] = {"id": COFIGHTER, "attributes": "{}",
                               "credits": 0, "inventory": "[]"}

        active0 = await COR.get_active(db)
        await COR.arm_stage_site(db, None, active0, now_ms=1_000_000)
        active = await COR.get_active(db)
        active_id = active["id"]
        state = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state["idx"] == 0
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom.tier == 2 and anom.resolution_mode == "combat"

        # Both fighters are in the room when the wave clears — the REAL
        # T2 payout enumerates room occupants as participants.
        db.room_occupants[anom.anchor_room_id] = [
            {"id": RESOLVER, "inventory": "[]"},
            {"id": COFIGHTER, "inventory": "[]"},
        ]

        # Drive the REAL production payout function (the same one the
        # combat kill hook calls) — RESOLVER lands the finishing blow.
        rng = random.Random(1)
        payout = await WA._payout_combat_anomaly(
            db, anom, RESOLVER, rng, 1_000_030.0, session_mgr=None,
        )
        assert payout is not None
        assert set(payout["participants"]) == {RESOLVER, COFIGHTER}
        assert anom.resolved_participants and set(anom.resolved_participants) == {
            RESOLVER, COFIGHTER,
        }

        # The push-notify fired inline (this stage's anomaly matched the
        # active uprising's armed anomaly_id) and already advanced the
        # stage — verify the REAL communal points ledger, not a
        # hand-injected one.
        contribs = _raw_contribs(db, active_id)
        full = CO.stage_clear_points()
        share = CO.staged_participant_share()
        expected_share = max(1, int(round(full * share)))

        assert int(contribs[str(RESOLVER)]["points"]) == full, (
            "the resolver must earn the full stage-clear points")
        assert int(contribs[str(COFIGHTER)]["points"]) == expected_share, (
            "F10: a real combat-payout co-participant who never landed "
            "the killing blow must earn a reduced share, not zero")
        assert expected_share > 0 and expected_share < full, (
            "the co-participant share must be strictly between 0 and "
            "the resolver's full points for the conservative default "
            "(communal.staged_participant_share=0.5)")

        WA._reset_state_for_tests()
    _run(go())


def test_staged_participant_share_zero_disables_fanout(monkeypatch):
    """Live-tunable check: communal.staged_participant_share=0 must fully
    disable the co-participant fan-out (resolver-only — the pre-fix
    behavior), proving the tunable is a real, wired consumer."""
    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        return int(delta or 0)
    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    from engine import tunables
    monkeypatch.setattr(
        tunables, "get_tunable",
        lambda key, default=None: (
            0.0 if key == "communal.staged_participant_share" else default
        ),
    )

    RESOLVER, COFIGHTER = 801, 802

    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
        db.chars[RESOLVER] = {"id": RESOLVER, "attributes": "{}",
                              "credits": 0, "inventory": "[]"}
        db.chars[COFIGHTER] = {"id": COFIGHTER, "attributes": "{}",
                               "credits": 0, "inventory": "[]"}

        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        active = await COR.get_active(db)
        active_id = active["id"]
        state = SE.get_stage_state(json.loads(active["contributions_json"]))
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        db.room_occupants[anom.anchor_room_id] = [
            {"id": RESOLVER, "inventory": "[]"},
            {"id": COFIGHTER, "inventory": "[]"},
        ]

        rng = random.Random(2)
        await WA._payout_combat_anomaly(
            db, anom, RESOLVER, rng, 1_000_030.0, session_mgr=None,
        )

        contribs = _raw_contribs(db, active_id)
        assert int(contribs[str(RESOLVER)]["points"]) == CO.stage_clear_points()
        assert str(COFIGHTER) not in contribs, (
            "communal.staged_participant_share=0 must disable the "
            "co-participant fan-out entirely")

        WA._reset_state_for_tests()
    _run(go())


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
