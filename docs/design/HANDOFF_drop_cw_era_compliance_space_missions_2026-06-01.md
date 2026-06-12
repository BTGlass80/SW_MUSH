# HANDOFF — CW era-compliance: space catalog, zone authority, faction missions

**Date:** 2026-06-01
**Apply:** `Expand-Archive -DestinationPath . -Force` (root-mirrored zip)
**Zip:** `SW_MUSH_drop_cw_era_compliance_space_missions_2026-06-01.zip`

---

## TL;DR

An external audit reported "we never wired in CW space and it's still GCW."
That was **half right**: the *plumbing* was already Clone Wars (active_era =
clone_wars, era-aware ship loader, all 14 CW hulls live), but the *content*
flowing through it was still Galactic Civil War — TIE-fighter patrols, Imperial
hails, an Empire/Rebellion faction board, and the GCW zone graph. This drop
makes the **space and missions subsystems** CW-compliant.

It does **not** claim the whole codebase is CW-clean — see "Scope boundary"
below. Two follow-up items are tracked in TODO.

---

## The four fixes

### A — Ship registry era-cleanliness (`engine/starships.py`, `parser/space_commands.py`)
The always-loaded base catalog `data/starships.yaml` is GCW; the CW overlay was
layered on top but never *removed* the GCW hulls, so all 10 era-breaking ships
(TIE fighter/interceptor/bomber, X/A/B-wing, Imperial Star Destroyer,
Nebulon-B, Lambda, Sentinel) were live and `@spawn`-able. The CW overlay even
authored an `excluded_global_keys` list naming them — but it was wired to
nothing, and `registry_hints` itself loaded as a junk "ship template."
- New `ShipRegistry.apply_era_hints(era_path)` drops the `registry_hints`
  pseudo-template and removes every hull in `excluded_global_keys`.
- `get_ship_registry()` calls it after loading the overlay.
- Result: registry goes 34 → 23 templates (10 GCW hulls + 1 junk key gone), all
  14 CW hulls and 9 era-agnostic allowed hulls (YT-1300, Z-95, Y-wing,
  Firespray, etc.) retained.
- `@spawn` help examples changed from `x_wing Red Five` / `yt_1300 Millennium
  Falcon` to `arc_170 Gold Leader` / `yt_1300 Wayward Star`.

### B — CW zone graph wiring (`engine/npc_space_traffic.py`, `space_zones.yaml`, `missions.py`, `smuggling.py`)
The engine hardcoded a GCW zone graph (Tatooine/Nar Shaddaa/Kessel/Corellia,
generic `outer_rim_lane_*`). A fully-authored CW graph
(`data/worlds/clone_wars/space_zones.yaml` — 24 zones, all six launch planets,
canonical lanes) sat **inert** ("this file is inert at runtime").
- Hardcoded graph renamed to `_GCW_ZONES` / `_GCW_SPAWN_ZONES` /
  `_GCW_BAY_PLANET_MAP` — now the GCW-era fallback.
- New `_load_zone_graph()` loads the live `ZONES` / `SPAWN_ZONES` /
  `BAY_PLANET_MAP` from `space_zones.yaml` for the active era, GCW fallback
  otherwise. `reload_zone_graph()` added for era-flip tests.
- New `authority` field on the `Zone` dataclass + on all 24 CW zones
  (republic ×12, hutt ×7, cis ×4, contested ×1), per the file's own prose.
- `missions.py` `_PATROL_ZONES`/`_SURVEY_ZONES`/`_INTERCEPT_ZONES`/
  `_ESCORT_ROUTES` and `smuggling.py` `PLANET_DOCK_ZONES` now **derive from the
  live graph** instead of naming dead GCW zone ids (kessel/corellia/
  outer_rim_lane_*), so they follow the era automatically.

