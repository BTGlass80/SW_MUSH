# HSpace & AresMUSH Feature Integration Analysis
## Design Document v1.0
### April 2026 · Opus Session

---

## 1. Executive Summary

After a thorough review of HSpace 4.4.1 (~50K lines C++), AresMUSH (~3.9M plugins directory, Ruby), and the Ares Web Portal (Ember.js SPA), the picture is clear: **SW_MUSH already surpasses both systems in mechanical depth**, but Ares pioneered two paradigm shifts that we should steal — the *out-of-client web portal* and *structured scene management* — and HSpace has a few engineering subsystems worth adapting to our WEG D6 engine. Neither system threatens our core strengths (D6 fidelity, Director AI, living economy, territory control), but both reveal UX patterns that would dramatically improve player retention and staff workflow.

**Bottom line — 7 features worth integrating, organized into 3 priority tiers:**

| Priority | Feature | Source | Impact | Effort |
|----------|---------|--------|--------|--------|
| A | Web Portal (out-of-client) | Ares | Transformative | Large |
| A | Scene Logging & Archive | Ares | High | Medium |
| B | Tractor Beam System | HSpace | Medium | Small |
| B | Boarding Links (ship-to-ship) | HSpace | Medium | Medium |
| B | Pose Order Tracker | Ares | Medium | Small |
| C | Event Calendar with Signup | Ares | Medium | Small |
| C | Plot/Story Arc Tracker | Ares | Medium | Small |

**What we should NOT port** (and why):

- HSpace's sensor model — ours is better (WEG-faithful skill checks, 4 info tiers, deep scan resolution)
- HSpace's damage control crews — we already have `damcon` with WEG skill checks
- HSpace's autopilot AI — our NPC space traffic system is far more sophisticated
- HSpace's territory system — our influence-based territory control is a generation ahead
- HSpace's power allocation — already delivered in our reactor power system
- FS3 combat — entirely incompatible with WEG D6; our combat system is mechanically richer
- FS3 skills — WEG D6 attribute+skill pips are our core identity
- Ares chargen web flow — our guided wizard is already excellent and WEG-specific
- Ares wiki — we have the Director AI generating narrative content; a static wiki is lower value
- Ares achievements system — our ship's log milestones + CP progression already fill this role
- Ares "places" (sub-locations within rooms) — nice but low priority; rooms are the atomic unit

---

## 2. Source Analysis

### 2.1 HSpace 4.4.1

HSpace is a C++ space simulation plugin for PennMUSH/TinyMUX, dating to ~2006. It's a well-engineered simulation with 3D coordinate-based movement, per-system power allocation, modular ship subsystems, and a class-based ship template hierarchy. Key subsystems:

**What it does well:**
- **Subsystem granularity**: Each ship system (engines, sensors, shields, weapons, reactors, life support, communications, computers, jump drives, cloaking, tractor beams, thrusters, damage control) is a separate C++ class with its own power draw, damage state, stress model, and repair cycles. Our system groups these more coarsely.
- **Tractor beam mechanics**: Three modes (tractor/repulse/hold), strength-based, power-dependent effectiveness. We have no tractor beam system.
- **Boarding links**: Ship-to-ship hatches that create walkable exits between docked vessels. Players can physically walk between ships. We have docking but no inter-ship walkways.
- **Missile tracking**: Missiles are independent 3D objects that track targets across cycles, can be shot down, and have their own movement physics. Our weapons are instant-hit.
- **Console-based gunnery**: Each console has its own heading independent of the ship, allowing turret-like behavior. Our gunnery is ship-heading-relative.

**What we already do better:**
- Skill-based everything (HSpace uses flat stat comparisons; we use WEG D6 dice pools)
- Director AI narrative integration (HSpace has zero narrative capability)
- Economy (HSpace has no economy at all)
- Web client with space HUD (HSpace is text-only)
- NPC crew with personalities and wages (HSpace NPCs are stat blocks)
- Anomaly scanning and salvage (HSpace has nothing comparable)
- Trade goods and smuggling (HSpace has no cargo mechanics)

