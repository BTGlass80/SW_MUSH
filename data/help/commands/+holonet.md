---
key: +holonet
title: HoloNet — Galactic News Browser
category: "Commands: Social"
summary: Opens the HoloNet galactic news browser (web client only). Displays live world events and fixture news stories. Telnet gets a brief text notice.
aliases: [holonet]
see_also: [news, space, world, channels]
tags: [news, social, web, command]
access_level: 0
examples:
  - cmd: "+holonet"
    description: "Open the HoloNet browser modal (web client) showing live world events and galactic news."
  - cmd: "holonet"
    description: "Same as +holonet (bare alias preserved)."
---

Opens the HoloNet galactic news browser. Web client only — Telnet
players see a brief text notice instead.

The HoloNet modal has two panes:

  LEFT PANE   Fixture news stories curated by the GNN feed.
  RIGHT PANE  Live world events from the Director — contest
              resolutions, faction victories, weather events,
              and any other dynamic world-state the Director
              has logged.

TELNET DEGRADATION

Telnet sessions receive:
  "=== HoloNet requires the web client ==="

The bare `news` command works on both Telnet and web and shows
the most recent Director log entries as plain text.

DATA SOURCE

Live events come from `world_events.get_world_event_manager()`.
They mirror the Director's recent log — the same events visible
in the right panel of the HoloNet modal update as the Director
processes them. No separate API call is made; the server sends
a `holonet_state` JSON event with the current snapshot.

EXAMPLES

  +holonet
  → Opens the HoloNet browser modal.

  holonet
  → Same — bare alias for players who don't like the + prefix.

  news
  → Text listing of recent Director log entries (works on Telnet).

CHEAT SHEET
  +holonet    = open HoloNet browser (web) / text notice (Telnet)
  holonet     = same (bare alias)
  news        = plain-text recent events (Telnet-safe)
