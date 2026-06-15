# SW_MUSH Economy Audit

## Verdict

SW_MUSH has the beginnings of a serious MMO-style economy, and the codebase shows more economy discipline than most solo projects: credit movement funnels through a ledger, the crafting lane intentionally shipped sinks with faucets, vendor buying is now stock-gated and presence-gated, tuition is a sink, contraband has an enforcement loop, and the P2P hard cap was replaced by velocity alerts instead of fighting the core player-market fantasy.

The major gap is not “credits.” The major gap is that **credits are the only value type receiving economy-grade observability**. SW_MUSH's real economy includes credits, CP, FP, DSP/Force consequences, faction reputation, schematics, crafting materials, item quality, equipment condition, legal infractions, contraband risk, knowledge, travel access, and social access. Those need to be modeled as value networks, not side effects.

## Economic model inventory

### Currencies and value stores

| Value type | Economic role | Audit concern |
|---|---|---|
| Credits | Primary fungible currency | Strong ledger discipline; still needs macro dashboards and docs reconciliation. |
| CP | Character advancement currency | No equivalent economy-wide ledger observed. Needs rate curves and spend/earn monitoring. |
| FP | Force-point scarcity / heroic currency | Needs gain/spend telemetry and abuse monitoring. |
| DSP / Force consequences | Risk currency, morality pressure, hunter triggers | Needs visible, predictable consequence ladder and anti-farming checks. |
| Faction reputation | Access currency / gate | Needs inflation control, decay or soft caps, and dashboards by faction. |
| Schematics known | Knowledge capital | Tuition helps, but grants/teaching/trainer access need audit logs. |
| Crafting materials | Production inputs | Needs quality-band stock monitoring and source/sink visibility. |
| Item quality | Vertical power/economic premium | Biggest current risk: quality does not yet reach combat. |
| Equipment condition/uses | Durability sink | Good direction; ensure all consumables/mitigation items use authoritative mutation. |
| Contraband/legal state | Risk premium and sink trigger | Needs clear player-facing risk and measurable confiscation/fine rates. |
| Travel/location access | Opportunity value | Strong as a game lever, but needs UX surfacing and anti-dead-zone checks. |

## Strengths

### 1. Credit ledger chokepoint is the right foundation.

The `adjust_credits(char_id, delta, tag)` pattern is exactly what an MMO economy needs. It creates one place to answer: Where did money come from? Where did it go? Which systems are inflating? Which sinks are working?

### 2. The crafting lane shows rare faucet/sink discipline.

The Gundark crafting lane's design principle — no craftable faucet without a matching consumption sink — is excellent. Single-use ordnance, limited-use mitigation gear, contraband confiscation, tuition, and vendor segmentation are the right instincts.

### 3. Vendor market segmentation is conceptually strong.

The old “bare buy can resolve the entire registry” hole was exactly the kind of economy exploit that sinks player markets. Default-closed `vendor_stocked` plus in-room vendor presence is the correct shape.

### 4. Removing the P2P hard cap was the right call.

A fixed P2P cap fights the fantasy of rare, high-quality player goods. The 5% tax plus velocity alert is a better tool. A player economy needs high-value trades; it just needs visibility and abuse detection.

## Major findings

### ECON-1 — P1: Crafted quality not reaching combat threatens the crafting economy.

The architecture notes already identify `OBS.quality_and_boosts_not_combat_read`: combat reads weapon damage and armor protection from registry keys, so crafted quality and experiment boosts currently affect value/decay more than actual combat performance.

That is an economy-level issue, not just a combat issue. If high-quality crafted gear does not feel better in the moment that matters, the market premium becomes roleplay-only. That undermines:

- crafter identity,
- player-to-player trade,
- material quality demand,
- trainer tuition value,
- black-market goods,
- endgame progression,
- faction/quest gating for T5 recipes.

**Recommendation:** implement a bounded quality-to-combat rule.

Suggested pattern:

- Keep registry stats as the canonical base.
- Apply a small, capped modifier from quality band and experiment boosts.
- Make effects readable: “Superior balance: +1 pip to attack,” “Reinforced plating: +1 pip soak,” “Overtuned emitter: +1 damage pip but higher wear.”
- Cap total combat advantage per item tier to avoid runaway power creep.
- Make quality matter more through reliability, condition loss, legality, signature, maintenance cost, and special properties than raw damage alone.

### ECON-2 — P1: Non-credit currencies need ledgers.

Credits are auditable. CP, FP, faction rep, DSP, schematics, material quality, contraband confiscation, and item destruction are not obviously centralized with the same rigor.

**Recommendation:** add a generalized `value_log` or narrow logs by domain.

Minimum useful fields:

```text
id, timestamp, character_id, account_id, value_type, delta, before, after,
source_system, source_tag, counterparty_id, item_id, room_id, metadata_json
```

For non-numeric value, use event rows:

```text
schematic_granted, schematic_taught, item_confiscated, item_destroyed,
contraband_detected, faction_rank_changed, force_point_spent
```

### ECON-3 — P1: Economy docs are stale enough to mislead balance work.

`Guide_06_Economy.md` still refers to a daily P2P cap and contains older earning/spending assumptions. The architecture notes say the hard cap was removed and converted to velocity alerts. If Claude uses stale docs as truth, it can reintroduce old policy, old reward rates, or old exploit assumptions.

**Recommendation:** create one economy-of-record doc:

- current faucet list,
- current sink list,
- current non-credit value flows,
- target hourly rates by playstyle,
- intended first-hour earning/spending,
- intended day-7 and day-30 wealth bands,
- current P2P policy,
- current contraband policy,
- current crafting quality policy.

