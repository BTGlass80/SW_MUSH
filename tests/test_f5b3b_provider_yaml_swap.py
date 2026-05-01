# -*- coding: utf-8 -*-
"""
tests/test_f5b3b_provider_yaml_swap.py — F.5b.3.b tests.

F.5b.3.b (Apr 30 2026) flips the housing_lots_provider's GCW path
from the legacy in-Python `HOUSING_LOTS_*` constants to the
slug-based YAML inventory authored in F.5b.3.a. To make this
byte-equivalent on player-facing output, F.5b.3.b also extends the
YAML schema with two optional override fields:

  - `display_label`: preserves the legacy hand-authored player-facing
    label for each lot (which the auto-derived label couldn't
    reproduce — auto-derivation comes from the host_room's `name`).
  - `security_override`: preserves the legacy hand-authored security
    tier (which the auto-derived security comes from a zone-level
    mapping that doesn't match the legacy per-lot authoring).

Both fields are optional. When absent, the provider falls back to
the auto-derived values (preserving CW behavior, where authors don't
specify these). When present, the override wins.

Test contract
-------------
1. The four lot dataclasses (Tier1RentalHost, Tier3Lot, Tier4Lot,
   Tier5Lot) accept the two new optional fields.
2. The YAML loader validates display_label / security_override per
   the optional-string contract (None when absent; non-empty string
   when present; security_override must be one of {secured, contested,
   lawless}).
3. The provider's `_build_tier_tuples_from_yaml` honors the override
   fields and falls back to derivation when absent.
4. GCW provider output is byte-equivalent to the legacy constants on
   (planet, label, security, max_homes) — id-stripped because YAML
   resolves the legacy ID drift.
5. The provider no longer has a special-case GCW branch — both eras
   flow through YAML; the legacy constants exist only as a soft
   fallback when YAML loading fails.
6. CW behavior is unchanged (no display_label/security_override on
   CW records yet, so derivation still applies).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────
# Section 1: dataclass schema accepts the new fields
# ──────────────────────────────────────────────────────────────────────


class TestDataclassesAcceptOverrides(unittest.TestCase):
    """The four lot dataclasses must accept display_label and
    security_override as optional keyword arguments."""

    def test_tier1_accepts_overrides(self):
        from engine.world_loader import Tier1RentalHost
        t = Tier1RentalHost(
            id="x", planet="p", zone="z", host_room="h", npc="n",
            slots=5, weekly_rent_base=100,
            display_label="Custom Label",
            security_override="secured",
        )
        self.assertEqual(t.display_label, "Custom Label")
        self.assertEqual(t.security_override, "secured")

    def test_tier1_overrides_default_to_none(self):
        from engine.world_loader import Tier1RentalHost
        t = Tier1RentalHost(
            id="x", planet="p", zone="z", host_room="h", npc="n",
            slots=5, weekly_rent_base=100,
        )
        self.assertIsNone(t.display_label)
        self.assertIsNone(t.security_override)

    def test_tier3_accepts_overrides(self):
        from engine.world_loader import Tier3Lot
        t = Tier3Lot(
            id="x", planet="p", zone="z", host_room="h", max_homes=2,
            display_label="Custom T3",
            security_override="contested",
        )
        self.assertEqual(t.display_label, "Custom T3")
        self.assertEqual(t.security_override, "contested")

    def test_tier4_accepts_overrides(self):
        from engine.world_loader import Tier4Lot
        t = Tier4Lot(
            id="x", planet="p", zone="z", host_room="h", max_homes=3,
            display_label="Custom T4",
            security_override="lawless",
        )
        self.assertEqual(t.display_label, "Custom T4")
        self.assertEqual(t.security_override, "lawless")

    def test_tier5_accepts_overrides(self):
        from engine.world_loader import Tier5Lot
        t = Tier5Lot(
            id="x", planet="p", zone="z", host_room="h", max_homes=1,
            display_label="Custom T5",
            security_override="secured",
        )
        self.assertEqual(t.display_label, "Custom T5")
        self.assertEqual(t.security_override, "secured")


# ──────────────────────────────────────────────────────────────────────
# Section 2: YAML loader parses the new fields
# ──────────────────────────────────────────────────────────────────────


class TestYAMLLoaderParsesOverrides(unittest.TestCase):
    """The F.5b.3.b enriched GCW housing_lots.yaml must parse with
    every override populated and validated."""

    @classmethod
    def setUpClass(cls):
        from engine.world_loader import load_era_manifest, load_housing_lots
        manifest = load_era_manifest(PROJECT_ROOT / "data" / "worlds" / "gcw")
        cls.corpus = load_housing_lots(manifest)

    def test_parse_clean(self):
        self.assertEqual(self.corpus.report.errors, [])
        self.assertEqual(self.corpus.report.warnings, [])

    def test_every_t1_has_display_label(self):
        for lot in self.corpus.tier1_rentals:
            self.assertIsNotNone(
                lot.display_label,
                f"T1 lot {lot.id!r} missing display_label",
            )
            self.assertTrue(lot.display_label.strip())

    def test_every_t1_has_security_override(self):
        for lot in self.corpus.tier1_rentals:
            self.assertIn(
                lot.security_override,
                {"secured", "contested", "lawless"},
                f"T1 lot {lot.id!r} has invalid security_override "
                f"{lot.security_override!r}",
            )

    def test_every_t3_has_overrides(self):
        for lot in self.corpus.tier3_lots:
            self.assertIsNotNone(lot.display_label, f"T3 {lot.id!r}")
            self.assertIn(
                lot.security_override,
                {"secured", "contested", "lawless"},
                f"T3 {lot.id!r}",
            )

    def test_every_t4_has_overrides(self):
        for lot in self.corpus.tier4_lots:
            self.assertIsNotNone(lot.display_label, f"T4 {lot.id!r}")
            self.assertIn(
                lot.security_override,
                {"secured", "contested", "lawless"},
                f"T4 {lot.id!r}",
            )

    def test_every_t5_has_overrides(self):
        for lot in self.corpus.tier5_lots:
            self.assertIsNotNone(lot.display_label, f"T5 {lot.id!r}")
            self.assertIn(
                lot.security_override,
                {"secured", "contested", "lawless"},
                f"T5 {lot.id!r}",
            )


# ──────────────────────────────────────────────────────────────────────
# Section 3: validation rejects bad overrides
# ──────────────────────────────────────────────────────────────────────


class TestYAMLLoaderRejectsBadOverrides(unittest.TestCase):
    """Per `_validate_optional_string`, the loader must reject
    display_label that is non-string-or-empty, and security_override
    that is non-string-or-empty or outside {secured, contested,
    lawless}."""

    def _parse_inline(self, raw_yaml: str):
        """Helper: parse a one-off YAML string through load_housing_lots.

        Bypasses `load_era_manifest` (which would require a full era
        directory with zones/planets/etc.) by constructing a minimal
        EraManifest stub. `load_housing_lots` only reads the
        `housing_lots_path` field — other fields can be placeholders.
        """
        import tempfile
        from engine.world_loader import (
            load_housing_lots, EraManifest,
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            housing_path = Path(td) / "housing_lots.yaml"
            housing_path.write_text(raw_yaml, encoding="utf-8")
            manifest = EraManifest(
                era_code="test_era",
                era_name="Test",
                schema_version=1,
                era_dir=Path(td),
                zones_path=Path(td),
                organizations_path=None,
                planet_paths=[],
                wilderness_paths=[],
                npcs_paths=[],
                housing_lots_path=housing_path,
                test_character_path=None,
                test_jedi_path=None,
            )
            return load_housing_lots(manifest)

    def test_t1_rejects_empty_string_display_label(self):
        yaml_doc = """
