# HANDOFF — Autonomous roadmap session RESULTS
## Session 2026-06-12 (9th, unattended Opus 4.8 1M) · for Brian's return

This is the results handoff for the autonomous session you set up in
`HANDOFF_autonomous_roadmap_setup_2026-06-12.md`. I worked the queue with the
subagent pipeline (Opus judgment + Sonnet implement/verify), committing per
drop on `roadmap`, no pushes/merges/full-suite runs.

---

## TL;DR — what got done

**All four "implementable now" queue items (handoff §5 items 1–4) are DONE**,
plus two pre-existing watch-item reds fixed, plus design calls queued for you.

| Drop | What | Tests | Verified |
|------|------|-------|----------|
| 13 | Buy-verb tail: `tracking_fob` +1D-Search wired to the Drop-F carried-tool seam (both landing paths); ledger tag `ship_weapon_purchase`→`ground_weapon_purchase` | new `test_buy_verb_tail.py` (10) | auditor CLEAN + 116/116 targeted |
| 14 | `T2.DEF.t5_drop_hooks` CLOSED: `scavenged_republic_tech` faucets from Coruscant Underworld harvest (region-keyed, tier-independent 7% bonus roll, +1 @ q75) | new `test_t5_scavenge_hook.py` (20) | auditor CLEAN + 77/77 |
| 15 | **Triage** (pre-existing red): `test_t5_difficulties_are_above_t4_ceiling` — excluded contraband schematics from the ceiling (Drop G's Heroic-cap band is a separate axis from crafting tier) | fixed in place | 40/40 file |
| 16 | `T2.DEF.handler_npcs` CLOSED: dynamic-HQ housing hook — `purchase_hq` spawns a faction-coded intel handler in the HQ entrance, `sell_hq` tears it down (+ latent `sell_hq` FK-ordering fix) | new `test_t2def_dynamic_hq_handler.py` (5) | auditor CLEAN + 12/12, 158-blast-radius clean |
| 17 | **Triage** (pre-existing red): `test_cities_phase4b` 3 BuyCommand city-tax tests — seed a vendor NPC (watch-item #7: they predated the vendor-presence gate) | fixed in place | 16/16 file, 158-blast-radius |
| 18 | `Coruscant Underworld` region build-out: **+12 landmarks** across 4 quadrants (parallel content-author fan-out, 4 new include files) | new `test_coruscant_underworld_buildout.py` (9) | loader 0-error/20-landmarks; era sweeps green |

Plus **3 design calls queued** in `TODO.json::design_calls_pending_brian`
(see §4 below).

---

## 1. Git state & what YOU do next

- Everything is committed on `roadmap` (drops 13–18 + the design-call commits).
  Your own infra commits (`enforcement hooks`, `code-reviewer/smoke-verifier
  agents`) interleaved cleanly — I stage files explicitly per drop, never
  `git add -A`, so nothing of yours was swept in.
- **The full Windows suite has NOT been run** (deny-listed in-session). It is
  the gate before merge, exactly as before.

**Your cheat-sheet (VS Code terminal, `c:\SW_MUSH`):**
```sh
run_all_tests.bat                 # the ~7,700-test gate
# If GREEN:
git switch main && git merge roadmap && git push && git switch roadmap
```
If RED, see §2 — most expected reds are watch-item flips I either pre-fixed or
documented.

> **Heads-up:** `node_modules/`, `package.json`, `package-lock.json` are
> untracked in the worktree and **not gitignored** (a local npm/jsdom
> experiment, I think). I never committed them. You may want to add
> `node_modules/` + `package-lock.json` to `.gitignore`.

---

## 2. Watch-item flips (handoff §7) — status

Your §7 listed 7 deliberate behavior changes that would flip suite tests
pinning old bugs. I found and **pre-fixed two of them in-sandbox**:

- **#6/#10 (T5 difficulty vs contraband):** drop 15 — `test_syn6c…
  test_t5_difficulties_are_above_t4_ceiling`. Drop G's contraband band
  (predator_rifle/anti_vehicle_grenade @ diff 26, the Heroic cap) reached the
  same difficulty as T5 via a *different axis* (illegality, not tier). Fixed
  the test to exclude `contraband` schematics; T5 still > every **legal**
  non-T5 recipe (max legal = comm_jammer 24; all T5 ≥ 25). **Data unchanged.**
- **#7 (buy gates on vendor presence):** drop 17 — `test_cities_phase4b` 3
  BuyCommand city-tax tests. They predated the drop-11 vendor-presence gate, so
  `buy` early-returned before `apply_city_tax` (revenue stayed 0). Seeded a
  vendor NPC so they exercise the real purchase+tax path. **Gate unchanged.**

**The other §7 flips** (trained-pool jumps, armor Dex penalties live, grenades
consume, mitigation gear depletes, tuition charges, buy gates on stock) I could
not surface from the targeted sandbox runs — they live in suites I didn't
touch. When you run the full suite, **expect flips in those areas and fix the
tests to the NEW (correct) numbers, not the old bug** — same rule as §7.

---

## 3. Key findings / reframes (read these)

1. **Coruscant Underworld content is now built out (20 landmarks), but the
   real playability gate is the RENDERER, not content.** The wilderness map
   renderer is still hardcoded to Dune Sea (design doc §4a generalization,
   `static/spa/m3_tier_wilderness_body.js` ~line 195) — so the region renders
   as *sand* until §4a ships. §4a is JS/SPA work that needs **your
   Windows/browser pass** (the sandbox can't render-verify). My +12 landmarks
   are functional as reachable, described rooms now; the map is the unlock.
2. **Landmark `ambient_lines` + gameplay properties are forward-looking, not
   live** — and this is *pre-existing*, affecting the 8 original anchors
   identically: `ambient_lines` ride `TD.WILDERNESS_AMBIENT_LINES_DEAD_WRITE`
   (written to a room prop with no runtime reader); `threat_tier`/
   `gameplay_role`/`faction_anchor` have **zero** live consumers (they await the
   encounter-spawner phase). My build-out reused only the established vocabulary
   (no invented/phantom keys) so it surfaces for free when those phases land.
   The **consumed** payload today is the reachable described room itself.
3. **`OBS.quality_and_boosts_not_combat_read` is HIGH-value and mostly
   unblocked** — see §4. Crafted quality is currently a pure credit sink with
   zero combat payoff. The weapon path is one parameter-pass from working.

---

## 4. Design calls queued for you (`design_calls_pending_brian`, 3 pending)

1. **`OBS.quality_and_boosts_not_combat_read`** (HIGH) — design-reviewer'd,
   decision-ready. Combat reads registry baseline by key; the crafted
   `ItemInstance` (quality + `effective_mods`) is read for wear at
   `combat_commands.py:1462` then **discarded at :1671**. Recommendation:
   **Option B** — wire weapon damage+accuracy now (unblocked, no migration),
   defer armor soak (blocked-on `TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES`).
   WEG-faithful pip caps (+1D max over vendor). **Two forks need your call:**
   (a) sanction the combat-isolation breach for *equipped crafted gear* (Drop F
   pinned combat tool-immune — this is a different, intended seam); (b) the pip
   cap (+1D vs +2 pips). *This one is ready to implement the moment you ratify.*
2. **`ECON.commissary_sellback_model`** — added a preliminary (reasoned, not
   formally reviewed) anti-laundering model: no open-market sellback for
   `faction_issued` gear; faction-commissary partial refund ≤50% of requisition
   cost via a `commissary_sellback` tag smaller than the purchase sink that
   created it (net loss → no buy-cheap/sell-high loop). Ratify or send to
   design-reviewer.
3. **`CRAFT.harvest_skill_flavor`** (LOW) — from drop 14: ship Survival now vs.
   per-region harvest-skill override post-launch. Recommended Survival now.

The remaining §4 forks (powered-suit, mines/breaching, `CRAFT.HOOK.restraints`,
`CRAFT.HOOK.force_detector`, world-event 6 FLAG effects, `TD.DIRECTOR_FACTION_
MODEL_GCW`, eavesdrop `target_char`, market-seg grandfather-vs-withdraw) are
**not yet design-reviewed** — I prioritized the highest-leverage one. They're a
clean batch for a future design-only session.

---

## 5. Next implementable work (for the next session)

- **Implement `OBS.quality_and_boosts_not_combat_read` Option B** once you
  ratify — it's the highest-value unblocked drop on the board (makes the whole
  crafting-quality economy matter in combat). Spec is 90% written in the design
  call.
- **Coruscant Underworld §4a renderer generalization** — the playability gate
  (your Windows/browser involvement needed).
- **Design-review-then-log the rest of §4** — single-threaded design session.
- Pre-release items (`PRELAUNCH.help_guides_rework`, `web_landing_retention`,
  browser smoke-tests) remain explicitly deferred to end-of-roadmap.

---

## 6. Pipeline notes

The Opus-judgment / Sonnet-execute pipeline worked well: every non-trivial drop
went `Explore/design-reviewer → drop-implementer → invariant-auditor +
test-runner → commit`. Drop 18 used a 4-way `content-author` parallel fan-out
(one per disjoint quadrant, separate include files) — zero coordinate
collisions, clean merge, validated by the loader + a pin test. The auditor
caught real things (it scrutinized drop 16's unspecced `sell_hq` FK reorder and
confirmed it equivalent). Two of my own test-fixes (drops 15, 17) came from the
test-runner surfacing pre-existing reds during verification — worth running the
blast radius, not just the touched file.
