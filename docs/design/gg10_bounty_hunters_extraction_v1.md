# SW_MUSH — Galaxy Guide 10: Bounty Hunters Extraction
## Version 1.0 — April 14, 2026 · Opus Session 24
## Source: WEG40073 — Galaxy Guide 10: Bounty Hunters (127 pages, scanned JPEG)

---

## Table of Contents

1. Deliverable A: World Lore Entries (8 new)
2. Deliverable B: Bounty Board Enrichment
3. Deliverable C: NPC Stat Block Templates
4. Equipment Catalog (reference data for future schematics/vendors)
5. Design Stub: Capture & Restraint System (future feature)
6. Remaining Unmined Pages

---

## 1. Deliverable A: World Lore Entries (8 New)

These entries are ready to add to `SEED_ENTRIES` in `engine/world_lore.py` using the existing seeding pattern.

```python
# --- GG10 Bounty Hunters (WEG40073) ---

{
    "title": "The Bounty Hunter Creed",
    "keywords": "bounty,hunter,creed,acquisition,code,ethics,honor",
    "content": "Most bounty hunters adhere to an unwritten code of ethics called the Bounty Hunter Creed. Three rules define it. First: People Don't Have Bounties, Only Acquisitions Have Bounties — once a bounty is posted, the target loses their rights and becomes an 'acquisition.' Second: Capture By Design, Kill By Necessity — killing is business, but unnecessary killing is murder. Third: No Hunter Shall Slay Another Hunter — hunters consider themselves a special breed and never take up arms against a fellow hunter who follows the creed. Those who break the creed become acquisitions themselves.",
    "category": "faction",
    "priority": 6,
},
{
    "title": "Imperial Peace-Keeping Certificate",
    "keywords": "IPKC,license,bounty,hunter,permit,imperial,certificate,legal",
    "content": "An Imperial Peace-Keeping Certificate is the license required to operate as a bounty hunter in the Empire. It costs 500 credits and must be renewed annually. The IPKC entitles the holder to carry weapons that would otherwise be illegal and to transport captured individuals. It is valid in most regions, though some Core Worlds prohibit bounty hunting entirely. Imperial officials review the holder's record at each renewal — flagrant violations of Imperial law can result in revocation, though the Empire usually prefers token fines and stern warnings.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Imperial Enforcement DataCore",
    "keywords": "datacore,bounty,IOCI,database,posting,wanted,criminal",
    "content": "The Imperial Enforcement DataCore is a specialized database maintained by the Imperial Office of Criminal Investigations. It lists all legal bounties in the Empire — who is wanted, by whom, and for how much. Hunters access it at local Imperial offices or through posting agencies and guild houses. A datacard listing a specific bounty costs 10 credits. Searching boards on other planets costs 50 credits. Posting agencies charge 10 to 25 credits per day for DataCore access and maintain their own supplemental intelligence on targets.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Bounty Classifications",
    "keywords": "bounty,classification,most wanted,galactic,regional,sector,local,corporate",
    "content": "Imperial bounties fall under eight classifications. Most Wanted and Galactic postings appear on all DataCore boards across the Empire. Regional bounties cover multiple sectors. Sector, System, and Local bounties are progressively more limited in scope. Corporate bounties are posted by companies and are only legally binding within that company's territory. A separate 'Locate and Detain' list covers individuals the Empire wants alive for questioning — killing a Locate and Detain target can result in penalties up to and including execution of the hunter.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Bounty Hunter Guilds",
    "keywords": "guild,syndicate,house,benelex,paramexor,neuvalis,renliss,membership",
    "content": "Bounty hunter guilds — also called syndicates or houses — are privately established organizations that broker contracts between hunters and those posting bounties. Major guilds include House Benelex (kidnapping retrievals, Outer Rim), House Neuvalis (the largest, 6,790 hunters, bounties under 20,000 credits only), House Paramexor (murder contracts exclusively), and House Renliss (female hunters only, bounties on males). Guilds take a 'gap' of 3 to 10 percent from each bounty's face value. In return they provide equipment, repairs, training, intelligence, legal mediation, and sanctuary from Imperial officials.",
    "category": "faction",
    "priority": 5,
},
{
    "title": "Three Types of Bounty Hunters",
    "keywords": "imperial hunter,guild hunter,independent,bounty,category,type",
    "content": "Bounty hunters fall into three categories. Imperial hunters work exclusively for the Empire, taking only government-authorized bounties — they are often ex-military and receive equipment discounts and subsidized transport. Guild hunters operate through their syndicate, which assigns contracts and takes a percentage — they get equipment, training, and sanctuary but have no choice in assignments. Independent hunters work alone, taking any contract from any source — they keep everything they earn but bear all expenses and have no institutional support. Most hunters are independents, but most successful hunters belong to a guild.",
    "category": "faction",
    "priority": 4,
},
{
    "title": "The SEPI Principle",
    "keywords": "SEPI,selection,evaluation,preparation,implementation,hunt,method,bounty",
    "content": "Experienced bounty hunters follow the SEPI principle — Selection, Evaluation, Preparation, and Implementation. Selection means choosing the right target based on bounty value, danger, and the hunter's strengths. Evaluation means researching the target's habits, associates, hideouts, and capabilities. Preparation means acquiring permits, equipment, transportation, and local contacts before beginning the hunt. Implementation is the hunt itself. Hunters who skip steps — especially Evaluation and Preparation — tend to end up dead.",
    "category": "faction",
    "priority": 4,
},
{
    "title": "Bounty Posting Format",
    "keywords": "bounty,posting,wanted,format,alive,dead,originator,receiver,application",
    "content": "Official Imperial bounty postings follow a standard format: the target's name, species, sex, age, homeworld, and known associates; the bounty amount in credits; the classification (Galactic, Regional, Sector, etc.); application conditions (Alive, Dead or Alive, or Dead); any bonus for special conditions; determents or restrictions on methods; the crimes warranting the bounty; the originator who posted it; and the receiver to whom the acquisition must be delivered. A brief narrative describes the circumstances. Typical bounties range from 2,000 credits for minor sector violations to 25,000 or more for galactic-class fugitives.",
    "category": "faction",
    "priority": 4,
},
```