### 2.2 AresMUSH & FS3

AresMUSH is a modern Ruby-based MU* platform with a plugin architecture. FS3 (FS3Skills + FS3Combat) is its default RPG system — a simple attribute+skill system with opposed rolls. The combat plugin supports web-based combat management.

**What it does well:**
- **Scene management**: First-class scene objects with lifecycle (create → pose → complete → share). Scenes can be started from the web portal, played asynchronously, and automatically logged.
- **Pose order tracking**: Built-in turn order tracker with "3-per" mode (everyone poses 3 times before the cycle resets) and standard round-robin. Notifies the next person whose turn it is.
- **Web-based combat setup**: Combat encounters can be configured entirely from the web — adding combatants, setting weapons/armor, assigning teams, managing NPC skill levels. The GM doesn't need to type commands.
- **Event calendar**: Full event scheduling with signup/cancel, scene auto-creation from events, and cron-based cleanup of past events.
- **Plot tracker**: Story arcs link related scenes together with storyteller attribution, content warnings, and tagging. Players can browse the arc and read all connected scenes in order.
- **Profile system**: Rich character profiles with demographics, relationships, gallery images, scene participation history, and FS3 sheet — all viewable from the web.

**What we already do better:**
- Mechanical depth (FS3 is intentionally simple; WEG D6 is mechanically rich)
- AI-driven narrative (Ares relies entirely on human GMs/storytellers)
- Automated content (missions, bounties, smuggling, anomalies — Ares has none)
- Economy and crafting (Ares has no economy systems at all)
- NPC AI combat profiles (Ares NPCs are stat-level tags like "Goon" or "Boss")

### 2.3 Ares Web Portal

The Ares web portal is an Ember.js single-page application that serves as a parallel interface to the game. It's *not* a Telnet-in-a-browser — it's a structured web application with its own routes, components, and real-time WebSocket updates. Key pages:

- **Home**: Welcome page with game description and connection info
- **Play**: Split-pane interface with scene list sidebar + active scene or channel
- **Characters**: Browseable character directory with profiles, sheets, relationships
- **Scenes**: Searchable scene archive with filtering by type, character, date
- **Plots**: Story arc browser linking related scenes
- **Events**: Calendar with signup
- **Forum**: BBBoard-style discussion forums
- **Wiki**: Collaborative wiki for world lore
- **Who**: Online player list with scene info
- **Locations**: Browseable room/area directory with descriptions

**Critical insight**: The Ares portal is *not* an alternative to the game client — it's an *addition*. Players use the portal to browse characters, read scene logs, sign up for events, and manage their profiles *between* play sessions. The actual gameplay still happens through the Telnet/WebSocket connection. This is the paradigm we should adopt.

---

## 3. Priority A — Features to Integrate

### 3.1 Web Portal (Out-of-Client)

**Source**: Ares Web Portal architecture
**Impact**: Transformative — this is the single biggest retention lever we don't have

#### The Problem

Our web client (`static/client.html`) is excellent for *playing the game*. But a MU* community needs a *web presence* that works when players aren't logged in. Right now, a prospective player who visits our URL sees... a login screen. They can't browse characters, read scene logs, see who's online, or learn about the world without creating an account and connecting.

Ares solved this by building a web portal that serves as the game's public face. Players spend time on the portal between sessions — reading logs, updating profiles, browsing the wiki. This creates engagement *outside* of active play sessions, which is the #1 driver of retention on modern MU* games.

#### What We Build

A lightweight web portal served by our existing aiohttp server (port 8080), accessible at the same URL as the game. It does NOT replace `client.html` — it wraps it in a broader site.

**Portal Pages** (in implementation priority order):

