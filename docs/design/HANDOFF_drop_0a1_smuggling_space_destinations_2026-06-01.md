# HANDOFF — Drop 0a-1: Smuggling Route Un-break + Space Travel/Landing Maps

**Date:** 2026-06-01
**Drop zip:** `SW_MUSH_drop_0a1_smuggling_space_destinations_2026-06-01.zip` (root-mirrored)
**Apply:** `Expand-Archive -Path <zip> -DestinationPath . -Force` from project root.
**Status:** Code complete, sandbox-validated. This is the clean, no-income-risk first slice of Drop 0a from `sw_mush_remediation_and_fun_additions_design_v1.md`. **It does NOT make the starter-ship quest end-to-end functional** — see §5.

---

## 1. What shipped (3 files)

The top two smuggling tiers and the general hyperspace map still pointed at **Kessel** and **Corellia**, which the 06-01 era drop removed from the Clone Wars graph — so those destinations had no dock zone and the runs **dead-ended**. This drop re-points them onto real CW worlds with verified dock zones, preserving the pay bands and the high-risk gradient.

**`engine/smuggling.py`** (10 edits)
- `ROUTE_TIERS`: `spicerun` kessel→**geonosis** (CIS war front), `corerun` corellia→**coruscant** (Republic capital). Pay bands and launch patrol chances unchanged.
- `PLANET_PATROL_FREQUENCY`: arrival heat now `geonosis 0.50` / `coruscant 0.60` (was kessel 0.40 / corellia 0.60) — preserves "higher-paying run = higher risk."
- Dropoff-flavor branches rewritten for the new destinations (Geonosian foundry / Separatist supply / Baktoid agent for Geonosis; Coruscant underlevel broker / Senate-district fixer / Works spice dealer for Coruscant).
- `_DEST_DISPLAY`, tier comments, `CargoTier.SPICE` comment: kessel/corellia → geonosis/coruscant.
- De-Imperialized comments/docstrings: "Imperial patrols/interest" → "customs."

**`parser/smuggling_commands.py`** (3 edits)
- Two "Imperial patrol" docstrings → "customs patrol"; `dest_planet` example planets → coruscant/geonosis.

**`parser/space_commands.py`** (3 edits)
- `_BAY_SEARCH` (hyperspace landing-room resolver): kessel/corellia → `"Coruscant - Westport Spaceport"` / `"Geonosis - Separatist Landing Platform"` (both verified to exist in CW world data).
- `HYPERSPACE_LOCATIONS` (starmap): replaced the GCW-era list with the **six CW launch worlds** (coruscant, kuat, nar_shaddaa, tatooine, geonosis, kamino). This removes the kessel/corellia dead-ends *and* the off-era Hoth/Bespin/Yavin/Alderaan/Dagobah/Naboo/Kashyyyk display entries in this dict.
- Price-check alias dict: kessel/corellia removed; coruscant/kuat/geonosis/kamino added.

**Intentionally kept:** `"raw Kessel spice"` (commodity name — Kessel-origin spice is canon lore in 20 BBY, not a travel path) and the `_planet_dock_zones()` docstring that correctly documents kessel/corellia's absence.

### Route table after this drop
| Route | Cargo tier | Destination | Pay | Launch heat | Arrival heat | Dock zones (live graph) |
|-------|-----------|-------------|-----|:--:|:--:|-------------|
| local | GREY_MARKET | — (Tatooine) | 200–500 | 0.00 | — | (local) |
| blackmkt | BLACK_MARKET | — (Tatooine) | 500–1500 | 0.20 | — | (local) |
| interplan | BLACK_MARKET | nar_shaddaa | 1500–3000 | 0.30 | 0.15 | nar_shaddaa_dock/orbit |
| **spicerun** | CONTRABAND | **geonosis** | 3000–6000 | 0.55 | **0.50** | geonosis_dock/orbit |
| **corerun** | SPICE | **coruscant** | 4000–8000 | 0.65 | **0.60** | coruscant_dock/orbit |

---

## 2. Validation (sandbox)

- **AST / py_compile:** clean on all 3 files (and on the staged zip copies).
- **Runtime:** confirmed both top-tier routes resolve to real CW dock zones via the live graph (`spicerun→geonosis_dock/orbit`, `corerun→coruscant_dock/orbit`); heat gradient intact.
- **Residual grep:** no active kessel/corellia references remain in the 3 files (only the 2 intentional keeps above).
- **Targeted tests (pytest 8.4.2 + pytest-asyncio 1.4.0, matching `requirements.txt`):** `test_b1g_tail_display_strings`, `test_economy_validation` (45), `test_session57b_space_umbrellas`, `test_b1b1_organizations_constants_era_aware`, `test_kd5b_sweep_npc_space_traffic`, `test_session57a_ship_expansion` — **all pass.** (Earlier sandbox errors were missing deps — pytest-asyncio, bcrypt — not code defects; installed and re-run green. One pre-existing RNG `UserWarning` in the survey-cooldown test is unrelated.)
- **Ground truth still pending on your Windows box:** full `run_all_tests.bat` / ~4,854-test suite. Recommend a quick in-client smoke too: pick up a `spicerun`/`corerun` job and fly it — confirm arrival/dropoff now resolves at Geonosis/Coruscant instead of dead-ending.

---

## 3. Pre-flight scope discovery — corrects our agreed defaults

The audit pre-flight overturned two assumptions baked into the plan we approved. **Acting on them blind would have created new bugs**, so they are deliberately *not* in this drop:

