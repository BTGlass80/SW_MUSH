---
key: rally
title: Rally — Community Uprising Response
category: "Commands: Social"
summary: View the active dark-side cult uprising threat board and make a strike against it. Collaborative community event — every player's strike pushes the menace meter down. Strike cooldown ~10 minutes. Rewards Republic rep and a status flag on victory.
aliases: [front, +rally]
see_also: [+faction, +reputation, +threat, +events]
tags: [social, faction, community, command]
access_level: 0
examples:
  - cmd: "rally"
    description: "Display the active uprising threat board — cult identity, location, menace level, and community progress."
  - cmd: "rally strike"
    description: "Make your move against the cult — rolls your best pool across playstyle, pushes menace down."
---

`rally` is the community response to a **dark-side cult uprising**
— a director-driven event where a villain or cult emerges and
threatens the galaxy. The threat board tracks community progress;
when menace reaches zero, the uprising is defeated.

VIEWING THE BOARD

  rally     Display the threat board:
              - Who the threat is (cult/villain identity)
              - Location or zone they are operating from
              - Menace meter (current % of maximum)
              - Remaining strikes needed to win
              - Win/lose state if the event has resolved

MAKING A STRIKE

  rally strike     Record your participation against the cult.

The server picks the best pool from your character's skills
across playstyles:

  Soldier        Combat skill (direct assault)
  Slicer         Tech skill (disrupting their operations)
  Face           Social skill (rallying civilians against them)
  Jedi           Force skill (pushing back the dark side)

You do not need to be in a specific location to strike. Strikes
represent your contribution to the galaxy-wide effort.

COOLDOWN

Each strike counts once per ~10 minutes per character. Spamming
`rally strike` returns a cooldown notice. The menace meter moves
from the community's total effort — one person cannot solo it.

REWARDS

  Victory   Republic reputation gain for all participants
            who struck during the event window. A special
            status flag ("Defended the Republic") awarded
            to active participants.
  Defeat    The cult achieves its goal. Director logs a
            world-event. No reward.

There are no credit rewards for rally events — these are
reputation and roleplay economy, not credit economy.

ACTIVE vs INACTIVE

If no uprising is active, `rally` returns:

  "No active uprising. Check +events for upcoming threats."

Check `+events` or the HoloNet (`+holonet`) for upcoming events.

EXAMPLES

  rally
  → === MENACE ALERT: The Umbral Conclave ===
    Location: Undercity, Coruscant
    Menace: ████████░░░░ 67% (33 strikes to defeat)
    Participants: 12 active

  rally strike
  → You rally the locals against the cult's influence.
  → Roll Persuasion 4D vs DC 8 … success.
  → Menace reduced. (Strike cooldown: 10 min)

  rally strike       (immediately after)
  → You've already acted against the Conclave. (8m remaining)

CHEAT SHEET
  rally           = view uprising threat board
  rally strike    = contribute your strike (10m cooldown)
  front           = alias for rally
