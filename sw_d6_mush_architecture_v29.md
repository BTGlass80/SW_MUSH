# SW_MUSH — Architecture Document v29

**Star Wars D6 MUSH · WEG Revised & Expanded · Galactic Civil War Era**
**April 17, 2026 · BTGlass80**

---

## 1. Project Overview

A Star Wars-themed MUSH (Multi-User Shared Hallucination) text game built in Python. Implements the **West End Games D6 Revised & Expanded** ruleset. Set during the Galactic Civil War era with Mos Eisley as the primary hub, expanded across four planets. Solo developer project (GitHub: BTGlass80).

**Runtime:** Python 3.x, asyncio, aiohttp, aiosqlite
**AI:** Ollama/Mistral 7B (NPC dialogue + idle queue tasks, constrained to RTX 3070 8GB), Claude Haiku (Director AI system, narrative summarization)
**Transport:** Telnet (port 4000) + WebSocket (port 4001), HTTP static serving + REST API (port 8080)
**Database:** SQLite via custom `Database` class with `DatabaseProxy` wrapper (session 33), schema v16 (v11 map coords; v12 credit_log; v13 scenes; v14 achievements; v15 npc_crew; v16 plots)
**Codebase:** ~90,000 lines Python + ~9,500 lines client HTML (client.html + chargen.html + portal.html) + ~29,000 lines tests

---

## 2. File Tree

```
SW_MUSH/
├── main.py
├── server/
│   ├── game_server.py         [v28] Boot, command registry, tick loop via TickScheduler, 30+ module imports, mail login hook, achievement loader, web chargen flow (_run_web_chargen, __token_auth__)
│   ├── session.py             [v28] Protocol-agnostic session, HUD update with room detail card, NPC roles, loadout, area map, active jobs, housing_info, reputation dicts, rep_change/rank_up/chargen_start Telnet-ignored
│   ├── api.py                 [v28] **NEW** — REST API: 8 chargen endpoints, HMAC-SHA256 token auth, IP rate limiting, skill key normalization — 605 lines
│   ├── tick_scheduler.py      [v22] TickScheduler, TickContext, TickHandler — 20+ registered handlers
│   ├── tick_handlers_ships.py [v22/v29] Ship tick handlers: ion/tractor, sublight, hyperspace, asteroid, anomaly, encounter_tick, texture_encounter_tick
│   ├── tick_handlers_economy.py [v23] Economy tick handlers: patrol, board, ambient, world, Director, CP, wages, payroll, vendor, housing, territory (5×), debt
│   ├── telnet_handler.py
│   ├── websocket_handler.py
│   ├── web_client.py          [v28] aiohttp WebSocket on /ws, /chargen route, /client.html route, ChargenAPI registration, token_auth WS handling
│   ├── channels.py            [v12] ChannelManager singleton
│   ├── ansi.py                ANSI color helpers
│   └── config.py              [v28] /chargen link in welcome banner
├── engine/
│   ├── combat.py              [v22] CombatInstance, to_hud_dict(), verb variety, wound escalation, armor soak, stun routing, CP-on-soak
│   ├── combat_flavor.py       [v19] Verb variety pools, margin-based flavor text
│   ├── dice.py                [v1/v22] D6 dice engine — single source of truth for all rolls
│   ├── character.py           Character data model
│   ├── creation.py            Character creation
│   ├── creation_wizard.py     Interactive creation wizard
│   ├── chargen_validator.py   [v28] **NEW** — Server-side chargen validation: species ranges, attribute pip totals, 2D skill bonus cap, name validation, account field validation — 198 lines
│   ├── items.py               Item instance system
│   ├── weapons.py             Weapon definitions
│   ├── species.py             9 species templates
│   ├── starships.py           [v5/v19] Ship management, get_effective_stats()
│   ├── force_powers.py        [v6] 8 Force powers, DSP, fall checks
│   ├── missions.py            [v23/v29] Mission board (14 types: 10 ground + 4 space), faction missions (empire/rebel/hutt/bh_guild), rep-gated board display, fixed spawn weights & refresh
│   ├── bounty_board.py        [v8] Bounty board (5 tiers)
│   ├── npc_combat_ai.py       [v4] 5 NPC combat profiles
│   ├── npc_generator.py       NPC stat generation
│   ├── npc_loader.py          NPC loading from YAML
│   ├── npc_crew.py            [v5] NPC crew management, wage ticks
│   ├── npc_space_crew.py      [v5] Space crew station assignment
│   ├── npc_space_traffic.py   [v6/v29] NPC space traffic spawning, zone security profiles, encounter creation, imperial boarding/customs
│   ├── space_encounters.py    [v29 — NEW] SpaceEncounter framework, EncounterManager singleton, choice presentation, deadline tick — 594 lines
│   ├── encounter_patrol.py    [v29 — NEW] Imperial patrol encounter (4-choice: Comply/Bluff/Run/Hide) — 614 lines
│   ├── encounter_pirate.py    [v29 — NEW] Pirate attack encounter (Pay/Negotiate/Fight/Flee) — 252 lines
│   ├── encounter_hunter.py    [v29 — NEW] Bounty hunter encounter (Surrender/Fight/Flee/Negotiate) — 217 lines
│   ├── encounter_texture.py   [v29 — NEW] Texture encounters: mechanical, cargo, contact — 534 lines
│   ├── encounter_anomaly.py   [v29 — NEW] 6 anomaly encounter types (distress, cache, pirate nest, mineral, dead drop, mynock) — 432 lines
│   ├── npc_space_combat_ai.py [v29 — NEW] NPC space combat AI, 5 profiles (aggressive/cautious/pursuit/ambush/patrol) — 543 lines
│   ├── space_anomalies.py     [v16] 7 anomaly types, spawn tick, deepscan resolution
│   ├── trading.py             [v19/v23] 8 trade goods, planet price tables, SupplyPool class (45-min refresh, per-good caps)
│   ├── ships_log.py           [v19] 17 milestones, 6 titles, CP tick rewards
│   ├── party.py               [v12] PartyManager
│   ├── world_events.py        [v12] World event system
│   ├── ambient_events.py      [v12] Zone-based ambient flavor
│   ├── director.py            [v28] Director AI — 5 core drops + faction_status + pc_hooks + faction_orders + era-progression milestones + player_faction_standings digest — 1,787 lines
│   ├── cp_engine.py           [v14/v23] CP progression, tick economy, train command — rebalanced constants
│   ├── skill_checks.py        [v13/v22] Central skill check engine (ALL out-of-combat rolls), mission completion resolver
│   ├── smuggling.py           [v13/v23] Smuggling job board (5 route tiers), fixed class ordering
│   ├── crafting.py            [v15] SWG-lite crafting (resources, assembly, experimentation, teaching)
│   ├── security.py            [v21] SecurityLevel enum, get_effective_security(character=), Director overrides, combat/PvP gates, territory claim upgrade
│   ├── territory.py           [v21/v25] Territory influence engine, room claiming, guard NPCs, armory, resource nodes, contesting, hostile takeover — 1,937 lines
│   ├── housing.py             [v21/v26] Player housing ALL 9 DROPS DELIVERED: rented rooms, desc editor, trophies, faction quarters, private residences, shopfronts, intrusion, org HQs, web panel, AI descriptions — 3,194 lines
│   ├── scenes.py              [v25] Scene logging: start/stop/share lifecycle, pose capture, CP bonus on completion, archive query — 474 lines
│   ├── organizations.py       [v28] Factions (5) + guilds (6), join/leave, payroll, equipment, territory hooks, **faction reputation system** (adjust_rep, get_char_faction_rep, get_all_faction_reps, get_faction_shop_modifier, get_faction_standing_context, auto-promotion, defection penalties) — 1,560 lines
│   ├── narrative.py           [v20/v26] Two-tier PC records, action logging, nightly Haiku summarization, thoughts + scars injection
│   ├── vendor_droids.py       [v20] 3-tier vendor droids, stock/unstock/buy with item transfer, buy orders, auto-recall
│   ├── tutorial.py            [v12] Legacy tutorial (basic 7-step)
│   ├── tutorial_v2.py         [v21] Tutorial state machine, hint system, elective modules, factions elective, 6 profession chains
│   ├── spacer_quest.py        [v23] "From Dust to Stars" 30-step quest chain engine, check_spacer_quest() hook
│   ├── debt.py                [v23] Hutt debt tick handler: weekly auto-deduction, missed payment warnings, enforcer escalation
│   ├── area_map.py            [v23] Area map BFS + auto-layout/hand-tuned coords, env/sec metadata, NPC service detection
│   ├── cooldowns.py           [v26] Centralized cooldown handler: check/set/clear per-character cooldowns in attributes JSON — 175 lines
│   ├── scars.py               [v26] Permanent wound scar system: 15 body locations, weapon-type descriptions, +sheet integration — 204 lines
│   ├── zone_tones.py          [v26] Narrative tone per zone: loads data/zones.yaml, injected into Director + NPC brain prompts — 137 lines
│   ├── sleeping.py            [v28] **NEW** — Sleeping character vulnerability: disconnect flag in non-secured rooms, pickpocket check, theft logging, reconnect notification — 298 lines
│   ├── espionage.py           [v28] Espionage engine: scan, eavesdrop, investigate, intel report, **comlink intercept** — 500 lines
│   ├── achievements.py        [v27] Achievement engine: YAML loader, 30 achievements in 7 categories, progress tracking, check/award logic, 20+ typed hook wrappers, CP bypass — 430 lines
│   ├── text_format.py         Text formatting utilities
│   ├── sheet_renderer.py      Character sheet display
│   ├── matching.py            Fuzzy name matching
│   ├── locks.py               [v23] Lock/key system + faction:X lock type
│   └── entity_actor.py        Entity actor abstraction
├── ai/
│   ├── providers.py           AI provider abstraction
│   ├── claude_provider.py     [v12] ClaudeProvider, budget tracking, circuit breaker
│   ├── intent_parser.py       Natural language intent parsing
│   ├── bounded_validator.py   Bounded context validation
│   ├── scene_context.py       Scene context builder
│   └── npc_brain.py           [v28] NPC dialogue, persuasion_context, pc_short_record injection, zone tone injection, **faction_standing context injection**
├── parser/
│   ├── commands.py            BaseCommand, AccessLevel, command registry
│   ├── builtin_commands.py    [v28] 20+ commands — look, move, who, say, think, trade (credits + items), **pickpocket** (sleeping chars), etc.
│   ├── combat_commands.py     [v26] 19 commands — attack (stun mode, armor), dodge, aim, flee, challenge, accept, decline, +soak, wear/remove armor + achievement hooks
│   ├── space_commands.py      [v28] 49 commands — full space system + FDTS hooks + achievement hooks + **faction shop discounts on NPC weapon buy** — 5,415 lines
│   ├── building_commands.py   11 commands — @dig, @describe, @create, etc.
│   ├── building_tier2.py      [v23] 12 commands — advanced building + @getattr/@setattr admin tools
│   ├── channel_commands.py    [v12] 10 commands — pub, comms, etc.
│   ├── crew_commands.py       [v5] 6 commands — crew management
│   ├── force_commands.py      [v26] 3 commands — Force powers + achievement hooks
│   ├── mission_commands.py    [v26] 5 commands — mission board + territory/FDTS/achievement hooks
│   ├── bounty_commands.py     [v21] 5 commands — bounty board + territory/FDTS hooks
│   ├── npc_commands.py        [v28] 4 commands — NPC interaction + profession chain + FDTS hooks + **faction standing context in TalkCommand** — 1,103 lines
│   ├── d6_commands.py         3 commands — dice rolling
│   ├── director_commands.py   [v12] 1 command — @ai
│   ├── news_commands.py       1 command — news board
│   ├── smuggling_commands.py  [v25] 5 commands — smuggling jobs + territory/FDTS hooks + skill check routing fix
│   ├── medical_commands.py    [v14] 3 commands — heal/healaccept/healrate
│   ├── entertainer_commands.py [v14] 1 command — perform
│   ├── cp_commands.py         [v26] 4 commands — train, kudos + achievement hooks
│   ├── sabacc_commands.py     [v26] 1 command — sabacc + achievement hooks
│   ├── crafting_commands.py   [v25/v26] 6 commands — survey/resources/craft/experiment/teach + achievement hooks + survey room fix
│   ├── tutorial_commands.py   [v12] 1 command — tutorial
│   ├── party_commands.py      [v12] 2 commands — party management
│   ├── faction_commands.py    [v28] faction command — join/leave/status/invest/influence/claim/unclaim/guard/armory/seize + **+reputation** — 677+ lines
│   ├── housing_commands.py    [v21/v25] rent/checkout/storage/sethome/home, describe/trophy/name, faction housing, residence/shopfront purchase+sell, intrusion log
│   ├── shop_commands.py       [v20/v25] 3 commands — shop buy/place/recall/name/desc/stock/unstock/upgrade, browse, market search, @shop — 916 lines
│   ├── faction_leader_commands.py [v20] 2 commands — leader ops, @faction admin
│   ├── narrative_commands.py  [v20] 7 commands — +background, +recap, +quests, quest ops, @narrative
│   ├── scene_commands.py      [v26] +scene/start|stop|title|type|summary|share|unshare, +scenes, +scene [id] + achievement hooks — 439 lines
│   ├── spacer_quest_commands.py [v23] +quest/+quest log/+quest abandon, debt/debt pay/debt payoff, travel <planet>
│   ├── encounter_commands.py  [v29 — NEW] respond, stationact, encounter, investigate — 291 lines
│   ├── plot_commands.py       [v29 — NEW] 8 plot/story arc commands — 350 lines
│   ├── espionage_commands.py  [v28] scan, eavesdrop, investigate, +intel, **intercept/intercept stop/intercept status** — 648 lines
│   ├── achievement_commands.py [v27] +achievements [category] — progress bars, category filter, web client JSON — 180 lines
│   ├── mux_commands.py        [v23] 11 commands: page, +finger/+finger/set, +where, @name, @clone, @decompile, @pemit, @wall, @force, @newpassword, @shutdown
│   ├── places_commands.py     [v23] 11 commands: places, join/sit, depart/stand, tt, ttooc, mutter, @osucc/@ofail/@odrop, @places, @place
│   ├── attr_commands.py       [v23] 4 commands: @setattr/&, @wipe, @getattr, @lattr + AENTER/ALEAVE event hooks
│   └── mail_commands.py       [v23] @mail with 9 subcommands: list, compose, quick, read, reply, forward, delete, purge, sent, unread
├── db/
│   └── database.py            [v27] Schema v14 (v11 map coords, v13 object_attributes + scenes, v14 character_achievements), 110+ async methods, 5 attribute helpers
├── data/
│   ├── skills.yaml            75 skills, 6 attributes
│   ├── species/               9 species templates
│   ├── weapons.yaml           Weapon definitions
│   ├── starships.yaml         19 ship templates (with reactor_power field)
│   ├── npcs_gg7.yaml          NPC templates from Galaxy Guide 7
│   ├── ambient_events.yaml    [v12] Static ambient flavor text, 7 zones
│   ├── schematics.yaml        [v15/v19] 20 crafting schematics (8 weapons, 3 consumables, 7 ship components, 2 countermeasures)
│   ├── organizations.yaml     [v17] 5 factions + 6 guilds, rank structures, equipment tables
│   ├── achievements.yaml      [v27] 30 achievements in 7 categories (combat, space, economy, crafting, social, exploration, force), CP rewards, trigger events
│   ├── skill_descriptions.yaml [v28] 75 skill descriptions with game_use, tip, gameplay_note — 1,122 lines. Used by chargen API and tooltip system
│   ├── vendor_droids.yaml     [v18] 3 droid tier definitions (cost, slots, listing fee, bargain dice)
│   ├── zones.yaml             [v26] 14 zone narrative tone strings (4 planets + space)
│   └── help_topics.py         Help system data
├── static/
│   ├── client.html            [v28] ~6,900 lines — Browser client: ANSI rendering, space HUD, ground UX, combat panel, security badges, ship schematic, context-sensitive quick buttons with tooltips, housing/vendor detection, achievement toast, **reputation panel + rep-change/rank-up notifications**, chargen overlay with iframe integration
│   └── chargen.html           [v28] **NEW** — ~1,830 lines — Single-page vanilla JS character creation wizard. 8-step (standalone) or 7-step (embedded) flow. Same design language as client.html (Share Tech Mono, Orbitron, Rajdhani, dark sci-fi palette). JS-positioned tooltip system. Template presets. Species attribute range enforcement.
├── build_mos_eisley.py        [v23] World builder v4 — 120 rooms, 4 planets, security zones, ~39 PLANET_NPCs, 120 hand-tuned map coordinates
├── build_tutorial.py          [v25] Tutorial zone rooms, NPCs, items — fixed build ordering for fresh DBs
├── tests/
│   ├── harness.py             [v27] Test framework core: MockSession, TestHarness (full game stack boot), assertion helpers — 480 lines
│   ├── conftest.py            [v27] pytest fixtures: harness, harness_empty, player_session
│   ├── test_world_integrity.py    [v27] 12 tests — room/exit/NPC/ship structural validation
│   ├── test_core_systems.py       [v27] 24 tests — look, move, sheet, inventory, say, emote, help, who
│   ├── test_combat.py             [v27] 16 tests — attack, dodge, parry, PvP, range, cover, respawn
│   ├── test_combat_mechanics.py   [v27] 31 tests — CombatInstance engine: multi-action, wounds, Force Points, full dodge, initiative, statistical validation
│   ├── test_economy.py            [v27] 13 tests — shops, missions, smuggling, credits persistence
│   ├── test_economy_validation.py [v27] 45 tests — all 6 audit vulnerabilities: trade goods caps, Bargain gate, mission skill checks, survey cooldowns, CP progression, faucet rates
│   ├── test_space.py              [v27] 14 tests — ship listing, boarding, crew, launch/land, scan, fire
│   ├── test_space_lifecycle.py    [v27] 16 tests — full lifecycle: spawn, board, pilot, launch, deducts fuel, can't double-launch
│   ├── test_crafting.py           [v27] 9 tests — survey, resources, schematics, craft, experiment, teach
│   ├── test_force.py              [v27] 8 tests — Force status, powers, dark side, force points
│   ├── test_factions.py           [v27] 7 tests — faction list/info/join, guilds, territory
│   ├── test_factions_deep.py      [v27] 14 tests — org seeding, join/leave lifecycle, roster, guild, specialization, territory schema
│   ├── test_housing.py            [v27] 4 tests — housing listing, availability, my housing, sethome
│   ├── test_professions.py        [v27] 11 tests — bounty, espionage, medical, entertainer, NPC talk, sabacc
│   ├── test_progression.py        [v27] 10 tests — CP display/spending, D6 rolls, skill check routing
│   ├── test_social_systems.py     [v27] 18 tests — mail, places, scenes, narrative, MUX compat, buffs, equipment, lockpick
│   ├── test_crew_and_parties.py   [v27] 6 tests — NPC crew, party invite/leave, spacer quest
│   ├── test_admin.py              [v27] 8 tests — admin access control, @dig, @desc, director, NPC management
│   ├── test_tutorial.py           [v27] 39 tests — core tutorial, training grounds, all 8 electives, sub-rooms
│   ├── test_multiplayer.py        [v27] 15 tests — PvP, player trade, say/whisper visibility, party, scene with 2 players
│   └── test_tick_scheduler.py     [v22] 38 unit tests for TickScheduler and ship handlers
└── pytest.ini                 [v27] pytest configuration
```

