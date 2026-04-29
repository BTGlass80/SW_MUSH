# -*- coding: utf-8 -*-
"""
tests/test_b1c_territory_constants_era_aware.py — B.1.c tests.

Per architecture v38 §19.7 and `b1_audit_v1.md` §3, B.1.c is the
single-session, low-risk extension of `engine/territory.py` constants
to support both eras. Four sites:

  1. `_GUARD_TEMPLATES` — extended with CW guard NPC templates
     (republic / cis / jedi_order / hutt_cartel / bounty_hunters_guild).
     Existing GCW entries unchanged. `_default` still acts as
     fallback for any unknown code.

  2. `ORG_TO_AXIS` — maps org-axis codes to director-axis codes.
     Extended with CW entries:
        republic              -> imperial
        cis                   -> rebel
        jedi_order            -> imperial
        hutt_cartel           -> criminal
        bounty_hunters_guild  -> independent

  3. `flavor` (in `get_zone_influence_line`) — narrative line per
     dominant org. Extended with CW flavor strings.

  4. `org_colors` (in `get_claim_display_tag`) — ANSI tag color per
     org. Extended with CW colors that mirror
     `data/worlds/clone_wars/organizations.yaml::properties.color`.

All extensions are additive; existing GCW entries are byte-equivalent
to pre-B.1.c.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# 1. _GUARD_TEMPLATES
# ──────────────────────────────────────────────────────────────────────

class TestGuardTemplatesByteEquivalence(unittest.TestCase):
    """GCW guard templates must remain byte-identical."""

    def test_gcw_codes_present(self):
        from engine.territory import _GUARD_TEMPLATES
        for code in ("empire", "rebel", "hutt", "bh_guild", "_default"):
            self.assertIn(code, _GUARD_TEMPLATES)

    def test_empire_template_unchanged(self):
        from engine.territory import _GUARD_TEMPLATES
        t = _GUARD_TEMPLATES["empire"]
        self.assertEqual(t["name_prefix"], "Imperial Garrison Guard")
        self.assertEqual(t["species"], "Human")
        self.assertEqual(t["faction"], "Imperial")
        self.assertEqual(t["weapon"], "Blaster Rifle (5D)")

    def test_rebel_template_unchanged(self):
        from engine.territory import _GUARD_TEMPLATES
        t = _GUARD_TEMPLATES["rebel"]
        self.assertEqual(t["name_prefix"], "Alliance Sentry")
        self.assertEqual(t["faction"], "Rebel Alliance")

    def test_hutt_template_unchanged(self):
        from engine.territory import _GUARD_TEMPLATES
        t = _GUARD_TEMPLATES["hutt"]
        self.assertEqual(t["name_prefix"], "Cartel Enforcer")
        self.assertEqual(t["species"], "Gamorrean")

    def test_bh_guild_template_unchanged(self):
        from engine.territory import _GUARD_TEMPLATES
        t = _GUARD_TEMPLATES["bh_guild"]
        self.assertEqual(t["name_prefix"], "Guild Watchman")
        self.assertEqual(t["faction"], "Bounty Hunters' Guild")


class TestGuardTemplatesCWAdditions(unittest.TestCase):
    """B.1.c: CW guard templates exist and have era-appropriate shape.

    Asymmetric: these tests FAIL pre-B.1.c (those keys didn't exist),
    PASS post-B.1.c.
    """

    def test_republic_template(self):
        from engine.territory import _GUARD_TEMPLATES
        self.assertIn("republic", _GUARD_TEMPLATES)
        t = _GUARD_TEMPLATES["republic"]
        self.assertEqual(t["species"], "Clone Trooper")
        self.assertIn("clone", t["description"].lower())
        self.assertIn("DC-15", t["weapon"])

    def test_cis_template(self):
        from engine.territory import _GUARD_TEMPLATES
        self.assertIn("cis", _GUARD_TEMPLATES)
        t = _GUARD_TEMPLATES["cis"]
        # Battle droid; must have a droid-themed species
        self.assertIn("Droid", t["species"])

    def test_jedi_order_template(self):
        from engine.territory import _GUARD_TEMPLATES
        self.assertIn("jedi_order", _GUARD_TEMPLATES)
        t = _GUARD_TEMPLATES["jedi_order"]
        self.assertIn("lightsaber", t["weapon"].lower())

    def test_hutt_cartel_template(self):
        from engine.territory import _GUARD_TEMPLATES
        self.assertIn("hutt_cartel", _GUARD_TEMPLATES)
        t = _GUARD_TEMPLATES["hutt_cartel"]
        # Same archetype as GCW Hutt
        self.assertEqual(t["faction"], "Hutt Cartel")

    def test_bounty_hunters_guild_template(self):
        from engine.territory import _GUARD_TEMPLATES
        self.assertIn("bounty_hunters_guild", _GUARD_TEMPLATES)
        t = _GUARD_TEMPLATES["bounty_hunters_guild"]
        self.assertEqual(t["faction"], "Bounty Hunters' Guild")

    def test_all_cw_templates_have_required_keys(self):
        """Schema check: every CW template must have the same keys as
        the GCW templates (so consumers don't crash on missing keys)."""
        from engine.territory import _GUARD_TEMPLATES
        required = {"name_prefix", "species", "description", "dex",
                    "blaster", "dodge", "brawling", "str", "per",
                    "weapon", "faction"}
        for code in ("republic", "cis", "jedi_order",
                     "hutt_cartel", "bounty_hunters_guild"):
            t = _GUARD_TEMPLATES[code]
            missing = required - set(t.keys())
            self.assertEqual(
                missing, set(),
                f"CW template {code!r} is missing keys: {missing}"
            )


# ──────────────────────────────────────────────────────────────────────
# 2. ORG_TO_AXIS
# ──────────────────────────────────────────────────────────────────────

class TestOrgToAxisByteEquivalence(unittest.TestCase):
    """Existing GCW mappings must be unchanged."""

    def test_gcw_mappings_preserved(self):
        from engine.territory import ORG_TO_AXIS
        self.assertEqual(ORG_TO_AXIS["empire"],   "imperial")
        self.assertEqual(ORG_TO_AXIS["rebel"],    "rebel")
        self.assertEqual(ORG_TO_AXIS["hutt"],     "criminal")
        self.assertEqual(ORG_TO_AXIS["bh_guild"], "independent")


class TestOrgToAxisCWAdditions(unittest.TestCase):
    """B.1.c: CW org codes map to the correct director-axis codes."""

    def test_republic_maps_to_imperial(self):
        """Republic = lawful state authority (like the Empire was)."""
        from engine.territory import ORG_TO_AXIS
        self.assertEqual(ORG_TO_AXIS["republic"], "imperial")

    def test_cis_maps_to_rebel(self):
        """CIS = insurgent challenger (like the Rebellion was)."""
        from engine.territory import ORG_TO_AXIS
        self.assertEqual(ORG_TO_AXIS["cis"], "rebel")

    def test_jedi_order_maps_to_imperial(self):
        """Jedi serve the Republic — also lawful authority."""
        from engine.territory import ORG_TO_AXIS
        self.assertEqual(ORG_TO_AXIS["jedi_order"], "imperial")

    def test_hutt_cartel_maps_to_criminal(self):
        from engine.territory import ORG_TO_AXIS
        self.assertEqual(ORG_TO_AXIS["hutt_cartel"], "criminal")

    def test_bounty_hunters_guild_maps_to_independent(self):
        """Same direction as bh_guild → independent."""
        from engine.territory import ORG_TO_AXIS
        self.assertEqual(ORG_TO_AXIS["bounty_hunters_guild"], "independent")


# ──────────────────────────────────────────────────────────────────────
# 3. flavor strings in get_zone_influence_line
# ──────────────────────────────────────────────────────────────────────

class TestZoneInfluenceLineFlavorByteEquivalence(unittest.TestCase):
    """GCW flavor strings unchanged."""

    def _mock_db(self, zone_data):
        db = MagicMock()
        db.fetchall = AsyncMock(return_value=[])
        return db

    def test_existing_gcw_flavor_strings_unchanged(self):
        """Inspect the source to confirm GCW flavor strings are intact.
        (The function-local dict isn't importable.)"""
        path = os.path.join(PROJECT_ROOT, "engine", "territory.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        # Each GCW flavor line still in source.
        self.assertIn("The Empire's presence is felt here", src)
        self.assertIn("Rebel Alliance influence stirs quietly", src)
        self.assertIn("The Hutt Cartel's grip extends", src)
        self.assertIn("Bounty Hunters' Guild operatives watch", src)


class TestZoneInfluenceLineFlavorCWAdditions(unittest.TestCase):
    """CW flavor strings present in source."""

    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "engine", "territory.py")
        with open(path, encoding="utf-8") as f:
            self.src = f.read()

    def test_republic_flavor_present(self):
        self.assertIn("Republic patrols", self.src)

    def test_cis_flavor_present(self):
        self.assertIn("Separatist sympathizers", self.src)

    def test_jedi_order_flavor_present(self):
        self.assertIn("Jedi presence pervades", self.src)

    def test_bounty_hunters_guild_flavor_present(self):
        self.assertIn("Guild hunters watch", self.src)


# ──────────────────────────────────────────────────────────────────────
# 4. get_claim_display_tag — colors
# ──────────────────────────────────────────────────────────────────────

class TestGetClaimDisplayTagColors(unittest.TestCase):
    """The org_colors dict (function-local) — verify via source check
    plus end-to-end tag generation for one CW org."""

    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "engine", "territory.py")
        with open(path, encoding="utf-8") as f:
            self.src = f.read()

    def test_gcw_color_entries_in_source(self):
        # Existing literal pairs.
        for entry in (
            '"empire":', '"rebel":', '"hutt":', '"bh_guild":',
        ):
            self.assertIn(entry, self.src)

    def test_cw_color_entries_in_source(self):
        for entry in (
            '"republic":', '"cis":', '"jedi_order":',
            '"hutt_cartel":', '"bounty_hunters_guild":',
        ):
            self.assertIn(
                entry, self.src,
                f"CW color entry {entry} missing from get_claim_display_tag"
            )

    def test_get_claim_display_tag_returns_for_cw_org(self):
        """Behavioral: a claim with org_code='republic' renders without
        crashing and includes a recognizable color escape."""
        from engine.territory import get_claim_display_tag
        db = MagicMock()
        # Mock get_claim returning a Republic claim
        async def _get_claim(db_arg, room_id):
            return {"org_code": "republic"}

        # Patch the imported get_claim if needed
        import engine.territory as terr
        original_get_claim = terr.get_claim
        terr.get_claim = _get_claim
        try:
            result = _run(get_claim_display_tag(db, 42))
            self.assertIsNotNone(result)
            self.assertIn("CLAIMED", result)
            self.assertIn("Republic", result)  # title-cased org code
        finally:
            terr.get_claim = original_get_claim


# ──────────────────────────────────────────────────────────────────────
# 5. Smoke
# ──────────────────────────────────────────────────────────────────────

class TestModuleImportsClean(unittest.TestCase):
    def test_territory_imports(self):
        import importlib
        # Force re-import to make sure post-edit module is clean
        if "engine.territory" in sys.modules:
            importlib.reload(sys.modules["engine.territory"])
        else:
            importlib.import_module("engine.territory")


if __name__ == "__main__":
    unittest.main()
