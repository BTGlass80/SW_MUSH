# -*- coding: utf-8 -*-
"""
engine/idle_queue.py — Ollama Idle Queue for SW_MUSH.

Uses GPU idle time to pre-generate content via Mistral 7B:
  - NPC ambient barks (one-liners on room entry)
  - Scene summaries (after +scene/stop)
  - Director event rewrites (atmospheric headlines)
  - Housing description pre-generation

Key invariant: idle tasks NEVER block player-initiated dialogue.
Player `talk <npc>` commands go direct to Ollama, bypassing this queue.
The queue backs off for 5 seconds after any player request.

Design doc: ollama_idle_queue_design_v1.md
"""

from __future__ import annotations
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ai.providers import AIManager

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BACKOFF_SECONDS = 5.0       # Pause after player request before resuming idle work
BARK_REFRESH_HOURS = 4      # Regenerate barks every N hours
BARK_COOLDOWN_SECS = 30.0   # Per-NPC per-player cooldown between barks
MAX_BARKS_PER_NPC = 8       # Number of barks to pre-generate per NPC
MAX_QUEUE_SIZE = 200         # Hard cap on pending tasks


# ── Task Types ────────────────────────────────────────────────────────────────

@dataclass
class IdleTask:
    """Base class for idle queue tasks."""
    priority: int = 2
    task_type: str = "unknown"
    created_at: float = 0.0

    async def execute(self, ai: "AIManager", db) -> None:
        """Override in subclasses."""
        pass


@dataclass
class AmbientBarkTask(IdleTask):
    """Generate ambient one-liners for a single NPC."""
    priority: int = 2
    task_type: str = "ambient_bark"
    npc_id: int = 0
    npc_name: str = ""
    species: str = ""
    personality: str = ""
    faction: str = ""
    room_name: str = ""
    zone_tone: str = ""

    async def execute(self, ai: "AIManager", db) -> None:
        system_prompt = (
            f"You are {self.npc_name}, a {self.species} in a Star Wars setting.\n"
            f"Personality: {self.personality}\n"
            f"Faction: {self.faction}\n"
            f"Location: {self.room_name}\n"
        )
        if self.zone_tone:
            system_prompt += f"Atmosphere: {self.zone_tone}\n"
        system_prompt += (
            "\nGenerate 5 short ambient lines this character might mutter, "
            "announce, or say to no one in particular while going about "
            "their business. Each line should be 1 sentence, max 15 words. "
            "Vary the mood. Do not address the player directly. Stay in "
            "character.\n\n"
            "Output as a JSON array of strings, nothing else."
        )

        try:
            raw = await ai.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": "Generate the ambient lines now."}],
                max_tokens=250,
                temperature=0.85,
                json_mode=True,
                provider="ollama",
            )
            if not raw:
                return

            # Parse JSON array — handle markdown fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()

            barks = json.loads(cleaned)
            if isinstance(barks, list) and barks:
                # Filter: only keep strings, strip, limit length
                valid = [
                    s.strip().strip('"').strip("'")
                    for s in barks
                    if isinstance(s, str) and 3 < len(s.strip()) < 120
                ]
                if valid:
                    # Store in the queue's bark cache
                    _bark_cache[self.npc_id] = {
                        "barks": valid,
                        "generated_at": time.time(),
                        "npc_name": self.npc_name,
                    }
                    log.info(
                        "[idle_queue] Generated %d barks for %s (npc_id=%d)",
                        len(valid), self.npc_name, self.npc_id,
                    )
        except json.JSONDecodeError:
            log.debug("[idle_queue] Bark JSON parse failed for %s", self.npc_name)
        except Exception as e:
            log.warning("[idle_queue] Bark generation failed for %s: %s", self.npc_name, e)


@dataclass
class SceneSummaryTask(IdleTask):
    """Generate a summary for a completed scene."""
    priority: int = 1
    task_type: str = "scene_summary"
    scene_id: int = 0
    room_name: str = ""
    participants: str = ""
    poses_text: str = ""

    async def execute(self, ai: "AIManager", db) -> None:
        system_prompt = (
            "Summarize this Star Wars roleplay scene in 2-3 sentences. "
            "Focus on what happened, who was involved, and the outcome. "
            "Write in past tense, third person. Be concise. "
            "Output only the summary, no preamble."
        )
        user_msg = (
            f"Scene location: {self.room_name}\n"
            f"Participants: {self.participants}\n\n"
            f"--- SCENE POSES ---\n{self.poses_text}\n---"
        )

        try:
            summary = await ai.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=200,
                temperature=0.5,
                provider="ollama",
            )
            if summary and db:
                await db.execute(
                    "UPDATE scenes SET summary = ? WHERE id = ?",
                    (summary.strip(), self.scene_id),
                )
                await db.commit()
                log.info(
                    "[idle_queue] Scene %d summary generated (%d chars)",
                    self.scene_id, len(summary),
                )
        except Exception as e:
            log.warning("[idle_queue] Scene summary failed for scene %d: %s",
                        self.scene_id, e)


