# -*- coding: utf-8 -*-
"""
tests/test_qa_force_session_sync_2026_06_23.py — QA break-it regression
(Force-powers-in-use sweep, 2026-06-23).

Two CORRUPTION findings: a Force power lands from the ATTACKER's command, so the
TARGET's session cache (HUD / sheet / equip display) was never updated -- it kept
showing the victim HEALTHY / still-armed until the victim's NEXT command refreshed
the session from the DB. The live combat object was correct; only the victim's
display lagged.

  #1 injure_kill: `_save_target_after_force` saved wound_level to the DB but not
     the target's session cache.
  #2 telekinesis disarm: `_apply_disarm` wrote the cleared equipment to the DB
     and already had the target session in hand (for the notify), but never
     updated its cached equipment.

Fix: both now sync the target's session cache and push a HUD update after the DB
write. Pinned structurally (the sync wiring must stay in each function; a
two-session behavioral test is disproportionately heavy for a display-cache sync).
"""
from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = (PROJECT_ROOT / "parser" / "force_commands.py").read_text(encoding="utf-8")


def _fn_body(name: str) -> str:
    i = SRC.index("async def %s(" % name)
    j = SRC.index("\nasync def ", i + 1)
    return SRC[i:j]


class TestForceSessionSync(unittest.TestCase):
    def test_injure_syncs_target_session_wound_and_hud(self):
        body = _fn_body("_save_target_after_force")
        self.assertIn('find_by_character(target_dict["id"])', body)
        self.assertIn('wound_level"] = target_obj.wound_level.value', body)
        self.assertIn("send_hud_update", body)

    def test_disarm_syncs_target_session_equipment_and_hud(self):
        body = _fn_body("_apply_disarm")
        self.assertIn('character["equipment"] = target_dict["equipment"]', body)
        self.assertIn('equipped_weapon"] = ""', body)
        self.assertIn("send_hud_update", body)


if __name__ == "__main__":
    unittest.main()
