# SW_MUSH — Economy Audit (FINAL)

**Prepared by:** Senior Game Economist (EVE / RuneScape / WoW / TORN lens)
**Date:** 2026-05-31
**Build audited:** `SW_MUSH_upload_20260531_1915.zip` — HEAD, Clone Wars era (~20 BBY)
**Status:** v1.0 — **FINAL. One of two handoff deliverables.** Companion: `SW_MUSH_Integrated_Game_Design_Report_Phases_1-4_FINAL.md` (the design/implementation plan that acts on these findings through a fun lens).
**Basis:** The live engine (`engine/`, `parser/`, `db/`, `data/`) and the current in-build guides (`data/guides/`). Claims about code behavior are tagged **[VERIFIED]** with file/symbol citations; economic judgments **[ANALYSIS]**; human/design calls **[DECISION]**; the two items needing re-confirmation in implementation **[CONFIRM]**.

**This is the money model.** It documents every economy-touching surface, builds a quantitative balance projection, benchmarks against the genre's best-run economies, and lists prioritized fixes. The companion report reshapes the feel-bad fixes into fun-positive form and sequences them; nothing here is lost there.

---

## Table of contents

1. Executive summary
2. Methodology, scope & confidence
3. The economy as built — full documentation
   - 3.1 Currencies & stores of value
   - 3.2 Credit faucets · 3.3 Credit sinks
   - 3.4 Transfers vs. true sinks
   - 3.5 The loss model (PvP & PvE)
   - 3.6 The measurement layer
4. Subsystem deep-dives
5. Quantitative balance model
6. Comparator benchmarking
7. Findings register
8. Prioritized recommendations (with proposed values)
9. Risk analysis & projections
10. Open decisions · 11. Appendices

---

## 1. Executive summary

SW_MUSH's economy is **architecturally stronger than its current behavior**, and most problems are structural (wiring, data, missing sinks) rather than fundamental. The trade-pricing engine, the death/insurance/escrow model, the credit-ledger skeleton, and the hybrid NPC-baseline-plus-player-premium macro design are professional-grade and should be preserved.

Four findings dominate, and they compound:

**1. The money supply is unmeasurable.** A `credit_log` table and a `get_credit_velocity()` faucet/sink dashboard exist and are correctly designed, but **~80% of credit-moving code bypasses them.** `save_character(credits=…)` doesn't log; each subsystem rolls its own un-logged award helper; the `ship_purchase` sink tag appears only in a test. Until fixed, every tuning number — including this report's — is an estimate.

**2. The high end has almost no sink.** Ship repair is **free** (a skill check). Ships are disabled, never destroyed. There is no functioning ship market. The wealthiest players — ship owners — have essentially nothing draining their credits. A quantitative model (§5) shows a veteran sinking **under 10% of income**, accumulating ~**87,000 cr per active week**, with a sink-to-faucet ratio that *falls* as players get richer (15% → 10%) — precisely backwards from a healthy economy.

**3. Galactic Civil War content residue breaks live systems — and the cleanup is half-staged.** The era pivot removed Corellia and Kessel, but the economic data layer still routes through them. This breaks **7 of 8 cargo-trade routes**, the **two highest-paying smuggling tiers**, and the **new-player starter-ship purchase** (the tutorial spine). Notably, the correct Clone Wars space map **already exists as content** (`data/worlds/clone_wars/space_zones.yaml`) but the engine still hardcodes the old GCW graph — so the fix is largely *flipping the engine to existing data* plus table re-maps and a text sweep.

**4. Several "designed sinks" are actually transfers or are unlogged.** The design counts medical (~10%) as a sink, but medical is player-to-player healing (a transfer). Faction stipends are treasury→member transfers. The sabacc house cut and entertainer faucet work but aren't on the ledger. So the real sink mix is thinner than the design assumes, reinforcing the inflationary lean.

A one-line diagnosis: **the faucets mostly work, the sinks mostly don't, and you cannot see either.** The economy will *feel* fine at launch (5–50 players) because volume is too low to move prices — but it is structured to inflate from the top down, invisibly. The recommendations in §8 make it **visible first, drainable second, and re-mapped onto the live galaxy throughout.**

---

## 2. Methodology, scope & confidence

