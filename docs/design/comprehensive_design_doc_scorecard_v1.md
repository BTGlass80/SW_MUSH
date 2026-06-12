# SW_MUSH — Comprehensive Design Doc Scorecard v1

**Generated:** April 24, 2026 · Symbol-level audit against `SW_MUSH__84_.zip`
**Supersedes:** `design_doc_implementation_status_v1.md` (overshallow) and `design_doc_audit_closeout_v2.md` (incomplete)
**Companion to:** `economy_audit_implementation_scorecard_v1.md`, `economy_bulk_premium_design_v1.md`

**Reason for this v1:** Brian flagged on April 24, 2026 that the previous audit "still seems light." He was right. The original audit treated each design document as a single checkbox, hiding the fact that **six of those documents are consolidated multi-design specs containing 4–23 individually-trackable items each**. Plus four historical design docs referenced by older architecture versions but no longer in `/mnt/project` were entirely absent from the audit. This document closes those gaps.

---

## Headline Numbers

| Layer | Count | Notes |
|---|---|---|
| Outer design docs in `/mnt/project` (md + pdf) | **41** | Up from the v1 audit's 38 by adding the three identified earlier (#39 sourcebook mining, #40 NPC traffic, #41 web UX competitive) |
| Review/audit docs containing implementation backlogs | **+4** | `economy_audit_v1.md`, `architecture_status_post_review.md`, `code_review_session32.md`, `opus_code_review_session4.md` |
| Historical design docs referenced by older architecture (v16/19/20/21) but no longer in `/mnt/project` | **+4** | `space_expansion_v2_design.md`, `space_expansion_v2_addendum.md`, `combat_ux_overhaul_design.md`, `capital_ship_rules_design.md` — all delivered, retired from project knowledge |
| **Total documents tracked** | **49** | |
| **Trackable design items inside the multi-design docs** | **~85** | See Part 2 |
| Top-level ❌ items (multi-design docs treated as monolithic in v1) | **6 docs** | Now correctly counted as ~13 sub-items below |
| Top-level ❌ when fully decomposed | **~18 sub-items** across all documents | See Part 5 |

---

## Part 1 — Documents Tracked

### 1A. Original 38 design docs (audit v1)

Disposition unchanged from v1 audit. See `design_doc_implementation_status_v1.md` for original entries. Six of them turn out to be multi-design specs needing decomposition (see Part 2).

### 1B. Three design docs missed by audit v1 (closeout v1 added)

- **#39 `sourcebook_mining_crafting_exp_design_v1.md`** — ✅ DELIVERED (3 drops: world lore expansion, crafting experimentation engine, Imperial NPC templates)
- **#40 `npc_space_traffic_design_v2.pdf`** — ✅ DELIVERED (1,668 lines in `engine/npc_space_traffic.py`; all 5 archetypes, 7 states, manager class, tick integration)
- **#41 `web_ux_competitive_analysis.md`** — 🟡 PARTIAL (6 of 8 priorities; gaps: P1 client-side mode rotation, P6 onboarding overlay)

### 1C. Four review/audit docs containing implementation backlogs (closeout v2 reclassification)

- **#42 `economy_audit_v1.md`** — 18-item backlog. **8 ✅ / 3 🟡 / 6 ❌ / 1 🟦**. See `economy_audit_implementation_scorecard_v1.md` for per-item evidence.
- **#43 `architecture_status_post_review.md`** — 4 standing items. C4 god-object refactoring **regressed**; ANSI cleanup, input limits, notification center pending.
- **#44 `code_review_session32.md`** — A/B mostly ✅; C4/D2/D6 still pending (overlap with #43).
- **#45 `opus_code_review_session4.md`** — 6 numbered bugs; **Bug #6 (Director faction code mismatch) confirmed in this audit** — `VALID_FACTION_CODES` has only 4 of 6 factions (`empire/rebel/hutt/bh_guild`), missing Traders' Guild and Underworld.

### 1D. Four historical design docs no longer in `/mnt/project` (this v1's new finding)

These are referenced by architecture v16/v19/v20/v21 but absent from `/mnt/project` and the code drop's `sw_d6_mush_architecture_v29.md`. Each was apparently retired from project knowledge after delivery. All four are confirmed delivered in current code:

