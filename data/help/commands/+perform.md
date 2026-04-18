---
key: +perform
title: Perform — Entertainer Performances
category: "Commands: Social"
summary: Entertain a crowd. Single-action command — perform music, dance, comedy, or storytelling. Rolls Entertain skill vs audience difficulty; successful performances tip and build your entertainer reputation.
aliases: [perform, entertain, play]
see_also: [entertain, cantinas, social]
tags: [social, entertainer, command]
access_level: 0
examples:
  - cmd: "+perform"
    description: "Start a performance in the current room. Entertainer skill roll vs Difficulty."
  - cmd: "perform"
    description: "Same as +perform (bare alias preserved)."
  - cmd: "entertain"
    description: "Another bare alias — start performing."
  - cmd: "play"
    description: "Bare alias — equivalent to +perform."
  - cmd: "+perform music"
    description: "Specify the type of performance (flavor text only; roll is the same)."
  - cmd: "+perform dance"
    description: "Dance performance — same roll, different flavor messages."
  - cmd: "+perform story"
    description: "Tell a story — storytelling performance."
  - cmd: "+perform comedy"
    description: "Stand-up comedy — different critical-success / fumble flavor."
---

The +perform command is a single-action command — no switches, just
run it to perform in the current room. Bare forms (perform, entertain,
play) still work as aliases.

WHAT HAPPENS

1. You declare your performance with optional type (music / dance /
   story / comedy).
2. Entertainer skill roll vs a room-wide Difficulty based on the
   crowd size and venue quality.
3. Successful performances:
   - Broadcast flavor text to everyone in the room
   - Earn tips from NPCs in the room (small credits)
   - Build your entertainer reputation (passive CP trickle at high
     rep tiers)
   - Grant a small morale bonus to allies nearby
4. Fumbles embarrass you publicly.

PERFORMANCE TYPES

Flavor only — the skill roll and mechanics are the same regardless
of type. Pick one that fits your character:

  music   Play an instrument, sing
  dance   Dance (with or without music)
  story   Storytelling, oral history
  comedy  Stand-up, observational humor

DIFFICULTY SCALES WITH VENUE

  Empty room       Very Easy  (5)
  Small crowd      Easy       (10)
  Full cantina     Moderate   (15)
  Standing-room    Difficult  (20)
  Concert hall     Heroic     (30)

Rebel Alliance outposts give a +1D reputation bonus for Light-
aligned performers; Imperial venues ban certain "subversive" acts.

WHY NO UMBRELLA CLASS?

Per the S57b convention for single-action commands (copilot,
engineer, navigator), single-action verbs don't get their own
umbrella class — the canonical +verb form is just added as an
alias. The S54 rename roadmap included +perform for naming
consistency, so it's registered here without the full umbrella
apparatus.

CHEAT SHEET
  +perform         = start performance (also: perform, entertain, play)
  +perform <type>  = type-flavored performance

Sources: R&E Entertain skill (p.91). The entertainer rep / tip
economy is game-original. See `+help cantinas` for good venues.
