---
key: +pvp
title: +Pvp — PvP Flag
category: "Commands: Combat"
summary: Opt in to open PvP in contested zones, allowing combat without a challenge/accept exchange.
aliases: [pvp]
see_also: [+combat, +spar, +soak, +threat]
tags: [pvp, combat, flag, consent, command]
access_level: 0
examples:
  - cmd: "+pvp on"
    description: "Flag yourself open to PvP in contested zones."
  - cmd: "+pvp off"
    description: "Remove your PvP flag (subject to cooldown after a fight)."
  - cmd: "+pvp status"
    description: "Check whether your flag is on and if a cooldown is active."
---

Toggle your PvP flag to opt into open player-versus-player combat
in contested zones without needing a challenge/accept exchange first.

SYNTAX

  +pvp on           Flag yourself open to PvP
  +pvp off          Unflag (5-minute cooldown after a fight)
  +pvp status       Show your current flag and cooldown
  +pvp              Alias for +pvp status

RULES

  - Flag does NOT override SECURED zones. Jedi Temple, Senate, and
    other secured areas remain absolute no-combat zones regardless
    of PvP flag.
  - If EITHER you OR your target is flagged, combat can proceed
    without challenge/accept (consensual-by-flag model).
  - After your flag is used in a fight, you cannot unflag for
    5 minutes — anti-tag-and-flee protection.
  - The flag applies only to CONTESTED zones (wilderness regions
    marked as contested, certain city districts, etc.).

STANDARD CONSENT

  Without a PvP flag, combat between players requires:
    1. Attacker types: challenge <player>
    2. Defender types: accept

  The flag lets two willing combatants skip that exchange. It
  does not allow one-sided no-consent attacks.

EXAMPLES

  +pvp on
  → You are now flagged open to PvP in contested zones.

  +pvp off
  → Removes the flag immediately if no cooldown is active.
    If you just fought, you must wait 5 minutes.

  +pvp status
  → Shows your flag state and remaining cooldown (if any).

SEE ALSO

  +combat    Combat help and standard encounter rules.
  +spar      Consensual practice combat — always safe.
  +threat    Your threat level in contested regions.

CHEAT SHEET
  +pvp on       open to PvP in contested zones
  +pvp off      remove flag (5-min cooldown after fight)
  +pvp status   check flag and cooldown
