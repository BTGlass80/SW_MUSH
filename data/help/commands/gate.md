---
key: gate
title: Gate — Answer Sister Vitha's Question
category: "Commands: Village Quest"
summary: Commit a numbered choice in Sister Vitha's gate dialogue (Village quest). Use after she presents the three-choice menu. Speak to her first with 'talk Vitha'.
aliases: []
see_also: ["+trial", "+village", accuse, path, talk]
tags: [village, quest, command]
access_level: 0
examples:
  - cmd: "gate 1"
    description: "Choose option 1 in Sister Vitha's gate dialogue."
  - cmd: "gate 2"
    description: "Choose option 2."
  - cmd: "gate 3"
    description: "Choose option 3."
---

Answer Sister Vitha's question at the Village Gate. Used during the
Village Quest (Jedi Force-sensitive path).

**Syntax:**

    gate <1|2|3>

**When to use:**

Speak to Sister Vitha at the Village Gate with `talk Vitha`. She
presents a three-choice menu. Use `gate 1`, `gate 2`, or `gate 3`
to commit your answer.

Outside of an active offer state (when Vitha hasn't asked you
anything yet), this command does nothing harmful — it tells you to
speak to Vitha first.

**See also:** `talk` to begin the gate dialogue; `+trial` for the
full Village trial system; `accuse` for the Trial of Insight;
`path` for the final path commitment.
