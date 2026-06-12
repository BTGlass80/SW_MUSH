# SW_MUSH Web Client UX — Competitive Analysis & Recommendations

*Opus session, April 10, 2026*
*Sources: Torn City (80K+ DAU, 21-year browser MMO), Iron Realms Nexus Client (Achaea/Imperian/Aetolia MUD web client), general browser RPG/MUD landscape*

---

## Executive Summary

SW_MUSH already leads the competition on interactivity — real-time D6 combat with initiative/declarations/cover/dodge, AI-driven NPCs, multi-planet space flight, and crafting are features that Torn and most browser RPGs lack entirely. The gap is in **UX polish and social infrastructure**. This document distills the strongest, most actionable lessons from competitors into recommendations ranked by impact-to-effort ratio.

---

## 1. Context-Sensitive Quick Buttons

**What competitors do:** Iron Realms Nexus replaces its F-key bar contextually — combat abilities light up when usable, exploration buttons appear when exploring. Torn progressively reveals entire navigation sections as players unlock features (flying at level 15, companies later, etc.).

**What we have:** Static quick buttons — `look`, `inv`, `score`, `sheet`, `jobs`, `who`, `news`, `help` — visible at all times regardless of context.

**Recommendation:** Replace the static button bar with a mode-driven system:

| Mode | Trigger | Buttons Shown |
|------|---------|---------------|
| **Explore** | Default ground state | `look`, `inv`, `score`, `who`, `jobs`, `news` |
| **Combat** | `combat_state.active == true` | `dodge`, `aim`, `attack`, `flee`, `pass`, `cover` |
| **Space** | `space_state` received | `scan`, `shields`, `speed`, `hyperspace`, `land`, `status` |
| **Trade** | Near a vendor NPC or in a market room | `buy`, `sell`, `list`, `appraise`, `haggle` |
| **Docked** | Aboard a landed ship | `launch`, `status`, `crew`, `repair`, `cargo` |

The mode is determined client-side from the JSON messages already being sent (`hud_update`, `combat_state`, `space_state`). No server changes required beyond ensuring the relevant JSON includes a `context` or `mode` hint.

**Effort:** Medium — client-side JS only, no server work.
**Impact:** High — eliminates the "what commands exist?" problem for new players.

---

## 2. Clickable Room Contents in Sidebar

**What competitors do:** Nexus 3.0 shows a "Room" panel listing all NPCs, players, and items present. Clicking an NPC opens a context menu (`look`, `talk`, `attack`). Clicking an item offers `get`, `examine`. This is built on GMCP — structured JSON pushed alongside text output.

**What we have:** `hud_update` already sends `exits` as clickable buttons. Room descriptions mention NPCs and items in text, but they're not interactive in the sidebar.

**Recommendation:** Extend `hud_update` to include:

```python
{
    "type": "hud_update",
    "exits": ["north", "south"],
    "room_contents": {
        "npcs": [
            {"name": "Wuher", "id": 12, "actions": ["look Wuher", "talk Wuher"]},
            {"name": "Stormtrooper", "id": 45, "actions": ["look Stormtrooper", "attack Stormtrooper"]}
        ],
        "items": [
            {"name": "dusty crate", "id": 88, "actions": ["look crate", "get crate", "open crate"]}
        ],
        "players": [
            {"name": "Tundra", "id": 1, "actions": ["look Tundra"]}
        ]
    }
}
```

Client renders these as a collapsible `.sb-section.room-contents` panel. Each entry is a clickable element that expands to show action buttons. Clicking an action button sends the corresponding command string.

**Server change:** `_build_hud_update()` in `game_server.py` queries room occupants and ground items. The data already exists in `db.get_npcs_in_room()` and room item lists — it just needs to be included in the JSON payload.

**Effort:** Medium — server adds ~20 lines to hud builder, client adds a new sidebar section.
**Impact:** High — bridges the gap between "type commands" and "click to interact." Directly addresses the biggest accessibility barrier for players unfamiliar with MUD/MUSH conventions.