### C — Zone-based patrols + flavor (`npc_space_traffic.py`, `encounter_patrol.py`, `encounter_anomaly.py`, `smuggling.py`, `smuggling_commands.py`)
Per your "by zone — Republic in Rep space, CIS at Geonosis, Hutt enforcement at
Tatooine/Nar Shaddaa" decision.
- The single global PATROL template (`tie_fighter`, "Imperial Patrol TK-{n}" /
  "ISB Patrol", captain "Lieutenant Varsk") became
  `PATROL_TEMPLATES_BY_AUTHORITY` + `_pick_patrol_template(zone)`: Republic →
  ARC-170 (clone/Judicial names), CIS → Vulture droid (droid designations),
  Hutt → Z-95 (cartel names), contested/neutral → Consular cruiser (Sector
  Customs).
- `_spawn` and the `encounter_patrol` combat-promotion both select the patrol
  hull by the spawn zone's authority (no more `tie_fighter`).
- Hail + boarding-inspection text is authority-aware (`_patrol_authority_label`,
  `_default_patrol_name`, `_board_party`): "Republic Navy patrol" / "Clone
  troopers", "Separatist patrol" / "B1 battle droids", "Hutt cartel customs" /
  "Cartel enforcers", neutral "sector customs."
- Anomaly dead-drop strings: "[IMPERIAL DEAD DROP]" / "Imperial cipher" /
  "Imperial distress beacon" → "[ENCRYPTED DEAD DROP]" / "Separatist cipher" /
  "Encrypted distress beacon" (handler keys + outcomes kept as internal ids).
- Smuggling patrol-encounter + arrival-customs strings de-Imperialized
  ("customs patrol"); contraband "classified Imperial schematics" →
  "classified Separatist schematics."
- Landing customs (`space_commands.py`) now triggers via
  `_planet_has_customs(planet)` (derived from zone authority) instead of a
  hardcoded `{"tatooine", "corellia"}` Imperial set.

### D — Faction missions + spacer quest (`missions.py`, `spacer_quest.py`)
`FACTION_MISSION_CONFIG` is now exactly the **five canonical CW slugs** from
`data/worlds/clone_wars/organizations.yaml`: `republic`, `cis`, `jedi_order`,
`hutt_cartel`, `bounty_hunters_guild`. Each points at an era-clean objective
table (`_CW_LAWFUL_OBJECTIVES`, `_CW_INSURGENT_OBJECTIVES`, `_HUTT_OBJECTIVES`,
`_BH_GUILD_OBJECTIVES`).
- Removed the legacy `empire`/`rebel`/`hutt`/`bh_guild` keys and the
  `_EMPIRE_OBJECTIVES`/`_REBEL_OBJECTIVES` tables entirely (you chose A2 —
  commit fully to CW, no GCW keys retained). Characters with stored legacy
  codes migrate to CW slugs on login via `organizations.apply_org_rewicker`
  (the `legacy_rewicker` map: empire→republic, rebel→cis, hutt→hutt_cartel,
  bh_guild→bounty_hunters_guild).
- **Note on a bug this fixed:** an earlier in-session edit had created
  *duplicate* `republic`/`cis` keys (a blind rename collided with a pre-existing
  CW block), leaving shadowed entries + two redundant objective tables. This
  drop reverts that collision; the config is now single, canonical, no dupes.
