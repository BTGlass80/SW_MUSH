# SW_MUSH — Clone Wars Era Design
## Version 3.0 — April 18, 2026 · Opus parallel session
### Pivoting SW_MUSH from Galactic Civil War to Clone Wars, mid-war ~20 BBY

---

## Changelog vs. v2

- **NEW §8 Director AI & World Lore Pivot** — full audit of the existing Director + world_lore system (61 seeded lore entries, 14 zone narrative tones, GCW-hardcoded faction keys in `engine/director.py`, GCW-keyed Director system prompt). Explicit triage: what to keep, rewrite, delete, and author fresh. Structural engine refactor called out as part of pivot enablement.
- **Revised drop plan** to include Director/lore content as Drop 6 (split 6a engine / 6b content), bumping tutorial to Drop 8, pivot enablement to Drop 9, etc. Now 11 drops total.
- **Added §11.3 item 7 Director engine data-fication** to the hard-coupled engine changes list — VALID_FACTIONS and ZONE_BASELINES must move from source constants to data. ~200-line refactor. Worth doing as a pure refactor first (Drop 6a) even ahead of the pivot.
- **All 11 v3 open questions resolved** (§13). Key user decisions this session:
  - Keep all 7 Coruscant zones (~65 rooms)
  - Clone Trooper deserters allowed → feeds BHG bounty mechanics
  - Shipwright template stays (Kuat buildout confirmed)
  - Gilded Cage uses soft NPC friction, not hard blocks
  - No one fully gated from Jedi path; non-signed characters take a longer road
  - Jedi/BHG starting rep stays -10 (canon-supported: Cad Bane archetype)
  - Kamino infiltration content for CIS players → post-launch
  - Director data-fication ships as Drop 6a ahead of pivot
  - Sith `dark_side_stirring` milestone events ship at launch (atmospheric only)
  - Holonet News flavor ships with Drop 6b
- **Sourcebook inventory** updated: GG10 Bounty Hunters *is* already extracted (8 lore entries present in codebase). GG11 and Jedi Academy remain the two most-valuable missing books — exist and will be uploaded in a future session for v4 integration.
- **§14 Status & Handoff Signal** added — design is review-ready, authoring gate is "one more pass" then proceed.

## Changelog vs. v1

- **Locked-in era**: Mid-war, ~20 BBY (v1 proposed, v2 locks)
- **Worlds sized up significantly** — target room counts raised to reflect user preference for larger worlds
- **Kuat added** as launch planet (6 launch planets, not 5)
- **Coruscant underworld wilderness** added as launch wilderness region (replaces Dune Sea as default)
- **Jedi Village** unlock mechanism locked in (SWG-style)
- **GCW retirement**: clean-slate DB wipe, preserve Test Jedi
- **Tutorial rework** required — must not lose scope
- **Exit discipline section** added (§6) — rigorous, testable rules to prevent the 21-collision tutorial bug pattern from recurring
- **Coruscant content enriched** from *Coruscant and the Core Worlds* (WotC d20, 2003) — Jedi Temple five-spire structure, Galactic Senate Rotunda layout, Westport, Calocour Heights, Column Commons, Southern Underground, Opera House, Skydome Botanical Gardens, Glitannai Esplanade, Western Sea, Galactic Fair, Garbage Pits
- **Kuat content enriched** from same book — KDY orbital array (15-zone diagram), Kuat City restricted access pattern, merchant-house intrigue (Andrim, Purkis)
- **Sourcebook gap list updated** — Galaxy Guide 11 and Jedi Academy Sourcebook noted as still-needed
- **§8 open questions** updated — several resolved, new ones surfaced

---

## Document Purpose

This document designs the **Clone Wars era** as a full pivot replacement for the Galactic Civil War setting currently shipped in SW_MUSH. It is a *content* design, not an *engine* design — the intent is that when the world-data-extraction refactor lands, this document's planet roster, faction roster, zone map, and policy settings drop into `data/worlds/clone_wars/` without further discussion.

This document was produced in parallel with the main development track and is explicitly designed to be **standalone** — it does not modify engine code, does not block on any in-flight implementation session, and produces artifacts that can be reviewed, revised, and staged independently.

### Key decisions (now locked)

| Decision | Choice | Rationale |
|---|---|---|
| Era timing | Mid-war, ~20 BBY | Richest, longest-legged setting. Outer Rim Sieges active. Mature Jedi Order fielding Padawans. Audience recognition via *The Clone Wars* series. Avoids Order 66 ticking-bomb problem. |
| Player fantasy | Mixed archetypes + factional | Jedi is one path among many. Faction choice (Republic/Separatist/Independent) gates content. SWG model. |
| Jedi unlock | **Village quest chain** | Hidden location, discoverable sequence, narrative-gated. Highest thematic fit with SWG reference. |
| Pivot scope | Full replacement | GCW content retired to reference. No dual-era runtime. `active_era: clone_wars` in config. |
| GCW retirement | **Clean-slate DB wipe** | No live players to migrate. Preserve Test Jedi character definition. |
| Starting location | Coruscant Spaceport (Westport arrivals) | New main hub. |
| World size | **Substantially larger than GCW** | User directive — target ~230 rooms across 6 planets vs. current ~120 across 4. |
| Tutorial | **Rework, don't regress** | Current 6-profession tutorial is GCW-keyed. Full rewrite required. Treat as expansion opportunity, not port. |
| Wilderness launch | **Coruscant Underworld** | First wilderness region is Coruscant underlevels, not Tatooine Dune Sea. |
| Clone Trooper defection | **Allowed** | Deserter clones become BHG contract targets — novel content loop tying clone PCs to bounty mechanics. |
| Shipwright template | **First-class** | Kuat gets full buildout; shipwright is its anchor archetype. |
| Gilded Cage access | **Soft NPC friction for Humans** | No hard block; establishes non-Human district without punishing players. |
| Force-sign fairness | **No one fully gated** | Non-seeded characters pursue Village via longer/harder path; roads exist for all. |
| Director data-fication | **Drop 6a, ahead of pivot** | Refactor is valuable standalone; ship with GCW config producing byte-identical behavior. |
| Sith milestone events | **Launch, atmospheric only** | `dark_side_stirring` fires when dark-side kills cluster; no joinable Sith faction. |
| Holonet News | **In Drop 6b** | War-front headlines are core atmosphere, not polish. |

---

## 1. Era Context — What the Galaxy Looks Like at ~20 BBY

### 1.1 Political situation

- The **Galactic Republic** is at war. Chancellor Palpatine holds emergency powers granted at the war's outset. The Senate remains technically in session but increasingly rubber-stamps military policy. Core Worlds loyalty is near-total; Mid and Outer Rim loyalty is uneven.
- The **Confederacy of Independent Systems** (Separatists) is led publicly by Count Dooku with a Separatist Council of corporate heads (Trade Federation, Techno Union, Banking Clan, Commerce Guild, Corporate Alliance, InterGalactic Banking Clan, Retail Caucus). The CIS fields droid armies; its leadership is Sith-directed but this is not public knowledge.
- The **Jedi Order** has been militarized. Knights and Masters serve as Generals, Padawans as Commanders. The Temple on Coruscant is functioning but partially depleted — many Jedi are in the field. Casualties since Geonosis have been significant.
- The **Grand Army of the Republic** is entirely clone troopers from Kamino, commanded by Jedi officers and clone commanders. Republic Navy capital ships (Venators, Acclamators, built at Kuat) are increasingly visible in both Core and Rim space.
- **Neutral powers** persist: the Hutt Cartel openly, the Corporate Sector semi-officially, several smaller polities trying to stay out of the conflict.

### 1.2 What this means for player experience

- **A Jedi walking into a cantina is an event**, not background. Civilian reactions range from reverence (Core), wariness (Outer Rim), to active hostility (Separatist territory).
- **Clone troopers are ubiquitous on Republic worlds** — in Coruscant lobbies, on Ryloth checkpoints, patrolling Christophsis streets. They are not menacing the way stormtroopers are in the GCW; they are soldiers doing a job.
- **Droid armies are the Separatist face**. Encounters with B1s, B2s, droidekas, magnaguards replace encounters with stormtroopers for players operating in CIS space.
- **Smuggling is a mature business** but the market has shifted. War contraband, medical supplies, intelligence, and people-smuggling are more profitable than spice. The Hutts profit from both sides.
- **Bounty hunting is thriving**. Jango Fett is dead but his reputation casts a long shadow; figures like Cad Bane, Aurra Sing, and Embo define the era.
- **The Force is public**. No Inquisitors, no purge, no "it's just an old religion." The Jedi Order is a visible galactic institution.

### 1.3 What's different about Jedi in this era (vs. GCW)

In GCW, Jedi are hunted fugitives. In this era:
- Lightsabers are **not illegal anywhere in Republic space**. They're restricted in Separatist territory but the issue is "this person is Jedi" not "this person has a weapon."
- Jedi have **command authority** — a Knight can commandeer resources, direct clone units, and override local authorities within reason on Republic-aligned worlds.
- Force use in public is **not suppressed**. Using telekinesis to catch a falling glass in a cantina on Coruscant draws "huh, Jedi" — not "call the Inquisitors."
- The Dark Side exists but is clandestine. Dooku, Ventress, and other Dark Side users are known but not publicly labeled as Sith.

### 1.4 Tone

Clone Wars is **operatically dramatic** where GCW is **gritty and oppressive**. The Rebel Alliance fights from shadows; the Grand Army fights in formation on the evening news. The visual palette is brighter — Venators over Coruscant at dawn, the crystalline cities of Christophsis, Naboo's green hills. There's still grit (Ryloth's ruined cities, Coruscant's underlevels, refugee camps) but the *default* scene reads as noble war, not occupation.

This tone shift matters for every Director AI prompt, ambient event, NPC disposition, and scene description we produce.

---

## 2. Planet Roster

