# SW_MUSH — Handoff (2026-06-06)
**For:** the next chat. **From:** the creature special-attack session.
**Repo:** BTGlass80/SW_MUSH · Clone Wars era · Python 3.14 · aiohttp/aiosqlite · vanilla-JS SPA.

---

## 1. What just shipped this session — Lane A tail (creature special-attack mechanics)

Closed the explicitly-deferred remainder of **Sourcebook Enrichment Lane A** (roadmap §3: "full poison/grapple *mechanics* are a follow-up"), under Brian's 2026-06-06 design-call #3 approval (poison/grapple/constrict as DoT + restraint, **WEG R&E D6 ONLY**, traced to the creature extractions). The 14 Lane-A creatures had inert poison/grapple riders; now they bite. Built by **extending** the combat round — no new system/command/schema.

**Mechanics (R&E-faithful):**
- **Poison = DoT.** Landed natural-attack hit injects a stack; each round-end (`_cleanup`) it counts down onset (slow-acting venom) or rolls damage vs the victim's **Strength** (no armor soak) on the wound ladder, then decrements. Re-envenom by same source refreshes (no unbounded stacking). Ticks regardless of can-act.
- **Restraint = a hold.** Grabbed → −2D attack pool, **cannot flee**, opposed break-free (brawling, holder wins ties) each round until won or grappler gone/dead/fled. **Constriction/choke** also squeeze for per-round STR-based damage. Downed victim isn't squeezed (no double-jeopardy with the MW death roll).

**Files (in the zip):** `engine/creature_special_attacks.py` (**NEW**, pure), `engine/character.py` (+2 hydrated spec dicts, not persisted), `engine/creature_library.py` (sheet injection), `engine/combat.py` (Combatant `poison_stacks`/`restraint`; `_apply_special_attack_on_hit`; `_cleanup` ticks; flee block; held-attacker penalty), `data/npcs_creatures.yaml` (structured `special_attack` on the **6** rider creatures — spor_crawler 5D / hitcher_crab 2D+2 slow / glim_worm + voroos grapple / stalker_lizard constriction STR+2D+2 / somago choke STR+3D; `natural_attack` left untouched so the Phase-B resolved-damage pins hold), `tests/test_creature_special_attacks.py` (**NEW, 34**), `CHANGELOG.md`, `TODO.json`.

**Verification (sandbox):** 34/34 new. Regression: combat+creature+sense **208/208**; death/insurance/hunter/cult green individually; era-cleanness 7/7; hygiene 9/9. New code B3/Q1-clean, AST + pyflakes clean. End-to-end smoke confirmed inject-on-hit + tick through real `resolve_round`.

**Deliverable:** `SW_MUSH_creature_special_attacks_drop_20260606.zip` (8 files, root-mirrored). Apply: `Expand-Archive -DestinationPath . -Force` from project root.

**⚠ Brian's Windows gate (still open):** apply the zip → run the full ~7,700 pytest suite with the new file → smoke live: spor-crawler venom DoT, stalker-lizard constriction-pin (can't flee + squeeze), glim-worm grab-and-break-free.

