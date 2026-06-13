# Difficulty Tiers / Zoned Content Progression — Design v1

**Status:** DESIGN (resolves T2.DIFF.difficulty_tiers_design). Direction
approved by Brian 2026-06-07 (D2: extend the security-zone + wilderness
machinery; no parallel system). This doc makes the six open
sub-decisions and specifies the build.

**Author:** overnight autonomous session, 2026-06-13. Brian invited
counter-proposals ("if you have something better I'm all ears") — the
calls below are mine; flag any you'd reverse.

**Era:** Clone Wars (~20 BBY), WEG R&E D6.

---

## 0. The problem (Brian's words)

> No difficulty levels today. New players should be able to experience
> combat (and space combat) in a NEWBIE area, mid-game players in
> another, end-game in another. Wilderness should have SECTIONS with
> KNOWN lines (players see where the tiers are). PC cities should
> probably only sit in mid-to-high difficulty areas.

## 1. The one load-bearing insight: difficulty ≠ security

The existing security model (`engine/security.py`,
`security_zones_design_v1.md`) answers **"is combat/PvP allowed here?"**
— SECURED (no combat) / CONTESTED (NPC combat + consensual PvP) /
LAWLESS (open PvP). It says nothing about **how dangerous** the things
you fight are.

Those are orthogonal questions. A LAWLESS deep-desert tile can be
newbie-easy (womp rats) or end-game-deadly (a krayt dragon). A SECURED
city core forbids combat whether it's the newbie hub or the veteran
capital. **Difficulty is a separate axis layered onto zones, not a
rename of the security level.** (Sub-decision #2, resolved: separate
parallel axis. Conflating them would force every newbie zone to be
SECURED — killing the "newbies fight in a newbie area" requirement,
since SECURED forbids combat entirely.)

So we add ONE new orthogonal property — a **threat band** — alongside
the existing `security`, read through the same zone→room inheritance
chain, surfaced on the same map/header UI, and consumed by the same
spawn/encounter machinery that already exists.

---

## 2. Sub-decision #1 — taxonomy + count

**Resolved: four named bands with a backing numeric rating.**

| Band | Numeric | Player-facing label | Who it's for |
|------|---------|--------------------|--------------|
| `frontier` | 1 | **Frontier** | brand-new chars (chargen → ~first session) |
| `settled` | 2 | **Settled** | found their feet; the default mid-game band |
| `contested_marches` | 3 | **Contested Marches** | seasoned; real risk, real reward |
| `wilds` | 4 | **Deep Wilds** | end-game; world-boss / Tier-3 anomaly country |

Why four, not three: Brian named three (newbie / mid / end-game) but the
gap between "found my feet" and "end-game" is the longest stretch of a
character's life — splitting it into Settled / Contested Marches gives
the mid-game somewhere to *progress through* instead of one undifferentiated
plateau. Four also maps cleanly onto the encounter `tier1/tier2` +
`threat_tier: miniboss` + Tier-3 world-boss content that ALREADY exists
in the wilderness data (see §6).

Named bands (not bare numbers) for the player UI — "Deep Wilds" reads as
a place, "threat rating 4" reads as a spreadsheet. The numeric backing
(`threat_rating: 1..4`) is what code compares so future content can
interpolate or add a band 5 without renaming.

The band name is era-neutral and B3-clean (no Imperial/Rebel framing).

---

## 3. Sub-decision #3 — hard gate vs advisory

**Resolved: advisory by default, with ONE soft gate for the top band.**

- **Frontier / Settled / Contested Marches:** advisory. The line is
  *visible* (map color + room/zone header tag + a one-time crossing
  banner) but never blocks movement. A player who wanders from Settled
  into Contested Marches gets a "⚠ You are entering the Contested
  Marches (threat 3) — hostiles here are seasoned" banner, then proceeds.
  This honors "players see where the tiers are" without walling off the
  sandbox. A MUSH lives on emergent exploration; hard walls on the
  overworld feel like a theme-park rail.

- **Deep Wilds (band 4):** a soft gate — crossing the boundary prompts a
  confirmation ("The Deep Wilds will kill an unprepared hunter. Travel
  on? `yes`/`no`") the FIRST time per character. Not a level lock (no
  "you must be level X"); just a deliberate, informed opt-in so a fresh
  char doesn't sleepwalk into a krayt dragon. After the first confirm,
  it reverts to advisory for that character (a `wilds_acknowledged` flag
  in chargen_notes).

Rationale: the only place the danger delta is lethal enough to warrant
friction is the top band. Everywhere else, the warning IS the mechanic.
This keeps the "no parallel system" discipline — the soft gate reuses
the existing movement-confirmation pattern, no new gating engine.

**Newbie-area protection (the inverse gate):** we do NOT need a gate to
keep veterans out of Frontier (a veteran in a newbie zone is harmless —
the content is trivially easy, not exploitable since rewards scale with
threat; see §7). The protection that matters is keeping *danger* out of
the newbie zone, which §6's tiered spawn tables handle directly.