---

## 3. Core Architecture

### 3.1 Server & Session Layer
`game_server.py` boots Telnet/WebSocket/HTTP, manages command registry (30+ module imports including 4 MUX compat modules + spacer quest + achievements), runs 1s async tick loop via `TickScheduler`, handles login/creation. Achievement data loaded from `data/achievements.yaml` on boot. Mail notification hook fires on login (`notify_unread_mail`). Tick loop delegates to 21+ registered handlers in `tick_scheduler.py` (110 lines) + `tick_handlers_ships.py` (302 lines) + `tick_handlers_economy.py` (~280 lines). Nightly jobs scheduled via `schedule_nightly_job` at 03:00 daily (narrative summarization). One inline block remains: `tick_npc_space_combat`.

**Web chargen flow [v28]:** When a WebSocket user creates an account with no characters, `_character_select()` branches to `_run_web_chargen()` which generates a 30-minute HMAC token and sends `{"type":"chargen_start","token":"..."}` via `send_json()`. Server waits for `__chargen_done__` message, then loads the most recently created character and enters the game. `__token_auth__` handler in the login loop validates tokens for auto-login from standalone chargen redirect.

Sessions are protocol-agnostic (~1,019 lines). `_input_intercept` callable bypasses normal command dispatch for multi-turn editors (housing description, @mail compose). HUD update includes `is_housing`, `roomHasVendors`, room detail card (description, services, NPC roles/actions), loadout, area map data, active jobs, and `reputation` dict via `get_all_faction_reps()`. Telnet-ignored JSON types include `chargen_start`, `rep_change`, `rank_up`.

### 3.2 Web Client [v28]
`static/client.html` (~6,900 lines). Split-pane browser client with ANSI-to-HTML rendering, HUD sidebar, command history, mobile responsive.

**Space HUD:** Space panel, station-aware quick buttons, zone map SVG, tactical radar SVG, power allocation bar, captain's order badge, ship status schematic, ambient mood theming.

**Ground UX [v23]:** Room detail card (name, zone+security pill badges, truncatable description, service icons row), NPC role icons (⚔️ hostile, 🛡 guard, 🎓 trainer, 🛒 vendor, ⚙ mechanic, 🍺 bartender, 💬 neutral, 👤 player) with server-driven action buttons, loadout sidebar (equipped weapon, armor, consumables), area map with environment-colored nodes (20+ env types), security-colored borders, service icons, fullscreen modal with zoom/pan/legend, active jobs tracker (missions/bounties/smuggling in sidebar), smart context-sensitive quick buttons.

**Combat panel:** Wound pips, initiative order, declared actions, cover/aim/fleeing status, ★ viewer marker, phase labels, round badge.

**Reputation panel [v28]:** Collapsible "Faction Standing" sidebar panel with colored tier bars per faction and rank display for members. Rep-change slide-in notification (2.5s auto-dismiss, left edge). Rank-up toast notification (4s, centered with star animation). 9 rep tier colors (fill bars + text). `toggleRepPanel()` expand/collapse.

**Achievement toast [v27]:** Floating notification slides in from right on `achievement_unlocked` event. Gold-bordered card with icon, name, description, CP reward. Auto-dismisses after 4.5s with fade-out animation.

**Chargen overlay [v28]:** Fullscreen iframe container for `/chargen?embedded=1&token=XXX`. `handleChargenStart()` shows overlay on `chargen_start` JSON message. `postMessage` listener catches `chargen_done` from iframe, hides overlay, sends `__chargen_done__` via WebSocket. Token auto-login on WS open via `URLSearchParams` (for standalone chargen redirect).

**Other:** Security zone badges (color-coded), context-sensitive quick buttons via `QUICK_MODES` with tooltip descriptions, housing and vendor droid detection, territory claim badge with guard symbol and contested-glow.

### 3.2A Web Character Creation [v28 — NEW]

Design doc: `web_chargen_design_v1.md`. Three new files, five modified files.

**`static/chargen.html`** (~1,830 lines) — Single-page vanilla JS character creation wizard. Same design language as `client.html` (Share Tech Mono, Orbitron, Rajdhani, dark sci-fi palette). JS-positioned tooltip system with edge clamping.

**Two modes:**
- **Standalone** (`/chargen`): Full 8-step wizard including account creation (Account → Path → Species → Attributes → Skills → Force → Story → Review). Submits to `/api/chargen/submit`. Redirects to `/client.html?token=XXX` on success.
- **Embedded** (`/chargen?embedded=1&token=XXX`): 7-step wizard (no Account step — account already exists from `create` command). Submits to `/api/chargen/create-character`. Sends `postMessage({type:'chargen_done'})` to parent.

**`server/api.py`** (605 lines) — REST API under `/api/chargen/*`. HMAC-SHA256 token generation/verification with configurable TTL. IP-based rate limiting (3 submits/min). Skill description key normalization (underscore ↔ space mapping between YAML and skill registry).

| Method | Route | Auth | Purpose |
|--------|-------|------|---------|
| GET | `/api/chargen/species` | None | All 9 species with attribute ranges, abilities, story factors |
| GET | `/api/chargen/species/{name}` | None | Single species detail |
| GET | `/api/chargen/skills` | None | 75 skills grouped by 6 attributes, with descriptions/tips/tags |
| GET | `/api/chargen/templates` | None | 7 templates with tagline, description, gameplay, key_skills |
| POST | `/api/chargen/validate` | None | Dry-run validation, returns error list |
| GET | `/api/chargen/check-name/{name}` | None | Live name availability check |
| POST | `/api/chargen/submit` | None | Create account + character atomically (standalone) |
| POST | `/api/chargen/create-character` | Token | Create character only for existing account (embedded) |

**`engine/chargen_validator.py`** (198 lines) — Server-side validation: species attribute ranges, attribute pip total enforcement, 2D skill bonus cap, character name validation (pattern + forbidden canon names), account field validation (username length, password strength).

**Token architecture:** `create_login_token(account_id, ttl)` produces HMAC-SHA256 signed tokens with base64 payload. Embedded chargen gets 30-minute TTL (issued by `_run_web_chargen`). Standalone redirect gets 5-minute TTL (issued by `handle_submit`). `_TOKEN_SECRET` is random bytes, regenerated on server restart.

### 3.3 Command Parser
`BaseCommand` with `key`, `aliases`, `help_text`, `usage`, `async execute(ctx)`. Prefix-match dispatch. `COMMAND_TIMEOUT = 30.0s`. `AccessLevel` gates builder/admin. **~252 command classes** across 35 modules.

### 3.4 Database Layer
`database.py` wraps aiosqlite. **Schema v14** declared in code. Migrations: v11 added `map_x`/`map_y` columns to rooms; v12 added `credit_log` table; v13 added `scenes`, `scene_poses`, `scene_participants` tables; v14 added `character_achievements` table + indexes. Tables: accounts, characters, rooms, exits, zones, objects, missions, bounties, ships, npcs, npc_memory, zone_influence, director_log, smuggling_jobs, cp_ticks, kudos_log, organizations, org_ranks, org_memberships, issued_equipment, issued_ships, guild_dues, faction_log, pc_narrative, pc_action_log, personal_quests, shop_transactions, player_housing, housing_lots, territory_influence, territory_claims, territory_contests, housing_intrusions, object_attributes, mail, mail_recipients, credit_log, scenes, scene_poses, scene_participants, character_achievements. 110+ async methods including 5 attribute helpers (`get_attribute`, `set_attribute`, `delete_attribute`, `list_attributes`, `wipe_attributes`) and credit logging (`log_credit`, `get_credit_velocity`).

### 3.5 Tick Loop [v22/v23]
1-second async tick dispatches through `TickScheduler` (21+ registered handlers). `TickContext` provides shared `ships_in_space` list (fetched once per tick), `db`, `session_mgr`, and `tick_count`. Ship handlers: ion/tractor decay, sublight transit, hyperspace arrival, asteroid collision (30-tick), space anomaly (300-tick). Economy handlers: patrol, board housekeeping, ambient events, world events, Director AI, CP engine, crew wages (4hr), faction payroll (daily), vendor recall (daily), housing rent (weekly@432K), territory presence/decay/claim/resources/contests (various), debt payment (weekly). One inline block remains: `tick_npc_space_combat`. Nightly summarization job at 03:00. Monotonic deadline scheduling with skip-ahead on >5 tick lag.

---

## 4. World Layout

### 4.1 Room Index Layout (World Builder v4)

```
Tatooine / Mos Eisley:  rooms 0-53   (54 rooms)
Nar Shaddaa:            rooms 54-83  (30 rooms)
Kessel:                 rooms 84-95  (12 rooms)
Corellia:               rooms 96-119 (24 rooms)
Total:                  120 rooms (all with hand-tuned map_x/map_y coordinates)
```

### 4.2 Zones with Security Tiers

| Zone | Planet | Security | Notes |
|------|--------|----------|-------|
| Mos Eisley core | Tatooine | Secured | Spaceport, streets, markets, government |
| Spaceport District | Tatooine | Contested | Docking bays, cantina area |
| Chalmun's Cantina | Tatooine | Contested | Interior cantina rooms |
| Jabba's Townhouse | Tatooine | Contested | Hutt territory |
| Outskirts | Tatooine | Contested | Scavenger market, speeder track, checkpoint |
| Jundland Wastes | Tatooine | Lawless | Tusken Raiders, Krayt Graveyard, hidden cave |
| Nar Shaddaa Docks | Nar Shaddaa | Contested | Landing platforms, trade area |
| Corellian Sector | Nar Shaddaa | Contested | Mixed commercial |
| Nar Shaddaa Undercity | Nar Shaddaa | Lawless | Criminal underworld |
| Nar Shaddaa Upper Levels | Nar Shaddaa | Contested | Promenade area |
| Warrens | Nar Shaddaa | Lawless | Deep undercity — Evocii, reactor levels |
| Kessel Surface | Kessel | Contested | Station area |
| Kessel Imperial Garrison | Kessel | Secured | Military base |
| Kessel Spice Mines | Kessel | Lawless | Mines and prison area |
| Deep Mines | Kessel | Lawless | Energy spiders, rare resources |
| Coronet Starport | Corellia | Secured | CEC shipyards |
| Coronet City | Corellia | Contested | Mixed commercial/residential |
| Coronet Government | Corellia | Secured | CorSec, official buildings |
| Old Quarter | Corellia | Contested | Market, tavern, residential |
| Blue Sector | Corellia | Contested | Mechanics' Guild, shipwright forge |

### 4.3 NPCs

**PLANET_NPCS:** ~39 entries in `build_mos_eisley.py` covering all 4 planets. Includes trainers (Old Prospector: survival/search; Renna Dox: shipwright; Venn Kator: shipwright), hostile NPCs (Tusken Raiders, Energy Spiders, Gamorrean enforcers), merchants, quest givers, and flavor characters. **FDTS NPCs:** Mak, Lira, Grek added for the quest chain.

**GG7 NPCs:** Templates in `data/npcs_gg7.yaml` (loaded separately).

---

## 5. Combat System

Full WEG D6 R&E combat implementation: initiative, declaration, resolution with opposed rolls, wound levels (stunned → wounded → incapacitated → mortally wounded → killed), dodge/parry, cover, aiming, fleeing. Death triggers respawn with equipment recovery.

### 5.1 Ground Combat [v22]
`engine/combat.py` + `parser/combat_commands.py` (~2,000 lines). 19+ commands. NPC AI with 5 combat profiles. Paced broadcast with `asyncio.sleep()` between combatant blocks. Two-line ANSI format with wound color escalation. Margin-based flavor text via `combat_flavor.py`. Consolidated initiative display. Per-session "YOU got hit" emphasis. Territory influence hooks on combat kills. Armor pipeline (wear/remove/soak), stun damage routing, defender CP-on-soak (`+soak` command), per-stun expiry timers, melee vs undeclared defender uses weapon difficulty.

### 5.2 Space Combat
`parser/space_commands.py` (5,415 lines). 49 commands. 7 crew stations (Pilot, Gunner, Copilot, Engineer, Navigator, Commander, Sensors). Capital-scale weapons with structure points. Ion weapons with decay tick. Tractor beams with reel tick. Lock-on mechanic with bonus damage. Evasive maneuvers (Jink/BarrelRoll/Loop/Slip). Imperial boarding with WEG40141 customs infraction fines.

### 5.3 Security Zones Integration [v21]
`engine/security.py` (246 lines) gates combat based on zone security level:
- **Secured:** No combat allowed (blocks AttackCommand, suppresses NPC aggro)
- **Contested:** NPC combat allowed; PvP requires challenge/accept consent
- **Lawless:** All combat unrestricted

`get_effective_security(room_id, db, character=None)` — accepts optional character parameter for territory-contextual security. When a character's org has claimed a lawless room, it returns CONTESTED for org members (PvP consent protection in own territory).

Space security: DOCK blocks fire; ORBIT/HYPERSPACE requires PvP consent; DEEP_SPACE unrestricted. Player-ship detection via pilot `account_id`.

BH guild PvP consent override: Bounty hunters with active claimed contracts bypass CONTESTED consent requirements in ground combat.

### 5.4 Combat Web Panel [v20]
`to_hud_dict()` serializes combat state per-viewer. Web sidebar panel with wound pips, initiative order, declared actions, cover/aim/fleeing status, ★ marker for viewer's own row, phase labels, round badge. `_send_combat_state` sends personalized payloads to each WebSocket session.

---

## 6. Space Systems

### 6.1 Space Expansion v2 — All 19 Drops Complete [v16–v19]

Full design in `space_expansion_v2_design.md` + `space_expansion_v2_addendum.md`.

