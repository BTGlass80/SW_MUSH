# Web Portal Foundation — Design Document v1
## SW_MUSH Priority D Phase 2

**Date:** April 15, 2026
**Author:** Claude (Opus)
**Estimated Effort:** 20-30 hours across 6 drops
**Priority:** D Phase 2 — Primary retention channel

---

## 1. Problem Statement

SW_MUSH's web client (`client.html`) is excellent for playing the game. But a MU* community needs a web presence that works when players **aren't logged in**. Right now, visiting the URL shows a login screen. Prospective players can't browse characters, read scene logs, see who's online, or learn about the world without connecting.

AresMUSH proved that a web portal dramatically increases retention — players spend time on the portal between sessions reading logs, browsing characters, and staying engaged. This creates the "ambient community" that sustains a MU* long-term.

**Current state:** Browser → login screen → play. No browse, no discovery, no engagement outside sessions.

**Target state:** Browser → rich landing page → browse characters, scenes, guides, who's online → "Play Now" launches the client. The portal is the game's public face.

---

## 2. Architecture Overview

### 2.1 Key Design Decisions

**No separate server.** The portal runs on the existing aiohttp instance (port 8080). No new processes, no new ports, no deployment complexity.

**JSON API + vanilla JS SPA.** Following the chargen pattern (`server/api.py` + `static/chargen.html`), the portal uses a REST API under `/api/portal/*` and a single-page vanilla JS frontend at `static/portal.html`. No framework dependencies — same design language as `client.html` and `chargen.html` (Share Tech Mono, Orbitron, Rajdhani, dark sci-fi palette).

**Public by default.** Character names, species, faction, description, and shared scene logs are viewable without login. Skills, attributes, private backgrounds, financial data, and inventory require authentication. This matches the Dual-Interface Principle — everything the portal shows is also available via in-game commands.

**Authentication via existing accounts.** Portal login uses the same `accounts` table. Session tokens via the existing HMAC-SHA256 mechanism in `server/api.py`. Cookie-stored for portal persistence.

**`/` becomes the portal, not the client.** The root URL serves the portal landing page. The play client moves to `/play` (with `/client.html` as a legacy alias). This is the single most important UX change — visitors land on a welcoming page instead of a login prompt.

### 2.2 Route Structure

All portal API routes mounted under `/api/portal/` on the existing aiohttp app. Portal HTML served from `static/portal.html`.

| Method | Route | Auth | Purpose |
|--------|-------|------|---------|
| GET | `/` | None | Portal landing page (serves `portal.html`) |
| GET | `/play` | None | Game client (serves `client.html`) |
| GET | `/chargen` | None | Character creation (existing) |
| GET | `/api/portal/who` | None | Online player list (name, species, location area, idle) |
| GET | `/api/portal/characters` | None | Character directory (paginated, public fields) |
| GET | `/api/portal/character/{id}` | None/Token | Character profile (public fields; auth adds private) |
| GET | `/api/portal/scenes` | None | Shared scene list (paginated, filterable) |
| GET | `/api/portal/scene/{id}` | None | Scene detail + pose log (shared scenes only) |
| GET | `/api/portal/guides` | None | Guide index (list of available guides) |
| GET | `/api/portal/guide/{slug}` | None | Guide content (rendered markdown) |
| GET | `/api/portal/news` | None | Recent Director events (last 20) |
| GET | `/api/portal/stats` | None | Game stats (player count, room count, uptime) |
| POST | `/api/portal/login` | None | Authenticate → session token |
| GET | `/api/portal/me` | Token | Authenticated user's own data |

### 2.3 New Files

| File | Est. Lines | Purpose |
|------|-----------|---------|
| `server/web_portal.py` | ~500 | REST API route handlers for all portal endpoints |
| `static/portal.html` | ~2,000 | Single-page portal frontend (vanilla JS, same design language as client/chargen) |
| `data/guides/` | ~varies | Guide markdown files (copied from project knowledge, served as content) |

