# Web Client Vision & Wire Protocol — Design v1.3

**SW_MUSH — Star Wars D6 Revised & Expanded · Clone Wars era (~20 BBY)**
**BTGlass80 — May 26 2026**
**Status:** v1.3 — surgical delta on v1.2 folding the SYN.1–10 (Contestable Wilderness) wave. Brian sign-off pending. **In-place revision May 26 2026 PM** folded four gap-check findings (see changelog).

**Changelog:**
- **v1.3 in-place revision** (May 26 2026 PM) — Folded four gap-check findings from a follow-up session: (a) added Anchor NPC names to the era-fidelity checklist (amends v1.2 §10.10 via §10.11), (b) added SYN.4 vitality chip note for the City panel (§6.16 sketch), (c) added SYN.5 intel-handover availability indicator note for the Faction panel (§6.11.2 sketch), (d) added a sample news event sequence to §6.10.1 for designer mockup context. All four are small additions, none invalidate prior v1.3 content.
- **v1.3** (May 26 2026) — Delta against v1.2. Folds in the May 25 SYN.10 handoff and the broader SYN.1–10 unification (region as first-class entity, region/zone security duality, contest state machine, weekly resource quality, player-constructed buildings, news-event taxonomy). Adds §3.16 (SYN data contracts), §4.6 (semantic ANSI→CSS palette table), §6.2.1 (Region panel), §6.10.1 (typed news events), §6.11.1 (Contests sub-tab), §6.14 (Constructions panel sketch), §6.15 (Harvest target sketch — post-launch). Extends §5.7 message catalog (territory streams). Updates §9 roadmap with three SYN-driven panel drops. Architecture-of-record updates to v50.
- **v1.2** (May 24 2026 night) — Folded the Claude Design drop-review findings. §3.15 NEVER-invent list, §6.3.1 pass-button, §6.13 Force panel, §10.10 era-fidelity sanity checklist.
- **v1.1** (May 24 2026 evening) — §7.13 map renderer architecture; §10.9 Claude Design re-brief.
- **v1.0** (May 24 2026 afternoon) — Initial draft.

**Companion / superseded docs:** `web_client_vision_and_protocol_v1_2.md` (this is a delta on top), `CLAUDE_DESIGN_BRIEF.md` (folded into v1.0 §7), `web_client_ux_overhaul_v1.md`, `ground_ux_overhaul_design_v1.md`, `web_ux_competitive_analysis.md`, `Map_Redesign_v2.html` (approved per-style footprint mockup), `HANDOFF_MAY25_SYN10.md` (bridge content — folded below), `contestable_wilderness_design_v2.md` §2.6 + §3.12 (data contract source).
**Architecture of record:** `sw_d6_mush_architecture_v50.md` (v49 rollup pending; v51 to follow this doc).

---

## 0. How to read this delta

v1.2 stays in force. v1.3 changes nothing about the dual-interface principle, the protocol versioning model, the map renderer architecture (§7.13), the combat panel, chargen, sheet, comms tabs, Force panel, or the holocron. Pull v1.2 for those.

What's new — and what this doc covers — is:

- **A whole new game-state concept** the panel catalog didn't anticipate: the **region as a first-class entity** with owner, influence, contest state, weekly resource quality, and Anchor NPC. Three new panel specs (§6.2.1, §6.11.1, §6.14) and one sketch (§6.15) come out of this.
- **A canonical UI data-contract layer** (`get_region_data_block`, `get_faction_contests_data`, `get_faction_resource_outlook_data`) that the engine already exposes and pins under test (per SYN.10 handoff). §3.16 documents these.
- **A semantic ANSI→CSS palette** the engine consolidated in SYN.10 — the CSS source of truth for territory rendering. §4.6.
- **A typed news taxonomy** — six concrete event types with stable formatters. §6.10.1.
- **Five new protocol streams/messages** the message catalog (§5.7) gains, with status legend.
- **A region/zone security duality** designers must understand: wilderness rooms derive security from the *region*, city rooms from the *zone*. Same palette, different state source. §4.6 and §6.2.1 cover this.
- **Two follow-up surfaces** from the gap-check revision: an intel-handover availability indicator on the Faction panel (§6.11.2, addressing the SYN.5 discoverability gap) and a city vitality chip on the City panel (§6.16, addressing the SYN.4 state-machine surface gap).

**Reading order:**

- Brian: §0, §3.16, §6.2.1, §6.10.1, §6.11.1, §6.11.2, §6.16, §9 (roadmap update). 10 minutes.
- Engineering Claude (drop sessions): §3.16, §5.7 delta, §6.2.1, §6.10.1, §6.11.1, §6.11.2, §6.14, §6.15, §6.16, §9.
- Claude Design (visual mockups): §3.16, §4.6, §6.2.1, §6.10.1 (including the sample news stream), §6.11.1, §6.11.2, §6.14, §6.16, then the v1.2 §3/§10 primer for context.

**What's NOT in this delta:**

- No combat changes. SYN didn't touch combat.
- No chargen, sheet, comms, holocron, or Force-panel changes.
- No map renderer-architecture changes. SYN hands the renderer overlay *data* (contest pins, ownership boundaries) — vision §7.13.3 already says overlays come from a data layer. No new architecture required.
- No mobile / Phase-5 changes.

