#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drop4_fixup_patch.py
--------------------
Fixes two issues left over from Drop 4 wire patch:

  1. engine/director.py — _run_api_turn() calls self._write_log() but
     the method is self.log_event(). Fix the call.

  2. engine/director.py — faction_turn() doesn't call _run_api_turn().
     Insert the API hook at the top of the method body.

Run from the SW_MUSH project root:
    python patches/drop4_fixup_patch.py
"""

import ast
import shutil
import sys
from pathlib import Path

TARGET = Path("engine/director.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")
patched = src

# ── Fix 1: _write_log → log_event ────────────────────────────────────────────
print("── Fix 1: _write_log → log_event ────────────────────────────────────────")

OLD_LOG_CALL = """        await self._write_log(
            db,
            event_type="faction_turn",
            summary=news_headline,
            details_json=details_json,
            token_cost_input=tok_in,
            token_cost_output=tok_out,
        )"""

NEW_LOG_CALL = """        await self.log_event(
            db,
            event_type="faction_turn",
            summary=news_headline,
            details=json.loads(details_json) if details_json else None,
            input_tokens=tok_in,
            output_tokens=tok_out,
        )"""

if "_write_log" not in patched:
    print("✓ _write_log not found — already fixed or not present.")
elif OLD_LOG_CALL.replace("\r\n", "\n") in patched.replace("\r\n", "\n"):
    patched = patched.replace(OLD_LOG_CALL, NEW_LOG_CALL)
    print("  + Replaced _write_log() call with log_event()")
else:
    # Try with CRLF
    old_crlf = OLD_LOG_CALL.replace("\n", "\r\n")
    new_crlf = NEW_LOG_CALL.replace("\n", "\r\n")
    if old_crlf in patched:
        patched = patched.replace(old_crlf, new_crlf)
        print("  + Replaced _write_log() call with log_event() (CRLF)")
    else:
        # Minimal fallback: just rename the method call
        patched = patched.replace("await self._write_log(", "await self.log_event(", 1)
        patched = patched.replace("            details_json=details_json,", "            details=json.loads(details_json) if details_json else None,", 1)
        patched = patched.replace("            token_cost_input=tok_in,", "            input_tokens=tok_in,", 1)
        patched = patched.replace("            token_cost_output=tok_out,", "            output_tokens=tok_out,", 1)
        print("  + Applied fallback rename of _write_log → log_event")

# ── Fix 2: Hook _run_api_turn into faction_turn() ────────────────────────────
print("── Fix 2: Wire _run_api_turn into faction_turn() ────────────────────────")

if "_run_api_turn" in patched and "await self._run_api_turn" in patched:
    print("✓ _run_api_turn already called in faction_turn() — skipping.")
else:
    # Insert API hook right after ensure_loaded(db), before local delta logic
    OLD_BODY = "        await self.ensure_loaded(db)\n\n        # Apply local deltas"
    NEW_BODY = (
        "        await self.ensure_loaded(db)\n\n"
        "        # Attempt API-driven Faction Turn first\n"
        "        try:\n"
        "            _ai_mgr = getattr(session_mgr, '_ai_manager', None)\n"
        "            if _ai_mgr and await self._run_api_turn(db, session_mgr, _ai_mgr):\n"
        "                self._digest.reset()\n"
        "                self._last_turn_time = time.time()\n"
        "                return  # API turn handled everything\n"
        "        except Exception as _api_exc:\n"
        "            log.warning('[director] API turn error: %s — using local fallback', _api_exc)\n\n"
        "        # Apply local deltas"
    )

    # Try LF then CRLF
    if OLD_BODY in patched:
        patched = patched.replace(OLD_BODY, NEW_BODY, 1)
        print("  + API hook inserted into faction_turn()")
    elif OLD_BODY.replace("\n", "\r\n") in patched:
        patched = patched.replace(OLD_BODY.replace("\n", "\r\n"), NEW_BODY.replace("\n", "\r\n"), 1)
        print("  + API hook inserted into faction_turn() (CRLF)")
    else:
        # Broader fallback: find the line after ensure_loaded
        alt = "        await self.ensure_loaded(db)"
        if alt in patched:
            patched = patched.replace(
                alt,
                alt + "\n\n"
                "        # Attempt API-driven Faction Turn first\n"
                "        try:\n"
                "            _ai_mgr = getattr(session_mgr, '_ai_manager', None)\n"
                "            if _ai_mgr and await self._run_api_turn(db, session_mgr, _ai_mgr):\n"
                "                self._digest.reset()\n"
                "                self._last_turn_time = time.time()\n"
                "                return\n"
                "        except Exception as _api_exc:\n"
                "            log.warning('[director] API turn error: %s — local fallback', _api_exc)",
                1,
            )
            print("  + API hook inserted (fallback anchor)")
        else:
            print("  WARNING: Could not find faction_turn() anchor.")
            print("  Add manually after 'await self.ensure_loaded(db)':")
            print("    _ai_mgr = getattr(session_mgr, '_ai_manager', None)")
            print("    if _ai_mgr and await self._run_api_turn(db, session_mgr, _ai_mgr):")
            print("        self._digest.reset()")
            print("        self._last_turn_time = time.time()")
            print("        return")

# ── Validate and write ────────────────────────────────────────────────────────
print("\n── Syntax check ─────────────────────────────────────────────────────────")
try:
    ast.parse(patched)
    print("  OK")
except SyntaxError as e:
    print(f"  SYNTAX ERROR: {e}")
    print("  File unchanged.")
    sys.exit(1)

bak = TARGET.with_suffix(".py.drop4fix_bak")
shutil.copy2(TARGET, bak)
TARGET.write_text(patched, encoding="utf-8")
print(f"  Backup: {bak.name}")
print("✓ engine/director.py fixed.")
print()
print("Drop 4 fixup complete. Test with:")
print("  @director trigger   — force a Faction Turn")
print("  @director budget    — verify spend tracking")
print("  news                — see the first headline")
