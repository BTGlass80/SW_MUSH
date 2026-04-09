# -*- coding: utf-8 -*-
"""
patch_tier1_wiring.py — Wire Tier 1 web client enhancements.

Three features, all surfacing existing data to the web client:

1. ALERT LEVEL in hud_update
   - Reads Director's get_alert_level() for the current zone
   - Adds 'alert_level' field to hud_update JSON
   - Client displays a color-coded badge under the room name

2. DIRECTOR NEWS BROADCAST
   - After each Faction Turn, broadcasts the headline as a
     {"type": "news_event"} JSON message to all WebSocket sessions
   - Client already handles news_event messages (comlink feed)

3. WORLD EVENT JSON BROADCAST
   - After event activation/expiry, sends {"type": "world_event"}
     JSON to all WebSocket sessions
   - Client shows a persistent banner at the top of the terminal

Usage:
    python patches/patch_tier1_wiring.py
"""

import ast
import os
import re
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def backup(path):
    bak = path + ".pre_tier1_bak"
    shutil.copy2(path, bak)
    print(f"  Backup: {bak}")

def normalize(src):
    """Normalize to LF, return (content, was_crlf)."""
    crlf = "\r\n" in src
    return src.replace("\r\n", "\n"), crlf

def restore_endings(content, was_crlf):
    if was_crlf:
        return content.replace("\n", "\r\n")
    return content

def validate(content, filename):
    try:
        ast.parse(content)
        return True
    except SyntaxError as e:
        print(f"  [ERROR] {filename} has syntax error: {e}")
        return False


# ══════════════════════════════════════════
#  1. session.py — add alert_level to HUD
# ══════════════════════════════════════════

def patch_session():
    path = os.path.join(ROOT, "server", "session.py")
    if not os.path.isfile(path):
        print(f"[SKIP] {path} not found")
        return False

    src, crlf = normalize(read_file(path))

    if "alert_level" in src:
        print("[OK] session.py already has alert_level. Skipping.")
        return True

    # Add alert_level and alert_faction to HUD dict
    anchor = '"zone_type": "",'
    if anchor not in src:
        # Maybe the zone patch wasn't applied
        anchor = '"exits": [],'
        if anchor not in src:
            print("[ERROR] Cannot find HUD dict anchor in session.py")
            return False
        replacement = '"exits": [],\n            "alert_level": "",\n            "alert_faction": "",'
    else:
        replacement = '"zone_type": "",\n            "alert_level": "",\n            "alert_faction": "",'

    src = src.replace(anchor, replacement, 1)

    # Add Director alert lookup after zone resolution block
    # Find the end of the zone resolution try/except
    zone_pass = "pass  # Non-critical — mood just stays default"
    if zone_pass not in src:
        # Try alternate text
        zone_pass = "pass  # Non-critical"
        # Find the second occurrence (first is exits, second is zone)
        idx1 = src.find(zone_pass)
        if idx1 >= 0:
            idx2 = src.find(zone_pass, idx1 + len(zone_pass))
            if idx2 >= 0:
                # Replace only the second occurrence
                pass

    # More robust: insert after the zone_type resolution block
    # Look for the block that sets zone_type and add alert after it
    alert_code = '''
        # Resolve alert level from Director AI
        try:
            from engine.director import get_director
            director = get_director()
            zone_key = hud.get("zone_type", "")
            if zone_key:
                alert = director.get_alert_level(zone_key)
                hud["alert_level"] = alert.value if alert else ""
                # Determine dominant faction
                zs = director.get_zone_state(zone_key)
                if zs:
                    factions = {"imperial": zs.imperial, "rebel": zs.rebel,
                                "criminal": zs.criminal, "independent": zs.independent}
                    hud["alert_faction"] = max(factions, key=factions.get)
        except Exception:
            pass  # Non-critical — alert badge just won't show
'''

    # Insert before the final send
    send_anchor = '        try:\n            await self._send(json.dumps({"type": "hud_update", **hud}))'
    if send_anchor not in src:
        print("[ERROR] Cannot find hud send anchor in session.py")
        return False

    src = src.replace(send_anchor, alert_code + "\n" + send_anchor, 1)

    if not validate(src, "session.py"):
        return False

    backup(path)
    write_file(path, restore_endings(src, crlf))
    print("[OK] session.py — added alert_level + alert_faction to hud_update")
    return True


# ══════════════════════════════════════════
#  2. director.py — broadcast news_event
# ══════════════════════════════════════════

def patch_director():
    path = os.path.join(ROOT, "engine", "director.py")
    if not os.path.isfile(path):
        print(f"[SKIP] {path} not found")
        return False

    src, crlf = normalize(read_file(path))

    if "news_event" in src:
        print("[OK] director.py already has news_event broadcast. Skipping.")
        return True

    # Find the headline log line and add broadcast after it
    anchor = 'log.info("[director] Faction Turn complete: %s", headline)'
    if anchor not in src:
        print("[ERROR] Cannot find Faction Turn log line in director.py")
        return False

    broadcast_code = '''
        # Broadcast headline to web clients as news_event
        try:
            import json as _json
            for _s in session_mgr.all:
                if (_s.is_in_game and hasattr(_s, 'protocol')
                        and _s.protocol.value == 'websocket'):
                    await _s._send(_json.dumps({
                        "type": "news_event",
                        "tag": "event",
                        "text": headline,
                    }))
        except Exception:
            pass  # Non-critical — news just won't appear in feed'''

    src = src.replace(anchor, anchor + "\n" + broadcast_code, 1)

    if not validate(src, "director.py"):
        return False

    backup(path)
    write_file(path, restore_endings(src, crlf))
    print("[OK] director.py — added news_event broadcast after Faction Turn")
    return True


