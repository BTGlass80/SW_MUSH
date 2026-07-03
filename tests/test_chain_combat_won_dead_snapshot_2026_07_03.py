# -*- coding: utf-8 -*-
"""F1 (Fable review 2026-07-02): chain `combat_won` credit lost to a
straight-to-DEAD finishing blow — all 40 chains.

`resolve_round()`'s `_cleanup()` pops any combatant that reached DEAD from
`combat.combatants` the same round it falls. The F.8.c.2.b chain-completion
block used to collect defeated foils by iterating the LIVE `combat.combatants`
dict, so a foil finished with a DEAD blow was invisible → the `on_combat_won`
hook never fired → chain credit silently lost (a hard soft-lock on a single-foil
questline step). The fix feeds the PRE-resolution snapshot (`_pre_npcs`) to a
pure helper, matching the three sibling reward consumers in the same function.
This is the DEAD-side twin of the 2026-07-02 anomaly-defeat fix.
"""
import asyncio
import json
import pathlib

from parser.combat_commands import _collect_defeated_chain_templates


def _run(coro):
    return asyncio.run(coro)


class _StubChar:
    def __init__(self, can_act):
        self._can_act = can_act

    def can_act_now(self):
        # Real Character.can_act_now() is False for Incapacitated+ AND a stun-KO
        # (unconscious_until set while wound stays STUNNED). The helper only ever
        # calls this predicate, so the boolean stub is faithful.
        return self._can_act


class _StubCombatant:
    def __init__(self, cid, is_npc=True, can_act=False, has_char=True):
        self.id = cid
        self.is_npc = is_npc
        self.char = _StubChar(can_act) if has_char else None


class _StubDB:
    def __init__(self, rows):
        self._rows = rows  # {npc_id: row-dict}; missing id = ghost (no row)

    async def get_npc(self, npc_id):
        return self._rows.get(npc_id)


def _row(tpl):
    return {"ai_config_json": json.dumps({"chain_enemy_template": tpl})}


# ── THE regression + counting ────────────────────────────────────────────────
def test_dead_foil_in_snapshot_is_counted():
    db = _StubDB({1: _row("thug_A")})
    snap = [_StubCombatant(1, can_act=False)]  # DEAD → popped from live dict
    assert _run(_collect_defeated_chain_templates(db, snap)) == {"thug_A": 1}


def test_both_droids_one_combat_counts_two():
    db = _StubDB({1: _row("republic_soldier"), 2: _row("republic_soldier")})
    snap = [_StubCombatant(1, can_act=False), _StubCombatant(2, can_act=False)]
    assert _run(_collect_defeated_chain_templates(db, snap)) == {"republic_soldier": 2}


def test_still_active_excluded():
    db = _StubDB({1: _row("thug")})
    snap = [_StubCombatant(1, can_act=True)]  # HEALTHY / still fighting
    assert _run(_collect_defeated_chain_templates(db, snap)) == {}


# ── robustness (must never raise) ────────────────────────────────────────────
def test_untagged_npc_excluded():
    db = _StubDB({1: {"ai_config_json": "{}"}})
    assert _run(_collect_defeated_chain_templates(db, [_StubCombatant(1, can_act=False)])) == {}


def test_ghost_id_skipped_beside_a_good_one():
    db = _StubDB({1: _row("thug")})  # id 2 has no DB row
    snap = [_StubCombatant(1, can_act=False), _StubCombatant(2, can_act=False)]
    assert _run(_collect_defeated_chain_templates(db, snap)) == {"thug": 1}


def test_non_npc_and_none_char_skipped():
    db = _StubDB({1: _row("thug"), 2: _row("thug")})
    snap = [_StubCombatant(1, is_npc=False, can_act=False),
            _StubCombatant(2, has_char=False, can_act=False)]
    assert _run(_collect_defeated_chain_templates(db, snap)) == {}


def test_empty_and_none_snapshot():
    db = _StubDB({})
    assert _run(_collect_defeated_chain_templates(db, [])) == {}
    assert _run(_collect_defeated_chain_templates(db, None)) == {}


def test_malformed_ai_config_tolerated():
    db = _StubDB({1: {"ai_config_json": "{not valid json"}})
    assert _run(_collect_defeated_chain_templates(db, [_StubCombatant(1, can_act=False)])) == {}


def test_dict_ai_config_supported():
    db = _StubDB({1: {"ai_config_json": {"chain_enemy_template": "thug"}}})
    assert _run(_collect_defeated_chain_templates(db, [_StubCombatant(1, can_act=False)])) == {"thug": 1}


# ── wiring canary — a live-dict revert fails deterministically ────────────────
def test_call_site_feeds_the_pre_resolution_snapshot():
    src = pathlib.Path("parser/combat_commands.py").read_text(encoding="utf-8")
    i = src.index("F.8.c.2.b")
    block = src[i:i + 2500]
    assert "_fire_chain_combat_won(" in block, \
        "chain combat_won block no longer calls the accumulated-defeat firer"
    # the old inline live-dict scan must be gone
    assert "_defeated_templates" not in block, \
        "the old inline live-dict collection is back — the DEAD bug can recur"


# ── wiring canary (F11, 2026-07-03) — per-round accumulation outside the
# _combat_finished gate, so a straight-to-DEAD kill in a non-final round of
# a multi-hostile fight is still tallied ────────────────────────────────────
def test_accumulate_call_is_outside_the_combat_finished_gate():
    src = pathlib.Path("parser/combat_commands.py").read_text(encoding="utf-8")
    fn_start = src.index("async def _try_auto_resolve(")
    fn_end = src.index("\nasync def ", fn_start + 1)
    fn_body = src[fn_start:fn_end]
    accum_i = fn_body.index("_accumulate_chain_defeated_this_round(")
    gate_i = fn_body.index("if _combat_finished(combat):")
    assert accum_i < gate_i, (
        "chain-defeat accumulation must run EVERY round, before the "
        "_combat_finished gate — otherwise a foil killed in a non-final "
        "round is dropped again (audit F11)"
    )


def test_resolve_command_shares_the_same_accumulation_and_firing():
    src = pathlib.Path("parser/combat_commands.py").read_text(encoding="utf-8")
    fn_start = src.index("class ResolveCommand(BaseCommand):")
    fn_end = src.index("\nclass ", fn_start + 1)
    fn_body = src[fn_start:fn_end]
    assert "_accumulate_chain_defeated_this_round(" in fn_body, \
        "admin force-resolve must also accumulate chain defeats per round"
    assert "_fire_chain_combat_won(" in fn_body, \
        "admin force-resolve must also fire chain combat_won credit"
