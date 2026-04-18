---
key: +medical
title: Medical — Healing & Medical Treatment
category: "Commands: Combat"
summary: All medical verbs under +medical/<switch>. Heal a wounded target (initiates a consent flow), accept an incoming heal offer, or configure your heal rate. Uses R&E First Aid / Medicine skills.
aliases: [heal, healaccept, haccept, healrate, hrate]
see_also: [firstaid, medicine, wounds, combat]
tags: [combat, healing, medical, command]
access_level: 0
examples:
  - cmd: "+medical"
    description: "Defaults to /heal — prompts for a target."
  - cmd: "+medical/heal Jex"
    description: "Offer to heal Jex. Sends a consent prompt; Jex must /accept."
  - cmd: "heal Jex"
    description: "Same as +medical/heal (bare alias preserved)."
  - cmd: "+medical/accept"
    description: "Accept an incoming heal offer. Medicine/First Aid roll resolves."
  - cmd: "healaccept"
    description: "Same as +medical/accept (bare alias preserved)."
  - cmd: "haccept"
    description: "Short form for /accept."
  - cmd: "+medical/rate 5"
    description: "Set your max heals-per-hour rate (NPC medics). Admin-configurable floor."
  - cmd: "healrate 5"
    description: "Same as +medical/rate (bare alias preserved)."
  - cmd: "hrate"
    description: "Short form — view current rate."
  - cmd: "+medical/rate"
    description: "View your current heal-rate config (no args)."
  - cmd: "+medical/heal self"
    description: "Attempt to heal yourself (harder difficulty — First Aid on yourself is +5)."
  - cmd: "heal"
    description: "Bare heal with no args — lists wounded targets in the room."
---

All medical verbs live under +medical/<switch>. Bare forms (heal,
healaccept, healrate) still work as aliases.

See `+help firstaid` and `+help medicine` for the underlying skill
mechanics. This page is the command reference.

SWITCH REFERENCE
  /heal <target>   Offer to heal a target (consent prompt)
  /accept          Accept an incoming heal offer
  /rate [n]        View or set your heal-rate limit

THE HEAL FLOW

Healing requires consent — so healing a stranger isn't
involuntary:

  1. Medic types `+medical/heal Jex`
  2. Jex sees: "<medic> offers to heal you. Type healaccept to accept."
  3. Jex types `+medical/accept` (or `healaccept`)
  4. Medic rolls First Aid or Medicine vs wound difficulty
  5. Success: wounds reduced by one level per degree of success
  6. Failure: no effect; the target may be worse off on a fumble

/heal <target>

Initiates the consent flow. Targets can be any character, NPC,
or `self`. Healing yourself is harder (difficulty +5 per R&E
p.92).

If the target has no wounds, the command tells you so. If the
target is dead, you can't heal them — they need bacta tank or
a cloning facility (see `+help death`).

/accept

Completes the second half of the flow. Only works when an incoming
heal offer is pending. The medic's roll resolves immediately.

/rate [n]

Heal-rate is a throttle to prevent heal spam:
  - PCs: soft cap at 10 heals/hour (no penalty; narrative only)
  - NPC medics: configured by admin; typical 3-5/hour
  - /rate with no args shows your current rate
  - /rate <n> sets it (PC) or requests admin adjustment (NPC)

SKILL CHECK MECHANICS (R&E p.92)

First Aid: stabilizes and reduces Stun damage
  - Stun wound: Easy (10)
  - Wounded: Moderate (15)
  - Incapacitated: Difficult (20)
  - Mortally wounded: Heroic (30)

Medicine: the deeper skill, required for surgery/bacta/long-term
care. Any character can use First Aid; Medicine is a trained
specialty.

Degrees of success scale the healing:
  - Success: reduce by one level
  - Great (beat by 10+): reduce by two levels
  - Critical (Wild Die explodes): full heal of one level + stun clear

CHEAT SHEET
  +medical              = heal (default)
  +medical/heal <t>  = offer heal (also: heal)
  +medical/accept       = accept heal (also: healaccept, haccept)
  +medical/rate [n]     = view/set rate (also: healrate, hrate)

Sources: R&E First Aid (p.92), Medicine (p.93), wound scale
(R&E p.95–96).
