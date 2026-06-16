---
key: +kudos
title: Kudos — Peer RP Recognition
category: "Commands: Social"
summary: Award kudos to another player for excellent roleplay. Grants them 35 character-point ticks. You can give 3 kudos per week; each recipient can receive 3 per week.
aliases: [kudos, givekudos, "+givekudos"]
see_also: [+cpstatus, +scenebonus, +scene, advancement, reputation]
tags: [social, roleplay, advancement, kudos, command]
access_level: 0
examples:
  - cmd: "+kudos Tundra Great scene at the cantina!"
    description: "Award kudos to Tundra with an optional reason note."
  - cmd: "kudos Asha Loved your Jedi Council scene."
    description: "Same as +kudos (bare alias preserved)."
---

Recognize exceptional roleplay from another player. A kudos award
grants them 35 ticks toward their next Character Point — the
equivalent of a strong solo scene's worth of engagement.

USAGE

  +kudos <player name>
  +kudos <player name> <reason>

The reason is optional but encouraged — it lets the recipient know
what you valued about their performance and appears in their
notification message.

Target matching is prefix-based. Typing `+kudos Ash` finds Asha if
she's the only online player whose name starts with "Ash".

LIMITS — PREVENTING FARMING

  - You can give 3 kudos per week (7-day rolling window)
  - Any specific recipient can receive a kudos from you once per
    7 days (per-giver lockout)
  - Recipients can receive up to 3 kudos per week total

These limits stop kudos-farming between alts or a small group of
friends abusing the system. The peer-recognition pool is shared and
finite by design.

WHAT HAPPENS

  1. Recipient gets +35 ticks toward their next CP
  2. Both giver and recipient see a confirmation message
  3. The giver's weekly remaining kudos count decrements
  4. An achievement unlock check fires for the recipient (first kudos
     received, 5th kudos received, etc.)

You must be online and playing a character to give kudos. The target
must also be online (any room — no same-room requirement since the
game has low population sizes at launch).

CHECKING YOUR STATUS

  +cpstatus shows:
    - How many kudos you've received this week
    - How many slots are still open (max 3)

Recipients see the giver's name and your optional reason note when
you award them.

EXAMPLES

  +kudos Brix
  → "You gave kudos to Brix. +35 ticks awarded."
  → (Brix sees) "Asha recognized your RP with kudos! +35 ticks."

  +kudos Tundra Amazing work in the Council scene tonight.
  → Same but with the reason note in Tundra's notification.

  +kudos Jorak  (second time this week)
  → "You have already given kudos to Jorak this week."

  (if you've given all 3 this week)
  → "You've given all your kudos for the week. Resets in 4 days."

CHEAT SHEET
  +kudos <name>           = give kudos (35 ticks to them)
  +kudos <name> <reason>  = give kudos with a note
  +cpstatus               = see your kudos remaining / received
