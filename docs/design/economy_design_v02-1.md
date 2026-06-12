# Star Wars D6 MUSH — Economy Design Document
## Version 0.2 — Profession-Based Income Lanes

---

## 1. Design Principles

### 1.1 Core Constraint: Small Player Population
EVE works at 30,000+ concurrent. SWG worked at 3,000+. We're designing for 5-50.
This kills pure player-driven free markets — not enough volume. We use a **hybrid 
model**: NPC infrastructure provides baseline supply/demand, player activity creates 
the premium layer.

### 1.2 The Four Laws
1. **Every credit entering the game must have a path to leave.** (Sink/Faucet balance)
2. **Risk must scale with reward.** No safe grind that prints money forever.
3. **Every archetype has a viable income path.** Nobody is locked out of earning.
4. **Player choices must have economic consequences.** Gear quality, route selection,
   faction alignment, crafting investment — decisions that matter.

### 1.3 Star Wars Feel
The economy should feel like the Outer Rim. Smugglers smuggle. Bounty hunters hunt.
Mechanics keep everything running. Jedi are poor monks who occasionally need 
something expensive (a crystal, passage offworld) and have to do favors or rely 
on allies. Nobody gets rich doing the right thing, but the dark path always pays.

---

## 2. Credit Flow Architecture

```
    ┌────────────────────────────────────────────────────────────┐
    │                  FAUCETS (Credits In)                       │
    │                                                            │
    │  Smuggling Runs ───────────── Smugglers, Pilots            │
    │  NPC Bounties ─────────────── Bounty Hunters, Combat chars │
    │  Crafting & Repair Services ─ Technicians, Weaponsmiths    │
    │  Medical Services ─────────── Medics                       │
    │  Slicing & Intelligence ───── Slicers, Spies               │
    │  Performance & Morale ─────── Entertainers (cantina)       │
    │  Salvage & Scavenging ─────── Scouts, Scavengers           │
    │  Force Services ───────────── Jedi (limited, see §3.8)     │
    │  Mission Board (all types) ── Everyone                     │
    │  Selling Loot to NPCs ─────── Everyone                     │
    │  Gambling (Sabacc) ────────── Everyone (zero-sum + house)  │
    └──────────────────────┬─────────────────────────────────────┘
                           │
                   [ Player Wallets ]
                           │
    ┌──────────────────────┴─────────────────────────────────────┐
    │                  SINKS (Credits Out)                        │
    │                                                            │
    │  Item Durability/Repair ────── 30% of outflow              │
    │  Ship Fuel & Docking ───────── 20% of outflow              │
    │  NPC Vendor Purchases ──────── 15% of outflow              │
    │  Medical/Bacta Treatment ───── 10% of outflow              │
    │  Transaction Tax (5%) ──────── 10% of outflow              │
    │  Imperial Fines & Bribes ───── 10% of outflow              │
    │  Skill Training Costs ──────── 5% of outflow               │
    └────────────────────────────────────────────────────────────┘
```

### 2.1 Target Equilibrium
A player should earn ~500-2,000 credits per hour of active play.
Basic living expenses (docking, ammo, food, repairs) should cost ~200-400/hr.
Net accumulation: ~300-1,600/hr depending on risk and skill.
Baseline gear: ~500cr. Good ship repair: ~2,000cr. A ship: 50,000-150,000cr.
New player buys basic gear in first session. Saves for a ship over 1-2 weeks.

---

## 3. Profession Income Lanes

Every archetype has a PRIMARY income source that fits their fantasy, a SECONDARY 
source for variety, and access to the general MISSION BOARD as a floor.

### 3.1 Smuggler / Pilot
**Fantasy**: Han Solo. Risk-taker. Fast ship, questionable cargo.
**Primary**: Smuggling runs (cargo delivery with danger scaling)
**Secondary**: Passenger transport (ferry NPCs/players between planets)
**Income**: 500-5,000cr per run depending on risk
**Unique mechanic**: Reputation with contacts unlocks better jobs. 
Getting caught with contraband = cargo confiscated + fine.
**Requires**: Ship, piloting skill, Con/Sneak for inspections.

| Tier | Cargo | Pay | Risk |
|------|-------|-----|------|
| Milk Run | Medical supplies | 200-500 | None |
| Gray Market | Weapons parts | 500-1,500 | 20% patrol |
| Spice Run | Glitterstim | 1,500-5,000 | 50% patrol + pirates |
| Kessel Run | Raw spice | 5,000-15,000 | 80% patrol + nav hazard |

