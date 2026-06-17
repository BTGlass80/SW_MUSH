---
category: paths
order: 4
summary: "\"From Dust to Stars\" — the long arc from moisture farmer to ship captain."
tags: ["spacer", "quest", "ship", "captain", "tatooine", "story arc"]
---

# The Spacer Quest — "From Dust to Stars"

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

The Spacer Quest is a **30-step narrative quest chain** that takes a non-spacer character from "I just finished my tutorial chain" to "I own a beat-up Ghtroc 720 with a Hutt debt and a captain's chair." It's roughly **2-4 weeks of real-time play**, structured across five phases, narrated by two recurring NPCs (Kessa on Tatooine and Mak Torvin everywhere else).

This is the **canonical entry path** for new spacer characters in the Clone Wars era. If you've completed a non-spacer tutorial chain (Smuggler is the obvious match, but Bounty Hunter / Republic Officer / Republic Pilot also work) and you want to become a spacer rather than buy a ship outright, the Spacer Quest is the intended route. It pays out a ship, gives you contacts, and embeds you in the spacer community through narrative scenes rather than abstract progression.

If you only have ten minutes, read **§1 What the Spacer Quest Is** and **§4 The Five Phases**. The rest is detail for players actually running the quest.

This is a new guide. There was no earlier version.

---

## 1. What the Spacer Quest Is

The Spacer Quest is a **narrative onboarding for the spacer lifestyle**. The chain has 30 steps spread across 5 phases. Each step has:

- A **briefing** from one of the two recurring NPCs (Kessa in Phase 1, Mak Torvin from Phase 1 onward).
- An **objective** — a specific in-game action: complete a mission, kill a hostile NPC, win at sabacc, use a specific command, talk to a specific NPC, etc.
- A **completion text** when you achieve the objective.
- A **reward**: credits, sometimes a title, sometimes a flag that affects later steps.
- A **hint** that surfaces in your `+quest` display.

You don't pick which steps to do; they advance linearly. Step 1 must complete before Step 2 becomes available, and so on. The 5 phases gate progression: completing the last step of a phase (the **phase gate**) advances you to the next phase, which usually changes setting and stakes.

### What makes it different from the Tutorial Chain