---

## 3.16 SYN data contracts (the canonical web-UI inputs)

**The new discipline:** every territory-flavored UI surface reads from the structured dicts exposed by `engine/territory_display.py`. The CLI renderer (`get_region_look_block`) is *one consumer* of these dicts. The web HUD is another. The dicts are pinned under test and stable.

Source of truth: `HANDOFF_MAY25_SYN10.md` §"UI-PIVOT: Data contract".

### 3.16.1 `get_region_data_block(db, region_slug)` → dict

```python
{
  "region_slug": str,                  # the slug as queried
  "region_name": str,                  # humanized name from YAML or slug
  "planet": str | None,                # YAML field
  "security": str,                     # 'lawless' | 'contested' | 'secured'
  "description": str | None,           # long_desc from YAML
  "ownership": {                       # None if un-owned
    "org_code": str,
    "org_name": str | None,
    "tier": str,                       # 'foothold' | 'dominant' | 'no_presence'
    "claimed_at": float | None,        # epoch seconds
  } | None,
  "influence": [                       # sorted by score desc
    {"org_code": str, "score": int, "tier": str},
    ...
  ],
  "resource_outlook": {
    "best": {"type": str, "multiplier": float} | None,
    "worst": {"type": str, "multiplier": float} | None,
    "all": {type: multiplier, ...},
  },
  "active_contest": {                  # None if no contest
    "challenger_org": str,
    "defender_org": str | None,
    "phase": str,                      # 'active', etc.
    "started_at": float,
    "ends_at": float,
    "secs_remaining": float,
    "accumulation": {org_code: score}, # zone influence scores
  } | None,
}
```

### 3.16.2 `get_faction_contests_data(db, org_code)` → dict

```python
{
  "org_code": str,
  "contests": [
    {
      "region_slug": str,
      "region_name": str,
      "role": "challenger" | "defender",
      "opponent_code": str,
      "opponent_name": str,
      "phase": str,
      "secs_remaining": float,
      "accumulation": {org_code: score},
    },
    ...
  ]
}
```

### 3.16.3 `get_faction_resource_outlook_data(db, org_code)` → dict

```python
{
  "org_code": str,
  "regions": [
    {
      "region_slug": str,
      "region_name": str,
      "best": {"type": str, "multiplier": float} | None,
      "worst": {"type": str, "multiplier": float} | None,
      "all": {type: multiplier, ...},
    },
    ...
  ]
}
```

### 3.16.4 Key invariants the UI must respect

These come from the SYN.10 handoff §"UI-PIVOT: Key design decisions to know" and are *binding* on the web client:

