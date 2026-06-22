---
category: economy
order: 1
summary: "Credits, missions, bounties, smuggling, mob hunting, commissary, and creature spoils. How money moves."
tags: ["economy", "credits", "money", "missions", "bounty", "smuggling", "trade", "hunting"]
---

# Economy: Missions, Bounties, Smuggling & Trade

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — June 2026**
**Guide Version 2.0**

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
| Combat | Blaster | 300–1,000 cr | 40% |
| Investigation | Search | 200–800 cr | 40% |
| Social | Persuasion | 500–2,000 cr | 40% |
| Technical | Space Transports Repair | 300–1,500 cr | 40% |
| Medical | First Aid | 200–1,000 cr | 40% |
| Smuggling | Con | 500–5,000 cr | 40% |
| Bounty | Streetwise | 300–3,000 cr | 40% |
| Slicing | Computer Prog/Repair | 400–2,000 cr | 40% |
| Salvage | Search | 200–1,000 cr | 40% |

Every type except Delivery pays a flat **40%** on a partial success (Delivery always pays in full). The number was levelled to 40% across the board in the economy audit so no mission type is a strictly better partial-pay bet than another.

**Space mission types (4):**

| Type | Pay Range | Requirement |
|------|-----------|-------------|
| Patrol | 600–1,000 cr | Hold a zone for 120 ticks |
| Escort | 1,500–2,500 cr | Protect NPC trader to destination |
| Intercept | 2,000–3,000 cr | Destroy 2–4 hostile ships in a zone |
| Survey Zone | 1,200–1,800 cr | Resolve at least 1 anomaly in a zone |

**Mission lifecycle:** AVAILABLE → ACCEPTED → COMPLETE/EXPIRED/FAILED. One active mission per character at a time. Unclaimed missions expire after 1 hour; accepted missions expire after 2 hours.

**Commands** — every mission verb lives under the `+mission/<switch>` umbrella:
```
+mission/board            — View the mission board
+mission/accept <id>      — Accept a mission by its board id (e.g. m-4f3a; prefix match works)
+mission/view             — View your active mission's details
+mission/complete         — Complete your active mission at the destination (skill check)
+mission/abandon          — Abandon your active mission (no penalty)
```
Bare shorthands still resolve: `missions` (= `/board`), `accept <id>`, `complete`/`turnin`, `abandon`/`dropmission`.

**Completion:** When you type `+mission/complete` at the appropriate location, the game rolls the relevant skill against a difficulty scaled by the reward amount (an 8/11/14/16/19/21 ladder — bigger payouts are harder). Full success pays the full reward. A near miss (margin ≥ −2, i.e. you missed by 2 or less) pays the partial fraction above. Missing by more pays nothing. A critical success (the Wild Die explodes) adds a **+20%** bonus on top. A fumble (Wild Die = 1) colors the failure message but imposes **no extra credit penalty** — you simply earn nothing, the same as any other miss.

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

**Bounty lifecycle:** POSTED → CLAIMED → COLLECTED/EXPIRED/FAILED. The board refills toward 4 contracts (2 minimum). Refreshes every 45 minutes. Unclaimed bounties expire after 3 hours; claimed bounties expire after 4 hours.

**Investigation phase:** Before engaging, you can track your target:
```
+bounty/track             — Use Search, Streetwise, or Tracking to locate your target
```
The track rolls the best of your Search, Streetwise, and Tracking against a per-tier difficulty (6 / 10 / 13 / 17 / 21 from Extra up to Superior). Success reveals the target's current room without requiring direct combat.

**Commands** — every bounty verb lives under the `+bounty/<switch>` umbrella:
```
+bounty/board             — View the bounty board
+bounty/claim <id>        — Claim a bounty contract (e.g. b-7e1f; prefix match works)
+bounty/view              — View your active contract's details
+bounty/track             — Locate your target (Search/Streetwise)
+bounty/collect           — Collect the reward after defeating the target
```
Bare shorthands still resolve: `bounties` (= `/board`), `claimbounty`, `tracktarget`, `collectbounty`. Your active contract also shows under `+mybounty`. A claimed contract you don't finish in time simply expires — there is no manual abandon.

**Target archetypes:** Thugs, smugglers, rogue bounty hunters, scouts, deserter clone troopers, ARC renegades, and corrupt Republic officers — procedurally generated with appropriate stats and equipment for their tier (the roster era-maps to the active timeline, so the Clone Wars fields clone/ARC/Republic figures rather than the underlying generic keys).

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
| Spice Run | Contraband | Geonosis | 3,000–6,000 cr | 55% |
| Core Run | Spice | Coruscant | 4,000–8,000 cr | 65% |

**Patrol encounters:** If intercepted, you roll Con or Sneak (your choice) against the tier's difficulty. Success means you slip past. Failure means cargo confiscated + a fine. The fine is **50%** of the job reward on the low tiers (Grey/Black Market) but only **25%** on the high tiers (Contraband/Spice Run) — at those tiers the patrol *chance* itself is the deterrent, so a bust stings without wiping you out.

