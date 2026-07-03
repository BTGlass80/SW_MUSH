# FINDINGS FOR THE CLAUDE CODE LOOP — Fable review, 2026-07-02

**Consumption contract (Brian's call: findings in, loop implements — no cross-agent diffs):**
- The companion `SW_MUSH_fable_review_drop_20260702.zip` is **REFERENCE ONLY — do not apply**. Re-derive every fix at your own HEAD.
- Per phantom discipline: **verify each finding at your HEAD first** (grep the cited symbols, run the cited repros). My tree = Brian's `SW_MUSH_upload_20260702_2204.zip`; if HEAD has moved, re-confirm before writing code.
- Each finding below carries: symptom → evidence → HEAD symbol cites → repro → recommended fix-shape → suggested test slice → invariant notes. Narrative context lives in `REVIEW_FABLE_2026-07-02.md`; this doc is the actionable half.

---

## F1 🔴 P0-class — chain `combat_won` credit silently lost to a straight-to-DEAD finishing blow (all 40 chains)

**Symptom.** `tests/smoke/test_smoke_chain_walkthrough.py::…[republic_soldier]` is **flaky-red at HEAD**: my 6-run baseline = 2 pass / 4 fail; the assert is "step 2 (combat_won) did NOT advance." Dice-conditioned, so full-suite runs can green on luck.

**Evidence (silent-probe).** Wrapping `engine.chain_events.on_combat_won` + `engine.tutorial_chains.record_combat_kills` with a print-free recorder (file-dump at unconfigure — an in-run `print`/`-s` is enough to perturb; keep it silent) yields two failure signatures:
- Fail-A: recorder empty — the hook **never fired** for either droid.
- Fail-B: one `(tally→1, hook, no-adv)` — second droid's defeat never credited.
Pass runs show `1 → 2 → ADV`. So the loss is **upstream of the hook**: the parser end-block's defeated-template collection comes up empty for that kill.

Probe plugin, verbatim (drop at `/tmp/probe2.py`, run with `PYTHONPATH=/tmp:. … -p probe2`):
```python
import functools, json
REC = []
def pytest_configure(config):
    import engine.chain_events as ce
    import engine.tutorial_chains as tc
    real = ce.on_combat_won
    @functools.wraps(real)
    async def rec(db, char, tpl, cnt=1):
        adv = await real(db, char, tpl, cnt)
        REC.append(("hook", tpl, cnt, bool(adv)))
        return adv
    ce.on_combat_won = rec
    real_rk = tc.record_combat_kills
    @functools.wraps(real_rk)
    def rk(attrs, tpl, cnt, skey):
        r = real_rk(attrs, tpl, cnt, skey)
        REC.append(("tally", skey, tpl, cnt, r))
        return r
    tc.record_combat_kills = rk
def pytest_unconfigure(config):
    open("/tmp/probe2.json","w").write(json.dumps(REC))
```

**Root cause (symbol cites — verify each at your HEAD).**
- `parser/combat_commands.py::_try_auto_resolve` — the snapshot's own comment states the mechanism: *"Snapshot NPC combatants BEFORE resolution — `resolve_round()` runs `_cleanup()` which removes dead combatants"* → `_pre_npcs = [...]` → `events = combat.resolve_round()`.
- `engine/combat.py`: `resolve_round()` → `self._cleanup()`; `_cleanup()` builds `[c … if c.char.wound_level == WoundLevel.DEAD]` and `self.remove_combatant(c.id)` (pop) — **DEAD (and fled) leave `combat.combatants` the same round they fall**.
- The F.8.c.2.b chain block (same function, `combat_won completion` comment) collects defeated templates by iterating **`combat.combatants.values()`** — the live, post-pop dict.
- Consequence: finishing blow lands **DEAD (margin ≥16, `engine/character.py::WoundLevel.from_damage_margin`)** → foil popped → invisible → `_defeated_templates` empty → hook skipped → credit lost. INCAP (9–12) / MW (13–15) / stun-KO stay in the dict, hence the flake pattern.
- Three sibling consumers in the *same function* were already snapshot-fed for this exact reason: `_apply_combat_wear`, `_award_mob_grind_rewards`, `_award_early_combat_cp`. The chain block is the odd one out. (Sibling context: this is the DEAD-side twin of your 07-02 `anomaly-defeat-clear`, which fixed the INCAP side of the same cleanup interaction.)

**Blast radius.** Every `combat_won` step: 7 onboarding chains + all 33 accessible-questline foils. **Single-foil questline steps = hard soft-lock** (foil despawned dead, step unfireable). Why existing guards missed it: `test_t5_questline_content`'s walkable test doesn't route kills through the parser end-block, and the 06-20 stun-capture fix adjusted the *predicate* (can_act_now) without touching the *iteration source*.

**Repro.**
```
for i in 1 2 3 4 5 6; do python -m pytest \
  "tests/smoke/test_smoke_chain_walkthrough.py::TestChainWalkthrough::test_chain_walks_to_graduation[republic_soldier]" \
  -m smoke -o addopts= -q ; done        # expect ~1/3 pass pre-fix
```

**Fix-shape (pattern-match the siblings; keep `engine/combat.py` READ-ONLY).**
Extract collection into a pure module-level helper — suggested name `_collect_defeated_chain_templates(db, npc_combatants) -> Counter` — and feed it **`_pre_npcs`** at the call site. Preserve semantics exactly: defeat predicate = `c.char.can_act_now()` False (covers Incap+ **and** the QA-06-20 stun-KO capture — do not regress the Bounty Hunter stun path); skip `is_npc` False / `char` None; `db.get_npc` miss or malformed `ai_config_json` → skip, never raise; return `Counter` of `chain_enemy_template` strings (so the multi-enemy `record_combat_kills` accumulation still receives correct counts, including both-droids-in-one-combat = count 2). Surviving-PC dispatch loop unchanged. Update the block's header comment (it currently only explains the row-availability ordering, not the snapshot requirement).

**Suggested test slice** (`tests/test_chain_combat_won_dead_snapshot_2026_MM_DD.py`, mirror the anomaly test's stub style — MiniDB with just an `npcs` table + a `_StubChar` whose `can_act_now()` implements wound≥Incap ∨ future `unconscious_until`). Cases that closed it for me (15):
1. **THE regression:** DEAD foil in snapshot → counted.
2. Snapshot-independence: helper called with snapshot only, no live-dict object in existence (a live-dict revert cannot pass this shape).
3. Both-droids-one-combat: DEAD + INCAP same template → Counter{tpl:2} (republic_soldier s2 single-end shape).
4–6. Ladder kept: INCAP counted; MW counted; **stun-KO counted** (STUNNED + `unconscious_until` future).
7. Still-active excluded: HEALTHY / STUNNED(no-KO) / WOUNDED → {}.
8–12. Robustness: untagged NPC excluded; ghost id (no row) skipped beside a good one; `is_npc=False` and `char=None` skipped; empty **and** `None` snapshot → {}; malformed `ai_config_json` tolerated.
13–15. **Call-site wiring canary** (source-read the F.8.c.2.b block): helper name + `_pre_npcs` present; old inline scan gone (assert `_defeated_templates` and the old "# Collect defeated…" comment absent from the block); `_pre_npcs = [` still precedes `combat.resolve_round()`.
**Integration gate:** the flaky smoke ×6 (mine went 2/6 → 6/6) + full 7-chain walkthrough + adjacent seam (anomaly-defeat slice, f8c2b/2b2/2b3/2c, combat-dead-hooks, fun2-combat-cp, qa-h8 — 180 green here).

**Invariants:** no schema, no faucet/sink, era-clean, `force_sensitive` untouched, engine/combat.py read-only.

---

## F2 🟠 Design-record correction + pre-staged lever — the fun14 melee-foil acceptance rests on an unimplemented "kite" premise (Bohrus Kang math)

**What fun14 recorded:** "a fresh character wins via the **ranged advantage** (blaster + kite + dodge **while the foil must close**)."

**HEAD reality (cites):**
- `engine/combat.py::CombatInstance.__init__` — `default_range: RangeBand = RangeBand.SHORT` for every pair; per-pair overrides exist but nothing in ground combat sets them for this case.
- No closing cost, no `advance/retreat/withdraw` combat verb (grep negative across combat.py/combat_commands.py). Melee resolves round 1 at SHORT.
- Defense split (combat.py header + resolution): **dodge defends ranged only; melee is opposed vs melee/brawling parry** — which a blaster-build fresh character has not raised (falls to DEX).
- Ladder: `engine/character.py::WoundLevel.from_damage_margin` — ≤3 Stun / ≤8 Wound / ≤12 **Incap** / ≤15 MW / 16+ Dead.
- Bohrus (condemned_hull yaml): STR 3D+1, melee_combat 4D, dodge 3D, vibroaxe (STR+3D+1) ⇒ damage **6D+2 (mean ≈22.7)**.

**The math for the archetypal fresh blaster build** (DEX 3D, STR 3D, blaster ~4D, parries unraised): his 4D opposed vs their ~3D parry lands often; a landed swing's mean margin vs STR 3D ≈ **+12 → Incapacitated, brushing Mortal on above-mean rolls, Dead within reach at 16+**. Meanwhile the PC's pistol (4D vs his STR 3D+1) averages margin ≈ +2.3 → Stun/low-Wound, needing many landed hits against dodge 3D. Net: **he needs one swing; they need a fight** — the opposite of the recorded rationale. The yaml's own retained `⚠ BALANCE FLAG` anticipated exactly this.

**Recommendation (not a revert — a correction + instrument):**
1. Docs-side: amend the fun14 CHANGELOG rationale (the *stat-band* acceptance stands; the *kite* justification doesn't exist in the engine).
2. Pre-stage the one-liner the yaml flag promises — but note **vibroblade is a useless swap** (STR+3D ⇒ 6D+1, same Incap-per-hit); the meaningful one-liner is **`blaster_pistol`** (4D damage *and* moves him onto dodge-defensible ranged). Park it, don't fire it.
3. Decide on telemetry: `@balance chains` — if condemned_hull's start→complete funnel lags its 34 siblings materially, fire the one-liner. (If melee foils are wanted as a *class* later, the real feature is a range-band verb — separate design, don't smuggle it in here.)

---

## F3 🟡 CHANGELOG phantom — fun15 advertises `situation (alias sit)`; the alias was deliberately dropped

**HEAD truth:** `parser/builtin_commands.py` (SituationCommand vicinity, ~L5227) carries the comment *"No 'sit' alias: it introduced a new prefix-collision…"*; `sit` is owned by **join** (`parser/places_commands.py`, `aliases = ["sit"]`), confirmed via the live registry (`sit → join`). Code is right and self-documented; **the fun15 CHANGELOG entry is the over-claim** (inverted-narrative micro-case). Guide_16 and `data/help/commands/situation.md` did **not** copy it — drift is one entry.
**Fix-shape:** one-line CHANGELOG correction on the fun15 entry. Optional 2-line canary in the fun15 slice: `reg.get("sit").key == "join"` + the no-alias comment present, so the deliberate collision-avoidance can't silently regress either direction.

---

## F4 🟡 Two live regions boot with no map geometry — `*_overview.yaml` orphaned by a filename-convention mismatch

**Symptom (every boot, incl. smoke setup):** `[area_loader] registry: skipping coruscant_underworld … AreaGeometry YAML not found: data/worlds/clone_wars/maps/coruscant_underworld.yaml` (same for `tatooine_dune_sea`).
**HEAD truth:** `maps/coruscant_underworld_overview.yaml` and `maps/tatooine_dune_sea_overview.yaml` **exist** — the loader (`engine/area_loader.py`, registry load path ~L787) resolves `maps/<slug>.yaml` bare. Both regions are *live*: dune_sea anchors wilderness anomalies + a force landmark; underworld hosts the mob-grind wilderness batch and is the T3.23 first-party-challenge candidate. The overview art is dead weight until the lookup and the filenames agree.
**Fix-shape:** pick one convention — either the registry entry/lookup tries `<slug>_overview.yaml` for wilderness-overview areas, or rename the two files. Add a boot-parity guard: every area the registry declares must load (assert zero `skipping … load failure` for declared slugs), so the next mismatch is red, not a warning.

---

## F5 🟢 Land these two bookkeeping items (I did them in the reference zip; re-land at your HEAD)

**(a) hollow-sun tunables rows** — the 07-02 entry advertises both keys; neither is in `data/tunables.yaml` (behavior fine via `get_tunable` fallback; the *operator lever* is missing). Rows, comment-style-matched, after `communal.title_share_threshold`:
```yaml
communal.staged_menace_per_minute: 0.18  # STAGED cults' one-way failure clock (~6h window; hollow-sun-tuning 2026-07-02). Legacy strike-path cults keep communal.menace_per_minute.
communal.win_capstone_credits: 1000      # headline-rout WIN capstone paid to every title-earner (0 disables; hollow-sun-tuning 2026-07-02)
```
While there: the `communal.menace_per_minute` comment ("menace gained per real minute active") is now staged-misleading — touch it.
**(b) un-logged deferral** — the same entry defers "wire the persuasion/con turn-the-farmers fallback into `hollow_sun_cistern_slice` (alt_skills add) + wave-to-wave re-engage polish" with **no TODO row**. Add `EVENT.hollow_sun_cistern_alt_skills` to `tier_2_queued` (T3.23 phase-1 `alt_skills` substrate already exists — this is per-template data, not engine).

---

## F6 Minors (batchable)

1. **Loader-overlap warning:** `npcs_drop_mob_grind_coruscant_underworld.yaml` is `wilderness_npcs:`-keyed (correct, own loader via `content_refs.wilderness_npcs`) but the generic `npcs:` sweep warns "no 'npcs' key" every boot — teach the generic loader to skip that key shape silently.
2. **Help dup keys** `anomalies` / `force` / `salvage` warn-and-override at boot (`engine/help_loader.py:290`) — confirm the later-file winner is intended; dedupe.
3. **Dead spa locator:** `tests/spa/test_m3_tokens.py` skips one case on every box — "Could not locate WoundLevel(IntEnum) in engine/character.py" though the class is there; the source-regex is stale, so that assertion never runs anywhere.
4. **GCW display-string residue** (dormant): `engine/territory.py::_GUARD_TEMPLATES['empire'/'rebel']`, `engine/contest.py` champion twins, `_influence_flavor` GCW half — unreachable on CW (no org rows carry those codes; rewicker migrates) but they're the last engine-level GCW *player-facing* strings. Either strip to comments or add a guard asserting no live org row resolves those keys.
5. **UI micro:** `.here-wound-hurt` and `-crit` share `--warn` (crit differs by bold only) — one extra var helps colorblind setups.

---

## APPENDIX A — Credit-funnel ledger (baseline for the launch+2wk `@balance flows` pass)

Method: AST-walk of every `adjust_credits(` call in engine/parser/server (**108 sites, 84 distinct tags**, zero funnel bypasses found tree-wide). "Dynamic" tags all resolved to module constants / pass-through params (`DEN_SETUP_SOURCE`/`_REFUND_SOURCE`, hunting `CREDIT_TAG` = the grind tag, pc-bounty helper `source`, space-anomaly `spec["tag"]`, gear_insurance constants) — **no untagged flows**; `@balance flows` bucketing is sound.

**FAUCETS (player income) — 31 tags** *(sign-corrected by hand where the refund/payout word-order fooled the heuristic)*:
`chain_reward · chain_step_reward · tutorial_reward · bounty` (NPC-collect, also the combat kill award) `· bh_bounty_payout · mission · smuggling · grind (CREDIT_TAG, soft-capped 15→3/day) · wilderness_anomaly_reward · space_anomaly_reward · space_encounter_reward · space_salvage · boarding_reward · space_hunter_bounty (DSP-hunter defeat) · communal_win_capstone · item_sale · commissary_sellback · vendor_buy_order_payout · vendor_escrow_collect · org_stipend · harvest · entertainer · sabacc (net win) · theft_gain · intel_handover · npc_pirate_bounty · corpse_credit_return` + refunds (`bacta_tank_ · bounty_expire_ · commissary_purchase_ · home_prestige_ · housing_ · housing_deposit_ · ship_purchase_ · ship_repair_ · shopfront_ · vanity_title_ · vendor_buy_order_ · den_setup_`).

**SINKS (52-deep — structurally healthy; the launch pass should tune faucet *rates*, not add sinks):**
housing family (purchase/upgrade/rent/rename/deposit/prestige/shopfront) · vendor-droid family (deploy/upgrade/purchase/relist_fee/buy_order_escrow) · commissary/resource_vendor/trade_goods/ground_weapon_purchase · ship family (purchase/refuel/repair/docking_fee/spacer_quest_ship) · fines & predation (smuggling/space/patrol/npc_boarding fines, pirate extortion ×2, hazard_theft, theft_loss, space_hunter_settlement) · bh_insurance (pay/hit/hit_partial) + bh_guild_treasury_sink · schematic_tuition · medical/bacta_tank/repair · crew_wage · debt_payment · p2p_transfer+p2p_tax · city_tax · player_building_construct · vanity_title · sabacc_rake · den setup.

**Notes for the pass:** (i) `bounty` tag is shared by two faucet call-sites (bounty_commands collect + combat_commands kill-award) — fine, but if you ever want kill-vs-collect split in flows, fork the tag then. (ii) Questline-lane aggregate = **15,750 cr** (35×450) + 3,500 master-arc = 19,250 all-questlines; one-shot per character, so it's a *stock*, not a rate — read it against the repeatable rates (grind cap, mission/bounty boards, capstone ~1k/6h-shared) when tuning.

---

## APPENDIX B — Natural-verb ground truth at HEAD (supersedes the stale list inside `FUN.shop_verb_and_natural_verb_surface`)

Probed via the canonical builder the guards use: `tests/test_t321_admin_command_access_invariant.py::_build_full_registry()` (≥300 commands). Guard any fix drop against this seam.

**Now resolve (post fun13/15 — the design call's list is partly stale):** `inventory/inv/i → +inv · goals · situation · presence → +who · list · who/online · quests → +quests · missions → +missions · where → +where · browse · market · buy/sell · shop · train/learn · help`.

**Still dead at HEAD (→ helpful-recovery):** `attributes · +attributes · attr · stats · sheet` (bare; **`+sheet` exists** — inconsistent with the fun13 bare-reflex philosophy) `· skills · +skills · equipment · +equipment · gear` (noun; **`equip` the verb exists** — a noun/verb trap for newcomers) `· objectives/objective · exits · +exits · map · +map · store`.

**Semantic traps to resolve in the same drop:** `shop` = "Manage your **vendor droid** player shop" (usage `shop <sub-command>`), not "browse a store" — the design call's core question stands; `sit → join` (deliberate, F3) will surprise a tutorial player reaching for the situation board; `browse` targets player vendor-droids, not the in-room vendor NPC (`list` covers that half — decide whether they merge).

**Fix-shape when Brian rules on the design call:** alias the dead bare-reflexes to their + canonicals exactly per the fun13 pattern (`sheet→+sheet`, `skills`, `attributes`, `equipment` as a *show* command, `exits`, `objectives→goals?`, `map→` the map modal opener if a text form exists), collision-check each against `reg.collision_signatures` first (that's how `sit` was rightly rejected), and extend the fun15 slice with the matrix above as a table-driven guard.

---

## APPENDIX C — Design-call one-liners (carried from the review so this doc stands alone)

`QUEST.t3_24_36th`: wind down at 35; next content budget → a **staged-questline archetype** on the Hollow-Sun/T3.23 substrate (unify with `EVENT.communal_rework` in one design pass). · `SPACE.anomaly 6/7 unwired`: pre-launch minimum = soften the scan hint that advertises the dead `course anomaly` verb (violates the fun-lane no-dead-end doctrine); wiring is a lane. · `COMM.comlink`: rebrand global unless planet-islands are *wanted*. · `ENV.hazard_no_cure`: wire a cure (medicine+rest or antidote sink). · `UX.living_sheet_delta`: keep per-view. · `CP.ai_trickle`: stay dormant; revisit on `@balance progress`. · `FUN2.feed_render`: close as misattribution pending one live glance. · Rep-saturation note for any lane tuning: 17/arc pins the ±100 clamp by ~arc 6; if lane rep should *matter*, add higher-tier consumers or a lane-scoped clears-counter for titles.

— Fable. Everything above verified against the 2026-07-02 22:04 tree; re-verify at your HEAD before implementing.