1. **Lira Shan is NOT a Corellia/Nar Shaddaa NPC.** The CW worldbuilding establishes her as **the KDY broker on Kuat, explicitly reserved for the "From Dust to Stars" quest** (`npcs_drop_def_civilians.yaml`: "Lira Shan reserved for FDtS"; `npcs_drop_g1_nar_shaddaa_topside.yaml`: "Lira Shan [Kuat-only, not here]"; cross-references in `npcs_drop_g2`). The generic Kuat broker civilian was deliberately seeded as *not* Lira Shan. So the previously-approved "relocate Lira → Nar Shaddaa" was **wrong**, and she may not be seeded as a walkable NPC at all. → **Decision needed** (§4, 0a-2).
2. **Venn Kator is seeded on Tatooine at Docking Bay 94** (`build_tutorial.py`), not Corellia. So `spacer_quest.py`'s "Venn Kator on Corellia" is stale; the correct target is Tatooine — verifiable, no decision needed, but it belongs with the rest of the quest migration (0a-2) to keep that file internally consistent.

The residue is also **wider** than the space/smuggling layer:
- **`engine/spacer_quest.py`** — starter-ship quest still references Lira/Corellia (ship purchase climax), Venn/Corellia, Zekka Thansen "Corellian Sector," a "land on Kessel + Corellia" objective, and trade hints ("Corellia sells luxury").
- **`parser/spacer_quest_commands.py`** — the tutorial-passenger `travel` map (`_DOCKING_NAME_FRAGMENTS` / `_LANDING_NAME_FRAGMENTS`) still lists kessel/corellia rooms.
- **`engine/tutorial_v2.py`** — **multiple full quest chains** built on `planet_land_kessel` / `planet_land_corellia` triggers, `smuggling_complete_kessel`, and target rooms that don't exist in CW ("Kessel - Black Market Tunnel," "Corellian Slice Cantina," etc.), plus "Coronet City is officially Imperial territory" copy. This is a content migration, not a sweep.
- **`engine/housing.py`** — `("empire", N)` Imperial home types, `("empire","corellia")`/empire HQ-room mappings, kessel/corellia planet home + shop + viewport flavor, an `"empire"` Imperial-Outpost building template, and "Imperial security/surveillance" lock/theft flavor.
- **`engine/organizations.py`** — the `_SPEC_CONFIG_BY_FACTION["empire"]` block (the `T2.CW.spec_config_cleanup` TODO), plus the `empire` enmity/pay entries, the `IMPERIAL_SPEC_EQUIPMENT` dict, and the Imperial equipment defs (stormtrooper_armor, e11, TIE pilot suit, etc.).
- **Confirmed safe to leave:** `engine/npc_space_traffic.py::_GCW_ZONES` (intentional GCW fallback) and `engine/missions.py:72` (a comment documenting the migration).

---

## 4. Deferred follow-ons (scoped)

- **Drop 0a-2 — Starter-quest CW migration (`spacer_quest.py` + `parser/spacer_quest_commands.py`), DECISION-GATED.**
  Blocking question: **which broker sells the starter ship, and where?** Options: (a) use Lira Shan on **Kuat** and seed her there, accepting overlap with FDtS's reservation; (b) introduce/seed a **non-canon Kuat KDY broker** (the def_civilians file already anticipates this) and leave Lira Shan to FDtS; (c) move the purchase to a **Nar Shaddaa** smuggler-broker for onboarding simplicity. Once chosen, I fix the whole quest in one pass: relocate the purchase NPC, set Venn Kator → Tatooine (Docking Bay 94), rewrite the "land on 4 planets" objective to CW worlds (tatooine, nar_shaddaa, + 2 of kuat/geonosis/coruscant — all have verified landing rooms), update the travel map + hints, and de-Imperialize the dialogue.
- **Drop 0a-3 — `tutorial_v2.py` quest-chain migration.** Larger content pass: re-point each kessel/corellia chain to CW destinations with verified target rooms, and migrate the `planet_land_*` / `smuggling_complete_*` triggers + handlers. Needs a per-chain destination/room mapping (I'll propose one for sign-off).
- **Drop 0a-4 — `housing.py` + `organizations.py` Imperial/empire residue sweep.** Remove the empire home/shop/building/equipment/spec blocks (incl. `T2.CW.spec_config_cleanup`). Low-risk but should verify a Republic equivalent exists for each empire entry before deletion (most do, per the "mirrors the Imperial …" comments).

---

## 5. Important flags

- **The starter-ship quest is NOT end-to-end functional after this drop.** Its travel and landing infrastructure to CW worlds is now sound, but the **ship-purchase climax (Lira step) is still broken** until 0a-2. Don't advertise the starter quest as fixed yet.
- **Wider starmap era-residue is only partially addressed.** `HYPERSPACE_LOCATIONS` in `space_commands.py` is now CW-clean, but other off-era references across the codebase (the broader `T2.CW.codebase_era_sweep`) remain out of scope here.
- **No income risk in this drop.** It restores already-intended faucets that were *suppressed/broken* (dead-ended) to their design level; it does not raise income above design intent. The trade-goods re-map (`trading.py`, Drop **0b**) — which *does* re-open 7 routes — remains gated behind the ledger (Drop 1) + sink (Drop 3) per the hard ordering rule.

---

## 6. Next action

Awaiting your call on **0a-2's broker decision** (§4, options a/b/c) to proceed with the starter-quest migration. In parallel I can take **0a-4** (housing/org sweep — no decision needed) or draft the **0a-3** per-chain mapping for your sign-off. Your pick.