### 3.2 Bounty Hunter
**Fantasy**: Boba Fett. Track, fight, collect.
**Primary**: Bounty board contracts (hunt specific NPC targets)
**Secondary**: Security escort jobs, debt collection for Hutts
**Income**: 300-3,000cr per bounty depending on target tier
**Unique mechanic**: Target NPCs are generated at appropriate tiers using the 
NPC generator. Higher bounties = veteran/superior targets who fight back hard.
Investigation phase: use Search, Tracking, Streetwise to locate the target 
across multiple rooms before combat. Pure combat players who skip investigation 
waste time searching randomly.
**Requires**: Combat skills, Investigation/Search/Tracking.

| Target Tier | Pay | Difficulty |
|-------------|-----|------------|
| Extra | 100-300 | Easy, stationary |
| Average | 300-800 | Moderate, may flee |
| Novice | 800-1,500 | Fights back, armed |
| Veteran | 1,500-3,000 | Dangerous, bodyguards |
| Superior | 3,000-10,000 | Extremely dangerous, rare |

### 3.3 Weaponsmith / Armorsmith
**Fantasy**: The guy with the shop full of custom blasters.
**Primary**: Crafting weapons and armor for sale (player and NPC demand)
**Secondary**: Weapon/armor modification and repair services
**Income**: Markup on crafted items over NPC baseline. A quality-80 blaster 
sells for 150-300% of the NPC price. Repair services: 50-200cr per job.
**Unique mechanic**: Crafted items have your name on them. Resource quality 
directly affects item stats. Experimentation rolls create unique items — no 
two are identical. Your reputation is your brand.
**Requires**: Technical skills (blaster repair, armor repair), resources, schematics.

**Income flow**: Buy quality-40 materials from NPC vendor (200cr), craft a 
blaster pistol (skill check + experiment), sell the finished product to NPC 
shop for 600-1,200cr depending on quality, or sell to players at a premium.
Net profit: 400-1,000cr per crafted item, minus materials and risk of 
critical failure destroying materials.

### 3.4 Mechanic / Shipwright
**Fantasy**: The grease monkey who keeps the Falcon flying.
**Primary**: Ship repair services (hull, systems, overhaul)
**Secondary**: Vehicle modification, droid repair, component crafting
**Income**: Ship repair is the most expensive service in the game. Players 
will ALWAYS need mechanics because ships take damage in space combat and 
components degrade over time.
**Unique mechanic**: Better Technical skill = cheaper repair (fewer materials 
wasted). A master mechanic can repair a system for 60% of what the NPC 
repair bay charges. This spread is pure profit.
**Requires**: Technical skills (space transport repair, starfighter repair, 
droid repair), components/materials.

| Service | NPC Price | Player Mechanic Cost | Mechanic Profit |
|---------|-----------|---------------------|-----------------|
| Hull patch (1 point) | 500cr | 200cr materials | 300cr |
| System repair | 1,000cr | 400cr materials | 600cr |
| Full overhaul | 10,000cr | 4,000cr materials | 6,000cr |

### 3.5 Medic / Doctor
**Fantasy**: The field medic patching blaster wounds between firefights.
**Primary**: Healing services (bacta treatment, wound treatment)
**Secondary**: Crafting stimpacks and medpacs for sale (consumables)
**Income**: Medical treatment is a constant need. Every combat character 
takes wounds. NPC medical bays charge full price; player medics charge less 
and get to keep the spread. Stimpacks are consumable — perpetual demand.
**Unique mechanic**: Better Medicine/First Aid skill = heal more wound 
levels per treatment. A novice medic heals Stunned/Wounded. A master can 
stabilize Mortally Wounded and prevent death rolls.
**Requires**: First Aid, Medicine, organic compounds for crafting.

| Service | NPC Price | Player Medic Cost | Medic Profit |
|---------|-----------|-------------------|--------------|
| Treat Stunned | 50cr | Free (skill only) | 50cr |
| Treat Wounded | 200cr | 50cr materials | 150cr |
| Treat Incapacitated | 500cr | 150cr materials | 350cr |
| Stabilize Mortally Wounded | 1,000cr | 300cr materials | 700cr |
| Craft stimpacks (10) | — | 100cr materials | Sell at 30cr each = 200cr |

