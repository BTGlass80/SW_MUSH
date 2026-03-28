"""
Entity Actor System.

Provides per-entity serialized action processing for combat and
complex interactions. Each entity gets a dedicated async task with
its own action queue, eliminating the need for global locks.

Architecture:
  - EntityActor: single coroutine processing ActionRequests from a queue
  - ActorRegistry: manages actor lifecycle (lazy spawn, idle reap)
  - ActionRequest/ActionResult: typed work items flowing through the pipeline

Design decision: LLM inference happens BEFORE the action enters the entity
queue. The IntentParser validates and converts natural language into a clean
ActionRequest, which is then enqueued. Actors only see validated work items.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

log = logging.getLogger(__name__)

# How long an idle actor lives before being reaped (seconds)
IDLE_TIMEOUT = 60.0
# How often the registry checks for idle actors (seconds)
REAP_INTERVAL = 15.0


# ── Action Types ──

class ActionType(Enum):
    """All possible action types in the game."""
    ATTACK = auto()
    DODGE = auto()
    PARRY = auto()
    AIM = auto()
    FLEE = auto()
    USE_ITEM = auto()
    FORCE_POWER = auto()
    PASS = auto()
    # Non-combat
    SKILL_CHECK = auto()
    DIALOGUE = auto()


# ── Request / Result ──

@dataclass
class ActionRequest:
    """
    A validated action to be processed by an EntityActor.

    Created by the command parser (structured input) or IntentParser
    (natural language input), validated by BoundedContextValidator,
    then enqueued to the target EntityActor.
    """
    actor_id: int                      # Who is performing the action
    action_type: ActionType
    target_id: int = 0                 # Target entity (for attacks, etc.)
    skill: str = ""                    # Skill name (blaster, dodge, etc.)
    weapon_damage: str = ""            # Damage dice string (e.g. "4D")
    params: dict = field(default_factory=dict)  # Extra parameters
    timestamp: float = field(default_factory=time.time)

    # The future is set by the submitter and resolved by the actor
    _result_future: Optional[asyncio.Future] = field(
        default=None, repr=False, compare=False
    )

    @property
    def result_future(self) -> asyncio.Future:
        if self._result_future is None:
            self._result_future = asyncio.get_event_loop().create_future()
        return self._result_future

    @result_future.setter
    def result_future(self, val):
        self._result_future = val


@dataclass
class ActionResult:
    """
    The outcome of processing an ActionRequest.

    Contains mechanical results (rolls, damage) and optionally
    a narrative string. If narrative is empty, the caller can
    request async LLM narration separately.
    """
    actor_id: int
    action_type: ActionType
    success: bool = False
    # Roll details
    attack_roll: str = ""
    defense_roll: str = ""
    damage_roll: str = ""
    soak_roll: str = ""
    margin: int = 0
    # Wound/effect
    wound_inflicted: str = ""
    target_id: int = 0
    # Narrative (may be filled by sync text or async LLM)
    narrative: str = ""
    # Error info
    error: str = ""


# ── Entity Actor ──

class EntityActor:
    """
    Processes actions for a single entity via a serialized async queue.

    All state mutations for this entity happen in this coroutine,
    so no locking is needed. The actor reads from the DB, applies
    mechanical resolution, writes results back, and resolves the
    request's Future with an ActionResult.
    """

    def __init__(self, entity_id: int, resolver=None):
        """
        Args:
            entity_id: The character/NPC ID this actor represents.
            resolver: A callable(ActionRequest) -> ActionResult that
                      performs mechanical resolution. Injected by the
                      combat system.
        """
        self.entity_id = entity_id
        self.resolver = resolver
        self._queue: asyncio.Queue[ActionRequest] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._idle_since: float = time.time()
        self._actions_processed: int = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def is_idle(self) -> bool:
        return self._queue.empty() and self.is_running

    @property
    def idle_duration(self) -> float:
        if not self.is_idle:
            return 0.0
        return time.time() - self._idle_since

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def start(self):
        """Start the actor's processing loop."""
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"actor-{self.entity_id}")

    def stop(self):
        """Stop the actor, cancelling any pending work."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def submit(self, request: ActionRequest) -> ActionResult:
        """
        Submit an action and wait for the result.

        This is the primary interface for the combat pipeline.
        The caller awaits the result Future, which is resolved
        when the actor processes the request.
        """
        if not self.is_running:
            raise RuntimeError(f"Actor {self.entity_id} is not running")

        # Create a fresh future for this request
        loop = asyncio.get_running_loop()
        request._result_future = loop.create_future()

        await self._queue.put(request)
        return await request.result_future

    async def submit_nowait(self, request: ActionRequest):
        """
        Submit an action without waiting for the result.

        Useful for fire-and-forget actions (e.g., NPC auto-actions).
        The result can still be retrieved via request.result_future.
        """
        if not self.is_running:
            raise RuntimeError(f"Actor {self.entity_id} is not running")

        loop = asyncio.get_running_loop()
        request._result_future = loop.create_future()
        await self._queue.put(request)

    async def _run(self):
        """Main processing loop."""
        log.debug("Actor %d started", self.entity_id)
        try:
            while self._running:
                try:
                    request = await asyncio.wait_for(
                        self._queue.get(), timeout=IDLE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    # Idle timeout — actor will be reaped by registry
                    self._idle_since = time.time()
                    continue

                try:
                    result = await self._resolve(request)
                    if not request.result_future.done():
                        request.result_future.set_result(result)
                except Exception as e:
                    log.exception("Actor %d resolve error: %s", self.entity_id, e)
                    error_result = ActionResult(
                        actor_id=self.entity_id,
                        action_type=request.action_type,
                        error=str(e),
                    )
                    if not request.result_future.done():
                        request.result_future.set_result(error_result)
                finally:
                    self._actions_processed += 1
                    self._idle_since = time.time()
                    self._queue.task_done()

        except asyncio.CancelledError:
            log.debug("Actor %d cancelled", self.entity_id)
            # Resolve any pending requests with cancellation
            while not self._queue.empty():
                try:
                    req = self._queue.get_nowait()
                    if not req.result_future.done():
                        req.result_future.set_result(ActionResult(
                            actor_id=self.entity_id,
                            action_type=req.action_type,
                            error="Actor was stopped",
                        ))
                except asyncio.QueueEmpty:
                    break
        finally:
            self._running = False
            log.debug("Actor %d stopped (processed %d actions)",
                      self.entity_id, self._actions_processed)

    async def _resolve(self, request: ActionRequest) -> ActionResult:
        """
        Resolve a single action.

        If a resolver was injected, delegate to it. Otherwise return
        a default result (useful for testing).
        """
        if self.resolver:
            return await self.resolver(request)

        # Default: no-op resolution
        return ActionResult(
            actor_id=request.actor_id,
            action_type=request.action_type,
            narrative=f"Entity {request.actor_id} performs {request.action_type.name}",
        )


# ── Actor Registry ──

class ActorRegistry:
    """
    Manages the lifecycle of EntityActors.

    - Spawns actors lazily on first action submission
    - Tracks idle time
    - Reaps actors after IDLE_TIMEOUT
    - Provides lookup by entity ID
    """

    def __init__(self, resolver=None):
        """
        Args:
            resolver: Default resolver for new actors. Can be overridden
                      per-actor if needed.
        """
        self._actors: dict[int, EntityActor] = {}
        self._default_resolver = resolver
        self._reap_task: Optional[asyncio.Task] = None

    @property
    def active_count(self) -> int:
        return sum(1 for a in self._actors.values() if a.is_running)

    def get(self, entity_id: int) -> Optional[EntityActor]:
        """Get an actor by entity ID, or None if not active."""
        return self._actors.get(entity_id)

    def get_or_create(self, entity_id: int, resolver=None) -> EntityActor:
        """
        Get an existing actor or create and start a new one.

        This is the primary interface for the combat pipeline.
        """
        actor = self._actors.get(entity_id)
        if actor and actor.is_running:
            return actor

        # Create new actor
        actor = EntityActor(
            entity_id=entity_id,
            resolver=resolver or self._default_resolver,
        )
        actor.start()
        self._actors[entity_id] = actor
        log.debug("Registry spawned actor for entity %d (total: %d)",
                  entity_id, len(self._actors))
        return actor

    async def submit(self, entity_id: int, request: ActionRequest) -> ActionResult:
        """
        Submit an action to an entity's actor, creating the actor if needed.

        Convenience method that combines get_or_create + actor.submit.
        """
        actor = self.get_or_create(entity_id)
        return await actor.submit(request)

    async def submit_nowait(self, entity_id: int, request: ActionRequest):
        """Submit without waiting for result."""
        actor = self.get_or_create(entity_id)
        await actor.submit_nowait(request)

    def remove(self, entity_id: int):
        """Stop and remove an actor."""
        actor = self._actors.pop(entity_id, None)
        if actor:
            actor.stop()
            log.debug("Registry removed actor for entity %d", entity_id)

    def stop_all(self):
        """Stop all actors."""
        for actor in self._actors.values():
            actor.stop()
        self._actors.clear()
        if self._reap_task and not self._reap_task.done():
            self._reap_task.cancel()

    def start_reaper(self):
        """Start the background task that reaps idle actors."""
        if self._reap_task and not self._reap_task.done():
            return
        self._reap_task = asyncio.create_task(self._reap_loop(), name="actor-reaper")

    async def _reap_loop(self):
        """Periodically check for and remove idle actors."""
        try:
            while True:
                await asyncio.sleep(REAP_INTERVAL)
                to_reap = []
                for eid, actor in self._actors.items():
                    if actor.is_idle and actor.idle_duration > IDLE_TIMEOUT:
                        to_reap.append(eid)

                for eid in to_reap:
                    self.remove(eid)
                    log.debug("Reaped idle actor for entity %d", eid)

        except asyncio.CancelledError:
            pass

    def get_status(self) -> list[dict]:
        """Get status of all actors for debugging."""
        status = []
        for eid, actor in self._actors.items():
            status.append({
                "entity_id": eid,
                "running": actor.is_running,
                "queue_size": actor.queue_size,
                "idle_duration": round(actor.idle_duration, 1),
                "actions_processed": actor._actions_processed,
            })
        return status
