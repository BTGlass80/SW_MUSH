#!/usr/bin/env python3
"""
Patch: creation_wizard.py — width-aware formatting, no truncation.

Changes:
  1. Replaces hardcoded W = 78 with Fmt(width) from text_format.py
  2. CreationWizard.__init__() gains an optional `width` parameter
  3. Removes all [:N] + "..." truncation in species, skills, and sheet_renderer
  4. All _wrap / _bar / _hdr calls routed through self.fmt
  5. sheet_renderer.py gains an optional `width` parameter on render functions
"""
import os
import re
import sys
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIZARD_PATH = os.path.join(ROOT, "engine", "creation_wizard.py")
SHEET_PATH  = os.path.join(ROOT, "engine", "sheet_renderer.py")
SERVER_PATH = os.path.join(ROOT, "server", "game_server.py")

DRY_RUN = "--dry-run" in sys.argv


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    if DRY_RUN:
        print(f"  [DRY RUN] Would write {len(content)} chars to {path}")
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    bak = path + ".pre_fmt_bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  Backup: {bak}")


def patch_wizard():
    """Patch creation_wizard.py for width-aware formatting."""
    src = read(WIZARD_PATH)
    backup(WIZARD_PATH)
    original = src

    # --- 1. Replace import block: add Fmt import ---
    old_import = "from server.ansi import (\n    BOLD, RESET, CYAN, YELLOW, GREEN, RED, DIM, WHITE,\n    BRIGHT_WHITE, BRIGHT_CYAN, BRIGHT_YELLOW, BRIGHT_GREEN,\n    BRIGHT_RED, BRIGHT_BLUE, BRIGHT_MAGENTA,\n)"
    new_import = """from server.ansi import (
    BOLD, RESET, CYAN, YELLOW, GREEN, RED, DIM, WHITE,
    BRIGHT_WHITE, BRIGHT_CYAN, BRIGHT_YELLOW, BRIGHT_GREEN,
    BRIGHT_RED, BRIGHT_BLUE, BRIGHT_MAGENTA,
)
from engine.text_format import Fmt"""
    if old_import in src:
        src = src.replace(old_import, new_import, 1)
        print("  [1] Added Fmt import")
    else:
        print("  [1] SKIP import (already patched or anchor mismatch)")

    # --- 2. Replace module-level W = 78 with DEFAULT_WIDTH constant ---
    src = re.sub(r'^W = 78\s*#.*$', 'DEFAULT_WIDTH = 78  # Fallback; actual width comes from Fmt', src, flags=re.MULTILINE)
    print("  [2] Replaced module-level W constant")

    # --- 3. Replace module-level helpers with Fmt-delegating versions ---
    # Replace _bar, _hdr, _dim, _yl, _gr, _cy, _mg, _bl, _wrap
    # We keep them as module-level functions for backward compat but they
    # now use DEFAULT_WIDTH and are only used as fallbacks.
    old_bar = '''def _bar(char="=", color=BRIGHT_CYAN):
    return f"{color}{char * W}{RESET}"'''
    new_bar = '''def _bar(char="=", color=BRIGHT_CYAN, width=DEFAULT_WIDTH):
    return f"{color}{char * width}{RESET}"'''
    if old_bar in src:
        src = src.replace(old_bar, new_bar, 1)
        print("  [3a] Patched _bar()")

    old_wrap = '''def _wrap(text, indent=2, width=W-4):
    """Word-wrap text with consistent indent."""
    lines = []
    for para in text.strip().split("\\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        for line in textwrap.wrap(para, width=width):
            lines.append(" " * indent + line)
    return lines'''
    new_wrap = '''def _wrap(text, indent=2, width=DEFAULT_WIDTH-4):
    """Word-wrap text with consistent indent."""
    lines = []
    for para in text.strip().split("\\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        for line in textwrap.wrap(para, width=width):
            lines.append(" " * indent + line)
    return lines'''
    if old_wrap in src:
        src = src.replace(old_wrap, new_wrap, 1)
        print("  [3b] Patched _wrap() default")

    # --- 4. Patch __init__ to accept width and create self.fmt ---
    old_init = '''    def __init__(self, species_reg: SpeciesRegistry, skill_reg: SkillRegistry,
                 data_dir: str = "data"):
        self.species_reg = species_reg
        self.skill_reg = skill_reg
        self.engine = CreationEngine(species_reg, skill_reg)
        self.descs = _load_skill_descriptions(data_dir)
        self.step = STEP_WELCOME
        self.path = "undecided"  # "template" or "scratch"
        self.background = ""
        self._force_sensitive = False'''
    new_init = '''    def __init__(self, species_reg: SpeciesRegistry, skill_reg: SkillRegistry,
                 data_dir: str = "data", width: int = DEFAULT_WIDTH):
        self.species_reg = species_reg
        self.skill_reg = skill_reg
        self.engine = CreationEngine(species_reg, skill_reg)
        self.descs = _load_skill_descriptions(data_dir)
        self.step = STEP_WELCOME
        self.path = "undecided"  # "template" or "scratch"
        self.background = ""
        self._force_sensitive = False
        self.fmt = Fmt(width=width)'''
    if old_init in src:
        src = src.replace(old_init, new_init, 1)
        print("  [4] Patched __init__ with width + self.fmt")
    else:
        print("  [4] SKIP __init__ (anchor mismatch)")

    # --- 5. Patch all _bar() calls in renderers to use self.fmt ---
    # Replace bare _bar("=") → self.fmt.bar("=")
    # Replace _bar("-", DIM) → self.fmt.bar("-", DIM)
    # Replace _bar("=") at end of renderers similarly
    src = re.sub(r'(?<!\w)_bar\("="\)', 'self.fmt.bar("=")', src)
    src = re.sub(r'(?<!\w)_bar\("-", DIM\)', 'self.fmt.bar("-", DIM)', src)
    src = re.sub(r'(?<!\w)_bar\("=", BRIGHT_CYAN\)', 'self.fmt.bar("=", BRIGHT_CYAN)', src)
    print("  [5] Replaced _bar() calls with self.fmt.bar()")

    # --- 6. Replace _wrap() calls in renderers with self.fmt.wrap() ---
    # Only replace calls inside class methods (indented), NOT the module-level def
    src = re.sub(r'(?<=\s)_wrap\((?!text, indent=2, width=DEFAULT_WIDTH)', 'self.fmt.wrap(', src)
    print("  [6] Replaced _wrap() calls with self.fmt.wrap()")

    # --- 7. Remove species description truncation ---
    old_species_trunc = '''            desc_text = sp.description.strip()
            first_sentence = desc_text.split(".")[0] + "."
            if len(first_sentence) > 72:
                first_sentence = first_sentence[:69] + "..."
            lines.append(f"    {_cy(first_sentence)}")'''
    new_species_desc = '''            desc_text = sp.description.strip()
            # Show full first sentence, word-wrapped (no truncation)
            first_sentence = desc_text.split(".")[0] + "."
            for dl in self.fmt.wrap(first_sentence, indent=4):
                lines.append(f"{_cy('')}{dl}")'''
    if old_species_trunc in src:
        src = src.replace(old_species_trunc, new_species_desc, 1)
        print("  [7] Removed species description truncation")
    else:
        print("  [7] SKIP species truncation (anchor mismatch)")

    # --- 8. Remove skill hint truncation ---
    old_skill_trunc = '''                    hint = game_use.strip().split(".")[0] + "." if game_use else ""
                    if len(hint) > 45:
                        hint = hint[:42] + "..."
                    lines.append(f"    {_dim(sd.name):27s} {_dim(hint)}{star}")'''
    new_skill_hint = '''                    hint = game_use.strip().split(".")[0] + "." if game_use else ""
                    lines.append(f"    {_dim(sd.name):27s} {_dim(hint)}{star}")'''
    if old_skill_trunc in src:
        src = src.replace(old_skill_trunc, new_skill_hint, 1)
        print("  [8] Removed skill hint truncation")
    else:
        print("  [8] SKIP skill truncation (anchor mismatch)")

    if src != original:
        write(WIZARD_PATH, src)
        print("  ✓ creation_wizard.py patched")
    else:
        print("  ✗ No changes to creation_wizard.py")


