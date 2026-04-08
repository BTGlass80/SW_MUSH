#!/usr/bin/env python3
"""
patches/patch_cp_wire.py  --  Drop 4 of CP Progression system.

Wires into server/game_server.py:
  1. Adds imports for entertainer_commands and cp_commands
  2. Adds register_entertainer_commands + register_cp_commands calls
  3. Adds CP engine tick to the game tick loop

Also fixes the missing entertainer wire (register_entertainer_commands was
never called despite the file existing since the Opus session).

Run from project root:
    python patches/patch_cp_wire.py
"""

import sys
import shutil
import ast
from pathlib import Path

TARGET = Path("server/game_server.py")
BACKUP = Path("server/game_server.py.bak_cp")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def apply(src: str, old: str, new: str, label: str) -> str:
    """Try exact match, then LF-normalised match."""
    if old in src:
        return src.replace(old, new, 1)
    old_lf = old.replace("\r\n", "\n")
    src_lf = src.replace("\r\n", "\n")
    if old_lf in src_lf:
        return src_lf.replace(old_lf, new, 1)
    print(f"ERROR: anchor not found for: {label}")
    print(f"  Expected to find:\n{repr(old[:120])}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    shutil.copy(TARGET, BACKUP)
    print(f"Backup: {BACKUP}")

    src = read(TARGET)

    # ── Change 1: add imports ─────────────────────────────────────────────────
    old_imports = "from parser.medical_commands import register_medical_commands\n"
    new_imports = (
        "from parser.medical_commands import register_medical_commands\n"
        "from parser.entertainer_commands import register_entertainer_commands\n"
        "from parser.cp_commands import register_cp_commands\n"
    )
    src = apply(src, old_imports, new_imports, "import block")
    print("  [1/3] Imports added (entertainer + cp)")

    # ── Change 2: add registrations ───────────────────────────────────────────
    old_reg = "        register_medical_commands(self.registry)\n"
    new_reg = (
        "        register_medical_commands(self.registry)\n"
        "        register_entertainer_commands(self.registry)\n"
        "        register_cp_commands(self.registry)\n"
    )
    src = apply(src, old_reg, new_reg, "registration block")
    print("  [2/3] Registrations added (entertainer + cp)")

    # ── Change 3: add CP tick after Director tick ─────────────────────────────
    old_tick = (
        '                log.debug("Director tick skipped", exc_info=True)\n'
    )
    new_tick = (
        '                log.debug("Director tick skipped", exc_info=True)\n'
        '            # \u2500\u2500 CP Progression tick \u2500\u2500\n'
        '            try:\n'
        '                from engine.cp_engine import get_cp_engine\n'
        '                await get_cp_engine().tick(self.db, self.session_mgr)\n'
        '            except Exception:\n'
        '                log.debug("CP engine tick skipped", exc_info=True)\n'
    )
    src = apply(src, old_tick, new_tick, "CP tick insertion")
    print("  [3/3] CP engine tick added to game tick loop")

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        ast.parse(src)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  AST FAIL: {e}")
        sys.exit(1)

    write(TARGET, src)
    print(f"\nPatch applied successfully → {TARGET}")
    print("New commands: cpstatus, train, kudos, scenebonus, perform")


if __name__ == "__main__":
    main()
