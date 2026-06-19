---
key: training
title: Training Grounds — Practice Facility
category: "Commands: Advancement"
summary: Access the Training Grounds — a persistent practice facility with modules covering each game system. Complete modules for credits and titles.
aliases: [+training]
see_also: [train, +cpstatus, +sheet, chain]
tags: [advancement, tutorial, command]
access_level: 0
examples:
  - cmd: "training"
    description: "Go to the Training Grounds hub."
  - cmd: "training list"
    description: "Show your progress across all available modules."
  - cmd: "training space"
    description: "Go directly to the Space Combat training module."
  - cmd: "training return"
    description: "Return to where you were before entering the Training Grounds."
  - cmd: "training skip"
    description: "Skip the core tutorial (experienced players who don't need the walkthrough)."
---

The Training Grounds are a persistent practice facility available
after you complete the core tutorial. Each module teaches a different
game system and earns rewards on completion.

**Syntax:**

    training                — go to the Training Grounds hub
    training list           — show progress across all modules
    training <module>       — jump directly to a module
    training return         — return to your previous location
    training skip           — skip the core tutorial

**Available modules:**

    space       — piloting, combat maneuvers, hyperspace
    combat      — ground combat, postures, wounds
    economy     — missions, bounties, trading, credits
    crafting    — resource gathering, schematics, crafting
    force       — Force powers and the Dark Side
    bounty      — bounty hunting and tracking
    crew        — NPC crew management and stations
    factions    — organizations, reputation, specializations

**Rewards:** Completing a module earns credits and a title. Check
`training list` to see which modules you've completed.

**Note:** `training` is the Training Grounds facility. To advance a
skill using Character Points, use `train <skill>` (a different
command — see `+help train`).

**See also:** `train` for CP-based skill advancement; `+cpstatus` for
your Character Point balance; `chain` to start a tutorial chain.
