---
category: galaxy
order: 4
summary: "Locations, plots, scene archives, and the social fabric of the game world."
tags: ["scenes", "plots", "places", "locations", "rooms", "world"]
---

# Scenes, Plots & Places

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This guide covers the **RP infrastructure layer** of the game — the three systems that organize, archive, and structure player roleplay. Scenes log what happened in a room over time; plots tie scenes together into multi-session story arcs; places carve rooms into sub-locations (booths, tables, seats) for parallel conversations.

These systems don't drive what you RP — they're the **scaffolding** around what you and other players choose to create. They make RP archivable (you can read scenes later), discoverable (players can find your plot), and richer (a busy cantina can support five conversations simultaneously through places).

If you only have ten minutes, read **§1 What These Systems Do** and **§3 Scene Logging in Practice**. Most players use scenes; fewer use plots; and places are common in active social rooms.

This is a new guide. There was no earlier version.

---

## 1. What These Systems Do

Three systems that solve three different RP organization problems.

**Scenes** answer "what happened in this room while I was here?" They auto-log poses, actions, and dialogue while active. They produce a transcript you can later read, share, or archive. They give players who weren't present a way to catch up on a story.

**Plots** answer "what's the bigger story we're building?" They group multiple scenes into a narrative arc. A plot tracks who's involved, what the stakes are, and which scenes are part of it. Plots make multi-session storytelling discoverable — other players can browse open plots and decide whether to engage.

**Places** answer "how do five different conversations happen in one cantina at the same time?" They carve a single room into sub-locations (a corner booth, a window table, the bar, the back room). Players sit at places; speech can be place-only (table-talk) so conversations don't collide.

Together, the three layer up: places shape *how* RP happens within a room; scenes log *what* happens within a session; plots tie together *why* it matters across sessions.

---

## 2. The Three Systems at a Glance

| System | Scope | Lifespan | Main Use |
|---|---|---|---|
| **Scenes** | Within a single room | Active for a session; archived afterwards | Logging what happened |
| **Plots** | Across multiple rooms and sessions | Multi-week story arc | Organizing long-form narrative |
| **Places** | Within a single room | Persistent room feature | Parallel conversations |

Most players will routinely use **scenes** (any extended RP benefits from logging). Some players will create or join **plots** (story-heavy players, faction leaders, plotrunners). **Places** are room-level — they're a builder feature you opt into when a room has them.

---

## 3. Scene Logging in Practice

The scene system **auto-logs** what happens in a room from the moment you start a scene until you end it. The log captures poses (your `:` actions), dialogue (`"` and `say`), and most meaningful actions. You can review the log later, share it with other players, or send it to the public archive.

### Starting a scene

```
+scene/start [title]
```

Begins a scene in your current room. The optional title is the scene's name. If you don't provide one, it defaults to the room name plus the timestamp.

When a scene starts:
- The scene is **active** in this room.
- Anyone in the room (including new arrivals) is automatically a participant.
- Poses, dialogue, and significant actions are auto-logged.
- The scene shows up in `+scenes` for participants and on the public scene list (after you mark it shared).

### Setting scene metadata

While the scene runs, you can update its title, type, and summary:

```
+scene/title <text>      — Rename the active scene
+scene/type <type>       — Set scene type
+scene/summary <text>    — Set a brief summary
```

**Scene types** classify what kind of RP is happening:

| Type | Use |
|---|---|
| **Social** | Casual conversation, character interaction, relationship-building |
| **Action** | Combat, chase, escape, intense physical scene |
| **Plot** | Connected to a larger plot arc |
| **Vignette** | Short, focused, possibly solo or two-person |

The type is for discoverability — players browsing the scenes list can filter by type. A character-focused player might browse Social scenes; an action-RP player might browse Action.

**Scene summary** is your one-paragraph description. Used in the scenes list and when other players are deciding whether to read the full transcript.

### Ending a scene

```
+scene/stop
```

Ends the active scene. The log is finalized; the scene transitions from `active` to `completed`. The log is now archived (private to participants by default) and viewable via `+scene <id>`.

### Sharing a scene

```
+scene/share              — Share the most recent completed scene
+scene/share <id>         — Share a specific scene
+scene/unshare [id]       — Revert to private
```

