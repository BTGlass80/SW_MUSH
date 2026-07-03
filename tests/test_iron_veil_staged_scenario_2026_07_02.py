# -*- coding: utf-8 -*-
"""tests/test_iron_veil_staged_scenario_2026_07_02.py — the Iron Veil (Kuat)
becomes a PLAYABLE site scenario (iron_veil_kuat_staged_scenario drop).

Mirrors tests/test_events_more_scenarios_2026_06_24.py exactly (which proved
the pattern for Ember Court/Ashen Hand). Kuat had no wilderness substrate at
events_more_scenarios time (2026-06-24) — this drop authors one
(wilderness/kuat_sabotaged_yards.yaml) so the Iron Veil converts too:

  Iron Veil (Kuat / kuat_sabotaged_yards)
    Stage 1  wave combat  (iron_veil_cell_assault, multi-phase)
    Stage 2  skill gate    (iron_veil_power_relay, resolution:"skill")
    Stage 3  boss          (iron_veil_veilmaster, multi-phase)

Walks the scenario end-to-end through the SAME orchestrator + REAL anomaly
registry + REAL runtime SQL (rep stubbed), proving the new cult is additive
DATA that flows through the existing engine. Mirrors the Ember Court/Ashen
Hand test exactly.

Run: python -m pytest tests/test_iron_veil_staged_scenario_2026_07_02.py
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


CULT = "iron_veil"
REGION = "kuat_sabotaged_yards"
TEMPLATES = ["iron_veil_cell_assault", "iron_veil_power_relay", "iron_veil_veilmaster"]
STAGE_KEYS = ["cells", "power", "veilmaster"]
SPECS = [("iron_veil_cell_assault", 2), ("iron_veil_power_relay", 1),
         ("iron_veil_veilmaster", 2)]


# ════════════════════════════════════════════════════════════════════════════
# Pure-layer: the staged-event descriptors carry the per-stage anomaly mapping
# ════════════════════════════════════════════════════════════════════════════

def test_cult_is_staged():
    """is_staged is true and the cult has exactly 3 stages, a real
    CO.CULT_BY_KEY entry (no phantom cult)."""
    assert CULT in CO.CULT_BY_KEY
    assert SE.is_staged(CULT)
    stages = SE.stages_for(CULT)
    assert stages and len(stages) == 3


def test_each_stage_maps_to_a_real_anomaly_template():
    """Every stage names a template that actually exists in the live anomaly
    registry (no phantom producer)."""
    stages = SE.stages_for(CULT)
    for s in stages:
        key = s.get("anomaly_template")
        assert key, f"{CULT} stage {s['key']} has no anomaly_template"
        assert key in WA.SCENARIO_TEMPLATES, f"{key} not registered"
        # the template self-identifies as belonging to this cult's scenario
        assert WA.SCENARIO_TEMPLATES[key].get("scenario") == CULT
        # orchestrator-spawned only — never tick-rolled into the open world
        assert WA.SCENARIO_TEMPLATES[key].get("regions") == []


def test_stage_kinds_match_anomaly_resolution_modes():
    """Combat/boss stages map to combat anomalies; the middle skill stage maps
    to a resolution:'skill' anomaly (the live skill path, not the inert seam)."""
    assert WA.SCENARIO_TEMPLATES[TEMPLATES[0]]["resolution"] == "combat"
    assert WA.SCENARIO_TEMPLATES[TEMPLATES[1]]["resolution"] == "skill"
    assert WA.SCENARIO_TEMPLATES[TEMPLATES[2]]["resolution"] == "combat"
    # the skill stage's stage descriptor is KIND_SKILL
    by_key = {s["key"]: s for s in SE.stages_for(CULT)}
    assert by_key[STAGE_KEYS[1]]["kind"] == SE.KIND_SKILL
    assert by_key[STAGE_KEYS[0]]["kind"] == SE.KIND_COMBAT
    assert by_key[STAGE_KEYS[2]]["kind"] == SE.KIND_BOSS


def test_skill_stage_names_live_skills_and_alt_skills():
    """The skill template names primary/secondary skills the live resolver
    reads (NOT the inert skill_gate seam), and advertises the social
    alt_skills route named in its long_desc + the staged_event skills[] pool
    (8e5a53e fallback — the 3 sibling staged-cult skill stages all do this)."""
    tmpl = WA.SCENARIO_TEMPLATES[TEMPLATES[1]]
    assert tmpl.get("primary_skill") == "technical"
    assert tmpl.get("secondary_skill") == "computer_programming"
    assert tmpl.get("alt_skills") == ["persuasion", "con", "bargain"]
    # and a fail_reward exists so the one-shot skill path always resolves
    assert "fail_reward" in tmpl
    # every skill the staged_event pool advertises is rollable by the template
    stage = SE.stages_for(CULT)[1]
    rollable = {tmpl["primary_skill"], tmpl["secondary_skill"], *tmpl["alt_skills"]}
    for sk in stage["skills"]:
        assert sk in rollable, f"stage advertises {sk!r} but the template can't roll it"


def test_current_stage_anomaly_spec_walks_with_the_cursor():
    for idx, expect in enumerate(SPECS):
        got = SE.current_stage_anomaly_spec(CULT, {"idx": idx, "progress": 0})
        assert got == expect, f"stage {idx}: {got!r} != {expect!r}"
    # past the last stage → no anomaly to arm
    assert SE.current_stage_anomaly_spec(CULT, {"idx": 3, "progress": 0}) is None


def test_scenario_region_matches():
    assert SE.scenario_region(CULT) == REGION


def test_era_clean_new_scenario_strings():
    """B3/Q1: no Imperial/Rebel/canon strings anywhere in the authored cult
    templates (whole SCENARIO_TEMPLATES blob, including the new cult)."""
    banned = ["imperial", "empire", "rebel", "stormtrooper", "tie ", "x-wing",
              "star destroyer", "vader", "sidious", "dooku", "grievous", "sith"]
    blob = json.dumps(WA.SCENARIO_TEMPLATES).lower()
    for bad in banned:
        assert bad not in blob, f"banned term {bad!r} in scenario templates"


def test_reward_bands_match_ember_court_same_tier_templates():
    """Reward bands copied EXACTLY from the Ember Court's same-tier templates
    (conservative, balance-neutral — per the drop brief)."""
    ember_combat1 = WA.SCENARIO_TEMPLATES["ember_court_forge_assault"]
    ember_skill = WA.SCENARIO_TEMPLATES["ember_court_relay_slice"]
    ember_boss = WA.SCENARIO_TEMPLATES["ember_court_forgemaster"]
    iron_combat1 = WA.SCENARIO_TEMPLATES["iron_veil_cell_assault"]
    iron_skill = WA.SCENARIO_TEMPLATES["iron_veil_power_relay"]
    iron_boss = WA.SCENARIO_TEMPLATES["iron_veil_veilmaster"]

    assert iron_combat1["success_reward"]["credits"] == ember_combat1["success_reward"]["credits"]
    assert iron_combat1["success_reward"]["influence"] == ember_combat1["success_reward"]["influence"]
    assert iron_skill["success_reward"]["credits"] == ember_skill["success_reward"]["credits"]
    assert iron_skill["fail_reward"]["credits"] == ember_skill["fail_reward"]["credits"]
    assert iron_boss["success_reward"]["credits"] == ember_boss["success_reward"]["credits"]
    assert iron_boss["success_reward"]["influence"] == ember_boss["success_reward"]["influence"]


# ════════════════════════════════════════════════════════════════════════════
# Runtime layer: a mini-DB with rooms + NPCs over the real communal table
# (mirrors the Hollow Sun / Ember Court / Ashen Hand test's _SceneDB)
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


def _seed_site(db):
    """Put one landmark room in the cult's region so the site can anchor."""
    db.rooms[900] = {"id": 900, "name": "Scenario Site",
                     "zone_id": 12, "wilderness_region_id": REGION}


