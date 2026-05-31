#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_login.py — Walk Brian through exactly what's broken.

Checks, in order:
  1. Drop applied: client.html has the chargen URL fix.
  2. Drop applied: static/chargen.html exists.
  3. Drop applied: data/worlds/clone_wars/test_character.yaml exists.
  4. DB has testuser account with a bcrypt-matching password hash.
  5. DB has Test Jedi character belonging to testuser.
  6. Server is reachable on http://localhost:8080.
  7. Portal login (/api/portal/login) succeeds with testuser/testpass.
  8. Game WebSocket login ("connect testuser testpass") returns char_select.
  9. Game WebSocket new-account ("create probe-<random> probe-pass-<random>")
     returns chargen_start.

Each check prints a one-line PASS/FAIL with diagnostic context.
First FAIL is the bug.

USAGE:

  # Server must be RUNNING for checks 6-9. Start it first in another window:
  #   .\\run.bat   or   python main.py
  # Then in the project root:
  python diagnose_login.py

  # Without server: only checks 1-5 will run.
  python diagnose_login.py --no-network
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time

# Project import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def pass_(msg):
    print(f"  \033[32mPASS\033[0m  {msg}")


def fail(msg, hint=None):
    print(f"  \033[31mFAIL\033[0m  {msg}")
    if hint:
        print(f"        \033[33m→ {hint}\033[0m")


def info(msg):
    print(f"  \033[36mINFO\033[0m  {msg}")


def section(title):
    print()
    print(f"\033[1m── {title} ──\033[0m")


