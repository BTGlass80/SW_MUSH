#!/usr/bin/env python3
"""Fix self._influence -> self._zones in engine/director.py"""
import ast, shutil, sys
from pathlib import Path

DIR = Path("engine/director.py")
if not DIR.exists():
    print(f"ERROR: {DIR} not found."); sys.exit(1)

src = DIR.read_text(encoding="utf-8")
count = src.count("self._influence")
if count == 0:
    print("OK: no self._influence references found — already clean")
    sys.exit(0)

patched = src.replace("self._influence", "self._zones")
try:
    ast.parse(patched)
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}"); sys.exit(1)

shutil.copy2(DIR, DIR.with_suffix(".py.inf_bak"))
DIR.write_text(patched, encoding="utf-8")
print(f"OK: replaced {count} self._influence -> self._zones in engine/director.py")
