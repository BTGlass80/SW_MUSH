---
key: +reputation
title: +Reputation — Faction Standings
category: "Commands: Factions"
summary: View your reputation standings with all factions, or a detailed view for one faction.
aliases: [+rep, reputation]
see_also: [+faction, +sheet, +who]
tags: [faction, reputation, standing, command]
access_level: 0
examples:
  - cmd: "+reputation"
    description: "Show your standing with all factions at a glance."
  - cmd: "+rep"
    description: "Short alias for +reputation."
  - cmd: "+reputation republic"
    description: "Detailed breakdown of your Republic reputation."
---

Display your faction reputation standings. Reputation determines your rank
within each faction, affects NPC attitudes toward you, unlocks faction-specific
shops and missions, and can grant discounts or penalties on purchases.

SYNTAX

  +reputation               — overview of all faction standings
  +reputation <code>        — detailed view for one faction

FACTION CODES

  republic    Galactic Republic
  cis         Confederacy of Independent Systems (CIS)
  jedi        Jedi Order
  hutt        Hutt Clans
  mandalore   Mandalorian clans
  bounty      Bounty Hunters' Guild
  criminal    Criminal underworld

REPUTATION OVERVIEW

  Each faction entry shows your current reputation score, tier label,
  and progress toward the next tier. Example:

    Republic    ████████░░  72  — Ally
    Jedi Order  ██████░░░░  54  — Trusted
    Hutt Clans  ████░░░░░░  38  — Neutral

REPUTATION TIERS

  Reviled → Hostile → Unfriendly → Neutral → Friendly → Trusted → Ally → Champion

  Higher tiers unlock:
  • Faction missions and exclusive contracts
  • NPC dialogue options and quest lines
  • Shop discounts and restricted item access

HOW REPUTATION CHANGES

  • Complete faction missions (+mission, +quest)
  • Fulfill contracts and favors
  • Territory influence shifts affect regional faction standings
  • Certain story events adjust reputation for multiple factions at once

EXAMPLES

  +reputation
  → See all your faction standings at once.

  +reputation hutt
  → Detailed Hutt Clans breakdown: score, tier, history, nearby NPCs.

CHEAT SHEET
  +reputation        = all faction standings
  +reputation <code> = one faction detail
  +rep               = short alias
