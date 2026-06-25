# Events as Playable Scenarios — Design v1 (vertical slice)

**Status:** RATIFIED FOR VERTICAL SLICE. Composes existing engines; no new
top-level system. Builds on (and supersedes the *gameplay* half of)
`event_rework_staged_scenarios_2026-06-22.md`.
**Origin:** Brian played the **Cult of the Hollow Sun** and reported the
communal event "isn't gameplay — typing `rally` / `rally strike` is a counter,
not a scenario. Events should be: **go to a LOCATION, cooperate, fight waves of
enemies, and use varied skills (slice terminals, etc.).**"
**Author:** Claude Opus 4.8 (main session), grounded against HEAD in worktree
`C:/SW_MUSH_events`.
**Build posture:** EXTEND `engine/staged_event.py` + reuse the *live, tested*
wilderness-anomaly substrate and the communal reward funnels. Additive only.

---

## 1. What exists at HEAD (verified, symbol-level)

The June "staged scenarios" drop already landed a **virtual** staging layer:

- `engine/staged_event.py` — `HOLLOW_SUN_STAGES` (combat → skill → boss),
  `is_staged()`, `advance()`, `stage_pool_pips()`, `stage_tracker_lines()`.
  Stage state rides `communal_objective.contributions_json["_stage"]` (no schema
  change). `engine/communal_objective_runtime.record_strike` routes a staged
  cult's `rally strike` through the *current stage's* relevant skills and the
  menace becomes the failure timer.
- **Gap (Brian's actual complaint is still unsolved):** this is a *staged
  counter*. There is still **no location to travel to, no enemy ever spawns into
  your room, and no terminal to slice.** `rally strike` is the same single roll;
  only its skill-selection and progress display changed. It reads better; it
  does not *play*.

The gameplay Brian wants already exists, live and tested, in
`engine/wilderness_anomalies.py`:

| Primitive Brian asked for | Live seam at HEAD | Status |
| --- | --- | --- |
| Go to a **location** | anomaly anchors to a real landmark `anchor_room_id`; `investigate <id>` is gated to *be at the site* (`_gate_investigate`) | **REUSE** |
| **Waves** of enemies in your room | multi-phase combat (`phases:[...]`): `_resolve_anomaly_combat` spawns phase-0 NPCs into the room; the kill hook (`award_combat_anomaly_reward` → `_advance_to_next_phase`) spawns the next wave on last-NPC-of-phase death | **REUSE** |
| **Slice a terminal** (varied skills) | `resolution:"skill"` anomaly: `_resolve_anomaly_skill` runs `perform_skill_check(char, skill, DC)` and pays a success/partial reward | **REUSE** |
| **Cooperative** | both the multi-phase combat and the room-occupant payout (`_payout_combat_anomaly`) already credit everyone fighting at the site | **REUSE** |
| Reward funnels | anomaly path: `db.adjust_credits(..., "wilderness_anomaly_reward")` + `add_resource` + `adjust_territory_influence`; communal path: `adjust_rep(republic)` + the commemorative `communal_objective_wins` flag | **REUSE — no new faucet/sink** |

So the missing piece is **not** an engine — it is the **orchestration that ties
the existing `hollow_sun` communal objective to a real anchor room and a curated
sequence of live anomaly instances**, one per stage, advancing as each is
cleared. That is exactly the "stage orchestration" the prior doc identified.

### Why we do NOT touch `skill_gate`

`party_skill_challenges_design_v1.md` designs a per-phase `skill_gate` field
*inside* the anomaly engine, but it is **explicitly post-launch, INERT, and
guarded**: `tests/test_t3_23_skill_gate_phase0.py::TestInertness` *fails loudly*
if any `skill_gate` consumer is wired (it asserts `skill_gate` never appears near
`perform_skill_check` in `wilderness_anomalies.py`). Its open design calls
(`solo_penalty` magnitude, failure cost, `alt_skills` breadth) are deferred to
Brian post-launch. **We deliberately do not wire `skill_gate`.** The "slice the
terminal" stage uses the *already-live* `resolution:"skill"` anomaly path
instead, which is a separate, fully-wired, fully-tested seam. This keeps the
slice additive and leaves the inert seam inert.

---

## 2. The staged-scenario pattern

A communal event becomes a **site scenario**: the active `communal_objective`
row gains an anchored **site** (a real room) and a **stage cursor**. Each stage
maps to a **live anomaly instance** spawned at the site:

```
Stage 1  WAVE COMBAT  → a multi-phase combat anomaly (escalating cultist waves)
Stage 2  SKILL GATE   → a resolution:"skill" anomaly (slice the cistern / turn the farm)
Stage 3  BOSS         → a combat anomaly whose final phase is the leader
```

- The **`rally` board becomes the tracker/locator**: who the cult is, *where the
  site is* (room + zone), which stage is live, and the objective verb. The
  gameplay is `investigate`, `attack`, the skill verbs — not `rally strike`.
- Clearing a stage's anomaly **advances the stage cursor** (persisted in
  `contributions_json["_stage"]`) and arms the next stage's anomaly. Clearing
  the final stage **wins** the objective (existing `_finalize` → Republic rep +
  the commemorative flag + holonet broadcast).
