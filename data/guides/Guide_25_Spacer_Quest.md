---
category: paths
order: 4
summary: "\"From Dust to Stars\" — the long arc from moisture farmer to ship captain."
tags: ["spacer", "quest", "ship", "captain", "tatooine", "story arc"]
---

# The Spacer Quest — "From Dust to Stars"

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.1 — revised against engine HEAD (June 2026)**

---

## How to Read This Guide

The Spacer Quest is a **30-step narrative quest chain** that takes a non-spacer character from "I just finished my tutorial chain" to "I own a beat-up Ghtroc 720 with a Hutt debt and a captain's chair." It's roughly **2-4 weeks of real-time play**, structured across five phases, narrated mostly by two recurring NPCs (Kessa on Tatooine and Mak Torvin from the back half onward).

This is the **canonical entry path** for new spacer characters in the Clone Wars era. If you've completed a non-spacer tutorial chain (Smuggler is the obvious match, but Bounty Hunter / Republic Officer / Republic Pilot also work) and you want to become a spacer rather than buy a ship outright, the Spacer Quest is the intended route. It pays out a ship, gives you contacts, and embeds you in the spacer community through narrative scenes rather than abstract progression.

If you only have ten minutes, read **§1 What the Spacer Quest Is** and **§4 The Five Phases**. The rest is detail for players actually running the quest.

This is a new guide. There was no earlier version.

---

## 1. What the Spacer Quest Is

The Spacer Quest is a **narrative onboarding for the spacer lifestyle**. The chain has 30 steps spread across 5 phases. Each step has:

- A **briefing** from one of the two recurring NPCs (Kessa for Phase 1, Mak Torvin from Step 8 onward).
- An **objective** — a specific in-game action: complete a mission, kill a hostile NPC, win at sabacc, use a specific command, talk to a specific NPC, etc.
- A **completion text** when you achieve the objective.
- A **reward**: credits, sometimes a title, sometimes a flag that affects later steps.
- A **hint** that surfaces in your `+spacerquest` display.

You don't pick which steps to do; they advance linearly. Step 1 must complete before Step 2 becomes available, and so on. The 5 phases gate progression: completing the last step of a phase (the **phase gate**) advances you to the next phase, which usually changes setting and stakes.

### What makes it different from the Tutorial Chain

