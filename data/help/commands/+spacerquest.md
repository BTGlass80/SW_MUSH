---
key: +spacerquest
title: "+spacerquest — From Dust to Stars Quest Chain"
category: "Commands: Quests"
summary: View your progress in the "From Dust to Stars" spacer quest chain — a 30-step new-player arc that ends with you owning a ship and a Hutt debt.
aliases: [quest, +dusttostars, +fdts]
see_also: [debt, travel, +quest, chain, +missions]
tags: [quests, onboarding, newbie, command]
access_level: 0
examples:
  - cmd: "+spacerquest"
    description: "Show your current quest step and overall phase progress."
  - cmd: "+spacerquest log"
    description: "Show the full step history — completed steps with their rewards."
  - cmd: "+spacerquest abandon confirm"
    description: "Reset the quest chain. Keeps credits/titles/items; loses step progress."
---

Displays your progress in **From Dust to Stars**, the 30-step new-player
quest chain. Complete it to earn your own ship and graduate to the
open profession tracks.

PREREQUISITE

You must finish the starter quest chain first (talk to Kessa in
Chalmun's Cantina). Once the starter chain clears, the spacer quest
starts automatically.

THE FIVE PHASES

  Phase 1  Earning Your Keep    (Steps  1-7)  — Ground work in Mos Eisley
  Phase 2  The Wider Galaxy     (Steps  8-14) — Broader jobs, deeper contacts
  Phase 3  Off-World            (Steps 15-20) — Multi-planet travel as a passenger
  Phase 4  A Spacer's Reputation(Steps 21-26) — Building your name
  Phase 5  The Captain's Chair  (Steps 27-30) — Getting your ship

WHAT YOU EARN

Each step grants credits. Phase completions grant bonus credits and
reputation. Phase 5 ends with you owning a Ghtroc 720 light freighter
and a 10,000 cr Hutt Cartel debt (see `help debt`).

FORMS

  +spacerquest            Show current phase, step, and objective.
  +spacerquest log        Full history of completed steps.
  +spacerquest abandon    Prompt to reset. Add 'confirm' to proceed.

NOTES

- Quest steps advance automatically via in-game triggers (talking to
  NPCs, completing missions, visiting locations). You don't manually
  accept or hand in steps — just play.
- Abandoning resets step progress but keeps all credits, titles, and
  items you earned. You can restart at Mos Eisley after abandoning.
- Phase 3 uses the `travel` command to move between planets (see
  `help travel`). Phase 4+ uses your own ship.

CHEAT SHEET
  +spacerquest          = view progress
  +spacerquest log      = view history
  +spacerquest abandon  = reset chain (asks for confirm)
  debt                  = check/pay your Hutt Cartel debt (Phase 5)
  travel <planet>       = book passage (Phases 2-3 only)
