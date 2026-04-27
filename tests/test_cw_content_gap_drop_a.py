"""Drop A — CW content-gap remediation: regression tests.

Per `cw_content_gap_design_v1_1_decisions.md` Drop A and architecture
v36 §35.3, this drop introduces:

  · `data/worlds/clone_wars/npcs_cw_replacements.yaml` — 7 GG7 NPC
    substitutions for the CW era, each carrying a `replaces:` field
    naming the GG7 entry to suppress.
  · `era.yaml` `content_refs.npcs` widened from a single string to a
    list of files (legacy single-string form remains accepted).
  · `engine/world_loader.py` resolver gains a list-or-legacy-string
    helper so the era manifest can be parsed in either form.

These tests pin the contract so a future drop can't silently:
  1. Author a replacement whose `replaces:` value doesn't match any
     real GG7 entry (the suppression would no-op and the room would
     end up with two NPCs of conflicting era).
  2. Use a faction code that isn't reconciled per Q4 (would route
     the NPC to a non-existent organization and fall back to defaults).
  3. Break the era.yaml schema for `content_refs.npcs`.
  4. Regress the world_loader's backward compatibility for the legacy
     single-string form.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import yaml

# When this file is invoked as a standalone script (e.g.
# `python tests/test_cw_content_gap_drop_a.py`), sys.path won't include
# the project root and `from engine.world_loader import ...` will fail.
# pytest handles this via conftest.py, but bare-Python invocations need
# the explicit insert. Mirrors the pattern in tests/test_world_loader.py.
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_STR = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)


PROJECT_ROOT = Path(__file__).parent.parent

GG7_PATH = PROJECT_ROOT / "data" / "npcs_gg7.yaml"
CW_ERA_YAML = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml"
CW_REPLACEMENTS = (
    PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "npcs_cw_replacements.yaml"
)
CW_ADDITIONS = (
    PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "npcs_cw_additions.yaml"
)


# Faction codes must match data/worlds/clone_wars/organizations.yaml or
# the project-wide standard set. Per `cw_content_gap_design_v1_1_decisions.md`
# §Q4, the canonical CW codes are:
ALLOWED_FACTION_CODES_CW = {
    "republic",
    "cis",
    "jedi_order",
    "hutt_cartel",
    "bounty_hunters_guild",
    "shipwrights_guild",
    "independent",
    "neutral",            # Implicit allowed for non-aligned NPCs (Vela Niree)
    # Anti-faction descriptors (used by Het Nkik and similar) are treated
    # as 'independent' at the engine level but appear here for clarity.
}


class TestReplacementsFile(unittest.TestCase):
    """The npcs_cw_replacements.yaml file conforms to the contract."""

    @classmethod
    def setUpClass(cls):
        if not CW_REPLACEMENTS.is_file():
            raise unittest.SkipTest(
                f"missing {CW_REPLACEMENTS} — Drop A not applied"
            )
        with CW_REPLACEMENTS.open(encoding="utf-8") as f:
            cls.data = yaml.safe_load(f)
        with GG7_PATH.open(encoding="utf-8") as f:
            cls.gg7 = yaml.safe_load(f)
        cls.gg7_names = {npc["name"] for npc in cls.gg7["npcs"]}

    def test_schema_version_present(self):
        self.assertEqual(self.data["schema_version"], 1)

    def test_npcs_list_is_seven(self):
        """Drop A replaces exactly 7 GG7 Imperial NPCs per Q3 mapping."""
        self.assertEqual(len(self.data["npcs"]), 7)

    def test_every_replacement_has_replaces_field(self):
        """The `replaces:` field is what the engine uses to suppress
        the original GG7 entry. A replacement without it is just a
        normal addition — and we'd end up with two NPCs in the room."""
        for npc in self.data["npcs"]:
            self.assertIn("replaces", npc, msg=f"NPC {npc.get('name')!r} missing replaces field")
            self.assertIsInstance(npc["replaces"], str)
            self.assertTrue(npc["replaces"].strip())

    def test_every_replaces_target_exists_in_gg7(self):
        """If `replaces:` points to a name that doesn't exist in the
        GG7 source, the suppression is a no-op and the room ends up
        with the GG7 original AND the CW replacement — both visible
        at once. That breaks the in-place-replacement guarantee."""
        for npc in self.data["npcs"]:
            target = npc["replaces"]
            self.assertIn(
                target, self.gg7_names,
                msg=(
                    f"Replacement {npc['name']!r} targets {target!r}, "
                    f"which does not exist in data/npcs_gg7.yaml. "
                    f"The replacement will load but the suppression "
                    f"will be a no-op — the GG7 NPC will spawn alongside."
                ),
            )

    def test_no_two_replacements_target_the_same_gg7(self):
        """Two replacements pointing at the same GG7 target would
        leave the engine ambiguous about which one wins. Guard."""
        targets = [npc["replaces"] for npc in self.data["npcs"]]
        self.assertEqual(
            len(targets), len(set(targets)),
            msg=f"Duplicate `replaces:` targets: {targets}",
        )

    def test_every_replacement_has_full_schema(self):
        """Mirror of npcs_gg7.yaml schema. Missing required fields
        would crash the npc_loader at runtime."""
        required_top = ["name", "room", "species", "description", "char_sheet", "ai_config"]
        required_char_sheet = ["attributes", "skills", "weapon", "move",
                               "force_points", "character_points", "dark_side_points"]
        required_attrs = ["dexterity", "knowledge", "mechanical",
                          "perception", "strength", "technical"]
        required_ai = ["personality", "knowledge", "faction", "dialogue_style",
                       "hostile", "combat_behavior", "fallback_lines"]
        for npc in self.data["npcs"]:
            for fld in required_top:
                self.assertIn(fld, npc, msg=f"{npc.get('name')!r}: missing {fld}")
            for fld in required_char_sheet:
                self.assertIn(fld, npc["char_sheet"],
                              msg=f"{npc['name']!r}: char_sheet missing {fld}")
            for fld in required_attrs:
                self.assertIn(fld, npc["char_sheet"]["attributes"],
                              msg=f"{npc['name']!r}: attributes missing {fld}")
            for fld in required_ai:
                self.assertIn(fld, npc["ai_config"],
                              msg=f"{npc['name']!r}: ai_config missing {fld}")

    def test_no_imperial_faction_codes(self):
        """Per Q3, the entire point of Drop A is to remove `Imperial`
        from CW NPCs. If a future edit reintroduces it, fail loudly."""
        for npc in self.data["npcs"]:
            faction = (npc["ai_config"].get("faction") or "").lower()
            self.assertNotIn(
                "imperial", faction,
                msg=f"{npc['name']!r} has Imperial faction code {faction!r} — "
                    f"Empire does not exist in 20 BBY CW era",
            )

    def test_faction_codes_are_reconciled(self):
        """Per `cw_content_gap_design_v1_1_decisions.md` §Q4, all
        faction codes used in CW content must map to organizations.yaml
        codes. This catches design-doc-code regressions early."""
        for npc in self.data["npcs"]:
            faction = (npc["ai_config"].get("faction") or "").lower()
            self.assertIn(
                faction, ALLOWED_FACTION_CODES_CW,
                msg=f"{npc['name']!r} faction {faction!r} not in the "
                    f"allowed CW faction set. Update ALLOWED_FACTION_CODES_CW "
                    f"if the addition is intentional.",
            )

    def test_room_targets_are_string_names_not_ids(self):
        """The schema is the same as npcs_gg7.yaml — `room` is a
        display-name string, NOT an integer DB id. The npc_loader
        resolves names to ids at load time."""
        for npc in self.data["npcs"]:
            self.assertIsInstance(npc["room"], str)
            self.assertTrue(npc["room"].strip())


