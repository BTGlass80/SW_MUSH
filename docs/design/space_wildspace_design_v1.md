# Space Wildspace Design Document
## SW_MUSH · Clone Wars Era · April 27, 2026

---

## 1. Overview

Ground wilderness (`wilderness_system_design_v1.md`) gives players a content-sparse, event-dense place to log in and grind without RP obligation. This document is the space-side counterpart for the Clone Wars era: dedicated branch zones hanging off existing deep_space zones where the activity is salvage, mining, and faction-cache hunting, and where the Director and NPC traffic systems are explicitly tuned to *not* generate social hooks.

There are **two distinct theaters**, sharing the same engine but differing in flavor, faction stakes, and content:

- **Sieges Theater** — active and recent Clone Wars battle debris. Republic vs. CIS faction tension. Drifting munitions, droid wreckage, downed Jedi recovery beacons. Hazardous and faction-loaded.
- **Hutt Frontier** — lawless smuggling periphery beyond Tatooine and Nar Shaddaa. Derelict freighters, contraband caches, BHG dead-drop targets. Criminal-flavored and morally murky.

Republic, CIS, and Jedi PCs grind the Sieges Theater. Hutt Cartel, BHG, and Independent PCs grind the Hutt Frontier. Players can grind across the dividing line, but cache-visibility rules mean their faction won't have hidden content waiting for them on the other side.

**What it is:**

- A place to grind salvage, mining yields, credits, and faction rep on a predictable loop
- A faction-cache hunting environment with role-locked content (only Jedi see the recovery beacons, only BHG sees the bounty dead drops, etc.)
- A test bed for the equipment progression layer (mining laser, salvage arm, refinery) without which space gear is purely cosmetic
- A clean home for the "I just want to play, not roleplay" archetype

**What it is not:**

- A new combat layer or new range-band system — existing space combat is unchanged
- A coordinate grid — space stays zone-based; the v3 Space Overhaul argument against grids still holds
- A replacement for the existing space encounter system — encounters are still seasoning in the *non*-wildspace zones; wildspace just doesn't seed them
- A mission-board content type — the mission board does not route players to wildspace zones

---

## 2. Design Principles

**1. Branch zones, not overload.** Wildspace zones are *new* zones that connect to existing deep_space zones via the adjacency graph. Existing deep_space zones keep their current dual role as transit corridor and encounter zone. We do not retune Tatooine Deep Space to suddenly be a grind zone.

**2. Two theaters, shared mechanics.** Sieges and Hutt Frontier use the same cache table, the same equipment layer, and the same encounter framework. They differ in YAML content, faction visibility tables, and atmospheric tone — not in code.

**3. Cache visibility is the faction hook.** Every wildspace zone has a population of caches. Most caches are universally visible (asteroid clusters, generic salvage). Some are *faction-tagged* — only PCs of the right faction get them rendered in scan output. This is the direct analog to ground wilderness landmark visibility.

**4. Director-mute by zone flag.** A new `wildspace: true` flag in the zone definition tells the Director and NPC traffic systems to skip these zones for narrative encounter seeding, friendly traffic spawns, and mission-board targeting. This is a tuning layer, not a new system.

**5. Equipment progression rewards repeat play.** A player with stock salvage and no mining laser can still grind these zones, but slower. A player who's invested in Mining Laser II and a Refinery harvests roughly 2× faster. This is the carrot for sticking with it.

**6. Telnet-first, web-enhanced.** Wildspace zones must work on raw telnet — `scan`, `mine`, `salvage`, `harvest cache <id>`. The web client gets a panel showing cache density and yield projections. Text is canonical.

**7. CW-flavored, not GCW-rewicked.** All cache content, NPC encounters, and atmospheric flavor reference Clone Wars factions and events. No "Imperial dead drops," no "Rebel supply caches." This is a CW-native design.

