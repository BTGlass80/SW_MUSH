# T5 Master-Trainer Questlines — Design v1

**Status:** ACTIVE (build in progress, 2026-06-13)
**Author:** Claude Opus 4.8 (main session), under Brian's unattended-progress directive.
**Roadmap item:** `T2.DEF.t5_trainer_storyline`
**Supersedes:** the empty `trainer_npc` fields on the five `t5_*` schematics.

---

## 1. Problem

The five tier-5 master schematics in `data/schematics.yaml`
(`t5_master_crafted_lightsaber`, `t5_top_spec_blaster_rifle`,
`t5_hyperdrive_surge_converter`, `t5_mil_spec_ion_engine_core`,
`t5_master_grade_armor`) are 25–28-difficulty, 7.5k–15k-cost end-game
recipes. The trainer machinery
(`parser/crafting_commands.py::trainer_curriculum` /
`handle_trainer_teach`) keys schematics to a trainer by the
`trainer_npc` field — but all five t5 fields are empty `""`, so the
recipes are unreachable by any normal player. Closing that gap is the
roadmap item. The *how a player earns access* is the design.

## 2. Resolved design forks (Brian, 2026-06-13)

These were genuine forks; Brian ratified them interactively before the
build so it could run unattended.

| Fork | Decision |
| --- | --- |
| **DIFF.4 reward multipliers** (live since drop 31) | **Ratify as-is** — 0.6 / 1.0 / 1.4 / 2.0 by threat band stand as launch values; retune from telemetry post-launch. |
| **How a player earns a t5 trainer** | **Gated questline each** — every trainer is unlocked by completing a dedicated questline, not just a rep number or a talk. |
| **Questline richness** | **Rich** — combat + travel + a small NPC web per questline (not a 3-beat lean chain). |
| **Placement + gate** | **Faction rep ≥ honored (50) AND the trainer lives in a Contested Marches / Deep Wilds zone** (ties into the DIFF threat bands). The curriculum hides t5 schematics below 50 rep even if the player reaches the trainer. |
| **Quest engine architecture** | **Generalize the chain engine to multi-slot + add a quest-start verb / NPC offer hook** — extend, don't bolt on a parallel quest system or stretch the mission board. |

### Unattended-risk note (main session, not a Brian fork)

"Rich" questlines (cross-zone travel, themed combat, multiple NPCs) are
exactly the shape that stranded players in drops 24–25 (keystone
teleport, SECURED drill rooms, multi-enemy unwinnable). Mitigation, held
as a hard gate on Drop B:

- Every new questline gets the **static reachability invariant**
  (`tests/test_chain_corpus_reachability_invariant.py` CLASS 1–4) +
  a **per-chain walkthrough smoke** that drives the LIVE parser from a
  real chargen by player-only commands.
- If a rich step genuinely strands a player and the fix is a design
  fork (not a bug), that single step is **downgraded to lean** and the
  fork logged — rather than stalling the unattended run. Any such
  downgrade is recorded in the end-of-session handoff.

## 3. Ground truth verified at HEAD (no phantoms)

- **Chains are LIVE at runtime.** The `chains.yaml` header comment
  claiming the file is "inert at runtime" is **STALE** — verified false.
  `engine/chain_events._get_corpus()` lazy-loads the corpus; all 11
  completion types are wired into production parser/combat/movement/
  mission/bounty seams; chargen assigns a chain
  (`server/game_server.py` merges the wizard's chain block into
  attributes JSON). The walkthrough smoke walks all 7 unlocked chains
  from chargen to graduation through the live parser.
  *(Side task: this build will correct the stale header comment.)*
- **Chain state is single-slot, chargen-only.** `attributes.tutorial_chain`
  holds exactly one chain block. There is **no** `start_chain` /
  `begin_chain` seam and **no** second slot. Every state helper in
  `engine/tutorial_chains.py` reads/writes the one literal key
  `_TUTORIAL_CHAIN_KEY = "tutorial_chain"`. This is the single fact that
  forces the Drop-A engine work.
