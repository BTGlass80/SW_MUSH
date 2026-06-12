# Ground UX Overhaul — Design Document v1

*Opus session, April 12, 2026*
*Follows from: `web_client_ux_overhaul_v1.md`, `web_ux_competitive_analysis.md`, `combat_ux_overhaul_design.md`*
*Screenshot reference: Ground combat in Notsub Shipping – Lobby, April 12 2026*

---

## 1. Problem Statement

The space UI has evolved into something genuinely impressive — zone map SVG, tactical radar with sweep animation, ship schematic, shield arc grid, system chips with damage states, power allocation bar, captain's orders badge, crew station awareness, and station-driven quick buttons. It's a *dashboard*. A player in space feels like they're sitting at a console.

The ground UI, by contrast, is a list of labels and values. The screenshot tells the story: a player just fought a lightsaber duel with a Jawa Scrap Boss, got incapacitated, and the sidebar shows... the same static panel it always shows. Character name, condition bar, credits/force/CP numbers, room name, a zone badge, one exit button, one NPC name, and generic quick buttons. The context panel to the right of the terminal shows only the room name and zone text — two lines of information floating in 280px of empty black.

The space UI succeeds because it communicates *what's happening* and *what you can do about it*. The ground UI communicates *where you are* and *what numbers you have*. That's the gap.

### 1.1 Specific Deficiencies (from screenshot analysis)

1. **Context panel is nearly empty on ground.** 280px column shows room name + zone/security one-liner. In space, this same column has a zone map and tactical radar. On ground, it's wasted space.

2. **No room description in the sidebar.** Players must scroll the terminal to re-read room descriptions. The context panel could show this persistently.

3. **Combat panel exists but is minimal.** Round badge, phase tag, combatant list with pips — functional, but compared to the space HUD's hull bars and shield arcs, it's spartan. No initiative timeline, no damage history, no action prompts.

4. **HERE section is bare.** Shows NPC names as amber text with `look`/`talk`/`atk` micro-buttons. No visual distinction between hostile and friendly NPCs. No indication of NPC role (vendor, trainer, quest-giver, guard). No player status indicators.

5. **No equipped loadout display.** The weapon row exists but is hidden by default and shows only a text name. No armor indicator. No indication of carried items relevant to the current context (medpacs, stims, grenades).

6. **No mission/job tracker.** Players must type `missions` to check active quest status. Smuggling job tracker was designed but never wired to ground mode — it only appears for cargo runs.

7. **Quick buttons don't surface contextual actions.** In the screenshot, the player is post-combat and has been teleported somewhere. The buttons still show generic explore mode. No "heal" or "medpac" button when wounded. No "loot" button after killing an NPC. No "rest" button in a safe zone.

8. **No minimap or area orientation.** Space has a zone map. Ground has nothing. Players navigating Mos Eisley's 40 rooms or Nar Shaddaa's 15 rooms have no visual sense of where they are relative to anything.

9. **Credits display is static.** Just a number. No indication of recent changes (earned, spent), no wallet trend. Compare to Torn's animated credit counter.

10. **No ambient information about the location.** Zone type drives mood colors (cantina = warm amber, spaceport = cool blue) but the sidebar doesn't tell you anything *about* the location — security level, faction presence, available services, nearby points of interest.

---

## 2. Design Philosophy

### 2.1 Guiding Principle: Parity with Space

The ground UX should match the space UX in information density, contextual awareness, and visual engagement — adapted for the different nature of ground gameplay. Space is about managing a ship. Ground is about navigating a world, interacting with characters, and making tactical decisions in combat.

### 2.2 The Three Columns

The current layout already has three logical columns:

```
┌──────────────────────────┬────────────────┬──────────┐
│   TERMINAL OUTPUT        │  CONTEXT PANEL │ SIDEBAR  │
│   (game text, ~80ch)     │  (280px)       │ (260px)  │
│                          │                │          │
├──────────────────────────┤                │          │
│   COMMS PANE (28%)       │                │          │
└──────────────────────────┴────────────────┴──────────┘
```

In space, the context panel earns its space with the zone map + radar. On ground, it's nearly empty. This is the primary real estate to fill.

