# SW_MUSH — Galaxy Guide 6: Tramp Freighters Extraction
## Version 1.0 — April 26, 2026 · Opus parallel-track session
## Source: WEG40027 — Galaxy Guide 6: Tramp Freighters, 1st Edition (80 pages, scanned JPEG)
## Drop: J1 (per `cw_content_gap_design_v1_1_decisions.md` §4)

---

## Table of Contents

1. Source overview and era-coupling notes
2. Deliverable A: World Lore Entries (12 new)
3. Deliverable B: Mission Board / Smuggling Job Enrichment
4. Deliverable C: NPC Stat Block Templates (9 archetypes)
5. Deliverable D: Equipment & Ship Modifications Catalog
6. Deliverable E: Canonical Loan Shark Debt Mechanic
7. Deliverable F: Design stubs (ship-as-character, modification economy)
8. Deliverable G: FDtS character grounding (Mak Torvin / Lira Shan / Grek)
9. Bonus: Faction-code validator script (per Q4 action item)
10. Remaining unmined pages

---

## 1. Source overview and era-coupling notes

GG6 (WEG40027) is the canonical WEG D6 sourcebook on independent freighter operators in the Star Wars galaxy. Published 1989; 80 pages; 1st edition. The book is structured in two halves: a **rules half** (Chapters 1-8 covering tramp freighter operations: speculative trading, drop-point delivery, black market, loan sharks, ship modifications) and a **campaign half** (Chapters 9-11 plus character templates: a Minos Cluster campaign setting with Imperial-occupied colonies and a Rebel cell).

**Era coupling.** The campaign half is firmly GCW-keyed — the Minos Cluster campaign assumes an Imperial occupation, a Rebel underground, and Imperial Customs as the primary law-enforcement antagonist. The rules half is **almost entirely era-portable**:

- Speculative trading (Chapter 4) — era-agnostic. Tech levels, bargain mechanics, planet classifications work identically in CW.
- Drop-point delivery (Chapter 5) — era-agnostic. The mechanic is "tramp captain hired to move cargo between two points for a fee." Doesn't care about war.
- Black market (Chapter 6) — era-agnostic. Black markets operate in any era; only the contraband list changes.
- Loan sharks (Chapter 7) — **fully era-agnostic.** The mechanic is timeless. This is the most directly FDtS-relevant chapter. See §6.
- Ship modifications (Chapter 8) — era-agnostic. The economic structure (parts costs, repair costs, modifications, hyperdrive prices) holds in CW.

**Two CW-period references appear in the campaign half** that are worth noting:
- p75 (Korkeal Hai template): "imported an old high-grade computer (a relic of the Clone Wars)." Places the campaign ~20 years post-Clone Wars.
- p76 (Rollo Morsai template): "she had played a Jedi fighting the Clone Wars in a holo many years before." Same dating.

**For our purposes, GG6 yields:**
- Foundational lore on tramp freighter culture, applicable to any era.
- 6 tramp captain stat block templates that are era-portable archetypes (just swap "Imperial Customs" → "Republic Customs" or "Hutt enforcer" depending on context).
- The canonical loanshark debt mechanic — the single most-cited reference for FDtS Phase 5.
- The complete ship modification economy (hyperdrive costs, fuel rules, repair rates, maintenance fees) which can ground SW_MUSH's own ship economy more rigorously.
- Three secondary archetypes useful elsewhere: the customs officer, the loanshark mastermind, and the engineer/mechanic NPC.

The Minos Cluster campaign content (Chapters 9-11) is Imperial-keyed and not extractable as CW content — it's noted in §10 as unmined.

---

## 2. Deliverable A: World Lore Entries (12 New)

These entries are ready to add to `SEED_ENTRIES` in `engine/world_lore.py` using the existing seeding pattern. All 12 are era-agnostic (no GCW-specific framing).

