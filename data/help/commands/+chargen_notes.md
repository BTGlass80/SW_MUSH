---
key: +chargen_notes
title: ChargenNotes — Character Creation Rationale
category: "Commands: Character"
summary: Set or view your personal chargen rationale — the player-facing notes explaining why you built your character the way you did. Visible only to you, never to other players.
aliases: [chargen_notes, "+cgn", "cgn", "+chargennotes", "chargennotes"]
see_also: [+sheet, +background, +char, chargen]
tags: [character, chargen, notes, command]
access_level: 0
examples:
  - cmd: "+chargen_notes"
    description: "Show your current chargen notes."
  - cmd: "+chargen_notes Jedi Sentinel build: high Sense, medium Control, focus on Perception and Stealth."
    description: "Set your chargen notes to the given text."
  - cmd: "+chargen_notes /clear"
    description: "Clear your chargen notes entirely."
  - cmd: "cgn"
    description: "Short alias — show your chargen notes."
---

Store a private note about your character build — which skills you
prioritized, what trade-offs you accepted, what build direction
you're aiming at, and what plot hooks you're hoping for.

These notes are ONLY visible to you. Other players cannot see them.
Staff/admins cannot see them either through normal channels (they're
stored privately in your character record).

PURPOSE

Chargen notes exist because:
  - Character builds in R&E D6 involve dozens of choices and the
    reasoning is easy to forget between sessions
  - You may want to note "I took Streetwise 4D instead of Search
    so I could fill the underworld-contact role in the party"
  - Tracking intended build progression: "plan to raise Blasters
    to 5D next, then invest in Move Object if I get Force"
  - Plot hooks you want staff to pick up: "hoping to get recruited
    into the BH Guild eventually, set that up in background"

DISTINCT FROM +BACKGROUND

  +background    — in-character biography and history (other players
                   can see this with +finger <name>)
  +chargen_notes — out-of-character build rationale (private, only
                   visible to you in your sheet panel)

Both have a 2,000-character limit.

USAGE

  +chargen_notes               View current notes
  +chargen_notes <text>        Set notes (overwrites previous)
  +chargen_notes /clear        Clear notes entirely

The notes appear in the right-rail panel of the character sheet
in the web interface (`+sheet` / the Sheet tab). They don't appear
on the public character card.

EXAMPLES

  +chargen_notes
  → (if set) "Sentinel build. High Sense + Perception; moderate
     Control. Want to develop Move Object once I hit Knight.
     Background hook: looking for clues on my master's disappearance."

  +chargen_notes Smuggler archetype. Maxed Piloting and Con. Plan to
  invest in Smuggling skill track for the guild questline.
  → "Chargen notes updated."

  +chargen_notes /clear
  → "Chargen notes cleared."

CHEAT SHEET
  +chargen_notes           = view notes
  +chargen_notes <text>    = set/overwrite
  +chargen_notes /clear    = erase
  +background              = the public IC biography (different)
