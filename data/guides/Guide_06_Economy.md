# SW_MUSH Detailed Systems Guide #6
# Economy: Missions, Bounties, Smuggling & Trade

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Economic Design Targets

### Player Rules

The economy is designed around these targets for an active player:

| Metric | Target |
|--------|--------|
| **Earning rate** | 500–2,000 credits/hour |
| **Living expenses** | 200–400 credits/hour |
| **Net accumulation** | 300–1,600 credits/hour |

The spread is intentional — a cautious player doing delivery missions earns less but risks nothing. A smuggler running raw spice earns 10x more but can lose half the reward to Imperial fines. Skill, risk tolerance, and time invested all affect income.

### 🔧 Developer Internals

**Design doc:** `economy_design_v02-1.md`. Full audit in `economy_audit_v1.md`.

The economy audit identified six structural vulnerabilities, the most critical being that trade goods are a "solved game" (static price multipliers can theoretically generate 120x the design target). The audit recommends dynamic supply pools, Bargain skill gates on bulk purchases, and per-planet inventory limits. These are documented but not yet implemented.

---

## 2. Mission Board

### Player Rules

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

### 🔧 Developer Internals

**File:** `engine/missions.py` (~856 lines):

**`MissionType` enum** (lines 46–62): 14 types including 4 space types (PATROL, ESCORT, INTERCEPT, SURVEY_ZONE).

**`MissionStatus` enum**: AVAILABLE, ACCEPTED, COMPLETE, EXPIRED, FAILED.

**`PAY_RANGES` dict** (lines 109–127): Min/max pay per type. Space missions pay 300–2,500 cr.

**Board management:**
- `BOARD_MIN = 5`, `BOARD_MAX = 8`
- `REFRESH_SECONDS = 1800` (30 minutes)
- `MISSION_TTL = 3600` (1 hour unclaimed)
- `MISSION_ACTIVE_TTL = 7200` (2 hours accepted)
- Board maintains the AVAILABLE pool and replaces completed missions immediately

**Mission generation:** Procedural — picks random type, generates reward within range, assigns destination rooms based on type, creates flavor text. Space missions reference specific zone targets from `_PATROL_ZONES`, `_SURVEY_ZONES`, `_INTERCEPT_ZONES`, `_ESCORT_ROUTES`.

**Completion skill check:** Routes through `skill_checks.py::resolve_mission_completion()` which calls `perform_skill_check()`. Difficulty scales with reward via `mission_difficulty()` (intermediate values 8–21, not the canonical R&E ladder).

**File:** `parser/mission_commands.py` (~600 lines): 5 commands — missions, mission accept, mission info, mission complete, mission abandon.

---

## 3. Bounty Board

### Player Rules

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

**Target archetypes:** Thugs, smugglers, bounty hunters, scouts, stormtroopers, Imperial officers — procedurally generated with appropriate stats and equipment for their tier.

### 🔧 Developer Internals

**File:** `engine/bounty_board.py` (~554 lines):

**`BountyTier` enum** (lines 53–58): EXTRA through SUPERIOR.

**`TIER_WEIGHTS` dict** (lines 70–76): Extras are 5x more common than Superiors.

**`FUGITIVE_ARCHETYPES`** (lines 79–82): 6 archetype strings that make sense as fugitives.

**Board management:**
- `BOARD_SIZE = 4`, `BOARD_MIN = 2`
- `REFRESH_SECONDS = 2700` (45 minutes)
- `BOUNTY_TTL = 10800` (3 hours unclaimed)
- `CLAIMED_TTL = 14400` (4 hours claimed)

**Target spawning:** NPCs are actually spawned in the world using `engine/npc_generator.py`. They're placed in non-obvious rooms (avoids docking bays). Their stats match the tier difficulty.

**Completion:** Requires the target NPC to be killed or incapacitated. The combat system has a bounty kill hook that triggers when a bounty target is defeated.

**File:** `parser/bounty_commands.py` (~410 lines): 5 commands.

---

## 4. Smuggling

### Player Rules

Smuggling is the high-risk, high-reward income path. You pick up contraband cargo from criminal contacts and deliver it to a dropoff point, hoping to avoid Imperial patrols along the way.

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

### 🔧 Developer Internals

**File:** `engine/smuggling.py` (~625 lines):

**`CargoTier` IntEnum** (lines 102–106): GREY_MARKET(0), BLACK_MARKET(1), CONTRABAND(2), SPICE(3).

**`ROUTE_TIERS` dict** (lines 72–80): 5 route configurations with tier, destination planet, pay override, and patrol chance.

**`PLANET_PATROL_FREQUENCY` dict** (lines 84–89): Per-planet arrival intercept probability. Corellia = 0.60 (Core World).

**Board management:**
- `BOARD_SIZE = 5`, `BOARD_MIN = 3`
- `REFRESH_SECONDS = 2700` (45 minutes)
- `JOB_TTL = 7200` (2 hours unclaimed)
- `JOB_ACTIVE_TTL = 14400` (4 hours accepted)

