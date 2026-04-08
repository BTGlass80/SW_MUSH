#!/usr/bin/env python3
"""
Drop 4 — Wire patch: register medical commands in game_server.py.
Also adds 'heal', 'healaccept', 'healrate' to HelpCommand categories.

Run from project root:
    python patches/patch_wire_medical.py
"""
import os
import sys
import shutil
import ast


def read_file(path):
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def safe_replace(source, old, new, label):
    if old in source:
        return source.replace(old, new, 1), True
    old_crlf = old.replace("\n", "\r\n")
    if old_crlf in source:
        new_crlf = new.replace("\n", "\r\n")
        return source.replace(old_crlf, new_crlf, 1), True
    print(f"  [FAIL] {label} — anchor not found!")
    return source, False


def main():
    # ── Patch game_server.py ──
    target = "server/game_server.py"
    if not os.path.exists(target):
        print(f"ERROR: {target} not found. Run from project root.")
        sys.exit(1)

    source = read_file(target)
    backup = target + ".pre_medical_bak"
    if not os.path.exists(backup):
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")

    # Add import
    source, ok = safe_replace(
        source,
        "from parser.smuggling_commands import register_smuggling_commands",
        "from parser.smuggling_commands import register_smuggling_commands\n"
        "from parser.medical_commands import register_medical_commands",
        "game_server.py import"
    )
    if ok:
        print("  [OK] Added medical import")
    else:
        sys.exit(1)

    # Add registration call
    source, ok = safe_replace(
        source,
        "        register_force_commands(self.registry)",
        "        register_force_commands(self.registry)\n"
        "        register_medical_commands(self.registry)",
        "game_server.py registration"
    )
    if ok:
        print("  [OK] Added medical registration")
    else:
        sys.exit(1)

    try:
        ast.parse(source)
        print("  [OK] game_server.py ast.parse passed")
    except SyntaxError as e:
        print(f"  [FAIL] SyntaxError: {e}")
        sys.exit(1)

    with open(target, "w", encoding="utf-8") as f:
        f.write(source)
    print(f"  Written: {target}")

    # ── Patch builtin_commands.py HelpCommand categories ──
    target2 = "parser/builtin_commands.py"
    source2 = read_file(target2)
    backup2 = target2 + ".pre_medical_help_bak"
    if not os.path.exists(backup2):
        shutil.copy2(target2, backup2)
        print(f"Backup: {backup2}")

    # Add Medical category after Economy
    source2, ok = safe_replace(
        source2,
        '        "Crafting": ["survey", "resources", "buyresource",\n'
        '                      "schematics", "craft"],',
        '        "Crafting": ["survey", "resources", "buyresource",\n'
        '                      "schematics", "craft"],\n'
        '        "Medical": ["heal", "healaccept", "healrate"],',
        "HelpCommand categories"
    )
    if ok:
        print("  [OK] Added Medical category to help")
    else:
        print("  [WARN] Could not add help category (non-fatal)")

    try:
        ast.parse(source2)
        print("  [OK] builtin_commands.py ast.parse passed")
    except SyntaxError as e:
        print(f"  [FAIL] SyntaxError: {e}")
        sys.exit(1)

    with open(target2, "w", encoding="utf-8") as f:
        f.write(source2)
    print(f"  Written: {target2}")

    print("\nDone. Medical commands wired.")
    print("  Commands: heal, healaccept, healrate")


if __name__ == "__main__":
    main()
