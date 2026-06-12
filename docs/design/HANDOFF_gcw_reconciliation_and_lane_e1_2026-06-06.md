# HANDOFF — GCW test reconciliation + Lane E1 + two locked decisions
**Date:** 2026-06-06
**Session:** Recorded two design decisions, shipped a GCW-retirement **test-reconciliation** drop (production code untouched), and shipped **Lane E1** (org scale + Violence Index + 9 GG11 underworld lore entries). Both drops verified in sandbox; both await the Windows full-suite gate.

---

## 0. TL;DR — two zips in `/mnt/user-data/outputs/`

| # | Zip | Touches | Deletions? | Windows gate |
|---|-----|---------|-----------|--------------|
| A | `SW_MUSH_gcw_test_reconciliation_drop_20260606.zip` | **tests only** (12 reconciled) + CHANGELOG + TODO | **YES — 1 file** | full suite → expect 0 GCW-fallout failures |
| B | `SW_MUSH_lane_e1_org_scale_violence_drop_20260606.zip` | organizations.yaml, organizations.py, faction_commands.py, lore.yaml, +1 test, CHANGELOG, TODO | none (additive) | full suite + `faction info` spot-check |

**⚠ APPLY ORDER MATTERS — apply A first, then B.** Both zips contain `CHANGELOG.md` and `TODO.json`. **B's copies are cumulative** (they already include A's reconciliation entry + A's design calls + A's tech-debt closure, plus E1's). If you apply B then A, A's older CHANGELOG/TODO would overwrite and **lose the E1 bookkeeping**. No other files overlap (A = `tests/*`; B = prod/content + its own test), so apply A, run its deletion, then apply B.

---

## 1. Drop A — GCW-retirement test reconciliation (NO production-code change)

**Why:** the GCW-retirement drop deleted `data/worlds/gcw`, `data/organizations.yaml`, and `_LEGACY_TEMPLATES_GCW`, and flipped the default era to clone_wars — but its README deletion list covered only **6** test files and missed **~13** others still asserting GCW contracts. Result on your last Windows run: **44 failed + 50 errors** (53× WorldLoadError `missing data/worlds/gcw/era.yaml`, 30× AssertionError, 3× ImportError `_LEGACY_TEMPLATES_GCW`, 1× IndexError empty-GCW-chargen). **Zero were production regressions; zero touched the creature special-attack drop (its gate is green).**

**What it does:** retires tests whose premise is gone, repoints dual-purpose ones to the live clone_wars contract. **1 deleted + 12 reconciled.**

