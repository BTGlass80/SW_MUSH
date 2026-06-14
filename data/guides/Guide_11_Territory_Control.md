---
category: galaxy
order: 3
summary: "How factions and organizations claim, hold, and contest territory across the galaxy."
tags: ["territory", "control", "faction", "claim", "war", "contest"]
---

# Territory Control

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

Territory Control is an influence-based system that lets player organizations claim and hold rooms in contested and lawless zones. Your faction earns influence through member activity — combat, missions, investment — and once you cross key thresholds, you can claim rooms, station guards, and generate passive income.

This is the endgame organizational content: it turns abstract faction membership into concrete territorial power with visible map presence.

---

## 2. Influence

Each organization tracks an **influence score** (0–150) per zone. Influence determines what your faction can do in that zone:

| Threshold | Score | Effect |
|-----------|-------|--------|
| **Presence** | 25+ | Org name appears in `look` output |
| **Foothold** | 50+ | Can claim rooms in this zone |
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

**Influence decay:** If no org members are present in a zone for 48 hours, influence decays at −5 per day. Active presence resets the timer. This means you have to maintain a real presence — you can't just invest once and walk away.

---

## 3. Room Claiming

Once your org has **50+ influence** (Foothold threshold) in a zone, rank 3+ members can claim rooms:

```
faction claim                — Claim the room you're standing in
faction unclaim               — Release a claimed room
faction territory             — View all your org's claims
```

**Claiming rules:**
- Must be standing in the room to claim
- Room must be in a contested or lawless zone (secured = Republic-controlled, can't claim)
- Maximum 3 claims per zone, 10 total per org
- Costs 5,000 credits from org treasury (one-time)
- Weekly maintenance: 200 credits per room from treasury
- Player-owned housing can't be claimed
- Existing claims can't be overridden (must be contested — see Drop 6D)

**What claimed rooms get:**
- Lawless rooms are treated as **contested** for org members (PvP consent protection on your own turf)
- A visible claim tag in `look` output
- Can station a guard NPC (see section 4)
- Generate passive resource income (see section 5)

---

## 4. Guard NPCs

Rank 3+ members can station a guard NPC in a claimed room:

```
faction guard station          — Station a guard (500 credits one-time + 100 cr/week upkeep)
faction guard dismiss          — Remove a guard
```

Guards are faction-flavored NPCs with appropriate stats, descriptions, and equipment:
- **Republic:** Clone Trooper with DC-15 rifle, white armor, 5D Blaster
- **Separatist:** Alliance sentry with A280 rifle, 4D+2 Blaster
- **Hutt:** Gamorrean enforcer with vibroaxe, 5D Brawling
- **BH Guild:** Sharp-eyed hunter with heavy blaster, 5D+1 Blaster

Guards are **aggressive** combat NPCs — they'll attack hostile intruders in the claimed room. They add weekly upkeep (100 cr) on top of the room's base maintenance (200 cr).

---

## 5. Resource Nodes (Passive Income)

Claimed rooms generate passive resources via a daily tick, scaled by zone security and influence tier:

| Security | Influence Tier | Daily Yield |
|----------|---------------|-------------|
| Contested | Foothold (50+) | 50–150 credits |
| Contested | Dominant (75+) | 100–300 credits + 1–2 metal |
| Contested | Control (100+) | 150–400 credits + 1–2 metal + 1 rare |
| Lawless | Foothold (50+) | 75–200 credits |
| Lawless | Dominant (75+) | 150–400 credits + 2–4 metal + 1–2 chemical |
| Lawless | Control (100+) | 250–600 credits + 2–4 metal + 2–4 chemical + 1–2 rare |

Resources go into org shared storage. Lawless zones yield more than contested — higher risk, higher reward.

---

## 6. Display Integration

Territory influence is visible throughout the game:

**In `look` output:** When any org has 25+ influence in your zone, a presence line appears:
```
  Republic patrols and clone trooper presence are felt here.
```

For claimed rooms, a claim tag appears:
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

---

## 8. Commands Quick Reference

| Command | Description |
|---------|-------------|
| `faction influence` | View influence across all zones |
| `faction invest <amount>` | Invest treasury credits into zone influence |
| `faction claim` | Claim the room you're in |
| `faction unclaim` | Release a claimed room |
| `faction territory` | View all org claims |
| `faction guard station` | Station a guard NPC (500 cr + 100 cr/week) |
| `faction guard dismiss` | Remove a guard NPC |

---