This audit traced every economy-touching subsystem to source, extracted actual constants/formulas (not design-doc intent), enumerated the credit ledger's reason codes against the sites that mutate credits, and built a quantitative model from the extracted magnitudes. Where implementation diverges from the design docs or guides, **implementation is treated as ground truth** and the divergence is flagged. Scope: all currencies and stores of value; all faucets/sinks; trade/markets; crafting and the resource chain; the ship/space economy; housing/cities/territory; the faction economy; gambling/entertainment; and the PvP/PvE loss model.

**Known limitation:** because the ledger is disconnected (F1), no *empirical* money-supply data exists; the macro assessment is modeled, not measured. This is itself the strongest argument for fixing F1 first.

---

## 3. The economy as built — full documentation

### 3.1 Currencies & stores of value

| Currency | Role | Tradeable | Decays? | Inflation risk | Verdict |
|---|---|---|---|---|---|
| **Credits** | Medium of exchange | Yes (P2P + vendors) | No carry cost | **HIGH** | Structurally inflationary (§5) |
| **CP** | Advancement | No | No | Low | Well-gated; one leak (milestones) |
| **Force Points** | Dramatic resource | No | Spent on use | None | Economically inert; correct |
| **Resources** (6 base + T5 rare) | Crafting inputs | Yes (P2P droids) | **No** | **MEDIUM** | Permanent store; ratchets |
| **Items** | Gear | Yes | **Yes** (condition) | Low | Multiple sinks; healthy |
| **Faction reputation** | Price/access gate | No | Yes (penalties) | N/A | Working gate |
| **Territory influence** | Org zone control | No (org-scoped) | Yes (decay) | N/A | Working endgame loop |

**Credits** start at **500** (`engine/character.py`); no bank interest, no wealth tax, no carry cost — they only accumulate. **CP** **[VERIFIED — `engine/cp_engine.py`]** is time/social-gated (200 ticks = 1 CP; weekly cap 400 ticks; kudos-dominant; ~1 CP/10–12 days; 3D→5D ≈ 7 months), with WEG-canonical advance costs — a deliberately anti-grind, anti-pay-to-win design. **Leak:** `award_milestone_cp()` grants CP *outside* the weekly cap (audit the total milestone pool — F11). **Force Points** are personal, non-tradeable, self-balancing via the dark-side ratchet — inert. **Resources** (`metal, chemical, organic, energy, composite, rare` + T5) **never decay** (`[VERIFIED]` no `resource_decay` in HEAD) — a permanent value-store ratchet (F5).

### 3.2 Credit faucets (creation)

| Faucet | Magnitude | Cadence / governor | On ledger? | Citation |
|---|---|---|---|---|
| NPC mission board | 100–5,000 cr (14 types) | 5–8 jobs, 30-min refresh, 1 active | ⚠️ partial | `engine/missions.py:PAY_RANGES` |
| NPC bounty board | 100–10,000 cr (5 tiers) | 3–5 contracts, 45-min refresh | ✅ `bounty` | `engine/bounty_board.py:PAY_RANGES` |
| Smuggling | 200–8,000 cr (5 routes) | 45-min refresh; −50% on bust | ✅ `smuggling` | `engine/smuggling.py:ROUTE_DEFS` |
| Cargo trade | ~6,000–8,000 cr/hr (soft-capped) | supply-pool rationed | ✅ `trade_goods` | `engine/trading.py` |
| Harvest | 100–800 cr/pull + resources | 30-min cooldown per region | ❌ **no** | `engine/harvest.py:YIELD_TABLE` |
| Entertainer `perform` | 50–500 cr/perform | 10-min cooldown; **NPC crowd, no audience needed** | ❌ **no** | `parser/entertainer_commands.py` |
| Director contracts | 100–5,000 cr/order | per-order capped; **aggregate unbounded** | ❌ **no** | `engine/director.py:1164` |
| City tax on NPC commerce | ≤10% of NPC sale | per-transaction; **created from thin air** | ❌ **no** | `engine/player_cities.py:apply_city_tax` |
| NPC weapon sell-back | 25–50% of base | per sale | ❌ **no** | `parser/builtin_commands.py:SellCommand` |