### 2.4 Modified Files

| File | Change |
|------|--------|
| `server/web_client.py` | `/` → serves `portal.html`; `/play` and `/client.html` → serve `client.html`; register portal API routes |
| `server/config.py` | Update welcome banner links |
| `engine/scenes.py` | Add `get_shared_scenes()` and `get_public_scene_detail()` query functions |
| `db/database.py` | Add `get_all_active_characters_public()` for character directory |

---

## 3. Portal Pages

### 3.1 Landing Page (`/`)

The game's front door. Must answer three questions in under 5 seconds: **What is this?** **Is anyone playing?** **How do I start?**

**Content:**
- Game title, era tagline ("Galactic Civil War era, WEG D6 Revised & Expanded")
- "Play Now" button → `/play`
- "Create a Character" button → `/chargen`
- Live online player count (fetched via `/api/portal/who`, auto-refreshes every 30s)
- Recent GNN news feed (last 5 Director events from `/api/portal/news`)
- Quick-links navigation: Characters | Scenes | Guides | Who's Online
- Brief game description paragraph (what makes SW_MUSH different — AI Director, player-driven economy, 120+ rooms across 4 planets)

**Design:** Full-viewport hero section with Star Wars-themed dark background. Same font stack as client.html. No login required.

### 3.2 Who's Online (`/who`)

Live player list. The portal equivalent of the `who` command.

**API response (`/api/portal/who`):**
```json
{
  "online": [
    {
      "name": "Kael Voss",
      "species": "Human",
      "location_area": "Mos Eisley",
      "idle_seconds": 120,
      "faction": "Neutral"
    }
  ],
  "count": 5,
  "uptime_seconds": 86400
}
```

**Privacy:** Shows character name, species, general area (planet/zone name, not specific room), faction, and idle time. Does NOT show room name, credits, inventory, or attributes. Matches what the in-game `who` command shows to non-admin players.

**Data source:** `session_mgr.all` → filter `is_in_game` → extract public fields from `session.character`. Zone name from `session.character["room_id"]` → room → zone lookup.

### 3.3 Character Directory (`/characters`)

Browseable list of all active characters. The game's cast page.

**API response (`/api/portal/characters`):**
```json
{
  "characters": [
    {
      "id": 1,
      "name": "Kael Voss",
      "species": "Human",
      "template": "Smuggler",
      "faction": "Neutral",
      "description_snippet": "A lean Human pilot with quick eyes...",
      "online": true
    }
  ],
  "total": 42,
  "page": 1,
  "per_page": 20
}
```

**Pagination:** 20 per page, `?page=N`. Filterable by `?species=`, `?faction=`, `?online=true`.

**Data source:** `SELECT id, name, species, template, faction, description FROM characters WHERE is_active = 1`. Description truncated to first 100 chars for snippet.

### 3.4 Character Profile (`/character/{id}`)

Full character page — the portal equivalent of `+finger` and `sheet`.

**Public fields (no auth required):**
- Name, species, template, faction, description
- Background (from `pc_narrative.background` — the player-written bio)
- Scars (from character attributes)
- Achievement count and recent achievements
- Scene participation count
- Faction membership and rank (if any)
- Online status

**Private fields (auth required, own character only):**
- Full attribute/skill sheet
- Credits balance
- Inventory
- Reputation standings
- CP balance

**Data source:** `get_character()` + `pc_narrative` query + `org_memberships` join + `character_achievements` count.

### 3.5 Scene Archive (`/scenes`)

Browseable archive of shared scenes. AresMUSH's killer feature.

**API response (`/api/portal/scenes`):**
```json
{
  "scenes": [
    {
      "id": 7,
      "title": "Cantina Confrontation",
      "scene_type": "Action",
      "location": "Chalmun's Cantina",
      "started_at": "2026-04-15T14:30:00Z",
      "completed_at": "2026-04-15T16:00:00Z",
      "summary": "A tense standoff between smugglers...",
      "participants": ["Kael Voss", "Zara Kint"],
      "pose_count": 45
    }
  ],
  "total": 12,
  "page": 1
}
```

