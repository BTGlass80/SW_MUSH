#!/usr/bin/env python3
"""
web_client_main_patch.py
------------------------
Adds --web-port argument to main.py so the browser client port
is configurable from the command line.

Run from the SW_MUSH project root:
    python3 patches/web_client_main_patch.py

Safe to re-run: skips if already present.
"""

import ast
import sys
from pathlib import Path

TARGET = Path("main.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")

if "web-port" in src or "web_port" in src:
    print("✓ main.py already has --web-port — skipping.")
    sys.exit(0)

# ── Step 1: Add argparse argument after --ws-port ──
ARG_ANCHOR = '''    parser.add_argument(
        "--ws-port", type=int, default=4001,
        help="WebSocket listen port (default: 4001)",
    )'''

ARG_INSERT = '''    parser.add_argument(
        "--ws-port", type=int, default=4001,
        help="WebSocket listen port (default: 4001)",
    )
    parser.add_argument(
        "--web-port", type=int, default=8080,
        help="Web client HTTP port (default: 8080)",
    )'''

if ARG_ANCHOR in src:
    src = src.replace(ARG_ANCHOR, ARG_INSERT, 1)
    print("  + Added --web-port argument")
else:
    print("WARNING: Could not find --ws-port argument anchor.")
    print("Add --web-port argument manually.")

# ── Step 2: Pass web_client_port to Config ──
CONFIG_ANCHOR = '''    config = Config(
        telnet_port=args.telnet_port,
        websocket_port=args.ws_port,
        db_path=args.db,
    )'''

CONFIG_INSERT = '''    config = Config(
        telnet_port=args.telnet_port,
        websocket_port=args.ws_port,
        web_client_port=args.web_port,
        db_path=args.db,
    )'''

if CONFIG_ANCHOR in src:
    src = src.replace(CONFIG_ANCHOR, CONFIG_INSERT, 1)
    print("  + Passed web_client_port to Config constructor")
else:
    print("WARNING: Could not find Config constructor anchor.")
    print("Add web_client_port=args.web_port manually.")

# ── Syntax validation ──
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"\nERROR: Patched main.py failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("\n✓ main.py patched successfully.")
print("Usage: python main.py --web-port 8080")