### 3.6 Slicer / Intelligence Agent
**Fantasy**: The hacker who opens doors and finds secrets.
**Primary**: Slicing contracts (bypass security, decrypt data, forge documents)
**Secondary**: Intelligence gathering (sell information to factions)
**Income**: Slicing is high-skill, high-margin. Fewer people can do it. 
Opening a locked container might yield 500-2,000cr in hidden goods. 
Forging transit documents for smugglers: 300-500cr per set.
**Unique mechanic**: Encrypted datacrons found as loot are worthless until 
a slicer decrypts them. Contents might be coordinates to a stash, faction 
intel worth reputation, or financial data worth credits. Creates interdependency 
— combat characters find datacrons, slicers unlock them, they split the take.
**Requires**: Computer Programming/Repair, Security, Forgery.

### 3.7 Scout / Scavenger
**Fantasy**: The junk dealer who finds value in wreckage.
**Primary**: Salvage runs (harvest components from wrecks, ruins, battlefields)
**Secondary**: Resource surveying (find high-quality material deposits, sell 
location data to crafters)
**Income**: Salvage yields random-quality components (10-70 quality). Higher 
Perception and Search skill = better finds. Survey data for quality-80+ 
deposits sells to crafters for 200-500cr.
**Unique mechanic**: After any space battle, debris fields appear. Scouts 
with the right skills can salvage them before they despawn. Ground-side, 
unexplored areas (Jundland Wastes, crashed ships) have lootable caches 
that respawn on a timer.
**Requires**: Search, Survival, Perception, basic Technical.

### 3.8 Jedi / Force User
**Fantasy**: Poor monk with a laser sword. Credits are not the Jedi way.

Jedi have **no dedicated income lane**. This is intentional and thematic.

**Why**: In the source material, Jedi don't charge for their services. 
They rely on the hospitality of those they help. Luke didn't invoice the 
Rebel Alliance. Obi-Wan lived in a cave. The Jedi path is powerful but poor.

**How they get by**:
- **Gratitude payments**: NPCs occasionally give credits after Force-assisted 
  help (heal someone with Force, resolve a conflict). Small amounts: 50-200cr.
- **Mission board**: Jedi can take standard missions like anyone. The Force 
  doesn't pay, but the Mission Board does.
- **Faction stipend**: Rebel Alliance (or other allied faction) provides a 
  small weekly stipend to Force-sensitives who maintain good standing. ~500cr/week.
- **Party economics**: Jedi in a group benefit from the group's income. The 
  smuggler makes the money; the Jedi provides the combat/Force advantage.
- **Dark side shortcut**: Using Affect Mind to swindle credits, Injure/Kill 
  for bounties, working for the Hutts — all viable but cost Dark Side Points. 
  The dark side is the fast path to wealth. This is a real temptation mechanic.

**Design intent**: Jedi players should feel tension between power and poverty. 
They're the strongest in combat and the Force, but they need allies for the 
economic game. This creates party interdependency and makes the dark side 
temptation meaningful — "I could just mind-trick this merchant for free gear, 
but it costs me a DSP..."

### 3.9 Noble / Diplomat / Entertainer
**Fantasy**: Lando Calrissian. Mon Mothma. Figrin D'an.
**Primary**: Social contracts (negotiate deals, perform in cantinas, broker trades)
**Secondary**: Information brokering, faction liaison work
**Income**: Performance in cantinas generates tips from NPC patrons (passive 
income while "performing" — 50-200cr per 15 minutes of in-character RP).
Negotiation skill reduces prices on NPC purchases (Bargain skill = discount).
Brokering trades between other players for a cut.
**Unique mechanic**: High Persuasion/Bargain/Con unlocks "social missions" 
on the mission board that combat characters can't access: negotiate a treaty, 
convince a witness to testify, broker a business deal. Pay: 500-2,000cr.
**Requires**: Persuasion, Bargain, Con, Command, Languages.

### 3.10 Generic / Multi-Class
**Fantasy**: The player who doesn't specialize.
**Primary**: Mission board (available to everyone)
**Secondary**: Selling loot from combat encounters
**Income**: Mission board always has 3-5 missions available covering delivery, 
combat, investigation, and social tasks. Pay: 200-1,000cr. These are the 
floor — anyone can earn credits, but specialists earn more in their lane.

---

## 4. The Mission Board (Universal Faucet)

Every player has access to the Mission Board regardless of build. This prevents 
anyone from being completely broke.

### 4.1 Mission Types