### 2.3 Design Constraints

- **Dual-Interface Principle remains absolute.** Everything in the web UI is derivable from typed commands. No web-only information.
- **Server-side data budget.** Every new sidebar section needs data in `hud_update` or a new message type. Minimize DB queries per HUD update — batch reads, cache when possible.
- **Performance.** No per-frame JS animation loops. CSS transitions and SVG for visual elements. Radar sweep pattern from space UI is the ceiling for animation complexity.
- **Mobile.** Context panel already hides below 1100px. New ground features in the context panel must degrade gracefully — their information should also appear in the sidebar on narrow viewports.

---

## 3. Feature Catalog

### 3.1 Context Panel — Area Map (Tier 1, High Impact)

**The single highest-impact ground feature.** Equivalent to the zone map in space.

A small SVG rendering of the local area — the rooms connected to the player's current room, laid out as a node-link graph. The player's current room is highlighted. Visited rooms show their names; unvisited rooms show as dim nodes.

**Data requirements:**
- `hud_update` gains an `area_map` field:
```python
"area_map": {
    "current": 17,
    "rooms": [
        {"id": 17, "name": "Notsub Shipping - Lobby", "x": 0.5, "y": 0.5},
        {"id": 16, "name": "Notsub Shipping - Warehouse", "x": 0.5, "y": 0.2},
        {"id": 18, "name": "Streets & Markets", "x": 0.5, "y": 0.8},
    ],
    "edges": [
        {"from": 17, "to": 16, "dir": "north"},
        {"from": 17, "to": 18, "dir": "south"},
    ],
    "poi": [
        {"room_id": 18, "type": "vendor", "label": "Market Stalls"},
    ]
}
```

**Layout algorithm:** Server-side BFS from the current room, depth 2 (current room + neighbors + their neighbors). Room coordinates can be pre-computed and stored in the DB (a `map_x`, `map_y` float column on the rooms table), or computed on-the-fly with a simple force-directed layout. Pre-computed is strongly preferred — it gives hand-tuned maps per zone.

**Client rendering:** SVG in the context panel. Rooms as rounded rectangles with names. Current room glows with `--mood-accent`. Edges as lines with directional arrows. Click a room node to send the movement command (if adjacent). POI icons for vendors, trainers, cantinas, docking bays.

**Visual style:** Dark background matching terminal. Rooms as outlined nodes with text inside. Current room filled with accent color. Adjacent rooms clickable (brighter outline). Two-hop rooms visible but dimmer (orientation only, not clickable).

**Why this matters:** Navigation is the #1 activity on ground. Every competitor with a web client (Nexus, Mudlet mappers, MUSHclient) offers a map. This is table stakes.

**Server effort:** Medium — BFS neighbor query, coordinate storage, POI annotation.
**Client effort:** Medium — SVG rendering, click handlers, animation on room change.

---

### 3.2 Context Panel — Room Detail Card (Tier 1, High Impact)

Below the area map, show a persistent room description card.

**Contents:**
- Room name (already present, keep it)
- Room description text (from `look` output, stored in DB)
- Security level badge (colored: green/amber/red)
- Faction presence indicator (if Director AI has zone state data)
- Territory claim tag (if claimed — data already in `hud_update`)
- Available services icons: vendor (shopping bag), trainer (graduation cap), cantina (drink), medical (cross), docking bay (ship), crafting bench (wrench)

**Data requirements:**
- `hud_update` gains `room_description` (string, the room's desc text)
- `hud_update` gains `room_services` (list of strings: `["vendor", "trainer", "cantina"]`)
- Both are simple DB reads from the rooms table + checking for NPC types in the room

**Why this matters:** Players currently see the room description once (when they enter) and it scrolls away. Having it persistent in the context panel means they can reference it during combat, while crafting, or when deciding where to go next. The services icons give at-a-glance information about what this location offers.

**Server effort:** Low — room description is already in DB, services derived from NPC types.
**Client effort:** Low — text rendering + icon row.

---

### 3.3 Sidebar — Enhanced Combat Panel (Tier 1, High Impact)

The current combat panel has: round badge, phase tag, combatant list with health pips, action summary, waiting line. This is functional but doesn't match the visual richness of the space HUD.

**Enhancements:**

**A) Initiative Timeline (visual)**
Replace the text-based combatant list with a vertical timeline showing initiative order. Each combatant gets a card-like row:

