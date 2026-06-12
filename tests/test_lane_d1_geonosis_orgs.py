# -*- coding: utf-8 -*-
"""
tests/test_lane_d1_geonosis_orgs.py — Lane D1 (Geonosis foundation) guards.

Lane D drop 1 lays the foundation the faction-tension wiring (D2) needs:
the Geonosian hive orgs that the contest engine will pit against each
other. `engine/contest.py` declares contests between **org codes**
(`declare_region_contest(db, slug, defender, challenger, ...)`), and
before this drop no Geonosis/Kamino org existed in organizations.yaml —
so faction-wiring could not be drop 1. This drop authors:

  * organizations.yaml :: stalgasin (dominant hive, CIS-leaning)
  * organizations.yaml :: gehenbar  (rival hive, Republic-backable)

Both are NPC-only, Director-narrated factions modelled on the existing
sith / separatist_council pattern, and both carry a `violence_index`
(the live `faction info` posture consumer reads it via
`format_org_posture_line`) but **no `scale`** — matching the E1 rule
(scale only on criminal orgs; state/military factions get a tone, not a
criminal tier). The contest-aggression consumer for violence_index is
explicitly D2, not here.

What these guards lock:
  1. Both hive entries exist with the NPC-faction shape.
  2. violence_index present (88 / 84), scale absent.
  3. The live helpers resolve them (descriptor bands, posture line).
  4. The joinable set is untouched (hives are NOT in valid_factions /
     era.yaml factions — non-joinability is what keeps them out of
     chargen; valid_factions is byte-pinned at 6 by
     test_f6a3_director_config_loader).
  5. Both hives registered in npc_only_factions in BOTH era.yaml and
     director_config.yaml (the established declaration for Director NPC
     factions).
  6. B3 era-cleanness of the production description strings.
  7. Q1 canon policy: no canonical figures named; the original NPCs
     (Typtus, Acklay Chopper) ARE named (substance check, and proof the
     archduke is framed institutionally rather than as Poggle).
  8. geonosis.yaml description enriched with the caste/hive substance.

Sandbox-runnable: imports only `yaml` + the pure org helpers (no
aiosqlite/aiohttp). The full suite is Brian's Windows ground truth.
"""
import json
import os
import unittest

import yaml

from engine.organizations import (
    get_org_scale,
    get_org_violence_index,
    violence_descriptor,
    format_org_posture_line,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
ORGS_YAML = os.path.join(CW, "organizations.yaml")
GEONOSIS_YAML = os.path.join(CW, "planets", "geonosis.yaml")
DIRECTOR_CONFIG_YAML = os.path.join(CW, "director_config.yaml")
ERA_YAML = os.path.join(CW, "era.yaml")

HIVE_CODES = ("stalgasin", "gehenbar")
EXPECTED_VI = {"stalgasin": 88, "gehenbar": 84}
EXPECTED_DESCRIPTOR = {"stalgasin": "range war", "gehenbar": "bloody"}

# B3: production strings must not carry GCW/Imperial-era vocabulary.
# (Comments and era-mapping keys are exempt; loading via yaml.safe_load
# drops comments, so we only ever scan parsed string VALUES here.)
B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "x-wing", "tie fighter", "tie pilot", "rebel alliance",
)

# Q1: a focused canonical blocklist relevant to Geonosis/Kamino content.
# Mirrors the spirit of tests/test_q1_2_extended_sweep.CANONICAL_FORBIDDEN
# for the figures these descriptions could plausibly have named.
Q1_FORBIDDEN = (
    "Poggle", "Sun Fac", "Lama Su", "Taun We", "Nala Se", "Ko Sai",
    "Dooku", "Sidious", "Tyranus", "Grievous", "Sifo-Dyas",
    "Jango", "Obi-Wan", "Kenobi",
)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_faction(orgs, code):
    for f in orgs.get("factions", []) or []:
        if isinstance(f, dict) and f.get("code") == code:
            return f
    return None


def _org_row(faction):
    """Reproduce the loader's view: properties -> JSON string -> a row
    whose `properties` key is that string (engine/organizations.py
    load path serializes faction['properties'] with json.dumps)."""
    return {"properties": json.dumps(faction.get("properties", {}))}


def _desc(faction):
    return ((faction.get("properties") or {}).get("description") or "")


