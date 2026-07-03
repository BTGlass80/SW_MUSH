# DESIGN — The Staged-Questline Archetype (reusable "staged content" pattern)

**Date:** 2026-07-03
**Author:** Opus design-synthesis pass (Brian's picked primary next investment)
**Status:** PROPOSAL — surfaces the genuine forks; not yet built.
**Origin:** Fable review Appendix C / §4a — *"wind down one-off arcs at 35; next content budget = a staged-questline archetype on the Hollow-Sun / T3.23 substrate, unified with EVENT.communal_rework in ONE design pass."*
**Grounding:** Every symbol cited below was verified against HEAD (not handoff docs). Cites carry file + line.

---

## 0 · TL;DR — what the archetype IS

A **staged questline** is an ordinary `kind: questline` chain (the T3.24 engine) with **one new step kind — `site_cleared`** — whose completion is "go to this room, clear the multi-phase scenario anomaly that gets armed there." The wave→skill-gate→boss shape lives *inside* the anomaly's own `phases[]` (the T3.23 substrate). So the archetype is a **seam, not a system**: it bridges the two staged engines SW already owns —

- **chain engine** (`engine/tutorial_chains.py` + `chain_events.py`): sequencing, per-character state in the `attributes` JSON blob (no migration), narrative NPC givers, reward funnels, graduation, reachability/winnability invariants; and
- **wilderness-anomaly engine** (`engine/wilderness_anomalies.py`): multi-phase wave combat + `skill_gate` + participation payout + `spawn_scenario_anomaly` deterministic named-spawn —

by adding **one completion type, one arm-on-step-entry sibling, and one dispatcher hook.** No new table, no new command, no new orchestrator, no new reward faucet.

The payoff: a designer authors "go to a site, fight staged waves + skill gates + a boss, get a questline reward + graduation" as a **YAML chain that names a scenario template** — the exact thing each of the 5 cult conversions had to hand-wire. It also finally lands T3.23's `skill_gate` content, which is fully built but **inert with zero authored rows** at HEAD.

---

## 1 · What EXISTS vs what is NEW (the reuse map)

### REUSED verbatim — no rebuild (verified at HEAD)

| Capability | Symbol (HEAD) |
|---|---|
| Deterministic named-template spawn at a named room | `wilderness_anomalies.spawn_scenario_anomaly(db, region_slug, template_key, anchor_room_id, *, tier, zone_id, …)` — L3414 |
| Multi-phase wave → skill-gate → boss shape | `SCENARIO_TEMPLATES[...].phases[]` L1833+; `_advance_to_next_phase`; `phase_skill_gate` L3069 |
| The skill-diverse middle stage (T3.23) | `_resolve_skill_gate_phase` L3904 (alt_skills role-sub + solo_penalty soft-require + retry-cooldown); `contribution_log` L3018 |
| Clear signal | `anomaly.resolved_by` stamped at every resolution path — skill L3847, combat kills L4619/L4802 |
| Participation-scaled payout | `_payout_combat_anomaly` L4581 (unions `kill_counts` ∪ `contribution_log`) |
| Multi-step sequencing + per-char state (no DB migration) | `tutorial_chains.advance_step` L692; `active_questline` slot L520; state rides `attributes` JSON |
| **Arm-something-on-step-ENTRY precedent** | `chain_missions.maybe_spawn_for_step` L284, called from the `_try_advance` new-step block `chain_events.py` L1207 |
| "Completes when the tagged NPC is cleared" precedent | `on_combat_won` L458 + `_try_advance_all_slots` L930 |
| Slug→room resolution for a step's location | `chain_missions._spawn_bounty` → `db.get_room_by_slug(target_slug)` L412 |
| Reward funnels (per-step + graduation) | `chain_rewards.apply_step_rewards` / `apply_graduation_rewards` → `adjust_credits` / `adjust_rep` / `add_to_inventory` |
| Reward-tier consistency + winnability guards | `tests/test_questline_reward_tier_consistency.py`, `test_questline_foil_winnability_band.py` |
| Reachability invariant framework (per-class validators) | `tests/test_chain_corpus_reachability_invariant.py` |

### NEW — the minimal engine glue (this is the whole build)

1. **One completion type.** Add `"site_cleared"` (name TBD, see Fork 2) to `ALLOWED_COMPLETION_TYPES` (frozenset, `tutorial_chains.py` L59) + validate its `scenario_template` / `tier` in `_parse_step` (already validates `ctype` against the frozenset, L457).
2. **One arm-on-entry sibling.** `chain_missions.maybe_arm_site_for_step(db, char, chain_id, step_num)`, called from the SAME `_try_advance` new-step block (`chain_events.py` L1207, right beside the existing `maybe_spawn_for_step` call). It resolves `step.location` slug→room (+zone_id) exactly as `_spawn_bounty` does (L412), calls `spawn_scenario_anomaly(...)`, and **stamps the returned `anomaly.id` onto chain-step state** (new key `step_scenario_anomaly_id`, dropped on advance the same way `step_combat_kills` / `step_progress_satisfied` are).
3. **One dispatcher hook.** `chain_events.on_site_cleared(db, char, template_key, anomaly_id)`, wired at the anomaly **all-phases-resolved** seam (where `resolved_by` is stamped — inside/after `resolve_anomaly` L3706 and `_payout_combat_anomaly` L4581), dispatching through `_try_advance_all_slots` with a new `_match_site_cleared` matcher (match `completion.scenario_template == cleared template` **and/or** the stamped `step_scenario_anomaly_id`, gated on `resolved_by == char.id`). Failure-tolerant like every sibling hook.
4. **One matcher + the state-key drop** in `advance_step` (mirror `step_combat_kills`).
5. **One reachability-invariant class.** Assert every `site_cleared` step's `scenario_template` resolves to a real `SCENARIO_TEMPLATES` key and `step.location` is a real loaded room (parallel to the existing CLASS-4 skill validation).
6. **(Fork 3-conditioned) one `suppress_payout` flag** on `spawn_scenario_anomaly` so a chain-armed scenario doesn't double-pay its own anomaly faucet on top of the questline reward.

That is the entire new surface: **+1 frozenset value, +1 arm sibling (~a clone of `maybe_spawn_for_step`'s slug-resolve + one spawn call), +1 hook + matcher, +1 invariant class, +1 optional flag.** No schema, no command, no faucet, no orchestrator.

### What is NOT reused (the cult wrapper we deliberately leave behind)

`is_staged`/`CULT_BY_KEY` gating, the single-global-`communal_objective`-row state carrier, `staged_event.STAGED_CULTS`'s cult-keyed stage machine, `_pick_anchor_room`'s **random** re-roll (L3267), the staged menace failure clock, and `_distribute_rewards`'s cult payout. The archetype rides the **chain** carrier instead. (Whether to later fold the cults *onto* the archetype is Fork 6.)

---

## 2 · The exact seam where staged-scenario meets chain-step

Two touch points, both already load-bearing precedents in the codebase:

**ARM (chain → anomaly), on step entry.** `chain_events._try_advance`, after a successful advance, already runs the new-step spawn block (L1207):

```python
if new_step is not None and not graduated:
    from engine.chain_missions import maybe_spawn_for_step
    await maybe_spawn_for_step(db, char, chain.chain_id, new_step.step)
    # NEW — sibling call, same failure-tolerant shape:
    await maybe_arm_site_for_step(db, char, chain.chain_id, new_step.step)
```

`maybe_arm_site_for_step` reads the step's `completion.scenario_template` + `tier`, resolves `new_step.location` via `db.get_room_by_slug` (the `_spawn_bounty` pattern, L412), calls `spawn_scenario_anomaly`, and writes `anomaly.id` into the chain-step state blob.

**CLEAR (anomaly → chain), on resolution.** Every anomaly resolution path already stamps `anomaly.resolved_by = char_id` (skill L3847; combat kills L4619/L4802). At the **final-phase** resolution (all `phases[]` done), fire `on_site_cleared(db, resolver_char, template_key, anomaly_id)`, which walks both chain slots via `_try_advance_all_slots(event_type="site_cleared", matcher=_match_site_cleared)`. The matcher advances the step whose `completion` names that template/anomaly, exactly as `on_combat_won` advances a `combat_won` step.

This is symmetric with the mission path that already exists: `maybe_spawn_for_step` arms → the parser fires `on_mission_completed` → the step advances. We are adding the anomaly-shaped twin of that loop.

---

## 3 · The DATA schema a designer authors

### 3a · The chain (YAML, `chains.yaml` — already data)

A staged questline is a normal `kind: questline` chain. The only new thing is a step whose `completion.type = site_cleared`:

```yaml
- chain_id: geonosis_hive_purge
  chain_name: "The Hive That Wouldn't Die"
  kind: questline
  archetype_label: staged            # NEW optional label so the tier guard & UI
                                     #   can recognize the heavier format (Fork 3/9)
  prerequisites: [chargen_complete]
  starting_zone: ...
  starting_room: ...
  steps:
    - step: 1                        # narrative giver (reused talk_to_npc)
      title: "The Contract"
      location: <giver_room_slug>
      npc: "Overseer Krenn"
      completion: {type: talk_to_npc, npc: "Overseer Krenn"}
      reward: {...}                  # small per-step reward (existing funnel)

    - step: 2                        # THE STAGED SITE — one multi-phase scenario
      title: "Purge the Hive"
      location: <wilderness_or_venue_room_slug>   # FIXED room (Fork 5)
      completion:
        type: site_cleared           # NEW completion type
        scenario_template: geonosis_hive_purge_site   # a SCENARIO_TEMPLATES key
        tier: 2
      reward: {...}                  # OR reward only at graduation (Fork 3)

    - step: 3                        # resolve + graduation (reused talk_to_npc)
      title: "Report In"
      location: <giver_room_slug>
      npc: "Overseer Krenn"
      completion: {type: talk_to_npc, npc: "Overseer Krenn"}
  graduation:
    reward: {credits: <tier>, faction_rep: {...}, achievement: hive_purged}
    drop_room: <live_vendor_hub_slug>
```

### 3b · The scenario template (the wave/skill/boss content)

The `scenario_template` value points at a `SCENARIO_TEMPLATES` entry whose `phases[]` carry the whole staged shape — **this is where the archetype activates T3.23's inert `skill_gate`**:

```python
"geonosis_hive_purge_site": {
    "resolution": "combat",
    "regions": [],                       # orchestrator-spawned only (no random tick)
    "chain_armed": True,                 # NEW: mark as questline-armed (Fork 3 payout-suppress)
    "phases": [
        {"name": "Outer Tunnels", "intro": "...",
         "combat_npcs": [ ...wave... ]},                    # WAVE
        {"name": "Sealed Bulkhead", "intro": "...",
         "skill_gate": {"skill": "security", "difficulty": 12,
                        "alt_skills": ["demolitions", "computer_programming"],
                        "solo_penalty": 3}},                # SKILL-GATE (T3.23)
        {"name": "The Brood-Mother", "intro": "...",
         "combat_npcs": [ ...boss... ]},                    # BOSS
    ],
    "success_reward": {...},              # fires ONLY if not chain_armed (Fork 3)
}
```

**Honest note (Fork 8):** `SCENARIO_TEMPLATES` is a *Python module literal*, not YAML. So today the chain (sequencing / narrative / NPCs / rewards / graduation) is authored as data, but the wave/skill/boss template is still a Python dict edit. "Authored mostly as DATA" is true — the sequencing, reward, and narrative are all YAML — but the *combat content* is one `.py` edit unless Fork 8(a) moves the template registry to YAML.

---

## 4 · What becomes DATA vs what stays ENGINE

**Reusable DATA (per-instance, zero orchestration edit):**
- The whole questline chain: steps, narrative, givers, per-step + graduation rewards, drop room, prerequisites (already 100% YAML).
- Each `site_cleared` step's `{scenario_template, tier}` pointer.
- The venue/region YAML + ambient-NPC file (already YAML, like every wilderness region).
- The scenario template's phase content — *data-shaped* but currently a Python literal (Fork 8).

**New ENGINE glue (built once, then never touched per-instance):** the six items in §1 — completion type, arm sibling, clear hook + matcher, invariant class, optional suppress flag. Per the extend-don't-add invariant, **none of it re-implements** the arm→stage→clear→reward loop; it wires the chain carrier to the anomaly substrate at two seams that already have working twins (`maybe_spawn_for_step`, `on_combat_won`).

---

## 5 · Smallest first slice (prove the pattern; don't boil the ocean)

**One authored staged questline, single `site_cleared` step, one multi-phase anomaly.**

- A `kind: questline` chain with **3 steps**: `talk_to_npc` (giver) → `site_cleared` (a NEW standalone `SCENARIO_TEMPLATES` entry with exactly **wave phase → skill_gate phase → boss phase**, tier 2) → `talk_to_npc` (resolve + graduation).
- Anchor at a **fixed hand-built venue room** (proves Fork 5a fixed-anchor — reuse the just-shipped `kuat_bulk_liner`-style venue pattern from the 36th arc, or a new small venue), *or* a fixed wilderness-region landmark room if the resolve path needs a region (verify at build).
- Reuse the hollow-sun phase *structure* as the model, but as a standalone (non-cult) template — do NOT touch `STAGED_CULTS`.
- Reward: pick a tier (Fork 3/9) — recommend a new **staged tier** distinct-and-higher than freelance 450 — and **suppress the anomaly's own `success_reward`** so the format doesn't double-pay.
- **Guard with a walkthrough smoke that drives the REAL `investigate`/combat-kill seam** — not a hand-injected clear. This is the explicit lesson from the 5-cult payout bug: every per-cult test hand-injected `contribs["cid"]={"points":50}` and so all 5 clones rode a broken payout to launch (`test_staged_cult_reward_payout_2026_07_03.py`). One tested archetype orchestration is what catches that class.

This proves: the additive completion type; arm-on-entry; clear-to-advance; **T3.23 `skill_gate` finally exercised by shipping content**; the reward tier; and the reachability invariant class — all on ONE arc, with the cult runtime untouched.

---

## 6 · GENUINE FORKS for Brian (each a concrete either/or)

> These are real decisions, not guesses. The recommendation after each is the design-synthesis lean; Brian overrides.

**Fork 1 — Host carrier: bridge the chain engine, or generalize `staged_event`?**
- **(A) Bridge chains.** Add `site_cleared` to the chain engine; state rides `active_questline` in `attributes` (per-character, **no new table**). Lowest new surface; gets narrative givers + graduation + the tier/reachability guards for free. **But chains are strictly SOLO** — no party model.
- **(B) Generalize `staged_event`** into a `scenario_id`-keyed registry with a carrier abstraction, so one orchestrator serves both communal *and* questline triggers. Keeps party-shared play; **more engine work, and it lacks narrative givers / per-char progression.**
- *Recommend **A*** (matches "author one pattern, extend don't add"; party-optional is achievable via Fork 4-b without abandoning the chain carrier). *This is THE structural decision — Forks 2-9 assume A.*

**Fork 2 — Staging granularity: one multi-phase anomaly per step, or one single-phase anomaly per step with the chain as the stage machine?**
- **(A) One multi-phase anomaly per `site_cleared` step (Route 2).** Wave→skill→boss lives in the anomaly's `phases[]`; one step = one boss fight. Reuses the anomaly phase machine + **activates T3.23 `skill_gate`**. Best for a single-location climactic site.
- **(B) One single-phase anomaly per step, N steps = N stages (Route 1).** Each stage at a *different* room (matches how `STAGED_CULTS` names 3 separate templates). Reuses the simpler one-shot `resolution:"skill"` templates the cults ship today; good for a multi-location arc, but does NOT exercise `skill_gate`.
- *Recommend **A for the archetype's core**, allow **B** as a multi-step authoring option — the `site_cleared` step-kind supports both (a chain can have several `site_cleared` steps).*

**Fork 3 — Reward faucet + the double-pay hazard.** A chain-armed anomaly ALREADY pays its own `success_reward` / `_payout_combat_anomaly` on resolution, *plus* the chain step/graduation reward — and `test_questline_reward_tier_consistency` counts **only** chain rewards, so the "450cr freelance tier" invariant would become fiction.
- **(A) Suppress the anomaly's own payout** for chain-armed scenarios (a `suppress_payout`/`chain_armed` flag on `spawn_scenario_anomaly`); pay ONLY the questline reward. Clean single-faucet; keeps the tier guard honest.
- **(B) Keep both faucets** and extend the tier guard to fold the anomaly payout into the counted total. More faithful to "participation pays," but the tier math gets coupled to anomaly reward bands.
- *Recommend **A*** (one faucet per completion; simplest to reason about at `@balance chains`).

**Fork 4 — Solo vs party / shared instance.** `active_questline` is per-character solo; anomaly clears are room-shared and participation-scaled. "Whose questline advances when a co-op site clears?"
- **(A) Strictly solo.** Only the `resolved_by` char advances. Simplest — but two questers at the same room-shared anomaly collide (one clears it out from under the other).
- **(B) Party-optional via T3.23 participation.** The resolver advances; any co-quester who contributed (in `contribution_log` ∪ `kill_counts`) and is on the same `site_cleared` step also advances. Leans on already-built machinery; matches Fable's "party-optional." Needs the clear hook to fan over contributors, not just `resolved_by`.
- **(C) Per-player instanced anomalies.** Each quester arms their OWN anomaly instance. True isolation, but anomalies are currently room-keyed — **needs new per-player instancing (real engine work).**
- *Recommend **B*** (the solo_penalty soft-require + contribution_log union are built for exactly this).

**Fork 5 — Site anchor: fixed room, or wilderness-region random?**
- **(A) Fixed named room per step** (reuse the chain's `step.location` slug→room resolution). Anchors in ANY room — including hand-built venues (the `kuat_bulk_liner` 36th-arc pattern). This is what makes authored questline beats + capital-ship-style venues possible.
- **(B) Wilderness-region-anchored** (`_pick_anchor_room` random landmark). Right for a roving communal uprising; **wrong for an authored questline beat.**
- *Recommend **A*** — but verify at build that `spawn_scenario_anomaly` / resolve path tolerate a non-wilderness anchor room (templates conventionally set `regions:[]` and live in wilderness; a venue room may need a region association or a small resolve tweak).

**Fork 6 — Unify the cult uprisings onto the archetype, or keep communal separate?** (Fable: "author one staged pattern, not two.")
- **(A) Full unification.** Lift `STAGED_CULTS` into a `scenario_id`-keyed registry; a cult becomes a *communal-triggered* instance of the same scenario descriptor a questline uses — one substrate, two triggers (6h rotation vs quest-accept). Maximum reuse; retires the bespoke cult stage machine.
- **(B) Keep communal separate for now.** The archetype is questline-only; cults stay on their own runtime and merely **share** `SCENARIO_TEMPLATES` (which they already do). Ship the archetype without migrating 5 live cults.
- *Recommend **B for the first slice, design the DATA schema trigger-agnostic** so a later drop can point communal at it (A as stated end-state). Migrating 5 shipped cults is its own drop and shouldn't gate the archetype.*

**Fork 7 — Failure clock.** Cults have a one-way menace loss timer; chains have none.
- **(A) Persistent-until-cleared** (chain-style, no timer). Simplest; matches every existing questline.
- **(B) Optional per-scenario fail clock** — an authorable `fail_after_secs` on the site step (a menace-analog on the carrier) for "the reactor melts down" tension.
- *Recommend **A for v1**, **B** as an authorable-later data field (don't build the timer until an arc wants it).*

**Fork 8 — Move `SCENARIO_TEMPLATES` (and eventually `STAGED_CULTS`) to YAML, or keep the templates in Python?** (Reader-4 smoking gun: even a "100% declarative" cult requires editing two engine `.py` modules.)
- **(A) YAML-load the scenario templates** (like wilderness regions/NPCs already are). Eliminates the LAST `.py` edit → a staged questline becomes pure-data. But it's a migration of the existing 5-cult content + a new loader.
- **(B) Keep templates in Python.** The chain is YAML; the wave/skill/boss template is one `.py` dict edit reusing/adding a `SCENARIO_TEMPLATES` key. "Mostly data," not "fully data."
- *Recommend **B for the first slice, log A as the fast-follow** that closes the "authored as DATA" goal completely.*

**Fork 9 — Reward tier / difficulty for the heavier format.** (Fable §4a: flat 450 + fresh-winnable = veteran-trivial; the staged format is the natural home for a heavier tier.)
- **(A) A new "staged" reward tier** in `test_questline_reward_tier_consistency` — distinct-and-higher than freelance (450) and separate from master (700), e.g. ~900-1200cr — because a wave+skill+boss site is objectively more work than talk→check→shoot.
- **(B) Reuse the freelance 450 tier.** Keeps the tier guard trivial; **underpays the format** and gives veterans no reason to run it.
- **(C) Gate behind N freelance clears as an end-game "hard remix."** Adds a progression ladder; needs a lane-scoped clears-counter (which Fable also floated for rep-saturation).
- *Recommend **A*** (a distinct staged tier), with **C** as a post-launch remix once `@balance chains` shows completionists blowing through.

---

## 7 · Invariant & test notes (so the build lands clean)

- **Additive completion type:** `site_cleared` goes into the frozenset; `_parse_step` already rejects unknown types (L457) — a new type must ship with its consumer (the `on_site_cleared` hook) in the SAME drop (no phantom producers/consumers).
- **Faucet/sink:** no new faucet — reward flows through the existing `chain_reward` / `chain_step_reward` funnels; the suppress flag (Fork 3-A) *removes* a faucet on the chain-armed path, it doesn't add one.
- **Reachability:** new invariant class validating `scenario_template` → real `SCENARIO_TEMPLATES` key + `step.location` → real loaded room.
- **Winnability:** the boss/wave phases go through `test_questline_foil_winnability_band` (fresh-char-winnable band); the `skill_gate` difficulty goes through the skill-difficulty-winnability guard.
- **Drive the real seam in tests:** the walkthrough smoke MUST resolve the anomaly through the live `investigate`/combat-kill path (the 5-cult payout bug shipped precisely because every clone hand-injected the clear).
- **No schema:** state rides `attributes` JSON (`step_scenario_anomaly_id` dropped on advance like `step_combat_kills`).

---

## 8 · Decision order for Brian

Fork 1 (host carrier) gates everything. Then Fork 3 (reward faucet) + Fork 9 (tier) are the balance-critical pair. Fork 4 (solo/party) sets the clear-hook fan-out shape. Forks 2/5/7 are per-arc authoring latitude the archetype can support either way. Forks 6/8 are "how far to unify now vs fast-follow" — recommend deferring both past the first slice so the archetype ships on one arc without migrating live cult content or the template registry.

**One-line recommended default stack:** 1-A · 2-A(core) · 3-A · 4-B · 5-A · 6-B(schema trigger-agnostic) · 7-A · 8-B(log A) · 9-A. That stack ships a single self-contained staged questline with no schema change, no cult migration, T3.23 skill_gate finally live, one honest reward faucet at a distinct tier, and the whole cult-unification / YAML-templates work logged as fast-follows rather than gating the slice.