**Scene detail (`/api/portal/scene/{id}`):**
```json
{
  "id": 7,
  "title": "Cantina Confrontation",
  "scene_type": "Action",
  "summary": "...",
  "participants": ["Kael Voss", "Zara Kint"],
  "poses": [
    {
      "character": "Kael Voss",
      "type": "emote",
      "content": "leans against the bar, watching the door.",
      "timestamp": "2026-04-15T14:31:00Z"
    }
  ]
}
```

**Access control:** Only scenes with `status = 'shared'` are visible. Unshared/private scenes are invisible to the portal.

**Data source:** `engine/scenes.py` — add `get_shared_scenes(page, per_page, filters)` and `get_public_scene_detail(scene_id)`.

### 3.6 Game Guide (`/guide/{slug}`)

Renders the 11 Guide markdown files as formatted HTML pages. Gives prospective players a way to learn the mechanics before connecting.

**Guide index (`/api/portal/guides`):**
```json
{
  "guides": [
    {"slug": "core-mechanics", "title": "WEG D6 Core Mechanics", "order": 1},
    {"slug": "character-creation", "title": "Character Creation", "order": 2},
    {"slug": "ground-combat", "title": "Ground Combat", "order": 3}
  ]
}
```

**Guide content (`/api/portal/guide/{slug}`):**
Returns the markdown content as a JSON string. The frontend renders it using a lightweight markdown-to-HTML converter (can use a small JS library or a simple regex-based converter — these are structured documents, not arbitrary markdown).

**Data source:** `data/guides/` directory — markdown files named by slug. Loaded once at startup, cached in memory.

### 3.7 News Feed (`/api/portal/news`)

Recent Director events — the GNN ticker on the web.

**Data source:** `director_log` table, last 20 entries ordered by timestamp desc. Fields: `text`, `timestamp`, `event_type`.

---

## 4. Frontend Architecture

### 4.1 Single-Page Application

`static/portal.html` — one file, same pattern as `chargen.html`. Client-side routing via hash fragments (`#/`, `#/who`, `#/characters`, `#/character/5`, `#/scenes`, `#/scene/7`, `#/guide/core-mechanics`).

**Navigation bar:** Home | Who's Online | Characters | Scenes | Guides | Play Now

**Design language:** Identical to `client.html` and `chargen.html`:
- Fonts: Share Tech Mono (body), Orbitron (headings), Rajdhani (UI elements)
- Palette: `#0a0e17` background, `#1a1f2e` panels, `#00d4ff` primary accent, `#e8e6e3` text
- Subtle sci-fi border glows, panel shadows
- Responsive: works on mobile

### 4.2 Key Frontend Components

**`renderLanding()`** — Hero section, online count, news feed, CTA buttons
**`renderWho()`** — Player list table with species/faction/idle columns
**`renderCharacters()`** — Card grid with pagination, search, filters
**`renderCharacterProfile(data)`** — Full profile page with tabs (Overview / Sheet / Scenes)
**`renderScenes()`** — Scene list with type badges, participant names, date
**`renderSceneDetail(data)`** — Full pose log with character-attributed poses
**`renderGuide(content)`** — Rendered markdown content with table of contents

### 4.3 Auto-Refresh

- `/who` page: polls `/api/portal/who` every 30 seconds
- Landing page online count: polls every 30 seconds
- News feed: polls `/api/portal/news` every 60 seconds
- All other pages: static on load (user refreshes manually)

---

## 5. Implementation Plan — 6 Drops

### Drop 1: Portal Shell + Landing + Who's Online (~4-6 hrs)

**Server:**
- `server/web_portal.py` — `PortalAPI` class with `register_routes()`, handlers for `/api/portal/who`, `/api/portal/news`, `/api/portal/stats`
- `server/web_client.py` — `/` serves `portal.html`, `/play` serves `client.html`

