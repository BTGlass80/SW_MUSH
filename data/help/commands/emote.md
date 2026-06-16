---
key: emote
title: Emote — Pose / Action
category: "Commands: Social"
summary: Describe an action your character performs. Your name is prepended automatically. Shortcut ':' (colon) for standard poses, ';' (semicolon) for possessive poses.
aliases: [":", "pose", "em"]
see_also: [say, whisper, +scene, +who]
tags: [social, roleplay, pose, command]
access_level: 0
examples:
  - cmd: "emote draws a blaster and levels it at the door."
    description: "Tundra draws a blaster and levels it at the door."
  - cmd: ":draws a blaster and levels it at the door."
    description: "Shortcut — colon prefix works identically."
  - cmd: ";'s hand trembles slightly."
    description: "Possessive pose — Tundra's hand trembles slightly."
---

Describe an action your character performs. Everyone in the room
sees the pose with your character name prepended.

SYNTAX

  emote <action>         Standard pose.
  :<action>              Colon-prefix shortcut (no space required).
  ;<action>              Semicolon-prefix possessive pose ('s).

OUTPUT FORMAT

  Standard:    Tundra draws a blaster and levels it at the door.
  Possessive:  Tundra's hand trembles slightly.

Write in **third person present tense** — the system prepends your
name, so don't start with it.

RIGHT:   emote draws a credit chip from her pocket.
WRONG:   emote Tundra draws a credit chip from her pocket.

SHORTCUTS

  :                  Alias for emote (most common)
  ;                  Possessive shortcut — prepends "'s" after name
  pose               Explicit long-form alias
  em                 Short alias

SCENE LOGGING

Poses are automatically logged when a scene is active in your
room (`+scene start`). The scene log preserves them in order
with timestamps.

EXAMPLES

  emote glances at the chrono on the wall.
  → Tundra glances at the chrono on the wall.

  :glances at the chrono on the wall.
  → Tundra glances at the chrono on the wall.

  ;'s eyes narrow.
  → Tundra's eyes narrow.

  pose spreads a star chart across the table.
  → Tundra spreads a star chart across the table.

CHEAT SHEET
  emote <text>   = third-person action pose
  :<text>        = shortcut for emote
  ;<text>        = possessive shortcut (adds 's after name)
  pose <text>    = same as emote
