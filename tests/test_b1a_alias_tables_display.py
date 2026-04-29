# -*- coding: utf-8 -*-
"""
tests/test_b1a_alias_tables_display.py — B.1.a (server display + alias
tables) tests.

Per architecture v38 §19.7 and `b1_audit_v1.md` §3, B.1.a is the lowest-
risk B.1 sub-drop: extend three alias tables / display constants to
cover both GCW and CW faction codes. No removals; both eras coexist.

Three change sites:

  1. `server/channels.py` — `FACTIONS` / `FACTION_LABELS` / `FACTION_COLORS`
     extended to be the era-agnostic union. CW PCs with stored
     `attributes.faction = "republic"` now render as `[Republic]` not
     the `Unknown` fallback.

  2. `engine/vendor_droids.py::_FACTION_NAME_MAP` — extended with CW
     entries (republic/cis/jedi_order/hutt_cartel/bounty_hunters_guild
     plus long-form aliases like "Galactic Republic", "Confederacy of
     Independent Systems", "Jedi Order").

  3. `parser/npc_commands.py::_fac_map` (inside
     `_inject_faction_context`) — same treatment.

Tests are byte-equivalent: every existing GCW alias still resolves to
its same canonical code; every existing GCW label/color still matches
the prior value. New CW entries are additive.

Note: `engine/vendor_droids.py::_FACTION_NAME_MAP` is a function-local
dict, so we can't import it directly. Instead we test it via the
public function that consumes it (or by inspecting the source token-
level — see TestVendorDroidsFactionMapSource).
"""
from __future__ import annotations

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. server/channels.py — FACTIONS / FACTION_LABELS / FACTION_COLORS
# ──────────────────────────────────────────────────────────────────────

class TestChannelsConstantsByteEquivalence(unittest.TestCase):
    """Existing GCW codes must keep their existing labels and colors."""

    def test_gcw_factions_still_present(self):
        """All four canonical GCW director-axis codes are still in
        FACTIONS (the production set)."""
        from server.channels import FACTIONS
        for fac in ("imperial", "rebel", "criminal", "independent"):
            self.assertIn(fac, FACTIONS,
                          f"GCW canonical code '{fac}' was dropped from FACTIONS")

    def test_gcw_labels_unchanged(self):
        """Existing label values are byte-identical to pre-B.1.a."""
        from server.channels import FACTION_LABELS
        self.assertEqual(FACTION_LABELS["imperial"],    "Imperial")
        self.assertEqual(FACTION_LABELS["rebel"],       "Rebel")
        self.assertEqual(FACTION_LABELS["criminal"],    "Criminal")
        self.assertEqual(FACTION_LABELS["independent"], "Independent")

    def test_gcw_colors_unchanged(self):
        """Existing color values are byte-identical to pre-B.1.a."""
        from server.channels import FACTION_COLORS
        self.assertEqual(FACTION_COLORS["imperial"],    "\033[37m")
        self.assertEqual(FACTION_COLORS["rebel"],       "\033[31m")
        self.assertEqual(FACTION_COLORS["criminal"],    "\033[33m")
        self.assertEqual(FACTION_COLORS["independent"], "\033[36m")


class TestChannelsConstantsCWExtensions(unittest.TestCase):
    """The B.1.a additions: CW codes are recognized and display correctly.

    Asymmetric: these tests FAIL pre-B.1.a (those keys didn't exist),
    PASS post-B.1.a.
    """

    def test_cw_factions_added(self):
        from server.channels import FACTIONS
        for fac in ("republic", "cis"):
            self.assertIn(fac, FACTIONS,
                          f"CW director-axis code '{fac}' missing from FACTIONS")

    def test_cw_labels_present(self):
        from server.channels import FACTION_LABELS
        self.assertEqual(FACTION_LABELS["republic"], "Republic")
        self.assertEqual(FACTION_LABELS["cis"],      "Separatist")

    def test_cw_colors_present(self):
        """CW codes have a color entry (any valid ANSI code)."""
        from server.channels import FACTION_COLORS
        self.assertIn("republic", FACTION_COLORS)
        self.assertIn("cis", FACTION_COLORS)
        # Colors are ANSI escape sequences.
        self.assertTrue(FACTION_COLORS["republic"].startswith("\033["))
        self.assertTrue(FACTION_COLORS["cis"].startswith("\033["))

    def test_org_axis_aliases_for_attributes_faction(self):
        """Org-axis codes (`empire`/`republic`/`hutt_cartel` etc.) that
        might appear in `attributes.faction` from chargen are also
        recognized."""
        from server.channels import FACTION_LABELS
        # Org-axis 'empire' should display as 'Imperial' (matches GCW
        # director-axis label).
        self.assertEqual(FACTION_LABELS["empire"], "Imperial")
        # CW org-axis names get reasonable display labels.
        self.assertEqual(FACTION_LABELS["hutt_cartel"], "Hutt")
        self.assertEqual(FACTION_LABELS["jedi_order"],  "Jedi")
        self.assertEqual(
            FACTION_LABELS["bounty_hunters_guild"], "Bounty Hunter"
        )


