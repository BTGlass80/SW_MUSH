# -*- coding: utf-8 -*-
"""tests/test_drowned_choir_staged_scenario_2026_07_02.py — the Cult of the
Drowned Choir (Nar Shaddaa) becomes a PLAYABLE site scenario.

The Hollow Sun / Ember Court / Ashen Hand conversions proved the staged-
scenario pattern (tests/test_events_playable_scenarios_2026_06_24.py,
tests/test_events_more_scenarios_2026_06_24.py). This drop extends it,
WITHOUT new orchestration, to the fourth cult, whose world (nar_shaddaa) now
has a small (4-landmark) wilderness region to anchor a site:

  Drowned Choir (Nar Shaddaa / nar_shaddaa_drowned_sublevels)
    Stage 1  wave combat  (drowned_choir_runoff_assault, multi-phase)
    Stage 2  skill gate    (drowned_choir_patron_exposure, resolution:"skill")
    Stage 3  boss          (drowned_choir_choirmaster, multi-phase)

Mirrors tests/test_events_more_scenarios_2026_06_24.py's contracts exactly
(pure-layer descriptor checks + a full scenario walk through the REAL
orchestrator + REAL anomaly registry + REAL runtime SQL, rep stubbed), plus
region-load checks (mirrors tests/test_lane_d_ey_akh_landmarks.py) proving the
new wilderness region is real, reachable map content — not phantom data.

Run: python -m pytest tests/test_drowned_choir_staged_scenario_2026_07_02.py
(asyncio.run, Python 3.14-safe.)
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3

import pytest
import yaml

import engine.communal_objective as CO
import engine.communal_objective_runtime as COR
import engine.staged_event as SE
import engine.wilderness_anomalies as WA
from db.database import MIGRATIONS
from engine.wilderness_loader import load_wilderness_region

CULT = "drowned_choir"
REGION_SLUG = "nar_shaddaa_drowned_sublevels"
TEMPLATES = [
    "drowned_choir_runoff_assault",
    "drowned_choir_patron_exposure",
    "drowned_choir_choirmaster",
]
STAGE_KEYS = ["sublevels", "patrons", "choirmaster"]
SPECS = [
    ("drowned_choir_runoff_assault", 2),
    ("drowned_choir_patron_exposure", 1),
    ("drowned_choir_choirmaster", 2),
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
REGION_YAML = os.path.join(CW, "wilderness", "nar_shaddaa_drowned_sublevels.yaml")
ERA_YAML = os.path.join(CW, "era.yaml")
NARSHADDAA_YAML = os.path.join(CW, "planets", "nar_shaddaa.yaml")
NPC_YAML = os.path.join(CW, "npcs_drop_drowned_choir_scenario.yaml")


def _run(coro):
    return asyncio.run(coro)


def _region():
    rep = load_wilderness_region(REGION_YAML)
    assert rep.ok, f"region failed to load: {rep.errors}"
    assert rep.errors == [], rep.errors
    assert rep.warnings == [], rep.warnings
    return rep.region


# ════════════════════════════════════════════════════════════════════════════
# Pure-layer: the staged-event descriptors carry the per-stage anomaly mapping
# ════════════════════════════════════════════════════════════════════════════

def test_cult_is_staged():
    """is_staged is true and the cult has exactly 3 stages, mapping to a real
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
        assert key, f"stage {s['key']} has no anomaly_template"
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
    by_key = {s["key"]: s for s in SE.stages_for(CULT)}
    assert by_key[STAGE_KEYS[1]]["kind"] == SE.KIND_SKILL
    assert by_key[STAGE_KEYS[0]]["kind"] == SE.KIND_COMBAT
    assert by_key[STAGE_KEYS[2]]["kind"] == SE.KIND_BOSS


def test_skill_stage_names_live_skills():
    """The skill template names primary/secondary skills the live resolver
    reads (NOT the inert skill_gate seam), plus the alt_skills fallback."""
    tmpl = WA.SCENARIO_TEMPLATES[TEMPLATES[1]]
    assert tmpl.get("primary_skill") == "security"
    assert tmpl.get("secondary_skill") == "investigation"
    assert tmpl.get("alt_skills") == ["persuasion", "con", "bargain"]
    # and a fail_reward exists so the one-shot skill path always resolves
    assert "fail_reward" in tmpl


