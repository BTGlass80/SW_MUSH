# -*- coding: utf-8 -*-
"""tests/test_rank_up_benefits_producer.py — rank_up event carries real benefits.

Phantom client sub-field fix: `static/client.html::handleRankUp` renders the
toast sub-line from `data.benefits`, but the only producer
(`engine/organizations.check_auto_promote`) emitted `{faction,new_rank,new_level}`
with NO `benefits` key, so the sub-line was always blank. Best/most-complete fix
(add the producer, don't delete the consumer): `rank_benefits_summary` derives a
concise, accurate summary from the rank's real grants — the weekly stipend
(STIPEND_TABLE) plus the rank's newly-issued equipment — and check_auto_promote
now ships it in both the web event and the telnet line.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import organizations


class _FakeSession:
    """Captures send_line text + send_json events emitted on promotion."""
    def __init__(self):
        self.lines = []
        self.events = []

    async def send_line(self, text):
        self.lines.append(text)

    async def send_json(self, kind, data):
        self.events.append((kind, data))


class _PromoteOnceDB:
    """DB that lets exactly one auto-promotion (level 1 -> 2) succeed."""
    def __init__(self, equipment="[]"):
        self._equipment = equipment
        self._level = 1

    async def get_organization(self, code):
        return {"id": 1, "name": "Hutt Cartel"}

    async def get_membership(self, char_id, org_id):
        # rep 9999 always clears the next-rank gate; level advances as promoted.
        return {"rank_level": self._level, "rep_score": 9999}

    async def get_org_ranks(self, org_id):
        # Only a level-2 rank exists past current level 1 -> single promotion.
        return [
            {"rank_level": 1, "title": "Runner", "min_rep": 0, "equipment": "[]"},
            {"rank_level": 2, "title": "Enforcer", "min_rep": 100,
             "equipment": self._equipment},
        ]

    async def update_membership(self, char_id, org_id, rank_level=None):
        self._level = rank_level

    async def log_faction_action(self, *a, **k):
        pass


class TestRankBenefitsSummary(unittest.TestCase):
    def test_stipend_only(self):
        # hutt_cartel rank 2 has a 150 cr stipend; rank with no equipment.
        rank = {"rank_level": 2, "title": "Enforcer", "equipment": "[]"}
        s = organizations.rank_benefits_summary("hutt_cartel", rank, 2)
        self.assertIn("150 cr/week stipend", s)
        self.assertNotIn("·", s)  # only one part

    def test_stipend_and_equipment(self):
        rank = {"rank_level": 2, "title": "Enforcer",
                "equipment": '["medpac"]'}
        s = organizations.rank_benefits_summary("hutt_cartel", rank, 2)
        self.assertIn("150 cr/week stipend", s)
        self.assertIn("Medpac", s)  # catalog display name, not the raw code
        self.assertIn("·", s)

    def test_unknown_equipment_code_falls_back_to_code(self):
        rank = {"rank_level": 2, "equipment": '["mystery_gizmo"]'}
        s = organizations.rank_benefits_summary("hutt_cartel", rank, 2)
        self.assertIn("mystery_gizmo", s)

    def test_many_items_summarized(self):
        rank = {"rank_level": 5,
                "equipment": '["medpac","blaster_pistol","slicing_kit","tracking_fob"]'}
        s = organizations.rank_benefits_summary("hutt_cartel", rank, 5)
        self.assertIn("+ 2 more", s)

    def test_spec_faction_rank1_defers_equipment(self):
        # Spec-eligible faction at rank 1 must NOT promise gear (SpecializeCommand
        # issues it). Use the first spec faction the engine actually configures.
        spec_factions = list(organizations._SPEC_CONFIG_BY_FACTION)
        self.assertTrue(spec_factions, "expected at least one spec faction")
        fac = spec_factions[0]
        rank = {"rank_level": 1, "equipment": '["medpac"]'}
        s = organizations.rank_benefits_summary(fac, rank, 1)
        self.assertNotIn("Medpac", s)

    def test_malformed_equipment_is_safe(self):
        rank = {"rank_level": 2, "equipment": "not-json"}
        s = organizations.rank_benefits_summary("hutt_cartel", rank, 2)
        # stipend still surfaces; no crash on bad JSON
        self.assertIn("150 cr/week stipend", s)

    def test_no_benefits_returns_empty(self):
        rank = {"rank_level": 9, "equipment": "[]"}
        s = organizations.rank_benefits_summary("nonexistent_faction", rank, 9)
        self.assertEqual(s, "")


class TestRankUpProducer(unittest.IsolatedAsyncioTestCase):
    async def test_event_includes_nonempty_benefits(self):
        db = _PromoteOnceDB(equipment='["medpac"]')
        sess = _FakeSession()
        char = {"id": 7, "name": "Greedo"}
        with mock.patch("engine.achievements.on_org_rank_reached",
                        new=mock.AsyncMock()):
            promoted = await organizations.check_auto_promote(
                char, "hutt_cartel", db, session=sess)
        self.assertTrue(promoted)
        # exactly one rank_up event, and it carries a real benefits string
        rank_ups = [d for (k, d) in sess.events if k == "rank_up"]
        self.assertEqual(len(rank_ups), 1)
        ev = rank_ups[0]
        self.assertEqual(ev["new_rank"], "Enforcer")
        self.assertEqual(ev["new_level"], 2)
        self.assertIn("benefits", ev)
        self.assertIn("150 cr/week stipend", ev["benefits"])
        self.assertIn("Medpac", ev["benefits"])

    async def test_telnet_line_echoes_benefits(self):
        db = _PromoteOnceDB(equipment='["medpac"]')
        sess = _FakeSession()
        char = {"id": 7, "name": "Greedo"}
        with mock.patch("engine.achievements.on_org_rank_reached",
                        new=mock.AsyncMock()):
            await organizations.check_auto_promote(
                char, "hutt_cartel", db, session=sess)
        joined = "\n".join(sess.lines)
        self.assertIn("RANK UP", joined)
        self.assertIn("Benefits:", joined)
        self.assertIn("150 cr/week stipend", joined)

    async def test_benefits_key_always_present_even_when_empty(self):
        # A faction absent from STIPEND_TABLE with no rank equipment -> empty
        # benefits, but the key must still ship so the SPA consumer never reads
        # undefined, and the telnet line must omit the "Benefits:" row.
        assert ("test_guild", 2) not in organizations.STIPEND_TABLE
        db = _PromoteOnceDB(equipment='[]')
        sess = _FakeSession()
        char = {"id": 7, "name": "Greedo"}
        with mock.patch("engine.achievements.on_org_rank_reached",
                        new=mock.AsyncMock()):
            await organizations.check_auto_promote(
                char, "test_guild", db, session=sess)
        ev = [d for (k, d) in sess.events if k == "rank_up"][0]
        self.assertIn("benefits", ev)
        self.assertEqual(ev["benefits"], "")
        self.assertNotIn("Benefits:", "\n".join(sess.lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
