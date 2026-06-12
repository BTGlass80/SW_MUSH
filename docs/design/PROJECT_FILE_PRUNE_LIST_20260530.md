# SW_MUSH — Project Knowledge Prune List
## May 30, 2026 · file-by-file audit for reclaiming project space

Files are listed with the **exact name** shown in the project so you can match them in the
Knowledge UI, plus size and the reason. Work top-down: Tier 1 is zero-risk, Tier 2 needs one
quick check each, and the **Keep** section flags files that look prunable but aren't.

---

## Tier 1 — Safe to delete now (~42.9 MB)

| File | Size | Why it can go |
|---|---|---|
| `WEG40069.pdf` | **22.0 MB** | Galaxy Guide 7: Mos Eisley (scanned). **Now extracted** → `gg7_mos_eisley_extraction_v1.md` preserves the build-relevant content (geography, docking bays, establishments, hooks), era-translated. Your single biggest file. |
| `WEG40027_Galaxy_Guide_6__Tramp_Freighters__1st_Edcompressed4382.pdf` | **10.8 MB** | Duplicate scan of GG6 (the *other* GG6 file is the same book). Pure redundancy — delete regardless. |
| `WEG40027_Galaxy_Guide_6__Tramp_Freighters__1st_Edcompressed142.pdf` | **9.8 MB** | Second GG6 scan. Fully mined into `gg6_tramp_freighters_extraction_v1.md` (9 deliverables). Keep this one only if you want a single scan for art reference; otherwise delete. |
| `sw_d6_mush_architecture_v50.md` | 73 KB | v51 supersedes it and says "discard v50 or earlier; this is the single architecture-of-record." |
| `sw_d6_mush_architecture_v47.md` | 47 KB | Two versions stale (covered by v51's "v50 or earlier"). |
| `economy_audit_v1.md` | 36 KB | `economy_audit_v2.md` reviews and supersedes it. |
| `GCW_AUDIT_REPORT.md` | 35 KB | Completed May-23 contamination audit; cleanup applied and now guarded by the era-cleanness static tests. Job done. |
| `player_cities_design_v1.md` | 25 KB | `player_cities_design_v1_2.md` folds in v1 + v1.1. |
| `gcw_counterparts_and_lore_expansion_design_v1.md` | 12 KB | Drop shipped. **Delete the design doc only — keep the GCW `*.yaml` data files it produced** (deliberate regression/era-switch asset). |

---

## Tier 2 — Delete after one quick check (~15.5 MB more)

| File | Size | Check before deleting |
|---|---|---|
| `Star_Wars_Sourcebook_2nd_Edition_WEG400932.pdf` | **14.7 MB** | OT/GCW-era core book (Empire/Rebels/Star Destroyers), scanned. No dedicated extraction, but cited as a mining source by `sourcebook_mining_crafting_exp_design_v1` and `cwcg_extraction_v1`. **Confirm the crafting/gear/species content you needed is already captured there + in the Guides**, then delete. |
| `npc_space_traffic_design_v2.pdf` | 0.73 MB | A v2 design doc zipped as a PDF. `space_overhaul_v3_design.md` builds on / replaces its zone model. **Confirm v3 + `Guide_05_Space_Systems` cover it**, then delete. |
| `economy_design_v02-1.md` | 22 KB | Original v0.2 design, superseded by the audits + `Guide_06_Economy`. **Confirm the "Four Laws" rationale lives elsewhere**, then delete. |

---

## Tier 3 — Optional housekeeping (tiny, ~155 KB — only if you want it tidy)

These were folded into the web-client protocol or the architecture-of-record. Savings are
negligible; do these only for cleanliness, and **verify each was fully folded** first.

| File | Size | Note |
|---|---|---|
| `Map_Redesign_v2.html` | 59 KB | Approved footprint mockup; SPA map renderer is now live end-to-end per v51. |
| `ground_ux_overhaul_design_v1.md` | 34 KB | Listed as a superseded companion in protocol v1.3. |
| `HANDOFF_MAY22_CITIES_PHASE5.md` | 22 KB | Old handoff; cities work folded into architecture v51. |
| `web_ux_competitive_analysis.md` | 17 KB | Superseded companion (protocol v1.3). |
| `web_client_ux_overhaul_v1.md` | 12 KB | Superseded companion (protocol v1.3). |
| `CLAUDE_DESIGN_BRIEF.md` | 11 KB | Folded into protocol v1.0 §7. |

---

## Keep — do NOT delete (these look prunable but aren't)

- **`WEG40120.pdf`** (1.1 MB) — the R&E core ruleset. Foundation of every mechanic. Non-negotiable.
- **`web_client_vision_and_protocol_v1_2.md`** (139 KB — your biggest `.md`) — v1.3 is a *delta* on it ("v1.2 stays in force; pull v1.2 for those"). Deleting it guts the protocol spec.
- **`WEG40092.pdf`** (455 KB) — Imperial Sourcebook. Off-era but small and still cited by `clone_wars_era_design_v3` / `space_overhaul_v3`. Not worth pruning.
- **The three May-30 handoffs** (`HANDOFF_MAP_ENV_BEARING_POI_…`, `HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_…`, `HANDOFF_OBJECTIVE_AND_VENDOR_POI_…`) and **`MAP_NAV_OVERLAY_DROP_20260529.md`** — current/in-flight; the SPA cutover (Drop 4.14 + navigator wiring) isn't finished. Keep until that lands.

---

## Bottom line

- **Tier 1 alone:** ~42.9 MB.
- **Tier 1 + Tier 2:** ~58.4 MB — well over half the project, almost all of it three scanned PDFs.
- The `.md`/`.html` prunes barely move the needle; the wins are the scans. Once `WEG40069.pdf`
  is gone (extraction is in `gg7_mos_eisley_extraction_v1.md`), the biggest pressure is off.
