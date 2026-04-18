---
key: +crew
title: Crew — Hire, Assign, Command NPC Crew
category: "Commands: Ships"
summary: All crew management verbs live under +crew/<switch>. Hire NPCs from a recruiting board, assign them to ship stations, give tactical orders in combat, or dismiss them — every verb is a switch here.
aliases: [crew, mycrew, +mycrew, hire, recruiting, hireboard, roster, assign, unassign, dismiss, firecrew, order, ord]
see_also: [crew, +roster, hire, stations, wages, ships, captainorders]
tags: [ships, crew, npcs, command]
access_level: 0
examples:
  - cmd: "+crew"
    description: "Show your crew roster (default — /roster)."
  - cmd: "+crew/roster"
    description: "Same as bare +crew — list hired NPCs, stations, and daily wages."
  - cmd: "crew"
    description: "Same as +crew/roster (bare alias preserved)."
  - cmd: "mycrew"
    description: "Another bare alias for /roster."
  - cmd: "+crew/hire"
    description: "Browse the recruiting board at your current location (cantina, spaceport)."
  - cmd: "hire"
    description: "Same as +crew/hire (bare alias preserved)."
  - cmd: "+crew/hire Kessa"
    description: "Hire Kessa from the recruiting board."
  - cmd: "hire 2"
    description: "Hire the 2nd NPC on the board (index alias)."
  - cmd: "+crew/assign Kessa pilot"
    description: "Assign Kessa to the pilot station on your current ship."
  - cmd: "assign Kessa pilot"
    description: "Same as +crew/assign (bare alias preserved)."
  - cmd: "+crew/unassign Kessa"
    description: "Remove Kessa from her station. She stays hired."
  - cmd: "unassign Kessa"
    description: "Same as +crew/unassign (bare alias preserved)."
  - cmd: "+crew/dismiss Kessa"
    description: "Fire Kessa. Wages stop; she leaves the crew."
  - cmd: "firecrew Kessa"
    description: "Another bare alias for /dismiss."
  - cmd: "+crew/order pilot evade"
    description: "Order the pilot NPC to take evasive maneuvers this round."
  - cmd: "order gunner fire TIE-Alpha"
    description: "Order the gunner NPC to fire at TIE-Alpha (bare alias preserved)."
---

All crew management verbs are switches under +crew. Bare forms
(hire, roster, assign, unassign, dismiss, order) still work as
aliases — typing `assign Kessa pilot` and `+crew/assign Kessa pilot`
reach the same code. The canonical form is +crew/<switch>; the rest
of this page uses it everywhere.

See `+help crew` for the conceptual overview of the NPC crew system.
This page is the command reference.

SWITCH REFERENCE
  /roster      View your crew (also: bare '+crew', crew, mycrew)
  /hire        Browse recruiting board / hire an NPC
  /assign      Put an NPC at a ship station
  /unassign    Pull an NPC off a station (stays hired)
  /dismiss     Fire an NPC (wages stop)
  /order       Give a tactical order during space combat

THE CREW LIFECYCLE

  (browse hiring board) → HIRED → ASSIGNED (at a station)
                               ↘ UNASSIGNED (still on payroll)
                               ↘ DISMISSED (off payroll, back to NPC pool)

/hire

Two modes:

  +crew/hire           → Show the recruiting board for this location
  +crew/hire <n|name>  → Hire a specific NPC

Recruiting boards are ROOM-SCOPED. Each cantina / spaceport / hiring
hall has its own set of available NPCs. The board generates on first
view per room and persists — the same 4–6 NPCs stay until hired or
the game-server restarts.

Board entries show name, template (pilot, smuggler, mechanic...),
tier (extra / average / novice / veteran / superior), primary skill,
and daily wage.

First day's wage is deducted immediately on hire. NPC joins your
roster and is ready to be assigned.

TIER AND WAGES

  Tier         Skill Range       Wage (cr/day)
  Extra        1D–2D             30
  Average      2D–3D             80
  Novice       3D+1–4D           150
  Veteran      4D+1–5D+2         400
  Superior     5D+2–6D+2         1,000

