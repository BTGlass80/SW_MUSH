# SW_MUSH — Sourcebook Enrichment Roadmap & Implementation Plan
## Version 1.0 — June 3, 2026
## Purpose: Turn the eight completed WEG/WotC extractions into an actionable, sequenced build plan for enriching the live game with WEG-authentic content — never at the expense of fun or gameplay. This is the *what-to-build* companion to `sourcebook_extraction_roadmap_v1.md` (the *which-book-to-extract* roadmap). No development work is performed here; this is design-of-record for an upcoming implementation session.

---

## 0. How to read this

**Scope.** This doc synthesizes eight finished extractions against a symbol-level audit of HEAD
(`SW_MUSH_upload_20260603_1817.zip`). It answers one question: *of the era-translated source material
we already hold, what is worth building, in what order, and how does it wire into the systems that
already exist?*

**Distinction from the extraction roadmap.** `sourcebook_extraction_roadmap_v1.md` rates *which books
to OCR/translate*. That work is done for the eight books below. This doc is downstream: it assumes the
extraction is in hand and plans the **content/feature drops** that turn reference docs into live content.

**The eight source extractions this plan draws from:**
- `creatures_of_the_galaxy_extraction_v1.md` (CotG) — ~70 era-translated D6 beasts, biome-mapped
- `gundarks_personal_gear_extraction_v1.md` — the full WEG personal-gear catalog, normalized + era-translated
- `gg11_criminal_organizations_extraction_v1.md` — org taxonomy, criminal-occupation NPCs, gear, two design stubs
- `wretched_hive_extraction_v1.md` — venue schema + generator, d66 ambient table, NPCs, creatures, adventure seeds
- `hideouts_and_strongholds_extraction_v1.md` — 20 stronghold archetypes, NPC roster, quest seeds (+ a reference annex)
- `platt_smugglers_guide_extraction_v1.md` — concealment gear, forged-doc economy, contact/grudge models, origins
- `secrets_of_tatooine_extraction_v1.md` (SoT) — Tatooine setting/hazards/economy/day-night vocabulary, Mos Espa
- `geonosis_outer_rim_extraction_v1.md` — Geonosis + Kamino setting, interiors, wilderness, creatures, faction tension

**Governing rules (unchanged, apply to every lane):** B3 era-cleanness (zero Empire/Imperial/Rebel/TIE/
X-wing in production strings); Q1 canon-character policy (canonical figures referenced institutionally/
absence-framed, never named open-world NPCs); WEG = keep content *and* stats; WotC = setting/lore only,
re-stat to D6 from scratch.

**Status:** triage/sequencing approved. Recommended order: **A → B → (C or D) → E folded in → F as a later strategic bet.**

---

## 1. HEAD audit baseline (so nothing here is duplicated)

This section records what is **already built** on HEAD, so the implementation session never re-builds a
system that exists. Verified at symbol level.

**Already mature — do NOT rebuild:**

| System | Where (HEAD) | State |
|---|---|---|
| Crafting | `engine/crafting.py`, `data/schematics.yaml` (38 schematics), `data/weapons.yaml` (~two dozen entries incl. a little armor) | Full SWG-lite resource/schematic/experimentation engine; quality 1–100; experimentation breakdown-die (WEG40046 jury-rigging). All rolls via `perform_skill_check`. |
| Smuggling | `engine/smuggling.py` (CargoTier: standard/restricted/contraband/spice; customs patrol; lockdown heat), `engine/encounter_patrol.py` | Cargo-run loop is live and **already cites Platt's** — the WEG40141 `INFRACTION` ladder (Huttese fines, Con/hide/bluff/run paths) is implemented. |
| Faction reputation | `engine/organizations.py` (`REP_TIERS`, `REP_TIER_NAMES`, `get_faction_standing_context`, cross-faction penalties) | Live ("Faction Reputation Drop 1–6"). NPC dialogue injection by rep tier. |
| Wilderness harvest | `engine/harvest.py` (`YIELD_TABLE` keyed `(security, influence_tier)`, `compute_harvest_payout`, tax, skill margin, region quality) | Live. Real economy goods come out of it. |
| Wilderness substrate | `engine/wilderness_encounters.py`, `wilderness_loader.py`, `wilderness_movement.py`, `region_quality.py`; regions `dune_sea.yaml`, `coruscant_underworld.yaml` (+ `force_resonant_landmarks`, `uscru_fringe_brokers`) | Contestable substrate, graph movement, anomalies, territory all live. **Encounter roller fires narrative + records cooldown only — see §1 surprises.** |
| Director | `engine/director.py`, `data/worlds/clone_wars/director_config.yaml` | Influence/zone-baseline model; emits categories `rumor / opportunity / encounter / personal_quest`; per-planet `zone_baselines`. **No deterministic quest-template framework** — see §8. |
| World clock | `engine/world_time.py` (`TIMES_OF_DAY = day/dusk/night`, ~2 real hrs/game-day; room→zone→global resolution) | Generic cycle; renderer has no distinct dawn. **No planet-specific period vocabulary.** |
| NPC system | `engine/npc_loader.py` (`schema_version: 1`; `npcs: [{name, room, species, description, char_sheet:{attributes D-codes, skills, weapon, move…}, ai_config}]`), `engine/npc_generator.py` (archetypes incl. `creature`; `generate_npc`) | NPC templates are hand-placed by `room:`. A generator pool from a template file is the file-comment's own "future" note. |
| Player shops / cities / housing / orgs | `parser/shop_commands.py`; `engine/housing.py` (`shopfront_owner_id` — single owner); `player_cities.py`, `buildings.py`, `organizations.py`, `territory.py` | Live. Shops have a single owner; **no front/true-owner split.** |

