#!/usr/bin/env python3
"""
patches/patch_npc_dialogue_skill_brain.py  --  NPC dialogue skill gating, Drop 1/2.

Patches ai/npc_brain.py:
  - _build_system_prompt gains a `persuasion_context` param that injects
    a behaviour hint into the system prompt based on the skill check result.
  - dialogue() gains a `persuasion_context` kwarg and passes it through.

Run from project root:
    python patches/patch_npc_dialogue_skill_brain.py
"""

import sys
import shutil
import ast
from pathlib import Path

TARGET = Path("ai/npc_brain.py")
BACKUP = Path("ai/npc_brain.py.bak_dialogue_skill")


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

    # ── Change 1: _build_system_prompt gains persuasion_context param ─────────
    old_bsp_sig = (
        "    def _build_system_prompt(self, room_desc: str = \"\",\n"
        "                             player_name: str = \"\",\n"
        "                             player_memory: str = \"\") -> str:\n"
        "        \"\"\"Assemble the full system prompt for this NPC.\"\"\""
    )
    new_bsp_sig = (
        "    def _build_system_prompt(self, room_desc: str = \"\",\n"
        "                             player_name: str = \"\",\n"
        "                             player_memory: str = \"\",\n"
        "                             persuasion_context: str = \"\") -> str:\n"
        "        \"\"\"Assemble the full system prompt for this NPC.\"\"\""
    )
    src = apply(src, old_bsp_sig, new_bsp_sig, "_build_system_prompt signature")
    print("  [1/3] _build_system_prompt signature updated")

    # ── Change 2: inject persuasion_context block before the RULES line ───────
    old_rules = (
        "        # Constraints\n"
        "        parts.append(\n"
        "            \"RULES: Stay in character at all times. Do not reference game mechanics, \"\n"
        "            \"dice rolls, or being an AI. Respond as your character would speak. \"\n"
        "            \"Keep responses concise (1-3 sentences). Do not narrate actions for the player.\"\n"
        "        )\n"
        "\n"
        "        return \"\\n\".join(parts)"
    )
    new_rules = (
        "        # Persuasion context (injected by skill check in TalkCommand)\n"
        "        if persuasion_context:\n"
        "            parts.append(persuasion_context)\n"
        "\n"
        "        # Constraints\n"
        "        parts.append(\n"
        "            \"RULES: Stay in character at all times. Do not reference game mechanics, \"\n"
        "            \"dice rolls, or being an AI. Respond as your character would speak. \"\n"
        "            \"Keep responses concise (1-3 sentences). Do not narrate actions for the player.\"\n"
        "        )\n"
        "\n"
        "        return \"\\n\".join(parts)"
    )
    src = apply(src, old_rules, new_rules, "persuasion_context injection")
    print("  [2/3] persuasion_context injection added to _build_system_prompt")

    # ── Change 3: dialogue() gains persuasion_context kwarg + passes it ───────
    old_dialogue_sig = (
        "    async def dialogue(\n"
        "        self,\n"
        "        player_input: str,\n"
        "        player_name: str = \"\",\n"
        "        player_char_id: int = 0,\n"
        "        room_desc: str = \"\",\n"
        "        db=None,\n"
        "    ) -> str:\n"
        "        \"\"\"\n"
        "        Generate an NPC dialogue response.\n"
        "\n"
        "        Args:\n"
        "            player_input: What the player said/asked.\n"
        "            player_name: Player character name.\n"
        "            player_char_id: For rate limiting and memory lookup.\n"
        "            room_desc: Current room description for context.\n"
        "            db: Database reference for memory lookup/save.\n"
        "\n"
        "        Returns:\n"
        "            NPC's spoken response as a string.\n"
        "        \"\"\""
    )
    new_dialogue_sig = (
        "    async def dialogue(\n"
        "        self,\n"
        "        player_input: str,\n"
        "        player_name: str = \"\",\n"
        "        player_char_id: int = 0,\n"
        "        room_desc: str = \"\",\n"
        "        db=None,\n"
        "        persuasion_context: str = \"\",\n"
        "    ) -> str:\n"
        "        \"\"\"\n"
        "        Generate an NPC dialogue response.\n"
        "\n"
        "        Args:\n"
        "            player_input: What the player said/asked.\n"
        "            player_name: Player character name.\n"
        "            player_char_id: For rate limiting and memory lookup.\n"
        "            room_desc: Current room description for context.\n"
        "            db: Database reference for memory lookup/save.\n"
        "            persuasion_context: Hint injected by Persuasion skill check.\n"
        "                Empty string = no check was run (casual greeting).\n"
        "\n"
        "        Returns:\n"
        "            NPC's spoken response as a string.\n"
        "        \"\"\""
    )
    src = apply(src, old_dialogue_sig, new_dialogue_sig, "dialogue() signature")
    print("  [3a/3] dialogue() signature updated")

    old_build_call = (
        "        # Build prompt\n"
        "        system_prompt = self._build_system_prompt(\n"
        "            room_desc=room_desc,\n"
        "            player_name=player_name,\n"
        "            player_memory=player_memory,\n"
        "        )"
    )
    new_build_call = (
        "        # Build prompt\n"
        "        system_prompt = self._build_system_prompt(\n"
        "            room_desc=room_desc,\n"
        "            player_name=player_name,\n"
        "            player_memory=player_memory,\n"
        "            persuasion_context=persuasion_context,\n"
        "        )"
    )
    src = apply(src, old_build_call, new_build_call, "dialogue() build call")
    print("  [3b/3] dialogue() build call updated")

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        ast.parse(src)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  AST FAIL: {e}")
        sys.exit(1)

    write(TARGET, src)
    print(f"\nPatch applied successfully → {TARGET}")


if __name__ == "__main__":
    main()
