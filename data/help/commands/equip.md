---
key: equip
title: Equip — Manage Weapons and Armor
category: "Commands: Gear"
summary: Equip and remove weapons and armor. Covers equip/wear/unequip/remove and all their aliases.
aliases: [wield, draw, wear, don, unequip, holster, sheathe, remove, doff]
see_also: [+inv, +weapons, +armor, buy, sell]
tags: [gear, weapons, armor, command]
access_level: 0
examples:
  - cmd: "equip blaster pistol"
    description: "Equip a DL-44 Blaster Pistol (partial name works)."
  - cmd: "wear blast vest"
    description: "Put on armor (same as equip for armor items)."
  - cmd: "unequip"
    description: "Holster your weapon."
  - cmd: "remove armor"
    description: "Take off your worn armor."
---

Arm yourself with a weapon and wear armor before entering combat.
Your equipment slots hold one weapon and one armor piece.

WEAPONS

  equip <weapon name>      — ready a weapon from inventory
  wield <weapon name>      — alias for equip
  draw <weapon name>       — alias for equip

  unequip                  — holster/put away your weapon
  holster                  — alias for unequip
  sheathe                  — alias for unequip

  Bare "equip" (no argument) shows the currently equipped weapon.

ARMOR

  wear <armor name>        — put on armor from inventory
  don <armor name>         — alias for wear

  remove armor             — take off worn armor
  doff                     — alias for remove armor

  Armor adds to Strength for soak rolls (WEG R&E p83).
  Bare "wear" (no argument) shows what you are currently wearing.

RESTRAINTS

  Bound or cuffed characters cannot change equipment until they
  break free (try `escape`).

FINDING ITEMS

  Use `+inv` to see what you are carrying and what is currently
  equipped. Use `+weapons` and `+armor` to browse available gear.
  Purchase items with `buy <name>` at a commissary or vendor.

CHEAT SHEET

  equip / wield / draw <weapon>   — ready a weapon
  wear / don <armor>              — put on armor
  unequip / holster / sheathe     — put weapon away
  remove armor / doff             — take off armor
