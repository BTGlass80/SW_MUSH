# Ollama Idle Queue — Design Document v1

## Problem Statement

The RTX 3070 running Mistral 7B via Ollama is idle 95%+ of the time. NPC dialogue only fires when a player explicitly types `talk <npc>`, which might happen a few times per hour in a live population. Meanwhile, Haiku (Claude API) handles Director faction turns and narrative summarization — already budget-tracked and rate-limited. The local GPU is effectively wasted.

The world feels static between player interactions. NPCs stand silently until addressed. Room descriptions are player-written (often minimal). Director events use template text. Scene summaries don't exist until the nightly Haiku run.

## Design Goals

1. **Use Ollama during idle time** to pre-generate content that enriches the world
2. **Never interfere with player-initiated requests** — player `talk` commands always take priority
3. **Fail gracefully** — if Ollama is down or overloaded, the game is unchanged
4. **Budget-neutral** — all idle work runs on local Mistral, never Haiku

## Architecture

### Core: `engine/idle_queue.py`

A priority-aware async work queue that feeds Ollama tasks during idle ticks.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Tick Handler │────▶│  Idle Queue  │────▶│   Ollama     │
│  (every 30s) │     │  (priority)  │     │  (Mistral)   │
└──────────────┘     └──────────────┘     └──────────────┘
                           │                     │
                     ┌─────┴──────┐        ┌─────┴──────┐
                     │ Task Types │        │   Cache    │
                     │ • ambient  │        │   Tables   │
                     │ • scene    │        │ • npc_bark │
                     │ • event    │        │ • event_tx │
                     │ • desc     │        │ • desc_sug │
                     └────────────┘        └────────────┘
```

### Priority System

| Priority | Type | Preempts idle? |
|----------|------|----------------|
| 0 (highest) | Player `talk <npc>` | Always — not in queue, goes direct |
| 1 | Scene summary (player just ran `+scene/stop`) | Yes |
| 2 | NPC ambient barks | No |
| 3 | Director event rewrite | No |
| 4 | Housing description suggestion (pre-gen) | No |

Player-initiated requests (priority 0) never enter the queue — they go direct to Ollama as they do today. The idle queue only processes priority 1+ tasks.

### Contention Prevention

The key invariant: **idle tasks must never block player dialogue.**

```python
class IdleQueue:
    def __init__(self, ai_manager: AIManager):
        self._queue: list[IdleTask] = []  # sorted by priority
        self._busy = False                # True while an idle task is in-flight
        self._ai = ai_manager

    async def try_process_one(self, db) -> bool:
        """Called by tick handler. Returns True if a task was processed."""
        if self._busy:
            return False
        if not self._queue:
            return False

        # Check if Ollama is likely free — no player requests in last 5s
        if self._last_player_request and (time.time() - self._last_player_request) < 5.0:
            return False

        task = self._queue.pop(0)
        self._busy = True
        try:
            await task.execute(self._ai, db)
        except Exception as e:
            log.warning("[idle_queue] Task %s failed: %s", task.task_type, e)
        finally:
            self._busy = False
        return True

    def notify_player_request(self):
        """Called by npc_brain before every player-initiated generate().
        Updates the last-request timestamp so idle tasks back off."""
        self._last_player_request = time.time()
```

The `notify_player_request()` call is the critical integration point. It goes into `NPCBrain.generate_response()` right before the `self.ai.generate()` call. This ensures the idle queue backs off for at least 5 seconds after any player dialogue, giving the GPU time to unload the idle task context and respond to the player.

### Tick Handler

```python
# server/tick_handlers_economy.py

async def idle_queue_tick(ctx: TickContext) -> None:
    """Process one idle AI task if Ollama is free. Runs every 30 ticks."""
    queue = getattr(ctx.server, '_idle_queue', None)
    if not queue:
        return
    await queue.try_process_one(ctx.db)
