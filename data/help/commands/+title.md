---
key: +title
title: +Title — Character Titles
category: "Commands: Character"
summary: Buy and set decorative titles that appear before your character name. Titles are purchased with credits and held in your collection.
aliases: [title, "+titles", titles]
see_also: [+sheet, +finger, +credits, +finances]
tags: [title, character, cosmetic, credits, command]
access_level: 0
examples:
  - cmd: "+title"
    description: "Browse available titles and your collection."
  - cmd: "+title buy veteran_pilot"
    description: "Purchase the 'Veteran Pilot' title."
  - cmd: "+title set veteran_pilot"
    description: "Wear a title you already own."
  - cmd: "+title clear"
    description: "Remove your active title."
---

Browse, purchase, and equip decorative titles that appear before
your character name. Titles are cosmetic and purchased with credits.
Once bought, a title stays in your collection permanently.

SYNTAX

  +title                         Browse available titles and your collection
  +title buy <key>               Purchase a title (auto-equips it)
  +title set <key>               Equip a title you already own
  +title clear                   Remove your currently-worn title

HOW TITLES WORK

  Titles appear before your character's display name in the room
  and in other player-facing contexts. Each title has a credit
  cost shown in the catalog. Buying auto-equips the new title.
  You can switch between owned titles any time with +title set.

  Use the key shown in parentheses in the catalog listing for
  buy and set commands.

EXAMPLES

  +title
  → Shows the catalog (cost + key) and your collection.

  +title buy starfighter_ace
  → Purchases "Starfighter Ace" and equips it immediately.

  +title set bounty_hunter
  → Switches to "Bounty Hunter" if you already own it.

  +title clear
  → Removes your active title; your name appears without a prefix.

SEE ALSO

  +sheet     Your full character sheet.
  +finger    How others see your profile.
  +credits   Your current credit balance.

CHEAT SHEET
  +title                  browse catalog
  +title buy <key>        purchase + equip
  +title set <key>        equip owned title
  +title clear            remove active title
