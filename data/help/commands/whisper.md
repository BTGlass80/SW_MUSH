---
key: whisper
title: Whisper — Private In-Room Message
category: "Commands: Social"
summary: Send a private message to a player in the same room. Only you and the target see it. For cross-room messages use 'page'.
aliases: [wh, tell]
see_also: [say, emote, page, +who]
tags: [social, private, speech, command]
access_level: 0
examples:
  - cmd: "whisper Tundra = Meet me at bay 94."
    description: "Send a private whisper to Tundra (must be in the same room)."
  - cmd: "wh Tundra = I know who you are."
    description: "Short alias for whisper."
---

Send a private message to another player in the same room. Only
you and the target see the text. Anyone else in the room sees
nothing.

SYNTAX

  whisper <player> = <message>
  wh <player> = <message>
  tell <player> = <message>

The `=` separator is required.

OUTPUT

  You whisper to Tundra, "Meet me at bay 94."
  (Tundra sees) Valeska whispers, "Meet me at bay 94."
  (others see)  nothing

RANGE

Whisper only works when the target is in the **same room**. In
wilderness zones, both you and the target must be on the **same
co-located tile** — wilderness rooms are large and the command
respects adjacency.

For cross-room or cross-zone private messaging, use `page`.

ALIASES

  whisper   — full form
  wh        — short alias
  tell      — MUX-style alias

EXAMPLES

  whisper Tundra = The cargo is in hold three.
  → You whisper to Tundra, "The cargo is in hold three."

  wh Kira = Watch the barabel on your left.
  → You whisper to Kira, "Watch the barabel on your left."

  whisper Marko = He's one of ours.
  → Error if Marko is not in this room.

CHEAT SHEET
  whisper <name> = <msg>   = private same-room message
  wh <name> = <msg>        = short alias
  tell <name> = <msg>      = MUX-style alias
  page                     = cross-room private messaging