- **#46 `space_expansion_v2_design.md`** — ✅ DELIVERED. 19 drops covering galaxy expansion, hyperspace, sublight nav, asteroid fields, anomaly scanning, salvage, space HUD server/client, smuggling routes, ship customization, components, missions, power allocation, captain's orders, planetary trade, transponder codes, ship quirks. All ticked off in v29 §6.1.
- **#47 `space_expansion_v2_addendum.md`** — ✅ DELIVERED. Phases 10–14 (power allocation, captain's orders, planetary trade goods, transponder codes, ship quirks/log). Same v29 §6.1 coverage.
- **#48 `combat_ux_overhaul_design.md`** — ✅ DELIVERED. 7 drops: staggered combat output, visual hierarchy, initiative noise reduction, combat web panel. v21 §16 lists it as completed.
- **#49 `capital_ship_rules_design.md`** — ✅ DELIVERED. 5 drops: structure points, multiple fire arcs, capital-scale weapon templates. v20 §12, v21 §15, v31 §15 all confirm "DELIVERED — Pre-existing."

These four are properly accounted for in the live code; they just lack project-knowledge presence. Recommend re-uploading them or archiving the references in v32 §25.

---

## Part 2 — The Six Multi-Design Documents Hiding Sub-Backlogs

The previous audit treated each of these as one row. They're each containers for many design items. Here is each broken down with current implementation status.

### #7 `competitive_analysis_feature_designs_v1.md` — 11 sub-designs (A through K)

The doc contains **eleven** named designs. Previous audit had this as a single "🟡 Partial" row.

| Sub-design | Topic | Current state | Status |
|---|---|---|---|
| A | Consensual Permadeath System | `mux_commands.py:635` has "permadeath" as a permaflag option; no `engine/permadeath.py`, no permadeath duels, no AI review system | **❌ Not implemented** |
| B | Think Command & Internal Monologue | `parser/builtin_commands.py:2326` `class ThinkCommand` with `key = "think"` | ✅ Delivered |
| C | World Lore System (Lorebook Pattern) | `engine/world_lore.py:284` `SEED_ENTRIES` (64 entries) | ✅ Delivered |
| D | Narrative Tone Per Zone | `engine/zone_tones.py`; injected into Director digest at `director.py:756-761` | ✅ Delivered |
| E | Environmental Hazards | `engine/hazards.py:32` `HAZARD_TYPES`; consumed by `espionage.py:273` | ✅ Delivered |
| F | Espionage Command Suite | `parser/espionage_commands.py` — `ScanCommand`/`assess`, `EavesdropCommand`, `InvestigateCommand`, `IntelCommand`/`+intel`, `InterceptCommand` | ✅ Delivered |
| G | Achievement System | `engine/achievements.py:122` `check_achievement` | ✅ Delivered |
| H | Buff/Debuff Handler | `engine/buffs.py:34` `class Buff` | ✅ Delivered |
| I | Safe Trade Command | `parser/builtin_commands.py:2610` `key = "trade"` | ✅ Delivered |
| J | RP Preferences | `parser/mux_commands.py:645` `class RpPrefsCommand` | ✅ Delivered |
| K | Centralized Cooldown Handler | `engine/cooldowns.py:76` `check_cooldown`, `set_cooldown`, `remaining_cooldown` | ✅ Delivered |

**Decomposed status:** 10 ✅ / 1 ❌. Permadeath (A) is the only outstanding item — and it's a major ~12–16 hour feature with schema changes, not a small one.

### #38 `competitive_analysis_feature_mining_v1.md` — 23 numbered features across 4 tiers

The doc's §4 prioritizes 23 features. Previous audit had this as ✅ Delivered.