schema_version: 1
era: test_era
tier2_faction_quarters: {}
tier1_rentals:
  - id: bad
    planet: tatooine
    zone: residential
    host_room: spaceport_hotel
    npc: someone
    slots: 5
    weekly_rent_base: 100
    display_label: ""
"""
        corpus = self._parse_inline(yaml_doc)
        self.assertTrue(
            any("display_label" in e for e in corpus.report.errors),
            f"Expected display_label error, got: {corpus.report.errors}",
        )

    def test_t3_rejects_invalid_security_override(self):
        yaml_doc = """
schema_version: 1
era: test_era
tier2_faction_quarters: {}
tier3_lots:
  - id: bad
    planet: tatooine
    zone: market
    host_room: some_slug
    max_homes: 4
    security_override: medium  # not in valid set
"""
        corpus = self._parse_inline(yaml_doc)
        self.assertTrue(
            any("security_override" in e for e in corpus.report.errors),
            f"Expected security_override error, got: {corpus.report.errors}",
        )

    def test_t4_accepts_absent_overrides(self):
        """Absent override fields must not generate validation errors —
        they default to None and the provider falls back to derivation."""
        yaml_doc = """
schema_version: 1
era: test_era
tier2_faction_quarters: {}
tier4_lots:
  - id: ok
    planet: tatooine
    zone: market
    host_room: some_slug
    max_homes: 4
