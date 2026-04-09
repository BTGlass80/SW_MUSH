#!/usr/bin/env python3
"""
Hotfix: Fix two web client interface issues.

1. creation_wizard.py — Replace any remaining `width=W-8` with
   `width=self.fmt.prose_width - 4` (CRLF-safe).
2. text_format.py — Cap bar width at MAX_PROSE_WIDTH so decorative
   bars don't overflow on wide WebSocket sessions. Bars should match
   the prose content width, not span 120+ columns.
"""
import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIZARD_PATH = os.path.join(ROOT, "engine", "creation_wizard.py")
FMT_PATH = os.path.join(ROOT, "engine", "text_format.py")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def fix_wizard():
    """Replace any remaining width=W-8 references and ensure W→DEFAULT_WIDTH rename."""
    src = read(WIZARD_PATH)
    original = src

    # --- Ensure the module-level constant is renamed ---
    # Match both LF and CRLF: "W = 78" at start of line
    src = re.sub(r'^W = 78\s*#.*$', 'DEFAULT_WIDTH = 78  # Fallback; actual width comes from Fmt', src, flags=re.MULTILINE)
    # If the line is just "W = 78\r\n" with no comment
    src = re.sub(r'^W = 78\s*$', 'DEFAULT_WIDTH = 78  # Fallback; actual width comes from Fmt', src, flags=re.MULTILINE)

    # --- Fix _bar default ---
    src = re.sub(r'def _bar\(char="=", color=BRIGHT_CYAN, width=W\)',
                 'def _bar(char="=", color=BRIGHT_CYAN, width=DEFAULT_WIDTH)', src)
    # Also handle if it was never patched at all (original form)
    src = re.sub(r'def _bar\(char="=", color=BRIGHT_CYAN\):',
                 'def _bar(char="=", color=BRIGHT_CYAN, width=DEFAULT_WIDTH):', src)

    # --- Fix _wrap default ---
    src = re.sub(r'def _wrap\(text, indent=2, width=W-4\)',
                 'def _wrap(text, indent=2, width=DEFAULT_WIDTH-4)', src)

    # --- Fix any width=W-8 in method bodies ---
    src = re.sub(r'width\s*=\s*W\s*-\s*8', 'width=self.fmt.prose_width - 4', src)
    src = re.sub(r'width\s*=\s*W\s*-\s*4', 'width=self.fmt.prose_width', src)

    # --- Fix char * W in _bar body ---
    src = re.sub(r'\{char \* W\}', '{char * width}', src)

    if src != original:
        write(WIZARD_PATH, src)
        print(f"  Fixed W references in creation_wizard.py")
    else:
        print(f"  No W references found (already clean)")


def fix_formatter():
    """Cap bar width and add a display_width property."""
    src = read(FMT_PATH)
    original = src

    # Replace the bar method to use a capped width
    old_bar = '''    def bar(self, char: str = "=", color: str = BRIGHT_CYAN) -> str:
        """Full-width decorative rule."""
        return f"{color}{char * self.width}{RESET}"'''

    new_bar = '''    @property
    def display_width(self) -> int:
        """Capped width for decorative elements (bars, headers).

        Bars should match the prose content area, not span the raw
        session width.  On a 120-col WebSocket session, a 120-char
        bar of ===== looks broken. Cap at prose_width + 4 (indent).
        """
        return min(self.width, MAX_PROSE_WIDTH + 4)

    def bar(self, char: str = "=", color: str = BRIGHT_CYAN) -> str:
        """Decorative rule spanning the display width."""
        return f"{color}{char * self.display_width}{RESET}"'''

    if old_bar in src:
        src = src.replace(old_bar, new_bar, 1)
        print("  Added display_width property and capped bar()")
    else:
        # Try CRLF version
        old_bar_crlf = old_bar.replace('\n', '\r\n')
        if old_bar_crlf in src:
            new_bar_crlf = new_bar.replace('\n', '\r\n')
            src = src.replace(old_bar_crlf, new_bar_crlf, 1)
            print("  Added display_width property and capped bar() [CRLF]")
        else:
            print("  SKIP bar patch — anchor not found")

    # Also cap the center() method
    old_center = '''    def center(self, text: str) -> str:
        """Center *text* within the current width."""
        pad = max(0, self.width - _ansi_len(text))
        return " " * (pad // 2) + text'''

    new_center = '''    def center(self, text: str) -> str:
        """Center *text* within the display width."""
        pad = max(0, self.display_width - _ansi_len(text))
        return " " * (pad // 2) + text'''

    if old_center in src:
        src = src.replace(old_center, new_center, 1)
        print("  Capped center() to display_width")
    else:
        old_center_crlf = old_center.replace('\n', '\r\n')
        if old_center_crlf in src:
            new_center_crlf = new_center.replace('\n', '\r\n')
            src = src.replace(old_center_crlf, new_center_crlf, 1)
            print("  Capped center() to display_width [CRLF]")
        else:
            print("  SKIP center patch — anchor not found")

    if src != original:
        write(FMT_PATH, src)
        print("  ✓ text_format.py patched")
    else:
        print("  ✗ No changes to text_format.py")


def validate():
    import ast
    ok = True
    for path in [WIZARD_PATH, FMT_PATH]:
        try:
            ast.parse(read(path))
            print(f"  AST OK: {os.path.basename(path)}")
        except SyntaxError as e:
            print(f"  AST FAIL: {os.path.basename(path)} — {e}")
            ok = False
    return ok


if __name__ == "__main__":
    print("=" * 60)
    print("Hotfix: W reference + bar overflow")
    print("=" * 60)
    print()

    print("[creation_wizard.py]")
    fix_wizard()
    print()

    print("[text_format.py]")
    fix_formatter()
    print()

    print("[Validation]")
    if validate():
        print("\nHotfix applied successfully.")
    else:
        print("\nVALIDATION FAILED.")
        sys.exit(1)