**Two surprises that shape the plan:**

1. **No creature data file exists.** There is no `data/npcs_creatures.yaml`. The encounter system is
   ready to *reference* creatures, but the stat-block library is absent, and the encounter→spawner
   bridge is explicitly deferred: `wilderness_encounters.py` returns `fired=True` with `entry.narrative`
   and a `payload.npc_template`, and its own docstring says the actual spawn is dispatched "in a
   follow-up drop." So today even the existing `dune_sea.yaml` encounters (`tusken_warrior`, `dewback`)
   surface narrative only — they do not yet instantiate a creature. This is an
   infrastructure-complete-vs-content-complete gap, and it cleanly splits the creature lane (§3).

2. **B3 era-cleanness is not actually clean in the live game.** `engine/encounter_patrol._apply_infraction()`
   (≈ lines 564–604) hardcodes `[IMPERIAL BOARDING] Stormtroopers board for inspection` and
   `[IMPERIAL CUSTOMS]` strings — even though the same module already builds era-correct strings
   (`republic → "Republic Sector Patrol"`, `republic → "Clone troopers"`, `_board_party()`,
   `_default_patrol_name()`) that its *setup* path uses. A player who fails a customs check in the live
   Clone Wars game sees Imperial strings. Additional scattered surfaces exist (see §4). This is lane B.

---

## 2. Ranked lanes and recommended sequence

ROI is rated for a *live* system (fun + authenticity per unit of risk/effort), not for how good the book is.

| # | Lane | Source(s) | Net-new vs HEAD | Value | Effort | Risk |
|---|---|---|---|---|---|---|
| **A** | Creature library | CotG, Geonosis, Wretched Hive, SoT | Yes — no creature data exists | ★★★★★ | Low (data) + small Phase B | Low |
| **B** | B3 era-cleanness sweep | (audit finding) | Yes — live leak | ★★★★☆ (integrity) | Low | Low |
| **C** | Gear / crafting expansion | Gundark's, GG11, Platt's gear | Mostly (triples vocabulary) | ★★★★☆ | Med | Med (era landmines) |
| **D** | Geonosis & Kamino depth | Geonosis extraction | Yes (two thin launch worlds) | ★★★★☆ | Med–High (content build) | Low–Med |
| **E** | Small-wins trio | GG11, SoT, Wretched Hive | Yes | ★★★☆☆ each | Low/Tiny | Low |
| **F** | Director quest-template library | Wretched Hive, Hideouts, Geonosis, SoT, GG11, roadmap §4 | Yes — no template framework | ★★★★★ strategic | High (new framework) | Med |

**Recommended sequence and why:**

1. **A (creatures)** first — highest fun-per-risk, turnkey, lights up all six launch worlds, zero new
   mechanics in Phase A, no locked-decision collisions. The hard extraction work is already done.
2. **B (B3 sweep)** next — cheap, and you want it *before* the gear work (C) amplifies the era surface.
3. **C or D** — pick by appetite. C is broad (gear touches crafting/economy/security/combat) but
   era-landmine-heavy; D is deep for two specific worlds (Geonosis especially is thin today).