---

## 3. Persistent Character Gauge

**What competitors do:** Nexus displays health, mana, and endurance as colored horizontal bars above the input box, always visible. Torn shows energy bars, nerve bars, and cooldown timers on every page. Both treat character status as ambient, always-on information.

**What we have:** Wound status is conveyed in combat text via ANSI color escalation, and `hud_update` carries wound data. But there's no persistent visual gauge outside of active combat.

**Recommendation:** Add a compact character status strip to the sidebar (or above the input box) showing:

- **Wound level** — colored bar segment matching the existing wound-color CSS (`green → yellow → orange → red → dark red`)
- **Stun status** — if stunned, a separate indicator
- **Force Points** — if the character has Force skills, show current/max
- **Credits** — current wallet balance

Data source: `hud_update` already carries `wound_level`. Add `stun`, `force_points`, and `credits` fields to the same payload. All are single DB reads that `_build_hud_update()` can include trivially.

**Effort:** Low — minor server-side addition to existing JSON, ~30 lines of client CSS/JS.
**Impact:** High — players always know their state without typing `score`. Reduces unnecessary command traffic.

---

## 4. Mobile-Responsive Sidebar

**What competitors do:** Nexus 3.0 uses swipe-left/swipe-right to access sidebar panels on mobile. Torn's mobile site collapses its navigation into a hamburger menu. Torn PDA (40K+ users) exists specifically because Torn's core site wasn't mobile-friendly enough — a cautionary tale.

**What we have:** A desktop-optimized two-column layout (sidebar + terminal). On narrow viewports, the sidebar either overflows or crushes the terminal width.

**Recommendation:** Implement a responsive breakpoint system:

- **Desktop (>1024px):** Current two-column layout, sidebar always visible.
- **Tablet (768–1024px):** Sidebar collapses to icons-only rail (expandable on hover/tap).
- **Mobile (<768px):** Sidebar hidden by default. Hamburger icon in top-left toggles a slide-over panel. Terminal takes full width. Quick buttons move to a fixed bottom bar (thumb-reachable).

Key mobile constraints:
- Touch targets minimum 44×44px (Apple HIG / Material Design standard)
- Exit buttons arranged as a compass rose or horizontal strip, not a vertical list
- Input box fixed to bottom of viewport, never scrolled out of view
- Combat text at `font-size: 14px` minimum for readability

**Effort:** Medium — CSS media queries + a small amount of JS for the toggle/swipe behavior. No server changes.
**Impact:** High — unlocks mobile players entirely. Torn's experience shows that mobile players are often the most engaged (short, frequent sessions throughout the day).

---

## 5. Comms Separation Panel

**What competitors do:** Nexus pipes all chat/communication to a dedicated window, separate from the main game output. Mudlet users routinely set up tabbed chat windows that capture channel communication with blinking tabs on new messages. Torn has a dedicated messaging/chat system separate from game actions.

**What we have:** The Comlink Feed panel parses `[SYSTEM]`, `[COMBAT]`, `[THE FORCE]`, and GNN keywords from the text stream. But `say`, `ooc`, `page`, and player-to-player communication still appears inline in the main terminal and scrolls away during combat.

**Recommendation:** Expand the Comlink Feed into a tabbed communication panel:

| Tab | Captures |
|-----|----------|
| **All** | Everything (current behavior) |
| **IC Chat** | `say`, `emote`, `whisper` output |
| **OOC** | `ooc`, `page` messages |
| **System** | `[SYSTEM]`, `[COMBAT]`, GNN, Director AI alerts |

Implementation: Server-side, tag outgoing messages with a `channel` field in WebSocket JSON:

```python
{"type": "chat", "channel": "ic", "from": "Wuher", "text": "We don't serve their kind here."}
{"type": "chat", "channel": "ooc", "from": "Brian", "text": "brb 5 min"}
```

Client-side, route messages to the appropriate tab. Unread indicator (dot or count badge) on inactive tabs. Clicking a tab filters the comms panel. The main terminal still shows everything inline for Telnet parity.

