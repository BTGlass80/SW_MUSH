#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_director_commands_patch.py
Run from the SW_MUSH project root:
    python patches/fix_director_commands_patch.py
"""
import ast, shutil, sys
from pathlib import Path

NEW_CONTENT = """ + repr(new_content) + """

DC = Path("parser/director_commands.py")
DIR = Path("engine/director.py")

for f in (DC, DIR):
    if not f.exists():
        print(f"ERROR: {f} not found. Run from project root.")
        sys.exit(1)

# Patch 1: rewrite director_commands.py
try:
    ast.parse(NEW_CONTENT)
except SyntaxError as e:
    print(f"ERROR in new content: {e}"); sys.exit(1)

shutil.copy2(DC, DC.with_suffix(".py.cmd_bak"))
DC.write_text(NEW_CONTENT, encoding="utf-8")
print("OK parser/director_commands.py rewritten")

# Patch 2: self._influence -> self._zones in director.py
src = DIR.read_text(encoding="utf-8")
count = src.count("self._influence")
if count == 0:
    print("OK engine/director.py: already clean")
else:
    patched = src.replace("self._influence", "self._zones")
    try:
        ast.parse(patched)
    except SyntaxError as e:
        print(f"ERROR: director.py syntax error: {e}"); sys.exit(1)
    shutil.copy2(DIR, DIR.with_suffix(".py.inf_bak"))
    DIR.write_text(patched, encoding="utf-8")
    print(f"OK engine/director.py: {count} self._influence -> self._zones")

print()
print("Done. Restart: python main.py")
print("Then: @director enable")
