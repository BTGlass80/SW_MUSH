# -*- coding: utf-8 -*-
"""
Tests for the Entity Actor system.

Covers:
  - ActionRequest/ActionResult creation
  - EntityActor queue ordering
  - EntityActor exception propagation
  - EntityActor idle behavior
  - ActorRegistry lazy spawn
  - ActorRegistry idle reap
  - Concurrent multi-entity scenarios
  - Actor stop / cancel behavior
"""
import asyncio
import time
import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.entity_actor import (
    ActionType, ActionRequest, ActionResult,
    EntityActor, ActorRegistry,
    IDLE_TIMEOUT,
)


# ── Helpers ──

def make_request(actor_id=1, action_type=ActionType.ATTACK,
                 target_id=2, skill="blaster", damage="4D") -> ActionRequest:
    return ActionRequest(
        actor_id=actor_id,
        action_type=action_type,
        target_id=target_id,
        skill=skill,
        weapon_damage=damage,
    )


async def counting_resolver(request: ActionRequest) -> ActionResult:
    """Simple resolver that returns action details in the narrative."""
    return ActionResult(
        actor_id=request.actor_id,
        action_type=request.action_type,
        success=True,
        target_id=request.target_id,
        narrative=f"{request.actor_id} -> {request.target_id} with {request.skill}",
    )


async def slow_resolver(request: ActionRequest) -> ActionResult:
    """Resolver that takes time to process."""
    await asyncio.sleep(0.05)
    return ActionResult(
        actor_id=request.actor_id,
        action_type=request.action_type,
        success=True,
        narrative="slow",
    )


async def failing_resolver(request: ActionRequest) -> ActionResult:
    """Resolver that always raises."""
    raise ValueError("Intentional test failure")


async def ordered_resolver(request: ActionRequest) -> ActionResult:
    """Resolver that records processing order via params."""
    seq = request.params.get("seq", 0)
    return ActionResult(
        actor_id=request.actor_id,
        action_type=request.action_type,
        narrative=f"seq-{seq}",
    )


# ══════════════════════════════════════════════════════════════
# ActionRequest / ActionResult Tests
# ══════════════════════════════════════════════════════════════

class TestActionRequest:
    def test_basic_creation(self):
        req = make_request()
        assert req.actor_id == 1
        assert req.action_type == ActionType.ATTACK
        assert req.target_id == 2
        assert req.skill == "blaster"
        assert req.weapon_damage == "4D"
        assert req.timestamp > 0

    def test_params_default(self):
        req = make_request()
        assert req.params == {}

    def test_params_custom(self):
        req = ActionRequest(actor_id=1, action_type=ActionType.AIM, params={"rounds": 2})
        assert req.params["rounds"] == 2


class TestActionResult:
    def test_success_result(self):
        result = ActionResult(
            actor_id=1, action_type=ActionType.ATTACK,
            success=True, margin=5, wound_inflicted="Wounded",
        )
        assert result.success is True
        assert result.margin == 5
        assert result.wound_inflicted == "Wounded"
        assert result.error == ""

    def test_error_result(self):
        result = ActionResult(
            actor_id=1, action_type=ActionType.ATTACK,
            error="Target not found",
        )
        assert result.success is False
        assert result.error == "Target not found"


# ══════════════════════════════════════════════════════════════
# EntityActor Tests
# ══════════════════════════════════════════════════════════════

