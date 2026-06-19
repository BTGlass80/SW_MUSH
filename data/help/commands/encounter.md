---
key: encounter
title: Encounter — Space Encounter Status and Response
category: "Commands: Space"
summary: Commands for handling active space encounters — customs patrols, pirate demands, distress signals, and multi-crew events. View status, respond to choices, or act from your station.
aliases: [enc, respond, resp, stationact, sa, encounters]
see_also: [+pilot, +sensors, pay, +bridge, +gunner]
tags: [space, encounter, command]
access_level: 0
examples:
  - cmd: "encounter"
    description: "Display the current encounter status and available choices."
  - cmd: "enc"
    description: "Short alias — same as encounter."
  - cmd: "respond 1"
    description: "Choose option 1 in an active encounter (customs patrol, pirate demand, etc.)."
  - cmd: "respond bluff"
    description: "Choose a response by name instead of number."
  - cmd: "stationact 1"
    description: "Perform station-specific action 1 during a multi-crew encounter."
  - cmd: "sa hide_cargo"
    description: "Perform a named station action (short alias for stationact)."
---

Space encounters interrupt travel with events that require a crew
decision — customs inspections, pirate demands, distress signals,
anomalous contacts, and more.

**encounter / enc**

Show the current encounter and its available response options. If no
encounter is active, reports nothing. Run this after hearing an
encounter announcement to see the choices.

    encounter    — display active encounter + choice list
    enc          — short alias

**respond / resp**

Select your response to the encounter. Choose by number or by name.

    respond 1            — choose option #1
    respond 2            — choose option #2
    respond bluff        — choose by name

The response may trigger a skill check depending on the option — a
smuggler bluffing a customs patrol rolls Persuasion, for example.

**stationact / sa**

During multi-crew encounters, each bridge station (pilot, gunner,
engineer, sensors) may have station-specific actions beyond the
standard response options.

    stationact 1             — perform station action #1
    stationact hide_cargo    — perform by name
    sa 2                     — short alias for stationact

**Resolution:** Options that trigger skill checks use
`perform_skill_check()` and report the result inline. Some choices
cost credits (see `pay` for pirate tribute).

**See also:** `pay` to transfer credits to pirates; `+sensors` for
anomaly scanning; `+pilot` / `+bridge` / `+gunner` for station roles.
