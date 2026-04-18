---
key: +combat
title: Combat — All Ground Combat Verbs
category: "Commands: Combat"
summary: All ground combat verbs live under +combat/<switch>. Attack, dodge, parry, aim, cover, flee, Force Points, PvP challenges — every combat action is a switch here.
aliases: [combat, cs, +cs, attack, att, kill, shoot, hit, dodge, fulldodge, fdodge, parry, fullparry, fparry, soak, aim, flee, run, retreat, pass, disengage, resolve, range, distance, cover, hide, forcepoint, fp, +fp, cpose, combatpose, crolls, challenge, duel, accept, decline, refuse]
see_also: [combat, dodge, melee, ranged, wounds, cover, multiaction, dice, scale, forcepoints, darkside, cpose]
tags: [combat, core, command]
access_level: 0
examples:
  - cmd: "+combat"
    description: "Show current combat status (combatants, wounds, initiative order)."
  - cmd: "+combat/attack greedo"
    description: "Attack Greedo with your equipped weapon. Auto-detects skill (ranged, melee, brawling)."
  - cmd: "+combat/attack thug cp 2"
    description: "Attack thug, spending 2 Character Points on the roll (+1 pip per CP, max 5)."
  - cmd: "+combat/attack guard stun"
    description: "Fire in stun mode (blasters only). Damage is stun damage."
  - cmd: "+combat/dodge"
    description: "Reactive dodge. Rolls against ONE incoming ranged attack this round."
  - cmd: "+combat/fulldodge"
    description: "Full dodge. Entire round spent dodging; adds to difficulty for ALL incoming ranged."
  - cmd: "+combat/parry"
    description: "Reactive parry against melee. Uses melee parry, brawling parry, or lightsaber skill."
  - cmd: "+combat/fullparry"
    description: "Full parry. Entire round defending against melee."
  - cmd: "+combat/soak 3"
    description: "Pre-declare 3 CP to spend on soak if you take damage this round (max 5, R&E p.55)."
  - cmd: "+combat/aim"
    description: "Spend a round aiming for +1D on next attack (cumulative to +3D max)."
  - cmd: "+combat/cover half"
    description: "Take half cover (+2D against ranged). Levels are quarter, half, 3-quarter, full."
  - cmd: "+combat/range greedo short"
    description: "Move yourself to short range from Greedo. Bands are pointblank, short, medium, long."
  - cmd: "+combat/flee"
    description: "Attempt to leave combat. Opposed roll vs nearest enemy."
  - cmd: "+combat/forcepoint"
    description: "Spend a Force Point to DOUBLE all dice this round. Declaration phase only."
  - cmd: "+combat/pose <narrative text>"
    description: "Submit your round pose during the posing window."
  - cmd: "+combat/rolls"
    description: "Show the initiative roll breakdown for the current round."
  - cmd: "+combat/challenge Jex"
    description: "PvP challenge. Target must /accept within 10 minutes for open PvP in contested zones."
---

All ground combat verbs are switches under +combat. Bare forms
(attack, dodge, parry, etc.) still work as aliases — typing
'attack greedo' and '+combat/attack greedo' reach the same code.
The canonical form is +combat/<switch>; the rest of this page uses
it everywhere.

See '+help combat' for the conceptual rules of how a combat round
works. This page is the command reference.

SWITCH REFERENCE
  /attack      Attack a target (ranged, melee, or brawling auto-detected)
  /dodge       Reactive dodge vs ONE ranged attack (uses your action)
  /fulldodge   Full dodge — entire round, applies to ALL ranged
  /parry       Reactive parry vs ONE melee attack (uses your action)
  /fullparry   Full parry — entire round, applies to ALL melee
  /soak <1-5>  Pre-declare CP on damage resistance (R&E p.55)
  /aim         Spend a round aiming — +1D next attack, cumulative to +3D
  /cover       Take cover — quarter / half / 3-quarter / full
  /range       Check or move to a range band — pointblank, short, medium, long
  /flee        Attempt to leave combat via opposed roll
  /disengage   Leave peacefully when combat is over
  /pass        Skip your action this round
  /forcepoint  DOUBLE all dice this round (R&E p.135)
  /pose        Submit narrative pose during posing window
  /rolls       Show initiative roll breakdown
  /challenge   PvP: issue challenge to another player
  /accept      PvP: accept a pending challenge
  /decline     PvP: decline a pending challenge
  /resolve     Admin: force-resolve the round
  /status      Show combat status (also: bare '+combat' with no switch)

THE COMBAT ROUND
  1. INITIATIVE — Everyone rolls Perception. Highest acts first.
  2. DECLARATION — In REVERSE initiative order, each combatant
     declares actions (attack, dodge, aim, flee, soak, FP, etc.).
     Declaring later is an advantage — you see what others plan.
  3. RESOLUTION — In initiative order, actions resolve. Hits, damage,
     wound rolls all happen in this phase. The engine narrates.
  4. POSING — 30-second window for +combat/pose <your narrative>.
     Skip with /pass or let the auto-pose run.

