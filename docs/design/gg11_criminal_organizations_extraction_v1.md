# SW_MUSH — Galaxy Guide 11: Criminal Organizations Extraction
## Version 1.0 — May 31, 2026 · Opus session
### Source: WEG40075 — Galaxy Guide 11: Criminal Organizations (Rick D. Stuart, West End Games, 1994, 94 pages, scanned/text-rendered)

---

## Table of Contents

1. Book Identity & Mining Assessment
2. Deliverable A: World Lore Entries (9 new) — era-translated for Clone Wars
3. Deliverable B: Criminal Organization Tiers → Faction/Org system (G10)
4. Deliverable C: Criminal Occupation NPC Stat-Block Templates
5. Deliverable D: Crime-Org Internal Role Taxonomy (the Karazak model)
6. Deliverable E: Haven World Templates → Security Zones (G04) lawless worlds
7. Deliverable F: Specialized Gear Catalog (Tools of the Trade) — D6 stats
8. Design Stub: Black Market Transaction Protocol + Violence Index
9. Era-Translation Notes — what carries, what doesn't, Q1 handling
10. Remaining Unmined Pages

---

## 1. Book Identity & Mining Assessment

**Source confirmed.** WEG40075, *Galaxy Guide 11: Criminal Organizations*, by Rick D. Stuart, West End Games, 1994. 94 pages. Image-based scan with an OCR text layer (legible but error-prone — stat blocks transcribed by eye against the rendered pages).

**Roadmap status.** Tier 1, sequencing item #1 ("Crime + place core") in `sourcebook_extraction_roadmap_v1.md` — the highest-ROI book on the list, rated *the backbone of an Outer Rim crime game*. It feeds four live systems: Factions/Orgs (G10), Security Zones (G04), Territory Control (G11), and Espionage (G22).

**Era note — this is the heaviest translation job to date.** GG11 is set ~6 years after *Return of the Jedi*, after *Dark Empire*. Its entire narrative frame — the death of Jabba, the Hutt-clan power scramble, Empire-vs-New-Republic war, the Imperial Civil War, Thrawn, the Battle of Calamari, Pinnacle Base — is post-ROTJ and off-era. **The frame is stripped; the skeleton is kept.** What survives translation is genuinely valuable and almost entirely era-agnostic:

