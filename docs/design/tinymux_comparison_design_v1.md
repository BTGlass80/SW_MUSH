# TinyMUX ↔ SW_MUSH Comparative Analysis & Porting Strategy
## Design Document v1.0
### April 2026 · Opus Session

---

## 1. Executive Summary

After a thorough code review of both TinyMUX (132K lines of C++ engine alone, 510 built-in functions, 126 `@`-commands, 524 total command table entries) and SW_MUSH (69K lines Python, 203 command classes, 25 modules), the picture is clear: **SW_MUSH is already a strong game, but it's not yet a MU\* platform.** A TinyMUX veteran admin or builder who connects will find the gameplay systems far beyond what TinyMUX offers natively — but they'll be missing the *infrastructure layer* that lets them extend the game without touching Python code.

The gap isn't in gameplay — it's in **builder extensibility, the object model, and softcode**. Closing this gap doesn't mean reimplementing TinyMUX. It means identifying the 20% of MU\* platform features that deliver 80% of builder/admin familiarity, and wiring those into our existing architecture.

---

## 2. What SW_MUSH Does Better Than TinyMUX

Before diving into gaps, it's worth acknowledging that SW_MUSH already surpasses TinyMUX in several significant areas. These are features TinyMUX builders would be *impressed* by, not things they'd miss:

**Integrated game mechanics.** TinyMUX has zero built-in RPG mechanics. All dice rolling, combat, character sheets, skills — everything gets softcoded from scratch by each game. Our WEG D6 engine, combat system, skill checks, CP progression, and Force powers are all first-class citizens. A TinyMUX Star Wars game would need thousands of lines of softcode (written in TinyMUX's notoriously arcane syntax) to replicate what we ship out of the box.

**Economy engine.** TinyMUX has `@cost` and basic penny tracking. We have crafting, trade goods, smuggling, vendor droids, faction payroll, mission boards, bounty hunting, and an economy audit framework. The gap is enormous.

**Director AI.** Nothing remotely comparable exists in TinyMUX. AI-driven narrative, NPC dialogue via Ollama, scene context generation — this is generational.

**Space system.** TinyMUX has no native space. MU\* space systems (like HSpace or FS3) are notoriously complex add-ons. We have 49 space commands, 19 ship templates, 16 zones, NPC traffic, and a full web HUD.

**Web client.** TinyMUX recently added WebSocket support and a proxy architecture, but the client is still fundamentally a Telnet terminal. Our split-pane browser client with context-sensitive quick buttons, space HUD, combat panel, territory panel, and tooltips is a different class of product.

**Tutorial system.** TinyMUX has none. We have a multi-step tutorial with profession chains and faction onboarding.

**Territory control.** Influence-based territory claiming, guard NPCs, resource nodes, contesting — none of this exists in the MU\* world as a built-in.

---

## 3. The Gaps: What TinyMUX Builders Will Miss

### 3.1 The Object Model (CRITICAL)

This is the fundamental architectural difference. TinyMUX has a **unified object model** with four types: Room, Thing, Exit, Player. Every object:
- Has a unique database reference number (dbref, e.g., `#1234`)
- Can store arbitrary **user-defined attributes** (key-value pairs)
- Has a set of **flags** (DARK, STICKY, WIZARD, INHERIT, etc.)
- Has an **owner**
- Has a **parent** (attribute inheritance chain)
- Has a **zone** (permission grouping)
- Can have **locks** (boolean expressions controlling who can interact)

Our model is **relational and specialized**: separate tables for rooms, exits, objects, characters, ships, NPCs, etc. This is great for our game mechanics (type safety, indexing, complex queries) but it means:

- **No arbitrary attributes on objects.** In TinyMUX, `&MY_CUSTOM_DATA object = some value` stores anything on anything. Our objects have a `data` JSON blob, but there's no universal attribute system that works across all types.
- **No parent chain / attribute inheritance.** TinyMUX's `@parent` lets you set up template hierarchies. Room #100 parents to Zone Master Room #50, which parents to Global Master Room #1. When you look up an attribute, the system walks the parent chain. We don't have this.
- **No dbref-based addressing.** TinyMUX builders constantly reference `#1234` to target any object. We have room IDs, character IDs, exit IDs, but they're in separate namespaces.
- **Limited flag system.** TinyMUX has ~60 flags (DARK, STICKY, OPAQUE, TRANSPARENT, WIZARD, etc.) that modify behavior in well-known ways. We have `is_admin`, `is_builder`, and room properties in JSON.

**Impact:** HIGH. This affects how builders think about world construction. A TinyMUX builder creates a "Generic NPC" thing object, sets attributes on it, and parents other NPCs to it. They can't do that here.

### 3.2 Softcode / MUSHcode (STRATEGIC DECISION REQUIRED)

TinyMUX's defining feature is **softcode** — an in-game programming language with 510 built-in functions. Examples:
```
&CMD-FINGER obj=$+finger *:@pemit %#=[name(num(*%0))] is cool.
[add(2,3)]                    → 5
[iter(1 2 3,mul(##,2))]       → 2 4 6
[switch(%0,foo,bar,baz)]      → conditional matching
```

This lets admins build entire game systems *without server restarts*. The SGP (Sandbox Globals Package) is a prime example — `+finger`, `+who`, `+staff`, `+where`, `+view`, `+knock`, `+shout`, `+mutter`, `places` — all implemented in MUSHcode, all loaded by uploading text files.

**Our position:** We don't need a full MUSHcode interpreter. Here's why:

1. **Softcode exists because MU\* servers have no built-in game logic.** Everything must be coded by admins. We already have 200+ commands and dozens of engine modules. The systems that MUSHcode usually implements (dice, combat, chargen, channels, etc.) are already Python-native.

2. **MUSHcode is widely reviled.** It's an impenetrable syntax that drives away modern developers. The `+finger` command in SGP is a single line of 1,200 characters. No one wants to debug that.

3. **The actual need is extensibility, not compatibility.** Builders want to add custom commands, set custom messages on rooms, trigger actions on events. We can provide that through cleaner mechanisms.

**However**, there are a few TinyMUX softcode *functions* that builders use constantly in everyday building (not programming) that we should support. These are less "programming language" and more "template substitution":

| Function | What it does | Our equivalent |
|----------|-------------|----------------|
| `%N` / `%n` | Enactor's name | We already handle this in poses |
| `%L` / `%l` | Enactor's location | Available via context |
| `%0`–`%9` | Positional args | Not needed (we parse args differently) |
| `[name(#1234)]` | Get object name | `@examine` partially covers this |
| `[get(obj/attr)]` | Get attribute value | Needs attribute system first |

### 3.3 Missing Builder Commands

Commands that TinyMUX has and we lack, grouped by how much builders would miss them:

**Must-Have (builders use these daily):**
| TinyMUX Command | Purpose | Our Status |
|----------------|---------|------------|
| `@desc` | Set description (alias for our `@describe`) | **Have it** (`@describe`) but naming differs |
| `@name` | Rename objects/rooms | Missing — must delete and recreate |
| `@chown` | Change object ownership | Missing |
| `@clone` | Duplicate an object | Missing |
| `@parent` | Set parent object | Missing (no parent chain) |
| `@wipe` | Clear all attributes | Missing (no attribute system) |
| `@decompile` | Dump object as commands | Missing — `@examine` partial substitute |
| `@trigger` | Execute an action list | Missing (no action lists) |
| `@force` | Force object to execute command | Missing |
| `@pemit` | Send message to specific player | Missing (have `whisper` and `page` but not raw emit-to-player) |
| `@wall` | Broadcast to all connected | Missing |
| `@shutdown` | Graceful server shutdown | Missing from in-game |
| `@newpassword` | Admin password reset | Missing |

**Nice-to-Have (used regularly but less critical):**
| TinyMUX Command | Purpose | Our Status |
|----------------|---------|------------|
| `@switch` | Conditional execution | N/A — we're not softcode |
| `@dolist` | Iterate over list | N/A — we're not softcode |
| `@wait` | Delayed execution | N/A — we're not softcode |
| `@scan` | View softcode on objects | N/A — no softcode |
| `@edit` | Find/replace in attributes | Missing |
| `@cpattr` | Copy attributes between objects | Missing (no attributes) |
| `@mvattr` | Move attributes | Missing (no attributes) |

**Not Needed (replaced by our systems):**
| TinyMUX Command | Purpose | Our Replacement |
|----------------|---------|-----------------|
| `@mail` | In-game mail | Not yet built, but could be |
| `@cron` | Scheduled tasks | Our tick_scheduler handles this |
| `@quota` | Object creation limits | Not needed with our architecture |
| `think` | Private eval output | Not needed without softcode |

### 3.4 The Places System

TinyMUX's SGP includes the **Places** system — virtual sub-locations within a room. `configure 3 places` creates 3 "tables" in a cantina; players `join 1` to sit at Table 1. Players at the same table see each other's `tt` (table-talk) messages; the rest of the room sees partial/muted versions.

This is *extremely* popular on RP MUSHes and is exactly the kind of thing a Star Wars game would want — cantina tables, cockpit seats, different areas of a large room.

**Impact:** MEDIUM-HIGH. RP-focused players expect this. It's a comfort feature that signals "this game gets MU\* culture."

### 3.5 Communication Gaps

| Feature | TinyMUX | SW_MUSH |
|---------|---------|---------|
| `page <player>=<msg>` | Built-in private messaging | We have `whisper` (room-local) but not cross-game `page` |
| `@mail` | Full mail system with folders | Not built |
| `+finger` | Player info display | Not built |
| `+where` | Who's where (findable players) | Partial — `who` shows room |
| `mutter` | Partial overheard speech | Not built |
| `MONITOR` flag on rooms | Hears connect/disconnect | Not built |

### 3.6 Lock System Sophistication

TinyMUX locks are **boolean expressions** that can combine conditions:
```
@lock door = flag/WIZARD | attribute/FACTION:IMPERIAL & !#1234
```

Our lock system (from `engine/locks.py`) supports:
- Skill check locks (`skill:stealth:15`)
- Key item locks (`key:Cantina Pass`)
- Faction locks (`faction:imperial`)
- Admin-only locks (`admin`)

We're actually in decent shape here, but we lack the *composability* — you can't say "faction:imperial OR skill:con_artist:20". Compound locks are a notable gap.

---

## 4. Porting Strategy: The Compatibility Layer

### 4.1 Philosophy: Familiar, Not Identical

The goal is NOT to implement a MUSHcode interpreter. The goal is:

1. **Naming parity** — builders who type `@desc`, `@name`, `@chown`, `@dig`, `@open`, `@link`, `@lock`, `@set` should find them working as expected.
2. **Workflow parity** — the build-test-iterate cycle should feel familiar. Dig a room, describe it, link exits, set properties, test by walking through.
3. **Feature parity for non-softcode features** — places, mail, page, finger, where, emit-to-player.
4. **Extensibility without softcode** — provide a clean mechanism for admin-defined custom behaviors (event hooks, custom messages, simple scripting) that doesn't require Python.

### 4.2 Tier 1: Command Aliases & Naming (LOW EFFORT, HIGH FAMILIARITY)

Make existing commands respond to TinyMUX names:

| TinyMUX Name | Our Command | Action |
|-------------|-------------|--------|
| `@desc` | `@describe` | Add alias |
| `@tel` | `@teleport` | Already aliased |
| `look` / `l` | `look` | Already works |
| `say` / `"` | `say` | Already works |
| `pose` / `:` | `emote` | Add `pose` alias, `:` prefix |
| `@emit` | `@emit` | Already works |
| `page` | `whisper` → needs new impl | Cross-game messaging (see §4.4) |
| `WHO` | `who` | Already works |
| `QUIT` | `quit` | Already works |
| `@find` | `@find` | Already works |
| `@entrances` | `@entrances` | Already works |

### 4.3 Tier 2: Missing Builder Commands (MEDIUM EFFORT)

New commands to implement:

**@name <target> = <new name>** — Rename a room, exit, or object. Straightforward DB update.

**@chown <target> = <player>** — Transfer ownership. Requires ownership concept on rooms/exits (we have `owner_id` on objects but not rooms).

**@clone <target>** — Duplicate an object (deep copy the JSON data blob). Essential for builders creating multiples of the same item.

**@wall <message>** — Broadcast to all connected players. Easy — iterate `session_mgr.sessions`.

**@pemit <player> = <message>** — Emit raw text to a specific player, anywhere on the game. Different from `whisper` (which is room-local and visible to others).

**@force <player> = <command>** — Admin-only: make a player/NPC execute a command. Useful for testing and scripting NPC behavior.

**@newpassword <player> = <password>** — Admin password reset. Important for game ops.

**@shutdown** — Graceful server shutdown from in-game. Admin-only.

**@decompile <target>** — Dump an object/room as a series of `@create`/`@set`/`@desc` commands that could recreate it. Extremely useful for backup/copy/share workflows.

### 4.4 Tier 3: Communication Features (MEDIUM EFFORT, HIGH IMPACT)

**Page system:**
```
page <player> = <message>
page <player1> <player2> = <message>   (multi-page)
```
Cross-game private messaging. Stored as `lastpaged` for quick reply (`page <message>` to last target). This is *the* most-used command on any MU\* after `say` and `pose`.

**+finger system:**
```
+finger <player>
&fullname me = Han Solo
&position me = Smuggler
```
Player info display card. In TinyMUX this is softcoded; we should build it as a first-class feature with predefined fields (Full Name, Species, Faction, Short-Desc, Position, RP-Prefs, Quote) plus user-defined fields.

**+where:**
Show all findable connected players and their locations. We have `who` but it doesn't show location for non-admin players.

**Mutter:**
```
mutter <player> = <message with "quoted" parts>
```
Partial overheard speech — quoted portions are visible to the room, the rest becomes `...`. Adds RP texture.

### 4.5 Tier 4: The Places System (MEDIUM EFFORT, HIGH RP VALUE)

Implement sub-locations within rooms:

```
configure 4 places              (admin: set up 4 "spots" in this room)
update 1/name = Corner Booth    (admin: name spot #1)
update 1/maxplaces = 4          (admin: max 4 people)
join 1                          (player: sit at Corner Booth)
tt Hey, keep your voice down.   (table-talk: only booth members see full text)
depart                          (stand up and leave the spot)
places                          (list all spots in the room)
```

Implementation: A `room_places` table with room_id, place_number, name, max_occupants, current occupants (JSON array of char_ids), and custom messages (join_msg, depart_msg, prefix).

### 4.6 Tier 5: Attribute System (HIGH EFFORT, STRATEGIC DECISION)

This is the biggest architectural decision. Full TinyMUX attribute compatibility would mean:

```sql
CREATE TABLE object_attributes (
    id          INTEGER PRIMARY KEY,
    object_type TEXT NOT NULL,     -- 'room', 'exit', 'object', 'character'
    object_id   INTEGER NOT NULL,
    attr_name   TEXT NOT NULL,
    attr_value  TEXT NOT NULL,
    attr_flags  INTEGER DEFAULT 0,
    owner_id    INTEGER,
    UNIQUE(object_type, object_id, attr_name)
);
```

With this table:
- `@set here/WEATHER = A dust storm howls outside` works on rooms
- `&MY_DATA object = some value` works on objects
- `@decompile` can dump everything
- `+finger` fields become attributes on the player

**This is recommended** as a longer-term investment. It doesn't need to support softcode evaluation — just storage and retrieval of key-value pairs on any game object. The `@set`, `@get` (or `examine`), and `@wipe` commands become powerful when they work against this store.

### 4.7 Tier 6: Event Hooks (LOWER PRIORITY, HIGH EXTENSIBILITY)

Instead of softcode, provide a **hook system** where admins can attach predefined behaviors to objects and rooms:

```
@hook here/AENTER = emit The door creaks shut behind %N.
@hook here/ADESC = emit The room feels watched.
@hook exit/ASUCC = emit %N slips through the doorway.
```

Supported hook events: AENTER (after enter room), ALEAVE (after leave), ADESC (after look), ASUCC (after successful exit traverse), AFAIL (after failed exit), ACONNECT (player connects), ADISCONNECT (player disconnects).

Hook actions: `emit <text>`, `pemit <player> <text>`, `trigger_ambient <event_key>`. Substitutions: `%N` (name), `%S` (subject pronoun), `%O` (object pronoun), `%P` (possessive).

This gives builders 80% of what they use `@action` lists for in TinyMUX, without a programming language.

---

## 5. Implementation Priority

### Phase 1: Immediate Builder Comfort (1-2 Sonnet sessions)
- [ ] Tier 1: Command aliases (`@desc`, `pose`/`:`, etc.)
- [ ] Tier 2: `@name`, `@wall`, `@pemit`, `@shutdown`, `@newpassword`
- [ ] Tier 3: `page` command (cross-game private messaging)

### Phase 2: RP Infrastructure (2-3 Sonnet sessions)
- [ ] Tier 3: `+finger` system, `+where`, mutter
- [ ] Tier 4: Places system
- [ ] Tier 2: `@clone`, `@force`, `@decompile`

### Phase 3: Extensibility Layer (2-3 Sonnet sessions)
- [ ] Tier 5: Universal attribute system
- [ ] Tier 2: `@chown` (requires ownership on rooms/exits)
- [ ] Tier 6: Event hooks (AENTER, ALEAVE, ADESC, ASUCC, AFAIL)

### Phase 4: Polish (1 session)
- [ ] `@mail` system
- [ ] Compound locks (AND/OR/NOT expressions)
- [ ] `@decompile` with full attribute dump

---

## 6. What We Should NOT Port

**MUSHcode interpreter.** The softcode language is TinyMUX's defining feature but also its greatest liability. 510 functions, nested evaluation, %-substitution, register variables — this is thousands of hours of work for an arcane language. Our extensibility story should be hooks + Python plugins, not a MUSHcode clone.

**The unified object model.** Our relational model is better for a game with typed entities (ships, NPCs, characters). Shoehorning everything into "dbref with attributes" would regress our architecture. The attribute system (Tier 5) gives us the extensibility benefits without abandoning type safety.

**Pennies/money as an object attribute.** TinyMUX stores wealth as `A_MONEY` on the player object. Our credit system is properly tracked through a relational ledger with credit_log, which is far superior for economy auditing.

**Object quotas.** TinyMUX limits how many objects each player can create. Not relevant for our architecture where only builders create rooms/exits and game items are managed by engine systems.

**WoD Realms / Reality Levels.** TinyMUX has an elaborate reality-layer system for World of Darkness games. Interesting but completely wrong for Star Wars.

---

## 7. Takeaways for Existing Systems

Beyond porting, the TinyMUX review suggests a few improvements to existing SW_MUSH systems:

**Cron/scheduler visibility.** TinyMUX has `@cron` and `@ps` so admins can see what's scheduled. Our `tick_scheduler` works but has no admin visibility command. We should add `@ps` or `@scheduler` to show running tick handlers, intervals, and next-fire times.

**Room flags formalization.** Our `@set` stores arbitrary JSON. TinyMUX has well-defined flags (DARK, FLOATING, JUMP_OK, LINK_OK, etc.) with documented behaviors. We should define and document our room flag vocabulary: `dark` (hidden from +where), `no_combat` (safe zone), `no_shout` (sound isolation), `jump_ok` (teleport permitted), `outdoor`/`indoor`, etc.

**Exit messages.** TinyMUX has `@succ`, `@osucc`, `@fail`, `@ofail`, `@drop`, `@odrop` — messages shown to the mover, to the room they left, and to the room they arrived in. We have `@success` and `@fail` but not the "others" variants (`@osucc`: "Han walks north.", `@ofail`: "Han tries the door but it's locked."). Adding these would significantly improve RP immersion.

**ANSI color in builder text.** TinyMUX lets descriptions use `%ch` (highlight), `%cn` (normal), `%cr` (red), etc. Our ANSI module supports colors but builders can't use them in `@describe` text. Supporting a simple color tag syntax in descriptions (e.g., `{red}Warning!{/}`) would let builders create more vivid rooms.

---

## 8. Architecture Doc Changes

When this work proceeds, update the architecture document with:

- **New section: §24 MU\* Compatibility Layer** — documents which TinyMUX features are supported, command aliases, the attribute system, event hooks
- **Modified: §3.4 Database Layer** — add `object_attributes` and `room_places` tables
- **Modified: §3.3 Command Parser** — document alias resolution and the `:` prefix for poses
- **New: §25 Places System** — sub-location mechanics
- **New: §26 Page & Mail** — cross-game communication
