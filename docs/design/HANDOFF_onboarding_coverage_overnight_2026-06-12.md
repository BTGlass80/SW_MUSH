# HANDOFF — Overnight Implementation Session: Onboarding Coverage Net + Polish

**Date authored:** 2026-06-12 (after drop 24)
**Branch:** `roadmap` (drop 24 committed @ `aa57838`, pushed)
**Audience:** an autonomous overnight Claude Code session (unattended)
**Mode:** implementation. Stop and log genuine design forks; do not guess.

---

## 0. Context — what just shipped (drop 24)

Live-testing a fresh Bounty Hunter exposed that **all 7 unlocked Clone Wars
tutorial chains were non-completable**. Drop 24 (committed, pushed) fixed the
playability:

- **Inter-step teleport** (`engine/chain_graduation.py::apply_step_teleport`,
  called from `engine/chain_events.py::_try_advance`) — the player is now
  relayed to each step's room on advance (tutorial rooms have no exits by
  policy).
- **`+factions` graduation alias** (`parser/faction_commands.py`).
- **`give` command** (`parser/builtin_commands.py::GiveCommand`).
- **Corpus fixes** (`data/worlds/clone_wars/tutorials/chains.yaml`): 2
  `room_entered` → `talk_to_npc`; phantom skills → real; shipwright
  `item_acquired` → `command_executed:+craft` + step reward; misleading npc
  text + dead-end directional hints rewritten.
- **Global `look`/`examine <carried item>`**, **chargen tooltips**.

All 7 chains are now structurally completable. **But there is still no
test that proves a player can walk a chain from a real chargen** — the entire
existing chain test+smoke layer injects state, pre-supplies destination slugs,
or pre-places the player at a slugless room. That coverage gap is THIS
session's primary objective.

Read first (detailed spec lives here):
- Session memory `cw-tutorial-chains-onboarding-break` and
  `chain-coverage-strategy` (in the project memory dir).
- `TODO.json` → `tech_debt` → `TD.ONBOARDING_CHAIN_REACHABILITY_COVERAGE`.
- The drop-24 CHANGELOG entry.

---

## P0 (PRIMARY) — Onboarding reachability coverage net

Two complementary layers. **Coordinate with the parallel smoke-coverage
session** — if it has already started the walkthrough harness, extend its work
rather than duplicating. Check `git log`/`git status` and recent smoke files
before authoring.

### P0.1 — Static reachability invariant (pure-YAML, milliseconds)

New file `tests/test_chain_corpus_reachability_invariant.py`. Loads
`data/worlds/clone_wars/tutorials/chains.yaml` and asserts, for every unlocked
chain (skip `locked: true` stubs):

1. **Step-to-step reachability.** For each adjacent step pair where
   `step[i+1].location != step[i].location`, a reachability seam must exist.
   Today the seam is the inter-step teleport, which requires `step[i+1].location`
   to resolve to a real built room — so assert every step `location` (and the
   chain `starting_room` and `graduation.drop_room`) resolves to a loaded room
   slug. (Reuse the slug-set helpers in `tests/test_f4c_chains_room_references.py`
   / `tests/test_f8b_tutorial_rooms.py`.)
2. **No `room_entered` / `item_acquired` completions** (unreachable / producerless
   in exit-less teleport-only rooms — drop 24 removed them; this pins it). NOTE:
   inline guards already exist in `tests/test_f8c2b_chain_events.py` and
   `tests/test_f8c2b2_chain_events_phase2.py` — consolidate or cross-reference,
   don't duplicate blindly.
3. **Every completion `command:` (and every `requires_first[].command`) resolves
   through the REAL command registry.** This is the guard that would have caught
   the `+factions` blocker. Build the full registry the way the server does
   (`server/game_server.py` ~lines 191-225: `CommandRegistry()` then the
   `register_*` sequence) — factor a small helper or call them in order. Then
   assert `registry.get(cmd)` is not None for each completion command literal.
   (Watch: bare `factions` must NOT be required — only the exact literal in the
   corpus.)
4. **Every `skill:` (and `fallback.skill`) in a `skill_check_passed` completion
   resolves** to a real skill — `engine.character.canonical_skill_key(skill)`
   must be in the `data/skills.yaml` name-set OR the sanctioned
   `engine/skill_checks.py` `_FALLBACK` attr map. (Would have caught
   `starship_repair` / `starship_piloting`.)

Acceptance: the test passes against the current corpus and FAILS if any of the
four classes regress.

