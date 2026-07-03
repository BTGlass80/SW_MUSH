# -*- coding: utf-8 -*-
"""
tests/test_staged_questline_archetype_slice1_2026_07_03.py — the
STAGED-QUESTLINE ARCHETYPE first slice (DESIGN_staged_questline_
archetype_2026-07-03.md; Brian's fork stack, 2026-07-03).

Proves "The Undertow Skim" (kamino_undertow_skim, data/worlds/clone_wars/
tutorials/chains.yaml) walks giver -> site_cleared -> report-in ->
graduation through the PRODUCTION dispatcher chain — and, unlike the
5-cult payout bug (test_staged_cult_reward_payout_2026_07_03.py's own
docstring: every per-cult test hand-injected `contribs["cid"]={"points":
50}` and so all 5 clones rode a broken payout to launch), this test
resolves the site's scenario anomaly through the REAL `investigate` /
combat-kill seam:

  * `wilderness_anomalies.resolve_anomaly()` for the initial wave
    engagement AND the mid-phase skill_gate attempt (T3.23's
    `_resolve_skill_gate_phase`, finally exercised by shipped content).
  * `wilderness_anomalies.award_combat_anomaly_reward()` for every wave
    and boss NPC kill — the SAME hook `parser/combat_commands.py` calls
    on a real kill.

No field is hand-set on the anomaly object anywhere in this file.

Sections:
  1. TestArcShape           — the chain/template/NPC/venue are real
  2. TestFullWalkthrough    — the real-seam end-to-end walk + reward-
                               tier/no-double-pay assertions
  3. TestSuppressFlagWiring — spawn_scenario_anomaly/WildernessAnomaly
                               carry + honor suppress_payout directly
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CHAIN_ID = "kamino_undertow_skim"
GIVER_NPC = "Quartermaster Rensa Dahl"
TEMPLATE_KEY = "kamino_undertow_purge"
GIVER_ROOM_SLUG = "kamino_pylon_access"
SITE_ROOM_SLUG = "understructure_cistern"
REGION_SLUG = "kamino_flooded_understructure"
ACHIEVEMENT_KEY = "undertow_skim_cleared"
RELIC_ITEM_KEY = "skimmers_sealed_strongbox"
STAGED_CREDITS = 900
STAGED_REP_TOTAL = 20

CHAINS_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
               / "tutorials" / "chains.yaml")


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _load_chain_block() -> dict:
    data = yaml.safe_load(open(CHAINS_PATH, encoding="utf-8"))
    for c in data["chains"]:
        if c.get("chain_id") == CHAIN_ID:
            return c
    raise AssertionError(f"{CHAIN_ID} not found in chains.yaml")


# ══════════════════════════════════════════════════════════════════════
# Real-DB harness — a fresh in-memory schema (not the full world), with
# the two rooms the arc actually touches hand-seeded to real slugs /
# wilderness_region_id / zone_id, so every production DB call the engine
# makes (get_room_by_slug, create_npc, get_characters_in_room,
# adjust_credits, add_to_inventory, ...) runs against REAL behavior.
# ══════════════════════════════════════════════════════════════════════

async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _seed_account(db):
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts "
        "(username, password_hash, email) "
        "VALUES ('test', 'hash', 't@e.com')"
    )
    await db._db.commit()


async def _seed_world(db):
    """Seed the giver room + the site room (with wilderness_region_id)
    the arc's chain steps reference, plus the `independent` organization
    row `adjust_rep` requires to route the graduation's non-member rep
    award (production seeds this from data/worlds/clone_wars/
    organizations.yaml at boot; a fresh in-memory test DB does not).
    Returns (giver_room_id, site_room_id, region_slug)."""
    await db.create_organization("independent", "Independent",
                                 org_type="neutral")
    giver_zone_id = await db.create_zone(
        "kamino_ocean_platform", properties=json.dumps(
            {"security": "secured"}))
    site_zone_id = await db.create_zone(
        REGION_SLUG, properties=json.dumps({"security": "contested"}))

    giver_room_id = await db.create_room(
        "Kamino - Pylon Access Corridor", zone_id=giver_zone_id,
        properties=json.dumps({"slug": GIVER_ROOM_SLUG}),
    )
    site_room_id = await db.create_room(
        "The Mooring Shelf", zone_id=site_zone_id,
        properties=json.dumps({"slug": SITE_ROOM_SLUG}),
    )
    # wilderness_region_id is a dedicated column (not inside `properties`)
    # — create_room doesn't expose it, so stamp it directly, mirroring
    # engine/wilderness_writer.py's own INSERT shape.
    await db._db.execute(
        "UPDATE rooms SET wilderness_region_id = ? WHERE id = ?",
        (REGION_SLUG, site_room_id),
    )
    await db._db.commit()
    return giver_room_id, site_room_id, REGION_SLUG


async def _seed_char(db, room_id: int) -> int:
    char_id = await db.create_character(
        account_id=1,
        fields={
            "name": "Undertow Runner",
            "species": "Human",
            "attributes": json.dumps({"chargen_complete": True}),
            "skills": json.dumps({}),
            "room_id": room_id,
        },
    )
    return char_id


def _force_skill_success(monkeypatch):
    """Deterministic stand-in for perform_skill_check (mirrors
    tests/test_t3_23_party_skill_gate_phase1.py's _SCController) — the
    skill_gate phase's dice outcome is not what THIS test proves; the
    chain-advance + no-double-pay wiring is."""
    import engine.skill_checks as sc_mod
    from engine.skill_checks import SkillCheckResult

    def _fake_check(char, skill_name, difficulty, *a, **k):
        roll = int(difficulty) + 5
        return SkillCheckResult(
            roll=roll, difficulty=int(difficulty), success=True,
            margin=roll - int(difficulty), critical_success=False,
            fumble=False, skill_used=skill_name, pool_str="4D",
        )

    monkeypatch.setattr(sc_mod, "perform_skill_check", _fake_check)


class _RealCorpusBase(unittest.TestCase):
    def setUp(self):
        from engine.era_state import set_active_config
        import engine.chain_events as ce
        import engine.wilderness_anomalies as WA
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        ce._reset_corpus_cache()
        WA._reset_state_for_tests()

    def tearDown(self):
        from engine.era_state import clear_active_config
        import engine.chain_events as ce
        import engine.wilderness_anomalies as WA
        clear_active_config()
        ce._reset_corpus_cache()
        WA._reset_state_for_tests()


# ══════════════════════════════════════════════════════════════════════
# 1. TestArcShape — the authored content is real
# ══════════════════════════════════════════════════════════════════════

class TestArcShape(_RealCorpusBase):

    def test_chain_is_a_questline_with_site_cleared_middle_step(self):
        chain = _load_chain_block()
        self.assertEqual(chain.get("kind"), "questline")
        steps = chain["steps"]
        self.assertEqual(len(steps), 3)
        types_seen = [s["completion"]["type"] for s in steps]
        self.assertEqual(
            types_seen, ["talk_to_npc", "site_cleared", "talk_to_npc"])
        self.assertEqual(
            steps[1]["completion"]["scenario_template"], TEMPLATE_KEY)
        self.assertEqual(steps[1]["completion"]["tier"], 2)

    def test_scenario_template_is_wave_skill_gate_boss(self):
        from engine.wilderness_anomalies import SCENARIO_TEMPLATES
        tmpl = SCENARIO_TEMPLATES[TEMPLATE_KEY]
        self.assertEqual(tmpl["resolution"], "combat")
        phases = tmpl["phases"]
        self.assertEqual(len(phases), 3)
        self.assertIn("combat_npcs", phases[0])
        self.assertNotIn("skill_gate", phases[0])
        self.assertIn("skill_gate", phases[1])
        self.assertNotIn("combat_npcs", phases[1])
        self.assertIn("combat_npcs", phases[2])
        self.assertNotIn("skill_gate", phases[2])

    def test_site_cleared_is_a_registered_completion_type(self):
        from engine.tutorial_chains import ALLOWED_COMPLETION_TYPES
        self.assertIn("site_cleared", ALLOWED_COMPLETION_TYPES)

    def test_giver_npc_is_placed_at_the_giver_room(self):
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "npcs_drop_staged_questline_archetype_slice1.yaml")
        data = yaml.safe_load(open(path, encoding="utf-8"))
        names = {n["name"]: n["room"] for n in data["npcs"]}
        self.assertIn(GIVER_NPC, names)
        self.assertEqual(names[GIVER_NPC],
                         "Kamino - Pylon Access Corridor")

    def test_venue_room_is_a_real_wilderness_landmark(self):
        wpath = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "wilderness" / "kamino_flooded_understructure.yaml")
        data = yaml.safe_load(open(wpath, encoding="utf-8"))
        self.assertEqual(data["region"]["slug"], REGION_SLUG)
        ids = {lm["id"] for lm in data["landmarks"]}
        self.assertIn(SITE_ROOM_SLUG, ids)

    def test_achievement_registered_and_linked(self):
        import engine.achievements as A
        A.load_achievements()
        ach = A.get_achievement(ACHIEVEMENT_KEY)
        self.assertIsNotNone(ach, "achievement not registered")
        trig = ach.get("trigger") or {}
        self.assertEqual(trig.get("event"), "chain_graduation")
        self.assertEqual(trig.get("chain_id"), CHAIN_ID)


# ══════════════════════════════════════════════════════════════════════
# 2. TestFullWalkthrough — the real-seam end-to-end walk
# ══════════════════════════════════════════════════════════════════════

class TestFullWalkthrough(_RealCorpusBase):

    def test_giver_to_site_to_graduation_real_seam_no_double_pay(self):
        from engine.chain_events import (
            start_questline, on_talk_to_npc,
        )
        from engine.tutorial_chains import (
            is_chain_complete, _QUESTLINE_KEY,
        )
        from engine.wilderness_anomalies import (
            get_anomalies_for_region, resolve_anomaly,
            award_combat_anomaly_reward,
        )
        import pytest
        monkeypatch = pytest.MonkeyPatch()
        self.addCleanup(monkeypatch.undo)
        _force_skill_success(monkeypatch)

        async def go():
            db = await _fresh_db()
            await _seed_account(db)
            giver_room_id, site_room_id, region = await _seed_world(db)
            char_id = await _seed_char(db, giver_room_id)
            char = await db.get_character(char_id)
            self.assertIsNotNone(char)
            starting_credits = int(char.get("credits", 0) or 0)

            # ── Step 1: accept + talk to the giver ──────────────────
            ok, msg = await start_questline(db, char, CHAIN_ID)
            self.assertTrue(ok, msg)
            qstate = json.loads(char["attributes"]).get(_QUESTLINE_KEY)
            self.assertEqual(qstate["step"], 1)

            advanced = await on_talk_to_npc(db, char, GIVER_NPC)
            self.assertTrue(advanced, "step 1 talk_to_npc did not advance")
            qstate = json.loads(char["attributes"]).get(_QUESTLINE_KEY)
            self.assertEqual(qstate["step"], 2)

            # The arm-on-entry hook (chain_missions.maybe_arm_site_for_
            # step) must have armed a REAL scenario anomaly at the site
            # room, with the anomaly id stamped onto the chain-step state.
            anomalies = get_anomalies_for_region(region)
            self.assertEqual(len(anomalies), 1,
                             "site_cleared step entry did not arm exactly "
                             "one scenario anomaly")
            anomaly = anomalies[0]
            self.assertEqual(anomaly.template_key, TEMPLATE_KEY)
            self.assertEqual(anomaly.anchor_room_id, site_room_id)
            self.assertTrue(anomaly.suppress_payout,
                            "chain-armed anomaly must suppress its own "
                            "payout (Fork 3A)")
            self.assertEqual(qstate.get("step_scenario_anomaly_id"),
                             anomaly.id)
            # Inter-step teleport moved the player to the site room.
            self.assertEqual(int(char["room_id"]), site_room_id)

            # ── Phase 0 (wave): engage via the REAL investigate seam ──
            out = await resolve_anomaly(db, char, anomaly.id)
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "combat")
            self.assertTrue(anomaly.spawned_npc_ids)
            wave_ids = list(anomaly.spawned_npc_ids)
            self.assertEqual(len(wave_ids), 3)

            # Kill every wave NPC via the REAL kill hook. No field is
            # hand-set on `anomaly` anywhere in this test.
            for nid in wave_ids:
                payout = await award_combat_anomaly_reward(
                    db, killer_char_id=char_id, npc_id=nid,
                )
                self.assertIsNone(
                    payout, "payout must not fire before the FINAL "
                    "phase clears")
            self.assertEqual(anomaly.current_phase, 1)
            self.assertFalse(anomaly.resolved)

            # ── Phase 1 (skill_gate): the REAL investigate seam routes
            # to _resolve_skill_gate_phase (T3.23, finally exercised). ──
            out = await resolve_anomaly(db, char, anomaly.id)
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "skill_gate")
            self.assertTrue(out["gate_cleared"])
            self.assertEqual(anomaly.current_phase, 2)
            self.assertFalse(anomaly.resolved)
            boss_ids = list(anomaly.spawned_npc_ids)
            self.assertEqual(len(boss_ids), 1)

            # ── Phase 2 (boss): the real kill hook fires the FINAL
            # payout — suppressed (Fork 3A) — and the clear-hook dispatch
            # (Fork 4B fan-out; solo here, so just the resolver). ──
            payout = await award_combat_anomaly_reward(
                db, killer_char_id=char_id, npc_id=boss_ids[0],
            )
            self.assertIsNotNone(payout)
            self.assertTrue(anomaly.resolved)
            self.assertEqual(anomaly.resolved_by, char_id)
            # THE double-pay proof: the anomaly's own faucet paid ZERO —
            # no wilderness_anomaly_reward credit_log rows for this char.
            self.assertEqual(payout["credits"], 0)
            rows = await db.fetchall(
                "SELECT * FROM credit_log WHERE char_id = ? "
                "AND source = 'wilderness_anomaly_reward'",
                (char_id,),
            )
            self.assertEqual(
                len(rows), 0,
                "the chain-armed anomaly paid its OWN faucet — Fork 3A "
                "suppression did not hold (double-pay)")

            # The clear-hook advanced the QUESTLINE step 2 -> 3. My
            # local `char` object is stale here (the payout dispatched
            # to a FRESH DB-fetched participant dict, same as every
            # other T2/T3 payout's non-killer credit award) — refetch.
            char = await db.get_character(char_id)
            qstate = json.loads(char["attributes"]).get(_QUESTLINE_KEY)
            self.assertEqual(
                qstate["step"], 3,
                "on_site_cleared did not advance the chain past the "
                "site_cleared step")
            # Re-teleported back to the giver room for step 3.
            self.assertEqual(int(char["room_id"]), giver_room_id)

            # ── Step 3: report in -> graduation ──────────────────────
            advanced = await on_talk_to_npc(db, char, GIVER_NPC)
            self.assertTrue(advanced, "step 3 talk_to_npc did not advance")
            char = await db.get_character(char_id)
            self.assertTrue(
                is_chain_complete(json.loads(char["attributes"]),
                                  _QUESTLINE_KEY))

            # ── The RICHER staged capstone paid EXACTLY ONCE ─────────
            final_credits = int(char.get("credits", 0) or 0)
            self.assertEqual(final_credits - starting_credits,
                             STAGED_CREDITS)
            chain_reward_rows = await db.fetchall(
                "SELECT * FROM credit_log WHERE char_id = ? "
                "AND source = 'chain_reward'",
                (char_id,),
            )
            self.assertEqual(len(chain_reward_rows), 1)
            self.assertEqual(chain_reward_rows[0]["delta"],
                             STAGED_CREDITS)
            # Still zero wilderness_anomaly_reward rows after the whole
            # walk — the suppression held through graduation.
            rows = await db.fetchall(
                "SELECT * FROM credit_log WHERE char_id = ? "
                "AND source = 'wilderness_anomaly_reward'",
                (char_id,),
            )
            self.assertEqual(len(rows), 0)

            # ── Relic + rep ───────────────────────────────────────────
            from engine.items import coerce_inventory
            inv = coerce_inventory(char["inventory"])
            item_keys = [it.get("key") for it in inv["items"]]
            self.assertIn(RELIC_ITEM_KEY, item_keys)

            attrs = json.loads(char["attributes"])
            faction_rep = attrs.get("faction_rep") or {}
            self.assertEqual(faction_rep.get("independent"),
                             STAGED_REP_TOTAL)

        _run(go())


# ══════════════════════════════════════════════════════════════════════
# 3. TestSuppressFlagWiring — the engine-level plumbing in isolation
# ══════════════════════════════════════════════════════════════════════

class TestSuppressFlagWiring(unittest.TestCase):

    def setUp(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()

    def tearDown(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()

    def test_spawn_scenario_anomaly_carries_suppress_flag(self):
        from engine.wilderness_anomalies import spawn_scenario_anomaly

        class _MiniDB:
            async def get_room(self, room_id):
                return {"id": room_id, "zone_id": 1}

        anomaly = _run(spawn_scenario_anomaly(
            _MiniDB(), "some_region", TEMPLATE_KEY, 42,
            tier=2, suppress_payout=True,
        ))
        self.assertIsNotNone(anomaly)
        self.assertTrue(anomaly.suppress_payout)

    def test_default_suppress_payout_is_false(self):
        from engine.wilderness_anomalies import WildernessAnomaly
        a = WildernessAnomaly(
            id=1, region_slug="r", zone_id=1,
            template_key=TEMPLATE_KEY, anchor_room_id=1,
        )
        self.assertFalse(a.suppress_payout)


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
