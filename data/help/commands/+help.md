---
key: +help
title: +Help — Command Reference
category: "Commands: Info"
summary: Display the command category overview, look up a specific command or topic, or search for help entries by keyword.
aliases: [help, "?", commands, +commands]
see_also: [+who, +sheet, +inv]
tags: [help, commands, reference, meta, command]
access_level: 0
examples:
  - cmd: "+help"
    description: "Show the full command category listing."
  - cmd: "+help +mission"
    description: "Show help for the +mission command."
  - cmd: "+help dice"
    description: "Show help on D6 dice mechanics."
  - cmd: "+help/search bounty"
    description: "Search all help text for 'bounty'."
---

The primary help system. Shows the command category overview or
looks up a specific command, topic, or keyword. Usable before login.

SYNTAX

  +help                    Show all command categories.
  +help <command>          Show help for that command.
  +help <topic>            Show a help topic (dice, combat, space, etc.).
  +help/search <keyword>   Search all help entries for a keyword.

COMMAND CATEGORIES

  Navigation   Combat       Force        Economy      Smuggling
  Communication Character   D6 Dice     Advancement   Bounty
  Crafting     Medical      Space        Social        Channels
  NPC Crew     NPCs         Info

  Admin/Building categories are visible only to staff.

TOPIC KEYWORDS

  dice, d6, wilddie, attributes, skills, difficulty, combat,
  ranged, melee, wounds, dodge, cover, multiaction, armor, scale,
  force, forcepoints, darkside, lightsaber, cp, advancement,
  space, spacecombat, crew, hyperdrive, sensors, moseisley,
  cantina, tatooine, trading, smuggling, bounty, species, rp,
  newbie, commands, channels, building.

EXAMPLES

  +help
  → Lists all command categories with their commands.

  +help +mission
  → Full help page for the +mission command (syntax, examples, etc.).

  +help dice
  → WEG D6 dice-rolling rules: wild die, difficulties, modifiers.

  +help/search boarding
  → Lists every help entry that mentions 'boarding'.

ALIASES

  The following all work the same as '+help':
    help, ?, commands, +commands

SEE ALSO

  +who     Who is currently online.
  +sheet   Your character stats.

CHEAT SHEET
  +help                show command categories
  +help <topic>        show a command or topic
  +help/search <kw>    search all help entries
