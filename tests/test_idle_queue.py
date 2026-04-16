# -*- coding: utf-8 -*-
"""
tests/test_idle_queue.py — Unit tests for the Ollama Idle Queue system.

Tests cover:
  - IdleQueue priority ordering
  - Contention backoff (notify_player_request)
  - Bark cache: get_random_bark, cooldowns, staleness
  - Enqueue deduplication
  - Queue size limits
  - Task execution (with MockProvider)
  - needs_bark_refresh logic
  - get_random_bark return structure
"""

import asyncio
import json
import os
import sys
import time
import pytest

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.idle_queue import (
    IdleQueue,
    IdleTask,
    AmbientBarkTask,
    SceneSummaryTask,
    EventRewriteTask,
    HousingDescTask,
    get_random_bark,
    needs_bark_refresh,
    _bark_cache,
    _bark_cooldowns,
    _housing_desc_cache,
    BACKOFF_SECONDS,
    BARK_COOLDOWN_SECS,
    BARK_REFRESH_HOURS,
    MAX_QUEUE_SIZE,
)
from ai.providers import AIManager, AIConfig, MockProvider


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ai():
    """AIManager with mock provider as default."""
    cfg = AIConfig(enabled=True, default_provider="mock")
    mgr = AIManager(cfg)
    return mgr


