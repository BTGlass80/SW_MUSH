---
key: cities
title: Player Cities
category: Economy
summary: Player-built cities anchored on a tier-5 organization HQ. Found on contested or lawless ground, claim adjacent rooms as expansion, collect tax, banish troublemakers — but pay weekly maintenance from the org treasury or enter a four-week grace period that ends in auto-dissolve.
aliases: [city, playercities, pcity]
see_also: [+city, "@city", housing, +home, territory, factions, shopfront, economy]
tags: [economy, cities, governance, territory]
access_level: 0
---

Player cities are the org-level deepening of the housing and
territory systems. A city is a named, mapped region of rooms,
anchored on a single tier-5 organization HQ, run by a Mayor on
behalf of the founding org. Cities can tax commerce within their
walls, banish enemies, host citizen-only spaces, and (Phase 7)
station NPC guards. They also cost credits to maintain — let
the treasury run dry and the city slips into a four-week grace
period that ends in auto-dissolve.

FOUNDING

A city is declared with `+city found <name>`. Requirements:

  - You are the leader of an organization at rank 5+.
  - Your org owns a tier-5 HQ in the target zone.
  - Your org has 50+ influence in the zone (same threshold as
    a Drop 6 territory claim).
  - The zone's security level is **contested** or **lawless**.
    Secured zones are off-limits to player cities — the
    governing authority does not allow private settlements
    inside their writ.
  - The org treasury covers the founding cost, set by HQ subtype:

        Outpost        25,000 cr    (up to 5 expansion rooms)
        Chapter House  75,000 cr    (up to 10 expansion rooms)
        Fortress      200,000 cr    (up to 20 expansion rooms)

  - The chosen name is 3-32 characters and is not on the
    reserved canonical-locations list (e.g. "Mos Eisley",
    "Theed", "Coruscant" — canon names are out of bounds for
    player cities by design §1).

If validation passes, the founding cost is debited from the
treasury, the city row is inserted, and the HQ's rooms become
the city's initial footprint.

FOUNDER vs MAYOR

The **Founder** is the org leader who declared the city.
Founder is **immutable** for the city's lifetime — the database
column is set once and never updated. The Founder retains a few
exclusive rights:

  - Reassign the Mayor (`+city mayor <player>`)
  - Set the tax-rate cap (`+city tax ratecap <pct>`)
  - Voluntarily dissolve the city (`+city dissolve <name>`)
  - All Mayor powers (Founder is always also a Mayor-tier actor)

The **Mayor** is the day-to-day governor. The Founder may
appoint any org member. Mayor powers:

  - Set the city motto (`+city motd <text>`, 240 char max)
  - Set the tax rate within the Founder cap (0-10% ceiling)
  - Manage citizen-only room flags
  - Manage guests (add/remove)
  - Banish and unbanish players (30-day default)

EXPANSION

`+city claim <direction>` or `+city claim <room_id>` adds an
adjacent room to the city. Each claim:

  - Debits 5,000 cr from the org treasury
  - Requires 50+ zone influence (same threshold as founding)
  - Is rate-limited to one claim per 24 hours per city
  - Counts against the HQ subtype's room cap (see above)

`+city release [room_id]` returns a room to the wilderness and
refunds 50% of the claim cost. The HQ room itself cannot be
released — to lose the HQ, dissolve the city.

GOVERNANCE — CITIZENS, GUESTS, BANISHMENT

A city's **citizens** are members of the founding org. They get
the standard set of citizen privileges (entry to citizen-only
rooms, use of +city/home). The Mayor cannot grant or revoke
citizen status — that's controlled by org membership.

**Guests** are non-citizen characters granted explicit access by
the Mayor or Founder. Useful for allied org members, visiting
diplomats, or trusted contractors. Guest status persists until
removed; it is not automatically expired.

**Banishment** locks a player out of all city rooms for 30 days
(the default; admin can void early via `@city void-banish`). A
banished player attempting to enter a city room gets the
banishment notice and is bounced to the adjacent room. Used
for griefers, ex-allies, and rival faction infiltrators.

CITIZEN-ONLY ROOMS

`+city citizenroom on` flags the current room as citizen-only —
only members of the founding org and registered guests can
enter. Used for treasury rooms, council chambers, members-only
watering holes, etc. Multiple rooms in a city can be flagged.

TAXATION

`+city tax set <pct>` sets a surcharge on commerce performed
inside the city's rooms — purchases at NPC vendors, shopfront
sales by players, training fees. The collected credits flow
into the org treasury. Two tracking values are visible in
`+city tax view`:

  - **revenue_week** — credits collected since the last weekly
    rollover tick (`server.tick_handlers_economy.city_revenue_rollover_tick`)
  - **revenue_total** — cumulative collection for the city's
    lifetime

The Mayor sets the rate within the Founder's cap. The absolute
ceiling is **10%** regardless of cap setting; the engine refuses
higher values.

MAINTENANCE & GRACE PERIOD

