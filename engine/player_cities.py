"""
engine/player_cities.py — Player Cities (Phases 1 + 2 + 3 + 4 + 4b + 5)

Phase 1 deliverable per ``player_cities_design_v1_2.md`` §13:
  - Schema (4 tables, idempotent ensure_schema)
  - found_city() — validates prereqs, debits treasury, anchors HQ
    rooms as the City Center
  - dissolve_city() — refunds half the founding cost, removes
    city_rooms rows, marks state='dissolved'
  - validate_city_name() — name moderation (length, charset,
    reserved-list)

Phase 2 deliverable per design §13:
  - claim_room_for_city() — contiguous-expansion claim with
    same-zone, size-cap, influence, treasury, and 24h-rate-limit
    enforcement
  - release_room_from_city() — refund half the claim cost, drop
    the row, but do not touch HQ rooms (is_center=1)
  - Helpers for expansion-count and last-expansion-time reads

Phase 3 deliverable per design §13:
  - Role resolution: get_city_role() — founder | mayor | citizen |
    guest | outsider | banished, derived from org membership +
    banishment/guest tables. Single read used by look + Phase 4
    tax + Phase 5 citizen benefits.
  - Founder-only commands: assign_mayor() — promote an org member
    to Mayor (only the org leader at founding can reassign).
  - Mayor commands: set_city_motd(), banish_player(),
    unbanish_player(), add_guest(), remove_guest(),
    set_room_citizen_only().
  - Look output: format_city_header_tag() — bracket tag for the
    LookCommand chain, citizen-aware (SECURED upgrade) and
    banishment-aware (warning line surface).
  - List / info: list_active_cities(), format_city_info().

Phase 4 deliverable per design §13:
  - Mayor commands: set_city_tax_rate() — set rate within rate_cap
    (0-10% absolute max).
  - Founder commands: set_city_rate_cap() — set the rate-cap that
    bounds Mayor's tax-set authority (max 10% per design §4.3).
  - apply_city_tax(db, room_id, gross_amount) — SINGLE chokepoint
    for collection. Returns (city_take, city_id, city_name); also
    debits the city's cut into the org treasury and tags it in
    player_cities.revenue_total + revenue_week.
  - Two Phase 4 collection sites:
        * Vendor droid sales (engine/vendor_droids.py::buy_from_droid)
        * Bounty postings   (parser/pc_bounty_commands._handle_post,
                              _do_stack)
  - tick_city_revenue_rollover() — weekly: zeroes revenue_week and
    advances week_start_ts. Wired into server.tick_handlers_economy
    as city_revenue_rollover_tick at interval=86400 (daily check;
    per-city week boundaries roll at most ~1 day late).
  - format_city_tax_view() — multi-line render for +city tax view.

Phase 4b deliverable per design §13:
  - Five additional collection sites wired with the same
    apply_city_tax chokepoint (no engine changes):
        * Sabacc rake               (parser/sabacc_commands.py)
        * In-room weapon sell to NPC (parser/builtin_commands.py
                                       ::SellCommand)
        * In-room weapon buy from NPC (parser/space_commands.py
                                        ::BuyCommand)
        * Dock cargo-sell at planet market
          (parser/builtin_commands.py::_handle_sell_cargo)
        * Dock cargo-buy at planet market
          (parser/space_commands.py::_handle_buy_cargo)
  - Customs-fine bargaining (parser/space_commands.py
    ::_run_customs_check) is deliberately SKIPPED. State-imposed
    penalty, not commerce; design §5.1 only enumerates commerce
    surfaces; design §5.2 affirms that government/state actions
    are not taxable.

Phase 5 deliverable per design §13 (this drop) — Citizen benefits:
  - Read seams:
        * is_citizen(db, char, city)   — convenience wrapper around
                                          get_city_role (Phase 3).
        * is_rest_bonus_room(db, char, room_id)
                                       — §6.1 seam for the (not-yet-
                                          shipped) rest bonus
                                          mechanic. Returns True iff
                                          char is a citizen and the
                                          room is in their city.
  - Movement gating:
        * can_enter_city_room(db, char, room_id)
                                       — §6.3 gate. Returns
                                          (False, reason) for non-
                                          citizens (incl. guests)
                                          attempting citizen_only
                                          rooms. Wired into
                                          MoveCommand's
                                          _check_exit_gates chain.
  - Security upgrade (engine/security.py::_apply_city_upgrade):
        * §6.2: contested → SECURED for citizens; lawless →
          CONTESTED for citizens. Appended to the _finalize chain
          AFTER faction-override and claim-upgrade so the city
          upgrade is the most-permissive last word for citizens
          inside their own city.
  - +city home teleport:
        * can_use_city_home(db, char) → (ok, dest_room_id, reason)
                                       — §6.4 gate: citizen-only,
                                          same-zone, not in combat,
                                          not in space, cooldown
                                          honored.
        * record_city_home_use(db, char_id)
                                       — sets last_city_home in
                                          attributes JSON for
                                          cooldown tracking.
  - 30%-cap enforcement on set_room_citizen_only when flag=True
    (Phase 3 shipped the flag write but deferred the cap; HQ
    rooms are citizen-only by default per design §6.3 and don't
    count against the 30%).

Phase 1+2+3+4+4b+5 deliberately does NOT include:
  - NPC guard assignment/scaling       — Phase 6/7
  - Wilderness / hidden city variants  — Phase 7+
  - The rest-bonus MECHANIC itself     — separate system feature;
                                          Phase 5 only ships the
                                          read seam (is_rest_bonus_room).

────────────────────────────────────────────────────────────────────
Schema design vs the v1.2 design doc — locked design calls

  May 22 2026 design call #1 (Brian): "Hard-block + data drop" —
    only zones whose ``properties.security`` is explicitly
    'contested' or 'lawless' qualify for city founding. The
    fallback-to-'contested' behavior of
    engine.territory.get_zone_security is bypassed here by
    reading the zone row directly. The 19 previously-unknown CW
    zones are addressed in the same drop via a zones.yaml edit.

  May 22 2026 design call #2 (Brian): "Keep design-doc numbers"
    FOUNDING_COSTS = 25K outpost / 75K chapter_house / 200K
    fortress, justified separately from the tier-5 HQ purchase
    cost (which is 50K/100K/150K per engine.housing.TIER5_TYPES).
    Rationale: founding cost is the *city sink*, distinct from
    the HQ-building purchase. Sink magnitudes track the design.

  HEAD reality: the v1.2 design doc references an ``org_hqs``
  table that never existed at HEAD. tier-5 HQs live as rows in
  ``player_housing`` with ``housing_type='org_hq'``. The
  player_cities.hq_id FK therefore references player_housing(id).

  HEAD reality: HQ subtype (outpost / chapter_house / fortress)
  is NOT persisted as a named field by purchase_hq. It is
  reconstructible from storage_max (100/200/400) per
  engine.housing.TIER5_TYPES. _infer_hq_type() handles this.

  HEAD reality: ``zone_id`` is INTEGER on rooms but TEXT on
  the legacy ``zone_influence`` table. The active influence
  read for Player Cities goes through
  engine.territory.get_territory_influence which uses INTEGER
  zone_id against the newer ``territory_influence`` table.
  No type juggling required.

  Phase 2 May 22 2026 design call (Brian via Claude proposal):
    Expansion rooms tracked in ``player_city_rooms`` only, NOT
    in ``territory_claims``. Drop 6's CLAIM_MAX_PER_ZONE = 3
    hard-blocks the design's 5/10/20-room per-tier expansion;
    cities are the explicit governed-cluster exception. We
    replicate the cost (5,000 cr) and the influence threshold
    (50, == THRESHOLD_FOOTHOLD) but do not write to
    territory_claims. Tradeoff: city expansion rooms do not
    appear in ``+territory list``. Resolved on the city-side
    by ``+city info`` (Phase 3) listing expansion rooms.

  Phase 3 May 22 2026 design call (Brian via Claude proposal):
    Banishment anti-griefing rule per design §4.4 — "Cannot
    banish org leadership of rival orgs without admin approval"
    — implemented as a hard-block in banish_player(): if the
    target is rank_level >= MIN_RANK_LEVEL_TO_FOUND (= 5) in
    ANY org other than the city's owning org, the command is
    rejected with an actionable error. Admin override is the
    Phase 6 ``@city void-banish`` admin command (not in this
    drop). This is stricter than the design wording ("rival
    orgs") because we don't model rivalries; the implementable
    invariant is "the leadership of any org other than this
    one." If two orgs hold reciprocal banishments under this
    rule, both leaders are blocked, which matches the design's
    safety stance.

  Phase 3 May 22 2026 design call (Brian via Claude proposal):
    `+city guards` is implemented as a view-only stub that lists
    NPC guards already stationed in city rooms (none in Phase 3,
    so always empty). The guard-assignment surface (`+city
    guards assign <npc>` / `remove <npc>`) is deferred to
    Phase 6/7 with the guard-scaling-by-influence system per
    design §7. Phase 3 ships the read so the public command
    surface advertises correctly; the write hooks land later.

  Phase 4 May 22 2026 design call (Brian via Claude proposal):
    Tax is carved out of EXISTING sinks, not added as new debit
    on top of the player's transaction. Design §5.3's flow is:
    "[City tax e.g. 5%] = 50 cr deducted from vendor's net."
    Implementation honors this literally — for vendor droid
    sales, the city's cut comes from the droid's net_payout
    (which currently goes to escrow); the buyer pays the same
    final_price they would without the tax. For bounty
    postings, the city's cut comes from the posting fee
    (currently a sunk cost that disappears); the poster pays
    the same total_debit. This is the design-locked model:
    cities tax the SYSTEM's slice, not the player's slice.

  Phase 4 May 22 2026 design call #2 (Brian via Claude proposal):
    Sabacc rake and NPC vendor bargaining are deferred to a
    Phase 4b drop. Three reasons:
      1. Sabacc rake site is single but in a different parser
         flow with its own commit pattern — clean drop, but
         best done with its own focused testing.
      2. NPC vendor bargaining is scattered across at least 4
         sites (parser/builtin_commands.py SellCommand,
         parser/builtin_commands.py BuyCommand,
         parser/space_commands.py 2 sites). Each is the
         current point of credit transfer and would each
         need its own atomic apply_city_tax wiring.
      3. The chokepoint design (apply_city_tax returns
         (take, city_id, name) for any room_id) is deliberately
         shaped so these sites can be wired in with 1-2 lines
         each. Phase 4b is a wiring drop, not a design drop.
    Phase 4 ships the engine machinery + 2 highest-ROI sites;
    Phase 4b adds the remaining 4 sites with the same API.

  Phase 4b May 22 2026 design call (Brian via Claude proposal):
    Five sites wired (not four — the Phase 4 handoff undercounted
    by one). The fifth is dock cargo-sell at planet markets, which
    is structurally a player-vs-NPC commerce site identical to the
    cargo-buy form. Both should tax for consistency. Customs-fine
    bargaining (parser/space_commands.py::_run_customs_check ~line
    5079) was identified during the Phase 4b site scan and is
    explicitly NOT wired — a customs fine is a state penalty, not
    commerce. Design §5.1 enumerates taxable surfaces and §5.2
    affirms state actions are exempt; the spirit of "tax commerce,
    not government action" governs. If a future drop changes this
    (e.g., to allow city-aligned customs offices), it would need a
    fresh design discussion.

  Phase 4b May 22 2026 design call #2 (Brian via Claude proposal):
    NPC vendor sites use the "tax from thin air" pattern. The
    NPC vendor system doesn't have a wallet to debit; the player's
    payment/receipt is unchanged. The city revenue is credited
    directly into the org treasury + revenue trackers, funded by
    the NPC vendor system itself. This is the cleanest realization
    of the Phase 4 design call ("cities tax the SYSTEM's slice,
    not the player's slice") when the system has no other player
    on the other side of the transaction. Vendor droid (Phase 4)
    differs because the droid IS owned by another player whose
    escrow gets reduced; that other player is "the system's
    slice." For NPC vendor sites, there's no such player, so the
    cost is borne by the system itself.

  Phase 4b May 22 2026 discovery (Brian via Claude proposal):
    During Phase 4b wiring, the cargo-buy success-message echo at
    parser/space_commands.py::_handle_buy_cargo was found to
    reference `get_cargo_tons` without importing it — a pre-
    existing NameError that would have crashed every successful
    cargo-buy. Fixed in this drop by adding `get_cargo_tons` to
    the trading imports. Logged here so a future maintainer
    sees that the import-fix was in scope of Phase 4b and not
    a Phase 4b-introduced bug. (Verified pristine pre-Phase-4b
    code reproduces the same crash.)

  Phase 5 May 22 2026 design call (Brian via Claude proposal):
    "Same planet" for +city home is implemented as "same zone." The
    design (§6.4) says the teleport is planet-scoped, but zones in
    data/worlds/clone_wars/zones.yaml don't carry an explicit
    `planet` attribute — planet is currently a soft concept inferred
    via engine.trading and the Director. Phase 5 ships the
    implementable invariant: same zone_id. This is STRICTER than the
    design (only same-zone counts, not other-zone-on-same-planet),
    but is loose enough for actual Clone Wars zones today since
    cities are zone-anchored and most actionable destinations are in
    the same zone. If a future drop adds a zone→planet attribute,
    can_use_city_home can be updated to honor the looser planet
    check in 2-3 lines.

  Phase 5 May 22 2026 design call #2 (Brian via Claude proposal):
    The 30%-cap on citizen_only rooms (design §6.3) counts only
    expansion rooms. HQ rooms (is_center=1) are citizen-only by
    default per the design wording ("The City Center HQ rooms
    count as citizen-only by default and don't reduce the
    available 30%"). Implementation: when set_room_citizen_only
    flag=True is requested on a non-HQ room, count current
    non-HQ citizen_only rooms vs total non-HQ rooms; reject if
    adding this one would exceed 30% (rounded to the nearest
    whole room, with at least 1 always allowed so brand-new
    cities aren't blocked on rounding). HQ rooms are not
    counted; non-HQ counts are.

  Phase 5 May 22 2026 design call #3 (Brian via Claude proposal):
    +city home cooldown survives logout. Stored in
    characters.attributes JSON as `last_city_home` (epoch
    seconds), parallel to the Phase 3 banishment mechanic and
    the existing `last_sabacc` cooldown. This survives reboots
    and is durable across sessions, matching the design's
    "1-hour cooldown" intent (otherwise a player could log out
    and back in to dodge it).

  Phase 5 May 22 2026 design call #4 (Brian via Claude proposal):
    Rest bonus MECHANIC itself is not shipped — only the
    is_rest_bonus_room() read seam. The current engine has no
    rest-bonus mechanic at any consumer site (verified by
    grepping engine/, parser/, server/ for REST_BONUS,
    rest_bonus, home_logout — all empty). Adding the mechanic
    would be an unrelated system feature. Phase 5 ships the
    cities-side answer so the future mechanic gets city support
    for free.

────────────────────────────────────────────────────────────────────
Architecture invariants enforced here (per design v1.2 §15):

  - A room belongs to at most one (active) city. Enforced at
    INSERT INTO player_city_rooms time by the (city_id, room_id)
    PRIMARY KEY combined with the get_city_for_room read path.
  - City Center rooms (HQ rooms) cannot be released individually
    — only the entire city dissolves. Phase 1 has no `release`
    command, so trivially true.
  - Founder is immutable for the city's lifetime. founder_id is
    set on INSERT and never UPDATEd.
  - All city state transitions through dissolve_city (the only
    Phase 1 transition); Phases 2-6 will add expansion / banish /
    grace / dissolved transitions through their own choke points.

Phase 1 leaves these invariants for later phases to enforce:
  - 24-hour expansion rate-limit (Phase 2)
  - Tax collection through a single apply_city_tax (Phase 4)
  - +city home cooldown sharing (Phase 5)

See ``player_cities_design_v1_2.md`` for the full specification.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

# Per design v1.2 §2.3 + May 22 design call #2: founding cost is the
# city declaration sink, separate from the HQ purchase cost.
FOUNDING_COSTS: dict[str, int] = {
    "outpost":       25_000,
    "chapter_house": 75_000,
    "fortress":      200_000,
}

# Per design v1.2 §2.3: max expansion-room count per HQ tier. Phase 1
# reads this constant but does not enforce it (no expansion shipped);
# Phase 2 will use it in +city claim.
MAX_EXPANSION_ROOMS: dict[str, int] = {
    "outpost":       5,
    "chapter_house": 10,
    "fortress":      20,
}

# Refund on dissolution — 50% of founding cost per design §5
# ("Treasury depletion → dissolved" path implies the city's
# invested resources have to come back somewhere; 50% is a
# reasonable sink-honest number that doesn't make founding free).
DISSOLUTION_REFUND_PCT = 50

# Per design v1.2 §2.1: 50 influence threshold (matches single-room
# claim threshold from Drop 6 territory).
MIN_INFLUENCE_TO_FOUND = 50

# Per design v1.2 §2.1: only the org leader (rank 5+) can found a
# city; mayor delegation is post-founding.
MIN_RANK_LEVEL_TO_FOUND = 5

# Per May 22 design call #1: hard-block eligibility. Only declared
# contested/lawless zones qualify.
ELIGIBLE_SECURITY: frozenset[str] = frozenset({"contested", "lawless"})

# Name validation
NAME_MIN_LEN = 3
NAME_MAX_LEN = 32

# Reserved canonical Star Wars location names — cannot be used as
# player city names (admin moderation per design §1).
RESERVED_CITY_NAMES: frozenset[str] = frozenset({
    "mos eisley", "mos espa", "mos entha", "anchorhead", "bestine",
    "theed", "naboo", "coruscant", "kamino", "tipoca city",
    "galactic city", "kuat", "corellia", "mandalore", "sundari",
    "kashyyyk", "kachirho", "nar shaddaa", "nal hutta", "mygeeto",
    "geonosis", "utapau", "cato neimoidia", "felucia", "saleucami",
    "mustafar", "ryloth", "jedi temple", "senate building",
})

# HQ storage_max → subtype lookup. engine.housing.TIER5_TYPES sets
# storage_max to 100/200/400 for outpost/chapter_house/fortress; we
# reverse-lookup at use time since purchase_hq doesn't persist the
# named subtype.
_STORAGE_TO_HQ_TYPE: dict[int, str] = {
    100: "outpost",
    200: "chapter_house",
    400: "fortress",
}


# ── Phase 2: expansion constants ──────────────────────────────────────────────

# Per design v1.2 §3.1: "Costs the standard territory-claim treasury
# debit (per Drop 6: 5,000 cr per room)." Mirrors
# engine.territory.CLAIM_COST. We replicate the value rather than
# importing it to keep the city subsystem self-contained — if Drop 6
# changes its cost in the future, the city subsystem requires an
# explicit design call to follow.
EXPANSION_CLAIM_COST = 5_000

# Per design v1.2 §3.1: "Requires sufficient influence (per Drop 6:
# each new claim consumes a portion of zone influence)." Drop 6's
# THRESHOLD_FOOTHOLD = 50 — same threshold as founding (§2.1).
EXPANSION_INFLUENCE_THRESHOLD = 50

# Per design v1.2 §3.2: "Refunds 50% of the claim cost to the
# treasury (matches housing sell-back rate)."
EXPANSION_REFUND_PCT = 50

# Per design v1.2 §3.3: "max 1 new claim per 24 hours per city."
EXPANSION_RATE_LIMIT_SECONDS = 24 * 60 * 60


# ── Phase 3: governance constants ─────────────────────────────────────────────

# Per design v1.2 §4.4: "Banishment lasts 30 days by default."
BANISHMENT_DEFAULT_SECONDS = 30 * 24 * 60 * 60

# Per design v1.2 §4.2: tax-rate Mayor-settable range. The cap is
# Founder-settable up to MAX_TAX_RATE. Phase 4 will enforce these on
# +city tax set; Phase 3 ships the constants since +city info renders
# the rate cap in its info view.
MAX_TAX_RATE = 0.10        # 10% absolute ceiling per §5.4
DEFAULT_RATE_CAP = 0.10    # founder default rate-cap
MIN_TAX_RATE = 0.0         # 0% floor per §5.4 (no city pays the city)

# Per design v1.2 §5: weekly revenue tracking. revenue_week resets
# on the rollover tick (server.tick_handlers_economy.city_revenue_rollover_tick)
# every CITY_REVENUE_ROLLOVER_SECONDS. revenue_total is cumulative.
CITY_REVENUE_ROLLOVER_SECONDS = 7 * 24 * 60 * 60

# Per design v1.2 §4.2: motd character ceiling (rendered on every
# city-room entry, so must be terse).
MOTD_MAX_LEN = 240

# Per design v1.2 §11.1 (+city list): list paging. Phase 3 returns a
# capped list; long lists overflow to "and N more" lines.
CITY_LIST_PAGE_SIZE = 25


# ── Phase 6 maintenance constants (May 23 2026) ─────────────────────────────
#
# Per design v1.2 §8.1 (maintenance costs) and §8.2 (treasury
# depletion behavior / 4-week grace state machine).
#
# Storage trick: the schema's existing `grace_started_at REAL DEFAULT 0`
# column (provisioned in Phase 1, never written until Phase 6) is the
# single source of truth for grace state.
#   - grace_started_at == 0  → city is healthy (active, paying)
#   - grace_started_at != 0  → city is in grace; current week is
#     derived from (now - grace_started_at) / 86400 / 7
#
# This avoids adding a Phase-6-specific state column; the existing
# `state` enum stays {active, dissolved}.

# Per design §8.1: cost components other than HQ base maintenance.
# HQ base (500/1000/1500) is already paid by engine.housing's
# tick_hq_maintenance — don't double-charge.
CITY_EXPANSION_MAINT_PER_WEEK_CR = 100   # per expansion (non-HQ) room
CITY_GUARD_MAINT_PER_WEEK_CR = 200       # per NPC guard (Phase 7; constant
                                          # provided now for Phase 7's drop)

# Per design §8.2: 4-week grace period. Stage thresholds are
# elapsed-seconds-since-grace-started:
#   t = 0       → week 1: guards stop functioning (Phase 7 only)
#   t = 7d      → week 2: citizen-only flags cleared; mayor can't
#                 apply new ones
#   t = 14d     → week 3: tax collection ceases
#   t = 21d     → week 4: still functioning but final warning
#   t = 28d     → end of week 4: auto-dissolve
ONE_WEEK_SECONDS = 7 * 24 * 60 * 60
CITY_GRACE_FLAGS_OFF_AT_SECONDS = 1 * ONE_WEEK_SECONDS
CITY_GRACE_TAX_OFF_AT_SECONDS = 2 * ONE_WEEK_SECONDS
CITY_GRACE_FINAL_WARNING_AT_SECONDS = 3 * ONE_WEEK_SECONDS
CITY_GRACE_DISSOLVE_AT_SECONDS = 4 * ONE_WEEK_SECONDS

# Tick cadence for the maintenance tick. Weekly per design §8.1.
# The tick is *idempotent* per-city: the per-city check uses the
# org treasury at tick-time, not a stored "last-paid" timestamp,
# so running the tick twice in one week without an interceding
# week boundary is safe (the second call sees a depleted treasury
# only if the first call already collected).
#
# We avoid that double-charge by stamping a `last_maint_ts` value
# into the city's existing JSON-friendly column. We don't have one
# at HEAD that's appropriate, so we use the `motd` field? No —
# motd is player-facing.
#
# Decision: add a `maint_paid_until` REAL column via subsystem
# bootstrap (ensure_schema migration). The column starts at
# founded_at + ONE_WEEK_SECONDS for new cities; existing rows
# get a default of now (so they get a full week of grace before
# first maintenance debit).
CITY_MAINTENANCE_TICK_INTERVAL_SECONDS = ONE_WEEK_SECONDS


# ── Schema ────────────────────────────────────────────────────────────────────

# All schema declared here; mirrors engine.housing.HOUSING_SCHEMA_SQL
# convention. The migration runner in db.database.MIGRATIONS is NOT
# touched — subsystem owns its own idempotent bootstrap, called from
# server boot. This avoids two competing sources of truth for what
# tables exist on disk.

PLAYER_CITIES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS player_cities (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL,
    name_lower            TEXT NOT NULL,
    org_id                INTEGER NOT NULL,
    hq_id                 INTEGER NOT NULL,
    zone_id               INTEGER,
    is_wilderness         INTEGER NOT NULL DEFAULT 0,
    wilderness_region_id  TEXT,
    wilderness_x          INTEGER,
    wilderness_y          INTEGER,
    is_hidden             INTEGER NOT NULL DEFAULT 0,
    search_difficulty     INTEGER DEFAULT 20,
    visibility_factions   TEXT DEFAULT '[]',
    founded_at            REAL NOT NULL,
    founder_id            INTEGER NOT NULL,
    mayor_id              INTEGER NOT NULL,
    tax_rate              REAL NOT NULL DEFAULT 0.0,
    rate_cap              REAL NOT NULL DEFAULT 0.10,
    motd                  TEXT DEFAULT '',
    state                 TEXT NOT NULL DEFAULT 'active',
    grace_started_at      REAL DEFAULT 0,
    revenue_total         INTEGER DEFAULT 0,
    revenue_week          INTEGER DEFAULT 0,
    week_start_ts         REAL NOT NULL,
    hq_tier               TEXT NOT NULL DEFAULT 'outpost',
    FOREIGN KEY (org_id)    REFERENCES organizations(id),
    FOREIGN KEY (hq_id)     REFERENCES player_housing(id),
    FOREIGN KEY (founder_id) REFERENCES characters(id),
    FOREIGN KEY (mayor_id)   REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS player_city_rooms (
    city_id      INTEGER NOT NULL,
    room_id      INTEGER NOT NULL,
    is_center    INTEGER NOT NULL DEFAULT 0,
    citizen_only INTEGER NOT NULL DEFAULT 0,
    claimed_at   REAL NOT NULL,
    PRIMARY KEY (city_id, room_id),
    FOREIGN KEY (city_id) REFERENCES player_cities(id)
);

CREATE TABLE IF NOT EXISTS player_city_banishments (
    city_id   INTEGER NOT NULL,
    char_id   INTEGER NOT NULL,
    until     REAL NOT NULL,
    issued_by INTEGER NOT NULL,
    issued_at REAL NOT NULL,
    PRIMARY KEY (city_id, char_id)
);

CREATE TABLE IF NOT EXISTS player_city_guests (
    city_id   INTEGER NOT NULL,
    char_id   INTEGER NOT NULL,
    added_by  INTEGER NOT NULL,
    added_at  REAL NOT NULL,
    PRIMARY KEY (city_id, char_id)
);

CREATE TABLE IF NOT EXISTS player_city_guards (
    city_id     INTEGER NOT NULL,
    npc_id      INTEGER NOT NULL,
    room_id     INTEGER NOT NULL,
    assigned_by INTEGER NOT NULL,
    assigned_at REAL NOT NULL,
    PRIMARY KEY (city_id, npc_id),
    FOREIGN KEY (city_id) REFERENCES player_cities(id)
);
"""