**8. Parallel-shippable to ground wilderness, but pattern-dependent.** The faction-cache *visibility* mechanic should be designed and shipped first in ground wilderness; space wildspace inherits the pattern. See §10 for how this gets memorialized in the architecture doc so we don't accidentally ship space wildspace with a different cache visibility model.

---

## 3. Zone Layout

Four new zones, two per theater, branching off existing deep_space zones in the CW galaxy graph.

### 3.1 Sieges Theater

#### 3.1.1 Geonosis Front (`geonosis_front`)

**Branches off:** `geonosis_deep_space`
**Security:** LAWLESS (PvP unrestricted, NPC aggro frequent)
**Hazard:** MEDIUM — drifting munitions, mine fields from recent skirmishes
**Theme:** Active CIS-Republic skirmish frontier. Recent battle debris. CIS patrol presence is constant; Republic counter-patrols sweep through irregularly.

The most recent fighting in the Geonosian sector. Wreckage is fresh, droid platoons may not be fully dead, and CIS supply convoys still occasionally transit through. Republic Pathfinder squadrons have planted recovery beacons for downed Jedi pilots that haven't been recovered.

**Cache pool:**
- *Universal:* droid scrap clusters, munitions debris (raw ore equivalent), drifting hull plating
- *Republic-visible:* downed clone trooper survival pods (rep + creds), Republic supply drops
- *CIS-visible:* CIS recovery markers, intact battle droid platoons (salvage as parts)
- *Jedi-visible:* Jedi recovery beacons (kyber crystal fragments, lightsaber components, big rep)
- *BHG-visible:* deserter clone bounty dead drops (BHG contract bait)

**Encounter pool (hostile only — no friendlies, no chatter):**
- Stray droid fighter packs (vulture droids, tri-fighters)
- Damaged CIS frigate playing dead (false derelict — fights when approached)
- Republic patrol intercept (aggressive to non-Republic, polite-to-hostile to Republic)

#### 3.1.2 Outer Rim Sieges Drift (`outer_rim_sieges_drift`)

**Branches off:** `outer_rim_lane_2` (the Tatooine ↔ Nar Shaddaa lane)
**Security:** LAWLESS
**Hazard:** LOW — older debris, settled into stable drift orbits
**Theme:** Older battle debris, post-skirmish, neither side actively contesting. The forgotten battlefield. Big derelicts, picked-over but still rewarding for the patient.

This is where ships go when their war is over. Hulks of Republic frigates, scuttled CIS supply transports, the occasional fully intact escape pod nobody ever recovered. Patrol presence is minimal — both sides moved on.

**Cache pool:**
- *Universal:* large derelict hulks (multi-stage salvage), drifting cargo containers
- *Republic-visible:* mothballed Republic supply caches (medical, rations, military gear)
- *CIS-visible:* abandoned CIS field HQs (tactical data, CIS tech schematics)
- *Jedi-visible:* lost Jedi artifact beacons (Force-attuned items, fragment holocrons)
- *Hutt-visible:* Hutt salvage claims (pre-marked wrecks; harvesting yields rep + creds)
- *Independent-visible:* nothing extra — pure salvage play

