# -*- coding: utf-8 -*-
"""tests/test_audit_fix_pvp_dedup_2026_07_03.py — verify-drop follow-up on
the four audit-fix lanes (2026-07-03 aggregate code review).

Pins the MAJOR cross-lane finding + one minor:

  PVP-DEDUP  parser/combat_commands.py::_apply_combat_wear — the wl==0
      victory block (a) had no is_npc filter, so a beaten PC fired the
      NPC-flavored rep ("kill_enemy_faction_npc") + territory.on_npc_kill
      influence AND stacked with lane A's new on_pvp_kill award at death
      (double-counting the flagship contest-PvP influence); and (b) re-
      fired every round while a beaten opponent lingered in
      combat.combatants short of DEAD (INCAP/MW foes are only popped at
      DEAD), letting a multi-round fight farm rep/influence. Fixed with a
      two-tier per-(victor, opponent) latch on the CombatInstance
      (combat._victory_credited, mirroring _chain_credited_ids) + gating
      the rep/on_npc_kill pair to NPC opponents only. The tiers ("beaten"
      >=4 / "killed" >=5) are separate so a Region Anchor first credited
      at INCAPACITATED still resolves its contest when it later dies.

  F12-CLAMP  engine/hunting_rewards.py::on_huntable_kill — `applied` is
      now ALSO ceiling-clamped to the nominal reward, so an unrelated
      concurrent credit landing between the before-read and the
      adjust_credits call can never inflate the daily soft-cap meter.

Methodology matches tests/test_audit_fix_combat_victory_2026_07_03.py:
drive the REAL production functions against the in-process harness DB;
hand-set wound levels (no dice RNG); monkeypatch only downstream side-
observers to prove wiring.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engine.character import Character, WoundLevel
from engine.combat import Combatant, CombatInstance
from parser.combat_commands import _apply_combat_wear


# ── Shared helpers (mirroring the lane-A audit-fix test file) ────────────────

def _standalone_npc_combatant(npc_row, wound_level, *, last_attacker_id=None):
    npc_char = Character.from_db_dict(npc_row)
    npc_char.wound_level = wound_level
    combatant = Combatant(id=npc_char.id, name=npc_char.name,
                          is_npc=True, char=npc_char)
    if last_attacker_id is not None:
        combatant.last_attacker_id = last_attacker_id
    return combatant


def _registered_combatant(combat, char_row_or_char, *, is_npc,
                          wound_level=None):
    """Insert a combatant INTO combat.combatants — mirrors an opponent that
    resolve_round's _cleanup() has NOT popped (anything short of DEAD)."""
    char = (char_row_or_char if isinstance(char_row_or_char, Character)
            else Character.from_db_dict(char_row_or_char))
    if wound_level is not None:
        char.wound_level = wound_level
    c = Combatant(id=char.id, name=char.name, is_npc=is_npc, char=char)
    combat.combatants[c.id] = c
    return c


def _ctx(harness):
    return SimpleNamespace(db=harness.db,
                           session_mgr=harness.server.session_mgr)


def _spies(monkeypatch):
    calls = {"rep": [], "influence": [], "anchor": [], "pvp": []}

    async def _spy_adjust_rep(char, org, db, *a, **kw):
        calls["rep"].append((char["id"], org))

    async def _spy_on_npc_kill(db, char, room_id):
        calls["influence"].append((char["id"], room_id))

    async def _spy_on_npc_killed_in_combat(db, npc_id_, char, room_id, **kw):
        calls["anchor"].append(npc_id_)

    import engine.organizations as orgs_mod
    import engine.territory as territory_mod
    import engine.contest as contest_mod
    monkeypatch.setattr(orgs_mod, "adjust_rep", _spy_adjust_rep)
    monkeypatch.setattr(territory_mod, "on_npc_kill", _spy_on_npc_kill)
    monkeypatch.setattr(contest_mod, "on_npc_killed_in_combat",
                        _spy_on_npc_killed_in_combat)
    return calls


async def _make_npc(h, name):
    npc_id = await h.db.create_npc(
        name, room_id=1, char_sheet_json="{}", ai_config_json="{}")
    return npc_id, await h.db.get_npc(npc_id)


# ── (a) beaten PC must not fire the NPC-flavored rep/influence pair ─────────

class TestBeatenPcRoutesOnlyThroughPvpKill:
    async def test_beaten_pc_fires_neither_npc_rep_nor_npc_influence(
            self, harness, monkeypatch):
        h = harness
        victor = await h.login_as("DedupVictor", room_id=1)
        loser = await h.login_as("DedupLoser", room_id=1)

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(victor.character))
        _registered_combatant(combat, loser.character, is_npc=False,
                              wound_level=WoundLevel.INCAPACITATED)

        calls = _spies(monkeypatch)
        await _apply_combat_wear(combat, _ctx(h), [])

        assert calls["rep"] == [], (
            "a beaten PC must not fire kill_enemy_faction_npc rep — PC "
            "defeats award via on_pvp_kill at death (engine/death.py)")
        assert calls["influence"] == [], (
            "a beaten PC must not fire territory.on_npc_kill — that plus "
            "on_pvp_kill double-counted PvP influence")


# ── (b) once-per-fight latch: no per-round refire ────────────────────────────

