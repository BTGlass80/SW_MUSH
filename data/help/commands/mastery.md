---
key: mastery
title: Mastery — Questlines and the Galaxy-Wide Directory
category: "Commands: Character"
summary: Opt-in mid-game questlines — freelance side-jobs open to anyone, and master-trainer trials that help unlock Tier-5 schematics. Use `mastery browse` to see every questline in the galaxy.
aliases: [masteries, mastertrials]
see_also: [chain, +craft, +cpstatus, +teach, skills, advancement]
tags: [progression, questline, crafting, tier5, command]
access_level: 0
examples:
  - cmd: "mastery browse"
    description: "Galaxy-wide directory: every questline, who gives it, and where it starts."
  - cmd: "mastery"
    description: "Show your active questline (or any offer from an NPC in this room)."
  - cmd: "mastery start nar_freight_ghost_shipment"
    description: "Begin an offered questline by its id (get the id from `mastery browse`)."
  - cmd: "mastery status"
    description: "Detailed step breakdown of your active questline."
  - cmd: "mastery abandon"
    description: "Abandon your active questline. You can restart it later."
---

Questlines are opt-in, mid-game story arcs you start deliberately —
multi-step jobs with their own characters, locations, and rewards. They
are separate from your chargen-assigned tutorial chain (`chain`) and from
Director-issued personal quests.

There are TWO kinds, and both use the same `mastery` command:

  • FREELANCE SIDE-JOBS — open to any character once you have finished
    character creation. A broker in a cantina, market, or back-alley
    offers them; the rewards are credits, reputation, and a bit of CP.
    These are the bulk of the galaxy's side-content.

  • MASTER-TRAINER TRIALS — offered by a master trainer in a dangerous
    or contested zone. Completing one helps unlock that trainer's
    advanced Tier-5 crafting schematics.

SYNTAX

  mastery               Show your active questline, or offers in this room
  mastery browse        Galaxy-wide directory of every questline
  mastery status        Detailed step breakdown of your active questline
  mastery start <id>    Begin an offered questline (id from `mastery browse`)
  mastery abandon       Abandon the active questline (you can restart later)

  `mastery browse` also answers to `all`, `directory`, and `catalog`.

FINDING ONE — `mastery browse`

  You no longer have to stumble onto a giver to learn a questline exists.
  `mastery browse` lists the whole catalogue partitioned by where you
  stand with each one:

      • AVAILABLE NOW  — what you can start, with the giver, the start
                         zone, and the exact `mastery start <id>` to type.
      • LOCKED         — what you cannot start yet, and why (a reputation
                         or faction requirement you have not met).
      • COMPLETED      — what you have already finished.

  Browsing shows existence only — `mastery start` still enforces every
  gate, and starting a questline teleports you to its opening scene from
  wherever you are. You can also still walk up to a giver and `talk` to
  them; the in-room offer and the directory always agree.

STARTING — `mastery start <id>`

  Pick an id from `mastery browse` (or from an in-room offer) and begin.
  You can have ONE active questline at a time; starting a new one
  requires abandoning the current.

QUESTLINE STEPS

  Steps work like tutorial chain steps: most advance automatically as you
  play (talk to the right person, travel, win a fight, complete a job).
  Steps that require a skill roll use `chain attempt` — `mastery status`
  tells you which step you are on and what it is waiting for.

      mastery status
      → Step 2 / 5: Trace the skimmed shipment
        Completes when: skill_check_passed (security)
        → Type `chain attempt` here to make the roll.

COMPLETION REWARD

  Finishing the final step pays out the questline's reward. Freelance
  arcs grant credits, reputation, and a CP-bearing achievement;
  master-trainer trials additionally unlock the trainer's Tier-5
  schematic set in your `+craft` panel. Some arcs add unique items.

ABANDONING

  `mastery abandon` drops the active questline so you can pick up a
  different one; you can `mastery start <id>` it again later. Your step
  progress resets to the beginning.

CHEAT SHEET

  mastery browse         = galaxy-wide directory (also: all / directory / catalog)
  mastery                = active questline / room offers
  mastery start <id>     = begin a questline
  mastery status         = step-by-step progress
  mastery abandon        = give up (restart later)
  chain attempt          = roll a skill check (when a step requires it)
