#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drop4_wire_patch.py
-------------------
Drop 4 wire patch for SW_MUSH Director AI system.

Applies three changes:

  1. ai/providers.py
     — Register ClaudeProvider in AIManager._setup_providers()

  2. engine/director.py
     — Add _run_api_turn() method to DirectorAI
     — Patch faction_turn() to attempt API call before local fallback

  3. server/game_server.py
     — Import + register director_commands and news_commands

Run from the SW_MUSH project root:
    python patches/drop4_wire_patch.py

Safe to re-run: each step checks if already applied before modifying.
"""

import ast
import shutil
import sys
from pathlib import Path

# ── Target files ──────────────────────────────────────────────────────────────
PROVIDERS  = Path("ai/providers.py")
DIRECTOR   = Path("engine/director.py")
GAMESERVER = Path("server/game_server.py")

for f in (PROVIDERS, DIRECTOR, GAMESERVER):
    if not f.exists():
        print(f"ERROR: {f} not found. Run from the SW_MUSH project root.")
        sys.exit(1)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, src: str) -> None:
    p.write_text(src, encoding="utf-8")


def validate(p: Path, src: str) -> bool:
    try:
        ast.parse(src)
        return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {p}: {e}")
        return False


def backup(p: Path) -> None:
    bak = p.with_suffix(p.suffix + ".drop4_bak")
    shutil.copy2(p, bak)
    print(f"  Backup: {bak.name}")


# ══════════════════════════════════════════════════════════════════════════════
#  PATCH 1: ai/providers.py — register ClaudeProvider
# ══════════════════════════════════════════════════════════════════════════════
print("\n── ai/providers.py ──────────────────────────────────────────────────────")

src = read(PROVIDERS)

if "claude_provider" in src or "ClaudeProvider" in src:
    print("✓ ClaudeProvider already registered — skipping.")
else:
    # Step 1a: Add import after the existing imports block
    # The file starts with standard imports; we add ours before the AIConfig class.
    # Reliable anchor: the AIConfig dataclass definition.
    IMPORT_INSERT = (
        "# ── Claude provider (optional, requires ANTHROPIC_API_KEY) ──\n"
        "from ai.claude_provider import make_claude_provider\n"
        "\n"
    )
    IMPORT_ANCHOR = "# ── Configuration ──"
    ALT_IMPORT_ANCHOR = "@dataclass\nclass AIConfig:"

    patched = src
    if IMPORT_ANCHOR in patched:
        patched = patched.replace(IMPORT_ANCHOR, IMPORT_INSERT + IMPORT_ANCHOR, 1)
        print("  + Import inserted before '# ── Configuration ──'")
    elif ALT_IMPORT_ANCHOR in patched:
        patched = patched.replace(ALT_IMPORT_ANCHOR, IMPORT_INSERT + ALT_IMPORT_ANCHOR, 1)
        print("  + Import inserted before AIConfig dataclass")
    else:
        print("  WARNING: Could not find import anchor in ai/providers.py")
        print(f"  Add manually:\n{IMPORT_INSERT}")

    # Step 1b: Register Claude in _setup_providers()
    # Anchor: end of _setup_providers(), after the "Always have a mock as fallback" block.
    # The method ends with: self.providers["mock"] = MockProvider()
    CALL_ANCHOR   = '        self.providers["mock"] = MockProvider()'
    CALL_INSERT   = (
        '        self.providers["mock"] = MockProvider()\n'
        '        # Optional: Claude API provider (Director AI)\n'
        '        _claude = make_claude_provider()\n'
        '        if _claude is not None:\n'
        '            self.providers["claude"] = _claude\n'
        '            log.info("ClaudeProvider registered (Director AI).")'
    )

    if CALL_ANCHOR in patched:
        patched = patched.replace(CALL_ANCHOR, CALL_INSERT, 1)
        print("  + ClaudeProvider registration inserted in _setup_providers()")
    else:
        print("  WARNING: Could not find _setup_providers anchor.")
        print(f"  Add manually after self.providers[\"mock\"] = MockProvider():\n")
        print('        _claude = make_claude_provider()')
        print('        if _claude is not None:')
        print('            self.providers["claude"] = _claude')

    if not validate(PROVIDERS, patched):
        print("  File unchanged.")
    else:
        backup(PROVIDERS)
        write(PROVIDERS, patched)
        print("✓ ai/providers.py patched.")


# ══════════════════════════════════════════════════════════════════════════════
#  PATCH 2: engine/director.py — add _run_api_turn() + wire into faction_turn()
# ══════════════════════════════════════════════════════════════════════════════
print("\n── engine/director.py ───────────────────────────────────────────────────")

src = read(DIRECTOR)

if "_run_api_turn" in src:
    print("✓ _run_api_turn already present — skipping.")
else:
    # The _run_api_turn method body to insert.
    # We insert it as a new method on DirectorAI.
    # Anchor: the get_recent_log method definition (reliable, unique)
    # Fallback: async def reset_influence
    API_TURN_METHOD = '''
    async def _run_api_turn(
        self,
        db,
        session_mgr,
        ai_mgr,
    ) -> bool:
        """
        Attempt a Faction Turn via the Claude API.

        Compiles the world-state digest, sends it to ClaudeProvider,
        parses and validates the JSON response, then applies:
          - influence_adjustments to zone influence scores
          - narrative_event to WorldEventManager (if present)
          - ambient_pool to AmbientEventManager (if present)
          - news_headline to director_log

        Returns True if the API turn succeeded, False if fallback needed.
        """
        import json as _json

        # Check provider availability
        claude = ai_mgr.providers.get("claude") if ai_mgr else None
        if not claude:
            return False
        if not await claude.is_available():
            return False

        # Build the director system prompt (static, cacheable)
        system_prompt = (
            "You are the Director AI for a Star Wars MUSH set in Mos Eisley, Tatooine.\\n"
            "Your role is to evaluate the current state of the galaxy and decide what\\n"
            "happens next at the MACRO level. You never narrate player actions or\\n"
            "describe what individual characters do. You move the unseen pieces:\\n"
            "faction responses, economic shifts, atmospheric changes, and emerging\\n"
            "threats.\\n\\n"
            "You are guided by these principles:\\n"
            "- The Empire reacts to resistance with escalation, not retreat.\\n"
            "- The criminal underworld fills any vacuum the Empire leaves.\\n"
            "- The Rebel Alliance operates in shadows; their influence is felt\\n"
            "  through sabotage and propaganda, not open warfare on Tatooine.\\n"
            "- Tatooine is a backwater. The Empire cares about order, not ideology.\\n"
            "  The Hutts care about profit. Neither wants open war here.\\n"
            "- Events should create OPPORTUNITIES for players, never OBLIGATIONS.\\n"
            "- Consequences should feel proportional and narratively logical.\\n\\n"
            "Respond with ONLY a JSON object in this exact format:\\n"
            "{\\n"
            "  \\"influence_adjustments\\": [\\n"
            "    {\\"zone\\": \\"...\\", \\"faction\\": \\"...\\", \\"delta\\": <int>}\\n"
            "  ],\\n"
            "  \\"narrative_event\\": {\\n"
            "    \\"type\\": \\"...\\",\\n"
            "    \\"headline\\": \\"...\\",\\n"
            "    \\"duration_minutes\\": <int>,\\n"
            "    \\"zones_affected\\": [\\"...\\"],\\n"
            "    \\"mechanical_effects\\": {\\"...\\": \\"...\\"}\\n"
            "  } OR null,\\n"
            "  \\"ambient_pool\\": [\\"line1\\", \\"line2\\", \\"line3\\"] OR null,\\n"
            "  \\"news_headline\\": \\"One-sentence summary for the world events board.\\"\\n"
            "}"
        )

        # Compile digest
        digest = await self.compile_digest(session_mgr)
        user_message = _json.dumps(digest, ensure_ascii=False)

        # Call API
        try:
            raw = await claude.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=1000,
                temperature=0.7,
            )
        except Exception as exc:
            log.warning("[director] Claude API call failed: %s", exc)
            return False

        if not raw:
            log.debug("[director] Claude returned empty response — using local fallback.")
            return False

        # Parse JSON response
        try:
            # Strip possible markdown fences
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\\n")
                cleaned = "\\n".join(
                    l for l in lines if not l.strip().startswith("```")
                )
            resp = _json.loads(cleaned)
        except _json.JSONDecodeError as exc:
            log.warning("[director] JSON parse failed: %s — raw: %.200s", exc, raw)
            return False

        # ── Validate & apply influence adjustments ─────────────────────────
        VALID_ZONES    = frozenset(self._influence.keys())
        VALID_FACTIONS = frozenset({"imperial", "rebel", "criminal", "independent"})
        EVENT_TYPES    = frozenset({
            "imperial_crackdown", "imperial_checkpoint", "bounty_surge",
            "merchant_arrival", "sandstorm", "cantina_brawl", "distress_signal",
            "pirate_surge", "hutt_auction", "krayt_sighting",
            "rebel_propaganda", "trade_boom",
        })

        adjustments = resp.get("influence_adjustments", [])
        if isinstance(adjustments, list):
            for adj in adjustments:
                zone    = adj.get("zone", "")
                faction = adj.get("faction", "")
                delta   = adj.get("delta", 0)
                if zone not in VALID_ZONES:
                    log.debug("[director] Skipping invalid zone '%s'", zone)
                    continue
                if faction not in VALID_FACTIONS:
                    log.debug("[director] Skipping invalid faction '%s'", faction)
                    continue
                delta = max(-5, min(5, int(delta)))  # clamp ±5
                await self._apply_influence_delta(db, zone, faction, delta)

        # ── Apply narrative event ──────────────────────────────────────────
        narrative_event = resp.get("narrative_event")
        if isinstance(narrative_event, dict):
            evt_type = narrative_event.get("type", "")
            if evt_type in EVENT_TYPES:
                duration = int(narrative_event.get("duration_minutes", 30))
                duration = max(15, min(120, duration))
                zones    = narrative_event.get("zones_affected", [])
                if isinstance(zones, str):
                    zones = [zones]
                headline = narrative_event.get("headline", evt_type)
                try:
                    from engine.world_events import get_world_event_manager
                    wem = get_world_event_manager()
                    activated = await wem.activate_event(
                        db, session_mgr,
                        event_type=evt_type,
                        zones_affected=zones,
                        duration_minutes=duration,
                        headline=headline,
                        source="director",
                    )
                    if activated:
                        log.info(
                            "[director] Narrative event activated: %s (zones: %s)",
                            evt_type, zones,
                        )
                except Exception as exc:
                    log.warning("[director] Failed to activate narrative event: %s", exc)
            else:
                log.debug("[director] Invalid event type '%s' — ignored.", evt_type)

        # ── Update dynamic ambient pool ────────────────────────────────────
        ambient_pool = resp.get("ambient_pool")
        if isinstance(ambient_pool, list):
            online_names = set()
            try:
                online_names = {
                    s.char_name.lower()
                    for s in session_mgr.sessions.values()
                    if getattr(s, "char_name", None)
                }
            except Exception:
                pass
            BAD_KEYWORDS = frozenset({"roll", "attack", "skill check", "dice"})
            valid_lines = []
            for line in ambient_pool:
                if not isinstance(line, str):
                    continue
                line = line.strip()
                if not line or len(line) > 120:
                    continue
                lower = line.lower()
                if any(kw in lower for kw in BAD_KEYWORDS):
                    continue
                if any(name in lower for name in online_names):
                    continue
                valid_lines.append(line)
            if valid_lines:
                try:
                    from engine.ambient_events import get_ambient_manager
                    get_ambient_manager().set_dynamic_pool(valid_lines)
                    log.debug(
                        "[director] Dynamic ambient pool updated (%d lines).",
                        len(valid_lines),
                    )
                except Exception as exc:
                    log.warning("[director] Failed to update ambient pool: %s", exc)

        # ── Write director log ─────────────────────────────────────────────
        news_headline = str(resp.get("news_headline", "Faction Turn complete."))[:200]
        details_json  = _json.dumps(resp, ensure_ascii=False)[:4000]

        # Get token counts from ClaudeProvider budget stats
        stats      = claude.get_budget_stats()
        # Approximate call tokens — ClaudeProvider tracks cumulatively.
        # For the log we store 0/0 (exact per-call tracking would require
        # returning from generate(); good enough for audit purposes).
        tok_in  = 0
        tok_out = 0

        await self._write_log(
            db,
            event_type="faction_turn",
            summary=news_headline,
            details_json=details_json,
            token_cost_input=tok_in,
            token_cost_output=tok_out,
        )

        return True
'''

    # Find a reliable insertion point: just before get_recent_log or reset_influence
    INSERT_ANCHORS = [
        "    async def get_recent_log(",
        "    async def reset_influence(",
        "    def get_alert_level(",
        "    async def compile_digest(",
    ]

    patched = src
    inserted = False
    for anchor in INSERT_ANCHORS:
        if anchor in patched:
            patched = patched.replace(anchor, API_TURN_METHOD + "\n" + anchor, 1)
            print(f"  + _run_api_turn() inserted before '{anchor.strip()}'")
            inserted = True
            break

    if not inserted:
        print("  WARNING: Could not find insertion anchor for _run_api_turn().")
        print("  Add the method manually to engine/director.py.")

    # Now patch faction_turn() to call _run_api_turn first.
    # We look for the enabled guard that currently begins faction_turn,
    # then insert the API call right after it sets _turn_in_flight = True.
    #
    # Typical pattern from Drop 3 design:
    #   self._turn_in_flight = True
    #   try:
    #       ...
    #
    # We insert: if await self._run_api_turn(db, session_mgr, ai_mgr): ...
    #
    # Strategy: find the first "self._turn_in_flight = True" and insert after it.

    TURN_ANCHOR = "        self._turn_in_flight = True"
    TURN_INSERT = (
        "        self._turn_in_flight = True\n"
        "        # Attempt API-driven Faction Turn first\n"
        "        try:\n"
        "            _ai_mgr = getattr(session_mgr, '_ai_manager', None)\n"
        "            if _ai_mgr and await self._run_api_turn(db, session_mgr, _ai_mgr):\n"
        "                self._turn_in_flight = False\n"
        "                return  # API turn handled everything\n"
        "        except Exception as _api_exc:\n"
        "            log.warning('[director] API turn error: %s — using local fallback', _api_exc)"
    )

    if TURN_ANCHOR in patched:
        patched = patched.replace(TURN_ANCHOR, TURN_INSERT, 1)
        print("  + faction_turn() API call hook inserted after _turn_in_flight = True")
    else:
        # Fallback: look for the apply_player_action_deltas call
        ALT_TURN_ANCHOR = "        await self.apply_player_action_deltas(db)"
        ALT_TURN_INSERT = (
            "        # Attempt API-driven Faction Turn first\n"
            "        _ai_mgr = getattr(session_mgr, '_ai_manager', None)\n"
            "        if _ai_mgr:\n"
            "            try:\n"
            "                if await self._run_api_turn(db, session_mgr, _ai_mgr):\n"
            "                    return  # API turn handled everything\n"
            "            except Exception as _api_exc:\n"
            "                log.warning('[director] API turn error: %s', _api_exc)\n"
            "        await self.apply_player_action_deltas(db)"
        )
        if ALT_TURN_ANCHOR in patched:
            patched = patched.replace(ALT_TURN_ANCHOR, ALT_TURN_INSERT, 1)
            print("  + faction_turn() API call hook inserted before apply_player_action_deltas()")
        else:
            print("  WARNING: Could not find faction_turn() anchor. Add API call manually.")

    if not validate(DIRECTOR, patched):
        print("  engine/director.py unchanged.")
    else:
        backup(DIRECTOR)
        write(DIRECTOR, patched)
        print("✓ engine/director.py patched.")


# ══════════════════════════════════════════════════════════════════════════════
#  PATCH 3: server/game_server.py — import + register director and news commands
# ══════════════════════════════════════════════════════════════════════════════
print("\n── server/game_server.py ────────────────────────────────────────────────")

src = read(GAMESERVER)

gs_patched = src
gs_changed = False

# Import director_commands
if "register_director_commands" not in gs_patched:
    IMPORT_LINE = "from parser.director_commands import register_director_commands"
    for anchor in [
        "from parser.bounty_commands import register_bounty_commands",
        "from parser.mission_commands import register_mission_commands",
        "from parser.crew_commands import register_crew_commands",
    ]:
        if anchor in gs_patched:
            gs_patched = gs_patched.replace(anchor, anchor + "\n" + IMPORT_LINE, 1)
            print(f"  + director_commands import inserted after: {anchor}")
            gs_changed = True
            break
    else:
        print(f"  WARNING: Could not find import anchor. Add manually:\n    {IMPORT_LINE}")
else:
    print("  ✓ register_director_commands import already present")

# Import news_commands
if "register_news_commands" not in gs_patched:
    IMPORT_LINE2 = "from parser.news_commands import register_news_commands"
    if "register_director_commands" in gs_patched:
        gs_patched = gs_patched.replace(
            "from parser.director_commands import register_director_commands",
            "from parser.director_commands import register_director_commands\n" + IMPORT_LINE2,
            1,
        )
        print("  + news_commands import inserted after director_commands import")
        gs_changed = True
    else:
        print(f"  WARNING: Add manually:\n    {IMPORT_LINE2}")
else:
    print("  ✓ register_news_commands import already present")

# Register director_commands call
if "register_director_commands(self.registry)" not in gs_patched:
    CALL_LINE = "        register_director_commands(self.registry)"
    for anchor in [
        "        register_bounty_commands(self.registry)",
        "        register_mission_commands(self.registry)",
        "        register_crew_commands(self.registry)",
    ]:
        if anchor in gs_patched:
            gs_patched = gs_patched.replace(anchor, anchor + "\n" + CALL_LINE, 1)
            print(f"  + register_director_commands() call inserted after: {anchor.strip()}")
            gs_changed = True
            break
    else:
        print(f"  WARNING: Could not find call anchor. Add manually:\n    {CALL_LINE.strip()}")
else:
    print("  ✓ register_director_commands() call already present")

# Register news_commands call
if "register_news_commands(self.registry)" not in gs_patched:
    CALL_LINE2 = "        register_news_commands(self.registry)"
    if "register_director_commands(self.registry)" in gs_patched:
        gs_patched = gs_patched.replace(
            "        register_director_commands(self.registry)",
            "        register_director_commands(self.registry)\n" + CALL_LINE2,
            1,
        )
        print("  + register_news_commands() call inserted after director_commands call")
        gs_changed = True
    else:
        print(f"  WARNING: Add manually:\n    {CALL_LINE2.strip()}")
else:
    print("  ✓ register_news_commands() call already present")

if gs_changed:
    if not validate(GAMESERVER, gs_patched):
        print("  server/game_server.py unchanged.")
    else:
        backup(GAMESERVER)
        write(GAMESERVER, gs_patched)
        print("✓ server/game_server.py patched.")
else:
    print("✓ server/game_server.py already up to date — nothing to do.")


# ══════════════════════════════════════════════════════════════════════════════
#  Final validation summary
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Final syntax check ───────────────────────────────────────────────────")
all_ok = True
for target in (PROVIDERS, DIRECTOR, GAMESERVER):
    try:
        ast.parse(read(target))
        print(f"  OK  {target}")
    except SyntaxError as e:
        print(f"  ERR {target}: {e}")
        all_ok = False

print()
if all_ok:
    print("Drop 4 wire patch complete.")
    print()
    print("Enable the Director:")
    print("  export ANTHROPIC_API_KEY=sk-ant-...")
    print("  (restart server)")
    print("  @director enable")
    print()
    print("Check status:  @director status")
    print("Check budget:  @director budget")
    print("Force a turn:  @director trigger")
    print("World news:    news")
else:
    print("WARNING: Some files failed syntax check. Review errors above.")
    sys.exit(1)
