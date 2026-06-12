# SW_MUSH — Economy Audit v2
## Second-Pass Senior Economic Review
### April 28, 2026 · Opus 4.7 Architecture Session

---

## Executive Summary

The mechanics that were marquee weaknesses in the v1 audit (April 2026) have been put right with care. Trade goods now have supply pools, demand depression, and a thoughtful volume premium. Mission completion routes through skill checks with partial pay. The P2P cap is implemented with a race-safe accept-time recheck (real defensive engineering, not just a happy-path check). Resource floors exist. Sabacc has a sensible rake. The credit log and `@economy` dashboard ship.

What's left is a different class of problem. It's not that individual systems are broken — it's that the **economy as a whole still has the topology of a single-player game**: lots of well-tuned ways to *make* credits, very few ways to *destroy* them at the high end, and several places where the economic instruments report less than the full picture. Below the headline numbers there are five structural things to close before a population of 15+ active players gets to week 4, plus a half-dozen tuning issues that won't kill anything but are leaving value on the floor.

**Overall grade: B+.** That's a real grade — most MUSH economies are D-tier and most indie MMO economies are C. The reasons it isn't an A are below.

---

## Tier 1 — Structural Issues

### 1.1 The credit log is a half-truth, which makes the dashboard a half-truth

The `log_credit` infrastructure is good. The wiring is incomplete in a way that will silently mislead. By count, it's called from these sources:

> p2p_transfer · p2p_tax · trade_goods (buy + sell) · mission · bounty · smuggling · smuggling_fine · resource_vendor · docking_fee

What's missing is conspicuous: faction stipends, weapon repair, NPC weapon buy/sell, vendor droid escrow & listing fees, crew wages (a substantial sink — 30–1,000 cr per NPC per 4h), housing rent and deposit, sabacc rake, sabacc winnings/losses, entertainer earnings, hyperspace fuel, launch fuel, and ship purchase.

This is not cosmetic. Crew wages alone, on a five-NPC veteran crew, are ~12,000 cr/day per player. If three players are running crews, that's ~36,000 cr/day of sink that **does not appear** on `@economy velocity`. The dashboard will report "net is +5,000 cr/day, looks balanced" while the truth is "net is −31,000 cr/day, you're deflating." Inflation alerts will trip late; deflation alerts won't trip at all because farming detection only watches positive deltas.

CCP at EVE solved this with a hard discipline: every code path that mutates ISK on a character writes to a single audit log on the same line, and any commit that touches `wallet` without a log line is a P0. SW_MUSH would benefit from the same posture. The cleanest implementation is to wrap `db.save_character(credits=...)` so it *requires* a `source` parameter and logs automatically — make it impossible to mutate credits without telling the auditor what happened. Until then, the `@economy` dashboard's accuracy is an inverse function of how much code was written before the audit shipped.

**Recommendation:** Wrapper-enforce credit-log on every mutation. Treat any unlogged credit movement as a P0 bug.

---

### 1.2 There is no terminal sink for ship-class wealth

The personal-weapon decay loop (−5 max condition per repair, weapons retire to dust around the 500-attack mark) is the best piece of economic design in the codebase. It creates predictable demand for new weapons, gives crafters a treadmill of customers, and removes credits and items from circulation deterministically. This is *better* than EVE's insurance system in some ways — it's not random, it can't be insured against, and it converts into player agency.

There is no analogue for ships, vehicles, droids, or armor.

`_apply_hull_damage` on a PC ship runs to no effect — the kill branch only fires on traffic-managed NPCs. `damcon` heals hull damage on a free skill check (no spacedock fee, no parts cost). The "spacedock for destroyed systems" message is flavor text with no implementation behind it. A player ship is functionally invincible and free to maintain beyond the daily 25-cr docking fee.

