# -*- coding: utf-8 -*-
"""
tests/test_e2_texture_encounter_era_cleanness.py

T2.CW.codebase_era_sweep (slice): engine/encounter_texture.py is a LIVE
production space-encounter file (driven by server/tick_handlers_ships.py::
texture_encounter_tick) that the 2026-06-01 space+missions era-compliance drop
missed. It carried Imperial / TIE / Rebel / Empire strings in the `contact`
scenario (probe-droid carrier, TIE pursuit, "Hail Imperials", "Rebel contact",
"The Empire appreciates loyal citizens").

This drop pivots those to CW-era factions (Republic patrol / Separatist probe
droids / Republic intelligence contact). These tests pin it:

1. Static: no banned era string appears in a CODE line (comments excluded —
   the file's design comments legitimately mention the removed "Imperial"
   label to explain the faction-derived patrol identity).
2. Behavioral: driving contact_hail_imps captures no banned string.
3. The CONTACT_SCENARIOS table descriptions are clean.

Mirrors the _BANNED set + harness from tests/test_drop0a_patrol_era_cleanness.py.
"""
from __future__ import annotations

import asyncio
import os
import re
import unittest

from engine import encounter_texture as et

_BANNED = ("Imperial", "IMPERIAL", "imperial", "Stormtrooper", "stormtrooper",
           "Empire", "TIE fighter", "TIEs", "Rebel", "Rebellion", "Moff",
           "X-wing", "Star Destroyer")


def _run(coro):
    return asyncio.run(coro)


class _FakeMgr:
    def __init__(self):
        self.captured = []

    async def broadcast_to_bridge(self, enc, text, session_mgr):
        self.captured.append(text)

    def resolve(self, enc, outcome=None):
        self.last_outcome = outcome


class _Enc:
    def __init__(self):
        self.zone_id = "zone_test"
        self.context = {"scenario": "racer"}
        self.choices = []
        self.prompt = ""


class TestTextureEncounterStaticCleanliness(unittest.TestCase):
    """No banned era string in a non-comment code line."""

    def test_source_has_no_banned_strings_in_code(self):
        path = et.__file__
        if path.endswith(".pyc"):
            path = path[:-1]
        offending = []
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                code = line.split("#", 1)[0]  # drop trailing/whole comments
                if code.lstrip().startswith("#"):
                    continue
                for term in _BANNED:
                    # word-ish boundary so "Empire" doesn't match "empirical"
                    if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])",
                                 code):
                        offending.append((i, term, line.strip()))
        self.assertEqual(
            offending, [],
            "encounter_texture.py has era-leaking strings in code lines:\n"
            + "\n".join(f"  L{i}: {term!r} — {txt[:80]}"
                        for i, term, txt in offending),
        )


class TestTextureEncounterBehavioral(unittest.TestCase):
    """The runtime strings the player actually sees are CW-clean."""

    def test_hail_patrol_broadcast_is_clean(self):
        mgr = _FakeMgr()
        _run(et.contact_hail_imps(_Enc(), mgr, db=None, sm=None))
        blob = "\n".join(mgr.captured)
        for term in _BANNED:
            self.assertNotIn(term, blob,
                             f"contact_hail_imps leaked era string {term!r}")
        # still routes to the same outcome (mechanics unchanged)
        self.assertEqual(getattr(mgr, "last_outcome", None),
                         "contact_racer_reported")

    def test_contact_scenarios_table_is_clean(self):
        for key, weight, desc in et.CONTACT_SCENARIOS:
            for term in _BANNED:
                self.assertNotIn(
                    term, desc,
                    f"CONTACT_SCENARIOS[{key!r}] leaks era string {term!r}: {desc!r}")


if __name__ == "__main__":
    unittest.main()
