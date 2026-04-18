---
key: +ship
title: Ship — Status, Info, Fleet, Mods, and Maintenance
category: "Commands: Ships"
summary: All ship-admin verbs live under +ship/<switch>. View tactical status, browse the catalog, inspect template specs, manage your owned fleet, rename, repair, or modify your ship — every verb is a switch here.
aliases: [ship, shipstatus, ss, +shipstatus, +ss, ships, shiplist, +ships, myships, ownedships, +myships, shipinfo, si, +shipinfo, shiprepair, srepair, +shiprepair, shipname, +shipname]
see_also: [ships, hyperspace, launch, land, crew, +crew, +pilot, +bridge, capital]
tags: [ships, admin, command]
access_level: 0
examples:
  - cmd: "+ship"
    description: "Show tactical status of your ship (default — /status)."
  - cmd: "+ship/status"
    description: "Same as bare +ship — hull, systems, shields, power, damaged systems."
  - cmd: "ship"
    description: "Same as +ship (bare alias preserved)."
  - cmd: "ss"
    description: "Short form for ship-status."
  - cmd: "+ship/list"
    description: "Browse the full ship catalog — every template the game supports."
  - cmd: "ships"
    description: "Same as +ship/list (bare alias preserved)."
  - cmd: "shiplist"
    description: "Another bare alias for /list."
  - cmd: "+ship/info x-wing"
    description: "Show stats for the X-Wing template — speed, hull, weapons, crew slots."
  - cmd: "shipinfo yt-1300"
    description: "Same as +ship/info yt-1300 (bare alias preserved)."
  - cmd: "si yt-1300"
    description: "Short form — template specs for YT-1300."
  - cmd: "+ship/mine"
    description: "List every ship you own. Shows name, template, current zone / dock."
  - cmd: "myships"
    description: "Same as +ship/mine (bare alias preserved)."
  - cmd: "+ship/rename Millennium Falcon"
    description: "Rename your owned ship (S57a). You must own the ship; 2–40 chars, alphanumerics + spaces/hyphens/apostrophes."
  - cmd: "shipname Millennium Falcon"
    description: "Same as +ship/rename (bare alias preserved)."
  - cmd: "+ship/repair"
    description: "Engineer-station action — roll Space Transports Repair against a damaged system."
  - cmd: "+ship/mods"
    description: "View installed modifications on your ship."
  - cmd: "+ship/install Engine Booster (Basic)"
    description: "Install a crafted ship component into the appropriate slot."
  - cmd: "+ship/uninstall 0"
    description: "Remove the mod in slot 0. Slot indices shown by +ship/mods."
  - cmd: "+ship/log"
    description: "View your ship's log — milestones, combat kills, routes, major events."
  - cmd: "+ship/quirks"
    description: "View installed ship quirks — template-specific or crafted traits."
---

All ship-admin verbs are switches under +ship. Bare forms
(ship, ships, shipinfo, myships, shipname, shiprepair) still work
as aliases — typing `myships` and `+ship/mine` reach the same code.
The canonical form is +ship/<switch>; the rest of this page uses
it everywhere.

See `+help ships` for the conceptual overview of ship types and
rules. This page is the command reference.

SWITCH REFERENCE
  /status     Tactical status of your ship (default — bare +ship)
  /list       Browse the full ship catalog (all templates)
  /info <t>   Show stats for a specific ship template
  /mine       List ships you own
  /rename <n> Rename your owned ship (2–40 characters)
  /repair     Engineer repair action on a damaged system
  /mods       View installed modifications
  /install <item>    Install a crafted ship component
  /uninstall <slot>  Remove a mod by slot number
  /log        Ship's log — milestones and major events
  /quirks     View installed ship quirks

ONE DEFAULT. Bare `+ship` (no switch) shows your current ship's
tactical status — the most common "what's my state" query.

SHIP OWNERSHIP MODEL