```
┌─────────────────────────────┐
│ ⚔ COMBAT        R2          │
│ declaration                  │
├─────────────────────────────┤
│ 17 ▸ Test Jedi         ████ │  ← green, your turn indicator
│ 10 ▸ Jawa Scrap Boss   ██░░ │  ← orange, wounded
└─────────────────────────────┘
```

Each combatant row shows:
- Initiative number (left)
- Name (colored by allegiance: green = you, amber = NPC, cyan = allied player, red = hostile player)
- Health bar (5-segment wound bar, same CSS as existing wound segments)
- Action declared indicator (checkmark or "..." if waiting)
- Cover level indicator (shield icon, 0-3)

**B) Action Prompt Bar**
When it's the player's turn to declare, show a prominent action prompt with context-aware buttons:

```
YOUR TURN — Declare an action:
[Attack] [Dodge] [Aim] [Flee] [Cover] [Use Item] [Pass]
```

The `[Attack]` button auto-targets the last-targeted combatant. `[Use Item]` expands to show medpacs/stims/grenades from inventory.

**C) Damage Feed**
A compact scrolling feed below the combatant list showing the last 3-4 damage events:

```
  You → Jawa Scrap Boss: HIT (Wounded)
  Jawa Scrap Boss → You: PARRIED
```

Color-coded by outcome: green for hits you land, red for hits you take, dim for misses/parries.

**Data requirements:** All of this data is already in `combat_state` or can be added trivially. The damage feed requires a new `combat_events` array in the `combat_state` message:
```python
"events": [
    {"attacker": "Test Jedi", "target": "Jawa Scrap Boss",
     "result": "hit", "wound": "wounded", "weapon": "lightsaber"},
]
```

**Server effort:** Low — combat_state message extension.
**Client effort:** Medium — new combatant row layout, action prompt, damage feed scroll.

---

### 3.4 Sidebar — Equipped Loadout Section (Tier 2, Medium Impact)

Replace the hidden single-line weapon row with a proper loadout section.

```
┌─────────────────────────────┐
│ LOADOUT                      │
│ ⚔ DL-44 Heavy Blaster       │
│ 🛡 Blast Vest (Torso +1D)   │
│ 💊 Medpac ×3                │
│ 🧪 Stimpack ×1              │
└─────────────────────────────┘
```

Shows equipped weapon, equipped armor (if any), and consumables that are contextually relevant (healing items when wounded, grenades in combat, tools when near a crafting bench).

**Data requirements:** Extend `hud_update` with:
```python
"loadout": {
    "weapon": {"name": "DL-44 Heavy Blaster", "damage": "5D"},
    "armor": {"name": "Blast Vest", "location": "torso", "bonus": "+1D"},
    "consumables": [
        {"name": "Medpac", "count": 3, "type": "healing"},
        {"name": "Stimpack", "count": 1, "type": "boost"},
    ]
}
```

**Server effort:** Low-Medium — query equipment and inventory, filter to relevant items.
**Client effort:** Low — render list with icons.

---

### 3.5 Sidebar — HERE Section Overhaul (Tier 2, Medium Impact)

The current HERE section shows NPC names in amber with tiny `look`/`talk`/`atk` buttons. Improve it:

**A) Role Icons**
Each NPC/player gets a role icon prefix:
- 🛒 Vendor/trader
- 🎓 Trainer
- ⚔️ Hostile (red)
- 🛡 Guard/patrol
- 💬 Quest/dialogue NPC
- 🔧 Mechanic/shipwright
- 👤 Player character

**B) Status Indicators**
- Hostile NPCs show a red outline or tint
- Wounded NPCs show a reduced health indicator
- Players show online/idle status
- Trainers show "CAN TRAIN" badge if the player has unspent CP and trainable skills