**Encounter pool:**
- Pirates (low aggression — they're scavenging too)
- Drifting broken droid wreckage that reactivates if disturbed
- BHG hunter on a deserter trail (passes through, doesn't engage non-targets)

### 3.2 Hutt Frontier

#### 3.2.1 Jundland Drift (`jundland_drift`)

**Branches off:** `tatooine_deep_space`
**Security:** LAWLESS
**Hazard:** LOW — light asteroid drift
**Theme:** The asteroid drift past Tatooine's outer ring. Hutt smuggling staging area. Independent freighter graveyard. Where ships go to disappear.

**Cache pool:**
- *Universal:* asteroid mineral clusters (mining-laser optimized), abandoned freighter wrecks
- *Hutt-visible:* Hutt-marked smuggling caches (spice, weapons, contraband)
- *BHG-visible:* fugitive ship wreckage with bounty markers, BHG dead-drop intel caches
- *Independent-visible:* spacer mutual-aid caches (small but reliable)
- *Republic-visible:* nothing — they don't operate here
- *CIS-visible:* nothing — too far from the front

**Encounter pool:**
- Pirate skiffs (aggressive, fast)
- Hutt Cartel collector ship (hostile to non-Hutt-aligned)
- Rogue freighter playing dead (false derelict)

#### 3.2.2 Smuggler's Run Periphery (`smugglers_run_periphery`)

**Branches off:** `nar_shaddaa_deep_space`
**Security:** LAWLESS
**Hazard:** MEDIUM — sensor-jamming nebula clouds, Hutt orbital mines
**Theme:** The unofficial back-route trade lanes the Hutts use to dodge Republic inspection. Heavy Hutt presence, but they tax rather than fight if you've got cred with them.

**Cache pool:**
- *Universal:* drifting cargo crates from rushed-jump dumps, pirate prize wrecks
- *Hutt-visible:* premium Hutt caches (better yields, in jamming pockets — needs higher Sensors)
- *BHG-visible:* high-value bounty bait (top-tier dead drops)
- *Independent-visible:* smuggler stash caches (mid-tier)
- *Republic-visible:* nothing
- *CIS-visible:* nothing — Republic-CIS war doesn't run through Hutt Space

**Encounter pool:**
- Hutt enforcers (hostile to non-Hutt; protection-rackets non-Hutt PCs)
- Rival smuggler contesting your salvage
- Sensor-blind ambush by pirate wing

### 3.3 Zone Graph Updates

The CW zone graph (in `engine/npc_space_traffic.py` `ZONES` dict per the world-extraction refactor, this lives in YAML) gains four entries:

```python
"geonosis_front": Zone("Geonosis Front", DEEP_SPACE,
    planet=None, adjacent=["geonosis_deep_space"],
    wildspace=True, wildspace_theater="sieges"),
"outer_rim_sieges_drift": Zone("Outer Rim Sieges Drift", DEEP_SPACE,
    planet=None, adjacent=["outer_rim_lane_2"],
    wildspace=True, wildspace_theater="sieges"),
"jundland_drift": Zone("Jundland Drift", DEEP_SPACE,
    planet=None, adjacent=["tatooine_deep_space"],
    wildspace=True, wildspace_theater="hutt_frontier"),
"smugglers_run_periphery": Zone("Smuggler's Run Periphery", DEEP_SPACE,
    planet=None, adjacent=["nar_shaddaa_deep_space"],
    wildspace=True, wildspace_theater="hutt_frontier"),
```

Adjacency is one-way-back: from a wildspace zone you can return to its parent deep_space zone, but not skip across to the other wildspace. This keeps the graph readable and forces transit through "civilized" space between theaters.

---

## 4. Cache System

### 4.1 Cache Definition

Each wildspace zone has a cache pool defined in YAML. Schema:

```yaml
zones:
  geonosis_front:
    cache_pool:
      - id: droid_scrap_cluster
        kind: mining
        yield_table: droid_scrap
        visibility: universal
        respawn_minutes: 45
        density: 6   # avg number active in zone at once

      - id: jedi_recovery_beacon
        kind: faction_cache
        yield_table: jedi_beacon_loot
        visibility: [jedi_order]
        respawn_minutes: 180
        density: 1
        rep_reward: {jedi_order: 5}

      - id: clone_survival_pod
        kind: faction_cache
        yield_table: republic_supply_minor
        visibility: [republic]
        respawn_minutes: 90
        density: 2
        rep_reward: {republic: 2}
```

**`visibility`** values:
- `universal` — every PC sees it on scan
- `[faction_a, faction_b, ...]` — only PCs with positive rep with one of these factions sees it
- `hidden` — never on scan; only revealed via specific encounter or mission outcome (used sparingly)

**`kind`** values:
- `mining` — node persists through harvest, depletes on cooldown, mining laser optimized
- `faction_cache` — one-shot reward, consumed on harvest, respawns elsewhere in zone
- `derelict` — multi-stage salvage (large hulk, several harvests before consumed)

### 4.2 Scan Resolution

When a PC enters a wildspace zone and runs `scan`, the cache renderer:

1. Pulls the active cache instances for the zone from `space_caches`.
2. For each cache, evaluates visibility against the PC's faction memberships and rep scores.
3. Returns visible caches in scan output, with cache ID and rough kind hint.

A PC scans for caches more than once at no cost — visibility is the gate, not an action economy. The point of these zones is *grinding*, not skill-checking your way to content.

`deepscan` (existing) reveals cache yield estimate (e.g., "10-15 units of metal scrap, 1-2 rare components") for caches the PC can already see. This is the reward for investing in Sensors.

### 4.3 Harvest Commands

Three commands cover the loop:

- **`mine <cache_id>`** — for `kind: mining` caches. Uses Pilot + Mechanical, modified by Mining Laser mod tier. Yields raw resources. Cache enters cooldown.
- **`salvage <cache_id>`** — for `kind: derelict` caches. Uses Technical, modified by Salvage Arm mod tier. Yields components, schematics, rare drops. Hulk depletes after 3-5 harvests.
- **`harvest <cache_id>`** — for `kind: faction_cache` caches. Uses no skill check (it's a marker, not a challenge). Yields the configured loot + rep. Cache disappears, respawns elsewhere on cooldown.

All three commands display a "requires web client" message on Telnet for the cache list visualization but the harvest action itself works on raw telnet via the cache ID.

### 4.4 Faction Rep Interaction

Cache visibility checks a single rep threshold: PC must have rep ≥ 0 (i.e., not actively negative) with at least one faction in the visibility list. Negative-rep faction members do *not* see those caches — if the Hutt Cartel hates you, you can't see Hutt caches even in Hutt territory.

Rep rewards from cache harvests are small (1-5 per cache) so the loop doesn't replace mission/quest rep gains as the primary progression path. Wildspace is *supplementary* faction grinding, not the main driver.

---

## 5. Equipment Progression

Three new ship mods, slotted into the existing `mod_slots` system. Each mod occupies one slot.

### 5.1 Mining Laser

**Tier 1 — Mining Laser Mk1**
- Cost: 4,500 cr
- Effect: +2D to mining-related Pilot/Mechanical checks. Reduces mining cache cooldown by 25%.
- Crafting: requires `metal_scrap × 12`, `power_cell × 4`, schematic from Kuat shipwrights.

**Tier 2 — Mining Laser Mk2**
- Cost: 12,000 cr (or upgrade Mk1 for 9,000 cr)
- Effect: +3D to mining checks. -40% cooldown. Unlocks "deep mining" — extracts an additional rare-resource roll on critical successes.
- Crafting: requires `metal_scrap × 24`, `power_cell × 8`, `rare_alloy × 2`, schematic from Geonosian black-market trader (Hutt Frontier reputation gates the schematic).

### 5.2 Salvage Arm

**Tier 1 — Reinforced Salvage Arm Mk1**
- Cost: 5,200 cr
- Effect: +2D to salvage Technical checks. +1 component recovery per successful salvage.
- Crafting: standard parts available from any Kuat shipwright.

**Tier 2 — Reinforced Salvage Arm Mk2**
- Cost: 14,000 cr (or upgrade Mk1 for 10,500 cr)
- Effect: +3D to salvage. +2 component recovery. Unlocks "intact extraction" — chance to recover schematics from large derelicts.
- Crafting: needs Republic Engineering Corps connection (Republic-rep gated) for schematic access.

### 5.3 Onboard Refinery

**Refinery Module — single tier**
- Cost: 8,500 cr
- Effect: Processes raw resources mid-flight at 2:1 ratio (raw → refined). Refined resources sell for 3× raw at any port and feed crafting recipes that require refined inputs. Eliminates the "fly back to base to refine" trip.
- Crafting: Kuat shipwright, no faction gate, but expensive components.

### 5.4 Equipment Sequencing Note

Sieges Theater zones reward Salvage Arm investment. Hutt Frontier zones reward Mining Laser investment (more asteroid clusters). Refinery is universally good. This gives PCs a reason to specialize their ship loadout based on which theater they prefer, without locking either theater behind any specific equipment.

---

## 6. Director and NPC Traffic Behavior

The "no RP hooks" feel is achieved through a small set of behavioral flags read from the zone definition. This is **not a new system** — it's a configuration layer over existing systems.

### 6.1 Director Behavior

When a zone has `wildspace: true`:

- **No proactive narrative encounters.** The Director's encounter-seed pass skips wildspace zones. Players still get encounters, but only from the existing space_encounter spawn tables (which are also retuned for wildspace — see §6.3).
- **No ambient social NPCs.** Wildspace zones are excluded from the trader/diplomat/courier ambient spawn pool.
- **No mission-board contracts route here.** When the mission generator picks a zone for a contract destination, wildspace zones are filtered out. Players can still find caches *like* mission rewards, but no NPC ever asks them to go fetch one.
- **Atmospheric Director output is muted.** The Director can still emit ambient flavor lines for these zones, but the line pool is "war debris drifts past your viewport," not "a mysterious figure hails you on local comm."

### 6.2 NPC Traffic Behavior

When a zone has `wildspace: true`:

- **No friendly traffic spawns.** Trader and friendly courier archetypes are excluded from spawn rolls.
- **Hostile traffic uses combat profiles, not dialogue profiles.** Pirates that appear here go straight to attack/demand rather than the standard hail-and-negotiate flow. They don't have anything to say to you. Bounty hunters still use targeted-hail flow but only for actual bounty targets.
- **Patrol-presence is theater-flavored.** Sieges Theater gets occasional Republic or CIS patrols. Hutt Frontier gets Hutt enforcers. No Imperial patrols (era-incorrect anyway), no friendly traders, no diplomatic envoys.

### 6.3 Encounter Tuning

The space encounter framework's `texture_encounter_tick` (`engine/director.py`) gets a wildspace branch:

- **Hostile-only encounter pool.** Wildspace encounter tables include only hostile or environmental encounters (pirate ambush, droid pack, sensor-jamming nebula). No "stranded ship asks for help," no "Imperial customs hail," no "mysterious distress signal that's actually a friendly NPC offering a quest."
- **Higher base rate.** Texture encounters fire at 2.5× the base rate in wildspace zones. The compensating factor is that they're all combat or hazard — players who can't handle combat shouldn't be here.

### 6.4 Configuration Knobs (memorialize in architecture doc — see §10)

These are new fields on the zone definition:

| Field | Type | Default | Effect |
|---|---|---|---|
| `wildspace` | bool | false | Master flag enabling all wildspace behaviors |
| `wildspace_theater` | string | null | "sieges" or "hutt_frontier" — selects content YAML |
| `friendly_traffic_density` | float | 1.0 | Multiplier on friendly NPC spawn rate (wildspace: 0.0) |
| `mission_board_targeting` | bool | true | Mission generator may select this zone (wildspace: false) |
| `director_narrative_seeding` | bool | true | Director may seed branching encounters here (wildspace: false) |
| `encounter_pool` | string | "default" | Encounter table key (wildspace: "wildspace_<theater>") |

---

## 7. Files Modified

| File | Changes |
|------|---------|
| `engine/npc_space_traffic.py` | New zone entries, `wildspace` and `wildspace_theater` fields on `Zone` dataclass; spawn-pool exclusions |
| `engine/space_anomalies.py` | Cache rendering merged into scan output; existing anomaly system unchanged |
| `engine/space_caches.py` | **NEW** — cache pool loader, cache instance state, harvest resolution |
| `engine/space_equipment.py` | **NEW** (or extend `engine/starships.py`) — Mining Laser / Salvage Arm / Refinery mod logic |
| `engine/director.py` | Wildspace branch in encounter-seeding pass; mute friendly archetypes |
| `engine/security.py` | All four new zones default to LAWLESS |
| `parser/space_commands.py` | New `mine`, `harvest` commands; existing `salvage` extended for wildspace caches |
| `data/worlds/clone_wars/zones.yaml` | Four new zone definitions |
| `data/worlds/clone_wars/wildspace/sieges.yaml` | **NEW** — Sieges Theater cache pools and encounter content |
| `data/worlds/clone_wars/wildspace/hutt_frontier.yaml` | **NEW** — Hutt Frontier cache pools and encounter content |
| `data/starships.yaml` | Three new mod definitions (Mining Laser Mk1/Mk2, Salvage Arm Mk1/Mk2, Refinery) |
| `db/database.py` | New `space_caches` table, helpers for cache state |
| `static/client.html` | Wildspace cache panel, theater badge in HUD |
| `sw_d6_mush_architecture_v37_consolidated.md` | Section additions per §10 below |

### Schema migration:

```sql
CREATE TABLE space_caches (
  cache_instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
  zone_key TEXT NOT NULL,
  cache_def_id TEXT NOT NULL,
  state TEXT NOT NULL,           -- 'available', 'cooldown', 'depleted'
  last_harvested_at INTEGER,
  next_available_at INTEGER,
  harvested_by_character_id INTEGER,
  harvest_count INTEGER DEFAULT 0,
  visibility_factions TEXT       -- JSON list of faction codes
);

CREATE INDEX idx_space_caches_zone ON space_caches(zone_key);
CREATE INDEX idx_space_caches_state ON space_caches(state);
```

Mod additions to `data/starships.yaml` are non-schema, just YAML data.

---

## 8. Drop Plan

### Drop 1 — Framework + Schema (engine + DB)

- `engine/space_caches.py` core (cache loader, instance state, visibility check)
- `space_caches` table migration
- Zone fields: `wildspace`, `wildspace_theater`, plus the four configuration knobs from §6.4
- Cache rendering merged into `scan` output (universal-only for now; faction visibility shipped in Drop 2)
- `mine` and `harvest` commands; `salvage` extension
- One throwaway test zone with universal-only mining caches to validate the loop

**Validation:** AST + module tests for `space_caches.py`. Brian runs full pytest externally.

### Drop 2 — Sieges Theater Content + Faction Visibility

- `data/worlds/clone_wars/zones.yaml` adds `geonosis_front` and `outer_rim_sieges_drift`
- `data/worlds/clone_wars/wildspace/sieges.yaml` cache pools, encounter pools, atmospheric flavor
- Faction visibility check shipped (rep ≥ 0 against any visibility-list faction)
- Director knobs honored (wildspace zones excluded from narrative seeding, friendly traffic, mission-board targeting)
- Sieges-flavored encounter pool

### Drop 3 — Hutt Frontier Content

- Two new zones (`jundland_drift`, `smugglers_run_periphery`)
- `data/worlds/clone_wars/wildspace/hutt_frontier.yaml` cache pools, encounter pools
- Hutt enforcer NPC traffic profile

### Drop 4 — Equipment Progression

- Three new ship mods in `data/starships.yaml`
- Mod effect logic in `engine/space_equipment.py` (or extension of `starships.py`)
- Mining Laser: skill bonus + cooldown reduction wiring
- Salvage Arm: skill bonus + recovery bonus wiring
- Refinery: in-flight resource conversion command (`refine <resource>`)
- Schematic gating: Mining Laser Mk2 requires Hutt-rep-gated schematic; Salvage Arm Mk2 requires Republic-rep-gated schematic

### Drop 5 — Web Client + Architecture Doc Update

- Web client wildspace panel (cache density, theater badge, equipment loadout summary)
- Architecture doc `v37_consolidated.md` updated per §10 below
- Director config doc updated to describe the `wildspace`-related zone knobs

**Total:** 5 drops, sequenced after the CW pivot ships. Drops 2 and 3 are content-parallelizable (different YAMLs). Drop 4 is independent of Drops 2/3. Drop 5 ties off.

---

## 9. Failure Modes & Mitigations

**Risk: Cache density is wrong.** Too sparse = boring grind, too dense = trivial farming and economy inflation. Mitigation: launch with conservative densities and instrument harvest events; tune via config in Drop 5 after observing playtester behavior. The cache table is config-driven (no code changes to retune).

**Risk: Faction-cache visibility creates resentment.** Independent and Republic PCs in Hutt Frontier see fewer caches than Hutt-aligned PCs. Mitigation: universal caches are 60-70% of total cache count; faction caches are the *bonus* layer, not the primary income. An Independent in Hutt Frontier still earns; a Hutt PC there earns ~25% more.

**Risk: Equipment progression gates content harder than designed.** A new player without mod cash can't grind effectively, killing the "log in and grind" promise. Mitigation: stock ship salvage works in wildspace at the existing salvage rates. Mods are accelerators, not gates. Verify in playtest that a fully unmodded ship can complete a 30-minute wildspace run profitably.

**Risk: Director behavior diverges between wildspace and regular zones in confusing ways.** A player expects encounters and gets none; thinks the system is broken. Mitigation: scan output for wildspace zones includes a one-line theater banner ("**SIEGES THEATER** — Active war debris field. Combat encounters likely; no friendly traffic.") so players know what they're walking into.

**Risk: PvP exploitation.** Lawless wildspace + PCs grinding solo = ganking opportunity. Mitigation: existing space PvP rules (LAWLESS = unrestricted) apply. This is *intentional* — risk-reward is part of the loop. New players should be warned via tutorial mention before they head to wildspace. PvP gankers are an organic part of the lawless space ecosystem; we don't engineer special protection.

**Risk: Theater split fragments playerbase.** Republic-aligned PCs never see Hutt-aligned PCs because they're grinding different zones. Mitigation: the dividing line isn't enforced — anyone can transit anywhere. Theater split is a *visibility* difference, not a zone-access gate. Cross-faction encounters in wildspace are possible and probably interesting (Republic PC in Hutt Frontier hunting bounty targets, Hutt smuggler in Sieges Theater scavenging war debris).

**Risk: Schema or zone-graph breakage when CW pivot lands.** Mitigation: this design assumes the CW world-extraction refactor (`world_data_extraction_design_v1.md`) has shipped. Wildspace zones are added through the same YAML loader path as all other CW zones — no special-case zone code.

---

## 10. Architecture Doc Memorialization Items

Two items must be added to `sw_d6_mush_architecture_v37_consolidated.md` before this design ships, so they don't get lost in the next architecture pass:

### 10.1 Ground Wilderness → Space Wildspace Pattern Dependency

**Add to architecture doc, in the wilderness/wildspace section:**

> **Faction-Cache Visibility Pattern (cross-cutting).** Both `wilderness_system_design_v1.md` (ground) and `space_wildspace_design_v1.md` (space) implement faction-tagged content visibility — landmarks (ground) and caches (space) that only render to PCs of the right faction. This pattern was designed first for ground wilderness and is inherited by space wildspace. **The implementations must share a single visibility resolution function** (proposed: `engine/faction_visibility.py::is_visible_to_character(content_visibility, character)`) so that future faction additions, era pivots, and rep-threshold rule changes only require one place to update. If space wildspace ships before ground wilderness for any reason, the visibility function must still be authored as the shared module — not duplicated.

### 10.2 Director "No RP Hooks" Configuration Knobs

**Add to architecture doc, in the Director AI section:**

> **Wildspace Configuration Knobs.** The Director AI and NPC Traffic systems support per-zone behavior modifiers that allow zones to opt out of narrative encounter seeding, friendly NPC ambient spawning, and mission-board targeting. The flags (`wildspace`, `friendly_traffic_density`, `mission_board_targeting`, `director_narrative_seeding`, `encounter_pool`) are read from zone definitions and consulted at every relevant Director and traffic-spawn pass. These exist to support designated grinding zones where social/RP content is suppressed by design. Any future system that generates proactive social encounters (e.g., new ambient archetypes, future faction-event seeders, anything with NPC-initiated dialogue) **must check these flags before targeting a zone.** Failing to check them re-introduces RP pressure into zones explicitly designed without it and breaks the player contract.

---

## 11. Open Questions

1. **Should wildspace zones count toward "discovered planets" or any progression tracking?** Recommendation: no. They're activity zones, not destinations. They show up in `course` output normally but aren't celebrated as discoveries.

2. **Do wildspace zones get atmospheric Director lines?** Recommendation: yes, but from a separate flavor pool. War-debris ambient lines for Sieges, smuggler-frontier ambient lines for Hutt Frontier. ~10 lines per theater authored at launch.

3. **Should Independent faction PCs get *any* faction-visible caches?** Recommendation: a small "Independent Spacers Mutual Aid" cache type in the Hutt Frontier (only). Independent characters don't get the rich faction-content layer, but they get a token stash so they don't feel completely shut out. Sieges Theater stays Independent-blind — that's the trade-off for not picking a side in a war.

4. **What happens if a PC's faction rep drops below 0 mid-grind?** Recommendation: cache visibility is checked at scan time. If they re-scan, the now-invisible caches just don't render. Already-targeted caches (the PC has an active `harvest <id>` command) complete normally. No retroactive locking.

5. **Should there be a "wildspace mission" type — repeating contract that pays for X harvests?** Recommendation: defer to v2. The point of wildspace is that you don't need a mission to justify being here. Adding contracts re-introduces some of the social pressure we're trying to avoid. Revisit if playtest shows players want progression structure beyond the cache loop itself.

6. **CIS-aligned PCs in Hutt Frontier — any visibility?** Recommendation: no. The Hutts are profiteering off both sides of the war but don't have a content layer keyed to CIS specifically. CIS PCs get the universal caches and that's it.

7. **Should Mining Laser Mk2 schematic gate be Hutt-rep or BHG-rep?** Resolved in §5.1 as Hutt-rep — the schematic comes from a Geonosian black-market trader, who fences through Hutt channels. BHG isn't really in the schematic-trading business per the BHG faction design.

8. **Capital ship interaction with wildspace?** Capital-scale ships in wildspace zones — do they grind here, or is this small-ship content? Recommendation: capital ships *can* enter wildspace zones but their cache yields are no better than light-freighter yields (the content is sized for small-craft economy). This is content for freighters, not Star Destroyers. Capital-ship content gets its own design later.

---

*End of Space Wildspace Design Document — v1*

*Prerequisites: CW pivot drops 0–11 (`clone_wars_era_design_v3.md`), world-extraction refactor (`world_data_extraction_design_v1.md`), ground wilderness drops 1–2 for the shared visibility module pattern.*

*References: `wilderness_system_design_v1.md`, `clone_wars_era_design_v3.md`, `clone_wars_director_lore_pivot_design_v1.md`, `space_overhaul_v3_design.md`, `npc_space_traffic_design_v2.pdf`, `economy_design_v02-1.md` (faction rep system), Star Wars Sourcebook 2nd Ed (WEG40093) Chapter 1 (Spacecraft Systems, Escape Pods), Galaxy Guide 6: Tramp Freighters (WEG40027) salvage and modification rules.*
