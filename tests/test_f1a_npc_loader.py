# -*- coding: utf-8 -*-
"""F.1a — Era-aware NPC loader regression tests.

These tests guard the contract between build_mos_eisley.py (consumer) and
engine/npc_loader.py + the data/worlds/<era>/era.yaml content_refs (producer).

Pre-F.1a, build_mos_eisley.py held HIREABLE_CREW (4 entries) and PLANET_NPCS
(43 entries) as Python literals. F.1a extracted them to:
    data/worlds/gcw/npcs_planet.yaml      (43 entries)
    data/worlds/gcw/npcs_hireable.yaml    (4 entries)
And combined with the era-agnostic data/npcs_gg7.yaml (55 entries), the
era loader returns 98 planet + 4 hireable = 102 NPCs total — matching
the F.0 Pass B build smoke output exactly.

Tests cover:
  * Total-count parity (98 planet + 4 hireable, by file decomposition).
  * Trainer flag preservation (4 NPCs: Old Prospector, Vek Nurren,
    Renna Dox, Venn Kator) — these were silently dropped before the loader
    patch in F.1a; the regression guard prevents recurrence.
  * Space-skills (`skills` key in ai_config) preservation for the 4
    hireable crew NPCs — also silently dropped before F.1a.
  * Replacement-suppression mechanism (used by CW era's npcs_cw_replacements.yaml).
"""
import os
import pytest

from engine.npc_loader import load_era_npcs, load_npcs_from_yaml
from engine.world_loader import load_world_dry_run


@pytest.fixture(scope="module")
def gcw_room_map():
    bundle = load_world_dry_run("gcw")
    return {r.name: r.id for r in bundle.rooms.values()}


@pytest.fixture(scope="module")
def gcw_npcs(gcw_room_map):
    """Returns (planet_npcs, hireable_npcs) for GCW era."""
    era_dir = os.path.join(os.path.dirname(__file__), "..", "data", "worlds", "gcw")
    return load_era_npcs(era_dir, gcw_room_map)


# ──────────────────────────────────────────────────────────────────────────
# Count parity
# ──────────────────────────────────────────────────────────────────────────


class TestCountParity:
    def test_planet_count_matches_baseline(self, gcw_npcs):
        planet, _ = gcw_npcs
        # 55 from npcs_gg7.yaml (era-agnostic GG7) + 43 from npcs_planet.yaml
        assert len(planet) == 98

    def test_hireable_count_matches_baseline(self, gcw_npcs):
        _, hireable = gcw_npcs
        # 4 from npcs_hireable.yaml: Kael Voss, Grek Duul, Mira Tann, Tik-So
        assert len(hireable) == 4

    def test_total_npc_count(self, gcw_npcs):
        planet, hireable = gcw_npcs
        # F.0 Pass B build smoke reported 102 NPCs; F.1a must preserve.
        assert len(planet) + len(hireable) == 102


# ──────────────────────────────────────────────────────────────────────────
# Hireable crew (extraction round-trip)
# ──────────────────────────────────────────────────────────────────────────


class TestHireableCrew:
    EXPECTED_NAMES = {"Kael Voss", "Grek Duul", "Mira Tann", "Tik-So"}

    def test_hireable_names(self, gcw_npcs):
        _, hireable = gcw_npcs
        names = {tup[0] for tup in hireable}
        assert names == self.EXPECTED_NAMES

    def test_hireable_kael_voss_is_pilot(self, gcw_npcs):
        _, hireable = gcw_npcs
        kael = next(tup for tup in hireable if tup[0] == "Kael Voss")
        _, _, species, _, sheet, _ = kael
        assert species == "Human"
        # Kael's signature stat is 5D+1 starfighter_piloting per the literal
        assert sheet["skills"]["starfighter_piloting"] == "5D+1"

    def test_hireable_space_skills_preserved(self, gcw_npcs):
        """Regression guard — pre-F.1a, npc_loader._build_ai_config dropped
        the `skills` key from ai_config (it's how _ai() in build_mos_eisley.py
        stores space_skills). All four hireable crew depend on this."""
        _, hireable = gcw_npcs
        for name, _, _, _, _, ai_cfg in hireable:
            assert "skills" in ai_cfg, (
                f"{name}: ai_config.skills (space-skills) was stripped — "
                f"npc_loader regression"
            )
            assert isinstance(ai_cfg["skills"], dict)
            assert len(ai_cfg["skills"]) > 0


# ──────────────────────────────────────────────────────────────────────────
# Trainer flag preservation
# ──────────────────────────────────────────────────────────────────────────


class TestTrainerFlag:
    """4 trainer NPCs in the GCW corpus: Old Prospector (Jundland Wastes
    survival), Vek Nurren (Wastes survival gear), Renna Dox (Nar Shaddaa
    starship repair), Venn Kator (Coronet starship repair).

    Pre-F.1a, npc_loader._build_ai_config silently dropped the `trainer`
    and `train_skills` fields. Without them, +train UX has no skill data
    to teach. This test asserts they round-trip.
    """

    EXPECTED_TRAINERS = {
        "Old Prospector": ["survival", "search"],
        "Vek Nurren": ["survival", "first_aid", "armor_repair", "security"],
        "Renna Dox": ["starship_repair", "space_transports_repair"],
        "Venn Kator": ["starship_repair", "space_transports_repair"],
    }

    def test_all_trainers_present_and_flagged(self, gcw_npcs):
        planet, _ = gcw_npcs
        by_name = {tup[0]: tup for tup in planet}
        for name, expected_skills in self.EXPECTED_TRAINERS.items():
            assert name in by_name, f"Trainer {name} missing from planet NPCs"
            _, _, _, _, _, ai_cfg = by_name[name]
            assert ai_cfg.get("trainer") is True, (
                f"{name}: trainer flag not preserved by npc_loader"
            )
            assert ai_cfg.get("train_skills") == expected_skills, (
                f"{name}: train_skills mismatch — got "
                f"{ai_cfg.get('train_skills')!r}, expected {expected_skills!r}"
            )


