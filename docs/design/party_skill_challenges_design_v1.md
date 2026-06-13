# Party Skill Challenges — Design v1 (POST-LAUNCH)

**Status:** DESIGN ONLY — post-launch content. No engine code in this doc.
**Requested by:** Brian, 2026-06-13 (sparked by the breaching-charge work —
"D&D-style content where you need different party members: a rogue for
locks, a face, a cleric for healing, a wizard for spells").
**Author:** Claude Opus 4.8 (main session), grounded against HEAD.
**Build posture:** non-invasive — EXTEND the existing multi-phase anomaly
engine; do not add a parallel dungeon system.

---

## 1. The pitch (Brian's words, captured)

End-game content that rewards a **skill-diverse team** the way a D&D
party does: you want a rogue (locks/traps), a face (social), a cleric
(healing), a wizard (Force), a demolitions hand (breaching), and
fighters. A lone character is a jack-of-no-master at end-game depth, so a
balanced party dramatically outperforms — but (Brian's call) **nothing is
hard-locked to "you must bring 4 players"**: a lone wolf CAN attempt every
phase, just at a steep, punishing penalty. Post-launch; non-invasive.

## 2. Why this is an EXTENSION, not a new system

Verified against HEAD — the substrate already exists in
`engine/wilderness_anomalies.py`:

| Need | Existing seam (HEAD) | Posture |
| --- | --- | --- |
| Multi-phase encounters | T2/T3 anomaly `phases: [...]` — advance on last-NPC-of-phase death, final-phase clear fires the reward | **EXTEND** — a phase can gate on a SKILL check instead of (or before) combat |
| Participation tracking | `WildernessAnomaly.kill_counts` (per-char), participant enumeration at payout | **REUSE** — credit each role's contribution (who breached / sliced / healed / killed) |
| Skill-check resolution | `investigate <id>` already rolls an authored `skill`+`difficulty` via `perform_skill_check` | **REUSE** — the per-phase skill gate is the same check, keyed per phase |
| Participation-scaled rewards | `_payout_combat_anomaly` (T3): participants = `kill_counts.keys()`, scaled t5-mat distribution + trophies | **REUSE** — Brian's chosen reward model; extend "participant" to include non-combat contributors |
| Spawn / anchor / cadence | anomaly tick + anchor room + duration window | **REUSE** — a party challenge spawns/anchors like any anomaly |
| The role skills themselves | breaching (`breach`/Demolitions, drop 40), `picklock`/Security, Medicine/stims, Force powers, Bargain/persuasion/intimidation, combat | **REUSE** — all already exist as live verbs/checks |

A "party dungeon" = a multi-phase anomaly where **each phase gates a
different skill**, so no single character has all the end-game-depth
skills to clear it efficiently. Zero new top-level system.

## 3. The core mechanic — skill-gated phases

Extend the anomaly phase schema with an optional **`skill_gate`** per
phase (alongside the existing combat `combat_npcs`):

```yaml
phases:
  - name: "The Sealed Vault Door"
    intro: "A blast door, locked and reinforced, bars the way deeper."
    skill_gate:
      skill: demolitions        # the role this phase wants
      difficulty: 22
      alt_skills: [security]     # a slicer can also open it (rogue path)
      solo_penalty: 8           # +difficulty when attempted by a lone wolf
      on_clear: "The door grinds open."
  - name: "The Wounded Contact"
    intro: "Your contact is bleeding out; stabilize them to learn the way on."
    skill_gate:
      skill: medicine
      difficulty: 18
      alt_skills: [first aid]
  - name: "The Guardian"          # a normal combat phase (existing schema)
    combat_npcs: [...]
  - name: "The Negotiation"
    intro: "The vault's keeper will let you leave with the prize — for a price."
    skill_gate:
      skill: persuasion
      difficulty: 20
      alt_skills: [intimidation, con]   # face OR brute OR liar
```

- A phase with `skill_gate` advances when ANY present character passes
  the check (the team's specialist steps up). `alt_skills` lets a
  different role substitute (the rogue picks the lock the demolitions hand
  would breach) — this is what makes "bring SOME mix" work without
  hard-locking one exact class.
- Combat phases use the existing `combat_npcs` machinery unchanged. A
  challenge interleaves skill phases and combat phases freely.

## 4. Soft-require (Brian's call) — soloable but punishing

Per Brian: no hard population lock. Implemented as a **`solo_penalty`**:
when the only character engaging the challenge attempts a skill-gate, the
difficulty rises by `solo_penalty` (and/or failure has a steeper cost —
a wound, a consumed resource, a time penalty). A balanced party each
clears their specialty at base difficulty; a solo character faces every
gate at penalty, across every role, with no one to cover their weak
skills. So:
- **Soloable:** a sufficiently over-leveled lone wolf CAN grind it.
- **Punishing:** the penalty stacks against a generalist; a party is
  dramatically more efficient and safer.
- **No dead content:** low population never hard-locks the challenge
  (the MMO "can't even start without 4 people" failure mode is avoided).

`min_party_size` is deliberately NOT a gate in v1. (A future hard-require
"raid" capstone could add one — left out of v1 per the soft-require call.)

## 5. Rewards — participation-scaled t5 mats + credits (Brian's call)

Reuse the T3 anomaly reward model (`_payout_combat_anomaly`), with one
extension: **"participant" includes non-combat contributors.** Today
participants = `kill_counts.keys()`; party challenges also credit anyone
who **cleared a skill-gate phase** (breached, sliced, healed, negotiated).
- A `contribution_log` (per char: phases cleared + kills) replaces the
  combat-only `kill_counts` for these encounters.
- Payout: participation-scaled **t5 crafting materials** (the same band
  the T3 apex drops — feeds the t5 master-trainer crafting economy we just
  shipped) + **credits** (via the metered anomaly reward faucet) + a
  **trophy** per participant.
- This ties party content INTO the end-game crafting loop: the mats it
  drops are what the t5 trainers' recipes consume. Clean economic circle,
  no new reward system, no new faucet.

## 6. Non-invasive scoping (the "as long as it's non-invasive" constraint)

- **Extends one engine** (`wilderness_anomalies.py`) — the `skill_gate`
  phase field is additive; existing combat-only anomalies are unchanged
  (no `skill_gate` = behave exactly as today).
- **No new top-level system, command, or schema migration** — party
  challenges are authored anomaly templates; `investigate` + the existing
  role verbs (`breach`, `picklock`, `stim`, Force, social) drive them.
- **No new reward faucet** — rides the anomaly reward path.
- **All role skills already exist** — nothing new to build mechanically;
  the work is the phase-gate field + the participation extension + content
  authoring.
- **Pre-launch hook (optional, tiny):** if we want party challenges live
  soon after launch, the only pre-launch-worth scaffolding is the
  `skill_gate` phase field in the anomaly schema (inert until a template
  uses it) — same "land the seam early" pattern as ambient-life's DB
  scaffolding. Otherwise it's a pure post-launch content + small-engine
  drop.

## 7. Phased build plan (post-launch)

- **Phase 1 — engine seam:** add the `skill_gate` phase field + resolution
  (skill check, `alt_skills`, `solo_penalty`) to the anomaly phase
  machinery; the `contribution_log` participation extension. Behavior-
  neutral for existing combat anomalies. Tests: a 2-phase "breach then
  slice" challenge walks via the role verbs.
- **Phase 2 — first authored challenge:** one full skill-diverse end-game
  challenge (e.g. a Coruscant Underworld vault: breach → slice → heal a
  contact → boss fight → negotiate the exit), reward-tuned to drop t5
  mats. Proves the loop end-to-end.
- **Phase 3 — content scale-out:** more challenges across the
  Contested/Wilds zones, themed per faction/region.
- **Phase 4+ (deferred):** a true HARD-require "raid" capstone with
  `min_party_size` (the one place hard party-gating is warranted), if v1
  proves the soft-require model fun.

## 8. Open design calls for Brian (when this comes off the shelf)

1. **`solo_penalty` magnitude** — how punishing is the lone-wolf tax
   (rec: +6–10 difficulty per gate, tuned post-launch from telemetry).
2. **Failure cost** on a missed skill-gate — retry-allowed (like
   `chain attempt`) vs a wound/resource cost vs phase-abort. Rec:
   retry-allowed with a small resource/time cost, not a hard abort
   (frustration control).
3. **`alt_skills` breadth** — how many roles can substitute per gate (rec:
   1–2 alts, so a gate favors a role without hard-locking it).
4. **Where the first challenge lives** + its theme (rec: a Coruscant
   Underworld vault — ties to the scavenged-tech salvage flavor).
5. **Trophy/unique-reward question** — Brian chose participation-scaled
   t5 mats + credits for v1; revisit whether a unique gated drop is added
   later (the "only obtainable in a party" pull).

## 9. Relationship to other systems
- **Feeds** the t5 master-trainer crafting economy (drops 33–35) — party
  challenges drop the t5 mats those recipes consume.
- **Composes** the role verbs: breaching (drop 40/42), `picklock`,
  medicine/stims, Force, social, combat.
- **Extends** the wilderness-anomaly engine (T2/T3) — same multi-phase +
  participation + reward substrate.
- **Sibling to** ambient NPC life (T3.22) — both are post-launch
  end-game-feel systems built non-invasively on existing engines.
