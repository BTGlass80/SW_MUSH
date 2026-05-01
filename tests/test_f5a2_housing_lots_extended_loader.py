# -*- coding: utf-8 -*-
"""
tests/test_f5a2_housing_lots_extended_loader.py — F.5a.2 loader extension tests

Per cw_housing_design_v1.md §11 (the housing_lots.yaml schema). F.5a.2
extends `engine/world_loader.py::load_housing_lots()` to parse the
remaining four lot-inventory sections:

  - tier1_rentals  → list[Tier1RentalHost]
  - tier3_lots     → list[Tier3Lot]
  - tier4_lots     → list[Tier4Lot]
  - tier5_lots     → list[Tier5Lot]

Each section is optional and may be empty. F.5a.1's existing tests
(`tests/test_f5a1_housing_lots_loader.py`) prove backwards compat: the
existing GCW + CW YAMLs (which have empty arrays for these four
sections) still parse cleanly with no errors.

What's tested in this file:
  - Backwards compat: empty / missing sections parse fine
  - Per-tier dataclass construction with all fields populated
  - Required-field validation: missing id/planet/zone/host_room
  - Type validation: string-typed fields reject non-strings
  - Numeric validation: slots/max_homes/weekly_rent_base reject negative,
    bool, non-int
  - Duplicate-id detection within a section
  - rep_gate (T3 only) validation: missing/extra fields, type checks
  - Optional-field handling: max_stay_weeks (T1), market_search_priority
    (T4), recommended_faction (T5)
  - T5 max_homes defaults to 1 when absent
  - Cross-tier id collisions are NOT errors (different sections, different
    namespaces — by design)
  - Existing GCW + CW YAMLs still load with empty T1/T3/T4/T5 lists

What's NOT tested here:
  - Live engine consumption of the parsed lots (comes in F.5b.2 with the
    rep_gate filter and the `list_available_lots()` data-fy)
  - Actual lot inventory authoring (comes in F.5a.3 — populating the
    YAMLs with the real ~46-lot inventory)
  - housing_descriptions.yaml (comes in F.5a.4)
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# Test helpers: build an isolated era directory with a custom YAML and
# load it through the public loader API. This avoids touching the real
# data/worlds/{gcw,clone_wars}/housing_lots.yaml during validation tests.
#
# IMPORTANT: We compose the housing_lots.yaml string by concatenating
# column-0 lines rather than nesting textwrap.dedent inside f-strings.
# The latter approach is fragile because dedent's common-prefix
# calculation interacts badly with substitution (the substituted text
# arrives at column 0, so dedent computes a common prefix of 0 and
# leaves the surrounding template's own indent intact, breaking YAML).
# ──────────────────────────────────────────────────────────────────────


def _build_isolated_era(tmpdir: Path, era_name: str,
                       housing_yaml_text: str) -> Path:
    """Build a minimal era manifest + housing_lots.yaml under tmpdir.

    Returns the era dir path. Caller passes this to load_era_manifest().
    The era manifest references housing_lots.yaml so the loader picks
    it up. The era.yaml shape mirrors what F.5a.1's tests use so this
    helper stays consistent with the loader's actual contract.
    """
    era_dir = tmpdir / era_name
    era_dir.mkdir(parents=True, exist_ok=True)

    # Minimal era.yaml — same shape F.5a.1's tests use. Requires zones
    # and housing_lots content_refs; planets/wilderness can be empty.
    era_yaml_text = textwrap.dedent(f"""
        schema_version: 1
        era: {{ code: {era_name}, name: "Test Era ({era_name})" }}
        content_refs:
          zones: zones.yaml
          housing_lots: housing_lots.yaml
          planets: []
          wilderness: []
    """).strip() + "\n"
    (era_dir / "era.yaml").write_text(era_yaml_text, encoding="utf-8")

    # Minimal zones.yaml stub — load_era_manifest requires the file to
    # exist when zones is declared as required (which it is).
    (era_dir / "zones.yaml").write_text("zones: {}\n", encoding="utf-8")

    (era_dir / "housing_lots.yaml").write_text(
        housing_yaml_text, encoding="utf-8"
    )
    return era_dir


def _compose_housing_yaml(*, tier1_records: str = "",
                          tier3_records: str = "",
                          tier4_records: str = "",
                          tier5_records: str = "",
                          tier2_quarters_inline: str = "{}") -> str:
    """Compose a housing_lots.yaml string with optional sections.

    Each `tierN_records` argument is the YAML body (records) only —
    column-0 indented (typical YAML list shape, "- id: foo" at the
    start of the line). The section header line (`tier1_rentals:`,
    etc.) is added here. When a tierN_records is empty, the section
    is emitted as `tierN_<rentals|lots>: []` to keep the YAML
    well-formed.
    """
    lines: list = ["schema_version: 1", "era: test_era",
                   f"tier2_faction_quarters: {tier2_quarters_inline}"]

    if tier1_records.strip():
        lines.append("tier1_rentals:")
        lines.append(tier1_records.rstrip("\n"))
    else:
        lines.append("tier1_rentals: []")

    if tier3_records.strip():
        lines.append("tier3_lots:")
        lines.append(tier3_records.rstrip("\n"))
    else:
        lines.append("tier3_lots: []")

    if tier4_records.strip():
        lines.append("tier4_lots:")
        lines.append(tier4_records.rstrip("\n"))
    else:
        lines.append("tier4_lots: []")

    if tier5_records.strip():
        lines.append("tier5_lots:")
        lines.append(tier5_records.rstrip("\n"))
    else:
        lines.append("tier5_lots: []")

    return "\n".join(lines) + "\n"


def _load_corpus(era_dir: Path):
    """Load the housing corpus from an isolated era dir."""
    from engine.world_loader import load_era_manifest, load_housing_lots
    manifest = load_era_manifest(era_dir)
    return load_housing_lots(manifest)


def _load_with_sections(era_name: str = "f5a2_test", **kwargs):
    """Convenience: build an isolated era from optional tierN_records
    kwargs, load the corpus, return it. The caller doesn't need to
    manage tempdirs."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        yaml_text = _compose_housing_yaml(**kwargs)
        era_dir = _build_isolated_era(tmpdir, era_name, yaml_text)
        return _load_corpus(era_dir)