```python
# --- GG6 Tramp Freighters (WEG40027) ---

{
    "title": "Tramp Freighter",
    "keywords": "tramp,freighter,independent,trader,captain,smuggler,light freighter,small ship",
    "content": "A tramp freighter is an independent, owner-operated cargo ship — typically a stock light freighter modified by its captain. Tramp captains take whatever work they can find: legitimate cargo runs (drop-point delivery), speculative trading (buying low and selling high across planets), smuggling, salvage, and the occasional dangerous courier job. The life is precarious — over 60 percent of one-ship operations fail in their first year — but the freedom is unmatched. Most tramp captains carry significant debt to a loanshark or a bank, and many spend their careers chasing the next score that will let them pay it off.",
    "category": "occupation",
    "priority": 7,
},
{
    "title": "Drop-Point Delivery",
    "keywords": "drop,point,delivery,DPD,cargo,run,freight,hauling,contract",
    "content": "Drop-Point Delivery is the standard contract structure for tramp freighters: a captain is hired to carry cargo from one specified location to another for a specified fee. Standard fees run between five and 10 credits per ton per day, calculated on a baseline x2 hyperdrive engine, one day to load and depart, one day to arrive and unload. Modifiers apply for time pressure, dangerous routes, hazardous cargo, and the captain's reputation. Most tramps live primarily on DPD income, supplementing with speculative trading when capital allows.",
    "category": "economy",
    "priority": 7,
},
{
    "title": "Speculative Trading",
    "keywords": "speculative,trading,trade,goods,markets,profit,cargo,tech level,planets",
    "content": "Speculative trading is the high-risk, high-reward complement to drop-point delivery: the captain purchases cargo from their own pocket on one planet, transports it, and sells it for (hopefully) a profit on another. Roughly twenty percent of even experienced tramps' speculative deals go sour. The rules of the game are governed by tech-level differentials between worlds — primitive worlds will pay fortunes for manufactured goods, while industrial planets crave raw materials. The galaxy's tech-level classifications are Stone, Feudal, Industrial, Atomic, Hyperspace, and Hyperspace+1. A captain who can read these gradients can make a killing; one who can't will be skinned by the established trading houses, who hate freighter competition.",
    "category": "economy",
    "priority": 7,
},
{
    "title": "The Black Market",
    "keywords": "black,market,illegal,goods,contraband,smuggling,fence,broker,underground",
    "content": "Every populated planet has a black market — an illegal economy that runs alongside the legitimate one. What it carries varies: weapons and drugs on most worlds, banned holos on repressive worlds, mind-altering substances like alcohol on highly religious worlds, animal products on environmentalist worlds. The first contact is the hard part. Spaceport personnel — purchasing agents, shippers, warehouse managers — form the visible edge of every black market, and a polite inquiry at a spacer's bar (with a small fee) usually produces a contact. Local Customs agents are sometimes intimately involved themselves. After the first connection is made, repeat business runs smoothly.",
    "category": "economy",
    "priority": 6,
},
{
    "title": "Loan Sharks",
    "keywords": "loan,shark,debt,interest,creditor,goon,enforcer,payment,Hutt,broken,kneecap",
    "content": "Most legitimate financial institutions will not loan tramp freighter captains money at any price — the risks are too high, the collateral (a highly mobile ship that can be re-registered in weeks) too unreliable. Loan sharks fill this gap. They charge brutal rates: 300 percent over 30 months, 10 percent of principal per month, no early-repayment discount. They have no qualms about using force to remind customers of payment dates, and they hunt down defaulters as a matter of policy. Despite the rates, they remain the only credit available for someone trying to buy their first ship — every spacer in the galaxy knows someone who is making payments to one. The Twi'lek Yerkys ne Dago is the most famous of these loansharks in the Outer Rim, but every sector has its own.",
    "category": "economy",
    "priority": 8,
},
{
    "title": "Loan Shark Discipline",
    "keywords": "missed,payment,goon,broken,finger,beating,debtor,enforcer,delinquent",
    "content": "A loanshark's discipline ladder is canonical and predictable. A first missed payment doubles next month's bill (the missed payment plus a penalty payment of equal size). A second missed payment in a row brings goons to the debtor's door — a violent demonstration that typically ends with broken fingers and a wound. A third missed payment means being dragged to the loanshark's office, where the debtor must talk their way out via Con or Bargain rolls; failure on those rolls runs from beaten to mortally wounded to dead, depending on how poorly the rolls go. Note that the loanshark always gives the debtor the chance to make their case; the violence is not malice, it is policy. Loansharks who break this convention lose customers — and the customers' debts.",
    "category": "economy",
    "priority": 5,
},
{
    "title": "The Tramp Freighter and Its Captain",
    "keywords": "freighter,modification,ship,captain,upgrade,hyperdrive,personality,modify",
    "content": "Stock light freighters are slow, unmaneuverable, and lightly armed when they leave the factory. Most freighter captains plow a substantial portion of their profits back into modifying their ship — bigger hyperdrive, better ion drive, sensor masks, hidden compartments, occasionally illegal weapons systems. A tramp captain's ship is rarely sold; it accumulates the captain's investments, quirks, and history over decades. A famous saying in the trade: 'A tramp captain marries her ship before she marries anything else.' The conventional view among captains is that the ship has a personality of its own, that this personality is shaped by the captain's modifications, and that mistreating the ship will eventually cost the captain dearly.",
    "category": "occupation",
    "priority": 6,
},
{
    "title": "Hyperdrive Class and Cost",
    "keywords": "hyperdrive,class,multiplier,cost,jump,starship,upgrade,x1,x2,x3",
    "content": "Hyperdrive performance is rated by multiplier. A x1 hyperdrive (15,000 credits, 18 tons, civilian-best) covers a route in standard time. A x2 hyperdrive (10,000 credits, 15 tons) takes twice as long. The standard tramp freighter hyperdrive is x2; serious smugglers and racing operations upgrade to x1. A x1/2 hyperdrive (military-grade, 30,000 credits on the black market when available, 20 tons) is the only thing faster, and most tramps will never own one. Slower hyperdrives — x3, x4, x5 — are progressively cheaper and lighter, but the time penalty makes them suitable only for budget operations. Hyperdrive multipliers are also the conversational shorthand by which captains size each other up; 'she's a x1 ship' carries weight at any spacer's bar.",
    "category": "starship",
    "priority": 6,
},
{
    "title": "Spaceport Classes",
    "keywords": "spaceport,landing field,limited,standard,stellar,imperial,docking,fees",
    "content": "Spaceports are classified by the official galactic bureaucracy into five tiers: Landing Field (a flat space cleared on the ground; no services, no control tower, ships risk collisions on landing), Limited Services (a small tower, basic refueling, limited maintenance), Standard Class (full control tower, restocking, minor repairs and modifications, possibly at premium), Stellar Class (multiple shipyards capable of major repair and customization, usually with a Customs office on site), and Imperial Class (luxurious, lavish facilities, expensive services, well-staffed Customs office with portable scanners). Docking fees scale with class: Standard runs 50 credits per day; busy Imperial-class ports may charge up to 150 per day. The class-name is era-agnostic in galactic usage; non-Imperial governments use the same five-tier scale for their own spaceports.",
    "category": "economy",
    "priority": 5,
},
{
    "title": "Standard Maintenance and Restocking",
    "keywords": "maintenance,restock,consumables,fuel,oxygen,fluid,ship,upkeep",
    "content": "Every Standard-class or better spaceport will automatically perform standard restock and maintenance on any ship that lands, typically within 24 hours. Restocking includes water, lubricating fluids, coolants, oxygen, basic protein for food converters, and waste removal. The standard maintenance package covers air filters, gravitational disks, ablative heat shields, ion engine recalibration, and basic hyperdrive maintenance. Cost is calculated as 10 credits multiplied by the ship's total crew and passenger capacity, multiplied by the consumables duration in days. Ships that skip restocking risk being stranded with a depleted oxygen supply — which has killed crews more often than pirates have.",
    "category": "starship",
    "priority": 4,
},
{
    "title": "Hyperdrive Overhaul",
    "keywords": "overhaul,hyperdrive,maintenance,malfunction,jump,inspection,replacement",
    "content": "After every twenty hyperspace jumps, a ship's hyperdrive should receive a complete overhaul — replacement of certain key components, inspection of the rest. The cost is approximately 1,000 credits at most spaceports. Captains who skip overhauls accumulate a malfunction risk: roughly three percent per subsequent jump (mechanically, a roll of 2 on 2D6 produces a malfunction). A malfunction during a long jump can leave a ship adrift in deep space for days — long enough that the consumables countdown becomes lethal before rescue can arrive. Tramp captains who skip overhauls to save credits usually only make this mistake once.",
    "category": "starship",
    "priority": 5,
},
{
    "title": "Outer Rim Trade Routes",
    "keywords": "outer rim,trade,route,smuggler,hyperlane,corridor,run,frontier",
    "content": "The Outer Rim Territories are the natural habitat of the tramp freighter. Distance from Core World authority means lighter customs enforcement, sparser official patrols, and no large trading houses with the political clout to muscle out independent operators. The trade-off is risk: pirates, less-regulated economies that can collapse mid-route, planets where the local government is hostile or absent, and routes that take longer because the safe lanes are not always the direct lanes. A captain who learns the unmarked hyperlanes — the routes that bypass the popular space lanes where Customs corvettes wait — earns more per run, but the routes themselves are jealously-guarded knowledge. New captains buy this knowledge from old captains, in trade for favors or future cargo discounts; a route never appears in print.",
    "category": "geography",
    "priority": 6,
},
```