**C) Interaction Menu**
Clicking an NPC name expands an inline menu with all valid actions (the current `look`/`talk`/`atk` buttons, but smarter):
- Vendor NPCs: `look`, `buy`, `sell`, `list`
- Trainers: `look`, `talk`, `train`
- Hostile NPCs: `look`, `attack`
- Quest NPCs: `look`, `talk`, `missions`
- Other players: `look`, `whisper`, `challenge`

**Data requirements:** Extend `room_contents.npcs` with:
```python
{"id": 12, "name": "Wuher", "role": "vendor",
 "hostile": False, "wound_level": 0,
 "actions": ["look", "talk", "buy", "sell"]}
```

NPC role is derivable from NPC type/template data already in the DB. The `actions` list is determined server-side based on NPC type + security level + player state.

**Server effort:** Medium — NPC role classification, action list generation.
**Client effort:** Medium — icon rendering, expandable interaction menus.

---

### 3.6 Sidebar — Active Quests/Jobs Tracker (Tier 2, Medium Impact)

A persistent section showing active missions, bounties, and smuggling jobs.

```
┌─────────────────────────────┐
│ ACTIVE JOBS                  │
│ 📦 Smuggle: Spice → Kessel  │
│    Cargo: 2/3 crates loaded  │
│    Risk: ███░ High           │
│ 🎯 Bounty: Greedo           │
│    Last seen: Mos Eisley     │
│ 📋 Mission: Imperial Patrol  │
│    Objective: Report to HQ   │
└─────────────────────────────┘
```

**Data requirements:** New `active_jobs` array in `hud_update`:
```python
"active_jobs": [
    {"type": "smuggle", "label": "Spice → Kessel",
     "progress": "2/3 crates", "risk": "high"},
    {"type": "bounty", "target": "Greedo",
     "last_seen": "Mos Eisley"},
    {"type": "mission", "label": "Imperial Patrol",
     "objective": "Report to HQ"},
]
```

This pulls from the `smuggling_jobs`, `bounty_contracts`, and `missions` tables.

**Server effort:** Medium — aggregate query across three tables.
**Client effort:** Low — render list with type icons.

---

### 3.7 Context Panel — Location Services Panel (Tier 2, Medium Impact)

Below the room description card, show what's available in the immediate area (current zone):

```
NEARBY SERVICES
  🍺 Chalmun's Cantina (2 rooms south)
  🛒 Market Stalls (1 room south)
  🚀 Docking Bay 94 (3 rooms east)
  🔧 Venn Kator, Shipwright (Docking Bay 94)
  🎓 Sergeant Kreel, Combat Trainer (Barracks)
```

Each entry is clickable — sends a series of movement commands (auto-walk) or shows the path on the area map.

**Data requirements:** Server-side BFS from current room, filtered to rooms containing service NPCs or tagged with service types. Limited to depth 4-5 to keep the list short.

```python
"nearby_services": [
    {"name": "Chalmun's Cantina", "room_id": 5,
     "type": "cantina", "distance": 2, "direction": "south"},
]
```

**Server effort:** Medium — BFS with service filtering.
**Client effort:** Low-Medium — render with click-to-walk.

---

### 3.8 Sidebar — Smart Quick Buttons Upgrade (Tier 2, Low-Medium Impact)

The context-sensitive quick buttons already switch between 8 modes. Enhance them:

**A) Wound-Aware Buttons**
When the player is wounded and NOT in combat, inject a `[Heal]` or `[Medpac]` button if they have healing items. When incapacitated, show `[Wait for help]` or similar.

**B) Post-Combat Buttons**
After combat ends (detected by `combat_state.active` transitioning from true to false), briefly show a post-combat mode:
- `[Loot]` — if there are dead NPCs in the room
- `[Heal]` — if wounded
- `[Rest]` — if in a secured zone
- `[Look]` — re-examine the room

This mode auto-clears after 30 seconds or on room change.

**C) Crafting Context**
When near a crafting bench NPC (data from `room_contents`), show:
- `[Craft]`, `[Schematics]`, `[Resources]`

**D) Training Context**
When near a trainer NPC:
- `[Train]`, `[Skills]`, `[Sheet]`

**Data requirements:** Minimal — most of this is client-side logic based on existing `hud_update` fields (`wound_level`, `room_contents.npcs`, `combat_state`).

