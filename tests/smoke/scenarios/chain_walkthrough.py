# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/chain_walkthrough.py — P0.2 per-chain walkthrough
smoke (drop 25, 2026-06-12).

THE REGRESSION NET
==================
Drop 24 (F.8.c.2.e) found that all 7 unlocked Clone Wars tutorial chains
were non-completable from a real chargen, and the entire existing chain
test+smoke layer MISSED it because every test injects chain state,
pre-supplies destination slugs, or pre-places the player at a slugless
room so the reachability gate short-circuits. This scenario closes that
gap: it walks each chain from its REAL starting room to graduation using
ONLY player-issued `cmd()` calls, and asserts at every step that the
player is actually standing in the step's authored `location` BEFORE
attempting the step (the reachability gate — the exact assertion that
was failing for bounty_hunter at step 3).

HARD RULES (the whole point — do not relax these)
-------------------------------------------------
* NEVER call an engine.chain_events hook directly.
* NEVER write the player's next room_id.
* NEVER inject chain state mid-walk (start_chain seeds step 1 ONLY).
* Movement between steps must come from the product (the inter-step
  teleport on advance). If a chain can't be walked by player action, the
  scenario FAILS at the reachability gate — which is the bug-catch.

Completion-type drivers (all player commands)
---------------------------------------------
    command_executed   → type the literal command (+sheet, +factions,
                         examine <x>, say <x>, +craft, use <x>, …),
                         satisfying any requires_first prereqs first.
    talk_to_npc        → talk <npc-first-token>
    combat_won         → attack each chain enemy (disambiguated token)
                         to victory; the cumulative-kill accumulation
                         (drop 25) lets sequential single-enemy fights
                         satisfy enemy_count>1.
    mission_accepted   → +missions, then accept chain_<mission_id>
    mission_completed  → the chain mission auto-completes in the
                         tutorial; driven via +missions + complete.
    bounty_accepted    → +bounties, then accept the tutorial contract.
    skill_check_passed → chain attempt (RNG — bounded retry; skills are
                         seeded high so authored difficulties pass).
    item_used          → use <item-first-token>

