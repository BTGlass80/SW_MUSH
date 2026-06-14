# T3.17 (Sheet redesign) + T3.18 (Ground-UX overhaul) — Gap-check findings

*Main-march session, 2026-06-14 PM. Worktree C:/SW_MUSH_live. Method: 18-feature
verification workflow (server producer + live-client consumer per feature), each
non-DONE verdict adversarially rechecked (refute-the-gap). **0 of the claimed gaps
were refuted** — all confirmed at HEAD (790083d) with file:line evidence.*

## Headline

Brian believed T3.17/T3.18 were largely done. **Half-true and the half matters:**
the **server side is built across the board**; the **live client regressed in the
legacy→SPA rewrite.** A whole tier of ground-UX panels exists *fully* in the
**retired `static/client_legacy.html`** but was **never ported** into the served
client **`static/client.html`** (the server redirects players to `/client.html`,
which loads the `static/spa/m3_*.js` modules). So most gaps are **mechanical
client-side ports with a working reference**, not net-new builds. Several m3_*.js
modules (M3Sheet, m3_combat_theater, buildMiniJobs) carry richer renderers but are
**scaffold-only — loaded, not wired to live WS data**.

## Verified status (18 features)

| # | Feature | Server | Client | Overall | Effort |
|---|---------|--------|--------|---------|--------|
| S1 | `+sheet` → `sheet_data` WS event end-to-end | done | done | **DONE** | — |
| S2 | Sheet modal + tabs (FULL/SKILLS/COMBAT/FORCE) | done | done | **DONE** | (opt polish) |
| S3 | skill_descriptions.yaml tooltips + detail drawer | done | done | **DONE** | — |
| S4 | Sheet shows ALL content (bio/specs/inventory/notes) | done | partial | **PARTIAL** | med |
| S5 | latent `+sheet/skills` GUI-silent bug | done | done | **DONE** (obsoleted) | — |
| G1 | Room Detail Card (desc + service icons, persistent) | done | partial | **PARTIAL** | med |
| G2 | Area Map server (area_map.py BFS, map_x/y, POIs) | done | done | **DONE** | — |
| G3 | Area Map client (SVG/click-nav done; polish gaps) | done | partial | **PARTIAL** | small |
| G4 | Enhanced Combat Panel (events feed, init ladder) | partial | partial | **PARTIAL** | med |
| G5 | HERE overhaul (npc role icons + interaction menus) | partial | missing | **PARTIAL** | med |
| G6 | Loadout (weapon/armor/consumables) | done | done | **DONE** | — |
| G7 | Active Jobs tracker | done | partial | **PARTIAL** | small |
| G8 | Smart Quick Buttons (post-combat/wound/context) | n/a | missing | **MISSING** | med |
| G9 | Nearby Services panel + click-to-walk | done | missing | **PARTIAL** | small |
| G10 | Credit activity ticker | done | partial | **DONE** (core; ring-buffer downscoped) | small |
| G11 | CP progress indicator | done | done | **DONE** | — |
| G12 | Zone Influence gauge (+ CW-era color fix) | done | missing | **PARTIAL** | small |
| G13 | Director zone-scoped story feed (Zone Intel) | partial | missing | **MISSING** | med |

DONE: S1,S2,S3,S5,G2,G6,G10,G11 (8). Work remaining: S4,G1,G3,G4,G5,G7,G8,G9,G12,G13 (10).

## What's actually left, by where the work lives

