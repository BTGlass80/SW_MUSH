---
key: +shipcrew
title: ShipCrew — Authorized Crew Roster
category: "Commands: Ships"
summary: Manage who is authorized to pilot your ship. Only the owner and authorized crew can take the pilot seat and launch — all others can board but not fly.
aliases: [shipcrew, "+permit"]
see_also: [+ship, +pilot, +bridge, +crew, launch, land]
tags: [ships, crew, command]
access_level: 0
examples:
  - cmd: "+shipcrew"
    description: "List the authorized crew roster for the ship you're aboard."
  - cmd: "+shipcrew add Jorak"
    description: "Authorize Jorak to pilot your ship."
  - cmd: "+shipcrew remove Jorak"
    description: "Revoke Jorak's piloting authorization."
  - cmd: "shipcrew"
    description: "Same as +shipcrew (bare alias preserved)."
---

Control who can fly your ship. The owner is always authorized;
everyone else needs explicit crew authorization before they can
sit in the pilot seat and launch.

SUBCOMMANDS

  +shipcrew                  List authorized crew for the ship you're aboard
  +shipcrew add <name>       Authorize a co-pilot / crew member
  +shipcrew remove <name>    Revoke a crew member's authorization

You must be ABOARD the ship you want to manage. Changes take effect
immediately — an authorized pilot can fly it the moment you add them.

OWNER AUTHORIZATION

The ship owner is always authorized — no entry in the roster is
needed (and trying to +shipcrew add yourself returns a notice).
The roster shows additional authorized crew beyond the owner.

BOARDING VS FLYING

Anyone can board a docked ship — cargo bays and passenger areas
don't require authorization. The gate applies specifically to:
  - Taking the pilot seat
  - Using the `launch` command
  - Hyperspacing

If someone tries to launch a ship they're not authorized for, they
get "You don't have authorization to pilot this ship."

USE CASES

  Co-piloting friends: Add trusted allies who regularly fly with
    you so they can launch even when you step away.

  Contracted crews: If you hire an NPC crew, their authorization is
    handled automatically by the crew system — you don't need to
    manually add them.

  Shared guild ships: Add all guild members who use the ship.
    The roster can hold multiple entries.

REVOKING ACCESS

+shipcrew remove works immediately. A pilot mid-flight retains
their seat for the current leg (you can't kick someone out of the
cockpit while hyperspace is active), but they lose authorization
to launch again afterward.

EXAMPLES

  (aboard your YT-1300)
  +shipcrew
  → "Authorized crew for 'Dusty Mynock':
       Owner: Asha
       Crew:  Jorak, Brix"

  +shipcrew add Tundra
  → "Tundra added to 'Dusty Mynock' crew roster."

  +shipcrew remove Brix
  → "Brix removed from 'Dusty Mynock' crew roster."

  (Brix tries to fly)
  → "You don't have authorization to pilot this ship."

CHEAT SHEET
  +shipcrew             = view authorized roster
  +shipcrew add <name>  = authorize a pilot
  +shipcrew remove      = revoke authorization
