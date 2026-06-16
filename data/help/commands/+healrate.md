---
key: +healrate
title: HealRate — Set Your Medical Service Rate
category: "Commands: Medical"
summary: View or set the credit cost you charge for healing treatments. Used by medics and field surgeons to advertise their service rate before performing a medical check.
aliases: [healrate, hrate]
see_also: ["+medical", "+check", medicine, healing, credits]
tags: [medical, credits, economy, command]
access_level: 0
examples:
  - cmd: "+healrate"
    description: "Show your current heal rate (credits per treatment)."
  - cmd: "healrate 500"
    description: "Set your healing service to cost 500 credits per treatment."
  - cmd: "healrate 0"
    description: "Set your healing to free (0 cr)."
---

Set the credit cost you charge for medical treatments. This is a
character-level setting that tracks what your medic character
charges per +medical check performed on another player.

USAGE

  +healrate           View your current rate
  +healrate <amount>  Set the rate (0 to 100,000)

The rate is stored on your character and persists between sessions.
Players who want your services see your rate before accepting.

PURPOSE

In a game with a real economy, skilled medics can earn credits for
their services. Set your rate to reflect:
  - Your character concept (charitable healer vs. professional
    surgeon vs. field medic on contract)
  - The risk and difficulty of the treatments you perform
  - Market conditions (what the current player base can afford)

Setting rate to 0 makes all your treatments free — appropriate for
Jedi healers who treat as an act of compassion, or new medics still
building a reputation.

VALID RANGE

  Minimum: 0 credits (free)
  Maximum: 100,000 credits per treatment

The game caps at 100,000 with the message "That's... ambitious. Max
100,000." This is a safety valve, not a recommendation.

MARKET CONTEXT

A reasonable medic rate for a character with Medicine 3D–4D:
  - 100–300 cr for basic wound treatment
  - 500–1,500 cr for serious injuries
  - 2,000+ cr for critical care / exotic treatments

Top specialists with Medicine 5D+ can justify premium rates; the
market will self-regulate as players shop for healers.

NOTE ON MECHANICS

+healrate sets your ADVERTISED rate. The actual credit transfer
when you heal someone happens through the normal credit system
(see `+medical` for how treatments are performed). The rate here
is the value shown to patients before they consent to treatment.

EXAMPLES

  +healrate
  → "Your heal rate: 300 credits per treatment."

  healrate 500
  → "Heal rate set to 500 credits."

  healrate 0
  → "Heal rate set to 0 credits. (Free treatments.)"

  +healrate 200000
  → "That's... ambitious. Max 100,000."

CHEAT SHEET
  +healrate           = view current rate
  healrate <amount>   = set rate (0 – 100,000)
  +medical            = perform a healing treatment
