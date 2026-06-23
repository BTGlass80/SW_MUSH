"""
engine/staged_event.py — staged communal-event scenarios (2026-06-23).

Resolves EVENT.communal_rework_staged_scenarios (Brian played the Cult of the
Hollow Sun and reported "typing rally / rally strike isn't fun -- it's a counter,
not a scenario; auto-picks your best skill so playstyle is irrelevant").

This reworks the headline cult -- the Cult of the Hollow Sun -- from a flat
menace-grind into a multi-STAGE site scenario, REUSING the existing strike loop
(engine.communal_objective_runtime.record_strike) but routing each stage through
the RIGHT mechanic so playstyle finally matters and matters TOGETHER:

  Stage 1  WAVE COMBAT  -- Break the Shrines (fight the sun-cult zealots)
  Stage 2  SKILL GATE   -- Cut the Water Tithes (slice cisterns / turn the farms)
  Stage 3  BOSS         -- Confront the Hierophant

`rally strike` advances the CURRENT stage via that stage's relevant skills;
clearing all three breaks the cult. The menace meter is retained as the FAILURE
TIMER (the stakes), not the gameplay. Stage progress rides the objective's
contributions_json under the reserved "_stage" key (no schema change), and is
community-shared, so a coordinating group clears faster -- which is exactly the
cooperative play the doc calls for.

PURE: no DB / IO (the runtime owns persistence). Vertical slice: hollow_sun only;
the other cults keep the menace path until this is playtested and generalized.
See docs/design/event_rework_staged_scenarios_2026-06-22.md.
"""
from __future__ import annotations

KIND_COMBAT = "combat"
KIND_SKILL = "skill"
KIND_BOSS = "boss"

# `need` = successful strikes to clear a stage (community-shared). Conservative
# for solo viability while rewarding a group; tune in playtest. `skills` = the
# WEG skill keys that satisfy the stage, so a slicer / face matters alongside the
# soldiers, and the boss rewards the fighters.
HOLLOW_SUN_STAGES = [
    {"key": "shrines", "kind": KIND_COMBAT, "need": 4,
     "name": "Break the Shrines",
     "objective": "Fight through the sun-maddened zealots guarding the desert shrines.",
     "skills": ["brawling", "blaster", "melee_combat", "dodge", "blaster_artillery"]},
    {"key": "tithes", "kind": KIND_SKILL, "need": 3,
     "name": "Cut the Water Tithes",
     "objective": "Slice the shrine cisterns (security / computer programming) or turn "
                  "the moisture farms they prey on (persuasion / con) to cut their tithes.",
     "skills": ["security", "computer_programming", "persuasion", "con", "bargain"]},
    {"key": "hierophant", "kind": KIND_BOSS, "need": 5,
     "name": "Confront the Hierophant",
     "objective": "Bring down the Hollow Sun's Hierophant and scatter the faithful.",
     "skills": ["brawling", "blaster", "melee_combat", "dodge", "lightsaber"]},
]

STAGED_CULTS = {"hollow_sun": HOLLOW_SUN_STAGES}


def is_staged(cult_key: str) -> bool:
    return cult_key in STAGED_CULTS


def stages_for(cult_key: str):
    return STAGED_CULTS.get(cult_key)


def get_stage_state(contribs: dict) -> dict:
    """Read the {idx, progress} stage state out of contributions_json."""
    st = contribs.get("_stage") if isinstance(contribs, dict) else None
    if not isinstance(st, dict):
        return {"idx": 0, "progress": 0}
    return {"idx": int(st.get("idx", 0)), "progress": int(st.get("progress", 0))}


def set_stage_state(contribs: dict, state: dict) -> None:
    contribs["_stage"] = {"idx": int(state["idx"]), "progress": int(state["progress"])}


def current_stage(cult_key: str, state: dict):
    stages = stages_for(cult_key)
    if not stages:
        return None
    idx = state["idx"]
    return stages[idx] if 0 <= idx < len(stages) else None


def advance(cult_key: str, state: dict, success: bool):
    """Apply one strike outcome. Returns (new_state, stage_cleared, all_cleared)."""
    stages = stages_for(cult_key)
    if not stages:
        return state, False, False
    idx, progress = state["idx"], state["progress"]
    if idx >= len(stages):
        return state, False, True
    stage_cleared = all_cleared = False
    if success:
        progress += 1
        if progress >= int(stages[idx]["need"]):
            idx += 1
            progress = 0
            stage_cleared = True
            if idx >= len(stages):
                all_cleared = True
    return {"idx": idx, "progress": progress}, stage_cleared, all_cleared


def _pips_of(dice_str) -> int:
    """'4D+2' -> 14 pips; tolerant of ints / None / garbage."""
    try:
        s = str(dice_str).upper().replace(" ", "")
        if "D" in s:
            d, _, p = s.partition("D")
            dice = int(d) if d else 0
            pips = int(p.replace("+", "")) if p.replace("+", "") else 0
            return dice * 3 + pips
        return int(s)
    except Exception:
        return 0


def stage_pool_pips(cult_key, state, skills: dict, attrs: dict, fallback_pips: int) -> int:
    """Pips for the CURRENT stage's mechanic: the best of the stage's relevant
    skills (so the right playstyle is rewarded), falling back to the generic
    cross-playstyle pool when the player has none of them (so anyone can still
    contribute, just less efficiently)."""
    stage = current_stage(cult_key, state)
    if not stage:
        return fallback_pips
    best = 0
    skills = skills or {}
    for sk in stage.get("skills", []):
        if sk in skills:
            best = max(best, _pips_of(skills[sk]))
    return best if best > 0 else fallback_pips


def stage_tracker_lines(cult_name: str, cult_key: str, state: dict) -> list:
    """Render the staged tracker shown by `rally`."""
    stages = stages_for(cult_key)
    if not stages:
        return []
    idx = state["idx"]
    out = [f"  Operation against {cult_name}:"]
    for i, s in enumerate(stages):
        if i < idx:
            mark, label = "[x]", "cleared"
        elif i == idx:
            mark, label = "[>]", f"{state['progress']}/{s['need']}"
        else:
            mark, label = "[ ]", "locked"
        out.append(f"    {mark} Stage {i + 1} — {s['name']}  ({label})")
    cur = current_stage(cult_key, state)
    if cur:
        verb = {KIND_COMBAT: "fight the next wave",
                KIND_SKILL: "work the objective",
                KIND_BOSS: "engage the leader"}.get(cur["kind"], "act")
        out.append(f"  Now: {cur['objective']}")
        out.append(f"  `rally strike` to {verb}.")
    return out