@pytest.fixture
def queue(mock_ai):
    """Fresh IdleQueue with mock AI."""
    q = IdleQueue(mock_ai)
    return q


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear bark and housing caches before each test."""
    _bark_cache.clear()
    _bark_cooldowns.clear()
    _housing_desc_cache.clear()
    yield
    _bark_cache.clear()
    _bark_cooldowns.clear()
    _housing_desc_cache.clear()


# ── Queue Priority Tests ─────────────────────────────────────────────────────

def test_queue_priority_ordering(queue):
    """Tasks should be sorted by priority (lower = higher priority)."""
    t_low = IdleTask(priority=4, task_type="low")
    t_high = IdleTask(priority=1, task_type="high")
    t_mid = IdleTask(priority=2, task_type="mid")

    queue.enqueue(t_low)
    queue.enqueue(t_high)
    queue.enqueue(t_mid)

    assert queue.pending == 3
    assert queue._queue[0].task_type == "high"
    assert queue._queue[1].task_type == "mid"
    assert queue._queue[2].task_type == "low"


def test_queue_fifo_within_same_priority(queue):
    """Tasks at the same priority should be processed FIFO."""
    t1 = IdleTask(priority=2, task_type="first")
    t2 = IdleTask(priority=2, task_type="second")
    t3 = IdleTask(priority=2, task_type="third")

    queue.enqueue(t1)
    # Small delay to ensure distinct created_at
    t2.created_at = time.time() + 0.001
    queue.enqueue(t2)
    t3.created_at = time.time() + 0.002
    queue.enqueue(t3)

    assert queue._queue[0].task_type == "first"


# ── Queue Size Limit ─────────────────────────────────────────────────────────

def test_queue_max_size(queue):
    """Queue should reject tasks when full."""
    for i in range(MAX_QUEUE_SIZE):
        assert queue.enqueue(IdleTask(priority=2, task_type=f"task_{i}"))

    # Next enqueue should fail
    assert not queue.enqueue(IdleTask(priority=1, task_type="overflow"))
    assert queue.pending == MAX_QUEUE_SIZE


# ── Contention Backoff ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backoff_after_player_request(queue):
    """Queue should not process tasks within BACKOFF_SECONDS of a player request."""
    queue.enqueue(IdleTask(priority=2, task_type="test"))
    queue.notify_player_request()

    # Should refuse to process (player just talked)
    result = await queue.try_process_one(None)
    assert not result
    assert queue.pending == 1  # Task still in queue


@pytest.mark.asyncio
async def test_processes_after_backoff_expires(queue):
    """Queue should process after backoff expires."""
    queue.enqueue(IdleTask(priority=2, task_type="test"))

    # Set player request to well in the past
    queue._last_player_request = time.time() - BACKOFF_SECONDS - 1.0

    result = await queue.try_process_one(None)
    assert result
    assert queue.pending == 0


@pytest.mark.asyncio
async def test_no_backoff_when_no_player_request(queue):
    """Queue should process if no player has ever talked."""
    queue.enqueue(IdleTask(priority=2, task_type="test"))

    result = await queue.try_process_one(None)
    assert result
    assert queue.pending == 0


@pytest.mark.asyncio
async def test_busy_flag_prevents_concurrent(queue):
    """Queue should not process if already busy."""
    queue._busy = True
    queue.enqueue(IdleTask(priority=2, task_type="test"))

    result = await queue.try_process_one(None)
    assert not result
    assert queue.pending == 1

    queue._busy = False


# ── Stats ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_tracking(queue):
    """Stats should track completed and failed tasks."""
    queue.enqueue(IdleTask(priority=2, task_type="ok"))
    await queue.try_process_one(None)

    st = queue.stats
    assert st["completed"] == 1
    assert st["failed"] == 0
    assert st["pending"] == 0


@pytest.mark.asyncio
async def test_stats_failed_task(queue):
    """Failed tasks should be counted."""
    class FailTask(IdleTask):
        async def execute(self, ai, db):
            raise RuntimeError("boom")

    queue.enqueue(FailTask(priority=2, task_type="fail"))
    await queue.try_process_one(None)

    st = queue.stats
    assert st["completed"] == 0
    assert st["failed"] == 1


# ── Bark Enqueue Deduplication ────────────────────────────────────────────────

def test_bark_dedup(queue):
    """Should not enqueue bark for same NPC twice."""
    ok1 = queue.enqueue_bark(
        npc_id=42, npc_name="Wuher", species="Human",
        personality="Grumpy bartender", faction="neutral",
        room_name="Cantina",
    )
    ok2 = queue.enqueue_bark(
        npc_id=42, npc_name="Wuher", species="Human",
        personality="Grumpy bartender", faction="neutral",
        room_name="Cantina",
    )
    assert ok1
    assert not ok2
    assert queue.pending == 1


def test_bark_skip_no_personality(queue):
    """NPCs without personality should be skipped."""
    ok = queue.enqueue_bark(
        npc_id=99, npc_name="Guard", species="Human",
        personality="", faction="imperial",
        room_name="Gate",
    )
    assert not ok
    assert queue.pending == 0


# ── Housing Desc Deduplication ────────────────────────────────────────────────

def test_housing_desc_dedup(queue):
    """Should not re-enqueue if description already cached."""
    _housing_desc_cache[100] = "A dusty apartment."
    ok = queue.enqueue_housing_desc(
        housing_id=100, room_name="Test Room",
        tier_label="Private Residence", planet="tatooine",
    )
    assert not ok


def test_housing_desc_cache_pop(queue):
    """get_cached_description should pop from cache (one-time use)."""
    _housing_desc_cache[200] = "A cozy hovel."
    result = queue.get_cached_description(200)
    assert result == "A cozy hovel."
    assert queue.get_cached_description(200) is None


# ── Bark Cache / get_random_bark ──────────────────────────────────────────────

def test_get_random_bark_empty():
    """Should return None when no barks cached."""
    result = get_random_bark(npc_id=1, char_id=1)
    assert result is None


def test_get_random_bark_returns_dict():
    """Should return a dict with npc_name, bark, and text keys."""
    _bark_cache[10] = {
        "barks": ["Another fine day in Mos Eisley."],
        "generated_at": time.time(),
        "npc_name": "Wuher",
    }
    result = get_random_bark(npc_id=10, char_id=1)
    assert result is not None
    assert isinstance(result, dict)
    assert result["npc_name"] == "Wuher"
    assert result["bark"] == "Another fine day in Mos Eisley."
    assert "Wuher" in result["text"]
    assert "mutters" in result["text"]


def test_get_random_bark_cooldown():
    """Same NPC + player should be on cooldown after first bark."""
    _bark_cache[20] = {
        "barks": ["Test bark."],
        "generated_at": time.time(),
        "npc_name": "Greedo",
    }
    first = get_random_bark(npc_id=20, char_id=5)
    assert first is not None

    # Second call should be on cooldown
    second = get_random_bark(npc_id=20, char_id=5)
    assert second is None

    # Different player should not be on cooldown
    third = get_random_bark(npc_id=20, char_id=6)
    assert third is not None


def test_get_random_bark_stale():
    """Barks older than 2× refresh interval should be suppressed."""
    stale_time = time.time() - (BARK_REFRESH_HOURS * 3600 * 2) - 100
    _bark_cache[30] = {
        "barks": ["Old bark."],
        "generated_at": stale_time,
        "npc_name": "OldNPC",
    }
    result = get_random_bark(npc_id=30, char_id=1)
    assert result is None


def test_get_random_bark_cooldown_expired():
    """Bark should be available after cooldown expires."""
    _bark_cache[40] = {
        "barks": ["Fresh bark."],
        "generated_at": time.time(),
        "npc_name": "FreshNPC",
    }
    # First call
    get_random_bark(npc_id=40, char_id=7)

    # Fake expired cooldown
    _bark_cooldowns[(40, 7)] = time.time() - BARK_COOLDOWN_SECS - 1.0

    result = get_random_bark(npc_id=40, char_id=7)
    assert result is not None


# ── needs_bark_refresh ────────────────────────────────────────────────────────

def test_needs_refresh_no_cache():
    """Should need refresh when not cached."""
    assert needs_bark_refresh(999)


def test_needs_refresh_fresh():
    """Should not need refresh when freshly generated."""
    _bark_cache[50] = {
        "barks": ["test"],
        "generated_at": time.time(),
        "npc_name": "Test",
    }
    assert not needs_bark_refresh(50)


def test_needs_refresh_stale():
    """Should need refresh when older than BARK_REFRESH_HOURS."""
    _bark_cache[60] = {
        "barks": ["test"],
        "generated_at": time.time() - (BARK_REFRESH_HOURS * 3600) - 10,
        "npc_name": "StaleNPC",
    }
    assert needs_bark_refresh(60)


# ── AmbientBarkTask Execution ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ambient_bark_task_parses_json(mock_ai):
    """AmbientBarkTask should parse JSON response and populate bark cache."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response(json.dumps([
        "The cantina never changes.",
        "I need a drink.",
        "Those stormtroopers are bad for business.",
    ]))

    task = AmbientBarkTask(
        npc_id=70, npc_name="Wuher", species="Human",
        personality="Grumpy bartender", faction="neutral",
        room_name="Chalmun's Cantina",
    )
    await task.execute(mock_ai, None)

    assert 70 in _bark_cache
    assert len(_bark_cache[70]["barks"]) == 3
    assert _bark_cache[70]["npc_name"] == "Wuher"


