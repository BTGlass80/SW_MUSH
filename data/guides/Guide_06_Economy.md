---
category: economy
order: 1
summary: "Credits, missions, bounties, smuggling, commissary, and creature spoils. How money moves."
tags: ["economy", "credits", "money", "missions", "bounty", "smuggling", "trade"]
---

# Economy: Missions, Bounties, Smuggling & Trade

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Economic Design Targets

The economy is designed around these targets for an active player:

| Metric | Target |
|--------|--------|
| **Earning rate** | 500–2,000 credits/hour |
| **Living expenses** | 200–400 credits/hour |
| **Net accumulation** | 300–1,600 credits/hour |

The spread is intentional — a cautious player doing delivery missions earns less but risks nothing. A smuggler running raw spice earns 10x more but can lose half the reward to Republic customs fines. Skill, risk tolerance, and time invested all affect income.

---

## 2. Mission Board

The mission board is the primary reliable income source. It holds **5–8 procedurally generated jobs** spanning 14 mission types. The board refreshes every 30 minutes, and completed missions are replaced immediately.

**Ground mission types (10):**

| Type | Skill Tested | Pay Range | Partial Pay |
|------|-------------|-----------|-------------|
| Delivery | Stamina | 100–300 cr | 100% (always full) |
| Combat | Blaster | 300–1,000 cr | 50% |
| Investigation | Search | 200–800 cr | 75% |
| Social | Persuasion | 500–2,000 cr | 75% |
| Technical | Space Transports Repair | 300–1,500 cr | 50% |
| Medical | First Aid | 200–1,000 cr | 75% |
| Smuggling | Con | 500–5,000 cr | 50% |
| Bounty | Streetwise | 300–3,000 cr | 50% |
| Slicing | Computer Prog/Repair | 400–2,000 cr | 50% |
| Salvage | Search | 200–1,000 cr | 75% |

**Space mission types (4):**

| Type | Pay Range | Requirement |
|------|-----------|-------------|
| Patrol | 300–1,500 cr | Hold a zone for 120 ticks |
| Escort | 500–2,000 cr | Protect NPC trader to destination |
| Intercept | 500–2,500 cr | Destroy N hostile ships in a zone |
| Survey Zone | 300–1,200 cr | Resolve at least 1 anomaly in a zone |

**Mission lifecycle:** AVAILABLE → ACCEPTED → COMPLETE/EXPIRED/FAILED. One active mission per character at a time. Unclaimed missions expire after 1 hour; accepted missions expire after 2 hours.

**Commands:**
```
missions                  — View the mission board
mission accept <#>        — Accept a mission
mission info <#>          — View mission details
mission complete          — Complete your active mission (skill check)
mission abandon           — Abandon your active mission
```

**Completion:** When you type `mission complete` at the appropriate location, the game rolls the relevant skill against a difficulty scaled by the reward amount. Full success pays full reward. Partial success (miss by ≤4) pays a fraction. Failure pays nothing. Critical success (Wild Die exploded) gives a bonus. Fumble (Wild Die = 1) may impose a penalty.

---

## 3. Bounty Board

The bounty board offers **hunting contracts** — targets are actual NPCs spawned in the game world. You have to find them and defeat them in combat.

**5 bounty tiers:**

| Tier | Pay Range | Spawn Weight | Target Difficulty |
|------|-----------|-------------|-------------------|
| Extra | 100–300 cr | Common (5) | Easy NPC |
| Average | 300–800 cr | Frequent (4) | Moderate NPC |
| Novice | 800–1,500 cr | Moderate (3) | Competent NPC |
| Veteran | 1,500–3,000 cr | Uncommon (2) | Dangerous NPC |
| Superior | 3,000–10,000 cr | Rare (1) | Elite NPC |

**Bounty lifecycle:** POSTED → CLAIMED → COLLECTED/EXPIRED/FAILED. Board holds 3–5 contracts. Refreshes every 45 minutes. Unclaimed bounties expire after 3 hours; claimed bounties expire after 4 hours.

**Investigation phase:** Before engaging, you can track your target:
```
bountytrack               — Use Search/Streetwise to locate your target
```
This reveals the target's current room without requiring direct combat.

**Commands:**
```
bounties                  — View the bounty board
bounty claim <#>          — Claim a bounty contract
bounty info <#>           — View bounty details
bounty collect            — Collect reward after defeating target
bounty abandon            — Abandon your claimed bounty
```

**Target archetypes:** Thugs, smugglers, bounty hunters, scouts, B1 droids, CIS agents, Hutt enforcers — procedurally generated with appropriate stats and equipment for their tier.

---

## 4. Smuggling

