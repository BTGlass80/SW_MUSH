# -*- coding: utf-8 -*-
"""Live playtest QA cluster (2026-06-20) — new-player-experience pass.

Findings reproduced live in the web client during Brian's first-session
playtest, fixed in this cluster:

  1. COMBAT JSON LEAK — every combat dumped the raw combat_resolution_event
     JSON into the log. Root cause: the engine emits difficulty.breakdown as a
     STRING (combat.py -> defense_display) but the inspector called .map() on it
     as an array -> TypeError -> ws.onmessage's catch fell back to dumping
     evt.data. Client fixes + jsdom tests live in
     tests/spa/test_combat_inspector_string_breakdown.py; the onmessage
     hardening is source-guarded here.

  2. BH "CAPTURE" STRANDING — the Bounty Hunter chain explicitly rewards a STUN
     capture ("attack <t> stun pays more"), but the combat_won chain hook only
     counted wound_level>=4. A stun-KO leaves wound_level at STUNNED, so the
     player who followed the in-game advice was stranded on step 4. Fixed to use
     can_act_now() (combat's own elimination predicate). Covered end-to-end by
     the bounty_hunter walkthrough now that the walker drives the stun path;
     source- and predicate-guarded here.

  3. CRAFTING-TRIAL LEAK — the master-trainer crafting questlines (The Hermit's
     Trial, etc., kind=questline) leaked into the chargen chain picker. Fixed:
     handle_chains filters to kind=="tutorial".
"""
from __future__ import annotations

import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The five master-trainer crafting/end-game trials that must NEVER appear at
# character creation (they are started mid-game via quests/mastery).
_TRIALS = [
    "master_jedi_lightsaber",
    "master_hutt_blaster",
    "master_republic_hyperdrive",
    "master_republic_ion",
    "master_armorer_armor",
]
_ONBOARDING = ["bounty_hunter", "smuggler", "republic_soldier", "shipwright_trader"]


def _src(rel: str) -> str:
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


# ── 3. crafting-trial leak into chargen ──────────────────────────────────────

def test_master_trainer_trials_are_questline_kind():
    from engine.tutorial_chains import load_tutorial_chains

    corpus = load_tutorial_chains()
    assert corpus is not None and corpus.ok, "chains corpus must load"
    by_id = corpus.by_id()
    for cid in _TRIALS:
        assert cid in by_id, f"trial {cid!r} missing from the chain corpus"
        assert by_id[cid].kind == "questline", (
            f"{cid!r} must be kind=questline so the chargen picker excludes it"
        )


def test_onboarding_chains_remain_tutorial_kind():
    from engine.tutorial_chains import load_tutorial_chains

    by_id = load_tutorial_chains().by_id()
    for cid in _ONBOARDING:
        assert by_id[cid].kind == "tutorial", (
            f"{cid!r} is an onboarding chain and must stay kind=tutorial"
        )


def test_chargen_chain_endpoint_filters_non_tutorial_kinds():
    s = _src("server/api.py")
    assert 'getattr(chain, "kind", "tutorial") != "tutorial"' in s, (
        "handle_chains must skip non-tutorial (questline) chains so end-game "
        "crafting trials never appear in the chargen picker"
    )


# ── 2. BH capture stranding on stun-KO ───────────────────────────────────────

def test_combat_won_hook_uses_can_act_now_not_wound_only():
    s = _src("parser/combat_commands.py")
    assert "if c.char.can_act_now():" in s, (
        "the combat_won defeated-detection must use can_act_now() so a STUN-KO "
        "(wound_level still STUNNED) counts as defeated"
    )
    assert "if c.char.wound_level.value < 4:" not in s, (
        "the wound-only defeat check stranded stun-captures and must be gone"
    )


def test_can_act_now_is_false_when_stun_unconscious():
    from engine.character import Character

    c = Character()
    assert c.can_act_now() is True, "a fresh character can act"
    c.unconscious_until = time.time() + 600.0  # stun-KO, wound_level untouched
    assert c.can_act_now() is False, (
        "a stun-unconscious character must read as out-of-the-fight so the "
        "combat_won hook counts the capture"
    )


def test_walkthrough_drives_stun_for_stun_reward_steps():
    # The shared chain walker must drive the RECOMMENDED capture mode (stun)
    # for steps that reward it, so the bounty_hunter walkthrough actually
    # exercises the stun path that was stranded.
    s = _src("tests/smoke/scenarios/chain_walkthrough.py")
    assert 'completion.get("stun_bonus_credits")' in s
    assert 'f"attack {token}{attack_mode}"' in s


# ── 1. combat JSON leak: onmessage robustness ────────────────────────────────

def test_onmessage_does_not_dump_raw_json_on_handler_error():
    s = _src("static/client.html")
    # The dispatch switch is now in its own try whose catch LOGS the handler
    # error rather than dumping evt.data — so a throwing handler can never spill
    # a raw protocol payload into the player's log again.
    assert "WS handler error for type=" in s, (
        "ws.onmessage must log handler errors, not classifyAndAppend(evt.data)"
    )