**Client-only ports (server already emits the data — pure `static/client.html`, zero
engine-collision; reference impl in `client_legacy.html`):**
- **G1** Room Detail Card — persistent context-panel card: room_description (currently only in the scroll log) + room_services icon row + security badge. Ref: client_legacy.html ~4488-4545.
- **G9** Nearby Services — context panel list + click-to-walk via `sendCmd(direction)`. Server BFS depth=4 wired at session.py:2091. Ref: client_legacy.html ~4543-4608.
- **G12** Zone Influence — context-panel horizontal faction gauge. **Use CW-era org codes** (republic/cis/hutt_cartel/bhg/jedi_order/independent) — server emits these; the legacy renderer's color map is keyed on dead GCW codes (empire/rebel/hutt/bh_guild) → must define CW colors.
- **G7** Active Jobs — sidebar section from `hud.active_jobs[]` (server aggregates tutorial/mission/bounty/smuggle). Live client currently shows only the single-line `hud.objective`. Ref: client_legacy.html ~4793-4830.
- **G5 (client half)** HERE overhaul — `g-room-contents` panel + `_ROLE_ICONS` + per-NPC interaction menus + hostile tint from `hud.room_contents`. Ref: client_legacy.html (updateRoomContents).
- **G8** Smart Quick Buttons — full QUICK_MODES/getQuickMode/updateQuickButtons + post-combat 30s mode + wound-aware heal injection + trainer/crafting context. Ref: client_legacy.html ~5538-5729.
- **G3** Area Map polish — two-hop node-body dimming (legacy path) + a per-move SVG cross-fade. POI icons already work in the M3 geometry path.
- **S4 (client half)** Sheet content — render bio fields (gender/homeworld/age/height/hair/eyes), specializations array, inventory, notes, pvp_flagged into the live sheet panel (all already in the sheet payload, just unconsumed).

**Needs server work too (touch carefully — Director/engine is the other live session's lane):**
- **G5 (server half)** add `wound_level` to npc entries + a quest-giver branch in `_classify_npc_role()` (server/session.py ~1268).
- **G4** add an `events` array (last N damage events) to `combat_state` `to_hud_dict()` (engine/combat.py) + render initiative ladder/cover/aim + a "Use Item" action.
- **G13** Director must attach a `zone` field to `news_event` + generate zone-scoped blurbs (engine/director.py — **THIS IS THE HOT SESSION'S LANE; DEFER/coordinate**) + client Zone Intel panel.
- **S4** advantages/disadvantages are always `[]` server-side (no schema) — a separate, larger change; defer.

## Drop plan (this session)
1. **gnd-ux-context-panel** — G1 + G9 + G12 (+G3 polish). All context-panel, client-only.
2. **gnd-ux-sidebar** — G7 + G5 client half. Sidebar, client-only.
3. **gnd-ux-quick-buttons** — G8. Client-only.
4. **sheet-content-surface** — S4 client half (bio/specs/inventory/notes).
5. **(later, when engine lane quiet)** G5 server half + G4 combat events. **G13 deferred** (director.py = other session).

Each drop: port into `static/client.html` matching the existing live handler style
(handleHudUpdate / handleCombatState), add a `tests/spa/test_*.py` wireup assertion
(pattern: test_client_wireup_42c.py / test_client_onclick_exports.py), AST/JS-syntax
validate, then full-suite gate + merge to main (full autonomy).

*All file:line evidence captured in the gap-check workflow run wf_40bc8b53-fd4.*

## STATUS (end of main-march session, 2026-06-14)
**SHIPPED** on `drop/gnd-ux-client-parity` (3 commits, client-only, `static/client.html` + 3 new `tests/spa` files, 75 new tests):
- G1 Room Detail Card, G9 Nearby Services, G12 Zone Influence (CW-era fix) — context-panel cards.
- G5 (client half) HERE room-contents panel, G7 Active Jobs — sidebar panels.
- S4 (client half) sheet specializations / PvP badge / notes / description / guarded bio.

**DEFERRED** (with rationale):
- **G8** smart quick-buttons — client-only but *replaces* the live `#qa-row` component (higher regression risk; the static buttons work). Port `client_legacy.html` QUICK_MODES (~5540-5701). Good next client drop.
- **G3** area-map polish (two-hop node dimming + per-move transition) — cosmetic, low value; POI already works in the M3 geometry path.
- **G4** combat events array + initiative-ladder wiring — needs `engine/combat.py` (server) + wiring `m3_combat_theater.js`.
- **G5 server-half** — add `wound_level` to npc entries + quest-giver branch in `_classify_npc_role()` (`server/session.py` ~1268). Small.
- **G13** director zone-scoped news feed — needs `engine/director.py`, **the parallel engine session's lane; coordinate before touching.**
- **G10** ring-buffer/reason for credit ticker — deliberate downscope (pinned ABI is `{type,credits,delta}`); skip unless requested.