class TestEraYamlNpcsField(unittest.TestCase):
    """era.yaml's content_refs.npcs is a list (post-Drop A)."""

    @classmethod
    def setUpClass(cls):
        if not CW_ERA_YAML.is_file():
            raise unittest.SkipTest(f"missing {CW_ERA_YAML}")
        with CW_ERA_YAML.open(encoding="utf-8") as f:
            cls.era = yaml.safe_load(f)

    def test_npcs_field_is_a_list(self):
        npcs_ref = self.era["content_refs"]["npcs"]
        self.assertIsInstance(
            npcs_ref, list,
            msg="era.yaml content_refs.npcs should be a list post-Drop A; "
                "got %r" % (npcs_ref,),
        )

    def test_list_includes_additions_and_replacements(self):
        npcs_ref = self.era["content_refs"]["npcs"]
        self.assertIn("npcs_cw_additions.yaml", npcs_ref)
        self.assertIn("npcs_cw_replacements.yaml", npcs_ref)

    def test_referenced_files_exist(self):
        """Each filename in the list resolves to an existing file
        relative to the era directory. The dangling `npcs.yaml`
        reference (the very thing Drop A reconciles) is prevented
        from recurring."""
        era_dir = CW_ERA_YAML.parent
        for fname in self.era["content_refs"]["npcs"]:
            target = era_dir / fname
            self.assertTrue(
                target.is_file(),
                msg=f"era.yaml references {fname!r} but {target} doesn't exist",
            )


