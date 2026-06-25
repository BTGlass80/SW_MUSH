# -*- coding: utf-8 -*-
"""tests/test_events_more_scenarios_2026_06_24.py — TWO more communal objectives
become PLAYABLE site scenarios (events_more_scenarios drop).

The Cult of the Hollow Sun proved the staged-scenario pattern
(tests/test_events_playable_scenarios_2026_06_24.py). This drop extends it,
WITHOUT new orchestration, to the next two cults whose world already has a
wilderness region to anchor a site:

  Ember Court (Geonosis / geonosis_ey_akh)
    Stage 1  wave combat  (ember_court_forge_assault, multi-phase)
    Stage 2  skill gate    (ember_court_relay_slice, resolution:"skill")
    Stage 3  boss          (ember_court_forgemaster, multi-phase)

  Ashen Hand (Coruscant / coruscant_underworld)
    Stage 1  wave combat  (ashen_hand_warren_assault, multi-phase)
    Stage 2  skill gate    (ashen_hand_informant_turn, resolution:"skill")
    Stage 3  boss          (ashen_hand_ashfather, multi-phase)

Each walks the scenario end-to-end through the SAME orchestrator + REAL anomaly
registry + REAL runtime SQL (rep stubbed), proving the new cults are additive
DATA that flow through the existing engine. Mirrors the Hollow Sun test exactly.

Run: python -m pytest tests/test_events_more_scenarios_2026_06_24.py
(asyncio.run, Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest

import engine.communal_objective as CO
import engine.communal_objective_runtime as COR
import engine.staged_event as SE
import engine.wilderness_anomalies as WA
from db.database import MIGRATIONS


def _run(coro):
    return asyncio.run(coro)


# The two cults this drop converts, with their anchoring region + the ordered
# template keys per stage. Each parametrizes the full walk below.
NEW_SCENARIOS = {
    "ember_court": {
        "region": "geonosis_ey_akh",
        "templates": ["ember_court_forge_assault",
                      "ember_court_relay_slice",
                      "ember_court_forgemaster"],
        "stage_keys": ["forge_tunnels", "relays", "forgemaster"],
        "specs": [("ember_court_forge_assault", 2),
                  ("ember_court_relay_slice", 1),
                  ("ember_court_forgemaster", 2)],
    },
    "ashen_hand": {
        "region": "coruscant_underworld",
        "templates": ["ashen_hand_warren_assault",
                      "ashen_hand_informant_turn",
                      "ashen_hand_ashfather"],
        "stage_keys": ["warrens", "informants", "ashfather"],
        "specs": [("ashen_hand_warren_assault", 2),
                  ("ashen_hand_informant_turn", 1),
                  ("ashen_hand_ashfather", 2)],
    },
}

CULTS = sorted(NEW_SCENARIOS)


# ════════════════════════════════════════════════════════════════════════════
# Pure-layer: the staged-event descriptors carry the per-stage anomaly mapping
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cult", CULTS)
def test_cult_is_staged(cult):
    """is_staged is true and the cult has exactly 3 stages, each a real
    CO.CULT_BY_KEY entry (no phantom cult)."""
    assert cult in CO.CULT_BY_KEY
    assert SE.is_staged(cult)
    stages = SE.stages_for(cult)
    assert stages and len(stages) == 3


@pytest.mark.parametrize("cult", CULTS)
def test_each_stage_maps_to_a_real_anomaly_template(cult):
    """Every stage names a template that actually exists in the live anomaly
    registry (no phantom producer)."""
    stages = SE.stages_for(cult)
    for s in stages:
        key = s.get("anomaly_template")
        assert key, f"{cult} stage {s['key']} has no anomaly_template"
        assert key in WA.SCENARIO_TEMPLATES, f"{key} not registered"
        # the template self-identifies as belonging to this cult's scenario
        assert WA.SCENARIO_TEMPLATES[key].get("scenario") == cult
        # orchestrator-spawned only — never tick-rolled into the open world
        assert WA.SCENARIO_TEMPLATES[key].get("regions") == []


@pytest.mark.parametrize("cult", CULTS)
def test_stage_kinds_match_anomaly_resolution_modes(cult):
    """Combat/boss stages map to combat anomalies; the middle skill stage maps
    to a resolution:'skill' anomaly (the live skill path, not the inert seam)."""
    keys = NEW_SCENARIOS[cult]["templates"]
    assert WA.SCENARIO_TEMPLATES[keys[0]]["resolution"] == "combat"
    assert WA.SCENARIO_TEMPLATES[keys[1]]["resolution"] == "skill"
    assert WA.SCENARIO_TEMPLATES[keys[2]]["resolution"] == "combat"
    # the skill stage's stage descriptor is KIND_SKILL
    by_key = {s["key"]: s for s in SE.stages_for(cult)}
    skill_stage_key = NEW_SCENARIOS[cult]["stage_keys"][1]
    assert by_key[skill_stage_key]["kind"] == SE.KIND_SKILL


@pytest.mark.parametrize("cult", CULTS)
def test_skill_stage_names_live_skills(cult):
    """The skill template names primary/secondary skills the live resolver reads
    (NOT the inert skill_gate seam)."""
    skill_key = NEW_SCENARIOS[cult]["templates"][1]
    tmpl = WA.SCENARIO_TEMPLATES[skill_key]
    assert tmpl.get("primary_skill")
    assert tmpl.get("secondary_skill")
    # and a fail_reward exists so the one-shot skill path always resolves
    assert "fail_reward" in tmpl


@pytest.mark.parametrize("cult", CULTS)
def test_current_stage_anomaly_spec_walks_with_the_cursor(cult):
    specs = NEW_SCENARIOS[cult]["specs"]
    for idx, expect in enumerate(specs):
        got = SE.current_stage_anomaly_spec(cult, {"idx": idx, "progress": 0})
        assert got == expect, f"{cult} stage {idx}: {got!r} != {expect!r}"
    # past the last stage → no anomaly to arm
    assert SE.current_stage_anomaly_spec(cult, {"idx": 3, "progress": 0}) is None


@pytest.mark.parametrize("cult", CULTS)
def test_scenario_region_matches(cult):
    assert SE.scenario_region(cult) == NEW_SCENARIOS[cult]["region"]


def test_era_clean_new_scenario_strings():
    """B3/Q1: no Imperial/Rebel/canon strings anywhere in the authored cult
    templates (whole SCENARIO_TEMPLATES blob, including the two new cults)."""
    banned = ["imperial", "empire", "rebel", "stormtrooper", "tie ", "x-wing",
              "star destroyer", "vader", "sidious", "dooku", "grievous", "sith"]
    blob = json.dumps(WA.SCENARIO_TEMPLATES).lower()
    for bad in banned:
        assert bad not in blob, f"banned term {bad!r} in scenario templates"


# ════════════════════════════════════════════════════════════════════════════
# Runtime layer: a mini-DB with rooms + NPCs over the real communal table
# (mirrors the Hollow Sun test's _SceneDB)
# ════════════════════════════════════════════════════════════════════════════

class _SceneDB:
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


def _seed_site(db, region):
    """Put one landmark room in the cult's region so the site can anchor."""
    db.rooms[900] = {"id": 900, "name": "Scenario Site",
                     "zone_id": 12, "wilderness_region_id": region}


