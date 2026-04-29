# -*- coding: utf-8 -*-
"""
tests/test_f6a6_boot_ordering.py — F.6a.6 boot-ordering tripwire.

The F.6a.6 plumbing depends on a strict ordering at boot:

  1. Build the Config (with era flags resolved from CLI / defaults).
  2. Call engine.era_state.set_active_config(config).
  3. THEN import server.game_server (which transitively imports
     engine/director.py, which resolves its module-level constants
     through the F.6a.3 seam at import time).

If steps 2 and 3 are reversed, director.py captures the default
(no-era) state and the flag flip silently no-ops.

These tests use subprocess-spawned fresh Python interpreters because
once the test process has imported `engine.director`, the module-level
constants are frozen for the lifetime of the process.

Coverage:
  - With the flag OFF (default), director's constants are the legacy
    GCW values regardless of import order — no regression risk.
  - With the flag ON and config registered BEFORE import, director's
    constants reflect the era YAML (Clone Wars).
  - With the flag ON but config registered AFTER import, director's
    constants are the legacy values — proves the ordering matters.
  - main.py's CLI flag plumbing is wired correctly: passing
    --era=clone_wars --use-yaml-director-data sets the right Config
    fields. (Tested via subprocess invocation of main.py with --help.)
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))


def _run_python(script: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a Python script in a fresh subprocess from PROJECT_ROOT.

    Returns (returncode, stdout, stderr).
    """
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ══════════════════════════════════════════════════════════════════════════════
# Boot-ordering correctness
# ══════════════════════════════════════════════════════════════════════════════


class TestBootOrderingFlagOff(unittest.TestCase):
    """With the flag OFF (default Config), director's constants must
    be the legacy GCW values. Any import order should produce the
    same result because the seam returns legacy when no era is asked
    for."""

    def test_default_config_no_active_config_legacy_constants(self):
        # No set_active_config call at all. era_state returns its
        # defaults, which means resolve_era_for_seeding -> None,
        # which means the seam returns legacy.
        script = textwrap.dedent("""
            import sys
            from engine import director
            print("source:", director._RUNTIME_CFG.source)
            print("factions:", sorted(director.VALID_FACTIONS))
            print("zones:", sorted(director.DEFAULT_INFLUENCE.keys()))
        """)
        rc, out, err = _run_python(script)
        self.assertEqual(rc, 0, f"subprocess failed: {err}")
        self.assertIn("source: legacy", out)
        # Legacy GCW factions
        self.assertIn(
            "factions: ['criminal', 'imperial', 'independent', 'rebel']",
            out,
        )
        # Legacy GCW zones
        self.assertIn(
            "zones: ['cantina', 'government', 'jabba', 'shops', "
            "'spaceport', 'streets']",
            out,
        )

    def test_config_registered_but_flag_off_legacy_constants(self):
        # Config built with use_yaml_director_data=False (default),
        # set_active_config called BEFORE director import. Should
        # still resolve to legacy because the flag is off.
        script = textwrap.dedent("""
            from server.config import Config
            from engine.era_state import set_active_config
            cfg = Config(active_era="clone_wars",
                         use_yaml_director_data=False)
            set_active_config(cfg)
            from engine import director
            print("source:", director._RUNTIME_CFG.source)
            print("factions:", sorted(director.VALID_FACTIONS))
        """)
        rc, out, err = _run_python(script)
        self.assertEqual(rc, 0, f"subprocess failed: {err}")
        self.assertIn("source: legacy", out)
        self.assertIn(
            "factions: ['criminal', 'imperial', 'independent', 'rebel']",
            out,
        )


class TestBootOrderingFlagOn(unittest.TestCase):
    """With the flag ON and config registered BEFORE director import,
    director's constants must reflect the era YAML."""

    def test_correct_ordering_picks_up_era_yaml(self):
        # set_active_config BEFORE import. This is what main.py does.
        script = textwrap.dedent("""
            from server.config import Config
            from engine.era_state import set_active_config
            cfg = Config(active_era="clone_wars",
                         use_yaml_director_data=True)
            set_active_config(cfg)
            from engine import director
            print("source:", director._RUNTIME_CFG.source)
            print("factions:", sorted(director.VALID_FACTIONS))
            print("zones_count:", len(director.DEFAULT_INFLUENCE))
        """)
        rc, out, err = _run_python(script)
        self.assertEqual(rc, 0, f"subprocess failed: {err}")
        # Source is the era YAML, not legacy
        self.assertIn("source: yaml-clone_wars", out)
        # CW factions, NOT GCW
        self.assertIn(
            "factions: ['bhg', 'cis', 'hutt_cartel', 'independent', "
            "'jedi_order', 'republic']",
            out,
        )
        # CW has many more zones than the GCW 6
        for line in out.splitlines():
            if line.startswith("zones_count:"):
                count = int(line.split(":")[1].strip())
                self.assertGreater(
                    count, 10,
                    f"CW should have >10 zones, got {count}",
                )

    def test_wrong_ordering_silently_uses_legacy(self):
        # Import director FIRST, then set_active_config. Confirms the
        # silent no-op failure mode that the boot order in main.py
        # is designed to prevent.
        script = textwrap.dedent("""
            from server.config import Config
            # Director gets imported here — constants resolve with no
            # active config registered yet.
            from engine import director
            # Now register the config — too late, director's constants
            # are already frozen at module-level.
            from engine.era_state import set_active_config
            cfg = Config(active_era="clone_wars",
                         use_yaml_director_data=True)
            set_active_config(cfg)
            print("source:", director._RUNTIME_CFG.source)
            print("factions:", sorted(director.VALID_FACTIONS))
        """)
        rc, out, err = _run_python(script)
        self.assertEqual(rc, 0, f"subprocess failed: {err}")
        # Director was imported BEFORE the config was registered, so
        # it captured the default (no-era) state — legacy.
        self.assertIn("source: legacy", out)
        self.assertIn(
            "factions: ['criminal', 'imperial', 'independent', 'rebel']",
            out,
        )


