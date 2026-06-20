# -*- coding: utf-8 -*-
"""
QA HIGH (phantom-import family, 2026-06-19) regression guard.

Four NPC bargain/gambling call sites read an NPC's dice-code off its
char_sheet_json via `from engine.skill_checks import _parse_dice_str`:

  - parser/sabacc_commands.py     (dealer gambling pool)
  - parser/builtin_commands.py    (vendor bargain, ×2)
  - parser/space_commands.py      (planet vendor bargain)

But `_parse_dice_str` lived ONLY in engine.lightsaber_construction, so
every one of those imports raised ImportError, was swallowed by the
surrounding `except Exception`, and the NPC pool silently fell back to a
flat default (DEALER dice / 3D). The fix gives the function its canonical
home in engine.skill_checks (the module the callers already targeted) and
dedupes lightsaber_construction onto it. These tests pin both halves so
the phantom import can't silently regress.
"""
import ast
import importlib

import pytest


def test_skill_checks_exports_parse_dice_str():
    """The canonical home resolves — this is the import every call site does."""
    from engine.skill_checks import _parse_dice_str  # must not raise ImportError
    assert callable(_parse_dice_str)


def test_single_source_of_truth():
    """lightsaber_construction re-exports the SAME object — no duplicate impl."""
    from engine.skill_checks import _parse_dice_str as canonical
    from engine.lightsaber_construction import _parse_dice_str as relocated
    assert relocated is canonical


@pytest.mark.parametrize("raw,expected", [
    ("3D", (3, 0)),
    ("3D+1", (3, 1)),
    ("3D+2", (3, 2)),
    ("+2D", (2, 0)),       # some sheets store a leading '+'
    ("4D", (4, 0)),
    ("4", (4, 0)),         # bare integer = dice
    ("", (0, 0)),
    (None, (0, 0)),
    ("garbage", (0, 0)),
    ("3D+", (3, 0)),       # trailing '+' with no pips
    ("  5d+3  ", (5, 3)),  # whitespace + lowercase tolerated
])
def test_parse_cases(raw, expected):
    from engine.skill_checks import _parse_dice_str
    assert _parse_dice_str(raw) == expected


def test_call_sites_reference_skill_checks_not_lightsaber():
    """Guard against a future edit re-pointing the import at a module that
    doesn't export it (the original bug). Every `_parse_dice_str` import in
    the four call sites must target engine.skill_checks."""
    import parser.sabacc_commands as m1
    import parser.builtin_commands as m2
    import parser.space_commands as m3
    seen = 0
    for mod in (m1, m2, m3):
        src = open(mod.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names = {a.name for a in node.names}
                if "_parse_dice_str" in names:
                    seen += 1
                    assert node.module == "engine.skill_checks", (
                        f"{mod.__name__} imports _parse_dice_str from "
                        f"{node.module!r}, not engine.skill_checks"
                    )
    # sabacc ×1, builtin ×2, space ×1 = 4 import statements
    assert seen == 4, f"expected 4 _parse_dice_str imports, found {seen}"


def test_call_site_modules_import_clean():
    """The whole point: importing the call-site modules must not blow up."""
    for name in ("parser.sabacc_commands",
                 "parser.builtin_commands",
                 "parser.space_commands",
                 "engine.lightsaber_construction"):
        importlib.import_module(name)
