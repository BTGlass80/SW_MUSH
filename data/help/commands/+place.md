---
key: +place
title: Place — Seating, Tables, Booths in Cantina-Style Rooms
category: "Commands: Social"
summary: Player places verbs under +place/<switch>. View places in the current room, sit at a table or booth, or stand up to leave. RP shortcuts (tt, ttooc, mutter) stay bare. Admin place configuration uses @places / @place (native @-prefix form).
aliases: [places, place, join, sit, depart, stand]
see_also: [tt, ttooc, mutter, places, "@places", "@place", social]
tags: [social, seating, rp, command]
access_level: 0
examples:
  - cmd: "+place"
    description: "List places (tables, booths, seats) in this room — default."
  - cmd: "places"
    description: "Same as +place (bare alias preserved)."
  - cmd: "+place/view"
    description: "Same as default — list places in this room."
  - cmd: "+place/join 3"
    description: "Join place #3 (e.g., Table 3, Corner Booth)."
  - cmd: "join 3"
    description: "Same as +place/join (bare alias preserved)."
  - cmd: "sit 3"
    description: "Another bare alias — sit at place #3."
  - cmd: "+place/depart"
    description: "Leave your current seat (stand up)."
  - cmd: "depart"
    description: "Same as +place/depart (bare alias preserved)."
  - cmd: "stand"
    description: "Another bare alias — leave your seat."
  - cmd: "tt Care for a drink?"
    description: "Table-talk — only others at your table hear this (bare RP shortcut; NOT under +place)."
  - cmd: "ttooc brb phone"
    description: "OOC chat at your table (bare; not umbrella'd)."
  - cmd: "mutter Fine, I'll take it"
    description: "Mutter under your breath — only players near you hear (bare)."
  - cmd: "@places 4"
    description: "Admin/builder: configure 4 places in this room (native @-prefix form, not under +place)."
---

Player seating verbs live under +place/<switch>. Bare forms
(places, join, depart) still work as aliases. The canonical form
is +place/<switch>; the rest of this page uses it everywhere.

See `+help places` for the conceptual overview of cantina-style
places. This page is the command reference.

SWITCH REFERENCE
  /view     List places in current room (default — bare +place)
  /join <n>  Sit at a place (by number or name match)
  /depart   Stand up / leave your seat

WHAT ARE PLACES?

"Places" are named seats within a room — tables, booths, bar
stools, conference tables. Cantinas typically have 4–6. Each seat
can hold multiple occupants (max configured by builders).

When you join a place, you get:
  - A "At Table 3" prefix on your pose/say lines
  - Access to table-talk (tt) — private to others at your table
  - A natural RP anchor for a conversation or meal

/join <n-or-name>

Accepts either a place number or a partial name match:
  +place/join 3              place #3
  +place/join booth          first place matching "booth"
  +place/join corner         first place matching "corner"

If the place is full (at its configured max), you're bounced with
a message and stay standing.

/depart

Leave your current seat. No args needed. You're returned to the
general room floor.

RP SHORTCUTS — STAY BARE (S54 POLICY)

Per the S54 rename policy, three RP shortcuts stay bare rather
than being folded into +place:

  tt <text>        Table-talk — only others at your table hear
  ttooc <text>     OOC chat within your table
  mutter <text>    Mutter under your breath — only nearby hear

These are natural RP actions players type without thinking about
role context. The S54 policy is: "natural English verbs stay bare."
Typing `tt What'll you have?` is fluid; typing `+place/tabletalk
What'll you have?` is not.

ADMIN COMMANDS — NATIVE @-PREFIX

Place configuration stays at the @-prefix admin form:

  @places <n>           Configure N places in the room
  @places/clear         Remove all places
  @place <#>/name = ...  Set place name
  @place <#>/max = <n>   Set max occupants
  @place <#>/desc = ...  Set place description
  @place <#>/prefix = ... Set pose/say prefix

These were NOT folded into +place/config or +place/set in S58
because their native ctx.switches handling (@places/clear reads
"clear" from switches) would be shadowed by the umbrella's own
switch routing. The @-prefix form is already canonical; no change
needed.

CHEAT SHEET
  +place           = list places (also: places, place)
  +place/join <n>  = sit (also: join, sit)
  +place/depart    = stand (also: depart, stand)
  tt <text>        = table-talk (STAYS BARE)
  ttooc <text>     = table OOC (STAYS BARE)
  mutter <text>    = nearby whisper (STAYS BARE)
  @places <n>      = admin setup (NATIVE @-PREFIX)

Sources: Places concept adapted from classic MUSH/MUX code
(TinyMUX/PennMUSH +places); game-original implementation.
