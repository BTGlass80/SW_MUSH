#!/usr/bin/env python3
"""
patches/party_tutorial_wire_patch.py
SW_MUSH — Drop: Party Commands + Tutorial Wiring

Applies two patches to server/game_server.py:
  1. Import + register party_commands
  2. Wire tutorial on_enter_game, skip-tutorial intercept, and on_command hooks

Run from project root:
    python patches/party_tutorial_wire_patch.py
"""

import ast
import shutil
import sys
from pathlib import Path

TARGET = Path("server/game_server.py")
BACKUP = Path("server/game_server.py.bak_party_tutorial")


def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save(path: Path, text: str):
    path.write_text(text, encoding="utf-8")


def apply(src: str, old: str, new: str, label: str) -> str:
    if old not in src:
        print(f"  [WARN] Anchor not found for: {label}")
        return src
    result = src.replace(old, new, 1)
    print(f"  [OK]   {label}")
    return result


def validate(src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError as e:
        print(f"  [ERROR] Syntax error after patching: {e}")
        return False


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    print(f"Backing up {TARGET} -> {BACKUP}")
    shutil.copy2(TARGET, BACKUP)

    src = load(TARGET)

    # ── Patch 1: Add party_commands import after bounty_commands import ──────
    src = apply(
        src,
        old="from parser.bounty_commands import register_bounty_commands\n",
        new=(
            "from parser.bounty_commands import register_bounty_commands\n"
            "from parser.party_commands import register_party_commands\n"
        ),
        label="Add party_commands import",
    )

    # ── Patch 2: Register party commands after bounty commands ───────────────
    src = apply(
        src,
        old="        register_bounty_commands(self.registry)\n",
        new=(
            "        register_bounty_commands(self.registry)\n"
            "        register_party_commands(self.registry)\n"
        ),
        label="Register party commands",
    )

    # ── Patch 3: Tutorial on_enter_game hook after auto-look ─────────────────
    # Fires after the look command runs, so the tutorial greeting appears after
    # the room description.
    src = apply(
        src,
        old="        await session.send_prompt()\n\n    async def _run_character_creation(self, session: Session) -> Optional[dict]:",
        new=(
            "        # Tutorial hook — starts or resumes tutorial for new/returning players\n"
            "        await self.tutorial.on_enter_game(session, self.db, self.session_mgr)\n"
            "\n"
            "        await session.send_prompt()\n"
            "\n"
            "    async def _run_character_creation(self, session: Session) -> Optional[dict]:"
        ),
        label="Wire tutorial on_enter_game hook",
    )

    # ── Patch 4: Tutorial skip + on_command hooks in _game_loop ──────────────
    src = apply(
        src,
        old=(
            "            if session.state != SessionState.IN_GAME:\n"
            "                return\n"
            "\n"
            "            await self.parser.parse_and_dispatch(session, line)\n"
        ),
        new=(
            "            if session.state != SessionState.IN_GAME:\n"
            "                return\n"
            "\n"
            "            # Tutorial: intercept 'skip tutorial' before dispatch\n"
            "            if line.strip().lower() == \"skip tutorial\":\n"
            "                await self.tutorial.skip(session, self.db)\n"
            "                continue\n"
            "\n"
            "            await self.parser.parse_and_dispatch(session, line)\n"
            "\n"
            "            # Tutorial: notify after each command\n"
            "            cmd, _, args = line.strip().partition(\" \")\n"
            "            await self.tutorial.on_command(\n"
            "                session, cmd.lower(), args.strip(), self.db, self.session_mgr\n"
            "            )\n"
        ),
        label="Wire tutorial skip + on_command hooks",
    )

    # ── Validate ─────────────────────────────────────────────────────────────
    if not validate(src):
        print("Rolling back.")
        shutil.copy2(BACKUP, TARGET)
        sys.exit(1)

    save(TARGET, src)
    print(f"\nAll patches applied. {TARGET} updated.")
    print(f"Backup at {BACKUP}")


if __name__ == "__main__":
    main()
