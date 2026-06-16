---
key: +repair
title: +Repair — Repair Equipped Weapon
category: "Commands: Gear"
summary: Repair your currently equipped weapon, restoring condition at a credit cost.
aliases: []
see_also: [+weapons, +inv, equip, +craft]
tags: [repair, weapon, condition, credits, command]
access_level: 0
examples:
  - cmd: "+repair"
    description: "Repair your currently equipped weapon."
---

Repair your currently equipped weapon, restoring its condition in
exchange for credits. The weapon must be equipped (not in your pack)
to be repaired.

SYNTAX

  +repair

WHAT HAPPENS

  1. The command checks your equipped weapon's current condition
     and maximum condition.
  2. It shows you the repair cost and how much the max condition
     will change.
  3. If you have enough credits, the repair is applied immediately.

OUTPUT (EXAMPLE)

  DL-44 Blaster Pistol: ████████░░ (8/10)
  Repair cost: 350 credits (max condition drops 10 -> 5)
  Your credits: 4,200
  DL-44 Blaster Pistol repaired! ██████████ (10/10)  (350 credits spent, 3,850 remaining)

CONDITION SYSTEM

  Weapons degrade with use. +repair restores current condition to
  its maximum, but LOWERS the maximum by 5 each time you repair.

  • A new weapon might be 10/10.
  • After one repair: max drops to 5. You can repair it back to 5/5.
  • At max condition 5 or below: the weapon is too worn out — it
    cannot be repaired further and should be replaced.

  Plan repairs carefully. High-quality crafted weapons resist
  degradation better than vendor-bought stock.

REPAIR COST

  Cost scales with the weapon's base value and current condition:
  cheaper to fix minor wear, expensive to fix a badly damaged piece.

CANNOT REPAIR

  • Nothing equipped: equip a weapon first.
  • Already at full condition: no repair needed.
  • Max condition ≤ 5: the weapon is worn out — replace it.
  • Insufficient credits: save up and try again.

SEE ALSO

  +weapons   List all weapons and see condition of your equipped one.
  +inv       Show your equipped weapon and carried gear.
  equip      Equip a weapon from your pack before repairing.
  +craft     Craft new weapons at a crafting station.

EXAMPLES

  +repair
  → Repairs equipped weapon; deducts credits immediately.

CHEAT SHEET
  +repair   = repair equipped weapon (costs credits; lowers max cond by 5)
