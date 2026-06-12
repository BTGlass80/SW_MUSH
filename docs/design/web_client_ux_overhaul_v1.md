# Web Client UX Overhaul — Design Document v1

*Opus session, April 10, 2026*
*Follows from: `opus_handoff_ui_eval_apr11.md`, `web_ux_competitive_analysis.md`*

---

## Problem Statement

The SW_MUSH web client (`static/client.html`, 3,346 lines) has a capable engine underneath — 190 commands, space flight with 7 crew stations, AI-driven NPCs, combat with initiative/declarations, crafting, trading — but the presentation doesn't communicate that richness. The web client is currently a **terminal emulator with a thin sidebar**, closer to "PuTTY with a HUD strip" than a game client.

### Specific Issues Identified (Screenshots, April 10, 2026)

1. **Dead space dominance** — Terminal text runs full-width (~140ch on 1920px monitor) with no `max-width` constraint. Short game lines float in vast dark emptiness.
2. **Space mode doesn't activate** — Player is on bridge, has launched, receiving patrol COMMS — sidebar still shows ground HUD. The `space_state` message isn't reaching the client (likely `get_ship_by_bridge` or `docked_at` issue).
3. **`[object Object]` in exits** — Exit buttons render raw JS object stringification instead of labels. Data format mismatch between server and client.
4. **Word wrapping** — `white-space: pre-wrap` wraps at container edge (1670px), not at readable width. 80-char server-formatted lines render as unwrapped strips.
5. **Sidebar underutilized** — 250px, static quick buttons regardless of context, no combat/space context sensitivity.
6. **Comms buried** — The comlink feed competes with sidebar sections in a small scrollable area. Chat/sensor/system messages scroll away during combat.

---

## Design Philosophy

### Goal
Transform from **terminal emulator with sidebar** → **game dashboard with embedded terminal**.

### Principles
1. **Dual-Interface Principle remains absolute** — Text output is canonical. Web client adds visual convenience, never gates content.
2. **Constrain, don't expand** — The terminal text should occupy ~80ch max, creating breathing room for contextual panels.
3. **Context sensitivity** — UI should respond to game state. Ground/space/combat/trade modes change what the player sees.
4. **Comms are first-class** — Chat, sensors, system messages get their own dedicated pane, not a sidebar afterthought.
5. **Progressive disclosure** — Show essentials at a glance, details on demand.

---

## Architecture: Layout Changes

### Current Layout (CSS Grid)
```
grid-template-columns: 1fr var(--sidebar-w)  /* 250px */
grid-template-rows: var(--header-h) 1fr var(--input-h)

┌──────────────────────────────────┬─────────┐
│            HEADER                │ (spans) │
├──────────────────────────────────┼─────────┤
│                                  │         │
│         TERMINAL (full width)    │ SIDEBAR │
│         ~140ch on 1920px         │  250px  │
│                                  │         │
├──────────────────────────────────┼─────────┤
│         INPUT BAR                │         │
└──────────────────────────────────┴─────────┘
```

### Proposed Layout
```
--sidebar-w: 250px  (unchanged — sidebar was fine)
--comms-h: 30%      (new: comms pane fraction)

┌──────────────────────────────────┬─────────┐
│            HEADER                │ (spans) │
├──────────────────────────────────┼─────────┤
│                                  │         │
│  GAME OUTPUT (full 1fr width)    │ SIDEBAR │
│  Text fills naturally because    │  250px  │
│  server now formats to ~100ch    │         │
│  instead of 72ch                 │         │
├──────────────────────────────────┤         │
│  COMMS PANE (30% of terminal)    │         │
│  Tabs: All | IC | OOC | Sys     │         │
├──────────────────────────────────┼─────────┤
│         INPUT BAR                │         │
└──────────────────────────────────┴─────────┘

The dead space fix is SERVER-SIDE, not CSS:
1. Client sends actual terminal width (in chars) on WebSocket connect
2. Server uses that width in Fmt() instead of hardcoded 72
3. Fmt.prose_width caps at MAX_PROSE_WIDTH (100ch) for readability
4. Text fills the terminal naturally — no CSS max-width needed
```

