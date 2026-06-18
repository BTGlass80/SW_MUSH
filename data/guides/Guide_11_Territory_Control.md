---
category: galaxy
order: 3
summary: "How factions and organizations claim, hold, and contest wilderness regions across the galaxy."
tags: ["territory", "control", "faction", "claim", "war", "contest"]
---

# Territory Control

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — June 2026**
**Guide Version 2.0**

---

## 1. Overview

Territory Control is an influence-based system that lets player organizations claim and hold **wilderness regions** across the galaxy. Your faction earns influence through member activity — combat, missions, investment — and once you cross key thresholds, you can claim regions, deploy garrison troops, and generate passive income.

This is the endgame organizational content: it turns abstract faction membership into concrete territorial power with visible map presence. Claimed regions can be challenged by rival factions through an automated **Region Contest** system — ownership changes hands only through a seven-day siege culminating in a direct fight.

---

## 2. Influence

Each organization tracks an **influence score** (0–150) per zone. Influence determines what your faction can do in that zone:

| Threshold | Score | Effect |
|-----------|-------|--------|
| **Presence** | 25+ | Org name appears in `look` output |
| **Foothold** | 50+ | Can claim wilderness regions in this zone |
| **Dominance** | 75+ | Security upgrade + passive income from claims |
| **Control** | 100+ | Full zone branding |

**Earning influence:**

| Action | Influence Gained |
|--------|-----------------|
| Member present in zone (hourly) | +1 per member |
| Kill NPC in zone | +2 |
| Complete mission/bounty/smuggling in zone | +5 |
| PvP victory in zone | +15 |
| Invest 1,000 credits from treasury | +10 |

**Investment:** `faction invest <amount>` spends org treasury credits to boost influence. Minimum 1,000 cr, maximum 10,000 cr per investment. Requires rank 3+.

**Influence decay:** If no org members are present in a zone for 48 hours, influence decays at −5 per day. Active presence resets the timer. You can't just invest once and walk away — maintaining territory means maintaining presence.

---

## 3. Region Claiming

Once your org has **50+ influence** (Foothold threshold) in a zone, rank 3+ members can claim a wilderness region:

```
faction claim                — Claim the wilderness region you're standing in
faction unclaim               — Release your org's claim on this region
faction territory             — View all your org's claimed regions and active contests
```

