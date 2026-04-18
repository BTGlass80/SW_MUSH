---
key: +spy
title: Spy — Espionage, Assess, Eavesdrop, Investigate, Intel
category: "Commands: Social"
summary: All espionage verbs under +spy/<switch>. Assess a target's combat readiness, eavesdrop on nearby conversations, investigate a room for clues, manage intel reports, or intercept comms channels.
aliases: [assess, size, eavesdrop, listen, investigate, search, inspect, intel, intercept, wiretap, comtap]
see_also: [perception, search, streetwise, sensors, intel]
tags: [social, espionage, stealth, command]
access_level: 0
examples:
  - cmd: "+spy"
    description: "Defaults to /assess — size up the nearest target (if any)."
  - cmd: "+spy/assess Greedo"
    description: "Size up Greedo — reveals rough skill dice, gear, attitude. Perception roll."
  - cmd: "assess Greedo"
    description: "Same as +spy/assess (bare alias preserved)."
  - cmd: "size Greedo"
    description: "Another bare alias for /assess."
  - cmd: "+spy/eavesdrop"
    description: "Listen in on nearby conversations. Perception + Streetwise roll vs Difficulty."
  - cmd: "listen"
    description: "Same as +spy/eavesdrop (bare alias preserved)."
  - cmd: "+spy/investigate"
    description: "Search the current room for clues, hidden objects, evidence. Search skill roll."
  - cmd: "search"
    description: "Same as +spy/investigate (bare alias preserved)."
  - cmd: "inspect"
    description: "Another bare alias for /investigate."
  - cmd: "+spy/intel"
    description: "Open your intel report workspace — list drafts, view sealed reports."
  - cmd: "intel"
    description: "Same as +spy/intel (bare alias preserved)."
  - cmd: "+spy/intel create Imperial Patrol Routes"
    description: "Create a new intel report draft."
  - cmd: "+spy/intel add Patrols rotate at 0600 standard"
    description: "Add a line to the current draft."
  - cmd: "+spy/intel seal"
    description: "Finalize the draft — becomes a sealed intel report (valuable to faction agents)."
  - cmd: "+spy/intercept imperial_comms"
    description: "Attempt to wiretap a comms channel. Slicer + Computer Programming roll."
  - cmd: "wiretap imperial_comms"
    description: "Same as +spy/intercept (bare alias preserved)."
---

All espionage verbs live under +spy/<switch>. Bare forms (assess,
listen, search, intel, wiretap) still work as aliases.

See `+help perception` for Perception skill mechanics and
`+help search` for the Search skill. This page is the command
reference.

SWITCH REFERENCE
  /assess      Size up a target — gear, skills, attitude (default)
  /eavesdrop   Listen to nearby conversations (passive)
  /investigate Search a room for clues / hidden objects
  /intel       Intel report workspace
  /intercept   Wiretap a comms channel (slicer action)

/assess  (default)

Perception roll against the target's Sneak or (passive Perception).
Reveals:
  - Rough skill-dice estimate (Novice / Skilled / Veteran / etc.)
  - Visible gear (armor, weapons, obvious mods)
  - Attitude toward you (friendly / neutral / hostile)
  - Faction affiliation if obvious (uniformed, insignia)

Critical success reveals subtle details (concealed weapons, faction
ties through mannerisms). Fumble may return misleading info.

/eavesdrop

Passive listening check against nearby speakers' Streetwise (for
casual talk) or Con (if they're hiding something). You hear pieces
of conversations rather than full transcripts — gossip, deal
fragments, names mentioned.

/investigate

Search the current room for hidden objects, fresh tracks,
bloodstains, datapad fragments, etc. Search skill vs Difficulty.
Some rooms have scripted clues accessible only via /investigate.

/intel — REPORT WORKSPACE (forwards to IntelCommand)

`+spy/intel` opens your intel workspace. IntelCommand uses
positional subcommands:
  +spy/intel                    View workspace (default)
  +spy/intel create <title>     Start a new draft
  +spy/intel add <text>         Add a line to the draft
  +spy/intel seal               Finalize — becomes sealed report
  +spy/intel discard            Discard the current draft
  +spy/intel list               List your sealed reports

Sealed reports are valuable — faction agents (Rebel, Imperial)
pay credits and reputation for sealed intel relevant to their
ongoing operations. See `+help intel` for the economy of intel.

/intercept

Attempt to wiretap a comms channel. Slicer + Computer Programming
vs the channel's encryption difficulty. Imperial channels are
Heroic (30+); civilian channels are Moderate (15). Failed attempts
alert the channel owner.

CHEAT SHEET
  +spy             = assess (also: assess, size)
  +spy/assess      = size up target
  +spy/eavesdrop   = listen nearby (also: listen)
  +spy/investigate = search room (also: search, inspect)
  +spy/intel       = intel workspace (also: intel)
  +spy/intercept   = wiretap channel (also: wiretap, comtap)

NAMING NOTE

`parser.espionage_commands.ScanCommand` has key="assess" (NOT
"scan") — it was renamed pre-sweep to avoid collision with
`parser.space_commands.ScanCommand` (the sensor scan). The
umbrella's /assess switch dispatches to the espionage ScanCommand;
/scan in +sensors dispatches to the space one. Two different
commands, two different canonical forms, no collision.

Sources: R&E Perception (p.91), Search (p.93), Streetwise (p.91),
Con (p.91), Computer Programming/Repair (p.93). Intel-report
economy is game-original.
