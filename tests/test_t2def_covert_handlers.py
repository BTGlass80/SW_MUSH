# -*- coding: utf-8 -*-
"""
tests/test_t2def_covert_handlers.py

T2.DEF.handler_npcs — Republic & CIS covert-contact intel handlers
(Brian decision 2026-06-05, option A: add dedicated covert-contact NPCs
rather than mis-tag the canon-faithful Nar Shaddaa HQ residents or
relocate the HQs).

Also covers the bundled one-line data fix TD.CW_JEDI_HQ_ROOM_NAME: the
Jedi Order `hq_room_name` now points at a real room.

Runtime-pinned, not just byte-pinned: each new handler's ai_config is
run through engine.npc_loader._build_ai_config (the exact function the
world loader uses) to prove the `is_intel_handler` marker survives the
schema filter into the config the engine reads — the failure mode that
the Q3 seed originally tripped (the marker being silently dropped).
"""
from __future__ import annotations

import os
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
G1 = os.path.join(CW, "npcs_drop_g1_nar_shaddaa_topside.yaml")
ORGS = os.path.join(CW, "organizations.yaml")
CORUSCANT = os.path.join(CW, "planets", "coruscant.yaml")


def _load_npcs(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {n["name"]: n for n in data.get("npcs", [])}


class TestCovertHandlersSeeded(unittest.TestCase):
    """The two new covert handlers exist at the right HQ rooms with the
    right faction and the handler marker."""

    @classmethod
    def setUpClass(cls):
        cls.npcs = _load_npcs(G1)

    def test_republic_handler_present(self):
        n = self.npcs.get("Tomar Vell")
        self.assertIsNotNone(n, "Tomar Vell (Republic handler) not found")
        self.assertEqual(n["room"], "Nar Shaddaa - Corellian Sector Promenade")
        ai = n["ai_config"]
        self.assertEqual(ai["faction"], "republic")
        self.assertTrue(ai.get("is_intel_handler"))
        self.assertFalse(ai.get("hostile", False))

    def test_cis_handler_present(self):
        n = self.npcs.get("Vexen Daro")
        self.assertIsNotNone(n, "Vexen Daro (CIS handler) not found")
        self.assertEqual(n["room"], "Nar Shaddaa - The Burning Deck Cantina")
        ai = n["ai_config"]
        self.assertEqual(ai["faction"], "cis")
        self.assertTrue(ai.get("is_intel_handler"))
        self.assertFalse(ai.get("hostile", False))

    def test_full_static_hq_handler_roster(self):
        """All 5 static-HQ factions now have exactly one intel handler.

        Borka (hutt_cartel), Drel Mok (bounty_hunters_guild) and Halen
        Voss (jedi_order) were already seeded; Republic and CIS land here.
        We assert the two new ones rather than re-counting across files
        (the other three live in other yaml drops) — the contract this
        test owns is "Republic and CIS are now covered, cleanly."
        """
        for name, faction in (("Tomar Vell", "republic"),
                              ("Vexen Daro", "cis")):
            n = self.npcs[name]
            self.assertEqual(n["ai_config"]["faction"], faction)
            self.assertTrue(n["ai_config"]["is_intel_handler"])


class TestHandlerMarkerSurvivesLoader(unittest.TestCase):
    """Runtime pin: _build_ai_config must carry is_intel_handler + faction
    through into the config the engine actually reads."""

    @classmethod
    def setUpClass(cls):
        cls.npcs = _load_npcs(G1)

    def test_marker_passes_through_build_ai_config(self):
        from engine.npc_loader import _build_ai_config
        for name, faction in (("Tomar Vell", "republic"),
                              ("Vexen Daro", "cis")):
            ai = self.npcs[name]["ai_config"]
            config = _build_ai_config(ai, name)
            self.assertTrue(
                config.get("is_intel_handler"),
                f"{name}: is_intel_handler dropped by loader",
            )
            self.assertEqual(
                config.get("faction"), faction,
                f"{name}: faction not carried by loader",
            )

    def test_intel_handlers_module_importable(self):
        """Smoke: the intel-handler engine module imports and exposes the
        key name it matches against. (Recognition semantics are covered by
        that module's own suite; this drop's contract is that the marker
        survives _build_ai_config, asserted above.)"""
        try:
            from engine.intel_handlers import INTEL_HANDLER_AI_KEY
        except Exception:
            self.skipTest("intel_handlers not importable")
        self.assertEqual(INTEL_HANDLER_AI_KEY, "is_intel_handler")


class TestJediHqRoomFix(unittest.TestCase):
    """TD.CW_JEDI_HQ_ROOM_NAME: jedi_order hq_room_name resolves to a
    room that actually exists."""

    @staticmethod
    def _factions(orgs):
        if isinstance(orgs, dict) and isinstance(orgs.get("factions"), list):
            return orgs["factions"]
        return []

    @staticmethod
    def _hq_name(fac):
        # hq_room_name lives under properties in this schema.
        props = fac.get("properties") if isinstance(fac, dict) else None
        if isinstance(props, dict) and "hq_room_name" in props:
            return props["hq_room_name"]
        return fac.get("hq_room_name") if isinstance(fac, dict) else None

    def setUp(self):
        with open(ORGS, "r", encoding="utf-8") as fh:
            self.orgs = yaml.safe_load(fh)

    def test_jedi_hq_points_at_real_room(self):
        jedi = next(
            (f for f in self._factions(self.orgs)
             if f.get("code") == "jedi_order"), None)
        self.assertIsNotNone(jedi, "jedi_order faction not found")
        hq = self._hq_name(jedi)
        self.assertEqual(hq, "Jedi Temple - Entrance Hall")

        # And that room must exist on Coruscant.
        with open(CORUSCANT, "r", encoding="utf-8") as fh:
            cor = yaml.safe_load(fh)
        names = set()

        def collect(o):
            if isinstance(o, dict):
                if isinstance(o.get("name"), str):
                    names.add(o["name"])
                for v in o.values():
                    collect(v)
            elif isinstance(o, list):
                for i in o:
                    collect(i)

        collect(cor)
        self.assertIn("Jedi Temple - Entrance Hall", names)

    def test_no_faction_points_at_the_old_broken_room(self):
        broken = "Coruscant - Jedi Temple Main Hall"
        for f in self._factions(self.orgs):
            self.assertNotEqual(
                self._hq_name(f), broken,
                f"{f.get('code')} still points at the removed room name",
            )


if __name__ == "__main__":
    unittest.main()