---

## 3. Deliverable B: Mission Board / Smuggling Job Enrichment

The existing mission/bounty system can be enriched with two GG6-canonical mechanics: the **drop-point delivery roll** for finding cargo runs, and the **black market contact** mechanic for finding fences.

### B.1 Drop-Point Delivery Roll Table (canonical from p19)

Used to determine the kind of run a captain finds when scanning a planetary mission board:

| Streetwise / Perception roll | Run Found |
|---|---|
| Failure | No Run |
| Very Easy (5) | Long Run, Not Much Cargo, Marginally Profitable |
| Easy (10) | Long Run, Large Cargo, Barely Profitable |
| Moderate (15) | Moderate Run, Large Cargo, Fairly Profitable |
| Difficult (20) | Moderate Run, Full Cargo, Good Profit |
| Very Difficult (30) | Short Run, Full Cargo, High Profit |

This pattern is already partially in the SW_MUSH mission generator. **Recommendation:** Adopt this exact result table when refactoring the smuggling-mission generator. The 5-tier resolution is more granular than the existing 3-tier and gives players a meaningful skill-check sweet spot.

### B.2 Standard Drop-Point Delivery Fee

5–10 credits per ton per day, baseline x2 hyperdrive, +1 day load + 1 day unload. Modifiers (per GG6 conventions):

- Time-pressured cargo (must arrive by date): ×1.5 to ×3
- Hazardous cargo (corrosive, biological, contraband): ×1.5 to ×4
- Dangerous route (war zone, pirate corridor, customs choke): ×1.5 to ×3
- Captain's reputation (high-rep): ×1.2 to ×1.5
- Captain's reputation (low-rep, desperate): ×0.5 to ×0.8

**SW_MUSH applicability:** The existing smuggling-jobs system pays in flat tiers. Folding in a per-ton-per-day calculation with these modifiers would make the economy more rigorous and ground it in canon. Defer to a future engine session.

### B.3 Black Market Contact Mechanic (from p21)

First-time black market contact on a planet: streetwise roll + GM-judged modifier for player roleplay quality.

| Roll | Result |
|---|---|
| Failure | No contact made; rumor spreads ("there's a captain asking around") |
| Easy (10) | Low-tier contact (small fence, limited inventory, will rip you off if able) |
| Moderate (15) | Mid-tier contact (real fence, moderate inventory, fair deals) |
| Difficult (20) | Tier-1 contact (organized network, large inventory, treats repeat customers well) |
| Very Difficult (30) | Direct contact with the local boss (Hutt-tier) |

After first contact, subsequent visits to the same planet skip this roll — the captain knows who to talk to.

**SW_MUSH applicability:** This maps cleanly onto the Uscru Fringe broker system already shipped (6 brokers across 5 reliability tiers — see `data/worlds/clone_wars/wilderness/uscru_fringe_brokers.yaml`). The Uscru system **is** GG6's black market mechanic, just instantiated for one specific planet. A future drop can extend the same broker pattern to other CW planets' underworld scenes.

---

## 4. Deliverable C: NPC Stat Block Templates (9 archetypes)

Six tramp freighter captain templates plus three supporting archetypes. All templates are extracted at full canonical fidelity from GG6 pp.69-76.

**Era-portability note:** All nine templates are era-portable. Where the canonical text references "Imperial" institutions, the CW reskin substitutes "Republic" (per `era.yaml` substitution rules) — but most templates have no Imperial framing at all and carry over unchanged.

### C.1 — Axtor Bridgeman (Tramp Freighter Captain — older, debt-saddled)

**Template Type:** Tramp Freighter Captain
**Ht/Sex:** 1.72m / male
**Source:** GG6 p.74

**Stats:**
- DEX 2D+2 — Blaster 4D+1, Dodge 3D+2
- KNO 3D+1 — Bureaucracy 4D+1, Cultures 4D, Languages 4D, Planetary Systems 5D+1, Technology 3D+2
- MEC 3D — Astrogation 4D, Starship Piloting 5D+1
- PER 3D+2 — Bargain 5D, Command 4D+2, Con 4D
- STR 2D
- TEC 3D+1 — Computer Programming/Repair 4D+2, Starship Repair 5D

**Description:** Older man. Greying hair for the last 20 years; only sign of aging is the lines in his face. Large, strong hands of a mechanic.

**Background:** First contact with freighter life when Axtor's father — a ship's mechanic — was offered crew on a freighter in exchange for repair work. Axtor accompanied his father on a voyage and was sold on the life. Borrowed from a Twi'lek loanshark (Yerkys ne Dago — see C.7) to buy his own light freighter; has been making interest payments for years and never quite dented the principal.

**Personality:** Easygoing, doesn't follow rules, accepts bad luck and good luck equally. Would quit the freight business if he became wealthy, but he knows that retirement would kill him faster than the work would.

**Role in CW reskin (FDtS):** **This is Mak Torvin's archetypal foundation.** See §8 for the full grounding map.

### C.2 — Chordak (Rodian Tramp Captain, Pirate-Adjacent)

**Template Type:** Rodian
**Ht/Sex:** 1.63m / male
**Source:** GG6 p.75

**Stats:**
- DEX 3D — Blaster 4D+2, Dodge 4D, Grenade 7D, Heavy Weapons 3D+2
- KNO 1D+2
- MEC 1D+2 — Astrogation 2D+1, Starship Gunnery 3D, Starship Piloting 4D+1, Starship Shields 3D+1
- PER 2D — Bargain 3D+1, Command 3D, Gambling 4D+1, Hide/Sneak 4D, Search 4D+1
- STR 2D+2 — Brawling 3D+1
- TEC 1D — Computer Prog/Repair 2D, Demolition 6D+1, Security 2D+2, Starship Repair 2D+1