| Type | Skills Used | Pay | Frequency |
|------|-----------|-----|-----------|
| Delivery | Movement only | 100-300cr | Always available |
| Combat | Any combat skill | 300-1,000cr | Frequent |
| Investigation | Search, Streetwise | 200-800cr | Moderate |
| Social | Persuasion, Bargain, Con | 500-2,000cr | Rare |
| Technical | Any repair skill | 300-1,500cr | Moderate |
| Medical | First Aid, Medicine | 200-1,000cr | Frequent |
| Smuggling | Piloting, Con, Sneak | 500-5,000cr | Moderate |
| Bounty | Combat + Investigation | 300-3,000cr | Moderate |
| Slicing | Computer Prog, Security | 400-2,000cr | Rare |
| Salvage | Search, Perception | 200-1,000cr | Moderate |

### 4.2 Mission Generation

Missions auto-generate based on:
- Available room graph (destinations, NPC locations)
- Player skill levels (harder missions appear as skills improve)
- Faction state (Imperial crackdown = more smuggling jobs but higher risk)
- Randomized objectives and targets (NPC generator for bounties)

Board refreshes every 30 minutes. 5-8 missions available at any time.
Completed missions are replaced immediately.

---

## 5. Sink Systems (unchanged from v0.1, summarized)

| Sink | % of Outflow | How |
|------|-------------|-----|
| Item durability/repair | 30% | Weapons and armor degrade with use |
| Ship fuel & docking | 20% | 25cr/day docking, fuel per jump/combat |
| NPC vendor markup | 15% | Buy at 100%, sell back at 25-50% |
| Medical treatment | 10% | Wounds cost credits to heal at NPC bays |
| Transaction tax | 10% | 5% on player-to-player transfers |
| Imperial fines | 10% | Caught smuggling/fighting = fines |
| Skill training | 5% | 100-500cr per skill learned/improved |

---

## 6. Crafting System (SWG-Lite, unchanged from v0.1)

See v0.1 §5 for full crafting details. Key points:
- 6 resource types with quality 1-100
- Assembly + experimentation skill checks
- Crafter name permanently on items
- Critical failure destroys materials (risk)
- Quality-80+ materials yield superior items

---

## 7. Item Durability (unchanged from v0.1)

See v0.1 §6 for full durability details. Key points:
- Condition 100 → 0 through combat use
- Repair restores condition but reduces max by 5 each time
- Master-crafted items start higher (120-150 max condition)
- Creates perpetual demand for crafters and repair services

---

## 8. Faction Reputation (expanded)

### 8.1 Six Factions

| Faction | Primary Income Source | Opposes |
|---------|----------------------|---------|
| Rebel Alliance | Military missions, stipends | Empire |
| Galactic Empire | Imperial contracts, bounties | Rebellion |
| Hutt Cartel | Smuggling, black market | — (neutral broker) |
| Bounty Hunters' Guild | Registered bounties | — (neutral) |
| Traders' Guild | Crafting, honest commerce | Underworld |
| Underworld | Slicing, fencing, shady deals | Traders' Guild |

### 8.2 Axis Conflicts
- **Rebel ↔ Empire**: Primary political axis. Going up in one pulls down the other.
- **Traders' Guild ↔ Underworld**: Economic axis. Honest vs. criminal business.
- **Hutts**: Neutral broker. Can have high Hutt rep AND high Rebel/Empire rep.
  The Hutts don't care about your politics, only your reliability.
- **Bounty Hunters' Guild**: Neutral. Takes contracts from anyone. Rep is purely 
  based on completing bounties, not on who posted them.

### 8.3 Economic Impact of Faction Standing

| Standing | Effect |
|----------|--------|
| Hostile | Cannot buy from faction vendors. Attacked on sight in faction territory. |
| Unfriendly | 150% markup at faction vendors. Searched at faction checkpoints. |
| Neutral | Standard prices. No special access. |
| Friendly | 10% discount. Access to faction mission board. |
| Trusted | 20% discount. Access to restricted gear/locations. |
| Allied | 30% discount. Faction stipend (100-500cr/week). Best mission access. |

---

## 9. Income Comparison (Hourly Estimates)

Assuming competent skill investment and active play:

| Archetype | Low End | Typical | High End | Notes |
|-----------|---------|---------|----------|-------|
| Smuggler | 500cr | 1,500cr | 5,000cr | Risk-dependent; can lose it all |
| Bounty Hunter | 400cr | 1,200cr | 3,000cr | Per-target; downtime between hunts |
| Weaponsmith | 300cr | 800cr | 2,000cr | Steady; limited by material supply |
| Mechanic | 400cr | 1,000cr | 3,000cr | Scales with player ship count |
| Medic | 300cr | 700cr | 1,500cr | Steady; always in demand |
| Slicer | 200cr | 600cr | 2,500cr | Feast-or-famine; big scores |
| Scout | 200cr | 500cr | 1,500cr | Depends on what you find |
| Jedi | 100cr | 300cr | 800cr | Intentionally low; party-dependent |
| Noble/Entertainer | 200cr | 600cr | 1,500cr | Social RP + mission board |
| Generalist | 200cr | 500cr | 1,000cr | Mission board baseline |

