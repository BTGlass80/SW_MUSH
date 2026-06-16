---
key: +ooc
title: +OOC — Local Out-of-Character Chat
category: "Commands: Social"
summary: Send an out-of-character message visible only to people in your current room.
aliases: ["@ooc"]
see_also: [say, emote, whisper, +channels]
tags: [social, ooc, local, command]
access_level: 0
examples:
  - cmd: "+ooc brb, phone call"
    description: "Tell everyone in the room you'll be right back."
  - cmd: "+ooc Can I +check Piloting here or do we need a ship?"
    description: "Ask an OOC rules question to people sharing the scene."
---

Send a local out-of-character (OOC) message. Only players in your current room
(or co-located wilderness tile) will see it. Useful for quick scene logistics,
rules questions, or flagging AFK without broadcasting to the whole game.

SYNTAX

  +ooc <message>

The message displays as:  [Local OOC] YourName: <message>

SCOPE

  +ooc is LOCAL — only your room.

  For game-wide OOC chat visible to all players, use the plain channel command:
    ooc <message>

  For new-player questions:
    newbie <message>

OUTPUT FORMAT

  [Local OOC] Kira Solenne: brb, phone
  [Local OOC] Tundra Vehn: ok

EXAMPLES

  +ooc BRB
  → "BRB" out-of-character to everyone in your room.

  +ooc Sorry, had to handle something — where were we?
  → Scene logistics note visible only to co-present players.

CHEAT SHEET
  +ooc <msg>  = local OOC (room only)
  ooc <msg>   = global OOC (all online players)
  newbie <msg>= new-player help channel