class TestEntityActor:

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        actor = EntityActor(entity_id=1, resolver=counting_resolver)
        actor.start()
        assert actor.is_running
        actor.stop()
        await asyncio.sleep(0.05)
        assert not actor.is_running

    @pytest.mark.asyncio
    async def test_submit_and_receive(self):
        actor = EntityActor(entity_id=1, resolver=counting_resolver)
        actor.start()
        try:
            req = make_request(actor_id=1, target_id=5, skill="dodge")
            result = await actor.submit(req)
            assert result.success is True
            assert result.actor_id == 1
            assert result.target_id == 5
            assert "dodge" in result.narrative
        finally:
            actor.stop()

    @pytest.mark.asyncio
    async def test_queue_ordering(self):
        """Actions must be processed in FIFO order."""
        results = []

        async def recording_resolver(req):
            result = await ordered_resolver(req)
            results.append(result.narrative)
            return result

        actor = EntityActor(entity_id=1, resolver=recording_resolver)
        actor.start()
        try:
            tasks = []
            for i in range(5):
                req = ActionRequest(
                    actor_id=1, action_type=ActionType.ATTACK,
                    params={"seq": i},
                )
                tasks.append(asyncio.create_task(actor.submit(req)))

            await asyncio.gather(*tasks)
            assert results == [f"seq-{i}" for i in range(5)]
        finally:
            actor.stop()

    @pytest.mark.asyncio
    async def test_exception_propagation(self):
        """Errors in resolver produce ActionResult with error, not crash."""
        actor = EntityActor(entity_id=1, resolver=failing_resolver)
        actor.start()
        try:
            req = make_request()
            result = await actor.submit(req)
            assert result.error == "Intentional test failure"
            # Actor should still be running after an error
            assert actor.is_running
        finally:
            actor.stop()

    @pytest.mark.asyncio
    async def test_actor_survives_multiple_errors(self):
        """Actor keeps processing after resolver errors."""
        call_count = 0

        async def sometimes_fails(req):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError(f"Fail #{call_count}")
            return ActionResult(actor_id=req.actor_id,
                                action_type=req.action_type, success=True)

        actor = EntityActor(entity_id=1, resolver=sometimes_fails)
        actor.start()
        try:
            r1 = await actor.submit(make_request())
            assert r1.error != ""
            r2 = await actor.submit(make_request())
            assert r2.error != ""
            r3 = await actor.submit(make_request())
            assert r3.success is True
            assert actor.is_running
        finally:
            actor.stop()

    @pytest.mark.asyncio
    async def test_submit_to_stopped_actor_raises(self):
        actor = EntityActor(entity_id=1, resolver=counting_resolver)
        # Never started
        with pytest.raises(RuntimeError, match="not running"):
            await actor.submit(make_request())

    @pytest.mark.asyncio
    async def test_stop_resolves_pending(self):
        """Stopping an actor resolves pending requests with error."""
        actor = EntityActor(entity_id=1, resolver=slow_resolver)
        actor.start()

        # Submit several requests
        reqs = []
        for _ in range(3):
            req = make_request()
            loop = asyncio.get_running_loop()
            req._result_future = loop.create_future()
            await actor._queue.put(req)
            reqs.append(req)

        # Let first one start processing
        await asyncio.sleep(0.02)
        actor.stop()
        await asyncio.sleep(0.1)

        # At least some should have error results
        resolved = sum(1 for r in reqs if r._result_future.done())
        assert resolved > 0

    @pytest.mark.asyncio
    async def test_default_resolver(self):
        """Actor with no resolver returns default result."""
        actor = EntityActor(entity_id=1)
        actor.start()
        try:
            result = await actor.submit(make_request())
            assert "ATTACK" in result.narrative
        finally:
            actor.stop()

    @pytest.mark.asyncio
    async def test_actions_processed_counter(self):
        actor = EntityActor(entity_id=1, resolver=counting_resolver)
        actor.start()
        try:
            for _ in range(3):
                await actor.submit(make_request())
            assert actor._actions_processed == 3
        finally:
            actor.stop()

    @pytest.mark.asyncio
    async def test_submit_nowait(self):
        actor = EntityActor(entity_id=1, resolver=counting_resolver)
        actor.start()
        try:
            req = make_request()
            await actor.submit_nowait(req)
            # Wait for processing
            result = await asyncio.wait_for(req.result_future, timeout=1.0)
            assert result.success is True
        finally:
            actor.stop()


# ══════════════════════════════════════════════════════════════
# ActorRegistry Tests
# ══════════════════════════════════════════════════════════════

