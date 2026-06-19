---
key: chain
title: Chain — Tutorial Chain Interaction
category: "Commands: Character"
summary: Check your active tutorial chain progress or attempt a skill-check step. Most chain steps advance automatically when you talk to the right NPC, enter a room, win a fight, or complete a mission — only skill-check steps need `chain attempt`.
aliases: [chainstatus, chainattempt]
see_also: [newbie, skills, +sheet, mastery]
tags: [tutorial, chain, progression, command]
access_level: 0
examples:
  - cmd: "chain"
    description: "Show your active tutorial chain, current step, and what completes it."
  - cmd: "chain status"
    description: "Same as bare `chain`."
  - cmd: "chain attempt"
    description: "Roll the skill check for a skill_check_passed step (e.g. sneak past a patrol)."
---

Tutorial chains guide you through the opening gameplay loop. They
track your progress through a series of steps and reward you with
credits, items, or faction reputation on completion.

SYNTAX

  chain             Show active chain and current step
  chain status      Same as bare chain
  chain attempt     Attempt the current step's skill roll (only for
                    skill-check steps — see STEP TYPES below)

HOW CHAINS WORK

The server assigns your first chain automatically. Each chain is a
sequence of numbered steps; completing a step advances the counter.
Progress is visible on your character sheet under CHAINS.

Most steps advance **automatically** when a game event occurs:

  talk_to_npc        Talk to the specified NPC in the right room
  room_entered       Travel to the indicated location
  combat_won         Win a fight against the required target
  mission_accepted   Accept the indicated mission from the board
  mission_completed  Turn in the indicated mission
  bounty_accepted    Accept the indicated bounty contract
  item_acquired      Pick up or receive the required item
  item_used          Use the required item in the right context
  command_executed   Run the indicated command
  prerequisite       An automatic game-state trigger (no player action)

For these types, **there is nothing extra to type** — just do the
thing the step describes and the chain advances on its own.

SKILL-CHECK STEPS

When the current step type is `skill_check_passed`, the server needs
you to initiate the roll:

  chain attempt

The system picks the indicated skill, rolls it against the stated
difficulty, and resolves the step if you succeed. On failure you can
try again — there is no penalty and your dice do not deplete. Chain
status will show you the skill and difficulty so you can judge whether
to wait until your skill improves.

  chain status
  → Completes when: skill_check_passed
  → When ready, type chain attempt to roll Stealth vs difficulty 13.

CHEAT SHEET

  chain             = see current step
  chain attempt     = roll the skill check (only when step type is skill_check)
  (everything else happens automatically as you play)
