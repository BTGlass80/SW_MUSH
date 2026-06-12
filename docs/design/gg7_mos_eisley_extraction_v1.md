# SW_MUSH — Galaxy Guide 7: Mos Eisley Extraction
## Version 1.0 — May 30, 2026
## Source: WEG40069 — *Galaxy Guide 7: Mos Eisley*, West End Games (96 pages, scanned JPEG, OCR'd)
## Purpose: Distill the build-relevant Mos Eisley content so the 22 MB scan (`WEG40069.pdf`) can be pruned from the project.

---

## 0. What this is, and the two mandates that govern it

This is a **design reference**, not a transcription. Everything below is paraphrased and
reorganized for the SW_MUSH Mos Eisley build (the tight-seed relayout, the POI/bearing
substrate, the docking and economy systems). The source is firmly **A New Hope era (GCW)**,
so two project rules are applied throughout:

- **Era translation (Clone Wars, ~20 BBY).** The Empire does not exist yet, so everything
  Imperial is stripped or replaced: the Imperial Prefect, Imperial customs/garrison,
  stormtroopers, the Rebel Alliance, and the post-droid-escape "quarantine of Mos Eisley"
  are all off-era. At ~20 BBY the authority that actually runs Tatooine's underworld is the
  **Hutt cartel** (canon-consistent — the Hutts dominate the planet for centuries). The
  Clone Wars reach Mos Eisley only as distant news: disrupted trade lanes, refugees,
  war-profiteering, and a brisk black market in contraband and arms. The Republic has
  essentially no footprint here.
- **Q1 canon-character policy.** GG7 names a number of canonical figures. **None may appear
  as named NPCs.** Each is reduced below to an era-safe archetype. The project already
  preserves `JABBA'S PALACE` as a pinned *location* name; the Hutt himself is referenced only
  generically ("the dominant cartel") or off-screen with absence framing.

**Omitted on purpose:** Chapter Three ("Adventure Ideas," pp. ~85–96) is ANH-era plot
scaffolding (Imperial/Rebel hooks, the droid-hunt quarantine, etc.) and was **not** extracted.
Chapter One ("Tatooine," pp. ~5–14) is planet-scale color already covered by our world data;
only the Tatooine stat line is captured below for convenience.

---

## 1. Tatooine stat line (for convenience)

Terrestrial · Hot · Type I (breathable) atmosphere · Dry hydrosphere · Standard gravity ·
Desert terrain · 23-hour day · 304-day local year · Sapients: Humans, Jawas (N), Tusken
Raiders (N) · Standard-class starport · Population ~80,000 (no census ever taken) ·
Function: smuggling, trade, subsistence. (Binary system; long mistaken for a third sun.)

---

## 2. The town at a glance — physical character

Mos Eisley reads as **a hodge-podge that blends into the desert**. From a distance it's just
sand-colored mounds shimmering in heat-haze; up close it resolves into low concrete, stone,
and plastoid domes radiating outward from the **power and water distribution plants**.

- **Construction is subterranean by tradition.** Most structures are dug in, with one or two
  stories breaking the surface. Roofs are curved/domed to shed sand and resist dune buildup,
  and a subterranean emphasis blunts sandstorms. Newer (mostly commercial) buildings rise
  four or five stories using **pourstone over durasteel double-walls with circulating coolant
  between them**, which sidesteps the shifting-sand problem of deep pits.
