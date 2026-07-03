# -*- coding: utf-8 -*-
"""
tests/test_hygiene_batch_2026_07_03.py — Fable F6 hygiene-batch pins.

Small, independent, low-risk cleanups landed together (drop
hygiene-batch-f6, 2026-07-03):

  1. mapgen accidental-commit red — tools/mapgen/term_boundaries.json's
     `terms` key must stay `{}` at rest (already pinned by
     tests/test_mapgen_pipeline_offline.py::TestBoundarySeedFile; this
     file adds a metadata-preservation check).
  2. F6.1 — the generic `npcs:` loader (engine/npc_loader.py) must not
     warn on a file that's correctly keyed for a sibling loader
     (wilderness_npcs: / jedi_village_npcs:).
  3. F6.2 — the help-loader duplicate-key warnings for anomalies/force/
     salvage are gone: the live-command docs (commands/*.md) now own
     those exact keys; the lore/rules docs moved to distinct keys
     (space_anomalies / the_force / space_salvage) with no alias
     collisions.
  4. F6.3 — tests/spa/test_m3_tokens.py's WoundLevel locator regex
     actually finds engine.character.WoundLevel (was silently skipping
     forever because of the class's docstring line).
  5. F6.5 — .here-wound-crit now uses a distinct --warn-crit color
     var (not just bold-on---warn) for colorblind legibility.
  6. F6.4 — GCW display-string residue in engine/territory.py
     (_GUARD_TEMPLATES) / engine/contest.py (_REGION_ANCHOR_TEMPLATES)
     / territory.get_zone_influence_line()'s flavor dict is
     deliberately NOT stripped (the rewicker migration may still
     reference the code paths), but is proven unreachable: the sole
     producer of a live org_code is
     engine.organizations.seed_organizations(), which reads `code:`
     off data/worlds/<era>/organizations.yaml. Clone Wars (the only
     live era) never assigns 'empire' or 'rebel' as a code.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import re
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────
# 1. mapgen accidental-commit red
# ──────────────────────────────────────────────────────────────────────

class TestMapgenBoundarySeedMetadataPreserved(unittest.TestCase):
    """Companion to test_mapgen_pipeline_offline.py's terms=={} pin: also
    confirm the _note/_schema metadata survived the empty-out edit."""

    def test_terms_empty_note_and_schema_preserved(self):
        path = PROJECT_ROOT / "tools" / "mapgen" / "term_boundaries.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("terms"), {})
        self.assertIn("_note", data, "the hand-editable _note breadcrumb was dropped")
        self.assertIn("_schema", data, "the _schema version marker was dropped")
        self.assertIn("Empty until the first live batch runs", data["_note"])

    def test_style_ref_experiment_test_no_longer_leaks_into_tracked_seed(self):
        """Root cause of the accidental-commit red, found running the FULL
        suite gate for this drop: tests/test_mapgen_style_ref_experiment.py
        ::TestStyleRefExperimentOffline redirected SEEDS_DIR/BATCHES_DIR/
        MAPS_DIR but NOT TERM_BOUNDARIES_FILE, so its mock run's on-theme
        'cantina'/'starship' terms (detected in the real mos_eisley paint
        brief) got written straight into the git-tracked
        tools/mapgen/term_boundaries.json on every run — silently re-dirtying
        the committed-empty seed this drop's item 1 fixed. Runs the actual
        offending test class, then asserts the tracked file is untouched."""
        path = PROJECT_ROOT / "tools" / "mapgen" / "term_boundaries.json"
        before = path.read_text(encoding="utf-8")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_mapgen_style_ref_experiment.py::TestStyleRefExperimentOffline",
             "-q", "-m", ""],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120,
        )
        self.assertIn("passed", result.stdout, result.stdout)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(
            before, after,
            "TestStyleRefExperimentOffline must not mutate the git-tracked "
            "term_boundaries.json — TERM_BOUNDARIES_FILE must stay redirected",
        )
        self.assertEqual(json.loads(after).get("terms"), {})


# ──────────────────────────────────────────────────────────────────────
# 2. F6.1 — generic npcs: loader silently skips sibling-schema files
# ──────────────────────────────────────────────────────────────────────

class TestNpcLoaderSkipsSiblingSchemaSilently(unittest.TestCase):
    """engine.npc_loader.load_npcs_from_yaml() must not WARN on a file
    correctly keyed wilderness_npcs:/jedi_village_npcs: (owned by a
    sibling loader pass), but must still WARN on a genuinely broken
    file with none of the known schema keys."""

    def test_wilderness_npcs_keyed_file_no_warning(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sibling.yaml"
            p.write_text(
                yaml.safe_dump({"wilderness_npcs": [{"name": "x", "room": "y"}]}),
                encoding="utf-8",
            )
            logger = logging.getLogger("engine.npc_loader")
            records = []
            handler = logging.Handler()
            handler.emit = lambda r: records.append(r)
            logger.addHandler(handler)
            try:
                from engine.npc_loader import load_npcs_from_yaml
                result = load_npcs_from_yaml(str(p), {})
            finally:
                logger.removeHandler(handler)
            self.assertEqual(result, [])
            warnings = [r for r in records if r.levelno >= logging.WARNING]
            self.assertEqual(
                warnings, [],
                f"sibling-schema file should not warn, got: {[r.getMessage() for r in warnings]}",
            )

    def test_jedi_village_npcs_keyed_file_no_warning(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sibling2.yaml"
            p.write_text(
                yaml.safe_dump({"jedi_village_npcs": [{"name": "x", "room": "y"}]}),
                encoding="utf-8",
            )
            logger = logging.getLogger("engine.npc_loader")
            records = []
            handler = logging.Handler()
            handler.emit = lambda r: records.append(r)
            logger.addHandler(handler)
            try:
                from engine.npc_loader import load_npcs_from_yaml
                result = load_npcs_from_yaml(str(p), {})
            finally:
                logger.removeHandler(handler)
            self.assertEqual(result, [])
            warnings = [r for r in records if r.levelno >= logging.WARNING]
            self.assertEqual(warnings, [])

    def test_genuinely_broken_file_still_warns(self):
        """A file with neither `npcs:` nor a known sibling key is a real
        authoring mistake — must still surface the warning."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "broken.yaml"
            p.write_text(yaml.safe_dump({"something_else": []}), encoding="utf-8")
            logger = logging.getLogger("engine.npc_loader")
            records = []
            handler = logging.Handler()
            handler.emit = lambda r: records.append(r)
            logger.addHandler(handler)
            try:
                from engine.npc_loader import load_npcs_from_yaml
                result = load_npcs_from_yaml(str(p), {})
            finally:
                logger.removeHandler(handler)
            self.assertEqual(result, [])
            warnings = [r for r in records if r.levelno >= logging.WARNING]
            self.assertTrue(warnings, "a genuinely-broken npcs file should still warn")

    def test_real_mob_grind_file_no_longer_warns_via_era_sweep(self):
        """The actual F6.1 offender: npcs_drop_mob_grind_coruscant_underworld
        .yaml is listed under BOTH content_refs.wilderness_npcs (correct
        loader) AND content_refs.npcs (the generic sweep, era.yaml is
        off-limits for this drop so the duplicate listing stays) —
        confirm the generic sweep no longer warns on it."""
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "npcs_drop_mob_grind_coruscant_underworld.yaml")
        self.assertTrue(path.is_file())
        logger = logging.getLogger("engine.npc_loader")
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        logger.addHandler(handler)
        try:
            from engine.npc_loader import load_npcs_from_yaml
            load_npcs_from_yaml(str(path), {})
        finally:
            logger.removeHandler(handler)
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        self.assertEqual(
            warnings, [],
            f"expected silent skip, got: {[r.getMessage() for r in warnings]}",
        )


