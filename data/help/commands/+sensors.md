---
key: +sensors
title: Sensors — Sensor Station, Scanning, and Deep Analysis
category: "Commands: Ships"
summary: All sensor verbs live under +sensors/<switch>. Take the sensor seat, scan the zone for contacts, or run deep-scan analysis on a specific target. Every sensor verb is a switch here.
aliases: [sensors, sensor, scan, deepscan]
see_also: [+pilot, +gunner, +bridge, +ship, contacts, anomalies, transponder]
tags: [ships, sensors, command]
access_level: 0
examples:
  - cmd: "+sensors"
    description: "Take the sensors seat (default — /claim)."
  - cmd: "sensors"
    description: "Same as +sensors (bare alias preserved)."
  - cmd: "sensor"
    description: "Another bare alias for the sensors station."
  - cmd: "+sensors/claim"
    description: "Take the sensors seat (same as default)."
  - cmd: "+sensors/scan"
    description: "Passive sensor sweep of the current zone — lists all contacts (ships, anomalies)."
  - cmd: "scan"
    description: "Same as +sensors/scan (bare alias preserved)."
  - cmd: "+sensors/deepscan"
    description: "Active deep-scan — higher precision, reveals transponder details and threat levels. Attracts attention."
  - cmd: "deepscan"
    description: "Same as +sensors/deepscan (bare alias preserved)."
  - cmd: "+sensors/scan 3"
    description: "Scan contact #3 specifically — detailed analysis of that ship."
  - cmd: "+sensors/deepscan 2"
    description: "Deep-scan contact #2 — runs the full sensor-operator workup."
  - cmd: "scan"
    description: "If sensors is unoccupied, pilot can roll with -1D penalty (no dedicated operator)."
  - cmd: "+sensors"
    description: "Get sensor seat status line if already occupied."
  - cmd: "+sensors/scan"
    description: "Good at the start of a combat round — identify the hostiles before declaring attacks."
  - cmd: "+sensors/deepscan"
    description: "Ideal against a transponder-spoofed target — reveals the true identity on success."
---

All sensor verbs are switches under +sensors. Bare forms (scan,
deepscan) still work as aliases. The canonical form is
+sensors/<switch>; the rest of this page uses it everywhere.

See `+help contacts` for the conceptual overview of sensor contacts
and the scan/deepscan distinction. This page is the command reference.

SWITCH REFERENCE
  /claim      Take the sensors seat (default — bare +sensors)
  /scan       Passive sensor sweep of the zone
  /deepscan   Active deep-scan (precise, attracts attention)

SEATING THE SENSOR OPERATOR

`+sensors` with no switch claims the sensor station. On ships with
dedicated sensor rigs (capital, specialist freighters), the operator
gets a +2D scan bonus on the Sensors skill. Without an operator,
the pilot can run sensors but at -1D (divided attention).

SCAN VS DEEPSCAN

`/scan` is passive — it listens for transponder emissions,
electromagnetic signatures, and hyperspace wakes. Returns a contact
list (ship name, estimated range, threat flag, heading). Does NOT
reveal:
  - True identity behind a spoofed transponder
  - Weapons loadout or hull status
  - Jump destination programmed into another ship's nav computer

`/deepscan <target>` is active — directed energy probe and high-gain
analysis on a specific contact. Returns:
  - True ship template (even behind a false transponder)
  - Estimated hull damage, shields status
  - Weapons hot/cold state
  - Faction affiliation if known

Deepscan is NOTICEABLE. The target gets a sensor-hit alert and
hostile NPCs may treat being deepscanned as a provocation.
Transponder spoofers spook particularly.

SENSOR DIFFICULTIES (R&E p.93)

  Scan, same zone          Very Easy (5)
  Scan, adjacent zone      Easy (10)
  Deepscan vs in-zone      Easy (10)
  Deepscan vs transponder  Moderate (15)
  Deepscan vs transponder  Difficult (20) if lockdown-grade false ID
  Anomaly detection        Difficult (20) — anomalies are subtle

Wild Die affects precision. Critical successes reveal unusual details
(like a rebel-aligned pilot's discreet faction emblem). Fumbles may
return false data.

EXAMPLES

  (space combat, aboard your ship)
  +sensors
  → "You take the sensors seat. Stations online."

  +sensors/scan
  → "Contacts in zone: 3. [1] TIE-Alpha (range medium, hostile),
     [2] Jex's Freighter (range short, friendly), [3] Unknown
     (range long, transponder=CORUSCANT_03142)"

  +sensors/deepscan 3
  → "Deep scan of Unknown... spoofed transponder detected. True
     ID: GR-75 medium transport. Hull damage: light. Rebel Alliance
     markings visible on underside."

CHEAT SHEET
  +sensors           = take sensor seat (also: sensors, sensor)
  +sensors/scan      = zone sweep (also: scan)
  +sensors/deepscan  = active probe (also: deepscan)

Sources: R&E p.93 (Sensors skill), game-original deep-scan mechanic
(no direct R&E equivalent — WEG D6 doesn't formalize sensor states).
