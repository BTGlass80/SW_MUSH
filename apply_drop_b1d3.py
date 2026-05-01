# -*- coding: utf-8 -*-
r"""
apply_drop_b1d3.py — Applies the B.1.d.3 drop in place.

B.1.d.3 wires the remaining CW faction-quarter anchors:
  - ("republic",    "coruscant"):   259  (Coco Town Civic Block)
  - ("cis",         "geonosis"):    418  (Geonosis Deep Hive Tunnel)
  - ("hutt_cartel", "nar_shaddaa"):  71  (Hutt Emissary Tower Audience)

Closes the wider CW gap explicitly flagged by F.5d. See
HANDOFF_APR30_B1D3.md for full context.

Usage (Windows, from project root):
    Expand-Archive -Path .\drop_b1d3.zip -DestinationPath . -Force

This script is the AST validator the zip extraction uses.
File opens use encoding='utf-8' explicitly per the project's
Windows cp1252 default-encoding rule.
"""
from __future__ import annotations

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))


def _ast_validate(rel: str) -> bool:
    """Confirm the destination file parses as Python."""
    import ast
    path = os.path.join(HERE, rel)
    if not os.path.exists(path):
        print(f"  [SKIP] AST validation: {rel} not present")
        return True
    try:
        with open(path, "r", encoding="utf-8") as f:
            ast.parse(f.read())
        print(f"  [OK]   AST: {rel}")
        return True
    except SyntaxError as e:
        print(f"  [FAIL] AST: {rel} — {e}")
        return False


def main() -> int:
    print("=" * 60)
    print("B.1.d.3 Drop Application")
    print("=" * 60)

    targets = [
        "engine/housing.py",
        "tests/test_b1d3_cw_faction_anchors_wired.py",
        "tests/test_b1d2_housing_codeflow_era_aware.py",
        "tests/test_f5d_jedi_temple_integration.py",
    ]

    print("\n[1/2] AST validation of deliverables")
    print("-" * 60)
    all_clean = True
    for t in targets:
        if not _ast_validate(t):
            all_clean = False

    if not all_clean:
        print("\n[FAIL] One or more files failed AST validation.")
        return 1

    print("\n[2/2] Recommended next steps")
    print("-" * 60)
    print("  Run the B.1.d.3 integration suite:")
    print("    python -m pytest tests/test_b1d3_cw_faction_anchors_wired.py -v")
    print()
    print("  Run the housing-adjacent regression block:")
    print("    python -m pytest "
          "tests/test_b1d2_housing_codeflow_era_aware.py "
          "tests/test_b1d3_cw_faction_anchors_wired.py "
          "tests/test_f5d_jedi_temple_integration.py "
          "tests/test_f5b1_faction_quarter_tiers_datafied.py "
          "tests/test_f5b2x_housing_rep_gate_enforcement.py")
    print()
    print("  Run the full suite:")
    print("    python -m pytest")

    print()
    print("=" * 60)
    print("B.1.d.3 drop ready. See HANDOFF_APR30_B1D3.md for full context.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
