# SW_MUSH — Unattended Review, Claude Code Era (Fable, 2026-07-02)

Scope: everything since the Claude Code migration — **343 CHANGELOG drops (2026-06-19 → 07-02)** on top of the archived history. Method: full-tree AST/YAML validation, invariant audit (B3/Q1/force_sensitive/funnels/silent-no-op), symbol-level phantom verification of every headline claim I sampled (~25), targeted test batteries (unit slices, 124 jsdom DOM tests, balance guards, 5 smokes), one live break-it investigation with silent-probe instrumentation, and a gameplay/economy read of the two big content lanes. Sandbox = targeted runs only per the standing split; your Windows full suite remains the acceptance gate.

**Verdict:** The Claude Code loop has been *very* good. Discipline held at scale — every invariant I audited is intact across 343 drops, the phantom rate is near zero (one 2-line yaml omission, fixed), the extend-don't-add and faucet+consumer rules were honored even under a 10-drop tunables blitz, and the fiction quality on the questline lane is genuinely strong. I found **one P0-class gameplay bug** (dice-conditioned chain soft-lock, all 40 chains in blast radius — fixed, tested, zipped in this session), a handful of small triage items, and a set of lane-level *design* observations that are exactly the kind of thing per-drop guards can't see. Details below.

---

## 1 · FIXED THIS SESSION — apply the zip

**`SW_MUSH_fable_review_drop_20260702.zip`** → `Expand-Archive -DestinationPath . -Force` from repo root. See `APPLY_CHAIN_COMBAT_WON_README.txt`. Acceptance = your full `run_all_tests.bat`.

### 🔴 Chain `combat_won` credit lost to a straight-to-DEAD finishing blow (P0 class)
The P0.2 walkthrough smoke was **flaky at HEAD**: `chain_walks_to_graduation[republic_soldier]` failed ~2/3 of runs (my 6-run baseline: 2 pass / 4 fail). Silent-probe instrumentation (recording `on_combat_won` + `record_combat_kills`, zero in-run prints) showed the failure signature was *zero or partial hook calls* — the parser end-block ran but collected nothing. Root cause, confirmed against the code's own `_pre_npcs` comment: the F.8.c.2.b block iterated the **live** `combat.combatants` dict, but `resolve_round()` runs `_cleanup()`, which pops any combatant that reached **DEAD** that round. Overshoot the finishing blow to DEAD → foil invisible → credit silently lost. INCAP/MW/stun-KO paths worked, which is exactly why it presented as flake, not solid red.

**Blast radius:** every `combat_won` step — all 7 onboarding chains and all 33 accessible-questline foils. On a single-foil questline step it's a **hard soft-lock** (foil despawned dead, step can never fire). This is the DEAD-side sibling of your same-day anomaly-defeat fix, and the *third* consumer bitten by the `_cleanup` pop — wear/mob-grind/early-CP were already snapshot-fed for this exact reason.

**Fix (pattern-matches the siblings):** collection extracted to pure helper `_collect_defeated_chain_templates(db, _pre_npcs)`, fed the pre-resolution snapshot; semantics otherwise identical (can_act_now defeat predicate incl. the QA-06-20 stun-capture). New 15-test slice incl. a 3-test wiring canary so a revert fails **deterministically**, not one smoke in three. Gate: smoke **6/6** (was 2/6), full 7-chain walkthrough green, 180 adjacent tests green, `engine/combat.py` untouched.

### 🟢 Also in the zip (phantom completion)
`hollow-sun-tuning` advertised `communal.staged_menace_per_minute` / `communal.win_capstone_credits` as tunables but never added the rows — behavior was already correct via `get_tunable` fallback; the *operator lever* was missing. Rows added (0.18 / 1000, code defaults unchanged). Also added the tier-2 row for the hollow-sun deferred follow-up (cistern `alt_skills` persuasion fallback + wave re-engage polish) that the CHANGELOG promised but never logged.

---

## 2 · TRIAGE LIST (nothing here blocks; ordered by my read of severity)