# ──────────────────────────────────────────────────────────────────────────
# Replacement-suppression mechanism
# ──────────────────────────────────────────────────────────────────────────


class TestReplacementSuppression:
    """The era loader implements a `replaces:` protocol so a CW NPC file
    can suppress its GG7 antecedent and substitute its own. This is the
    mechanism behind data/worlds/clone_wars/npcs_cw_replacements.yaml.

    These tests use load_npcs_from_yaml directly (not load_era_npcs) so
    they don't depend on era.yaml structure — they verify the primitive.
    """

    def test_no_suppression_no_op(self, gcw_room_map, tmp_path):
        # Without suppress_names, every entry loads.
        yaml_text = """
schema_version: 1
npcs:
  - name: "Test NPC A"
    room: "Mos Eisley Street - Market District"
    species: "Human"
    description: "Test."
    char_sheet:
      attributes:
        dexterity: "2D"
        knowledge: "2D"
        mechanical: "2D"
        perception: "2D"
        strength: "2D"
        technical: "2D"
    ai_config: {}
"""
        p = tmp_path / "test_a.yaml"
        p.write_text(yaml_text)
        loaded = load_npcs_from_yaml(str(p), gcw_room_map)
        assert len(loaded) == 1

    def test_suppression_drops_named_entries(self, gcw_room_map, tmp_path):
        yaml_text = """
schema_version: 1
npcs:
  - name: "Keeper"
    room: "Mos Eisley Street - Market District"
    species: "Human"
    description: "Stays."
    char_sheet:
      attributes:
        dexterity: "2D"
        knowledge: "2D"
        mechanical: "2D"
        perception: "2D"
        strength: "2D"
        technical: "2D"
    ai_config: {}
  - name: "Doomed"
    room: "Mos Eisley Street - Market District"
    species: "Human"
    description: "Removed by suppression."
    char_sheet:
      attributes:
        dexterity: "2D"
        knowledge: "2D"
        mechanical: "2D"
        perception: "2D"
        strength: "2D"
        technical: "2D"
    ai_config: {}
"""
        p = tmp_path / "test_b.yaml"
        p.write_text(yaml_text)
        loaded = load_npcs_from_yaml(str(p), gcw_room_map, suppress_names={"Doomed"})
        assert len(loaded) == 1
        assert loaded[0][0] == "Keeper"

    def test_replacement_entry_not_self_suppressed(self, gcw_room_map, tmp_path):
        """An entry with `replaces: X` is itself NOT skipped — it's a
        replacement that takes X's slot. Suppression only applies to base
        entries (no `replaces:` field) whose name appears in the suppress set."""
        yaml_text = """
schema_version: 1
npcs:
  - replaces: "Imperial Stormtrooper"
    name: "Clone Trooper CT-7842"
    room: "Mos Eisley Street - Market District"
    species: "Human"
    description: "CW replacement for the GCW stormtrooper."
    char_sheet:
      attributes:
        dexterity: "3D"
        knowledge: "2D"
        mechanical: "2D"
        perception: "2D"
        strength: "3D"
        technical: "2D"
    ai_config: {}
"""
        p = tmp_path / "test_c.yaml"
        p.write_text(yaml_text)
        loaded = load_npcs_from_yaml(
            str(p), gcw_room_map,
            suppress_names={"Clone Trooper CT-7842"},  # accidental over-suppression
        )
        # The replacement entry has `replaces:` set, so the suppression
        # check skips it. The clone trooper still loads.
        assert len(loaded) == 1
        assert loaded[0][0] == "Clone Trooper CT-7842"


# ──────────────────────────────────────────────────────────────────────────
# Era-loader paths
# ──────────────────────────────────────────────────────────────────────────


class TestEraLoaderPaths:
    def test_gcw_loader_resolves_dotdot_path(self, gcw_room_map):
        """The GCW era.yaml uses `../../npcs_gg7.yaml` to reference the
        era-agnostic GG7 base. Verify the loader resolves it correctly
        rather than treating it as a literal subpath."""
        era_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "worlds", "gcw"
        )
        planet, _ = load_era_npcs(era_dir, gcw_room_map)
        # Wuher is in npcs_gg7.yaml; if the path didn't resolve, he'd be missing.
        names = {tup[0] for tup in planet}
        assert "Wuher" in names
        # Jawa Scrap Boss is in npcs_planet.yaml (the era-relative file).
        assert "Jawa Scrap Boss" in names

    def test_missing_era_yaml_returns_empty(self, tmp_path, gcw_room_map):
        """No era.yaml → no NPCs (no crash)."""
        planet, hireable = load_era_npcs(str(tmp_path), gcw_room_map)
        assert planet == []
        assert hireable == []