- **Reachability CLASS 2 forbids `room_entered` / `item_acquired`
  completions** in teleport-only chain rooms. New questline steps must
  use other completion types for movement/fetch beats (e.g. drive travel
  via `command_executed` on a move/`go` verb that the player issues,
  with the step's `location` doing the teleport-on-advance), or place
  the fetch beat in a real world room that has exits.
- **Threat bands are already on zones** (DIFF.2). `zones.yaml` carries
  `properties.threat_band` ∈ {frontier, settled, contested_marches,
  wilds}. Contested/Deep-Wilds zones exist on Tatooine (Dune Sea),
  Coruscant (Underworld), Geonosis, etc. — real placement targets.
- **Reputation API:** `engine/organizations.py::get_char_faction_rep(char, faction_code, db)`
  returns 0–100 for members / −100..+100 for non-members; the "honored"
  tier starts at 50. This is the gate funnel for the curriculum filter.

## 4. Architecture — multi-slot chains (Drop A)

**Principle:** the existing single-slot onboarding chain stays
byte-for-byte unchanged. Mid-game questlines live in a *second* slot.

### 4.1 Two slots, one engine

```
attributes["tutorial_chain"]    # onboarding (chargen-assigned) — UNCHANGED
attributes["active_questline"]  # NEW: one active mid-game questline
```

Rather than rewrite every helper to operate on a list (churny, risks
onboarding regressions), the state helpers in `engine/tutorial_chains.py`
gain an optional **`state_key` parameter defaulting to
`_TUTORIAL_CHAIN_KEY`**. Every existing call site is therefore
behavior-neutral; questline callers pass `state_key=_QUESTLINE_KEY`.

Helpers parameterized: `select_chain`, `get_current_step`,
`advance_step`, `is_chain_complete`, `get_active_chain_id`,
`reset_chain_state`, plus the `requires_first` / combat-tally
sub-helpers (their private state keys become per-slot to avoid
cross-slot bleed).

### 4.2 Dispatcher checks both slots

`engine/chain_events._get_active_step` today reads only the onboarding
slot. It becomes slot-aware: each event dispatcher
(`on_command_executed`, `on_talk_to_npc`, `on_combat_won`, …) attempts a
match against the onboarding slot **and** the questline slot, advancing
whichever has a matching active step. Both can be active at once
(a newbie won't have a questline; a veteran's onboarding chain is long
graduated — so in practice only one matches, but the engine supports
both).

### 4.3 Starting a questline mid-game

A questline is offered by its trainer-questline *giver* NPC and started
by an explicit player verb. New surface, all thin. **Verb namespace
note:** `quest`/`quests`/`+quests` are already owned by the Director-AI
personal-quest system (`narrative_commands.py`), `quest` is a spacer-quest
alias, and `train`/`training` are the CP-spend / tutorial commands — so
the trainer-questline verb is **`mastery`** (collision-free, reads as
"master-trainer certification").

- **`mastery`** (aliases `masteries`, `mastertrials`): lists the player's
  active questline + any offered-and-eligible questlines in the current
  room.
- **`mastery start <id>`** / NPC-offer accept: validates eligibility
  (`is_chain_locked_for_character` against the questline's prerequisites
  — which include the rep+zone gate), then `select_chain(attrs,
  questline, state_key=_QUESTLINE_KEY)`.
- **NPC offer hook:** when a player talks to a questline-giver NPC and
  has no active questline + meets prereqs, the talk surfaces the offer
  (reusing the existing `talk_to_npc` seam — no new combat/move seam).

Questline chains are flagged `kind: questline` (new optional chain
field, default `tutorial`) so the chargen chain-picker never lists them
and the `quests` surface never lists onboarding chains. Additive schema.

### 4.4 What Drop A does NOT change

- Onboarding chain behavior, chargen flow, the chain-picker UI.
- The 11 completion-type matchers (reused verbatim).
- The reachability invariant / walkthrough smoke harness (extended to
  cover the new questline kind, not rewritten).

## 5. Content — five rich questlines (Drop B)

Each questline = one `kind: questline` chain in a new content file
(`data/worlds/clone_wars/questlines/t5_master_trainers.yaml` or appended
section), 5 rich steps, ending in a `talk_to_npc` certification step
whose graduation grants the rep that crosses the 50 threshold AND a
durable `attributes` flag the curriculum reads. Themed per trainer:

| Trainer (archetype) | Faction | Home zone (band) | Schematic unlocked | Questline flavor |
| --- | --- | --- | --- | --- |
| Jedi Master | jedi_order | contested/wilds | `t5_master_crafted_lightsaber` | contemplative trial + a guardian combat |
| Hutt weaponsmith | hutt_cartel | contested (Dune Sea) | `t5_top_spec_blaster_rifle` | shady fetch across the wastes + a rival ambush |
| Republic engineer-corps | republic | contested | `t5_mil_spec_ion_engine_core` / `t5_hyperdrive_surge_converter` | field-test under fire |
| Master armorer | independent / guild | wilds | `t5_master_grade_armor` | endurance + a beast hunt |

*(Trainer names, exact rooms, and which engineer schematic pairs with
which beat are authoring choices made in Drop B against the real
zone/room set; the table is the skeleton, not a phantom-room promise.)*

### 5.1 The rep+zone+questline gate (three layers, defense in depth)

1. **Reach the trainer:** the giver/trainer NPC lives in a
   Contested/Deep-Wilds room — physically getting there is the first
   gate (and the reason the questline reads as end-game).
2. **Questline completion:** the schematic's `trainer_npc` only teaches
   after the questline graduates (the curriculum checks the durable
   completion flag the graduation sets).
3. **Rep floor:** `trainer_curriculum` hides any `t5_*` schematic when
   the player's rep with the trainer's faction is < 50, even
   post-questline — a deserter who tanks their rep loses access.

### 5.2 Curriculum rep-gate (Drop B engine touch)

`trainer_curriculum(npc_name, char=None, db=None)` gains optional
char/db params. When present and any matched schematic is `t5_*`, it
filters t5 entries by `await get_char_faction_rep(char, trainer_faction,
db) >= 50` AND the questline-complete flag. Absent char/db (legacy
callers / tests), behavior is unchanged (no t5 in the base seed data
today, so no regression). The trainer's faction comes from the NPC's
`ai_config.faction`.

## 5.3 Build sequencing decision (main session, 2026-06-13)

Drop B is large (5 trainers × {NPC + enemy template + 5-step rich chain +
gate fields} + test extensions). To keep the "rich = stranding" risk
(drops 24/25) contained under unattended work, Drop B ships as
**one proven vertical slice at a time**, not 5 chains at once:

- **Drop B slice 1 (LANDED 2026-06-13):** the Jedi Master / lightsaber
  questline ("The Hermit's Trial", `master_jedi_lightsaber`) — the
  complete path end-to-end (NPC + krayt-spawn enemy + 5-step chain +
  schematic gate), proven by the static reachability invariant AND a
  content walkthrough test that drives start→graduation through the real
  dispatcher hooks. This establishes the template.
- **Drop B slices 2–5 (companion drop):** the remaining masters, each a
  mechanical repeat of slice 1's proven template:
  - Hutt weaponsmith → `t5_top_spec_blaster_rifle` (Nar Shaddaa
    `fighting_pits`, hutt_cartel)
  - Republic hyperdrive specialist → `t5_hyperdrive_surge_converter`
    (Geonosis `geonosis_cis_command_post`, republic)
  - Republic ion-engine specialist → `t5_mil_spec_ion_engine_core`
    (Geonosis, republic) — split from the hyperdrive trainer so each
    questline is 1:1 with one schematic (cleaner than one engineer
    gating two recipes), preserving the "5 trainers" shape.
  - Master armorer → `t5_master_grade_armor` (Nar Shaddaa
    `warrens_scavenger_den`, independent)

  Each gets its own `gated_by_questline`/`gated_faction` fields, its own
  reachability-invariant pass, and its own walkthrough test.

## 5.4 Rep economy (Brian, 2026-06-13) — the per-step reward consumer

Drop B's review found that per-step `credits`/`faction_rep` rewards were
authored across ALL chains but never delivered (`apply_step_rewards` was
items-only). Brian's call: **make the consumer real for all chains, and
tune the rep so no one walks out of a short questline maxed on faction
rep.** Implemented:

- `apply_step_rewards` now delivers per-step credits (metered
  `chain_step_reward` faucet) + rep (`adjust_rep` funnel).
- Because per-step rep now stacks on graduation rep, all chain rep
  totals were rebalanced. **Invariant (pinned by
  `TestChainRepEconomyCeiling`): no chain may leave a player at ≥
  honored (rep 50) in any one faction from the chain alone.** Honored is
  the t5 gate and the threshold for serious faction standing — it is
  earned through play, never handed out by a tutorial/questline.
- Result (after Brian's "tune lower" follow-up — 20–40 read as too
  generous): onboarding chains land **recognized (~8–13**, ≈10% of max —
  "the faction knows your name"); "The Hermit's Trial" lands jedi_order =
  18. The t5 lightsaber's rep-50 gate therefore requires a substantial
  ~32 rep of post-questline Jedi play — the **questline gate and the rep
  gate are genuinely separate** (completing the trial is necessary but
  far from sufficient). Hard ceiling of 22 pinned in
  `TestChainRepEconomyCeiling` so the tuning can't silently drift up.

## 6. Drop plan

- **Drop A (engine, behavior-neutral):** multi-slot `state_key` param +
  questline slot; slot-aware dispatcher; `quests` / `quest start` verbs
  + NPC offer hook; `kind` chain field; correct the stale chains.yaml
  header. Tests: onboarding-neutrality regression (every existing chain
  test still green), new multi-slot unit tests, a questline start/advance
  unit test. No content yet.
- **Drop B (content + gate):** 5 questline chains + 5 trainer/giver NPCs
  placed in Contested/Wilds rooms; populate the 5 `trainer_npc` fields;
  curriculum rep+completion gate; reachability invariant extended to the
  questline kind; per-questline walkthrough smoke. Faucet/sink check:
  questline graduation credits are a faucet — paired against the t5
  crafting cost sink (7.5k–15k), which dwarfs any graduation payout.

## 7. Invariant checklist (both drops)

- Era cleanness (B3): CW-only strings; no Imperial/Rebel/TIE.
- Funnels: graduation credits via `adjust_credits(..., "questline_reward")`;
  rep via `adjust_territory_influence` / the org rep funnel; any skill
  check via `perform_skill_check`.
- No phantom producers/consumers: every authored room/NPC/flag has a live
  consumer; every `trainer_npc` value names a placed NPC.
- Faucet/sink land together (graduation faucet + t5 craft sink).
- Map safety: NPC placement is additive; no deleted world-YAML lines.
- CHANGELOG.md + TODO.json updated in the same commit as each drop.
