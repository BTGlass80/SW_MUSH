# -*- coding: utf-8 -*-
"""
tests/test_f7_chargen_templates_loader.py — F.7 integration tests.

F.7 (Apr 30 2026) extracts the in-Python TEMPLATES literal at
engine/creation.py to per-era YAML and resolves at module-import
time via a seam in engine/chargen_templates_loader.py.

Phase 1 (this drop): seam ships with the legacy literal
(`_LEGACY_TEMPLATES_GCW` in the seam module) as a rollback safety
net. Tests below prove byte-equivalence between the GCW YAML and
the legacy constant — the byte-equivalence assertion is the gate
that lets F.7.b Phase 2 retire the constant later.

Test sections:
  1. TestGCWByteEquivalence       — YAML matches _LEGACY_TEMPLATES_GCW
  2. TestCWCorpusLoads            — CW YAML loads with expected keys
  3. TestSeamReturnShape          — seam dict shape matches legacy
  4. TestSeamFallbackPaths        — seam falls back gracefully
  5. TestWorldLoaderCorpus        — loader produces correct corpus
  6. TestEraManifestPath          — chargen_templates_path resolves
  7. TestF7DocstringMarkers       — source-level guards
  8. TestCreationModuleIntegration — engine.creation.TEMPLATES is
                                     a proper post-F.7 binding

Tests use temp directories for the YAML-failure paths so they
don't depend on the real worlds tree being broken.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. GCW byte-equivalence — the F.7.b gate
# ──────────────────────────────────────────────────────────────────────

class TestGCWByteEquivalence(unittest.TestCase):
    """The GCW chargen_templates.yaml MUST match the in-Python
    _LEGACY_TEMPLATES_GCW literal byte-for-byte. F.7.b Phase 2 will
    retire the legacy constant once this byte-equivalence has been
    proven in production for some period; the assertion below is
    that gate."""

    def test_gcw_yaml_matches_legacy_literal(self):
        from engine.chargen_templates_loader import (
            get_chargen_templates, _LEGACY_TEMPLATES_GCW,
        )
        gcw = get_chargen_templates(era="gcw")
        self.assertEqual(
            gcw, _LEGACY_TEMPLATES_GCW,
            "GCW chargen_templates.yaml must match _LEGACY_TEMPLATES_GCW "
            "byte-for-byte. If you intentionally changed one, update "
            "the other in lockstep until F.7.b Phase 2 retires the "
            "legacy constant.",
        )

    def test_gcw_has_seven_templates(self):
        from engine.chargen_templates_loader import get_chargen_templates
        gcw = get_chargen_templates(era="gcw")
        self.assertEqual(len(gcw), 7)

    def test_gcw_template_keys(self):
        from engine.chargen_templates_loader import get_chargen_templates
        gcw = get_chargen_templates(era="gcw")
        expected = {
            "smuggler", "bounty_hunter", "rebel_pilot", "scoundrel",
            "technician", "jedi_apprentice", "soldier",
        }
        self.assertEqual(set(gcw.keys()), expected)

    def test_gcw_template_order_preserved(self):
        """The chargen wizard relies on preserved YAML order for the
        numbered template-selection menu. The first option in GCW is
        Smuggler; the last is Soldier."""
        from engine.chargen_templates_loader import get_chargen_templates
        gcw = get_chargen_templates(era="gcw")
        keys = list(gcw.keys())
        self.assertEqual(keys[0], "smuggler")
        self.assertEqual(keys[-1], "soldier")


# ──────────────────────────────────────────────────────────────────────
# 2. CW corpus loads correctly
# ──────────────────────────────────────────────────────────────────────

class TestCWCorpusLoads(unittest.TestCase):
    """The CW chargen_templates.yaml loads cleanly with the expected
    archetype set."""

    def test_cw_has_nine_templates(self):
        from engine.chargen_templates_loader import get_chargen_templates
        cw = get_chargen_templates(era="clone_wars")
        self.assertEqual(len(cw), 9)

    def test_cw_template_keys(self):
        from engine.chargen_templates_loader import get_chargen_templates
        cw = get_chargen_templates(era="clone_wars")
        expected = {
            # Era-neutral carry-overs
            "smuggler", "bounty_hunter", "scoundrel", "technician",
            # CW-specific
            "clone_trooper", "republic_officer", "republic_pilot",
            "separatist_pilot", "cis_field_agent",
        }
        self.assertEqual(set(cw.keys()), expected)

    def test_cw_jedi_apprentice_intentionally_absent(self):
        """CW Jedi PCs are village-gated per era.yaml policy. The
        chargen YAML is the 'what can you pick at chargen' allowlist;
        jedi_apprentice belongs to the village quest unlock path,
        not the chargen template menu."""
        from engine.chargen_templates_loader import get_chargen_templates
        cw = get_chargen_templates(era="clone_wars")
        self.assertNotIn(
            "jedi_apprentice", cw,
            "CW chargen YAML must NOT include jedi_apprentice — "
            "Jedi PCs in CW are village_gated per era policy",
        )

    def test_cw_clone_trooper_is_human(self):
        """Clones are exclusively human in canon. Locked species check."""
        from engine.chargen_templates_loader import get_chargen_templates
        cw = get_chargen_templates(era="clone_wars")
        self.assertEqual(cw["clone_trooper"]["species"], "Human")

    def test_cw_pilots_are_dice_symmetric(self):
        """republic_pilot and separatist_pilot share the same
        mechanical fingerprint per the YAML rationale comment —
        the pilot archetype is era-axis-symmetric."""
        from engine.chargen_templates_loader import get_chargen_templates
        cw = get_chargen_templates(era="clone_wars")
        self.assertEqual(
            cw["republic_pilot"]["attributes"],
            cw["separatist_pilot"]["attributes"],
        )
        self.assertEqual(
            cw["republic_pilot"]["skills"],
            cw["separatist_pilot"]["skills"],
        )

    def test_cw_era_neutral_carryovers_match_gcw(self):
        """smuggler / bounty_hunter / scoundrel / technician are
        byte-equivalent across eras per the YAML rationale comment."""
        from engine.chargen_templates_loader import get_chargen_templates
        gcw = get_chargen_templates(era="gcw")
        cw = get_chargen_templates(era="clone_wars")
        for key in ("smuggler", "bounty_hunter", "scoundrel", "technician"):
            self.assertEqual(
                gcw[key], cw[key],
                f"Era-neutral template {key!r} should be byte-identical "
                f"across GCW and CW",
            )


# ──────────────────────────────────────────────────────────────────────
# 3. Seam return shape
# ──────────────────────────────────────────────────────────────────────

class TestSeamReturnShape(unittest.TestCase):
    """The seam returns a dict shaped exactly like the legacy
    in-Python TEMPLATES literal so existing consumers
    (engine/creation.py, parser/chargen) work without changes."""

    def test_each_template_has_required_fields(self):
        from engine.chargen_templates_loader import get_chargen_templates
        gcw = get_chargen_templates(era="gcw")
        for key, tmpl in gcw.items():
            self.assertIn("label", tmpl, f"{key} missing label")
            self.assertIn("species", tmpl, f"{key} missing species")
            self.assertIn("attributes", tmpl, f"{key} missing attributes")
            self.assertIn("skills", tmpl, f"{key} missing skills")
            self.assertIsInstance(tmpl["label"], str)
            self.assertIsInstance(tmpl["species"], str)
            self.assertIsInstance(tmpl["attributes"], dict)
            self.assertIsInstance(tmpl["skills"], dict)

    def test_attributes_are_dice_pool_strings(self):
        from engine.chargen_templates_loader import get_chargen_templates
        gcw = get_chargen_templates(era="gcw")
        for key, tmpl in gcw.items():
            for attr_name, attr_value in tmpl["attributes"].items():
                self.assertIsInstance(
                    attr_value, str,
                    f"{key}.attributes.{attr_name} must be a string "
                    f"(dice-pool format), got {type(attr_value).__name__}",
                )

    def test_returned_dict_is_independent_copy(self):
        """Seam returns a fresh dict per call; mutating the result
        must not poison subsequent callers."""
        from engine.chargen_templates_loader import get_chargen_templates
        gcw1 = get_chargen_templates(era="gcw")
        gcw1["smuggler"]["label"] = "MUTATED"
        gcw2 = get_chargen_templates(era="gcw")
        self.assertEqual(gcw2["smuggler"]["label"], "Smuggler",
                         "Mutating one call's result poisoned a later call")


# ──────────────────────────────────────────────────────────────────────
# 4. Seam fallback paths
# ──────────────────────────────────────────────────────────────────────

class TestSeamFallbackPaths(unittest.TestCase):
    """The seam falls back to _LEGACY_TEMPLATES_GCW when the YAML
    path doesn't resolve. Phase 1 expects this for any era without a
    chargen_templates.yaml authored yet (or any era with a manifest
    parse error)."""

    def test_unknown_era_falls_back_to_legacy(self):
        from engine.chargen_templates_loader import (
            get_chargen_templates, _LEGACY_TEMPLATES_GCW,
        )
        # Era 'fake_era_for_test' doesn't exist on disk; the seam
        # should fall back to legacy without raising.
        result = get_chargen_templates(era="fake_era_for_test")
        self.assertEqual(result, _LEGACY_TEMPLATES_GCW)

    def test_worlds_root_override_with_no_chargen_ref(self):
        """If the worlds_root override points at a tmp dir with an
        era.yaml but no chargen_templates ref, fallback fires."""
        from engine.chargen_templates_loader import (
            get_chargen_templates, _LEGACY_TEMPLATES_GCW,
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            era_dir = tmp_root / "tmpera"
            era_dir.mkdir()
            # Minimal era.yaml with a zones ref but no chargen_templates
            era_yaml = era_dir / "era.yaml"
            zones_yaml = era_dir / "zones.yaml"
            zones_yaml.write_text("zones: {}\n", encoding="utf-8")
            era_yaml.write_text(
                "schema_version: 1\n"
                "era:\n"
                "  code: tmpera\n"
                "  name: TmpEra\n"
                "content_refs:\n"
                "  zones: zones.yaml\n",
                encoding="utf-8",
            )
            result = get_chargen_templates(
                era="tmpera",
                worlds_root=tmp_root,
            )
            self.assertEqual(result, _LEGACY_TEMPLATES_GCW)

    def test_legacy_dict_is_deep_copied(self):
        """Calling _legacy_templates_dict() twice returns independent
        dicts so callers can't accidentally pollute the constant."""
        from engine.chargen_templates_loader import _legacy_templates_dict
        d1 = _legacy_templates_dict()
        d1["smuggler"]["label"] = "POISONED"
        d2 = _legacy_templates_dict()
        self.assertEqual(d2["smuggler"]["label"], "Smuggler")


