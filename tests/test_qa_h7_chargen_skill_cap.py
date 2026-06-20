# -*- coding: utf-8 -*-
"""QA H7 — in-game (telnet) chargen wizard must enforce the WEG R&E
2D-per-skill creation cap, matching the web validator.

Before this fix, `engine.creation.CreationEngine._cmd_skill` checked only
that the bonus was at least +1 pip; a telnet player could `skill blaster 5D`
and persist an illegal stat. `_validate()` (the finalize gate) also had no
per-skill cap, so template/undo paths that set skills directly were
unguarded. The web path (`engine.chargen_validator`) already enforced the
cap — this brings the in-game wizard to parity using the same constant.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from engine.dice import DicePool
from engine.character import SkillRegistry
from engine.species import SpeciesRegistry
from engine.creation import CreationEngine
from engine.chargen_validator import MAX_SKILL_BONUS_PIPS


@pytest.fixture(scope="module")
def regs():
    skill_reg = SkillRegistry()
    skill_reg.load_file(str(PROJECT_ROOT / "data" / "skills.yaml"))
    species_reg = SpeciesRegistry()
    species_reg.load_directory(str(PROJECT_ROOT / "data" / "species"))
    return species_reg, skill_reg


@pytest.fixture
def engine(regs):
    species_reg, skill_reg = regs
    return CreationEngine(species_reg, skill_reg)


def test_cap_constant_is_2d():
    # 2D = 6 pips; the in-game wizard imports the same source of truth
    # the web validator uses, so they can never drift.
    assert MAX_SKILL_BONUS_PIPS == 6


def test_skill_at_cap_accepted(engine):
    msg, _, done = engine.process_input("skill blaster 2D")
    assert not done
    assert "exceeds" not in msg.lower()
    assert engine.state.skills.get("blaster") == DicePool(2, 0)


def test_skill_over_cap_rejected_and_not_stored(engine):
    msg, _, done = engine.process_input("skill blaster 3D")
    assert not done
    assert "exceeds" in msg.lower() or "cap" in msg.lower()
    # the illegal bonus must NOT have been stored
    assert "blaster" not in engine.state.skills


def test_skill_one_pip_over_cap_rejected(engine):
    # 2D+1 = 7 pips, just over the 6-pip cap — the boundary that matters
    msg, _, _ = engine.process_input("skill blaster 2D+1")
    assert "exceeds" in msg.lower() or "cap" in msg.lower()
    assert "blaster" not in engine.state.skills


def test_validate_flags_skill_set_directly_over_cap(engine):
    # Simulate a template/undo path that writes self.state.skills directly,
    # bypassing _cmd_skill. _validate() is the finalize authority and must
    # still catch it.
    engine.state.skills["blaster"] = DicePool(5, 0)  # 5D — way over cap
    errors = engine._validate()
    assert any("exceeds creation cap" in e.lower() or "2d" in e.lower()
               for e in errors), errors


def test_validate_passes_skill_at_cap(engine):
    # A skill exactly at 2D must NOT raise the per-skill cap error.
    engine.state.skills["blaster"] = DicePool(2, 0)
    errors = engine._validate()
    assert not any("creation cap" in e.lower() for e in errors), errors


def test_done_blocked_when_skill_over_cap(engine):
    # End-to-end: an over-cap skill set directly must block finalize.
    engine.state.skills["blaster"] = DicePool(4, 0)
    msg, _, done = engine.process_input("done")
    assert not done
    assert "cannot finalize" in msg.lower()