### 2.1 Six launch planets

| Planet | Role | Zones | Rooms (target) | Status |
|---|---|---|---|---|
| **Coruscant** | Republic capital, Jedi Temple, starting hub | 7 | ~65 | New, largest build |
| **Kuat** | Republic shipyards, orbital ring | 3 | ~30 | New, mid-sized |
| **Geonosis** | Separatist industrial heartland | 4 | ~35 | New, themed |
| **Kamino** | Clone facility, aquatic | 3 | ~25 | New, small-medium |
| **Tatooine** | Neutral Hutt-adjacent frontier | 5 (existing, renumbered) | ~54 (existing) | Reskin of current |
| **Nar Shaddaa** | Smugglers' moon | 3 (existing, renumbered) | ~30 (existing) | Reskin of current |

**Total:** ~239 rooms across 6 planets vs. current ~120 across 4. About **135 net new rooms to build**, concentrated on Coruscant (~65), Geonosis (~35), Kuat (~30), and Kamino (~25).

Plus the **Coruscant Underworld wilderness region**, which the wilderness system contemplates as coordinate-based tiles rather than hand-built rooms — so the "effective" world size is larger still.

### 2.2 Dropped from current roster

- **Kessel** — spice mines are still canon in this era but pull less narrative weight when the Empire isn't the consumer/threat. Can resurface as a wilderness expansion pack later.
- **Corellia** — existing 24 rooms are built around GCW Corellia flavor. In Clone Wars, Corellia is a major Republic Core World deserving a proper build, not a reskin. Deferred to post-launch.

### 2.3 Per-planet detail

#### 2.3.1 Coruscant (new, ~65 rooms)

Drawing from *Coruscant and the Core Worlds* (WotC, 2003) which explicitly addresses the Rise of the Empire era:

> "During the Rise of the Empire era, Coruscant is very cosmopolitan. Despite the growing corruption of the Senate, the 'capital planet' is still enjoying a golden age. The Jedi maintain a strong presence on Coruscant, and local criminal syndicates keep a low profile."

This is the tone to capture: a city at its zenith, gleaming on the surface, corruption churning below.

**Zones (7):**

| Zone | Security | Rooms | Theme |
|---|---|---|---|
| `westport_district` | secured | 8 | Arrivals hub, customs, landing platforms, outer plaza — **starting zone** |
| `senate_district` | secured | 10 | Senate Rotunda, Chancellor's approach, diplomat's quarter, Pliada di am Imperium (open-air balcony) |
| `jedi_temple` | secured | 14 | Temple grounds, five-spire layout, Archives, training halls, Council Chamber lobby — **Jedi-faction deep areas** |
| `coco_town` | contested | 10 | Middle-level commercial district, Dex's Diner equivalent, eateries, mixed-faction legal |
| `calocour_heights` | secured | 6 | Marketing/advertising district, pushy holo-ads, gadget shops, cutthroat agencies |
| `southern_underground` | lawless | 10 | Seedy mid-levels, Crystal Jewel cantina, barter stalls, shadow economy |
| `gilded_cage` | contested | 7 | Alien quarters (pre-Invisec era equivalent), expat communities, mercantile |

Note on the Gilded Cage: the WotC book describes the "Invisible Sector" ("Invisec") as Palpatine's post-imperial alien ghetto. At mid-war Clone Wars, that walling-off hasn't happened yet. I'm naming our version the **"Gilded Cage"** to signal: a district where non-Humans concentrate, prosperous but feeling the social pressure of rising Human High Culture rhetoric, foreshadowing what will become Invisec after the Republic falls. This gives us a distinctive name, ties to canonical lore, and sets up future narrative (if we ever run events depicting the fall).

**Key named locations (anchors that must exist in their zones):**

- `westport_arrivals` — starting room for new non-Jedi characters
- `jedi_temple_gates` — starting room for new Jedi-Padawan characters (if they skip the Village quest)
- `jedi_council_chamber_lobby` — Jedi-only deep area; the chamber itself is NPC-gated
- `jedi_archives` — Jedi-only; huge library, research-skill quest hooks
- `grand_convocation_chamber_gallery` — visitor gallery of the Senate Rotunda
- `chancellors_approach` — high-security, Republic-faction rep-gated
- `dexs_diner` — classic Coruscant NPC hangout, faction-neutral
- `crystal_jewel_cantina` — sign reads "If the customers don't kill you, the drinks will" (from sourcebook)
- `opera_house_foyer` — Coruscant Opera House, cultural scene anchor
- `skydome_botanical_gardens` — public tour entry, carnivorous flora exhibit
- `glitannai_esplanade` — top-dropped boulevard, ritzy shops alongside Judicial Plaza
- `western_sea_promenade` — the artificial aquifer resort
- `bhg_chapter_house` — Bounty Hunters Guild Coruscant chapter, in Southern Underground

**Underworld connection:** the Southern Underground zone has one explicit exit downward (a named exit, `manhole` or `vent`) into the Coruscant Underworld wilderness region. That's the gateway to the coordinate-based wilderness tiles — a single clear handoff point.

#### 2.3.2 Kuat (new, ~30 rooms)

Drawing from the same sourcebook:

> "The heart and soul of Kuat reside in the Drive Yards. These massive shipyards encircle the planet, producing some of the most memorable ships and ship classes in the galaxy."

In our era (20 BBY), Kuat Drive Yards is the primary Republic capital-ship supplier — Venators, Acclamators, and other Grand Army vessels are built here. Heavily patrolled by Kuati Security Forces (KSF) and **not** generally accessible to Separatist-aligned characters. Planet surface is permit-gated; most visitors only see the orbital ring.

**Zones (3):**

| Zone | Security | Rooms | Theme |
|---|---|---|---|
| `kuat_main_spaceport` | secured | 6 | Main arrival ring, customs, KSF checkpoint, merchant lounges |
| `kdy_orbital_ring` | secured | 18 | The shipyards themselves — drydocks, warehouses, machine shops, factories, apartments, commercial zone |
| `kuat_city_embassy` | secured | 6 | Small planetary downport — mercantile forum, Republic liaison office, (limited) restaurants & hotels |

**Key named locations:**