Running out of credits? Wages auto-deduct on the game's daily tick.
If you can't pay, crew auto-dismisses themselves.

/roster

Lists everyone you've hired:

  Name                 Role        Tier      Station      Wage
  Kessa                Pilot       Novice    pilot        150 cr/day
  Torvin               Gunner      Veteran   gunner       400 cr/day

Totals daily wages at the bottom; warns you if your credits cover
≤3 days. Assigned/unassigned status shown per NPC.

/assign <name> <station>

Put an NPC at one of six ship stations:

  Station     Skill Used              What They Do
  pilot       Space Transports        Fly the ship; react to pilot orders
  copilot     Space Transports        Assist pilot rolls
  gunner      Starship Gunnery        Fire weapons at targets
  engineer    Space Trans. Repair     Repair damaged systems
  navigator   Astrogation             Plot hyperspace jumps
  sensors     Sensors                 Scan, detect, identify

You must be aboard a ship when you assign. Only one NPC per station
per ship. Name-matching is fuzzy (first name, full name, or index).

/unassign <name>

Pull an NPC off their station. They stay hired (wages still apply)
but aren't contributing during combat/travel. Useful when swapping
roles between two NPCs.

/dismiss <name>

Fire the NPC. Wages stop immediately. They return to the NPC pool
and may eventually reappear on a recruiting board elsewhere.

/order <station> <action>

Override an NPC's auto-behavior for ONE combat round. Only works
during active space combat and only if the target station has an
NPC assigned.

Pilot orders:
  +crew/order pilot close <target>  → Close range with target
  +crew/order pilot flee            → Break off and flee
  +crew/order pilot tail <target>   → Get behind target
  +crew/order pilot evade           → Evasive maneuvers

Gunner orders:
  +crew/order gunner fire <target>  → Fire at specific target

Engineer orders:
  +crew/order engineer repair <system>  → Repair named system
                                          (shields, hull, engines, etc.)

The NPC acknowledges verbally in chat, then their turn resolves
with the overridden action. Without orders, NPCs use their default
AI behavior (automatic target selection, automatic repair
priorities).

ORDER ≠ CAPTAIN-ORDER. This is crew-order — direct instruction to
your hired NPCs at a specific station. Ship-scale commands (patrols,
fleet orders, etc.) use the captain-order system in `+help
captainorders`. If both systems claim a bare word, crew wins
(registration order). Canonical forms always disambiguate.

WAGE AFFORDABILITY GUARDS

/hire refuses if you can't afford one day's wage.
Daily tick deducts all wages; insufficient credits → auto-dismiss.
/roster warns when days_left ≤ 3.

The system is designed to be self-balancing — high-tier crew
outperform low-tier but cost significantly more. Running a
masterwork pilot-gunner-engineer team (all Superior) costs
3,000 cr/day, which demands consistent income from missions,
bounties, smuggling, or trade.

EXAMPLES

  (at Mos Eisley Cantina)
  +crew/hire
  → Shows 5 NPCs on the recruiting board.

  +crew/hire Kessa
  → "Kessa joins your crew for 150 credits/day. First day's
     wage paid. Balance: 3,850 credits."

  move docking_bay_94
  +crew/assign Kessa pilot
  → Kessa now assigned to pilot station.

  +crew/order pilot evade
  → "Kessa acknowledges: 'Evasive action, aye!'"

  +crew/dismiss Kessa
  → "Kessa leaves your crew. Wages stopped."

CHEAT SHEET
  +crew               = view roster (also: /roster, crew, mycrew)
  +crew/hire          = browse or hire (also: hire, recruiting)
  +crew/assign        = place at station (also: assign)
  +crew/unassign      = pull off station (also: unassign)
  +crew/dismiss       = fire (also: dismiss, firecrew)
  +crew/order <s> <a> = combat order (also: order, ord)

Sources: NPC crew system is game-original. Skill mappings use
canonical R&E space-combat skills (Space Transports, Starship
Gunnery, Astrogation, Sensors — R&E p.89, p.93). Tier wages and
skill-pool generation follow the hiring-board design in
`engine/hiring_board.py`.