1. **Home/Landing** (`/`) — Game description, connection info, "Play Now" button linking to the client, online player count, recent news from GNN feed
2. **Who's Online** (`/who`) — Live player list (name, location area, idle time). Updates via WebSocket. No login required for public view.
3. **Character Directory** (`/characters`) — Browseable list of all approved characters. Each entry shows name, species, template, faction, description snippet. Links to full profile.
4. **Character Profile** (`/character/<name>`) — Full character sheet (public fields), player-written background, description, faction membership, org roles. Uses existing `Character.format_sheet()` data but renders as HTML instead of ANSI.
5. **Scene Archive** (`/scenes`) — Searchable/filterable log of completed scenes (see §3.2). Public scenes viewable without login.
6. **Event Calendar** (`/events`) — Upcoming events with signup (see §5.2).
7. **Plot Browser** (`/plots`) — Story arcs linking related scenes (see §5.3).
8. **Game Guide** (`/guide`) — Static pages for rules reference, command help. Could render our existing Guide markdown files.
9. **Play Client** (`/play`) — The existing `client.html`, now embedded as a portal route.

#### Architecture

```
aiohttp routes (server/game_server.py or new server/web_portal.py):
  GET /                    → landing page (template)
  GET /who                 → JSON: online players
  GET /characters          → JSON: character directory
  GET /character/<name>    → JSON: character profile data
  GET /scenes              → JSON: scene list (paginated, filtered)
  GET /scene/<id>          → JSON: scene detail + log
  GET /events              → JSON: event list
  GET /plots               → JSON: plot list
  GET /api/v1/*            → REST API for all portal data
  GET /play                → serves client.html (existing)
  GET /portal/*            → serves portal SPA (new)

Portal frontend:
  static/portal/           → Single-page app (vanilla JS or lightweight framework)
  static/portal/index.html → Portal shell
  static/portal/app.js     → Client-side routing, API calls, rendering
```

**Key design decisions:**

- **No separate server.** The portal runs on the same aiohttp instance. No new processes, no deployment complexity.
- **JSON API layer.** All portal data comes from a REST API (`/api/v1/`). This makes the portal a thin rendering layer over existing DB queries.
- **Public by default.** Character names, species, templates, descriptions, and public scene logs are viewable without login. Skills/attributes, private backgrounds, and financial data require authentication.
- **Authentication via existing accounts.** Portal login uses the same accounts table as the game. Session tokens via cookies.
- **Dual-Interface Principle still applies.** Everything the portal shows is also available via in-game commands. The portal adds web convenience; it never gates content.

#### DB Requirements

No new tables for the portal itself. The portal reads from existing tables: `characters`, `accounts`, `pc_narrative` (for backgrounds). Scene logging (§3.2) adds one new table.

#### Files Modified/Created

| File | Changes |
|------|---------|
| `server/web_portal.py` | **NEW FILE.** aiohttp route handlers for portal API |
| `server/game_server.py` | Register portal routes on startup |
| `static/portal/` | **NEW DIRECTORY.** Portal SPA frontend |
| `engine/character.py` | Add `to_portal_dict()` method (public-safe character data) |

#### Effort Estimate

Large — but most of the *data* already exists. The work is in the API layer and frontend. Recommend building incrementally: Landing + Who + Character Directory first, then Scene Archive, then the rest.

---

### 3.2 Scene Logging & Archive

**Source**: AresMUSH Scenes plugin
**Impact**: High — scene logs are the lifeblood of a MU* community

#### The Problem

MU* games generate collaborative fiction through RP scenes. These scenes are ephemeral — once the participants disconnect, the text is gone forever (unless someone manually copies it to a wiki). This is a massive loss. Good RP scenes are *content* — they're the stories that make the game world feel alive. Ares recognized this and built scene logging as a first-class system.

We have the PC Narrative Memory system, which logs *significant actions* for the Director AI. But we don't log the actual RP text — the collaborative poses that form the scene.

#### What We Build

A scene management system that captures RP sessions and makes them browseable.

**Scene Lifecycle:**

