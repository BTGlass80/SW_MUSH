# -*- coding: utf-8 -*-
r"""
apply_drop_f5d.py — Applies the F.5d drop in place.

F.5d wires ("jedi_order", "coruscant"): 211 into FACTION_QUARTER_LOTS
so Jedi PC rank promotion creates real Temple quarters instead of
hitting the soft-bail path. See HANDOFF_APR30_F5D.md for full context.

Usage (Windows, from project root):
    Expand-Archive -Path .\drop_f5d.zip -DestinationPath . -Force

This script is the file-mover the zip extraction uses.
File opens use encoding='utf-8' explicitly per the project's
Windows cp1252 default-encoding rule.
"""
from __future__ import annotations

import os
import shutil
import sys


HERE = os.path.dirname(os.path.abspath(__file__))


def _copy(src_rel: str, dst_rel: str) -> None:
    src = os.path.join(HERE, src_rel)
    dst = os.path.join(HERE, dst_rel)
    if not os.path.exists(src):
        print(f"  [SKIP] source not present: {src_rel}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"  [OK]   {src_rel} -> {dst_rel}")


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
    print("F.5d Drop Application")
    print("=" * 60)

    # The zip puts files in a staging tree; the apply script copies
    # them in place. If the zip extracts directly over the project
    # root (Expand-Archive -Force), no copy is needed — the files
    # are already where they belong. This script's main job is to
    # AST-validate the deliverables.

    targets = [
        "engine/housing.py",
        "tests/test_f5d_jedi_temple_integration.py",
        "tests/test_b1d2_housing_codeflow_era_aware.py",
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
    print("  Run the F.5d integration suite:")
    print("    python -m pytest tests/test_f5d_jedi_temple_integration.py -v")
    print()
    print("  Run the housing-adjacent regression block:")
    print("    python -m pytest tests/test_b1d2_housing_codeflow_era_aware.py "
          "tests/test_f5b1_faction_quarter_tiers_datafied.py "
          "tests/test_f5b2x_housing_rep_gate_enforcement.py "
          "tests/test_f5d_jedi_temple_integration.py")
    print()
    print("  Run the full suite:")
    print("    python -m pytest")

    print()
    print("=" * 60)
    print("F.5d drop ready. See HANDOFF_APR30_F5D.md for full context.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
