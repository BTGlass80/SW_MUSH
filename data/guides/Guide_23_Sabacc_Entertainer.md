---
category: economy
order: 4
summary: "Gambling tables, performance gigs, and earning credits through entertainment skills."
tags: ["sabacc", "gambling", "entertainer", "perform", "cards", "music"]
---

# Sabacc & Entertainer

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This guide covers the **cantina-economy systems** — sabacc gambling and the entertainer's perform mechanic. Both are room-bound (cantinas only), both pay credits for cantina-zone activity, and both serve as the social layer's economic engine.

If you only have ten minutes, read **§1 The Two Systems** and **§3 The Sabacc Walkthrough**. Sabacc is the more universal system (anyone can gamble); the entertainer perform mechanic is a specialized character build.

This is a new guide. There was no earlier version.

---

## 1. The Two Systems

**Sabacc** is the in-game gambling. Any player in a cantina zone can play a hand against the house dealer. You bet 50-2,000 cr, the dice resolve, and credits move. It's the "cantina interlude" — you take a break from missions, you play a few hands, you win or lose. Pure economic exchange with social cover.

**Perform** is the entertainer's income channel. If you have a high Persuasion (or Musical Instrument skill), you can perform for credits in cantina zones. Successful performances pay 50-500 cr per shot. Active entertainers can make 1,500-3,000 cr per hour of cantina presence — comparable to mid-tier mission income with much lower risk and a different social-RP texture.

Both systems are **opt-in** — you don't have to gamble; you don't have to perform. But for characters whose identity involves the cantina (smugglers, Hutt aficionados, social characters, professional entertainers), these are core income channels.

---

## 2. Where Both Systems Work

Both sabacc and perform require you to be in a **cantina zone room**. Not every room with cantina ambiance qualifies — the system checks for the explicit "cantina" zone designation.

Cantina zones across the galaxy include:
- **Mos Eisley Cantina** (the most iconic).
- **Coruscant cantina districts** (multiple options in the urban sprawl).
- **Nar Shaddaa cantinas** (the underworld variety).
- **Kessel mining-station bars** (rough, isolated).
- **Corellian space-port cantinas** (more refined, Republic-aligned).
- **Smaller regional cantinas** in outpost settlements.

If `sabacc` or `perform` doesn't work in a room, you're not in a cantina zone. Check `look` or the zone tag.

---

## 3. The Sabacc Walkthrough

```
sabacc [bet]
```

You sit at a sabacc table and play a hand against the **house dealer NPC**. The bet defaults to 100 cr if you don't specify. Bet range: 50 cr minimum, 2,000 cr maximum (doubled during the Cantina Brawl world event, see §6).

### The mechanics

A single hand resolves in one exchange:

1. **Bet validation.** Your wallet has the cr; you're in a cantina; you're not on cooldown.
2. **Player rolls Gambling skill** (with wild die). This is the standard skill-check mechanic (Guide #1).
3. **Dealer rolls 3D Gambling, no wild die.** The dealer is steady (not lucky); the house never crits or fumbles.
4. **Compare totals.** Higher total wins. **Ties go to the dealer** (the house edge).

### Outcomes

| Outcome | Pay |
|---|---|
| **Critical success** (wild die exploded) | Bet × 2, no house cut (rare bonus) |
| **Win** | Bet × 0.9 (10% house cut) |
| **Tie** | Loss (dealer wins ties) |
| **Loss** | Bet lost |
| **Fumble** | Bet lost + flavor "you bomb out" |

The 10% house cut applies to **winnings** — your stake comes back plus 90% of the winnings. So a 100 cr bet won pays you 190 cr (your 100 + 90 winning). A 1,000 cr bet won pays you 1,900 cr.

A critical success (wild die exploded) pays **double** — your bet comes back doubled with no house cut. A 100 cr bet with crit pays 200 cr.

### Cooldowns

- **After a win:** 5-minute cooldown.
- **After a loss:** 2-minute cooldown.

This prevents grind-style sabacc spam. You play a hand, you wait, you play again. Active players might cycle 3-5 hands per session in cantina time. Heavy gamblers cycle more.

### Strategic considerations

**The Gambling skill matters.** A 3D Gambling character with no specialization rolls 3D against the dealer's 3D. The dealer wins ties (house edge), so the player's expected value is slightly negative — they'll lose more often than win.

A 5D Gambling character with specialization (or a +1D Gambling bonus from equipment) tips the odds in the player's favor. **A serious gambler with 5D+ Gambling wins about 55% of hands** — small edge, but it compounds over many hands.

**Bet sizing matters.** Betting at the maximum (2,000 cr) makes wins big and losses big. Bet conservatively if you're testing your luck; bet aggressively if you're confident in your Gambling and the math.

**Don't chase losses.** The 2-minute cooldown after losses limits how fast you can compound a losing streak. Don't try to "win it back" by re-betting larger after a loss; the math doesn't favor that strategy. Take a break; come back fresh.

### When sabacc is worth it

For a 5D Gambling specialist:
- 5 hands per cantina session, averaging 500 cr bets.
- Win rate ~55%, ~45% loss rate.
- Average payout per win: 450 cr (after house cut).
- Average per session: (5 × 0.55 × 450) − (5 × 0.45 × 500) = 1,237 − 1,125 = **112 cr/session**

A modest income — but it's the *cantina presence* and the social texture that matters. Sabacc is rarely your main earning path; it's the texture of cantina life. Spacers, smugglers, and Hutt-aligned characters integrate it as part of their identity.

For a 3D non-specialist:
- Same 5 hands at 500 cr.
- Win rate ~45%, ~55% loss rate.
- Average per session: (5 × 0.45 × 450) − (5 × 0.55 × 500) = 1,012 − 1,375 = **−363 cr/session**

A consistent loss. Casual gamblers should accept that sabacc is **entertainment, not income** for them. The cost is the price of cantina-RP authenticity.

---

## 4. The Perform System

```
perform
```

A skill-check entertainment performance. You roll your **Persuasion** skill (or **Musical Instrument** if your character has it) against a difficulty of **10** (Easy). The result determines pay and audience reaction.

### Outcomes

| Result | Pay | Flavor |
|---|---|---|
| **Critical** (wild die exploded) | 250-500 cr | "A once-in-a-lifetime performance" |
| **Success** | 50-200 cr (scaled by margin) | Pleasant audience reaction |
| **Partial** (near-miss) | 25 cr | "Polite applause" |
| **Failure** | 0 cr | "Awkward silence" |

A skilled entertainer (4D+ Persuasion) almost always succeeds. The difficulty is 10 (Easy); a 4D character averages 14 on their roll. Failures are uncommon.

**Margin matters for pay**. The amount you get on a success is randomized but scales with how cleanly you passed. Roll of 12 vs. difficulty 10: 50 cr-ish payout. Roll of 25 vs. 10: 200 cr-ish payout. Crits jump to 250-500.

### Cooldowns

- **Success cooldown: 10 minutes** between successful performances.
- **Failure cooldown: 5 minutes** after an awkward-silence failure.

The 10-minute success cooldown is real. You can't grind perform every 30 seconds; it's a "performance every quarter hour" pace. Sustainable but not exploitable.

### Math

For a 5D Persuasion entertainer:
- Performances per hour: ~4-5 (allowing for the 10-minute cooldown between hits and some social-RP padding).
- Average pay per success: ~125 cr (varies; specialty performers get more).
- Per hour: ~500-625 cr.

For a 5D entertainer with a regular cantina presence (3 hours per session × 3 sessions per week = 9 hours/week), the income is 4,500-5,600 cr/week. Add the crits (occasional 250-500 cr payouts), and a dedicated entertainer makes a real living from this.

**Plus the morale aura** (see §5).

### When perform doesn't work

- **Outside cantina zones.** The system checks for cantina-zone designation; you can't perform in a private room or a non-cantina cantina-themed area.
- **Cooldown active.** Wait for the timer.
- **Insufficient skill.** Below 3D Persuasion, you'll fail often. Build the skill first.

---

## 5. The Morale Aura

A subtle but powerful feature: when you succeed at `perform`, you create a **morale aura** in the cantina that benefits other players.

### How the aura works

The performance roll's margin determines the aura's magnitude:

| Margin | Magnitude | Flavor |
|---|---|---|
| 1-4 (basic success) | 1 | "Pleasant background music" |
| 5-9 (good) | 2 | "An engaging performance lifts the mood" |
| 10-14 (excellent) | 3 | "A genuinely inspiring performance" |
| 15+ (heroic) | 5 | "A once-in-a-lifetime performance" |

The **magnitude** is the **difficulty reduction** applied by the aura to morale-flavored rolls (some Persuasion-type checks) in the same room. A magnitude-3 aura subtracts 3 from the difficulty of an applicable roll for the next 30 minutes.

For example: a 5D entertainer plays a heroic performance (magnitude 5 aura). In the same cantina, another player attempts a difficult Persuasion roll (difficulty 20) to convince an NPC. The aura reduces the effective difficulty to 15 (Moderate). The player makes the roll more easily because of the entertainer's performance.

### Duration

30 minutes per performance. If multiple entertainers perform consecutively, the auras can stack (depending on type and overlap rules).

### Why this matters

The aura turns the entertainer into a **support role**. A skilled entertainer in the cantina isn't just earning income — they're buffing the other characters in the room. Other players notice; they appreciate; the entertainer becomes valuable to the social scene beyond just being interesting RP.

In gameplay terms, a cantina with a steady entertainer presence is a **better social space**. Other characters' Persuasion attempts succeed more often. The cantina becomes lively, productive, and fun. The entertainer's craft has mechanical impact, not just narrative impact.

### Fatigue

If you spam perform repeatedly without breaks, the system applies **fatigue** — a small penalty to subsequent performance rolls. The intent is to prevent grind-perform exploitation while still rewarding sustained entertainer presence.

The fatigue window is 8 hours of no-perform — after 8 hours without performing, the fatigue counter resets.

---

## 6. The Cantina Brawl Event

One of the Director AI's world events (Guide #26) is the **Cantina Brawl** — a randomly-triggered event that fires in a cantina zone.

When a Cantina Brawl is active:

- **Sabacc max bet doubles** (2,000 cr → 4,000 cr).
- **Sabacc payouts double** for the duration.
- **Perform payouts double** for the duration.
- **NPC combat in the cantina** is more active.
- **The cantina is more "alive"** — bursts of activity, dramatic moments.

The event lasts 30-60 minutes (Director-determined). The doubled payouts make this **the peak earning window** for both sabacc players and entertainers. Active players in cantinas during a brawl can earn 2-3x their normal rate.

To know when a brawl is active, check `+news` (Guide #21). The event appears in the bulletin when it starts.

---

## 7. The Entertainer Profession

For players who want to build their character explicitly around the perform system, here are the strategic considerations.

### Build

- **Persuasion 5D+** is the core stat. The skill rolls drive performance success and pay.
- **Musical Instrument** as a specialization (5D+) is even better — characters with this skill use it instead of Persuasion, often with higher pools.
- **The Entertainers Guild** (Guide #10) provides the 20% CP discount on Persuasion advancement — significant savings over months.
- **Cantina-zone presence**. A cantina-aligned character spends 70% of their play time in cantinas. Be where the work is.

### Income economics

A 5D Persuasion entertainer (with Entertainers Guild membership for the CP discount):

- Active hours: 3 hours per session, 3 sessions per week = 9 hours/week.
- Performances per hour: 4-5.
- Average pay: 125 cr/success.
- Crit rate: ~5% (wild die exploded), paying 250-500.
- Weekly base income: ~4,500-6,000 cr.

Add **cantina-brawl bonuses** (typically 1-2 brawls per week affecting your sessions): 200-500 additional cr per brawl-affected hour.

**Total weekly income: 6,000-9,000 cr.** A real living. Comparable to mid-tier mission running, with much lower physical risk.

### The social weight

Beyond the income, entertainers have **social capital**. The cantina is where things happen; you're the constant in the cantina. You see everyone come and go. You hear conversations. You become a trusted figure in the cantina's culture. Faction agents come to you for information; nobles tip generously after good performances; the local Hutt notices you and offers a side opportunity.

This isn't a quest path; it's just the social position the system supports. Players who lean into entertainer identity build deep cantina-based networks over months.

---

## 8. The Worked Scenarios

Five concrete pictures.

**Scenario 1 — Casual cantina visit.** You stop by the Mos Eisley Cantina between missions. You play three hands of sabacc. Two wins (390 cr total after house cuts), one loss (100 cr). Net +290 cr for 15 minutes of cantina-RP time. Not big money, but you played a few hands like a real cantina regular. The fiction is intact.

**Scenario 2 — The lucky night.** You roll a crit on your first sabacc hand (200-cr bet doubles to 400 cr). You win the next two normal hands. Then you lose a fourth. Total: +700 cr in 25 minutes. The crit was the high point. You exit the table while ahead.

**Scenario 3 — The dedicated entertainer.** You're a Twi'lek dancer working the Mos Eisley Cantina. You spend two hours in the cantina performing. You roll perform 8 times across the two hours. Six successes (averaging 130 cr each = 780 cr), one crit (350 cr), one failure (0). Total income: 1,130 cr per session. Plus you've buffed the cantina's social atmosphere with several aura instances — other characters' Persuasion rolls trended better; they appreciate the cover.

**Scenario 4 — The cantina brawl peak.** You log in. The news shows: "Cantina brawl breaks out at Mos Eisley." The cantina has been declared a brawl zone for the next 45 minutes. You head over. You play 4 sabacc hands at 1,000 cr each (doubled max during brawl). You win 3, lose 1. With doubled payouts: (3 × 1,800) − 1,000 = 4,400 cr net. Plus you perform once during the brawl (320 cr, doubled to 640 cr). Total brawl-session income: 5,040 cr in 45 minutes. The brawl was the windfall night.

**Scenario 5 — The losing streak.** Your 3D Gambling character plays five hands at 200 cr each. You lose three in a row, win one (180 cr), lose one. Net: −620 cr. The math is honest — non-specialized gamblers lose long-term. You take the hit, move on, and stop playing sabacc as a serious income strategy. The cantina visit was still satisfying RP, but you accept that gambling isn't your earning path.

---

## 9. Common Pitfalls

**1. Trying to grind sabacc as income.** Cooldowns (5 min win, 2 min loss) cap your hourly rate. Even a winning streak can't be exploited fast enough to compete with active missioning. Sabacc is texture; missions are income.

**2. Underestimating the house edge.** Ties go to the dealer. A 3D player vs. a 3D dealer technically rolls the same expected value, but tie-goes-to-dealer makes the player's net expected value slightly negative. Train Gambling above 3D before gambling seriously.

**3. Performing in non-cantina rooms.** The perform check requires cantina-zone designation. If it fails with no error, you're not in a cantina. Check `look` for the zone tag.

**4. Ignoring the aura's value.** The morale aura is real mechanical buff to room-mates. If you're an entertainer, your perform's value isn't just the credits — it's the help you give other players' rolls. Tell them about it.

**5. Spamming perform.** The 10-minute cooldown plus the fatigue mechanic prevent exploitation. Space your performances; treat them as scenes, not button-mashing.

---

## 10. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `sabacc [bet]` | Play a hand of sabacc (50-2,000 cr bet, cantina only) |
| `perform` | Perform for credits in a cantina zone |

---

## 11. Numbers At A Glance

| Quantity | Value |
|---|---|
| Sabacc bet range | 50-2,000 cr (4,000 during Cantina Brawl) |
| Sabacc default bet | 100 cr |
| Sabacc house cut | 10% of winnings |
| Sabacc win cooldown | 5 minutes |
| Sabacc loss cooldown | 2 minutes |
| Sabacc dealer roll | 3D Gambling, no wild die |
| Sabacc tie | Dealer wins (house edge) |
| Sabacc crit payout | Bet × 2 (no house cut) |
| Perform difficulty | Easy (10) |
| Perform payout — Partial | 25 cr |
| Perform payout — Standard | 50-200 cr (scaled by margin) |
| Perform payout — Critical | 250-500 cr |
| Perform success cooldown | 10 minutes |
| Perform failure cooldown | 5 minutes |
| Perform fatigue window | 8 hours |
| Morale aura duration | 30 minutes |
| Morale aura magnitudes | 1 / 2 / 3 / 5 (difficulty reduction) |
| Cantina Brawl event duration | 30-60 minutes |
| Cantina Brawl bonus | All payouts × 2 |

---

## 12. A Final Word

Sabacc and perform are the **cantina layer** of the game's economy. They're not the most efficient ways to earn credits — missions and trade pay better. But they're the *thematically right* ways to earn credits if your character lives in cantinas, and the social side-effects they produce (cantina presence, audience appreciation, the morale aura) shape the cantina's culture.

For most characters, **sabacc is occasional indulgence** — a few hands while waiting for a contact, a celebratory hand after a big payout. It's the equivalent of a real-life trip to a casino with a small budget. Fun, narratively meaningful, not a primary income path.

For **dedicated entertainers**, the perform mechanic is a profession. Combined with the morale aura, the cantina presence, and the social-capital benefits, entertainers become valued figures in their cantinas. Over months, they build reputation and income; over years, they become legends of their local cantina.

If you're starting out and want to try the cantina layer: visit Mos Eisley Cantina. Play one hand of sabacc at 100 cr (just to feel the mechanics). If your character has Persuasion 3D+, try `perform`. You'll learn whether this layer fits your character's identity. If it doesn't, no harm done — you're back to missions. If it does, you've found a thread that will weave through your entire character's life.

That's the system at its best — an optional layer that rewards committed engagement and shapes character identity for those who lean in.

---

*End of Guide #23 — Sabacc & Entertainer*