**Deployment:** Append to `SEED_ENTRIES` in `engine/world_lore.py`. Run `@lore/reseed` or clear/re-seed the `world_lore` table.

---

## 2. Deliverable B: Bounty Board Enrichment

The existing `engine/bounty_board.py` generates bounties for players to accept and complete. The GG10 data provides canonical structure to make these bounties richer and more varied.

### 2A. Bounty Classification Tiers

Add classification as a field to generated bounties. This determines scope, difficulty, and payout range:

| Classification | Scope | Typical Bounty Range | Difficulty |
|---|---|---|---|
| Local | Single city/settlement | 500–2,000 cr | Easy–Moderate |
| System | Single star system | 1,000–5,000 cr | Moderate |
| Sector | Multiple systems | 2,000–10,000 cr | Moderate–Difficult |
| Regional | Multiple sectors | 5,000–25,000 cr | Difficult |
| Galactic | Empire-wide | 10,000–50,000 cr | Very Difficult |
| Corporate | Company territory only | 1,000–15,000 cr | Varies |
| Most Wanted | Empire-wide, alive only | 25,000–100,000+ cr | Heroic |
| Locate & Detain | Empire-wide, alive mandatory | 10,000–50,000 cr | Difficult–Heroic |

### 2B. Application Conditions

Bounties should specify capture requirements that affect payout:

| Condition | Payout Modifier | Notes |
|---|---|---|
| Dead or Alive | 100% (dead), 100% (alive) | Standard, most common |
| Alive | 100% (alive), 0% (dead) | Target must be delivered alive — killing forfeits bounty |
| Alive (preferred) | 100% (alive), 50% (dead) | Alive preferred but dead accepted at reduced rate |
| Dead | 100% (dead only) | Rare — usually revenge postings |