def test_current_stage_anomaly_spec_walks_with_the_cursor():
    for idx, expect in enumerate(SPECS):
        got = SE.current_stage_anomaly_spec(CULT, {"idx": idx, "progress": 0})
        assert got == expect, f"stage {idx}: {got!r} != {expect!r}"
    # past the last stage → no anomaly to arm
    assert SE.current_stage_anomaly_spec(CULT, {"idx": 3, "progress": 0}) is None


def test_scenario_region_matches():
    assert SE.scenario_region(CULT) == REGION_SLUG


def test_reward_bands_match_ashen_hand_exactly():
    """REWARD BANDS: copied EXACTLY from the Ashen Hand's three templates
    (conservative, balance-neutral — no new magnitudes invented)."""
    ashen = WA.SCENARIO_TEMPLATES
    drowned = WA.SCENARIO_TEMPLATES
    assert drowned["drowned_choir_runoff_assault"]["success_reward"] == \
        ashen["ashen_hand_warren_assault"]["success_reward"]
    assert drowned["drowned_choir_patron_exposure"]["success_reward"] == \
        ashen["ashen_hand_informant_turn"]["success_reward"]
    assert drowned["drowned_choir_patron_exposure"]["fail_reward"] == \
        ashen["ashen_hand_informant_turn"]["fail_reward"]
    assert drowned["drowned_choir_choirmaster"]["success_reward"] == \
        ashen["ashen_hand_ashfather"]["success_reward"]


def test_era_clean_new_scenario_strings():
    """B3/Q1: no Imperial/Rebel/canon strings anywhere in the authored
    templates (whole SCENARIO_TEMPLATES blob, including the new cult)."""
    banned = ["imperial", "empire", "rebel", "stormtrooper", "tie ", "x-wing",
              "star destroyer", "vader", "sidious", "dooku", "grievous", "sith",
              "jabba", "kenobi", "skywalker", "palpatine"]
    blob = json.dumps(WA.SCENARIO_TEMPLATES).lower()
    for bad in banned:
        assert bad not in blob, f"banned term {bad!r} in scenario templates"


# ════════════════════════════════════════════════════════════════════════════
# Map layer: the new wilderness region is real, reachable content
# ════════════════════════════════════════════════════════════════════════════