@pytest.mark.asyncio
async def test_ambient_bark_task_filters_bad_entries(mock_ai):
    """AmbientBarkTask should filter out too-short and too-long strings."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response(json.dumps([
        "OK",           # Too short (3 chars)
        "ab",           # Too short
        "A valid bark that meets the length requirement.",  # Good
        "x" * 130,      # Too long (>120 chars)
        "",             # Empty
        42,             # Not a string
    ]))

    task = AmbientBarkTask(
        npc_id=71, npc_name="Test", species="Human",
        personality="Test NPC", faction="neutral",
        room_name="Test Room",
    )
    await task.execute(mock_ai, None)

    assert 71 in _bark_cache
    assert len(_bark_cache[71]["barks"]) == 1


@pytest.mark.asyncio
async def test_ambient_bark_task_handles_empty_response(mock_ai):
    """AmbientBarkTask should handle empty AI response gracefully."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response("")

    task = AmbientBarkTask(
        npc_id=72, npc_name="Silent", species="Human",
        personality="Quiet", faction="neutral",
        room_name="Nowhere",
    )
    await task.execute(mock_ai, None)

    assert 72 not in _bark_cache


@pytest.mark.asyncio
async def test_ambient_bark_task_handles_markdown_fence(mock_ai):
    """AmbientBarkTask should strip markdown code fences from response."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response(
        "```json\n"
        '["Watch your back around here.", "Credits talk, blasters walk."]\n'
        "```"
    )

    task = AmbientBarkTask(
        npc_id=73, npc_name="Smuggler", species="Human",
        personality="Shady dealer", faction="criminal",
        room_name="Back Alley",
    )
    await task.execute(mock_ai, None)

    assert 73 in _bark_cache
    assert len(_bark_cache[73]["barks"]) == 2


# ── SceneSummaryTask ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scene_summary_no_db(mock_ai):
    """SceneSummaryTask should handle None db gracefully (no crash)."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response("The heroes discussed their next move in the cantina.")

    task = SceneSummaryTask(
        scene_id=1, room_name="Cantina",
        participants="Luke, Han", poses_text="Luke: Let's go.\nHan: I know.",
    )
    # db=None means summary can't be saved, but should not crash
    await task.execute(mock_ai, None)
    # Just verify no exception — summary write requires db