### 2C. Bounty Posting Template for Director AI

When the Director AI or bounty board generates a new bounty, it should populate these fields:

```python
BOUNTY_TEMPLATE = {
    "target_name": "",        # Generated or pulled from NPC pool
    "species": "",            # From species list
    "homeworld": "",          # From location data
    "bounty_credits": 0,      # Based on classification tier
    "classification": "",     # local/system/sector/regional/galactic/corporate
    "condition": "",          # alive/dead_or_alive/alive_preferred/dead
    "bonus": "",              # Optional: "+2,000 for live capture within 30 days"
    "determent": "",          # Optional: "Half bounty if target sustains serious injury"
    "crimes": [],             # List of charges
    "originator": "",         # Who posted it: Imperial office, Moff, corporation, private
    "receiver": "",           # Where to deliver: "Any Imperial office", specific location
    "brief": "",              # 1-2 sentence narrative description
}
```

### 2D. Sample Bounties for Seeding

These are based directly on GG10 examples and can be added to bounty board generation pools:

```python
SAMPLE_BOUNTIES = [
    {
        "target_name": "Maxig Kress",
        "species": "Human",
        "homeworld": "Tibro",
        "bounty_credits": 25000,
        "classification": "regional",
        "condition": "alive",
        "bonus": "+5,000 for safe return of stolen crystalline compounds",
        "determent": "Half bounty if stolen materials not recovered",
        "crimes": ["Destruction of Corporate Property", "Theft", "Assault on Corporate Employees"],
        "originator": "Gandalom Paramedicinals, Inc.",
        "receiver": "GPI corporate headquarters, Corvanni IV",
        "brief": "Wanted for trespass on GPI property, destruction of security droids, and theft of experimental compounds. Armed and dangerous.",
    },
    {
        "target_name": "Ulicx Vinaq",
        "species": "Devaronian",
        "homeworld": "Devaron",
        "bounty_credits": 2000,
        "classification": "sector",
        "condition": "dead_or_alive",
        "bonus": "+500 live capture, +800 capture within 30 standard days. Hunter awarded salvage rights to target's vessel.",
        "determent": "",
        "crimes": ["Unlawful Possession of Illegal Weapon"],
        "originator": "Governor Desh, Gandrossi VI, Outer Rim",
        "receiver": "Any planetary government office on Gandrossi VI",
        "brief": "Merchant known to possess illegal energy weapons. Armed and dangerous. Hunter salvage rights awarded for confiscation of vessel.",
    },
    {
        "target_name": "Cherioer",
        "species": "Wookiee",
        "homeworld": "Kashyyyk",
        "bounty_credits": 25000,
        "classification": "galactic",
        "condition": "alive",
        "bonus": "+20,000 for information leading to arrest of confederates",
        "determent": "No serious injuries",
        "crimes": ["Flight to Avoid Prosecution", "Aggression Against Imperial Forces",
                   "Conspiracy", "Possession of Illegal Weapons", "Aiding Known Rebels",
                   "Destruction of Imperial Property", "High Treason"],
        "originator": "Moff Linis, Korev VII, Zaric Sector",
        "receiver": "Any Imperial law enforcement or military office",
        "brief": "Known ally of Wookiee Rebels. Has supplied food and medical assistance to Rebel Alliance members and personally assaulted Imperial military personnel.",
    },
]
```

### 2E. Permit Cost Structure (Economy Integration)

If/when the bounty hunter profession lane is formalized, these canonical costs create money sinks:

| Permit | Cost | Duration | Notes |
|---|---|---|---|
| IPKC License | 500 cr | Annual | Required to operate legally |
| Target Permit | ~100 cr | Per target, monthly | Varies 10–1,000 cr based on bounty value |
| Sector Permit | 1,000–10,000 cr | Monthly | Required in most sectors |
| System Permit | 50–500 cr | Monthly | Required in some systems |
| Capture Permit | 25% of bounty face value | After-the-fact | Retroactive permit when permits weren't obtained beforehand |

Guild members have most permits handled through their guild (included in the gap percentage).

---

## 3. Deliverable C: NPC Stat Block Templates

### 3A. Bounty Hunter Templates (for NPC generation / Director AI encounters)

These are canonical WEG templates from GG10 Ch. 2. Use for spawning hunter NPCs at varying threat levels.

| Template | DEX | KNO | MEC | PER | STR | TEC | Key Skills | Equipment |
|---|---|---|---|---|---|---|---|---|
| Imperial Hunter | 3D+1 | 3D | 4D | 3D+1 | 3D | 2D | blaster 5D, dodge 4D, investigation 5D+1, search 7D+1 | Blast helmet (+2 energy/phys), blaster carbine (5D), jet pack, knife (STR+1D), magnacuffs, medpac, stun grenades (5D stun) |
| Guild Hunter (combat) | 3D | 2D+2 | 3D | 3D+2 | 3D+1 | 2D+1 | blaster 6D+2, dodge 4D+2, grenade 3D+1, investigation 3D+2, search 3D+1 | Blaster pistol (4D), blaster rifle (5D), bounty hunter armor (+2D phys/+1D energy/-1D DEX), magnacuffs, medpac, syntherope |
| Guild Hunter (stealth) | 3D+1 | 2D+2 | 3D | 3D+2 | 2D+1 | 2D+1 | blaster 5D, dodge 5D, melee combat 5D, hide 5D+1, sneak 4D+2, con 6D, investigation 6D+1 | Hold-out blaster (3D+1), knife (STR+1D), stun cloak (5D stun), neural inhibitor pistol (3D+1/6D stun), datapad |
| Independent Hunter | 3D+2 | 2D+2 | 2D+1 | 3D | 3D+2 | 2D | blaster 7D, dodge 5D+2, brawling 5D, melee parry 5D, streetwise 5D, search 5D | Heavy blaster pistol (5D), vibroblade (STR+2D), blast vest (+1D phys), magnacuffs, syntherope, 500 credits |

### 3B. Named Hunter NPCs (for Director AI events, cantina encounters, rival spawns)

These are condensed from GG10 Ch. 6 notable hunter profiles. Each has a personality hook suitable for AI NPC dialogue generation.