**[ANALYSIS]** Mission/bounty boards are a reliable, well-shaped floor faucet (single active, TTLs, partial-pay fractions). Three faucets are **population-independent and unmeasured** — they pay on timers regardless of player count or demand: the mission board, the entertainer `perform` (a fictional NPC crowd "tosses credits onto the stage"), and Director contracts. The **city tax is genuine net-new credit creation** (conjured into org treasuries, later paid out as stipends), bounded only by the ≤10% rate and NPC-commerce volume.

### 3.3 Credit sinks (destruction)

| Sink | Magnitude | Type | On ledger? | Status | Citation |
|---|---|---|---|---|---|
| Housing rent / purchase | 50–250/wk · 5k–25k | recurring + capital | ❌ no | works | `engine/housing.py` |
| Crew wages | default 80/day, /4h | recurring | ❌ no | works | `engine/npc_crew.py:TIER_WAGES` |
| Docking fee | 25 cr (±zone) | recurring | ✅ `docking_fee` | works | `parser/space_commands.py:1288` |
| Fuel | sublight 50+(speed×10); jump 100×hyperdrive | recurring | ❌ no | works | `parser/space_commands.py:1190/3807` |
| Weapon repair | 50–250 cr + permanent −5 max cond | recurring | ❌ no | works | `engine/items.py` |
| NPC vendor spread | buy 100% / sell 25–50% | per txn | ❌ no | works | `parser/builtin_commands.py` |
| Smuggling fine | 50% of reward | risk | ✅ `smuggling_fine` | works | `engine/smuggling.py:FINE_FRACTION` |
| Sabacc house cut | 10% + dealer wins ties | voluntary | ❌ **no** | works | `parser/sabacc_commands.py:HOUSE_CUT` |
| Vendor droid / listing fee | 2k/5k/12k · 1–2%/sale | capital + per-sale | ❌ no | works | `engine/vendor_droids.py` |
| P2P transfer tax | 5% (`amount//20`) | per transfer | ✅ `p2p_tax` (char 0) | works | `parser/builtin_commands.py:4514` |
| Schematic purchase | 50–15,000 cr | capital | ❌ no | works | `data/schematics.yaml` |
| Resource-vendor buy | metal 15, etc. | per purchase | ✅ `resource_vendor` | works | `parser/crafting_commands.py` |
| BH guild cut / insurance | 20% escrow · 10% on death | per event | ✅ `bh_*` | works | `engine/death.py` |
| Hutt debt | 500/wk | quest | ❌ no | works | `engine/debt.py` |
| City founding/expansion/maint | 25k–200k · 5k · 100–200/wk | treasury sink | ❌ no | works | `engine/player_cities.py` |
| Territory investment | 1,000 cr → 10 influence | treasury sink | ❌ no | works | `engine/territory.py` |
| **Ship repair** | **0 cr** | — | n/a | **GAP (F2)** | `engine/skill_checks.py`, `parser/space_commands.py:DamConCommand` |
| **Ship purchase** | 8k starter only; 98k–1.5M inert | capital | test-only | **near-inert (F4)** | `engine/spacer_quest.py:826` |

**[ANALYSIS]** The functioning sinks cluster at the **low-to-mid tier** (rent, fuel, wages, docking, handheld-gear repair, vendor spread, fines, P2P tax, schematics) and taper to near-zero for anyone with a paid-off ship and house. The structural sinks that should anchor the *high* tier — ship repair and ship replacement — are absent or inert (§4.8). Treasury sinks (city/territory) are real and substantial but reachable only by organized groups.

### 3.4 Transfers vs. true sinks

A transfer redistributes credits; a sink destroys them. Only destruction fights inflation. **[VERIFIED]** Two systems the design treats as sinks are transfers: **medical** (patient → medic, default 200 cr; `parser/medical_commands.py`) and **faction stipends** (treasury → member; `engine/organizations.py`). Conversely, two real sinks are **unlogged** and thus invisible: the **sabacc house cut** and the **vendor sell-back spread**. **[ANALYSIS]** The design ledger therefore *overstates* real sink capacity; when F1 is fixed and these are reclassified, expect measured sinks to come in below the design's assumed outflow, confirming the inflationary lean.

### 3.5 The loss model (PvP & PvE) — and an important guide-vs-code divergence

