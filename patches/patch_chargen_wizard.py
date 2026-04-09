#!/usr/bin/env python3
"""
Patch: Wire CreationWizard into game_server.py

Replaces the bare CreationEngine with the guided CreationWizard
in _run_character_creation(). The wizard wraps CreationEngine
internally, so all existing validation and undo logic is preserved.

Usage:
    python patches/patch_chargen_wizard.py
    (or: python patches/patch_chargen_wizard.py --dry-run)

Effects:
    1. Adds 'from engine.creation_wizard import CreationWizard' import
    2. Replaces the CreationEngine instantiation with CreationWizard
    3. All references to 'engine' local var become 'wizard'
    4. get_character() now returns a Character with force_sensitive,
       force_points, and description (background) set by the wizard.
"""
import os
import sys
import shutil
import ast

TARGET = os.path.join("server", "game_server.py")
BACKUP = TARGET + ".bak_chargen_wizard"


def read_file(path):
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Cannot read {path}")


def apply_patch(dry_run=False):
    if not os.path.isfile(TARGET):
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    source = read_file(TARGET)

    # ── Patch 1: Add import ──
    old_import = "from engine.creation import CreationEngine"
    new_import = ("from engine.creation import CreationEngine\n"
                  "from engine.creation_wizard import CreationWizard")

    if "CreationWizard" in source:
        print("  Import already present, skipping patch 1.")
    elif old_import in source:
        source = source.replace(old_import, new_import, 1)
        print("  Patch 1: Added CreationWizard import.")
    else:
        print(f"  WARNING: Could not find import anchor. Manual fix needed.")
        print(f"    Expected: {old_import}")

    # ── Patch 2: Replace CreationEngine instantiation ──
    # The method creates: engine = CreationEngine(self.species_reg, self.skill_reg)
    old_engine = "engine = CreationEngine(self.species_reg, self.skill_reg)"
    new_engine = "wizard = CreationWizard(self.species_reg, self.skill_reg)"

    if new_engine in source:
        print("  Instantiation already patched, skipping patch 2.")
    elif old_engine in source:
        source = source.replace(old_engine, new_engine, 1)
        print("  Patch 2: Replaced CreationEngine with CreationWizard.")
    else:
        print(f"  WARNING: Could not find engine instantiation anchor.")

    # ── Patch 3: Replace 'engine.' references in _run_character_creation ──
    # We need to be surgical — only replace within this method, not globally.
    # The method uses 'engine.get_initial_display()', 'engine.process_input()',
    # 'engine.get_character()' — all of which exist on CreationWizard.

    # Find the method boundaries
    method_start = source.find("async def _run_character_creation")
    if method_start == -1:
        print("  WARNING: Could not find _run_character_creation method.")
    else:
        # Find the next method (next 'async def' or 'def' at the same indent)
        next_method = source.find("\n    async def ", method_start + 10)
        if next_method == -1:
            next_method = len(source)

        method_body = source[method_start:next_method]

        # Only replace if we haven't already patched
        if "wizard." not in method_body and "engine." in method_body:
            patched_body = method_body.replace("engine.", "wizard.")
            # But DON'T replace 'engine.' in the dice engine or other refs
            # These are local variable refs so they should all be our wizard
            source = source[:method_start] + patched_body + source[next_method:]
            print("  Patch 3: Replaced 'engine.' → 'wizard.' in method body.")
        elif "wizard." in method_body:
            print("  Method already patched, skipping patch 3.")

    # ── Validate ──
    try:
        ast.parse(source)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  ERROR: AST validation failed: {e}")
        print("  Patch NOT applied.")
        sys.exit(1)

    if dry_run:
        print("\n  DRY RUN — no files modified.")
        # Show a diff-like preview of key changes
        for line_no, line in enumerate(source.splitlines(), 1):
            if "CreationWizard" in line or "wizard =" in line:
                print(f"    L{line_no}: {line.strip()}")
        return

    # ── Apply ──
    shutil.copy2(TARGET, BACKUP)
    print(f"  Backup: {BACKUP}")

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(source)
    print(f"  Written: {TARGET}")
    print("  Done!")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    apply_patch(dry_run=dry_run)