def _force_post_cult(db, now_ms):
    """Insert an active uprising for iron_veil (the rotation order would
    otherwise pick another). Mirrors maybe_post's INSERT, then arms stage 1."""
    cult = CO.CULT_BY_KEY[CULT]
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
# spawn_scenario_anomaly — each template anchors, deterministic + live
# ════════════════════════════════════════════════════════════════════════════

def test_spawn_scenario_anomaly_anchors_each_template():
    async def go():
        for template_key, tier in SPECS:
            WA._reset_state_for_tests()
            db = _SceneDB()
            _seed_site(db)
            anom = await WA.spawn_scenario_anomaly(
                db, REGION, template_key, 900, tier=tier)
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

def test_arm_stage_one_site():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        _force_post_cult(db, now_ms=1_000_000)
        active = await COR.get_active(db)
        armed = await COR.arm_stage_site(db, None, active, now_ms=1_000_000)
        assert armed is not None and armed["cult_key"] == CULT
        state = SE.get_stage_state(json.loads(armed["contributions_json"]))
        assert state["site_room_id"] == 900
        assert state.get("anomaly_id") is not None
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom is not None and anom.template_key == TEMPLATES[0]
        WA._reset_state_for_tests()
    _run(go())


def test_arm_is_idempotent_while_the_stage_anomaly_is_live():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        _force_post_cult(db, now_ms=1_000_000)
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

