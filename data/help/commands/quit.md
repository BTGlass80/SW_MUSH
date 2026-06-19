---
key: quit
title: Quit — Disconnect from the Game
category: "Commands: System"
summary: Save your character and disconnect from Parsec. Your character remains in the game world in a sleep state until you return.
aliases: [logout, QUIT]
see_also: [+who, look]
tags: [system, session, command]
access_level: 0
examples:
  - cmd: "quit"
    description: "Save your character and disconnect."
  - cmd: "logout"
    description: "Alias — same as quit."
---

Saves your character and ends your session.

**What happens when you quit:**

Your character enters a sleep state at their current location. Other
players see `<Name> falls asleep here.` unless you are in a private
room. Your credits, inventory, and position are all preserved.

**Safe to quit anywhere.** There is no penalty for disconnecting
mid-scene — your character simply becomes inactive until you return.
Combat does not continue against sleeping characters.

**Aliases:** `quit`, `logout`, `QUIT`

Return any time by connecting and selecting your character. Use
`look` to reorient when you come back.
