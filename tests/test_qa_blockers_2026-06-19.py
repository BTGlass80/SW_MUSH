# -*- coding: utf-8 -*-
"""tests/test_qa_blockers_2026-06-19.py — regression guards for the QA-playthrough
blocker fixes (docs/design/QA_PLAYTHROUGH_FINDINGS_2026-06-19.md, drop
qa-blockers-2026-06-19).

Source-level guards (the established test_qa_* style): each asserts the buggy
pattern is GONE and the fixed pattern is PRESENT, so the exact regression can't
silently return. Functional behavior is covered by the broader suites; these pin
the specific seams the playthrough proved broken.
"""
from __future__ import annotations

import ast
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _parses(rel: str) -> None:
    ast.parse(_src(rel), filename=rel)


# ── B1: train / NPC trainer crash (Character.from_db_row -> from_db_dict) ──────

def test_b1_cp_commands_uses_from_db_dict():
    s = _src("parser/cp_commands.py")
    assert "Character.from_db_row(" not in s, "B1 regressed: from_db_row is phantom"
    assert "Character.from_db_dict(" in s


def test_b1_npc_commands_uses_from_db_dict():
    s = _src("parser/npc_commands.py")
    assert "Character.from_db_row(" not in s, "B1 regressed: from_db_row is phantom"
    assert "Character.from_db_dict(" in s


# ── B2/B3: combat wound UnboundLocalError on stun-KO / soaked-on-incap ─────────

def test_b2_b3_combat_incap_lines_use_bound_word():
    s = _src("engine/combat.py")
    # The two incapacitation lines must NOT reference `wound.display_name`
    # (bound only on the damage_margin>0 branch).
    assert "wound.display_name.upper()" not in s, (
        "B2/B3 regressed: incap line references unbound wound.display_name"
    )
    assert "incap_word" in s, "B2/B3 fix missing: incap_word not defined"
    _parses("engine/combat.py")


# ── B4 + force_sensitive sweep: derive, never read the raw key ─────────────────

def test_b4_session_hud_force_sensitive_is_derived():
    s = _src("server/session.py")
    # HUD must read the derived Character property, not the raw dict key.
    assert 'bool(char.get("force_sensitive", False))' not in s, (
        "B4 regressed: HUD reads force_sensitive off the raw char dict"
    )
    assert "force_sensitive = bool(char_obj.force_sensitive)" in s


def test_force_sensitive_family_derives():
    # force_commands._is_force_being, tutorial training gate, and the lock flag
    # all derive force_sensitive via Character.from_db_dict, not the raw key.
    fc = _src("parser/force_commands.py")
    assert "return bool(row.get(\"force_sensitive\"))" not in fc
    tc = _src("parser/tutorial_commands.py")
    assert 'not char.get("force_sensitive", False)' not in tc
    lk = _src("engine/locks.py")
    assert 'return bool(char.get("force_sensitive"))' not in lk
    assert "from_db_dict" in lk


# ── B6: medical healaccept must not drive patient credits negative ─────────────

def test_b6_medical_uses_allow_negative_false():
    s = _src("parser/medical_commands.py")
    assert "allow_negative=False" in s, (
        "B6 regressed: medical charge no longer guards against negative credits"
    )
    _parses("parser/medical_commands.py")


# ── B5: housing-lot seeder maps lots to the DB id, not the YAML id ────────────

def test_b5_housing_lots_resolve_db_id():
    prov = _src("engine/housing_lots_provider.py")
    # The seed path resolves the host slug -> DB AUTOINCREMENT id (with a YAML-id
    # fallback for dry-run/test), via the existing get_room_by_slug seam.
    assert "def prime_lots_db_ids" in prov, "B5 fix missing: prime_lots_db_ids"
    assert "slug_to_db.get(host.slug, host.id)" in prov
    assert "get_room_by_slug" in prov
    hsg = _src("engine/housing.py")
    assert "await prime_lots_db_ids(db, era)" in hsg, (
        "B5 regressed: seed_lots no longer primes DB ids"
    )


# All touched modules still parse.
def test_touched_modules_parse():
    for rel in ("parser/cp_commands.py", "parser/npc_commands.py",
                "engine/combat.py", "server/session.py",
                "parser/tutorial_commands.py", "parser/force_commands.py",
                "engine/locks.py", "parser/medical_commands.py",
                "engine/housing_lots_provider.py", "engine/housing.py"):
        _parses(rel)
