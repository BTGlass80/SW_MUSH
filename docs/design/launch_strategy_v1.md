# SW_MUSH — Launch Strategy
## Version 1.0 — April 18, 2026 · Opus parallel session (Clone Wars track)
### The anchoring document for scope, priority, and tier decisions.

---

## 1. Purpose

This document codifies the phased-launch strategy for SW_MUSH and the launch-day tier allocation for Jedi Masters and Knights. It is the anchor every future design decision should check against. If a feature, an economy choice, or a scope expansion assumes a 1000-player launch, this document overrides that assumption.

---

## 2. Core Assumption

**SW_MUSH launches small and grows.** Expect 20-50 concurrent players at peak in the first six months. Expect closed beta to produce a cohort of 15-30 dedicated testers. Expect open launch to add 50-150 additional players over the first quarter.

Do not design for 1000 concurrent players. Do not design for 100 concurrent players. Design for 50, with graceful scaling paths where cheap to include and deferred scaling work where expensive.

---

## 3. What This Unlocks

Several architectural anxieties dissolve once the 50-player assumption is the default:

### 3.1 Budget ceilings are fine where they are.

- Claude Haiku at ~$20/month for Director AI / narrative memory at 50 players = sustainable
- Ollama/Mistral 7B on a single RTX 3070 8GB = sufficient for NPC dialogue at 50-player concurrent load
- SQLite (aiosqlite) = sufficient; no migration to Postgres until sustained 100+ concurrent
- Single-server deployment = sufficient; no distributed architecture work needed

### 3.2 Economy tuning is a beta problem, not a launch problem.

You cannot tune an economy without real player behavior data. Ship the launch economy with sensible starting values per `economy_hardening_design_v1.md`, observe what breaks during beta, hotfix. The existing `economy_audit_v1.md` identifies trade goods exploit as high-priority for pre-launch hardening — that stays. Fine-grained balance (daily caps, mission payout curves, crafting material costs) does not.

### 3.3 Feature cuts are the default, not the exception.

A system is launch-ready when its minimum functional version works. Not its complete version. The Padawan/Master system ships with Masters-can-take-Padawans, Padawans-have-linked-Master, Master-approves-Trials. Council politics, tribunal mechanics, formal lineage trees, Padawan re-assignment ceremonies — all deferred to post-launch expansion.

### 3.4 Marketing is narrow and targeted.

Later-phase marketing work (flagged by Brian for future session) will focus on a handful of high-signal channels: r/MUD, r/StarWarsEU, SWRPG Discord servers, a few WEG-focused forums, and the MUD Coders Guild. 100 of the right players beats 1000 of the wrong ones. We do not need ProductHunt, HackerNews, or mainstream gaming press.

### 3.5 Testing cohort becomes the backbone.

Pre-launch testers are the right people — anyone who grinds through a pre-launch text MUSH to file bugs and stress-test systems is, by definition, someone who cares about the setting, understands the WEG D6 ruleset, and can RP. This is the cohort you want modeling good behavior for launch-day newbies. They are also the natural pool from which launch-day Masters and Knights are drawn.

---

## 4. Phase Definitions

| Phase | Duration | Goal | Player Count |
|---|---|---|---|
| **Alpha** | Current → T-60 days | Engine stability, no catastrophic bugs | Developer only (Brian) |
| **Closed Beta** | T-60 → T-30 days | System integration testing, balance probes, world stress testing | 15-30 invited testers |
| **Open Beta** | T-30 → T-0 | Onboarding flow, tutorial polish, economy observation | 30-75 testers (invited + referrals) |
| **Launch** | T-0 | Public opening | 50-150 in first quarter |
| **Growth** | Post-launch | Feature expansion, Drop 2+ content | Organic growth; revisit strategy at 100+ concurrent |

**Closed beta invitation criteria:** personal outreach + WEG community known-quantities. No open sign-up. Goal is high signal-to-noise: every beta tester should be someone Brian can identify by handle.

**Open beta invitation criteria:** closed beta referrals + targeted outreach to named community members. Still not a public sign-up link. Open beta tests the onboarding flow with people who don't already know the developer personally.

**Launch:** public sign-up opens. Marketing push to narrow channels begins. Beta cohort transitions into launch-day Master/Knight tier per §5.

---

## 5. Launch-Day Tier Allocation

The Padawan / Knight / Master tier hierarchy is defined in `padawan_master_system_design_v1.md`. This section defines **who occupies which tier at launch** and how they're chosen.

### 5.1 Tester-Seeded Tier Structure

**Launch-day Masters are drawn from the pre-launch tester cohort.** No NPC Masters. No staff-run Masters. No day-one open Master chargen.

Launch-day Knights are similarly drawn from testers, with a broader allocation.

Launch-day open sign-up produces Padawan and non-Jedi PCs only.

### 5.2 Allocation Criteria

Tier assignment is **contribution-based, not self-select**. Testers earn tier through demonstrated behavior during alpha/beta, not by requesting it.

