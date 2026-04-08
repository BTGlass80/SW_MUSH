#!/usr/bin/env python3
"""
patches/patch_crew_wages_wire.py  --  Wire NPC crew wages into the tick loop.

Two changes:

  1. engine/npc_crew.py
     - Fixes process_wage_tick() which calls session_mgr.get_session_for_character()
       — that method does not exist. The real method is find_by_character().
     - Adds a WAGE_TICK_INTERVAL constant (14400 ticks = every 4 real hours).

  2. server/game_server.py
     - Adds a wage tick counter to _game_tick_loop().
     - Calls process_wage_tick() every WAGE_TICK_INTERVAL ticks.

Run from project root:
    python patches/patch_crew_wages_wire.py
"""

import sys
import shutil
import ast
from pathlib import Path

CREW_TARGET  = Path("engine/npc_crew.py")
SERVER_TARGET = Path("server/game_server.py")
CREW_BACKUP  = Path("engine/npc_crew.py.bak_wages")
SERVER_BACKUP = Path("server/game_server.py.bak_wages")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def apply(src: str, old: str, new: str, label: str) -> str:
    if old in src:
        return src.replace(old, new, 1)
    old_lf = old.replace("\r\n", "\n")
    src_lf = src.replace("\r\n", "\n")
    if old_lf in src_lf:
        return src_lf.replace(old_lf, new, 1)
    print(f"ERROR: anchor not found for: {label}")
    print(f"  First 120 chars: {repr(old[:120])}")
    sys.exit(1)


def patch_npc_crew(src: str) -> str:
    # ── Fix 1: add WAGE_TICK_INTERVAL constant near top of file ──────────────
    # Insert after the imports block — find the first blank line after imports
    old_const = "log = logging.getLogger(__name__)\n"
    new_const = (
        "log = logging.getLogger(__name__)\n"
        "\n"
        "# How often wages fire in the tick loop (1 tick = 1 second).\n"
        "# 14400 ticks = 4 real hours.  Six deductions per real day.\n"
        "WAGE_TICK_INTERVAL = 14400\n"
    )
    src = apply(src, old_const, new_const, "WAGE_TICK_INTERVAL constant")

    # ── Fix 2: replace get_session_for_character with find_by_character ───────
    old_notify = (
        "        # Notify the player if they're online\n"
        "        if departed:\n"
        "            session = session_mgr.get_session_for_character(char_id)\n"
        "            if session:\n"
        "                for name in departed:\n"
        "                    await session.send_line(\n"
        "                        f\"  \\033[1;33m{name} has left your crew -- unpaid wages.\\033[0m\"\n"
        "                    )\n"
        "        if total_paid > 0:\n"
        "            session = session_mgr.get_session_for_character(char_id)\n"
        "            if session:\n"
        "                await session.send_line(\n"
        "                    f\"  \\033[0;36mCrew wages paid: {total_paid:,} credits.\\033[0m\"\n"
        "                )\n"
    )
    new_notify = (
        "        # Notify the player if they're online\n"
        "        if departed:\n"
        "            session = session_mgr.find_by_character(char_id)\n"
        "            if session:\n"
        "                for name in departed:\n"
        "                    await session.send_line(\n"
        "                        f\"  \\033[1;33m{name} has left your crew -- unpaid wages.\\033[0m\"\n"
        "                    )\n"
        "        if total_paid > 0:\n"
        "            session = session_mgr.find_by_character(char_id)\n"
        "            if session:\n"
        "                await session.send_line(\n"
        "                    f\"  \\033[0;36mCrew wages paid: {total_paid:,} credits.\\033[0m\"\n"
        "                )\n"
    )
    src = apply(src, old_notify, new_notify, "get_session_for_character → find_by_character")
    return src


def patch_game_server(src: str) -> str:
    # ── Add wage tick counter initialisation ──────────────────────────────────
    old_tick_init = (
        "        self._tick_task: Optional[asyncio.Task] = None\n"
    )
    new_tick_init = (
        "        self._tick_task: Optional[asyncio.Task] = None\n"
        "        self._wage_tick_counter: int = 0\n"
    )
    src = apply(src, old_tick_init, new_tick_init, "wage counter init")

    # ── Add wage tick call after CP tick ─────────────────────────────────────
    old_after_cp = (
        "            # \u2500\u2500 CP Progression tick \u2500\u2500\n"
        "            try:\n"
        "                from engine.cp_engine import get_cp_engine\n"
        "                await get_cp_engine().tick(self.db, self.session_mgr)\n"
        "            except Exception:\n"
        "                log.debug(\"CP engine tick skipped\", exc_info=True)\n"
    )
    new_after_cp = (
        "            # \u2500\u2500 CP Progression tick \u2500\u2500\n"
        "            try:\n"
        "                from engine.cp_engine import get_cp_engine\n"
        "                await get_cp_engine().tick(self.db, self.session_mgr)\n"
        "            except Exception:\n"
        "                log.debug(\"CP engine tick skipped\", exc_info=True)\n"
        "            # \u2500\u2500 NPC crew wages (every 4 real hours) \u2500\u2500\n"
        "            self._wage_tick_counter += 1\n"
        "            try:\n"
        "                from engine.npc_crew import process_wage_tick, WAGE_TICK_INTERVAL\n"
        "                if self._wage_tick_counter % WAGE_TICK_INTERVAL == 0:\n"
        "                    await process_wage_tick(self.db, self.session_mgr)\n"
        "            except Exception:\n"
        "                log.debug(\"Crew wage tick skipped\", exc_info=True)\n"
    )
    src = apply(src, old_after_cp, new_after_cp, "wage tick call")
    return src


def main():
    for p in [CREW_TARGET, SERVER_TARGET]:
        if not p.exists():
            print(f"ERROR: {p} not found. Run from project root.")
            sys.exit(1)

    shutil.copy(CREW_TARGET,  CREW_BACKUP)
    shutil.copy(SERVER_TARGET, SERVER_BACKUP)
    print(f"Backups: {CREW_BACKUP}, {SERVER_BACKUP}")

    # Patch npc_crew.py
    src = read(CREW_TARGET)
    src = patch_npc_crew(src)
    try:
        ast.parse(src)
        print("  npc_crew.py  AST: OK")
    except SyntaxError as e:
        print(f"  npc_crew.py  AST FAIL: {e}")
        sys.exit(1)
    write(CREW_TARGET, src)
    print(f"  [1/2] engine/npc_crew.py patched (method fix + WAGE_TICK_INTERVAL)")

    # Patch game_server.py
    src = read(SERVER_TARGET)
    src = patch_game_server(src)
    try:
        ast.parse(src)
        print("  game_server.py  AST: OK")
    except SyntaxError as e:
        print(f"  game_server.py  AST FAIL: {e}")
        sys.exit(1)
    write(SERVER_TARGET, src)
    print(f"  [2/2] server/game_server.py patched (wage counter + tick call)")

    print("\nCrew wages now fire every 4 real hours (14400 ticks).")
    print("Players with hired crew will be notified of deductions when online.")
    print("Crew quit if wages can't be paid.")


if __name__ == "__main__":
    main()
