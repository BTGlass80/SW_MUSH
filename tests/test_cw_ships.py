# -*- coding: utf-8 -*-
"""
tests/test_cw_ships.py — CW.SHIPS drop verification.

CW.SHIPS (May 2026) closes the gap surfaced by smoke harness scenarios:
the Clone Wars era had a 14-class starship template catalog at
``data/worlds/clone_wars/starships.yaml`` but neither (a) registered
those templates with ``get_ship_registry()`` nor (b) spawned any
docked ships at world-build time. CW players literally could not
board a ship. Per architecture v39 §3.2 priority #1 CW.SHIPS, this
drop:

  1. Made ``engine.starships.get_ship_registry()`` era-aware: loads
     the base ``data/starships.yaml`` (legacy/GCW) plus the active
     era's ``data/worlds/<era>/starships.yaml`` if present.
  2. Authored ``data/worlds/clone_wars/ships.yaml`` — 7 docked ships
     across the four player-facing CW planets (Tatooine, Nar Shaddaa,
     Kuat, Coruscant), mirroring the GCW roster size.
  3. Added ``ships: ships.yaml`` to CW ``era.yaml`` ``content_refs``.

Test sections:
  1. TestEraAwareRegistry          — overlay loading + reset behavior
  2. TestCWTemplatesResolveable    — every CW class is registered
  3. TestCWDockedRosterShape       — ships.yaml is well-formed
  4. TestCWDockedRosterTemplates   — every docked ship's template_key
                                     resolves through the registry
  5. TestCWDockedRosterBays        — every bay_room exists in the CW
                                     world data
  6. TestEraManifestRef            — era.yaml content_refs.ships is
                                     correctly wired
  7. TestGCWUnchanged              — GCW load path is unaffected
  8. TestDocstringMarker           — source-level guard
"""
from __future__ import annotations

import os
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CW_DIR = os.path.join(DATA_DIR, "worlds", "clone_wars")
GCW_DIR = os.path.join(DATA_DIR, "worlds", "gcw")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _MockCfg:
    """Minimal Config-shaped object for engine.era_state.set_active_config."""
    def __init__(self, era):
        self.active_era = era
        self.use_yaml_director_data = False


def _flip_era(era):
    """Set active era and reset the ship registry so the next get_*() rebuilds."""
    from engine.era_state import set_active_config
    from engine.starships import reset_ship_registry
    set_active_config(_MockCfg(era))
    reset_ship_registry()


def _clear_era():
    from engine.era_state import set_active_config
    from engine.starships import reset_ship_registry
    set_active_config(None)
    reset_ship_registry()


def _load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_room_names_for_era(era_dir):
    """Walk every planet YAML in an era and return the set of room names."""
    names = set()
    era_yaml = _load_yaml(os.path.join(era_dir, "era.yaml"))
    refs = era_yaml.get("content_refs", {}) or {}
    planet_files = refs.get("planets", []) or []
    extra_room_files = []
    # tutorials/rooms.yaml ref, if present, is a string (single file)
    if "planets" in refs:
        for entry in planet_files:
            if isinstance(entry, str):
                if entry.startswith("tutorials/"):
                    extra_room_files.append(entry)
                else:
                    p = os.path.join(era_dir, entry)
                    if os.path.exists(p):
                        d = _load_yaml(p) or {}
                        for r in (d.get("rooms") or []):
                            if isinstance(r, dict) and r.get("name"):
                                names.add(r["name"])
    for entry in extra_room_files:
        p = os.path.join(era_dir, entry)
        if os.path.exists(p):
            d = _load_yaml(p) or {}
            for r in (d.get("rooms") or []):
                if isinstance(r, dict) and r.get("name"):
                    names.add(r["name"])
    return names


# ─────────────────────────────────────────────────────────────────────────────
# 1. Era-aware registry behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestEraAwareRegistry(unittest.TestCase):
    """get_ship_registry() loads base + era overlay; reset_ship_registry() clears it."""

    def tearDown(self):
        _clear_era()

    def test_default_era_loads_base_only(self):
        """With no era set, registry equals the base catalog."""
        _clear_era()
        from engine.starships import get_ship_registry
        reg = get_ship_registry()
        # Base catalog has the GCW-era staples
        self.assertIsNotNone(reg.get("yt_1300"),
                             "yt_1300 should be in base catalog")
        # CW templates should NOT be present in pure-base load
        # (because default era is "gcw", which has no overlay file)
        self.assertIsNone(reg.get("venator"),
                          "venator should not load when era is gcw")

    def test_clone_wars_era_loads_overlay(self):
        """Setting active era to clone_wars exposes the CW template overlay."""
        _flip_era("clone_wars")
        from engine.starships import get_ship_registry
        reg = get_ship_registry()
        # Base catalog still present
        self.assertIsNotNone(reg.get("yt_1300"),
                             "yt_1300 (base) should still resolve under CW era")
        # CW overlay templates now present
        for key in ("venator", "arc_170", "eta_2_actis", "consular_cruiser"):
            self.assertIsNotNone(
                reg.get(key),
                f"CW template {key!r} should be loaded when era=clone_wars")

    def test_reset_ship_registry_drops_cache(self):
        """reset_ship_registry() forces the next call to rebuild."""
        _flip_era("clone_wars")
        from engine.starships import get_ship_registry, reset_ship_registry
        reg1 = get_ship_registry()
        reset_ship_registry()
        reg2 = get_ship_registry()
        self.assertIsNot(reg1, reg2,
                         "reset_ship_registry should invalidate the singleton")

    def test_gcw_after_cw_returns_to_base_only(self):
        """Flipping back to GCW removes CW templates from the registry."""
        _flip_era("clone_wars")
        from engine.starships import get_ship_registry
        cw_reg = get_ship_registry()
        self.assertIsNotNone(cw_reg.get("venator"))
        _flip_era("gcw")
        gcw_reg = get_ship_registry()
        self.assertIsNone(gcw_reg.get("venator"),
                          "venator should not be reachable after era flip to gcw")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Every CW template registers cleanly
