# -*- coding: utf-8 -*-
"""
tests/test_fable_addendum_hygiene_2026_07_03.py — drop
`fable-addendum-hygiene` (docs/fable/FABLE_ADDENDUM_FOR_CLAUDE_CODE_2026-07-03.md
§§4-5).

Three independent, small pins:

  1. §4 — the `deepscan` alias collision (F6 batch's own cross-platform
     red). `deepscan` now has ONE deliberate owner (the `space_anomalies`
     topic); `+sensors.md` dropped it from its `aliases:` list. Pinned
     BOTH ways: normal `os.walk` order, and a reversed/unsorted directory
     order forced via a mock — `engine.help_loader.iter_help_files` sorts
     `dirnames` in place, so the resolution no longer depends on which
     order the OS's raw readdir happens to hand back.

  2. §4(d) — the F6 dup-KEY warn/ratchet
     (`engine.help_loader.load_help_directory`) now also fires on a
     duplicate ALIAS across two different keys, loud on every OS.

  3. §5b — the three highest-measured-duration jsdom-subprocess SPA test
     files (`test_m3_assembled_client.py`, `test_m3_sheet.py`,
     `test_combat_inspector_d_prime_client.py` — identified by summing
     real per-test durations from a `-n auto --dist loadscope
     --durations=0` run on this box, not guessed) carry pytest-xdist's
     `xdist_group` marker via `tests/spa/conftest.py`. VERIFIED (against
     xdist 3.8.0's own scheduler source) that `xdist_group` only forces
     same-worker scheduling under `--dist loadgroup` — this repo's real
     `--dist loadscope` gate ignores it for cross-file grouping, proven
     empirically here too (spawning a worker-id probe showed the trio
     landing on 3 different workers even with the marker applied). The
     marker is kept anyway (harmless, correctly wired, effective the day
     the gate ever runs `loadgroup`), but the mechanism that actually
     fixes the flake under `loadscope` is a one-retry-on-
     `subprocess.TimeoutExpired` wrapper
     (`spa_dom_harness._run_node_with_one_retry`), reused by both shared
     Node-subprocess call sites.

Per the no-phantom-claims invariant: item 2 (Phantom Tonnage records) has
no test surface of its own — it's a comment-only YAML header addition and
a TODO.json note — so it isn't pinned here (its content is exercised by
the drop's YAML/JSON validation and the existing
tests/test_generalized_questline_phantom_tonnage.py, both re-run in this
drop unmodified in behavior).
"""
from __future__ import annotations

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
# 1. `deepscan` — single deliberate owner, order-independent
# ══════════════════════════════════════════════════════════════════════

class TestDeepscanSingleOwnerBothWalkOrders(unittest.TestCase):

    def _load_manager(self):
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files(str(HELP_ROOT))
        return mgr

    def test_deepscan_resolves_to_space_anomalies_normal_order(self):
        mgr = self._load_manager()
        entry = mgr.get("deepscan")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "space_anomalies")

    def test_sensors_no_longer_claims_deepscan_alias(self):
        """Regression pin for the actual fix: +sensors.md's frontmatter
        aliases list must not carry `deepscan` any more (moved to the
        anomalies topic as the sole owner)."""
        text = (HELP_ROOT / "commands" / "+sensors.md").read_text(encoding="utf-8")
        # Only check the frontmatter aliases: line, not the whole body
        # (the body legitimately still documents `deepscan` as a live
        # +sensors/deepscan SWITCH — that's the command, not the alias).
        for line in text.splitlines():
            if line.startswith("aliases:"):
                self.assertNotIn("deepscan", line,
                                 f"deepscan still claimed in +sensors.md: {line!r}")
                break
        else:
            self.fail("+sensors.md has no aliases: frontmatter line")

    def test_scan_unaffected_no_other_claimant(self):
        """`scan` has no ground-command claimant (verified at HEAD), so it
        legitimately stays a +sensors alias — this is a regression guard
        that it wasn't accidentally dropped too."""
        mgr = self._load_manager()
        entry = mgr.get("scan")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "+sensors")

    def test_deepscan_resolves_to_space_anomalies_reversed_dir_order(self):
        """Force os.walk to hand back subdirectories in reverse order
        (simulating a filesystem whose raw readdir order differs from
        alphabetical) and confirm iter_help_files' internal
        `dirnames.sort()` makes the result identical regardless."""
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
        # No OTHER entry claims deepscan as an alias (single owner, any order).
        claimants = [e.key for e in entries if "deepscan" in e.aliases]
        self.assertEqual(claimants, ["space_anomalies"])

    def test_iter_help_files_sorts_dirnames_for_deterministic_order(self):
        """Direct unit pin on the walk-determinism fix itself, independent
        of the deepscan content: iter_help_files' output order must not
        depend on the (unsorted) order os.walk hands back dirnames."""
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
# 2. Alias-dup warn/ratchet — extends the existing key-dup mechanism
# ══════════════════════════════════════════════════════════════════════

