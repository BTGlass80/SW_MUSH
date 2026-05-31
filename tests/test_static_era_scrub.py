"""
test_static_era_scrub.py — era-contamination regression test for static/ HTML.

Drop 4.7-A (May 26 2026): scrubbed 6 era-contamination hits from production
static frontend (5 in client.html + 1 in portal.html). This test prevents
regression: any new Imperial/Empire/Rebel/TIE/X-wing/etc. strings in the
shipped HTML files will fail this test.

Allowlist:
- "Hutt Empire" in any file — canonical galactic-history reference
  (ancient Hutt Empire ~25,000 BBY, unrelated to the Galactic Empire).
- "empire" / "rebel" as backward-compat keys in static/client.html
  FACTION_LABELS and FACTION_PRIORITY — kept because engine still emits
  these legacy keys (engine bug #6 per opus_code_review_session4.md;
  unfixed at HEAD). Both render as GALACTIC REPUBLIC / CONFEDERACY OF
  INDEPENDENT SYSTEMS so the player never sees the legacy text.

This test runs alongside the Playwright harness Drop 4.1 sets up.
Until then, it can be run as a standalone pytest.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

ERA_CONTAMINATION_PATTERN = re.compile(
    r"\b("
    r"Empire|Imperial|Rebel|Rebellion|Stormtrooper|"
    r"TIE/|TIE-|X-wing|X-Wing|Vader|Death Star|"
    r"ISB|Imperial Security Bureau|stormtroop"
    r")\b"
)

# False positives (allowed substrings that match but aren't era contamination).
ALLOWLIST_PATTERNS = [
    re.compile(r"\bTIER\b"),                 # Renderer tier system
    re.compile(r"\btier:\b"),                # YAML / data references
    re.compile(r"\bTIER_DEFS\b"),
    re.compile(r"\btier_index\b"),
    re.compile(r"\bTier [0-9]"),             # Cover tier names ("Tier 3")
    re.compile(r"\bHutt Empire\b"),          # Canonical ancient lore
    re.compile(r"backward-compat", re.IGNORECASE),  # Comments explaining the back-compat keys
    re.compile(r"fallback", re.IGNORECASE),
    re.compile(r"legacy GCW", re.IGNORECASE),
    re.compile(r"GCW codes", re.IGNORECASE),
    re.compile(r"Drop 4\.7", re.IGNORECASE), # Drop-trail comments
    re.compile(r"engine bug", re.IGNORECASE),
    re.compile(r"player never sees", re.IGNORECASE),
    re.compile(r"never sees Empire", re.IGNORECASE),
]

# Specific backward-compat lines in FACTION_LABELS / FACTION_PRIORITY
# that contain bare empire/rebel keys but are intentional fallback aliases.
EXPECTED_BACKCOMPAT_LINES = {
    # Format: (filename, fragment_required_to_match)
    ("client.html", "FACTION_PRIORITY = ['republic', 'cis'"),
    ("client.html", "empire:   'GALACTIC REPUBLIC'"),
    ("client.html", "rebel:    'CONFEDERACY OF INDEPENDENT SYSTEMS'"),
}


def _is_allowlisted(line: str, filename: str) -> bool:
    """True if any allowlist pattern matches this line."""
    for pat in ALLOWLIST_PATTERNS:
        if pat.search(line):
            return True
    # Check backward-compat fragments
    for (fname, fragment) in EXPECTED_BACKCOMPAT_LINES:
        if fname == filename and fragment in line:
            return True
    return False


@pytest.mark.parametrize("filename", ["client.html", "portal.html", "chargen.html"])
def test_no_era_contamination_in_static_html(filename: str) -> None:
    """No Imperial/Rebel/TIE/X-wing era contamination in shipped HTML."""
    path = STATIC_DIR / filename
    assert path.exists(), f"{filename} not found at {path}"

    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if ERA_CONTAMINATION_PATTERN.search(line) and not _is_allowlisted(line, filename):
            hits.append((lineno, line.strip()))

    if hits:
        msg_lines = [f"Era contamination found in {filename}:"]
        for lineno, line in hits:
            msg_lines.append(f"  line {lineno}: {line[:140]}")
        pytest.fail("\n".join(msg_lines))


def test_chargen_boot_string_uses_sbi() -> None:
    """Chargen credential-verification subtitle uses Senate Bureau of Intelligence."""
    path = STATIC_DIR / "client.html"
    content = path.read_text(encoding="utf-8")
    assert "Senate Bureau of Intelligence · Credential Verification" in content, (
        "Expected SBI credential-verification subtitle in client.html"
    )
    assert "Imperial Security Bureau · Credential Verification" not in content, (
        "Legacy ISB subtitle still present in client.html"
    )


def test_portal_tagline_uses_republic_patrols() -> None:
    """Portal landing tagline references Republic patrols, not Imperial."""
    path = STATIC_DIR / "portal.html"
    content = path.read_text(encoding="utf-8")
    assert "past Republic patrols" in content, (
        "Expected 'past Republic patrols' tagline in portal.html"
    )
    assert "past Imperial patrols" not in content, (
        "Legacy 'past Imperial patrols' tagline still present in portal.html"
    )


def test_faction_labels_render_canonical_cw_strings() -> None:
    """FACTION_LABELS renders Galactic Republic / CIS, not Empire / Rebel Alliance."""
    path = STATIC_DIR / "client.html"
    content = path.read_text(encoding="utf-8")
    # Canonical CW labels present
    assert "republic: 'GALACTIC REPUBLIC'" in content
    assert "cis:      'CONFEDERACY OF INDEPENDENT SYSTEMS'" in content
    # Legacy labels removed (the bare strings, not the backward-compat aliases)
    assert "'GALACTIC EMPIRE'" not in content
    assert "'REBEL ALLIANCE'" not in content


def test_faction_priority_includes_both_canonical_and_legacy() -> None:
    """FACTION_PRIORITY includes canonical CW codes first AND legacy aliases.

    The dual-key approach is the documented back-compat strategy until the
    engine's VALID_FACTION_CODES is updated (engine bug #6).
    """
    path = STATIC_DIR / "client.html"
    content = path.read_text(encoding="utf-8")
    assert "FACTION_PRIORITY = ['republic', 'cis'" in content, (
        "FACTION_PRIORITY should have CW codes first"
    )
    # Legacy codes should still be in the list (back-compat)
    assert "'rebel', 'empire'" in content, (
        "Legacy GCW codes should remain in FACTION_PRIORITY for back-compat"
    )
