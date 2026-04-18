---
key: +smuggle
title: Smuggle — Contraband Jobs & Underworld Contacts
category: "Commands: Economy"
summary: All smuggling verbs live under +smuggle/<switch>. Browse the underworld board, take a run, deliver cargo, or jettison contraband to avoid a patrol — every verb is a switch here.
aliases: [smuggle, smugjob, myrun, activerun, cargo, +cargo, +smugjob, smugjobs, smugboard, smugcontacts, underworld, +underworld, +smugjobs, smugaccept, takesmug, takerun, smugdeliver, deliver, dropoff, smugdump, dumpcargo, jettison]
see_also: [smuggling, +mission, economy, factions, darkside, reputation]
tags: [economy, smuggling, underworld, command]
access_level: 0
examples:
  - cmd: "+smuggle"
    description: "Show your active smuggling run (cargo, destination, risk)."
  - cmd: "+smuggle/board"
    description: "Browse available smuggling jobs. Must be near a contact (cantina, docking bay, Jabba's court)."
  - cmd: "smugjobs"
    description: "Same as +smuggle/board (bare alias preserved)."
  - cmd: "underworld"
    description: "Board alias (flavor name for Outer Rim contacts)."
  - cmd: "+smuggle/accept s-2c4b"
    description: "Accept smuggling job s-2c4b (prefix match works)."
  - cmd: "takerun s-2c4b"
    description: "Same as +smuggle/accept (bare alias preserved)."
  - cmd: "+smuggle/view"
    description: "Show your active run. Same as bare +smuggle."
  - cmd: "cargo"
    description: "View active run alias."
  - cmd: "+smuggle/deliver"
    description: "Deliver cargo. Must be docked at the destination planet."
  - cmd: "deliver"
    description: "Same as +smuggle/deliver (bare alias preserved)."
  - cmd: "dropoff"
    description: "Another bare alias for /deliver."
  - cmd: "+smuggle/dump"
    description: "Jettison cargo out the airlock. No pay, no fine — avoids patrol confiscation."
  - cmd: "jettison"
    description: "Same as +smuggle/dump (bare alias preserved)."
  - cmd: "dumpcargo"
    description: "Another bare alias for /dump."
  - cmd: "+smuggle/board"
    description: "Lists all 3–5 available runs with cargo type, tier, reward, fine, and destination."
  - cmd: "+smugjobs"
    description: "Board alias (muscle memory preserved)."
---

All smuggling verbs are switches under +smuggle. Bare forms
(smugjobs, deliver, jettison, etc.) still work as aliases — typing
`deliver` and `+smuggle/deliver` reach the same code. The canonical
form is +smuggle/<switch>; the rest of this page uses it everywhere.

See `+help smuggling` for the conceptual overview of tiers, patrol
mechanics, and planet routes. This page is the command reference.

SWITCH REFERENCE
  /board     Browse available jobs (must be near a contact)
  /accept    Accept a job by its id (prefix match works)
  /view      Show your active run (also: bare '+smuggle', cargo, myrun)
  /deliver   Deliver cargo at the destination. Must be docked at the
             correct planet.
  /dump      Jettison cargo. No pay, no fine. Use this BEFORE patrol
             intercept if you know you can't beat the Con/Sneak roll.

ONE ACTIVE RUN AT A TIME. Deliver, dump, or wait for confiscation
before accepting another.

ACCESSING THE BOARD

The smuggling board isn't public. /board only works if you're in a
room that gives you access to underworld contacts — a cantina, a
docking bay, a spaceport, or Jabba's court. The board won't show in
the throne room or a residence; the bartender can't help you there.

Eligible room keywords: "cantina", "docking bay", "docking",
"spaceport", "jabba". If your current room matches any, the board
opens.

This restriction applies to /board AND /accept. You can review your
active run (/view) and deliver (/deliver) from anywhere.

CARGO TIERS (Galaxy Guide 6: Tramp Freighters p.78–82)

Tier       Cargo                Pay            Patrol   Difficulty
  0 Grey   Medical supplies     200–500 cr     0%       None
  1 Black  Weapons parts        500–1,500 cr   20%      Easy (10)
  2 Contr. Glitterstim          1,500–5,000    50%      Moderate (15)
  3 Spice  Raw spice            5,000–15,000   80%      Difficult (20)

Grey-market cargo never triggers patrols — it's legal, just unusual.
Black-market and up earn the Empire's attention. Spice runs are the
big-ticket jobs that built careers like Han Solo's.

