---
key: space
title: Space Travel
category: "Rules: Space"
summary: Space travel in SW_MUSH uses a zone-based model.
aliases: [spaceflight, travel]
see_also: [spacecombat, crew, hyperdrive, +ship]
---
Space travel in SW_MUSH uses a zone-based model. Ships move between
named zones rather than tracking exact coordinates. Four planets are
connected by three hyperspace lanes across 16 zones.

BASIC OPERATIONS
  board              Board a docked ship
  launch             Take off from a docking bay (pilot only)
  land               Land at the planet below (pilot only, orbit/dock zone)
  disembark          Leave a docked ship
  course <zone>      Navigate to an adjacent zone (pilot only)
  hyperspace <dest>  Jump to another star system (pilot only)

THE GALAXY
  4 planets: Tatooine, Nar Shaddaa, Kessel, Corellia
  16 zones connected by 3 hyperspace lanes
  Type '+help zonemap' for the full zone graph.

CREW STATIONS
Ships have 7 crew stations. Each grants different abilities.
Type '+help crew' for details on each station.

SHIP STATUS
  +ship/status (ss)  Your current ship's status and crew
  +ship/info <n>     Detailed stats on a ship type
  +ships             Browse all ships in the zone
  +myships           Ships you own

SPACE ACTIVITIES
  Combat: fire, evade, close, flee, tail — see '+help spacecombat'
  Scanning: scan, deepscan — see '+help sensors' and '+help anomalies'
  Salvage: salvage wreckage for crafting resources — '+help salvage'
  Smuggling: run contraband between planets — '+help smuggling'
  Customization: craft and install ship mods — '+help shipmod'