class TestHiveEntriesExist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orgs = _load(ORGS_YAML)

    def test_organizations_yaml_parses(self):
        self.assertIsInstance(self.orgs, dict)
        self.assertIn("factions", self.orgs)

    def test_both_hives_present(self):
        for code in HIVE_CODES:
            self.assertIsNotNone(
                _find_faction(self.orgs, code),
                f"organizations.yaml missing the '{code}' hive org. "
                f"Lane D2's contest wiring declares contests between "
                f"org codes and cannot reference a hive that does not "
                f"exist as an org.",
            )

    def test_hives_are_npc_only_director_managed(self):
        for code in HIVE_CODES:
            f = _find_faction(self.orgs, code)
            self.assertTrue(
                f.get("npc_only") is True,
                f"{code} must be npc_only: true (Director NPC faction, "
                f"not player-joinable).",
            )
            self.assertTrue(
                f.get("director_managed") is True,
                f"{code} must be director_managed: true.",
            )

    def test_hives_have_a_name_and_a_rank(self):
        for code in HIVE_CODES:
            f = _find_faction(self.orgs, code)
            self.assertTrue(
                (f.get("name") or "").strip(),
                f"{code} needs a display name (faction info header).",
            )
            # At least one rank so `faction info` renders a non-empty
            # rank table under its header.
            self.assertTrue(
                f.get("ranks"),
                f"{code} needs at least one rank row.",
            )


class TestHiveViolenceFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orgs = _load(ORGS_YAML)

    def test_violence_index_values(self):
        for code in HIVE_CODES:
            f = _find_faction(self.orgs, code)
            props = f.get("properties") or {}
            self.assertEqual(
                props.get("violence_index"), EXPECTED_VI[code],
                f"{code} violence_index should be {EXPECTED_VI[code]}.",
            )

    def test_no_criminal_scale(self):
        # The hives are political/military, not criminal orgs. The E1
        # rule: `scale` only on criminal orgs. A `scale` here would be a
        # modelling error and would make `faction info` print a bogus
        # criminal tier.
        for code in HIVE_CODES:
            f = _find_faction(self.orgs, code)
            props = f.get("properties") or {}
            self.assertNotIn(
                "scale", props,
                f"{code} must NOT carry a criminal `scale` (E1 rule: "
                f"scale only on criminal orgs).",
            )

    def test_live_helpers_resolve_hives(self):
        # The actual runtime path: get_org_violence_index / get_org_scale
        # / violence_descriptor / format_org_posture_line over the
        # loader-shaped row. This is the live `faction info` consumer.
        for code in HIVE_CODES:
            row = _org_row(_find_faction(self.orgs, code))
            self.assertEqual(get_org_violence_index(row), EXPECTED_VI[code])
            self.assertIsNone(
                get_org_scale(row),
                f"{code}: get_org_scale must be None.",
            )
            self.assertEqual(
                violence_descriptor(get_org_violence_index(row)),
                EXPECTED_DESCRIPTOR[code],
                f"{code} posture descriptor mismatch.",
            )
            posture = format_org_posture_line(row)
            self.assertIsNotNone(posture)
            self.assertIn("Posture:", posture)
            self.assertIn(EXPECTED_DESCRIPTOR[code], posture)
            # No criminal tier should be printed.
            self.assertNotIn("Scale:", posture)


class TestJoinableSetUntouched(unittest.TestCase):
    """The hives must NOT be joinable. Non-joinability is governed by the
    joinable allowlist (era.yaml: factions / director valid_factions),
    not the per-faction npc_only flag — so the real guard is that the
    hives are absent from those lists. valid_factions is also byte-pinned
    at exactly 6 by test_f6a3_director_config_loader; the hives leaking
    into it would break that pin and silently change Director behaviour."""

    def test_hives_not_in_era_joinable_factions(self):
        era = _load(ERA_YAML)
        joinable = (era.get("policy") or {}).get("factions", [])
        for code in HIVE_CODES:
            self.assertNotIn(
                code, joinable,
                f"{code} must NOT be in era.yaml joinable factions "
                f"(it is NPC-only).",
            )

    def test_hives_not_in_director_valid_factions(self):
        cfg = _load(DIRECTOR_CONFIG_YAML)
        valid = cfg.get("valid_factions", [])
        for code in HIVE_CODES:
            self.assertNotIn(
                code, valid,
                f"{code} must NOT be in director_config valid_factions "
                f"(that set is byte-pinned at 6).",
            )

    def test_director_valid_factions_count_preserved(self):
        cfg = _load(DIRECTOR_CONFIG_YAML)
        self.assertEqual(
            len(cfg.get("valid_factions", [])), 6,
            "director_config valid_factions must stay at 6 "
            "(pinned by test_f6a3_director_config_loader).",
        )