- **Sand traps everywhere.** Virtually every entrance has electrostatic repellors ("sand
  traps"), in varying states of repair, to keep drifting sand out.
- **No urban planning, no neighborhoods.** Family homes sit beside landing bays sit across
  from heavy factories. Crucially for navigation design: **the streets are unsurfaced and
  unnamed.** Directions are given by **landmark and business**, never by intersection — "it's
  assumed that if you want to go somewhere, you know how to find it."
- **The core.** At the heart sit the original spaceport docking bays, the power/water plants,
  and the **spaceport control tower**. The utility network never reached most of the city, so
  moisture farms are tucked into odd corners. The core also sits **over the old ore mine** —
  unstable ground, minor sinkholes that open and close with every storm.
- **Industry to the north.** The largest employer is **Notsub Shipping** (see §6). Limited
  manufacturing turns specially treated ores into droids, landspeeders, and sand skiffs.

### 2.1 The Underground (high-value for hidden-zone design)
Beneath the town lies a **wholly unregulated network** of abandoned mines and excavations
left by the original settlers. It's used for dumping contraband and toxic waste, discreet
agro-farming, and outright illegal operations; the cartel's people move through the tunnels
**unobserved** and treat them as rent-free warehouses. **Only about a fifth has ever been
mapped** — and the cartel has mapped more of it than every corporation combined. This is a
ready-made hidden-tunnel/smuggler-route layer (web-client map overlay; ties to the
contestable-wilderness hidden-zone patterns).

---

## 3. Authority and law (era-translated)

**Original (GCW):** Mos Eisley is nominally run by an Imperial Prefect whose decrees are
rubber-stamped by the planetary governor — a structure built for bribery and intimidation,
with the Hutt buying off the Prefect's advisors. A small, newly-formed police force
(ex-militia in nicer uniforms) handles appearances; real trouble falls to the **local
militia**, current and retired. Most businesses hire **private security**. Indiscriminate
crime is deterred less by law than by the cartel itself, which hands out neighborhood
"licenses" to gangs, collects protection money, and keeps eyes everywhere.

**CW translation:** Delete the Prefect and the Imperial scaffolding. At ~20 BBY there is **no
real civic government** — the dominant **Hutt cartel** is the de facto authority, governing
through licensed gangs, bought-off local administrators, and a web of informants. Keep the
militia, the private-guard economy, and the licensing model intact; they map cleanly onto our
security model (Mos Eisley as a mixed/low-security zone, with cartel-"SECURED" pockets).

**Crime & punishment flavor (era-safe, keep):** law is a suggestion, not a policy. Courts
welcome bribery and judge by *who* you are and *where* it happened. Minor infractions are
overlooked — this is a galactic crossroads and outsiders aren't expected to know local
custom. Open carry of small arms is normal. The one consistent rule: **outsiders who wrong
residents are punished hard; residents who wrong each other get a slap.** Tolerance runs much
higher here than in the Core.

---

## 4. The spaceport and docking bays (primary build content)

### 4.1 What a docking bay *is*
A Mos Eisley bay is **a sunken pit**, not a pad: floor ~10 meters below street level, with the
offices and maintenance below ground too. They're old and small, built back when traffic was
shuttles and small tramp freighters (e.g. the ubiquitous YT-1300), and engineered to take the
**backblast of older Orion-style ion sublight engines**. Modern Hoersch-Kessel drives plus
repulsorlift maneuvering make the pits unnecessary, but they stay in use because rebuilding
costs credits nobody wants to spend. (All of this lore is pre-Imperial and fully era-safe.)

### 4.2 Fee model (drop straight into the economy)
Rates run **far below galactic standard** — part of what makes Mos Eisley a smuggler's port:

| Service | Rate (GG7 baseline) |
|---|---|
| Berth | ~25 cr/day (crept up from 20) |
| Resupply (consumables) | ~8 cr per person-day, ~20% below standard |
| Fuel cells (replace) | ~10 cr/cell (a light freighter holds ~50) |
| Recharge | ~10 cr/cell/hour (empty light freighter ≈ 50 hours) |
| Warehouse storage | ~5 cr/ton/week, 250-ton capacity per warehouse |

These slot directly into our `docking_fee` / resupply / fuel sinks (already in the credit log
per the economy audits).

### 4.3 Independent bay operators (the De Maal pattern → reusable NPC archetype)
Bays are run by **independent operators** who pay the cartel "insurance" for protection from
thugs and meddling officials. The canonical example is a **Duros couple** (anonymize the
names if used as NPCs) who run **Docking Bay 94 plus five others (bays 27, 43, 67, 71, 86)**, a
service shuttle, and several warehouses — the warehouses being most of their profit. They keep
**three part-time hands** (load/unload, servicing, cleaning, mynock inspections) and a clutch
of not-quite-competent droids.

**Built-in tension hook (era-safe):** their business is down to ~¾ after a regular customer —
a Corellian smuggler — broke port quarantine from their bay. Their permit was pulled for a
season, they had to repay their own bail at 25% interest, and the smuggler skipped on the
debt. (For CW, recast "quarantine" as a **cartel lockdown** or a customs hold; the
operator-with-a-grudge-and-a-bad-debt is a clean quest seed.)

### 4.4 Anatomy of a typical bay — 14 features (use as the POI interior template)
1. **Office** — scheduling transmitter to spaceport control; filing/coordination computers;
   all operating permits; the tractor-beam control terminal (see #12).
2. **Restroom** — public, functional, unlovely.
3. **Maintenance Garage** — servicing machinery; two binary load-lifters for cargo.
4. **Ship Supplies** — bulk consumables (oxygen, lubricant, basic proteins for food
   converters), metered out as part of the berth fee.
5. **Passenger Entrance** — stair to a **blast door, Strength 6D (character scale)**, usually
   left open while docked. The alley above is worked by beggars, shell-game grifters, and
   pickpockets — and occasionally a cartel or rival informant.
6. **Back-Blast Ceiling Vents** — softened old ion-engine discharge; defunct for ~70 years but
   kept clear by regulation.
7. **Sand Trap** — electrostatic repellors confining kicked-up sand to the pit.
8. **Fusion Generators** — three converters tied to a large fusion generator in the garage;
   used to recharge ships' power cells.
9. **Landing Lights** — eight, marking the landing circle for night landings.
10. **Docking Pit** — reinforced durasteel floor; lighter pourstone walls.
11. **Entrance Ramp** — powered cargo/non-ambulatory ramp reaching near pit center; exits to a
    wide service alley.
12. **Tractor Beams** — eight small dishes, **combined Strength 2D (starfighter scale)**, 100 m
    reach. Enough to *guide a willing ship* to berth, **not** to hold one against the pilot's
    will. Two are failing, so an operator must babysit the beam computer from the Office via
    video.
13. **Service Entrance** — an unused stairwell + blast door to the street.
14. **Customs Inspector's Office** — see §4.5.

### 4.5 Spaceport Customs
A customs office sits on the bays. **Era-translate:** drop the Imperial customs framing;
replace with a **cartel/port toll-and-inspection** post — perfunctory, bribeable, and
smuggling-permissive (which is the whole point of choosing Mos Eisley).

### 4.6 Vehicles for hire (a transport/rental hub)
A speeder shop (run by a local owner, with a gifted mechanic always tinkering in the back)
rents out ground and air transport: **air taxis (Bespin Motors Void-Spider), the Ikas-Adno
Starhawk, cargo skiffs**, and the like. (Manufacturer names like Bespin Motors / Ikas-Adno are
era-safe.) **Local color:** a small crew of hot-rodders races heavily modified speeders out of
town at "twilight," forever trying to beat their own escape-the-city time — good ambient flavor
and a low-stakes side activity.

---

## 5. The Cantina (social centerpiece)

The iconic **den of thieves, rogues, and brigands** — every species drinks here, deals get
done in the back, live music plays, and weapons are technically frowned on but openly worn.
Flavor anecdote worth keeping: a droid sent in for a part once came back out chased by a very
angry Gamorrean.

- **Owner:** a **Wookiee proprietor** (canon Chalmun → anonymize).
- **Bartender:** a **surly human bartender** (canon Wuher → anonymize).
- **Regulars:** a rotating cast of smugglers, bounty hunters, racers, and small-time hoods —
  use generic archetypes, not the book's named patrons.

For SW_MUSH this is the **primary social hub + informal jobs board** for the starting zone.
Era-safe as-is once ANH-specific patrons are dropped.

---

## 6. Establishments gazetteer (vendor/quest POIs)

Each entry: what it is, the keepable flavor, and the era/canon note. All names of canonical
people are replaced with archetypes.

- **Lup's General Store** (a.k.a. "Lup's Wares and Supplies") — general goods, run by a
  friendly-but-vengeful **Shistavanen ("wolfman") couple**. Touch-screen catalog stools (only
  6 of 15 work — one in black-and-white), a wall of specials monitors with failing sound, a
  back bathroom whose **sliding mirror hides where the illegal deals happen**, rear offices for
  private haggling, and a droid-run warehouse. Prices ~90–110% of list (120% for meds and
  weapons); stocks common gear, can order mid-tier, **no rare items**. A blaster carbine lives
  under the counter. → **Primary general-goods vendor.** Era-safe.
- **Jawa Traders** — a **Jawa-run droid and scrap dealership**: used (and dubious) droids,
  repairs, and "house calls" by sandcrawler. → Droid/parts vendor with a buyer-beware twist.
  Era-safe.
- **Lucky Despot Hotel** — a **grounded, gutted cargo hauler converted into a hotel/casino** by
  failed-tourism investors; now a seedy landmark run by a **Whiphid rival to the Hutt cartel**
  (canon Lady Valarian → anonymize). → Lodging + gambling POI and a second-faction power center.
  Iconic; keep the crashed-ship concept.
- **Zygian Banking Concern** — a struggling **branch of an offworld savings-and-loan** (HQ
  off-planet) that has slid into being a **pawn shop**, its vault cluttered with collateral from
  defaulted loans. → Banking/pawn/loan POI; pairs naturally with the **loan-shark debt mechanic
  already extracted from GG6**. Era-safe.
- **The Cutting Edge Clinic** — a back-alley clinic fronted by a **wanted black-market surgeon
  operating under an alias** (canon Dr. Evazan/"Cornelius" → anonymize). No-questions
  medicine and cybernetics. → Ties to the medical/death system (Guide 19). Era-safe as an
  archetype.
- **Dim-U Monastery** — an **urban splinter of a bantha-worshipping desert religion**. The
  wilderness branch sends out street preachers; the city house quietly offers aid and
  "enlightenment," opposes settlement expansion, and (usefully) **harbors a document forger**.
  → Flavor faction + forgery service hook. Era-safe.
- **Notsub Shipping Company** — **Tatooine's largest firm**, with the factory district to the
  north and its own private security (and a shadier underside). → Major economic anchor;
  cargo/mission source. Era-safe.
- **Wioslea's lot** — a **used-vehicle / landspeeder dealer**. → Vehicle vendor (buy/sell).
  Era-safe.
- **Gep's Grill / Dockside Cafe / Spaceport Express** — **dockside eateries** (daily specials,
  fast spaceport food). → Ambient food POIs near the bays. Era-safe.
- **Transport Depot** — local transit/logistics node. Era-safe.

---

## 7. How to use this in SW_MUSH (build hooks)

- **Docking bays as numbered POIs.** Model each bay (94, 27, 43, 67, 71, 86, …) on the §4.4
  template, fronted by an independent-operator NPC on the §4.3 pattern, wired to the §4.2 fee
  model. The seed bays for the relayout can reuse the De Maal archetype.
- **Navigate by landmark, not street grid.** The "no named streets — directions by business"
  principle (§2) is a direct fit for the POI/bearing substrate (the recent MAP_NAV / bearing /
  POI handoffs). Mos Eisley wayfinding should key off landmarks and establishments.
- **The Underground as a hidden layer.** §2.1 is a turnkey hidden-tunnel/smuggler network —
  web-client map overlay, illicit warehouses, contraband caches, unobserved ingress. Telnet
  shows a "requires web client" notice for the map view.
- **Establishments as the POI economy.** General store (vendor), cantina (social + jobs),
  clinic (medical/death), bank/pawn (loan-shark tie-in), shipping co. (cargo/missions),
  used-speeder lot (vehicle vendor), monastery (forgery/flavor faction).
- **Authority model.** The cartel-licenses-gangs structure (§3) replaces the Imperial garrison
  as the local security framing — feeds the security-zone / security-model layer for the
  starting city.
- **Two rival power centers.** The Hutt cartel vs. the Whiphid-run Lucky Despot gives the zone
  built-in faction friction without inventing anything.

---

## 8. Era-translation cheat-sheet

| GG7 element (ANH/GCW) | SW_MUSH handling (~20 BBY Clone Wars) |
|---|---|
| Imperial Prefect / planetary governor | Delete — no real civic government; the Hutt cartel is the de facto authority |
| Imperial customs / garrison / stormtroopers | Delete — cartel/port toll & inspection; local militia + private guards |
| Rebel Alliance presence/recruiters | Delete — off-era |
| "Quarantine of Mos Eisley" (droid hunt) | Recast as a cartel lockdown or customs hold |
| Jabba the Hutt (named) | Generic "Hutt cartel/kajidic"; off-screen only; `JABBA'S PALACE` location name already pinned |
| Chalmun (Wookiee cantina owner) | "the Wookiee proprietor" |
| Wuher (bartender) | "the surly bartender" |
| Garindan (Kubaz spy) | "a Kubaz informant for the cartel" |
| Momaw Nadon ("Hammerhead" Ithorian) | "an exiled Ithorian" |
| Dr. Evazan / "Dr. Cornelius" | "a wanted black-market surgeon" |
| Lady Valarian (Whiphid crime boss) | "a Whiphid rival to the cartel" |
| **"Mace Windu"** (obscure 1993 WEG NPC) | **Do not reuse this name** — hard collision with the Jedi Master; invent an original name |
| Docking-pit / ion-backblast lore, fees, bay anatomy, establishments, the Underground, social fabric | **Keep** — era-agnostic |

---

## 9. Prune note

With this extraction in hand, **`WEG40069.pdf` (Galaxy Guide 7: Mos Eisley, ~22 MB) can be
removed from the project** — it was the single largest file. This doc preserves the
build-relevant content (geography, docking, establishments, hooks) in era-translated,
canon-safe form. If you later need an exact map plate or art reference, the book is
re-obtainable; the design content you were actually using is captured here.
