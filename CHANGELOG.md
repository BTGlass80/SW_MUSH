# CHANGELOG

Machine-friendly drop ledger for SW_MUSH. One entry per delivered
drop. Companion to `TODO.json` (forward-looking) and
`sw_d6_mush_architecture_v51.md` (narrative ground truth).

**Update discipline:** Append an entry at the end of every drop,
alongside `TODO.json`. Architecture revisions roll up multiple
entries into their `§1.4 What landed since` section.

Format per entry:

```
### YYYY-MM-DD — <drop name>
- **Wave:** <wave name if part of a series>
- **Files:** <comma-separated paths>
- **Tests:** +N (or rewritten) — <test_module>
- **What it shipped:** <one or two sentences>
- **Handoff:** <handoff filename if any>
```

Entries are reverse-chronological (most recent first).

---

## 2026-06-04 — E2: wire the dormant world-event PASSIVE effects (+ phantom repair)

- **Wave:** Audit remediation (post-Drop 3). Rolled up with E1 in the same combined zip. Wires the *passive* subset of the dormant world-event `mechanical_effects` to their existing faucets (the proven `get_effect()` pattern), and **repairs a phantom**: `patrol_spawn_mult` was never actually consumed.
- **Scope decision:** E2 = only the **passive** effects (scale/modify an existing mechanic at an existing faucet, **no new player interaction**). The 6 **flag** effects each *enable a new interaction* and need a design decision, so per the design/implementation-separation discipline they were split out to a design pass (`T2.E3.flag_event_interactions_design`): `contraband_scan`, `rare_vendor`, `hutt_auction`/`criminal_rep_gate`, `krayt_bounty`, `brawl_active`, `distress_active`.
- **Wired (authoritative effect keys from `EVENT_DEFS`):**
  - `bounty_reward_mult` (BOUNTY_SURGE, ×2) → `parser/bounty_commands.py`: read `get_effect("bounty_reward_mult", 1.0)` and scale `reward` **before** the metered `adjust_credits(..., "bounty")` payout; surfaces a "bounty surge … pays N credits extra" line. No-op (1.0) when inactive.
  - `pirate_spawn_mult` (PIRATE_SURGE, ×3) **and** `patrol_spawn_mult` (SECURITY_CRACKDOWN, ×2) → `engine/npc_space_traffic.py::_pick_archetype` spawn weighting.
  - `perception_penalty` (SANDSTORM, −3 pips = −1D) → `engine/skill_checks.py::perform_skill_check`, folded into the central pip-modifier slot but **guarded to the observation-skill family** `{perception, search}` (new `_ENV_PERCEPTION_SKILLS`) so it never touches the many social skills that merely fall back to the PERCEPTION attribute. No-op (default 0) when inactive — transparent to the suite and to every non-observation check; the only path here that reaches the world-event singleton.