1. **MED — Wilderness map geometry filename mismatch.** `area_loader` skips `coruscant_underworld` and `tatooine_dune_sea` at every boot ("AreaGeometry YAML not found: …/maps/<slug>.yaml") — but `<slug>_overview.yaml` **exists** for both. The art is orphaned; the map navigator has no geometry for two *live* regions (dune_sea anchors anomalies + a force landmark; underworld is where T3.23's first party challenge is slated). Looks like a one-line registry/lookup convention fix.
2. **LOW — Loader-overlap warning noise.** `npcs_drop_mob_grind_coruscant_underworld.yaml` is `wilderness_npcs:`-keyed (correct, has its own loader via `content_refs.wilderness_npcs`) but the generic `npcs:` loader also sweeps it and warns "no 'npcs' key" every boot. Content is fine; silence the generic sweep for that key shape.
3. **LOW — GCW string residue in two engine template dicts.** `engine/territory.py::_GUARD_TEMPLATES` + `engine/contest.py` champion templates + the `_influence_flavor` GCW half still carry `empire`/`rebel`-keyed blocks with "stormtrooper / Imperial crest / Rebel Alliance" player-facing strings. Dormant on a CW server (no org row carries those codes; the rewicker migrates old ones) and consistent with GCW-as-deprecated-reference — but they're the last engine-level GCW *display* strings. Suggest either stripping to comments or a guard test asserting no live org row ever resolves those keys.
4. **LOW — Help-corpus duplicate keys** (`anomalies`, `force`, `salvage`) warn-and-override at boot. Later file wins; verify the winner is the intended one and dedupe.
5. **LOW — Dead spa test locator.** `tests/spa/test_m3_tokens.py` skips one case everywhere: "Could not locate `WoundLevel(IntEnum)` in engine/character.py" — the import works fine, so the source-regex locator is stale; that assertion never runs on any box.
6. **INFO — `communal.menace_per_minute` yaml comment** ("menace gained per real minute active") is now misleading for staged cults; the new row's comment disambiguates, but consider touching the old comment too.

---

## 3 · VERIFIED GOOD (so you don't have to re-check)

- **Invariants across all 343 drops:** B3 era-clean at the hard-token level in every production surface (all hits triaged: era-map keys, `replaces:` metadata, common-noun "crime empire", era-correct "Venator-class Star Destroyer", the fixed world_events rename, plus item 3 above). Q1 clean — canon figures appear only as *place names* (Jabba's Townhouse/Palace = sanctioned institutional framing). `force_sensitive` never a save kwarg/column anywhere. **Zero** kwargs-less `save_character()` no-ops. **Zero** direct credit mutations outside `adjust_credits` (raw d6s found are all encounter/loot *tables*, not skill checks — pre-existing pattern). 1,257 py files AST-clean; 178 yaml clean.
- **Phantom check:** every headline claim I sampled is real at symbol level — fun13/15 commands, G5 producer+consumer, anomaly INCAP gate, hollow-sun constants + `_CAPSTONE_LOOT` (5 era-clean relics, capstone funnel-routed through `adjust_credits` with a ledger tag, ≥10%-share gated), ambient-audio manager, palette/sheet/goals/sit modules, `@balance`, tunables loader, mob-grind, guide-browser API, TYPE-THIS chips, contextual hints. The only phantom found is the tunables-rows one, fixed above. The loop's own "honest framing" habit in changelog entries (calling out what *isn't* a first) is doing real work — I checked several of those claims against the corpus and they hold.
- **Test batteries green here:** the five newest drop slices (36), all-questlines-walkable + newest arc + hygiene (56), all three balance guards incl. the post-fun14 foil band (37 — Bohrus Kang now correctly admitted via the melee-aware path), 124 targeted jsdom DOM tests (palette, living-sheet deltas, goals, situation, scene, onboard chips, onclick exports, sheet), 490 static spa, smokes: foundation, vendor-gate, and post-fix 7/7 walkthrough.
- **T3.19 is genuinely closed**, not checkbox-closed: 13-board `@balance` dashboard reads every sink that shipped; the 10-drop tunables blitz gave each knob a live consumer. Extend-don't-add held under pressure.
- **The QA campaigns were real work** — the 06-19/20 blocker/high sweep, the credit-integrity passes, the adversarial re-run that itself found FP-dup + the −20cr vendor demo. This is the phantom-hunting culture working.

---

## 4 · GAMEPLAY REVIEW (your primary ask)

### 4a · The T3.24 questline lane — 35 arcs in six days
**The fiction is the best thing in this batch.** I read the full racket taxonomy: 35 genuinely *distinct* fraud shapes (false-death bonds, clocked flight-hours, hollow defensive fits, sold competency tickets, faked demil, staged self-raids…), each with real-world texture, victims who feel specific, and villains kept correctly offstage from the war. The skill-spread invariant held perfectly — I extracted the full matrix; every accessible arc's chain-skill pair is unique across the lane (the only reuses are vs the five old master chains, which predate it). Zone spread is reasonable (20 zones, Mos Eisley heaviest at 4+adjacent — the loop's "not a fresh face" honesty flags match reality). DC envelope is consistent (11/13, third checks 14, the earliest arcs slightly easier). `mastery browse` discoverability shipped. Rewards verified uniform: **450 cr + 17 independent rep + cp-3 achievement** per arc.