The tutorial chain (Guide #16) is **structured, fast onboarding**: 4-6 steps, 15-25 minutes of real-time, contained within a starting zone, designed to teach commands and drop you into the live world.

The Spacer Quest is **live-world story over weeks**: 30 steps, no tutorial bubble, runs entirely in the regular game while you also do everything else. It's a long-running arc that you progress alongside missions, RP scenes, faction work, and ordinary play. The quest doesn't replace your normal life; it threads through it.

### Prerequisites

To start the Spacer Quest:
- Your starter (tutorial) chain must be complete (`starter_quest >= 10` in your state).
- You must talk to **Kessa** in the Mos Eisley spaceport area to begin.

There's no chargen-time flag. The quest is **opt-in** — characters who never speak to Kessa never start the quest. New players who want to be spacers seek her out; players who don't want the arc simply skip her.

You can also **abandon** the quest at any point with `+quest abandon` (with confirmation), losing all current progress. Abandonment is rare — most players who start the chain see it through to completion. But if your character's direction shifts away from spacer-life, you can step out cleanly.

---

## 2. The Two NPCs

**Kessa** is the **Phase 1 mentor**. She's a Twi'lek mission-runner on Tatooine who's been working freight and odd-jobs out of Mos Eisley for years. She's pragmatic, slightly cynical, and treats you like a junior associate she's testing. Phase 1's 7 steps are all briefed by Kessa. She's the bridge from "you just finished onboarding" to "you understand how this world works."

After Phase 1, Kessa hands you off to:

**Mak Torvin** is the **Phase 2-5 mentor**. He's an aging human spacer who owns a beat-up Ghtroc 720 freighter called the **Rusty Mynock**. He's the spacer veteran — knows everyone, has flown every route, has the kind of stories that suggest a much rougher life than he lets on. He briefs **22 of the 30 steps** (everything from Step 8 onward).

Mak is also the **ship transfer endpoint**. At Step 26, he offers to sell you the Rusty Mynock. The price: 8,000 cr to him directly, plus a 10,000-cr note he holds with **Drago the Hutt**. You become his successor — taking over not just his ship but his Hutt debt. This is the core narrative reveal: the ship comes with strings.

Both NPCs are full conversational characters. They respond to talk, they have personalities, they reference your previous actions. Players who treat them as flavor text get through the quest mechanically; players who actually RP with them get more out of the experience.

---

## 3. The Quest State

Your progress is tracked in your character's `attributes` blob under `spacer_quest`:

```
{
  "phase": 3,
  "step": 14,
  "started_at": <timestamp>,
  "completed_steps": [1, 2, 3, ..., 13],
  "flags": {
    "met_mak": true,
    "background_written": true,
    "sabacc_played": true,
    "borrowed_ship_id": null,
    "ship_transferred": false,
    "debt_active": false,
    "chain_complete": false
  }
}
```

You don't see this raw data, but you can check your progress at any time:

```
+quest                 — Show current objective and progress
+quest log             — Show completed steps
+quest abandon         — Abandon the quest (with confirmation)
```

The `+quest` output displays your current phase, your current step, the step's objective, the next-action hint, and approximately how much of the chain you've completed.

The quest also produces **`[COMLINK]` messages** when NPCs reach out to you. After completing a step, Kessa or Mak's voice arrives over your comlink with the next briefing. This makes the quest feel ambient — you're not always at the NPC; sometimes they call you.

---

## 4. The Five Phases

Each phase has a theme, a setting, and a specific arc.

### Phase 1 — Earning Your Keep (Steps 1-7)

**Mentor:** Kessa.
**Setting:** Tatooine, mostly Mos Eisley.
**Theme:** Prove you can hack the basic spacer life — missions, combat, social rolls, investigation, diversification.

**The seven steps:**

1. **The Routine Run.** Complete any mission from the mission board. Kessa wants to see you finish a basic job. Pay: 200 cr.
2. **Pest Control.** Defeat any hostile NPC in combat. Pay: 200 cr.
3. **Smooth Operator.** Pass a Persuasion or Bargain check. Pay: 200 cr.
4. **The Investigation.** Pass a Search or Streetwise check. Pay: 200 cr.
5. **Diversify.** Complete a mission of a different type than your first. Pay: 300 cr.
6. **The Sabacc Table.** Play a game of sabacc (the cantina gambling system). Pay: 200 cr + sabacc winnings/losses.
7. **The Old Captain.** Travel to Docking Bay 94 in Mos Eisley and meet Mak Torvin for the first time. Pay: 500 cr.

By the end of Phase 1, you've completed 7 specific kinds of activities. You're roughly 1-2 weeks into the quest. You've earned ~1,700 cr from quest rewards plus whatever the underlying missions paid. And you've now met Mak Torvin, the spacer who'll guide you through the rest of the arc.

The Phase 1→2 gate is meeting Mak. Once you've talked to him in Docking Bay 94, the phase advances.

### Phase 2 — Wider Horizons (Steps 8-13)

**Mentor:** Mak Torvin.
**Setting:** Begins to expand beyond Tatooine — Nar Shaddaa enters the picture.
**Theme:** You're no longer just a Mos Eisley regular. You're a spacer-in-training who travels.

**The six steps:**

8. **The Powers That Be.** Demonstrate the faction system — `faction list` and choose to engage with one. Pay: 300 cr.
9. **Your First Bounty.** Complete a bounty (NPC or PC). Pay: 500 cr.
10. **The Underworld Economy.** Run a smuggling job (any tier). Pay: 800 cr.
11. **Write Your Story.** Write your character's background using `+background <text>`. Pay: 200 cr.
12. **Check Your Progress.** Examine your character sheet (`+sheet`) — a self-awareness moment. Pay: 100 cr.
13. **Passage to Nar Shaddaa.** Use `travel nar_shaddaa` to book passage as a passenger on an NPC vessel. Pay: 500 cr.

By Step 13, you've left Tatooine for the first time. The `travel <planet>` command is Phase-2-specific — it lets you book passenger transit without owning a ship yourself. This is the system's gentle answer to "how do I travel between planets when I don't have a ship yet?" You pay an NPC freighter, you arrive, and you're at the next planet.

The Phase 2→3 gate is arriving on Nar Shaddaa. The quest now lives in the underworld.

### Phase 3 — Becoming a Spacer (Steps 14-20)

**Mentor:** Mak Torvin.
**Setting:** Nar Shaddaa primarily; also Kessel, Corellia, return to Tatooine.
**Theme:** You're learning to fly. You're given a borrowed ship for hands-on training.

**The seven steps:**

14. **Making Contacts.** Talk to specific NPCs on Nar Shaddaa to establish you've arrived properly. Pay: 300 cr.
15. **Your First Launch.** Take off in a borrowed ship — Mak loans you a starter vessel for the next several steps. Pay: 400 cr.
16. **Star Roads.** Complete an astrogation check for a hyperspace jump. Pay: 500 cr.
17. **Touch Down.** Land at a destination. Pay: 300 cr.
18. **Your First Cargo Run.** Complete a legitimate cargo trade (buy at one port, sell at another). Pay: 800 cr.
19. **When Things Break.** Repair a damaged system on the borrowed ship using `damcon` or `+ship/repair`. Pay: 400 cr.
20. **The Grand Tour.** Visit each of the four planets via hyperspace. Pay: 1,000 cr.

Phase 3 is the **flying-training phase**. The borrowed ship — typically a lower-tier freighter — is yours to use for these steps. You're learning launch/land, astrogation, cargo trade, repair, navigation. By Step 20, you've touched the entire galaxy map.

The Phase 3→4 gate is completing the Grand Tour. You've now been everywhere a small ship can practically go.

### Phase 4 — A Spacer's Reputation (Steps 21-26)

**Mentor:** Mak Torvin.
**Setting:** Broadly distributed — wherever your character has work.
**Theme:** Building reputation and expertise. Diversifying. Earning the right to take over a ship.

**The six steps:**

21. **The Artisan's Edge.** Craft any item using the crafting system (Guide #7). Pay: 400 cr.
22. **Faction Flavors.** Complete any 2 of: a bounty, a smuggling run, or a mission. Pay: 800 cr.
23. **Safe Harbor.** Check housing options (`housing` command). Pay: 300 cr.
24. **The Crew Question.** Hire an NPC crew member or recruit a player crew. Pay: 500 cr.
25. **The Big Job.** Complete all 3 of: mission, smuggling, bounty (single comprehensive demonstration). Pay: 1,200 cr + title "Versatile Spacer".
26. **The Proposition.** Talk to Mak Torvin at Docking Bay 94. (The pivotal scene — see §5.)

Step 26 is the **proposition scene**. Mak tells you he can't fly the Rusty Mynock anymore — his hands shake, his eyes aren't what they were. He'll sell her to you. The price: 8,000 cr to him as retirement money. Plus you take over his 10,000-cr debt to Drago the Hutt, paid off at 500 cr/week.

If you've been playing through the quest, you're typically around 8,000-12,000 cr at this point (between quest rewards and your underlying mission/bounty income). The 8,000 cr to Mak is achievable. The 10,000-cr Hutt debt becomes part of your future.

The Phase 4→5 gate is accepting the proposition.

### Phase 5 — The Captain's Chair (Steps 27-30)

**Mentor:** Mak Torvin (final-arc scenes), plus introductions to Lira Shan (Corellia) and Grek (Nar Shaddaa).
**Setting:** Corellia for the paperwork, Nar Shaddaa for the debt, Tatooine for the takeover.
**Theme:** Closing the deal. Becoming the captain. The chain ends with you owning the ship.

**The four steps:**

27. **The Down Payment.** Travel to Corellia, find **Lira Shan** at Coronet Starport, and pay 8,000 cr to complete the ship paperwork. Lira is a CEC-aligned registration officer; she handles the title transfer. Pay (from your wallet): 8,000 cr. Reward: ship registration document.
28. **Settling Accounts.** Travel to Nar Shaddaa, find **Grek** (the Hutt debt manager), and acknowledge the 10,000-cr note. This **activates the Hutt debt** in your character data: 10,000 cr principal, 500 cr/week payments, accumulating until paid off. Reward: nothing (this is the cost).
29. **Name Her.** Use `+ship/rename <name>` to rename the Rusty Mynock to whatever you want. The default is "Rusty Mynock" but you can change it (and most players do). Pay: 300 cr.
30. **First Solo Jump.** Pilot your new ship through your first solo hyperspace jump. The chain completes when the jump succeeds. Final reward: title "Captain" + chain_complete flag + a small grand-completion celebration.

By Step 30, you are:
- A licensed captain with a registered ship.
- A debtor to a Hutt for 10,000 cr at 500 cr/week.
- A spacer character with a complete narrative arc behind you, a recognized identity, and a vessel.

The chain ends here. You're now in normal spacer life (Guide #5), with the Hutt debt as an ongoing economic constraint that motivates continued play.

---

## 5. The Pivotal Scene — Step 26

Step 26 ("The Proposition") is the **narrative crux** of the entire chain. It's the moment where the quest reveals what it's actually been building toward.

When you finally meet Mak at Docking Bay 94 (he's been there throughout Phase 4, but Step 26 is when the offer comes), he speaks to you directly:

> Mak: "The Rusty Mynock — she's mine, but I can't fly her anymore. My hands shake, my eyes aren't what they were. I'll sell her to you for 8,000 credits — my retirement fund. The other 10,000 goes to Drago the Hutt who holds the note. You pay that off over time, 500 a week. Talk to Lira Shan on Corellia for the paperwork, then Grek on Nar Shaddaa about the debt. What do you say?"

This is the scene where you decide whether to become a spacer with strings attached or step away. Mechanically, accepting is just continuing the chain. Narratively, this is when your character commits to the spacer life — *including the debt*.

**The debt is real.** It's not flavor text. Once activated at Step 28, your character has 10,000 cr to pay back at 500 cr/week. You can:

- **Make weekly payments.** Auto-debits from your wallet each week. Easy if you're earning enough.
- **Pay extra.** `debt pay <amount>` makes an additional payment. Speeds up payoff.
- **Pay off entirely.** `debt payoff` pays the remaining balance in one transaction. Recommended once you have the funds.
- **Miss payments.** If you can't make a weekly payment, the engine notes the miss. Multiple consecutive misses trigger Hutt-aligned NPC consequences — increased patrol scrutiny, lower Hutt reputation, eventually credit-collector NPCs come looking for you. The Hutts are not patient creditors.

For most players, paying off the debt takes **3-5 real-time months** at the steady 500 cr/week pace. Players who are doing well economically often pay extra to clear it sooner. Either way, it's an ongoing motivation: you have a real reason to take that next mission, that next smuggling job, that next cargo run.

```
debt                    — Show current Hutt debt status
debt pay <amount>       — Make an extra payment
debt payoff             — Pay off entire balance
```

---

## 6. Rewards Across the Chain

The full reward summary:

| Phase | Step Range | Quest Reward Credits | Notable Other Rewards |
|---|---|---|---|
| **1** | 1-7 | ~1,700 cr | Meeting Mak Torvin |
| **2** | 8-13 | ~2,400 cr | Background written; travel system unlocked |
| **3** | 14-20 | ~3,700 cr | Hands-on flying training; visited 4 planets |
| **4** | 21-26 | ~3,200 cr + "Versatile Spacer" title | The Proposition scene |
| **5** | 27-30 | 300 cr | The Rusty Mynock + Captain title |
| **Total** | 30 steps | ~11,300 cr quest rewards | Ship + Captain title + Hutt debt |

The quest rewards alone add up to about 11,300 cr — meaningful for an early-career character. Beyond that, the underlying missions/bounties/smuggling jobs you completed to satisfy step requirements paid out their own rewards (often 1,000-5,000 cr per major step), so total wealth at chain completion is typically 20,000-30,000 cr.

The 8,000 cr you spend on the down payment leaves you with a meaningful reserve. You start your captain's career with a ship, your remaining credits, a 10,000-cr debt, and a network of contacts you built across 5 phases.

---

## 7. Pacing — How Fast Should You Go?

The chain is designed to take **2-4 weeks of real-time** for a regularly-playing player (3-5 hours per week of active play). Steps don't have hard time-gates between them, but the underlying missions, combats, and travel naturally take time. A typical pace:

- **Week 1**: Phase 1 (Steps 1-7). Establishing yourself in Mos Eisley. Meeting Mak.
- **Week 2**: Phase 2 (Steps 8-13). Broadening your activities. Booking passage to Nar Shaddaa.
- **Week 3**: Phase 3 (Steps 14-20). Flying lessons. The Grand Tour.
- **Week 4**: Phase 4-5 (Steps 21-30). Reputation building. The Proposition. Ship purchase. Captain.

**Faster players** can complete in 1-2 weeks if they grind. The objectives are achievable in compressed sessions. But the quest is more satisfying spread across more real-time — the relationships with Kessa and Mak develop better; the in-game story has time to breathe; the proposition scene lands harder because you've actually inhabited the character through weeks of play.

**Slower players** can take 6-8 weeks comfortably. Steps don't time out. Real-life intervenes, you're busy at work, you only log in twice a week — the quest is still there waiting for you. There's no rush.

The quest is intentionally **co-existable with everything else**. You're not removed from the world while doing it. You can take faction missions, run PvP combat, develop social relationships, do other arcs — the spacer quest threads through your ordinary play rather than replacing it.

---

## 8. The Borrowed Ship (Phase 3)

Phase 3 needs you to fly a ship to learn ship-handling commands. You don't have one yet. The solution: **the borrowed ship**.

When Phase 3 begins, Mak introduces you to a friend who'll lend you a small freighter — typically a Ghtroc 720 or comparable starter vessel — for the duration of training. The ship is yours to use for Phase 3 steps; you can `board`, `pilot`, `launch`, `land`, `hyperspace`, and `damcon` on it.

The borrowed ship has a few important constraints:
- **It's not yours.** You can't customize it permanently. You can't sell it. You can't make it your home base.
- **You can't take it into serious combat.** The lender expects it back undamaged.
- **It returns when Phase 3 ends.** When you advance to Phase 4 (or sooner if you complete all Phase 3 steps), the ship reverts to its owner.

This is a teaching scaffold, not a free ship. The narrative purpose: Mak knows people who'll lend you a ship for training because that's how spacers learn. The mechanical purpose: you need to practice flying before you commit to owning.

Some players try to "keep" the borrowed ship by lingering in Phase 3. The chain doesn't force you to advance, but Mak's NPC begins to nudge you forward after some delay. Eventually, the ship is recalled regardless.

---

## 9. Lira Shan and Grek — The Phase 5 Contacts

**Lira Shan** at Coronet Starport on Corellia handles the title transfer. She's a CEC paperwork official — meticulous, friendly, knows ship records. She takes your 8,000 cr, files the registration, hands you the title. The scene is brief and professional; the title is real (mechanically, it's an attribute on your character).

**Grek** is the Hutt debt manager on Nar Shaddaa. He's a Twi'lek who works for Drago the Hutt — manages the note collection, tracks debtor payments, handles enforcement when needed. He's not threatening in the proposition scene (you're just accepting the debt; that's good for the Hutts), but his presence signals what this debt actually means. You'll be in business with the Hutts whether you like it or not.

After Step 28, both characters remain in their locations. You can visit Lira to look up ship records (yours or others'). You can visit Grek to make extra debt payments or to ask about the Hutt economy generally. They're persistent characters who continue to exist in the world, just no longer driving quest steps.

---

## 10. Common Pitfalls

**1. Trying to skip Step 26.** Some players, eager to own a ship, want to bypass the proposition and just buy one outright. The quest doesn't allow this — you can't advance past Phase 4 without accepting Mak's offer. If you want to skip the quest entirely, you can `+quest abandon` and buy a ship from a shipyard, but you forfeit all the rewards and the narrative.

**2. Underestimating the Hutt debt.** 10,000 cr at 500 cr/week is 20 weeks of obligation. If you're earning 1,500 cr/week from regular play, the 500 cr is manageable but real. Players who plan their finances poorly and miss payments find themselves facing Hutt-aligned NPC pressure — which is RP gold but also stressful. Plan ahead.

**3. Trying to save up for the ship before Step 27.** You don't need 8,000 cr until Step 27, which is well into Phase 5. Many players save up early "just in case" and find themselves with extra credits at the wrong time. The chain pays out enough that you'll have the funds when you need them.

**4. Forgetting to make weekly payments.** Once the debt activates at Step 28, weekly payments auto-debit. If your wallet is below 500 cr at the weekly tick, the payment misses. After 2-3 missed payments, consequences begin. Always keep at least 500 cr in your wallet between mission payouts.

**5. Treating the chain as just mechanical.** The chain is much richer if you RP it. Kessa is a fully-realized NPC; Mak Torvin is, too. The proposition scene is one of the best narrative moments in the game. Players who pose carefully through the briefings and reactions get a much better experience than players who just type the objective commands and move on.

---

## 11. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `+quest` (or `quest`) | Show current quest objective and progress |
| `+quest log` | Show completed steps |
| `+quest abandon` | Abandon the chain (with confirmation; loses all progress) |
| `debt` | Show current Hutt debt status |
| `debt pay <amount>` | Make an extra payment |
| `debt payoff` | Pay off entire remaining balance |
| `travel <planet>` | Book passage as a passenger (Phases 2-3 only) |
| `talk kessa` (or `mak`, `lira`, `grek`) | Talk to a quest NPC |

---

## 12. Numbers At A Glance

| Quantity | Value |
|---|---|
| Total steps | 30 |
| Phases | 5 |
| Total quest reward credits | ~11,300 cr |
| Down payment (Step 27) | 8,000 cr |
| Hutt debt (Step 28) | 10,000 cr principal |
| Weekly debt payment | 500 cr |
| Typical chain completion time | 2-4 real-time weeks |
| Phase 1 mentor | Kessa (Tatooine) |
| Phase 2-5 mentor | Mak Torvin (Tatooine) |
| Ship received | Ghtroc 720 ("Rusty Mynock" by default) |
| Final title | Captain |
| Prerequisite | Starter tutorial chain complete |

---

## 13. A Final Word

The Spacer Quest exists because the alternative — "buy a ship from the shipyard, you're now a spacer" — feels hollow. The system wants spacer characters to *come from somewhere*. Kessa's mentorship, Mak's friendship, the borrowed ship lessons, the proposition scene, the down payment to Lira, the debt to Grek — these are the texture that makes your spacer character feel like a person who arrived at this life through real choices and real relationships, not just a sheet with a ship attached.

It also creates **ongoing motivation**. The Hutt debt isn't punitive; it's *purposeful*. Every week of paying it down is a small commitment to your spacer identity. Players whose characters are deep in spacer play often look fondly at the debt as the thing that got them out into the world running missions and trading cargo in the first place. By the time you've paid it off (months later), you're not just a spacer — you're an established spacer with stories, contacts, and a ship that's yours by hard-earned right.

If you're starting a new character and you want them to be a spacer: complete a non-spacer chain first (Smuggler is the natural choice, but any will do), then find Kessa in Mos Eisley and start the quest. By the time you're at the proposition scene 2-4 weeks later, you'll know the spacer world. By the time you've paid off the debt months after that, you'll be inhabited fully in the spacer identity. That's the system at its best — a quest that doesn't just hand you the role; it grows you into it.

---

*End of Guide #25 — The Spacer Quest "From Dust to Stars"*