### P0.2 — Per-chain walkthrough smoke (runtime truth)

New `tests/smoke/scenarios/chain_walkthrough.py` +
`tests/smoke/test_smoke_chain_walkthrough.py`, parametrized over the 7 unlocked
chains.

First add a harness helper in `tests/harness.py`, e.g.
`async def start_chain(self, name, chain_id) -> _ClientSession`:
- resolve the chain's `starting_room` slug → room id via `room_id_by_slug`;
- `login_as(name, room_id=<that id>)`;
- persist the `select_chain` attrs block (mirror
  `engine.tutorial_chains.select_chain` shape — `{chain_id, step:1,
  started_at, completed_steps:[], completion_state:"active"}` — like the
  `_inject_chain` pattern in `tests/smoke/scenarios/chain_attempt.py`, but
  placing the player in the REAL starting room, not room 1).

Then for each chain, the scenario:
1. `start_chain(...)`.
2. For each step in order, BEFORE attempting completion, **assert the player's
   current room slug == `step.location`** (the reachability gate — this is the
   exact assertion that was failing for bounty_hunter at step 3).
3. Drive the step's completion using ONLY player-issued `cmd()` calls derived
   from the step's `completion`/`teaches`:
   - `command_executed` → type the literal command (`+sheet`, `+factions`,
     `examine <x>`, `say <x>`, `+craft`, …);
   - `talk_to_npc` → `talk <npc>`;
   - `combat_won` → drive combat to victory (reuse the ground-combat smoke
     helpers; the chain enemy templates are real — see
     `npcs_drop_f8c2b2_combat_templates.yaml`);
   - `bounty_accepted` → `+bounties` then accept the tutorial contract;
   - `mission_accepted`/`mission_completed` → accept/complete the tutorial
     mission;
   - `skill_check_passed` → `chain attempt`;
   - `item_used` → `use <item>`.
4. After each completion, reload `get_char` and assert `tutorial_chain.step`
   advanced (or `completion_state == "graduated"` on the last step).
5. At the end assert graduated AND the player is in `graduation.drop_room`.

**HARD RULES (the whole point):** the scenario must NEVER call
`engine.chain_events` hooks directly, NEVER write the next `room_id` itself,
and NEVER inject chain state mid-walk. Movement between steps must come from the
product (the inter-step teleport). If a chain can't be walked by player action,
the scenario FAILS at the reachability gate — which is the bug-catch we want.

Caveats to handle gracefully (skip-with-reason, like `chain_attempt.py` does, on
corpus drift): `skill_check_passed` is RNG — a failed roll is a valid outcome;
loop `chain attempt` a bounded number of times, or seed skills high enough via
`login_as(skills=...)` that the authored difficulties pass reliably. Combat
steps may need the player statted to win — use the harness skill/stat overrides.

Acceptance: all 7 chains walk to graduation green using only player commands.
This is the regression net that makes the drop-24 class un-reshippable.

---

## P1 — Get the full suite to green (2 stale count-pins)

The drop-24 full-suite run (`tests_output.log`) was **8333 passed, 2 failed**.
Both failures are pre-existing stale count-pins from parallel CONTENT drops,
unrelated to drop 24 — fix the pins (or the data if the pin is right):

1. `tests/test_t2_3_coruscant_underworld.py::TestCoruscantUnderworldLoads::test_eight_landmarks_total`
   — drop 18 grew the Coruscant Underworld to 20 landmarks; the test still
   pins 8. Verify the real count and update the pin (the drop-18 CHANGELOG
   claimed "no count-pin flipped" — it did).
2. `tests/test_f7c1_village_trials.py::TestVillageTrialNPCsPlaced::test_total_npc_count_includes_all_seven_village`
   — hardcoded NPC count ("F.7.b shipped 145 → 147"); a later content drop
   moved the count. Verify the real placed-NPC count and update.

Confirm each is a stale pin (real data correct, test number wrong) vs. a real
data regression before editing. One commit, CHANGELOG/TODO updated.

---

## P2 — Non-blocking onboarding polish (from the drop-24 audit)

Independent, each its own small drop. Pick up in order; stop on any design fork.