1. **Scene Start** — A player (or the system) creates a scene in a room. The scene is tagged with location, type (Social, Action, Plot, Vignette), and an optional title.
2. **Posing** — All `say`, `pose`/`:`, and `emit` output in the scene room is automatically captured as scene poses. OOC text is captured separately and excluded from the final log.
3. **Scene End** — The scene creator (or any participant) marks the scene complete. The system compiles all IC poses into a clean log.
4. **Sharing** — The scene creator reviews the log and chooses to "share" it (make it public on the portal) or keep it private. Shared scenes appear in the Scene Archive.

**Commands:**

| Command | Syntax | Description |
|---------|--------|-------------|
| `+scene/start` | `+scene/start [title]` | Start a scene in the current room |
| `+scene/stop` | `+scene/stop` | End the active scene |
| `+scene/title` | `+scene/title <text>` | Set/change scene title |
| `+scene/type` | `+scene/type <type>` | Set scene type (Social/Action/Plot/Vignette) |
| `+scene/summary` | `+scene/summary <text>` | Add a brief summary for the archive |
| `+scene/share` | `+scene/share` | Make the completed scene public |
| `+scene/unshare` | `+scene/unshare` | Make a shared scene private again |
| `+scenes` | `+scenes` | List your recent scenes |
| `+scene` | `+scene [id]` | View scene details or current scene info |

**Auto-start integration:** Scenes can auto-start when a pose occurs in a room that doesn't have an active scene, with a configurable setting. Alternatively, scenes auto-start when the Director AI fires an encounter or event in a room.

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS scenes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    DEFAULT '',
    summary         TEXT    DEFAULT '',
    scene_type      TEXT    DEFAULT 'Social',    -- Social, Action, Plot, Vignette
    location        TEXT    DEFAULT '',           -- Room name at time of scene
    room_id         INTEGER,                      -- FK to rooms (nullable, room may be deleted)
    creator_id      INTEGER NOT NULL REFERENCES characters(id),
    status          TEXT    DEFAULT 'active',     -- active, completed, shared
    started_at      REAL    NOT NULL,
    completed_at    REAL,
    shared_at       REAL
);

CREATE TABLE IF NOT EXISTS scene_poses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id        INTEGER NOT NULL REFERENCES scenes(id),
    char_id         INTEGER REFERENCES characters(id),  -- NULL for system poses
    char_name       TEXT    NOT NULL,                    -- Denormalized for deleted chars
    pose_text       TEXT    NOT NULL,
    pose_type       TEXT    DEFAULT 'pose',   -- pose, say, emit, ooc, system
    is_ooc          INTEGER DEFAULT 0,
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS scene_participants (
    scene_id        INTEGER NOT NULL REFERENCES scenes(id),
    char_id         INTEGER NOT NULL REFERENCES characters(id),
    PRIMARY KEY (scene_id, char_id)
);

