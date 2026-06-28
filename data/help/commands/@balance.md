---
key: "@balance"
title: "@balance — Telemetry Balance Dashboard (Admin)"
category: "Commands: Admin"
summary: Admin read-side of the T3.19 telemetry pipeline — rolls the append-only behavioural record (engine/telemetry.py) into balance-tuning signals (grind cap pressure, CP source mix, objective/chain funnels, encounter pacing, communal menace). Companion to @economy's live-DB snapshot. Requires admin access.
aliases: ["@bal"]
see_also: ["@economy", "@director", "@city"]
tags: [admin, telemetry, balance, economy, tuning, command]
access_level: 3
examples:
  - cmd: "@balance"
    description: "Overview — event mix plus every headline rollup in one screen."
  - cmd: "@balance grind"
    description: "Mob-grind kill volume, credit payout, and how hard players are pressing the daily grind cap."
  - cmd: "@balance cp"
    description: "Character-Point income source mix and weekly-cap pressure."
  - cmd: "@balance objectives"
    description: "Mission / bounty / smuggling start→complete funnel (where players abandon)."
  - cmd: "@balance chains"
    description: "Tutorial-chain and freelance-questline completion funnel — the NPE health metric."
  - cmd: "@balance encounters"
    description: "Wilderness encounter roll→fire rate, broken out by difficulty band."
  - cmd: "@balance events"
    description: "Communal-objective (cult menace) accumulation and strike outcomes."
  - cmd: "@balance sessions"
    description: "Login/logout engagement: connect→login conversion, play-time distribution, web-vs-telnet transport mix."
  - cmd: "@balance raw 50"
    description: "Dump the last 50 raw telemetry records verbatim (default 20, clamped 1–200)."
---

`@balance` is the **admin telemetry dashboard** — the read-side of the
T3.19 tunables/telemetry system. It requires admin access
(`AccessLevel.ADMIN`). The single alias is `@bal`.

@BALANCE vs @ECONOMY
  These two admin boards answer different questions and you will
  usually read them together:

  - **`@economy`** reads **live DB state** — who holds how many
    credits *right now*, the current money supply, treasury
    balances. It is a snapshot of the present.
  - **`@balance`** reads the **append-only telemetry dump**
    (`engine/telemetry.py`) — the *behavioural record* of how
    players actually earn, spend, and progress *over time*. It
    rolls those events up into the signals you tune balance
    against. It is the trend, not the snapshot.

  Put plainly: `@economy` tells you the bank balance; `@balance`
  tells you the cash flow.

SUBCOMMAND REFERENCE
  (no arg)            Overview — event mix + every headline rollup
  grind              Mob-grind kill volume, payout, cap pressure
  cp                 CP-income source mix + weekly-cap pressure
  objectives         Mission/bounty/smuggling start→complete funnel
  chains             Tutorial-chain / questline completion funnel
  encounters         Wilderness encounter roll→fire rate by band
  events             Communal-objective menace + strike outcomes
  sessions           Login/logout engagement + retention funnel
  raw [N]            The last N raw telemetry records (default 20)

  Sub-board aliases the parser also accepts:
    objectives = objective, missions
    chains     = chain, questlines, questline
    encounters = encounter
    events     = communal
    sessions   = session

READING THE BOARDS
  - **grind** surfaces whether the solo-PvE mob-grind trickle is
    paying out near, at, or under its bounded daily cap — the
    signal for whether the grind faucet needs widening or
    tightening.
  - **cp** shows where Character Points are actually coming from
    (early-combat kills, objectives, achievements, the weekly
    tick) and how close players run to the weekly CP cap.
  - **objectives** and **chains** are *funnels*: how many players
    *start* a mission / questline vs how many *complete* it. A
    wide start→complete gap on a chain is an NPE drop-off worth
    investigating. (The chain board carries a per-`chain_id`
    breakdown, label-preferred over the raw id.)
  - **encounters** reports the wilderness-anomaly roll→fire rate
    by difficulty band — the pacing knob for how often the
    open world actually triggers content.
  - **events** tracks communal-objective (cult) menace
    accumulation and strike outcomes.
  - **sessions** is the engagement / retention funnel: connections
    vs logins (the connect→login conversion — how many of a day's
    connects ever reach the world), average and peak play time,
    average connect→disconnect span (which exposes time spent
    bouncing at the login screen), distinct characters/accounts,
    and the web-vs-telnet transport mix. This is the signal for
    whether `idle_timeout` is cutting real sessions short and
    whether players come back.

RAW DUMP
  `@balance raw [N]` prints the last N telemetry records as
  `<event-type> {fields…}`, newest last. N defaults to 20 and is
  clamped to 1–200. Use it to spot-check a specific event's
  payload when a rollup looks surprising.

OPERATIONAL NOTES
  - The dashboard reads only what is **in view** — telemetry is
    a bounded in-memory buffer flushed to the append-only sink;
    the header shows the buffered/dropped-overflow counts and the
    time window the events span.
  - If nothing has been recorded yet (or the sink is disabled),
    the board says so and reports the sink path/state instead of
    erroring.
  - Telemetry is **fail-open**: emission never blocks gameplay,
    and reading the board never mutates state. It is safe to run
    on a live server at any time.
  - For the full prose walkthrough — including how `@balance`
    differs from `@economy` and what each sub-board means for
    tuning — see the Administration guide (Guide 27 §3).

CHEAT SHEET
  @balance              = overview (event mix + all rollups)
  @balance grind        = grind cap pressure
  @balance cp           = CP source mix
  @balance objectives   = mission/bounty/smuggling funnel
  @balance chains       = chain/questline completion funnel
  @balance encounters   = wilderness pacing
  @balance events       = communal menace + strikes
  @balance sessions     = engagement/retention funnel
  @balance raw [N]      = last N raw records (default 20)

Sources: T3.19 telemetry read-side (`parser/director_commands.py`
`BalanceCommand`; rollups in `engine/telemetry.py::summarize`). The
chain funnel board is the consumer added in the telemetry-chain-rollup
drop. For the live-DB economy snapshot, see `@economy`.