# ─────────────────────────────────────────────────────────────────────────────

class TestCWTemplatesResolveable(unittest.TestCase):
    """Each entry in clone_wars/starships.yaml is loadable as a ShipTemplate."""

    @classmethod
    def setUpClass(cls):
        _flip_era("clone_wars")

    @classmethod
    def tearDownClass(cls):
        _clear_era()

    def test_all_cw_template_keys_resolve(self):
        """Every key in CW starships.yaml resolves via get_ship_registry()."""
        from engine.starships import get_ship_registry
        cw_yaml = _load_yaml(os.path.join(CW_DIR, "starships.yaml"))
        reg = get_ship_registry()
        # Filter out non-ship metadata entries (e.g. registry_hints)
        ship_keys = [
            k for k, v in cw_yaml.items()
            if isinstance(v, dict) and v.get("scale") in ("starfighter", "capital")
        ]
        self.assertGreater(len(ship_keys), 10,
                           "Expected at least 10 CW ship classes")
        missing = [k for k in ship_keys if reg.get(k) is None]
        self.assertEqual(missing, [],
                         f"CW template keys failed to register: {missing}")

    def test_cw_template_field_shape(self):
        """Sample CW templates have the fields ShipTemplate cares about."""
        from engine.starships import get_ship_registry
        reg = get_ship_registry()
        for key in ("venator", "arc_170", "eta_2_actis", "consular_cruiser"):
            tmpl = reg.get(key)
            self.assertIsNotNone(tmpl, f"{key} should resolve")
            self.assertTrue(tmpl.name, f"{key}.name should be non-empty")
            self.assertIn(tmpl.scale, ("starfighter", "capital"),
                          f"{key}.scale should be a known WEG scale")
            self.assertGreater(tmpl.crew, 0,
                               f"{key}.crew should be positive")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CW docked roster — schema shape
# ─────────────────────────────────────────────────────────────────────────────

