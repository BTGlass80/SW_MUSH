# -*- coding: utf-8 -*-
"""tests/test_qa_h7_launch_closeout.py — launch close-out regressions (2026-06-20).

H7: the telnet/in-game chargen wizard (engine/creation.py) never enforced the WEG
R&E 2D per-skill creation cap (only the web chargen_validator did), so a player
could persist illegal >2D skills. Plus two go-live hardening fixes: a durable
Director monthly-budget backstop (engine/director.py) and the in-client fan
disclaimer (static/client.html).
"""
from __future__ import annotations

import os

from engine.character import SkillRegistry
from engine.species import SpeciesRegistry
from engine.creation import CreationEngine

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _engine() -> CreationEngine:
    skill_reg = SkillRegistry()
    skill_reg.load_file(os.path.join(REPO_ROOT, "data", "skills.yaml"))
    species_reg = SpeciesRegistry()
    species_reg.load_directory(os.path.join(REPO_ROOT, "data", "species"))
    return CreationEngine(species_reg, skill_reg)


def _src(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── H7: telnet chargen 2D per-skill cap (functional) ─────────────────────────

def test_h7_skill_over_2D_rejected():
    out, _prompt, _done = _engine().process_input("skill blaster 3D")  # 3D bonus > 2D cap
    assert "2d" in out.lower() and ("exceed" in out.lower() or "cap" in out.lower()), (
        f"H7: a +3D skill bonus must be rejected at creation; got: {out!r}"
    )


def test_h7_skill_at_2D_allowed():
    eng = _engine()
    out, _prompt, _done = eng.process_input("skill blaster 2D")  # exactly 2D = the cap
    assert "exceed" not in out.lower(), f"H7: +2D is the legal cap, must be allowed; got: {out!r}"
    assert "blaster" in eng.state.skills, "H7: a legal +2D skill should be recorded"


def test_h7_cap_present_in_both_chargen_paths():
    s = _src("engine/creation.py")
    assert "MAX_SKILL_BONUS_PIPS" in s, "H7: telnet wizard must reference the creation cap"
    assert s.count("MAX_SKILL_BONUS_PIPS") >= 2, "H7: cap must guard both _cmd_skill and _validate"


# ── Director durable monthly-budget backstop ─────────────────────────────────

def test_director_durable_budget_backstop():
    s = _src("engine/director.py")
    assert "get_budget_stats(db)" in s, "durable budget pre-check missing"
    assert "_cap_cents * 0.9" in s, "budget backstop must gate at the 90% breaker threshold"


# ── In-client fan disclaimer (boot + login pre-auth screens) ─────────────────

def test_client_fan_disclaimer_present():
    s = _src("static/client.html")
    n = s.count("not affiliated with Lucasfilm")
    assert n >= 2, f"in-client fan disclaimer must appear on boot + login screens (found {n})"