```yaml
# Add to data/npcs_bounty_hunters.yaml or similar

bounty_hunter_npcs:

  - key: yarr_gatonne
    name: "Yarr Gatonne"
    species: Human
    type: "Obsessive Hunter"
    guild: Independent
    personality: "Calm and soft-spoken off the hunt, forceful and relentless on it. Collector of rare gems — will take extremely dangerous bounties if gems are involved."
    stats:
      dexterity: "4D+1"
      knowledge: "3D"
      mechanical: "4D"
      perception: "4D"
      strength: "4D"
      technical: "3D"
    key_skills: "blaster 5D+2, dodge 6D, melee combat 5D+2, streetwise 5D, bargain 5D, search 7D, sneak 5D, brawling 5D, stamina 6D"
    equipment: "Heavy blaster pistol (5D), light repeating blaster (6D), blaster rifle (5D), bounty hunter armor (+2D phys/+1D energy/-1D DEX), medpac, syntherope"
    credits: 500
    force_points: 3
    dark_side_points: 2

  - key: saras_krenin
    name: "Saras Krenin"
    species: Rodian
    type: "Guild Flamboyant Hunter"
    guild: "House Benelex"
    personality: "Enjoys the hunt as much as the credits. Throws elaborate announcement parties before each hunt to spook targets into revealing their location. Hunts Han Solo as a personal vendetta."
    stats:
      dexterity: "4D+2"
      knowledge: "2D+2"
      mechanical: "2D+2"
      perception: "3D"
      strength: "2D+2"
      technical: "2D+1"
    key_skills: "blaster 6D, dodge 6D, grenade 5D+1, thrown weapons: Rodian razorstick 7D, alien species 3D, cultures 3D, languages 3D+2, bargain 5D, con 6D, forgery 5D, gambling 7D, investigation 6D+1, search 5D, sneak 4D+2, brawling 5D, stamina 4D, computer programming/repair 5D, demolition 3D, security 3D+2"
    equipment: "Blaster pistol (4D), knife (STR+1D), hold-out blaster (3D+2), light repeating blaster (6D), magnacuffs, medpac, neural inhibitor (5D stun), syntherope"
    credits: 500

  - key: tyrn_jiton
    name: "Tyrn Jiton"
    species: Devaronian
    type: "Independent Stealth Hunter"
    guild: Independent
    personality: "Cruel and calculating. Uses stealth and ambush exclusively. Prides himself on 'one shot, one kill.' Hunts to fund a lifestyle of high-stakes gambling and carousing."
    stats:
      dexterity: "4D"
      knowledge: "3D"
      mechanical: "3D+2"
      perception: "3D"
      strength: "4D"
      technical: "2D+2"
    key_skills: "blaster 6D, bows 4D+1, dodge 5D+1, grenade 6D, melee combat 6D+2, melee parry 5D, alien species 4D, intimidation 7D+1, law enforcement 6D+1, streetwise 6D+1, survival 6D, willpower 5D, bargain 4D, con 5D, forgery 4D, gambling 4D+2, hide 6D, investigation 7D+2, search 7D, sneak 5D+2, brawling 5D, climbing/jumping 4D+2, stamina 6D+2, armor repair 4D, blaster repair 4D"
    equipment: "Modified sporting blaster rifle (4D+2), knife (STR+1D), magnetic binders, medpac, neural inhibitor (5D stun), modified speeder bike"
    credits: 1000

  - key: sabran
    name: "Sabran"
    species: Human
    type: "Guild Linguist Hunter"
    guild: "House Paramexor"
    personality: "Former navy communications officer framed for treason and sold to slavers. Rescued by House Paramexor. Fluent in 300+ languages. Uses underground contacts and cultural knowledge to locate targets, then closes with hand-to-hand combat. Striking appearance — uses charm as a weapon."
    stats:
      dexterity: "3D+1"
      knowledge: "2D+2"
      mechanical: "3D"
      perception: "3D+2"
      strength: "2D+1"
      technical: "2D+1"
    key_skills: "blaster 5D, dodge 5D, melee combat 5D, melee parry 5D, thrown weapons: balanced throwing knife 6D, alien species 3D, cultures 6D, languages 9D, streetwise 6D+1, bargain 4D, con 4D, investigation 5D, search 4D+1, sneak 4D, brawling 5D+1, stamina 4D"
    equipment: "Blaster pistol (4D), hold-out blaster (3D+2), knife (STR+1D), heat reflective armor (+1D energy/+2D phys/-1D DEX), Rodian razor-stick (STR+1D+2), magnacuffs, medpac, syntherope"
    credits: 500

  - key: galasett
    name: "Galasett"
    species: Kerestian
    type: "Independent Vigilante Hunter"
    guild: Independent
    personality: "Vigilante who hunts other hunters who have broken Imperial law. After his brother was murdered by hunters pursuing a mistaken bounty, Galasett decided to keep other hunters in line. Has been fined for excessive damage and briefly imprisoned for straying into a No Hunt Zone."
    stats:
      dexterity: "3D+2"
      knowledge: "2D+2"
      mechanical: "2D+1"
      perception: "3D+2"
      strength: "2D+2"
      technical: "2D+2"
    key_skills: "blaster 7D, dodge 5D+2, melee combat 4D, missile weapons 4D, alien species 5D+2, languages 4D+2, law enforcement 4D, streetwise 5D, bargain 4D, investigation 4D, search 7D+1, persuasion 5D+1, computer programming/repair 4D, security 5D"
    equipment: "Blaster pistol (4D), pulse rifle (5D-7D), electronet (1D-10D), comlink, datapad, medpac, magnetic binders, syntherope"
    credits: 500
    force_points: 1
    dark_side_points: 1

  - key: gradness_nall
    name: "Gradness Nall"
    species: Human
    type: "Salaktori Guild Hunter"
    guild: "Salaktori Hunter Guild"
    personality: "Third-generation guild hunter. Insufferably arrogant but genuinely skilled. Headstrong and overconfident. Has the potential to be one of the best — if his gloating doesn't get him killed first."
    stats:
      dexterity: "3D"
      knowledge: "2D+2"
      mechanical: "3D"
      perception: "3D"
      strength: "3D+1"
      technical: "3D"
    key_skills: "blaster 6D+2, dodge 4D+2, grenade 3D+1, alien species 3D, cultures 3D, survival 3D+2, bargain 3D+1, investigation 3D+2, search 3D+1, blaster repair 4D, computer programming/repair 4D, demolition 4D"
    equipment: "Blaster pistol (4D), heavy repeating blaster (8D), heat reflective armor (+1D energy/+2D phys/-1D DEX), magnacuffs, medpac, neural inhibitor (5D stun), stun cloak (5D stun), syntherope"
    credits: 500
```

