---
key: +threat
title: +Threat — Area Threat Band
category: "Commands: World"
summary: Show the danger rating of the current area and how tough the hostiles are.
aliases: [threat]
see_also: [+weather, look, +combat, +region]
tags: [threat, difficulty, zone, danger, command]
access_level: 0
examples:
  - cmd: "+threat"
    description: "Show the threat band for your current location."
  - cmd: "threat"
    description: "Alias — same as +threat."
---

Display the THREAT BAND of your current location — a rating that
tells you how dangerous the hostiles are in this area.

SYNTAX

  +threat
  threat

OUTPUT

  Threat band: Deep Wilds (level 4/4)
  This region is hostile territory. Expect well-armed adversaries
  and minimal support.

THREAT BANDS

  Frontier (1/4)
    Newbie-friendly territory. Hostiles are weak and few. Mistakes
    are survivable. Good for new characters.

  Settled (2/4)
    Standard mid-level content. Moderately dangerous. Bring backup
    or solid gear.

  Contested Marches (3/4)
    Serious hostiles. Experienced characters and team tactics
    recommended. Expect resistance.

  Deep Wilds (4/4)
    Highest danger. Only well-equipped, experienced characters
    should venture here alone.

THREAT VS. SECURITY

  Threat is NOT the same as security. They are independent:

  • Security (Secured / Contested / Lawless) controls whether
    combat and PvP are allowed here.
  • Threat controls how powerful the NPCs and encounters are.

  A Secured city can still sit in Contested Marches territory.
  A Lawless zone can be a safe Frontier area.

  Use `look` to see both the security level and the off-default
  threat band in the room header.

SEE ALSO

  +weather   Check local time and active weather.
  look       Room header shows threat band (non-Frontier areas).
  +pvp       Opt-in to PvP (Contested zones only).
  +region    Information about the current region.

EXAMPLES

  +threat
  → "Threat band: Settled (level 2/4)"

CHEAT SHEET
  +threat / threat   = area danger rating
