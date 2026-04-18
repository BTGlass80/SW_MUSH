---
key: anomalies
title: Space Anomaly Scanning
category: "Rules: Space"
summary: "Anomalies are hidden points of interest in space — derelict ships, distress signals, pirate nests, and more."
aliases: [anomaly, deepscan, deepscanning]
see_also: [sensors, salvage, navigation]
---
Anomalies are hidden points of interest in space — derelict ships,
distress signals, pirate nests, and more. Finding them is the sensors
station's primary non-combat purpose.

SCANNING FOR ANOMALIES
  deepscan                   Scan for anomalies in current zone
  deepscan <id>              Focus on a specific detected anomaly

Anomaly resolution is iterative — like detective work, not a button press:
  1st scan: Detect something is there (33% resolved)
  2nd scan: Learn the general type (66% resolved)
  3rd scan: Fully resolved — navigate to investigate

Critical success on any scan skips one step. Fumble garbles the signal
for 60 seconds.

ANOMALY TYPES (7 total)
  Derelict Ship (30%)     Salvageable components, credits
  Distress Signal (20%)   Rescue opportunity — or pirate ambush
  Hidden Cache (15%)      Credits, rare resources, schematics
  Pirate Nest (15%)       2-3 hostile pirates, good salvage
  Mineral Vein (10%)      High-quality crafting resources
  Imperial Dead Drop (5%) Big credits, but Imperial patrol risk
  Mynock Colony (5%)      Hull parasites — nuisance only

INVESTIGATING
Once resolved, the pilot types 'course anomaly <id>' to navigate there
(10-second transit). The encounter auto-triggers on arrival.

SPAWNING
Anomalies spawn every 5 minutes in zones with player ships present.
Deep space zones: 15% chance. Orbit: 10%. Hyperspace lanes: 5%.
Dock zones: never. Max 2 anomalies per zone.
