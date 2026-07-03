# -*- coding: utf-8 -*-
"""
tests/test_audit_fix_combat_victory_2026_07_03.py — drop
audit-fix-combat-victory (Lane A of the signal-producer audit,
2026-07-03). Five CONFIRMED findings, fixed through their REAL
production seams (no hand-injected on_combat_won/on_pvp_kill/etc.
calls — the whole audit exists because earlier tests hand-injected
those signals and missed the wiring gaps underneath them).

  F1  parser/combat_commands.py::_apply_combat_wear — a straight-to-
      DEAD kill (popped from combat.combatants by resolve_round's
      _cleanup() BEFORE _apply_combat_wear runs) made the `beaten`
      scan see zero opponents, silently skipping faction rep,
      territory influence, and Region-Anchor contest resolution.
      Fixed by unioning the live combat.combatants scan with the
      pre-resolution `_newly_dead` snapshot (the same union already
      used for the DEAD-gated bounty/anomaly/WoW.3a hooks).

  F11 parser/combat_commands.py::_try_auto_resolve / ResolveCommand —
      a chain-tagged foil that died straight-to-DEAD in a NON-FINAL
      round of a multi-hostile fight lost its combat_won chain credit
      forever (the chain-completion block only ever read the
      finishing round's snapshot). Fixed via a per-CombatInstance
      accumulator (_accumulate_chain_defeated_this_round /
      _fire_chain_combat_won) that tallies every round, deduped by
      combatant id, shared by both resolution seams.

  F4  engine/bounty_board.py::notify_target_killed — reassigned
      contract.claimed_by to whoever landed the killing blow, paying
      the killer instead of the claimant (a hijack). Fixed by
      deleting the reassignment; the reward now pays contract.claimed_by
      unconditionally.

  F5  parser/bounty_commands.py::BountyCollectCommand — the manual
      collect gate required wound >= MORTALLY_WOUNDED(5), but combat
      itself ends (and nulls the NPC's room_id) at INCAPACITATED(4),
      permanently stranding the modal single-attacker outcome. Fixed
      (Brian's ruling) by gating on wound >= INCAPACITATED(4), with
      captured_alive = wound < DEAD so both 4 and 5 pay the alive
      bonus.

  F2  engine/death.py::on_pc_death — engine.territory.on_pvp_kill had
      ZERO production callers despite being the flagship contest-PvP
      influence hook. Wired in at the exact point
      _record_pvp_death_and_loot_factor already uses killer_id.

Every test drives the REAL production function under test
(``_apply_combat_wear``, ``_accumulate_chain_defeated_this_round`` /
``_fire_chain_combat_won``, the real ``+bounty/claim`` /
``+bounty/collect`` commands, ``on_pc_death``) against a real
in-process harness DB (``tests/harness.py``). Combat-state INPUTS
(wound levels) are hand-set to avoid dice RNG flake — the same
methodology the audit's own probes used — but every hook under test
fires through its real call site; only downstream side-observers
(rep/territory/contest recorders) are monkeypatched to prove wiring
without needing a fully populated org/contest fixture. F2's own
influence WRITE is additionally proven end-to-end against a real
wilderness room + territory_influence table, not just a recorder.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engine.character import Character, WoundLevel
from engine.combat import Combatant, CombatInstance
from parser.combat_commands import (
    _accumulate_chain_defeated_this_round,
    _apply_combat_wear,
    _combat_finished,
    _fire_chain_combat_won,
)


# ── Shared helpers ───────────────────────────────────────────────────────────

def _standalone_npc_combatant(npc_row, wound_level, *, last_attacker_id=None):
    """Build a Combatant NOT registered in any CombatInstance.combatants
    dict — mirrors an NPC that resolve_round's _cleanup() already popped
    THIS round (the real shape fed to _apply_combat_wear's `pre_npcs` arg
    at both live call sites)."""
    npc_char = Character.from_db_dict(npc_row)
    npc_char.wound_level = wound_level
    combatant = Combatant(id=npc_char.id, name=npc_char.name,
                          is_npc=True, char=npc_char)
    if last_attacker_id is not None:
        combatant.last_attacker_id = last_attacker_id
    return combatant


def _ctx(harness):
    return SimpleNamespace(db=harness.db, session_mgr=harness.server.session_mgr)


# ── F1 — beaten scan must include the pre-resolution DEAD snapshot ─────────

class TestF1BeatenScanIncludesNewlyDead:
    async def test_sole_npc_straight_to_dead_fires_all_three_hooks(self, harness,
                                                                     monkeypatch):
        h = harness
        pc = await h.login_as("F1Hero", room_id=1)
        pc_id = pc.character["id"]

        npc_id = await h.db.create_npc(
            "F1Foe", room_id=1, char_sheet_json="{}", ai_config_json="{}")
        npc_row = await h.db.get_npc(npc_id)

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(pc.character))

        # The NPC already left combat.combatants — mirrors resolve_round's
        # _cleanup() having popped it this round for a straight-to-DEAD kill.
        npc_combatant = _standalone_npc_combatant(
            npc_row, WoundLevel.DEAD, last_attacker_id=pc_id)

        rep_calls = []
        territory_calls = []
        anchor_calls = []

        async def _spy_adjust_rep(char, org, db, *a, **kw):
            rep_calls.append((char["id"], org))

        async def _spy_on_npc_kill(db, char, room_id):
            territory_calls.append((char["id"], room_id))

        async def _spy_on_npc_killed_in_combat(db, npc_id_, char, room_id,
                                                **kw):
            anchor_calls.append(npc_id_)

        import engine.organizations as orgs_mod
        import engine.territory as territory_mod
        import engine.contest as contest_mod
        monkeypatch.setattr(orgs_mod, "adjust_rep", _spy_adjust_rep)
        monkeypatch.setattr(territory_mod, "on_npc_kill", _spy_on_npc_kill)
        monkeypatch.setattr(contest_mod, "on_npc_killed_in_combat",
                            _spy_on_npc_killed_in_combat)

        await _apply_combat_wear(combat, _ctx(h), [npc_combatant])

        assert rep_calls, (
            "faction rep hook must fire for a straight-to-DEAD kill — F1")
        assert territory_calls == [(pc_id, 1)], (
            "territory.on_npc_kill must fire for a straight-to-DEAD kill — F1")
        assert anchor_calls == [npc_id], (
            "contest.on_npc_killed_in_combat must fire for a straight-to-"
            "DEAD kill — F1")

    async def test_dead_anchor_plus_surviving_incap_mook_still_fires_anchor_hook(
            self, harness, monkeypatch):
        h = harness
        pc = await h.login_as("F1Hero2", room_id=1)
        pc_id = pc.character["id"]

        anchor_id = await h.db.create_npc(
            "F1Anchor", room_id=1, char_sheet_json="{}", ai_config_json="{}")
        mook_id = await h.db.create_npc(
            "F1Mook", room_id=1, char_sheet_json="{}", ai_config_json="{}")
        anchor_row = await h.db.get_npc(anchor_id)
        mook_row = await h.db.get_npc(mook_id)

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(pc.character))

        # Anchor: DEAD, already popped from combat.combatants this round.
        anchor_combatant = _standalone_npc_combatant(
            anchor_row, WoundLevel.DEAD, last_attacker_id=pc_id)
        # Mook: INCAPACITATED, still lingering in combat.combatants (only
        # DEAD is popped by _cleanup).
        mook_char = Character.from_db_dict(mook_row)
        mook_char.wound_level = WoundLevel.INCAPACITATED
        mook_combatant = combat.add_combatant(mook_char)
        mook_combatant.is_npc = True

        anchor_calls = []

        async def _spy_on_npc_killed_in_combat(db, npc_id_, char, room_id,
                                                **kw):
            anchor_calls.append(npc_id_)

        import engine.contest as contest_mod
        monkeypatch.setattr(contest_mod, "on_npc_killed_in_combat",
                            _spy_on_npc_killed_in_combat)

        await _apply_combat_wear(
            combat, _ctx(h), [anchor_combatant, mook_combatant])

        assert anchor_calls == [anchor_id], (
            "a DEAD Region Anchor popped from combat.combatants must still "
            "resolve the contest even with a surviving INCAP mook present "
            f"— F1. Got: {anchor_calls}")


# ── F11 — chain-defeat credit must survive across rounds ───────────────────

class TestF11ChainDefeatAccumulatesAcrossRounds:
    async def test_foil_killed_in_non_final_round_still_credited_at_combat_end(
            self, harness, monkeypatch):
        h = harness
        pc = await h.login_as("F11Hero", room_id=1)
        pc_id = pc.character["id"]

        alpha_id = await h.db.create_npc(
            "F11Alpha", room_id=1, char_sheet_json="{}",
            ai_config_json=json.dumps({"chain_enemy_template": "f11_test_tpl"}))
        beta_id = await h.db.create_npc(
            "F11Beta", room_id=1, char_sheet_json="{}", ai_config_json="{}")
        alpha_row = await h.db.get_npc(alpha_id)
        beta_row = await h.db.get_npc(beta_id)

        combat = CombatInstance(1, h.server.skill_reg)
        combat.add_combatant(Character.from_db_dict(pc.character))

        # ── Round 1: Alpha (tagged) dies straight-to-DEAD; Beta (untagged)
        # survives, so combat does NOT finish this round. ──
        alpha_combatant = _standalone_npc_combatant(alpha_row, WoundLevel.DEAD)
        beta_char = Character.from_db_dict(beta_row)
        beta_combatant = combat.add_combatant(beta_char)
        beta_combatant.is_npc = True

        await _accumulate_chain_defeated_this_round(
            combat, h.db, [alpha_combatant, beta_combatant])

        assert dict(combat._chain_defeated_tpl_counts) == {"f11_test_tpl": 1}, (
            "round 1's straight-to-DEAD tagged foil must be tallied "
            "immediately, not only on the finishing round — F11")
        assert not _combat_finished(combat), (
            "Beta + the PC are both still active — combat must not be "
            "finished after round 1")

        # ── Round 2: Beta (untagged) also dies, ending combat. ──
        combat.combatants.pop(beta_combatant.id, None)
        beta_combatant.char.wound_level = WoundLevel.DEAD
        await _accumulate_chain_defeated_this_round(
            combat, h.db, [beta_combatant])

        assert _combat_finished(combat), (
            "only the PC remains active — combat must be finished now")

        won_calls = []

        async def _spy_on_combat_won(db, char, tpl, count):
            won_calls.append((char["id"], tpl, count))
            return False

        import engine.chain_events as chain_events_mod
        monkeypatch.setattr(chain_events_mod, "on_combat_won",
                            _spy_on_combat_won)

        await _fire_chain_combat_won(combat, _ctx(h))

        assert won_calls == [(pc_id, "f11_test_tpl", 1)], (
            "the round-1 kill (Alpha) must still be credited when combat "
            f"finishes on round 2 — audit F11. Got: {won_calls}")

    async def test_lingering_incap_foil_tallied_only_once(self, harness):
        h = harness
        npc_id = await h.db.create_npc(
            "F11Lingerer", room_id=1, char_sheet_json="{}",
            ai_config_json=json.dumps(
                {"chain_enemy_template": "f11_lingerer_tpl"}))
        npc_row = await h.db.get_npc(npc_id)

        combat = CombatInstance(1, h.server.skill_reg)
        combatant = combat.add_combatant(Character.from_db_dict(npc_row))
        combatant.is_npc = True
        combatant.char.wound_level = WoundLevel.INCAPACITATED

        await _accumulate_chain_defeated_this_round(combat, h.db, [combatant])
        assert dict(combat._chain_defeated_tpl_counts) == {
            "f11_lingerer_tpl": 1}

        # Same combatant, still lingering INCAPACITATED (never died, never
        # left combat.combatants) — a second round's accumulation call must
        # NOT tally it again.
        await _accumulate_chain_defeated_this_round(combat, h.db, [combatant])
        assert dict(combat._chain_defeated_tpl_counts) == {
            "f11_lingerer_tpl": 1}, (
            "a lingering INCAPACITATED foil must only be tallied once, on "
            "the first round its can_act gate trips — F11")


# ── F4 — bounty pays the claimant, never the killer ─────────────────────────

class TestF4BountyPaysClaimantNotKiller:
    async def test_non_claimant_finishing_blow_pays_the_claimant(self, harness):
        h = harness
        claimant = await h.login_as("F4Claimant", room_id=1)
        killer = await h.login_as("F4Killer", room_id=1)
        claimant_id = claimant.character["id"]
        killer_id = killer.character["id"]

        from engine.bounty_board import generate_bounty, get_bounty_board

        contract = await generate_bounty(h.db, rooms=[{"id": 1}])
        assert contract is not None
        board = get_bounty_board()
        await board.ensure_loaded(h.db, rooms=[])
        board._contracts[contract.id] = contract

        out = await h.cmd(claimant, f"+bounty/claim {contract.id}")
        assert "traceback" not in out.lower(), out[:400]
        claimed = board.get(contract.id)
        assert claimed is not None and claimed.claimed_by == str(claimant_id)

        npc_row = await h.db.get_npc(contract.target_npc_id)
        combat = CombatInstance(1, h.server.skill_reg)
        npc_combatant = _standalone_npc_combatant(
            npc_row, WoundLevel.DEAD, last_attacker_id=killer_id)

        await _apply_combat_wear(combat, _ctx(h), [npc_combatant])

        claimant_after = await h.get_char(claimant_id)
        killer_after = await h.get_char(killer_id)

        assert claimant_after["credits"] > 0, (
            "the claimant must be paid even though a non-claimant landed "
            "the killing blow — audit F4")
        assert killer_after["credits"] == 0, (
            "the non-claimant killer must NOT be paid — F4 hijack "
            f"regression. killer credits={killer_after['credits']}")
        assert board.get(contract.id) is None, (
            "the contract must be collected (removed from the board)")


# ── F5 — bounty pays on INCAPACITATED defeat (Brian's ruling) ──────────────

class TestF5BountyCollectPaysOnIncapDefeat:
    async def test_incap_wound_collects_with_alive_bonus(self, harness,
                                                          monkeypatch):
        h = harness
        hunter = await h.login_as("F5Hunter", room_id=1)
        hunter_id = hunter.character["id"]

        from engine.bounty_board import (
            BountyBoard, generate_bounty, get_bounty_board,
        )

        contract = await generate_bounty(h.db, rooms=[{"id": 1}])
        board = get_bounty_board()
        await board.ensure_loaded(h.db, rooms=[])
        board._contracts[contract.id] = contract

        await h.cmd(hunter, f"+bounty/claim {contract.id}")

        # Mirror the exact post-combat state the F5 finding's repro proved:
        # round-resolution persists wound_level=INCAPACITATED(4) AND nulls
        # the NPC's room_id (parser/combat_commands.py ~511-515).
        npc_row = await h.db.get_npc(contract.target_npc_id)
        cs = json.loads(npc_row["char_sheet_json"] or "{}")
        cs["wound_level"] = 4
        await h.db.update_npc(contract.target_npc_id,
                              char_sheet_json=json.dumps(cs), room_id=None)

        alive_flags = []
        _orig_total_reward = BountyBoard.total_reward

        def _spy_total_reward(self_, c, alive):
            alive_flags.append(alive)
            return _orig_total_reward(self_, c, alive)

        monkeypatch.setattr(BountyBoard, "total_reward", _spy_total_reward)

        out = await h.cmd(hunter, "+bounty/collect")
        out_lc = out.lower()

        assert "hasn't been defeated" not in out_lc, (
            "wound=4 + room_id=None must not strand the contract — F5 "
            f"regression. Output: {out[:400]!r}")
        assert "bounty collected" in out_lc, out[:400]
        assert alive_flags == [True], (
            "wound=4 (INCAPACITATED) must pay the alive-capture bonus "
            "(captured_alive = wound < DEAD) — F5")
        assert board.get(contract.id) is None

        hunter_after = await h.get_char(hunter_id)
        assert hunter_after["credits"] > 0

    async def test_wounded_twice_still_gated(self, harness):
        h = harness
        hunter = await h.login_as("F5Hunter2", room_id=1)

        from engine.bounty_board import generate_bounty, get_bounty_board

        contract = await generate_bounty(h.db, rooms=[{"id": 1}])
        board = get_bounty_board()
        await board.ensure_loaded(h.db, rooms=[])
        board._contracts[contract.id] = contract

        await h.cmd(hunter, f"+bounty/claim {contract.id}")

        elsewhere_room = await h.db.create_room(
            name="F5 Elsewhere Room", zone_id=1)
        npc_row = await h.db.get_npc(contract.target_npc_id)
        cs = json.loads(npc_row["char_sheet_json"] or "{}")
        cs["wound_level"] = 3  # WOUNDED_TWICE — still able to act, not defeated
        await h.db.update_npc(contract.target_npc_id,
                              char_sheet_json=json.dumps(cs),
                              room_id=elsewhere_room)

        out = await h.cmd(hunter, "+bounty/collect")
        assert "hasn't been defeated" in out.lower(), out[:400]
        assert board.get(contract.id) is not None, (
            "a target below INCAPACITATED must NOT collect — the F5 fix "
            "must not have lowered the gate past 4")

    async def test_auto_collect_kill_hook_stays_dead_gated_at_incap(
            self, harness):
        h = harness
        claimant = await h.login_as("F5AutoClaimant", room_id=1)
        claimant_id = claimant.character["id"]

        from engine.bounty_board import generate_bounty, get_bounty_board

        contract = await generate_bounty(h.db, rooms=[{"id": 1}])
        board = get_bounty_board()
        await board.ensure_loaded(h.db, rooms=[])
        board._contracts[contract.id] = contract
        await h.cmd(claimant, f"+bounty/claim {contract.id}")

        npc_row = await h.db.get_npc(contract.target_npc_id)
        combat = CombatInstance(1, h.server.skill_reg)
        npc_char = Character.from_db_dict(npc_row)
        npc_char.wound_level = WoundLevel.INCAPACITATED
        npc_combatant = combat.add_combatant(npc_char)
        npc_combatant.is_npc = True
        npc_combatant.last_attacker_id = claimant_id

        await _apply_combat_wear(combat, _ctx(h), [])

        # Auto-collect kill hook stays DEAD-gated by design (capture vs.
        # kill distinction) — an INCAPACITATED defeat must NOT auto-collect;
        # the manual +bounty/collect path is the sink for that case.
        fresh = board.get(contract.id)
        assert fresh is not None and fresh.status.value == "claimed", (
            "an INCAPACITATED (not DEAD) NPC must not auto-collect the "
            "bounty via the combat kill hook")
        claimant_after = await h.get_char(claimant_id)
        assert claimant_after["credits"] == 0


# ── F2 — on_pvp_kill wired into the real PC-death seam ─────────────────────

class TestF2PvpKillWiredIntoDeathHook:
    async def test_on_pc_death_calls_on_pvp_kill_with_correct_attribution(
            self, harness, monkeypatch):
        h = harness
        killer = await h.login_as("F2Killer", room_id=1)
        victim = await h.login_as("F2Victim", room_id=1)
        killer_id = killer.character["id"]
        victim_id = victim.character["id"]

        calls = []

        async def _spy_on_pvp_kill(db, winner, loser, room_id):
            calls.append((winner["id"], loser["id"], room_id))

        import engine.territory as territory_mod
        monkeypatch.setattr(territory_mod, "on_pvp_kill", _spy_on_pvp_kill)

        from engine.death import on_pc_death
        await on_pc_death(
            h.db, char_id=victim_id, room_id=1,
            security_level="lawless", killer_id=killer_id,
            session_mgr=h.server.session_mgr,
        )

        assert calls == [(killer_id, victim_id, 1)], (
            "on_pc_death must call engine.territory.on_pvp_kill(winner=killer,"
            f" loser=victim, room_id=...) — audit F2. Got: {calls}")

    async def test_on_pc_death_pvp_kill_writes_real_territory_influence(
            self, harness):
        h = harness
        killer = await h.login_as("F2RealKiller", room_id=1)
        victim = await h.login_as("F2RealVictim", room_id=1)
        killer_id = killer.character["id"]
        victim_id = victim.character["id"]

        await h.db.save_character(killer_id, faction_id="republic")
        await h.db.save_character(victim_id, faction_id="cis")

        room_id = await h.db.create_room(
            name="F2 Wilderness Test Room", zone_id=1)
        await h.db._db.execute(
            "UPDATE rooms SET wilderness_region_id=?, zone_id=? WHERE id=?",
            ("f2_test_region", 1, room_id))
        await h.db._db.commit()

        from engine.territory import get_territory_influence

        before = await get_territory_influence(h.db, "republic", 1)

        from engine.death import on_pc_death
        await on_pc_death(
            h.db, char_id=victim_id, room_id=room_id,
            security_level="lawless", killer_id=killer_id,
            session_mgr=h.server.session_mgr,
        )

        after = await get_territory_influence(h.db, "republic", 1)
        assert after > before, (
            "a PvP kill in a wilderness region must write real territory "
            "influence via on_pvp_kill — audit F2 (previously ZERO "
            f"production callers). before={before} after={after}")
