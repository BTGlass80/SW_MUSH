---
key: page
title: Page — Private Message to Any Online Player
category: "Commands: Social"
summary: Send a private tell to any online player, regardless of location. Re-page your last target with just page <message>.
aliases: [p]
see_also: [say, +ooc, +channels, whisper]
tags: [social, comms, private, messaging, command]
access_level: 0
examples:
  - cmd: "page Tundra = Meet me at bay 94."
    description: "Send a private message to Tundra."
  - cmd: "page Hey, still there?"
    description: "Re-page your last page target without re-specifying the name."
  - cmd: "p Kira = I'm running late."
    description: "Short form of page."
---

Send a private tell to any online player. Pages cross rooms and zones — the
recipient sees it wherever they are. Useful for coordination, OOC logistics,
or contacting someone before they see a room message.

SYNTAX

  page <player> = <message>
  page <message>              (re-pages your last page target)
  p <player> = <message>      (short alias)

OUTPUT FORMAT

  You paged Tundra Vehn: "Meet me at bay 94."
  Tundra Vehn pages you: "Meet me at bay 94."

NOTES

  • Re-page (bare `page <message>`) re-uses the last player you paged.
    If you have no prior target, you will get an error.
  • Pages are IC-blind — the game logs pages in the same session buffer
    as in-game messages. Use player real names (character names), not
    account names.
  • Pages reach offline players as a missed-tell when they log in
    (not yet implemented — currently pages to offline players are dropped).

CHEAT SHEET
  page <player> = <msg>   — private tell to player
  page <msg>              — re-page same player
  p <player> = <msg>      — short alias
