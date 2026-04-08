#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_checks_wire_patch.py
--------------------------
Wires skill checks into mission completion and bounty collection.

Changes:
  1. parser/mission_commands.py  — CompleteMissionCommand
     Replaces the flat reward block with a skill check.
     Delivery missions always succeed (difficulty 8, stamina).
     Other types roll relevant skill vs scaled difficulty.
     Partial success (margin >= -4) pays a fraction.
     Critical success pays +20%.

  2. parser/bounty_commands.py  — BountyCollectCommand
     Adds a Streetwise/Search check representing confirmation
     work. Partial pay on near-miss; full pay on success.
     The target being dead is still required — the check
     represents the quality of the writeup and claim process.

Run from the SW_MUSH project root:
    python patches/skill_checks_wire_patch.py
"""
import ast, shutil, sys
from pathlib import Path

MC = Path("parser/mission_commands.py")
BC = Path("parser/bounty_commands.py")

for f in (MC, BC):
    if not f.exists():
        print(f"ERROR: {f} not found. Run from project root.")
        sys.exit(1)

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")
def validate(p, s):
    try:
        ast.parse(s); return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {p}: {e}"); return False
def backup(p):
    bak = p.with_suffix(".py.skill_bak")
    if not bak.exists(): shutil.copy2(p, bak)
    print(f"  Backup: {bak.name}")

# ══════════════════════════════════════════════════════════════════════════════
# 1. parser/mission_commands.py — skill check on complete
# ══════════════════════════════════════════════════════════════════════════════
print("\n── parser/mission_commands.py ───────────────────────────────────────────")

src = read(MC)

if "resolve_mission_completion" in src:
    print("  ✓ skill check already present — skipping.")
else:
    # Replace the flat reward block in CompleteMissionCommand.execute()
    OLD_REWARD = (
        "        # Complete and award credits\n"
        "        reward = active.reward\n"
        "        completed = await board.complete(active.id, ctx.db)\n"
        "        if not completed:\n"
        "            await ctx.session.send_line(\n"
        "                \"  Something went wrong completing the mission. Try again.\")\n"
        "            return\n"
        "\n"
        "        old_credits = char.get(\"credits\", 0)\n"
        "        new_credits = old_credits + reward\n"
        "        char[\"credits\"] = new_credits\n"
        "        await ctx.db.save_character(char[\"id\"], credits=new_credits)\n"
        "\n"
        "        await ctx.session.send_line(\n"
        "            ansi.success(f\"  Mission complete: {completed.title}\"))\n"
        "        await ctx.session.send_line(\n"
        "            f\"  {ansi.BOLD}Reward: +{reward:,} credits{ansi.RESET}  \"\n"
        "            f\"(Balance: {new_credits:,} cr)\")\n"
        "        await ctx.session.send_line(\"\")\n"
        "        await ctx.session.send_line(\n"
        "            f\"  {ansi.DIM}Type 'missions' for your next job.{ansi.RESET}\")"
    )

    NEW_REWARD = (
        "        # Complete and resolve skill check\n"
        "        completed = await board.complete(active.id, ctx.db)\n"
        "        if not completed:\n"
        "            await ctx.session.send_line(\n"
        "                \"  Something went wrong completing the mission. Try again.\")\n"
        "            return\n"
        "\n"
        "        from engine.skill_checks import resolve_mission_completion\n"
        "        check = resolve_mission_completion(\n"
        "            char,\n"
        "            completed.mission_type.value,\n"
        "            completed.reward,\n"
        "        )\n"
        "\n"
        "        earned = check[\"credits_earned\"]\n"
        "        old_credits = char.get(\"credits\", 0)\n"
        "        new_credits = old_credits + earned\n"
        "        char[\"credits\"] = new_credits\n"
        "        await ctx.db.save_character(char[\"id\"], credits=new_credits)\n"
        "\n"
        "        await ctx.session.send_line(\n"
        "            ansi.success(f\"  Mission complete: {completed.title}\"))\n"
        "        # Skill roll feedback\n"
        "        result_tag = \"\"\n"
        "        if check[\"critical\"]:\n"
        "            result_tag = f\" {ansi.BOLD}[EXCEPTIONAL +20%]{ansi.RESET}\"\n"
        "        elif check[\"partial\"]:\n"
        "            result_tag = f\" {ansi.DIM}[PARTIAL PAY]{ansi.RESET}\"\n"
        "        elif not check[\"success\"]:\n"
        "            result_tag = f\" {ansi.error('[FAILED]') if hasattr(ansi, 'error') else '[FAILED]'}\"\n"
        "        await ctx.session.send_line(\n"
        "            f\"  {ansi.BOLD}Reward: +{earned:,} credits{ansi.RESET}{result_tag}  \"\n"
        "            f\"(Balance: {new_credits:,} cr)\")\n"
        "        await ctx.session.send_line(\n"
        "            f\"  Skill: {check['skill'].title()} [{check['pool']}]  \"\n"
        "            f\"Roll: {check['roll']} vs Difficulty: {check['difficulty']}\")\n"
        "        await ctx.session.send_line(f\"  {check['message']}\")\n"
        "        await ctx.session.send_line(\"\")\n"
        "        await ctx.session.send_line(\n"
        "            f\"  {ansi.DIM}Type 'missions' for your next job.{ansi.RESET}\")"
    )

    patched = src
    for old, new in [(OLD_REWARD, NEW_REWARD),
                     (OLD_REWARD.replace("\n", "\r\n"), NEW_REWARD.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + Skill check wired into CompleteMissionCommand")
            break
    else:
        print("  WARNING: Could not find mission reward anchor.")
        print("  Apply manually — replace the flat reward block in CompleteMissionCommand.")
        patched = src

    if patched != src:
        if validate(MC, patched):
            backup(MC)
            write(MC, patched)
            print("  ✓ parser/mission_commands.py patched")
        else:
            print("  parser/mission_commands.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# 2. parser/bounty_commands.py — skill check on collect
# ══════════════════════════════════════════════════════════════════════════════
print("\n── parser/bounty_commands.py ────────────────────────────────────────────")

src = read(BC)

if "resolve_mission_completion" in src or "skill_checks" in src:
    print("  ✓ skill check already present — skipping.")
else:
    OLD_COLLECT = (
        "        # Collect it\n"
        "        collected = await board.collect(contract.id, False, ctx.db)\n"
        "        if not collected:\n"
        "            await ctx.session.send_line(\"  Error collecting bounty. Try again.\")\n"
        "            return\n"
        "\n"
        "        reward = board.total_reward(collected, alive=False)\n"
        "        old_credits = char.get(\"credits\", 0)\n"
        "        new_credits = old_credits + reward\n"
        "        char[\"credits\"] = new_credits\n"
        "        await ctx.db.save_character(char[\"id\"], credits=new_credits)"
    )

    NEW_COLLECT = (
        "        # Collect it — skill check represents claim quality\n"
        "        collected = await board.collect(contract.id, False, ctx.db)\n"
        "        if not collected:\n"
        "            await ctx.session.send_line(\"  Error collecting bounty. Try again.\")\n"
        "            return\n"
        "\n"
        "        base_reward = board.total_reward(collected, alive=False)\n"
        "        from engine.skill_checks import perform_skill_check\n"
        "        # Bounty hunters roll Streetwise; others roll Search\n"
        "        import json as _bj\n"
        "        _attrs = _bj.loads(char.get('attributes', '{}'))\n"
        "        _skills = _bj.loads(char.get('skills', '{}'))\n"
        "        _skill = 'streetwise' if _skills.get('streetwise') else 'search'\n"
        "        _diff = 8 if base_reward < 500 else (11 if base_reward < 1500 else 14)\n"
        "        _check = perform_skill_check(char, _skill, _diff)\n"
        "        if _check.success:\n"
        "            reward = base_reward\n"
        "            if _check.critical_success:\n"
        "                reward = int(base_reward * 1.20)\n"
        "        elif _check.margin >= -4:\n"
        "            reward = int(base_reward * 0.75)  # partial\n"
        "        else:\n"
        "            reward = int(base_reward * 0.50)  # poor paperwork\n"
        "        old_credits = char.get(\"credits\", 0)\n"
        "        new_credits = old_credits + reward\n"
        "        char[\"credits\"] = new_credits\n"
        "        await ctx.db.save_character(char[\"id\"], credits=new_credits)"
    )

    patched = src
    for old, new in [(OLD_COLLECT, NEW_COLLECT),
                     (OLD_COLLECT.replace("\n", "\r\n"), NEW_COLLECT.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + Skill check wired into BountyCollectCommand")
            break
    else:
        print("  WARNING: Could not find bounty collect anchor.")
        print("  Apply manually — replace the flat reward block in BountyCollectCommand.")
        patched = src

    # Also update the reward display line in bounty collect to use 'reward' not fixed value
    if patched != src:
        OLD_DISPLAY = (
            "        await ctx.session.send_line(\n"
            "            ansi.success(f\"  Bounty collected: {collected.target_name}\")\n"
            "        )\n"
            "        await ctx.session.send_line(\n"
            "            f\"  {ansi.BOLD}Reward: +{reward:,} credits{ansi.RESET}  \"\n"
            "            f\"(Balance: {new_credits:,} cr)\"\n"
            "        )"
        )
        NEW_DISPLAY = (
            "        await ctx.session.send_line(\n"
            "            ansi.success(f\"  Bounty collected: {collected.target_name}\")\n"
            "        )\n"
            "        _result_tag = \" [EXCEPTIONAL +20%]\" if _check.critical_success else (\n"
            "            \" [PARTIAL]\" if _check.margin >= -4 and not _check.success else \"\")\n"
            "        await ctx.session.send_line(\n"
            "            f\"  {ansi.BOLD}Reward: +{reward:,} credits{ansi.RESET}{_result_tag}  \"\n"
            "            f\"(Balance: {new_credits:,} cr)\"\n"
            "        )\n"
            "        await ctx.session.send_line(\n"
            "            f\"  Claim quality: {_skill.title()} [{_check.pool_str}]  \"\n"
            "            f\"Roll {_check.roll} vs {_check.difficulty}\"\n"
            "        )"
        )
        for old, new in [(OLD_DISPLAY, NEW_DISPLAY),
                         (OLD_DISPLAY.replace("\n", "\r\n"), NEW_DISPLAY.replace("\n", "\r\n"))]:
            if old in patched:
                patched = patched.replace(old, new, 1)
                print("  + Bounty collect display updated")
                break

    if patched != src:
        if validate(BC, patched):
            backup(BC)
            write(BC, patched)
            print("  ✓ parser/bounty_commands.py patched")
        else:
            print("  parser/bounty_commands.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Final syntax check ───────────────────────────────────────────────────")
all_ok = True
for f in (MC, BC):
    try:
        ast.parse(read(f))
        print(f"  OK  {f}")
    except SyntaxError as e:
        print(f"  ERR {f}: {e}")
        all_ok = False

print()
if all_ok:
    print("Skill checks wired. Character skills now affect:")
    print("  - Mission completion pay (partial/full/exceptional)")
    print("  - Bounty collection reward quality")
    print()
    print("Skill used per mission type:")
    print("  Combat -> Blaster | Smuggling -> Con | Investigation -> Search")
    print("  Social -> Persuasion | Technical -> Space Transports Repair")
    print("  Medical -> First Aid | Slicing -> Computer | Delivery -> Stamina")
else:
    print("WARNING: Syntax errors found.")
    sys.exit(1)