# ──────────────────────────────────────────────────────────────────────
# 5. world_loader.load_chargen_templates corpus shape
# ──────────────────────────────────────────────────────────────────────

class TestWorldLoaderCorpus(unittest.TestCase):
    """The world_loader.load_chargen_templates function produces a
    ChargenTemplatesCorpus dataclass with parsed templates."""

    def test_gcw_corpus_loads(self):
        from engine.world_loader import (
            load_era_manifest, load_chargen_templates,
        )
        manifest = load_era_manifest(Path("data") / "worlds" / "gcw")
        corpus = load_chargen_templates(manifest)
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.schema_version, 1)
        self.assertEqual(len(corpus.templates), 7)
        self.assertFalse(corpus.report.errors,
                         f"GCW corpus had errors: {corpus.report.errors}")

    def test_cw_corpus_loads(self):
        from engine.world_loader import (
            load_era_manifest, load_chargen_templates,
        )
        manifest = load_era_manifest(Path("data") / "worlds" / "clone_wars")
        corpus = load_chargen_templates(manifest)
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.schema_version, 1)
        self.assertEqual(len(corpus.templates), 9)
        self.assertFalse(corpus.report.errors,
                         f"CW corpus had errors: {corpus.report.errors}")

    def test_corpus_template_dataclass_shape(self):
        from engine.world_loader import (
            load_era_manifest, load_chargen_templates, ChargenTemplate,
        )
        manifest = load_era_manifest(Path("data") / "worlds" / "gcw")
        corpus = load_chargen_templates(manifest)
        for tmpl in corpus.templates:
            self.assertIsInstance(tmpl, ChargenTemplate)
            self.assertTrue(tmpl.key)
            self.assertTrue(tmpl.label)
            self.assertTrue(tmpl.species)
            self.assertTrue(tmpl.attributes)
            self.assertTrue(tmpl.skills)

    def test_loader_returns_none_when_no_manifest_ref(self):
        """If the manifest's chargen_templates_path is None,
        load_chargen_templates returns None (caller falls back)."""
        from engine.world_loader import (
            load_chargen_templates, EraManifest,
        )
        # Build a synthetic manifest with chargen_templates_path = None
        manifest = EraManifest(
            era_code="testera",
            era_name="TestEra",
            schema_version=1,
            era_dir=Path("/tmp"),
            zones_path=Path("/tmp/zones.yaml"),
            organizations_path=None,
            planet_paths=[],
            wilderness_paths=[],
            npcs_paths=[],
            housing_lots_path=None,
            test_character_path=None,
            test_jedi_path=None,
            chargen_templates_path=None,
        )
        result = load_chargen_templates(manifest)
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────
# 6. EraManifest path resolution
# ──────────────────────────────────────────────────────────────────────