| Drop | Summary |
|------|---------|
| 1 | Bug fixes — ion decay, tractor reel, evasive registration, crafting API rewrite |
| 2 | Galaxy expansion — 3 planets (Nar Shaddaa, Kessel, Corellia), 16 zones, 3 hyperspace lanes |
| 3 | Hyperspace transit — travel time formula, transit state, dest-to-zone mapping, tick hooks |
| 4 | Sublight navigation — `course` command, zone transit, piloting checks |
| 5 | Asteroid fields — zone hazards, entry checks, 30-tick collision tick |
| 6 | Anomaly scanning — `engine/space_anomalies.py`, `deepscan`, 7 anomaly types, spawn tick |
| 7 | Salvage system — `salvage` command, loot tables, combat debris, wreck hook |
| 8 | Space HUD server — `build_space_state()`, `broadcast_space_state()`, send points |
| 9 | Space HUD client — space panel, station-aware quick buttons, crew/status display |
| 10 | Zone map SVG + tactical radar SVG + anomaly pings (web only) |
| 11 | Multi-planet smuggling routes, patrol-on-arrival, destination enforcement |
| 12 | Ship customization — `get_effective_stats()`, mod slots, +ship/install/uninstall/mods |
| 13 | Ship component schematics (7 types), Shipwright NPCs (Venn Kator + Renna Dox) |
| 14 | Space missions — PATROL/ESCORT/INTERCEPT/SURVEY_ZONE, intercept kill tracking |
| 15 | Power allocation — reactor budgets, `power` command, overcharge, silent running |
| 16 | Captain's Orders — 8 tactical orders, Command skill check, ship-wide modifiers |
| 17 | Planetary trade goods — `market`/`buy cargo`/`sell cargo`, 8 goods, planet price tables |
| 18 | Transponder codes — false ID, sensor mask/comm jammer, imperial customs checks |
| 19 | Ship quirks (18 quirks, 5 categories) + ship's log (17 milestones, 6 titles, CP rewards) |

### 6.2 Space Bugfixes [v21]
- Transit never arrives: `get_all_ships()` → `get_ships_in_space()` (6 call sites)
- Radar empty after scan: `broadcast_space_state()` added at end of `ScanCommand.execute()`
- NPC targeting: `_pick_target()` skips non-hostile NPCs
- Duplicate ships in space list: dedup by ship ID in `get_ships_in_space()`
- Pirate spam: shared cooldown per zone
- Boarding loop: `already_boarded` set check
- ETA display: shows "ETA: Xs" during sublight transit
- Life support: `LIFE_SUPPORT` power draw wired
- Weapon pips: fixed ion cannon pip values
- Scan zone-filter: corrected in `ScanCommand`

### 6.3 Space Zones (16 total)

Tatooine Orbit, Tatooine Deep Space, Nar Shaddaa Orbit, Nar Shaddaa Deep Space, Kessel Orbit, Kessel Deep Space, The Maw, Corellia Orbit, Corellia Deep Space, Corellian Asteroid Belt, Hyperspace Lane: Tatooine↔Nar Shaddaa, Hyperspace Lane: Nar Shaddaa↔Kessel, Hyperspace Lane: Nar Shaddaa↔Corellia, Hyperspace Lane: Corellia↔Tatooine, Tatooine Outer Rim, Corellia Trade Lane.

---

### 6.4 Space Overhaul v3 — All 11 Drops [v29 — NEW, COMPLETE]

Design doc: `space_overhaul_v3_design.md` (2,012 lines). Core principle: **space is not a minigame** — each archetype (smuggler/trader/bounty hunter/faction pilot/explorer) has a primary activity loop. Encounters are seasoning, not the main course.

**Drop 0 — Space Security Zones:** 16 zones assigned per-planet security profiles (Corellia=SECURED, Tatooine=standard, Nar Shaddaa=CONTESTED, Kessel=LAWLESS). `get_space_security(zone_id)` with Director override. Zone-aware NPC spawn rates and anomaly quality.

**Drop 1 — SpaceEncounter Framework:** `SpaceEncounter` + `EncounterChoice` dataclasses. `EncounterManager` singleton with handler registry, cooldown tracking, choice presentation (WebSocket JSON + Telnet text menus), deadline tick. Commands: `respond`, `stationact`, `encounter`, `investigate`.

**Drop 2 — Imperial Patrol Redesign:** 4-choice branching (Comply/Bluff/Run/Hide). Inspection with Con check for contraband. WEG40141 infraction fines. Security-scaled difficulty.

**Drop 3 — NPC Space Combat AI:** `engine/npc_space_combat_ai.py` — 5 combat profiles (aggressive, cautious, pursuit, ambush, patrol). TrafficShip → SpaceGrid promotion. Action pacing (3-5s intervals). Flee/destruction/disable outcomes. Wreck anomaly on NPC destruction.

**Drop 4 — Pirate Encounter:** 4-choice (Pay/Negotiate/Fight/Flee). Bargain skill check negotiation. Fight path uses NPC combat AI.

**Drop 5 — Contact Encounter:** Mysterious ship contact with multiple scenarios (help/hail imperials/board/destroy/ignore).

**Drop 6 — Mechanical/Cargo Encounters:** System malfunction with Technical repair check. Cargo bay emergency with investigate/vent/ignore.

**Drop 7 — Bounty Hunter Encounter:** False transponder stealth check. 4-choice (Surrender/Fight/Flee/Negotiate). Pursuit profile AI.

**Drop 8 — Anomaly Encounters:** 6 types (distress signal, hidden cache, pirate nest, mineral vein, Imperial dead drop, mynock colony). `investigate <anomaly_id>` triggers encounters.

**Drop 9 — Web Client Encounter UI:** Fixed-bottom choice panel with risk-colored borders. Countdown timer bar. Click-to-respond buttons.

**Drop 10 — Crew Station Badges:** Station hint badges (PILOT, ENGINEER, etc.) on choice buttons.

**Drop 11 — Tuning/Polish:** Help text auto-registered. Balance integration.

**Texture Encounter Auto-Trigger (Session 38):** `texture_encounter_tick()` runs every 10 ticks during sublight/hyperspace transit. ~0.8% chance per invocation, scaled by zone security (lawless 1.6×, secured 0.3×). Picks from mechanical/cargo/contact weighted 40/30/30.

**NPC Combat Hyperspace Cleanup (Session 38):** When player enters hyperspace mid-combat, NPC combatant is removed from SpaceGrid, traffic ship reset, encounter resolved with `player_fled_hyperspace` outcome.

### 6.5 Faction Mission Board [v29 — NEW]

Faction-specific missions with rep gating. `FACTION_MISSION_CONFIG` in `engine/missions.py` defines empire/rebel/hutt/bh_guild missions with custom givers, objectives by type, reward multipliers (1.4-1.6×), and rep thresholds. `generate_faction_mission()` creates missions tagged with `faction_code` and `faction_rep_required`. `available_missions_for_char()` filters by character's faction rep. Board display shows `[EMPIRE]`/`[REBEL]`/etc. badges.

## 7. Organizations & Factions [v20 — DELIVERED]

Design doc: `organizations_factions_design_v1.md`. All 6 drops delivered. Unchanged from v20.

---

## 7A. Faction Reputation System [v28 — NEW, ALL 6 DROPS DELIVERED]

Design doc: `faction_reputation_design_v1.md`. `engine/organizations.py` (1,560 lines — expanded from 939 in v27).

### Architecture

Per-character faction reputation tracking with gameplay consequences, auto-promotion, and Director AI integration. Reputation is stored as integer values in the `org_memberships` table (for members) and `attributes.faction_rep` JSON (for non-members).

### Rep Tiers

| Tier | Range | Shop Effect |
|------|-------|-------------|
| Exalted | 90–100 | -20% discount |
| Revered | 75–89 | -15% discount |
| Honored | 50–74 | -10% discount |
| Trusted | 25–49 | -5% discount |
| Neutral | -24–24 | No effect |
| Unfriendly | -49–-25 | +50% markup |
| Hostile | -74–-50 | Access denied |
| Hated | -89–-75 | Access denied |
| Enemy | -100–-90 | Access denied |

### Core Functions (engine/organizations.py)

- `adjust_rep(db, char_id, faction_code, delta, reason, session=None)` — Single entry point for all rep changes. Fires `rep_change` web event and checks auto-promotion
- `get_char_faction_rep(db, char_id, faction_code)` — Unified lookup (member DB or attributes JSON)
- `get_all_faction_reps(db, char_id)` — All-factions overview dict for HUD/web panel
- `get_faction_shop_modifier(db, char_id, faction_code)` — Returns `(allowed, modifier, tier_name)` for shop pricing
- `get_faction_standing_context(db, char_id, faction_code)` — Builds NPC dialogue context string by rep tier
- `check_auto_promote(db, char_id, session)` — Fires rank-up when rep crosses thresholds (members only)

### Drops Delivered