This matters because **ship destruction is the single largest ISK sink in EVE by volume**, and the analogous mechanic in every healthy persistent-world economy (SWG armor decay, RuneScape PvP "items to dust", PoE map consumption, Albion full-loot zones, Foxhole vehicle scrapping) is the load-bearing column. The reason economies without it tend to inflate isn't that players make too many credits — it's that there's no place for the *high-tier* credits to die. A casual player buys consumables and pays rent. A wealthy player has nowhere for their wealth to go.

The current population shape hides this: with 5 players and no ships destroyed, no one notices. With 15 active players and 60 days of play, you'll have 6–10 capital-class wallets that have plateau'd at "owns ship + droid + housing, nothing left to want." That's the population that drives the inflation seen in EVE/SWG postmortems.

**Three options, in order of difficulty:**

- **Easy and underrated:** add a flat repair fee on `damcon` and a separate "spacedock repair" service for destroyed systems with a real credit cost (5–15% of ship base cost per destroyed system). This converts ship combat into a credit drain even when ships don't die.
- **Medium:** when a PC ship's hull crosses the destruction threshold, mark it `disabled` and require a tow + 30–50% of base cost to restore. SWG used this. Standard "death has a cost but isn't permanent" lever.
- **Hard, optional:** 10–20% chance per disable of a permanent component loss. This is the EVE lesson — destruction creates *replacement demand* in adjacent markets (component crafting), which converts a sink into someone else's faucet.

---

### 1.3 NPC vendor buyback price-supports crafting, which suppresses player-shop prices

The audit added an NPC resource floor (good). What it didn't address is the *output* side. A player can craft a Tier 1 blaster pistol from materials worth ~55 cr (or free, surveyed) and sell it to an NPC for 25–50% of the 500 cr base cost — call it 200 cr after Bargain. That's a >250 cr per-craft credit-creation engine that requires no buyer.

The economic problem isn't the profit margin — it's that the **NPC vendor sets the floor price for the entire crafted-goods market**. No one will list a Tier 1 pistol on a vendor droid for less than 200 cr, because the NPC will pay that. The vendor droid market never has to discover its own floor. Tier 1 crafting becomes a solo grind with no need to engage the player economy.

This was SWG's mistake pre-NGE: NPC vendors were the always-on fallback that prevented player-to-player markets from emerging at the low end. The fix that worked there, and will work here, is to make NPC buyback uneconomical for crafted items specifically.

**Two options:**

- **Direct:** NPCs buy crafted items at 10–15% of base cost (vs. 25–50% for "factory" items). The signal to the player is "this is salvage value; if you want real money, list it."
- **Indirect:** NPCs only buy items below a quality threshold (e.g., quality < 50). High-quality crafts are too good for NPC scrap and *must* go to a player vendor.

The second is more thematic and more interesting economically — it forces low-quality crafts to liquidate (good, removes glut) while pushing high-quality into a real market.

---

### 1.4 Smuggling is currently the worst risk-adjusted faucet, which kills the smuggler fantasy

Running the math on the published rates:

> **Spice Run** (Contraband, Nar Shaddaa→Kessel): 3,000–6,000 cr reward, 55% patrol, 50% fine on bust
> EV per run = 0.45 × 4,500 − 0.55 × 0.5 × 4,500 = 2,025 − 1,238 = **+787 cr**

> **Core Run** (Spice tier, →Corellia): 4,000–8,000 cr, 65% patrol, 50% fine
> EV per run = 0.35 × 6,000 − 0.65 × 0.5 × 6,000 = 2,100 − 1,950 = **+150 cr**

> **Bounty (Veteran)**: 1,500–3,000 cr, target is a fightable NPC, no fine on failure (the bounty just expires)
> EV per claim = pSuccess × 2,250. Even at 50% completion rate = +1,125 cr, with no negative tail.

Smuggling Spice is a 1.5× win-vs-loss bet against a coin flip. A Core Run is a -EV trade for everyone except a fully spec'd Con/Sneak/Pilot character, and even then the variance dominates expectations for short play sessions. Meanwhile a generalist Bounty Hunter Veteran-tier contract has +EV with a strictly bounded downside (you fail, you lose time, no credits forfeit).