| # | Feature | Tier | Current state | Status |
|---|---|---|---|---|
| 1 | `think` command | 1 | (Design B above) | ✅ |
| 2 | Narrative tone per zone | 1 | (Design D above) | ✅ |
| 3 | Centralized cooldown handler | 1 | (Design K above) | ✅ |
| 4 | RP preferences on `+finger` | 1 | (Design J above) | ✅ |
| 5 | Scar system | 1 | `grep -rn "scars\":\|class.*Scar" engine/` returns 0 hits | **❌ Not implemented** |
| 6 | `trade` command | 1 | (Design I above) | ✅ |
| 7 | World Lore table | 2 | (Design C above) | ✅ |
| 8 | Environmental hazards | 2 | (Design E above) | ✅ |
| 9 | Room state descriptions | 2 | `engine/room_states.py` exists; `set_zone_state` called from `director.py:880` | ✅ |
| 10 | Espionage commands | 2 | (Design F above) | ✅ |
| 11 | Achievement system | 2 | (Design G above) | ✅ |
| 12 | Crafting experimentation | 2 | `engine/crafting.py` `DEFAULT_EXPERIMENT_PARAMS`, `resolve_experiment_result` | ✅ |
| 13 | Buff/debuff handler | 2 | (Design H above) | ✅ |
| 14 | Scene logging + web archive | 3 | `parser/scene_commands.py:138` `_show_scene_log` | ✅ (verify web archive) |
| 15 | Director era-progression thresholds | 3 | `grep -rn "era_progression\|era_threshold\|ERA_THRESHOLD"` returns 0 hits | **❌ Not implemented** |
| 16 | Sleeping character vulnerability | 3 | `engine/sleeping.py` exists with explicit "Tier 3 Feature #16" comment | ✅ |
| 17 | Layered equipment descriptions | 3 | `grep -rn "layered_desc\|equipment_layer"` returns 0 hits | **❌ Not implemented** |
| 18 | Survival crafting lane | 3 | `engine/crafting.py:166 "survival_gear"`; `data/schematics.yaml:416,433` | ✅ |
| 19 | Comlink intercept | 3 | `parser/espionage_commands.py:507` `InterceptCommand` | ✅ |
| 20 | Web-based character creation | 3 | `static/chargen.html` (1,830 lines) | ✅ |
| 21 | Procedural wilderness zones | 4 | Promoted to its own design doc — `wilderness_system_design_v1.md` (❌ in audit) | tracked separately |
| 22 | Hacking/slicing minigame | 4 | No minigame implementation | **❌ Not implemented** |
| 23 | Player-run government/senate | 4 | No senate system | **❌ Not implemented** (Tier 4 — explicitly future) |

