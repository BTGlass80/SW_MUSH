# -*- coding: utf-8 -*-
"""
Authoritative cross-check guard for Guide_20_Scenes_Plots_Places.md (Opus quality
pass, 2026-06-23).

Guide_20 was the only player guide with no test guard and no authoritative pass.
The pass verified every mechanical claim against HEAD and corrected three factual
defects the guide carried since v1.0:

  1. §12 "Recent scenes list cap | 30"   -> the bare `+scenes` (your recent
     scenes) list is capped at 15 (engine.scenes.get_char_scenes default); 30 is
     the SHARED / closed archive cap, not the personal recent-scenes cap.
  2. §12 "Max places per room | unlimited" -> @places caps the count at 1..20.
  3. §9 quick-ref `mutter <player> <message>` -> the `=` separator is REQUIRED
     (`mutter <player> = <message>`, as §6 already showed).

This guard pins the documented numbers/commands to the live engine constants,
the function-signature defaults, and the parser source so the guide cannot
silently rot back. Pure cross-check: imports the live scene/plot modules and
reads the guide + parser source as text. No DB, no server.
"""

import inspect
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_20_Scenes_Plots_Places.md")
SCENE_CMD_PATH = os.path.join(PROJECT_ROOT, "parser", "scene_commands.py")
PLOT_CMD_PATH = os.path.join(PROJECT_ROOT, "parser", "plot_commands.py")
PLACES_CMD_PATH = os.path.join(PROJECT_ROOT, "parser", "places_commands.py")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _default(fn, param):
    return inspect.signature(fn).parameters[param].default


class TestGuide20Exists(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(os.path.exists(GUIDE_PATH))

    def test_version_bumped(self):
        body = _read(GUIDE_PATH)
        self.assertIn("Guide Version 1.1", body)


class TestGuide20LiveEngineConstants(unittest.TestCase):
    """Pin the documented numbers to the live engine constants/signatures."""

    def test_scene_types_match_engine(self):
        from engine import scenes as sm
        # §3 / §9 / §12 all list exactly these four scene types.
        self.assertEqual(sm.SCENE_TYPES, ("Social", "Action", "Plot", "Vignette"))

    def test_pose_modes_match_engine(self):
        from engine import scenes as sm
        # §3 documents the two pose-order modes by these exact names.
        self.assertEqual(sm.POSE_MODE_ROUNDROBIN, "round-robin")
        self.assertEqual(sm.POSE_MODE_THREEPOSE, "3-per")
        self.assertEqual(set(sm.POSE_MODES), {"round-robin", "3-per"})

    def test_recent_scenes_cap_is_15(self):
        from engine import scenes as sm
        # §12 "Your recent scenes cap (`+scenes`) | 15" — the bare +scenes list
        # calls get_char_scenes with no limit, so its default IS the cap.
        self.assertEqual(_default(sm.get_char_scenes, "limit"), 15)

    def test_shared_archive_cap_is_30(self):
        from engine import scenes as sm
        # §12 "Shared / closed archive lists cap | 30".
        self.assertEqual(_default(sm.get_shared_scenes, "limit"), 30)
        self.assertEqual(_default(sm.get_player_shared_scenes, "limit"), 30)

    def test_open_plots_cap_is_30(self):
        from engine import plots as pm
        # §12 "Open plots list cap | 30".
        self.assertEqual(_default(pm.get_open_plots, "limit"), 30)


class TestGuide20PlacesBounds(unittest.TestCase):
    """The @places count is bounded 1..20 (NOT unlimited)."""

    def test_places_count_capped_at_20_in_source(self):
        src = _read(PLACES_CMD_PATH)
        self.assertIn("count < 1 or count > 20", src)

    def test_place_fields_are_name_max_desc_prefix(self):
        src = _read(PLACES_CMD_PATH)
        # §8 / §9 document exactly these four configurable fields.
        self.assertIn('("name", "max", "desc", "prefix")', src)

    def test_guide_documents_1_to_20_not_unlimited(self):
        body = _read(GUIDE_PATH)
        self.assertIn("Max places per room | 1", body)
        # The old phantom "unlimited" claim must not return.
        self.assertNotIn("Max places per room | unlimited", body)


class TestGuide20CommandSurface(unittest.TestCase):
    """Every command the guide documents must exist at HEAD with the right key."""

    def test_scene_command_keys(self):
        src = _read(SCENE_CMD_PATH)
        self.assertIn('key = "+scene"', src)
        self.assertIn('key = "+scenes"', src)

    def test_scene_subcommands_dispatched(self):
        src = _read(SCENE_CMD_PATH)
        for sub in ("start", "stop", "title", "type", "summary",
                    "share", "unshare", "poseorder", "drop", "mode"):
            self.assertIn(f'sub == "{sub}"', src,
                          f"+scene/{sub} no longer dispatched")

    def test_plot_command_keys_and_arcs_alias(self):
        src = _read(PLOT_CMD_PATH)
        self.assertIn('key = "+plots"', src)
        self.assertIn('key = "+plot"', src)
        # §4 documents `+arcs` as an alias for +plots.
        self.assertIn('"+arcs"', src)

    def test_plot_subcommands_dispatched(self):
        src = _read(PLOT_CMD_PATH)
        for sub in ("create", "summary", "link", "unlink", "close", "reopen"):
            self.assertIn(f'sub == "{sub}"', src,
                          f"+plot/{sub} no longer dispatched")

    def test_plots_filter_keywords(self):
        # §4: `+plots closed` and `+plots all`.
        src = _read(PLOT_CMD_PATH)
        self.assertIn('"closed"', src)
        self.assertIn('"all"', src)

    def test_places_player_command_keys(self):
        src = _read(PLACES_CMD_PATH)
        for key in ('key = "places"', 'key = "join"', 'key = "depart"',
                    'key = "tt"', 'key = "ttooc"', 'key = "mutter"'):
            self.assertIn(key, src, f"{key} missing")
        # Documented aliases.
        self.assertIn('aliases = ["sit"]', src)
        self.assertIn('aliases = ["stand"]', src)

    def test_places_builder_command_keys(self):
        src = _read(PLACES_CMD_PATH)
        for key in ('key = "@places"', 'key = "@place"', 'key = "@osucc"',
                    'key = "@ofail"', 'key = "@odrop"'):
            self.assertIn(key, src, f"{key} missing")


class TestGuide20MutterSyntax(unittest.TestCase):
    """The §9 quick-ref must show the required `=` separator (matches §6 + HEAD)."""

    def test_mutter_usage_requires_equals_in_engine(self):
        src = _read(PLACES_CMD_PATH)
        # The live command splits on "=" and its usage string carries the "=".
        self.assertIn("mutter <player> = <message>", src)

    def test_guide_quick_ref_mutter_has_equals(self):
        body = _read(GUIDE_PATH)
        self.assertIn("`mutter <player> = <message>`", body)
        # The bad (no-`=`) quick-ref form must not return.
        self.assertNotIn("`mutter <player> <message>`", body)


if __name__ == "__main__":
    unittest.main()
