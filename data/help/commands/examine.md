---
key: examine
title: Examine — Inspect an Object or Character
category: "Commands: Basic"
summary: Examine an object, NPC, character, or room detail to get a closer look. Delegates to the look-at system and also triggers Trial of Insight holocron fragment interactions.
aliases: []
see_also: [look, +inv, investigate]
tags: [basic, exploration, command]
access_level: 0
examples:
  - cmd: "examine crate"
    description: "Examine a crate in the current room — shows its description."
  - cmd: "examine Jex"
    description: "Examine another character or NPC in the room."
  - cmd: "examine fragment_1"
    description: "Listen to holocron fragment 1 (Trial of Insight, Village Council Hut)."
---

Examine an object, NPC, or character in your current room to get a
detailed description. Also works for your own inventory items.

**Syntax:**

    examine <target>

**Resolution order:**

1. NPCs and characters in the room (by name)
2. Room details / scenery keywords defined by the builder
3. Your own inventory items
4. Falls back to: `You don't see '<X>' here.`

**Trial of Insight (Village quest):**

Inside the Council Hut (after speaking with Elder Saro Veck), the
fragments are interactable:

    examine fragment_1    — listen to holocron fragment 1
    examine fragment_2
    examine fragment_3

Use `accuse fragment_<N>` to commit your answer after examining them.

**See also:** `look` for room descriptions; `+inv` for your full
inventory list; `investigate` for wilderness anomalies.