- `jedi_order` uses the lawful objective shape with Council-flavored givers
  (Jedi Knight, Padawan, Temple liaison) and COMBAT/INVESTIGATION/DELIVERY
  types — no smuggling/bounty (Jedi don't run mercenary jobs).
- Spacer-quest completion banner triad "Rebel Cell · Imperial Service ·
  Underworld" → "Republic Service · Separatist Contracts · Underworld"; the
  "not just the Empire" and "Empire and the Rebellion" dialogue → Republic /
  Confederacy.

---

## Files in this zip (15)

| Path | Change |
|------|--------|
| `engine/starships.py` | A: `apply_era_hints` + registry wiring |
| `engine/npc_space_traffic.py` | B+C: YAML zone loader, `authority`, per-authority patrols, hail/boarding flavor |
| `engine/encounter_patrol.py` | C: authority-aware patrol labels + promotion hull |
| `engine/encounter_anomaly.py` | C: de-Imperialized dead-drop strings |
| `engine/spacer_quest.py` | D: banner triad + dialogue |
| `engine/smuggling.py` | B+C: dock zones from graph, de-Imperialized patrol strings, contraband |
| `engine/missions.py` | B+D: mission zone pools from graph; canonical CW faction config; legacy keys/tables removed |
| `parser/space_commands.py` | A+C: `@spawn` examples; `_planet_has_customs` |
| `parser/smuggling_commands.py` | C: customs arrival string |
| `data/worlds/clone_wars/space_zones.yaml` | B: `authority` on all 24 zones |
| `tests/test_b1e_missions_era_aware.py` | D: removed obsolete GCW-regression tests (now CW-only contract) |
| `tests/test_session38.py` | D: faction codes → canonical CW |
| `tests/test_session49_faction_missions.py` | D: faction codes → canonical CW |
| `CHANGELOG.md` | this drop's entry (newest) |
| `TODO.json` | +2 follow-up items, `last_updated` bumped |

---

## Verification (sandbox)

- `py_compile` clean on all 9 source files.
- **Core batch: 89 passed** — `test_b1e_missions_era_aware` (17),
  `test_session38` (32), `test_session49_faction_missions` (20),
  `test_cw_ships` (20).
- **Broader space regression batch: 149/150 passed** —
  `test_kd5b_sweep_npc_space_traffic`, `test_session46_encounter_dispatch`,
  `test_q1_chains_and_traffic`, `test_f8c2b3_chain_missions`,
  `test_session57b_space_umbrellas`, plus `test_session38`.
- Codebase sweep: **no** remaining references to the removed mission keys
  (`empire`/`rebel`/`hutt`/`bh_guild` as `FACTION_MISSION_CONFIG` keys) or the
  deleted objective tables (`_EMPIRE_OBJECTIVES`/`_REBEL_OBJECTIVES`/
  `_REPUBLIC_OBJECTIVES`/`_CIS_OBJECTIVES`) anywhere in engine/parser/tests.

### ⚠️ One known failure — pre-existing flake, NOT from this drop
`tests/test_session38.py::TestTextureEncounterTick::test_security_scaling`
fails ~4 of 5 runs (passed 1/5 on re-run). It's a **probabilistic** test
(compares random encounter trigger counts: lawless should exceed secured; saw
27 vs 29) in `texture_encounter_tick` / `space_encounters` — a subsystem this
drop does **not** touch. It has no RNG seed, so it flakes on its own. Left as a
separate fix rather than folded in (it'd be scope creep). Flag for a future
"seed the flaky encounter-scaling test" cleanup.

**Your Windows `run_all_tests.bat` (~4,854 tests) is ground truth.** The sandbox
ran only the affected modules + neighbors, per the usual split. The one thing
the sandbox can't do is render — if you want to *see* an ARC-170 Republic
patrol hail in-game, that's a browser/telnet check on your box.

---

## ⚠️ Scope boundary — what is NOT in this drop

You chose to draw the line at space + missions and ship now. Two CW-compliance
items remain, tracked in TODO.json:

1. **`T2.CW.spec_config_cleanup`** — `engine/organizations.py`'s
   `_SPEC_CONFIG_BY_FACTION` still has a live `empire` chargen block
   (stormtrooper, tie_pilot) alongside the parallel `republic` block. The
   login rewicker should make it unreachable, but it's still GCW content in
   source. Decide delete-vs-repoint (mirror the A2 missions decision).
2. **`T2.CW.codebase_era_sweep`** — no full codebase-wide Imperial/Rebel/TIE
   sweep has been run outside space+missions. Suspects: chargen templates,
   equipment, NPC seeds, help text, the Director axis (note: director-axis
   `imperial`/`rebel` codes are a *separate* rewickered namespace — verify
   before touching).

So: the space and missions subsystems are CW-compliant and tested. "Fully CW
compliant codebase-wide" is **not** yet a claim this drop supports — those two
items close the gap.

---

## CHANGELOG / TODO regeneration caveat

`CHANGELOG.md` and `TODO.json` were edited from the session-start upload
baseline. `Expand-Archive -Force` overwrites, so this is clean only if you
haven't hand-edited those two since this morning's upload. If you have, extract
this zip's copies to a temp dir and merge the one new CHANGELOG entry + the two
new TODO items by hand. The 13 code/test/data files are safe to `-Force`
regardless.
