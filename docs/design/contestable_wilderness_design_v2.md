# Contestable Wilderness — Design v2 (LOCKED)

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 24 2026**
**Design Document Version 2.0 — supersedes v1**

---

## Document status

**This is the locked design.** It supersedes
`contestable_wilderness_design_v1.md` (May 24 2026 morning draft).
v1 captured the structural pivot (city-map = neutral commons,
wilderness = contestable frontier, one owner per region, cold
start) but did not yet incorporate:

- The four-MMO competitive review (EVE / Albion / SWG / Foxhole +
  Eco + Realm of the Mad God) conducted May 24 2026 afternoon.
- The wilderness-only T5 crafting materials and two-stream
  resource economy.
- The wilderness anomaly system (Tier 1-3, including world-boss
  events like krayt dragon hunts).
- The player-constructed buildings inside cities (full version,
  not just pre-authored housing lots).
- The three afternoon Q-locks: hybrid contest centrality,
  Albion-style culminating fight, partial-passive-plus-harvest
  yield model.

v2 captures all of the above. Implementation begins at SYN.0
after v2 lock.

---

## 0. Summary

The structural pivot: SW_MUSH's faction-vs-faction contest layer
moves entirely into wilderness regions, and the city map becomes
permanently neutral commons.

**Four foundational moves:**

1. **City-map zones become permanently neutral commons.** Hand-
   built rooms (Mos Eisley, Coronet, Coruscant proper, Nar
   Shaddaa promenades, every existing built-up area) keep their
   security tier and PvP gates, but cease to be contestable
   territory. No org claims them. The cantina is the cantina;
   nobody owns the cantina.

2. **Wilderness regions become the contestable frontier.** Each
   region has one owner or no owner. Org-vs-org contest happens
   at this granularity.

3. **Player cities anchor in wilderness only.** Cities become
   citadels-in-the-frontier — safety meaningful *because* the
   surrounding region is contestable.

4. **All wilderness regions launch un-owned with zero seeded
   influence.** Pure cold start.

**Three afternoon refinements (locked May 24 2026):**

5. **Hybrid contest centrality.** Faction warfare is highly
   visible — the news digest, the region-look text, the daily
   anomaly events — but mechanically optional. A player who
   wants to be a crafter in Mos Eisley, a Sabacc dealer in the
   cantina, or a Jedi in the Village can do those things and
   feel like the game is full. Wilderness *pulls* engagement
   (the rewards are real) but does not *demand* it.

6. **Albion-style culminating fight.** The 7-day contest
   accumulation does not silently resolve. Instead, in the
   final 4 hours, a **Region Anchor** NPC (a Tier-2-class
   spawn) appears at a contested landmark. Whoever lands the
   killing blow wins the contest. Accumulated influence does
   not pick the winner directly; it sets the **anchor's HP**
   — heavily-influenced defenders get a bigger, tougher
   anchor; weak challengers face a harder fight if the
   defender held strong. The contest becomes a *scheduled
   tactical event*, not a silent number-grind.

7. **Partial passive + active harvest.** Owning a region
   confers a small **passive baseline yield** (incentive to
   hold even when members are quiet). On top of that, members
   present in the region can run **harvest commands** at
   landmarks for substantially larger active yields. The
   region's owner takes a **15% cut** of any *non-owner*
   harvests too. Three economic flows: passive trickle to
   owners + active harvest by owner members + tax on outsider
   harvests.

The system this produces: **factions contesting wilderness
regions for control** as a real player loop, with PvP, sabotage,
economic warfare, espionage-as-influence, scheduled culminating
fights, world-boss anomaly events, owner-built city
infrastructure, and visible-to-all narrative tension. *And* a
parallel track for non-contest players who never want any of
that and still have a full game.

---

## 1. Design Rationale

### 1.1 Why retire per-room claims

Drops 6A–6D shipped a per-room claim system that works
mechanically but produces *bookkeeping without stakes*:

- Per-org caps (3/zone, 10/org total) prevent any org from
  *owning* a region in the literal sense.
- Per-room yields are small drips.
- City-map zones are already civilization; "X faction has
  claimed this back alley" conflicts with the built world's
  narrative.

The wilderness is *frontier* and is *supposed* to be contested.
Putting the contest layer there matches both the Star Wars
narrative and the gameplay intuition that "out there" is where
factions fight for ground.

### 1.2 Why whole regions, one owner

Per Brian's call (May 24 2026). Granularity options:

- Per-tile (1600 contestable units per region): swamp.
- Per-landmark (5-10 per region): playable but still bookkeeping-
  heavy.
- **Whole region, one owner**: simple, legible, stakes real.

Loss of a region is felt across the entire player base. "The
Hutts lost the Dune Sea" is a real news headline.

### 1.3 Why cities in wilderness only

City-map zones are neutral commons under the pivot → cities
can't anchor there (no contest, no claim). Wilderness regions
are contestable → cities anchor in wilderness regions.

The city's **citadel effect** (citizens get security upgrade in
city rooms regardless of zone) becomes *meaningful* in
wilderness: a Hutt city in the Hutt-owned Dune Sea is doubly
safe for Hutt members, fortified against rival faction influence
pushes, and the city's destruction or banishment is felt across
the contest.

### 1.4 Why cold start with zero seeded influence

Per Brian's call (May 24 2026). Pure cold start makes the first
weeks of the game *about* the contest. Early players are the
founders of the political shape. The first faction to push the
Dune Sea past 50 influence does so because *their members*
showed up and worked. The story of ownership belongs to the
players who made it.

### 1.5 Why hybrid contest centrality

Per Brian's call (May 24 2026 afternoon). The lesson from
contrasting EVE (contest is the game) with SWG (contest is one
of the games):

- EVE's small-territory-fights work for 50,000-player factions
  with 24/7 coverage. With our 8-15 active players, full-contest-
  centrality means every player is constantly drafted into
  faction work and burns out.
- SWG demonstrated that a Star Wars sandbox can have rich non-
  contest gameplay (crafting, RP, music, social, exploration)
  while *also* hosting a GCW for those who want it.

Our small playerbase and RP-leaning audience explicitly want
the SWG-style optionality. The contest is *available* and
*visible* — players know it's happening, can join in if they
want, see its outcomes in the news digest — but *can be
ignored*. A crafter in Mos Eisley has a full game.

This shapes scope decisions throughout. Several features the
competitive review surfaced (mandatory daily ratting, intel
warfare requirements, scheduled defense windows) get *softer*
implementations to preserve the SWG-optionality default.

### 1.6 Why Albion-style culminating fights

Per Brian's call (May 24 2026 afternoon). The lesson from
comparing EVE FozzieSov (continuous accumulation resolves
silently) with Albion GvG (5v5 scheduled tactical fight):

- A 7-day silent influence comparison rewards *constant grinding*
  during the window. Our small playerbase can't sustain that.
- Albion's scheduled fights create *moments to be present for* —
  the contest becomes a calendar event everyone schedules around.

