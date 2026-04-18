---
key: +bridge
title: Bridge — Commander Station, Captain Orders, Ship-Wide Actions
category: "Commands: Ships"
summary: All commander / bridge-tier verbs live under +bridge/<switch>. Take the commander seat, issue tactical orders, hail / open comms, manage shields / power / transponder / damage control. Also station management (vacate, assist, coordinate). Every bridge verb is a switch here.
aliases: [commander, command, captain, order, orders, hail, comms, comm, radio, shields, power, pwr, transponder, transp, resist, breakfree, damcon, damagecontrol, repair, vacate, unstation, assist, coordinate, coord]
see_also: [+pilot, +gunner, +sensors, +ship, +crew, captainorders, stations, combat]
tags: [ships, commander, bridge, command]
access_level: 0
examples:
  - cmd: "+bridge"
    description: "Take the commander seat on your ship (default — /claim)."
  - cmd: "commander"
    description: "Same as +bridge (bare alias preserved)."
  - cmd: "captain"
    description: "Another bare alias for the commander seat."
  - cmd: "+bridge/order pilot evade"
    description: "Captain-order — direct the pilot at the pilot station to evade this round."
  - cmd: "order gunner fire TIE-3"
    description: "Same as +bridge/order (bare alias preserved — but collides with +crew/order)."
  - cmd: "+bridge/hail TIE-3"
    description: "Open a comms channel with target TIE-3."
  - cmd: "hail TIE-3"
    description: "Same as +bridge/hail (bare alias preserved)."
  - cmd: "+bridge/comms"
    description: "Show available comms channels on your ship."
  - cmd: "+bridge/shields full"
    description: "Raise shields to full — consumes power; distribute via /power."
  - cmd: "shields"
    description: "Same as +bridge/shields (bare alias preserved)."
  - cmd: "+bridge/power"
    description: "Show current power allocation (shields / weapons / engines / sensors)."
  - cmd: "+bridge/power shields 4 weapons 2"
    description: "Set power allocation — 4 to shields, 2 to weapons (total must not exceed reactor output)."
  - cmd: "+bridge/transponder off"
    description: "Turn off your transponder — ship stops broadcasting ID (illegal in most space, Customs flag)."
  - cmd: "+bridge/transponder spoofed IMP_CUSTOMS"
    description: "Broadcast a spoofed Imperial Customs ID — requires crafted slicer module."
  - cmd: "+bridge/resist"
    description: "Resist a tractor beam lock via Piloting + Commander synergy."
  - cmd: "resist"
    description: "Same as +bridge/resist (bare alias preserved)."
  - cmd: "+bridge/damcon shields"
    description: "Damage-control NPC — redirect to repair shields this tick."
  - cmd: "+bridge/vacate"
    description: "Leave whatever station you're currently at."
  - cmd: "vacate"
    description: "Same as +bridge/vacate (bare alias preserved)."
  - cmd: "+bridge/assist pilot"
    description: "Assist the pilot's next roll with +1D (Coordinate bonus)."
---

All commander / bridge-tier verbs live under +bridge/<switch>. Bare
forms (commander, hail, shields, power, damcon, etc.) still work as
aliases. The canonical form is +bridge/<switch>; the rest of this
page uses it everywhere.

See `+help captainorders` for tactical-order mechanics, and
`+help power` for the power-allocation table. This page is the
command reference.

SWITCH REFERENCE
  /claim        Take the commander seat (default — bare +bridge)
  /order <s> <a> Issue tactical order to crew at station (captain-order)
  /hail <t>     Open comms channel with target ship
  /comms        Show comms channels on your ship
  /shields <l>  Set shield level (full / forward / aft / down)
  /power <a>    Show or set power allocation
  /transponder  Set transponder state (on / off / spoofed)
  /resist       Resist tractor beam lock
  /damcon <s>   Damage-control NPC priority
  /vacate       Leave your current station
  /assist <s>   +1D Coordinate bonus to another station's roll
  /coordinate   Cross-station coordination (advanced — see help coord)

CLAIMING THE COMMANDER SEAT

`+bridge` with no switch claims the commander station. On small
ships (YT-1300) there's no dedicated commander — the pilot often
doubles. On larger ships the commander is the captain, and their
Command skill buffs the crew via /coordinate and /order.

`+bridge/vacate` leaves whatever station you're at (not just the
commander seat). Useful when swapping roles mid-combat.

CAPTAIN-ORDERS (R&E + game-original)