# Indexes are separate from CREATE TABLE so they can be added
# incrementally if (e.g.) Phase 2 needs a new index.
#
# The idx_city_name_active partial-unique index enforces "one active
# city per name" without blocking dissolved rows (which the design
# §17 keeps for audit). A row INSERT with the same name_lower as an
# existing active row will fail; reuse of a dissolved city's name
# succeeds because the partial index does not cover dissolved rows.
# SQLite has supported partial indexes since 3.8.0 (2013).
PLAYER_CITIES_INDEXES_SQL: list[str] = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_city_name_active "
    "ON player_cities(name_lower) WHERE state != 'dissolved'",
    "CREATE INDEX IF NOT EXISTS idx_city_rooms_room "
    "ON player_city_rooms(room_id)",
    "CREATE INDEX IF NOT EXISTS idx_city_org "
    "ON player_cities(org_id)",
    "CREATE INDEX IF NOT EXISTS idx_city_zone "
    "ON player_cities(zone_id)",
    "CREATE INDEX IF NOT EXISTS idx_city_wilderness "
    "ON player_cities(wilderness_region_id, wilderness_x, wilderness_y)",
    "CREATE INDEX IF NOT EXISTS idx_city_state "
    "ON player_cities(state)",
    # Phase 7: city guards lookup-by-city and lookup-by-room.
    "CREATE INDEX IF NOT EXISTS idx_city_guards_city "
    "ON player_city_guards(city_id)",
    "CREATE INDEX IF NOT EXISTS idx_city_guards_room "
    "ON player_city_guards(room_id)",
]


async def ensure_schema(db) -> None:
    """Create Player Cities tables + indexes if absent. Idempotent.

    Mirrors the engine.housing.ensure_schema convention. Called from
    server.game_server's boot path after housing + territory init.

    Phase 6 May 23 2026: additive ALTER for the new
    `maint_paid_until` column (REAL, default 0). This is the
    "last-paid timestamp + one week" anchor — a city is due for
    maintenance when `now >= maint_paid_until`. ALTER TABLE wrapped
    in try/except for idempotence (SQLite doesn't support
    IF NOT EXISTS on ADD COLUMN until 3.35; we support older).
    """
    try:
        for stmt in PLAYER_CITIES_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        for idx_sql in PLAYER_CITIES_INDEXES_SQL:
            try:
                await db.execute(idx_sql)
            except Exception:
                pass  # Index already exists
        # Phase 6 additive column: maint_paid_until.
        try:
            await db.execute(
                "ALTER TABLE player_cities "
                "ADD COLUMN maint_paid_until REAL NOT NULL DEFAULT 0"
            )
            # Backfill for existing rows: set to founded_at +
            # ONE_WEEK_SECONDS so legacy cities get a full week
            # before the first maintenance debit hits them.
            await db.execute(
                "UPDATE player_cities "
                "SET maint_paid_until = founded_at + ? "
                "WHERE maint_paid_until = 0",
                (ONE_WEEK_SECONDS,),
            )
        except Exception:
            # Column already exists (re-bootstrap on existing DB)
            pass
        # SYN.4 additive columns: vitality_state, vitality_below_since.
        # Per contestable_wilderness_design_v2.md §2.9.4 (SWG-lesson
        # vitality mechanic). `vitality_state` is 'active' | 'reduced'
        # | 'dormant'; `vitality_below_since` is the unix timestamp at
        # which active-citizen count first dropped below the HQ-tier
        # threshold (NULL when at/above threshold). The 14-day dormancy
        # window is gated on this timestamp.
        try:
            await db.execute(
                "ALTER TABLE player_cities "
                "ADD COLUMN vitality_state TEXT NOT NULL DEFAULT 'active'"
            )
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE player_cities "
                "ADD COLUMN vitality_below_since REAL DEFAULT NULL"
            )
        except Exception:
            pass  # Column already exists
        await db.commit()
    except Exception as e:
        log.warning("[player_cities] schema create error: %s", e)


# ── Read helpers ──────────────────────────────────────────────────────────────

async def get_city_by_name(db, name: str) -> Optional[dict]:
    """Look up an active city by case-insensitive name. None if absent.

    Dissolved cities are excluded from this read path; the rows
    remain in the table for audit history.
    """
    rows = await db.fetchall(
        "SELECT * FROM player_cities "
        "WHERE name_lower = ? AND state != 'dissolved'",
        (name.strip().lower(),),
    )
    return dict(rows[0]) if rows else None


async def get_city_by_id(db, city_id: int) -> Optional[dict]:
    """Look up a city by primary key, or None if absent.

    UNLIKE `get_city_by_name` / `get_city_by_org`, this read path
    does NOT filter out dissolved cities. The dissolved row stays
    in the table for audit history, and several callers need to
    inspect the dissolved record (e.g. Phase 7c city-guard rules
    must distinguish "no such city" from "city dissolved" so the
    guard fails safe in both cases — and the guards-active check
    in `engine.city_guard_runtime` reads `state` explicitly to
    decide whether to engage).

    Callers that want active-only should check
    ``city.get("state") != "dissolved"`` themselves, or use
    `get_city_by_org` / `get_city_by_name` which already filter.

    Phantom-undelivered fix (May 24 2026): this function was
    referenced by `engine.city_guard_runtime` (3 call sites) and
    listed in architecture v48 §10.4 module surface, but was
    never actually implemented. The broad `try/except` wrapper
    in `should_city_guard_engage` and friends caught the
    AttributeError and returned the safe-default `False`,
    silently breaking Phase 7c trigger evaluation. The
    `tests/test_cities_phase7c_combat.py` suite surfaced 9
    failures once both halves of the Phase 7c implementation
    landed.
    """
    rows = await db.fetchall(
        "SELECT * FROM player_cities WHERE id = ?",
        (int(city_id),),
    )
    return dict(rows[0]) if rows else None


async def get_city_by_org(db, org_id: int) -> Optional[dict]:
    """Return the (active) city for an org, or None.

    Phase 1 invariant: at most one active city per org. (The design's
    multi-city-per-org-via-multiple-HQs future is Phase 7+, gated on
    wilderness cities.)
    """
    rows = await db.fetchall(
        "SELECT * FROM player_cities "
        "WHERE org_id = ? AND state != 'dissolved' "
        "ORDER BY id DESC LIMIT 1",
        (org_id,),
    )
    return dict(rows[0]) if rows else None


async def get_city_for_room(db, room_id: int) -> Optional[dict]:
    """Return the city that contains a room, or None.

    Phase 3 look-output integration consumes this; the contract is
    defined and tested in Phase 1 so the integration surface is
    stable before Phase 3 wires it in.
    """
    rows = await db.fetchall(
        "SELECT pc.* FROM player_cities pc "
        "JOIN player_city_rooms pcr ON pc.id = pcr.city_id "
        "WHERE pcr.room_id = ? AND pc.state != 'dissolved' "
        "LIMIT 1",
        (room_id,),
    )
    return dict(rows[0]) if rows else None


# ── Validation ────────────────────────────────────────────────────────────────

def validate_city_name(name) -> tuple[bool, str]:
    """Pure validation: shape, length, charset, reserved-list.

    Returns (ok, message).
      ok=True  → message is the normalized name (whitespace-trimmed)
      ok=False → message is a human-readable error string

    The function is intentionally pure (no DB access). Name-uniqueness
    is checked separately in found_city() against the live DB.
    """
    if not isinstance(name, str):
        return False, "City name must be a string."
    name = name.strip()
    if len(name) < NAME_MIN_LEN:
        return False, (
            f"City name must be at least {NAME_MIN_LEN} characters."
        )
    if len(name) > NAME_MAX_LEN:
        return False, (
            f"City name must be at most {NAME_MAX_LEN} characters."
        )
    # Allow letters, digits, spaces, apostrophes, hyphens. Reject
    # anything else (quotes, punctuation, control chars, slashes).
    for ch in name:
        if not (ch.isalnum() or ch in " '-"):
            return False, (
                "City name may only contain letters, digits, spaces, "
                "apostrophes, and hyphens."
            )
    if name.lower() in RESERVED_CITY_NAMES:
        return False, (
            f"'{name}' is a reserved name and cannot be used."
        )
    return True, name


# ── Founding ──────────────────────────────────────────────────────────────────

async def found_city(db, char: dict, name: str) -> tuple[bool, str]:
    """Found a new player city for the org of the founding character.

    DEPRECATED 2026-05-24 (anchor) — anchor logic retargets in SYN.4
    per ``contestable_wilderness_design_v2.md`` §2.9 + §3.4. Steps
    7–10 below (the entire HQ-room → zone → declared_security →
    influence chain) get rewritten to anchor on a wilderness region
    instead. Cities founded today are dissolved with a 75% refund
    via ``tools/syn_migration.py`` as part of the SYN.4 drop.

    Validation order (each check short-circuits with an actionable error):

      1. Name validity (pure validation)
      2. Character has a faction membership
      3. Org exists in DB
      4. Character is the org leader (rank 5+)
      5. Org does not already have an active city
      6. City name not duplicate
      7. Org has a tier-5 HQ                          ← SYN.4 retargets
      8. HQ subtype determinable from storage_max     ← SYN.4 retargets
      9. HQ's zone is contested or lawless (explicit) ← SYN.4 retargets
     10. Org has >= 50 influence in that zone         ← SYN.4 retargets
     11. Treasury balance >= founding cost

    On success:
      - Treasury debited by FOUNDING_COSTS[hq_type]
      - One row inserted into player_cities (state='active')
      - HQ rooms anchored as City Center via player_city_rooms

    Returns (ok, message). Caller is responsible for echoing message
    to the player.
    """
    # ── 1. Validate name first (cheap, pure) ─────────────────────
    ok, validated_name = validate_city_name(name)
    if not ok:
        return False, validated_name
    name = validated_name

    # ── 2. Resolve org via faction_id ────────────────────────────
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return False, "You are not a member of any organization."

    # ── 3. Org exists ────────────────────────────────────────────
    org = await db.get_organization(faction_code)
    if not org:
        return False, f"Organization '{faction_code}' could not be found."
    org_id = org["id"]

    # ── 4. Rank check: org leader only ───────────────────────────
    membership = await db.get_membership(char["id"], org_id)
    if not membership:
        return False, "You do not appear to be a member of your organization."
    rank_level = membership.get("rank_level") or 0
    if rank_level < MIN_RANK_LEVEL_TO_FOUND:
        return False, (
            f"Only the organization leader (rank "
            f"{MIN_RANK_LEVEL_TO_FOUND}+) can found a city."
        )

    # ── 5. Already has a city? ───────────────────────────────────
    existing = await get_city_by_org(db, org_id)
    if existing:
        return False, (
            f"Your organization already has a city: {existing['name']}."
        )

    # ── 6. Name uniqueness against live DB ───────────────────────
    name_dup = await get_city_by_name(db, name)
    if name_dup:
        return False, f"A city named '{name}' already exists."

    # ── 7. Org must have a tier-5 HQ ─────────────────────────────
    from engine.housing import get_org_hq
    hq = await get_org_hq(db, faction_code)
    if not hq:
        return False, (
            "Your organization does not have a tier-5 HQ to anchor "
            "a city. Build an HQ first."
        )

    # ── 8. Determine HQ subtype ──────────────────────────────────
    hq_type = _infer_hq_type(hq)
    if hq_type not in FOUNDING_COSTS:
        return False, (
            f"Cannot determine HQ type for city founding "
            f"(storage_max={hq.get('storage_max')!r}). "
            f"This is a data issue; contact an admin."
        )
    cost = FOUNDING_COSTS[hq_type]

    # ── 9. HQ's zone must be contested or lawless ────────────────
    hq_entry_room_id = hq.get("entry_room_id")
    if not hq_entry_room_id:
        return False, "Your HQ does not have a valid entry room."
    hq_room = await db.get_room(hq_entry_room_id)
    if not hq_room:
        return False, "Your HQ's entry room could not be located."
    zone_id = hq_room.get("zone_id")
    if zone_id is None:
        return False, "Your HQ's zone could not be determined."

    # Per May 22 design call: hard-block. Read zone properties
    # directly rather than going through get_zone_security's
    # 'contested' fallback — we want explicit declaration only.
    zone = await db.get_zone(zone_id)
    declared_security = _read_zone_declared_security(zone)
    if declared_security not in ELIGIBLE_SECURITY:
        return False, (
            f"Cities can only be founded in zones with explicit "
            f"contested or lawless security. Your HQ's zone is "
            f"'{declared_security}'."
        )

    # ── 10. Influence threshold ──────────────────────────────────
    from engine.territory import get_territory_influence
    influence = await get_territory_influence(
        db, faction_code, zone_id,
    )
    if (influence or 0) < MIN_INFLUENCE_TO_FOUND:
        return False, (
            f"Your organization needs at least "
            f"{MIN_INFLUENCE_TO_FOUND} influence in this zone to "
            f"found a city. (Current: {influence or 0})"
        )

    # ── 11. Treasury balance ─────────────────────────────────────
    treasury = org.get("treasury") or 0
    if treasury < cost:
        return False, (
            f"Treasury is insufficient. Founding requires "
            f"{cost:,} cr; treasury has {treasury:,} cr."
        )

    # ── All validation passed — commit the transaction ──────────
    now = time.time()
    hq_room_ids = _parse_hq_room_ids(hq)

    # Debit treasury via the canonical adjust_org_treasury entry
    # point (audit-logged in db.database).
    await db.adjust_org_treasury(org_id, -cost)

    # Insert city row.
    # Phase 6 (May 23 2026): set maint_paid_until = now + ONE_WEEK_SECONDS
    # so a brand-new city doesn't get charged maintenance on its first
    # day. The first debit hits at the start of the second week, parallel
    # to the housing rent_paid_until convention.
    cursor = await db.execute(
        "INSERT INTO player_cities "
        "(name, name_lower, org_id, hq_id, zone_id, founded_at, "
        " founder_id, mayor_id, week_start_ts, hq_tier, "
        " maint_paid_until) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, name.lower(), org_id, hq["id"], zone_id, now,
         char["id"], char["id"], now, hq_type,
         now + ONE_WEEK_SECONDS),
    )
    city_id = _extract_lastrowid(cursor)
    if city_id is None:
        # Fallback (some db wrappers don't expose lastrowid)
        lookup = await db.fetchall(
            "SELECT id FROM player_cities WHERE name_lower = ?",
            (name.lower(),),
        )
        city_id = lookup[0]["id"] if lookup else None
    if city_id is None:
        await db.commit()  # avoid leaking the treasury debit
        return False, "Internal error: city created but id not resolvable."

    # Anchor HQ rooms as City Center (is_center=1).
    for rid in hq_room_ids:
        try:
            await db.execute(
                "INSERT INTO player_city_rooms "
                "(city_id, room_id, is_center, claimed_at) "
                "VALUES (?, ?, 1, ?)",
                (city_id, rid, now),
            )
        except Exception as e:
            # Concurrent insert race or duplicate PK — skip this
            # room, log, continue. The PK guarantee protects
            # cross-city contamination.
            log.warning(
                "[player_cities] could not anchor room %s to city %s: %s",
                rid, city_id, e,
            )
    await db.commit()

    log.info(
        "[player_cities] founded '%s' (city_id=%d, org=%s, hq_type=%s, "
        "cost=%d, %d HQ rooms)",
        name, city_id, faction_code, hq_type, cost, len(hq_room_ids),
    )
    return True, (
        f"City '{name}' has been founded. {cost:,} credits debited "
        f"from treasury. {len(hq_room_ids)} HQ rooms are now the "
        f"City Center."
    )


# ── Dissolution ───────────────────────────────────────────────────────────────