# ──────────────────────────────────────────────────────────────────────
# 3. F6.2 — help dup keys deduped, no boot warning
# ──────────────────────────────────────────────────────────────────────

class TestHelpDupKeysDeduped(unittest.TestCase):
    """anomalies/force/salvage no longer collide across data/help/commands
    and data/help/topics; the live-command doc wins the exact key, and
    the lore/rules doc moved to a distinct key with no alias collision."""

    def _load_no_warn(self):
        from engine.help_loader import load_help_directory
        from data.help_topics import HelpEntry
        logger = logging.getLogger("engine.help_loader")
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        logger.addHandler(handler)
        try:
            entries = list(load_help_directory(
                str(PROJECT_ROOT / "data" / "help"), HelpEntry))
        finally:
            logger.removeHandler(handler)
        warnings = [r for r in records if r.levelno >= logging.WARNING]
        dup_warnings = [r for r in warnings if "duplicate key" in r.getMessage()]
        return entries, dup_warnings

    def test_no_duplicate_key_warnings_at_all(self):
        _, dup_warnings = self._load_no_warn()
        self.assertEqual(
            dup_warnings, [],
            f"unexpected duplicate-key warnings: {[r.getMessage() for r in dup_warnings]}",
        )

    def test_command_docs_own_the_exact_command_keys(self):
        entries, _ = self._load_no_warn()
        by_key = {e.key: e for e in entries}
        self.assertEqual(by_key["anomalies"].category, "Commands: Wilderness")
        self.assertEqual(by_key["force"].category, "Commands: Force")
        self.assertEqual(by_key["salvage"].category, "Commands: Ships")

    def test_lore_topics_moved_to_distinct_keys(self):
        entries, _ = self._load_no_warn()
        by_key = {e.key: e for e in entries}
        self.assertIn("space_anomalies", by_key)
        self.assertIn("the_force", by_key)
        self.assertIn("space_salvage", by_key)
        self.assertEqual(by_key["space_anomalies"].category, "Rules: Space")
        self.assertEqual(by_key["the_force"].category, "Rules: Force")
        self.assertEqual(by_key["space_salvage"].category, "Rules: Space")

    def test_alias_anom_resolves_to_the_ground_command(self):
        """anom is the live ground `anomalies` command's own alias
        (parser/anomaly_commands.py); it must not be shadowed by the
        space deepscan topic's alias list."""
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files(str(PROJECT_ROOT / "data" / "help"))
        entry = mgr.get("anom")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "anomalies")

    def test_alias_deepscan_still_resolves_to_space_topic(self):
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files(str(PROJECT_ROOT / "data" / "help"))
        entry = mgr.get("deepscan")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "space_anomalies")

    def test_alias_useforce_still_resolves(self):
        from data.help_topics import HelpManager
        mgr = HelpManager()
        mgr.load_markdown_files(str(PROJECT_ROOT / "data" / "help"))
        entry = mgr.get("useforce")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "the_force")