```

Registered at interval=30 (every 30 seconds), offset=15 (avoid piling on with other handlers).

---

## Task Types

### Task 1: NPC Ambient Barks

**What:** Pre-generate 5-8 contextual one-liners per NPC that fire when players enter the room or pass through. Stored in an in-memory cache, rotated through, and refreshed daily.

**Why:** NPCs currently stand silent unless directly addressed. Ambient barks make Mos Eisley feel alive — the bartender muttering about the stormtroopers, a bounty hunter sizing up newcomers, a Jawa chittering about salvage.

**Prompt:**

```
You are {npc_name}, a {species} {role} in {room_name}.
Personality: {personality}
Faction: {faction}
Zone atmosphere: {zone_tone}

Generate 5 short ambient lines this character might mutter, announce,
or say to no one in particular while going about their business.
Each line should be 1 sentence, max 15 words. Vary the mood.
Do not address the player directly. Stay in character.

Output as a JSON array of strings, nothing else.
```

**Cache:** `dict[int, list[str]]` keyed by NPC ID. Each list is the bark pool. When a player enters a room with a barking NPC, one is selected at random and displayed as:

```
Wuher mutters, "Another day, another spilled drink on my counter."
```

**Display rules:**
- Max 1 bark per room entry per NPC (don't spam)
- 30-second cooldown per NPC per player (don't repeat on re-entry)
- Only fire for NPCs with `ai_config.enabled = true`
- Only fire when the NPC has a personality string (skip generic guards)
- Barks are flavor text — no game mechanical content

**Refresh:** Queue refill tasks for all populated rooms every 4 hours. Each NPC refill is a separate queue entry (don't batch 33 NPCs into one massive request). Estimated load: 33 NPCs × 1 request every 4 hours = ~8 requests/hour = one every ~7 minutes. Well within Mistral's capacity.

**Schema:** None — pure in-memory cache. Lost on restart, regenerated automatically within 30 minutes of boot (queue seeded on startup for rooms with online players).

### Task 2: Scene Summary Generation

**What:** After a player runs `+scene/stop`, queue the scene's poses for Ollama to generate a 2-3 sentence narrative summary. Stored in the `scenes` table `summary` column (which exists but is currently always NULL).

**Why:** Scene summaries are valuable for the web portal (`/scenes` page), for the Director AI's context, and for players reviewing past RP. Currently the nightly Haiku summarization handles character records, but individual scene summaries don't exist.

**Prompt:**

```
Summarize this Star Wars roleplay scene in 2-3 sentences.
Focus on what happened, who was involved, and the outcome.
Write in past tense, third person. Be concise.

Scene location: {room_name}
Participants: {participant_names}

--- SCENE POSES ---
{poses_text}
---

Output only the summary, no preamble.
```

**Trigger:** When `+scene/stop` fires, instead of running Ollama synchronously (which would freeze the player's session for 5-15 seconds), push a task to the idle queue. The summary appears in the scene record within 30-60 seconds.

**Token budget:** Scenes can be long. Cap input at the last 30 poses (or ~3000 tokens of pose text). Mistral 7B handles this comfortably at 4-bit quantization on 8GB VRAM.

**Schema change:** None — `scenes.summary` column already exists (TEXT DEFAULT NULL).

### Task 3: Director Event Flavor Text

**What:** When the Director generates a template-based news headline (the local fallback when Haiku is unavailable or between faction turns), queue the headline for Ollama to rewrite with more variety and atmosphere.

**Current:** `"Imperial patrols increase in Mos Eisley"` (template)
**After:** `"Stormtrooper squads spotted conducting house-to-house searches near the Cantina district"` (Ollama rewrite)

**Prompt:**

```
Rewrite this Star Wars news headline to be more vivid and specific.
Keep the same meaning but add atmospheric detail.
One sentence, max 20 words. No quotes.

Zone: {zone_name}
Zone atmosphere: {zone_tone}
Original: {headline}