- The **menace meter is retained as the failure timer / stakes**: it still rises
  on the tick; if it maxes or the deadline passes, the objective is LOST
  (existing `resolve_state`) and the site disarms. Failure is flavor, never a
  penalty (the standing communal invariant).
- **Cooperative by construction:** everyone at the site fights the same waves
  and the anomaly payout already splits to room occupants / participants.

### Data model (additive, no schema migration)

Extend `engine/staged_event.py`'s stage descriptors with the anomaly each stage
spawns, and extend the per-objective `_stage` blob with the site + live anomaly
id:

```python
# per stage (in HOLLOW_SUN_STAGES), additive keys:
"anomaly_template": "hollow_sun_shrine_assault",   # a live anomaly template key
"anomaly_tier": 2,                                  # 1 = single, 2 = multi-phase wave/boss
# (skill stage carries a resolution:"skill" template instead)

# in contributions_json["_stage"] (additive keys, defaults preserved):
{"idx": 0, "progress": 0,
 "site_room_id": 4123,      # the anchored room (resolved once, on arm)
 "anomaly_id": 57}          # the live anomaly instance for the current stage
```

`get_stage_state()` already returns `{idx, progress}` for back-compat; new keys
are read defensively and default to absent, so every existing caller and test is
unaffected.

### The Situation Board contract (UX Drop 4) — preserved

`ux_engagement_roadmap_2026-06-23.md` (line 238) pins the Situation Board's
digest compiler to `communal_objective_runtime.get_active(db)` reading
`cult_key, zone_label, menace, state`. **The slice keeps `get_active` returning
the same row with those exact columns intact** — scenario state lives in the
existing `contributions_json` blob, not in renamed/removed columns. The contract
is strictly EXTENDED (a richer `_stage` blob the board may later surface), never
broken.

---

## 3. Vertical slice — Cult of the Hollow Sun (this drop)

Concrete first scenario. Region: `tatooine_dune_sea` (the cult's `world_key`),
where combat anomalies already spawn.

**Stage 1 — Break the Shrines (wave combat).** A new multi-phase combat anomaly
template `hollow_sun_shrine_assault` (Tier-2 schema: `phases:[...]`): two waves
of sun-cult zealots (average → veteran), authored to the live `combat_npcs`
spec. Players `investigate` at the site; waves spawn into the room; the kill hook
advances waves and, on final clear, fires the anomaly reward AND signals the
stage cleared.

**Stage 2 — Cut the Water Tithes (skill).** A new `resolution:"skill"` anomaly
template `hollow_sun_cistern_slice`: primary `security`, secondary
`computer_programming` (slicer) — DC on the WEG Moderate–Difficult band — with a
`persuasion`/`con` alt path narratively ("turn the farms"). `_resolve_anomaly_skill`
runs the check and pays the success/partial reward; resolving it clears the stage.

**Stage 3 — Confront the Hierophant (boss).** A combat anomaly
`hollow_sun_hierophant`: a one-or-two-phase fight ending in the Hierophant
(superior tier). Final clear wins the objective.

**Orchestration (the additive engine work):**
- `engine/staged_event.py` gains the per-stage anomaly mapping + pure helpers to
  pick the next stage's template and read/write the site/anomaly-id in `_stage`.
- `engine/communal_objective_runtime.py` gains a small async orchestrator
  (`arm_stage_site` / `on_stage_anomaly_resolved`) that: anchors the site room
  when the staged objective is posted; force-spawns the current stage's anomaly
  via `spawn_anomaly_for_region(..., force=True)`; and, when that anomaly
  resolves, advances the `_stage` cursor and arms the next stage's anomaly (or
  finalizes the win on the last stage). It is best-effort and guarded exactly
  like the rest of the runtime.
