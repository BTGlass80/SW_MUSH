---
key: +who
title: +Who — Online Player List
category: "Commands: Social"
summary: Display all players currently logged in and in-game, with species and connection type.
aliases: [who, online, +online]
see_also: [+sheet, say, +where, channels]
tags: [social, info, online, command]
access_level: 0
examples:
  - cmd: "+who"
    description: "Show the online player list with name, species, and connection type."
  - cmd: "who"
    description: "Same as +who (bare alias)."
---

Display all players currently in-game. Shows each player's name,
species, connection type (WEB or TELNET), and worn title if they
have one equipped.

SYNTAX

  +who
  who
  online

OUTPUT FORMAT

  === Who's Online ===
    Tundra Vehn               Devaronian     [WEB] — Smuggler
    Kira Solenne              Human          [WEB]
    Marko Reyes               Zabrak         [TELNET]
    3 player(s) online.

  Columns:
    Name       Character name (30 chars wide)
    Species    Species from character sheet
    [Protocol] WEB = web-client session, TELNET = Telnet session
    Title      Worn title from the title system (if equipped)

NOTES

  • Only players who have entered the game world are listed.
    Accounts connected to the login screen are not shown.
  • Player count is shown at the bottom.
  • Titles are dim-formatted — the bracketed protocol appears first.

EXAMPLES

  +who
  → Full online list.

  who
  → Same (MUX-style alias).

CHEAT SHEET
  +who    = list online players (name / species / protocol / title)
  who     = same
  online  = same