---

## 4. Sub-decision #2 (resolved above) + how the axis attaches

**Storage:** `zone.properties.threat_band: <name>` with room-level
override `room.properties.threat_band`, read through the SAME resolver
shape as security:

```
effective_threat(room) =
    room.properties.threat_band
    ?? zone.properties.threat_band
    ?? wilderness_region.threat_band   # for wilderness tiles
    ?? DEFAULT (settled, band 2)
```

Default is **Settled (2)**, not Frontier — an unmarked zone should be
"normal mid-game", not "trivially safe" (safer default against an
author forgetting to tag a dangerous zone; a missing tag fails toward
*more* caution-surfacing, not less).

New engine module surface (small, mirrors `engine/security.py`):
`engine/threat_band.py` —
- `ThreatBand` enum (FRONTIER=1, SETTLED=2, CONTESTED_MARCHES=3, WILDS=4)
- `get_effective_threat(room_id, db) -> ThreatBand` (zone→room inherit)
- `threat_label(band) -> str` (player-facing, ANSI-tagged)
- `threat_color(band)` for the map renderer

It does NOT touch `get_effective_security` — orthogonal call, orthogonal
property. A room has BOTH a security level AND a threat band.

---

## 5. Sub-decision #4 — per-world tier map (the 6 launch worlds)

