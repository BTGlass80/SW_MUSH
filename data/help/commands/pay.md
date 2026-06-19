---
key: pay
title: Pay — Transfer Credits to a Pirate Vessel
category: "Commands: Space"
summary: Pay a pirate's credit demand to end their pursuit and make them stand down. Use during an active space encounter when the pirate option to pay is available.
aliases: []
see_also: [encounter, respond, +pilot, +sensors]
tags: [space, economy, encounter, command]
access_level: 0
examples:
  - cmd: "pay Black Knife"
    description: "Transfer the demanded tribute to the Black Knife pirate vessel."
  - cmd: "respond 2"
    description: "If option 2 is 'Pay tribute' in an encounter, this also triggers payment."
---

Pay a tribute demand from a pirate vessel during a space encounter.
The pirates stand down and disengage once payment clears.

**Syntax:**

    pay <ship name>

**When to use:**

When an encounter presents a payment option (typically a pirate
intercept or customs shakedown), `respond <N>` for the pay option
routes through this same logic. You can also issue `pay <ship>`
directly if you know the name of the demanding vessel.

**Requirements:**

- You must be in open space (not docked).
- The named vessel must be actively demanding payment in your zone.
- Your character must have sufficient credits.

Credits are deducted via the `adjust_credits` funnel and logged.
If the demand is met, the pirate vessel withdraws.

**See also:** `encounter` to view active encounter details; `respond`
to select from all available options (combat, bluff, flee, pay).
