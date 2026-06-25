"""test_m3_situation_board.py — UX Drop 4 (Living-world Situation board) contract.

Loads static/spa/m3_situation_board.js under jsdom and exercises
M3SituationBoard.render() against a representative situation_state payload (the
shape produced by DirectorAI.compile_situation_digest / server _hud_situation_
digest). Verifies the influence ladder, the world-event rows, the active-
uprising card + menace threat-meter, and the truncated headline rows; that a
null/absent uprising degrades to NO card (no throw); and that server-authored
headlines route through escapeHtml (XSS).

Static wire-up guards (no node) pin the cartridge registration ('SIT' tab +
'SITUATION' dispatcher case) in m3_assembled_client.js, the client.html
situation_state router + sidebar panel, and the server push helper — mirroring
tests/spa/test_m3_region.py's wiring guards.
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_SIT = str(REPO_ROOT / "static" / "spa" / "m3_situation_board.js")


_STATE_JS = """
var state = {
  zone: 'mos_eisley',
  influence: [
    { faction: 'hutt_cartel', score: 72 },
    { faction: 'republic',    score: 45 },
    { faction: 'cis',         score: 12 }
  ],
  events: [
    { type: 'sandstorm', name: 'Sandstorm', zones: ['mos_eisley'],
      remaining_minutes: 18, effects: {}, headline: 'A wall of sand rolls in.' },
    { type: 'bounty_surge', name: 'Bounty Surge', zones: [],
      remaining_minutes: 0, effects: {}, headline: 'Contracts spike galaxy-wide.' }
  ],
  uprising: { cult_key: 'hollow_sun', zone_label: 'Mos Eisley',
              menace: 63, state: 'active' },
  news: [
    { timestamp: '02:14', event_type: 'news',
      summary: 'Republic cruisers converge on Ryloth as the CIS ground assault stalls badly.' },
    { timestamp: '00:42', event_type: 'ambient',
      summary: 'Krayt dragon sighted north of Anchorhead.' }
  ]
};
"""


def test_situation_board_renders_all_sections():
    out = run_with_dom([M3_SIT], _STATE_JS + """
        var root = window.M3SituationBoard.render(state);

        var infRows = root.querySelectorAll('.sit-inf-row');
        // ladder is sorted desc → first row is the highest score (hutt 72)
        var firstName = infRows[0].querySelector('.sit-inf-name').textContent;
        var firstFill = infRows[0].querySelector('.sit-inf-fill').getAttribute('style');

        var eventRows = root.querySelectorAll('.sit-event-row');
        var uprising  = root.querySelector('[data-sit-uprising]');
        var menaceBar = root.querySelector('.sit-menace-fill');
        var newsRows  = root.querySelectorAll('[data-sit-news-row]');

        result = {
            zone: root.querySelector('.sit-zone-name').textContent,
            infCount: infRows.length,
            firstName: firstName,
            firstFill: firstFill,
            eventCount: eventRows.length,
            hasUprising: !!uprising,
            uprisingKey: uprising ? uprising.getAttribute('data-sit-uprising') : null,
            menaceWidth: menaceBar ? menaceBar.getAttribute('style') : null,
            menaceBand: root.querySelector('.sit-uprising').getAttribute('class'),
            newsCount: newsRows.length
        };
    """)

    assert out["zone"] == "Mos Eisley"
    assert out["infCount"] == 3
    # highest score sorts first; 72/100 → 72.0% fill
    assert out["firstName"] == "Hutt Cartel"
    assert "width:72.0%" in out["firstFill"]
    assert out["eventCount"] == 2
    assert out["hasUprising"] is True
    assert out["uprisingKey"] == "hollow_sun"
    # menace 63 → 63.0% bar, cresting band (>= MENACE_MED 66? no → rising/med band)
    assert "width:63.0%" in out["menaceWidth"]
    # 63 is in [33,66) → RISING (sit-menace-med)
    assert "sit-menace-med" in out["menaceBand"]
    assert out["newsCount"] == 2


def test_menace_band_thresholds():
    out = run_with_dom([M3_SIT], """
        var b = window.M3SituationBoard;
        result = {
            low:  b.menaceBand(10).key,
            med:  b.menaceBand(50).key,
            high: b.menaceBand(80).key
        };
    """)
    assert out["low"] == "simmering"
    assert out["med"] == "rising"
    assert out["high"] == "cresting"


def test_null_uprising_degrades_to_no_card():
    out = run_with_dom([M3_SIT], _STATE_JS + """
        state.uprising = null;
        var root = window.M3SituationBoard.render(state);
        result = {
            hasUprisingCard: !!root.querySelector('[data-sit-uprising]'),
            // the board still renders the other sections
            infCount: root.querySelectorAll('.sit-inf-row').length,
            eventCount: root.querySelectorAll('.sit-event-row').length
        };
    """)
    assert out["hasUprisingCard"] is False   # no card, no throw
    assert out["infCount"] == 3
    assert out["eventCount"] == 2


def test_empty_payload_renders_without_throw():
    out = run_with_dom([M3_SIT], """
        var root = window.M3SituationBoard.render({});
        result = {
            isElement: !!(root && root.nodeType === 1),
            hasUprising: !!root.querySelector('[data-sit-uprising]'),
            // empty-state copy is shown rather than crashing
            emptyCount: root.querySelectorAll('.sit-empty').length
        };
    """)
    assert out["isElement"] is True
    assert out["hasUprising"] is False
    assert out["emptyCount"] >= 1


def test_headline_is_xss_escaped():
    out = run_with_dom([M3_SIT], """
        var state = {
          zone: 'mos_eisley', influence: [], events: [],
          uprising: null,
          news: [ { timestamp: '00:00', event_type: 'news',
                    summary: '<img src=x onerror=alert(1)>' } ]
        };
        var root = window.M3SituationBoard.render(state);
        var row = root.querySelector('[data-sit-news-row] .sit-news-summary');
        // querySelector to prove no live <img> element was parsed into the DOM
        result = {
            innerHTML: row.innerHTML,
            title: row.getAttribute('title'),
            liveImgCount: root.querySelectorAll('img').length
        };
    """)
    # The visible row is escaped (entities, not a live tag); no <img> element
    # was ever parsed into the DOM tree.
    assert "<img" not in out["innerHTML"]
    assert "&lt;img" in out["innerHTML"]
    assert out["liveImgCount"] == 0
    # The tooltip carries the RAW summary verbatim — setAttribute('title', ...) is
    # a safe DOM sink (attribute values are never parsed as HTML); locking it here
    # documents the contract + prevents a future over-eager double-escape.
    assert out["title"] == '<img src=x onerror=alert(1)>'


def test_event_headline_is_xss_escaped():
    out = run_with_dom([M3_SIT], """
        var state = {
          zone: 'z', influence: [], uprising: null, news: [],
          events: [ { type: 'x', name: 'X', zones: [], remaining_minutes: 5,
                      headline: '<script>alert(1)</script>' } ]
        };
        var root = window.M3SituationBoard.render(state);
        var hl = root.querySelector('.sit-event-headline');
        result = { innerHTML: hl ? hl.innerHTML : '' };
    """)
    assert "<script>" not in out["innerHTML"]
    assert "&lt;script&gt;" in out["innerHTML"]


# ── static wire-up guards (no node needed) ───────────────────────────
def test_cartridge_registration_in_assembled_client():
    src = (REPO_ROOT / "static" / "spa" / "m3_assembled_client.js").read_text(encoding="utf-8")
    # 'SIT' tab in the cartridge pill array.
    assert "'SIT'" in src, "SIT tab not registered in cartridge tabs array"
    # 'SITUATION' dispatcher case reachable (alias of 'SIT').
    assert "case 'SITUATION'" in src, "SITUATION dispatcher case missing"
    assert "case 'SIT'" in src, "SIT dispatcher case missing"
    assert "buildMiniSituation" in src, "SIT body builder missing"
    assert "M3SituationBoard.render" in src, "board renderer not invoked from cartridge"


def test_situation_panel_wired_into_client_html():
    html = (REPO_ROOT / "static" / "client.html").read_text(encoding="utf-8")
    for needle in (
        'id="situation-panel"',
        'id="situation-body"',
        '/static/spa/m3_situation_board.js',
        "case 'situation_state':",
        "function handleSituationState(",
        "function hideSituationPanel(",
        "hideSituationPanel();",        # called on room change
        "M3SituationBoard.render(",
    ):
        assert needle in html, f"situation panel wiring missing from client.html: {needle!r}"


def test_situation_state_pushed_by_server():
    sess = (REPO_ROOT / "server" / "session.py").read_text(encoding="utf-8")
    assert "_hud_situation_digest" in sess, "situation push helper missing"
    assert '"situation_state"' in sess, "situation_state send missing"
    assert "compile_situation_digest" in sess, "digest producer not called"
    # Rides the existing HUD tick (called from send_hud_update).
    assert "send_hud_update" in sess


def test_digest_producer_and_filter_in_director():
    director = (REPO_ROOT / "engine" / "director.py").read_text(encoding="utf-8")
    assert "async def compile_situation_digest" in director
    assert "INTERNAL_NEWS_EVENTS" in director
    for t in ("faction_turn", "era_milestone", "economic_nudge"):
        assert t in director
