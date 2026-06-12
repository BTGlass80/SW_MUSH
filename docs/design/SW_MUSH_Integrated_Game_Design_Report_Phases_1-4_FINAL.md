# SW_MUSH — Integrated Game Design Report & Implementation Plan (Phases 1–4)

**Prepared by:** Senior Game Designer (with the senior-economist audit fully folded in)
**Date:** 2026-05-31
**Status:** v1.0 — **FINAL. One of two handoff deliverables.** This is the implement-from design document for the whole-game rev. Its companion is `SW_MUSH_Economy_Audit_FINAL.md` (the money model and its findings, referenced throughout but not duplicated here).
**Basis:** The current in-build guides (`data/guides/Guide_01`–`Guide_26`) and the live engine (`engine/`, `parser/`, `data/`, `db/`). Engine hooks cited here were verified at the symbol level; where the in-build guide and the project-folder copy disagreed, the in-build guide was treated as truth.

**This document consolidates and supersedes the working drafts** (`SW_MUSH_holistic_systems_review_v1.md`, `SW_MUSH_economy_and_fun_design_v1.md`, `SW_MUSH_phase3_*_spec_v1.md`). Everything implementable from those is here, integrated and reconciled.

---

## Table of contents

- **Part I — The verdict & the design thesis**
- **Part II — System-by-system design ratings** (the whole-game read)
- **Part III — The cross-system findings** (what only the wide aperture reveals)
- **Part IV — The integrated change set** (fun + economy, one rev)
- **Part V — PHASE 1 spec: Instrument the economy**
- **Part VI — PHASE 2 spec: Era migration & death reconciliation**
- **Part VII — PHASE 3 spec: Playstyle loops & the aspirational economy**
- **Part VIII — PHASE 4 spec: Force depth & the living world**
- **Part IX — Phase 5 (post-rev): markets, rhythm, hygiene**
- **Part X — Open design decisions (yours to own)**
- **Part XI — Acceptance tests & sequencing**

A note on confidence: engine-behavior claims are verified; proposed values are design first-cuts to playtest against live data once Phase 1 ships, not laws.

---

# PART I — The verdict & the design thesis

## The verdict

SW_MUSH is, system-for-system, **a genuinely well-built RP MUSH** — more mechanical depth and far better presentation than the overwhelming majority of text games. Combat is excellent and fun to play; the RP scaffolding (scenes/plots/places) is first-class; onboarding is mature; the faction *fiction* is rich and evocative. This is not a "make it fun" project at the system level.

The whole-game problems are **structural and cross-cutting**, and they cluster in five places:

1. **An incomplete era migration taxes the core fantasy.** The Clone Wars pivot — the game's entire reason for being in this era — was never finished in the space layer or the player-facing guides. Players still fly to Corellia and Kessel and read about the Empire. (Part III §C1.)
2. **Death has two rulebooks; the harsher one is live.** The guide promises equipped gear is safe; the code drops everything. This breaks trust and isn't fun. (Part III §C2.)
3. **Playstyles diverge in fiction but converge in mechanics.** Eight distinct fantasies share one uniform earning loop. This is the biggest *fun* opportunity and it's mostly wiring. (Part III §C3.)
4. **The economy can't be measured and has no high-tier sink.** The money supply is invisible; the rich have no drain. (Companion audit, summarized Part III §C4.)
5. **The signature fantasy — the Force — is mechanically thin**, and the rich narrative layer doesn't talk to the mechanical layer. (Part II §2.4, Part III §C5.)

## The design thesis (the lens for every decision below)

**The economy exists to feed the fun, not to compete with it.** SW_MUSH's fun comes from five pillars — *being someone, telling stories, living the fantasy, mastery, and belonging/status*. Every mechanic is judged by one question: *does this create a situation, a story, a fantasy moment, a meaningful choice, or a status marker?*

From that lens comes the single most important idea in this report, which reconciles the economist's findings with fun:

> **The best economic sinks are ones players are happy to pay.** The economist correctly found the rich need a drain. The designer's contribution is to build that drain out of *aspirational* spending — ship customization, home/city/faction prestige, status, vanity — so the player who spends walks away *happy*, having bought something they wanted, not taxed. Punitive sinks (repair, fuel) become a modest, in-fiction backstop, not the main event.

Every economist recommendation survives this report. The three that were feel-bad got reshaped into fun (Part IV).

---

# PART II — System-by-system design ratings

Each system rated **Fun** (enjoyable to engage?) and **Integration** (reinforces other systems + the economy?).