Smuggling is the high-risk, high-reward income path. You pick up contraband cargo from criminal contacts and deliver it to a dropoff point, hoping to avoid Republic clone patrol along the way.

**4 cargo tiers:**

| Tier | Cargo Type | Pay Range | Patrol Risk | Patrol Difficulty |
|------|-----------|-----------|-------------|-------------------|
| 0 — Grey Market | Medical supplies | 200–500 cr | 0% | None |
| 1 — Black Market | Weapons parts | 500–1,500 cr | 20% | Easy (10) |
| 2 — Contraband | Glitterstim | 1,500–5,000 cr | 50% | Moderate (15) |
| 3 — Spice Run | Raw spice | 5,000–15,000 cr | 80% | Difficult (20) |

**Multi-planet routes (5 route tiers):**

| Route | Tier | Destination | Pay | Patrol Chance |
|-------|------|-------------|-----|---------------|
| Local | Grey | Same planet | 200–500 cr | 0% |
| Black Market | Black | Same planet | 500–1,500 cr | 20% |
| Interplanetary | Black | Nar Shaddaa | 1,500–3,000 cr | 30% |
| Spice Run | Contraband | Kessel | 3,000–6,000 cr | 55% |
| Core Run | Spice | Corellia | 4,000–8,000 cr | 65% |

**Patrol encounters:** If intercepted, you roll Con or Sneak (your choice) against the tier's difficulty. Success means you slip past. Failure means cargo confiscated + a fine of 50% of the job reward.

**Director integration:** A LOCKDOWN alert from the Director AI adds +1 tier of patrol risk (making tier 0 behave like tier 1, etc.).

**Planet arrival checks:** Extra patrol check on hyperspace arrival, stacking with launch check. Corellia (Core World) has 60% patrol frequency; Tatooine (Outer Rim) only 10%.

**Commands:**
```
smugjobs                  — View available smuggling jobs
smugaccept <#>            — Accept a smuggling job
smugjob                   — View your active job details
smugdeliver               — Deliver cargo at the dropoff
smugdump                  — Dump contraband (avoid fines, lose cargo)
```

---

## 5. Cargo Trading