---

## 4. Equipment Catalog (Reference Data)

This data is extracted from GG10 Chapter 7 for future use in schematics, vendor inventories, and the bounty hunter profession lane. **None of this requires implementation now** — it's reference material for when the capture system or new crafting schematics are built.

### 4A. Weapons

| Item | Cost | Damage | Skill | Range | Availability | Notes |
|---|---|---|---|---|---|---|
| ABC Scrambler | 3,000 cr (350 cr/pod) | 8D/5D/3D stun | Missile weapons | 50-200/350/500 | 2, R | Sensory disorientation device, area effect |
| Electronet | 2,000 cr/magazine | 1D-10D variable stun or normal | Missile weapons: grenade launcher | 10-250/350/500 | 2, F | Wire-guided, variable charge |
| Micro-Grenade Launcher | 2,500 cr (1,000 cr/magazine) | 4D/3D/2D frag | Missile weapons | 5-25/100/200 | 3, F | Computerized fire control, +1D to hit |
| Neural Inhibitor (rifle) | 5,000 cr (750 cr/ammo) | 3D+1 impact + 6D stun neurotoxin | Firearms: rail gun | 3-20/50/150 | 4, R or X | Victim must make Difficult stamina roll or unconscious |
| Neural Inhibitor (pistol) | 4,000 cr | 3D+1 impact + 6D stun neurotoxin | Firearms: rail gun | 3-10/25/50 | 4, R or X | Same neurotoxin effect as rifle |
| Pulse Rifle | 5,000 cr (200 cr power pack, 300 cr filaments) | 6D/5D/3D cone | Blaster: pulse rifle | 1-10/20/30 | 4, X | 60-degree cone of fire; overload at 7+ = 250cr repair; 11+ = 9D explosion |
| Prax "Blast and Smash" | 4,500 cr (250 cr ammo + grenade magazine) | 5D blaster / 4D-3D-2D grenades | Blaster / Missile weapons | 3-25/50/75 (blaster) | 3, F or R | Combo weapon: blaster rifle + micro-grenade launcher |
| Rocket Launcher | 1,500 cr (200 cr/clip, 15 cr/capsule) | 4D explosive / 5D stun (nerve gas) | Missile weapons | 3-30/100/300 | 3, F or R | Type-12A explosive or Type-12B nerve gas capsules |
| Stun Cloak | 1,500 cr | 5D stun | Melee combat | Contact | 2 | 3 charges, recharges from external power; melee parry to avoid |
| Wrist Lasers | 2,000 cr (100 cr power pack) | 4D | Blaster: wrist lasers | 0-2 (melee parry/brawling parry range) | 2, F | Overload mode: 8D/5D/3D with 1-2/4/6 blast radius, non-reversible |