class TestVictoryBlockLatchesPerFight:
    async def test_lingering_incap_npc_credits_once_across_rounds(
            self, harness, monkeypatch):
        h = harness
        victor = await h.login_as("LatchVictor", room_id=1)
        _npc_id, npc_row = await _make_npc(h, "LatchFoe")

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(victor.character))
        _registered_combatant(combat, npc_row, is_npc=True,
                              wound_level=WoundLevel.INCAPACITATED)

        calls = _spies(monkeypatch)
        # Three consecutive rounds of a continuing fight (e.g. a second
        # hostile still active) — pre-fix this re-credited every round.
        await _apply_combat_wear(combat, _ctx(h), [])
        await _apply_combat_wear(combat, _ctx(h), [])
        await _apply_combat_wear(combat, _ctx(h), [])

        assert len(calls["rep"]) == 1, (
            f"rep must fire once per beaten opponent per fight, got "
            f"{len(calls['rep'])}")
        assert len(calls["influence"]) == 1, (
            f"on_npc_kill must fire once per beaten opponent per fight, "
            f"got {len(calls['influence'])}")

    async def test_multi_victor_each_gets_rep_once(self, harness,
                                                   monkeypatch):
        h = harness
        v1 = await h.login_as("LatchAlly1", room_id=1)
        v2 = await h.login_as("LatchAlly2", room_id=1)
        _npc_id, npc_row = await _make_npc(h, "LatchFoe2")

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(v1.character))
        combat.add_combatant(Character.from_db_dict(v2.character))
        _registered_combatant(combat, npc_row, is_npc=True,
                              wound_level=WoundLevel.INCAPACITATED)

        calls = _spies(monkeypatch)
        await _apply_combat_wear(combat, _ctx(h), [])
        first_round = sorted(calls["rep"])
        await _apply_combat_wear(combat, _ctx(h), [])

        assert sorted(c for c, _o in first_round) == sorted(
            [v1.character["id"], v2.character["id"]]), (
            "the (victor, opponent) latch must stay PER-VICTOR — both "
            "surviving allies earn victory rep")
        assert sorted(calls["rep"]) == first_round, (
            "no victor may be re-credited on a later round")


# ── tier separation: Anchor INCAP'd earlier must still resolve on death ─────

class TestKilledTierIndependentOfBeatenTier:
    async def test_anchor_incap_then_dead_still_resolves_contest(
            self, harness, monkeypatch):
        h = harness
        victor = await h.login_as("TierVictor", room_id=1)
        npc_id, npc_row = await _make_npc(h, "TierAnchor")

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(victor.character))
        lingering = _registered_combatant(
            combat, npc_row, is_npc=True,
            wound_level=WoundLevel.INCAPACITATED)

        calls = _spies(monkeypatch)
        # Round N: Anchor INCAP'd — "beaten" tier credits (rep), the >=5
        # killed-tier hooks must NOT fire yet.
        await _apply_combat_wear(combat, _ctx(h), [])
        assert calls["anchor"] == []
        assert len(calls["rep"]) == 1

        # Round N+2: the Anchor dies — popped from combatants, arrives via
        # the pre-resolution snapshot. The "killed" tier must still fire
        # even though the "beaten" tier already latched this opponent.
        combat.combatants.pop(lingering.id, None)
        dead = _standalone_npc_combatant(
            npc_row, WoundLevel.DEAD,
            last_attacker_id=victor.character["id"])
        await _apply_combat_wear(combat, _ctx(h), [dead])

        assert calls["anchor"] == [npc_id], (
            "an Anchor first credited at INCAPACITATED must still resolve "
            "its contest when it later dies — the two latch tiers are "
            "independent")
        assert len(calls["rep"]) == 1, (
            "the death round must not re-credit the beaten tier")


# ── F12 ceiling clamp ────────────────────────────────────────────────────────

class TestGrindCapAppliedClamp:
    async def test_out_of_band_credit_cannot_inflate_the_cap_meter(self):
        from engine.hunting_rewards import on_huntable_kill, _reward_for

        reward = _reward_for(0)
        out_of_band = 77  # an unrelated concurrent credit inside the gap

        class _Db:
            def __init__(self):
                self.saved = {}

            async def get_character(self, cid):
                return {"id": cid, "credits": 100}

            async def adjust_credits(self, cid, delta, tag, **kw):
                # balance reflects this award PLUS a foreign credit that
                # landed between the before-read and this call
                return 100 + delta + out_of_band

            async def save_character(self, cid, **kw):
                self.saved.update(kw)
                return True

        killer = {"id": 42, "credits": 100, "attributes": "{}",
                  "name": "ClampHunter"}
        npc_row = {"id": 9000, "name": "Clamp Thug",
                   "ai_config_json": json.dumps({"hostile": True})}

        db = _Db()
        summary = await on_huntable_kill(db, killer, npc_row,
                                         day_stamp="2026-07-03")
        assert summary is not None

        attrs = json.loads(killer["attributes"]) if isinstance(
            killer["attributes"], str) else killer["attributes"]
        booked = attrs["hunting_log"]["daily_credits"]
        assert booked == reward, (
            f"daily cap meter must book the clamped applied amount "
            f"({reward}), not the foreign-credit-inflated diff "
            f"({reward + out_of_band}); booked={booked}")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