def _force_post_cult(db, cult_key, now_ms):
    """Insert an active uprising for a SPECIFIC cult (the rotation order would
    otherwise pick another). Mirrors maybe_post's INSERT, then arms stage 1."""
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


# ════════════════════════════════════════════════════════════════════════════
# spawn_scenario_anomaly — each new template anchors, deterministic + live
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cult", CULTS)
def test_spawn_scenario_anomaly_anchors_each_template(cult):
    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        for template_key, tier in NEW_SCENARIOS[cult]["specs"]:
            WA._reset_state_for_tests()
            db = _SceneDB()
            _seed_site(db, region)
            anom = await WA.spawn_scenario_anomaly(
                db, region, template_key, 900, tier=tier)
            assert anom is not None, f"{template_key} failed to spawn"
            assert anom.template_key == template_key
            assert anom.anchor_room_id == 900
            assert anom.tier == tier
            assert WA.find_anomaly_globally(anom.id) is anom
            WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# arm_stage_site — the orchestrator anchors the site + spawns stage 1
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cult", CULTS)
def test_arm_stage_one_site_for_each_new_cult(cult):
    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        first_template = NEW_SCENARIOS[cult]["templates"][0]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, region)
        _force_post_cult(db, cult, now_ms=1_000_000)
        active = await COR.get_active(db)
        armed = await COR.arm_stage_site(db, None, active, now_ms=1_000_000)
        assert armed is not None and armed["cult_key"] == cult
        state = SE.get_stage_state(json.loads(armed["contributions_json"]))
        assert state["site_room_id"] == 900
        assert state.get("anomaly_id") is not None
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom is not None and anom.template_key == first_template
        WA._reset_state_for_tests()
    _run(go())


