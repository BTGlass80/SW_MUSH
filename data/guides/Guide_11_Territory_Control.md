---
category: galaxy
order: 3
summary: "How factions and organizations claim, hold, and contest wilderness regions across the galaxy."
tags: ["territory", "control", "faction", "claim", "war", "contest"]
---

# Territory Control

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — June 2026**
**Guide Version 3.0**

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
| Kill an NPC in a wilderness region | +2 |
| Complete a mission / bounty / smuggling run in a wilderness region | +5 |
| PvP victory in a wilderness region | +15 (loser's org loses −5) |
| Invest 1,000 credits from treasury | +10 |

> **The wilderness rule (important):** Combat, missions, and PvP only build influence when they happen in a **wilderness region** — a room with a region tag. The same kill or mission completed in a **city map room** (a spaceport, cantina, or street) earns its normal credits, reputation, and CP but grants **zero influence**. Territory is won in the wild, not downtown. Presence (the hourly +1 per member) and treasury investment count anywhere in a contestable zone.

**Investment:** `faction invest <amount>` spends org treasury credits to boost influence. Minimum 1,000 cr, maximum 10,000 cr per investment. Requires rank 3+. (Investment is refused in Republic-secured zones — you can't buy a foothold where the Republic holds the ground.)

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
- A garrison of 5 faction-appropriate guards auto-deploys across the region's landmark rooms (see §4)
- Your org gains a one-time **+20 influence** in the parent zone, cementing the foothold
- The region starts generating passive credit income (see §5)
- Rival factions at Foothold influence can trigger a Region Contest to challenge ownership (see §7)

---

## 4. Region Garrison

When you claim a region, **5 garrison guards auto-deploy**, scattered across the region's landmark rooms. There is no manual placement and no manual dismissal — the garrison is a property of ownership. It deploys the moment you claim, and it dismisses automatically when you `faction unclaim` the region or when treasury runs short of upkeep (see §5). (A small region with fewer than five landmarks simply stacks more than one guard in a room.)

Guards are era-appropriate combat NPCs matched to your faction:

| Faction | Guard Type | Weapon | Key Skill |
|---------|-----------|--------|-----------|
| **Galactic Republic** | Republic Garrison Guard (Clone Trooper, Phase II armor) | DC-15A Blaster Rifle | 5D Blaster |
| **CIS / Separatists** | CIS Battle Droid (B1 Battle Droid) | E-5 Blaster Rifle | 4D+1 Blaster |
| **Jedi Order** | Temple Sentinel | Lightsaber | 5D Dodge / 4D+1 Brawling |
| **Hutt Cartel** | Cartel Enforcer (Gamorrean) | Vibroaxe | 5D Brawling |
| **Bounty Hunters' Guild** | Guild Hunter | Heavy Blaster Pistol | 5D+1 Blaster |

Garrison guards challenge non-members on sight and fight anyone who threatens the territory. The 1,000 cr/week garrison upkeep is charged alongside the 2,000 cr/week base maintenance.

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

**When the treasury runs dry:** Upkeep is charged weekly. If your treasury can't cover a region's full 3,000 cr, the engine cuts costs in stages rather than silently draining you:

1. **Garrison dismissed first.** The guards stand down (saving 1,000 cr/week) and the org is notified. The region stays owned, now at 2,000 cr/week.
2. **Region lapses.** If even the 2,000 cr base is unaffordable, the region returns to un-owned, the org is notified, and any rival can move in. There is no partial refund — a lapsed region is simply lost.

Hold only what you can pay for. An over-extended faction that claims more turf than its treasury supports will watch its garrisons evaporate and its borders collapse on the next maintenance tick.

---

## 6. Display Integration

Territory influence is visible throughout the game:

**In `look` output:** When any org has 25+ influence in your zone, a presence line appears:
```
  Republic patrols and clone trooper presence are felt here.
```

**In the web client's HUD:** When you stand in an owned wilderness region, the client shows a **territory indicator** naming the controlling faction:
```
  Galactic Republic — controlled territory
```
If a Region Contest is active there, the HUD also flags the challenger, defender, and time remaining (and highlights the culminating-fight phase). This is web-first; the Telnet client shows the zone presence line but not the per-region ownership banner.

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

- **Days 1–7 (minus the final 4 hours):** Accumulation phase. The contest is declared and active, but play continues normally. Both factions should maximize wilderness kills, missions, and PvP in the contested region to build influence advantage going into the fight. **Influence earned in the contested region is doubled (2×) for both contestants during the contest** — this is the window to pull ahead. If the defending faction is *outnumbered* (fewer registered members than the challenger), the defender earns an additional **1.5×** on top of the doubling, an anti-zerg cushion so a smaller faction can still hold its ground.
- **Final 4 hours of day 7 — Culminating Fight:** A **Region Anchor NPC** spawns at one of the region's landmarks. This is the climactic engagement. The Anchor's strength scales with the **defender's** influence (high influence = a tougher, higher-HP Anchor). Counter-intuitively, a **challenger** who has piled up a large influence lead (above 100) causes the defender to field **extra reinforcement NPCs** alongside the Anchor — the bigger the challenger's advantage, the more bodies guard the Anchor. The challenger must find and kill the Anchor before the 4-hour window closes; reinforcements must be fought through, but only the Anchor's death wins the region.

**Outcomes:**
- **Challenger kills the Anchor:** The region changes hands immediately. Ownership transfers to the challenger, the old garrison is dismissed, and a fresh garrison auto-deploys for the new owner. The former owner's influence in that zone drops by 25 and they go on a **14-day cooldown** — they cannot re-challenge the region they just lost until it expires.
- **Anchor survives the window:** Defender wins. The challenger's influence drops by 25 and they cannot contest that region again for **14 days** (cooldown).

The cooldown is symmetric: whichever side *loses* eats the 25-influence penalty and the 14-day lockout on that region.

**Checking contest status:**
```
faction contest               — View all active contests for your org
faction territory             — View claimed regions and contest status
```

**Strategy notes:**
- Defending factions should invest heavily and stay active during the accumulation phase: every point of defender influence raises Anchor HP, and the doubled (2×) contest gain makes that lead easy to build.
- A smaller defending faction shouldn't despair — the outnumbered-defender 1.5× bonus is designed to let you out-pace a larger challenger if you stay present in the region.
- Challengers should weigh the reinforcement math: running up a runaway influence lead before the fight summons *more* defenders to the Anchor. Sometimes a lean, decisive strike beats a maximal one.
- Whoever loses eats a 14-day cooldown on that region — don't rush in underprepared.

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
| `faction claim` | Claim the wilderness region you're standing in (garrison auto-deploys) |
| `faction unclaim` | Release your org's claim on this region (garrison auto-dismisses) |
| `faction contest` | View active Region Contests for your org |
| `faction resource_outlook` | View weekly resource quality for claimed regions |

---
