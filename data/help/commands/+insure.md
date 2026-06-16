---
key: +insure
title: +Insure — Gear Insurance
category: "Commands: Economy"
summary: Buy a one-shot gear insurance policy that protects your loose loadout if you die in a lawless or contested zone. The policy is consumed on use. Equipped gear is always kept regardless. No cash payout — loadout protection only.
aliases: [insure, +insurance, insurance]
see_also: [+sheet, +inv, equip, wear, +credits]
tags: [economy, gear, death, command]
access_level: 0
examples:
  - cmd: "+insure"
    description: "Show your current coverage status, the premium cost, and what the policy protects."
  - cmd: "+insure buy"
    description: "Purchase a one-shot insurance policy (premium debited immediately)."
  - cmd: "+insure cancel"
    description: "Drop your current coverage. No refund."
---

`+insure` lets you buy a **one-shot gear insurance policy** that
protects your loose inventory if you die in a dangerous zone.

SYNTAX

  +insure          Show coverage status, premium cost, and
                   what the policy covers.
  +insure buy      Purchase a one-shot policy.
  +insure cancel   Drop current coverage (no refund).

WHAT IT PROTECTS

  Covered   Loose items in your inventory (anything not
            equipped or worn at the moment of death).
  Not needed Equipped and worn items are ALWAYS kept on
              death — insurance is not required for them.
  Not covered Credits, quest flags, reputation, skills.

There is no cash payout. The policy only prevents your
loose loadout from dropping to a lootable corpse.

HOW IT WORKS

  1. You buy a policy; premium is deducted immediately.
  2. You die in a lawless or contested zone.
  3. Instead of your loose inventory dropping as a loot
     pile, it stays on your character.
  4. The policy is **consumed** — you return to uninsured
     status and must buy again if you want continued cover.

If you die in a safe zone (occupied territory, cities),
gear does not drop regardless — the policy is not consumed
and remains active for your next dangerous-zone death.

PREMIUM COST

The premium is shown by `+insure` (no arguments). It is a
fixed credit sink scaled to typical loose-gear values.
The cost is tuned so that insuring cheap gear is not worth
it but protecting a high-value loadout is reasonable.

ANTI-EXPLOIT

Insurance covers your **loadout at time of death**, not
items transferred in from external storage just before dying.
A snapshot is taken at combat-start or hostile-entry to
prevent last-second gear-dump insurance abuse.

ALIASES

  +insure   =   insure   =   +insurance   =   insurance

EXAMPLES

  +insure
  → Coverage: NONE
    Premium: 800 credits
    Covers: loose inventory items on death in lawless/contested zones

  +insure buy
  → Policy purchased. 800 credits deducted.
  → Your loose gear is protected until your next dangerous-zone death.

  +insure       (with active policy)
  → Coverage: ACTIVE (one-shot remaining)
    Premium: 800 credits
    Covers: loose inventory on your next dangerous-zone death

  +insure cancel
  → Coverage cancelled. No refund.

CHEAT SHEET
  +insure           = show coverage status
  +insure buy       = buy one-shot policy (premium debited now)
  +insure cancel    = drop coverage (no refund)
  equip/wear        = equipped/worn gear is ALWAYS kept; no insurance needed