`/order <station> <action>` is the commander's tactical command.
Examples:

  +bridge/order pilot evade         Pilot must /evade this round
  +bridge/order pilot close TIE-3   Pilot closes range
  +bridge/order gunner fire TIE-3   Gunner fires at target
  +bridge/order engineer repair shields  Engineer priorities repairs

The commander rolls Command vs Difficulty 10. Success: the crew
member gets a +1D bonus on the ordered action. Critical: +2D.
Fumble: the crew member is rattled, -1D.

This is SEPARATE from `+crew/order` (crew manages hired NPCs).
  - `+crew/order` — direct a hired NPC on your ship (for your
    own crew roster, any station)
  - `+bridge/order` — captain tactical order to any crew at their
    station, rolls Command

Bare `order` still routes to `+crew/order` by registration order
(same as pre-S57b).

COMMS

`/hail <target>` opens a private channel. `/comms` lists available
channels on your ship. See `+help channels` for general comms rules.

SHIELDS AND POWER (R&E p.97+, game-original)

  /shields full      Raise shields to full strength
  /shields forward   Forward-arc only (asymmetric)
  /shields aft       Aft-arc only
  /shields down      Lower shields (necessary to dock, etc.)

  /power             Show reactor allocation:
                       shields / weapons / engines / sensors
  /power shields 4   Allocate 4 pips to shields
  /power shields 4 weapons 2 engines 0  Full reallocation

Reactor output varies by ship template. Fighters typically 4
pips total; light freighters 6–8; capitals 12+. Exceeding total
reactor output rolls Space Transports Repair to prevent overload.

TRANSPONDER (game-original)

  /transponder on           Normal broadcast (default)
  /transponder off          Dark — no ID broadcast (illegal most places)
  /transponder spoofed <id> Broadcast a spoofed ID (requires crafted module)

Running dark attracts patrol attention (Customs flag). Spoofed IDs
pass initial scans but fail `/sensors/deepscan`.

DAMAGE CONTROL

`/damcon <system>` redirects the ship's damage-control NPC (if
any) to prioritize repairing a specific system. Without an assigned
engineer, damage-control uses an NPC auto-priority. With an
engineer PC at the station, the PC does the work via ship-admin
`/repair`.

SHIP MANAGEMENT

  /vacate       Leave your current station
  /assist <station>  +1D to another crew member's next roll
                (copilot-style Coordinate bonus, R&E p.89)
  /coordinate   Advanced cross-station action — see /help coord

RESISTING TRACTOR BEAMS

`/resist` fires when your ship is caught in a tractor beam. Piloting
roll (or Command, whichever is higher) vs the tractor beam's strength.
Success: break free. Failure: continue to be pulled in.

EXAMPLES

  (aboard the Millennium Falcon, combat begins)
  +bridge
  → "You take the commander seat. Tactical station active."

  +bridge/shields full
  → "Shields raised to full. Power drain: 2 pips."

  +bridge/order pilot evade
  → "Kessa: 'Evasive action, aye!' (+1D defense from captain-order)"

  +bridge/hail TIE-3
  → "Opening channel to TIE-3..."

  +bridge/resist
  → "Rolling Piloting + Commander vs tractor beam... Success! You
     break free."

CHEAT SHEET
  +bridge             = take commander seat (also: commander, command, captain)
  +bridge/order <s> <a>  = captain order (also: order — collides with +crew)
  +bridge/hail <t>    = open channel (also: hail)
  +bridge/comms       = comms channels (also: comms, comm, radio)
  +bridge/shields <l> = shield level (also: shields)
  +bridge/power <a>   = power allocation (also: power, pwr)
  +bridge/transponder = transponder state (also: transponder, transp)
  +bridge/resist      = resist tractor (also: resist, breakfree)
  +bridge/damcon <s>  = damage-control NPC (also: damcon, damagecontrol, repair)
  +bridge/vacate      = leave station (also: vacate, unstation)
  +bridge/assist <s>  = +1D bonus (also: assist)
  +bridge/coordinate  = cross-station (also: coordinate, coord)

Sources: R&E p.89 (Command skill, Coordinate), R&E p.97+
(space-combat actions), Imperial Sourcebook chapters on ship
command for flavor. Transponder mechanics are game-original.

THE ORDER COLLISION — FOR THE RECORD

S54–S57a flagged and S57b formally resolves: bare `order` is
claimed by both +crew/order (hired NPCs) and +bridge/order
(captain orders to PC/NPC crew at stations). Registration order
makes crew win the bare word. Use the canonical forms to
disambiguate. Neither side will flip — both are legitimate uses;
the bare word must pick one. Crew wins because it's the more
common day-to-day action.
