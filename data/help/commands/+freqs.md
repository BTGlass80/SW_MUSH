---
key: +freqs
title: +Freqs — Tuned Comlink Frequencies
category: "Commands: Social"
summary: List the custom comlink frequencies you are currently subscribed to.
aliases: [freqs, frequencies, myfreqs, tune, tunein, untune, tuneout, commfreq, cf, freq]
see_also: [+channels, +ooc, say]
tags: [social, comms, frequency, command]
access_level: 0
examples:
  - cmd: "+freqs"
    description: "Show all custom frequencies you are tuned to."
  - cmd: "freqs"
    description: "Alias for +freqs."
  - cmd: "tune 1138"
    description: "Subscribe to frequency 1138."
  - cmd: "commfreq 1138 Meet at docking bay in five minutes."
    description: "Transmit on frequency 1138."
  - cmd: "untune 1138"
    description: "Unsubscribe from frequency 1138."
---

Show the custom comlink frequencies you are currently tuned to, and the
command to transmit on each. Frequencies are private channels — only players
who have tuned in hear transmissions.

SYNTAX

  +freqs
  freqs

MANAGING FREQUENCIES

  tune <number>         — subscribe to a frequency (1-9999)
  untune <number>       — unsubscribe
  commfreq <num> <msg>  — transmit on a frequency you are tuned to
  cf <num> <msg>        — short alias for commfreq

OUTPUT FORMAT

  === Tuned Frequencies ===
    1138  -- transmit: commfreq 1138 <message>
    501   -- transmit: commfreq 501 <message>

NOTES

  • Frequencies are not persistent — you are untuned if you log out or
    the server restarts. Re-tune at login start with "tune <number>".
  • Only players tuned to the same frequency hear your transmissions.
  • Frequency numbers range from 1 to 9999.

EXAMPLES

  +freqs
  → Show your currently tuned frequencies.

  tune 1138
  → Subscribe to frequency 1138.

  commfreq 1138 Ready when you are.
  → Send IC message to everyone on frequency 1138.

  untune 1138
  → Leave frequency 1138.

CHEAT SHEET
  +freqs          = list my tuned frequencies
  tune <n>        = subscribe to frequency n
  untune <n>      = unsubscribe
  commfreq <n> <msg> = transmit on frequency n