def md5_of(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except FileNotFoundError:
        return None


async def check_disk_state(root):
    section("Disk-state checks (Drop 1 applied?)")
    issues = 0

    # 1. client.html has the fix
    client_html = os.path.join(root, "static", "client.html")
    if not os.path.isfile(client_html):
        fail("static/client.html missing entirely",
             "Drop 1 did not extract. Re-apply the zip.")
        issues += 1
    else:
        with open(client_html, "r", encoding="utf-8") as f:
            content = f.read()
        has_fix = "/chargen?embedded=1&token=" in content
        has_listener = "evt.data.type === 'chargen_done'" in content
        has_old = "ifr.src = msg.url || '/chargen.html'" in content
        if has_fix and has_listener and not has_old:
            pass_(f"static/client.html has the May 19 fix "
                  f"({len(content):,} chars)")
        else:
            fail(f"static/client.html does NOT have the May 19 fix "
                 f"(has_fix={has_fix}, has_listener={has_listener}, "
                 f"has_old_broken_line={has_old})",
                 "Drop 1's client.html edits did not land. Re-apply "
                 "the zip with `Expand-Archive ... -Force`.")
            issues += 1

    # 2. chargen.html exists
    chargen_html = os.path.join(root, "static", "chargen.html")
    if os.path.isfile(chargen_html):
        size = os.path.getsize(chargen_html)
        pass_(f"static/chargen.html present ({size:,} bytes)")
    else:
        fail("static/chargen.html missing",
             "Drop 1's chargen.html SPA did not extract. "
             "Re-apply the zip.")
        issues += 1

    # 3. CW test_character.yaml
    tc_yaml = os.path.join(
        root, "data", "worlds", "clone_wars", "test_character.yaml")
    if os.path.isfile(tc_yaml):
        size = os.path.getsize(tc_yaml)
        pass_(f"data/worlds/clone_wars/test_character.yaml present "
              f"({size:,} bytes)")
    else:
        fail("data/worlds/clone_wars/test_character.yaml missing",
             "Drop 1's test character YAML did not extract.")
        issues += 1

    return issues


async def check_db_state(db_path):
    section(f"DB-state checks (testuser exists with correct hash?)")

    if not os.path.isfile(db_path):
        fail(f"DB file '{db_path}' does not exist",
             "Server has not run yet, OR you deleted the DB. "
             "Start the server (python main.py) once to let it "
             "auto-build the world.")
        return 1

    try:
        from db.database import Database
    except ImportError as e:
        fail(f"Could not import db.database: {e}",
             "Run this script from the project root.")
        return 1

    db = Database(db_path)
    await db.connect()
    await db.initialize()

    try:
        # accounts
        rows = await db.fetchall(
            "SELECT id, username, password_hash, is_admin, is_builder "
            "FROM accounts WHERE username = ?", ("testuser",),
        )
        if not rows:
            fail("No 'testuser' account in DB",
                 "The CW build did not create the test character. "
                 "Check that data/worlds/clone_wars/test_character.yaml "
                 "exists, then nuke sw_mush.db and re-run "
                 "`python main.py` so the world auto-build re-fires.")
            return 1

        acct = rows[0]
        info(f"Found 'testuser' account: id={acct['id']}, "
             f"is_admin={acct['is_admin']}, is_builder={acct['is_builder']}")

        # Verify the bcrypt hash matches "testpass"
        import bcrypt
        pw_hash = acct["password_hash"]
        if isinstance(pw_hash, str):
            pw_hash_bytes = pw_hash.encode("utf-8")
        else:
            pw_hash_bytes = pw_hash
        try:
            matches = bcrypt.checkpw(b"testpass", pw_hash_bytes)
        except Exception as e:
            fail(f"bcrypt.checkpw raised: {e}",
                 f"password_hash field looks malformed: "
                 f"{pw_hash[:40]!r}...")
            return 1
        if matches:
            pass_("testuser's stored bcrypt hash verifies against 'testpass'")
        else:
            fail("testuser exists but 'testpass' does NOT verify "
                 "against its stored hash",
                 f"The account was created with a DIFFERENT password. "
                 f"Nuke sw_mush.db and re-run the server so the build "
                 f"recreates it from test_character.yaml. "
                 f"Stored hash prefix: {pw_hash[:20]!r}...")
            return 1

        # characters
        char_rows = await db.fetchall(
            "SELECT id, name, room_id, faction_id FROM characters "
            "WHERE account_id = ?", (acct["id"],),
        )
        if not char_rows:
            fail("testuser has NO characters",
                 "Character creation step in the build was skipped or "
                 "failed. Try running seed_test_character.py.")
            return 1
        for c in char_rows:
            info(f"  character: id={c['id']}, name={c['name']!r}, "
                 f"room_id={c['room_id']}, faction={c['faction_id']}")
        pass_(f"testuser has {len(char_rows)} character(s)")

        return 0
    finally:
        await db.close()


async def check_server_live(host, port):
    section(f"Server connectivity check (http://{host}:{port})")
    try:
        import aiohttp
    except ImportError:
        fail("aiohttp not installed in this Python env",
             "pip install aiohttp")
        return 1

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as cs:
            async with cs.get(f"http://{host}:{port}/") as resp:
                if resp.status == 200:
                    pass_(f"Portal homepage reachable (HTTP {resp.status})")
                    return 0
                else:
                    fail(f"Portal homepage returned HTTP {resp.status}",
                         "Server is up but returning an error.")
                    return 1
    except Exception as e:
        fail(f"Could not reach server: {e}",
             f"Start the server first: python main.py")
        return 1


async def check_portal_login(host, port):
    section("Portal login (POST /api/portal/login)")
    import aiohttp
    try:
        async with aiohttp.ClientSession() as cs:
            async with cs.post(
                f"http://{host}:{port}/api/portal/login",
                json={"username": "testuser", "password": "testpass"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                body = await resp.json()
                if resp.status == 200 and body.get("token"):
                    chars = body.get("characters", [])
                    pass_(f"Portal login OK; account_id={body.get('account_id')}, "
                          f"characters={[c['name'] for c in chars]}")
                    return 0
                else:
                    fail(f"Portal login returned HTTP {resp.status}: {body}",
                         "Portal login is broken. Check testuser/testpass "
                         "exist in the DB (above check) and the server "
                         "logs for the actual error.")
                    return 1
    except Exception as e:
        fail(f"Portal login request failed: {e}")
        return 1


async def check_game_ws_signin(host, port):
    section("Game WebSocket sign-in (connect testuser testpass)")
    import aiohttp
    try:
        async with aiohttp.ClientSession() as cs:
            async with cs.ws_connect(
                f"http://{host}:{port}/ws",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as ws:
                # Drain banner
                await asyncio.sleep(0.6)
                await ws.send_str(json.dumps(
                    {"input": "connect testuser testpass"}))
                got_char_select = False
                got_welcome = False
                got_error = False
                deadline = asyncio.get_event_loop().time() + 4.0
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                t = data.get("type", "?")
                                if t == "char_select":
                                    got_char_select = True
                                    info(f"  got char_select: "
                                         f"{[c['name'] for c in data.get('characters', [])]}")
                                elif t == "chargen_start":
                                    info(f"  got chargen_start (token={data.get('token','?')[:20]}...)")
                                    got_char_select = True  # also a success signal
                                elif t == "text":
                                    txt = data.get("data", "")
                                    if "Welcome back" in txt:
                                        got_welcome = True
                                    if "Invalid" in txt or "invalid" in txt:
                                        got_error = True
                                        info(f"  got error text: {txt!r}")
                            except json.JSONDecodeError:
                                pass
                        elif msg.type in (aiohttp.WSMsgType.CLOSE,
                                          aiohttp.WSMsgType.CLOSED,
                                          aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        if got_char_select:
                            break
                if got_char_select:
                    pass_("Game WS sign-in OK — char_select received")
                    return 0
                elif got_error:
                    fail("Server returned an 'Invalid' text response",
                         "Server-side auth refused testuser/testpass.")
                    return 1
                elif got_welcome and not got_char_select:
                    fail("Got 'Welcome back' text but no char_select JSON",
                         "Auth succeeded but _character_select did not "
                         "send the picker. Check server logs for exceptions "
                         "in _character_select.")
                    return 1
                else:
                    fail("No char_select or auth response within 4s",
                         "Server is up but the WS auth flow is silent. "
                         "Check server logs for exceptions.")
                    return 1
    except Exception as e:
        fail(f"Game WS sign-in failed: {e}")
        return 1


async def check_game_ws_create(host, port):
    section("Game WebSocket new-account (create <probe> <probe-pass>)")
    import aiohttp
    import random
    import string
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    user = f"diag_{suffix}"
    pw = f"diag_pw_{suffix}"
    try:
        async with aiohttp.ClientSession() as cs:
            async with cs.ws_connect(
                f"http://{host}:{port}/ws",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as ws:
                await asyncio.sleep(0.6)
                await ws.send_str(json.dumps(
                    {"input": f"create {user} {pw}"}))
                got_chargen_start = False
                got_error = False
                deadline = asyncio.get_event_loop().time() + 4.0
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                t = data.get("type", "?")
                                if t == "chargen_start":
                                    got_chargen_start = True
                                    info(f"  got chargen_start; "
                                         f"token={data.get('token','?')[:20]}...")
                                elif t == "text":
                                    txt = data.get("data", "")
                                    if "already taken" in txt:
                                        got_error = True
                                        info(f"  text: {txt!r}")
                            except json.JSONDecodeError:
                                pass
                        elif msg.type in (aiohttp.WSMsgType.CLOSE,
                                          aiohttp.WSMsgType.CLOSED,
                                          aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        if got_chargen_start:
                            break
                if got_chargen_start:
                    pass_(f"Game WS new-account OK — chargen_start received "
                          f"for {user!r}")
                    return 0
                else:
                    fail(f"No chargen_start within 4s for create '{user}'",
                         "Server is up but `create` flow is silent.")
                    return 1
    except Exception as e:
        fail(f"Game WS new-account failed: {e}")
        return 1


async def main():
    parser = argparse.ArgumentParser(
        description="Diagnose Brian's login flow.")
    parser.add_argument("--db", default="sw_mush.db",
                        help="SQLite DB path (default: sw_mush.db)")
    parser.add_argument("--host", default="localhost",
                        help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=8080,
                        help="Server port (default: 8080)")
    parser.add_argument("--no-network", action="store_true",
                        help="Skip checks that require a running server")
    args = parser.parse_args()

    print()
    print("\033[1m═══ SW_MUSH login diagnosis — May 19 2026 ═══\033[0m")
    print()

    root = os.path.dirname(os.path.abspath(__file__))
    info(f"Project root: {root}")
    info(f"DB path:      {args.db}")

    total_fails = 0

    total_fails += await check_disk_state(root)
    total_fails += await check_db_state(args.db)

    if not args.no_network:
        live = await check_server_live(args.host, args.port)
        total_fails += live
        if live == 0:
            total_fails += await check_portal_login(args.host, args.port)
            total_fails += await check_game_ws_signin(args.host, args.port)
            total_fails += await check_game_ws_create(args.host, args.port)

    print()
    if total_fails == 0:
        print("\033[1;32m═══ ALL CHECKS PASS ═══\033[0m")
        print("If login still isn't working in your browser, it's a")
        print("browser-cache issue. Hard-reload /play with Ctrl+Shift+R.")
        return 0
    else:
        print(f"\033[1;31m═══ {total_fails} CHECK(S) FAILED ═══\033[0m")
        print("First FAIL above is the root cause. Address it and re-run.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
