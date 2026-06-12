# SW_MUSH — Weight of War Design
## Version 1.0 — April 18, 2026 · Opus parallel session (Clone Wars track)
### Cumulative war-strain tracking for Jedi PCs.

---

## 1. Purpose

This document defines the **Weight of War** system: a cumulative strain metric for Jedi PCs that models the psychological and spiritual cost of commanding armies in the Clone Wars, distinct from Dark Side Points.

The goal is to make Jedi PCs feel the pain of the canon-mandated role (Jedi Generals commanding clone troopers) without punishing players for being in the setting. Weight of War is the Anakin trajectory, mechanically modeled: you don't fall from one big act, you fall from a thousand small compromises under pressure.

**Prerequisites:** `clone_wars_era_design_v4.md` (faction structure, Clone Wars context), `launch_strategy_v1.md` (phased launch anchor), `padawan_master_system_design_v1.md` (bond mechanics), `jas_extraction_v1.md` (Jedi Code and Sith contrast), `director_ai_design_v1.md` (narrative integration).

---

## 2. Core Principle

**Weight of War is not Dark Side Points.** It does not directly flip a character to the dark side. It is a separate metric that tracks cumulative strain from sustained wartime service.

High Weight of War makes DSP-triggering actions *easier to rationalize*, through Director AI narrative effects and subtle mechanical modifiers. It models the reality that a Jedi who has been on the front lines for two years, seen ten thousand clones die under their command, and witnessed civilian horror, finds it harder to hold the Code than a Jedi fresh from meditation at the Temple.

**Weight of War applies only to Jedi PCs.** Non-Jedi PCs (soldiers, smugglers, bounty hunters) have their own stress mechanics already present in the engine (wound track, fatigue, reputation) and do not carry this burden. Weight of War is specifically about the Jedi's special relationship with the Force being compromised by war.

---

## 3. What Weight of War Is NOT

To prevent design drift, some clarifications:

- **It is not PTSD.** SW_MUSH is not trying to model real-world combat trauma. Weight of War is a Force-connection metric in the Star Wars idiom.
- **It is not permanent penalty.** Weight of War decays over time during peace (meditation, Temple return, time at peace).
- **It is not DSP gating.** A character can fall to the dark side without ever accruing Weight of War (pure malice). And a character can accrue maximum Weight of War without falling (Obi-Wan's arc — war-weary but still light). The two systems are independent and measure different things.
- **It is not a morality meter.** The game does not judge Weight of War. Director AI surfaces it narratively; it does not announce "you are 47% corrupted."
- **It is not exposed as a raw number to players at launch.** Players see narrative descriptors (per §6), not a numeric score. The number exists internally in the database for Director AI prompts and mechanical effects.

---

## 4. Accrual Triggers

Weight of War accrues from actions that model the wear of sustained command and battlefield presence. Triggers are categorized by scale.

### 4.1 Minor Triggers (+1-3 Weight)

- Completing a military mission with clone trooper deaths under your command (+1 per 5 clones lost, cap +5 per mission)
- Spending 7+ in-game days continuously in a combat zone without a Temple return (+2 weekly)
- Authorizing an attack-first action (the Code says defense, not attack; the attack-first choice logs per `engine/combat.py` initiation flag) (+1 per instance)
- Witnessing a civilian casualty in your zone of responsibility (+2 per event)
- Failing to save a clone trooper you had a personal bond with (Director AI tracks named clone NPCs; death of a named bonded clone = +3)

### 4.2 Moderate Triggers (+5-10 Weight)

- Completing a battlefield victory with pyrrhic cost (>50% clone casualties under your command) (+5 per instance)
- A Padawan under your command (whether bonded Padawan or situational command) is killed or falls (+10 per instance)
- Issuing an order that results in a civilian population being exposed to harm for strategic reasons (+8 per instance; requires player acknowledgment — this is a meaningful choice)
- Killing an enemy combatant who was surrendering (this is also +1 DSP per standard rules; the Weight of War penalty is additive — +5 Weight here is *in addition to* the DSP) (+5 per instance)

### 4.3 Major Triggers (+15-25 Weight)

- Ordering clone troopers to execute prisoners (+20; also +2 DSP)
- A mission that results in mass civilian casualties, even if unintended (+15 per 100 civilians)
- Abandoning a combat position in a way that results in ally deaths (+15 per instance)
- Extended torture or coercive interrogation of an enemy (+25; also +3 DSP — this is Sith-philosophy territory)

### 4.4 Accrual Caps

- No single event can accrue more than +25 Weight.
- Weekly accrual cap: +40 Weight per in-game week. Beyond this cap, additional triggers are narratively acknowledged by Director AI but do not add to the numeric score. This prevents spiraling accrual from a single bad session.
- Hard cap: 200 Weight total. A character at 200 is at the maximum modeled strain — the narrative is fully bleak. Further triggers do not add to the score.

---

## 5. Decay Triggers

Weight of War decays during periods of peace, meditation, and reconnection with the Jedi Order.

### 5.1 Passive Decay

- -1 Weight per in-game day spent entirely at the Jedi Temple on Coruscant (no active missions)
- -2 Weight per in-game day spent in a peaceful zone with no combat events (e.g., Naboo, pacifist worlds)
- -0 Weight during active military campaigns (decay pauses; the strain is current)

### 5.2 Active Decay (Player-Initiated)

- `+meditate` command at Temple: Spend 1 Force Point, gain -5 Weight (once per in-game day)
- `+counsel` with bonded Master (for Padawans) or with a Council member (for Knights/Masters): Director AI-narrated counseling scene, -10 Weight on completion (once per in-game week; limited by Master/Council NPC availability)
- Completing a non-combat mission (diplomatic, archival, rescue, agricultural relief): -5 Weight on completion (reinforces that Jedi have other duties)
- Extended leave of absence: declared via `+retreat`, character becomes unavailable for combat missions for 7+ in-game days, gain -2 Weight per day of retreat (with a cap of -30 per retreat)

### 5.3 Decay During Peace Arcs

If the game's meta-narrative shifts into a peace interval (e.g., brief armistice storyline, post-war setting), decay rates multiply: passive decay doubles, active decay halves in Force Point cost. This is a lever for staff to use if the campaign arc calls for healing periods.

---

## 6. Narrative Surfacing (Player-Facing)

Players do not see "Weight of War: 47" in their sheet at launch. They see narrative descriptors that Director AI injects into Force-connection status, dream sequences, and NPC dialogue.

| Weight Range | Narrative Descriptor | Player-Visible Signal |
|---|---|---|
| 0-20 | At peace | "You feel the Force flowing freely around you." |
| 21-50 | Troubled | "The Force feels clouded. Small noises startle you. You sleep poorly." |
| 51-100 | Burdened | "You hesitate before drawing your saber. Every clone's face becomes familiar, and you cannot remember all their names." |
| 101-150 | Strained | "The voices in the Force grow dim. Meditation no longer calms you. You dream of fire and dying men you could not save." |
| 151-200 | Crushed | "The Force feels distant, withheld. You feel hollow. The Code is words you recite, not truths you feel. You understand, now, why Masters have fallen." |

Implementation: the `look self` command includes one of these descriptors in the Jedi's Force-connection section when Weight of War is >20. The Director AI uses the same descriptors to flavor NPC dialogue and dream events.

---

## 7. Mechanical Effects

Weight of War does not directly penalize skill rolls. It operates through four indirect channels:

### 7.1 DSP Resistance Erosion

At high Weight of War, the character is more susceptible to the "moment of weakness" mechanic (standard WEG): when tempted to act in anger, fear, or expedience, they roll willpower vs. a difficulty modified by Weight of War.

- Weight 0-50: standard willpower roll, no modifier
- Weight 51-100: +2 to willpower difficulty when resisting a dark-side temptation
- Weight 101-150: +5 to willpower difficulty
- Weight 151-200: +10 to willpower difficulty; additionally, a failed willpower roll grants 1 extra DSP beyond the baseline DSP award

This is the core mechanical bite: a war-weary Jedi finds it genuinely harder to hold the line in a critical moment. This is the Anakin-Mustafar mechanic in miniature, applied continuously.

### 7.2 Force Point Replenishment

Standard WEG awards Force Points for heroic acts aligned with the light side. Weight of War reduces the rate:

- Weight 0-50: normal FP award
- Weight 51-100: 75% FP award (round down, minimum 1)
- Weight 101-150: 50% FP award
- Weight 151-200: 25% FP award

Implementation: post-combat FP award logic in `engine/character.py` checks Weight of War before committing the award. The war-weary Jedi saves the village but feels less restored by it.

### 7.3 Force Vision Tone

Director AI-generated Force visions (dreams, meditations, Force-bond transmissions) shift in tone by Weight tier:

- Low Weight: hopeful, instructive, clear
- Moderate Weight: ambiguous, fragmented, troubling but interpretable
- High Weight: fragmented, dark, contradictory, often frightening; visions may hint at dark-side futures

This is narrative only, no mechanical impact beyond the RP fuel.

### 7.4 Bonded Partner Awareness

A bonded Master/Padawan can sense their partner's Weight of War state through the `+forcebond` command (per `padawan_master_system_design_v1.md` §5.1). This creates gameplay opportunities for mutual support: a Master can notice their Padawan is struggling and initiate `+counsel`; a Padawan can see their Master fraying and offer support (reversing the normal direction of mentorship, which is itself a Clone Wars-era theme).

---

## 8. Database Schema

```sql
ALTER TABLE characters ADD COLUMN weight_of_war INTEGER NOT NULL DEFAULT 0;
ALTER TABLE characters ADD COLUMN weight_last_decay_at TIMESTAMP;
ALTER TABLE characters ADD COLUMN weight_last_accrual_at TIMESTAMP;

CREATE TABLE weight_of_war_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id INTEGER NOT NULL,
    event_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delta INTEGER NOT NULL,  -- signed: positive for accrual, negative for decay
    trigger_type TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY (char_id) REFERENCES characters(char_id)
);

CREATE INDEX idx_wow_char ON weight_of_war_events(char_id, event_at DESC);
```

The event log is verbose but essential. It lets Director AI prompts reference specific recent events ("the Massacre at Ryloth still haunts you") and lets staff audit accrual/decay if a player disputes the state. The log also enables a post-launch `+history weight` command that shows the player a prose summary of their arc.

**Migration:** Additive. Apply via boot-time migration. Default `weight_of_war = 0` for all existing characters (including pre-launch Jedi testers).

---

## 9. Director AI Integration

The Director AI system (per `director_ai_design_v1.md`) is extended to accept a Weight of War input for Jedi PCs. The integration points:

- **Every NPC dialogue prompt** for a Jedi PC includes the character's current Weight tier as a prompt variable. The AI weaves appropriate acknowledgment — concerned glances from Council members at high Weight, reassurance and warmth at low Weight.
- **Dream/vision generation** uses Weight tier to select the emotional palette of the generated content.
- **Mission briefings** for Jedi PCs with high Weight include an optional "rest" variant — the briefing NPC (often a Master) suggests the PC might take a Temple retreat before accepting another combat mission. This is a soft signal, not a block.
- **Post-mission reflection prompts** (the Director AI's end-of-mission narrative summaries) foreground Weight-relevant events: at high Weight, the summary emphasizes costs; at low Weight, it emphasizes successes.

Prompt-engineering specifics are deferred to implementation. This is work for beta iteration against the tester cohort — initial prompts will be rough, refined based on what actually lands.

---

## 10. Commands Summary

New commands introduced by this system:

| Command | Who Uses It | Purpose |
|---|---|---|
| `+meditate` | Jedi PC at Temple | Spend 1 FP, -5 Weight (1x per day) |
| `+counsel` | Padawan (with Master) or Knight/Master (with Council) | Initiate counseling scene, -10 Weight on completion (1x per week) |
| `+retreat` | Jedi PC | Declare extended leave; combat unavailable; -2 Weight/day |
| `look self` (extended) | Jedi PC | Displays Weight narrative descriptor (per §6) |

Post-launch (Drop 3+):
- `+history weight` — shows player's accrual/decay event log as prose
- Admin command to manually adjust Weight (for staff story purposes)

---

## 11. MVP Scope for Launch

**Everything in §4 (accrual), §5 (decay), §6 (narrative surfacing), §8 (schema), and §10 MVP commands must work at launch.**

**Deferred to post-launch:**

- Full Director AI narrative-tone integration (§9). At launch, basic Weight-tier descriptors in `look self` and minimal NPC dialogue variation. Deep integration in Drop 3+ once tester feedback informs what narrative beats land.
- `+history weight` command (Drop 3+).
- Mission-type-specific accrual triggers (§4 distinguishes between mission outcomes; at launch, accrual is simpler — fixed triggers, not outcome-dependent).
- Peace-arc decay multipliers (§5.3) — meta-narrative feature, post-launch.

MVP delivers the mechanical substrate and the first-pass narrative surfacing. Director AI depth comes through beta iteration.

---

## 12. Interaction with Other Systems

### 12.1 DSP

Weight of War and DSP are independent but correlated. High Weight makes DSP accrual easier (per §7.1). However, a character can have high DSP and low Weight (the Sith-trajectory character who embraces darkness without war context) or high Weight and low DSP (the war-weary Jedi who holds the line despite cost).

### 12.2 Padawan-Master Bond

See `padawan_master_system_design_v1.md` §5.1 — bonded partners can sense Weight through `+forcebond`. A fallen or fallen-risk Padawan (per `padawan_master_system_design_v1.md` §7) will often have high Weight as a contributing factor.

### 12.3 Force Powers

The new Force powers from `jas_extraction_v1.md` §3 integrate cleanly — no special Weight interactions. However, use of Sith powers (§4 of that extraction) should trigger a +10 Weight event in addition to their DSP penalty. The war-weary Jedi who experiments with "just this once" takes cumulative damage.

### 12.4 Economy

No direct interaction. Weight of War is a Force-connection metric, not an economic one. Jedi PCs do not earn or lose credits based on Weight.

### 12.5 Faction / Reputation

No direct interaction at launch. Post-launch, a Jedi PC with sustained very-high Weight might trigger Council intervention (reputation effect with Jedi faction), but this is a Drop 3+ refinement.

---

## 13. Open Questions for Brian

1. **Per-tier FP award reduction (§7.2) — too harsh?** Reducing FP restoration by 75% at max Weight might make high-Weight characters feel punished rather than strained. Alternative: no reduction to FP, but introduce a FP expenditure tax (high-Weight Jedi spends 2 FP for effects that normally cost 1). Brian-decision; feel it out in beta.

2. **Accrual from bonded clone deaths (§4.1).** The "named clone NPC with bonded relationship" feature requires Director AI work to track and surface named clones. Worth the complexity? Alternative: generic "clone deaths under command" trigger, no named-bond mechanic. Recommend: launch with generic; add named clones in Drop 3 if it emerges as desired.

3. **Player visibility of raw Weight number.** At launch, narrative descriptors only (§6). Should there be an "I want to see the number" staff-unlockable option? Could be useful for testers during beta. Recommend: staff-unlockable via `+debug weight` command for beta; public-launch defaults to narrative-only.

4. **Does Weight of War apply to Force-sensitive non-Jedi PCs?** Some PC concepts might include Force-sensitive but untrained characters (fringe RP). Recommend: no. Weight of War is specifically a Jedi-Order framing. Non-Jedi Force-sensitives have a different relationship to these events.

5. **Retroactive application to beta characters.** If a tester-Master has been running combat missions during beta, do those mission events accrue Weight when the system ships? Recommend: no. Start all characters at 0 on system launch, grandfather in beta activity. This avoids "I didn't know my actions were being counted" grievance.

---

## 14. Acceptance Criteria

The Weight of War MVP is considered complete at launch when:

- Accrual triggers fire correctly in response to mission outcomes, combat events, and specific commanded actions (§4)
- Passive and active decay function (§5)
- `+meditate`, `+counsel`, `+retreat` commands are implemented and tested (§10)
- `look self` displays the appropriate narrative descriptor for the character's current Weight tier (§6)
- DSP willpower-difficulty modifier applies at the correct Weight tier (§7.1)
- FP award reduction applies correctly (§7.2)
- Database schema is migrated and the event log records all changes (§8)
- Staff can manually adjust Weight for narrative purposes (admin command)
- Bonded partners can sense each other's Weight state via `+forcebond` (§7.4)

Director AI deep integration (§9), `+history weight` command, and post-launch refinements are out-of-scope for launch MVP.

---

*End of Weight of War Design v1.0 — April 18, 2026.*
*Paired with: launch_strategy_v1.md (anchor), clone_wars_era_design_v4.md (world context), padawan_master_system_design_v1.md (bond integration), jas_extraction_v1.md (Jedi pedagogy and Sith contrast), director_ai_design_v1.md (narrative integration).*
*Ready to drive Drop 2 / Drop 3 implementation.*