(Detailed in Guide #5, section 8 — summarized here for completeness.)

Buy-low-sell-high speculative trading between planets. 8 trade goods with planet-specific source (50% price) and demand (200% price) multipliers. A Bargain skill check modifies the price by ±10%. Cargo stored in ship's hold.

**Key vulnerability (from audit):** Static price multipliers with no supply limits mean a single run of Luxury Goods from Corellia to Tatooine in a full YT-1300 generates ~240,000 cr/hr — 120x the design target. This is a known issue awaiting dynamic supply pools.

---

## 6. Other Income Sources

**Entertainment:** The `perform` command in cantina zones rolls a Perception-based check. Success earns credits based on performance quality. A niche but risk-free income.

**Medical healing:** Player-to-player healing via `heal <player>` / `healaccept`. The healer rolls First Aid. Credits are exchanged P2P (the patient pays).

**Faction stipends:** Weekly payroll from faction treasury. Amount varies by faction and rank.

**Weapon sell-back:** Selling weapons to NPC vendors returns 25–50% of purchase price. Bargain check affects the price.

---

## 7. Credit Sinks (Where Money Goes)

| Sink | Cost | Frequency |
|------|------|-----------|
| Ship fuel (launch) | 50–100 cr | Per launch |
| Ship fuel (hyperspace) | 100–600 cr | Per jump |
| Docking fees | 25–38 cr | Per landing |
| Weapon repair | 50–250 cr | When condition degrades |
| NPC weapon purchases | 275–5,000 cr | One-time per weapon |
| NPC crew wages | 30–1,000 cr | Every 4 hours per crew |
| Vendor droid | 2,000–12,000 cr | One-time purchase |
| Vendor listing fee | 1–2% | Per sale |
| Housing deposit | 500 cr | One-time |
| Housing rent | 50 cr/week (Tier 1) | Weekly |
| Smuggling fines | 50% of job reward | On patrol failure |
| Sabacc house rake | 10% of pot | Per game |

**Weapon durability** creates an ongoing repair cycle — every attack degrades weapon condition by 1 point. When condition hits 0, the weapon needs repair from an NPC. This is a well-designed lifecycle sink.

---

## 8. The Bargain Skill

Many economic transactions involve a **Bargain skill check** — an opposed roll between your Bargain skill and the NPC vendor's bargain dice. The margin determines a price modifier:

- ±2% per 4 points of margin, capped at ±10%
- Critical success doubles the modifier (still capped)
- Fumble inverts the modifier and guarantees at least 2% swing against you

When buying, a positive margin means a cheaper price. When selling, it means a higher sell price. A skilled haggler saves/earns 10% on every transaction.

---

## 9. Faction Commissary

Sworn members of most factions can requisition gear from their faction's commissary — rank-appropriate equipment at below-market prices. This is a **credit sink**: you're spending earned credits on gear issued by the organization rather than buying from the open market.

**Which factions have a commissary:**

| Faction | Access |
|---------|--------|
| Republic | Rank 0+ (uniform + sidearm free issue; rifle + armor at Rank 1) |
| CIS | Rank 0+ (comlink at Rank 0; operative kit + pistol at Rank 1) |
| Hutt Cartel | Rank 0+ (pistol at Rank 0; heavy pistol + vest at Rank 1) |
| Bounty Hunters' Guild | Rank 0+ (binder cuffs + license at Rank 0; tracking fob at Rank 1) |
| Jedi Order | **No commissary** — the Order issues, it does not sell. |

**Republic commissary:**

| Item | Slot | Cost | Min Rank |
|------|------|------|----------|
| Republic Service Uniform | Armor | 150 cr | 0 |
| DC-17 Hand Blaster | Weapon | 500 cr | 0 |
| DC-15A Blaster Rifle | Weapon | 1,200 cr | 1 |
| Republic Combat Plate | Armor | 900 cr | 1 |

**Bounty Hunters' Guild commissary:**

| Item | Slot | Cost | Min Rank |
|------|------|------|----------|
| Binder Cuffs | Misc | 200 cr | 0 |
| Guild License | Misc | 100 cr | 0 |
| Tracking Fob (+1D Search for targets) | Misc | 350 cr | 1 |

CIS and Hutt Cartel commissaries follow the same pattern — a basic loadout at Rank 0, heavier kit at Rank 1. Use `+commissary` to see the catalog for your faction and rank.

**Commands:**
```
+commissary                  — Browse your faction's catalog
+commissary buy <key>        — Purchase an item (debits credits)
+commissary sell <key>       — Sell a commissary item back (partial refund)
```

Items bought via commissary behave identically to the same items acquired elsewhere. The `key` is shown in the catalog listing.

---

## 10. Creature Spoils

Killing certain wilderness creatures triggers an automatic **field-dressing check** when the creature falls. No command needed — if you land the killing blow, the engine rolls Survival (DC 8, or 10 for some tougher creatures) against your character's Survival skill. Success yields a resource stack in your inventory.

**How it works:**

1. You defeat a creature that has spoils in the wilderness.
2. The engine rolls `Survival vs. DC` automatically.
3. **Success:** You receive a resource stack. Margin bonuses apply (+1 stack unit per 6 points of margin over DC, capped at base + 2 units). Quality scales with margin (base ~40, +3 per margin point, capped at 65).
4. **Failure:** No resource. The carcass yields nothing.

**What creatures drop:**

| Creature | Material | Type | DC |
|----------|----------|------|----|
| Magus | Magus hide | Organic | 8 |
| Stalker Lizard | Stalker hide | Organic | 8 |
| Tymp | Tymp hide | Organic | 8 |
| Wrix | Wrix pelt | Organic | 8 |
| Voroos | Voroos hide (2 stacks) | Organic | 8 |
| Hitcher Crab | Water sacs | Chemical | 8 |
| Spor Crawler | Spor venom | Chemical | 10 |

Small nuisance creatures (worrt, shredder bat, spor swarms) yield nothing — the field-dressing system rewards big-predator kills by contrast.

**Economy note:** Spoils are **not credits**. They're crafting resources (organic or chemical) that go into the same inventory pool as wilderness-harvested materials. They're not bought by NPC vendors directly; they either go into your crafting queue or sell P2P via a vendor droid buy-order. This means spoils add no inflation to the credit economy — they feed directly into crafting demand.

Quality is intentionally capped below T5 minimum (75), so creature spoils can supply basic and intermediate recipes but never replace the dedicated wilderness harvest economy for high-end materials.

---

## 11. Economy Commands Quick Reference

| System | Commands |
|--------|---------|
| **Missions** | `missions`, `mission accept <#>`, `mission info <#>`, `mission complete`, `mission abandon` |
| **Bounties** | `bounties`, `bounty claim <#>`, `bounty info <#>`, `bounty collect`, `bounty abandon`, `bountytrack` |
| **Smuggling** | `smugjobs`, `smugaccept <#>`, `smugjob`, `smugdeliver`, `smugdump` |
| **Trading** | `market`, `buy <good> <qty>`, `sell <good>` |
| **Commissary** | `+commissary`, `+commissary buy <key>`, `+commissary sell <key>` |
| **General** | `credits` (check balance), `sell` (sell weapons to NPC), `repair` (repair weapons at NPC) |

---

