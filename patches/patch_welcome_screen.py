#!/usr/bin/env python3
"""
Patch: New welcome screen for both Telnet and WebSocket clients.

Replaces the boring +---+ box banner with a colorful ANSI splash
that works on both 80-col Telnet and the web client.

Also removes the broken ASCII art splash from client.html so the
server's banner is the single source of truth for the login screen.

Changes:
  1. server/config.py — new welcome_banner with ANSI art
  2. static/client.html — remove client-side splash, keep only
     a minimal connecting message
"""
import os
import re
import sys
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "server", "config.py")
CLIENT_PATH = os.path.join(ROOT, "static", "client.html")

# ANSI escape codes
RST = "\\033[0m"
BOLD = "\\033[1m"
DIM = "\\033[2m"
BY = "\\033[93m"   # bright yellow
BC = "\\033[96m"   # bright cyan
BG = "\\033[92m"   # bright green
BB = "\\033[94m"   # bright blue
BR = "\\033[91m"   # bright red
BW = "\\033[97m"   # bright white
BM = "\\033[95m"   # bright magenta
YL = "\\033[33m"   # yellow
CN = "\\033[36m"   # cyan


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def backup(path):
    bak = path + ".pre_splash_bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  Backup: {bak}")


# The new banner — designed for 78 columns, looks great on wider too.
# Uses box-drawing characters that work in UTF-8 Telnet and browsers.
NEW_BANNER = r'''    welcome_banner: str = (
        "\r\n"
        "\033[93m"
        "     ____________  ___    ____       _       _____    ____   _____ \r\n"
        "    / ___/_ __/   |   \\  / _  \\     | |     / /   |  / _  \\ / ___/ \r\n"
        "    \\__ \\ | | / /| |  / / /_| |     | | /| / / /| | / /_| / \\__ \\  \r\n"
        "   ___/ / | |/ ___ | / /  _   |     | |/ |/ / ___ |/  _  /___/ /  \r\n"
        "  /____/  |_/_/  |_|/_/  | |  |     |__/|__/_/  |_/_/ | | /____/   \r\n"
        "                         |_|                           |_|          \r\n"
        "\033[0m"
        "\r\n"
        "\033[2m\033[96m"
        "         ╔═══════════════════════════════════════════════╗\r\n"
        "         ║\033[0m \033[1m\033[97m  D 6   R E V I S E D   &   E X P A N D E D \033[0m \033[2m\033[96m║\r\n"
        "         ╚═══════════════════════════════════════════════╝\r\n"
        "\033[0m"
        "\r\n"
        "\033[2m  A long time ago in a galaxy far, far away...\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
        "\033[33m  Mos Eisley Spaceport.\033[0m\r\n"
        "\033[2m  You will never find a more wretched hive of scum and\r\n"
        "  villainy.  Smugglers, bounty hunters, and Imperial patrols\r\n"
        "  fill its dusty streets.  Your story begins here.\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
        "  \033[92mconnect\033[0m \033[2m<username> <password>\033[0m   \033[2m— Log in to an existing account\033[0m\r\n"
        "  \033[92mcreate\033[0m  \033[2m<username> <password>\033[0m   \033[2m— Register a new account\033[0m\r\n"
        "  \033[92mquit\033[0m                          \033[2m— Disconnect\033[0m\r\n"
        "\r\n"
        "\033[36m  ───────────────────────────────────────────────────────────\033[0m\r\n"
        "\r\n"
    )'''


def patch_config():
    """Replace the welcome banner in config.py."""
    src = read(CONFIG_PATH)
    backup(CONFIG_PATH)

    # Find the welcome_banner field — match everything from the field name
    # to the closing paren, regardless of content
    pattern = r'    welcome_banner: str = \(.*?\)'
    match = re.search(pattern, src, re.DOTALL)
    if match:
        src = src[:match.start()] + NEW_BANNER + src[match.end():]
        write(CONFIG_PATH, src)
        print("  ✓ Welcome banner replaced")
    else:
        print("  FAIL — welcome_banner field not found")
        return False
    return True


def patch_client():
    """Remove the client-side ASCII art splash from client.html."""
    src = read(CLIENT_PATH)
    backup(CLIENT_PATH)
    original = src

    # Replace the showSplash function with a minimal version
    # Match the full function body
    old_splash_pattern = r"function showSplash\(\)\s*\{.*?\}"
    match = re.search(old_splash_pattern, src, re.DOTALL)
    if match:
        new_splash = """function showSplash() {
    systemMsg('Connecting to Mos Eisley...');
  }"""
        src = src[:match.start()] + new_splash + src[match.end():]
        print("  ✓ Client splash replaced with minimal version")
    else:
        print("  SKIP — showSplash not found")

    if src != original:
        write(CLIENT_PATH, src)
        print("  ✓ client.html patched")
    else:
        print("  ✗ No changes to client.html")


def validate():
    import ast
    try:
        ast.parse(read(CONFIG_PATH))
        print(f"  AST OK: config.py")
        return True
    except SyntaxError as e:
        print(f"  AST FAIL: config.py — {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Patch: Welcome Screen Overhaul")
    print("=" * 60)
    print()

    print("[config.py]")
    ok = patch_config()
    print()

    if ok:
        print("[client.html]")
        patch_client()
        print()

    print("[Validation]")
    if validate():
        print("\nPatch applied successfully.")
    else:
        print("\nVALIDATION FAILED.")
        sys.exit(1)
