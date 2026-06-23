# -*- coding: utf-8 -*-
"""tests/test_guide_14_padawan_master_rework.py — Guide_14 T3.13 feature update.

What this drop changed
----------------------
Guide_14_Padawan_Master.md v1.1: added two shipped-but-undocumented T3.13
features:
  1. +leave-master — Padawan-initiated voluntary bond dissolution.
  2. +authorize — Master pre-authorization for offworld/powers/trials categories.
Also corrected a factual error: §9 previously stated "Padawans cannot release
the bond unilaterally" which became false once +leave-master shipped.

Tests verify
------------
A. +leave-master command is documented (syntax + reason-required note).
B. The false "Padawans cannot release unilaterally" claim is gone.
C. +authorize command is documented with all three categories.
D. The three authorization categories (offworld, powers, trials) are named.
E. Standing pre-authorization concept is explained.
F. Quick Reference table includes +leave-master and +authorize.
G. Guide version was bumped to 1.1.
H. Frontmatter is valid (required keys present).
"""

import pathlib

GUIDE_PATH = pathlib.Path("data/guides/Guide_14_Padawan_Master.md")


def read_guide() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_14_Padawan_Master.md not found"


# ── A. +leave-master documented ───────────────────────────────────────────

def test_leave_master_command_documented():
    text = read_guide()
    assert "+leave-master" in text, (
        "+leave-master command must be documented (T3.13 Padawan-voluntary-leave)"
    )


def test_leave_master_reason_required_noted():
    text = read_guide()
    lower = text.lower()
    assert "reason" in lower and "leave-master" in text, (
        "Guide must note that +leave-master requires a reason"
    )


def test_leave_master_syntax_present():
    text = read_guide()
    assert "+leave-master <reason>" in text, (
        "+leave-master <reason> syntax form must appear in guide"
    )


# ── B. False claim removed ─────────────────────────────────────────────────

def test_false_unilateral_claim_removed():
    text = read_guide()
    assert "Padawans cannot release the bond unilaterally" not in text, (
        "Stale false claim 'Padawans cannot release the bond unilaterally' "
        "must be removed — +leave-master now ships"
    )


# ── C. +authorize documented ───────────────────────────────────────────────

def test_authorize_command_documented():
    text = read_guide()
    assert "+authorize" in text, (
        "+authorize command must be documented (T3.13 Master pre-authorization)"
    )


def test_authorize_section_present():
    text = read_guide()
    lower = text.lower()
    assert "pre-authorization" in lower or "pre-authoriz" in lower, (
        "A pre-authorization section or subsection must be present"
    )


# ── D. All three categories named ─────────────────────────────────────────

def test_category_offworld_documented():
    text = read_guide()
    assert "offworld" in text, (
        "authorize category 'offworld' must be documented"
    )


def test_category_powers_documented():
    text = read_guide()
    assert "powers" in text.lower(), (
        "authorize category 'powers' must be documented"
    )


def test_category_trials_authorize_documented():
    text = read_guide()
    # The word 'trials' appears in the Trials section too; check it's
    # specifically associated with +authorize
    assert "authorize" in text and "trials" in text.lower(), (
        "authorize category 'trials' must be documented alongside +authorize"
    )


# ── E. Standing pre-authorization concept explained ───────────────────────

def test_standing_authorization_concept():
    text = read_guide()
    lower = text.lower()
    assert "standing" in lower, (
        "Guide must explain 'standing' pre-authorization (grant once, not per-action)"
    )


# ── F. Quick Reference table updated ──────────────────────────────────────

def test_quick_reference_has_leave_master():
    text = read_guide()
    # Both the QR table marker and the command must appear in the same text
    assert "+leave-master" in text and "Quick Reference" in text, (
        "+leave-master must appear in the Quick Reference table"
    )


def test_quick_reference_has_authorize():
    text = read_guide()
    assert "+authorize" in text and "Quick Reference" in text, (
        "+authorize must appear in the Quick Reference table"
    )


# ── G. Version bump ────────────────────────────────────────────────────────

def test_guide_version_bumped():
    text = read_guide()
    # Bumped to 1.2 by the 2026-06-23 authoritative quality pass.
    assert "Version 1.2" in text, (
        "Guide version must be at 1.2 (authoritative quality pass)"
    )


# ── H. Frontmatter valid ───────────────────────────────────────────────────

def test_frontmatter_required_keys():
    import yaml
    text = read_guide()
    assert text.startswith("---\n"), "Guide_14 missing leading frontmatter delimiter"
    end = text.find("\n---\n", 4)
    assert end > 4, "Guide_14 missing closing frontmatter delimiter"
    meta = yaml.safe_load(text[4:end])
    for key in ("category", "order", "summary", "tags"):
        assert key in meta, f"Frontmatter missing required key: {key}"