Sharing moves a completed scene to the **public archive**. Anyone can browse and read shared scenes via `+scenes`. This is how memorable RP becomes part of the server's culture — other players can find your great cantina scene from last week, read it, and reference it.

Most players share their best scenes (memorable moments, important plot beats, particularly well-written exchanges). Routine RP can stay private. The choice is yours.

### Browsing scenes

```
+scenes                  — List recent scenes (yours + public)
+scenes shared           — List public shared scenes
+scenes plot             — List Plot-type scenes
+scenes <player>         — Scenes by a specific player
+scene <id>              — View a scene's log
```

The browse-and-read flow is how players engage with the archive. Newer players can read shared scenes to understand the server's RP culture; established players can revisit their own scene history for character continuity.

### What gets logged

The scene log captures:
- **Poses** (`:does something`, `;jumps`, `.is thinking`).
- **Dialogue** (`"says something"`, `say x`).
- **Notable actions** (combat resolutions, skill check results, important system events).
- **Arrivals and departures** (so the cast is clear).

What does **not** get logged:
- OOC commands (helpfile lookups, system queries).
- Channel chatter (faction, OOC, etc. — different system).
- Private pages (whispered messages between two characters).
- Mechanical commands (combat dice rolls, inventory checks).

The log is the **public-facing scene** — what a observer in the room would have seen. Private/OOC stays out of the record.

---

## 4. Plots

Plots are **multi-scene story arcs**. They give your story discoverable continuity.

### Creating a plot

```
+plot/create <title>=<summary>
```

Creates a new open plot with a title and summary. The summary is one paragraph — what the plot is about, who's involved, what the stakes are.

Example:
```
+plot/create The Hutt Debt Collection=A faction of Hutt enforcers is pursuing
captain Trill Sethka for an unpaid debt. The arc will play out across
Tatooine, Nar Shaddaa, and possibly Kessel over several sessions.
```

The plot is now public. Other players can see it via `+plots`.

### Listing and viewing plots

```
+plots                          — List open plots
+plot <id>                      — View plot details + linked scenes
```

The `+plots` list shows open plots with their summaries. Players browsing for RP opportunities can find plots they want to engage with.

The `+plot <id>` detail view shows the plot's title, summary, status (open/closed), creation date, and a list of all scenes linked to it.

### Linking scenes to plots

```
+plot/link <plot_id>=<scene_id>          — Link a scene
+plot/unlink <plot_id>=<scene_id>        — Unlink a scene
```

After running a scene, you can link it to a plot. This builds the arc's transcript — anyone viewing the plot sees all the scenes connected to it in chronological order.

Most plot-runners link every scene that's part of the arc. A 5-scene plot becomes a 5-chapter story with full session transcripts.

### Closing and reopening

```
+plot/close <id>                 — Close a completed plot
+plot/reopen <id>                — Reopen a closed plot
```

Closing marks the plot as **resolved**. The story arc concluded. The plot remains in the archive but no longer appears on the active `+plots` list.

Reopening can happen if a story unexpectedly continues — a "completed" plot revives, becomes active again.

### Updating the summary

```
+plot/summary <id>=<text>
```

Updates the plot's summary text. Useful as the arc evolves — the original summary may have been vague; mid-arc, you can update it to reflect what's actually been happening.

---

## 5. Plots in Practice

A typical multi-session plot arc:

**Session 1.** A medic in the cantina overhears chatter about a missing Republic supply convoy. She investigates with two players. The scene runs 30 minutes. She ends the scene, names it "Missing Supply Convoy — investigation begins," summary: "An informant claims a supply convoy bound for the Republic outpost on Kessel disappeared. Initial inquiries point to Hutt involvement."

She creates a plot: `+plot/create The Lost Convoy=A Republic supply convoy bound for Kessel has vanished. The arc will follow attempts to recover it across Tatooine, Nar Shaddaa, and possibly Kessel.` She links the scene: `+plot/link 14 = 87`.

**Sessions 2-4.** Other players see the plot in `+plots` and join. Each session runs a scene that advances the arc. Each scene is linked to the plot. The plot's scene list grows: 1, 2, 3, 4.

**Session 5.** Resolution. The convoy is found (or destroyed, or rescued — the players have agency). The final scene runs. It's linked to the plot. The plot is closed: `+plot/close 14`.