4. **E** — fold the small wins in opportunistically alongside A–D (they're tiny and independent).
5. **F** — the strategic bet; do it once A–E have populated the world with content worth sequencing.

**Out-of-scope by decision** (recorded in §9): mounts/beast-riding, the Hideouts emplacement/construction
tables, the Mos Espa second city, the grudge/nemesis + contact-relationship layer, the forged-document
economy, the starport-class tier model, and the "Between Sand and Sky" quest extraction.

---

## 3. Lane A — Creature library

**Why first.** The single biggest "this feels like a real WEG Star Wars galaxy" lever, at the lowest risk.
Today the wilderness has a handful of creatures across six worlds; the extractions hand you ~70
era-translated, D6-statted beasts already mapped to your launch biomes, plus harvestable creature-goods
for the live harvest economy. This is packaging, not invention.

**Sources (already extracted — go straight to these for the raw blocks):**
- CotG §2 (launch-biome roster, grouped by the six worlds' biomes), §3 (cross-biome drop-ins), §4 (exotic
  appendix table — full remainder), §5.1 (encounter-table snippets in your exact format), §5.2 (`world_lore`
  species entries), §5.3 (mount stock — parked for §9), §5.4 (technivore ship/station pests), §5.6
  (Stiltwalker Force-sense flavor), §5.7 (harvest sinks).
- Geonosis extraction §2.8 (8 net-new D6 creatures: **aiwha** mount, **saberjowl** region-boss, **rollerfish**,
  **spike-finned sounder**, + trivial razoral/iiaa/sounders), §2.7 (**pocker** spear-rifle), §1.4/§1.6 (**merdeth**
  herds + the Ebon Sea acklay/hydra-worm predator zone in E'Y-Akh).
- Wretched Hive §5A/§5B (jexxel, crynoid, ice modrol; **Derriphan** as an optional high-end Force-mystery boss).
- SoT §10 (D6-stat gaps to re-stat from scratch: **womp rat** and **sarlacc** first — iconic/Tatooine-defining;
  then scurrier, rock wart). SoT also supplies ecology flavor for the R&E-core Tatooine fauna (krayt "dragon
  pearls," ronto/bantha behavior, eopie) as `world_lore` strings.

**De-dup (do NOT re-stat):** the R&E-core appendix already ships ghest, bantha, dewback, krayt, ronto, eopie,
rancor, tauntaun, mynock, etc. CotG/SoT/Geonosis are all written to be additive to that set; honor their
dedup notes (e.g. CotG defers ghest to the core block; SoT defers the marquee Tatooine fauna).

### Phase A — content (turnkey, zero new mechanics, ships now)

1. **`data/npcs_creatures.yaml` (new).** Existing `schema_version: 1` / `npcs:` shape, `char_sheet.attributes`
   in D-codes (non-intelligent creatures carry DEX/PER/STR + skills + special abilities + Move + Size +
   Scale). Lift the launch-biome roster + cross-biome drop-ins; the exotic appendix can follow as a second
   pass. This is the **generator pool** the `npcs_drop_h_combat.yaml` comment already anticipates
   ("a future respawn/scenario engine drop could pull from this file as a generator pool"). Mark Starfighter-scale
   entries (CotG **Miner's Horror**) and the vacuum oddity (**Barri**, Move in meters/round) explicitly so the
   space-combat vs ground-combat path is unambiguous.
2. **`world_lore` species seeds** appended to `engine/world_lore.py` `SEED_ENTRIES` (category `species`,
   era-clean strings, `zone_scope` where biome-specific). Immediately live in the Director digest, NPC brain,
   and `look`. CotG §5.2 and SoT §10 give the content; keep the **worrt**'s Jabba reference institutional
   ("the dominant Hutt cartel") per Q1.
3. **Encounter-pool entries** authored into region YAMLs using the verified schema:
   ```
   encounters:
     base_chance_per_move: <float>
     pool:
       - id: <slug>
         type: hostile | non_hostile
         weight: <int>
         terrains: [<terrain_slug>, …]
         min_distance_from_edge: <int>   # optional
         faction_gate: "<flag>"          # optional
         narrative: "<live string the player sees>"
         payload: { npc_template: <key in npcs_creatures.yaml>, count: [lo, hi] }
   ```
   The **`narrative` fires live today** during wilderness movement; the `npc_template` is consumed once
   Phase B lands. Use CotG §5.1's swarm/pack count ranges so encounters read right (adar 4–36, shredder
   bat 20+, wrix/draagax 5–15, etc.). Target regions now: `dune_sea.yaml`, `coruscant_underworld.yaml`;
   add new biome region stubs for the other launch worlds as their wilderness comes online (ties to Lane D
   for Geonosis/Kamino).
4. **Harvest sinks** wired into `harvest.py` `YIELD_TABLE` / yield logic: **magus** hide, **Andoan
   mineral-fish** alloy (+ the "school marks the ore" prospecting hook), **two-headed tortuce** delicacy,
   Geonosian **merdeth** shells, **thanu** stone "feet" charms, kalaides mollusk. Harvest is live, so these
   are real vendor goods immediately.

### Phase B — encounter→spawner bridge (small engine drop, separate, optional follow-up)

Make `payload.npc_template` actually instantiate the creature at the tile (observable / fightable), reusing
`npc_generator`'s `creature` archetype + the new `npcs_creatures.yaml` as the stat source. This is the deferred
"follow-up drop" named in `wilderness_encounters.py`'s docstring. Modest, but it is new code, so it ships as
its own drop with its own tests. Side benefit: it also lights up the *existing* `dune_sea` encounters
(`tusken_warrior`/`dewback`), which are narrative-only today for the same reason.

**Risks / cautions.** None structural — no schema change, no locked-decision collision. The only honesty
note is the Phase A/B split: creatures are live as ambient encounters + lore + harvest goods immediately;
"a creature you can fight in the wild" needs Phase B. Set that expectation up front so it doesn't read as
a phantom.

**Free riders worth taking with Phase A:** the **Stiltwalker** (chirps near Force-users — a cheap Q1-clean
"the wild reacts to a Jedi" detail), the **Sensor Star** (living-alarm flavor for dens/strongholds), and
quietly landing the mount stock (**aiwha**, **bergruutfa**, **selligore**, **tentacle bird**) in the data
file so §9's mount lane has ready data when/if it opens.

**Acceptance/tests (per-drop file).** Creature-loader schema parse; a `world_lore` reseed assertion; the
wilderness encounter validator over the edited region YAMLs (the loader's warn-don't-fail path means a bad
entry must be *caught by test*, not silently dropped). Phase B adds spawn-instantiation tests with a
force-roll monkeypatch over the creature combat path.

---

## 4. Lane B — B3 era-cleanness sweep

**Why now.** It's cheap, it's a live integrity issue, and you want it before Lane C's gear work widens the
surface. It is also squarely in the spirit of the era discipline every extraction enforces.

**Confirmed primary leak (player-facing):** `engine/encounter_patrol._apply_infraction()` (≈ 564–604) prints
`[IMPERIAL BOARDING] Stormtroopers board for inspection`, `[IMPERIAL CUSTOMS]`, and `[IMPERIAL BOARDING]
Troops withdraw` — bypassing the module's own era-correct helpers (`_zone_authority`, `_default_patrol_name`,
`_board_party`, the `republic → "Clone troopers"` map). The setup/comply/bluff paths use the helpers; the
infraction branch was simply missed in translation. **Fix = route these strings through the same helpers.**

**Other surfaces to triage (not a blind purge — some may be deprecated GCW paths or test-only):**
- `parser/faction_commands.py` (≈ 917) — a help listing "Imperial: 1 = Stormtrooper 2 = TIE Pilot
  3 = Naval Officer 4 = Intelligence".
- `parser/npc_commands.py` (≈ 894) — NPC-type list including `stormtrooper`, `scout_trooper`, `dark_jedi`.
- `parser/combat_commands.py` — multiple `attack stormtrooper` examples in help/usage text.
- `engine/organizations.py` (≈ 163) — `e11_blaster_rifle` "Standard stormtrooper weapon. 5D damage."
- `data/weapons.yaml` (≈ 251) — a `stormtrooper_armor` entry.

**Method (matches project discipline).** Strip block/line comments before grepping; a broad scan
(`imperial|empire|stormtrooper|rebel alliance|tie fighter|x-wing`) over `engine/ parser/ data/` returns on
the order of ~500 raw hits — most are expected to be comments, deprecated-GCW code paths, or test fixtures,
so this is a **triage-and-classify** pass, not a search-and-replace. Classify each hit as: (1) live
player-facing string → recast era-correct; (2) deprecated GCW path → confirm it's unreachable in the CW era
or remove; (3) comment/test → leave or annotate. Reconcile the result with the `META_SWEEP` tracking so the
"B3 clean" claim matches reality after this lane.

**Risk.** Low, but resist over-purging — the goal is era-clean *production strings and reachable paths*, not
deleting every historical reference in comments.

---

## 5. Lane C — Gear / crafting expansion

**Why.** Gundark's roughly triples the gear vocabulary and adds whole *families* the R&E core (and your 38
schematics) are thin on. Brian flagged crafting as the obvious candidate; it is high-value, with the caveat
that gear is where era landmines and balance both cluster.

**Sources:** Gundark's §2 (weapons), §3 (armor + attachments + powered armor), §4 (field/conveyances/
restraints/survival), §5 (espionage/security/sensors), §6 (entertainment), §7 (build-hook mapping per lane),
**§8 (the era cheat-sheet — the authoritative strip list; read before seeding any string)**. GG11 §7 (Tools
of the Trade — 13 items incl. the gangland war-wagon, gambling droid, tri-laser engraver). Platt's gear is
covered in Lane E3 (concealment) — keep it separate.

