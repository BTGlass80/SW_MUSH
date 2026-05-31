---
key: +city
title: City — Player City Governance
category: "Commands: Economy"
summary: All player-city verbs under +city/<switch>. Found a city on contested or lawless ground, claim expansion rooms, manage citizens and guests, set the city motto, collect taxes, and teleport home as a citizen. Admin tools live at @city.
aliases: [city]
see_also: [cities, housing, +home, territory, shopfront]
tags: [economy, cities, governance, command]
access_level: 0
examples:
  - cmd: "+city"
    description: "Show the +city subcommand cheat-sheet."
  - cmd: "+city found Sunshine Outpost"
    description: "Org leader founds a city around the org's tier-5 HQ. Requires 50+ zone influence, treasury, and a contested or lawless zone."
  - cmd: "+city dissolve Sunshine Outpost"
    description: "Org leader voluntarily dissolves the city; treasury gets a 50% refund."
  - cmd: "+city claim north"
    description: "Claim the room one step north of an already-owned city room (24h cooldown per city)."
  - cmd: "+city claim 4231"
    description: "Claim a specific adjacent room by explicit id."
  - cmd: "+city release"
    description: "Release the room you're standing in back to the wilderness (50% refund)."
  - cmd: "+city info"
    description: "Show the current city: HQ tier, room count, treasury, tax rate, citizens, grace state."
  - cmd: "+city map"
    description: "ASCII map of the current city's rooms."
  - cmd: "+city citizens"
    description: "List members + guests of the current city."
  - cmd: "+city list"
    description: "List all active cities across the galaxy (paged, 25 per page)."
  - cmd: "+city motd Welcome to Sunshine."
    description: "Set the message-of-the-day shown on every city-room entry (Mayor/Founder; 240 char max)."
  - cmd: "+city mayor Janna"
    description: "Reassign Mayor to Janna (Founder only; Founder is immutable)."
  - cmd: "+city guards"
    description: "View NPC guards stationed in this city (Phase 7)."
  - cmd: "+city guest add Jex"
    description: "Grant Jex guest access to the city (Mayor/Founder)."
  - cmd: "+city guest remove Jex"
    description: "Revoke Jex's guest access."
  - cmd: "+city banish Vex"
    description: "Banish Vex for 30 days (Mayor/Founder)."
  - cmd: "+city unbanish Vex"
    description: "Lift Vex's banishment early."
  - cmd: "+city citizenroom on"
    description: "Mark the current room as citizen-only (Mayor/Founder)."
  - cmd: "+city citizenroom off 4231"
    description: "Clear the citizen-only flag on a specific room."
  - cmd: "+city tax view"
    description: "View current tax rate and weekly + cumulative revenue."
  - cmd: "+city tax set 5"
    description: "Set tax rate to 5% (Mayor/Founder; must be within the rate cap)."
  - cmd: "+city tax ratecap 8"
    description: "Set the maximum rate the Mayor may set, in percent (Founder only; absolute ceiling 10%)."
  - cmd: "+city home"
    description: "Teleport to the city's HQ entry (citizen only; 1-hour cooldown; same-zone; not in combat or space)."
  - cmd: "@city"
    description: "Admin-only — player city admin commands (NATIVE @-PREFIX, not under +city)."
---

All player-city verbs live under +city/<switch>. The bare `city`
alias is preserved.

See `+help cities` for the conceptual overview of founding,
expansion tiers, governance, taxation, and the four-week
maintenance grace period. This page is the command reference.