- The **criminal-organization taxonomy** (territorial gang → crime guild → cartel → syndicate → criminal empire) — a clean five-tier scale model that maps directly onto our org/faction schema.
- The **criminal-occupation roster** (assassin, black marketeer, enforcer, slicer/data fixer, slaver, fence, corrupt official, counterfeiter, informant, loan shark, spice-jacker, smuggler) — a dozen era-portable NPC archetypes with full D6 stats.
- The **crime-org internal role structure** (the Karazak Slavers' five-role model: acquisitions → project developer → strike team leader → logistics → distribution) — a generalizable job taxonomy for *any* criminal org.
- The **haven-world templates** — five WEG-original lawless worlds, perfect security-zone "lawless" archetypes.
- The **Tools of the Trade catalog** (Ch. 6) — a dozen pieces of criminal gear with full D6 stats, nearly all era-agnostic.
- The **black-market transaction protocol** (the seven unwritten "market rules") — a ready interaction script for fences/espionage.

**Q1 canon-character policy.** Jabba Desilijic Tiure runs through Chapter Three. In our era (~20 BBY) the Desilijic clan is intact and dominant; per Q1, Jabba is **never instantiated as a named NPC** and is referenced only institutionally ("the Desilijic kajidic," "the dominant Hutt clan") with absence framing. Leia Organa, Han Solo, Talon Karrde, and Grand Admiral Thrawn are dropped outright. The Chapter Three "post-Jabba" crimelord roster (Kumac, Brasck, Jelasi, Llleag'Mak, Serimirl) is built entirely on Jabba's death and is **reduced to archetypes** (Hutt-clan lieutenant, mercenary enforcer-boss, legitimizing entrepreneur, spice-trade gangster, loyalist crime-boss) — see §C. The WEG-original NPCs from Chapters One/Two/Five (Brahle Logris, the haven-world bosses, the Karazak leadership, etc.) are **not** canonical figures and survive as named templates after frame-stripping.

**Pages mined for this v1:** Ch. 1 (pp. 8–28, criminal occupations + hierarchy); Ch. 2 (pp. 29–52, org-type exemplars + the Karazak role model + indentured servitude); Ch. 3 (pp. 53–63, Hutt kajidic methodology — archetype-only); Ch. 4 (pp. 64–70, the invisible market protocol); Ch. 5 (pp. 71–80, haven worlds); Ch. 6 (pp. 81–87, Tools of the Trade); Ch. 7 (pp. 88–94, law enforcement — partial, Sector Rangers only).

---

## 2. Deliverable A: World Lore Entries (9 New)

Ready to append to `SEED_ENTRIES` in `engine/world_lore.py`. All era-translated to ~20 BBY. **These deliberately avoid duplicating existing entries** — the codebase already has *Black Market*, *Loan Sharks*, *Smuggling*, *Hutt Cartel*, *Bounty Classifications*, and the BHG cluster (per the `clone_wars_era_design_v3.md` lore audit). Entries 6 and 3 below *extend* the existing *Black Market* and *Hutt Cartel* entries rather than restating them.

```python
# --- GG11 Criminal Organizations (WEG40075) — era-translated to ~20 BBY ---

{
    "title": "Criminal Organization Tiers",
    "keywords": "crime,gang,cartel,syndicate,guild,organization,turf,underworld,scale",
    "content": "Criminal groups come in five sizes, defined by scope. A TERRITORIAL GANG controls a few rackets in a finite area, usually one city or district (bookmaking, protection, extortion); most are urban and openly competitive, fighting turf wars over boundaries. A CRIME GUILD pools the talent of specialists across many systems toward one trade (slaving, smuggling), assigning members exclusive zones and buying off competition rather than holding ground. A CARTEL spans multiple systems and sectors to monopolize a single commodity or activity (spice, gunrunning), ruled by a central committee that uses monopoly profits to buy influence. A SYNDICATE is an alliance of cartels controlling ALL criminal activity in a region, often with members seated in local government. A CRIMINAL EMPIRE combines all of the above into one conspiracy; the Hutt kajidics are the archetype. The test is the group's aim: limited rackets in a finite area = gang; corner one market broadly = cartel; control everything broadly = syndicate.",
    "category": "faction",
    "priority": 6,
},
{
    "title": "Criminal Occupations",
    "keywords": "criminal,occupation,assassin,enforcer,fence,slicer,fixer,counterfeiter,informant,marketeer",
    "content": "The underworld runs on specialists. An ASSASSIN (called 'exterminator' on the Rim, 'problem solver' in the Corporate Sector) eliminates targets for hire. An ENFORCER is criminal muscle — back-alley thugs who keep the rabble in line through fear. A BLACK MARKETEER moves contraband through covert networks, respectable by day. A DEALMAKER (fence) buys stolen goods low and sells high behind a legitimate business front. A SLICER breaks unbreakable computer systems; a DATA FIXER blends slicing and forgery to insert falsified records and erase their tracks. A COUNTERFEITER mass-produces forged currency. An INFORMANT sells hard data for hard credits — the trick is selling the same information to multiple buyers without either learning of the other. A LOAN SHARK lends at 300-500% interest with violent collection. A SPICE-JACKER hijacks cargo, preferring smugglers (who can't go to the authorities) over company ships. Con artists and kidnappers exist too but are rarer.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "The Kajidic",
    "keywords": "kajidic,hutt,clan,desilijic,business,enterprise,crime,empire",
    "content": "Kajidic is a Huttese term meaning roughly 'the means by which we prosper' — it names any organized Hutt business venture, legal or illegal, and increasingly the individual clan crime empires themselves. Hutts are long-lived, patient, and grudge-keeping; they prefer to work behind the scenes as 'the galaxy's perfect middlemen,' financing a rising crimelord with credits, enforcers, and technical support in exchange for a cut that escalates over years until the partner is effectively enslaved by debt. The Hutt clans gained their homeworld Nal Hutta by trading technology to the native Evocii for land until three-quarters of the planet was theirs, then relocating the Evocii — a pattern repeated on many worlds since. A Hutt reveals only its first name to outsiders; the clan name (its cuirvas) is kept private. Clan competition is savage, but the clans share a belief in their own superiority and a doctrine that displays of wealth signal the power that keeps rivals at bay.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Indentured Servitude",
    "keywords": "indenture,servitude,labor,contract,hutt,debt,bondage,slavery",
    "content": "Distinct from outright slavery, indentured servitude is the Hutt clans' preferred labor system because it avoids the discipline problems and rebellions of slave labor. A person sells their services for a fixed term (typically six months to ten years) under a contract that has a credit value and can be bought and sold between Hutts and Hutt businesses. Hutt courts impose draconian sentences on debtors and 'agitators,' so many 'volunteer' for indenture rather than face the alternative. In theory, contracts forbid unsafe work and define fair treatment; in practice, a thicket of regulations lets contract-holders levy fines for infractions that extend the term indefinitely, and 'safety inspections' are conducted over dinner at the manager's estate. The indentured worker has no avenue of appeal. The system supplies cheap labor to mines and industries across Hutt Space and the Outer Rim.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Haven Worlds",
    "keywords": "haven,lawless,crime,planet,open,neutral,outer rim,fringe,sanctuary",
    "content": "A haven world is a planet where criminals can safely ply their trade — many acts that are crimes elsewhere are legal there, protected by the tacit support (or outright ownership) of the local government. Havens cluster in the Outer Rim, where they serve as outlets for illegal commerce, sources of contraband and gear, and neutral ground for deals. Some declare themselves 'open planets,' welcoming anyone who leaves their politics at the door; in wartime this neutrality is a survival strategy that lets a world dodge both sides' attention. The price is a leadership that courts criminal gangs with hard cash and no questions asked — and a population slowly remade in the underworld's image. A haven's underworld can supply equipment, information, and contacts unavailable anywhere else, if you live to collect.",
    "category": "location",
    "priority": 5,
},
{
    "title": "The Black Market Code",
    "keywords": "black market,deal,dealer,marketeer,rules,contraband,fence,buy,sell",
    "content": "Dealing the invisible market follows four steps — establish contact, strike a deal, take delivery, walk away in one piece — governed by seven unwritten rules. (1) Never give away too much too quickly, money OR information. (2) There is no such thing as a perfect deal; the art is getting most of the details in your favor. (3) Never pay credits up front. (4) Never appear to lose control of the situation. (5) Always have insurance — backup muscle, a contact in officialdom, or a clever escrow. (6) Never turn your back on the other party; they expect you to cheat them and may strike first in 'self-defense.' (7) Never make the other person feel they lost out — wounded pride brings retaliation. Dealers never come to a buyer; the buyer finds them, in any place people gather in numbers and law enforcement avoids. Best practice: never deal with the same operator twice in a row.",
    "category": "faction",
    "priority": 4,
},
{
    "title": "Spice",
    "keywords": "spice,glitterstim,ryll,kessel,ryloth,sevarcos,drug,contraband,smuggling",
    "content": "'Spice' is a catch-all slang term for substances used to artificially enhance — to 'spice up' — physical or mental attributes. There are many kinds: glitterstim from Kessel, ryll from Ryloth, Sevarcos spice, and others. Not all spice is addictive or even illegal; some is processed into legitimate pharmaceuticals by major corporations, while other batches are cooked in back-room labs. Whether a given substance is legal contraband varies from system to system by economic, political, and religious factors, so the same product may be sold openly in one place and be a capital offense in the next. Control of the spice trade is one of the most lucrative prizes in the underworld, and the trade can include legal as well as illegal goods.",
    "category": "trade",
    "priority": 5,
},
{
    "title": "Slaver Guilds",
    "keywords": "slaver,slavery,zygerian,thalassian,karazak,guild,kidnapping,captives",
    "content": "Organized slaving is concentrated in the Outer Rim, where restrictions are rarely enforced, and run by competing guilds. The ZYGERIANS are the best-known and harshest, disciplinarians with a slaving tradition stretching back generations. The THALASSIANS are the oldest, preferring to work within society, supplying contract labor to large corporations (often covertly) for new colonies. The KARAZAKS are the newest and most professional — they run slaving as a single-minded specialty with planned, low-risk operations and famously 'take care of their own,' bailing out captured members within a day and providing for the families of those killed. Many in the Republic publicly condemn slavery while quietly tolerating it; the Hutt clans keep personal slaves as prestige but consider mass slave labor economically impractical, preferring indentured servitude (which see). There is no such thing as an honest slaver.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Sector Rangers",
    "keywords": "sector ranger,law,enforcement,judicial,fugitive,extradition,jurisdiction",
    "content": "Sector Rangers are an interstellar law-enforcement corps created under the Old Republic, authorized by the Senate so regional governors could pursue criminals across the many newly colonized worlds. Where local police are bound to a single city or system, a Ranger can pursue a fugitive anywhere in their sector, demand extradition of prisoners, and escort captives between systems for trial. Rangers are reserved for the most dangerous and notorious criminals and are empowered to deputize civilian assistants and, in rare cases, suspend the authority of local officials suspected of aiding criminals. The best Rangers are promoted to Special Enforcement Officers, who can cross sector boundaries entirely in pursuit and who specialize in anti-trafficking, kidnapping recovery, and undercover infiltration of gangs.",
    "category": "faction",
    "priority": 5,
},
```

**Deployment:** Append to `SEED_ENTRIES` in `engine/world_lore.py`, then `@lore/reseed` (or clear/re-seed the `world_lore` table). These feed the Director digest and NPC brain context injection.

---

## 3. Deliverable B: Criminal Organization Tiers → Faction/Org System (G10)

GG11's five-tier taxonomy is the missing **scale** dimension for the org system. The existing schema (`organizations`, `faction_ranks`, `zone_influence` with `criminal` faction code, Hutt Cartel as the criminal faction) describes *one* large criminal org but has no vocabulary for the small gangs and mid-size cartels that should populate a crime game. This deliverable proposes a lightweight `scale` field and a canonical rank ladder.

### 3A. Organization Scale (proposed `scale` field on `organizations`)

| Scale | Scope | Zone-influence behavior | Example density |
|---|---|---|---|
| `gang` | One city/district | Contests a single zone's influence | Many per planet |
| `guild` | Cross-system, one trade | Doesn't contest territory; monopolizes a profession | A few per region |
| `cartel` | Multi-system, one commodity | Contests influence across a sector | One per major commodity |
| `syndicate` | Regional, all activities | Dominates a sector's `criminal` influence | One per region |
| `empire` | Galaxy-spanning | The Hutt kajidics; institutional, off-screen | The Desilijic clan (Q1: never an NPC) |

The Hutt Cartel faction (org code `hutt` → `criminal` zone-influence faction) is `scale: empire`. Player-foundable criminal orgs in lawless/contested zones (per `security_drop6_territory_control_design_v1.md`) start at `scale: gang` and can grow.

### 3B. Canonical criminal rank ladder

The existing Hutt Cartel ranks (Associate → Vigo, 6 tiers) are sound. GG11 supplies the *generic* gang/cartel ladder for non-Hutt player criminal orgs, drawn from the occupation and boss tiers in Chapters One–Two:

| Rank | Title | Notes |
|---|---|---|
| 0 | Runner | Errand-level; no permissions |
| 1 | Soldier | Rank-and-file enforcer/operator |
| 2 | Specialist | Occupation role (fixer, fence, marketeer) |
| 3 | Street Boss | Controls a district; leads henchmen (cf. Rodik Xern, §C) |
| 4 | Lieutenant | Multi-district / operation head |
| 5 | Underboss | Org admin; PC leader rank |
| 6 | Boss / Don | Org head (cf. Lady Sabrin, §C) |

### 3C. Organization Profile schema (the GG11 stat-card)

GG11's org-profile card is a clean data schema for any criminal faction. Recommend storing these as org metadata (JSON on `organizations`):

```yaml
# Organization profile card (from GG11 org exemplars)
type: cartel            # gang | guild | cartel | syndicate | empire
location: "<sector/system>"
leadership: "<boss name or governing committee>"
principal_activities: [spice, extortion, slaving, ...]
affiliations: [hutt_kajidic, smuggler_guild, ...]   # backers / allies
territory: "<systems controlled>"
payroll: 0              # estimated headcount (flavor / influence-cap input)
violence_index: 0       # 0-100, see §8 — drives territory contestability tone
```

---

## 4. Deliverable C: Criminal Occupation NPC Stat-Block Templates

WEG D6 templates from Chapter One's occupation profiles, era-translated. Use for spawning criminal NPCs at varying threat levels in cantinas, lawless zones, and Director events. Skill notation is `skill XD` over the listed attribute. **Era edits applied:** `forgery: Imperial credits` → `forgery: Republic credits`; all "Empire/New Republic" backstory framing stripped (capsules rewritten as era-neutral).

### 4A. Occupation archetypes (generic, for NPC generation)

| Template | DEX | KNO | MEC | PER | STR | TEC | Signature skills | Equipment |
|---|---|---|---|---|---|---|---|---|
| **Assassin** | 4D | 3D+2 | 2D+1 | 3D | 2D | 3D | blaster 5D, dodge 5D+1, sneak 7D, con 5D, biochemistry: exotic poisons 9D | poison vials, hypo injectors, blaster pistol (4D) |
| **Black Marketeer** *(Twi'lek)* | 3D | 4D | 2D | 3D+2 | 2D | 2D+1 | business: black market 8D+1, streetwise 6D, value 7D, bargain 6D+2 | hold-out blaster (3D+2), vibro-blade (STR+1D+2), datapad |
| **Enforcer** *(Gamorrean)* | 3D+1 | 2D | 1D+1 | 3D | 4D | 1D+1 | blaster 5D, melee combat 7D, intimidation: bullying 7D, brawling 7D, stamina 5D+1 | blaster pistol (4D), 2 throwing knives (STR+1D) |
| **Fence (Dealmaker)** *(Anomid)* | 1D | 1D+2 | 1D | 1D | 1D | 2D+1 | business: fencing 9D+2, streetwise 8D, value 8D, bargain 5D, con 5D+1 | blaster pistol (4D), breather mask, stolen goods |
| **Corrupt Official** *(Human)* | 3D+1 | 4D | 2D+2 | 3D | 2D | 3D | bureaucracy 6D, law enforcement 5D+2, command 4D+1, bargain 5D | blaster pistol (4D), comlink |
| **Counterfeiter** *(Sullustan)* | 2D+1 | 1D+2 | 2D | 3D | 1D+1 | 1D+2 | forgery 6D+2, forgery: Republic credits 10D+1, scholar: currency 7D+2 | tri-laser engraver, acid vials, phoney credits |
| **Informant** *(Mon Calamari)* | 3D+1 | 4D | 2D+1 | 3D | 2D | 3D+1 | streetwise 9D, bargain 7D, gambling 5D, persuasion 6D | datachips, recording rod, hold-out blaster (3D) |
| **Loan Shark** *(Devaronian)* | 1D+1 | 3D | 1D+1 | 3D | 2D | 1D+1 | business: loan sharking 10D, intimidation 8D, streetwise 8D | datapad, comlink |
| **Slicer / Data Fixer** *(Human)* | 2D+2 | 3D+1 | 4D | 2D | 2D | 4D | computer prog/repair 6D+2, security 5D+1, forgery 7D, communications 7D, sensors 6D | personalized computer, datapad, datachips |
| **Smuggler** *(Human)* | 3D | 3D+1 | 3D+2 | 3D+1 | 2D | 2D+2 | business: smuggling 9D, space transports 8D, starship gunnery 5D+1, bargain 6D, value 7D+2 | modified light freighter, blaster pistol (4D) |
| **Spice-Jacker** *(Nalroni)* | 3D | 3D+1 | 2D | 3D+2 | 3D | 3D | search 8D, computer prog: starship security 7D, security 7D, command: henchmen 5D+1 | heavy blaster pistol (5D), droid disabler, shipjacking kit, retina disguiser |
| **Slaver** *(Rodian)* | 3D | 3D | 2D+1 | 3D+1 | 4D+1 | 2D | business: slaving 9D, intimidation: torture 8D+1, command: slavers 6D, space transports 6D, brawling 5D+1 | slaver snare gun (2D stun + entangle), blaster pistol (4D), magnacuffs |

**Threat scaling:** the Enforcer, Spice-Jacker, and Slaver are combat-capable spawns; the Fence, Informant, Counterfeiter, and Corrupt Official are social/quest NPCs (low combat). The Slaver and Enforcer above carry **Dark Side Points** in the source (5 and 4 respectively) — appropriate for villain-tier NPCs.

### 4B. Crime-boss templates

| Template | DEX | KNO | MEC | PER | STR | TEC | Signature skills | CP / FP |
|---|---|---|---|---|---|---|---|---|
| **Gang Boss** *(cf. Lady Sabrin)* | 2D+1 | 4D | 2D | 2D+1 | 2D | 3D | command: henchmen 9D, bureaucracy 5D, streetwise 6D, blaster 4D+1 | CP 28 / FP 1 |
| **Street Boss** *(cf. Rodik Xern)* | 2D+1 | 3D+2 | 2D | 4D | 3D+1 | 2D+2 | command: henchmen 8D+1, streetwise 7D+2, intimidation 6D+2, con 6D | CP 20 / FP 1 |
| **Generic Enforcer (org soldier)** | 3D | 3D | 2D+1 | 3D | 3D | 2D+2 | blaster 5D, brawling 7D, intimidation: bullying 6D, dodge 4D | heavy blaster pistol (5D), vibro-blade, armored blast vest (+1D front) |

### 4C. Hutt-kajidic lieutenant archetypes (Q1: archetypes only — Chapter Three roster, frame-stripped)

Chapter Three's named crimelords exist only as heirs to Jabba's broken empire; that frame is off-era and discarded. What survives is five **reusable Hutt-clan lieutenant archetypes** for CW-era kajidic NPCs (the lieutenant who answers to an off-screen Hutt):

```yaml
hutt_lieutenant_archetypes:
  - key: clan_liaison          # cf. "Kumac" frame-stripped
    role: "Brokers favors between the kajidic and outside power-players; arranges 'special favors' and collects compensation."
    hooks: ["always travels with Gamorrean guards", "plays rivals against each other", "patient, never the first to move"]
  - key: merc_enforcer_boss    # cf. "Brasck"
    role: "Ex-mercenary turned kajidic hatchetman; runs slaving and smuggling muscle."
    hooks: ["taste for finer things", "remembers every slight", "watches the war for opportunity"]
  - key: legitimizing_broker   # cf. "Jelasi"
    role: "Advocates laundering crime into legitimate business; quietly eliminates those who won't go along."
    hooks: ["works within the system", "values banking over blasters", "low-key by design"]
  - key: spice_gangster        # cf. "Llleag'Mak"
    role: "Controls spice production and smuggling rings; rose by overthrowing each superior."
    hooks: ["never stays in one place", "reads others' greed and intent", "surrounds self with a personal guard"]
  - key: loyalist_boss         # cf. "Serimirl"
    role: "Fanatically loyal head of a kajidic front corporation; charming, seductive, deadly if crossed."
    hooks: ["origins a mystery", "runs private vendettas", "graceful under pressure"]
```

---

## 5. Deliverable D: Crime-Org Internal Role Taxonomy (the Karazak Model)

Chapter Two's Karazak Slavers' Cooperative is the book's best structural contribution: a **division-of-labor model** that any organized criminal operation can use. It's directly applicable to org-internal job assignments and to multi-stage Director quest generation (each role = a quest beat). Generalized away from slaving:

| Karazak role | Generalized function | Quest-beat use | Sample skills |
|---|---|---|---|
| **Acquisitions Specialist** | Scout / target assessor — works alone under cover, evaluates a target's value and the risk level | Recon / casing beat | investigation, value, command, cultures, business |
| **Project Developer** | Planner / go-no-go authority — owns mission success, approves or scrubs ops on cost-effectiveness | Planning / approval beat | investigation 10D, value, computer prog, business |
| **Strike Team Leader** | Operator lead — selects the team, runs the actual job, penalized for "damaged merchandise" | Execution / combat beat | blaster 8D, command: strike teams, survival, grenade |
| **Logistics Coordinator** | Quartermaster — outfits teams, handles captives/cargo, sets up and tears down bases | Supply / extraction beat | astrogation, all the repair skills, command, search |
| **Distribution Manager** | Fence-at-scale — finds the buyer on the right world at the right time, closes deals | Payoff / fence beat | bargain 7D, con, persuasion 7D, business: black market |

**Design value:** this is a turnkey schema for (a) populating an org's roster with *differentiated* NPC roles instead of generic "thugs," and (b) generating a five-beat heist/op quest where each beat is owned by one role. The Karazak's "specialization promotes internal competition; failures get a refresher course from the wrong end of the business" is good Director-flavor for org-internal tension.

---

## 6. Deliverable E: Haven World Templates → Security Zones (G04)

Chapter Five's five haven worlds are WEG-original (no canon-character entanglement) and map cleanly onto the **lawless-zone** tier of the security model (Guide_04) and the territory-control system. Era-translated: "open planet neutral between Empire and New Republic" → "neutral in the Clone Wars / pure Hutt-space haven"; the war frame is generic. These are world-design templates, not necessarily literal additions — pick what fits the map.

| Template | Archetype | Security profile | Hook |
|---|---|---|---|
| **Andasala** *(criminal-haven, mining)* | A war-battered world saved by a local crimelord who got himself elected provisional governor, declared it an "open planet," then invited the Hutts in. | Lawless; "organized crime" government; native gangs now at war with incoming Hutt operations | The whole planet is a power struggle the players can exploit — natives vs. Hutt newcomers, with the governor sitting back enjoying it |
| **Demesel** *(trade haven, anomalous)* | A peaceful backwater whose underworld is run by a single terrifying enforcer-boss; notably **Hutt-free** (the boss made his name killing Hutt agents). | Lawless by night, "business as usual" by day; ~1 in 4 officials bribed | A rare non-Hutt haven living on borrowed time; the Hutts want their renegade dead |
| **Tresidiss** *(gambling/tourism)* | An openly-criminal casino world run by a gambler-species syndicate; 4,000+ gambling halls, espionage hub, lowest tariffs in the galaxy. | Lawless but orderly; everything legal if the government gets its cut | Neutral ground where intelligence agents and crimelords make deals; the casinos are mostly rigged |
| **Bridin Anchorage** *(Mandroxan spice cartel seat)* | A heavily-shielded world that declared neutrality to survive the war, then became the open-defiance base of a spice cartel that operates in broad daylight. | Lawless; impervious to assault; "no questions asked" policy | A cartel capital that kills investigators rather than bribing them — high-violence, high-stakes |
| **Sabrixin system** *(territorial-gang mining colony)* | A three-planet system run by an ex-military gang boss mining radioactives with indentured labor, backed by Hutt credits, laundering profits, and slowly building a crude weapons program. | Lawless; provincial strong-arm gangs; "exit permits" required to leave | A company-town nightmare — debt-bondage mining, a paranoid boss, and a secret weapons project to expose |

**Integration note:** each maps to a `zone_environment` profile in the security schema and an org profile (§3C) for its ruling group. Andasala and Sabrixin are the richest quest-bearing templates; Tresidiss is the natural espionage/gambling hub (ties to Guide_22 and Guide_23).

---

## 7. Deliverable F: Specialized Gear Catalog (Tools of the Trade)

Chapter Six, full D6 stats, era-checked. Reference data for future schematics/vendors and for equipping criminal NPCs. **Era edits:** the "Modified E-11 Blaster Rifle" is built on an Imperial-era base (BlasTech E-11) — recast to a generic **modified blaster carbine + underbarrel slug-thrower** combo (the energy+slug concept that defeats reinforced structures is what matters; the clone-era base would be a DC-15-class carbine). The Teklos battle vehicle is built on the Nen-Carvon mobile command base; it's a commercial repulsorlift and era-flexible. Everything else is era-agnostic. Prices are credits; `bm` = black-market price.

### 7A. Weapons & restraints

| Item | Type | Skill | Damage | Range | Cost | Notes |
|---|---|---|---|---|---|---|
| **Slaver Snare Gun** *(Thalassian Corodex)* | Ranged restraint | missile weapons | 2D stun + entangle | 5-10/25/50 | 1,200 bm | Ammo 6. Filaments entangle (snare STR 3D, +1D/round, harden in seconds); opposed STR to break free; dissolving agent degrades them |
| **Modified Blaster Carbine + Slug-thrower** *(was E-11/S)* | Energy + projectile combo | blaster / firearms | 5D (energy), 4D (slug) | per base weapon | 7,000 | Ammo 25 (energy) / 6 (slug). Selector + timing-delay switch; energy burns through reinforced plate, slug follows — defeats armored building/vehicle structures. Outlawed in civilized space |
| **Mandroxan Droid Disabler** | Anti-droid | blaster | 6D stun, +1D per hit after first | 5-10/30/50 | 10,000 bm | Ammo 10. Phased particles cling to a droid's mass and build charge; hit droids take -1D to all rolls for 3 rounds or are knocked out; needs diagnostic + power-up to revive |
| **Plasticene Thermite Gel** *(Gatrellis)* | Pyrotechnic breaching charge | demolitions | 10D/round | — | 1,000/kg | Burns at 500°C; 0.5 kg = 3 rounds burn; defeats most locks and armored plating; difficulty scales with target hardness |

### 7B. Anti-security / infiltration

| Item | Function | Skill | Cost | Notes |
|---|---|---|---|---|
| **Fingerprint Masque** | Overlays a false fingerprint pattern (random or preset) for 10-12 hrs | computer prog/repair | 15,000 bm | Hard to fake a different species' prints |
| **Retinal Disguiser** | Visor projecting a false retinal pattern; can scan-and-store a live pattern | medicine | 25,000 bm | Hard to fake a different species' retina; preset patterns raise difficulty |
| **DimSim** | Holographic projector that hides the user's face behind a shield of darkness | — | 5,000 | Cap/helmet, 20-min powerpack; beats imaging systems that read faces under masks |
| **Sensor No-Show** | Wristband field generator vs. heat/IR tracking sensors | sneak | 5,000 bm | +2D sneak vs. heat/IR; 15-min cell; motion/vision sensors unaffected |
| **Shipjacking Kit** | Hand-held decoder that cracks a docked ship's security lock | security | 8,000 (licensed) / 16,000+ bm | +3D security to defeat a ship lock |

### 7C. Vehicles & equipment

| Item | Type | Skill | Cost | Notes |
|---|---|---|---|---|
| **Drogue** *(mod. Aratech WorkStar skiff)* | Cargo skiff (Speeder scale) | repulsorlift op: skiff | 1,000 | Cargo 350 kg; altitude to 200 m; whisper-quiet — the second-story-burglary platform |
| **Teklos Battle Vehicle** *(mod. Nen-Carvon command base)* | Mobile command base (Speeder scale) | repulsorlift op: Teklos | 45,000+ / 100,000+ bm | Crew 2 + 3 gunners + 7 pax; Body 7D; triple laser cannon (4D, turret) + 2 concussion grenade launchers (3D+1); the gangland war-wagon |
| **Tri-laser Engraver** *(Opirus KL-543)* | Counterfeiting tool | forgery | 4,000 / 8,000 bm | Replicates currency-plate incisions; long use without eyewear damages sight |
| **Gambling Droid** *(Droxian GDA-8)* | Gaming droid | gambling 6D | 10,000 | Holds 10,000 cr; 100-game library (expandable to 500); credit-transfer comlink; programs often rigged for the house |

---

## 8. Design Stub: Black Market Transaction Protocol + Violence Index

Two ready-to-design mechanics fall out of GG11. Neither is in scope to build here; both are noted for future feature work.

### 8A. Black Market Transaction Protocol (Espionage/Economy — G22/G06)

Chapter Four's four-step / seven-rule market script (captured in lore entry §A.6) is a ready **fence/contraband interaction loop**. The book even walks a worked example (the bounty hunter "Suroc" buying an attack beast) demonstrating escrow tricks (a codechip to an off-site safe with a palm+temperature lock) and double-cross tension. A future design could implement contraband purchase as a short negotiation mini-interaction at fence NPCs:

- **Contact:** locate a fence NPC in a lawless/contested zone (or via an informant lead).
- **Deal:** opposed bargain/con rolls set price; rule (2) — never a perfect deal.
- **Delivery:** the dangerous step — a chance of double-cross resolved by an opposed con/Perception check; "insurance" (backup, escrow) modifies risk per rule (5).
- **Walk away:** rule (7) — leaving the dealer feeling cheated risks a reprisal flag (later ambush).

This dovetails with the existing Black Market lore entry and the espionage system (Guide_22). Effort: medium; depends on a fence-NPC interaction framework.

### 8B. Violence Index → Territory Contestability (Territory — G11)

GG11 rates each org with a **Violence Index** (0-100): >70 = ruthless, little regard for life/property; <30 = low-key, force only to defend turf. This is a clean tone/behavior knob for the territory-control system (`security_drop6_territory_control_design_v1.md`): an org's violence index could drive how aggressively it contests claims, the Director's narration of turf disputes, and the likelihood of "range war" escalation vs. "surgical" hits. Store it on the org profile (§3C). Reference values from the book's exemplars: territorial gang ~58, crime guild (kidnapping ops) ~88, cartel ~88, syndicate ~94 — i.e. violence climbs with scale. Effort: small (a field + a few branch points in the territory/Director logic).

---

## 9. Era-Translation Notes — What Carries, What Doesn't

**Kept (era-agnostic skeleton):**
- The five-tier org taxonomy; the criminal-occupation roster + D6 stats; the Karazak role model; the black-market protocol; the haven-world templates; the entire Tools of the Trade catalog; the kajidic concept; indentured servitude; the Violence Index; the org-profile schema; **Sector Rangers + Special Enforcement Officers** (the book itself dates Rangers to the Old Republic — directly CW-compatible and a clean fill for the deprecated GCW law-enforcement lore).
- Era-correct species throughout (Twi'lek, Rodian, Gamorrean, Sullustan, Mon Calamari, Devaronian, Anomid, Verpine, Nalroni, Herglic, Defel, Brubb, Kian'thar) — all keepable NPC species.
- Spice taxonomy (glitterstim/Kessel, ryll/Ryloth, Sevarcos) — canon and era-agnostic; **ryll/Ryloth is strongly CW-relevant.**
- The Zygerian slavers — **elevated**, not just kept: the Zygerian slave empire is canon Clone Wars content. Thalassian/Karazak guilds are WEG-original keeps.
- Nar Shaddaa "Smugglers' Moon" — already in-game (Hutt Cartel HQ); strip the "avoid Imperial crackdown" framing.

**Recast:**
- "Empire / New Republic / Imperial Civil War / the war" → "Republic / Separatist Alliance (CIS) / the Clone Wars" (or generic "the war").
- "Imperial customs / New Republic trade officials" → "Republic customs / port authority / planetary trade officials."
- "Moff / Governor" (Moffs don't exist in CW) → "corrupt Senator / regional administrator / planetary governor."
- "IOCI (Imperial Office of Criminal Investigations)" → Republic Judicial Department / Judicial Forces (CW-canon law enforcement). "ISB / Imperial Intelligence" → Republic Intelligence / Senate Bureau of Intelligence (or drop).
- `forgery: Imperial credits` → `forgery: Republic credits`. The modified E-11 base → generic clone-era carbine + slug-thrower.
- Imperial Decree legalizing slavery → dropped; in CW the Republic outlaws slavery while the Hutts/Zygerians run it in the Outer Rim regardless.

**Dropped (off-era frame and Q1):**
- The entire post-ROTJ setting frame: Jabba's death, the Hutt-clan power scramble, *Dark Empire*, the Battle of Calamari, Pinnacle Base / Da Soocha, Coruscant's loss, the Thrawn material.
- **Q1 canon figures:** Jabba Desilijic Tiure (institutional reference only — "the Desilijic kajidic," absence framing; never an NPC), Leia Organa, Han Solo, Talon Karrde, Grand Admiral Thrawn.
- The Chapter Three "post-Jabba" crimelord roster as written → reduced to the five Hutt-lieutenant archetypes in §4C.
- NRSF (New Republic Security Force) → dropped (GCW institution; Sector Rangers carry the law-enforcement load instead).

---

## 10. Remaining Unmined Pages

- **Ch. 3 pp. 53–63 (Hutt methodology):** mined for the kajidic concept and the lieutenant archetypes only. The detailed Hutt divide-and-conquer / legitimacy / "generosity" strategies are good Director-flavor for how a Hutt kajidic expands; a future pass could lift these as Director playbook entries. Priority: low-medium.
- **Ch. 7 pp. 88–94 (The Opposition):** only Sector Rangers / SEOs extracted. The remaining law-enforcement tiers (planetary police, planetary prosecutors, citizen constabulary/militia, seeker droids, skip tracers) are mostly GCW-framed but several are era-portable as **NPC opposition templates** (skip tracer, seeker droid, planetary police). Worth a short follow-up if a law-enforcement-NPC drop is ever queued. Priority: low.
- **Chapter sidebar fiction (throughout):** rich tone pieces (the black-market dialogues, the haven-world vignettes); not extracted — usable as ambient/flavor inspiration only, not mechanics.

---

*End of Galaxy Guide 11: Criminal Organizations Extraction — Version 1.0*
*Source: WEG40075 (94 pages, scanned)*
*Deliverables: 9 world-lore entries; org-scale + rank + profile schema (G10); 15 criminal-occupation + boss stat-block templates; the Karazak role taxonomy; 5 haven-world templates (G04); 13-item gear catalog with D6 stats; 2 design stubs (black-market protocol G22/G06, violence index G11)*
*Era: translated to ~20 BBY Clone Wars; Q1 canon-character policy applied (Jabba institutional-only, no named canon NPCs)*
*Next: implement world-lore entries (reseed), then decide whether org `scale`/violence-index fields are worth a small G10/G11 schema drop*