**Server effort:** None — purely client-side.
**Client effort:** Medium — new mode detection logic, timer for post-combat mode.

---

### 3.9 Sidebar — Credit Activity Ticker (Tier 3, Low Impact)

Show recent credit changes with a brief animation:

```
CREDITS: 100,117
  +500 (bounty reward)     2m ago
  -150 (medpac purchase)  12m ago
```

**Data requirements:** New `credit_events` array in `hud_update`, or a separate `credit_event` message type sent when credits change:
```python
{"type": "credit_event", "amount": 500, "reason": "bounty reward"}
```

Client maintains a local ring buffer of the last 5 events with timestamps.

**Server effort:** Low — emit event on credit change (already happens in multiple places).
**Client effort:** Low — render list, animate new entries.

---

### 3.10 Context Panel — Faction Influence Gauge (Tier 3, Low Impact)

A visual gauge showing the faction balance in the current zone, pulling from the Director AI's zone state:

```
ZONE INFLUENCE
  Imperial ████████░░ 78%
  Rebel    ██░░░░░░░░ 18%
  Criminal █░░░░░░░░░  4%
```

Color-coded (Imperial = white/red, Rebel = blue/orange, Criminal = purple/green). Shows which faction is dominant and whether the zone is contested.

**Data requirements:** Already partially in `hud_update` via `alert_level` and `alert_faction`. Extend with full faction percentages:
```python
"zone_influence": {
    "imperial": 0.78,
    "rebel": 0.18,
    "criminal": 0.04,
}
```

**Server effort:** Low — Director AI already computes this.
**Client effort:** Low — horizontal bar rendering.

---

### 3.11 Context Panel — Director AI Story Feed (Tier 3, Medium Impact)

A compact narrative feed in the context panel showing recent Director AI events for the current zone:

```
ZONE INTEL
  ▸ Imperial patrols increased after
    smuggler activity near Bay 94
  ▸ Rumors of Rebel sympathizers
    in the cantina district
  ▸ Bounty posted: 2,000cr for info
    on missing cargo shipment
```

This transforms the Director AI from a background system into visible narrative texture. Each entry is generated by the Director and pushed via the existing `news_event` message type.

**Data requirements:** Zone-filtered `news_event` messages, stored client-side in a per-zone buffer.

**Server effort:** Medium — Director AI needs to generate zone-scoped narrative blurbs.
**Client effort:** Low — render feed with fade-in animation.

---

### 3.12 Sidebar — CP Progression Indicator (Tier 3, Low Impact)

Show progress toward the next Character Point tick:

```
CP PROGRESS
  ████████░░ 8/10 actions
  Next CP in ~2 actions
```

This makes the CP progression system visible and motivating. Players can see that their actions are counting toward advancement.

**Data requirements:** `hud_update` gains `cp_progress`:
```python
"cp_progress": {
    "actions": 8,
    "threshold": 10,
    "next_cp_est": 2,
}
```

**Server effort:** Low — CP tick counter already exists.
**Client effort:** Low — progress bar.

---

## 4. Layout Plan

### 4.1 Context Panel (280px, right of terminal text)

Vertical stack, top to bottom:

| Section | Height | Priority |
|---------|--------|----------|
| **Area Map** (SVG) | ~200px | Tier 1 |
| **Room Detail Card** | ~120px, flexible | Tier 1 |
| **Location Services** | ~100px, collapsible | Tier 2 |
| **Zone Influence** | ~60px | Tier 3 |
| **Director Story Feed** | flex remainder | Tier 3 |

The context panel scrolls vertically if content exceeds viewport. The area map is sticky/pinned to the top.

### 4.2 Sidebar (260px)

Vertical stack, top to bottom:

| Section | Visibility | Priority |
|---------|-----------|----------|
| **Character** | Always | Existing |
| **Condition** (wound bar) | Always | Existing |
| **Stats** (credits, FP, CP, DSP) | Always | Existing, enhanced |
| **Loadout** | When equipped | Tier 2 |
| **Location** | Always | Existing |
| **Combat Panel** (enhanced) | In combat | Tier 1 |
| **Active Jobs** | When jobs active | Tier 2 |
| **Exits** | Always | Existing |
| **Here** (enhanced) | When populated | Tier 2 |
| **Shops** | When vendors present | Existing |
| **CP Progress** | Always | Tier 3 |
| *flex spacer* | — | — |
| **Quick Buttons** (enhanced) | Always, bottom-anchored | Tier 2 |