CREATE INDEX IF NOT EXISTS idx_scene_poses_scene ON scene_poses(scene_id, created_at);
CREATE INDEX IF NOT EXISTS idx_scenes_status ON scenes(status, started_at);
CREATE INDEX IF NOT EXISTS idx_scene_participants ON scene_participants(char_id);
```

**Integration with PC Narrative Memory:** When a scene is completed, the scene summary (if provided) is automatically logged as an action in the `pc_action_log` for all participants. This feeds the existing summarization pipeline.

**Integration with Director AI:** The Director can create scenes when it fires events or encounters, pre-populating the title and type. Director-initiated combat automatically creates an "Action" scene.

**Integration with CP Engine:** Scene completion fires a CP scene bonus tick (already exists as `scenebonus`), but now with proof — the system can verify that actual posing occurred rather than relying on honor system.

**Portal display:** Scene logs render as clean HTML with character names linked to profiles, OOC stripped, and system poses formatted distinctly.

#### Files Modified/Created

| File | Changes |
|------|---------|
| `engine/scenes.py` | **NEW FILE.** SceneManager, scene lifecycle, log compilation |
| `parser/scene_commands.py` | **NEW FILE.** All +scene commands |
| `parser/comm_commands.py` | Hook `say`, `pose`, `emit` to capture into active scene |
| `server/web_portal.py` | Scene archive API endpoints |
| `db/schema.sql` | Scene tables (schema v13+) |
| `engine/cp_engine.py` | Wire scene completion to verified scene bonus |

#### Effort Estimate

Medium. The logging hooks into existing pose/say/emit are straightforward. The scene lifecycle is a state machine. The bulk of the work is the portal frontend for scene browsing.

---

## 4. Priority B — Features to Integrate

### 4.1 Tractor Beam System

**Source**: HSpace `hstractor.cpp`
**Impact**: Medium — enables a new class of space encounters and interactions

#### The Problem

Our space system has no tractor beam mechanics. WEG D6 R&E includes tractor beams in ship stat blocks (the YT-1300 has a tractor beam projector), and they're a signature Star Wars mechanic — tractor beams pulling ships into Star Destroyers, towing disabled allies, repulsing incoming projectiles.

HSpace implements tractor beams with three modes (tractor/repulse/hold) and strength-based mechanics. We should adapt this to WEG D6.

#### What We Build

A tractor beam system using the WEG D6 Starship Gunnery skill and opposed Piloting checks.

**Mechanics (WEG R&E faithful):**

- **Lock**: Tractor beam operator rolls Starship Gunnery vs. target's Starship Piloting (dodge). Success = beam locked.
- **Hold**: While locked, the target's speed is reduced by the beam's strength rating. Target can attempt to break free each round with a Piloting check vs. beam strength difficulty.
- **Tow**: A locked target at speed 0 can be towed. The towing ship's speed is reduced proportionally.
- **Repulse**: Reverses beam polarity to push targets away (increases distance by beam strength per tick).

**Commands:**

| Command | Syntax | Description |
|---------|--------|-------------|
| `tractor` | `tractor <contact#>` | Lock tractor beam on target |
| `tractor release` | `tractor release` | Release tractor lock |
| `tractor mode` | `tractor mode <hold/tow/repulse>` | Change beam mode |
| `tractor status` | `tractor status` | Show tractor beam status |

**Data:** Add `tractor_beam` field to `starships.yaml` ship templates (strength rating in D).

**Station:** Requires Engineer or dedicated Tractor station. Uses `sensors` system power.

#### Files Modified/Created

| File | Changes |
|------|---------|
| `engine/starships.py` | Tractor beam state in systems JSON, lock/release/mode logic |
| `parser/space_commands.py` | TractorCommand, TractorReleaseCommand, TractorModeCommand |
| `data/starships.yaml` | Add `tractor_beam` field to relevant ship templates |

#### Effort Estimate

Small — ~200-300 lines. Well-contained subsystem.

---

### 4.2 Boarding Links (Ship-to-Ship)

**Source**: HSpace `hshatch.cpp`, `@nav-boardlink`
**Impact**: Medium — enables boarding actions, rescue scenarios, piracy

#### The Problem

Our ships dock at planets/stations, but there's no way for two ships to connect to each other in space. In Star Wars, boarding actions are a core mechanic — stormtroopers boarding the Tantive IV, pirates boarding freighters, rescue operations connecting to disabled ships.

HSpace implements boarding via "hatches" — each ship has configurable hatch points, and a `boardlink` command creates a walkable exit between two ships' hatches. This is elegant.

#### What We Build

A boarding link system that creates temporary exits between docked ships.

**Requirements:**

1. Both ships must be in the same zone
2. Target ship must be stationary (speed 0) or tractor-locked
3. Initiating ship must be adjacent (within docking range)
4. Target ship can resist boarding (opposed Piloting or Security check)
5. While linked, a temporary exit connects the two ships' interior rooms
6. Either ship can sever the link (emergency undock)

**Commands:**

| Command | Syntax | Description |
|---------|--------|-------------|
| `board` | `board <contact#>` | Initiate boarding link with target ship |
| `board release` | `board release` | Sever boarding link |
| `board status` | `board status` | Show boarding link status |

