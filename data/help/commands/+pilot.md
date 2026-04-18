---
key: +pilot
title: Pilot — The Pilot Station & Piloting Maneuvers
category: "Commands: Ships"
summary: All piloting verbs live under +pilot/<switch>. Take the pilot seat, or perform maneuvers — evade, jink, barrelroll, loop, slip, tail, close, flee, course. Every pilot verb is a switch here.
aliases: [pilot, evade, evasive, jink, barrelroll, broll, loop, immelmann, slip, sideslip, tail, getbehind, outmaneuver, shake, close, approach, fleeship, breakaway, course, navigate, setcourse]
see_also: [+gunner, +sensors, +bridge, +ship, stations, combat, maneuver]
tags: [ships, pilot, combat, command]
access_level: 0
examples:
  - cmd: "+pilot"
    description: "Take the pilot seat on your current ship (default — /claim)."
  - cmd: "pilot"
    description: "Same as +pilot (bare alias preserved)."
  - cmd: "+pilot/evade"
    description: "Evasive maneuvers — adds +2D defense against incoming fire this round."
  - cmd: "evade"
    description: "Same as +pilot/evade (bare alias preserved)."
  - cmd: "+pilot/jink"
    description: "Quick jink — moderate defensive bonus, cheaper stunt than evade."
  - cmd: "+pilot/barrelroll"
    description: "Barrel roll — classic defensive maneuver, harder to track weapons-lock."
  - cmd: "broll"
    description: "Short form for barrelroll."
  - cmd: "+pilot/loop"
    description: "Loop (Immelmann) — reverse course mid-fight, reposition for the next pass."
  - cmd: "+pilot/slip"
    description: "Side slip — lateral evasion, subtle but effective vs lock-on."
  - cmd: "+pilot/tail TIE-3"
    description: "Attempt to get on TIE-3's six — Piloting vs Piloting opposed roll."
  - cmd: "+pilot/outmaneuver TIE-3"
    description: "Break an opponent's tail — shake a pursuer off your own six."
  - cmd: "+pilot/close TIE-3"
    description: "Close range with TIE-3 — Piloting roll to reduce range band by one."
  - cmd: "+pilot/flee"
    description: "Attempt to break off combat entirely. Piloting opposed roll vs nearest hostile."
  - cmd: "+pilot/course"
    description: "Show current zone and adjacent zones you can transit to."
  - cmd: "+pilot/course deep_space_tat"
    description: "Set course for Tatooine deep-space zone. Transit time 20-25s based on band."
  - cmd: "course cancel"
    description: "Cancel the current transit (bare alias preserved)."
---

All piloting verbs are switches under +pilot. Bare forms (evade,
jink, loop, tail, course, etc.) still work as aliases — typing
`evade` and `+pilot/evade` reach the same code. The canonical form
is +pilot/<switch>; the rest of this page uses it everywhere.

See `+help combat` for the conceptual overview of space-combat rounds
(initiative, actions, resolution). This page is the command reference.

SWITCH REFERENCE
  /claim       Take the pilot seat (also: bare '+pilot', pilot)
  /evade       Evasive maneuvers (defensive bonus)
  /jink        Quick jink (lighter defense)
  /barrelroll  Barrel roll (lock-breaking)
  /loop        Loop / Immelmann (reposition)
  /slip        Sideslip (lateral evasion)
  /tail <t>    Get on target's six
  /outmaneuver Break an opponent's tail on you
  /close <t>   Close range with target
  /flee        Break off combat (opposed roll)
  /course <z>  Sublight course to adjacent zone

SEATING THE PILOT

`+pilot` with no switch claims the pilot station of the ship you're
aboard. You must be on a ship's bridge room and the pilot seat must
be unoccupied. Once seated, all other switches become available —
they check that you're the pilot and refuse otherwise.

Only ONE pilot per ship. If another PC is already piloting, wait for
them to `/vacate` (the +bridge management switch) before claiming.

PILOTING MANEUVERS

Most maneuvers roll your Space Transports or Starfighter Piloting
skill against a difficulty scaled to the action. R&E p.89 for the
skill tree; R&E p.97+ for opposed-roll combat rules.

  /evade        +2D defense vs all incoming fire this round
  /jink         +1D defense, costs less of your turn
  /barrelroll   Break a weapons lock-on
  /loop         Reverse direction mid-fight
  /slip         Lateral dodge, subtle
  /tail <t>     Claim the rear arc vs target (opposed)
  /outmaneuver  Break out of a hostile's rear arc
  /close <t>    Reduce range by one band (4 bands: short/medium/long/extreme)
  /flee         Break off combat entirely (opposed vs nearest hostile)

NAVIGATION

`/course` is pilot-only. It handles sublight movement between zones.

  +pilot/course                List current zone + adjacent zones
  +pilot/course <zone-key>     Set course; transit time 15–25s
  +pilot/course cancel         Cancel transit

Zone adjacency comes from the zone graph. Transit times:
  Dock ↔ Orbit           15s
  Orbit ↔ Deep Space     20s
  Deep Space ↔ Lane      25s

During transit you're off the combat grid — can't fire or be fired
upon. The pilot rolls Space Transports on arrival; a good roll
enters cleanly, a bad one signals emerging-ship alarms to anyone
nearby (sensor tell).

Hyperspace jumps are NOT a pilot switch — they go through the
navigator station (bare `hyperspace` or `jump`).

FACTION / DARK-SIDE

Piloting maneuvers don't grant/cost DSP directly. The `fleeing`
verb CAN grant a small Survival mark in profession-chain tracking,
but only if used to escape a losing fight rather than as a feint.

EXAMPLES

  (aboard an X-Wing)
  +pilot
  → "You take the pilot seat. Controls are live."

  (space combat begins)
  +pilot/evade
  → "You jink and weave — +2D defense this round."

  +pilot/tail TIE-3
  → Opposed Space Transports vs TIE-3. Success: claim rear arc.

  +pilot/course deep_space_tat
  → "Plotting course to Tatooine deep space. ETA 20 seconds."

CHEAT SHEET
  +pilot                = take pilot seat (also: pilot)
  +pilot/evade          = evasive maneuvers (also: evade, evasive)
  +pilot/jink           = quick jink
  +pilot/barrelroll     = barrel roll (also: broll)
  +pilot/loop           = loop (also: immelmann)
  +pilot/slip           = sideslip
  +pilot/tail <t>       = get on six
  +pilot/outmaneuver    = break a tail (also: shake)
  +pilot/close <t>      = close range (also: approach)
  +pilot/flee           = break combat (also: fleeship, breakaway)
  +pilot/course <z>     = sublight nav (also: course, navigate, setcourse)

Sources: R&E p.89 (Space Transports, Starfighter Piloting),
R&E p.97+ (space-combat opposed rolls).