Every week, the city tick debits maintenance from the org
treasury:

  - **HQ base** — already paid by `engine.housing`'s HQ
    maintenance tick (500 / 1,000 / 1,500 cr/wk for outpost /
    chapter house / fortress). The city tick does **not**
    re-charge this; it would double-tax.
  - **Expansion rooms** — 100 cr per non-HQ city room per week.
  - **NPC guards (Phase 7)** — 200 cr per guard per week.

If the treasury covers the bill, the tick debits, advances
`maint_paid_until` by a week, and the city stays healthy.

If the treasury is **short**, the city enters a four-week
**grace period**. The state machine, by week of grace:

  WEEK 1   Guards stop functioning (Phase 7 only). Otherwise
           the city operates normally. Mayor + Founder get mail.

  WEEK 2   Citizen-only flags are **bulk-cleared**. The Mayor
           cannot apply new flags (the gate refuses with a
           recovery hint). Existing flags are gone — refilling
           the treasury later does NOT restore them; the Mayor
           must reapply them by hand once the city recovers.

  WEEK 3   Tax collection **ceases**. The rate stays settable
           (so the Mayor can prepare for recovery), but no
           credits flow until the city is healthy again.

  WEEK 4   Final warning mail. City still functional but the
           clock is at one tick to dissolve.

  EXPIRED  At the start of week 5 (t = 28 days since grace
           began), the city is **auto-dissolved**. Cascade
           cleanup runs (rooms released, banishments cleared,
           guests cleared), `state` is set to `dissolved`, mail
           goes to Mayor + Founder. The `player_cities` row is
           kept for audit. **No refund** — the treasury was
           empty by definition.

**Recovery** is simple: refill the org treasury. On the next
maintenance tick, if treasury covers the bill, the city pays,
the grace timestamp is cleared, and a "restored" mail goes out.
Recovery is allowed at any point before auto-dissolve — even
week 4 can be saved. **However:** week-2 citizen-only flag
clearing is permanent; recovery doesn't reapply them.

The state machine is fail-safe by design: even an unexpected
mail-system failure cannot block a state transition (the mail
helper is wrapped in best-effort error handling).

DISSOLUTION

There are three paths to dissolved state:

  1. **Voluntary** (`+city dissolve <name>`, Founder only).
     Refunds 50% of the founding cost to the treasury. The
     graceful exit.
  2. **Admin force** (`@city dissolve <name>`). No refund. The
     moderation path — typically used for policy violations or
     long-abandoned cities.
  3. **Maintenance expiry** (auto, end of grace week 4). No
     refund. The natural-causes path.

All three cascade-clean identically: city_rooms rows pruned,
banishments and guests cleared, citizen-only flags dropped.
The `player_cities` row stays in the table for audit, with
`state = 'dissolved'`.

INVARIANTS (developer notes)

These are the load-bearing rules other systems depend on:

  - **Founder is immutable.** Code never updates `founder_id`.
  - **Grace state is derived from `grace_started_at`.** No
    separate state column was added; the existing
    `state ∈ {active, dissolved}` enum is unchanged. Phase 6
    Helpers (`is_in_grace`, `grace_stage`, etc.) read
    `grace_started_at` directly.
  - **HQ base maintenance lives in `engine.housing`.** The
    city tick does not re-charge it.
  - **`maint_paid_until` is the tick-idempotence anchor.** Both
    the "paid" path and the "in grace" path bump it by a week,
    so the tick is safe to run twice in the same week.
  - **Tax collection is gated at the call site, not the
    rate-setter.** The rate stays settable in grace so the
    Mayor can prepare for recovery; the actual collection
    short-circuits when the city is in week 3+.
  - **Citizen-flag setting is gated at the setter, not the
    reader.** Once set, the flag is read normally; setting new
    ones is refused in week 2+. Clearing is always allowed.

ADMIN OVERSIGHT

The `@city` admin verb gives staff the moderation surface:

  - `@city list` — every active city across all planets
  - `@city inspect <name>` — full state dump for one city
  - `@city void-banish <city> = <player>` — lift a banishment
  - `@city set-rate-cap <city> = <pct>` — override the cap
  - `@city dissolve <name>` — force-dissolve (no refund)
  - `@city rename <old> = <new>` — rename

See `+help @city` for the admin command reference.

CHEAT SHEET (PLAYER)

  +city found <name>      = found a city (org leader)
  +city info              = current city details
  +city map               = ASCII map
  +city citizens          = members + guests
  +city motd <text>       = set MOTD (Mayor/Founder)
  +city tax view          = revenue + rate
  +city tax set <pct>     = set rate (Mayor/Founder, ≤ cap, ≤ 10%)
  +city home              = citizen teleport home (1h cd)
  +city dissolve <name>   = voluntary dissolve (50% refund)

Sources: Player Cities system per design v1.2 (founding,
expansion, governance, taxation, maintenance + grace state
machine). For the command-level reference, see `+help +city`
(player) and `+help @city` (admin). Related systems:
`+help housing`, `+help +home`, `+help territory`,
`+help factions`, `+help economy`.