@dataclass
class EventRewriteTask(IdleTask):
    """Rewrite a Director template headline with atmospheric detail."""
    priority: int = 3
    task_type: str = "event_rewrite"
    event_id: int = 0
    headline: str = ""
    zone_name: str = ""
    zone_tone: str = ""
    session_mgr: object = None

    async def execute(self, ai: "AIManager", db) -> None:
        system_prompt = (
            "Rewrite this Star Wars news headline to be more vivid and specific. "
            "Keep the same meaning but add atmospheric detail. "
            "One sentence, max 25 words. No quotes. No preamble. "
            "Output only the rewritten headline."
        )
        user_msg = (
            f"Zone: {self.zone_name}\n"
        )
        if self.zone_tone:
            user_msg += f"Zone atmosphere: {self.zone_tone}\n"
        user_msg += f"Original: {self.headline}"

        try:
            rewrite = await ai.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=60,
                temperature=0.7,
                provider="ollama",
            )
            if not rewrite or len(rewrite.strip()) < 10:
                return  # Keep original

            rewrite = rewrite.strip().rstrip(".")
            # Update the director_log entry
            if db and self.event_id:
                await db.execute(
                    "UPDATE director_log SET summary = ? WHERE id = ?",
                    (rewrite, self.event_id),
                )
                await db.commit()

            # Re-broadcast to web clients
            if self.session_mgr:
                try:
                    import json as _ej
                    for _s in self.session_mgr.all:
                        if (_s.is_in_game and hasattr(_s, 'protocol')
                                and _s.protocol.value == 'websocket'):
                            await _s._send(_ej.dumps({
                                "type": "news_event",
                                "tag": "event_rewrite",
                                "text": rewrite,
                            }))
                except Exception as _e:
                    log.debug("silent except in engine/idle_queue.py:232: %s", _e, exc_info=True)

            log.info("[idle_queue] Event %d rewritten: %s", self.event_id, rewrite[:60])
        except Exception as e:
            log.warning("[idle_queue] Event rewrite failed: %s", e)


@dataclass
class HousingDescTask(IdleTask):
    """Pre-generate a room description for a newly purchased home."""
    priority: int = 4
    task_type: str = "housing_desc"
    housing_id: int = 0
    room_name: str = ""
    tier_label: str = ""
    planet: str = ""
    faction: str = ""
    zone_tone: str = ""

    async def execute(self, ai: "AIManager", db) -> None:
        system_prompt = (
            "You are a Star Wars room description writer for a text-based "
            "multiplayer game set during the Galactic Civil War era. Write a "
            "vivid, atmospheric room description in second person present "
            "tense. 2-4 sentences, under 400 characters. Focus on sensory "
            "details. Output ONLY the description text."
        )
        parts = [
            f"Room name: {self.room_name}",
            f"Housing type: {self.tier_label}",
            f"Planet: {self.planet}",
        ]
        if self.faction:
            parts.append(f"Faction: {self.faction}")
        if self.zone_tone:
            parts.append(f"Atmosphere: {self.zone_tone[:200]}")

        try:
            desc = await ai.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": "\n".join(parts)}],
                max_tokens=250,
                temperature=0.8,
                provider="ollama",
            )
            if desc and len(desc.strip()) > 20:
                _housing_desc_cache[self.housing_id] = desc.strip()
                log.info("[idle_queue] Housing %d desc pre-generated (%d chars)",
                         self.housing_id, len(desc))
        except Exception as e:
            log.warning("[idle_queue] Housing desc failed for %d: %s",
                        self.housing_id, e)


# ── Bark Cache ────────────────────────────────────────────────────────────────

# {npc_id: {"barks": [...], "generated_at": float, "npc_name": str}}
_bark_cache: dict[int, dict] = {}

# {(npc_id, char_id): last_bark_time} — per-player per-NPC cooldown
_bark_cooldowns: dict[tuple[int, int], float] = {}