**Patrol resolution:** Random check against `TIER_PATROL_CHANCE[tier]`. If triggered, player rolls Con or Sneak vs. `PATROL_DIFFICULTY[tier]`. Failure: cargo confiscated, fine = `FINE_FRACTION (0.50) × reward`.

**File:** `parser/smuggling_commands.py` (~480 lines): 5 commands.

---

## 5. Cargo Trading

### Player Rules

(Detailed in Guide #5, section 8 — summarized here for completeness.)

Buy-low-sell-high speculative trading between planets. 8 trade goods with planet-specific source (50% price) and demand (200% price) multipliers. A Bargain skill check modifies the price by ±10%. Cargo stored in ship's hold.

**Key vulnerability (from audit):** Static price multipliers with no supply limits mean a single run of Luxury Goods from Corellia to Tatooine in a full YT-1300 generates ~240,000 cr/hr — 120x the design target. This is a known issue awaiting dynamic supply pools.

---

## 6. Other Income Sources

### Player Rules

**Entertainment:** The `perform` command in cantina zones rolls a Perception-based check. Success earns credits based on performance quality. A niche but risk-free income.

**Medical healing:** Player-to-player healing via `heal <player>` / `healaccept`. The healer rolls First Aid. Credits are exchanged P2P (the patient pays).

**Faction stipends:** Weekly payroll from faction treasury. Amount varies by faction and rank.

**Weapon sell-back:** Selling weapons to NPC vendors returns 25–50% of purchase price. Bargain check affects the price.

---

## 7. Credit Sinks (Where Money Goes)

### Player Rules

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

### 🔧 Developer Internals

**From economy audit:** ~50% of designed sinks are not yet wired. Missing: transaction tax (5%), recurring daily docking fees, ammo costs, medical NPC treatment costs, crafting material NPC vendors. The most damaging gap is free crafting materials via the `survey` command (zero input cost, output worth hundreds/thousands).

**What's working well (per audit — don't touch):** Weapon durability/repair cycle, vendor droid listing fees, crew wages, smuggling risk/reward.

---

## 8. The Bargain Skill

### Player Rules

Many economic transactions involve a **Bargain skill check** — an opposed roll between your Bargain skill and the NPC vendor's bargain dice. The margin determines a price modifier:

- ±2% per 4 points of margin, capped at ±10%
- Critical success doubles the modifier (still capped)
- Fumble inverts the modifier and guarantees at least 2% swing against you

When buying, a positive margin means a cheaper price. When selling, it means a higher sell price. A skilled haggler saves/earns 10% on every transaction.

### 🔧 Developer Internals

**File:** `engine/skill_checks.py` — `resolve_bargain_check()` (lines 297–428). Both player and NPC roll through `roll_d6_pool()`. NPC bargain dice auto-detected from room NPCs; falls back to 3D generic vendor. Result dict includes `adjusted_price`, `price_modifier_pct`, `margin`, `critical`, `fumble`, and narrative `message`.

---

## 9. Economy Commands Quick Reference

| System | Commands |
|--------|---------|
| **Missions** | `missions`, `mission accept <#>`, `mission info <#>`, `mission complete`, `mission abandon` |
| **Bounties** | `bounties`, `bounty claim <#>`, `bounty info <#>`, `bounty collect`, `bounty abandon`, `bountytrack` |
| **Smuggling** | `smugjobs`, `smugaccept <#>`, `smugjob`, `smugdeliver`, `smugdump` |
| **Trading** | `market`, `buy <good> <qty>`, `sell <good>` |
| **General** | `credits` (check balance), `sell` (sell weapons to NPC), `repair` (repair weapons at NPC) |

---

## 10. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/missions.py` | ~856 | 14 mission types, board management, generation, completion |
| `engine/bounty_board.py` | ~554 | 5 bounty tiers, target spawning, tracking, collection |
| `engine/smuggling.py` | ~625 | 4 cargo tiers, 5 route tiers, patrol encounters, fines |
| `engine/trading.py` | ~335 | 8 trade goods, planet price tables, cargo hold |
| `engine/skill_checks.py` | ~590 | Bargain, mission completion, repair resolvers |
| `parser/mission_commands.py` | ~600 | 5 mission commands |
| `parser/bounty_commands.py` | ~410 | 5 bounty commands |
| `parser/smuggling_commands.py` | ~480 | 5 smuggling commands |
| `parser/builtin_commands.py` | ~1,872 | sell, repair, credits commands |
| `economy_design_v02-1.md` | — | Economy design document |
| `economy_audit_v1.md` | — | Full economy audit with 6 vulnerability findings |

**Total economy system:** ~3,845 lines of engine code + ~1,490 lines of parser code + ~335 lines of trading = ~5,670 lines dedicated to the credit economy.

---

*End of Guide #6 — Economy*
*Next: Guide #7 — Crafting*
