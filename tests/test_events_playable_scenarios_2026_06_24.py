# -*- coding: utf-8 -*-
"""tests/test_events_playable_scenarios_2026_06_24.py — events as PLAYABLE
site scenarios (vertical slice: Cult of the Hollow Sun).

Resolves Brian's complaint that `rally` / `rally strike` "isn't gameplay — it's
a counter, not a scenario. Events should be: go to a LOCATION, fight waves of
enemies, slice terminals." This drop composes the EXISTING wilderness-anomaly
substrate (multi-phase wave combat + the live resolution:"skill" path) with the
staged-event stage cursor so the Hollow Sun becomes a 3-stage site scenario:

  Stage 1  wave combat  (hollow_sun_shrine_assault, multi-phase)
  Stage 2  skill gate    (hollow_sun_cistern_slice, resolution:"skill")
  Stage 3  boss          (hollow_sun_hierophant, multi-phase)

See docs/design/events_playable_scenarios_design_v1.md. This test walks the
scenario end-to-end through the REAL orchestrator + REAL anomaly registry +
REAL runtime SQL (rep stubbed), proving the slice is playable and additive.

Run: python -m pytest tests/test_events_playable_scenarios_2026_06_24.py
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


def _run(coro):
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════════════
# Pure-layer: the staged-event descriptors carry the per-stage anomaly mapping
# ════════════════════════════════════════════════════════════════════════════

def test_each_stage_maps_to_a_real_anomaly_template():
    """Every Hollow Sun stage names a template that actually exists in the live
    anomaly registry (no phantom producer)."""
    stages = SE.stages_for("hollow_sun")
    assert stages and len(stages) == 3
    for s in stages:
        key = s.get("anomaly_template")
        assert key, f"stage {s['key']} has no anomaly_template"
        # resolves in the scenario catalog (the .template lookup chain)
        assert key in WA.SCENARIO_TEMPLATES, f"{key} not registered"


def test_stage_kinds_match_anomaly_resolution_modes():
    """Combat/boss stages map to combat anomalies; the skill stage maps to a
    resolution:'skill' anomaly (the live skill path, not the inert seam)."""
    by_key = {s["key"]: s for s in SE.stages_for("hollow_sun")}
    assert WA.SCENARIO_TEMPLATES[by_key["shrines"]["anomaly_template"]]["resolution"] == "combat"
    assert WA.SCENARIO_TEMPLATES[by_key["tithes"]["anomaly_template"]]["resolution"] == "skill"
    assert WA.SCENARIO_TEMPLATES[by_key["hierophant"]["anomaly_template"]]["resolution"] == "combat"


def test_current_stage_anomaly_spec_walks_with_the_cursor():
    spec0 = SE.current_stage_anomaly_spec("hollow_sun", {"idx": 0, "progress": 0})
    spec1 = SE.current_stage_anomaly_spec("hollow_sun", {"idx": 1, "progress": 0})
    spec2 = SE.current_stage_anomaly_spec("hollow_sun", {"idx": 2, "progress": 0})
    assert spec0 == ("hollow_sun_shrine_assault", 2)
    assert spec1 == ("hollow_sun_cistern_slice", 1)
    assert spec2 == ("hollow_sun_hierophant", 2)
    # past the last stage → no anomaly to arm
    assert SE.current_stage_anomaly_spec("hollow_sun", {"idx": 3, "progress": 0}) is None


def test_stage_state_carries_site_and_anomaly_through_contribs():
    contribs = {}
    SE.set_stage_state(contribs, {"idx": 1, "progress": 2,
                                  "site_room_id": 4123, "anomaly_id": 57})
    got = SE.get_stage_state(contribs)
    assert got == {"idx": 1, "progress": 2, "site_room_id": 4123, "anomaly_id": 57}
    # back-compat: the original two-key shape still round-trips and defaults clean
    SE.set_stage_state(contribs, {"idx": 0, "progress": 0})
    assert SE.get_stage_state(contribs) == {"idx": 0, "progress": 0}


def test_tracker_points_to_the_site_when_armed():
    state = {"idx": 0, "progress": 0, "site_room_id": 4123, "anomaly_id": 57}
    lines = "\n".join(SE.stage_tracker_lines(
        "the Cult of the Hollow Sun", "hollow_sun", state, site_label="The Sun Shrines"))
    assert "investigate" in lines.lower()
    assert "The Sun Shrines" in lines
    assert "rally strike" not in lines  # demoted when the site is live


def test_era_clean_scenario_strings():
    """B3/Q1: no Imperial/Rebel/canon strings in the authored cult templates."""
    banned = ["imperial", "empire", "rebel", "stormtrooper", "tie ", "x-wing",
              "star destroyer", "vader", "sidious", "dooku", "grievous", "sith"]
    blob = json.dumps(WA.SCENARIO_TEMPLATES).lower()
    for bad in banned:
        assert bad not in blob, f"banned term {bad!r} in scenario templates"


# ════════════════════════════════════════════════════════════════════════════
# Runtime layer: a mini-DB with rooms + NPCs over the real communal table
# ════════════════════════════════════════════════════════════════════════════

class _SceneDB:
    """aiosqlite-shaped wrapper: real communal_objective table + an in-memory
    rooms/npcs/chars store, enough for the scenario orchestrator + anomaly
    spawn/resolve paths."""
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for sql in MIGRATIONS[43]:
            self.conn.execute(sql)
        self.conn.commit()
        self.rooms: dict[int, dict] = {}
        self.npcs: dict[int, dict] = {}
        self.chars: dict[int, dict] = {}
        self._npc_counter = 0

    async def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    async def fetchall(self, sql, params=()):
        # rooms-table queries from _pick_anchor_room land here.
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
        return c["credits"]

    async def create_npc(self, **kw):
        self._npc_counter += 1
        nid = self._npc_counter
        self.npcs[nid] = dict(kw, id=nid)
        return nid

    async def get_npc(self, nid):
        return self.npcs.get(int(nid))


def _seed_site(db):
    """Put one landmark room in the cult's region so the site can anchor."""
    db.rooms[900] = {"id": 900, "name": "The Sun Shrines",
                     "zone_id": 12, "wilderness_region_id": "tatooine_dune_sea"}