**What's net-new (the missing families):** stun/non-lethal melee (stun baton/cloak/gauntlets, contact
stunner, taser staff, neuronic whip — *slaver gear, keep faction-gated*); capture weapons (net gun, tangier,
snare, Stokhli, electronet, force cage, magnacuffs, man trap — the BHG/Hutt kit); sensor-evading ballistics
(slugthrower, black-powder, dart shooter, flechette — the "energy scanners miss this" niche); flame & sonic;
disruptors; area/deck weapons (45° arc / cone, the no-dodge band); demolitions (detonite tape, shaped/focal
charges, thermite gel, mines); powered armor (7 suits); the spy/security toolkit.

**Implementation:**
1. **`data/schematics.yaml` + `data/weapons.yaml` expansion.** Map each item to a crafting recipe tier keyed
   by the book's **Availability code** (1 → trivially craftable/general vendors; 2/F → licensed; 3 →
   specialist/faction; 4/R/X → master-tier / black-market only). Required-skill and component-tier come from
   the recipe; the existing crafting engine consumes the rest unchanged (same skills, same R&E damage grammar).
2. **Economy gating (G06).** The Availability code is a ready legality/scarcity axis — wire it to market-tier
   vendor access and to bulk/black-market pricing (contraband X carries the steepest markup; the book's
   "a blaster sells for ~5× retail on the black market" is a fair X-tier anchor).
