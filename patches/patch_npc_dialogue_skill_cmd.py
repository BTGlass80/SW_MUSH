#!/usr/bin/env python3
"""
patches/patch_npc_dialogue_skill_cmd.py  --  NPC dialogue skill gating, Drop 2/2.

Patches parser/npc_commands.py:
  - TalkCommand.execute() runs a Persuasion check for substantive messages.
    The result shapes the persuasion_context hint passed to brain.dialogue().
  - Casual greetings (≤3 words, no question mark) skip the check entirely.
  - AskCommand always triggers the check (it delegates to TalkCommand after
    rewriting ctx.args, so the check fires naturally in TalkCommand).

Persuasion context tiers:
  CRITICAL  -> NPC is unusually forthcoming: extra detail, possible discount hint
  SUCCESS   -> NPC is cooperative: gives full answer
  (none)    -> Casual: normal flavour
  FAILURE   -> NPC is guarded: short, non-committal
  FUMBLE    -> NPC is offended or suspicious: dismissive/hostile

Difficulty: 10 (Easy social roll — baseline for a public conversation).

Run from project root:
    python patches/patch_npc_dialogue_skill_cmd.py
"""

import sys
import shutil
import ast
from pathlib import Path

TARGET = Path("parser/npc_commands.py")
BACKUP = Path("parser/npc_commands.py.bak_dialogue_skill")


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
    print(f"  First 120 chars of anchor: {repr(old[:120])}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    shutil.copy(TARGET, BACKUP)
    print(f"Backup: {BACKUP}")

    src = read(TARGET)

    # ── Change 1: add skill_checks import after existing imports ─────────────
    old_import = (
        "from server import ansi\n"
        "\n"
        "# Cache of active NPC brains (npc_id -> NPCBrain)\n"
        "_npc_brains: dict[int, NPCBrain] = {}"
    )
    new_import = (
        "from server import ansi\n"
        "from engine.skill_checks import perform_skill_check\n"
        "\n"
        "# Persuasion difficulty for NPC dialogue\n"
        "_PERSUASION_DIFFICULTY = 10\n"
        "\n"
        "# Words that mark a message as substantive (triggers skill check)\n"
        "_QUESTION_WORDS = frozenset([\n"
        "    \"what\", \"where\", \"when\", \"who\", \"why\", \"how\", \"tell\",\n"
        "    \"know\", \"heard\", \"about\", \"job\", \"work\", \"sell\", \"buy\",\n"
        "    \"hire\", \"need\", \"help\", \"information\", \"rumor\", \"rumour\",\n"
        "    \"price\", \"cost\", \"deal\", \"discount\", \"info\", \"news\",\n"
        "])\n"
        "\n"
        "# Cache of active NPC brains (npc_id -> NPCBrain)\n"
        "_npc_brains: dict[int, NPCBrain] = {}"
    )
    src = apply(src, old_import, new_import, "import block")
    print("  [1/2] Import + constants added")

    # ── Change 2: replace TalkCommand.execute() body (the dialogue section) ──
    # Anchor: the block between "show thinking emote" and brain.dialogue() call
    old_talk_body = (
        "        # Show thinking emote\n"
        "        char = ctx.session.character\n"
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            char[\"room_id\"],\n"
        "            f'  {ansi.player_name(char[\"name\"])} says to {ansi.npc_name(npc_data.name)}, \"{message}\"',\n"
        "        )\n"
        "\n"
        "        if ai_manager.config.npc_thinking_emote:\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.dim(f'{npc_data.name} considers...')}\"\n"
        "            )\n"
        "\n"
        "        # Get room description for context\n"
        "        room = await ctx.db.get_room(char[\"room_id\"])\n"
        "        room_desc = room.get(\"desc_short\", \"\") if room else \"\"\n"
        "\n"
        "        # Generate response\n"
        "        response = await brain.dialogue(\n"
        "            player_input=message,\n"
        "            player_name=char[\"name\"],\n"
        "            player_char_id=char[\"id\"],\n"
        "            room_desc=room_desc,\n"
        "            db=ctx.db,\n"
        "        )\n"
        "\n"
        "        # Display NPC response\n"
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            char[\"room_id\"],\n"
        "            f'  {ansi.npc_name(npc_data.name)} says, \"{response}\"',\n"
        "        )"
    )
    new_talk_body = (
        "        # Show thinking emote\n"
        "        char = ctx.session.character\n"
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            char[\"room_id\"],\n"
        "            f'  {ansi.player_name(char[\"name\"])} says to {ansi.npc_name(npc_data.name)}, \"{message}\"',\n"
        "        )\n"
        "\n"
        "        # ── Persuasion skill gate ──────────────────────────────────────\n"
        "        # Casual greetings skip the check; substantive questions do not.\n"
        "        persuasion_context = \"\"\n"
        "        words = message.lower().split()\n"
        "        is_substantive = (\n"
        "            len(words) > 3\n"
        "            or \"?\" in message\n"
        "            or bool(_QUESTION_WORDS & set(words))\n"
        "        )\n"
        "        if is_substantive:\n"
        "            try:\n"
        "                result = perform_skill_check(\n"
        "                    char, \"persuasion\", _PERSUASION_DIFFICULTY\n"
        "                )\n"
        "                if result.fumble:\n"
        "                    persuasion_context = (\n"
        "                        \"SOCIAL CONTEXT: The player approached this very poorly. \"\n"
        "                        \"You are offended or suspicious. Be curt, dismissive, or \"\n"
        "                        \"openly hostile. Give nothing away. End the conversation \"\n"
        "                        \"if your character would.\"\n"
        "                    )\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"  {ansi.DIM}[Persuasion: {result.pool_str} vs {_PERSUASION_DIFFICULTY} \"\n"
        "                        f\"— roll {result.roll}, fumble]{ansi.RESET}\"\n"
        "                    )\n"
        "                elif not result.success:\n"
        "                    persuasion_context = (\n"
        "                        \"SOCIAL CONTEXT: The player did not make a strong impression. \"\n"
        "                        \"Be guarded and non-committal. Give only the bare minimum. \"\n"
        "                        \"Do not volunteer extra information.\"\n"
        "                    )\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"  {ansi.DIM}[Persuasion: {result.pool_str} vs {_PERSUASION_DIFFICULTY} \"\n"
        "                        f\"— roll {result.roll}, failed]{ansi.RESET}\"\n"
        "                    )\n"
        "                elif result.critical_success:\n"
        "                    persuasion_context = (\n"
        "                        \"SOCIAL CONTEXT: The player is exceptionally charming or \"\n"
        "                        \"persuasive. Be unusually open and forthcoming. Volunteer \"\n"
        "                        \"extra detail, a useful rumour, or hint at a discount if \"\n"
        "                        \"you are a vendor. Treat them as someone you genuinely \"\n"
        "                        \"want to help.\"\n"
        "                    )\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"  {ansi.BRIGHT_GREEN}[Persuasion: {result.pool_str} vs {_PERSUASION_DIFFICULTY} \"\n"
        "                        f\"— roll {result.roll}, critical!]{ansi.RESET}\"\n"
        "                    )\n"
        "                else:\n"
        "                    persuasion_context = (\n"
        "                        \"SOCIAL CONTEXT: The player communicated clearly and \"\n"
        "                        \"respectfully. Answer their question fully and in good faith. \"\n"
        "                        \"Normal cooperative tone.\"\n"
        "                    )\n"
        "            except Exception:\n"
        "                pass  # Graceful-drop — dialogue still fires without context\n"
        "\n"
        "        if ai_manager.config.npc_thinking_emote:\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.dim(f'{npc_data.name} considers...')}\"\n"
        "            )\n"
        "\n"
        "        # Get room description for context\n"
        "        room = await ctx.db.get_room(char[\"room_id\"])\n"
        "        room_desc = room.get(\"desc_short\", \"\") if room else \"\"\n"
        "\n"
        "        # Generate response\n"
        "        response = await brain.dialogue(\n"
        "            player_input=message,\n"
        "            player_name=char[\"name\"],\n"
        "            player_char_id=char[\"id\"],\n"
        "            room_desc=room_desc,\n"
        "            db=ctx.db,\n"
        "            persuasion_context=persuasion_context,\n"
        "        )\n"
        "\n"
        "        # Display NPC response\n"
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            char[\"room_id\"],\n"
        "            f'  {ansi.npc_name(npc_data.name)} says, \"{response}\"',\n"
        "        )"
    )
    src = apply(src, old_talk_body, new_talk_body, "TalkCommand dialogue block")
    print("  [2/2] TalkCommand Persuasion skill gate wired")

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        ast.parse(src)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  AST FAIL: {e}")
        sys.exit(1)

    write(TARGET, src)
    print(f"\nPatch applied successfully → {TARGET}")
    print("Persuasion (difficulty 10) now gates substantive NPC dialogue.")
    print("Casual greetings (≤3 words, no ?, no topic keywords) skip the check.")


if __name__ == "__main__":
    main()