class TestFmtFcommUsesEraAwareLabels(unittest.TestCase):
    """The display function must render CW factions correctly."""

    def test_fcomm_format_for_republic(self):
        """A CW Republic PC's fcomm should render as [Republic], not [Unknown]."""
        from server.channels import fmt_fcomm
        out = fmt_fcomm("Skywalker", "republic", "Hello")
        self.assertIn("[Republic]", out)
        self.assertNotIn("[Unknown]", out)

    def test_fcomm_format_for_cis(self):
        from server.channels import fmt_fcomm
        out = fmt_fcomm("Dooku", "cis", "Greetings")
        self.assertIn("[Separatist]", out)

    def test_fcomm_format_for_imperial_unchanged(self):
        """GCW byte-equivalence: existing Imperial fcomm still renders correctly."""
        from server.channels import fmt_fcomm
        out = fmt_fcomm("Vader", "imperial", "You don't know the power")
        self.assertIn("[Imperial]", out)


# ──────────────────────────────────────────────────────────────────────
# 2. engine/vendor_droids.py — _FACTION_NAME_MAP (in-source check)
# ──────────────────────────────────────────────────────────────────────

class TestVendorDroidsFactionMapSource(unittest.TestCase):
    """The `_FACTION_NAME_MAP` is a function-local dict, so we verify
    the source contains the expected entries (string match) rather than
    importing it directly."""

    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "engine", "vendor_droids.py")
        with open(path, encoding="utf-8") as f:
            self.source = f.read()

    def test_gcw_entries_still_present(self):
        for entry in (
            '"empire":', '"imperial":', '"galactic empire":',
            '"rebel":', '"rebellion":', '"rebel alliance":',
            '"hutt":', '"hutts":', '"hutt cartel":',
            '"bh_guild":', '"bounty hunters guild":', '"bounty hunters":',
        ):
            self.assertIn(entry, self.source,
                          f"GCW alias '{entry}' missing from vendor_droids "
                          f"_FACTION_NAME_MAP (regression)")

    def test_cw_entries_added(self):
        for entry in (
            '"republic":', '"galactic republic":',
            '"cis":', '"confederacy":', '"separatist":',
            '"jedi":', '"jedi order":',
            '"hutt_cartel":', '"bounty_hunters_guild":',
        ):
            self.assertIn(entry, self.source,
                          f"CW alias '{entry}' missing from vendor_droids "
                          f"_FACTION_NAME_MAP")

    def test_cw_entries_route_to_canonical_codes(self):
        """The CW long-form entries should map to canonical CW codes."""
        # Quick sanity: source contains the right pairings.
        # Exact pattern: `"republic":             "republic",` etc.
        self.assertRegex(self.source, r'"galactic republic":\s*"republic"')
        self.assertRegex(self.source, r'"confederacy":\s*"cis"')
        self.assertRegex(self.source, r'"jedi order":\s*"jedi_order"')


# ──────────────────────────────────────────────────────────────────────
# 3. parser/npc_commands.py — _fac_map (in-source check)
# ──────────────────────────────────────────────────────────────────────

class TestNpcCommandsFacMapSource(unittest.TestCase):
    """The `_fac_map` is a function-local dict inside
    `_inject_faction_context`. Verify source-level extension."""

    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "parser", "npc_commands.py")
        with open(path, encoding="utf-8") as f:
            self.source = f.read()

    def test_gcw_entries_still_present(self):
        for key in (
            '"imperial":', '"empire":', '"galactic empire":',
            '"rebel":', '"rebel alliance":',
            '"hutt":', '"hutt cartel":',
            '"bounty hunter":', '"bounty hunters":',
            "\"bounty hunters' guild\":",
        ):
            self.assertIn(
                key, self.source,
                f"GCW alias '{key}' missing from npc_commands _fac_map"
            )

    def test_cw_entries_added(self):
        for key in (
            '"republic":', '"galactic republic":',
            '"cis":', '"separatist":', '"separatists":',
            '"jedi":', '"jedi order":',
            '"confederacy":',
            '"hutt_cartel":', '"bounty_hunters_guild":',
        ):
            self.assertIn(
                key, self.source,
                f"CW alias '{key}' missing from npc_commands _fac_map"
            )


# ──────────────────────────────────────────────────────────────────────
# 4. Smoke: imports clean (catches typo regressions)
# ──────────────────────────────────────────────────────────────────────

class TestModuleImportsClean(unittest.TestCase):
    def test_channels_imports(self):
        import importlib
        mod = importlib.import_module("server.channels")
        self.assertTrue(hasattr(mod, "FACTIONS"))
        self.assertTrue(hasattr(mod, "FACTION_LABELS"))
        self.assertTrue(hasattr(mod, "FACTION_COLORS"))
        # FACTIONS must be a frozenset/set.
        self.assertIsInstance(mod.FACTIONS, (frozenset, set))


if __name__ == "__main__":
    unittest.main()
