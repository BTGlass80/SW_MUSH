---
key: npccrew
title: NPC Crew Members
category: "Rules: Space"
summary: You can hire NPC crew members to fill stations on your ship.
aliases: [hirecrew, npchire, npcpilot, npcgunner, crewwages]
see_also: [crew, spacecombat, +roster]
---
You can hire NPC crew members to fill stations on your ship. They act
autonomously during space combat and draw a regular wage.

HIRING
  hire                       View the hiring board at a cantina/spaceport
  assign <npc> <station>     Assign a hired NPC to a crew station
  unassign <npc>             Remove an NPC from their station
  dismiss <npc>              Fire an NPC crew member
  +roster                    View your hired crew and their assignments

WHAT NPC CREW DO IN COMBAT
NPC crew auto-act every tick when enemies are in sensor range:

  NPC Pilot:    Maneuvers based on behavior profile (aggressive = close/tail,
                defensive = evade, cowardly = flee). Rolls their actual Space
                Transports skill vs. enemy pilot.
  NPC Gunner:   Fires their assigned weapon at the nearest enemy in arc and
                range. Full attack resolution — damage, hull rolls, system
                hits. Multiple gunners fire independently.
  NPC Engineer: Auto-repairs damaged systems in priority order: engines,
                shields, weapons, sensors, hyperdrive. If all systems are
                fine, repairs hull damage instead. Rolls repair skill.
  NPC Copilot:  Provides a passive +1D assist bonus to pilot actions.

PLAYER ORDERS
You can override NPC behavior with the 'order' command:
  order pilot close          Tell NPC pilot to close range
  order pilot flee           Tell NPC pilot to break away
  order engineer repair shields  Prioritize shield repair

Orders are consumed after execution — the NPC reverts to default behavior
the next tick unless you issue another order.

BEHAVIOR PROFILES
NPC pilots have a behavior profile set in their AI config:
  Aggressive: closes range, tries to tail
  Defensive:  evades and holds position
  Cowardly:   flees from combat
  Berserk:    charges in recklessly
  Sniper:     evades while letting gunners do the work

WAGES
NPC crew cost credits. Four wage tiers exist. Wages fire every 14,400
ticks (roughly 4 hours). If you can't cover wages, you risk losing crew.

  +roster shows each NPC's station and daily wage.

LIMITATIONS
NPC crew do NOT currently handle:
  - Deep scanning for anomalies (sensors station)
  - Sublight navigation via 'course' (pilot station)
  - Power allocation (engineer station)
  - Captain's orders (commander station)
These systems require a human crew member. A player crew is always more
effective than NPCs, but hired crew makes solo spaceflight viable.

NARRATIVE OUTPUT
NPC actions broadcast to the bridge with colored station tags:
  [HELM]        Pilot maneuvers
  [WEAPONS]     Gunner attacks
  [ENGINEERING] Engineer repairs
