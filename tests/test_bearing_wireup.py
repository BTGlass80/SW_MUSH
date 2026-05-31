"""
test_bearing_wireup.py — Phase-1 bearing substrate wiring (end-to-end seam).

Guards the whole bearing path without a live server/browser:
  · parser/builtin_commands.py MoveCommand records attributes.bearing from the
    matched exit's direction, folded into the existing rooms_visited
    attributes write (no extra DB write), only on planar moves.
  · server/session.py exposes _bearing_from_attributes and stamps bearing on
    BOTH player_position and each pc contact.
  · static/client.html copies player_position.bearing into _sw_areaGeom.player
    on both the area-transition and per-tick paths.
The server reader's behaviour (string/dict/absent/junk, bearing 0) is exercised
directly.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILTINS = REPO_ROOT / "parser" / "builtin_commands.py"
SESSION_PY = REPO_ROOT / "server" / "session.py"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def test_move_command_records_bearing():
    src = BUILTINS.read_text(encoding="utf-8")
    start = src.index("async def _post_move_hooks")
    body = src[start: start + 3000]
    assert "from engine.bearing import bearing_for_direction" in body, (
        "MoveCommand must derive bearing from the move direction"
    )
    assert '_attrs["bearing"] = _bearing' in body, "MoveCommand must store attributes.bearing"
    # uses the matched exit's canonical direction (de-abbreviated) as the source
    assert 'exit_data.get("direction")' in body, "bearing source should be the matched exit direction"
    # folded into the same attributes write — the save call appears once in the block
    assert body.count("save_character(char[\"id\"], attributes=") == 1, (
        "bearing + rooms_visited must share ONE attributes write (no extra DB write)"
    )


def test_server_emits_bearing():
    src = SESSION_PY.read_text(encoding="utf-8")
    assert "def _bearing_from_attributes(char)" in src, "session must define _bearing_from_attributes"
    # player_position carries the player's own bearing
    import re as _re
    assert _re.search(r'"bearing":\s*_bearing_from_attributes\(self\.character\)', src), (
        "player_position must carry the player's bearing"
    )
    # pc contacts carry bearing
    bc = src[src.index("async def _build_area_contacts"):][:4000]
    assert '"bearing": _bearing_from_attributes(sc)' in bc, "pc contacts must carry bearing"


def test_client_plumbs_player_bearing():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    # both player blocks copy bearing through from player_position
    assert html.count("bearing: data.player_position.bearing") == 2, (
        "both player_position assignments must copy bearing into _sw_areaGeom.player"
    )


def test_server_reader_behaviour():
    # import the real helper and exercise its branches
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from server.session import _bearing_from_attributes
    assert _bearing_from_attributes({"attributes": json.dumps({"bearing": 90})}) == 90
    assert _bearing_from_attributes({"attributes": {"bearing": 270}}) == 270
    assert _bearing_from_attributes({"attributes": json.dumps({"bearing": 0})}) == 0  # falsy but valid
    assert _bearing_from_attributes({"attributes": "{}"}) is None
    assert _bearing_from_attributes({"attributes": "not json"}) is None
    assert _bearing_from_attributes({}) is None
    assert _bearing_from_attributes(None) is None