# ════════════════════════════════════════════════════════════════════════════
# spawn_scenario_anomaly — deterministic, resolvable, live
# ════════════════════════════════════════════════════════════════════════════

def test_spawn_scenario_anomaly_anchors_the_named_template():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        anom = await WA.spawn_scenario_anomaly(
            db, "tatooine_dune_sea", "hollow_sun_shrine_assault", 900, tier=2)
        assert anom is not None
        assert anom.template_key == "hollow_sun_shrine_assault"
        assert anom.anchor_room_id == 900
        assert anom.tier == 2
        assert anom.resolution_mode == "combat"
        # it's findable in the live registry, like any anomaly
        assert WA.find_anomaly_globally(anom.id) is anom
        WA._reset_state_for_tests()
    _run(go())


def test_spawn_scenario_anomaly_unknown_template_returns_none():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        assert await WA.spawn_scenario_anomaly(
            db, "tatooine_dune_sea", "no_such_template", 900) is None
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# arm_stage_site — the orchestrator anchors the site + spawns stage 1
# ════════════════════════════════════════════════════════════════════════════

def test_post_arms_stage_one_site_for_a_staged_cult():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        # rotation 0 → hollow_sun (staged). maybe_post should arm stage 1.
        posted = await COR.maybe_post(db, None, now_ms=1_000_000)
        assert posted is not None and posted["cult_key"] == "hollow_sun"
        contribs = json.loads(posted["contributions_json"])
        state = SE.get_stage_state(contribs)
        assert state["site_room_id"] == 900
        assert state.get("anomaly_id") is not None
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom is not None
        assert anom.template_key == "hollow_sun_shrine_assault"
        WA._reset_state_for_tests()
    _run(go())


def test_arm_is_idempotent_while_the_stage_anomaly_is_live():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        posted = await COR.maybe_post(db, None, now_ms=1_000_000)
        first_id = SE.get_stage_state(json.loads(posted["contributions_json"]))["anomaly_id"]
        # arming again must NOT spawn a second anomaly for the same stage
        again = await COR.arm_stage_site(db, None, posted)
        second_id = SE.get_stage_state(json.loads(again["contributions_json"]))["anomaly_id"]
        assert first_id == second_id
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# Full scenario walk — clear each stage → advance → win on the last
# ════════════════════════════════════════════════════════════════════════════