1. **Tutorial bounty target binding.** `engine/chain_missions.py::_materialize_bounty`
   sets `target_npc_id=None` / `target_room_id=None`; `tutorial_bounties.yaml`
   carries `target_room_slug` which the materializer ignores, so
   `parser/bounty_commands.py::BountyTrackCommand` hard-errors
   ("Contract data error — target NPC not found") on the tutorial Tarko Vinn
   contract. Resolve `target_room_slug` → room id and bind the Tarko Vinn anchor
   NPC (present in `npcs_drop_f8c2a_chain_anchors.yaml`) so `bountytrack` works
   in the tutorial. (The chain itself drives capture via `chain attempt` +
   `combat_won`, so this is quality, not a blocker.)

2. **`examine`/`look` of room objects + NPCs.** Drop 24 made `look`/`examine`
   resolve CARRIED items, but `examine <booth>` / `examine kost` / `examine crate`
   (republic_intelligence s2, smuggler s2, separatist_agent s2) still hit the
   holocron handler's flat "You see nothing special about X" even though the
   `command_executed` completion fires. Extend `ExamineCommand` (and/or
   `LookCommand`) to render a room NPC's `description` and any room-object detail
   when the target is an NPC/object in the room (reuse `match_in_room` —
   `include_npcs=True`). Low risk; improves every examine step's UX.

3. **Web onboarding panel polish** (`static/spa/m3_onboard.js` + the
   `build_onboarding_state` producer in `engine/chain_events.py`): surface the
   step `next_hint` (currently authored but never sent to the web panel —
   thread it into the payload + render a NEXT line under the objective), and
   suppress the misleading chip-per-`teaches`-token for tokens that aren't the
   real trigger (the `scan`/`search` chips). The corpus `teaches` are now mostly
   correct post-drop-24, but verify the panel renders `chain attempt` as the
   actionable chip for `skill_check_passed` steps. Browser pass is Brian's, but
   the producer/JS changes + their unit/smoke coverage are autonomous.

4. **`get`/`take`/`drop` redirect stubs** (optional, low value): these verbs
   don't exist and a new player will type them. A full ground-item system is a
   DESIGN FORK — do NOT build it. A purely-additive friendly-redirect stub
   (`get`/`take` → "items come from examining the world / commissaries";
   `drop` → "use sell/unequip") removes the "Huh?" dead-end. Only do this if
   P0-P3 are done and there's budget; otherwise log and skip.

---

## P3 / stretch — broader launch readiness

Only after P0-P2. Pull the next-highest item from `TODO.json` `tier_1_active` /
the roadmap, applying the standing `implementation_discipline` note (re-examine
the design at implementation time; do not blindly implement). Stop on any fork.

---

## Guardrails (apply to every drop tonight)

- **Verify before claiming.** Grep HEAD at symbol level before asserting any
  symbol/feature exists or is missing. Memory/handoffs/design docs are
  untrusted without verification (the standing phantom-delivery discipline).
- **One drop = one logical change**, with `CHANGELOG.md` + `TODO.json` updated
  in the SAME change (hygiene tests enforce it). Append; don't clobber.
- **Funnels:** credits → `adjust_credits(...,"tag")`; out-of-combat dice →
  `perform_skill_check`; influence → `adjust_territory_influence`. No phantom
  producers/consumers; faucets and sinks land together.
- **Era cleanness (B3):** no Imperial/Empire/Rebel/TIE in production strings.
- **Don't touch the parallel sessions' in-flight files** without checking
  `git status` — combat/items/smoke-coverage work may be live. Do NOT commit
  `node_modules/`, `package.json`, `.pyc`, or `.claude/settings.json` (strays in
  the tree, not gitignored for node_modules — leave them or add a gitignore
  entry as its own tiny change if you touch it at all).
- **Verification fan-out before declaring a drop done:** targeted `test-runner`
  + `invariant-auditor` + `code-reviewer` + `smoke-verifier` (in parallel),
  adjudicate findings, fix, re-verify.
- **Design forks → STOP.** Log to `TODO.json::design_calls_pending_brian` with
  the options and your recommendation; move on to the next P-item. Do not guess
  on novel systems, economy/balance, or invariant-ambiguous changes.
- **Commit + push** each completed, verified drop to `roadmap` (or a
  `drop/<name>` branch). Do NOT merge to `main` — that's Brian's gate on a green
  full suite.

## Definition of done for the night

- P0.1 + P0.2 landed: all 7 chains proven walkable from a real chargen by a
  player-only smoke, plus the static invariant. (This alone is a great night.)
- P1 landed: full suite green (0 failures).
- As many P2 items as budget allows, each independently verified + committed.
- A short end-of-run summary appended here or in a new HANDOFF, listing what
  shipped, what was deferred, and any design forks logged for Brian.
