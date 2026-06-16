---
key: +scenes
title: +Scenes — Scene List
category: "Commands: RP"
summary: List all your recent scenes with status, type, location, and duration.
aliases: [scenes]
see_also: [+scene, emote, say]
tags: [scene, rp, logging, archive, command]
access_level: 0
examples:
  - cmd: "+scenes"
    description: "List all your recent scenes, newest first."
---

Show a compact list of all scenes you have participated in, with
their status, type, location, start time, and duration. Use
+scene <id> to view the full pose log for any entry.

SYNTAX

  +scenes
  scenes

OUTPUT FORMAT

  #  14  SHARED    Social      The Cantina Deal
             Mos Eisley Cantina  2026-06-15 21:10  47m

  #  13  COMPLETED  Action     Warehouse Ambush
             Docking Bay 94     2026-06-15 19:33  22m

  Columns:
    #id      Scene number — use with +scene <id>
    Status   ACTIVE / COMPLETED / SHARED
    Type     Social / Action / Plot / Vignette
    Title    Scene title (untitled if none set)
    Location Room name where scene was started
    Time     Scene start timestamp
    Duration Time from start to end

STATUS MEANINGS

  ACTIVE      Scene is currently recording in a room.
  COMPLETED   Scene has ended; private archive.
  SHARED      Published — any player can read the full log.

EXAMPLES

  +scenes
  → Your scene history. Tap +scene <id> to read any log.

  +scene 14
  → Read the full pose log for scene #14.

  +scene/share 14
  → Publish scene #14 to the shared archive.

CHEAT SHEET
  +scenes         list your scene history
  +scene <id>     read a scene log
  +scene/share    publish a scene
