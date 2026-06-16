---
key: say
title: Say — Speak Aloud
category: "Commands: Social"
summary: Speak aloud so everyone in the same room hears you. Shortcut ' or " followed immediately by your text.
aliases: ["'", '"']
see_also: [emote, whisper, +who, channels]
tags: [social, roleplay, speech, command]
access_level: 0
examples:
  - cmd: "say Nice ship. She yours?"
    description: "You say, \"Nice ship. She yours?\" — visible to everyone in the room."
  - cmd: "'Nice ship. She yours?"
    description: "Shortcut — leading single-quote works identically to 'say'."
  - cmd: "\"Nice ship. She yours?"
    description: "Leading double-quote also works as an alias for say."
---

Speak aloud. Everyone in the same room — and wilderness
co-located tile — sees what you say.

SYNTAX

  say <message>         Speak the message.
  '<message>            Single-quote shortcut (no space required).
  "<message>            Double-quote shortcut (same as above).

OUTPUT

  You say, "Nice ship. She yours?"
  (others see)  Tundra says, "Nice ship. She yours?"

Web client users also see speech appear in the Comms panel under
the IC (in-character) channel tab with the speaker's name.

SCENE LOGGING

If a scene is active in your room (started with `+scene`), spoken
lines are automatically captured in the scene log. The scene log
is viewable in the web client's scene panel and can be exported.

EAVESDROP WARNING

Players running the `eavesdrop` espionage ability can overhear
speech from an adjacent room. Assume anything said in a public
space may be overheard.

ROLEPLAY NOTES

  • Write in first person — the command adds your character name.
  • Use `emote` for actions (third person), `whisper` for private
    speech (same-room only).

EXAMPLES

  say May I see your cargo manifest?
  → You say, "May I see your cargo manifest?"

  'Ready when you are.
  → You say, "Ready when you are."

CHEAT SHEET
  say <text>   = speak aloud to the room
  '<text>      = shortcut alias
  "<text>      = same shortcut (double-quote)