**Decomposed status:** 18 ✅ / 5 ❌. The 5 ❌: scar (#5), era thresholds (#15), layered desc (#17), hacking minigame (#22), senate (#23). Tier 4 items #22 and #23 were explicitly "Future Consideration" — not really backlog. Genuine in-flight gaps: 3 (#5, #15, #17).

### #28 `gemini_critique_response_design_v1.md` — 4 issues + additional findings

| Issue | Topic | Current state | Status |
|---|---|---|---|
| 1 | Tick loop isolation (per-system tasks) | `server/tick_scheduler.py` (110 lines), `tick_handlers_economy.py`, `tick_handlers_ships.py`; integrated in `game_server.py:198` | ✅ |
| 2 | AI inference queueing (Ollama serialization) | Only `ai/claude_provider.py:72` `asyncio.Lock()` exists; no Ollama-side queue | 🟡 Partial — Claude has lock; Ollama doesn't |
| 3 | Database migration strategy | `db/database.py:21` `schema_version` table, `db/database.py:228` `MIGRATIONS` dict | ✅ |
| 4 | Roadmap sequencing | Process change, not code | ✅ (advisory accepted) |
| Additional | NPC death cleanup | `engine/combat.py:1429,1453` handles `WoundLevel.DEAD` cleanup | ✅ |

**Decomposed status:** 4 ✅ / 1 🟡. Issue 2 (Ollama queue) is the partial — overlaps with #29 below.

### #29 `ollama_idle_queue_design_v1.md` — was incorrectly marked ✅ in v1 audit

The design doc specifies an `OllamaIdleQueue` class that runs background AI tasks during idle periods. Symbol verification:

- `find . -name "ollama*.py"` returns no Python module
- `grep -rn "asyncio.Queue\|inference_queue\|class.*OllamaIdleQueue" ai/ engine/` returns zero hits
- The only async-lock pattern in `ai/` is `claude_provider.py:72 self._lock = asyncio.Lock()` (different concept — single-flight, not idle queue)

**Status correction:** Was ✅ in v1 audit. Should be **❌ Not implemented**. This is the single most consequential miss in the v1 audit.

### #16 `organizations_factions_design_v1.md` — 6 factions + 6 guilds + 5 phases

Previous audit had this as ✅ Delivered.

| Item | Current state | Status |
|---|---|---|
| 6-faction roster (Rebel, Empire, Hutt, BH Guild, Traders Guild, Underworld) | `engine/director.py:949` `VALID_FACTION_CODES = frozenset({"empire", "rebel", "hutt", "bh_guild"})` — **4 of 6 only** | 🟡 Partial |
| Director AI faction management | Director has faction order processing (lines 956–967) | ✅ for the 4 wired factions |
| `engine/organizations.py` exists | Yes, file present | ✅ |
| Guild system | No `data/guilds.yaml`, no `engine/guilds.py` found | ⚠️ Needs deeper verification |
| 5 implementation phases | Not individually tracked here — assume mostly delivered given org system is live | ⚠️ Needs phase-level scorecard |

**Status correction:** Was ✅ in v1 audit. Should be **🟡 PARTIAL** until faction roster is completed and guild system verified. This is also the same as `opus_code_review_session4.md` Bug #6 (Director faction code mismatch) — confirming that bug is real.

### Summary of decomposed multi-design totals

| Doc | Sub-items | ✅ | 🟡 | ❌ | Net |
|---|---|---|---|---|---|
| #7 feature_designs (A–K) | 11 | 10 | 0 | 1 | mostly done |
| #38 feature_mining (1–23) | 23 | 18 | 0 | 5 | 3 genuine gaps + 2 Tier 4 |
| #28 gemini_critique (4+) | 5 | 4 | 1 | 0 | minor gap |
| #29 ollama_idle_queue | 1 (whole doc) | 0 | 0 | 1 | full miss |
| #16 organizations_factions | ~6 visible | ~3 | 1 | 0 | needs deeper pass |
| #42 economy_audit (1–17 + §3.2.D) | 18 | 8 | 3 | 6 + 1 in flight | known |
| **Totals** | **64+** | **43** | **5** | **13** | net |

---

## Part 3 — Summary: Where the v1 Audit Diverged from Reality

The v1 audit said: 27 ✅ / 3 🟡 / 5 ❌ / 3 🚫 (38 total docs).

The corrected picture (this v1 + closeouts):

**Documents tracked:** 49 (38 + 3 closeout 1A + 4 review-doc reclassification + 4 historical references)

**Document-level status (treating multi-design docs as compound but using their dominant signal):**

| Status | Count |
|---|---|
| ✅ Delivered or substantially delivered | 30 |
| 🟡 Partial (including the multi-design rollups and audit backlogs) | 9 |
| ❌ Not implemented | 6 |
| 🚫 N/A | 4 |
| ⚠️ Needs deeper verification pass | — (#16, #45 partly) |
| **Total** | **49** |

**Most consequential miss in v1:** `ollama_idle_queue_design_v1.md` was marked ✅ but has zero implementation. This is a single-doc correction, not a backlog reclassification.

**Most consequential bucket discovered:** the 11 Designs A–K in `competitive_analysis_feature_designs_v1.md` each got individual implementation status — 10 ✅, 1 ❌ (Permadeath, Design A). That ❌ alone is a ~12–16 hour design that was hidden behind a single-checkbox audit row.

---

## Part 4 — Specific Status Corrections to Apply to v32

When v32 rolls up, these specific lines should change vs. v1 audit:

| Doc | v1 audit said | v32 should say | Reason |
|---|---|---|---|
| `competitive_analysis_feature_designs_v1.md` | (single row) | 11 sub-design rows (A–K) | 1 of 11 ❌ (Permadeath A) hidden |
| `competitive_analysis_feature_mining_v1.md` | (single row) | 23 sub-feature rows | 5 of 23 ❌ (3 genuine, 2 Tier 4) hidden |
| `gemini_critique_response_design_v1.md` | (single row) | 5 sub-issue rows | Issue 2 partial (Ollama queue) |
| `ollama_idle_queue_design_v1.md` | ✅ (incorrect) | ❌ Not implemented | Symbol-level audit returns zero hits |
| `organizations_factions_design_v1.md` | ✅ | 🟡 Partial | 4 of 6 factions wired in Director; guild system unverified |
| `economy_audit_v1.md` | (treated as review doc, untracked) | 🟡 Partial — 18-item backlog | 6 of 18 ❌ (Phase 3 mostly untouched) |
| `architecture_status_post_review.md` | (treated as review doc, untracked) | 🟡 Partial — 4-item backlog | C4 regressed; D2/D6 pending |
| `code_review_session32.md` | (treated as review doc, untracked) | 🟡 Partial | A/B fixed; C4/D2/D6 outstanding (overlap with #43) |
| `opus_code_review_session4.md` | (treated as review doc, untracked) | 🟡 Partial — Bug #6 confirmed | Director faction roster incomplete (4/6) |

---

## Part 5 — Honest Backlog of ❌ Not-Implemented Items (Decomposed)

This is what's actually outstanding, ignoring "🚫 N/A" and "future consideration":

### From the original 41 + closeout additions (5 items)

1. ❌ `clone_wars_era_design_v3.md` — entire era pivot stack
2. ❌ `world_data_extraction_design_v1.md` — F.0 loader (the bottleneck)
3. ❌ `wilderness_system_design_v1.md`
4. ❌ `padawan_master_system_design_v1.md`
5. ❌ `weight_of_war_design_v1.md`

### Hidden inside multi-design docs (10 items)

6. ❌ Design A — Consensual Permadeath System (12–16 hrs)
7. ❌ #5 — Scar system (2–3 hrs; was Tier 1)
8. ❌ #15 — Director era-progression thresholds (4–6 hrs; was Tier 3)
9. ❌ #17 — Layered equipment descriptions (8–12 hrs; was Tier 3)
10. ❌ Ollama Idle Queue (full doc)
11. ❌ Economy audit #9 — Power pack consumables (2–3 hrs)
12. ❌ Economy audit #12 — Dynamic trade prices / supply curves (4–6 hrs)
13. ❌ Economy audit #13 — Resource decay (2–3 hrs)
14. ❌ Economy audit #14 — `@economy` web dashboard panel (3–4 hrs)
15. ❌ Economy audit #15 — Ship impound mechanic (2–3 hrs)
16. ❌ Economy audit #16 — Loot tables on NPC kills (3–4 hrs)

### From review-doc backlogs (3 items)

17. ❌ Phase 3 C4 god-object refactoring (FireCommand 518L, AttackCommand 428L, CourseCommand 248L) — **regressed since post-review was written**
18. ❌ Hardcoded ANSI → `server.ansi` module (1,257 hits remain)
19. ❌ Input length limits (no `MAX_INPUT_LEN`)

### Excluded (intentional or out of scope)

- #22 Hacking minigame (Tier 4, future consideration)
- #23 Player senate (Tier 4, future consideration)
- Bulk-premium pricing (🟦 in flight per parallel Sonnet session)
- Tutorial/web client items already tracked under #41

**Total honest ❌ backlog: ~19 items**, distributed: 5 large (Clone Wars/wilderness/padawan-master/weight-of-war/world-extraction), 11 medium (1–6 hrs each), 3 architectural cleanups (refactor work).

---

## Part 6 — Recommended Actions

1. **Re-upload the 4 historical design docs** (`space_expansion_v2_design.md`, `space_expansion_v2_addendum.md`, `combat_ux_overhaul_design.md`, `capital_ship_rules_design.md`) to project knowledge for v32 §25 referencing. Or add an explicit "Retired (delivered)" row in v32 §25 with code-symbol pointers so they don't keep being lost.
2. **Re-classify `ollama_idle_queue_design_v1.md` as ❌** in v32 §25. This is a real backlog item. Decision: implement (~3–4 hrs design says) or formally retire?
3. **Decompose the multi-design docs** in v32 §25 — list sub-items A–K, sub-features 1–23, etc. so single ❌ items don't hide inside ✅ rollup rows.
4. **Verify Bug #6** (Director faction code mismatch) is acceptable as-is, or extend `VALID_FACTION_CODES` to the full 6-faction roster (`traders_guild`, `underworld`).
5. **Audit `organizations_factions_design_v1.md` properly** — it's marked ✅ but has at least one confirmed gap. Run a phase-by-phase scorecard.
6. **Verify the 5 remaining `opus_code_review_session4.md` bugs** beyond Bug #6 — the v1 audit didn't.
7. **Decision-time on the ~19-item honest ❌ backlog**:
   - Permadeath (Design A) is the largest discrete feature on the list. Worth scheduling explicitly or formally deprioritizing.
   - Scar system (#5) was Tier 1, supposed to be ~2–3 hrs. Easy win.
   - 6 economy Phase-3 items total ~17–24 hrs. Cluster them as a single sprint?
   - Architectural cleanups (#17–#19) are pre-launch hygiene. Worth a dedicated grind session.
8. **Process change for future audits:** any doc with named subsections (Design A/B/C, Tier 1/2/3, Phase 1/2, Drop 1/2/3, numbered fixes/issues) gets each row tracked individually in §25, never as a single rollup checkbox.

---

## Companion Documents

| Document | Status | Purpose |
|---|---|---|
| `comprehensive_design_doc_scorecard_v1.md` | This document | Master scorecard reflecting full reality |
| `economy_audit_implementation_scorecard_v1.md` | Companion (Apr 24) | Per-item evidence for #42 |
| `economy_bulk_premium_design_v1.md` | Companion (Apr 24) | Spec for in-flight implementation |
| `design_doc_audit_closeout_v2.md` | Superseded by this v1 | Earlier iteration; this version absorbs it |
| `design_doc_implementation_status_v1.md` | Original audit, still valid as reference | The 38-doc original survey |

---

*End of Comprehensive Design Doc Scorecard — Version 1.0*
