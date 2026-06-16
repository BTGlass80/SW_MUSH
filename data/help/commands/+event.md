---
key: +event
title: +Event — Event Details and Management
category: "Commands: Social"
summary: View, create, and manage in-game events. Any player can create events; creators can set time, location, and cancel.
aliases: []
see_also: [+events, +who, channels, say]
tags: [events, calendar, social, command]
access_level: 0
examples:
  - cmd: "+event 3"
    description: "View details for event #3."
  - cmd: "+event/create Sabacc Night=Weekly sabacc tournament in the cantina."
    description: "Create a new event with title and description."
  - cmd: "+event/signup 3"
    description: "Sign up for event #3."
  - cmd: "+event/time 3=2026-06-20 20:00"
    description: "Set the scheduled time for event #3 (creator only)."
  - cmd: "+event/cancel 3"
    description: "Cancel event #3 (creator only)."
---

View detailed information about a specific event, or use subcommands
to create, schedule, and manage events. Any player can create an
event; only the creator can edit or cancel their own events.

SYNTAX

  +event <id>                          View event details and signup list
  +event/create <title>=<description>  Create a new event
  +event/time <id>=<time>              Set the event time (creator)
  +event/location <id>=<location>      Set the event location (creator)
  +event/signup <id>                   Sign your character up
  +event/unsignup <id>                 Remove your signup
  +event/cancel <id>                   Cancel the event (creator only)

VIEWING AN EVENT

  +event <id> shows:
    Title, status, scheduled time, location, creator, description,
    and the full list of signed-up characters.

CREATING AN EVENT

  Any player can create an event:
    +event/create Sabacc Night=Weekly high-stakes sabacc tournament.

  After creating, use /time and /location to fill in the details:
    +event/time 3=2026-06-20 20:00
    +event/location 3=Mos Eisley Cantina, Table 7

SIGNING UP

  +event/signup <id>    Adds your character to the attendance list.
  +event/unsignup <id>  Removes your signup if plans change.

CANCELLING

  Only the event creator can cancel. Cancellation is visible to all
  signed-up players via the event listing status.

STATUS

  upcoming   Scheduled, not yet started.
  active     Currently in progress.
  completed  The event has passed.
  cancelled  Creator cancelled.

EXAMPLES

  +event 3
  → Full details: description, time, location, who signed up.

  +event/create Heist Planning=Coordinating the warehouse job.
  → Creates a new event, returns its ID.

  +event/signup 3
  → Your name appears in the signup list for event #3.

SEE ALSO

  +events   List all upcoming events.

CHEAT SHEET
  +event <id>              view event
  +event/create <t>=<d>   create
  +event/signup <id>       sign up
  +event/unsignup <id>     withdraw
  +event/time <id>=<t>     set time
  +event/location <id>=<l> set location
  +event/cancel <id>       cancel (creator only)