**Director AI integration:** The Director can trigger NPC pirate boarding encounters. When NPC pirates board, hostile NPCs spawn in the player's ship interior — creating a ground combat encounter in space.

**Territory integration:** Boarding a ship in Imperial-controlled space triggers a security response (patrol dispatch).

#### Files Modified/Created

| File | Changes |
|------|---------|
| `engine/starships.py` | Boarding link state, link/unlink logic, temporary exit creation |
| `parser/space_commands.py` | BoardCommand, BoardReleaseCommand |
| `engine/combat.py` | Support for combat in ship rooms during boarding |

#### Effort Estimate

Medium — the tricky part is temporary exit management and cleanup on undock/destruction.

---

### 4.3 Pose Order Tracker

**Source**: AresMUSH Scenes posing helper
**Impact**: Medium — quality-of-life for RP scenes

#### The Problem

In multi-player RP scenes, keeping track of whose turn it is to pose is a constant social friction point. Fast posers dominate; slow posers get left behind. Ares built a pose order tracker that monitors who has posed and notifies the next person.

We have the party system and the scene concept (from §3.2), but no pose order tracking.

#### What We Build

A lightweight pose order tracker that attaches to active scenes.

**Mechanics:**

- When a scene has 3+ participants, the system tracks pose order automatically
- After each pose, the system privately notifies the next player(s) in the rotation
- Two modes: **Round-robin** (strict A→B→C→A) and **3-per** (everyone gets 3 poses per cycle, go in any order, system tracks who's used theirs)
- `+scene/poseorder` shows current order and who's up next
- `+scene/drop <name>` removes someone from the rotation (if they leave)
- Entirely optional — scenes work fine without it

**Integration:** This hooks into the scene system (§3.2). When a scene is active and has 3+ participants, pose order tracking activates automatically. Web client shows whose turn it is in the combat/scene sidebar.

#### Files Modified/Created

| File | Changes |
|------|---------|
| `engine/scenes.py` | Pose order tracking methods |
| `parser/scene_commands.py` | PoseOrderCommand, DropPoseOrderCommand |
| `static/client.html` | Pose order indicator in scene panel |

#### Effort Estimate

Small — ~150-200 lines. Purely additive.

---

## 5. Priority C — Features to Integrate

### 5.1 Event Calendar with Signup

**Source**: AresMUSH Events plugin
**Impact**: Medium — community coordination tool

#### The Problem

MU* games thrive on scheduled events — plot runs, social gatherings, PvP tournaments. Right now, event coordination happens on Discord or OOC channels. An in-game event calendar with web portal visibility would consolidate this.

#### What We Build

A simple event system with in-game commands and portal visibility.

**Commands:**

| Command | Syntax | Description |
|---------|--------|-------------|
| `+events` | `+events` | List upcoming events |
| `+event` | `+event <id>` | View event details |
| `+event/create` | `+event/create <title>=<date> <time>` | Create an event |
| `+event/signup` | `+event/signup <id>` | Sign up for an event |
| `+event/cancel` | `+event/cancel <id>` | Cancel your signup |

**Integration:** Events appear on the web portal calendar. When an event starts, the system can auto-create a scene (§3.2) for logging.

**Schema:** One `events` table (title, description, datetime, creator_id, location) + one `event_signups` table.

#### Effort Estimate

Small — straightforward CRUD with a datetime field.

---

### 5.2 Plot/Story Arc Tracker

**Source**: AresMUSH Scenes plot system
**Impact**: Medium — helps players follow ongoing narratives

#### The Problem

The Director AI generates emergent narrative, but there's no way for players to see the "big picture" of ongoing story arcs. Ares's plot system links related scenes into named story arcs with storyteller attribution.

#### What We Build

A plot tracker that groups related scenes and Director-generated events into named arcs.

**Commands:**

| Command | Syntax | Description |
|---------|--------|-------------|
| `+plots` | `+plots` | List active plots |
| `+plot` | `+plot <id>` | View plot details and linked scenes |
| `+plot/create` | `+plot/create <title>=<summary>` | Create a plot (admin/storyteller) |
| `+plot/link` | `+plot/link <plot_id>=<scene_id>` | Link a scene to a plot |

**Director AI integration:** The Director can auto-create plots from faction turn events and link Director-initiated scenes to existing plots. This gives the emergent narrative a structured wrapper that players can browse.

**Portal display:** Plots page shows active arcs with scene counts, storytellers, and summaries. Clicking through shows all linked scenes in chronological order.

**Schema:** One `plots` table + one `plot_scenes` junction table.

#### Effort Estimate

Small — lightweight wrapper over the scene system.

---

## 6. What We Explicitly Skip (and Why)

### 6.1 HSpace Features Not Worth Porting

**3D coordinate movement**: HSpace uses XY heading + Z heading for true 3D navigation. Our zone-based system is deliberately simpler and more narratively flexible. 3D coordinates add mechanical complexity without gameplay value in a text game.

**Per-system stress model**: HSpace tracks stress accumulation on overloaded systems. Our reactor power allocation already provides this pressure. Adding per-system stress would make engineering micro-management tedious.

**Missile as independent 3D objects**: HSpace missiles are tracked objects that fly across space over multiple cycles. Our proton torpedoes resolve on firing (WEG R&E: "fire control" roll, hit or miss). The WEG rules don't model missile flight time.

**Console-independent headings**: HSpace lets each gunnery console aim independently of the ship. WEG D6 doesn't model turret facing — fire arcs are simply "all" or "front/rear/left/right". Adding per-console headings would contradict the ruleset.

**Jump/warp drives**: HSpace has both warp (continuous speed multiplier) and jump (instant teleport). Our hyperspace system (astrogation → travel time → arrival) is WEG-faithful and already excellent.

**Cloaking devices**: HSpace has a sophisticated cloaking/tachyon detection interplay. We *could* add this, but it's niche — cloaking devices are rare in the GCW era. Defer unless players request it.

### 6.2 Ares Features Not Worth Porting

**Full wiki system**: Ares has a collaborative wiki with revision history, tagging, and templates. This is a significant engineering effort and our Director AI + game guides already provide world lore. If players want a wiki, we can link to an external one.

**Forum/BBS**: Ares has built-in forums. Standard MU* `+bbread`/`+bbpost` commands would be lighter weight if we need this. Lower priority than the portal and scenes.

**Chargen from web**: Ares lets players create characters entirely through the web portal. Our wizard-based chargen is already smooth and WEG-specific. Web chargen would be nice eventually but is a large frontend effort for modest gain.

**Roster/idle management**: Ares has sophisticated roster systems for claimed/unclaimed characters and idle sweeping. We're a single-game server, not a platform — simpler idle policies suffice.

**FS3 combat web management**: Ares lets GMs manage entire combats from the web (adding NPCs, setting weapons, rolling turns). Our combat system is fast enough that in-game commands work well. Web combat management would be a large effort.

---

## 7. Implementation Roadmap

### Phase 1: Scene Logging (Priority A, Medium effort)

Build the scene system (§3.2) first because it's self-contained, immediately useful, and a prerequisite for the portal scene archive. This can ship as a pure Telnet feature before any portal work begins.

**Drops:**
1. Scene model + commands (`+scene/start`, `+scene/stop`, `+scene/share`)
2. Pose capture hooks (say/pose/emit → scene_poses)
3. Scene completion + log compilation
4. CP engine integration (verified scene bonus)
5. Director AI integration (auto-scene on encounters)

### Phase 2: Web Portal Foundation (Priority A, Large effort)

Build the portal framework and first three pages. This establishes the architecture that all subsequent portal features use.

**Drops:**
1. Portal server routes + SPA shell (`/`, `/who`, `/play`)
2. Character directory + profile pages (`/characters`, `/character/<name>`)
3. Scene archive (`/scenes`, `/scene/<id>`)
4. Authentication (login via existing accounts)

### Phase 3: Space Enhancements (Priority B, Medium effort)

Build tractor beams and boarding links. These are gameplay-enriching and relatively self-contained.

**Drops:**
1. Tractor beam system (lock/hold/tow/repulse)
2. Boarding links (ship-to-ship exits)
3. Director AI boarding encounters (pirate boarding events)

### Phase 4: RP Quality-of-Life (Priority B+C, Small effort)

Pose order tracker, event calendar, and plot tracker. All lightweight additions.

**Drops:**
1. Pose order tracker in scene system
2. Event calendar (commands + portal page)
3. Plot/story arc tracker (commands + portal page)

---

## 8. Architecture Impact

### 8.1 New Files

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `engine/scenes.py` | Scene lifecycle, logging, pose order | ~500 |
| `parser/scene_commands.py` | Scene commands | ~400 |
| `server/web_portal.py` | Portal API routes | ~600 |
| `static/portal/index.html` | Portal SPA shell | ~100 |
| `static/portal/app.js` | Portal client-side app | ~1500 |
| `static/portal/style.css` | Portal styles | ~500 |
| `engine/events.py` | Event calendar | ~200 |
| `parser/event_commands.py` | Event commands | ~200 |
| `engine/plots.py` | Plot tracker | ~150 |
| `parser/plot_commands.py` | Plot commands | ~150 |

**Total new code:** ~4,300 lines across 10 files.

### 8.2 Schema Changes

Three new table groups (scenes, events, plots) = schema v13. All additive — no modifications to existing tables.

### 8.3 Architecture Doc Updates

- New §14F: Scene Management System
- New §14G: Event Calendar
- New §14H: Plot Tracker
- New §22: Web Portal Architecture
- Update §15 (Space): Tractor beams, boarding links
- Update §21 (Web Client): Portal integration, scene panel

### 8.4 Dual-Interface Compliance

All features remain fully playable on Telnet. The web portal is *additive* — it provides browse/read/manage capabilities that supplement the game client. No portal-only actions exist; every portal interaction maps to an in-game command.

---

## 9. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Portal frontend scope creep | High | Ship Landing + Who + Characters first; iterate |
| Scene logging performance (busy rooms) | Low | Batch INSERT, async writes, prune old poses |
| Pose capture breaks existing output | Low | Capture is append-only; never modifies pose delivery |
| Boarding link exit cleanup on crash | Medium | Startup sweep: delete all temporary exits |
| Tractor beam balance issues | Low | WEG D6 opposed rolls are inherently balanced |

---

## 10. References

| Source | Key Takeaways |
|--------|--------------|
| HSpace 4.4.1 (`hstractor.cpp`, `hshatch.cpp`) | Tractor beam modes, boarding link architecture |
| HSpace 4.4.1 (`hssensors.cpp`, `hsship.cpp`) | Confirmed our sensor system is already superior |
| AresMUSH Scenes plugin (`plugins/scenes/`) | Scene lifecycle, pose capture, log compilation, sharing model |
| AresMUSH Scenes posing helper | Pose order tracking, 3-per mode, next-turn notification |
| AresMUSH Events plugin | Event CRUD, signup, scene auto-creation |
| AresMUSH Scenes plot system | Plot-scene linking, storyteller attribution |
| AresMUSH Profile plugin | Character web profiles, relationship display |
| Ares Web Portal (`app/router.js`) | Full page inventory, SPA architecture |
| Ares Web Portal (`app/templates/play.hbs`) | Split-pane play interface, scene sidebar |
| Ares Web Portal (`app/services/game-socket.js`) | WebSocket real-time update pattern |
| SW_MUSH Architecture v21 | Current state baseline for gap analysis |
| SW_MUSH TinyMUX Comparison v1 | Prior competitive analysis confirming our strengths |

---

*End of Design Document — HSpace & AresMUSH Feature Integration Analysis v1.0*
*Reference docs: `sw_d6_mush_architecture_v21.md`, `tinymux_comparison_design_v1.md`, `web_ux_competitive_analysis.md`*