Key changes:
- `.output-line` gets `max-width: 80ch` — text wraps at readable width
- Terminal pane splits vertically: game output (top ~70%) + comms (bottom ~30%)
- Comms pane has its own tab bar (moved from sidebar), receives `[COMMS]`, `[SENSORS]`, `[SYSTEM]`, `[MARKET]`, chat, OOC
- Sidebar widens to 260px for better readability
- Gutter space (between 80ch text and sidebar) remains dark — atmospheric negative space

---

## Drop Plan

### Drop 1: Width Negotiation + Exit Bug Fix (Client + Server, ~1 hour)

**The dead space root cause:** WebSocket sessions are created with `width=72` (hardcoded in `websocket_handler.py`). The client never sends a resize. `Fmt(width=72).prose_width` = min(68, 100) = 68. All text wraps at 68 characters — leaving 60% of the terminal empty on a 1920px monitor.

**Changes:**
1. **Client sends width on connect** — On WebSocket open, client calculates the terminal's character width from `#output.clientWidth / charWidth` and sends `{"type": "resize", "width": N, "height": N}`. Also sends on window resize.
2. **Server handles resize message** — `websocket_handler.py` reads the resize JSON and updates `session.width`. Remove the `wrap_width` cap of 78 for WebSocket sessions (CSS handles visual wrapping).
3. **Fix `[object Object]` in exit buttons** — Add robust fallback: `var dirLabel = (typeof exitEntry === 'object') ? (exitEntry.label || exitEntry.dir || JSON.stringify(exitEntry)) : String(exitEntry);`
4. **Fix `wrap_width` for WebSocket** — Change `session.wrap_width` to return `min(self.width, 120)` instead of `min(self.width, 78)`, or remove the cap entirely for WebSocket sessions and let `Fmt.MAX_PROSE_WIDTH` (100) handle readability.

**Files:** `static/client.html`, `server/session.py`, `server/websocket_handler.py`

### Drop 2: Comms Split Pane (CSS + JS, ~2 hours)

**Changes:**
1. Restructure `.terminal` interior: game output div (flex: 7) + comms div (flex: 3)
2. Move comlink tab bar + news items from sidebar into the comms pane
3. Add resizable divider (CSS `resize: vertical` or JS drag handle)
4. Comms pane inherits the existing `addNewsItem()` / tab filtering logic
5. Remove the `news-panel` section from the sidebar

**Files:** `static/client.html` only

### Drop 3: Context-Sensitive Quick Buttons (JS, ~1 hour)

**Changes:**
1. Define button sets per mode:
   - `explore`: look, inv, score, who, jobs, help
   - `combat`: dodge, aim, attack, flee, pass, cover
   - `space`: (already exists in `station_buttons` from `space_state`)
   - `docked`: launch, status, crew, repair, cargo
2. Client detects mode from `combat_state.active`, `space_state.active`, ground default
3. Quick buttons section swaps content on mode change

**Files:** `static/client.html` only (pure client-side)

### Drop 4: Space Panel Activation Debug (Server + Client, ~1 hour)

**Changes:**
1. Add logging to `LookCommand` space_state path — log whether `get_ship_by_bridge` returns a ship, what `docked_at` is
2. Verify the `except Exception: pass` isn't swallowing a real error
3. Test that `launch` command clears `docked_at` in the DB
4. If `space_state` is sending but client isn't receiving: check `send_json` path

**Files:** `parser/builtin_commands.py`, `parser/space_commands.py`

### Drop 5: Sidebar Polish (CSS, ~1 hour)

**Changes:**
1. Quick buttons section anchored to bottom of sidebar with `margin-top: auto`
2. Room contents "HERE" section always visible (not gated on `display:none`)
3. Exit buttons show full labels (e.g., "down (Pit Floor)") not just direction
4. Add equipped weapon indicator to stats section (from `hud_update`)