class TestRegionIsRealMapContent:
    def test_region_loads_clean(self):
        reg = _region()
        assert reg.slug == REGION_SLUG
        assert len(reg.landmarks) == 4

    def test_landmark_coordinates_unique_and_in_bounds(self):
        reg = _region()
        coords = [l.coordinates for l in reg.landmarks]
        assert len(coords) == len(set(coords)), f"duplicate coords: {coords}"
        w, h = reg.grid_width, reg.grid_height
        for lm in reg.landmarks:
            x, y = lm.coordinates
            assert 0 <= x < w and 0 <= y < h, f"{lm.id} out of bounds"

    def test_adjacency_resolves_to_defined_landmarks(self):
        reg = _region()
        ids = {l.id for l in reg.landmarks}
        for lm in reg.landmarks:
            for adj in lm.adjacency:
                assert adj in ids, f"{lm.id} adjacency {adj!r} dangling"

    def test_no_phantom_ambient_lines_field(self):
        """`ambient_lines` has no runtime reader at HEAD (per
        test_lane_d_ey_akh_landmarks.py's pinned discipline) — flavor must
        live in `description`, not this dead field."""
        reg = _region()
        for lm in reg.landmarks:
            assert lm.ambient_lines == [], f"{lm.id} must not carry ambient_lines"
            assert len(lm.description) > 200, f"{lm.id} needs a substantive description"
            assert lm.short_desc.strip(), f"{lm.id} needs a short_desc"

    def test_region_registered_in_era_content_refs(self):
        with open(ERA_YAML, encoding="utf-8") as f:
            era = yaml.safe_load(f)
        wilderness_refs = era["content_refs"]["wilderness"]
        assert "wilderness/nar_shaddaa_drowned_sublevels.yaml" in wilderness_refs
        npc_refs = era["content_refs"]["wilderness_npcs"]
        assert "npcs_drop_drowned_choir_scenario.yaml" in npc_refs

    def test_edge_references_an_existing_nar_shaddaa_room_with_a_free_direction(self):
        """The edge's room_slug must resolve to a REAL room in nar_shaddaa.yaml,
        and that room must NOT already declare an exit in direction_from_room
        (otherwise the wilderness-entry fallback in
        parser/builtin_commands.py::_try_wilderness_entry would never fire —
        the normal exit would win first)."""
        reg = _region()
        assert len(reg.edges) == 1
        edge = reg.edges[0]
        assert edge.room_slug == "undercity_depths"

        with open(NARSHADDAA_YAML, encoding="utf-8") as f:
            planet = yaml.safe_load(f)
        room_ids = {r["slug"]: r["id"] for r in planet["rooms"]}
        assert edge.room_slug in room_ids, (
            f"edge room_slug {edge.room_slug!r} does not exist in "
            f"nar_shaddaa.yaml — the site would be unreachable"
        )
        target_id = room_ids[edge.room_slug]

        # Collect every direction already claimed by this room (either as the
        # 'from' side of a global exits: entry, or the 'reverse' side).
        claimed_directions = set()
        for ex in planet.get("exits", []):
            if ex.get("from") == target_id:
                claimed_directions.add(ex["forward"].split()[0].lower())
            if ex.get("to") == target_id:
                claimed_directions.add(ex["reverse"].split()[0].lower())
        assert edge.direction_from_room not in claimed_directions, (
            f"{edge.room_slug} already has a real exit in "
            f"{edge.direction_from_room!r} — the wilderness edge would never "
            f"trigger (parser/builtin_commands.py only falls through to "
            f"_try_wilderness_entry when no normal exit matches)"
        )

    def test_no_edit_to_nar_shaddaa_planet_file(self):
        """The region is reachable purely by REFERENCING the existing room —
        confirms the drop didn't need to touch a shared, high-traffic planet
        file (parallel-session file-disjointness)."""
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD", "--", NARSHADDAA_YAML],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        )
        assert result.stdout.strip() == "", (
            f"nar_shaddaa.yaml was modified: {result.stdout}"
        )


# ════════════════════════════════════════════════════════════════════════════
# NPC layer: the ambient/mob-grind file is real, consumed content
# ════════════════════════════════════════════════════════════════════════════