This isn't a small mistuning. It's a **theme-mechanic mismatch**: the highest-flavor / highest-risk archetype is also the lowest expected return. Players will figure this out within a week and route around smuggling.

**Fix is one or more of:**

- Lower the fine fraction from 50% to 25–30% at the high tiers (the patrol risk alone provides plenty of variance).
- Raise the Spice/Core Run pay band 1.5–2× — these should be the apex of the credit curve, not the middle.
- Add stack-able "smuggling reputation" that increases pay or decreases patrol chance over time. (TORN pattern — career grind for diminishing risk, which keeps end-game smugglers economically distinct from end-game bounty hunters.)

---

### 1.5 Trade goods supply pool is non-persistent — exploit pattern, not policy choice

The comment in `trading.py` line 200–202 says:

> *"Process-memory only — the pool resets on restart, which is fine: it's a rate limiter, not game state."*

It is not fine. Players will learn the restart pattern. Whatever the cadence — daily maintenance, crash recovery, deploy-driven — the first player on after a restart sees every (planet, good) pool at full or freshly-seeded full, because the `_refreshed()` first-touch branch (line 213–216) seeds at `max_units` on the first call after the dictionary is empty.

If the server restarts daily, daily supply is effectively *doubled* for early-bird players. If restarts are unpredictable, you've created a windfall lottery for whoever happens to log in next. EVE's market state persists; SWG's resources persisted; RuneScape's GE persists; this is not an esoteric requirement.

Persisting this is roughly twenty lines: serialize `_pools` to a single JSON column on a `market_state` table, hydrate on startup, snapshot on each `consume()` call (or on a 5-minute timer to amortize the writes). The cost is small. The cost of *not* doing it is "every time the server bounces, the wealthiest player in the next 30 minutes is whoever was paying attention to the announcement channel."

While in there: same fix should add a `last_consumed_at` so admins can see, on `@economy zones`, which markets are being run hot and which are stagnant. That's the data needed for tuning.

---

## Tier 2 — Tuning Issues

### 2.1 The mission completion difficulty curve rewards over-reaching

`mission_difficulty()` in `skill_checks.py` maps reward → difficulty linearly: 8/11/14/16/19/21 across the 100–5000+ cr bands. The partial-pay fraction in `MISSION_SKILL_MAP` is 50–100% on a margin of −1 to −4. Run the EV math at a 3D skill (4D pool, ~14 average roll):

- 300-cr easy mission, diff 8: ~95% pass → 285 cr expected
- 2,500-cr hard mission, diff 19: pass rare, but partial (margin −1 to −4) covers diffs 15–18 → ~50% → 50% × 2,500 = 1,250 cr expected

A player who *over-reaches by two tiers* expects 4× the income of one who stays in their lane. This is the wrong-direction incentive — the design intent is to reward skill investment matching mission tier, but the math rewards aspirational picks.

**Two fixes that compose:**

- Drop partial pay from 50–75% down to 25–40% (combat/smuggling already at 50%; bring social/investigation/medical/salvage down too).
- Tighten the partial window from `margin >= -4` to `margin >= -2`. A near-miss is a near-miss; a clear failure should pay zero.

The +20% on critical success is well-calibrated and should stay. The fumble branch correctly pays zero. The middle (partial) is the leak.

---

### 2.2 The bounty board is winner-take-all at low population

Board size 4, weighted spawn 5/4/3/2/1 across Extra/Average/Novice/Veteran/Superior. Expected board composition is ≈1.3 Extras, 1.1 Average, 0.8 Novice, 0.5 Veteran, 0.3 Superior. So at any moment there is *probably one* contract worth more than 1,500 cr.

With 5 active players, that one contract goes to whoever spots the refresh first. With 50, it evaporates in seconds. With 15 — the population this design seems aimed at — there's a queueing problem where the same 2–3 fast players collect every Veteran/Superior and the rest grind Extras. This is not a balance bug; it's the topology of shared boards.

