---
key: +finger
title: +Finger — Player Info Card
category: "Commands: Social"
summary: View any player's info card, or set fields on your own.
aliases: [finger]
see_also: [+who, +where, +rpprefs, +background]
tags: [social, info, profile, command]
access_level: 0
examples:
  - cmd: "+finger"
    description: "View your own info card."
  - cmd: "+finger Kira"
    description: "View Kira's info card (partial name match)."
  - cmd: "+finger/set position = Freelance Pilot"
    description: "Set your Position field."
  - cmd: "+finger/set quote = The stars don't care what you did yesterday."
    description: "Set your personal Quote."
  - cmd: "+finger/set timezone = US/Central"
    description: "Set your timezone so others know when you're available."
---

View a player's public info card, or set your own. Shows species, faction,
description excerpt, online status, and any custom profile fields the player
has filled in.

SYNTAX

  +finger               — your own card
  +finger <name>        — another player's card (partial name match)
  +finger/set <field> = <value>   — set a field on your own card
  +finger/set <field> =           — clear a field (empty value)

FIELDS

  fullname    Your full in-character name (for multi-part names).
  position    Job title / role (e.g. "Jedi Padawan", "Smuggler").
  rp-prefs    Short RP preference summary (use +rpprefs for the structured form).
  quote       A memorable quote or motto.
  alts        Other characters you play (if you want to share).
  theme-song  A song that fits your character.
  plan        What your character is currently up to / looking for in RP.
  timezone    Your real-world timezone (helps coordinate scene scheduling).

OUTPUT FORMAT

  ══════════════════════════════════════════════
    Kira Solenne
  ══════════════════════════════════════════════
  Species:     Human
  Faction:     Republic
  Desc:        She keeps her head down and her blaster close…
  Status:      Online  On for: 2h14m  Idle: 3m

  RP PREFERENCES:
    Adventure ......... YES    Intrigue .......... YES
    Romance ........... MAYBE  Dark Themes ........ NO

OUTPUT NOTES

  • Status shows ONLINE with on-time and idle if the player is connected;
    OFFLINE otherwise.
  • RP Preferences are drawn from +rpprefs settings.
  • Only fields with non-empty values are displayed.

EXAMPLES

  +finger
  → Your own card with current status.

  +finger Han
  → Info card for the first online player matching "Han".

  +finger/set plan = Looking for a crew. Any job that pays.
  → Sets your "Plan" field, visible to other players.

CHEAT SHEET
  +finger          = view your own card
  +finger <name>   = view another player's card
  +finger/set f=v  = set field f to value v