class TestCWDockedRosterShape(unittest.TestCase):
    """clone_wars/ships.yaml is well-formed."""

    def test_ships_yaml_exists(self):
        path = os.path.join(CW_DIR, "ships.yaml")
        self.assertTrue(os.path.exists(path),
                        f"CW docked roster missing at {path}")

    def test_schema_version(self):
        d = _load_yaml(os.path.join(CW_DIR, "ships.yaml"))
        self.assertEqual(d.get("schema_version"), 1,
                         "ships.yaml schema_version should be 1")

    def test_ships_list_nonempty(self):
        d = _load_yaml(os.path.join(CW_DIR, "ships.yaml"))
        ships = d.get("ships") or []
        self.assertGreater(len(ships), 0, "CW should have at least one docked ship")
        # Mirror GCW size (7) — design choice, not load-bearing forever
        self.assertGreaterEqual(len(ships), 5,
                                "Roster should have at least 5 ships")

    def test_every_ship_has_required_fields(self):
        d = _load_yaml(os.path.join(CW_DIR, "ships.yaml"))
        for i, s in enumerate(d.get("ships") or []):
            for field in ("template_key", "name", "bay_room", "bridge_desc"):
                self.assertIn(field, s,
                              f"Ship #{i} missing required field {field!r}: {s}")
                self.assertTrue(s[field],
                                f"Ship #{i} field {field!r} is empty")

    def test_no_duplicate_ship_names(self):
        d = _load_yaml(os.path.join(CW_DIR, "ships.yaml"))
        names = [s["name"] for s in d.get("ships") or []]
        self.assertEqual(len(names), len(set(names)),
                         f"Duplicate ship names: {sorted(names)}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Every docked template_key resolves through the registry
# ─────────────────────────────────────────────────────────────────────────────

class TestCWDockedRosterTemplates(unittest.TestCase):
    """Each docked ship's template_key is resolvable in the CW-era registry."""

    @classmethod
    def setUpClass(cls):
        _flip_era("clone_wars")

    @classmethod
    def tearDownClass(cls):
        _clear_era()

    def test_all_template_keys_resolve(self):
        from engine.starships import get_ship_registry
        d = _load_yaml(os.path.join(CW_DIR, "ships.yaml"))
        reg = get_ship_registry()
        unresolved = []
        for s in d.get("ships") or []:
            if reg.get(s["template_key"]) is None:
                unresolved.append((s["name"], s["template_key"]))
        self.assertEqual(unresolved, [],
                         f"Docked ships referencing unknown templates: {unresolved}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Every bay_room exists in CW world data
# ─────────────────────────────────────────────────────────────────────────────

class TestCWDockedRosterBays(unittest.TestCase):
    """Each docked ship's bay_room resolves to a real CW room."""

    def test_all_bay_rooms_exist_in_cw_world(self):
        d = _load_yaml(os.path.join(CW_DIR, "ships.yaml"))
        cw_room_names = _all_room_names_for_era(CW_DIR)
        unresolved = []
        for s in d.get("ships") or []:
            if s["bay_room"] not in cw_room_names:
                unresolved.append((s["name"], s["bay_room"]))
        self.assertEqual(
            unresolved, [],
            f"Docked ships reference rooms missing from CW world data: "
            f"{unresolved}\n(Available CW rooms with 'bay'/'hangar'/'docking' "
            f"in name: {sorted(n for n in cw_room_names if any(t in n.lower() for t in ('bay','hangar','docking','landing')))})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. era.yaml correctly references ships.yaml
# ─────────────────────────────────────────────────────────────────────────────

class TestEraManifestRef(unittest.TestCase):
    """CW era.yaml content_refs.ships points at ships.yaml."""

    def test_cw_era_has_ships_ref(self):
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        refs = era.get("content_refs", {})
        self.assertEqual(
            refs.get("ships"), "ships.yaml",
            "CW era.yaml content_refs.ships should be 'ships.yaml' "
            "(the docked roster), distinct from 'starships' (the templates)"
        )

    def test_cw_era_still_has_starships_ref(self):
        """The pre-existing starships ref (templates) is untouched."""
        era = _load_yaml(os.path.join(CW_DIR, "era.yaml"))
        refs = era.get("content_refs", {})
        self.assertEqual(refs.get("starships"), "starships.yaml")

    def test_ship_loader_picks_up_cw_roster(self):
        """engine.ship_loader.load_era_ships returns the CW roster."""
        from engine.ship_loader import load_era_ships
        cw_room_names = _all_room_names_for_era(CW_DIR)
        # Build a minimal name→idx map (loader uses it for bay_room resolution)
        name_map = {n: i for i, n in enumerate(sorted(cw_room_names))}
        ships = load_era_ships(CW_DIR, name_map)
        self.assertGreater(
            len(ships), 0,
            "load_era_ships should return non-empty list for CW now that "
            "ships.yaml exists and is referenced from era.yaml"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. GCW behavior is unchanged
# ─────────────────────────────────────────────────────────────────────────────

class TestGCWUnchanged(unittest.TestCase):
    """The era-aware registry change must not break the GCW load path."""

    def tearDown(self):
        _clear_era()

    def test_gcw_registry_size_equals_base_catalog(self):
        """Under GCW (no overlay file), registry size = base catalog size."""
        _flip_era("gcw")
        from engine.starships import get_ship_registry
        reg = get_ship_registry()
        base_yaml = _load_yaml(os.path.join(DATA_DIR, "starships.yaml"))
        # Top-level dict keys minus the registry_hints metadata key
        base_count = sum(
            1 for k, v in base_yaml.items()
            if isinstance(v, dict) and v.get("scale") in ("starfighter", "capital")
        )
        # Allow loose match — base may include other valid keys too
        self.assertGreaterEqual(reg.count, base_count,
                                "GCW registry should have at least the base count")

    def test_gcw_ship_loader_still_works(self):
        """GCW docked roster still loads correctly (regression guard)."""
        _flip_era("gcw")
        from engine.ship_loader import load_era_ships
        gcw_room_names = _all_room_names_for_era(GCW_DIR)
        name_map = {n: i for i, n in enumerate(sorted(gcw_room_names))}
        ships = load_era_ships(GCW_DIR, name_map)
        self.assertGreater(len(ships), 0,
                           "GCW ship_loader regression: returned empty roster")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Source-level marker (catches accidental revert in starships.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestDocstringMarker(unittest.TestCase):
    """get_ship_registry source contains era-aware overlay logic."""

    def test_starships_module_references_era_state(self):
        path = os.path.join(PROJECT_ROOT, "engine", "starships.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("get_active_era", src,
                      "engine/starships.py should call get_active_era() "
                      "(CW.SHIPS era-aware overlay)")
        self.assertIn("reset_ship_registry", src,
                      "engine/starships.py should expose reset_ship_registry()")


if __name__ == "__main__":
    unittest.main()
