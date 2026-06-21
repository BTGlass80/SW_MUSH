---
key: +scenes
title: +Scenes — Scene List
category: "Commands: RP"
summary: List your scenes or browse the public shared-scene archive.
aliases: [scenes]
see_also: [+scene, emote, say, +plots]
tags: [scene, rp, logging, archive, command]
access_level: 0
examples:
  - cmd: "+scenes"
    description: "List all your recent scenes, newest first."
  - cmd: "+scenes shared"
    description: "Browse the public shared-scene archive from all players."
  - cmd: "+scenes Ahsoka"
    description: "Browse shared scenes by the player named Ahsoka."
---

Show your scene history, or browse the public shared-scene archive.
Use +scene <id> to view the full pose log for any entry.

SYNTAX

  +scenes                  Your scene history (all statuses)
  +scenes shared           The public shared-scene archive (all players)
  +scenes <player>         A specific player's shared (public) scenes
  scenes                   Alias for +scenes

OUTPUT FORMAT (your history)

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
  COMPLETED   Scene has ended; private archive (only you can read it).
  SHARED      Published — any player can read the full log.

PRIVACY NOTE

  Only SHARED scenes appear in +scenes shared or +scenes <player>.
  A player's COMPLETED (private) scenes are never browsable by others.

EXAMPLES

  +scenes
  → Your scene history. Tap +scene <id> to read any log.

  +scenes shared
  → The public archive: all published scenes from every player.

  +scenes Greedo
  → Greedo's publicly shared scenes only.

  +scene 14
  → Read the full pose log for scene #14.

  +scene/share 14
  → Publish scene #14 to the shared archive.

CHEAT SHEET
  +scenes                  your scene history
  +scenes shared           public archive (all players)
  +scenes <player>         a player's shared scenes
  +scene <id>              read a scene log
  +scene/share <id>        publish a scene
