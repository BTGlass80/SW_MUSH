---
key: investigate
title: Investigate — Resolve a Wilderness Anomaly
category: "Commands: Wilderness"
summary: Attempt to resolve a specific wilderness anomaly by ID. You must be at the anomaly's anchor location. Success grants credits, crafting materials, and faction reputation. Use `anomalies` first to see the active list.
aliases: []
see_also: [anomalies, wilderness, faction, region]
tags: [wilderness, exploration, economy, command]
access_level: 0
examples:
  - cmd: "anomalies"
    description: "List active anomalies in your region (get the ID first)."
  - cmd: "investigate 3"
    description: "Attempt to resolve anomaly #3. Must be at its anchor location."
---

Attempt to resolve a specific wilderness anomaly. Use `anomalies`
first to get the ID and location of available anomalies.

SYNTAX

  investigate <id>

You must be at or adjacent to the anomaly's **anchor location**
(shown in the `anomalies` listing as a grid reference). Attempting
to investigate from the wrong location returns an error and
wastes no resources.

RESOLUTION MODES

Anomalies resolve in one of two modes depending on type:

  Skill-check mode   The server rolls a relevant skill against a
                     difficulty set by the anomaly. Outcome:
                       Success:        Full credit/material reward
                       Partial fail:   Reduced reward (still worth
                                        doing — never a total loss)
                       Hard fail:      No reward, anomaly persists

  Combat mode        (Raider party anomalies) Engaging the anomaly
                     initiates combat. Reward on kill. Fleeing
                     leaves the anomaly active for others.

REWARDS

On success you receive a combination of:

  - Credits (scaled to region security tier and faction influence)
  - Crafting material stacks (metal, organic, chemical, rare)
  - Faction reputation with the anomaly's relevant organisation

The exact skill check used depends on anomaly type. The server
chooses the best pool from relevant skills your character has.

MULTIPLAYER

Multiple players can investigate the same anomaly. Each resolver
gets their own reward roll — you are not splitting a fixed pot.
Combat-mode anomalies support assisted resolution (bring friends).

ANOMALY EXPIRY

Anomalies expire after approximately 30 minutes. If the anomaly
has already timed out when you investigate, you get a message
and no reward is deducted.

EXAMPLES

  anomalies
  → [1] Salvage Cache — 24m remaining  (grid F-3)
    [3] Raider Party  — 08m remaining  (grid B-7)

  (move to grid F-3)
  investigate 1
  → Roll Mechanics 3D vs DC 8 … success (margin +4)
  → +120cr. +2t metal (quality 72). +5 Separatist Watch rep.

  investigate 3
  → You are not near anomaly #3. Travel to grid B-7 first.

CHEAT SHEET
  anomalies       = list active anomalies and their IDs
  investigate N   = resolve anomaly N (must be at its location)