Output only the rewritten headline.
```

**Cache:** Replace the headline in the Director's event log and re-broadcast to web clients. If Ollama fails, the original template headline stands.

**Frequency:** Director faction turns happen every ~15 minutes. At most 1 rewrite per turn = 4/hour.

### Task 4: Housing Description Pre-generation

**What:** When a player purchases a new home (any tier), queue a description suggestion for Ollama to generate. Store it so that when the player opens `housing describe`, the `.suggest` command returns instantly from cache instead of hitting Haiku.

**Why:** This moves the AI description generation from Haiku (costs money) to Ollama (free, local). The `.suggest` command currently calls Haiku. With the idle queue, it checks the Ollama cache first and only falls back to Haiku if the cache is empty.

**Trigger:** `purchase_home()`, `purchase_shopfront()`, `purchase_hq()`, `assign_faction_quarters()` — all push a description task to the queue after purchase.

**Cache:** `dict[int, str]` keyed by housing ID. Cleared when the player saves a description (they wrote their own or accepted the suggestion). Persists in memory only.

---

## Integration Points

### 1. NPC Brain — Player Request Notification

```python
# ai/npc_brain.py — inside generate_response(), before the AI call

# Notify idle queue that a player request is about to happen
idle_queue = getattr(self.ai, '_idle_queue', None)
if idle_queue:
    idle_queue.notify_player_request()
```

This is the critical contention-prevention hook. The idle queue backs off for 5 seconds after this fires.

### 2. Game Server — Queue Initialization

```python
# server/game_server.py — in __init__() after ai_manager creation

from engine.idle_queue import IdleQueue
self._idle_queue = IdleQueue(self.ai_manager)
self.session_mgr._idle_queue = self._idle_queue
# Also expose on ai_manager for npc_brain access
self.ai_manager._idle_queue = self._idle_queue
```

### 3. Movement Hook — Ambient Bark Trigger

```python
# parser/builtin_commands.py — MoveCommand, after auto-look

# Fire ambient bark for NPCs in the new room
idle_queue = getattr(ctx.session_mgr, '_idle_queue', None)
if idle_queue:
    bark = idle_queue.get_random_bark(room_id, char_id)
    if bark:
        await ctx.session.send_line(bark)
```

### 4. Scene Stop — Summary Queue

```python
# parser/scene_commands.py — in +scene/stop handler, after the scene is closed

idle_queue = getattr(ctx.session_mgr, '_idle_queue', None)
if idle_queue:
    idle_queue.enqueue_scene_summary(scene_id, room_name, participants, poses)
```

### 5. Housing Describe — Cache Check

```python
# parser/housing_commands.py — in _ai_suggest_description()

# Check Ollama cache first (free, instant)
idle_queue = getattr(ctx.session_mgr, '_idle_queue', None)
if idle_queue:
    cached = idle_queue.get_cached_description(housing_id)
    if cached:
        # Display cached suggestion instead of calling Haiku
        ...
        return
