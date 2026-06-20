# -*- coding: utf-8 -*-
"""tests/test_chain_rep_persist.py — onboarding QA regression guard (2026-06-20).

The onboarding_chains re-run found that completing a tutorial chain awarded ZERO
faction rep: the per-step + graduation reward calls write `faction_rep` into
`char["attributes"]` via `adjust_rep`, but `engine/chain_events.py::_try_advance`
then wrote back its STALE local `attrs` dict with a blanket `_persist_attrs`,
clobbering the rep. Fix: snapshot attrs before the advance, then MERGE-persist —
re-read the post-reward attrs and overlay only the keys this function changed.

Deterministic source guard (the functional repro is a chain walkthrough, which
shares the known republic_soldier walkthrough flake — not added to the gate).
"""
from __future__ import annotations

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_try_advance_merge_persists_reward_path_rep():
    s = _src("engine/chain_events.py")
    # Pre-advance snapshot the merge diffs against.
    assert "_attrs_at_entry" in s, "pre-advance attrs snapshot missing"
    # The advance path must re-read post-reward attrs and merge-persist, NOT
    # blanket-overwrite with the stale local dict (which dropped faction_rep).
    assert "_merged = _load_attrs(char)" in s, "merge-persist re-read missing"
    assert "await _persist_attrs(db, char, _merged)" in s, "merge-persist write missing"