**Client:**
- `static/portal.html` — SPA shell with nav bar, hash routing, landing page, who's online page

**Result:** Visitors land on a welcoming page with online count and "Play Now" button. Who's Online page shows live player list.

### Drop 2: Character Directory + Profile (~4-6 hrs)

**Server:**
- `web_portal.py` — `/api/portal/characters` (paginated, filterable), `/api/portal/character/{id}` (public + optional auth)
- `db/database.py` — `get_all_active_characters_public()` query

**Client:**
- Character directory page with card grid, search, species/faction filters
- Character profile page with public bio, faction, scars, achievements

**Result:** Visitors can browse all characters. Players can view each other's profiles.

### Drop 3: Scene Archive (~4-6 hrs)

**Server:**
- `web_portal.py` — `/api/portal/scenes` (paginated, filterable by type/participant), `/api/portal/scene/{id}`
- `engine/scenes.py` — `get_shared_scenes()`, `get_public_scene_detail()` with character name joins

**Client:**
- Scene list page with type badges, participant names, date sorting
- Scene detail page with full pose log, character-attributed entries

**Result:** Shared scenes are browseable on the web. The game's RP history becomes a public asset.

### Drop 4: Game Guide (~2-3 hrs)

**Server:**
- `web_portal.py` — `/api/portal/guides`, `/api/portal/guide/{slug}`
- `data/guides/` — Copy 11 Guide markdown files into the game data directory

**Client:**
- Guide index page with numbered list
- Guide content page with markdown rendering, table of contents

**Result:** New players can read rules and mechanics before connecting. Reduces friction.

### Drop 5: Authentication + Private Data (~3-4 hrs)

**Server:**
- `web_portal.py` — `/api/portal/login` (POST username/password → token), `/api/portal/me` (GET own characters)
- Character profile: auth token adds private fields (sheet, credits, inventory, reputation)
- Cookie-based session storage using existing HMAC token mechanism

**Client:**
- Login button in nav bar → login modal
- Character profile shows expanded sheet when viewing own character
- "My Characters" shortcut in nav when authenticated

**Result:** Players can log into the portal to view their own private data.

### Drop 6: Polish + Mobile + Integration (~2-3 hrs)

- Mobile responsive tweaks (nav collapse, card stacking)
- Portal link in welcome banner and config.py
- `client.html` "Portal" button/link in sidebar
- Loading states, error handling, empty state messages
- Meta tags for social sharing (Open Graph: title, description, image)

**Result:** Portal is production-ready and cross-linked with the game client.

---

## 6. Data Privacy Model

| Data | Public | Auth (Own) | Auth (Other) |
|------|--------|-----------|--------------|
| Name, species, template | ✅ | ✅ | ✅ |
| Description, background | ✅ | ✅ | ✅ |
| Faction, rank | ✅ | ✅ | ✅ |
| Scars | ✅ | ✅ | ✅ |
| Achievement count/list | ✅ | ✅ | ✅ |
| Scene participation | ✅ | ✅ | ✅ |
| Online status | ✅ | ✅ | ✅ |
| Attributes/skills | ❌ | ✅ | ❌ |
| Credits | ❌ | ✅ | ❌ |
| Inventory | ❌ | ✅ | ❌ |
| Reputation standings | ❌ | ✅ | ❌ |
| CP balance | ❌ | ✅ | ❌ |
| Private scenes | ❌ | ✅ (own) | ❌ |

---

## 7. API Authentication

Reuses the existing HMAC-SHA256 token mechanism from `server/api.py`.

**Login flow:**
1. POST `/api/portal/login` with `{"username": "x", "password": "y"}`
2. Server verifies credentials against `accounts` table
3. Returns `{"token": "...", "account_id": N, "characters": [...]}`
4. Frontend stores token in `localStorage` (portal sessions, not game sessions)
5. Subsequent requests include `Authorization: Bearer <token>` header
6. Token TTL: 24 hours (longer than chargen tokens — portal is a browsing session)