You can own multiple ships. At any given moment you're ABOARD at
most one of them (the ship whose bridge-room you're in). /status
shows the ship you're aboard; /mine lists everything you own; /info
is a catalog lookup against any template in the game (you don't
need to own it).

/status  (default)

Shows the ship you're currently aboard:
  - Name + template
  - Hull damage (current / max)
  - Damaged systems list
  - Shield level, power allocation
  - Current zone or dock location
  - Active orders (if in combat)
  - Assigned crew by station

If you aren't aboard a ship, returns "You're not aboard a ship."

/list

Browse the catalog of every ship template the game supports. Each
entry shows template key, display name, class (fighter / light
freighter / capital / etc.), and a one-line description. Use
/info <template> to drill into specific stats.

/info <template>

Detailed stats for a ship type. Shows:
  - Hull, shields, maneuverability, speed
  - Crew slots (pilot / copilot / gunner / engineer / navigator /
    sensors)
  - Weapons (type, fire control, damage)
  - Cargo capacity, passenger capacity
  - Hyperdrive class + backup
  - Sensor rating
  - Hull type (fighter / patrol_craft / light_freighter / shuttle /
    capital)

This is catalog information — doesn't require ownership.

/mine

Your owned fleet. Each entry:
  - Ship name (you named it) + template
  - Current zone or dock location
  - Hull damage + damaged systems summary
  - Last boarded timestamp

Most players own one ship, but there's no hard cap. Hoarding ships
has upkeep costs — see '+help ships' for maintenance details.

/rename <new-name>  (S57a — absorbs shipname command)

Rename your owned ship. Rules:
  - You must OWN the ship (the first one in your /mine list)
  - Name must be 2–40 characters
  - Only letters, numbers, spaces, hyphens, and apostrophes allowed
  - Must be the ship you're aboard? No — works on any owned ship

Example:
  +ship/rename Millennium Falcon
  → "Ship renamed: Old Scrap → Millennium Falcon"

Triggers the spacer-quest `use_command` hook with command=shipname
(legacy trigger name preserved for FDTS progression).

/repair

Engineer-station action — roll Space Transports Repair against a
damaged system to restore it. You must be aboard, at the engineer
station, with a damaged system present. Difficulty scales with
damage severity; partial successes repair one level.

See '+help engineer' for the repair mechanics and difficulty
ladder.

/mods

Shows installed modifications on your ship. Each mod is one of:
  - Weapon retrofit (damage +, fire control +)
  - System upgrade (shields +, hyperdrive backup)
  - Convenience (cargo expansion, passenger comfort)

Slot 0 is the first mod, 1 the second, etc. Use /uninstall <slot>
to remove a specific mod.

/install <item-name>

Install a crafted ship component from your inventory. Component
must match a free mod slot on your ship's template. Some slots
are exclusive (can't install two hyperdrive backups, for example).

Installation consumes the crafted item and persists the mod to
the ship. Removable via /uninstall.

/uninstall <slot>

Remove the mod at the given slot index. Removed mods vanish
(not returned to inventory — uninstall is a destructive action
representing ripped-out parts).

/log

Ship's log — an in-fiction record of milestones:
  - First launch, first combat, first hyperspace jump
  - Notable kills, deliveries, rescues
  - Boarding events, territory shifts
  - Commander handoffs (if you've had the ship long enough)

Good for RP continuity and nostalgia. Updated automatically as
events occur.

/quirks

Some ship templates come with built-in quirks (YT-1300s are
famously temperamental). Crafted mods can also impart quirks.
/quirks shows what your specific ship has, including their
mechanical effects (small dice modifiers, reliability penalties,
flavor effects).

SHIP CLASSES AND WHAT THEY CAN DO

  fighter         X-Wing, TIE, Y-Wing — small, agile, NOT boardable,
                  no cargo missions
  patrol_craft    Imperial patrol ships — midweight, boardable
  light_freighter YT-1300, YT-2400, Corellian Action VI — cargo-
                  capable, crew of 2+, boardable
  shuttle         Lambda, Sentinel — passenger-focused, slow combat
  capital         Star Destroyer, Nebulon-B, Mon Cal — massive
                  crews, scale 4, different ruleset

Your ship class gates which encounter types apply to you (fighters
skip cargo encounters; light freighters get boarded) — see
'+help encounters'.

EXAMPLES

  (aboard your YT-1300)
  +ship
  → Tactical status of your ship.

  +ship/list
  → Browse all templates in the catalog.

  +ship/info x-wing
  → X-Wing stats.

  +ship/mine
  → "You own 1 ship: Old Scrap (yt-1300) — docked at Mos Eisley Bay 94"

  +ship/rename Millennium Falcon
  → "Ship renamed: Old Scrap → Millennium Falcon"

  (after combat damage)
  +ship
  → Shows damaged: shields, starboard_laser
  +ship/repair  (at engineer station)
  → Roll Space Transports Repair against shields difficulty.

  +ship/mods
  → "Installed: [0] Engine Booster (Basic)"
  +ship/uninstall 0
  → "Engine Booster (Basic) removed."

CHEAT SHEET
  +ship              = view status (also: /status, ship, ss)
  +ship/list         = catalog (also: ships, shiplist)
  +ship/info <t>     = template specs (also: shipinfo, si)
  +ship/mine         = your fleet (also: myships, ownedships)
  +ship/rename <n>   = rename (also: shipname)
  +ship/repair       = engineer repair (also: shiprepair, srepair)
  +ship/mods         = installed modifications
  +ship/install <i>  = install crafted component
  +ship/uninstall <n>  = remove mod by slot
  +ship/log          = milestones record
  +ship/quirks       = template/crafted traits

S57A NOTES

The +ship umbrella now absorbs all sibling ship-admin commands:
  - `+ships` → still works; routes to /list
  - `+shipinfo <t>` → still works; routes to /info
  - `+myships` → still works; routes to /mine
  - `+shiprepair` → still works; routes to /repair
  - `shipname <n>` → still works; routes to /rename (new)

The `gunnery` alias was also cleaned up in S57a — it used to be
both a bare alias for `GunnerCommand` AND for `BoardCommand` (an
obvious bug). It now unambiguously means "take the gunner seat".

Sources: Ship template system is game-original, inspired by
SWG and EVE. Skill rolls use standard R&E Space Transports
(R&E p.89), Space Transports Repair (R&E p.93).