class TestNpcOnlyRegistration(unittest.TestCase):
    """Both hives declared as Director NPC factions in both faction-set
    configs, matching how sith / separatist_council are registered."""

    def test_in_director_config_npc_only(self):
        cfg = _load(DIRECTOR_CONFIG_YAML)
        npc = cfg.get("npc_only_factions", [])
        for code in HIVE_CODES:
            self.assertIn(code, npc, f"{code} missing from "
                                     f"director_config npc_only_factions.")

    def test_in_era_npc_only(self):
        era = _load(ERA_YAML)
        npc = (era.get("policy") or {}).get("npc_only_factions", [])
        for code in HIVE_CODES:
            self.assertIn(code, npc, f"{code} missing from "
                                     f"era.yaml npc_only_factions.")


class TestHiveDescriptionsB3EraClean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orgs = _load(ORGS_YAML)

    def test_descriptions_present_and_substantial(self):
        for code in HIVE_CODES:
            d = _desc(_find_faction(self.orgs, code))
            self.assertGreater(
                len(d.strip()), 120,
                f"{code} description is too thin to be useful.",
            )

    def test_descriptions_no_imperial_era_vocabulary(self):
        for code in HIVE_CODES:
            d = _desc(_find_faction(self.orgs, code)).lower()
            for bad in B3_BANNED:
                self.assertNotIn(
                    bad, d,
                    f"{code} description carries banned era token "
                    f"{bad!r} (B3).",
                )


class TestHiveDescriptionsQ1Clean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orgs = _load(ORGS_YAML)

    def test_no_canonical_figures_named(self):
        for code in HIVE_CODES:
            d = _desc(_find_faction(self.orgs, code))
            for name in Q1_FORBIDDEN:
                self.assertNotIn(
                    name, d,
                    f"{code} description names canonical figure "
                    f"{name!r}. The ruling archduke must stay "
                    f"institutional (Q1).",
                )

    def test_original_npcs_named(self):
        # Proof the descriptions carry their authored hooks AND that the
        # archduke is framed institutionally (named NPCs are originals).
        self.assertIn(
            "Typtus", _desc(_find_faction(self.orgs, "gehenbar")),
            "gehenbar should name its patron Typtus of the 33rd Egg "
            "(an original NPC).",
        )
        self.assertIn(
            "Acklay Chopper", _desc(_find_faction(self.orgs, "stalgasin")),
            "stalgasin should name its arena handler Acklay Chopper "
            "(an original NPC).",
        )

    def test_archduke_framed_institutionally(self):
        # Stalgasin is the archduke's seat — the role must be referenced
        # without the canonical name.
        d = _desc(_find_faction(self.orgs, "stalgasin")).lower()
        self.assertIn(
            "archduke", d,
            "stalgasin should reference the ruling archduke as an "
            "institution.",
        )


class TestGeonosisDescriptionEnriched(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planet = _load(GEONOSIS_YAML)

    def test_geonosis_yaml_parses(self):
        self.assertIsInstance(self.planet, dict)
        self.assertEqual(self.planet.get("planet"), "geonosis")

    def test_description_has_caste_and_hive_substance(self):
        d = (self.planet.get("description") or "").lower()
        # Markers spanning the new framing: caste society, the spire-hive
        # structure, the foundry, and the live drone tension.
        for marker in ("queen", "aristocrat", "drone", "hive",
                       "petranaki", "foundr"):
            self.assertIn(
                marker, d,
                f"geonosis.yaml description lacks the {marker!r} framing.",
            )

    def test_description_era_clean(self):
        d = (self.planet.get("description") or "").lower()
        for bad in B3_BANNED:
            self.assertNotIn(
                bad, d,
                f"geonosis.yaml description carries banned token "
                f"{bad!r} (B3).",
            )

    def test_description_no_canonical_figures(self):
        d = self.planet.get("description") or ""
        for name in Q1_FORBIDDEN:
            self.assertNotIn(
                name, d,
                f"geonosis.yaml description names canonical figure "
                f"{name!r} (Q1).",
            )


if __name__ == "__main__":
    unittest.main()
