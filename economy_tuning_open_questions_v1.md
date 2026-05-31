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

### SYN.7.a — Tier 1 wilderness anomalies (shipped 2026-05-25, fix shipped 2026-05-25)

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

## SYN.7.b — Tier 2 wilderness anomalies (pending)

Will include: Tier 2 reward bands (rare-tier salvage, named loot,
15-25 influence), cadence, multi-participant loot distribution
rules.

### SYN.8 — Tier 3 world bosses (pending)

Will include: world-boss HP, multi-phase thresholds, participation-
scaled loot formula (`floor(participants/4)` is the design number,
but the participant denominator could be tighter or looser).

### SYN.9 — Player-constructed buildings (pending)

Will include: building costs, category effect magnitudes,
construction time, demolish refund percentages.

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

The review opens **after SYN.9 ships** (the last SYN drop). Until
then, this ledger is the bookkeeping that keeps every numeric pick
traceable.
