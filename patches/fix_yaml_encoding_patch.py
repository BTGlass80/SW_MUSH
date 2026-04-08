#!/usr/bin/env python3
"""
fix_yaml_encoding_patch.py
--------------------------
Fixes: 'charmap' codec can't decode byte 0x90 in weapons.yaml

On Windows, open() defaults to cp1252. All YAML loaders need
encoding="utf-8". This patch fixes:
  - engine/weapons.py  (WeaponRegistry.load_file)
  - engine/starships.py (ShipTemplateRegistry.load_file)
  - engine/character.py (SkillRegistry.load_file)
  - engine/species.py   (SpeciesRegistry.load_directory)

Run from the SW_MUSH project root:
    python3 patches/fix_yaml_encoding_patch.py

Safe to re-run.
"""

import ast
import sys
from pathlib import Path

TARGETS = {
    "engine/weapons.py": {
        "old": '        with open(path) as f:\n            data = yaml.safe_load(f)',
        "new": '        with open(path, encoding="utf-8") as f:\n            data = yaml.safe_load(f)',
    },
    "engine/starships.py": {
        "old": '        with open(path) as f:\n            data = yaml.safe_load(f)',
        "new": '        with open(path, encoding="utf-8") as f:\n            data = yaml.safe_load(f)',
    },
    "engine/character.py": {
        "old": '        with open(path, "r") as f:\n            data = yaml.safe_load(f)',
        "new": '        with open(path, "r", encoding="utf-8") as f:\n            data = yaml.safe_load(f)',
    },
    "engine/species.py": {
        "old": '                    with open(filepath, "r") as f:',
        "new": '                    with open(filepath, "r", encoding="utf-8") as f:',
    },
}

patched_count = 0
for filepath, patch in TARGETS.items():
    p = Path(filepath)
    if not p.exists():
        print(f"  SKIP: {filepath} not found")
        continue

    src = p.read_text(encoding="utf-8")

    if 'encoding="utf-8"' in src and patch["old"] not in src:
        print(f"  OK: {filepath} already has utf-8 encoding")
        continue

    if patch["old"] not in src:
        print(f"  WARNING: {filepath} — anchor not found, may need manual fix")
        continue

    src = src.replace(patch["old"], patch["new"], 1)

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  ERROR: {filepath} failed syntax check after patch: {e}")
        continue

    p.write_text(src, encoding="utf-8")
    patched_count += 1
    print(f"  FIXED: {filepath}")

print(f"\n✓ Patched {patched_count} files with encoding='utf-8'")