# Fall through to Haiku call (existing code)
```

---

## Load Analysis

### GPU Budget

Mistral 7B on RTX 3070 8GB (4-bit quantization):
- Inference time: ~2-5 seconds per request (150 tokens output)
- Memory: ~4.5GB VRAM (leaves headroom for context)
- Throughput: ~12-20 requests per minute if running flat out

### Expected Idle Load

| Task | Frequency | Tokens/request | Daily total |
|------|-----------|----------------|-------------|
| Ambient barks | 8/hr (33 NPCs ÷ 4hr cycle) | ~200 out | ~38K tokens |
| Scene summaries | 2-5/day (depends on RP activity) | ~300 out | ~1.5K tokens |
| Event rewrites | 4/hr | ~40 out | ~3.8K tokens |
| Housing descriptions | 1-3/day | ~200 out | ~600 tokens |

**Total: ~44K tokens/day output.** At Mistral's ~30 tokens/second, that's about 25 minutes of actual GPU time spread across 24 hours. The GPU is still idle >98% of the time.

### Contention Risk

With the 5-second backoff after player requests and the 30-second tick interval, the worst case is:
1. Idle task starts (takes 3-5 seconds)
2. Player types `talk <npc>` during that window
3. Player waits up to 5 seconds for the idle task to finish, then their request runs immediately

This is acceptable — 5 seconds is within the "NPC is thinking" tolerance for a text game. And it only happens if a player talks to an NPC at the exact moment an idle task is running.

To further reduce this risk, we can add a `cancel_in_flight` mechanism that uses Ollama's `/api/generate` cancel endpoint, but this is optimization-over-engineering for launch. The 5-second backoff is sufficient.

---

## What NOT To Do

1. **Don't batch multiple NPCs into one Ollama request.** Mistral 7B handles single-NPC prompts well. Multi-NPC prompts produce lower quality and higher latency.

2. **Don't persist bark caches to disk.** They're cheap to regenerate and stale barks are worse than no barks. In-memory only, seeded on startup.

3. **Don't queue ambient barks for NPCs in empty rooms.** Only populate barks for rooms that have had players in the last hour. Check `session_mgr.sessions_in_room()` or a "room last visited" timestamp.

4. **Don't use the idle queue for time-critical content.** If a player needs AI output *now* (like `talk` or `.suggest`), that goes direct. The idle queue is for content that's nice-to-have within the next 30-60 seconds.

5. **Don't fire ambient barks for hostile NPCs in combat.** A Tusken Raider shouldn't be muttering atmospheric dialogue while trying to kill you.

---

## Implementation Plan

### Drop 1: Core + Ambient Barks (~4-6 hours)

| File | Changes |
|------|---------|
| `engine/idle_queue.py` | NEW — IdleQueue class, IdleTask base, AmbientBarkTask, bark cache |
| `server/tick_handlers_economy.py` | Add `idle_queue_tick` handler |
| `server/game_server.py` | Initialize IdleQueue, register tick handler |
| `ai/npc_brain.py` | Add `notify_player_request()` hook |
| `parser/builtin_commands.py` | Add bark display in MoveCommand |

### Drop 2: Scene Summaries (~2-3 hours)

| File | Changes |
|------|---------|
| `engine/idle_queue.py` | Add SceneSummaryTask |
| `parser/scene_commands.py` | Queue summary on `+scene/stop` |
| `engine/scenes.py` | Add `update_summary()` function |

### Drop 3: Director Event Rewrites (~2-3 hours)

| File | Changes |
|------|---------|
| `engine/idle_queue.py` | Add EventRewriteTask |
| `engine/director.py` | Queue rewrite after local headline generation |

### Drop 4: Housing Description Cache (~1-2 hours)

| File | Changes |
|------|---------|
| `engine/idle_queue.py` | Add HousingDescTask |
| `engine/housing.py` | Queue description on purchase |
| `parser/housing_commands.py` | Check cache before Haiku call |

---

## Architecture Doc Changes for v26

**New section: §21 Ollama Idle Queue**
- Queue architecture, priority system, contention prevention
- Task type registry with expected load
- Integration points (npc_brain, MoveCommand, scene_commands, director, housing)

**Modified: §8 NPC Brain**
- Add ambient bark display on room entry
- Add `notify_player_request()` contention hook

**Modified: §16A Scene Logging**
- Scene summary auto-generation via idle queue (async, not blocking)

**Modified: §13A Director AI**
- Event headline rewrite via idle queue when Haiku is unavailable

**Modified: §12 Housing**
- Description pre-generation via idle queue, Haiku as fallback

**New invariant: §18**
- "Idle queue tasks never block player-initiated AI requests. All player dialogue goes direct to Ollama, bypassing the queue. The queue backs off for 5 seconds after any player request."

---

*End of Ollama Idle Queue Design Document — Version 1.0*
*Reference: ai/providers.py, ai/npc_brain.py, engine/director.py, engine/narrative.py, server/tick_scheduler.py, competitive_analysis_feature_designs_v1.md*
