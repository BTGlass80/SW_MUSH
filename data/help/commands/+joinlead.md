---
key: +joinlead
title: +Joinlead — Join a Combined Action
category: "Commands: Social"
summary: Acknowledge and join a leader's combined action to receive a Command skill bonus on your next roll.
aliases: [joinlead]
see_also: [+lead, +roll, +check]
tags: [joinlead, combined-action, group, skill, command]
access_level: 0
examples:
  - cmd: "+joinlead"
    description: "Join any active lead in your room."
  - cmd: "+joinlead Marak"
    description: "Join the lead offered by Marak specifically."
---

Acknowledge and join a combined action started by a leader in your
room. Once you join, the Command bonus applies to your next skill roll.

SYNTAX

  +joinlead
  +joinlead <leader name>

HOW IT WORKS

  When another player uses +lead and names you as a follower, their
  successful Command roll stages a bonus for you. Type +joinlead to
  receive and hold that bonus. The bonus is automatically applied to
  your very next +check or skill roll.

  The bonus expires after 60 seconds whether you join or not.

  If multiple leaders have offered you a lead, specify a name to pick
  one. With only one offer in the room, the name is optional.

EXAMPLES

  +joinlead
  → Accepts the active lead in your current room.

  +joinlead Kira
  → Joins specifically Kira's lead (if she has one staged for you).

SEE ALSO

  +lead    Start a combined action as the leader.
  +check   Roll a skill — the lead bonus applies here.
  +roll    Unmodified dice roll.

CHEAT SHEET
  +joinlead              join any lead in your room
  +joinlead <leader>     join a specific leader's lead