# ── HousingDescTask ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_housing_desc_task_caches(mock_ai):
    """HousingDescTask should populate the housing desc cache."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response(
        "Dim light filters through grimy transparisteel windows, "
        "casting long shadows across the cramped living space."
    )

    task = HousingDescTask(
        housing_id=500, room_name="Player's Apartment",
        tier_label="Private Residence", planet="nar_shaddaa",
    )
    await task.execute(mock_ai, None)

    assert 500 in _housing_desc_cache
    assert "transparisteel" in _housing_desc_cache[500]


@pytest.mark.asyncio
async def test_housing_desc_task_rejects_short(mock_ai):
    """HousingDescTask should reject descriptions under 20 chars."""
    mock = mock_ai.get_provider("mock")
    mock.queue_response("A room.")

    task = HousingDescTask(
        housing_id=501, room_name="Tiny",
        tier_label="Private Residence", planet="tatooine",
    )
    await task.execute(mock_ai, None)

    assert 501 not in _housing_desc_cache


# ── Notify Player Request ────────────────────────────────────────────────────

def test_notify_updates_timestamp(queue):
    """notify_player_request should update the last request timestamp."""
    before = queue._last_player_request
    queue.notify_player_request()
    assert queue._last_player_request > before


# ── Scene Summary Enqueue Convenience ─────────────────────────────────────────

def test_scene_summary_caps_pose_text(queue):
    """enqueue_scene_summary should cap pose text at 8000 chars."""
    long_text = "A" * 20000
    queue.enqueue_scene_summary(
        scene_id=1, room_name="Test",
        participants="Player1, Player2", poses_text=long_text,
    )
    assert queue.pending == 1
    task = queue._queue[0]
    assert len(task.poses_text) == 8000


# ── Event Rewrite Enqueue ─────────────────────────────────────────────────────

def test_event_rewrite_enqueue(queue):
    """enqueue_event_rewrite should add a priority 3 task."""
    ok = queue.enqueue_event_rewrite(
        event_id=42, headline="Stormtroopers patrol the streets",
        zone_name="Mos Eisley", zone_tone="Tense and dusty",
    )
    assert ok
    assert queue.pending == 1
    assert queue._queue[0].priority == 3
    assert queue._queue[0].task_type == "event_rewrite"