- **PHANTOM REPAIRED (`patrol_spawn_mult`):** `npc_space_traffic.py` had **two** `_pick_archetype` definitions — a world-event-aware one **shadowed** by a later `_pick_archetype(exclude_hunter=True)` (the one `_spawn` actually calls). So `patrol_spawn_mult` (long claimed "live") had **never** been consumed at runtime, and no test caught it (the E1 test only asserts the effect is *declared* on the event). Fix: deleted the dead duplicate and consolidated **both** multipliers into the live definition (each `max(0, int(weight*mult))`, with a `total<=0 → TRADER` guard). Proven live by consumption tests — patrol share **0.158→0.298** under SECURITY_CRACKDOWN, pirate **0.173→0.378** under PIRATE_SURGE.
- **Bookkeeping in the same drop:** Director LLM event vocab `EVENT_TYPES` += `intelligence_thaw`, `spice_demand` (closes `TD.DIRECTOR_EVENT_VOCAB_GAP` — they previously only auto-fired on the timer). Live "Jabba" Q1 named-figure strings cleaned → `HUTT_AUCTION` announce ("A Hutt kajidic is running an auction") and `_ZONE_DISPLAY_NAMES["jabba"]` ("the Hutt quarter").
- **Files:** `engine/world_events.py`, `engine/skill_checks.py`, `engine/npc_space_traffic.py`, `engine/director.py`, `parser/bounty_commands.py`, `tests/test_e2_dormant_effects.py` (NEW).
- **Tests:** +9 — `tests/test_e2_dormant_effects.py` (DB-free; a `clean_events` fixture snapshots/clears/restores the world-event singleton and injects `ActiveEvent` directly to bypass `activate_event`'s global cooldown). **Consumption** tests (pirate skew, patrol skew, sandstorm drops the observation pool 5D→4D, sandstorm no-op on a non-observation skill, no-event no-op) + **structural** pins (exactly one `_pick_archetype` def — shadow regression guard; `bounty_reward_mult` read precedes the payout; Director vocab has the two new events; no "Jabba" in any EventDef string or zone-display value).
- **Regression (sandbox, changed modules):** no E2-caused failures; `test_srb3_combined_action` (the lead-bonus suite that shares the exact `perform_skill_check` block edited here) **passes**. **Two PRE-EXISTING / ENVIRONMENTAL failures observed and confirmed NOT caused by E2:** `test_skill_checks_unit::TestResolveMissionCompletion::test_partial_success_pays_fraction` (a stale test — `MISSION_SKILL_MAP["investigation"]` fraction has drifted to `0.40`; **proven to fail identically on reverted, baseline-equivalent code**), and `test_srb2_morale_aura` (37 failures — a DB+asyncio harness that can't run in the bare sandbox, like the aiohttp-dependent `test_singleton_bindings`). Both are for the Windows ground-truth run to confirm.
- **Smoke (Windows):** the `perform_skill_check` change is the one touch to a high-blast-radius central function — trigger/admin-activate `sandstorm` and confirm a `search`/`perception` check drops by 1D while a `blaster`/social check is unchanged; activate `bounty_surge` and collect a bounty (payout ×2 + surge line); activate `pirate_surge`/`security_crackdown` and confirm traffic skews.
- **Handoff:** `HANDOFF_e2_dormant_effects_2026-06-04.md`

---

## 2026-06-04 — E1: B3 era-cleanness + milestone repair of the Director / world-event / room-state narrative layer

- **Wave:** Audit remediation (post-Drop 3). Self-contained era-cleanness drop; surfaced while scoping the "wire the holidays" aside from the dens handoff. Closes a **live B3 era-cleanness leak** in the `clone_wars` production era that the partial F3/F14 era-migration never reached — the Director/event/room-state narrative layer broadcast GCW content ("Imperial / Stormtrooper / Rebel / The Empire"), and the era-milestone feature was silently inert in CW.
- **The finding (symbol-level):** (1) `engine/world_events.py` defined three GCW events — `IMPERIAL_CRACKDOWN`, `IMPERIAL_CHECKPOINT`, `REBEL_PROPAGANDA` — whose `name`/`announce_text`/`expire_text` broadcast GCW strings; the world-event manager `tick()` fires **all** `EVENT_DEFS` with no era gate, so they auto-fired in CW. (2) `engine/director.py::ERA_MILESTONES` was keyed on GCW factions (`imperial`/`rebel`/`criminal`) while `_compute_faction_averages()` keys on the live `VALID_FACTIONS` (`republic`/`cis`/`hutt_cartel`/…) — so `avgs.get("imperial")` was always 0: the six above-threshold milestones could **never** fire, and the one below-threshold milestone (`imperial_retreat`, avg < 30) fired **spuriously on the first faction turn**, posting "Imperial forces withdraw…" to the news/director log. (3) `engine/room_states.py::STATE_DESCRIPTIONS` carried GCW overlay text shown on `look`.
- **Fix (per Brian's option A):** era-clean the player-facing layer + repair the broken milestone feature; **defer** the deeper internal faction-model re-key (seam below). Clean enum **rename** (not a string re-skin) — every reference site was being touched anyway, the blast radius was fully contained (no test and no other subsystem referenced the three event symbols), and fresh CW milestone code should not reference GCW tokens.
  - **Events:** `IMPERIAL_CRACKDOWN → SECURITY_CRACKDOWN`, `IMPERIAL_CHECKPOINT → SECURITY_CHECKPOINT`, `REBEL_PROPAGANDA → SEPARATIST_AGITATION`; all three EventDefs re-skinned CW-clean ("Security forces flooding…", "A security checkpoint…", "Separatist agitprop / pro-Confederacy…"). Mechanical effects **preserved** (`smuggling_pay_mult`/`patrol_spawn_mult` on the crackdown, `contraband_scan` on the checkpoint); the dormant `rebel_influence_tick` effect → `cis_influence_tick`.
  - **Milestones:** `ERA_MILESTONES` replaced with 7 CW milestones keyed to `republic`/`cis`/`hutt_cartel` (republic_ascendant ≥60, republic_martial_footing ≥75, separatist_surge ≥40, separatist_offensive ≥55, cartels_profit ≥65, underworld_dominion ≥80, power_vacuum < 12) — verified every faction key ∈ `VALID_FACTIONS` (so they can actually fire) and every `evt_type` ∈ `VALID_EVENT_TYPES`. Below-threshold special-case `imperial_retreat → power_vacuum`. The Director event-vocab (`EVENT_TYPES`), the event→room-state map (`_EVENT_TO_STATE`), and the security-overlay special-case (`_apply_security_overlays`) all moved to the renamed CW values.
  - **Room states:** `imperial_crackdown → security_crackdown`, `rebel_propaganda → separatist_agitation`, `imperial_control → republic_control`, `rebel_presence → cis_presence`; all four texts re-skinned CW-clean (clone troopers / Grand Army of the Republic / Confederacy / CIS).
  - **Deprecated GCW config kept consistent:** `data/worlds/gcw/director_config.yaml` 2× `narrative_event_type: imperial_crackdown → security_crackdown` (the event *value* is era-agnostic; GCW headlines stay GCW-themed, which is correct for the deprecated era).
- **Files:** `engine/world_events.py`, `engine/room_states.py`, `engine/director.py`, `data/worlds/gcw/director_config.yaml`, `tests/test_e1_event_era_cleanness.py` (NEW).
- **Tests:** +11 — `tests/test_e1_event_era_cleanness.py` (DB-free): word-boundaried B3 forbidden-token scan over **all** EventDef strings + all room-state text + all milestone headlines; enum-rename pins (new present / old absent / values); effect-preservation + dormant-key rename; milestone faction keys ∈ live `VALID_FACTIONS`; milestone evt_types ∈ `VALID_EVENT_TYPES`; below-threshold special-case key present in table **and** wired in source; director/world_events source free of the three legacy event-value tokens. In-sandbox regression check of the changed modules' existing suites: **112 passed** (incl. `test_f6a3_int_byte_equivalence` — GCW emergency-fallback baselines untouched — and `test_a3_intelligence_thaw`/`test_a5_spice_demand`). Full ~4,100+ pytest run is Brian's Windows ground truth.
- **Deferred (recorded seam — TODO `tech_debt` `TD.DIRECTOR_FACTION_MODEL_GCW`):** the Director's **internal** faction model is still GCW-keyed and is a separate, larger drop — `ZoneState.imperial/rebel/criminal/independent` fields (+ `get_faction`'s `getattr` reliance), `AlertLevel.compute_alert` thresholds, `compile_digest()` reporting GCW faction fields to the LLM, `ActionDigest` default dict keys, the GCW influence-adjustment special-cases, and `VALID_FACTION_CODES` (`empire`/`rebel`/`hutt`/`bh_guild`) gating the LLM's faction-orders. LLM-context/internal only (no player-facing string leak); needs a GCW→CW faction-mapping decision. The emergency-fallback baselines stay (intentionally GCW-byte-equivalent for the flag-off legacy path; pinned by `test_f6a3_int_byte_equivalence`). Also logged: `TD.DIRECTOR_EVENT_VOCAB_GAP` (Director vocab missing `intelligence_thaw`/`spice_demand`) and `TD.HUTT_AUCTION_Q1_JABBA` (Q1 canon-name in HUTT_AUCTION flavor — not a B3 issue), both to fold into E2.
- **Handoff:** `HANDOFF_e1_event_era_cleanness_2026-06-04.md`

---

## 2026-06-04 — Drop 3 A5 (centerpiece): sabacc dens — the criminal-empire loop

- **Wave:** Audit remediation / Drop 3 (aspirational economy). Rolled up with B4 + A8 + A3 + the A5 SPICE_DEMAND event (same combined zip). This **closes A5**: the deferred centerpiece from the SPICE_DEMAND entry below — "operate a sabacc den in a claimed room so the house cut flows to the org treasury as `sabacc_rake` (audit F15)" — is now delivered.
- **Design call (per Brian's ruling):** extending ownership into the city was ruled out, so dens use a **dedicated per-room marker**, NOT the wilderness/region or zone-territory ownership models. A Hutt-cartel member of rank ≥3 establishes a den in a cantina with `+den establish` (a one-time 10,000-credit setup-cost **sink**, `sabacc_den_setup`); one den per room; `+den abandon` closes it (no refund). Self-contained, one-row lookup, no dependence on the mid-migration territory model.
- **Rake model (F15 fix, non-inflationary):** while a room is a den, the sabacc house rake (after the existing city-tax slice) routes to the operating cartel org's treasury via `adjust_org_treasury`, and is logged as a `sabacc_rake` **system-faucet** ledger entry (`adjust_credits(0, …)`) so it's visible on `@economy` (fixes F15: the rake was previously notional + unlogged). The player's net win is unchanged. In a public (non-den) cantina the rake stays the house edge baked into net_win, as before — there are no real credits to log there.
- **Files:** `db/database.py` — `SCHEMA_VERSION` 39→40 + migration v40 (`sabacc_dens` table: `room_id` PK, `org_id`, `org_code`, `established_by`, `established_at`). `engine/dens.py` (NEW) — `HUTT_ORG_CODE`/`DEN_ESTABLISH_MIN_RANK`/`DEN_SETUP_COST` + pure `check_den_eligibility` + DB helpers `get_room_den`/`get_org_dens`/`_is_cantina_room` + `establish_den` (gated, debits the sink, writes the row, refunds on write-failure) + `abandon_den` (gated delete). `parser/den_commands.py` (NEW) — `+den` / `establish` / `abandon`, registered in `server/game_server.py`. `parser/sabacc_commands.py` — win-branch den lookup + treasury routing + `sabacc_rake` system-faucet log + den note in the result line (additive; the player credit flow is untouched).
- **Tests:** +18 — `tests/test_a5_dens.py`: the pure `check_den_eligibility` (ok + every refusal reason: not_cantina / not_member / rank / already_den / insufficient); `establish_den` + `abandon_den` against a FakeDB (happy path debits the setup sink + writes; each refusal spends nothing; write-failure refunds; abandon gating); the v40 `sabacc_dens` table + `get_room_den`/`get_org_dens` on a real in-memory DB (via the real migration SQL); structural pins that sabacc routes the den rake (org treasury + `sabacc_rake` tag) and that `+den` is registered + the v40 migration exists.
- **Also fixed:** the B4 structural test (`tests/test_gear_insurance.py::TestStructural::test_v39_migration_adds_gear_insured`) pinned the literal `SCHEMA_VERSION = 39`, which this drop's v40 bump correctly invalidated; it now asserts the v39 migration block + the `gear_insured` ALTER are intact and that `SCHEMA_VERSION >= 39` (version-robust against future bumps). Test-only change.
- **Handoff:** `HANDOFF_drop_b4_a8_a3_a5_dens_rollup_2026-06-04.md`

---


- **Wave:** Audit remediation / Drop 3 (aspirational economy). Rolled up with B4 + A8 + A3 (same combined zip). **Partial A5:** ships the self-contained Hutt/criminal playstyle "holiday" — the `SPICE_DEMAND` world event (report A5's named event) — and, as a necessary side-effect, makes the `smuggling_pay_mult` effect **live for the first time**. A5's centerpiece (route the sabacc den rake to a controlling Hutt-org treasury — the "criminal empire" loop) is **deferred** (see below).
- **Files:** `engine/world_events.py` — new `EventType.SPICE_DEMAND` + an era-clean `EventDef` (global, 30-min, `timer_probability` 1/6h, `mechanical_effects={"smuggling_pay_mult": 2.0}`); auto-fires (`tick()` iterates `EVENT_DEFS`) and is Director-activatable. `engine/smuggling.py` — `SMUGGLING_DEMAND_EFFECT_KEY` + pure `apply_smuggling_demand(reward, mult) -> (new_reward, bonus)` (no-op ≤1.0, garbage-safe, rounds). `parser/smuggling_commands.py` — the delivery-payout site now reads `get_effect("smuggling_pay_mult", 1.0)` and applies `apply_smuggling_demand` to the reward **before** the `adjust_credits(..., "smuggling")` ledger call, surfacing a "spice is in high demand … paid Ncr extra" line when boosted. **This is the first live consumer of `smuggling_pay_mult`** — the key was previously **dormant** (declared on the legacy Imperial-crackdown event def but read by no consumer); activating it is a latent-bug fix as well as the SPICE_DEMAND hook.
- **Tests:** +10 — `tests/test_a5_spice_demand.py` (all DB-free): the event definition (enum + `EVENT_DEFS` + `smuggling_pay_mult` 2.0 + global); a fresh `WorldEventManager` activating it and exposing the multiplier (and the no-event default being neutral); the pure `apply_smuggling_demand` (doubles + bonus / no-op ≤1.0 / garbage-safe / rounds); structural pins that the smuggling payout reads the effect + applies the helper + still routes through the `smuggling` ledger tag; a B3 era-cleanness pin on the new strings.
- **Faucet note:** SPICE_DEMAND is a bounded, temporary, opt-in boost on the already-ledger-metered `smuggling` faucet (visible on `@economy` under `smuggling`), so it adds no farmable pressure. Thematically the Hutt holiday (the kajidic's product — spice — in demand lifts the whole smuggling supply chain); the report's separate smuggler holiday (`CRACKDOWN`, heat/risk-flavoured) is a different, not-yet-built event.
- **Deferred — A5 centerpiece (recorded for its own focused drop):** "operate a sabacc den in a claimed room so the house cut flows to the org treasury as `sabacc_rake`." Blocked on a clean **cantina/den room → controlling-org lookup**: the current region-ownership model (`region_ownership` keyed by `region_slug`, `get_region_owner`) is **wilderness-only**, and cantina rooms (where sabacc is played, `parser/sabacc_commands.py`) have no region/owner; the legacy per-room `is_room_claimed_by` is a deprecated *check*, not a lookup, and the model is mid-migration (SYN.1.b). The sabacc rake (`HOUSE_CUT=0.10`, `parser/sabacc_commands.py:250`) is currently notional on a win (the player just nets less; only the pre-existing city-tax slice is a real movement), so making it a real, routed, logged `sabacc_rake` flow requires first establishing how an org *controls a den room*. That design (den establishment + ownership marker, or extending the region model to city rooms) + the routing is its own drop. **Open question for Brian recorded in TODO.json.**
- **Handoff:** `HANDOFF_drop_b4_a8_a3_a5_rollup_2026-06-04.md`

---


- **Wave:** Audit remediation / Drop 3 (aspirational economy). Rolled up with B4 (re-apply) + A8 (same combined zip). **A3's core was already delivered** by SYN.5 (`engine/intel_handlers.py::handover_intel`): a faction-gated handler NPC (`is_intel_handler`) buys a sealed intel report for **credits + influence**, priced by quality via `evaluate_intel_quality` (which already factors **freshness/recency** and region/actionability), consumes the report, and routes the credit award through the ledger (tag `intel_handover`); it's wired into `+intel handover` (`parser/espionage_commands.py:471`). This drop adds the **genuinely-undelivered** A3 piece: the spy playstyle's **"holiday"** — the `INTELLIGENCE_THAW` world event that doubles the intel **credit** payout while active (parallel to `BOUNTY_SURGE`→hunters 2×, `CANTINA_BRAWL`→entertainers 2×; report line 246's "wire each playstyle to its holiday").
- **Files:** `engine/world_events.py` — new `EventType.INTELLIGENCE_THAW` + an era-clean `EventDef` (global, 30-min, `timer_probability` 1/6h like Bounty Surge, `mechanical_effects={"intel_pay_mult": 2.0}`); since the timer fallback `tick()` iterates `EVENT_DEFS.items()`, the event auto-fires on its probability when Director mode is off and is Director-activatable when on — **no extra wiring**. `engine/intel_handlers.py` — new `INTEL_THAW_EFFECT_KEY = "intel_pay_mult"` + pure `apply_intel_thaw(credits, mult)` (no-op at/below 1.0, garbage-safe, rounds); `handover_intel` gains an injectable `pay_mult` param (defaults to the live `get_effect("intel_pay_mult", 1.0)`, read defensively) applied to the sampled **credits** and surfaces a "(Intelligence Thaw: double rates!)" note. **Influence is deliberately left unscaled** — multiplying influence would distort the territory-contest system; the thaw is an income opportunity, never a territory lever.
- **Tests:** +12 — `tests/test_a3_intelligence_thaw.py` (all DB-free): the event definition (enum + `EVENT_DEFS` + `intel_pay_mult` 2.0 + global zones); a fresh `WorldEventManager` activating the event and exposing the multiplier via `get_effect` (and the no-event default being neutral); the pure `apply_intel_thaw` (doubles / no-op ≤1.0 / garbage-safe / rounds); structural pins that `handover_intel` reads the effect + takes `pay_mult` + applies `apply_intel_thaw` to credits + surfaces the bonus + leaves influence unscaled; and a B3 era-cleanness pin on the new announce/expire strings (no Empire/Imperial/Rebel/stormtrooper/TIE/X-wing).
- **Tunables / faucet note:** `intel_pay_mult` (2.0) in the EventDef; the base tiers stay in `intel_handlers.py` (`INTEL_QUALITY_LOW/MEDIUM/HIGH`). The thaw is a bounded, temporary, opt-in faucet boost on an already-quality-gated, report-consuming, ledger-metered loop (intel income shows on `@economy` under `intel_handover`), so it adds no farmable pressure.
- **Deferred (recorded seams, not this drop):** (1) A3's "tie report value to live Director/faction-intent state" — `evaluate_intel_quality` is explicitly a heuristic stub that the Director AI replaces at T3.15 (SYN.5's documented seam); the thaw is the event-rhythm half. (2) The `intel_sale` tag name from the report is **not** adopted — SYN.5's pre-existing `intel_handover` tag already meters intel income accurately and renaming would break ledger continuity for cosmetic taxonomy; the "new tag for intel income" intent is satisfied.
- **Handoff:** `HANDOFF_drop_b4_a8_a3_rollup_2026-06-04.md`

---


- **Wave:** Audit remediation / Drop 3 (aspirational economy). Rolled up with the B4 gear-insurance re-apply (same combined zip). A *tightening* of an existing faucet, not a new system: the perform payout is already metered through the ledger (tag `entertainer`, Drop 1), so this adds the report's **audience-weighting** — a modest, capped bonus when other online players are present in the room, so the faucet rewards being a social hub rather than a solo timer-tap (report A8).
- **Files:** `parser/entertainer_commands.py` — new module helpers `audience_multiplier` (pure; bounded `[1.0, 1.0 + CAP*PER]`), `_audience_flavor`, `_count_audience` (counts *other* online players via `session_mgr.sessions_in_room(room_id, source_char=char)`, excluding the performer by id — `sessions_in_room` includes the source char, so the id-exclusion is required — defensive 0 on any failure or missing session manager); the `perform` success branch now multiplies the payout by `audience_multiplier(audience)` **before** the ledger call (so the logged `entertainer` faucet reflects the real amount) and appends a crowd-acknowledging flavour line. **Also removed two dead pre-ledger credit mutations** (`new_credits = char.get("credits",0)+payout; char["credits"]=new_credits`) in the success *and* partial branches — both were immediately overwritten by the `adjust_credits(..., "entertainer")` call, so they were unlogged dead writes with a latent throttle-bypass footgun (the dead write used the raw payout, ignoring the Drop-1c `@economy throttle`). Removing them leaves the ledger call as the single credit path.
- **Tests:** +14 — `tests/test_entertainer_audience_a8.py` (pure multiplier math: neutral at 0, +PER per head, hard cap at `_AUDIENCE_CAP`, modest ceiling, garbage-input safety; `_count_audience` against a fake session manager — counts others / excludes self by id / ignores a session with no character / returns 0 on exception / returns 0 with no session manager; `_audience_flavor` branches; structural pins that the handler applies the multiplier, still routes through the `entertainer` ledger tag, and no longer carries the dead pre-ledger mutation). The structural pin caught a *second* copy of the dead mutation in the partial branch, which was then also removed.
- **Tunables:** `_AUDIENCE_BONUS_PER` (0.15) and `_AUDIENCE_CAP` (4) in `engine`/`parser/entertainer_commands.py` → multiplier ceiling 1.6×. Modest and capped by design: a solo grinder can't conjure an audience, and the cap bounds alt-parking to a small, high-effort return. Partial-pay (25cr near-miss) is intentionally *not* audience-weighted — the bonus rewards a real performance to a crowd, not a near-miss. Faucet pressure is negligible (a conditional bonus on an already-metered, cooldown- and fatigue-bounded faucet) and is now fully visible on `@economy` under `entertainer`.
- **Note (scope):** A8's "entertainer-renown status track" mentioned in the report is deferred — it belongs with the Drop 4 earned-status layer (design III.2), which builds the worn-title display surface B3 already seeded. This drop delivers the metering-already-done + audience-weighting core.
- **Handoff:** `HANDOFF_drop_b4_gear_insurance_plus_a8_audience_2026-06-04.md`

---

## 2026-06-04 — Drop 3 A4 remainder: VERIFIED ALREADY DELIVERED (no code change)

- **Wave:** Audit remediation / Drop 3 bookkeeping correctness. The 06-03 A4-commissary scope note and `TODO.json` listed A4's other two parts — populate `FACTION_MISSION_CONFIG` for Republic+CIS, and a visible `faction_payroll` stipend pay-cycle — as "remaining clean slices." A pre-flight grep of HEAD found **both already in the tree and wired** (an inverted-narrative phantom: the docs said undelivered, the code showed delivered). No code was written; this entry records the corrected state.
- **Evidence (symbol-level, at HEAD):** `engine/missions.py::FACTION_MISSION_CONFIG` is fully populated for all five CW factions — `republic` and `cis` each carry a badge, four era-clean givers, `mission_types`, an objective table (`_CW_LAWFUL_OBJECTIVES` line 999 / `_CW_INSURGENT_OBJECTIVES` line 1020), `reward_mult` 1.5, and `rep_required` 25 — and the shape is pinned by `tests/test_session49_faction_missions.py`. The pay-cycle is live: `engine/organizations.py::faction_payroll_tick` (line 1469) pays weekly stipends from the populated `STIPEND_TABLE` (CW values), applies the insurance-debt intercept, and routes payment through the ledger as `org_stipend`; it is registered on the tick scheduler in `server/game_server.py:448` (`interval=86400`) via `server/tick_handlers_economy.py::faction_payroll_tick`. **A4 is therefore complete** (commissary sink shipped 06-03; mission config + payroll pre-existing).
- **Files:** none. **Tests:** none added (existing `test_session49_faction_missions.py` already pins the config shape).

---

## 2026-06-04 — Drop 3 B4 (gear insurance): RE-APPLIED — phantom closure

- **Wave:** Audit remediation / Drop 3 (aspirational economy). **Bookkeeping-correctness drop.** The B4 gear-insurance entry was recorded in this CHANGELOG + `TODO.json` dated 2026-06-03, but its **code never landed in the tree** that produced the `_2148`/`0804` upload zips (flagged at the time in `HANDOFF_drop_vanity_titles_and_commissary_2026-06-03.md` §0 and `TODO.json` as a phantom). This drop **re-applies B4 on top of HEAD** so the code now matches the bookkeeping. Pre-flight grep confirmed the phantom at HEAD before any code was written: `engine/gear_insurance.py` / `parser/insurance_commands.py` / `tests/test_gear_insurance.py` all absent; `SCHEMA_VERSION` still 38; zero `gear_insur*` references in `db/database.py`, `engine/death.py`, `server/game_server.py`; `+insure` unregistered.
- **Files:** `engine/gear_insurance.py` (NEW — `GEAR_INSURANCE_PREMIUM=500`, the stable ledger tags `gear_insurance_premium` / `gear_insurance_premium_refund`, pure helpers `premium_amount` / `is_insured` / `insure_status_lines`, and the two async ledger-routed refund-safe mutators `purchase_gear_insurance` / `cancel_gear_insurance` — mirrors `engine/titles.py`'s shape), `parser/insurance_commands.py` (NEW — `+insure` / `+insure buy` / `+insure cancel`; aliases `insure`/`+insurance`/`insurance`; registered in `server/game_server.py` beside `+commissary`), `db/database.py` (migration **v39**: `characters.gear_insured` flag + writable-column allowlist entry; `SCHEMA_VERSION` 38→39), `engine/death.py` (`_consume_gear_insurance_if_active` helper + the `on_pc_death` protection branch).
- **Tests:** +18 — `tests/test_gear_insurance.py` (pure helpers; `purchase`/`cancel` branches against a recording stub — buy debits `gear_insurance_premium` + sets the flag; already-insured / insufficient → no charge; persist-failure fires `gear_insurance_premium_refund`; cancel clears the flag with **zero** credit movement / no-policy no-op / persist-failure; a real in-memory `Database` buy path proving the v39 column + the ledger debit + the persisted flag + the no-double-buy guard; the **death-flow protection** end-to-end against a real `Database` — an insured **lawless** death keeps the loose loadout on the character + preserves equipped gear + consumes the policy + leaves a corpse holding none of their gear; an **uninsured** lawless death drops the loose gear to the corpse as before; a **secured** death is a no-op, no corpse, policy untouched; structural pins on the v39 migration, the `gear_insurance_premium` tag + the absence of any `"gear_insurance_payout"` tag, the death consume-branch, and the command registration). Sandbox: AST clean on all touched files; engine symbols import-load; v39 migration SQL verified to apply on a fresh table with the correct default-0; Drop 2 death-reconciliation (16) stays green and **untouched** (it exercises the death *helpers* directly, never `on_pc_death`, so the new branch adds no noise to it).
- **What it shipped — and the key design call (unchanged from the original B4 spec).** A one-shot policy: `+insure buy` debits a flat premium (`GEAR_INSURANCE_PREMIUM = 500`, tunable) through the ledger chokepoint as **`gear_insurance_premium`** (a sink) and sets `gear_insured`. On the holder's next **lawless/contested** death, `on_pc_death` keeps their loose loadout on them (instead of dropping it to a lootable corpse, exactly as *equipped* gear has been preserved since Drop 2) and consumes the policy; the corpse is still created (body/decay/wound intact) but holds none of their gear. **It is a restoration model, not a credit indemnity** — deliberately: this death model does *not* destroy gear, it sends it to a *re-lootable* corpse, so a credit payout (the obvious `gear_insurance_payout`) would be a **suicide-faucet** (die on demand → re-loot your own gear → keep the payout). Protecting the loadout with no payout is the only exploit-safe shape — the premium is the sole credit movement (a sink), so there is nothing to farm. Uninsured deaths still drop loose gear, so the consensual gear-loss sink survives. `+insure cancel` drops coverage with **no refund** (the premium bought an *option*; forfeiting unused coverage keeps the premium a pure sink — no buy/cancel wash to farm). The consume helper is **fail-open**: any DB error treats the death as uninsured (gear drops), so a glitch never lets a PC keep both the gear AND the policy. Refund-safe (premium debited before the flag flips; `gear_insurance_premium_refund` on persist failure). Surfaces on `@economy` as a sink automatically.
- **Difference from the original (06-03) recorded shape — for the record.** The original CHANGELOG line described `engine/gear_insurance.py` as "pure: premium + helpers" with the buy/cancel DB logic implied elsewhere. The re-applied module instead carries the two async ledger-routed mutators *in the engine module* (with the command a thin wrapper), matching the established `engine/titles.py` pattern exactly — the more testable and more consistent split. Observable behaviour (the `+insure` command, the death protection, the v39 migration, the `gear_insurance_premium` ledger tag) is as the original spec intended.
- **Tunables / flagged for live data:** `GEAR_INSURANCE_PREMIUM` (flat for v1). If data shows *everyone* insures — eroding the gear-loss sink the consensual-loss model rests on — raise the premium or scale it by assessed loadout value (valuation only affects premium fairness, never exploit-safety, since there is no payout).
- **Handoff:** `HANDOFF_drop_b4_gear_insurance_reapply_2026-06-04.md`

---

## 2026-06-03 — Drop 3 A4 (commissary): faction requisition sink

- **Wave:** Audit remediation / Drop 3 (aspirational economy). The "config on working machinery" piece the design sequences before the sink stack — the spending side of the Republic/CIS officer's "serve the war" loop (report A4): **requisition**. Packaged (rolled up) with the B3 vanity-titles drop.
- **Files:** `engine/commissary.py` (NEW — `COMMISSARY_STOCK` per-faction catalog + pure helpers `faction_has_commissary` / `commissary_item` / `commissary_stock_for` / `commissary_status_lines` + `purchase_commissary`), `parser/commissary_commands.py` (NEW — `+commissary` / `+commissary buy <key>`; resolves the member's rank from their org membership; registered in `server/game_server.py`). **No schema change, no `db/database.py` migration** — the commissary reads org membership (existing), debits the existing ledger, and grants to existing inventory.
- **Tests:** +15 — `tests/test_commissary.py` (pure stock/helpers incl. well-formedness, the era-cleanness guard, rank filtering, and the Jedi-has-no-commissary rule; `purchase_commissary` branches against a recording stub — buy debits `commissary_purchase` + grants the item; no-commissary / unknown / rank-locked / insufficient → no charge; refund-on-grant-failure fires `commissary_purchase_refund`; a real in-memory `Database` path proving the ledger debit + the real `add_to_inventory` grant; structural pins on the sink tag and the registration). No org/faction suites touched — the commissary only *reads* `organizations.py`'s catalog conceptually; its stock is self-contained.
- **What it shipped.** A sworn faction member browses rank-appropriate gear with `+commissary` and requisitions it with `+commissary buy <key>`, debiting the cost through the ledger chokepoint as **`commissary_purchase`** (a sink — "requisition" that *feels* like spending). Stock is per-faction and rank-gated (each item has a `min_rank`: a rank-0 member requisitions basic kit, rank-1 gear needs rank 1). The catalog is the four CW non-Jedi factions' own rank-0/rank-1 issue gear (republic, cis, hutt_cartel, bounty_hunters_guild), so item keys match `EQUIPMENT_CATALOG` and a bought item behaves identically to an issued one — **era-clean by construction**. The **Jedi Order keeps no commissary** (austere — issues, never sells), faithful to the report's Jedi thesis. Refund-safe (`commissary_purchase_refund` if the grant fails). Surfaces on `@economy` as a sink automatically.
- **Scope note (A4 is multi-part):** this delivers the **commissary sink** — the economically meaningful piece. A4's other two parts (populate `FACTION_MISSION_CONFIG` for Republic+CIS; a visible stipend pay-cycle, `faction_payroll`) remain as separate clean slices.
- **Tunables:** `COMMISSARY_STOCK` (per-faction items / costs / `min_rank`) in `engine/commissary.py`. Ratify requisition rates against live `@economy` data.
- **Handoff:** `HANDOFF_drop_vanity_titles_and_commissary_2026-06-03.md`

---

## 2026-06-03 — Drop 3 B3: vanity titles (aspirational cosmetic sink)

- **Wave:** Audit remediation / Drop 3 (aspirational economy). The next clean high-tier **sink** after the home-prestige ladder (B2) — sitting beside the Kuat ship brokerage (B1) and the spacedock yard-repair drain (F2). Buying an honorific *title* is pure social standing: no payout, no mechanical benefit, nothing to farm. It deliberately introduces the **worn-title display layer** that the earned-status work (design III.2, Drop 4) will later extend, so that layer is built once.
- **Files:** `engine/titles.py` (NEW — catalog + pure helpers + `purchase_title`/`set_worn_title` + the two `characters` columns via the module's **own** idempotent `ensure_schema` column-loop, **not** the main `SCHEMA_MIGRATIONS` dict, so **no `SCHEMA_VERSION` bump / no concurrent v-number collision** — same discipline as B2's `prestige_level`), `parser/title_commands.py` (NEW — `+title` / `+title buy <key>` / `+title set <key>` / `+title clear`; registered in `server/game_server.py`), `db/database.py` (`vanity_titles` + `display_title` added to the character writable-column allowlist), `server/game_server.py` (`titles.ensure_schema` wired at startup beside housing's), `parser/builtin_commands.py` (worn title on `+who` and in the room "is here" listing), `engine/sheet_renderer.py` (worn-title sub-line on the Telnet `+sheet`; `title` field in the web `build_sheet_payload` identity block).
- **Tests:** +19 — `tests/test_vanity_titles.py` (pure catalog/helpers incl. unique keys/labels, the era-cleanness guard, and the safe owned-blob parse; `purchase_title` branches against a recording stub — buy / unknown / already-owned / insufficient / refund-on-persist-failure; `set_worn_title` — set-owned / reject-non-owned / clear, all proving **zero** credit movement; a **real in-memory `Database`** path proving the column migration, two `vanity_title` ledger debits, persisted owned-set + auto-wear, and a free worn-title switch; structural pins on the sink tag, the columns, the registration, and the who/room/sheet display wiring). Regression: B2 home-prestige (13) and the PvP/bond display-surface suite (7) stay green — the new surfaces append only when a title is worn, so title-less output is byte-identical.
- **What it shipped.** `+title` shows your worn title, what you own, and an eight-tier catalog (`the Wayfarer` 2,000 → `Luminary of the Core` 400,000) with owned/affordable/locked markers. `+title buy <key>` debits the cost through the ledger chokepoint as `vanity_title` (a pure sink) and **auto-wears** the new title; `+title set <key>` / `+title clear` move the worn title among already-owned titles for free. Buying is a one-time unlock — you keep it forever and switch freely — so the sink depth comes from catalog breadth (a collector burns ~824k for the set) and the headline tier being a genuine money-burn (cf. B2's 250k top). The worn title surfaces to others on `+who`, the room "is here" listing, and the `+sheet` (Telnet line + web payload field). Era-clean (B3): titles are mundane prestige honorifics only (wealth/reputation flavour) — Jedi rank and the like stay *earned*, never bought. Refund-safe (`vanity_title_refund` on a persist failure). Surfaces on `@economy` as a sink automatically.
- **Tunables:** `VANITY_TITLES` (keys / labels / costs / blurbs) in `engine/titles.py`. Ratify steepness/breadth against live `@economy` data.
- **Handoff:** `HANDOFF_drop_vanity_titles_2026-06-03.md`

---

## 2026-06-03 — Drop 3 B2: home prestige (aspirational credit sink)

- **Wave:** Audit remediation / Drop 3 (aspirational economy). The headline remaining high-tier **sink** — alongside the Kuat ship brokerage (B1) and the spacedock repair drain (F2), it gives veteran credit somewhere to *go*. Pure cosmetic standing on the existing housing system; no payout, no mechanical benefit, no exploit surface.
- **Files:** `engine/housing.py` (prestige catalog + pure helpers + `purchase_home_prestige` + the `prestige_level` column via the housing module's own idempotent `ensure_schema` — **no main-schema migration / no `SCHEMA_VERSION` bump**), `parser/housing_commands.py` (`+home prestige` / `+home prestige buy` wired into the `+home` umbrella).
- **Tests:** +13 — `tests/test_home_prestige.py` (pure catalog/helpers incl. the strictly-escalating-cost invariant; `purchase_home_prestige` branches against a recording stub — buy / insufficient / maxed / refund-on-persist-failure / no-home; a **real in-memory `Database` happy path** that proves the `prestige_level` column migration, the `home_prestige` ledger debit, and the persisted level; structural pins). All existing housing suites (224 tests) + the ledger pin (4) stay green — no regression.
- **What it shipped.** `+home prestige` shows your residence's current standing and the next tier's price; `+home prestige buy` purchases the next of five escalating cosmetic tiers — `Tastefully Furnished` (5,000) → `Finely Appointed` (15,000) → `Luxuriously Outfitted` (40,000) → `A Connoisseur's Residence` (100,000) → `A Sector-Renowned Estate` (250,000). Each purchase debits through the ledger chokepoint as `home_prestige` (a pure sink) and raises `player_housing.prestige_level`. Costs escalate steeply so the top tier is a genuine money-burn for the wealthy, not a routine buy — exactly the veteran-surplus drain the audit calls for. Refund-safe (`home_prestige_refund` on a persist failure). Surfaces on `@economy` as a sink automatically. The `prestige_level` lives on the housing record and is added through housing's existing idempotent column path, so there is **no main-schema migration and no concurrent v-number collision risk**.
- **Tunables:** `HOME_PRESTIGE_TIERS` (labels / costs / descriptors) in `engine/housing.py`. Ratify the steepness against live `@economy` data.
- **Handoff:** `HANDOFF_drop_home_prestige_2026-06-03.md`

---

## 2026-06-03 — Drop 3 B4: gear insurance (loadout protection, willing sink)

- **Wave:** Audit remediation / Drop 3 (aspirational economy). Completes the policyholder side of insurance that the Drop 2 death reconciliation explicitly deferred ("the insurance *payout* to the policyholder lands in Drop 3"). Adds the *willingly-paid* sink the audit wants the high tier spending into, and turns lawless gear-loss from a flat churn into a hedge-able choice.
- **Files:** `engine/gear_insurance.py` (NEW — pure: premium + helpers), `parser/insurance_commands.py` (NEW — `+insure` / `+insure buy` / `+insure cancel`; registered in `server/game_server.py`), `db/database.py` (migration **v39**: `characters.gear_insured` flag + writable-column allowlist; `SCHEMA_VERSION` 38→39), `engine/death.py` (`on_pc_death` protection branch).
- **Tests:** +16 — `tests/test_gear_insurance.py` (pure helpers; the `+insure` command — status/buy/cancel/insufficient-funds/refund-on-failure, all against a recording stub; the death-flow protection driven end-to-end against a real in-memory `Database` — insured lawless death keeps the loadout + consumes the policy + leaves an empty-of-their-gear corpse, uninsured drops as before, secured is a no-op; structural pins on the premium tag + the v39 migration). Drop 2 death tests (16) + the ledger pin (4) stay green — no regression.
- **What it shipped — and the key design call.** A one-shot policy: `+insure buy` debits a flat premium (`GEAR_INSURANCE_PREMIUM = 500`, tunable) through the ledger chokepoint as `gear_insurance_premium` and sets `gear_insured`. On the holder's next **lawless/contested** death, `on_pc_death` keeps their loose loadout on them (instead of dropping it to a lootable corpse, exactly as equipped gear has been preserved since Drop 2) and consumes the policy; the corpse is still created (body/decay/wound intact) but holds none of their gear. **It is a restoration model, not a credit indemnity** — and that is deliberate: this game's death model does *not* destroy gear, it sends it to a *re-lootable* corpse, so a credit payout (the obvious `gear_insurance_payout` design) would be a **suicide-faucet** (die on demand → re-loot your own gear → keep the payout). Protecting the loadout with no payout is the only exploit-safe shape — the premium is the sole credit movement (a sink), so there is nothing to farm. Uninsured deaths still drop loose gear, so the gear-loss sink survives for the high-adrenaline play. Refund-safe (premium debited before the flag flips; `gear_insurance_premium_refund` on any failure). Surfaces on `@economy` as a sink automatically.
- **Tunables / flagged for live data:** `GEAR_INSURANCE_PREMIUM` (flat for v1). If data shows *everyone* insures — eroding the gear-loss sink the consensual-loss model rests on — raise the premium or scale it by assessed loadout value (a future enhancement; valuation only affects premium fairness here, never exploit-safety, since there is no payout).
- **Handoff:** `HANDOFF_drop_gear_insurance_2026-06-03.md`

---

## 2026-06-03 — Economy audit v2 Tier-2 tuning batch (#4 smuggling · #5 missions · #7 P2P · #8 listing TTL)

- **Wave:** Audit remediation — the four Tier-2 *tuning* items, shipped together now that the structural three (#1 ledger, #2 pools, #3 ship-repair sink) are closed.
- **Files:** `engine/smuggling.py` (#4), `engine/skill_checks.py` (#5), `parser/builtin_commands.py` (#7), `engine/vendor_droids.py` + `server/tick_handlers_economy.py` (#8). Tests: `tests/test_tier2_tuning_batch.py` (+19); `tests/test_session51_economy_hardening.py` updated (P2P cap assertion 5000→1500).
- **#4 — smuggling EV (§1.4).** The smuggler archetype was EV-dominated by bounty hunting (a Core Run was ~+150 cr EV vs a Veteran bounty's ~+1,125). New tier-aware fine: the high-risk tiers (CONTRABAND, SPICE) drop from a flat 50% to **25%** on a bust (`FINE_FRACTION_BY_TIER` + `_fine_fraction(tier)`); low tiers unchanged. The patrol-chance alone supplies the variance, so the highest-flavour/highest-risk run becomes the apex of the credit curve it is themed to be — without raising gross payouts (no faucet increase). At 25% the Spice Run clears ~+1,400 EV (now above a Veteran bounty) and the Core Run ~+1,125 (matching it), both with higher variance. Tunable in one map.
- **#5 — mission partial-pay (§2.1).** Over-reaching by two tiers used to out-earn staying in lane. Partial-pay fractions drop from 0.50/0.75 to **0.40** across the board (`delivery` stays full-pay as the deliberately-easy tier), and the partial window tightens from `margin >= -4` to `>= -2` — a clear failure now pays zero, a near-miss pays 0.40. The repair resolver's unrelated -4 window is untouched.
- **#7 — P2P cap (§2.4).** `P2P_DAILY_CAP` 5,000 → **1,500** (a meal-out gift, not a salary; the old cap let seven alts wire ~35k/day to a main *through* it). Vendor-droid purchases and faction-treasury contributions are inherently exempt — they route through their own commands/ledger tags, not `get_daily_p2p_outgoing`, which is what the cap reads. So the cap targets only *unattributed* P2P flow.
- **#8 — vendor listing TTL (§2.7).** A listing that sits forever for one listing fee works against price discovery. Listings now carry a `listed_at` clock (stamped at stock time); a new daily pass (`tick_listing_fees`, wired alongside the existing `tick_auto_recall`) charges a small recurring **relist fee** (1% of the slot's listed value, min 10 cr, tag `vendor_relist_fee`) on slots older than 30 days, then refreshes the clock — turning the one-time listing fee into a recurring cost (the audit's stated goal) without moving or destroying items. Best-effort: a broke owner is warned, never has a listing silently deleted; true abandonment is still handled by the existing 60-day auto-recall. The fee surfaces on `@economy` as a sink automatically. *(Design note: the architecture's `recall_droid` recalls the whole droid with its stock intact rather than itemising stock back to inventory, so the audit's "items return to seller" is realised as a recurring fee + the existing whole-droid auto-recall, not a per-item return.)*
- **Tests:** +19 (smuggling fine map + bust-site pin; mission fractions + the -2 window with a guard that the repair -4 stays; the P2P constant; the listing-fee pricing math + the tick against a recording stub DB incl. the broke-owner no-loss path). Regression: session51 20/20, economy_validation 45/45, missions 37, vendor/shop suites 69, ledger pin + F2 + #2 — all green (176 in one consolidated run; session38 32/32 standalone).
- **Handoff:** `HANDOFF_drop_tier2_tuning_batch_2026-06-03.md`

---

## 2026-06-03 — Economy audit v2 §1.5: persist trade pools + wire demand depression

- **Wave:** Audit remediation — the last *structural* item before the Tier-2 tuning batch (`economy_audit_v2.md` priority #2 / §1.5). Two fixes ship together because the second makes the first meaningful.
- **Files:** `engine/trading.py` (pool persistence + orchestration), `db/database.py` (migration **v38** `market_state` table + `get_market_state`/`set_market_state`; `SCHEMA_VERSION` 37→38), `server/game_server.py` (startup hydration), `parser/space_commands.py` (buy-path flush after `SUPPLY_POOL.consume`), `parser/builtin_commands.py` (`_handle_sell_cargo`: apply depression + `record_sale` + flush). Plus in-domain cleanups: `parser/director_commands.py` (one silent `except: pass` in `@economy alerts` → logged), and three stale 0b-era test references corrected (`tests/test_session38.py` ×2, `tests/test_economy_validation.py` ×1: `corellia` → `coruscant`, since raw_ore's CW demand world is Coruscant).
- **Tests:** +15 — `tests/test_market_state_persistence.py` (pure pool serialization + dirty-flag lifecycle; the restart-windfall fix itself; real in-memory-DB get/set + flush→load round-trip; the depression-now-bites behaviour; structural pins on the sell path + the v38 migration). The three corrected stale tests + the silent-except invariant are green again (session38 32/32, economy_validation 45/45). Ledger pin + the F2 suite + the trade-remap/buyback/hardening suites all green (no regression).
- **What it shipped:** *(1) Persistence.* The supply and demand pools were process-memory singletons, so a server restart re-seeded every supply pool to full (a windfall for the first trader after a bounce) and cleared all demand depression (a windfall for the first seller). Both now snapshot to the `market_state` DB table — one JSON row each, with `updated_at` for future `@economy zones` "ran-hot" visibility — and rehydrate on startup. Only *consumption*/sales are persisted (which aren't recoverable from time); time-based refresh is reconstructed from the stored timestamps. Snapshots write immediately after each buy (`consume`) and sell (`record_sale`); at MUSH population the write volume is trivial and immediate flush is the most exploit-tight (no window in which a crash loses consumption). All flush/hydrate paths are best-effort / fail-open — a DB hiccup never blocks a trade or startup. *(2) Demand-depression wiring (latent bug found in pre-flight).* `_handle_sell_cargo` priced sales at the *base* price (it never passed `include_demand_depression=True`) and never called `DEMAND_POOL.record_sale` — so the sell-side depression mechanic, which both audits praise as the cleanest piece of trade-economics code and which forms the natural per-route round-trip profit ceiling, was **entirely inert in production** despite the price-list display advertising it. It is now wired: a saturated market pays less per ton, and the sale depresses the price for the next seller (recovering over the 45-min demand window).
- **No new content/era surfaces;** uses existing trade goods and the already-supported `get_planet_price(..., include_demand_depression=True)` path. Schema +1 (v38). Remaining harmless `corellia`/`kessel` references in test code are planet-agnostic pool-mechanic dict keys (they don't fail); flagged for a later B3-in-tests sweep.
- **Handoff:** `HANDOFF_drop_market_state_persistence_2026-06-03.md`

---

## 2026-06-03 — Economy audit F2: the spacedock yard-repair sink (high-tier drain)

- **Wave:** Audit remediation — closes **F2**, the single largest gap in the sink architecture (`SW_MUSH_Economy_Audit_FINAL.md` R2/B5; `economy_audit_v2.md` priority #3). The audit's verdict: ship repair was free and ships are never destroyed, so the wealthiest players (ship owners) had essentially nothing draining their credits — a veteran banked ~87k cr/week at <10% sunk, a ratio that *fell* with wealth. This is the lever that keeps the high-tier economy from inflating.
- **Files:** `engine/ship_repair.py` (NEW — pure pricing + apply), `parser/space_commands.py` (NEW `SpacedockCommand`; registered in the top-level space registry + the bridge-switch dispatch dict).
- **Tests:** +27 — `tests/test_ship_repair_yard_sink.py` (pricing math + boundaries + design invariants; the restore step; full `SpacedockCommand` integration against a recording stub DB loading the *real* ship registry — docked gate, quote-only, debit==quote via `ship_repair`, systems+hull restored, insufficient-funds, refund-on-write-failure; and structural pins). Ledger tree-wide pin + 137 adjacent space/ship tests green, no regression.
- **What it shipped:** `damcon` field-repair **stays free** — the in-combat skill moment, protected and structurally pinned (the command contains no `adjust_credits`). The new **spacedock** does the two things `damcon` cannot, for credits: it restores **DESTROYED** systems (which `damcon` explicitly refuses — "needs spacedock") and fully restores hull + any remaining damage in one paid pass. `+spacedock` quotes the job; `+spacedock repair` pays it. The fee is a fraction of **hull value** (single-sourced from `ShipTemplate.cost`, exactly what the Kuat brokerage prices off), dominated by a per-destroyed-system fee (`YARD_DESTROYED_PCT=0.06`), with modest fees for `damaged` systems (`0.01`, since `damcon` is the free alternative) and hull (`0.03 × damage-fraction`), floored at `YARD_MIN_FEE=50`. So the fee scales with the asset — a 1.5 M-cr cruiser's destroyed hyperdrive costs 90 k (the whale actually feels it), a starter freighter's a few hundred. Debited through the ledger chokepoint as `ship_repair` (refund-safe: the debit precedes the ship write; `ship_repair_refund` on any failure), gated to docked ships only. The new sink appears on `@economy` automatically (the velocity dashboard groups by `source`), so it is measured the moment it is used.
- **Tunables (first-cuts, ratify against live ledger):** `YARD_DESTROYED_PCT`, `YARD_DAMAGED_PCT`, `YARD_HULL_PCT`, `YARD_MIN_FEE` in `engine/ship_repair.py`. The docked-only gate (vs. specific repair-yard slugs) is the robust choice — it matches `damcon`'s own "needs spacedock" framing and never dead-ends at a world whose docks aren't tagged.
- **Handoff:** `HANDOFF_drop_F2_ship_repair_sink_2026-06-03.md`

---

## 2026-06-02 — Economy audit v2 §1.3: NPC vendors stop price-supporting crafted goods

- **Wave:** Audit remediation — closes the craft → NPC-sell price-support loop (`economy_audit_v2.md` §1.3), the real lever behind the #10 survey-cooldown throttle. Distinct from #12 (dynamic supply/demand curves), which remains a deferred Month-1+ feature.
- **The exploit:** a player crafts a Tier-1 item from ~55 cr (or free, surveyed) materials and sells it to an NPC for ~200 cr — a >250 cr/craft credit engine needing no buyer. Worse, the NPC's buyback set the floor price for the whole crafted-goods market, so player vendor droids never had to discover their own floor (SWG's pre-NGE mistake). Compounded by the existing sell-price *quality bonus* (≥80 → +30%, ≥60 → +15%), which made NPCs pay a premium for exactly the high-quality crafts that should go to players.
- **Fix (the audit's preferred "indirect" option):** NPC vendors **refuse** well-made player crafts — "too good for scrap, list it on a vendor droid" — pushing them to the player vendor market where the price discovers itself. Low-quality crafts (`quality < 50`) and all factory/vendor items still sell to NPCs as salvage (which usefully liquidates glut).
- **Files (source):** `engine/items.py` (new tunable `CRAFTED_NPC_BUYBACK_MAX_QUALITY = 50` + `npc_refuses_buyback(item)` helper), `parser/builtin_commands.py` (`SellCommand` gated by the helper before pricing/credit write; help text updated). **(tests):** `tests/test_npc_buyback_crafted.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Scope/safety:** the gate keys on a **non-empty `crafter`** (set only by `new_crafted`), so factory items (`new_from_vendor`, no crafter) and synthetic `crafter=""` fixtures are unaffected; the `sell <resource> to <shop>` and `sell cargo` routes dispatch earlier and are untouched. Threshold is tunable; the gate short-circuits before the `item_sale` ledger write.
- **Tests:** +6 (`test_npc_buyback_crafted`: helper logic — high-quality craft refused, low-quality + factory pass, boundary at threshold, threshold pinned at 50 — and a structural pin that `SellCommand` consults the gate before the credit write). **152 passed** across the sell/craft/weapon-adjacent suites (`test_cities_phase4b` city-tax-on-sell, `test_session56_craft_crew_umbrellas`, `test_syn6c_t5_crafting_and_harvest_nodes`, `test_weapons_unit`, +new) — no regression (`test_cities_phase4b` sells a `new_from_vendor` item, correctly not gated).
- **Validation (sandbox):** `py_compile` clean; helper smoke-verified; suites green. **Pending on Brian's box:** full suite; smoke a real crafted high-quality weapon → confirm the NPC refusal message and that a low-quality craft / factory weapon still sells.
- **Handoff:** `HANDOFF_npc_buyback_crafted_2026-06-02.md`

---

## 2026-06-02 — Test-suite health: all 3 known pre-existing failures fixed (manifest y-flip, asyncio 3.14, substrate-seed lock re-pinned)

- **Wave:** Project-health pass over the three known pre-existing test failures — all three now green.
- **Fix 1 — `tests/test_make_register_manifest.py` (1 failure → 0):** the local `_frac_to_world` helper still inverted y (`y_max - fy*h`), drifting the round-trip (`bay94 y 2.5 vs 4.7`). The tool's `world_to_frac` is **no-flip** per Drop 4.17 (`fy = (wy - y_min)/dy`, SVG-space y-down), and the renderer paints the substrate rect at `y_min` — both confirm no flip. Fixed the helper to `y_min + fy*h`; round-trip now exact. **6/6 pass.**
- **Fix 2 — `tests/test_area_map_emits_slug.py` (deprecation → clean):** replaced the deprecated `asyncio.get_event_loop().run_until_complete(coro)` in `_run` with the canonical fresh-loop pattern (`new_event_loop()` + `try/finally: close`) used by the already-fixed siblings (BugFix5 / 2026-05-24). On **Python 3.14** the old call raises when no loop is running; this also fixes the documented subset-run flakiness on 3.12. **3/3 pass, no deprecation.** (The broader `get_event_loop()` pattern survives in ~16 other sites but is shielded by pytest-asyncio's managed loop; not swept here to avoid churn.)
- **Fix 3 — `tests/test_wilderness_substrate_seed.py` (6 failures → 0, now 13/13):** this Drop 4.16 regression lock checked conventions the substrate lane (4.15a–4.18) outgrew. Re-pinned to the substrate-first reality, confirmed against the live artifacts and Brian's input (PNGs painted; substrate-first is the design): (a) `terrain_zones` check now substrate-aware (a painted region carrying `substrate_image` needs no procedural zones; any present are still validated); (b) manifest check now locks **builder fidelity** (manifest converts every authored landmark into an in-bounds pin, exits not distinctive) instead of a fixed `6/4` that was wrong for both regions (Dune Sea has 5, Underworld 6); (c) the old package `{GEOGRAPHY}` IP-neutral check (those lines moved to generated briefs in Drop 4.18) replaced by `test_package_documents_generated_briefs` — asserts the package points at `gen_wilderness_overview.py` + the generated brief paths, which exist; (d) the JS substrate check repointed from the body renderer's old *commented placeholder* to the **active** `substrate_image` in the generated overview data (`m3_wilderness_overview_data.js`), with the body confirmed data-driven.
  - **Heads-up (not enforced):** the generated paint-brief prompts intentionally reuse each region's authored feature descriptions, which include lore nouns (`Black Sun`, `Jedi`, `Uscru`, region names). The painted PNGs were produced from exactly those prompts, so the old blanket franchise-noun ban no longer reflects the working pipeline — left as a note (`TD.WILDERNESS_BRIEF_FRANCHISE_LEAK`) in case a future regeneration hits a Gemini filter refusal.
- **Files:** `tests/test_make_register_manifest.py`, `tests/test_area_map_emits_slug.py`, `tests/test_wilderness_substrate_seed.py`; `CHANGELOG.md`, `TODO.json`.
- **Validation (sandbox):** all three files green — 6/6, 3/3, 13/13; no deprecation.
- **Handoff:** `HANDOFF_test_suite_health_2026-06-02.md`

---

## 2026-06-02 — Economy audit #10: survey cooldown 5 min → 15 min

- **Wave:** Audit remediation — resolves **#10** (🟡 "value mismatch"). Brian's tuning call: adopt the audit's recommended value.
- **Change:** `engine/cooldowns.py` `SURVEY_COOLDOWN_S` `300 → 900` (5 → 15 minutes). Rationale (per audit): free surveyed crafting materials should feel earned, and the survey cooldown is the *input throttle* on the survey→craft→NPC-sell faucet `economy_audit_v2` flagged (at 5 min that's 12 free material pulls/hr feeding it; at 15 min, 4). Note: #10 alone is partial mitigation — the NPC buyback margin (Phase-3 #12) is the larger lever and remains deferred.
- **Files:** `engine/cooldowns.py`; `tests/test_cooldowns_unit.py` (the value-pin `test_survey_duration_is_5_minutes` → `test_survey_duration_is_15_minutes`, asserting 900 — mandatory update, the old pin is now wrong). `CHANGELOG.md`, `TODO.json`.
- **Tests:** `test_cooldowns_unit.py` **51 passed** (updated pin green); `test_economy_validation.py::...::test_survey_has_cooldown` (range `>= 120`) still passes at 900. No new breakage — the harness-fixture errors and the `TestTradeGoodsPricing` failure in that file are pre-existing and unrelated to a constant change.
- **Canonical value:** recorded here + in `TODO.json`. The architecture-of-record (`sw_d6_mush_architecture_v51.md`) lives outside the repo tree, so if a doc line is wanted there it's: `SURVEY_COOLDOWN_S = 900 (15 min), canonical per economy audit #10`.
- **Handoff:** `HANDOFF_survey_cooldown_2026-06-02.md`

---

## 2026-06-02 — Economy audit F1/R1: COMPLETE the ledger chokepoint (13 bypass sites migrated)

- **Wave:** Audit remediation — finishes **F1 / R1** ("connect the ledger"), the #1 economy-audit finding. The Drop 1 migration was marked complete, but an AST sweep found credit mutations still bypassing the chokepoint.
- **The finding:** the line-based grep used previously only caught single-line calls; an **AST scan found 14** `save_character(credits=...)` sites still writing the balance directly (bypassing `Database.adjust_credits`), so they never hit `credit_log` — meaning **entertainer payouts, medical fees, sabacc, PvP bounty rewards, equipment repair/sale, debt payments, org stipends, boarding rewards, and the docking fee were all invisible to `@economy velocity`, the dashboard, and the velocity alerts shipped earlier today.**
- **What it shipped:** migrated the **13 running-economy transactions** to `adjust_credits` (atomic balance + `credit_log` write), preserving each site's existing affordability checks (`allow_negative=True` default — the change is about *logging through the chokepoint*, not adding refusals). Each carries a source tag: `org_stipend`, `boarding_reward`, `debt_payment` (×3), `entertainer` (×2), `medical` (×2, the patient→healer legs), `sabacc`, `repair`, `item_sale`, `bounty`, plus `docking_fee` (the daily tick, also migrated off its old non-atomic `save_character + log_credit` two-step). The **1** remaining raw site (`server/api.py` skip-starter-kit) is an intentional **chargen absolute-init** (consistent with the unlogged `create_character` INSERT), documented + allowlisted.
- **Files (source):** `engine/organizations.py`, `engine/encounter_boarding.py`, `engine/debt.py`, `engine/chain_rewards.py` (stale-docstring fix — it already used `adjust_credits`), `parser/entertainer_commands.py`, `parser/medical_commands.py`, `parser/sabacc_commands.py`, `parser/spacer_quest_commands.py`, `parser/builtin_commands.py`, `parser/combat_commands.py`, `server/tick_handlers_economy.py` (docking_fee), `server/api.py` (allowlist comment). **(tests):** `tests/test_ledger_chokepoint_complete.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Anti-regression lock:** the new guard AST-scans engine/parser/server and **fails if any raw `save_character(credits=...)` appears outside the documented allowlist** — AST, not grep, so comments/docstrings that mention the old pattern don't trip it. This is what keeps F1 from silently re-opening.
- **Also resolved this drop:** economy-audit **#5** (recurring docking fee) confirmed already implemented (`docking_fee_tick`, 25 cr/day per docked ship) — the scorecard was stale; the tick is now also ledger-correct.
- **Tests:** +5 (`test_ledger_chokepoint_complete`: comprehensive AST guard + allowlist-still-valid + docking_fee-uses-chokepoint pins). **146 passed** across the ledger/chokepoint, economy-hardening, combat, and debt-gate suites — no regression.
- **Validation (sandbox):** `py_compile` clean on all 12 source files; AST re-scan confirms only the 1 allowlisted site remains; suites above green. (Pre-existing unrelated failure still present: `test_economy_validation.py::TestTradeGoodsPricing` — trade-goods tiers, untouched here.) **No dedicated sandbox tests exist for the entertainer/sabacc/medical/spacer-quest command paths** — those migrations are mechanically uniform and compile, and rely on Brian's full suite + in-client smoke. **Pending on Brian's box:** full ~4,854 suite; smoke each migrated flow (perform, gamble, heal, repair, sell, pay debt, collect a bounty) and confirm the credits show up under `@economy velocity` faucets/sinks.
- **Handoff:** `HANDOFF_ledger_chokepoint_complete_2026-06-02.md`

---

## 2026-06-02 — Economy audit #17 / R1: proactive credit-velocity alerts

- **Wave:** Audit remediation — closes economy-audit finding **#17** (scorecard: "data collected, no alerts") and the "add velocity alerts" clause of **R1** in `SW_MUSH_Economy_Audit_FINAL.md`.
- **Files (source):** `engine/economy_alerts.py` (**new** — pure evaluator + ring buffer), `server/tick_handlers_economy.py` (new `credit_velocity_alert_tick` + `_page_economy_alert_staff`), `server/game_server.py` (register the hourly tick), `parser/director_commands.py` (surface recent alerts in `@economy alerts`). **(tests):** `tests/test_econ_velocity_alerts.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +19 (`test_econ_velocity_alerts`: band evaluator incl. **deflation**, both severities, below-band, custom thresholds, 24h-context/driver carry, malformed input; ring-buffer record/recent/clear/cap/limit; formatter; + 3 structural pins — handler defined, registered in GameServer, readout wired). **19 passed** alone; **87 passed** with the economy-hardening + director-loader suites (no regression).
- **The gap:** `Database.get_credit_velocity` computed faucet/sink/net flow and `@economy velocity`/`alerts` *read* it on demand, but nothing proactively flagged a hot economy. The audit wanted automated paging, not just dashboard reads.
- **What it shipped:** an hourly `credit_velocity_alert_tick` (interval 3600, offset 2100) evaluates server-wide net 1h flow against tunable bands; on a breach it records the alert (surfaced under "Recent velocity alerts" in `@economy alerts`), logs `[ECONOMY ALERT] …`, and pages every online admin/builder session. The 24h figure rides along as context.
- **Bidirectional by design:** `economy_audit_v2.md` flagged that farming detection only watches *positive* deltas, so a wage-heavy server can deflate silently. The band is on **|net|**, labelled inflation (net ≫ 0) vs deflation (net ≪ 0) — both page.
- **Tunable thresholds (initial defaults, NOT yet calibrated):** `VELOCITY_CAUTION_NET_1H = 50,000` and `VELOCITY_CRITICAL_NET_1H = 150,000` cr/hr, server-wide net. Module-level so a tuning pass (or a future config surface) can move them without touching the tick. Operator calibrates against `@economy velocity` + `@economy throttle`.
- **Design choices:** logic lives in a server-free `engine/economy_alerts.py` so the band evaluator is unit-testable without the aiohttp stack; the tick does all I/O and fails open on every step (a velocity-fetch, record, or page failure logs and returns without disturbing the tick loop); the recent-alert buffer is an in-memory capped deque (no schema migration).
- **Validation (sandbox):** `py_compile` clean on all four source files; evaluator + buffer + structural pins green; relevant economy/director suites green. (Pre-existing unrelated sandbox failure noted: `test_economy_validation.py::TestTradeGoodsPricing` — a trade-goods price-tier `assert 100 < 100`, no overlap with these files.) **Pending on Brian's box:** full ~4,854 suite; live check — set the bands low, drive credit flow, confirm staff get `[ECONOMY ALERT]` pages and `@economy alerts` shows the recent entries.
- **Handoff:** `HANDOFF_econ_velocity_alerts_2026-06-02.md`

---

## 2026-06-02 — Drop 2 follow-up: wire the respawn-grace consumer (anti-spawn-camp)

- **Wave:** Audit remediation — closes a flagged Drop 2 loose end (infrastructure-complete but unwired).
- **Files (source):** `parser/combat_commands.py` (the PC-death block in `_apply_combat_wear`). **(tests):** `tests/test_drop2_respawn_grace_wiring.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +8 (`test_drop2_respawn_grace_wiring`: 5 source-structure wiring pins — reader called, gated before `on_pc_death`, caps at INCAPACITATED, death path intact, no-throw-guarded — + 3 real-db reader-contract checks). **8 passed** alone; **16 passed** Drop 2 reconciliation (no regression); **113 passed** across the death/combat files (`test_pg1_death_a/b`, `test_combat_mechanics`, `test_session54_combat_umbrella`).
- **The gap:** Drop 2 shipped `engine.death.get_respawn_grace_until` (a reader that returns the wall-clock time a PC is protected from re-kill after a PvP death) **and** the `grace_until` writer inside `on_pc_death` — but **nothing ever called the reader**. The anti-spawn-camp protection the function's own docstring described ("read by the combat layer to refuse lethal damage during the grace window") did nothing. Confirmed by grep: zero callers outside `death.py`.
- **What it shipped:** the PC-death finalization in `_apply_combat_wear` now consults `get_respawn_grace_until(ctx.db, c.id)` **before** running `on_pc_death`. If the victim is still inside their grace window, the killing blow is refused: wound_level is capped at **INCAPACITATED** (alive, downed — and crucially *not* MORTALLY_WOUNDED, so it won't bleed out next round), the lowered level is re-synced to DB + session, the player is told (`[RESPAWN PROTECTION] …`), and the death side-effects (`on_pc_death`: corpse, inventory drop, wound debuff, BH-insurance fire) are skipped entirely. Otherwise the normal death path runs unchanged.
- **Design notes:** the reader **fails open to 0.0** (no protection), so a DB read error can never *grant* invulnerability. Grace is only ever written on PvP deaths (those with a `killer_id`), so the window is inherently a PvP-respawn protection; while protected, repeated blows simply re-cap the victim at INCAPACITATED until the 60 s window (`RESPAWN_GRACE_SECONDS`) elapses. Scope = "refuse the lethal blow during the window" regardless of attacker type (simple + faithful to the docstring); can be tightened to same-killer-only later if desired.
- **Validation (sandbox):** `py_compile` clean; the wiring + Drop 2 + death/combat suites pass as above. *Sandbox-divergence note:* the sandbox was missing `aiosqlite`/`bcrypt`/`aiohttp`; once `aiosqlite`+`bcrypt` were installed the db-backed tests ran green (server-import tests still need `aiohttp`, irrelevant to this change). **Pending on Brian's box:** full ~4,854 suite; in-client PvP smoke (kill a PC, respawn, attempt an immediate re-kill within 60 s → blow turned aside, `[RESPAWN PROTECTION]` shown, no second corpse).
- **Handoff:** `HANDOFF_drop2_respawn_grace_wiring_2026-06-02.md`

---

## 2026-06-02 — Mos Eisley population recovery, Phase 2 (utility tier) + port schedule

- **Wave:** Audit remediation follow-up; continuation of Phase 1. Adds the Mos Eisley **service tier** and records the schedule + density cap for the rest of the GG7 era-portable port.
- **Files (source):** `data/worlds/clone_wars/npcs_mos_eisley_population_p2.yaml` (**new** — 6 NPCs), `data/worlds/clone_wars/era.yaml` (register). **(tests):** `tests/test_mos_eisley_population_p2.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json` (new `T2.CW.tatooine_npc_density` resolved decision + a `_notes` entry with the full Phase 1–4 schedule).
- **Tests:** +9 (`test_mos_eisley_population_p2`: file/roster ×3, era-cleanliness ×1, Lup-not-Rebel re-skin ×1, no-collision ×1, era-registration ×1, **CW dry-run integration ×2** — all-6-resolve, De-Maal-distinct-from-Pit-Floor). **38 passed** combined (9 + 11 Phase 1 + 18 0a-2).
- **Density directive (user, this session):** *"Don't go crazy with NPCs on Tatooine. We need flavor and utility but PCs are the focus."* Recorded as `T2.CW.tatooine_npc_density` — **supersedes** `cw_content_gap_design_v1.md` Q6's "~1.4 NPCs/room matching GCW" target for Tatooine. The port is restrained: one good NPC per real service gap, measured street flavor, no chasing GCW density. Mos Eisley/Tatooine named-NPC footprint after Phases 1–2 is ~30 across ~40 rooms (well under 1/room).
- **What it shipped — the utility tier (one NPC per service gap):**
  - **Heist** — medic @ The Cutting Edge Clinic (re-skinned from a GCW "Imperial-bribery" angle to a discreet, no-questions doctor the cartel tolerates).
  - **Zygian Teller** — Rodian banker @ Zygian's Banking Concern (accounts, exchange, discreet cartel transfers).
  - **Lup** — Ithorian general store @ Lup's General Store (**re-skinned Rebel → neutral merchant**; the Rebellion doesn't exist at ~20 BBY).
  - **Geordi Hans** — speeder dealer/mechanic @ Spaceport Speeders.
  - **De Maal** — independent bay operator @ Docking Bay 94 – Entrance (carries the `gg7_mos_eisley_extraction_v1.md` §4.3 era-safe tension hook: business down after a Corellian customer broke port quarantine from his bay; sits at the bay *Entrance*, distinct from Mak/Venn on the Pit Floor — a coherent multi-room bay).
  - **Gep** — Devaronian food-grill + market gossip @ Market Place – Gep's Grill.
  - All re-skinned with original prose, era framing (no Empire/Rebellion; Hutts run Tatooine; war is distant news), and **nested-lowercase `char_sheet.attributes`**. Transactional mechanics (shop/medical/vehicle/banking) are separate-system concerns, not NPC seeding.
- **Port schedule (recorded in `TODO.json`):** Phase 1 ✅ (cantina core + Venn + Kayson, 12), Phase 2 ✅ (utility tier, 6). **Phase 3** (future, lean): light street ambiance + leftover service NPCs only if a gap is felt (transport dispatcher, a hotel clerk, BoSS agents, 1–2 street-flavor figures). **Phase 4** (future): the salvageable GCW-coupled NPCs (Lady Valarian, Momaw Nadon, …) — re-skin pass (Lup and Heist were pulled forward into Phase 2). **Not porting:** ANH-plot figures (BoShek, Evazan, Garindan) unless a quest wants one.
- **Validation (sandbox):** `py_compile` + YAML-parse clean; era-cleanliness scan over parsed field values clean; live `load_world_dry_run('clone_wars')` resolves all 6 to their intended rooms. **Pending on Brian's box:** full ~4,854 suite; in-client smoke (`talk heist`, `talk lup`, etc.).
- **Handoff:** `HANDOFF_mos_eisley_population_p2_2026-06-02.md`

---

## 2026-06-02 — Mos Eisley population recovery, Phase 1 (port era-portable GG7 cantina + Venn/Kayson into CW)

- **Wave:** Audit remediation follow-up. Acts on the HEAD-audit finding logged in the Drop 0a-2 entry below (CW never loads the GG7 base roster, so Mos Eisley is a ghost town and the `schematics.yaml` "Venn Kator" trainer dangles). Implements **Gap A** of `cw_content_gap_design_v1.md` for the cantina tier, per the Q5 "re-skin first" decision and the `gg7_mos_eisley_extraction_v1.md` era playbook.
- **Files (source):** `data/worlds/clone_wars/npcs_mos_eisley_population_p1.yaml` (**new** — 12 NPCs), `data/worlds/clone_wars/era.yaml` (register the new file). **(tests):** `tests/test_mos_eisley_population_p1.py` (**new**), `tests/test_drop0a2_spacer_quest_relocate.py` (the `test_venn_kator_absent_from_cw` pin rewritten to `test_step24_independent_of_venn` — see "cross-drop note"). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +11 (`test_mos_eisley_population_p1`: file/roster ×3, era-cleanliness scan ×1, Venn-trainer ×2, no-collision-with-replacements ×1, era-registration ×1, **CW dry-run integration ×3** — all-12-resolve, Main-Bar-now-populated, Venn-trainer-survives-load) + 0a-2 rewritten pin. **29 passed** in the combined sandbox run (11 + 18).
- **The finding (answers a standing question about `npcs_gg7.yaml`):** GG7 = *Galaxy Guide 7: Mos Eisley*, an A-New-Hope/GCW roster of 55 NPCs. ~15 are era-broken for the Clone Wars (7 hard-Imperial — already replaced in `npcs_cw_replacements.yaml` — plus 8 GCW-coupled); the other ~40 are era-neutral Mos Eisley locals. **All 29 GG7 rooms already exist in the CW Tatooine build, but CW never loads the GG7 roster**, so they sit empty — Chalmun's Cantina held a single NPC (Renn Sallow). The content-gap plan's Q6 density target assumed "GG7 carries Tatooine at ~1.4 NPCs/room," which is false in the live build; this drop begins closing that real (not assumed-closed) gap.
- **What it shipped:** 12 era-portable NPCs, re-skinned with original prose (no WEG text copied) and the era framing (no Empire/Rebellion; the Hutt cartel is Tatooine's de-facto authority; the war is distant news) and proper **nested-lowercase** `char_sheet.attributes` (the loader silently ignores GG7's capitalized top-level form, defaulting to 2D):
  - **Chalmun's Cantina** — Wuher, Chalmun, Muftak, Kabe, Djas Puhr, Hem Dazon, M'iiyoom Onith, Bom Vimdin (Main Bar; now 9 NPCs incl. Renn Sallow), Figrin D'an (Back Hallway), Cantina Bouncer (Entrance).
  - **Venn Kator** at "Docking Bay 94 - Pit Floor" — the ship-component crafting trainer named by `data/schematics.yaml` (`trainer_npc: Venn Kator`, skill `space_transports_repair`); now `trainer: true` with a real `train_skills: [starship_repair, space_transports_repair]` (the GG7 entry set the flag but listed no skills) plus a `teach_intro` directed response. Un-dangles the schematics reference. Pairs with Mak Torvin, relocated to the same bay in 0a-2.
  - **Kayson** at "Kayson's Weapon Shop" — the armorer whose CW room description already references "Kayson's knowledge of weapons," now with a keeper.
- **Cross-drop note:** seeding Venn intentionally falsifies the old 0a-2 `test_venn_kator_absent_from_cw` pin. That pin's real intent was *quest-independence* (step 24 uses Renna, not the deleted Corellia-Venn), which still holds — this is a **different** Venn instance (the Mos Eisley DB94 shipwright/crafting trainer, not the Corellia forge-master). The pin is rewritten to assert step 24 still routes through Renna and that any seeded Venn is the DB94 shipwright.
- **Validation (sandbox):** `py_compile` + YAML-parse clean; era-cleanliness test scans parsed field values (descriptions/personality/dialogue/fallback_lines) for Imperial/Rebellion tokens — clean; live `load_world_dry_run('clone_wars')` resolves all 12 to their intended rooms (none to the Market Row fallback), Main Bar = 9, Venn trainer config survives load. **Pending on Brian's box:** full ~4,854 suite; in-client smoke (`talk wuher`, `talk venn`, and learning a `schematics.yaml` ship-component recipe from Venn once the Drop-12 ship-customization consumer lands).
- **Deferred (Phase 2+):** the street / docking-bay / shop / service tiers (speeder dealers, dock operators, the inn, the general store, the medic, the banker, BoSS agents, Lady Valarian, …), the 8 salvageable GCW-coupled NPCs, and the ANH-plot-coupled cantina figures (BoShek, Evazan/Ponda-Baba's associate, Garindan).
- **Handoff:** `HANDOFF_mos_eisley_population_p1_2026-06-02.md`

---

## 2026-06-02 — Drop 0a-2: un-break the "From Dust to Stars" starter quest (era-migration dead-ends)

- **Wave:** Audit remediation — Drop 0a (un-break what the 06-01 era migration broke). Closes the starter-ship quest's dead-ends; companion to 0a.1 (smuggling/space destinations) and 0b (trade re-map).
- **Files (source, 3):** `engine/spacer_quest.py` (quest geography: steps 15/18/20/23/24/26/27), `data/worlds/clone_wars/npcs_drop_0a2_fdts_relocate.yaml` (**new** — seeds Lira Shan on Kuat), `data/worlds/clone_wars/npcs_drop_g1_nar_shaddaa_topside.yaml` (Mak Torvin relocation), `data/worlds/clone_wars/era.yaml` (register the new NPC file). **(tests):** `tests/test_drop0a2_spacer_quest_relocate.py` (**new**), `tests/test_drop_g1_nar_shaddaa.py` (Mak docstring + Nar-Shaddaa-only invariant exception). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +18 (`test_drop0a2_spacer_quest_relocate`: geography migration ×2, Grand-Tour roster ×1, step-27 climax ×1, Lira-seeded-on-Kuat ×4, Mak-relocated ×3, step-24→Renna ×3, manifest-stays-bespoke ×1, era-registration ×1, **CW dry-run integration ×2 incl. a 3-NPC subtest**) + g1 unchanged at 32. **50 passed** in the combined sandbox run.
- **The bug:** the FDtS starter quest (`spacer_quest.py`, 30 steps) was half-migrated when the 06-01 era pivot deleted Kessel and Corellia from the CW graph. Step 7 (Phase 1!) dead-ended because Mak Torvin — the quest-giver the code expects at "Docking Bay 94" — was seeded on Nar Shaddaa (contradicting his own dialogue, which says "head back to Tatooine"). Step 20 sent players to land on the deleted Kessel/Corellia. Steps 26/27 (the ship-purchase climax) routed through broker Lira Shan "on Corellia at Coronet Starport" — but Lira was reserved-for-FDtS and never actually seeded, so the quest could not be completed. Step 24 talked to Venn Kator "on Corellia."
- **What it shipped (per `from_dust_to_stars_design_v2_clone_wars.md`):**
  - **Lira Shan seeded on Kuat** as a Kuati Drive Yards (KDY) broker at "Kuat Drive Yards - Commercial Zone" (design §49/§209/§538-546). Reachable from Kuat arrivals via the Ring Transit Hub. Step 27's `room_substr` changed `Coronet` → `Kuat Drive Yards`; verified by a live `load_world_dry_run('clone_wars')` that she resolves to room idx 307 (not the Market Row fallback).
  - **Mak Torvin relocated** Nar Shaddaa → "Docking Bay 94 - Pit Floor" (Tatooine), where steps 7/13/26 and his ship (the Rusty Mynock, parked there per `ships.yaml`) expect him; description re-grounded to the bay. Resolves to room idx 1.
  - **Travel objectives re-mapped:** step 20 visit-planets `[tatooine, nar_shaddaa, kessel, corellia]` → `[..., kuat, coruscant]`; step 15 hyperspace hint and step 18 cargo example updated to the new roster (Kuat industrial components → Nar Shaddaa, per design §427/§432).
  - **Step 24 retargeted to Renna Dox** (already seeded on Nar Shaddaa). Design v2 §501-507 explicitly *removes* Venn Kator (a Corellia NPC absent from the CW manifest) rather than relocating him; the unauthored "Kuat crew office" alternative (§986) means Renna alone is the trigger. Objective `npc` = `"renna dox"` (unambiguous vs. the Threnna/Vrenna substrings).
- **HEAD-audit finding (logged for a future drop, NOT fixed here):** the CW `era.yaml` does **not** load the base roster `data/npcs_gg7.yaml` (only the GCW `era.yaml` lists `../../npcs_gg7.yaml`); the `npcs_cw_additions.yaml` header claiming the CW files are "additive on top of npcs_gg7.yaml" is stale. Consequently GG7 base NPCs (Venn Kator, Kayson, …) are **absent from CW** — confirmed by dry-run load. Any CW system still naming them (e.g. the `schematics.yaml` / build-tutorial ship-component trainer "Venn Kator at Docking Bay 94") is a dangling reference. Recommend a dedicated CW Mos Eisley roster audit.
- **Lesson re-confirmed (verify by LOAD, not grep):** a mid-build grep showed Venn in `npcs_gg7.yaml` and I briefly concluded "step 24 already works." Only a live `load_world_dry_run('clone_wars')` + `load_era_npcs(...)` revealed Venn is absent from CW — which is also what the design doc says to assume. The integration test (`TestCWWorldLoadResolvesFDtSNPCs`) now pins NPC→room resolution so this class of silent failure (registered-but-unresolved, or never-loaded) cannot regress unnoticed.
- **Validation (sandbox):** `py_compile` + YAML-parse clean on all touched files; residue grep confirms no `kessel`/`corellia`/`coronet`/`venn` in quest geography (only the legitimate Nar Shaddaa "Corellian Sector" district). **Pending on Brian's box:** full ~4,854 suite; in-client end-to-end smoke of the FDtS quest (Phase-1 step 7 talk-Mak at DB94 through Phase-5 step 27 buy-from-Lira at Kuat KDY, plus step 24 talk-Renna).
- **Handoff:** `HANDOFF_drop_0a2_spacer_quest_relocate_2026-06-02.md`

---

## 2026-06-02 — Drop 1.c: close the ledger wave (`+finances` + `@economy throttle`)


- **Wave:** Economy audit Phase 1 (finding F1 — ledger chokepoint). This is the **wave closer**: with 1.a→1.b.4 routing every credit movement through `adjust_credits`, 1.c adds the two user-facing pieces the audit specified — a player ledger view and an admin faucet-tuning lever.
- **Files (source, 4):** `db/database.py` (throttle correctness fix), `parser/director_commands.py` (`@economy throttle` subcommand), `parser/finances_commands.py` (**new** — `+finances`), `server/game_server.py` (register `+finances`). **(tests):** `tests/test_drop1c_finances_and_throttle.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +14 — `test_drop1c_finances_and_throttle` (FaucetThrottle ×8 against the real `adjust_credits`, EconomyThrottleCommand ×4, FinancesCommand ×2).
- **HEAD audit note (infra-complete pattern):** the throttle **DB layer already existed at HEAD** — the `economy_config` table (migration v36), the `_faucet_throttle_pct` cache, `get_/set_faucet_throttle_pct`, and the application inside `adjust_credits` — all tagged "Drop 1.c" but with **no command wired** to read or set it, and `get_char_credit_breakdown` carried a docstring saying it "powers the player-facing `+finances` command" that **did not exist**. 1.c wires both.
- **What it shipped:**
  - **`@economy throttle [0-100]`** (ADMIN, in `EconomyCommand`) — show the current global player-faucet throttle, or set it (clamped 0–100; persisted in `economy_config`; cached in-process). 100 % = no-op; 0 % = faucets fully suppressed (logged as zero entries so the suppression is visible). Intercepts before the dashboard render.
  - **Throttle correctness fix** (`adjust_credits`): the existing code scaled **all** positive deltas, which at <100 % would also shrink **p2p-transfer receipts** (zero-sum moves) and **refunds** (reversals — shortchanging a player on a canceled order). Now excludes any source containing `p2p_transfer` or `refund`, so only genuine new-money faucets are cooled; sinks and `char_id=0` system entries remain exempt as before.
  - **`+finances [hour|day|week]`** (PLAYER, new) — the player's own credit flow over a window: balance, earned/spent/net, transaction count, and top faucet/sink sources (prettified labels), via `get_char_credit_breakdown`. Read-only, fails open to an empty summary.
  - **Closes economy-audit Phase 1 (F1).** Remaining audit work is the deferred whole-game economist pass (`T2.ECON.review`) and the Drop 3 sink depth (3b/3c).
- **Validation (sandbox):** `py_compile` clean on all touched files. **80 tests passed** across this session's four drop test files **plus the drop1a ledger regression** (`test_drop1a_adjust_credits`), confirming the `adjust_credits` edit doesn't regress existing ledger behaviour. (Sandbox needed `aiosqlite`+`bcrypt` to exercise the real `Database`; a benign aiosqlite teardown ResourceWarning appears under the per-test event-loop harness — cleaner under Brian's pytest-asyncio config.) **Pending on Brian's box:** full ~4,854 suite; in-client smoke — `+finances` after some activity; `@economy throttle 50`, earn a mission reward, confirm it's halved on `@economy velocity` and a refund is unaffected; `@economy throttle 100` to restore.
- **Handoff:** `HANDOFF_drop_1c_finances_throttle_2026-06-02.md`

---

## 2026-06-02 — Drop 3b.1: ship ownership control gate (open boarding, gated control)

- **Wave:** Economy/security follow-up to Drop 3a. Brian flagged during 3a review that `owner_id` did no work in the control path — anyone could board a docked ship and fly off. 3a made it acute by parking valuable owned hulls at a public pad.
- **Files (source, 4):** `engine/ship_access.py` (**new** — pure policy helpers), `parser/space_commands.py` (gate `PilotCommand` + `LaunchCommand`), `parser/ship_crew_commands.py` (**new** — `+shipcrew`), `server/game_server.py` (register `+shipcrew`). **(tests):** `tests/test_drop3b1_ship_ownership_gate.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +23 — `test_drop3b1_ship_ownership_gate` (ShipAccessHelpers ×10, PilotGate ×5, ShipCrewRoster ×6, GateWiredStructural ×2).
- **What it shipped:**
  - **Model = open boarding, gated control** (Brian's pick). `board` stays open to anyone (preserves stowaway / passenger / piracy-attempt RP); only the **owner** or an **authorized crew member** may take the pilot seat (`pilot`) and `launch`. Resolved the `design_calls_pending_brian::T2.ECON.ship_ownership_gate` call.
  - **`engine/ship_access.py`** (pure, no I/O): `is_authorized_pilot(char_id, owner_id, authorized, *, is_admin)`, `get_authorized_pilots(systems)`, `add_/remove_authorized_pilot(systems, id)`. The allow-list lives in the ship's `systems` JSON under `authorized_pilots` — **separate from the volatile `crew` seat dict** so authorizations persist across crew changes / disembarks / reboots. Char ids are coerced (int vs str appear in different code paths). **Admin bypass** for staff.
  - **Unowned hulls fail open** (`owner_id` NULL/0 ⇒ anyone may fly): covers derelicts/salvage, the GCW seed/demo ships the space smoke suite flies, and the borrowed quest ship before its ownership transfer. **Every production player ship — brokerage, builder spawn, quest grant — is created with a real `owner_id`**, so the theft hole is closed wherever it actually exists. This choice is why the entire space smoke suite (S2–S10 board+pilot+launch on the unowned seed ship) passes **untouched**.
  - **`PilotCommand` gate** rejects unauthorized pilots before seating them (no state change); **`LaunchCommand`** re-checks at launch (defense-in-depth — closes the edge where the owner revokes a co-pilot who is already seated).
  - **`+shipcrew`** (aliases `shipcrew`, `+permit`, PLAYER): `+shipcrew` lists who is cleared to fly the ship you're aboard; `+shipcrew add <name>` / `remove <name>` let the **owner only** manage the roster (scoped to the ship whose bridge you're on, via `get_ship_by_bridge`).
- **Deferred (unchanged from 3a handoff):** 3b military procurement (faction-gated); 3b/3c sink depth (customization/paint/modules, vanity, gear insurance, repair backstop, catalysts, intel/Hutt/entertainer). A future polish item: let the owner manage the roster remotely (today it's scoped to being aboard).
- **Validation (sandbox):** `py_compile` + pyflakes clean on all touched files (space_commands.py's pre-existing legacy warnings are unrelated to the gate sites). `test_drop3b1_ship_ownership_gate`: **23 passed.** **Pending on Brian's Windows box:** full ~4,854-test suite incl. the space smoke scenarios (expected green given fail-open-on-unowned; watch for any test that seats a pilot on a ship it explicitly *owns* under a different char — none found in audit); in-client smoke (board your own ship → `pilot` works; have a second char try `pilot` → denied; `+shipcrew add <them>` → they can now `pilot`).
- **Handoff:** `HANDOFF_drop_3b1_ship_ownership_gate_2026-06-02.md`

---

## 2026-06-02 — Drop 0b + ledger completion (1.b.4) + 3a ship brokerage

- **Wave:** Economy audit remediation. One atomic drop honoring the master plan's hard-ordering rule — a re-opened faucet (0b) lands *with* its measurement (ledger) and its counterweight capital sink (3a) rather than in isolation.
- **Files (source, 5):** `engine/trading.py` (0b re-map), `engine/harvest.py` + `parser/shop_commands.py` (ledger), `parser/shipyard_commands.py` (**new** — 3a brokerage), `server/game_server.py` (register `+shipyard`). **(tests):** `tests/test_drop3a_shipyard_and_0b_remap.py` (**new**). **(bookkeeping):** `CHANGELOG.md`, `TODO.json`.
- **Tests:** +20 — `test_drop3a_shipyard_and_0b_remap` (TradeRemap0b ×5, LedgerBypassesClosed ×3, ShipyardCatalog ×4, ShipyardPurchase ×8).
- **What it shipped:**
  - **0b (TRADE_GOODS re-map):** all 8 trade goods re-pointed off the deleted GCW worlds (Kessel/Corellia) onto the six CW launch worlds per Economy Audit Appendix C. The dead map (only `luxury_goods` had a valid planet pair; everything else pointed at deleted worlds, so cargo income was silently suppressed) is replaced by a **connected web** — every CW world is now both a source and a demand of *something*. Also fixed stale `# 50%/200%` struct comments → `70/140` (the `PRICE_SOURCE=0.70`/`PRICE_DEMAND=1.40` constants were already correct; only the comments lied) and the `foodstuffs` "mining worlds" desc → "clone facilities and frontier worlds." Map change only; spread unchanged.
  - **Ledger completion (1.b.4):** **⚠ phantom-delivery finding** — the 1.b.2 entry (below) claims it migrated *harvest* and *shop upgrade* onto the chokepoint, and 1.b.3 claims the tree-wide `save_character(...credits...)` pin was green. At **this HEAD both were still RED**: `engine/harvest.py` (harvest payout faucet) and `parser/shop_commands.py` (vendor-droid upgrade sink) each still wrote credits via `save_character(credits=...)`, and the `vendor_droid_upgrade` source tag existed nowhere. Both now route through `adjust_credits` (new/owned tags: `harvest`, `vendor_droid_upgrade`). The tree-wide negative pin is re-asserted in this drop's test so it cannot silently regress again.
  - **3a (Kuat ship brokerage):** new `+shipyard` command (aliases `shipyard`/`+broker`/`+buyship`, PLAYER) at the Kuat Drive Yards merchant-house shipyards. Turns the inert `starships.yaml` catalog into a **live capital sink** (audit F2/F4). Civilian-only ladder, prices single-sourced from the registry's `ShipTemplate.cost`: Z-95 40k → Ghtroc 720 98.5k → YT-1300 100k → Firespray 120k → YT-2400 130k → Consular-class 1.5M (whale). Slug-bound rooms (broker: `kuat_deporin_shipyards`/`kuat_ileu_shipyards`/`kuat_ring_commercial`; delivery dock: first-present of `kuat_city_landing_pad`/`kuat_shuttle_bay`/`kuat_arrivals`). **Debit-first-then-refund**: credits sunk via `ship_purchase` *before* instantiation; any downstream failure refunds (`ship_purchase_refund`) and cleans the orphan bridge room — a failed delivery never charges. Instantiation mirrors the proven `spacer_quest` borrowed-ship path; boarding uses the existing multi-ship `board <name>`. `MAX_OWNED_SHIPS=8` room-spam guard.
- **Deferred (named, NOT in this drop):** **3b** = military procurement (Republic ARC-170/LAAT/V-19/Eta-2, CIS droid fighters — faction-membership/rank gated). **3b/3c** = ship customization/paint/livery/modules, vanity/regalia (title-gated), gear insurance, modest repair backstop (~5–8% hull; damcon stays free), crafting catalysts, spy intel-desk demand, Hutt-den treasury revenue, entertainer audience-weighting, Drop 2's deferred insurance payout. None required to *balance* 0b.
- **⚠ Flagged to Brian (open design call):** ship *ownership* is not enforced in the control path — `board` and `pilot` have **no owner/authorization check** (`pilot` only checks seat occupancy; `launch` requires being the pilot, but the seat is grabbable by anyone), so as it stands **anyone can board a docked ship and fly off with it**. `owner_id` does no work here today. 3a makes this more acute (valuable owned ships now park at a public pad). Recorded under `design_calls_pending_brian` (open vs gated boarding) and `tech_debt`. Proposed fix queued as the next drop pending Brian's model choice.
- **Validation (sandbox):** `py_compile` + pyflakes undefined-name scan clean across all 5 source files (only pre-existing "imported but unused" warnings remain). Tree-wide ledger pin → NONE. 0b web verified connected (zero non-CW planets; every world both source & demand). `test_drop3a_shipyard_and_0b_remap`: **20 passed**. **Pending on Brian's Windows box (ground truth):** full ~4,854-test suite; in-client smoke (buy a hull at Deporin & `board` it at the pad; run a `raw_ore` route Tatooine→Kuat; harvest and confirm `@economy` logs `harvest`/`ship_purchase`).
- **Handoff:** `HANDOFF_drop_0b_ledger_3a_shipyard_2026-06-02.md`

---

## 2026-06-01 — Drop 1.b.3: complete the credit-write migration (chokepoint everywhere)

- **Wave:** Economy audit remediation (Phase 1 / finding F1). Finishes the bulk migration onto `Database.adjust_credits` begun in 1.a/1.b.1/1.b.2 — per Brian's roll-up directive, the remaining work was consolidated into this one drop instead of further tranches.
- **Files (source, 22):** `engine/`: encounter_texture, encounter_anomaly, encounter_patrol, encounter_pirate, encounter_hunter, housing, buildings, hazards, sleeping, chain_rewards, intel_handlers, npc_space_traffic, tutorial_v2, wilderness_anomalies, spacer_quest, player_cities. `parser/`: space_commands, builtin_commands, smuggling_commands, bounty_commands, crafting_commands, mission_commands. **(tests/ledger):** `tests/test_drop1b3_ledger_migration_complete.py` (new), `tests/test_syn9_player_buildings.py` + `tests/test_f8c2d_chain_rewards.py` (stub fixes), `CHANGELOG.md`, `TODO.json`.
- **What it shipped:** Converted **all remaining credit-write sites** (~30) onto the chokepoint, so **every** credit movement under `engine/`+`parser/` now routes through `adjust_credits` (which performs the atomic `credits += delta` and writes `credit_log` internally). New/owned source tags: `space_encounter_reward`, `space_anomaly_reward`, `space_patrol_fine`, `space_pirate_extortion`, `space_hunter_bounty`, `space_hunter_settlement`, `housing_purchase`/`_deposit_refund`/`_rent`/`_rename`/`_upgrade`/`_refund`, `shopfront_purchase`/`_refund`, `player_building_construct`, `hazard_theft`, `theft_loss`/`theft_gain`, `chain_reward`, `intel_handover`, `npc_boarding_fine`/`npc_pirate_extortion`/`npc_pirate_bounty`, `tutorial_reward`, `wilderness_anomaly_reward`, `spacer_quest`/`spacer_quest_ship`, `ship_refuel`, `ship_weapon_purchase`, `space_fine`, `bacta_tank`/`bacta_tank_refund`, plus the previously-logged pairs folded in (`docking_fee`, `trade_goods`, `smuggling`, `smuggling_fine`, `bounty`, `resource_vendor`, `p2p_transfer`/`p2p_tax`). Combined-column writes (credits+equipment / credits+bounty) were split; `max(0,…)` fine clamps now log the **actual** deduction; the last `mission_commands` failed-check `else` re-save (a no-op for credits) was dropped. **New `city_tax` system sink:** `apply_city_tax` now records the city's slice as a `char_id=0` ledger entry — non-double-counting (system entries are excluded from player faucet/sink totals), mirroring `p2p_tax`, so the city-tax drain is legible by source on `@economy`. **[DECISION — Brian veto welcome]** Claude defaulted to YES on logging `city_tax`.
- **Invariant pinned:** `test_drop1b3` asserts **tree-wide** that no `save_character(... credits ...)` and no direct `log_credit(` call remains anywhere under `engine/`+`parser/` (only 2 rST docstring mentions allowed) — this single negative pin guards the *entire* migration (1.a→1.b.3) against regression.
- **Tests / validation:** `py_compile` + **pyflakes undefined-name scan** clean across all 22 files (pyflakes caught 4 dangling `new_credits` display refs from dropped locals — all fixed). Two test-harness `_MiniDB`/`_MockDB` stubs lacked `adjust_credits` and were given one (the full 28-file stub blast radius was checked; only these two reached a converted path). **Sandbox regression green:** the 4 ledger pins, `economy_validation`, `session51` (p2p tax), `pg1_death_a/b`, `pg2_pc_bounty_1/2`, `bounty_board_unit`, `syn6a/6c`, `syn5/7a/7b/8`, the 12-file village `f7*` batch, `syn9_player_buildings`, `f8c2d_chain_rewards`, `cities_phase4b` (city_tax) — **~1,400 tests**. **Not run in-sandbox** (heavy full-server harness boots that exceeded the sandbox timeout; deferred to Brian's Windows full run): `session39`/`session57a/b`/`session63` (space), `session46_encounter_dispatch`, `kd5b` (NPC traffic), `session55`/`session58`, `b1d2`, `q1_2`, `srb2`. Pyflakes-clean + stub-gap-closed make the residual risk low, but the full ~4,854-test suite is the ground truth.
- **Remaining in this wave:** **1.c** = `+finances` player command + `@economy throttle <pct>` (the `@economy` dashboard already exists from S51). Then 0b (TRADE_GOODS remap) and Drops 2–5. Tracked under `T2.ECON.ledger_chokepoint`.
- **Handoff:** `HANDOFF_drop_1b3_ledger_migration_complete_2026-06-01.md`

---

## 2026-06-01 — Drop 1.b.2: ledger migration tranche 2 (harvest + entertainer + shop upgrade + corpse refund)

- **Wave:** Economy audit remediation (Phase 1 / finding F1). Follows Drop 1.a (chokepoint) and 1.b.1 (crew + vendor).
- **Files:** `engine/harvest.py`, `parser/entertainer_commands.py`, `parser/shop_commands.py`, `engine/death.py`, `tests/test_drop1b2_ledger_tranche2.py`, `CHANGELOG.md`, `TODO.json`
- **Tests:** +3 structural-pin — `test_drop1b2_ledger_tranche2.py` (no credit-writing `save_character` remains in the 4 files; the 4 source tags present). Behaviour verified by the existing suites: `test_syn6a`/`test_syn6b` (harvest), `test_srb2_morale_aura` + `test_session58_cleanup_umbrellas` (entertainer perform + shop droid-upgrade), `test_pg1_death_b_loot_and_recovery` (corpse recovery), `test_economy_validation` — **278 green** in the combined run (with `test_drop1a`/`test_drop1b1`). `py_compile` clean on all 4 source files.
- **What it shipped:** The next priority groups in the bulk migration — **harvest** and **entertainer** — plus the vendor-droid **tier-upgrade** sink and the **corpse-credit-return** owner refund that was deferred from 1.a. **5 previously-UNLOGGED credit movements** now route through `adjust_credits`: `engine/harvest.py` → `harvest` (harvester payout faucet; the owner-tax leg already goes to the org treasury, not a wallet, so it's untouched here); `parser/entertainer_commands.py` → `entertainer_perform` ×2 (success + partial — each split the combined credits+attributes write into a `save_character(attributes=...)` plus the `adjust_credits` credit move); `parser/shop_commands.py` → `vendor_droid_upgrade` (droid tier upgrade sink, joins the vendor taxonomy); `engine/death.py` → `corpse_credit_return` (owner refund, keeps the owner-exists guard). All behaviour-preserving. **`engine/death.py` is now fully on the chokepoint** (zero credit-writing `save_character` calls).
- **Scope boundary (deliberate):** **1.b.3+** — the remaining unlogged sites: **city-tax** treasury sinks (`apply_city_tax` routes to an org/city treasury, not a wallet — needs a call on whether/how it should appear in `credit_log` as a system sink), **Director** flows, then the tail (`sleeping`/`hazards`/`buildings`/`housing`/`chain_rewards`/`intel_handlers`/`tutorial_v2`/`spacer_quest`/`npc_space_traffic`/`wilderness_anomalies`/`encounter_*` + `medical`/`sabacc`/`combat`/`spacer_quest` commands). Plus the still-pending already-logged-pair conversions (space/bounty/smuggling/builtin trade_goods; separated crafting `resource_vendor` + builtin p2p). **1.c** = `+finances` + `@economy throttle`. Tracked under `T2.ECON.ledger_chokepoint`.
- **Handoff:** `HANDOFF_drop_1b2_ledger_tranche2_2026-06-01.md`

---

## 2026-06-01 — Drop 1.b.1: ledger migration tranche 1 (crew wages + vendor-droid economy)

- **Wave:** Economy audit remediation (Phase 1 / finding F1) — `sw_mush_remediation_and_fun_additions_design_v1.md`. Follows Drop 1.a (the `adjust_credits` chokepoint).
- **Files:** `parser/crew_commands.py`, `engine/vendor_droids.py`, `tests/test_drop1b1_crew_vendor_ledger.py`, `CHANGELOG.md`, `TODO.json`
- **Tests:** +4 structural-pin — `test_drop1b1_crew_vendor_ledger.py` (no credit-writing `save_character` / no direct `log_credit` remains in the two files; the 7 source tags present). Behaviour verified by the existing suites that exercise these paths: `test_session39` (vendor droids), `test_cities_phase4` (vendor + city tax), `test_session56_craft_crew_umbrellas` (crew) — **133 green** in the combined run (with `test_drop1a`). `py_compile` clean on both source files.
- **What it shipped:** First tranche of the bulk write-site migration (Drop 1.b), in the doc's priority order. Instruments the first two groups — **crew wages** and the **vendor-droid player-shop economy** — moving **7 previously-UNLOGGED credit movements** onto `adjust_credits` so they finally appear in `credit_log` / the `@economy` dashboard: `parser/crew_commands.py` → `crew_wage` (first-day hire wage); `engine/vendor_droids.py` → `vendor_droid_deploy` (deploy cost), `vendor_purchase` (buyer sell-to-droid), `vendor_escrow_collect` (owner collects sale revenue), `vendor_buy_order_escrow` (owner funds a buy order), `vendor_buy_order_refund` (cancel refund), `vendor_buy_order_payout` (seller fills a buy order). Escrow is internal droid-object data, not a player wallet, so only the buyer **sink** and the owner/seller **faucets** are logged — no double-counting of the in-between hold. All conversions behaviour-preserving (default `allow_negative=True`; sites pre-check or previously allowed overdraw). Both files now have zero credit-writing `save_character` calls.
- **Scope boundary (deliberate):** **1.b.2+** continues the priority order with the remaining unlogged sites (shop ship-upgrade sink, harvest payout, entertainer ×2, city-tax sinks, Director flows, then the encounter/wilderness/tutorial/etc. tail incl. `death.py:778` owner-refund) plus the still-pending already-logged-pair conversions (space `docking_fee`+`trade_goods`, bounty, smuggling ×2, builtin `trade_goods`; separated: crafting `resource_vendor`, builtin p2p batch). **1.c** = `+finances` + `@economy throttle`. Tracked under `T2.ECON.ledger_chokepoint`.
- **Decisions recorded this session:** **0a-2 starter-quest broker = option b** (non-canon Kuat KDY broker; leave Lira Shan for *From Dust to Stars*) — resolved. **GCW retirement = approved but deferred** to preserve ledger-wave momentum (`T2.CW.gcw_retirement` → `approved_deferred`; runs as its own deletion drop later, which will then close `T2.CW.spec_config_cleanup` and retire the org-axis rewicker).
- **Handoff:** `HANDOFF_drop_1b1_crew_vendor_ledger_2026-06-01.md`

---

## 2026-06-01 — Drop 1.a: economy ledger chokepoint (`adjust_credits`)

- **Wave:** Economy audit remediation (Phase 1 / finding F1) — `sw_mush_remediation_and_fun_additions_design_v1.md`
- **Files:** `db/database.py`, `engine/death.py`, `parser/mission_commands.py`, `parser/pc_bounty_commands.py`, `tests/test_drop1a_adjust_credits.py`, `CHANGELOG.md`, `TODO.json`
- **Tests:** +14 — `test_drop1a_adjust_credits.py` (faucet/sink/system-sink, atomic-increment compounding, `allow_negative` guard ×5, end-to-end `get_credit_velocity` reflection, + `TestDrop1aMigrationComplete` structural pin). Targeted regression **262 green** (`test_session51_economy_hardening`, `test_economy_validation`, `test_pg1_death_a/b`, `test_pg2_pc_bounty_session1/2`, `test_pg2_pl_post_launch`, `test_insurance_debt_gate`, `test_b1e_missions_era_aware`, `test_bounty_board_unit`) — the PG.2 insurance-payout/partial-debt tests exercise the converted `death.py` paths end-to-end against the real schema. `py_compile` clean on all 5 source files; sandbox-only deps installed for the run (aiosqlite/bcrypt/aiohttp/pytest) — present on the Windows box.
- **What it shipped:** The economy audit's headline finding (F1: ~80% of credit-moving code bypasses the `credit_log`, so the money supply is unmeasurable). New `Database.adjust_credits(char_id, delta, source, *, allow_negative=True) -> Optional[int]` — the single sanctioned way to move credits: an **atomic** `UPDATE characters SET credits = credits + ?` (race-safe, not read-then-set) → read-back authoritative balance → `log_credit` (best-effort) → return new balance. `char_id == 0` is the **system faucet/sink** path (no row touched, logged with `balance=0`, returns `0`); `allow_negative=False` refuses an overdraw (returns `None`). Drop 1 is split — this is **1.a (seam + proof)**: build the chokepoint and convert a representative set covering every call shape (DB-fetched dict, session dict, system sink, guarded sink). **10 currently-logged movements** converted off the drift-prone manual `save_character(credits=) + log_credit()` pair (2 non-atomic commits) onto `adjust_credits`: `death.py` ×4 (insurance hit / partial / BH payout / guild-treasury system sink), `pc_bounty_commands.py` ×4 (`_debit_credits` now uses the `allow_negative=False` guard — behaviour-exact; `_credit_credits`; `bh_insurance_pay`; `bounty_expire_refund`), `mission_commands.py` ×2 (`_resolve_ground_reward` preserves *log-iff-`earned>0`*; `_award_credits`). `log_credit` call count in all three converted files is now **0** — everything routes through the chokepoint.
- **Scope boundary (deliberate):** **1.b** = migrate ALL remaining credit-write sites per the doc order (crew→vendor→harvest→entertainer→city-tax→Director→rest) — the six clean logged pairs not yet converted, the two separated logged pairs (crafting `resource_vendor`, builtin p2p batch), and the ~30-file unlogged tail (full inventory in the handoff §3); **1.c** = `+finances` player command + `@economy throttle <pct>` (the `@economy` dashboard already exists from S51 — only those two surfaces are missing). Tracked as `T2.ECON.ledger_chokepoint`.
- **Pre-flight finding (killed the originally-picked 0a-4):** symbol-level pre-flight overturned **0a-4 (Imperial/`empire` residue sweep)** — the `empire`/Kessel/Corellia blocks in `organizations.py` + `housing.py` are **not dead CW residue**; they are **live, test-pinned GCW-era config** (the GCW half of era-mirrored tables, reachable via `main.py --era gcw` against the full `data/worlds/gcw/` tree, pinned by ~8 byte-equivalence tests incl. `test_b1b2`/`test_b1d1`/`test_f5b3a`). CW-runtime safety is already handled by `apply_org_rewicker` + era-gating. So deleting them is **not** a low-risk sweep — it requires a **GCW-retirement decision** (new `T2.CW.gcw_retirement`, pending Brian). `T2.CW.spec_config_cleanup` corrected accordingly; `T2.CW.codebase_era_sweep` given a GCW-exclusion caution.
- **Handoff:** `HANDOFF_drop_1a_ledger_chokepoint_2026-06-01.md`

---

## 2026-06-01 — CW era-compliance: space catalog, zone authority, faction missions

- **Files:** `engine/starships.py`, `engine/npc_space_traffic.py`, `engine/encounter_patrol.py`, `engine/encounter_anomaly.py`, `engine/spacer_quest.py`, `engine/smuggling.py`, `engine/missions.py`, `parser/space_commands.py`, `parser/smuggling_commands.py`, `data/worlds/clone_wars/space_zones.yaml`, `tests/test_b1e_missions_era_aware.py`, `tests/test_session38.py`, `tests/test_session49_faction_missions.py`, `CHANGELOG.md`, `TODO.json`
- **Tests:** 89 green in the core batch (`test_b1e` 17, `test_session38` 32, `test_session49` 20, `test_cw_ships` 20); 149/150 green in the broader space regression batch (the 1 failure is a **pre-existing flaky** RNG-threshold test, `test_session38::test_security_scaling`, in the untouched `texture_encounter_tick`/`space_encounters` path — fails ~4/5 runs independent of this drop). `node --check` n/a (no JS touched). `py_compile` clean on all 9 source files.
- **What it shipped:** Closes the era-fidelity gap flagged by an external audit ("CW space never wired / still GCW"). The audit was half-right: the *plumbing* was already CW (active_era=clone_wars, era-aware ship loader, 14 CW hulls live), but the *content* flowing through it was GCW. Four fixes: **(A) Ship registry era-cleanliness** — `ShipRegistry.apply_era_hints` now drops the `registry_hints` junk pseudo-template and enforces `excluded_global_keys`, removing the 10 GCW hulls (TIE variants, X/A/B-wing, ISD, Nebulon-B, Lambda, Sentinel) that were live and `@spawn`-able; `@spawn` help examples de-GCW'd. **(B) CW zone graph wiring** — the hardcoded GCW zone graph in `npc_space_traffic.py` (Tatooine/Nar Shaddaa/Kessel/Corellia) became the `_GCW_*` fallback; the live graph now loads from `data/worlds/clone_wars/space_zones.yaml` (24 zones, all 6 launch planets, canonical lanes) with a new `authority` field per zone (republic/cis/hutt/contested). Mission zone pools (`missions.py`) and smuggling dock zones (`smuggling.py`) now derive from the live graph instead of naming dead GCW zone ids. **(C) Zone-based patrols + flavor** — the single global `tie_fighter` "Imperial Sector Patrol" became per-authority patrol templates (Republic→ARC-170, CIS→Vulture droid, Hutt→Z-95, neutral→Consular cruiser) selected by the spawn zone's authority; hail/boarding/anomaly/smuggling-patrol player strings are now authority-aware or CW-neutral (no Imperial/ISB/stormtrooper). **(D) Faction missions + spacer quest** — `FACTION_MISSION_CONFIG` is now exactly the five canonical CW slugs (`republic`, `cis`, `jedi_order`, `hutt_cartel`, `bounty_hunters_guild`) from `organizations.yaml`, each pointing at era-clean objective tables; the legacy `empire`/`rebel`/`hutt`/`bh_guild` keys and `_EMPIRE_OBJECTIVES`/`_REBEL_OBJECTIVES` tables are removed (characters migrate to CW slugs on login via `apply_org_rewicker`). The spacer-quest completion banner triad ("Rebel Cell · Imperial Service · Underworld" → "Republic Service · Separatist Contracts · Underworld") and Empire/Rebellion dialogue are pivoted to Republic/Confederacy.
- **Scope boundary (deliberate):** This drop covers the **space + missions** subsystems only. Two CW-compliance items are NOT in this drop and are tracked in TODO: `organizations.py`'s `_SPEC_CONFIG_BY_FACTION` still carries a live `empire` chargen block (stormtrooper/tie_pilot), and no full codebase-wide Imperial/Rebel/TIE sweep has been run. See `T2.CW.spec_config_cleanup` and `T2.CW.codebase_era_sweep`.
- **Handoff:** `HANDOFF_drop_cw_era_compliance_space_missions_2026-06-01.md`

- **Files:** `engine/crafting.py` (`check_resources`), `parser/crafting_commands.py` (`ResourcesCommand`, `SchematicsCommand`, `CraftCommand`), `tests/test_crafting_discoverability.py`, `TODO.json`, `CHANGELOG.md`
- **Tests:** +13 — `test_crafting_discoverability.py` (5 `check_resources` diagnostic + 3 schematics-listing + 2 resources-listing + 1 craft-skill + 2 craft-resolves). Neighbor batch 488 green (crafting / command-umbrella / economy / cooldown). Existing `test_syn6c` stays 40 green (Bug A message kept compatible — still names the resource type).
- **What it shipped:** Closes `T2.DEF.t5_discoverability` plus **four** adjacent live bugs, all rooted in `parser/crafting_commands.py` having drifted out of sync with the engine/data schema (`components` / `quantity` / `skill_required`). **Bug D (severe, pre-existing — the `craft` command was non-functional end-to-end):** it passed `quality_base` (a float) to `resolve_craft`, which expects a `SkillCheckResult`, so *every* craft with materials in hand raised `AttributeError: 'float' object has no attribute 'fumble'`. It survived only because no test ran the command **through** `resolve_craft` (the unit tests call `resolve_craft` directly with real result objects). Now passes the result object; the except-branch fallback builds a clean auto-success `SimpleNamespace` instead of `None`. **Bug C:** `CraftCommand` rolled `schematic.get("skill", "repair")` — a key no schematic carries — so every craft rolled a non-existent "repair" skill and dropped to the `[auto]` quality-60 path, divorcing craft quality from the crafter's skill; now rolls `skill_required` (blaster_repair, craft_lightsaber, …). **Bug B1:** the `schematics` listing read `resource_requirements` (always `{}`) + `skill`, printing "Needs: none" under "[craft]" for all 38 recipes; now reads `components` + `skill_required`, shows each component's min-quality, and prefixes a `[*]` craftable flag. **Bug B2:** the `resources` listing read `r['amount']` via hard bracket access but stored stacks use `quantity` → `KeyError` crash whenever a player with resources ran it; now reads `quantity`. **Bug A (the discoverability item):** `check_resources` reported quality-blocked failures as count shortfalls ("3x more kyber" while you hold 5× q72 and need q75); now distinguishes QUANTITY-blocked ("need Nx — you have none") from QUALITY-blocked ("have 5× but only 0× at q75+, best grade q72 — refine or survey higher-grade").
- **Handoff:** `HANDOFF_drop_crafting_repair_discoverability_2026-05-31.md`

---

## 2026-05-31 — Drop 4.22: live wilderness region resolution for the ⊕ region map

- **Files:** `server/session.py` (`_hud_area_map`), `static/client.html` (region-map resolution + palette), `tests/test_drop422_wilderness_region_hud.py`, `tests/spa/test_m3_region_map_live.py`, `tests/spa/test_env_substrate_wireup.py`, `tests/spa/test_client_wireup_42a.py`
- **Tests:** +8 — `test_drop422_wilderness_region_hud.py` (always-present `wilderness_region_id`, registry-gated consistency, failure tolerance); 3 pre-existing SPA tests re-pinned for the new resolution path. 190 in-scope pytest green; `node --check` clean on all touched JS.
- **What it shipped:** A live player could not reach the Coruscant Underworld painting via the ⊕ region map — `openRegionMap` resolved the region from `_sw_areaGeom`, which is **null for wilderness rooms** (overview YAMLs carry `landmarks:`, not the `rooms:` / `planet` / `era` / `palette` an AreaGeometry needs), so ⊕ always fell back to the Dune Sea default. Fix rides the always-present `rooms.wilderness_region_id` column (== `region.slug` for wilderness): the server stamps it on the HUD area-map path every tick, the client captures `_sw_wildernessRegion` and feeds it to `regionKeyForArea` preferentially (which already accepts a bare slug), and the palette resolver leads with a coruscant-prefix branch. Pure additive; `renderMapV2` and the registry-gated `player_position` path untouched. Verified with a runtime consume-path probe against the real `m3_adapter.js` (all 7 inputs resolve correctly). **NOTE:** this is the CHANGELOG/TODO entry that drop 4.22's own zip omitted — recorded here.
- **Handoff:** `HANDOFF_drop_4_22_wilderness_region_resolution_2026-05-31.md`

---

## 2026-05-30 — Housekeeping: delete orphan `parser/admin_fp_commands.py` (clears a baseline failure)

- **Files:** `parser/admin_fp_commands.py` (**deleted**), `sw_d6_mush_architecture_v51.md` (§1.3, standalone), `TODO.json`, `CHANGELOG.md`
- **Tests:** clears 1 pre-existing failure — `test_wow3c_dsp_fp_wiring.py::TestNoLeftoverAdminFpModule::test_admin_fp_module_removed` (the file is now 27/27 green, was 26 + this failing).
- **What it shipped:** Deleted the orphan `parser/admin_fp_commands.py`. Its `@fp` admin surface (GM grants/deducts Force Points, with the Weight-of-War §7.2 award multiplier) had already been folded into `@weight <name> fp <delta> [for <reason>]` as the `fp` subform during the WoW.4 consolidation — the live `@weight fp` path still carries the same `engine.weight_of_war.fp_award_after_weight` scaling, so the deletion removes **zero** live functionality. Pre-flight: `server/game_server.py` already had no reference (the test's second assertion), and a full-tree grep (`--include=*.py`, excluding the module and the removal test) found **zero** other importers. The removal test had been a carried-forward baseline failure listed in v51 §1.3; it now passes, and all weight/WoW suites stay green (248 passed across `test_wow*`).
- **Handoff:** `HANDOFF_OBJECTIVE_AND_VENDOR_POI_20260530.md` (rolled into the same session's combined drop)

---

## 2026-05-30 — POI feed completed: objective + vendor kinds on the map

- **Files:** `server/session.py` (`_build_area_pois`), `engine/missions.py` (`MissionBoard.refresh`), `tests/test_poi_feed.py`, `sw_d6_mush_architecture_v51.md` (delivered standalone, outside the code tree), `TODO.json`, `CHANGELOG.md`
- **Tests:** +20 — `test_poi_feed.py` (8 objective + 7 vendor sweep cases, incl. all-four-kinds-coexist, plus 5 lazy-rooms/static guards). Whole file 17→37.
- **What it shipped:** Wired the **last two runtime POI kinds** onto the map's `L_Entities` layer, completing the dynamic feed (it now renders **all four** room-anchored kinds it was built to carry: bounty + anomaly + vendor + objective). Both in the proven "renderer was already there, only the server enumeration was missing" shape — **zero JS** (verified byte-identical to HEAD), schema-neutral. (1) **Objective** (personal): `_build_area_pois` reads `self.character`, finds that character's `ACCEPTED` missions, and places a green-star `{kind:"objective"}` on each `destination_room_id` in view. Pre-flight grep-HEAD overturned the prior handoff's premise that "missions carry a destination name, not a room id" — `Mission.destination_room_id` already existed and was populated; only the enumeration was missing (Pattern 3, inverted-narrative). Enabling co-fix: `MissionBoard.refresh` lazily fetches the room list when filling the board (gated on `needed > 0` → zero per-tick DB cost), so tick-spawned missions also carry a destination. (2) **Vendor** (area-state, joins bounty/anomaly): one batched `SELECT room_id FROM objects WHERE type='vendor_droid' AND room_id IN (…)` (the contacts-NPC no-storm pattern), `{kind:"vendor"}` on each placed shopfront in view; unplaced droids (`room_id` NULL) excluded by the filter. Only mission-**giver** pins remain unwired (a giver is a name, not a room). Also folded both into `sw_d6_mush_architecture_v51.md` §1.4-F / §1.5 / §3 / §10.6, and recorded a dependency surfaced in pre-flight: the intel-handler seeding's HQ rooms are *dynamically created* (`engine/housing.py`, `organizations.hq_room_id` FK), not statically seeded — so that follow-up must resolve the live room id, not a YAML-fixed one.
- **Handoff:** `HANDOFF_OBJECTIVE_AND_VENDOR_POI_20260530.md`

---

## 2026-05-30 — Design-call resolutions recorded (§8.7, §8.13, §8.16) + §8 hygiene

- **Files:** `sw_d6_mush_architecture_v51.md`, `TODO.json`, `CHANGELOG.md`
- **Tests:** none (doc/tracker-only).
- **What it shipped:** Recorded three Brian design decisions in v51 §8 and propagated them to §1.5/§3/§7/§10: **§8.13** Coruscant Underworld → author the **full 40×40×3 region file** (now Tier 2 #4 content build, no longer a design call); **§8.7** SYN.4 city-dissolution migration → **run now, as part of this deploy** (admin `syn4_migrate_dissolve_city_map_cities`, idempotent, 75% refund); **§8.16** web-client launch scope → **pull a selected Phase 2 panel subset into launch** (candidates already built in the SPA suite; rest of Phase 2 + Phases 4/5 post-launch). Also closed **§8.10 / §8.15 / §8.17** as moot (map renderer + web port shipped; SYN ran to completion). `TODO.json`: dropped the moot map-port green-light (T2.6/7/8) from `design_calls_pending_brian`; added the four resolutions to `design_calls_resolved_recent`. Three smaller design calls remain open + **non-blocking**: T2.5 (Coruscant zone naming), T2.10.c (SRB.1 overdose auto-incap), T2.11.b (broaden morale-flavored skill set).
- **Handoff:** `HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_20260530.md`

---

## 2026-05-30 — Architecture doc v51 (full consolidation; closes TD.ARCH_V51)

- **Files:** `sw_d6_mush_architecture_v51.md` (new; supersedes v50 — lives outside the code tree, like all architecture docs), `TODO.json`, `CHANGELOG.md`
- **Tests:** none (doc-only).
- **What it shipped:** Wrote `sw_d6_mush_architecture_v51.md`, rolling up everything since v50: the **SYN tail** (SYN.6→SYN.10, which shipped 2026-05-25 but post-dated the v50 doc), the **SPA visual port** (Tier-1 #4, drops 4.11→4.15 cutover), the **v51 hybrid raster substrate map lane** (six maps painted + four new areas + cardinal fixes + Mos Eisley relayout + `L_SubstrateRooms`), **map A/D/B + env/bearing + the POI feeds**, and this session's HUD fix + RELAYOUT rebase + tracker backfill. Header/§0 rewritten; §1.3 code-state re-grounded at HEAD May 30 (schema-neutral at 35); §1.4 "what landed since v50"; §1.5 trimmed (SYN + SPA port moved to done); §2.5/§2.6 (SPA module suite + painted maps); **new invariant §4.28** (hybrid raster substrate render contract); §3 roadmap re-ranked (engine + web-client lanes now CLOSED for launch; browser smoke-test is the top remaining item); §9 version history; §10 closing. Flipped `TODO.json` `architecture_of_record` v50→v51 and resolved `TD.ARCH_V51`; updated the CHANGELOG companion-line header to v51.
- **Handoff:** `HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_20260530.md` (§4 + the v51 note)

---

> **⚠ Ledger backfill (reconstructed 2026-05-30).** The drop ledger lapsed
> between 2026-05-25 (SYN.10) and 2026-05-30 — the SPA visual port, the v51
> substrate migration, and the map/POI work below were delivered without
> contemporaneous CHANGELOG/TODO entries. The four entries immediately below
> were **reconstructed on 2026-05-30** from first-party handoff docs
> (`MAP_NAV_OVERLAY_DROP_20260529.md`, `NANO_MAP_PACKAGE.md`,
> `HANDOFF_MAP_ENV_BEARING_POI_20260530.md`) plus symbol-level grep of HEAD.
> Files/tests are HEAD-verified facts; some **dates are approximate** (marked)
> and exact per-drop boundaries for the SPA port are best-effort. Discipline
> (`tracker_update_in_same_drop`) resumes from 2026-05-30.

---

## 2026-05-30 — Anomaly POI feed + HUD resilience fix + RELAYOUT test rebase

- **Files:** `engine/area_loader.py`, `server/session.py`, `tests/test_poi_feed.py`, `tests/test_fmap1_area_geometry_loader.py`, `tests/test_fmap2_area_geometry_registry.py`, `tests/test_fmap2_session_hud.py`, `tests/test_fmap6_session_contacts.py`, `tests/test_area_loader_substrate.py`
- **Tests:** +11 (`test_poi_feed.py` anomaly sweep); 8 RELAYOUT tests rebased to v51-substrate geometry. Sandbox: 88 passed in the 5 formerly-failing files; 164 passed/10 skipped in the map/HUD/area/env/bearing/poi/substrate sweep; 159 passed/1 skipped in the DB-backed session sweep. Zero regressions (cross-checked vs pristine HEAD).
- **What it shipped:** (1) Dynamic POI feed now emits live wilderness anomalies (`anomaly_t1/t2/t3`, incl. Tier-3 world boss) onto the map's `L_Entities` layer alongside bounties — `_RoomLookupEntry` gains a free `region_slug` (captured off the row `resolve_area_room_ids` already fetches; zero extra DB), and `_build_area_pois` groups covered regions in-memory and maps each anomaly's `anchor_room_id` → render coords. No JS changed (renderer/adapter were already done). (2) HUD resilience fix: the env-substrate drop had hoisted `row = await db.get_room()` out of the F.MAP.2 try, so a `get_room` failure crashed the whole HUD push; now guarded → degrades to the legacy `area_map`. (3) Rebased the 8 tests broken by the v51 substrate relayout (bounds, exit_paths→0, labels→2, slug-count re-targeted to Mos Eisley's own rooms now that the registry is multi-area, `docking_bay_94_pit`/`spaceport_row`/`cantina` coords, and the senate-substrate test flipped to declare its substrate).
- **Handoff:** `HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_20260530.md`

## 2026-05-30 — Map A+D+B + environment + bearing + bounty POI feed

- **Files (reconstructed):** `engine/world_time.py` (new), `engine/bearing.py` (new), `engine/area_map.py`, `server/session.py`, `static/client.html`, `static/spa/m3_adapter.js`, `parser/builtin_commands.py`, `tools/check_map_cardinals.py`, `data/worlds/clone_wars/planets/{tatooine,nar_shaddaa}.yaml`
- **Tests (reconstructed):** `test_area_map_emits_slug`, `test_map_cardinals_reverse`, `spa/test_clickwalk_slugjoin`, `spa/test_map_label_lod`, `test_world_time`, `spa/test_env_substrate_wireup`, `test_bearing`, `test_bearing_wireup`, `test_poi_feed` (bounty v1).
- **What it shipped:** Map A (click-to-walk reachability via slug-join; vertical exits clickable + badges); Map D (zoom-reveal room labels, constant on-screen font); Map B (geometry-true direction words + forward/reverse cardinal gate). Phase-1 environment substrate (time-of-day day-cycle + override, weather; server emit, client read) and bearing substrate (facing from last planar move; `attributes.bearing`; self-chevron rotate). Dynamic POI feed v1: posted bounty contracts whose `target_room_id` is in the covered area → `{kind:"bounty", x, y}` on `L_Entities`.
- **Handoff:** `HANDOFF_MAP_ENV_BEARING_POI_20260530.md`

## 2026-05-29 — v51 hybrid raster substrate migration (six maps) + cardinal fixes + Mos Eisley relayout + micro-overlay

- **Files (reconstructed):** all six `data/worlds/clone_wars/maps/*.yaml` gain `substrate_image`; six painted PNGs in `static/maps/` (`mos_eisley_/coruscant_senate_/kuat_city_/nar_shaddaa_/geonosis_stalgasin_/kamino_tipoca_substrate.png`); 4 new painted areas (`kuat_city`, `smugglers_moon`, `stalgasin_hive`, `tipoca_city`) + their planet YAMLs (`kuat`, `nar_shaddaa`, `geonosis`, `kamino`); `static/spa/m3_composition_engine.js` (`L_SubstrateRooms` + tier-driven substrate dim); `tools/check_map_cardinals.py`, `tools/apply_cardinal_fixes.py`, `tools/relayout_map.py`; cardinal fixes in `data/worlds/clone_wars/planets/{coruscant,nar_shaddaa}.yaml`; Mos Eisley map relaid (Philosophy A).
- **Tests (reconstructed):** `test_area_loader_substrate` (substrate_image field), `spa/test_m3_substrate_hybrid`, cardinal-gate tooling tests.
- **What it shipped:** Migrated the entire CW map set to the architecture-v51 hybrid raster lane — a pre-painted substrate under the SVG overlay; the client skips procedural district/building/street/furniture layers (baked into the painting) and keeps labels/entities/weather/chrome on top. Cardinal pre-flight made gameplay compass words agree with rendered geometry (Coruscant 7 fixes, Nar Shaddaa 5 fixes via Philosophy B; **Mos Eisley relaid via Philosophy A** — 48/48 cardinal exits, which **dropped its `exit_paths` to 0 and street labels** since straight ribbons tangle post-relayout and aren't used under a substrate). Micro-overlay `L_SubstrateRooms` paints translucent tactical room cells at close zoom (precise `data-room-id` click targets) over a dimmed painting.
- **Handoff:** `MAP_NAV_OVERLAY_DROP_20260529.md`, `NANO_MAP_PACKAGE.md`
- **NOTE:** these docs name `sw_d6_mush_architecture_v51.md` as the architecture-of-record, but no v51 doc exists in the tree and `TODO.json` still points to v50 — **architecture-of-record update to v51 is an open item.**

## 2026-05-26 → 2026-05-28 (approx) — SPA visual port (Tier-1 #4): tier-body modules + production cutover + showToast fix

- **Files (reconstructed):** `static/spa/m3_tier_galaxy_body.js` (474 LOC), `m3_tier_system_body.js` (470), `m3_tier_planet_body.js` (623) [Drop 4.13]; `m3_tier_city_body.js` (481), `m3_tier_wilderness_body.js` (507), `m3_tier_interior_body.js` (451) [Drop 4.14]; `m3_tier_registry.js` (canonical `getTierRenderer`) [Drop 4.15 cutover]; earlier in the port: `m3_skill_check.js` [4.11], `m3_sheet.js` patch + `m3_assembled_client.js` [4.12a/b]; `static/client.html` (showToast hotfix).
- **Tests (reconstructed):** per-tier test files `tests/spa/test_m3_tier_{galaxy,system,planet,city,wilderness,interior}_body.py` + `test_m3_tier_registry.py` (loud-substitution / absent-palette-key + era-cleanness + Q1 canonical-name pins).
- **What it shipped:** Ported the JSX prototype map UI into self-contained vanilla-JS SPA tier-body builders for all six map tiers (galaxy/system/planet/city/wilderness/interior), then wired `M3MapNavigator.getTierRenderer` to the canonical `M3TierRegistry` so the visual port renders end-to-end. Fixed the `showToast` `Unexpected token 'function'` browser syntax error. Defensive DI (try/catch) for optional composition-engine helpers; labeled-fallback chrome.
- **Handoff:** (drop handoffs not retained in tree; reconstructed from grep HEAD + session memory)

---

## 2026-05-25 — SYN.10 (Display integration + launch polish — FINAL SYN drop)

- **Wave:** SYN sequence — final drop. Per `contestable_wilderness_design_v2.md` §2.6 + §3.12. **Closes the SYN wave.** Architecture v49 rollup + T2.ECON.review open next.
- **Files:**
  - `engine/territory_display.py` (new, ~890 LOC): canonical display-rendering module. Public surface — `get_region_data_block(db, region_slug)` returns structured dict (the web-UI data contract); `get_region_look_block(db, region_slug, *, viewing_org_code, ansi)` returns CLI ANSI lines; `get_faction_contests_lines/data(db, org_code)` and `get_faction_resource_outlook_lines/data(db, org_code)` are faction-scoped. 6 news-format helpers — `format_ownership_change_news`, `format_contest_start_news`, `format_contest_resolve_news`, `format_anomaly_defeat_news`, `format_building_completion_news`, `format_building_demolition_news`. Centralized ANSI palette via 8 module constants (`_RED`, `_YELLOW`, `_GREEN`, `_CYAN`, `_MAGENTA`, `_BOLD`, `_DIM`, `_ITALIC`). All renderers accept `ansi=False` for plain-text mode. Read-only — pure rendering; no state mutation. Failure-tolerant: every sub-section (ownership, influence, outlook, contest) wraps in its own try/except so partial data still produces a valid output.
  - `parser/region_commands.py` (new): `RegionCommand` (key `+region`, aliases `+reg`). With no args: resolves caller's current region via `wilderness_movement.get_wilderness_coords` then falls back to `territory._resolve_room_region` for sentinel rooms. With slug arg: looks up any wilderness region. Both paths render via `get_region_look_block` with the viewer's `faction_id` for highlight.
  - `parser/builtin_commands.py` (modified, +30 LOC in `_look_wilderness`): region info block auto-injects between the security/movement tag block and adjacent-terrain compass. Reads viewer's `char.get("faction_id")` for own-faction influence highlight. Failure-tolerant — any error silently no-ops so the wilderness look proper never breaks.
  - `parser/faction_commands.py` (modified, +75 LOC): `+faction contest` + `+faction resource_outlook` subcommands wired into the existing `FactionUmbrellaCommand` dispatcher via `_FACTION_SWITCH_IMPL`. Aliases: `contests` → `contest`, `outlook`/`resource`/`quality` → `resource_outlook`. Independent-rejection: both surfaces require a faction membership and refuse the `independent` placeholder.
  - `engine/territory.py` (modified, +28 LOC): `claim_region` and `unclaim_region` return dicts now include an optional `news` field with the pre-formatted news text. Existing callers that only check `ok` and `msg` are unaffected.
  - `engine/wilderness_anomalies.py` (modified, +38 LOC): new `_broadcast_anomaly_defeat` helper called at the end of every payout path (T1 single-character + T2/T3 multi-participant). Best-effort: missing `session_mgr` or missing org-name lookup silently no-ops.
  - `engine/buildings.py` (modified, +30 LOC): `_complete_construction` adds a global broadcast for `garrison_annex` category only (other categories stay owner-only — private investment signal). Two new resolver helpers: `_resolve_region_for_building`, `_resolve_char_name`.
  - `server/game_server.py` (modified, +2 LOC): imports `register_region_commands` and calls it during bootstrap (alongside the existing anomaly + player-building registrations).
  - `tests/test_syn10_display_integration.py` (new, ~1100 LOC, 43 tests across 10 sections): TestNewsFormatters (12 — all 6 helpers × 2 variants each), TestRegionDataBlock (6 — shape, YAML fields, ownership tier from influence score, no-ownership case, influence sort-desc, unknown-region safe), TestRegionLookBlockRender (5 — header, ownership, influence, outlook, active-contest panel), TestFactionContestsData (3 — as challenger, as defender, empty), TestFactionContestsLines (2 — empty message, listed contest), TestResourceOutlookData (2 — owned regions, non-owner empty), TestResourceOutlookLines (2 — empty, populated), TestAnsiToggle (4 — region look + contests + outlook all strip color with ansi=False), TestClaimUnclaimNewsField (2 — format helpers for claim/unclaim), TestBuildingBroadcastHook (5 — resolver helpers importable + functional). **5/5 deterministic on first run, no debug iterations needed.**
- **Tests:** +43. **5/5 deterministic.** Full SYN family (test_syn1a..test_syn10): 637 → 680 tests green (+43), zero regressions. Combat-adjacent (wow3a, wow3b, pvp_flag, sess54_combat_umbrella): 81 tests green. City-substrate (cities_phase1-6, cities_help_topics): 437 tests green. Build pass A: 8 tests green. **Total cross-cutting sweep: 1,206 tests green, zero regressions.**
- **UI pivot bridge — design content for incoming web UI work:**
  - **Data contract** is `engine/territory_display.py` — structured-dict accessors are the canonical web-UI input. Top-level keys are documented in each function's docstring; stable shape pinned by tests.
  - **ANSI palette** centralized so the UI work can map 8 color tags to semantic CSS classes in one pass: `_RED` → security-lawless / threat, `_YELLOW` → security-contested / warning, `_GREEN` → security-secured / success, `_CYAN` → accent / heading, `_MAGENTA` → contest panel, `_BOLD` → emphasis, `_DIM` → subtle metadata, `_ITALIC` → descriptive flavor.
  - **News event taxonomy** (6 types): ownership change (claimed/lost/unclaimed), contest start, contest resolve (defender/challenger), anomaly defeat, building completion, building demolition (demolished/evicted). Each has a `format_*_news` helper returning a stable string. UI news ticker can consume the strings directly, or rebuild from raw event data using the same templates.
  - **Surfaces inventory for UI consumption:**
    - Region look block (auto in wilderness look + explicit `+region`)
    - `+faction contest` (active contests, both as challenger and as defender)
    - `+faction resource_outlook` (weekly digest of owned regions)
    - News broadcasts via `session_mgr.broadcast` (the UI work decides whether to surface these as toasts, ticker, log, etc.)
- **Design decisions documented in code comments:**
  - Influence tier thresholds from `_influence_tier`: `>=100` = dominant, `>=50` = foothold, else = no_presence. Bar width default 20 chars.
  - Ownership tier derives from the *org's actual zone-keyed influence score*, NOT from a column on `region_ownership` (which doesn't have one). `get_territory_influence(org, zone)` is the source of truth.
  - Region "active contest" panel uses `region_contests.ends_at - now` for time remaining (the real schema uses `started_at`/`accumulation_ends_at`/`ends_at`; the `accumulation_ends_at` would be the more accurate "culminating fight begins" mark but is not what the design surfaces).
  - Accumulation falls back to zone influence rather than a per-contest table column — there's no per-contest accumulation column; the contest tick reads zone influence as the canonical source.
  - News broadcasts for ownership change ship the `news` text in the return dict; the parser command that called `claim_region`/`unclaim_region` is responsible for the actual `session_mgr.broadcast` since engine.territory has no session_mgr in scope. Contest start/resolve broadcasts already happen in `engine.contest` (predating SYN.10) with `[REGION CONTEST]`/`[REGION DEFENDED]`/`[REGION SEIZED]` tags.
  - Building completion is selective: `garrison_annex` is a visible faction-power-projection so it gets a global `[News]` broadcast; residence/crafting_station/commerce_stall/cultural_hall stay owner-only because they're private investments.
- **What this drop deliberately did not do:**
  - No web HUD implementation. Design §3.12 calls the web HUD "post-launch polish; CLI suffices for launch." Substrate ready; rendering deferred.
  - No news-digest persistence. Real-time broadcasts only; no log of news events for offline players to catch up. Useful but out of scope.
  - No faction-influence-dashboard region-keyed rewrite. The `+region` command + auto-overlay covers the design need; the existing per-zone dashboard is unchanged. UI pivot will likely replace it entirely.
  - No building completion broadcast for non-garrison categories. Owner-only stays intentional for private investment.
- **Handoff:** `HANDOFF_MAY25_SYN10.md` — extensive UI-pivot-bridge section with data contracts, ANSI palette mapping, surface inventory, and consumer guidance for the upcoming UI work.

---

## 2026-05-25 — SYN.9 (Player-constructed building system)

- **Wave:** SYN sequence — player-built structures on city-claimed wilderness landmarks. Per `contestable_wilderness_design_v2.md` §2.9.3 + §3.9. Largest single-file engine drop in the SYN wave.
- **Files:**
  - `engine/buildings.py` (new, ~1150 LOC): full substrate. `BUILDING_CATEGORIES` dict with 5 entries (residence, crafting_station, commerce_stall, garrison_annex, cultural_hall) per design literal — each with credit_cost, material_costs list, effect_summary, plus category-specific fields (storage_cap=50 for residence; skill_bonus_dice=1 for crafting_station; owner_cut_pct/city_cut_pct=50 for commerce_stall; npc_count=2 for garrison_annex; cp_bonus_per_day=1 for cultural_hall). Constants per design: `CONSTRUCTION_TIME_SECS=24h`, `DEMOLISH_REFUND_PCT=25`, `REBUILD_DISCOUNT_PCT=10`, `EVICT_NOTICE_SECS=2d`, `DEFAULT_LANDMARK_SLOT_CAPACITY=2`, `MIN_RANK_TO_CONSTRUCT=3`. `buildings` table schema with idempotent CREATE TABLE IF NOT EXISTS + 3 indexes. `ensure_schema(db)` for boot-time migration. `get_slot_capacity(db, room_id)` reads `properties.building_slot_capacity` if present, else 2 for `wilderness_landmark: True` rooms, else 0; force-resonant rooms always 0. `construct_building(db, char, category, room_id, *, donate_to_org)` validates (rank 3+ in city's owning org, slot free, materials in inventory.resources, credits in wallet) → deducts → inserts row with `status='under_construction'` + `completion_ts=now+24h`. `demolish_building(db, char, building_id)` owner-only; 25% material refund if operational, no refund if under_construction; cleans up garrison NPCs. `evict_building(db, mayor, building_id)` mayor-only; sets `evict_after_ts=now+2d`; double-evict rejected. `tick_building_construction(db, session_mgr)` periodic transitioner: under_construction → operational at 24h (spawns 2 garrison NPCs for garrison_annex; broadcasts `[CONSTRUCTION COMPLETE]` to owner if online); operational + expired evict-notice → evicted (cleans up garrison NPCs; broadcasts `[EVICTED]`). 4 effect-lookup helpers: `get_crafting_station_bonus`, `get_cultural_hall_in_room`, `get_commerce_stall_in_room`, `get_residence_for_owner`. `residence_store_item` + `residence_take_item` with 50-item cap. `_is_rebuild` queries demolished/evicted rows for same owner + room + category. Helper functions: `_check_materials`, `_deduct_materials`, `_spawn_garrison_npcs` (faction-flavored to city's owning org), `_cleanup_building_npcs`.
  - `parser/player_building_commands.py` (new, ~350 LOC): `PlayerBuildingCommand` dispatch with 7 subcommands (`construct`, `demolish`, `evict`, `list`, `inspect`, `store`, `take`). Thin wrappers over engine. Filename chosen deliberately to avoid collision with existing `parser/building_commands.py` (admin world-building: `@dig`, `@tunnel`, `@destroy`, etc — unrelated keyspace). `register_player_building_commands(registry)` for boot-time registration.
  - `server/tick_handlers_economy.py` (modified, +25 LOC): `building_construction_tick` wrapper.
  - `server/game_server.py` (modified, +8 LOC): import + `ensure_schema` call at boot (after player_cities schema) + scheduler register (interval=300s = 5min, offset=120) + `register_player_building_commands` at parser bootstrap.
  - `tests/test_syn9_player_buildings.py` (new, ~1100 LOC, 54 tests across 11 sections): TestBuildingCategories (8 — 5 categories, required fields, design-literal constants pinned), TestSchema (3 — idempotent, indexes present), TestSlotCapacity (6 — landmark→2, non-landmark→0, force-resonant→0, explicit override, 0 valid, unknown room→0), TestConstructValidation (7 — unknown category, not landmark, no city, low rank, no membership, no materials, no credits), TestConstructSuccess (7 — success path, credits/materials deducted, status set, completion_ts correct, slot consumed, cap enforced), TestDemolish (5 — refund 25%, non-owner rejected, no-refund-under-construction, unknown id rejected, slot freed), TestEvict (3 — mayor sets notice, non-mayor rejected, double-evict rejected), TestConstructionTick (5 — 24h transition, garrison NPCs spawn, evict expiry, NPC cleanup, idempotent-when-empty), TestEffectLookupHelpers (4 — all 4 helpers return correctly with + without active building), TestResidenceStorage (4 — store/take, non-owner rejected, wrong-type rejected), TestRebuildDiscount (2 — applied for same owner, not applied for different owner). **5/5 deterministic on first run, no debug iterations needed.**
- **Tests:** +54 in new file. 5/5 deterministic. Full SYN family (SYN.1.a..SYN.9): 583 → 637 tests green (583 prior + 54 new), zero regressions. Combat-adjacent (wow3a, wow3b, pvp_flag, sess54_combat_umbrella): 81 tests green. City-substrate adjacent (cities_phase1-6): 437 tests green, zero regressions.
- **Design decisions documented in code comments:**
  - Default landmark slot capacity = 2 (per design "0-5 depending on landmark capacity" — 2 is the midpoint default, overridable via `properties.building_slot_capacity`).
  - Force-resonant landmarks have 0 slots (no buildings on sacred sites).
  - Effect helpers shipped as substrate; consumer integration deferred. Substrate ships the contract first with no consumer; SYN.10 polish wires consumers. This is the seam-discipline pattern from architecture v50.
  - `parser/player_building_commands.py` name chosen to avoid collision with existing admin `parser/building_commands.py` (separate concern; @dig/@tunnel keyspace).
  - Material refund uses quality 60 (medium-grade) on resource grant rather than tracking original input quality (simplification — design doesn't pin quality preservation).
- **What this drop deliberately did not do:**
  - **No consumer integration.** Effect-lookup helpers are ready but `engine/crafting.py`'s craft-roll path doesn't consult `get_crafting_station_bonus`. `engine/cp_engine.py`'s daily tick doesn't consult `get_cultural_hall_in_room`. No vendor command consumes `get_commerce_stall_in_room`. Lookup substrate ships; wiring deferred to SYN.10 or post-launch polish.
  - **No commerce stall vendor surface.** Building detects + lookup works; the player-vendor command (list items for sale, accept buyer credits, 50/50 with city treasury) is deferred.
  - **No cultural hall time-tracking.** Design says "5+ minutes here." Per-char-time-in-room tracking requires either periodic tick poll or hooking room-move events; deferred.
  - **No donate-to-org parser surface.** `construct_building` has the `donate_to_org` parameter; the `+building construct` command doesn't expose it. Substrate ready.
  - **No building HP / combat damage.** Schema has hp column; nothing decrements it. Design mentions Tier 3 anomaly events / contest damage as destruction paths; deferred.
- **Handoff:** `HANDOFF_MAY25_SYN9.md`

---

## 2026-05-25 — SYN.8 (Tier 3 wilderness anomalies, world bosses)

- **Wave:** SYN sequence — Tier 3 anomalies. Per `contestable_wilderness_design_v2.md` §2.8 + §3.8. Builds on the multi-phase combat substrate established by SYN.7.b.
- **Files:**
  - `engine/wilderness_anomalies.py` (modified, ~1500 → ~2000 LOC): added TIER3_TEMPLATES catalog (4 templates per design literal), TIER3_* constants (CADENCE_TICK_INTERVAL=24h, SPAWN_CHANCE_PER_TICK=0.10 → ~10-day avg, MAX_PER_REGION=1, DURATION_SECS=8h, INFLUENCE_DELTA=50, T5_MAT_QUALITY=80). WildernessAnomaly extended with `kill_counts: dict[char_id, int]` for participation tracking. `template` property now searches all 3 catalogs. `_pick_template` extended with tier=3 branch. `spawn_anomaly_for_region` extended with tier=3 dispatch (T3 cap + duration + chance independent). `_resolve_anomaly_combat`, `_advance_to_next_phase`, `award_combat_anomaly_reward` all changed `tier == 2` → `tier >= 2` so multi-phase machinery handles T3. `_payout_combat_anomaly` rewritten as tier dispatch — T1 = single-char (unchanged), T2 = room occupants (unchanged), T3 = kill_counts.keys() as participants. New helpers: `_grant_trophy` (adds item to inventory['items'] with is_trophy:True + is_anomaly_loot:True), `_distribute_scaled_t5_mat` (floor(N/4) pieces ranked by kill count descending; killer wins ties; minimum 1 piece consolation for small teams of <4). New `tick_tier3_wilderness_anomalies` parallel to T1/T2 ticks. Also fixed: `total_phases` property previously checked `tier == 2`; now `tier >= 2` (was a latent bug from SYN.7.b that only surfaced under T3).
  - `parser/combat_commands.py` (modified, +50 LOC): kill hook detects tier=3, surfaces `[WORLD BOSS DEFEATED]` headline (vs `[ANOMALY CLEARED]` for T1/T2), `[TROPHY]` line per participant, `[T5 MATERIAL]` line for top scaled-T5 recipients with kill-count attribution.
  - `server/tick_handlers_economy.py` (modified, +25 LOC): `tier3_wilderness_anomaly_tick` wrapper.
  - `server/game_server.py` (modified, +1 import + 1 scheduler register): registers `tier3_wilderness_anomaly` at interval=86400 (24h), offset=7200 (won't collide with T1 offset=1500 or T2 offset=3300).
  - `tests/test_syn8_wilderness_anomalies_tier3.py` (new, ~1000 LOC, 39 tests across 10 sections): TestTier3TemplateCatalog (7), TestTier3TemplateStructure (8), TestTier3RegionFiltering (4), TestTier3SpawnCadence (4), TestTier3InvestigateSpawn (2), TestTier3PhaseAdvancement (2), TestTier3KillCountTracking (2), TestTier3FinalPayout (3), TestTier3TrophyDistribution (2), TestTier3ScaledT5Distribution (5). **5/5 deterministic.**
- **Templates added:**
  - **Dune Sea (1):** `krayt_dragon` (3 phases — juvenile pack → elder krayt → enraged krayt; trophy: Krayt Dragon Scale; scaled T5 mat: `deep_dune_iron` q80).
  - **Coruscant Underworld (1):** `maze_predator_apex` (3 phases — pack vanguard → the apex → frenzy; trophy: Maze Apex Fang; scaled T5 mat: `composite_chitin` q80).
  - **REGION_ANY (2):** `crashed_separatist_capital_ship` (3 phases — perimeter security → heavy response → tactical command; trophy: Salvaged Separatist Hull Plate; scaled T5 mat: `weapons_capacitor_core` q80), `republic_lost_patrol` (3 phases — outer picket → interrogation detail → final reinforcements; trophy: Republic Patrol Insignia; scaled T5 mat: `weapons_capacitor_core` q80).
- **Resolution flow:** Same multi-phase pattern as Tier 2. Investigate → spawn phase 0 NPCs. Kill last NPC of phase N → phase N+1 spawns (intro broadcast). Each kill increments `anomaly.kill_counts[killer_char_id]`. Kill last NPC of final phase → `_payout_combat_anomaly` distributes rewards. Tier 3 payout: **(a)** participants = union of `kill_counts.keys()` (anyone who killed any anomaly NPC), **(b)** credits split equally among participants, **(c)** resources shared (full list per participant), **(d)** trophy item granted to every participant (`is_trophy: True` for housing.trophy_mount), **(e)** influence +50 to killer's faction, **(f)** scaled T5 mat: `floor(N/4)` pieces (minimum 1 consolation for small teams of <4) distributed to top participants by kill count descending; killer wins ties.
- **T5 mat drop hooks closed:** `composite_chitin` (fully — T2 outbreak + T3 Apex scaled). `deep_dune_iron` (fully — T3 krayt scaled). Cumulative T5 mat coverage: 3 of 4 mats now have drop hooks (`weapons_capacitor_core`, `composite_chitin`, `deep_dune_iron`). Only `scavenged_republic_tech` remains (Coruscant harvest path; standalone small drop).
- **Tests:** +39 in new file. 5/5 deterministic. Adjacent SYN family (SYN.1.a..SYN.7.b): 544 → 583 tests green (544 prior + 39 new), zero regressions. Combat-adjacent files (wow3a, wow3b, pvp_flag, sess54_combat_umbrella): 81 tests green, zero regressions.
- **Closes:** `T2.DEF.t5_drop_hooks.composite_chitin` (fully), `T2.DEF.t5_drop_hooks.deep_dune_iron` (fully). 
- **Latent bug caught + fixed:** The `total_phases` property checked `tier == 2`, returning 1 (not phase count) for T3 templates. T3 multi-phase resolution silently collapsed to single-phase. Fixed to `tier >= 2`. SYN.7.b tests didn't catch this because the property was only consulted on T2 paths.
- **Phantom caught + fixed:** Templates used `tier: "elite"` for the strongest archetypes, but the NPCTier enum has no `elite` (only extra/average/novice/veteran/superior). SYN.7.b tests didn't catch this either because the exception was silently absorbed by `_spawn_combat_npcs`'s per-NPC try/except — the elite NPC silently failed to spawn, but the test harness chose templates whose tested phases happened to use only veteran-tier. Surfaced under SYN.8 because phase advancement test landed on a phase that included elite-tier NPCs. Fixed by `sed s/elite/superior/g` across all T2 + T3 templates. Both `superior` (76-150D, "Formidable, major challenge") fits design intent for both T2 boss-tier and T3 world-boss-tier.
- **Design decision documented:** `engine/world_events.py::KRAYT_SIGHTING` was originally scoped to be "elevated from flag to real spawn" by SYN.8. Decision: leave the world_event as the atmospheric rumor layer. The Tier 3 anomaly system is the actual fightable krayt, with its own cadence engine, spawn surface, and combat resolution. The two layers cooperate (world_event broadcasts rumor; T3 anomaly is the encounter) but stay disjoint. Avoids coupling the wilderness anomaly system to the world-events substrate (which has its own atmospheric/director-narrated semantics).
- **Handoff:** `HANDOFF_MAY25_SYN8.md`

---

## 2026-05-25 — SYN.7.b (Tier 2 wilderness anomalies, multi-phase combat)

- **Wave:** SYN sequence — Tier 2 anomalies. Per `contestable_wilderness_design_v2.md` §2.8 + §3.7. Builds on the region-tag + combat-resolution substrate established by SYN.7.a.fix.
- **Files:**
  - `engine/wilderness_anomalies.py` (modified, ~1100 → ~1500 LOC): added TIER2_TEMPLATES catalog (5 templates), TIER2_* constants (CADENCE_TICK_INTERVAL=6h, SPAWN_CHANCE_PER_TICK=0.20 → ~30h avg, MAX_PER_REGION=1, DURATION_SECS=2h, INFLUENCE_DELTA=20, T5_MAT_QUALITY=70). WildernessAnomaly dataclass extended with `tier`, `current_phase`, and properties `phases`, `total_phases`, `is_final_phase`. `template` property now searches BOTH catalogs. `_pick_template` gained `tier=` kwarg (disjoint selection from Tier 1 vs Tier 2 catalogs). `spawn_anomaly_for_region` gained `tier=` kwarg (per-tier duration + cap). New `tick_tier2_wilderness_anomalies` parallel to Tier 1 tick. New helpers: `_spawn_combat_npcs` (extracted shared NPC-spawn loop used by both initial engage and phase advancement), `_advance_to_next_phase` (Tier 2 phase advancement; spawns next wave + broadcasts phase intro), `_payout_combat_anomaly` (split Tier 1 single-char from Tier 2 multi-char payout; called from the kill hook), `_grant_named_loot` (handles both `type: "resource"` and `type: "item"` shapes). `_resolve_anomaly_combat` rewritten to spawn ONLY phase 0 for Tier 2 templates. `award_combat_anomaly_reward` extended: when last NPC of current phase dies, check if Tier 2 with more phases → advance, else fire payout. Tier 2 payout distributes credits (equally split) + resources (shared full list) to all characters in anchor room; killer alone gets influence + named loot.
  - `parser/combat_commands.py` (modified, +60 LOC in kill hook): detects payout tier; for Tier 1 keeps existing single-line `[ANOMALY CLEARED]` shape; for Tier 2 issues per-participant lines + killer-only `[NAMED LOOT]` line. Passes `session_mgr` through to `award_combat_anomaly_reward` so phase intros can broadcast to room.
  - `server/tick_handlers_economy.py` (modified, +18 LOC): `tier2_wilderness_anomaly_tick` wrapper that delegates to `tick_tier2_wilderness_anomalies`.
  - `server/game_server.py` (modified, +1 import + 1 scheduler register): registers `tier2_wilderness_anomaly` at interval=21600 (6h), offset=3300 (won't collide with Tier 1's offset=1500).
  - `tests/test_syn7b_wilderness_anomalies_tier2.py` (new, ~900 LOC, 43 tests across 9 sections): TestTier2TemplateCatalog (6), TestTier2TemplateStructure (10), TestTier2RegionFiltering (5), TestTier2SpawnCadence (4), TestTier2InvestigateSpawn (3), TestTier2PhaseAdvancement (3), TestTier2FinalPhasePayout (5), TestTier2NamedLoot (3), TestTier2MultiParticipant (4). `_MiniDB` extends the SYN.7.a harness with `commit()`, `fetchone()`, `region_contests` + `region_contest_cooldowns` tables so `adjust_territory_influence` can fire end-to-end through the contest auto-check. **5/5 deterministic.**
- **Templates added:**
  - **Dune Sea (3):** `downed_republic_acclamator` (3 phases — CIS scout element → heavy response → salvage commander; named loot: 1× `weapons_capacitor_core` q70). `hutt_smuggling_convoy` (2 phases — Nikto outriders → Trandoshan + Weequay heavies; named loot: 1× `weapons_capacitor_core` q70). `cis_commando_deployment` (3 phases — BX commando vanguard → B2 heavy support → T-series tactical droid commander; named loot: T-Series Tactical Droid Command Module item).
  - **Coruscant Underworld (2):** `maze_predator_outbreak` (3 phases — scout pack → main pack → alpha; named loot: 1× `composite_chitin` q70). `coruscant_gang_war` (2 phases — Black Sun + Pyke first volley → boss engagement; named loot: Black Sun Vigo Signet Ring item).
- **Resolution flow:** investigate → spawn phase 0 NPCs. Players engage via normal `attack`. Kill last NPC of phase N → phase N+1 spawns (broadcast `[Phase N+1/N] {intro}` to room) → continue until final phase. Kill last NPC of final phase → `_payout_combat_anomaly` distributes rewards.
- **T5 mat drop hooks closed:** `weapons_capacitor_core` (closed — Acclamator + convoy named-loot drops) and `composite_chitin` (partially closed — Maze outbreak T2 drop; T3 Apex participation-scaled drop remains queued for SYN.8). Both mats land via `engine.crafting.add_resource` at q70 quality.
- **Tests:** +43 in new file. 5/5 deterministic. Adjacent SYN family (SYN.1.a..SYN.7.a): 501 → 544 tests green (501 prior + 43 new), zero regressions across SYN.1.a..SYN.7.a.fix. Combat-adjacent files (wow3a, wow3b, pvp_flag, sess54_combat_umbrella): 81 tests green, zero regressions.
- **Closes:** `T2.DEF.t5_drop_hooks.weapons_capacitor_core` (fully) + `T2.DEF.t5_drop_hooks.composite_chitin` (partially — Tier 2 portion).
- **Phantom-pattern note (v45 §6.2):** Original SYN.7.b TODO scope referenced `engine/encounter_boarding.py` as the boarding-party-ground-adaptation mechanism. Audit showed `engine/encounter_boarding.py` is deeply ship-coupled (created for space pirates boarding player ships); reusing it for ground-anomaly use would have required heavy adaptation. Implemented instead as a separate phase-based ground encounter that follows the same SHAPE (multi-NPC, phased, win-condition based) but lives entirely inside the wilderness anomaly system. Decision documented in the handoff; encounter_boarding.py untouched.
- **Handoff:** `HANDOFF_MAY25_SYN7B.md`

---

## 2026-05-25 — SYN.7.a.fix (Coruscant templates + real NPC combat)

- **Wave:** SYN sequence — closes the Coruscant gap and real-combat shortcut in SYN.7.a before SYN.7.b begins. Per Brian's directive: "complete SYN" means actually complete, not corner-cut.
- **Files:**
  - `engine/wilderness_anomalies.py` (rewritten, ~1100 LOC up from 785). 10 templates now (5 Dune Sea + 5 Coruscant Underworld). New per-template fields: `regions: [...]` (region tag list, with `REGION_ANY` sentinel) and `resolution: "skill"|"combat"`. Combat-mode templates declare `combat_npcs: [{archetype, tier, species, name_pool, weapon, behavior, personality}, ...]` — one real NPC spawned per entry via `db.create_npc`. New helpers: `find_anomaly_globally` (cross-region lookup for combat-death hook), `_prune_expired_region_with_cleanup` (DB-touching variant that deletes surviving NPCs from expired combat anomalies), `award_combat_anomaly_reward` (the kill-hook entry point — decrements live-NPC list, fires payout to killer when last hostile dies), `_apply_reward_to_char` (consolidated reward-application helper used by both skill + combat paths), `_gate_investigate` (extracted common pre-resolution gating), `_resolve_anomaly_skill` / `_resolve_anomaly_combat` (split resolution paths). `_pick_template` now takes `region_slug` and filters to matching templates; returns `None` for unknown regions (anomaly system stays silent for un-templated regions rather than spawning random content). `tick_wilderness_anomalies` calls the cleanup variant.
  - `parser/combat_commands.py` (modified, +75 LOC): anomaly kill hook inserted between bounty kill hook and WoW.3a kill credit. Mirrors the bounty pattern — reads `ai_config_json.is_anomaly_target` on the dying NPC, calls `award_combat_anomaly_reward`, surfaces `[ANOMALY CLEARED]` line with credits/resources/influence to the killer. Uses `c.last_attacker_id` for attribution (same chain as bounty + WoW kill credit).
  - `parser/anomaly_commands.py` (modified, +15 LOC): `InvestigateCommand` branches on `result.mode` — combat-mode shows `long_desc` + "use 'attack <target>'" nudge; skill-mode shows the roll + verdict + resource grants. No skill-roll line for combat investigations.
  - `tests/test_syn7a_wilderness_anomalies.py` (modified, +26 tests, 41 → 67): existing tests updated for 10-template catalog + region-tagged spawn; new sections cover Coruscant template structure + CW-correctness, region filtering enforcement (Dune Sea never picks Coruscant template and vice versa), combat-resolution NPC spawn, kill-hook payout (single-NPC + partial-group + final-kill + faction inf + independent + post-expiry + untagged + two-player attribution), expired-anomaly NPC cleanup, and the global anomaly lookup helper. `_MiniDB` extended with `npcs` table + `create_npc` / `get_npc` / `delete_npc` / `update_npc` / `get_npcs_in_room` for combat-path tests.
- **Templates added (Coruscant Underworld, all CW-correct):** `black_sun_courier` (combat, 2 thugs), `factory_cache` (skill, technical), `maze_rogue` (combat, 1 veteran creature), `cis_sleeper_cell` (combat, 2 B1 droids), `bounty_hunter_rival` (combat, 1 veteran bounty hunter). All region-tagged `coruscant_underworld` only.
- **Templates flipped skill → combat:** `wounded_animal` (now spawns 1 creature NPC — bantha bull, archetype `creature`), `tusken_party` (now spawns 3 NPCs — 2 average + 1 novice `thug` archetype, "Tusken Raider" species).
- **Resolution mix:** 4 skill (`stranded_clone_scout`, `salvage_cache`, `crashed_cis_probe`, `factory_cache`) + 6 combat (the other six).
- **Tests:** +26 — total 67 across this file. **5/5 deterministic.** Adjacent SYN family (SYN.1.a..SYN.7.a): 501 tests green, zero regressions. Combat-adjacent files (`test_wow3a_combat_hooks`, `test_wow3b_passive_decay_and_duels`, `test_pvp_flag_unit`, `test_session54_combat_umbrella`, `test_session58_cleanup_umbrellas`, `test_session63_bulk_premium`): 147 tests green, zero regressions.
- **Closes:** `T2.DEF.tier1_combat_polish` (real-NPC combat for wounded_animal + tusken_party — promoted to first-class delivery, not deferred). Closes the Coruscant gap raised mid-session ("we also have the Coruscant underworld wilderness zone — are we skipping that?"). Also closes the SYN.7.b uniform-template-distribution tuning concern by establishing region-tagged spawning as the system-level pattern.
- **Phantom-pattern note (v45 §6.2):** Pre-flight grep confirmed `wem.broadcast_news` phantom in `engine/director.py:1281` is untouched (still scheduled as separate tech-debt cleanup); SYN.7.a's news broadcasts route through `session_mgr.broadcast` directly, unchanged.
- **Handoff:** `HANDOFF_MAY25_SYN7A_FIX.md`

---

## 2026-05-25 — SYN.7.a (wilderness anomalies Tier 1, CW-correct)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Tenth drop, first half of SYN.7. Per `contestable_wilderness_design_v2.md` §2.8 + §3.7. Splits SYN.7 into SYN.7.a (Tier 1, skill-check resolution) + SYN.7.b (Tier 2, multi-phase combat including downed Republic Acclamator boarding-party-ground-adaptation).
- **Files:**
  - `engine/wilderness_anomalies.py` (new, ~600 LOC): substrate + cadence engine + 5 CW-correct Tier 1 templates + skill-check resolution. Module-level transient state keyed by `region_slug` (mirrors `engine.space_anomalies` pattern — restart wipes anomalies). `WildernessAnomaly` dataclass (id, region_slug, zone_id, template_key, anchor_room_id, spawned_at, expiry, resolved, resolved_by, resolved_faction). Pure helpers: `_format_news`, `_sample_credits`, `_pick_template`, `_pick_better_skill`, `_prune_expired_region`. DB-touching: `_iter_wilderness_regions` (broader than `region_ownership` — catches un-owned regions too), `_pick_anchor_room` (prefers landmark rooms via `engine.territory._get_region_landmarks` with fallback to any room in region), `spawn_anomaly_for_region` (single-region spawn with cap + chance check + force kwarg), `tick_wilderness_anomalies` (the periodic tick — returns stats dict), `get_anomalies_for_region` (lists active non-resolved), `get_anomaly_by_id`, `resolve_anomaly` (the main resolution path).
  - **5 Tier 1 templates (all CW-correct, no GCW residue)**:
    - `stranded_clone_scout` — Republic clone patrol, Medicine/Survival, 200-400cr + 2 organic q50 + 1 metal q55 + 5 inf on success
    - `salvage_cache` — Technical/Survival, 150-350cr + 3 metal q55 + 2 composite q50 on success
    - `wounded_animal` — Survival/Brawling, 100-250cr + 4 organic q55 + 1 composite q45 on success (simplified combat — proper NPC spawn deferred to T2.DEF.tier1_combat_polish)
    - `tusken_party` — Blaster/Melee, 180-380cr + 2 composite q55 + 2 metal q50 on success (simplified combat as above)
    - `crashed_cis_probe` — CIS Separatist (replaces design's GCW-era "reconnaissance droid" flavor), Technical/Knowledge, 250-500cr + 2 metal q60 + 2 energy q55 + 1 composite q60 on success
  - `parser/anomaly_commands.py` (new, ~150 LOC): `AnomaliesCommand` (key `anomalies`, alias `anom`) lists active anomalies in caller's wilderness region with ~Nm-left countdown and color-graded display; `InvestigateCommand` (key `investigate`) resolves a specific anomaly by id with full success/partial-failure flow and skill-roll surfacing for player feedback.
  - `server/tick_handlers_economy.py` (modified, +24 LOC): `wilderness_anomaly_tick` wrapper delegates to `engine.wilderness_anomalies.tick_wilderness_anomalies`. Hourly cadence (`CADENCE_TICK_INTERVAL = 3600`).
  - `server/game_server.py` (modified, +11 LOC): import `wilderness_anomaly_tick` + `register_anomaly_commands`; scheduler register `region_quality_weekly` offset 1500 + parser register both anomaly commands after `register_attune_command`.
  - `tests/test_syn7a_wilderness_anomalies.py` (new — 41 tests, 10 sections):
    - **TestTemplateCatalog (7):** 5 templates present, required fields, success_reward shape, **CW-correct (no "imperial"/"empire"/"stormtrooper"/"tie fighter" tokens anywhere)**, clone_scout is Republic-flavored, cis_probe is Separatist-flavored, all resource types in rewards are in `engine.crafting.RESOURCE_TYPES`.
    - **TestPureHelpers (9):** `_format_news` region substitution + unknown-template safety, `_sample_credits` in-band + zero-band, `_pick_template` returns known keys, `_pick_better_skill` (trained primary, fallback secondary, neither trained, no secondary).
    - **TestPruneExpiredRegion (3):** fresh kept, expired removed, mixed region partial prune.
    - **TestSpawnAnomalyForRegion (4):** basic force-spawn, cap respected, low-roll no-spawn, no-rooms-no-spawn.
    - **TestTickFlow (2):** tick returns stats dict, no-wilderness-rooms no-op.
    - **TestGetAnomaliesForRegion (3):** empty region, active listed, resolved excluded.
    - **TestResolveAnomalyFailures (5):** no room_id, room-not-in-wilderness, anomaly-not-found, wrong-room-rejection, already-resolved.
    - **TestResolveAnomalySuccess (5):** high-skill success grants credits, resources granted to inventory, anomaly marked resolved, independent char gets no influence, faction char gets +5 inf.
    - **TestResolveAnomalyFailedSkill (1):** one-shot semantics — failed skill check still resolves the anomaly + grants `fail_reward`.
    - **TestStateIsolation (2):** region A vs B isolation, `_reset_state_for_tests` helper.
  - `TODO.json` (modified): split SYN.7 → SYN.7.a (DONE) + SYN.7.b (queued); added new `T2.DEF.tier1_combat_polish` deferred-wireup entry at top of tier_2_queued; replaced `syn7_questions_pending` placeholder with 8 SYN.7.a tuning entries in `tunable_open_questions::syn7a_questions`.
  - `economy_tuning_open_questions_v1.md` (modified): SYN.7.a section populated with 8 tuning entries (cadence, duration, cap, influence delta, DC, reward bands, fail_reward existence, template distribution).
  - `CHANGELOG.md` (this entry).
- **Tests:** +41 in `test_syn7a_wilderness_anomalies.py`. **5/5 consecutive runs deterministic.** Adjacent regression sweep: SYN family + faction + crafting = **611 tests green** (was 570 at SYN.6.c close, +41 = 611).
  - Sandbox is Linux/Python 3.12. Windows/Python 3.14 box is ground truth — `run_all_tests.bat` on apply.
- **What it shipped:**
  - **The Tier 1 wilderness anomaly substrate.** Module-level transient state + cadence engine. SYN.7.b consumes the substrate for Tier 2 templates; SYN.8 consumes it for Tier 3 world bosses (with the dataclass extended for multi-phase HP + relocation).
  - **5 CW-correct Tier 1 templates.** No GCW residue (verified by automated test). Republic clone scout (rescuable), Tusken hunting party (combat), CIS probe droid (salvage), plus 2 era-neutral templates (salvage cache, wounded animal).
  - **News broadcasts on spawn.** Each anomaly fires a news line via `session_mgr.broadcast` (best-effort — silently logs on failure).
  - **One-shot resolution semantics.** Failed skill check still consumes the anomaly + grants `fail_reward`. Prevents farming + prevents arbitrary first-fail-then-second-succeed feel.
  - **+5 influence reward** routed to the resolver's faction in the anomaly's zone_id. Independent characters get no influence (no faction to credit).
- **What it deliberately did not do:**
  - **Did not ship full NPC-spawn-based combat resolution** for wounded_animal and tusken_party templates. Simplified skill-check resolution is in place; real NPC spawn touches the NPC AI system + faction tagging + combat loop. Tracked as `T2.DEF.tier1_combat_polish` (~0.5-1 sess).
  - **Did not ship region-flavored template weighting.** Current implementation: uniform random across all 5 templates. Region-flavored weighting (Tusken party more likely in Dune Sea, CIS probe more likely in CIS-traffic regions) ships in SYN.7.b alongside Tier 2 templates so it's designed once across both tiers.
  - **Did not ship Tier 2 templates** (downed Republic Acclamator, Hutt smuggling convoy, Maze Predator outbreak, CIS commando deployment). SYN.7.b. These also carry the `weapons_capacitor_core` and `composite_chitin` T5 mat drop hooks.
  - **Did not ship persistent anomaly state** across server restarts. Module-level transient state — matches `engine.space_anomalies`. If restart-persistence becomes a requirement post-launch, that's a DB-backed enhancement.
- **Pre-flight findings:**
  - **No phantom delivery risk.** Greps for `wilderness_anomal`, `WildernessAnomaly`, `TIER1_TEMPLATES`, `tick_wilderness_anomal` returned zero hits. Clean greenfield.
  - **Found a phantom call** in `engine/director.py:1281` — `wem.broadcast_news(...)` invokes a method that doesn't exist on `WorldEventManager`. The call silently fails via the `except Exception` wrapper. Pre-existing bug not introduced by SYN.7.a; documented for tech-debt but out of scope. Anomaly news routes through `session_mgr.broadcast` directly to avoid involving the broken WEM surface.
  - **CW-correctness verified automatically.** Test `test_cw_correct_no_imperial` greps all template flavor strings for GCW-era tokens and asserts none are present. Future SYN.7.b / SYN.8 templates can reuse this test pattern.
  - **`craft_lightsaber` skill key precedent honored**: anomaly templates use existing skill keys (medicine, survival, technical, knowledge, blaster, melee_combat, brawling) — no new skill keys invented.
- **Tuning concerns logged (NOT fixed in this drop, feed T2.ECON.review):**
  - 8 new entries in `tunable_open_questions::syn7a_questions` covering cadence, duration, cap, influence delta, DC, reward bands, fail_reward existence, template distribution.
  - Most are design-doc-aligned (cadence midpoint, duration, +5 influence). Two are honest Claude-picks worth scrutinizing: DC 13 (target ~70% success rate at 4D skill — needs playtest confirmation) and uniform-template-distribution (vs region-flavored, deferred to SYN.7.b).
- **Handoff:** `HANDOFF_MAY25_SYN7A.md`.

---

## 2026-05-25 — SYN.6.tracking (TODO/doc hygiene, no code)

- **Wave:** SYN sequence — bookkeeping after the SYN.6 wave close.
- **Trigger:** Brian raised three concerns at SYN.6.c close: (1) Are intel-handler NPCs seeded? (2) Are we considering the economy / spam vectors / supply-demand? (3) Are the deferred T5 wire-ups tracked? Honest answers: (1) No, only in CHANGELOG prose, not as a discrete TODO entry. (2) Partial — the SYN.6 numeric picks weren't audited end-to-end; some (e.g. kyber 24h per-landmark cooldown × 4 force-resonant landmarks = 4 shards/Jedi/day) are likely oversupplied. (3) Tracked but nested inside the SYN.6.c entry's `what_deferred_within_scope` field — invisible when SYN.6.c is grep'd as DONE.
- **Files:**
  - `TODO.json` (modified):
    - **6 new tier_2_queued entries** promoted to first-class (was: tracked only in CHANGELOG prose / nested deferral fields):
      - `T2.ECON.review` — whole-game economist pass; explicitly scoped beyond just SYN; deferred until SYN.9 ships to avoid mid-wave derailment.
      - `T2.DEF.handler_npcs` — seed `is_intel_handler` NPCs at 9 faction HQs (SYN.5 deferral).
      - `T2.DEF.t5_drop_hooks` — 4 sub-items for the missing T5 mat drop hooks (weapons_capacitor_core / composite_chitin land in SYN.7.b; scavenged_republic_tech is a standalone small drop; deep_dune_iron lands in SYN.8).
      - `T2.DEF.t5_trainer_storyline` — T5 schematic acquisition path.
      - `T2.DEF.t5_ship_part_items` — `data/items.yaml` extension for hyperdrive/ion engine items.
      - `T2.DEF.t5_discoverability` — `craft` command UI for T5 schematics.
    - **New top-level `tunable_open_questions` array** — 13 SYN.6 entries documenting every numeric value picked during SYN.6.a/b/c with its alternatives, supply/demand math, and the smallest playtest that would confirm or refute. Includes ⚠ HIGH PRIORITY marker on `TUN.kyber.cooldown` (most likely to be off). Placeholder sections for SYN.7.a / SYN.7.b / SYN.8 / SYN.9 — to be appended as those drops land.
  - `economy_tuning_open_questions_v1.md` (new — ~13KB): standing design doc consolidating the tuning ledger. Feeds T2.ECON.review when the economist pass opens. Documents the standing process: every future drop appends its tuning knobs to this doc + the TODO.json array.
  - `CHANGELOG.md` (this entry).
- **Tests:** N/A — TODO/doc-only. JSON validation passed (`python -c "json.load(open('TODO.json'))"` clean).
- **What it shipped:**
  - **Promoted deferrals from prose to first-class TODO entries.** Future "what's left?" greps will surface T2.DEF.* and T2.ECON.review explicitly. No more nested-in-DONE-field rot.
  - **Standing tuning ledger.** Every SYN.6 numeric pick now has a documented home. Future SYN drops append rather than starting from scratch.
  - **Explicit deferral of the economist pass to post-SYN-completion.** Per Brian's call: doing it mid-SYN would derail forward progress; doing it after SYN means looking at a complete system rather than a moving target.
- **What it deliberately did not do:**
  - **No code change.** This is bookkeeping, not engineering.
  - **No tuning adjustments.** The economist pass (`T2.ECON.review`) does the actual tuning. This drop just inventories what needs review.
  - **No drop zip.** Two-file diff (TODO.json + new .md) is small enough to roll into the next code drop (SYN.7.a) rather than ship standalone.
- **Pre-flight findings:**
  - **3 SYN.6 picks identified as likely-off**: kyber cooldown (current 24h per-landmark across 4 landmarks = 4 shards/Jedi/day, likely should be 1/day or 1/week), kyber quality floor (no-duds design is generous), harvest skill-margin credit bonus (uncapped +20%/band gives extreme outliers at 10D+ Survival).
  - **Other 10 SYN.6 picks are design-doc values** — preserved verbatim from `contestable_wilderness_design_v2.md` and noted in the ledger as "design number, no debate needed."
- **Handoff:** Inline in this entry — no separate handoff doc for a bookkeeping drop.

---

## 2026-05-25 — SYN.6.c (T5 crafting tier + harvest-node gating + kyber attunement)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Ninth drop, closes SYN.6 entirely. Per `contestable_wilderness_design_v2.md` §2.5.2 (harvest-node gate), §2.5.6 (T5 crafting). Originally scoped as post-launch; pulled into pre-launch per Brian's call to complete SYN before shipping.
- **Files:**
  - `engine/crafting.py` (modified): extended `RESOURCE_TYPES` from 6 to 11 entries by adding 5 T5 wilderness-only materials (`kyber_shard_minor`, `weapons_capacitor_core`, `scavenged_republic_tech`, `deep_dune_iron`, `composite_chitin`). Added `HARVESTABLE_RESOURCE_TYPES` (the T1-T4 subset, 6 entries) for clean separation: T5 mats are DROP-ONLY and don't participate in weekly variance — their quality is set at the drop event (skill margin on landmark visit, anomaly participation rules). Added `T5_WILDERNESS_MATERIALS` frozenset + `T5_MIN_QUALITY=75` constants. Existing crafting flow (`add_resource`, `check_resources`, `consume_components`) handles the new types transparently — no code-path additions needed.
  - `data/schematics.yaml` (modified): appended 5 T5 schematics (33 → 38 schematics total). All CW-correct era flavor; difficulty band 25-28 (Very Difficult on WEG D6 R&E, explicitly above the existing T1-T4 ceiling of 20). Each gates on exactly one T5 mat at q75+ AND consumes standard T1-T4 components at min_quality 50-65. The 5: `t5_master_crafted_lightsaber` (kyber_shard_minor, craft_lightsaber skill, diff 28), `t5_top_spec_blaster_rifle` (weapons_capacitor_core, diff 25), `t5_hyperdrive_surge_converter` (scavenged_republic_tech, diff 26 — forward-references future ship-part item catalog), `t5_mil_spec_ion_engine_core` (deep_dune_iron, diff 27 — same), `t5_master_grade_armor` (composite_chitin, diff 25). Output_keys reuse existing base item keys where they exist (`lightsaber`, `blaster_rifle`, `bounty_hunter_armor`); ship-part keys forward-reference a future item catalog drop.
  - `engine/harvest.py` (modified, ~+90 LOC): new `_is_harvest_node(db, room_id, region_slug)` helper + `_room_has_harvest_node_flag` predicate. SYN.6.c gates `perform_harvest` Step 1.5 on the new check with **region-scoped fallback**: if ANY room in the region has `properties.harvest_node: true`, only those rooms are harvest nodes (gated); if NO rooms in the region are flagged, every room qualifies (SYN.6.a back-compat). This lets content authors opt regions into landmark-gating one region at a time without breaking the existing harvest experience.
  - `engine/region_quality.py` (modified): three-line change — switched weekly-variance loop from `RESOURCE_TYPES` to `HARVESTABLE_RESOURCE_TYPES` so the variance table stays scoped to harvestable types. Semantics: "this week the Dune Sea has good metal" makes sense; "this week the Dune Sea has good kyber" does not — kyber quality is per-attune-event, not per-region-week. Eliminates 5 unused rows per region per week.
  - `engine/kyber_attunement.py` (new, ~280 LOC): `attune_to_landmark(db, char, room_id, *, rng, now)` — single entry point for kyber acquisition. Validation chain (5 steps: room exists, room is force_resonant, character is_jedi_pc, cooldown clear, skill check). On success, grants 1 `kyber_shard_minor` resource stack via `engine.crafting.add_resource` at quality 75-95 (skill-margin-scaled: margin 0 → q75, +5 bands give +5 quality each, capped at q95). 24h per-landmark cooldown (per-landmark not per-region; kyber shards are scarce, not renewable). Failed skill check still sets cooldown (anti-farm). Pure helpers: `_compute_kyber_quality`, `_resolve_skill` (prefers scholar → willpower → knowledge fallback), `_room_is_force_resonant`. Quality ceiling q95 — q100 reserved for Tier-3 anomaly kyber drops (SYN.8) representing major kyber finds.
  - `parser/attune_command.py` (new, ~95 LOC): `AttuneCommand` (key `attune`, no aliases). Thin wrapper over `engine.kyber_attunement.attune_to_landmark`. On meaningful success surfaces the skill roll + margin for player feedback (same pattern as `harvest`).
  - `server/game_server.py` (modified, +9 LOC): import `register_attune_command`; register after `register_harvest_command` in the bootstrap.
  - `tests/test_syn6c_t5_crafting_and_harvest_nodes.py` (new — 40 tests, 11 sections):
    - **TestResourceTypeConstants (6):** module-level shape — RESOURCE_TYPES (11), HARVESTABLE (6), T5_WILDERNESS (5), disjoint subsets, union, T5_MIN_QUALITY.
    - **TestT5SchematicsLoadable (4):** 5 T5 schematics load, required fields present, each gates on exactly one T5 mat at q75+, difficulties above non-T5 ceiling.
    - **TestT5SchematicGating (2):** q74 kyber fails the lightsaber gate (off-by-one); q75 kyber passes.
    - **TestT5CraftingFlow (2):** `add_resource` accepts T5 mats (no "unknown type" error); `consume_components` drains T5 mats through the existing surface.
    - **TestHarvestNodeGate (4):** no flags in region → fallback allows any room (SYN.6.a back-compat); flagged room allowed; unflagged room rejected when region has at least one flag; `harvest_node: false` doesn't count as flagged.
    - **TestAttuneRoomFlag (5):** `_room_is_force_resonant` bounds — resonant True, False, missing properties, dict (not string), malformed string.
    - **TestAttuneQualityScaling (6):** margin 0 → q75, 5 → q80, 10 → q85, 20 → q95, huge → capped at q95, negative defensive floor.
    - **TestAttuneSkillResolution (4):** no trained skills → attribute fallback, scholar preferred over willpower, willpower if scholar absent, malformed skills JSON fallback.
    - **TestAttuneEntryGates (3):** no room rejected, non-resonant room rejected, non-Jedi at resonant room rejected with thematic message.
    - **TestAttuneSuccessPath (3):** Jedi with 12D scholar acquires q75-95 shard, cooldown set after success, second attempt blocked.
    - **TestAttuneFailedSkillPath (1):** failed skill check still consumes cooldown (anti-farm).
  - `tests/test_syn6a_active_harvest.py` (modified): two SYN.6.a tests tightened — yield-table containment now asserts `HARVESTABLE_RESOURCE_TYPES` (strict subset, T5 mats must NOT appear in ordinary harvest); seam-baseline test asserts the dict covers `HARVESTABLE_RESOURCE_TYPES` not the broader set.
  - `tests/test_syn6b_weekly_region_quality.py` (modified): bulk rename of 6 `RESOURCE_TYPES` references to import `HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES` (test variable name unchanged, semantics correct for weekly variance scope).
  - `TODO.json` (modified): SYN.6.c → DONE; SYN.6 wave fully closed.
  - `CHANGELOG.md` (this entry).
- **Tests:** +40 in `test_syn6c_t5_crafting_and_harvest_nodes.py`. Combined SYN.6 suite: **135 tests** (57 SYN.6.a + 38 SYN.6.b + 40 SYN.6.c), **5/5 consecutive runs deterministic**. Adjacent regression: SYN.1.a..SYN.6.c (394) + faction tests (94) + crafting tests (42) = **530 tests green**. No shared engine/parser code modified outside the documented surfaces.
  - Sandbox is Linux/Python 3.12. Windows/Python 3.14 box is ground truth — `run_all_tests.bat` on apply.
- **What it shipped:**
  - **The T5 crafting endgame.** 5 master-tier schematics gated on wilderness-only materials at q75+. Per the design's framing: *"the genuine endgame crafting lane — reasons to engage with wilderness for non-PvP players."* A crafter can now build a full career around region-specific sourcing without ever participating in a formal contest.
  - **Kyber attunement seam fully wired.** Force-sensitive PCs (jedi_order faction OR jedi_path_unlocked chargen flag, per `is_jedi_pc` predicate) at force-resonant landmarks (existing content — `force_resonant_landmarks.yaml`) can now `attune` for the T5 lightsaber gate material. One drop hook live; the four other T5 mats await their respective drop sources (SYN.7/8 anomalies, special harvest paths).
  - **Harvest-node gating with fallback.** Content authors can flag specific landmarks `harvest_node: true` in YAML; rooms not so flagged in a region with flagged rooms are rejected. Regions with no flags still work as in SYN.6.a (back-compat). Lets the content team migrate regions one at a time.
  - **HARVESTABLE_RESOURCE_TYPES semantic split.** Weekly variance, harvest yield tables, and outlook digests stay scoped to the 6 T1-T4 types. T5 mats can't accidentally appear in ordinary harvest output and don't bloat the region_quality table.
- **What it deliberately did not do:**
  - **Did not ship the four non-kyber T5 mat drop hooks.** `weapons_capacitor_core` (Dune Sea T2 anomaly drop) lands in SYN.7.b. `composite_chitin` (Maze Predator hunts) also SYN.7.b. `scavenged_republic_tech` (Coruscant Underworld special harvest) deferred to a small post-SYN content drop. `deep_dune_iron` (Tier-3 krayt anomaly) lands in SYN.8. The schematics + RESOURCE_TYPES entries ship now as seams; consumers wire when the drop sources land.
  - **Did not ship a `trainer_npc` for T5 schematics.** The `trainer_npc` field is empty string on all 5 T5 entries — the design intent is acquisition via story/quest-line (Jedi Master, Hutt weaponsmith, Republic engineer-corps officer), not via standard trainer-NPC dialogue. That player-facing acquisition path is its own future drop. T5 schematics are craftable today for any character whose `attributes.schematics` list contains the key; admin-grant is the current path.
  - **Did not add ship-part item catalog entries.** `t5_hyperdrive_surge_converter` and `t5_mil_spec_ion_engine_core` schematics craft `ItemInstance` rows with those output_keys, but the items themselves don't have functional combat/space effects until a follow-up `data/items.yaml` drop lands. The schematic still produces a valid inventory item; it's just inert in combat.
  - **Did not surface T5 schematics in the existing `craft` command's discovery UI.** They're craftable via the existing surface for any character who has them in their `attributes.schematics` list; the discoverability path (where do players find these recipes) is the same future drop as the trainer story-line.
- **Pre-flight findings:**
  - **No phantom delivery risk.** Greps for the T5 mat keys (`kyber_shard_minor`, `weapons_capacitor_core`, etc.) and `harvest_node` on HEAD returned zero hits. Clean greenfield.
  - **Skill-key correction caught.** Initial draft used `lightsaber_repair` for the T5 lightsaber schematic, but `engine.village_trials.py` already uses `craft_lightsaber` as the canonical skill key. Fixed before tests landed.
  - **`vendor_droids.py` line 1070 has dead validation** (`RESOURCE_TYPES.keys()` on a set throws AttributeError; the `if hasattr` guard makes it inert). Pre-existing bug, not introduced by SYN.6.c. Expanding RESOURCE_TYPES doesn't change the operational behavior here (validation was never running). Documented for tech-debt, not fixed in this drop.
  - **HARVESTABLE subset cleanup needed during dev.** Initial draft expanded RESOURCE_TYPES without the subset split; SYN.6.b weekly-variance tests broke because they asserted the seam covers `RESOURCE_TYPES` (now 11 types). Pivoted to the subset model — semantically cleaner AND smaller test diff. Two SYN.6.a tests + 6 SYN.6.b sites updated; 95 prior tests stayed green after.
- **Handoff:** `HANDOFF_MAY25_SYN6C.md`.

---

## 2026-05-25 — SYN.6.b (weekly region-quality variance + Director resource outlook)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Eighth drop, second half of the SYN.6 (`~1.5 sess`) item per `contestable_wilderness_design_v2.md` §3.6. Closes the active-harvest economy loop; SYN.6.c (post-launch) covers T5 crafting + optional landmark-gated harvest.
- **Files:**
  - `engine/region_quality.py` (new, ~290 LOC): owns the weekly-quality subsystem end-to-end.
    - **Schema:** `region_quality` table (region_slug + resource_type composite PK, quality_multiplier real, rolled_at real, roll_year_week text 'YYYY-Www'). Created via `ensure_region_quality_schema(db)` — per-feature bootstrap pattern (mirrors SYN.1.a's `ensure_region_ownership_schema`), no `SCHEMA_VERSION` bump.
    - **Pure helpers:** `_iso_year_week(now)` canonical 'YYYY-Www' key (ISO 8601 Monday anchor), `_compute_weekly_multiplier(rng)` float in `[0.7, 1.3]` rounded to 2 decimals, `_outlook_summary(rows)` per-region best/worst with stable alphabetical tie-breaking.
    - **DB-touching:** `roll_region_quality(db, region_slug, rng, now)` single-region roll (idempotent per ISO week), `get_region_quality_for(db, region_slug)` returns `dict[type, float]` (fail-soft to all-baseline if table missing), `get_outlook(db, org_code=None)` outlook digest data, `tick_weekly_region_quality(db, session_mgr, now)` weekly tick that iterates `SELECT DISTINCT wilderness_region_id FROM rooms` (broader than `region_ownership` — un-owned regions get rolls too since SYN.6.a maps them to fallback yields).
    - **Constants:** `QUALITY_MIN=0.7`, `QUALITY_MAX=1.3`, `QUALITY_BASELINE=1.0`.
  - `engine/harvest.py` (modified, ~+50 LOC net): swap the SYN.6.a seam from `return 1.0` to delegating into `engine.region_quality.get_region_quality_for`. `compute_harvest_payout` now polymorphic on `quality`: accepts either a `float` (SYN.6.a back-compat, applies uniformly to all stacks) OR a `dict[type, float]` (SYN.6.b consumer, per-type quality). New result fields: `stack_qualities: dict[type, float]` (per-type qualities for awarded stacks) and `stack_quality: float` (legacy single-value field, now computed as the mean of per-type qualities for display compat). Missing types in a dict default to 1.0× (defensive). Fail-soft on seam-import errors falls back to the legacy 1.0 float.
  - `parser/faction_commands.py` (modified, ~+85 LOC): new `_cmd_resource_outlook` subcommand handler. Dispatch keys `resource_outlook`, `outlook`, `resources` (all alias). Color-graded display by best-multiplier (green ≥1.2×, yellow ≥1.0×, dim <1.0×). For faction members, restricts to their org's owned regions. For independent characters, shows all regions with a "for context only" framing line. Empty-state message when no rolls have fired yet.
  - `server/tick_handlers_economy.py` (modified, +24 LOC): `region_quality_weekly_tick(ctx)` wrapper that delegates to `engine.region_quality.tick_weekly_region_quality`. Hourly cadence with per-region per-week ISO year-week idempotence — only the first call in a new week actually writes; subsequent calls no-op cheaply. Matches the `city_maintenance_tick` pattern (simpler than wiring cron-style Monday-midnight fire on an interval-based scheduler).
  - `server/game_server.py` (modified, +9 LOC): import `region_quality_weekly_tick`; register as `region_quality_weekly` with `interval=3600, offset=3300` (between `territory_contests` at 2700 and the next hourly tick on the load-spreading grid).
  - `tests/test_syn6a_active_harvest.py` (modified, +9 LOC): one test (`test_region_quality_seam_returns_baseline`) updated to assert the new dict contract (seam intentionally changed shape in SYN.6.b per design §2.5.5 per-resource-type variance). All 57 SYN.6.a tests remain green.
  - `tests/test_syn6b_weekly_region_quality.py` (new — 38 tests, 10 sections):
    - **TestIsoYearWeek (5):** Monday anchor, Sunday-same-week, next-week boundary, ISO format, default-arg.
    - **TestComputeWeeklyMultiplier (4):** in-range, 2-decimal rounding, RNG determinism, distribution covers central 60%.
    - **TestOutlookSummary (6):** single region, multiple types, multiple regions, alphabetical tie-breaking, `all` field, empty input.
    - **TestSchemaBootstrap (2):** creates table, idempotent.
    - **TestRollRegionQuality (4):** fresh roll covers all `RESOURCE_TYPES`, idempotent in same week, re-rolls next week, partial-existing-data completes.
    - **TestGetRegionQualityFor (3):** baseline before roll, post-roll values, missing-table fail-soft.
    - **TestTickWeeklyRegionQuality (4):** rolls all distinct regions (duplicates collapsed), idempotent in same week, re-rolls next week, no-wilderness no-op.
    - **TestHarvestPayoutDictQuality (5):** dict quality per type, missing type defaults to 1.0×, float back-compat, `stack_qualities` field present, legacy `stack_quality` is the mean.
    - **TestGetOutlook (3):** unfiltered, org-filtered, unknown-org empty.
    - **TestHarvestSeamWired (2):** `_get_region_quality` returns per-type dict after roll, baseline dict before roll.
  - `TODO.json` (modified): SYN.6.b → DONE.
  - `CHANGELOG.md` (this entry).
- **Tests:** +38 in `test_syn6b_weekly_region_quality.py`. Adjacent regression sweep: SYN family `syn1a..syn6b` = 394 tests green; faction tests (`b1d3_cw_faction_anchors_wired`, `b6_defensive_faction`, `f5b1_faction_quarter_tiers_datafied`, `session49_faction_missions`) = 94 tests green. Combined SYN.6.a+SYN.6.b suite is **95 tests, 5/5 consecutive runs deterministic**.
  - Sandbox is Linux/Python 3.12. Windows/Python 3.14 box is ground truth — `run_all_tests.bat` on apply.
- **What it shipped:**
  - **Per-resource-type weekly variance.** Same region rolls metal might be 1.3× while chemical is 0.8× the same week — the SWG crafter-traffic mechanic from design §2.5.5 fully wired.
  - **Idempotent weekly tick.** Hourly cadence, per-region per-week ISO 8601 anchor. Survives server restarts without double-rolling; new week reliably triggers fresh rolls.
  - **Outlook digest as a player surface.** `faction resource_outlook` (with aliases `outlook` / `resources`) gives crafters a one-glance view of which regions have which high-quality types this week.
  - **Harvest economy fully connected.** SYN.6.a's seam is now consumed; harvested stack qualities reflect both the weekly per-type variance AND the per-harvest skill-margin bonus.
- **What it deliberately did not do:**
  - **Did not bump `SCHEMA_VERSION`.** Per-feature `ensure_region_quality_schema` bootstrap (mirrors SYN.1.a). Cleaner — table appears where the feature is wired, no global migration entry, deployment is automatic on first tick.
  - **Did not push outlook to news channels.** Pull-only via the parser command. A push-to-news ("This week's best region: Tatooine Dune Sea, metal 1.28×!") would be a small follow-up; the data layer is already in place.
  - **Did not implement history retention.** Only the current week's roll is stored (`INSERT OR REPLACE`). If we ever want "last 4 weeks of outlook for trend analysis" that needs a history table — out of scope.
  - **Did not ship T5 crafting recipes or `harvest_node: true` YAML gating.** Both deferred to SYN.6.c (post-launch).
- **Pre-flight findings:**
  - **No phantom delivery risk.** Greps for `region_quality`, `weekly_quality`, `resource_outlook`, `monday tick`, `weekly variance` returned only forward references from the SYN.6.a drop earlier today — all correctly tagged "SYN.6.b will ship".
  - **Iterate `rooms.wilderness_region_id` distinct, not `region_ownership`.** Caught during design: un-owned regions can still be harvested (SYN.6.a maps them to foothold-fallback yields), so they need quality rolls too. Pulling from `rooms` catches every materialised region; `region_ownership` would only catch claimed ones.
  - **Polymorphic `quality` parameter on `compute_harvest_payout`.** Allows the SYN.6.a unit tests to keep their `quality=1.0` (float) signature unchanged while the SYN.6.b consumer naturally gets per-type semantics. One-line type check in the helper closure.
- **Handoff:** `HANDOFF_MAY25_SYN6B.md`.

---

## 2026-05-25 — SYN.6.a (active wilderness harvest mechanic)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Seventh drop, first half of the SYN.6 (`~1.5 sess`) item per `contestable_wilderness_design_v2.md` §3.6. SYN.6.b will land the weekly region-quality variance tick + Director resource-outlook digest.
- **Files:**
  - `engine/harvest.py` (new, ~510 LOC): pure helpers + DB-touching entry point for active harvest.
    - **Yield table per design §2.5.2 verbatim** (6 rows, security × influence tier). Contested/foothold → 100-200cr + 1 metal; lawless/control → 400-800cr + 4 metal + 3 chemical + 2 rare + T5 chance.
    - **Pure helpers:** `_yield_table_lookup`, `_apply_skill_margin` (5-pt bands, +20%/+10Q each, quality cap +50), `_quality_to_resource_quality` (region-q × 50 + margin Q, clamped 1..100), `_compute_tax` (3-state: owner-member / non-member-of-owned / un-owned-region), `compute_harvest_payout` (full deterministic computation).
    - **DB-touching:** `_get_region_quality` (seam — returns 1.0 in SYN.6.a; SYN.6.b swaps body), `_is_owner_member` (resolves owner_code and member status), `perform_harvest` (main entry — room→region resolution, security gate, cooldown check, skill check, payout, tax routing, resource grant).
    - **Constants:** `HARVEST_DIFFICULTY = 6` (WEG Easy), `HARVEST_SKILL = "survival"`, `HARVEST_COOLDOWN_SECS = 1800` (30 min per region), `NON_OWNER_TAX_RATE = 0.15`.
    - **Resource integration:** stacks land in `inventory.resources` via `engine.crafting.add_resource` — same storage the crafting system already reads from. SWG-style `{type, quantity, quality}` per stack. Region quality + skill margin → stack quality (1..100). T5 rare hit grants 1 extra `rare` stack at q100 (top of band) rather than inventing a new resource type — when T5 crafting lands it can gate on `min_quality ≥ 95` and these q100 rares will qualify.
    - **Influence: NONE.** Active harvest does NOT grant org influence. The design §2.7 reward table covers npc_kill / mission_complete / pvp_win + intel handover; harvesting earns credits + resources only. Owner orgs get the 15% tax on visitor harvests as their influence-economy payoff. This is intentional — if harvest granted influence, the visitor-economy pressure would invert (no one would visit if it shored up the owner's contest position). Pinned by a dedicated test.
  - `parser/harvest_command.py` (new, ~95 LOC): thin wrapper.
    - `HarvestCommand` (no aliases, key `harvest`). Resolves char + room_id, delegates to `engine.harvest.perform_harvest`, surfaces the result line + a skill-feedback line on payout. All gating (wilderness-only, cooldown, etc.) lives in the engine.
  - `server/game_server.py` (modified, +1 import + 1 register block).
  - `tests/test_syn6a_active_harvest.py` (new — 57 tests, 12 sections):
    - **TestYieldTableLookup (10):** every (security, tier) pair, unknown-tier fallback, unknown-security fallback, None-handling.
    - **TestApplySkillMargin (8):** failure margin, base band at 0/4 margin, one band at 5, two bands at 10, quality cap at 25+, credit-keeps-scaling-after-cap at 50.
    - **TestQualityConversion (5):** baseline 50 at 1.0×, margin bonus addition, clamp at 1 and 100, zero quality.
    - **TestComputeTax (6):** owner keeps all, non-member pays 15%, zero credits, small-amount rounding, 1-cred edge, un-owned region (the bug found during dev — credits no longer vanish).
    - **TestComputeHarvestPayout (8):** failure margin zero payout, owner-member zero tax, non-member tax routed, stack quality propagated, T5 rare grants q100 when rolled, T5 rare absent otherwise, margin scales credits up, quality scales stack quality.
    - **TestPerformHarvestWilderness (2):** city-room rejected, missing-room rejected.
    - **TestPerformHarvestSecured (1):** defensive — secured wilderness rejected.
    - **TestPerformHarvestCooldown (3):** cooldown set on first harvest, blocks second harvest, per-region namespacing (cooldown on region A doesn't block region B).
    - **TestPerformHarvestTaxRouting (4):** member pays no tax, non-member pays 15% to owner treasury, un-owned region no tax, independent harvester pays tax in owned region.
    - **TestPerformHarvestResources (2):** stacks land in `inventory.resources` with SWG schema, all yield-table types are in `engine.crafting.RESOURCE_TYPES`.
    - **TestPerformHarvestNoInfluence (1):** the wilderness-only-influence invariant — harvest must NOT mutate `territory_influence`. Pre/post byte-identical row check.
    - **TestConstantsAndShape (7):** tax rate, cooldown duration, difficulty, skill name, table shape, seam returns 1.0, cooldown key prefix shape.
  - `TODO.json` (modified): SYN.6.a → DONE; SYN.6.b queued.
  - `CHANGELOG.md` (this entry).
- **Tests:** +57 in `test_syn6a_active_harvest.py`. Adjacent regression sweep: SYN.1.a (43), SYN.2 (24), SYN.3.a (65), SYN.3.b (53), SYN.4a (30), SYN.4b (37), SYN.5 (47) = **299 prior SYN tests still green**. 10/10 consecutive runs of the new suite all 57/57 green — fully deterministic.
  - Sandbox is Linux/Python 3.12. Windows/Python 3.14 box is ground truth — `run_all_tests.bat` on apply.
- **What it shipped:**
  - **Active harvest as the larger income lever** per design §2.5.2. Passive yield (SYN.1.b) is the smaller, automatic-tick lever; active harvest is the player-driven larger one. A character standing in a wilderness region runs `harvest`, rolls Survival vs DC 6, and walks off with 100-800cr + stackable resources at quality 1..100.
  - **15% non-owner tax routed to owner treasury** per design §2.5.3. Visiting harvesters pay; the harvester is unaffected by tax-routing failures (their `credits_kept` is calculated locally). Logged for ops on failure.
  - **30-min per-region cooldown** with per-region namespacing — a harvester can cycle between regions without waiting on a single global cooldown.
  - **Cooldown sets even on failed skill check** to prevent slot-machine spam-rolling for Wild Die hits. Design call: harvest should feel measured, not gambled.
  - **SYN.6.b seam in place.** `_get_region_quality(db, region_slug)` returns 1.0 today; SYN.6.b only needs to swap the function body to wire weekly quality variance. No call site changes needed.
- **What it deliberately did not do:**
  - **Did not ship weekly region-quality variance** — that's SYN.6.b. The seam returns 1.0× (baseline → stack quality 50). SYN.6.b adds a Monday-midnight tick that rolls 0.7..1.3× per region and writes to a new column.
  - **Did not ship the Director resource-outlook digest.** Also SYN.6.b — consumes the same quality data, parser-side surface (`faction resource_outlook`).
  - **Did not invent a new `t5_rare` resource type.** Pivoted to "+1 rare stack at q100" so the existing crafting system sees the bonus immediately. When T5 crafting lands, recipes can gate on `min_quality ≥ 95`. Avoids a new RESOURCE_TYPES entry that would otherwise be dead until T5 ships.
  - **Did not gate harvest on a `harvest_node: true` YAML flag.** Pragmatic choice: any wilderness room with `wilderness_region_id` is harvestable. A later content pass (post-launch) can add the YAML flag and gate harvest on landmark rows specifically. Documented in module docstring as a deliberate design choice.
  - **Did not grant influence on harvest.** Pinned by `TestPerformHarvestNoInfluence`. Per §4.25 wilderness-only-influence invariant + design §2.7 reward table.
- **Pre-flight findings:**
  - **No phantom delivery risk.** `harvest`/`HARVEST` grep on HEAD returned 6 hits, all forward references explicitly tagged "ships in SYN.6" (the most prominent being `engine/territory.py:1085` — `tick_resource_nodes` no-op stub with "Active harvest ships in SYN.6" comment).
  - **Crafting resource model is `inventory.resources` (list of stacks), not `attributes.resources` (dict).** Initial harvest module v1 used the attribute-blob dict pattern (matching cooldowns/intel reports); pivoted to `engine.crafting.add_resource` after grepping the crafting module. This integration is invisible to the harvester but means harvested resources are immediately usable by crafting without any migration.
  - **Bug found and fixed in test:** my v1 of `_compute_tax` charged 15% tax even when there was no owner to route to — the credits silently vanished. Caught by `test_unowned_region_no_tax`. Fixed by adding `owner_exists` parameter; new test pins the corrected contract.
  - **Flake found and fixed in test:** initial tests put skills inside `attributes.skills`; `perform_skill_check._get_skill_pool` reads from a separate `char["skills"]` field. Six initial test branches used 6D survival which has a small but non-zero DC 6 failure rate, surfacing as ~10% test flakes. Fixed by giving the harvester 12D survival (knowledge 3D + survival 9D), guaranteeing the skill check passes deterministically. 10/10 consecutive runs green after.
- **Handoff:** `HANDOFF_MAY25_SYN6A.md`.

---

## 2026-05-25 — SYN.5 (espionage-as-influence + mission/bounty/PvP hooks retarget)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Sixth drop. Per design v2 §2.7 + §3.5. Single-session scope; no roll-up needed.
- **Files:**
  - `engine/intel_handlers.py` (new, ~520 LOC): the espionage redemption surface.
    - **Quality tiers per design §2.7:** `INTEL_QUALITY_LOW = (1, 3, 200, 500)`, `INTEL_QUALITY_MEDIUM = (4, 8, 600, 1500)`, `INTEL_QUALITY_HIGH = (10, 20, 2000, 5000)` — `(min_inf, max_inf, min_cr, max_cr)`. Quality determines the random range; the actual reward is sampled per redemption.
    - **`evaluate_intel_quality(report, known_regions, now)`** — heuristic stub. Scores on line count (cap +5), region mentions (+2 for any known region; +1 for 2+ regions or 3+ lines plus 1 region), freshness (+1 within 24h; -1 if stale past 3 days), and proper-noun-shaped tokens (+1 for capitalized multi-word phrase). Score ≥7 → high, ≥4 → medium, else low. Returns `{"quality", "score", "region_slug"}` where `region_slug` is the first known region mentioned in the report (None if none). T3.15 (Director AI CW-tuning) will replace this with a real LLM call; the function-level seam makes the swap cheap.
    - **`_extract_mentioned_regions(text, known_regions)`** — pure helper. Slug or spaced-form match, case-insensitive, word-boundary. **First-mention-order** sorted (caught during testing — initial implementation iterated the set in undefined order, which broke first-mention semantics).
    - **`sample_intel_reward(quality, rng=None)`** — pure RNG sampling within the quality tier. `rng` is injectable for deterministic tests.
    - **`find_handler_in_room(db, room_id, char_faction)`** — locates an intel handler NPC in the room that accepts the character's faction. Handlers are tagged in `ai_config_json` with `{"is_intel_handler": true, "faction": "<code>"}`. Untagged-faction handlers accept any faction (criminal-underworld information brokers).
    - **`handover_intel(db, char, handler_npc_id, report_id, session_mgr, rng)`** — main entry point. Validation chain (5 steps: faction membership, handler in room and matching faction, report held by char, report sealed, report not expired). On success: remove from holdings, evaluate quality, sample reward, credit credits, and apply influence delta to the report's named region's parent zone via `engine.territory.adjust_territory_influence(..., region_slug=...)` so SYN.3 contest multipliers fire. If the report doesn't describe any known wilderness region, credits pay out but influence is zero.
  - `engine/territory.py` (modified): three influence hooks retargeted per design v2 §2.7.
    - **`_resolve_room_region(db, room_id)`** — new helper. Returns `(wilderness_region_id, zone_id)` for a room; either tuple element may be None.
    - **`on_npc_kill(db, char, room_id)`** — now gates on `wilderness_region_id`. City-map kills are zero-influence; wilderness kills grant `INFLUENCE_NPC_KILL` (2) via the region-keyed path so contest multipliers fire.
    - **`on_mission_complete(db, char, room_id)`** — same gate. Wilderness completions grant `INFLUENCE_MISSION` (5); city-map completions are zero-influence (the mission's rep + credit awards live in the caller and still fire).
    - **`on_pvp_kill(db, winner, loser, room_id)`** — same gate. Wilderness winner gets `INFLUENCE_PVP_WIN` (15); loser pays 5 influence. City-map PvP (which requires consent gates upstream) is zero-influence either way.
  - `parser/espionage_commands.py` (modified): `IntelCommand` gains the `handover` subcommand. `+intel handover [<id>]` — with no id, picks the player's first sealed report; with an id, hands that specific sealed report. Routes through `find_handler_in_room` + `handover_intel`; player feedback includes quality tier + credit/influence breakdown.
  - `tests/test_syn5_espionage_as_influence.py` (new — 47 tests, 8 sections):
    - **TestExtractMentionedRegions (6):** empty text, empty regions, exact slug, spaced form, first-mention order, sub-word non-match.
    - **TestEvaluateIntelQuality (7):** None report → low, vague short report → low, specific recent → high, medium substance, stale penalized, no region → None region_slug, score clamped at zero.
    - **TestSampleIntelReward (4):** low/medium/high in-range, unknown quality → low fallback.
    - **TestHandlerNpcResolution (8):** non-handler rejected, no-faction-tag → any-faction accepted, faction match, faction mismatch, 'independent' faction → any, room hit, room miss, malformed ai_config_json skipped.
    - **TestHandoverIntelHappyPath (3):** credits + influence applied, report removed from holdings, high-quality report yields high-tier rewards.
    - **TestHandoverIntelRejections (7):** independent char, missing handler, wrong faction handler, handler in different room, unknown report id, unsealed draft, expired report.
    - **TestInfluenceHooksRetarget (9):** NPC-kill city-map → 0 inf, NPC-kill wilderness → +2, mission city-map → 0, mission wilderness → +5, PvP city-map → 0 for both sides, PvP wilderness → +15 winner / -5 loser, independent attacker → no-op, orphan zone_id → safe skip.
    - **TestConstantsAndShape (3):** quality tiers match design, handler AI key, module exports.
  - `TODO.json` (modified): SYN.5 → DONE with combined scope.
  - `CHANGELOG.md` (this entry).
- **Tests:** +47 in `test_syn5_espionage_as_influence.py`. Adjacent regression sweep:
  - SYN.1.a (43), SYN.2 (24), SYN.3.a (65), SYN.3.b (53), SYN.4a (30), SYN.4b (37), SYN.5 (47) = 299 in SYN family.
  - secmod1 (43), B1c (26), T2.WENC (28), wilderness_drop2 + phase2 (92), hygiene (11) = 200 adjacent.
  - drop_h_combat_npcs + w_2_4_combat_wilderness + session49_faction_missions + B6/B1b1/B1c/B1d3 = 191 combat/faction adjacent.
  - cities_phase4/4b/5/6_maint + pvp_display + pvp_flag + f8c2b2_chain_events = 220 broader adjacent.
  - **= 943 green across the SYN + adjacent sweep.**
  - Sandbox is Linux/Python 3.12. Windows/Python 3.14 box is ground truth — `run_all_tests.bat` on apply.
- **What it shipped:**
  - **Two-tier influence reward rule, fully wired.** Per design v2 §2.7 table: city-map activity yields rep + credits + CP but no influence delta; wilderness activity yields the same plus the design-table influence delta. The three engine hooks all gate on `room.wilderness_region_id`. The constants `INFLUENCE_NPC_KILL=2`, `INFLUENCE_MISSION=5`, `INFLUENCE_PVP_WIN=15` already matched the design — only the gate logic was the work item.
  - **Espionage-as-influence path live.** Players who build espionage characters (perception + con + search) can now turn intel into faction influence on top of credits. A high-quality, specific, recent report describing a wilderness region yields 10-20 influence + 2000-5000 credits in that region; a vague report still pays credits but no influence.
  - **Director-AI seam in place.** `evaluate_intel_quality` is a heuristic stub that's good-enough for SYN.5 ship. T3.15 (Director AI CW-tuning) will swap it out for a real LLM call without touching any of the call sites or the redemption flow.
  - **Handler NPCs are content, not code.** Intel handlers are NPCs tagged via `ai_config_json` with `{"is_intel_handler": true, "faction": "<code>"}`. No new schema. Faction HQs get handler NPCs by populating that ai_config field; a follow-up YAML drop can seed handlers at all 9 faction HQs in one pass.
- **What it deliberately did not do:**
  - **Did not seed handler NPCs at faction HQs.** Content drop, not engine drop. The engine treats any NPC with the `is_intel_handler` tag as a handler; populating those tags is a small follow-up YAML edit or admin-spawn pass after the engine drops land.
  - **Did not implement cross-faction intel laundering** (e.g. selling Rebel intel to a Hutt broker for a discount). The handler-faction match is strict (or independent-handler accepts-all). Cross-faction laundering is a future feature with interesting RP implications.
  - **Did not implement intel-report bartering between players** beyond what `+intel give` already supports. Player-to-player intel trading is design-level fine — the handover surface is for redemption only.
  - **Did not retarget the existing zone-influence economy hooks** (e.g. anywhere `invest_influence` or other treasury-to-influence flows fire). Those operate on zone influence directly and are not part of the §2.7 reward-rule retarget.
- **Pre-flight findings:**
  - **The `wilderness_region_id` column already gates city-map vs wilderness rooms.** The room model carries this since v19 (May 3 2026); null for hand-built rooms, set on wilderness landmark rows. The retarget is just "ask the room which kind it is".
  - **The SYN.3 `region_slug` kwarg on `adjust_territory_influence` is the right seam.** It already applies contest multipliers; SYN.5's hooks just pass it down. No engine changes needed in `adjust_territory_influence` itself.
  - **`INFLUENCE_*` constants matched design out of the box.** Brian had set them to 2/5/15 already; no tuning needed.
  - **First-mention order matters in region extraction.** A report mentioning multiple wilderness regions could be about either, but design intent is "the region the intel describes" — which the heuristic interprets as the first one named. Initial implementation iterated the `known_regions` set, which is unordered; caught during testing and fixed via position-sort.
- **Handoff:** `HANDOFF_MAY25_SYN5.md`.

---

## 2026-05-25 — SYN.4 (cities retarget to wilderness regions + migration + vitality, combined)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Fifth drop in the SYN sequence. Originally scoped ~2 sessions; landed as a single combined drop per Brian's standing roll-up call (same pattern as SYN.3 earlier today).
- **Files:**
  - `engine/player_cities.py` (modified, +~720 LOC SYN.4 section appended): the new region-anchored founding + landmark expansion + vitality state machine + one-shot migration. Constants section adds `CITY_FOUNDING_MIN_FOOTHOLD` (50, alias of `MIN_INFLUENCE_TO_FOUND`), `CITY_VITALITY_ACTIVE_WINDOW_DAYS` (7), `CITY_VITALITY_DORMANT_GRACE_DAYS` (14), `CITY_VITALITY_TAX_MULTIPLIER_REDUCED` (0.5), `CITY_VITALITY_THRESHOLDS` (outpost 1, chapter house 3, fortress 5), `SYN4_MIGRATION_REFUND_RATIO` (0.75), `SYN4_MIGRATION_KEY` (`syn4_cities_dissolved`). Schema gains two additive columns via idempotent `ALTER TABLE` inside `ensure_schema`: `vitality_state TEXT NOT NULL DEFAULT 'active'` and `vitality_below_since REAL DEFAULT NULL`.
    - `found_city_in_region(db, char, name, region_slug)` — new founding surface. 11-step validation chain mirrors the legacy `found_city` shape but swaps steps 7-10 (the HQ-zone → declared-security → influence chain) for a region-eligibility check: owned by self → OK no influence check; owned by rival → reject (must contest first); un-owned → require `CITY_FOUNDING_MIN_FOOTHOLD` influence in the region's parent zone. Inserts the city with `wilderness_region_id = region_slug` and `vitality_state = 'active'`.
    - `claim_landmark_for_city(db, char, target_room_id)` — new expansion surface. Validates target is a landmark of the city's region, contiguous (via the existing `_is_contiguous_to_city` helper — landmark rooms are normal rooms with normal exits, so the contiguity semantic is unchanged), under the HQ-tier expansion cap, and that vitality is `active` (reduced/dormant blocks expansion per design §2.9.4). Rejects legacy city-map cities with a clear actionable error pointing to dissolve + re-found.
    - `count_active_citizens(db, city_id)` — joins `memberships` ⋈ `characters.last_login` filtered to `last_login >= now - 7d`.
    - `compute_vitality_threshold(hq_tier)` — pure rule, returns the per-tier threshold (defaults to 1 for unknown tiers).
    - `compute_vitality_state(active_count, threshold, below_since, now)` — pure-rule state machine returning `(state, new_below_since)`. Four-branch logic: at/above threshold → active + clear below_since; below threshold + below_since=None → reduced + record now; below + within 14-day grace → reduced + preserve below_since; below + past 14-day grace → dormant + preserve below_since. Recovery is single-tick.
    - `tick_city_vitality(db, session_mgr)` — hourly tick. Per-city failures are caught and logged so one bad row doesn't kill the whole tick. Broadcasts `[CITY DORMANT]` / `[CITY ACTIVE]` lines on notable transitions only (entering dormant or recovering from dormant).
    - `effective_tax_rate_cap(city)` — pure rule: returns `rate_cap * 0.5` when vitality is reduced/dormant, else `rate_cap` unchanged. (Wiring at `set_city_tax_rate` will land in a follow-up; this drop only ships the seam.)
    - `syn4_migrate_dissolve_city_map_cities(db)` — one-shot migration. Idempotent via `syn_migration_state` row keyed `syn4_cities_dissolved` (same pattern as SYN.1.b's `territory_claims` wipe). Targets cities where `wilderness_region_id IS NULL OR = ''` AND `state = 'active'`. For each match: read founding cost from `FOUNDING_COSTS[hq_tier]`, credit `floor(cost * 0.75)` to the org treasury, DELETE all `player_city_rooms` rows for the city, UPDATE state to 'dissolved' with `grace_started_at = now`. Returns a summary dict: `{"ran", "dissolved_count", "total_refunded", "cities": [...]}`.
  - `parser/city_commands.py` (modified):
    - `_handle_found` accepts the new `+city found <name> in <region_slug>` form. Token-level detection via last-` in `-with-spaces split, with a no-spaces-in-slug guard so multi-word names containing 'in' don't false-positive. Falls through to legacy `found_city` when no `in <slug>` suffix is present.
    - `_handle_claim` looks up the active org's city first; if `wilderness_region_id` is set, routes to the new `claim_landmark_for_city`; otherwise falls through to legacy `claim_room_for_city`. The user-facing `+city claim <direction|room_id>` syntax is unchanged.
  - `server/tick_handlers_economy.py` (modified): adds `city_vitality_tick(ctx)` wrapper around `engine.player_cities.tick_city_vitality`.
  - `server/game_server.py` (modified): registers `city_vitality_tick` in the scheduler at `interval=3600, offset=1900` (between `territory_presence@1800` and `territory_contests@2700`).
  - `tests/test_syn4a_city_region_anchor.py` (new — 30 tests, 4 sections): founding happy path, each validation rejection (independent faction, low rank, duplicate name, no HQ, unknown region, existing city for org, insufficient treasury), treasury debit, HQ anchoring, region eligibility (owned-by-self, owned-by-rival, un-owned with/without/at/just-below foothold), landmark expansion (adjacent succeed, non-landmark reject, non-adjacent reject, size cap, vitality reduced+dormant blocks, legacy city refused), constants invariants.
  - `tests/test_syn4b_vitality_and_migration.py` (new — 37 tests, 8 sections): `compute_vitality_threshold` per tier, `compute_vitality_state` full 6-case state machine (at/above, recovery clears below_since, first drop records now, within grace preserves below_since, exactly 14d transitions to dormant, past 14d remains dormant), `effective_tax_rate_cap` per state, `count_active_citizens` (no members, one active, old login excluded, mixed, missing last_login, nonexistent city), `tick_city_vitality` full path (active stays active, drops to reduced, becomes dormant after 14d, recovers from dormant, dissolved skipped, chapter house threshold), migration happy path (75% refund + state + rooms cleared), migration idempotency (second run no-op, marker recorded, no double-credit), migration scope (skips wilderness-anchored, skips already-dissolved, handles empty-string region_id).
  - `TODO.json` (modified): SYN.4 marked DONE, scope reflecting the parallel-ship pattern + the new test sections.
  - `CHANGELOG.md` (this entry).
- **Tests:** +67 across two new files (`test_syn4a_city_region_anchor.py` 30 + `test_syn4b_vitality_and_migration.py` 37). Existing 520 cities tests (phase 1, 2, 3, 4, 4b, 5, 6_admin, 6_maintenance, 6_web_ui, 7_guards, 7c_combat, help_topics) all stay green. Adjacent regression sweep covers SYN.1.a (43), SYN.2 (24), SYN.3.a (65), SYN.3.b (53), secmod1 (43), B1c (26), T2.WENC (28), wilderness_drop2 + phase2 (92 combined), hygiene (11). **485 green across the SYN + adjacent sweep. 587 green when cities phases are added on top.**
- **What it shipped:**
  - **Region-anchored city founding.** A city's HQ now anchors on a wilderness landmark instead of a city-map zone. Founding rules: an org owning the region needs no influence check; an org without ownership but with 50+ influence (Foothold) in the region's parent zone can stake a claim with infrastructure; an org without either is rejected with a clear contest-first directive. The five city benefits (identity, tax, citizen security upgrade, +city home, mayor governance) are all preserved as-is.
  - **Landmark-adjacency expansion.** Cities expand by claiming adjacent landmark rooms within the same region. The contiguity semantic is identical to the legacy per-room expansion since landmark rooms are real rooms with normal exits — the change is just constraint (must be a landmark, must be in the same region).
  - **City vitality state machine.** Cities below their HQ-tier active-citizen threshold drop to `reduced` immediately and to `dormant` after 14 consecutive days under threshold. Reduced/dormant blocks expansion and halves the tax cap. Recovery is single-tick: get back to threshold and the next hourly tick clears the state.
  - **One-shot dissolution migration.** All pre-pivot city-map cities are dissolved with a 75% treasury refund. The migration is idempotent: a row in `syn_migration_state` records that it ran, so re-bootstrapping the schema never re-dissolves already-migrated cities. Founders are compensated for the platform's pivot by the extra-generous refund (legacy `dissolve_city` returns 50%; SYN.4 migration returns 75%).
  - **Parallel-ship pattern preserved.** The legacy `found_city` and `claim_room_for_city` keep working — the 520 existing cities tests stay green without retargeting. The new surfaces ship alongside; the parser routes by checking `wilderness_region_id` on the active city.
- **What it deliberately did not do:**
  - Did not delete the legacy `found_city` / `claim_room_for_city` surfaces. Removing them depends on the migration having run in production AND every existing cities test being retargeted to wilderness fixtures — that's its own ~2-session refactor. The cleaner separation is to ship the new engine + migration now and remove the legacy in a follow-up after the runtime confirms no orphan legacy cities remain.
  - Did not run the migration automatically. `syn4_migrate_dissolve_city_map_cities` is an engine surface, not a server-boot tick. The actual cutover happens via an admin/script invocation at apply time — the idempotency marker means re-running is safe.
  - Did not wire `effective_tax_rate_cap` into `set_city_tax_rate`. The seam is in place but the consumer is a small follow-up; rather than touch the existing tax-set validation chain in the same drop, the wiring lands later.
  - Did not implement the building construction system (SYN.9 scope per the drop plan).
  - Did not retarget the existing 520 cities tests to wilderness fixtures. They keep passing against the legacy API, which is intentional — the design note "Existing 553 cities tests update to wilderness-anchor fixtures" is its own work item that depends on the legacy API actually being removed, which is post-migration.
- **Pre-flight findings:**
  - **`wilderness_region_id` / `wilderness_x` / `wilderness_y` columns already exist on `player_cities`.** This made the schema delta tiny — only two vitality columns added. Pre-existing wilderness columns presumably from an earlier Phase 7 scoping pass; they were unused at HEAD but readily usable for SYN.4.
  - **`cooldowns_enabled` lives in `engine.jedi_gating`, not `engine.cooldowns`.** Initial implementation imported the wrong module; caught immediately by the test suite and corrected.
  - **`player_housing` keys HQ on `(housing_type='org_hq', faction_code=?)`.** Easy to miss because the rest of the schema uses `org_id` more directly. The test fixtures needed an explicit `seed_hq` helper that matched the real column layout.
  - **The existing `_is_contiguous_to_city` helper works unchanged.** It walks the `exits` table for any source-to-target connection; landmark rooms are normal rooms with normal exits, so no special-case logic was needed.
  - **Founding-cost determination still routes through `_infer_hq_type`.** The HQ's `storage_max` (100/200/400) maps to outpost/chapter_house/fortress. This is unchanged from legacy founding — the HQ-tier influence on the city is the same in both paths.
- **Handoff:** `HANDOFF_MAY25_SYN4.md`.

---

## 2026-05-25 — SYN.3 (region contest state machine, combined: schema + culminating fight + Drop 6D deletion)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Fourth drop in the SYN sequence. Originally split into SYN.3.a (schema + engine half) and SYN.3.b (culminating fight + caller retargets + Drop 6D physical deletion) per the two-session split discipline (mirrors SYN.1.a/SYN.1.b). SYN.3.a delivered in a session earlier today; SYN.3.b queued. **Brian called the roll-up: both halves consolidated into a single combined drop before SYN.3.a shipped externally.** SYN.3.a never landed as a standalone drop — its scope is fully subsumed by this entry.
- **Files:**
  - `engine/contest.py` (new, ~1700 LOC). The full module covers both halves:
    - **Schema half (was SYN.3.a):** `region_contests` table (id, region_slug, defender_org_code [nullable for un-owned seize], challenger_org_code, zone_id, started_at, accumulation_ends_at, ends_at, anchor_landmark_id, anchor_npc_id, status) with `UNIQUE(region_slug, status)` enforcing at-most-one-active-per-region; `region_contest_cooldowns` table (region_slug, org_code, cooldown_until) with PRIMARY KEY (region_slug, org_code); five supporting indexes.
    - **Constants per design §2.4:** `REGION_CONTEST_DURATION_SECS = 7 days`; `REGION_CONTEST_CULMINATING_SECS = 4 hours`; `REGION_CONTEST_ACCUMULATION_SECS = DURATION - CULMINATING` (derived; module-load-time assertion guards the invariant that the two phases sum exactly to 7 days, since the design's "Days 1-6" calendar shorthand would have summed to 6d4h); `REGION_CONTEST_TRIGGER_RATIO = 0.75`; `REGION_CONTEST_MIN_CHALLENGER_INFLUENCE = 50`; `REGION_CONTEST_FAILURE_PENALTY = 25`; `REGION_CONTEST_COOLDOWN_SECS = 14 days`; `REGION_ANCHOR_BASE_HP = 100`; `REGION_ANCHOR_HP_FLOOR_INFLUENCE = 50`; `REGION_ANCHOR_REINFORCEMENT_THRESHOLD = 100`; `REGION_ANCHOR_REINFORCEMENT_PER = 25`; `OUTNUMBERED_DEFENDER_INFLUENCE_MULTIPLIER = 1.5`.
    - **Pure rules:** `compute_anchor_hp(defender_influence)`, `compute_anchor_reinforcements(challenger_influence)`, `compute_outnumbered_defender_multiplier(def_count, chall_count)`.
    - **Query surfaces:** `get_active_region_contest`, `get_org_region_contests`, `is_region_in_active_contest`, `is_org_on_contest_cooldown`.
    - **Declaration:** `declare_region_contest`, `check_and_declare_region_contests` (rival-held auto-trigger; un-owned regions deliberately not auto-triggered, per design §2.4 second bullet — parser-command-driven).
    - **Culminating fight (was SYN.3.b):** `_REGION_ANCHOR_TEMPLATES` for all 9 factions (GCW: empire/rebel/hutt/bh_guild; CW: republic/cis/jedi_order/hutt_cartel/bounty_hunters_guild) + `_default` for un-owned. `_anchor_hp_tier` buckets `compute_anchor_hp(defender_inf)` into `basic` (100-124) / `strong` (125-149) / `hardened` (150-174) / `fortress` (175-200) tiers; `_ANCHOR_TIER_STATS` matrix maps each tier to WEG D6 stat dice (STR drives damage soak, dodge drives miss rate — WEG D6 has no raw HP, so a higher-influence Anchor materializes as stronger soak rolls). `_build_anchor_sheet` (char_sheet_json), `_build_anchor_ai` (ai_config_json with `model_tier=2` per design's "Tier-2 NPC"). `_spawn_region_anchor(db, contest, session_mgr)` picks a region landmark uniformly at random, spawns the Anchor + N reinforcements (via `engine/territory._GUARD_TEMPLATES`), pins `anchor_npc_id`+`anchor_landmark_id` on the contest row, broadcasts `[CULMINATING FIGHT]`.
    - **Two-phase tick:** `tick_region_contest_resolution(db, session_mgr)` — Phase A spawns the Anchor when `now >= accumulation_ends_at AND ends_at > now AND anchor_npc_id IS NULL`; Phase B resolves expired contests as defender-win-by-default (preserves the SYN.3.a placeholder behavior as the no-kill fallback).
    - **Kill detection:** `on_npc_killed_in_combat(db, npc_id, killer_char, room_id, session_mgr)` — wired into the combat NPC-death hook. Looks up active contests by `anchor_npc_id`; if killer's faction = challenger → `_resolve_challenger_win`; if = defender → defender win; if independent/None → defender win by default.
    - **Ownership transfer:** `_resolve_challenger_win` marks status='resolved_challenger', dismisses old garrison via `dismiss_region_garrison`, UPSERTs `region_ownership` with `claimed_by = -contest_id` sentinel (distinguishes contest-wins from player claims in audit log), spawns new garrison via `spawn_region_garrison`, defender pays 25-influence penalty + 14-day cooldown, broadcasts `[REGION SEIZED]`.
    - **Influence multipliers:** `apply_contest_influence_multipliers(db, org, slug, delta)` — returns delta unchanged if delta≤0 or no active contest or org not a contestant; otherwise 2× doubling for both sides; defender additionally gets 1.5× outnumbered bonus (`_count_org_members` joins `memberships` ⋈ `organizations` on `org_id`).
    - **Admin path:** `cancel_region_contest(db, contest_id, reason)` — marks status='failed' with no penalty or cooldown.
    - **Display:** `get_region_contest_status_lines(db, org_code)` renders `[ANCHOR PHASE]` tag once `now > accumulation_ends_at`.
  - `engine/territory.py` (modified):
    - `adjust_territory_influence` gains optional `region_slug` kwarg. When passed with positive delta, calls `apply_contest_influence_multipliers` before applying. After persisting, auto-trigger check swapped from removed `check_and_declare_contests` (Drop 6D) to `check_and_declare_region_contests`. Backward compatible: callers that don't pass `region_slug` are unaffected.
    - **Drop 6D contest block physically deleted.** Lines 1340-1804 of pre-drop territory.py — 442 lines, 12 surfaces — replaced with a 24-line retirement header comment listing every retired surface: `territory_contests` schema, `ensure_contest_schema`, `get_active_contest`, `get_contests_for_org`, `is_in_active_contest`, `_declare_contest`, `check_and_declare_contests`, `tick_contest_resolution`, `_transfer_zone_claims`, `hostile_takeover_claim`, `get_contest_status_lines`, and the `CONTEST_*` constants.
    - `ensure_contest_schema(db)` call removed from `ensure_territory_schema`. Dangling `get_contest_status_lines` call in `get_claims_status_lines` swapped to `engine.contest.get_region_contest_status_lines`.
  - `server/session.py` (modified): `_hud_territory` retargeted. Pre-drop: `get_claim` + `get_active_contest` + `get_room_zone_id` (zone-keyed Drop 6D). Post-drop: resolves room's `wilderness_region_id`; calls `engine.territory.get_region_owner` + `engine.contest.get_active_region_contest`. New HUD fields: `contest_region`, `contest_defender`, `contest_culminating`. City-map rooms (no wilderness_region_id) get neither badge nor contest — they're neutral commons per design §0+§1.3.
  - `parser/combat_commands.py` (modified):
    - `_check_territory_contest_override` retargeted from `is_in_active_contest` (zone-keyed) to `is_region_in_active_contest` (region-keyed via room's `wilderness_region_id`). Broadcast text changed `[TERRITORY WAR]` → `[REGION CONTEST]`.
    - NPC-death hook: replaced Drop 6D hostile-takeover-on-guard-kill block with a loop calling `on_npc_killed_in_combat(db, npc_id, killer, room_id, session_mgr)` for every dead NPC. Handler is no-op for non-Anchor NPCs (cheap).
  - `parser/faction_commands.py` (modified): `_cmd_seize` method body **deleted** along with its dispatch table entry, its line in the help text, its mention in the unknown-subcommand fallback message, and its mention in the usage string. Replaced with a retirement comment explaining region-level seizure now happens organically through the contest state machine.
  - `server/tick_handlers_economy.py` (modified): `territory_contests_tick` retargeted from removed `engine.territory.tick_contest_resolution` to `engine.contest.tick_region_contest_resolution`. Scheduler entry name preserved (no change needed in `server/game_server.py`).
  - `tests/test_syn3a_region_contest_state_machine.py` (new — 65 tests, was SYN.3.a's): 9 sections covering schema, pure rules, query surfaces, declaration (rival-held + un-owned), cooldown, auto-trigger (rival-held + un-owned), placeholder tick, status lines.
  - `tests/test_syn3b_anchor_kill_and_multipliers.py` (new — 53 tests): 12 sections covering Anchor HP tier boundaries (4), templates (2), build-anchor-sheet (4), two-phase tick (5), spawn flow (4 including no-landmarks + un-owned + reinforce-count + landmark-pick), kill detection (6 covering challenger/defender/independent/None/non-anchor/zero-id paths), challenger-win resolution (6 including unowned-region + broadcast), influence multipliers (7), `adjust_territory_influence` hook (3), cancel (5), Drop 6D physical-deletion sanity (3), caller-retarget source-level checks (4).
  - `TODO.json` (modified): SYN.3.a (DONE) + SYN.3.b (queued) collapsed into a single SYN.3 (DONE) entry recording the combined drop.
  - `CHANGELOG.md` (this entry — replaces the SYN.3.a entry that never shipped).
- **Tests:** +118 across two new files (`test_syn3a_region_contest_state_machine.py` 65 + `test_syn3b_anchor_kill_and_multipliers.py` 53). Adjacent regression sweep, all green:
  - SYN.1.a region ownership: 43
  - SYN.2 wilderness-aware security: 24
  - SYN.3.a region contest state machine: 65
  - SYN.3.b anchor kill + multipliers: 53
  - secmod1 admin security: 43
  - B1c territory constants era-aware: 26
  - T2.WENC wilderness encounters: 28
  - security resolver runtime + writer-merge + zone coverage: 22
  - wilderness drop2 + drop2_phase2: 92 combined
  - PvP display surfaces + flag unit: covered by 33-test sweep
  - WoW.1/2a/2b/2c/3a/3b/4 (combat-hooks adjacent): 286 in the bundle
  - drop_h_combat_npcs + W.2.4 combat wilderness: 46
  - Faction missions session49 + B1b1 organizations + B1d3 CW faction anchors + B6 defensive faction + F5 wilderness integration + F5b1 faction quarters: full coverage
  - TODO/CHANGELOG hygiene + encoding hygiene: 9
  - **= 889 adjacent tests green.**
  - Single failure encountered in the sweep is `test_wow3c_dsp_fp_wiring.py::TestNoLeftoverAdminFpModule::test_admin_fp_module_removed` — pre-existing WoW.4 housekeeping debt (`parser/admin_fp_commands.py` should have been deleted in WoW.4 but wasn't). Unrelated to SYN.3.
  - Sandbox is Linux/Python 3.12. Windows/Python 3.14 box is ground truth — `run_all_tests.bat` on apply.
- **What it shipped:**
  - **Region-keyed contest state machine, fully operational.** The 7-day total duration splits exactly into accumulation + 4-hour culminating window via a derived constant guarded by a load-time assertion. Both rival-held (75% ratio auto-trigger) and un-owned (direct API call) declaration paths work. Defender slot is NULL for un-owned seize contests. 14-day post-loss cooldown enforced per (region_slug, org_code) at both auto-trigger and direct-declare paths.
  - **Anchor NPC culminating fight.** When a contest enters its final 4 hours, the Anchor spawns at a randomly-chosen landmark in the region — flavored to the defending faction (or `_default` template for un-owned regions), HP-tier-scaled by defender influence (basic/strong/hardened/fortress brackets translating to WEG D6 stat-dice boosts on STR and dodge), with `compute_anchor_reinforcements(challenger_influence)` tier-1 reinforcement NPCs alongside. The `[CULMINATING FIGHT]` broadcast announces the spawn to all online players.
  - **Killing-blow ownership transfer.** When the Anchor NPC dies in combat, the killer's faction wins the contest. Ownership transfers cleanly: old garrison dismissed, `region_ownership` UPSERTed with the new org code, fresh garrison spawned. For un-owned-region seizures the prior-owner side is just NULL, no garrison to dismiss. The losing defender (if any) pays the 25-influence penalty and enters the 14-day cooldown — symmetric with the defender-win-by-default outcome's challenger penalty. `[REGION SEIZED]` broadcast announces the outcome.
  - **Influence-doubling mechanism.** `apply_contest_influence_multipliers` applies the 2× doubling (both sides during an active contest) and the 1.5× outnumbered-defender bonus (defender side only, when challenger member count > defender). Hook lives in `adjust_territory_influence` behind an optional `region_slug` kwarg — domain callers (missions, bounties, harvests) wire the region context where applicable. SYN.3 ships the multiplier mechanism; the consumer hooks land in SYN.5 (espionage-as-influence) and SYN.6 (harvest).
  - **Drop 6D physically retired.** All 12 zone-keyed contest surfaces are gone from `engine/territory.py`; `_cmd_seize` is gone from `parser/faction_commands.py`; all 5 callers (HUD, PvP gate, NPC death, dispatch, tick handler) point at SYN.3. The `RETIRED in SYN.3` comment block in territory.py documents what was deleted so future readers don't go looking for it in git history.
- **What it deliberately did not do:**
  - Did not retarget domain hooks (mission/bounty/harvest reward paths) to pass `region_slug` for influence-doubling. The multiplier mechanism is in place; the consumers are SYN.5+SYN.6 work. Each hook will add the `region_slug=...` kwarg at its call site when it lands.
  - Did not re-key influence to regions. Influence remains zone-keyed in HEAD per the SYN.1.a `claim_region` docstring's "transitional rule for SYN.1; SYN.3 will make this strictly per-region once influence is region-keyed" note. The deeper per-region influence refactor is potentially SYN.6 (harvest + region quality) or later.
  - Did not add a `+region challenge` parser command for un-owned-region seize. The engine supports it via `declare_region_contest(defender=None, ...)`, but no parser surface invokes it yet. That command can ship in a small follow-up drop or with SYN.4.
  - Did not implement the daily contest digest. The design mentions a "news digest hook" — that's a small follow-up easier to land alongside the news/log subsystem changes than as a one-off.
- **Pre-flight findings (re-confirmed from SYN.3.a's session, plus SYN.3.b additions):**
  - **Drop 6D auto-trigger was inert at HEAD.** Since SYN.1.b wiped `territory_claims`, the legacy `check_and_declare_contests` found no zone claim rows and returned early. No race between the two engines during the parallel-ship window. Now moot — Drop 6D block is physically deleted.
  - **Influence stays zone-keyed (transitional).** Per-region influence is a deeper refactor; the 75% trigger ratio and 25-influence failure penalty operate on parent-zone influence.
  - **WEG D6 has no raw HP.** Anchor "HP" is narrative — stored as `anchor_target_hp` in the Anchor's char_sheet_json for display. Kill detection uses the standard `wound_level >= 5` check on the contest's `anchor_npc_id`. The HP-tier system instead drives stat-dice boosts (STR/dodge), which is the mechanically-correct way to make an Anchor "take more hits" within WEG D6's wound-level resolution.
  - **`memberships` keys on org_id not org_code.** The outnumbered-defender member count joins `memberships` with `organizations` on `org_id`, looking up `o.code = ?`. Verified against existing usage in `engine/organizations.py`.
  - **Status enum.** `'active' | 'resolved_defender' | 'resolved_challenger' | 'failed'`. UNIQUE(region_slug, status) lets at-most-one-active-per-region coexist with arbitrary resolved/failed history rows. `'failed'` is reserved for admin-cancellation; ordinary outcomes route through `resolved_*`.
- **Handoff:** `HANDOFF_MAY25_SYN3.md`.

---


## 2026-05-24 — SYN.2 (wilderness-aware security branch)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Third drop in the SYN sequence. Adds the wilderness-aware security resolution step per `contestable_wilderness_design_v2.md` §2.3 + §3.2. SYN.3 (contest state machine + culminating fight) next.
- **Files:**
  - `engine/security.py` (modified):
    - New `_get_wilderness_region_state(room, db)` helper reads `default_security` from the `wilderness_regions` registry table (populated by `engine/wilderness_writer.py` at world-build time) and `org_code` from `region_ownership` (SYN.1.a). Returns `{slug, default_security, owner_org}` or None if the region isn't registered.
    - New `_apply_wilderness_ownership(base, character, region_state)` is the pure citadel-upgrade rule: LAWLESS → CONTESTED for characters in the owning org; base stands for outsiders or un-owned regions; CONTESTED stays CONTESTED (no double promotion to SECURED, which is impossible in wilderness by design).
    - `get_effective_security` gains a new step 4 between the Director influence overlay (step 3) and the room/zone property fallback (step 5). Step 4 is terminal for wilderness rooms — when the room has `wilderness_region_id` set and the region is in the registry, the branch resolves through the helpers above and returns via `_finalize`. Rooms whose region isn't in the registry (stale ref, world not yet built) fall through gracefully to step 5.
    - `_apply_claim_upgrade` physically deleted (was a no-op stub from SYN.1.b). `_finalize` stripped of its `claim_upgrade` call — now runs only `_apply_faction_override` and `_apply_city_upgrade`.
    - Docstring of `_finalize` updated to record the SYN.2 retirement.
  - `tests/test_syn2_wilderness_aware_security.py` (new — 24 tests across 6 sections: pure citadel-upgrade rule unit tests, DB-backed region state lookup, full step 4 integration in `get_effective_security`, retirement sanity checks (`_apply_claim_upgrade` symbol gone; `_finalize` no longer calls it), city-map isolation, and Director-overlay short-circuit precedence).
  - `tests/test_secmod1_admin_security.py` (modified — `TestClaimUpgradeCompose` docstring updated to reflect that `_apply_claim_upgrade` is now physically deleted, not just stubbed. Assertion + test body unchanged from SYN.1.b — the no-op outcome was always observed through `_finalize`, not by importing the deleted symbol).
  - `TODO.json` (modified — SYN.2 flipped `queued → DONE` with done_date and resolution recording the wilderness branch + the `_apply_claim_upgrade` physical deletion; `tech_debt::shipped_surfaces_retiring_in_SYN_sequence` entry for `_apply_claim_upgrade` transitioned from `retired_in_SYN.1.b_2026_05_24` to `physically_deleted_in_SYN.2_2026_05_24 (was stubbed in SYN.1.b)` so the historical retirement event is preserved alongside the physical-deletion event).
  - `CHANGELOG.md` (this entry).
- **Tests:** +24 (`tests/test_syn2_wilderness_aware_security.py`). One test docstring updated (`test_faction_override_runs_claim_upgrade_now_noop`) — assertion and body unchanged. Adjacent regression sweep: 313 tests green across SYN.1.a region ownership (43), SYN.2 wilderness branch (24), secmod1 admin security (43), territory constants (26), wenc encounters (28), security resolver runtime + writer merge + zone coverage + yaml audit, wilderness drop2 + drop2_phase2 (53), TODO/CHANGELOG hygiene (9). Cities phases 1-7c: 396 tests green. Combat regression: 77 tests green (w_2_4_combat_wilderness, w2_3_combat_source_char, wow3a_combat_hooks, drop_h_combat_npcs).
- **What it shipped:**
  - **Step 4: Wilderness ownership branch.** When a player is in a room with `wilderness_region_id` set, security now resolves through the region's `default_security` (from the `wilderness_regions` YAML registry) plus its current owner (from `region_ownership` table). A Hutt PC standing at Anchor Stones in a Hutt-owned Dune Sea sees CONTESTED (citadel upgrade from the region's LAWLESS base). A Rebel PC at the same room sees LAWLESS — hostile territory, no upgrade. An NPC observer or system query (no character context) sees the region's base tier unchanged. Per design §2.3, this step is *terminal* for wilderness rooms; the city-map fallback (step 5) doesn't apply, but `_finalize`'s SECMOD.1 faction-override + city-upgrade still run so that wilderness-anchored cities (the universal case after SYN.4) continue to grant citizen upgrades correctly.
  - **Director overlays still win.** Steps 1-3 (transient admin override, env-key Director override, live influence thresholds) run before step 4 and short-circuit it. An admin `@security` override on a wilderness zone produces the override level regardless of region ownership — preserving the admin's intent to e.g. lock down a zone during a live event.
  - **`_apply_claim_upgrade` physically deleted.** The stub from SYN.1.b is gone. `_finalize`'s post-resolve chain is now just `_apply_faction_override → _apply_city_upgrade`. The deletion is observable in source but not in any test assertion that imported the symbol — `test_secmod1_admin_security.py::TestClaimUpgradeCompose` was already updated in SYN.1.b to observe behavior through `_finalize`, not by reaching into the deleted private surface.
  - **Graceful fallback for unregistered regions.** If a room has `wilderness_region_id` set but the slug isn't in `wilderness_regions` (e.g. stale data, partial world build, manual SQL write), `_get_wilderness_region_state` returns None and the branch falls through to step 5. This means the wilderness branch's correctness is tied to the existing `wilderness_writer.py` discipline rather than introducing a new failure surface; if a deploy ships rooms without their region registered, security still resolves through the city-map path rather than wedging.
  - **Pure rule extracted.** `_apply_wilderness_ownership` takes no DB and is therefore unit-testable without setup; the DB-touching lookup is in the separate `_get_wilderness_region_state` helper. Six unit tests on the rule cover every cell of the ownership × character-faction matrix (unowned, owned-by-own, owned-by-rival, contested base, no character, independent PC).
- **What it deliberately did not do:**
  - Did not touch any wilderness writer / loader. The `wilderness_regions` table is read as-is.
  - Did not touch `region_ownership` (SYN.1.a's domain) or the contest state machine (SYN.3's domain).
  - Did not retarget any city-map rooms — those continue to resolve through steps 5-6 unchanged.
- **Pre-flight finding:** The design doc §2.3 description ("If the character is in wilderness (`wilderness_region_slug` set)") describes character-state, not room-state. Implementation reads the *room's* `wilderness_region_id` instead, which is functionally equivalent (a character is "in wilderness" iff their current room has `wilderness_region_id`) and simpler — no character-state column read needed. The semantics match the design's intent verbatim.
- **Handoff:** `HANDOFF_MAY24_SYN2.md`.

---

## 2026-05-24 — SYN.1.b (legacy block stub-and-defang + call site retargets)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Second half of SYN.1. Pure mechanical retarget + retirement; no new logic. Closes the SYN.1 design step; SYN.2 next.
- **Files:**
  - `engine/territory.py` (modified — 8 legacy surfaces stubbed to no-ops with RETIRED docstrings; `CLAIM_MAX_PER_ZONE` / `CLAIM_MAX_TOTAL` deleted; 3 internal armory callers (`armory_deposit_item`, `armory_withdraw_item`, `armory_withdraw_resources`) retargeted to `is_region_owned_by` reading `wilderness_region_id` off the room; `get_claims_status_lines` retargeted to iterate `region_ownership`; new `_syn1b_wipe_territory_claims_once` helper appended; `ensure_territory_schema` now invokes the wipe helper once at first boot post-apply via a `syn_migration_state` marker table for idempotency).
  - `engine/security.py` (modified — `_apply_claim_upgrade` stubbed to no-op; pre-empted from SYN.2 since it cannot function without `is_room_claimed_by`).
  - `engine/sleeping.py` (modified — `is_room_claimed_by` consumer retargeted to `is_region_owned_by` reading `wilderness_region_id` off the room; safe-sleep bonus now applies in faction-owned wilderness regions, not city-map rooms).
  - `parser/faction_commands.py` (modified — `_cmd_claim` retargeted to `claim_region` with `wilderness_region_id` lookup; `_cmd_unclaim` retargeted to `unclaim_region`; `_cmd_guard` short-circuited with retirement message (legacy body preserved beneath the return for reference, cleaned up in SYN.4); both commands reject city-map rooms with a clear message).
  - `server/tick_handlers_economy.py` (modified — `territory_claim_tick` retargeted to `tick_region_maintenance`; `territory_resources_tick` retargeted to `tick_region_passive_yield`. Tick function *names* preserved so scheduler registration in server/game_server.py is unchanged).
  - `tests/test_secmod1_admin_security.py` (modified — `TestClaimUpgradeCompose::test_faction_override_then_claim_upgrade_composes` renamed to `test_faction_override_runs_claim_upgrade_now_noop`; assertion changed from CONTESTED to LAWLESS to reflect `_apply_claim_upgrade`'s no-op status; class docstring updated; monkey-patch of `is_room_claimed_by` removed (no longer needed)).
  - `TODO.json` (modified — SYN.1.b flipped `ready → DONE` with full resolution recording the stub-and-defang strategy and the SYN.2 pre-emption; 9 surfaces transitioned from `deprecated_after_design_pivot_2026_05_24` to `retired_in_SYN.1.b_2026_05_24` via `tools/syn_migration.py::tag_surface_retired`; SYN.2 entry annotated with `note_preempted_in_syn1b` recording that `_apply_claim_upgrade` is already a no-op stub; SYN.2's `retires_surfaces` cleaned to remove the pre-empted item).
  - `CHANGELOG.md` (this entry).
- **Tests:** No new tests (SYN.1.a tests cover the new surfaces; SYN.1.b is pure retarget). One test updated (`test_faction_override_runs_claim_upgrade_now_noop`). Sandbox sweep: 43 SYN.1.a + 43 secmod1 + 26 territory constants + 28 wenc + 5 security_resolver_runtime + 6 security_resolver_writer_merge + 52 wilderness_drop2 + zone coverage + yaml audit = 280 tests, all green. Cities sweep: phase1+phase2+phase3+phase4+phase5+phase6_maintenance+phase7_guards + TODO/CHANGELOG hygiene = 376 tests, all green.
- **What it shipped:**
  - **Stub-and-defang of 8 legacy surfaces.** `claim_room`/`unclaim_room` return `ok=False` with deprecation messages directing the player to the region command. `is_room_claimed_by` always returns `False` (the truth, post-wipe). `spawn_guard_npc` returns `ok=False`. `remove_guard_npc` returns `ok=True` no-op (also accepts `**kwargs` because the housing.py HQ-cleanup caller used `force=True` which never matched the old signature anyway — the kwarg tolerance preserves the silent-success behavior). `tick_claim_maintenance` and `tick_resource_nodes` are no-ops. `get_claims_status_lines` retargeted to iterate `region_ownership` instead of `territory_claims` (function name preserved so the parser import doesn't change).
  - **3 internal armory callers retargeted.** `engine/territory.py` `armory_deposit_item` / `armory_withdraw_item` / `armory_withdraw_resources` now check `is_region_owned_by(db, wilderness_region_id, org_code)` instead of `is_room_claimed_by`. The faction armory is accessible from any room inside a region owned by the org (much broader than the legacy per-room restriction).
  - **6 external `is_room_claimed_by` consumers handled:**
    - `engine/sleeping.py:63-64` → retargeted to `is_region_owned_by` (safe-sleep in owned wilderness regions).
    - `engine/security.py:223-224` (`_apply_claim_upgrade`) → stubbed to no-op (pre-empted from SYN.2).
    - `parser/faction_commands.py:566,572` (armory gate) → retargeted to `is_region_owned_by` (parallel to the 3 internal armory callers above; the gate now checks the room's region against the org).
  - **2 faction parser commands retargeted.** `faction claim` and `faction unclaim` now look up the player's room's `wilderness_region_id` and call `claim_region` / `unclaim_region`. City-map rooms (no `wilderness_region_id`) get a clear-message rejection pointing them to wilderness travel.
  - **2 tick handlers retargeted.** `territory_claim_tick` calls `tick_region_maintenance` (weekly upkeep with garrison-dismiss-then-lapse fallbacks); `territory_resources_tick` calls `tick_region_passive_yield` (daily lawless 100–250 / contested 50–150 to owners). Tick function names preserved so the scheduler registration in `server/game_server.py` doesn't need to change.
  - **`wipe_territory_claims` wired into boot.** New `_syn1b_wipe_territory_claims_once` helper in `engine/territory.py` creates a `syn_migration_state` marker table (idempotent), runs `DELETE FROM territory_claims` once, then writes a marker row so subsequent boots no-op. This is the cold-start wipe per design §1.4 — all influence carries forward (territory_influence untouched) but room-level claims are erased.
  - **`_apply_claim_upgrade` pre-empted from SYN.2.** The function is non-viable without `is_room_claimed_by`, so SYN.1.b stubs it to no-op (returns base unchanged). SYN.2's remaining scope — adding the wilderness-aware security branch in `get_effective_security` — is unaffected. SYN.2's TODO entry is annotated with this pre-emption note.
  - **CLAIM_MAX_PER_ZONE / CLAIM_MAX_TOTAL physically deleted.** Only used inside `claim_room`; replaced with a breadcrumb comment.
- **What it deliberately did not do:**
  - Did not physically delete the 8 stubbed function bodies. Their bodies are short no-op stubs that preserve the call signatures so external callers in `server/session.py` (HUD), `parser/builtin_commands.py` (look output via `get_claim_display_tag`), `parser/combat_commands.py` (hostile takeover, SYN.3's domain) continue to compile. Physical deletion follows in SYN.2/3/4 as those consumers move.
  - Did not delete `CLAIM_COST`, `CLAIM_WEEKLY_MAINT`, `CLAIM_MIN_RANK`, `GUARD_COST`, `GUARD_WEEKLY_UPKEEP`, `GUARD_MIN_RANK`, or `_GUARD_TEMPLATES`. `_GUARD_TEMPLATES` is still consumed by `spawn_region_garrison`; the others are referenced in surrounding display text and are cheap to leave.
  - Did not touch `engine/housing.py`. Its `remove_guard_npc(db, org_code, rid, force=True)` call was always silently failing (the old signature didn't accept `force`); the new stub accepts `**kwargs` so the call now returns `ok=True` silently — same observable behavior, less log noise.
  - Did not touch the Drop 6D contest state machine in `engine/territory.py` (`hostile_takeover_claim`, `tick_contest_resolution`, `_declare_contest`, `check_and_declare_contests`). That's SYN.3's domain (retargets the contest state machine to region-keyed).
- **Stub-and-defang rationale (explicit, for future readers):** The original SYN.0 Finding 2 enumerated 6 external `is_room_claimed_by` consumers. Pre-flight for SYN.1.b widened this to ~12 dependencies once `get_claim`, `get_claim_display_tag`, `get_claims_status_lines`, `_GUARD_TEMPLATES`, and the Drop 6D combat hooks were counted. Physical deletion of the 8 surfaces in one drop would have required simultaneous edits across `server/session.py`, `parser/builtin_commands.py`, `parser/combat_commands.py`, `parser/faction_commands.py` (guard handler), `engine/territory.py` armory/display, `engine/sleeping.py`, and `engine/security.py` — ~7 modules. The stub strategy: preserve signatures so external callers compile; return "false" answers so the surfaces are inert; rely on the cold-start wipe so display reads return naturally-empty results. Physical deletion deferred to SYN.2 (security branch retarget), SYN.3 (Drop 6D contest retarget), and SYN.4 (cities retarget — finally cleans the guard handler tail-end). This is a smaller-blast-radius variation of "loud-substitution": the swap is loud (RETIRED docstrings, retirement tags in TODO), the bodies just take longer to disappear.
- **Handoff:** `HANDOFF_MAY24_SYN1b.md`.

---

## 2026-05-24 — SYN.1.a (region ownership engine — data-only)

- **Wave:** SYN sequence — Contestable Wilderness pivot. Data-only first half of SYN.1, per the two-session-split discipline (medium-risk items: data-only first, code-flow second). Old surfaces remain operational through this drop; SYN.1.b retargets call sites and retires the legacy block.
- **Files:**
  - `engine/territory.py` (modified — `ensure_territory_schema` now transitively calls the new `ensure_region_ownership_schema`; ~310 LOC appended at the end of the file as a labeled "SYN.1.a Region Ownership — Contestable Wilderness pivot" block containing constants, schema SQL, public functions, garrison spawning, and two new tick handlers. The legacy `claim_room` / `unclaim_room` / `is_room_claimed_by` / `CLAIM_MAX_*` / `tick_claim_maintenance` / `tick_resource_nodes` / `spawn_guard_npc` block above is unchanged and continues to operate.)
  - `tests/test_syn1a_region_ownership.py` (new — 43 tests across 10 sections covering schema idempotency, introspection helpers, ownership queries, claim/unclaim validation chain + happy path, garrison spawn + dismiss, weekly maintenance tick with full/partial/lapse paths, daily passive yield, and integration with `ensure_territory_schema`).
  - `TODO.json` (modified — SYN.1 split into SYN.1.a (DONE) + SYN.1.b (ready); split rationale recorded; SYN.1.b retains the full list of surfaces it will retire so SYN.0's TODO hygiene remains intact).
  - `CHANGELOG.md` (this entry).
- **Tests:** +43 (`tests/test_syn1a_region_ownership.py`). Adjacent regression sweep: `test_b1c_territory_constants_era_aware` (26) + `test_t2_wenc_wilderness_encounters` (28) + `test_cities_phase{1,2,3}` (185) + `test_security_resolver_runtime` (5) + `test_security_resolver_writer_merge` (6) + `test_wilderness_drop2` (52) + `test_todo_and_changelog_hygiene` (9) = 311 tests, all green.
- **What it shipped:**
  - **New schema** (idempotent, additive — no migrations required, both tables use `CREATE TABLE IF NOT EXISTS`):
    - `region_ownership` (region_slug PK, org_code, zone_id, claimed_by, claimed_at, maintenance) — one row per owned region; `region_slug` as PK enforces the one-owner-per-region invariant at the schema level. Indexed on `org_code` for the `get_org_regions` query.
    - `region_garrison` (region_slug + npc_id composite PK) — mapping table for cleanup on lapse/unclaim. Indexed on `region_slug`.
  - **New public surfaces** in `engine/territory.py`:
    - `claim_region(db, char, org_code, region_slug)` — full validation chain (org exists, rank ≥ `REGION_CLAIM_MIN_RANK=3`, region is a known wilderness region with landmark rooms, region not already owned, parent zone not `secured`, org has Foothold (≥50) influence in the parent zone, treasury covers `REGION_CLAIM_COST=5000`); on success, deducts treasury, inserts ownership row, bumps influence +20 (parity with legacy `claim_room`), spawns garrison.
    - `unclaim_region(db, char, org_code, region_slug)` — release flow; dismisses garrison; no partial refund (lapse path is in `tick_region_maintenance`).
    - `get_region_owner`, `get_org_regions`, `is_region_owned_by` — read surfaces.
    - `spawn_region_garrison(db, org_code, region_slug)` — spawns `REGION_GARRISON_COUNT=5` NPCs at random landmark rooms (multi-NPC-per-room allowed if region has fewer landmarks than 5). Idempotent: re-call returns existing npc_ids. Reuses `_GUARD_TEMPLATES` for org-flavored sheet/AI so the existing 9 org codes (CW + GCW) all work without new template data.
    - `dismiss_region_garrison(db, region_slug)` — deletes garrison NPC rows and mapping rows.
    - `tick_region_maintenance(db, session_mgr)` — weekly tick: full upkeep (`REGION_WEEKLY_MAINT=2000` + `REGION_GARRISON_WEEKLY=1000`) → garrison dismissal as cost-saving → lapse if base upkeep still unaffordable. Members notified at each transition.
    - `tick_region_passive_yield(db, session_mgr)` — daily tick: pays passive credits to owners (lawless 100–250, contested 50–150, secured 0) per design §2.5.1.
    - `_get_region_landmarks` / `_get_region_zone` — internal helpers; zone derived from any landmark's `rooms.zone_id` (wilderness loaders guarantee landmarks in a region share a parent zone).
  - **Constants:** `REGION_CLAIM_COST=5000`, `REGION_CLAIM_MIN_RANK=3`, `REGION_WEEKLY_MAINT=2000`, `REGION_GARRISON_WEEKLY=1000`, `REGION_GARRISON_COUNT=5`, `REGION_PASSIVE_LAWLESS_MIN/MAX=100/250`, `REGION_PASSIVE_CONTESTED_MIN/MAX=50/150`.
  - **Boot wiring:** `server/game_server.py`'s existing call to `ensure_territory_schema(self.db)` now transitively creates the new region tables — no boot-script change needed.
- **What it deliberately did not do (SYN.1.b scope):**
  - No call sites moved. The six known consumers of the legacy `is_room_claimed_by` (per SYN.0 Finding 2) still run against the room-keyed code path.
  - `parser/faction_commands.py::_cmd_claim` and `_cmd_unclaim` still call `claim_room` / `unclaim_room`.
  - `tools/syn_migration.py::wipe_territory_claims` is NOT invoked in this drop. The legacy `territory_claims` table still exists and is still writable.
  - No legacy surfaces deleted. No surfaces retired in `TODO.json::tech_debt`.
- **Handoff:** `HANDOFF_MAY24_SYN1a.md`.

---

## 2026-05-24 — BugFix5 + SYN.0 (combined drop)

- **Wave:** Bugfix block + SYN.0 (pre-flight + migration plan). One drop, two blocks. No engine code change in the SYN.0 block; only test fixes + tooling skeleton + docstring tags + tracker hygiene.
- **Files:**
  - `tests/smoke/scenarios/ground_combat.py` (modified — `_find_hostile_npc` filtered to `WHERE room_id IS NOT NULL ORDER BY id`).
  - `tests/smoke/scenarios/combat_extended.py` (modified — same fix; helper mirrors ground_combat).
  - `tests/test_t2_wenc_wilderness_encounters.py` (modified — three `asyncio.get_event_loop().run_until_complete(...)` calls replaced with `asyncio.run(...)` for Python 3.14 compatibility; class docstring annotated).
  - `parser/admin_fp_commands.py` (DELETED — orphan from the WoW.4 consolidation; `@fp` was folded into `@weight <name> fp <delta>` subform; the existing `test_admin_fp_module_removed` assertion fires correctly until this file is gone. Pre-apply step: `Remove-Item parser\admin_fp_commands.py` before applying the zip).
  - `engine/territory.py` (modified — docstring deprecation tags on `claim_room`, `unclaim_room`, `is_room_claimed_by` listing retirement drop + 6 known callers; tags on `CLAIM_MAX_PER_ZONE` / `CLAIM_MAX_TOTAL` block with SYN.0 correction note for the previously-misnamed `MAX_CLAIMS_PER_ZONE` / `MAX_CLAIMS_PER_ORG` entries in TODO.json).
  - `engine/security.py` (modified — docstring deprecation tag on `_apply_claim_upgrade` pointing at SYN.2 retirement).
  - `engine/player_cities.py` (modified — docstring deprecation tags on `found_city` (anchor chain steps 7-10 retarget in SYN.4) and `claim_room_for_city` (full retire in SYN.4 — expansion model goes away with the wilderness anchor pivot)).
  - `tools/syn_migration.py` (new — ~250 lines: audit phase + wipe `territory_claims` phase implemented; city-dissolution phase deferred to SYN.4 with full pseudocode; `tag_surface_retired` helper for SYN.N transitions; CLI with `--audit-only` / `--dry-run` / `--cold-start` modes).
  - `TODO.json` (modified — SYN.0 flipped `ready → DONE` with four pre-flight findings recorded; SYN.1 flipped `queued → ready`; `tech_debt::shipped_surfaces_retiring_in_SYN_sequence` corrected for two surface-name errors and amended with caller note for `is_room_claimed_by`).
  - `CHANGELOG.md` (this entry).
- **Tests:** No new tests authored; fixes are to existing failing tests. The five HEAD failures reproduce on Python 3.14 / Windows; after this drop they are green.
- **What it shipped — BugFix block:**
  - **Test pollution / Python 3.14 hostile-NPC discovery bug** (1 test, root cause of 2 — both `test_g2_combat_state_payload_emitted` and CX4's long-standing flake). `_find_hostile_npc` was returning the first row from an unordered `SELECT * FROM npcs WHERE hostile`; on Python 3.14 + Windows SQLite the first row was a `room_id=NULL` hostile NPC (hired-but-unassigned NPC or despawned entity), which crashed `int(row["room_id"])` with TypeError. Added `WHERE room_id IS NOT NULL ORDER BY id` for both correctness (NULL-room NPCs aren't valid ground-combat targets) and determinism (same NPC across all callers in a class-scoped harness).
  - **Python 3.14 asyncio API change** (3 tests, identical root cause). `asyncio.get_event_loop()` no longer implicitly creates an event loop on the main thread in 3.14. Replaced with `asyncio.run(...)` which creates and cleans up a fresh loop per call.
  - **WoW.4 leftover file** (1 test). `parser/admin_fp_commands.py` was supposed to be deleted as part of the WoW.4 consolidation that folded `@fp` into `@weight <name> fp <delta>`. The HEAD test `TestNoLeftoverAdminFpModule::test_admin_fp_module_removed` exists precisely to catch this leftover. Pre-apply step required: `Remove-Item parser\admin_fp_commands.py` before unzipping.
- **What it shipped — SYN.0 block:** Pre-flight verification + migration plan, no engine code change. Per `contestable_wilderness_design_v2.md` §5 and `HANDOFF_MAY24_DESIGN_LOCK_v2.md`. Deliverables:
  1. `tools/syn_migration.py` skeleton with audit phase, `wipe_territory_claims` phase, and `tag_surface_retired` helper. City-dissolution phase deferred to SYN.4 (where it ships atomically with the wilderness-anchor retarget) — full pseudocode present.
  2. Eight engine surfaces tagged with deprecation docstrings pointing at their SYN.N retirement: `claim_room`, `unclaim_room`, `is_room_claimed_by`, `CLAIM_MAX_PER_ZONE`, `CLAIM_MAX_TOTAL` (territory.py); `_apply_claim_upgrade` (security.py); `found_city`, `claim_room_for_city` (player_cities.py).
  3. TODO.json tech_debt list corrected:
     - `MAX_CLAIMS_PER_ZONE` → `CLAIM_MAX_PER_ZONE` (actual symbol at engine/territory.py:66).
     - `MAX_CLAIMS_PER_ORG` → `CLAIM_MAX_TOTAL` (actual symbol at engine/territory.py:67).
     - `expand_city` → `claim_room_for_city` (actual function at engine/player_cities.py:1178).
     - `is_room_claimed_by` action amended with the 6-caller list discovered in pre-flight.
  4. Four pre-flight findings recorded in TODO.json::SYN.0 for SYN.1+'s reference:
     - **Finding 1**: the surface-name corrections above.
     - **Finding 2**: `is_room_claimed_by` has 6 callers (the design doc named only 1). Six call sites listed by file:line.
     - **Finding 3**: `engine/player_cities.py::found_city` is NOT anchor-agnostic at HEAD; steps 7-10 of the validation chain all retarget in SYN.4.
     - **Finding 4**: `claim_room_for_city` (expand_city's actual name) retires entirely in SYN.4 — expansion model goes away.
- **Effort:** ~0.5 sess (1 sess in the original plan since BugFix5 is folded into SYN.0).
- **Drop discipline:** Pre-flight audit conducted before any code touched. Five failures inspected and root-caused (G2 was the proximate fail; CX4 was an instance of the same bug surfacing under a different scenario, not a separate bug). No phantom delivery: all eight tagged surfaces verified at HEAD; `register_admin_fp_commands` confirmed to have zero callers outside its own module + the test (via repo-wide grep).
- **Next:** SYN.1 (schema migration `territory_claims.room_id` → `wilderness_region_slug`; `claim_room` → `claim_region` etc.; 6 `is_room_claimed_by` callers retargeted/retired; ~30 tests; ~1 sess).
- **Handoff:** `HANDOFF_MAY24_BUGFIX5_SYN0.md`.

---

## 2026-05-24 — Design Lock: Contestable Wilderness v2

- **Wave:** Design lock event (not a code drop).
- **Files:**
  - `contestable_wilderness_design_v2.md` (new, ~1,460 lines) — the locked design.
  - `contestable_wilderness_design_v1.md` (May 24 morning draft, superseded by v2 — kept for historical reference).
  - `TODO.json` (modified — added SYN.0-SYN.10 to tier_2_queued with `lane: design_locked_pending_implementation` status; tagged ~13 deprecated surfaces with `deprecated_after_design_pivot_2026_05_24`; rebumped T2.WENC.b/c to "rolled into SYN.7-SYN.8").
  - `CHANGELOG.md` (this entry).
- **Tests:** No code shipped; no test delta.
- **What it shipped:** Locked the structural pivot for the wilderness layer. Key moves: city-map zones become permanently neutral commons; wilderness regions become contestable at the whole-region/one-owner granularity; player cities anchor in wilderness only; all regions launch un-owned with zero seeded influence (cold start); contest centrality is *hybrid* (visible to all, mechanically optional); 7-day contest resolves via Albion-style culminating fight at a contested landmark with influence-scaled Anchor HP; daily yields are partial-passive-plus-active-harvest with 15% non-owner tax. Additionally specified: wilderness-only T5 crafting materials gating endgame crafting; full wilderness anomaly system Tier 1-2 (corvette boardings, scout patrols, salvage caches) and Tier 3 (krayt dragon, Maze Predator Apex, Crashed Capital Ship, Lost Patrol world-bosses); city vitality (SWG lesson — citizens needed to maintain rank); player-constructed buildings inside cities (residence, crafting station, commerce stall, garrison annex, cultural hall categories). All informed by four-MMO competitive review (EVE, Albion, SWG, Foxhole + Eco + RotMG); inspiration trace in §9.
- **Implementation path:** SYN.0 (pre-flight + migration plan) → SYN.10 (display polish). Eleven drops, ~14.5 sessions estimated.
- **Q-locks resolved May 24 2026:** Path B (pivot to wilderness-aware-security first), whole-region granularity, espionage-as-influence shipped in SYN.5; retire-per-room-claims, cities-wilderness-only, zero-seeded cold start; hybrid contest centrality, Albion-style culminating fight, partial-passive-plus-active-harvest. All eight design questions answered explicitly by Brian.
- **Deprecation discipline:** Per Pattern-2 hygiene, ~13 shipped surfaces (claim_room, unclaim_room, _apply_claim_upgrade, MAX_CLAIMS_PER_ZONE, MAX_CLAIMS_PER_ORG, Drop 6D room-keyed contest state, city-map city-validation, etc.) tagged in TODO.json as `deprecated_after_design_pivot_2026_05_24`. Each retires in its corresponding SYN drop with status transition to `retired_in_SYN.N_2026_MM_DD`.
- **Locking statement:** Drift between design and implementation is a Phantom-1 (silent under-shipping) or Phantom-2 (silent over-shipping) violation requiring same-drop remediation. The design is the source of truth; the SYN sequence is the implementation; TODO.json + CHANGELOG.md are the running ledger; architecture v49 rolls up after SYN sequence completes.
- **Handoff:** No handoff (no code drop). Next session begins at SYN.0.

---

## 2026-05-24 — T2.WENC.a Wilderness encounter system + hazard tick wilderness path

- **Wave:** T2.WENC drop 1 (selector + cooldown + filters + integration hook + content + hazard tick path). NPC spawn / vendor dispatch / weather effects deferred to T2.WENC.b per minimal-substrate-first discipline (same pattern T2.3 shipped under).
- **Files:**
  - `engine/wilderness_encounters.py` (new — ~330 lines: `EncounterEntry`, `EncounterPool`, `EncounterRollResult` dataclasses; `roll_encounter()` selector with 60s per-character in-memory cooldown per design §5.4; `parse_encounter_pool()` for the loader; `evaluate_faction_gate()` stub returning True until Director-AI wiring lands as T2.WENC.c).
  - `engine/wilderness_loader.py` (modified — added `encounter_pool` field to `WildernessRegion` dataclass; parses `encounters:` YAML block via `parse_encounter_pool`; docstring updated to remove "Encounter pool resolution" from the deferred list).
  - `engine/hazards.py` (modified — `hazard_tick()` extended with wilderness path; new `_check_wilderness_hazard()` looks up the character's terrain `ambient_hazard`/`hazard_severity` and runs `check_hazard_for_character` against a synthetic room dict; aspirational hazard tags (terrain hazards not in HAZARD_TYPES) are inert without erroring; wilderness pseudo-room-id is negative to avoid colliding with `rooms.id`).
  - `parser/builtin_commands.py` (modified — `_execute_wilderness_move` fires `roll_encounter` after the arrival broadcast and before the auto-look; encounter narrative surfaced as `[ENCOUNTER]` line; encounter failures never sink a move).
  - `data/worlds/clone_wars/wilderness/dune_sea.yaml` (modified — 9-entry encounter pool authored: tusken_scout_party, tusken_war_party, dewback_herd, lone_jawa_scavenger, moisture_farmer_speeder, jawa_sandcrawler_stop, crashed_speeder_wreck, abandoned_moisture_vaporator, sandstorm_approaching; covers all 5 design §5.2 types; `base_chance_per_move: 0.04`).
  - `data/worlds/clone_wars/wilderness/coruscant_underworld.yaml` (modified — 10-entry encounter pool authored: gang_patrol, maze_ambush, ranza_pack, cleaner_droid_remnant, refugee_huddle, lone_information_broker, black_market_pop_up, crashed_speeder_drop, abandoned_tech_cache, ventilation_failure; covers all 5 design §5.2 types; `base_chance_per_move: 0.05`).
  - `tests/test_t2_wenc_wilderness_encounters.py` (new — 28 tests across 12 classes: schema parse, no-op for missing block, unknown type/duplicate-id/clamped-chance/unknown-terrain warning, regions-without-encounters silent, chance gate, terrain/distance/faction-gate filters, weighted pick, per-character cooldown, no-eligible-entries doesn't burn cooldown, wilderness hazard tick path with known/aspirational/zero-severity cases, production Dune Sea and Coruscant pool sanity-check, region attr presence, missing/None pool robustness).
- **Tests:** +28 new; 235/235 in the wilderness + village regression sweep (test_wilderness_drop2, test_wilderness_drop2_phase2, test_t2_3_coruscant_underworld, test_f5_wilderness_integration, test_f7d_village_choice) all green after the change. Dune Sea minimal sweep 28/28 green. AST, YAML, JSON validated.
- **What it shipped:** Wilderness movement now rolls for encounters on each successful in-tile move. The roll honors a 60s per-character cooldown, filters the region's encounter pool by terrain + minimum distance from edge + faction gate, weighted-picks from what remains, and surfaces the chosen entry's narrative line. Regions without an `encounters:` block no-op silently — minimal-substrate regions don't need updating. Independently, the hazard tick now walks a second path for wilderness-resident characters: it looks up the terrain at their coordinates, reads the terrain's `ambient_hazard`/`hazard_severity`, and runs the existing hazard check against a synthetic room dict. `extreme_heat` (Dune Sea) is now a live hazard in wilderness; Coruscant's `structural_collapse`/`stale_air`/`lethal_environment` tags are aspirational (no matching HAZARD_TYPE yet) and stored-but-inert until content authoring brings those hazard types online. The negative pseudo-room-id keeps wilderness cooldowns separate from real-room cooldowns in the `_hazard_timers` dict.
- **Design decisions locked:**
  - **Minimal-substrate-first ship.** Encounter fires as a narrative broadcast only; NPC spawn / vendor caravan / weather effects deferred to T2.WENC.b. Same pattern that brought the wilderness regions online in T2.3. The `EncounterEntry.payload` dict already carries the dispatch hints (`npc_template`, `vendor_template`, `salvage_table`, `effect`) so T2.WENC.b is purely consumer-side work — the contract is locked.
  - **Faction gate as seam, not consumer.** `evaluate_faction_gate()` always returns True for now. The seam is shipped so the selector path doesn't change when Director-AI wiring lands as T2.WENC.c. Gate strings are stored on every authored entry (`tusken_pressure_high`, `underworld_gang_pressure_default`, etc.) so the wiring drop just replaces the stub.
  - **No-eligible-entries doesn't burn cooldown.** Per design §5.1 silence is fine, but a player exploring an edge tile with a thin pool shouldn't pay the cooldown for it. Cooldown is set only when an encounter actually fires.
  - **Aspirational hazard tags are inert, not errors.** Coruscant's `structural_collapse`/`stale_air`/`lethal_environment` ship as content placeholders. The hazard tick logs them at debug and skips — bringing them online is a content drop authoring matching HAZARD_TYPES entries, not an engine change.
  - **Negative pseudo-room-id for wilderness cooldowns.** `rooms.id` is always positive; negative ids keep wilderness hazard cooldowns separate from real-room cooldowns in the shared `_hazard_timers` dict without a schema change.
  - **Per-region cooldown granularity.** All tiles inside a region share the same cooldown key (`_wilderness_pseudo_room_id(slug)`) so a hazard fires every 5 minutes at the region level, not every tile. Tile-by-tile cooldown reset would defeat the design's hazard pacing.
- **TODO updates:** T2.WENC marked `partly_done` with explicit subitem breakdown (T2.WENC.a DONE this drop; T2.WENC.b ready for next session — encounter type dispatch; T2.WENC.c ready — Director-AI faction-gate wiring). Added T2.WENC.a to `design_calls_resolved_recent`. Added P2.a "TODO drift" sub-pattern to phantom catalog per the May 24 combined drop's note. Added `tracker_update_in_same_drop` and `minimal_substrate_first` to `named_disciplines_quick_ref`.
- **Handoff:** HANDOFF_MAY24_T2WENCa.md

---

## 2026-05-24 — T2.3 Coruscant Underworld + W.3 landmark_includes + T1.1/T1.2/T2.12 design calls closed

- **Wave:** Combined drop. T2.3 (Coruscant Underworld wilderness
  build) plus W.3 (loader generic landmark_includes mechanism).
  Four Tier-1/Tier-2 design calls closed: T1.1, T1.2, T2.3, T2.12.
- **Files:** `engine/wilderness_loader.py` (modified — generic
  `landmark_includes:` mechanism with region filter and enrichment
  semantics; legacy `force_resonant_path` parameter preserved for
  backward compat), `data/worlds/clone_wars/wilderness/coruscant_underworld.yaml`
  (new — region YAML, 40×40 single-level grid, 5 terrain pools, 1
  edge, 2 landmark_includes), `data/worlds/clone_wars/wilderness/coruscant_underworld_landmarks.yaml`
  (modified — added coordinates to 3 transit nodes per collapsed-Z-axis
  decision), `data/worlds/clone_wars/wilderness/dune_sea.yaml`
  (modified — migrated to `landmark_includes:` for parity),
  `data/worlds/clone_wars/era.yaml` (modified — added Coruscant
  Underworld to `content_refs.wilderness`),
  `tests/test_t2_3_coruscant_underworld.py` (new — 24 tests)
- **Tests:** +24 new, 153 existing wilderness tests still green;
  177/177 in wilderness sweep, 86 more in village-adjacent sweep.
- **What it shipped:** Coruscant Underworld now loads as a single-
  level wilderness region with minimal-substrate parity to Dune Sea.
  5 named landmarks + 3 transit nodes pulled in via region-filtered
  includes from `coruscant_underworld_landmarks.yaml` and
  `force_resonant_landmarks.yaml`. Dune Sea reconciled with the same
  mechanism. Loader's `landmark_includes:` supports multiple files
  per region, region filtering, and enrichment semantics
  (within-source dup-id still errors; cross-source dup-id enriches).
- **Design calls resolved (2026-05-24):**
  - **T1.1** Eavesdrop target_char model → resolved_deferred. No
    code change. Pre-flight Pattern-2 finding: substrate is shipped;
    the narrow forward-compat note at
    parser/espionage_commands.py:199-207 is the standing trigger-
    to-fix for any future wilderness-tile-to-wilderness-tile
    eavesdropping. Carried since v45.
  - **T1.2** skill_check_passed trigger-site → DONE (already
    shipped 2026-05-20). Pre-flight Pattern-2 finding: Option 2
    (`chain attempt` command) shipped four days ago; the docstring
    in `engine/chain_events.py` documents the resolution. TODO.json
    was carrying it as pending. Now correctly tracked.
  - **T2.3** Coruscant scope → ship single-level (Z-axis collapsed),
    minimal-substrate parity with Dune Sea, encounter system in
    a separate follow-up wave covering both regions.
  - **T2.12** Knighting trials launch-scope → Master-fiat
    (`+knight` + `+endorse trials`) is the launch posture.
    Mechanical 5 Trials deferred post-launch; Trial of Spirit
    additionally blocked on T3.15 Director AI CW-tuning.
- **TODO updates:** T1.1 marked resolved_deferred; T1.2 marked
  DONE with the May-20 already-shipped resolution captured; T2.3
  marked DONE; T2.12 marked deferred_low_priority with the
  5-trial breakdown for future reference; T2.WENC added as new
  Tier 2 item slotted after the cleared Tier 1.
- **Pattern catalog notes:** Two Pattern-2 (Phantom-undelivered)
  hits this drop — T1.1 and T1.2 were both shipped at HEAD but
  tracked as pending. This is the same failure mode that caught
  PG.3 in v48's audit, T2.10.a in the SRB.1.b drop, and now T1.1
  + T1.2. The userMemories/TODO.json drift between session waves
  is the root cause; the pre-flight grep-first discipline keeps
  catching it.
- **Tech debt added:** TD.2 (surface_manhole_room_duplication) —
  two rooms exist at coordinates (20, 17) representing the same
  gameplay handoff point. Documented + lock-in test in place; small
  follow-up drop will reconcile.
- **Handoff:** `HANDOFF_MAY24_COMBINED.md`

---

## 2026-05-24 — SRB.1.b — stim consumption wired to attributes.consumables

- **Wave:** SRB.1 follow-ups (T2.10.b)
- **Files:** `engine/buffs.py` (modified — added consumable
  helpers), `parser/medical_commands.py` (modified — offer-time
  gate + attempt-time consumption + substrate-decision docstring
  rewrite), `tests/test_srb1_medic_stim.py` (modified — extended
  `_make_char()` with `consumables=` kwarg, seeded 8 broken
  fixtures with `_TYPICAL_MEDIC_KIT`),
  `tests/test_srb1b_stim_consumable_wiring.py` (new — 19 tests)
- **Tests:** +19 new, 8 fixtures updated; 228/228 green across
  SRB family (40 stim + 14 schematic + 19 new + 100 SRB.2/3 +
  55 adjacent buff/craft)
- **What it shipped:** Medics now need stims in their kit
  (`attributes.consumables[<key>]`) to administer them. Offer-time
  gate fires after the skill check ("do I know how → do I have
  the kit"); attempt-time consumption fires in `_execute_stim_roll`
  on success/failure/fumble per design §3.5 ("target wastes the
  stim, no benefit" on failure). Crafting writes to the same
  storage model. New `engine.buffs.has_consumable()` /
  `get_consumable_count()` / `consume_consumable()` helpers.
- **Tech debt added:** TD.1 (consumable_storage_unification) —
  see TODO.json. Two parallel consumable-storage models
  (attributes.consumables vs inventory.items+consumable:true);
  this drop accepts the bifurcation and ships in the
  attributes.consumables model where crafting already writes.
- **Closed:** T2.10.a (was already done at HEAD; pre-flight
  caught the phantom-undelivered status), T2.10.b
- **Handoff:** `HANDOFF_MAY24_SRB1B.md`

---

## 2026-05-24 — TODO.json + CHANGELOG.md seeded

- **Wave:** Tooling
- **Files:** `TODO.json`, `CHANGELOG.md` (both new)
- **Tests:** 0 (content-only drop)
- **What it shipped:** Machine-readable companion files to
  augment the architecture doc. `TODO.json` mirrors arch v48
  §3.2 priority ranking + §8 outstanding decisions in a
  greppable form. `CHANGELOG.md` reverse-chronological drop
  ledger. Both updated at end of every drop going forward.
- **Handoff:** (this drop)

---

## 2026-05-24 — WoW MVP complete (six drops)

This is the May 24 Weight of War launch wave. Six drops in
sequence; WoW launch-MVP acceptance criteria per
`weight_of_war_design_v1.md` §14 all met.

### 2026-05-24 — WoW.4 + @fp consolidation
- **Wave:** May 24 WoW MVP
- **Files:** `parser/padawan_master_commands.py` (modified),
  `parser/admin_weight_commands.py` (modified),
  `parser/admin_fp_commands.py` (DELETED via pre-apply step),
  `server/game_server.py` (modified),
  `tests/test_wow3c_dsp_fp_wiring.py` (rewritten),
  `tests/test_wow4_bond_weight_sense.py` (new)
- **Tests:** +13 new, 13 rewritten (net +11); 391/391 green
  across all WoW + force-power + combat + padawan-master suites
- **What it shipped:** Bond-based Weight sensing through
  `+master` / `+padawan` (no new `+forcebond` command per
  extend-don't-add discipline). `@fp` admin command retired
  and folded into `@weight ... fp <delta>` subform. WoW MVP
  launch complete.
- **Handoff:** `HANDOFF_MAY24_WOW4.md`
- **New standing principle:** "Extend, don't add" - established
  by this retrospective; arch v49 should add to §4 invariants.

### 2026-05-24 — WoW.3c DSP/FP wiring
- **Wave:** May 24 WoW MVP
- **Files:** `parser/admin_fp_commands.py` (new — superseded by
  WoW.4), 2 signature extensions, 2 parser wirings
- **Tests:** +29 (later rewritten in WoW.4 to 27)
- **What it shipped:** DSP-resistance modifier, extra DSP at
  high Weight, FP-award reduction via §7.2 multiplier, Knighting
  FP grant. `@fp` admin command (later consolidated into
  `@weight`).

### 2026-05-24 — WoW.3b passive decay and duel gating
- **Wave:** May 24 WoW MVP
- **Files:** 1 substrate function + tick + 2 parser gates
- **Tests:** +22
- **What it shipped:** Passive Weight decay tick; duel
  participation gated by Weight tier.

### 2026-05-24 — WoW.3a combat hooks
- **Wave:** May 24 WoW MVP
- **Files:** 1 new module, 2 parser insertions
- **Tests:** +19
- **What it shipped:** Combat-driven Weight accumulation hooks.

### 2026-05-24 — Phase 7c phantom fix
- **Wave:** May 24 WoW MVP
- **Files:** (Pattern 1 fix - phantom-delivered retirement)
- **Tests:** +0
- **What it shipped:** Closed one Pattern 1 phantom carried
  from Cities Phase 7c.

(WoW.1, WoW.2a/b/c shipped earlier waves — see arch v47/v48
§1.4 for those.)

---

## 2026-05-23 — Player Cities v1.2 close-out (seven drops)

The May 23 wave closed the largest Tier 2 engine item from v47.
Cumulative: 240 new tests, all green. Player Cities v1.2 is
feature-complete per `player_cities_design_v1_2.md` §1-11.
Cities engine + parser sums to 6,290 LOC. 553 cities tests
across 13 files at HEAD.

### 2026-05-23 — Cities Phase 7c — combat-round triggers
- **Files:** `engine/combat.py`, `engine/city_guard_runtime.py`,
  `parser/combat_commands.py`
- **Tests:** +29
- **What it shipped:** Attacked-citizen and bountied-target
  combat round triggers.

### 2026-05-23 — Cities Phase 6 web UI
- **Files:** `server/session.py`, `static/client.html`
- **Tests:** +10
- **What it shipped:** Sidebar + modal + Mayor/admin buttons.
  First instance of two-stage confirm pattern for destructive
  actions (reusable - see arch §4.21).

### 2026-05-23 — Cities Phase 7b runtime
- **Files:** `engine/city_guard_runtime.py`,
  `engine/player_cities.py`, `parser/builtin_commands.py`
- **Tests:** +33
- **What it shipped:** Banished-entry trigger, on-entry filter.

### 2026-05-23 — Cities Phase 7 NPC guards
- **Files:** `engine/player_cities.py`, `parser/city_commands.py`
- **Tests:** +44
- **What it shipped:** NPC guards (slots, assignment, basic
  combat hooks).

### 2026-05-23 — Cities Phase 6 help topics
- **Files:** `data/help/commands/+city.md`,
  `data/help/commands/@city.md`, `data/help/topics/cities.md`
- **Tests:** +33
- **What it shipped:** Phase 6 help docs.

### 2026-05-23 — Cities silent-except remediation
- **Files:** `engine/death.py`, `engine/player_cities.py`,
  `parser/builtin_commands.py`,
  `parser/padawan_master_training_commands.py`,
  `parser/pc_bounty_commands.py`
- **Tests:** +32 (existing test_session38.py stayed green;
  remediation cleared sandbox-failure mode)
- **What it shipped:** `except Exception: pass` remediation
  at 6 sites - added logging where there had been silent
  passes.

### 2026-05-23 — Cities Phase 6 weekly maintenance
- **Files:** `engine/player_cities.py`,
  `server/tick_handlers_economy.py`, `server/game_server.py`
- **Tests:** +59
- **What it shipped:** Weekly maintenance + 4-week grace state
  machine.

---

## 2026-05-22 — Wave 1 carry-over (four drops)

v47 listed these but they were applied to Windows between v47's
draft and v48's consolidation.

### 2026-05-22 — SRB.3 Combined-action
- **Files:** `engine/combined_actions.py`,
  `parser/lead_commands.py`, `lead_bonus` / `auto_consume_lead`
  kwargs
- **Tests:** +53
- **What it shipped:** `+lead` / `+joinlead` + consume-on-
  skill-check.

### 2026-05-22 — SRB.2 Entertainer morale aura
- **Files:** schema v32 `morale_auras` + fatigue cols, 8 DB
  helpers, `perform_morale_aware_check`, PerformCommand aura
  write, LookCommand surfacing, MoveCommand departure clear,
  `morale_aura_expiry_tick`
- **Tests:** +47

### 2026-05-22 — PG2.PL post-launch consumers
- **Files:** `engine/mail_utils.send_system_mail`, stipend
  interceptor in `engine/organizations.py`, BH-payout mail in
  `engine/death.py`
- **Tests:** +12

### 2026-05-22 — PM.3 training events
- **Files:** `parser/padawan_master_training_commands.py`
  (`+teach`, `+learn`, `+spar`), schema v34 `training_log` table
- **Tests:** +39

---

## Pre-2026-05-22 — see architecture doc

For drops prior to the May 22 wave, see
`sw_d6_mush_architecture_v48.md` §1.4 (and earlier revisions'
equivalent sections). This changelog began life on 2026-05-24
and is not retroactively populated past the May 22 wave.

The pre-existing baseline of recently-shipped systems (as of
arch v48 consolidation):
- Player Cities v1.2 - May 23 (above)
- PM.3 training events - May 22 (above)
- PG2.PL post-launch consumers - May 22 (above)
- SRB.2 Entertainer morale aura - May 22 (above)
- SRB.3 Combined-action - May 22 (above)
- PG.3 Force progression gates (pre-v47; v48 corrected v47's
  omission) - predisposition scoring, play-time accumulation,
  force-sign trigger seam, village-quest cooldowns, STEP_FORCE
  chargen removal. 101 tests.
- Drop 6D Territory contestation - verified pre-v47
- +pvp opt-in (schema v27) - May era earlier
- S-RES + S-RES.2 security defaults - May era earlier
- Q1.3 Falleen Syndicate Tower - May era earlier
- active_era CW pivot - May 18 2026
- PVF-5 schema-seed-collision fix
- F.7.j-m Jedi village quest chain
- F.8.c.2.a 20 chain-anchor NPCs

For dates and detail on these, see arch v48 §1.4 and §3.3.