@pytest.mark.parametrize("cult", CULTS)
def test_arm_is_idempotent_while_the_stage_anomaly_is_live(cult):
    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, region)
        _force_post_cult(db, cult, now_ms=1_000_000)
        active = await COR.get_active(db)
        armed = await COR.arm_stage_site(db, None, active)
        first_id = SE.get_stage_state(json.loads(armed["contributions_json"]))["anomaly_id"]
        again = await COR.arm_stage_site(db, None, armed)
        second_id = SE.get_stage_state(json.loads(again["contributions_json"]))["anomaly_id"]
        assert first_id == second_id
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# Full scenario walk — clear each stage → advance → win on the last
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cult", CULTS)
def test_full_scenario_walk_advances_stages_and_wins(cult, monkeypatch):
    """Clearing each stage's site anomaly (simulating investigate/combat) walks
    the stage cursor and finalizes the objective WIN on the last stage — paying
    the EXISTING communal rep payout (no new faucet)."""
    rep_calls = []

    async def _fake_adjust_rep(char, faction, db, delta=None, reason=None, **kw):
        rep_calls.append((int(char["id"]), faction, int(delta or 0)))
        return int(delta or 0)

    import engine.organizations as ORG
    monkeypatch.setattr(ORG, "adjust_rep", _fake_adjust_rep, raising=False)

    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        expected = NEW_SCENARIOS[cult]["templates"]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, region)
        _force_post_cult(db, cult, now_ms=1_000_000)
        # arm stage 1
        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        db.chars[42] = {"id": 42, "attributes": "{}"}

        for stage_idx, expect_key in enumerate(expected):
            active = await COR.get_active(db)
            assert active is not None, f"{cult}: objective gone at stage {stage_idx}"
            state = SE.get_stage_state(json.loads(active["contributions_json"]))
            assert state["idx"] == stage_idx
            anom = WA.find_anomaly_globally(state["anomaly_id"])
            assert anom is not None and anom.template_key == expect_key, \
                f"{cult} stage {stage_idx}: wrong template"
            # simulate the player clearing this stage's anomaly via the site
            anom.resolved = True
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
        assert await COR.get_active(db) is None, f"{cult}: did not win on last stage"
        # the EXISTING communal rep payout fired for the contributor
        assert any(cid == 42 and fac == CO.REP_FACTION
                   for (cid, fac, d) in rep_calls), f"{cult}: rep payout missing"
        WA._reset_state_for_tests()
    _run(go())


@pytest.mark.parametrize("cult", CULTS)
def test_skill_stage_is_a_live_skill_anomaly(cult):
    """The middle stage resolves through the REAL _resolve_anomaly_skill path —
    a competent character rolls the stage's primary skill and the anomaly
    resolves, paying via the metered anomaly credit faucet (adjust_credits)."""
    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        skill_template = NEW_SCENARIOS[cult]["templates"][1]
        primary = WA.SCENARIO_TEMPLATES[skill_template]["primary_skill"]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, region)
        anom = await WA.spawn_scenario_anomaly(
            db, region, skill_template, 900, tier=1)
        assert anom.resolution_mode == "skill"

        char = {"id": 5, "name": "Specialist", "room_id": 900,
                "faction_id": "independent", "credits": 0,
                "skills": json.dumps({primary: "6D"}),
                "attributes": json.dumps({"knowledge": "4D",
                                          "perception": "4D"})}
        import random
        result = await WA._resolve_anomaly_skill(
            db, char, anom, region, rng=random.Random(1), now=1.0)
        assert result["ok"] and result["mode"] == "skill"
        assert anom.resolved  # one-shot resolve
        assert result["credits"] >= 0
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# get_active contract (Situation Board / UX Drop 4) preserved
# ════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cult", CULTS)
def test_get_active_row_still_exposes_situation_board_columns(cult):
    """The Situation Board digest reads cult_key/zone_label/menace/state from
    get_active. The scenario rework must keep those columns intact and ride
    scenario state in contributions_json only."""
    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, region)
        _force_post_cult(db, cult, now_ms=1_000_000)
        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        active = await COR.get_active(db)
        for col in ("cult_key", "zone_label", "menace", "state"):
            assert col in active.keys(), f"Situation-Board column {col} missing"
        assert active["state"] == CO.STATE_ACTIVE
        assert active["cult_key"] == cult
        # scenario state rides contributions_json['_stage'] only
        contribs = json.loads(active["contributions_json"])
        assert "_stage" in contribs
        WA._reset_state_for_tests()
    _run(go())


@pytest.mark.parametrize("cult", CULTS)
def test_expired_stage_anomaly_rearms_same_stage_not_advance(cult):
    """A stage whose site anomaly ages out UNcleared must RE-ARM the same stage,
    NOT free-advance the cursor (the expire-vs-clear invariant). Regression for
    each new cult."""
    async def go():
        region = NEW_SCENARIOS[cult]["region"]
        first_template = NEW_SCENARIOS[cult]["templates"][0]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, region)
        _force_post_cult(db, cult, now_ms=1_000_000)
        armed = await COR.arm_stage_site(db, None, await COR.get_active(db),
                                         now_ms=1_000_000)
        state0 = SE.get_stage_state(json.loads(armed["contributions_json"]))
        assert state0["idx"] == 0 and state0["anomaly_id"] is not None
        first_id = state0["anomaly_id"]
        # Simulate the stage anomaly aging out UNcleared: drop the registry.
        WA._reset_state_for_tests()
        assert WA.find_anomaly_globally(first_id) is None
        await COR.on_scenario_progress(db, None, await COR.get_active(db))
        active = await COR.get_active(db)
        assert active is not None, f"{cult}: wrongly ended on an uncleared expire"
        state1 = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state1["idx"] == 0, f"{cult}: stage WRONGLY advanced on expire"
        assert state1.get("anomaly_id") is not None, f"{cult}: stage not re-armed"
        re_anom = WA.find_anomaly_globally(state1["anomaly_id"])
        assert re_anom is not None and re_anom.template_key == first_template
        WA._reset_state_for_tests()
    _run(go())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