# ══════════════════════════════════════════════════════════════════════════════
# main.py CLI plumbing
# ══════════════════════════════════════════════════════════════════════════════


class TestMainCLIFlags(unittest.TestCase):
    """Verify main.py's argparse exposes the F.6a.6 flags. We can't
    actually start the server in a test, but we can inspect the
    argparse surface via --help."""

    def _run_main_help(self) -> str:
        """Invoke `python main.py --help` and return combined stdout+stderr."""
        proc = subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "main.py"), "--help"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.stdout + proc.stderr

    def test_help_includes_era_flag(self):
        out = self._run_main_help()
        self.assertIn("--era", out,
                      "main.py CLI is missing the --era flag")

    def test_help_includes_use_yaml_director_data_flag(self):
        out = self._run_main_help()
        self.assertIn(
            "--use-yaml-director-data", out,
            "main.py CLI is missing the --use-yaml-director-data flag",
        )

    def test_help_calls_out_dev_only_status(self):
        # Explicit warning so a future contributor doesn't read --era
        # and assume it's production-ready.
        out = self._run_main_help().lower()
        # At least one of the era flags should mention dev-only / preflight
        self.assertTrue(
            "dev only" in out or "dev-only" in out or "preflight" in out,
            f"main.py --help should flag the era options as dev-only. "
            f"Got: {out!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Top-level main.py import safety
# ══════════════════════════════════════════════════════════════════════════════


class TestMainImportSafety(unittest.TestCase):
    """main.py must not import GameServer at module scope, because that
    would force director.py to resolve before main() can call
    set_active_config(). This test reads main.py source and asserts
    GameServer is only imported inside a function."""

    @classmethod
    def setUpClass(cls):
        main_path = os.path.join(PROJECT_ROOT, "main.py")
        with open(main_path, "r", encoding="utf-8") as f:
            cls.main_source = f.read()

    def test_no_module_level_gameserver_import(self):
        # The TYPE_CHECKING block is fine — it never runs.
        # Look for `from server.game_server import GameServer` at
        # column 0 (i.e. not indented inside a function).
        for i, line in enumerate(self.main_source.splitlines(), 1):
            if line.startswith("from server.game_server import GameServer"):
                self.fail(
                    f"main.py:{i}: GameServer is imported at module "
                    f"scope, which forces director.py to resolve "
                    f"before main() can call set_active_config(). "
                    f"Move this import inside main()."
                )

    def test_set_active_config_called_in_main(self):
        # main() must call set_active_config before importing GameServer.
        self.assertIn(
            "set_active_config(config)", self.main_source,
            "main.py is missing the set_active_config(config) call. "
            "Without it, the F.6a.6 flag silently no-ops.",
        )

    def test_set_active_config_precedes_gameserver_import(self):
        # In source order, the set_active_config(config) line must
        # appear BEFORE the deferred `from server.game_server import
        # GameServer` line.
        src = self.main_source
        sac_pos = src.find("set_active_config(config)")
        gs_import_pos = src.find(
            "from server.game_server import GameServer",
            # Skip any TYPE_CHECKING-only occurrences (those are
            # inside `if TYPE_CHECKING:` blocks).
        )
        # Find the first non-TYPE_CHECKING occurrence — the one that
        # actually runs at runtime. We do this by finding the import
        # AFTER the set_active_config call should be.
        self.assertGreater(
            sac_pos, 0, "set_active_config(config) not found in main.py",
        )
        # Find the LAST occurrence of the GameServer import, which
        # should be the runtime one inside main().
        gs_runtime_pos = src.rfind(
            "from server.game_server import GameServer"
        )
        self.assertGreater(
            gs_runtime_pos, 0,
            "GameServer is never imported at runtime in main.py",
        )
        self.assertLess(
            sac_pos, gs_runtime_pos,
            "set_active_config(config) must come BEFORE the runtime "
            "import of GameServer in main.py",
        )


if __name__ == "__main__":
    unittest.main()
