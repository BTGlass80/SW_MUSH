# -*- coding: utf-8 -*-
"""
patch_hud_zone_mood.py — Add zone_name and zone_type to hud_update.

Adds two new fields to the HUD update payload so the web client can:
  1. Display the current zone name as a badge
  2. Shift ambient mood theming (colors, glow) based on zone type

The zone type is resolved from the zone's properties JSON
(the 'environment' key, e.g. "cantina", "industrial", "street").

Usage:
    python patches/patch_hud_zone_mood.py

Requires:
    - server/session.py with send_hud_update() method
"""

import os
import re
import shutil
import ast
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
TARGET = os.path.join(ROOT, "server", "session.py")


def main():
    if not os.path.isfile(TARGET):
        print(f"[ERROR] Cannot find {TARGET}")
        sys.exit(1)

    # Read with universal newlines to handle CRLF
    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    # Detect original line ending
    crlf = "\r\n" in src
    nl = "\r\n" if crlf else "\n"

    # Normalize to LF for safe matching
    work = src.replace("\r\n", "\n")

    # ── Check: already patched? ──
    if "zone_name" in work and "zone_type" in work:
        print("[OK] session.py already has zone_name/zone_type in hud_update. Nothing to do.")
        return

    # ── Add 'import json' if not present (it should be, but safety) ──
    if "import json" not in work:
        work = work.replace("import logging", "import json\nimport logging", 1)

    # ── Patch: Add zone lookup after the exits block ──
    # We look for the try/except block that fetches exits and add zone
    # lookup logic after it.

    # Anchor: the line that builds the hud["exits"] list
    anchor = '"exits": [],'
    if anchor not in work:
        print(f"[ERROR] Could not find anchor '{anchor}' in session.py")
        sys.exit(1)

    # We'll add zone_name and zone_type fields to the initial hud dict
    work = work.replace(
        '"exits": [],',
        '"exits": [],\n            "zone_name": "",\n            "zone_type": "",',
        1,
    )

    # Now find the exits-fetching block and add zone lookup after it.
    # Anchor: the except block after exits fetch
    exits_except = 'pass  # Non-critical'
    if exits_except not in work:
        # Try alternate
        exits_except = "pass  # Non-critical — HUD just won't show exits"
    if exits_except not in work:
        print(f"[ERROR] Could not find exits except block anchor in session.py")
        sys.exit(1)

    zone_lookup = '''pass  # Non-critical — HUD just won't show exits

        # Resolve zone name and type for ambient mood
        if db and room_id:
            try:
                room = await db.get_room(room_id)
                if room and room.get("zone_id"):
                    zone = await db.get_zone(room["zone_id"])
                    if zone:
                        hud["zone_name"] = zone.get("name", "")
                        # Zone type from properties.environment
                        props = zone.get("properties", "{}")
                        if isinstance(props, str):
                            import json as _json
                            try:
                                props = _json.loads(props)
                            except Exception:
                                props = {}
                        hud["zone_type"] = props.get("environment", "")
            except Exception:
                pass  # Non-critical — mood just stays default'''

    work = work.replace(exits_except, zone_lookup, 1)

    # ── Validate syntax ──
    try:
        ast.parse(work)
    except SyntaxError as e:
        print(f"[ERROR] Patch produced invalid Python: {e}")
        sys.exit(1)

    # Restore original line endings
    if crlf:
        work = work.replace("\n", "\r\n")

    # Backup
    backup = TARGET + ".pre_zone_mood_bak"
    shutil.copy2(TARGET, backup)
    print(f"[OK] Backup: {backup}")

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(work)

    print("[OK] Patched session.py — hud_update now includes zone_name and zone_type")
    print("     Web client will shift ambient mood based on zone environment.")


if __name__ == "__main__":
    main()