---

## 5. Visual Design Notes

### 5.1 Design Language Consistency

All new ground sections use the same design language as the space HUD:

- **Section headers:** `font-family: var(--font-display)` (Orbitron), 8px, uppercase, letterspaced, `color: var(--text-dim)`
- **Data values:** `font-family: var(--font-mono)` (Share Tech Mono), 13-14px
- **Color accents:** CSS variables only — `--accent-green`, `--accent-amber`, `--accent-red`, `--accent-cyan`
- **Bars and gauges:** Same segment-based pattern as wound bar and hull bar. 4px height, 2px gap, rounded ends.
- **Cards/containers:** `background: rgba(255,255,255,0.04)`, `border: 1px solid var(--border-dim)`, `border-radius: 3px`
- **Interactables:** Hover state `background: rgba(255,255,255,0.08)`, `cursor: pointer`

### 5.2 Area Map Visual Style

The area map SVG should feel like a tactical overlay, not a tourist map:

- Dark background matching terminal
- Room nodes as rounded rectangles, 60×24px, outlined in `var(--border-mid)`
- Current room: filled with `var(--mood-accent)` at 20% opacity, border in `var(--mood-accent)`
- Adjacent rooms: outlined in `var(--accent-cyan)`, clickable
- Two-hop rooms: outlined in `var(--border-dim)`, not clickable
- Edges as 1px lines in `var(--border-dim)`, with small directional indicators
- POI icons as small SVG symbols inside or beside room nodes
- Subtle pulse animation on current room node (reuse existing `pulse` keyframe)
- Room transition: animate the view shifting to re-center on the new room

### 5.3 Combat Panel Visual Style

The enhanced combat panel should feel urgent:

- When combat is active, the combat section gets a subtle red left-border accent (2px solid `var(--accent-red)`)
- Initiative timeline entries animate in on round start (staggered fade-in, 50ms per entry)
- Damage feed entries slide in from the right
- Action prompt pulses gently when it's the player's turn
- On combat end, the section fades out over 1 second

### 5.4 Mood Integration

The ambient mood system (zone-keyed CSS custom properties) should extend to new ground sections:

- Area map edge colors shift with mood
- Room detail card border-top color matches mood
- Location services icons tint with mood accent
- Combat panel overrides mood to `combat` (red) regardless of zone

---

## 6. Implementation Drop Plan

### Drop 1: Room Detail Card + Enhanced Room Description (Tier 1, ~2 hours)

**Server changes:**
1. Add `room_description` field to `hud_update` payload — read from `rooms.description`
2. Add `room_services` field — derived from NPC types in room (vendor, trainer, etc.)

**Client changes:**
1. Populate `ctx-room-desc` with actual room description text
2. Add service icon row below description
3. Add security badge (already exists in sidebar, mirror to context panel)
4. Style the card with proper typography and spacing

**Files:** `server/session.py`, `static/client.html`

### Drop 2: Area Map — Server Data (Tier 1, ~3 hours)

**Server changes:**
1. Add `map_x`, `map_y` REAL columns to `rooms` table (ALTER TABLE, idempotent)
2. Write `build_area_map(room_id, db, depth=2)` function — BFS from current room, return nodes + edges + POI
3. Add hand-tuned coordinates for Mos Eisley rooms in `build_mos_eisley.py`
4. Add `area_map` field to `hud_update`

**Files:** `db/database.py`, `server/session.py`, `build_mos_eisley.py`, new `engine/area_map.py`

### Drop 3: Area Map — Client Rendering (Tier 1, ~3 hours)

**Client changes:**
1. Replace `ctx-ground` section with area map SVG
2. Implement node layout, edge rendering, current room highlight
3. Click handlers for adjacent room navigation
4. Animate room transitions (re-center view, pulse new room)
5. POI icon set (small SVG symbols)