**Director integration:** A LOCKDOWN alert from the Director AI adds +1 tier of patrol risk (shifting the intercept chance up ~30% and raising the inspection difficulty by +5). A zone-wide security checkpoint stacks on top of any lockdown.

**Planet arrival checks:** Extra patrol check on hyperspace arrival, stacking with the launch check. Coruscant (Republic capital) runs the heaviest customs presence at 60%, Geonosis (CIS war front) 50%, Nar Shaddaa 15%, and Tatooine (Outer Rim) only 10%.

**Commands** — every smuggling verb lives under the `+smuggle/<switch>` umbrella (you must be near a criminal contact to browse or accept):
```
+smuggle/board            — View available smuggling jobs
+smuggle/accept <id>      — Accept a job by its board id (e.g. smug-2c4b; prefix match works)
+smuggle/view             — View your active run's details
+smuggle/deliver          — Deliver cargo at the dropoff (must be docked there)
+smuggle/dump             — Dump contraband before a patrol (no pay, no fine)
```
Bare shorthands still resolve: `smugjobs`/`underworld` (= `/board`), `takerun`, `cargo`, `deliver`, `jettison`.

---

## 5. Cargo Trading

(Detailed in Guide #5 *Space Systems* — summarized here for completeness.)

Buy-low-sell-high speculative trading between planets. **8 trade goods**, each with planet-specific **source** pricing (**70%** of base — the good is produced cheaply there) and **demand** pricing (**140%** of base — it's scarce/needed there). A Bargain skill check modifies the price by ±10%. Cargo rides in your ship's hold.

Every one of the six Clone Wars launch worlds (Tatooine, Nar Shaddaa, Kuat, Coruscant, Kamino, Geonosis) is both a source for something and a demand for something else, so cargo forms a real multi-world web rather than one fat route. For example, **Luxury Goods** are cheap on Nar Shaddaa (source, 70%) and sell high on Coruscant or Tatooine (demand, 140%).

**On the spread:** the source/demand multipliers were deliberately narrowed from an earlier 50%/200% (a 4:1 ratio) to today's 70%/140% (2:1). The old 4:1 spread was an exploit — a full freighter on the single viable luxury route could clear far more per hour than the design targets in §1 allow. The 2:1 spread is still very profitable for an attentive trader but no longer breaks the curve.

---

## 6. Mob Hunting (the Combat Trickle)

Not every fight is a contract. The galaxy is full of **roaming hostiles** — street thugs, swoop-gang enforcers, pirate scavengers, rogue droids — seeded across populated and contested zones. Putting one down pays a small **automatic credit trickle** plus prestige toward earned hunter titles. There is no board to check and no contract to claim: land the killing blow on a huntable mob and the reward fires on its own.

This is the **solo-play income floor** — what you do when no one else is on and you just want to grind out some NPCs and zone out. It sits deliberately *below* the mission and bounty earning curve in §1: a satisfying tick, not a road to wealth.

**What counts as a huntable mob?** Any generic hostile NPC that does **not** already carry its own reward hook — that is, it is *not* a bounty target, a space/wilderness anomaly spawn, a field-dressable creature, a Dark-Side-Point hunter's quarry, a tutorial/questline chain enemy, or a vendor. Ordinary sentient guards, thugs, gangers, and street pirates standing in the world are the typical quarry. (Posted **bounty contracts** in §3 and field-dressable **creatures** in §11 pay through their own systems and never double-dip with this trickle.)

**The reward:**

| | |
|---|---|
| **Per kill, under the cap** | 15 cr |
| **Daily soft cap** | 400 cr/day from grinding |
| **Per kill, over the cap** | 3 cr — the "extreme trickle" tail |
| **Character Points** | **Zero, always** |
| **Daily reset** | Each new UTC day |

Once the day's grind take passes 400 cr the per-kill reward drops to a token 3 cr. You can keep hunting for prestige and titles, but no longer for meaningful income — the faucet is bounded on purpose.

**Why so small?** Combat costs money. A real fight burns bacta (medical, 50–1,000 cr) and degrades your weapon (repair, 50–250 cr). For any non-trivial mob those costs exceed the 15 cr reward, so grinding runs **break-even to slightly negative** on hard targets — the tougher the quarry, the more you spend healing relative to the trickle. The credits are a bonus on top of an activity you were doing anyway; the *real* reward is the prestige track.

**Character Points are deliberately zero.** Advancement is RP- and time-gated (the weekly CP cap; see Guide #9). Grinding mobs can never buy skill growth — it pays credits and prestige only, and structurally cannot touch your character's progression.

**Milestone hunter titles.** Your lifetime kill count lives in a per-character hunting log, and crossing a threshold earns a permanent, wearable title:

| Lifetime kills | Title key | Worn as |
|----------------|-----------|---------|
| 25 | `hunter` | the Hunter |
| 100 | `seasoned_hunter` | the Seasoned Hunter |
| 500 | `master_hunter` | the Master Hunter |
| 2,500 | `apex_hunter` | the Apex Hunter |

Earned titles are permanent and show on `+finger` and `+sheet`. Wear one with `+title wear <key>` (e.g. `+title wear hunter`).

**Commands:**
```
+hunting                  — Your lifetime kill tally, today's take vs the 400 cr cap, and your next milestone
+title wear <key>         — Wear an earned hunter title
```
Bare `hunting` resolves to the same display. Credits earned this way are tagged `mob_grind` in the economy ledger.

---

## 7. Other Income Sources

**Entertainment:** The `perform` command in cantina zones rolls a Persuasion check (or Musical Instrument, if you have that skill — it's preferred when present). Success earns credits scaled by performance quality and audience size, on a 10-minute cooldown. A niche but risk-free income. (See Guide #23 for the full Entertainer track.)

**Medical healing:** Player-to-player healing via `heal <player>` / `healaccept`. The healer rolls First Aid. Credits are exchanged P2P (the patient pays).

**Faction stipends:** Weekly payroll from faction treasury. Amount varies by faction and rank.

**Weapon sell-back:** Selling weapons to NPC vendors returns 25–50% of purchase price. Bargain check affects the price.

---

## 8. Credit Sinks (Where Money Goes)

| Sink | Cost | Frequency |
|------|------|-----------|
| Ship fuel (launch) | 60–100 cr | Per launch |
| Ship fuel (hyperspace) | 100–600 cr | Per jump |
| Docking fees | 19–38 cr (base 25, scaled by zone security) | Per landing |
| Weapon repair | 50–250 cr | When condition degrades |
| NPC weapon purchases | 25–7,000 cr | One-time per weapon |
| NPC crew wages | 30–1,000 cr | Every 4 hours per crew |
| Vendor droid | 2,000–12,000 cr | One-time purchase |
| Vendor listing fee | 1–2% | Per sale |
| Housing deposit | 500 cr | One-time |
| Housing rent | 50 cr/week (Tier 1) | Weekly |
| Smuggling fines | 25–50% of job reward (tiered) | On patrol failure |
| Sabacc house rake | 10% of pot | Per game |

**Weapon durability** creates an ongoing repair cycle — every attack degrades weapon condition by 1 point (lightsabers by 2). When condition hits 0, the weapon is broken and needs repair from an NPC. This is a well-designed lifecycle sink.

---

## 9. The Bargain Skill

Many economic transactions involve a **Bargain skill check** — an opposed roll between your Bargain skill and the NPC vendor's bargain dice. The margin determines a price modifier:

- ±2% per 4 points of margin, capped at ±10%
- Critical success doubles the modifier (still capped)
- Fumble inverts the modifier and guarantees at least 2% swing against you

When buying, a positive margin means a cheaper price. When selling, it means a higher sell price. A skilled haggler saves/earns 10% on every transaction.

---

## 10. Faction Commissary

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
+commissary sell <key>       — Sell a commissary item back (50% refund)
```

Items bought via commissary behave identically to the same items acquired elsewhere. The `key` is shown in the catalog listing.

---

## 11. Creature Spoils

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

Small nuisance creatures (worrt, shredder bat) yield nothing — the field-dressing system rewards big-predator kills by contrast. (The Spor Crawler in the table above *is* a real harvest target, DC 10 — don't let the name fool you.)

**Economy note:** Spoils are **not credits**. They're crafting resources (organic or chemical) that go into the same inventory pool as wilderness-harvested materials. They're not bought by NPC vendors directly; they either go into your crafting queue or sell P2P via a vendor droid buy-order. This means spoils add no inflation to the credit economy — they feed directly into crafting demand.

Quality is intentionally capped below T5 minimum (75), so creature spoils can supply basic and intermediate recipes but never replace the dedicated wilderness harvest economy for high-end materials.

---

## 12. Economy Commands Quick Reference

| System | Commands |
|--------|---------|
| **Missions** | `+mission/board`, `+mission/accept <id>`, `+mission/view`, `+mission/complete`, `+mission/abandon` |
| **Bounties** | `+bounty/board`, `+bounty/claim <id>`, `+bounty/view`, `+bounty/track`, `+bounty/collect` |
| **Smuggling** | `+smuggle/board`, `+smuggle/accept <id>`, `+smuggle/view`, `+smuggle/deliver`, `+smuggle/dump` |
| **Trading** | `market`, `buy <good> <qty>`, `sell <good>` |
| **Commissary** | `+commissary`, `+commissary buy <key>`, `+commissary sell <key>` |
| **Hunting** | `+hunting` (kill tally + daily take), `+title wear <key>` (wear an earned hunter title) |
| **General** | `+credits` (check balance), `sell` (sell weapons to NPC), `+repair` (repair an equipped weapon at an NPC) |

---

