"""Regression: BountyTrack best-investigation-skill selection was dead.

`BountyTrackCommand.execute` ranks search / streetwise / tracking by the
character's dice pool, then rolls the winner through `perform_skill_check`
(the dice funnel — funnel routing was correct and is NOT changed here).

The ranking itself was broken: `Character.get_skill_pool(skill_name,
skill_registry)` takes TWO positional args (no default for the registry),
but the loop called `char_obj.get_skill_pool(sk)` with one. Every iteration
raised `TypeError`, which the surrounding `except Exception: continue`
swallowed — so `best_skill` stayed pinned to its `"search"` default for
every character. A Streetwise-5D bounty hunter with untrained Search always
tracked on Search.

Fix (2026-07-03): pass the process-cached SkillRegistry so the ranking runs.
This restores the documented QA-H10 intent; it is balance-conservative in
that it only makes an already-intended feature work (a specialist now rolls
their best skill instead of raw-attribute Search).
"""

import inspect

import pytest

from engine.character import (
    Character,
    canonical_skill_key,
    get_cached_skill_registry,
)


# The three skills BountyTrack ranks, kept in sync with the production list.
_INVESTIGATION_SKILLS = ["search", "streetwise", "tracking"]


def _char(skills: dict | None = None) -> Character:
    """A minimal Character with every attribute at 2D.

    All six attributes are equal, so a trained skill's bonus is the only
    thing that can move its pool above the untrained ones — the ranking is
    deterministic regardless of which attribute governs which skill.
    """
    attrs = {a: "2D" for a in (
        "dexterity", "knowledge", "mechanical",
        "perception", "strength", "technical",
    )}
    return Character.from_db_dict({
        "id": 1,
        "name": "Tracker",
        "attributes": attrs,
        "skills": skills or {},
    })


def _rank_best(char: Character) -> str:
    """Mirror of the production ranking predicate (pinned by the source guard
    below), driven through the REAL get_skill_pool + cached registry."""
    reg = get_cached_skill_registry()
    best_skill = "search"
    best_pips = -1
    for sk in _INVESTIGATION_SKILLS:
        pool = char.get_skill_pool(sk, reg)
        if pool.total_pips() > best_pips:  # total_pips is a METHOD, not a property
            best_pips = pool.total_pips()
            best_skill = sk
    return best_skill


# ── the bug class: get_skill_pool needs the registry ─────────────────────────

def test_get_skill_pool_requires_registry_arg():
    """One-arg get_skill_pool raises TypeError — the swallowed error that
    silently killed the ranking. This is why the registry MUST be passed."""
    char = _char({"streetwise": "3D"})
    with pytest.raises(TypeError):
        char.get_skill_pool("streetwise")  # missing skill_registry


def test_get_skill_pool_with_registry_returns_trained_pool():
    """With the registry, a trained skill returns a richer pool than an
    untrained one — the signal the ranking depends on. total_pips is a
    METHOD (the second swallowed-TypeError source), so it must be called."""
    reg = get_cached_skill_registry()
    char = _char({"streetwise": "3D"})
    trained = char.get_skill_pool("streetwise", reg)
    untrained = char.get_skill_pool("search", reg)
    assert trained.total_pips() > untrained.total_pips()


# ── the restored behavior: rank picks the character's best skill ─────────────

def test_ranking_selects_trained_streetwise_over_search():
    """A Streetwise specialist must be tracked on Streetwise, not Search."""
    char = _char({"streetwise": "3D"})
    assert _rank_best(char) == "streetwise"


def test_tracking_investigation_entry_is_inert_unregistered():
    """Documents a SEPARATE, logged finding (BOUNTY.track_third_skill_phantom):
    the third entry "tracking" is not a registered skill, so get_skill_pool
    returns DicePool(0,0) and it can NEVER be selected. A char "trained" in
    tracking still ranks Search. Fixing which real skill belongs here (survival?
    investigation?) is a Brian design call, not part of this correctness drop.
    If a Tracking skill is later registered, this test flips and prompts an
    update to the ranking list."""
    reg = get_cached_skill_registry()
    assert reg.get(canonical_skill_key("tracking")) is None, (
        "tracking is currently unregistered; if that changes, revisit the "
        "BountyTrack investigation_skills list + the logged design call"
    )
    char = _char({"tracking": "4D"})
    assert _rank_best(char) == "search"


def test_ranking_defaults_to_search_when_untrained():
    """No investigation training → the "search" default still holds."""
    char = _char({})
    assert _rank_best(char) == "search"


# ── source guard: production must pass the registry (anti-regression) ─────────

def test_source_passes_registry_to_get_skill_pool():
    from parser import bounty_commands

    src = inspect.getsource(bounty_commands.BountyTrackCommand.execute)
    assert "get_cached_skill_registry()" in src, (
        "BountyTrack must obtain the cached SkillRegistry for the ranking"
    )
    assert "get_skill_pool(sk, skill_reg)" in src, (
        "get_skill_pool must be called with the registry (two args)"
    )
    assert "get_skill_pool(sk)" not in src, (
        "the one-arg call is the swallowed-TypeError regression (defect 1)"
    )
    # total_pips is a METHOD; the uncalled `pool.total_pips` was defect 2
    # (another swallowed TypeError). It must be invoked.
    assert "pool.total_pips()" in src, (
        "total_pips must be called, not compared as a bound method"
    )
    assert "pool.total_pips >" not in src, (
        "the uncalled bound-method comparison is the defect-2 regression"
    )
    # The roll must still route through the dice funnel (H10 invariant).
    assert "perform_skill_check" in src
