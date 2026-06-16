---
key: +background
title: +Background — Character Background
category: "Commands: Character"
summary: View or set your character's backstory, read by NPCs and the Director AI when generating quests.
aliases: [background, "+bg", bg]
see_also: [+sheet, +finger, +rpprefs]
tags: [character, background, narrative, command]
access_level: 0
examples:
  - cmd: "+background"
    description: "Show your current background text."
  - cmd: "+background A former Clone Wars medic who deserted after Geonosis."
    description: "Set your background to a single-line text."
  - cmd: "+bg"
    description: "Short alias for +background."
---

View or write your character's background — a short narrative summary of
who they are, where they came from, and what drives them. NPCs consult
your background during conversations and the Director AI uses it when
generating personal quests and story hooks.

SYNTAX

  +background              — show your current background
  +background <text>       — set your background (up to 2000 characters)

TIPS FOR A GOOD BACKGROUND

  • Write in third person ("She is…", "He spent…").
  • Focus on what shaped the character, not what they can do.
  • Include at least one hook — a loss, a debt, a loyalty, a secret —
    so the Director has material to build quests around.
  • Keep it under a paragraph or two; the Director reads it each time.

EXAMPLE BACKGROUND

  +background A former clone medic who walked off the line after the
  Geonosis campaign, haunted by the ones he couldn't save. Now works
  as a ship's surgeon on the Outer Rim, staying one jump ahead of
  the Republic inquiry and the nightmares alike.

NOTES

  • Your background is visible to other players who view your +finger card.
  • You can update it any time — changes take effect immediately.
  • The 2000-character limit is enough for two substantial paragraphs.

EXAMPLES

  +background
  → Read your current background.

  +background Grew up on Corellia, stole her first speeder at twelve…
  → Set your background. Overwrites the previous text.

CHEAT SHEET
  +background        = view your background
  +background <text> = set your background
  +bg                = short alias
