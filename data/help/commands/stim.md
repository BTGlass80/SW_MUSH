---
key: stim
title: Stim / Stimaccept — Administer Medical Consumables
category: "Commands: Medical"
summary: Administer a stimpack, medpac, or specialty stim to yourself or another player. The target must type stimaccept to receive the treatment.
aliases: [stimaccept, saccept]
see_also: [+medical, heal, healaccept, respawn, +healrate]
tags: [medical, consumables, combat, command]
access_level: 0
examples:
  - cmd: "stim Han"
    description: "Administer a basic stimpack to Han (Easy First Aid check)."
  - cmd: "stim me with medpac"
    description: "Self-administer a medpac to heal one wound level (-1D penalty)."
  - cmd: "stim Leia with medpac_advanced"
    description: "Advanced medpac — heals two wound levels."
  - cmd: "stim/force Rey"
    description: "Force a second stim through when Rey already has one active (overdose risk)."
  - cmd: "stimaccept"
    description: "Accept the pending stim offer from a medic in this room."
---

Administer medical consumables to yourself or another player.

STIM COMMAND

  stim <player>                          — basic stimpack (default)
  stim <player> with <consumable>        — specify consumable type
  stim me with <consumable>              — self-administer (-1D penalty)
  stim/force <player>                    — override active stim (overdose risk)

CONSUMABLE TYPES

  stimpack           Easy First Aid (1D). Clears Stunned.
  adrenaline_shot    Initiative + Dexterity boost (combat stim).
  combat_stim        Strength boost for 3 rounds.
  focus_stim         Perception bonus for skill checks.
  medpac             Heals 1 wound level (Moderate First Aid).
  medpac_advanced    Heals 2 wound levels (Difficult First Aid).
  medpac_fastflesh   Easiest medpac (Easy First Aid, heals 1 level).

  You must have the consumable in your kit (crafted or purchased).
  You need at least 1 pip in the relevant skill (First Aid for
  healing stims, Medicine for advanced medpacs).

SELF-ADMINISTRATION

  Medpacs and stimpacks can be self-administered with a -1D penalty.
  Specialty stims (combat_stim, focus_stim, adrenaline_shot) require
  another person to administer.

STIMACCEPT

  stimaccept     — accept a pending stim offer
  saccept        — alias

  When a medic types `stim <you>`, you receive a prompt. Type
  `stimaccept` within 60 seconds while the medic is still in the
  room to receive the treatment.

OVERDOSE (stim/force)

  If you already have an active stim running, the medic can use
  `stim/force` to push a second one through — at +5 difficulty and
  a risk of incapacitation on failure.

CHEAT SHEET

  stim <player>              — administer default stimpack
  stim <player> with medpac  — administer medpac (heals 1 wound)
  stimaccept                 — receive a stim from a medic
  heal <player>              — NPC/med-droid healing (no consumable needed)
