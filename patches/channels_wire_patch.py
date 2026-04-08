#!/usr/bin/env python3
"""
patches/channels_wire_patch.py
SW_MUSH — Drop: Communication Channels (P4)

Applies three patches to server/game_server.py:
  1. Import register_channel_commands
  2. Register channel commands at startup
  3. Cleanup channel freq subscriptions on idle disconnect

Run from project root:
    python patches/channels_wire_patch.py
"""

import ast
import shutil
import sys
from pathlib import Path

TARGET = Path("server/game_server.py")
BACKUP = Path("server/game_server.py.bak_channels")


def load(path):
    return path.read_text(encoding="utf-8")


def save(path, text):
    path.write_text(text, encoding="utf-8")


def apply(src, old, new, label):
    if old not in src:
        print(f"  [WARN] Anchor not found for: {label}")
        return src
    result = src.replace(old, new, 1)
    print(f"  [OK]   {label}")
    return result


def validate(src):
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

    # ── Patch 1: Import ───────────────────────────────────────────────────────
    src = apply(
        src,
        old="from parser.bounty_commands import register_bounty_commands\n",
        new=(
            "from parser.bounty_commands import register_bounty_commands\n"
            "from parser.channel_commands import register_channel_commands\n"
        ),
        label="Add channel_commands import",
    )

    # ── Patch 2: Register at startup ──────────────────────────────────────────
    src = apply(
        src,
        old="        register_bounty_commands(self.registry)\n",
        new=(
            "        register_bounty_commands(self.registry)\n"
            "        register_channel_commands(self.registry)\n"
        ),
        label="Register channel commands",
    )

    # ── Patch 3: Cleanup freq listeners on idle disconnect ────────────────────
    src = apply(
        src,
        old=(
            "                    await session.close()\n"
            "                    self.session_mgr.remove(session)\n"
        ),
        new=(
            "                    await session.close()\n"
            "                    self.session_mgr.remove(session)\n"
            "                    # Cleanup channel freq subscriptions\n"
            "                    if session.character:\n"
            "                        try:\n"
            "                            from server.channels import get_channel_manager\n"
            "                            get_channel_manager().cleanup_character(\n"
            "                                session.character[\"id\"]\n"
            "                            )\n"
            "                        except Exception:\n"
            "                            pass\n"
        ),
        label="Cleanup channel freqs on idle disconnect",
    )

    # ── Validate ──────────────────────────────────────────────────────────────
    if not validate(src):
        print("Rolling back.")
        shutil.copy2(BACKUP, TARGET)
        sys.exit(1)

    save(TARGET, src)
    print(f"\nAll patches applied. {TARGET} updated.")
    print(f"Backup at {BACKUP}")


if __name__ == "__main__":
    main()
