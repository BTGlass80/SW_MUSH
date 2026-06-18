---
category: paths
order: 5
summary: "Disguise, infiltration, sabotage, and intel networks. The shadow profession."
tags: ["espionage", "spy", "disguise", "stealth", "intel", "sabotage", "infiltration"]
---

# Espionage

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This guide covers the **information-gathering layer** of the game — the commands you use to assess strangers, eavesdrop on adjacent rooms, search rooms for hidden information, intercept comlinks, and compose intelligence reports you can trade with other characters.

Espionage is **the alternative to direct confrontation**. Combat tells you what your enemy can do; espionage tells you who they are, what they're carrying, where they've been, what they're planning. For investigators, journalists, faction intelligence officers, spies, and any character whose work involves knowing things before others do, this is the toolkit.

If you only have ten minutes, read **§1 The Five Commands** and **§4 Intel Reports**. The first sets the toolkit; the second is the trade layer where information becomes currency.

This is a new guide. There was no earlier version.

---

## 1. The Five Commands

Five player-facing commands form the espionage suite. All five also live under the `+spy` umbrella for unified discoverability.

| Command | What it does |
|---|---|
| **`assess`** | Covertly read another character — their stats, gear, mood |
| **`eavesdrop`** | Listen to conversations in an adjacent room |
| **`investigate`** | Search the current room for hidden information |
| **`intercept`** | Tap nearby comlink and faction comms |
| **`+intel`** | Compose, seal, and trade intelligence reports |

Each command has its own skill check, cooldown, and discovery risk (the chance the target notices you spying). The risks scale with the action — assessing someone has low discovery risk; intercepting comms is louder.

### Common skills used

| Skill | Where it shows up |
|---|---|
| **Perception** | Assess, eavesdrop, intercept |
| **Search** | Investigate |
| **Con** | Defending against being assessed |
| **Sneak** | Defending against being noticed |
| **Security** | Defending against intercept |

Strong espionage characters typically train Perception to 4D-5D and pick up Search at 3D+. Their build is information-focused — they're not always combat capable, but they know things.

---

## 2. Assess — Covert Character Assessment

```
assess <player>
(aliases: size)
```

Reads another character covertly. The system uses your **Perception** against the target's **Con** in an opposed roll. The result determines how much you learn.

### What you can learn

The assess result depends on your skill check **margin** (your roll minus their roll). Higher margins reveal more:

| Margin | What you see |
|---|---|
| < 0 (fail) | Nothing useful — "You observe casually but can't read much" |
| 0-4 | Basic state: demeanor, wound level |
| 5-9 | + Equipped weapon, rough faction affiliation hints |
| 10-14 | + More detailed equipment, posture/attitude reads |
| 15+ | + Full assessment: gear, faction, recent activity, mood |

A skilled assessor catching a wounded character with the right margin sees things like: *"They look tense, hand near their weapon. Wounded — a recent fight. Armed with a blaster pistol, Republic-issue. The way they hold themselves suggests military training."*

### Discovery risk

If you **fumble** the Perception roll (wild die complication), the target notices. They get a message: *"You catch [your name] sizing you up."* You get: *"They catch you staring."* This is the social embarrassment — the assess failed *visibly*.

If you simply fail (without fumble), no one notices. You just learn nothing useful.

### Cooldown

Per-target cooldown of **2 minutes**. You can assess Player A, then Player B, then Player C in quick succession — but you can't re-assess Player A for another 2 minutes. Prevents stalker-style "constantly scan everyone."

### Practical wisdom

Assess is the **opening move** of an espionage scene. Walking into a room, you can assess up to half a dozen characters quickly to gauge who's interesting. The wounded character with Republic gear is probably worth investigating further; the relaxed bartender with no equipment is probably not.

For characters whose identity is to "see everything," assess is a routine command — they assess most strangers as part of normal play. The 2-minute cooldown prevents spam; the discovery risk creates real consequence if you push your luck.

---

## 3. Eavesdrop — Listening Through Walls