**Note**: These are SOLO income. Party play multiplies: a 4-person crew 
(pilot + gunner + mechanic + medic) running smuggling operations together 
earns 3-4x what any of them could solo, split evenly.

---

## 10. Dark Side Economics

The dark side is ALWAYS more profitable. This is a design feature, not a bug.

| Light Side Action | Pay | Dark Side Equivalent | Pay |
|-------------------|-----|---------------------|-----|
| Deliver medical supplies | 200cr | Deliver spice | 2,000cr |
| Return lost property | 100cr | Sell stolen property | 500cr |
| Negotiate peacefully | 500cr | Extort with Force | 1,000cr + DSP |
| Turn in bounty alive | 800cr | Kill target, take their gear too | 800cr + loot |
| Help for free (Jedi way) | 0cr + Light Side Point | Mind-trick for payment | 500cr + DSP |

**Light Side Points** are earned by doing the right thing for free or at cost.
At certain LSP thresholds, Force-sensitives get:
- LSP 5: Force skills improve +1 pip (free advancement)
- LSP 10: Force powers cost less strain / have lower difficulty
- LSP 15+: Can call on the Force in desperate moments (extra FP)

So the light side rewards you with POWER, not CREDITS.
The dark side rewards you with CREDITS, but costs you POWER (DSP erodes control).

This is the thematic core: "You can have wealth or virtue, but not both easily."

---

## 11. Implementation Phases

### Phase 1: Foundation
- [ ] Condition field on weapons/armor, wear on combat use
- [ ] NPC repair command, player repair (Technical skill check)
- [ ] `sell` command at NPC vendors (25-50% value)
- [ ] Docking fees (passive daily drain)
- [ ] Ship fuel costs on hyperspace/combat
- [ ] Skill training costs

### Phase 2: Income Lanes
- [ ] Mission board system (auto-generated missions for all types)
- [ ] Bounty board (NPC-generated targets using NPC generator)
- [ ] Smuggling job board (cargo delivery with patrol encounters)
- [ ] Medical service commands (player-to-player healing for credits)
- [ ] Performance/entertainer income (cantina RP)

### Phase 3: Crafting & Resources
- [ ] Resource quality model (1-100)
- [ ] Resource surveying and harvesting
- [ ] Assembly + experimentation crafting
- [ ] Crafter name/reputation system
- [ ] NPC shop integration for crafted goods

### Phase 4: Full Economy
- [ ] Faction reputation system (6 factions, axis conflicts)
- [ ] Faction vendor discounts/access
- [ ] Transaction tax on player trades
- [ ] Light Side Point / Dark Side Point economic effects
- [ ] Admin @economy dashboard (credits in/out, monitoring)
- [ ] Sabacc gambling

---

## 12. Open Questions for Iteration

1. **Decay speed**: ~50 combats per repair, ~500 per lifecycle. Right?

2. **Ship loss**: Disabled + expensive repair, not destroyed. Agree?

3. **Resource granularity**: 6 types × 3-4 subtypes = ~20. Enough?

4. **Party income splitting**: Auto-split when grouped, or manual?

5. **Entertainer income**: Too passive if it's "sit in cantina, earn credits"?
   Should it require active RP engagement (emotes, performance commands)?

6. **Jedi income floor**: Is 100-300cr/hr too punishing, or does the power 
   advantage justify it? Should Jedi temples/enclaves provide free room & board 
   to offset? 

7. **Crafting depth**: Should there be rare schematics as drops (creating a
   schematic economy), or should all schematics be learnable from trainers?

8. **NPC economy scaling**: Should NPC vendor prices adjust based on supply/demand
   (dynamic like EVE), or stay fixed (stable anchor)?

---

## 13. Anti-Exploit Considerations

- **Alt farming**: Limit credit transfers between characters on same account
- **AFK grinding**: No passive income except docked ship fees (which are negative)
- **Duplication**: All mutations through single DB transactions
- **Market manipulation**: NPC price floors/ceilings prevent loops
- **Credit overflow**: Admin @economy dashboard for live monitoring
- **Bounty cycling**: Can't put bounties on yourself or your alts
- **Faction exploits**: Reputation changes capped per day to prevent speed-running
