# -*- coding: utf-8 -*-
"""tests/test_t3_23_party_skill_gate_phase1.py — Party skill challenges,
Phase 1 (T3.23, 2026-06-26). The post-launch engine seam that wires the
``skill_gate`` anomaly-phase field to live skill-check resolution.

Per docs/design/party_skill_challenges_design_v1.md §3/§4/§5/§7:

  * A multi-phase anomaly can interleave COMBAT phases (advance on the
    last hostile's death, existing machinery) with SKILL_GATE phases
    (advance when a present character passes the gated check via
    ``investigate <id>``). The team's specialist steps up.
  * ``alt_skills`` lets a different role substitute for the gate
    (rogue picks the lock the demolitions hand would breach).
  * ``solo_penalty`` raises the difficulty for a lone wolf (no teammate
    present), implementing the soft-require: soloable but punishing, with
    no hard party-size lock (no dead content at low population).
  * A failed gate is retry-allowed after a short cooldown (a time cost,
    not a hard abort — frustration control).
  * The payout reuses the participation-scaled combat reward path; the
    participant set is the UNION of combat killers (``kill_counts``) and
    skill-gate clearers (``contribution_log``), so a slicer / medic /
    face is paid alongside the fighters.

This is the Phase-1 ENGINE seam, behavior-neutral for existing combat-only
anomalies. The first AUTHORED production party challenge (Phase 2) + its
spawn-cadence integration is a follow-up drop — so this drop registers its
challenge templates only in-test (no live TIER3_TEMPLATES auto-spawn).

Sections:
  1. TestSkillGateRouting          — investigate on a skill_gate phase
                                     routes to skill_gate mode + attribution
  2. TestSkillGateClearAdvances    — passing a gate advances + credits
  3. TestSkillGateFailRetry        — fail → retry-allowed + cooldown throttle
  4. TestSoloPenalty               — solo difficulty tax; teammate removes it
  5. TestAltSkillSubstitution      — a char uses a trained alt_skill
  6. TestFinalGatePayout           — final skill gate pays out the clearer
  7. TestMixedChallengeEndToEnd    — skill → combat → skill full walk
  8. TestBehaviorNeutralCombatOnly — combat-only anomalies are unchanged
"""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# Minimal in-memory DB harness (self-contained; mirrors the SYN.8 _MiniDB
# surface the anomaly engine touches, plus a real adjust_credits so the
# payout's credit movement can be asserted).
# ──────────────────────────────────────────────────────────────────────