**Effort:** Medium — server needs to wrap chat output in structured messages (parallel to existing text output, not replacing it). Client needs tab UI in the existing Comlink panel.
**Impact:** High — in active multiplayer sessions, social messages getting buried in combat/movement output is the #1 cause of missed communication. This is table-stakes for any MUD web client.

---

## 6. Onboarding Walkthrough

**What competitors do:** Torn uses "George's Tutorial Missions" — an NPC that walks new players through core mechanics with guided tasks and rewards. Nexus games (Achaea etc.) have interactive character creation and a tutorial area with gated progression. Both use progressive disclosure — you don't see systems until you're ready for them.

**What we have:** 133+ commands, a `help` system, and new players dropped into Mos Eisley with no guidance.

**Recommendation:** Create a first-login tutorial NPC encounter:

- On first connection, spawn the player in a designated arrival room (Docking Bay 94 entry corridor or a new "Mos Eisley Spaceport Arrivals" room)
- An NPC (protocol droid, port authority officer, or a smuggler contact) initiates dialogue via the Director AI or scripted sequence
- Tutorial sequence teaches 6 core actions in order:
  1. `look` — "Take a look around."
  2. Movement — "Head north to the cantina."
  3. `talk` — "Talk to Wuher at the bar."
  4. `score` / `sheet` — "Check your stats."
  5. `get` / `inv` — Pick up a starter item.
  6. `equip` — Equip the starter item.
- Each step triggers only after the previous one is completed (server-side flag on the character record: `tutorial_step`)
- Tutorial is skippable (`skip tutorial` command) for experienced MUSH players
- On completion, award a small credit bonus and direct the player to `help topics`

**Effort:** Medium-Large — needs a tutorial state machine in the command parser or a dedicated tutorial handler, plus the NPC dialogue content. Can be implemented as a special-case check in `handle_command()` that intercepts during tutorial mode.
**Impact:** High — this is the single biggest retention lever. Every competitor that survives long-term has solved onboarding. Players who don't understand `look` in the first 60 seconds leave and never return.

---

## 7. Player-Driven Economy Infrastructure

**What competitors do:** Torn's founder: "We give the players the tools to build their own game." They employ a degree-certified economist to monitor every credit flowing between every player. Their player marketplace, bazaar system, and company ownership are the primary retention drivers — more than combat, more than quests. Billions of in-game dollars change hands daily across player-run shops and trades.

**What we have:** NPC vendors, a crafting system with schematics, and Economy Phase 2 stubs for missions/bounties. No player-to-player trade command, no player-run shops, no marketplace.

**Recommendation:** Implement a `trade` command and a bulletin-board market:

**Phase 1 — Direct Trade:**
```
trade <player> <item> for <credits>
```
Both parties must confirm. Transaction logged. This is the minimum viable economy — it lets players exchange crafted goods, loot, and equipment.

**Phase 2 — Market Board:**
A terminal in each starport (Mos Eisley Cantina, Nar Shaddaa landing pad, etc.) where players can post buy/sell orders:
```
market list                    — show all active listings
market sell <item> <price>     — post a sell order
market buy <listing_id>        — purchase a listed item
market cancel <listing_id>     — cancel your listing
```