**Files:** `static/client.html`

### Drop 4: Enhanced Combat Panel (Tier 1, ~3 hours)

**Server changes:**
1. Add `events` array to `combat_state` message (last N damage events)
2. Add `cover_level` and `aim_bonus` to combatant entries (already in design)

**Client changes:**
1. Redesign combatant list as initiative timeline with health bars
2. Add action prompt bar with context-aware buttons
3. Add damage feed section
4. Wire combat-specific quick buttons to action prompt
5. Post-combat mode detection + temporary button set

**Files:** `engine/combat.py`, `static/client.html`

### Drop 5: HERE Section Overhaul + Loadout (Tier 2, ~2 hours)

**Server changes:**
1. Add `role` and `hostile` fields to `room_contents.npcs`
2. Add `loadout` field to `hud_update`

**Client changes:**
1. NPC role icons
2. Expanded interaction menus
3. Loadout section rendering
4. Wound-aware quick button injection

**Files:** `server/session.py`, `static/client.html`

### Drop 6: Active Jobs Tracker (Tier 2, ~2 hours)

**Server changes:**
1. Aggregate active jobs from smuggling/bounty/mission tables
2. Add `active_jobs` array to `hud_update`

**Client changes:**
1. Render jobs section with type icons and progress
2. Show/hide based on active job count

**Files:** `server/session.py`, `static/client.html`

### Drop 7: Smart Quick Buttons Upgrade (Tier 2, ~1 hour)

**Client changes only:**
1. Post-combat mode detection + timer
2. Wound-aware heal button injection
3. Crafting/training context detection from room_contents
4. NPC role-based button suggestions

**Files:** `static/client.html`

### Drop 8: Location Services + Nearby POI (Tier 2, ~2 hours)

**Server changes:**
1. BFS service discovery from current room (depth 4-5)
2. Add `nearby_services` to `hud_update`

**Client changes:**
1. Render services panel in context area
2. Click-to-walk (send movement command sequence)
3. Highlight path on area map

**Files:** `server/session.py`, `engine/area_map.py`, `static/client.html`

### Drop 9: Polish — Credits Ticker, CP Progress, Zone Influence (Tier 3, ~2 hours)

**Server changes:**
1. `credit_event` message type on credit changes
2. `cp_progress` in `hud_update`
3. `zone_influence` percentages in `hud_update`

**Client changes:**
1. Credit activity ticker with animation
2. CP progress bar
3. Zone influence gauge in context panel

**Files:** `server/session.py`, `engine/economy.py` (credit event hooks), `static/client.html`

### Drop 10: Director Story Feed (Tier 3, ~2 hours)

**Server changes:**
1. Director AI generates zone-scoped narrative blurbs
2. `news_event` messages with zone filter

**Client changes:**
1. Zone Intel section in context panel
2. Filter incoming news_events by current zone
3. Fade-in animation on new entries

**Files:** `engine/director.py`, `static/client.html`

---

## 7. Estimated Total Effort

| Drop | Feature | Server | Client | Total |
|------|---------|--------|--------|-------|
| 1 | Room Detail Card | 30min | 1.5h | ~2h |
| 2 | Area Map — Server | 3h | — | ~3h |
| 3 | Area Map — Client | — | 3h | ~3h |
| 4 | Enhanced Combat Panel | 1h | 2h | ~3h |
| 5 | HERE + Loadout | 1h | 1h | ~2h |
| 6 | Active Jobs Tracker | 1.5h | 30min | ~2h |
| 7 | Smart Quick Buttons | — | 1h | ~1h |
| 8 | Location Services | 1.5h | 30min | ~2h |
| 9 | Credits/CP/Influence | 1h | 1h | ~2h |
| 10 | Director Story Feed | 1.5h | 30min | ~2h |
| **Total** | | | | **~22h** |

Tier 1 (Drops 1-4): ~11 hours — the core transformation.
Tier 2 (Drops 5-8): ~7 hours — meaningful enhancements.
Tier 3 (Drops 9-10): ~4 hours — polish and flavor.

---

## 8. Before/After Comparison

### Before (Current Ground UI — from screenshot)