def test_full_scenario_walk_advances_stages_and_wins(monkeypatch):
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
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        _force_post_cult(db, now_ms=1_000_000)
        # arm stage 1
        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        db.chars[42] = {"id": 42, "attributes": "{}"}

        for stage_idx, expect_key in enumerate(TEMPLATES):
            active = await COR.get_active(db)
            assert active is not None, f"objective gone at stage {stage_idx}"
            state = SE.get_stage_state(json.loads(active["contributions_json"]))
            assert state["idx"] == stage_idx
            anom = WA.find_anomaly_globally(state["anomaly_id"])
            assert anom is not None and anom.template_key == expect_key, \
                f"stage {stage_idx}: wrong template"
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
        assert await COR.get_active(db) is None, "did not win on last stage"
        # the EXISTING communal rep payout fired for the contributor
        assert any(cid == 42 and fac == CO.REP_FACTION
                   for (cid, fac, d) in rep_calls), "rep payout missing"
        WA._reset_state_for_tests()
    _run(go())


def test_skill_stage_is_a_live_skill_anomaly():
    """The middle stage resolves through the REAL _resolve_anomaly_skill path —
    a competent character rolls the stage's primary skill and the anomaly
    resolves, paying via the metered anomaly credit faucet (adjust_credits)."""
    async def go():
        primary = WA.SCENARIO_TEMPLATES[TEMPLATES[1]]["primary_skill"]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        anom = await WA.spawn_scenario_anomaly(
            db, REGION, TEMPLATES[1], 900, tier=1)
        assert anom.resolution_mode == "skill"

        char = {"id": 5, "name": "Technician", "room_id": 900,
                "faction_id": "independent", "credits": 0,
                "skills": json.dumps({primary: "6D"}),
                "attributes": json.dumps({"knowledge": "4D",
                                          "perception": "4D"})}
        import random
        result = await WA._resolve_anomaly_skill(
            db, char, anom, REGION, rng=random.Random(1), now=1.0)
        assert result["ok"] and result["mode"] == "skill"
        assert anom.resolved  # one-shot resolve
        assert result["credits"] >= 0
        WA._reset_state_for_tests()
    _run(go())