```
eavesdrop <direction>
eavesdrop stop
```

Begins listening to conversations in an adjacent room. You must specify a direction (`eavesdrop north`, `eavesdrop east`). The system identifies the room in that direction and starts an eavesdrop session.

### How it works

1. **Skill check on initiation.** Your Perception roll vs. a target difficulty determined by how distant or noisy the adjacent room is. Most cases are Moderate (15).
2. **On success**: an eavesdrop session is created. Lasts **5 minutes** real-time.
3. **During the session**: every time someone in the target room speaks (via `say` or pose-dialogue), you receive a **muffled fragment** of what they said.
4. **On fumble or failure**: nothing happens; cooldown still applies. On critical fumble, the target room hears suspicious sounds from your direction ("a faint shuffling sound from beyond the wall").

### What "muffled" means

You don't get the full transcript. The text is **partially obscured**:

- High-margin success: you hear most of the words, some lost. *"...the cargo at midnight... bring the [obscured]... meet at the [obscured]..."*
- Moderate success: you hear fragments. *"...something something cargo... midnight... [obscured]..."*
- Low success: you hear scattered words. *"...cargo... [obscured]... ...meet..."*

You're catching pieces, not transcripts. Your character can piece together meaning over the 5-minute window. Some sessions yield clear intel; others yield only suspicion.

### Cooldown

**10 minutes** between eavesdrop sessions. You can't chain-eavesdrop to a different room immediately after one ends.

### Movement breaks it

Moving out of your current room (or out of range of the target room) ends the eavesdrop session. You can manually stop with `eavesdrop stop`.

### Practical wisdom

Eavesdrop works best when you have **a specific target conversation** you want to catch. Trailing a suspect through a building? Eavesdrop on their meeting room after they enter. Investigating a faction safehouse? Set up in an adjacent corridor and listen during their planning session.

It's less useful for fishing — random eavesdropping on busy rooms produces noise rather than information. Most cantina conversations are mundane; the worthwhile catches are quiet, deliberate exchanges in less-public rooms.

---

## 4. Investigate — Searching Rooms for Hidden Information

```
investigate
(aliases: search, inspect)
```

Searches the current room for **hidden information** — clues, environmental details, signs of recent activity. Uses your **Search** skill against a difficulty determined by the room's content.

### What you can find

Rooms can contain hidden information layers:
- **Recent activity traces.** Footprints, disturbed dust, the smell of recent fire.
- **Hidden objects.** A small comm device tucked behind a barrel; a stash of credits in a wall niche.
- **Document fragments.** A torn piece of a manifest; a coded message half-burned in an ashtray.
- **Environmental clues.** Signs of struggle; the room layout suggesting a meeting just happened.

The Director AI and room builders seed rooms with this information — not every room has discoveries, but rooms with recent significant events often do.

### How the check works

1. **Cooldown per room: 30 minutes.** You can only investigate a given room twice per real-time hour. The cooldown prevents brute-force re-investigation.
2. **Search roll vs. room difficulty.** Higher Search + better roll = more findings.
3. **Findings revealed**: a description of what you discover, often with context for why it matters.

### Discovery risk

Investigation is **not particularly covert**. If other characters are in the room, they see you searching. The action isn't private. You're not hiding your search; you're conducting it openly.

If you want to investigate covertly, do it in an empty room (or use `sneak` to enter unnoticed first).

### Practical wisdom

Investigation pairs naturally with detective work. After a combat in a room, investigate before leaving — you may find evidence about what happened, who the attackers were, what they were after. After overhearing a conversation through eavesdropping, follow the speakers and investigate where they meet next. Build a case from physical traces.

For investigative journalists, faction intel officers, and detective-style characters, the investigate command is a primary tool. The 30-minute cooldown is generous enough for active investigation; the findings can be substantive.

---

## 5. Intercept — Tapping Comlinks and Faction Comms

```
intercept                — Start intercepting (5-minute session)
intercept stop           — Stop intercepting
intercept status         — Check active intercept
(aliases: wiretap, comtap)
```