**[VERIFIED — `engine/death.py`]** Death is **zone-gated**: secured zones give instant respawn-with-gear and no corpse; contested/lawless create a lootable corpse (decay 2h/4h) and apply a −1D wounded debuff for a recovery window. **Credits never drop** (carried + bank protected). **Ships are disabled, not destroyed** — only cargo can be lost in specific encounters. A BH kill on an active PC bounty adds a 10% insurance hit; escrow splits 80% hunter / 20% sunk to Guild treasury.

**The divergence [VERIFIED]:** the in-build combat & medical guides tell players *"equipment you had equipped is preserved; loose inventory may be lootable."* The code's `_snapshot_and_clear_inventory` drops **everything — equipped gear + inventory + resources** — in non-secured zones. So the *documented* loss model is gentle and the *actual* one is a full strip.

**[ANALYSIS / economic relevance]** Gear loss is a real **sink** (uninsured deaths remove items from the economy), so the loss model is economically meaningful, not just a fun question. But the magnitude is larger than documented, and the consent model (the security-zone backbone) is sound. **[DECISION]** Reconcile to the *documented gentle model* (preserve equipped gear, drop only loose inventory) — it keeps a real sink while fixing the trust break — and add gear insurance + anti-griefing (see F12 / companion report Phase 2). Keep credits and ships protected for population reasons; hold ship-destructibility as a reserve anti-inflation lever (§10).

### 3.6 The measurement layer

**[VERIFIED — `db/database.py:2427 log_credit`, `:2441 get_credit_velocity`]** The instrument exists and is well-designed: `log_credit(char_id, delta, source)` writes a `credit_log`; `get_credit_velocity(seconds)` returns faucet/sink totals, net, top faucets/sinks/earners. `economy_hardening_design_v1.md` defines a 22-source taxonomy. **[VERIFIED]** Only ~10 sources are ever emitted (`trade_goods, mission, bounty, smuggling, smuggling_fine, resource_vendor, docking_fee, p2p_tax, bh_insurance_hit, bh_bounty_payout, bh_guild_treasury_sink`); the rest — every recurring sink (rent, wages, fuel, repair) and several faucets (harvest, entertainer, city tax, Director) — never call it, because `save_character(credits=…)` doesn't auto-log and each module mutates `char["credits"]` directly. **[ANALYSIS]** The dashboard reports on ~a fifth of the economy and **systematically under-reports inflation** (the largest unmeasured flows net positive). Fixing this is cheap relative to its value: route every mutation through one `adjust_credits(char_id, delta, source)` chokepoint that updates and logs atomically.

---

## 4. Subsystem deep-dives

**4.1 Trade & cargo — the best-engineered system; running on a dead map.** **[VERIFIED — `engine/trading.py`]** `SupplyPool` (per-planet rationing, 45-min refresh, 2× carryover) + `DemandPool` (sell-side depression ~0.5%/ton to a 30% cap) + `volume_premium()` (order-impact pricing) compose into a *natural per-round-trip profit ceiling without a hard cap* — the elegant way to bound a trade economy; spread tightened to a healthy 70/140. **[CRITICAL — F3]** But `TRADE_GOODS` sources nearly every good from Corellia/Kessel (deleted); only `luxury_goods` retains a valid pair. The cargo economy funnels onto one thin route. Fix = data re-map (Appendix C).

**4.2 Player vendor droids & the market question.** **[VERIFIED — `engine/vendor_droids.py`]** A real player storefront economy: droid tiers (2k/5k/12k), player-set prices, tier-3 **buy orders** (a primitive order book), a `PRICE_FLOOR_PCT=0.5` anti-dump guard, faction-rep price modifiers. **[DECISION]** What's missing is **discovery, not a marketplace.** At 5–50 players a full central AH is wrong (no volume, kills the RP). Build `+market <item>`/`search` (read-only index of live listings + open buy orders, no remote execution) — EVE-regional-lite. (R7.)

**4.3 Crafting — a clean value-add transformer.** **[VERIFIED — `engine/crafting.py`, `data/schematics.yaml`]** Quality-gated resource inputs, no credit cost to craft (schematic 50–15,000 cr is the sink), output quality scales with skill+inputs, regional/weekly quality variance creates arbitrage, a meaningful high end (Master-Crafted Lightsaber 10k, etc.). **[ANALYSIS]** Healthy. **Tension (F8):** NPC vendors buy crafted weapons at 25–50% of base — a floor under player goods, but the NPC competes with the player crafter market; watch at higher population.