The culminating fight at a wilderness landmark in the contest's
final 4 hours gives the contest a real *climax*. Influence
accumulation still matters (it shapes the anchor's HP), but the
*fight* decides the outcome. Both modes — the slow strategic
influence game and the tactical moment — get their due.

### 1.7 Why partial passive + active harvest

Per Brian's call (May 24 2026 afternoon). The lesson from EVE
(fully active ratting required) versus pure-passive models:

- Pure passive means owners can win contests and then ignore
  the region. The wilderness becomes uncontested ground that
  earns money for absentees. Boring.
- Pure active (EVE-style) means owners must constantly run
  harvest fleets. Exhausting for our scale.

Partial passive + active means:
- Holding a region gives you *something* even when nobody
  shows up (the baseline yield). Worth defending in principle.
- *Active members* in the region earn substantially more
  (harvest yields). Presence is rewarded.
- *Non-owner visitors* who harvest in your region pay you 15%
  tax. Tolerating visitors becomes economically attractive.

Three flows = three player types served: dormant owners get
something, active owners get a lot, visiting harvesters get the
crafting materials they need (minus tax).

---

## 2. System Definitions Under the Pivot

This section defines each affected system's new shape. Where a
shipped surface survives unchanged, noted. Where retargeted,
specified. Where retired, flagged for the deprecation drop (§6).

### 2.1 Factions (Guide 10, engine/organizations.py)

**Unchanged.** Faction membership, ranks, rep, equipment issue/
reclaim, weekly stipends, the 7-day switch cooldown — all of it
works the same. The only difference is how rep and influence
interact (§2.10).

### 2.2 Territory — Retargeted

`engine/territory.py` retargets from rooms to regions.
**Surface preserved; semantics retargeted.**

**What survives:**
- `territory_influence` table (org_code, zone_id, score 0-150,
  thresholds Presence/Foothold/Dominant/Control). Zone_id is
  the *region's* zone.
- `adjust_territory_influence()` as the single influence-change
  entry point. Architecture invariant preserved.
- Influence earning hooks: `on_npc_kill`, `on_mission_complete`,
  `on_pvp_kill`. **But:** these now only fire when the action
  happens *inside a contestable wilderness region*. City-map
  actions hand out faction rep (Guide 10) without influence
  delta.
- Hourly presence tick (+1 per member in region), daily decay
  (−5/day after 48hr absence).
- Investment (`faction invest <amount>`).
- Influence dashboard (`faction influence`).

**What retargets:**
- `territory_claims` schema: `room_id` retires, replaced by
  `wilderness_region_slug` (TEXT, UNIQUE). One row per region.
- `claim_room()` → `claim_region()`. Validates rank 3+, region
  exists, org has Foothold (50+) in the region, no current
  owner, treasury ≥ founding cost.
- `unclaim_room()` → `unclaim_region()`.
- `is_room_claimed_by()` → `is_region_owned_by()`.
- `get_territory_influence()` and digest functions: shape
  preserved; semantics now describe regions.

**What retires:**
- Per-zone claim cap (3) and per-org total cap (10) — irrelevant
  under one-owner-per-region.
- Per-room weekly maintenance (200 cr) — replaced by region-
  scale upkeep (§2.5 economy).
- Per-room guard NPC stationing — replaced by region-level
  garrison.
- `[CLAIMED: <org>]` look tag on rooms — replaced by region-
  level look line (§2.6 display).

**Influence thresholds retained, repurposed:**
- **Presence (25+):** Org name appears in region look output.
- **Foothold (50+):** Org *qualifies* to attempt region claim.
- **Dominant (75+):** Flavor only; no mechanical benefit alone.
- **Control (100+):** If region is un-owned, the Control-tier
  org auto-seizes ownership. If a rival org holds the region,
  Control triggers a **contest event** (§2.4).

**Influence thresholds are gates, not ownership itself.**

### 2.3 Security — Wilderness-aware

`engine/security.py::get_effective_security()` gains a
wilderness branch. New resolution order:

1. Transient Director override on zone_id (unchanged).
2. Director env override by zone environment key (unchanged).
3. Director live influence overlay (unchanged):
   - Criminal ≥80: downgrade one tier.
   - Imperial ≥75: upgrade one tier.
   - Imperial ≥90: force SECURED.
4. **NEW: Wilderness region ownership branch.** If the character
   is in wilderness (`wilderness_region_slug` set):
   - Look up region's owner (org_code) and the region's base
     security tier from the region YAML (default_security).
   - If region has owner AND character is in owning org: citadel
     upgrade (LAWLESS → CONTESTED).
   - If region has owner AND character is *not* in owning org:
     base security tier stands. (Hostile territory.)
   - If region has no owner: base security tier stands.
   - **For characters in wilderness, this is the terminal branch
     — skip steps 5-7.**
5. Room/zone property fallback (city-map path, unchanged).
6. Default CONTESTED.
7. **`_apply_claim_upgrade` retires.** City citizen upgrades go
   through the cities engine, not this function.

City-map zone security is completely unaffected by the pivot.

### 2.4 The Contest State Machine — Region-scaled with culminating fight

Drop 6D's contest state machine retargets to regions and adds
the **culminating fight** layer.

**Contest triggers:**
- An org with Control (100+) influence in a region where a
  rival holds ownership triggers a contest event.
- An org with Foothold (50+) in an un-owned region can attempt
  to seize via the same contest mechanism.

**Contest mechanics:**
- A contest event runs for **7 real-time days** from
  declaration.
- **Days 1-6: Accumulation phase.**
  - Cross-faction PvP at landmarks in the contested region does
    not require consent (the contest is the consent).
  - All faction missions/bounties/smuggling/harvests completed
    in the contested region grant **2× influence** for both
    sides.
  - The Director publishes a daily contest digest in the news
    system.
  - A countdown timer is visible in region look output and on
    the web client.
- **Day 7, final 4 hours: Culminating fight.**
  - A **Region Anchor** NPC spawns at a designated contested
    landmark (chosen by the Director from the region's
    landmark list; one specific landmark per contest).
  - The Anchor is a Tier-2-class spawn (multiplayer-capable),
    flavored to the defending faction (Hutt warlord NPC for
    Hutt-defended regions, Stormtrooper Commander for Empire,
    etc).
  - **The Anchor's HP scales with the *defender's* accumulated
    influence** in the region over the 7-day window:
    - Anchor base HP: 100.
    - +1 HP per defender influence point above 50.
    - Example: defender finished with 90 influence → Anchor
      has 100 + (90-50) = 140 HP. A strong defender bunkers
      the Anchor.
  - **The Anchor's tier scales with the challenger's
    accumulated influence:**
    - Challenger below 50 influence: Anchor stays tier2.
    - Challenger above 100: Anchor reinforced with additional
      Tier-1 NPCs (1 extra per 25 influence above 100).
  - Whoever lands the killing blow on the Anchor wins the
    contest. *No silent comparison.*
  - PvP at the Anchor landmark during the 4-hour window is
    fully open — challenging-faction members can attack the
    Anchor and each other; defending-faction members defend
    the Anchor; non-aligned members get free PvP target status
    if they enter the landmark.

**Contest resolution:**
- Killing-blow faction wins.
- If no killing blow lands in 4 hours (Anchor not killed): the
  *defender* wins by default. Failure to break the Anchor =
  the defense held.
- Ownership transfers cleanly if challenger wins. Guards
  dismiss; resource yields cut over.
- Loser's faction: influence in the region slashed by 25.
- Cooldown: an org that loses a contest cannot challenge the
  same region again for **14 days**.

**Outnumbered-defender bonus** (anti-zerg, Albion lesson):
- During accumulation phase, if the challenging faction has
  more registered members than the defending faction, the
  defender's influence-gain rate is **1.5×**.
- During the culminating fight, if the *participating* count
  during the 4-hour window is asymmetric (more challengers
  than defenders), the Anchor gets +20 HP and a +1D damage
  bonus per outnumbering tier (1.5x, 2x, 3x).

**Per Brian's cold-start call:**
no contest is possible at launch. Day one: every region is
un-owned, 0/0/0/0 influence. First contests fire 2-4 weeks in.

### 2.5 Economy — Three-stream model

Per Brian's call (afternoon May 24 2026): **passive baseline +
active harvest + outsider tax**.

#### 2.5.1 Passive baseline yield (to owning org)

Each owned wilderness region pays a small daily passive yield
to the owning org's treasury — *no member presence required*.

| Region base security | Daily passive (credits) |
|----------------------|--------------------------|
| Contested (rare) | 50-150 |
| Lawless (default) | 100-250 |

Modest deliberately. Dormant ownership earns *something* but
not enough to fund the contest defense. Real income comes from
active harvest.

Resource yields (metals/chemicals/rares) are **not** part of
the passive baseline. Those come from active harvest only.

#### 2.5.2 Active harvest (member presence required)

Every wilderness region has **harvest nodes** — specific
landmarks or tiles where the `harvest` command runs.
The command:
- Validates character is at a harvest node.
- Runs a Survival or relevant-specialty skill check.
- Yields credits + resources scaled by influence tier +
  region quality (§2.5.5).
- 30-minute personal cooldown per character per region.

Harvest yields by influence tier (per harvest, scaled by skill
margin):

| Region base | Owning org's influence | Harvest (cr) | Resources (units) |
|-------------|------------------------|--------------|---------------------|
| Contested | Foothold | 100-200 | 1 metal |
| Contested | Dominant | 150-300 | 2 metal + 1 organic |
| Contested | Control | 200-400 | 2 metal + 1 organic + chance T5 rare |
| Lawless | Foothold | 150-300 | 2 metal + 1 chemical |
| Lawless | Dominant | 250-500 | 3 metal + 2 chemical + 1 rare |
| Lawless | Control | 400-800 | 4 metal + 3 chemical + 2 rare + T5 chance |

Lawless yields > contested yields (frontier risk premium).
Active members in a Lawless+Control region can earn 1500-2500
cr/hour from harvesting alone, plus T5-eligible rare crafting
material drops.

#### 2.5.3 Outsider harvest with owner tax

Non-owner-faction characters CAN run the harvest command in an
owned region. They receive 100% of the harvest, BUT the system
debits a **15% tax** in credits and routes it to the owning
org's treasury. Resource drops are not taxed (they go entirely
to the harvester).

