# -*- coding: utf-8 -*-
"""
tests/test_grind_redirect_round2_jundland.py

GRIND-REDIRECT round 2 content validation (2026-06-24).

Three new creatures (canyon_womp_rat, rock_wart, scurrier) and the new
Tatooine Jundland Wastes wilderness region (tatooine_jundland.yaml).

Contracts enforced:

  1. CREATURES: the three new ids parse correctly in npcs_creatures.yaml;
     all are non-intelligent and carry KNO/MEC/TEC = 0D; all have
     natural_attack, description, and source.

  2. ENCOUNTER RESOLUTION (anti-phantom): every new pool entry whose
     payload.npc_template is one of the new ids resolves via the SAME
     runtime resolver (engine.creature_library.get_creature) the spawn
     bridge uses. A miss here = narrative fires, nothing spawns.

  3. REGION LOAD: tatooine_jundland.yaml loads without errors; the region
     appears in load_era_wilderness_regions results.

  4. ENCOUNTER PRESENCE: the expected new encounter ids exist in the
     Jundland pool.

  5. ERA-CLEANNESS (B3): new creature descriptions + encounter narratives
     contain no banned GCW-era strings.

  6. SPOILS WIRING: creatures with a harvest.good block are accepted by
     creature_spoils.creature_has_spoils; resource types in the allowed set.

  7. NO-ORPHAN: each new creature is referenced by at least one live
     encounter in the Jundland region.

  8. HIGH-DAMAGE GATING: hostile encounters with creatures of STR >= 2D+2 or
     pack_count hi >= 5 MUST carry min_band >= 2 (per task STEP 2 constraint).

  9. ALL TEMPLATES RESOLVE: every hostile/non_hostile encounter in the
     Jundland pool with an npc_template resolves in the creature library
     (anti-phantom coverage, complementing the global resolution guard).
"""

import os
import sys
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import yaml  # noqa: E402

CREATURES_FILE = os.path.join(PROJECT_ROOT, "data", "npcs_creatures.yaml")
WILD_DIR = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "wilderness"
)
JUNDLAND = os.path.join(WILD_DIR, "tatooine_jundland.yaml")
ERA_DIR = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")

NEW_CREATURE_IDS = {"canyon_womp_rat", "rock_wart", "scurrier"}

# Encounter ids that must appear in the Jundland pool.
EXPECTED_ENCOUNTER_IDS = {
    "womp_rat_pack",
    "rock_wart_ambush",
    "scurrier_colony",
    "tusken_jundland_patrol",
    "tusken_jundland_war_party",
    "jundland_dewback_herd",
    "wrix_jundland_pack",
    "jundland_cave_bats",
    "jundland_keejin_drop",
    "jawa_salvage_wagon",
    "krayt_skeleton_site",
    "ruined_moisture_farm",
    "canyon_thermal_surge",
}

B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "rebel alliance", "tie fighter", "tie pilot",
)

# Encounters whose creature-spawn threat justifies a min_band gate.
# key = encounter id; value = minimum acceptable min_band.
HIGH_THREAT_ENCOUNTERS = {
    "tusken_jundland_war_party": 3,   # 4-6 Tusken warriors
    "wrix_jundland_pack": 3,          # 3-5 wrix (brawling 5D)
    "jundland_cave_bats": 3,          # 6-12 shredder bats (dive STR+2D+2)
    "rock_wart_ambush": 2,            # paralytic venom + egg risk
}


