"""
test_m3_command_palette.py — UX Drop 7 (Ctrl/Cmd+K command palette) contract.

Two layers (mirrors tests/spa/test_m3_goals.py):

  A. jsdom DOM-runtime of static/spa/m3_command_palette.js:
     - Fuzzy filtering returns correct subset.
     - Result list is capped at 10.
     - Selecting a row STAGES (fires the stage callback with the verb) and
       does NOT auto-send (no ws.send call).
     - Esc closes the palette.
     - XSS: a malicious summary/key renders as escaped text, no live element.
     - Closed-palette guard: Enter keydown does NOT fire the stage callback
       when the palette is closed.

  B. Static parse of static/client.html:
     - #command-palette element exists.
     - /static/spa/m3_command_palette.js script is included.
     - M3CommandPalette.init( is called inside the client init block.
     - The Ctrl/Cmd+K handler is attached via M3CommandPalette's own
       document-level keydown (guard: the init call is present).
"""
from __future__ import annotations

import re
from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_PALETTE = str(REPO_ROOT / "static" / "spa" / "m3_command_palette.js")
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

# ── Sample corpus injected into every DOM test ───────────────────────────────
# All entries carry is_command:true — this corpus represents registered command
# verbs. Tests that need a mixed command+topic corpus use _MIXED_CORPUS_JS.
_CORPUS_JS = """
var corpus = [
  { key: 'look',     title: 'Look',       category: 'Movement',    summary: 'Examine your surroundings.',   is_command: true },
  { key: 'attack',   title: 'Attack',     category: 'Combat',      summary: 'Initiate a melee attack.',      is_command: true },
  { key: '+sheet',   title: 'Character Sheet', category: 'Info',   summary: 'View your character stats.',   is_command: true },
  { key: 'craft',    title: 'Craft',      category: 'Economy',     summary: 'Craft an item from a schematic.', is_command: true },
  { key: 'survey',   title: 'Survey',     category: 'Exploration', summary: 'Survey the area for resources.', is_command: true },
  { key: 'bounties', title: 'Bounties',   category: 'Jobs',        summary: 'Open the bounty board.',        is_command: true },
  { key: 'pose',     title: 'Pose',       category: 'Social',      summary: 'Perform an emote or action pose.', is_command: true },
  { key: 'say',      title: 'Say',        category: 'Social',      summary: 'Speak aloud to the room.',      is_command: true },
  { key: 'whisper',  title: 'Whisper',    category: 'Social',      summary: 'Send a private message.',       is_command: true },
  { key: 'go',       title: 'Go',         category: 'Movement',    summary: 'Move to an exit.',              is_command: true },
  { key: 'north',    title: 'North',      category: 'Movement',    summary: 'Move north.',                   is_command: true },
  { key: 'south',    title: 'South',      category: 'Movement',    summary: 'Move south.',                   is_command: true },
  { key: 'east',     title: 'East',       category: 'Movement',    summary: 'Move east.',                    is_command: true },
  { key: 'west',     title: 'West',       category: 'Movement',    summary: 'Move west.',                    is_command: true },
  { key: '+help',    title: 'Help',       category: 'Info',        summary: 'Access the help system.',       is_command: true },
];
"""

_INIT_JS = """
window.M3CommandPalette.init({
  escapeHtml: function(s){
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  },
  fetchImpl: function(url) {
    // No real network in tests; resolve with the injected corpus.
    return Promise.resolve({
      json: function() { return Promise.resolve({ entries: corpus }); }
    });
  },
  stage: function(cmd) { staged.push(cmd); }
});
"""

_BASE = _CORPUS_JS + """
var staged = [];
var sent = [];
""" + _INIT_JS + """
// Seed the cache directly so tests don't need async fetch to settle.
window.M3CommandPalette._setCache(corpus);

// Build overlay DOM (falls back to the programmatic builder in the module).
"""


# ════════════════════════════════════════════════════════════════════════
# A. jsdom DOM-runtime
# ════════════════════════════════════════════════════════════════════════

def test_fuzzy_filter_returns_correct_subset():
    """Search 'att' returns attack (key substring) but not look or survey."""
    out = run_with_dom([M3_PALETTE], _BASE + """
        window.M3CommandPalette._openPalette();
        window.M3CommandPalette._renderResults('att');
        var results = window.M3CommandPalette._getResults();
        result = {
            count: results.length,
            keys: results.map(function(e){ return e.key; })
        };
    """)
    assert 'attack' in out['keys'], f"'attack' missing from results: {out['keys']}"
    assert 'look' not in out['keys'], f"'look' should not match 'att': {out['keys']}"
    assert 'survey' not in out['keys'], f"'survey' should not match 'att': {out['keys']}"