The tax cut creates the *visitor economy*:
- A Hutt-owned Dune Sea welcomes Rebel crafters who come for
  krayt-pearl fragments.
- Each non-Hutt harvest sends 15% of the credit yield to the
  Hutt treasury.
- The Hutts profit from peaceful traffic. They may choose to
  tolerate or attack visitors based on their political
  posture.

This is the EVE-style "your space, your tax" mechanic, scaled
down for our playerbase.

#### 2.5.4 Region upkeep

Weekly costs to the owning org's treasury:
- **Region maintenance**: 2,000 cr/wk.
- **Region garrison**: 1,000 cr/wk (5 NPCs).
- **Total**: 3,000 cr/wk per owned region.

If treasury can't pay:
- Garrison dismisses first (saves 1,000 cr/wk).
- If still can't pay: region lapses (becomes un-owned;
  influence preserved; org gets one warning).

#### 2.5.5 Region resource quality — SWG-style time-varying

Per the SWG resource lesson: each region rolls a **weekly
quality variance** for its resource outputs. The Director
announces in news. Crafters travel to high-quality regions of
the week.

Mechanically:
- Each Monday at server midnight: each region rolls a quality
  modifier (random 0.7× to 1.3× on harvest yields).
- The roll is per resource type (metal might be 1.3× while
  chemical is 0.8× the same week).
- Director publishes a `resource_outlook` digest naming the
  best-quality regions of the week.

This is the *crafter's news feed* — drives wilderness traffic
without forcing combat engagement.

#### 2.5.6 Wilderness-only T5 crafting materials

Per Brian's afternoon call: high-tier crafting is **gated on
wilderness-sourced materials**.

New crafting tier system on top of existing quality 1-100:
- **T1-T4**: existing tiers. Resources from anywhere.
- **T5**: new tier. Requires *wilderness-sourced rare* of
  quality 75+ AND region-flavored special component.

T5 outputs and their gating materials (initial list, tunable):
- **Master-crafted lightsaber**: kyber_shard_minor (from
  force-resonant landmarks in any wilderness region) + crystal
  selection mechanics (existing engine).
- **Top-spec blaster rifle**: weapons_capacitor_core
  (Dune Sea harvest at Tier-2 anomaly drops) + base T4 rifle
  schematic.
- **Hyperdrive surge converter (ship part)**: scavenged_
  republic_tech (Coruscant Underworld harvest) + base
  hyperdrive schematic.
- **Mil-spec ion engine core (ship part)**: deep_dune_iron
  (Dune Sea Tier-3 anomaly drop) + base ion engine schematic.
- **Master-grade armor**: composite_chitin (from Coruscant
  Underworld Maze Predator hunts) + base armor schematic.

These items represent the genuine endgame crafting lane —
*reasons to engage with wilderness for non-PvP players*.
Crafters can build a full career around region-specific
sourcing without ever participating in a formal contest.

### 2.6 Display Integration

**Region look output (new):**
```
─── The Dune Sea (Tatooine) ─── [LAWLESS]
  Sand stretches to the horizon under hammering suns. Bantha
  spoor crosses old caravan tracks. The wind never stops.

  Ownership: Hutt Cartel (Foothold)
  Influence: Hutt 65 [FOOTHOLD] · Rebel 22 · Empire 8
  
  Resource quality this week: Metal 1.2× · Chemical 0.9× · Rare 1.3×

  ── Active contest ───────────────────────
  Rebel Alliance challenges Hutt Cartel
  Time remaining: 3d 14h 22m
  Current accumulation: Hutt 90 · Rebel 80
```

**Faction influence command:**
- `faction influence` shows org's influence in each region with
  progress bars and current owner.
- `faction territory` shows owned regions only with upkeep
  status.
- New `faction contest` shows active contests (defender and
  challenger, time remaining, accumulation scores).
- New `faction resource_outlook` shows weekly region quality
  digests.

**Player commands added in this pivot:**
- `faction challenge region <slug>` — initiate contest.
- `harvest` — run a harvest at current location.
- `+intel handover <handler>` — espionage-as-influence (§2.7).
- `+building construct <type>` — start a building (§2.9).