def _load_creatures():
    with open(CREATURES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {n["id"]: n for n in (data.get("npcs") or [])}


def _load_region_raw(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_region_parsed(path):
    from engine.wilderness_loader import load_wilderness_region
    return load_wilderness_region(path)


class TestNewCreaturesSchema(unittest.TestCase):
    """Contract 1: the three new creatures parse correctly."""

    def setUp(self):
        self.lib = _load_creatures()

    def test_all_new_ids_present(self):
        missing = NEW_CREATURE_IDS - set(self.lib)
        self.assertEqual(
            missing, set(),
            f"new creature ids missing from library: {missing}",
        )

    def test_non_intelligent_have_zero_kmt(self):
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None or c.get("intelligent"):
                continue
            attrs = (c.get("char_sheet") or {}).get("attributes") or {}
            for a in ("knowledge", "mechanical", "technical"):
                self.assertEqual(
                    attrs.get(a), "0D",
                    f"{cid}.{a} must be '0D' for a non-intelligent creature",
                )

    def test_have_natural_attack_description_source(self):
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            self.assertIn("natural_attack", c, f"{cid} missing natural_attack")
            self.assertTrue(
                (c.get("natural_attack") or {}).get("damage"),
                f"{cid}.natural_attack.damage is empty",
            )
            self.assertTrue(c.get("description"), f"{cid} missing description")
            self.assertTrue(c.get("source"), f"{cid} missing source")

    def test_char_sheet_required_keys(self):
        required_attrs = {
            "dexterity", "perception", "strength",
            "knowledge", "mechanical", "technical",
        }
        for cid in NEW_CREATURE_IDS:
            c = self.lib.get(cid)
            if c is None:
                continue
            attrs = ((c.get("char_sheet") or {}).get("attributes") or {})
            missing = required_attrs - set(attrs)
            self.assertEqual(
                missing, set(), f"{cid} missing attribute keys: {missing}",
            )


class TestNewCreaturesRuntimeResolve(unittest.TestCase):
    """Contract 2: runtime resolver finds all new creatures."""

    def test_get_creature_resolves_all_new_ids(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)
        missing = [
            cid for cid in NEW_CREATURE_IDS
            if CL.get_creature(cid) is None
        ]
        self.assertEqual(
            missing, [],
            f"creature_library.get_creature returned None for: {missing}",
        )

    def test_natural_attack_resolves_to_usable_damage(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)
        broken = []
        for cid in NEW_CREATURE_IDS:
            c = CL.get_creature(cid)
            if c is None:
                continue
            atk = CL.resolve_natural_attack(c)
            if not str(atk.get("damage") or "").strip():
                broken.append(cid)
        self.assertEqual(
            broken, [],
            f"creature(s) resolve but produce no natural-attack damage: {broken}",
        )


class TestJundlandRegionLoad(unittest.TestCase):
    """Contract 3: tatooine_jundland.yaml loads without errors."""

    def test_region_file_exists(self):
        self.assertTrue(
            os.path.isfile(JUNDLAND),
            f"tatooine_jundland.yaml missing at {JUNDLAND}",
        )

    def test_region_yaml_parses(self):
        try:
            raw = _load_region_raw(JUNDLAND)
        except yaml.YAMLError as e:
            self.fail(f"tatooine_jundland.yaml YAML parse error: {e}")
        self.assertIsInstance(raw, dict)

    def test_region_loads_via_loader(self):
        rep = _load_region_parsed(JUNDLAND)
        self.assertTrue(
            rep.ok,
            f"tatooine_jundland.yaml loader errors: {rep.errors[:5]}",
        )
        self.assertIsNotNone(rep.region)

    def test_region_slug(self):
        rep = _load_region_parsed(JUNDLAND)
        if rep.ok and rep.region:
            self.assertEqual(
                rep.region.slug, "tatooine_jundland",
            )

    def test_region_in_era_wilderness_list(self):
        from engine.wilderness_loader import load_era_wilderness_regions
        reports = load_era_wilderness_regions(ERA_DIR)
        slugs = [
            r.region.slug
            for r in reports
            if getattr(r, "ok", False) and getattr(r, "region", None)
        ]
        self.assertIn(
            "tatooine_jundland", slugs,
            f"tatooine_jundland not in loaded era regions; found: {slugs}",
        )


class TestJundlandEncounterPresence(unittest.TestCase):
    """Contract 4: expected encounter ids exist in the Jundland pool."""

    def _pool_ids(self):
        rep = _load_region_parsed(JUNDLAND)
        self.assertTrue(rep.ok, f"Jundland failed to load: {rep.errors[:3]}")
        return {e.id for e in rep.region.encounter_pool.entries}

    def test_expected_encounters_present(self):
        ids = self._pool_ids()
        missing = EXPECTED_ENCOUNTER_IDS - ids
        self.assertEqual(
            missing, set(),
            f"Jundland pool missing expected encounter ids: {missing}",
        )

    def test_pool_is_non_empty(self):
        ids = self._pool_ids()
        self.assertGreater(len(ids), 0, "Jundland encounter pool is empty")


class TestEraCleanness(unittest.TestCase):
    """Contract 5: new content is B3-clean."""

    def _player_strings_from_creature(self, c):
        strings = [
            c.get("description") or "",
            (c.get("natural_attack") or {}).get("name") or "",
        ]
        for s in c.get("special") or []:
            strings.append(str(s))
        return strings

    def test_creature_descriptions_era_clean(self):
        lib = _load_creatures()
        violations = []
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None:
                continue
            for s in self._player_strings_from_creature(c):
                for banned in B3_BANNED:
                    if banned in s.lower():
                        violations.append(f"{cid}: '{banned}' in '{s[:60]}'")
        self.assertEqual(
            violations, [],
            "B3 era violations in new creatures:\n  " + "\n  ".join(violations),
        )

    def test_encounter_narratives_era_clean(self):
        raw = _load_region_raw(JUNDLAND)
        pool = (raw.get("encounters") or {}).get("pool") or []
        violations = []
        for e in pool:
            if not isinstance(e, dict):
                continue
            narrative = str(e.get("narrative") or "")
            for banned in B3_BANNED:
                if banned in narrative.lower():
                    violations.append(
                        f"{e.get('id')}: '{banned}' in narrative"
                    )
        self.assertEqual(
            violations, [],
            "B3 era violations in Jundland encounter narratives:\n  " +
            "\n  ".join(violations),
        )

    def test_landmark_descriptions_era_clean(self):
        raw = _load_region_raw(JUNDLAND)
        landmarks = raw.get("landmarks") or []
        violations = []
        for lm in landmarks:
            desc = str(lm.get("description") or "")
            short = str(lm.get("short_desc") or "")
            for text, label in ((desc, "description"), (short, "short_desc")):
                for banned in B3_BANNED:
                    if banned in text.lower():
                        violations.append(
                            f"{lm.get('id')}.{label}: '{banned}'"
                        )
        self.assertEqual(
            violations, [],
            "B3 era violations in Jundland landmarks:\n  " +
            "\n  ".join(violations),
        )


class TestSpoilsWiring(unittest.TestCase):
    """Contract 6: creatures with harvest blocks are accepted by creature_spoils."""

    def test_spoils_resource_types_allowed(self):
        from engine.creature_spoils import (
            creature_has_spoils, spoils_resource_type,
            _ALLOWED_RESOURCE_TYPES,
        )
        lib = _load_creatures()
        bad = []
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None or not creature_has_spoils(c):
                continue
            rtype = spoils_resource_type(c)
            if rtype not in _ALLOWED_RESOURCE_TYPES:
                bad.append(f"{cid}: resource type {rtype!r} not in allowed set")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_spoils_has_good_string(self):
        from engine.creature_spoils import creature_has_spoils
        lib = _load_creatures()
        for cid in NEW_CREATURE_IDS:
            c = lib.get(cid)
            if c is None:
                continue
            h = c.get("harvest")
            if h is not None:
                self.assertTrue(
                    creature_has_spoils(c),
                    f"{cid} has a harvest block but creature_has_spoils returned False",
                )
                self.assertTrue(
                    str(h.get("good") or "").strip(),
                    f"{cid}.harvest.good is empty",
                )


class TestNoOrphanCreatures(unittest.TestCase):
    """Contract 7: each new creature is referenced by at least one Jundland encounter."""

    def test_no_orphan_new_creatures(self):
        rep = _load_region_parsed(JUNDLAND)
        self.assertTrue(rep.ok)
        referenced = {
            (e.payload or {}).get("npc_template")
            for e in rep.region.encounter_pool.entries
            if (e.payload or {}).get("npc_template")
        }
        orphans = NEW_CREATURE_IDS - referenced
        self.assertEqual(
            orphans, set(),
            f"New Jundland creatures with no encounter reference: {orphans}",
        )


class TestHighDamageGating(unittest.TestCase):
    """Contract 8: high-threat encounters carry the required min_band gate."""

    def test_high_threat_encounters_gated(self):
        raw = _load_region_raw(JUNDLAND)
        pool = (raw.get("encounters") or {}).get("pool") or []
        by_id = {e["id"]: e for e in pool if isinstance(e, dict) and e.get("id")}
        violations = []
        for enc_id, required_min_band in HIGH_THREAT_ENCOUNTERS.items():
            e = by_id.get(enc_id)
            if e is None:
                # Missing encounter is caught by Contract 4 — don't double-report
                continue
            actual = int(e.get("min_band", 1))
            if actual < required_min_band:
                violations.append(
                    f"{enc_id}: min_band={actual} < required {required_min_band}"
                )
        self.assertEqual(
            violations, [],
            "High-threat encounters missing min_band gate:\n  " +
            "\n  ".join(violations),
        )


class TestAllJundlandTemplatesResolve(unittest.TestCase):
    """Contract 9: every spawning encounter in the Jundland pool resolves."""

    def test_every_spawning_template_resolves(self):
        from engine import creature_library as CL
        CL.load_creature_library(force_reload=True)

        rep = _load_region_parsed(JUNDLAND)
        self.assertTrue(rep.ok)

        dangling = []
        checked = 0
        for e in rep.region.encounter_pool.entries:
            if e.type not in ("hostile", "non_hostile"):
                continue
            tmpl = (e.payload or {}).get("npc_template")
            if not tmpl:
                continue
            checked += 1
            if CL.get_creature(tmpl) is None:
                dangling.append(f"{e.id} -> {tmpl!r}")

        self.assertGreater(
            checked, 0,
            "no hostile/non_hostile encounter with npc_template found in "
            "Jundland pool — template-resolution guard is vacuous",
        )
        self.assertEqual(
            dangling, [],
            "dangling npc_template(s) in Jundland pool — encounter fires "
            "narrative but spawn_encounter_creatures returns []:\n  " +
            "\n  ".join(dangling),
        )


if __name__ == "__main__":
    unittest.main()