The mature MMO answer is **personal queues**: each player has their own bounty board, generated against their level/skill curve, refreshing on their personal timer. EVE agents work this way; SWG mission terminals worked this way; even WoW's daily quests work this way. The shared board makes for cantina RP texture (which has value!) but it's bad as an income system.

**Cheap mitigations if keeping the shared board:**

- **Reservation token**: claiming a contract puts a 60-second hold on it before commit. Reduces refresh-spotter advantage.
- **Tier-aware refresh**: when a Superior is collected, the next spawn is biased toward Superior. Avoids "cleaned out" boards.
- **Personal cooldown on tier**: claim a Superior, can't claim another for 4h. Spreads the wealth.

---

### 2.3 Crew wages aren't logged, and they're substantial

A 5-NPC mixed-tier crew (1 superior + 2 veteran + 2 average) at the published rates costs (1,000 + 2×400 + 2×80) × 6 ticks/day = **11,280 cr/day per player running a full crew**. If three players run crews: ~34,000 cr/day of unlogged sink. This is the single largest source of dashboard error today.

It's also the largest *deflationary* force in the game and it's invisible. If median wealth ever appears to be falling despite faucets running normally, this is where the credits are going. Wire `log_credit(char_id, -wage, "crew_wages", balance)` into `deduct_crew_wages` and the inflation/deflation reading becomes honest.

This is technically a sub-case of §1.1 but called out separately because it's so consequential.

---

### 2.4 The 5,000 cr/day P2P cap is alt-permissive

The cap is correctly *implemented*. The number is the question. 5,000 cr/day is one nice gift between friends, but seven alts → main = 35,000 cr/day = 980,000 cr/month, enough for a Lambda Shuttle + a Tier-3 vendor droid every month, transferred through the cap rather than blocked by it.

**Two changes that compose:**

- Drop the cap to **1,500 cr/day** for raw `pay`/`trade` — that's a meal-out gift, not a salary.
- Exempt explicitly-trackable economic transactions (vendor droid purchases, faction treasury contributions) from the cap. They have their own audit trails. The cap should target *unattributed* P2P credit flow, which is the alt-farming surface.

This makes the legitimate use case better, not worse. A player who wants to sell something to a friend lists on a vendor droid (covered, not capped). A player who wants to bankroll a corporation contributes to the faction treasury (covered, not capped). What the cap blocks is "alt logged in just to wire-transfer to main," which is exactly what should be blocked.

---

### 2.5 The volume-premium / Bargain interaction is unclear

`volume_premium` returns a multiplicative price modifier on the buy side. `resolve_bargain_check`, if invoked in the buy path, also returns a modifier. It's not clear from a quick read whether they compose multiplicatively (a 5D Bargain trader can offset most of the volume premium), additively (they cancel cleanly), or whether Bargain is even invoked on the trade-goods buy path.

Worth a code grep and a unit test — the right design here is *additive* (Bargain shaves off a fixed −10%, volume adds +0–40%, they sum), so a high-Bargain whale still pays a thin-market premium, but a generalist using Bargain on a normal-supply buy gets the discount cleanly.

---

### 2.6 Docking-fee non-payment is a no-op

`docking_fee_tick` graciously skips the deduction if a player can't pay. There's no impound, no escalating penalty, no reclamation. A player who runs out of credits gets *free parking forever*. That's the inverse of what the fee is meant to do.

The v1 audit's recommendation (3 days of non-payment → impound, 500 cr to release) is the right pattern; what's there now is a sink that's only paid by the solvent, which is the wrong incidence.

---

### 2.7 Vendor droid listings don't decay

Once stocked, a player's listing sits forever for the cost of one listing fee (1–2%). A player can list 50 quality-95 pistols at 10× market, pay 1% fee, and wait. This works against price discovery in the player market.

The SWG fix is a 14-day or 30-day listing TTL: items return to seller with a small "stale fee," forcing relist. This converts the listing fee from a one-time stamp into a recurring cost, which is what makes it function as a real sink.

---

### 2.8 There is no end-game credit sink for prestige

