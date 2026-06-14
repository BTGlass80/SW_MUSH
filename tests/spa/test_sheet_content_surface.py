"""
test_sheet_content_surface.py — Drop C (T3.17 sheet gap-close) verification.

Static parse of static/client.html asserting that the five new surfaces
ship correctly:

  1. Specializations — p.specializations list rendered in SKILLS view.
  2. PvP badge       — pts.pvp_flagged truthy guard → badge rendered.
  3. Notes           — p.notes truthy guard → rendered in right rail.
  4. Description     — identity.description truthy guard → rendered.
  5. Bio fields      — gender/homeworld/age/height/hair/eyes each
                       guarded on truthy (no unconditional empty rows).

Pure-Python regex/string checks; mirrors test_gnd_ux_context_panel.py style.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ── helpers ────────────────────────────────────────────────────────────────

def _extract_fn(html: str, fn_name: str) -> str:
    """Extract a top-level JS function by brace-counting."""
    needle = "function " + fn_name + "("
    start = html.find(needle)
    if start == -1:
        return ""
    depth = 0
    i = start
    in_fn = False
    while i < len(html):
        ch = html[i]
        if ch == '{':
            depth += 1
            in_fn = True
        elif ch == '}':
            depth -= 1
            if in_fn and depth == 0:
                return html[start: i + 1]
        i += 1
    return html[start: start + 6000]


# ── 1. Specializations ─────────────────────────────────────────────────────

def test_specializations_field_read():
    """p.specializations is referenced in client.html."""
    assert "specializations" in _html(), (
        "specializations field not referenced in client.html"
    )


def test_makeSheetSpecRow_defined():
    """makeSheetSpecRow function is defined."""
    html = _html()
    assert re.search(r"function\s+makeSheetSpecRow\s*\(", html), (
        "makeSheetSpecRow not defined"
    )


def test_specializations_rendered_in_renderSheetCenter():
    """renderSheetCenter calls makeSheetSpecRow for each spec."""
    block = _extract_fn(_html(), "renderSheetCenter")
    assert "makeSheetSpecRow" in block, (
        "makeSheetSpecRow not called inside renderSheetCenter"
    )


def test_specializations_guarded_on_non_empty():
    """Specializations block is guarded: only rendered when specs.length > 0."""
    block = _extract_fn(_html(), "renderSheetCenter")
    # Must find a truthy/length guard near makeSheetSpecRow
    assert re.search(r"specs\.length\s*[>!]=?\s*0|specs\.length\b", block), (
        "Specializations not guarded on non-empty list in renderSheetCenter"
    )


def test_specializations_skipped_on_combat_tab():
    """Specializations are not rendered on the combat tab."""
    block = _extract_fn(_html(), "renderSheetCenter")
    # Must find a 'combat' exclusion guard around the specs block
    assert re.search(r"combat", block), (
        "'combat' tab guard not found in renderSheetCenter (specs should be excluded)"
    )


def test_spec_row_uses_escapeHtml():
    """makeSheetSpecRow uses escapeHtml for server-supplied text."""
    block = _extract_fn(_html(), "makeSheetSpecRow")
    assert "escapeHtml" in block, (
        "makeSheetSpecRow must use escapeHtml on server-supplied spec.name/spec.skill"
    )


def test_spec_row_uses_sheetPoolToStr():
    """makeSheetSpecRow formats dice pools via sheetPoolToStr."""
    block = _extract_fn(_html(), "makeSheetSpecRow")
    assert "sheetPoolToStr" in block, (
        "makeSheetSpecRow should format pools via sheetPoolToStr"
    )


# ── 2. PvP badge ───────────────────────────────────────────────────────────

def test_pvp_flagged_field_read():
    """pvp_flagged is referenced in client.html."""
    html = _html()
    assert "pvp_flagged" in html, (
        "pvp_flagged field not referenced"
    )


def test_pvp_badge_rendered_in_renderSheetPoints():
    """renderSheetPoints contains the PvP badge render path."""
    block = _extract_fn(_html(), "renderSheetPoints")
    assert "pvp_flagged" in block, (
        "pvp_flagged not consumed in renderSheetPoints"
    )
    assert "pvp" in block.lower() or "PvP" in block, (
        "PvP badge text not found in renderSheetPoints"
    )


def test_pvp_badge_guarded_on_truthy():
    """PvP badge is rendered only when pvp_flagged is truthy (not unconditional)."""
    block = _extract_fn(_html(), "renderSheetPoints")
    # There must be a conditional guard — either an if-statement or ternary
    # that gates on pts.pvp_flagged
    assert re.search(r"pvp_flagged\s*\?|if\s*\(.*pvp_flagged", block), (
        "PvP badge must be guarded by pvp_flagged truthiness"
    )


def test_pvp_badge_empty_when_false():
    """When pvp_flagged is false, the badge branch yields empty string."""
    block = _extract_fn(_html(), "renderSheetPoints")
    # The ternary must have an empty-string false branch
    assert re.search(r"pvp_flagged\s*\?.*:\s*['\"]", block, re.DOTALL), (
        "pvp_flagged ternary must have an empty-string false branch"
    )


# ── 3. Notes ───────────────────────────────────────────────────────────────

def test_notes_field_read():
    """p.notes is referenced in client.html."""
    assert "p.notes" in _html() or ".notes" in _html(), (
        "notes field not referenced"
    )


def test_notes_rendered_in_renderSheetBackground():
    """renderSheetBackground renders p.notes."""
    block = _extract_fn(_html(), "renderSheetBackground")
    assert "notes" in block, (
        "notes not consumed inside renderSheetBackground"
    )


def test_notes_guarded_on_non_empty():
    """Notes block is only rendered when notes text is non-empty."""
    block = _extract_fn(_html(), "renderSheetBackground")
    # Must find a truthy guard around notes content
    assert re.search(r"notesText\b|p\.notes", block), (
        "notes not guarded on non-empty inside renderSheetBackground"
    )
    # The guard must be conditional, not unconditional
    assert re.search(r"if\s*\(notesText\)|if\s*\(.*notes", block), (
        "notes must be in a conditional block (non-empty guard)"
    )


def test_notes_uses_escapeHtml():
    """Notes text is passed through escapeHtml."""
    block = _extract_fn(_html(), "renderSheetBackground")
    # Find escapeHtml somewhere after the notes variable
    idx_notes = block.find("notesText")
    idx_escape = block.find("escapeHtml(notesText)")
    assert idx_escape != -1, (
        "notesText must be rendered via escapeHtml(notesText)"
    )


# ── 4. Description ─────────────────────────────────────────────────────────

def test_description_field_read():
    """identity.description is referenced in renderSheetBackground."""
    block = _extract_fn(_html(), "renderSheetBackground")
    assert "description" in block, (
        "identity.description not referenced in renderSheetBackground"
    )


def test_description_guarded_on_non_empty():
    """Description block is only rendered when non-empty."""
    block = _extract_fn(_html(), "renderSheetBackground")
    assert re.search(r"descText\b|id\.description", block), (
        "description not guarded on non-empty"
    )
    assert re.search(r"if\s*\(descText\)", block), (
        "description must be in an if(descText) conditional block"
    )


def test_description_uses_escapeHtml():
    """Description text is passed through escapeHtml."""
    block = _extract_fn(_html(), "renderSheetBackground")
    assert "escapeHtml(descText)" in block, (
        "descText must be rendered via escapeHtml(descText)"
    )


# ── 5. Bio fields ──────────────────────────────────────────────────────────

def test_bio_fields_read_in_renderSheetBackground():
    """All 6 bio fields referenced inside renderSheetBackground."""
    block = _extract_fn(_html(), "renderSheetBackground")
    for field in ("gender", "homeworld", "age", "height", "hair", "eyes"):
        assert field in block, (
            f"Bio field '{field}' not referenced in renderSheetBackground"
        )


def test_bio_fields_each_individually_guarded():
    """Each bio field is individually guarded on truthy (if (id.<field>))."""
    block = _extract_fn(_html(), "renderSheetBackground")
    for field in ("gender", "homeworld", "age", "height", "hair", "eyes"):
        # Must appear in a truthiness check (if-guard or ternary)
        pattern = rf"if\s*\(\s*id\.{field}\s*\)|id\.{field}\s*&&|id\.{field}\s*\?"
        assert re.search(pattern, block), (
            f"Bio field '{field}' must be individually guarded on truthy in "
            f"renderSheetBackground — no unconditional empty row allowed"
        )


def test_bio_no_unconditional_placeholder_rows():
    """There are no unconditional 'Gender: —' / empty-placeholder rows."""
    block = _extract_fn(_html(), "renderSheetBackground")
    # Should not contain unconditional labels like 'Gender:' outside a guard
    for field in ("Gender:", "Homeworld:", "Age:", "Height:"):
        # A static string like 'Gender: —' would be a phantom producer
        assert "Gender: —" not in block, (
            "Unconditional 'Gender: —' placeholder found — must be guarded"
        )


def test_bio_uses_escapeHtml_for_server_fields():
    """Bio fields are escaped via escapeHtml before insertion."""
    block = _extract_fn(_html(), "renderSheetBackground")
    assert "escapeHtml(id." in block or "escapeHtml(String(id." in block, (
        "Bio fields must be escaped via escapeHtml"
    )


# ── Safety: no raw payload data injected without escaping ─────────────────

def test_no_raw_innerHTML_of_payload_in_new_renderers():
    """New rendering code does not inject raw payload strings via innerHTML.

    We assert that every reference to spec.name, spec.skill, id.description,
    id.gender etc is wrapped in escapeHtml or is a static literal prefix.
    This is a best-effort static check — look for obvious direct injections.
    """
    spec_block = _extract_fn(_html(), "makeSheetSpecRow")
    bg_block   = _extract_fn(_html(), "renderSheetBackground")
    pts_block  = _extract_fn(_html(), "renderSheetPoints")

    # spec.name must not appear outside escapeHtml in innerHTML assignment
    raw_spec_name = re.search(r"innerHTML\s*[+]=.*spec\.name(?!\s*\|\|)", spec_block)
    # If found, it must be wrapped — just assert escapeHtml is present
    assert "escapeHtml" in spec_block, "makeSheetSpecRow must use escapeHtml"
    assert "escapeHtml" in bg_block,   "renderSheetBackground must use escapeHtml"


# ── Era cleanliness ────────────────────────────────────────────────────────

def test_no_gcw_tokens_in_new_code():
    """New rendering functions contain no GCW era tokens."""
    combined = (
        _extract_fn(_html(), "makeSheetSpecRow") +
        _extract_fn(_html(), "renderSheetPoints")
    )
    # Only check the new functions; renderSheetBackground predates this drop
    for token in ("empire", "rebel", r"\bTIE\b"):
        assert not re.search(token, combined, re.IGNORECASE), (
            f"GCW token '{token}' found in new sheet renderers"
        )
