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
#
# events_playable_scenarios_design_v1 (2026-06-24): each stage also names the
# LIVE wilderness-anomaly instance it spawns at the site, so the stage is real
# gameplay (go to the location, fight waves / slice the terminal / drop the boss)
# rather than a counter:
#   anomaly_template — a key in engine.wilderness_anomalies (the SCENARIO_TEMPLATES
#                      authored for this cult). Combat/boss stages map to a
#                      multi-phase combat template; skill stages map to a
#                      resolution:"skill" template (NOT the inert skill_gate seam).
#   anomaly_tier     — 1 = single-shot (skill, or one combat group); 2 = multi-
#                      phase wave/boss. Selects the spawn duration band + which
#                      reward path fires. Tier is the anomaly schema tier, not a
#                      difficulty rating.
HOLLOW_SUN_STAGES = [
    {"key": "shrines", "kind": KIND_COMBAT, "need": 4,
     "name": "Break the Shrines",
     "objective": "Fight through the sun-maddened zealots guarding the desert shrines.",
     "skills": ["brawling", "blaster", "melee_combat", "dodge", "blaster_artillery"],
     "anomaly_template": "hollow_sun_shrine_assault", "anomaly_tier": 2},
    {"key": "tithes", "kind": KIND_SKILL, "need": 3,
     "name": "Cut the Water Tithes",
     "objective": "Slice the shrine cisterns (security / computer programming) or turn "
                  "the moisture farms they prey on (persuasion / con) to cut their tithes.",
     "skills": ["security", "computer_programming", "persuasion", "con", "bargain"],
     "anomaly_template": "hollow_sun_cistern_slice", "anomaly_tier": 1},
    {"key": "hierophant", "kind": KIND_BOSS, "need": 5,
     "name": "Confront the Hierophant",
     "objective": "Bring down the Hollow Sun's Hierophant and scatter the faithful.",
     "skills": ["brawling", "blaster", "melee_combat", "dodge", "lightsaber"],
     "anomaly_template": "hollow_sun_hierophant", "anomaly_tier": 2},
]

STAGED_CULTS = {"hollow_sun": HOLLOW_SUN_STAGES}

# The wilderness region each staged cult's scenario site anchors in. Mirrors the
# CultDef.world_key → region used by the anomaly substrate. Vertical slice:
# hollow_sun only.
STAGED_CULT_REGION = {"hollow_sun": "tatooine_dune_sea"}


def scenario_region(cult_key: str) -> "str | None":
    """The wilderness region slug the cult's scenario site anchors in."""
    return STAGED_CULT_REGION.get(cult_key)


def is_staged(cult_key: str) -> bool:
    return cult_key in STAGED_CULTS


def stages_for(cult_key: str):
    return STAGED_CULTS.get(cult_key)


def get_stage_state(contribs: dict) -> dict:
    """Read the stage state out of contributions_json.

    Returns at minimum {idx, progress}; carries the scenario-site keys
    (site_room_id, anomaly_id) when present so the live-scenario orchestrator
    can find the active anomaly. Back-compat: the two original keys are always
    present and an absent/garbled blob defaults to a fresh stage 0.
    """
    st = contribs.get("_stage") if isinstance(contribs, dict) else None
    if not isinstance(st, dict):
        return {"idx": 0, "progress": 0}
    out = {"idx": int(st.get("idx", 0)), "progress": int(st.get("progress", 0))}
    # Optional live-scenario keys (events_playable_scenarios_design_v1). Read
    # defensively; a None means "no site/anomaly armed yet".
    if st.get("site_room_id") is not None:
        try:
            out["site_room_id"] = int(st["site_room_id"])
        except (TypeError, ValueError):
            pass
    if st.get("anomaly_id") is not None:
        try:
            out["anomaly_id"] = int(st["anomaly_id"])
        except (TypeError, ValueError):
            pass
    return out


def set_stage_state(contribs: dict, state: dict) -> None:
    """Persist the stage state back into contributions_json["_stage"].

    Always writes {idx, progress}; carries the scenario-site keys through when
    the caller supplies them (drops them when explicitly None so a freshly armed
    stage starts clean)."""
    blob = {"idx": int(state["idx"]), "progress": int(state["progress"])}
    if state.get("site_room_id") is not None:
        blob["site_room_id"] = int(state["site_room_id"])
    if state.get("anomaly_id") is not None:
        blob["anomaly_id"] = int(state["anomaly_id"])
    contribs["_stage"] = blob


def current_stage(cult_key: str, state: dict):
    stages = stages_for(cult_key)
    if not stages:
        return None
    idx = state["idx"]
    return stages[idx] if 0 <= idx < len(stages) else None


def current_stage_anomaly_spec(cult_key: str, state: dict):
    """The (template_key, tier) the CURRENT stage spawns at the site, or None.

    Used by the live-scenario orchestrator to know which authored anomaly to
    arm for the active stage. None once all stages are cleared, or for a stage
    that declares no anomaly (defensive)."""
    stage = current_stage(cult_key, state)
    if not stage:
        return None
    tmpl = stage.get("anomaly_template")
    if not tmpl:
        return None
    return (tmpl, int(stage.get("anomaly_tier", 1)))


def advance(cult_key: str, state: dict, success: bool):
    """Apply one strike outcome. Returns (new_state, stage_cleared, all_cleared).

    This is the legacy `rally strike` COUNTER advance (used only when no live
    site is armed). The site-scenario path (clearing a stage's anomaly) uses
    `complete_current_stage` instead, which jumps the whole stage in one step."""
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


def complete_current_stage(cult_key: str, state: dict):
    """Mark the CURRENT stage fully cleared (site-scenario path: one anomaly
    clear = one stage). Advances the cursor to the next stage and resets
    progress. Returns (new_state, all_cleared). The site-keys are NOT carried
    here — the orchestrator re-stamps site_room_id / arms the next anomaly_id."""
    stages = stages_for(cult_key)
    if not stages:
        return state, False
    idx = int(state["idx"])
    if idx >= len(stages):
        return {"idx": idx, "progress": 0}, True
    idx += 1
    all_cleared = idx >= len(stages)
    return {"idx": idx, "progress": 0}, all_cleared


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


def stage_tracker_lines(cult_name: str, cult_key: str, state: dict,
                        site_label: "str | None" = None) -> list:
    """Render the staged tracker shown by `rally`.

    When the live scenario site is armed (an anomaly_id is present in `state`),
    `rally` reads as a *locator*: it points the player to the site and tells them
    to `investigate` there — that is where the real gameplay (waves / slice /
    boss) happens. `site_label` is the human room/zone name the runtime resolves;
    when absent the tracker degrades to the stage objective only. Back-compat:
    the signature gains an optional trailing arg, so existing two/three-arg
    callers are unaffected."""
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
        out.append(f"  Now: {cur['objective']}")
        live = state.get("anomaly_id") is not None
        if live:
            where = f" at {site_label}" if site_label else ""
            verb = {KIND_COMBAT: "fight through the waves",
                    KIND_SKILL: "work the objective",
                    KIND_BOSS: "bring down the leader"}.get(cur["kind"], "act")
            out.append(
                f"  The site is active{where}. Travel there and "
                f"`investigate` to {verb}.")
        else:
            verb = {KIND_COMBAT: "fight the next wave",
                    KIND_SKILL: "work the objective",
                    KIND_BOSS: "engage the leader"}.get(cur["kind"], "act")
            out.append(f"  `rally strike` to {verb}.")
    return out