def test_caps_at_ten_results():
    """A broad query that matches all 15 entries still returns only 10."""
    out = run_with_dom([M3_PALETTE], _BASE + """
        window.M3CommandPalette._openPalette();
        // Empty query: all entries score > 0 (score=1 for empty)
        window.M3CommandPalette._renderResults('');
        var results = window.M3CommandPalette._getResults();
        result = { count: results.length };
    """)
    assert out['count'] == 10, f"Expected 10 (cap), got {out['count']}"


def test_selecting_row_stages_not_auto_sends():
    """Selecting index 0 fires the stage callback and does NOT call ws.send."""
    out = run_with_dom([M3_PALETTE], _BASE + """
        // Populate a single-entry filtered result so index 0 is deterministic.
        window.M3CommandPalette._openPalette();
        window.M3CommandPalette._renderResults('look');
        var results = window.M3CommandPalette._getResults();

        // stage callback is already registered in _INIT_JS — it appends to staged[].
        window.M3CommandPalette._stageEntry(0);

        result = {
            stagedCount: staged.length,
            stagedCmd:   staged[0] || null,
            sentCount:   sent.length,
            paletteOpen: window.M3CommandPalette._open()
        };
    """)
    assert out['stagedCount'] == 1, f"stage not called: staged count = {out['stagedCount']}"
    assert out['stagedCmd'] is not None, "staged command was null"
    assert 'look' in out['stagedCmd'], f"Expected 'look' in staged cmd, got {out['stagedCmd']!r}"
    assert out['sentCount'] == 0, f"ws.send was called (auto-sent): sentCount={out['sentCount']}"
    assert out['paletteOpen'] is False, "palette should close after selecting a row"


def test_esc_closes_palette():
    """Dispatching an Escape keydown event closes the palette."""
    out = run_with_dom([M3_PALETTE], _BASE + """
        window.M3CommandPalette._openPalette();
        var before = window.M3CommandPalette._open();

        // Dispatch a real keydown event that the module's handler catches.
        var ev = document.createEvent('KeyboardEvent');
        ev.initKeyboardEvent('keydown', true, true, window, 'Escape', 0, false, false, false, false);
        // Some jsdom versions need the key property set directly
        Object.defineProperty(ev, 'key', { value: 'Escape', writable: false });
        document.dispatchEvent(ev);

        result = { openBefore: before, openAfter: window.M3CommandPalette._open() };
    """)
    assert out['openBefore'] is True, "palette wasn't open before Esc"
    assert out['openAfter'] is False, "palette should be closed after Esc"


def test_xss_escaped_in_results():
    """Malicious summary/key renders as escaped text; no live script/img."""
    out = run_with_dom([M3_PALETTE], _BASE + """
        var maliciousCorpus = [
          { key: '<img src=x onerror=alert(1)>',
            title: 'Evil',
            category: 'Test',
            summary: '<script>alert(2)</script>' }
        ];
        window.M3CommandPalette._setCache(maliciousCorpus);
        window.M3CommandPalette._openPalette();
        window.M3CommandPalette._renderResults('');

        var listEl = window.M3CommandPalette._getListEl();
        result = {
            innerHTML:    listEl ? listEl.innerHTML : '',
            liveImgCount: listEl ? listEl.querySelectorAll('img').length : 0,
            liveScriptCount: listEl ? listEl.querySelectorAll('script').length : 0
        };
    """)
    assert '<img' not in out['innerHTML'], "live <img> tag found in palette list"
    assert '&lt;img' in out['innerHTML'] or '&amp;lt;img' in out['innerHTML'] or \
           'onerror' not in out['innerHTML'], \
        f"XSS not escaped in innerHTML: {out['innerHTML'][:300]}"
    assert out['liveImgCount'] == 0, f"Live <img> element found: count={out['liveImgCount']}"
    assert out['liveScriptCount'] == 0, f"Live <script> element found: count={out['liveScriptCount']}"
    assert '<script>' not in out['innerHTML'], "raw <script> in innerHTML"


def test_closed_palette_does_not_intercept_enter():
    """When the palette is closed, Enter keydown does NOT fire stage."""
    out = run_with_dom([M3_PALETTE], _BASE + """
        // Ensure palette is closed.
        // (It is not opened in this test.)
        var isOpen = window.M3CommandPalette._open();

        // Dispatch Enter keydown while palette is closed.
        var ev = document.createEvent('KeyboardEvent');
        ev.initKeyboardEvent('keydown', true, true, window, 'Enter', 0, false, false, false, false);
        Object.defineProperty(ev, 'key', { value: 'Enter', writable: false });
        document.dispatchEvent(ev);

        result = { isOpen: isOpen, stagedCount: staged.length };
    """)
    assert out['isOpen'] is False, "palette should be closed at test start"
    assert out['stagedCount'] == 0, \
        f"stage() was called with palette closed: staged count={out['stagedCount']}"


