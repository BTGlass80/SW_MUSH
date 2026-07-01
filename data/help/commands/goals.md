---
key: goals
title: Goals — Your Active Objectives
category: "Commands: Info"
summary: Show your active questline step, accepted mission, and claimed bounty as text.
aliases: []
see_also: [+missions, bounties, +sheet]
tags: [info, goals, questline, mission, bounty, command]
access_level: 0
examples:
  - cmd: "goals"
    description: "List your current objectives — what you're working toward and how to act on it."
---

# Goals

`goals` prints your active objectives as text, the same information the GOALS
panel shows in the web client:

- **Questline** — your current tutorial/chain step and its objective.
- **Mission** — the one job you've accepted from the mission board (with its
  reward and the `+missions` verb to review it).
- **Bounty** — any contract you've claimed from the bounty board.

If you have nothing active, `goals` points you at `+missions` and `bounties` to
pick something up. Use `goals` any time you're not sure what to do next.