SUBCOMMAND REFERENCE
  /found <name>           Found a city (org leader only)
  /dissolve <name>        Voluntarily dissolve (50% treasury refund)

  EXPANSION (org leader)
  /claim <direction>      Claim an adjacent room (24h cooldown per city)
  /claim <room_id>        Claim by explicit room id
  /release [room_id]      Release a room (default: current room)

  GOVERNANCE
  /info                   Details for the city you're in
  /map                    ASCII map
  /citizens               Members + guests
  /list                   All active cities (paged)
  /motd <text>            Set message-of-the-day (Mayor/Founder)
  /mayor <player>         Reassign Mayor (Founder only)
  /guards                 View NPC guards (Phase 7)
  /guest add <player>     Grant guest access (Mayor/Founder)
  /guest remove <player>  Revoke guest access
  /banish <player>        Banish 30 days (Mayor/Founder)
  /unbanish <player>      Lift banishment early
  /citizenroom on|off [room_id]
                          Mark/unmark a room as citizen-only

  TAXATION
  /tax view               Current rate + revenue
  /tax set <pct>          Set rate, 0-10% (Mayor/Founder, within cap)
  /tax ratecap <pct>      Set rate cap, 0-10% (Founder only)

  CITIZEN BENEFITS
  /home                   Teleport to city HQ entry (citizen, 1h cd)

FOUNDING REQUIREMENTS
  Per design v1.2 §2:
    - Org leader (rank 5+)
    - 50+ influence in the target zone
    - Zone security must be contested or lawless
    - Tier-5 HQ owned by the org in this zone
    - Treasury covers the founding cost:
        outpost       25,000 cr   (up to 5 expansion rooms)
        chapter_house 75,000 cr   (up to 10 expansion rooms)
        fortress      200,000 cr  (up to 20 expansion rooms)
    - Name passes validation (3-32 chars, not on the reserved
      canonical-location list — see `+help cities`)

  Founder is **immutable** for the city's lifetime. Mayor is
  reassignable (Founder may call +city/mayor <player>).

EXPANSION
  Each +city/claim debits 5,000 cr from the org treasury and
  costs zone influence (same threshold as founding). Limit is
  one new claim per 24 hours per city. Releasing a room refunds
  50% of the claim cost.

CITIZEN-ONLY ROOMS
  +city/citizenroom flags a city room as citizen-only. Only
  citizens of that city (members of the founding org or
  registered guests) can enter. Used for treasury rooms,
  council chambers, members-only watering holes, etc.

  IMPORTANT — flagging is **suspended** when the city enters week
  2+ of the maintenance grace period; existing flags are bulk-
  cleared at the week-2 boundary. Refill the org treasury to
  recover. See `+help cities` "Grace period" for the full
  state machine.

TAX
  +city/tax sets a 0-10% surcharge on commerce inside city rooms
  (purchases, shopfront sales, training fees). Revenue rolls
  into the org treasury weekly. Mayor can set the rate within
  the Founder-set cap; absolute ceiling is 10%.

  IMPORTANT — tax collection **ceases** at week 3 of the grace
  period. The rate stays settable so the Mayor can prepare for
  recovery, but no credits flow until the treasury is refilled.

+CITY/HOME
  Citizens of a city can use +city/home to teleport to the
  city's HQ entry room from anywhere in the same zone. One-hour
  cooldown. Disabled in combat and in space. Non-citizens get
  the standard "you're not a citizen here" error.

ADMIN COMMANDS — NATIVE @-PREFIX
  @city (admin) stays at its native @-prefix form. See
  `+help @city` for the admin reference. Folding @city into
  +city/admin would shadow the admin permission gate.

CHEAT SHEET
  +city                  = subcommand list
  +city found <name>     = found a city (org leader)
  +city claim <dir>      = claim adjacent room
  +city info             = current-city details
  +city map              = ASCII map
  +city citizens         = members + guests
  +city motd <text>      = set MOTD (Mayor/Founder)
  +city tax set <pct>    = set rate (Mayor/Founder)
  +city home             = citizen teleport home
  @city                  = admin (NATIVE @-PREFIX)

Sources: Player Cities system per design v1.2 (founding +
expansion + governance + tax + maintenance). Influence + zone
security are shared with the Drop 6 territory system —
see `+help territory`. Tier-5 HQ purchase lives in
`+help housing` and `+help +home`. For the long-form
conceptual overview, see `+help cities`.