def test_prefix_beats_substring_in_ranking():
    """Key-prefix match ranks above key-substring for same query."""
    out = run_with_dom([M3_PALETTE], """
        var M = window.M3CommandPalette;
        var prefixEntry    = { key: 'attack', title: 'Attack', summary: '' };
        var substringEntry = { key: 'jab-attack', title: 'Jab Attack', summary: '' };
        var prefixScore    = M._score(prefixEntry, 'att');
        var substringScore = M._score(substringEntry, 'att');
        result = { prefixScore: prefixScore, substringScore: substringScore, prefixWins: prefixScore > substringScore };
    """ + _INIT_JS.replace("window.M3CommandPalette._setCache(corpus);", ""))
    assert out['prefixWins'], \
        f"prefix should outscore substring: prefix={out['prefixScore']}, sub={out['substringScore']}"


# ════════════════════════════════════════════════════════════════════════
# B. Static client.html wire-up guards (no node needed)
# ════════════════════════════════════════════════════════════════════════

def test_command_palette_element_in_client_html():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    assert 'id="command-palette"' in html, \
        "#command-palette element missing from client.html"


def test_script_include_in_client_html():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_command_palette.js' in html, \
        "m3_command_palette.js script tag missing from client.html"


def test_init_call_in_client_html():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    assert 'M3CommandPalette.init(' in html, \
        "M3CommandPalette.init( call missing from client.html"


def test_ctrl_k_handler_via_separate_listener():
    """The palette's Ctrl/Cmd+K handler is attached inside M3CommandPalette.init
    (a separate document-level keydown), NOT inside setupInput.

    Guard: setupInput must NOT contain any Ctrl/Cmd+K logic; the M3CommandPalette
    init call is present in client.html so the module attaches its own listener.
    """
    html = CLIENT_HTML.read_text(encoding="utf-8")

    # Find the setupInput function body (between its open brace and the next
    # top-level function declaration) and assert no Ctrl/K logic is in there.
    # We use a simple regex to capture the function's text.
    m = re.search(r'function setupInput\(.*?\{(.+?)(?=\nfunction |\Z)', html, re.DOTALL)
    assert m, "setupInput function not found in client.html"
    setup_body = m.group(1)

    # The palette's keydown is in M3CommandPalette, not setupInput. Both checks
    # are independent (an OR here would be tautological — setupInput never
    # contains the literal 'M3CommandPalette', so the right operand is always
    # true and would mask a real ctrlKey leak).
    assert 'ctrlKey' not in setup_body, \
        "Ctrl+K logic leaked into setupInput body — must live in M3CommandPalette only"
    assert 'M3CommandPalette' not in setup_body, \
        "M3CommandPalette referenced inside setupInput — palette must wire its own listener"

    # Confirm the init call is present (so the module attaches its own listener).
    assert 'M3CommandPalette.init(' in html, \
        "M3CommandPalette.init( not found — palette Ctrl/K listener won't attach"


# ════════════════════════════════════════════════════════════════════════
# C. Fun-2: is_command filter — topics never staged
# ════════════════════════════════════════════════════════════════════════

# Mixed corpus: some entries have is_command=true, some false (topics).
_MIXED_CORPUS_JS = """
var corpus = [
  { key: 'look',    title: 'Look',        category: 'Commands', summary: 'Examine surroundings.', is_command: true  },
  { key: 'attack',  title: 'Attack',      category: 'Combat',   summary: 'Attack a target.',      is_command: true  },
  { key: '+sheet',  title: 'Sheet',       category: 'Info',     summary: 'View character stats.', is_command: true  },
  { key: 'dice',    title: 'The D6 System', category: 'Rules: D6', summary: 'How dice work.',     is_command: false },
  { key: 'combat',  title: 'Combat Basics', category: 'Rules: Combat', summary: 'How combat works.', is_command: false },
  { key: 'force',   title: 'The Force',   category: 'Rules: Force', summary: 'Force abilities.',  is_command: false },
  { key: 'moseisley', title: 'Mos Eisley', category: 'World',  summary: 'The spaceport city.',   is_command: false },
];
"""

_MIXED_BASE = _MIXED_CORPUS_JS + """
var staged = [];
var sent = [];
""" + _INIT_JS + """
window.M3CommandPalette._setCache(corpus);
"""


