# -*- coding: utf-8 -*-
"""
tests/test_qa_blockers_b2_b3.py

Regression guards for two VERIFIED launch blockers from the pre-launch QA
campaign (docs/design/QA_FINDINGS_2026-06-16.md), both fixed in the same
loop-safe drop:

  B2. Weapon vendors all dead — the `vendor` flag was dropped at the NPC
      DB-write seam (engine.npc_loader._build_ai_config), so the buy-gear
      credit SINK was entirely inert. NPCs declare `vendor: true` under
      `ai_config:` in YAML; the buy consumer (parser/space_commands.py)
      gates on `ai_config_json["vendor"]`.

  B3. Faction comms reached 0 recipients — server.channels.get_faction read
      `char["faction"]` / `attrs["faction"]`, but membership lives in the
      `faction_id` column (DEFAULT 'independent'). Every real member
      collapsed to 'independent', so fcomm / faction channel / faction
      announce delivered to nobody.

These were invisible to the ~7,700-test suite (the systemic stub/curated-data
blind spot the QA campaign called out): the vendor producer test only checked
the YAML source, not the DB write; and get_faction was exercised with
hand-built `{"faction": ...}` dicts, never a real `faction_id`-carrying row.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.npc_loader import _build_ai_config  # noqa: E402
from server.channels import get_faction, FACTIONS  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# B2 — the `vendor` flag survives the ai_config build (DB-write seam)
# ══════════════════════════════════════════════════════════════════════════
class TestB2VendorFlagSurvives(unittest.TestCase):
    def test_vendor_true_passed_through(self):
        cfg = _build_ai_config({"vendor": True}, "Kayson")
        self.assertTrue(cfg.get("vendor"),
                        "vendor: true must survive _build_ai_config so the "
                        "buy consumer's ai_config_json['vendor'] gate fires")

    def test_vendor_survives_json_roundtrip_to_consumer(self):
        # Mirror the real path: build -> json.dumps (ai_config_json column)
        # -> json.loads -> the consumer's `ai_cfg.get("vendor")` gate.
        cfg = _build_ai_config({"vendor": True, "personality": "Jawa trader"},
                               "Trade-elder")
        ai_config_json = json.dumps(cfg)
        ai_cfg = json.loads(ai_config_json)
        self.assertTrue(ai_cfg.get("vendor"))

    def test_no_vendor_key_when_absent(self):
        cfg = _build_ai_config({"personality": "grumpy"}, "Lup")
        # Absent -> falsy at the consumer (the grocer is NOT an arms dealer).
        self.assertFalse(cfg.get("vendor"))

    def test_vendor_false_is_not_a_vendor(self):
        cfg = _build_ai_config({"vendor": False}, "Lup")
        self.assertFalse(cfg.get("vendor"))

    def test_vendor_coexists_with_other_passthroughs(self):
        # Regression: adding vendor must not disturb the existing schema or
        # the other conditional pass-throughs.
        cfg = _build_ai_config(
            {"vendor": True, "trainer": True, "train_skills": ["blaster"],
             "faction": "Hutt", "personality": "  spaced   out  "},
            "Multi")
        self.assertTrue(cfg.get("vendor"))
        self.assertTrue(cfg.get("trainer"))
        self.assertEqual(cfg.get("train_skills"), ["blaster"])
        self.assertEqual(cfg.get("faction"), "Hutt")
        # personality is still whitespace-normalized
        self.assertEqual(cfg.get("personality"), "spaced out")


# ══════════════════════════════════════════════════════════════════════════
# B3 — get_faction resolves real members from the `faction_id` column
# ══════════════════════════════════════════════════════════════════════════
class TestB3FactionResolvesFromFactionId(unittest.TestCase):
    def test_cw_faction_ids_resolve(self):
        # THE bug repro: a DB-row-shaped char carries only faction_id.
        for code in ("republic", "cis", "jedi_order"):
            self.assertIn(code, FACTIONS)  # codes really are valid
            self.assertEqual(get_faction({"faction_id": code}), code)

    def test_faction_id_takes_precedence_over_legacy_key(self):
        char = {"faction_id": "jedi_order", "faction": "cis"}
        self.assertEqual(get_faction(char), "jedi_order")

    def test_independent_faction_id(self):
        self.assertEqual(get_faction({"faction_id": "independent"}),
                         "independent")

    def test_unknown_faction_id_falls_back_to_independent(self):
        self.assertEqual(get_faction({"faction_id": "not_a_faction"}),
                         "independent")

    def test_legacy_top_level_faction_key_still_works(self):
        # Back-compat: callers that pass an explicit `faction` field
        # (no faction_id) keep working.
        self.assertEqual(get_faction({"faction": "cis"}), "cis")

    def test_attributes_blob_fallback_still_works(self):
        char = {"attributes": json.dumps({"faction": "republic"})}
        self.assertEqual(get_faction(char), "republic")

    def test_empty_and_none(self):
        self.assertEqual(get_faction({}), "independent")
        self.assertEqual(get_faction(None), "independent")

    def test_two_members_share_a_faction(self):
        # The delivery condition broadcast_fcomm uses:
        # get_faction(sender) == get_faction(recipient).
        a = {"faction_id": "jedi_order"}
        b = {"faction_id": "jedi_order"}
        c = {"faction_id": "cis"}
        self.assertEqual(get_faction(a), get_faction(b))
        self.assertNotEqual(get_faction(a), get_faction(c))


if __name__ == "__main__":
    unittest.main()