Now the plot exists as a 5-scene narrative arc in the archive. New players months later can browse `+plots` (filtered to closed), find "The Lost Convoy," read all five linked scenes in order, and understand the entire story.

This is the **persistence of player narrative**. Without plots, the story would have happened in five disconnected scenes. With plots, it's a discoverable, archived story arc that contributes to the server's lore.

---

## 6. Places

Places turn a single room into multiple sub-locations. A cantina with places might have:

- **Corner Booth** (4 seats, dim, private feel)
- **Window Table** (3 seats, public, near the door)
- **Bar** (4 stools, social, near the bartender)
- **Back Alcove** (2 seats, secretive)

Each place is its own "where" within the room. Players can sit at a place. Talking at a place can be **table-talk** — heard only by other players at the same place. Multiple conversations can run in parallel without crashing into each other.

### Using places

```
places                       — List places in the current room
join <#|name>                — Sit at a place
depart                       — Leave your current place (alias: stand)
tt <message>                 — Table-talk: speak only to your place
ttooc <message>              — OOC table-talk
mutter <message>             — Whisper to one player at your place
```

The `places` command shows what's available in the current room. You'll see something like:

```
Places in this room:
1. Corner Booth (4 seats — 2 occupied: Trill, Mara)
2. Window Table (3 seats — empty)
3. Bar (4 stools — 1 occupied: Kessa)
4. Back Alcove (2 seats — empty)
```

You `join 1` (or `join corner booth`) to sit. Anyone in the room knows you sat down — but conversation at your place is mostly private to other players at that place.

### Table-talk vs. room-talk

While at a place, you have two speech modes:

- **`say`** (room-talk): Heard by everyone in the room, place or no place.
- **`tt`** (table-talk): Heard only by other players at your place.

This is the parallel-conversation magic. In a busy cantina:
- Trill and Mara at the Corner Booth are having a private conversation via `tt`.
- Kessa at the Bar is loudly grumbling via `say` — everyone hears her, including the booth and table players.
- Players at the Window Table are having their own `tt` conversation, unaware of the specifics of what Trill and Mara are discussing.

Each conversation runs independently. The room can support 3-5 simultaneous conversations comfortably. Without places, all these conversations would collide into one noisy mess.

### `ttooc` and `mutter`

**`ttooc`** is OOC table-talk — for asking questions or coordinating mechanics within your place's conversation circle. Useful when you need to clarify something OOC without disrupting the room.

**`mutter`** is a one-on-one whisper to a specific player at your place — even more private than `tt`. For intimate or conspiratorial exchanges.

### Place prefixes

Some places have a **prefix** that decorates your poses:

```
Trill: At the booth, Trill leans forward and whispers.
Mara: At the booth, Mara nods slowly.
```

The prefix ("At the booth,") is set by the builder and signals to other room members that the action is happening at the booth specifically. Players at the bar might not literally see Trill's actions, but they can see *that* Trill is at the booth and somehow active there.

### When places are configured

Not every room has places. Builders add them where social RP benefits from sub-locations. Typical places-rooms:
- Cantinas and bars.
- Hotel lobbies and reception areas.
- Group dining rooms.
- Large gathering halls.
- Some hub-style rooms in major cities.

If you enter a room and `places` returns nothing, the room has no places — RP happens at the room level, with `say` going to everyone.

---

## 7. How These Systems Compose

The three systems compose naturally:

**A typical heavy-RP session:**

1. You enter the Mos Eisley Cantina. `places` shows 4 sub-locations.
2. You `join Bar` to sit with two other players already there.
3. The conversation starts. You `tt` to chat privately with the bar crew.
4. Someone realizes the conversation is great and starts a scene: `+scene/start Late Night at the Bar`.
5. The scene auto-logs the bar's conversation (poses, `say`, `tt` poses — depending on logging mode).
6. Other players enter, join the bar, are auto-included in the scene.
7. The conversation goes for an hour. Someone says, "this should be part of the Convoy plot."
8. The scene is ended: `+scene/stop`.
9. It's linked to the existing plot: `+plot/link 14 = 92`.
10. It's shared publicly: `+scene/share 92`.

Now the scene exists in the archive, attached to a plot, with the place context preserved. Future players can read it; the plot gains another chapter; the cantina remains the rich social space it was during the session.