# ──────────────────────────────────────────────────────────────────────
# 1. Backwards compatibility: existing F.5a.1 YAMLs still load
# ──────────────────────────────────────────────────────────────────────


class TestBackwardsCompatWithF5a1(unittest.TestCase):
    """The F.5a.1 YAMLs (live in data/worlds/{gcw,clone_wars}/) initially
    declared empty `tier1_rentals: []`, `tier3_lots: []`, etc. After
    F.5a.2 the loader must still accept these. After F.5b.3.a (Apr 30
    2026) GCW's housing_lots.yaml carries an authored T1/T3/T4/T5
    inventory mirroring the legacy in-Python constants; the loader
    must accept BOTH empty and populated inventories.
    """

    def _load(self, era: str):
        from engine.world_loader import load_era_manifest, load_housing_lots
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / era
        )
        return load_housing_lots(manifest)

    def test_gcw_loads_cleanly(self):
        """After F.5b.3.a, GCW housing_lots.yaml is populated with the
        T1/T3/T4/T5 inventory — counts must match the legacy constant
        cardinalities (the byte-equivalence pre-gate for F.5b.3.b).

        F.5b.3.c (Apr 30 2026): the engine.housing constants were
        deleted; the cardinality reference is now the frozen snapshot
        in tests/_legacy_housing_lots_snapshot.py.
        """
        from tests._legacy_housing_lots_snapshot import (
            LEGACY_HOUSING_LOTS_DROP1, LEGACY_HOUSING_LOTS_TIER3,
            LEGACY_HOUSING_LOTS_TIER4, LEGACY_HOUSING_LOTS_TIER5,
        )
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "housing_lots.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/housing_lots.yaml not present")
        corpus = self._load("gcw")
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.report.errors, [],
                         f"GCW load produced errors: {corpus.report.errors}")
        # F.5b.3.a counts must match legacy snapshot cardinalities.
        self.assertEqual(
            len(corpus.tier1_rentals), len(LEGACY_HOUSING_LOTS_DROP1),
            "F.5b.3.a T1 inventory must mirror legacy DROP1 cardinality",
        )
        self.assertEqual(
            len(corpus.tier3_lots), len(LEGACY_HOUSING_LOTS_TIER3),
            "F.5b.3.a T3 inventory must mirror legacy TIER3 cardinality",
        )
        self.assertEqual(
            len(corpus.tier4_lots), len(LEGACY_HOUSING_LOTS_TIER4),
            "F.5b.3.a T4 inventory must mirror legacy TIER4 cardinality",
        )
        self.assertEqual(
            len(corpus.tier5_lots), len(LEGACY_HOUSING_LOTS_TIER5),
            "F.5b.3.a T5 inventory must mirror legacy TIER5 cardinality",
        )

    def test_clone_wars_loads_with_populated_lot_inventories(self):
        """After F.5a.3 (Apr 30 2026), CW housing_lots.yaml ships with
        13 T1 / 16 T3 / 8 T4 / 9 T5 records. The loader must accept
        the populated inventory cleanly, with no validation errors,
        and produce the expected record counts. If F.5a.3's content
        is later expanded, update the expected counts here."""
        cw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
                   "housing_lots.yaml")
        if not cw_yaml.is_file():
            self.skipTest("data/worlds/clone_wars/housing_lots.yaml not present")
        corpus = self._load("clone_wars")
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.report.errors, [],
                         f"CW load produced errors: {corpus.report.errors}")
        # F.5a.3 expected counts
        self.assertEqual(len(corpus.tier1_rentals), 13)
        self.assertEqual(len(corpus.tier3_lots), 16)
        self.assertEqual(len(corpus.tier4_lots), 8)
        self.assertEqual(len(corpus.tier5_lots), 9)
        # Sanity: at least 2 T3 lots have rep_gate (Kuat KDY + Embassy)
        rep_gated = [r for r in corpus.tier3_lots if r.rep_gate]
        self.assertGreaterEqual(len(rep_gated), 2,
            "Expected ≥2 rep-gated T3 lots (Kuat KDY + Embassy per design §7.1).")
        # Sanity: Kamino lot has the 2-week stay cap
        kamino_lots = [r for r in corpus.tier1_rentals if r.planet == "kamino"]
        self.assertEqual(len(kamino_lots), 1,
            "Expected exactly one Kamino T1 lot (Visiting Officers' Quarters).")
        self.assertEqual(kamino_lots[0].max_stay_weeks, 2,
            "Kamino lot must have max_stay_weeks: 2 per design §6.")
        # Sanity: flagship Coco Town Market Arcade has priority 100
        flagship = [r for r in corpus.tier4_lots
                    if r.id == "coco_town_market_arcade"]
        self.assertEqual(len(flagship), 1)
        self.assertEqual(flagship[0].market_search_priority, 100,
            "coco_town_market_arcade must have market_search_priority: 100 "
            "per design §8 (flagship CW shopfront).")

    def test_yaml_with_no_lot_sections_at_all(self):
        """If the YAML omits T1/T3/T4/T5 entirely (only has T2 quarters),
        the loader still works — empty lists in corpus, no errors."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            yaml_text = (
                "schema_version: 1\n"
                "era: test_era\n"
                "tier2_faction_quarters: {}\n"
            )
            era_dir = _build_isolated_era(tmpdir, "test_era", yaml_text)
            corpus = _load_corpus(era_dir)

        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier1_rentals, [])
        self.assertEqual(corpus.tier3_lots, [])
        self.assertEqual(corpus.tier4_lots, [])
        self.assertEqual(corpus.tier5_lots, [])


# ──────────────────────────────────────────────────────────────────────
# 2. Tier 1 rental hosts: happy path + validation
# ──────────────────────────────────────────────────────────────────────


class TestTier1RentalHosts(unittest.TestCase):
    """Validate Tier1RentalHost parsing and field validation."""

    def test_full_tier1_record(self):
        """All fields populated → exactly one Tier1RentalHost in corpus."""
        records = (
            "- id: westport_travelers_hotel\n"
            "  planet: coruscant\n"
            "  zone: westport_district\n"
            "  host_room: westport_arrivals_hotel_lobby\n"
            "  npc: rental_clerk_wx9\n"
            "  slots: 6\n"
            "  weekly_rent_base: 50\n"
            "  description_theme: corporate_chain\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier1_rentals), 1)
        host = corpus.tier1_rentals[0]
        self.assertEqual(host.id, "westport_travelers_hotel")
        self.assertEqual(host.planet, "coruscant")
        self.assertEqual(host.zone, "westport_district")
        self.assertEqual(host.host_room, "westport_arrivals_hotel_lobby")
        self.assertEqual(host.npc, "rental_clerk_wx9")
        self.assertEqual(host.slots, 6)
        self.assertEqual(host.weekly_rent_base, 50)
        self.assertEqual(host.description_theme, "corporate_chain")
        self.assertIsNone(host.max_stay_weeks)

    def test_optional_max_stay_weeks(self):
        """The Kamino transient cap field per §6 — when present, must be
        a positive int."""
        records = (
            "- id: kamino_ocean_platform\n"
            "  planet: kamino\n"
            "  zone: ocean_platforms\n"
            "  host_room: ocean_platform_visitor_quarters\n"
            "  npc: kaminoan_lodgings_attendant\n"
            "  slots: 4\n"
            "  weekly_rent_base: 80\n"
            "  max_stay_weeks: 2\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier1_rentals[0].max_stay_weeks, 2)

    def test_missing_id_field_skips_record(self):
        records = (
            "- planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: outlander_cantina\n"
            "  npc: doola_bartender\n"
            "  slots: 5\n"
            "  weekly_rent_base: 50\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        self.assertEqual(len(corpus.tier1_rentals), 0)
        self.assertTrue(any("'id' must be a non-empty string" in e
                            for e in corpus.report.errors),
                        f"errors: {corpus.report.errors}")

    def test_negative_slots_skips_record(self):
        records = (
            "- id: bad_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: bad_room\n"
            "  npc: clerk\n"
            "  slots: -1\n"
            "  weekly_rent_base: 50\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        self.assertEqual(len(corpus.tier1_rentals), 0)
        self.assertTrue(any("'slots'" in e for e in corpus.report.errors))

    def test_negative_rent_skips_record(self):
        records = (
            "- id: bad_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: bad_room\n"
            "  npc: clerk\n"
            "  slots: 5\n"
            "  weekly_rent_base: -10\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        self.assertEqual(len(corpus.tier1_rentals), 0)
        self.assertTrue(any("'weekly_rent_base'" in e
                            for e in corpus.report.errors))

    def test_zero_max_stay_weeks_is_invalid(self):
        """`max_stay_weeks: 0` is meaningless (no stay allowed)."""
        records = (
            "- id: bad_lot\n"
            "  planet: kamino\n"
            "  zone: ocean_platforms\n"
            "  host_room: bad_room\n"
            "  npc: clerk\n"
            "  slots: 4\n"
            "  weekly_rent_base: 80\n"
            "  max_stay_weeks: 0\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        self.assertEqual(len(corpus.tier1_rentals), 0)
        self.assertTrue(any("'max_stay_weeks'" in e
                            for e in corpus.report.errors))

    def test_duplicate_id_within_t1_section_records_error(self):
        records = (
            "- id: dupe_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_a\n"
            "  npc: clerk_a\n"
            "  slots: 5\n"
            "  weekly_rent_base: 50\n"
            "- id: dupe_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_b\n"
            "  npc: clerk_b\n"
            "  slots: 5\n"
            "  weekly_rent_base: 50\n"
        )
        corpus = _load_with_sections(tier1_records=records)
        # First wins; second is rejected.
        self.assertEqual(len(corpus.tier1_rentals), 1)
        self.assertTrue(any("duplicate id 'dupe_lot'" in e
                            for e in corpus.report.errors))


# ──────────────────────────────────────────────────────────────────────
# 3. Tier 3 private residence lots — including rep_gate
# ──────────────────────────────────────────────────────────────────────


class TestTier3Lots(unittest.TestCase):
    """Validate Tier3Lot parsing — including the rep_gate field that
    F.5b.2 will hook into for faction-rep-locked lots."""

    def test_full_tier3_record(self):
        records = (
            "- id: coco_town_residential_walk\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: coco_town_residential_walk\n"
            "  max_homes: 4\n"
            "  allowed_types: [studio, standard, deluxe]\n"
            "  description_theme: midlevel_apartment\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier3_lots), 1)
        lot = corpus.tier3_lots[0]
        self.assertEqual(lot.id, "coco_town_residential_walk")
        self.assertEqual(lot.max_homes, 4)
        self.assertEqual(lot.allowed_types, ["studio", "standard", "deluxe"])
        self.assertIsNone(lot.rep_gate)

    def test_rep_gate_field_parsed(self):
        """The Kuat KDY engineer apartments need Republic rep ≥ 25."""
        records = (
            "- id: kdy_engineer_apartments\n"
            "  planet: kuat\n"
            "  zone: kdy_orbital_ring\n"
            "  host_room: kdy_engineer_apartments\n"
            "  max_homes: 3\n"
            "  allowed_types: [studio, standard]\n"
            "  description_theme: industrial_dormitory\n"
            "  rep_gate:\n"
            "    faction: republic\n"
            "    min_value: 25\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(corpus.report.errors, [])
        lot = corpus.tier3_lots[0]
        self.assertIsNotNone(lot.rep_gate)
        self.assertEqual(lot.rep_gate, {"faction": "republic", "min_value": 25})

    def test_rep_gate_missing_faction_invalid(self):
        records = (
            "- id: bad_lot\n"
            "  planet: kuat\n"
            "  zone: kdy_orbital_ring\n"
            "  host_room: room_a\n"
            "  max_homes: 3\n"
            "  rep_gate:\n"
            "    min_value: 25\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(len(corpus.tier3_lots), 0)
        self.assertTrue(any("rep_gate.faction" in e
                            for e in corpus.report.errors))

    def test_rep_gate_missing_min_value_invalid(self):
        records = (
            "- id: bad_lot\n"
            "  planet: kuat\n"
            "  zone: kdy_orbital_ring\n"
            "  host_room: room_a\n"
            "  max_homes: 3\n"
            "  rep_gate:\n"
            "    faction: republic\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(len(corpus.tier3_lots), 0)
        self.assertTrue(any("rep_gate.min_value" in e
                            for e in corpus.report.errors))

    def test_rep_gate_negative_min_value_allowed(self):
        """A negative `min_value` is a meaningful design choice — gating
        a lot to characters who have wronged a faction. The loader
        accepts any int."""
        records = (
            "- id: smuggler_lot\n"
            "  planet: tatooine\n"
            "  zone: jundland_wastes\n"
            "  host_room: jundland_compound\n"
            "  max_homes: 2\n"
            "  rep_gate:\n"
            "    faction: empire\n"
            "    min_value: -50\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier3_lots[0].rep_gate["min_value"], -50)

    def test_max_homes_zero_is_invalid(self):
        """A T3 lot with 0 max_homes serves no purpose — invalid."""
        records = (
            "- id: bad_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_a\n"
            "  max_homes: 0\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(len(corpus.tier3_lots), 0)
        self.assertTrue(any("'max_homes'" in e
                            for e in corpus.report.errors))

    def test_allowed_types_must_be_list(self):
        records = (
            "- id: bad_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_a\n"
            "  max_homes: 3\n"
            "  allowed_types: \"studio\"\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(len(corpus.tier3_lots), 0)
        self.assertTrue(any("'allowed_types'" in e
                            for e in corpus.report.errors))

    def test_allowed_types_can_be_omitted(self):
        """When absent, defaults to []."""
        records = (
            "- id: simple_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_a\n"
            "  max_homes: 3\n"
        )
        corpus = _load_with_sections(tier3_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier3_lots[0].allowed_types, [])


# ──────────────────────────────────────────────────────────────────────
# 4. Tier 4 shopfront lots
# ──────────────────────────────────────────────────────────────────────


class TestTier4Lots(unittest.TestCase):
    """Validate Tier4Lot parsing including the optional
    market_search_priority field."""

    def test_full_tier4_record(self):
        records = (
            "- id: coco_town_market_arcade\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: coco_town_market_arcade\n"
            "  max_homes: 4\n"
            "  allowed_types: [stall, merchant, trading]\n"
            "  description_theme: bustling_arcade\n"
            "  market_search_priority: 100\n"
        )
        corpus = _load_with_sections(tier4_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier4_lots), 1)
        lot = corpus.tier4_lots[0]
        self.assertEqual(lot.id, "coco_town_market_arcade")
        self.assertEqual(lot.allowed_types, ["stall", "merchant", "trading"])
        self.assertEqual(lot.market_search_priority, 100)

    def test_market_search_priority_defaults_to_zero(self):
        records = (
            "- id: ordinary_shopfront\n"
            "  planet: tatooine\n"
            "  zone: mos_eisley_core\n"
            "  host_room: mos_eisley_market\n"
            "  max_homes: 3\n"
            "  allowed_types: [stall]\n"
        )
        corpus = _load_with_sections(tier4_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier4_lots[0].market_search_priority, 0)

    def test_negative_priority_invalid(self):
        records = (
            "- id: bad_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_a\n"
            "  max_homes: 4\n"
            "  market_search_priority: -5\n"
        )
        corpus = _load_with_sections(tier4_records=records)
        self.assertEqual(len(corpus.tier4_lots), 0)
        self.assertTrue(any("'market_search_priority'" in e
                            for e in corpus.report.errors))


# ──────────────────────────────────────────────────────────────────────
# 5. Tier 5 organization HQ lots
# ──────────────────────────────────────────────────────────────────────


class TestTier5Lots(unittest.TestCase):
    """Validate Tier5Lot parsing including the recommended_faction
    bias field and the max_homes default."""

    def test_full_tier5_record(self):
        records = (
            "- id: coco_town_civic_block\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: coco_town_civic_block\n"
            "  max_homes: 1\n"
            "  allowed_types: [outpost, chapter_house, fortress]\n"
            "  recommended_faction: republic\n"
            "  description_theme: republic_civic\n"
        )
        corpus = _load_with_sections(tier5_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier5_lots), 1)
        lot = corpus.tier5_lots[0]
        self.assertEqual(lot.id, "coco_town_civic_block")
        self.assertEqual(lot.recommended_faction, "republic")
        self.assertEqual(lot.allowed_types,
                         ["outpost", "chapter_house", "fortress"])

    def test_max_homes_defaults_to_one_when_absent(self):
        """Per §9: T5 default is 1 HQ per host room."""
        records = (
            "- id: bhg_chapter_house\n"
            "  planet: coruscant\n"
            "  zone: southern_underground\n"
            "  host_room: bhg_chapter_house\n"
            "  allowed_types: [chapter_house, fortress]\n"
        )
        corpus = _load_with_sections(tier5_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier5_lots[0].max_homes, 1)

    def test_recommended_faction_optional(self):
        """An indep org slot has no recommended_faction."""
        records = (
            "- id: indep_outpost\n"
            "  planet: tatooine\n"
            "  zone: outskirts\n"
            "  host_room: outskirts_compound\n"
            "  allowed_types: [outpost, chapter_house]\n"
        )
        corpus = _load_with_sections(tier5_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertIsNone(corpus.tier5_lots[0].recommended_faction)

    def test_max_homes_explicitly_greater_than_one_allowed(self):
        """Shared compounds with multiple HQs (rare but supported)."""
        records = (
            "- id: shared_compound\n"
            "  planet: nar_shaddaa\n"
            "  zone: nar_shaddaa_upper\n"
            "  host_room: corporate_tower\n"
            "  max_homes: 3\n"
            "  allowed_types: [chapter_house, fortress]\n"
        )
        corpus = _load_with_sections(tier5_records=records)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.tier5_lots[0].max_homes, 3)

    def test_empty_recommended_faction_string_invalid(self):
        """If present, must be non-empty."""
        records = (
            "- id: bad_lot\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: room_a\n"
            "  recommended_faction: ''\n"
        )
        corpus = _load_with_sections(tier5_records=records)
        self.assertEqual(len(corpus.tier5_lots), 0)
        self.assertTrue(any("'recommended_faction'" in e
                            for e in corpus.report.errors))


# ──────────────────────────────────────────────────────────────────────
# 6. Cross-section invariants
# ──────────────────────────────────────────────────────────────────────


class TestCrossSectionInvariants(unittest.TestCase):
    """Tests that span multiple lot sections."""

    def test_id_collisions_across_tiers_are_allowed(self):
        """A T1 host and a T3 lot can share an id — they're different
        namespaces. The schema deliberately doesn't enforce cross-tier
        uniqueness because a building's `id` field is local to its tier
        section."""
        t1 = (
            "- id: shared_id\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: building_a\n"
            "  npc: clerk\n"
            "  slots: 5\n"
            "  weekly_rent_base: 50\n"
        )
        t3 = (
            "- id: shared_id\n"
            "  planet: coruscant\n"
            "  zone: coco_town\n"
            "  host_room: building_b\n"
            "  max_homes: 3\n"
        )
        corpus = _load_with_sections(tier1_records=t1, tier3_records=t3)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier1_rentals), 1)
        self.assertEqual(len(corpus.tier3_lots), 1)
        self.assertEqual(corpus.tier1_rentals[0].id, "shared_id")
        self.assertEqual(corpus.tier3_lots[0].id, "shared_id")

    def test_all_four_sections_can_coexist(self):
        """Sanity check: T1, T3, T4, T5 all populated in one YAML."""
        t1 = ("- id: t1a\n  planet: coruscant\n  zone: coco_town\n"
              "  host_room: r1\n  npc: clerk1\n  slots: 5\n"
              "  weekly_rent_base: 50\n")
        t3 = ("- id: t3a\n  planet: coruscant\n  zone: coco_town\n"
              "  host_room: r2\n  max_homes: 4\n")
        t4 = ("- id: t4a\n  planet: coruscant\n  zone: coco_town\n"
              "  host_room: r3\n  max_homes: 4\n")
        t5 = ("- id: t5a\n  planet: coruscant\n  zone: coco_town\n"
              "  host_room: r4\n")
        corpus = _load_with_sections(tier1_records=t1, tier3_records=t3,
                                      tier4_records=t4, tier5_records=t5)
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(len(corpus.tier1_rentals), 1)
        self.assertEqual(len(corpus.tier3_lots), 1)
        self.assertEqual(len(corpus.tier4_lots), 1)
        self.assertEqual(len(corpus.tier5_lots), 1)

    def test_section_must_be_a_list_not_a_dict(self):
        """If an author writes `tier1_rentals: {...}` instead of a list,
        we record one structural error and the section is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            yaml_text = (
                "schema_version: 1\n"
                "era: test_era\n"
                "tier2_faction_quarters: {}\n"
                "tier1_rentals:\n"
                "  some_id:\n"
                "    planet: coruscant\n"
            )
            era_dir = _build_isolated_era(tmpdir, "bad_test", yaml_text)
            corpus = _load_corpus(era_dir)

        self.assertEqual(corpus.tier1_rentals, [])
        self.assertTrue(any("'tier1_rentals' must be a list" in e
                            for e in corpus.report.errors))


