---
key: +leave-master
title: +Leave-Master — Leave Your Master (Padawan-Side)
category: "Commands: Padawan-Master"
summary: Padawan voluntarily leaves their Master-Padawan bond. A reason is required; the dissolution is logged on both narrative records.
aliases: [leavemaster]
see_also: [+master, +bond, +release, +trials]
tags: [padawan, master, bond, jedi, command]
access_level: 1
examples:
  - cmd: "+leave-master Reassigned by the Council after the Geonosis campaign"
    description: "Leave your Master bond, recording the reason."
---

Voluntarily leave your Padawan-Master bond from the Padawan's side.
A reason is REQUIRED — this discourages impulsive breaks and creates
a narrative record. The dissolution is logged on both characters and
your Master is notified.

SYNTAX

  +leave-master <reason>     Dissolve your active bond (reason required).

WHY A REASON IS REQUIRED

  Bond dissolution is a significant narrative event in the Clone Wars.
  The reason is stored in both characters' narrative logs (visible to
  the Director AI) and shown to the Master if they are online.

WHAT HAPPENS

  - Bond is marked dissolved immediately.
  - Master is notified in real time (or sees it on next '+padawan').
  - Both sides receive a narrative log entry.
  - Your +master will show "no active Master bond" afterwards.

TO REFORM A BOND

  Use '+bond accept <master>' if your former Master (or a new one)
  proposes again.

EXAMPLES

  +leave-master The war has taken us down different paths
  → "You leave the bond with Obi-Wan. Reason: The war has taken..."
  → Obi-Wan (if online) hears the bond dissolve.

SEE ALSO

  +master       View your Master's status.
  +bond         Propose or accept a bond.
  +release      Master-side dissolution.
  +trials       Trial progress.

CHEAT SHEET
  +leave-master <reason>   Padawan leaves bond (reason required)