This is the system at its best — **three layers working together**, each adding richness, none requiring you to think about them mechanically while you're RP'ing.

---

## 8. Builders and Place Configuration

Players who own shopfront rooms or are working as part of city-building can configure places in their own rooms.

### Configuring places

```
@places <count>                          — Configure N places in this room
@places/clear                            — Remove all places
@place <#>/<field>=<value>               — Set place properties
```

**Fields:**
- `name` — display name ("Corner Booth")
- `max` — seat capacity
- `desc` — description shown when looking at the place
- `prefix` — pose decoration ("At the booth")

A builder would set up a 4-place cantina with:

```
@places 4
@place 1/name=Corner Booth
@place 1/max=4
@place 1/desc=A dimly lit booth in the corner.
@place 1/prefix=At the booth

@place 2/name=Window Table
@place 2/max=3
@place 2/desc=A small table near the cantina windows.
@place 2/prefix=At the window table

@place 3/name=Bar
@place 3/max=4
@place 3/desc=The long bar runs the length of the back wall.
@place 3/prefix=At the bar

@place 4/name=Back Alcove
@place 4/max=2
@place 4/desc=A hidden alcove behind a beaded curtain.
@place 4/prefix=In the alcove
```

The room now has 4 sub-locations. Players can `places` to see them and `join` to sit.

### Exit messages

Builders can also customize exit messages for departures and arrivals:

```
@osucc <dir>=<msg>     — Others-success message (seen by departure room)
@ofail <dir>=<msg>     — Others-fail message (seen on lock failure)
@odrop <dir>=<msg>     — Others-arrive message (seen by destination room)
```

This is the cantina-builder's tool for atmosphere. Instead of "Trill leaves north," you can show "Trill saunters out toward the bar." Same mechanics, richer narrative texture.

---

## 9. Player Commands Quick Reference

### Scene commands

| Command | What it does |
|---|---|
| `+scene/start [title]` | Start a scene in this room |
| `+scene/stop` | End the active scene |
| `+scene/title <text>` | Rename the active scene |
| `+scene/type <type>` | Set scene type (Social/Action/Plot/Vignette) |
| `+scene/summary <text>` | Set scene summary |
| `+scene/share [id]` | Share a scene publicly |
| `+scene/unshare [id]` | Revert to private |
| `+scenes` | List recent scenes |
| `+scene <id>` | View a scene's log |

### Plot commands

| Command | What it does |
|---|---|
| `+plots` | List open plots |
| `+plot <id>` | View plot details + linked scenes |
| `+plot/create <title>=<summary>` | Create a new plot |
| `+plot/summary <id>=<text>` | Update plot summary |
| `+plot/link <plot_id>=<scene_id>` | Link a scene to a plot |
| `+plot/unlink <plot_id>=<scene_id>` | Unlink a scene |
| `+plot/close <id>` | Close a completed plot |
| `+plot/reopen <id>` | Reopen a closed plot |

### Places commands (player)

| Command | What it does |
|---|---|
| `places` | List places in this room |
| `join <#\|name>` | Sit at a place |
| `depart` (alias `stand`) | Leave your current place |
| `tt <message>` | Table-talk (place-only speech) |
| `ttooc <message>` | OOC table-talk |
| `mutter <player> <message>` | Private whisper to one place-mate |

### Places commands (builder)

| Command | What it does |
|---|---|
| `@places <count>` | Configure N places in this room |
| `@places/clear` | Remove all places |
| `@place <#>/<field>=<value>` | Set place properties (name/max/desc/prefix) |
| `@osucc <dir>=<msg>` | Set others-success exit message |
| `@ofail <dir>=<msg>` | Set others-fail exit message |
| `@odrop <dir>=<msg>` | Set others-arrive exit message |

---

## 10. The Worked Scenarios

Five concrete pictures.

**Scenario 1 — Casual cantina chat with places.** You walk into Mos Eisley Cantina. `places` shows the Bar (3 occupied), Corner Booth (empty), and Window Table (empty). You sit at the Bar via `join Bar`. You `tt Hi all` — the players at the bar see your greeting; the rest of the cantina (in other places or in the room generally) doesn't. You chat for 20 minutes through table-talk. The conversation stays at the bar.

