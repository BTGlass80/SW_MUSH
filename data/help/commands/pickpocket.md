---
key: pickpocket
title: Pickpocket — Steal Credits from a Sleeping Character
category: "Commands: Economy"
summary: Attempt to steal a portion of credits from a character who has disconnected in a non-secured room. Uses Pickpocket (Dexterity) vs. the target's Perception at −2D. Cannot be used in Secured zones. 10-minute cooldown per target.
aliases: [pp]
see_also: [+pvp, combat, skills, difficulty, housing]
tags: [economy, espionage, pvp, command]
access_level: 0
examples:
  - cmd: "pickpocket Greelo"
    description: "Attempt to steal credits from the sleeping character Greelo."
---

Steal a portion of credits from a character who has logged off
in a non-secured room. Requires them to still be in the same room
you are (their body persists while they are sleeping).

SYNTAX

  pickpocket <player name>

Partial name matches work. If multiple sleeping characters match,
the first match in the room is targeted.

REQUIREMENTS

  - Target must be SLEEPING (disconnected from the game). Online
    characters cannot be pickpocketed.
  - You and the target must be in the same room.
  - The room must NOT be in a SECURED zone. Secured areas have
    guards that make pickpocketing impossible.
  - 10-minute cooldown per target — you cannot repeatedly hit the
    same sleeping character back-to-back.

RESOLUTION — WEG D6 OPPOSED CHECK

  Your roll:       Pickpocket (Dexterity) — full pool
  Target's pool:   Perception at −2D (sleeping penalty)

  Success margin   Outcome
  ─────────────────────────────────────────────────────────────────
  Success          Steal 5–25% of the target's current credits.
                   Exact amount scales with the success margin.
  Failure          Nothing stolen. No alerting of the room.
  Fumble / crit    You drop something or make noise — everyone in
  fail             the room is informed that someone attempted a
                   theft. Your name is revealed to room occupants.

NOTES

  - Sleeping characters retain their credits and gear. This command
    only steals credits, not items from inventory.
  - The target's faction affiliation and your faction may affect
    NPC reactions in the room, but guards only intervene in secured
    zones (where the command is blocked entirely).
  - Credits stolen flow through `adjust_credits` (no hidden ledger).

CHEAT SHEET

  pickpocket <name>   = steal credits (Pickpocket vs Perception−2D)
