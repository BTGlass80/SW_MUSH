# SW_MUSH — Wretched Hives of Scum and Villainy Extraction
## Version 1.0 — May 31, 2026 · Opus session
### Source: WEG40153 — *Wretched Hives of Scum and Villainy* (Paul Danner, West End Games, 1997, 121 pages, scanned JPEG, OCR'd)
### Purpose: Distill the build-relevant content so the 22 MB scan (`WEG40153_compressed.pdf`) can be pruned from the project. This is the Tier-1 "venues + patrons + seeds" book (roadmap §1) — it feeds Player Shops (G17), Sabacc/Entertainer (G23), Encounters/Hazards (G24), Scenes/Plots/Places (G20), with secondary feeds into Security Zones (G04), Space (G05), Espionage (G22), and the deterministic Director library (G26).

---

## 0. What this is, and the two mandates that govern it

This is a **design reference**, not a transcription. Everything below is paraphrased and reorganized for the SW_MUSH build. The book details **eight watering holes** plus a venue-design appendix and a starship deckplan. Two project rules apply throughout:

- **Era translation (Clone Wars, ~20 BBY).** The source is firmly **Galactic Civil War era**. The Empire and the Rebel Alliance are stripped or recast everywhere they appear as *setting*: Imperial garrisons/liaisons/stormtroopers, ISB, the Emperor, "the Rebellion," Imperial-class starports, Imperial censorship, and "TIE-series" framing are all off-era. At ~20 BBY the relevant powers are the **Republic** (thin Outer Rim footprint), the **Separatist/corporate** bloc, the **Hutt cartels**, and local crime families. The war reaches these venues as distant news — war profiteering, refugees, disrupted lanes, and a brisk black market.
- **Q1 canon-character policy.** **Key finding: this book is almost entirely original.** Unlike GG7 (Jabba/Chalmun/Evazan/etc.), the eight venues are WEG inventions and the named cast — Cohden K'Reye, Sibarra the Hutt, Dunan Par'Ell, Luskin Exovar, Gorge & Greel, Odanni, Yin Vocta, Blizz Pinnix, the A'Daasha twins, Talandro Starlyte — are **not canonical figures**. There is therefore very little to anonymize; the era work is stripping the **Imperial/Rebellion framing**, not renaming people. The only canon-name brush is the joke band "Dengar and the Destroyers" (drop/rename) and a stray "Mon Cal/Calamari is the Rebel shipyard" arc (recast — see §3.4).

**Stat policy.** WEG = our ruleset (D6 R&E), so NPC and creature stats are kept. Where a stat line names an off-era skill specialization (e.g. *bureaucracy: Imperial*, *bureaucracy: Alliance*, *law enforcement: Imperial*), re-label it to a CW analogue (*bureaucracy: Republic / CIS / kajidic*, *law enforcement: Judicial / planetary*). The dice stay; only the label changes.

---

## 1. Book identity & mining assessment

| Element | Verdict | Where it lands |
|---|---|---|
| **"Cohden's Condensed Critique" venue card** | **Extract — schema** | Venue/shop profile schema (G17, G20) |
| **10-Step Cantina Creation guide** | **Extract — schema** | Procedural venue/player-shop generator (G17) |
| **d66 Cantina Encounter Table** | **Extract — content (era-translate 4 entries)** | Director scene library (G26), Scenes (G20) |
| **8 fully-detailed venues** | **Extract — templates** | Venue/POI gazetteer; map & room design |
| **Price/service tables (per venue)** | **Extract — economy** | Economy sinks (G06), docking/lodging/cover |
| **NPC roster (~25, statted)** | **Extract — archetypes** | NPC templates (G10 staffing, dialogue) |
| **Creatures (jexxel, crynoid, ice modrol, Derriphan)** | **Extract — turnkey** | Encounters/Wilderness (G24) |
| **Environmental hazards (acid rain, lethal atmosphere, frozen waste)** | **Extract — turnkey** | Hazards (G24), world data |
| **Adventure hooks ("Loose Threads")** | **Extract — seeds (era-translate)** | Director quest-template library (G26) |
| **Starship deckplan (*Starbound Misfit*, tramp freighter)** | **Optional** | Ship-as-location asset (G05; pairs w/ GG6) |
| **GCW/Imperial setting framing** | **Strip/recast** | — |

---

## 2. The reusable schemas (highest ROI)

These three artifacts are the most valuable thing in the book: they generalize all eight chapters into systems.

### 2A. The Venue Profile card ("Cohden's Condensed Critique")
Every venue is summarized by the same seven-field card. This is a ready **venue/player-shop profile schema**:

```yaml
# Venue profile card (from Wretched Hives "Condensed Critique")
venue_profile:
  establishment: ""          # display name
  owner: ""                  # owner / front-owner (may differ from the real power — see Ace)
  amenities: []              # {food, drink, lodging, gambling, dancing, supplies, vehicle_repair, vehicle_parts, entertainment, ...}
  cover: 0                   # entry fee in credits (0 = none; may be conditional)
  vip_room: ""               # optional inner sanctum (Sabre Club, Sandstorm, etc.)
  security: ""               # named chief + force (NPC archetype ref)
  illegal_activities: []     # {fencing, slavery, espionage, info_brokering, smuggling, counterfeiting, loan_sharking, slicing, data_fixing, prohibited_holos, ...}
  rating: 0                  # 1–5 ("supernovas") — a quick desirability/danger dial
```