Once a player owns a ship, a Tier-3 vendor droid, and Tier-3 housing, what does an extra 100,000 cr buy them? The answer right now is "nothing, really" — there's no aspirational tier 4–5 cosmetic or status purchase. Torn solved this with private islands, EVE with citadel structures, WoW with mounts/transmog, RuneScape with party hats. The pattern is the same: **non-power, high-prestige, expensive, visible to other players**.

**Candidates that fit the SW_MUSH theme:**

- Custom-painted ships at 50–100k flat fee (no stat change, just a description in `ships`)
- Naming rights for unclaimed asteroids, watering holes, docking bays (10k–50k, persistent in look-room output)
- A "big spender" leaderboard on `+who/wealthy` that shows lifetime credits sunk (not held — sunk), creating prestige around being a megafaucet for the economy
- Tier-4 housing at price points well above current Tier-3 (200k+) with bigger room counts and named features
- Faction patronage — a single donation that earns a permanent listed title ("Imperial Patron of the Outer Rim Garrison")

These don't need to be implemented all at once. One or two of them being expensive enough to feel meaningful at 200k+ keeps the wealth ladder from terminating at 50k.

---

## What's Working Well — Don't Touch

A few specific things deserve protection from future tinkering:

The **weapon-decay-by-repair loop** (-5 max condition per repair, weapons retire around 500 attacks) is genuinely well-designed and rarely seen even in big-budget games. Don't soften it. Players will complain; the loop is what creates the ongoing crafted-weapons demand and prevents weapon hoarding.

The **volume-premium-against-current-supply** approach in `volume_premium()` is mathematically correct and beats both flat per-unit pricing (boring) and hard caps (frustrating). Punishing thin-market hoarding without punishing bulk traders in deep markets is the right ceiling. Keep it.

The **demand-pool depression on the sell side** mirrors the supply-pool premium on the buy side. The composition gives a natural per-route round-trip ceiling that doesn't need a separate cap. Cleanest piece of trading-economics code in the project.

The **race-safe P2P cap recheck at accept time** is the kind of detail amateur designs miss. Two simultaneous offers from one offerer would otherwise both pass at offer time and both succeed at accept. Closing this race is good defensive engineering. Don't refactor it away in the name of cleanup.

The **Sabacc 10% rake with a 5-cr floor** is correctly modeled as a voluntary social sink. The minimum keeps it from being free entertainment; the rake keeps it from being a faucet. Right shape for a casino in a persistent world.

The **Director-modulated mission weights** (Lockdown buffs Smuggling pay, Underworld buffs Bounty/Smuggling, Unrest buffs Combat) is a piece of cleverness — the AI dynamically reshapes the income landscape in response to world state. The economic implications are subtle and good. Most games have static job-board distributions; this has a responsive one.

---

## Priorities

Single-sprint ordering:

1. **Wire `log_credit` into every credit-mutating code path.** Without this the dashboard is a fiction. Crew wages first (largest unlogged sink), then weapon repair, then NPC weapon buy/sell, then everything else. Consider a `save_character_credits(char_id, delta, source)` wrapper that makes it impossible to mutate credits without an audit entry.

2. **Persist `SUPPLY_POOL` and `DEMAND_POOL`.** Twenty lines. Closes the restart-windfall exploit. Adds the data needed for tuning anyway.

3. **Add ship repair credit costs to `damcon` and a spacedock ship-disable flow.** Single largest gap in the sink architecture and the lever that keeps the high-tier economy from inflating.

4. **Rebalance smuggling EV.** Either drop the fine fraction at high tiers or raise the pay band. Current numbers make the smuggler archetype economically dominated by bounty hunting, which is theme failure.

5. **Tighten the partial-pay window on missions.** Margin ≥ −2 instead of ≥ −4, and lower partial fractions across the board. Reward staying in lane, not over-reaching.

