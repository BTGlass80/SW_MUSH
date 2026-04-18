---
key: +mission
title: Mission — The Mission Board
category: "Commands: Economy"
summary: All mission-board verbs live under +mission/<switch>. Browse the board, accept a job, view your active mission, complete it at the destination, or abandon it — every verb is a switch here.
aliases: [mission, missions, mb, jobs, +jobs, +mb, +missions, myjob, activemission, +myjob, accept, takejob, complete, finishjob, turnin, abandon, dropmission, quitjob]
see_also: [missions, bounty, +bounty, +smuggle, economy, factions, difficulty]
tags: [economy, missions, core, command]
access_level: 0
examples:
  - cmd: "+mission"
    description: "Show your active mission (destination, objective, reward)."
  - cmd: "+mission/board"
    description: "Browse available missions on the board. Shows 5–8 procedurally generated jobs."
  - cmd: "missions"
    description: "Same as +mission/board (bare alias preserved)."
  - cmd: "+mission/accept m-4f3a"
    description: "Accept mission m-4f3a (prefix match works — 'm-4f' is enough if unique)."
  - cmd: "accept m-4f3a"
    description: "Same as +mission/accept m-4f3a (bare alias preserved)."
  - cmd: "+mission/view"
    description: "Show your active mission in detail. Same as bare +mission."
  - cmd: "+mission/complete"
    description: "Turn in the mission at the destination. Rolls the relevant skill; pay scales with result."
  - cmd: "complete"
    description: "Same as +mission/complete (bare alias preserved)."
  - cmd: "turnin"
    description: "Another bare alias for /complete."
  - cmd: "+mission/abandon"
    description: "Return your active mission to the board. No penalty."
  - cmd: "abandon"
    description: "Same as +mission/abandon (bare alias preserved)."
  - cmd: "dropmission"
    description: "Another bare alias for /abandon."
  - cmd: "+mission/board"
    description: "Shows the board. Accept a job by its 4-character prefix id."
  - cmd: "+missions"
    description: "Board alias (muscle memory preserved)."
  - cmd: "jobs"
    description: "Board alias."
  - cmd: "myjob"
    description: "View your active mission (alias for +mission)."
---

All mission-board verbs are switches under +mission. Bare forms
(missions, accept, complete, abandon) still work as aliases — typing
`accept m-4f3a` and `+mission/accept m-4f3a` reach the same code.
The canonical form is +mission/<switch>; the rest of this page uses
it everywhere.

See `+help missions` for the conceptual overview of mission types,
pay ranges, and lifecycle. This page is the command reference.

SWITCH REFERENCE
  /board     Browse available missions (5–8 jobs, refreshes every 30 min)
  /accept    Accept a mission by its id (prefix match works)
  /view      Show your active mission (also: bare '+mission')
  /complete  Turn in at the destination — skill check determines pay
  /abandon   Drop your active mission, return it to the board (no penalty)

ONE ACTIVE MISSION AT A TIME. You cannot hold two. Complete or
abandon the current one before accepting another.

THE MISSION LIFECYCLE

  AVAILABLE → ACCEPTED → COMPLETE
                      ↘ EXPIRED (2 hours after accept)
                      ↘ ABANDONED → AVAILABLE

Unclaimed missions expire off the board after 1 hour.
Accepted missions expire after 2 hours (2,700s board refresh cycle).
Abandoning a mission returns it to the board with no cost.

MISSION TYPES — GROUND (10 kinds)

  Type            Skill         Pay Range         Partial Pay
  Delivery        Stamina       100–300 cr        100% (always full)
  Combat          Blaster       300–1,000 cr      50%
  Investigation   Search        200–800 cr        75%
  Social          Persuasion    500–2,000 cr      75%
  Technical       Space Trans.  300–1,500 cr      50%
                  Repair
  Medical         First Aid     200–1,000 cr      75%
  Smuggling       Con           500–5,000 cr      50%
  Bounty          Streetwise    300–3,000 cr      50%
  Slicing         Comp. Prog.   400–2,000 cr      50%
                  or Repair
  Salvage         Search        200–1,000 cr      75%

MISSION TYPES — SPACE (4 kinds)

  Type          Pay Range         Requirement
  Patrol        300–1,500 cr      Hold a zone for 120 ticks (seconds)
  Escort        500–2,000 cr      Protect an NPC trader to destination
  Intercept     500–2,500 cr      Destroy N hostile ships in a zone
  Survey Zone   300–1,200 cr      Resolve ≥1 anomaly in the zone

