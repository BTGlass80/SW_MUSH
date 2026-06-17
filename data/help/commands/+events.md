---
key: +events
title: +Events — Event Calendar
category: "Commands: Social"
summary: List upcoming player-run and staff-run events scheduled in the event calendar.
aliases: [+event/list, +calendar]
see_also: [+event, +who, channels]
tags: [events, calendar, social, command]
access_level: 0
examples:
  - cmd: "+events"
    description: "List all upcoming events with title, time, location, and signup count."
---

Display all upcoming events on the in-game event calendar. Shows
title, scheduled time, location, signup count, and creator. Use
+event <id> to see full details or sign up.

SYNTAX

  +events
  +calendar
  +event/list

OUTPUT FORMAT

  ═══ UPCOMING EVENTS ═══
    #3  The Sabacc Tournament  [ACTIVE]
        2026-06-16 20:00 @ Mos Eisley Cantina · 7 signed up · by Kira
    #4  Clone Corps Strategy Briefing
        TBD · 3 signed up · by Tundra Vehn

  Columns:
    #id        Event number — use with +event <id>
    Title      Event name
    [ACTIVE]   Shown when event is currently in progress
    Time       Scheduled time (TBD if not yet set)
    Location   Where the event is held
    Signups    Number of characters signed up
    By         Event creator's name

RELATED COMMANDS

  +event <id>               View full details and signup list.
  +event/signup <id>        Sign your character up for an event.
  +event/create <t>=<desc>  Create a new event (any player can create).

EXAMPLES

  +events
  → Full list of upcoming events.

  +event 3
  → Details for event #3, including description and who is signed up.

CHEAT SHEET
  +events              list upcoming events
  +event <id>          full event details
  +event/signup <id>   sign up for an event
