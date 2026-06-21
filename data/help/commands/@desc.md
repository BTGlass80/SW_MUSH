---
key: "@desc"
title: "@desc — Set Your Character Description"
category: "Commands: Character"
summary: Set your character's description — the text other players see when they 'look' at you.
aliases: ["@describe"]
see_also: [look, +sheet, +finger]
tags: [character, roleplay, description, command]
access_level: 1
examples:
  - cmd: "@desc A lean Twi'lek woman with copper lekku and sharp eyes."
    description: "Set your character description."
  - cmd: "@desc"
    description: "View your current description without changing it."
  - cmd: "@describe A tall Mirialan with green-gold skin and geometric tattoos."
    description: "Alias — identical to @desc."
---

Set the description other players see when they 'look <your name>' at you.
Your description appears in the look output and in '+finger' profiles.

SYNTAX

  @desc <description>    Set description to the given text (2000 char max).
  @desc                  Show your current description without changing it.

TIPS

  Write in third person ("A lean Twi'lek woman…") — the game prepends
  your name when displaying to others.

  Keep it to 1-3 sentences covering appearance, posture, and one or
  two notable details. Long descriptions are legal but slow to read.

  You can update your description at any time; there is no cooldown.

EXAMPLE

  @desc A lean Twi'lek woman with copper lekku and sharp, calculating eyes.
       She wears a worn utility vest over a flight suit, blaster holstered
       at the hip, and carries herself with the ease of someone used to
       moving through hostile spaces.
  → "Description set."

  look Jax
  → "A lean Twi'lek woman with copper lekku and sharp, calculating eyes…"

CHEAT SHEET
  @desc <text>   Set your description
  @desc          View current description