Space missions require a launched ship in the target zone to complete.
Escort missions spawn an NPC trader on accept; if the freighter is
destroyed before delivery, pay drops to 25% (partial — "freighter lost").

COMPLETION SKILL CHECK

Ground missions roll the type's skill against a difficulty scaled to
the reward. Space missions pay their full reward when the objective
condition is met (no per-mission skill check — the gameplay IS the check).

  Ground roll pipeline:
    - perform_skill_check(char, skill, difficulty) is called
    - Success: full reward (100%)
    - Partial success (miss by ≤4): partial pay (50–100% per type)
    - Critical success (Wild Die explodes): +20% bonus, [EXCEPTIONAL]
    - Failure (miss by >4): 0 credits, [FAILED]

  Difficulty scales with reward. Low-pay jobs are forgiving; high-pay
  jobs demand pros. The mission_difficulty() table ranges 8–21 —
  intermediate values below the canonical R&E Heroic ladder (R&E p.75)
  so players can clear low-tier jobs reliably.

FACTION REPUTATION

Completing a mission grants +3 reputation to your primary faction
(if any) via the 'complete_faction_mission' action. Some missions
are faction-flagged (e.g. Alliance courier runs) — these grant rep
to the flagged faction instead. See '+help reputation'.

POST-COMPLETION HOOKS

A successful /complete also fires:
  - +3 faction reputation (above)
  - Narrative log entry (your PC's Director record updates)
  - Ships-log tick (for profession chain progression)
  - Territory influence in the current zone
  - Spacer quest check (if on a quest-chain tier)
  - Achievement: first_mission, missions_completed, credits_earned

THE BOARD

/board shows 5–8 available missions. Each line has:
  - ID (4-character prefix, e.g. 'm-4f3a')
  - Type (delivery, combat, etc.)
  - Short title
  - Destination (room name)
  - Reward (credits)
  - Faction tag (if sponsored)

Board refreshes every 30 minutes. Completed missions are replaced
immediately. BOARD_MIN=5 ensures at least 5 jobs are always posted.

/accept <id>

Prefix matching: if you type `+mission/accept m-4f` and there's
exactly one mission starting with m-4f, it accepts that one. If there
are two matches, the first in iteration order wins — use the full id
to disambiguate.

You'll see a one-shot announcement with the objective, destination,
and reward. Type '+mission' to review at any time.

/view

Shows the active mission in detail:
  - Full title + objective text
  - Destination (room name + coordinates if known)
  - Reward amount
  - Expires-at timestamp
  - Faction tag (if sponsored)
  - Mission-specific data (target zone, escort ID, etc. for space)

/complete

Context-sensitive. The game checks:
  1. Do you have an active mission? If not: "No active mission."
  2. Is it a space mission?
     → Check ship + zone + objective state (patrol ticks, kills,
       escort alive, anomaly resolved). If not satisfied, tells
       you what's missing.
     → If satisfied, award full reward (or 25% for escort-with-loss).
  3. Otherwise (ground):
     → Are you in the destination room? If not: tells you where.
     → If yes, rolls the skill check and pays accordingly.

/abandon

No-penalty drop. Mission returns to the board AVAILABLE for anyone
to claim. Your slot opens up for a new accept.

EXAMPLES

  +mission/board
  → Shows all 5–8 available missions.

  +mission/accept m-4f
  → Accepts mission m-4f3a (prefix match).

  +mission
  → "Delivery to Mos Eisley Spaceport — Courier package for 250 cr"

  move mos_eisley_spaceport
  +mission/complete
  → "Mission complete: Courier run  Reward: +250 cr (Balance: 3,400 cr)
      Skill: Stamina [2D+1]  Roll: 14 vs Difficulty: 8"

  +mission/abandon
  → "Mission abandoned: Courier run. The job has been returned to the board."

CHEAT SHEET
  +mission/board     = browse
  +mission/accept    = take a job (prefix id matching)
  +mission           = view active (also: /view, mission, myjob)
  +mission/complete  = turn in (also: complete, turnin, finishjob)
  +mission/abandon   = drop (also: abandon, dropmission, quitjob)