# ──────────────────────────────────────────────────────────────────────
# 4. F6.3 — spa WoundLevel locator regex actually matches
# ──────────────────────────────────────────────────────────────────────

class TestSpaWoundLevelLocatorFixed(unittest.TestCase):
    """Meta-pin: the same regex technique tests/spa/test_m3_tokens.py
    now uses must locate engine.character.WoundLevel(IntEnum) and parse
    its 7 members, independent of whatever else that test file does."""

    def test_regex_locates_and_parses_wound_level(self):
        char_py = PROJECT_ROOT / "engine" / "character.py"
        content = char_py.read_text(encoding="utf-8")
        m = re.search(
            r"class WoundLevel\(IntEnum\):\s*\n"
            r'(?:\s*"""[\s\S]*?"""\s*\n)?'
            r"((?:\s+[A-Z_]+\s*=\s*\d+\s*\n)+)",
            content,
        )
        self.assertIsNotNone(m, "WoundLevel locator regex failed to match HEAD")
        levels = {}
        for line in m.group(1).strip().splitlines():
            name, value = line.strip().split("=")
            levels[int(value.strip())] = name.strip()
        self.assertEqual(sorted(levels.keys()), [0, 1, 2, 3, 4, 5, 6])

    def test_target_test_is_not_skipped(self):
        """Run the actual pinned test and confirm it executes (not
        skipped) — the whole point of the F6.3 fix."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/spa/test_m3_tokens.py::test_parity_with_engine_wound_level_enum",
             "-v", "-m", ""],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120,
        )
        self.assertNotIn("SKIPPED", result.stdout, result.stdout)
        self.assertIn("PASSED", result.stdout, result.stdout)


# ──────────────────────────────────────────────────────────────────────
# 5. F6.5 — colorblind-safe crit wound color
# ──────────────────────────────────────────────────────────────────────

class TestWoundCritColorDistinct(unittest.TestCase):
    def test_warn_crit_var_defined_in_both_themes(self):
        html = (PROJECT_ROOT / "static" / "client.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            html.count("--warn-crit"), 3,
            "expected --warn-crit declared in both themes + used by .here-wound-crit",
        )

    def test_here_wound_crit_uses_distinct_var(self):
        html = (PROJECT_ROOT / "static" / "client.html").read_text(encoding="utf-8")
        m = re.search(r"\.here-wound-crit\s*\{([^}]*)\}", html)
        self.assertIsNotNone(m)
        self.assertIn("--warn-crit", m.group(1))

    def test_here_wound_hurt_unchanged(self):
        html = (PROJECT_ROOT / "static" / "client.html").read_text(encoding="utf-8")
        m = re.search(r"\.here-wound-hurt\s*\{([^}]*)\}", html)
        self.assertIsNotNone(m)
        self.assertIn("var(--warn)", m.group(1))
        self.assertNotIn("--warn-crit", m.group(1))


# ──────────────────────────────────────────────────────────────────────
# 6. F6.4 — GCW display-string residue proven unreachable on Clone Wars
# ──────────────────────────────────────────────────────────────────────

class TestGCWDisplayStringResidueUnreachable(unittest.TestCase):
    """engine/territory.py::_GUARD_TEMPLATES / engine/contest.py::
    _REGION_ANCHOR_TEMPLATES / territory.get_zone_influence_line()'s
    flavor dict all still carry dormant 'empire'/'rebel' entries by
    design (NOT stripped — the rewicker migration may still reference
    the code paths). This guards that they can never actually fire:
    the sole producer of a live DB org_code is
    engine.organizations.seed_organizations(), reading `code:` off
    data/worlds/<era>/organizations.yaml's factions/guilds lists.
    """

    GCW_CODES = {"empire", "rebel"}

    def _live_cw_org_codes(self):
        path = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "organizations.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        codes = {f["code"] for f in (data.get("factions") or [])}
        codes |= {g["code"] for g in (data.get("guilds") or [])}
        return codes

    def test_live_cw_organizations_yaml_has_no_gcw_codes(self):
        codes = self._live_cw_org_codes()
        leaked = codes & self.GCW_CODES
        self.assertFalse(
            leaked, f"data/worlds/clone_wars/organizations.yaml defines GCW "
                     f"org code(s) {leaked} — the residue templates would "
                     f"become reachable"
        )

    def test_seed_organizations_reads_the_file_and_fields_this_guard_assumes(self):
        """Anchor against silent drift: if seed_organizations ever reads a
        different file or a different field name for the org code, this
        guard would be checking the wrong thing without knowing it."""
        from engine.organizations import seed_organizations
        src = inspect.getsource(seed_organizations)
        self.assertIn('"organizations.yaml"', src)
        self.assertIn('faction["code"]', src)
        self.assertIn('guild["code"]', src)

    def test_default_era_is_clone_wars_not_gcw(self):
        """The residue is scoped 'dormant on Clone Wars' because CW is
        the only production era — pin that the default hasn't reverted."""
        from engine.era_state import get_active_era, clear_active_config
        clear_active_config()
        self.assertEqual(get_active_era(), "clone_wars")

    def test_no_cw_world_yaml_assigns_org_or_faction_code_empire_or_rebel(self):
        """Defense in depth: scan every YAML under the live era directory
        for a literal org/faction/code field set to empire/rebel (would
        be a second, undiscovered producer of a live org_code)."""
        cw_dir = PROJECT_ROOT / "data" / "worlds" / "clone_wars"
        offenders = []
        pattern = re.compile(
            r'^\s*(?:code|org_code|org|faction_code)\s*:\s*["\']?(empire|rebel)["\']?\s*$',
            re.MULTILINE,
        )
        for p in cw_dir.rglob("*.yaml"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                offenders.append(str(p.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