**4.4 Harvesting.** **[VERIFIED — `engine/harvest.py:YIELD_TABLE`]** 100–800 cr + resources per pull, scaling with zone-control tier and lawlessness, 30-min/region cooldown, 15% non-owner tax to the territory owner. **[ANALYSIS]** Sound; but credits are **unlogged** (F1), and because resources never decay (F5), every pull permanently adds material stock.

**4.5 Bounty hunting.** **[VERIFIED — `engine/bounty_board.py`, `engine/death.py`]** NPC bounties (100–10k, well-shaped) + PC bounties with **escrow** (80% hunter / 20% sunk to Guild) + a 10% insurance hit. **[ANALYSIS]** One of the strongest-built systems; the 20% cut is a real, logged sink. Needs only the insurance-curve fix so low-value bounties deter (F12).

**4.6 Smuggling.** **[VERIFIED — `engine/smuggling.py`]** Five risk-tiered routes (patrol chance, 50% fine on bust). **[CRITICAL — F3]** The two top tiers (`spicerun`→Kessel 3–6k, `corerun`→Corellia 4–8k) deliver to deleted worlds; income caps at the `interplan` tier (~1.5–3k). "Imperial patrol/fine" framing is GCW residue. Re-point + re-theme.

**4.7 NPC missions.** **[VERIFIED — `engine/missions.py:PAY_RANGES`]** 14 types, 100–5,000 cr, 5–8 jobs, 30-min refresh, one active, floored partial-pay. **[ANALYSIS]** The reliable floor faucet; well-shaped but population-independent and partly unlogged (F1/F10). Notably, `generate_faction_mission()` + `available_missions_for_char()` already support rep-gated faction missions — the hook for faction-flavored income.

**4.8 Ships & the space economy — the biggest structural gap.** **[CRITICAL — F2]** Repair is free (`damcon` is a skill check; spacedock credit path unwired); ships are disabled, never destroyed. **[HIGH — F4]** No live ship market: the only purchase path is the scripted 8k starter (`engine/spacer_quest.py:826`, on deleted Corellia); the 98k–1.5M catalog (`data/.../starships.yaml`, Consular 1.5M) is inert; `ship_purchase` logged only in a test. **[ANALYSIS]** Repair-and-replace is the load-bearing high-tier sink in every capital-asset economy because it taxes exactly the players whose un-sunk credits most drive prices up. SW_MUSH has *neither half*. This is why §5 shows the high tier accumulating ~87k/week at <10% sunk. **Note:** the CW space topology already exists as data (`data/worlds/clone_wars/space_zones.yaml`); the engine hardcodes the GCW graph (`engine/npc_space_traffic.py`) — so the era fix is largely flipping engine to data. **Era residue (F14):** X-Wing/TIE hulls in the catalog.

**4.9 Housing, cities & territory.** **[VERIFIED]** Housing is a solid recurring sink (5k–25k purchase, 50–250/wk rent). **Player cities** are large net credit sinks (founding 25k/75k/200k, expansion 5k, maintenance 100/room + 200/guard per week — all debited from treasury) — a healthy endgame drain that *net-drains* the economy. **Treasury fill (F9):** org treasuries start at 0 and fill only via `adjust_org_treasury` — member deposits + the **city tax created from thin air** (genuine net creation, unlogged; likely small vs. founding/upkeep). **Territory** runs on non-credit influence (cap 150, control at 100) with a **1,000 cr → 10 influence** credit sink and a control→harvest-boost loop. Reasonable.

**4.10 Faction economy.** **[VERIFIED — `engine/organizations.py`]** Stipends (50–500/wk, faction+rank) are **paid from and debited against the treasury** — transfers, not faucets (the city-tax fill is the creation event). Jedi stipends are deliberately austere. Reputation gates vendor prices and access — a working, non-inflationary lever.

**4.11 Gambling & entertainment.** **[VERIFIED]** **Sabacc** is a genuine sink (10% house cut + dealer wins ties) — correctly designed, but the cut is **unlogged** (F15). **Entertainer `perform`** is a **pure NPC faucet** (50–500 cr/10min, fictional crowd, no real audience required), credits added directly and **unlogged** (F10) — economically the same shape as the mission board.