The **owner ≠ real power** pattern (the Ace's public owner is a shell corporation; the true owner is a hidden Hutt) is worth a flag field on venues: `front_owner` vs `true_owner`, with the true owner often running the illicit activities from a concealed control room. Great for investigation plots and territory ownership.

### 2B. The 10-Step Venue Creation framework
The appendix codifies the design process behind every chapter. Use it as the **field set for a procedural venue/shop generator** (and the authoring checklist for hand-built POIs):

1. **Locale** — world / city / neighborhood; the venue should reflect its locale.
2. **Structure** — category (raucous spaceport cantina / exclusive club / niche nightclub / two-bit dive), floors, underground vs. tower, high-tech vs. throwback. *"Anything more elaborate than a square room with a bar improves the scene."*
3. **Owner** — criminal / investor / honest proprietor; how they acquired it; absentee vs. hands-on.
4. **Theme** — the gimmick that draws and retains a crowd (sport/blood-sport, gambling, high-society mingling, a culture, an era). Drives decor, atmosphere, clientele.
5. **Amenities** — food/drink quality, lodging, docking/parking, supplies.
6. **Prices** — high-class markup vs. discount-to-attract; cover fee; drink minimum; docking fees.
7. **Security** — bouncers / hired muscle / droids / none; trustworthy or thieving or spying.
8. **Crowd** — class, age/temperament, droid policy, fight frequency.
9. **Famous Faces** — resident celebrities, regulars, the bounty hunter at "his" table.
10. **Illegal Activities** — the shady backbone (spice, fencing, slavery, slicing, data-fixing, loan-sharking, laundering for a Hutt). Who knows; who's watching.

This maps 1:1 onto the player-shops/venue config and is the natural backbone for a "generate a CW cantina" admin tool.

### 2C. The d66 Cantina Encounter Table (era-translated)
A 36-entry random table: roll 2d6, read one as tens and one as ones (no addition). Turnkey **deterministic scene content** for the Director library (G26) and ambient venue life (G20). Reproduced below in our own words, with the four Imperial/Rebellion entries recast (marked ⟳):

| Roll | Encounter (era-translated) |
|---|---|
| 11 | A furtive figure peddles a datacard of stolen secrets. |
| 12 | A barroom brawl erupts out of nowhere. |
| 13 | ⟳ Local enforcers (cartel toughs / planetary security / clone patrol) burst in chasing a fugitive. |
| 14 | Drunken starfighter pilots loudly embellish their exploits. |
| 15 | Two old rivals lock eyes and clear leather. |
| 16 | An attractive stranger buys a PC a drink. |
| 21 | ⟳ Off-duty soldiers (mercenaries / clones) antagonize the patrons. |
| 22 | A badly wounded being staggers through the door. |
| 23 | A vendor hawks exotic (and illegal) goods. |
| 24 | A nervous stranger keeps one eye on the entrance. |
| 25 | Someone is shopping for passage offworld. |
| 26 | Gamblers are deep in a high-stakes sabacc hand. |
| 31 | A bounty hunter quizzes the bartender about a PC. |
| 32 | Two beings argue furiously at the next table. |
| 33 | Security sweeps the room with a visual search. |
| 34 | A lost child wanders in looking for its parents. |
| 35 | A pickpocket tries to lift from a PC. |
| 36 | A famous individual is present. |
| 41 | A sudden explosion rocks the bar. |
| 42 | A nasty-looking alien will not stop staring at a PC. |
| 43 | Someone drops a loaded cred-stick on the way out. |
| 44 | A PC spots a man slipping something into a drink. |
| 45 | Blaster fire breaks out between two rival swoop gangs. |
| 46 | A passing alien points a blaster at a PC — and laughs. |
| 51 | Heavily-armed gunmen take hostages. |
| 52 | A patron keels over dead; authorities start questioning the crowd. |
| 53 | A man stands and arms two thermal detonators. |
| 54 | A private investigator tails the PCs out the door. |
| 55 | Two mercs are looking for bodyguard work. |
| 56 | A serving droid malfunctions and starts attacking patrons. |
| 61 | Staff walk out on strike; the bar is forced to close. |
| 62 | A disgruntled owner shoves the deed at a PC and leaves. |
| 63 | An out-of-control airspeeder crashes into the cantina. |
| 64 | A stranger begs the PCs for help getting offworld. |
| 65 | A police tactical team storms in to arrest the PCs. |
| 66 | ⟳ A contact the PCs came to meet turns out to be a double agent (working for a rival faction / the Hutts / enemy intelligence). |

(Entry 62 — "the owner hands you the deed and walks out" — is a tidy, era-safe way to put a player into ownership of a venue: a natural Player-Shops onboarding hook.)

---

## 3. The eight venue templates (gazetteer)

Each is a drop-in POI/scene. For each: the concept, the world stat line (era-translated), layout highlights worth modeling as rooms, the price/service model, security, illegal backbone, key NPCs, and era notes. Use the §2A card to register each.

### 3.1 The Ace of Sabres — *luxury gambling resort* (★★★)
**Concept.** A colossal 99-level entertainment resort on its own continent: seven themed restaurants, three nightclubs, two dancehalls, a dozen casinos with 1,000+ games of chance, and an invitation-only thirteenth casino, **the Sabre Club**, for the ultra-rich. "You can't lose at the Ace" — which is exactly the lie.
**World — Kluistar:** comfortable Colonies-border world; small cities + a few starports amid vast unspoiled wilderness. The resort owns and maintains an entire continent. (Era-safe as written.)
**Layout to model.** Casino floor (dampener-field tables for privacy; voice-dimmed lighting; air scrubbers) → rowdier "ambiance" casinos (smoke, hard drinks, swindlers) → **Sabre Club** VIP wing (triple-shielded blast doors; Kubaz chefs; 500-seat banquet hall; data library + study; a dozen programmable holo-imaging rooms; a game room that supplies opponents on request) → **hidden underground control room** (the true owner's surveillance bunker). Outer wilderness = camping/hunting/fishing with rental gear (and the place where people "get lost permanently").
**Prices (drop into the economy).**

| Service | Rate |
|---|---|
| Hotel: economy / mid / view / penthouse | 20 / 40 / 75 / 100 cr/night |
| Meals: special / multi-course / four-star | 7 / 15 / 30 cr/meal |
| Drinks: on tap / mixed / vintage | 2 / 5 / 20+ cr/glass |
| Personal transport | 10 cr/person |
| Recreational kit (full backpack + map) | 20 cr/day |
| **Sabre Club membership** | **25,000 cr / 2 years** (999 members; cancelable, no refund) |

**House rules (a strict-venue model).** No droids, datapads, or weapons; no personal cards/dice. Door scanners run *search 10D*; smuggled contraband = immediate ejection, no refund. Sabre Club issues a holocard keyed to genetic sample + voiceprint + retinal scan (lost card replaced at great expense).
**House edge / "Know When to Fold."** Casino dealers gamble at **4D–7D**; Sabre Club dealers at **8D+** and can quietly fix outcomes (i.e., they cheat). A clean dial for "the house always wins" — and a cheating-detection investigation hook.
**Security.** Chief **Dunan Par'Ell** (see §4) + his firm **UniGuard** (Universal Guardians, Inc.) — a reusable elite private-security contractor brand. Sabre guards: standard 2D except *Dexterity 3D, blaster 5D+1, dodge 4D, melee 5D, Strength 3D, brawling 5D*; customized body armor (+1D phys/energy), blast helmet (+2 phys/energy), heavy blaster pistol (5D), stun baton (STR+1D). Move 10.
**Illegal backbone.** The visible owner is a shell ("Ace Entertainment Corporation"); the **true owner is a hidden cybernetic Hutt crime lord, Sibarra** (see §4), who has bugged the entire resort with holocams + audio pickups and runs black-market ops, fencing, slavery, counterfeiting, bribery, stolen-information trafficking, loan-sharking, slicing, and data-fixing from his concealed bunker. He supplies a slaver ring (Ahntanda, §4) — attractive guests "win" wilderness getaways and vanish.
**Notable regulars.** A brash smuggler (YT-2000, ship *Distant Sunrise*); a half-trained Force-sensitive ex-cop carrying a self-built lightsaber and a Jedi lorebook, *seeking training* (a clean Force-recruitment hook for G08/G14/G18 — original NPC, Q1-safe); an arrogant noble gambler; a popular dancer/entertainer.
**Era notes.** Recast "royalty / Imperial nobility / corporate elite" as sector grandees, war profiteers, Separatist & Republic notables, and kajidic elite. Rename the game "Death Star Bluff." Par'Ell's backstory ("ex-Imperial, maybe a Royal Guard, protégé of Vader") → ex-military of some shadowy security apparatus (see §4). Drop the Boba-Fett comparison.

### 3.2 Exovar's Emporium — *remote hidden curio-cantina / safe haven* (★★★★)
**Concept.** A cavernous cantina-museum buried in a frozen valley on the far side of an ice world, run by an eccentric retired scout who has filled it with artifacts from a legendary career. Neutral ground for the fringe; a thieves'-guild-style truce holds because the owner's assassin-droid guards enforce it.
**World — Neftali (Socorro system):** ice world, frigid, Type I atm, light gravity; glaciers, fjords, ice canyons; pop ~15,000; **government: organized crime family**; exports include contraband and "nether ice." Main town **Cordel Cove** is neutral ground for smugglers/hunters, run by gangster Memcha-Badawzi. *(Direct tie-in to the Tier-2 book Black Sands of Socorro — and to our smuggling/space content.)* The Emporium itself is thousands of km away, hidden in a wind-scoured valley.
**Layout to model (excellent room-design source).**
- **Ion Alley** — an armored entry tunnel (~90 m diameter) lined with sensor arrays, defended by the **Ion Defense Grid** (a capital-scale ion field that shuts down intruding ships; *Fire Control 6D, Range 0–50, ionization Damage 2D–16D, adjustable*).
- **Luskin's Landing** — underground hangar, 50+ docking stalls, droid-staffed; restock/refuel at nominal fee, minor repairs at discount; manifests not required (but a first-visit hazmat scan); K4 security droids.
- **Main hall** — seats ~1,000; sunken central bar (~2 m down); waiter/bartender droids that dispense drinks *and* advice; a shielded **Trophy Wall** (display cases under 8D character-scale shields + hypersonic alarms); full-size craft hung from the ceiling on transparent duracables.
- **Rendezvous Rooms** — 24+ private themed sitting rooms with sound screens, bookable; several are claimed by regular cliques: **Chasers** (bounty hunters; bounty postings on the walls), **The Trap** (big-game hunters; staffed by resident beast-hunter Kaori Batta), **The Explorer's Guild** (scouts; AV records of legendary expeditions), **The Library** (quiet reading room stocked with banned/contraband texts). *These themed-room archetypes are turnkey for player-shop back rooms and faction hangouts.*
**Security model (remote-venue flavor).** Twin **assassin droids** (Entax & Botax) + the owner's alien sidekick. Discipline: troublemakers are stripped of gear, bound, and dumped in the wastelands at night ("round 'em up and let the modrols sort 'em out"). Cheap, memorable deterrence for an isolated venue.
**Illegal backbone.** "Various" — info/goods/services traded in near-perfect secrecy in the private rooms; the owner himself stays clean ("his boots remain clean") while the fringe deals around him.
**Era notes.** The owner is canonically of the *Old Republic Scout Service* — **era-friendly** (CW is the late Old Republic). His retirement framed as "fleeing a dark storm on the horizon" recasts neatly as fleeing the Clone Wars. Strip the Imperial/Rebel set dressing (the "Imperial Royal Guard uniform" trophy, "Emperor's censors," "a room used by Rebels"); the Jedi-lightsaber trophies, Sun Guard helmets, and rumored Mandalorian armor are era-safe (and more interesting in CW). **Era-translate the AT-AT-head trophy/turret** (an Imperial walker) → a battered old battle-droid head or a salvaged planetary-defense turret, keeping the "functional trophy doubling as a fixed gun emplacement" gag (Walker-scale, Body 6D, fire-linked heavy cannons; enter via a hidden basement ladder + prefix code).

### 3.3 The Broken Tusk — *crashed-ship dive + blood-sport arena* (★★)
**Concept.** A grimy after-dark dive built inside the **wreck of a crashed bounty-hunter's starship** that impaled an abandoned factory; the rear hull is the bar, stern aimed at the sky. Run by two Gamorrean brothers — a huge bouncer and his undersized, sharp-dressed, fast-talking sibling (who speaks via a voice synthesizer). Its main draw is a built-in combat pit.
**World — Reuss VIII:** once-lush world strip-mined into an industrial nightmare; hot, **Type III atmosphere (breath mask required)**, urban, pop 25 billion; government: organized crime (crime lord *Torel Vorne* — ties to **GG9: Fragments from the Rim**, a Tier-2 book). **Acid-rain hazard** (see §5).
**Layout to model.** Blast-shielded double doors, magnalocked by day, open at dusk to a waiting crowd; the Tusk's atmosphere processors make breath masks unnecessary inside. Multi-tier seating descends to the sunken **Dool Arena** (5 m plasteel walls) so every seat has a view.
**The Dool Arena (turnkey blood-sport + wagering sink).** One rule: **no ranged weapons** — everything else is legal. Single-elimination bouts; the winner faces the **reigning champion** (crowd favorite "Tull," with powered shockboxing gloves; another contender, Zomil). **Wagering on matches is the Tusk's single largest revenue source.** Management *claims* it never rigs a fight. → Wire this to G23 (gambling/wagering), combat, and the economy (a pit-fight sink + a payout pool); a clean spot for a "fix the fight" or "fight your way out" plot.
**Prices.** Cover depends on the night's entertainment (i.e., on the card); food/drink standard dive fare (e.g. fried seasquid, boiled babasta as specials).
**Security.** The bouncer brother (vibromallet STR+3D+2; two heavy blaster pistols; picks his fights, prefers a growl to a brawl). Voicebox note: Gamorreans can't speak Basic; the entrepreneur brother uses a SoroSuub Synthax-7 voice-synth implant.
**Era notes.** Origin is **era-safe** (two ex-slave Gamorreans; the dropped-off bounty was at Coruscant — fine). Only the *hooks* are Imperial-framed — recast the captor running the death-games as a Hutt/slaver/crime-lord (see §8).

### 3.4 Fathoms — *submerged four-in-one entertainment complex* (★★★)
**Concept.** A self-contained underwater complex occupying eight levels of a tower in a floating ocean city, with transparisteel viewports onto the sea. It is **four venues in one stack**: *Fathoms* (fine-dining restaurant), *The HyperDive Cantina* (rowdy bar), *Wave Works* (gift shop), and *The Seabed Lodge* (hotel + leisure). Built up from a tiny eatery by a Mon Calamari businesswoman.
**World — Mon Calamari:** ocean world, temperate, Type I atm, saturated hydrosphere; floating + underwater cities; Mon Calamari (open, accepting) and Quarren (pragmatic, conservative) share the homeworld uneasily. The venue sits in **Wildwater City**, a young, bohemian floating metropolis that welcomes eccentrics — a natural artists'/outsiders' quarter.
**Layout to model.** A **vertical multi-venue complex** in one tower is a great composite-POI template (restaurant + cantina + retail + lodging on stacked levels, shared docking/lift core). Underwater levels = stunning, slightly disorienting views (mooring lines, transport tubes, submersibles); deepest levels glimpse Quarren deep-sea mining.
**Era notes — heaviest in the book.** The source leans hard on the OT arc: "before the Empire / enslavement / freed and joined the Rebellion / Mon Cal shipyards building the Rebel fleet." **Recast wholesale for ~20 BBY:** Mon Calamari is a *peaceful Old Republic ocean world*, not yet conquered, with its famous shipyards building *civilian and Republic* vessels. Drop the Empire/Rebellion arc entirely. **Keep** the underwater-city setting, the four-in-one venue, the Wildwater "bohemian quarter" tone, and the **Mon Cal ⇆ Quarren cultural tension** (era-agnostic and canonically live in the prequel era). The "fugitive safehouse" hook recasts cleanly (see §8).

### 3.5 Bantha Traxx — *desert-motif dance club / espionage front* (★★★★)
**Concept.** The trendiest dance club on its world — a desert/cantina motif (ironically, on an industrial planet), a neon dancing-bantha holo-sign, a signature drink ("Tatooine Sunburn"), live bands, three floors. The top floor, **The Sandstorm**, is a VIP club-within-a-club. Beneath the glamour it is an **information-brokering / espionage / assassination front**.
**World — Lianna:** urban industrial world, Allied Tion sector; HQ of a major starship manufacturer (Santhe/Sienar). **A strict weapons-illegal world** — a useful contrast to Mos Eisley's open carry:

| Offense (Lianna) | Penalty |
|---|---|
| Possess an energy weapon | 200,000 cr fine + 2 years hard labor |
| Possess a non-energy weapon | 50,000 cr fine + 6 months hard labor |
| *Use* a weapon | Substantially harsher |

→ A turnkey **high-security / no-weapons legal model** for Security Zones (G04): scanned entry, severe possession penalties, concealed-carry as the norm anyway.
**Layout to model.** Three-story club: two lower floors (standing-room, all classes mingling) + the VIP **Sandstorm** on the third. Liann architecture favors bright color, gardens/atriums, and a central **floorpit** (sunken focal area) — a nice decor template.
**Prices.** Cover 10 cr.
**Security.** Chief "Jik'Tal and the Enforcers."
**Illegal backbone.** Information brokering, espionage, assassinations — the owner (an Anomid dealmaker, see §4) is implicated in a shadowy corporate-espionage arrangement with the planet's dominant tech firm. → Wire to Espionage (G22): the club as a neutral dead-drop / fixer hub where secrets are bought and contracts let.
**Era notes.** Drop "TIE-series" and "Imperial-class starport"; the corporate-espionage frame and the no-weapons law are era-safe. Re-label the owner's *bureaucracy: Imperial/Alliance* skills to Republic/CIS.

### 3.6 The Pits — *swoop-racer bar + rooftop sky-dock* (normals ★★ / racers ★★★★)
**Concept.** A dirty, sunken swoop-racer bar where most disputes are settled on the racecourse and the rest in brawls; home turf for vicious swoop gangs. Sells the whole vehicle stack: repair, parts, new & used rides.
**World — Stend VI:** dull terrestrial manufacturing world plagued by swoop gangs that out-fly local law enforcement. (Recast "another cog in the Galactic Empire / thorn in the side of the Empire" → a sleepy Republic/Outer Rim world whose **planetary** authorities can't catch the gangs.)
**Layout to model (unique vertical concept).** Two entrances with a built-in **status hierarchy**: *fly in via "The Hive"* (respect) vs. *walk in via the ground door* ("bantha droppings"). **The Hive** is a rooftop honeycomb tower of hundreds of particle/ray-shielded docking **stalls** (cubicles), each with a refuel unit (extra cost), cleaning supplies, and a holoboard of notices + vehicles for sale; blast-proof doors (8D) with auto-erasing private codes (one master code, owner-only); a three-turbolift core (one always broken). → A turnkey **swoop/speeder docking + vehicle-market node**.
**Amenities.** Food, drink, lodging, vehicle repair, vehicle parts, new & used vehicles.
**Security.** A bouncer named Chugg.
**Illegal backbone.** Stolen vehicles & parts; slavery.
**Build value.** Swoop gangs + racing → a racing minigame/encounter and a **vehicle crafting/mod economy** (G07): gang swoops standardly carry heavy weapons, acceleration boosters, and black-market engine "juicers"; a stock "factory" swoop is mocked. Gang turf + rivalry feeds Territory (G11).

### 3.7 Glow Dome — *holographic light/dance nightclub* (★★★★★)
**Concept.** "The Bright Center to the Galaxy" — a photovoltaic dome lit so brightly it's visible 5 km away (polarized lenses/glowshades mandatory), with 10,000+ robotic spot-luma projectors, glowing drinks, illuminated dancers, and mood-altering **SenseLights**. Almost everything inside *could be a hologram* (and often is). Co-owned by twin sisters.
**World — Adarlon (Minos Cluster):** an entertainment world obsessed with pleasure; home to a huge **holo-production industry** and dozens of immersive **theme parks** (live-action roleplay: a mystery park, a space-dogfight-sim park, a "raid the crime lord's citadel" park). *(Ties to GG6: Tramp Freighters, already extracted.)*
**Layout to model.** Glowing photovoltaic dome roof (stores sunlight by day, blazes by night); a swirling sky of ~100 spot-lumas synced to the music; holographic decor everywhere (built-in "is it real?" deception flavor).
**Prices.** Cover 25 cr; amenities: drinks.
**Security.** A chief named Lux.
**Illegal backbone.** "Prohibited holos." (Recast: in CW, illicit/underground holos might be anti-war, pro-Separatist, anti-Hutt, or simply censored entertainment — drop the "celebrate the Jedi / Rebellion / pro-Empire" framing.)
**Build value.** A pure entertainment/nightclub node (G23) plus a holo-production industry hook; the theme-park concept is a nice optional immersive-scene generator. **Hidden danger (optional boss):** a rare Force-parasite (Derriphan, see §5) lurks here, quietly killing patrons — a high-end Force-mystery seed.

### 3.8 The Falling Star Saloon — *free-port cantina aboard a derelict station* (rating n/a)
**Concept.** An interstellar cantina at the heart of a decaying former transfer station that a slick businessman rents and runs as a free-trading post; a haven for smugglers, privateers, pirates, and castoffs.
**Setting — Starlyte Station, orbiting Tshindral III:** a spherical-framed station whose **equatorial docking ring has 250+ berths**; decades of neglect mean broken systems stay broken and repairs are jury-rigged; replacement parts are scarce. Quietly defended by **five fire-linked turreted turbolaser batteries** wired to the command center (operable individually if separately crewed). Below: **Tshindral III**, a lifeless planetoid with a **lethal atmosphere** (instant death; corrodes a YT-1300 hull in <24h) — a planet whose true fate is an in-bar tall-tale game.
**Layout to model.** A **derelict orbital free-port** is a turnkey space-station venue (G05): docking ring (250+ berths, docking fees), a central command center with hidden capital-scale guns, a station shop ("Talandro's Trading Post"), maintenance crawlways, sublight drive, cargo bay/freezer, and a ship "graveyard" of derelicts nearby (salvage hook). Pairs with the space guide and GG6's ship-as-location.
**Owner / NPCs.** A black-marketeer proprietor (Talandro Starlyte); a tramp-freighter captain whose ship (*The Starbound Misfit*, starfighter scale, w/ deckplans at the back of the book) can serve as a player-relevant vessel.
**Era notes — second-heaviest strip.** Origin is built on the Empire (Imperial Transfer Post, rented from the Empire, an **Imperial Liaison Officer** + a stormtrooper detachment, "the Emperor's Irregulars"). **Recast the whole frame:** an *abandoned Republic/Trade-Federation/old-corporate* transfer station (or one of murky origin) that the proprietor has claimed; replace the Imperial garrison/liaison with station-security toughs, a Hutt enforcer presence, or a token Republic customs observer. The "rent a derelict station, turn it into a free-port cantina with a hidden gun battery" concept is fully era-safe.

---

## 4. NPC archetype roster (era-translated)

Stats kept (WEG = our ruleset). Off-era skill *labels* re-tagged to CW analogues; dice unchanged. The signature roles get fuller blocks; the rest are role + hook. Per Q1, all are original NPCs (no canon figures) — use as reusable templates for venue staffing and dialogue.

### 4A. Signature templates (fuller blocks)

**The Elite Security Specialist** (Ace's chief — "Dunan Par'Ell"). The model "scary bodyguard who owns the firm." *Era-translate the backstory:* a decade in **some shadowy security/military apparatus** (drop Empire/Vader/Royal Guard), resigned under murky circumstances, now hires out at astronomical fees and owns an elite private-security firm (**UniGuard**), currently head of security at the venue while on retainer to other elites. Calm, soft-spoken, never loses his temper; mirror-surfaced eyes; master of an exotic martial art; signature scarlet cloak over body armor.
```
Type: Security Specialist  ·  Move: 12  ·  FP 3 / DSP 9 / CP 30
DEX 5D: blaster 7D+1, blaster: heavy pistol 9D, blaster artillery 6D, brawling parry 8D,
        dodge 11D, grenade 7D, melee 9D, melee parry 8D+1, thrown 9D
KNO 3D: alien species 5D+2, bureaucracy 5D, bureaucracy: [intelligence svc] 8D,
        cultures: [elite court] 11D, intimidation 10D+1, law enforcement 7D,
        planetary systems 4D, streetwise 8D, survival 9D, tactics: squads 10D, willpower 12D+1
MEC 2D: beast riding 5D, repulsorlift op 4D
PER 3D: command 9D, hide 11D, search 9D, sneak 10D+2
STR 3D: brawling 9D, brawling: [martial art] 12D, climb/jump 7D, stamina 9D+1, swim 5D
TEC 2D: computer prog/repair 7D+1, demolitions 8D+2, first aid 7D, security 13D
Gear: fitted body armor (+2D phys/energy), hold-out blaster (3D+1), stun baton (STR+2D+2),
      heavy blaster pistol (5D+2), 2 smoke grenades, 5 throwing knives (STR+1D+2), comlink
```

**The Cybernetic Hutt Crime Lord** (Ace's true owner — "Sibarra"). An original Hutt villain: a cyborg outcast, hated by every kajidic, who rules through fear from a hidden surveillance bunker and runs the venue's entire illicit economy. *Era-safe as written* (generic Hutt). Great hidden-mastermind / investigation target; ties to Factions (G10) and Territory (G11).
```
Type: Cybernetic Hutt Crime Lord  ·  Move: 2  ·  FP 4 / DSP 14 / CP 23
DEX 2D: blaster 5D, blaster: hold-out 8D, dodge 6D+1
KNO 5D: business 12D, business: [own org] 14D, intimidation 11D, planetary systems 7D,
        streetwise 12D, value 11D, willpower 10D, alien species 5D, cultures 6D
MEC 1D: repulsorlift op: Hutt floater 5D
PER 4D: bargain 12D, command 11D, con 9D, gambling 7D, search 9D
STR 5D: brawling: tail spike 10D+2
TEC 3D: computer prog/repair 9D
Special: Force Resistance (Hutts roll 2× Perception vs Force mind-influence; cannot learn Force skills)
Gear: armored subdermal hide (+3D phys/+2D energy), cyber shock-spike tail (STR+5D),
      cyber-claw hand (STR+3D), enhanced eye (glows red; flashes before a rage), comlink, Hutt floater
```

### 4B. Compact templates (role + signature dice + hook)
- **The Slick Front-Manager / Con-Artist** (Ace's manager): *Businessman.* Strong **business (9D), business: black-market ops (11D+1), business: fencing (10D), streetwise (11D+2), value (10D)**; con 8D+2, bargain 9D. Obsessed with an immaculate appearance ("people trust the well-dressed"). Runs the venue's day-to-day and launders the boss's deals. (Era: "fingered by the Imperials when a deal sours" → fingered by the authorities/enforcers.)
- **The Sullustan Slaver** (kidnapping-ring villain): *Slaver.* business: slaving 8D, intimidation: torture 6D+1, command 8D+1; Sullustan **Enhanced Senses** (+2D search/Perception in low light) and **Location Sense** (+1D astrogation to known systems). Gear: stun pistol (6D stun), magnacuffs/harness. Cold, amoral; the antagonist behind venue "disappearances."
- **The Entertainer / Dancer** (knows-too-much escapee): *Entertainer.* **dance 10D, persuasion 9D, dodge 9D+1, pick pocket 7D+2, con 7D**; gear: lock-pick kit, recording rod, hold-out blaster (4D). A popular performer who's overheard too much and needs extraction.
- **The Gamorrean Bouncer** (over-2m, ~150 kg): *Bouncer.* **brawling 10D+2, melee: vibromallet 10D+2, intimidation 9D, stamina 12D**; 2 heavy pistols, two-handed vibromallet (STR+3D+2), light armor. Stamina special (auto re-roll a failed stamina check). Picks fights carefully; a growl usually suffices.
- **The Gamorrean Entrepreneur** (atypical — svelte, sharp-dressed): *Entrepreneur.* **business 9D, streetwise 9D, dodge 7D, bargain 7D**; SoroSuub Synthax-7 voice-synth implant (Gamorreans can't speak Basic). Slick fast-talker; ruthless when the business needs it.
- **The Eccentric Ex-Scout** (Emporium owner): *Former Scout.* Enormous breadth — **planetary systems 13D, search 13D+2, survival 11D, cultures 12D+2, alien species 11D+2, con 12D+1, droid programming 10D**; rapid-fire rambling personality masking a "hidden clarity." A legendary, era-safe Old-Republic scout; great for the spacer/scout/wilderness systems (G25) and as a quest-giver.
- **The Anomid Info-Broker / Club Owner** (Bantha Traxx): *Businessman.* **command 11D, con 10D+2, persuasion: charm 12D+1, intimidation 11D, streetwise 11D+2**; Anomid sign-language 12D; missile weapons: vac blade 10D. Fronts a chic club; deals in secrets and contracts. (Re-tag *bureaucracy: Imperial/Alliance* → Republic/CIS.)
- **The Tramp-Freighter Smuggler** (multiple venues): *Smuggler/Captain.* space transports ~6D, con/gambling, value; a customized light freighter (YT-2000 / generic tramp) as a player-relevant ride. "Imprisoned three times, escaped each time" (recast captor as authorities/a Hutt). Pairs with GG6.
- **Generic guard block** (any venue's muscle): 2D except *Dex 3D, blaster 5D(+1), dodge 4D–6D, melee 5D, Str 3D, brawling 5D*; body armor (+1D–2 phys/energy), blast helmet, heavy pistol (5D), stun baton. Move 10. Scale up to chief level by adding 2D–4D to combat skills.

---

## 5. Creatures & hazards (turnkey for Encounters / Wilderness — G24)

### 5A. Ice-world predator set (Neftali) — a ready encounter ecology
**Jexxel** — small, vicious pack predator (hunts in packs of 5+; a pack can down an ice modrol; attacks for almost any reason).
```
Type: Predator  ·  Move 18–20  ·  Size 0.5 m tall / 1 m long
DEX 5D: brawling parry 8D, dodge 9D    PER 4D: search 6D, sneak 8D+2    STR 3D: brawling 4D, climb/jump 7D
Special: Claws (STR+1D+1), Fangs (STR+3D), Night Vision (sees in total darkness)
```
**Crynoid ("snow spider")** — tiny poisonous arachnid; not aggressive but bites if pestered.
```
Type: Poisonous arachnid  ·  Move 8  ·  Size 3 cm
DEX 4D    PER 1D: sneak 5D    STR +1: climb/jump 5D
Poisonous Bite: 4D damage, rolled every 5 min for 1 hour. Survivors make a Difficult stamina roll
  vs extreme pain or take -3D to all actions for 6 hours. A Moderate first aid + medpac neutralizes
  the venom (but not the pain).
```
**Ice modrol** — large cold-weather herd-beast/predator-prey anchor (a stuffed one is a trophy centerpiece in the Emporium); the apex grazers the jexxels hunt. Use as the big dangerous fauna of a frozen biome. *(Herbivore filler also named: glessyl beasts, snow q'lk — fauna that scent food-rich geothermal caverns from ~5 km.)*

### 5B. The Derriphan — *rare Force-parasite "boss"* (Glow Dome; optional, high-end)
A powerful, intelligent **body-snatching Force creature** that secretly "Hosts" a victim, using **control mind** + **memory wipe** to hide its presence even from its host; it lives to feed and grow stronger, prefers humanoid prey, and *fears/hates Force-users* (one nearly destroyed it). The book warns it is **extremely powerful** — a single average specimen can wipe an unwary party — and best used as a lurking dread, not a brawl. **Use as a rare, scripted antagonist** for a Force-mystery plot (patrons dying mysteriously at a venue); Q1-safe (original creature); era-agnostic (ancient Sith-bred lore, fine for CW where the Dark Side is live). Flag it strictly as instanced/scripted, never an open-world spawn.

### 5C. Environmental hazards (drop into Hazards — G24)
- **Toxic industrial atmosphere (Reuss VIII).** Acid rain that never fully stops. *Low contamination:* 2D damage per 6 hours of exposure; 2 weeks of exposure → irreversible lung damage. *High contamination:* 2D+2 damage per round (breath masks mandatory to survive). A graded environmental-damage model for polluted/urban-blight zones.
- **Lethal atmosphere (Tshindral III).** Effectively instant death on exposure; corrodes a freighter hull in <24h. A "do not go outside, ever" backdrop hazard for a derelict-station scenario.
- **Frozen wastes (Neftali).** Bone-chilling winds + predator ecology (§5A); the Emporium's discipline model literally weaponizes it ("dumped in the wastes overnight"). Exposure + predation as a combined survival hazard.

---

## 6. How to use this in SW_MUSH (build hooks)

- **Register venues with the §2A card.** Each of the eight becomes a POI with `front_owner`/`true_owner`, amenities, cover, VIP room, security ref, illegal-activities list, and a 1–5 desirability/danger rating. The owner≠true-owner split is a built-in investigation/territory mechanic.
- **Stand up a venue/shop generator from §2B.** The 10 steps are the config field set for player shops (G17) and admin-built cantinas; the chapters are eight worked examples.
- **Feed the Director library from §2C + §8.** The d66 table is ambient scene fuel (G26/G20); the "Loose Threads" are pre-authored, era-translated quest templates (kidnap-ring investigation, forced-arena escape, revenge siege, fugitive safehouse, knows-too-much extraction).
- **Wire the economy (G06).** The Ace price grid (lodging/meals/drinks/transport/recreation/membership) and the per-venue cover/docking/refuel fees are drop-in sinks; the Dool Arena wagering pool and the Hive refuel/parts/used-vehicle market are venue-specific economic nodes.
- **Two contrasting security-law models (G04).** Mos Eisley (open carry, cartel-licensed) ⇆ **Lianna** (weapons illegal, scanned entry, severe possession penalties) gives a clean high-security vs. low-security contrast for the security-zone tiers.
- **Blood-sport + racing activities (G23/G24).** The Dool Arena (no-ranged-weapons single-elim pit + wagering) and the Pits' swoop-racing/gang scene are two ready competitive activities, each with an economy tie-in.
- **Spatial/room templates.** Themed private back rooms (Exovar's Chasers/The Trap/Explorer's Guild/The Library), a vertical four-in-one tower (Fathoms), a rooftop sky-dock with fly-in/walk-in status (the Hive), a derelict free-port station with a hidden gun battery (Starlyte) — all reusable layout patterns for the web-client map.
- **Force-system seeds (G08/G14/G18).** The self-trained Force-sensitive seeking a teacher (Ace regular) is a Q1-safe recruitment hook; the Derriphan is an optional high-end Force-mystery boss.
- **Encounter ecology (G24).** The jexxel/crynoid/ice-modrol set + three graded environmental hazards are turnkey wilderness/biome content.

---

## 7. Era-translation cheat-sheet

| Wretched Hives element (GCW) | SW_MUSH handling (~20 BBY Clone Wars) |
|---|---|
| Imperial garrison / liaison officer / stormtrooper detachment (Starlyte Station) | Replace with station-security toughs, a Hutt enforcer presence, or a token Republic customs observer |
| "Rented from the Empire" / Imperial Transfer Post (Starlyte Station origin) | Abandoned Republic / Trade-Federation / old-corporate transfer station, or murky origin, now claimed by the proprietor |
| Mon Cal "freed from the Empire → joined the Rebellion → builds the Rebel fleet" (Fathoms) | Peaceful Old-Republic ocean world; shipyards build civilian/Republic vessels; drop the Empire/Rebellion arc entirely |
| Imperial nobility / royalty among the high rollers (Ace) | Sector grandees, war profiteers, Separatist & Republic notables, kajidic elite |
| "Death Star Bluff" (a card game) | Rename (e.g., "Dreadnaught Bluff" / an invented game) |
| AT-AT walker head as functional turret trophy (Emporium) | Salvaged battle-droid head or planetary-defense turret; keep the "trophy doubling as a gun emplacement" gag |
| "Imperial Royal Guard uniform" trophy / "Emperor's censors" / "a room used by Rebels" (Emporium) | Drop; the Jedi-lightsaber/Sun Guard/Mandalorian trophies are era-safe and stay |
| Santhe/Sienar "TIE-series" / Imperial-class starport (Lianna) | Generic starship manufacturer; recast the starport class; corporate-espionage frame is era-safe |
| Underground holos "celebrate the Jedi / glamorize the Rebellion / pro-Empire" (Adarlon) | Recast illicit holos as anti-war / pro-Separatist / anti-Hutt / simply censored entertainment |
| "Thorn in the side of the Empire" (Stend VI swoop gangs) | Thorn in the side of local/planetary authorities (or the Republic) |
| Hook captors: "Imperial torture games" / "captured by Imperials" (Broken Tusk) | A Hutt / slaver / crime-lord running illegal death-matches with captured prisoners |
| Hook framing: "Rebel agents / Alliance operative / cover blown" (Fathoms, Ace) | Fugitives wanted by a faction; a Republic-intelligence or Hutt-fugitive safehouse network |
| d66 entries 13, 21, 66 (stormtroopers / off-duty Imperials / Alliance-vs-Imperial double agent) | Local enforcers/clone patrol; off-duty soldiers/mercs/clones; a rival-faction double agent |
| Skill labels: *bureaucracy/law enforcement: Imperial*, *bureaucracy: Alliance* | Re-tag to *Republic / CIS / kajidic / Judicial / planetary*; dice unchanged |
| Joke band "Dengar and the Destroyers" | Drop or rename (canon-name brush) |
| Original cast, venue concepts, prices, layouts, creatures, hazards, the two appendix schemas, the Dool Arena, the Hive, the Sabre Club, Hutt crime-lord, ice-world ecology | **Keep** — era-agnostic |

---

## 8. Adventure-seed library (era-translated) — for the deterministic Director (G26)

Each "Loose Thread" is a pre-authored, branching template. Strip the Imperial/Rebel framing; the structures translate cleanly and become quest-template fodder scoped to a venue.

- **The Vanishings (kidnap-ring investigation).** PCs are hired to investigate disappearances at a resort; the missing are being taken by a slaver ring fronted by the venue. Patron variants: a wealthy parent seeking a vacationing child; a faction that lost an operative; an old acquaintance hunting a friend. The venue's hidden true-owner actively obstructs; careless PCs end up in chains themselves. *(Venue: the Ace; villain: the Sullustan slaver §4B + the Hutt §4A.)*
- **Knows Too Much (extraction/escort).** After a show, a popular entertainer begs the PCs for passage offworld — she's overheard the venue's secrets and two killers are after her, *operating independently* (one wants only to end her career, the other to end her). A tense escort with competing antagonists. *(Venue: the Ace; NPC: the entertainer §4B.)*
- **Forced Card (arena escape).** PCs are captured and made unwilling contestants in an illegal death-match run by a crime lord; survival odds rise if they plan an escape, recruit other prisoners, or smuggle out a call for help. Even after escaping, the operator's champions hunt them. *(Venue: the Broken Tusk's Dool Arena; recast captor from "Imperials" to a Hutt/slaver.)*
- **The Wrecked Hunter's Revenge (siege).** On a packed night, the bounty hunter whose crashed ship *became* the bar arrives with hired goons to settle the score with the owners — indifferent to collateral. The venue turns into a war zone; unlikely alliances form to survive. *(Venue: the Broken Tusk; era-safe as written.)*
- **Safe Harbor (fugitive safehouse run).** PCs are fugitives whose cover is blown and who must reach a hidden safehouse network keyed to a local "foster"/safehouse keeper — but reaching the city is only half the problem. *(Venue: Fathoms / Wildwater City; recast the "Rebel/Imperial" frame to a faction-agnostic fugitive network.)*
- **The Lurker (Force-horror mystery — optional, high-end).** Patrons at a dazzling nightclub are dying or vanishing; the cause is a hidden Force-parasite (§5B) Hosting a victim and erasing memories. A slow-burn investigation that should rely on dread, not a stand-up fight. *(Venue: Glow Dome; instanced/scripted only.)*

Combine with the §2C d66 table for ambient interruptions between beats. Per the roadmap §4, these slot into the deterministic quest-template library (no live LLM needed); flavor text can stay optional (Haiku/Mistral top layer).

---

## 9. Prune note

With this extraction in hand, **`WEG40153_compressed.pdf` (Wretched Hives of Scum and Villainy, ~22 MB) can be removed from the project.** This doc preserves the build-relevant content — the venue-profile and venue-creation schemas, the d66 encounter table, all eight venue templates (concept/layout/prices/security/illicit/NPCs/hooks), the NPC archetype roster with stats, the creature and hazard stat blocks, and the era-translated adventure-seed library — in canon-safe, ~20 BBY form. If you later want an exact deckplan plate (the *Starbound Misfit* freighter, book pp. 112–121) or a specific piece of art, the book is re-obtainable; the design content you'd actually build from is captured here.

**Roadmap status:** this closes the **Wretched Hive** entry in Tier 1 (roadmap §1) and step 1 of the suggested crime-core sequence (GG11 → **Wretched Hive** → Hideouts and Strongholds). Next in that sequence: **Hideouts and Strongholds** (base/stronghold layouts for housing/cities).
