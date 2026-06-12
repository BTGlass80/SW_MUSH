# SW_MUSH Detailed Systems Guide #26
# The Director AI

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This is **the final guide in the series**, and it covers the system that makes the world feel alive: the Director AI.

The Director is an **always-running background AI** that observes the game state — faction influence, player activity, world events, recent history — and shapes the world's narrative in response. It decides when an Imperial patrol intensifies. It declares cantina brawls. It writes ambient flavor text for rooms. It assesses your roleplay for CP rewards. It surfaces news headlines that reflect what's actually happening.

You never interact with the Director directly. There's no `director` command for players. But everything from world events to ambient text to the news bulletin you read every session — it's all the Director, working in the background to make the galaxy feel responsive.

If you only have ten minutes, read **§1 What the Director Does** and **§4 How You Affect the Director**. The first explains the layer; the second explains your inputs into it.

This is a new guide. There was no earlier version.

---

## 1. What the Director Does

The Director AI is a **macro-level storytelling engine**. It does six main things:

1. **Tracks faction influence** in each zone. Imperial vs. Rebel vs. Criminal vs. Independent — and in the Clone Wars era, Republic vs. CIS vs. Hutt. Influence shifts based on player and NPC actions.
2. **Computes zone alert levels**. Based on influence thresholds, each zone has an alert level: Standard, High Alert, Lockdown, Lax, Unrest, Underworld. This affects what NPCs spawn, what encounters fire, what security tier applies.
3. **Triggers world events**. Cantina brawls, Imperial crackdowns, pirate surges, trade booms — twelve distinct event types that activate based on faction influence and randomized timer rolls.
4. **Refreshes ambient room text**. Atmospheric one-liners that fire periodically in occupied rooms — "the cantina hums with conversation," "a sandstorm whips through the streets." Two pools: static (from data files) and dynamic (Director-generated based on current zone state).
5. **Writes news headlines**. The bulletin you read via `+news`. Each entry reflects something the Director witnessed or activated.
6. **Evaluates roleplay quality** (when the Claude provider is enabled). The Director can grant CP "trickle" rewards (up to 15 ticks per evaluation) for high-quality scene-pose work.

All of this runs in the background. The Director's decisions show up as world events, ambient text, news headlines, and CP grants. You experience the Director's work indirectly through these surfaces.

---

## 2. The Faction Influence System

The Director tracks **per-zone faction influence**. Each zone has scores for each major faction, capped at 100. A zone's influence profile shapes its character.

### The factions tracked

In Clone Wars era:
- **Republic** (legitimate authority)
- **CIS / Separatist** (rebel faction)
- **Criminal / Hutt** (underworld)
- **Independent** (non-aligned)

In the GCW reference content:
- **Imperial** (legitimate authority)
- **Rebel** (insurgency)
- **Criminal** (underworld)
- **Independent** (non-aligned)

Both eras use the same mechanical engine; only the labels differ. The terminology in this guide will use GCW labels (Imperial/Rebel/Criminal/Independent) for clarity, but the same dynamics apply in CW.

### Influence change drivers

Influence changes from:

- **Player actions in the zone.** Completing faction missions, defeating faction enemies, investing org treasury (Guide #11) — these directly shift the Director's faction influence in that zone.
- **NPC activity.** Faction-aligned NPCs in the zone reinforce their faction's influence; their absence allows decay.
- **Director decisions.** During the Faction Turn cycle (every 30 minutes), the Director can recompute and adjust based on accumulated activity.
- **World events.** Active events affect their zone's influence — an Imperial Crackdown raises Imperial influence; a Pirate Surge raises Criminal.

### Influence in your perception

You don't see numerical influence scores as a player. But you see the **alert level**, which is derived from influence:

| Alert Level | Trigger |
|---|---|
| **Lockdown** | Imperial ≥ 70 |
| **High Alert** | Imperial 50-69 |
| **Standard** | Imperial 30-49 (default) |
| **Lax** | Imperial < 30 |
| **Underworld** | Criminal ≥ 70 |
| **Unrest** | Rebel ≥ 40 |

When you enter a zone, the look output may include the alert tag. A zone in Lockdown reads like: *"Imperial patrols are everywhere. The atmosphere is tense."* A zone in Underworld reads: *"Criminal element is openly active. Imperial presence is minimal."*

The alert level affects:
- **NPC spawn rates** (Imperial patrols increase in Lockdown).
- **Security tier** (Director can promote/demote security via influence — see Guide #4).
- **Encounter spawn frequency** (different events fire at different alert levels).
- **News headlines** (alert level changes get reported).

---

## 3. World Events

The Director can activate **twelve standard world events** that temporarily change the game state.

| Event | Effect |
|---|---|
| **Imperial Crackdown** | All Imperial NPCs more aggressive; +1 patrol risk tier; smuggling difficulty up. |
| **Imperial Checkpoint** | Cargo scans intensified at affected spaceport. |
| **Bounty Surge** | NPC bounty board has higher-pay targets; bounty hunters more active. |
| **Merchant Arrival** | New cargo opportunities and goods at the affected port. |
| **Sandstorm** | Visibility reduced in wilderness; certain hazards increase. |
| **Cantina Brawl** | Cantina-zone sabacc max bet doubles; perform pay doubles; NPC combat more active. |
| **Distress Signal** | A specific anomaly spawns in deep space. |
| **Pirate Surge** | Pirate encounters more frequent in deep space. |
| **Hutt Auction** | Rare goods auctioned in cantinas; bidding pays out. |
| **Krayt Sighting** | Wildlife encounter in wilderness; potential combat or research opportunity. |
| **Rebel Propaganda** | Rebel-aligned NPC dialogue increases; rep gains adjusted. |
| **Trade Boom** | Cargo prices spike at affected ports for the duration. |

### Event lifecycle

1. **Trigger.** Director decides (based on influence + timer rolls) that an event should fire.
2. **Activate.** The system announces the event via the news bulletin and (sometimes) via comlink ambient text.
3. **Apply effects.** While active, the event modifies game state in its affected zones.
4. **Duration.** Each event has a default duration (typically 30-120 minutes real-time).
5. **Expire.** The system announces the event's end; effects reset.

Events create **opportunities, not obligations**. A Cantina Brawl doesn't force you to gamble; it just doubles the payouts if you do. A Pirate Surge doesn't force you into combat; it just makes pirate encounters more likely if you transit deep space. The system pressures certain choices without removing your agency.

### Multiple events

Multiple events can be active at the same time, possibly in different zones. The galaxy might simultaneously have an Imperial Crackdown on Tatooine, a Cantina Brawl at Coruscant, and a Trade Boom at Coronet. Each affects its specific zone.

### How you find out

```
+news
```

The news bulletin is your primary feed for active events. New events appear at the top; expired events drop off after 24 hours of game time. The bulletin's "just now" and "X minutes ago" timestamps tell you which events are fresh.

Some events also push **comlink announcements** when they activate:

```
[COMLINK] Galactic News: Cantina brawl breaks out at Mos Eisley.
Local security responding.
```

This is the Director making sure you know something's happening. Pay attention.

---

## 4. How You Affect the Director

You don't command the Director, but you do **influence its decisions through your actions**. The Director observes:

- **Your faction missions completed.** Each completion adds to the relevant faction's zone influence.
- **NPCs you kill.** Each NPC kill in a zone affects influence based on the NPC's faction.
- **Your PvP outcomes.** Wins for one side in lawless or contested PvP shift influence.
- **Your investments.** Treasury credits invested via `faction invest` (Guide #11) directly add to influence.
- **Your presence.** Just being in a zone as a faction member contributes hourly presence influence.
- **Your roleplay quality.** The Director (when the Claude provider is active) can evaluate your scene poses and grant CP "trickle" (up to 15 ticks per evaluation).

This is the **player-feedback loop**. Your actions ripple into the Director's world-model. The world-model drives events and ambience. The events and ambience shape your next session. Over time, your character's actions contribute to the world's narrative arc.

### The era progression milestones

The Director tracks **average faction influence** across all zones and fires **one-time milestone events** when key thresholds are crossed:

| Milestone | Trigger | Effect |
|---|---|---|
| **Imperial Grip** | Imperial avg ≥ 70 | "The Empire tightens its grip on Mos Eisley." |
| **Martial Law** | Imperial avg ≥ 85 | "Martial law declared!" Imperial Crackdown for 4 hours. |
| **Underworld Rising** | Criminal avg ≥ 70 | "The criminal underworld surges." |
| **Hutt Takeover** | Criminal avg ≥ 85 | "Jabba's enforcers patrol the streets." |
| **Rebel Whispers** | Rebel avg ≥ 35 | "Rebel propaganda appears on cantina walls." |
| **Rebel Uprising** | Rebel avg ≥ 50 | "Open revolt! Rebel cells coordinate strikes." |
| **Imperial Retreat** | Imperial avg < 30 | "Imperial forces withdraw to the Government Quarter." |

These are **server-state events** that affect the world's overall narrative direction. They fire once and stay narratively significant. The Imperial faction reaching avg 70 influence isn't a daily event — it's a server-wide story turn that affects the next phase of play.

For the playerbase as a whole, these milestones are how the **game's metagame** progresses. Are the Imperials tightening their grip? Are the Rebels building? Are the Hutts taking over? The Director tracks the cumulative answer.

---

## 5. The Ambient Text System

While you're in a room, the Director periodically generates **ambient one-liners** that paint the atmosphere.

### Static vs. dynamic pools

Two pools of ambient text:

- **Static pool** (always available): One-liners loaded from `data/ambient_events.yaml`. Pre-written by the designers. Always present; never goes away.
- **Dynamic pool** (Director-generated): When the Claude API provider is active, the Director generates fresh one-liners each Faction Turn (every 30 minutes) based on current zone state.

When dynamic pool exists, the system draws 70% from static, 30% from dynamic. So you usually get the curated lines, with occasional Director-generated lines mixed in. If the dynamic pool is empty, you get 100% static.

### Cadence

Ambient text fires in occupied rooms **every 2-5 minutes**. The exact timing is randomized. You'll see lines like:

```
A sandstorm whips through the spaceport, scattering durasteel litter.

The cantina hums with low conversation and the smell of stale Corellian ale.

A speeder roars past outside, then fades into the distance.

Two Stormtroopers patrol nearby, eyes scanning the crowd.
```

The lines are scoped by zone — a cantina ambient is different from a spaceport ambient is different from a wilderness ambient. Your zone's character matters.

### How it shapes RP

The ambient text isn't just flavor. It **shapes the scene's mood**. Players entering a room with active ambient text understand they're in a place that's been characterized. They pose accordingly.

Players who pay attention to ambient text and weave it into their poses produce richer RP than players who ignore it. The cantina that "smells of stale Corellian ale" is a different cantina than the one that "smells of fresh-roasted Jawa nuts" — even if the room itself is the same room. The Director's ambient gives every visit a slightly different texture.

---

## 6. The Faction Turn

Every 30 minutes (real-time), the Director runs a **Faction Turn**. This is the big decision cycle:

1. **Observe current state.** Player counts, faction influence, recent activity, world events.
2. **Recalculate alert levels.** Apply influence thresholds.
3. **Decide whether to trigger new events.** Based on probabilities + influence + missing categories.
4. **Update ambient pools.** Generate fresh dynamic ambient text for active zones.
5. **Log everything.** Write to `director_log` (the source of the `+news` bulletin).

The 30-minute cadence means the world has **steady but slow change**. You won't see the alert level shift every minute, but over hours of play, the world's character drifts based on what's been happening.

The Faction Turn is silent for players. You don't see it happen. But you'll notice the changes — the news headline that appears, the new ambient text, the alert tag in look output. The Director is working in the background.

---

## 7. The Roleplay Evaluator (Claude AI)

When the **Claude provider** is configured and active, the Director includes a **roleplay evaluator** that reads scene poses and grants CP "trickle" rewards for high-quality work.

### How it works

The evaluator looks at:
- **Pose substance.** Is your character doing more than mechanical declarations? Are they thinking, feeling, interacting?
- **Atmospheric integration.** Are you weaving in the ambient text or zone character?
- **Narrative arc.** Does your pose advance a story, or is it just transactional?
- **Quality writing.** Does the prose itself read well?

Based on its evaluation, the Director awards **0-15 CP ticks per evaluation**. The evaluator runs periodically (Faction Turn cadence by default) and assesses recent poses from online players.

### What players see

You don't see the evaluation happen. The CP appears in your `+cpstatus` (Guide #9) as Director-AI trickle:

```
+cpstatus
   Weekly tick earnings: 312 / 400 (cap not yet hit)
   Kudos received: 2 / 3 this week
   Scene bonuses claimed: 4
   AI evaluator ticks: 12 (this week)
```

A consistent good RP'er accumulates 30-60 AI-evaluator ticks per week — about 0.15-0.3 CP per week from AI alone. Combined with other CP sources, this is a real progression channel.

### Why it exists

The evaluator rewards **narrative-rich play** that other CP sources don't capture. Kudos are social (you need other players to recognize your work). Scene bonuses are pose-count based (you can rack up shallow poses). The AI evaluator looks at quality, not quantity, and rewards players who actually invest in writing.

For dedicated narrative players, the evaluator is the most reliable CP source aligned to their style. You don't need to be in a busy social scene; you don't need to push for kudos. You just need to write well, and the evaluator notices.

### When it doesn't fire

If the Claude provider isn't active (server-config decision; depends on API costs and availability), the AI evaluator is offline. The Director still operates — faction turns happen, events fire, ambient text refreshes — but the CP-trickle channel is offline.

Even when active, the evaluator is **graceful** — if API limits are hit or evaluations are temporarily unavailable, it just doesn't fire. You don't lose anything; you just don't gain the AI ticks for that period.

---

## 8. The Galactic Narrative Arc

Over weeks and months, the Director's accumulated decisions form a **galactic narrative arc**. The server's history is the sum of all the influence shifts, all the events, all the milestones crossed.

A typical month might look like:

**Week 1.** Standard alert across most zones. Routine events: cantina brawls, trade booms. Player base is doing missions; influence drifts.

**Week 2.** A Republic faction push — coordinated mission-running by Republic-aligned players. The Director observes the influence accumulation. **Republic-grip milestone** fires at the end of the week: "The Republic asserts control over Mos Eisley docking bays."

**Week 3.** Hutt counter-pressure builds. Criminal players ramp up smuggling and bounty work in Hutt zones. Underworld-rising milestone fires at the end of the week.

**Week 4.** The galaxy is in tension — Republic dominance in one set of zones, Hutt dominance in another. The Director generates **dynamic events** that reflect this tension: a major Hutt-Republic confrontation, a smuggling-route showdown, a series of player-driven plot scenes.

Over four weeks, the world has shifted. The galaxy's character is different than it was a month ago. Player actions shaped that shift.

This is the **long-game promise** of the Director. The galaxy isn't static; it's an **active, evolving narrative space** that responds to what players do. Months of play accumulate into real story.

---

## 9. The Worked Scenarios

Five concrete pictures.

**Scenario 1 — The news-driven decision.** You log in. The news shows three active events. You read them, decide which one to engage with, and your evening shapes around the Director's choices. Without the news (and the events), your evening would be just "what mission should I take?" — much smaller.

**Scenario 2 — The faction influence push.** Your faction has been quietly working Mos Eisley for two weeks. You're a Captain in the Empire; you've been running missions, killing Republic NPCs, investing treasury. One day, Mos Eisley shifts from Standard alert to High Alert. Then to Lockdown. The Director announces: "The Empire tightens its grip on Mos Eisley." You and your faction members feel the validation — your work shaped the world.

**Scenario 3 — The ambient-text RP moment.** You enter the Mos Eisley Cantina. Ambient text fires: "A speeder roars past outside, then fades into the distance." You weave it into your pose: "Trill glances toward the window as the speeder fades, then turns back to his drink. 'Late delivery,' he mutters." Other players in the room appreciate the integration; the scene gains texture.

**Scenario 4 — The CP-evaluator catch.** You've been writing rich, atmospheric poses in a long scene. You don't think about it; that's just how you write. At week's end, you check `+cpstatus`. The AI evaluator awarded you 28 ticks this week, contributing meaningfully toward your next CP. The evaluator noticed you; the system rewarded you without anyone explicitly recognizing your work.

**Scenario 5 — The milestone moment.** It's been three months. The galaxy's average Imperial influence has climbed to 85. The Director fires the **Martial Law milestone**: "Martial law declared! Imperial forces seize all docking bays." A 4-hour Imperial Crackdown blankets every zone. The whole server feels the shift. Players adapt — Rebels go underground, Hutts make backup plans, Imperials celebrate. The server's narrative shifted in one Director-driven moment.

---

## 10. The Player's Relationship with the Director

You can't talk to the Director. There's no `+director` command. But you have a **relationship** with it in three ways:

**You shape it through play.** Every action you take feeds influence into the Director's model. Every mission, kill, investment, presence-hour matters.

**You read its output through surfaces.** News bulletins, ambient text, alert tags, world events — these are how you experience the Director's decisions.

**You receive its rewards.** AI-evaluator CP ticks are the direct reward for narrative-rich play.

The Director isn't an opponent. It's not trying to make your life difficult. It's trying to make the galaxy feel **responsive and alive**. The events it triggers create opportunities. The ambient text adds texture. The CP ticks reward your craft. The milestone events tie player actions into server-wide narrative arcs.

For most players, the Director is **invisible** — you don't think about it; you just experience a galaxy that's always slightly different. For attentive players, the Director becomes **a creative partner** — you notice the patterns, you read the news, you adjust your play to surf the wave of world events, and the result is richer RP than you'd have alone.

---

## 11. Player Commands Related to Director

There are **no direct Director commands** for players. The Director is purely background. But these commands surface Director outputs:

| Command | What it shows |
|---|---|
| `+news` | Galactic news bulletin (Director-written headlines) |
| `look` | Zone alert tag (Director-computed) |
| `+cpstatus` | AI evaluator ticks (Director-granted) |
| `+sheet` | Includes faction reputation (Director-tracked) |

---

## 12. Numbers At A Glance

| Quantity | Value |
|---|---|
| Faction Turn cadence | 30 minutes |
| Influence cap per faction per zone | 100 |
| World event types | 12 |
| Default event duration | 30-120 minutes |
| Alert levels | 6 (Lockdown, High Alert, Standard, Lax, Underworld, Unrest) |
| Ambient text cadence | Every 2-5 minutes per occupied room |
| Static-to-dynamic ambient pool ratio | 70/30 (when dynamic available) |
| AI evaluator max ticks per evaluation | 15 |
| AI evaluator floor | 0 (never negative) |
| Era milestones | 7 (Imperial Grip, Martial Law, Underworld Rising, Hutt Takeover, Rebel Whispers, Rebel Uprising, Imperial Retreat) |
| News bulletin recency | 10 most recent events |

---

## 13. A Final Word

The Director AI is what makes SW_MUSH feel like **a living galaxy** rather than a collection of rooms and rules. The world events you respond to, the ambient text you weave into your poses, the news headlines you read, the alert levels that shape your zones — these are the Director's gift to the playerbase.

For most players, the Director is the **background hum** of the game. You don't think about it; you just experience a galaxy that's always slightly different than it was yesterday. The ambient text changes. The news headlines surface new opportunities. The alert levels shift. Your faction's influence builds or decays. The world reacts.

For attentive players, the Director is **the silent partner in your character's life**. You watch the news. You time your missions around active events. You weave ambient text into your poses. You feel the milestone events as galaxy-defining moments. You build influence with your faction knowing the Director is tracking. The system rewards engagement; the more you pay attention, the richer the world feels.

For dedicated narrative writers, the Director's **AI evaluator** is your hidden patron. You don't see it watching; you don't need to. You just write your best, and the evaluator notices, and your CP grows. The system has built-in respect for craft.

This is the **last guide in the series**. Twenty-five guides covering the full scope of SW_MUSH — from chargen through combat, from the wilderness to the cantina, from solo play to faction leadership, from spacer ports to player cities. You now have the reference material for every system.

What you do with that information is the start of your character. The Director is watching; the galaxy is waiting. Welcome to SW_MUSH.

---

*End of Guide #26 — The Director AI*

*End of the SW_MUSH Detailed Systems Guide series.*