**Files:** `static/client.html`, minor `server/session.py` for equipped weapon in HUD

---

## Server-Side Width Fix

### Width Negotiation Protocol
```javascript
// Client: on WebSocket connect
var charWidth = measureCharWidth(); // measure a monospace char in #output
var termCols = Math.floor(output.clientWidth / charWidth);
ws.send(JSON.stringify({type: 'resize', width: termCols, height: 50}));

// Also on window resize (debounced)
window.addEventListener('resize', debounce(function() {
    var cols = Math.floor(output.clientWidth / charWidth);
    if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({type: 'resize', width: cols, height: 50}));
    }
}, 300));
```

```python
# Server: websocket_handler.py — in read loop
if msg_type == 'resize':
    session.width = min(max(data.get('width', 80), 40), 200)
```

```python
# Server: session.py — raise the wrap_width cap
@property
def wrap_width(self) -> int:
    if self.protocol == Protocol.WEBSOCKET:
        return self.width  # Fmt.prose_width caps at 100 anyway
    return min(self.width, 78)  # Telnet stays conservative
```

### Comms Pane
```css
.terminal-inner {
    display: flex;
    flex-direction: column;
    height: 100%;
}

.game-output {
    flex: 7;
    overflow-y: auto;
}

.comms-pane {
    flex: 3;
    min-height: 80px;
    max-height: 40%;
    border-top: 1px solid var(--border-dim);
    overflow-y: auto;
    background: rgba(0,0,0,0.08);
}
```

### Context-Sensitive Buttons
```javascript
var MODE_BUTTONS = {
    explore: [
        {label: 'look', cmd: 'look'},
        {label: 'inv', cmd: 'inventory'},
        {label: 'score', cmd: 'score'},
        {label: 'who', cmd: 'who'},
        {label: 'jobs', cmd: 'missions'},
        {label: 'help', cmd: 'help'},
    ],
    combat: [
        {label: 'dodge', cmd: 'dodge'},
        {label: 'aim', cmd: 'aim'},
        {label: 'attack', cmd: 'attack'},
        {label: 'flee', cmd: 'flee'},
        {label: 'pass', cmd: 'pass'},
        {label: 'cover', cmd: 'cover 1'},
    ],
    docked: [
        {label: 'launch', cmd: 'launch'},
        {label: 'status', cmd: 'status'},
        {label: 'crew', cmd: 'crew'},
        {label: 'repair', cmd: 'repair status'},
        {label: 'cargo', cmd: 'cargo'},
        {label: 'look', cmd: 'look'},
    ],
};
```

---

## What This Does NOT Change

- **Server text formatting** — `Fmt(width=session.width)` continues to format text for the negotiated terminal width. The `max-width: 80ch` CSS constraint handles visual wrapping; it doesn't change what the server sends.
- **Telnet experience** — No Telnet changes. The Dual-Interface Principle is preserved.
- **Game mechanics** — No combat, space, crafting, or economy changes.
- **Message protocol** — No new message types. Uses existing `hud_update`, `combat_state`, `space_state`.

---

## Success Criteria

1. Text wraps at ~80 characters on all viewport widths > 1024px
2. Exit buttons show readable labels (e.g., "down (Pit Floor)")
3. Comms/chat messages have a dedicated pane that doesn't scroll away during combat
4. Space panel activates when player launches from dock
5. Quick buttons change based on ground/combat/space context
6. The client feels like a **game** on first impression, not a terminal

---

## Future Considerations (Not in This Doc)

- **Login overlay** — Replace raw text username/password with a proper modal
- **Right gutter usage** — The space between 80ch text and sidebar could host a mini-map, zone map, or atmospheric art
- **Mobile layout testing** — CSS media queries exist but are untested
- **Sound effects** — Ambient zone audio, combat hit sounds
- **Notification badges** — Unread message counts on comms tabs

---

*End of design document.*