### 4B. Armor

| Item | Cost | Protection | DEX Penalty | Availability | Special |
|---|---|---|---|---|---|
| Corellian HuntSuit | 2,900 cr | +2D phys, +1D energy | -1D DEX | 3, R | Sensor pod: +1D search within 50m, +1D lifting |
| Koromondain Half-Vest | 250 cr | +1D+2 phys, +2 energy (torso front/back) | None | 1 | Cheap basic protection |
| Cresh Luck Armor | 500 cr | +2D phys, +1D energy (torso front/back/legs) | None | 2 | Infrared motion sensor: alarm at 30m, +1D search |
| Corondexx Blast Vest | 3,000 cr (25 power cells) | +1D energy, +2 phys (torso only) | None | 2 | Ablative power cells, 10 min continuous, power jacks for recharge |
| Camo Armor | 1,500 cr | +1D phys, +2 energy | None | 2 | +1D difficulty to search/perception to spot wearer when motionless |
| Smasher Armor | 1,250 cr | +1D phys and energy | None | 3 | Servo enhancers: +2D to brawling, climbing/jumping, lifting, STR damage |
| A3AA Personal Defense Module | 8,500 cr | +2D phys, +1D energy | -1D DEX | 4, X | Disperses blaster bolts: reduces blaster damage by 2D at medium/long range. Imperial hunters only. |
| Reflect Body Glove | 4,000 cr | +1D STR vs medium/long range blasters | None | 3, X | Absorbs 5 blaster hits before destroyed. Destroyed if wearer is wounded. |
| Doubler Suit | 30,000 cr | None (not armor) | None | 4, X | Holographic projector: creates lifelike decoy up to 10m away. Very Difficult perception/search to detect at 50m+. |

### 4C. Confinement Apparatus

| Item | Cost | Breakout Difficulty | Availability | Notes |
|---|---|---|---|---|
| Magnacuffs | 75 cr | STR vs 6D+2 | 2, F | Fingerprint-locked magnetic restraints |
| Magnaharness | 200 cr | STR vs 8D | 2, F | Full-body magnetic restraint (arms, legs, torso, neck) |
| Force Cage | 7,000 cr | STR vs 7D | 3 | Portable collapsible containment, electric shock 1D-7D variable, 5 min assembly |
| Restraint Capsule | 10,700 cr | STR vs 7D | 3, F | Shipboard containment pod with force fields, minimal power drain |
| Man Trap | 8,000 cr | STR vs 5D-15D (variable) | 3, F | Reversed repulsorlift gravity plate, hidden, immobilizes targets on contact |
| Syntherope | 25 cr | STR vs 4D | 1 | Standard restraint material, included with most hunter loadouts |

### 4D. Miscellaneous

| Item | Cost | Notes |
|---|---|---|
| Armorer Droid (House Paramexor Squire) | Not for sale | TEC 3D, blaster repair 6D, weapons database, IMR repair module |
| HSS Thruster Pack | ~3,000 cr (estimated) | Enhanced jetpack with repulsorlift stabilizers and hover mode |

---

## 5. Design Stub: Capture & Restraint System (Future Feature)

### Problem Statement

The current bounty board system resolves bounty completion as a flag — the player accepts a bounty, goes to a location, wins combat, and gets paid. There is no mechanical distinction between "kill the target" and "capture the target alive." This makes bounty hunting indistinguishable from any other combat mission and renders the entire GG10 equipment catalog (confinement apparatus, stun weapons, alive/dead bounty conditions) meaningless.

### Required Mechanics (Minimum Viable)

**5A. Target States**

