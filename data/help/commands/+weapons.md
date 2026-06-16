---
key: +weapons
title: +Weapons — Weapon Reference
category: "Commands: Gear"
summary: List all weapons in the game with damage, skill, ranges, and cost.
aliases: [weapons, weaponlist, armory, +armory]
see_also: [+armor, +inv, +shop, +repair, equip]
tags: [weapons, gear, reference, command]
access_level: 0
examples:
  - cmd: "+weapons"
    description: "Show full weapon list with stats."
  - cmd: "weapons"
    description: "Alias — same as +weapons."
---

Display all weapons available in the game — damage dice, governing
skill, range bands, and whether the weapon is shop-purchasable or
must be crafted.

SYNTAX

  +weapons
  weapons
  armory

OUTPUT COLUMNS

  Weapon      Name of the weapon.
  Damage      Damage dice pool (e.g. 4D+1 for a DL-44).
  Skill       Governing skill used to attack (e.g. Blaster, Brawling).
  Short/Med/Long  Range in meters (ranged weapons). "Melee" for close-
              quarters weapons.
  Cost        NPC shop price in credits, or "craft" if it must be
              made at a crafting station.

EQUIPPED WEAPON

  The bottom of the list shows your currently equipped weapon and
  its condition bar.

RANGE BANDS

  Short   Full skill pool.
  Medium  -1D penalty.
  Long    -2D penalty.
  Extreme (beyond long range) is generally not possible without
  specialized equipment.

ACQUIRING WEAPONS

  shop / buy   Purchase shop-stocked weapons at NPC vendors.
  +craft       Craft weapons at a crafting station (crafted gear
               can exceed shop quality).
  loot         Salvage weapons from defeated enemies.

SEE ALSO

  +armor    List all armor.
  +inv      Check currently equipped weapon and carried gear.
  +repair   Repair your equipped weapon.
  equip     Equip a carried weapon.

EXAMPLES

  +weapons
  → Full weapon list. Your equipped weapon shown at the bottom.

CHEAT SHEET
  +weapons / weapons / armory   = weapon reference list
