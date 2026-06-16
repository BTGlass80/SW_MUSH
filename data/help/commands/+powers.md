---
key: +powers
title: +Powers — Force Powers List
category: "Commands: Force"
summary: List the Force powers available to your character based on your Control, Sense, and Alter skill levels.
aliases: [powers, forcepowers, listpowers]
see_also: [+forcestatus, +meditate, +sheet, +check]
tags: [powers, force, jedi, control, sense, alter, command]
access_level: 0
examples:
  - cmd: "+powers"
    description: "List Force powers your character can currently use."
---

List the Force powers your character has unlocked, based on your
Control, Sense, and Alter skill ratings. Also shows powers that
are locked and what skills you need to unlock them.

SYNTAX

  +powers

WHAT IS SHOWN

  - Available powers: powers you can activate now.
  - Locked powers: powers you'll unlock with further training,
    shown with the required skills listed.

  Force powers are activated with: force <power> [target]

  You must be Force-sensitive to use this command. Characters
  without Force skills (Control, Sense, Alter) will see a
  message indicating they have no Force access.

HOW TO UNLOCK POWERS

  Force powers unlock automatically as your Control, Sense,
  and Alter dice ratings increase. Train these skills through
  +teach/<learn> with a Jedi master or through Force XP awards.

EXAMPLES

  +powers
  → Lists available and locked powers with skill requirements.

  force move_object <target>
  → Activates the "Move Object" power (if unlocked).

SEE ALSO

  +forcestatus   Your Force attributes, Force Points, and Dark Side status.
  +meditate      Reduce the Weight of War (Jedi, Temple only, daily).
  +sheet         Your full character sheet.

CHEAT SHEET
  +powers               list your available Force powers
  force <power>         use a Force power
  force <power> <name>  use a targeted Force power