| # | System | Fun | Integ. | One-line finding |
|---|---|:--:|:--:|---|
| 2.1 | Ground Combat | **A** | **A** | Best system in the game; tactical, dramatic, archetype-varied. Protect it. |
| 2.2 | Character Creation | A− | A | Strong front door (9 species, 7 templates, real build expression). |
| 2.3 | CP Progression | B+ | A | Slow/anti-grind = right for mastery & inflation; needs early wins elsewhere. |
| 2.4 | **Force Powers** | **C+** | B | Thin for the era's signature fantasy. Highest unspecced fun investment. |
| 2.5 | Space Systems | B | C | Solid framework dragged down by un-migrated GCW map. |
| 2.6 | Crafting | B+ | A | Clean value-add loop; the supply-chain fantasy's engine. |
| 2.7 | Economy (faucets) | B− | — | Sound faucets, missing sinks, dead routes (companion audit). |
| 2.8 | Security Zones | A− | A | Excellent consent model; the backbone of consensual loss. |
| 2.9 | Medical & Death | C | B | Guide-vs-code divergence; harsh model live. Reconcile. |
| 2.10 | Orgs & Factions | A−/C | B | Gorgeous fiction, uniform mechanics. The marquee opportunity. |
| 2.11 | Territory Control | B+ | A | Clean org endgame; serves groups well. |
| 2.12 | Cities & Housing | B+ | A | The natural home for the aspirational sink. |
| 2.13 | Player Shops | B | A | Good bones; needs discovery + faction flavor. |
| 2.14 | **Espionage** | B+ | B | Hidden gem: intel-as-currency. Underexposed; elevate it. |
| 2.15 | Encounters & Hazards | A− | B | Generative-not-punitive; great pressure system. |
| 2.16 | Scenes/Plots/Places | A | A | The heart of the game. Protect; connect to mechanics. |
| 2.17 | Sabacc & Entertainer | B | B | Good flavor sinks/faucets; wire into faction loops. |
| 2.18 | Director AI | B+ | A | Powerful but invisible; could be the engagement heartbeat. |

**The pattern across the table:** individually strong systems that don't yet *compound* into distinct, fantasy-driven journeys, with a layer of stale era-content taxing the core appeal. The rev fixes the compounding and the staleness.

---

# PART III — The cross-system findings

## C1 — The GCW→CW migration is incomplete and taxes the core fantasy [CRITICAL]

The economy audit found dead-planet references in trade *code*. The guides + engine reveal the problem is **broader, player-visible, and half-staged**:

- **The space topology is still GCW at runtime.** `data/worlds/clone_wars/space_zones.yaml` already contains the full correct CW graph (24 zones — six worlds × dock/orbit/deep-space + six canonical hyperlanes: Hydian Way, Corellian Run, Triellus, Hutt Space Corridor, Kamino Approach), **but the engine still hardcodes the GCW graph in `engine/npc_space_traffic.py` (the `ZONES` dict)**, and the CW file is inert pending an "F.X Space Pivot" drop that never landed. *(This is a gift: the content exists; only the wiring is missing.)*
- **Player-facing GCW text is everywhere:** Guide 05 documents live Corellia/Kessel systems and room blocks 55–76 reserved for them; the Republic HQ is "Nar Shaddaa — Corellian Sector Promenade"; Guide 11 says "The Empire's presence is felt here"; combat compares clone armor to "stormtrooper armor"; RP examples send players to Kessel.
- **Residue in code data:** `engine/housing.py` has Kessel/Corellia home types + view descriptions; `engine/missions.py` `SPACE_MISSION_TYPES` lists `kessel_approach`/`corellia_orbit`; smuggling routes (audit) terminate at the dead worlds.

**Why critical for fun, not just economy:** every Empire/Old-Republic/Corellia/Kessel reference contradicts the game's core pitch ("we pivoted to CW so Jedi make sense"). New players learn the galaxy from these guides — they're being taught the wrong map. This is immersion debt on the front door.

## C2 — Death has two rulebooks; the harsher one is live [CRITICAL]

The combat & medical guides promise: *"Equipment you had equipped is preserved; loose inventory may be lootable; −1D for 30 minutes."* The code (`engine/death.py`) is **already correctly zone-gated** — secured zones give instant respawn-with-gear and no corpse; contested/lawless create a corpse (2h/4h decay). **But the corpse snapshot drops *everything* — equipped gear + inventory + resources** (`_snapshot_and_clear_inventory`), not just loose inventory. So:

- The *consent model is already there* (it's the security-zone backbone, §2.8) — good news; the reconciliation is narrower than "rewrite death."
- The *divergence* is precise: the guide says equipped gear is preserved; the code drops it. **Bring the code to the guide** — preserve equipped gear, drop only loose inventory — and the trust break and the fun problem both resolve.

## C3 — Playstyles diverge in fiction but converge in mechanics [HIGH — marquee opportunity]

Everywhere: the *fiction* of who you are is richly differentiated (faction, species, HQ, rank ladder, guild); the *mechanics of what you do to earn and progress* are uniform (everyone runs the mission board, harvests, trades, fights the same way). The systems to differentiate them **already exist** (smuggling, bounty escrow, the espionage intel suite, sabacc, crafting, perform) — they're just not wired into per-archetype loops. **This is the highest fun-per-effort change in the game** and it dovetails with the economy: differentiated loops give each playstyle its own faucet/sink character without a uniform grind. Full spec in Part VII.

## C4 — The economy is unmeasurable and lacks a high-tier sink [CRITICAL — see companion audit]

Summarized from `SW_MUSH_Economy_Audit_FINAL.md`: ~80% of credit flows bypass the `credit_log` dashboard (you can't see the money supply); ship repair is free and ships are never destroyed (the rich have no drain — a veteran banks ~87k cr/week with <10% sunk, a ratio that *falls* with wealth); and the "medical/stipend sinks" are actually transfers. Phases 1 and 3 fix this — visibility first, then a fun-positive sink.

## C5 — The narrative layer and the mechanical layer don't talk [MEDIUM — big amplifier]

Plots are archived transcripts that don't move territory or spawn runs; world events spike faucets but aren't surfaced as story beats; the Director is powerful but invisible. Connecting them is low-cost, high-impact: plots that drive stakes, Director events as the engagement heartbeat, faction intent that reshapes the economy. Part VIII §B.

---

# PART IV — The integrated change set (fun + economy, one rev)

Folded together so you rev once. Economy items keep their audit IDs (R#); whole-game items are G#.

**Tier 0 — See the game (Phase 1).** R1: connect the credit ledger + dashboard + throttle valve + player-facing `+finances`.

**Tier 1 — Fix the era & fix trust (Phase 2).**
- G1: complete the CW space-layer migration (flip the engine to the existing CW `space_zones.yaml`; re-map trade/smuggling tables; relocate faction HQs; sweep all Empire/Corellia/Kessel guide + data text). Enlarges audit R3/R10.
- G2: reconcile death to the documented gentle model (preserve equipped gear, drop only loose inventory) + gear insurance + anti-griefing. Resolves audit F12 + the C2 divergence.

**Tier 2 — Make playstyles real + build the aspirational economy (Phase 3).**
- G3: wire eight archetype-specific playstyle loops from existing systems.
- R2 + R4 (fun-revised): the aspirational sink stack — ship customization/brokerage, home/city/faction prestige, vanity, *modest* repair backstop (5–8%), opt-in crafting catalysts (no resource decay).

**Tier 3 — Deepen the marquee fantasy + connect the layers (Phase 4).**
- G4: deepen the Force (more powers, lightsaber forms as a tactical choice, a Force progression path).
- G5: connect narrative ↔ mechanics (plots drive stakes; Director events as heartbeat; faction intent reshapes economy).

**Tier 4 — Liquidity, rhythm, hygiene (Phase 5, post-rev).**
- R7 (fun-revised): `+market` discovery + faction-flavored markets (no central AH).
- G6 / R5 / R6 / R9: daily/weekly rhythm + goal ladder; farming controls (P2P cap → ~1,500; NPC-buyback gating; meter hidden faucets); milestone-CP cap.

**Deliberately unchanged (protect):** combat, chargen, RP scaffolding, security-zone consent model, slow anti-grind CP, the Jedi's austerity, the trade-pricing math, physical player shops, generative-not-punitive world events.

---

# PART V — PHASE 1 SPEC: Instrument the economy

**Goal:** make the money supply visible and add the emergency lever, before changing anything else. Nothing in Phases 2–4 should be tuned blind.

**Verified state:** `db/database.py::log_credit(char_id, delta, source)` + `get_credit_velocity(seconds)` exist and are well-designed (they return faucet/sink totals, net, top faucets/sinks/earners). But `save_character(credits=…)` does **not** auto-log, and ~30 sites mutate credits directly via per-module `_award_credits` helpers (`engine/encounter_texture.py:45`, `engine/tutorial_v2.py:2186`, `parser/entertainer_commands.py:269`, etc.). Only ~10 of the 22 designed `source` tags are ever emitted. `ship_purchase` appears only in a test.

**Build:**
1. **`adjust_credits(char_id, delta, source, **meta)` chokepoint** — single function that updates balance *and* logs atomically. The only sanctioned way to move credits.
2. **Migrate all ~30 mutation sites onto it.** Order by largest unmeasured flow first: crew wages → (ship repair, once Phase 3) → vendor buy/sell → harvest → entertainer → city tax → Director contracts → remainder. Each site passes a distinct `source` tag (see the tag list seeded across Parts VI–VIII).
3. **`@economy` admin command + web panel** surfacing `get_credit_velocity` over selectable windows (24h / 7d / 30d): faucet/sink totals, net, top tags, top earners, and the **sink-to-faucet ratio by wealth tier** (the key diagnostic from the audit — it should *rise* with wealth; today it falls).
4. **Velocity alerts** — flag when net creation exceeds a threshold over a window.
5. **`@economy throttle <pct>`** — a global multiplier on NPC faucet payouts (the EVE payout-scaling valve). Build the lever before it's needed.
6. **Player-facing `+finances`** — a lightweight personal earnings/spending summary. Players enjoy seeing their numbers, and it makes economic choices feel meaningful (free once the chokepoint exists).

**Acceptance:** every credit faucet and sink in the game appears on `@economy`, tagged; the §5 audit model can be re-derived from live data.

**Effort:** medium. **Risk:** low (invisible to players). **Dependency:** none. **Do first.**

---

# PART VI — PHASE 2 SPEC: Era migration & death reconciliation

**Goal:** finish the Clone Wars pivot in the space layer and all player-facing content, and reconcile death to one fair, documented, consensual model. Fixes the two CRITICAL trust/immersion findings and three economy items (dead trade/smuggling routes, the loss sink).

## A. The CW space-layer migration (G1)

**Verified state — this is half-done:** the correct CW graph already exists as content in `data/worlds/clone_wars/space_zones.yaml` (24 zones, canonical hyperlanes). The engine ignores it and hardcodes the GCW graph in `engine/npc_space_traffic.py` (`ZONES` dict). The CW file's own header says it's waiting on an "F.X Space Pivot" drop. **Phase 2 is that drop.**

**Build:**
1. **Flip the engine to the data.** Era-parameterize `npc_space_traffic.py` to load `space_zones.yaml` via the world loader instead of the hardcoded `ZONES` dict. Retire the GCW graph (or gate it behind the GCW world for any legacy use). *This single change makes the six-world map live.*
2. **Re-map trade goods** onto the six worlds per the companion audit's Appendix C (source ≈70% / demand ≈140%): ore (Tatooine/Geonosis → Kuat/Coruscant), industrial parts (Kuat → frontier), electronics/droid-parts (Geonosis/Kuat → markets), medical/bacta (Kamino → war/frontier), foodstuffs (Coruscant → barren worlds), luxury (Nar Shaddaa → core), weapons (Nar Shaddaa → conflict zones), spice/contraband (Nar Shaddaa → core black market). Fix `engine/trading.py::TRADE_GOODS`.
3. **Re-point smuggling top tiers** off Kessel/Corellia to Nar Shaddaa / a deep-Outer-Rim node, retaining the 3,000–8,000 pay bands and high patrol risk; re-theme interdiction from "Imperial" to Republic/CIS. Fix `engine/smuggling.py::ROUTE_DEFS`.
4. **Relocate the starter-ship vendor** off Corellia (Spacer Quest step 27) to a CW world — Kuat (shipyards) or a Nar Shaddaa broker. Fix `engine/spacer_quest.py`.
5. **Relocate the Republic HQ** off the "Corellian Sector Promenade" to an era-appropriate CW Republic presence; update the faction guide.
6. **Sweep all residue:** Kessel/Corellia home types + view descriptions in `engine/housing.py`; `kessel_approach`/`corellia_orbit` in `SPACE_MISSION_TYPES`; X-Wing/Y-Wing/A-Wing/B-Wing/TIE hulls in `data/starships.yaml`; "Empire"/"stormtrooper"/Kessel references across **all guide text** (Guides 05, 06, 10, 11, 20, 24 confirmed to contain it); Empire/Rebel payroll language in docs.

**Note on scope:** this is a content-migration project, not a one-line data tweak — the audit under-scoped it as "re-point a table." But the heaviest piece (the topology) is already authored; the work is wiring + table re-maps + a text sweep.

## B. Death reconciliation (G2)

**Verified state:** `engine/death.py` is already zone-gated (secured = instant respawn-with-gear, no corpse; contested/lawless = corpse, 2h/4h decay; credits never drop; −1D wounded debuff). The divergence is narrow and precise: `_snapshot_and_clear_inventory` drops **everything** (equipped + inventory + resources), but the guide promises **equipped gear is preserved, only loose inventory drops.**

**Build:**
1. **Bring code to the guide.** Modify `_snapshot_and_clear_inventory` so equipped gear stays on the character; only **loose (un-equipped) inventory + resources** snapshot to the corpse. This is the single highest-trust fix in the game — it makes the documentation honest.
2. **Gear insurance (D4 in Phase 3, but design it here):** generalize the BH insurance model — players can insure a loadout (pay a premium, recover a replacement on death in a lawless zone). Converts gear-loss from a churn mechanic into a *choice with a hedge*, and adds a willingly-paid sink. *(Implementation lands in Phase 3 with the rest of the aspirational economy; the death model in Phase 2 must be insurance-aware.)*
3. **Anti-griefing (audit R8):** diminishing/zero corpse loot on repeated kills of the same target within a window; a short loot-protection/respawn-grace timer for the victim. Kills the camp-a-weaker-player pattern without removing risk.
4. **Rescale the bounty insurance hit** to flat-plus-percentage so low-value PC bounties still deter (audit F12).
5. **Reward-in-risk:** confirm the best harvest/materials/anomalies concentrate in lawless zones (they largely do) so the consensual risk is *opt-in for reward*, the fun engine the whole model rests on.
6. **Legibility:** an unmissable threshold warning when crossing into a lawless/contested zone ("Death here means losing what you carry"). Consent requires knowing.

**Acceptance:** the guide and the code agree; death in a lawless zone is a consensual, insurable, story-generating risk, not a mugging; gear loss still leaves the economy on uninsured deaths (the sink survives).

**Effort:** medium (migration is content-heavy but low-tech; death change is surgical). **Risk:** medium (touches world data and a core mechanic). **Dependency:** Phase 1 (ledger) so re-mapped routes are measured. **Blocks:** Phase 3 (the playstyle loops assume the CW map and the reconciled death model).

---

# PART VII — PHASE 3 SPEC: Playstyle loops & the aspirational economy

**Goal:** turn eight fantasies that share one earning loop into eight *distinct* economic playstyles, and build the high-tier sink as an **aspirational economy** players spend into willingly. The marquee fun rev + the economy's missing sink, shipped together because they're two halves of one flow.

**Verified hooks (this is mostly content/config/wiring, not new tech):**
- `engine/missions.py::generate_faction_mission()` sets `faction_code`+`faction_rep_required`; `available_missions_for_char()` already filters faction missions by rep. A `FACTION_MISSION_CONFIG` is the documented extension point.
- `engine/organizations.py` stores a per-rank JSON `permissions` list (e.g. `faction_comms`, `lead_npc_squad`). Commissary = new permission + gated vendor.
- `engine/espionage.py` already has structured, sealable, tradeable intel reports (capped at 10). The spy loop exists; it needs a *demand sink*.
- `engine/vendor_droids.py::get_faction_shop_modifier` (faction-rep pricing); `engine/world_events.py` (generative Director events); trophy wall + ship nickname + housing/cities (aspirational substrate) all exist.

## A. The eight loops

Each: **Fantasy · Signature verb · Income character · New work · Ledger tags · Event hook.**

**A1. Smuggler — "outrun the blockade."** Verb: the contraband run (evade patrols, deliver to black-market drop). Spiky high-variance. *New:* smuggler-reputation track unlocking higher tiers/better drop prices; bias this player's space encounters toward patrol/contraband/contact. Tags: `smuggling`, `smuggling_fine`. Event: new `CRACKDOWN` (+1 patrol tier, window) — the smuggler's high-risk holiday.

**A2. Bounty Hunter — "track the mark."** Verb: claim → track → collect; BH override = consent on the claimed PC target. Steady-mid + PC-bounty spikes. *New:* rescale insurance hit (flat+%); a `+hunt` tracking affordance (last-known-zone hints, skill-gated) so the hunt is a *verb*; aspirational Guild-rank perks (Veteran gear, a title). Tags: `bounty`, `bh_*`. Event: `BOUNTY_SURGE` (exists).

**A3. Spy / Intel — "know it first" (the gem).** Verb: gather + *sell* sealed intel. Low-violence, knowledge income. *New — the missing demand sink:* a **faction intel desk** (permission-gated NPC per faction) that *buys* reports matching the faction's current interests for credits + rep, priced by freshness/quality margin; **intel decay** (freshness matters); tie report value to live Director/faction-intent state. Converts intel from flavor toy to real loop *and* connects narrative↔economy. Tags: new `intel_sale`. Event: new `INTELLIGENCE_THAW`.

**A4. Republic / CIS Officer — "serve the war."** Verb: war-effort contracts + requisition. Stable/salaried; the *spending* side (requisition) shines. *New:* populate `FACTION_MISSION_CONFIG` for Republic+CIS; add a **`commissary` permission** to mid+ ranks + a commissary vendor selling rank-appropriate gear at a faction discount (a sink that *feels* like requisition); make stipends feel like pay (visible pay cycle). Tags: `mission`, new `commissary_purchase`, `faction_payroll`. Event: war-front pushes spike contracts.

**A5. Hutt / Criminal — "build the empire."** Verb: run the rackets (dens, territory tax, vice, criminal-org treasury). Org-scale/accumulative. *New:* let a Hutt-faction org **operate a sabacc den in a claimed room** so the house cut flows to the org treasury (player-controlled revenue — the criminal fantasy); theme harvest/city tax as "the Cartel's cut"; Vigo aspirational trappings. Tags: route sabacc cut to org treasury as `sabacc_rake` (currently unlogged — fixes audit F15). Event: new `SPICE_DEMAND`.

**A6. Jedi — "the Force, not credits" (austere by design).** Verb: train + mentor (Padawan/Master bond, trials, knighting) + Force mastery. Intentionally minimal income. *New for Phase 3:* **none on the economy — protect the austerity.** Phase-3 deliverable is aspirational *status* in-fiction: Temple standing, robe/saber styling (cosmetic), Knight/Master titles. Force *gameplay* depth is Phase 4. **Do not add a Jedi credit faucet.** Tags: `faction_payroll` (austere stipend).

**A7. Crafter / Trader — "arm the galaxy."** Verb: the supply chain (source quality materials → craft → sell to players). Invest-and-return. *New:* ensure Phase-2 trade re-map gives real spreads; **opt-in crafting catalysts** (NPC reagents that *improve* output quality/success, never a mandatory tax — replaces resource decay). Note: `+market` discovery (Phase 5) is what makes the *selling* side scale — flagged dependency. Tags: new `crafting_catalyst`, `trade_goods`, `resource_vendor`. Event: `TRADE_BOOM` + material-scarcity.

**A8. Entertainer / Social — "the cantina life."** Verb: perform + be the social nexus (scenes/places). Modest/steady/social. *New:* **meter the perform faucet** through the ledger (currently unlogged) and keep it modest; **audience-weight** it (bonus when other players are present at your place) so it rewards being a hub, not a solo timer-tap — connects the faucet to the RP fabric; entertainer-renown as a status track. Tags: new `entertainer` (audience-weighted). Event: `CANTINA_BRAWL` (exists; 2× perform).

## B. The aspirational economy (the high-tier sink, fun-positive)

Absorbs the modeled ~40–90k/week mid-to-veteran surplus through *willing* spending. Priority order; (B1)+(B2) carry the load.

**B1. Ship customization & brokerage (primary sink).** A real `+shipyard`/`+shipbuy` storefront at **Kuat** selling hulls (the 98k–1.5M catalog becomes live capital sinks) *and* customization: paint/livery (1,000–5,000 cr), named-registration flair (existing `nickname`), interior modules, and the **crafted ship-component fit path** (Shield Mk.II, Hyperdrive Tuning Kit — already in `data/schematics.yaml` — become installable stat upgrades). The EVE lesson: people spend fortunes making their ship *theirs*. Tags: `ship_purchase` (make live), `ship_customization`, `ship_upgrade`. Repeatable as new lines release.

**B2. Home & city prestige (major sink, lowest-risk).** Charge for what's free/flavor today: trophy-wall expansion beyond 10 slots, premium furnishings, home upgrades; for orgs, city monuments, faction-hall décor, named landmarks. Status you show visitors. Tags: `home_prestige`, `city_prestige`.

**B3. Faction vanity & regalia (cheap, strong status pull).** Paid titles, faction colors, ceremonial/cosmetic gear per playstyle. Gives the Jedi (no credit loop) and the officer an aspirational outlet that isn't power. Tags: `vanity_purchase`, `title_purchase`.

**B4. Gear insurance (sink + risk-enabler).** Insure a loadout (premium → replacement on lawless death). Makes the consensual-loss model fun. Tags: `gear_insurance_premium`, `gear_insurance_payout`.

**B5. Friction backstop (modest, not the main event).** `damcon` field-repair stays **free** (skill moment); full spacedock restoration costs **~5–8% of hull value** ("yard fees", fun-revised down from the audit's 8–15%). Fuel stays as-is. Tags: `ship_repair`, `fuel`.

## C. World-event heartbeat

Wire each playstyle to its "holiday" so Director events spike the relevant loop: `BOUNTY_SURGE`→hunter, `TRADE_BOOM`→trader/crafter, `CANTINA_BRAWL`→entertainer, new `CRACKDOWN`→smuggler, `SPICE_DEMAND`→Hutt, `INTELLIGENCE_THAW`→spy, war-front→officer. Surface active/upcoming events prominently; opportunities, never penalties.

## D. Build order within Phase 3

1. Ledger tags first (all new `source` tags, so every new flow is measured day one).
2. Faction mission configs + commissary (A4, A1, A5) — highest leverage, lowest risk (config+content on working machinery).
3. Aspirational economy B1–B3 — the big sink; lands here so faucets don't outrun it.
4. Spy demand sink (A3) + Hutt empire assembly (A5) — the two loops needing real new wiring.
5. Gear insurance (B4) + repair backstop (B5) — completes the consensual-loss model.
6. Entertainer metering/audience (A8); smuggler/hunter polish.
7. World-event hooks (C).

**Effort:** high (but mostly content/wiring). **Risk:** medium. **Dependency:** Phases 1+2. **This is the rev's center of gravity.**

---

# PART VIII — PHASE 4 SPEC: Force depth & the living world

**Goal:** deliver the signature fantasy of the era at a depth worthy of it, and make the rich narrative apparatus *drive* the mechanical world. Two workstreams.

## A. Deepen the Force (G4)

**Verified state:** `engine/force_powers.py` has 8 powers across Control/Sense/Alter (combination powers roll the weakest), 2 dark-side powers auto-accruing DSP with a harsh fall check at 6+ (`DSP_FALL_THRESHOLD=6`, Willpower vs DSP×3). The `ForcePower` dataclass (`key`, `name`, `skills`, `base_diff`, `dark_side`, `combat_only`, `target`, `description`) is clean and extensible. Combat treats a lightsaber as **flat 5D, armor-bypassing**, defended by Lightsaber/Melee Parry. The dark-side ratchet is *good design* — keep it.

**The problem:** for the defining fantasy of the Clone Wars, the Force has *less tactical depth than the blaster system*. A blaster duel has more decisions than a lightsaber duel. This is the highest-value unspecced *fun* investment in the game.

**Build (keep the Force economically inert and non-tradeable — deepen *gameplay*, not economy; keep canon figures scripted-only per existing policy):**
1. **More powers, organized as a tree.** Expand well beyond 8 across the three disciplines, with tiered prerequisites (a Control adept unlocks deeper Control powers). The `ForcePower` dataclass already supports this; add a `tier`/`prereq` field. Canonical R&E powers to draw from: Absorb/Dissipate Energy, Force Push/Pull (telekinetic combat), Lightsaber Combat (the power, distinct from the skill), Danger Sense, Combat Sense, Hibernation Trance, Force of Will, etc.
2. **Lightsaber forms as a tactical choice** — the key combat-depth addition. Map forms onto the *existing* parry/attack economy so they're a per-stance decision, not new tech:
   - **Form III (Soresu, defensive):** bonus to parry / deflect, penalty to attack — the survival stance.
   - **Form V (Djem So, aggressive):** bonus to attack/riposte, penalty to defense — the kill stance.
   - **Form IV (Ataru, acrobatic):** mobility/initiative bonus, stamina cost.
   - A `stance <form>` command sets the active form; it modifies the combat dice math the same way cover/aim do. Suddenly a lightsaber duel has the same round-to-round decisions as a blaster fight, *plus* the form layer.
3. **A Sense/precognition tactical layer:** powers that grant initiative re-rolls, danger warnings, or defensive bonuses — making Sense matter in combat beyond a flat Perception boost.
4. **Telekinetic combat depth:** Force Push (knockback/prone), Pull (disarm at range), object-throwing — turning Alter into a tactical toolkit, not just Injure/Kill.
5. **Tie Force progression to the Padawan/Master bond** (Phase 3's Jedi status track + the existing `+teach`): Masters unlock/teach deeper powers and forms to Padawans, making the bond the *mechanical* spine of Jedi growth, not just a social marker.

**Acceptance:** a lightsaber duel is as tactically rich as a blaster fight; a Jedi player has a multi-month *gameplay* progression (powers + forms) that matches the multi-month CP arc; the dark-side ratchet still bites.

## B. Connect narrative ↔ mechanics (G5)

**Verified state:** plots (`Guide_20`) are archival transcripts; the Director (`engine/director.py`) drives world events/faction intent/news but is largely invisible to players; world events are generative but not surfaced as a heartbeat.

**Build:**
1. **Plots that drive stakes.** Let a plot optionally bind to mechanical outcomes — a faction-war plot that shifts territory influence on resolution; a smuggling-ring plot that spawns real contraband runs; a bounty-saga plot that posts real PC bounties. The narrative layer *changes the world* instead of only recording it.
2. **The Director as the engagement heartbeat.** Surface active/upcoming Director events prominently (the daily/weekly *exciting* rhythm), let faction-intent shifts visibly reshape the economy (a CIS push raises war-front contract pay; spikes the relevant playstyle holidays from Phase 3 §C). This is the connective tissue that makes the galaxy feel *alive* rather than *systemic*.
3. **Faction intent → economy.** Wire the Director's faction-intent state to the faction mission configs and the intel desk demand (Phase 3 A3/A4) so the economy *breathes* with the war's narrative.

**Acceptance:** a plot can move territory or spawn runs; players feel the Director as a present force; the war's narrative state visibly drives the economy.

**Effort:** high (Force depth is real new design; narrative wiring is medium). **Risk:** medium. **Dependency:** Phase 3 (the playstyle loops + Jedi status track are what Force depth and faction-intent wiring plug into). **Payoff:** the signature fantasy delivered + a living world.

---

# PART IX — Phase 5 (post-rev): markets, rhythm, hygiene

Not part of the core 1–4 rev, but the natural follow-on (full detail in the working drafts / companion audit):
- **R7 — `+market` discovery + faction-flavored markets** (read-only index of live listings/buy-orders, no central AH — preserves RP; completes the crafter's selling side).
- **G6 — daily/weekly rhythm + goal ladder** (light, opt-in, leaning on the Director; pressure-free).
- **R5/R6 — farming controls** (P2P cap → ~1,500; NPC crafted-gear buyback gating; meter/cap city tax + Director + entertainer faucets).
- **R9 — milestone-CP cap** (keep the long mastery arc honest).

---

# PART X — Open design decisions (yours to own)

These set tone, not math; recommendations given:

1. **Ship destructibility (the master lever).** *Rec:* keep ships repairable for launch; build the aspirational sink + modest repair; hold destructibility in reserve as the lever to pull only if measured (post-Phase-1) inflation proves stubborn.
2. **Gear-insurance generosity.** *Rec:* tune so insured runs are clearly safer-but-costlier, uninsured runs are the high-adrenaline play.
3. **Aspirational vs. punitive sink mix.** *Rec:* ~80% aspirational / ~20% friction; revisit if data shows aspiration under-draining.
4. **Resource sink form.** *Rec:* opt-in catalysts, no decay.
5. **Force-tree breadth & form count.** *Rec:* enough breadth that a Jedi's gameplay progression spans months and rivals the blaster system's depth — but resist power-creep that trivializes non-Force play.
6. **How hard to push daily/weekly hooks.** *Rec:* gentle, opt-in; this is an RP MUSH, not a retention funnel.
7. **NPC loot drops.** *Rec:* keep zero (crafting-centric is cleaner and distinctive); the rare-materials-in-risk-zones loop gives combat builds their feed.
8. **CP milestone budget.** How much direct CP may bypass the cap before mastery feels unearned.

---

# PART XI — Acceptance tests & sequencing

## Sequencing (and the one hard ordering rule)

Phase 1 → Phase 2 → Phase 3 → Phase 4, then Phase 5. **The hard rule:** the Phase-2 era migration restores dead trade/smuggling routes (raising faucet income), so the Phase-3 aspirational sink must land *with or immediately after* it — never re-open the faucets without the new sink, or you accelerate the inflation the audit modeled. Phase 1 ships first unconditionally because it converts every downstream tuning decision from guesswork to measurement.

## Acceptance tests (the "did we succeed" check)

Use the player-experience arcs, specialized:
- **New smuggler:** feels the spice-run fantasy in week 1 (the contraband run is *different* from a courier mission); saves toward a first ship on the live CW map.
- **Mid spy:** earns a real living *selling intel* without firing a shot.
- **Veteran (any combat/space playstyle):** is the biggest *spender*, not just earner — a painted, named, upgraded ship; a trophy wall; a faction title. The audit's <10% sink ratio *rises* with wealth.
- **Jedi:** credit-poor and content; progression is the bond, the trials, Temple standing, and (Phase 4) a Force/forms gameplay arc as deep as the blaster system.
- **Roleplayer:** ignores the optimization layer entirely; loops and events are pull, never pressure.
- **The galaxy:** reads as Clone Wars throughout (no Corellia/Kessel/Empire); death is a consensual, insurable risk that matches its documentation; the Director is a felt presence; `@economy` shows every faucet/sink tagged with a healthy, rising-with-wealth sink ratio.

If those hold against live `get_credit_velocity` data, the rev succeeded: eight Star Wars fantasies, one healthy economy, the signature Force fantasy delivered, in a galaxy that finally reads as the era it's set in.

---

## One-paragraph summary for the implementer

Instrument the economy first (Phase 1: the `adjust_credits` chokepoint + dashboard + throttle + `+finances`) so nothing downstream is tuned blind. Then finish the Clone Wars pivot and fix trust (Phase 2: flip the engine to the already-authored CW space map, re-map trade/smuggling, relocate faction HQs, sweep all Empire/Corellia/Kessel text; and reconcile death by preserving equipped gear so the code matches the guide, with insurance + anti-griefing). Then ship the rev's center of gravity (Phase 3: wire eight faction-flavored playstyle loops from existing systems, and build the high-tier sink as an *aspirational* economy — ship/home/faction prestige — that players spend into happily, with repair/fuel as a modest backstop and opt-in catalysts instead of resource decay). Then deliver the signature fantasy and a living world (Phase 4: deepen the Force with a power tree and lightsaber *forms* mapped onto the existing parry/attack economy, and wire plots/Director/faction-intent to drive real mechanical stakes). Keep markets-discovery, daily rhythm, and hygiene for Phase 5. Every economist recommendation survives; the feel-bad ones were reshaped into fun. Protect combat, chargen, the RP scaffolding, the slow CP, the trade math, and the Jedi's austerity — they're already right. Tune everything against live ledger data once Phase 1 exists.

---

*End of integrated game design report, Phases 1–4. Companion deliverable: `SW_MUSH_Economy_Audit_FINAL.md`.*