- `rally` board lines gain the **site location + the live "go investigate at
  <site>" pointer** (extends `stage_tracker_lines`).
- **`rally strike` is retained but demoted**: for a staged cult it now tells the
  player to go to the site and `investigate` rather than rolling a counter (the
  gameplay moved to the site). Non-staged cults keep `rally strike` unchanged.

**Scope honesty (what this slice builds vs. defers):** the slice lands the full
*data + pure orchestration logic + the live skill/combat templates + the rally
locator*, with a test that walks the scenario end-to-end through the pure stage
machinery and the template registry. Wiring the anomaly-resolution → stage-cursor
callback into the *live kill hook* is the one IO seam; it is implemented as a
single best-effort call from the existing communal runtime so it composes without
modifying `wilderness_anomalies.py`'s guarded internals.

### Reward magnitudes (reused funnels, conservative)

- Stage anomalies pay the **existing anomaly reward bands** (the per-stage
  combat/skill anomaly `success_reward`/`fail_reward`) via the metered
  `wilderness_anomaly_reward` faucet + `add_resource` — same bands as the
  Tier-1/Tier-2 templates they mirror. No new faucet, no new sink.
- The **objective win** still pays the existing communal payoff (Republic rep +
  commemorative flag) via `_finalize` — unchanged.
- Net: a Hollow Sun run now pays *per-stage* anomaly loot (the gameplay loop's
  moment-to-moment reward) on top of the existing prestige win — all through
  funnels that already exist. Balance numbers stay conservative (mirror the
  existing same-tier templates); tune in playtest.

---

## 4. Generalization (post-slice, not this drop)

Once Brian has played the Hollow Sun slice and tuned the feel (pacing,
solo-viability, which skills, reward magnitude), the pattern generalizes by
authoring the same three-stage descriptor + templates for the rest of
`CULT_ROSTER` (Ember Court, Drowned Choir, Iron Veil, Ashen Hand), each themed to
its `world_key` region. No further engine work: `is_staged()` flips a cult into
the scenario path, and the orchestrator is roster-agnostic. The `rally strike`
counter remains only for any not-yet-converted cult, and is retired entirely once
the roster is converted.

---

## 5. Invariants honored

- **Extend, don't add:** no new top-level system, no parallel event engine; the
  slice extends `staged_event.py` + reuses anomaly/communal seams.
- **No phantom producers/consumers:** every new data field (stage→anomaly
  mapping, `_stage` site/anomaly-id) has a real consumer in this drop; the
  authored templates are consumed by the live anomaly resolver.
- **Faucets/sinks land together:** no new credit faucet — reuses the metered
  `wilderness_anomaly_reward` and the rep-only communal payout.
- **Funnel functions:** all credit movement stays on `db.adjust_credits`; all
  out-of-combat dice on `perform_skill_check`; rep on `adjust_rep`; influence on
  `adjust_territory_influence` — all via the existing anomaly/communal paths.
- **Era cleanness (B3):** authored cult NPCs are the invented sun-cult zealots /
  Hierophant — no Imperial/Empire/Rebel/TIE strings, no canon figures.
- **`get_active` contract preserved** for the Situation Board (UX Drop 4):
  same columns, strictly extended blob.
- **Inert seam left inert:** `skill_gate` is not wired (the slice uses the live
  `resolution:"skill"` path instead), so `TestInertness` stays green.

---

## 6. Open design calls for Brian (surface, do not guess)

1. **`rally strike` for a staged cult — demote or remove?** This slice *demotes*
   it (it points you to the site instead of rolling). Brian may prefer it removed
   outright for staged cults. (Default chosen: demote, reversible.)
2. **Solo-viability of the wave stage.** The multi-phase combat assumes 3–5
   coordinating players; the slice authors *conservative* wave sizes so a strong
   solo character can grind it, but Brian's "solo-scalable variant vs.
   small-group-required" call (open in the prior doc) still stands for tuning.
3. **Reward magnitude.** The slice mirrors existing same-tier anomaly bands; if
   Brian wants the headline event to pay *more* than a generic anomaly (it is
   rarer + multi-stage), that is a balance call to make in playtest.
4. **Should the site be a fixed, authored room** (a named cult shrine room) **or
   the anomaly engine's random landmark pick?** The slice uses the existing
   landmark-anchor (zero new world data); a bespoke authored shrine room is a
   nicer-feel upgrade deferred to content authoring.
