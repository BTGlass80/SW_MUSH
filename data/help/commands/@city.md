---
key: "@city"
title: "@city — Player City Admin Commands"
category: "Commands: Admin"
summary: Six-form admin verb for moderating player cities — list, inspect, void-banish, set-rate-cap, force-dissolve, rename. Requires admin access. Mirrors the @security admin pattern.
aliases: []
see_also: [+city, cities, "@housing", "@security"]
tags: [admin, cities, moderation, command]
access_level: 2
examples:
  - cmd: "@city list"
    description: "List every active city across all planets (one line per city: name, planet, mayor, room count, treasury share)."
  - cmd: "@city inspect Sunshine Outpost"
    description: "Detailed dump for one city — founder/mayor, HQ tier, rooms, citizens, guests, banishments, motd, tax, revenue, maintenance state."
  - cmd: "@city void-banish Sunshine Outpost = Bob"
    description: "Lift Bob's banishment from Sunshine Outpost regardless of the original Mayor's preference."
  - cmd: "@city set-rate-cap Sunshine Outpost = 8"
    description: "Override the founder's rate-cap on Sunshine Outpost, accepting 5 / 5% / 0.05 (parsed to a fraction). Engine enforces the 10% absolute ceiling."
  - cmd: "@city dissolve Sunshine Outpost"
    description: "Force-dissolve a city for moderation reasons. NO treasury refund (intentional — distinguishes admin moderation from voluntary +city dissolve)."
  - cmd: "@city rename Sunshine = Sunrise Outpost"
    description: "Admin rename. Equals-sign separates old and new names since either may contain spaces."
---

Admin verb for moderating player cities. All six subforms require
admin access (AccessLevel.ADMIN). Following the SECMOD.1 admin
pattern, this is a single command with parameter-driven dispatch.

SUBCOMMAND REFERENCE
  list                                List all active cities
  inspect <name>                      Detailed city status dump
  void-banish <city> = <player>       Lift a banishment
  set-rate-cap <city> = <pct>         Override the founder rate cap
  dissolve <name>                     Force-dissolve (NO refund)
  rename <old> = <new>                Rename an active city

ARGUMENT CONVENTIONS
  - City lookup is case-insensitive exact-match. Partial-match
    is intentionally NOT supported — ambiguous matches would
    create surprise moderation actions on the wrong city.
  - Character lookup (void-banish) is also exact-match via
    db.get_character_by_name.
  - Two-arg subforms use `=` to disambiguate names with spaces.
    Single-arg subforms (list, inspect, dissolve) take the arg
    as a plain trailing token.
  - set-rate-cap accepts 5, 5%, or 0.05 — all parse to 0.05
    (5%). Values >= 1 are interpreted as percentages.
  - Changes take effect immediately. No restart required.

@CITY DISSOLVE vs +CITY DISSOLVE
  Admin force-dissolve and voluntary dissolve are intentionally
  different paths:

  - `+city dissolve` (player) goes through
    `engine.player_cities.dissolve_city` and **refunds 50% of
    the founding cost** to the treasury. This is the
    voluntary-winding-down path.
  - `@city dissolve` (admin) goes through
    `engine.player_cities.admin_dissolve_city` and **issues no
    refund**. This is the moderation path — typically used for
    policy violations or abandoned cities.

  Both cascade-clean the same way: city_rooms rows pruned,
  banishments and guests cleared, citizen-only flags dropped.
  The `player_cities` row is kept for audit (state='dissolved').

@CITY VOID-BANISH NOTES
  void-banish lifts a banishment without consulting the Mayor.
  Used when:
    - A banishment was placed in error and the Mayor is offline
    - A player has appealed to staff and prevailed
    - The Mayor themselves was banished by another admin and
      can't lift it

  The player can re-enter the city immediately after. If the
  Mayor re-banishes, the player can appeal again.

@CITY SET-RATE-CAP NOTES
  Used to discipline a Founder who set their cap punitively
  high (e.g., 9.9% on a high-traffic trade hub). The engine
  helper enforces the 10% absolute ceiling regardless of admin
  input, so `@city set-rate-cap X = 50` will be clamped or
  refused (the parser-side helper logs the clamp).

@CITY RENAME NOTES
  Used for:
    - Trademark / lore conflicts caught after the fact
    - Player request for a typo fix
    - Reserved-name collisions that slipped past the
      RESERVED_CITY_NAMES list

  The new name still has to pass the standard 3-32 char +
  reserved-list validation. Use `@city list` to see if the
  target name is already taken.

LOGGING
  Every @city action emits a log line at INFO level:
    [player_cities] ADMIN dissolve city=<id> name=<name> by=<admin>
    [player_cities] ADMIN void_banish city=<id> char=<id> by=<admin>
    [player_cities] ADMIN set_rate_cap city=<id> rate=<pct> by=<admin>
    [player_cities] ADMIN rename city=<id> from=<old> to=<new> by=<admin>

  ADMIN dissolves are logged separately from MAINT dissolves
  (the latter come from the maintenance grace expiring; see
  `+help cities` for the grace state machine).

CHEAT SHEET
  @city list                          = all active cities
  @city inspect <name>                = detailed status
  @city void-banish <city> = <name>   = lift banishment
  @city set-rate-cap <city> = <pct>   = override cap
  @city dissolve <name>               = force-dissolve (no refund)
  @city rename <old> = <new>          = rename

Sources: Player Cities Phase 6 admin per design v1.2 §11.5 +
§13. Pattern mirrors `@security` (SECMOD.1) and `@housing`
admin commands. For the player-facing side, see `+help +city`.
For the conceptual city overview (including the maintenance
grace state machine), see `+help cities`.
