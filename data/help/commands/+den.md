---
key: +den
title: +Den — Hutt Cartel Sabacc Den
category: "Commands: Criminal"
summary: Hutt cartel members establish illegal sabacc dens in cantinas. While a den is active, the sabacc house rake routes to the cartel's treasury. Requires rank 3+ and a 25,000-credit setup cost. No refund on abandonment.
aliases: [den]
see_also: [sabacc, +faction, +credits, +smuggle]
tags: [criminal, economy, faction, command]
access_level: 0
examples:
  - cmd: "+den"
    description: "Show this room's active den (if any) and your cartel's full den list."
  - cmd: "+den establish"
    description: "Claim this cantina as a cartel den (rank 3+ required, costs 25,000 credits)."
  - cmd: "+den abandon"
    description: "Abandon the cartel's den in this room. The setup stake is not returned."
---

Hutt cartel members can establish **sabacc dens** — unofficial
control points inside cantinas that redirect the house rake to
the cartel's treasury.

SYNTAX

  +den              Show this room's den (if any) and your
                    cartel's full den list.
  +den establish    Claim this room as a cartel den.
  +den abandon      Release the cartel's claim on this room.

REQUIREMENTS

  Faction       Hutt Cartel membership required.
  Rank          Cartel rank 3 or higher to establish.
  Location      You must be inside a cantina room.
  Cost          25,000 credits up-front setup stake (deducted
                from your personal account, not the cartel's).
  Refund        None — the stake is spent. Abandoning a den
                does not return any credits.

HOW DENS WORK

While a den is active in a cantina:

  1. Players run sabacc games there as normal (`sabacc`).
  2. The standard house rake (a percentage of each pot) that
     would otherwise disappear as a credit sink is instead
     routed to the **cartel organisation's treasury**.
  3. The cartel can then spend that treasury on operations,
     bribes, and territory influence via `+faction`.

Dens do not change sabacc gameplay for the players at the
table — only the destination of the house cut changes.

COMPETING DENS

Only one cartel can hold the den in a given cantina at a time.
A rival cartel can attempt to displace the existing den by
establishing their own — this triggers a contested-territory
event (not a direct command; the Director handles resolution).

STATUS

  +den        Displays:
              - Room: current den holder (cartel name) or NONE
              - Your cartel's active dens (location + age)

EXAMPLES

  +den
  → Room: No active den.
    Your cartel's dens: Hutt Boulevard Cantina (3d), The Slag Pit (1d)

  +den establish
  → Den established. 25,000 credits deducted.
  → The house rake in this cantina now flows to your cartel.

  +den abandon
  → Den abandoned. The 25,000-credit stake is not returned.

  +den           (non-cantina room)
  → Dens can only be established in cantinas.

CHEAT SHEET
  +den              = show den status for this room + your cartel
  +den establish    = open den here (rank 3+, 25,000cr; cantina only)
  +den abandon      = close den here (no refund)
