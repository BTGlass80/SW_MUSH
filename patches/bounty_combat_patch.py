#!/usr/bin/env python3
"""
bounty_combat_patch.py
----------------------
Injects the bounty board kill-notification hook into the NPC death
path inside _apply_combat_wear() in parser/combat_commands.py.

When an NPC with is_bounty_target=True is killed in combat, the
bounty board is automatically notified and the contract collected
for the killer.

Run from the SW_MUSH project root:
    python3 bounty_combat_patch.py

Safe to re-run: skips if hook is already present.
"""

import ast
import sys
from pathlib import Path

TARGET = Path("parser/combat_commands.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Already patched? ───────────────────────────────────────────────────────────

if "notify_target_killed" in source:
    print("✓ Bounty kill hook already present — nothing to do.")
    sys.exit(0)

# ── Locate anchor ──────────────────────────────────────────────────────────────
#
# The NPC wound-persist block in _apply_combat_wear looks like:
#
#     if c.is_npc:
#         try:
#             npc_row = await ctx.db.get_npc(c.id)
#             if npc_row:
#                 cs = _json.loads(npc_row.get("char_sheet_json", "{}"))
#                 cs["wound_level"] = c.char.wound_level.value
#                 await ctx.db.update_npc(
#                     c.id, char_sheet_json=_json.dumps(cs)
#                 )
#         except Exception as e:
#             log.warning("Failed to save NPC %s wound: %s", c.name, e)
#         continue
#
# We inject the bounty hook between the update_npc call and the `continue`.

OLD_BLOCK = """\
        if c.is_npc:
            try:
                npc_row = await ctx.db.get_npc(c.id)
                if npc_row:
                    cs = _json.loads(npc_row.get("char_sheet_json", "{}"))
                    cs["wound_level"] = c.char.wound_level.value
                    await ctx.db.update_npc(
                        c.id, char_sheet_json=_json.dumps(cs)
                    )
            except Exception as e:
                log.warning("Failed to save NPC %s wound: %s", c.name, e)
            continue"""

NEW_BLOCK = """\
        if c.is_npc:
            try:
                npc_row = await ctx.db.get_npc(c.id)
                if npc_row:
                    cs = _json.loads(npc_row.get("char_sheet_json", "{}"))
                    cs["wound_level"] = c.char.wound_level.value
                    await ctx.db.update_npc(
                        c.id, char_sheet_json=_json.dumps(cs)
                    )
                    # ── Bounty kill hook ──────────────────────────────────
                    # If this NPC is a bounty target and just died, auto-
                    # collect the contract for the player who killed them.
                    from engine.character import WoundLevel as _WL
                    if c.char.wound_level.value >= _WL.DEAD.value:
                        try:
                            _ai_cfg = _json.loads(
                                npc_row.get("ai_config_json", "{}")
                            )
                            if _ai_cfg.get("is_bounty_target"):
                                from engine.bounty_board import get_bounty_board
                                _board = get_bounty_board()
                                # Find the player who dealt the killing blow
                                # (first non-NPC attacker in this round)
                                _killer_id = None
                                for _ac in combat.combatants.values():
                                    if not _ac.is_npc and any(
                                        _a.action_type == ActionType.ATTACK
                                        and _a.target_id == c.id
                                        for _a in _ac.actions
                                    ):
                                        _killer_id = _ac.id
                                        break
                                if _killer_id:
                                    _contract = await _board.notify_target_killed(
                                        c.id, _killer_id, ctx.db
                                    )
                                    if _contract:
                                        _reward = _board.total_reward(
                                            _contract, alive=False
                                        )
                                        # Award credits
                                        _sess = ctx.session_mgr.find_by_character(
                                            _killer_id
                                        )
                                        if _sess and _sess.character:
                                            _cr = _sess.character.get("credits", 0)
                                            _sess.character["credits"] = _cr + _reward
                                            await ctx.db.save_character(
                                                _killer_id,
                                                credits=_sess.character["credits"],
                                            )
                                            await _sess.send_line(
                                                f"  \\033[1;33m[BOUNTY COLLECTED]\\033[0m "
                                                f"{_contract.target_name} — "
                                                f"+{_reward:,} credits awarded."
                                            )
                                            log.info(
                                                "[bounty] Auto-collected %s for "
                                                "char %s: %dcr",
                                                _contract.id, _killer_id, _reward,
                                            )
                        except Exception as _be:
                            log.warning(
                                "Bounty kill hook error for NPC %s: %s",
                                c.id, _be,
                            )
                    # ── End bounty kill hook ──────────────────────────────
            except Exception as e:
                log.warning("Failed to save NPC %s wound: %s", c.name, e)
            continue"""

if OLD_BLOCK not in source:
    print("ERROR: Could not locate anchor block in _apply_combat_wear.")
    print("The NPC wound-persist block may have changed since this patch was written.")
    print()
    print("Add the following manually inside _apply_combat_wear(), immediately")
    print("after the `await ctx.db.update_npc(c.id, char_sheet_json=...)` call:")
    print()
    print("    # Bounty kill hook")
    print("    from engine.character import WoundLevel as _WL")
    print("    if c.char.wound_level.value >= _WL.DEAD.value:")
    print("        _ai_cfg = json.loads(npc_row.get('ai_config_json', '{}'))")
    print("        if _ai_cfg.get('is_bounty_target'):")
    print("            from engine.bounty_board import get_bounty_board")
    print("            await get_bounty_board().notify_target_killed(c.id, killer_id, ctx.db)")
    sys.exit(1)

patched = source.replace(OLD_BLOCK, NEW_BLOCK, 1)

# ── Syntax validation ──────────────────────────────────────────────────────────

try:
    ast.parse(patched)
except SyntaxError as e:
    print(f"ERROR: Patched source failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

# ── Write ──────────────────────────────────────────────────────────────────────

backup = TARGET.with_suffix(".py.bounty_combat_bak")
backup.write_text(source, encoding="utf-8")
print(f"  Backup written → {backup}")

TARGET.write_text(patched, encoding="utf-8")
print(f"✓ Patched {TARGET}")
print()
print("Bounty kill hook active. When a bounty target NPC is killed in combat,")
print("the contract is auto-collected and credits awarded to the killer.")