class TestAliasDuplicateRatchetFires(unittest.TestCase):

    def _load_with_capture(self, root):
        from engine.help_loader import load_help_directory
        from data.help_topics import HelpEntry
        logger = logging.getLogger("engine.help_loader")
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        logger.addHandler(handler)
        try:
            entries = load_help_directory(root, HelpEntry)
        finally:
            logger.removeHandler(handler)
        return entries, records

    def test_two_files_same_alias_different_keys_warns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            Path(d, "a.md").write_text(
                "---\nkey: alpha\naliases: [shared_alias]\n---\nbody\n",
                encoding="utf-8")
            Path(d, "b.md").write_text(
                "---\nkey: beta\naliases: [shared_alias]\n---\nbody\n",
                encoding="utf-8")
            _, records = self._load_with_capture(d)
            warnings = [r for r in records if r.levelno >= logging.WARNING]
            dup_alias = [r for r in warnings
                         if "duplicate alias" in r.getMessage()]
            self.assertTrue(
                dup_alias,
                f"expected a 'duplicate alias' warning, got: "
                f"{[r.getMessage() for r in warnings]}")

    def test_same_key_reloaded_does_not_false_positive_on_its_own_alias(self):
        """A key that legitimately reappears (e.g. re-registration) must
        not warn about its OWN alias colliding with itself."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d, "sub")
            sub.mkdir()
            Path(d, "a.md").write_text(
                "---\nkey: alpha\naliases: [only_alpha]\n---\nbody\n",
                encoding="utf-8")
            Path(sub, "a2.md").write_text(
                "---\nkey: alpha\naliases: [only_alpha]\n---\nbody v2\n",
                encoding="utf-8")
            _, records = self._load_with_capture(d)
            warnings = [r for r in records if r.levelno >= logging.WARNING]
            dup_alias = [r for r in warnings
                         if "duplicate alias" in r.getMessage()]
            self.assertEqual(
                dup_alias, [],
                f"same-key re-registration should not warn on its own "
                f"alias: {[r.getMessage() for r in dup_alias]}")

    def test_live_corpus_deepscan_and_scan_produce_no_warning(self):
        """The two collisions THIS drop targeted (deepscan: +sensors vs.
        the anomalies topic; scan: +sensors vs. the sensors topic) are
        both resolved — scoped check, not a whole-corpus claim (see the
        next test's docstring: the alias-dup ratchet's first real run
        surfaced ~34 OTHER pre-existing collisions across the help corpus
        that predate this drop and are out of its scope; logged as
        HYG.help_alias_collision_backlog in TODO.json rather than
        silently fixed here or silently ignored)."""
        _, records = self._load_with_capture(str(HELP_ROOT))
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        dup_alias_msgs = [r.getMessage() for r in warnings
                          if "duplicate alias" in r.getMessage()]
        for scoped in ("'deepscan'", "'scan'"):
            offenders = [m for m in dup_alias_msgs if scoped in m]
            self.assertEqual(
                offenders, [],
                f"{scoped} still collides post-fix: {offenders}")

    def test_live_corpus_alias_collision_backlog_is_tracked_not_growing(self):
        """The alias-dup ratchet (new this drop) surfaced a real,
        pre-existing backlog of help-alias collisions across the corpus
        that predate this drop and are NOT deepscan/scan-related (e.g.
        '+quests' vs '+quest', 'force' vs '+powers', 'housing' vs
        '+home'). Fixing all of them is out of scope for
        fable-addendum-hygiene (deepscan/scan only) — but the ratchet
        must not let the backlog grow silently, so this pins the CURRENT
        count as a ceiling. A genuine NEW collision must either be fixed
        in the drop that introduces it or bump this ceiling deliberately
        (never silently)."""
        _, records = self._load_with_capture(str(HELP_ROOT))
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        dup_alias = [r for r in warnings if "duplicate alias" in r.getMessage()]
        KNOWN_PRE_EXISTING_BACKLOG_CEILING = 34
        self.assertLessEqual(
            len(dup_alias), KNOWN_PRE_EXISTING_BACKLOG_CEILING,
            f"help-alias collision backlog GREW past the tracked ceiling "
            f"({KNOWN_PRE_EXISTING_BACKLOG_CEILING}) — a new collision was "
            f"introduced; fix it in its own drop or, if a deliberate "
            f"backlog reduction, lower this ceiling: "
            f"{[r.getMessage() for r in dup_alias]}")


# ══════════════════════════════════════════════════════════════════════
# 3a. The functional fix: one retry on subprocess.TimeoutExpired
# ══════════════════════════════════════════════════════════════════════

class TestRunNodeWithOneRetry(unittest.TestCase):
    """spa_dom_harness._run_node_with_one_retry — the mechanism that
    actually absorbs a transient CPU-starved Node spawn under `--dist
    loadscope` (where xdist_group is a documented no-op; see the trio
    tests below)."""

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
        """Regression pin: run_with_dom must route through the shared
        retry wrapper, not a bare subprocess.run call."""
        import inspect
        mod = self._helper()
        src = inspect.getsource(mod.run_with_dom)
        self.assertIn("_run_node_with_one_retry", src)

    def test_combat_inspector_harness_reuses_the_same_helper(self):
        """m3_combat_inspector_harness must import (not duplicate) the
        shared retry wrapper."""
        src = (PROJECT_ROOT / "tests" / "spa"
               / "m3_combat_inspector_harness.py").read_text(encoding="utf-8")
        self.assertIn("from .spa_dom_harness import _run_node_with_one_retry", src)
        self.assertIn("_run_node_with_one_retry(", src)


# ══════════════════════════════════════════════════════════════════════
# 3b. jsdom-subprocess trio carries the xdist_group serial mark
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


class TestJsdomTrioCarriesSerialMark(unittest.TestCase):

    def _spa_conftest(self):
        import importlib.util
        path = PROJECT_ROOT / "tests" / "spa" / "conftest.py"
        spec = importlib.util.spec_from_file_location(
            "tests.spa._conftest_under_test", str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_trio_files_are_the_expected_three(self):
        mod = self._spa_conftest()
        self.assertEqual(
            mod._JSDOM_SERIAL_FILES,
            {"test_m3_assembled_client.py", "test_m3_sheet.py",
             "test_combat_inspector_d_prime_client.py"})

    def test_trio_items_get_xdist_group_and_spa_jsdom_serial_marks(self):
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
            self.assertIn("spa_jsdom_serial", names)
            self.assertIn("xdist_group", names)
            xg = next(m for m in item.added_markers
                      if m.mark.name == "xdist_group")
            self.assertEqual(xg.mark.kwargs.get("name"),
                             mod._JSDOM_SERIAL_GROUP)

    def test_all_three_share_the_same_group_name(self):
        """The whole point: all three land on ONE worker, so they must
        share the exact same xdist_group name."""
        mod = self._spa_conftest()
        spa_dir = mod._SPA_DIR
        items = [_FakeItem(f"{spa_dir}/{fname}")
                 for fname in sorted(mod._JSDOM_SERIAL_FILES)]
        mod.pytest_collection_modifyitems(None, items)
        group_names = set()
        for item in items:
            xg = next(m for m in item.added_markers
                      if m.mark.name == "xdist_group")
            group_names.add(xg.mark.kwargs.get("name"))
        self.assertEqual(len(group_names), 1)

    def test_other_spa_files_are_not_grouped(self):
        """A normal (non-trio) spa test file gets `slow` only — no
        xdist_group — so the fix doesn't over-serialize the whole
        directory."""
        mod = self._spa_conftest()
        spa_dir = mod._SPA_DIR
        item = _FakeItem(f"{spa_dir}/test_m3_tokens.py")
        mod.pytest_collection_modifyitems(None, [item])
        names = item._mark_names()
        self.assertIn("slow", names)
        self.assertNotIn("xdist_group", names)
        self.assertNotIn("spa_jsdom_serial", names)

    def test_files_outside_spa_dir_are_untouched(self):
        mod = self._spa_conftest()
        item = _FakeItem(str(PROJECT_ROOT / "tests" / "test_something_else.py"))
        mod.pytest_collection_modifyitems(None, [item])
        self.assertEqual(item.added_markers, [])

    def test_xdist_group_marker_registered_by_the_plugin(self):
        """xdist_group is provided by pytest-xdist itself (an EXISTING
        mechanism) — sanity-check the plugin is actually installed so the
        marker isn't silently a no-op typo."""
        import xdist
        self.assertTrue(hasattr(xdist, "__version__"))

    def test_spa_jsdom_serial_marker_documented_in_pytest_ini(self):
        ini = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
        self.assertIn("spa_jsdom_serial:", ini)


if __name__ == "__main__":
    unittest.main()