**4.12 Advancement (CP & FP).** Covered in §3.1. Both well-designed and largely outside the credit economy. CP is the model the credit economy should aspire to. Watch-items: the milestone-CP cap bypass (F11) and a confirmation FP isn't farmable via the same hooks that feed CP.

---

## 5. Quantitative balance model

Modeled (ledger disconnected), conservative, directional. Three archetypes:

**New player** (no ship/house, ~10 hrs/wk): faucets ~5,000/wk (missions + easy bounties + harvest); sinks ~540/wk; **net +4,460/wk** → starter ship in ~1.8 weeks (healthy onramp — *if* the starter ship weren't on deleted Corellia, F3).

**Mid player** (ship+house, trades, ~12 hrs/wk): faucets ~51,600/wk (missions, bounties, interplan smuggling, the one live cargo route); sinks ~7,900/wk (fuel, rent, docking, vendor, **ship repair 0**); **net +43,700/wk — 15.3% sunk.**

**Veteran** (paid-off, optimized, ~15 hrs/wk): faucets ~96,000/wk (elite bounties, cargo, missions); sinks ~9,250/wk (fuel, rent, docking, **ship repair 0**); **net +86,750/wk — 9.6% sunk.**

| Tier | Sunk % | Net/wk |
|---|---|---|
| New | 10.8% | +4,460 |
| Mid | 15.3% | +43,700 |
| Veteran | **9.6%** | **+86,750** |

**[ANALYSIS]** A healthy economy's sink ratio **rises** with wealth; SW_MUSH's **peaks mid-game and falls for veterans**, because mid-game sinks don't scale with veteran income and the sink that *should* scale — ship repair/replacement — is zero. Mature economies target **60–90% sunk** at the top; SW_MUSH is at ~10%. That is an inflation engine at the top of the wealth curve, currently invisible (F1). **Sequencing caution:** fixing the dead-planet routes (F3) *raises* faucet income (restores 7 trade routes + top smuggling tiers), so the high-tier sink (R2) must land with or ahead of it.

---

## 6. Comparator benchmarking

**Sinks.** *EVE* runs on ship destruction (its master sink) + fees/clones; SW_MUSH has EVE's fee instinct (listing fees, P2P tax) but opted *out* of EVE's master sink and hasn't replaced it. *RuneScape* learned that recurring scaling sinks (high-level repair, degradation) beat mudflation; SW_MUSH has the degradation instinct for handheld gear but not ships — the inverse of where RuneScape put its heaviest sink. *WoW* leans on repair bills + vanity + consumables; SW_MUSH has consumables and the *structure* for repair but zeroed the bill.
**Faucets.** All four comparators eventually added global rate governors (EVE bounty nerfs, RuneScape drop tuning); SW_MUSH's faucets are effort-gated but ungoverned and several pay on timers independent of population — the recommended `@economy throttle` is the SW_MUSH equivalent.
**Loss.** SW_MUSH's "gear-at-risk, credits/hull-safe" sits closest to *TORN's* middle ground — well-judged for an RP MUSH, but like TORN it needs anti-griefing guards it currently lacks (F12).
**Markets.** SW_MUSH's scattered droids are pre-market (listings, no discovery); the recommended `+market` targets the *EVE regional-discovery* model, not the *WoW global-AH* model — correct for the population and RP.
**Measurement.** *EVE* publishes a Monthly Economic Report because you can't manage what you can't measure. SW_MUSH built the right instrument and left it disconnected — **the single biggest gap vs. best practice, and the cheapest to close.**
**Net:** SW_MUSH has the *instincts* of the genre's best-run economies but has left the highest-impact mechanisms disconnected (measurement), zeroed (repair), or un-built (ship market, discovery). The gap is execution, not understanding.

---

## 7. Findings register

| # | Severity | Finding | Consequence |
|---|---|---|---|
| F1 | **CRITICAL** | ~80% of credit flows bypass `log_credit`; `save_character` doesn't auto-log | Money supply unmeasurable; inflation invisible; all tuning blind |
| F2 | **CRITICAL** | Ship repair free (skill check); spacedock credit path unwired | No high-tier sink; veterans bank ~87k/wk at <10% sunk |
| F3 | **CRITICAL** | GCW dead planets break trade (7/8), smuggling (top 2), starter-ship onramp; CW map exists as data but engine hardcodes GCW | Three live systems degraded; trade runs on a dead map (fix half-staged) |
| F4 | HIGH | No real ship market; 98k–1.5M catalog inert; ships never destroyed | Largest designed sink doesn't exist; no replacement demand |
| F5 | HIGH | Resources never decay; credits have no carry cost | Permanent value stores ratchet wealth upward |
| F6 | HIGH | "Medical/stipend sinks" are transfers; sabacc/vendor sinks unlogged | Real sink mix thinner than design claims; confirms inflationary lean |
| F7 | MEDIUM | No item-discovery layer across scattered player droids | Poor price discovery/liquidity |
| F8 | MEDIUM | P2P cap still 5,000; NPC buys crafted gear at 25–50% | Alt-farming window; NPC competes with player crafters |
| F9 | MEDIUM | City tax created from thin air → treasury → stipends; unlogged | Net credit creation, unbounded/unseen (likely small) |
| F10 | MEDIUM | Mission board, entertainer, Director are population-independent unmeasured faucets | Constant net-positive injection invisible on dashboard |
| F11 | MEDIUM | Milestone CP bypasses the weekly cap | Advancement can inflate past ~2 CP/week design |
| F12 | MEDIUM | Death drops *all* gear (vs. guide's "equipped preserved"); corpse-loot griefing; insurance doesn't scale down | Trust break; one-sided stripping; weak low-end deterrent |
| F13 | LOW | NPC kills drop no item loot | Combat builds lack a material loop (deliberate; decision) |
| F14 | LOW | Era residue (Imperial patrols, X-Wing/TIE hulls, Empire payroll, Corellia/Kessel in guides + housing) | Reads off-era; F3 is the mechanical part |
| F15 | LOW | Working sinks (wages, fuel, rent, repair, sabacc cut) unlogged | Invisible on dashboard (rolls into F1) |

---

## 8. Prioritized recommendations (with proposed values)

Sequenced by leverage/dependency. Values are first-cuts to ratify against live data.

**R1 — Connect the ledger (first; everything depends on it). [F1, F10, F15]** A single `adjust_credits(char_id, delta, source)` chokepoint (update + log atomically); migrate all ~30 mutation sites (order: crew wages → repair → vendor → harvest → entertainer → city tax → Director → rest); surface `get_credit_velocity` in `@economy` + web panel + player-facing `+finances`; add velocity alerts and an `@economy throttle <pct>` global NPC-faucet valve.

**R2 — Build the high-tier sinks. [F2, F4]** Ship-repair credit cost (proposed: full-restoration ~5–8% of hull value as a paid spacedock service; keep `damcon` field-repair free); a real ship brokerage so the 98k–1.5M catalog is a live sink; + the ship-permanence/destructibility decision (R-DEC1). *Highest impact after R1.*

**R3 — Re-map the galaxy onto the six CW worlds. [F3; F14]** Flip the engine to the existing `space_zones.yaml`; re-map `TRADE_GOODS` source/demand (Appendix C) and smuggling top-tier destinations off Kessel/Corellia; relocate the starter-ship vendor; sweep X-Wing/TIE hulls, Imperial framing, and Corellia/Kessel guide+housing text. *Pure data/wiring; repairs three live systems; land with or ahead of R2.*

**R4 — Add a resource sink. [F5]** Recommend **opt-in quality catalysts** (NPC reagents that improve craft output/success — a willing sink) over decay or mandatory reagents.

**R5 — Bound & meter the hidden faucets. [F9, F10]** Ledger + cap city tax, Director contracts, entertainer payout.

**R6 — Tighten farming controls. [F8]** P2P daily cap 5,000 → ~1,500; gate/lower NPC crafted-gear buyback.

**R7 — Market discovery (not a central AH). [F7]** `+market <item>`/`search` read-only index + listing TTL.

**R8 — Fix the PvP loss edges. [F12]** Reconcile the corpse drop to the documented model (preserve equipped gear); diminishing loot on repeated kills + victim grace; flat-plus-% insurance floor.

**R9 — Cap milestone CP. [F11]**

**R10 — Era cosmetic sweep. [F14]** (Bundle with R3.)

---

## 9. Risk analysis & projections

**Short term (launch, 5–50 players):** feels fine; new players progress well; low volume hides everything. **Danger: false confidence** while veterans accumulate ~87k/wk with no drain. **Medium term (50–200, months in):** veteran balances reach the hundreds of thousands to millions; player-market prices on scarce/crafted goods drift up as the credit-rich bid them up; new players feel "everything costs too much"; **none of it shows on the dashboard until advanced (F1).** **Long term (200+):** classic mudflation — the currency loses meaning at the top, NPC-priced goods become trivially cheap for veterans, the economy bifurcates into a hyperinflated player layer over a frozen NPC floor. Far cheaper to prevent than reverse. **Sequencing risk:** R3 without R2 *accelerates* the problem. **Lowest-regret path:** R1 first (visibility + valve), then R2+R3 together, then R4–R10 as tuning — R1 converts this model into measured data so every value can be ratified against reality.

---

## 10. Open decisions

1. **Ship permanence vs. destructibility (master lever).** *Rec:* keep repairable for launch; build repair + aspirational sink; hold destructibility in reserve for stubborn measured inflation. 2. **How much should players lose?** *Rec:* keep credits/hull safe; reconcile gear loss to the documented model + insurance. 3. **Market posture.** *Rec:* discovery-only `+market`. 4. **Resource sink.** *Rec:* opt-in catalysts, no decay. 5. **NPC loot.** *Rec:* keep zero. 6. **CP milestone generosity.**

---

## 11. Appendices

**Appendix A — Master ledger (extracted constants).** *Faucets:* mission 100–5,000 · bounty 100–10,000 · smuggling 200–8,000 · trade ~6–8k/hr · harvest 100–800/30min/region · entertainer 50–500/10min · Director 100–5,000/order · city-tax ≤10% · NPC sell-back 25–50%. *Sinks:* rent 50–250/wk · house 5k–25k · crew 80/day/4h · docking 25 · sublight fuel 50+(speed×10) · jump fuel 100×hyperdrive · weapon repair 50–250 (+perm −5) · vendor sell 25–50% · smuggle fine 50% · sabacc 10% · droid 2k/5k/12k · listing 1–2% · P2P tax 5% · schematic 50–15k · resource-vendor (metal 15…) · BH guild 20% · BH insurance 10% · Hutt debt 500/wk · city 25k/75k/200k + 5k + 100/room + 200/guard/wk · territory 1,000→10 influence · **ship repair 0** · **ship purchase 8k starter only.**

**Appendix B — Crafting (selected schematic base costs, cr).** Blaster Pistol 500 · Rifle 1,000 · Vibroblade 250 · Medpac 100/300 · Combat Stim 2,000 · Shield Generator Mk.II 3,500 · Hyperdrive Tuning Kit 4,500 · Master-Crafted Lightsaber 10,000 · Hyperdrive Surge Converter 12,000 · Mil-Spec Ion Engine Core 15,000 · Master-Grade Armor 8,500. Resources: metal, chemical, organic, energy, composite, rare (+T5). No credit cost to craft beyond the schematic; resources consumed.

**Appendix C — Proposed CW trade re-map (first cut).** Source ≈70% / Demand ≈140%: Raw ore — Tatooine/Geonosis → Kuat/Coruscant · Industrial parts — Kuat → Geonosis/Tatooine · Electronics/droid parts — Geonosis/Kuat → Coruscant/Nar Shaddaa · Medical/bacta — Kamino → Geonosis/Tatooine/Nar Shaddaa · Foodstuffs — Coruscant → Kamino/Tatooine/Geonosis · Luxury — Nar Shaddaa → Coruscant/Tatooine · Weapons — Nar Shaddaa → Geonosis/Tatooine · Spice/contraband — Nar Shaddaa → Coruscant. Smuggling top tiers re-point to Nar Shaddaa / deep-Outer-Rim, re-themed to Republic/CIS interdiction.

**Appendix D — Verification status.** All findings [VERIFIED] at symbol level except **[CONFIRM]**: the full crew-wage tier table beyond the 80/day default, and the precise org-treasury seeding path (confirmed: starts at 0, fills only via `adjust_org_treasury`; no auto-seed found). Neither is load-bearing for any CRITICAL/HIGH finding; both are the first items to re-confirm in implementation.

---

*End of Economy Audit (FINAL). Companion: `SW_MUSH_Integrated_Game_Design_Report_Phases_1-4_FINAL.md`, which acts on these findings through a fun lens and sequences the implementation.*
