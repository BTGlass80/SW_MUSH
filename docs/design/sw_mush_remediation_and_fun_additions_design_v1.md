# SW_MUSH — Audit Remediation & Fun-Additions Design (consolidated)

**Date:** 2026-06-01
**Status:** v1.0 — implement-from. Consolidates the two FINAL handoff audits and the chosen fun additions into one sequenced plan.
**Consolidates / supersedes (as the working plan):** `SW_MUSH_Integrated_Game_Design_Report_Phases_1-4_FINAL.md`, `SW_MUSH_Economy_Audit_FINAL.md` (both retained as the reference money-model and design rationale; their finding IDs F#/G#/R# are carried through here for traceability).
**Basis:** Verified at the symbol level against **`SW_MUSH_upload_20260601_1731.zip`** (HEAD *after* the `cw_era_compliance_space_missions` drop of 2026-06-01). Where this doc and the two audits disagree on what's done, **this doc is current** — the audits were prepared against the 2026-05-31 build, one drop stale.
**Confidence:** Code-state claims are grep-verified at HEAD (Appendix A). Proposed values/designs are first-cuts to playtest against live ledger data once the ledger ships, not laws.

---

## Part I — Reconciled state: where we actually are

The single most important correction to the audits: **the 06-01 drop did the *space-traffic + missions* half of the era migration, but the *economic* and *content* halves are untouched — and the half-migration appears to have turned three off-era flows into broken ones.**

### I.1 What the 06-01 drop closed (era migration, partial)

The drop fixed the zone graph and everything that *derives* from it:

- Ship registry: 10 GCW hulls + 1 junk key dropped (34 → 23 templates); CW hulls live.
- CW zone graph wired in (`npc_space_traffic._load_zone_graph`); `authority` field on all 24 CW zones.
- Mission zone pools and smuggling **dock** zones now derive from the live graph (follow the era automatically).
- Per-authority patrols (Republic ARC-170 / CIS Vulture / Hutt Z-95 / neutral Consular) + de-Imperialized hail/boarding/anomaly flavor.
- `FACTION_MISSION_CONFIG` = the five canonical CW slugs; legacy `empire`/`rebel` keys + objective tables removed; login rewicker migrates stored codes.
- Spacer-quest *banner triad + faction dialogue* de-Imperialized.

This is real progress and it's tested (89 + 149/150 in sandbox). It is **not** a codebase-wide CW sweep, and the handoff said so.

### I.2 What it left open — and the part that is now actively broken

The drop changed the *zones*; it did not touch the code that still hardcodes dead-planet **destinations**. In the live CW era, **Kessel and Corellia do not exist as landable worlds** (their planet definitions live only under `data/worlds/gcw/planets/`; there is no `clone_wars/planets/kessel.yaml` or `corellia.yaml`). Yet:

- **Cargo trade is dead-mapped.** `engine/trading.py::TRADE_GOODS` — 7 of 8 routes still `source`/`demand` Kessel/Corellia (lines 43–93).
- **The top two smuggling tiers dead-end.** `engine/smuggling.py::ROUTE_DEFS` — `spicerun`→`kessel`, `corerun`→`corellia` (126–127); patrol-heat table still keys kessel/corellia (136–137); per-destination dropoff branches at 285/291. With dock zones now derived from the CW graph, these destinations have no dock zone → the runs cannot complete.
- **The starter-ship tutorial spine dead-ends.** `engine/spacer_quest.py` — the ship is still bought from **Lira Shan on Corellia** (Coronet Starport, line 826), the crew shipwright **Venn Kator on Corellia** (745/752), and an objective still requires landing on **Kessel and Corellia** (639–645).
- **Content residue.** `engine/housing.py` Kessel/Corellia home types (655–674), shop types (2282–2314), view strings (1324–1325), and an `("empire","corellia")` home key (543); guide text (Kessel in 8 guides, Corellia in 6, "Empire" 3, "Imperial" 2, "stormtrooper" 1); `engine/organizations.py::_SPEC_CONFIG_BY_FACTION` still carries an `empire` chargen block (handoff TODO `T2.CW.spec_config_cleanup`).

**Why this is the top priority:** before the 06-01 drop, the GCW graph still contained those zones, so the flows limped along on the wrong map. Now the graph is CW-only, so the same references likely **fail** rather than read wrong. A broken starter-ship quest is a launch-blocker. *Verify on hardware:* run a `corerun` smuggle and the spacer-quest ship purchase in-client — five minutes confirms whether they dead-end. This is the textbook "infrastructure-complete ≠ content-complete" / half-staged-migration failure mode.

### I.3 The four critical findings — real status at HEAD

| ID | Finding | Audit severity | Status now |
|----|---------|:--:|---|
| **F3 / G1** | GCW dead-planet residue (trade, smuggling, starter quest, housing, guides, chargen) | CRITICAL | **PARTIAL** — graph + missions done; trade/smuggling-destinations/starter-quest/housing/guides/chargen **open & likely broken** |
| **F1** | ~80% of credit flows bypass the ledger; no chokepoint | CRITICAL | **OPEN** — no `adjust_credits`; 8 `log_credit` callers vs 69 `save_character` sites |
| **F2 / F4** | Ship repair free; no ship market (no high-tier sink) | CRITICAL/HIGH | **OPEN** — `damcon` still a free skill check; `ship_purchase` only in a test |
| **F12 / G2** | Death drops *all* gear vs guide's "equipped preserved" | CRITICAL | **OPEN** — `_snapshot_and_clear_inventory` wipes equipped + loose + resources |
| F5 | Resources never decay | HIGH | **OPEN** (by recommendation, becomes opt-in catalysts — unbuilt sink, not a defect) |
| F14 | Cosmetic era residue | LOW | **OPEN** — folds into the F3 content sweep |

---

## Part II — Remediation plan (re-sequenced for current HEAD)

The audits' lowest-regret order holds — *un-break and instrument first, then drain, then deepen* — but it compresses because part of Phase 2 already shipped, and the monolithic "G1" splits cleanly along an economy-risk seam (below).

**Drop 0 — Finish the era migration (URGENT, launch-blocker). [F3, F14, G1 remainder]**
The fix flagged as not-to-lose. Splits along economy risk:
- **0a — Un-break the dead-ends (no income risk; do first).** Re-point smuggling destinations off Kessel/Corellia to Nar Shaddaa / a deep-Outer-Rim node (keep pay bands + patrol risk); fix the spacer-quest waypoints/NPCs (relocate Lira Shan + Venn Kator to a CW world — Nar Shaddaa broker or Kuat; rewrite the "land on Kessel/Corellia" objective to CW planets); sweep housing home/shop/view residue + the `_SPEC_CONFIG_BY_FACTION` empire block + the guide text. *This restores suppressed/broken flows to their intended level; it does not raise income above design intent.*
- **0b — Trade re-map (re-opens 7 routes → faucet income; sequence-gated).** Re-map `TRADE_GOODS` source/demand onto the six CW worlds (Economy Audit Appendix C). Per the hard ordering rule, land this **with or after the ledger (Drop 1)** so the restored faucets are measured, and ensure the aspirational sink (Drop 3) lands before population grows enough for them to inflate.

**Drop 1 — Ledger chokepoint (Phase 1). [F1, F10, F15]**
`adjust_credits(char_id, delta, source, **meta)` — atomic update + log, the only sanctioned way to move credits. Migrate the ~30 mutation sites (order: crew wages → vendor → harvest → entertainer → city tax → Director → rest; ship repair joins when Drop 3 adds it). `@economy` admin command + web panel over 24h/7d/30d (faucet/sink totals, net, top tags, top earners, **sink-to-faucet ratio by wealth tier**), velocity alerts, `@economy throttle <pct>`, and player-facing `+finances`. Invisible, low-risk; everything downstream tunes blind without it.

**Drop 2 — Death reconciliation (Phase 2). [F12, G2, R8]**
Surgical change to `_snapshot_and_clear_inventory`: preserve **equipped** gear on the character; snapshot only **loose (un-equipped) inventory + resources** to the corpse (note: the current docstring frames the all-drop as "the design" — the *guide* is the authority; bring code to guide). Make the death model insurance-aware (payout lands in Drop 3); add anti-griefing (diminishing/zero corpse loot on repeated kills of the same target in a window + victim respawn grace); rescale bounty-insurance to flat-plus-%; add an unmissable lawless/contested threshold warning ("death here means losing what you carry").

**Drop 3 — Playstyle loops + aspirational sink (Phase 3). [G3, R2, R4]**
The rev's center of gravity. Ledger tags first; then faction mission configs + commissary (A4/A1/A5 — config on working machinery); then the aspirational sink stack — ship customization/brokerage at Kuat (make the 98k–1.5M catalog a live capital sink + paint/livery/modules/crafted-component fits), home/city/faction prestige, vanity/regalia, gear insurance, and a *modest* repair backstop (~5–8% of hull, `damcon` stays free); opt-in crafting catalysts (no decay); spy intel-desk demand sink (A3) + Hutt den-in-claimed-room treasury revenue (A5); entertainer audience-weighting; world-event holidays. **Lands with/after Drop 0b so faucets don't outrun the sink.**

**Drop 4 — Force depth + the living world + the fun additions (Phase 4). [G4, G5 + new]**
Force combat depth (power tree + lightsaber forms mapped onto the existing parry/attack economy + telekinetic/Sense tactical layer), narrative↔mechanics wiring (plots drive stakes; Director as heartbeat; faction intent reshapes economy), **plus the three chosen additions in Part III** — social/non-combat Force (III.1), earned status (III.2), communal goals + persistent threat (III.3). These three slot here because they plug into the same substrate (Force, Director/faction-intent, the status layer) and several are low-risk, high-fun.

**Drop 5 — Liquidity, rhythm, hygiene (Phase 5). [R5, R6, R7, R9, G6]**
`+market` discovery (no central AH); farming controls (P2P cap → ~1,500; NPC crafted-gear buyback gating; meter/cap hidden faucets); milestone-CP cap; gentle opt-in daily/weekly rhythm.

**The hard ordering rule (now sharper):** Drop 0b re-opens the dead trade routes (more faucet income), so the aspirational sink (Drop 3) must land *with or immediately after* it, and the ledger (Drop 1) should precede or accompany 0b so the restored faucets are measured. Drop 0a carries no income risk and can ship immediately. **Never re-open the faucets without the sink, or you accelerate the modeled top-down inflation.**

---

## Part III — Fun additions (specced to implement-from)

The two audits are, by design, an audit of *existing* systems. These three are *net-new* fun, chosen for high fantasy-payoff and low economy risk. All three are **economically inert or status-only** — they do not add a credit faucet, by deliberate consistency with the economist's lens and the Jedi-austerity thesis.

### III.1 Social / non-combat Force (idea 1)

**Fantasy.** The Force's most distinctive power isn't damage — it's *presence, foresight, and influence*. The Jedi who senses a lie in a negotiation, feels a disturbance, pushes a suggestion, or shares a thought across the Master/Padawan bond. This makes the Jedi fantasy whole **without** a credit faucet — it's status, story, and gameplay, which is exactly what the report prescribed for the Jedi.

**Verified substrate.** `engine/force_powers.py` has 8 powers via the `ForcePower` dataclass (`key, name, skills, base_diff, dark_side, combat_only, target, description`); `combat_only` defaults False; combination powers roll the weakest pool (`min(pools, key=lambda p: p.dice*3 + p.pips)`). Presence-sensing partly exists: `life_sense` and `sense_force` already `target="room"`. The DSP ratchet (`DSP_FALL_THRESHOLD=6`, Willpower vs DSP×3) is good design — keep it.

**Build.**
1. **Fix the mind-trick classification.** `affect_mind` is currently `dark_side=True` (awards DSP). In R&E the mind trick (Affect Mind, Control+Sense+Alter) is *not* inherently dark. Split into: a **light influence/suggestion** path (no DSP; a contested social skill check) and a **coercive/dominating** use that stays dark (DSP). The iconic non-dark "you don't need to see his identification" should not fall a light Jedi.
2. **Add a Sense/Control social + precognition branch** (`combat_only=False`, economically inert, non-tradeable):
   - **Telepathy (Receptive/Projective):** the *mechanical* spine of the Master/Padawan bond — bonded pairs can sense each other's state / send short impressions. Ties Force growth to the bond, per the report.
   - **Farseeing / Danger Sense:** precognition as *narrative* — surfaces a personalized Director-driven **Force vision** (a story beat / foreshadowing hook), and in tense moments grants a defensive warning / initiative re-roll (the Sense-in-combat layer the report wanted).
   - **Sense intent / lie / disturbance:** a perception-of-truth check usable in social scenes (read sincerity of an NPC; feel a death/disturbance in the room or zone).
   - **Magnify Senses / Life Detection:** extend the existing room-sensing into graded awareness.
3. **Consent + canon guardrails.** Influence on an **NPC** is a skill check resolved by the engine. Influence on a **PC** requires the security-zone/consent ethos — never an involuntary override of another player; surface it as an offered effect the target can accept/RP, mirroring the consent model that is the game's backbone. Open-world influenced NPCs are **non-canon** (canon figures remain scripted-only per existing policy). `force_sensitive` stays **derived state**, never a `save_character` kwarg.

**Economy interaction.** None. No faucet, no tradeable artifact. Status/story only.

**Acceptance.** A Jedi has meaningful non-combat Force verbs in a scene (sense, suggest, foresee, bond); the light mind trick no longer accrues DSP; Force visions arrive as personalized Director beats; the Master/Padawan bond has a telepathy mechanic. **Effort:** medium (extends an existing, clean dataclass + new resolution paths + Director-vision hook). **Risk:** low-medium (the consent path for PC influence needs care). **Dependency:** the Director-event surfacing from G5 for visions; otherwise standalone.

### III.2 Earned status — deeds, titles, memorials (idea 5)

**Fantasy.** Status you *earned* beats status you *bought*, and it's free of inflation concern. "First Knight of the server," bounties claimed, lanes discovered, a memorialized heroic death. This pairs *with* the report's bought-vanity sink (Drop 3 B3), not against it.

**Verified substrate.** `engine/achievements.py` (604 lines) is a real, data-driven engine: achievements loaded from data, `_BY_KEY`/`_BY_EVENT` indexes, event-trigger matching (`_matches_filters`), unlock notifications with icons (`★ ACHIEVEMENT UNLOCKED`), and a completion/progress query. **The missing layer is not an engine — it's *displayed, worn* status.**

**Build.**
1. **A title / honorific display layer.** Let certain achievements *confer a wearable title/honorific* shown on the sheet, `who`, and in-room (e.g. "Knight of the Order", "Ace of the Hydian Way", "Survivor of the Maw"). A `+title` command to select among earned titles. This is the status marker the achievements engine currently lacks.
2. **Flagship *deed* achievements** that confer those titles: combat/bounty deeds, exploration "firsts" (ties to III's exploration substrate and the social-Force Force-nexus discoveries), faction-service milestones, Jedi trial/knighting markers.
3. **Memorialized death (optional, opt-in).** A character who dies meaningfully can be memorialized (a named marker / news beat / a small legacy nod on the player's next character) — turns the death system you're touching in Drop 2 into a *legacy* system, not just a loss event.

**Economy interaction.** None (status markers, not dice/CP). Protects the mastery arc and adds no faucet. *Optional* tie-in: some bought-vanity items (Drop 3 B3) can be **gated behind** an earned title, so the sink and the status layer reinforce.

**Acceptance.** Achievement unlocks can grant wearable titles; `+title` works; a handful of flagship deeds exist; an opt-in memorial path closes the loop with Drop 2. **Effort:** low-medium (display layer + data definitions on an existing engine). **Risk:** low. **Dependency:** Drop 2 for the memorial tie-in; otherwise standalone.

### III.3 Communal goals + a persistent threat (idea 6)

**Fantasy.** A small RP community rallies hardest around a *shared* objective with a real win/lose state — "hold Kamino against a Separatist push" — and around a *persistent adversary* that gives the war stakes beyond contract-pay multipliers. This complements the report's faction-intent wiring (G5) rather than duplicating it.

**Verified substrate.** `engine/director.py` already drives world events / faction intent / news (the report's "engagement heartbeat"); `engine/world_events.py` is generative; the 06-01 drop added per-zone `authority`. Territory/influence already has a control loop. The pieces exist; the gap is *framing them as a shared, surfaced objective with a state*.

**Build.**
1. **Communal objectives** the Director posts with a visible progress/win-lose state (a CW front: defend/contest a world; a galaxy-wide relief or interdiction effort). Participation is open across playstyles (a smuggler runs the blockade, an officer holds the line, a Jedi protects civilians, an entertainer keeps morale). Surface prominently as the weekly *exciting* rhythm; opportunities, never penalties.
2. **A persistent external threat (CW-appropriate).** A roaming, generative adversary — a **CIS droid offensive** that pressures a front, **pirate incursions**, **Hutt enforcement** sweeps, or a **roaming non-canon bounty hunter** that actually tracks high-DSP PCs (a soft consequence for the dark path, tying to the DSP ratchet). No Imperial content. Any named canon antagonist remains **scripted-only**, never an open-world Ollama NPC.
3. **Wire to faction intent (G5).** A communal-objective outcome shifts faction-intent state, which (per G5) reshapes contract pay / intel-desk demand — so the war's narrative *breathes* through the economy.

**Economy interaction.** Rewards lean **status and aspirational** (titles via III.2, prestige currency for Drop 3 B-stack, faction rep) rather than raw credits — keeping the faucet discipline. Any credit reward routes through the Drop 1 ledger and the `@economy throttle`.

**Acceptance.** The Director can post a communal objective with a win/lose state surfaced in-client; a persistent CW-appropriate threat applies pressure players can rally against; outcomes move faction intent and (via III.2) confer earned status. **Effort:** medium-high (objective state machine + threat generator on existing Director/world-event substrate). **Risk:** medium. **Dependency:** G5 (faction-intent→economy wiring) and III.2 (status rewards) for full payoff; a basic objective can ship without them.

---

## Part IV — Integrated sequencing

| Drop | Contents | Income risk | Gated by | Why here |
|------|----------|:--:|---|---|
| **0a** | Un-break dead-ends: smuggling destinations, spacer-quest waypoints/NPCs, housing/guide/chargen residue | none | — | Launch-blocker correctness; restores suppressed flows to intent |
| **0b** | `TRADE_GOODS` CW re-map (Appendix C) | **raises** | Drop 1 (measure) + Drop 3 (sink) close behind | Re-opens 7 routes; hard ordering rule applies |
| **1** | Ledger chokepoint + `@economy` + `+finances` + throttle | none | — | Tune nothing blind; do early/concurrent with 0b |
| **2** | Death reconciliation (equipped preserved) + anti-grief + insurance-aware | minor | — | Highest-trust fix; sets up insurance + III.2 memorial |
| **3** | Playstyle loops + aspirational sink (B1–B5) + insurance payout | drains | 0b, 1 | Center of gravity; the sink that absorbs the surplus |
| **4** | Force combat depth + narrative wiring **+ III.1 social Force + III.2 earned status + III.3 communal/threat** | inert/status | G5 + III.2 for full payoff | Signature fantasy + living world + the three fun additions |
| **5** | `+market`, farming controls, milestone-CP cap, gentle rhythm | tightens | 3 | Liquidity + hygiene last |

The three fun additions are intentionally placed in Drop 4 because they share substrate (Force dataclass, Director/faction-intent, the achievements/status layer) and are economically inert/status-only — so they carry no inflation-sequencing constraint and can be scoped as self-contained sub-drops within Phase 4.

---

## Part V — Open decisions (yours to own)

1. **First drop:** **Drop 0a** (recommended — un-break the launch-blocker; no income risk) vs **Drop 1** (the audit's mandated-first for *economy* work; invisible/low-risk). Recommendation: 0a first (a broken starter quest at launch is worse than an unmeasured economy at 5–50 players), then Drop 1 immediately, then 0b.
2. **Relocation targets for the era fix:** starter-ship vendor + crew shipwright → Nar Shaddaa broker or Kuat shipyards? Smuggling top-tier destination → Nar Shaddaa or a named deep-Outer-Rim node?
3. **Mind-trick split (III.1):** how wide is the "light influence" path vs. where coercion turns dark? (Tone call on Jedi grey areas.)
4. **PC-influence consent model (III.1):** offered-effect-the-target-accepts (recommended, matches the consent backbone) vs. a contested roll. Confirm.
5. **Memorial scope (III.2):** marker/news only, or a small mechanical legacy nod on the next character? (Watch the CP-bypass concern, F11.)
6. **Persistent-threat flavor (III.3):** which CW adversary leads — CIS offensive, pirates, Hutt enforcement, or the high-DSP bounty hunter? Reward currency: status/prestige-only (recommended) vs. a throttled credit component.

---

## Appendix A — Verification evidence (symbol-level, at HEAD)

Grep findings against `SW_MUSH_upload_20260601_1731.zip` that ground Part I (per the project's "symbol-level evidence before claiming delivered/undelivered" discipline):

- **F1 (ledger):** no `def adjust_credits` in engine/parser/db; `log_credit` called in 8 files; `save_character` in 69. `ship_purchase` source tag appears only in `tests/test_session51_economy_hardening.py:226`.
- **F2/F4 (ship sink):** `damcon` is `DamConCommand` (a skill check); spacedock strings exist (`space_commands.py:4214/4272`) with no credit path; no live ship-purchase sink.
- **F3 (trade):** `trading.py::TRADE_GOODS` source/demand kessel/corellia at lines 43–93.
- **F3 (smuggling):** `smuggling.py::ROUTE_DEFS` `spicerun`→kessel (126), `corerun`→corellia (127); patrol-heat keys (136–137); dropoff branches (285/291).
- **F3 (starter quest):** `spacer_quest.py` Lira Shan/Corellia (826), Venn Kator/Corellia (745/752), land-on-Kessel/Corellia objective (639–645).
- **Planets gone:** Kessel/Corellia defined only under `data/worlds/gcw/planets/`; absent from `data/worlds/clone_wars/planets/` and from `space_zones.yaml` (header: "drops Kessel + Corellia").
- **F12 (death):** `death.py::_snapshot_and_clear_inventory` reads full `_get_inventory_raw`, snapshots items + resources to corpse, wipes both; no equipped-vs-loose distinction (docstring calls the all-drop "the design").
- **F5 (resources):** no `resource_decay` symbol in engine.
- **F14 (housing/guides/chargen):** `housing.py` kessel/corellia home types (655–674), shop types (2282–2314), view strings (1324–1325), `("empire","corellia")` key (543); guides reference Kessel ×8, Corellia ×6, "Empire" ×3, "Imperial" ×2, "stormtrooper" ×1; `organizations.py::_SPEC_CONFIG_BY_FACTION` empire chargen block (handoff TODO `T2.CW.spec_config_cleanup`).
- **III.1 substrate:** `force_powers.py` 8 powers (`accelerate_healing`, `control_pain`, `remain_conscious` [Control/self]; `life_sense`, `sense_force` [Sense/room]; `telekinesis` [Alter/target]; `injure_kill`, `affect_mind` [dark]); `affect_mind` is `dark_side=True`; combination rolls weakest pool.
- **III.2 substrate:** `achievements.py` (604 lines) — data-driven, `_BY_KEY`/`_BY_EVENT`, `_matches_filters`, icon unlock notification, completion query; no worn-title layer.
- **III.3 substrate:** `director.py` (events/intent/news), `world_events.py` (generative), per-zone `authority` (06-01), territory influence loop.

---

*End. Next action: implementation begins at Drop 0a (per Part V.1), pending your go.*
