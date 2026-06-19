---
key: ;
title: Semipose — Name-Glued Emote
category: "Commands: Social"
summary: Emit a room emote with your character's name fused directly to the text (no space). Used for possessives and flowing action descriptions.
aliases: [semipose]
see_also: [emote, say, whisper, +scene]
tags: [social, roleplay, emote, command]
access_level: 0
examples:
  - cmd: ";'s lightsaber hums softly."
    description: "Displays: Tundra's lightsaber hums softly."
  - cmd: ";grabs the crate and shoves it aside."
    description: "Displays: Tundraggrabs the crate and shoves it aside. — note: no space, so include one if needed."
  - cmd: "semipose 's blaster clears leather in a blur."
    description: "Same as ; — displays Tundra's blaster clears leather in a blur."
---

The semipose (`;`) fuses your character name directly to whatever
follows — no space is inserted. This is used for possessives and
action lines where the name flows into the text.

**Syntax:**

    ;<text>            → <Name><text>
    semipose <text>    → <Name><text>

**Comparison with emote:**

    :draws their blaster.     → Tundra draws their blaster.   (emote — space after name)
    ;'s hand twitches.        → Tundra's hand twitches.       (semipose — no space, possessive)

**Broadcast:** visible to all characters in the same room, filtered
to co-located players in wilderness areas.

**See also:** `emote` (`:`) for standard action lines with a space
after the name; `say` for speech.