- `kdy_main_spaceport_arrivals` — the public-facing port-of-entry
- `drydock_bay_venator` — one of several drydocks; a Venator under construction. Republic-faction access to decks. **Target: mission anchor.**
- `drydock_bay_acclamator` — same for Acclamator-class
- `ksf_headquarters_lobby` — Kuati security HQ, high-rep Republic access
- `mercantile_forum` — Kuat City merchant-house negotiations, trade-mission source
- `house_andrim_office` / `house_purkis_office` — **merchant-house intrigue content** (from sourcebook's adventure hook about sabotage-for-hire between rival shipwright houses)
- `kdy_offices_reception` — corporate HQ

**Design notes on Kuat:**

- Player-owned ships cannot dock at drydocks (those are for capital-ship construction); they dock at Main Spaceport and shuttle to the ring.
- Kuati Security Forces are treated as a **faction adjunct** — they serve the Republic but jealously guard KDY trade secrets. A Republic-high-rep character still needs specific permits for deep-ring zones.
- This is a rich location for **industrial espionage missions** (CIS-aligned characters) and **escort/protection missions** (Republic-aligned). Merchant-house intrigue is a bonus subplot layer.

#### 2.3.3 Geonosis (new, ~35 rooms)

Separatist industrial heartland. The iconic Clone Wars opening battlefield, still active as a droid-foundry world.

**Zones (4):**

| Zone | Security | Rooms | Theme |
|---|---|---|---|
| `stalgasin_hive_surface` | lawless | 10 | Geonosian city surface, hive entrance, markets, Separatist docking pads |
| `stalgasin_deep_hive` | lawless | 10 | Hive tunnels, Archduke's palace approach, Geonosian ruling class |
| `petranaki_arena` | contested | 5 | The arena and gladiatorial prep quarters — pit-fight opportunities, instanced-combat candidate |
| `droid_foundries` | lawless | 10 | Weapons factories, assembly lines, sabotage targets |

**Key named locations:**

- `geonosis_landing_platform_primary` — main CIS-friendly arrival point
- `stalgasin_market` — Geonosian + smuggler + bounty-hunter intersection
- `archdukes_audience_hall_approach` — high-level CIS diplomat content
- `petranaki_arena_floor` — the iconic execution-pit location
- `geonosis_arena_stands` — gladiatorial audience perspective
- `droid_foundry_assembly_line_alpha` — sabotage mission anchor
- `cis_recruiter_office` — Separatist-aligned chargen support

**Design notes on Geonosis:**

- Republic-aligned characters face active hostility — patrols from B1 droid NPCs, KO-ing mechanics.
- CIS-faction characters get friendly NPCs and reputation rewards.
- Independent-faction characters can transit with caution.
- This is the opposite of Coruscant — where Coruscant is dangerous for CIS (Republic security is tight), Geonosis is dangerous for Republic.

#### 2.3.4 Kamino (new, ~25 rooms)

Republic military facility. Restricted, themed, claustrophobic in a cool way.

**Zones (3):**

| Zone | Security | Rooms | Theme |
|---|---|---|---|
| `tipoca_city_platform` | secured | 10 | Main platform — command deck, hangar bays, clone barracks, training grounds |
| `cloning_facilities` | secured | 10 | Vats, maturation chambers, medical wings — **deep-rep Republic access only** |
| `ocean_platforms` | contested | 5 | Outer platforms, aiwha stables, ocean-level maintenance |

**Key named locations:**

- `tipoca_spaceport_arrivals` — main port of entry
- `prime_ministers_office_lobby` — Kaminoan leadership
- `clone_barracks_mess` — ambient clone trooper interactions
- `training_grounds_primary` — Clone Trooper template chargen anchor
- `growth_chamber_observation` — high-Republic-rep quest content
- `medbay_primary` — genetic engineering lore
- `aiwha_stables` — the giant sea-creatures used for transport and flavor

**Design notes:**

- Non-Republic characters need a clearance quest to access anything past `tipoca_spaceport_arrivals`.
- Kaminoan NPCs are aloof, professional, genetically obsessed — distinctive NPC voice.
- Clone trooper ambient interactions here are the backbone of immersion.

#### 2.3.5 Tatooine (reskin, ~54 rooms)

Neutral Hutt-adjacent frontier. Retains all existing rooms with text-level reskin.

**Reskin scope:**
- Replace all "Imperial" NPC and flavor references with "Republic patrol" (rare — Outer Rim Republic presence is thin) or simply remove
- Strip references to Rebel sympathizers; add references to war refugees, deserter clone troopers (rare but thematic), Separatist recruiters
- Lars homestead reference: remove or prepend with "young family" — pre-dates Luke's residence
- Jabba's Palace stays exactly as-is (Hutts are era-agnostic)
- Mos Espa podracing is more canonical in this era (pre-war and early-war Boonta Eve)
- Prefect Eugene Talmont (existing Imperial-flavored NPC) → rename and re-faction to "Republic Sector Administrator" or simply "Mos Eisley Prefect" with no central-government affiliation

Every reskin edit is a YAML string change, not a structural change.

#### 2.3.6 Nar Shaddaa (reskin, ~30 rooms)

Smugglers' moon, Hutt Cartel neutral ground. Retains all existing rooms.

**Reskin scope:**
- Hutt Cartel is the same organization; Nal Hutta politics work identically
- Add "war profiteer" flavor — both Republic intel and Separatist agents frequent the moon
- Bounty hunter presence intensifies (BHG chapter house NPC)
- Spice references become medical + recreational — wartime medical demand is a plot hook

### 2.4 Planet-to-faction-to-fantasy map

| If a player wants to... | They go to... |
|---|---|
| Train as a Jedi Padawan | Coruscant (Temple) — after completing Jedi Village unlock |
| Run Republic intel missions | Coruscant → Kamino → Geonosis strike missions |
| Run Republic industrial/diplomatic | Coruscant → Kuat |
| Run Separatist ops | Geonosis → Tatooine → Nar Shaddaa |
| Smuggle war contraband | Nar Shaddaa ↔ Tatooine ↔ everywhere |
| Hunt bounties on any side | Coruscant underworld or Nar Shaddaa → galaxy-wide |
| Play a clone trooper | Kamino (origin) → Coruscant (deployment) → Geonosis or Kuat |
| Play a Hutt Cartel thug | Nar Shaddaa → Tatooine |
| Play a shipwright/industrial | Kuat (merchant houses, KDY work) |

Every planet-faction combination has a primary activity loop. No planet is a dead zone for any of the core archetypes.

---

## 3. Faction Roster

### 3.1 The eight factions

| Code | Name | Role | Alignment | Joinable |
|---|---|---|---|---|
| `republic` | Galactic Republic | Primary aligned power | Light-lean | Yes |
| `cis` | Confederacy of Independent Systems | Primary opposition power | Dark-lean | Yes |
| `jedi_order` | Jedi Order | Light Side Force order, serves Republic | Light (locked) | **Yes, Village-gated** |
| `hutt_cartel` | Hutt Cartel | Organized crime / neutral | Neutral, chaotic | Yes |
| `bhg` | Bounty Hunters Guild | Contract killers / neutral | Neutral | Yes |
| `independent` | Unaligned | Default | Neutral | Default |
| `sith` | Sith Order | Dark Side Force power, covert | Dark (locked) | **No (NPC-only)** |
| `separatist_council` | Separatist Council | CIS corporate oligarchy | Dark-lean | **No (NPC-only)** |

### 3.2 Faction reputation starting posture

| If PC faction is... | Republic rep | CIS rep | Jedi rep | Hutt rep | BHG rep |
|---|---|---|---|---|---|
| `republic` | +50 | -30 | +10 | -10 | 0 |
| `cis` | -30 | +50 | -30 | -10 | 0 |
| `jedi_order` | +30 | -50 | +100 | -20 | -10 |
| `hutt_cartel` | -20 | -20 | -20 | +50 | +10 |
| `bhg` | 0 | 0 | -10 | +10 | +50 |
| `independent` | 0 | 0 | 0 | 0 | 0 |

Existing reputation math handles the rest.

### 3.3 Faction HQ locations

| Faction | HQ location | Room slug (target) |
|---|---|---|
| Republic | Coruscant Senate District | `senate_military_liaison_office` |
| CIS | Geonosis Stalgasin Deep Hive | `cis_diplomatic_annex` |
| Jedi Order | Coruscant Jedi Temple | `jedi_temple_mission_board` |
| Hutt Cartel | Nar Shaddaa | (existing) |
| BHG | Coruscant Southern Underground | `bhg_chapter_house` |
| Independent | (none, by design) | — |

### 3.4 Chargen templates (approximate set)

| Template | Primary faction | Notes |
|---|---|---|
| Clone Trooper | Republic | Origin: Kamino |
| Republic Naval Officer | Republic | Coruscant or Kuat start |
| Republic Intelligence | Republic | Covert ops |
| **Jedi Padawan** | Jedi Order | **Gated — Village unlock required** |
| Separatist Commando | CIS | Elite droid-adjacent trooper |
| CIS Agent / Infiltrator | CIS | Covert ops |
| Bounty Hunter | BHG | Nar Shaddaa or Coruscant underworld start |
| Smuggler | Independent / Hutt | Tatooine or Nar Shaddaa start |
| Freighter Captain | Independent | GG6 Tramp Freighter flavor |
| Mercenary | Independent | Faction-switchable |
| Medic | Independent | Battlefield-neutral |
| Slicer / Tech | Independent | Cracken's computer ops |
| Podracer / Gunrunner | Independent / Hutt | Tatooine-focused |
| Scout | Republic / Independent | Uncharted worlds exploration |
| **Shipwright** | Independent | Kuat-focused. New template. |

15 templates. Jedi Padawan is the marquee unlock; Shipwright is a new niche for Kuat-focused play.

---

## 4. The Jedi Village Unlock

### 4.1 The SWG reference

In Star Wars Galaxies, Force-sensitivity was originally gated behind a grind called "the Village" — players had to complete a hidden questline that required them to first identify themselves as Force-sensitive (via specific skills and activities), then travel to a Mustafar-adjacent hidden village, then complete a branching questline to unlock Jedi path. The Village was universally praised as *thematic* even when players complained about the grind.

We can do better than grind: **we can do a pure quest chain.**

### 4.2 Our implementation

**Act 1: The Signs.**
Every character, regardless of faction, has a small (~1%) chance per session of triggering an ambient "Force sign" event — a prescient dream, a moment of heightened awareness in combat, an accidental telekinetic twitch. These are passive flavor events. Over 4-8 weeks of play, a given character either accumulates signs or doesn't.

After enough signs (threshold: ~5), the character receives an unprompted cryptic message from an unknown sender: "I have seen you in my meditations. Come to the Jundland Wastes. Alone." Or similar.

**Act 2: The Village.**
The "village" is a hidden wilderness location — a candidate site: a cluster of rooms in the Tatooine wilderness (or Dagobah, or Felucia — TBD) built as a small hand-crafted enclave of Force-sensitive hermits who left (or were never part of) the Jedi Order.

The village entry is gated by:
1. Having received Act 1 signs (flag on character)
2. Successfully navigating to the exact wilderness coordinate (with subtle hints)
3. Passing an NPC conversation test (not a skill check — a dialogue tree)

Once inside, the character is welcomed by an elder NPC who identifies them as Force-sensitive and offers training. This is a **multi-session quest chain** (~5-10 sessions of play depending on depth).

**Act 3: The Choice.**
The Village elder eventually presents the character with a choice:

- **Path A: Report to the Jedi Order.** The character is escorted (via NPC convoy mission) to the Coruscant Jedi Temple, where they are tested, accepted as a late-age Padawan, and gain the `jedi_order` faction. This path is the canonical one; it gives full faction benefits and lightsaber issuance.
- **Path B: Stay with the Village.** The character remains Force-sensitive but unaffiliated with the Jedi Order. They gain the `independent` faction with Force powers unlocked. They can construct or acquire a lightsaber through alternative (difficult) means. This path is for players who want Force powers without Jedi politics.
- **Path C: Dark whispers.** A third NPC (hidden, requires specific dialogue branches earlier) offers Sith-adjacent guidance. This path is flagged but not implemented in launch — it's the seed for future dark-side content.

### 4.3 Why Village-style works for us

- **Thematic:** "A Jedi showing up in a cantina is an event" — because their path was earned in secret, not chargen-selected.
- **Player retention:** A ~10-session quest chain keeps committed players engaged without forcing a grind.
- **Admin-neutral:** No admin gatekeeping. Unlock is earned via play.
- **Narrative richness:** Three paths from one unlock gives roleplay texture.
- **Engine-friendly:** Fits cleanly into the existing quest chain / narrative memory system.

### 4.4 Village location — recommendation

I recommend hiding the village in the **Dune Sea wilderness region on Tatooine**, not Coruscant Underworld. Reasoning:

- Tatooine fits the "hermit retreat" archetype perfectly (Obi-Wan did it).
- The Dune Sea wilderness was already contemplated in `wilderness_system_design_v1.md`; it can host the Village as a hand-authored landmark within the coordinate grid.
- Coruscant Underworld is urban and hostile — doesn't fit the "reclusive elder" aesthetic.
- Separating the Jedi unlock geographically from Coruscant Temple (where canonical Jedi are) makes the Village feel distinct from the Order.

The Dune Sea wilderness region is built after launch content stabilizes, so the Village quest chain is a **post-launch content drop** — but the design doc includes it so the architecture supports it from day 1.

---

## 5. Era Policy Knobs

`data/worlds/clone_wars/era.yaml`:

```yaml
era:
  code: clone_wars
  name: "Clone Wars"
  description: >
    Mid-war, approximately 20 BBY. The Republic fights the Separatist
    alliance across the Outer Rim. Jedi serve as generals, clone troopers
    fill the Grand Army ranks, and Count Dooku leads the CIS publicly
    while the Sith direct events from the shadows.
  timeline_reference: "~20 BBY"
  schema_version: 1

policy:
  # Force policy
  force_chargen_allowed: false          # Cannot select Jedi at chargen default
  force_sensitive_chargen: village_gated # Requires Village quest chain to unlock
  lightsaber_availability: restricted_jedi  # Issued by Order, or earned via Village
  force_suppression: none               # No Inquisitorial pressure
  dark_side_detectability: high         # Using DS in public draws attention
  village_location: tatooine_dune_sea   # Seed data for Village quest

  # Faction set
  factions: [republic, cis, jedi_order, hutt_cartel, bhg, independent]
  npc_only_factions: [sith, separatist_council]

  # Starting defaults
  starting_room_slug: westport_arrivals
  starting_faction: independent
  starting_credits_default: 500

  # Era-specific flavor defaults
  default_trooper_type: clone
  default_imperial_substitute: republic
  default_rebel_substitute: cis
  hutt_cartel_stance: neutral_profiteering

content_refs:
  zones: zones.yaml
  planets:
    - planets/coruscant.yaml
    - planets/kuat.yaml
    - planets/geonosis.yaml
    - planets/kamino.yaml
    - planets/tatooine.yaml
    - planets/nar_shaddaa.yaml
  wilderness:
    - wilderness/coruscant_underworld.yaml
  npcs: npcs.yaml
  housing_lots: housing_lots.yaml
  test_character: test_character.yaml
  test_jedi: test_jedi.yaml          # Separate god-mode Jedi account

# Policy enforcement requirements (what must be wired)
policy_enforcement:
  force_chargen_allowed_is_enforced: true
  force_sensitive_chargen_is_enforced: true
  lightsaber_availability_is_enforced: true
  starting_faction_is_enforced: true
```

The `test_jedi` field is new — per your direction to preserve the Test Jedi god-mode account across the pivot. It's a second test character definition specifically for a fully-leveled Jedi for dev-time testing of Jedi content.

---

## 6. Exit Discipline — Preventing the Collision Bug Class

### 6.1 Why this section exists

The tutorial bugfix history (`tutorial_bugfix_design_v1.md`) documented **21 exit collisions across 4 planets** that rendered **21 rooms silently unreachable**, including Kayson's Weapon Shop which blocked the starter quest chain. Root cause: `create_exit()` silently drops duplicates when `(room_id, direction)` collides.

The YAML world-extraction design's §5.5 validation list includes collision detection as a hard-fail. That's the right floor. This section adds higher-level authoring discipline so collisions are avoided at design time, not caught at boot time.

### 6.2 The taxonomy of exit failure

The 21-collision bug revealed several distinct failure modes:

1. **Hub-overcrowding**: Market District (room 8) had 11 destinations but only 10 cardinal directions + up + down. Every destination beyond the 12th collided.
2. **Symmetric-direction assumption**: Exits are naturally defined bidirectionally (`(from, to, forward, reverse)`), and authors often picked "the obvious reverse" — south if forward is north — without checking the destination's existing exits for conflicts.
3. **True duplicates**: At least one case (`103↔117`) was a complete duplicate of an already-existing bidirectional exit pair.
4. **Third-direction collisions**: A room can have exits to A (north) and B (northeast) defined correctly, but when a new exit to C also tries to use north from C's side, the reverse collides.

### 6.3 The rules

**Rule 1: Budget directions per room.**

Each room has a fixed budget of 12 standard directions:

```
north, south, east, west,
northeast, northwest, southeast, southwest,
up, down, in, out
```

Plus unlimited **named exits** (e.g., `bank`, `market`, `wreckage`, `temple`, `vent`, `drydock`, `manhole`). Named exits are first-class in the engine — the parser treats the first word of a typed command as a direction key, so `go bank` and `bank` both work.

**Rule 2: Hubs use named exits, not cardinals, for sub-destinations.**

A zone's central hub — the room most other rooms connect *to* — is a hub. Hubs systematically exceed 12 cardinals. The rule: hubs use cardinals for zone-to-zone connections and named exits for zone-internal destinations.

Example for Coruscant `westport_arrivals` (starting hub):
- `east` → senate_district (zone-to-zone)
- `west` → coco_town (zone-to-zone)
- `south` → bh_transit_platform (zone-to-zone, to gateway of Southern Underground)
- `north` → customs_inspection (hub-internal)
- `customs` → customs_inspection (named duplicate of `north` — convenience alias, same destination)
- `cantina` → arrivals_cantina (named, zone-internal)
- `board` → job_board_kiosk (named, zone-internal)
- `up` → observation_deck (vertical)

8 exits, 3 named. No risk of collision.

**Rule 3: YAML schema enforces per-room direction uniqueness.**

The world YAML uses an **explicit per-room exits block** rather than a flat global exit list. Proposed schema:

```yaml
rooms:
  - slug: westport_arrivals
    name: "Westport Arrivals Hall"
    zone: westport_district
    description: |
      The wide, polished arrivals hall of Coruscant's Westport...
    exits:
      east: senate_grand_approach
      west: coco_town_plaza
      south: transit_platform_bravo
      north: customs_inspection
      up: observation_deck
      customs: customs_inspection      # named alias of north
      cantina: arrivals_cantina
      board: job_board_kiosk
```

Vs. the current flat-list approach:

```python
EXITS = [
  (0, 7, "east", "west to Westport"),  # senate_grand_approach reverse
  ...
]
```

**The schema change is the key defense.** Under the per-room `exits:` block, a YAML author cannot define two exits with the same direction key from the same room without visibly writing the duplicate. YAML keys are unique per mapping; a duplicate direction on the same room is a parse error.

**Rule 4: Exits are declared on the "from" side only.**

In the old EXITS tuple, each row defined forward and reverse simultaneously — which is where collision logic got tangled. In the new schema:

- Room A declares `east: room_b`
- Room B separately declares `west: room_a`

The loader walks both and confirms round-trip consistency. If Room A says `east: room_b` but Room B has no `west: room_a`, that's a warning (one-way exit, which is sometimes intentional — e.g., a vent you fall down but can't climb back up). If Room B has `west: room_c` instead, that's a consistency error.