**Middleware:** `web_portal.py` includes an `_optional_auth(request)` helper that returns `account_id` if a valid token is present, or `None` otherwise. Endpoints use this to conditionally include private data.

---

## 8. Performance Considerations

**Caching:** Guide content loaded once at startup, cached in memory. Character directory can be cached for 30 seconds (invalidated on login/logout). Scene list cached for 60 seconds.

**Query efficiency:** Character directory uses the slim `get_all_active_characters_public()` query (no inventory/attributes blobs). Scene list uses indexed queries on `status + started_at`.

**No WebSocket for portal.** The portal uses polling (30s for /who, 60s for news). WebSocket is reserved for the game client. This keeps the portal lightweight and avoids connection limits.

---

## 9. Integration with Existing Systems

**Director news:** Reads directly from `director_log` table. No changes to Director AI.

**Scenes:** Adds two read-only query functions to `engine/scenes.py`. No changes to scene lifecycle.

**Characters:** Reads from existing `characters` + `pc_narrative` + `org_memberships` tables. No schema changes.

**Chargen link:** Portal "Create a Character" button links to `/chargen` (existing standalone flow). On completion, the chargen redirect goes to `/play?token=XXX` instead of `/client.html?token=XXX`.

---

## 10. What This Does NOT Include (Future Drops)

- **Event calendar** — needs new `events` table and commands (Priority D Phase 4)
- **Plot/story arc tracker** — needs new `plots` table and commands (Priority D Phase 4)
- **Pose order tracker** — in-game command, not portal feature (Priority D Phase 4)
- **Forum/wiki** — large scope, Director AI fills the lore role
- **In-portal editing** (profile, background) — future enhancement after core portal ships
- **WebSocket real-time updates** on portal — polling is sufficient for v1

---

## 11. Success Metrics

The portal is successful if:
1. A new visitor can understand what the game is within 5 seconds of landing
2. The "Play Now" path from portal to in-game takes under 30 seconds
3. Existing players visit the portal between sessions to browse scenes/characters
4. The portal works on mobile without horizontal scrolling
5. Google can index the portal pages (proper meta tags, server-rendered content accessible to crawlers)

---

## 12. Testing Checklist

### Drop 1 (Shell + Landing + Who)
1. ☐ Browse to `localhost:8080` → portal landing page (NOT login screen)
2. ☐ Online count updates every 30 seconds
3. ☐ "Play Now" button → `/play` → game client loads
4. ☐ "Create Character" button → `/chargen` → chargen loads
5. ☐ Navigate to Who's Online → player list shown
6. ☐ `/play` serves client.html correctly
7. ☐ `/client.html` legacy URL still works

### Drop 2 (Characters)
8. ☐ Character directory shows all active characters
9. ☐ Filter by species works
10. ☐ Click character → profile page with bio, faction, description
11. ☐ Private fields (credits, skills) NOT visible without login

### Drop 3 (Scenes)
12. ☐ Scene archive shows only shared scenes
13. ☐ Click scene → full pose log
14. ☐ Unshared scene returns 404

### Drop 4 (Guides)
15. ☐ Guide index lists all 11 guides
16. ☐ Click guide → formatted content renders correctly
17. ☐ Tables and code blocks render properly

### Drop 5 (Auth)
18. ☐ Login with valid credentials → token stored
19. ☐ Own character profile shows full sheet
20. ☐ Other character profiles remain public-only
21. ☐ Invalid credentials → error message

### Regression
22. ☐ Telnet connection unchanged
23. ☐ WebSocket game client at `/play` unchanged
24. ☐ Chargen at `/chargen` unchanged (both standalone and embedded)

---

*Opus session — Web Portal Foundation design doc. 6 drops, ~20-30 hours estimated.*