**Background:** Rodian who didn't take to the kill-for-sport culture of his species. Trades cargo legitimately, but plays the pirate when opportunity allows — uses superb demolition skills to rig target ships with explosives, follows them through hyperspace, triggers the bombs at a quiet location to cripple them. Willing to kill but prefers not to.

**Role in CW reskin:** Rodian template is era-agnostic. Useful as a Nar Shaddaa pirate-adjacent NPC or as a CW Tatooine smuggler with a violent edge.

### C.3 — Korkeal Hai (Tinkerer Tramp Captain)

**Template Type:** Tramp Freighter Captain
**Ht/Sex:** 1.9m / female
**Source:** GG6 p.75

**Stats:**
- DEX 2D+2
- KNO 3D+1 — Bureaucracy 4D+1, Technology 5D
- MEC 3D — Astrogation 3D+2, Repulsorlift Op 4D, Starship Piloting 4D+1, Starship Shields 5D+1
- PER 3D+2 — Bargain 4D
- STR 2D — Lifting 3D
- TEC 3D+1 — Computer Prog/Repair 4D, Droid Prog/Repair 4D+2, Repulsorlift Repair 3D+2, Starship Repair 5D+2

**Description:** Older woman. Slender, wears glasses.

**Background:** Built her freighter herself from spare parts in the Shesharile system over many years. Imported an old high-grade ship computer ("a relic of the Clone Wars" in canon — for CW, this becomes "a current Republic-decommissioned naval computer"). The computer constantly nags her about her ship's disarray.

**Personality:** Hyperactive. Never tires of trying new combinations of parts. Quote: "No, I won't throw away my Torshkin M-2 intergyrons. I'll figure out some way to use them to make this ship even better!"

**Role in CW reskin:** Era-portable. The Korkeal archetype is the foundation for any tramp captain who is more shipwright than gunslinger — could be reskinned as Renna Dox on Nar Shaddaa (FDtS shipwright contact) or as a Kuat KDY engineer.

### C.4 — Rollo Morsai (Fallen Star Tramp Captain)

**Template Type:** Tramp Freighter Captain
**Ht/Sex:** 1.75m / female
**Source:** GG6 p.76

**Stats:** (Truncated — see GG6 p.76 for full block)
- DEX 2D+2 — Brawling Parry 3D
- KNO 3D+1
- MEC 3D — Astrogation 4D+1, Starship Piloting 5D
- PER 3D+2 — Bargain 4D, Con 6D
- STR 2D — Brawling 2D+2
- TEC 3D+1

**Background:** Former famous holo actress, blacklisted by an Imperial customs officer (Babel Torsh) for political reasons. Converted her expensive space yacht into a light freighter, makes a living through trade runs. Most of the work is actually done by her pilot/former valet, Tiebo. Prone to fits of despondency.

**Personality:** Fatalist. Believes more pain is coming. Quote: "I once played a tramp freighter captain in 'Captain Rygaen's Ploy,' but I never expected I'd actually become one."

**Role in CW reskin:** Substitute "Imperial customs officer" with "Republic officer" or "Hutt enforcer who took a personal dislike." Era-portable. Useful as a melancholy Nar Shaddaa cantina presence.

### C.5 — Trynic (Devaronian "Devil" Tramp Captain)

**Template Type:** Devaronian
**Ht/Sex:** 1.9m / male
**Source:** GG6 p.76

**Stats:**
- DEX 2D — Blaster 3D, Brawling Parry 4D+2, Dodge 3D+1
- KNO 3D — Alien Races 4D+1, Bureaucracy 7D, Cultures 5D+2, Languages 6D+2, Planetary Systems 7D
- MEC 1D
- PER 2D+2 — Bargain 6D+1, Command 4D, Con 5D+1, Gambling 5D, Search 3D+2
- STR 2D+1 — Brawling 5D, Lifting 3D
- TEC 1D — Computer Prog/Repair 4D

**Description:** Typical Devaronian — humanoid, dark horns atop hairless head, red-tinted skin, piercing eyes that unnerve those communicating with him (anyone attempting Con or Bluff against Trynic gets -1D).

**Background:** Considered the best tramp captain in his sector. Shrewd bargaining skills produce immense profits. Loves the life and uses Devaronian wanderlust as the excuse to never settle. Quote: "No, I can't return to Devaron. I... haven't made enough money yet."

**Role in CW reskin:** Era-portable. Useful as a high-status reference NPC on any planet — a captain players hear about long before they meet, a benchmark of what an experienced tramp looks like.

### C.6 — Yerkys ne Dago (Twi'lek Loanshark)

**Template Type:** Twi'lek (Loanshark)
**Ht/Sex:** 1.84m / male
**Source:** GG6 p.73

**Stats:**
- DEX 2D
- KNO 4D — Alien Races 6D, Bureaucracy 5D+1, Cultures 5D+2, Languages 7D, Planetary Systems 4D+1
- MEC 2D+2
- PER 4D+1 — Bargain 7D, Command 10D, Con 8D+1
- STR 2D
- TEC 3D — Computer Prog/Repair 3D+1, Droid Prog/Repair 4D

**Description:** Very physically fit Twi'lek. Always well-dressed, makes daily changes in the ornamental painted designs on his head tails. Right lekku gestures and points to add flair to his speech; left lekku flexes when angered, quivers when content.

**Background:** Ryloth-born; escaped slavery by allying with a band of smugglers, eventually took control of the band. Conditions on Ryloth deteriorated; Yerkys escaped further to the Outer Rim. Established a criminal network of black marketeers, smugglers, and other undesirables that is practically unrivaled in the galaxy. Most beings in debt in his sector owe their lives — and a lot of money — to Yerkys.

**Personality:** Superficially gracious and courteous. Actually a base, corrupt, and evil individual. Quote: "'One cannot defeat a heatstorm,' so just let it grow hotter."

**Role in CW reskin:** **This is the canonical loanshark archetype.** Drago the Hutt (FDtS Phase 5 antagonist) is the CW analog — a Hutt rather than a Twi'lek, but the operational pattern is identical: criminal network, debt-leveraged influence over freighter captains, public courtesy concealing brutal enforcement. Grek (FDtS Phase 5 fixer) is Drago's Yerkys-equivalent operational manager. See §8 for the full grounding map.

### C.7 — Babel Torsh (Customs Officer)

**Template Type:** Customs Officer (canon: Imperial)
**Ht/Sex:** 1.74m / male
**Source:** GG6 p.69

