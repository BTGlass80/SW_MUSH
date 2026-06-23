# -*- coding: utf-8 -*-
"""
tests/test_fork_space_skill_registry_2026_06_23.py — space skill-check registry fix.

Resolves SPACE.load_default_does_not_exist. `parser/space_commands.py` called
`sr.load_default()` at 8 sites, but SkillRegistry has no such method -> every call
raised AttributeError. Effect: 3 commands (`+ship/install`, `order`,
`transponder false`) silently NO-OP'd; 5 (scan / deepscan / hyperspace / salvage /
customs) fell to a `result is None` fallback and BYPASSED their skill gate (free
scans, guaranteed jumps, free salvage, smugglers never caught). The fix routes all
8 to the process-cached `get_cached_skill_registry()` (loaded once, off the event
loop). Swapping in a real result also UNMASKED a second bug at deepscan + salvage,
which read `result.critical` / `result.total` -- attributes SkillCheckResult does
NOT have (it has `.critical_success` / `.roll`); those are corrected and made
fail-CLOSED (an engine error no longer auto-succeeds).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "parser" / "space_commands.py").read_text(encoding="utf-8")


class TestNoBrokenRegistryLoad:
    def test_load_default_is_gone(self):
        assert "load_default" not in SRC, \
            "load_default() does not exist on SkillRegistry — must use the cached registry"

    def test_cached_registry_is_imported_and_used(self):
        assert "from engine.character import get_cached_skill_registry" in SRC
        # the 8 former load_default sites + the 5 pre-existing = many cached calls
        assert SRC.count("get_cached_skill_registry()") >= 13


class TestDeepscanSalvageAttrFix:
    def test_no_skillcheck_total_or_bare_critical(self):
        # the SkillCheckResult misuse the registry fix unmasked
        assert "result.critical if result else False" not in SRC
        assert "result.total >= _DIFF" not in SRC and "result.total >= diff" not in SRC

    def test_deepscan_salvage_use_correct_attrs_failclosed(self):
        assert SRC.count("result.critical_success if result else False") == 2
        assert "(result is not None and result.roll >= _DIFF)" in SRC   # deepscan
        assert "(result is not None and result.roll >= diff)" in SRC    # salvage
        # the valid, different result types must be left alone
        assert "roll_result.total" in SRC          # roll_d6_pool result (.total is valid)
        assert "if result.critical else" in SRC    # MINE result (.critical is valid)


class TestSkillCheckResultContract:
    def test_cached_registry_loaded_and_result_has_roll_not_total(self):
        from engine.character import get_cached_skill_registry
        from engine.skill_checks import perform_skill_check
        sr = get_cached_skill_registry()
        assert sr is not None
        char = {"id": 1, "skills": json.dumps({}),
                "attributes": json.dumps({"dexterity": "2D", "knowledge": "2D",
                                          "mechanical": "2D", "perception": "2D",
                                          "strength": "2D", "technical": "2D"})}
        # the governing skills behind the 8 fixed commands
        for skill, diff in (("sensors", 8), ("technical", 15), ("command", 8),
                            ("con", 8), ("astrogation", 10)):
            r = perform_skill_check(char, skill, diff, sr)
            assert r is not None, f"{skill}: no result"
            assert hasattr(r, "roll") and hasattr(r, "success") \
                and hasattr(r, "critical_success"), f"{skill}: missing real attrs"
            assert not hasattr(r, "total"), f"{skill}: SkillCheckResult should not have .total"
            assert not hasattr(r, "critical"), f"{skill}: should not have .critical"


if __name__ == "__main__":
    import sys, pytest
    sys.exit(pytest.main([__file__, "-v"]))