def test_full_scenario_walk_advances_stages_and_wins(monkeypatch):
    """Clearing each stage's site anomaly (simulating investigate/combat) walks
    the stage cursor and finalizes the objective WIN on the last stage — paying
    the existing communal rep payout."""
    rep_calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        rep_calls.append((int(char["id"]), faction, int(delta or 0)))
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        posted = await COR.maybe_post(db, None, now_ms=1_000_000)
        # a contributor with banked points so the win pays out
        db.chars[42] = {"id": 42, "attributes": "{}"}

        expected = ["hollow_sun_shrine_assault",
                    "hollow_sun_cistern_slice",
                    "hollow_sun_hierophant"]
        for stage_idx, expect_key in enumerate(expected):
            active = await COR.get_active(db)
            assert active is not None, f"objective gone at stage {stage_idx}"
            state = SE.get_stage_state(json.loads(active["contributions_json"]))
            assert state["idx"] == stage_idx
            anom_id = state["anomaly_id"]
            anom = WA.find_anomaly_globally(anom_id)
            assert anom is not None and anom.template_key == expect_key
            # simulate the player clearing this stage's anomaly via the site
            anom.resolved = True
            # seed a contribution so the final win has a payee
            contribs = json.loads(active["contributions_json"])
            contribs["42"] = {"points": 50, "last_strike_at": 1.0}
            SE.set_stage_state(contribs, state)
            await db.execute(
                "UPDATE communal_objective SET contributions_json=? WHERE id=?",
                (json.dumps(contribs), int(active["id"])),
            )
            await db.commit()
            # poll the scenario forward (what `rally` / the tick do)
            await COR.on_scenario_progress(db, None, await COR.get_active(db))

        # after clearing all three, the objective is WON (no longer active)
        assert await COR.get_active(db) is None
        # the existing communal rep payout fired for the contributor
        assert any(cid == 42 and fac == CO.REP_FACTION for (cid, fac, d) in rep_calls)
        WA._reset_state_for_tests()
    _run(go())


def test_skill_stage_is_a_live_skill_anomaly(monkeypatch):
    """Stage 2 (Cut the Water Tithes) resolves through the REAL
    _resolve_anomaly_skill path — a slicer rolls security and the anomaly
    resolves, paying via the metered anomaly credit faucet."""
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        anom = await WA.spawn_scenario_anomaly(
            db, "tatooine_dune_sea", "hollow_sun_cistern_slice", 900, tier=1)
        assert anom.resolution_mode == "skill"

        # a competent slicer (security 6D) standing at the site. skills/attrs
        # are WEG dice-code strings, the shape perform_skill_check expects.
        char = {"id": 5, "name": "Slicer", "room_id": 900,
                "faction_id": "independent", "credits": 0,
                "skills": json.dumps({"security": "6D"}),
                "attributes": json.dumps({"knowledge": "4D"})}
        import random
        result = await WA._resolve_anomaly_skill(
            db, char, anom, "tatooine_dune_sea",
            rng=random.Random(1), now=1.0)
        assert result["ok"] and result["mode"] == "skill"
        assert anom.resolved  # one-shot resolve
        # credits paid through the metered faucet (adjust_credits)
        assert result["credits"] >= 0
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# get_active contract (Situation Board / UX Drop 4) preserved
# ════════════════════════════════════════════════════════════════════════════

def test_get_active_row_still_exposes_situation_board_columns():
    """The Situation Board digest reads cult_key/zone_label/menace/state from
    get_active. The scenario rework must keep those columns intact."""
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        await COR.maybe_post(db, None, now_ms=1_000_000)
        active = await COR.get_active(db)
        for col in ("cult_key", "zone_label", "menace", "state"):
            assert col in active.keys(), f"Situation-Board column {col} missing"
        assert active["state"] == CO.STATE_ACTIVE
        WA._reset_state_for_tests()
    _run(go())


def test_expired_stage_anomaly_rearms_same_stage_not_advance():
    """A stage whose site anomaly ages out UNcleared must RE-ARM the same stage,
    NOT free-advance the cursor. You can't win a staged scenario by waiting (the
    menace timer is the overall failure clock). Regression for the on_scenario_
    progress expire-vs-clear blocker (advancing on a vanished anomaly granted a
    whole stage of credit for zero player action)."""
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        posted = await COR.maybe_post(db, None, now_ms=1_000_000)
        state0 = SE.get_stage_state(json.loads(posted["contributions_json"]))
        assert state0["idx"] == 0 and state0["anomaly_id"] is not None
        first_id = state0["anomaly_id"]
        # Simulate the stage anomaly aging out UNcleared: drop it from the live
        # registry while the DB still records its (now-stale) anomaly_id.
        WA._reset_state_for_tests()
        assert WA.find_anomaly_globally(first_id) is None
        # poll forward (what the tick / `rally` do) — must RE-ARM stage 0
        await COR.on_scenario_progress(db, None, await COR.get_active(db))
        active = await COR.get_active(db)
        assert active is not None, "objective wrongly ended on an uncleared expire"
        state1 = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state1["idx"] == 0, "stage WRONGLY advanced on an uncleared expire"
        assert state1.get("anomaly_id") is not None, "stage was not re-armed"
        re_anom = WA.find_anomaly_globally(state1["anomaly_id"])
        assert re_anom is not None
        assert re_anom.template_key == "hollow_sun_shrine_assault"  # still stage 1
        WA._reset_state_for_tests()
    _run(go())


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