### 2.7 Missions, Bounties, Espionage — Two-tier rewards

**City-map activity = personal advancement only.** Missions in
Mos Eisley grant rep, credits, CP. No zone influence delta.

**Wilderness activity = faction power projection.** Missions in
wilderness regions grant rep + credits + CP + **5 influence
delta** for the player's faction in that region.

| Action | City-map | Wilderness region |
|---|---|---|
| Mission | +3 rep | +3 rep + 5 inf |
| Bounty | +2 rep | +2 rep + 5 inf |
| Smuggling | +2 rep | +2 rep + 5 inf |
| PvP kill | (consent only) | +0 rep + 15 inf |
| NPC kill | +0 rep | +0 rep + 2 inf |
| Investment | n/a | +10/1000 cr |
| Harvest (success) | n/a | +1 inf |
| Anomaly participation | n/a | +5 to +30 inf (§2.8) |

**During an active contest**, all wilderness column numbers
**double**.

**Espionage-as-influence:**

The `+intel` command gains a redemption surface. Sealed intel
reports given to a **faction handler NPC** convert to:
- Credits (existing).
- **Influence delta** in the region the intel describes.

Conversion rates (tunable):
- Low-quality intel: 1-3 inf + 200-500 cr.
- Medium: 4-8 inf + 600-1500 cr.
- High (specific, recent, actionable): 10-20 inf + 2000-5000 cr.

The handler's evaluation runs through the Director AI (T3.15
real impl; SYN.5 ships a stub heuristic).

Espionage as a path to influence serves:
- Espionage-build characters (perception + con + search).
- RP-identity factions (Rebel intel cell, Hutt informants).
- New players who can observe and report.

### 2.8 Wilderness Anomalies — Krayt dragons, corvettes, world bosses

Per Brian's afternoon call. **Tier 1-2 anomalies in pre-launch
scope; Tier 3 world-boss in pre-launch as a flagship feature.**

A wilderness anomaly is a temporary, persistent landmark that
spawns in a region for a defined window. Broadcast in news +
faction comms. Investigable, fightable, lootable. Modeled on
`engine/space_anomalies.py` with wilderness-flavored content.

**Tier 1 — Solo/small group (~30 min duration):**
- Stranded scout patrol
- Recently-uncovered salvage cache (sandstorm/cave-in exposed)
- Wounded animal worth hunting
- Roving Tusken hunting party (3-4 tier1 NPCs)
- Crashed reconnaissance droid
- **Reward shape:** crafting materials + credits + small
  influence delta (+5) for player's faction.
- **Cadence:** every 2-3 hours per region.

**Tier 2 — Coordinated group (~2 hour duration):**
- **Imperial corvette stranded** — hyperdrive failure leaves
  the ship grounded. Boarding party encounter. Multi-room
  ground combat inside the corvette using
  `engine/encounter_boarding.py`. Reward: rare-tier salvage,
  named loot, 15-25 influence to participating faction.
- **Hutt smuggling convoy** with heavy escort — intercept or
  escort, depending on player faction.
- **Maze Predator pack outbreak** in Coruscant Underworld —
  multi-wave clearout.
- **Separatist commando deployment** — landed strike team to
  destroy, multi-phase combat.
- **Reward shape:** high-value crafting materials, named loot,
  meaningful influence (15-25), unique trophy items.
- **Cadence:** every 24-48 hours per region.
- **Player count:** 3-5 coordinating, soloing impossible at
  intended tier.

**Tier 3 — Region-wide world boss (~6-12 hour duration):**
- **The Krayt Dragon** (Dune Sea). Existing
  `world_events.KRAYT_SIGHTING` substrate becomes a real
  spawnable tier-3 NPC at specific coordinates. Multi-phase:
  at half HP, relocates to a new tile and players track it.
  Defeat awards every participating character a unique trophy
  (housing display), credit pot, AND the killing-blow faction
  gets +50 region influence. *Drops krayt pearls* — N pearls
  scaled to participation (floor(participants / 4)) per the
  RotMG lesson.
- **The Maze Predator Apex** (Coruscant Underworld) — massive
  subterranean predator, equivalent shape to krayt. Drops
  composite_chitin (T5 armor mat) scaled to participation.
- **The Crashed Separatist Capital Ship** (random wilderness
  region during major contests) — multi-faction encounter:
  ground combat vs security droids, salvage from wreck,
  faction race to "claim" the wreck site.
- **Republic Lost Patrol** (rare; any region) — recovered
  patrol of canon-NPCs (Jedi Order knights, Republic
  commandos), can be rescued for major faction rep + influence
  rewards or turned in to Separatist sympathizers for
  contraband.
- **Cadence:** every 7-14 days per region.
- **During an active contest in that region: 2× cadence
  (krayts every 3-7 days when contested).**
- **Player count:** 8-16, hour+long fights.

**Spawn / cadence engine:** new module
`engine/wilderness_anomalies.py` parallel to
`engine/space_anomalies.py`. Tier 1-2 ship in SYN.7; Tier 3
ships in SYN.8 (both pre-launch).

**Loot distribution:**
- Tier 1: per-character drop to harvester.
- Tier 2: rolled among damage-contributors, with the named
  loot piece visible to all and granted to the killing-blow
  participant.
- Tier 3: scaled loot (krayt pearls = floor(participants /
  4)) visible to all; distributed by participation rules
  (highest damage gets first pick, then descending).

### 2.9 Player Cities + Building Construction

Per Brian's afternoon call: **full building construction system
in pre-launch scope as SYN.9.**

#### 2.9.1 Cities anchor in wilderness only

`engine/player_cities.py` retargets founding from city-map zones
to wilderness regions. **Most of the engine survives unchanged.**

**What survives unchanged:**
- Five city benefits: identity, tax, citizen security upgrade,
  `+city home`, mayor governance.
- Role system: Founder, Mayor, Citizen, Guest, Outsider,
  Banished.
- Tax (0-10% cap, invisible-to-payer).
- Citizen-only rooms (30% cap on non-HQ expansion).
- `+city home` (1/hr).
- All mayor commands.

**What retargets:**
- **HQ anchor**: anchor at a wilderness *landmark room* within
  the chosen region. The city HQ becomes the chosen landmark.
- **Expansion**: claim adjacent landmarks within the same
  region using the existing landmark adjacency graph. Max
  5/10/20 by HQ tier preserved. 24-hour rate limit preserved.
- **Founding requirement**: "org owns the region OR has
  Foothold (50+)". Foundling in un-owned region is allowed
  (stakes a claim with infrastructure).

**What retires:**
- "Cities cannot be founded in secured zones" rule.

#### 2.9.2 Existing cities at the pivot date

Per Brian's call: cities ship as-shipped *to be reworked*.
Migration: **dissolve all city-map cities at SYN.4 with 75%
refund**. Re-found in wilderness. Founders compensated by the
extra refund.

#### 2.9.3 Building construction (SYN.9, pre-launch)

Inside a city's expansion landmarks, citizens with sufficient
rank can construct buildings. Each landmark has **0-5 building
slots** (depending on landmark capacity).

**Building categories** (initial set, extensible):

