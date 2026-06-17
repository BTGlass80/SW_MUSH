---
key: +learn
title: +Learn — Request Force Power Training
category: "Commands: Padawan-Master"
summary: Padawan requests instruction in a Force power from their bonded Master. The Master must be present and respond with +teach within the time window.
aliases: []
see_also: [+teach, +spar, +powers, +forcestatus, +master]
tags: [padawan, force, training, jedi, command]
access_level: 1
examples:
  - cmd: "+learn accelerate healing from Obi-Wan"
    description: "Request instruction in Accelerate Healing from your Master."
---

Request instruction in a specific Force power from your bonded Master.
The request is staged for a short window; the Master responds with
'+teach' to complete the transfer.

SYNTAX

  +learn <power name> from <master name>

REQUIREMENTS

  - You must have an active Padawan bond.
  - The named character must be your Master (not just any Jedi).
  - The power name must be a recognized Force power (see +powers).

WHAT HAPPENS

  1. You stage the learn request.
  2. Your Master is notified in real time (or sees it on login).
  3. Your Master types '+teach <power>' while in the same room.
  4. If your relevant Force skill is below 1D, Character Points are
     spent from YOUR pool to bring it to the minimum.
  5. The training is logged on the bond record.

POWER NAMES

  Use '+powers' to list all available Force powers and their names.
  Common powers: accelerate healing, life detection, sense Force,
  telekinesis, lightsaber combat, affect mind, etc.

EXAMPLES

  +learn accelerate healing from Obi-Wan
  → "You request instruction in Accelerate Healing from Obi-Wan."
  → Obi-Wan sees: "<Padawan> requests instruction. Use +teach."

  (Obi-Wan is offline)
  → Request is staged until they next log in (request window applies).

SEE ALSO

  +teach       Master's side of the training exchange.
  +spar        Earn CP through a training duel.
  +powers      List all Force powers and prerequisites.
  +forcestatus Check your current Force Points.

CHEAT SHEET
  +learn <power> from <master>   request Force power training
