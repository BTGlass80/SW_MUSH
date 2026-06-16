---
key: anomalies
title: Anomalies — Wilderness Anomaly Scanner
category: "Commands: Wilderness"
summary: List active wilderness anomalies in your current region. Anomalies are timed events (stranded patrols, salvage caches, raider parties, crashed droids) that grant credits, materials, and faction influence when resolved with `investigate`.
aliases: [anom]
see_also: [investigate, wilderness, faction, region]
tags: [wilderness, exploration, economy, command]
access_level: 0
examples:
  - cmd: "anomalies"
    description: "List all active anomalies in your current wilderness region with their IDs and time remaining."
  - cmd: "anom"
    description: "Short alias — same as anomalies."
  - cmd: "investigate 3"
    description: "Attempt to resolve anomaly #3 (must be at its anchor location)."
---

Scans for active wilderness anomalies in your current region.
Anomalies are short-lived, time-limited events that spawn in
wilderness — each one is an opportunity to earn credits, crafting
materials, or faction influence.

ANOMALY TYPES

  Stranded patrol    A clone or militia unit in trouble.
  Salvage cache      Debris field hiding useful components.
  Raider party       Hostile group pinned by terrain or damage.
  Crashed droid      Recon unit with recoverable data or parts.

Each type has its own resolution flavour but all are handled
through `investigate`.

LISTING

`anomalies` shows every active anomaly in your region:

  [1] Salvage Cache  — 24m remaining  (grid F-3)
  [3] Raider Party   — 08m remaining  (grid B-7)

Entries that have expired since the last cache refresh may
disappear between listings. If an anomaly drops off the list
before you investigate it, it timed out.

RESOLUTION

Use `investigate <id>` at the anomaly's anchor location to
attempt resolution. Success grants:

  - Credits (scaled to region security and faction influence)
  - Crafting material stacks
  - Faction reputation with the relevant organisation

Partial failure (skill check missed by a small margin) still
grants a smaller reward. Combat-mode anomalies (raider parties)
are resolved on kill.

ANOMALY RULES

  - Anomalies last approximately 30 minutes from spawn.
  - A region typically has 1–3 active anomalies at any time.
  - You must be at or adjacent to the anchor location to
    investigate. The listing shows the grid reference.
  - Multiple players can investigate the same anomaly; rewards
    are distributed to each resolver.

EXAMPLES

  anomalies
  → [1] Salvage Cache — 24m remaining  (grid F-3)
    [3] Raider Party  — 08m remaining  (grid B-7)

  investigate 1
  → Move to grid F-3 first — see `investigate` help.

CHEAT SHEET
  anomalies      = list active anomalies in this region
  anom           = short alias
  investigate N  = resolve anomaly #N at its location