| Category | Effect | Construction cost |
|----------|--------|---------------------|
| Residence | Tier-3-equivalent housing for one citizen (lockable, with storage) | 5,000 cr + 5 metal + 5 organic |
| Crafting station | Grants +1D bonus to a specific guild's crafting checks performed at this building | 8,000 cr + 10 metal + 5 composite |
| Commerce stall | Mini-vendor that takes a 50% cut of its sales to the owning citizen, 50% to the city tax pool | 6,000 cr + 8 metal |
| Garrison annex | Spawns 2 additional defending NPCs at the landmark (faction-flavored) | 10,000 cr + 15 metal + 5 chemical |
| Cultural hall | Grants +1 daily CP to citizens who spend 5+ minutes here | 7,500 cr + 8 metal + 5 organic |

**Construction flow:**
- Citizen with rank 3+ in the city's owning org issues
  `+building construct <type>`.
- System validates: rank, slot available, materials in inventory
  or org storage, treasury for credit cost.
- Construction takes **24 real-time hours**. During construction,
  the building shows as "Under Construction" in look output.
- Materials and credits deducted at start. Construction is
  *irreversible from this point* (no refund if construction
  cancelled).
- On completion: building is operational. Owner of the
  building is the constructing citizen (or, optionally, the
  org for "public" buildings the constructor donates).

**Ownership and transfer:**
- A building is owned by its constructor (or by the org if
  donated).
- On city ownership transfer (region changed hands; new owner
  founded city): owner of each existing building can choose:
  - **Preserve** (default): building stands; original owner
    keeps it as a tolerated tenant. New city owner can later
    evict.
  - **Demolish**: 25% material refund to the original owner,
    slot freed.
- The new city owner has these powers for each existing
  building:
  - **Tolerate** (default): building stands.
  - **Evict** (after 2-day notice): owner is removed; building
    becomes city property; original owner gets no refund.
  - **Demolish** (after 2-day notice): building destroyed,
    slot freed.

**Destruction:**
- Owner-initiated: `+building demolish` with 25% material
  refund.
- City-initiated: mayor command with 2-day notice; no refund.
- Combat-initiated (Tier-3 anomaly events, contest event
  damage): possible at the Director's discretion for narrative
  purposes; rare.

**Replication / rebuild:**
- A destroyed building's slot is freed.
- Construction system supports re-building from scratch using
  the existing construct flow.
- "Same building rebuilt by same owner" gets a small discount
  (10% off materials) representing institutional memory.

#### 2.9.4 City vitality (SWG lesson)

Cities require **N active citizens** (logged in within last 7
days) to maintain rank benefits.

| HQ Tier | Active citizens required |
|---------|---------------------------|
| Outpost (max 5 expansion) | 1+ |
| Chapter House (max 10) | 3+ |
| Fortress (max 20) | 5+ |

Below threshold:
- Tax cap drops to 50% of HQ-tier baseline.
- Expansion limit drops to current actual size (no new claims).
- Falls back to **dormant state** after 14 days under
  threshold: continues operating but no growth, no upgrades,
  visible "DORMANT" tag in look.
- Re-activates immediately if citizen count recovers.

Cities don't dissolve on inactivity. Dormant state is a
"reminder, not a death sentence" — small playerbases need
recovery room.

### 2.10 Director AI integration

The Director's existing per-axis-per-zone influence model
remains the source of *atmospheric* shifts (Imperial crackdown,
criminal surge). It does NOT directly determine wilderness
region ownership.

**New Director responsibilities under the pivot:**
- Publish daily contest digest during active contests (§2.4).
- Publish weekly resource outlook (§2.5.5).
- Evaluate intel reports for the handler conversion (§2.7).
- Schedule Tier-3 anomaly events on the per-region cadence
  (§2.8).
- Narrate region ownership changes via news system.
- Narrate building construction completion + destruction in
  faction-relevant cases.

Director's CW-era prompt tuning (T3.15) makes all of this rich
narrative-wise. SYN drops ship with stub Director responses
that get replaced when T3.15 lands.

---

## 3. Engine Changes

### 3.1 `engine/territory.py` retarget (SYN.1)

- Schema migration: `territory_claims.room_id` →
  `wilderness_region_slug` (TEXT, UNIQUE). Wipe existing rows.
- Function renames: `claim_room`→`claim_region`, etc.
- Per-room caps deleted.
- `tick_claim_maintenance` retargets, weekly 3,000 cr.
- `tick_resource_nodes` retargets to **passive yields only**
  (§2.5.1).
- Garrison spawning per-region (5 NPCs, faction-flavored).

### 3.2 `engine/security.py` wilderness branch (SYN.2)

- New helper `_get_wilderness_region_state(char, db)`.
- New helper `_apply_wilderness_ownership(base, char, region_state)`.
- New step 4 in resolution chain (terminal for wilderness chars).
- `_apply_claim_upgrade` deletes.

### 3.3 Contest state machine + culminating fight (SYN.3)

- `engine/contest.py` new file (~600 LOC estimated). Region-
  scoped contest state machine; culminating fight scheduler;
  Anchor NPC spawning + HP/tier scaling logic; resolution
  handler.
- Influence-doubling during contest in mission/bounty/harvest
  hooks.
- 14-day cooldown after lost contest.
- Outnumbered-defender bonus calculation.
- News digest hook.

### 3.4 `engine/player_cities.py` anchor retarget + migration (SYN.4)

- `found_city()` validates wilderness anchor.
- `expand_city()` uses landmark adjacency graph.
- One-time migration: dissolve city-map cities with 75%
  refund.
- City vitality mechanic.
- Existing 553 cities tests update to wilderness-anchor
  fixtures.

### 3.5 Espionage-as-influence (SYN.5)

- `engine/intel_handlers.py` new (~200 LOC).
- Intel handler NPCs at faction HQs.
- `+intel handover <handler>` command.
- Director-AI evaluation stub.
- Mission/bounty/smuggling hooks retarget to wilderness-only
  influence.

### 3.6 Active harvest + region resource quality (SYN.6)

- `engine/harvest.py` new module (~300 LOC).
- `harvest` player command with skill check + cooldown.
- 15% non-owner tax routing.
- Weekly region quality variance roll (Monday midnight tick).
- Director resource-outlook digest.

### 3.7 Wilderness anomalies Tier 1-2 (SYN.7)

- `engine/wilderness_anomalies.py` new (~600 LOC).
- Anomaly type catalogue (~12 entries across Tier 1-2).
- Spawn cadence engine (per-region rolls every 30 minutes).
- Encounter resolution for each type (most reuse existing
  combat/encounter infrastructure).
- Imperial corvette boarding uses existing
  `engine/encounter_boarding.py` with ground-side adaptation.
- Reward distribution: per-character drops, named loot,
  influence delta.

### 3.8 Wilderness anomalies Tier 3 (SYN.8)

- Tier 3 templates: krayt dragon, Maze Predator Apex, Crashed
  Separatist Capital Ship, Republic Lost Patrol.
- Multi-phase combat with relocation mechanic.
- Participation-scaled loot (RotMG lesson).
- Killing-blow influence bonus.
- During-contest 2× cadence wiring.
- Trophy item generation + housing display integration.

### 3.9 Building construction (SYN.9)