# {housing_id: description_text} — pre-generated descriptions from Ollama
_housing_desc_cache: dict[int, str] = {}


def get_random_bark(npc_id: int, char_id: int, npc_name: str = "") -> Optional[dict]:
    """Return a bark dict for display, or None if on cooldown/empty.

    Called by MoveCommand after auto-look. Returns None if:
      - NPC has no cached barks
      - Player saw a bark from this NPC within BARK_COOLDOWN_SECS
      - Cache is stale (> 2× refresh interval)

    Returns dict with keys: npc_name, bark, text (ANSI-formatted for Telnet).
    """
    entry = _bark_cache.get(npc_id)
    if not entry or not entry.get("barks"):
        return None

    # Staleness check — don't show very old barks
    age = time.time() - entry.get("generated_at", 0)
    if age > BARK_REFRESH_HOURS * 3600 * 2:
        return None

    # Per-player cooldown
    key = (npc_id, char_id)
    last = _bark_cooldowns.get(key, 0)
    if time.time() - last < BARK_COOLDOWN_SECS:
        return None

    # Pick a random bark
    bark = random.choice(entry["barks"])
    _bark_cooldowns[key] = time.time()

    name = entry.get("npc_name", npc_name or f"NPC#{npc_id}")
    return {
        "npc_name": name,
        "bark": bark,
        "text": f"\n  \033[2m{name} mutters, \"{bark}\"\033[0m",
    }


def needs_bark_refresh(npc_id: int) -> bool:
    """Return True if this NPC needs bark regeneration."""
    entry = _bark_cache.get(npc_id)
    if not entry:
        return True
    age = time.time() - entry.get("generated_at", 0)
    return age > BARK_REFRESH_HOURS * 3600


# ── Idle Queue ────────────────────────────────────────────────────────────────

class IdleQueue:
    """Priority-aware async work queue for Ollama idle tasks.

    Key invariant: player-initiated requests (talk <npc>) always take
    priority. This queue backs off for BACKOFF_SECONDS after any player
    request, and never processes more than one task per tick cycle.
    """

    def __init__(self, ai_manager: "AIManager"):
        self._ai = ai_manager
        self._queue: list[IdleTask] = []
        self._busy = False
        self._last_player_request: float = 0.0
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0

    def notify_player_request(self) -> None:
        """Called by npc_brain before every player-initiated generate().

        Updates the last-request timestamp so idle tasks back off.
        """
        self._last_player_request = time.time()

    def enqueue(self, task: IdleTask) -> bool:
        """Add a task to the queue. Returns False if queue is full."""
        if len(self._queue) >= MAX_QUEUE_SIZE:
            return False
        task.created_at = time.time()
        self._queue.append(task)
        # Sort by priority (lower = higher priority)
        self._queue.sort(key=lambda t: (t.priority, t.created_at))
        return True

    async def try_process_one(self, db) -> bool:
        """Process one idle task if Ollama is free. Called by tick handler.

        Returns True if a task was processed (success or failure).
        """
        if self._busy:
            return False
        if not self._queue:
            return False

        # Back off if a player just talked to an NPC
        elapsed = time.time() - self._last_player_request
        if self._last_player_request > 0 and elapsed < BACKOFF_SECONDS:
            return False

        # Check Ollama availability
        try:
            ollama = self._ai.get_provider("ollama")
            if not await ollama.is_available():
                return False
        except Exception:
            return False

        task = self._queue.pop(0)
        self._busy = True
        try:
            await task.execute(self._ai, db)
            self._tasks_completed += 1
        except Exception as e:
            log.warning("[idle_queue] Task %s failed: %s", task.task_type, e)
            self._tasks_failed += 1
        finally:
            self._busy = False
        return True

    def enqueue_bark(self, npc_id: int, npc_name: str, species: str,
                     personality: str, faction: str, room_name: str,
                     zone_tone: str = "") -> bool:
        """Convenience: enqueue an ambient bark generation task."""
        if not personality:
            return False  # Skip NPCs without personality
        # Don't re-queue if already pending for this NPC
        for t in self._queue:
            if t.task_type == "ambient_bark" and getattr(t, "npc_id", 0) == npc_id:
                return False
        return self.enqueue(AmbientBarkTask(
            npc_id=npc_id, npc_name=npc_name, species=species,
            personality=personality, faction=faction, room_name=room_name,
            zone_tone=zone_tone,
        ))

    def enqueue_scene_summary(self, scene_id: int, room_name: str,
                              participants: str, poses_text: str) -> bool:
        """Convenience: enqueue a scene summary task."""
        # Cap pose text to avoid overloading Mistral context
        if len(poses_text) > 8000:
            poses_text = poses_text[-8000:]
        return self.enqueue(SceneSummaryTask(
            scene_id=scene_id, room_name=room_name,
            participants=participants, poses_text=poses_text,
        ))

    def enqueue_event_rewrite(self, event_id: int, headline: str,
                              zone_name: str, zone_tone: str = "",
                              session_mgr=None) -> bool:
        """Convenience: enqueue a Director headline rewrite task."""
        return self.enqueue(EventRewriteTask(
            event_id=event_id, headline=headline,
            zone_name=zone_name, zone_tone=zone_tone,
            session_mgr=session_mgr,
        ))

    def enqueue_housing_desc(self, housing_id: int, room_name: str,
                             tier_label: str, planet: str,
                             faction: str = "", zone_tone: str = "") -> bool:
        """Convenience: enqueue a housing description pre-generation task."""
        # Don't re-queue if already cached
        if housing_id in _housing_desc_cache:
            return False
        return self.enqueue(HousingDescTask(
            housing_id=housing_id, room_name=room_name,
            tier_label=tier_label, planet=planet,
            faction=faction, zone_tone=zone_tone,
        ))

    def get_cached_description(self, housing_id: int) -> Optional[str]:
        """Return a pre-generated description from cache, or None."""
        return _housing_desc_cache.pop(housing_id, None)

    @property
    def pending(self) -> int:
        """Number of tasks waiting."""
        return len(self._queue)

    @property
    def stats(self) -> dict:
        """Queue statistics for @economy or admin display."""
        return {
            "pending": len(self._queue),
            "completed": self._tasks_completed,
            "failed": self._tasks_failed,
            "busy": self._busy,
            "barks_cached": len(_bark_cache),
            "backoff_remaining": max(0, BACKOFF_SECONDS - (time.time() - self._last_player_request)),
        }