| Drop | Contents |
|------|----------|
| 1 | Fixed 3 broken callers (`ctx.db.adjust_rep()` didn't exist), refactored to `engine/organizations.adjust_rep()` |
| 2 | Auto-promotion on rep threshold, `+reputation` overview command, `+reputation <faction>` detailed view |
| 3 | Profession chain rep rewards wired (were silently failing as no-ops) |
| 4 | Gameplay consequences — shop discounts/markup/blocks by tier, NPC dialogue tone injection via `get_faction_standing_context()` |
| 5 | Web client reputation panel — sidebar bars, rep-change slide-in notification, rank-up toast |
| 6 | Director AI integration — `player_faction_standings` in digest, faction-aware event targeting |

### Invariants

- All rep changes go through `engine/organizations.adjust_rep()` — no direct DB writes
- Rep history capped at 10 entries per faction (FIFO) in `attributes.rep_history`
- Auto-promotion only fires for members, never for non-member attribute-based rep
- Cross-faction rep only applies to Empire ↔ Rebel axis (Hutts and BH Guild neutral)
- Non-member rep clamps at -100..+100, member rep at 0..100

---

## 8. PC Narrative Memory [v20 — DELIVERED]

Design doc: `pc_narrative_memory_design_v1.md`. All 6 drops delivered. Unchanged from v20.

**[v24 Enhancement Designed]:** `think` command (Feature #1) — logs internal monologue to `pc_action_log` with `event_type = 'thought'`. Nightly Haiku summarization pipeline includes thought entries, enabling NPCs to reference character demeanor without explicit OOC disclosure. World Lore keyword injection (Design C) adds lore context to NPC dialogue prompts alongside existing `pc_short_record` injection.

---

## 9. Combat UX Overhaul [v20 — DELIVERED]

Design doc: `combat_ux_overhaul_design.md`. All 7 drops delivered. Unchanged from v20.

---

## 10. Player Shops [v20 — DELIVERED]

Design doc: `player_shops_design_v1.md`. **All 5 drops delivered.**

Features: Core vendor droid lifecycle, `browse`, stock/unstock with item transfer, `buy_from_droid` with item delivery, NPC droid dealers (3 tiers), `shop upgrade`, Bargain checks, buy orders (Tier 3), auto-recall tick (60-day idle), `+shop` dashboard, `@economy` admin stub. Anti-exploit: same-account purchase block, price floor at 50% NPC buy-back, listing fee as credit sink, faction-issued item block.

---

## 11. Security Zones & Territory Control [v25 — ALL DROPS DELIVERED]

Design docs: `security_zones_design_v1.md` + `security_drop6_territory_control_design_v1.md`.

### Delivered (Drops 1–5 + 6A–6E — ALL COMPLETE):
- Drops 1–3: Security engine, combat gates, PvP consent, look tags, lawless warnings, space gates
- Drop 4: Director AI dynamic security overlays (criminal surge/Imperial crackdown)
- Drop 5: Bounty hunter PvP consent override in ground combat
- Drop 6A: Territory influence — earning hooks in combat/mission/smuggling/bounty handlers, `faction invest` (treasury → influence), `faction influence` display, influence decay tick, `look` presence line at 25+ threshold
- Drop 6B: Room claiming — `territory_claims` table, `faction claim/unclaim/territory` commands, claim validation (influence threshold, treasury, rank 3+), weekly maintenance tick, `look` claimed room tag, security upgrade for claimed lawless rooms (→ contested for org members), `get_effective_security()` character parameter
- Drop 6C: Guard NPC spawning — `spawn_guard_npc()` / `remove_guard_npc()` in `engine/territory.py`, `faction guard station|remove` subcommands, guard upkeep wired into maintenance tick; Faction Armory — `org_storage` in room properties JSON, `faction armory deposit|withdraw` commands; Resource nodes — `tick_resource_nodes` daily tick, quality scales with influence tier and zone security
- Drop 6D: Contesting & PvP — `territory_contests` table, `check_and_declare_contests()`, 7-day contest timer, `tick_contest_resolution` hourly tick, `_transfer_zone_claims()` on victory, `hostile_takeover_claim()` for lawless zones, `faction seize` command
- Drop 6E: Web client territory badge — `claim-badge` span with guard symbol + contested-glow CSS, contest alert injected into news feed, `session.py` sends `territory_claim`/`contest_active`/`contest_challenger`/`contest_ends`

### 11A. Territory Control System [v25 — FULLY DELIVERED]

`engine/territory.py` (1,937 lines). Influence-based territory claiming for player organizations in contested and lawless zones.

**Core mechanic:** Organizations earn influence points in zones through member presence, combat, missions, and treasury investment. When influence crosses a threshold, they can claim specific rooms. Claimed rooms get security upgrades, guard NPCs, daily resource generation, and can be contested by rivals.

**Key architecture:**
- Territory influence uses a separate `territory_influence` table (integer zone IDs, org codes) — NOT the Director's `zone_influence` table (string environment keys, faction axes). Different systems, different purposes.
- `adjust_territory_influence()` is the single entry point for all influence changes (same pattern as `perform_skill_check()`)
- Claims are room-level, not zone-level. Max 3 per zone, 10 total per org.
- Guard NPCs: `spawn_guard_npc()` / `remove_guard_npc()`. Guard upkeep (100cr/wk) added to maintenance tick. Org-tagged `guard_for_org` in NPC `ai_config`.
- Faction Armory: `org_storage` dict stored in room `properties` JSON. Items and crafting resources stored/withdrawn via `armory_deposit_item()`, `armory_withdraw_item()`, `armory_withdraw_resources()`.
- Resource nodes: `tick_resource_nodes()` daily tick awards crafting resources and credit bonuses based on influence tier and zone security. Resources deposited directly into org armory.
- Contests: `territory_contests` table, 7-day timer. `check_and_declare_contests()` fires after every influence change. `tick_contest_resolution()` checks hourly for expired contests, transfers claims via `_transfer_zone_claims()`.
- Hostile takeover: `hostile_takeover_claim()` — lawless zone only, after killing the room's guard NPC. `faction seize` command.
- `get_territory_digest()` compiles data for Director narrative. `ORG_TO_AXIS` mapping bridges to faction axis system.

---

## 12. Player Housing [v26 — ALL 9 DROPS DELIVERED]

Design doc: `player_housing_design_v1.md`. `engine/housing.py` (3,194 lines), `parser/housing_commands.py` (872 lines).

### Delivered:
- **Drop 1:** Tier 1 rented rooms — rent/checkout/storage/sethome/home, rent tick (weekly at game_server offset 432,000), `player_housing` + `housing_lots` tables, `rooms.housing_id` column
- **Drop 2:** Description editor (multi-turn input via `session._input_intercept`), trophies, room naming, `look` integration
- **Drop 3:** Tier 2 faction quarters — auto-assigned by faction rank, Empire/Rebel/Hutt/BH Guild variants with thematic descriptions, `FACTION_QUARTER_TIERS` table with rank-based upgrades
- **Drop 4:** Tier 3 private residences — real estate NPC, `HOUSING_LOTS_TIER3` lot system, `TIER3_TYPES` (studio/standard/deluxe), multi-room with guest lists, purchase/sell lifecycle
- **Drop 5:** Tier 4 Shopfronts — `HOUSING_LOTS_TIER4`, `purchase_shopfront()` / `sell_shopfront()` (50% refund), `housing shopfront <type> <lot_id>` command, +1 personal droid cap for shopfront owners, `get_shopfront_directory()` for `market search` integration. `MarketSearchCommand` in `parser/shop_commands.py` — planet-wide shopfront directory, filterable by planet.
- **Drop 6:** Tier 5 Organization HQs — `TIER5_TYPES` (outpost/chapter_house/fortress), `purchase_hq()` / `sell_hq()`, faction-themed room descriptions (Empire/Rebel/Hutt), 6 lot locations across 4 planets, per-faction guard slots, treasury-funded weekly maintenance with degradation cascade (1wk guards offline → 2wk doors unlock → 4wk auto-abandon), `faction hq` command tree, `can_enter_hq_room()` org membership gate
- **Drop 7:** Security & intrusion — `housing_intrusions` table via `ensure_intrusion_schema()`, `LockpickCommand` (Security skill vs. lock difficulty), `ForceDoorCommand` (Strength check, damages door), `StealCommand` (Pickpocket vs. Perception, trophy items only), all intrusion attempts logged, `housing intrusions` view command
- **Drop 8:** Web client housing panel — `housing_info` dict in HUD payload (tier, rent status, storage bar, trophy count, guest count, guard slots), context panel section with owner/visitor detection, quick action buttons, performance-gated on `rooms.housing_id` column (no LIKE scan on non-housing rooms)
- **Drop 9:** AI description suggestions — `.suggest` / `.suggest <style>` / `.accept` commands in description editor, Haiku API with zone tone + planet + tier context, `housing visit <player>` shopfront lookup command

---

## 13. Tutorial System [v21 — FULLY DELIVERED]

Design docs: `tutorial_system_design.md` + `tutorial_factions_addendum_v2.md`. **All 12 drops delivered.**

Core 6-room tutorial, 8 elective modules, starter quest chain (10 steps including step 5.5 "The Powers That Be"), planet discovery tracking, tutorial titles. `engine/tutorial_v2.py` (2,100+ lines).

**6 profession chains** [v21 — all delivered]:

| Chain | Contact | Entry Gate | Reward |
|-------|---------|-----------|--------|
| Smuggler's Run | Kessa (Cantina) | smuggling_runs ≥ 1 | ~6,800cr + "Veteran Smuggler" |
| Hunter's Mark | Ssk'rath (Bounty Office) | bounties_collected ≥ 3 | ~3,100cr + "Guild Hunter" |
| Artisan's Forge | Vek Nurren (Workshop) | crafting_complete ≥ 3 | ~3,500cr + "Master Artisan" |
| Rebel Cell | Fulcrum comlink | missions_complete ≥ 2 | ~4,000cr + "Rebel Sympathizer" |
| Imperial Service | Sergeant Kreel (Police) | missions_complete ≥ 2 | ~5,300cr + "Imperial Associate" |
| Underworld | Gep (Grill) | smuggling_runs ≥ 3 | ~7,300cr + "Made Man" |

`check_profession_chains(session, db, trigger, **kwargs)` is the central dispatcher.

---

## 13A. From Dust to Stars Quest Chain [v23 — NEW]

Design doc: `from_dust_to_stars_design_v1.md`. `engine/spacer_quest.py` (1,528 lines), `engine/debt.py` (159 lines), `parser/spacer_quest_commands.py` (370 lines).

**30-step, 5-phase quest chain** spanning 12–20 hours of gameplay across all 4 planets. Takes a new player from completing the starter quest to owning a beat-up Ghtroc 720 with a 10,000cr Hutt debt. Covers every major game system: factions, trade goods, sabacc, CP progression, +background, housing awareness, crafting, NPC crew, ship ownership.

**Architecture:**
- Quest state stored in character `attributes` JSON under `"spacer_quest"` key
- `check_spacer_quest()` hook function wired into 15+ command handlers (same pattern as `check_profession_chains`)
- `engine/debt.py` handles weekly Hutt debt auto-deduction with missed payment warnings and enforcer threat escalation
- `travel <planet>` command provides passenger travel for pre-ship phases
- Phase 1 tested and verified (Steps 1–7, Tatooine)

**Player commands:** `+quest` (status), `+quest log` (history), `+quest abandon`, `debt` (status), `debt pay <amount>`, `debt payoff`, `travel <planet>`.

---

## 13B. Director AI Enhancements [v28 — TONE + ERA DELIVERED, LORE DESIGNED]

Design doc: `competitive_analysis_feature_mining_v1.md` §7 + `competitive_analysis_feature_designs_v1.md` §C & §D.

**Narrative Tone Per Zone (Design D) ✅ DELIVERED:** `engine/zone_tones.py` (137 lines) loads `data/zones.yaml` (14 zones across 4 planets + space). `get_zone_tone_by_name()` prefix-matches zone names. `get_zone_tone(db, room_id)` resolves room → zone → tone with zone_id cache. Wired into `engine/director.py` (faction turn digest) and `ai/npc_brain.py` (ATMOSPHERE injection in system prompt). Module-level cache; lazy-loaded on first access.

**Era-Progression Thresholds (Feature #15) ✅ DELIVERED [v28]:** `engine/director.py` (1,787 lines, up from ~1,327 in v20). 7 era milestones tracking average faction influence across all 6 Director zones:

| Era Key | Faction | Threshold | Event |
|---------|---------|-----------|-------|
| `imperial_grip` | imperial | avg ≥ 70 | 2hr crackdown event |
| `imperial_martial_law` | imperial | avg ≥ 85 | 4hr crackdown event |
| `underworld_rising` | criminal | avg ≥ 70 | Narrative only |
| `hutt_takeover` | criminal | avg ≥ 85 | Narrative only |
| `rebel_whispers` | rebel | avg ≥ 35 | Narrative only |
| `rebel_uprising` | rebel | avg ≥ 50 | Narrative only |
| `imperial_retreat` | imperial | avg < 30 | Narrative only |

- One-time events stored in `director_log` as `event_type='era_milestone'`
- Previously fired eras loaded from DB on startup (`ensure_loaded`)
- Era banner broadcast to all online players (Telnet ANSI + web `news_event`)
- World events fired for `imperial_crackdown` type milestones
- Checked after every Faction Turn

**Director faction standings [v28]:** `compile_digest()` now includes `player_faction_standings` with compact tier summaries for all online players. System prompt updated with `FACTION STANDINGS` section instructing Director to target events by player rep.

**World Lore (Design C) — DESIGNED, UNBUILT:** NovelAI Lorebook-style keyword injection for NPC dialogue prompts.

---

## 14. Economy System — Audit & Assessment [v21/v23]

Design docs: `economy_design_v02-1.md`, `economy_audit_v1.md`, `economy_hardening_design_v1.md`.

### 14.1 Credit Flow — Current State

**Faucets (LIVE):** Missions (14 types), bounties (5 tiers), smuggling jobs (5 route tiers), NPC weapon sell-back (25–50%), trade goods arbitrage (8 goods × 4 planets), entertainer performance, medical healing (P2P), faction stipends (from treasury). Sabacc is zero-sum (10% house rake = net sink).

**Sinks (LIVE):** Ship fuel (50–600 cr/event), docking fees (25–38 cr/land), weapon repair (50–250 cr), NPC weapon purchases (275–5,000 cr), vendor droid purchase (2,000–12,000 cr), vendor droid listing fee (1–2%/sale), crew wages (30–1,000 cr/4hrs per NPC), housing deposit/rent (500 cr + 50 cr/week at Tier 1), smuggling fines (50% of job reward), sabacc house rake (10% of wins), transaction tax on `pay` (5%).

### 14.2 Economy Hardening Status [v25 — ALL 8 ITEMS DELIVERED]

All economy hardening items confirmed in live codebase (Session 19 audit):

| Item | Status | Location |
|------|--------|----------|
| Mission completion skill checks | ✅ DELIVERED | `resolve_mission_completion()` in `engine/skill_checks.py` |
| Trade goods supply limits + Bargain gate | ✅ DELIVERED | `SupplyPool` class in `engine/trading.py` |
| Transaction tax on `pay` (5%) | ✅ DELIVERED | `TradeCommand._accept()` in `parser/builtin_commands.py` |
| Recurring daily docking fees (25 cr/ship) | ✅ DELIVERED | `docking_fee_tick` in `tick_handlers_economy.py` |
| Credit transaction log + `@economy velocity` | ✅ DELIVERED | Schema v12 `credit_log` table, `log_credit()` / `get_credit_velocity()` in `database.py`, `@economy velocity` in `director_commands.py` |
| NPC resource vendors (price floor) | ✅ DELIVERED | `buyresources` command in `crafting_commands.py` |
| CP progression rebalance (200/400/10) | ✅ DELIVERED | Constants in `cp_engine.py` |
| Kudos same-room requirement removed | ✅ DELIVERED | `cp_commands.py` |

### 14.3 What's Working Well (Don't Touch)

Weapon durability/repair cycle. Vendor droid listing fees. Crew wages. Smuggling risk/reward. Dark side economics. Sabacc as a sink (10% rake).

### 14.4 Economy Enhancements from Competitive Analysis [v24 — DESIGNED]

Design doc: `competitive_analysis_feature_designs_v1.md` §I, §H, §E, §12.

- **Safe trade command** (Feature #6, Design I): ✅ DELIVERED [v27]. Two-step consent item exchange. See §16C.
- **Survival crafting lane** (Feature #18): Environment-specific schematics (Tatooine cooling units, Kessel breath masks, NS anti-mugging alarms) that NPCs don't sell. Demand created by environmental hazard system. Adds `data/schematics.yaml` entries + `engine/crafting.py` schematic type.
- **Crafting experimentation parameters** (Feature #12, Design in feature_designs §12): ✅ DELIVERED [v27]. Engineer-tunable parameters per schematic category.
- **Buff/debuff handler** (Feature #13, Design H): ✅ DELIVERED [v26]. `engine/buffs.py` — timed stat modifiers with stacking rules and tick drain.

---

## 15. Capital Ship Rules [DELIVERED — Pre-existing]

Design doc: `capital_ship_rules_design.md`. All 5 drops implemented. Unchanged from v20.

---

## 16. Ground UX Overhaul [v25 — ALL 10 DROPS DELIVERED]

Design doc: `ground_ux_overhaul_design_v1.md`. All 10 drops complete.

### Delivered:

**Drop 1: Room Detail Card + NPC Roles + Loadout (Session 13)**
- Server: `_classify_npc_role()` determines display role from AI config (hostile/guard/trainer/vendor/mechanic/bartender/neutral), `_npc_actions()` returns context-sensitive action list, `_derive_room_services()` derives service tags, `_build_loadout()` extracts equipment data
- Client: Room card with name/zone/security badges/description (3-line truncation + expand), NPC role icons with colored names, action buttons (red attack, green train, amber buy), loadout sidebar (weapon/armor/consumables)

**Drops 2+3: Area Map (Session 13)**
- `engine/area_map.py` (362 lines) — BFS from current room, collects node-link graph (max 25 rooms), direction-aware auto-layout with normalized 0–1 coordinates
- Client minimap in HUD sidebar, click-to-navigate on adjacent rooms

**Drop 4 (partial): Area Map v2 — Environment Theming + Fullscreen (Session 15)**
- 20+ environment-type color fills (cantina amber, industrial blue, desert sandy gold, underground purple, etc.)
- Security-colored borders and dot indicators (green/amber/red)
- Service icons (🍺🚀🛒🎓⚕🔧) from NPC presence detection
- Fullscreen modal with zoom/pan (0.5×–5× viewBox), auto-generated legend, click-to-navigate, auto-update on movement, responsive

**Drop 5: Hand-Tuned Map Coordinates (Session 16)**
- Schema v11 added `map_x`/`map_y` REAL columns to rooms table
- `build_mos_eisley.py` populates 120 hand-tuned coordinates across all 4 planets
- `build_area_map()` uses stored coords when available, falls back to auto-layout

**Drop 6: Active Jobs Tracker (Session 16)**
- Server: `send_hud_update()` scans 4 sources (active mission, active bounty, active smuggling job, active spacer quest step) and includes structured data
- Client: `#g-active-jobs` sidebar section shows current objectives with type icons

**Drop 7: Smart Quick Buttons (Session 16)**
- `_buildExploreButtons()` augments static explore button list with context-sensitive actions (e.g., "heal" when wounded near a medic, "train" near a trainer)
- `updateQuickButtons()` calls the builder for explore mode

**Drop 8: Nearby Services Panel (Session 19)**
- `engine/area_map.py`: `find_nearby_services(room_id, db, depth=4, max_results=8)` — BFS outward 4 hops, detects services via environment type + room name keywords + NPC roles. Tracks first-hop direction. Shared `_detect_room_services()` helper.
- Client: Nearby Services panel below current room services, each entry shows icon + truncated room name + hop count + direction. Click sends movement command.

**Drop 9: Credits Ticker + CP Progress + Zone Influence (Session 19)**
- `session.py`: `credit_event` fired when credits change (carries `delta`), `cp_progress` dict (`ticks_to_next`, `pct`, weekly cap status), `zone_influence` dict (`org_code: pct_share`).
- Client: animated `+N`/`-N` credit delta (`creditPop` keyframe), 3px cyan CP progress bar under Char Pts, mini bar chart for zone influence with faction colors.

**Drop 10: Director Story Feed (Session 19)**
- `engine/director.py`: `news_event` broadcast includes `zone` field.
- `session.py`: `zone_intel` — last 5 `director_log` entries `[{text, timestamp, event_type}]`.
- Client: Zone Intel panel with fade-in animation, staggered delay, relative timestamps. Live injection prepends incoming `news_event`. Most recent item highlighted.

---

## 16A. Scene Logging System [v25 — NEW, DELIVERED]

Design reference: `hspace_ares_integration_design_v1.md` §3.2. `engine/scenes.py` (474 lines), `parser/scene_commands.py` (439 lines). Inspired by AresMUSH scene management.

**Lifecycle:** `+scene/start` → status `active`, room bound → posing/saying auto-captured → `+scene/stop` → status `completed`, CP bonus fired → `+scene/share` → status `shared`, visible in future web portal archive.

**Schema (v13 migration):** `scenes` (id, title, summary, scene_type, location, room_id, creator_id, status, started_at, completed_at, shared_at), `scene_poses` (scene_id, char_id, pose_type, content, created_at), `scene_participants` (scene_id, char_id). Indexes on scene_poses by scene+time, scenes by status+started_at and room+status.

**Pose capture hooks:** `capture_pose()` called from `SayCommand`, `EmoteCommand`, `OocCommand` in `parser/builtin_commands.py` when an active scene exists in the room. Pose type auto-detected (`say`, `emote`, `ooc`).

**CP integration:** `stop_scene()` calls `cp_engine.award_scene_bonus()` per participant, scaled by pose count. Encourages RP over grinding.

**In-memory cache:** `_active_scenes: dict[int, int]` (room_id → scene_id) warmed on server startup via `warm_cache()`. Kept in sync on start/stop — zero DB hits on the hot path of every pose.

**Commands:**
| Command | Action |
|---------|--------|
| `+scene/start [title]` | Start a scene in current room |
| `+scene/stop` | End active scene, fire CP bonuses |
| `+scene/title <text>` | Rename active scene |
| `+scene/type <type>` | Set type: Social / Action / Plot / Vignette |
| `+scene/summary <text>` | Add archive summary |
| `+scene/share [id]` | Make completed scene public |
| `+scene/unshare [id]` | Revert to private |
| `+scenes` | List your recent scenes |
| `+scene [id]` | View scene info / pose log |

**Remaining (Phase 2):** Web portal scene archive — `/scenes` page listing shared scenes with full pose log viewer. Requires web portal foundation (Priority D Phase 2).

---

## 16B. Achievement System [v27 — NEW, DELIVERED]

### Architecture

YAML-driven achievement tracking with persistent SQLite storage. 30 achievements across 7 categories, CP milestone rewards, and hooks wired into 14 existing game systems. Achievement data loaded from `data/achievements.yaml` on server boot.

**Files:** `engine/achievements.py` (430 lines), `parser/achievement_commands.py` (180 lines), `data/achievements.yaml` (220 lines).

### Schema

`character_achievements` table (schema v14):
- `character_id`, `achievement_key`, `progress` (int), `completed` (bool), `completed_at` (timestamp)
- Indexes on `character_id` and `(character_id, achievement_key)` unique

### Categories (30 achievements)

| Category | Count | Examples |
|----------|-------|---------|
| Combat | 5 | First blood, 10 victories, 100 attacks landed |
| Space | 5 | First launch, hyperspace jumps, anomaly salvage, ship destroyed |
| Economy | 4 | First mission, smuggling runs, credits earned |
| Crafting | 4 | First craft, masterwork, experiment successes |
| Social | 4 | First conversation, scene completions, kudos received |
| Exploration | 4 | Rooms visited milestones, planet discovery |
| Force | 4 | Force power usage, dark side points accumulated |

### Hook Architecture

19 events across 14 files. All hooks wrapped in `try: ... except Exception: pass` (graceful-drop — achievement failure never breaks gameplay). Hooks call typed wrappers in `engine/achievements.py` (e.g., `check_combat_victory(db, char_id, session)`, `check_hyperspace_complete(db, char_id, session)`).

| File | Events |
|------|--------|
| `parser/combat_commands.py` | `combat_victory`, `attack_hit` |
| `parser/space_commands.py` | `ship_launch`, `anomaly_salvaged`, `ship_destroyed` |
| `server/tick_handlers_ships.py` | `hyperspace_complete` |
| `parser/crafting_commands.py` | `item_crafted`, `craft_masterwork`, `experiment_success` |
| `parser/scene_commands.py` | `scene_completed` |
| `parser/smuggling_commands.py` | `smuggling_complete`, `mission_credits_earned` |
| `parser/mission_commands.py` | `mission_complete`, `mission_credits_earned` |
| `parser/sabacc_commands.py` | `sabacc_win` |
| `parser/force_commands.py` | `force_power_used`, `dark_side_point` |
| `parser/cp_commands.py` | `kudos_received` |
| `parser/builtin_commands.py` | `pc_conversation`, `rooms_visited` |

### CP Rewards

Achievement CP rewards bypass the weekly tick cap — they are milestone rewards, not grindable income. CP is awarded immediately on unlock via direct DB credit.

### Web Client Integration

`achievement_unlocked` JSON event triggers a floating toast notification (gold border, icon, name, description, CP reward). Auto-dismisses after 4.5s. `achievements_status` event reserved for future sidebar panel.

### Commands

| Command | Description |
|---------|-------------|
| `+achievements` | Show all achievements with progress bars |
| `+achievements <category>` | Filter by category (combat/space/economy/crafting/social/exploration/force) |

---

## 16C. Safe Item Trade [v27 — NEW, DELIVERED]

Extension of the existing `trade` command in `parser/builtin_commands.py` to support item trades alongside credit trades.

**Syntax:** `trade <player> item <item name>` — offer an inventory item for trade. Uses the same `offer/accept/decline/cancel` flow as credit trades. Fuzzy prefix matching against offerer's inventory. Accept verifies offerer still has item before transfer (prevents race conditions). Atomic transfer via `remove_from_inventory()` + `add_to_inventory()`. Room broadcast and narrative log for both parties. No tax on item trades (tax only applies to credit transfers). `trade list` shows both item and credit offers.

---

## 16D. Sleeping Character Vulnerability [v28 — NEW, DELIVERED]

Design source: Competitive Analysis Feature #16 (Sindome). `engine/sleeping.py` (298 lines).

**Mechanic:** When a player disconnects in a non-secured room that isn't their own housing or faction territory, their character is flagged as "sleeping." Other characters can pickpocket sleeping characters using `pickpocket <player>`.

**Architecture:**
- Sleeping flag stored in `attributes.sleeping` JSON (timestamp, room_id, credits_at_sleep)
- Flag set on disconnect in qualifying rooms; cleared on reconnect
- `"X falls asleep against the wall..."` broadcast to room on disconnect
- `"While you were asleep..."` theft report shown on reconnect with itemized log
- Theft log capped at 10 entries per sleeping session

**`pickpocket <player>` command** (in `parser/builtin_commands.py`):
- Pickpocket skill vs. Perception - 2D contested roll (sleeping target penalty)
- Steals a percentage of credits on success
- Room broadcast of theft attempt (success or failure)
- Narrative log entry for both parties

**Safety rules:**
- Sleeping flag only set in non-SECURED rooms that aren't own housing or faction territory
- No sleeping in tutorial zones
- Players receive full report of what happened while asleep

---

## 16E. Comlink Intercept System [v28 — NEW, DELIVERED]

Design source: Competitive Analysis Feature #19 (Sindome SIC). Implemented in `parser/espionage_commands.py` (648 lines total, up from ~350 in v26) and `engine/espionage.py` (500 lines).

**Mechanic:** Players with the Espionage skill chain can intercept comlink and faction comms transmissions for a limited time.

**Commands:**
| Command | Description |
|---------|-------------|
| `intercept` | Start intercepting comlink/fcomm communications (5min, Perception check) |
| `intercept stop` | End active intercept, report count |
| `intercept status` | Check remaining time and intercept count |

**Architecture:**
- In-memory only (lost on restart — intentional, matches eavesdrop pattern)
- Intercept only delivers to players who did NOT already receive the original message
- Muffling uses 20% word survival (heavier than eavesdrop's 30%)
- 5-minute duration with Perception skill check gate
- Intercepted messages shown with `[INTERCEPTED]` prefix and source attribution

---

## 17. MU\* Compatibility Layer [v23 — NEW, ALL 4 PHASES DELIVERED]

Design doc: `tinymux_comparison_design_v1.md`. Analysis doc: `hspace_ares_integration_design_v1.md`. 4 new parser modules, ~2,325 lines of new code.

### 17.1 Design Philosophy

After a thorough TinyMUX codebase review (132K lines C++, 510 functions, 524 commands), the analysis concluded: SW_MUSH surpasses TinyMUX in gameplay systems (D6 mechanics, economy, Director AI, space, territory control, web client) but lacked the *infrastructure layer* that MU\* veterans expect. The gap isn't in gameplay — it's in builder extensibility, communication tools, and RP social features. The compatibility layer provides naming parity, workflow parity, and feature parity for non-softcode features without implementing a MUSHcode interpreter.

### 17.2 Phase 1: Builder & Admin Commands (`parser/mux_commands.py`, 597 lines, 11 commands)
- **`page`** — Cross-game private messaging with last-target memory, multi-target, pose/semipose (`:` and `;` prefixes), idle warnings
- **`+finger` / `+finger/set`** — Player info card (fullname, position, rp-prefs, quote, alts, theme-song, plan, timezone) stored in character attributes JSON. **[v24 Enhancement Designed]:** Structured RP preferences field (Feature #4, Design J) — combat/romance/dark-themes/mentoring/seeking-plot flags displayed as icon row. ~2-3 hrs.
- **`+where`** — Who's where, grouped by room with idle times
- **`@name`** — Rename rooms/exits by reference or ID
- **`@clone`** — Duplicate an object in the current room
- **`@decompile`** — Dump room as recreatable @dig/@describe/@set/@open/@lock commands
- **`@pemit`** — Send raw text to any player anywhere (builder+)
- **`@wall`** — Broadcast to all connections (admin)
- **`@force`** — Inject command into another player's input queue via `feed_input()` (admin)
- **`@newpassword`** — Password reset via raw SQL (admin)
- **`@shutdown`** — Graceful shutdown with broadcast, character save, SIGTERM delay (admin)

### 17.3 Phase 2: Places & RP Infrastructure (`parser/places_commands.py`, 740 lines, 11 commands)
- **Places system** — Virtual sub-locations within rooms (tables, booths, seats). Data stored in room properties JSON (no new DB table). Builder configures with `@places <count>`, customizes with `@place <#>/name = Corner Booth`.
- **`places`** — List all places with occupant names
- **`join <#>` / `sit`** — Sit at a place (by number, name, or `join with <player>`)
- **`depart` / `stand`** — Leave current place. Auto-depart on room movement.
- **`tt <msg>`** — Table-talk: place occupants see full text, rest of room sees muffled version (30% word leak rate, `"quoted"` words always leak through)
- **`ttooc`** — OOC table-talk
- **`mutter <player> = <msg>`** — Partial overheard speech (same muffling rules)
- **`@osucc` / `@ofail` / `@odrop`** — Exit messages shown to others on departure, lock failure, and arrival. Stored in exit `lock_data` JSON. `%N` substitution support.

### 17.4 Phase 3: Universal Attribute System (`parser/attr_commands.py`, 339 lines, 4 commands)
- **`object_attributes` table** (migration v13) — key-value pairs on any game object (room, exit, object, character)
- **`@setattr` / `&`** — Set attributes (`@setattr here/WEATHER = A dust storm howls outside` or `&RP_STATUS me = Looking for RP`)
- **`@wipe`** — Clear all attributes on a target
- **`@getattr`** — Read a single attribute
- **`@lattr`** — List all attributes on a target
- **`faction:X` lock type** — Added to `engine/locks.py` (e.g. `@lock exit = faction:imperial`)
- **Event hooks** — `AENTER`/`ALEAVE` room attributes fire on movement with `%N/%S/%O/%P` pronoun substitution. `fire_room_hook()` reusable dispatcher wired into MoveCommand.

### 17.5 Phase 4: Mail System (`parser/mail_commands.py`, 649 lines, 1 command class + 9 subcommands)
- **`@mail`** — List inbox (unread first, 30-message cap)
- **`@mail <player> = <subject>`** — Multi-line compose via `_input_intercept`
- **`@mail/quick <player>/<subj> = <body>`** — One-line send
- **`@mail/read <#>`** — Read message, auto-marks as read
- **`@mail/reply <#>`** — Opens compose with `Re:` prefix (also supports quick inline reply)
- **`@mail/forward <#> = <player>`** — Forward with attribution block
- **`@mail/delete <#|all>`** — Soft-delete
- **`@mail/purge`** — Permanent delete + orphan cleanup
- **`@mail/sent`** — View sent messages (last 20)
- **`@mail/unread`** — Unread count
- **Login notification** — `notify_unread_mail()` hooked into game_server login flow
- **Online delivery** — Recipients who are online get instant `[NEW MAIL]` notification
- **DB tables:** `mail` (sender, subject, body, sent_at) + `mail_recipients` (per-recipient read/deleted flags) — migration v14

### 17.6 HSpace & AresMUSH Analysis [v23 — DESIGN COMPLETE]

Design doc: `hspace_ares_integration_design_v1.md`. Thorough review of HSpace 4.4.1 (~50K lines C++) and AresMUSH (~3.9M plugins directory, Ruby) + Ares Web Portal (Ember.js SPA).

**Conclusion:** SW_MUSH already surpasses both systems in mechanical depth. HSpace has tractor beam and boarding link mechanics worth adapting; AresMUSH pioneered structured scene management and out-of-client web portals that would dramatically improve retention.

**7 features identified for integration:**
- Priority A: Web Portal (out-of-client), Scene Logging & Archive
- Priority B: Tractor Beam System, Boarding Links (ship-to-ship), Pose Order Tracker
- Priority C: Event Calendar with Signup, Plot/Story Arc Tracker

**What we should NOT port:** HSpace sensors (ours are better), HSpace damage crews (we have damcon), HSpace autopilot (our NPC traffic is more sophisticated), FS3 combat/skills (incompatible with WEG D6), Ares wiki (Director AI fills this), Ares chargen web flow (our wizard is already excellent — now delivered in §3.2A), full MUSHcode interpreter.

---

## 18. Completed Features

- Server Core, D6 Dice Engine, Character System, Building Commands [v1–v3]
- Personal Combat (full R&E, wound, CP spend), Death/Respawn [v4]
- NPC Combat AI (5 profiles), Item Instance System [v4–v5]
- Space Combat (49 cmds, 7 stations), NPC Crew [v5]
- IntentParser + BoundedContextValidator (NL combat), NPC Space Traffic [v6]
- Force Powers (8 powers, DSP, fall checks) [v6]
- Tailing, Evasive Maneuvers, Hazard Table [v7]
- Mission Board (14 types), Bounty Board (5 tiers) [v8]
- Starship Templates (19), Lock-On, GG7 NPC Data [v9]
- WebSocket Browser Client [v11], Tutorial [v12], Party System [v12]
- Communication Channels [v12], Director AI System (all 5 drops) [v12]
- Director System Integration (traffic/missions/economy) [v13]
- Smuggling Job Board (5 route tiers, patrol checks) [v13]
- Out-of-combat Skill Check Engine [v13]
- Mission/bounty completion skill checks [v13/v22]
- Skill Check Engine expanded (Bargain, Repair, Coordinate helpers) [v14]
- Buy/Sell Bargain integration (opposed roll, NPC skill auto-detect) [v14]
- Medical commands, Entertainer commands, Sabacc gambling [v14]
- CP Progression System (tick economy, kudos, scene bonus, train command) [v14]
- NPC crew wages wired [v14]
- Crafting System — SWG-Lite (resources, schematics, assembly, experimentation, teaching) [v15]
- Space Expansion v2 — All 19 Drops [v16–v19]
- Capital Ship Rules — All 5 Drops [pre-v16]
- **Organizations & Factions — All 6 Drops [v20]**
- **PC Narrative Memory — All 6 Drops [v20]**
- **Combat UX Overhaul — All 7 Drops [v20]**
- **Player Shops — All 5 Drops [v20–v21]**
- **Security Zones — Drops 1–5 + 6A/6B of 6E [v20–v21]**
- **World Builder v4 — 120 rooms, 4 planets, security zones [v20]**
- **Tutorial Expansion — All 6 profession chains [v21]**
- **Player Housing — ALL 9 Drops [v21–v26]**
- **Territory Control — ALL 5 Drops (6A–6E) [v21–v25]**
- **Web Client — Ship schematic, quick buttons with tooltips, context-sensitive modes [v21]**
- **Space bugfixes — 11 bugs fixed across sessions 7–8 [v21]**
- **WEG Rules Conformance — Tier 1 + Tier 2 complete (14 items) [v22]**
- **Tick Scheduler Refactor — 20 handlers, TickContext, deadline accounting [v22]**
- **Armor Pipeline — wear/remove/soak in combat [v22]**
- **Stun Damage + Per-Stun Expiry + CP-on-Soak + Melee Fixes [v22]**
- **Dice Engine Unification — single roll path [v22]**
- **From Dust to Stars — 30-step quest chain, Phase 1 tested [v23]**
- **Ground UX Overhaul — ALL 10 Drops [v23–v25]**
- **MU\* Compatibility Layer — all 4 phases: MUX commands, places, attributes, mail [v23]**
- **Economy Hardening — All 8 items confirmed delivered [v25 audit]**
- **Scene Logging — Full lifecycle, pose capture, CP bonus, archive queries [v25]**
- **Competitive Analysis Tier 1 — All 6 items [v26]**
- **Competitive Analysis Tier 2 — All 7 items [v26–v27]**
- **Achievement System — 30 achievements, 7 categories, 19 hooks, web toast [v27]**
- **Integration Test Framework — 279 tests, 24 files, ~27,200 lines [v27]**
- **Faction Reputation System — All 6 Drops [v28]**
- **Director Era-Progression — 7 milestones [v28]**
- **Sleeping Character Vulnerability [v28]**
- **Comlink Intercept System [v28]**
- **Web Character Creation — Embedded + standalone wizard, REST API, token auth [v28]**

---

## 18A. Competitive Analysis Features [v28 — TIER 1 + TIER 2 + TIER 3 NEAR-COMPLETE]

Design docs: `competitive_analysis_feature_mining_v1.md` (source analysis + prioritized feature list), `competitive_analysis_feature_designs_v1.md` (full implementation specs for 11 features).

Survey sources: Sindome (MOO), Armageddon MUD (RPI), AI Dungeon / NovelAI (AI narrative), Evennia (Python MU\* engine), AresMUSH (Ruby MU\* platform), Legends of the Jedi (Star Wars MUD competitor).

**Thesis:** SW_MUSH leads the field in AI-driven narrative, economy depth, and web client UX. High-value gaps: player interdependence mechanics (Sindome), environmental survival pressure (Armageddon), keyword-triggered lore injection (NovelAI Lorebook pattern), achievement/progression visibility (Evennia), scene logging (AresMUSH), and engineer-as-kingmaker crafting (LOTJ).

### 18A.1 Tier 1 — High Impact, Low Effort ✅ ALL DELIVERED

| # | Feature | Source | Status | Notes |
|---|---------|--------|--------|-------|
| 1 | `think` command → `pc_action_log` | Armageddon | ✅ DELIVERED | `ThinkCommand` in `builtin_commands.py` |
| 2 | Narrative tone per zone (YAML config) | NovelAI Author's Note | ✅ DELIVERED | `engine/zone_tones.py` + `data/zones.yaml` |
| 3 | Centralized cooldown handler | Evennia | ✅ DELIVERED | `engine/cooldowns.py` (175 lines) |
| 4 | RP preferences on `+finger` | AresMUSH | ✅ DELIVERED | Structured flags in character attributes |
| 5 | Scar system (permanent wound record) | Armageddon | ✅ DELIVERED | `engine/scars.py` (204 lines), combat hook, +sheet |
| 6 | `trade` command (safe item exchange) | Evennia barter | ✅ DELIVERED | `trade <player> item <n>`, offer/accept/decline flow |

### 18A.2 Tier 2 — High Impact, Medium Effort ✅ ALL DELIVERED (7/7)

| # | Feature | Source | Status | Notes |
|---|---------|--------|--------|-------|
| 7 | World Lore table + keyword injection | NovelAI Lorebook | ✅ DELIVERED | `engine/world_lore.py`, Director + NPC prompt injection |
| 8 | Environmental hazards (room-based) | Armageddon | ✅ DELIVERED | `hazard_type` on room properties, periodic PC check |
| 9 | Room state descriptions | Evennia ExtendedRoom | ✅ DELIVERED | Per-room state variants, Director event updates |
| 10 | Espionage commands | LOTJ / Sindome | ✅ DELIVERED | `parser/espionage_commands.py` + `engine/espionage.py` |
| 11 | Achievement system (core + web toast) | Evennia | ✅ DELIVERED | `engine/achievements.py` + `data/achievements.yaml`, 19 hooks across 14 files — see §16B |
| 12 | Crafting experimentation parameters | LOTJ engineering | ✅ DELIVERED | Engineer-tunable parameters in `engine/crafting.py` |
| 13 | Buff/debuff handler | Evennia buffs | ✅ DELIVERED | `engine/buffs.py`, prerequisite for hazards |

**Tier 1 + Tier 2 = 13/13 features delivered across sessions 22–26.**

### 18A.3 Tier 3 — Near-Complete (6/7 delivered)

| # | Feature | Source | Effort | Status |
|---|---------|--------|--------|--------|
| 14 | ~~Automated scene logging~~ | AresMUSH | ✅ DELIVERED | `engine/scenes.py` + `parser/scene_commands.py` — see §16A |
| 15 | Director era-progression thresholds | LOTJ timelines | ✅ DELIVERED [v28] | 7 milestones in `engine/director.py` — see §13B |
| 16 | Sleeping character vulnerability | Sindome | ✅ DELIVERED [v28] | `engine/sleeping.py` (298 lines) — see §16D |
| 17 | ~~Layered equipment descriptions~~ | Sindome | — | Cut from roadmap |
| 18 | Survival crafting lane | Armageddon | 6-8 hrs | **LAST REMAINING TIER 3 ITEM** — environment-specific gear schematics, demand driven by hazards |
| 19 | Comlink intercept system | Sindome SIC | ✅ DELIVERED [v28] | `parser/espionage_commands.py` — see §16E |
| 20 | Web-based character creation | AresMUSH | ✅ DELIVERED [v28] | `static/chargen.html` + `server/api.py` + `engine/chargen_validator.py` — see §3.2A |

**Tier 3 scorecard: 6/7 delivered. Only #18 (Survival Crafting Lane) remains.**

### 18A.4 Tier 4 — Future Consideration (Needs Design Doc)

| # | Feature | Source | Notes |
|---|---------|--------|-------|
| 21 | Procedural wilderness zones | Evennia wilderness | Large architectural addition for exploration content |
| 22 | Hacking/slicing minigame | Sindome Grid | Computer slicing as Star Wars counterpart to Sindome decking |
| 23 | Player-run government/senate | LOTJ Galactic Senate | Org system extension for political gameplay |

### 18A.5 What NOT to Adopt

**Permadeath** — incompatible with MMO-informed retention; scar system captures emotional weight without player loss. **Opaque mechanics** — SW_MUSH design philosophy is transparency. **Karma/trust gating** — locks content behind OOC reputation, poisons community. **Full softcode** — builder tools without requiring MUSHcode. **AI-generated room descriptions on `look`** — explicitly rejected in Director AI design doc §13. **DIKU-style level grinding** — WEG D6 dice-pool progression is superior.

---

## 19. Remaining Roadmap

### Priority A0 — WEG Rules Conformance (Tier 3 Remaining)

| # | Item | Notes | Audit Ref |
|---|------|-------|-----------|
| 16 | Skill training time / teachers | House rule territory — design call | #17 |
| 17 | Specializations as first-class skills | Only if templates use them | #18 |
| 18 | Initiative method | Perception-roll is an intentional house rule; documented in §20 | #14 |
| 19 | `board_housekeeping_tick` → interval=60 | S12 |
| 20 | Slim `get_characters_in_room` (summary variant) | S17 |

**Audit carry-forward (not yet audited):** `engine/npc_combat_ai.py`, `engine/force_powers.py` (Chapter 9), `engine/director.py` (deep audit), `engine/starships.py` (Chapter 7 space combat scale), `parser/combat_commands.py`, healing rules, tutorial/creation flow.

### Priority A — Economy Hardening ✅ COMPLETE

All 8 items confirmed delivered in live codebase (Session 19 audit). See §14.2.

### Priority A1 — Competitive Analysis Tier 1 ✅ COMPLETE

All 6 items delivered. See §18A.1.

### Priority B — Territory Control ✅ COMPLETE

All 5 drops (6A–6E) confirmed delivered in live codebase (v25 audit). See §11A.

### Priority C — Housing Completion ✅ COMPLETE

All 9 housing drops delivered (Sessions 21–22). See §12.

### Priority D — Scene Management & Web Portal

| Phase | Feature | Status | Notes |
|-------|---------|--------|-------|
| 1 | Scene logging — `+scene/*`, pose capture, CP integration | ✅ DELIVERED | `engine/scenes.py`, `parser/scene_commands.py` |
| 2 | Web portal foundation — `/who`, `/characters`, `/scenes`, `/play` | ✅ PARTIAL | Portal shell delivered (Session 30), auth + character list working |
| 3 | Space enhancements — tractor beams, boarding links | Unbuilt | Medium — WEG-faithful opposed rolls |
| 4 | RP quality-of-life — pose order tracker, event calendar, plot tracker | ✅ PARTIAL | Plot tracker delivered (Session 32) |

### Priority D3 — Faction Reputation ✅ COMPLETE

All 6 drops delivered across sessions 27-37. See §7A. Includes: fixed callers, auto-promote, +reputation command, chain rep rewards, shop discounts, NPC dialogue context, Director AI integration, web client panel, faction mission board.

### Priority D4 — Space Overhaul v3 ✅ COMPLETE

All 11 drops delivered (Session 37) + texture auto-trigger and combat cleanup (Session 38). See §6.4. 8 new files, 3,477 lines, 61 encounter handlers across 12 encounter types.

### Priority D5 — Code Review Phases 1-3 ✅ COMPLETE

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 — Crash Prevention | `execute_fetchone` bug, DB method routing | ✅ Session 33 |
| Phase 2 — Silent Failures | 172 → 0 silent except/pass blocks | ✅ Sessions 33-38 |
| Phase 3 C1 — DB Proxy | DatabaseProxy wrapper, 325 raw accesses eliminated | ✅ Session 33 |
| Phase 3 C2 — Split send_hud_update | 552→155 line orchestrator, 22 _hud_* helpers | ✅ Session 34 |
| Phase 3 C4 — God-object commands | 11/11 refactored via pipeline extraction | ✅ Sessions 34-36 |

Silent except/pass invariant enforced by regression test (`test_no_silent_except_pass_in_production`).

### Priority D1 — Competitive Analysis Tier 2 ✅ COMPLETE (7/7)

All 7 items delivered across sessions 22–26. See §18A.2.

### Priority D2 — Competitive Analysis Tier 3 — NEAR-COMPLETE (6/7)

6 of 7 items delivered across sessions 27–28 + web chargen. See §18A.3. Only #18 (Survival Crafting Lane, 6-8 hrs) remains.

### Priority D3 — Faction Reputation ✅ COMPLETE

All 6 drops delivered (Sessions 27–28). See §7A.

### Priority E — Web Client Remaining (small items)

| Item | Status | Notes |
|------|--------|-------|
| Housing sidebar panel (Drop 8) | ✅ DELIVERED | `housing_info` dict + context panel section |
| Achievement toast | ✅ DELIVERED | `achievement_unlocked` event → floating gold card, auto-dismiss 4.5s |
| Reputation panel | ✅ DELIVERED [v28] | Collapsible sidebar, tier bars, rep-change/rank-up notifications |
| Chargen overlay | ✅ DELIVERED [v28] | Embedded iframe for `/chargen?embedded=1` |
| Achievement sidebar panel | Small | Dedicated panel showing progress across categories |
| Mail panel in sidebar | Small | Unread count badge + inline read |
| Places panel in sidebar | Small | Current place + tt shortcut |
| Mobile touch optimization | Medium | Touch targets, swipe gestures |
| Accessibility improvements | Medium | Screen reader, high contrast |

### Long-term (Unscheduled)

- Survival crafting lane (#18, last Tier 3 item, 6-8 hrs)
- Web portal (Priority D Phase 2) — `/who`, `/characters`, `/scenes`, `/play`
- Galactic Marketplace (auction house, commodity exchange)
- Creature companions / pets
- Expanded Director AI (housing events, dynamic world storylines, territory narration)
- Mobile client (dedicated app vs responsive web)
- Gemini critique response implementation (`gemini_critique_response_design_v1.md`)
- Power pack / ammunition consumable system
- Dynamic trade prices (supply/demand curves)
- NPC loot tables on kill
- Ollama Idle Queue implementation (designed in v26 — see §21A)
- MU\* Compatibility Tier 5: Universal attribute system formalization (attribute inheritance, parent chains)
- MU\* Compatibility Tier 6: Event hooks (ACONNECT/ADISCONNECT/ADESC — beyond delivered AENTER/ALEAVE)
- **Competitive Analysis Tier 4 (Needs Design Doc):**
  - #21: Procedural wilderness zones
  - #22: Hacking/slicing minigame
  - #23: Player-run government/senate

---

## 20. Key Architecture Invariants

**Skill checks:** ALL out-of-combat rolls go through `engine/skill_checks.py::perform_skill_check()`. Never roll dice directly in command files. `perform_skill_check` delegates to `engine/dice.py::roll_d6_pool()` — there is ONE dice engine, not two. [v22: unified, `_roll_wild_die_pool` deleted]

**Dice engine:** `engine/dice.py` is the single source of truth for D6 rolls. Wild Die complication correctly removes highest normal die per R&E p82. Difficulty ladder in `dice.py::Difficulty` uses R&E canonical values (5/10/15/20/25/30). Mission-specific intermediate difficulties in `skill_checks.py::mission_difficulty()` are game tuning, not a second ladder.

**Territory influence:** ALL influence changes go through `engine/territory.py::adjust_territory_influence()`. Same pattern as `perform_skill_check()`.

**Housing rent:** ALL rent deductions go through `engine/housing.py::process_housing_rent()`. Weekly tick at game_server offset 432,000.

**Input intercept:** `session._input_intercept` callable bypasses normal command dispatch for multi-turn editors (housing description editor, @mail compose). Set to `None` when done. Never set in a tick loop.

**Medical consent:** `heal` → `healaccept` two-step flow. No self-healing.

**Entertainer gating:** `perform` only works in rooms within cantina-named zones.

**CP economy:** Weekly tick cap prevents grinding. Guild training bonus (20% CP cost reduction) stacks as multiplier on `advance_skill()` cost calculation.

**Organizations:** One faction per character. Up to 3 guild memberships. Faction change has 7-day cooldown + equipment return + standing consequences. Guilds have weekly dues with 3-week grace period.

**PC Narrative Memory:** Two-tier (short for Mistral, long for Haiku). Player background never overwritten by AI. Short record = public knowledge only. Budget circuit breaker shared with Director.

**Tutorial zones:** Flagged `tutorial_zone: true`. Disable ambient events, world events, NPC traffic, CP tick accrual. Tutorial ships can't be permanently destroyed.

**Vendor droids:** Stored in `objects` table with `type = 'vendor_droid'`, config in `data` JSON. Max 2 per room, 3 per character. Price floor = 50% of NPC buy-back. Same-account purchase block. Listing fee is a credit sink (destroyed, not transferred). Faction-issued items cannot be stocked. Bulk trade cargo cannot be stocked. Bargain checks route through `perform_skill_check()`. Buy order escrow lives in droid, not owner wallet. Auto-recall after 60 days idle.

**Effective stats in combat:** `get_effective_stats()` feeds into ALL combat/maneuvering code paths. Ship modifications, power allocation overcharge, and captain's order modifiers affect fire control, maneuverability, hull, shields, speed, and sensors. The helper `_get_effective_for_ship(ship)` in `space_commands.py` centralizes this pattern.

**Security zones:** `SecurityLevel` enum (SECURED/CONTESTED/LAWLESS). `get_effective_security(room_id, db, character=None)` checks room → zone → Director override → territory claim (when character provided). Ground combat gated in `AttackCommand`. Space combat gated in `FireCommand`. PvP consent dict is transient (per-session). BH guild override for active bounty contracts.

**Territory claims:** Room-level, not zone-level. Max 3 per zone, 10 total per org. Security upgrade is contextual per character — org members get CONTESTED in their claimed lawless rooms. Territory influence uses a separate `territory_influence` table from the Director's `zone_influence`. Contests have fixed 7-day duration (no acceleration). Treasury is the universal cost for all territory operations.

**Places system:** Data stored in room `properties` JSON (`properties.places`), not a separate table. No migration needed. Table-talk muffling uses 30% word survival rate with `"quoted"` segments always leaking through.

**Mail system:** Uses `_input_intercept` for multi-line compose (same pattern as housing description editor). `mail` table + `mail_recipients` table with per-recipient read/deleted flags. Login notification via `notify_unread_mail()`.

**Silent except invariant [v29]:** Zero `except Exception: pass` (or bare `except: pass`) blocks in production code. All exception handlers must include `log.warning(...)` or meaningful handling. Enforced by regression test `test_no_silent_except_pass_in_production` in `tests/test_session38.py`. Down from 172 (Session 32) → 6 (Session 37) → 0 (Session 38).

**Space encounters [v29]:** All encounter creation goes through `EncounterManager.create_encounter()` — respects cooldowns, zone caps, and ship-already-in-encounter checks. Encounter handlers registered via `mgr.register_handler(type, event, fn)`. NPC combat promotion via `get_npc_combat_manager().promote_to_combat()`. Zone security affects everything: encounter spawn rates, anomaly quality, bluff/hide difficulty, patrol competence — always read `get_space_security(zone_id)`.

**Hyperspace cleanup [v29]:** When a player enters hyperspace, the `HyperspaceCommand` cleans up: removes ship from SpaceGrid, removes targeting NPC combatants, resolves active encounters, resets traffic ship state. Any new state that needs cleanup on zone change should be added to this block.

**Faction reputation [v29]:** All rep changes go through `engine.organizations.adjust_rep()` — no direct DB writes. Auto-promotion fires after every rep increase that crosses a rank threshold. Cross-faction rep only on Empire ↔ Rebel axis. Shop discounts stack additively with Bargain skill results. `get_faction_standing_context()` injects NPC dialogue flavor.

**Critical API patterns:**
- `get_ship_by_bridge(bridge_room_id)` — use this, NOT `get_ship_by_id` (doesn't exist).
- `session_mgr.sessions_in_room(room_id)` — use this, NOT `get_sessions_in_room`.
- `session.feed_input(command)` — non-async, queues into session's input queue (used by @force).

**Patch strategy:** Complete file replacements over surgical patches for heavily-patched files — CRLF line endings on Windows cause anchor-matching failures. One file per response for large deliverables. Always read live source before writing patches. Patch scripts must use `re.MULTILINE`, include `ast.parse()` validation, create `.bak` backups, and attempt both LF and CRLF anchor variants.

**Dual-Interface Principle:** Web client adds visual convenience but never gates content; text output is canonical and must work on Telnet.

**Initiative (house rule):** Combat initiative uses a Perception *roll* (not static Perception attribute). R&E RAW uses static ordering, but the rolled variant adds tactical uncertainty appropriate for a MUSH. This is an intentional design choice, documented per audit #14. [v22]

**Graceful-drop with LOGGING:** All new hooks wrapped in `try/except` with `log.warning`. No `except Exception: pass` without logging.

**Tick scheduler:** ALL tick subsystems registered in `TickScheduler` via `game_server.py::__init__`. Handlers receive `TickContext` with shared `ships_in_space` (fetched once). Handlers that mutate ships must update `ctx.ships_in_space` in place. One exception: `tick_npc_space_combat` remains inline (takes `db`/`session_mgr` directly). Director AI calls spawned as `asyncio.create_task` — never block the tick loop with API roundtrips. [v22]

**Persistent cooldowns:** All persistent per-character cooldowns go through `engine/cooldowns.py` (check/set/clear/format). Stored as expiry timestamps in character `attributes` JSON under a `"cooldowns"` key. Transient in-memory cooldowns (scan, medical) may remain ad-hoc. Sabacc's legacy `last_sabacc` timestamp pattern is intentionally left alone. [v26]

**Scars:** All scar creation goes through `engine/scars.py::add_scar()`. Triggered by combat incapacitation hook in `combat_commands.py::_apply_combat_wear()`. Capped at 20 per character. Displayed on `+sheet` via `sheet_renderer.py`. Injected into narrative summarization prompts via `format_scars_for_narrative()`. [v26]

**Idle queue backoff:** Idle AI tasks (ambient barks, scene summaries, event rewrites) never block player-initiated dialogue. `npc_brain.py` calls `idle_queue.notify_player_request()` before every player `generate()`. The queue backs off for 5 seconds after any player request. All idle tasks use local Mistral only — never Haiku. [v26]

**Achievements:** YAML-driven (`data/achievements.yaml`), editable without code changes. All 19 hooks use graceful-drop (`try: ... except Exception: pass`) — achievement failure never breaks gameplay. CP rewards bypass weekly tick cap (milestone rewards, not grindable). Room visits tracked in `attributes["rooms_visited"]` JSON list. Web client `achievement_unlocked` renders toast; `achievements_status` reserved for future sidebar. [v27]

**Item trades:** `trade <player> item <n>`. No tax (tax only on credit transfers). Atomic transfer via `remove_from_inventory()` + `add_to_inventory()`. Accept verifies offerer still has item before transfer. [v27]

**Test framework:** `tests/harness.py` boots full game stack against temp SQLite. `MockSession` captures output without network listeners. `harness.login_as()` + `harness.cmd()` pattern for all tests. Run `python3 -m pytest tests/ -v` before every implementation zip to catch regressions. 279 tests, 24 files, ~27,200 lines. [v27]

**Faction reputation:** ALL rep changes go through `engine/organizations.adjust_rep()` — no direct DB writes. Rep history capped at 10 entries per faction (FIFO). Auto-promotion only fires for members. Cross-faction rep only applies to Empire ↔ Rebel axis. Non-member rep clamps at -100..+100, member rep at 0..100. Shop discount stacks additively with Bargain skill check. [v28]

**Sleeping characters:** Sleeping flag only set in non-SECURED rooms that aren't own housing or faction territory. Sleeping data stored in `attributes.sleeping` JSON (cleared on reconnect). Theft log capped at 10 entries per sleeping session. No sleeping in tutorial zones. [v28]

**Comlink intercept:** In-memory only (lost on restart — intentional, matches eavesdrop pattern). Intercept only delivers to players who did NOT already receive the original message. Muffling uses 20% word survival (heavier than eavesdrop's 30%). [v28]

**Web chargen tokens:** HMAC-SHA256 signed, base64 payload. `_TOKEN_SECRET` regenerated on server restart. Embedded = 30-min TTL, standalone redirect = 5-min TTL. Rate limited at 3 submits/min per IP. [v28]

---

## 21. Data Files

| File | Contents |
|------|---------|
| `data/skills.yaml` | 75 skills across 6 attributes |
| `data/species/` | 9 species templates |
| `data/weapons.yaml` | Weapon definitions |
| `data/starships.yaml` | 19 ship templates (with `reactor_power` field) |
| `data/npcs_gg7.yaml` | GG7 NPC templates |
| `data/ambient_events.yaml` | [v12] Static ambient flavor text, 7 zones |
| `data/schematics.yaml` | [v15/v19] 20 crafting schematics (8 weapons, 3 consumables, 7 ship components, 2 countermeasures) |
| `data/organizations.yaml` | [v17] 5 factions + 6 guilds, rank structures, equipment tables |
| `data/skill_descriptions.yaml` | [v28] 75 skill descriptions with game_use, tip, gameplay_note — 1,122 lines |
| `data/vendor_droids.yaml` | [v18] 3 droid tier definitions (cost, slots, listing fee, bargain dice) |
| `data/achievements.yaml` | [v27] 30 achievements in 7 categories, CP rewards, trigger events, optional prerequisites |
| `data/zones.yaml` | [v26] 14 zone narrative tone strings (4 planets + space), `name_match` prefix-matched keys |
| `engine/space_anomalies.py` | [v16] Anomaly system — 7 types, loot tables, spawning, deepscan resolution |
| `engine/trading.py` | [v19/v23] 8 trade goods, planet price tables, SupplyPool (source/demand/normal), cargo hold helpers |
| `engine/ships_log.py` | [v19] Per-character ship's log, 17 milestones, 6 titles, CP tick rewards |

---

## 21A. Ollama Idle Queue [v26 — DESIGNED]

Design doc: `ollama_idle_queue_design_v1.md`. Planned files: `engine/idle_queue.py`.

### Purpose

The RTX 3070 running Mistral 7B via Ollama is idle 95%+ of the time — NPC dialogue only fires on explicit `talk <npc>` commands. The idle queue uses this dead GPU time to pre-generate content that enriches the world, without ever interfering with player-initiated AI requests.

### Architecture

Priority-aware async work queue processed by a tick handler (every 30 ticks). Player `talk` commands bypass the queue entirely and go direct to Ollama. The queue backs off for 5 seconds after any player request via a `notify_player_request()` hook in `npc_brain.py`.

| Priority | Task | Description |
|----------|------|-------------|
| 0 (bypass) | Player `talk <npc>` | Never queued — goes direct to Ollama |
| 1 | Scene summary | After `+scene/stop`, summarize poses into `scenes.summary` |
| 2 | NPC ambient barks | Pre-generate 5-8 contextual one-liners per NPC, cached in memory |
| 3 | Director event rewrite | Rewrite template headlines with atmospheric detail |
| 4 | Housing description pre-gen | Pre-generate room description for newly purchased homes |

### Key Invariant

**Idle tasks never block player dialogue.** The queue checks `time.time() - last_player_request > 5.0` before processing. If a player `talk`s an NPC during an idle task, worst case is a 3-5 second wait (within "NPC is thinking" tolerance). All idle tasks use local Mistral only — never Haiku (budget-neutral).

### Implementation Plan (4 drops, ~10-14 hours)

| Drop | Contents | Effort |
|------|----------|--------|
| 1 | Core `engine/idle_queue.py` + ambient barks + tick handler + MoveCommand hook | 4-6 hrs |
| 2 | Scene summary task + `+scene/stop` integration | 2-3 hrs |
| 3 | Director event rewrite task | 2-3 hrs |
| 4 | Housing description cache + `.suggest` fallback | 1-2 hrs |

---

## 21B. Integration Test Framework [v27 — NEW, DELIVERED]

### Architecture

Comprehensive pytest-based test framework that boots the full SW_MUSH game stack (database, all command modules, registries) against a temporary SQLite database and exercises every system through the same `parse_and_dispatch()` code path used by live players. No network listeners or AI providers needed.

**Results: 279 passed, 41 skipped, 0 failed across 24 test files / ~27,200 lines. Runs in ~2:43.**

The 41 skips are tutorial room tests that automatically pass once a fresh DB is built with the tutorial build fix (included in session 25).

### Core Framework

- **`tests/harness.py`** (~480 lines) — `MockSession` (captures output, feeds input without sockets), `TestHarness` (boots full game stack with DB/parser/registries), assertion helpers (`strip_ansi`, `assert_output_contains`, `assert_credits_in_range`)
- **`tests/conftest.py`** — Fixtures: `harness` (pre-built world, DB copied per test), `harness_empty` (schema only), `player_session`
- **`pytest.ini`** — Configuration

### Key Harness Methods

```python
s = await harness.login_as("Han", room_id=2, credits=5000, skills={"blaster": "3D"})
out = await harness.cmd(s, "look")
delta = await harness.measure_credits_delta(s, "shop/buy 1")
credits = await harness.get_credits(s.character["id"])
inv = await harness.get_inventory(s.character["id"])
```

### Test Coverage Map

| File | Tests | Coverage |
|------|-------|---------|
| `test_world_integrity.py` | 12 | Room/exit/NPC/ship structural validation, tutorial path, zone consistency |
| `test_core_systems.py` | 24 | Look, move, sheet, inventory, say, emote, help, who |
| `test_combat.py` | 16 | Attack, dodge, parry, PvP challenge, range, cover, respawn |
| `test_combat_mechanics.py` | 31 | CombatInstance engine: multi-action penalties, wound stacking (R&E p59), Force Point doubling, full dodge exclusivity, initiative, 100-trial statistical hit validation, 50-round crash resistance |
| `test_economy.py` | 13 | Shops buy/sell, missions, smuggling jobs, credits persistence |
| `test_economy_validation.py` | 45 | All 6 audit vulnerabilities: trade goods supply caps, Bargain gate, mission skill checks, survey cooldowns, CP progression, faucet rate caps, Wild Die statistics |
| `test_space.py` | 14 | Ship listing, boarding, crew, launch/land, scan, fire |
| `test_space_lifecycle.py` | 16 | Full lifecycle: admin spawn, +myships, board/disembark, pilot/gunner, launch deducts fuel, can't double-launch |
| `test_crafting.py` | 9 | Survey, resources, schematics, craft, experiment, teach |
| `test_force.py` | 8 | Force status, powers listing, dark side, force points |
| `test_factions.py` | 7 | Faction list/info/join, guilds, territory, leader access |
| `test_factions_deep.py` | 14 | Org seeding, join/leave lifecycle, can't double-join, roster, guild, specialization, territory schema |
| `test_housing.py` | 4 | Housing listing, availability, my housing, sethome |
| `test_professions.py` | 11 | Bounty board, espionage, medical, entertainer, NPC talk, sabacc |
| `test_progression.py` | 10 | CP display/spending, D6 rolls, skill check routing |
| `test_social_systems.py` | 18 | Mail, places, scenes, narrative, MUX compat, buffs, equipment, lockpick |
| `test_crew_and_parties.py` | 6 | NPC crew, party invite/leave, spacer quest |
| `test_admin.py` | 8 | Admin access control, @dig, @desc, director, NPC management |
| `test_tutorial.py` | 39 | Core tutorial (skips if rooms missing), training grounds, all 8 electives |
| `test_multiplayer.py` | 15 | PvP challenge/accept/decline, player trade, say/whisper visibility, party, scene with 2 players |
| `test_tick_scheduler.py` | 38 | TickScheduler and ship handlers (pre-existing, separate from harness) |

### Usage

```bash
python3 -m pytest tests/ -v          # full suite
python3 -m pytest tests/test_combat.py -v  # single module
```

Run before every Sonnet implementation zip to catch regressions. Add tests as new systems are built — the `harness.login_as()` + `harness.cmd()` pattern makes this ~5 lines per test.

---

## 22. Version Change Summaries

### v29 Changes (Sessions 33–38: Code Review, Space Overhaul v3, Faction Missions, Texture Encounters)

**Session 33 — Code Review Phase 1 + DB Proxy:** `DatabaseProxy` wrapper eliminating 325 raw `db._db` accesses. `execute_fetchone` crash bug fixed. Phase 2 started (silent exception sweep).

**Session 34 — Code Review Phase 3 C2 + C4:** `send_hud_update()` decomposed from 552 → 155 lines (22 `_hud_*` helpers). 8/11 god-object commands refactored via dispatch tables. Economy Hardening verified complete in live codebase. 16 new HUD helper tests.

**Sessions 35–36 — Code Review Phase 3 C4 Complete:** Final 5 god-objects refactored (CourseCommand, CompleteMissionCommand, LookCommand, MoveCommand, TalkCommand). 82 helper methods extracted across 12 refactors. Engineering standards doc delivered. Phase 3 C4: 11/11.

**Session 37 — Space Overhaul v3 (All 11 Drops):** 8 new files, 3,477 lines, 61 encounter handlers across 12 encounter types. Space security zones (EVE high/low/null model). SpaceEncounter framework + EncounterManager. Imperial patrol redesign (4-choice). NPC space combat AI (5 profiles). Pirate/hunter/texture/anomaly encounters. Web client encounter UI. 2 bug fixes (character select IIFE scope, portal property call).

**Session 38 — Texture Auto-Trigger + Combat Cleanup + Silent Except Purge:** `texture_encounter_tick()` triggers random mechanical/cargo/contact encounters during transit, scaled by zone security. NPC combat zone-change cleanup on hyperspace jump. Final 5 silent except/pass blocks eliminated (invariant enforced by test). Faction mission board verified complete. Architecture doc v29.

**New files (Session 37-38):** `engine/space_encounters.py`, `engine/encounter_patrol.py`, `engine/encounter_pirate.py`, `engine/encounter_hunter.py`, `engine/encounter_texture.py`, `engine/encounter_anomaly.py`, `engine/npc_space_combat_ai.py`, `parser/encounter_commands.py`, `tests/test_session38.py`.

### v28 Changes (Sessions 27–28 + Web Chargen: Reputation, Era Progression, Sleeping, Intercept, Web Chargen)

| Change | Category | Notes |
|--------|----------|-------|
| Faction Reputation System — All 6 Drops | DELIVERED | `engine/organizations.py` expanded to 1,560 lines. adjust_rep refactor, auto-promotion, +reputation command, gameplay consequences (shop discounts/blocks, NPC tone), web panel (sidebar bars, rep-change/rank-up notifications), Director integration. See §7A |
| Director Era-Progression (#15) | DELIVERED | 7 era milestones in `engine/director.py` (1,787 lines). One-time events on faction dominance thresholds. See §13B |
| Sleeping Character Vulnerability (#16) | DELIVERED | `engine/sleeping.py` (298 lines, NEW). Disconnect flag, pickpocket command, theft logging. See §16D |
| Comlink Intercept (#19) | DELIVERED | `parser/espionage_commands.py` expanded to 648 lines. intercept/intercept stop/intercept status. See §16E |
| Web Character Creation (#20) | DELIVERED | 3 new files: `server/api.py` (605), `engine/chargen_validator.py` (198), `static/chargen.html` (1,830). 5 modified files. REST API, HMAC token auth, embedded + standalone modes. See §3.2A |
| Web Client Reputation Panel | DELIVERED | ~320 lines added to `client.html`. Sidebar bars, rep-change slide-in, rank-up toast. See §3.2 |
| Web Client Chargen Overlay | DELIVERED | ~50 lines added to `client.html`. Fullscreen iframe, postMessage listener, token auto-login. See §3.2 |
| Faction Shop Discounts | DELIVERED | `parser/space_commands.py` + `parser/npc_commands.py`. NPC weapon buy applies faction rep discount/markup/block |
| NPC Faction Standing Context | DELIVERED | `parser/npc_commands.py`. TalkCommand injects `FACTION STANDING` context alongside persuasion_context |
| Director Faction Standings Digest | DELIVERED | `engine/director.py`. `compile_digest()` includes player_faction_standings. System prompt instructs faction-aware targeting |
| `send_json_event` Fix | BUGFIX | `engine/organizations.py`. `send_json_event` → `await session.send_json()` — rank_up and rep_change web events were silently failing since rep Drop 2 |
| Chargen Script Parse Fix | BUGFIX | `static/chargen.html`. Orphan code caused entire script block to fail to parse; fetch calls never fired |
| Chargen EMBEDDED TDZ Fix | BUGFIX | `static/chargen.html`. `const EMBEDDED` was defined after code that referenced it; moved to top |
| Chargen Skill Tooltip Fix | BUGFIX | `server/api.py`. Key format mismatch between YAML (underscores) and registry (spaces); added normalization |
| Chargen Tooltip Cutoff Fix | BUGFIX | `static/chargen.html`. CSS `::after` centered tooltips overflowed viewport; replaced with JS-positioned engine |
| §2 File Tree | UPDATED | Added `server/api.py`, `engine/chargen_validator.py`, `engine/sleeping.py`, `static/chargen.html`. Updated version tags on 10+ existing entries |
| §3.1 Server | UPDATED | 30+ module imports, web chargen flow documented |
| §3.2 Web Client | UPDATED | Reputation panel, chargen overlay, ~6,900 lines, ~8,700 total client HTML |
| §3.2A Web Character Creation | NEW SECTION | Full technical spec: modes, API endpoints, token architecture, validator |
| §3.3 Command Parser | UPDATED | ~252 command classes |
| §7A Faction Reputation | NEW SECTION | Full technical spec: 6 drops, rep tiers, core functions, invariants |
| §13B Director AI | UPDATED | Era-progression marked DELIVERED, faction standings digest documented |
| §16D Sleeping Vulnerability | NEW SECTION | Full technical spec: sleeping.py, pickpocket, safety rules |
| §16E Comlink Intercept | NEW SECTION | Full technical spec: intercept commands, muffling, in-memory architecture |
| §18A.3 Tier 3 | UPDATED | #15, #16, #19, #20 marked ✅ DELIVERED. Scorecard: 6/7 |
| §19 Roadmap | UPDATED | Priority D2 (Tier 3) + D3 (Reputation) marked near-complete/complete. Survival crafting lane is last Tier 3 item |
| §20 Invariants | UPDATED | Faction reputation, sleeping, comlink intercept, web chargen token invariants added |
| §21 Data Files | UPDATED | `data/skill_descriptions.yaml` documented |
| §23 Web Client Roadmap | UPDATED | Reputation panel + chargen overlay marked delivered |
| §25 Design Documents | UPDATED | 6 new handoff entries + 3 new design docs |
| Codebase | UPDATED | ~85,000 lines Python, ~8,700 lines client HTML (client.html + chargen.html), ~27,200 lines tests, 252 commands, schema v14 |

### v27 Changes (Sessions 25–26: Test Framework, Achievements, Bugfixes, Tier 2 Complete)

| Change | Category | Notes |
|--------|----------|-------|
| Integration Test Framework | NEW | 24 test files, 279 tests, ~27,200 lines. `tests/harness.py` boots full game stack against temp SQLite. `MockSession` captures output without network. See §21B |
| Achievement System | NEW | `engine/achievements.py` (430 lines), `parser/achievement_commands.py` (180 lines), `data/achievements.yaml` (220 lines). 30 achievements, 7 categories, 19 hooks across 14 files. Schema v14 `character_achievements` table. See §16B |
| Safe Item Trade | DELIVERED | `trade <player> item <n>` in `builtin_commands.py`. Offer/accept/decline flow, atomic transfer, no tax. See §16C |
| Web Client Achievement Toast | DELIVERED | `achievement_unlocked` JSON event → floating gold-bordered card, auto-dismiss 4.5s |
| Competitive Analysis Tier 2 | ✅ 7/7 COMPLETE | All Tier 2 features delivered across sessions 22–26. See §18A.2 |
| Tutorial Build Fix | BUGFIX | `build_tutorial.py` — checked zone existence but not room count; fresh DBs got zero tutorial rooms |
| Smuggling Patrol Fix | BUGFIX | `parser/smuggling_commands.py` — `Character.from_dict()` doesn't exist; patrol checks now route through `perform_skill_check()` |
| Survey Resource Signature Fix | BUGFIX | `engine/crafting.py` — `get_survey_resources()` returned bare strings, not dicts; now returns proper resource dicts with amount/quality |
| Survey Room Classification Fix | BUGFIX | `parser/crafting_commands.py` — rooms don't have `type` field; now passes room name for outdoor keyword matching |

### v26 Changes (Sessions 21–22: Tier 1 Quick Wins, Housing Completion, Idle Queue Design)

| Change | Category | Notes |
|--------|----------|-------|
| Housing Drop 6 — Org HQs (Tier 5) | DELIVERED | `TIER5_TYPES` (outpost/chapter_house/fortress), `purchase_hq()` / `sell_hq()`, faction-themed descs, degradation cascade, `faction hq` command tree, 6 lots across 4 planets |
| Housing Drop 8 — Web Panel | DELIVERED | `housing_info` HUD dict, context panel section (storage bar, rent status, action buttons), owner/visitor detection, perf-gated on `rooms.housing_id` |
| Housing Drop 9 — AI Descriptions | DELIVERED | `.suggest` / `.accept` in description editor via Haiku, `housing visit <player>` shopfront lookup |
| `think` command | DELIVERED | `ThinkCommand` in `builtin_commands.py`, `pc_action_log` with `event_type='thought'`, narrative pipeline integration |
| Scar system | DELIVERED | `engine/scars.py` (204 lines), 15 body locations, weapon-type generators, `+sheet` display, narrative injection, combat hook on incapacitation |
| Centralized cooldown handler | DELIVERED | `engine/cooldowns.py` (175 lines), survey 5-min cooldown migrated, sabacc/scan left as intentional legacy |
| Narrative tone per zone | DELIVERED | `engine/zone_tones.py` (137 lines), `data/zones.yaml` (14 zones), Director + NPC brain prompt injection |
| Ollama Idle Queue | DESIGN COMPLETE | `ollama_idle_queue_design_v1.md` — priority queue for GPU idle time: ambient barks, scene summaries, event rewrites, description pre-gen |
| §12 Housing | COMPLETE | All 9 drops delivered — rented rooms through org HQs, web panel, AI descriptions |
| §13B Director AI | UPDATED | Narrative tone marked delivered; World Lore + Era-Progression remain designed |
| §19 Roadmap | UPDATED | Priority A1 partially delivered (4 of 6 items), Priority C complete, §21A idle queue added |
| §20 Invariants | UPDATED | Cooldowns, scars, idle queue backoff rules added |
| §21A Ollama Idle Queue | NEW SECTION | Full architecture spec for idle GPU utilization |
| Codebase | UPDATED | ~77,000 lines Python, ~6,400 lines client HTML |

### v25 Changes (Codebase Audit — Sessions 19–20)

| Change | Category | Notes |
|--------|----------|-------|
| Architecture doc v25 | AUDIT | Full codebase audit against v24 doc; corrected schema version, line counts, completed items |
| Schema corrected to v13 | AUDIT | v13 = scenes/scene_poses/scene_participants. Previous doc incorrectly listed v14 (object_attributes, mail tables not in database.py migrations — those are initialized by engine modules directly) |
| Codebase size corrected | AUDIT | ~76,500 lines Python (excluding venv), ~6,200 lines client HTML |
| Territory Drops 6C–6E | CONFIRMED DELIVERED | Guard spawning/removal, resource nodes, faction armory, contest state machine, hostile takeover, web territory badge — all in live codebase |
| Housing Drop 5 — Shopfronts | CONFIRMED DELIVERED | `HOUSING_LOTS_TIER4`, `purchase_shopfront()`, `sell_shopfront()`, `MarketSearchCommand` |
| Housing Drop 7 — Intrusion | CONFIRMED DELIVERED | `LockpickCommand`, `ForceDoorCommand`, `StealCommand`, `housing_intrusions` table |
| Scene Logging — Phase 1 | CONFIRMED DELIVERED | `engine/scenes.py` (474 lines), `parser/scene_commands.py` (439 lines), schema v13 tables, pose capture hooks in SayCommand/EmoteCommand/OocCommand, CP bonus on stop, warm cache on startup |
| Economy Hardening — all 8 items | CONFIRMED DELIVERED | Transaction tax, docking fees, credit_log, @economy velocity, NPC resource vendors, CP rebalance, kudos room removal (Session 19 audit) |
| Ground UX Drops 8–10 | CONFIRMED DELIVERED | Nearby Services panel, Credits ticker + CP bar + zone influence gauge, Director Story Feed (Session 19) |

### v24 Changes (Competitive Analysis & Feature Mining)

| Change | Category | Notes |
|--------|----------|-------|
| Competitive Analysis & Feature Mining | DESIGN COMPLETE | `competitive_analysis_feature_mining_v1.md` — 6-source survey (Sindome, Armageddon, NovelAI, Evennia, AresMUSH, LOTJ), 23 actionable features in 4 tiers |
| Competitive Analysis Feature Designs | DESIGN COMPLETE | `competitive_analysis_feature_designs_v1.md` — full implementation specs for 11 features (A–K): Permadeath, Think, World Lore, Narrative Tone, Hazards, Espionage, Achievements, Buffs, Safe Trade, RP Prefs, Cooldowns |

### v23 Changes (Sessions 10–17: FDTS, Ground UX, MUX Compat, Economy Hardening Design)

| Change | Category | Notes |
|--------|----------|-------|
| From Dust to Stars Quest Chain | DELIVERED | 30-step, 5-phase quest engine: `engine/spacer_quest.py` (1,528 lines), `engine/debt.py` (159 lines), `parser/spacer_quest_commands.py` (370 lines). Phase 1 tested. |
| FDTS Hook Installation | DELIVERED | 15+ hooks across 12 files |
| Ground UX Overhaul — Drops 1-4, 6-7 | DELIVERED | Room detail card, NPC roles + actions, loadout, area map, jobs tracker, smart buttons |
| Schema v11 | DELIVERED | `map_x`/`map_y` REAL columns on rooms table |
| 120 Map Coordinates | DELIVERED | Hand-tuned positions for all rooms in `build_mos_eisley.py` |
| MUX Compatibility Layer — All 4 Phases | DELIVERED | ~2,325 lines total |
| Economy Hardening Design | DESIGN COMPLETE | `economy_hardening_design_v1.md` |

### v22 Changes (WEG Audit + Structural Hardening)

| Change | Category | Notes |
|--------|----------|-------|
| Tick Scheduler Refactor | DELIVERED | 470-line monolith → `TickScheduler` + 20 handlers |
| Dice engine unification | DELIVERED | Deleted `_roll_wild_die_pool`; all rolls via `dice.roll_d6_pool` |
| Armor pipeline | DELIVERED | `wear`/`remove armor`/`armor` commands, soak integration |
| Stun damage routing | DELIVERED | `attack <target> stun`, capped at unconscious |

### v21 Changes (Sessions 7–9 + Economy Audit)

| Change | Category | Notes |
|--------|----------|-------|
| Player Housing — Drops 1–4 | DELIVERED | Rented rooms, description editor, trophies, faction quarters, private residences |
| Security Drop 6A–6B | DELIVERED | Territory influence + room claiming |
| Tutorial — All 6 profession chains | DELIVERED | Smuggler/Hunter/Artisan/Rebel/Imperial/Underworld |
| Economy Audit | DESIGN COMPLETE | 6 vulnerabilities, 17 specific fixes |

### v20 Changes

| Change | Category | Notes |
|--------|----------|-------|
| Organizations & Factions — all 6 drops | DELIVERED | Join/leave, payroll, equipment, leader commands, Director integration |
| PC Narrative Memory — all 6 drops | DELIVERED | Two-tier records, action logging, nightly summarization |
| Combat UX Overhaul — all 7 drops | DELIVERED | Paced output, ANSI hierarchy, web panel, verb variety |
| Player Shops — Drops 1–3 | DELIVERED | Core droid lifecycle, browse, stock/unstock, NPC dealers |
| Security Zones — Drops 1–3 | DELIVERED | Security engine, combat gates, PvP consent |
| World Builder v4 | DELIVERED | 120 rooms, 4 planets, security zones, ~39 PLANET_NPCs |

---

## 23. Web Client Enhancement Roadmap [v28]

The browser client (`static/client.html`, ~6,900 lines) + chargen (`static/chargen.html`, ~1,830 lines) are the primary interfaces for most players.

**Delivered features:** ANSI-to-HTML rendering, split-pane layout, command history, mobile responsive, HUD sidebar, ambient mood theming, zone-keyed environments, Director AI alert badges, world event banners, pre-login sidebar dimming. Space HUD: space panel, station-aware quick buttons, zone map SVG, tactical radar SVG, anomaly pings, power allocation bar, captain's order badge, ship status schematic. Combat panel: wound pips, initiative order, declared actions, ★ viewer marker, phase labels, round badge. Security: color-coded zone badges. Context-sensitive quick buttons via `QUICK_MODES` with tooltip descriptions. Housing and vendor droid detection. **Ground UX [v23–v25]:** Room detail card (description, services, NPC roles+actions), loadout sidebar, area map with environment theming + fullscreen modal + zoom/pan/legend, active jobs tracker, smart context-sensitive quick buttons, Nearby Services panel, Credits ticker with animated delta, CP progress bar, Zone influence gauge (mini bar chart), Director Story Feed (Zone Intel panel). **Territory [v25]:** Claim badge (`◆ OrgName ■`) with guard symbol and contested-glow, contest alert injected into news feed. **Achievement toast [v27]:** Floating gold-bordered card on `achievement_unlocked` event with icon, name, description, CP reward; auto-dismiss after 4.5s. **Reputation panel [v28]:** Collapsible "Faction Standing" sidebar with colored tier bars, rep-change slide-in notification (2.5s), rank-up toast (4s, star animation). **Chargen overlay [v28]:** Fullscreen iframe for embedded character creation, postMessage integration, token auto-login.

**Remaining:**
- Achievement sidebar panel — dedicated panel showing progress across categories
- Mail panel in sidebar — unread count badge + inline read
- Places panel in sidebar — current place + `tt` shortcut
- Mobile touch optimization
- Accessibility improvements
- Web portal (Priority D Phase 2) — `/who`, `/characters`, `/scenes`, `/play` — separate aiohttp SPA

---

## 24. WEG Sourcebook Reference

| Document | ID | Format | Notes |
|----------|-----|--------|-------|
| D6 Revised & Expanded Rulebook | WEG40120 | Extractable PDF | Primary rules reference; `pdftotext` works |
| Galaxy Guide 7: Mos Eisley | WEG40069 | JPEG scan zip | NPC stats, location maps; visual reading only |
| Galaxy Guide 6: Tramp Freighters | WEG40027 | Partial PDF | Ship operations, cargo rules |
| Star Wars Sourcebook 2nd Ed | WEG40093 | PDF (2 parts) | Equipment, vehicles, organizations |
| Platt's Smugglers Guide | WEG40141 | Scanned PDF | Smuggling equipment, ship quirks, customs infractions |
| Pirates & Privateers | WEG40143 | Scanned PDF | Pirate tactics, countermeasures, transponder codes |
| Star Warriors | WEG40201 | — | Damage control, space combat mechanics |
| Gamemaster Kit | WEG40048 | PDF | Adventure scenarios |
| WEG40092 | — | PDF | Additional source material |
| WEG40124 | — | PDF | Additional source material |

Non-WEG40120 PDFs are mostly JPEG scans requiring visual reading. Use `pdftoppm -jpeg -r 150` to rasterize pages.

---

## 25. Design Documents Reference

| Document | Status | Contents |
|----------|--------|----------|
| `economy_design_v02-1.md` | Reference | Core economy design — faucets, sinks, profession lanes |
| `economy_audit_v1.md` | **NEW v21** | Economy audit — 6 vulnerabilities, 17 fixes in 3 phases |
| `economy_hardening_design_v1.md` | **NEW v23** | Economy hardening — 6 items, all delivered |
| `director_ai_design_v1.md` | Delivered | Director AI system spec |
| `space_expansion_v2_design.md` | Delivered | Space expansion — all 19 drops complete |
| `space_expansion_v2_addendum.md` | Delivered | Phases 10–14 (power, orders, trade, transponders, quirks) |
| `combat_ux_overhaul_design.md` | Delivered | Combat UX — all 7 drops complete |
| `capital_ship_rules_design.md` | Delivered | Capital ship combat — all 5 drops complete |
| `organizations_factions_design_v1.md` | Delivered | Factions & guilds — all 6 drops complete |
| `pc_narrative_memory_design_v1.md` | Delivered | PC narrative memory — all 6 drops complete |
| `tutorial_system_design.md` | Delivered | Tutorial — all drops complete |
| `tutorial_factions_addendum_v2.md` | Delivered | Tutorial faction integration — delivered |
| `player_shops_design_v1.md` | Delivered | Player shops — all 5 drops complete |
| `security_zones_design_v1.md` | **DELIVERED v25** | Security zones — all drops complete |
| `security_drop6_territory_control_design_v1.md` | **DELIVERED v25** | Territory control — all 5 drops delivered |
| `player_housing_design_v1.md` | **DELIVERED v26** | Player housing — all 9 drops complete |
| `from_dust_to_stars_design_v1.md` | **NEW v23** | 30-step quest chain — implemented, Phase 1 tested |
| `ground_ux_overhaul_design_v1.md` | **NEW v23** | Ground UX — all 10 drops delivered |
| `tinymux_comparison_design_v1.md` | **NEW v23** | TinyMUX comparison — all 4 phases delivered |
| `competitive_analysis_feature_mining_v1.md` | **NEW v24** | 6-source competitive analysis — 23 features in 4 tiers |
| `competitive_analysis_feature_designs_v1.md` | **NEW v24** | Full implementation specs for 11 features (A–K) |
| `hspace_ares_integration_design_v1.md` | **NEW v23** | HSpace & AresMUSH analysis — 7 features for integration |
| `web_ux_competitive_analysis.md` | Mostly delivered | Quick buttons + tooltips done; notification/mobile remain |
| `web_client_ux_overhaul_v1.md` | Delivered | Web UX overhaul spec |
| `gemini_critique_response_design_v1.md` | Design only | Response to external critique — unscheduled |
| `AUDIT_HANDOFF.md` | **NEW v22** | WEG rules conformance + scaling audit |
| `code_review_fixes_design_v1.md` | **NEW v22** | Tick scheduler, exception sweep, DB consolidation |
| `ollama_idle_queue_design_v1.md` | **NEW v26** | Ollama idle queue design |
| `faction_reputation_design_v1.md` | **NEW v28** | Faction reputation system — all 6 drops delivered |
| `web_chargen_design_v1.md` | **NEW v28** | Web character creation — all 8 drops delivered |
| `tutorial_bugfix_design_v1.md` | **NEW v28** | Tutorial build fix design |
| `HANDOFF_APR15_SESSION27.md` | **NEW v28** | Architecture v27 + faction reputation drops 1-3 |
| `HANDOFF_APR15_SESSION28.md` | **NEW v28** | Reputation drops 4-6 + Tier 3 features #15, #16, #19 |
| `HANDOFF_APR15_WEB_CHARGEN.md` | **NEW v28** | Web character creation drops 1-8 |
| `sourcebook_mining_crafting_exp_design_v1.md` | **NEW v27** | Sourcebook extraction results for crafting + experimentation |
| `gg10_bounty_hunters_extraction_v1.md` | **NEW v27** | Galaxy Guide 10 bounty hunter extraction |
| `crackens_rebel_field_guide_extraction_v1.md` | **NEW v27** | Cracken's Rebel Field Guide extraction |
| `space_overhaul_v3_design.md` | **NEW v29** | Space Overhaul v3 — 2,012 lines. Archetype loops, security zones, encounter catalogue, NPC combat AI, web UI. All 11 drops delivered. |
| `db_proxy_design_v1.md` | **NEW v29** | DatabaseProxy wrapper design — Phase 3 C1 |
| `engineering_standards_v1.md` | **NEW v29** | Engineering standards and code review process |
| `architecture_status_post_review.md` | **NEW v29** | Post-review architecture status assessment |
| `code_review_session32.md` | **NEW v29** | Session 32 code review findings (6 priority areas) |
| `HANDOFF_APR15_SESSION29.md` | **NEW v29** | Web portal drops 1-4 |
| `HANDOFF_APR15_SESSION30.md` | **NEW v29** | Web portal drops 5-6 |
| `HANDOFF_APR15_SESSION31.md` | **NEW v29** | Events bugfix + sidebar panels |
| `HANDOFF_APR15_SESSION32.md` | **NEW v29** | Plots system + code review |
| `HANDOFF_APR16_SESSION33.md` | **NEW v29** | DB Proxy + Phase 1 crash fix |
| `HANDOFF_APR16_SESSION34.md` | **NEW v29** | HUD decomposition + god-object refactoring |
| `HANDOFF_APR16_SESSION35.md` | **NEW v29** | Engineering standards + C4 progress |
| `HANDOFF_APR16_SESSION36.md` | **NEW v29** | Phase 3 C4 complete (11/11) |
| `HANDOFF_APR16_SESSION37.md` | **NEW v29** | Space Overhaul v3 — all 11 drops |
| `HANDOFF_APR17_SESSION38.md` | **NEW v29** | Texture encounters + combat cleanup + silent except purge |

---

*End of Architecture Document — Version 29*
*Reference: all design documents listed in §25, all handoff docs listed above.*