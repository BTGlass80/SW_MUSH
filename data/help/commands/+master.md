---
key: +master
title: +Master — View Bonded Master Status
category: "Commands: Padawan-Master"
summary: Padawan-side bond status — shows your bonded Master's name, online status, bond age, and Weight of War sense.
aliases: [master]
see_also: [+padawan, +bond, +trials, +leave-master, +forcestatus]
tags: [padawan, master, bond, jedi, command]
access_level: 1
examples:
  - cmd: "+master"
    description: "Show your current Master's status, bond age, and their Weight of War sense through the bond."
---

Show your bonded Master's status through the Force bond. Jedi Padawans
use this to check their Master's presence, bond age, and emotional
weight without needing to be in the same room.

SYNTAX

  +master

WHAT IT SHOWS

  - Master's name and online/offline status.
  - How long the bond has been active (days / hours / minutes).
  - Weight of War sense through the bond: your Master's current
    Weight tier and its descriptor, felt across the connection.
  - Trials passed so far (of 5 required for knighting).

REQUIREMENTS

  - You must have an active Padawan bond (created via +bond accept
    or @bond by staff).
  - Jedi-only: only Force-sensitive characters hold bonds.

NOT SEEING YOUR MASTER?

  If you have no active bond, +master will say so. If you ARE a
  Master (no Padawan-side bond), it will suggest +padawan instead.

EXAMPLES

  +master
  →  Master: Obi-Wan Kenobi  (online)
  →  Bonded: 3 days ago
  →  Through the bond: Burdened — a dull ache, present but manageable.
  →  Trials passed: 2 of 5

SEE ALSO

  +padawan      Master-side view of Padawan(s).
  +bond         Propose or accept a bond.
  +trials       Full Trial progress display.
  +leave-master Voluntarily dissolve the bond (Padawan-side).
  +forcestatus  Your Force Points and powers.

CHEAT SHEET
  +master   show bonded Master's status (Padawan use)
