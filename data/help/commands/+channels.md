---
key: +channels
title: +Channels — Communication Channel Overview
category: "Commands: Social"
summary: Show all available communication channels and how to use them.
aliases: [channels, chan, channellist, comlink, cl, clink, fcomm, fc, faction-comm, oocsay]
see_also: [+freqs, +ooc, say, +who]
tags: [social, comms, channels, command]
access_level: 0
examples:
  - cmd: "+channels"
    description: "Show the channel list with your current tuned frequencies."
  - cmd: "channels"
    description: "Alias for +channels."
---

Display the available communication channels — their names, scope, and how to
transmit on each. This is the quick-reference for the entire comms system.

SYNTAX

  +channels
  channels

OUTPUT FORMAT

  === Communication Channels ===
  ooc / newbie      Global OOC chat  (4 player(s) online)
  comlink / cl      Planet-wide IC comlink
  fcomm / fc        Faction channel  (your faction: Republic)
  commfreq / cf     Custom frequency  (tuned: 1138, 501)

CHANNELS

  ooc / newbie      Game-wide out-of-character chat. Use "newbie" for
                    new-player questions — veteran players monitor it.

  comlink / cl      In-character planetary comlink. Heard by everyone
                    on the same planet.

  fcomm / fc        Faction-private channel. Only members of your
                    faction hear it.

  commfreq / cf     Custom private frequency. Only players tuned to the
                    same number hear it.

  +ooc              Local room-only OOC (NOT a broadcast channel;
                    see help +ooc).

HOW TO USE EACH CHANNEL

  ooc <message>
  newbie <message>
  comlink <message>     (alias: cl)
  fcomm <message>       (alias: fc)
  commfreq <freq#> <message>   (alias: cf)

CUSTOM FREQUENCIES

  tune <number>         — subscribe to a frequency (1-9999)
  untune <number>       — unsubscribe
  +freqs                — list frequencies you are tuned to

EXAMPLES

  ooc Anyone want to RP?
  → Broadcast to all online players.

  comlink This is Reyes. Anyone at docking bay four?
  → IC broadcast heard by players on the same planet.

  fcomm Rally at the senate in ten minutes.
  → Private message to your faction only.

  commfreq 1138 Go around.
  → Private message to everyone tuned to frequency 1138.

CHEAT SHEET
  ooc       = global OOC
  comlink   = planet IC
  fcomm     = faction only
  commfreq  = private freq
  +channels = this list