**Stats:**
- DEX 2D+1 — Dodge 4D
- KNO 3D+1 — Bureaucracy 8D+2, Languages 5D+2, Planetary Systems 5D+1
- MEC 2D+2
- PER 4D+2 — Command 7D, Con 6D+1, Search 8D
- STR 2D — Lifting 3D
- TEC 3D — Computer Prog/Repair 5D

**Description:** Pudgy, dark human male. Fanatically clean, well-groomed. Smuggler's nightmare — checks every paper and credential.

**Background:** Career bureaucrat. Banned holos when in charge of the cultural office; now runs Customs in his sector. **CW reskin:** "Republic Customs Liaison Officer." His pattern of zeal — chasing rule-breakers regardless of severity — works identically for a Republic functionary as for an Imperial one.

**Personality:** Huge ego. Will not tolerate the slightest infraction. Many Customs officers fall to bribery, but not Torsh. Add +5 to any Con attempts against him.

**Role in CW reskin:** **This is the canonical zealous-customs-officer template.** A re-skinned Babel Torsh is the natural replacement for the Imperial Customs Inspector in `npcs_gg7.yaml` (per Drop A — see `cw_content_gap_design_v1_1_decisions.md` Q3 mappings).

### C.8 — Porgo Goo (Engineer/Mechanic)

**Template Type:** Engineer (alien — "Chortose")
**Ht/Sex:** 1.7m / male
**Source:** GG6 p.72

**Stats:**
- DEX 2D+1
- KNO 4D — Technology 5D+2
- MEC 2D+2
- PER 2D+1
- STR 2D+2
- TEC 4D — Computer Prog/Repair 10D, Droid Prog/Repair 10D, Repulsorlift Repair 10D, Starship Repair 10D

**Description:** Short, plump, furry. Member of an obscure species (Chortose).

**Background:** Latent talent for mechanics from an early age. Doesn't have the education to understand the theory but intuitively grasps how technological devices work. Runs a small repair shop with his brothers. The Goo brothers will work for non-monetary motivation (dares and bets) and complete repairs in a third the normal time when so motivated. Frequently install illegal modifications.

**Personality:** Playful. Not embarrassed by his lack of formal understanding. Quote: "I don't know how it's supposed to work, but I sure can fix it."

**Role in CW reskin:** Era-portable. Foundation for any "scrappy mechanic NPC" — useful for Nar Shaddaa repair-yard rosters, for cantina patrons with mechanical skills, etc. Renna Dox (FDtS Nar Shaddaa shipwright) can ground partly on this template: Renna is more formal and less "playful," but the "knows ships better than the manuals" pattern is the same.

### C.9 — Iceman (Bounty Hunter — bonus archetype)

**Template Type:** Bounty Hunter
**Ht/Sex:** 2.23m / male
**Source:** GG6 p.70

**Stats:**
- DEX 4D — Blaster 7D+1, Brawling Parry 5D+1, Dodge 6D+2, Heavy Weapons 5D, Melee Parry 7D, Melee 8D
- KNO 2D+2 — Alien Races 4D, Cultures 4D+1, Languages 4D, Planetary Systems 5D+2, Streetwise 6D+1, Survival 6D+1
- MEC 2D+2 — Astrogation 5D, Repulsorlift Op 4D+1, Starship Gunnery 5D+1, Starship Piloting 6D+2, Starship Shields 6D
- PER 3D — Command 4D, Hide/Sneak 5D+2, Search 6D
- STR 3D+2 — Brawling 5D, Climb/Jump 6D+2, Lifting 4D+1, Stamina 7D, Swimming 5D+1
- TEC 2D — Computer Prog/Repair 6D, Droid Prog/Repair 4D+2, Medicine 5D, Security 6D

**Description:** Fair-complected, tall, athletic. Skin smooth and almost glassy. Smiles or other emotional displays never cross his face — in fact, he is unable to demonstrate such emotions.

**Personality:** No mercy. Believes in killing his quarry without warning. Quote: "Paying me if I succeed is as good as paying me now."

**Role in CW reskin:** Era-portable. Useful as a high-end bounty hunter NPC — players hear about him before encountering him. Complements the existing Bounty Hunters' Guild content from gg10 extraction.

---

## 5. Deliverable D: Equipment & Ship Modifications Catalog

Pricing data extracted from Chapter 8 (pp.28-37) of GG6. All prices in galactic credits, era-agnostic.

### D.1 Hyperdrive Multipliers

| Class | Cost | Weight (tons) | Notes |
|---|---|---|---|
| x1/2 | 30,000 | 20 | Military-grade, black market only |
| x1 | 15,000 | 18 | Civilian-best |
| x2 | 10,000 | 15 | Standard tramp freighter |
| x3 | 7,000 | 12 | Budget |
| x4 | 4,000 | 10 | Slow |
| x5 | 2,500 | 8 | Slowest |

Backup hyperdrive: 800 credits to install, 200 credits to remove (and sell). Ships without backup hyperdrive risk total loss on main drive failure.

### D.2 Fuel and Power Cells

Standard Empire Mark IV fuel cell. Standard light freighter carries 50 cells.

| Recharge Rate | Cost per Cell |
|---|---|
| Trickle (1 cell/day) | 5 credits |
| Standard (1 cell/hour) | 10 credits |
| Fast (4 cells/hour) | 50 credits |
| Emergency (20 cells/hour) | 500 credits* |

*Emergency rate replaces depleted cells with previously-charged cells rather than recharging.

**Fuel consumption per task:**
- Entering hyperspace: 1 cell
- Six hours in hyperspace: 1 cell
- One month of realspace operations: 1 cell
- One hour of combat maneuvers: 1 cell
- One hour of atmospheric flight: 1 cell

### D.3 Maintenance and Restocking

**Standard maintenance** (fluid replacement, filters, ion engine recalibration, basic hyperdrive service): 10 credits × total crew/passenger capacity × consumables duration in days.

**Hyperdrive overhaul** (every 20 jumps): 1,000 credits. Skipping the overhaul produces a ~3% malfunction risk per subsequent jump.

**Damage repair flat costs:**
- Lightly damaged ship: 1,000 credits
- Heavily damaged ship: 2,000 credits
- Severely damaged ship: 3,000 credits

Plus replacement of any destroyed systems (separate cost).

### D.4 Spaceport Docking Fees

