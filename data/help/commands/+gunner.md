---
key: +gunner
title: Gunner — Weapons Station & Target Lock
category: "Commands: Ships"
summary: All gunner verbs live under +gunner/<switch>. Take a gunner seat, fire weapons, or lock onto a target. Every gunner verb is a switch here.
aliases: [gunner, gunnery, fire, lockon, lock, targetlock]
see_also: [+pilot, +sensors, +bridge, +ship, combat, weapons]
tags: [ships, gunner, combat, command]
access_level: 0
examples:
  - cmd: "+gunner"
    description: "Take the first open weapon station (default — /claim)."
  - cmd: "gunner"
    description: "Same as +gunner (bare alias preserved)."
  - cmd: "+gunner/claim 2"
    description: "Take weapon station #2 on a multi-weapon ship."
  - cmd: "gunner 2"
    description: "Same as +gunner/claim 2 (bare alias)."
  - cmd: "gunner turbo"
    description: "Take the station matching 'turbo' (e.g., turbolaser)."
  - cmd: "+gunner/fire TIE-3"
    description: "Fire your weapon at TIE-3. Starship Gunnery roll vs target's maneuver + range."
  - cmd: "fire TIE-3"
    description: "Same as +gunner/fire (bare alias preserved)."
  - cmd: "+gunner/lockon TIE-3"
    description: "Establish weapons lock on TIE-3. Successful lock = +2D on the next /fire."
  - cmd: "lockon TIE-3"
    description: "Same as +gunner/lockon (bare alias preserved)."
  - cmd: "lock TIE-3"
    description: "Short bare alias for /lockon."
  - cmd: "targetlock TIE-3"
    description: "Another bare alias for /lockon."
  - cmd: "+gunner/fire"
    description: "Fire at your current lock-on target (if one is set)."
  - cmd: "+gunner"
    description: "Checking what station you're at — if seated at gunner, gives a status line."
  - cmd: "gunnery"
    description: "S57a fix — bare 'gunnery' now unambiguously means gunner (no longer aliased to board)."
---

All gunner verbs are switches under +gunner. Bare forms (fire,
lockon, etc.) still work as aliases — typing `fire TIE-3` and
`+gunner/fire TIE-3` reach the same code. The canonical form is
+gunner/<switch>; the rest of this page uses it everywhere.

See `+help combat` for the space-combat round structure. This page
is the gunner-station command reference.

SWITCH REFERENCE
  /claim [#]    Take the gunner seat (default — bare +gunner)
  /fire <t>     Fire weapon at target
  /lockon <t>   Establish weapons lock on target

SEATING THE GUNNER

`+gunner` with no switch claims the first available weapon station.
Some ships have multiple gunner seats (YT-1300 has 2, TIE Bomber
has 1, capital ships have many). You can specify which by number
or partial weapon name:

  +gunner         First open station
  +gunner 1       Station #1 specifically
  +gunner turbo   Station matching 'turbo' (e.g., turbolaser)

WEAPONS FIRING

`/fire <target>` rolls Starship Gunnery vs a difficulty based on:
  - Range band to target (short/medium/long/extreme, R&E p.97+)
  - Target's maneuverability (ships with better handling harder to hit)
  - Evasive maneuvers by pilot (+2D difficulty from /evade)
  - Target lock bonus (+2D if you have /lockon active)
  - Scale modifier (fighter vs capital, R&E p.96)

Successful hit rolls damage vs the target's shields + hull. Critical
hits (Wild Die explodes) add bonus damage.

LOCK-ON

`/lockon <target>` is a setup action that costs your turn but grants
+2D on your next attack against that target. Useful when the target
is hard to hit (small scale, evading, long range).

The lock persists until:
  - You /fire (consumed)
  - Target breaks the lock via /pilot/barrelroll
  - You move to a new station or vacate

CHEAT SHEET
  +gunner           = take gunner seat (also: gunner, gunnery)
  +gunner/claim [#] = take specific station
  +gunner/fire <t>  = fire weapon (also: fire)
  +gunner/lockon <t> = weapons lock (also: lockon, lock, targetlock)

S57A NOTE — `gunnery` collision fixed

Pre-S57a, bare `gunnery` was aliased to BOTH GunnerCommand AND
BoardCommand (a collision bug). Registration order decided which
won. S57a removed it from BoardCommand — `gunnery` now unambiguously
means "take the gunner seat."

Sources: R&E p.89 (Starship Gunnery skill), R&E p.97+ (space-combat
difficulty and scale modifiers).
