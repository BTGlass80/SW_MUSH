---
key: +sabacc
title: Sabacc — Card Gambling
category: "Commands: Social"
summary: Start or join a sabacc game. Single-action command — classic Star Wars card gambling. Risk credits, bluff opponents, and build a rogue reputation. Bare forms (sabacc, gamble, cards) still work.
aliases: [sabacc, gamble, cards]
see_also: [cantinas, economy, social]
tags: [social, gambling, sabacc, command]
access_level: 0
examples:
  - cmd: "+sabacc"
    description: "Start a new sabacc game at your table, or join an existing game in the room."
  - cmd: "sabacc"
    description: "Same as +sabacc (bare alias preserved)."
  - cmd: "gamble"
    description: "Another bare alias — equivalent to +sabacc."
  - cmd: "cards"
    description: "Bare alias — start/join a game."
  - cmd: "+sabacc 100"
    description: "Set an ante of 100 credits when starting a game."
  - cmd: "+sabacc join"
    description: "Join an existing game at your table (if any)."
  - cmd: "+sabacc fold"
    description: "Fold your current hand."
  - cmd: "+sabacc call"
    description: "Call the current bet."
  - cmd: "+sabacc raise 50"
    description: "Raise the bet by 50 credits."
  - cmd: "+sabacc reveal"
    description: "Reveal your hand at showdown."
---

The +sabacc command starts or joins a sabacc game. Bare forms
(sabacc, gamble, cards) still work as aliases.

See `+help gambling` for the conceptual overview of the sabacc
economy in cantinas and private dens.

SABACC BASICS

Sabacc is the classic Star Wars card game — played for high stakes
in every cantina. The rules:
  - 2-card hand to start; players bet in rounds
  - Dealer may offer exchanges (draw/discard)
  - Target values (card sums) shift each round via sabacc shifts
    (random events)
  - Closest to +23 or -23 (without going over) wins; the Idiot's
    Array (0, 2, 3) is an automatic win
  - Betting, bluffing, and card-reading are as important as luck

SESSION FLOW

1. `+sabacc` to start or join a game. If a game exists at your
   table, you join it. Otherwise you open a new table and wait
   for others to join.
2. Set ante with `+sabacc <amount>` (default: 50 credits).
3. Play rounds: `+sabacc call`, `/raise <amount>`, `/fold`,
   `/reveal`.
4. Winner takes the pot. Reputation notes: winning big in public
   earns you a rogue-charm flavor tag.

WHY NO UMBRELLA CLASS?

Per the S57b convention for single-action commands, +sabacc is
a single command with internal positional subcommands (join, fold,
call, raise, reveal) rather than a multi-class umbrella. The
canonical +sabacc form is added as an alias on SabaccCommand for
naming consistency with the rest of the S54-S58 sweep.

CHEAT SHEET
  +sabacc           = start/join game (also: sabacc, gamble, cards)
  +sabacc <ante>    = set ante
  +sabacc join      = join existing game
  +sabacc call      = call bet
  +sabacc raise <n> = raise bet
  +sabacc fold      = fold hand
  +sabacc reveal    = showdown

Sources: Sabacc rules adapted from canonical Star Wars sources
(Han Solo winning the Millennium Falcon from Lando being the
archetypal example). Betting and bluffing mechanics are
game-original; use standard R&E Gambling / Con rolls where relevant.
