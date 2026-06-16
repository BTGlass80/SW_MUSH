---
key: +achievements
title: +Achievements — Achievement Progress
category: "Commands: Progress"
summary: View your achievement progress across all game systems, optionally filtered by category.
aliases: [+achievement, +ach, achievements]
see_also: [+sheet, +reputation, +mission]
tags: [achievements, progress, stats, command]
access_level: 0
examples:
  - cmd: "+achievements"
    description: "Show all achievements and your current progress."
  - cmd: "+achievements combat"
    description: "Show only combat-category achievements."
  - cmd: "+ach space"
    description: "Show space-combat achievements."
  - cmd: "+ach economy"
    description: "Show economy and trade achievements."
---

Display your achievement progress across all game systems. Achievements track
milestones you've reached in combat, exploration, crafting, trade, and more.
Completed achievements award Contribution Points (CP) used for advancement.

SYNTAX

  +achievements              — show all achievements
  +achievements <category>   — filter by category

CATEGORIES

  combat        Ground combat milestones
  space         Space combat and piloting
  economy       Credits, trade, and business
  crafting      Item creation and repair
  social        RP scenes, events, and social goals
  exploration   Regions visited, wildspace, discoveries
  smuggling     Smuggling runs and contraband
  force         Force-related milestones (Force-sensitive characters)

OUTPUT FORMAT

  === Achievements: Combat ===
  [X] First Blood           — Land your first attack hit.         +5 CP
  [X] Survivor              — Survive 10 combat encounters.       +10 CP
  [ ] Decorated Veteran     — Win 50 combat encounters.           (12/50)
  [ ] Undefeated            — Win 25 consecutive encounters.       (3/25)

  [X] = completed    [ ] = in progress (count shown if applicable)

NOTES

  • Completed achievements cannot be re-earned.
  • CP awards from achievements go to your Contribution Point total.
  • Some achievements are hidden until you discover the relevant content.
  • The full list grows as new game systems are added.

EXAMPLES

  +achievements
  → Full achievement list across all categories.

  +achievements force
  → Achievements for Force-sensitive characters only.

CHEAT SHEET
  +achievements            = all achievements
  +achievements <category> = filtered view
  +ach                     = short alias