def patch_sheet_renderer():
    """Patch sheet_renderer.py for width-aware formatting."""
    src = read(SHEET_PATH)
    backup(SHEET_PATH)
    original = src

    # --- 1. Add Fmt import ---
    old_import = "from server.ansi import ("
    new_import = "from engine.text_format import Fmt\nfrom server.ansi import ("
    if "from engine.text_format import Fmt" not in src:
        src = src.replace(old_import, new_import, 1)
        print("  [1] Added Fmt import to sheet_renderer")

    # --- 2. Remove ability description truncation ---
    old_ab_trunc = '            desc = ab.description[:50] + "..." if len(ab.description) > 50 else ab.description'
    new_ab_full  = '            desc = ab.description  # Full description, no truncation'
    if old_ab_trunc in src:
        src = src.replace(old_ab_trunc, new_ab_full, 1)
        print("  [2] Removed ability description truncation")
    else:
        print("  [2] SKIP ability truncation (anchor mismatch)")

    # --- 3. Add width parameter to render_game_sheet ---
    old_render_sig = 'def render_game_sheet(char_dict, skill_reg):'
    new_render_sig = 'def render_game_sheet(char_dict, skill_reg, width=W):'
    if old_render_sig in src and 'def render_game_sheet(char_dict, skill_reg, width' not in src:
        src = src.replace(old_render_sig, new_render_sig, 1)
        print("  [3] Added width param to render_game_sheet")

    # --- 4. Add width parameter to render_creation_sheet ---
    old_create_sig = '''def render_creation_sheet(
    name, species, attributes, skills, skill_reg,
    attr_pips_total, attr_pips_spent, skill_pips_total, skill_pips_spent,
):'''
    new_create_sig = '''def render_creation_sheet(
    name, species, attributes, skills, skill_reg,
    attr_pips_total, attr_pips_spent, skill_pips_total, skill_pips_spent,
    width=W,
):'''
    if old_create_sig in src and 'width=W,\n):' not in src:
        src = src.replace(old_create_sig, new_create_sig, 1)
        print("  [4] Added width param to render_creation_sheet")

    if src != original:
        write(SHEET_PATH, src)
        print("  ✓ sheet_renderer.py patched")
    else:
        print("  ✗ No changes to sheet_renderer.py")