3. **Security-zone scan (G04).** §5 is a self-contained **detect-vs-defeat** system that maps onto the
   security-zone scan exactly: detectors (Sniffer 5D, CorSec Autoscan 6D fixed checkpoint, Search-Scan,
   Bioscan) define a zone's weapon-scan rating; defeat devices (hide-bonus weapons, identity-defeat masques,
   lock-defeat slicers, camo-netting) give the smuggler an opposed roll. A clean opposed `hide`/concealment
   vs. zone `search` loop, with the slugthrower/black-powder "beats energy scanners" line as a built-in counter.
4. **Combat (G03):** weapons drop straight into the resolver. Two-setting stun weapons are the in-world
   sources of stun damage relevant to the Drop D stun-KO design.

**Era / Q1 cautions (load-bearing).** Strip the entire bylined-commentary layer (densest off-era source).
Recast the wrapper to a Clone-Wars Hutt-cartel/Outer-Rim black-market datalog (foil = CorSec / Republic
Judicial / planetary security). Drop the Imperial-Munitions blaster clones (KK-5, SC-4, etc.). The
**Force-suppression cage** and **Force-aura analyzer** stay **quest artifacts of mysterious/Separatist
origin, never vendor goods**. Keep slaver gear illegal and faction-gated, not on general vendors. Full
per-item handling is Gundark's §8 — treat it as the gate.

**Balance pass.** Calibrate new damage/range/cost against the existing weapon bands on the dev box before
shipping; the catalog includes some very high-end items (disruptors, predator rifle 7D, powered-armor mounts)
that should be 4/R/X-gated, not freely craftable.

**Risk.** Medium — era landmines (mitigated by §8 + Lane B first) and balance. Suggest shipping in waves by
family rather than one monolith drop.

---

## 6. Lane D — Geonosis & Kamino depth

**Why.** The biggest content payoff for two **live launch worlds** that are thin today — they have painted
city maps (Stalgasin Hive, Tipoca City) and Director zone baselines, but no wilderness regions, no extracted
interiors, and no *internal* faction story. Geonosis in particular has rich, era-native material because it's
where the Clone Wars begin.

**Sources:** Geonosis extraction §1 (Geonosis), §2 (Kamino), §4 (build-hook summary), §5 (era cheat-sheet).

**Geonosis build:**
- **World data:** enrich `data/worlds/clone_wars/planets/geonosis.yaml` with the era-clean setting framing
  (caste society, spire-hives, the radiation-scoured surface, droid-foundry economy). No rules change.
- **Interior tier:** the **Gladiator Barracks** beneath the arena is a turnkey pre-gridded interior (1 square
  = 2 m): Slave Barracks · Gladiator Barracks · Sparring Pit · Beast Cage ×2 · Picadors' / Beastwardens' /
  Acklay Chopper's Chambers · Med Center · Armory · exit to Orray Stables. Drop-in room layout.