# ── Bark Seeding ──────────────────────────────────────────────────────────────

async def seed_barks_for_populated_rooms(idle_queue: IdleQueue, db,
                                          session_mgr) -> int:
    """Queue bark generation for NPCs in rooms with online players.

    Called on startup and periodically (every BARK_REFRESH_HOURS).
    Returns number of tasks queued.
    """
    queued = 0
    try:
        # Get rooms that have online players
        occupied_rooms: set[int] = set()
        for s in session_mgr.all:
            if s.is_in_game and s.character:
                rid = s.character.get("room_id")
                if rid:
                    occupied_rooms.add(rid)

        if not occupied_rooms:
            return 0

        for room_id in occupied_rooms:
            npcs = await db.get_npcs_in_room(room_id)
            room = await db.get_room(room_id)
            room_name = room.get("name", "") if room else ""

            # Get zone tone
            zone_tone = ""
            try:
                from engine.zone_tones import get_zone_tone
                zone_tone = await get_zone_tone(db, room_id)
            except Exception as _e:
                log.debug("silent except in engine/idle_queue.py:519: %s", _e, exc_info=True)

            for npc in npcs:
                npc_id = npc.get("id", 0)
                if not npc_id:
                    continue

                # Skip if barks are fresh
                if not needs_bark_refresh(npc_id):
                    continue

                # Parse ai_config
                ai_cfg = npc.get("ai_config_json", "{}")
                if isinstance(ai_cfg, str):
                    try:
                        ai_cfg = json.loads(ai_cfg)
                    except Exception:
                        ai_cfg = {}

                # Skip hostile NPCs, disabled AI, or those without personality
                if ai_cfg.get("hostile", False):
                    continue
                if not ai_cfg.get("enabled", True):
                    continue
                personality = ai_cfg.get("personality", "")
                if not personality:
                    continue

                ok = idle_queue.enqueue_bark(
                    npc_id=npc_id,
                    npc_name=npc.get("name", ""),
                    species=npc.get("species", "alien"),
                    personality=personality,
                    faction=ai_cfg.get("faction", ""),
                    room_name=room_name,
                    zone_tone=zone_tone,
                )
                if ok:
                    queued += 1

    except Exception as e:
        log.warning("[idle_queue] seed_barks failed: %s", e)

    if queued:
        log.info("[idle_queue] Seeded %d bark tasks for %d occupied rooms",
                 queued, len(occupied_rooms))
    return queued
