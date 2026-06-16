---
key: +village
title: Village — Village Quest Progress
category: "Commands: Quests"
summary: View your Village quest standing and trial completion status. Shows village_standing score, trial progress, courage choices, and your chosen path if you've committed at Step 10.
aliases: ["+vil"]
see_also: [+quests, +quest, +sheet, reputation, tutorial]
tags: [quests, village, progression, command]
access_level: 0
examples:
  - cmd: "+village"
    description: "Show your Village quest standing, trial status, and path (if chosen)."
  - cmd: "+vil"
    description: "Short alias for +village."
---

Show your progress through the Village questline — the core
tutorial experience for new characters that establishes their
place in the Clone Wars era.

WHAT IS SHOWN

  Village standing     — current score (0 to 12+) and tier label
  Trial completion     — each of the 5 trials: complete / pending
  Courage choice       — which path you took at the trial fork
  Chosen path          — your long-term path (Jedi / Soldier /
                         Scoundrel / etc.) if you've committed at
                         Step 10 of the quest line

FIRST VISIT NOTE

If you haven't visited the Village yet, +village returns a brief
placeholder: "You have not yet been to the Village. Find the
Hermit; he will give you the invitation."

The Hermit can be found via the tutorial chain — follow the
initial chain quests until the Village invitation appears. You
won't see the full status panel until after your first audience
with the Village Elder.

THE VILLAGE QUESTLINE

The Village is a structured story sequence (~10 steps) that:
  - Introduces the major factions and Clone Wars stakes
  - Puts your character through trials that define their
    character (courage, compassion, judgment)
  - Unlocks faction rep and starting gear appropriate to the
    path you choose
  - Connects to the main tutorial chain and opens profession
    questlines

VILLAGE STANDING TIERS

  0–2     Newcomer — just arrived
  3–5     Tested — completed initial trials
  6–8     Trusted — Elder recognizes your contributions
  9–11    Champion — significant reputation in the village
  12+     Legend — rare; marks exceptional service

TRIALS

The five trials each test a different quality:
  1. Trial of Knowledge   (lore / observation)
  2. Trial of Courage     (a fork: different paths are available)
  3. Trial of Compassion  (helping vs ignoring)
  4. Trial of Skill       (your primary attribute)
  5. Trial of Commitment  (path declaration — Step 10)

Completion of Trial 5 (commitment) locks in your path and opens
the full faction questlines.

EXAMPLES

  (before visiting the Village)
  +village
  → "You have not yet been to the Village. Find the Hermit;
     he will give you the invitation."

  (after completing all trials)
  +village
  → "Village Standing: 9 (Champion)
     Trials: Knowledge ✓  Courage ✓  Compassion ✓  Skill ✓
             Commitment ✓
     Courage choice: Face the dark side vision directly
     Chosen path: Jedi Guardian"

CHEAT SHEET
  +village     = full village progress panel
  +quests      = all active/available quest lines
  +quest <n>   = details on a specific quest
