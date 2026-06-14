# Quest/Scenario Expansion — Post-Launch Path (VERIFIED) — v1

> Captured 2026-06-13. Records a Brian scope ruling + the code-level verification that backs it.
> Pairs with `t5_trainer_questlines_design_v1.md` (the ratified chain-engine generalization) and the
> "Quest/hook extraction" decision in `sourcebook_ingestion_pipeline_v1.md`.

## The ruling (Brian, 2026-06-13)

Generalized **quest/scenario expansion is one of the few features explicitly allowed to live RIGHT OF
LAUNCH** (post-launch) — an exception to the standing "launch = the whole backlog" posture — **conditioned
on a clear, painless path to it (no ugly live-DB migration onto populated player rows).** If no painless
path existed, the same condition would force it back to pre-launch scope. So the condition is load-bearing
and was verified, not assumed.

## Verdict: the painless path EXISTS (verified at code level)

**Confirmed — quest expansion can safely defer to post-launch.** The four seams a quest engine needs are
already present and additive:

1. **Engine — already the generalization target (extend, don't add is satisfied).** `engine/tutorial_chains.py`
   (state machine) + `engine/chain_events.py` (event→advance dispatcher) is the quest engine. The T5
   "questline arc" (ratified by Brian 2026-06-13 in `t5_trainer_questlines_design_v1.md`) already added a
   first-class `kind: questline` chain type, a dedicated `active_questline` state slot (`CHAIN_STATE_KEYS`),
   start/abandon/offer functions, and mid-game `quests` / `quest start` / `mastery` verbs
   (`parser/questline_commands.py`). Questlines are authored in the same `chains.yaml`.

2. **State store — JSON blob, NO migration (this is the #1 risk, and it's already neutralized).**
   Per-character quest progress lives inside the character row's `attributes` TEXT/JSON column
   (`CHAIN_STATE_KEYS` slots), persisted through `save_character`. Adding quests post-launch needs **no
   ALTER on a live populated table, no backfill, no save-format break.** (Optional belt-and-suspenders:
   reserve a dedicated `quest_progress` JSON column now via the `MIGRATIONS` list — or the `titles.py`-style
   idempotent `ensure_schema` column-loop — but it is NOT required; the `attributes` blob already holds
   chain/quest state. If reserved, add it to `_CHARACTER_WRITABLE_COLUMNS` in the same drop.)

3. **Event triggers — 11 types already emitted AND already fanned to the questline slot.**
   `chain_events._try_advance_all_slots` dispatches every emitted event across BOTH the onboarding slot and
   the `active_questline` slot, so these drive questline steps **today, zero new wiring, pure YAML**:
   `command_executed, talk_to_npc, combat_won (by enemy_template), room_entered, mission_accepted,
   mission_completed, bounty_accepted, item_acquired, item_used, skill_check_passed, prerequisite`.
   **Gaps (each additive, low-risk — one coroutine + matcher + one hook-site edit, no migration):** no
   emitter yet for skill-up / level-up / CP-spend; bounty COMPLETION (only accept is observed); generic
   untagged NPC kill (only chain-tagged `combat_won`); compound objectives (kill 3 of {a,b,c}) need matcher
   extension. Dispatch is hand-wired point-to-point (no central bus) by design — a new event type means
   adding the emit at its subsystem seam, not a refactor.

4. **Reward funnels — all four exist and are canonical (faucet/sink invariant already satisfied).**
   Credits → `db.adjust_credits(char_id, delta, tag)` (`db/database.py:2671`); items →
   `db.add_to_inventory(char_id, item, fire_chain_hook=True)` (`db/database.py:4795`); CP →
   `CPEngine.award_milestone_cp` (`engine/cp_engine.py:263`); influence →
   `adjust_territory_influence` (`engine/territory.py:331`). The existing chain reward helper
   `grant_reward` (`engine/tutorial_v2.py:369`) already composes credits + item + title in one place.
   **Quest rewards route through these with zero new plumbing.**

## Pre-launch obligation (what "painless" actually costs now)

**Essentially nothing blocking.** The path already exists. The only pre-launch moves worth considering:
- **(Optional)** reserve a `quest_progress` JSON column via a migration now, IF the fixed 2-slot
  `CHAIN_STATE_KEYS` model is judged too tight for the eventual engine. Cheap, additive, decided later.
- **(Already documented)** the content bridge: a `--target hooks` mode on `tools/ingest_lore.py` that emits
  sourcebook adventure hooks as mission/bounty seeds — feeds existing systems pre-launch, becomes quest
  fodder post-launch. See `sourcebook_ingestion_pipeline_v1.md`.
- **Keep questline state JSON-based** (it already is) so the post-launch widening (2 slots → N, new
  completion/trigger types) stays additive.

## Post-launch build shape (for when it's time)

Extend `tutorial_chains.py` / `chain_events.py` (do NOT fork a parallel system): (a) widen the fixed 2-slot
`CHAIN_STATE_KEYS` to an N-slot list; (b) add new `ALLOWED_COMPLETION_TYPES` + their matchers as quests
need them (timed, deliver-N, escort, bounty-completion, skill-up) — each with its emit seam in the same
drop (no phantom producers/consumers); (c) author questlines in `chains.yaml` (`kind: questline`). The
`tests/test_chain_corpus_reachability_invariant.py` reachability guard already polices questline-kind
chains (real rooms, registered commands, canonical skills).