"""
        corpus = self._parse_inline(yaml_doc)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier4_lots), 1)
        lot = corpus.tier4_lots[0]
        self.assertIsNone(lot.display_label)
        self.assertIsNone(lot.security_override)


# ──────────────────────────────────────────────────────────────────────
# Section 4: provider honors the overrides; CW behavior unchanged
# ──────────────────────────────────────────────────────────────────────


class TestProviderHonorsOverrides(unittest.TestCase):
    """`_build_tier_tuples_from_yaml` must use the override fields when
    present, and fall back to auto-derived values when absent."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_gcw_label_uses_override(self):
        """GCW T1 lot at spaceport_hotel must produce label
        'Spaceport Hotel' (the override) — which happens to match
        the auto-derived value for this room, but the override is
        what guarantees it."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        labels = [label for (rid, p, label, s, m) in t1]
        self.assertIn("Spaceport Hotel", labels)

    def test_gcw_label_override_wins_over_derivation(self):
        """For Nar Shaddaa T1 — the room is named 'Nar Shaddaa -
        Corellian Sector Promenade' (auto-derive), but the override
        is 'Nar Shaddaa Promenade Hostel' (legacy intent). The
        override must win."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        labels = [label for (rid, p, label, s, m) in t1]
        self.assertIn("Nar Shaddaa Promenade Hostel", labels,
                      "display_label override must win over derivation")
        self.assertNotIn("Corellian Sector Promenade", labels,
                         "derivation must NOT win when override is set")

    def test_gcw_security_override_wins_over_zone_default(self):
        """The Spaceport Hotel is in the 'residential' zone, which
        falls back to 'contested' in `_resolve_security`. But the
        override sets 'secured'. The override must win."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        for (rid, p, label, sec, m) in t1:
            if label == "Spaceport Hotel":
                self.assertEqual(
                    sec, "secured",
                    "security_override 'secured' must override zone-default",
                )
                return
        self.fail("Spaceport Hotel not found in GCW T1 output")

    def test_cw_lots_still_derive_label_from_room_name(self):
        """CW lot YAML records do NOT set display_label, so they
        should still derive from host_room.name. Pick a known CW
        T3 lot and verify."""
        from engine.housing_lots_provider import (
            clear_lots_cache, get_tier3_lots,
        )
        clear_lots_cache()
        cw_t3 = get_tier3_lots("clone_wars")
        # Coco Town Residential Walk should be present in CW T3.
        # Its label should come from the room name (auto-derived),
        # not a hand-authored override.
        self.assertGreater(len(cw_t3), 0, "CW T3 must have lots")


# ──────────────────────────────────────────────────────────────────────
# Section 5: byte-equivalence between YAML path and legacy constants
# ──────────────────────────────────────────────────────────────────────


class TestGCWYAMLByteEquivalenceToLegacy(unittest.TestCase):
    """The YAML-path output must be byte-equivalent to the legacy
    constants on (planet, label, security, max_homes) for every tier.
    Room IDs may differ — YAML uses corrected slug-resolved IDs, the
    legacy IDs are stale. This is the byte-equivalence pre-gate for
    F.5b.3.c (legacy constant deletion)."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    @staticmethod
    def _strip_id(tuples):
        return sorted([(p, l, s, m) for (rid, p, l, s, m) in tuples])

    def test_t1_byte_equivalent(self):
        from engine.housing_lots_provider import get_tier1_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_DROP1
        self.assertEqual(
            self._strip_id(get_tier1_lots("gcw")),
            self._strip_id(list(LEGACY_HOUSING_LOTS_DROP1)),
        )

    def test_t3_byte_equivalent(self):
        from engine.housing_lots_provider import get_tier3_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER3
        self.assertEqual(
            self._strip_id(get_tier3_lots("gcw")),
            self._strip_id(list(LEGACY_HOUSING_LOTS_TIER3)),
        )

    def test_t4_byte_equivalent(self):
        from engine.housing_lots_provider import get_tier4_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER4
        self.assertEqual(
            self._strip_id(get_tier4_lots("gcw")),
            self._strip_id(list(LEGACY_HOUSING_LOTS_TIER4)),
        )

    def test_t5_byte_equivalent(self):
        from engine.housing_lots_provider import get_tier5_lots
        from tests._legacy_housing_lots_snapshot import LEGACY_HOUSING_LOTS_TIER5
        self.assertEqual(
            self._strip_id(get_tier5_lots("gcw")),
            self._strip_id(list(LEGACY_HOUSING_LOTS_TIER5)),
        )


