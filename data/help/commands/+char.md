---
key: +char
title: Char — Account & Alternate Characters
category: "Commands: Character"
summary: Manage your account's alternate characters — list alts, switch to a different character, or delete a character you no longer want.
aliases: ["+character", "charswitch", "char"]
see_also: [+sheet, +background, +chargen_notes, login, chargen]
tags: [character, account, alts, command]
access_level: 0
examples:
  - cmd: "+char/list"
    description: "List all characters on your account (name, faction, active status)."
  - cmd: "+char/switch"
    description: "Return to the character selection screen without logging out."
  - cmd: "+char/delete Jorak"
    description: "Delete character 'Jorak'. Requires confirmation (type the name exactly)."
---

Manage alternate characters on your account. An account can hold
up to 3 characters across different factions. Two alts may not
share the same faction — faction loyalty is per-character and
presumed sincere.

SWITCH REFERENCE
  /list     List all characters on your account
  /switch   Return to character selection (stay logged in)
  /delete   Delete a character (permanent — requires confirmation)

ACCOUNT MODEL

One account, up to 3 characters. Each character is independent:
separate credits, gear, reputation, skills, faction standing, and
plot threads. They do NOT interact with each other — no inter-alt
trading, no shared purses, no using one to buff another. This is
both a game-balance rule and an engine constraint (cross-alt
transactions are blocked at the engine level).

/list

Shows every character attached to your account:
  - Name + faction
  - Active status (which one you're currently playing)
  - Brief creation date

Use this to remind yourself of your alts before switching.

/switch

Takes you back to the character selection screen. You remain
connected — no re-login required. Select a different character
from the list to begin playing them immediately.

This is the fastest way to swap alts mid-session.

/delete <name>

Permanently deletes a character. The game prompts you to type the
character's name exactly to confirm — this is a safeguard against
fat-finger deletion. Deletion is irreversible: all credits, gear,
reputation, and progress for that character are wiped. Faction
standing, RP history, and narrative records tied to that character
vanish.

Only delete characters you are done with. There is no recovery.

FACTION CONSTRAINT

Two characters on the same account may not share a faction. If you
play a Jedi and a Republic soldier, your third slot is not
available for another Republic character. The restriction exists to
prevent using alts as faction spies — a Separatist alt can't relay
your Jedi character's intel to the other side.

EXAMPLES

  +char/list
  → "Asha (Jedi Order) — active. Brix (Outer Rim Scoundrel) — idle."

  +char/switch
  → Returns to character selection screen.

  +char/delete Brix
  → "Type 'Brix' to confirm permanent deletion."
  → (you type 'Brix')
  → "Brix deleted. Your account now has 1 character."

CHEAT SHEET
  +char/list     = see all alts
  +char/switch   = swap characters (stay connected)
  +char/delete   = permanently delete an alt
