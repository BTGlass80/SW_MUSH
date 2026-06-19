---
key: "@narrative"
title: "@narrative — Narrative Memory Admin Commands"
category: "Commands: Admin"
summary: Admin verb for managing the PC narrative memory system — view, update, reset, or run the Director AI summarization pass. Requires admin access. Players interact with the narrative system via +recap and +quest.
aliases: ["@narr"]
see_also: [+quest, +recap, +background]
tags: [admin, narrative, director, command]
access_level: 3
examples:
  - cmd: "@narrative status"
    description: "System stats — AI enabled/disabled, PC count, log size, last batch run timestamp."
  - cmd: "@narrative view Han"
    description: "Dump Han's full narrative records: short_record (NPC-context inject), long_record (Director digest), action log summary."
  - cmd: "@narrative update Han"
    description: "Force an immediate summarization pass for Han. Invokes the Mistral/Haiku narrative pipeline for that PC only."
  - cmd: "@narrative reset Han"
    description: "Clear Han's narrative records. +background is preserved. Use when records are stale or the player has hard-pivoted their character concept."
  - cmd: "@narrative log Han"
    description: "View Han's raw pc_action_log entries — every action logged before the last summarization pass."
  - cmd: "@narrative enable"
    description: "Enable AI narrative features globally (short/long record updates, Director digest injection)."
  - cmd: "@narrative disable"
    description: "Disable AI narrative features globally. Logs still accumulate; records freeze until re-enabled."
  - cmd: "@narrative runnow"
    description: "Run the nightly summarization batch immediately. Processes all eligible PCs. Use to test the narrative pipeline or catch up after a downtime."
---

Admin verb for managing the PC narrative memory system. All
subcommands require admin access (AccessLevel.ADMIN).

The narrative system maintains two records per PC:
  short_record  (~150 words)  injected into NPC brain prompts
  long_record   (~800 words)  passed to the Director AI digest

Records are updated nightly by the summarization batch or on
demand via @narrative update.

SUBCOMMAND REFERENCE

  status                  AI status, PC count, log sizes, last run
  view <player>           Full narrative dump for that PC
  update <player>         Force immediate re-summarization (uses AI)
  reset <player>          Clear records — +background is preserved
  log <player>            Raw pc_action_log entries before last batch
  enable                  Enable AI features globally
  disable                 Freeze records (logs still accumulate)
  runnow                  Run the nightly batch immediately

WHEN TO USE EACH

  status          — check health before/after maintenance
  view            — QA a specific PC's narrative quality
  update          — player reports their record is stale or wrong
  reset           — hard character-concept pivot; record is misleading
  log             — debug why a player's record was generated oddly
  enable/disable  — toggle for cost control or system maintenance
  runnow          — spot-check the pipeline without waiting overnight

PLAYER-SIDE

  Players see their own records via:
    +recap              — short + long record summary
    +background         — set or view their own background text
    +quest              — list Director-generated personal quests

  Players CANNOT trigger re-summarization themselves — that's an
  admin action to prevent gaming the AI injection context.

CHEAT SHEET
  @narrative status           = system health
  @narrative view <name>      = see a PC's narrative records
  @narrative update <name>    = re-run summarization for that PC
  @narrative reset <name>     = clear records (keeps background)
  @narrative log <name>       = raw action log
  @narrative enable/disable   = toggle AI globally
  @narrative runnow           = run the nightly batch now
