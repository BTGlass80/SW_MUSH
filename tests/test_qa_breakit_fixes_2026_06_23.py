# -*- coding: utf-8 -*-
"""
tests/test_qa_breakit_fixes_2026_06_23.py — fixes from the browser break-it campaign.

Two confirmed real defects found by the real-Chromium break-it fan-out:

  * INVENTORY (HIGH): the INV quick-action HUD button sent `inventory`, but the
    command-syntax rework DELETED that alias (`+inv` is the only form). So the
    button was DEAD -- clicking it did nothing. (4 sites: the static markup + the
    explore / postcombat / enterPostCombatMode JS configs.) Retargeted to `+inv`.

  * AUTH (MEDIUM): the web character-select loop only broke on a matching id; an
    UNKNOWN id (stale picker after a delete/switch, a reconnect race, a desynced
    WS frame) fell through SILENTLY -- the client stayed stranded on its "entering
    game" splash until the 300s timeout. Now it errors + re-sends a fresh picker.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLIENT = (REPO / "static" / "client.html").read_text(encoding="utf-8")
GS = (REPO / "server" / "game_server.py").read_text(encoding="utf-8")


class TestInvButtonRetargeted:
    def test_no_dead_inventory_cmd_remains(self):
        assert "cmd: 'inventory'" not in CLIENT, "a JS quick-action still sends the deleted 'inventory'"
        assert 'data-cmd="inventory"' not in CLIENT, "a static button still sends the deleted 'inventory'"

    def test_inv_buttons_target_the_real_command(self):
        # the INV buttons now use +inv (the registered InventoryCommand key)
        assert "cmd: '+inv'" in CLIENT
        assert 'data-cmd="+inv"' in CLIENT
        from parser import builtin_commands
        assert builtin_commands.InventoryCommand.key == "+inv"


class TestCharSelectUnknownIdRecovery:
    def test_unknown_id_re_sends_picker_and_errors(self):
        # locate the web __char_select__ handler and assert it recovers on unknown id
        i = GS.index('line.startswith("__char_select__")')
        block = GS[i:i + 1400]
        assert "No such character" in block, "unknown-id path must tell the player"
        # must re-emit the picker so the client un-sticks from the entering-game splash
        after_break = block[block.index("Entering the game"):]
        assert 'send_json("char_select"' in after_break, \
            "unknown-id path must re-send the char_select picker"


if __name__ == "__main__":
    import sys, pytest
    sys.exit(pytest.main([__file__, "-v"]))