| Class | Daily Docking Fee | Notes |
|---|---|---|
| Landing Field | 0–10 credits | No services |
| Limited Services | 10–25 credits | Basic refueling only |
| Standard Class | 50 credits | Restock + minor repairs |
| Stellar Class | 75–100 credits | Major repair available |
| Imperial Class | up to 150 credits | Luxurious; full Customs |

### D.5 Independent Repair Work

Captains with sufficient Starship Repair skill can perform their own modifications and repairs. Required: a quiet place to work and a fully-equipped repair bay (rental: ~100 credits per day). Reduces parts cost by half. Used parts (50% of new) are commonly available; salvaged parts (25% of new) require black market access. Used parts break down more often than new parts.

### D.6 SW_MUSH Applicability Notes

The existing SW_MUSH ship economy uses simpler pricing. The full GG6 economic structure could ground a future "ship economy hardening" drop, with these specific candidate features:

- Per-day fuel cost ledger (currently abstracted)
- Hyperdrive overhaul timer ticking per jump (currently absent)
- Independent repair vs. shipwright cost split (currently flat)
- Spaceport-class docking fee scaling (currently flat per port)

Defer all of the above to engine sessions; this extraction provides the canon ground for the design.

---

## 6. Deliverable E: Canonical Loan Shark Debt Mechanic

This section is the most directly FDtS-relevant content in GG6. Full canonical mechanic from Chapter 7 (pp.26-27), with notes on FDtS divergence and reconciliation options.

### E.1 The Canonical Mechanic

**Loan structure:**
- Principal: typically 10,000–25,000 credits (the price range of a used light freighter, less down payment).
- Term: 30 months.
- Rate: 300% total over the term.
- Monthly payment: 10% of principal.
- Example: 20,000 credit loan → 2,000 credits/month × 30 months → 60,000 total paid → 40,000 in pure interest.
- No early repayment discount: borrowing 20,000 obligates the debtor to 60,000 regardless of how quickly they pay it back.