**Claiming rules:**
- Must be standing in a wilderness room inside the target region
- Region must be in a contested or lawless zone (Republic-secured zones can't be claimed)
- No per-org cap — a faction can hold every wilderness region on the server if it can defend them all
- Costs 5,000 credits from org treasury (one-time claim fee)
- Weekly maintenance: 2,000 credits per region + 1,000 credits garrison upkeep
- City-map rooms are not claimable (travel into the wilderness first)

**What claiming a region does:**
- Lawless regions are treated as **contested** for your org members (PvP consent protection on your turf)
- A visible claim tag appears on all rooms in the region (`look`)
- A garrison of 5 faction-appropriate guards auto-deploys in the region's landmark room
- The region starts generating passive credit income (see §5)
- Rival factions at Foothold influence can trigger a Region Contest to challenge ownership (see §7)

---

## 4. Region Garrison

When you claim a region, **5 garrison guards auto-deploy** in the region's central landmark room. No manual placement needed.

```
faction guard remove          — Dismiss the garrison from this room
```

Guards are era-appropriate combat NPCs matched to your faction:

| Faction | Guard Type | Weapon | Key Skill |
|---------|-----------|--------|-----------|
| **Galactic Republic** | Republic Garrison Guard (Clone Trooper, Phase II armor) | DC-15A Blaster Rifle | 5D Blaster |
| **CIS/Separatists** | CIS Battle Droid (B1 Battle Droid) | E-5 Blaster Rifle | 4D Blaster |
| **Hutt Cartel** | Cartel Enforcer (Gamorrean) | Vibroaxe | 5D Brawling |
| **Bounty Hunters' Guild** | Guild Watchman | Heavy Blaster Pistol | 5D+1 Blaster |

Garrison guards are **aggressive** combat NPCs — they attack hostile intruders in the landmark room. The 1,000 cr/week garrison upkeep is charged alongside the 2,000 cr/week base maintenance.

---

## 5. Passive Income

Claimed regions generate passive credit income via a daily tick:

| Region Security | Daily Credit Yield |
|----------------|-------------------|
| **Contested zone** | 50–150 credits |
| **Lawless zone** | 100–250 credits |

Credits go directly into your org treasury. Lawless zones yield more — higher risk, higher reward. A contested-zone region barely covers its weekly maintenance; lawless zones pay for themselves and then some.

Weekly cost summary per region:
- Base maintenance: 2,000 cr/week
- Garrison upkeep: 1,000 cr/week
- **Total: 3,000 cr/week** — budget accordingly

---

## 6. Display Integration

Territory influence is visible throughout the game:

**In `look` output:** When any org has 25+ influence in your zone, a presence line appears:
```
  Republic patrols and clone trooper presence are felt here.
```

For claimed regions, a claim tag appears in every room of that region:
```
  [CLAIMED: Galactic Republic]
```

**In `faction influence`:** An influence dashboard with per-zone progress bars:
```
── Territory Influence ──
  Spaceport District              ████████████░░░░░░░░  65/150 [FOOTHOLD]
  Cantina District                ██████░░░░░░░░░░░░░░  30/150 [PRESENCE]
  Jundland Wastes                 ████████████████░░░░  95/150 [DOMINANT]

  Thresholds: 25 Presence · 50 Foothold · 75 Dominant · 100 Control
```

**Active contests** are displayed under your influence summary when `faction influence` or `faction contest` is run.

---

## 7. Region Contests

Claimed regions can be challenged. The system is **automatic** — no manual declaration needed.

**How contests trigger:**

When a challenger org reaches Foothold influence (50+) in a zone containing a rival's claimed region, and the challenger's influence in that zone reaches **75% of the defender's**, the engine automatically declares a Region Contest. Both factions are notified.

**Contest timeline (7 days total):**

- **Days 1–7 (minus the final 4 hours):** Accumulation phase. The contest is declared and active, but play continues normally. Both factions should maximize presence, kills, and missions in the zone to build influence advantage going into the fight.
- **Final 4 hours of day 7 — Culminating Fight:** A **Region Anchor NPC** spawns in the region's landmark room. This is the climactic engagement. The Anchor's strength scales with the defender's influence (high influence = tougher fight). The challenger must find and kill the Anchor before the 4-hour window closes.

**Outcomes:**
- **Challenger kills the Anchor:** Region changes hands. The former owner's influence in that zone drops by 25. The challenger can immediately garrison the region.
- **Anchor survives the window:** Defender wins. The challenger's influence drops by 25. The challenger cannot contest that region again for **14 days** (cooldown).

**Checking contest status:**
```
faction contest               — View all active contests for your org
faction territory             — View claimed regions and contest status
```

**Strategy notes:**
- Defending factions should invest heavily during the accumulation phase to raise Anchor HP.
- Challengers get a 14-day cooldown after a loss — don't rush in underprepared.
- Both sides earn normal influence for zone activity during the contest window; presence matters throughout.

---

## 8. Resource Outlook

`faction resource_outlook` shows the weekly resource quality multipliers for your org's claimed regions. This is the crafter's news feed — it tells you which of your regions have the best material conditions this week, driving smarter harvest scheduling.

Independent players can also run this command to see all regions (read-only context).

```
faction resource_outlook      — View weekly resource quality across your claimed regions
```

---

## 9. Commands Quick Reference

| Command | Description |
|---------|-------------|
| `faction influence` | View influence across all zones (alias: `faction territory`) |
| `faction invest <amount>` | Invest treasury credits into zone influence (min 1,000 cr) |
| `faction claim` | Claim the wilderness region you're standing in |
| `faction unclaim` | Release your org's claim on this region |
| `faction guard remove` | Dismiss the garrison from the current room |
| `faction contest` | View active Region Contests for your org |
| `faction resource_outlook` | View weekly resource quality for claimed regions |

---
