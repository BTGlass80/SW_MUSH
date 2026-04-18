---
key: +quest
title: Quest — Personal Story Quests from the Director AI
category: "Commands: Narrative"
summary: All personal-quest verbs live under +quest/<switch>. List your quests, accept, complete, or abandon — every verb is a switch here. Personal quests are Director-AI-generated story hooks, distinct from the paid mission board.
aliases: [quest, quests, +pq, personalquests, +quests, questaccept, acceptquest, pqaccept, questcomplete, finishquest, pqcomplete, completequest, questabandon, abandonquest, pqdrop]
see_also: [+mission, +background, +recap, narrative, director]
tags: [narrative, quests, story, command]
access_level: 0
examples:
  - cmd: "+quest"
    description: "List your active personal quests."
  - cmd: "+quest/list"
    description: "Same as bare +quest — list active quests."
  - cmd: "+quest/list completed"
    description: "Show quests you've already completed."
  - cmd: "quests"
    description: "Same as +quest/list (bare alias preserved)."
  - cmd: "+pq"
    description: "Short alias for +quests."
  - cmd: "+quest/accept 12"
    description: "Acknowledge accepting quest 12 (personal quests are active on creation; this is ceremonial)."
  - cmd: "questaccept 12"
    description: "Same as +quest/accept 12 (bare alias preserved)."
  - cmd: "acceptquest 12"
    description: "Another bare alias for /accept."
  - cmd: "+quest/complete 12"
    description: "Mark quest 12 complete. The Director will verify your progress."
  - cmd: "questcomplete 12"
    description: "Same as +quest/complete 12 (bare alias preserved)."
  - cmd: "finishquest 12"
    description: "Another bare alias for /complete."
  - cmd: "completequest 12"
    description: "Another bare alias for /complete."
  - cmd: "+quest/abandon 12"
    description: "Drop quest 12. Some stories are left unfinished."
  - cmd: "questabandon 12"
    description: "Same as +quest/abandon 12 (bare alias preserved)."
  - cmd: "pqdrop 12"
    description: "Short alias for abandon."
---

All personal-quest verbs are switches under +quest. Bare forms
(quests, questaccept, questcomplete, questabandon) still work as
aliases — typing `questcomplete 12` and `+quest/complete 12` reach
the same code. The canonical form is +quest/<switch>; the rest of
this page uses it everywhere.

Personal quests are DIFFERENT from the mission board.
  - +mission = paid jobs posted to the board (credits, skill checks,
               lifecycle driven by generation + completion)
  - +quest   = Director-AI-generated story hooks tailored to your PC's
               narrative memory — no credits, no skill rolls, no
               difficulty ladder. These are narrative threads.

See `+help +mission` for the paid-job board. This page covers only
personal quests.

SWITCH REFERENCE
  /list      Show your active personal quests (also: bare '+quest')
  /list completed   Show completed quests
  /accept    Acknowledge quest acceptance (by id)
  /complete  Mark a quest as complete (Director verifies)
  /abandon   Drop a quest you no longer care to pursue

WHAT ARE PERSONAL QUESTS?

The Director AI watches your PC's actions and builds a narrative
memory. Based on that record — your background (+background),
your recent actions, your relationships — it periodically generates
a personal quest: a short-form story hook that makes sense for your
character specifically.

A smuggler with a debt to Jabba may see quests about repaying it.
A former Imperial might see quests about confronting their past.
A Jedi sympathizer might see quests about finding a lost holocron.

Quests DO NOT pay credits. They are markers of story progress —
the Director notes completion and adjusts future quest generation
and NPC dialogue accordingly.

THE QUEST LIFECYCLE

  (Director generates) → ACTIVE → COMPLETE
                                ↘ ABANDONED

Quests are created in ACTIVE status. /accept is mostly ceremonial —
it acknowledges you've seen the quest, but the quest doesn't need
acceptance to count as pursuable. You CAN complete an active quest
without first accepting it.

/complete and /abandon are terminal states. Abandoned quests DO get
logged to the narrative record — the Director notes that you left
that story thread hanging.

/list

Shows active quests by default:
  ▸ [12] The Debt to Jabba
      Jabba's loan shark is asking questions. Find a way to
      settle the debt before things get serious.

  ▸ [15] An Old Friend Returns
      A face from your Academy days surfaces in Mos Eisley...

/list completed shows the archive. Completed quests become part
of the PC's story record and feed future quest generation.

/accept <id>

Ceremonial. Prints the quest title + description as confirmation.
The quest was already ACTIVE when created, so this is purely a
"yes, I noticed this" signal. Some players use it; others skip
straight to /complete.

/complete <id>

Mark the quest done. The Director takes note:
  "Quest complete: The Debt to Jabba. The Director takes note
   of your accomplishment."

A successful /complete also fires an on-demand narrative
summarization, incorporating the completion into your PC's
long-record for future Director context. Future quests will
reference this outcome where relevant.

The Director DOES verify some quests against in-game state
(e.g., "killed X", "visited Y") but does NOT block /complete —
you can self-attest. Abuse pattern: mass-completing quests for
no narrative reason will eventually degrade the Director's
quest quality as the model sees you aren't actually playing them.

/abandon <id>

Drop the quest. Status → ABANDONED. Logged to narrative:
  "Quest abandoned: An Old Friend Returns.
   Some stories are left unfinished."

The Director notes abandonment but does not penalize — this is
RP, not grind. Some stories are deliberately hung; that is itself
a story.

GENERATION TIMING

The Director runs a batch summarization pass nightly (or via
@narrative runnow for admins). During the pass, each PC whose
action log has meaningful new entries gets:
  1. A short-record update (~200 chars — recent highlights)
  2. A long-record update (~400 chars — deep history)
  3. Possibly a new personal quest, if the narrative arc
     suggests one

You don't need to request quests — they appear as your story
develops. The best way to unlock more is to:
  - Write a rich +background
  - Be active (combat, missions, RP poses — anything logged)
  - Complete existing quests (closes arcs, opens new ones)

RELATED COMMANDS
  +background        — Set or view your character background
  +background <text> — Write your background (2000 chars)
  +recap             — See your narrative recap (short + long record)
  +quests            — Same as +quest/list (legacy alias)

ADMIN COMMANDS (GM-only)
  @narrative status           — System stats
  @narrative view <player>    — View a PC's narrative records
  @narrative update <player>  — Force immediate summarization
  @narrative reset <player>   — Clear records (keeps +background)
  @narrative log <player>     — View raw action log entries
  @narrative enable/disable   — Toggle AI narrative features
  @narrative runnow           — Run nightly batch immediately

See '+help @narrative' for details.

CHEAT SHEET
  +quest            = list active (also: /list, quests, +pq)
  +quest/list completed = show completed
  +quest/accept N   = acknowledge (also: questaccept, acceptquest)
  +quest/complete N = mark done (also: questcomplete, finishquest)
  +quest/abandon N  = drop (also: questabandon, pqdrop)