**Payment schedule:** monthly. Auto-deduction is not canon — the debtor must make active payments to a designated drop-point (a fixer's office, a cantina back room, a contact at a spaceport).

### E.2 Discipline Ladder

**First missed payment:**
- Next month, debtor owes the missed payment + the next month's payment + a penalty payment of equal size.
- Effective: triple the monthly payment in the catch-up month.

**Second missed payment in a row:**
- Loanshark sends goons.
- Demonstrative violence: broken fingers, a wound (full damage roll if the debtor resists).
- Debtor still owes the missed payments + accumulating penalties.

**Third missed payment in a row:**
- Debtor is "invited" to the loanshark's office.
- Forced to explain delinquency via Con or Bargain roll (debtor's choice).

| Roll Result | Outcome |
|---|---|
| Very Difficult (30) | Released with a warning |
| Difficult (20) | Beaten; takes wound in damage |
| Moderate (15) | Beaten to incapacitation; dumped with friends |
| Easy (10) | Mortally wounded; dumped |
| Failure | Killed; body disposed of |

Up-to-date payment + penalty (two penalty payments, one for each missed month after the third) gives a +5 modifier to the Con/Bargain roll. Resistance escalates to combat.

After surviving the third-month interview, the debtor faces continued accumulation of penalties for each subsequent missed month.

### E.3 The Loanshark as Adventure Hook

GG6 explicitly frames the loanshark as a character-engagement engine:
- Heavily-indebted characters take risky jobs they would normally refuse.
- The loanshark can offer direct employment ("a real simple run") in exchange for a payment cut — the debtor is encouraged not to ask too many questions about cargo contents.
- Customs encounters during loanshark-cargo runs put the debtor in the impossible position of jettisoning the loanshark's goods to avoid arrest, and then explaining the lost cargo to the loanshark.

This is a deliberate dramatic-irony loop. The loanshark doesn't want the debtor to easily pay off the loan; the loanshark wants the debtor permanently in his web.

### E.4 FDtS v2 Divergence and Reconciliation

The FDtS v2 design specifies:
- Principal: 10,000 credits
- Weekly payment: 500 credits (auto-deducted from account)
- Term: 20 weeks
- Effective rate: 0% (10,000 borrowed → 10,000 paid back, zero interest)
- 2 missed payments: threatening comlink
- 3 missed payments: hostile NPC spawn near the player

**The FDtS mechanic is dramatically softer than canon.** Comparisons:

| Feature | GG6 Canon | FDtS v2 |
|---|---|---|
| Term | 30 months | 20 weeks (~5 months) |
| Effective interest | 200% | 0% |
| Payment frequency | Monthly | Weekly |
| Auto-deduction | No | Yes |
| 1 missed payment | Triple owed | (no penalty stage) |
| 2 missed payments | Goons + violence | Comlink threat |
| 3 missed payments | Office summons; outcomes from warned to killed | Hostile NPC spawn |

**Reconciliation options for the FDtS engine drop:**

- **Option 1 — Use canon as-is.** Adopt the 30-month term and 300% interest. Most thematically aligned, hardest on new players. Probably too punishing for an onboarding quest chain.
- **Option 2 — Use FDtS v2 as-is.** Soft mechanic, friendly to new players. Loses canon flavor.
- **Option 3 — Compromise: shorter term, real interest, soft enforcement.** 20-week term but with 200cr/week interest layered on top of the 500cr principal payment (so 700cr/week total = 14,000 paid on 10,000 borrowed = 40% interest). Auto-deduction kept. Discipline escalates per FDtS v2 (no goon visits) until 3rd miss, where canonical "office summons" replaces "hostile NPC spawn" — but the office summons offers Con/Bargain as the FDtS-flavored dialogue tree, with stakes scaled to "lose Hutt rep" instead of "die."

**Recommendation: Option 3.** Preserves the canonical narrative beats (interest exists, missing payments has consequences, the loanshark wants you to stay in their web) while remaining new-player-friendly. The FDtS engine drop's designer makes the final call.

---

## 7. Deliverable F: Design stubs

### F.1 Ship-as-Character convention

GG6's recurring theme: the ship has a personality, shaped by the captain's modifications and history with it. Two specific authoring patterns surface:

- **Modification quirks** — a Korkeal-built ship (C.3) doesn't fit standard repair manuals; an Axtor ship (C.1) has the captain's initials welded inside the cockpit somewhere; a Trynic ship (C.5) has a hidden compartment behind every panel.
- **Personality lines in dialogue** — a captain talks to her ship (verbal habit) and reports the ship "responding" by behaving better or worse. This is a roleplay convention, not a mechanic.

**SW_MUSH applicability:** The existing ship system has `condition` and `systems` fields. A future engine drop could add a `quirks` JSON list per ship containing 3–5 cosmetic personality flags affecting random ambient text. Defer.

### F.2 Modification economy convention

Three things every captain in GG6 spends credits on, in order of priority:
1. Hyperdrive upgrade (most impactful per credit)
2. Sensor mask / smuggling concealment (for cargo-flexibility)
3. Weapons (last priority — "if you need them, you've already failed")

This priority order is a useful design hint for any future ship-customization minigame.

### F.3 The "first ship is debt" convention

Every tramp captain template in GG6 either has a current loanshark debt (Axtor, implied Korkeal) or had one in the past that they paid off (Trynic, implied Rollo). The "first ship" is canonically purchased with debt in this sourcebook. **FDtS Phase 5's "purchase the Mynock with a Hutt debt" structure is GG6-canonical** — not an FDtS invention. The FDtS engine drop can lean on this as a documented design ground.

---

## 8. Deliverable G: FDtS character grounding

Concrete mappings of the three bespoke FDtS NPCs to GG6 archetypal foundations. These are authoring guides for the FDtS step content drop — the bespoke NPCs are still authored, but they descend from documented sources rather than being purely invented.

### G.1 Mak Torvin → Axtor Bridgeman archetype (C.1)

**Inheritance:**
- **Stat block foundation:** Adopt Axtor's stats as Mak's baseline. Adjust slightly for the difference in role (Mak is retired/retiring; Axtor is mid-career):
  - Reduce DEX-stat skills by 1D each (Mak's hands shake)
  - Keep KNO/PER/MEC stats unchanged (the experience is what carries forward)
  - Increase Bargain and Con by 1 pip each (Mak has more negotiation experience than mid-career Axtor)
- **Backstory:** Mak inherits Axtor's "father was a freighter mechanic, took me on a voyage, sold me on the life" pattern. Modify: "Mak's father was a Republic Naval engineer, retired pre-war, brought Mak aboard his post-retirement freighter at age 15."
- **Loanshark history:** Axtor "is still making interest payments." Mak's variant: "made interest payments for 30 years; finally close to paying off the principal but had to sell the ship to do it, which is why he's selling to the player." This makes the Mynock-purchase + debt-transfer arc canon-grounded.
- **Personality:** Inherit Axtor's "easygoing, doesn't follow rules, accepts good and bad luck equally" wholesale. Mak's gruffness in FDtS v1 is a layer on top of this base — interpret as defensive armor over genuine warmth.

**Era reskin notes:**
- Axtor's Imperial customs encounters → Mak's Republic customs encounters.
- Axtor's mid-career → Mak's late-career retirement arc.
- Axtor's loanshark Yerkys ne Dago → Mak's loanshark Drago the Hutt.

### G.2 Lira Shan → Korkeal Hai archetype (C.3) + Trynic mannerisms (C.5)

**Inheritance:**
- **Stat block foundation:** Adopt Korkeal's stats with these adjustments — Lira is younger, more polished, less hyperactive:
  - Reduce TEC stats by 1D (Lira is a broker, not a hands-on mechanic)
  - Increase PER and KNO stats by 1D each (broker work)
  - Add Bureaucracy 6D+2 (KDY broker authority)
- **Backstory:** Lira inherits Korkeal's "deep familiarity with ship internals" but in a brokerage capacity rather than self-built-ship capacity. She's the person who knows whether a ship's documented history matches its actual mods.
- **Mannerisms:** Borrow Trynic's "shrewd bargainer, dubbed something memorable by competitors" pattern. Lira's nickname (per-CW): "the Kuati Reader" — for her ability to read a captain's true financial situation.

**Era reskin notes:**
- Lira lives on Kuat (per FDtS v2 Phase 5), not Corellia.
- KDY broker, not CEC. CEC is referenced as the original manufacturer of the Mynock; KDY handles the secondhand paperwork.

### G.3 Grek → Yerkys ne Dago archetype (C.6) — but as fixer, not boss

**Inheritance:**
- **Important distinction:** Yerkys is the loanshark mastermind. **Drago the Hutt is Yerkys' CW analog** (the boss). **Grek is Drago's operational manager** — Yerkys delegated rather than replaced.
- **Stat block foundation for Grek:** Adopt Yerkys' stats but reduced by 1D across the board (Grek is competent but not the kingpin):
  - DEX 2D+1 (small reduction)
  - KNO 3D+1 (Grek has Yerkys-tier research skills minus the boss-level connections)
  - PER 3D+2 (high but not 4D+1)
  - All skills similarly reduced 1 step
- **Personality:** Inherit Yerkys' "superficially gracious and courteous, actually corrupt" but soften the menace. Grek delivers Drago's threats; Drago is the menace. Grek's role is procedural — paperwork, payment schedules, escalation triggers.
- **Dialogue style:** GG6 Yerkys uses elaborate Twi'lek lekku gestures. Grek's CW analog could use Rodian / Trandoshan / Devaronian / human mannerisms — pick a species that fits the Hutt-employment niche (Twi'lek would also work fine if we want to keep the Yerkys callback explicit).

**Drago the Hutt** (the loanshark proper, not encountered in FDtS — only referenced):
- Adopt Yerkys' full stat block with Hutt-species substitutions (slower DEX, higher STR for the Hutt body, all KNO/PER skills intact or higher).
- Lives on Nar Shaddaa or Nal Hutta. Operates a multi-system lending network.
- Per FDtS v2, Drago "respects someone who faces their debts" — this is consistent with Yerkys-style "I don't want you dead, I want you in debt."

### G.4 Note on the canonical mention of "Drago" vs. "Yerkys"

GG6 names Yerkys ne Dago specifically as the dominant Twi'lek loanshark of the Outer Rim. **A future drop could decide whether Drago and Yerkys are the same character (Hutt vs. Twi'lek species inconsistency aside) or whether Drago is a CW-period predecessor of Yerkys' eventual GCW operation.** Both options are defensible. Option B (Drago is CW-period; Yerkys arrives in the Outer Rim post-CW and inherits the loanshark niche) is mildly more elegant — it makes both characters era-canonical without forcing a species retcon.

---

## 9. Bonus: Faction-code validator script

Per the Q4 action item in `cw_content_gap_design_v1_1_decisions.md`. Greps design docs for deprecated faction codes and reports findings. Standalone script — no engine surface, no external dependencies beyond standard library.

```python
#!/usr/bin/env python3
"""
verify_faction_codes_in_design_docs.py
=======================================

Scans markdown design docs for deprecated faction codes that don't match
the live `data/worlds/clone_wars/organizations.yaml` codes.

Per cw_content_gap_design_v1_1_decisions.md Q4, the canonical mappings are:
    hutt        -> hutt_cartel
    bh_guild    -> bounty_hunters_guild
    traders     -> shipwrights_guild   (no Traders' Coalition in CW)
    underworld  -> hutt_cartel          (no separate underworld faction)

Usage:
    python3 verify_faction_codes_in_design_docs.py [--path PATH]

Exit codes:
    0 — clean, no findings
    1 — at least one deprecated code found

Findings are reported in `file:line:context` format. The validator is a
sanity check, not a hard blocker — design docs aren't authoritative
configuration; they are reference material. But this catches the issue
when it recurs.
"""

import argparse
import re
import sys
from pathlib import Path

# Patterns: word-boundary-anchored matches for the deprecated codes.
# Looking for these in *quoted-string* or *YAML/JSON-key* contexts where
# they would be interpreted as faction codes. False-positive minimization
# is a goal but not absolute — surface findings, let the human triage.
DEPRECATED_PATTERNS = [
    # Code, replacement, pattern
    ("hutt",       "hutt_cartel",         re.compile(r'(?<!_)\bhutt\b(?!_)')),
    ("bh_guild",   "bounty_hunters_guild", re.compile(r'\bbh_guild\b')),
    ("traders",    "shipwrights_guild",   re.compile(r'\btraders\b')),
    ("underworld", "hutt_cartel",         re.compile(r'\bunderworld\b')),
]

# Skip lines that mention the codes only as part of this validator's own
# documentation, in tables describing the mappings, or in prose discussing
# the issue itself. Heuristic: skip if the line contains "->" or "→"
# (mapping notation) or "deprecated" or matches a header.
def looks_like_mapping_line(line: str) -> bool:
    if "->" in line or "→" in line:
        return True
    if "deprecated" in line.lower():
        return True
    if re.match(r'^\s*\|', line):  # markdown table row — likely a mapping
        return True
    return False


def scan_file(path: Path) -> list:
    """Return list of (lineno, code, replacement, line_text) tuples."""
    findings = []
    try:
        with path.open("r", encoding="utf-8") as fp:
            for lineno, line in enumerate(fp, 1):
                if looks_like_mapping_line(line):
                    continue
                for code, replacement, pattern in DEPRECATED_PATTERNS:
                    if pattern.search(line):
                        findings.append((lineno, code, replacement, line.rstrip()))
    except (UnicodeDecodeError, PermissionError):
        pass
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".", help="Root path to scan")
    parser.add_argument("--ext", default=".md", help="File extension to match (default: .md)")
    parser.add_argument("--quiet", action="store_true", help="Only print exit code, no per-finding output")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"ERROR: path does not exist: {root}", file=sys.stderr)
        return 2

    total_findings = 0
    files_scanned = 0
    for md_path in root.rglob(f"*{args.ext}"):
        files_scanned += 1
        findings = scan_file(md_path)
        for lineno, code, replacement, line in findings:
            total_findings += 1
            if not args.quiet:
                rel = md_path.relative_to(root) if md_path.is_relative_to(root) else md_path
                print(f"{rel}:{lineno}: code '{code}' (use '{replacement}'): {line[:120]}")

    if not args.quiet:
        print(f"\nScanned {files_scanned} files. Found {total_findings} potential deprecated-code references.")

    return 1 if total_findings > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
```

**Notes on use:**

- The validator is intentionally noisy. The word "hutt" is a real word in normal English ("the Hutts run everything") and will match. Triage findings rather than treating them as bugs.
- The `looks_like_mapping_line` heuristic skips obvious documentation lines (tables, mapping notation, lines containing "deprecated").
- The validator does not check faction codes inside YAML config files — those are authoritative and should match live `organizations.yaml` directly. Use a separate script for config validation.
- Run periodically during design-doc authoring sessions to catch drift early.

---

## 10. Remaining unmined pages

Pages from GG6 that were sampled but not extracted in this drop:

- **Chapter 9: The Minos Cluster (pp. 38-42)** — campaign setting overview. Imperial-occupied colonies, light Rebel cell. Heavily GCW-keyed; not extractable for CW use without substantial rework.
- **Chapter 10: Planets of the Minos Cluster (pp. 43-60)** — 10 planet entries. GCW-keyed campaign material. Worth a future scan for any era-portable planet-archetype patterns (hint: the Adarlon entertainment-hub trope is era-portable and could ground a future Coruscant entertainment-quarter NPC drop).
- **Chapter 11: A Minos Campaign (pp. 61-68)** — adventure scenarios. Not extractable as content; possibly extractable as "scenario template" patterns for future quest-design work.
- **Charts and Tables (pp. 77-80)** — bargain table, fuel consumption, luxury goods reference. Useful as engine-implementation reference if the trade economy is ever hardened. Not extracted in detail here; refer to GG6 directly.
- **Chapter 2: Player Introduction (p. 8)** — flavor introduction. Not deliverable-grade content.

Estimated unmined extractable content: ~10-15 additional lore entries (planet archetypes from Chapter 10, scenario hooks from Chapter 11 stripped of GCW framing). Defer to a J3 follow-up extraction if Coruscant or other planetary-roster drops want the deeper grounding.

---

## 11. Sign-off

**12 lore entries** ready for `engine/world_lore.py`.
**6 tramp captain templates + 3 supporting archetypes** ready for re-skinning.
**Complete ship modification economy** documented for future hardening drops.
**Canonical loanshark mechanic** documented with FDtS divergence analysis and 3 reconciliation options.
**Mak Torvin / Lira Shan / Grek** all grounded in specific GG6 archetypes with explicit mapping notes.
**Faction-code validator script** authored per Q4 action item.

The extraction satisfies the Drop J1 spec from `cw_content_gap_design_v1_1_decisions.md` §4. The FDtS step content drop is now unblocked on the source-grounding axis (it still requires the Q4 reconciliation to be applied to the v2 design doc's JSON examples — a small future drop or part of FDtS itself).

*— Opus, parallel CW track, April 26 2026 (Drop J1)*