MULTI-ACTION PENALTY (R&E p.83)
Each additional action in a round costs -1D from ALL your rolls:
  1 action    no penalty
  2 actions   -1D on everything
  3 actions   -2D on everything
  4 actions   -3D on everything

Common combinations:
  dodge + attack          = -1D to both
  attack + attack         = -1D to both (split-fire one weapon)
  dodge + attack + aim    = -2D to all three

Declare carefully. Sometimes one aimed shot beats three sloppy ones.
See '+help multiaction' for the full table.

──────────────────────────────────────────────────────────────────────
  /attack <target> [with <skill>] [damage <dice>] [cp <N>] [stun]
──────────────────────────────────────────────────────────────────────
Attack a target with your equipped weapon. If no combat is active,
starts one. Skill is auto-detected from the weapon's type:

  Blaster / rifle / heavy weapon  → ranged skill (blaster, etc.)
  Sword / knife / vibroblade      → melee combat
  Unarmed                          → brawling
  Lightsaber                       → lightsaber skill

DIFFICULTY BY RANGE (R&E p.95-99)
Difficulty to hit scales with range band:
  Point-blank (0-3m)       Very Easy (5)
  Short (3-10m)            Easy (10)
  Medium (10-30m)          Moderate (15)
  Long (30-100m)           Difficult (20)

Moving targets, partial cover, and called shots all add difficulty.
See '+help cover' and '+help range' for the modifier stack.