The tutorial chain (Guide #16) is **structured, fast onboarding**: 4-6 steps, 15-25 minutes of real-time, contained within a starting zone, designed to teach commands and drop you into the live world.

The Spacer Quest is **live-world story over weeks**: 30 steps, no tutorial bubble, runs entirely in the regular game while you also do everything else. It's a long-running arc that you progress alongside missions, RP scenes, faction work, and ordinary play. The quest doesn't replace your normal life; it threads through it.

### Prerequisites and how it starts

To run the Spacer Quest your **starter (tutorial) chain must be complete** — internally that's `starter_quest >= 10` in your character state.

Once that prerequisite is met, the quest **starts itself the next time you talk to any NPC** (or arrive somewhere by booked passage). Kessa reaches you over the comlink with the opening briefing and Step 1 lands automatically — you don't have to "accept" anything. There is no chargen-time flag and no separate quest-giver hand-in.

The intended trigger is **Kessa in Chalmun's Cantina** in Mos Eisley — that's where the `+spacerquest` "not started yet" message points you, and her opening comlink is written in her voice. In practice, because the chain fires on your *first* post-tutorial NPC conversation, almost any newly-graduated character picks it up naturally while poking around Mos Eisley. If you genuinely never speak to another NPC, it simply never starts.

You can **abandon** the quest at any point with `+spacerquest abandon` (it asks for confirmation; you type `+spacerquest abandon confirm` to go through with it). Abandoning **resets your step progress to zero but you keep all credits, titles, and items** you've already earned — and you can restart the chain later by completing the trigger again in Mos Eisley. Abandonment is rare; most players who start the chain see it through. But if your character's direction shifts away from spacer-life, you can step out cleanly.

---

## 2. The Two NPCs

**Kessa** is the **Phase 1 mentor**. She's a mission-runner working freight and odd-jobs out of Mos Eisley, found in Chalmun's Cantina. She's pragmatic, slightly cynical, and treats you like a junior associate she's testing. All seven Phase 1 steps are briefed by Kessa, and she returns once more for Step 10 (the smuggling beat). She's the bridge from "you just finished onboarding" to "you understand how this world works."

After Phase 1, Kessa hands you off to:

**Mak Torvin** is the **Phase 2-5 mentor**. He's an aging human spacer who owns a beat-up Ghtroc 720 freighter called the **Rusty Mynock**, and he holds down Docking Bay 94 in Mos Eisley. He's the spacer veteran — knows everyone, has flown every route, has the kind of stories that suggest a much rougher life than he lets on. He briefs **22 of the 30 steps** (everything from Step 8 onward except Step 10, which Kessa takes).

Mak is also the **ship transfer endpoint**. At the Step 26 "Proposition," he offers to sell you the Rusty Mynock. The price: 8,000 cr to him directly, plus a 10,000-cr note he holds with **Drago the Hutt**. You become his successor — taking over not just his ship but his Hutt debt. This is the core narrative reveal: the ship comes with strings.

Both NPCs are full conversational characters. They respond to talk, they have personalities, they reference your previous actions. Players who treat them as flavor text get through the quest mechanically; players who actually RP with them get more out of the experience.

---

## 3. The Quest State

Your progress is tracked in your character's `attributes` blob under `spacer_quest`:

```
{
  "phase": 3,
  "step": 16,
  "started_at": <timestamp>,
  "completed_steps": [1, 2, 3, ..., 15],
  "flags": {
    "met_mak": true,
    "background_written": true,
    "sabacc_played": true,
    "borrowed_ship_id": 142,
    "ship_transferred": false,
    "debt_active": false,
    "chain_complete": false
  },
  "step_data": { ... }
}
```

You don't see this raw data, but you can check your progress at any time:

```
+spacerquest           — Show current objective and progress
+spacerquest log       — Show completed steps
+spacerquest abandon   — Abandon the quest (asks for confirmation)
```

The bare alias **`quest`** runs the same command, as do `+dusttostars` and `+fdts`. (Note: plain `+quest` is a *different* command — the personal-narrative quest umbrella — so use `+spacerquest` or `quest` for this chain.)

The `+spacerquest` output displays your current phase and phase name, your current step, the step's objective, the next-action hint (with live progress for counter steps), a progress bar toward 30, and the quest credits you've earned so far.

The quest also produces **`[COMLINK]` messages** when NPCs reach out to you. After completing a step, Kessa or Mak's voice arrives over your comlink with the next briefing. This makes the quest feel ambient — you're not always standing next to the NPC; sometimes they call you.

---

## 4. The Five Phases

Each phase has a theme, a setting, and a specific arc. The phase names below are exactly as the game prints them in your `+spacerquest` header.

### Phase 1 — Earning Your Keep (Steps 1-7)

**Mentor:** Kessa.
**Setting:** Tatooine, mostly Mos Eisley.
**Theme:** Prove you can hack the basic spacer life — missions, combat, a social roll, an investigation, sabacc.

**The seven steps:**

1. **The Routine Run.** Complete any mission from the mission board. Pay: 200 cr.
2. **Pest Control.** Defeat any hostile NPC in combat. Pay: 300 cr.
3. **Smooth Operator.** Talk to Kayson at the weapon shop and lean on his supplier — a Persuasion check vs Difficulty 10. Pay: 250 cr.
4. **The Investigation.** Go to the warehouse near the spaceport and search it for clues — a Search check vs Difficulty 12. Pay: 400 cr.
5. **Diversify.** Complete 3 missions of any type. Pay: 800 cr.
6. **The Sabacc Table.** Play a hand of sabacc in the cantina (`sabacc`). Pay: 100 cr.
7. **The Old Captain.** Travel to Docking Bay 94 in Mos Eisley and meet Mak Torvin for the first time. Pay: 250 cr.

By the end of Phase 1, you've completed a spread of basic spacer activities. You've earned **2,300 cr** from quest rewards plus whatever the underlying missions paid. And you've now met Mak Torvin, the spacer who'll guide you through the rest of the arc.

The Phase 1→2 gate is meeting Mak. Once you've talked to him in Docking Bay 94, the phase advances.

### Phase 2 — The Wider Galaxy (Steps 8-14)

**Mentor:** Mak Torvin (Kessa returns for Step 10).
**Setting:** Begins to expand beyond Tatooine — Nar Shaddaa enters the picture.
**Theme:** You're no longer just a Mos Eisley regular. You're a spacer-in-training who diversifies and travels.

**The seven steps:**

8. **The Powers That Be.** Learn who runs the galaxy — type `+factions`. Pay: 150 cr.
9. **Your First Bounty.** Complete a bounty (NPC or PC). Pay: 500 cr.
10. **The Underworld Economy.** Run a smuggling job (any tier). Briefed by Kessa. Pay: 400 cr.
11. **Write Your Story.** Write your character's background using `+background <text>`. Pay: 200 cr.
12. **Check Your Progress.** Check your advancement with `cpstatus` — see how close you are to your next Character Point. Pay: 100 cr.
13. **Passage to Nar Shaddaa.** Book passenger transit with `travel narshaddaa` from a Tatooine docking bay. Pay: 500 cr.
14. **Making Contacts.** On Nar Shaddaa, find and talk to three contacts: **Zekka Thansen**, **Renna Dox**, and **Doc Myrra**. Pay: 600 cr.

By Step 13 you've left Tatooine for the first time. The `travel <planet>` command is **passenger-only and works during Phases 2-3** — it lets you book transit without owning a ship yet. This is the system's gentle answer to "how do I get between planets before I have a ship?" You pay an NPC freighter crew, you ride along, and you arrive at the destination. Phase 2's only mandatory hop is `travel narshaddaa` (Step 13).

Phase 2 earns **2,450 cr** in quest rewards. The Phase 2→3 gate is making your three Nar Shaddaa contacts (Step 14). The quest now lives in the underworld and on the spacelanes.

### Phase 3 — Off-World (Steps 15-20)

**Mentor:** Mak Torvin.
**Setting:** Flying the four-planet circuit — Tatooine, Nar Shaddaa, Kuat, and Coruscant.
**Theme:** You're learning to fly. Mak lends you a ship for hands-on training.

**The six steps:**

15. **Your First Launch.** Mak lends you the Rusty Mynock — `board` it at Docking Bay 94, then `launch`. Pay: 200 cr.
16. **Star Roads.** Make a hyperspace jump to any destination (`hyperspace <destination>`). Pay: 300 cr.
17. **Touch Down.** Land on any planet other than Tatooine (`land`). Pay: 200 cr.
18. **Your First Cargo Run.** Buy and sell trade goods — buy at one port, sell at another (`trade list`, `trade buy`, `trade sell`). Pay: 500 cr.
19. **When Things Break.** Run ship diagnostics or attempt a repair with `damcon`. Pay: 300 cr.
20. **The Grand Tour.** Land on all four planets — Tatooine, Nar Shaddaa, Kuat, and Coruscant. Pay: 500 cr + the title **(Outer Rim Traveler)**.

Phase 3 is the **flying-training phase**, run in the loaner Rusty Mynock (see §8). You learn launch, hyperspace, landing, cargo trade, repair, and navigation. By Step 20 you've touched the whole galaxy map and earned your first title.

Phase 3 earns **2,000 cr** plus the (Outer Rim Traveler) title. The Phase 3→4 gate is completing the Grand Tour.

### Phase 4 — A Spacer's Reputation (Steps 21-26)

**Mentor:** Mak Torvin.
**Setting:** Broadly distributed — wherever your character has work.
**Theme:** Building reputation and expertise. Diversifying. Earning the right to take over a ship.

**The six steps:**

21. **The Artisan's Edge.** Craft any item using the crafting system (Guide #7). Pay: 400 cr.
22. **Faction Flavors.** Complete any 2 of: a bounty, a smuggling run, or a mission. Pay: 800 cr.
23. **Safe Harbor.** Check housing options (`housing`). Pay: 200 cr.
24. **The Crew Question.** Talk to **Renna Dox** at her Nar Shaddaa workshop about hiring crew. (The actual hiring is done later with the `hire` command at any spaceport; this step just completes when you talk to her.) Pay: 300 cr.
25. **The Big Job.** Complete all 3 of: a mission, a smuggling run, and a bounty. Pay: 1,000 cr + the title **(Versatile Spacer)**.
26. **The Proposition.** Talk to Mak Torvin at Docking Bay 94. (The pivotal scene — see §5.)

Step 26 is the **proposition scene**. Mak tells you he can't fly the Rusty Mynock anymore — his hands shake, his eyes aren't what they were. He'll sell her to you. The price: 8,000 cr to him as retirement money. Plus you take over his 10,000-cr debt to Drago the Hutt, paid off at 500 cr/week.

If you've been playing through the quest, you're typically in good shape on credits at this point (between quest rewards and your underlying mission/bounty income). The 8,000 cr to buy the ship is achievable; the 10,000-cr Hutt debt becomes part of your future.

Phase 4 earns **2,700 cr** plus the (Versatile Spacer) title. The Phase 4→5 gate is accepting the proposition.

### Phase 5 — The Captain's Chair (Steps 27-30)

**Mentor:** Mak Torvin, plus the Phase 5 contacts Lira Shan (Kuat) and Grek (Nar Shaddaa).
**Setting:** Kuat for the paperwork, Nar Shaddaa for the debt, your own cockpit for the finale.
**Theme:** Closing the deal. Becoming the captain. The chain ends with you owning the ship.

**The four steps:**

27. **The Down Payment.** Fly to **Kuat**, find **Lira Shan** at the Kuat Drive Yards commercial zone, and pay 8,000 cr to complete the ship paperwork. Lira is a KDY ship broker; she handles the title transfer. Cost: 8,000 cr from your wallet. On completion the Rusty Mynock becomes fully yours.
28. **Settling Accounts.** Fly to **Nar Shaddaa**, find **Grek** in the Undercity, and acknowledge the 10,000-cr note. This **activates the Hutt debt** in your character data: 10,000 cr principal, 500 cr/week payments. (This is the cost — no credit reward.)
29. **Name Her.** Use `+ship/rename <name>` to rename the Rusty Mynock to whatever you want. Pay: 500 cr + the title **(Captain)**.
30. **First Solo Jump.** Pilot your own ship through your first solo hyperspace jump. The chain completes when the jump succeeds. Final rewards: 1,000 cr, the title **(Spacer)**, +1 Character Point, and a grand-completion celebration.

By Step 30, you are:
- A licensed captain with a registered ship.
- A debtor to a Hutt for 10,000 cr at 500 cr/week.
- A spacer character with a complete narrative arc behind you, a recognized identity (titles (Outer Rim Traveler), (Versatile Spacer), (Captain), and (Spacer)), and a vessel.

Phase 5's net to your wallet is **+1,500 cr in rewards minus the 8,000 cr down payment**. The chain ends here. You're now in normal spacer life (Guide #5), with the Hutt debt as an ongoing economic constraint that motivates continued play — and the unlocked profession chains waiting for your next arc.

---

## 5. The Pivotal Scene — Step 26

Step 26 ("The Proposition") is the **narrative crux** of the entire chain. It's the moment where the quest reveals what it's actually been building toward.

When you finally meet Mak at Docking Bay 94 (he's been there throughout Phase 4, but Step 26 is when the offer comes), he speaks to you directly:

> Mak: "The Rusty Mynock — she's mine, but I can't fly her anymore. My hands shake, my eyes aren't what they were. I'll sell her to you for 8,000 credits — my retirement fund. The other 10,000 goes to Drago the Hutt who holds the note. You pay that off over time, 500 a week. Talk to Lira Shan on Kuat for the paperwork, then Grek on Nar Shaddaa about the debt. What do you say?"

This is the scene where you decide whether to become a spacer with strings attached or step away. Mechanically, accepting is just continuing the chain. Narratively, this is when your character commits to the spacer life — *including the debt*.

**The debt is real.** It's not flavor text. Once activated at Step 28, your character owes 10,000 cr, repaid at 500 cr/week. The repayment runs on a weekly tick:

- **Automatic weekly payments.** At each weekly cycle, if you have at least 500 cr the engine debits it, drops your principal, and Grek sends a comlink with your remaining balance.
- **Pay extra.** `debt pay <amount>` makes an additional payment toward the principal. Speeds up payoff.
- **Pay off entirely.** `debt payoff` clears the remaining balance in one transaction (you need the credits on hand). Recommended once you can afford it.
- **Miss a payment.** If your wallet is under 500 cr at the weekly tick, the payment misses and the missed counter ticks up. At **two** misses Grek sends a warning comlink; at **three** misses he warns that "Drago is sending someone." These are escalating narrative threats — keep current and you'll never find out how serious Drago is.

**Clear the debt and you earn the (Debt Free) title.** When your final payment lands, Grek closes the account and the game awards you the **(Debt Free)** title — the quiet capstone on the whole arc.

For most players, paying off the debt at the steady 500 cr/week pace takes around 20 weeks (10,000 ÷ 500); players doing well economically often pay extra to clear it sooner. Either way, it's ongoing motivation: you have a real reason to take that next mission, that next smuggling job, that next cargo run.

```
debt                    — Show current Hutt debt status
debt pay <amount>       — Make an extra payment
debt payoff             — Pay off entire balance
```

---

## 6. Rewards Across the Chain

The full quest-reward summary (credits granted by the chain itself, not counting the missions/bounties/jobs you ran to satisfy each step):

| Phase | Step Range | Quest Reward Credits | Notable Other Rewards |
|---|---|---|---|
| **1** | 1-7 | 2,300 cr | Meeting Mak Torvin |
| **2** | 8-14 | 2,450 cr | Background written; travel unlocked; Nar Shaddaa contacts |
| **3** | 15-20 | 2,000 cr | Flying training; visited 4 planets; **(Outer Rim Traveler)** |
| **4** | 21-26 | 2,700 cr | **(Versatile Spacer)**; the Proposition |
| **5** | 27-30 | 1,500 cr | The ship + **(Captain)** + **(Spacer)** + 1 CP |
| **Total** | 30 steps | **~10,950 cr** quest rewards | Ship + four titles + 1 CP + Hutt debt |

The quest rewards alone add up to about **10,950 cr** — meaningful for an early-career character. Note that at Step 27 you *spend* 8,000 cr on the down payment, so the chain's net contribution to your wallet is roughly 2,950 cr plus the ship. Beyond that, the underlying missions/bounties/smuggling jobs you completed to satisfy step requirements paid out their own rewards, so total wealth at chain completion varies widely depending on how much paying work you took on the way.

You finish with a ship, your remaining credits, a 10,000-cr debt, four titles, a Character Point, and a network of contacts you built across five phases.

---

## 7. Pacing — How Fast Should You Go?

The chain is designed to take **2-4 weeks of real-time** for a regularly-playing player (3-5 hours per week of active play). Steps don't have hard time-gates between them, but the underlying missions, combats, and travel naturally take time. A typical pace:

- **Week 1**: Phase 1 (Steps 1-7). Establishing yourself in Mos Eisley. Meeting Mak.
- **Week 2**: Phase 2 (Steps 8-14). Broadening your activities. Booking passage to Nar Shaddaa and making contacts.
- **Week 3**: Phase 3 (Steps 15-20). Flying lessons. The Grand Tour.
- **Week 4**: Phase 4-5 (Steps 21-30). Reputation building. The Proposition. Ship purchase. Captain.

**Faster players** can complete in 1-2 weeks if they grind. The objectives are achievable in compressed sessions. But the quest is more satisfying spread across more real-time — the relationships with Kessa and Mak develop better; the in-game story has time to breathe; the proposition scene lands harder because you've actually inhabited the character through weeks of play.

**Slower players** can take 6-8 weeks comfortably. Steps don't time out. Real-life intervenes, you're busy, you only log in twice a week — the quest is still there waiting for you. There's no rush.

The quest is intentionally **co-existable with everything else**. You're not removed from the world while doing it. You can take faction missions, run PvP combat, develop social relationships, do other arcs — the spacer quest threads through your ordinary play rather than replacing it.

---

## 8. The Borrowed Ship (Phases 3-4)

Phase 3 needs you to fly a ship to learn ship-handling commands, and you don't own one yet. The solution: **Mak lends you the Rusty Mynock**.

At Step 15 ("Your First Launch"), the game places Mak's own ship — a **Ghtroc 720 light freighter, the Rusty Mynock** — in Docking Bay 94 for you. It arrives a little worn (she's an old ship with a list of quirks), and she's yours to use for your training. You can `board` her, then `launch`, `hyperspace`, `land`, run cargo with `trade`, and patch her up with `damcon`.

Important truths about the loaner:

- **It's the same ship you eventually own.** This isn't a throwaway trainer that vanishes — the Rusty Mynock you fly from Step 15 is the very ship Mak sells you at Step 27. When you complete the down payment, the game simply transfers her registration to you; you keep flying the same vessel, now as owner.
- **You can't sell or transfer her while she's still Mak's.** Until the Step 27 paperwork lands she's flagged as a quest ship — the game blocks any attempt to sell or hand her off, with a note that she belongs to Mak until the chain's done.
- **Abandoning the quest reclaims her.** If you `+spacerquest abandon` while she's still the loaner (before Step 27), she's returned to Mak — the loaner ship is removed. If you've already bought her, she stays yours.

The narrative purpose: Mak lends you a ship for training because that's how spacers learn. The mechanical purpose: you practice flying the exact ship you're about to commit to owning — so by the time you sign for her, you already know her quirks.

---

## 9. Lira Shan and Grek — The Phase 5 Contacts

**Lira Shan** is a **Kuat Drive Yards ship broker**, found in the KDY commercial zone on Kuat. She's the registration official for your purchase: meticulous, professional, and she trusts the paperwork far more than the people signing it. At Step 27 she takes your 8,000 cr, files the title transfer, and the Rusty Mynock becomes legally yours. The scene is brief and transactional — exactly the kind of cool efficiency a KDY brokerage runs on.

**Grek** is the Hutt debt manager on **Nar Shaddaa**, working out of the Undercity for Drago the Hutt — he manages the note, tracks debtor payments, and handles the "encouragement" when payments slip. He's not threatening in the Step 28 scene (you're just accepting the debt, which is good for the Hutts), but his presence signals what this debt actually means: you'll be in business with the Hutts whether you like it or not. After Step 28, Grek is also who you deal with for the rest of the debt — his comlinks confirm your weekly payments and, eventually, close the account when you've paid it off.

Both characters remain in their locations after the chain. Lira stays on Kuat; Grek stays on Nar Shaddaa. You'll keep hearing from Grek every week until the debt is clear.

---

## 10. Common Pitfalls

**1. Using `+quest` instead of `+spacerquest`.** The bare `+quest` command is the *personal-narrative* quest umbrella — a different system. To see your spacer chain, type **`+spacerquest`** (or just `quest`, `+fdts`, or `+dusttostars`). If `+quest` shows you something unexpected, that's why.

**2. Trying to skip Step 26.** Some players, eager to own a ship, want to bypass the proposition and just buy one outright. The quest doesn't allow this — you can't advance past Phase 4 without accepting Mak's offer. If you want to skip the quest entirely, you can `+spacerquest abandon` and buy a ship from a shipyard instead; you keep any rewards you've already earned, but you forfeit the rest of the chain and its narrative.

**3. Underestimating the Hutt debt.** 10,000 cr at 500 cr/week is about 20 weeks of obligation. If you're earning comfortably, the 500 cr is manageable but real. Plan your finances so your wallet isn't sitting under 500 cr when the weekly tick hits.

**4. Trying to save up for the ship too early.** You don't need 8,000 cr until Step 27, which is well into Phase 5. Many players hoard credits early "just in case" and end up cash-starved at the wrong time. The chain pays out enough that you'll have the funds when you actually need them.

**5. Forgetting to keep 500 cr on hand once the debt is active.** After Step 28, payments auto-debit weekly. If your wallet is below 500 cr at the tick, the payment misses; two misses earns a warning comlink from Grek, three a sharper one. Keep a buffer between payouts.

**6. Treating the chain as just mechanical.** The chain is much richer if you RP it. Kessa and Mak are fully-realized NPCs, and the proposition scene is one of the best narrative moments in the game. Players who pose carefully through the briefings get a much better experience than players who just type the objective commands and move on.

---

## 11. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `+spacerquest` (or `quest`) | Show current quest objective and progress |
| `+spacerquest log` | Show completed steps |
| `+spacerquest abandon` → `+spacerquest abandon confirm` | Abandon the chain (resets step progress; keeps earned credits/titles/items) |
| `debt` | Show current Hutt debt status |
| `debt pay <amount>` | Make an extra payment |
| `debt payoff` | Pay off entire remaining balance |
| `travel <planet>` | Book passenger passage (Phases 2-3 only; e.g. `travel narshaddaa`) |
| `talk <npc>` | Talk to a quest NPC (`kessa`, `mak`, `kayson`, `renna`, `lira`, `grek`, …) |
| `+ship/rename <name>` | Name your ship (Step 29) |

Aliases for the quest command: `quest`, `+dusttostars`, `+fdts`. The plain `+quest` command is a *different* system (personal narrative quests).

---

## 12. Numbers At A Glance

| Quantity | Value |
|---|---|
| Total steps | 30 |
| Phases | 5 |
| Total quest reward credits | ~10,950 cr |
| Down payment (Step 27) | 8,000 cr |
| Hutt debt (Step 28) | 10,000 cr principal |
| Weekly debt payment | 500 cr |
| Typical chain completion time | 2-4 real-time weeks |
| Phase 1 mentor | Kessa (Chalmun's Cantina, Tatooine) |
| Phase 2-5 mentor | Mak Torvin (Docking Bay 94, Tatooine) |
| Step 27 broker | Lira Shan (Kuat Drive Yards) |
| Step 28 debt manager | Grek (Nar Shaddaa Undercity) |
| Ship received | Ghtroc 720 ("Rusty Mynock" by default) |
| Titles earned | (Outer Rim Traveler), (Versatile Spacer), (Captain), (Spacer); (Debt Free) on payoff |
| Bonus on completion | +1 Character Point |
| Prerequisite | Starter tutorial chain complete |

---

## 13. A Final Word

The Spacer Quest exists because the alternative — "buy a ship from the shipyard, you're now a spacer" — feels hollow. The system wants spacer characters to *come from somewhere*. Kessa's mentorship, Mak's friendship, the loaner-ship lessons, the proposition scene, the down payment to Lira on Kuat, the debt to Grek on Nar Shaddaa — these are the texture that makes your spacer character feel like a person who arrived at this life through real choices and real relationships, not just a sheet with a ship attached.

It also creates **ongoing motivation**. The Hutt debt isn't punitive; it's *purposeful*. Every week of paying it down is a small commitment to your spacer identity, and the (Debt Free) title at the end is the proof you saw it through. Players whose characters are deep in spacer play often look fondly at the debt as the thing that got them out into the world running missions and trading cargo in the first place. By the time you've paid it off, you're not just a spacer — you're an established spacer with stories, contacts, and a ship that's yours by hard-earned right.

If you're starting a new character and you want them to be a spacer: complete a non-spacer chain first (Smuggler is the natural choice, but any will do), then head into Mos Eisley and talk to Kessa in Chalmun's Cantina. The chain takes it from there. By the proposition scene 2-4 weeks later, you'll know the spacer world. By the time the debt's paid off, you'll be fully inhabited in the spacer identity. That's the system at its best — a quest that doesn't just hand you the role; it grows you into it.

---

*End of Guide #25 — The Spacer Quest "From Dust to Stars"*
