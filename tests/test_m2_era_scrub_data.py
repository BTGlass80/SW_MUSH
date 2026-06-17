"""
test_m2_era_scrub_data.py — M2 era-cleanness: extend era-scrub to data/help/ and data/guides/.

QA finding M2 (2026-06-16): the era-scrub test (test_static_era_scrub.py) only swept
static/*.html, letting B3 violations slip into player-facing help and guide files:
  - data/help/commands/+events.md "Rebel Strike Planning" (fixed this drop)
  - data/help/commands/+gunner.md "TIE-3" / "TIE Bomber" (fixed this drop)
  - data/help/commands/+crew.md "TIE-Alpha" (fixed this drop)
  - data/help/commands/+smuggle.md "ISB cares" (fixed this drop)
  - data/worlds/clone_wars/planets/coruscant.yaml room 237 "resistance organization" (fixed)

This file sweeps data/help/**/*.md and data/guides/**/*.md and will catch future drift.

Allowlists:
- Lines that contain the marker '<!-- lint-era-ok -->' (deliberate foreshadowing with explicit comment).
- The WEG D6 scale-18 "Death Star scale" table row (canonical game-mechanics reference,
  explicitly noted "no such weapon exists in the Clone Wars era" on the same line).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

ERA_CONTAMINATION_PATTERN = re.compile(
    r"\b("
    r"Empire|Imperial|Rebel|Rebellion|Stormtrooper|"
    r"TIE/|TIE-|X-wing|X-Wing|Vader|Death Star|"
    r"ISB|Imperial Security Bureau|stormtroop"
    r")\b"
)

LINT_ERA_OK = "lint-era-ok"
WEG_SCALE_REF = "Death Star scale"


def _is_allowlisted(line: str) -> bool:
    """True if this line is an approved era-contamination exception."""
    if LINT_ERA_OK in line:
        return True
    # WEG D6 scale-18 mechanics table row — lore-only reference, not a real weapon.
    if WEG_SCALE_REF in line and "no such weapon exists" in line:
        return True
    return False


def _collect_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.md"))


def _check_dir(directory: Path) -> list[str]:
    """Return a list of violation descriptions for all .md files under directory."""
    violations: list[str] = []
    for path in _collect_files(directory):
        rel = path.relative_to(REPO_ROOT)
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ERA_CONTAMINATION_PATTERN.search(raw) and not _is_allowlisted(raw):
                violations.append(f"  {rel}:{lineno}: {raw.strip()[:120]}")
    return violations


def test_no_era_contamination_in_help() -> None:
    """No Imperial/Rebel/TIE era contamination in data/help/**/*.md."""
    directory = REPO_ROOT / "data" / "help"
    assert directory.exists(), f"data/help/ not found at {directory}"
    violations = _check_dir(directory)
    if violations:
        pytest.fail(
            "Era contamination in data/help/ (B3 violation):\n" + "\n".join(violations)
        )


def test_no_era_contamination_in_guides() -> None:
    """No Imperial/Rebel/TIE era contamination in data/guides/**/*.md."""
    directory = REPO_ROOT / "data" / "guides"
    assert directory.exists(), f"data/guides/ not found at {directory}"
    violations = _check_dir(directory)
    if violations:
        pytest.fail(
            "Era contamination in data/guides/ (B3 violation):\n"
            + "\n".join(violations)
        )


def test_help_count_nonzero() -> None:
    """Sanity: data/help/ must contain at least 50 .md files (regression guard)."""
    files = _collect_files(REPO_ROOT / "data" / "help")
    assert len(files) >= 50, f"Expected >=50 help files, found {len(files)}"


def test_guides_count_nonzero() -> None:
    """Sanity: data/guides/ must contain at least 10 .md files (regression guard)."""
    files = _collect_files(REPO_ROOT / "data" / "guides")
    assert len(files) >= 10, f"Expected >=10 guide files, found {len(files)}"


# ── Regression tests for the specific M2 fixes ───────────────────────────────

def test_events_no_rebel_strike() -> None:
    """data/help/commands/+events.md must not contain 'Rebel Strike Planning'."""
    path = REPO_ROOT / "data" / "help" / "commands" / "+events.md"
    assert path.exists(), f"+events.md not found"
    assert "Rebel Strike Planning" not in path.read_text(encoding="utf-8"), (
        "Era-contaminated event name 'Rebel Strike Planning' still present in +events.md"
    )


def test_gunner_no_tie_refs() -> None:
    """data/help/commands/+gunner.md must not contain TIE- ship references."""
    path = REPO_ROOT / "data" / "help" / "commands" / "+gunner.md"
    assert path.exists(), f"+gunner.md not found"
    content = path.read_text(encoding="utf-8")
    assert "TIE-" not in content, "Era-contaminated 'TIE-' ship name in +gunner.md"
    assert "TIE Bomber" not in content, "Era-contaminated 'TIE Bomber' in +gunner.md"


def test_crew_no_tie_refs() -> None:
    """data/help/commands/+crew.md must not contain TIE- ship references."""
    path = REPO_ROOT / "data" / "help" / "commands" / "+crew.md"
    assert path.exists(), f"+crew.md not found"
    assert "TIE-" not in path.read_text(encoding="utf-8"), (
        "Era-contaminated 'TIE-' ship name in +crew.md"
    )


def test_smuggle_no_isb() -> None:
    """data/help/commands/+smuggle.md must not reference ISB."""
    path = REPO_ROOT / "data" / "help" / "commands" / "+smuggle.md"
    assert path.exists(), f"+smuggle.md not found"
    assert "ISB" not in path.read_text(encoding="utf-8"), (
        "Era-contaminated 'ISB' (Imperial Security Bureau) in +smuggle.md"
    )


def test_coruscant_no_resistance_org() -> None:
    """coruscant.yaml room 237 must not use the Sequel-era 'resistance organization' phrasing."""
    path = REPO_ROOT / "data" / "worlds" / "clone_wars" / "planets" / "coruscant.yaml"
    assert path.exists(), f"coruscant.yaml not found"
    assert "resistance organization" not in path.read_text(encoding="utf-8"), (
        "Sequel-era 'resistance organization' phrasing still in coruscant.yaml room 237"
    )
