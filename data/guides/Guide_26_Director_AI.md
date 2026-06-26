---
category: community
order: 4
summary: "The Director AI runs ambient events, NPC behavior, and emergent storylines across the galaxy."
tags: ["director", "ai", "npc", "events", "ambient", "story", "emergent"]
---

# The Director AI

**Parsec — WEG D6 Revised & Expanded**

---

## How to Read This Guide

The Director AI is the invisible hand that keeps the galaxy moving when no Game Master is online. It runs ambient text, posts missions, escalates faction conflicts based on player actions, narrates news, promotes and disciplines NPC-faction members, approves requisitions, and pushes the broader narrative of the Clone Wars forward over weeks and months of play.

Most players never need to think about the Director directly — they experience its work as ambient flavor and emergent consequences. But understanding the system helps you read what's happening, anticipate how the world will respond to your actions, and recognize when an opportunity is being put in front of you that you should grab.

If you only have ten minutes, read **§1 What the Director Does** and **§4 How You Affect the Director**. That's enough to understand the feedback loop between your actions and the world's response. The rest covers the underlying systems: faction influence, world events, ambient narration, the Faction Turn, and the war's broader tide.

This guide assumes familiarity with the [Organizations & Factions](#/guide/organizations-factions) and [Security Zones](#/guide/security-zones) systems, both of which the Director acts on.

---

## 1. What the Director Does

The Director AI is a Claude-backed orchestration layer that runs in the background of the game. Its responsibilities, in rough order of how often a player encounters them:

**Ambient narration.** Every few minutes, the Director emits room-flavor text appropriate to the zone you're in — a clone patrol marching past on the Nar Shaddaa Promenade, a Hutt enforcer collecting from a market stall, distant blaster fire from the underworld, a HoloNet vendor crying the day's headlines. These don't require your input or response. They just make the world feel inhabited.

**Mission generation.** The mission boards you interact with are populated from a Director-managed pool. The Director picks missions appropriate to the zone, the active faction influence, and recent player activity. CIS infiltration arc landing on Coruscant? Republic Intelligence missions appear on the Coruscant board. Hutt unrest in the Nar Shaddaa Warrens? Hutt enforcement contracts appear in the Hutt mission pool.

**NPC behavior.** NPCs in combat use behavioral profiles (see [Ground Combat](#/guide/ground-combat)), but their broader behavior — whether they're hostile, friendly, watchful, or absent — is shaped by the Director's read of the zone's current state. A clone patrol in a high-influence Republic zone is on routine watch; the same patrol in a contested zone is jumpy and hair-trigger.

**Faction administration.** For NPC-managed factions (currently Republic, CIS, Jedi Order, Hutt Cartel), the Director handles promotions, approves equipment requisitions, dispenses discipline for infractions, and posts faction-internal news. PC-led factions (currently only the Bounty Hunters' Guild operates this way) handle their own administration; the Director only intervenes if the faction goes inactive.

**World events.** The Director triggers narrative events that affect zones — crackdowns, surges, weather, market booms. See §3.

**Long-arc tide.** The Clone Wars are dragging on. The Director carries the war's tide forward — Republic consolidation, Separatist surges, the cartels profiting from both — by tracking faction influence across the galaxy and marking the milestones when one side's grip tightens. See §8.

The Director is **not** a Dungeon Master. It does not arbitrate disputes, does not invent plot for you, does not give players special treatment. It's a world simulator with narrative awareness.

> **A note on the Director's two gears.** The Director always runs its local simulation — influence shifts, alert levels, world events, security overlays, news headlines, and milestones happen on every Faction Turn regardless of budget. The richer, intelligent layer — Claude-written headlines, promotion and discipline decisions, requisition rulings, and personalized story hooks — runs when the Director's paid Claude turn fires, which is governed by a monthly spend budget and adaptive cadence. On a quiet server the Director slows its paid cadence (or skips it) to conserve budget; when players are active and the stakes are high, it speeds up. Either way the world keeps moving.

---

## 2. The Faction Influence System

The Director tracks **per-zone faction influence** — a score from 0 to 100 for each faction in each zone. The influence profile shapes everything about how that zone behaves.

### The factions tracked

Six factions are tracked in zone influence scores — the same six you can join:

- **Republic** — light-lean, primary order axis
- **CIS** — dark-lean, insurgent challenger
- **Jedi Order** — light, locked, Village-gated for PCs
- **Hutt Cartel** — neutral, criminal-coded
- **Bounty Hunters Guild (BHG)** — neutral, contract-coded
- **Independent** — default, unaligned

Several additional **NPC-only factions** exist for narrative coloring. They do **not** appear in zone influence scores — they surface only as ambient flavor and milestone narration:

- **Sith** — the Dooku/Sidious axis, covert and atmospheric. Players never see Sith influence as a number; it surfaces as dark-side ambient events and in the Director's narrative voice.
- **Separatist Council** — the CIS oligarchy. Narrated as a CIS overlay.
- **Stalgasin & Gehenbar** — the rival Geonosian hives (Stalgasin dominant and CIS-leaning, Gehenbar its Republic-backable challenger). They drive Geonosis turf-dispute narration only.

### Influence change drivers

Influence changes from:

- **Player actions in the zone.** Completing faction missions, defeating rival-faction NPCs, investing organization treasury (see [Territory Control](#/guide/territory-control)) — these directly shift the Director's faction influence in that zone. A Republic player completing Republic missions in Mos Eisley pushes Republic influence upward in Mos Eisley.
- **NPC activity.** Faction-aligned NPCs in the zone reinforce their faction's influence; their absence allows decay.
- **Director decisions.** During the Faction Turn cycle (every 30 game-minutes), the Director recomputes and adjusts based on accumulated activity. Maximum delta per turn is **5 points** — the Director won't catastrophically shift a zone overnight.
- **World events.** Active events affect their zone's character — a security crackdown raises the authority profile; a pirate surge raises criminal pressure in the space lanes.

### Influence in your perception

You don't see numerical influence scores as a player. You see derived signals — the zone's **security tier** changes, the **ambient narration tone** changes, the **NPC behavior** changes, the **mission pool** changes, the **HoloNet News** mentions the zone.

For example, in a zone where Republic influence has climbed high:

- The zone's security tier in `look` may upgrade — a **Contested** zone becomes **Secured** once Republic influence crosses 75 (one tier up), and at overwhelming Republic dominance (90+) the zone is forced to **Secured** under martial authority.
- Clone patrol ambient narration becomes more frequent.
- Republic enforcement missions appear on the board ("Apprehend a known CIS sympathizer in Sector 4").
- The HoloNet may announce: "Republic Garrison reinforced at Mos Eisley spaceport."
- Hutt-affiliated NPCs become wary, less likely to openly proposition you for contraband.

In a zone where Hutt influence has climbed instead:

- The security tier may downgrade — a **Contested** zone slips to **Lawless** once Hutt influence crosses 80 (one tier down).
- Hutt enforcer narration appears; clone patrols thin out.
- Hutt smuggling and enforcement missions appear; Republic missions become rare or absent.
- The HoloNet may announce: "Hutt Council issues neutrality reaffirmation following alleged enforcement actions in Outer Rim sectors."
- The black market becomes accessible to anyone with the right faction standing.

The world tells you what's happening. You don't have to dig.

---

## 3. World Events

The Director runs **world events** — narrative beats that affect zones for a bounded period. They're announced when they start and when they end, and the web client surfaces the ones near you. The Clone Wars era ships **seventeen** standard event types:

| Event | Effect | Typical Duration |
|---|---|---|
| Security crackdown | Patrols ×2, smuggling payouts ×1.5 in the affected zone | 30–60 min |
| Security checkpoint | Contraband scans intensify at the affected spaceport/streets | 15–30 min |
| Bounty surge | Bounty Hunters' Guild contract rewards ×2 | 30 min |
| Traveling merchant | A rare-goods vendor sets up in a market zone | 20 min |
| Sandstorm | Desert zone: Perception −1D, ranged fire −1D | 10–20 min |
| Gravel storm | Worse sand-weather: Perception −2D, ranged fire −2D | 10–18 min |
| Sandwhirl | Violent sand funnel: Perception −3D, ranged fire −3D — find shelter | 3–6 min |
| Cantina brawl | Cantina zone: a fight breaks out, combat spikes | ~5 min |
| Distress signal | A ship in orbit calls for help; rescue for rep + credits | 15 min |
| Pirate surge | Space lanes: pirate spawn rate ×3 — fly armed | 60–120 min |
| Hutt auction | Black-market vendor appears (criminal rep ≥ 30 to attend) | 30 min |
| Krayt dragon sighting | Tatooine outskirts: an emergency bounty contract posts | 45 min |
| Separatist agitation | CIS agitprop appears; sympathies stir | 30 min |
| Trade boom | Vendor sell prices +25% in the zone | 60 min |
| Intelligence thaw | Intel handler payouts ×2 — the spy's holiday | 30 min |
| Spice demand | Smuggling-run payouts ×2 — the smuggler's holiday | 30 min |
| E'Y-Akh flood | Geonosis: the annual flood rolls out; Perception −1D | 60–120 min |

Events are **announced when they fire** and visible to all players in the affected zone; the web client lists active events near you, and weather events also show up under `+weather`. They are an invitation, not an obligation — a Hutt auction in Nar Shaddaa is just a thing happening; you can ignore it, attend, exploit it, or sabotage it, as your character disposes.

Events also have **preferred zones, rarity, and cadence** to prevent monotony. A sandwhirl is the rarest weather beat and the shortest; a security checkpoint is common and brief; a pirate surge is a long, dangerous window in the space lanes. The Director respects pacing.

### Milestone headlines — the war's tide

Above the standard event pool, the Director tracks the **galaxy-wide average** of each faction's influence and fires a one-time **milestone headline** when a faction's tide crosses a threshold. These mark the broad sweep of the war rather than a single zone's weather. Seven are authored:

| Milestone | Fires when | Reads as |
|---|---|---|
| Republic ascendant | Republic influence climbs high (~60 avg) | Clone patrols and checkpoints multiply sector-wide; also triggers a security crackdown |
| Republic martial footing | Republic dominates (~75 avg) | The Grand Army locks down strategic districts; triggers a security crackdown |
| Separatist surge | CIS influence rises (~40 avg) | Sympathizers grow bolder, war fever rises; triggers separatist agitation |
| Separatist offensive | CIS pushes hard (~55 avg) | Separatist cells coordinate openly; triggers separatist agitation |
| Cartels' profit | Hutt influence climbs (~65 avg) | The kajidic tighten their grip on the war economy |
| Underworld dominion | Hutt influence dominates (~80 avg) | Neither Republic nor Confederacy writ runs here |
| Power vacuum | Republic influence collapses (~below 12 avg) | Republic authority withdraws; the streets answer to no banner |

Milestones are rare — each fires once when the tide turns, and they're driven by accumulated player and NPC activity across the whole galaxy. The deepest dark-side and Sith beats don't surface as a tracked number; they come through the Director's narration when the moment is right ("the dark side stirs — and most who notice are wrong about what they noticed"). But one dark-side beat *does* surface — with a meter and a fight attached. That's the **cult uprising**, below.

### Dark-side cult uprisings — a beat you can fight

Apart from the standard event pool, the Director occasionally posts a **cult uprising**: a named dark-side cult rising in a zone, with a visible **menace meter** that climbs on a clock. This is not a take-it-or-leave-it event — it has a win/lose state. The community has until a deadline to break the cult; if its menace reaches full strength first, the cult wins and the Director logs the loss to the war's record. Only one uprising runs at a time, with a breather between, so each stays an event.

You see and join an uprising through one command:

```
rally            — the threat board: which cult, where, the menace meter, the
                   win/lose state, and how to help
rally strike     — make your move against it (alias: front)
```

A cult uprising takes one of two shapes, and `rally` tells you which:

- **Staged operations.** The Cult of the Hollow Sun (Tatooine's deep desert), the Ember Court (the Geonosis wastes), and the Ashen Hand (the Coruscant underworld) run as real location scenarios. Here `rally` is your **locator** — it names the live **site** and the current stage. You travel to that site and `investigate` it to fight through the operation stage by stage: assault the cult's stronghold (waves of enemies), then work the objective (slice a terminal, turn an informant), then bring down the leader. `rally strike` from across the galaxy just points you to the site — the gameplay is *there*, hands-on, not a slogan you repeat from afar.
- **Galaxy-wide menace cults.** The Drowned Choir (Nar Shaddaa) and the Iron Veil (Kuat) are fought as a coordinated push from wherever you are. `rally strike` records your contribution — the game rolls your **best pool across playstyles** (a soldier swings, a slicer disrupts their operations, a face rallies civilians against them, a Jedi pushes back the dark side), so every kind of character can help. Each character lands one counted strike per ~10 minutes, and the meter moves on the **community's** total effort — a win is a group achievement, never one person macroing a counter to zero.

**The reward is reputation, not credits.** Break a cult and everyone who helped gains **Republic reputation** — more for a larger share of the effort (roughly 3 for a single strike, up to 15 for the largest contributor) — and the players who carried the most of the fight earn a commemorative status flag marking that they helped rout that cult. There are no credit rewards here; this is a reputation-and-roleplay beat, paid in the same Republic standing the Director watches (§4). A loss costs you nothing — an uprising is an opportunity, never a penalty.

---

## 4. How You Affect the Director

The feedback loop between player action and Director response is the heart of the system. Every meaningful action you take feeds back, in some way, to the world's evolving state.

**Direct feedback:**

- **Mission completion** shifts faction influence in the mission's zone.
- **PvE combat** with faction-aligned NPCs shifts influence in the room where the fight happened.
- **Faction treasury donations** (see [Territory Control](#/guide/territory-control)) shift faction influence in the zone the org is anchored to.
- **Death and respawn** generate small ambient flavor but don't shift influence.

**Indirect feedback:**

- **Sustained presence in a zone** is noticed — repeated visits, repeated combat, repeated faction work all read as the player choosing that zone as their base of operations. The Director may post more missions there to reward your interest.
- **Faction-comm engagement** — the Director tracks *how much* you engage on each faction's channels, as a volume signal of where your loyalties lie. It does not score the literary quality of your poses (see §7) — it counts your activity and weights its read of your alignment accordingly.
- **Faction standing** — your reputation with each faction (see `+reputation`) feeds the Director's read of your trajectory. A player who is Revered with the Republic draws Republic-themed opportunities; a player Hostile with the CIS may attract Separatist attention or bounty hunters. Players at Unknown/Wary standing are not targeted with faction content.

**What the Director does NOT respond to:**

- Out-of-character chatter in OOC channels
- Mechanical commands with no narrative footprint (checking the map, your sheet, etc.)
- Idle time — sitting AFK doesn't decay your reputation (though inactivity stretching to days does)

The Director is also **conservative about promotion**. It will not push you up faction ranks just because you've ground out reputation. Promotions happen on its Claude turn, against an explicit candidate list, and its standing instruction is blunt: *"Promote conservatively. Players must EARN rank."* Discipline is just as deliberate — it escalates warn → probation → expel and never skips a step.

---

## 5. The HoloNet News Feed

The Director publishes news at semi-regular intervals through the **HoloNet News feed**, read with `+news` (also `news`) or visible on the web client's news panel. Headlines come from a pool of templated stories the Director fills in with current world state, and the most dramatic ones are rewritten by Claude for atmosphere.

Sample headlines you might see:

- "Republic forces report continued operations in the Outer Rim Sieges. The Chancellor's office expresses confidence."
- "Senate debate on supplemental war appropriations enters its third week. Loyalist and Reformist blocs trade procedural blows."
- "Kuat Drive Yards announces production milestone: hundredth Venator-class Star Destroyer commissioned this fiscal year."
- "Confederate forces claim victory at undisclosed Outer Rim location. Republic Command declines comment pending verification."
- "Bounty Hunters Guild posts unusual cluster of high-value contracts. Source identification withheld."
- "Jedi Master [name] reportedly killed in action. Council statement pending."
- "Trade Federation assets seized in three Mid Rim systems. The Federation calls the actions 'irregular.'"
- "Senator from [sector] introduces resolution reaffirming Chancellor's emergency powers. Vote anticipated to be near-unanimous."

Some headlines reflect **current Director state** — a milestone the Director just crossed, or a world event that just fired. Others are flavor — atmospheric reminders of the wider galaxy.

Reading the news before you act on a plan is **smart pacing**. If there's a security crackdown announced on the spaceport, maybe defer your contraband run. If there's a trade boom announced, maybe push your cargo run forward.

---

## 6. The Faction Turn

Every **30 game-minutes** (1,800 seconds), the Director runs a Faction Turn cycle. The Director always performs its **local** work each turn:

1. **Influence update.** Player-action deltas accumulated since the last turn are applied to zone influence, then saved.
2. **Alert recompute.** Each zone's alert level is recomputed from its faction-influence axes (see §12).
3. **Security overlays.** Zone security tiers are shifted up or down based on the influence thresholds (§12).
4. **News emission.** A headline is generated, logged, broadcast to web clients, and queued for an atmospheric Ollama rewrite.
5. **Milestone check.** Galaxy-wide faction averages are checked against the milestone thresholds (§3); any newly-crossed milestone fires its one-time headline (and, for some, a world event).

When the Director's **paid Claude turn** runs (budget permitting — see §1), it additionally takes up to a few **faction orders** and player hooks:

- **Promotion review.** Eligible NPC-faction members are reviewed against the conservative-promote rule; eligible never means automatic.
- **Discipline review.** Infractions are reviewed and discipline applied (warn → probation → expel, never skipping a step).
- **Requisition review.** Pending equipment requests are approved unless the member negligently caused the loss.
- **Mission posting.** New missions are seeded to reflect current world state, not random jobs.
- **Story hooks.** A small number of brief, in-universe opportunity hooks may be delivered to specific online players via comlink.

The cycle runs in the background — you don't see it happen, and it doesn't interrupt play. But its effects show up over the next few minutes as the world adjusts.

---

## 7. How Roleplay Is Rewarded

A common misconception is that the Director "watches" and "grades" your roleplay — that an AI scores your poses and quietly hands out bonuses. **It does not.** The Director reads *world state* (influence, missions, combat, faction standing), not the literary quality of what you type. No AI currently grades your prose for rewards.

Roleplay is rewarded instead by two **player- and engine-driven** systems, both of which feed Character Point progression (see [CP Progression](#/guide/cp-progression)):

**Scene bonus — `+scenebonus`.** When a collaborative scene wraps, claim a completion bonus. The award scales with how many poses you contributed:

| Poses | Award |
|---|---|
| 1–3 | minimal (a brief encounter) |
| 4–9 | standard scene |
| 10–19 | extended scene — larger bonus |
| 20+ | full scene — maximum tier |

Claim it once per scene, when the thread reaches a natural stop. Spamming it for trivial interactions defeats the system, and staff can see the claim patterns.

**Kudos — `+kudos <player> [reason]`.** Recognize *another* player's excellent roleplay. A kudos award grants the recipient **35 ticks** toward their next Character Point. Anti-farming limits keep it honest: you can give **3 per week** (rolling 7 days), only once per recipient per 7 days, and any recipient can receive at most **3 per week**.

The two stack. An exceptional collaborative scene where everyone claims a scene bonus and then kudoses their partners is the fastest legitimate path to advancement. Check your standing anytime with `+cpstatus`.

So: play well because the *people you play with* will recognize it, and because finishing real scenes pays. The Director sets the stage; the reward for performing on it comes from the table, not from a hidden AI critic.

---

## 8. The War's Tide

The Director carries the Clone Wars forward, but it does it through **influence and milestones**, not a scripted three-act campaign. The setting is fixed at **mid-war, roughly 20 BBY** — both sides have committed, neither has the upper hand, the Republic has finally raised enough clone divisions to hold and the CIS has finally found the patience to attrit. That's the galaxy new players arrive into, and it's the tone the Director maintains.

What *moves* is the tide. As player and NPC activity shifts faction influence across the galaxy, the milestone headlines of §3 fire — Republic ascendant, Separatist surge, underworld dominion, power vacuum. These are the war's weather report: which way the galaxy is leaning right now. Sustained CIS success in the Outer Rim pushes the tide one way; sustained Republic success pushes it back. The war's pace is genuinely shaped by what players do, within the canonical envelope of the era.

There is no scheduled "Order 66 endgame" in the current build, and the Director will not retcon the era out from under you. The dark side stirs in the Director's narration — a deliberate, low background hum — but the operatic, mid-war Clone Wars is the stage, and it stays the stage.

---

## 9. Worked Scenarios

To make the abstractions concrete, here are three scenarios showing the Director at work.

**Scenario 1 — The mission pull.** You're a Republic Intelligence operative who's been working Mos Eisley for two weeks. Your reputation is climbing. The Director has tracked your activity and notices that Mos Eisley currently has elevated CIS influence (a CIS infiltrator NPC ran a successful arc two days ago, raising CIS in the zone). Your next mission board check shows a new mission: "Identify the CIS contact in Chalmun's Cantina before they make their handoff." The mission appeared because *you* are in the zone, *you* are Republic Intelligence, and the *zone state* needs Republic counter-intelligence work. The Director put it in front of you specifically. Whether you take it is your call.

**Scenario 2 — The faction influence push.** Your faction has been quietly working Mos Eisley for two weeks. You've been running missions, killing CIS NPCs, investing treasury. One Faction Turn, the zone's accumulated Republic influence crosses the threshold and its security tier upgrades — Contested becomes Secured. The Director announces: "Republic Garrison reinforced at Mos Eisley spaceport." You and your faction members feel the validation — your work shaped the world. The opposing Hutt-aligned players feel the corresponding pressure: their black-market access just got harder, their NPC enforcers more hesitant, their missions rarer.

**Scenario 3 — The escalation.** A new player joins the CIS faction and runs aggressive missions, killing several Republic NPCs in Coruscant's lower levels. The Director notices and posts an escalating series of responses: first an ambient flavor line ("Republic patrols search Sector 4 in heavier numbers tonight"), then a HoloNet headline ("Coruscant Security Force investigates string of attacks on Republic personnel"), then a posted bounty on the player. The new player has accidentally drawn real PvP heat. Other PCs in the Bounty Hunters' Guild see the contract on the board and can pursue. Actions have weight.

---

## 10. The Player's Relationship with the Director

The Director is your ally even when it's making your life harder. Its purpose is to keep the world dynamic and responsive — to make your choices matter, to put opportunities in front of you, to create the kind of emergent stories that no scripted campaign could match.

A few principles to keep in mind:

**The Director will never invent plot for you.** If you wait for a story, you'll wait forever. The Director sets the stage; you write the play. The mission boards, the events, the influence shifts — those are invitations. You have to RSVP.

**The Director respects player agency.** It does not retcon your decisions. It does not invalidate your character's progress. It does not put you in a no-win situation arbitrarily. When the world pushes back, it's because you pushed first.

**The Director is opaque, deliberately.** You don't see the influence scores, you don't see the pending promotion queue. The opacity is part of why the world feels real — you read consequences in their downstream effects, not in a numerical dashboard.

**The Director can be wrong.** It's an AI; it makes calls on incomplete information, and it will occasionally generate a mission that doesn't quite fit or narrate an ambient line that contradicts the zone's actual state. If you see something genuinely broken, report it. Don't try to game it.

---

## 11. Commands Related to the Director

The Director runs behind the scenes, but a few commands give you visibility into its outputs:

| Command | Effect |
|---|---|
| `+news` (also `news`) | Show recent HoloNet News headlines — the Director's news feed |
| `+missions` (also `missions`, `mb`, `jobs`) | Show your faction's currently posted missions |
| `+missions all` | Show all missions you're eligible for, across factions and guilds |
| `+bounties` (also `bboard`) | Show currently posted bounties (the Bounty Hunters' Guild board) |
| `+reputation` (also `+rep`) | Show your standing with each faction — the score the Director targets content by |
| `+weather` (also `+time`) | Show local conditions, including any active weather world event |
| `rally` (also `+rally`, `front`) | Show the active dark-side cult uprising — the menace board, the site to hit, and how to strike back (§3) |
| `look` | The room itself shows the zone's current security tier |

There are no commands to influence the Director directly — no `+petition`, no `+request-event`, no `+ask-director`. The world responds to what you do, not what you ask. (Note: `+events` is the player **social calendar** for scheduled scenes and plots — it is *not* the world-event feed; Director world events announce themselves when they fire and surface on the web client and via `+weather`/`+news`.)

---

## 12. Numbers at a Glance

For reference, the key parameters of the CW Director. You don't see these as a player — they drive the effects you *do* see — and they're playtest-tunable.

The alert/security thresholds read three **influence axes**: **authority** = Republic influence, **warfront** = CIS influence, **underworld** = Hutt Cartel influence.

| Parameter | Value | Note |
|---|---:|---|
| Faction Turn cycle | 30 game-minutes | When influence/alerts/milestones recompute |
| Max influence delta per turn | 5 points | Conservative pacing |
| Influence range | 0–100 | Per faction per zone |
| Player-joinable factions | 6 | Republic, CIS, Jedi, Hutt, BHG, Independent |
| NPC-only narrative factions | 4 | Sith, Separatist Council, Stalgasin, Gehenbar |
| Standard world events | 17 types | See §3 |
| Milestone headlines | 7 | Faction-tide markers; see §3 |
| **Security tier overlay** | | Applied to the SECURED / CONTESTED / LAWLESS base |
| Authority (Republic) ≥ 75 | Upgrade one tier | e.g. Contested → Secured |
| Authority (Republic) ≥ 90 | Force SECURED | Martial authority |
| Underworld (Hutt) ≥ 80 | Downgrade one tier | e.g. Contested → Lawless |
| **Director alert level** | | Most disruptive condition wins |
| Lockdown | Authority ≥ 70 | Patrols dense |
| Underworld | Underworld ≥ 70 | Hutt-coded zone behavior |
| Unrest | Warfront ≥ 40 | War pressing in |
| High alert | Authority ≥ 50 | Patrol density up |
| Lax | Authority < 30 and no threat axis dominant | Patrol density down |
| Standard | otherwise | The default state |
| Discipline escalation | Warn → Probation → Expel | Never skip steps |

---

## 13. A Final Word

The Director AI is the part of the game that makes it feel alive when no one is watching. A small playerbase doesn't have to mean an empty galaxy — the Director ensures that even in a quiet hour, the world is doing something. NPCs are moving, factions are scheming, news is breaking, missions are appearing, the war is grinding on somewhere offscreen.

When you log in, that's the world you're stepping into. When you log out, the world keeps going. Your character's story is written by you, but the setting that gives it meaning is maintained by the Director, around the clock, in service of the play experience for everyone.

---

*This guide is part of the Parsec Game Guides. See also: [Organizations & Factions](#/guide/organizations-factions), [Security Zones](#/guide/security-zones), [Territory Control](#/guide/territory-control), [Channels, Mail & News](#/guide/channels-mail-news), [CP Progression](#/guide/cp-progression).*