def test_skill_stage_alt_skill_route_also_resolves():
    """The face route (persuasion, via alt_skills) also resolves the stage —
    proves the advertised social route (8e5a53e) actually works here too."""
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        anom = await WA.spawn_scenario_anomaly(
            db, REGION, TEMPLATES[1], 900, tier=1)

        char = {"id": 6, "name": "Face", "room_id": 900,
                "faction_id": "independent", "credits": 0,
                "skills": json.dumps({"persuasion": "6D"}),
                "attributes": json.dumps({"knowledge": "4D",
                                          "perception": "4D"})}
        import random
        result = await WA._resolve_anomaly_skill(
            db, char, anom, REGION, rng=random.Random(1), now=1.0)
        assert result["ok"] and result["mode"] == "skill"
        assert result["skill_used"] == "persuasion"
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# get_active contract (Situation Board / UX Drop 4) preserved
# ════════════════════════════════════════════════════════════════════════════

def test_get_active_row_still_exposes_situation_board_columns():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        _force_post_cult(db, now_ms=1_000_000)
        await COR.arm_stage_site(db, None, await COR.get_active(db),
                                 now_ms=1_000_000)
        active = await COR.get_active(db)
        for col in ("cult_key", "zone_label", "menace", "state"):
            assert col in active.keys(), f"Situation-Board column {col} missing"
        assert active["state"] == CO.STATE_ACTIVE
        assert active["cult_key"] == CULT
        contribs = json.loads(active["contributions_json"])
        assert "_stage" in contribs
        WA._reset_state_for_tests()
    _run(go())


def test_expired_stage_anomaly_rearms_same_stage_not_advance():
    """A stage whose site anomaly ages out UNcleared must RE-ARM the same stage,
    NOT free-advance the cursor (the expire-vs-clear invariant)."""
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db)
        _force_post_cult(db, now_ms=1_000_000)
        armed = await COR.arm_stage_site(db, None, await COR.get_active(db),
                                         now_ms=1_000_000)
        state0 = SE.get_stage_state(json.loads(armed["contributions_json"]))
        assert state0["idx"] == 0 and state0["anomaly_id"] is not None
        first_id = state0["anomaly_id"]
        WA._reset_state_for_tests()
        assert WA.find_anomaly_globally(first_id) is None
        await COR.on_scenario_progress(db, None, await COR.get_active(db))
        active = await COR.get_active(db)
        assert active is not None, "wrongly ended on an uncleared expire"
        state1 = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state1["idx"] == 0, "stage WRONGLY advanced on expire"
        assert state1.get("anomaly_id") is not None, "stage not re-armed"
        re_anom = WA.find_anomaly_globally(state1["anomaly_id"])
        assert re_anom is not None and re_anom.template_key == TEMPLATES[0]
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# World-YAML anchoring: the region + landmark rooms + edge really exist
# ════════════════════════════════════════════════════════════════════════════

def test_wilderness_region_yaml_loads_and_has_four_landmarks():
    from engine.wilderness_loader import load_wilderness_region
    rep = load_wilderness_region(
        "data/worlds/clone_wars/wilderness/kuat_sabotaged_yards.yaml")
    assert rep.ok, f"region failed to load: {rep.errors}"
    assert rep.region.slug == REGION
    assert len(rep.region.landmarks) == 4
    assert len(rep.region.edges) == 1
    edge = rep.region.edges[0]
    assert edge.room_slug == "kuat_sabotaged_yards_edge"


def test_edge_room_and_warehouse_link_exist_in_kuat_yaml():
    import yaml
    with open("data/worlds/clone_wars/planets/kuat.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    rooms = {r["slug"]: r for r in data["rooms"]}
    assert "kuat_sabotaged_yards_edge" in rooms, "edge room missing from kuat.yaml"
    edge_room = rooms["kuat_sabotaged_yards_edge"]
    assert edge_room["zone"] == "kuat_sabotaged_yards"
    assert edge_room["exits"].get("out") == "kuat_ring_warehouses"
    warehouses = rooms["kuat_ring_warehouses"]
    assert warehouses["exits"].get("maintenance") == "kuat_sabotaged_yards_edge", (
        "Ring Warehouse District has no forward exit into the Sabotaged Yards edge"
    )


def test_zone_registered_in_zones_yaml():
    import yaml
    with open("data/worlds/clone_wars/zones.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert "kuat_sabotaged_yards" in data["zones"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