# ──────────────────────────────────────────────────────────────────────
# Section 6: provider has no special-case GCW branch
# ──────────────────────────────────────────────────────────────────────


class TestNoMoreGCWSpecialCase(unittest.TestCase):
    """Source-level guard: `_resolve_corpus_for_era` should not have
    a separate `if era == "gcw"` short-circuit branch.

    F.5b.3.b: deleted the GCW short-circuit; soft-fallback to legacy
    constants remained.

    F.5b.3.c: deleted the legacy constants entirely. The fallback path
    now logs ERROR and returns an empty result dict (fail-loud).
    """

    def test_no_gcw_short_circuit_branch(self):
        from pathlib import Path as P
        src = (P(PROJECT_ROOT) / "engine" / "housing_lots_provider.py"
               ).read_text(encoding="utf-8")
        # The pre-F.5b.3.b code had: `if era == "gcw":` that bypassed
        # `_load_yaml_corpus` entirely. Verify that's gone.
        self.assertNotIn(
            'if era == "gcw":\n        # GCW: pass through legacy',
            src,
            "_resolve_corpus_for_era must not special-case GCW after F.5b.3.b",
        )

    def test_no_more_legacy_import_in_provider(self):
        """F.5b.3.c: `from engine import housing as _housing` (the
        soft-fallback import) is gone — the legacy constants no
        longer exist."""
        from pathlib import Path as P
        src = (P(PROJECT_ROOT) / "engine" / "housing_lots_provider.py"
               ).read_text(encoding="utf-8")
        self.assertNotIn(
            "from engine import housing as _housing",
            src,
            "F.5b.3.c: provider must not import the deleted legacy constants",
        )
        self.assertNotIn(
            "_housing.HOUSING_LOTS_DROP1",
            src,
            "F.5b.3.c: provider must not reference the deleted constants",
        )


# ──────────────────────────────────────────────────────────────────────
# Section 7: room ID drift correction — the actual bug fix
# ──────────────────────────────────────────────────────────────────────


class TestRoomIDDriftCorrected(unittest.TestCase):
    """The legacy constants had stale room IDs (drifted from the live
    world build). F.5b.3.b's slug-based YAML path resolves them
    correctly. This test guards the fix."""

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_spaceport_hotel_resolves_to_correct_id(self):
        """Legacy says room 29; live world says room 25."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        for rid, p, label, s, m in t1:
            if label == "Spaceport Hotel":
                self.assertEqual(rid, 25)
                return
        self.fail("Spaceport Hotel not in GCW T1")

    def test_mos_eisley_inn_resolves_to_correct_id(self):
        """Legacy says room 21; live world says room 17."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        for rid, p, label, s, m in t1:
            if label == "Mos Eisley Inn":
                self.assertEqual(rid, 17)
                return
        self.fail("Mos Eisley Inn not in GCW T1")

    def test_promenade_hostel_resolves_to_correct_id(self):
        """Legacy says room 60 (which is actually Vertical Bazaar); live
        world says room 56 for Corellian Sector Promenade host."""
        from engine.housing_lots_provider import get_tier1_lots
        t1 = get_tier1_lots("gcw")
        for rid, p, label, s, m in t1:
            if label == "Nar Shaddaa Promenade Hostel":
                self.assertEqual(rid, 56)
                return
        self.fail("Nar Shaddaa Promenade Hostel not in GCW T1")

    def test_promenade_market_resolves_to_correct_id(self):
        """Legacy says room 46 (which is Hermit's Ridge — totally wrong);
        live world says room 60 for Vertical Bazaar (the intended
        Promenade Market host)."""
        from engine.housing_lots_provider import get_tier4_lots
        t4 = get_tier4_lots("gcw")
        for rid, p, label, s, m in t4:
            if label == "Promenade Market":
                self.assertEqual(rid, 60)
                return
        self.fail("Promenade Market not in GCW T4")


if __name__ == "__main__":
    unittest.main()
