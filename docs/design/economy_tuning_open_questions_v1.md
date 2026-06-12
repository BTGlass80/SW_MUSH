# Economy Tuning — Open Questions Ledger

**Date opened:** 2026-05-25 (at SYN.6 wave close)
**Status:** Standing — appended to as new feature drops introduce new
tuning knobs. Consumed by `T2.ECON.review` (whole-game economist pass,
deferred until SYN is complete per Brian's call).

---

## Why this document exists

During the SYN.6.a → SYN.6.b → SYN.6.c wave (May 25 2026, three drops
in one session), Claude picked numeric values for a number of
mechanics without explicit Brian sign-off. Most are design-doc
numbers (preserved verbatim from `contestable_wilderness_design_v2.md`),
but several were pure Claude choices in the absence of a specified
value — kyber attune cooldown shape, quality bands, skill-margin
scaling caps, etc.

Brian raised the concern explicitly:

> "Are we considering the economy? Like, can a force sensitive
> user walk up to a landmark and just spam harvest over and over
> again? We want to make sure the stuff we're adding is tuned
> right. Rarity, supply/demand, etc."

The right answer was: not enough. Mechanics were shipped that PASS
their tests but compound in supply-side ways that weren't computed
end-to-end. This document is the ledger.

The whole-game economist pass (T2.ECON.review) is deliberately
deferred until SYN is shipped — doing it mid-SYN derails forward
progress; doing it after SYN means the economist looks at a
complete system rather than a moving target. This ledger lets the
forward picks stay traceable without losing them.

---

## How to use this document

Each entry has:

- **The value picked** and where in code it lives.
- **The alternatives considered** (or that should have been
  considered, in retrospect).
- **The supply/demand math** if computed, or the gap if not.
- **The specific concern** — what would go wrong if the pick is
  off, and the smallest playtest/observation that would tell.

Entries are organized by SYN drop. As SYN.7+ ship, new entries will
append.

---

## SYN.6.a — Active harvest (shipped 2026-05-25)

### TUN.harvest.cooldown_per_region — 30 min per-region per-character

- **Site:** `engine/harvest.py::HARVEST_COOLDOWN_SECS`
- **Design source:** `contestable_wilderness_design_v2.md` §2.5.2
- **Alternatives:**
  - 30 min per-region (current) — design number
  - 30 min global — prevents region-cycling farm; tighter loop
  - 60 min per-region + 30 min global floor — caps both axes
  - Reset on death — combat-tied
- **Supply math:**
  A player cycling through 5+ wilderness regions per session
  could harvest 5+ × (yield/30min). At the lawless-control band
  (400-800cr base, +20%/band skill margin uncapped, 4 metal + 3
  chemical + 2 rare per craft), a long session can fill inventory
  to crafter-ready levels in 1-2 hours of play.
- **Concern:** 30min/region is the design number; per-region is
  the right axis. No session-level ceiling means a determined
  harvester can fill inventory in one session. Maybe acceptable
  for the "non-PvP crafter lane" Brian wants, but needs playtest.

### TUN.harvest.non_owner_tax_rate — 15%

- **Site:** `engine/harvest.py::NON_OWNER_TAX_RATE`
- **Design source:** §2.5.3
- **Alternatives:**
  - 10% — softer visitor friction
  - 15% (current, design)
  - 20-25% — heavier owner advantage, stronger claim incentive
  - Variable by region security (lawless 10%, contested 20%)
- **Concern:** Design number. Preserve unless economist pass
  surfaces it as a friction issue.

### TUN.harvest.yield_bands — 6-row table (100-200 → 400-800 cr)

- **Site:** `engine/harvest.py::YIELD_TABLE`
- **Design source:** §2.5.2 verbatim table
- **Concern:** End-to-end credit-per-hour-of-harvest math hasn't
  been computed. Economist should derive: typical Jedi-faction
  Knight playing 1h, harvesting 2 regions, gets X credits. Then
  compare against vendor prices, weapon costs, ship maintenance,
  etc.

### TUN.harvest.skill_margin_credit_bonus — +20% per 5-pt margin, uncapped

- **Site:** `engine/harvest.py::_MARGIN_CREDIT_BONUS_PER_BAND`
- **Alternatives:**
  - +20% per band uncapped (current) — 50-margin gives 11× base
  - +20% per band capped at +100% — exceptional rolls double base
  - +10% per band, capped at +50% — softer curve
- **Concern:** Uncapped scaling means Master-tier harvesters can
  get extreme credit outliers. Tests use 12D Survival → consistent
  large margins. Real-play margins likely tamer but 10D+ Survival
  is achievable post-progression.

### TUN.harvest.t5_rare_chance — 10% at Control tier

- **Site:** `engine/harvest.py::_T5_RARE_CHANCE`
- **Concern:** Currently the only path to q100 "rare" stacks. Will
  become moot when SYN.8 lands and q100 "rare" is design-reserved
  for anomaly drops. At that point, reduce or remove.

---

## SYN.6.b — Weekly region quality variance (shipped 2026-05-25)

### TUN.weekly_variance.band — 0.7×..1.3× per-type per-week

- **Site:** `engine/region_quality.py::QUALITY_MIN, QUALITY_MAX`
- **Design source:** §2.5.5 verbatim
- **Concern:** Design number; preserve unless economist pass
  surfaces it as too narrow (limited crafter-travel pull) or too
  wide (unstable economy).

---

## SYN.6.c — T5 crafting + kyber attune (shipped 2026-05-25)

### TUN.kyber.cooldown — 24h per-landmark per-character ⚠ HIGH PRIORITY

- **Site:** `engine/kyber_attunement.py::ATTUNE_COOLDOWN_SECS`
- **Alternatives:**
  - **24h per-landmark per-character (current)** — 4 force-resonant
    landmarks in current CW content × 24h = **4 shards/Jedi/day
    theoretical max**
  - 24h per-character GLOBAL — any landmark consumes the daily;
    **1 shard/Jedi/day**
  - Weekly per-character — ceremonial; **1 shard/Jedi/week**
    aligns with Padawan-trial canonical narrative
  - No cooldown but per-landmark consumed-this-week — landmark goes
    quiet for the week; preserves single-Jedi pacing but adds
    cross-Jedi competition (one Jedi gets it, others wait)
- **Supply math:**
  - Master-crafted lightsaber needs 1 kyber. Once-and-done per
    character (lightsabers don't break in current item engine).
  - Current shape: a Jedi can craft 4 lightsabers/day or accumulate
    indefinitely. **Grossly oversupplied** for a one-and-done need.
  - Reasonable shape: 1 kyber/Jedi/week → 1 lightsaber upgrade
    cycle every 1-2 weeks; matches canonical pacing.
- **Concern:** **HIGH PRIORITY** — this is the single most likely
  pick to be off. Per-landmark cooldown was the easy implementation
  choice; per-character (or per-week) is probably the right design
  choice for scarcity. Needs explicit Brian call:
  "Is kyber common-for-Jedi or ceremonial-for-Jedi?"

### TUN.kyber.quality_band — q75 floor, q95 ceiling, +5Q per margin band

- **Site:** `engine/kyber_attunement.py::QUALITY_FLOOR, QUALITY_CEILING`
- **Alternatives:**
  - Floor q60, ceiling q90 — matches existing crafting tier
    descriptors (Good=60+, Superior=80+, Masterwork=90+)
  - Floor q75 (current, matches T5_MIN_QUALITY), ceiling q95 — every
    successful attune is T5-craftable; **no duds**
  - Floor q70, ceiling q100 — exceptional rolls cap at q100, but
    removes SYN.8-reserved-tier semantics
  - Variable per-landmark — content-axis dial
- **Concern:** **No-duds design is generous.** A skilled Jedi (8D
  Scholar) auto-passes DC 11 every time. Every cooldown produces
  T5-grade material. Pre-launch playtest should confirm: is the
  right shape "always get something" (current) or "sometimes get
  nothing"?

### TUN.kyber.skill_difficulty — DC 11 (Moderate)

- **Site:** `engine/kyber_attunement.py::ATTUNE_DIFFICULTY`
- **Alternatives:**
  - DC 11 (Moderate, current) — typical Jedi clears easily
  - DC 15 (Difficult) — Padawan strains, Knight passes, Master
    auto-passes; tighter gate on quality outcomes
  - DC 21 (Very Difficult) — only Masters reliably succeed; cap
    matches T5 schematic-difficulty band; very ceremonial
- **Concern:** Typical Jedi starter (3D Knowledge) succeeds ~50%,
  trained (4D+) nearly always. Pairs with no-duds quality floor.

---

## T5 schematics (data/schematics.yaml — shipped 2026-05-25)

### TUN.t5_schematic.difficulty_band — 25-28 (Very Difficult)

- **Site:** `data/schematics.yaml` — `t5_*` entries
- **Alternatives:**
  - 25-28 (current) — Master crafter with 8D+ skill + Wild Die
    typical
  - 30-32 (Heroic) — even Masters need exceptional rolls; "genuine
    endgame" framing
  - 20-23 (Difficult top) — overlaps existing T4 ceiling; might
    dilute the T5 boundary
- **Concern:** T1-T4 ceiling is 20. T5 at 25-28 is clearly above.
  Playtest with a Master crafter should confirm 50-70% success at
  intended progression tier.

### TUN.t5_schematic.component_quality_bands — T5 mat q75+, standard q50-65

- **Site:** `data/schematics.yaml` — `t5_*` components `min_quality`
- **Alternatives:**
  - Current: q75 T5 mat + q50-65 standard mats
  - Tighter: q75 T5 mat + q65-75 standard mats — pulls in more
    standard-material economy
  - Looser: q75 T5 mat + q40-50 standard mats — only the T5 mat
    matters; standard mats are filler
- **Concern:** Current bands lock out Master crafters who can't
  source q50+ standard materials. Pairs with weekly variance
  (which can push a region's metal to 0.7× → harder to find q50+
  stacks). Real bottleneck question is whether the standard-mat
  floor is the right shape.

### TUN.t5_schematic.t5_mat_quantity — 1 per craft

- **Site:** `data/schematics.yaml` — `t5_*` components `quantity`
- **Alternatives:**
  - 1 per craft (current) — minimum scarcity
  - 2-3 per craft for more potent items (e.g. master-grade armor)
    — differentiates T5 outputs by gating cost
  - Variable by output_type — lightsaber 1, ship part 2, armor 1
- **Concern:** Flat 1-per-craft means every T5 output costs the
  same in T5-mat terms. Differentiation currently comes from T1-T4
  component costs; could also come from T5-mat costs.

### TUN.harvest_node.fallback_policy — Region-scoped fallback

- **Site:** `engine/harvest.py::_is_harvest_node`
- **Alternatives:**
  - Region-scoped (current) — incremental authoring; un-audited
    regions stay open
  - Global fallback — only triggers if NO room anywhere has the flag
  - Hard gate — all rooms require flag from day one
- **Concern:** Acceptable as transitional design; economist pass
  should confirm long-term shape after content pass completes.

---

## Standing process — what to do for future drops

When shipping a feature that introduces tuning knobs:

1. **Prefer the design doc number.** If `contestable_wilderness_design_v2.md`
   or other authoritative spec lists a value, use it verbatim and
   note "design number, no debate needed" in this ledger.
2. **For knobs not in the design doc**, pick a defensible value
   and add an entry to this document with:
   - The value
   - The alternatives considered
   - The supply/demand math (or the gap)
   - The concern
3. **High-priority knobs** (those that could break the economy if
   off) get a ⚠ marker — flagged for explicit Brian call before
   playtest, not just for the economist pass.
4. **Append to `TODO.json::tunable_open_questions` array** at the
   end of every drop alongside CHANGELOG.md.

---

## Forward sections (to be appended)

## SYN.7.a — Tier 1 wilderness anomalies (shipped 2026-05-25, fix shipped 2026-05-25)

**Note:** SYN.7.a.fix (same day) closed the corner-cuts in original
SYN.7.a — Coruscant Underworld now has 5 templates (was 0), and 6
of the 10 templates resolve via real NPC combat rather than skill
check. Tuning entries below cover both the original 5 Dune Sea
templates and the new shape.

### TUN.anomaly.cadence_per_region — hourly tick + 0.4 chance → ~2.5h avg

- **Site:** `engine/wilderness_anomalies.py::CADENCE_TICK_INTERVAL, SPAWN_CHANCE_PER_TICK`
- **Design source:** §2.8 "every 2-3 hours per region"
- **Supply math (UPDATED post-fix):** Now 2 templated wilderness
  regions (Dune Sea + Coruscant Underworld) × 0.4 chance/h = ~0.8
  spawns/h across the world. Per-region cap 2 means a single region
  tops out at 2 concurrent. For a small playerbase that's about
  right.
- **Concern:** Aligned with design midpoint. Halving (0.2 → 5h avg)
  might better fit a sparse server. Note: regions without templates
  are silently skipped (e.g. if a future Endor wilderness ships
  before its templates), which is the intended fail-safe.

### TUN.anomaly.duration — 30 min

- **Site:** `engine/wilderness_anomalies.py::TIER1_DURATION_SECS`
- **Design source:** §2.8 verbatim
- **Concern (UPDATED post-fix):** Now matters more for combat
  templates — 30min must be enough for a player to (a) see the news,
  (b) travel to the anchor room, (c) finish a 3-NPC combat. Combat
  duration estimate: 3-5 rounds × ~30s per round = 2.5min. Travel
  + scan time likely 5-15min. Comfortable margin at 30min for solo,
  tight for groups coordinating. Preserve unless playtest shows
  late-arrival frustration.

### TUN.anomaly.max_per_region — 2 concurrent

- **Site:** `engine/wilderness_anomalies.py::MAX_PER_REGION`
- **Concern:** With 30min duration + 2.5h cadence, regions hover
  near 0-1 most of the time. Cap mostly matters for cold-start.

### TUN.anomaly.tier1_influence_delta — +5 to resolver's faction

- **Site:** `engine/wilderness_anomalies.py::TIER1_INFLUENCE_DELTA`
- **Design source:** §2.8 verbatim
- **Supply math (UPDATED post-fix):** +5 × ~8 spawns/day × 0.5
  resolve rate × 2 regions = ~40 inf/day per region per active
  faction. Foothold (50) in ~6 days, Dominant (200) in ~5 weeks.
  Note: combat templates have higher engagement cost (real combat
  vs skill check) but pay the same +5 — under-tuned vs effort? Or
  appropriate (combat templates pay better in credits + resources)?
  Open question for economist.
- **Concern:** Playtest should confirm progression curve.

### TUN.anomaly.tier1_resolution_dc — DC 13 (Moderate-Difficult)

- **Site:** `engine/wilderness_anomalies.py::TIER1_RESOLUTION_DC`
- **Alternatives:** DC 11 (easier — starters succeed half the time),
  DC 15 (harder — only trained reliably).
- **Concern (UPDATED post-fix):** Now only applies to 4 of 10
  templates (the skill-resolution ones: stranded_clone_scout,
  salvage_cache, crashed_cis_probe, factory_cache). Combat
  templates bypass DC entirely. Target ~70% success rate for
  intended-tier player (4D).

### TUN.anomaly.template_reward_bands — 100-600cr / 1-5 resource stacks q45-60

- **Site:** `engine/wilderness_anomalies.py::TIER1_TEMPLATES`
- **Concern (UPDATED post-fix):** Reward bands now span 100-600cr
  on success (Coruscant urban templates pay slightly higher: 200-
  600cr, reflecting higher risk + urban-corruption flavor). Resource
  quality bumped to q45-q60 (up from q30-60). Combat templates pay
  in success_reward only (no partial); skill templates pay
  success_reward OR fail_reward. End-to-end credit-per-hour math
  defers to economist pass.

### TUN.anomaly.fail_reward_existence — skill-only, fail consumes + partial reward

- **Site:** `engine/wilderness_anomalies.py::resolve_anomaly,
  _resolve_anomaly_skill, _resolve_anomaly_combat`
- **Concern (UPDATED post-fix):** fail_reward semantics now apply
  only to the 4 skill-resolution templates. Combat templates have
  fail_reward=0/0/0 (you fled or died — no payout). This is
  semantically cleaner: skill check has graceful failure; combat
  is binary. Per-template fail_reward bands preserved at 30-100cr
  for skill templates (~25% of success band).

### TUN.anomaly.template_distribution — REGION-TAGGED (closed by SYN.7.a.fix)

- **Site:** `engine/wilderness_anomalies.py::_pick_template`,
  per-template `regions: [...]` field
- **Resolution:** Templates declare a `regions: [...]` list (with
  REGION_ANY sentinel for universal). `_pick_template(region_slug)`
  filters the catalog and picks uniformly from matches. Dune Sea
  picks uniformly from 5 Dune-tagged templates; Coruscant Underworld
  picks uniformly from 5 Coruscant-tagged templates. **Closed**
  the prior "uniform across all 5" concern.
- **Open follow-up:** Within-region weighting (e.g. should
  `tusken_party` be more common in Dune Sea than `crashed_cis_probe`?)
  remains uniform-within-region. The economist pass can re-tune by
  adjusting per-template weights if needed.

### TUN.anomaly.combat_npc_counts — 1-3 NPCs per combat template (new in fix)

- **Site:** `engine/wilderness_anomalies.py::TIER1_TEMPLATES` —
  `combat_npcs: [...]` arrays
- **Choices made:**
  - 1-NPC templates: `wounded_animal` (average creature),
    `maze_rogue` (veteran creature), `bounty_hunter_rival`
    (veteran bounty_hunter)
  - 2-NPC templates: `black_sun_courier` (2 average thugs),
    `cis_sleeper_cell` (2 average b1_battle_droids)
  - 3-NPC templates: `tusken_party` (2 average + 1 novice thug)
- **Concern:** 1-NPC veteran templates (Maze rogue, rival hunter)
  are intentionally harder than 2-3 NPC average templates. Whether
  the reward differential (Maze rogue: 150-350cr; rival hunter:
  350-600cr; black_sun_courier 2 NPCs: 300-550cr) matches the
  effort differential is an open question. Combat-time math for a
  4D starter vs a veteran NPC: ~5-7 rounds = ~3min. vs average
  NPCs: ~3-4 rounds × 2-3 targets = sequential or AOE-style fight.
- **Open follow-up:** Playtest required. Veteran-NPC templates may
  need to pay more, or have name-loot drops to compensate.

### TUN.anomaly.combat_attribution_window — last_attacker_id (new in fix)

- **Site:** `parser/combat_commands.py` anomaly kill hook + bounty
  hook + WoW.3a — all use the same `c.last_attacker_id` chain
- **Choice:** Last-attacker-wins for the killing blow. Same as
  bounty board. Means in a two-player situation, whoever lands
  the final hit gets the reward (credits + resources + influence
  for their faction).
- **Concern:** Could create griefing (player A wears down NPCs,
  player B "steals" the kill). Bounty board has the same shape
  and has not been a problem in practice; carrying that precedent.
  Open follow-up: economist may want to consider damage-sharing
  proportional reward.

---

## SYN.7.b — Tier 2 wilderness anomalies (shipped 2026-05-25)

### TUN.t2_anomaly.cadence_per_region — 6h tick + 0.20 chance → ~30h avg

- **Site:** `engine/wilderness_anomalies.py::TIER2_CADENCE_TICK_INTERVAL, TIER2_SPAWN_CHANCE_PER_TICK`
- **Design source:** §2.8 "every 24-48 hours per region" — midpoint 36h. Implemented as 30h average (closer to lower bound, slight bias toward more action for a small playerbase).
- **Supply math:** 2 templated wilderness regions × 0.20/6h = ~0.067 spawns/h = ~1.6 spawns/day across the world. Per-region cap 1 means a region cannot accumulate; the 2h duration ensures the slot opens up before the next 6h tick most of the time.
- **Concern:** For 1-2 players online a couple hours/day, expected encounter rate is 1 T2 per day-or-two. Aligned with design. Worth playtest at sparse-server population.

### TUN.t2_anomaly.duration — 2h

- **Site:** `engine/wilderness_anomalies.py::TIER2_DURATION_SECS`
- **Design source:** §2.8 verbatim
- **Concern:** 2h is generous and matches the "coordinated group" design language. Multi-phase combat with travel + coordination time at 3-5 player count needs the buffer.

### TUN.t2_anomaly.max_per_region — 1 concurrent

- **Site:** `engine/wilderness_anomalies.py::TIER2_MAX_PER_REGION`
- **Choice:** Tier 2 is the headline event in a region. 1 concurrent reinforces that. Tier 1 cap (2) and Tier 2 cap (1) are independent — a region can hold both a Tier 1 + a Tier 2 simultaneously.
- **Concern:** Playtest could show 1 is too few for active regions, or too many for sparse ones. Independent of T1 cap means the dial can be tuned per-tier.

### TUN.t2_anomaly.influence_delta — +20

- **Site:** `engine/wilderness_anomalies.py::TIER2_INFLUENCE_DELTA`
- **Design source:** §2.8 "15-25 influence" — midpoint 20
- **Supply math:** +20 × ~1.6 spawns/day × 0.5 resolve rate × 2 regions = ~32 inf/day from Tier 2 (system-wide). Compare to Tier 1's ~40 inf/day per active faction. Tier 2 is rarer but pays 4× per resolve.
- **Concern:** Influence is the differentiator. Whether +20 is the right value vs effort (3-5 player coordination, 30+ min combat, named loot stakes) is an economist call.

### TUN.t2_anomaly.template_count — 5 templates (3 Dune + 2 Coruscant)

- **Site:** `engine/wilderness_anomalies.py::TIER2_TEMPLATES`
- **Choice:** Mirrors region distribution (Dune Sea has 3 sub-regions of wilderness, Coruscant has 1 wilderness region in the game today). Region parity from SYN.7.a.fix means at least 1 Coruscant template alongside Dune Sea ones; shipped 2 Coruscant for true diversity.
- **Concern:** SYN.8 should ship Coruscant T3 too. SYN.7.b's region parity is currently "3 Dune : 2 Coruscant"; expanding to "1:1" is a tuning option for the economist pass.

### TUN.t2_anomaly.reward_credits_band — 800-2400cr per template

- **Site:** `engine/wilderness_anomalies.py::TIER2_TEMPLATES` per-template `success_reward.credits`
- **Bands:** 800-1600 (Coruscant gang war), 900-1800 (Maze outbreak), 1000-2000 (Hutt convoy), 1100-2200 (CIS commando), 1200-2400 (Acclamator).
- **Choice:** Tiered roughly by phase count + difficulty. Acclamator (3 phases + named T5 mat) pays most; gang war (2 phases + named item) pays least.
- **Supply math:** SPLIT across participants in Tier 2. For 3-5 player team on Acclamator: 1800cr (median) / 4 = ~450cr per char per resolution. Compares to Tier 1 single-char band of 100-600cr. Multi-participant split means per-char Tier 2 credits are NOT 4× Tier 1 — they're roughly Tier 1 PLUS named loot. The named-loot piece (T5 mat) is where the real value lives.
- **Concern:** Whether multi-participant split feels good or bad to players is a playtest call. Alternative: every participant gets the full credit band (no split). Current implementation is more conservative; economist will tune.

### TUN.t2_anomaly.t5_mat_quality — q70

- **Site:** `engine/wilderness_anomalies.py::TIER2_T5_MAT_QUALITY`
- **Choice:** q70 is comfortably above the q60 schematic gate but below the q75 high-end. Lets a Tier 2 resolve immediately yield a usable mat for T5 schematics. Higher quality (q75+) would be Tier 3 territory.
- **Concern:** Quality differential between T2 mat drops (q70) and T3 mat drops (q80+ presumed for SYN.8) is the gradient. If T2 q70 feels too generous for Tier 2 effort, can dial to q65; if too stingy, q75.

### TUN.t2_anomaly.multi_participant_loot_distribution — credits/2..N split, resources shared full

- **Site:** `engine/wilderness_anomalies.py::_payout_combat_anomaly`
- **Choice:**
  - Credits: total pool divided equally by N participants.
  - Resources: each participant gets the full resource list (not split).
  - Influence: killer's faction only (+20).
  - Named loot: killer alone.
- **Concern:** Resources-as-shared is a simplification — resources are bulky-but-renewable, so sharing-full feels good and avoids "ugh I got fewer ores than X." Credits-as-split is the cost discipline. Named-loot-to-killer matches the bounty + WoW.3a pattern (killing-blow attribution).
- **Open follow-up:** Damage-contribution-weighted distribution (vs equal split) was considered and deferred. Engine doesn't track per-combatant damage today; building that surface is non-trivial.

### TUN.t2_anomaly.phase_count_per_template — 2 or 3 phases

- **Site:** `engine/wilderness_anomalies.py::TIER2_TEMPLATES` per-template `phases: [...]`
- **Choice:** 2-phase templates: Hutt convoy, Coruscant gang war. 3-phase templates: Acclamator, CIS commando, Maze outbreak. Roughly: simpler narratives (convoy, gang war) = 2 phases; more cinematic narratives (war wreck, strike team, predator outbreak) = 3 phases.
- **Concern:** Whether 3 phases is too many for solo or duo players is a playtest concern. The design specs "3-5 coordinating" so the upper end is fine; the lower end of "you and your buddy" might find a 3-phase Acclamator daunting. Economist pass + observation.

### TUN.t2_anomaly.npc_tier_progression — average → veteran → elite

- **Site:** `engine/wilderness_anomalies.py::TIER2_TEMPLATES` per-template `phases[N].combat_npcs[*].tier`
- **Pattern:** Most templates progress from `average`-tier NPCs in phase 0 to `veteran`-tier in middle phases to `elite` in the final phase (e.g. salvage commander, tactical droid commander, Maze alpha, Vigo lieutenant).
- **Concern:** Standard escalation curve; tracks the design intent. Whether `elite` is too strong or too weak vs intended-tier 3-5-player coordination is a per-archetype balance question that flows into the economist pass.

---

## SYN.8 — Tier 3 world bosses (shipped 2026-05-25)

### TUN.t3_anomaly.cadence_per_region — 24h tick + 0.10 chance → ~10-day avg

- **Site:** `engine/wilderness_anomalies.py::TIER3_CADENCE_TICK_INTERVAL, TIER3_SPAWN_CHANCE_PER_TICK`
- **Design source:** §2.8 "every 7-14 days per region" — midpoint 10.5. Implemented at ~10-day avg (slightly toward lower bound for more event density at low playerbase).
- **Supply math:** 2 templated wilderness regions × 0.10/24h = ~0.0083 spawns/h = ~1 spawn per 5 days across the world. Plus REGION_ANY templates can land in any region, doubling the practical density.
- **Concern:** For 1-2 players at small playerbase, a Tier 3 every 5 days feels right. Could be tightened to weekly+ if it feels too rare in practice.

### TUN.t3_anomaly.duration — 8h

- **Site:** `engine/wilderness_anomalies.py::TIER3_DURATION_SECS`
- **Design source:** §2.8 "~6-12 hour duration" — midpoint 9, implemented at 8h (small bias toward earlier expiry so the 24h cadence has slot rotation).
- **Concern:** 8 hours is long. Players need time to coordinate 8-16-person engagement per design language. For a small server with 1-2 players, 8h gives them all day to find time. Could shorten to 4h if too generous.

### TUN.t3_anomaly.max_per_region — 1 concurrent

- **Site:** `engine/wilderness_anomalies.py::TIER3_MAX_PER_REGION`
- **Choice:** A world boss IS the world event. Capping at 1 reinforces that. Independent of T1 + T2 caps — a region can have all three tiers simultaneously.

### TUN.t3_anomaly.influence_delta — +50

- **Site:** `engine/wilderness_anomalies.py::TIER3_INFLUENCE_DELTA`
- **Design source:** §2.8 literal (+50 to killing-blow faction)
- **Supply math:** +50 × ~0.1 spawns/day per region × 0.5 resolve rate × 2 regions × 2x for REGION_ANY = ~10 inf/day from T3 system-wide. Compare to Tier 2's ~32 inf/day. Tier 3 is much rarer but the per-resolve delta is the headline; +50 in one event swings the region balance.

### TUN.t3_anomaly.template_count — 4 templates (design literal)

- **Site:** `engine/wilderness_anomalies.py::TIER3_TEMPLATES`
- **Choice:** Krayt Dragon (Dune Sea), Maze Predator Apex (Coruscant), Crashed Separatist Capital Ship (any), Republic Lost Patrol (any). Matches design §2.8 verbatim.

### TUN.t3_anomaly.reward_credits_band — 6000-16000 cr per template

- **Site:** `engine/wilderness_anomalies.py::TIER3_TEMPLATES` per-template `success_reward.credits`
- **Bands:** 6000-12000 (Capital Ship), 7000-14000 (Maze Apex), 7500-15000 (Lost Patrol), 8000-16000 (Krayt — highest, hardest).
- **Choice:** Tiered roughly by perceived difficulty + iconic status. Krayt at top; Capital Ship lowest because the Capital Ship has the most NPCs total (9) — players already getting a long fight, the credits balance for time-spent.
- **Supply math:** SPLIT across participants. For 8-player krayt kill: 12000 / 8 = 1500 per char per resolve. Compares to Tier 2's ~450 per char per resolve at 4-player. T3 is roughly 3× the per-char credits of T2, BUT happens 1/8 as often per region. T3 is a credit-spike event, not a credit-stream.

### TUN.t3_anomaly.t5_mat_quality — q80

- **Site:** `engine/wilderness_anomalies.py::TIER3_T5_MAT_QUALITY`
- **Choice:** q80 is above T2's q70 but below the q90+ tier reserved for future legendary-tier crafting paths. Significantly improves T5 schematic gating (schematics gate at q60, but the higher the input quality the better the output stat-wise).

### TUN.t3_anomaly.scaled_t5_distribution — floor(N/4) pieces to top participants

- **Site:** `engine/wilderness_anomalies.py::_distribute_scaled_t5_mat`
- **Design source:** §2.8 "N pearls scaled to participation (floor(participants/4))" + "highest damage gets first pick, then descending"
- **Choice:**
  - `pieces = floor(N/4) * per_4_participants` (1 piece per 4 participants by default).
  - Consolation rule: minimum 1 piece for small teams of <4 (goes to killer alone).
  - Ranked by `kill_counts` (descending) — proxy for damage contribution since per-combatant damage tracking doesn't exist.
  - Killer wins ties (a logical "they landed the hit" tiebreaker).
- **Concern:** Kill count is a cruder proxy than damage. A wizard-glass build that does 200 damage per hit but lands 1 hit looks worse than a clone trooper doing 30 damage per hit landing 5 hits. Whether this matters at observed playerbase scale is empirical.
- **Open follow-up:** True damage-contribution tracking is logged as a future tuning concern. Would require hooking into combat.py's damage application.

### TUN.t3_anomaly.trophy_distribution — 1 trophy per participant

- **Site:** `engine/wilderness_anomalies.py::_grant_trophy`
- **Choice:** Every participant (anyone with `kill_counts > 0`) gets exactly one trophy item with `is_trophy: True`. Housing's `trophy_mount` can pick these up. Matches design §2.8 "every participating character a unique trophy (housing display)".
- **Concern:** None mechanical. The aesthetic question — whether one trophy per kill is enough vs unique-named trophies per role/contribution — is post-launch polish.

### TUN.t3_anomaly.during_contest_2x_cadence — DEFERRED

- **Design source:** §2.8 "During an active contest in that region: 2× cadence (krayts every 3-7 days when contested)."
- **Status:** Deferred. The wiring requires the anomaly tick to query `engine.contest` for active region contests, which couples two systems that have so far been independent.
- **Tracked here for the economist pass.** When (and if) wired, the implementation is straightforward (multiply spawn_chance by 2 if region is contested at tick time); the coupling decision is the cost.

### TUN.t3_anomaly.relocation_tile_mechanic — DEFERRED (abstracted as phase advancement)

- **Design source:** §2.8 "Multi-phase: at half HP, relocates to a new tile and players track it."
- **Status:** Currently abstracted: phase advancement narratively conveys "boss withdrew and re-emerges" via the phase intro text. The boss respawns in the next phase at the same anchor room, fresh HP. Players don't physically track to a new tile.
- **Concern:** Real multi-room relocation requires temporary-room generation + mid-combat NPC movement + player-tracking surface. Engineering cost is substantial; abstracted version captures the narrative beat. Logged for polish drop or post-launch.

### TUN.t3_anomaly.republic_lost_patrol_choice — DEFERRED (currently combat-only)

- **Design source:** §2.8 "Republic Lost Patrol... can be rescued for major faction rep + influence rewards or turned in to Separatist sympathizers for contraband."
- **Status:** Ships as combat-only — clear the CIS captors holding the Republic patrol. The binary rescue-vs-handover choice mechanic is deferred.
- **Concern:** A mid-combat or post-clear binary choice introduces a UI surface that doesn't exist for other anomaly templates. Designing it consistently with the existing parser combat flow is a polish-tier task.

### TUN.t3_anomaly.kill_count_as_damage_proxy — known limitation

- **Site:** `engine/wilderness_anomalies.py::award_combat_anomaly_reward` (kill_counts increment)
- **Choice:** Track kills, not damage. Cheap (one line in the existing hook), no combat.py coupling.
- **Concern:** Imperfect proxy. Heavy-hit-low-rate vs light-hit-high-rate builds map differently. Empirical question for the economist pass — if players game it, build the damage-tracking surface in combat.py.

---

## SYN.9 — Player-constructed buildings (shipped 2026-05-25)

### TUN.bldg.construction_time — 24h

- **Site:** `engine/buildings.py::CONSTRUCTION_TIME_SECS`
- **Design source:** §2.9.3 literal ("24 real-time hours")
- **Concern:** 24h is long for small servers. Players might construct a building, log off, and not see it complete in a single session. The check-back-tomorrow loop is intentional per design (gives building construction *weight*) but at sparse playerbase this could feel like "I logged in 3 days ago and now I have a residence." Acceptable; possibly shortened to 12h for the smallest servers via a future config knob.

### TUN.bldg.credit_costs — 5000-10000 cr per category

- **Site:** `engine/buildings.py::BUILDING_CATEGORIES` per-category `credit_cost`
- **Costs:** residence 5000, commerce_stall 6000, cultural_hall 7500, crafting_station 8000, garrison_annex 10000.
- **Design source:** §2.9.3 literal (table)
- **Supply math:** Compared to the SYN.7-anomaly Tier 2/3 reward bands (T2 per-participant ~450cr, T3 per-participant ~1500cr for an 8-player krayt), residence at 5000cr is ~10x a T2 resolve or ~3x a T3 share. Means 3-10 successful anomaly resolves to fund one building. Aligned with design's "buildings are meaningful investments."

### TUN.bldg.material_costs — 5-30 units per building

- **Site:** `engine/buildings.py::BUILDING_CATEGORIES` per-category `material_costs`
- **Per-category totals:** residence 10 (5 metal + 5 organic), commerce_stall 8 (8 metal), cultural_hall 13 (8 metal + 5 organic), crafting_station 15 (10 metal + 5 composite), garrison_annex 20 (15 metal + 5 chemical).
- **Supply math:** A 4-character Tier 2 anomaly clear shares ~5-8 units of each resource type to each participant. So one Tier 2 clear gets you most of the way to a residence. Two T2 clears comfortably funds a crafting_station. Aligned.
- **Concern:** Whether these scale with playerbase is empirical. If the harvest system supplies materials too aggressively, building construction becomes trivial. Economist pass.

### TUN.bldg.slot_capacity_default — 2 per landmark

- **Site:** `engine/buildings.py::DEFAULT_LANDMARK_SLOT_CAPACITY`
- **Choice:** Midpoint of design's "0-5 depending on landmark capacity." Overridable per-room via `properties.building_slot_capacity`. Force-resonant landmarks override to 0.
- **Concern:** A city with say 10 landmarks gets 20 slots — generous. Could be tightened to 1 per landmark for smaller server populations; the per-room override allows landmark-by-landmark tuning when needed.

### TUN.bldg.min_rank_to_construct — rank 3

- **Site:** `engine/buildings.py::MIN_RANK_TO_CONSTRUCT`
- **Design source:** §2.9.3 literal ("rank 3+")
- **Concern:** Rank 3 in a player city's owning org is mid-progression. Citizens who joined and haven't ranked up can't build. Reinforces that buildings are an org-loyalty reward; appropriate.

### TUN.bldg.demolish_refund_pct — 25%

- **Site:** `engine/buildings.py::DEMOLISH_REFUND_PCT`
- **Design source:** §2.9.3 literal
- **Concern:** 25% means most of the cost is sunk; building decisions stick. Aligned with weight-of-decisions design intent.

### TUN.bldg.rebuild_discount_pct — 10%

- **Site:** `engine/buildings.py::REBUILD_DISCOUNT_PCT`
- **Design source:** §2.9.3 literal ("10% off materials")
- **Concern:** Only applies if same owner + same category + same room. Discourages "demolish-and-rebuild for refund" abuse (you only get 25% refund + 10% discount on rebuild = much less than original cost; rebuilding makes you net-negative on materials).

### TUN.bldg.evict_notice_secs — 2 days

- **Site:** `engine/buildings.py::EVICT_NOTICE_SECS`
- **Design source:** §2.9.3 literal
- **Concern:** 2-day notice protects owners from arbitrary mayor whim while still allowing eventual mayor authority. Aligned.

### TUN.bldg.residence_storage_cap — 50 items

- **Site:** `engine/buildings.py::BUILDING_CATEGORIES['residence']['storage_cap']`
- **Choice:** 50 is generous. Players' main inventory caps are typically 20-30; the residence is meaningful extra storage. Design says "tier-3-equivalent housing... lockable, with storage." Tier 3 housing in `engine/housing.py` has a similar cap.
- **Concern:** Whether residence storage cannibalizes the standard housing system (`engine/housing.py`) is a design-coherence question. Resolution: residences in landmark rooms are wilderness-coupled; housing is city-coupled. Both can coexist; tuning pass.

### TUN.bldg.garrison_npc_count — 2

- **Site:** `engine/buildings.py::GARRISON_NPC_COUNT`
- **Design source:** §2.9.3 literal ("2 additional defending NPCs")
- **Concern:** Each garrison adds 2 veteran-tier NPCs. A landmark with 2 garrison annexes adds 4 defenders. If multiple landmarks in a city each have garrison_annex, the total defender count scales. Could matter in contest scenarios; the economist pass should observe.

### TUN.bldg.crafting_station_bonus — +1D

- **Site:** `engine/buildings.py::BUILDING_CATEGORIES['crafting_station']['skill_bonus_dice']`
- **Design source:** §2.9.3 literal ("+1D bonus")
- **Concern:** +1D is the WEG D6 sweet spot for a single-stage bonus. Crafting consumer integration is deferred — when wired into `engine.crafting`, observe whether +1D feels right for the construction effort.

### TUN.bldg.cultural_hall_cp_bonus — +1 daily CP

- **Site:** `engine/buildings.py::BUILDING_CATEGORIES['cultural_hall']['cp_bonus_per_day']`
- **Design source:** §2.9.3 literal ("+1 daily CP")
- **Concern:** CP is the character progression currency. +1/day means a citizen who spends 5+ min at a cultural hall daily gains roughly 1 extra rank-up per ~30 days. Significant; encourages presence. Consumer integration deferred.

### TUN.bldg.commerce_stall_split — 50/50 owner/city

- **Site:** `engine/buildings.py::BUILDING_CATEGORIES['commerce_stall']` `owner_cut_pct`/`city_cut_pct`
- **Design source:** §2.9.3 literal ("50% to owner, 50% to city tax pool")
- **Concern:** Vendor surface deferred. When implemented, the 50/50 is a clean design; the question is whether commerce stalls cannibalize the broader vendor economy (existing bounty board, sabacc, NPC vendors). Observe at launch.

### TUN.bldg.consumer_integration_deferred — substrate-only

- **Site:** Multiple — see "What deferred" in handoff.
- **Status:** The 4 effect-lookup helpers ship as substrate. Wiring into consumers (`engine.crafting` craft rolls, `engine.cp_engine` daily tick, vendor command, time-in-room CP tracker) is deferred. Tracked as a single bucket because they share the "substrate ready, consumers wait" pattern.
- **When to wire:** SYN.10 polish drop or post-launch. Economist pass before wiring is preferable so consumers can apply the right magnitudes (e.g., crafting_station +1D might want a +1 pip bonus for some craft tiers, or the cultural_hall +1 CP might need a per-day cap).

### TUN.bldg.donate_to_org_path — substrate-only

- **Site:** `engine/buildings.py::construct_building` has `donate_to_org: bool` param.
- **Status:** Substrate stores `owning_org_id` when set; parser doesn't surface the option. Citizens currently always own personally.
- **When to surface:** A polish drop with the `+building construct <category> --org` shape, or interactive prompt. Defers the "do you want this to be a public building?" decision UX.

---

## SYN.10 — Display integration + launch polish (shipped 2026-05-25)

### TUN.display.region_look_auto_overlay — wilderness look only

- **Site:** `parser/builtin_commands.py::LookCommand._look_wilderness`
- **Choice:** The region info block auto-injects in wilderness `look` output, NOT in standard room look. Standard rooms in cities, ships, interiors don't need the region overlay (they're not in a wilderness region).
- **Concern:** A player at a wilderness sentinel room (the edge between standard map and wilderness coords) sees the region block only after stepping into wilderness coords. The `+region <slug>` command bridges this gap.

### TUN.display.viewer_org_highlight — viewer's faction marked in influence row

- **Site:** `engine/territory_display.py::get_region_look_block(viewing_org_code=...)`
- **Choice:** When the viewer is in a faction, that faction's influence entry in the breakdown row gets a color highlight. Helps players see their own position at a glance without scanning the row.
- **Concern:** Independent characters get no highlight; that's intentional — they have no faction stake in the region.

### TUN.display.ansi_palette_centralized — 8 semantic color tags

- **Site:** `engine/territory_display.py` module-level constants
- **Choice:** All ANSI codes consolidated in one module so the UI pivot can map them to semantic CSS classes in a single pass. Currently used: `_RED` (lawless/threat), `_YELLOW` (contested/warning), `_GREEN` (secured/success), `_CYAN` (accent/heading), `_MAGENTA` (contest panel), `_BOLD` (emphasis), `_DIM` (subtle), `_ITALIC` (descriptive).
- **Concern:** No tuning — design choice.

### TUN.display.influence_tier_thresholds — 50/100 for foothold/dominant

- **Site:** `engine/territory_display.py::_influence_tier`
- **Choice:** `>=100` = dominant, `>=50` = foothold, else = no_presence. Matches the standing thresholds in `engine.territory._get_influence_tier`.
- **Concern:** No tuning — pinned to engine.territory thresholds.

### TUN.display.news_broadcast_taxonomy — 6 event types

- **Site:** `engine/territory_display.py::format_*_news` helpers
- **Choice:** Ownership change (claimed/lost/unclaimed), contest start, contest resolve (defender/challenger), anomaly defeat, building completion, building demolition (demolished/evicted). All ship pre-formatted strings.
- **Concern:** Currently real-time broadcast only — no persistence. Players offline at broadcast time miss the news entirely. UI pivot could add a news log to bridge this gap.

### TUN.display.garrison_annex_only_global_broadcast — selective news visibility

- **Site:** `engine/buildings.py::_complete_construction`
- **Choice:** Only `garrison_annex` completions broadcast globally. residence/crafting_station/commerce_stall/cultural_hall completions stay owner-only.
- **Reasoning:** Garrison_annex is a visible faction-power-projection (spawns defending NPCs); residence is a private investment. Public broadcast for the former; quiet for the latter.
- **Concern:** A future polish could surface ALL completions in a "city construction log" surface (city-scoped, not global), but global broadcast for residences would feel spammy.

### TUN.display.contest_time_remaining_uses_ends_at — schema-pinned

- **Site:** `engine/territory_display.py::get_region_data_block` active_contest section
- **Choice:** Time remaining = `region_contests.ends_at - now`. The real schema uses `started_at`/`accumulation_ends_at`/`ends_at`; we surface `ends_at` (resolution time, not culminating-fight start time).
- **Concern:** The `accumulation_ends_at` mark might be more useful to surface ("X hours until the culminating fight begins") but the design uses "resolution" as the single visible countdown.

### TUN.display.contest_accumulation_falls_back_to_zone_influence — no per-contest column

- **Site:** `engine/territory_display.py::get_region_data_block`, `get_faction_contests_data`
- **Choice:** No per-contest accumulation column exists in `region_contests`. Accumulation values are the zone influence scores at query time (which the contest tick keeps updated via `adjust_territory_influence`).
- **Concern:** This is correct for the design intent — the contest IS the zone-influence accumulation — but means a contest's "starting accumulation" is lost (you only see current, not delta-since-start).

### TUN.display.region_data_block_stable_contract — UI pivot anchor

- **Site:** `engine/territory_display.py::get_region_data_block` return shape
- **Status:** **Stable contract for the upcoming web UI work.** Top-level keys documented in function docstring. Adding new fields is safe; renaming or removing requires coordination.
- **Reasoning:** The web HUD will consume this dict directly. CLI render is built on top of the same data accessor.

### TUN.display.ansi_toggle_for_consumers — ansi=False for plain text

- **Site:** All `*_lines` functions in `engine/territory_display.py`
- **Choice:** `ansi=False` strips all color codes. Test snapshots, log dumps, future structured-text consumers can pass `ansi=False`.
- **Concern:** No tuning — utility flag.

### TUN.display.faction_only_surfaces — independent rejection

- **Site:** `parser/faction_commands.py::_contest`, `_resource_outlook`
- **Choice:** Both subcommands reject the `independent` placeholder with a "join a faction" prompt.
- **Concern:** Independent characters lose access to these views; appropriate since they have no faction-side stake.

### TUN.display.region_command_auto_resolve — wilderness coords priority

- **Site:** `parser/region_commands.py::RegionCommand.execute`
- **Choice:** `+region` (no args) resolves via wilderness coords first; falls back to `_resolve_room_region` for sentinel-room lookups. Explicit slug bypasses both.
- **Concern:** A player in a city room with no wilderness association gets a "pass a slug explicitly" message — informational, not blocking.

---

(No additional SYN drops remaining. The wave is complete. `T2.ECON.review` opens next — see header note for the full ledger context.)

---

## Consumer: T2.ECON.review

This ledger is the standing input for the whole-game economist pass
(`T2.ECON.review` in `TODO.json`). The review will look at:

- This document's entries
- `economy_audit_v1.md`, `economy_audit_v2.md`, and the existing
  audit-implementation scorecard
- The original `economy_design_v02-1.md`
- All shipped numeric values across credits flow, resource flow,
  influence economy, time gates, opportunity costs, supply/demand,
  faction balance, progression gates, content gates

…and produce a unified tuning recommendation across the whole game,
not just SYN.

The review opens **now** — SYN.10 (the final SYN drop) shipped
2026-05-25. The SYN wave is complete. `T2.ECON.review` is open;
this ledger is the input. ~40 tuning concerns across SYN.6/7/8/9/10
sections await reconciliation in the whole-game economist pass.
