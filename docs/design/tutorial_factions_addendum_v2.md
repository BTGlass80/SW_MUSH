# Tutorial System Design — Addendum v2
## Faction & Job Introduction Integration
### April 10, 2026

---

## 1. Problem Statement

The existing tutorial design (§11–13 of `tutorial_system_design.md`) has a gap: **players don't learn about factions until they stumble into a profession chain**, which requires multi-planet travel, a ship, and significant playtime. A new player in their first week knows about missions, smuggling, bounties, and crafting — but has no idea that the Rebel Alliance, Galactic Empire, Hutt Cartel, Bounty Hunters' Guild, Traders' Coalition, and Underworld exist as joinable factions with exclusive missions, equipment, and faction channels.

Similarly, the existing job board tutorial (Trader's Hall elective, Step 5 of the starter chain) teaches `+missions` and `+smugjobs` as standalone systems, but doesn't explain that **faction membership unlocks faction-specific missions that pay 25% more** or that different job types align with different factions.

The fix: weave faction awareness into the existing tutorial flow at natural points, without adding new tutorial rooms or mandatory content.

---

## 2. Changes to Existing Tutorial Content

### 2.1 Starter Quest Chain — New Step 5.5: "The Powers That Be"

Insert between existing Step 5 ("Check the Boards") and Step 6 ("Meet Your Ship"). The player has just discovered the mission and smuggling boards — this is the natural moment to explain *who gives the orders*.

**Step 5.5: "The Powers That Be"**

*Kessa (comlink):* "One thing you should know about this town, kid. Mos Eisley looks like chaos, but there are powers behind the scenes pulling the strings. The Empire runs the garrison. The Hutts run the underworld. The Rebellion is out there somewhere, recruiting. And then there are the guilds — Bounty Hunters, Traders, Mechanics, Slicers. Knowing who's who can mean the difference between getting paid and getting shot."

*Kessa (comlink):* "I put together a quick dossier for you. Take a look — type `factions` to see who's out there. When you're ready, come find me."

*Task:* Use the `factions` command (lists all 6 factions with one-line descriptions). Then talk to Kessa at the cantina.

*Kessa (in person, when talked to):* "So now you know the players. You don't have to pick a side — plenty of people stay independent and do just fine. But if you ever want to sign up with someone, they'll be watching what you do. Run Imperial missions and the Empire notices. Smuggle for the Hutts and they'll come knocking. The choice finds you, not the other way around."

*Teaches:* The `factions` command, that factions exist, that faction standing is driven by actions (not a menu choice), and that joining is optional but has benefits.

*Reward:* 50 credits. No faction rep — this is purely informational.

*Tracking:* `starter_quest.step = 5.5` (or renumber the chain to 9 steps total).

### 2.2 Starter Quest Chain — Step 7 Enhancement: "The Outskirts"

The existing Step 7 already sends the player to Sergeant Kreel at the Police Station. Add a line to Kessa's comlink that flags Kreel as the **Imperial** contact:

*Kessa (comlink, updated):* "One more thing. The Jundland Wastes outside town can be dangerous, but they're good hunting ground. **Sergeant Kreel at the Police Station is the local Imperial garrison's point man** — he might have some pest control work if you're looking to earn combat pay. Fair warning: working for Kreel means the Empire starts paying attention to you. That can be good or bad, depending on your perspective."

This costs zero implementation effort — it's just a text change in the comlink message data.

### 2.3 Training Grounds Hub Room — Faction Board

The hub room description already mentions "holoprojectors showing recruitment notices." Extend this with an interactive element:

Add a **Faction Recruitment Board** object to the Training Grounds hub room. When the player types `look board` or `read board`:

```
══════════════════════════════════════════════════════
 GALACTIC FACTIONS — KNOW YOUR OPTIONS
══════════════════════════════════════════════════════

 GALACTIC EMPIRE        Military order. Regular pay,
                        issued gear, strict hierarchy.
                        Talk to: Sgt. Kreel (Police Station)

 REBEL ALLIANCE         Fight the Empire. Scrappy resources,
                        covert ops, righteous cause.
                        Talk to: "Fulcrum" (finds you)

 HUTT CARTEL            Crime syndicate. High risk, high pay.
                        Debt-driven onboarding.
                        Talk to: Gep (The Grill)

 BOUNTY HUNTERS' GUILD  Independent contractors.
                        Eat what you kill.
                        Talk to: Ssk'rath (Bounty Office)

 TRADERS' COALITION     Legitimate commerce. Trade routes,
                        crafting, mercantile connections.
                        Talk to: Greelo (Trader's Hall)

 INDEPENDENT            No faction. Free agent. No obligations,
                        no exclusive perks. Default.

──────────────────────────────────────────────────────
 Use 'factions' to see standings and join requirements.
 Faction-specific missions pay 25% more than public jobs.
══════════════════════════════════════════════════════
```

This is a static room object — zero server logic, just a `look` description on an object in the hub room. The build script creates it.

### 2.4 Trader's Hall Elective — Step 5 Enhancement

The existing Trader's Hall Step 5 ("Putting It Together") summarizes income lanes. Extend Greelo's closing dialogue to mention factions:

*Greelo (updated closing):* "Missions, smuggling, bounties, crafting — those are your income lanes. But here's a tip most spacers miss: **if you join a faction, their mission board opens up to you, and those jobs pay 25% more than the public board.** The Empire, the Rebellion, the Hutts — they all have their own contracts. Even the guilds — Mechanics, Shipwrights, Medics — they give you discounts and restricted schematics. Worth thinking about once you've found your footing."

Again, this is a text change — no new rooms or logic.

---

## 3. Changes to Profession Chains

### 3.1 Chain Entry — Faction Context Brief

Each profession chain already has an entry requirement and a contact NPC. Add a **one-paragraph faction context brief** at the start of each chain that explains which faction this chain leads toward and what joining that faction means mechanically. This fires as a comlink or NPC dialogue when the chain starts.

**Smuggler's Run — Entry Brief:**
*Kessa:* "This job I'm about to offer you — it leads deeper into the Hutt Cartel's world. Complete it, and they'll consider you a friend. That means cheaper docking at Hutt-controlled ports, access to Cartel-only smuggling contracts that pay way better than the public board, and Gep starts treating you like family. Fair warning: the Empire won't like it."

**Hunter's Mark — Entry Brief:**
*Ssk'rath:* "This contract comes from the Bounty Hunters' Guild directly. Finish it clean and you earn Guild standing. That means access to restricted Guild contracts — higher-tier targets, better payouts. The Guild is neutral — no political baggage. We hunt for whoever pays."

**Artisan's Forge — Entry Brief:**
*Vek Nurren:* "This commission comes through the Traders' Coalition. Finish it, and you'll have their backing — access to restricted schematics, wholesale resource prices, and Coalition trade contracts across four planets. Good honest work, no blaster required."

**Rebel Cell — Entry Brief:**
*Fulcrum (comlink):* "What I'm about to ask you puts you on the Rebellion's radar — permanently. Complete this operation and the Alliance considers you a friend. That means Rebel-only missions, covert supply drops, and allies who'll watch your back. But the Empire will be watching too. Once you're in, there's no pretending you're neutral."

**Imperial Service — Entry Brief:**
*Sergeant Kreel:* "This assignment is off the books, but the Empire remembers its friends. Complete this and you'll have Imperial standing — access to military contracts, garrison supply discounts, and a name that opens doors at any Imperial checkpoint in the sector. Of course, the Rebellion will consider you an enemy. That's the price of order."

**Underworld — Entry Brief:**
*Gep:* "What I'm about to propose is not for the faint of heart. Do this, and you're in with the Cartel — Hutt patronage, protection, and the kind of contracts that make smuggling look like shuttle service. The pay is the best in the galaxy. The risk matches."

### 3.2 Chain Completion — Faction Join Prompt

This is already designed in §9.4 of `organizations_factions_design_v1.md`. On chain completion, the NPC offers:

> *"The [faction] has noticed your work. Would you like to formally join? (yes/no)"*

If the faction system isn't live yet (Priority B not shipped), this prompt fires but stores the intent in `attributes` JSON under `"faction_intent"`. When the faction system goes live, any player with a stored intent gets a comlink welcome message and auto-joins at Friendly standing.

```json
{
    "faction_intent": "rebel_alliance",
    "faction_intent_set_at": 1712700000
}
```

### 3.3 Chain Completion — Job Board Preview

After the join prompt, the NPC gives a **concrete example** of what faction membership unlocks:

*Kessa (Smuggler's Run complete):* "Now that you're in good with the Hutts, check `+smugjobs` — you'll see Cartel-exclusive runs marked with a gold border. They pay double the public board and the Hutts cover your docking fees at Nar Shaddaa."

*Kreel (Imperial Service complete):* "Report to the garrison mission board — `faction missions`. Imperial contracts pay well and come with equipment requisitions. You've earned that privilege."

This teaches the specific command (`faction missions` or the filtered `+smugjobs`) and sets the expectation that faction membership has tangible mechanical benefits.

---

## 4. New Tutorial Elective: "Galactic Factions" (Optional)

A **lightweight 8th elective module** in the Training Grounds, placed physically between the Trader's Hall and the Bounty Office. This is a 2-room information-only module with no combat and no skill checks — purely a briefing.

### 4.1 Room 1: "The Briefing Room"

A holoprojector room showing rotating faction emblems. A Protocol Droid (C-4PO or similar) serves as the guide.

*C-4PO:* "Welcome. I am programmed to provide impartial information about the major galactic factions operating in this sector. Shall we begin?"

The droid walks through each faction with a short interactive exchange. For each faction, the player gets:

1. **Who they are** (1–2 sentences)
2. **What they offer members** (mechanical: missions, discounts, gear)
3. **Who they oppose** (axis conflicts)
4. **How to join** (what actions earn standing)

The droid presents this conversationally, not as a wall of text. Each faction block is triggered by a `talk c-4po` prompt:

> *"The Galactic Empire maintains order through military strength. Members receive regular pay, issued equipment, and access to Imperial mission boards. However, working with the Empire puts you at odds with the Rebel Alliance. To earn Imperial favor, complete Imperial-flagged missions or assist Sergeant Kreel's operations."*

After all six factions, the droid summarizes:

> *"Additionally, six professional guilds operate across the sector: Mechanics, Shipwrights, Medics, Slicers, Entertainers, and Scouts. Guild membership provides skill training discounts and restricted schematics. Unlike factions, you may join up to three guilds simultaneously. Type `guild info` for details."*

### 4.2 Room 2: "The Job Board Simulator"

A demonstration room showing example job postings from each faction's board. The room has a mock mission board that displays:

```
══════════════════════════════════════════════════════
 FACTION JOB BOARD — EXAMPLES (Training Simulation)
══════════════════════════════════════════════════════

 [IMPERIAL]    Patrol Escort — Outer Rim Lane
               Escort Imperial supply convoy.
               Pay: 1,250cr  (25% faction bonus)
               Requires: Imperial standing

 [REBEL]       Intel Drop — Nar Shaddaa
               Deliver encrypted data to Rebel cell.
               Pay: 1,000cr  (25% faction bonus)
               Requires: Rebel standing

 [HUTT CARTEL] Spice Run — Kessel → Nar Shaddaa
               Tier 3 contraband, Hutt protection.
               Pay: 3,500cr  (Cartel exclusive)
               Requires: Hutt standing

 [GUILD]       Precision Repair — Coronet Shipyards
               Repair a damaged CEC freighter hull.
               Pay: 800cr  (Mechanics' Guild contract)
               Requires: Mechanics' Guild membership

 [PUBLIC]      Cargo Delivery — Tatooine → Corellia
               Standard freight run.
               Pay: 600cr
               Requires: None (available to all)
══════════════════════════════════════════════════════
```

The droid explains: *"As you can see, faction and guild contracts offer significantly better compensation. The tradeoff is commitment — factions expect loyalty, and your actions for one faction may upset another."*

**Completion flag:** `tutorial_electives.factions = "complete"`
**Reward:** 100 credits. No title (too small a module).

### 4.3 Implementation

2 new rooms in `build_tutorial.py`, 1 new NPC (C-4PO), 1 static board object. State tracked in `tutorial_electives.factions`. Total effort: ~100 lines in the build script, ~20 lines in the tutorial engine for step tracking. Drops with Tutorial Drop 5 or 6 (alongside other electives).

---

## 5. Integration with Planetary Discovery Quests

Each planet's discovery chain already introduces planet-specific NPCs. Add a **faction flavor line** to the contact NPC's opening comlink on first arrival:

**Nar Shaddaa (Mira Vel):**
> *"The Hutts run everything here. If you're looking to earn Cartel favor, this is the place to do it. Run their smuggling contracts and they notice fast."*

**Kessel (Foreman Crix):**
> *"The Empire controls the spice mines. Traders' Coalition runs the legitimate trade. And everyone else is trying to survive. Pick your side carefully — or don't pick one at all."*

**Corellia (Dockmaster Vaan):**
> *"Coronet City is officially Imperial territory, but the Corellian spirit is independent. The Traders' Coalition has their headquarters here, and the Rebel sympathizers... well, they're careful. CorSec keeps the peace."*

These are single-line additions to the existing planet discovery contact dialogue. Zero new logic.

---

## 6. Updated Implementation Plan

The original tutorial design has 12 drops. This addendum modifies existing drops and adds minimal new content:

| Drop | Change | Size |
|------|--------|------|
| 3 (Starter chain) | Add Step 5.5 "The Powers That Be" — `factions` command intro + Kessa dialogue. Enhance Step 7 Kreel intro with faction context. | Tiny |
| 5 (Trader's Hall) | Enhance Greelo's closing dialogue with faction/guild mention. | Tiny (text only) |
| 5 or 6 | New "Galactic Factions" elective (2 rooms, C-4PO, faction board). | Small |
| 8 (Planetary discovery) | Add faction flavor lines to 3 planet contact NPCs. | Tiny (text only) |
| 9–11 (Profession chains) | Add entry briefs (faction context), completion join prompts, and job board previews. | Small (dialogue data) |

Total additional effort: **~1 extra drop's worth of work**, mostly dialogue text and a 2-room elective module. The faction introduction is woven into the existing flow rather than bolted on.

---

## 7. Reward Table Update

| Activity | Credits | Other |
|----------|---------|-------|
| Step 5.5 "The Powers That Be" | 50 | Learns `factions` command |
| "Galactic Factions" elective | 100 | — |
| **Revised starter chain total** | **850** | (was 800) |
| **Revised all-electives total** | **2,550** | (was 2,450; +100 for factions elective) |
| **Revised grand total** | **~36,500** | (was ~36,350) |

Economic impact: negligible. +150cr total across the entire tutorial system.

---

## 8. Design Principles

**Show, don't gate.** Faction information is presented everywhere but required nowhere. A player who ignores factions entirely can play the full game as an Independent.

**Faction context at the moment of relevance.** Don't dump faction info in the core tutorial when the player is learning `look` and `attack`. Introduce factions when the player discovers the job board (Step 5.5), when they visit a training elective (faction board), and when they start a profession chain (entry brief). Each touchpoint adds a layer without overwhelming.

**Actions drive faction standing, not menu choices.** This is reinforced at every touchpoint: "the choice finds you, not the other way around." The profession chains are the natural on-ramp, and the completion join prompt is the formal commitment point. Until then, standing accumulates passively from gameplay.

**Every faction mention is paired with a concrete benefit.** "25% more pay," "exclusive missions," "issued equipment," "restricted schematics." New players need to understand *why* they'd join, not just *that* they can.

**No faction propaganda.** C-4PO is explicitly "programmed to provide impartial information." The tutorial system doesn't favor any faction — each is presented with its benefits and costs. The moral weight comes from the profession chains (branching choices, axis conflicts), not from the tutorial.

---

*End of addendum.*
*Reference: `tutorial_system_design.md`, `organizations_factions_design_v1.md` §9.4*