**Rule 5: One-way exits must be explicit.**

YAML annotation for exits that don't round-trip:

```yaml
rooms:
  - slug: rooftop_vent
    exits:
      north: rooftop_proper    # normal two-way
      down: maintenance_shaft
        one_way: true           # acknowledged one-way (fall down, can't climb back)
```

The loader validates: if `one_way: true` is absent, both ends must declare matching exits.

**Rule 6: Pre-commit validation script.**

Ship `scripts/validate_world_exits.py` as a pre-commit hook:

```python
# Checks per-room:
# - No direction key collisions (enforced by YAML syntax)
# - All exit targets resolve to real room slugs
# - Every two-way exit has a matching entry on the other side
# - Hub rooms (>10 exits) report direction-budget usage
# - Named exits don't collide with system reserved words (e.g., "look", "say")

# Checks globally:
# - No orphaned rooms (rooms with zero exits in or out)
# - No unreachable rooms from starting_room_slug (BFS from start)
```

Run this before every commit that touches world YAML. The test suite should also run it on every CI pass.

**Rule 7: Hub audits for new construction.**

For any room projected to have more than 8 exits during design:

- List destinations first
- Assign directions second
- If cardinals exceed budget, convert overflow to named exits *before* writing YAML

This is a **design discipline**, not an engine rule. But it lives in this doc so it's captured.

### 6.4 Applied to Coruscant Westport

Let me walk through `westport_arrivals` as it would actually be authored:

**Step 1: List destinations.**

Westport arrivals connects to:
1. Customs inspection (adjacent, zone-internal)
2. Arrivals cantina (adjacent, zone-internal)
3. Job board kiosk (adjacent, zone-internal)
4. Observation deck (vertical, zone-internal)
5. Senate district (zone-to-zone)
6. CoCo Town (zone-to-zone)
7. Southern Underground gateway (zone-to-zone, via transit platform)
8. Jedi Temple transit (zone-to-zone, via speeder bay)

**Step 2: Assign directions, cardinals first.**