6. **Add NPC-vendor-buyback restrictions on crafted items.** Either a flat "10% of base, scrap value" or a quality-threshold gate (NPC won't buy quality > 50). Gives the player vendor market room to discover its own floor.

7. **Drop the P2P cap to 1,500 cr/day, exempt vendor-droid and faction transactions.** Closes alt-farming without disrupting legitimate flow.

8. **Listing TTL on vendor droids.** 14 or 30 days. Items return with a stale fee. Forces price discovery.

9. **End-game prestige sink.** One or two cosmetic / titular items at 100k+ price points. The wealth ladder needs a top rung.

The first three together are the difference between an economy that holds at 15+ active players for 90 days and one that doesn't. Everything below them is tuning.

---

## Comparison Set

EVE Online, SWG (pre-NGE), RuneScape, TORN, WoW, Albion Online, Path of Exile, Foxhole are referenced throughout because each solved a piece of the problem at hand. None is a template to copy whole.

The economy SW_MUSH is building is closer in spirit to **Pre-NGE SWG with a lighter touch and better tooling** than to anything else, and that's the right reference point — SWG had the best player-driven crafting economy ever shipped in an MMO, and most of its lessons are already internalized here. The remaining work is the lessons it *didn't* learn until too late.

---

## Implementation Estimates

| # | Item | Effort | Files |
|---|------|--------|-------|
| 1 | Credit log wrapper + wire all sources | 4–6h | `db/database.py`, all faucet/sink call sites |
| 2 | Persist SUPPLY_POOL and DEMAND_POOL | 1–2h | `engine/trading.py`, schema migration |
| 3 | Ship damcon/spacedock repair fees | 3–4h | `parser/space_commands.py`, `engine/starships.py` |
| 4 | Smuggling EV rebalance | 30 min | `engine/smuggling.py` (constants only) |
| 5 | Mission partial-pay tightening | 30 min | `engine/skill_checks.py` (constants only) |
| 6 | NPC buyback restriction on crafted | 1–2h | `parser/builtin_commands.py` (SellCommand) |
| 7 | P2P cap drop + exemptions | 1h | `parser/builtin_commands.py` |
| 8 | Vendor listing TTL | 2–3h | `engine/vendor_droids.py`, weekly tick |
| 9 | End-game prestige sinks (one or two) | 4–6h | new files, varies by choice |

**Total Tier 1 (items 1–3): ~8–12h.** Closes the structural gaps.

**Total Tier 2 (items 4–9): ~10–14h.** Closes the tuning gaps.

---

## Open Questions for v3

1. **Director payroll inflows.** Faction treasuries pay out daily stipends. Where do they refill from — world events, NPC contributions, member dues, or unbounded? If unbounded, this is a hidden faucet that doesn't appear on `@economy`. Worth a focused trace through the Director code path.

2. **First-touch supply pool seeding.** `SupplyPool._refreshed()` seeds at full on first contact. After persistence (item 2), should freshly-discovered planets seed at full or empty? Argument for empty: prevents the "first ever visit to Kessel after a deploy gets a free 80-ton spice load." Argument for full: thematic ("the planet has goods waiting for traders"). Recommend empty + a 1-tick warmup.

3. **Inflation emergency valve.** If the dashboard shows runaway inflation despite all sinks wired, what's the admin tool? Consider a "merchant guild tax" — a percentage taken off all NPC faucet payouts, adjustable from 0–30% via `@economy throttle <pct>`. EVE has done this once or twice in 20 years; having the lever available before it's needed is the difference between a soft fix and a panic patch.

4. **CP–credit decoupling.** The CP system being independent of credits is good design philosophy (prevents pay-to-win). But it does mean wealthy characters with maxed skills have nothing left to want. The prestige sinks in §2.8 are the answer; this question is just a flag to keep the decoupling intentional, not accidental.

5. **Bargain-vs-volume-premium composition.** §2.5 — verify additive, not multiplicative. Add a unit test in `tests/test_trade_economics.py`.

---

*Document ends. Companion to `economy_audit_v1.md` (April 2026). To be referenced from architecture doc roadmap as the "second-pass economic review."*