class TestAmbientNpcFileIsReal:
    def test_npc_rooms_match_real_landmarks(self):
        with open(NPC_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        entries = data["wilderness_npcs"]
        assert len(entries) == 3
        reg = _region()
        landmark_names = {l.name for l in reg.landmarks}
        for e in entries:
            assert e["room"] in landmark_names, (
                f"{e['name']} placed in {e['room']!r}, not a real landmark"
            )

    def test_npcs_are_hostile_with_no_special_markers(self):
        """Satisfies engine.hunting_rewards.is_huntable_mob(): hostile=true and
        none of the special-reward markers (including chain_enemy_template —
        see the design-fork note below)."""
        from engine.hunting_rewards import _SPECIAL_MARKERS
        with open(NPC_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for e in data["wilderness_npcs"]:
            ai = e.get("ai_config", {})
            assert ai.get("hostile") is True
            for marker in _SPECIAL_MARKERS:
                assert marker not in ai, (
                    f"{e['name']} carries special marker {marker!r}"
                )

    def test_no_chain_enemy_template_phantom_field(self):
        """DESIGN FORK (documented, not guessed): the task brief asked for the
        scenario boss to carry `chain_enemy_template`. That field's only real
        consumer is parser/combat_commands.py's combat_won hook, which matches
        it against an ACTIVE CHAIN STEP's `enemy_template`. No chain step in
        this drop's scope names a drowned_choir template, and NONE of the
        three sibling staged-cult bosses (hollow_sun_hierophant /
        ember_court_forgemaster / ashen_hand_ashfather) carry this field
        either — their boss/wave NPCs are procedurally spawned by
        _spawn_combat_npcs, which never reads chain_enemy_template at all.
        Tagging a value here would be a dead tag matching no consumer — so it
        was intentionally omitted from both the wilderness_anomalies.py
        combat_npcs specs and this ambient NPC file."""
        for tmpl_key in ("drowned_choir_runoff_assault", "drowned_choir_choirmaster"):
            tmpl = WA.SCENARIO_TEMPLATES[tmpl_key]
            for phase in tmpl["phases"]:
                for spec in phase["combat_npcs"]:
                    assert "chain_enemy_template" not in spec
        with open(NPC_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for e in data["wilderness_npcs"]:
            assert "chain_enemy_template" not in e.get("ai_config", {})


# ════════════════════════════════════════════════════════════════════════════
# Runtime layer: a mini-DB with rooms + NPCs over the real communal table
# (mirrors the Hollow Sun / Ember Court / Ashen Hand tests' _SceneDB)
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

def test_spawn_scenario_anomaly_anchors_each_template():
    async def go():
        for template_key, tier in SPECS:
            WA._reset_state_for_tests()
            db = _SceneDB()
            _seed_site(db, REGION_SLUG)
            anom = await WA.spawn_scenario_anomaly(
                db, REGION_SLUG, template_key, 900, tier=tier)
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
        first_template = TEMPLATES[0]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
        active = await COR.get_active(db)
        armed = await COR.arm_stage_site(db, None, active, now_ms=1_000_000)
        assert armed is not None and armed["cult_key"] == CULT
        state = SE.get_stage_state(json.loads(armed["contributions_json"]))
        assert state["site_room_id"] == 900
        assert state.get("anomaly_id") is not None
        anom = WA.find_anomaly_globally(state["anomaly_id"])
        assert anom is not None and anom.template_key == first_template
        WA._reset_state_for_tests()
    _run(go())


def test_arm_is_idempotent_while_the_stage_anomaly_is_live():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
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
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
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
        skill_template = TEMPLATES[1]
        primary = WA.SCENARIO_TEMPLATES[skill_template]["primary_skill"]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        anom = await WA.spawn_scenario_anomaly(
            db, REGION_SLUG, skill_template, 900, tier=1)
        assert anom.resolution_mode == "skill"

        char = {"id": 5, "name": "Specialist", "room_id": 900,
                "faction_id": "independent", "credits": 0,
                "skills": json.dumps({primary: "6D"}),
                "attributes": json.dumps({"knowledge": "4D",
                                          "perception": "4D"})}
        import random
        result = await WA._resolve_anomaly_skill(
            db, char, anom, REGION_SLUG, rng=random.Random(1), now=1.0)
        assert result["ok"] and result["mode"] == "skill"
        assert anom.resolved  # one-shot resolve
        assert result["credits"] >= 0
        WA._reset_state_for_tests()
    _run(go())


# ════════════════════════════════════════════════════════════════════════════
# get_active contract (Situation Board / UX Drop 4) preserved
# ════════════════════════════════════════════════════════════════════════════

def test_get_active_row_still_exposes_situation_board_columns():
    async def go():
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
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
        first_template = TEMPLATES[0]
        WA._reset_state_for_tests()
        db = _SceneDB()
        _seed_site(db, REGION_SLUG)
        _force_post_cult(db, CULT, now_ms=1_000_000)
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
        assert active is not None, "wrongly ended on an uncleared expire"
        state1 = SE.get_stage_state(json.loads(active["contributions_json"]))
        assert state1["idx"] == 0, "stage WRONGLY advanced on expire"
        assert state1.get("anomaly_id") is not None, "stage not re-armed"
        re_anom = WA.find_anomaly_globally(state1["anomaly_id"])
        assert re_anom is not None and re_anom.template_key == first_template
        WA._reset_state_for_tests()
    _run(go())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