**Scenario 2 — A scene that becomes part of a plot.** You're RP'ing a meeting between two faction agents in the cantina. After 10 minutes you realize this should be logged: `+scene/start Cantina Meeting — Republic Intel Drop`. The scene runs another hour. You end it: `+scene/stop`. You realize it's part of the broader plot you've been running: `+plot/link 7 = 142`. Now the meeting is part of "The Convoy Investigation" plot's archive.

**Scenario 3 — Browsing for plots.** You're a new player looking for an RP entry point. You type `+plots`. You see three open plots: "The Lost Convoy," "Hutt Debt Collection," "Smuggler's Strike." You browse the summaries; the Convoy plot looks interesting. You read the scenes linked to it via `+plot 14`. You decide to introduce your character into the next session by asking the plot-runner if they need any additional players. The plot becomes your entry into the community.

**Scenario 4 — A parallel-conversation cantina.** It's a busy evening. The cantina has 12 players in it. Three are at the Corner Booth running an intimate conversation (`tt`); four are at the Bar arguing about politics (`tt` mostly, with occasional `say` outbursts); two are at the Window Table planning a smuggling job (`tt`); three are walking around unaffiliated, gossiping via `say`. All four conversations happen simultaneously. Without places, they'd collide.

**Scenario 5 — The archived legacy.** Months after your character first ran the "Convoy Investigation" plot, a new player joins the server. They browse `+plots closed` looking for inspiration. They find the Convoy arc. They read all 7 linked scenes in order. They reference the plot in their own character's backstory — "I was a Republic adjutant who heard about the Convoy investigation." The story you wrote months ago becomes part of someone else's character. That's the value of the archive.

---

## 11. Common Pitfalls

**1. Never starting a scene.** Many great RP exchanges go unlogged because no one started a scene. If you're more than 10 poses into a substantive conversation, start a scene — even mid-conversation. The log captures what happens after the start.

**2. Forgetting to share good scenes.** A scene that's never shared stays in the participants' archive only. Memorable scenes deserve the public archive — share them.

**3. Plot creep — adding too many scenes loosely.** A plot with 25 weakly-related scenes loses its narrative focus. Curate. If a scene isn't really part of the arc, don't link it.

**4. Talking in `say` when you should `tt`.** In a busy cantina, default speech is `say` (heard by everyone). If you're at a place and want a private conversation, you have to use `tt`. New players often forget and broadcast their private chat to the whole room.

**5. Creating duplicate plots.** Check existing plots before creating. Two plots covering similar arcs fragment the audience. Often the right move is to extend an existing plot rather than start a new one.

---

## 12. Numbers At A Glance

| Quantity | Value |
|---|---|
| Scene types | 4 (Social, Action, Plot, Vignette) |
| Scene states | active / completed / shared |
| Plot states | open / closed |
| Max places per room | unlimited (typically 2-8) |
| Max occupants per place | configurable (typically 2-6) |
| Auto-logged in scenes | poses, dialogue, notable actions, arrivals/departures |
| Not auto-logged | OOC commands, channel chatter, private pages, mechanics |
| Recent scenes list cap | 30 |
| Open plots list cap | 30 |

---

## 13. A Final Word

The Scenes, Plots, and Places systems are the **scaffolding around player creativity**. They don't tell you what to RP, who to RP with, or what story to tell. They just make it possible to log, organize, share, and parallel-process the RP that you're already creating.

For most players, the systems become **background tools**. You start scenes when something's worth logging. You share what's memorable. You sit at places without thinking about it. The systems are invisible while you're actually in the RP — they're not commands you're constantly issuing, they're features that quietly make the rest of the game richer.

For story-running players — plotrunners, GMs, faction leaders, anyone organizing multi-session arcs — these systems are the **production layer** for your work. Plots make your stories discoverable. Scene logs make your stories permanent. Places make your scenes happen in interesting environments.

If you're starting out: try the basic flow. Sit at a place (`join`) when one is available. When you're in a substantive scene, start it (`+scene/start`). End and share the ones that worked (`+scene/stop`, `+scene/share`). Browse `+plots` for engagement opportunities. By month 3, you'll be using all three systems without thinking about them. By month 6, you'll have a personal archive of memorable scenes and possibly your own plot arc.

That's the system at its best — invisible infrastructure that lets the actual RP shine.

---

*End of Guide #20 — Scenes, Plots & Places*