INTERPLANETARY ROUTES (5 route tiers)

Route              Tier   Dest.          Pay            Patrol
  Local            Grey   Same planet    200–500 cr     0%
  Black Market     Black  Same planet    500–1,500 cr   20%
  Interplanetary   Black  Nar Shaddaa    1,500–3,000    30%
  Spice Run        Contr. Kessel         3,000–6,000    55%
  Core Run         Spice  Corellia       4,000–8,000    65%

Interplanetary and up require a ship and a hyperspace jump.

PATROL INTERCEPTS

Two checks can trigger a patrol encounter:
  1. LAUNCH CHECK — rolls when you launch your ship after accepting.
     Probability = TIER_PATROL_CHANCE[tier].
  2. ARRIVAL CHECK — rolls on hyperspace arrival at the destination
     planet. Per-planet probability (PLANET_PATROL_FREQUENCY):
       Corellia     0.60  (Core World — heavy customs)
       Nar Shaddaa  0.25  (Hutt space, but ISB cares)
       Kessel       0.20  (Imperial mining controlled)
       Tatooine     0.10  (Outer Rim — low patrol presence)

If intercepted, you roll Con OR Sneak (whichever pool is higher)
against the tier difficulty:
  - Success: "You slip past" — cargo intact, pay on delivery.
  - Failure: Cargo confiscated + fine = 50% of job reward deducted
             from your credits. Run marked FAILED on the board.

DIRECTOR LOCKDOWN

If the Director AI has raised a LOCKDOWN alert at the spaceport, add
+1 effective tier to patrol risk. A Grey-market run becomes as risky
as a Black-market one; Contraband becomes Spice-tier. Watch the news
and the alert level before you launch with a load of glitterstim in
your hold.

DARK-SIDE RELATIONSHIP

Smuggling contraband for credits is morally grey, not dark — the
game does NOT apply a DSP for taking a run. However, if your smuggling
supplies a faction whose agenda is harmful (e.g., weapons to a slave
operation), the mission-specific hooks may apply a DSP on delivery.
Smuggling medical supplies during an Imperial blockade may grant
light-side rep instead. See '+help darkside' for the model.

"Dark side pays more" applies — spice runs are the most lucrative
path in the entire economy, and they are also the one most likely
to put you in Imperial custody. (R&E p.135 for Force Points; the
choice is always yours.)

/accept <id>

Prefix matching works: if you type `+smuggle/accept s-2c` and
there's exactly one job starting with s-2c, it's accepted.

You'll see the cargo type, reward, fine, contact name, and dropoff.
The run appears in /view until you deliver, dump, or fail.

/view

Shows:
  - Tier + cargo type
  - Origin contact (e.g., "Jabba's lieutenant")
  - Dropoff location + planet
  - Reward and fine amounts
  - Patrol difficulty (for planning your roll)

/deliver

Requirements:
  1. Active run present.
  2. You're on a ship.
  3. The ship is docked (not in orbit or in-zone).
  4. You're docked on the RIGHT planet — interplanetary runs check
     the current_zone against PLANET_DOCK_ZONES.

If all met: /deliver runs the arrival patrol check one last time
(retroactively for ground-only runs), then pays out. You'll see:
  "Delivery complete. Glitterstim delivered to Jabba's warehouse.
   Payment received: 3,200 credits. Balance: 12,450 credits."

Post-delivery hooks fire: ships-log tick, territory influence at
the dropoff zone, profession-chain check (e.g., Jedi Smuggler path
progresses on first Corellia delivery), achievements.

/dump

The panic button. Cargo tumbles out the airlock. Run ends with no
pay and no fine. Use this when you're about to be intercepted and
know you won't make the Con/Sneak roll — better to lose the job
than to eat a 50% fine AND have your cargo confiscated.

Can be used from any ship room at any time (no patrol required).

CHEAT SHEET
  +smuggle/board     = browse (needs cantina / docking bay / spaceport)
  +smuggle/accept    = take a run (prefix id matching)
  +smuggle           = view active (also: /view, cargo, myrun)
  +smuggle/deliver   = deliver (also: deliver, dropoff)
  +smuggle/dump      = jettison (also: jettison, dumpcargo)

Sources: WEG Galaxy Guide 6: Tramp Freighters (GG6 p.78+) for the
cargo taxonomy; Con/Sneak rules per R&E p.93.