Add a `restrained` status to the NPC state machine, gated by the `incapacitated` or `stunned` combat outcomes:

```
Normal → Stunned → Incapacitated → [RESTRAIN action] → Restrained
                                  → [no action, timer] → Recovers to Wounded
```

A target that is incapacitated but not restrained will recover to `wounded` status after N rounds. The player must actively use a restraint item during the window.

**5B. Restraint Item Usage**

New command: `restrain <target>` (or `cuff <target>`, `bind <target>`)

Requirements:
- Target must be stunned or incapacitated
- Player must have a restraint item in inventory (magnacuffs, syntherope, force cage, etc.)
- System rolls target's STR vs the restraint item's breakout difficulty
- On success: target enters `restrained` state, restraint item is consumed/attached
- On failure: target is too strong for the restraint — need better equipment

**5C. Escape Checks**

Restrained NPCs attempt escape periodically (every N minutes of game time, or on room transitions during transport):
- Roll STR vs restraint breakout difficulty
- If successful: NPC breaks free, enters combat, flees, or calls for help
- Difficulty modifiers: wounded targets get penalties, multiple restraints stack

**5D. Transport**

Restrained NPCs follow the player between rooms (like a party member but involuntary). Environmental events during transport create gameplay:
- Rival hunters attempt to steal the acquisition
- Imperial patrols demand to see permits (Bureaucracy check)
- The target's associates attempt a rescue
- The target attempts to bribe the hunter (Willpower/con opposed check)

**5E. Delivery**

New interaction at bounty delivery locations (Imperial offices, guild houses, posting agency NPCs):
- `deliver <target>` or `turn in <target>`
- System checks: correct target, alive/dead matches bounty condition, permits in order
- Payout calculated: base bounty × condition modifier × bonus eligibility
- Alive targets that die during transport → condition drops to "dead" → reduced or zero payout

### Implementation Scope

This is a **medium-large feature** touching:
- `engine/combat.py` — stunned/incapacitated → restrained transition
- `engine/bounty_board.py` — alive/dead condition tracking, delivery resolution
- `parser/bounty_commands.py` — `restrain`, `deliver` commands
- `engine/items.py` or crafting — restraint items as usable equipment
- `engine/npc_combat_ai.py` — escape attempt behavior
- `data/schematics.yaml` — restraint item schematics (magnacuffs, syntherope, force cage)

Estimated effort: 3–5 Sonnet sessions once designed.

### Dependencies

- None on experimentation system — these are independent features
- Would benefit from the NPC crew/escort mechanics already stubbed in `npc_crew_and_traffic_design.md`
- Bounty board enrichment data (§2 above) should be integrated first so bounties have alive/dead conditions before the capture system enforces them

---

## 6. Remaining Unmined Pages (pp. 100–127)

The following content was not fully extracted and can be mined in a future session:

- **Pages 100–110**: Additional guild profiles (likely Salaktori Hunter Guild, House Tresario, and smaller guilds/posting agencies)
- **Pages 110–127**: Possibly the ESB bounty hunter stat blocks (Bossk, Dengar, IG-88, 4-LOM, Zuckuss, Boba Fett) — these would be high-value NPC templates but may also appear in other sourcebooks already in-project
- **Page 92 equipment**: HSS Thruster Pack full stats (partial read)

Priority for follow-up mining: **Medium**. The ESB hunter stat blocks are the most valuable remaining content. Guild profiles are useful for the organizations system but lower priority than the three deliverables above.

---

*End of Galaxy Guide 10: Bounty Hunters Extraction — Version 1.0*
*Source: WEG40073 (127 pages, scanned)*
*Deliverables: 8 world lore entries, bounty board enrichment data, 6 named NPC stat blocks, equipment catalog, capture system design stub*
*Next: Implement world lore entries (Drop 1), integrate bounty classification into bounty_board.py (Drop 2), add NPC templates to data files (Drop 3)*