1. **Influence tier thresholds are baked in.** `score >= 100` is `dominant`, `>= 50` is `foothold`, else `no_presence`. The UI mirrors these thresholds (don't invent new ones for the visual).
2. **Ownership tier comes from zone influence, not from the `region_ownership` row.** The data dict surfaces the derived tier — the UI reads it from the dict, doesn't re-derive.
3. **Active contest "time remaining" is `ends_at - now`.** This is the resolution-time countdown, not the "culminating fight begins" mark. The UI may surface both if desired (raw fields are available).
4. **Accumulation falls back to zone influence at query time.** No per-contest accumulation column exists. The contest tick updates zone influence via `adjust_territory_influence` — that's the canonical source.
5. **Viewer-org highlight.** `get_region_look_block(viewing_org_code=X)` highlights org X's influence entry. The web UI mirrors this — players want to see "their" position at a glance.
6. **Building completion broadcast is selective.** Only `garrison_annex` (visible faction-power-projection) is global; residence/crafting_station/commerce_stall/cultural_hall stay owner-only.
7. **Independent characters reject `+faction contest` / `+faction resource_outlook`.** The UI mirrors this access model — those sub-tabs are hidden or disabled for independent PCs.
8. **Failure-tolerant rendering.** Every sub-section of `get_region_data_block` is try/except wrapped. Partial data still produces a valid dict (e.g. missing region_quality → empty `resource_outlook`, rest of dict fine). The UI renders what's present and quietly hides what isn't.

### 3.16.5 Stability commitment

Per SYN.10 handoff: *"these shapes are pinned by tests. Adding new fields is safe; renaming or removing existing fields requires coordination with the UI work."*

In practice: the UI can safely read these dicts and trust the shape. Schema additions are forward-compatible. The engineering drops that wire these dicts to web messages should treat the dict structure as the public ABI.

---

## 4.6 Semantic ANSI → CSS palette (territory-flavored surfaces)

SYN.10 consolidated all territory-display ANSI codes into 8 module constants in `engine/territory_display.py`. The web client maps each to a semantic CSS class — this is the CSS source of truth for security tags, contest panels, news brackets, and viewer-org highlights.

| ANSI constant | Code           | Used for                       | Semantic CSS class                  |
|---------------|----------------|--------------------------------|-------------------------------------|
| `_RED`        | `\033[1;31m`   | Lawless tag, threat warnings   | `.security-lawless`, `.threat`      |
| `_YELLOW`     | `\033[1;33m`   | Contested tag, news brackets   | `.security-contested`, `.news-tag`  |
| `_GREEN`      | `\033[1;32m`   | Secured tag, construction-OK   | `.security-secured`, `.success`     |
| `_CYAN`       | `\033[1;36m`   | Accent text, headings          | `.accent`, `.heading`               |
| `_MAGENTA`    | `\033[1;35m`   | Contest panel separator        | `.contest-panel`                    |
| `_BOLD`       | `\033[1m`      | Emphasis (labels, region names)| `.emphasis`                         |
| `_DIM`        | `\033[2m`      | Subtle metadata                | `.metadata`                         |
| `_ITALIC`     | `\033[3m`      | Descriptive flavor (region desc)| `.descriptive`                     |
| `_RESET`      | `\033[0m`      | (end-of-style)                 | —                                   |

All `*_lines` functions in `territory_display.py` accept `ansi=False` to strip codes entirely — useful for test snapshots, log dumps, and any consumer that wants to apply its own theming. The web client subscribes with `ansi=False` and applies the CSS classes from the structured dict.

### 4.6.1 Security-tier duality — IMPORTANT for designers

The web client has **two security-tier sources on the same screen**:

- **Zone-level security** — present on every room, including cities, ships, interiors. Source: the room's `properties.security` field (resolved at world-load time per the S-RES writer-merge from May 2026).
- **Region-level security** — present only on wilderness rooms. Source: `get_region_data_block(region_slug).security`. Wilderness rooms *derive* their effective security from the region per the SYN.2 wilderness-aware security branch.

Both map to the same palette: `lawless` / `contested` / `secured` → red / yellow / green. The visual treatment must be **identical** for both — players don't care that the state comes from different tables, they care that the tag reads consistently.

The room context panel (§6.2) always shows the zone-level tag. The region panel (§6.2.1) shows the region-level tag (which is the *effective* security when the player is in a wilderness room). When both are visible on the same screen and they agree, no special treatment. When they disagree (e.g. a wilderness room inside a higher-tier region), both tags are shown side-by-side; tooltip explains the source.

---

## 5.7 Message catalog — delta on v1.2

v1.2's catalog stands. Add the following five entries; status legend unchanged (Shipped / Partial / Designed / Horizon).

| Message type | Stream | Status | Source of truth |
|---|---|---|---|
| `region_state` | territory | **Horizon** | this doc §3.16.1 — wraps `get_region_data_block` for push delivery |
| `faction_contests_state` | territory | **Horizon** | this doc §3.16.2 — wraps `get_faction_contests_data` |
| `faction_resource_outlook_state` | territory | **Horizon** | this doc §3.16.3 — wraps `get_faction_resource_outlook_data` |
| `territory_news_event` | news | **Partial** | SYN.10 — 6 typed broadcasts already shipped as text strings; the UI work adds the typed wrapper |
| `building_state` | hud | **Horizon** | this doc §6.14 — player constructions per SYN.9 |

**A new `territory` stream is added** to the existing stream list (§5.4). Default subscription on connect includes it. Clients can unsubscribe to reduce bandwidth (e.g. for accessibility-only consumers).

### 5.7.1 The "Partial" call on `territory_news_event`

The six SYN.10 broadcast types (ownership_change × 3, contest_start, contest_resolve × 2, anomaly_defeat, building_completion, building_demolition × 2) currently ship as **pre-formatted text strings** via `session_mgr.broadcast(text)`. The CLI consumes them directly; the web client today would render them as undifferentiated text.

The UI pivot adds a typed wrapper. The engine broadcast site retains the text broadcast for Telnet parity and ALSO emits a structured `territory_news_event` for WebSocket subscribers:

```python
{
  "schema_version": 1,
  "type": "territory_news_event",
  "stream": "news",
  "event_type": "contest_start" | "contest_resolve" | "ownership_change" |
                "anomaly_defeat" | "building_completion" | "building_demolition",
  "region_slug": str,
  "region_name": str,
  "payload": { ... },   # event-type-specific (see §6.10.1)
  "formatted_text": str, # the text that went to Telnet, for diff-free fallback rendering
  "ts": float,
}
```

The `formatted_text` field is a redundancy on purpose — it lets the web client fall back to plain rendering if it doesn't recognize the `event_type`, and it guarantees no information loss vs the Telnet channel.

---

## 6.2.1 Region panel — NEW

The region panel is a sibling of the room context panel (§6.2). It is present whenever the player is in a wilderness room, and queryable on demand for any region by slug.

### What it shows

- **Region name** (large, bold) with **planet** subtitle.
- **Security tag** — `lawless` / `contested` / `secured` chip using the §4.6 palette.
- **Region description** — italic, the long-form flavor text from YAML.
- **Ownership block** — owning faction's sigil + name + tier chip (`foothold` / `dominant` / `no_presence`). Shown only if `ownership` is non-null. If null: a subtle "Unclaimed" line.
- **Influence ladder** — top 3 orgs as horizontal bars, sorted descending. Each bar shows org name, score, and tier label. **Viewer's faction is highlighted** with an accent color marker (§4.6 `.accent`). If the viewer is independent, no highlight.
- **Resource outlook chips** — small chips for best/worst resource types with their multipliers (e.g. `Bantha hides ×1.4 ▲`, `Spice ×0.6 ▼`). Hover for the full `all` breakdown.
- **Active contest panel** (conditional — render only if `active_contest` is non-null):
  - Challenger sigil → Defender sigil (or "Unclaimed seizure" if defender is null).
  - **Countdown to resolution** — large, prominent. Source: `secs_remaining` (i.e. `ends_at - now`).
  - **Accumulation bars** — per-org accumulation scores rendered as competing horizontal bars. Viewer's faction highlighted.
  - **Phase label** — current contest phase (`active`, etc.).
  - Visual treatment uses `.contest-panel` magenta separator from §4.6.

### Why it matters

Region is the wilderness orientation anchor — the equivalent of "room" for indoor play. Players in wilderness will be checking this panel as often as the room panel in cities. The region's contest state is the primary driver of meaningful faction-vs-faction play.

### Wire data

- `region_state` (new — §5.7) — push delivery wrapping `get_region_data_block`.
- REST `/api/region/{slug}` for on-demand fetch (any region, even ones the player isn't in).
- The auto-overlay trigger mirrors the CLI: when the player enters a wilderness room, the client receives a fresh `region_state` and the panel is shown. Standard rooms (cities, ships, interiors) → no region panel.

### Mockup brief (for Claude Design)

Card layout, slightly wider than the room context panel (region info is denser). Header strip: region name + planet + security chip. Body: description in italic. Ownership block: sigil + name + tier chip in a single row. Influence ladder: 3 horizontal bars, each ~24px tall, with org name inline-left, score inline-right, tier chip after score. Resource chips: small pill-shaped, color-coded (best green, worst red, neutral). Contest panel (when active): a visually distinct sub-card with a magenta accent border, large countdown timer, opposing sigils with VS treatment, accumulation bars stacked.

**Show three example mockups:**
1. **Lawless un-owned region** (e.g. Dune Sea before any faction has claimed it). Ownership block: "Unclaimed". Influence ladder: empty or single foothold-tier entry. No contest.
2. **Secured dominant-owned region** (e.g. Republic-held Coruscant district). Full ownership block, dominant tier, influence ladder shows the dominant org plus 1-2 challenger footholds, no contest.
3. **Contested region with active contest** (Republic-held, CIS challenging). Full ownership, contest panel active with `~02:14:33` countdown, accumulation bars roughly even, viewer-faction highlighted.

### Engineering notes

- Auto-subscribe to `region_state` for the player's current region. On room change to a non-wilderness room, panel disappears; on room change to a different wilderness region, the `region_slug` updates and a fresh `region_state` arrives.
- REST `/api/region/{slug}` is independent — used by §6.11.1 contest sub-tab to fetch detail for a region the player isn't in.
- Failure-tolerant: missing sub-fields render as empty / absent. Never block the panel render on a missing field.

---

## 6.10.1 Typed news events (Holonet news ticker — extended)

v1.2 §6.10 specifies the news ticker as a generic stream. SYN.10 ships a **typed event taxonomy** the ticker should now render as distinct event cards rather than undifferentiated text.

### Event taxonomy (6 types, 6 stable formatters)

From `engine/territory_display.py`:

| `event_type` | Trigger | Payload fields |
|---|---|---|
| `ownership_change` | `claim_region` / `unclaim_region` | `org_name`, `action` ∈ `{'claimed', 'lost', 'unclaimed'}` |
| `contest_start` | `engine/contest.py::declare_region_contest` | `challenger_name`, `defender_name` (optional — null for unclaimed seizure) |
| `contest_resolve` | `engine/contest.py::_resolve_defender_win` / `_resolve_challenger_win` | `victor_name`, `defender_won` (bool) |
| `anomaly_defeat` | `engine/wilderness_anomalies.py::_broadcast_anomaly_defeat` | `anomaly_name`, `killer_org` (optional) |
| `building_completion` | `engine/buildings.py::_complete_construction` (garrison_annex only — others stay owner-only) | `building_category`, `owner_name` |
| `building_demolition` | `engine/buildings.py::demolish_building` + eviction (substrate ready — consumer wiring deferred) | `building_category`, `reason` ∈ `{'demolished', 'evicted'}` |

### Rendering

Each event type gets a distinct visual treatment in the ticker:

- **`ownership_change`** — small faction sigil + action verb + region name. Color: action-dependent (claimed = green, lost = red, unclaimed = yellow).
- **`contest_start`** — two opposing sigils with VS treatment, region name, "contest declared" label. Color: yellow (contested).
- **`contest_resolve`** — winning faction sigil, region name, outcome label ("defended" or "seized"). Color: green if defender won, red if challenger won (from the defender's POV; the viewer's POV is handled by the faction filter).
- **`anomaly_defeat`** — trophy/threat icon, anomaly name, region name, optional killer-faction sigil. Color: cyan (accent).
- **`building_completion`** — construction icon, building category, owner faction sigil, region name. Color: green.
- **`building_demolition`** — destruction icon, building category, region name, reason chip. Color: red.

### Expanded news pane

Click-to-expand on the ticker opens the full news pane (v1.2 §6.10). The expanded pane gains:

- **Filter by event type** — checkbox column on the left ("Show: ownership ☑ contests ☑ anomalies ☑ buildings ☑").
- **Filter by faction** — "My faction only" / "All factions" / per-faction toggles.
- **Filter by region** — drop-down of regions the player has touched, or "All".
- **Timeline rendering** — events grouped by hour with relative timestamps ("12 minutes ago").

### Sample news stream (for mockup designers)

Use this six-entry sequence to mock the ticker and the expanded pane. It exercises all six event types and shows them in plausible chronological order, so designers can see how the typed cards read as a *feed* rather than as six isolated examples.

```
[ownership_change]   12:04 — The Galactic Republic has CLAIMED Outer Rim Sector 7.
[contest_start]      12:18 — The Hutt Cartel CHALLENGES the Galactic Republic for Dune Sea.
[anomaly_defeat]     13:42 — A krayt dragon has been slain in Jundland Wastes by the Galactic Republic.
[contest_resolve]    16:18 — The Hutt Cartel has SEIZED Dune Sea from the Galactic Republic.
[building_completion] 17:01 — A garrison annex is now operational in Jundland Wastes (Galactic Republic).
[building_demolition] 17:53 — A garrison annex in Outer Rim Sector 7 has been DEMOLISHED (evicted).
```

Mockup notes: the four-hour contest window between `contest_start` (12:18) and `contest_resolve` (16:18) demonstrates the SYN.3 contest timer. The `building_demolition` reason chip (`evicted`) is one of the two valid values per §6.10.1. Verify designer mockup renders the viewer-faction filter correctly — if the viewer is Republic, `contest_resolve` rendering should use red palette (defender lost); if viewer is Hutt Cartel, green palette (challenger won).

### Persistence — known launch-time gap

Per SYN.10 handoff §"What's NOT in this drop":

> **News digest persistence.** Real-time broadcasts only — no log. Players offline at broadcast time miss the news entirely. UI work could add a news log table + replay surface.

**For launch:** the web client surfaces a single banner at the top of the expanded news pane: *"News history is live-only — you see events that fire while you're online. Persistence is post-launch."* This sets expectations without engineering a backend persistence layer pre-launch.

**Post-launch follow-up:** a server-side `news_log` table + a `GET /api/news?since=<ts>&filter=...` endpoint that returns missed events. The web client subscribes to live events and on connect fetches the log since last seen. Deferred per Brian's call to keep launch scope honest.

### Wire data

- `territory_news_event` (Partial — §5.7.1) for the six SYN.10 types.
- `news_event` (Shipped — existing) for Director AI narrative events. The ticker renders both; the expanded pane filters can separate them.

---

## 6.11.1 Contests sub-tab (lives on the Faction panel §6.11)

The faction reputation radial (§6.11) gets a sub-tab strip below the radial: **Reputation · Contests · Outlook**.

### Contests sub-tab

For factioned players only — independent PCs see this sub-tab disabled or hidden (per §3.16.4 invariant 7).

**What it shows.** Reads from `get_faction_contests_data(viewer_org_code)`. For each contest:

- **Region name** (clickable — opens region panel §6.2.1 in modal/overlay).
- **Role chip** — `Challenger` or `Defender`.
- **Opponent** — sigil + name.
- **Countdown** — `secs_remaining` rendered as `HH:MM:SS`.
- **Accumulation bars** — your faction's score vs opponent's score, with the other influences listed below if any.
- **Phase label** — `active`, etc.
- **Quick action** — `[Travel to region]` button (uses existing travel commands behind the scenes).

**Empty state.** If no active contests: "No active contests. Your faction holds X regions and challenges 0." with a link to the Outlook sub-tab.

### Outlook sub-tab

Reads from `get_faction_resource_outlook_data(viewer_org_code)`. For each owned region:

- **Region name** (clickable → region panel).
- **Best resource chip** — `bantha_hide ×1.4 ▲` (or whatever).
- **Worst resource chip** — `spice ×0.6 ▼` (or whatever).
- **Hover** — full `all` dict.

Sortable by region name, by best multiplier, by worst multiplier. Useful for harvest planning. Refresh cadence: weekly (per the weekly resource quality variance per SYN.6).

### Wire data

- `faction_contests_state` (Horizon — §5.7) — push on contest state-change.
- `faction_resource_outlook_state` (Horizon — §5.7) — push on weekly region-quality recompute.

### Mockup brief

Sub-tab strip below the existing radial (§6.11). The radial stays as-is; this just adds two sibling tabs. Tab content scrolls vertically within the panel — don't take over the full screen. Contest list items as cards (~96px tall each, with the elements above stacked compactly). Outlook list items thinner (~48px each, single-row).

---

## 6.14 Constructions panel — sketch (post-launch refinement)

SYN.9 lets players construct buildings in regions where their faction has presence. Categories:

- `garrison_annex` — faction-power-projection (broadcasts global on completion).
- `residence` — private (owner-only completion broadcast).
- `crafting_station` — private.
- `commerce_stall` — private.
- `cultural_hall` — private.

The vision doc's housing/city material (`cw_housing_design_v1.md`, `player_cities_design_v1.md`) doesn't fully cover this player-level construction loop. It deserves a panel.

### What it shows

**For launch:** a minimal "Your Constructions" sub-tab on the City/Faction panel listing:
- Building name + category + region + completion %.
- Status chip (`under construction`, `operational`, `damaged`, `demolished`).
- Construction timer for in-progress items.
- A `[Manage]` button (opens detail modal; for launch, the modal just hosts the existing CLI commands as buttons — `+building inspect`, `+building maintain`, etc.).

**Post-launch:** a dedicated panel with:
- Per-region build queue.
- Yield projection (resources/credits in vs harvest cost).
- Maintenance forecast (when does the next upkeep tick fire, what does it cost).
- Demolition affordance (with confirmation modal — destruction is destructive, no UI bypass).

### Wire data

- `building_state` (Horizon — §5.7) — push on construction state-change, completion, demolition, maintenance.
- REST `/api/buildings/mine` for full inventory.

### Mockup priority

Low for launch — CLI surfaces (`+building`, `+region <slug>`) cover the immediate need. Worth a Phase-2 placement after the higher-value panels (HUD, room, combat, inventory, comms, region).

---

## 6.15 Harvest target sketch (post-launch)

SYN.6 introduces an **active harvest** loop in wilderness regions — players spend time at a harvest site to extract resources, modulated by the weekly region resource quality. The CLI has commands; the web UI is greenfield.

### For launch

Nothing. The CLI commands work; the region panel §6.2.1 already surfaces the resource outlook chips (best/worst with multipliers) so players have the information they need to choose where to harvest. Adding an active harvest UI is post-launch scope.

### Post-launch sketch

A small "Harvest target" slot on the inventory panel (§6.4): shows the current harvest target (resource type, region, multiplier, progress bar to next yield tick), with a `[Cancel]` affordance. When no active harvest: empty slot with a `[Start harvest…]` button that opens a picker keyed off `get_faction_resource_outlook_data` (or, for independents, the player's own visited regions).

### Wire data

- Existing harvest state messages (engine emits these already for CLI).
- The web wrapper is a Phase-2 task.

### Engineering note

Per SYN.6 engineering notes, the harvest tick fires at known cadence and the engine pushes state per tick. The web wrapper is purely client-side state observation — no new server-side push schema required (uses existing harvest events).

---

## 6.11.2 Intel-handover availability indicator (Faction panel header)

SYN.5 ships espionage-as-influence: factioned PCs can collect intel and hand it over at a faction HQ for influence reward. The CLI command is `+intel handover` and it works today; the issue is **discoverability** — a player carrying handover-ready intel will not know it unless they happen to type the command at the right location.

### What it shows

A small **`[!]` indicator on the Faction panel header** when the viewer's character is carrying intel eligible for handover at the *current* room (i.e. they are at one of their faction's HQs and have pending intel). Hover or tap reveals:

- Number of intel items pending
- Estimated influence reward on handover
- A `[Hand over intel]` action button that fires `+intel handover` behind the scenes

When not at a faction HQ but carrying intel: the indicator is grayed/muted with hover text "Take this to a faction HQ to hand over."

When not carrying intel: indicator hidden.

### Why it matters

Espionage-as-influence is one of the SYN.5 design goals: turn intelligence-gathering into a real influence currency for region contests. If players don't know they have something to hand over, the loop doesn't close. The CLI surface alone is inadequate for first-time discovery.

### Wire data

- Existing `hud_update` extension or a new `intel_handover_ready` field on the faction stream. Engineering-call.
- Server-side: `engine/espionage.py` already exposes the eligibility check (`+intel handover` rejects non-handlers cleanly). A read-only accessor for "is this player at a handover-ready location with handover-ready intel" is the only new server surface needed.

### Launch scope

Recommend **launch-blocking**. The indicator is small but the discoverability problem is real, and the underlying SYN.5 engine work would otherwise be invisible to most players.

### Engineering note

The intel handler NPC seeding follow-up (per architecture v50 §8.18 — `T2.DEF.handler_npcs`) is still pending; once handler NPCs are spawned at the 9 faction HQs, the eligibility check resolves correctly. The UI indicator can ship before the NPC seed (it just won't ever light up in production until the seed lands), or it can ship paired with the seed drop.

---

## 6.16 City panel — vitality chip amendment (SYN.4 follow-up)

SYN.4 ships region-anchored cities + the city **vitality state machine**. Cities now have a vitality value (and underlying state) that drifts based on activity, maintenance, and region health. The existing City panel (per `player_cities_design_v1.md`) predates SYN.4 and shows no vitality.

### What changes

A small **vitality chip on the City panel header**, between the city name and the existing population/coffers blocks:

- Vitality value as a numeric or percent (engineering-call which is more legible).
- Vitality state as a color-coded chip (palette TBD — suggest the §4.6 security palette: thriving = green, stable = cyan, declining = yellow, dying = red).
- Hover reveals the recent vitality delta ("`+3 this week`") and the dominant drivers ("activity high, maintenance current").

### Why it matters

City founders and members need a glanceable answer to "is my city healthy?" Without the chip, players have to type a CLI command after every weekly tick to know.

### Wire data

- `city_state` (existing — extend with `vitality` and `vitality_state` fields).
- The accessor for vitality lives in `engine/player_cities.py` per the SYN.4.b drop.

### Launch scope

Recommend **launch-relevant**. Small chip on an existing panel; cheap to ship. The City panel itself is launch-scope already.

### Engineering note

Vitality update cadence is weekly per SYN.4. The chip can be static between ticks — no per-second updates needed. Push the new value on the weekly recompute and on any vitality-affecting event (city action, maintenance payment, etc.).

---

## 9. Roadmap — delta on v1.2

v1.2's Phase 0–5 structure stands. The following three drops are inserted into Phase 2; everything else is unchanged.

### Phase 2 additions (region/contest/news work)

These slot into the existing Phase 2 ordering. All depend on Phase 1 protocol foundation (§5.3, §5.6, the `subscribe`/`unsubscribe` model, schema versioning).

- **Drop 2.11 — Region panel (§6.2.1)** wired to new `region_state` message and `/api/region/{slug}` REST endpoint. ~1 session. Includes both wire-side (engine emits `region_state` on room change to a wilderness region) and client-side (panel rendering + auto-show on wilderness, hide elsewhere).
- **Drop 2.12 — Typed news events (§6.10.1)** — adds the `territory_news_event` wrapper at the six SYN.10 broadcast sites, extends the news ticker and expanded pane to render typed events. ~1 session. Engineering note: the broadcast sites already emit text via `session_mgr.broadcast(text)`; the new emission is an ADD beside the existing call, preserving Telnet parity.
- **Drop 2.13 — Contests sub-tab + Outlook sub-tab (§6.11.1)** — extends the Faction panel with the two new sub-tabs, wires `faction_contests_state` and `faction_resource_outlook_state` push messages. ~1 session. Engineering note: the `faction_state` message can be extended in-place, or these can ship as separate stream subscriptions (designer's call during the drop).
- **Drop 2.14 — Intel-handover indicator (§6.11.2)** — adds the `[!]` header indicator on the Faction panel. ~0.5 session. Pairs naturally with the `T2.DEF.handler_npcs` content seed drop (per architecture v50 §8.18).
- **Drop 2.15 — City vitality chip (§6.16)** — extends the City panel header with the vitality chip. ~0.5 session. Engineering touch is minimal: extend `city_state` message with `vitality` / `vitality_state` fields, add chip to existing panel.

### Phase 2 ordering (recommended)

After the Phase 1 foundation lands, the recommended Phase 2 sequence — accounting for the SYN deltas — is:

1. **Drop 2.1** — HUD (§6.1).
2. **Drop 2.2** — Room context (§6.2).
3. **Drop 2.11** — Region panel (§6.2.1) — *immediately after 2.2 because region is the wilderness sibling of room.*
4. **Drop 2.3** — Combat console (§6.3) with pass-button + dice transparency.
5. **Drop 2.5** — Tabbed comms (§6.5).
6. **Drop 2.9** + **Drop 2.12** — News pane + typed news events (paired).
7. **Drop 2.8** + **Drop 2.13** + **Drop 2.14** — Faction radial + contest/outlook sub-tabs + intel-handover indicator (triplet on the same panel).
8. **Drop 2.15** — City vitality chip (City panel; pairs with whoever takes the existing City panel work).
9. **Drop 2.4** — Inventory paper doll.
10. **Drop 2.6** — Skill-check ribbon.
11. **Drop 2.7** — Quest / progression tracker.
12. **Drop 2.10** — Holocron (biggest single drop).

The pairings (6 with 12, 7 with 13/14) are tactical: the news pane is much easier to design and verify alongside the typed event taxonomy it renders, and the faction radial gains useful neighbors (contest, outlook, intel indicator) on the same panel.

### Phase 3 additions (map overlays)

v1.2 §9 Phase 3 Drop 3.8 is **Map overlay system (contests, anomalies, weather, territory).** SYN now hands this drop a *richer* set of inputs:

- Contest markers pinned at the contested region's centroid, with the contest countdown rendered in the marker tooltip.
- Ownership boundaries rendered as faction-tinted polygon fills over wilderness region footprints.
- Anomaly markers (Tier 1 / 2 / 3) with the SYN.7/8 anomaly state.
- Building markers (garrison annexes shown publicly; private buildings shown only to the owning faction).

Drop 3.8 spec doesn't change; the *inputs* it consumes are now well-defined per §3.16. No new map drops, just better-defined inputs for the existing one.

### What stays unchanged

- Phase 0 (doc lock).
- Phase 1 (protocol substrate drops 1.1–1.5).
- Phase 2 drops 2.1–2.10 (existing — see above for reorder).
- Phase 3 map drops 3.1–3.10 (only Drop 3.8 gets richer inputs).
- Phase 4 diegetic polish.
- Phase 5 mobile.

### Launch-scope cut (per architecture v50 §8.16)

Brian's call: where does the launch cut land within Phase 2/3? The SYN-driven panels feel **launch-relevant** — the region panel especially, since wilderness is the core differentiator of the SYN pivot and the CLI already surfaces the equivalent. Recommend including the following in launch scope:

- **2.11** (Region panel) — launch-blocking. Wilderness orientation anchor.
- **2.12** (Typed news events) — launch-blocking. The CLI ships news; the web should too.
- **2.14** (Intel-handover indicator) — launch-relevant. Discoverability problem for SYN.5 espionage loop. Cheap to ship; closes a real player-facing gap.
- **2.15** (City vitality chip) — launch-relevant. Trivial extension to an existing launch-scope panel.
- **2.13** (Contest/outlook sub-tabs) — nice-to-have but not blocking. The radial alone covers immediate need; sub-tabs can ship post-launch.

---

## 10.11 SYN deltas checklist (Claude Design re-brief amendment)

Augments §10.9 (re-brief) and §10.10 (era-fidelity checklist) from v1.2. Before any new mockup drop touching territory-flavored surfaces, the visual designer should be able to check:

- [ ] **Region panel design exists** as a sibling of the room context panel (not subordinate, not the same panel).
- [ ] **Security tag duality is honored** — wilderness rooms can show *both* a zone tag and a region tag if they differ; same palette, both visible.
- [ ] **Influence ladder uses the SYN.10 thresholds** — 50/100 for foothold/dominant. No invented thresholds.
- [ ] **Viewer's faction is highlighted** in the influence ladder (per §3.16.4 invariant 5).
- [ ] **Contest countdown uses `secs_remaining`** (not "phase remaining" or some other field — there is no per-phase column).
- [ ] **News events render with typed treatments**, not just colored text. Six distinct event types, six distinct visual treatments.
- [ ] **News persistence gap is surfaced to the player** — banner in the expanded pane noting "live-only for launch."
- [ ] **Independent characters have contest/outlook sub-tabs disabled** — not hidden silently. Empty-state messaging or grayed-out chrome.
- [ ] **Building demolition affordances require a confirmation** — destructive operations don't ship one-click in the UI.
- [ ] **No invented region states** — the only security values are `lawless` / `contested` / `secured`; the only ownership tiers are `foothold` / `dominant` / `no_presence`. Designers don't invent fourth tiers or alternate names.
- [ ] **Anchor NPC names match `engine/contest.py::ANCHOR_NPC_TEMPLATES`** — Republic Sentinel, CIS Tactical Droid, Hutt Enforcer, Jedi Watchman, Black Sun Lieutenant, Trade Federation Commander, Techno Union Overseer, Mandalorian Vanguard, Pyke Lieutenant (plus the `_default` fallback). Never invent "Imperial Patrol," "Rebel Captain," or any GCW-era anchor. This extends the v1.2 §10.10 era-fidelity sanity list — when a contest panel mockup renders an Anchor NPC label, it must pull from this set or be flagged as a checklist failure. (The May 24 design review caught exactly this kind of leak with "Imperial Patrol"; codifying the canonical name set prevents the next leak.)

This checklist is binding on the Claude Design re-engagement (per the v1.2 §10.9 re-brief flow).

---

## Appendix A — What the SYN wave actually delivered (for designer context)

For Claude Design audiences who haven't tracked the engine wave: the SYN.1–10 sequence (May 18–25, 2026) re-shaped wilderness gameplay around **region-keyed ownership and influence**. The relevant engine surfaces the UI now consumes:

| Drop | Engine surface | UI relevance |
|---|---|---|
| SYN.1 | `region_ownership`, `region_garrison`, `claim_region`, `unclaim_region` | Region panel ownership block |
| SYN.2 | Wilderness-aware security (`region` security overrides `zone` security for wilderness rooms) | §4.6.1 security duality |
| SYN.3 | `engine/contest.py` — 7-day contest timer, 4-hour culminating fight, Anchor NPC | Contest panel + sub-tab |
| SYN.4 | Region-anchored cities + vitality state machine | City vitality chip §6.16 (small amendment to existing City panel) |
| SYN.5 | Espionage-as-influence (`+intel handover` at faction HQs) | Intel-handover availability indicator §6.11.2 (Faction panel header) |
| SYN.6 | Active harvest + weekly region resource quality + T5 crafting | Resource outlook chips; harvest sketch §6.15 |
| SYN.7 | Wilderness anomalies Tier 1/2 (single-phase + multi-phase combat) | News anomaly_defeat events; map markers (Drop 3.8) |
| SYN.8 | Tier 3 world bosses + trophies + scaled T5 | Same as SYN.7 |
| SYN.9 | Player-constructed buildings | Constructions panel §6.14 |
| SYN.10 | Display integration — region info block, `+region`, `+faction contest`, `+faction resource_outlook`, news taxonomy | §3.16 data contracts, §4.6 palette, §6.2.1/6.10.1/6.11.1/6.14 panels |

The unifying idea: **wilderness regions are now the unit of meaningful faction-vs-faction play**. The UI's job is to surface the region as a peer of the room — to make region ownership, influence, contests, resource quality, and player constructions visible at a glance.

---

*End of v1.3 delta. v1.4 will fold any sign-off changes from Brian's review of this doc.*
