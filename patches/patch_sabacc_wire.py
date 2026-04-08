#!/usr/bin/env python3
"""
patches/patch_sabacc_wire.py  --  Wire sabacc_commands into game_server.py.

Run from project root:
    python patches/patch_sabacc_wire.py
"""

import sys
import shutil
import ast
from pathlib import Path

TARGET = Path("server/game_server.py")
BACKUP = Path("server/game_server.py.bak_sabacc")


def read(p):  return p.read_text(encoding="utf-8")
def write(p, t): p.write_text(t, encoding="utf-8")


def apply(src, old, new, label):
    if old in src:
        return src.replace(old, new, 1)
    old_lf = old.replace("\r\n", "\n")
    src_lf = src.replace("\r\n", "\n")
    if old_lf in src_lf:
        return src_lf.replace(old_lf, new, 1)
    print(f"ERROR: anchor not found for: {label}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    shutil.copy(TARGET, BACKUP)
    print(f"Backup: {BACKUP}")

    src = read(TARGET)

    # ── Import ────────────────────────────────────────────────────────────────
    src = apply(
        src,
        "from parser.cp_commands import register_cp_commands\n",
        "from parser.cp_commands import register_cp_commands\n"
        "from parser.sabacc_commands import register_sabacc_commands\n",
        "sabacc import",
    )

    # ── Registration ──────────────────────────────────────────────────────────
    src = apply(
        src,
        "        register_cp_commands(self.registry)\n",
        "        register_cp_commands(self.registry)\n"
        "        register_sabacc_commands(self.registry)\n",
        "sabacc registration",
    )

    try:
        ast.parse(src)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  AST FAIL: {e}")
        sys.exit(1)

    write(TARGET, src)
    print(f"Patch applied → {TARGET}")
    print("New command: sabacc (aliases: gamble, cards)")


if __name__ == "__main__":
    main()
