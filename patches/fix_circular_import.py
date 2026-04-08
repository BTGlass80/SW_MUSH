#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_circular_import.py
----------------------
Fixes circular import: claude_provider.py imports AIProvider from providers.py,
but providers.py imports claude_provider.py during initialization.

Fix: remove the top-level 'from ai.providers import AIProvider' in
claude_provider.py and instead inherit from a locally-defined stub,
with the real AIProvider resolved lazily at class definition time via
a module-level __init_subclass__ trick -- actually the simplest fix
is just to copy the ABC definition inline / use duck typing.

Simplest correct fix: define ClaudeProvider without inheriting AIProvider
at import time. Python duck-typing means AIManager just needs .generate(),
.is_available(), and .name -- no ABC enforcement required at runtime.
"""
import ast, shutil, sys
from pathlib import Path

TARGET = Path("ai/claude_provider.py")
if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from project root.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")

# Remove the circular import line
OLD_IMPORT = "from ai.providers import AIProvider\n"
OLD_IMPORT_CRLF = "from ai.providers import AIProvider\r\n"

# Also remove the comment line that precedes it if present
OLD_BLOCK = (
    "# Lazy import to avoid circular dependency at module load time.\n"
    "# AIProvider is imported inside the class body reference only.\n"
    "from ai.providers import AIProvider\n"
)
OLD_BLOCK_CRLF = OLD_BLOCK.replace("\n", "\r\n")

patched = src

removed = False
for old in (OLD_BLOCK_CRLF, OLD_BLOCK, OLD_IMPORT_CRLF, OLD_IMPORT):
    if old in patched:
        patched = patched.replace(old, "", 1)
        removed = True
        print("  - Removed circular import line(s)")
        break

if not removed:
    if "from ai.providers import AIProvider" not in patched:
        print("✓ Circular import already removed — nothing to do.")
    else:
        print("WARNING: Could not find exact import line. Manual removal needed.")

# Fix class definition: AIProvider -> object (duck typing is sufficient)
OLD_CLASS = "class ClaudeProvider(AIProvider):"
NEW_CLASS  = "class ClaudeProvider:"   # duck-typed; AIManager checks .name / .generate() / .is_available()

if OLD_CLASS in patched:
    patched = patched.replace(OLD_CLASS, NEW_CLASS, 1)
    print("  ~ Changed ClaudeProvider(AIProvider) -> ClaudeProvider (duck-typed)")
elif NEW_CLASS in patched:
    print("✓ Class definition already duck-typed.")
else:
    print("WARNING: Could not find ClaudeProvider class definition.")

# Validate
try:
    ast.parse(patched)
    print("  SYNTAX OK")
except SyntaxError as e:
    print(f"  SYNTAX ERROR: {e}")
    sys.exit(1)

bak = TARGET.with_suffix(".py.circ_bak")
shutil.copy2(TARGET, bak)
TARGET.write_text(patched, encoding="utf-8")
print(f"✓ ai/claude_provider.py fixed (backup: {bak.name})")
print()
print("Set API key in PowerShell:")
print('  $env:ANTHROPIC_API_KEY = "sk-ant-..."')
print("Then restart:  python main.py")