### ECON-4 — P1: Cache mutation before authoritative DB movement can create divergence.

I saw examples where session character credits are mutated near or before calls to `adjust_credits`. This is not automatically wrong, but it creates a partial-failure risk if DB adjustment fails, is vetoed, applies a different returned balance, or later gains tax/seizure/bonus logic.

**Recommendation:** value mutations should follow this pattern everywhere:

1. Call authoritative service/DB function.
2. Receive returned canonical balance/state.
3. Update session cache from canonical result.
4. Emit player message from canonical result.

Never let session state be the first writer for value movement.

### ECON-5 — P1: Reward-rate balance needs simulation, not only unit tests.

Unit tests prove individual mechanics. They do not prove macro stability. SW_MUSH needs repeatable economy simulations that run common player profiles through 1, 7, 30, and 90 days of play.

Suggested player archetypes:

- casual mission runner,
- bounty hunter,
- crafter-only,
- crafter + gatherer alt pair,
- smuggler/contraband runner,
- Jedi/Force-sensitive path,
- space trader,
- social/RP-heavy low-combat player,
- exploit-minded optimizer.

Track:

- net credits/hour,
- CP/hour,
- faction rep/hour,
- item quality progression,
- material stockpiles,
- debt/fines/confiscations,
- time to first meaningful purchase,
- time to first crafted upgrade,
- time to T5 access.

### ECON-6 — P2: P2P velocity alerts should understand item value, not just credit value.

After the hard cap removal, pure credit velocity is not enough. Players can launder value through underpriced trades, item swaps, material gifts, schematic teaching, and alt-account “free labor.”

**Recommendation:** add item and account graph signals:

- trades where item assessed value differs sharply from price,
- repeated zero-price transfers,
- high-quality items moving to new/low-playtime accounts,
- same-IP or same-account-family flows,
- rapid buy/sell loops,
- suspicious schematic teaching chains.

This does not need automatic punishment. It needs admin visibility.

### ECON-7 — P2: Reputation is probably your most important hidden currency.

Faction reputation gates access, trainers, questlines, maybe equipment and social standing. If rep inflation is too fast, gates collapse. If too slow, players feel blocked.

**Recommendation:** treat rep like money:

- source tags for every rep change,
- rep/hour by faction,
- rank distribution by active days,
- negative-rep recovery rate,
- cross-faction conflict dashboard,
- caps or diminishing returns for repeatable low-risk sources.

### ECON-8 — P2: Contraband needs clear risk communication.

Contraband is excellent because it turns power into risk. But risk only creates fun if players understand it and can make meaningful choices.

**Recommendation:** every contraband item should show:

- legal risk tier,
- where scans are likely,
- concealment skill used,
- consequence on failure,
- known safer routes or “ask around” hints,
- whether the item is illegal everywhere or only in certain jurisdictions.

Do not hide the existence of risk; hide the exact enforcement roll if needed.

### ECON-9 — P2: Scarcity should create social play, not only grind.

Crafting and rare recipes should push players toward trade, apprenticeship, exploration, faction work, and risky markets. Avoid turning scarcity into pure solo farming.

Good levers:

- trainers with limited recipe families,
- faction-specific legal alternatives,
- black-market social discovery,
- material quality from dangerous zones,
- group objectives that reward different professions,
- player teach loops,
- public work orders.

## Recommended economy dashboards

### Daily macro dashboard

- credits minted by tag,
- credits sunk by tag,
- net inflation,
- median / p90 / p99 character wealth,
- median / p90 / p99 account wealth,
- new-player wealth at 1h / 5h / 20h,
- faction rep deltas by source,
- CP earned/spent,
- FP gained/spent,
- DSP gained/reduced,
- materials generated/consumed by quality band,
- items crafted/destroyed/confiscated by category,
- P2P trade value and tax collected.

### Market health dashboard

- top traded items,
- price by quality band,
- bid/ask spread if shops exist,
- items crafted but never used,
- recipes learned but never crafted,
- recipes crafted but never sold,
- vendor-stocked purchases vs player-market purchases,
- black-market item circulation.

### Exploit dashboard

- high-value transfers to low-playtime characters,
- repeated same-counterparty trades,
- zero-price transfers,
- repeated contraband scan evasion,
- rep farming loops,
- mission completion anomalies,
- CP/hour outliers,
- material quality outliers.

## Specific Claude prompts

### Prompt: non-credit economy ledger

> Audit SW_MUSH for every mutation of CP, FP, DSP, faction reputation, schematic knowledge, crafting materials, item quality, item condition, contraband status, and legal infractions. Do not change code first. Produce a map of every write site, whether it has a source tag, whether it is atomic, whether it logs before/after values, and whether it can fail after session-cache mutation. Then propose a minimal value_log or per-domain ledger design with tests.

### Prompt: quality-to-combat design

> Design a bounded quality-to-combat system for crafted weapons, armor, powered armor, consumables, and tools. It must preserve WEG D6 readability, avoid runaway power creep, support item identity, and make high-quality crafted gear feel valuable in combat. Start with a design table and balance caps before writing code. Include regression tests proving registry base stats still work, quality bonuses are capped, low-quality gear is not strictly useless, and combat messages explain the modifier.

### Prompt: economy simulation

> Build an offline economy simulation harness for SW_MUSH that can run player archetypes for 1, 7, 30, and 90 days. Include mission runner, bounty hunter, crafter, gatherer, smuggler, space trader, Jedi/Force path, and optimizer profiles. Report credits/hour, CP/hour, faction rep/hour, material quality stockpiles, item production, item destruction, P2P trade velocity, and time to meaningful upgrades. Do not tune values until the baseline report is produced.