def patch_game_server():
    """Patch game_server.py to pass session.width to CreationWizard."""
    src = read(SERVER_PATH)
    backup(SERVER_PATH)
    original = src

    old_wizard_create = "        wizard = CreationWizard(self.species_reg, self.skill_reg)"
    new_wizard_create = "        wizard = CreationWizard(self.species_reg, self.skill_reg, width=session.width)"
    if old_wizard_create in src:
        src = src.replace(old_wizard_create, new_wizard_create, 1)
        print("  [1] game_server passes session.width to CreationWizard")
    else:
        print("  [1] SKIP wizard create (anchor mismatch)")

    if src != original:
        write(SERVER_PATH, src)
        print("  ✓ game_server.py patched")
    else:
        print("  ✗ No changes to game_server.py")


def validate():
    """AST-parse all patched files."""
    import ast
    ok = True
    for path in [WIZARD_PATH, SHEET_PATH, SERVER_PATH]:
        try:
            ast.parse(read(path))
            print(f"  AST OK: {os.path.basename(path)}")
        except SyntaxError as e:
            print(f"  AST FAIL: {os.path.basename(path)} — {e}")
            ok = False
    return ok


if __name__ == "__main__":
    print("=" * 60)
    print("Patch: Width-Aware Text Formatting")
    print("=" * 60)
    print()

    print("[creation_wizard.py]")
    patch_wizard()
    print()

    print("[sheet_renderer.py]")
    patch_sheet_renderer()
    print()

    print("[game_server.py]")
    patch_game_server()
    print()

    print("[Validation]")
    if validate():
        print()
        print("All patches applied and validated successfully.")
    else:
        print()
        print("VALIDATION FAILED — check output above.")
        sys.exit(1)
