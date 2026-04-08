#!/usr/bin/env python3
"""
patches/patch_db_schema_v8.py — SW_MUSH Database patch: schema v6/v7 → v8

Schema v8 adds crafting support. Since resources are stored in the existing
'inventory' JSON blob column and schematics in the 'attributes' JSON blob,
there is NO new table required for Phase 3 crafting.

This patch:
  1. Bumps SCHEMA_VERSION constant from 7 → 8
  2. Adds the v8 migration block to _run_migrations()
  3. Confirms 'inventory' is in _CHARACTER_WRITABLE_COLUMNS (assertion only)

Run from the project root:
    python patches/patch_db_schema_v8.py
"""

import sys
import shutil
import ast
import os

TARGET = os.path.join("db", "database.py")
BACKUP = TARGET + ".bak_pre_v8"

# ---------------------------------------------------------------------------
# Read source
# ---------------------------------------------------------------------------

with open(TARGET, "r", encoding="utf-8") as fh:
    src = fh.read()

orig_src = src

# ---------------------------------------------------------------------------
# 1. Bump SCHEMA_VERSION
# ---------------------------------------------------------------------------

for old_ver, new_ver in [("SCHEMA_VERSION = 7", "SCHEMA_VERSION = 8"),
                          ("SCHEMA_VERSION=7", "SCHEMA_VERSION=8")]:
    if old_ver in src:
        src = src.replace(old_ver, new_ver, 1)
        print(f"[OK] Bumped: {old_ver} → {new_ver}")
        break
else:
    print("[WARN] SCHEMA_VERSION = 7 not found — check the file manually.")

# ---------------------------------------------------------------------------
# 2. Add v8 migration block to _run_migrations()
# ---------------------------------------------------------------------------

V8_BLOCK = '''
        # v8 — Crafting system (Phase 3)
        # Resources stored in inventory JSON blob; schematics in attributes JSON blob.
        # No new tables required. Migration only marks the schema version bump.
        if current_version < 8:
            # Ensure inventory column exists on characters table (it should from v1+)
            await db.execute("""
                SELECT inventory FROM characters LIMIT 1
            """)
            await db.execute(
                "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, 8)"
            )
            await db.commit()
            current_version = 8
            print("[DB] Migrated to schema v8 (crafting — JSON blob approach)")
'''

# Find the anchor: the v7 migration block end OR the end of _run_migrations body
# Try to insert after the v7 block
anchor_v7_end = "current_version = 7\n            print"
anchor_v7_full = None

# Find the closing of the last migration block
for anchor in [
    'current_version = 7\n            print("[DB] Migrated to schema v7',
    'current_version = 7\n            print("[DB]',
    "current_version = 7\n",
]:
    if anchor in src:
        # Find end of the print statement line after this anchor
        pos = src.index(anchor)
        # Find the next newline after the print statement
        print_start = src.index("print(", pos)
        line_end = src.index("\n", print_start)
        anchor_v7_full = src[pos:line_end + 1]
        break

if V8_BLOCK.strip() in src:
    print("[OK] v8 migration block already present — skipping.")
elif anchor_v7_full:
    src = src.replace(anchor_v7_full, anchor_v7_full + V8_BLOCK, 1)
    print(f"[OK] Inserted v8 migration block after v7 block.")
else:
    # Fallback: insert before the closing of _run_migrations
    # Look for a comment like "# end of migrations" or just before the function ends
    fallback_anchors = [
        "        # End of migrations",
        "        # end of migrations",
    ]
    inserted = False
    for anc in fallback_anchors:
        if anc in src:
            src = src.replace(anc, V8_BLOCK + "\n" + anc, 1)
            print(f"[OK] Inserted v8 migration block at fallback anchor.")
            inserted = True
            break
    if not inserted:
        print("[WARN] Could not find v7 migration anchor. V8 block NOT inserted.")
        print("       Manually add the following block to _run_migrations() after the v7 block:")
        print(V8_BLOCK)

# ---------------------------------------------------------------------------
# 3. Verify inventory in _CHARACTER_WRITABLE_COLUMNS (read-only check)
# ---------------------------------------------------------------------------

if "_CHARACTER_WRITABLE_COLUMNS" in src:
    # Find the list/tuple
    idx = src.index("_CHARACTER_WRITABLE_COLUMNS")
    snippet = src[idx:idx + 500]
    if "inventory" in snippet:
        print("[OK] 'inventory' confirmed in _CHARACTER_WRITABLE_COLUMNS.")
    else:
        print("[WARN] 'inventory' NOT found in _CHARACTER_WRITABLE_COLUMNS — add it manually.")
else:
    print("[WARN] _CHARACTER_WRITABLE_COLUMNS not found in source.")

# ---------------------------------------------------------------------------
# Validate + write
# ---------------------------------------------------------------------------

if src == orig_src:
    print("[INFO] No changes were needed (schema already at v8?).")
    sys.exit(0)

try:
    ast.parse(src)
    print("[OK] AST validation passed.")
except SyntaxError as e:
    print(f"[ERROR] Syntax error after patch: {e}")
    print("        Original file NOT modified.")
    sys.exit(1)

shutil.copy(TARGET, BACKUP)
print(f"[OK] Backup created: {BACKUP}")

with open(TARGET, "w", encoding="utf-8") as fh:
    fh.write(src)

print(f"[OK] Written: {TARGET}")
print("\nSchema v8 patch complete.")
print("NOTE: Delete sw_mush.db and re-run build_mos_eisley.py if this is a fresh environment.")
print("      On an existing live DB, the migration will run automatically on next server start.")
