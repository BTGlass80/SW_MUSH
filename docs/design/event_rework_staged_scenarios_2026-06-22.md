# Event rework — communal events as staged playable scenarios (2026-06-22)

**Origin:** Brian played the **Cult of the Hollow Sun** event live and reported it
"wasn't fun — typing 'rally' and 'rally strike' isn't gameplay." His standard for
what events should be: **go to a location, work together, face waves of enemies /
locations to traverse, use varied skills (slice terminals, etc.).** This applies to
the **whole communal-event / rally system**, not just the one cult.

## Current state (verified at HEAD)

The cult uprisings run on the **communal-objective** system:
- `engine/communal_objective.py` — `CULT_ROSTER` (a small roster; Hollow Sun = `hollow_sun`
  is one; **all mechanically identical**). A `CultDef` + a global **menace meter**.
- `parser/communal_commands.py` `RallyCommand` — `rally` shows a threat board;
  `rally strike` rolls the player's single best cross-playstyle pool **once per ~10 min**
  and nudges the menace down. The community grinds the meter to 0 over time.
- `engine/communal_objective_runtime.py` + `server/tick_handlers_progression.py`
  (`communal_objective_tick`) post/escalate/resolve it. Reward = Republic rep + a status flag.
- Explicitly an MVP: header says "design III.3"; `TODO.json` says **"rally-objective
  mechanics are design-open."** It auto-picks the player's best skill, so playstyle is
  irrelevant; there is no location, no waves, no cooperation beyond a shared number.

**Verdict:** it is a counter, not a scenario. Confirmed across the whole roster (one mechanic).

## The fix is mostly composition — the primitives already exist

The gameplay Brian wants already lives in the **wilderness-anomaly** system, which the
cults simply don't use (`engine/wilderness_anomalies.py`):
- **Location-based combat:** anomalies spawn at a site; `investigate <id>` spawns the
  real enemies into the player's room and a live fight starts; a kill-hook awards on the
  last death.
- **Waves (already scaffolded):** anomaly templates declare `phases: [...]` with their own
  `combat_npcs` per phase — *"killing the last hostile of phase N advances to phase N+1"* —
  designed for *"3-5 coordinating players."* That is waves of enemies, by design.
- **Varied skills:** anomalies have a `skill` mode (`perform_skill_check`) alongside `combat`,
  so "slice the conduit" = a security/computer check, "free the captives" = persuasion/medicine.

The only genuinely-missing piece is **stage orchestration** ("go here → wave → skill gate →
boss → resolve"). That is exactly what the **tutorial-chain / questline step engine** already
does — it gates steps on `combat_won` / `skill_check_passed` / location entry. **T3.24
generalized questlines is the orchestration layer for this.**

## Target design — the "staged event" pattern

A communal event becomes a multi-stage **site scenario** (data-defined, reusing the primitives):

1. The event posts a **site** (a flagged room/area). `rally` becomes the *find/track* surface
   ("where is it, what stage is it on, who's there") — not the gameplay.
2. Players travel there. **Stage 1 — wave combat** (anomaly multi-phase combat: escalating
   cultist waves; cooperative for a small group).
3. **Stage 2 — multi-skill objectives**: e.g. slice the ritual conduits (security/computer),
   shatter the wards (a Force or demolitions check), free captives (persuasion/medicine) — so a
   slicer / face / medic each matter *alongside* the soldiers, and matter *together*.
4. **Stage 3 — confront the cult leader** (boss combat).
5. **Resolve** with the existing reward/holonet payoff. Failure/timeout escalates (existing
   menace concept becomes the stakes, not the gameplay).

Cooperative because everyone in the site works the same stages — which is what the multi-phase
combat was built for. **Extend the anomaly/combat/skill/questline primitives; do NOT build a
parallel event system** (CLAUDE.md: extend-don't-add).

## Recommended path

1. Short design doc ratifies the staged-event pattern (this doc) + the data schema for a staged
   event (stages → {combat phases | skill gates | boss}, reusing anomaly/chain fields).
2. **Vertical slice:** rework **Cult of the Hollow Sun** into a 3-stage site scenario so Brian
   can play it and we tune the feel (pacing, solo-viability, which skills) before generalizing.
3. Generalize the pattern to the rest of `CULT_ROSTER` and any future events; retire the
   `rally strike` counter as the *gameplay* (keep `rally` as the tracker).

## Open questions for Brian
- **Timing:** an unfun headline event is a launch-quality issue → lean pre-launch for at least the
  vertical slice; but it's meatier than the QA tail. Slot now vs right-of-launch?
- **First scenario's shape:** which skills feature; how many waves; **solo-viable vs requires a
  small group** (the multi-phase combat assumes 3-5 — do we want a solo-scalable variant?).