- **DELETED (via Remove-Item — zip can't delete):** `tests/test_world_loader_gcw.py` (wholly GCW; `test_world_loader.py` covers CW).
- **RETIRED classes/methods** (dead premise): `TestGcwHasNoWilderness`; the `test_f7` GCW byte-equivalence class + GCW carryover/corpus/manifest/legacy-fallback methods; `test_f5b3b` GCW YAML-parse / byte-equiv / room-id-drift classes + GCW override methods; `test_f5b2` `TestGCWPath` + explicit-gcw-snapshot; `test_f5b1` gcw-factions-present / faction-min-rank-gcw / best-tier-gcw; `test_f5b3c` GCW lot-cardinality (→ one "gcw yields empty, no crash"); `test_smoke` gcw_chalmun methods; `test_b1d3`/`test_f5d` "existing GCW entries unchanged"; `test_world_writer.test_room_properties_persisted` (no CW room has properties).
- **REPOINTED to clone_wars:** `test_default_era_is_gcw` → `..._is_clone_wars` (test_b1a, test_f1d); `test_world_writer` counts + zone/room/exit assertions now **derive from the loaded bundle** (280 rooms / 35 zones / 270 exits) — era-robust; `test_f7` seam-return-shape + dataclass-shape → `clone_wars` (this **fixed 2 vacuous-pass tests** that iterated a now-empty GCW dict); `test_f7` unknown-era fallback → asserts `{}` (the in-Python legacy fallback was deleted); `test_f5b3c` → asserts `get_tierN_lots('gcw') == []`; `test_b1d3` dict-size `10 → 4` (CW-only `FACTION_QUARTER_LOTS`).

**Sandbox verification (all green, 216 passed, 2 pre-existing skips):** provider/loader 89, b1d3 34, f5d 22, smoke 15, world_writer 27, f1d 9, b1a 9, wilderness 11. Hygiene 9.

**Apply (PowerShell, from project root):**
```
Expand-Archive -Path SW_MUSH_gcw_test_reconciliation_drop_20260606.zip -DestinationPath . -Force
Remove-Item -Force tests\test_world_loader_gcw.py
run_all_tests.bat
```
**Gate:** full ~7,700 suite → expect **0** GCW-fallout failures. (Full detail in `APPLY_GCW_TEST_RECONCILIATION_README.txt` inside the zip.)

---

## 2. Drop B — Lane E1 (org scale + Violence Index + 9 GG11 lore entries)

Sourcebook enrichment, **Lane E small-wins trio, E1 of 3**. Source: `gg11_criminal_organizations_extraction_v1.md` §2/§3A/§8B; roadmap §7.

**Provider (NO schema change — both live in `organizations.properties` JSON):**
- `scale` = GG11's five-tier criminal taxonomy `gang|guild|cartel|syndicate|empire`. Applied **only to criminal orgs**: `hutt_cartel` = `empire`/vi 88, `bounty_hunters_guild` = `guild`/vi 55.
- `violence_index` (0–100) on **all** factions: republic 25, cis 60, jedi_order 15, sith 95, separatist_council 65, independent 30. State factions carry the tone but **no criminal `scale`**.

**Helpers (pure, in `engine/organizations.py`):** `ORG_SCALES`; `get_org_scale`; `get_org_violence_index` (clamped 0–100, bool-rejecting, tolerates JSON-string props, `default=None` so display stays silent when unset); `violence_descriptor` (surgical <30 / pointed / heated / bloody / range war 85+); `format_org_posture_line`.

**Consumer shipped now:** `parser/faction_commands.py` → `faction info` shows a **Scale + Posture** line. (So the field is **not inert**.)

**Lore:** 9 era-translated GG11 §2 entries appended to `data/worlds/clone_wars/lore.yaml` — Criminal Organization Tiers, Criminal Occupations, The Kajidic, Indentured Servitude, Haven Worlds, The Black Market Code, Spice, Slaver Guilds, Sector Rangers. B3-clean, Q1-safe. **The Kajidic** and **The Black Market Code** *extend* (never restate) the existing Hutt Cartel / black-market lore.

**⚑ Deferred to Lane D (flagged, not skipped):** wiring `violence_index` into (1) territory-contest **aggression math** and (2) the Director's **turf-dispute narration** ("range war" vs "surgical"). Both plug into the existing **SYN.3 faction-intent/contest machinery (`engine/contest.py`)**, so they belong with the Geonosis/Kamino faction-tension work rather than a hasty contest-math edit. `violence_descriptor` / `get_org_violence_index` are the reusable primitives that wiring will consume.

**Sandbox verification (all green):** `test_e1_org_scale_violence` 27; `test_f6a2_world_lore_yaml` 9 (+4 skip); `test_b1b1_organizations_constants_era_aware` 20; `test_b6_defensive_faction` 18; `test_b1d3_cw_faction_anchors_wired` 34. AST-clean; both YAMLs parse. Hygiene 9.

**Apply (PowerShell, from project root — additive, no Remove-Item):**
```
Expand-Archive -Path SW_MUSH_lane_e1_org_scale_violence_drop_20260606.zip -DestinationPath . -Force
run_all_tests.bat
```
**Spot-check (live):**
- `faction info hutt_cartel` → a line `Scale: Empire   Posture: range war (88/100)`
- `faction info republic` → `Posture: surgical (25/100)` (no Scale line)
- After a lore reseed / server restart, search underworld lore: `spice` / `kajidic` / `sector ranger` / `haven` / `slaver`.

(Full detail in `APPLY_LANE_E1_README.txt` inside the zip.)

---

## 3. Decisions locked this session (recorded in `TODO.json` → `design_calls_resolved_recent`)

1. **Lane C gate = SPLIT faucet/sink** (Brian: "Split the faucet/sink"). Purchasable/vendor gear families (anti-inflationary credit **sink**, balance-gated by Gundark's §8 availability + WEG D6 re-stats, **not** by farming controls) may ship **now**, in waves by family. Craftable/lootable families (value/income **faucet**) stay gated behind **Drop-5 farming controls** per the standing faucets-and-sinks-land-together rule. Basis: Drop-3 sinks effectively satisfied; faucet bounds already exist (creature_spoils tier-cap, SURVEY_COOLDOWN_S=900, trading.py per-round-trip ceiling); the missing prereq is only the general Drop-5 farming layer (gates the faucet wave alone).

2. **Markets are LOCAL by design — NO galaxy-wide auction house.** Discovery-not-marketplace / EVE-regional-lite: read-only planet-scoped listing index + buy orders, no remote execution; WoW global AH rejected for a 5–50 pop game. Already partly realized: `parser/shop_commands.py::MarketSearchCommand` (`market search [planet|all]` → planet-scoped player shopfronts via `engine.housing.get_market_directory`; `market <planet>` → cargo prices). Outstanding Drop-5 `+market` work = **item-level discovery + buy-order index** layered on the existing planet-scoped directory — not a new marketplace, not galaxy-wide.

---

## 4. Latent item flagged (NOT fixed — separate from these drops)

`build_mos_eisley.py` argparse `--era` default is still `"gcw"` (~line 546) — a **CLI-only** default now pointing at deleted data. `build()` itself correctly defaults to `clone_wars`, so runtime/auto-build is unaffected. One-line fix to fold into a future **code** drop (not a test drop).

---

## 5. What's next (roadmap)

**Finish the Lane E trio** (each independent, low-risk):
- **E2** — Sandwhirl hazard (ground **and** space; wandering ~200 m funnel, re-stat d20→D6) into `engine/hazards.py`, re-tune graded sandstorm/gravel/heat-thirst; **Tatooine day/night vocabulary** (First Dawn / Second Dawn / High Noon / First Twilight / Second Twilight) as planet-keyed display strings over `engine/world_time.py` (**no renderer change**). Source: SoT §3/§1.
- **E3** — venue `front_owner`/`true_owner` flag-pair (today `housing.py` carries a single `shopfront_owner_id`) as an investigation/territory mechanic + **d66 cantina ambient table** (era-translate the ~4 flagged entries: clone patrol / off-duty mercs / rival-faction double agent). Optional depth: the 10-step venue-generator schema. Source: Wretched Hive §2A/§2B/§2C/§6.

**Then Lane D — Geonosis & Kamino faction-tension.** Must plug into the existing SYN.3 faction-intent/contest machinery (`engine/contest.py`), **not** a second system. **Natural home for E1's deferred work:** `violence_index` → contest aggression + Director turf narration (reuse `get_org_violence_index`/`violence_descriptor`). Related: `T2.E3.flag_event_interactions_design` — the 5 dormant world-event FLAG effects (rare_vendor, hutt_auction, krayt_bounty, brawl_active, distress_active), "implement with judgment, flag only real forks."

**Broader pre-launch backlog (Brian wants nearly all of A–F + the remainder before launch):**
- **Lane C** vendor/sink gear wave (per the split decision above); Lane C faucet families wait for Drop-5 farming controls.
- **Drop 5** — `+market` item-level discovery, farming controls, milestone-CP cap (meter-only, not capped).
- **Pre-launch hardening passes (cluster near T3.19–T3.21):** telemetry (**re-review/expand** the thin economy metrics; async/sampled/non-blocking — never slow the game); state-preservation / reload-round-trip robustness (incl. **F.7.n** — `force_sensitive` survival on reload is an **unconfirmed/speculative** concern: **verify via a reload-round-trip test and close as not-a-bug if FS survives**); optimization + security.

---

## 6. Standing context for the next session (don't relearn the hard way)

- **Pre-flight discipline:** read `TODO.json` + `CHANGELOG.md` before the architecture doc; architecture doc before code; **symbol-level grep of HEAD before claiming anything delivered/undelivered** (phantom-delivery is the chronic failure mode). Don't blindly implement TODO items as written — re-examine design-heavy ones at implementation time and flag real forks.
- **Every drop:** atomic, game-playable through apply; updates `CHANGELOG.md` + `TODO.json` (hygiene-test enforced); ships a **root-mirrored** zip for `Expand-Archive -DestinationPath . -Force`. A zip **cannot delete** — deletions go in the APPLY README as `Remove-Item` lines.
- **Architecture doc `sw_d6_mush_architecture_v51.md` is STALE** (held for a dedicated **v52 reconciliation**: rebuild the §4.x invariant block from the CHANGELOG, renumber cult → §4.33, special-attack → §4.34). CHANGELOG + TODO are authoritative until then. Neither drop this session touched the arch doc.
- **Test philosophy:** sandbox = AST + targeted module tests; **Brian's Windows box (Python 3.14, full ~7,700 pytest) is ground truth.** Real-aiosqlite suites can hang when batched — **run them individually** with a timeout.
- **Sandbox env note (this session):** installed in the sandbox to enable verification — `pytest`, `pytest-asyncio`, `pytest-subtests`, `aiosqlite`, `bcrypt`, `aiohttp`, `PyYAML` (Python 3.12). The working tree at `/home/claude/head` does **not** persist across sessions; the next session re-unzips from a fresh upload. Mid-session during the E1 build I restored `engine/organizations.py` + `data/worlds/clone_wars/organizations.yaml` to pristine from the upload zip to re-run a corrected build script — **final state is correct** (verified by AST + YAML parse + tests).
- **HEAD facts:** `data/worlds/clone_wars` is the only world; default era `clone_wars` (`server/config.py::active_era`); `build_mos_eisley.build(era="clone_wars")`. Org records carry a flexible `properties` JSON column (how E1 added fields with no schema change). CW lore seeds from `data/worlds/clone_wars/lore.yaml` via `seed_lore(db, era=...)` (the legacy `SEED_ENTRIES` literal is deleted).
