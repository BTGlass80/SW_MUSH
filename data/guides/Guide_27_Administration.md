---
category: admin
order: 1
summary: "Running the game: granting access, world-building, the Director AI, moderation, and the staff command set. Admin-only."
tags: ["admin", "staff", "builder", "administration", "moderation", "grant", "director", "wizard"]
access_level: 3
---

# Administration

**SW_MUSH — Star Wars D6 Revised & Expanded**
**Game administration reference — ADMIN ONLY**

---

This guide is gated to admins (`access_level: 3`); players never see it. It documents the
live staff command surface. Every command below was verified against the command registry
at authoring time — but the codebase moves, so if a command behaves differently than
described, trust the game and re-check the handler. Builder-tier (`@dig`/`@open`/etc.)
world-building has its own in-game help: `help building`. City moderation has `help @city`.

## 1. Access levels & granting access

Three tiers (`parser/commands.py::AccessLevel`):

| Level | Name | Flag | Can do |
|-------|------|------|--------|
| 1 | PLAYER | (logged in) | normal play |
| 2 | BUILDER | `accounts.is_builder` | world-building commands (`@dig`, `@open`, …) |
| 3 | ADMIN | `accounts.is_admin` | everything below |

Each command checks the caller's level via `BaseCommand.check_access()`, which reads the
account's `is_admin` / `is_builder` flag.

**Granting access — `@grant`:**
```
@grant <player> = builder      — give world-building access
@grant <player> = admin        — give full admin access
```
Updates the `accounts` row and takes effect live for an online player — no restart. This
is how you make someone staff. To remove access you currently edit the account flag
directly (there is no `@revoke` verb).

## 2. World-building (BUILDER+)

The full builder toolkit lives behind `help building`. The core verbs: `@dig` (new room),
`@tunnel` (dig + auto return exit), `@open` / `@link` / `@unlink` (exits), `@rdesc` /
`@rname` (room text), `@destroy` (delete a room), `@teleport` (go to a room), `@examine`
(inspect), `@rooms` / `@find` / `@entrances` (locate), `@set` / `@lock` / `@success` /
`@fail` (properties & locks), `@zone` (zones), `@create` (in-game objects), `@emit` /
`@name` / `@pemit` (room/object text & messaging).

⚠️ **Map-safety invariant:** the painted exterior surface rooms are pinned by a coordinate
golden snapshot, and world YAML is edited additively. Live `@`-building of those surfaces
can desync the snapshot. For exterior/world geography, prefer the data-file pipeline over
live digging; use live building for interiors and ad-hoc scene rooms.

## 3. The Director AI (ADMIN)

The Director is the Claude-backed world-orchestration layer. Admin controls:

| Command | What it does |
|---------|--------------|
| `@director status` | show Director state, budget, last run |
| `@director enable` / `disable` | turn the AI orchestration on/off |
| `@director trigger` | force a faction turn / Director pass now |
| `@director budget` | inspect/adjust the Claude spend circuit-breaker |
| `@director influence` | inspect/adjust territory influence |
| `@director log` / `reset` / `narrative` / `cult` | run log, state reset, narrative & cult subforms |
| `@economy` | economy dashboard — shops/credits/zones/velocity/alerts/throttle |
| `@lore` | world-lore entries — list/search/add/disable/enable |
| `@hazard` | set/clear/list environmental room hazards (heat, toxic atmosphere, …) |
| `@roomstate` | apply/clear/list dynamic room-state overlays |
| `@ai` | AI subsystem status — Ollama queue, bark cache, flush |

The Director runs on a budget circuit-breaker (~$20/mo target); `@director budget` is where
you watch and cap it. Missing Ollama or an absent API key degrades to mocks — the game
still runs; you just lose live NPC dialogue / Director narration.

## 4. Moderation (ADMIN)

| Command | What it does |
|---------|--------------|
| `@wall <msg>` | broadcast to every connected player |
| `@force <player> = <command>` | run a command as that player (use sparingly) |
| `@newpassword <player>` | reset an account password |
| `@pcbounty void / review / fulfill` | moderate PC-placed bounties (refund / inspect / assign) |
| `@city` | player-city moderation — list/inspect/void-banish/set-rate-cap/dissolve/rename (`help @city`) |
| `@security` | zone security — show/set, faction room override set/clear |
| `@faction` | faction admin — leader handoff, Director enable/disable, treasury add/remove |

**Note on what does NOT exist:** there is no `@ban`, `@boot`/`@kick`, `@mute`, `@slay`, or
generic `@spawn` verb. Player removal is handled through city banishment (`@city`) and
account-level controls, not a global kick. NPCs are data-driven / auto-spawned (e.g. a
bounty hunter via `@setbounty`), not hand-summoned. Don't promise players a moderation
verb that isn't here.

## 5. Jedi & progression overrides (ADMIN)

These bypass the normal consent/attestation gates — use them for Council-fiat situations:

| Command | What it does |
|---------|--------------|
| `@bond <master> = <padawan>` | force a Master–Padawan bond (skips consent) |
| `@trial <trial_name> = <padawan>` | record a Trial pass (skips Master attestation) |
| `@knight <padawan>` | promote to Knight bypassing the all-5-Trials gate (battlefield knighting) |
| `@weight` | inspect/set a character's Weight of War and Force Points (show/set/history/fp) |

## 6. Debug & commerce (ADMIN)

| Command | What it does |
|---------|--------------|
| `@getcharattr [key]` (`@gca`) | dump your character's attribute-JSON keys (optionally one key) |
| `@setcharattr <key> = <value>` (`@sca`) | set one of your character's JSON attributes (raw debug write — be careful) |
| `@shop` | vendor-droid management — list/inspect/remove |
| `@setbounty <player>` | set a bounty flag and spawn a bounty hunter |
| `@narrative` | PC narrative-memory system — status/view/update/reset/log/enable/disable/runnow |

`@setcharattr` writes raw character attribute-JSON with no validation. It is the most
dangerous admin verb — a malformed write can corrupt a character sheet. Prefer the
purpose-built commands above it whenever one exists. (Not to be confused with `@setattr`,
the builder command that sets user-defined attributes on rooms/exits/objects.)

## 7. Server lifecycle

Launch the server from a plain terminal outside any Claude Code session (it binds the web
and telnet ports and touches the live `sw_mush.db`). `@shutdown` (if enabled) does a
graceful in-game stop. Routine restarts are a terminal operation, not an in-game one.

---

*End of Guide #27 — Administration (admin-only)*
