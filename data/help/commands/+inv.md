---
key: +inv
title: +Inv — Inventory
category: "Commands: Gear"
summary: Display your equipped items, carried inventory, and credit balance.
aliases: [inventory, inv, i, +inventory]
see_also: [+sheet, +shop, equip, wear, use]
tags: [gear, inventory, items, command]
access_level: 0
examples:
  - cmd: "+inv"
    description: "Show equipped gear, carried items, and credits."
  - cmd: "i"
    description: "Short alias — same as +inv."
  - cmd: "inventory"
    description: "Explicit long-form alias."
---

Display everything you are carrying and wearing, plus your
current credit balance.

SYNTAX

  +inv
  inventory
  inv
  i

OUTPUT SECTIONS

  Equipped:
    ⚔  DL-44 Blaster Pistol   dmg 4D+1
    🛡  Blast Vest

  Carried:
    ◆  Medpac x2
    ◆  Sealed Data Packet   [quest]

  Credits: 12,450 cr

SECTIONS

  Equipped    Items worn or wielded. Weapon slot (⚔) and
              armor slot (🛡). Damage shown for weapons.
  Carried     Items in your backpack/pouch, not equipped.
              Quest items show a [quest] slot tag.
  Credits     Current credit balance.

WEB CLIENT

Web-client users also see a structured inventory panel in the
sidebar that refreshes automatically after any item transaction.

RELATED COMMANDS

  +shop        Buy and sell items at vendors.
  equip        Equip a carried weapon or armor.
  wear         Alias for equip.
  use          Activate or consume a carried item.
  drop         Drop an item (where supported).

EXAMPLES

  +inv
  → Full inventory with equipped, carried, and credits.

  i
  → Same — shortest alias.

CHEAT SHEET
  +inv / i / inv / inventory   = show equipped + carried + credits