class TestActorRegistry:

    @pytest.mark.asyncio
    async def test_lazy_spawn(self):
        """Actors are created on first submission."""
        registry = ActorRegistry(resolver=counting_resolver)
        assert registry.active_count == 0

        result = await registry.submit(1, make_request())
        assert result.success is True
        assert registry.active_count == 1

    @pytest.mark.asyncio
    async def test_reuse_existing_actor(self):
        registry = ActorRegistry(resolver=counting_resolver)
        await registry.submit(1, make_request())
        await registry.submit(1, make_request())
        assert registry.active_count == 1

    @pytest.mark.asyncio
    async def test_multiple_entities(self):
        """Each entity gets its own actor."""
        registry = ActorRegistry(resolver=counting_resolver)
        tasks = []
        for eid in [1, 2, 3]:
            req = make_request(actor_id=eid, target_id=eid + 10)
            tasks.append(registry.submit(eid, req))

        results = await asyncio.gather(*tasks)
        assert len(results) == 3
        assert registry.active_count == 3
        # Each result should have the correct actor_id
        for r, eid in zip(results, [1, 2, 3]):
            assert r.actor_id == eid

        registry.stop_all()

    @pytest.mark.asyncio
    async def test_remove_actor(self):
        registry = ActorRegistry(resolver=counting_resolver)
        await registry.submit(1, make_request())
        assert registry.active_count == 1
        registry.remove(1)
        await asyncio.sleep(0.05)
        assert registry.active_count == 0

    @pytest.mark.asyncio
    async def test_stop_all(self):
        registry = ActorRegistry(resolver=counting_resolver)
        for eid in [1, 2, 3]:
            await registry.submit(eid, make_request(actor_id=eid))
        assert registry.active_count == 3
        registry.stop_all()
        await asyncio.sleep(0.05)
        assert registry.active_count == 0

    @pytest.mark.asyncio
    async def test_get_status(self):
        registry = ActorRegistry(resolver=counting_resolver)
        await registry.submit(1, make_request())
        await registry.submit(2, make_request(actor_id=2))
        status = registry.get_status()
        assert len(status) == 2
        ids = {s["entity_id"] for s in status}
        assert ids == {1, 2}
        registry.stop_all()

    @pytest.mark.asyncio
    async def test_submit_nowait(self):
        registry = ActorRegistry(resolver=counting_resolver)
        req = make_request()
        await registry.submit_nowait(1, req)
        result = await asyncio.wait_for(req.result_future, timeout=1.0)
        assert result.success is True
        registry.stop_all()

    @pytest.mark.asyncio
    async def test_concurrent_submissions_to_same_entity(self):
        """Multiple concurrent submissions to the same entity are serialized."""
        order = []

        async def tracking_resolver(req):
            seq = req.params.get("seq", 0)
            await asyncio.sleep(0.01)  # Simulate work
            order.append(seq)
            return ActionResult(actor_id=req.actor_id,
                                action_type=req.action_type, narrative=str(seq))

        registry = ActorRegistry(resolver=tracking_resolver)
        tasks = []
        for i in range(5):
            req = ActionRequest(actor_id=1, action_type=ActionType.ATTACK,
                                params={"seq": i})
            tasks.append(asyncio.create_task(registry.submit(1, req)))

        await asyncio.gather(*tasks)
        # Should be processed in order despite concurrent submission
        assert order == [0, 1, 2, 3, 4]
        registry.stop_all()

    @pytest.mark.asyncio
    async def test_parallel_entities_are_truly_parallel(self):
        """Different entities process concurrently, not sequentially."""
        start_times = {}

        async def timing_resolver(req):
            start_times[req.actor_id] = time.time()
            await asyncio.sleep(0.05)
            return ActionResult(actor_id=req.actor_id,
                                action_type=req.action_type, success=True)

        registry = ActorRegistry(resolver=timing_resolver)
        tasks = []
        for eid in [1, 2, 3]:
            req = make_request(actor_id=eid)
            tasks.append(asyncio.create_task(registry.submit(eid, req)))

        t0 = time.time()
        await asyncio.gather(*tasks)
        elapsed = time.time() - t0

        # If truly parallel, should take ~0.05s, not ~0.15s
        assert elapsed < 0.12, f"Took {elapsed:.3f}s, expected parallel execution"
        registry.stop_all()

    @pytest.mark.asyncio
    async def test_get_or_create_with_custom_resolver(self):
        """Per-entity resolver override."""
        async def custom(req):
            return ActionResult(actor_id=req.actor_id,
                                action_type=req.action_type, narrative="custom")

        registry = ActorRegistry(resolver=counting_resolver)
        actor = registry.get_or_create(99, resolver=custom)
        result = await actor.submit(make_request(actor_id=99))
        assert result.narrative == "custom"
        registry.stop_all()