# ══════════════════════════════════════════
#  3. world_events.py — send world_event JSON
# ══════════════════════════════════════════

def patch_world_events():
    path = os.path.join(ROOT, "engine", "world_events.py")
    if not os.path.isfile(path):
        print(f"[SKIP] {path} not found")
        return False

    src, crlf = normalize(read_file(path))

    if '"type": "world_event"' in src:
        print("[OK] world_events.py already has world_event JSON broadcast. Skipping.")
        return True

    # Patch _broadcast_activation to also send structured JSON
    old_activate = 'await session_mgr.broadcast(f"\\n  {text}")'
    if src.count(old_activate) < 2:
        # Some versions might differ
        pass

    # Find _broadcast_activation method and add JSON send
    activate_anchor = '    async def _broadcast_activation(self, event: ActiveEvent, session_mgr):'
    if activate_anchor not in src:
        print("[ERROR] Cannot find _broadcast_activation in world_events.py")
        return False

    # Replace the _broadcast_activation method entirely
    old_method = '''    async def _broadcast_activation(self, event: ActiveEvent, session_mgr):
        """Broadcast event activation announcement to all online players."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "Mos Eisley"
        text = edef.announce_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\\n  {text}")'''

    new_method = '''    async def _broadcast_activation(self, event: ActiveEvent, session_mgr):
        """Broadcast event activation announcement to all online players."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "Mos Eisley"
        text = edef.announce_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\\n  {text}")
        # Send structured world_event to web clients
        try:
            import json as _json
            for _s in session_mgr.all:
                if (_s.is_in_game and hasattr(_s, 'protocol')
                        and _s.protocol.value == 'websocket'):
                    await _s._send(_json.dumps({
                        "type": "world_event",
                        "action": "start",
                        "title": edef.name,
                        "effects": edef.effect_text,
                        "event_type": event.event_type,
                    }))
        except Exception:
            pass  # Non-critical'''

    if old_method not in src:
        print("[WARN] _broadcast_activation exact match failed — trying regex")
        # Try a more flexible match
        pattern = r'(    async def _broadcast_activation\(self, event: ActiveEvent, session_mgr\):.*?await session_mgr\.broadcast\(f"\\n  \{text\}"\))'
        match = re.search(pattern, src, re.DOTALL)
        if not match:
            print("[ERROR] Cannot match _broadcast_activation method body")
            return False
        src = src[:match.start()] + new_method + src[match.end():]
    else:
        src = src.replace(old_method, new_method, 1)

    # Do the same for _broadcast_expiry
    old_expiry = '''    async def _broadcast_expiry(self, event: ActiveEvent, session_mgr):
        """Broadcast event expiry announcement."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "Mos Eisley"
        text = edef.expire_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\\n  {text}")'''

    new_expiry = '''    async def _broadcast_expiry(self, event: ActiveEvent, session_mgr):
        """Broadcast event expiry announcement."""
        edef = event.event_def
        zone_name = ", ".join(_zone_display(z) for z in event.zones_affected) if event.zones_affected else "Mos Eisley"
        text = edef.expire_text.replace("{zone_name}", zone_name)
        await session_mgr.broadcast(f"\\n  {text}")
        # Send structured world_event end to web clients
        try:
            import json as _json
            for _s in session_mgr.all:
                if (_s.is_in_game and hasattr(_s, 'protocol')
                        and _s.protocol.value == 'websocket'):
                    await _s._send(_json.dumps({
                        "type": "world_event",
                        "action": "end",
                        "title": edef.name,
                        "event_type": event.event_type,
                    }))
        except Exception:
            pass  # Non-critical'''

    if old_expiry not in src:
        print("[WARN] _broadcast_expiry exact match failed — trying regex")
        pattern = r'(    async def _broadcast_expiry\(self, event: ActiveEvent, session_mgr\):.*?await session_mgr\.broadcast\(f"\\n  \{text\}"\))'
        match = re.search(pattern, src, re.DOTALL)
        if not match:
            print("[ERROR] Cannot match _broadcast_expiry method body")
            return False
        src = src[:match.start()] + new_expiry + src[match.end():]
    else:
        src = src.replace(old_expiry, new_expiry, 1)

    if not validate(src, "world_events.py"):
        return False

    backup(path)
    write_file(path, restore_endings(src, crlf))
    print("[OK] world_events.py — added world_event JSON broadcast on start/end")
    return True


# ══════════════════════════════════════════
#  Main
# ══════════════════════════════════════════

def main():
    print("=== Tier 1 Web Client Wiring ===\n")

    ok = True
    ok = patch_session() and ok
    ok = patch_director() and ok
    ok = patch_world_events() and ok

    if ok:
        print("\n[DONE] All Tier 1 patches applied successfully.")
        print("  - hud_update now includes alert_level + alert_faction")
        print("  - Director broadcasts news_event JSON on each Faction Turn")
        print("  - World events broadcast world_event JSON on start/end")
        print("  Replace static/client.html with the updated v4 client.")
    else:
        print("\n[WARN] Some patches had issues. Check output above.")


if __name__ == "__main__":
    main()