async def dissolve_city(db, char: dict, name: str) -> tuple[bool, str]:
    """Dissolve a player city (founder/leader only, by name).

    Phase 1 behavior:
      - Refunds 50% of the founding cost to org treasury.
      - Removes all player_city_rooms rows (HQ rooms lose city
        designation but remain HQ rooms — only the city overlay
        lifts).
      - Removes any banishments + guests (they are now meaningless).
      - Marks city.state = 'dissolved' (row kept for audit).

    Phase 2+ may add expansion-room unclaiming via the territory
    system. Phase 1's HQ rooms remain HQ rooms regardless; this
    function only removes the city overlay, not the HQ itself.

    Returns (ok, message).
    """
    ok, validated_name = validate_city_name(name)
    if not ok:
        return False, validated_name
    name = validated_name

    city = await get_city_by_name(db, name)
    if not city:
        return False, f"No active city named '{name}'."

    # Auth: must be member of the city's org AND org leader
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return False, (
            "You are not a member of the organization that owns "
            "this city."
        )
    org = await db.get_organization(faction_code)
    if not org or org["id"] != city["org_id"]:
        return False, (
            "You are not a member of the organization that owns "
            "this city."
        )
    membership = await db.get_membership(char["id"], org["id"])
    if not membership or (membership.get("rank_level") or 0) < MIN_RANK_LEVEL_TO_FOUND:
        return False, "Only the organization leader can dissolve a city."

    # Refund 50% of founding cost
    hq_type = city.get("hq_tier") or "outpost"
    refund = (FOUNDING_COSTS.get(hq_type, 0) * DISSOLUTION_REFUND_PCT) // 100
    if refund > 0:
        await db.adjust_org_treasury(org["id"], refund)

    # Cascade-remove city-scoped rows (banishments, guests, rooms)
    city_id = city["id"]
    await db.execute(
        "DELETE FROM player_city_rooms WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "DELETE FROM player_city_banishments WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "DELETE FROM player_city_guests WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "UPDATE player_cities SET state = 'dissolved' WHERE id = ?",
        (city_id,),
    )
    await db.commit()

    log.info(
        "[player_cities] dissolved '%s' (city_id=%d, refund=%d)",
        name, city_id, refund,
    )
    return True, (
        f"City '{name}' has been dissolved. "
        f"{refund:,} credits refunded to treasury."
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_hq_room_ids(hq: dict) -> list[int]:
    """Parse the player_housing.room_ids JSON list to a python list."""
    raw = hq.get("room_ids")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [int(r) for r in raw if r is not None]
    try:
        parsed = json.loads(raw)
        return [int(r) for r in parsed if r is not None]
    except Exception:
        return []


def _infer_hq_type(hq: dict) -> str:
    """Infer the HQ subtype from storage_max.

    engine.housing.TIER5_TYPES sets storage_max uniquely per subtype
    (100 outpost / 200 chapter_house / 400 fortress) and the field is
    persisted on player_housing. This is the durable signal at HEAD;
    purchase_hq does NOT store a named subtype.

    Returns 'outpost' / 'chapter_house' / 'fortress' or '' if the
    storage_max doesn't match a known tier-5 value.
    """
    storage_max = hq.get("storage_max")
    if storage_max is None:
        return ""
    try:
        return _STORAGE_TO_HQ_TYPE.get(int(storage_max), "")
    except (TypeError, ValueError):
        return ""


def _read_zone_declared_security(zone: Optional[dict]) -> str:
    """Read the *declared* security level from a zone row.

    Bypasses engine.territory.get_zone_security's 'contested'
    fallback. Returns the empty string '' if no explicit security
    is declared in the zone's properties — that's the signal
    eligibility should be rejected (per May 22 hard-block call).
    """
    if not zone:
        return ""
    props = zone.get("properties") or "{}"
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except Exception:
            return ""
    if not isinstance(props, dict):
        return ""
    sec = props.get("security")
    if isinstance(sec, str):
        return sec
    return ""


def _extract_lastrowid(cursor):
    """Best-effort lastrowid extraction across SQLite cursor wrappers.

    The aiosqlite Cursor exposes ``.lastrowid``; some test stubs
    return the cursor wrapped or as None. This helper returns None
    on any failure rather than raising.
    """
    if cursor is None:
        return None
    val = getattr(cursor, "lastrowid", None)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ── Phase 2: expansion read helpers ───────────────────────────────────────────

async def get_city_expansion_count(db, city_id: int) -> int:
    """Count non-center (expansion) rooms for a city.

    Used to enforce ``MAX_EXPANSION_ROOMS[hq_tier]``. The HQ rooms
    (is_center=1) don't count against the cap — only expansion rooms.
    """
    rows = await db.fetchall(
        "SELECT COUNT(*) AS n FROM player_city_rooms "
        "WHERE city_id = ? AND is_center = 0",
        (city_id,),
    )
    return int(rows[0]["n"]) if rows else 0


async def get_city_last_expansion(db, city_id: int) -> float:
    """Wall-clock timestamp of the most recent expansion claim.

    Returns 0.0 if the city has never expanded (no non-center rooms).
    Used by the 24-hour rate-limit check.
    """
    rows = await db.fetchall(
        "SELECT MAX(claimed_at) AS t FROM player_city_rooms "
        "WHERE city_id = ? AND is_center = 0",
        (city_id,),
    )
    if not rows:
        return 0.0
    t = rows[0]["t"]
    return float(t) if t is not None else 0.0


# ── Phase 2: expansion (claim) ────────────────────────────────────────────────

async def claim_room_for_city(
    db, char: dict, target_room_id: int,
) -> tuple[bool, str]:
    """Claim a room as a city expansion room.

    DEPRECATED 2026-05-24 — retires in SYN.4 per
    ``contestable_wilderness_design_v2.md`` §2.9 + §6. The per-room
    expansion model goes away entirely when cities anchor on
    wilderness regions: a city IS the region, and expansion happens
    via wilderness landmark capture + building construction (SYN.9),
    not by claiming individual map rooms.

    Validation order (each short-circuits with an actionable error):

      1. Character has a faction membership
      2. Org has an active city
      3. Character is the org leader (rank 5+)  [matches founding]
      4. Target room exists
      5. Target room is in the same zone as the city
      6. Target room not already a city room (any city)
      7. Size cap: count(expansion rooms) < MAX_EXPANSION_ROOMS[tier]
      8. Contiguity: target shares an exit with an existing city room
      9. 24-hour rate-limit (honors cooldowns_enabled() dev bypass)
     10. Influence threshold (>= 50 in the city's zone)
     11. Treasury >= EXPANSION_CLAIM_COST

    On success:
      - Treasury debited 5,000 cr
      - One row inserted into player_city_rooms (is_center=0)

    Per the Phase 2 design call: we do NOT write to territory_claims.
    See module-level docstring "Phase 2 May 22 2026 design call".

    Returns (ok, message).
    """
    # ── 1. Resolve org via faction_id ─────────────────────────────
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return False, "You are not a member of any organization."
    org = await db.get_organization(faction_code)
    if not org:
        return False, f"Organization '{faction_code}' could not be found."
    org_id = org["id"]

    # ── 2. Org must have an active city ──────────────────────────
    city = await get_city_by_org(db, org_id)
    if not city:
        return False, "Your organization has no active city to expand."

    # ── 3. Rank check ────────────────────────────────────────────
    membership = await db.get_membership(char["id"], org_id)
    if not membership or (membership.get("rank_level") or 0) < MIN_RANK_LEVEL_TO_FOUND:
        return False, (
            f"Only the organization leader (rank "
            f"{MIN_RANK_LEVEL_TO_FOUND}+) can claim city expansion rooms."
        )

    # ── 4. Target room exists ────────────────────────────────────
    target_room = await db.get_room(target_room_id)
    if not target_room:
        return False, "That room does not exist."

    # ── 5. Same zone as city center ──────────────────────────────
    target_zone = target_room.get("zone_id")
    if target_zone != city.get("zone_id"):
        return False, (
            "Cities cannot expand across zones. The target room is "
            "in a different zone from your city center."
        )

    # ── 6. Not already a city room ───────────────────────────────
    existing_city = await get_city_for_room(db, target_room_id)
    if existing_city:
        if existing_city["id"] == city["id"]:
            return False, "That room is already part of your city."
        return False, (
            f"That room is already part of another city: "
            f"{existing_city['name']}."
        )

    # ── 7. Size cap ──────────────────────────────────────────────
    hq_tier = city.get("hq_tier") or "outpost"
    max_expansion = MAX_EXPANSION_ROOMS.get(hq_tier)
    if max_expansion is None:
        return False, (
            f"Unknown city tier '{hq_tier}'. Cannot resolve "
            f"expansion cap."
        )
    current_expansion = await get_city_expansion_count(db, city["id"])
    if current_expansion >= max_expansion:
        return False, (
            f"City has reached its expansion cap "
            f"({current_expansion}/{max_expansion} rooms for "
            f"'{hq_tier}' tier). Upgrade the HQ to expand further."
        )

    # ── 8. Contiguity: target must share an exit with a city room ─
    contiguous = await _is_contiguous_to_city(
        db, city["id"], target_room_id,
    )
    if not contiguous:
        return False, (
            "The target room is not adjacent to any existing city "
            "room. Cities can only expand to rooms with a direct "
            "exit from the city."
        )

    # ── 9. 24-hour rate limit ────────────────────────────────────
    # Honors the cooldowns_enabled() dev-bypass seam (F.7.k
    # convention). In dev mode the limit is skipped; in production
    # mode the gate is enforced at wall-clock.
    try:
        from engine.jedi_gating import cooldowns_enabled
        enforce_cooldown = cooldowns_enabled()
    except Exception:
        # If the seam is unavailable for any reason, fall back to
        # enforcing (production-safe default).
        enforce_cooldown = True

    if enforce_cooldown:
        last = await get_city_last_expansion(db, city["id"])
        now = time.time()
        if last > 0 and (now - last) < EXPANSION_RATE_LIMIT_SECONDS:
            remaining = EXPANSION_RATE_LIMIT_SECONDS - (now - last)
            hours_left = max(1, int(remaining // 3600 + 1))
            return False, (
                f"City expansion is rate-limited to one claim per "
                f"24 hours. Try again in ~{hours_left} hour"
                f"{'s' if hours_left != 1 else ''}."
            )

    # ── 10. Influence threshold ──────────────────────────────────
    from engine.territory import get_territory_influence
    zone_id = city["zone_id"]
    influence = await get_territory_influence(
        db, faction_code, zone_id,
    )
    if (influence or 0) < EXPANSION_INFLUENCE_THRESHOLD:
        return False, (
            f"Your organization needs at least "
            f"{EXPANSION_INFLUENCE_THRESHOLD} influence in this "
            f"zone to claim expansion rooms. "
            f"(Current: {influence or 0})"
        )

    # ── 11. Treasury check ───────────────────────────────────────
    treasury = org.get("treasury") or 0
    if treasury < EXPANSION_CLAIM_COST:
        return False, (
            f"Treasury is insufficient. Expansion claim requires "
            f"{EXPANSION_CLAIM_COST:,} cr; treasury has "
            f"{treasury:,} cr."
        )

    # ── All validation passed — commit ───────────────────────────
    await db.adjust_org_treasury(org_id, -EXPANSION_CLAIM_COST)
    now = time.time()
    try:
        await db.execute(
            "INSERT INTO player_city_rooms "
            "(city_id, room_id, is_center, claimed_at) "
            "VALUES (?, ?, 0, ?)",
            (city["id"], target_room_id, now),
        )
        await db.commit()
    except Exception as e:
        # Race with another writer creating the same (city_id, room_id)
        # PK collision. Refund treasury and return a soft error.
        log.warning(
            "[player_cities] claim_room_for_city PK conflict: "
            "city=%s room=%s err=%s",
            city["id"], target_room_id, e,
        )
        await db.adjust_org_treasury(org_id, EXPANSION_CLAIM_COST)
        return False, "That room was just claimed by another action. Try again."

    room_name = target_room.get("name", f"Room #{target_room_id}")
    new_count = current_expansion + 1
    log.info(
        "[player_cities] expansion claimed: city=%s room=%s (%s) "
        "cost=%d new_count=%d/%d",
        city["name"], target_room_id, room_name,
        EXPANSION_CLAIM_COST, new_count, max_expansion,
    )
    return True, (
        f"Claimed '{room_name}' for {city['name']}. "
        f"{EXPANSION_CLAIM_COST:,} credits debited. "
        f"City size: {new_count}/{max_expansion} expansion rooms."
    )


# ── Phase 2: release ──────────────────────────────────────────────────────────

async def release_room_from_city(
    db, char: dict, room_id: int,
) -> tuple[bool, str]:
    """Release a city expansion room.

    Phase 2 behavior per design §3.2:
      - Removes the room from player_city_rooms.
      - Refunds 50% of EXPANSION_CLAIM_COST = 2,500 cr.
      - Cannot release the City Center (HQ rooms). To remove HQ
        rooms, the city must dissolve.

    Returns (ok, message).
    """
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return False, "You are not a member of any organization."
    org = await db.get_organization(faction_code)
    if not org:
        return False, f"Organization '{faction_code}' could not be found."
    org_id = org["id"]

    # Must have an active city
    city = await get_city_by_org(db, org_id)
    if not city:
        return False, "Your organization has no active city."

    # Rank check
    membership = await db.get_membership(char["id"], org_id)
    if not membership or (membership.get("rank_level") or 0) < MIN_RANK_LEVEL_TO_FOUND:
        return False, (
            f"Only the organization leader can release city rooms."
        )

    # Find the player_city_rooms row
    rows = await db.fetchall(
        "SELECT * FROM player_city_rooms "
        "WHERE city_id = ? AND room_id = ?",
        (city["id"], room_id),
    )
    if not rows:
        return False, "That room is not part of your city."
    row = rows[0]
    if row["is_center"]:
        return False, (
            "HQ rooms (City Center) cannot be released individually. "
            "To remove HQ rooms, dissolve the entire city with "
            "'+city dissolve'."
        )

    # Refund 50% of EXPANSION_CLAIM_COST
    refund = (EXPANSION_CLAIM_COST * EXPANSION_REFUND_PCT) // 100
    await db.adjust_org_treasury(org_id, refund)

    # Drop the row
    await db.execute(
        "DELETE FROM player_city_rooms "
        "WHERE city_id = ? AND room_id = ?",
        (city["id"], room_id),
    )
    await db.commit()

    target_room = await db.get_room(room_id)
    room_name = (
        target_room.get("name", f"Room #{room_id}")
        if target_room else f"Room #{room_id}"
    )
    log.info(
        "[player_cities] expansion released: city=%s room=%s (%s) "
        "refund=%d",
        city["name"], room_id, room_name, refund,
    )
    return True, (
        f"Released '{room_name}' from {city['name']}. "
        f"{refund:,} credits refunded to treasury."
    )


# ── Phase 2: contiguity ───────────────────────────────────────────────────────

async def _is_contiguous_to_city(
    db, city_id: int, target_room_id: int,
) -> bool:
    """Return True if target_room_id shares at least one direct
    exit with either an existing player_city_rooms entry for
    city_id, OR the HQ's entry_room (the city's outward-facing
    doorstep).

    Contiguity sources:
      1. Any row in player_city_rooms for this city (HQ rooms +
         already-claimed expansion rooms).
      2. The HQ's entry_room_id from player_housing.

    The entry_room is included even though it isn't stored as a
    city room itself. Per engine.housing.purchase_hq, the HQ rooms
    are interior — they connect ONLY to each other and to the
    entry_room via 'out'. Without including the entry_room as a
    contiguity anchor, expansion would never reach any zone room
    from the City Center. This is the pragmatic resolution of the
    design's "+city claim outward" semantics against the housing
    architecture's interior-HQ topology.

    The check is symmetric: either the target has an exit pointing
    at a contiguity-source, OR a contiguity-source has an exit
    pointing at the target. Either direction counts (handles
    one-way exits gracefully).
    """
    # Get all current city room ids
    crows = await db.fetchall(
        "SELECT room_id FROM player_city_rooms WHERE city_id = ?",
        (city_id,),
    )
    sources = {r["room_id"] for r in crows}

    # Add the HQ's entry_room as a contiguity anchor
    city_rows = await db.fetchall(
        "SELECT hq_id FROM player_cities WHERE id = ?",
        (city_id,),
    )
    if city_rows:
        hq_id = city_rows[0]["hq_id"]
        hq_rows = await db.fetchall(
            "SELECT entry_room_id FROM player_housing WHERE id = ?",
            (hq_id,),
        )
        if hq_rows and hq_rows[0]["entry_room_id"]:
            sources.add(int(hq_rows[0]["entry_room_id"]))

    if not sources:
        return False  # impossible if Phase 1 ran, but safe-guard
    if target_room_id in sources:
        return False  # target IS a source — not "adjacent to", but inside

    # Direction 1: target has an exit to a source
    erows = await db.fetchall(
        "SELECT to_room_id FROM exits WHERE from_room_id = ?",
        (target_room_id,),
    )
    for r in erows:
        if r["to_room_id"] in sources:
            return True

    # Direction 2: a source has an exit to the target
    placeholders = ",".join("?" * len(sources))
    erows2 = await db.fetchall(
        f"SELECT from_room_id FROM exits "
        f"WHERE to_room_id = ? AND from_room_id IN ({placeholders})",
        (target_room_id, *sources),
    )
    return bool(erows2)


# ── Phase 2: direction-to-room resolution helper ──────────────────────────────

async def resolve_direction_to_room(
    db, from_room_id: int, direction: str,
) -> tuple[int | None, str]:
    """Resolve a direction keyword (e.g. 'northwest') from a room
    to a target room_id via the exits table.

    Returns (target_room_id, ""). On failure returns (None, error).
    """
    direction = (direction or "").strip().lower()
    if not direction:
        return None, "No direction provided."

    rows = await db.fetchall(
        "SELECT to_room_id, direction FROM exits "
        "WHERE from_room_id = ? AND LOWER(direction) = ?",
        (from_room_id, direction),
    )
    if not rows:
        return None, f"There is no exit '{direction}' from your current room."
    return int(rows[0]["to_room_id"]), ""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Governance + look-output
# ─────────────────────────────────────────────────────────────────────────────


# ── Internal: shared auth resolvers ──────────────────────────────────────────

async def _resolve_actor_city(
    db, char: dict,
) -> tuple[Optional[dict], Optional[dict], str]:
    """Resolve (org, city, error) for a character acting on their org's city.

    Used by all Phase 3 governance commands. The org is read by the
    character's faction_id; the city is the org's single active city
    (Phase 1 invariant). If any link is missing, returns
    (None, None, actionable_error).
    """
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return None, None, "You are not a member of any organization."
    org = await db.get_organization(faction_code)
    if not org:
        return None, None, (
            f"Organization '{faction_code}' could not be found."
        )
    city = await get_city_by_org(db, org["id"])
    if not city:
        return org, None, "Your organization has no active city."
    return org, city, ""


async def _is_org_leader(db, char_id: int, org_id: int) -> bool:
    """Return True iff char is rank >= MIN_RANK_LEVEL_TO_FOUND in org."""
    membership = await db.get_membership(char_id, org_id)
    if not membership:
        return False
    return (membership.get("rank_level") or 0) >= MIN_RANK_LEVEL_TO_FOUND


async def _is_founder(city: dict, char: dict) -> bool:
    """Return True iff char is the city's recorded founder."""
    return int(city.get("founder_id") or 0) == int(char.get("id") or 0)


async def _is_mayor(city: dict, char: dict) -> bool:
    """Return True iff char is the city's recorded Mayor."""
    return int(city.get("mayor_id") or 0) == int(char.get("id") or 0)


# ── Phase 3: read helpers ────────────────────────────────────────────────────

async def is_banished(db, city_id: int, char_id: int) -> bool:
    """Return True iff char is under an active banishment from city.

    "Active" means `until > now`. Expired banishment rows are kept for
    audit (no auto-delete in Phase 3); the read filter does the work.
    """
    rows = await db.fetchall(
        "SELECT until FROM player_city_banishments "
        "WHERE city_id = ? AND char_id = ?",
        (city_id, char_id),
    )
    if not rows:
        return False
    return float(rows[0]["until"] or 0) > time.time()


async def is_guest(db, city_id: int, char_id: int) -> bool:
    """Return True iff char is on the city's guest list."""
    rows = await db.fetchall(
        "SELECT 1 FROM player_city_guests "
        "WHERE city_id = ? AND char_id = ?",
        (city_id, char_id),
    )
    return bool(rows)


async def get_city_role(db, city: dict, char: dict) -> str:
    """Return char's role in city.

    Returns one of:
      - "banished"  — active banishment (highest priority; overrides
        org membership)
      - "founder"   — char is the immutable founder_id
      - "mayor"     — char is the current mayor_id
      - "citizen"   — char is a member of the city's org (any rank)
      - "guest"     — char is on the guest list
      - "outsider"  — none of the above

    "founder" and "mayor" coincide initially (the founder is the
    first mayor); the role returned is whichever distinguishes them
    most usefully — we return "founder" because founder permissions
    are a strict superset of mayor permissions, so the higher role
    surfaces first. Phase 3 commands use is_founder/is_mayor for
    auth instead of role-string comparison for clarity.
    """
    char_id = int(char.get("id") or 0)
    city_id = int(city.get("id") or 0)
    if not char_id or not city_id:
        return "outsider"

    # Banishment overrides everything except admin-void (Phase 6)
    if await is_banished(db, city_id, char_id):
        return "banished"

    if int(city.get("founder_id") or 0) == char_id:
        return "founder"
    if int(city.get("mayor_id") or 0) == char_id:
        return "mayor"

    # Citizen check: member of the city's org
    membership = await db.get_membership(char_id, int(city.get("org_id") or 0))
    if membership:
        return "citizen"

    # Guest check
    if await is_guest(db, city_id, char_id):
        return "guest"

    return "outsider"


async def list_active_cities(
    db, *, zone_id: Optional[int] = None,
) -> list[dict]:
    """Return active cities, optionally filtered by zone.

    Result ordered by founded_at ascending (oldest first). Each row
    is a dict from player_cities. Phase 3 consumer is `+city list`;
    Phase 4+ readers may add their own filters.
    """
    if zone_id is None:
        rows = await db.fetchall(
            "SELECT * FROM player_cities "
            "WHERE state != 'dissolved' "
            "ORDER BY founded_at ASC"
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM player_cities "
            "WHERE state != 'dissolved' AND zone_id = ? "
            "ORDER BY founded_at ASC",
            (zone_id,),
        )
    return [dict(r) for r in rows]


async def list_citizen_room_ids(
    db, city_id: int,
) -> list[int]:
    """Return the list of room_ids in the city that are citizen_only.

    Used by `+city info` and by Phase 5 movement gating.
    """
    rows = await db.fetchall(
        "SELECT room_id FROM player_city_rooms "
        "WHERE city_id = ? AND citizen_only = 1",
        (city_id,),
    )
    return [int(r["room_id"]) for r in rows]


async def list_city_room_ids(
    db, city_id: int,
) -> list[int]:
    """Return all room_ids in the city (center + expansion)."""
    rows = await db.fetchall(
        "SELECT room_id FROM player_city_rooms "
        "WHERE city_id = ? "
        "ORDER BY is_center DESC, claimed_at ASC",
        (city_id,),
    )
    return [int(r["room_id"]) for r in rows]


async def list_guests(db, city_id: int) -> list[int]:
    """Return char_ids of city guests."""
    rows = await db.fetchall(
        "SELECT char_id FROM player_city_guests "
        "WHERE city_id = ? "
        "ORDER BY added_at ASC",
        (city_id,),
    )
    return [int(r["char_id"]) for r in rows]


async def list_active_banishments(db, city_id: int) -> list[dict]:
    """Return active banishments for a city (until > now).

    Each row dict has char_id, until, issued_by, issued_at.
    """
    rows = await db.fetchall(
        "SELECT char_id, until, issued_by, issued_at "
        "FROM player_city_banishments "
        "WHERE city_id = ? AND until > ? "
        "ORDER BY issued_at DESC",
        (city_id, time.time()),
    )
    return [dict(r) for r in rows]


# ── Phase 3: Founder-only commands ───────────────────────────────────────────

async def assign_mayor(
    db, char: dict, target_char_id: int,
) -> tuple[bool, str]:
    """Assign a new Mayor for the founder's city.

    Founder-only (immutable founder per design §4.3). The target
    must be an org member with at least rank 1 (any membership). The
    founder may assign themselves (no-op in practice).

    Returns (ok, message).
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err

    if not await _is_founder(city, char):
        return False, (
            "Only the city's Founder can reassign the Mayor role."
        )

    target = await db.get_character(int(target_char_id))
    if not target:
        return False, "That character does not exist."

    membership = await db.get_membership(int(target["id"]), int(org["id"]))
    if not membership:
        return False, (
            f"{target['name']} is not a member of {org['name']}. "
            f"Only org members can serve as Mayor."
        )

    # Idempotent: if already mayor, return success with no-op message
    if int(city.get("mayor_id") or 0) == int(target["id"]):
        return True, f"{target['name']} is already the Mayor of {city['name']}."

    await db.execute(
        "UPDATE player_cities SET mayor_id = ? WHERE id = ?",
        (int(target["id"]), int(city["id"])),
    )
    await db.commit()
    log.info(
        "[player_cities] mayor reassigned: city=%s, new_mayor=%s",
        city["name"], target["name"],
    )
    return True, (
        f"{target['name']} has been appointed Mayor of {city['name']}."
    )


# ── Phase 3: Mayor-or-Founder commands ───────────────────────────────────────

def _is_mayor_or_founder(city: dict, char: dict) -> bool:
    """Sync helper: True iff char is Mayor or Founder of city."""
    char_id = int(char.get("id") or 0)
    return (
        int(city.get("mayor_id") or 0) == char_id
        or int(city.get("founder_id") or 0) == char_id
    )


async def set_city_motd(
    db, char: dict, motd_text: str,
) -> tuple[bool, str]:
    """Set the city's motd (shown on room entry).

    Mayor or Founder only. Per design §4.2.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, (
            "Only the Mayor or Founder can set the city's motd."
        )

    if motd_text is None:
        motd_text = ""
    motd_text = str(motd_text).strip()
    if len(motd_text) > MOTD_MAX_LEN:
        return False, (
            f"Motd text is too long ({len(motd_text)} chars; max "
            f"{MOTD_MAX_LEN})."
        )

    await db.execute(
        "UPDATE player_cities SET motd = ? WHERE id = ?",
        (motd_text, int(city["id"])),
    )
    await db.commit()
    log.info(
        "[player_cities] motd set on city=%s by char=%s",
        city["name"], char.get("name"),
    )
    if not motd_text:
        return True, f"Motd cleared for {city['name']}."
    return True, f"Motd set for {city['name']}."


async def add_guest(
    db, char: dict, target_char_id: int,
) -> tuple[bool, str]:
    """Add a character to the city's guest list.

    Mayor or Founder only. Per design §4.1: guests have free
    movement but no rest bonus and cannot use restricted services.
    A character can be a guest of multiple cities (per-city table).

    Idempotent — re-adding an existing guest is a no-op success.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, "Only the Mayor or Founder can manage the guest list."

    target = await db.get_character(int(target_char_id))
    if not target:
        return False, "That character does not exist."

    # Reject adding a citizen as guest (redundant — citizens already
    # have free movement)
    target_membership = await db.get_membership(
        int(target["id"]), int(org["id"]),
    )
    if target_membership:
        return False, (
            f"{target['name']} is already a citizen of {city['name']} "
            f"(via {org['name']} membership). No guest entry needed."
        )

    if await is_guest(db, int(city["id"]), int(target["id"])):
        return True, f"{target['name']} is already a guest of {city['name']}."

    now = time.time()
    await db.execute(
        "INSERT INTO player_city_guests "
        "(city_id, char_id, added_by, added_at) "
        "VALUES (?, ?, ?, ?)",
        (int(city["id"]), int(target["id"]), int(char["id"]), now),
    )
    await db.commit()
    log.info(
        "[player_cities] guest added: city=%s, target=%s, by=%s",
        city["name"], target["name"], char.get("name"),
    )
    return True, f"{target['name']} added as a guest of {city['name']}."


async def remove_guest(
    db, char: dict, target_char_id: int,
) -> tuple[bool, str]:
    """Remove a character from the city's guest list. Mayor/Founder only."""
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, "Only the Mayor or Founder can manage the guest list."

    target = await db.get_character(int(target_char_id))
    if not target:
        return False, "That character does not exist."

    if not await is_guest(db, int(city["id"]), int(target["id"])):
        return False, (
            f"{target['name']} is not on the guest list of {city['name']}."
        )

    await db.execute(
        "DELETE FROM player_city_guests "
        "WHERE city_id = ? AND char_id = ?",
        (int(city["id"]), int(target["id"])),
    )
    await db.commit()
    log.info(
        "[player_cities] guest removed: city=%s, target=%s, by=%s",
        city["name"], target["name"], char.get("name"),
    )
    return True, f"{target['name']} removed from the guest list of {city['name']}."


async def banish_player(
    db, char: dict, target_char_id: int, *,
    duration_seconds: int = BANISHMENT_DEFAULT_SECONDS,
) -> tuple[bool, str]:
    """Banish a character from the city for duration_seconds.

    Mayor or Founder only. Per design §4.4: 30 days default; cannot
    banish org leadership of other orgs (anti-griefing). The Founder
    of THIS city is also unbanishable to prevent a hostile-Mayor
    from locking out the Founder.

    Re-banishing an already-banished character extends/replaces the
    expiry (last-write-wins). Cannot banish self.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, "Only the Mayor or Founder can banish players."

    target = await db.get_character(int(target_char_id))
    if not target:
        return False, "That character does not exist."

    target_id = int(target["id"])

    if target_id == int(char.get("id") or 0):
        return False, "You cannot banish yourself."

    # Cannot banish this city's Founder
    if target_id == int(city.get("founder_id") or 0):
        return False, (
            f"The Founder of {city['name']} cannot be banished. "
            f"Only the org leadership or admin moderation can resolve "
            f"this dispute."
        )

    # Anti-griefing per design §4.4 (Phase 3 design call): block
    # banishment of any rank-5+ leader of another org. Admin override
    # is Phase 6 `@city void-banish`.
    other_org_leaderships = await db.fetchall(
        "SELECT org_id FROM org_memberships "
        "WHERE char_id = ? AND rank_level >= ? AND org_id != ?",
        (target_id, MIN_RANK_LEVEL_TO_FOUND, int(org["id"])),
    )
    if other_org_leaderships:
        return False, (
            f"{target['name']} is a leader of another organization "
            f"and cannot be banished without admin approval (per "
            f"anti-griefing rule)."
        )

    if duration_seconds <= 0:
        return False, "Banishment duration must be positive."

    now = time.time()
    until = now + duration_seconds

    # Upsert: replace any existing banishment row for this (city, char)
    await db.execute(
        "DELETE FROM player_city_banishments "
        "WHERE city_id = ? AND char_id = ?",
        (int(city["id"]), target_id),
    )
    await db.execute(
        "INSERT INTO player_city_banishments "
        "(city_id, char_id, until, issued_by, issued_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (int(city["id"]), target_id, until, int(char["id"]), now),
    )
    # Also drop them from the guest list if present — banishment
    # supersedes guest status.
    await db.execute(
        "DELETE FROM player_city_guests "
        "WHERE city_id = ? AND char_id = ?",
        (int(city["id"]), target_id),
    )
    await db.commit()

    days = int(duration_seconds // (24 * 60 * 60))
    log.info(
        "[player_cities] banished: city=%s, target=%s, until=%.0f, by=%s",
        city["name"], target["name"], until, char.get("name"),
    )
    return True, (
        f"{target['name']} has been banished from {city['name']} "
        f"for {days} days."
    )


async def unbanish_player(
    db, char: dict, target_char_id: int,
) -> tuple[bool, str]:
    """Lift a banishment. Mayor or Founder only.

    Idempotent: lifting a non-banishment returns a clear no-op.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, "Only the Mayor or Founder can lift banishments."

    target = await db.get_character(int(target_char_id))
    if not target:
        return False, "That character does not exist."

    target_id = int(target["id"])

    rows = await db.fetchall(
        "SELECT 1 FROM player_city_banishments "
        "WHERE city_id = ? AND char_id = ?",
        (int(city["id"]), target_id),
    )
    if not rows:
        return False, (
            f"{target['name']} is not banished from {city['name']}."
        )

    await db.execute(
        "DELETE FROM player_city_banishments "
        "WHERE city_id = ? AND char_id = ?",
        (int(city["id"]), target_id),
    )
    await db.commit()
    log.info(
        "[player_cities] unbanished: city=%s, target=%s, by=%s",
        city["name"], target["name"], char.get("name"),
    )
    return True, (
        f"Banishment lifted for {target['name']} from {city['name']}."
    )


async def set_room_citizen_only(
    db, char: dict, room_id: int, flag: bool,
) -> tuple[bool, str]:
    """Mark a city room as citizen-only (or clear the flag).

    Mayor or Founder only. The room must be part of the city. The
    City Center HQ rooms (is_center=1) are citizen-only by default
    per design §6.3 and don't count against the 30% cap on non-HQ
    citizen_only rooms (Phase 5 May 22 2026 design call #2).

    When ``flag=True`` and the target is a non-HQ room, the engine
    enforces the cap: the count of non-HQ citizen_only rooms after
    this change must not exceed 30% of non-HQ rooms. To avoid
    rounding lockouts on small cities, the ceiling is computed as
    ``max(1, int(0.30 * non_hq_count))``.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, (
            "Only the Mayor or Founder can flag city rooms as "
            "citizen-only."
        )

    rows = await db.fetchall(
        "SELECT room_id, is_center FROM player_city_rooms "
        "WHERE city_id = ? AND room_id = ?",
        (int(city["id"]), int(room_id)),
    )
    if not rows:
        return False, "That room is not part of your city."
    target_is_center = bool(int(rows[0]["is_center"]))

    # Phase 6 (May 23 2026) gate: per design §8.2 week 2, citizen
    # flagging is locked while the city is in grace stage week2 or
    # later. Clearing the flag (flag=False) is always allowed.
    if flag and is_citizen_flagging_disabled(city):
        return False, (
            f"{city['name']} is in maintenance grace; citizen-only "
            f"flagging is suspended. Refill the org treasury to "
            f"restore the city."
        )

    # Phase 5 §6.3: 30%-cap on non-HQ citizen_only rooms. Only
    # enforced when SETTING the flag (clearing it is always safe),
    # and only counted against non-HQ rooms (HQ rooms are
    # citizen-only by default per design wording, exempt from cap).
    if flag and not target_is_center:
        # Count non-HQ rooms in this city
        non_hq_total_rows = await db.fetchall(
            "SELECT COUNT(*) AS n FROM player_city_rooms "
            "WHERE city_id = ? AND is_center = 0",
            (int(city["id"]),),
        )
        non_hq_total = int(non_hq_total_rows[0]["n"]) if non_hq_total_rows else 0

        # Count non-HQ rooms currently flagged citizen_only
        non_hq_co_rows = await db.fetchall(
            "SELECT COUNT(*) AS n FROM player_city_rooms "
            "WHERE city_id = ? AND is_center = 0 "
            "AND citizen_only = 1 AND room_id != ?",
            (int(city["id"]), int(room_id)),
        )
        non_hq_co_after = int(non_hq_co_rows[0]["n"]) + 1
        ceiling = max(1, int(0.30 * non_hq_total))
        if non_hq_co_after > ceiling:
            return False, (
                f"At most {ceiling} of {non_hq_total} expansion "
                f"rooms can be citizen-only (30% cap per design "
                f"§6.3). Currently {non_hq_co_after - 1} "
                f"expansion rooms are citizen-only. Clear another "
                f"with `+city citizenroom off <room>` first."
            )

    flag_int = 1 if flag else 0
    await db.execute(
        "UPDATE player_city_rooms SET citizen_only = ? "
        "WHERE city_id = ? AND room_id = ?",
        (flag_int, int(city["id"]), int(room_id)),
    )
    await db.commit()
    log.info(
        "[player_cities] room citizen_only=%d: city=%s, room=%d, by=%s",
        flag_int, city["name"], int(room_id), char.get("name"),
    )
    verb = "marked as citizen-only" if flag else "opened to non-citizens"
    return True, f"Room {int(room_id)} {verb} in {city['name']}."


# ── Phase 3: rendering helpers ───────────────────────────────────────────────

def format_city_header_tag(city: dict) -> str:
    """Return the bracket tag for the LookCommand chain.

    Format: ``" [CITY: <name>]"`` (leading space included). Returns
    empty string if city is falsy. Caller is responsible for
    color/style. The viewer-aware "you are not welcome" warning is
    rendered separately via the room overlay path (so the bracket
    chain stays compact and the warning gets its own line per
    design §12).
    """
    if not city:
        return ""
    return f" [CITY: {city.get('name', '<unnamed>')}]"


async def format_city_info(
    db, city: dict, viewer: Optional[dict] = None,
) -> list[str]:
    """Render a multi-line info block for `+city info`.

    Returns a list of lines (no terminal newlines). Lines are
    plain text; the parser layer adds any ANSI styling.

    Viewer-aware:
      - If viewer is None or an outsider, the citizens list is
        replaced with a count-only line ("Citizens: 12 members").
      - If viewer is a citizen/mayor/founder, the citizens list
        renders names from the org_memberships table.
      - If viewer is banished, the info block is replaced with a
        single-line "you are not welcome here" message.
    """
    if not city:
        return ["No city to display."]

    # Banishment short-circuit
    viewer_role = "outsider"
    if viewer:
        viewer_role = await get_city_role(db, city, viewer)
    if viewer_role == "banished":
        return [f"You are banished from {city.get('name', '<city>')}."]

    name = city.get("name", "<unnamed>")
    org_id = int(city.get("org_id") or 0)
    org = None
    if org_id:
        org_rows = await db.fetchall(
            "SELECT name, code FROM organizations WHERE id = ?",
            (org_id,),
        )
        if org_rows:
            org = dict(org_rows[0])
    org_name = org["name"] if org else "<unknown org>"

    hq_tier = city.get("hq_tier") or "outpost"
    max_expansion = MAX_EXPANSION_ROOMS.get(hq_tier, 0)
    expansion_count = await get_city_expansion_count(db, int(city["id"]))

    founder = None
    if city.get("founder_id"):
        founder = await db.get_character(int(city["founder_id"]))
    founder_name = founder["name"] if founder else "<unknown>"

    mayor = None
    if city.get("mayor_id"):
        mayor = await db.get_character(int(city["mayor_id"]))
    mayor_name = mayor["name"] if mayor else "<vacant>"

    tax_rate = float(city.get("tax_rate") or 0.0)
    motd = (city.get("motd") or "").strip()

    lines = [
        f"=== {name} ===",
        f"Founding org:    {org_name}",
        f"Founder:         {founder_name}",
        f"Mayor:           {mayor_name}",
        f"HQ tier:         {hq_tier} "
        f"({expansion_count}/{max_expansion} expansion rooms)",
        f"Tax rate:        {tax_rate * 100:.1f}%",
        f"State:           {city.get('state') or 'active'}",
    ]
    if motd:
        lines.append(f"Motd:            {motd}")

    # Citizen list (member-visible only)
    if viewer_role in ("founder", "mayor", "citizen"):
        member_rows = await db.fetchall(
            "SELECT c.name, m.rank_level "
            "FROM org_memberships m "
            "JOIN characters c ON c.id = m.char_id "
            "WHERE m.org_id = ? "
            "ORDER BY m.rank_level DESC, c.name ASC",
            (org_id,),
        )
        member_count = len(member_rows)
        lines.append(f"Citizens:        {member_count} members")
        for r in member_rows[:10]:  # cap inline list
            lines.append(f"  - {r['name']} (rank {r['rank_level']})")
        if member_count > 10:
            lines.append(f"  ... and {member_count - 10} more")
    else:
        # Outsider view — count only, no names
        member_count_rows = await db.fetchall(
            "SELECT COUNT(*) AS n FROM org_memberships WHERE org_id = ?",
            (org_id,),
        )
        n = int(member_count_rows[0]["n"]) if member_count_rows else 0
        lines.append(f"Citizens:        {n} members")

    return lines



# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Taxation
# ─────────────────────────────────────────────────────────────────────────────


# ── Phase 4: Mayor / Founder tax commands ────────────────────────────────────

async def set_city_tax_rate(
    db, char: dict, rate: float,
) -> tuple[bool, str]:
    """Set the Mayor's chosen tax rate (0.0 – rate_cap).

    Mayor or Founder only. The rate is bounded by the city's
    rate_cap (Founder-set). Per design §4.2 + §5.4: 0% floor, 10%
    absolute ceiling (the rate_cap further constrains within that).

    Returns (ok, message). On success, message describes the new rate
    and the active cap.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, (
            "Only the Mayor or Founder can set the city tax rate."
        )

    try:
        rate = float(rate)
    except (TypeError, ValueError):
        return False, (
            f"Invalid tax rate: {rate!r}. "
            f"Use a decimal between 0 and {city.get('rate_cap', MAX_TAX_RATE)}."
        )

    if rate < MIN_TAX_RATE:
        return False, f"Tax rate must be at least {MIN_TAX_RATE * 100:.0f}%."

    cap = float(city.get("rate_cap") or DEFAULT_RATE_CAP)
    if rate > cap + 1e-9:  # tiny epsilon for float-comparison sanity
        return False, (
            f"Tax rate {rate * 100:.1f}% exceeds your city's rate cap "
            f"({cap * 100:.1f}%). The Founder controls the cap; "
            f"see `+city tax ratecap` (Founder-only)."
        )

    # Defense in depth: even with a corrupt cap, never exceed the
    # absolute MAX_TAX_RATE ceiling.
    if rate > MAX_TAX_RATE + 1e-9:
        return False, (
            f"Tax rate {rate * 100:.1f}% exceeds the absolute "
            f"ceiling of {MAX_TAX_RATE * 100:.0f}%."
        )

    await db.execute(
        "UPDATE player_cities SET tax_rate = ? WHERE id = ?",
        (rate, int(city["id"])),
    )
    await db.commit()
    log.info(
        "[player_cities] tax rate set to %.4f on city=%s by char=%s",
        rate, city["name"], char.get("name"),
    )
    return True, (
        f"Tax rate for {city['name']} set to {rate * 100:.1f}% "
        f"(cap: {cap * 100:.1f}%)."
    )


async def set_city_rate_cap(
    db, char: dict, cap: float,
) -> tuple[bool, str]:
    """Set the Founder-controlled rate-cap (0 – MAX_TAX_RATE).

    Founder only. Per design §4.3: the Founder bounds the Mayor's
    tax-set authority via this cap. If the current tax_rate is
    above the new cap, the tax_rate is clamped down to match the
    new cap (so a Founder can't paint a Mayor into a corner where
    the rate exceeds the cap).

    Returns (ok, message). On clamp, message names the clamp.
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not await _is_founder(city, char):
        return False, (
            "Only the city's Founder can set the rate cap."
        )

    try:
        cap = float(cap)
    except (TypeError, ValueError):
        return False, (
            f"Invalid rate cap: {cap!r}. "
            f"Use a decimal between 0 and {MAX_TAX_RATE}."
        )

    if cap < MIN_TAX_RATE:
        return False, f"Rate cap must be at least {MIN_TAX_RATE * 100:.0f}%."
    if cap > MAX_TAX_RATE + 1e-9:
        return False, (
            f"Rate cap {cap * 100:.1f}% exceeds the absolute ceiling "
            f"of {MAX_TAX_RATE * 100:.0f}% (design §5.4)."
        )

    # Clamp current rate to new cap if necessary
    current_rate = float(city.get("tax_rate") or 0.0)
    clamp_msg = ""
    if current_rate > cap:
        await db.execute(
            "UPDATE player_cities SET tax_rate = ?, rate_cap = ? "
            "WHERE id = ?",
            (cap, cap, int(city["id"])),
        )
        clamp_msg = (
            f" (Tax rate clamped from {current_rate * 100:.1f}% to "
            f"{cap * 100:.1f}%.)"
        )
    else:
        await db.execute(
            "UPDATE player_cities SET rate_cap = ? WHERE id = ?",
            (cap, int(city["id"])),
        )
    await db.commit()
    log.info(
        "[player_cities] rate cap set to %.4f on city=%s by char=%s%s",
        cap, city["name"], char.get("name"),
        " (rate clamped)" if clamp_msg else "",
    )
    return True, (
        f"Rate cap for {city['name']} set to {cap * 100:.1f}%."
        f"{clamp_msg}"
    )


# ── Phase 4: Collection chokepoint ───────────────────────────────────────────

async def apply_city_tax(
    db, room_id: int, gross_amount: int,
) -> tuple[int, Optional[int], Optional[str]]:
    """Apply a city tax to a gross transaction amount.

    The single chokepoint for ALL Phase 4 tax collection sites
    (vendor droid sales, bounty postings, sabacc rake, NPC vendor
    bargaining). Callers compute their gross amount and pass it
    here; this function:

      1. Looks up the city for the room (returns 0/None/None if
         the room is not in any city — no tax)
      2. Computes city_take = floor(gross * tax_rate)
      3. Credits the org treasury with city_take
      4. Updates player_cities.revenue_total + revenue_week
      5. Returns (city_take, city_id, city_name) so the caller
         can render an attribution line if desired

    Per design §5.3: the tax is carved out of the gross — the
    caller should subtract city_take from its own internal
    accounting (e.g., vendor droid escrow) so the net effect on
    the player's wallet is unchanged. The city's slice comes from
    the system's slice, not the player's.

    Returns:
        (0, None, None) when no tax applies (no city / rate=0)
        (take, city_id, city_name) otherwise; take is always >= 0
    """
    if gross_amount <= 0:
        return 0, None, None

    city = await get_city_for_room(db, int(room_id))
    if not city:
        return 0, None, None

    # Phase 6 (May 23 2026) gate: per design §8.2 week 3, tax
    # collection ceases for cities in grace stage week3 or later.
    # Return zero tax with the city attribution preserved (so the
    # caller can still render "city X is here but not collecting"
    # if it wants to). Same shape as a rate-0.0 city.
    if is_tax_collection_disabled(city):
        return 0, int(city["id"]), city["name"]

    rate = float(city.get("tax_rate") or 0.0)
    if rate <= 0.0:
        return 0, int(city["id"]), city["name"]

    take = int(gross_amount * rate)
    if take <= 0:
        # Avoid silent zero-take when rate is non-zero — log it but
        # don't fail. This happens at very small gross amounts.
        return 0, int(city["id"]), city["name"]

    # Credit org treasury
    org_id = int(city.get("org_id") or 0)
    if org_id:
        await db.adjust_org_treasury(org_id, take)

    # Update revenue tracking
    await db.execute(
        "UPDATE player_cities "
        "SET revenue_total = revenue_total + ?, "
        "    revenue_week = revenue_week + ? "
        "WHERE id = ?",
        (take, take, int(city["id"])),
    )
    await db.commit()
    log.info(
        "[player_cities] city tax: %d cr → '%s' (rate=%.4f, gross=%d)",
        take, city["name"], rate, gross_amount,
    )
    return take, int(city["id"]), city["name"]


# ── Phase 4: Weekly revenue rollover (tick handler) ──────────────────────────

async def tick_city_revenue_rollover(db) -> None:
    """Reset revenue_week for cities whose week has elapsed.

    Called by server.tick_handlers_economy.city_revenue_rollover_tick
    at interval=CITY_REVENUE_ROLLOVER_SECONDS (1 week). Per design
    §5.3: the weekly figure resets so Mayors can see week-over-week
    trends; revenue_total is cumulative and never resets.

    Each city's week boundary is per-city (week_start_ts), so
    rollovers spread across the calendar rather than thundering
    on one moment.
    """
    now = time.time()
    threshold = now - CITY_REVENUE_ROLLOVER_SECONDS
    rows = await db.fetchall(
        "SELECT id, name FROM player_cities "
        "WHERE state != 'dissolved' AND week_start_ts <= ?",
        (threshold,),
    )
    for row in rows:
        await db.execute(
            "UPDATE player_cities "
            "SET revenue_week = 0, week_start_ts = ? "
            "WHERE id = ?",
            (now, int(row["id"])),
        )
        log.info(
            "[player_cities] weekly revenue rollover: city=%s",
            row["name"],
        )
    if rows:
        await db.commit()


# ── Phase 4: tax view rendering ──────────────────────────────────────────────

def format_city_tax_view(city: dict) -> list[str]:
    """Render +city tax view lines.

    Returns a list of plain-text lines (no terminal newlines). The
    parser layer wraps these with ANSI styling. Per design §5.3
    surfaces revenue_total and revenue_week so the Mayor can see
    week-over-week trends.
    """
    if not city:
        return ["No city to display."]

    rate = float(city.get("tax_rate") or 0.0)
    cap = float(city.get("rate_cap") or DEFAULT_RATE_CAP)
    rev_total = int(city.get("revenue_total") or 0)
    rev_week = int(city.get("revenue_week") or 0)
    week_start = float(city.get("week_start_ts") or 0.0)

    days_into_week = 0
    if week_start > 0:
        elapsed = max(0.0, time.time() - week_start)
        days_into_week = int(elapsed // (24 * 60 * 60))

    return [
        f"=== Tax for {city['name']} ===",
        f"Current rate:    {rate * 100:.1f}%",
        f"Rate cap:        {cap * 100:.1f}%  (Founder-controlled)",
        f"Revenue (week):  {rev_week:,} cr  ({days_into_week} days "
        f"into this week)",
        f"Revenue (total): {rev_total:,} cr  (since founding)",
    ]



# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: Citizen benefits
# ─────────────────────────────────────────────────────────────────────────────

# Per design v1.2 §6.4: "+city home" cooldown.
CITY_HOME_COOLDOWN_SECONDS = 60 * 60  # 1 hour

# Per design v1.2 §6.3: max fraction of NON-HQ rooms that can be
# citizen-only. HQ rooms count as citizen-only by default and are
# exempt from this cap (Phase 5 May 22 2026 design call #2).
CITIZEN_ONLY_MAX_FRACTION = 0.30


# ── Phase 5: Read seams (citizenship + rest bonus) ──────────────────────────

async def is_citizen(db, char: dict, city: dict) -> bool:
    """True iff char's role in city is founder | mayor | citizen.

    Convenience wrapper around get_city_role (Phase 3). Guests and
    banished users are NOT citizens. Banishment supersedes
    everything else.
    """
    if not char or not city:
        return False
    role = await get_city_role(db, city, char)
    return role in ("founder", "mayor", "citizen")


async def is_rest_bonus_room(
    db, char: dict, room_id: int,
) -> bool:
    """True iff this room qualifies for the citizen rest bonus.

    Per design §6.1: any city room (HQ + expansion) counts as
    "home" for a citizen, regardless of whether the citizen has
    personal housing. This is the read seam — the rest bonus
    mechanic itself is a separate system feature (not in Phase 5;
    see Phase 5 May 22 2026 design call #4).

    Returns False if the room is not in any city, or if char is
    not a citizen of that city.
    """
    if not char:
        return False
    city = await get_city_for_room(db, int(room_id))
    if not city:
        return False
    return await is_citizen(db, char, city)


# ── Phase 5: Movement gate (citizen-only rooms) ─────────────────────────────

async def can_enter_city_room(
    db, char: dict, room_id: int,
) -> tuple[bool, str]:
    """Phase 5 §6.3 movement gate.

    Returns (False, reason) iff:
      - the room is in a city AND
      - the room is flagged citizen_only AND
      - char is NOT a citizen of that city (banished, guest, or
        outsider all fail)

    Otherwise returns (True, ""). This is the gate consumed by
    parser.builtin_commands.MoveCommand._check_exit_gates.

    Failure-soft on internal errors: if the city lookup raises,
    returns (True, "") and logs. Better to leak occasional access
    than to silently break every movement on a transient DB hiccup.
    """
    try:
        city = await get_city_for_room(db, int(room_id))
        if not city:
            return True, ""  # not in any city — open

        # Is this room flagged citizen_only?
        rows = await db.fetchall(
            "SELECT citizen_only FROM player_city_rooms "
            "WHERE city_id = ? AND room_id = ?",
            (int(city["id"]), int(room_id)),
        )
        if not rows:
            return True, ""  # paranoia — city exists but room not in it
        if not int(rows[0]["citizen_only"]):
            return True, ""  # not citizen-only — open

        # Citizen-only room. Check membership.
        if await is_citizen(db, char, city):
            return True, ""

        return False, (
            f"That room in {city['name']} is restricted to "
            f"citizens of the city's owning organization."
        )
    except Exception:
        log.warning(
            "[player_cities] can_enter_city_room failed; "
            "failing open",
            exc_info=True,
        )
        return True, ""


# ── Phase 5: +city home teleport ────────────────────────────────────────────

def _get_last_city_home(char: dict) -> float:
    """Read last_city_home timestamp from attributes JSON."""
    try:
        attrs = char.get("attributes") or "{}"
        if isinstance(attrs, str):
            attrs = json.loads(attrs) if attrs else {}
        return float(attrs.get("last_city_home", 0))
    except Exception:
        return 0.0


def _set_last_city_home(char: dict, timestamp: float) -> str:
    """Set last_city_home in attributes JSON, return updated string.

    Mirrors the existing _set_last_sabacc pattern in
    parser/sabacc_commands.py — durable across logout per
    Phase 5 May 22 2026 design call #3.
    """
    attrs = char.get("attributes") or "{}"
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs) if attrs else {}
        except Exception:
            attrs = {}
    attrs["last_city_home"] = float(timestamp)
    return json.dumps(attrs)


async def get_city_entry_room_id(db, city: dict) -> Optional[int]:
    """Resolve a city to its HQ entry room (the 'doorstep').

    Per Phase 2 invariant the entry_room is NOT in
    player_city_rooms — it's the outward-facing room players walk
    INTO to reach the city interior. Stored on the housing row
    (player_housing.entry_room_id) linked via player_cities.hq_id.
    """
    if not city:
        return None
    hq_id = city.get("hq_id")
    if not hq_id:
        return None
    rows = await db.fetchall(
        "SELECT entry_room_id FROM player_housing WHERE id = ?",
        (int(hq_id),),
    )
    if not rows or not rows[0]["entry_room_id"]:
        return None
    return int(rows[0]["entry_room_id"])


async def can_use_city_home(
    db, char: dict,
) -> tuple[bool, Optional[int], str]:
    """Phase 5 §6.4 teleport gate.

    Returns (ok, dest_room_id, reason).

    Checks (in order):
      1. char is a member of an org (faction_id != independent)
      2. The org has an active city
      3. char is a citizen of that city (founder | mayor | citizen)
      4. char is not in combat
      5. char is not in space (no ship interior, no docked-on-ship)
      6. char is currently in the same zone as the city
         (Phase 5 May 22 2026 design call: "same planet" is
         implemented as "same zone" because zones don't carry
         an explicit planet attribute yet)
      7. Cooldown (CITY_HOME_COOLDOWN_SECONDS = 1 hour) elapsed
    """
    if not char:
        return False, None, "No character context."

    # 1-3: org + city + citizenship
    faction = char.get("faction_id") or "independent"
    if faction == "independent":
        return False, None, "You are not a member of any organization."
    org = await db.get_organization(faction)
    if not org:
        return False, None, f"Organization '{faction}' could not be found."
    city = await get_city_by_org(db, int(org["id"]))
    if not city:
        return False, None, "Your organization has no active city."
    if not await is_citizen(db, char, city):
        return False, None, (
            "You are not a citizen of your organization's city "
            "(possibly banished)."
        )

    # 4: not in combat. Combat state lives on character.attributes
    # JSON or via the combat-engine. Cheap read: char.attributes
    # carries an in_combat flag in this engine.
    try:
        attrs_raw = char.get("attributes") or "{}"
        attrs = (
            json.loads(attrs_raw) if isinstance(attrs_raw, str)
            else attrs_raw
        ) or {}
        if attrs.get("in_combat") or attrs.get("combat_state"):
            return False, None, "You cannot teleport while in combat."
    except Exception:
        # Failure-soft on attribute parse — fall through.
        log.warning(
            "[player_cities] can_use_city_home combat-check parse failed",
            exc_info=True,
        )

    # 5: not in space. A character "in space" lives on a ship's
    # bridge or interior — those rooms have NULL zone_id or are
    # tagged. Cheap proxy: char's room has a zone, and that zone
    # exists. If room has no zone, treat as space.
    char_room_id = char.get("room_id")
    if not char_room_id:
        return False, None, "You have no current location."
    char_room = await db.get_room(int(char_room_id))
    if not char_room:
        return False, None, "Your current location is invalid."
    char_zone_id = char_room.get("zone_id")
    if not char_zone_id:
        return False, None, (
            "You cannot use +city home from a ship or space. "
            "Land first."
        )

    # 6: same zone as the city (Phase 5 design call: same-zone
    # instead of same-planet — see module docstring).
    city_zone_id = city.get("zone_id")
    if not city_zone_id:
        return False, None, "Your city's location is invalid."
    if int(char_zone_id) != int(city_zone_id):
        return False, None, (
            f"You must be in the same zone as {city['name']} to "
            f"teleport home. (Phase 5 implementation: same-zone "
            f"only; cross-zone teleport is a future enhancement.)"
        )

    # 7: cooldown
    now = time.time()
    last = _get_last_city_home(char)
    if last and (now - last) < CITY_HOME_COOLDOWN_SECONDS:
        remaining = int(CITY_HOME_COOLDOWN_SECONDS - (now - last))
        m, s = divmod(remaining, 60)
        return False, None, (
            f"You used +city home recently. Try again in "
            f"{m}m {s}s."
        )

    # Resolve destination
    dest = await get_city_entry_room_id(db, city)
    if not dest:
        return False, None, (
            f"Could not resolve {city['name']}'s entry room."
        )
    return True, dest, ""


async def record_city_home_use(db, char: dict) -> None:
    """Stamp the cooldown after a successful +city home teleport.

    Persists to characters.attributes JSON via the
    _set_last_city_home helper. Survives logout per Phase 5
    May 22 2026 design call #3.
    """
    if not char or not char.get("id"):
        return
    now = time.time()
    new_attrs = _set_last_city_home(char, now)
    char["attributes"] = new_attrs
    await db.save_character(int(char["id"]), attributes=new_attrs)


# ── Phase 6: Admin tools ─────────────────────────────────────────────────────
#
# Per design v1.2 §11.5 + §13 Phase 6 ("admin tools" line of Phase 6
# polish). These helpers operate by city NAME / character NAME rather
# than from the actor's org/city (which is the normal player flow via
# `_resolve_actor_city`). Admin actions bypass auth checks but still
# cascade-clean any city-scoped tables they touch.
#
# Discipline:
#   - admin helpers return (ok, message) for parity with the Phase 1-5
#     command helpers.
#   - they NEVER consume founder/mayor auth (the parser layer enforces
#     the AccessLevel.ADMIN gate; the engine helpers trust the parser).
#   - they fail loudly on missing data (no fail-soft pass-through here;
#     admin commands should not silently no-op).
#   - admin_dissolve does NOT refund the treasury — admin moderation
#     is not the same as a founder voluntarily winding down a city.
#     If a refund is desired the admin can call adjust_org_treasury
#     separately.


async def list_all_cities(
    db, *, include_dissolved: bool = False,
) -> list[dict]:
    """Return cities for admin `@city list` view.

    By default returns only active cities (state != 'dissolved').
    When `include_dissolved=True`, returns all rows including
    dissolved ones (for moderation auditing). Sorted oldest-first.
    """
    if include_dissolved:
        rows = await db.fetchall(
            "SELECT * FROM player_cities ORDER BY founded_at ASC"
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM player_cities "
            "WHERE state != 'dissolved' "
            "ORDER BY founded_at ASC"
        )
    return [dict(r) for r in rows]


async def admin_dissolve_city(
    db, name: str, *, admin_name: str = "admin",
) -> tuple[bool, str]:
    """Force-dissolve a city as an admin moderation action.

    Differs from the player-facing `dissolve_city`:
      - no founder/leader auth check (admin gate at parser layer)
      - NO treasury refund (this is moderation, not voluntary
        winding-down)
      - still cascade-cleans player_city_rooms, banishments,
        guests, and marks state='dissolved' (row kept for audit)

    Returns (ok, message). Idempotent failure: dissolving a
    non-existent or already-dissolved city is a clear no-op.
    """
    ok, validated_name = validate_city_name(name)
    if not ok:
        return False, validated_name
    name = validated_name

    city = await get_city_by_name(db, name)
    if not city:
        return False, f"No active city named '{name}'."

    city_id = int(city["id"])
    await db.execute(
        "DELETE FROM player_city_rooms WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "DELETE FROM player_city_banishments WHERE city_id = ?",
        (city_id,),
    )
    await db.execute(
        "DELETE FROM player_city_guests WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "UPDATE player_cities SET state = 'dissolved' WHERE id = ?",
        (city_id,),
    )
    await db.commit()

    log.info(
        "[player_cities] ADMIN dissolve: city='%s' (id=%d) by %s",
        name, city_id, admin_name,
    )
    return True, (
        f"City '{name}' force-dissolved by admin. "
        f"No treasury refund issued."
    )


async def admin_unbanish(
    db, city_name: str, target_name: str,
    *, admin_name: str = "admin",
) -> tuple[bool, str]:
    """Lift a banishment by admin moderation. Looks up the city
    by name and the target by character name.

    Returns (ok, message). Fails loudly when either lookup misses
    or no banishment is on file (idempotent no-op signal so the
    admin can verify the state).
    """
    city = await get_city_by_name(db, city_name)
    if not city:
        return False, f"No active city named '{city_name}'."

    target = await db.get_character_by_name(target_name)
    if not target:
        return False, f"No character named '{target_name}'."

    city_id = int(city["id"])
    target_id = int(target["id"])

    rows = await db.fetchall(
        "SELECT 1 FROM player_city_banishments "
        "WHERE city_id = ? AND char_id = ?",
        (city_id, target_id),
    )
    if not rows:
        return False, (
            f"{target['name']} is not banished from {city['name']}."
        )

    await db.execute(
        "DELETE FROM player_city_banishments "
        "WHERE city_id = ? AND char_id = ?",
        (city_id, target_id),
    )
    await db.commit()
    log.info(
        "[player_cities] ADMIN void-banish: city='%s' target='%s' by %s",
        city["name"], target["name"], admin_name,
    )
    return True, (
        f"Admin lifted banishment of {target['name']} "
        f"from {city['name']}."
    )


async def admin_set_rate_cap(
    db, city_name: str, cap: float,
    *, admin_name: str = "admin",
) -> tuple[bool, str]:
    """Admin override of the Founder-controlled rate cap.

    Parallel to `set_city_rate_cap` but skips the founder-auth
    check. Still validates the cap is in [MIN_TAX_RATE, MAX_TAX_RATE]
    and still clamps the current tax_rate down if it exceeds the
    new cap.

    Returns (ok, message). On clamp, message names the clamp.
    """
    city = await get_city_by_name(db, city_name)
    if not city:
        return False, f"No active city named '{city_name}'."

    try:
        cap = float(cap)
    except (TypeError, ValueError):
        return False, (
            f"Invalid rate cap: {cap!r}. "
            f"Use a decimal between 0 and {MAX_TAX_RATE}."
        )

    if cap < MIN_TAX_RATE:
        return False, (
            f"Rate cap must be at least {MIN_TAX_RATE * 100:.0f}%."
        )
    if cap > MAX_TAX_RATE + 1e-9:
        return False, (
            f"Rate cap {cap * 100:.1f}% exceeds the absolute ceiling "
            f"of {MAX_TAX_RATE * 100:.0f}% (design §5.4)."
        )

    current_rate = float(city.get("tax_rate") or 0.0)
    clamp_msg = ""
    if current_rate > cap:
        await db.execute(
            "UPDATE player_cities SET tax_rate = ?, rate_cap = ? "
            "WHERE id = ?",
            (cap, cap, int(city["id"])),
        )
        clamp_msg = (
            f" (Tax rate clamped from {current_rate * 100:.1f}% to "
            f"{cap * 100:.1f}%.)"
        )
    else:
        await db.execute(
            "UPDATE player_cities SET rate_cap = ? WHERE id = ?",
            (cap, int(city["id"])),
        )
    await db.commit()
    log.info(
        "[player_cities] ADMIN rate cap set: city='%s' cap=%.4f "
        "by %s%s", city["name"], cap, admin_name,
        " (rate clamped)" if clamp_msg else "",
    )
    return True, (
        f"Admin set rate cap for {city['name']} to "
        f"{cap * 100:.1f}%.{clamp_msg}"
    )


async def admin_rename_city(
    db, old_name: str, new_name: str,
    *, admin_name: str = "admin",
) -> tuple[bool, str]:
    """Admin rename of a city.

    Validates the NEW name via `validate_city_name` (length, charset,
    reserved-list). Checks uniqueness via the active-name partial
    index (an active city with the new name already existing is a
    block). Old name becomes reusable immediately because the
    rename is an UPDATE, not an INSERT.

    Returns (ok, message).
    """
    city = await get_city_by_name(db, old_name)
    if not city:
        return False, f"No active city named '{old_name}'."

    ok, validated_new = validate_city_name(new_name)
    if not ok:
        return False, validated_new
    new_name = validated_new

    # No-op rename: same name (case-insensitive) is a clear signal
    if (city.get("name_lower") or "").lower() == new_name.lower():
        return False, (
            f"City is already named '{city['name']}' "
            f"(case-insensitive match)."
        )

    # Active-name collision check (the partial unique index will
    # also catch this, but checking up front gives a friendlier msg)
    conflict = await get_city_by_name(db, new_name)
    if conflict:
        return False, (
            f"Another active city is already named '{new_name}'."
        )

    await db.execute(
        "UPDATE player_cities SET name = ?, name_lower = ? "
        "WHERE id = ?",
        (new_name, new_name.lower(), int(city["id"])),
    )
    await db.commit()
    log.info(
        "[player_cities] ADMIN rename: '%s' -> '%s' (city_id=%d) by %s",
        old_name, new_name, int(city["id"]), admin_name,
    )
    return True, (
        f"City '{old_name}' renamed to '{new_name}'."
    )


async def format_city_inspect(db, city: dict) -> list[str]:
    """Detailed admin inspect view of a single city. Returns a
    list of pre-formatted lines suitable for line-by-line sending.

    Includes:
      - basic identity (name, id, org, hq tier, founded_at, state)
      - mayor and founder names (resolved via db lookup)
      - taxation (rate, cap, revenue totals)
      - room count (center + expansion + citizen-only flags)
      - active banishments (count + most recent 5)
      - guest list (count + most recent 5)

    Per design §11.5 `@city inspect <name>`.
    """
    lines: list[str] = []
    city_id = int(city["id"])

    # Identity
    state = city.get("state", "active")
    founded = float(city.get("founded_at") or 0.0)
    founded_str = (
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(founded))
        if founded else "unknown"
    )
    org_id = city.get("org_id")
    org_str = f"org_id={org_id}"
    try:
        if hasattr(db, "get_organization_by_id"):
            org = await db.get_organization_by_id(int(org_id))
            if org and org.get("name"):
                org_str = f"{org['name']} ({org_id})"
    except Exception:
        # Fail-soft: missing org doesn't break the inspect view
        log.debug("[player_cities] inspect org lookup failed", exc_info=True)

    lines.append(
        f"== City Inspect: {city.get('name')} =="
    )
    lines.append(
        f"  id={city_id}  state={state}  hq_tier={city.get('hq_tier')}"
    )
    lines.append(
        f"  org: {org_str}  founded: {founded_str} UTC"
    )

    # Founder + Mayor names
    fid = city.get("founder_id")
    mid = city.get("mayor_id")
    founder_name = f"id={fid}"
    mayor_name = f"id={mid}"
    try:
        if fid:
            f_row = await db.get_character(int(fid))
            if f_row and f_row.get("name"):
                founder_name = f_row["name"]
        if mid:
            m_row = await db.get_character(int(mid))
            if m_row and m_row.get("name"):
                mayor_name = m_row["name"]
    except Exception:
        log.debug("[player_cities] inspect char lookup failed", exc_info=True)
    lines.append(f"  founder: {founder_name}  mayor: {mayor_name}")

    # Taxation
    rate = float(city.get("tax_rate") or 0.0)
    cap = float(city.get("rate_cap") or 0.0)
    rev_total = int(city.get("revenue_total") or 0)
    rev_week = int(city.get("revenue_week") or 0)
    lines.append(
        f"  tax: {rate * 100:.1f}%  cap: {cap * 100:.1f}%  "
        f"revenue: {rev_total:,} total / {rev_week:,} this week"
    )

    # Rooms
    all_rooms = await list_city_room_ids(db, city_id)
    citizen_rooms = await list_citizen_room_ids(db, city_id)
    center_rows = await db.fetchall(
        "SELECT COUNT(*) AS n FROM player_city_rooms "
        "WHERE city_id = ? AND is_center = 1",
        (city_id,),
    )
    center_n = int(center_rows[0]["n"]) if center_rows else 0
    expansion_n = max(0, len(all_rooms) - center_n)
    lines.append(
        f"  rooms: {len(all_rooms)} total "
        f"({center_n} HQ / {expansion_n} expansion) "
        f"— {len(citizen_rooms)} citizen-only"
    )

    # Banishments
    bans = await list_active_banishments(db, city_id)
    lines.append(f"  active banishments: {len(bans)}")
    for b in bans[:5]:
        cid = int(b.get("char_id") or 0)
        until = float(b.get("until") or 0.0)
        until_str = (
            time.strftime("%Y-%m-%d %H:%M", time.gmtime(until))
            if until else "unknown"
        )
        bname = f"id={cid}"
        try:
            crow = await db.get_character(cid)
            if crow and crow.get("name"):
                bname = crow["name"]
        except Exception:
            log.debug(
                "[player_cities] inspect: banishment name lookup "
                "failed for char %s (best-effort)", cid, exc_info=True,
            )
        lines.append(f"    - {bname} until {until_str} UTC")

    # Guests
    guest_ids = await list_guests(db, city_id)
    lines.append(f"  guests: {len(guest_ids)}")
    for gid in guest_ids[:5]:
        gname = f"id={gid}"
        try:
            grow = await db.get_character(int(gid))
            if grow and grow.get("name"):
                gname = grow["name"]
        except Exception:
            log.debug(
                "[player_cities] inspect: guest name lookup "
                "failed for char %s (best-effort)", gid, exc_info=True,
            )
        lines.append(f"    - {gname}")

    return lines


# ── Phase 6 (May 23 2026): Maintenance + grace state machine ────────────────
#
# Per design v1.2 §8.1 (maintenance costs) and §8.2 (treasury
# depletion behavior / 4-week grace period).
#
# State derivation (no new state enum):
#   - city['grace_started_at'] == 0  → city is healthy
#   - city['grace_started_at'] > 0   → city is in grace; week
#                                       computed from (now - that)
#
# Stage thresholds (per design §8.2):
#   week 1 (t >= 0)    → guards stop functioning (Phase 7 only)
#   week 2 (t >= 7d)   → citizen-only flags cleared and locked
#   week 3 (t >= 14d)  → tax collection ceases
#   week 4 (t >= 21d)  → final warning (still functional)
#   end of 4 (t >= 28d)→ auto-dissolve
#
# Substrate decisions:
#   1. **HQ base maintenance is NOT charged here.** It's already
#      charged by engine.housing.tick_hq_maintenance for the
#      underlying HQ. Charging again would be a double-tax.
#   2. **Guard maintenance is constant-zero in Phase 6.** No guards
#      exist yet (Phase 7). The constant is set up now so the
#      Phase 7 drop only adds the count query.
#   3. **Tax-rate stays settable in grace.** The gate is at
#      collection time (apply_city_tax). Mayor can adjust the
#      rate in anticipation of recovery, and the change takes
#      effect on the next collection that's not gated.
#   4. **Mail is sent on grace transitions only**, not on every
#      tick. Mail-fatigue would dilute the signal.
#   5. **Mail send is best-effort.** The maintenance state change
#      MUST proceed even if the courtesy mail fails to send (the
#      send_system_mail substrate is already fail-soft).


def is_in_grace(city: dict) -> bool:
    """True iff this city is in the maintenance-grace state.

    Derived from the `grace_started_at` column (provisioned in
    Phase 1 but never written until Phase 6). A non-dissolved city
    with grace_started_at > 0 is in grace.
    """
    if not city:
        return False
    if (city.get("state") or "active") == "dissolved":
        return False
    return float(city.get("grace_started_at") or 0.0) > 0.0


def grace_stage(city: dict, now: Optional[float] = None) -> str:
    """Return a discrete grace stage label for a city.

    Returns one of:
      - "active"    : not in grace
      - "week1"     : in grace, t < 7d (guards stop — Phase 7)
      - "week2"     : 7d <= t < 14d   (citizen-only flags off)
      - "week3"     : 14d <= t < 21d  (tax collection ceases)
      - "week4"     : 21d <= t < 28d  (final warning)
      - "expired"   : t >= 28d        (should be dissolved by tick)
      - "dissolved" : city.state == 'dissolved'
    """
    if not city:
        return "active"
    if (city.get("state") or "active") == "dissolved":
        return "dissolved"
    started = float(city.get("grace_started_at") or 0.0)
    if started <= 0.0:
        return "active"
    t_now = float(now) if now is not None else time.time()
    elapsed = t_now - started
    if elapsed < CITY_GRACE_FLAGS_OFF_AT_SECONDS:
        return "week1"
    if elapsed < CITY_GRACE_TAX_OFF_AT_SECONDS:
        return "week2"
    if elapsed < CITY_GRACE_FINAL_WARNING_AT_SECONDS:
        return "week3"
    if elapsed < CITY_GRACE_DISSOLVE_AT_SECONDS:
        return "week4"
    return "expired"


def is_tax_collection_disabled(city: dict, now: Optional[float] = None) -> bool:
    """Per design §8.2 week 3: tax collection ceases.

    True iff city is in grace stage week3, week4, or expired.
    Used by apply_city_tax to short-circuit collection.
    """
    return grace_stage(city, now) in ("week3", "week4", "expired")


def is_citizen_flagging_disabled(city: dict, now: Optional[float] = None) -> bool:
    """Per design §8.2 week 2: citizen-only flags removed; Mayor
    can no longer apply new flags.

    True iff city is in grace stage week2 or later. Used by
    set_room_citizen_only to refuse SETTING the flag (clearing
    is always allowed; the maintenance tick is what bulk-clears).
    """
    return grace_stage(city, now) in ("week2", "week3", "week4", "expired")


async def compute_city_maintenance_cost(db, city_id: int) -> int:
    """Per design §8.1: weekly maintenance cost for a city.

    Components:
      - HQ base: NOT included here (charged by housing tick)
      - Per expansion room: CITY_EXPANSION_MAINT_PER_WEEK_CR each
      - Per NPC guard: CITY_GUARD_MAINT_PER_WEEK_CR each (Phase 7)

    Returns total in credits.
    """
    # Count non-HQ (expansion) rooms
    rows = await db.fetchall(
        "SELECT COUNT(*) AS n FROM player_city_rooms "
        "WHERE city_id = ? AND is_center = 0",
        (int(city_id),),
    )
    n_expansion = int(rows[0]["n"]) if rows else 0
    expansion_cost = n_expansion * CITY_EXPANSION_MAINT_PER_WEEK_CR
    # Phase 7: count assigned city guards. count_city_guards is the
    # single-query helper that the parser also uses for `+city
    # guards` display, so cost computation and player-facing display
    # always agree on the count.
    n_guards = await count_city_guards(db, int(city_id))
    guard_cost = n_guards * CITY_GUARD_MAINT_PER_WEEK_CR
    return expansion_cost + guard_cost


async def _get_org_treasury(db, org_id: int) -> int:
    """Look up an org's current treasury balance. Returns 0 on
    lookup failure (fail-soft so the maint tick doesn't crash an
    entire pass over an unmodeled org row)."""
    try:
        rows = await db.fetchall(
            "SELECT treasury FROM organizations WHERE id = ?",
            (int(org_id),),
        )
        if rows:
            return int(rows[0]["treasury"] or 0)
    except Exception:
        log.warning(
            "[player_cities] _get_org_treasury(%r) failed",
            org_id, exc_info=True,
        )
    return 0


async def _bulk_clear_citizen_flags(db, city_id: int) -> int:
    """Per design §8.2 week 2: when a city advances into week 2,
    all citizen_only flags are cleared at once. Returns count
    cleared.

    Idempotent: if no flags are set, returns 0 cleanly. Does NOT
    touch HQ-center rooms (is_center=1 doesn't carry citizen_only
    semantics; the design's "citizen-only HQ rooms by default"
    is implicit, not stored).
    """
    rows = await db.fetchall(
        "SELECT COUNT(*) AS n FROM player_city_rooms "
        "WHERE city_id = ? AND citizen_only = 1 AND is_center = 0",
        (int(city_id),),
    )
    n = int(rows[0]["n"]) if rows else 0
    if n > 0:
        await db.execute(
            "UPDATE player_city_rooms SET citizen_only = 0 "
            "WHERE city_id = ? AND is_center = 0",
            (int(city_id),),
        )
    return n


async def _notify_mayor_and_founder(
    db, city: dict, *, subject: str, body: str,
) -> None:
    """Best-effort: mail the city's Mayor and Founder. Failure is
    logged but does NOT block the state change. Mayor == Founder
    is the common case; the second send is suppressed.
    """
    from engine.mail_utils import send_system_mail

    sent_to = set()
    for key in ("mayor_id", "founder_id"):
        cid = city.get(key)
        if not cid:
            continue
        cid = int(cid)
        if cid in sent_to:
            continue
        sent_to.add(cid)
        try:
            await send_system_mail(
                db, recipient_id=cid, subject=subject, body=body,
            )
        except Exception:
            log.warning(
                "[player_cities] grace mail send failed "
                "(city=%s recipient=%s)",
                city.get("name"), cid, exc_info=True,
            )


async def tick_city_maintenance(db, session_mgr=None) -> dict:
    """Weekly city maintenance + grace-state-machine tick.

    Per design §8.1 and §8.2. Called by
    server.tick_handlers_economy.city_maintenance_tick at interval
    CITY_MAINTENANCE_TICK_INTERVAL_SECONDS (1 week). Per-city
    check uses each city's `maint_paid_until` so cadence is
    per-city, not global.

    Steps per city (state != 'dissolved' and now >= maint_paid_until):
      1. compute cost
      2. read treasury
      3. if treasury >= cost: debit; clear grace if was set; bump
         maint_paid_until by ONE_WEEK_SECONDS
      4. else: enter grace (if not already in); check elapsed time
         and advance/clear citizen flags / dissolve as appropriate;
         do NOT debit; do NOT bump maint_paid_until (so next tick
         re-checks)

    Returns a dict with summary counters (useful for tests +
    observability):
      {
        "checked": int,        # cities the tick examined
        "paid": int,           # cities that paid this tick
        "entered_grace": int,
        "advanced_in_grace": int,  # stage transitions
        "recovered": int,      # cities that exited grace
        "dissolved": int,      # cities auto-dissolved
      }

    The session_mgr arg is unused at Phase 6 but accepted to
    match the TickContext convention; Phase 7 may use it (e.g.
    poking online citizens with a "grace started" notification).
    """
    now = time.time()
    summary = {
        "checked": 0, "paid": 0, "entered_grace": 0,
        "advanced_in_grace": 0, "recovered": 0, "dissolved": 0,
    }

    rows = await db.fetchall(
        "SELECT * FROM player_cities "
        "WHERE state != 'dissolved' AND maint_paid_until <= ?",
        (now,),
    )

    for row in rows:
        city = dict(row)
        city_id = int(city["id"])
        summary["checked"] += 1
        # For advance detection (per-tick stage transitions): compare
        # the stage AT now to the stage AT one-week-ago. If the
        # boundary was crossed during the past week, we fire the
        # advance hook. This avoids needing a stored last_stage
        # column.
        prev_stage = grace_stage(city, now - ONE_WEEK_SECONDS)
        cur_stage_pre_pay = grace_stage(city, now)

        cost = await compute_city_maintenance_cost(db, city_id)
        org_id = int(city.get("org_id") or 0)
        treasury = await _get_org_treasury(db, org_id) if org_id else 0

        if treasury >= cost:
            # Pay this week's maintenance.
            if cost > 0 and org_id:
                await db.adjust_org_treasury(org_id, -cost)
            # Bump the paid-until anchor by one week.
            new_paid = float(city.get("maint_paid_until") or now) + ONE_WEEK_SECONDS
            await db.execute(
                "UPDATE player_cities "
                "SET maint_paid_until = ?, grace_started_at = 0 "
                "WHERE id = ?",
                (new_paid, city_id),
            )
            await db.commit()
            summary["paid"] += 1
            # If this clears an active grace, notify + count
            if cur_stage_pre_pay != "active":
                summary["recovered"] += 1
                await _notify_mayor_and_founder(
                    db, city,
                    subject=f"[CITY] {city['name']}: maintenance restored",
                    body=(
                        f"The treasury covered this week's "
                        f"maintenance ({cost:,} cr). {city['name']} "
                        f"has exited its grace period and is fully "
                        f"operational."
                    ),
                )
            log.info(
                "[player_cities] maint paid: city='%s' cost=%d "
                "treasury_after=%d",
                city["name"], cost, treasury - cost,
            )
        else:
            # Treasury cannot cover. Enter / advance / dissolve.
            #
            # Bump maint_paid_until by one week regardless of which
            # sub-branch we take (enter/advance/dissolve). This is
            # the idempotence anchor: if the tick runs twice within
            # one week (e.g. operator manually re-runs), the second
            # call sees maint_paid_until > now and skips the city.
            # The grace timer itself runs off grace_started_at, which
            # is independent of this bump.
            new_paid = float(city.get("maint_paid_until") or now) + ONE_WEEK_SECONDS
            if not is_in_grace(city):
                # Just entered grace.
                await db.execute(
                    "UPDATE player_cities "
                    "SET grace_started_at = ?, maint_paid_until = ? "
                    "WHERE id = ?",
                    (now, new_paid, city_id),
                )
                await db.commit()
                # Refresh the in-memory city dict for downstream
                # stage computation in this same tick pass.
                city["grace_started_at"] = now
                city["maint_paid_until"] = new_paid
                summary["entered_grace"] += 1
                await _notify_mayor_and_founder(
                    db, city,
                    subject=f"[CITY] {city['name']}: maintenance shortfall",
                    body=(
                        f"The treasury could not cover this week's "
                        f"maintenance ({cost:,} cr; treasury "
                        f"holds {treasury:,} cr). {city['name']} "
                        f"has entered a 4-week grace period.\n\n"
                        f"Week 1: NPC guards stop functioning.\n"
                        f"Week 2: citizen-only flags are cleared.\n"
                        f"Week 3: tax collection ceases.\n"
                        f"End of week 4: city auto-dissolves.\n\n"
                        f"Refill the treasury to restore the city."
                    ),
                )
                log.info(
                    "[player_cities] maint shortfall: city='%s' "
                    "cost=%d treasury=%d → entered grace",
                    city["name"], cost, treasury,
                )
                continue

            # Already in grace. Compute current stage and dispatch.
            new_stage = grace_stage(city, now)
            if new_stage == "expired":
                # End of week 4 reached without recovery. Dissolve.
                # No need to bump maint_paid_until — the dissolve
                # excludes this city from future tick passes.
                await _dissolve_for_maintenance(db, city)
                summary["dissolved"] += 1
                continue

            # Bump maint_paid_until for idempotence (the city stays
            # in grace; next tick re-checks treasury at +1 week).
            await db.execute(
                "UPDATE player_cities "
                "SET maint_paid_until = ? WHERE id = ?",
                (new_paid, city_id),
            )
            await db.commit()

            if new_stage != prev_stage:
                # Advanced into a new stage since the last tick
                # (week2 / week3 / week4).
                summary["advanced_in_grace"] += 1
                # Week 2 entry: bulk-clear citizen flags.
                if new_stage == "week2":
                    cleared = await _bulk_clear_citizen_flags(db, city_id)
                    log.info(
                        "[player_cities] grace week 2: city='%s' "
                        "cleared %d citizen-only flags",
                        city["name"], cleared,
                    )
                await _notify_mayor_and_founder(
                    db, city,
                    subject=(
                        f"[CITY] {city['name']}: grace advanced to "
                        f"{new_stage}"
                    ),
                    body=_grace_advance_body(city, new_stage, cost,
                                              treasury),
                )
                log.info(
                    "[player_cities] grace advanced: city='%s' "
                    "%s -> %s",
                    city["name"], prev_stage, new_stage,
                )
            # Same stage as previous tick — no spam, just continue waiting.

    return summary


def _grace_advance_body(city, stage, cost, treasury):
    """Build the body text for the grace-stage-advance mail."""
    head = (
        f"{city['name']} has advanced to grace stage {stage}. "
        f"This week's maintenance ({cost:,} cr) could not be paid "
        f"from the treasury (which holds {treasury:,} cr).\n\n"
    )
    if stage == "week2":
        return head + (
            "Effect: all citizen-only room flags are cleared. "
            "The Mayor cannot apply new citizen-only flags "
            "while in grace.\n\n"
            "Refill the treasury to restore the city."
        )
    if stage == "week3":
        return head + (
            "Effect: tax collection has ceased. No city revenue "
            "will be tagged this week.\n\n"
            "Refill the treasury to restore the city."
        )
    if stage == "week4":
        return head + (
            "Effect: FINAL WARNING. The city will auto-dissolve "
            "in one week if the treasury cannot cover maintenance.\n\n"
            "Refill the treasury to restore the city."
        )
    return head


async def _dissolve_for_maintenance(db, city) -> None:
    """Internal: dissolve a city that has exhausted its grace
    period. Parallel to admin_dissolve_city but:
      - sends a special "dissolution from grace" notification
      - logs as maint dissolve rather than admin dissolve
    """
    city_id = int(city["id"])
    name = city.get("name") or f"id={city_id}"

    await db.execute(
        "DELETE FROM player_city_rooms WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "DELETE FROM player_city_banishments WHERE city_id = ?",
        (city_id,),
    )
    await db.execute(
        "DELETE FROM player_city_guests WHERE city_id = ?", (city_id,),
    )
    await db.execute(
        "UPDATE player_cities SET state = 'dissolved' WHERE id = ?",
        (city_id,),
    )
    await db.commit()

    log.info(
        "[player_cities] MAINT dissolve: city='%s' (id=%d) "
        "grace period exhausted",
        name, city_id,
    )

    await _notify_mayor_and_founder(
        db, city,
        subject=f"[CITY] {name} has dissolved",
        body=(
            f"The 4-week grace period for {name} has expired "
            f"without the treasury recovering. The city has "
            f"automatically dissolved.\n\n"
            f"All expansion rooms are unclaimed; the HQ reverts "
            f"to standalone status. The city name is now "
            f"available for re-founding."
        ),
    )

# ═══════════════════════════════════════════════════════════════════════════
# Phase 7 (May 23 2026): NPC guards
# ═══════════════════════════════════════════════════════════════════════════
#
# Per design v1.2 §7: cities can station NPC guards in expansion
# rooms. Guards are distinct from HQ guards (stored in
# engine.housing's HQ data blob; advisory). City guards are real
# spawned NPCs (via engine.territory's well-tested seam) tracked
# in player_city_guards.
#
# Substrate decisions
# -------------------
# 1. **Separate table, not a column.** Guards have their own
#    lifecycle (assigned, removed, killed → row cleared); they're
#    not a property of a room. The table also lets a single room
#    host multiple guards if a future tweak relaxes the
#    one-per-room convention (Phase 7 enforces one-per-room via
#    the assignment helper, not at the schema level).
# 2. **Reuse engine.territory._GUARD_TEMPLATES + _build_*.** The
#    template + AI shape is fully tested by territory's Drop 6C
#    work. Re-implementing risks drift; importing the underscored
#    helpers is intentional reuse within the same package and is
#    documented at the import site.
# 3. **Slots = HQ guard slots + city guard slots.** Per §7.1 the
#    total guard pool is split. engine.housing already tracks the
#    HQ portion (advisory only); engine.player_cities tracks the
#    city portion (real NPCs). The two systems do NOT share
#    storage, but the total cap a Mayor sees is HQ+city per tier.
# 4. **`guards_active(city)` is a thin grace gate.** Per §7.3 and
#    the Phase 6 mail body promise ("Week 1: NPC guards stop
#    functioning"), the helper returns False for week1+. Wiring
#    this into NPC AI / combat-engage is Phase 7b (deferred — the
#    AI surface is in engine.npc_ai, not player_cities, and the
#    wiring belongs in that drop).
# 5. **Maintenance cost folds in via existing tick.** Phase 6's
#    `compute_city_maintenance_cost` is updated to add
#    `count_city_guards(...) * CITY_GUARD_MAINT_PER_WEEK_CR`. No
#    new tick handler needed — the existing weekly maintenance
#    tick charges guard upkeep alongside expansion-room upkeep.
# 6. **Removal is fail-soft on missing NPCs.** If the NPC row was
#    already deleted (e.g. killed in combat and the corpse cleanup
#    purged it), the row in player_city_guards is removed and the
#    operation reports success. This matches the territory.py
#    pattern (stale guard_npc_id is cleared on detection).

# Per design §7.1 — additional city-level guard slots beyond the
# HQ guard pool (which is engine.housing's advisory count).
CITY_GUARD_SLOTS_BY_HQ_TIER: dict[str, int] = {
    "outpost":       3,
    "chapter_house": 6,
    "fortress":      14,
}


def compute_city_guard_slots(city: dict) -> int:
    """Return the **city-level** guard slot cap for the city.

    Per design §7.1, the total guard pool is HQ_GUARD_SLOTS +
    CITY_GUARD_SLOTS. This helper returns only the city portion;
    callers that want the total should add the HQ portion read
    from engine.housing.

    Unknown HQ tier → returns 0 (treat as no city-level slots
    rather than a crash; the assignment helper's error message
    will mention the unknown tier).
    """
    hq_tier = (city or {}).get("hq_tier") or "outpost"
    return CITY_GUARD_SLOTS_BY_HQ_TIER.get(hq_tier, 0)


def guards_active(city: dict, now=None) -> bool:
    """Per design §7.3: guards stop functioning when treasury is
    depleted (i.e., the city is in grace week 1 or later).

    A 'functioning' guard challenges non-citizens, engages
    hostiles, and consumes maintenance. A non-functioning guard
    is still ASSIGNED (the row stays in player_city_guards) and
    still appears in `+city guards` — but downstream AI / combat
    code should consult this helper before treating the guard as
    active.

    Returns True for healthy cities (grace_started_at == 0) and
    False for any city in grace, including week1.

    Phase 7 ships the helper; Phase 7b wires it into NPC AI
    (currently in engine.npc_ai). For Phase 7 the helper is
    exercised by tests and surfaced in `+city guards` output so
    Mayors see the status, but the AI still runs normally — the
    grace stop-functioning behavior is design-promised but not
    yet runtime-enforced.
    """
    return not is_in_grace(city)


# ── Phase 7: read helpers ───────────────────────────────────────────────────

async def count_city_guards(db, city_id: int) -> int:
    """Return the number of guards currently assigned to the city."""
    rows = await db.fetchall(
        "SELECT COUNT(*) AS n FROM player_city_guards "
        "WHERE city_id = ?",
        (int(city_id),),
    )
    return int(rows[0]["n"]) if rows else 0


async def list_city_guards(db, city_id: int) -> list[dict]:
    """Return assignment rows for the city, ordered by assigned_at.

    Each row is a dict with keys: city_id, npc_id, room_id,
    assigned_by, assigned_at. Caller is responsible for joining
    against the npcs table if it needs names / status — the
    assignment row deliberately does NOT cache npc_name, so a
    rename or template change doesn't leave the display stale.
    """
    rows = await db.fetchall(
        "SELECT city_id, npc_id, room_id, assigned_by, assigned_at "
        "FROM player_city_guards "
        "WHERE city_id = ? "
        "ORDER BY assigned_at ASC, npc_id ASC",
        (int(city_id),),
    )
    return [dict(r) for r in rows]


async def get_guard_assignment(
    db, city_id: int, npc_id: int,
) -> Optional[dict]:
    """Return one assignment row by (city_id, npc_id) or None.

    Used by remove_city_guard to confirm the NPC belongs to this
    city before removing.
    """
    rows = await db.fetchall(
        "SELECT city_id, npc_id, room_id, assigned_by, assigned_at "
        "FROM player_city_guards "
        "WHERE city_id = ? AND npc_id = ?",
        (int(city_id), int(npc_id)),
    )
    return dict(rows[0]) if rows else None


# ── Phase 7: assignment + removal ───────────────────────────────────────────

async def assign_city_guard(
    db, char: dict, room_id: int,
    org_code: Optional[str] = None,
) -> tuple[bool, str, Optional[int]]:
    """Assign a city guard NPC to a room.

    Mayor or Founder only. Constraints (each surfaces its own
    actionable error message):

      - Caller is Mayor or Founder of an active city.
      - The room must be a city room of THIS city.
      - The room must NOT be the HQ center (HQ guards are a
        separate pool managed by engine.housing).
      - The city must have a free city-level guard slot
        (per CITY_GUARD_SLOTS_BY_HQ_TIER[hq_tier]).
      - The org treasury must cover the per-guard one-time
        cost (= GUARD_COST from engine.territory; reused for
        consistency with the per-room territory guard one-time
        cost).
      - The room must not already host a city guard (one-per-
        room enforced at the assignment layer, not the schema).

    Returns ``(success, message, npc_id_or_None)``. On success
    the message is a confirmation string suitable to forward
    verbatim to the player; the NPC id is the newly spawned
    guard. On failure the npc_id is None.

    Failure semantics:
      - All validation errors short-circuit BEFORE any DB
        mutation. The treasury is not touched on validation
        failure.
      - If treasury check passes and the debit happens, but the
        NPC create or assignment-row insert fails downstream,
        the operation refunds the treasury before returning the
        error. Atomicity is "all-or-nothing from the player's
        perspective" without requiring SQLite savepoints (which
        aiosqlite doesn't surface uniformly).
    """
    # Resolve the actor's org + city
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err, None
    if not _is_mayor_or_founder(city, char):
        return False, (
            "Only the Mayor or Founder can assign city guards."
        ), None

    # Validate room membership in this city
    room_id_i = int(room_id)
    city_id = int(city["id"])
    rows = await db.fetchall(
        "SELECT room_id, is_center FROM player_city_rooms "
        "WHERE city_id = ? AND room_id = ?",
        (city_id, room_id_i),
    )
    if not rows:
        return False, (
            f"Room {room_id_i} is not part of {city['name']}. "
            f"You can only station guards in your city's rooms."
        ), None
    room_row = dict(rows[0])
    if int(room_row.get("is_center") or 0) == 1:
        return False, (
            f"Room {room_id_i} is the HQ center. HQ guards are "
            f"managed separately via +hq. City guards station "
            f"on expansion rooms only."
        ), None

    # Slot cap
    n_existing = await count_city_guards(db, city_id)
    cap = compute_city_guard_slots(city)
    if cap <= 0:
        return False, (
            f"Unknown HQ tier {city.get('hq_tier')!r}; cannot "
            f"resolve city guard slot cap. Contact an admin."
        ), None
    if n_existing >= cap:
        return False, (
            f"City guard slots full ({n_existing}/{cap} for "
            f"{city.get('hq_tier')}). Remove a guard before "
            f"adding another."
        ), None

    # One-per-room enforcement
    same_room = await db.fetchall(
        "SELECT npc_id FROM player_city_guards "
        "WHERE city_id = ? AND room_id = ?",
        (city_id, room_id_i),
    )
    if same_room:
        return False, (
            f"A city guard is already stationed in room "
            f"{room_id_i}. Use +city guards remove <npc_id> "
            f"first."
        ), None

    # Treasury check — reuse territory's GUARD_COST for
    # consistency. This is the one-time stationing cost; the
    # weekly upkeep is folded into city maintenance via
    # compute_city_maintenance_cost.
    from engine.territory import GUARD_COST as _GUARD_ONE_TIME_COST
    treasury = int(org.get("treasury") or 0)
    if treasury < _GUARD_ONE_TIME_COST:
        return False, (
            f"Insufficient treasury. Stationing a guard costs "
            f"{_GUARD_ONE_TIME_COST:,} cr; treasury holds "
            f"{treasury:,} cr."
        ), None

    # All validation passed. Debit treasury first; if anything
    # downstream fails, refund before returning the error.
    await db.adjust_org_treasury(org["id"], -_GUARD_ONE_TIME_COST)

    npc_id: Optional[int] = None
    try:
        # Use the org's guard template; fall back to _default if
        # the org code isn't in the template map. Resolve org_code
        # from the org row if not provided by caller.
        from engine.territory import (
            _GUARD_TEMPLATES as _TEMPLATES,
            _build_guard_sheet, _build_guard_ai,
        )
        if org_code is None:
            org_code = org.get("code") or "_default"
        tmpl = _TEMPLATES.get(org_code) or _TEMPLATES["_default"]

        import json as _j
        char_sheet = _build_guard_sheet(tmpl)
        ai_config = _build_guard_ai(tmpl, org_code)
        # Tag the AI config so downstream NPC code can
        # distinguish a city guard from a territory guard. The
        # field is read-only metadata; engine.territory's spawn
        # path doesn't set it, so a True value uniquely
        # identifies a city guard.
        ai_config["city_guard_for_city_id"] = city_id

        guard_name = tmpl["name_prefix"]
        npc_id = await db.create_npc(
            name=guard_name,
            room_id=room_id_i,
            species=tmpl["species"],
            description=tmpl["description"],
            char_sheet_json=_j.dumps(char_sheet),
            ai_config_json=_j.dumps(ai_config),
        )

        # Record the assignment.
        import time as _time
        now = _time.time()
        await db.execute(
            "INSERT INTO player_city_guards "
            "(city_id, npc_id, room_id, assigned_by, assigned_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                city_id, int(npc_id), room_id_i,
                int(char.get("id") or 0), now,
            ),
        )
        await db.commit()
    except Exception as e:
        # Roll back the treasury debit so the player isn't
        # charged for a failed assignment. Best-effort: if even
        # the refund fails, log and let the original error
        # surface.
        try:
            await db.adjust_org_treasury(
                org["id"], _GUARD_ONE_TIME_COST,
            )
        except Exception:
            log.warning(
                "[player_cities] assign_city_guard: refund "
                "after failure ALSO failed for org %d",
                org.get("id"), exc_info=True,
            )
        # If the NPC was actually created, try to clean it up.
        if npc_id is not None:
            try:
                await db.delete_npc(int(npc_id))
            except Exception:
                log.debug(
                    "[player_cities] assign_city_guard: "
                    "npc cleanup after failure failed "
                    "(npc_id=%s)", npc_id, exc_info=True,
                )
        log.warning(
            "[player_cities] assign_city_guard failed for "
            "city %s room %d: %s",
            city_id, room_id_i, e, exc_info=True,
        )
        return False, (
            "Guard assignment failed — treasury has been "
            "refunded. Contact an admin if this persists."
        ), None

    log.info(
        "[player_cities] city=%d guard assigned: npc_id=%d "
        "room=%d by char=%d (slot %d/%d)",
        city_id, int(npc_id), room_id_i,
        int(char.get("id") or 0), n_existing + 1, cap,
    )
    return True, (
        f"Guard stationed in room {room_id_i} of "
        f"{city['name']}. Cost: {_GUARD_ONE_TIME_COST:,} cr "
        f"(weekly upkeep: +{CITY_GUARD_MAINT_PER_WEEK_CR} "
        f"cr/wk). Slot {n_existing + 1}/{cap}."
    ), int(npc_id)


async def remove_city_guard(
    db, char: dict, npc_id: int,
) -> tuple[bool, str]:
    """Remove a city guard NPC.

    Mayor or Founder only. The NPC must belong to the caller's
    org's city (verified via get_guard_assignment).

    Behaviour:
      - The assignment row is removed.
      - The NPC row is deleted (delete_npc).
      - If the NPC was already gone (e.g. killed in combat and
        cleaned up), the assignment row is still removed and
        the operation reports success with a note.

    No refund of the one-time stationing cost — this matches
    engine.territory's remove_guard_npc semantics. The Mayor
    chose to spend the credits; the upkeep saving from
    removing the guard is the only "refund".
    """
    org, city, err = await _resolve_actor_city(db, char)
    if err:
        return False, err
    if not _is_mayor_or_founder(city, char):
        return False, (
            "Only the Mayor or Founder can remove city guards."
        )

    city_id = int(city["id"])
    npc_id_i = int(npc_id)
    assignment = await get_guard_assignment(db, city_id, npc_id_i)
    if assignment is None:
        return False, (
            f"NPC #{npc_id_i} is not a city guard of "
            f"{city['name']}."
        )

    # Best-effort npc delete — the NPC may have already been
    # cleaned up by combat death cascade. Either way, remove
    # the assignment row.
    npc_was_present = True
    try:
        existed = await db.delete_npc(npc_id_i)
        if not existed:
            npc_was_present = False
    except Exception as e:
        log.debug(
            "[player_cities] remove_city_guard: delete_npc(%d) "
            "failed: %s — proceeding with assignment cleanup",
            npc_id_i, e, exc_info=True,
        )
        npc_was_present = False

    await db.execute(
        "DELETE FROM player_city_guards "
        "WHERE city_id = ? AND npc_id = ?",
        (city_id, npc_id_i),
    )
    await db.commit()

    log.info(
        "[player_cities] city=%d guard removed: npc_id=%d by "
        "char=%d (npc_was_present=%s)",
        city_id, npc_id_i, int(char.get("id") or 0),
        npc_was_present,
    )

    if npc_was_present:
        return True, (
            f"Guard #{npc_id_i} removed from {city['name']}."
        )
    return True, (
        f"Guard assignment #{npc_id_i} cleared from "
        f"{city['name']}. (The NPC was already absent; this "
        f"may have been from a recent combat or admin cleanup.)"
    )


async def format_city_guards_lines(
    db, city: dict,
) -> list[str]:
    """Render the `+city guards` view for a city.

    Returns a list of plain text lines (no ANSI). Caller wraps
    in any color codes. Sections:

      - Header (city name, slot N/cap, status active|grace)
      - One line per assigned guard: ``  #npc_id  room=R  by=char_id  at=ISO``
      - Trailer with the assignment help line

    Empty roster shows "no guards stationed" instead of a list.
    """
    city_id = int(city["id"])
    cap = compute_city_guard_slots(city)
    assigns = await list_city_guards(db, city_id)
    n = len(assigns)
    active = guards_active(city)
    status_label = "ACTIVE" if active else "INACTIVE (city in grace)"

    lines = [
        f"=== Guards of {city['name']} ===",
        f"  Slots: {n}/{cap}  Status: {status_label}",
    ]
    if not assigns:
        lines.append(
            "  (No NPC guards stationed. Use "
            "'+city guards assign <room_id>' to station one.)"
        )
        return lines

    import time as _time
    for a in assigns:
        ts = float(a.get("assigned_at") or 0.0)
        ts_str = (
            _time.strftime("%Y-%m-%d %H:%M",
                           _time.gmtime(ts))
            if ts else "unknown"
        )
        lines.append(
            f"  #{a['npc_id']}  room={a['room_id']}  "
            f"assigned by char={a['assigned_by']}  "
            f"at={ts_str} UTC"
        )
    lines.append(
        "  (Use '+city guards remove <npc_id>' to remove. "
        "Each guard costs "
        f"{CITY_GUARD_MAINT_PER_WEEK_CR} cr/wk.)"
    )
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# SYN.4 (2026-05-25) — Cities retarget to wilderness regions
# ══════════════════════════════════════════════════════════════════════════════
#
# Per ``contestable_wilderness_design_v2.md`` §2.9.1 + §3.4. The pivot moves
# city anchoring from city-map zones to wilderness regions. Per Brian's
# design call, MOST OF THE ENGINE SURVIVES UNCHANGED — only the founding
# anchor and the expansion adjacency retarget. Five city benefits (identity,
# tax, citizen security upgrade, +city home, mayor governance), the role
# system, the tax cap, the citizen-only mechanic, and all mayor commands
# stay exactly as they are.
#
# What ships here:
#   * ``found_city_in_region(db, char, name, region_slug)`` — new founding
#     surface anchoring on a wilderness region.
#   * ``claim_landmark_for_city(db, char, region_slug, target_room_id)`` —
#     new expansion surface using landmark adjacency.
#   * City vitality mechanic (active-citizen count per HQ tier, dormant
#     state after 14 days under threshold).
#   * Schema additions: ``vitality_state``, ``vitality_below_since``
#     columns on player_cities.
#
# Parallel-ship pattern: the legacy ``found_city`` and ``claim_room_for_city``
# remain operational so the existing 520 cities tests stay green. The new
# surfaces ship alongside; the parser layer chooses which to invoke. The
# SYN.4 migration script (tools/syn4_migration.py) dissolves all city-map
# cities with 75% refund — after migration runs in production, the legacy
# surfaces are unreachable through the parser by construction.
#
# Why not delete the legacy surfaces in this drop? Two reasons:
#   1. The 520 cities tests pin behavior of the legacy fixtures; updating
#      them in lockstep is its own ~2-session refactor. Keeping the old
#      surfaces lets those tests stay green without churn.
#   2. The retirement of the legacy surfaces depends on the migration
#      having run in production — which is an apply-time event, not a
#      drop-time one. The cleaner separation is: SYN.4 ships the new
#      engine + migration; a follow-up drop (post-migration confirmation)
#      removes the legacy surfaces.


# ── Constants per design §2.9.1 + §2.9.4 ─────────────────────────────────────

# Foothold threshold (50+ influence) per design §2.4 and the existing
# influence-tier system. Symbol-level alias for clarity at the SYN.4 call
# site; value matches MIN_INFLUENCE_TO_FOUND.
CITY_FOUNDING_MIN_FOOTHOLD = 50

# Days within which a citizen counts as "active" for vitality. A character
# is active if their last login (DB column `last_login`) is within this
# window. Per design §2.9.4.
CITY_VITALITY_ACTIVE_WINDOW_DAYS = 7
CITY_VITALITY_ACTIVE_WINDOW_SECS = (
    CITY_VITALITY_ACTIVE_WINDOW_DAYS * 24 * 60 * 60
)

# Days under threshold before a city drops to 'dormant'. Per design §2.9.4
# ("falls back to dormant state after 14 days under threshold").
CITY_VITALITY_DORMANT_GRACE_DAYS = 14
CITY_VITALITY_DORMANT_GRACE_SECS = (
    CITY_VITALITY_DORMANT_GRACE_DAYS * 24 * 60 * 60
)

# Tax cap multiplier when below threshold (active=reduced). Per design:
# "Tax cap drops to 50% of HQ-tier baseline."
CITY_VITALITY_TAX_MULTIPLIER_REDUCED = 0.5

# Active-citizen thresholds per HQ tier. Per design §2.9.4.
CITY_VITALITY_THRESHOLDS: dict[str, int] = {
    "outpost":       1,
    "chapter_house": 3,
    "fortress":      5,
}

# SYN.4 migration refund rate. Per design §2.9.2: "dissolve all city-map
# cities at SYN.4 with 75% refund". Higher than the standard 50%
# dissolution refund — founders are compensated for the platform's pivot.
SYN4_MIGRATION_REFUND_RATIO = 0.75

# Migration-state row keys for tools/syn4_migration.py idempotency.
# Mirrors SYN.1.b's syn_migration_state pattern.
SYN4_MIGRATION_KEY = "syn4_cities_dissolved"


# ── Found city anchored on a wilderness region ───────────────────────────────

async def found_city_in_region(
    db, char: dict, name: str, region_slug: str,
) -> tuple[bool, str]:
    """Found a new player city anchored on a wilderness region.

    SYN.4 (2026-05-25) per ``contestable_wilderness_design_v2.md`` §2.9.1
    + §3.4. The region-anchored founding surface — replaces the legacy
    ``found_city``'s HQ-zone validation chain.

    Validation order (each short-circuits with an actionable error):

      1. Name validity (pure validation, reuses validate_city_name).
      2. Character has a faction membership (not 'independent').
      3. Org exists in DB.
      4. Character is the org leader (rank 5+ via MIN_RANK_LEVEL_TO_FOUND).
      5. Org does not already have an active city.
      6. City name not duplicate.
      7. Org has a tier-5 HQ.
      8. HQ subtype determinable from storage_max.
      9. Region exists (has at least one landmark room).
     10. Region eligibility:
            (a) Owned by the org → OK (no influence check).
            (b) Owned by a different org → REJECT (the rival owns it;
                must contest first via SYN.3).
            (c) Un-owned → require Foothold (50+) influence in the
                region's parent zone.
     11. Treasury balance >= founding cost.

    The HQ room transfers to the first landmark room of the region. Each
    of the HQ's interior rooms still anchors as City Center via
    player_city_rooms (is_center=1). This preserves the "+city home"
    + look + citizen-room benefits exactly as the legacy founding flow
    did — the only thing that changes is *where* the city is anchored.

    The "cities cannot be founded in secured zones" rule is RETIRED in
    SYN.4: wilderness regions are CONTESTED by default per SYN.2's
    wilderness-aware security branch.

    Returns (ok, message). Caller is responsible for echoing message
    to the player.
    """
    # ── 1. Validate name ─────────────────────────────────────────
    ok, validated_name = validate_city_name(name)
    if not ok:
        return False, validated_name
    name = validated_name

    # ── 2. Resolve org via faction_id ────────────────────────────
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return False, "You are not a member of any organization."

    # ── 3. Org exists ────────────────────────────────────────────
    org = await db.get_organization(faction_code)
    if not org:
        return False, f"Organization '{faction_code}' could not be found."
    org_id = org["id"]

    # ── 4. Rank check ────────────────────────────────────────────
    membership = await db.get_membership(char["id"], org_id)
    if not membership:
        return False, "You do not appear to be a member of your organization."
    rank_level = membership.get("rank_level") or 0
    if rank_level < MIN_RANK_LEVEL_TO_FOUND:
        return False, (
            f"Only the organization leader (rank "
            f"{MIN_RANK_LEVEL_TO_FOUND}+) can found a city."
        )

    # ── 5. Already has a city? ───────────────────────────────────
    existing = await get_city_by_org(db, org_id)
    if existing:
        return False, (
            f"Your organization already has a city: {existing['name']}."
        )

    # ── 6. Name uniqueness ───────────────────────────────────────
    name_dup = await get_city_by_name(db, name)
    if name_dup:
        return False, f"A city named '{name}' already exists."

    # ── 7. Org must have a tier-5 HQ ─────────────────────────────
    from engine.housing import get_org_hq
    hq = await get_org_hq(db, faction_code)
    if not hq:
        return False, (
            "Your organization does not have a tier-5 HQ to anchor "
            "a city. Build an HQ first."
        )

    # ── 8. Determine HQ subtype ──────────────────────────────────
    hq_type = _infer_hq_type(hq)
    if hq_type not in FOUNDING_COSTS:
        return False, (
            f"Cannot determine HQ type for city founding "
            f"(storage_max={hq.get('storage_max')!r}). "
            f"This is a data issue; contact an admin."
        )
    cost = FOUNDING_COSTS[hq_type]

    # ── 9. Region exists (has at least one landmark) ─────────────
    from engine.territory import (
        _get_region_landmarks, _get_region_zone, get_region_owner,
        get_territory_influence,
    )
    landmarks = await _get_region_landmarks(db, region_slug)
    if not landmarks:
        return False, (
            f"Region '{region_slug}' is not a recognized wilderness "
            f"region with landmark rooms."
        )

    # ── 10. Region eligibility ───────────────────────────────────
    owner = await get_region_owner(db, region_slug)
    if owner:
        if owner["org_code"] != faction_code:
            # Rival owns the region. Must seize via SYN.3 contest first.
            return False, (
                f"Region '{region_slug}' is held by "
                f"{owner['org_code'].replace('_', ' ').title()}. "
                f"Contest it before founding a city there."
            )
        # Owned by this org — no influence check needed.
    else:
        # Un-owned region. Require Foothold (50+) influence in parent zone.
        zone_id = await _get_region_zone(db, region_slug)
        if zone_id is None:
            return False, (
                f"Region '{region_slug}' has no resolvable parent zone. "
                f"This is a data issue; contact an admin."
            )
        influence = await get_territory_influence(
            db, faction_code, zone_id,
        )
        if (influence or 0) < CITY_FOUNDING_MIN_FOOTHOLD:
            return False, (
                f"To found a city in an un-owned region you need at "
                f"least {CITY_FOUNDING_MIN_FOOTHOLD} influence in the "
                f"region's parent zone (Foothold). "
                f"Current: {influence or 0}."
            )

    # ── 11. Treasury balance ─────────────────────────────────────
    treasury = org.get("treasury") or 0
    if treasury < cost:
        return False, (
            f"Treasury is insufficient. Founding requires "
            f"{cost:,} cr; treasury has {treasury:,} cr."
        )

    # ── All validation passed — commit ───────────────────────────
    now = time.time()
    hq_room_ids = _parse_hq_room_ids(hq)
    # Resolve parent zone for the row (used by tax + maintenance ticks
    # that key on zone_id today; will retarget in later drops).
    zone_id = await _get_region_zone(db, region_slug)

    # Debit treasury
    await db.adjust_org_treasury(org_id, -cost)

    # Insert city row anchored on the region. wilderness_region_id +
    # zone_id both set; legacy fields stay populated for back-compat
    # with tax/maintenance code that still keys on zone_id.
    cursor = await db.execute(
        "INSERT INTO player_cities "
        "(name, name_lower, org_id, hq_id, zone_id, "
        " wilderness_region_id, founded_at, founder_id, mayor_id, "
        " week_start_ts, hq_tier, maint_paid_until, vitality_state) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (name, name.lower(), org_id, hq["id"], zone_id, region_slug,
         now, char["id"], char["id"], now, hq_type,
         now + ONE_WEEK_SECONDS),
    )
    city_id = _extract_lastrowid(cursor)
    if city_id is None:
        lookup = await db.fetchall(
            "SELECT id FROM player_cities WHERE name_lower = ?",
            (name.lower(),),
        )
        city_id = lookup[0]["id"] if lookup else None
    if city_id is None:
        await db.commit()
        return False, "Internal error: city created but id not resolvable."

    # Anchor HQ rooms as City Center.
    for rid in hq_room_ids:
        try:
            await db.execute(
                "INSERT INTO player_city_rooms "
                "(city_id, room_id, is_center, claimed_at) "
                "VALUES (?, ?, 1, ?)",
                (city_id, rid, now),
            )
        except Exception as e:
            log.warning(
                "[player_cities/SYN.4] could not anchor room %s to city %s: %s",
                rid, city_id, e,
            )
    await db.commit()

    log.info(
        "[player_cities/SYN.4] founded '%s' in region %s "
        "(city_id=%d, org=%s, hq_type=%s, cost=%d)",
        name, region_slug, city_id, faction_code, hq_type, cost,
    )
    return True, (
        f"City '{name}' has been founded in {region_slug}. "
        f"{cost:,} credits debited from treasury. "
        f"{len(hq_room_ids)} HQ rooms are now the City Center."
    )


# ── Expansion: claim a landmark in the same region ───────────────────────────

async def claim_landmark_for_city(
    db, char: dict, target_room_id: int,
) -> tuple[bool, str]:
    """Claim a landmark room in the city's wilderness region as expansion.

    SYN.4 per ``contestable_wilderness_design_v2.md`` §2.9.1. Replaces
    the legacy ``claim_room_for_city`` for region-anchored cities. The
    contiguity check uses landmark adjacency within the region's landmark
    graph — same engine as Drop 6C's `_get_region_landmarks`.

    Validation order:

      1. Character has a faction membership.
      2. Org has an active city.
      3. Character is the org leader (rank 5+) — matches founding.
      4. City is region-anchored (has wilderness_region_id).
      5. Target room exists.
      6. Target room is a landmark of the city's region.
      7. Target not already a city room (any city).
      8. Size cap (MAX_EXPANSION_ROOMS by HQ tier — unchanged from
         legacy). Vitality reduces cap when 'reduced' state (current
         actual size, no new claims).
      9. Contiguity: target shares an exit with an existing city
         room. Re-uses ``_is_contiguous_to_city`` because landmark
         rooms are real rooms with normal exits; the adjacency
         semantic is identical for the region-anchored case.
     10. 24-hour rate-limit (honors cooldowns_enabled() dev bypass).
     11. Treasury >= EXPANSION_CLAIM_COST.

    Returns (ok, message).
    """
    from engine.territory import _get_region_landmarks

    # ── 1. Resolve org ───────────────────────────────────────────
    faction_code = char.get("faction_id") or "independent"
    if faction_code == "independent":
        return False, "You are not a member of any organization."
    org = await db.get_organization(faction_code)
    if not org:
        return False, f"Organization '{faction_code}' could not be found."
    org_id = org["id"]

    # ── 2. Org must have an active city ──────────────────────────
    city = await get_city_by_org(db, org_id)
    if not city:
        return False, "Your organization has no active city to expand."

    # ── 3. Rank check ────────────────────────────────────────────
    membership = await db.get_membership(char["id"], org_id)
    if (not membership
            or (membership.get("rank_level") or 0) < MIN_RANK_LEVEL_TO_FOUND):
        return False, (
            f"Only the organization leader (rank "
            f"{MIN_RANK_LEVEL_TO_FOUND}+) can claim city expansion rooms."
        )

    # ── 4. City must be region-anchored ──────────────────────────
    region_slug = city.get("wilderness_region_id")
    if not region_slug:
        return False, (
            "This city is not anchored on a wilderness region. Legacy "
            "city-map cities cannot use the region-landmark expansion "
            "API. Use the standard +city claim flow, or dissolve and "
            "re-found in a wilderness region."
        )

    # ── 5. Target room exists ────────────────────────────────────
    target_room = await db.get_room(target_room_id)
    if not target_room:
        return False, "That room does not exist."

    # ── 6. Target must be a landmark of the city's region ────────
    landmarks = await _get_region_landmarks(db, region_slug)
    if target_room_id not in landmarks:
        return False, (
            f"That room is not a landmark of '{region_slug}'. "
            f"Cities can only expand to landmark rooms within their "
            f"anchoring region."
        )

    # ── 7. Not already a city room ───────────────────────────────
    existing_city = await get_city_for_room(db, target_room_id)
    if existing_city:
        if existing_city["id"] == city["id"]:
            return False, "That room is already part of your city."
        return False, (
            f"That room is already part of another city: "
            f"{existing_city['name']}."
        )

    # ── 8. Size cap (with vitality reduction) ────────────────────
    hq_tier = city.get("hq_tier") or "outpost"
    max_expansion = MAX_EXPANSION_ROOMS.get(hq_tier)
    if max_expansion is None:
        return False, (
            f"Unknown city tier '{hq_tier}'. Cannot resolve "
            f"expansion cap."
        )
    current_expansion = await get_city_expansion_count(db, city["id"])
    vitality_state = city.get("vitality_state") or "active"
    if vitality_state in ("reduced", "dormant"):
        # Per design §2.9.4: "Expansion limit drops to current actual
        # size (no new claims)." Hard-block any new claim while
        # vitality is below threshold.
        return False, (
            f"City vitality is {vitality_state}; expansion is locked "
            f"until active-citizen count recovers."
        )
    if current_expansion >= max_expansion:
        return False, (
            f"City has reached its expansion cap "
            f"({current_expansion}/{max_expansion} rooms for "
            f"'{hq_tier}' tier). Upgrade the HQ to expand further."
        )

    # ── 9. Contiguity ─────────────────────────────────────────────
    contiguous = await _is_contiguous_to_city(
        db, city["id"], target_room_id,
    )
    if not contiguous:
        return False, (
            "The target landmark is not adjacent to any existing city "
            "room. Choose a landmark connected by direct exit."
        )

    # ── 10. Rate-limit ────────────────────────────────────────────
    try:
        from engine.jedi_gating import cooldowns_enabled
        cd_active = cooldowns_enabled()
    except Exception:
        cd_active = True
    if cd_active:
        last_expansion = await get_city_last_expansion(db, city["id"])
        now = time.time()
        if now - last_expansion < EXPANSION_RATE_LIMIT_SECONDS:
            remaining = int(
                EXPANSION_RATE_LIMIT_SECONDS - (now - last_expansion)
            )
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            return False, (
                f"Expansion rate-limited. Try again in "
                f"{hours}h {minutes}m."
            )

    # ── 11. Treasury check ────────────────────────────────────────
    treasury = org.get("treasury") or 0
    if treasury < EXPANSION_CLAIM_COST:
        return False, (
            f"Treasury is insufficient. Expansion requires "
            f"{EXPANSION_CLAIM_COST:,} cr; treasury has {treasury:,} cr."
        )

    # ── Commit ────────────────────────────────────────────────────
    await db.adjust_org_treasury(org_id, -EXPANSION_CLAIM_COST)
    now = time.time()
    try:
        await db.execute(
            "INSERT INTO player_city_rooms "
            "(city_id, room_id, is_center, claimed_at) "
            "VALUES (?, ?, 0, ?)",
            (city["id"], target_room_id, now),
        )
        await db.commit()
    except Exception as e:
        log.warning(
            "[player_cities/SYN.4] expansion insert failed: %s", e,
        )
        return False, "Internal error claiming landmark."

    log.info(
        "[player_cities/SYN.4] expanded city #%d to landmark %d "
        "in region %s (cost=%d)",
        city["id"], target_room_id, region_slug, EXPANSION_CLAIM_COST,
    )
    return True, (
        f"Landmark room #{target_room_id} claimed for "
        f"{EXPANSION_CLAIM_COST:,} cr."
    )


# ── City vitality ────────────────────────────────────────────────────────────

async def count_active_citizens(db, city_id: int) -> int:
    """Count citizens of `city_id` whose last_login is within the
    7-day active window.

    Citizenship is membership-based: a citizen is anyone in the city's
    org. (Guests are not citizens for vitality purposes per the role
    system in get_city_role().) The query joins:
        player_cities → org_id → memberships → characters.last_login

    Characters without last_login (legacy rows / NPCs that somehow
    have memberships) are excluded. Returns 0 on lookup failure.
    """
    try:
        city_rows = await db.fetchall(
            "SELECT org_id FROM player_cities WHERE id = ?",
            (city_id,),
        )
        if not city_rows:
            return 0
        org_id = city_rows[0]["org_id"]
        cutoff = time.time() - CITY_VITALITY_ACTIVE_WINDOW_SECS
        rows = await db.fetchall(
            "SELECT COUNT(*) AS c "
            "FROM memberships m "
            "JOIN characters c ON c.id = m.char_id "
            "WHERE m.org_id = ? AND COALESCE(c.last_login, 0) >= ?",
            (org_id, cutoff),
        )
        return int(rows[0]["c"]) if rows and rows[0]["c"] is not None else 0
    except Exception:
        log.warning(
            "[player_cities/SYN.4] count_active_citizens failed for "
            "city_id=%d", city_id, exc_info=True,
        )
        return 0


def compute_vitality_threshold(hq_tier: str) -> int:
    """Pure rule: active-citizen threshold for a given HQ tier.

    Defaults to 1 if the tier is unknown (safer than crashing).
    """
    return CITY_VITALITY_THRESHOLDS.get(hq_tier, 1)


def compute_vitality_state(
    active_count: int, threshold: int,
    below_since: Optional[float], now: Optional[float] = None,
) -> tuple[str, Optional[float]]:
    """Pure rule: compute the new (state, below_since) for a city.

    Inputs:
      * ``active_count``  — current active-citizen count.
      * ``threshold``     — HQ-tier threshold from compute_vitality_threshold.
      * ``below_since``   — stored timestamp the city first dropped
                            below threshold, or None if it was at/above
                            on the previous tick.
      * ``now``           — current time (injectable for testing).

    Outputs (state, new_below_since):
      * If active_count >= threshold:
            state='active', new_below_since=None
      * If active_count < threshold AND below_since is None:
            state='reduced', new_below_since=now (just dropped)
      * If active_count < threshold AND now - below_since < 14d:
            state='reduced', new_below_since=below_since (preserved)
      * If active_count < threshold AND now - below_since >= 14d:
            state='dormant', new_below_since=below_since (preserved)

    State transitions are recoverable: when active_count rises back
    to threshold, below_since is cleared and state returns to
    'active' on the next tick.
    """
    if now is None:
        now = time.time()
    if active_count >= threshold:
        return ("active", None)
    # Below threshold
    if below_since is None:
        return ("reduced", now)
    if now - below_since >= CITY_VITALITY_DORMANT_GRACE_SECS:
        return ("dormant", below_since)
    return ("reduced", below_since)


async def tick_city_vitality(db, session_mgr=None) -> None:
    """Update vitality state for all active cities.

    Per design §2.9.4. Runs hourly via the existing tick scheduler
    (wired up in a separate drop — this tick is the engine surface).
    For each active city:
      1. Count active citizens (last_login within 7 days).
      2. Compare to HQ-tier threshold.
      3. Apply compute_vitality_state() rules.
      4. Persist any state transition + broadcast a status line when
         the city drops to 'dormant' or recovers to 'active'.

    Errors are caught per-city; one bad row won't bring down the
    whole tick.
    """
    now = time.time()
    try:
        rows = await db.fetchall(
            "SELECT id, name, org_id, hq_tier, vitality_state, "
            "vitality_below_since FROM player_cities "
            "WHERE state = 'active'"
        )
    except Exception:
        log.warning("[player_cities/SYN.4] tick: fetch failed",
                    exc_info=True)
        return

    for r in rows:
        city = dict(r)
        try:
            active_count = await count_active_citizens(db, city["id"])
            threshold = compute_vitality_threshold(city["hq_tier"])
            prev_state = city.get("vitality_state") or "active"
            new_state, new_below_since = compute_vitality_state(
                active_count, threshold,
                city.get("vitality_below_since"),
                now=now,
            )
            if (new_state != prev_state
                    or new_below_since != city.get("vitality_below_since")):
                await db.execute(
                    "UPDATE player_cities "
                    "SET vitality_state = ?, vitality_below_since = ? "
                    "WHERE id = ?",
                    (new_state, new_below_since, city["id"]),
                )
                await db.commit()
                log.info(
                    "[player_cities/SYN.4] vitality city #%d (%s): "
                    "%s -> %s (active=%d, threshold=%d)",
                    city["id"], city["name"], prev_state, new_state,
                    active_count, threshold,
                )
                # Broadcast notable transitions only (not every reduce/
                # restore-from-reduced cycle).
                if session_mgr is not None and new_state in (
                        "dormant",) or (prev_state == "dormant"
                                         and new_state == "active"):
                    try:
                        if new_state == "dormant":
                            msg = (
                                f"\n  \033[1;33m[CITY DORMANT]\033[0m "
                                f"\033[1;37m{city['name']}\033[0m has "
                                f"fallen dormant under low citizen "
                                f"activity.\n"
                            )
                        else:
                            msg = (
                                f"\n  \033[1;32m[CITY ACTIVE]\033[0m "
                                f"\033[1;37m{city['name']}\033[0m has "
                                f"recovered to active status.\n"
                            )
                        for sess in session_mgr.all:
                            if getattr(sess, "is_in_game", False):
                                await sess.send_line(msg)
                    except Exception:
                        log.warning(
                            "[player_cities/SYN.4] vitality "
                            "broadcast failed", exc_info=True,
                        )
        except Exception:
            log.warning(
                "[player_cities/SYN.4] vitality tick failed for "
                "city #%d", city["id"], exc_info=True,
            )
            continue


def effective_tax_rate_cap(city: dict) -> float:
    """Pure rule: effective tax-rate cap accounting for vitality.

    Per design §2.9.4: "Tax cap drops to 50% of HQ-tier baseline"
    when vitality state is 'reduced' or 'dormant'.

    Inputs:
      * ``city`` — a city row dict with rate_cap + vitality_state.

    Returns the effective cap as a float in [0.0, 1.0].
    """
    base_cap = float(city.get("rate_cap") or 0.10)
    vitality = city.get("vitality_state") or "active"
    if vitality in ("reduced", "dormant"):
        return base_cap * CITY_VITALITY_TAX_MULTIPLIER_REDUCED
    return base_cap


# ── SYN.4 one-shot migration: dissolve city-map cities with 75% refund ───────

async def syn4_migrate_dissolve_city_map_cities(db) -> dict:
    """Idempotent migration: dissolve all city-map cities with 75% refund.

    Per ``contestable_wilderness_design_v2.md`` §2.9.2 ("dissolve all
    city-map cities at SYN.4 with 75% refund"). Mirrors the SYN.1.b
    pattern: a row in ``syn_migration_state`` records that this
    migration has run, so re-bootstrapping the schema doesn't
    re-dissolve already-migrated cities.

    A "city-map city" is any active city with NULL wilderness_region_id
    — i.e. founded via the legacy ``found_city`` flow. Region-anchored
    cities (founded via ``found_city_in_region``) are untouched.

    For each city-map city:
      1. Read founding cost from FOUNDING_COSTS[hq_tier].
      2. Compute refund = floor(cost * 0.75).
      3. Credit refund to the city's org treasury.
      4. Drop all player_city_rooms rows for the city.
      5. Mark city state='dissolved' with grace_started_at=now.

    Returns a summary dict:
      {
        "ran": bool,                    # False if already migrated
        "dissolved_count": int,
        "total_refunded": int,
        "cities": [{"id", "name", "org_code", "refund"}, ...],
      }
    """
    # ── Idempotency check ──
    try:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS syn_migration_state ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL,"
            "  applied_at REAL NOT NULL"
            ")"
        )
        await db.commit()
    except Exception:
        log.warning(
            "[player_cities/SYN.4] migration state table create failed",
            exc_info=True,
        )

    try:
        marker_rows = await db.fetchall(
            "SELECT value FROM syn_migration_state WHERE key = ?",
            (SYN4_MIGRATION_KEY,),
        )
        if marker_rows:
            log.info(
                "[player_cities/SYN.4] migration already applied (%s)",
                marker_rows[0]["value"],
            )
            return {
                "ran": False,
                "dissolved_count": 0,
                "total_refunded": 0,
                "cities": [],
            }
    except Exception:
        log.warning(
            "[player_cities/SYN.4] migration marker read failed",
            exc_info=True,
        )

    # ── Find city-map cities (wilderness_region_id IS NULL) ──
    try:
        rows = await db.fetchall(
            "SELECT pc.id, pc.name, pc.org_id, pc.hq_tier, "
            "       o.code AS org_code "
            "FROM player_cities pc "
            "LEFT JOIN organizations o ON o.id = pc.org_id "
            "WHERE pc.state = 'active' "
            "  AND (pc.wilderness_region_id IS NULL "
            "       OR pc.wilderness_region_id = '')"
        )
    except Exception:
        log.warning(
            "[player_cities/SYN.4] migration city query failed",
            exc_info=True,
        )
        return {
            "ran": False,
            "dissolved_count": 0,
            "total_refunded": 0,
            "cities": [],
        }

    now = time.time()
    dissolved = []
    for r in rows:
        city = dict(r)
        try:
            hq_tier = city.get("hq_tier") or "outpost"
            base_cost = FOUNDING_COSTS.get(hq_tier, 0)
            refund = int(base_cost * SYN4_MIGRATION_REFUND_RATIO)
            await db.adjust_org_treasury(city["org_id"], refund)
            await db.execute(
                "DELETE FROM player_city_rooms WHERE city_id = ?",
                (city["id"],),
            )
            await db.execute(
                "UPDATE player_cities "
                "SET state = 'dissolved', grace_started_at = ? "
                "WHERE id = ?",
                (now, city["id"]),
            )
            await db.commit()
            dissolved.append({
                "id":       city["id"],
                "name":     city["name"],
                "org_code": city.get("org_code") or "(unknown)",
                "refund":   refund,
            })
            log.info(
                "[player_cities/SYN.4] migrated: dissolved '%s' "
                "(city_id=%d, org=%s, refund=%d)",
                city["name"], city["id"],
                city.get("org_code") or "(unknown)", refund,
            )
        except Exception:
            log.warning(
                "[player_cities/SYN.4] migration of city #%d failed; "
                "continuing", city["id"], exc_info=True,
            )
            continue

    # ── Record idempotency marker ──
    try:
        await db.execute(
            "INSERT INTO syn_migration_state (key, value, applied_at) "
            "VALUES (?, ?, ?)",
            (SYN4_MIGRATION_KEY,
             f"{len(dissolved)}_cities_dissolved",
             now),
        )
        await db.commit()
    except Exception:
        log.warning(
            "[player_cities/SYN.4] migration marker write failed",
            exc_info=True,
        )

    total_refunded = sum(c["refund"] for c in dissolved)
    log.info(
        "[player_cities/SYN.4] migration complete: %d cities dissolved, "
        "%d cr refunded total", len(dissolved), total_refunded,
    )
    return {
        "ran": True,
        "dissolved_count": len(dissolved),
        "total_refunded": total_refunded,
        "cities": dissolved,
    }


__all__ = list(set(globals().get("__all__", []))) + [
    # Constants
    "CITY_FOUNDING_MIN_FOOTHOLD",
    "CITY_VITALITY_ACTIVE_WINDOW_DAYS",
    "CITY_VITALITY_ACTIVE_WINDOW_SECS",
    "CITY_VITALITY_DORMANT_GRACE_DAYS",
    "CITY_VITALITY_DORMANT_GRACE_SECS",
    "CITY_VITALITY_TAX_MULTIPLIER_REDUCED",
    "CITY_VITALITY_THRESHOLDS",
    "SYN4_MIGRATION_REFUND_RATIO",
    "SYN4_MIGRATION_KEY",
    # New surfaces
    "found_city_in_region",
    "claim_landmark_for_city",
    # Vitality
    "count_active_citizens",
    "compute_vitality_threshold",
    "compute_vitality_state",
    "tick_city_vitality",
    "effective_tax_rate_cap",
    # Migration
    "syn4_migrate_dissolve_city_map_cities",
]
