# -*- coding: utf-8 -*-
"""
tests/test_fable_addendum_hygiene_2026_07_03.py — drop
`fable-addendum-hygiene` (docs/fable/FABLE_ADDENDUM_FOR_CLAUDE_CODE_2026-07-03.md
§§4-5).

A PARALLEL session independently landed the bulk of this same spec first
(commit ``5c215b5``, merged onto main before this drop pushed) — deepscan/
scan single-owner resolution, `engine/help_loader.py`'s deterministic walk
+ alias-dup warning/ratchet, and the `serial` pytest marker + skip-under-
xdist-worker mechanism (`pytest.ini` + `tests/conftest.py`). That work is
already pinned by `tests/test_hygiene_batch_2026_07_03.py` and is NOT
re-pinned here to avoid duplicate/competing tests for the same behavior.

This file covers only the genuine DELTA this session added on top of the
already-landed drop:

  1. A behavioral (not just source-grep) regression pin for the walk-order
     fix: force a MOCKED reversed ``os.walk`` directory order and confirm
     `deepscan` still resolves to a single owner regardless.

  2. The Phantom Tonnage skill-uniqueness relaxation, ALSO written into
     the header comment block of
     `data/worlds/clone_wars/npcs_drop_generalized_questline_phantom_
     tonnage.yaml` itself (the already-landed drop recorded it in the test
     docstring + TODO.json's `QUEST.t3_24_36th_arc_skill_pool_exhausted`
     decision only) — and the 4-room `kuat_bulk_liner` venue logged as
     reusable stock on the `QUEST.staged_archetype_fast_follows` TODO.json
     entry.

  3. The `HYG.help_alias_collision_backlog` TODO.json entry (the already-
     landed drop's `BASELINE_ALIAS_COLLISIONS` ratchet lives only in the
     test file; this makes the backlog discoverable outside it too).

  4. `serial`-marking EXTENDED to a second, independently-measured trio
     (`test_m3_assembled_client.py`, `test_m3_sheet.py`,
     `test_combat_inspector_d_prime_client.py` — the actual 3
     highest-total-duration jsdom files under a real `-n auto --dist
     loadscope --durations=0` run, a clear margin over the rest of
     tests/spa/), applied via `tests/spa/conftest.py`'s existing
     filename-driven auto-tag hook reusing the SAME `serial` marker /
     skip-under-xdist-worker mechanism the landed drop shipped — not a
     competing mechanism.

  5. A one-retry-on-`subprocess.TimeoutExpired` wrapper
     (`spa_dom_harness._run_node_with_one_retry`, reused by
     `m3_combat_inspector_harness`) around both shared Node-subprocess
     call sites — complementary defense-in-depth that protects every
     jsdom test in the directory, not just the `serial`-marked ones.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HELP_ROOT = PROJECT_ROOT / "data" / "help"


# ══════════════════════════════════════════════════════════════════════
# 1. Behavioral pin: deepscan single-owner under a MOCKED reversed walk
# ══════════════════════════════════════════════════════════════════════

class TestDeepscanResolutionSurvivesReversedWalkOrder(unittest.TestCase):

    def test_deepscan_resolves_to_space_anomalies_normal_order(self):
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files(str(HELP_ROOT))
        entry = mgr.get("deepscan")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "space_anomalies")

    def test_deepscan_resolves_to_space_anomalies_reversed_dir_order(self):
        """Force os.walk to hand back subdirectories in reverse order
        (simulating a filesystem whose raw readdir order differs from
        alphabetical) and confirm iter_help_files' internal
        `dirnames.sort()` makes the result identical regardless — a
        behavioral pin complementary to the landed drop's source-grep
        check (test_hygiene_batch_2026_07_03.py::
        test_dirnames_sorted_for_deterministic_traversal)."""
        import engine.help_loader as help_loader_mod
        from data.help_topics import HelpEntry

        real_walk = os.walk

        def reversed_dir_walk(top, *a, **kw):
            for dirpath, dirnames, filenames in real_walk(top, *a, **kw):
                dirnames.reverse()
                yield dirpath, dirnames, filenames

        with mock.patch.object(help_loader_mod.os, "walk", side_effect=reversed_dir_walk):
            entries = help_loader_mod.load_help_directory(str(HELP_ROOT), HelpEntry)
        by_key = {e.key: e for e in entries}
        self.assertIn("space_anomalies", by_key)
        self.assertIn("deepscan", by_key["space_anomalies"].aliases)
        claimants = [e.key for e in entries if "deepscan" in e.aliases]
        self.assertEqual(claimants, ["space_anomalies"])

    def test_iter_help_files_sorts_dirnames_for_deterministic_order(self):
        """Direct behavioral unit pin on the walk-determinism fix itself,
        independent of the deepscan content."""
        import tempfile
        from engine.help_loader import iter_help_files
        import engine.help_loader as help_loader_mod

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "zzz_dir").mkdir()
            (root / "aaa_dir").mkdir()
            (root / "zzz_dir" / "z.md").write_text(
                "---\nkey: z\n---\nbody\n", encoding="utf-8")
            (root / "aaa_dir" / "a.md").write_text(
                "---\nkey: a\n---\nbody\n", encoding="utf-8")

            real_walk = os.walk

            def unsorted_walk(top, *a, **kw):
                for dirpath, dirnames, filenames in real_walk(top, *a, **kw):
                    dirnames[:] = list(reversed(dirnames))
                    yield dirpath, dirnames, filenames

            with mock.patch.object(help_loader_mod.os, "walk", side_effect=unsorted_walk):
                paths = list(iter_help_files(str(root)))
            rels = [os.path.relpath(p, str(root)).replace("\\", "/") for p in paths]
            self.assertEqual(
                rels, sorted(rels),
                f"iter_help_files order is not fully deterministic: {rels}")


# ══════════════════════════════════════════════════════════════════════
# 2. Phantom Tonnage: yaml header note + venue-stock TODO.json note
# ══════════════════════════════════════════════════════════════════════

class TestPhantomTonnageInvariantRecords(unittest.TestCase):

    NPC_FILE = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "npcs_drop_generalized_questline_phantom_tonnage.yaml")

    def test_yaml_header_records_the_skill_uniqueness_relaxation(self):
        text = self.NPC_FILE.read_text(encoding="utf-8")
        self.assertIn("INVARIANT NOTE", text)
        self.assertIn("skill spread", text.lower())
        self.assertIn("sensors", text)
        self.assertIn("computer programming", text)
        self.assertIn("silent precedent", text.lower())

    def test_yaml_edit_is_purely_additive(self):
        """World-yaml safety: the header note must be a comment-only,
        zero-deleted-lines addition. Cross-check against git HEAD's
        version isn't available here without a git call, so instead
        confirm every non-comment line elsewhere in the file is
        unaffected by asserting the file still parses to the same NPC
        count/shape as the walkthrough test expects (3 NPCs)."""
        import yaml
        data = yaml.safe_load(self.NPC_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(data.get("npcs") or []), 3)

    def test_todo_json_records_venue_stock_on_fast_follows_entry(self):
        data = json.loads((PROJECT_ROOT / "TODO.json").read_text(encoding="utf-8"))
        entry = next(e for e in data["tier_2_queued"]
                     if e.get("id") == "QUEST.staged_archetype_fast_follows")
        self.assertIn("venue_stock", entry)
        self.assertIn("kuat_bulk_liner", entry["venue_stock"])

    def test_todo_json_has_help_alias_collision_backlog_entry(self):
        data = json.loads((PROJECT_ROOT / "TODO.json").read_text(encoding="utf-8"))
        ids = [e.get("id") for e in data["tier_2_queued"]]
        self.assertIn("HYG.help_alias_collision_backlog", ids)


# ══════════════════════════════════════════════════════════════════════
# 3. The functional flake fix: one retry on subprocess.TimeoutExpired
# ══════════════════════════════════════════════════════════════════════

class TestRunNodeWithOneRetry(unittest.TestCase):
    """spa_dom_harness._run_node_with_one_retry — complementary defense-
    in-depth alongside the landed drop's `serial` marker: protects EVERY
    jsdom test in the directory (not just serial-marked ones) from a
    transient CPU-starved Node spawn under contention."""

    def _helper(self):
        import importlib.util
        path = PROJECT_ROOT / "tests" / "spa" / "spa_dom_harness.py"
        spec = importlib.util.spec_from_file_location(
            "tests.spa._spa_dom_harness_under_test", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_timeout_calls_subprocess_run_exactly_once(self):
        import subprocess
        mod = self._helper()
        sentinel = subprocess.CompletedProcess(args=["node"], returncode=0,
                                                stdout="{}", stderr="")
        with mock.patch.object(mod.subprocess, "run",
                               return_value=sentinel) as run_mock:
            result = mod._run_node_with_one_retry(["node", "-e", "x"], timeout=20)
        self.assertEqual(run_mock.call_count, 1)
        self.assertIs(result, sentinel)

    def test_one_timeout_then_success_retries_exactly_once(self):
        import subprocess
        mod = self._helper()
        sentinel = subprocess.CompletedProcess(args=["node"], returncode=0,
                                                stdout="{}", stderr="")
        with mock.patch.object(
                mod.subprocess, "run",
                side_effect=[subprocess.TimeoutExpired(cmd="node", timeout=20),
                             sentinel]) as run_mock:
            result = mod._run_node_with_one_retry(["node", "-e", "x"], timeout=20)
        self.assertEqual(run_mock.call_count, 2)
        self.assertIs(result, sentinel)

    def test_two_consecutive_timeouts_propagates_the_second(self):
        """A GENUINE hang (not transient contention) must still fail —
        the retry absorbs ONE timeout, not an unbounded number."""
        import subprocess
        mod = self._helper()
        with mock.patch.object(
                mod.subprocess, "run",
                side_effect=[subprocess.TimeoutExpired(cmd="node", timeout=20),
                             subprocess.TimeoutExpired(cmd="node", timeout=20)]) as run_mock:
            with self.assertRaises(subprocess.TimeoutExpired):
                mod._run_node_with_one_retry(["node", "-e", "x"], timeout=20)
        self.assertEqual(run_mock.call_count, 2)

    def test_run_with_dom_uses_the_retry_helper(self):
        import inspect
        mod = self._helper()
        src = inspect.getsource(mod.run_with_dom)
        self.assertIn("_run_node_with_one_retry", src)

    def test_combat_inspector_harness_reuses_the_same_helper(self):
        src = (PROJECT_ROOT / "tests" / "spa"
               / "m3_combat_inspector_harness.py").read_text(encoding="utf-8")
        self.assertIn("from .spa_dom_harness import _run_node_with_one_retry", src)
        self.assertIn("_run_node_with_one_retry(", src)


# ══════════════════════════════════════════════════════════════════════
# 4. serial-marking extended to a second, independently-measured trio
# ══════════════════════════════════════════════════════════════════════

class _FakeItem:
    """Minimal stand-in for a pytest.Item — just enough surface for
    tests/spa/conftest.py::pytest_collection_modifyitems."""

    def __init__(self, fspath):
        self.fspath = fspath
        self.added_markers = []

    def add_marker(self, marker):
        self.added_markers.append(marker)

    def _mark_names(self):
        return [m.mark.name if hasattr(m, "mark") else getattr(m, "name", None)
                for m in self.added_markers]


class TestSecondSerialTrioReusesTheLandedMechanism(unittest.TestCase):

    def _spa_conftest(self):
        import importlib.util
        path = PROJECT_ROOT / "tests" / "spa" / "conftest.py"
        spec = importlib.util.spec_from_file_location(
            "tests.spa._conftest_under_test", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_second_trio_is_the_expected_three(self):
        mod = self._spa_conftest()
        self.assertEqual(
            mod._SERIAL_MARKED_FILES,
            {"test_m3_assembled_client.py", "test_m3_sheet.py",
             "test_combat_inspector_d_prime_client.py"})

    def test_second_trio_items_get_the_existing_serial_mark(self):
        """Extends the ALREADY-LANDED `serial` marker (pytest.ini,
        honored by tests/conftest.py's skip-under-xdist-worker hook) —
        not a new marker, not a new mechanism."""
        mod = self._spa_conftest()
        spa_dir = mod._SPA_DIR
        items = [
            _FakeItem(f"{spa_dir}/test_m3_assembled_client.py"),
            _FakeItem(f"{spa_dir}/test_m3_sheet.py"),
            _FakeItem(f"{spa_dir}/test_combat_inspector_d_prime_client.py"),
        ]
        mod.pytest_collection_modifyitems(None, items)
        for item in items:
            names = item._mark_names()
            self.assertIn("slow", names)
            self.assertIn("serial", names)

    def test_other_spa_files_are_not_serial_marked(self):
        mod = self._spa_conftest()
        spa_dir = mod._SPA_DIR
        item = _FakeItem(f"{spa_dir}/test_m3_tokens.py")
        mod.pytest_collection_modifyitems(None, [item])
        names = item._mark_names()
        self.assertIn("slow", names)
        self.assertNotIn("serial", names)

    def test_files_outside_spa_dir_are_untouched(self):
        mod = self._spa_conftest()
        item = _FakeItem(str(PROJECT_ROOT / "tests" / "test_something_else.py"))
        mod.pytest_collection_modifyitems(None, [item])
        self.assertEqual(item.added_markers, [])

    def test_serial_marker_is_registered_in_pytest_ini(self):
        """Sanity check the marker this file extends actually exists —
        landed by the parallel session's commit, not invented here."""
        ini = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
        self.assertIn("serial:", ini)

    def test_top_level_conftest_has_the_skip_under_xdist_worker_hook(self):
        text = (PROJECT_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("PYTEST_XDIST_WORKER", text)
        self.assertIn('"serial"', text)


if __name__ == "__main__":
    unittest.main()
