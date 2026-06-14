# -*- coding: utf-8 -*-
"""tests/test_durable_loop.py — unit tests for the durable-loop scheduler builders.

Covers the PURE builders + the cross-platform `--dry-run` path of
tools/durable_loop.py (the disk-persisted Windows Task Scheduler wrapper for the
autonomous dev loop). The actual `schtasks` register/fire/disarm is Windows-side-
effecting and is validated manually, not in the suite.
"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "durable_loop", str(PROJECT_ROOT / "tools" / "durable_loop.py"))
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)


class TestPermFlag(unittest.TestCase):
    def test_bypass(self):
        self.assertEqual(dl.perm_flag("bypass"), "--dangerously-skip-permissions")

    def test_accept_edits(self):
        self.assertEqual(dl.perm_flag("accept-edits"), "--permission-mode acceptEdits")

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            dl.perm_flag("nope")


class TestLauncher(unittest.TestCase):
    def test_claude_launcher_shape(self):
        out = dl.build_launcher(
            workdir="C:/SW_MUSH_night", claude_exe="C:/c/claude.exe",
            prompt_file="C:/s/prompt.txt", log_dir="C:/s/logs",
            model="opus", perm_mode="bypass")
        self.assertIn('cd /d "C:/SW_MUSH_night"', out)
        self.assertIn('type "C:/s/prompt.txt"', out)
        self.assertIn('"C:/c/claude.exe" -p --dangerously-skip-permissions --model opus', out)
        self.assertIn('> "C:/s/logs\\run_%TS%.log" 2>&1', out)
        self.assertTrue(out.startswith("@echo off"))
        self.assertIn("\r\n", out)  # CRLF for a .cmd

    def test_test_fire_launcher_has_no_claude(self):
        out = dl.build_launcher(
            workdir="C:/w", claude_exe="C:/c/claude.exe", prompt_file="p",
            log_dir="C:/l", model="opus", perm_mode="bypass",
            raw_action='echo hi & echo OK')
        self.assertNotIn("claude.exe", out)
        self.assertIn("echo hi & echo OK", out)
        self.assertIn('> "C:/l\\run_%TS%.log" 2>&1', out)

    def test_accept_edits_mode_in_launcher(self):
        out = dl.build_launcher("C:/w", "claude", "p", "C:/l", "opus", "accept-edits")
        self.assertIn("--permission-mode acceptEdits", out)


class TestTaskXml(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 6, 14, 22, 30, 0)

    def test_recurring_has_repetition_and_durability_settings(self):
        xml = dl.build_task_xml("C:/s/launcher.cmd", start_dt=self.start, every_minutes=20)
        self.assertIn("<Interval>PT20M</Interval>", xml)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", xml)
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", xml)
        self.assertIn("<StartBoundary>2026-06-14T22:30:00</StartBoundary>", xml)
        self.assertIn("<ExecutionTimeLimit>PT2H</ExecutionTimeLimit>", xml)
        self.assertIn('/c "C:/s/launcher.cmd"', xml)
        self.assertIn("<Command>cmd.exe</Command>", xml)
        self.assertIn('version="1.2"', xml)

    def test_one_shot_has_no_repetition(self):
        xml = dl.build_task_xml("C:/s/launcher.cmd", start_dt=self.start, every_minutes=None)
        self.assertNotIn("<Repetition>", xml)
        self.assertIn("<StartBoundary>2026-06-14T22:30:00</StartBoundary>", xml)

    def test_xml_is_well_formed(self):
        import xml.dom.minidom as minidom
        for every in (None, 15):
            xml = dl.build_task_xml("C:/s/l.cmd", start_dt=self.start, every_minutes=every)
            minidom.parseString(xml)  # raises on malformed XML


class TestDefaultPrompt(unittest.TestCase):
    def test_mentions_handoff_and_foreground_gate(self):
        p = dl.default_prompt("C:/SW_MUSH_night")
        self.assertIn("HANDOFF", p)
        self.assertIn("C:/SW_MUSH_night", p)
        self.assertIn("FOREGROUND", p.upper())
        # the durability lesson must be baked into the resume prompt:
        self.assertIn("notification", p.lower())


class TestDryRunCrossPlatform(unittest.TestCase):
    def test_dry_run_returns_zero_without_registering(self):
        # --dry-run must work on any platform (no schtasks side effects).
        rc = dl.main(["arm", "--in", "120", "--dry-run",
                      "--workdir", str(PROJECT_ROOT), "--name", "UNITTEST-DL"])
        self.assertEqual(rc, 0)
        # nothing should have been written to the state dir for a dry run
        self.assertFalse((dl.STATE_ROOT / "UNITTEST-DL" / "task.xml").exists())


if __name__ == "__main__":
    unittest.main()