A more aggressive surveillance tool. While active, you receive muffled fragments of comlink transmissions and faction-channel comms from players in **your room and adjacent rooms**.

### How it works

1. **Skill check on initiation.** Perception vs. Difficulty 15 (Moderate). On success, an intercept session begins for 5 minutes.
2. **During the session**: you receive muffled fragments from comlinks and faction chats originating nearby. The text is obscured similarly to eavesdrop.
3. **Cooldown: 10 minutes** between intercept sessions.
4. **Fumble on initiation**: you're discovered — players in your room are notified that someone is conducting electronic surveillance.

### Scope

Unlike eavesdrop (which is a single adjacent room), intercept catches transmissions from:
- Your current room.
- All adjacent rooms.
- Both comlink pages (`page`) and faction-channel speech.

This is broader coverage but less focused — you'll catch chatter from multiple sources at once.

### Practical wisdom

Intercept is most useful when you're **in a busy area with multiple targets**. A spaceport, a cantina, an embassy lobby — anywhere there's lots of comlink traffic. You might catch fragments of three different conversations simultaneously, piecing together what's happening in the area.

It's also useful for **catching faction-channel chatter**. If you're embedded near a rival faction's safehouse, intercept may catch their internal comms. This is high-stakes intel — if it works.

The fumble risk is real. A fumbled intercept tells everyone in the room "someone is doing electronic surveillance." If you're undercover, this can blow your cover instantly.

---

## 6. Intel Reports — Information as Currency

The `+intel` command is the **trade layer** for intelligence. You compose reports from information you've gathered, seal them, and trade them with other players (or factions) for credits, rep, or other intel.

### Composing a report

```
+intel create <title>           — Start a new report draft
+intel add <text>               — Add a line to the current draft
+intel seal                     — Seal the report (makes it tradeable)
+intel discard                  — Discard the current draft
```

Reports are built **line-by-line**. You start with a title, add lines as you go, and seal it when you're done.

Example:
```
+intel create Republic Garrison Activity at Mos Eisley
+intel add Two new Hyena-class Bombers arrived this week, hangared in Bay 8.
+intel add Captain Vora replaced Colonel Drake as garrison commander.
+intel add Increased patrols on Outskirts road; pattern suggests they're looking for someone.
+intel add Source: cantina overhears + investigation of supply manifests.
+intel seal
```

The sealed report is now a tradeable item.

### Reading and giving reports

```
+intel                              — List your reports
+intel read <id>                    — Read a report
+intel give <player> <id>           — Give a sealed report to another player
```

When you `give`, the report transfers to the recipient. They can read it, file it, give it to others, or sell it.

### What makes a good report

The **value of intel** depends on:

- **Specificity.** "The Separatists are up to something" is worthless; "Captain Vora replaced Colonel Drake on this date" is valuable.
- **Recency.** Old intel decays in value fast. A report on patrol patterns from last week may already be obsolete.
- **Exclusivity.** Common knowledge has no value. Information only a few characters could have gathered has high value.
- **Actionability.** Intel that lets the recipient *do something* is more valuable than intel that's merely interesting.

A good faction intelligence officer compiles reports that pay (or earn rep) when traded to interested parties. Intel about CIS movements has value to Republic Intelligence; intel about Republic supply convoys has value to CIS or Hutt buyers. The trade network emerges organically.

### Trading intel between players

The basic trade happens through player-to-player exchange — you give the report, they pay you (or pay you in advance based on description). The system doesn't auto-broker intel transactions; the players negotiate. This is flexible: you can sell to rivals, gift to allies, or hold reports for personal use.

### Handing over to a faction handler (`+intel handover`)

The more mechanically rewarding path is delivering sealed intel directly to your **faction's intel handler NPC**, found in your faction's HQ. Handlers convert intel into credits **and** territory influence automatically.

```
+intel handover          — hand over your first sealed report
+intel handover <id>     — hand over a specific report by ID
```