- `engine/buildings.py` new (~500 LOC).
- Schema migration: new `buildings` table (id, slot_id,
  category, owner_char_id, owning_org, status, hp, completion_ts).
- `+building construct/demolish/list/inspect/evict` commands.
- 24-hour construction timer + tick handler.
- Ownership transfer rules on city changes.
- Category effects (residence storage, crafting station bonuses,
  commerce stall vendor surface, garrison annex NPCs, cultural
  hall CP bonus).

### 3.10 T5 crafting tier (SYN.6)

- `engine/crafting.py` extension: T5 schematic gates that
  require wilderness-sourced rare components.
- New schematics catalogue: master-crafted lightsaber, top-spec
  blaster rifle, hyperdrive surge converter, mil-spec ion
  engine core, master-grade armor.
- Resource references to wilderness-only material keys.

### 3.11 Region YAML schema additions

Each region YAML gains:

```yaml
# Resource signature — region-flavored yield tables (active harvest)
resource_signature:
  flavor: tatooine_desert
  base_passive_credits: [100, 250]      # daily passive range to owner
  harvest_tables:
    foothold:    [...]
    dominant:    [...]
    control:     [...]
  weekly_quality_seed: 0xABCD            # for deterministic test fixtures

# Anomaly catalogue references
anomalies:
  tier1: [...]    # references to engine catalogue entries
  tier2: [...]
  tier3: [...]
  cadence_overrides:
    tier3: 720m   # custom per-region tier3 spawn rate

# Building slot capacity per landmark (added at landmark level)
landmarks:
  - id: anchor_stones
    building_slots: 3     # 0-5
    ...
```

### 3.12 Display integration (SYN.4+)

- `engine/territory_display.py::get_region_look_block(region, db)`.
- New `region look` command (`look region` or auto-included
  in tile look).
- Faction influence dashboard rewritten for region-keyed display.
- Web HUD: region ownership + contest countdown panel (post-
  launch polish; CLI suffices for launch).

---

## 4. Day-One Player Experience

### 4.1 The cold start

Every wilderness region: un-owned, 0/0/0/0 influence. Director
runs but no faction has seeded position. The first hours and
days of the game's life:

**A new Hutt player joins.** Tutorial Chain (existing). Mos
Eisley spaceport interior. RP, mission board, faction join.
Familiar onboarding.

**Their first mission:** Tutorial sends them to the Dune Sea
wilderness for the "Investigate Tatooine raider activity"
chain. They complete it. +3 Hutt rep, +5 Hutt influence in
the Dune Sea. The Hutts' influence dashboard now reads:
```
The Dune Sea (un-owned)
  Hutt Cartel  █░░░░░░░░░░░░░░░░░░░  5/150 [no presence]
  Rebel        ░░░░░░░░░░░░░░░░░░░░  0/150
  Empire       ░░░░░░░░░░░░░░░░░░░░  0/150
  Bounty Hunt  ░░░░░░░░░░░░░░░░░░░░  0/150
```

A trickle, a spark. The first influence point in a region's
history.

**Week 1:** A few faction members run wilderness missions,
explore. Tier 1 anomalies fire daily — Tusken hunting parties,
crashed scout droids. Players engage when they want; ignore
when they don't. Crafters notice the resource outlook digest
shows Tatooine metal at 1.2× this week and travel to harvest.
A few harvest commands grant the Hutt faction small influence
nudges.

**Week 3-4:** Hutts hit 50 (Foothold) in Dune Sea. They can
attempt to claim. They run `faction claim region tatooine_dune_sea`.
No rival has Foothold. Ownership transfers immediately. Five
Gamorrean enforcers spawn at random Dune Sea landmarks. Passive
yield begins. Region look says:
```
─── The Dune Sea (Tatooine) ─── [LAWLESS]
  Ownership: Hutt Cartel (Foothold)
  Influence: Hutt 65 [FOOTHOLD]
```

The Director publishes a news digest: "The Hutt Cartel has
claimed the Dune Sea. Rival factions take notice."

**Week 4-5:** Tier 2 anomalies start appearing — an Imperial
corvette stranded in the deep dunes. A coordinated Hutt strike
team boards it, fights through the corridors, captures the cargo
manifest. Rewards: salvage, influence (+15), a named blaster
trophy. The cantina buzzes with the story.

**A first krayt dragon (Tier 3) is announced for next Saturday
at 8 PM server time.** Players plan. Hutts mobilize defenders;
non-aligned players hunt; a Rebel cell decides to use the krayt
event as cover for an incursion attempt. Saturday night, 12
players engage the krayt over 90 minutes. Five krayt pearls
drop (floor(12/4) × 1.5 contest bonus). Distributed by
participation; the cantina remembers the hunt.

**Week 6-8:** A Rebel cell builds Dune Sea influence — missions,
intel handovers, a daring raid on a Hutt-owned harvest site.
Their influence climbs into Foothold (50+) and approaches
Control (100+). When they cross 100, a contest event triggers.

**Day 1-6 of the contest:** Open PvP at landmarks. Influence
doubles. The Director runs daily contest digest. Both sides
mobilize. Hutts reinforce defenses; Rebels prepare for the
culminating fight.

**Hour 4 of day 7:** The Anchor NPC spawns — a Hutt Warlord
boss (because Hutts are defenders) at the Anchor Stones tile.
Hutts have 130 influence at this point; Anchor has 100 + (130-50)
= 180 HP. Rebels arrive at 95 influence; Anchor stays at tier2
with no reinforcements.

**The fight.** Eight players present (5 Hutt, 3 Rebel). PvP
active. Players coordinate, attack the Anchor, defend, ambush
each other. After 90 minutes, a Rebel scout lands the killing
blow on the Hutt Warlord. Rebels win the contest. Ownership
transfers. Hutt influence in Dune Sea slashed by 25; Rebels'
preserved.

**Director publishes the news digest:** "The Dune Sea has fallen
to the Rebel Alliance. The Hutts have lost their first frontier
holding."

This is week 6-8. A real political story. **The system has done
its job.**

### 4.2 The non-contest player

In parallel to the contest narrative above, a different player —
let's call her Mira — has done none of it.

Mira joined in week 1 as a Mechanics' Guild member. She RP's
in the cantina, drinks at Chalmun's, talks to other players.
She runs missions but stays in city-map zones: Mos Eisley to
Mos Espa to the Anchorhead spaceport. She never enters
wilderness.

Mira's experience over weeks 1-8:
- Daily mission board, daily rep gains, weekly stipend.
- Crafting: she trains Technical: Speeder Repair and Technical:
  Blaster Repair. She buys T1-T4 materials from NPC vendors in
  Mos Eisley.
- She watches the news digest mention the Hutt/Rebel contest.
  She finds it interesting RP material. She talks about it at
  the cantina.
- She does NOT harvest. She does NOT participate in the krayt
  hunt. She does NOT engage with the contest.

**Mira's game is full.** She earns credits, ranks up, makes
friends, develops her character. The wilderness contest is
*backdrop* — the political weather she lives under. She's
having a good time.

This is the hybrid centrality answer in action. The contest is
visible to Mira; she can join in any time; but she doesn't have
to, and the game doesn't punish her for opting out.