**Lane-level observations no per-drop guard could see:**

- **Rep saturation.** Rep clamps at ±100 (member 0–100). 17/arc × 35 arcs = 595 nominal, so the rep line-item is **fully dead after ~6 arcs**; mission rep-gates top out at 20–30, cleared even faster. 29 of 35 arcs pay a partially-decorative reward. Not a bug — but if rep is meant to *matter* across the lane, it needs either higher-tier consumers (rep-gated vendor stock? title thresholds at 150/300 nominal-uncapped?) or the lane should openly lean on credits+achievement as the real payout. Cheap option: have the 17 also feed a lane-scoped counter (arcs-cleared) that titles/achievements read, so completionism has a visible ladder.
- **Structural monotony.** Every arc is the same stamp: talk → check → check → shoot-one-guy → talk, same payout, foil pinned to the fresh-char band. The *stories* differentiate; the *play* doesn't, and players will see the template by arc 3–4. Deliberate and sanctioned (breadth-safe widening) — but it means the lane's value is **coverage** (every build has a home arc), not replayability. Which is fine *if* you treat it as done — see the 36th-arc call below.
- **No difficulty ladder.** Fresh-char-winnable everywhere = veteran-trivial everywhere. Combined with the flat 450, there's no reason to run arc #20 except build-flavor. Acceptable for launch; a post-launch "hard remix" tier (same arcs, scaled foil band, 2–3× payout, gated on N clears) would be cheap reuse if `@balance chains` shows completionists blowing through.
- **Aggregate faucet never re-audited.** Lane total = 15,750 cr (+3,500 from the 5 master arcs = 19,250 all-questlines). The economy audit predates 33 of these arcs; add mob-grind (soft-capped), missions, bounties, anomalies, and the new 1,000-cr cult capstone (bounded, ~6h cadence, title-earners only — checked the gating) and the *shape* looks sane, but nobody has summed it since. Recommendation: **don't pre-tune** — you now have `@balance flows/chains/grind` precisely for this; schedule one economy-aggregate pass at launch+2 weeks on real telemetry.
- **The 36th-arc fork (`QUEST.t3_24_36th_arc_skill_pool_exhausted`)** — the loop was right to stop and ask. **My recommendation: wind down at 35** (the loop's own default). The remaining skills are reactive defenses + lightsaber, both of which fight the format; a 36th stamp buys nothing. Spend the next content budget on a **second archetype** instead — and you already own the substrate: the Hollow Sun staged-scenario runtime + T3.23 skill-gate phases. A "staged questline" (multi-stage, party-optional, skill-gate + combat mix) is the natural evolution and dovetails with your pending `EVENT.communal_rework_staged_scenarios` call.

### 4b · Hollow Sun / staged cults
Tuning math checks out: (100−35)/0.18 ≈ **361 min ≈ 6.0h** window, legacy 0.35 path untouched, staged rate applied only when `is_staged`. Capstone is correctly bounded (win-only, ≥10%-share title-earners, funnel-routed, 0-disables) and the relics are era-clean and characterful — all 5 cults covered + a default token. The **anomaly-defeat fix** that made these winnable is real and well-tested (it drives the actual parser seam the old tests skipped — good instinct; my fix this session copies that test's philosophy). The deferred cistern `alt_skills` fallback is now logged (tier-2). One design note: the staged menace being a **one-way** clock makes every uprising a pure race; that's a clean session shape, but if `@balance events` later shows near-100% timeouts off-peak, the lever you want is a small strike-driven *slowdown* (not reduction) — a middle ground between one-way and the legacy push-down.

### 4c · The NPE/fun arc (fun1–16) — this is the sleeper win of the batch
The sequencing shows real product thinking: sim made unkillable-safe → then *winnable* → talk de-LLM'd so Ollama can't hang the chain → bare `accept` auto-take → graduation lands at a vendor with a GOALS handoff → unknown verbs get helpful recovery → then the philosophical capstone: **the words newcomers reflexively type become real commands** (`inventory/inv/i`, `goals`, `situation`, `list`, `presence`), with `list` verified to print the *identical* `vendor_stocked` catalog `buy` sells (no lie between list and buy), and Guide_16 reconciled so the docs stopped teaching the pre-fix world. Plus TYPE-THIS chips, per-character tour, contextual first-hit hints, in-game guide browser. Together this closes the classic MUSH cold-start problem. The FUN2 "combat-feed never renders" item you have pending is flagged as likely misattribution by the loop's probes — my static+DOM pass agrees the wiring exists; I'd close it pending one live look rather than spend a drop on it.

### 4d · Mob grind, tunables, telemetry
Grind trickle is well-shaped (15→3 past the daily soft cap, per-day reset, telemetry'd, tunable). The tunables program is the right kind of boring: 10+ systems externalized, each with a `@balance` reader, zero orphan knobs that I found (post-fix).

### 4e · Your 11 pending design calls — my one-line reads on the ones that matter
- **COMM.comlink scoping:** rebrand as the global IC channel (honest + free) unless you *want* planet-local RP islands; enforcing planet-scope adds code and shrinks a small population's chat. 
- **ENV.hazard no-cure:** wire a cure (medicine check + rest, or a vendor antidote sink). Permanent debuffs on a persistent character age into support tickets.
- **SPACE.anomaly 6/7 unwired + scan advertises dead verb:** this now *violates the no-dead-end doctrine the fun lane just established*. Pre-launch minimum: mute/soften the scan hint for unwired types; wiring `course anomaly` is the real fix but is a lane, not a patch.
- **UX.living_sheet_delta:** keep per-view (loop default is right; session-cumulative turns the sheet into a nag).
- **CP.ai_trickle Director wiring:** leave dormant for launch; revisit when `@balance progress` shows whether CP income needs another faucet at all.
- **FUN2 feed/render:** close as misattribution pending one live glance (above).
- **QUEST 36th arc:** wind down; pivot budget to staged-scenario archetype (above).
- **EVENT.communal_rework:** yes — and fold the questline-lane evolution into the same design pass so you author one "staged content" pattern, not two.

---

## 5 · UI REVIEW

**The web client has crossed a threshold** — it now reads as a game UI, not a telnet wrapper. The panel set (HERE with wound badges + per-NPC verb buttons + clickable names + bounty highlight; GOALS; SIT; PRESENCE/SCENE; living sheet with delta highlights; Ctrl-K palette; guide overlay; per-char tour; TYPE-THIS chips; crafting/shop/bounty/board modals; region/influence) is coherent, and the **producer/consumer discipline held**: every surface I traced has both halves, and the 124 DOM tests I ran confirm render behavior, not just symbol presence. G5's severity buckets (stun/hurt/crit) are exactly the at-a-glance read a multi-mob fight needs. Ambient audio has the correct posture: off-default, gesture-gated (autoplay-policy-proof), fail-silent on missing files, crossfade manager, README documenting the 5 drop-in basenames — all that's missing is your CC0 sourcing call (Kenney.nl + freesound CC0 filters will cover cantina/spaceport/market/deep-space/city in an evening).

**Concerns:**
- **`client.html` is 15.2k lines and still absorbing new features inline** (audio manager, wound badge, palette wiring) while 42 clean `spa/m3_*.js` modules exist. Nothing is broken, but the monolith is where the next regression hides. Suggested *standing rule*, not a rewrite: new client features land as spa modules; queue one extraction pass post-launch under T3.21's umbrella.
- **Two live regions render no map geometry** (triage #1) — dune_sea is where anomalies visibly live, so the wilderness overview is blind exactly where the content is.
- Minor: `here-wound` colors reuse `--warn` for both hurt and crit (crit differentiates by bold only) — one extra CSS var would make crit pop on colorblind-hostile setups.

---

## 6 · SUGGESTED NEXT FIVE DROPS (post-apply, in order)

1. **Map-registry filename fix** for the two `_overview.yaml` regions (+ silence the wilderness_npcs loader warning) — small, restores visible content.
2. **Space-anomaly hint soft-mute** (or the `course anomaly` wiring if you'd rather spend the lane) — closes the last advertised-dead-verb.
3. **Hollow-sun cistern `alt_skills`** (now tier-2-logged) + the wave re-engage polish — completes the flagship scenario.
4. **Design pass: staged-content archetype v1** — one doc unifying communal-rework + the questline lane's next generation; Opus design-reviewer subagent is built for exactly this.
5. **Launch+2wk economy-aggregate pass** driven by `@balance flows/chains/grind/events` — the re-audit item 4a defers.

— Fable. Repo state at review end: my drop applied locally on top of your 2204 zip; everything above verified against that tree. Ping me the full-suite result when you run it.
