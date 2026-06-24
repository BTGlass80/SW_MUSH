---
key: force
title: Force — Activate a Force Power
category: "Commands: Force"
summary: Activate a Force power by name. Force-sensitive characters only. Requires trained Control, Sense, or Alter dice — use +teach (from a Jedi Master) to develop those skills first.
aliases: [powers, forcepowers, listpowers, "+powers", "+forcepowers"]
see_also: [+forcestatus, +meditate, +teach, darkside, forcepoints]
tags: [force, jedi, powers, command]
access_level: 0
examples:
  - cmd: "force control_pain"
    description: "Activate Control Pain — reduce wound penalties temporarily. Requires Control."
  - cmd: "force life_sense"
    description: "Sense the life force of all beings in the room. Requires Sense."
  - cmd: "force danger_sense"
    description: "Feel danger before it arrives. Grants a combat initiative bonus this round."
  - cmd: "force affect_mind <target>"
    description: "Suggest a course of action (light side). Requires Control + Sense."
  - cmd: "force telekinesis <target>"
    description: "Move objects or targets with the Force. Requires Alter."
  - cmd: "powers"
    description: "List all Force powers available to you and which are locked (need more training)."
---

Use the Force to activate a power by name.

## Usage

```
force <power name>
force <power name> <target>
powers
```

## Requirements

- You must be **Force-sensitive** (chose this at character creation).
- The power's required skill (Control, Sense, or Alter) must be **1D or higher**.
- If your Force skills are all 0D — as they are for new characters — use **+teach**
  to find a Jedi Master who can train you. Force skills cannot be raised with the
  `train` command.

## Available Powers

Type `powers` to see which powers you qualify for and which are locked. Powers
require specific skill combinations:

| Power           | Skills Required        | Effect |
|-----------------|------------------------|--------|
| control_pain    | Control                | Ignore wound penalties temporarily |
| accelerate_healing | Control             | Speed natural recovery |
| danger_sense    | Sense                  | Initiative bonus in combat |
| life_sense      | Sense                  | Detect living beings in room |
| sense_force     | Sense                  | Detect other Force-sensitive beings |
| sense_lie       | Sense                  | Detect deception in a target's speech |
| telekinesis     | Alter                  | Move objects / disarm targets |
| affect_mind     | Control + Sense        | Suggest a course of action (light side) |
| dominate_mind   | Control + Sense        | Coerce a target's will (dark side — earns DSP) |
| heal_another    | Control + Alter        | Heal a target's wounds |

## Dark Side Risk

Some powers — `dominate_mind` and others — earn **Dark Side Points** (DSP) on
use. Accumulating DSP leads to Director-triggered bounty hunters and Dark Side
consequences. Check `+forcestatus` to monitor your DSP total.

## Force Points

Spending a Force Point on a Force roll doubles your dice pool for that roll. Force
Points restore slowly. See `+forcestatus` for your current total.