OPTIONS
  with <skill>   Override the auto-detected skill (e.g., "attack thug
                 with brawling" to punch someone holding a blaster).
  damage <dice>  Override weapon damage (admin/demo).
  cp <N>         Spend N Character Points on the attack roll. Each
                 CP is +1 pip. Max 5 CP/round per R&E. Declared up
                 front; spent only if you roll.
  stun           Fire in stun mode (blasters/stun batons only).
                 Damage becomes stun damage — knocks out, doesn't kill.

EXAMPLES
  +combat/attack stormtrooper
  +combat/attack thug with brawling
  +combat/attack greedo cp 2
  +combat/attack guard stun
  attack stormtrooper           (bare alias, identical)

──────────────────────────────────────────────────────────────────────
  /dodge   /fulldodge   /parry   /fullparry
──────────────────────────────────────────────────────────────────────
Reactive defenses. Declared in the declaration phase; the defender
rolls in the resolution phase against the attacker's total.

DODGE (ranged defense)
  /dodge       One action. Your Dodge roll replaces the base difficulty
               for ONE incoming ranged attack. Additional ranged hits
               this round get the normal difficulty.
  /fulldodge   Full round. Your full Dodge pool applies to EVERY
               incoming ranged attack this round. Cannot attack, aim,
               or do anything else.

PARRY (melee defense)
  /parry       As /dodge, but for melee. Rolls the appropriate parry
               skill: melee parry, brawling parry, or lightsaber
               (whichever matches your equipped weapon or bare fists).
  /fullparry   Full round of melee defense. Same trade-off as fulldodge.

WHEN TO GO FULL
  Outnumbered 3+ enemies shooting you  → /fulldodge (one -1D hit is
                                          better than three clean ones)
  Badly wounded and can't afford a hit → /fulldodge or /fullparry
  Stormtroopers at short range          → /fulldodge; their accuracy
                                          is bad but numbers are scary

See '+help dodge' and '+help melee' for the skill mechanics.

──────────────────────────────────────────────────────────────────────
  /soak <1-5>
──────────────────────────────────────────────────────────────────────
Pre-declare Character Points to spend on your Strength roll to resist
damage, but ONLY if you actually get hit (R&E p.55).

  +combat/soak 3   Sets 3 CP aside for soak. If you take damage this
                   round, 3 CP are spent and your Strength roll gets
                   +3 pips. If you don't take damage, the CP are not
                   spent.

Max 5 CP per round (R&E hard cap). Does not stack with /forcepoint
in the same round — FP doubles Strength already; soak CP would
be redundant.

Declaration-phase only. You cannot soak after the hit is announced.

──────────────────────────────────────────────────────────────────────
  /aim
──────────────────────────────────────────────────────────────────────
Spend a round aiming instead of attacking. Gain +1D on your next
attack roll, cumulative to +3D maximum (three rounds of aiming).

AIM BREAKS ON
  Moving          Any deliberate movement loses aim bonus
  Taking damage   A hit breaks concentration
  Dodging         Declaring dodge cancels accumulated aim
  Switching target   Aim is target-specific

AIM DOES NOT BREAK ON
  Posing, being in cover, changing stance within the same spot,
  other combatants moving around you.

Good for snipers, marksmen, called-shot setups. Use with cover for
the classic "hunkered down and picking targets" posture.

──────────────────────────────────────────────────────────────────────
  /cover [quarter|half|3/4|full]
──────────────────────────────────────────────────────────────────────
Take cover behind whatever's around. Adds difficulty to ranged attacks
against you. Costs your action. Room environment caps max cover level.

LEVELS (R&E p.99)
  quarter   +1D defense  (low wall, desk corner)
  half      +2D defense  (pillar, overturned table)
  3/4       +3D defense  (doorway, barricade)
  full      untargetable, cannot be shot — but cannot shoot either

TRADEOFF
  Attacking from cover reduces it to quarter for that round. Sticking
  your head up to fire loses most of the protection.

Shown in combat status. Check '+combat/status' to see current cover
levels for everyone.

──────────────────────────────────────────────────────────────────────
  /range <target> [band]
──────────────────────────────────────────────────────────────────────
View or change your range band to a target. With just a target, shows
current ranges to all combatants.

BANDS (WEG 5-10-15-20 progression)
  pointblank   0-3m   Very Easy  (5)   — melee distance
  short        3-10m  Easy       (10)
  medium       10-30m Moderate   (15)
  long         30-100m Difficult (20)

Shortforms accepted: pb, s, med/m, l

Range changes cost movement. The engine tracks per-target ranges
independently — you can be at short to the stormtrooper and long
to the sniper simultaneously.

──────────────────────────────────────────────────────────────────────
  /flee   /disengage   /pass
──────────────────────────────────────────────────────────────────────
/flee        Attempt to leave combat. Opposed roll — your Dodge vs.
             nearest enemy's Perception. Win and you're out. Lose and
             you take an attack of opportunity. Can only try once per
             combat; failing burns the round.

/disengage   Leave combat peacefully. Only works when no enemies
             remain hostile (combat is effectively over). Cleans up
             the combat state without a roll.

/pass        Skip your action this round. Declaration phase: you're
             marked as taking no action. Posing phase: the engine
             writes an auto-pose for you. Useful when you don't want
             to multiaction-penalty your defenses.

──────────────────────────────────────────────────────────────────────
  /forcepoint  (also: /fp)
──────────────────────────────────────────────────────────────────────
Spend a Force Point to DOUBLE all dice you roll this round (R&E
p.135). Skill dice, attribute dice, wild die — all doubled.

DECLARATION-PHASE ONLY. You cannot spend FP after you've seen the
attacker's roll or the damage. Decide up front; live with it.

FP BEHAVIOR
  Heroic spend   Used to save a life, uphold justice, protect the
                 innocent. May be returned at adventure end.
  Selfish spend  Used for pure personal gain (killing a bounty,
                 rolling for wealth). Lost, and may earn a DSP.
  Dark-side     Used against helpless enemies, civilians, or
                 for cruelty. Always lost + earns a DSP.

Cannot combine with CP spending in the same round. Cannot combine
with /soak. Doubles your dice — that's already the "I'm bringing
everything I have" moment.

See '+help force' and '+help darkside' for the broader system.

──────────────────────────────────────────────────────────────────────
  /pose <narrative>   /rolls   /status
──────────────────────────────────────────────────────────────────────
/pose    Submit your narrative pose during the 30-second posing
         window after resolution. The engine posts your pose alongside
         the mechanical outcome.

         Short aliases: 'cpose' and 'combatpose' still work.

/rolls   Show the initiative roll breakdown for the current round.
         Useful when you want to see why someone went first.

/status  (or bare +combat with no switch) — show combat state:
         combatants, wound levels, current ranges, declared actions,
         round number, cover levels.

──────────────────────────────────────────────────────────────────────
  /challenge <player>   /accept <player>   /decline [player]
──────────────────────────────────────────────────────────────────────
Consensual PvP for contested zones. Open PvP in LAWLESS zones bypasses
this whole system.

/challenge   Issue a challenge to another player. They have 10 minutes
             to /accept or /decline. Both sides must consent before
             attacks land.
/accept      Accept a pending challenge from a specific challenger.
             Opens mutual combat.
/decline     Decline a specific pending challenge. Without a name,
             declines the most recent one.

Challenges expire after 10 minutes of no response. You can only
attack a player who's consented (or in a lawless zone).

──────────────────────────────────────────────────────────────────────
  /resolve  (ADMIN/BUILDER ONLY)
──────────────────────────────────────────────────────────────────────
Force-resolve the current combat round, skipping the normal posing
window. For admin intervention when a combat is stuck waiting on an
AFK player.

Requires Builder+ access level. Not for player use.

CHEAT SHEET: ONE LINE PER SWITCH
  Attack   /attack t   /dodge   /fulldodge  /parry   /fullparry
  Actions  /aim        /soak N  /cover L    /range t b
  Flow     /flee       /disengage /pass
  Power    /forcepoint (/fp)
  Meta     /pose text  /rolls   /status    (bare +combat)
  PvP      /challenge  /accept  /decline
  Admin    /resolve