| Tier | Launch Criteria |
|---|---|
| **Master** (cap: 5-8) | Consistent beta participation + demonstrated RP leadership (hosted events, mentored other testers, contributed to world lore or taught systems to newcomers) + commitment to weekly login during first 90 days post-launch |
| **Knight** (cap: 10-15) | Consistent beta participation + quality bug reports and/or system-stress testing + RP'd consistently in beta (not just mechanical testing) |
| **Padawan or non-Jedi** | All other testers; equivalent to standard open-launch chargen |

**Soft caps.** The Master and Knight caps above are targets, not absolutes. A beta cohort with only 3 Master-qualified testers ships with 3 Masters. A beta cohort with 10 Master-qualified testers ships with 8 and bumps 2 to Knight. Err on the side of scarcity — Masters should feel rare.

**Transparency.** Criteria are published to the beta cohort before tier assignments are made. This heads off the "why did they get Master and I didn't" drama that always happens when tier is discretionary and undocumented.

### 5.3 The Active-Master Obligation

A launch-day Master who takes a Padawan PC has a responsibility to that player. A Master who vanishes leaves their Padawan orphaned in a way that damages the game's social fabric.

**Obligation:** Masters who take a Padawan must log in at least weekly during that Padawan's first 90 days. A Master who fails this has their Padawan reassigned (see §5.5).

**Opt-out mechanism:** Tester-Masters who know they cannot commit to the obligation should be offered Knight instead. This conversation happens before tier assignment, not after. No surprise penalties; no post-hoc judgment.

### 5.4 Master Supply vs. Padawan Demand

Launch-day math: 5-8 Masters × 1 Padawan each (strict rule at launch) = 5-8 Padawan slots available on day one.

If more than 8 players roll Padawan on launch day, the surplus enters a **Padawan waitlist**. Waitlisted Padawans are playable — they begin at the Jedi Temple on Coruscant, can interact with other PCs, can train in basic skills — but they have not yet been formally apprenticed to a Master. Assignment to a Master happens as Masters become available (existing Padawans advance to Knight, new Masters are earned in-game, etc.).

This is narratively coherent: the Jedi Order does have Initiates at the Temple awaiting assignment. It's canon.

**No multiple Padawans per Master at launch.** Post-launch, this rule can loosen (some canon Masters had two apprentices at different stages), but at launch the clean 1:1 rule avoids overload.

### 5.5 Padawan Reassignment

Triggers for reassignment:
- Master PC inactive >2 weeks without notice
- Master PC fails the active-Master obligation in first 90 days
- Master PC voluntarily relinquishes apprentice (with Padawan consent or staff mediation)
- Master PC falls to the dark side narratively (see `padawan_master_system_design_v1.md` §7)
- Irreconcilable OOC conflict between players (staff-mediated)

Reassignment process: staff-run. Padawan is notified, offered a choice of available Masters (or the waitlist), and the narrative transition is handled with in-universe explanation (Master recalled to Temple, reassigned to front, killed in action, etc.).

### 5.6 Earning Master Tier In-Game

Post-launch, Master tier is earned through gameplay: a Knight PC who has taken a Padawan through Trials to Knighthood is eligible to take a second Padawan and be recognized as a Master themselves. The Council (NPC-authority, adjudicated by staff or Director AI) confirms the promotion.

This means the launch-day Master cohort is not static — over months, tester-Knights advance to Masters by training Padawans to Knighthood, and the ecosystem grows organically.

**No direct-roll Master in post-launch chargen.** New players cannot start as Masters. This preserves the earned nature of the tier and prevents tier inflation.

---

## 6. What This Does NOT Solve

This document anchors strategy. It does not replace design work. The following still need their own docs:

- **`padawan_master_system_design_v1.md`** — Master-Padawan mechanical bond, Trials system, Master veto/approval weights, fall mechanics, Knight promotion ceremony.
- **`weight_of_war_design_v1.md`** — cumulative war-strain tracking for Jedi PCs (distinct from DSP), Director AI integration, narrative surfacing.
- **`beta_onboarding_design_v1.md`** (future) — tester recruitment criteria, invitation process, beta feedback channels, criteria publication.

---

## 7. Decisions Codified

The following decisions are **locked** by this document unless explicitly revisited:

1. Launch target: 50 concurrent players, not 1000.
2. Closed beta cohort size: 15-30.
3. Launch-day Masters: tester-seeded, contribution-based, cap 5-8.
4. Launch-day Knights: tester-seeded, cap 10-15.
5. Launch-day open sign-up: Padawan and non-Jedi only.
6. No NPC Masters. No staff-run Masters.
7. Active-Master obligation: weekly login during Padawan's first 90 days.
8. 1:1 Master-Padawan ratio at launch.
9. Padawan waitlist is canon (Initiates awaiting assignment at Temple).
10. Post-launch Master promotion: earned in-game by training a Padawan to Knighthood. No direct-roll Master in open chargen.

These decisions drive scope, priority, and implementation work for Drop 1 and beyond.

---

*End of Launch Strategy v1.0 — April 18, 2026.*
*Anchoring document for the Clone Wars track.*
*Paired with: clone_wars_era_design_v4.md, padawan_master_system_design_v1.md (pending), weight_of_war_design_v1.md (pending).*