# ──────────────────────────────────────────────────────────────────────
# 7. Source-level guards: ensure F.5a.2 anchors are present in the loader
# ──────────────────────────────────────────────────────────────────────


class TestSourceLevelGuards(unittest.TestCase):
    """Inspect the engine source to confirm F.5a.2 additions are present.
    These guard against accidental deletion in future refactors and
    against confused test runs (passing tests with absent code is the
    'phantom-delivered' failure mode the project explicitly guards
    against)."""

    @classmethod
    def setUpClass(cls):
        wl_path = (Path(PROJECT_ROOT) / "engine" / "world_loader.py")
        cls.source = wl_path.read_text(encoding="utf-8")

    def test_dataclasses_present(self):
        for name in ("Tier1RentalHost", "Tier3Lot", "Tier4Lot", "Tier5Lot"):
            self.assertIn(f"class {name}", self.source,
                          f"dataclass {name} missing from world_loader.py")

    def test_corpus_has_new_fields(self):
        """HousingLotsCorpus must declare the four new lot list fields."""
        self.assertIn("tier1_rentals: list = field(default_factory=list)",
                      self.source)
        self.assertIn("tier3_lots: list = field(default_factory=list)",
                      self.source)
        self.assertIn("tier4_lots: list = field(default_factory=list)",
                      self.source)
        self.assertIn("tier5_lots: list = field(default_factory=list)",
                      self.source)

    def test_parser_helpers_defined(self):
        for name in ("_parse_tier1_rentals", "_parse_tier3_lots",
                     "_parse_tier4_lots", "_parse_tier5_lots"):
            self.assertIn(f"def {name}", self.source,
                          f"parser helper {name} missing")

    def test_f5a2_anchor_comment_present(self):
        """A locator string future maintainers can grep for."""
        self.assertIn("F.5a.2", self.source,
                      "F.5a.2 anchor comment missing from world_loader.py")


if __name__ == "__main__":
    unittest.main()