---

## 5. Drop Plan

### Pre-launch SYN sequence

**SYN.0 — Pre-flight + Migration Plan (~0.5 sess)**
- Verify HEAD state of `engine/territory.py`,
  `engine/security.py::_apply_claim_upgrade`,
  `engine/player_cities.py` anchor-agnosticism.
- Write migration script: dissolve city-map cities with 75%
  refund; wipe `territory_claims`.
- Tag deprecated surfaces in TODO.json.
- No code ships.

**SYN.1 — Schema + region ownership engine (~1 sess)**
- Migration: `territory_claims.room_id` → `wilderness_region_slug`.
- `territory.py` retargets (function renames, validations,
  ticks).
- Region YAML `resource_signature` schema.
- Region garrison spawning.
- ~30 tests.

**SYN.2 — Wilderness-aware security (~1 sess)**
- `security.py` step 4 wilderness branch.
- `_apply_claim_upgrade` deletes.
- ~15 tests.

**SYN.3 — Contest state machine + culminating fight (~1.5 sess)**
- `engine/contest.py` new module.
- 7-day timer, accumulation, doubling influence.
- Region Anchor NPC spawning with HP/tier scaling.
- 4-hour culminating fight window.
- Outnumbered-defender bonus.
- Cooldown enforcement.
- ~30 tests.

**SYN.4 — Cities retarget + migration + vitality (~2 sess)**
- `player_cities.py::found_city/expand_city` retarget.
- Migration dissolves city-map cities with 75% refund.
- City vitality mechanic.
- Existing 553 cities tests retargeted.
- ~20 new tests for wilderness anchor flows.

**SYN.5 — Espionage-as-influence (~1 sess)**
- `engine/intel_handlers.py` new.
- Intel handler NPCs at faction HQs.
- `+intel handover` command.
- Director-AI evaluation stub.
- Mission/bounty/smuggling hooks retarget to wilderness-only.
- ~20 tests.

**SYN.6 — Active harvest + T5 crafting tier (~1.5 sess)**
- `engine/harvest.py` new.
- `harvest` command + skill check + cooldown + 15% tax.
- Weekly region quality variance.
- T5 crafting schematics catalogue.
- ~25 tests.

**SYN.7 — Wilderness anomalies Tier 1-2 (~2 sess)**
- `engine/wilderness_anomalies.py` new.
- ~12 type templates across Tier 1-2.
- Cadence engine.
- Imperial corvette boarding adapted from
  `encounter_boarding.py`.
- Reward distribution.
- ~30 tests.

**SYN.8 — Wilderness anomalies Tier 3 / world bosses (~2 sess)**
- Tier 3 templates: krayt, Maze Predator Apex, Capital Ship,
  Lost Patrol.
- Multi-phase combat with relocation.
- Participation-scaled loot.
- During-contest 2× cadence wiring.
- Trophy generation + housing display.
- ~25 tests.

**SYN.9 — Building construction (~2 sess)**
- `engine/buildings.py` new.
- Schema: `buildings` table.
- `+building` command suite.
- 24-hour construction timer.
- Ownership transfer rules.
- Category effects (residence storage, crafting station bonus,
  commerce stall, garrison annex, cultural hall).
- ~35 tests.

**SYN.10 — Display integration + launch polish (~1 sess)**
- Region look block.
- Faction influence dashboard rewrite.
- `faction contest` and `faction resource_outlook` commands.
- News digest expansions for all new event types.
- ~15 tests.

**Total: ~14.5 sessions across 11 drops (SYN.0 through SYN.10).**

### Post-launch sequence (T3.x)

- **T3.15:** Director AI CW-tuning replaces SYN.5 stub
  evaluation, enriches all narrative output.
- **T3.16:** Space Wildspace expansion (adds wilderness regions
  in space; contest mechanics inherit).
- **T3.17:** Sheet redesign incorporates region ownership +
  building list on character sheet.
- **T3.18:** Ground UX overhaul adds region map widget to web
  HUD.
- **T3.19:** Additional building categories (laboratory,
  shipyard, prison cell, training arena).

---

## 6. Deprecation Discipline

Per Pattern-2 hygiene. All surfaces retired by this pivot get
a `deprecated_after_design_pivot_2026_05_24` tag in TODO.json
and a docstring note in their source files referencing this
design document.

### Surfaces tagged for deprecation in SYN.0

- `engine/territory.py::claim_room` → SYN.1
- `engine/territory.py::unclaim_room` → SYN.1
- `engine/territory.py::is_room_claimed_by` → SYN.1
- `engine/territory.py::spawn_guard_npc` (per-room) → SYN.1
- `engine/territory.py::MAX_CLAIMS_PER_ZONE` → SYN.1 (delete)
- `engine/territory.py::MAX_CLAIMS_PER_ORG` → SYN.1 (delete)
- `engine/territory.py::tick_claim_maintenance` → SYN.1 (retarget)
- `engine/territory.py::tick_resource_nodes` → SYN.1 (retarget
  to passive + harvest)
- `engine/security.py::_apply_claim_upgrade` → SYN.2 (delete)
- `engine/player_cities.py` city-map zone validation → SYN.4
- `engine/player_cities.py` city-map adjacency → SYN.4
  (retarget to landmark graph)
- Drop 6D contest-state-machine room-keyed code → SYN.3
  (retarget to regions)

### Surfaces tagged for status transition (not retirement)

- `engine/world_events.py::KRAYT_SIGHTING` (event-only flag) →
  SYN.8 (becomes real Tier-3 anomaly; flag remains but now
  triggers actual spawn).
- `engine/encounter_boarding.py` (space-only) → SYN.7 (ground-
  adapted version for corvette anomaly; original surface
  untouched).

### Documentation retirement

- **Guide 11 (Territory Control)** rewrites in SYN.1+. Archives
  v1.
- **Guide 12 (Player Cities)** rewrites founding + expansion +
  vitality + buildings sections in SYN.4 / SYN.9.
- **Guide 04 (Security Zones)** §8 (Territory Claims and
  Security Upgrades) rewrites in SYN.2.
- **Guide 24 (Encounters & Hazards)** gets new sections on
  wilderness anomalies (Tier 1-2 in SYN.7, Tier 3 in SYN.8).
- **New Guide 27 (Buildings)** created in SYN.9.
- **Architecture v49** rolls up the pivot. Per
  `tracker_update_in_same_drop` discipline, each SYN drop
  updates TODO.json in the same drop; architecture v49
  captures consolidated view.

### Tests retirement

- Existing per-room claim tests: rewrite to region-scoped
  fixtures in SYN.1. Assertion shape preserved; only fixtures
  change.
- Drop 6D contest state machine tests: rewrite in SYN.3.
- Cities tests (553 currently): retargeted in SYN.4.
- Net test count expected to *grow* substantially (estimate
  +200 new across SYN.1-SYN.10).

---

## 7. Launch Implications

Architecture v48 §3.6 launch scope updates to:

> All security zones + faction-override SECMOD.1.
> Wilderness movement, all wilderness regions.
> **Region ownership + 7-day contest with culminating fight
> (SYN.1-SYN.3).**
> Player Cities v1.2 **(wilderness-anchored per SYN.4)** with
> **city vitality (SYN.4) and building construction (SYN.9)**.
> **Espionage-as-influence (SYN.5).**
> **Active harvest + T5 crafting tier (SYN.6).**
> **Wilderness anomalies Tier 1-2 (SYN.7).**
> **Wilderness anomalies Tier 3 / world bosses (SYN.8).**
> **Region look + faction dashboard (SYN.10).**
> Director AI (Clone Wars era, with SYN-aware digests).

The 11-drop SYN sequence is the pivot's full delivery. Each
drop is shippable in isolation; partial-pivot launches are
possible but **not recommended** — the system is most coherent
when the full set lands together.

---

## 8. Open Calls (Resolved May 24 2026)

These were the open questions from v1; all resolved in the
afternoon Q-rounds.

1. **City founding cost in wilderness**: keep existing
   25k/75k/200k by HQ subtype. ✅ (default)
2. **Migration timing for existing cities**: dissolve all at
   SYN.4 with 75% refund, single clean break. ✅ (Brian)
3. **Region garrison NPC strength**: tier1 default, tier2 once
   owning org has Control (100+) influence. ✅ (default)
4. **Director-AI evaluation of intel reports**: ship stub
   heuristic in SYN.5, replace with real Director output in
   T3.15. ✅ (default)
5. **Region naming consistency**: current naming works
   (tatooine_dune_sea, coruscant_underworld); canonicalize
   post-launch if desired. ✅ (deferred)
6. **Contest centrality**: hybrid — visible to all, mechanically
   optional, wilderness pulls engagement, city-map life is
   genuinely complete. ✅ (Brian afternoon Q1)
7. **Albion-style culminating fight**: yes — 7-day accumulation
   + 4-hour fight at contested landmark with influence-scaled
   Anchor HP. ✅ (Brian afternoon Q2)
8. **EVE ratting loop**: partial — passive baseline + active
   harvest + 15% non-owner tax. ✅ (Brian afternoon Q3)

All design decisions locked. Implementation begins at SYN.0.

---

## 9. Competitive Inspiration Trace

This pivot drew direct lessons from contestable-territory MMOs.
Documented here so future audits know what informed which
decisions.

**EVE Online (CCP, 2003-present):**
- Sovereignty mechanics → region-level ownership.
- Nullsec ratting → active harvest as daily income.
- Non-consensual roaming → opt-in-by-presence PvP in owned
  regions.
- Resource tax for non-owners (NSA cut) → 15% non-owner harvest
  tax.
- *Lesson explicitly: contest centrality* — we deliberately
  diverged toward SWG model for our small playerbase.

**Albion Online (Sandbox Interactive, 2017-present):**
- Black/red/yellow/blue zones gradient → maps to our
  Lawless/Contested/Secured tiers.
- Black-zone-only T8 resources → wilderness-only T5 crafting
  materials.
- GvG scheduled 5v5 → culminating fight at contested landmark.
- Outnumbered-defender bonuses → 1.5× influence rate when
  defenders are outnumbered.
- Faction warfare alongside guild warfare → factions are
  separate from guilds in our system (already true; reinforced).

**Star Wars Galaxies (SOE/LucasArts, 2003-2011):**
- Time-varying resource quality → weekly region quality
  variance (SYN.6).
- Player cities with rank/vitality → city vitality mechanic
  (SYN.4).
- Krayt dragon hunts → Tier-3 wilderness anomaly templates
  (SYN.8).
- Open GCW with constant low-grade hostility → existing `+pvp`
  flag system aligns; reinforced in pivot.
- Crafting as a real career → T5 wilderness-sourced crafting
  lane.

**Foxhole (Siege Camp, 2017-present):**
- Industrial supply chain → too heavy for our scale; the
  *principle* (crafters and combat-players need each other)
  informs interdependence design throughout.

**Eco (Strange Loop Games, 2018-present):**
- Small playerbase intensifies political stakes → validates
  cold-start choice; first weeks become founding myth.

**Realm of the Mad God (Wild Shadow, 2011-present):**
- Public dungeon participation-scaled loot → Tier-3 anomaly
  loot drops (krayt pearls = floor(participants/4)).
- Fast cycles + visible scaling → anomaly cadence varies by
  region state.

**Sindome (MOO, 1990s-present) — already mined in v1
competitive analysis:**
- Player interdependence → reinforced across the pivot.
- Persistent character vulnerability on logout → not adopted.
- Layered descriptions → considered post-launch.

**Armageddon MUD (RPI, 1991-2024) — already mined:**
- Environmental hazards as gameplay → shipped (Hazards system,
  Guide 24).
- Crafting tied to survival → reinforced by T5 wilderness-only
  materials.

---

## 10. Why This Is The Right Move Now

T2.WENC.a shipped the wilderness encounter substrate the
morning of May 24 2026. The natural next step was T2.WENC.b
(encounter dispatch) and T2.WENC.c (Director faction gates).
That work would have been correct in isolation — the encounter
system would work, encounters would fire NPCs, the wilderness
would feel alive.

But the wilderness wouldn't *do* anything for the players who
fought in it. The contest layer lived in the city-map zones.
The wilderness was atmosphere.

The pivot inverts that. City map becomes the neutral
civilization where players RP, trade, socialize, and craft —
unchanged from its current shipped state. Wilderness becomes
the political layer where:

- Factions actually fight for ground.
- Cities sit as citadels in contested territory.
- High-tier crafting requires presence.
- Anomaly events drive narrative tension.
- Intel handovers move the dial.
- Building construction lets players invest infrastructure.
- The Director narrates real and player-driven contests.

Two regions exist today (Dune Sea, Coruscant Underworld). The
post-launch roadmap adds more (Space Wildspace, additional CW
content). **Every new region becomes a new front in the
contest** — a content lever that scales with development.

The competitive review confirmed the structural moves were
right and tuned the knobs (hybrid centrality, culminating
fight, partial harvest). The work survives at the test-
assertion level; only the fixtures change. The shipped
surfaces aren't wasted — they're the foundation the new model
retargets onto.

The synthesis is a *better* game, not just a more polished
one. That's worth ~14.5 sessions of pivot work and the
documented deprecation of shipped surfaces.

This is the kind of step-back that pays for itself.

---

## 11. Locking statement

**This design is locked May 24 2026.** Subsequent drops in the
SYN sequence reference this document by name. Changes to the
design (if any) require:

1. A new revision (`contestable_wilderness_design_v3.md`) with
   explicit supersede note.
2. A CHANGELOG.md entry calling out the design revision.
3. A TODO.json update flagging the design revision.

Drift between this document and the implementation is a
**Phantom-1 violation** (handoff says X shipped, HEAD says no)
if implementation diverges silently, or a **Phantom-2
violation** (handoff says X pending, HEAD says shipped) if
implementation exceeds the design silently. Both require
remediation in the same drop they're noticed.

This document IS the source of truth. The drop sequence IS the
implementation. TODO.json + CHANGELOG.md are the running ledger.
Architecture v49 will roll up the consolidated state when the
SYN sequence completes.

End of v2 design lock.