**Context panel:** Room name, zone + security one-liner. 95% empty.
**Sidebar:** Character name → Condition bar → Credits/Force/CP numbers → Room name → Zone badge → 1 exit → 1 NPC name with tiny buttons → Generic quick buttons.
**Information density:** ~12 data points visible.
**Contextual awareness:** Near zero. Same display in combat, exploration, shopping, crafting.

### After (Full implementation)

**Context panel:** Area map with 10-15 room nodes → Room description with service icons → Nearby services list → Zone influence gauge → Director story feed.
**Sidebar:** Character → Condition → Stats (with credit ticker) → Loadout → Location → Combat panel (when fighting, with initiative timeline, damage feed, action prompts) → Active jobs → Exits → Enhanced HERE with role icons → Shops → CP progress → Smart quick buttons.
**Information density:** ~40-50 data points visible, contextually filtered.
**Contextual awareness:** High. UI responds to combat, exploration, trading, crafting, post-combat, wound state, and zone characteristics.

---

## 9. Interaction with Existing Design Documents

This document extends and partially supersedes:

- **`web_client_ux_overhaul_v1.md`** — That doc proposed width negotiation, comms pane split, and context-sensitive buttons. Width negotiation and comms pane are delivered. This doc picks up the remaining ground-mode improvements and goes deeper.

- **`web_ux_competitive_analysis.md`** — That doc identified the gaps (clickable room contents, character gauge, mobile responsiveness, comms separation). This doc provides the implementation plan for the ground-specific items. Mobile responsiveness remains a separate concern (already specc'd there).

- **`combat_ux_overhaul_design.md`** — Phase 2 (web combat panel) is subsumed by Drop 4 here. Phase 3 (verb variety, narrative polish) remains its own workstream.

- **`architecture_section_21_web_client.md`** — Section 21.3 Tier 2 items (inventory quick-view, zone alert indicator) are covered by Drops 5 and 9 respectively.

---

## 10. Open Questions

1. **Area map coordinate storage.** Pre-computed (`map_x`, `map_y` on rooms table) vs. on-the-fly force layout. Recommendation: pre-computed, with a `@admin mapcoord <room_id> <x> <y>` command for hand-tuning. Auto-layout as fallback for rooms without coordinates.

2. **Area map scope.** Depth 2 BFS gives ~10-20 rooms on screen. Should it be configurable? Should there be a "full zone map" toggle that shows all rooms in the zone? Recommendation: depth 2 default, with a toggle for full zone view (scrollable SVG).

3. **Room description length.** Some rooms have multi-paragraph descriptions. Truncate in context panel with "..." and a "Show full" toggle? Recommendation: yes, cap at 3 lines (about 180 chars) with expand toggle.

4. **HUD update payload size.** Adding area_map, room_description, loadout, active_jobs, nearby_services, etc. significantly increases the `hud_update` JSON. Should some of these be separate message types sent only on room change? Recommendation: yes. `area_map` and `room_description` and `nearby_services` should be a separate `room_detail` message sent only on room change, not on every command. `loadout` and `active_jobs` update on `hud_update` since they can change from any command.

5. **Auto-walk from services panel.** Should clicking a nearby service auto-walk the player there (sending multiple movement commands)? This is convenient but could trigger combat in hostile rooms along the path. Recommendation: auto-walk only through secured rooms. If the path crosses contested/lawless territory, show the path on the map but require manual movement.

---

## 11. Architecture Update Notes (for v23)

When this design is implemented, update `sw_d6_mush_architecture_v23.md`:

**§21 Web Client:**
- Add `room_detail` to message type registry (sent on room change)
- Update context panel description (area map + room card + services)
- Mark Tier 2 items as delivered as each drop lands
- Document area map coordinate system and BFS parameters

**§18 Invariants:**
- "Area map: BFS depth 2, max 20 rooms. Coordinates stored in rooms.map_x/map_y. Fallback: force-directed layout."
- "HUD payload split: `hud_update` for per-command data, `room_detail` for per-room data, `combat_state` for combat data, `space_state` for space data."

**New file registry:**
- `engine/area_map.py` — area map builder, BFS, coordinate fallback
