---
key: +guide
title: +Guide — In-Game Field Guides
category: "Commands: Info"
summary: Open the in-game guide browser to read long-form field guides on combat, the Force, crafting, and more.
aliases: [guide, guides, +guides]
see_also: [+help, +sheet, +check]
tags: [guide, guides, help, reference, meta, command]
access_level: 0
examples:
  - cmd: "guide"
    description: "Open the guide browser overlay inside the game client."
  - cmd: "+guide"
    description: "Same as guide — opens the full guide library."
  - cmd: "help"
    description: "Bare 'help' (no topic) also opens the guide browser."
---

Open the in-game field guide browser. All 25+ long-form guides are
available without leaving the game — click any guide to read it in a
two-column overlay directly inside /play.

SYNTAX

  guide              Open the guide browser (alias: guides, +guide, +guides)
  +guide             Same
  help               Bare 'help' (no argument) also opens the browser

  help <topic>       With an argument, 'help' still queries the server-side
                     help system as normal (e.g. help +mission, help dice).

WHAT IS IN THE GUIDE LIBRARY?

  25+ guides covering every major system, organised by category:

    Getting Started  Combat           The Force
    Economy          Crafting         Space & Ships
    Social & RP      Factions         World & Lore

  Guides go deeper than the command help system — they explain why
  things work the way they do, give strategy tips, and cover edge cases
  that don't fit in a cheat-sheet.

HOW TO NAVIGATE

  Open the browser → pick a category on the left → click any guide to
  load it in the reading pane. The browser remembers which guides you
  have read and shows the last-opened guide on next launch.

  The GUIDES quick-action button in the HUD toolbar opens the same
  browser at any time.

EXAMPLES

  guide
  → Guide browser opens; categories listed on the left.

  help dice
  → Goes to the server; shows the WEG D6 dice-mechanics help page.

  help
  → Opens the guide browser (no server round-trip).

SEE ALSO

  +help <topic>   Server-side per-command help and topic pages.
  +sheet          Your character stats.
  +check          Roll a skill check.

CHEAT SHEET
  guide / +guide   open the guide browser
  help             same (bare — no argument)
  help <topic>     server-side help for a command or topic