- `east` → senate_grand_approach (zone-to-zone)
- `west` → coco_town_plaza (zone-to-zone)
- `south` → transit_platform_bravo (zone-to-zone)
- `north` → customs_inspection (zone-internal, but it's the one most-visited, so cardinal is fine)
- `up` → observation_deck
- 3 cardinals unused (northeast, northwest, southeast, southwest, down, in, out — plenty of room)

**Step 3: Named exits for remaining destinations.**

- `cantina` → arrivals_cantina
- `board` → job_board_kiosk
- `temple` → jedi_temple_speeder_bay (zone-to-zone; named because "north" is taken for customs)

**Step 4: Sanity check.**

Total: 5 cardinals + 3 named = 8 exits. Direction budget has 7 unused cardinals (budget is 12, used 5). Well within safety. No collision possible.

**Step 5: YAML.**

```yaml
- slug: westport_arrivals
  name: "Westport Arrivals Hall"
  zone: westport_district
  map: { x: 10, y: 20 }
  description: |
    The high, polished arrivals hall of Coruscant Westport stretches before
    you — a crystalline cathedral of glassteel, steel, and blue-lit walkways.
    Arrival gates line the eastern wall; customs inspection lanes run north;
    a news-board tower displays holographic headlines above the central
    concourse. A cantina pulses with music off to the side, and beyond the
    western archway, the bustle of CoCo Town spills in.
  exits:
    east: senate_grand_approach
    west: coco_town_plaza
    south: transit_platform_bravo
    north: customs_inspection
    up: observation_deck
    cantina: arrivals_cantina
    board: job_board_kiosk
    temple: jedi_temple_speeder_bay
```

And on every destination room, a matching reverse entry exists (e.g., `senate_grand_approach` has `west: westport_arrivals`).

### 6.5 Why the tutorial bug won't repeat

Under the old system: 21 collisions across 4 planets, silently dropped at build time, discovered only via live playtest.

Under the proposed system:
- **Per-room direction keys are YAML-unique** — a duplicate is a parse error, not a silent drop
- **Round-trip consistency** is validated by the loader — missing reverses fail the build
- **Hub audits during design** prevent direction budget overruns
- **Pre-commit validation script** catches issues before code review
- **BFS unreachability check** catches accidentally-orphaned rooms

This is the floor plus four layers of defense. The bug class should be dead.

---

## 7. Coruscant Underworld Wilderness — Launch Region

Replaces Dune Sea as the launch wilderness region per user direction.

### 7.1 Concept

The Coruscant Underworld is a coordinate-grid wilderness region below the Southern Underground zone. Unlike Dune Sea (open desert), this is a **3D layered region** — you descend via levels, and each level has coordinate tiles.

### 7.2 Region structure

Per `wilderness_system_design_v1.md`:

- Region slug: `coruscant_underworld`
- Grid dimensions: ~40×40 tiles per level, 3 levels deep (Mid, Low, Bottom)
- Terrain types: `alley`, `factory_ruins`, `sewer`, `abandoned_market`, `shaft_drop`, `collapsed_plaza`, `transit_tunnel`

Named landmarks anchored within the grid (these are rows in the `rooms` table with coordinate metadata):
- `black_sun_crawler_hideout` — Mid level, coord (20, 15). Bounty-hunter mission anchor.
- `forgotten_jedi_shrine` — Low level, coord (12, 38). Jedi Village Act 1 foreshadow (not the Village itself, just a sign).
- `abandoned_factory_dominus` — Low level, coord (30, 5). Smuggler contraband cache.
- `uscru_entertainment_district_fringe` — Mid level, coord (8, 20). NPC cluster, jobs hub.
- `maze_the_reaper_territory` — Bottom level, coord (25, 25). High-danger hostile NPC zone. Deterrent for low-level characters.
- `transit_shaft_alpha` — vertical connection Mid ↔ Low
- `transit_shaft_beta` — vertical connection Low ↔ Bottom
- `surface_manhole_to_southern_underground` — connection from Mid level up to Southern Underground zone

### 7.3 Gameplay role

- **Bounty hunters** — hostile NPCs for CP-fueled combat. Black Sun-flavored. Named hostiles as miniboss-class content.
- **Smugglers** — contraband caches to find and retrieve.
- **Exploration** — terrain-filter encounters (Director AI-flavored), hazard tiles (toxic sublevel air), random events.
- **Act 1 Jedi sign** — the `forgotten_jedi_shrine` landmark is one of the trigger sites for passive Force-sign accumulation.

### 7.4 Why this over Dune Sea for launch

- **Geographic integration with starting hub**: Coruscant is where new players land. A 5-minute walk from `westport_arrivals` to the Underworld gives players something to *find* in session one.
- **Thematic integration with faction content**: BHG jobs, smuggler work, underworld ambiance — all the things players of the relevant archetypes will seek out.
- **Vertical structure** tests the wilderness engine's level-handling, which is a prerequisite for future multi-level ships and player housing tiers 5+.
- **Dune Sea still built**, just after Coruscant Underworld — Dune Sea hosts the Jedi Village (§4.4) and launches as a second wilderness region post-launch.

---

## 8. Director AI & World Lore Pivot

This is the single biggest *content* change in the pivot after the world YAML itself. The current Director AI and world lore system are **saturated with GCW-specific material** — rewriting them is not optional, and the scope is larger than it first appears because Director AI logic itself hardcodes GCW faction identity.

### 8.1 Why this matters

The Director AI isn't just decoration. It drives:

- **Atmospheric coherence** — the "feel" of the galaxy in ambient events, news headlines, NPC dialogue context
- **Faction dynamics** — which factions rise and fall per zone, which milestone events fire
- **Per-zone narrative tone** — injected into every ambient event and Director-generated event
- **NPC dialogue grounding** — `ai/npc_brain.py` pulls relevant lore entries into NPC prompts based on player dialogue keywords. If the Hutt Cartel entry still says "the Empire tolerates them," every Hutt NPC reinforces GCW framing.

If we pivot the world to Clone Wars but leave the Director/lore GCW-keyed, players get a coherent Clone Wars surface with a GCW-shaped Director mind underneath. Immersion breaks immediately.

### 8.2 Live state audit

Verified against the uploaded codebase (`/tmp/sw_mush/SW_MUSH/`, session 55 snapshot):

**`engine/world_lore.py`** — 813 lines, 61 seeded entries in `SEED_ENTRIES`. Triage:

| Category | Count | Disposition |
|---|---|---|
| GCW-exclusive (must delete) | 15 | Galactic Empire, Rebel Alliance, Imperial Military Structure, Moffs, COMPNOR, Imperial Intelligence, Stormtrooper Variants, Imperial Star Destroyers, TIE Fighter Corps, Tarkin Doctrine, Imperial Customs, Imperial Law Infractions, Owen and Beru Lars, General Airen Cracken, Imperial Peace-Keeping Certificate, Imperial Enforcement DataCore, Imperial Lift-Mines |
| Dropped-planet (delete or dormant) | 3 | Kessel, Corellia, Corellian Shipyards, Nar Shaddaa *(wait — Nar Shaddaa stays; re-reading: the entry stays but needs reframing)*, Kessel Spice Mining |
| Location-specific, needs reframe | ~8 | Mos Eisley *(era-neutral enough to largely keep)*, Nar Shaddaa, Nar Shaddaa Criminal Networks, Chalmun's Cantina, Gep's Grill, Spaceport Express, Mos Eisley Slang, Wuher *(all largely era-agnostic but any GCW references get stripped)* |
| Era-agnostic (keep as-is) | ~35 | The Force, Galactic Credits, Smuggling, BHG, Hutt Cartel, Jawa Society, Tusken Raiders, Tatooine's Twin Suns, Speculative Trading, Trade Good Categories, Drop-Point Delivery, Black Market, Loan Sharks, Ship Modification Basics, Hyperdrive Classes, Astrogation Hazards, Docking Fees, Banthas, Dewbacks, Mynocks, Rancor, Bounty Hunter Creed, Bounty Classifications, Bounty Hunter Guilds, Three Types of Bounty Hunters, SEPI Principle, Bounty Posting Format, Jury-Rigging, Transponder Codes, BoSS, Cybernetic Enhancements, How Blasters Work, Acquiring Blaster Gas, Merr-Sonn Ion Mines, Computer Data Files |

**Observation:** the GG10 Bounty Hunters extraction (8 entries) is already in the codebase, providing rich era-agnostic BHG lore. That's a partial mitigation for GG11 being absent.

**Clone Wars additions needed** (not currently in the database):

| Entry | Source | Priority |
|---|---|---|
| Galactic Republic | Film/Legends canon | Critical |
| Confederacy of Independent Systems | Film/Legends canon | Critical |
| Separatist Council | Legends canon | High |
| Count Dooku | Film canon | High |
| General Grievous | Film/Clone Wars canon | High |
| The Sith (public knowledge as legend) | Film/Legends canon | High |
| The Jedi Order (Clone Wars) | Film/Jedi Academy SB | Critical |
| Jedi Temple on Coruscant | WotC Coruscant book | Critical |
| The Jedi Council | Film/Jedi Academy SB | Critical |
| Master & Padawan | Jedi Academy SB | High |
| Lightsaber construction | R&E Core + Jedi Academy SB | Medium |
| Republic Grand Army | Film canon + Legends | Critical |
| Clone Trooper origins | Film canon | Critical |
| Kaminoan Cloners | Film/Legends canon | High |
| Republic Navy (Venators, Acclamators) | Clone Wars canon | High |
| Kuat Drive Yards | WotC Coruscant book | High |
| Outer Rim Sieges | Clone Wars canon | Medium |
| Droid Armies (B1, B2, Droideka, Magnaguard) | Film canon | High |
| The Trade Federation | Film canon | Medium |
| Techno Union / Banking Clan / Commerce Guild | Film canon | Medium |
| Chancellor Palpatine's Emergency Powers | Film canon | Medium |
| The Galactic Senate | WotC Coruscant book | High |
| CoCo Town / Dex's Diner | WotC Coruscant book | Low |
| Coruscant Underworld | WotC Coruscant book + Clone Wars canon | High |
| Invisec / "Gilded Cage" | WotC Coruscant book (reframed) | Medium |
| Mandalore (Clone Wars neutral) | Clone Wars canon | Medium |
| Ryloth Liberation | Clone Wars canon | Low (post-launch) |
| Geonosian Hives | Film canon | Medium |
| Petranaki Arena | Film canon | Low |
| Holonet News during war | Film/Legends canon | Low |
| War Profiteering | Clone Wars canon | Medium |

**Count:** ~30 critical/high-priority new entries needed. Plus ~10 medium/low that round out the lorebook.

**End state of `SEED_ENTRIES`:** ~50-55 entries (down from 61 GCW; delete 15, reframe 10, add 30, keep 35-ish). Similar magnitude, completely different flavor.

### 8.3 `data/zones.yaml` — narrative tones

14 existing entries, all GCW-keyed, verified against live file. Every one requires rewriting. Example of the kind of rewrite needed:

**Current (Mos Eisley):**
> Dangerous and lawless. Deals happen in whispered conversations. Everyone is armed. Trust is the scarcest resource. The heat is oppressive and the twin suns bleach everything white. Strangers are watched carefully. **The Empire's grip is loose here — the Hutts and local crime lords hold the real power.**

**Clone Wars rewrite (Mos Eisley):**
> Dangerous and lawless. Deals happen in whispered conversations. Everyone is armed. Trust is the scarcest resource. The heat is oppressive and the twin suns bleach everything white. Strangers are watched carefully. **The Republic cares about the Outer Rim only when clones or credits are involved — the Hutts and local crime lords hold the real power. War refugees and Separatist recruiters drift through the streets alongside the usual smugglers.**

The mechanical difference: "Empire" → "Republic," "Imperial grip" → "Republic concern," plus a sentence-length addition that establishes the war's shadow falling on Tatooine without occupying it.

**New Clone Wars zones requiring fresh narrative tone authoring** (no existing equivalents):

| Zone | Estimated tone |
|---|---|
| `coruscant_westport` | Efficient, gleaming, cosmopolitan — arrivals from a thousand worlds |
| `coruscant_senate` | Stately, tense, performative — the Republic at parade despite the war |
| `coruscant_jedi_temple` | Serene, austere, quietly depleted — half the Knights are in the field |
| `coruscant_coco_town` | Lively, mixed, opinionated — gossip about the war flows with the caf |
| `coruscant_calocour_heights` | Pushy, branded, saturated — war propaganda from every angle |
| `coruscant_southern_underground` | Seedy, wary, predatory — the Jedi don't patrol down here |
| `coruscant_gilded_cage` | Tense, resilient, watchful — the non-Human districts feel the war's othering |
| `kuat_main_spaceport` | Efficient, militarized, bureaucratic — permits and papers |
| `kuat_orbital_ring` | Industrial, secretive, colossal — capital ships under construction everywhere |
| `kuat_city_embassy` | Decorous, guarded, aristocratic — merchant houses at their dinner tables |
| `geonosis_stalgasin_surface` | Hostile, alien, industrial — Separatist soil |
| `geonosis_deep_hive` | Claustrophobic, insectoid, ancient — Geonosian ruling class |
| `geonosis_petranaki_arena` | Brutal, ceremonial, echoing — gladiatorial bloodsport |
| `geonosis_droid_foundries` | Mechanical, relentless, assembly-line — the war's industrial heart |
| `kamino_tipoca_city` | Sterile, orderly, purposeful — clone production at scale |
| `kamino_cloning_facilities` | Clinical, genetic, disquieting — life made to order |
| `kamino_ocean_platforms` | Wind-blown, spare, oceanic — aiwha cries at dusk |

17 new tone entries + 14 rewrites = 31 narrative-tone authoring tasks. Plus the space-zone tones (currently 4: space_tatooine, space_nar_shaddaa, space_kessel, space_corellia) need updating — Kessel/Corellia drop, Nar Shaddaa/Tatooine rewrite, plus new space_coruscant, space_kuat, space_geonosis, space_kamino.

### 8.4 Director AI engine — structural GCW coupling

**This is the part that caught me off guard.** `engine/director.py` (1,787 lines) doesn't just have GCW *content* in its prompt text — it has GCW *structure* in its code.

Verified in the live file:

```python
# Line 48 — hardcoded faction set
VALID_FACTIONS = frozenset({"imperial", "rebel", "criminal", "independent"})

# Lines 58-63 — per-zone baseline scores keyed to GCW factions
ZONE_BASELINES = {
    "spaceport":  {"imperial": 65, "rebel": 8,  "criminal": 45, "independent": 25},
    "streets":    {"imperial": 55, "rebel": 12, "criminal": 50, "independent": 35},
    "cantina":    {"imperial": 40, "rebel": 15, "criminal": 65, "independent": 40},
    "shops":      {"imperial": 50, "rebel": 10, "criminal": 55, "independent": 40},
    "jabba":      {"imperial": 20, "rebel": 5,  "criminal": 85, "independent": 10},
    "government": {"imperial": 80, "rebel": 5,  "criminal": 20, "independent": 20},
}

# Lines 84-103 — milestone events hardcoded to imperial/rebel narrative
MILESTONE_EVENTS = [
    ("imperial", 70, "imperial_grip",
     "The Empire tightens its grip on Mos Eisley. Stormtrooper patrols double.",
     "imperial_crackdown", 120),
    ("imperial", 85, "imperial_martial_law", ...),
    ("rebel", 35, "rebel_whispers",
     "Rebel propaganda appears on cantina walls. Something is stirring.", ...),
    # ... 5 more in the same vein
]

# Lines 111-113 — alert-level math keyed to "imperial" score specifically
class AlertLevel(str, Enum):
    LOCKDOWN = "lockdown"       # Imperial >= 70
    HIGH_ALERT = "high_alert"   # Imperial 50-69
    STANDARD = "standard"       # Imperial 30-49
```

Total: 30 direct string references to GCW faction keys (`"imperial"`, `"rebel"`, `"criminal"`) across `director.py`. Plus the AlertLevel enum whose thresholds are computed as a function of the `imperial` score specifically.

**This is engine work, not content.** The Director faction model needs to move from source constants to data — probably a new `data/director_config.yaml` that declares:

```yaml
director:
  factions: [republic, cis, jedi_order, hutt_cartel, bhg, independent]

  zone_baselines:
    coruscant_westport:   { republic: 70, cis: 5,  jedi_order: 20, hutt_cartel: 10, bhg: 15, independent: 30 }
    coruscant_senate:     { republic: 85, cis: 5,  jedi_order: 40, hutt_cartel: 2,  bhg: 5,  independent: 15 }
    coruscant_jedi_temple:{ republic: 60, cis: 0,  jedi_order: 95, hutt_cartel: 0,  bhg: 0,  independent: 5  }
    tatooine_mos_eisley:  { republic: 15, cis: 10, jedi_order: 2,  hutt_cartel: 60, bhg: 35, independent: 55 }
    # ... one row per zone
    
  milestone_events:
    - faction: republic
      threshold: 70
      event_key: republic_presence_heavy
      headline: "Republic clone patrols become routine. Venators park overhead."
      event_type: republic_patrol_surge
      duration: 120
    - faction: cis
      threshold: 60
      event_key: cis_infiltration
      headline: "Separatist sympathizers grow bolder. Holo-graffiti appears overnight."
      event_type: cis_propaganda_wave
      duration: 120
    # ... similar for jedi_order, hutt_cartel, bhg
  
  alert_level:
    primary_faction: republic   # which faction's score drives alert level
    thresholds:
      lockdown: 70
      high_alert: 50
      standard: 30
    # under 30 → RELAXED
```

The Director engine is refactored to read `director_config.yaml` at init, populate `VALID_FACTIONS`, `ZONE_BASELINES`, and `MILESTONE_EVENTS` from it. AlertLevel keyed to the primary faction (Republic for CW, Imperial for GCW). Era-switching means dropping in a new config, not editing Python.

**Scope:** this is a ~200-line refactor of `director.py` plus a new YAML file plus test updates. Part of the pivot enablement drop. It's not optional — without this, the pivot breaks the Director.

### 8.5 Director system prompt rewrite

Verified at `director.py` line 678-711, the Director's system prompt is completely GCW-keyed:

> "You are the Director AI for a Star Wars MUSH set in Mos Eisley, Tatooine..."
> "The Empire reacts to resistance with escalation, not retreat."
> "The criminal underworld fills any vacuum the Empire leaves."
> "The Rebel Alliance operates in shadows; their influence is felt through sabotage and propaganda..."
> "Tatooine is a backwater. The Empire cares about order, not ideology."

Every one of those principles needs replacement. Draft Clone Wars version:

> "You are the Director AI for a Star Wars MUSH set in the Clone Wars era, centered on Coruscant with reach to Kuat, Geonosis, Kamino, Tatooine, and Nar Shaddaa..."
>
> Principles:
> - The Republic fights a two-front war: Separatists in the Outer Rim, corruption in the Senate. Neither front is fully visible to the other.
> - The Jedi Order is present but depleted. A Jedi showing up changes the tone of a scene.
> - The Confederacy of Independent Systems is a coalition of greed wearing the robes of rebellion. Their droid armies are relentless but impersonal.
> - The Hutt Cartel profits from both sides. They will sell to anyone with credits.
> - Coruscant is the galaxy's heart — gleaming above, rotting below. The upper levels deny the war; the lower levels live it.
> - Events should create OPPORTUNITIES for players, never OBLIGATIONS.
> - Consequences should feel proportional and narratively logical.

This is a ~40-line edit to one string. Trivial mechanically, important for atmospheric coherence.

### 8.6 Ambient events YAML

`data/ambient_events.yaml` — 93 lines, only 2 GCW references. Mostly weather/lighting/ambient flavor, largely era-agnostic. Scope: light rewrite pass to strip the 2 GCW references and extend to cover the new 17 Clone Wars zones (each zone wants ~10 ambient lines per the Director design doc). **Estimate: ~170 new ambient lines + 2 rewrites.**

### 8.7 NPC brain — automatic inheritance

`ai/npc_brain.py` (366 lines) has only 1 GCW reference total. It's era-agnostic by design — it pulls relevant lore dynamically from the world_lore table based on player dialogue keywords and NPC context. **When we rewrite the lore, NPC dialogue adapts automatically.** No direct work needed here.

### 8.8 Scope summary

| Workstream | Scope | Type |
|---|---|---|
| World lore content rewrite | 15 delete, 10 reframe, 30 new, 35 keep | Content |
| Zone narrative tones | 14 rewrites + 17 new + ~4 space zones | Content |
| Director system prompt rewrite | 1 string, ~40 lines | Content |
| Director engine data-fication | ~200-line refactor + new YAML config | **Engine** |
| Ambient events YAML | 2 rewrites + 170 new lines | Content |
| NPC brain | 0 changes | — |

**Call this "Drop 6: Director/Lore Pivot."** Delivered as a single cohesive content-plus-engine drop because they interdepend — you can't ship the new lore without the engine that reads the new faction set, and you can't test the new engine without new lore for the new factions.

### 8.9 Sourcebook gaps that hurt most here

- **Jedi Academy Sourcebook** missing = Jedi Order lore entries have to be authored from film/Legends canon. Entries like "The Jedi Council," "Master & Padawan," "Lightsaber Construction" would be materially richer with this book. Medium-high impact.
- **GG11 Criminal Organizations** missing = Hutt Cartel, Black Sun, BHG guild structure lore would be richer. Low-medium impact — GG10 Bounty Hunters extraction already covers the hunter side, and existing Hutt entries in world_lore.py are adequate.

Neither gap is blocking. Both would improve v4 if uploaded later.

---

## 9. Sourcebook Audit (Updated)

### 8.1 Available in project knowledge

| Book | Format | Era relevance | Pass decision |
|---|---|---|---|
| WEG40120 (R&E Core) | Text | Era-agnostic rules | **Use** for Jedi/Force rules |
| WEG40092 (Imperial Sourcebook) | Text | GCW-specific | **Skip** |
| WEG40069 (GG7 Mos Eisley) | Zip/JPEG | Tatooine, era-agnostic | **Use** for Tatooine reskin |
| WEG40124 (GG1 A New Hope) | Zip/JPEG | ANH/GCW | Partial — planet stats era-agnostic |
| WEG40027 (GG6 Tramp Freighters) | Zip/JPEG | Era-agnostic smuggler rules | **Use** for Freighter Captain template |
| WEG40048 (GM Kit) | Zip/JPEG | Era-agnostic tools | Skip — GM tools, not content |
| WEG400931/932 (SW Sourcebook 2e) | Zip/JPEG | Era-agnostic tech/ships | **Use** for ship stats |
| **Coruscant and the Core Worlds (WotC d20)** | **Scanned (rasterized)** | **Rise of the Empire + other eras** | **USE HEAVILY** for Coruscant + Kuat |

### 8.2 The WotC book — integration notes

- **System mismatch**: d20 stat blocks don't translate directly to WEG D6. We use this book for **lore, layout, NPCs-as-flavor, planetary descriptions, adventure hooks** — not for stat conversions. Stats are WEG D6 throughout.
- **Era match is solid**: Each planet chapter opens with era-specific context. The Rise of the Empire era section is written for Clone Wars.
- **Direct harvest for Coruscant**: Jedi Temple five-spire architecture, Galactic Senate Rotunda (1,024 floating platforms), Westport, Calocour Heights, Column Commons, Southern Underground, Coruscant Opera House, Skydome Botanical Gardens, Glitannai Esplanade, Western Sea, Pliada di am Imperium, Garbage Pits, "Invisec" (adapted as Gilded Cage for our era).
- **Direct harvest for Kuat**: KDY orbital array (15-zone diagram), planetside permit system, merchant-house intrigue (Andrim vs. Purkis), Kuati Security Forces, KDY headquarters / Main Spaceport / drydocks / warehouses / factories.

### 8.3 Still-needed books

Per user mention: **Galaxy Guide 11 (Criminal Organizations)** and **Jedi Academy Sourcebook** could not be uploaded. These would be valuable for:

- **GG11**: Hutt Cartel deep organization, Black Sun structure, BHG canonical hierarchy — would directly enrich the faction roster detail and BHG chapter house content on Coruscant. **Medium-high priority** for the pivot.
- **Jedi Academy Sourcebook**: Although it's written for the post-war New Republic Jedi era, the core Jedi Order customs (Master/Padawan relationships, training hierarchy, lightsaber construction) translate backward to Clone Wars. **High priority** for the Jedi Padawan template and Village quest chain authoring.

Neither is blocking. If you can get them into project knowledge, I'll integrate in a v3 pass. If not, we work from what's available plus Wookieepedia cross-reference.

### 8.4 The WEG gap — still true

WEG never published a Clone Wars supplement (product line ended 1998, Episode I released 1999). All Clone Wars-specific content draws from:
1. Film canon
2. Legends canon (*The Clone Wars* series, novels, comics)
3. Creative extrapolation (labeled as such)
4. WotC d20 Coruscant book (which explicitly covers Rise of the Empire era — partial workaround)

---

## 10. Tutorial Rework

### 9.1 Scope

The current tutorial has 6 profession chains (Smuggler, Hunter, Artisan, Rebel, Imperial, Underworld) built around GCW lore. The user direction: **rework, don't regress**. The new tutorial must cover the Clone Wars faction set, with room to grow.

### 9.2 Proposed Clone Wars tutorial chains

Eight chains for launch (up from six), mapping to the eight joinable faction-archetype axes:

1. **Republic Soldier** (Clone trooper or Naval Officer) — Kamino or Coruscant start
2. **Republic Intelligence** — Coruscant start, covert ops flavor
3. **Jedi Path** (hidden/locked until Village unlock — stub in tutorial, unlock post-Village)
4. **Separatist Commando** (CIS loyal warrior) — Geonosis start
5. **Separatist Agent** (CIS infiltrator/diplomat) — Coruscant start with CIS-hidden flavor
6. **Bounty Hunter** — Nar Shaddaa or Coruscant underworld start
7. **Smuggler** — Tatooine or Nar Shaddaa start
8. **Shipwright/Trader** — Kuat start

Each chain: 4-6 steps, introduces the player to their starting zone, faction HQ, mission board, relevant tools, and sets them up with 1-2 clear next actions.

### 9.3 Tutorial structural design

Borrows from current tutorial's structure:
- Intro room + concierge NPC that identifies player archetype
- Branch to profession-specific chain
- Each step unlocks next via NPC conversation + action
- Achievement granted on chain completion
- Graduation: player drops into regular play with faction rep and starter equipment

What's expanded vs. current:
- **Faction preview before commitment**: during the intro, the player walks through each faction's HQ briefly via speeder tour (Director-AI narrated), sees faction-specific benefits, then commits. This is the "show, don't gate" principle from the existing tutorial factions addendum.
- **Jedi seed**: during the tour, one ambient event flags a "Force sign" at ~50% probability. This is the introduction to the Village-chain mechanic, bundled into tutorial completion so every character has a 50/50 starting trajectory toward potential Force sensitivity.
- **Expansion slot**: the tutorial is designed so that additional profession chains (e.g., Scout, Medic, Mercenary) can be added as separate drops without refactoring. Each chain is a self-contained YAML file.

### 9.4 Scope estimate

Tutorial rework is a substantial drop — estimated similar to the original tutorial's build-out (6 chains of ~4-6 steps each = ~30 chain-steps + intro + graduation + Director prompts). Target: **one full implementation session's worth of work**. Should be scheduled after world YAML is in place so chain references resolve.

---

## 11. Standalone-Compatibility Notes

Updated from v2 to reflect the Director/lore scope surfaced in §8.

### 11.1 Can be done entirely in this parallel track, no dependencies

- This design doc.
- Complete Clone Wars era YAML content in target `data/worlds/clone_wars/` schema, produced as draft files ready to drop in when the loader lands.
- Faction roster for Clone Wars in YAML.
- All six planets' YAML (rooms, exits, NPCs) authored per §6 exit discipline.
- Coruscant Underworld wilderness region YAML.
- New template set design (including Shipwright).
- Jedi Village quest chain design (authoring the quest chain itself is implementation work; the design lives in this doc).
- **World lore content authoring (§8)** — the ~30 new Clone Wars lore entries, written as a `SEED_ENTRIES` patch file ready to drop into `engine/world_lore.py`. Content-only, no engine dependency.
- **Zone narrative tone rewrites and authoring (§8.3)** — all 14 rewrites + 17 new zone tones, as a replacement `data/zones.yaml`.
- **Director system prompt rewrite (§8.5)** — as a design snippet ready to drop into `engine/director.py`.
- **Ambient events YAML authoring (§8.6)** — ~170 new ambient lines for new zones.
- New tutorial chain designs.

### 11.2 Blocked on world-extraction refactor landing

Same as v1/v2: the `data/worlds/<era>/` loader must exist before any of this boots as an alternate era. Per `world_data_extraction_design_v1.md`, this is a ~4-drop prerequisite that benefits both Clone Wars and wilderness.

### 11.3 Hard-coupled to engine changes ("pivot enablement drop")

Updated for v3 — the list grew.

1. **Force-sensitive chargen gating** (Village-gated) — chargen reads `force_sensitive_chargen: village_gated` and hides Jedi Padawan template until character has the Village-completion flag.
2. **Lightsaber availability** — vendor droid and loot table code honors `lightsaber_availability: restricted_jedi`.
3. **Default starting faction** — chargen default.
4. **Village sign ambient event** — passive Force-sign accumulation system. New subsystem, small.
5. **Village unlock state machine** — character flags tracking Act 1 signs, Village entry, Act 2 completion, Act 3 choice.
6. **Test Jedi preservation** — ensure `test_jedi.yaml` boots alongside `test_character.yaml` and bypasses Village gating.
7. **Director engine data-fication (§8.4)** — refactor `engine/director.py` to read `VALID_FACTIONS`, `ZONE_BASELINES`, `MILESTONE_EVENTS`, and `AlertLevel` configuration from a new `data/director_config.yaml`. ~200 lines of source changes, new YAML config file, test updates.

Items 1-6 are small. Item 7 is the new heavyweight — a ~200-line refactor touching 30 hardcoded faction-key references across 1,787 lines of `director.py`. It belongs in a dedicated sub-drop so the whole pivot enablement doesn't become a single giant commit.

**Recommended breakdown:**

- **Drop 8a — Director engine data-fication.** Moves faction model to YAML. Ships with GCW config that produces byte-identical behavior to current hardcoded constants (via regression test). Safe to ship ahead of the full pivot — it's a pure refactor.
- **Drop 8b — Policy enforcement + Village scaffold.** Items 1-6 above. Needs the world-extraction refactor in place.

Note: Drop 8a is **valuable independent of the pivot**. It's the same "content as data" principle that motivates world-extraction. Even if the Clone Wars pivot were canceled tomorrow, 8a would still be worth doing on its own merits.

### 11.4 The handoff to the other session

- **They don't need to pause.** All content design work is parallel-safe.
- **They do need to ship the world-extraction refactor** before Clone Wars can boot.
- **Drop 8a (Director data-fication)** is a good early-win target for either session — low risk, no Clone Wars dependency, enables the pivot cleanly when content is ready.
- **Drop 8b (policy + Village)** is the dedicated pivot enablement drop. Best scheduled together.
- **GCW retirement:** clean-slate DB wipe per user direction. Preserve test_jedi. Old `build_mos_eisley.py` goes to `build_mos_eisley_legacy.py`, lives one release cycle, then deletes.

---

## 12. Drop Plan (updated)

### Drop 0 — Prerequisite: world-extraction refactor

Per `world_data_extraction_design_v1.md`. Prerequisite for everything else.

### Drop 1 — Clone Wars YAML foundation

- `data/worlds/clone_wars/era.yaml`
- `data/worlds/clone_wars/zones.yaml` (new zone set for 6 planets)
- `data/worlds/clone_wars/planets/tatooine.yaml` (reskin)
- `data/worlds/clone_wars/planets/nar_shaddaa.yaml` (reskin)
- Faction YAML for new faction set
- Exit discipline validation script

### Drop 2 — Coruscant

- `data/worlds/clone_wars/planets/coruscant.yaml` — all 7 zones, ~65 rooms
- Coruscant-specific NPCs
- Jedi Temple interior including Archives, Council Chamber lobby

### Drop 3 — Kuat + Kamino

- `data/worlds/clone_wars/planets/kuat.yaml` — ~30 rooms
- `data/worlds/clone_wars/planets/kamino.yaml` — ~25 rooms
- Related NPCs

### Drop 4 — Geonosis

- `data/worlds/clone_wars/planets/geonosis.yaml` — ~35 rooms
- Geonosian NPCs, CIS recruitment content

### Drop 5 — Housing + test characters + wilderness

- `housing_lots.yaml` (era-appropriate housing tiers)
- `test_character.yaml` + `test_jedi.yaml`
- `wilderness/coruscant_underworld.yaml` — 3-level coordinate region

### Drop 6 — Director AI & World Lore Pivot (§8)

This is the drop that makes the galaxy *feel* like the Clone Wars. Packaged as one cohesive drop because the content and engine changes interdepend.

**Engine (sub-drop 6a — can ship ahead of full pivot):**
- `engine/director.py` refactored to read faction model from YAML
- New `data/director_config.yaml` with GCW baseline (byte-identical behavior to current hardcoded constants, validated by regression test)

**Content (sub-drop 6b — ships with pivot):**
- 15 GCW lore entries deleted from `engine/world_lore.py` SEED_ENTRIES
- 10 era-neutral-ish entries reframed (Mos Eisley, Nar Shaddaa, Black Market, etc.)
- 30+ new Clone Wars lore entries added (Republic, CIS, Jedi Council, Master/Padawan, Grand Army, Clone Troopers, Kuat Drive Yards, Coruscant Senate, etc.)
- `data/zones.yaml` rewritten: 14 tone rewrites + 17 new Clone Wars zone tones + space-zone updates
- `engine/director.py` system prompt rewritten for Clone Wars era
- Clone Wars `director_config.yaml` shipped (Republic/CIS/Jedi baselines, new milestone events)
- `data/ambient_events.yaml` extended with ~170 new ambient lines for new zones

### Drop 7 — Chargen templates

- All 15 templates (§3.4)
- Jedi Padawan with Village-gated flag
- New Shipwright template

### Drop 8 — Tutorial rework

- 8 profession chains
- Intro + concierge + faction preview
- Jedi sign seed event
- All YAML, references resolve to rooms in prior drops

### Drop 9 — Pivot enablement (remaining engine)

- §11.3 items 1-6: policy enforcement, Village state machine scaffold
- GCW retirement operational changes
- (Director data-fication already shipped via Drop 6a)

### Drop 10 — Jedi Village quest chain

- Dune Sea wilderness region (`wilderness/tatooine_dune_sea.yaml`)
- The Village itself (hand-authored rooms within Dune Sea coordinates)
- Village quest chain YAML (Act 1 signs, Act 2 arrival, Act 3 choice)
- Jedi Path tutorial unlock

### Drop 11 — Live pivot

- DB wipe
- Flip `active_era` to `clone_wars`
- Architecture doc update to v31
- Release notes

**Total scope:** ~4x the Space Overhaul v3 effort — noticeably larger than v2 estimated after the Director/lore audit. Drops 1-5, 7-8, 10 are content-only and parallelizable across sessions. Drop 6 is hybrid (6a engine, 6b content). Drop 9 is the remaining pivot enablement engine work. Drop 11 is operations.

---

## 13. Open Questions — All Resolved for v3

All v2 and v3 surface-level open questions are now answered. Summary below; detailed notes follow.

### Resolved in v2
- ~~Jedi unlock mechanism~~ → Village (§4)
- ~~Kuat yes or no~~ → Yes (§2.3.2)
- ~~GCW retirement~~ → Clean-slate wipe, preserve Test Jedi (§5, §11.4)
- ~~Tutorial rework~~ → Full rework, expanded to 8 chains (§10)
- ~~Clone Wars wilderness choice~~ → Coruscant Underworld at launch, Dune Sea at Village drop (§7, §4.4)

### Resolved in v3 (design-authorial)
- ~~Director AI / world lore pivot scope~~ → Full audit complete (§8), Drop 6a/6b plan in place

### Resolved in v3 (user decisions this session)

1. **Coruscant zone count — 7 is ambitious.** → **Keep all 7.** Large Coruscant is part of the "worlds should be larger" directive. Target stands at ~65 rooms.

2. **Clone Trooper template — Republic-exclusive or allow defection?** → **Allow deserters.** And this potentially feeds bounty hunter mechanics: deserter clones become high-value targets on BHG boards. Interesting content loop — deserter PCs live under the shadow of a standing bounty, other PCs can hunt them. Cross-reference with Jedi Village Act 1 design (deserters may also be candidates for Force-sign awakening given the narrative of personal crisis/questioning of orders).

3. **Shipwright template — too niche?** → **Build it.** Brian loves Kuat getting built out. Keep Shipwright as a first-class template.

4. **Gilded Cage — Human PC access?** → **Soft friction.** Humans can enter but face NPC reactions — wary looks, elevated vendor prices, occasional refusal of service. No hard blocks; establishes the district's defensive posture without being punitive.

5. **Force signs for non-sensitives — fairness?** → **No one gated completely.** The ~50% who don't receive a tutorial seed can still pursue the Village but on a longer/harder path — sign accumulation rate is halved or requires specific activities (meditation roleplay in specific zones, proximity to Force-sign events triggered by other players, etc.). Every character has a road to the Village; some just have a steeper one.

6. **Jedi Padawan starting rep with BHG — 0 or negative?** → **Keep negative per canon.** Canonically confirmed: during the Clone Wars, bounty hunters were regularly hired against the Jedi, with Cad Bane as the era's archetype Jedi-hunter. Starting at -10 is thematically accurate and creates narrative texture (a Padawan knows the guild looks at them as potential contracts).

7. **Kamino access for Separatist players — infiltration path?** → **Yes.** Infiltration missions let CIS-aligned players get temporary access to Tipoca City. Designed into faction-quest content in a post-launch drop; engine support (temporary zone permits) is a small add.

8. **Director engine data-fication — Drop 6a or fold into 6?** → **Drop 6a.** Ship the refactor ahead of the full pivot with a GCW-faction `director_config.yaml` that produces byte-identical behavior. Then 6b swaps in the Clone Wars config. Safe, good refactor on its own merits, unblocks the pivot.

9. **Sith milestone events — launch or defer?** → **Launch.** A rare `dark_side_stirring` milestone event fires when dark-side kills cross a threshold in a zone. Atmospheric only — no player-facing Sith faction, just an environmental tell that adds texture to the Clone Wars' secret war. Designed into `director_config.yaml` milestone_events from day one.

10. **Holonet News flavor — Drop 6b or post-launch?** → **Drop 6b.** War-front reports, Senate gossip, Jedi deployments, industrial espionage headlines at Kuat — the Holonet News voice is core to the Clone Wars atmosphere. Not polish; ships with the pivot.

11. **Proceed to YAML authoring now, or revise once more?** → **One more pass.** Review v3 end-to-end, pay particular attention to §8 Director/lore scope, then commit to authoring. Two additional sourcebooks (Galaxy Guide 11: Criminal Organizations and Jedi Academy Sourcebook) exist and will be integrated into v4 when they can be uploaded.

---

## 14. Status & Handoff Signal

This design is **ready for review but not yet ready for YAML authoring.** The design space is locked; the review pass is for catching anything still off before we commit to ~240 rooms of new content and a ~200-line Director engine refactor.

**Next session work**, in order:

1. (Optional) Upload GG11 and Jedi Academy Sourcebook if possible; v4 integration pass
2. User review of v3 end-to-end with focus on §8 Director/lore scope
3. Brian's verdict: proceed to authoring, or revise to v4 first
4. If proceeding: begin Drop 1 content authoring (era.yaml, zones.yaml, tatooine.yaml reskin, nar_shaddaa.yaml reskin)

A separate handoff doc (`HANDOFF_CLONE_WARS_ERA_PIVOT.md`) accompanies this design; see it for session-bootstrap context.

---

*End of Clone Wars Era Design v3.0 — April 18, 2026*
*Parallel session, separate from main development track.*
*Incorporates WotC Coruscant and the Core Worlds source material.*
*Ready for review, revision, and phased implementation.*
