---
key: lockpick
title: Lockpick — Pick a Private Housing Lock
category: "Commands: Housing"
summary: Attempt to pick the lock on a private housing room door. Requires Security skill. Only works on housing doors adjacent to your current location. Critical failure jams the lock.
aliases: [pick]
see_also: [housing, +home, skills, difficulty]
tags: [housing, espionage, security, command]
access_level: 0
examples:
  - cmd: "lockpick"
    description: "Attempt to pick the lock on the adjacent private housing door."
---

Attempt to pick the lock on a private housing room door adjacent
to your current location. Uses the Security skill (Dexterity).

SYNTAX

  lockpick

You do not specify a target — the command automatically targets
the first adjacent private housing door it can reach. If there is
no such door here, you get an error.

PREREQUISITES

  - You must be standing outside a private housing room (the door
    must be visible as an exit from your current room).
  - The room must be privately owned (housing created via `+home`).
  - The zone must not be SECURED (see below).

DIFFICULTY

  Zone type       Difficulty
  ─────────────────────────
  Contested       Very Difficult (25)
  Lawless         Difficult (20)
  Secured         Impossible — security seals prevent lockpicking

Secured zones include all official facilities, Republic outposts,
and major urban cores. Lockpicking works in contested wilderness
zones and lawless outskirt areas.

OUTCOMES

  Success            You enter the private room.
  Failure            You do not enter; may alert the owner.
  Critical failure   You jam the lock — the door cannot be picked
                     again until the owner resets it.

A failed attempt (not critical) does not prevent future attempts.
The owner receives an alert message if they are online.

CHEAT SHEET

  lockpick    = try the adjacent housing lock (Security vs 20–25)