- **Wilderness tier:** the **E'Y-Akh Desert** with a **net-new annual-flood mechanic** (subterranean
  aquifers overflow; Geonosians herd merdeths into the desert to drown them; the receding water leaves
  glittering shells — a harvest hook). The **Ebon Sea** is an apex-predator zone (escaped + mutant acklays,
  hydra worms). **Golbah's Pit** is a poisoned crater POI. Pairs with the Lane A creatures (merdeth, the
  Geonosis cave/rock set already in CotG §2.3).
- **Faction tension:** the **Stalgasin vs. Gehenbar** inter-hive war + **drone unrest** (droids displacing
  drone labor; the Golbah hive was proton-bombed for revolting). This is real internal-faction fuel for
  Orgs/Territory/Director — the kind of content the Geonosis zone baselines currently lack. Original NPCs
  usable as named (per the extraction's Q1 note): **Typtus of the 33rd Egg**, **Acklay Chopper**, **Marmio Mio**.

**Kamino build:**
- **World data:** enrich `data/worlds/clone_wars/planets/kamino.yaml` (storm-world ocean, Tipoca framing).
- **Wilderness/space tier:** the seas/abyss — **aiwha** as the iconic Kamino mount candidate, the **saberjowl**
  as a launch-and-landing **region-boss hazard** (it can swallow a starfighter), Derem City ruins as an
  exploration/Force-landmark dive (Master Qalsneek's sea-crystal holocron — feeds the Force-resonant
  landmarks lane).
- **Economy/crime:** **cloning-for-hire** and **illicit-clone** jobs via the Ko Sai archetype; the
  Hutt-caravel hook (Geonosis ↔ Tatooine ↔ Hutt Cartel).

**Q1 handling.** Poggle/Sun Fac/Lama Su/Taun We/Ko Sai/Kina Ha/Spar and Jango/Dooku/Sifo-Dyas/Obi-Wan/Vos/
Secura are archetypes or historical backdrop only — never named open-world NPCs. The book's original NPCs
(Typtus, Acklay Chopper, Marmio Mio, Yubookoo, Master Qalsneek) may be named.

**Risk.** Low–Med, but this is a **content build**, not a data drop: the flood mechanic is net-new code, and
the wilderness regions need authoring/painting. Sequence it as a multi-step lane (world data → interior →
wilderness → faction wiring), each its own drop.

---

## 7. Lane E — The small-wins trio (cheap, fun, independent)

Fold these in opportunistically alongside A–D; they're tiny and don't depend on each other.

### E1 — Org scale + Violence Index (GG11)
- **Sources:** GG11 §3 (org-profile schema), §5 (the Karazak five-role model), §8B (Violence Index), §2 (the
  9 era-translated `world_lore` entries — incl. *Criminal Organization Tiers*, *Criminal Occupations*, *The
  Kajidic*, *Indentured Servitude*; entries 3 & 6 **extend** existing Black Market / Hutt Cartel lore rather
  than restating it — honor that).
- **Implementation:** add two fields to the org profile — `scale` (territorial gang → crime guild → cartel →
  syndicate → criminal empire) and `violence_index` (0–100). Violence Index drives how aggressively an org
  contests territory and how the Director narrates turf disputes ("range war" vs. "surgical"); reference
  values from the book: territorial gang ~58, kidnapping guild ~88, cartel ~88, syndicate ~94. GG11 §8B rates
  this "small effort — a field + a few branch points." Seed the 9 lore entries via the standard reseed.
- **Risk:** low. The lore entries are a clean reseed; the two fields are additive.

### E2 — Sandwhirl hazard + Tatooine day/night vocabulary (SoT)
- **Sources:** SoT §3 (hazards), §1 (day/night vocabulary).
- **Sandwhirl:** a dramatic, era-clean weather set-piece that works **both ground and space** — sudden,
  no-warning sand funnels with winds ~10× a sandstorm's that can drag a light starship half a kilometer,
  smash buildings, and fling banthas (~200 m pull radius; the funnel wanders randomly each round, so you
  can't simply walk out). Also re-tune the graded sandstorm/gravel-storm/heat-thirst hazards into the
  hazard/weather system (discard the d20 DCs; re-stat to D6). Slots into `engine/hazards.py`.
- **Day/night vocabulary:** layer Tatooine's idiom (First Dawn, Second Dawn, High Noon, First Twilight,
  Second Twilight) onto the world clock as **planet-keyed display strings** — a lookup keyed by planet +
  the existing day/dusk/night band. **No renderer change** (it still resolves to day/dusk/night underneath).
  High atmosphere-per-effort.
- **Risk:** low. The display-string layer is purely additive over `world_time.py`.

### E3 — Venue front_owner/true_owner + d66 ambient table (Wretched Hive)
- **Sources:** Wretched Hive §2A (the seven-field venue-profile card), §2B (the 10-step venue-creation
  framework — the field set for a procedural shop/venue generator and the authoring checklist), §2C (the d66
  cantina encounter table), §6 (build hooks), §8 (adventure seeds — these feed Lane F, not here).
- **Implementation:** add a `front_owner` / `true_owner` flag-pair to the venue/shop profile (today
  `housing.py` carries a single `shopfront_owner_id`). The owner≠true-owner split (public shell vs. hidden
  Hutt running the illicit activities from a concealed control room) turns "who really runs this place" into
  an investigation/territory mechanic. The d66 table is drop-in ambient scene fuel (era-translate the ~4
  flagged entries — stormtrooper/off-duty-Imperial/Alliance-double-agent → clone patrol / off-duty mercs /
  rival-faction double agent). Optionally seed the 10-step framework as the config field set for the player-shop
  generator and stand up a venue/POI profile schema (amenities, cover, VIP room, security ref,
  illegal-activities list, 1–5 desirability/danger rating).
- **Risk:** low. Schema add + content; the generator framework is optional depth.

---

## 8. Lane F — Director quest-template library (strategic bet, later)

**Why it's the headline and why it's last.** The roadmap's key insight (§4 of the extraction roadmap): you
don't need live LLM calls to get good direction if you mine the right material into a **deterministic content
library**. Every WEG adventure hook is a pre-authored, branching structure — objectives, NPC motivations,
encounter beats, complications, rewards. Extracted and era-translated, they become a library the Director
*sequences with rules*, not generation, capping API cost to optional flavor prose (Haiku/Mistral top layer)
rather than decision-making. This is the highest *strategic* value on the list — but it requires a new
quest-template framework that does not exist on HEAD (the Director today emits influence-driven
`rumor/opportunity/encounter/personal_quest` categories, not branching pre-authored templates). So it is a
framework build, sequenced after A–E have populated the world with content worth directing.

**Ready-translated seed content (already in hand):**
- Wretched Hive §8 — six "Loose Threads" templates (kidnap-ring investigation, knows-too-much extraction,
  forced-arena escape, wrecked-hunter siege, fugitive-safehouse run, the optional Force-horror "Lurker").
- Hideouts §7 — ten quest seeds (Attack!/siege, boarding assault, rescue, hidden munitions, gun-drop-gone-wrong,
  island fugitive, free-port intrigue, water-boss politics, salvage & debt, sewer chase).
- Geonosis §1.6/§2.6 — eight deterministic seeds (5 Geonosis, 3 Kamino).
- SoT §8C — "Between Sand and Sky" (era-translates cleanly; not yet structure-extracted — flagged as a
  follow-up extraction when this lane opens).
- GG11 §8A — the black-market transaction protocol (a four-step/seven-rule fence-negotiation mini-interaction:
  contact → deal (opposed bargain/con) → delivery (double-cross risk, escrow modifies) → walk-away (reprisal flag)).

**Scope note.** Building the framework (template schema, selection heuristics, complication tables, reaction
rules — the GM-guide material the roadmap recommends mining next for the Director) is a substantial design
effort in its own right and should get its own dedicated design doc before implementation. This roadmap
records the seed inventory and the rationale; it does not specify the framework.

---

## 9. Deferred / out-of-scope by decision (with rationale)

Recorded so the implementation session doesn't pick these up by accident, and so the *reasons* are durable.

- **Mounts / beast-riding.** CotG §5.3 and the Geonosis **aiwha** flag the ready stock (aiwha, bergruutfa,
  selligore, humbaba, tentacle bird). No mount system exists on HEAD. Defer as its own lane; **land the mount
  creatures' data in Lane A** so this opens cheaply later. Nice synergy: mounts depend on the creature drop.
- **Hideouts emplacement + construction tables (Hideouts §3/§4).** Collide with two **locked decisions**:
  Territory §12.3 lists "automated territory defense (turrets, mines, traps)" under *What NOT to Build*
  ("Guard NPCs are sufficient"), and Cities/Housing use **abstract tier pricing**, not per-feature
  construction sums. Use §3/§4 only as a **reference annex** — set-dressing, named landmarks, quest objectives
  ("sabotage the ion cannon"), canonical D6 stats for *NPC* bases, and a sanity-check on the abstract city
  numbers / `(A) Engineering` content. A player-facing base-defense layer would explicitly reopen those
  decisions. The Hideouts §1 **stronghold archetypes** are *not* deferred — they fold into Lane D (themed
  city/Org-HQ flavor) and Lane F (quest objective sites).
- **Mos Espa as a second painted city (SoT §5).** Strong future target (the OR/Hutt-era counterpart to Mos
  Eisley), but a full city build. Keep as world-data lore for now; revisit after Lane D proves the
  second-world content loop.
- **Grudge/nemesis + contact-relationship model (Platt's §5/§6).** Persistent adversaries with motives, and
  origin→loyalty→degradation relationship tracking. High flavor; feeds Director + bounties + the *existing*
  faction-reputation system. Defer until Lane F gives it somewhere to surface.
- **Forged-document economy + starport-class tier model (Platt's §4).** A credit sink + customs modifier, and
  a `port_class` field driving repair cost/scrutiny/patrol presence. Good depth; defer behind Lane E3/Lane C
  so it doesn't fragment the economy work.
- **"Between Sand and Sky" structure extraction (SoT §8C).** A ready Tatooine quest; extract its structure
  only when Lane F opens.

---

## 10. Cross-cutting drop discipline & acceptance notes

Every lane above ships under the standard discipline (recorded once here):

- **Pre-flight HEAD audit** before each drop — grep at symbol level; never trust a prior handoff/memory that
  a thing is delivered. (This roadmap's §1 is the current baseline; re-verify at drop time.)
- **Validate before claiming delivered:** AST-validate Python, `node --check` any JS, `python -c "from <mod>
  import <symbol>"` import-load check for anything claimed shipped.
- **Per-drop test file** (don't extend earlier test files). For content drops: schema-parse + a reseed/validator
  assertion + the wilderness encounter validator over edited region YAMLs (the loader's warn-don't-fail path
  means a malformed entry must be caught by a test, not silently dropped). For engine drops: force-roll
  monkeypatch over success/fail/fumble; `_FakeDB` read-only/mutation-log assertions where DB writes are claimed.
- **Slug-based binding** — smoke scenarios use `room_id_by_slug()`, never hardcoded DB IDs (PVF-5 lesson).
- **Era/Q1 gate** — strip block/line comments before B3 grepping; keep canonical figures institutional/
  absence-framed; recast every off-era production string. Gundark's §8 and each extraction's era cheat-sheet
  are the authoritative strip lists.
- **Package** root-mirrored zip for `Expand-Archive -Force`; update `CHANGELOG.md` + `TODO.json` in the same
  drop; combined rolled-up zip supersedes prior. Brian runs full pytest on Windows (ground truth); sandbox
  runs targeted AST + changed-module checks only.

---

## 11. Source-doc → lane index (quick lookup)

| Lane | Primary extraction sections to pull from |
|---|---|
| A — Creatures | CotG §2/§3/§4/§5.1/§5.2/§5.6/§5.7; Geonosis §2.8/§2.7/§1.4/§1.6; Wretched Hive §5A/§5B; SoT §10 |
| B — B3 sweep | (audit finding — `encounter_patrol`, `faction_commands`, `npc_commands`, `combat_commands`, `organizations`, `weapons.yaml`) |
| C — Gear/crafting | Gundark's §2/§3/§4/§5/§6/§7/**§8**; GG11 §7 |
| D — Geonosis/Kamino | Geonosis extraction §1/§2/§4/§5 (interiors §1.4; flood §1.6; Kamino §2) |
| E1 — Org scale/violence | GG11 §2/§3/§5/§8B |
| E2 — Sandwhirl + clock | SoT §3/§1 |
| E3 — Venue owner-split + d66 | Wretched Hive §2A/§2B/§2C/§6 |
| F — Director templates | Wretched Hive §8; Hideouts §7; Geonosis §1.6/§2.6; SoT §8C; GG11 §8A; extraction roadmap §4 |
| Deferred | CotG §5.3 + Geonosis aiwha (mounts); Hideouts §1/§3/§4/§7; SoT §5 (Mos Espa); Platt's §4/§5/§6 |

---

*End — SW_MUSH Sourcebook Enrichment Roadmap & Implementation Plan v1.0.*
*Companion to `sourcebook_extraction_roadmap_v1.md` (which-book) and the eight source extraction docs (raw stat blocks + era cheat-sheets). Architecture-of-record: `sw_d6_mush_architecture_v51.md`.*