Items are held in escrow (removed from seller's inventory on listing, returned on cancel). Credits transfer on purchase. A small listing fee acts as a credit sink.

**Why this matters for retention:** Torn's 21-year longevity is built on the fact that the economy gives players goals beyond combat. A player who crafts a custom blaster and sells it to another player has created a social bond and a reason to log in tomorrow. Our crafting system is the production pipeline — the market is the demand pipeline.

**Effort:** Large — needs new DB tables (listings, transaction log), new commands, escrow logic.
**Impact:** Very High — but this is a long-term play. Prioritize Phase 1 (`trade` command) as a near-term drop; Phase 2 market board can follow.

---

## 8. Structured JSON for All Systems

**What competitors do:** Iron Realms' GMCP protocol sends structured data for virtually everything: inventory changes, room transitions, skill usage, channel messages, character stats, quest progress, and more. This enables both their own Nexus client and third-party clients (Mudlet, MUSHclient) to build rich UIs. Torn's public API spawned an entire ecosystem of community tools (TornTools, TornPDA, TornStats, YATA).

**What we have:** `hud_update` (after every command), `combat_state` (during combat), `space_state` (in space), `news_event` (Director AI). These are well-designed but cover only a fraction of game systems.

**Recommendation:** Adopt a principle: **every new system emits structured JSON alongside its text output.** Formalize the message protocol:

| Message Type | Trigger | Payload |
|---|---|---|
| `hud_update` | After every command | Stats, exits, room contents, wound, location |
| `combat_state` | Combat state changes | Combatants, round, phase, actions |
| `space_state` | Space commands / tick | Ship status, zone, speed, hull, shields |
| `news_event` | Director AI / world events | Event type, headline, details |
| `chat` | Any social command | Channel, sender, text |
| `skill_check` | Any skill roll | Skill, difficulty, dice, result, margin |
| `trade` | Trade/market transactions | Buyer, seller, item, price, status |
| `craft` | Crafting progress/completion | Schematic, stage, result |
| `inventory_change` | Get/drop/equip/unequip | Action, item, container |

The text stream remains canonical (Dual-Interface Principle). These JSON messages are supplemental, sent only to WebSocket sessions. But having them means:
- The web client can update sidebar panels in real-time without parsing ANSI text
- Future community tools (Discord bots, companion apps) have a clean data source
- Accessibility tools (screen readers) can consume structured data instead of parsing formatted text

**Effort:** Low per-system (each new JSON emission is ~5-10 lines in the relevant command handler), but cumulative.
**Impact:** High — this is infrastructure that compounds. Every future feature benefits from it.

---

## Anti-Patterns to Avoid

These are lessons from competitors' mistakes — things we should explicitly **not** do:

### Timer-Locked Gameplay (Torn)
Torn players are locked out of the game for hours while traveling, in jail, or in hospital. This is the #1 complaint in every review. Our real-time MUSH doesn't have this problem by design. **Do not add cooldown timers that prevent players from taking actions.** If a system needs pacing (e.g., hyperspace travel), make the travel time interesting (random encounters, ship management) rather than a lockout.

### Overwhelming Command Dumps (Traditional MUDs)
Classic MUDs dump `help` output as a wall of 200+ commands. Our `help` system should be contextual: `help` with no arguments shows only commands relevant to the player's current situation and unlocked systems. `help all` for the completionists.

### Pay-to-Win Economy (Various Browser RPGs)
Torn's fairness is a major part of its retention. Players praise that no amount of real money gives a combat advantage. If SW_MUSH ever adds premium features, they should be cosmetic or convenience (custom descriptions, extra character slots) — never stat boosts or exclusive equipment.

---

## Implementation Priority

| Priority | Recommendation | Effort | Impact | Dependencies |
|----------|---------------|--------|--------|-------------|
| **1** | Context-Sensitive Quick Buttons | Medium | High | None — client-side only |
| **2** | Clickable Room Contents | Medium | High | Minor `hud_update` extension |
| **3** | Persistent Character Gauge | Low | High | Minor `hud_update` extension |
| **4** | Mobile-Responsive Sidebar | Medium | High | None — CSS/JS only |
| **5** | Comms Separation Panel | Medium | High | Chat message tagging |
| **6** | Onboarding Walkthrough | Medium-Large | Very High | Tutorial state machine |
| **7** | Trade Command (Phase 1) | Medium | High | New DB tables |
| **8** | Structured JSON Protocol | Low (ongoing) | High (cumulative) | Per-system additions |

Items 1–4 are pure UX improvements that require no new game systems. They can be delivered as client-side drops without touching game logic. Items 5–8 require server-side work but build the foundation for long-term retention and community growth.

---

*End of design document.*
