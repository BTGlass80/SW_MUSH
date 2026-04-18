---
key: poweralloc
title: Power Allocation
category: "Rules: Space"
summary: The engineer controls power distribution across ship systems.
aliases: [power, reactor, engineering, silentrunning]
see_also: [crew, shields, spacecombat]
---
The engineer controls power distribution across ship systems.

USAGE (engineer station only)
  power                      Show current power allocation
  power engines +1           Shift power to engines
  power silent               Enter silent running mode

SYSTEMS
Each ship has a reactor budget. The engineer allocates power to:
  Engines:   +1 speed per extra point
  Shields:   +1 pip shields per extra point (max +1D)
  Weapons:   +1 pip fire control per extra point (max +1D)
  Sensors:   +1D to scan/deepscan per extra point (max +2D)

Power is zero-sum — boosting one system means starving another.
Systems at 0 power go offline entirely.

SILENT RUNNING
  power silent — engines at minimum (speed 1), shields/weapons/sensors
  all offline. Your ship becomes very difficult to detect (+3D to sensor
  detection difficulty against you). Essential for smugglers and spies.

WITHOUT AN ENGINEER
If no one is at the engineer station, default power allocation applies.
The 'power' command returns: "No one at the engineering console."

REACTOR DAMAGE
Hazard table 'power failure' or ion hits can reduce available power.
The engineer must shed systems to stay within the reduced budget.
