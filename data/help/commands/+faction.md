---
key: +faction
title: Faction — Allegiance, Guild, Specialization, Reputation
category: "Commands: Social"
summary: All faction verbs under +faction/<switch>. View your faction, manage guild membership, choose a specialization, or check reputation standings. Includes forwarding for faction subcommands (join, leave, list, roster, missions, claim, etc.).
aliases: [fac, guild, "+guild", specialize, specialise, reputation, rep, "+rep", "+reputation"]
see_also: [factions, guilds, reputation, territory, organizations]
tags: [social, faction, guild, reputation, command]
access_level: 0
examples:
  - cmd: "+faction"
    description: "View your faction status (default — your allegiance, rank, reputation)."
  - cmd: "faction"
    description: "Same as +faction (bare alias preserved)."
  - cmd: "fac"
    description: "Short bare alias."
  - cmd: "+faction/view"
    description: "Same as default — faction status."
  - cmd: "+faction/list"
    description: "List all factions you can join (forwarded to FactionCommand)."
  - cmd: "+faction/join rebel"
    description: "Join the Rebel Alliance (forwarded to FactionCommand's positional parser)."
  - cmd: "+faction/leave"
    description: "Leave your current faction (forwarded)."
  - cmd: "+faction/roster"
    description: "List your faction's active members (forwarded)."
  - cmd: "+faction/missions"
    description: "View faction-specific mission board (forwarded)."
  - cmd: "+faction/claim territory-key"
    description: "Claim territory for your faction (forwarded; leader-only)."
  - cmd: "+faction/guild"
    description: "View your guild membership and perks."
  - cmd: "guild"
    description: "Same as +faction/guild (bare alias preserved)."
  - cmd: "+faction/specialize Pilot"
    description: "Choose a specialization within your faction (unlocks advanced skills)."
  - cmd: "specialize Slicer"
    description: "Same as +faction/specialize (bare alias preserved)."
  - cmd: "+faction/reputation"
    description: "View your reputation with all factions (standings, modifiers)."
  - cmd: "reputation"
    description: "Same as +faction/reputation (bare alias preserved)."
  - cmd: "rep"
    description: "Short bare alias for /reputation."
---

All faction verbs live under +faction/<switch>. Bare forms (faction,
guild, specialize, reputation, rep) still work as aliases.

See `+help factions` for the conceptual overview of the Rebellion,
Empire, criminal cartels, and independent factions. This page is
the command reference.

SWITCH REFERENCE
  /view         Faction status (default — bare +faction)
  /guild        Your guild membership
  /specialize   Choose a specialization
  /reputation   Reputation standings with all factions

  POSITIONAL SUBCOMMANDS (forwarded to FactionCommand):
  /list         List joinable factions
  /join <n>  Join a faction
  /leave        Leave current faction
  /info <n>  Detailed info on a faction
  /roster       List faction members
  /missions     Faction mission board
  /channel      Faction comms channel
  /requisition  Requisition gear (rank-gated)
  /invest <cr>  Invest credits in faction coffers
  /influence    Faction influence / territory status
  /territory    Same as /influence
  /claim        Claim territory (leader-only)
  /unclaim      Relinquish territory
  /guard        Post guards at a territory
  /armory       Faction armory access
  /seize        Admin seize (coup flow)
  /hq           View/set faction HQ

  LEADER SUBCOMMANDS (also forwarded):
  /promote, /demote, /kick, /invite, /motd, /setrank, /disband,
  /treasury, /payroll

FACTION OVERVIEW

Factions are organized groups with ranks, shared resources, and
missions. The core factions include:

  Rebel Alliance      — insurgency against the Empire (Light)
  Galactic Empire     — official galactic government (Dark)
  Hutt Cartel         — crime syndicate (Neutral, dark-lean)
  Czerka Corporation  — mega-corp (Neutral, greedy)
  + independent factions (Mandalorians, Bounty Hunter Guild, etc.)

Joining a faction unlocks:
  - Faction-only missions and comms channels
  - Rank progression (earn reputation → rise in rank)
  - Requisition access (gear at discount based on rank)
  - Territory operations (claim/hold zones)

CRAFTING A SPECIALIZATION

Within a faction, you can /specialize to focus on a role:
  Pilot / Gunner / Medic / Slicer / Infiltrator / Commando / Scout

Specialization unlocks advanced skills specific to the role. You
can only have one active specialization at a time; switching
costs CP and time.

REPUTATION SYSTEM

Reputation is tracked per-faction. /reputation shows:
  - Your standing with each faction (-1000 Hated .. +1000 Exalted)
  - Current modifiers on prices, dialogue, mission availability
  - Thresholds to the next reputation tier

Reputation is earned via missions, public actions, and combat
against faction enemies. It decays slowly if not maintained.

THE UMBRELLA FORWARDING PATTERN (S58)

FactionCommand uses positional-argument subcommands (join, leave,
list, roster, missions, etc.) rather than switch syntax. The
+faction umbrella recognizes all FactionCommand subcommands as
switches and forwards them — so `+faction/join rebel` reaches
FactionCommand as `faction join rebel` and works identically.

This forwarding is transparent — you can type either form:
  +faction/join rebel         (canonical)
  faction join rebel          (legacy bare form)
Both reach the same code.

CHEAT SHEET
  +faction             = view (also: faction, fac)
  +faction/join <n> = join (forwarded)
  +faction/leave       = leave (forwarded)
  +faction/list        = list joinable (forwarded)
  +faction/guild       = guild (also: guild)
  +faction/specialize  = pick spec (also: specialize)
  +faction/reputation  = rep standings (also: reputation, rep)
  +faction/roster      = members (forwarded)
  +faction/missions    = faction jobs (forwarded)
  +faction/claim       = take territory (forwarded, leader-only)

Sources: Faction system is game-original (inspired by
SWG Rebel/Imperial split, EVE sovereignty, TORN crime). R&E
Command skill (p.89) informs leader coordination rolls. Organ-
ization mechanics live in `engine/organizations.py`.