class _MiniDB:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY, name TEXT, zone_id INTEGER,
                wilderness_region_id TEXT, properties TEXT
            );
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY, name TEXT,
                properties TEXT DEFAULT '{"security":"lawless"}'
            );
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY, name TEXT,
                attributes TEXT DEFAULT '{}', skills TEXT DEFAULT '{}',
                credits INTEGER DEFAULT 0, inventory TEXT DEFAULT '{}',
                faction_id TEXT DEFAULT 'independent', room_id INTEGER
            );
            CREATE TABLE npcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
                room_id INTEGER, species TEXT DEFAULT 'Human',
                description TEXT DEFAULT '', char_sheet_json TEXT DEFAULT '{}',
                ai_config_json TEXT DEFAULT '{}'
            );
        """)
        self._conn.commit()

    async def fetchall(self, sql, params=()):
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    async def fetchone(self, sql, params=()):
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None

    async def get_room(self, room_id):
        rows = await self.fetchall("SELECT * FROM rooms WHERE id = ?", (room_id,))
        return rows[0] if rows else None

    async def get_character(self, char_id):
        rows = await self.fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,))
        return rows[0] if rows else None

    async def save_character(self, char_id, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        self._conn.execute(
            f"UPDATE characters SET {cols} WHERE id = ?",
            list(kwargs.values()) + [char_id])
        self._conn.commit()

    async def adjust_credits(self, char_id, delta, tag):
        row = await self.get_character(char_id)
        new = int((row or {}).get("credits", 0)) + int(delta)
        await self.save_character(char_id, credits=new)
        return new

    async def get_characters_in_room(self, room_id):
        return await self.fetchall(
            "SELECT * FROM characters WHERE room_id = ?", (room_id,))

    async def create_npc(self, name, room_id, species="Human",
                         description="", char_sheet_json="{}",
                         ai_config_json="{}"):
        cur = self._conn.execute(
            "INSERT INTO npcs (name, room_id, species, description, "
            "char_sheet_json, ai_config_json) VALUES (?, ?, ?, ?, ?, ?)",
            (name, room_id, species, description, char_sheet_json,
             ai_config_json))
        self._conn.commit()
        return cur.lastrowid

    async def get_npc(self, npc_id):
        rows = await self.fetchall("SELECT * FROM npcs WHERE id = ?", (npc_id,))
        return rows[0] if rows else None

    async def delete_npc(self, npc_id):
        self._conn.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
        self._conn.commit()
        return True

    async def get_npcs_in_room(self, room_id):
        return await self.fetchall(
            "SELECT * FROM npcs WHERE room_id = ?", (room_id,))

    # ── seed helpers ──
    def seed_zone(self, *, zone_id=1, name="Coruscant", security="lawless"):
        self._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, json.dumps({"security": security})))
        self._conn.commit()

    def seed_room(self, *, room_id, zone_id=1, wilderness_region_id=None,
                  name="Vault"):
        self._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
            "VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self._conn.commit()

    def seed_character(self, *, char_id, name=None, faction_id="independent",
                       room_id=10, credits=0, skills=None):
        self._conn.execute(
            "INSERT INTO characters (id, name, faction_id, room_id, credits, "
            "attributes, skills, inventory) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (char_id, name or f"Char{char_id}", faction_id, room_id, credits,
             "{}", json.dumps(skills or {}), "{}"))
        self._conn.commit()


def _make_char(*, char_id=1, faction_id="independent", room_id=10, skills=None):
    return {
        "id": char_id,
        "name": f"Char{char_id}",
        "faction_id": faction_id,
        "room_id": room_id,
        "credits": 0,
        "attributes": json.dumps({"knowledge": "3D", "perception": "3D"}),
        "skills": json.dumps(skills or {}),
        "inventory": json.dumps({}),
    }


# ── Deterministic stand-in for perform_skill_check ──

class _SCController:
    """Records each (skill, difficulty) call and returns queued outcomes
    (default success). Patched over engine.skill_checks.perform_skill_check
    so the gate logic is exercised independently of dice."""

    def __init__(self, default=True):
        self.calls = []
        self.outcomes = []          # FIFO of bools; empty → self.default
        self.default = default

    def __call__(self, char, skill_name, difficulty, *a, **k):
        from engine.skill_checks import SkillCheckResult
        self.calls.append((skill_name, int(difficulty)))
        ok = self.outcomes.pop(0) if self.outcomes else self.default
        roll = int(difficulty) + (5 if ok else -5)
        return SkillCheckResult(
            roll=roll, difficulty=int(difficulty), success=bool(ok),
            margin=roll - int(difficulty), critical_success=False,
            fumble=False, skill_used=skill_name, pool_str="4D",
        )


# ── Test challenge templates (registered in TIER3_TEMPLATES only in-test) ──

_VAULT_KEY = "_t3_23_test_party_vault"

_VAULT_PHASES = [
    {
        "name": "The Sealed Vault Door",
        "intro": "A reinforced blast door bars the way deeper.",
        "skill_gate": {
            "skill": "security",
            "difficulty": 14,
            "alt_skills": ["demolitions"],
            "solo_penalty": 8,
            "on_clear": "The door grinds open.",
        },
    },
    {
        "name": "The Vault Guardian",
        "intro": "A war droid powers up to defend the prize.",
        "combat_npcs": [{"archetype": "thug", "tier": "average"}],
    },
    {
        "name": "The Keeper's Price",
        "intro": "The keeper will let you leave with the prize — for a price.",
        "skill_gate": {
            "skill": "persuasion",
            "difficulty": 12,
            "alt_skills": ["intimidation", "con"],
            "on_clear": "The keeper waves you through.",
        },
    },
]

_VAULT_TEMPLATE = {
    "tier": 3,
    "regions": [],                     # never auto-spawns (in-test only)
    "resolution": "combat",            # multi-phase engagement model
    "display_name": "The Sundered Vault",
    "short_desc": "A skill-diverse vault delve.",
    "long_desc": "A scavenged-tech vault deep in the underworld.",
    "phases": _VAULT_PHASES,
    "success_reward": {
        "credits": (400, 400),
        "resources": [("metal", 1, 80)],
        "influence": 0,
    },
}


class _ChallengeTestCase(unittest.TestCase):
    """Registers the in-test challenge templates + patches the dice."""

    def setUp(self):
        from engine.wilderness_anomalies import (
            _reset_state_for_tests, TIER3_TEMPLATES,
        )
        import engine.skill_checks as sc_mod
        _reset_state_for_tests()
        self._registered = []
        # Deep-copy the phase list per test so a test mutating a gate dict
        # can't leak into another.
        TIER3_TEMPLATES[_VAULT_KEY] = json.loads(json.dumps(_VAULT_TEMPLATE))
        self._registered.append(_VAULT_KEY)
        # Patch the skill check.
        self.sc = _SCController()
        self._orig_sc = sc_mod.perform_skill_check
        sc_mod.perform_skill_check = self.sc

    def tearDown(self):
        from engine.wilderness_anomalies import (
            TIER3_TEMPLATES, _reset_state_for_tests,
        )
        import engine.skill_checks as sc_mod
        sc_mod.perform_skill_check = self._orig_sc
        for k in self._registered:
            TIER3_TEMPLATES.pop(k, None)
        _reset_state_for_tests()

    def _register_template(self, key, tmpl):
        from engine.wilderness_anomalies import TIER3_TEMPLATES
        TIER3_TEMPLATES[key] = json.loads(json.dumps(tmpl))
        self._registered.append(key)

    def _build(self, *, template_key=_VAULT_KEY, region="coruscant_underworld",
               anchor=10, current_phase=0, seed_chars=(1,), faction="independent"):
        """Stand up a DB + an in-_anomalies challenge anomaly. Seeds the
        given char ids into the anchor room. Returns (db, anomaly)."""
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER3_DURATION_SECS,
        )
        db = _MiniDB()
        db.seed_zone(zone_id=1)
        db.seed_room(room_id=anchor, zone_id=1, wilderness_region_id=region)
        for cid in seed_chars:
            db.seed_character(char_id=cid, room_id=anchor, faction_id=faction)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=region, zone_id=1, template_key=template_key,
            anchor_room_id=anchor, tier=3, expiry=now + TIER3_DURATION_SECS,
            current_phase=current_phase,
        )
        _anomalies[region] = [a]
        return db, a


# ══════════════════════════════════════════════════════════════════════
# 1. TestSkillGateRouting
# ══════════════════════════════════════════════════════════════════════

class TestSkillGateRouting(_ChallengeTestCase):

    def test_investigate_skill_gate_phase_returns_skill_gate_mode(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1)
        out = _run(resolve_anomaly(db, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "skill_gate")

    def test_first_contact_sets_engagement_attribution(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build(faction="hutt_cartel")
        char = _make_char(char_id=1, faction_id="hutt_cartel")
        self.assertIsNone(a.engaged_by)
        _run(resolve_anomaly(db, char, 1))
        self.assertEqual(a.engaged_by, 1)
        self.assertEqual(a.engaged_faction, "hutt_cartel")

    def test_combat_first_challenge_engages_combat_not_skill_gate(self):
        # A challenge whose phase 0 is COMBAT: investigate engages combat
        # (the skill-gate routing only fires when the current phase gates a
        # skill). The combat phase is then driven by attack/kills, never a
        # re-investigate.
        from engine.wilderness_anomalies import resolve_anomaly
        combat_first = {
            "tier": 3, "regions": [], "resolution": "combat",
            "display_name": "Combat-First Delve",
            "phases": [
                {"name": "Ambush", "combat_npcs": [{"archetype": "thug"}]},
                {"name": "Door", "skill_gate": {"skill": "security",
                                                "difficulty": 12}},
            ],
            "success_reward": {"credits": (100, 100), "resources": [],
                               "influence": 0},
        }
        self._register_template("_t3_23_test_combat_first", combat_first)
        db, a = self._build(template_key="_t3_23_test_combat_first")
        char = _make_char(char_id=1)
        out = _run(resolve_anomaly(db, char, 1))
        self.assertEqual(out["mode"], "combat")
        self.assertEqual(self.sc.calls, [])   # no skill check at engagement


# ══════════════════════════════════════════════════════════════════════
# 2. TestSkillGateClearAdvances
# ══════════════════════════════════════════════════════════════════════

class TestSkillGateClearAdvances(_ChallengeTestCase):

    def test_clearing_gate_advances_and_credits_contributor(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        out = _run(resolve_anomaly(db, char, 1))
        self.assertTrue(out["success"])
        self.assertTrue(out["gate_cleared"])
        # Advanced from skill phase 0 to the combat phase 1 (NPCs spawned).
        self.assertEqual(a.current_phase, 1)
        self.assertTrue(a.spawned_npc_ids, "combat phase should have spawned")
        # Contributor credited.
        self.assertEqual(a.contribution_log.get(1), 1)
        self.assertFalse(a.resolved)

    def test_clear_uses_on_clear_message(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        out = _run(resolve_anomaly(db, char, 1))
        self.assertIn("The door grinds open.", out["msg"])


# ══════════════════════════════════════════════════════════════════════
# 3. TestSkillGateFailRetry
# ══════════════════════════════════════════════════════════════════════

class TestSkillGateFailRetry(_ChallengeTestCase):

    def test_fail_is_retry_allowed_not_resolved(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1)
        self.sc.outcomes = [False]
        out = _run(resolve_anomaly(db, char, 1, now=1000.0))
        self.assertTrue(out["ok"])           # ok=True (a valid attempt)
        self.assertFalse(out["success"])     # but the gate was missed
        self.assertFalse(out["gate_cleared"])
        self.assertEqual(a.current_phase, 0)  # not advanced
        self.assertFalse(a.resolved)
        self.assertIn(1, a.skill_gate_retry_at)

    def test_retry_throttled_within_cooldown(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1)
        self.sc.outcomes = [False]
        _run(resolve_anomaly(db, char, 1, now=1000.0))
        # Immediate retry (same now) is throttled — no new skill check fires.
        calls_before = len(self.sc.calls)
        out = _run(resolve_anomaly(db, char, 1, now=1001.0))
        self.assertFalse(out["ok"])
        self.assertIn("try again", out["msg"].lower())
        self.assertEqual(len(self.sc.calls), calls_before,
                         "no skill check should fire while throttled")

    def test_retry_succeeds_after_cooldown(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, SKILL_GATE_RETRY_COOLDOWN_SECS,
        )
        db, a = self._build()
        char = _make_char(char_id=1)
        self.sc.outcomes = [False, True]
        _run(resolve_anomaly(db, char, 1, now=1000.0))
        later = 1000.0 + SKILL_GATE_RETRY_COOLDOWN_SECS + 1
        out = _run(resolve_anomaly(db, char, 1, now=later))
        self.assertTrue(out["gate_cleared"])
        self.assertEqual(a.current_phase, 1)
        # Cooldown cleared on success.
        self.assertNotIn(1, a.skill_gate_retry_at)


# ══════════════════════════════════════════════════════════════════════
# 4. TestSoloPenalty
# ══════════════════════════════════════════════════════════════════════

class TestSoloPenalty(_ChallengeTestCase):

    def test_solo_attempt_adds_penalty_to_difficulty(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build(seed_chars=(1,))   # only the lone wolf in the room
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, char, 1))
        # base 14 + solo_penalty 8 = 22
        self.assertEqual(self.sc.calls[-1], ("security", 22))

    def test_team_attempt_uses_base_difficulty(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build(seed_chars=(1, 2))  # a teammate is present
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, char, 1))
        self.assertEqual(self.sc.calls[-1], ("security", 14))

    def test_gate_without_solo_penalty_never_taxed(self):
        # The final gate (persuasion, difficulty 12) has no solo_penalty.
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build(current_phase=2, seed_chars=(1,))
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, char, 1))
        self.assertEqual(self.sc.calls[-1][1], 12)


# ══════════════════════════════════════════════════════════════════════
# 5. TestAltSkillSubstitution
# ══════════════════════════════════════════════════════════════════════

class TestAltSkillSubstitution(_ChallengeTestCase):

    def test_char_uses_trained_alt_skill(self):
        # The gate is security w/ alt demolitions. A char trained ONLY in
        # demolitions rolls demolitions.
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1, skills={"demolitions": "4D"})
        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, char, 1))
        self.assertEqual(self.sc.calls[-1][0], "demolitions")

    def test_untrained_char_falls_back_to_primary(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1, skills={})   # trained in neither
        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, char, 1))
        self.assertEqual(self.sc.calls[-1][0], "security")

    def test_primary_preferred_when_trained(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build()
        char = _make_char(char_id=1,
                          skills={"security": "5D", "demolitions": "4D"})
        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, char, 1))
        self.assertEqual(self.sc.calls[-1][0], "security")


# ══════════════════════════════════════════════════════════════════════
# 6. TestFinalGatePayout
# ══════════════════════════════════════════════════════════════════════

class TestFinalGatePayout(_ChallengeTestCase):

    def test_clearing_final_gate_pays_out_and_resolves(self):
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build(current_phase=2, seed_chars=(1,))
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        out = _run(resolve_anomaly(db, char, 1))
        self.assertTrue(out["gate_cleared"])
        self.assertTrue(a.resolved)
        self.assertEqual(a.resolved_by, 1)
        # Payout credited the (sole) skill clearer.
        self.assertGreater(out["credits"], 0)
        row = _run(db.get_character(1))
        self.assertGreater(int(row["credits"]), 0)

    def test_skill_only_contributor_is_a_participant(self):
        # A char who only cleared a skill gate (zero kills) is paid.
        from engine.wilderness_anomalies import resolve_anomaly
        db, a = self._build(current_phase=2, seed_chars=(1,))
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        out = _run(resolve_anomaly(db, char, 1))
        payout = out.get("payout") or {}
        self.assertIn(1, payout.get("participants", []))
        self.assertEqual(a.kill_counts, {})   # no combat happened


# ══════════════════════════════════════════════════════════════════════
# 7. TestMixedChallengeEndToEnd
# ══════════════════════════════════════════════════════════════════════

class TestMixedChallengeEndToEnd(_ChallengeTestCase):

    def test_skill_combat_skill_full_walk_unions_participants(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, award_combat_anomaly_reward,
        )
        # char 1 = the skill specialist, char 2 = the fighter; both present.
        db, a = self._build(seed_chars=(1, 2))
        slicer = _make_char(char_id=1)
        fighter = _make_char(char_id=2)

        # Phase 0 (skill gate): slicer clears the door.
        self.sc.outcomes = [True]
        out0 = _run(resolve_anomaly(db, slicer, 1))
        self.assertTrue(out0["gate_cleared"])
        self.assertEqual(a.current_phase, 1)
        self.assertTrue(a.spawned_npc_ids)

        # Phase 1 (combat): fighter kills the guardian → advances into the
        # final skill gate (no payout yet).
        for nid in list(a.spawned_npc_ids):
            _run(award_combat_anomaly_reward(
                db, killer_char_id=2, npc_id=nid, rng=random.Random(0)))
        self.assertEqual(a.current_phase, 2)
        self.assertFalse(a.resolved)
        self.assertEqual(a.kill_counts.get(2), 1)

        # Phase 2 (final skill gate): slicer negotiates the exit → payout.
        self.sc.outcomes = [True]
        out2 = _run(resolve_anomaly(db, slicer, 1))
        self.assertTrue(out2["gate_cleared"])
        self.assertTrue(a.resolved)

        payout = out2.get("payout") or {}
        participants = set(payout.get("participants", []))
        # Both the skill clearer AND the fighter share the reward.
        self.assertEqual(participants, {1, 2})
        # Both got paid credits.
        self.assertGreater(int(_run(db.get_character(1))["credits"]), 0)
        self.assertGreater(int(_run(db.get_character(2))["credits"]), 0)


# ══════════════════════════════════════════════════════════════════════
# 9. TestScaledRewardIncludesSkillClearer
# ══════════════════════════════════════════════════════════════════════

class TestScaledRewardIncludesSkillClearer(_ChallengeTestCase):
    """The participation-scaled T5-mat distribution ranks by combined
    contribution (kills + skill-gate clears), so a slicer/medic/face is
    eligible alongside the fighters (design v1 §5)."""

    REWARD_KEY = "_t3_23_test_party_vault_rewards"

    def _reward_template(self):
        t = json.loads(json.dumps(_VAULT_TEMPLATE))
        t["trophy_per_participant"] = {
            "key": "vault_seal", "name": "Vault Seal",
            "description": "Proof you cracked the Sundered Vault.",
        }
        t["scaled_t5_mat"] = {"key": "rare_alloy", "per_4_participants": 1,
                              "quality": 80}
        return t

    def test_skill_clearer_outranks_fighter_for_t5_mat(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, award_combat_anomaly_reward,
        )
        self._register_template(self.REWARD_KEY, self._reward_template())
        db, a = self._build(template_key=self.REWARD_KEY, seed_chars=(1, 2))
        slicer = _make_char(char_id=1)   # clears 2 gates (contribution 2)
        fighter = _make_char(char_id=2)  # 1 kill (contribution 1)

        self.sc.outcomes = [True]
        _run(resolve_anomaly(db, slicer, 1))                 # gate 0
        for nid in list(a.spawned_npc_ids):                  # combat phase 1
            _run(award_combat_anomaly_reward(
                db, killer_char_id=2, npc_id=nid, rng=random.Random(0)))
        self.sc.outcomes = [True]
        out = _run(resolve_anomaly(db, slicer, 1))           # final gate 2
        payout = out.get("payout") or {}

        # Every participant gets a trophy (participation union).
        self.assertEqual(set(payout.get("participants", [])), {1, 2})
        # n=2 participants → floor(2/4)=0 → 1 consolation piece to the TOP
        # contributor, which is the slicer (2 clears > 1 kill).
        grants = payout.get("scaled_t5_grants", [])
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["char_id"], 1)

    def test_pure_skill_challenge_t5_mat_goes_to_clearer(self):
        # A solo skill-only final clear still drops the consolation piece
        # to the clearer (no kills anywhere).
        from engine.wilderness_anomalies import resolve_anomaly
        self._register_template(self.REWARD_KEY, self._reward_template())
        db, a = self._build(template_key=self.REWARD_KEY,
                            current_phase=2, seed_chars=(1,))
        char = _make_char(char_id=1)
        self.sc.outcomes = [True]
        out = _run(resolve_anomaly(db, char, 1))
        grants = (out.get("payout") or {}).get("scaled_t5_grants", [])
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["char_id"], 1)
        self.assertEqual(a.kill_counts, {})


# ══════════════════════════════════════════════════════════════════════
# 8. TestBehaviorNeutralCombatOnly
# ══════════════════════════════════════════════════════════════════════

class TestBehaviorNeutralCombatOnly(_ChallengeTestCase):
    """A multi-phase anomaly with NO skill_gate is completely unaffected by
    the Phase-1 routing — investigate still engages combat."""

    COMBAT_KEY = "_t3_23_test_combat_only"
    COMBAT_TMPL = {
        "tier": 3, "regions": [], "resolution": "combat",
        "display_name": "Pure Combat Boss",
        "phases": [
            {"name": "P1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "P2", "combat_npcs": [{"archetype": "thug"}]},
        ],
        "success_reward": {"credits": (100, 100), "resources": [], "influence": 0},
    }

    def test_combat_only_investigate_engages_combat(self):
        from engine.wilderness_anomalies import resolve_anomaly
        self._register_template(self.COMBAT_KEY, self.COMBAT_TMPL)
        db, a = self._build(template_key=self.COMBAT_KEY)
        char = _make_char(char_id=1)
        out = _run(resolve_anomaly(db, char, 1))
        self.assertEqual(out["mode"], "combat")
        self.assertTrue(a.spawned_npc_ids)
        # No skill check ever fired for a combat-only anomaly.
        self.assertEqual(self.sc.calls, [])

    def test_combat_only_advances_purely_on_kills(self):
        from engine.wilderness_anomalies import (
            resolve_anomaly, award_combat_anomaly_reward,
        )
        self._register_template(self.COMBAT_KEY, self.COMBAT_TMPL)
        db, a = self._build(template_key=self.COMBAT_KEY)
        char = _make_char(char_id=1)
        _run(resolve_anomaly(db, char, 1))
        for nid in list(a.spawned_npc_ids):
            _run(award_combat_anomaly_reward(
                db, killer_char_id=1, npc_id=nid, rng=random.Random(0)))
        self.assertEqual(a.current_phase, 1)   # advanced to phase 2 (combat)
        self.assertEqual(a.contribution_log, {})  # never touched


if __name__ == "__main__":
    unittest.main()