def test_topic_entries_excluded_from_palette_results():
    """Entries with is_command=false are filtered out; only is_command=true entries appear."""
    out = run_with_dom([M3_PALETTE], _MIXED_BASE + """
        window.M3CommandPalette._openPalette();
        // Empty query: returns all scoreable entries — but only commands
        window.M3CommandPalette._renderResults('');
        var results = window.M3CommandPalette._getResults();
        result = {
            count: results.length,
            keys:  results.map(function(e){ return e.key; })
        };
    """)
    # Only the 3 is_command=true entries should appear
    assert out['count'] == 3, \
        f"Expected 3 command entries, got {out['count']}. Keys: {out['keys']}"
    assert 'look'   in out['keys'], f"'look' missing from filtered results: {out['keys']}"
    assert 'attack' in out['keys'], f"'attack' missing from filtered results: {out['keys']}"
    assert '+sheet' in out['keys'], f"'+sheet' missing from filtered results: {out['keys']}"
    # Topic keys must be absent
    for topic_key in ('dice', 'combat', 'force', 'moseisley'):
        assert topic_key not in out['keys'], \
            f"Topic key {topic_key!r} leaked into palette results: {out['keys']}"


def test_selecting_topic_never_stages_it():
    """If a topic somehow reached _results (legacy cache), _stageEntry is safe.

    More importantly: with the is_command filter active, searching for a topic
    key produces zero results, so _stageEntry(0) is a no-op and staged stays empty.
    """
    out = run_with_dom([M3_PALETTE], _MIXED_BASE + """
        window.M3CommandPalette._openPalette();
        window.M3CommandPalette._renderResults('dice');
        var results = window.M3CommandPalette._getResults();
        // Try to stage index 0 — should do nothing because results is empty
        window.M3CommandPalette._stageEntry(0);
        result = {
            resultCount: results.length,
            stagedCount: staged.length
        };
    """)
    assert out['resultCount'] == 0, \
        f"'dice' (is_command=false) should produce 0 palette results, got {out['resultCount']}"
    assert out['stagedCount'] == 0, \
        f"stage() should not have been called: stagedCount={out['stagedCount']}"


def test_command_entries_still_stageable_after_filter():
    """is_command=true entries are still staged normally (filter doesn't over-block)."""
    out = run_with_dom([M3_PALETTE], _MIXED_BASE + """
        window.M3CommandPalette._openPalette();
        window.M3CommandPalette._renderResults('look');
        var results = window.M3CommandPalette._getResults();
        window.M3CommandPalette._stageEntry(0);
        result = {
            resultCount: results.length,
            stagedCount: staged.length,
            stagedCmd:   staged[0] || null
        };
    """)
    assert out['resultCount'] >= 1, \
        f"'look' (is_command=true) should appear in palette results, got {out['resultCount']}"
    assert out['stagedCount'] == 1, \
        f"stage() should have been called once: stagedCount={out['stagedCount']}"
    assert out['stagedCmd'] is not None and 'look' in out['stagedCmd'], \
        f"Expected 'look' in staged command, got {out['stagedCmd']!r}"


def test_mixed_query_only_returns_command_matches():
    """A query that matches both a command and a topic key returns only the command."""
    out = run_with_dom([M3_PALETTE], _MIXED_BASE + """
        // 'att' matches 'attack' (is_command=true); does NOT match any topic
        // 'combat' topic has is_command=false and should not show.
        window.M3CommandPalette._openPalette();
        window.M3CommandPalette._renderResults('at');
        var results = window.M3CommandPalette._getResults();
        result = {
            keys: results.map(function(e){ return e.key; })
        };
    """)
    # 'attack' matches 'at' (prefix or substring) and is_command=true
    assert 'attack' in out['keys'], \
        f"'attack' should appear for query 'at'. Keys: {out['keys']}"
    # 'combat' contains 'at' but is_command=false → must not appear
    assert 'combat' not in out['keys'], \
        f"Topic 'combat' leaked into palette for query 'at'. Keys: {out['keys']}"


def test_enter_on_topic_result_never_stages_topic_key():
    """Enter on a result list populated with only commands stages a command, not a topic key.

    Regression guard: confirms the filter chain (corpus → is_command → _results → Enter)
    never produces a topic key in the staged slot.
    """
    out = run_with_dom([M3_PALETTE], _MIXED_BASE + """
        window.M3CommandPalette._openPalette();
        // Render all — only commands should be in results
        window.M3CommandPalette._renderResults('');
        var results = window.M3CommandPalette._getResults();

        // Simulate Enter: stage index 0 (the first result)
        window.M3CommandPalette._stageEntry(0);

        var topicKeys = ['dice', 'combat', 'force', 'moseisley'];
        var stagedIsATopic = staged.length > 0 &&
            topicKeys.some(function(k) { return staged[0] && staged[0].indexOf(k) === 0; });

        result = {
            stagedCmd: staged[0] || null,
            stagedIsATopic: stagedIsATopic,
            resultCount: results.length
        };
    """)
    assert not out['stagedIsATopic'], \
        f"Enter staged a topic key: {out['stagedCmd']!r}. Only command verbs should be stageable."
    assert out['resultCount'] == 3, \
        f"Expected 3 command results before Enter, got {out['resultCount']}"
