# -*- coding: utf-8 -*-
"""
tests/test_kd5b_sweep_npc_space_traffic.py — K-D5b-sweep tests.

Per architecture v38 §19.4 K-D5b-sweep and the apr 28 wrap doc:
`engine/npc_space_traffic.py` had 7 unguarded `json.loads(...)` sites
beyond the 24 the K-D5b-int drop swept (lines 1097, 1368, 1381, 1383,
1395, 1568, 1595 in pre-sweep HEAD). All 7 follow the "ship.systems"
or "ship.crew" pattern that crashes on corrupt DB rows and takes the
space-tick handler with it.

This drop swaps each unguarded site to use the existing
`engine.json_safe.load_ship_systems(ship)` and
`engine.json_safe.safe_json_loads(raw, default=..., context=...)`
helpers (already imported at the top of the file).

Tests cover:

  1. STATIC GATE — the bulk sweep guarantee. After this drop, the
     module body must contain ZERO `json.loads(` call sites. This
     is the asymmetric "fail pre-drop, pass post-drop" gate.

  2. IMPORT WIRING — `safe_json_loads` and `load_ship_systems` are
     both still imported (the helpers must be in scope for the swept
     sites to compile).

  3. BEHAVIOR — `_find_char_zone` and `_find_char_ship_id` no longer
     raise `JSONDecodeError` when a DB row's `crew` or `systems`
     column is corrupt (typed against the real method names with
     a synthetic DB).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


_MODULE_PATH = os.path.join(
    PROJECT_ROOT, "engine", "npc_space_traffic.py"
)


# ──────────────────────────────────────────────────────────────────────
# 1. STATIC GATE — no remaining json.loads sites
# ──────────────────────────────────────────────────────────────────────

class TestNoRemainingJsonLoadsSites(unittest.TestCase):
    """Asymmetric: this test FAILS pre-sweep, PASSES post-sweep.

    The sweep guarantee is module-wide: after this drop, no call to
    bare `json.loads(` remains in `engine/npc_space_traffic.py`. The
    file may still `import json` (used elsewhere or for json.dumps),
    but no `json.loads(` token may appear.
    """

    def setUp(self):
        with open(_MODULE_PATH, encoding="utf-8") as f:
            self.source = f.read()

    def test_no_bare_json_loads_calls(self):
        # Match `json.loads(` — but not `safe_json_loads(` or comments
        # mentioning "json.loads" inside docstrings/comments.
        # The simplest reliable check is line-by-line, skipping lines
        # that are wholly comments or are inside docstrings. Since
        # we only care about EXECUTABLE call sites, we use a tokenize
        # pass.
        import tokenize, io
        offending = []
        with open(_MODULE_PATH, "rb") as f:
            tokens = list(tokenize.tokenize(f.readline))
        # Look for a NAME 'json' followed by '.' followed by NAME 'loads'.
        for i in range(len(tokens) - 2):
            t1, t2, t3 = tokens[i], tokens[i + 1], tokens[i + 2]
            if (t1.type == tokenize.NAME and t1.string == "json"
                    and t2.type == tokenize.OP and t2.string == "."
                    and t3.type == tokenize.NAME and t3.string == "loads"):
                offending.append(t1.start[0])  # line number

        self.assertEqual(
            offending, [],
            f"Found bare json.loads call(s) at line(s): {offending}. "
            f"Sweep is incomplete."
        )

    def test_helper_imports_present(self):
        """Both helpers must still be imported."""
        self.assertIn(
            "from engine.json_safe import",
            self.source,
        )
        self.assertIn("safe_json_loads", self.source)
        self.assertIn("load_ship_systems", self.source)

    def test_swept_sites_use_helpers(self):
        """Sanity: at least 5 calls to load_ship_systems and at least
        2 calls to safe_json_loads (matching the 7 swept sites)."""
        # Count call sites, not bare references.
        sys_calls = len(re.findall(r"\bload_ship_systems\s*\(", self.source))
        crew_calls = len(re.findall(r"\bsafe_json_loads\s*\(", self.source))
        self.assertGreaterEqual(
            sys_calls, 5,
            f"Expected ≥5 load_ship_systems() calls; found {sys_calls}"
        )
        self.assertGreaterEqual(
            crew_calls, 2,
            f"Expected ≥2 safe_json_loads() calls; found {crew_calls}"
        )


# ──────────────────────────────────────────────────────────────────────
# 2. BEHAVIOR — corrupt rows no longer crash
# ──────────────────────────────────────────────────────────────────────

class TestCorruptRowsDoNotCrash(unittest.TestCase):
    """Behavior gate: the swept methods now log and continue rather
    than raising JSONDecodeError on corrupt rows."""

    def _mock_db(self, ship_rows):
        db = MagicMock()
        db.get_ships_in_space = AsyncMock(return_value=ship_rows)
        return db

    def test_find_char_zone_with_corrupt_crew_returns_none(self):
        """Pre-sweep: crashed with JSONDecodeError. Post-sweep: returns
        None gracefully."""
        from engine.npc_space_traffic import NpcSpaceTrafficManager
        mgr = NpcSpaceTrafficManager()
        # crew column is unparseable JSON — pre-sweep this raised.
        rows = [
            {"id": 99, "crew": "not_json{{{", "systems": "{}"},
        ]
        db = self._mock_db(rows)
        result = _run(mgr._find_char_zone(42, db))
        self.assertIsNone(result)

    def test_find_char_zone_with_corrupt_systems_returns_none(self):
        """Crew is fine, systems is corrupt → still graceful."""
        from engine.npc_space_traffic import NpcSpaceTrafficManager
        mgr = NpcSpaceTrafficManager()
        rows = [
            {"id": 99, "crew": '{"pilot": 42}',
             "systems": "ALSO_NOT_JSON{{"},
        ]
        db = self._mock_db(rows)
        # Char 42 is in crew, but systems parse fails. Returns None
        # (because load_ship_systems falls back to {} → no current_zone).
        result = _run(mgr._find_char_zone(42, db))
        self.assertIsNone(result)

    def test_find_char_zone_happy_path_still_works(self):
        """Byte-equivalence: well-formed JSON still returns the zone."""
        from engine.npc_space_traffic import NpcSpaceTrafficManager
        mgr = NpcSpaceTrafficManager()
        rows = [
            {"id": 99, "crew": '{"pilot": 42}',
             "systems": '{"current_zone": "tatooine_orbit"}'},
        ]
        db = self._mock_db(rows)
        result = _run(mgr._find_char_zone(42, db))
        self.assertEqual(result, "tatooine_orbit")

    def test_find_char_ship_id_with_corrupt_crew_returns_none(self):
        from engine.npc_space_traffic import NpcSpaceTrafficManager
        mgr = NpcSpaceTrafficManager()
        rows = [
            {"id": 88, "crew": "garbage", "systems": "{}"},
        ]
        db = self._mock_db(rows)
        result = _run(mgr._find_char_ship_id(42, db))
        self.assertIsNone(result)

    def test_find_char_ship_id_happy_path_still_works(self):
        from engine.npc_space_traffic import NpcSpaceTrafficManager
        mgr = NpcSpaceTrafficManager()
        rows = [
            {"id": 88, "crew": '{"pilot": 42}', "systems": "{}"},
        ]
        db = self._mock_db(rows)
        result = _run(mgr._find_char_ship_id(42, db))
        self.assertEqual(result, 88)


# ──────────────────────────────────────────────────────────────────────
# 3. IMPORT-LEVEL SANITY
# ──────────────────────────────────────────────────────────────────────

class TestModuleImportsCleanly(unittest.TestCase):
    """A failed sweep that introduces a SyntaxError or NameError would
    surface here as an ImportError."""

    def test_module_imports(self):
        import importlib
        mod = importlib.import_module("engine.npc_space_traffic")
        # Smoke: helper symbols are accessible from the module's namespace.
        self.assertTrue(hasattr(mod, "load_ship_systems"))
        self.assertTrue(hasattr(mod, "safe_json_loads"))
        self.assertTrue(hasattr(mod, "NpcSpaceTrafficManager"))


if __name__ == "__main__":
    unittest.main()
