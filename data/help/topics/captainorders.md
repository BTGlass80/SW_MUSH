---
key: captainorders
title: "Captain's Orders"
category: "Rules: Space"
summary: The Commander station can issue tactical orders that apply ship-wide bonuses with meaningful tradeoffs.
aliases: [orders, order, tacticalorders]
see_also: [crew, spacecombat]
---
The Commander station can issue tactical orders that apply ship-wide
bonuses with meaningful tradeoffs.

USAGE (commander station only)
  order                      Show current order
  order <name>               Issue a tactical order
  order cancel               Cancel current order

ORDERS
  Battle Stations     +1D fire control (all gunners)  / -1D maneuverability
  Evasive Pattern     +2D maneuverability (pilot)     / -1D fire control
  All Power Forward   +2 speed                        / -1D shields, no rear fire
  Hold the Line       +2D shields                     / -2 speed, can't flee
  Silent Running      +3D sensor stealth              / No weapons, shields off
  Boarding Action     +1D melee/brawl (boarding crew) / -1D piloting
  Concentrate Fire    +2D damage (one weapon)         / Other weapons offline
  Coordinate          +1D all crew checks             / No tradeoff

SKILL CHECK
Issuing an order requires a Command skill check (Easy, difficulty 8).
Failure: order not issued. Fumble: random order takes effect for 30s.

Orders take effect immediately and persist until changed, cancelled,
or the Commander vacates the station.
