---
category: community
order: 4
summary: "The Director AI runs ambient events, NPC behavior, and emergent storylines across the galaxy."
tags: ["director", "ai", "npc", "events", "ambient", "story", "emergent"]
---

# The Director AI

**SW_MUSH — Star Wars D6 Revised & Expanded**

---

## How to Read This Guide

The Director AI is the invisible hand that keeps the galaxy moving when no Game Master is online. It runs ambient text, generates missions, escalates faction conflicts based on player actions, narrates news, promotes characters, approves requisitions, applies discipline, and pushes the broader narrative arc of the Clone Wars forward over weeks and months of play.

Most players never need to think about the Director directly — they experience its work as ambient flavor and emergent consequences. But understanding the system helps you read what's happening, anticipate how the world will respond to your actions, and recognize when an opportunity is being put in front of you that you should grab.

If you only have ten minutes, read **§1 What the Director Does** and **§4 How You Affect the Director**. That's enough to understand the feedback loop between your actions and the world's response. The rest covers the underlying systems: faction influence, world events, ambient narration, faction turns, the Roleplay Evaluator, and the bigger-picture narrative arc.

This guide assumes familiarity with the [Organizations & Factions](#/guide/organizations-factions) and [Security Zones](#/guide/security-zones) systems, both of which the Director acts on.

---

## 1. What the Director Does

The Director AI is a Claude-backed orchestration layer that runs in the background of the game. Its responsibilities, in rough order of how often a player encounters them:

**Ambient narration.** Every few minutes, the Director emits room-flavor text appropriate to the zone you're in — a Republic patrol marching past on the Nar Shaddaa Promenade, a Hutt enforcer collecting from a market stall, distant blaster fire from the underworld, a HoloNet vendor crying the day's headlines. These don't require your input or response. They just make the world feel inhabited.

**Mission generation.** The mission boards you interact with are populated from a Director-managed pool. The Director picks missions appropriate to the zone, the active faction influence, and recent player activity. CIS infiltration arc landing on Coruscant? Republic Intelligence missions appear on the Coruscant board. Hutt unrest in the Nar Shaddaa Warrens? Hutt enforcement contracts appear in the Hutt mission pool.

**NPC behavior.** NPCs in combat use behavioral profiles (see [Ground Combat](#/guide/ground-combat) §11), but their broader behavior — whether they're hostile, friendly, watchful, or absent — is influenced by the Director's read of the zone's current state. A Republic patrol in a high-influence Republic zone is on routine watch; the same patrol in a contested zone is jumpy and hair-trigger.

**Faction administration.** For NPC-managed factions (currently Republic, CIS, Jedi Order, Hutt Cartel), the Director handles promotions, approves equipment requisitions, dispenses discipline for infractions, and posts faction-internal news. PC-led factions (currently only the Bounty Hunters' Guild operates this way) handle their own administration; the Director only intervenes if the faction goes inactive.

**World events.** The Director triggers narrative events that affect zones — crackdowns, surges, refugee waves, market booms. See §3.

**Long-arc storyline.** The Clone Wars are dragging on. The Director carries that arc forward week by week — Republic victories, CIS counter-offensives, Jedi losses, Sith stirrings — making the war feel like an actual ongoing event rather than a static backdrop.

The Director is **not** a Dungeon Master. It does not arbitrate disputes, does not invent plot for you, does not give players special treatment. It's a world simulator with narrative awareness.

---

## 2. The Faction Influence System

The Director tracks **per-zone faction influence** — a score from 0 to 100 for each faction in each zone. The influence profile shapes everything about how that zone behaves.

### The factions tracked

In zone influence scores, six factions are tracked:

- **Republic** — light-lean, primary order axis
- **CIS** — dark-lean, insurgent challenger
- **Jedi Order** — light, locked, Village-gated for PCs
- **Hutt Cartel** — neutral, criminal-coded
- **Bounty Hunters Guild (BHG)** — neutral, contract-coded
- **Independent** — default, unaligned

Two additional **NPC-only factions** are tracked for narrative purposes but don't appear in zone influence scores:

- **Sith** — the Dooku/Sidious axis, covert and atmospheric. Players never see Sith influence as a number; it surfaces as dark-side ambient events.
- **Separatist Council** — the CIS oligarchy. Narrated as a CIS overlay.

### Influence change drivers

Influence changes from:

- **Player actions in the zone.** Completing faction missions, defeating rival-faction NPCs, investing organization treasury (see [Territory Control](#/guide/territory-control)) — these directly shift the Director's faction influence in that zone. A Republic player completing Republic missions in Mos Eisley pushes Republic influence upward in Mos Eisley.
- **NPC activity.** Faction-aligned NPCs in the zone reinforce their faction's influence; their absence allows decay.
- **Director decisions.** During the Faction Turn cycle (every 30 game-minutes), the Director can recompute and adjust based on accumulated activity. Maximum delta per turn is 5 points — the Director won't catastrophically shift a zone overnight.
- **World events.** Active events affect their zone's influence — a Republic crackdown raises Republic influence; a pirate surge raises Hutt and Independent influence.

### Influence in your perception

You don't see numerical influence scores as a player. You see derived signals — the zone's **security level** changes, the **ambient narration tone** changes, the **NPC behavior** changes, the **mission pool** changes, the **HoloNet News** mentions the zone.

For example, in a zone where Republic influence has climbed from 40 to 75:

- The zone tag in `look` may upgrade — Contested becomes Secured under Republic influence above 75 (martial law).
- Clone patrol ambient narration becomes more frequent.
- Republic enforcement missions appear on the board ("Apprehend a known CIS sympathizer in Sector 4").
- The HoloNet may announce: "Republic Garrison reinforced at Mos Eisley spaceport."
- Hutt-affiliated NPCs become wary, less likely to openly proposition you for contraband.

In a zone where Hutt influence has climbed instead:

- The zone tag may downgrade — Contested becomes Lawless under Hutt dominance above 80.
- Hutt enforcer narration appears; clone patrols thin out or vanish.
- Hutt smuggling and enforcement missions appear; Republic missions become rare or absent.
- The HoloNet may announce: "Hutt Council issues neutrality reaffirmation following alleged enforcement actions in Outer Rim sectors."
- The black market becomes accessible to anyone with the right faction standing.

The world tells you what's happening. You don't have to dig.

---

## 3. World Events

The Director runs **world events** — narrative beats that affect zones for a bounded period. Twelve standard event types ship with the CW era:

| Event | Effect | Typical Duration |
|---|---|---|
| Republic crackdown | +Republic influence, secured-tier elevation, increased patrols | 1–3 days |
| Republic checkpoint | Customs scans intensify at affected spaceport | A few hours |
| Bounty surge | New high-value bounties posted to BHG board | 1–2 days |
| Merchant arrival | Special-stock vendor appears in a market zone | 12–24 hours |
| Sandstorm | Tatooine/desert zones: travel difficult, visibility reduced | 6–18 hours |
| Cantina brawl | Cantina zone: combat encounters spike briefly | 1–2 hours |
| Distress signal | A zone broadcasts a call for help; first responders rewarded | Until answered or expired |
| Pirate surge | +Hutt influence, lawless-tier downgrade in space lanes | 1–3 days |
| Hutt auction | Black market vendor appears in Hutt-aligned zone | 24 hours |
| Krayt sighting | Tatooine/wilderness zones: dangerous encounter posted | Until resolved |
| CIS propaganda | CIS sympathizer NPCs become more visible, recruitment opens | 1–2 days |
| Trade boom | A zone's market sees inflated prices and rare stock | 24–72 hours |

Events are **announced via HoloNet News** (see §5 below) and visible to all players. They are an invitation, not an obligation — a Hutt auction in Nar Shaddaa is just a thing happening; you can ignore it, attend, exploit it, or sabotage it, as your character disposes.

Events also have **prerequisites and cooldowns** to prevent monotony. A Republic crackdown can't trigger twice in the same zone within a week. A pirate surge requires Hutt influence to be above a threshold first. The Director respects pacing.

### Milestone events

A second category of event sits above the standard event pool: **milestone events** that mark major narrative beats in the broader Clone Wars arc. Five are currently authored:

- **Dark side stirring** — A Sith-narrated event that hints at off-stage dark-side activity. Atmospheric, not directly actionable.
- **Separatist offensive** — A major CIS push affecting multiple zones simultaneously.
- **Republic victory** — A Republic strategic win, often pulling clone resources away from one front to consolidate another.
- **Jedi lost** — A Jedi NPC killed in action. Affects Jedi Order morale and the Force-sensitive ambient flavor across multiple zones.
- **Hutt war profiteering** — A Hutt initiative to extract maximum profit from the war, often opening illicit opportunities for player smugglers.

Milestone events are rare — typically one every few real-world weeks of active play. They shape the long arc.

---

## 4. How You Affect the Director

The feedback loop between player action and Director response is the heart of the system. Every meaningful action you take feeds back, in some way, to the world's evolving state.

**Direct feedback:**

- **Mission completion** shifts faction influence in the mission's zone.
- **PvE combat** with faction-aligned NPCs shifts influence in the room where the fight happened.
- **Faction treasury donations** (see [Territory Control](#/guide/territory-control)) shift faction influence in the zone the org is anchored to.
- **Death and respawn** generate small ambient flavor events but don't shift influence.

**Indirect feedback:**

- **Sustained presence in a zone** is noticed — repeated visits, repeated combat, repeated faction work all read as the player choosing that zone as their base of operations. The Director may post more missions there to reward your interest.
- **Channel chatter** — what you say on faction comms is fed to the Roleplay Evaluator (see §7), which scores your activity for faction alignment and authenticity. High scores earn rep bonuses.
- **NPC interactions** that hit narratively significant beats — bargaining a Hutt enforcer down on contraband, persuading a Republic Intelligence officer to share information, defying a CIS Cell Leader's orders — are evaluated and can shift the Director's read of your character's trajectory.

**What the Director does NOT respond to:**

- Out-of-character chatter in OOC channels
- Mechanical commands that don't have a narrative footprint (looking at the map, checking your sheet, etc.)
- Idle time — sitting AFK doesn't decay your reputation (though long inactivity stretching to days does)

The Director is also **conservative about promotion**. It will not push you up faction ranks just because you've ground out reputation. It checks your behavior, your roleplay log, your engagement with the faction's narrative — and even then, it errs toward making you earn it. The handoff doc for the Director's training spells this out explicitly: "Promote conservatively. Players must EARN rank."

---

## 5. The HoloNet News Feed

The Director publishes news at semi-regular intervals through the **HoloNet News feed**, accessible via `+news` or visible on the web client's news panel. Headlines are generated from a pool of templated stories that the Director fills in with current world state.

Sample headlines you might see:

- "Republic forces report continued operations in the Outer Rim Sieges. The Chancellor's office expresses confidence."
- "Senate debate on supplemental war appropriations enters its third week. Loyalist and Reformist blocs trade procedural blows."
- "Kuat Drive Yards announces production milestone: hundredth Venator-class Star Destroyer commissioned this fiscal year."
- "Confederate forces claim victory at undisclosed Outer Rim location. Republic Command declines comment pending verification."
- "Refugee aid programs from Mid Rim worlds hit record allocations. Critics call them inadequate."
- "Bounty Hunters Guild posts unusual cluster of high-value contracts. Source identification withheld."
- "Jedi Master Tova Resh reportedly killed in action. Council statement pending."
- "Holonet weather report: Coruscant Senate District clear and calm. Most everywhere else: harder to say."
- "Trade Federation assets seized in three Mid Rim systems. The Federation calls the actions 'irregular.'"
- "Senator from Naboo introduces resolution reaffirming Chancellor's emergency powers. Vote anticipated to be near-unanimous."

Some headlines reflect **current Director state** — the named Jedi who was killed actually died in an event the Director ran; the production milestone reflects accumulated Republic influence on Kuat. Others are flavor — atmospheric reminders of the wider galaxy.

Reading the news before you act on a plan is **smart pacing**. If there's a Republic crackdown announced on Mos Eisley spaceport, maybe defer your contraband run. If there's a trade boom announced at Coronet, maybe push your cargo run forward.

---

## 6. The Faction Turn

Every **30 game-minutes**, the Director runs a Faction Turn cycle. During this cycle:

1. **Influence recompute.** Every zone's faction influence scores are recomputed based on accumulated activity since the last turn.
2. **Promotion review.** Eligible characters (those whose reputation crosses a rank threshold) are reviewed for promotion. The Director uses the conservative-promote rule; eligible doesn't mean automatic.
3. **Discipline review.** Recent infractions are reviewed and discipline applied (warn → probation → expel, never skipping steps).
4. **Equipment requisition review.** Pending equipment requests are approved or denied based on rank, recent activity, and whether the loss was the member's fault.
5. **World event tick.** Active events advance their timers; expired events resolve; new events may trigger if prerequisites are met.
6. **Mission pool refresh.** Mission boards are reseeded with faction-appropriate, zone-appropriate, current-world-state-appropriate missions.
7. **News emission.** New HoloNet headlines are published reflecting any of the above changes.

The cycle runs in the background — you don't see it happen, and it doesn't interrupt play. But its effects show up over the next few minutes of game time as the world adjusts.

---

## 7. The Roleplay Evaluator

The Director uses a separate Claude-backed component called the **Roleplay Evaluator** to score significant character actions for narrative authenticity. This is what catches the player who poses an emotionally rich confrontation versus the player who types `attack vex` and walks away.

The Evaluator looks at:

- **Pose quality.** Did you describe what happened in-character, or just type the mechanical command?
- **Faction alignment.** Did your behavior align with your faction's stated culture? (Republic soldiers don't generally extort civilians; Hutt enforcers don't generally turn down credit.)
- **Narrative consistency.** Did you respond to the situation as your character would, given everything established so far?
- **Engagement.** Did you carry the scene forward, or did you stall it?

High Evaluator scores earn **rep bonuses** — usually 1–3 extra reputation in your faction or guild, occasionally a small CP bonus. Low scores don't penalize you, but you miss the bonus.

The Evaluator runs on a sampling basis — not every action is evaluated, only ones the Director flags as narratively significant. You can't game it by posing constantly; you can only benefit from it by playing well at the moments that matter.

---

## 8. The Galactic Narrative Arc

The Director carries a long-running narrative arc that reflects the actual Clone Wars timeline. The arc has phases:

**Phase 1 — Mid-war (active default).** The current state. Both sides have committed; neither has the upper hand. The Republic has finally raised enough clone divisions to hold; the CIS has finally found enough strategic patience to attrit. Both sides are tired but neither knows how to stop. This is where new players arrive.

**Phase 2 — Late-war (future).** The Outer Rim Sieges intensify. Republic forces are stretched thin. CIS counter-offensives gain ground. Jedi losses accumulate. The Sith become more brazen in their off-stage maneuvering.

**Phase 3 — Endgame (future).** The events of Order 66. This phase requires explicit storyline triggering and is not currently active.

The arc is **gated by accumulated narrative weight** — Director-tracked metrics for things like total Jedi deaths, total Republic vs CIS zone victories, total HoloNet-reported milestones, etc. Phase transitions happen only when these metrics cross thresholds, and they're announced via HoloNet several days in advance to give players time to prepare.

The arc is also **partially player-driven**. Sustained CIS player success in the Outer Rim accelerates Phase 2's arrival. Sustained Republic success delays it. Player action shapes the war's pace within the canonical envelope.

---

## 9. Worked Scenarios

To make the abstractions concrete, here are three scenarios showing the Director at work.

**Scenario 1 — The mission pull.** You're a Republic Intelligence operative who's been working Mos Eisley for two weeks. Your reputation is climbing (now 47, just above Lieutenant threshold). The Director has tracked your activity and notices that Mos Eisley currently has elevated CIS influence (a CIS infiltrator NPC ran a successful arc two days ago, raising CIS in the zone from 12 to 28). Your next mission board check shows a new mission: "Identify the CIS contact in Chalmun's Cantina before they make their handoff. Reward: 600 cr, 6 rep." The mission appeared because *you* are in the zone, *you* are Republic Intelligence, and the *zone state* needs Republic counter-intelligence work. The Director put the mission in front of you specifically. Whether you take it is your call.

**Scenario 2 — The faction influence push.** Your faction has been quietly working Mos Eisley for two weeks. You're a Captain in the Republic; you've been running missions, killing CIS NPCs, investing treasury. One day, Mos Eisley shifts from Standard alert to High Alert. Then to Lockdown. The Director announces: "Republic Garrison reinforced at Mos Eisley spaceport." You and your faction members feel the validation — your work shaped the world. The opposing Hutt-aligned players in the zone feel the corresponding pressure: their black-market access just got harder, their NPC enforcers more hesitant, their missions rarer.

**Scenario 3 — The escalation.** A new player joins the CIS faction. They run aggressive missions, kill several Republic NPCs in Coruscant's lower levels. The Director notices and posts an escalating series of responses: first an ambient flavor line ("Republic patrols search Sector 4 in heavier numbers tonight"), then a HoloNet headline ("Coruscant Security Force investigates string of attacks on Republic personnel"), then an actual posted bounty on the player ("CIS operative wanted alive, 2000 cr, Bounty Hunters Guild contract #4421"). The new player has accidentally drawn real PvP heat. Other PCs in the Bounty Hunters' Guild see the contract on the board and can pursue. The new player learns that actions have weight.

---

## 10. The Player's Relationship with the Director

The Director is your ally even when it's making your life harder. Its purpose is to keep the world dynamic and responsive — to make your choices matter, to put opportunities in front of you, to create the kind of emergent stories that no scripted campaign could match.

A few principles to keep in mind:

**The Director will never invent plot for you.** If you wait for a story, you'll wait forever. The Director sets the stage; you write the play. The mission boards, the events, the influence shifts — those are invitations. You have to RSVP.

**The Director respects player agency.** It does not retcon your decisions. It does not invalidate your character's progress. It does not put you in a no-win situation arbitrarily. When the world pushes back, it's because you pushed first.

**The Director is opaque, deliberately.** You don't see the influence scores, you don't see the pending promotion queue, you don't see the Evaluator's notes on your last pose. The opacity is part of why the world feels real — you read consequences in their downstream effects, not in a numerical dashboard.

**The Director can be wrong.** It's an AI, it makes calls based on incomplete information, and it will occasionally generate a mission that doesn't quite fit, narrate an ambient line that contradicts the zone's actual state, or fail to notice something it should have. If you see something genuinely broken, report it. Don't try to game it.

---

## 11. Commands Related to the Director

The Director runs behind the scenes, but a few commands give you visibility into its outputs:

| Command | Effect |
|---|---|
| `+news` | Show recent HoloNet News headlines |
| `+news <count>` | Show last N headlines (default 5) |
| `+events` | Show currently active world events in your zone |
| `+events all` | Show all active world events across the galaxy |
| `+zone-status` | Show alert level and ambient context for your current zone |
| `+missions` | Show your faction's currently posted missions |
| `+missions all` | Show all missions you're eligible for (across factions and guilds) |
| `+bounty list` | Show currently posted bounties (BHG members only) |
| `+history rep` | Show your reputation history (changes over time, anonymous source) |

There are no commands to influence the Director directly — no `+petition`, no `+request-event`, no `+ask-director`. The world responds to what you do, not what you ask.

---

## 12. Numbers at a Glance

For reference, the key numerical parameters of the CW Director:

| Parameter | Value | Note |
|---|---:|---|
| Faction Turn cycle | 30 game-minutes | When influence/promotions/missions recompute |
| Max influence delta per turn | 5 points | Conservative pacing |
| Influence range | 0–100 | Per faction per zone |
| Secured-tier threshold | Republic ≥ 75 | Forces zone to Secured |
| Lawless-tier threshold | Criminal ≥ 80 | Forces zone to Lawless |
| Martial-law threshold | Republic ≥ 90 | Forced SECURED regardless of base |
| Standard alert | Republic 30–49 (default) | Zone's default state |
| High alert | Republic 50–69 | Patrol density up |
| Lockdown | Republic ≥ 70 | Combat restrictions, patrols dense |
| Lax | Republic < 30 | Patrol density down |
| Underworld | Criminal ≥ 70 | Hutt-coded zone behavior |
| Discipline escalation | Warn → Probation → Expel | Never skip steps |
| Player joinable factions | 6 | Republic, CIS, Jedi, Hutt, BHG, Independent |
| NPC-only factions | 2 | Sith, Separatist Council |
| Standard world events | 12 types | See §3 |
| Milestone events | 5 types | See §3 |

---

## 13. A Final Word

The Director AI is the part of the game that makes it feel alive when no one is watching. A small playerbase doesn't have to mean an empty galaxy — the Director ensures that even in a quiet hour, the world is doing something. NPCs are moving, factions are scheming, news is breaking, missions are appearing, the war is grinding on somewhere offscreen.

When you log in, that's the world you're stepping into. When you log out, the world keeps going. Your character's story is written by you, but the setting that gives it meaning is maintained by the Director, around the clock, in service of the play experience for everyone.

---

*This guide is part of the SW_MUSH Game Guides. See also: [Organizations & Factions](#/guide/organizations-factions), [Security Zones](#/guide/security-zones), [Territory Control](#/guide/territory-control), [Channels, Mail & News](#/guide/channels-mail-news), [Scenes, Plots & Places](#/guide/scenes-plots-places).*