**Requirements:**
- You must be a faction member (independent characters can't use handover).
- A matching handler NPC must be in the same room as you.
- The report must be sealed (not a draft) and not yet expired.

**Quality tiers — how the handler rates your intel:**

| Quality | Credits | Influence |
|---|---|---|
| **Low** | 200–500 cr | 1–3 |
| **Medium** | 600–1,500 cr | 4–8 |
| **High** | 2,000–5,000 cr | 10–20 |

**What determines quality?** The handler's assessment is a heuristic:
- **Line count** — more substantive entries (up to 5) score higher.
- **Region specificity** — naming a known wilderness region in your report body grants a major quality boost and is required for the influence award to land. Reports that don't describe any specific region still pay credits, but yield zero influence.
- **Freshness** — reports composed within the past 24 hours are worth more; reports older than 3 days are docked.
- **Proper-noun density** — actionable reports naming specific people, places, or units ("Clone Captain Voss," "Dune Sea garrison") score better than vague observations.

**Influence routing:** The influence delta routes into the region named in the report, applying SYN.3 contest multipliers if a contest is active. It flows through `adjust_territory_influence` — it counts toward your faction's foothold the same as a garrison garrison hold or territory action.

**INTELLIGENCE_THAW world event:** When this Director-triggered event is active, credit payouts double. Influence rates are unaffected. If you see "Intelligence Thaw: double rates!" in the handler's response, the event is running — a good time to clear your sealed-report backlog.

**Practical note:** To maximize quality, write reports that name a specific wilderness region your faction cares about, include at least 3–4 substantive lines naming real actors, and hand over within 24 hours of composing.

---

## 7. The Espionage Lifecycle

A typical espionage arc combines all five commands.

**Phase 1 — Initial reconnaissance.** You enter a busy area. You `assess` several strangers; some are interesting (high-rep faction members, wounded characters with story potential, clearly important figures). You note what you've learned.

**Phase 2 — Targeted observation.** One of the strangers heads to a quieter room — possibly to meet someone. You follow at a distance. They enter a meeting room. You position yourself in an adjacent room and `eavesdrop`. Over the next 5 minutes, you catch fragments of their conversation.

**Phase 3 — Physical investigation.** After they leave, you enter the meeting room. You `investigate`. You find the remnants of their meeting — a discarded data chip, a half-eaten meal, a note half-burned in an ashtray.

**Phase 4 — Compose the report.** You retreat to a safe location. You `+intel create Meeting at Mos Eisley Backroom`. You add what you learned: who attended, what they discussed (from eavesdrop fragments), what physical evidence remained. You `+intel seal`.

**Phase 5 — Trade or use the intel.** You can give the intel to your faction handler for credits and rep. Or you can sit on it, planning your own action based on what you learned. Or you can sell it to a third party who'd find it valuable.

This is the **information loop** — gather, analyze, package, distribute. Good intelligence work fits naturally into multi-session RP.

---

## 8. Counter-Espionage

If you're someone worth spying on — a faction leader, a known organizer, a high-rank character — you'll be on the receiving end of these commands. Some defenses:

### Defending against assess

Your **Con** skill is the defense against `assess`. High Con means assessors learn less from you. If your Con is 5D and someone tries to assess you with Perception 3D, they'll usually fail to read you usefully.

You can also dress to mislead. Wearing nondescript clothing, avoiding faction insignia, keeping your equipment hidden — these don't change the assess roll mechanically, but they shape what the result says (the assessor sees what's visible; what's hidden stays hidden).

### Defending against eavesdrop

The eavesdrop session has fumble risk for the eavesdropper — if they fumble, you hear suspicious sounds from their direction. Pay attention to ambient text. "A faint shuffling sound from beyond the wall" is your hint that someone is listening.

You can also use **places** (Guide #20) to compartmentalize sensitive conversation. Speaking via `tt` at a private booth is harder to overhear than speaking via `say` to the whole room.

### Defending against investigate

Don't leave evidence. If you finish a sensitive meeting, **clean the room** before leaving. Take any objects you placed. Be mindful of what an investigator might find — your half-burned note, your discarded data chip, the unique smell of your alien species lingering after you leave.

### Defending against intercept

Be cautious with comlink and faction-channel speech in public areas. Sensitive coordination should happen in private rooms (no intercept reach) or via in-person speech at a private place.

### Counter-surveillance commands

Some characters specialize in **counter-intelligence** — actively detecting and disrupting surveillance. They use `assess` on suspected spies. They sweep rooms with `investigate` for surveillance devices. They use `intercept` to catch surveillance comms targeting their faction. The cat-and-mouse dynamic is real.

---

## 9. Espionage and Reputation

Your espionage activity affects your reputation in subtle ways:

- **Discovered surveillance** (fumbled commands) damages your social standing if witnessed. Players who get caught spying may face faction-rep penalties from the targeted faction.
- **Good intel reports** delivered to faction handlers earn rep — typically +2 to +5 per significant report, depending on quality.
- **Faction informant work** is recognized in some faction's narrative — intelligence-gathering missions show up as faction missions for established intel officers.
- **The "known spy" identity** is real. A character with many discovered surveillance incidents is treated suspiciously everywhere. Some players embrace this; others avoid it.

The system supports both **clean intelligence professionals** (who never get caught and build sterling reputations) and **dirty spies** (whose work is messier but more dramatic).

---

## 10. The Worked Scenarios

Five concrete pictures.

**Scenario 1 — The cantina scout.** You're a Republic Intelligence officer in the Mos Eisley Cantina. You `assess` six strangers over 20 minutes. Two are interesting — a wounded character with CIS insignia, and a well-dressed Twi'lek with unmarked equipment. You pose your character making mental notes. The cantina rats know an intel scout when they see one; your assess work builds your reputation.

**Scenario 2 — The eavesdropping operation.** Two Hutt Cartel members enter a private booth in the Nar Shaddaa promenade. You move to the adjacent corridor and `eavesdrop east`. Over 5 minutes, you catch fragments: *"... shipment of glitterstim... arriving Tuesday... at the warehouse on..."* You don't catch every detail, but the patterns suggest a smuggling operation. You report it to your faction handler the next day.

**Scenario 3 — The investigation discovery.** A combat just ended in a Coruscant alley. You arrive after the fighters have left. You `investigate`. You find a torn piece of a uniform with CIS insignia, a blood smear suggesting the loser was wounded, and a small audio recording device (apparently dropped during the fight). The recorder still has data; combined with your read of the scene, you piece together the encounter.

**Scenario 4 — The intercept catch.** You're embedded near a CIS safehouse on Nar Shaddaa. You `intercept`. For 5 minutes, you catch fragments of comlink traffic between CIS operatives. One fragment is distinctive: *"... extracted... target acquired... rendezvous at the spaceport..."* You compile this into an intel report and deliver it to Republic Intel. The intel is fresh and actionable; Republic Intel pays 1,500 cr.

**Scenario 5 — The counter-intelligence sweep.** You're a faction security officer. You suspect spies are watching your safehouse. You walk the perimeter rooms. You `assess` everyone you encounter. One Twi'lek's pose feels off — too deliberately casual. You re-assess them; the second read suggests a CIS Intelligence pattern. You note their description and report it to your faction. The next time you see this Twi'lek, your faction is ready to follow them in turn.

---

## 11. Common Pitfalls

**1. Using `scan` instead of `assess` on the ground.** The `scan` command exists for ship sensors in space. On the ground, use `assess`. This is a frequent new-player confusion.

**2. Eavesdropping in a room with no direction information.** `eavesdrop` requires a direction; you can't just "listen" generally. Type `eavesdrop north` or `eavesdrop east` — whichever direction the target room lies.

**3. Burning the investigate cooldown on a thinly-content room.** Once you've investigated a room, the cooldown is 30 minutes. Don't waste it on rooms unlikely to have hidden information. Focus investigation on rooms where significant events recently happened.

**4. Composing intel from common knowledge.** A report saying "the Republic has soldiers" is worthless. Reports must contain information that wasn't already known to the recipient. Don't waste effort on common knowledge.

**5. Trying to be undetectable.** All espionage has fumble risk. Even the best Perception roll occasionally rolls a wild-die complication. Accepting that surveillance gets discovered occasionally is part of the realism. If your character can't accept that risk, espionage may not be their identity.

---

## 12. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `assess <player>` | Covertly assess a character (2-min cooldown per target) |
| `eavesdrop <direction>` | Listen to adjacent room (5-min session, 10-min cooldown) |
| `eavesdrop stop` | Stop active eavesdrop |
| `investigate` | Search current room (30-min cooldown per room) |
| `intercept` | Tap nearby comlinks (5-min session, 10-min cooldown) |
| `intercept stop` | Stop active intercept |
| `intercept status` | Check active intercept |
| `+intel` | List your intel reports |
| `+intel create <title>` | Start a new report draft |
| `+intel add <text>` | Add a line to the current draft |
| `+intel seal` | Seal the report (makes it tradeable) |
| `+intel discard` | Discard the current draft |
| `+intel read <id>` | Read a report |
| `+intel give <player> <id>` | Give a sealed report to another player |
| `+intel handover` | Hand first sealed report to faction handler (credits + influence) |
| `+intel handover <id>` | Hand a specific sealed report to faction handler |
| `+spy` | Umbrella for all the above |

---

## 13. Numbers At A Glance

| Quantity | Value |
|---|---|
| Assess cooldown per target | 2 minutes |
| Eavesdrop session duration | 5 minutes |
| Eavesdrop cooldown | 10 minutes |
| Investigate cooldown per room | 30 minutes |
| Intercept session duration | 5 minutes |
| Intercept cooldown | 10 minutes |
| Intercept skill check difficulty | Moderate (15) |
| Intercept scope | Your room + adjacent rooms |
| Eavesdrop scope | One specified adjacent room |
| Assess roll | Opposed Perception vs. Con |
| Eavesdrop roll | Perception vs. distance-scaled difficulty |
| Investigate roll | Search vs. room-scaled difficulty |
| Intel handover pay — Low quality | 200–500 cr, 1–3 influence |
| Intel handover pay — Medium quality | 600–1,500 cr, 4–8 influence |
| Intel handover pay — High quality | 2,000–5,000 cr, 10–20 influence |
| Intel handover — influence requirement | Report must name a known wilderness region |
| Intel handover — freshness window | 24 hours (older reports score lower) |
| Intel report rep gain | +2 to +5 per significant report (faction handler NPC) |

---

## 14. A Final Word

Espionage is the **information game** underneath the more visible combat and economic games. It rewards a specific kind of player: someone who pays attention, who keeps notes, who pieces small clues into bigger pictures, who enjoys the slow build of intel into actionable knowledge.

For most characters, espionage is **occasional** — you assess strangers as part of normal awareness, you investigate combat scenes for context, you eavesdrop when a specific situation calls for it. The commands are tools you reach for when relevant.

For dedicated intelligence characters, espionage is **profession**. You build Perception to 5D+, you specialize in observation and analysis, you compile detailed intel reports, you trade information for credits and reputation, you build a network of contacts who know your work is reliable. Over months, you become the character others come to when they need to know something.

The system rewards both modes. Casual users get useful information about their surroundings; specialists build entire careers around intelligence work.

If you're starting out: try `assess` on the next stranger you see in the cantina. You'll get a result (probably modest), and you'll understand the cadence. Try `investigate` after a combat ends. Try `+intel create` to compose your first report from what you observe in a single session. By month 3, you'll know which command to reach for when. By month 6, you may have a network of recipients who pay you for what you know.

The galaxy has secrets. Espionage is how you uncover them.

---

*End of Guide #22 — Espionage*