class TestEraManifestPath(unittest.TestCase):
    """The chargen_templates_path field is wired through
    load_era_manifest from era.yaml's content_refs.chargen_templates."""

    def test_gcw_manifest_has_chargen_path(self):
        from engine.world_loader import load_era_manifest
        manifest = load_era_manifest(Path("data") / "worlds" / "gcw")
        self.assertIsNotNone(manifest.chargen_templates_path)
        self.assertTrue(manifest.chargen_templates_path.is_file())
        self.assertEqual(
            manifest.chargen_templates_path.name,
            "chargen_templates.yaml",
        )

    def test_cw_manifest_has_chargen_path(self):
        from engine.world_loader import load_era_manifest
        manifest = load_era_manifest(Path("data") / "worlds" / "clone_wars")
        self.assertIsNotNone(manifest.chargen_templates_path)
        self.assertTrue(manifest.chargen_templates_path.is_file())


# ──────────────────────────────────────────────────────────────────────
# 7. Source-level guards
# ──────────────────────────────────────────────────────────────────────

class TestF7DocstringMarkers(unittest.TestCase):
    """Source-level guards mirroring the F.5d / B.1.d.3 pattern.
    Protect F.7's design intent against accidental reverts."""

    def test_seam_module_present(self):
        """The seam module exists and exports get_chargen_templates."""
        from engine import chargen_templates_loader
        self.assertTrue(hasattr(chargen_templates_loader, "get_chargen_templates"))
        self.assertTrue(hasattr(chargen_templates_loader, "_LEGACY_TEMPLATES_GCW"))

    def test_creation_module_no_inline_templates_literal(self):
        """engine/creation.py must NOT contain the pre-F.7 in-Python
        TEMPLATES literal anymore. The literal lives in the seam module
        (_LEGACY_TEMPLATES_GCW). Catches accidental reverts where
        someone re-adds the literal but forgets the seam path."""
        from engine import creation
        with open(creation.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        # The seam-resolved binding is what should be present
        self.assertIn(
            "TEMPLATES = _resolve_templates_at_import()",
            src,
            "engine/creation.py should resolve TEMPLATES via the seam",
        )
        # The pre-F.7 literal pattern would have lines like:
        #   TEMPLATES = {
        #       "smuggler": {
        # F.7's `_resolve_templates_at_import` function body should
        # NOT contain hardcoded template definitions. Loose check:
        # the substring '"smuggler": {' should not appear in
        # creation.py source any more — that pattern is the legacy
        # literal's signature.
        self.assertNotIn(
            '"smuggler": {', src,
            "engine/creation.py should not contain the pre-F.7 inline "
            "TEMPLATES literal — it lives in the seam module now",
        )

    def test_f7_marker_in_creation(self):
        from engine import creation
        with open(creation.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("F.7 (Apr 30 2026)", src)

    def test_f7_marker_in_seam(self):
        from engine import chargen_templates_loader
        with open(chargen_templates_loader.__file__, "r",
                  encoding="utf-8") as f:
            src = f.read()
        self.assertIn("F.7 (Apr 30 2026)", src)
        # The seam should document the Phase 1 / Phase 2 split
        self.assertIn("Phase 1", src)
        self.assertIn("Phase 2", src)
        self.assertIn("F.7.b", src)

    def test_world_loader_chargen_dataclasses_present(self):
        from engine import world_loader
        self.assertTrue(hasattr(world_loader, "ChargenTemplate"))
        self.assertTrue(hasattr(world_loader, "ChargenTemplatesCorpus"))
        self.assertTrue(hasattr(world_loader, "load_chargen_templates"))


# ──────────────────────────────────────────────────────────────────────
# 8. engine.creation.TEMPLATES integration
# ──────────────────────────────────────────────────────────────────────

class TestCreationModuleIntegration(unittest.TestCase):
    """engine.creation.TEMPLATES must be a non-empty dict at import
    time so existing CreationEngine consumers work without changes."""

    def test_creation_templates_is_dict(self):
        from engine.creation import TEMPLATES
        self.assertIsInstance(TEMPLATES, dict)

    def test_creation_templates_nonempty(self):
        from engine.creation import TEMPLATES
        self.assertGreater(len(TEMPLATES), 0,
                           "TEMPLATES must be non-empty post-F.7 — the "
                           "seam resolved to no archetypes which would "
                           "break chargen entirely")

    def test_creation_templates_has_smuggler(self):
        """smuggler is in both GCW and CW templates — this should
        succeed regardless of which era resolves at test time."""
        from engine.creation import TEMPLATES
        self.assertIn("smuggler", TEMPLATES)

    def test_creation_templates_each_template_has_required_fields(self):
        from engine.creation import TEMPLATES
        for key, tmpl in TEMPLATES.items():
            self.assertIn("label", tmpl)
            self.assertIn("species", tmpl)
            self.assertIn("attributes", tmpl)
            self.assertIn("skills", tmpl)


if __name__ == "__main__":
    unittest.main()