class TestWorldLoaderListSupport(unittest.TestCase):
    """engine/world_loader.py accepts both list and legacy-string forms."""

    def test_loader_imports(self):
        """Smoke: the module loads without error after the schema change."""
        from engine.world_loader import EraManifest  # noqa: F401
        from engine.world_loader import load_era_manifest  # noqa: F401

    def test_era_manifest_has_npcs_paths_field(self):
        """The dataclass exposes `npcs_paths` (always a list) per Drop A."""
        from dataclasses import fields
        from engine.world_loader import EraManifest
        field_names = {f.name for f in fields(EraManifest)}
        self.assertIn(
            "npcs_paths", field_names,
            msg="EraManifest should expose npcs_paths as a list field",
        )
        self.assertNotIn(
            "npcs_path", field_names,
            msg="EraManifest should not expose the singular npcs_path "
                "field anymore — it was renamed in Drop A",
        )

    def test_clone_wars_era_loads_with_list_form(self):
        """Real CW era.yaml (now using list form) loads cleanly."""
        from engine.world_loader import load_era_manifest
        era_dir = PROJECT_ROOT / "data" / "worlds" / "clone_wars"
        if not era_dir.is_dir():
            self.skipTest("data/worlds/clone_wars/ not present")
        manifest = load_era_manifest(era_dir)
        self.assertEqual(manifest.era_code, "clone_wars")
        # Drop A wires both files; expect at least 2 paths.
        self.assertGreaterEqual(
            len(manifest.npcs_paths), 2,
            msg="CW era should reference at least additions + replacements",
        )
        # Every resolved Path is absolute and points inside the era dir.
        for p in manifest.npcs_paths:
            self.assertTrue(p.is_absolute() or str(p).startswith(str(era_dir)))

    def test_legacy_single_string_form_still_accepted(self):
        """Backward compatibility: a hypothetical era still using the
        old `npcs: <single-file>.yaml` form must continue to load."""
        from engine.world_loader import load_era_manifest
        # Build a minimal era directory in a temp location.
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            era_dir = Path(tmp) / "test_era"
            era_dir.mkdir()
            # Minimal zones.yaml (required field)
            (era_dir / "zones.yaml").write_text(
                "test_zone:\n  name_match: Test\n", encoding="utf-8")
            # Legacy single-string npcs reference, file doesn't need
            # to exist — load_era_manifest just resolves the path.
            (era_dir / "era.yaml").write_text(
                "schema_version: 1\n"
                "era:\n"
                "  code: test_era\n"
                "  name: Test Era\n"
                "content_refs:\n"
                "  zones: zones.yaml\n"
                "  planets: []\n"
                "  wilderness: []\n"
                "  npcs: legacy_single_string.yaml\n",
                encoding="utf-8",
            )
            manifest = load_era_manifest(era_dir)
        self.assertEqual(len(manifest.npcs_paths), 1)
        self.assertTrue(str(manifest.npcs_paths[0]).endswith("legacy_single_string.yaml"))

    def test_omitted_npcs_field_returns_empty_list(self):
        """An era with no `npcs` ref at all (theoretically valid)
        should yield an empty list, not None or KeyError."""
        from engine.world_loader import load_era_manifest
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            era_dir = Path(tmp) / "test_era"
            era_dir.mkdir()
            (era_dir / "zones.yaml").write_text(
                "test_zone:\n  name_match: Test\n", encoding="utf-8")
            (era_dir / "era.yaml").write_text(
                "schema_version: 1\n"
                "era:\n  code: test_era\n  name: Test Era\n"
                "content_refs:\n"
                "  zones: zones.yaml\n"
                "  planets: []\n"
                "  wilderness: []\n",
                encoding="utf-8",
            )
            manifest = load_era_manifest(era_dir)
        self.assertEqual(manifest.npcs_paths, [])

    def test_invalid_npcs_field_type_raises(self):
        """Defensive: a non-string-non-list value (e.g. a dict) raises
        a clear error rather than silently producing garbage."""
        from engine.world_loader import load_era_manifest, WorldLoadError
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            era_dir = Path(tmp) / "test_era"
            era_dir.mkdir()
            (era_dir / "zones.yaml").write_text(
                "test_zone:\n  name_match: Test\n", encoding="utf-8")
            (era_dir / "era.yaml").write_text(
                "schema_version: 1\n"
                "era:\n  code: test_era\n  name: Test Era\n"
                "content_refs:\n"
                "  zones: zones.yaml\n"
                "  planets: []\n"
                "  wilderness: []\n"
                "  npcs:\n    bad: dict\n",
                encoding="utf-8",
            )
            with self.assertRaises(WorldLoadError):
                load_era_manifest(era_dir)


if __name__ == "__main__":
    unittest.main()
