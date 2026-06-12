# SW_MUSH — Sourcebook Mining & Crafting Experimentation Design
## Version 1.0 — April 14, 2026 · Opus Session 23

---

## Table of Contents

1. Sourcebook Inventory & Assessment
2. World Lore Extraction — 40 New Entries
3. NPC Stat Block Extraction — Imperial Military Templates
4. Equipment Price Validation & New Items
5. Ship Modification Rules (WEG Canon) vs. Current Implementation
6. Crafting Experimentation Parameters — Feature Design (#12)
7. Recommended Sourcebooks to Acquire
8. Implementation Plan

---

## 1. Sourcebook Inventory & Assessment

### Books In-Project — Confirmed Identities

| File | WEG ID | Title | Format | Pages | Mining Value |
|------|--------|-------|--------|-------|-------------|
| `WEG40120.pdf` | WEG40120 | D6 Revised & Expanded Core | Raw text (23K lines) | Full | ✅ Primary rules ref |
| `WEG40092.pdf` | WEG40092 | Imperial Sourcebook | Raw text (10K lines) | Full | NPC templates, Imperial org, world lore |
| `WEG40069.pdf` | WEG40069 | Galaxy Guide 7: Mos Eisley | JPEG zip (97 pg) | Full | NPC stats, locations, slang |
| `WEG40124_1.pdf` | WEG40124 | Galaxy Guide 1: A New Hope | JPEG zip (96 pg) | Full | Tatooine NPCs, Death Star, Yavin |
| `WEG40048_compressed.pdf` | WEG40048 | Gamemaster Screen/Kit | JPEG zip (73 pg) | Full | Spacecraft chart, damage tables |
| `WEG40093` (2 parts) | WEG40093 | Star Wars Sourcebook 2nd Ed | JPEG zip (149 pg) | Full | Ship stats, aliens, equipment costs |
| `WEG40027` (2 parts) | WEG40027 | Galaxy Guide 6: Tramp Freighters | JPEG zip (84 pg) | Full | Trading rules, ship mods, black market |

### Format Notes

- **WEG40120 and WEG40092** are raw text files (not actually PDFs despite extension). Fully searchable, direct extraction.
- All other books are ZIP archives containing per-page `.jpeg` + empty `.txt` files. Reading requires visual inspection of rasterized pages.
- Unzip via: `cp file.pdf file.zip && unzip file.zip -d outdir/` or `unzip -o file.pdf -d outdir/`

---

## 2. World Lore Extraction — 40 New Entries

The following entries are extracted from the sourcebooks to expand the `world_lore` table's 12 existing seed entries. They feed the Director AI digest and NPC brain context injection.

### 2A. Imperial Organization (from WEG40092 Imperial Sourcebook)

```python
# --- Add to SEED_ENTRIES in engine/world_lore.py ---

{
    "title": "Imperial Military Structure",
    "keywords": "imperial,military,navy,army,sector group,fleet",
    "content": "The Imperial military has two branches: the Imperial Navy (space) and Imperial Army (ground). A Sector Group typically includes 24 Star Destroyers, 1,600 smaller warships, and support vessels. Stormtroopers are separate from both branches and answer directly to the Emperor.",
    "category": "faction",
    "priority": 6,
},
{
    "title": "Moffs and Grand Moffs",
    "keywords": "moff,grand moff,tarkin,sector,governor,regional",
    "content": "Moffs govern entire sectors of the Empire. Grand Moffs command multiple sectors with even greater military resources. Grand Moff Tarkin devised the Doctrine of Fear — rule through terror rather than bureaucracy. After Tarkin's death at Yavin, the number of Grand Moffs is increasing as the Emperor seeks to tighten control.",
    "category": "faction",
    "priority": 6,
},
{
    "title": "COMPNOR",
    "keywords": "compnor,coalition,progress,propaganda,SAGroup,imperial youth",
    "content": "COMPNOR — the Commission for the Preservation of the New Order — is the Empire's propaganda and civilian control apparatus. It includes the Sub-Adult Group (youth indoctrination), the Imperial Security Bureau (ISB), and thousands of volunteer informants who report 'treasonous' activity among citizens.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Imperial Intelligence",
    "keywords": "imperial intelligence,ISB,ubiqtorate,analysis,bureau,spy",
    "content": "Imperial Intelligence operates parallel to the ISB but with different methods. The Ubiqtorate coordinates all intelligence operations from a hidden location. Analysis Bureau processes data, Intelligence Bureau runs field operations, and Internal Organization Bureau handles counterintelligence. They rival the ISB for influence and funding.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Stormtrooper Variants",
    "keywords": "stormtrooper,snowtrooper,seatrooper,spacetrooper,scout trooper,sandtrooper",
    "content": "Beyond standard stormtroopers, the Empire fields specialized variants: snowtroopers for polar environments, seatroopers for aquatic operations, spacetroopers in powered armor for zero-G boarding actions, scout troopers on speeder bikes for reconnaissance, and sandtroopers for desert operations on worlds like Tatooine.",
    "category": "faction",
    "zone_scope": "tatooine_mos_eisley,tatooine_outskirts",
    "priority": 5,
},
{
    "title": "Imperial Star Destroyers",
    "keywords": "star destroyer,imperial,ISD,executor,super star destroyer",
    "content": "The Imperial-class Star Destroyer is 1,600 meters long with a crew of over 37,000. It carries 72 TIE fighters, 20 AT-ATs, 30 AT-STs, and a full legion of stormtroopers. The mere appearance of a Star Destroyer in a system is usually enough to quell dissent. The Super Star Destroyer Executor, Darth Vader's flagship, is over 12 kilometers long.",
    "category": "item",
    "priority": 7,
},
{
    "title": "TIE Fighter Corps",
    "keywords": "tie fighter,tie interceptor,tie bomber,fighter pilot,imperial pilot",
    "content": "TIE fighters lack shields and hyperdrive — they are cheap, fast, and expendable. TIE pilots are elite but considered disposable by command. TIE Interceptors are faster with better firepower, used by ace squadrons. TIE Bombers deliver heavy ordnance against capital ships and ground targets.",
    "category": "item",
    "priority": 5,
},
{
    "title": "The Tarkin Doctrine",
    "keywords": "tarkin,doctrine,fear,death star,rule,terror",
    "content": "Governor Tarkin proposed that the Empire rule through fear of force rather than force itself. The Death Star was the ultimate expression of this doctrine. After its destruction at Yavin, the Emperor doubled down — assigning Darth Vader a personal fleet to hunt the Rebels and appointing more Grand Moffs with expanded military resources.",
    "category": "history",
    "priority": 7,
},
```

### 2B. Mos Eisley Detail (from WEG40069 Galaxy Guide 7)

```python
{
    "title": "Mos Eisley Slang",
    "keywords": "slang,bantha fodder,binary,bloated one,jawa trader,sand mine",
    "content": "Mos Eisley has its own vocabulary. 'Bantha Fodder' means worthless. 'Buy the Depp' means to die violently. 'Feed the Sarlacc' means to disappear forever. 'Jawa Trader' is anyone dishonest. 'Moisture Boy' mocks naive newcomers from farms. 'Suns-scorched ball' refers to Tatooine itself.",
    "category": "location",
    "zone_scope": "tatooine_mos_eisley,tatooine_outskirts,tatooine_docking",
    "priority": 4,
},
{
    "title": "Chalmun's Cantina Operations",
    "keywords": "cantina,chalmun,wuher,modal nodes,figrin,band,no droids",
    "content": "Chalmun's Cantina is owned by a Wookiee named Chalmun who won it in a sabacc game. Wuher tends bar and enforces the no-droids policy. Figrin Da'n and the Modal Nodes provide entertainment. The cantina serves as neutral ground — violence is discouraged but not uncommon. The back rooms host private deals and sabacc games.",
    "category": "location",
    "zone_scope": "tatooine_mos_eisley",
    "priority": 6,
},
{
    "title": "Gep's Grill and the Market Place",
    "keywords": "market,gep,grill,bantha burger,fillin,norun,whiphid",
    "content": "The Market Place is an open-air bazaar where agro-farmers sell produce and hunters trade meat. Gep's Grill sells Bantha Burgers (1.5 credits), Bantha Platters (2.0 credits), and Dewback Ribs. The stall owners Fillin Ta and Norun Gep are Whiphid meat traders who also run small-scale smuggling on the side.",
    "category": "location",
    "zone_scope": "tatooine_mos_eisley",
    "priority": 4,
},
{
    "title": "Spaceport Express",
    "keywords": "spaceport express,omon gantum,messenger,courier,delivery",
    "content": "Spaceport Express is a messenger and courier service run by the Quarren Omon Gantum. It handles legal goods — jewels, medicine, information — but has recently been infiltrated by smugglers using it to move contraband. The service is popular because it asks few questions about package contents.",
    "category": "location",
    "zone_scope": "tatooine_mos_eisley",
    "priority": 3,
},
```

### 2C. Tatooine Wilderness (from WEG40124 Galaxy Guide 1)

```python
{
    "title": "Jawa Society",
    "keywords": "jawa,sandcrawler,scavenger,droid,ion blaster,trade",
    "content": "Jawas are meter-tall scavengers who roam Tatooine's deserts in massive sandcrawlers. They salvage droids and technology from crashed ships and abandoned settlements, repairing and reselling them to moisture farmers. Jawas travel in extended clans of 20-30 and communicate in a rapid, chittering trade language.",
    "category": "species",
    "zone_scope": "tatooine_outskirts,tatooine_mos_eisley",
    "priority": 5,
},
{
    "title": "Tusken Raiders",
    "keywords": "tusken,sand people,raider,gaderffii,bantha,desert,attack",
    "content": "Tusken Raiders — Sand People — are fierce nomadic warriors native to Tatooine. They consider all water and territory their birthright and attack settlers who encroach on their lands. They ride single-file on banthas to hide their numbers, wield gaderffii sticks, and fire crude cycler rifles. Moisture farmers fear them above all other threats.",
    "category": "species",
    "zone_scope": "tatooine_outskirts",
    "priority": 6,
},
{
    "title": "Tatooine's Twin Suns",
    "keywords": "tatooine,tatoo,twin suns,desert,moisture,water,heat",
    "content": "Tatooine orbits the twin suns Tatoo I and Tatoo II. The brutal heat makes water the most precious commodity on the planet. Moisture farms extract water from the atmosphere using vaporators. Sandstorms can cast sand kilometers into the air, blinding ship sensors and cutting off settlements for weeks. The mining industry that once sustained Mos Eisley collapsed long ago.",
    "category": "location",
    "zone_scope": "tatooine_mos_eisley,tatooine_outskirts",
    "priority": 6,
},
{
    "title": "Owen and Beru Lars",
    "keywords": "lars,owen,beru,moisture farm,luke,homestead",
    "content": "Owen Lars was a moisture farmer on Tatooine who raised Luke Skywalker. He and his wife Beru were murdered by Imperial stormtroopers searching for stolen Death Star plans. The Lars homestead is now abandoned. Owen was known as a hard-working, protective man who wanted to keep Luke from the wider galaxy.",
    "category": "history",
    "zone_scope": "tatooine_outskirts",
    "priority": 5,
},
```

### 2D. Trading & Economy (from WEG40027 Tramp Freighters)

```python
{
    "title": "Speculative Trading",
    "keywords": "trade,cargo,speculative,buy,sell,profit,merchant",
    "content": "Speculative trading means buying cargo at one planet and selling it at another for profit. It requires capital, knowledge of supply and demand, and bargaining skill. Trading houses with established contacts dominate the market — independent traders compete on the margins. Roughly 20 percent of experienced traders' deals go sour.",
    "category": "item",
    "priority": 5,
},
{
    "title": "Trade Good Categories",
    "keywords": "trade goods,low tech,high tech,metals,minerals,luxury,foodstuffs,medicinal",
    "content": "The galaxy trades in eight categories of goods: Low Technology (crafts, furniture, cloth), Mid Technology (textiles, mechanical weapons), High Technology (computers, lasers, polymers), Metals (steel, copper, iron), Minerals (ores, cement, salt), Luxury Goods (spices, gems, art, liquor), Foodstuffs (grain, meat, produce), and Medicinal Goods (drugs, herbs).",
    "category": "item",
    "priority": 4,
},
{
    "title": "Technology Levels of Planets",
    "keywords": "technology,tech level,stone,feudal,industrial,atomic,information,space",
    "content": "Planets are classified by technology level: Stone (tribal, barter economy), Feudal (primitive manufacturing, slow transport), Industrial (mass production, beginning trade), Atomic (nuclear power, discovering space), Information (computers, approaching hyperspace), and Space (full galactic civilization). Supply and demand for goods varies dramatically by tech level.",
    "category": "item",
    "priority": 4,
},
{
    "title": "Drop-Point Delivery",
    "keywords": "delivery,cargo,drop point,freight,hauling,fee,transport",
    "content": "Drop-point delivery is the bread and butter of tramp freighters — hauling cargo from point A to point B for a fee. Standard fees are 5-10 credits per ton per day based on a x2 hyperdrive. It is the safest income but the least profitable. Finding customers requires a bureaucracy skill check.",
    "category": "item",
    "priority": 4,
},
{
    "title": "The Black Market",
    "keywords": "black market,illegal,contraband,fence,restricted,underground",
    "content": "The black market operates on every populated world. Finding a contact requires a streetwise roll — difficulty varies by population and Imperial presence. Black marketeers sell legal goods at x2, restricted goods at x4, and illegal goods at x5 their base price. They buy at x0.5 to x2.5 depending on legality. The Empire classifies infractions from Class One (conspiracy, cloaking devices — ship impounded, 5-30 years penal colony) down to Class Five (minor customs violations — fines).",
    "category": "item",
    "priority": 5,
},
{
    "title": "Loan Sharks",
    "keywords": "loan,shark,debt,payment,interest,credit,borrow",
    "content": "Loan sharks offer credits to desperate spacers at crushing interest rates. Miss one payment and you get a warning. Miss two and you get a beating. Miss three and the loan shark sends bounty hunters. Smart captains avoid loans entirely — but sometimes a ship modification or emergency repair leaves no other option.",
    "category": "item",
    "priority": 4,
},
```

### 2E. Ship Systems (from WEG40048 GM Screen + WEG40027)

```python
{
    "title": "Ship Modification Basics",
    "keywords": "modification,ship,upgrade,install,shipyard,repair,customize",
    "content": "Ship modifications cost money and cargo space. Improvements to ion drives, shields, hull, and weapons all add weight that reduces cargo capacity. Used parts cost 50 percent less but break down more often. A competent mechanic can do installations themselves with starship repair rolls, cutting the price by half. Renting a fully-equipped repair bay costs about 100 credits per day.",
    "category": "item",
    "priority": 5,
},
{
    "title": "Hyperdrive Classes",
    "keywords": "hyperdrive,multiplier,x1,x2,backup,hyperspace,jump",
    "content": "Hyperdrive multipliers determine travel speed — lower is faster. A x1 is military-grade and extremely expensive (15,000 credits, 18 tons). Stock freighters typically have x2 (10,000 credits). Slower drives like x4 or x5 are cheap but dramatically increase travel time. Removing a backup hyperdrive frees cargo space and earns a few hundred credits — but risks stranding you in deep space.",
    "category": "item",
    "priority": 5,
},
{
    "title": "Astrogation Hazards",
    "keywords": "astrogation,mishap,hyperspace,navigation,off course,mynock",
    "content": "Astrogation errors can be catastrophic. A standard journey requires a difficulty of 11-15. Flying without a nav computer raises this to 21-30. Mishaps include hyperdrive cutout, radiation fluctuations, going off-course, mynock infestations, close calls with gravity wells, and collisions with heavy damage. Each extra hour saved on a jump adds +1 difficulty.",
    "category": "item",
    "priority": 5,
},
{
    "title": "Docking Fees and Ship Costs",
    "keywords": "docking,fee,hangar,spaceport,maintenance,fuel,restock",
    "content": "Standard-class spaceports charge 50 credits per day for docking. Imperial-class ports charge up to 150 credits per day. Standard maintenance and restocking costs 10 credits multiplied by crew plus passengers, multiplied by days since last restock. Lightly damaged ships cost 1,000 credits to repair, heavily damaged 2,000, severely damaged 3,000 — plus replacement costs for any destroyed systems.",
    "category": "item",
    "priority": 4,
},
```

### 2F. Corellia & General Galaxy (from WEG40092 + WEG40093)

```python
{
    "title": "Imperial Customs Operations",
    "keywords": "customs,inspection,scan,cargo,manifest,permit,patrol",
    "content": "Imperial Customs uses patrol ships and boarding parties to inspect cargo. Outer Rim patrols are infrequent and understaffed — Customs agents there are often poorly trained locals who can be bribed. Core world inspections are thorough and professional. A captain must apply for weapon permits at Imperial offices — bureaucracy vs. the weapon's damage code determines approval.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Imperial Law Infractions",
    "keywords": "infraction,crime,class,punishment,impound,fine,arrest",
    "content": "The Empire classifies spacer crimes in five classes. Class One (conspiracy, cloaking devices, attacking Imperial ships): ship impounded, 5-30 years prison. Class Two (illegal weapons, smuggling rated-X goods): arrest, impound, heavy fines. Class Three (customs evasion, minor smuggling): fines 2,000-10,000 credits. Class Four (expired permits, minor violations): fines 500-2,000. Class Five (paperwork errors): warnings or small fines.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Corellian Shipyards",
    "keywords": "corellian,CEC,shipyard,engineering,YT,freighter,corvette",
    "content": "Corellian Engineering Corporation produces some of the galaxy's most popular starships, including the YT-series freighters and CR90 corvettes. Corellians have a reputation as exceptional pilots and engineers. The shipyards in Coronet City are among the largest non-Imperial facilities in the galaxy, turning out everything from personal yachts to military vessels.",
    "category": "location",
    "zone_scope": "corellia_coronet",
    "priority": 5,
},
{
    "title": "Nar Shaddaa Criminal Networks",
    "keywords": "nar shaddaa,hutt,criminal,network,undercity,spice,vice",
    "content": "Nar Shaddaa's criminal networks operate in layers. The Hutt Cartel controls the macro economy from the upper towers. Mid-level operators — smuggler captains, spice dealers, arms merchants — work the promenades and cantinas. The Undercity harbors the desperate: gangs, fugitives, debtors, and those who have fallen through every safety net the galaxy never had.",
    "category": "location",
    "zone_scope": "nar_shaddaa_upper,nar_shaddaa_lower,nar_shaddaa_undercity",
    "priority": 6,
},
{
    "title": "Kessel Spice Mining",
    "keywords": "kessel,spice,mine,glitterstim,prisoner,imperial,warden",
    "content": "Kessel's spice mines are among the most brutal labor operations in the galaxy. Prisoners — political dissidents, captured Rebels, debtors — mine glitterstim spice in absolute darkness. The spice is light-sensitive and must be harvested blind. Imperial wardens run the operation with ruthless efficiency. Guards are well-armed but poorly motivated — many are serving punishment postings themselves.",
    "category": "location",
    "zone_scope": "kessel_mines",
    "priority": 6,
},
```

### 2G. Creatures (from WEG40093 Star Wars Sourcebook)

```python
{
    "title": "Banthas",
    "keywords": "bantha,beast,mount,tusken,tatooine,herd",
    "content": "Banthas are massive, shaggy beasts native to Tatooine. They serve as mounts for Tusken Raiders and as livestock for settlers. Bantha meat is a staple food. An adult bantha stands over 2 meters tall and weighs several tons. They are docile unless provoked and form deep bonds with their Tusken riders.",
    "category": "species",
    "zone_scope": "tatooine_outskirts",
    "priority": 4,
},
{
    "title": "Dewbacks",
    "keywords": "dewback,lizard,mount,patrol,imperial,desert",
    "content": "Dewbacks are large reptilian creatures used as patrol mounts on Tatooine. Imperial sandtroopers ride them through Mos Eisley's streets. They are cold-blooded and become sluggish at night but are well-adapted to desert heat. Dewback meat is edible and sold at market stalls.",
    "category": "species",
    "zone_scope": "tatooine_outskirts,tatooine_mos_eisley",
    "priority": 4,
},
{
    "title": "Mynocks",
    "keywords": "mynock,parasite,ship,power,silicon,space,pest",
    "content": "Mynocks are silicon-based parasites that attach to starships and feed on power cables and energy conduits. They inhabit asteroid fields, derelict ships, and the dark spaces between stars. A mynock infestation can drain a ship's power systems. They are a common hazard for any ship that spends time in debris fields or makes port at poorly-maintained stations.",
    "category": "species",
    "priority": 4,
},
{
    "title": "The Rancor",
    "keywords": "rancor,jabba,pit,monster,dathomir,beast",
    "content": "Rancors are massive carnivorous beasts native to Dathomir. Jabba the Hutt kept one in a pit beneath his throne room on Tatooine, feeding it prisoners and enemies. Standing over 5 meters tall with razor claws and armored hide, a rancor is nearly impossible to kill with personal weapons. Luke Skywalker famously killed Jabba's rancor by crushing it under a gate.",
    "category": "species",
    "zone_scope": "tatooine_outskirts",
    "priority": 5,
},
```

**Total: 28 new entries + 12 existing = 40 world lore entries.**

---

## 3. NPC Stat Block Extraction — Imperial Military Templates

These are canonical WEG stat blocks from the Imperial Sourcebook (WEG40092). They can be used directly in `npcs_gg7.yaml` for Imperial NPCs in guard roles, patrol encounters, and Director AI events.

### 3A. Combat NPCs (for `npcs_gg7.yaml` or dynamic spawning)

| NPC Type | DEX | KNO | MEC | PER | STR | TEC | Key Skills | Equipment |
|----------|-----|-----|-----|-----|-----|-----|-----------|-----------|
| Standard Stormtrooper | 2D | 2D | 2D | 2D | 2D | 2D | blaster 4D, dodge 4D, brawling_parry 4D, brawling 3D | Armor (+2D phys/+1D energy/-1D DEX), blaster rifle (5D), blaster pistol (4D) |
| Snowtrooper | 2D | 2D | 2D | 2D | 3D | 2D | blaster 5D, blaster_artillery 4D, dodge 3D, brawling_parry 4D, survival_arctic 4D, search 3D+1, brawling 4D | Snowtrooper armor, blaster rifle, concussion grenades (5D) |
| Scout Trooper | 3D | 2D | 3D+2 | 2D+1 | 1D+1 | 1D | (implied from stats) | Speeder bike, blaster pistol |
| Imperial Army Trooper | 3D | 1D+1 | 1D+1 | 2D | 3D+1 | 1D | blaster 4D, dodge 3D, brawling 4D | Blast vest (+1D phys), blaster rifle (5D) |
| Veteran Army Trooper | 3D+1 | 2D | 2D | 2D+1 | 3D+2 | 2D | blaster 5D, dodge 4D, brawling 5D, tactics 3D | Blast vest, blaster rifle, grenades |
| Imperial Naval Trooper | 2D+1 | 1D+1 | 1D+2 | 3D | 2D+2 | 1D | blaster 3D, dodge 3D, brawling 3D | Blast vest, blaster pistol (4D) |
| Typical Imperial Pilot | 2D+1 | 1D+1 | 3D | 2D | 2D | 1D+1 | starship_piloting 4D, starship_gunnery 3D+1 | Flight suit, blaster pistol |
| TIE Fighter Pilot | 3D+1 | 2D | 4D | 3D | 3D | 2D | starfighter_piloting 5D+1, starship_gunnery 4D+2 | Flight suit, blaster pistol |
| Typical Imperial Officer | 2D+2 | 2D+1 | 2D+2 | 2D+2 | 3D | 2D+1 | blaster 4D, command 4D+2, tactics 3D+1, bureaucracy 3D | Blaster pistol, uniform |
| Imperial Advisor | 2D+1 | 4D+1 | 2D | 4D+1 | 3D | 2D | con 5D+1, persuasion 5D+2, bureaucracy 6D, intimidation 5D | Holdout blaster |

### 3B. Usage Recommendations

- **Stormtrooper block** → Use as-is for security zone guards, Imperial patrol encounters, and Director AI "Imperial raid" events
- **Army Trooper block** → Cheaper garrison forces for non-critical zones
- **TIE Pilot block** → Space combat encounters; these are significantly more skilled than generic pilots
- **Imperial Officer** → For customs inspections, checkpoint encounters, and faction mission givers
- **Advisor** → For political intrigue scenarios and Director AI events involving Imperial politics

---

## 4. Equipment Price Validation

The Star Wars Sourcebook 2nd Ed (WEG40093) provides canonical equipment costs. Key validations against our current economy:

### 4A. Weapons (vs. current base_cost in schematics.yaml)

| Item | WEG Canon Cost | Our base_cost | Status |
|------|---------------|---------------|--------|
| Blaster Pistol | 500 | 500 | ✅ Match |
| Sporting Blaster | 350 | 500 | ⚠️ Ours higher |
| Blaster Rifle | 1,000 | 1,000 | ✅ Match |
| Hold-Out Blaster | 275-300 | 300 | ✅ Match |
| Vibroblade | 250 | 250 | ✅ Match |
| Blaster Carbine | 900 | 900 | ✅ Match |
| Stun Pistol | 200 (implied) | 200 | ✅ Match |

### 4B. Equipment Costs for World Lore / NPC Vendor Pricing

| Item | WEG Canon Cost | Notes |
|------|---------------|-------|
| Medpac | 100 | Match |
| Bacta Tank | 3,000 | Medical facility equipment |
| Comlink (standard) | 100 | Baseline comm device |
| Macrobinoculars | 100 | Useful survey tool |
| Breath Mask | 50 | Our crafting cost: 150 (crafted = premium) |
| Power Scanner | 150 | Sensor tool |
| Computer Tool Kit | 200 | For slicing/tech work |
| Droid Tool Kit | 200 | For droid repair |

### 4C. Vehicle & Housing Costs (from WEG40093)

| Item | Rent/day | Buy | Notes |
|------|----------|-----|-------|
| Ground Car | 50/day | 6,000 new / 1,500 used | |
| Landspeeder | 75/day | 10,000 new / 2,000 used | |
| Swoop | 30/day | 5,000 new / 1,000 used | |
| Speeder Bike | 30/day | 5,000 new / 1,000 used | |
| Stock Light Freighter | 1,200+/day | 100,000 new / 25,000 used | Matches our YT-1300 cost |
| Hovel | 150-250/mo | N/A | |
| Regular Apartment | 250-500/mo | N/A | |
| Luxury Apartment | 500-1,400/mo | N/A | |
| House | 750-1,800/mo | 35,000 | |
| Storage Space | 10-100/mo | N/A | |

**Action**: These validate our housing tier pricing. Our Tier 1 (500cr) and Tier 2 (2,000cr) are in the correct range for the economy.

---

## 5. Ship Modification Rules (WEG Canon vs. Current)

### 5A. WEG Canon Rules (from Tramp Freighters Ch. 8)

The WEG system has several key principles our implementation should respect:

1. **Weight/Cargo Tradeoff**: Every modification adds weight, reducing cargo capacity. Ion drives cost 8-28 tons. Shields add 10-25 tons per die. Hull plating adds significant weight. This creates a meaningful player choice — more combat capability means less trading capacity.

2. **Modification Caps**: Ion drives can only be improved by +2 pips above stock. Beyond that, the entire engine must be replaced. This prevents infinite stacking.

3. **Stat Tradeoffs**: Increasing hull by 1 pip DECREASES maneuverability by 1 pip. This is a brilliant design — there's no free lunch.

4. **Cost Scaling**: Costs scale with the stat level being achieved, not linearly. Going from 4D→4D+1 hull costs 4 (hull dice) × 1,000 = 4,000cr. Going from 5D→5D+1 costs 5,000cr.

5. **Used Parts**: Cost 50% less but break down more often. Salvaged parts from wrecks cost even less (25%) but may fail catastrophically.

6. **DIY Installation**: A competent mechanic (starship repair rolls, Easy to Very Difficult) can install modifications themselves, halving labor cost but taking longer.

### 5B. Current Implementation Assessment

Our ship component schematics in `schematics.yaml` already capture the core loop — craft components, install them for stat boosts. But we're missing:

- **Modification caps** — no limit on stacking stat boosts
- **Hull/maneuverability tradeoff** — WEG says hull+ means maneuver−
- **Weight accounting** — `cargo_weight` field exists but may not be enforced
- **Used/salvaged quality tiers** — not implemented

These should be addressed as part of a ship customization polish pass, not the crafting experimentation feature.

---

## 6. Crafting Experimentation Parameters — Feature Design (#12)

### 6A. Design Philosophy

The current `experiment` command is functional but flat — it just adds +5 difficulty and +20 quality on success. The LOTJ-inspired design from the competitive analysis calls for **engineer-tunable parameters per schematic category** that create meaningful choices for crafters.

The WEG Tramp Freighters ship modification rules provide the perfect template: **tradeoffs**. Every improvement costs something. Hull armor costs maneuverability. Engine speed costs cargo capacity. This principle should extend to ground crafting: experimenting on a blaster might increase damage but decrease accuracy (fire control), or increase power but reduce durability.

### 6B. Experimentation Parameters per Category

Add an `experiment_params` block to each schematic in `schematics.yaml`:

```yaml
# Example: Blaster Pistol (Basic)
- key: blaster_pistol_basic
  name: "Blaster Pistol (Basic)"
  # ... existing fields ...
  experiment_params:
    # Which stat axes the crafter can tune
    axes:
      - axis: damage
        label: "Power Output"
        boost_per_margin: 0.5    # +0.5 quality per margin point toward this axis
        tradeoff_axis: durability
        tradeoff_ratio: 0.3      # each point of damage boost costs 0.3 durability
      - axis: accuracy
        label: "Barrel Calibration"
        boost_per_margin: 0.4
        tradeoff_axis: damage
        tradeoff_ratio: 0.2
      - axis: durability
        label: "Reinforced Housing"
        boost_per_margin: 0.6
        tradeoff_axis: null      # pure quality investment, no tradeoff
    max_experiments: 3           # max experiment attempts per item
    difficulty_escalation: 3     # +3 difficulty per prior experiment on same item
    fumble_risk: destroy         # fumble = item destroyed
    failure_risk: degrade        # failure = quality decreases by margin
```

### 6C. Experiment Flow (Updated)

1. Player crafts an item normally → receives item with quality score
2. Player uses `experiment <item> <axis>` → chooses which parameter to tune
3. System rolls skill check at `base_difficulty + 5 + (3 × prior_experiments_on_item)`
4. **Critical Success**: Boost the chosen axis by `boost_per_margin × margin`, apply `QUALITY_MULT_EXP_CRIT` (×2.0). If tradeoff_axis exists, reduce it by `tradeoff_ratio × boost`.
5. **Success**: Boost chosen axis by `boost_per_margin × margin`, apply tradeoff.
6. **Failure**: Quality degrades. The item gets worse. The more you miss by, the worse it gets.
7. **Fumble**: Item destroyed. Materials lost. Pain.
8. Each item tracks `experiment_count` — after `max_experiments`, no more attempts possible.

### 6D. What "Axes" Mean Mechanically

For **weapons** (output_type: weapon):
- `damage` → modifies the weapon's damage dice (e.g., 4D → 4D+1)
- `accuracy` → modifies a hidden accuracy bonus (added to attack roll)
- `durability` → modifies max_condition (how long before repair needed)

For **ship components** (output_type: component):
- `stat_boost` → modifies the component's stat_boost value
- `weight` → modifies cargo_weight (less weight = more cargo)
- `reliability` → modifies failure chance (not yet implemented, but designed for)

For **consumables** (output_type: consumable):
- `potency` → modifies healing amount or effect strength
- `duration` → modifies effect duration (for stimpacks)
- `yield` → modifies number of uses (e.g., 1 medpac → 2 uses)

For **survival_gear** (output_type: survival_gear):
- `effectiveness` → modifies hazard mitigation strength
- `durability` → modifies max_uses

### 6E. Data Model Changes

**Item inventory** (character attributes JSON → items list):
Add `experiments` field to each item:
```json
{
    "key": "blaster_pistol",
    "name": "Blaster Pistol",
    "quality": 78,
    "crafter": "Kael Voss",
    "experiment_count": 2,
    "experiment_log": [
        {"axis": "damage", "boost": 3.2, "tradeoff": {"durability": -0.96}},
        {"axis": "accuracy", "boost": 1.8, "tradeoff": {"damage": -0.36}}
    ],
    "effective_stats": {
        "damage_mod": 2.24,
        "accuracy_mod": 1.8,
        "durability_mod": -0.96
    }
}
```

**schematics.yaml**: Add `experiment_params` to each schematic (see §6B above).

**No schema migration needed** — this is all stored in the character attributes JSON and the YAML data file.

### 6F. Default Experiment Params by Category

To avoid specifying params for every schematic, define category defaults:

```python
DEFAULT_EXPERIMENT_PARAMS = {
    "weapon": {
        "axes": [
            {"axis": "damage", "label": "Power Output",
             "boost_per_margin": 0.5, "tradeoff_axis": "durability", "tradeoff_ratio": 0.3},
            {"axis": "accuracy", "label": "Barrel Calibration",
             "boost_per_margin": 0.4, "tradeoff_axis": "damage", "tradeoff_ratio": 0.2},
            {"axis": "durability", "label": "Reinforced Housing",
             "boost_per_margin": 0.6, "tradeoff_axis": None},
        ],
        "max_experiments": 3,
        "difficulty_escalation": 3,
        "fumble_risk": "destroy",
        "failure_risk": "degrade",
    },
    "component": {
        "axes": [
            {"axis": "power", "label": "Power Efficiency",
             "boost_per_margin": 0.3, "tradeoff_axis": "weight", "tradeoff_ratio": 0.4},
            {"axis": "weight", "label": "Weight Reduction",
             "boost_per_margin": 0.4, "tradeoff_axis": "reliability", "tradeoff_ratio": 0.3},
            {"axis": "reliability", "label": "Stress Testing",
             "boost_per_margin": 0.5, "tradeoff_axis": None},
        ],
        "max_experiments": 2,
        "difficulty_escalation": 4,
        "fumble_risk": "destroy",
        "failure_risk": "degrade",
    },
    "consumable": {
        "axes": [
            {"axis": "potency", "label": "Concentrated Formula",
             "boost_per_margin": 0.6, "tradeoff_axis": "yield", "tradeoff_ratio": 0.5},
            {"axis": "yield", "label": "Extended Batch",
             "boost_per_margin": 0.4, "tradeoff_axis": "potency", "tradeoff_ratio": 0.3},
        ],
        "max_experiments": 2,
        "difficulty_escalation": 3,
        "fumble_risk": "destroy",
        "failure_risk": "degrade",
    },
    "survival_gear": {
        "axes": [
            {"axis": "effectiveness", "label": "Enhanced Protection",
             "boost_per_margin": 0.5, "tradeoff_axis": None},
        ],
        "max_experiments": 1,
        "difficulty_escalation": 5,
        "fumble_risk": "degrade",
        "failure_risk": "degrade",
    },
}
```

### 6G. Updated Command Syntax

```
experiment                           — Show experimenting help
experiment <item#> <axis>            — Experiment on inventory item
experiment list <item#>              — Show available axes + history for item
```

Example session:
```
> experiment list 3
═══════════════════════════════════════════════════════════
  EXPERIMENTATION — Blaster Pistol (Quality: 78)
  Crafter: Kael Voss    Experiments: 1/3
═══════════════════════════════════════════════════════════
  AVAILABLE AXES:
    1. Power Output     [damage ↑ / durability ↓]
    2. Barrel Calibration [accuracy ↑ / damage ↓]
    3. Reinforced Housing [durability ↑ / no tradeoff]

  EXPERIMENT LOG:
    #1: Power Output — damage +3.2, durability -0.96
        [blaster_repair (experimental): 7D vs 17 — roll 22, margin 5]
═══════════════════════════════════════════════════════════

> experiment 3 power
  [blaster_repair (experimental): 7D vs 20 — roll 25, margin 5]

  ⚡ EXPERIMENT SUCCESS — Power Output
  Your Blaster Pistol's damage output increases. (+2.5 damage)
  Tradeoff: durability reduced slightly. (-0.75 durability)
  Experiments remaining: 1/3
```

### 6H. Economy Impact

- **Experimentation is free** (no material cost) but risky — fumbles destroy the item
- **Difficulty escalation** ensures diminishing returns — the 3rd experiment on an item is very hard
- **Tradeoffs** prevent items from becoming universally superior — a "power-tuned" blaster hits harder but needs repair sooner
- **Max experiments cap** prevents infinite optimization
- **Masterwork items** (quality 90+) are still the primary goal of the craft→experiment loop, but now the crafter also chooses *how* their masterwork excels

---

## 7. Recommended Sourcebooks to Acquire

### High Priority (would directly enrich existing game content)

| Book | WEG ID | Why | Effort to Mine |
|------|--------|-----|----------------|
| Galaxy Guide 11: Criminal Organizations | WEG40090 | Nar Shaddaa depth, Hutt faction detail, Black Sun | Medium |
| Galaxy Guide 10: Bounty Hunters | WEG40082 | Bounty profession lane, famous hunter NPCs | Medium |

### Medium Priority (useful for future expansion)

| Book | WEG ID | Why |
|------|--------|-----|
| Cracken's Rebel Field Guide | WEG40046 | Rebel equipment schematics, slicing tools |
| Galaxy Guide 9: Fragments from the Rim | WEG40080 | Fringe world locations, mercenary contacts |
| Galaxy Guide 2: Yavin and Bespin | WEG40038 | Cloud City, Rebel base — future destinations |

### Not Needed

| Book | Why Skip |
|------|----------|
| Rules of Engagement (WEG40109) | Military tactics — too GM-specific |
| Platt's Smugglers Guide (WEG40141) | Already have via Tramp Freighters |
| Star Warriors (WEG40201) | Board game rules, not RPG-compatible |

---

## 8. Implementation Plan

### Drop 1: World Lore Expansion (Sonnet — Small, ~1 hour)

**Files modified:**
- `engine/world_lore.py` — Add 28 new entries to `SEED_ENTRIES`

**Deployment:** Requires clearing the `world_lore` table for re-seeding, OR adding an `@lore/reseed` admin command that appends missing entries by title.

### Drop 2: Crafting Experimentation Engine (Sonnet — Medium, ~4-6 hours)

**Files modified:**
- `engine/crafting.py` — Add `DEFAULT_EXPERIMENT_PARAMS`, `resolve_experiment()`, experiment tracking helpers
- `parser/crafting_commands.py` — Rewrite `ExperimentCommand` with axis selection, `experiment list` subcommand
- `data/schematics.yaml` — Add `experiment_params` overrides for any schematics that need non-default tuning

**Files unchanged:**
- `db/database.py` — No schema changes (experiment data lives in item JSON)
- `engine/skill_checks.py` — Uses existing `perform_skill_check()`

### Drop 3: Imperial NPC Templates (Sonnet — Small, ~1-2 hours)

**Files modified:**
- `data/npcs_gg7.yaml` — Add Imperial NPC templates for use in guard spawning and Director AI events
- Potentially `build_mos_eisley.py` — Place Imperial patrol NPCs in appropriate rooms

### Optional: Architecture Doc v27

Update §14 (Crafting) with experimentation parameters, §24 (Sourcebook Reference) with confirmed book identities, and §18A (Competitive Analysis) to mark #12 as DELIVERED.

---

*End of Sourcebook Mining & Crafting Experimentation Design Document — Version 1.0*
*Sources: WEG40092, WEG40069, WEG40124, WEG40048, WEG40093, WEG40027, WEG40120*
*Next: Sonnet implementation session — Drop 1 (world lore) + Drop 2 (experimentation engine)*