Principle: every NEW character's chain starting zone must be **Frontier**,
so the onboarding chains (drop 24/25) run in safe water. End-game bands
live in the wilderness/edge zones, not the city cores. PC cities sit
Settled+ (Brian: "PC cities should probably only sit in mid-to-high
difficulty areas").

| World | Frontier (1) | Settled (2) | Contested Marches (3) | Deep Wilds (4) |
|-------|-------------|-------------|----------------------|----------------|
| **Kamino** (Tipoca) | tutorial briefing/sim/transport (republic_soldier start) | Tipoca city proper | — | open ocean platforms (storm country) |
| **Geonosis** | foundry briefing/drill (separatist_commando start) | foundry districts | the catacombs / hive deep | the Ey'akh wastes (wilderness) |
| **Tatooine** | Mos Eisley spaceport + market (smuggler start) | Mos Eisley town, Bestine | Jundland fringe, smuggler holdouts | Dune Sea deep + Ey'akh (krayt country) |
| **Nar Shaddaa** | BHG chapter house + promenade (bounty_hunter start) | promenade levels, landing docks | warrens, lower levels | deep undercity / Reaper territory |
| **Coruscant** | monumental/judicial plazas + safehouse (intel start) | commercial/commerce districts | underworld upper levels (NE/NW) | underworld bottom (SE mazefringe / SW deepwarren) |
| **Kuat** | KDY apprentice bays (shipwright start) | orbital ring, main spaceport | shadow-yards / derelict ring | the breaker fields (wilderness) |

Note this map is mostly a **labeling pass over zones that already
exist** — the chain starting rooms are already built (drop 24/25), the
Coruscant Underworld already has NE/NW/SE/SW wilderness regions with
graded danger (the landmarks file already calls SE/SW "high-danger" and
tags a `threat_tier: miniboss`), the Dune Sea + Ey'akh already exist.
The build is: add `threat_band` to each zone's `properties`, additively.

---

## 6. Sub-decision (spawn/threat scaling) — tiered spawn over EXISTING content

The wilderness encounter pools already carry `payload.tier: tier1/tier2`
and landmark `threat_tier: miniboss`. Today the runtime
(`engine/wilderness_encounter_runtime.py`) spawns by `npc_template` +
`count` and does NOT read `tier` for scaling — `tier` is currently just
an author label. We make it load-bearing:

**Eligibility filter (the core mechanic):** each encounter-pool entry
gains an optional `min_band` / `max_band` (default: eligible in all
bands). The runtime, when rolling an encounter for a tile, filters the
pool to entries whose `[min_band, max_band]` contains the tile's
effective threat band. So:

- A **Frontier** tile draws only `min_band ≤ 1` entries — the
  trivial fauna + low-tier thugs (the `womp_rat`, `ranza_pack`,
  `underworld_thug count:[2,3] tier1`). No miniboss, no Tier-2 ambush.
- A **Deep Wilds** tile unlocks the `threat_tier: miniboss` and
  Tier-3 anomaly entries that are gated out everywhere else.

This is purely additive to the encounter schema (a new optional pair of
keys) and it makes the existing `tier` labels meaningful: tier1 content
authors `max_band: 2`, tier2 authors `min_band: 3`, etc. No creature
re-statting — the danger gradient is already in the creature library;
we're gating *which* creatures a zone can roll.

**Space-lane tiering (sub-decision #5):** YES, space routes get the same
bands. A space zone (`space_tatooine`, etc.) carries `threat_band` the
same way; the space-encounter manager (`engine/space_encounters.py`)
gets the same `min_band/max_band` eligibility filter over its patrol /
pirate / hazard pools. Frontier space lanes spawn lone scout pirates;
Deep Wilds lanes spawn CIS patrol wings. Same orthogonal property, same
filter pattern — no separate space difficulty system. (The space hub
zones near the newbie starts are Frontier; the deep / border lanes are
Contested Marches / Wilds.)

---

## 7. Sub-decision #6 — newbie PvP safety + reward scaling

**PvP safety:** the *security* axis already protects newbies — Frontier
starting zones are authored SECURED or CONTESTED (consensual PvP only),
so a fresh char can't be ganked in the tutorial hub regardless of threat
band. We add ONE belt-and-braces rule: **open PvP (LAWLESS) is
incompatible with the Frontier band** — a zone may not be both `frontier`
and `lawless`; the world-loader validates this and a violation is a load
error. (You can't make a newbie zone a free-fire PvP zone by accident.)
This is the only hard constraint coupling the two axes, and it's a
one-line validator.

**Reward scaling (prevents veterans farming newbie zones AND makes
progression matter):** bounty/mission/encounter credit + rep rewards get
a **threat-band multiplier** applied through the existing
`adjust_credits(...)` faucet — Frontier ×0.6, Settled ×1.0, Contested
Marches ×1.4, Deep Wilds ×2.0 (tunable). A veteran *can* fight in a
Frontier zone but earns 60% — so there's no incentive to camp newbie
content, and pushing into higher bands is the natural income gradient.
This rides the existing credit chokepoint (no new faucet); the
multiplier is applied at the reward site with a `"threat_band"` tag
component so the economy ledger shows it. Faucet discipline: this scales
an EXISTING faucet, introduces no new credit source.

---

## 8. UI surfacing (the T2.UIPKG tie-in)

- **Room/zone header:** the room display gains a threat tag next to the
  existing security tag — `[SETTLED]` / `[CONTESTED MARCHES]` etc.,
  color-graded (green→yellow→orange→red). Reuses the
  `security_label`-style ANSI helper.
- **Map renderer:** zones tint by threat band (a translucent overlay,
  toggleable) so "players see where the tiers are" at a glance — the
  KNOWN LINES Brian asked for. This is the map-side of T2.UIPKG.
- **Crossing banner:** on a band change between adjacent rooms, a
  one-line advisory (and the §3 soft-gate confirm for Wilds).
- **`+threat` / `threat` command** (or folded into `look`): shows the
  current tile's band + a one-line "what this means".

All UI is additive; nothing changes the security display.

---

## 9. Build plan (phased, each its own drop)

1. **DIFF.1 — engine axis + validator.** `engine/threat_band.py`
   (enum + resolver + labels + colors), world-loader reads
   `properties.threat_band`, the frontier≠lawless validator, unit tests.
   No content yet — default Settled everywhere, so zero behavior change.
2. **DIFF.2 — zone labeling pass.** Add `threat_band` to every zone's
   `properties` per §5's map (additive YAML). Room/zone header tag +
   `+threat` command. Golden-snapshot map guard unaffected (additive).
3. **DIFF.3 — tiered encounter eligibility.** `min_band/max_band` on
   encounter-pool entries; runtime filter in
   `wilderness_encounter_runtime` + `space_encounters`. Author the
   band bounds onto the EXISTING pools (Coruscant Underworld, Dune Sea,
   Ey'akh, space lanes). Crossing banner + Wilds soft-gate.
4. **DIFF.4 — reward multiplier.** Band multiplier at the
   bounty/mission/encounter reward sites through `adjust_credits`.
5. **DIFF.5 — map renderer tint + UI polish.** The map overlay
   (T2.UIPKG coordination point).

Phases 1–4 are autonomous engine/data/test work. Phase 5 touches the web
map and wants a browser eyeball (Brian).

---

## 10. What this deliberately does NOT do

- No character "level" — SW D6 has no levels; threat bands gate by
  *advisory + spawn eligibility*, never by a numeric character gate.
  Progression is skill dice (already modeled), not an XP wall.
- No parallel difficulty system — every piece rides security's resolver
  shape, the existing encounter pools, the existing credit faucet, the
  existing map UI.
- No re-statting creatures — the danger gradient already exists in the
  creature library; we gate *which* creatures a zone rolls.
- No hard movement walls (except the one-time Wilds confirm) — the
  sandbox stays open; the lines are KNOWN, not LOCKED.

---

## 11. Open items genuinely for Brian (not blocking the build)

- The band multipliers in §7 (0.6 / 1.0 / 1.4 / 2.0) are first-guess
  tunables — fine to ship and tune from telemetry post-launch (this is
  exactly the kind of value the post-launch tuning LOOP adjusts).
- The four band NAMES (Frontier / Settled / Contested Marches / Deep
  Wilds) are a flavor call — swap freely if you have better.
- Whether `+threat` is its own command or folded into `look` — I lean
  folded into `look` (one less command to learn) with `+threat` as an
  alias.