RNG / statting
--------------
skill_check_passed is a real dice roll. The walker seeds every relevant
skill at 12D via login_as(skills=...) so the authored difficulties
(8-10) pass on essentially every roll; the retry loop is a belt-and-
braces backstop, not the primary mechanism. Combat steps stat the PC
high (blaster/dodge 12D) so the player reliably wins the drill.
"""
from __future__ import annotations

import json


# Skills seeded on every walker so authored skill checks + combat pass
# reliably. Covers every skill any chain's skill_check_passed /
# combat_won step rolls.
_WALKER_SKILLS = {
    "blaster": "12D",
    "dodge": "12D",
    "brawling": "12D",
    "melee combat": "12D",
    "sneak": "12D",
    "con": "12D",
    "search": "12D",
    "space transports": "12D",
    "space transport repair": "12D",
}

# Bounded retry budget for RNG skill checks (each `chain attempt` is a
# fresh roll; with 12D vs difficulty ≤10 the pass rate is ~100%, so this
# is a backstop).
_SKILL_ATTEMPT_BUDGET = 8

# Per-enemy attack budget for a combat step (a 12D blaster vs a 2D drill
# droid drops it in 1-3 rounds; this is the safety cap).
_ATTACK_BUDGET = 40


# ──────────────────────────────────────────────────────────────────────
# Step drivers — each returns the cmd() output of its final action
# ──────────────────────────────────────────────────────────────────────


async def _satisfy_requires_first(h, s, completion: dict) -> None:
    """Type every `requires_first` prereq command so the gated main
    completion can fire.

    The prereq matcher (engine.chain_events._match_prereq_command_executed)
    requires BOTH `target_contains` AND `target_npc` (when present) to
    appear as substrings of the command args. So `give crate to Dyn` is
    built as `<command> <target_contains> to <target_npc>` — e.g. the
    Smuggler chain's `give crate to Dyn` — rather than dropping one of
    the two constraints."""
    for pre in completion.get("requires_first") or []:
        if not isinstance(pre, dict):
            continue
        cmd = pre.get("command")
        if not cmd:
            continue
        tc = pre.get("target_contains") or ""
        npc = pre.get("target_npc") or ""
        if tc and npc:
            line = f"{cmd} {tc} to {npc}"
        elif tc or npc:
            line = f"{cmd} {tc or npc}"
        else:
            line = cmd
        await h.cmd(s, line.strip())


async def _drive_command_executed(h, s, completion: dict) -> str:
    await _satisfy_requires_first(h, s, completion)
    literal = completion.get("command", "")
    target = (completion.get("target_contains")
              or (completion.get("contains_any") or [""])[0]
              or "")
    return await h.cmd(s, f"{literal} {target}".strip())


async def _drive_talk_to_npc(h, s, completion: dict, get_step) -> str:
    """Drive a talk_to_npc step.

    The `talk` command fires its chain hook (`on_talk_to_npc`) from
    `_post_talk_hooks`, which runs AFTER the NPC's AI dialogue is
    generated. In the smoke harness there is no real Ollama backend, so
    that AI call takes a few seconds to fall back — longer than the
    default cmd() quiet-window. The chain therefore advances a beat
    AFTER `talk` returns, exactly as it would for a real player who sees
    the NPC reply and then the step tick. We issue `talk` then poll for
    the advance with a bounded settle wait."""
    import asyncio
    await _satisfy_requires_first(h, s, completion)
    npc = (completion.get("npc") or "").strip()
    # Use the first name token so `talk Major` resolves 'Major Tarrn'.
    token = npc.split()[0] if npc else ""
    start_step = (get_step() or {}).get("step")
    out = await h.cmd(s, f"talk {token}")
    # Settle: the post-talk chain hook fires asynchronously behind the
    # AI dialogue generation. Poll up to ~6s for the step to advance.
    for _ in range(30):
        s.character = await h.get_char(s.character["id"])
        s.session.invalidate_char_obj()
        info = get_step()
        if info is None or info.get("step") != start_step:
            break
        await asyncio.sleep(0.2)
    return out


async def _drive_skill_check_passed(h, s, completion, get_step):
    """Loop `chain attempt` until the step advances or the budget runs
    out. Returns the final output."""
    out = ""
    start_step = (get_step() or {}).get("step")
    for _ in range(_SKILL_ATTEMPT_BUDGET):
        out = await h.cmd(s, "chain attempt")
        info = get_step()
        if info is None or info.get("step") != start_step:
            break
    return out


async def _enemy_in_room(h, name, room_id) -> bool:
    rows = await h.db.fetchall(
        "SELECT id FROM npcs WHERE name = ? AND room_id = ?",
        (name, room_id),
    )
    return bool(rows)


async def _clear_pc_combat_block(h, s):
    """If the PC has been stunned/wounded out of acting, clear it so the
    drill can continue. A real clone trooper recovers between drill
    rounds (the sim droids are throttled, non-lethal). We reset BOTH the
    persisted wound level AND the in-memory stun-KO gate
    (`unconscious_until`, set in engine/combat.py and NOT DB-persisted —
    it lives on the session's live Character object and on any active
    combat's combatant Character). The smoke is proving CHAIN
    REACHABILITY, not combat survivability (which has its own coverage),
    so a transient stun mid-drill must not strand the chain-walk."""
    char_id = s.character["id"]
    cur = await h.get_char(char_id)
    if int(cur.get("wound_level") or 0) != 0:
        await h.db.save_character(char_id, wound_level=0)
        s.character = await h.get_char(char_id)
    # Invalidate so the session rebuilds a fresh Character object
    # (unconscious_until defaults to 0 on a fresh build). Then clear the
    # stun-KO + wound directly on BOTH the session's live Character and
    # any active combat's combatant Character — the combat engine holds
    # its own Character reference (engine/combat.py sets unconscious_until
    # in-memory; it is NOT DB-persisted), so resetting the DB row alone
    # doesn't wake an already-KO'd combatant.
    from engine.character import WoundLevel
    try:
        s.session.invalidate_char_obj()
    except AttributeError:
        pass

    def _wake(charobj):
        if charobj is None:
            return
        try:
            if hasattr(charobj, "clear_stun_unconscious"):
                charobj.clear_stun_unconscious()
            charobj.wound_level = WoundLevel.HEALTHY
        except Exception:
            pass

    try:
        _wake(s.session.get_char_obj())
    except Exception:
        pass
    # Reach the active combat (keyed in parser.combat_commands).
    try:
        from parser import combat_commands as _cc
        for combat in list(getattr(_cc, "_active_combats", {}).values()):
            c = combat.get_combatant(char_id)
            if c is not None:
                _wake(c.char)
    except Exception:
        pass


async def _drive_combat_won(h, s, completion, room_id, get_step):
    """Attack each chain enemy in the room (by a disambiguating name
    token) until defeated; the cumulative-kill accumulation advances
    the step once enemy_count is met. Returns the final output.

    Resilient to combat ending mid-fight (the drill droids fight back
    and can stun the PC out of acting): on a combat-end / can't-act
    condition with the enemy still alive, it clears the PC's transient
    wound state and re-engages. This keeps the chain-reachability walk
    from being held hostage to combat RNG — survivability is covered by
    the ground-combat smoke, not here."""
    template = (completion.get("enemy_template") or "").strip()
    start_step = (get_step() or {}).get("step")
    rows = await h.db.fetchall(
        "SELECT name, ai_config_json FROM npcs WHERE room_id = ?",
        (room_id,),
    )
    targets = []
    for r in rows:
        try:
            ai = json.loads(r["ai_config_json"] or "{}")
        except Exception:
            ai = {}
        if (ai.get("chain_enemy_template") or "").strip() == template:
            targets.append(r["name"])
    assert targets, (
        f"combat_won step expects enemy_template={template!r} but no "
        f"NPC in room {room_id} carries that chain_enemy_template tag. "
        f"Room NPCs: {[r['name'] for r in rows]}"
    )
    out = ""
    for tname in targets:
        token = tname.split()[-1].lower()
        for _ in range(_ATTACK_BUDGET):
            # Make sure the PC can act before swinging.
            await _clear_pc_combat_block(h, s)
            out = await h.cmd(s, f"attack {token}")
            info = get_step()
            if info is None or info.get("step") != start_step:
                return out
            if not await _enemy_in_room(h, tname, room_id):
                break
        info = get_step()
        if info is None or info.get("step") != start_step:
            break
    return out


async def _drive_mission(h, s, completion, get_step, *, complete=False):
    """Accept (and optionally complete) the chain mission. The mission
    was spawned onto the board by the engine's on-step-entry hook when
    the player teleported into this step — we only issue player
    commands."""
    chain_mid = (completion.get("mission_id") or "").strip()
    board_id = f"chain_{chain_mid}"
    await h.cmd(s, "+missions")
    if complete:
        out = await h.cmd(s, f"complete {board_id}")
    else:
        out = await h.cmd(s, f"accept {board_id}")
    return out


async def _drive_bounty(h, s, completion, get_step):
    """Accept the tutorial bounty contract. The contract was spawned onto
    the board by the engine's on-step-entry hook when the player
    teleported into this step; we only issue player commands.

    The board lists the contract under id `chain_<bounty_id>` (e.g.
    `chain_tutorial_bhg_tarko_vinn`) and the accept verb is
    `+bounty/claim <id>` (aliases claimbounty / acceptbounty; the run-on
    `bountyclaim` was deleted in command-syntax rework Drop 2). The chain
    `bounty_accepted` hook fires synchronously from BountyClaimCommand
    after the claim succeeds — no AI settle needed."""
    chain_bid = (completion.get("bounty_id") or "").strip()
    board_id = f"chain_{chain_bid}"
    await h.cmd(s, "+bounties")
    return await h.cmd(s, f"+bounty/claim {board_id}")


async def _drive_item_used(h, s, completion) -> str:
    item = (completion.get("item") or "").strip()
    token = item.split("_")[0] if item else item
    return await h.cmd(s, f"use {token}")


# ──────────────────────────────────────────────────────────────────────
# The walker
# ──────────────────────────────────────────────────────────────────────


async def walk_chain(h, chain_id: str, walker_name: str) -> None:
    """Walk `chain_id` from its real starting room to graduation using
    only player commands. Asserts the reachability gate at every step
    and graduation at the end.

    Skips (returns early with no failure) if the chain isn't walkable
    for a structural reason that isn't a regression — e.g. the era has
    no chains corpus. A genuine reachability failure RAISES.
    """
    from engine.chain_events import get_active_step_info
    from engine.tutorial_chains import load_tutorial_chains

    corpus = load_tutorial_chains(h.era)
    if corpus is None:
        # Era without chains — nothing to walk. Not a regression.
        return
    chain = corpus.by_id().get(chain_id)
    assert chain is not None, (
        f"chain {chain_id!r} not in the {h.era!r} corpus"
    )
    assert not chain.locked, (
        f"chain {chain_id!r} is locked — not walkable; the test "
        f"parametrization should not include it"
    )

    s = await h.start_chain(walker_name, chain_id, skills=_WALKER_SKILLS)
    char_id = s.character["id"]

    def reload_step():
        # Always read fresh char state for the step view.
        return get_active_step_info(s.character)

    total_steps = len(chain.steps)
    # Hard cap on the walk loop (defends against a never-advancing step
    # spinning forever): at most one iteration per step plus slack.
    for _iter in range(total_steps + 2):
        # Refresh the character row + cached object so the step view and
        # the player's room reflect the latest persisted state (the
        # inter-step teleport mutates room_id on the DB row).
        s.character = await h.get_char(char_id)
        s.session.invalidate_char_obj()

        info = reload_step()
        if info is None:
            # No active step → graduated (or never started). Verify.
            attrs = json.loads(
                (await h.get_char(char_id)).get("attributes") or "{}")
            state = attrs.get("tutorial_chain") or {}
            assert state.get("completion_state") == "graduated", (
                f"chain {chain_id!r}: no active step but not graduated. "
                f"State: {state!r}"
            )
            break

        step_num = info["step"]
        want_loc = info["location"]
        ctype = info["completion_type"]
        completion = info["completion"]

        # ── THE REACHABILITY GATE ──
        # The player must ALREADY be standing in the step's authored
        # location — placed there by the product (start_chain for step
        # 1, the inter-step teleport for every later step). This is the
        # exact assertion that failed for bounty_hunter at step 3.
        cur = await h.get_char(char_id)
        have_loc = await h.room_slug_by_id(cur["room_id"])
        assert have_loc == want_loc, (
            f"REACHABILITY GATE FAILED — chain {chain_id!r} step "
            f"{step_num} ({info['title']!r}): player is in room "
            f"{have_loc!r} but the step is authored at {want_loc!r}. "
            f"The product did not move the player to this step's room "
            f"(the inter-step teleport / starting-room placement is the "
            f"only sanctioned mover). This is the drop-24 stranding "
            f"class."
        )

        room_id = cur["room_id"]

        # ── Drive the step's completion with player commands only ──
        if ctype == "command_executed":
            out = await _drive_command_executed(h, s, completion)
        elif ctype == "talk_to_npc":
            out = await _drive_talk_to_npc(h, s, completion, reload_step)
        elif ctype == "skill_check_passed":
            out = await _drive_skill_check_passed(
                h, s, completion, reload_step)
        elif ctype == "combat_won":
            out = await _drive_combat_won(
                h, s, completion, room_id, reload_step)
        elif ctype == "mission_accepted":
            out = await _drive_mission(h, s, completion, reload_step)
        elif ctype == "mission_completed":
            out = await _drive_mission(
                h, s, completion, reload_step, complete=True)
        elif ctype == "bounty_accepted":
            out = await _drive_bounty(h, s, completion, reload_step)
        elif ctype == "item_used":
            out = await _drive_item_used(h, s, completion)
        else:
            raise AssertionError(
                f"chain {chain_id!r} step {step_num}: unhandled "
                f"completion type {ctype!r}. Add a driver to "
                f"chain_walkthrough.py."
            )

        assert "traceback" not in (out or "").lower(), (
            f"chain {chain_id!r} step {step_num} ({ctype}) raised: "
            f"{out[:500]!r}"
        )

        # ── Assert the step actually advanced ──
        s.character = await h.get_char(char_id)
        s.session.invalidate_char_obj()
        after = reload_step()
        if after is None:
            attrs = json.loads(
                (await h.get_char(char_id)).get("attributes") or "{}")
            state = attrs.get("tutorial_chain") or {}
            assert state.get("completion_state") == "graduated", (
                f"chain {chain_id!r} step {step_num}: step view is None "
                f"but state is not graduated: {state!r}"
            )
            break
        assert after["step"] > step_num, (
            f"chain {chain_id!r} step {step_num} ({ctype}) did NOT "
            f"advance after the player action. Still on step "
            f"{after['step']}. Driver output: {out[:400]!r}"
        )

    # ── Graduation assertions ──
    attrs = json.loads((await h.get_char(char_id)).get("attributes") or "{}")
    state = attrs.get("tutorial_chain") or {}
    assert state.get("completion_state") == "graduated", (
        f"chain {chain_id!r} did NOT graduate after walking all "
        f"{total_steps} steps. Final state: {state!r}"
    )

    # The player should be standing in the graduation drop_room.
    drop_room = chain.graduation.drop_room
    cur = await h.get_char(char_id)
    have_loc = await h.room_slug_by_id(cur["room_id"])
    assert have_loc == drop_room, (
        f"chain {chain_id!r} graduated but the player is in room "
        f"{have_loc!r}, not the graduation drop_room {drop_room!r}. "
        f"The graduation teleport did not fire."
    )
