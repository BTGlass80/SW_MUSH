#!/usr/bin/env python3
"""
web_client_wire_patch.py
------------------------
Wires the WebClient (browser client HTTP server) into the game server.

Changes:
  1. config.py: Adds web_client_host and web_client_port fields
  2. game_server.py: Adds import, __init__ instantiation, start(), stop()

Run from the SW_MUSH project root:
    python3 patches/web_client_wire_patch.py

Safe to re-run: skips if already wired.
"""

import ast
import sys
from pathlib import Path

CONFIG_FILE = Path("server/config.py")
SERVER_FILE = Path("server/game_server.py")

errors = []
for f in (CONFIG_FILE, SERVER_FILE):
    if not f.exists():
        errors.append(f"ERROR: {f} not found.")
if errors:
    for e in errors:
        print(e)
    print("Run from the SW_MUSH project root.")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════
#  PATCH 1: config.py — add web_client_host and web_client_port
# ══════════════════════════════════════════════════════════════

config_src = CONFIG_FILE.read_text(encoding="utf-8")

if "web_client_port" in config_src:
    print("✓ config.py already has web_client_port — skipping.")
else:
    # Insert after websocket_port line
    anchor = "    websocket_port: int = 4001"
    insert = (
        "    websocket_port: int = 4001\n"
        "    web_client_host: str = \"0.0.0.0\"\n"
        "    web_client_port: int = 8080"
    )

    if anchor in config_src:
        config_src = config_src.replace(anchor, insert, 1)
        try:
            ast.parse(config_src)
        except SyntaxError as e:
            print(f"ERROR: config.py patch failed syntax check: {e}")
            sys.exit(1)
        CONFIG_FILE.write_text(config_src, encoding="utf-8")
        print("  + config.py: Added web_client_host/web_client_port after websocket_port")
    else:
        print("WARNING: Could not find anchor in config.py:")
        print(f"    {anchor}")
        print("Add manually:")
        print('    web_client_host: str = "0.0.0.0"')
        print("    web_client_port: int = 8080")


# ══════════════════════════════════════════════════════════════
#  PATCH 2: game_server.py — import, init, start, stop
# ══════════════════════════════════════════════════════════════

src = SERVER_FILE.read_text(encoding="utf-8")

if "WebClient" in src:
    print("✓ game_server.py already has WebClient — skipping.")
    sys.exit(0)


# ── Step 2a: Add import ──
IMPORT_ANCHOR = "from server.websocket_handler import WebSocketHandler"
IMPORT_LINE = "from server.web_client import WebClient"

if IMPORT_ANCHOR in src:
    src = src.replace(
        IMPORT_ANCHOR,
        IMPORT_ANCHOR + "\n" + IMPORT_LINE,
        1,
    )
    print("  + Import: added after WebSocketHandler import")
else:
    print("WARNING: Could not find import anchor. Add manually:")
    print(f"    {IMPORT_LINE}")


# ── Step 2b: Instantiate in __init__ ──
INIT_ANCHOR = "        self.websocket = WebSocketHandler(self)"
INIT_LINE = "        self.web_client = WebClient()"

if INIT_ANCHOR in src:
    src = src.replace(
        INIT_ANCHOR,
        INIT_ANCHOR + "\n" + INIT_LINE,
        1,
    )
    print("  + __init__: added self.web_client = WebClient()")
else:
    print("WARNING: Could not find __init__ anchor. Add manually:")
    print(f"    {INIT_LINE}")


# ── Step 2c: Start in start() ──
# Insert after the websocket.start() block
START_ANCHOR = (
    "        await self.websocket.start(\n"
    "            self.config.websocket_host, self.config.websocket_port\n"
    "        )"
)
START_INSERT = (
    "        await self.websocket.start(\n"
    "            self.config.websocket_host, self.config.websocket_port\n"
    "        )\n"
    "\n"
    "        # Web client (browser UI)\n"
    "        await self.web_client.start(\n"
    "            self.config.web_client_host, self.config.web_client_port\n"
    "        )"
)

if START_ANCHOR in src:
    src = src.replace(START_ANCHOR, START_INSERT, 1)
    print("  + start(): added web_client.start() after websocket.start()")
else:
    print("WARNING: Could not find start() anchor. Add manually.")


# ── Step 2d: Update log.info to include web client port ──
LOG_ANCHOR = (
    '        log.info(\n'
    '            "%s is running. Telnet:%d  WebSocket:%d",\n'
    '            self.config.game_name,\n'
    '            self.config.telnet_port,\n'
    '            self.config.websocket_port,\n'
    '        )'
)
LOG_REPLACE = (
    '        log.info(\n'
    '            "%s is running. Telnet:%d  WebSocket:%d  WebClient:%d",\n'
    '            self.config.game_name,\n'
    '            self.config.telnet_port,\n'
    '            self.config.websocket_port,\n'
    '            self.config.web_client_port,\n'
    '        )'
)

if LOG_ANCHOR in src:
    src = src.replace(LOG_ANCHOR, LOG_REPLACE, 1)
    print("  + start(): updated log.info to include WebClient port")
else:
    print("NOTE: Could not find log.info anchor — cosmetic only, skipping.")


# ── Step 2e: Stop in stop() ──
STOP_ANCHOR = "        await self.websocket.stop()"
STOP_INSERT = (
    "        await self.websocket.stop()\n"
    "        await self.web_client.stop()"
)

if STOP_ANCHOR in src:
    src = src.replace(STOP_ANCHOR, STOP_INSERT, 1)
    print("  + stop(): added web_client.stop() after websocket.stop()")
else:
    print("WARNING: Could not find stop() anchor. Add manually.")


# ── Step 2f: Syntax validation ──
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"\nERROR: Patched game_server.py failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

SERVER_FILE.write_text(src, encoding="utf-8")
print("\n✓ game_server.py patched successfully.")
print("\nRemember to: pip install aiohttp")
print("Then restart the server. Browser client at http://localhost:8080/")