**Arch doc:** `sw_d6_mush_architecture_v51.md` is **stale** (held for a v52 reconciliation). This invariant folds into v52 as **§4.34** (after the cult's §4.33). CHANGELOG.md + TODO.json are authoritative until then.

---

## 2. NEW direction from Brian this session — pivot to UI *after* enrichment

Two TODO items added to `tier_2_queued` (both **sequenced AFTER Lanes A–F complete**):

- **`T2.UIPKG.claude_design_handoff`** — Produce a **detailed package for Claude Design** to expand the web SPA UI for gameplay surfaces that are currently text-only. Claude (this project) knows the gameplay; Claude Design doesn't — the package must teach each surface. **Hard principle: posing/speaking/RP stays TEXT** (the soul of a MUSH); web UI is for mechanical state + structured interactions, shown alongside the RP stream. The just-shipped **vendor UX is the pattern to extend**; **inventory** is the obvious adjacent surface, and there's likely a lot more (combat HUD incl. the new poison/restraint conditions, space combat, crafting/mining, economy/+market/bounty board, Force palette, CP/training, org/faction dashboards, territory overlay, city/housing/shop management, tutorial/onboarding, channels/mail/news, sabacc, etc.). Also: keep room **descriptions** text but consider a persistent room panel (exits/occupants/objects/POIs) — and **investigate+fix a flagged bug**: on movement the text pane doesn't reliably auto-scroll to the new room. Deliverable = per-surface spec, prioritized, referencing the existing SPA (`m3_*`, `m3_tier_registry` getTierRenderer) + `web_client_vision_and_protocol_v1_3` so Claude Design **extends**, not reinvents. Workflow: Claude drafts package → Brian prioritizes → implementation drops. Brian's view: the web interface is plausibly **make-or-break** (different audience than classic MUSHers — matches Claude's original web-first call).

- **`T2.DIFF.difficulty_tiers_design`** — (split out because it's a **world-design axis, not strictly UI**, though they connect via zone difficulty indicators). No difficulty levels today; Brian wants newbie/mid/end-game areas for combat **and space combat**, wilderness **sections with known lines**, and PC cities only in mid-to-high tiers. **Claude recommendation: extend the existing security-zone + wilderness region machinery** (attach a threat band to zones, surface on map/zone header, gate creature-spawn + space-patrol danger by tier via tiered spawn tables over the Lane-A creatures' danger profiles, restrict PC-city placement to mid+ tiers) — don't build a parallel system. **Needs a Brian direction-decision + short design doc** before build (taxonomy/count, difficulty-vs-security, hard-gate-vs-advisory, which of the 6 worlds host which tiers, space-lane tiering, newbie PvP-safety vs the +pvp opt-in). Brian invited counter-proposals.

---

## 3. Enrichment roadmap status (the current workstream) — `sourcebook_enrichment_roadmap_v1.md`

- **Lane A** — DONE (Phase A creatures + Phase B spawner bridge + **this session's special-attack tail**).
- **Lane B** — DONE (encounter_patrol B3 era-cleanness leak fixed; verified).
- **Lane C** (expanded gear catalog) — **GATED**: must land after Drop-3 aspirational sinks **and** Drop-5 farming controls (faucets+sinks land together).
- **Lane D** (Geonosis/Kamino faction-tension depth) — content build; faction-tension pre-approved "implement with judgment, plug into existing faction-intent machinery, don't duplicate."
- **Lane E** (small-wins trio) — **NEXT**:
  - **E1** org scale/violence,
  - **E2** sandwhirl hazard + Tatooine clock,
  - **E3** venue front / true-owner + d66 table.
  (Content + small-schema; packageable as one rollup. Note `T2.E3.flag_event_interactions_design` is the related FLAG-effects design item.)
- **Lane F** (Director quest-template library) — needs its **own design doc** first.

**Immediate next action for the new chat:** roll up the **Lane E trio (E1/E2/E3)**, then Lane D. (Brian approves with single chars — "Roll up", "A", "Continue".)

Also still open in the overall pre-launch roadmap (not blocking Lane E): the 5 FLAG world-event effects (pre-approved "implement with judgment"), Drop 5 (`+market`, farming controls, milestone-CP meter-only cap), the T3.19/T3.20/T3.21 pre-launch hardening cluster (telemetry — re-review/expand the thin economy metrics before building; state-preservation/reload-round-trip — F.7.n force_sensitive RECLASSIFIED as speculative not-a-bug, verify via reload test; optimization/security), and the **arch v52 reconciliation** (rebuild the §4.x block from CHANGELOG; renumber cult→§4.33, add special-attack→§4.34).

> **Launch scope reminder:** Brian wants nearly **all** of enrichment (A–F) **+ the remainder of the overall roadmap** done **before** launch (he's wary invasive post-launch schema/state changes break the live game).

---

## 4. Standing disciplines (don't drift)

- **Pre-flight:** read TODO.json + CHANGELOG.md, then the (stale) arch doc. **Symbol-grep HEAD** before claiming anything delivered/undelivered — handoffs and memory are untrusted without a grep. Phantom-delivery is the chronic failure mode.
- **Extend, don't add.** New files only for genuinely new surface; never write a consumer before its provider exists.
- **Faucets + sinks land together** (hard-ordering rule — this is why Lane C is gated).
- **WEG keeps D6 stats; WotC = lore-only, re-statted to D6 from scratch.** Opposed rolls mean real dice, not fixed numbers.
- **B3 era-cleanness:** no Imperial/Rebel/TIE/stormtrooper/clone-trooper in production strings. **Q1:** canonical figures never named open-world NPCs.
- **Smoke scenarios:** slug lookup via `room_id_by_slug()`, never hardcode DB ids.
- **Do NOT blindly implement TODO as written** — rethink design-heavy items at build time.
- **Tests:** sandbox = AST + targeted module tests (`python3 -m unittest`, changed modules only); the **full pytest (~7,700) on Brian's Windows box is ground truth**. Pinned-keyset tests: when a placeholder breaks because a feature shipped, re-purpose to assert the new live contract (don't delete).
- **Every drop:** atomic, game-playable through apply; update CHANGELOG.md + TODO.json (hygiene-test enforced); root-mirror the zip for `Expand-Archive -Force`.

## 5. Paths / tooling
- Working tree: `/home/claude/head`. Outputs: `/mnt/user-data/outputs/`. Design docs: `/mnt/project/`.
- Sandbox note: real-aiosqlite suites can hang **when run together** (event-loop) — run them **individually**; not a failure. Use the `_MiniDB`/raw-aiosqlite harness for new DB tests.
- Current: engine **136 modules**, parser **67**, schema **v43**, ~292 test files.
- Key docs: `sourcebook_enrichment_roadmap_v1.md`, `web_client_vision_and_protocol_v1_3.md`, the `Guide_*` series, `sheet_redesign_design_v1.md`, `combat_mechanics_display_design_v1_1.md`, the eight sourcebook extractions.
