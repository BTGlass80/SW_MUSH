---
key: think
title: Think — Private In-Character Thoughts
category: "Commands: Roleplay"
summary: Record a private IC thought. Other players cannot see it, but the AI narrative system uses it to inform NPC behavior and Director quest hooks.
aliases: []
see_also: [say, emote, whisper, +ooc, +scene]
tags: [roleplay, rp, narrative, command]
access_level: 0
examples:
  - cmd: "think I don't trust this Rodian."
    description: "Record a private suspicion. Logged for the Director AI."
  - cmd: "think Something about this deal feels wrong..."
    description: "Narrative thought that may influence NPC reactions over time."
---

Record an internal thought that only you can see.

USAGE

  think <text>

  Your thoughts are completely private — no other player or NPC in
  the room sees them in their feed. The text is capped at 500
  characters.

HOW THOUGHTS WORK

  The AI narrative system reads your logged thoughts along with your
  location, faction standing, and active quests. They feed the
  Director's pacing model and may influence:

    • NPC dialogue choices in future `talk` interactions
    • Director-generated event hooks in your zone
    • Quest branch weighting over time

  Thoughts are low-weight signals — useful for setting intent or
  RP motivation, not mechanical triggers.

ROLEPLAY USE

  `think` is the tool for inner monologue, planning, or RP beats
  that belong in your character's head but not in the room feed.
  Combine it with `emote` (visible) and `say` (spoken) for a fuller
  scene.

CHEAT SHEET

  think <text>    — private IC thought (invisible to others)
  say <text>      — spoken out loud (everyone in room)
  emote <text>    — visible action/pose
  whisper <player> = <text>   — whispered to one player
