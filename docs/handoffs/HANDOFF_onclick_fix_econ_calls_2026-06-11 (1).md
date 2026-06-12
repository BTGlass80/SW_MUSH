# HANDOFF — Onclick-export fix (tour + Webify modals) · economy calls
## Session 2026-06-11 (2nd) · Drop 3 · Rollup: `SW_MUSH_drops1-3_rollup_2026-06-11.zip` (14 files, CUMULATIVE — supersedes drops1-2)

**Apply:** `Expand-Archive -DestinationPath . -Force` from the Windows project root, then
`run_all_tests.bat`. This zip contains drops 1–2 at their latest state plus drop 3 — apply this one
zip only. **Windows validation pending for all three drops.**

---

## 1. Drop 3 — the bug you hit, and its whole class

The tour buttons were dead because `client.html`'s inline script is a **strict-mode IIFE** — inline
`onclick` attributes resolve in GLOBAL scope at click time, so any handler without a
`window.NAME = NAME` export is a silent ReferenceError. The audit found **12 dead handlers**, not 3:
the tour trio (NEXT / SKIP / the TRAINING-head **?** replay) **plus the ✕-close and backdrop-click
of every Webify modal** — inventory, shop, board, craft, city. ESC worked everywhere
(addEventListener), which masked it. All 12 exported per the file's convention.

**Regression net** (`tests/spa/test_client_onclick_exports.py`, 4 tests): a whole-file sweep that
makes the class unrepresentable (bite-verified against a sabotaged copy), instance pins, and a
jsdom `runScripts:'dangerously'` test that extracts the LIVE tour code/markup and dispatches REAL
clicks — 1/4 → NEXT → 2/4, SKIP hides + sets the localStorage flag, replay-? still works after.
No prior test executed the inline handlers; this closes that for every current and future onclick.

**Your onboarding walk can resume after applying this zip.** Also re-check the modal ✕ buttons
(inventory / shop / board / craft) while you're in there — they were equally dead.

## 2. Decisions recorded this session

- **`CRAFT.market_segmentation` = a** (resolved): Avail-1 vendor-stocked at book cost + craftable;
  Avail-2/3 craft/loot/player-shop supply; Avail-4/X = Drop G black market. Implementation queued as
  `CRAFT.market_segmentation_impl` (lands with Lane C vendor families / Drop G; starts with the
  existing-stock audit + explicit grandfather-vs-withdraw list — no silent inventory rips).

## 3. Two NEW design calls (HEAD facts gathered this session — letters fine)

**`ECON.p2p_cap_review`** — yes, a cap exists: **1,500 cr per rolling 24 h per sender** on the
trade credit path (audit v2 §2.4, tightened from v1's 5,000), race-safe at accept, plus a **5%
tax**. Item trades uncapped; vendor-droid sales + faction treasuries exempt by design.
*Recommendation (a):* remove the hard cap, keep the 5% tax and ledger tag, convert the threshold
into an `@economy` velocity ALERT (alert infra already exists) — under segmentation (a), one
quality-crafted rifle legitimately trades above 1,500, so the cap now fights the core loop, and the
audit's own note shows caps only linearly slow multi-alt funneling. (b = raise to N · c = keep.)

**`CRAFT.schematic_tuition`** — trainer learning is currently **free and all-at-once**: one
`talk kayson` grants his ENTIRE list (16+ schematics after Drop B); PC `teach` is free;
`base_cost` feeds only repair/salvage, no tuition consumer exists. *Recommendation (a):* graduated
tuition — trainer lists prices, new `learn <schematic> from <npc>` charges
`adjust_credits(.., "schematic_tuition")` and grants ONE schematic at **50% of base_cost (min 50
cr)** so price tracks desirability automatically; **PC teach stays free** (your lean — payment is
RP + the trade verb, making crafter→apprentice a social loop). In-drop caveats already logged:
tutorial chains that do "talk trainer → craft" (Heist/medpac) need first-one-free or chain-grant
exemption; no clawback for chars who already free-learned. (b = flat per-band 100/250/500 ·
c = keep free.)

## 4. Verification + queue

- **Sandbox:** drop-3 suite 4 green (sweep bite-verified) · wireup+onboard 36 · modal-family spa 14 ·
  hygiene 9 · inline script syntax-checked. Drops 1–2 batches unchanged from this morning (273).
- **Windows:** drops 1–3 pending — watch items unchanged from the drops-1-2 handoff (melee-NPC
  pools correctly jump; mission/craft training now counts) + the new spa suite.
- **Queue:** 1) Brian: apply, suite run, resume onboarding walk. 2) Letters: `ECON.p2p_cap_review`,
  `CRAFT.schematic_tuition`. 3) Gundark Drop C (armor + armorer trainer) on "continue"; D–F behind
  it; tuition drop slots before/with Drop G if (a). 4) `WEBIFY.commissary_vendor_mode`,
  `CRAFT.HOOK.*` passes, Lane C remainder + Lane F, Kamino, Drop-5 farming controls.

## 5. Session learnings

- **"It renders" ≠ "it's wired."** The Webify wave's render contracts were all tested; not one
  click on an inline handler was. Interaction surfaces need at least one real-event test per wave —
  the sweep now enforces the wiring half structurally.
- **Strict-IIFE + inline onclick is a standing trap** in this file: any future handler must ship
  its export line, and the sweep fails the suite the moment one doesn't.
- **A masked failure mode hid five modals' worth of dead buttons:** ESC handlers worked, so manual
  testing closed modals without ever touching ✕. When two paths exist, test the one users click.
