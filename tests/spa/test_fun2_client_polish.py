"""
test_fun2_client_polish.py — FUN2 client dead-code removals (verified).

- The cockpit BOOST switch staged a non-existent `speed +1` verb → removed.
- handleRankUp read `data.benefits`, a field the rank_up producer
  (engine/organizations.py) never emits → dead read removed.

(auth_status was NOT removed — it HAS a producer at game_server.py:985, so the
audit's 'dead consumer' finding was stale. The separatist 'cannot be retried'
copy is left pending verification of abort_step_no_retry enforcement.)
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def test_boost_switch_removed():
    html = _html()
    assert 'data-switch="BOOST"' not in html, "dead BOOST switch should be removed"
    assert 'data-cmd="speed +1"' not in html, "the phantom 'speed +1' command should be gone"


def test_rank_up_does_not_read_benefits():
    html = _html()
    i = html.find("function handleRankUp")
    assert i != -1, "handleRankUp missing"
    block = html[i:i + 400]
    assert "data.benefits" not in block, (
        "handleRankUp must not read data.benefits (never emitted by the producer)")
