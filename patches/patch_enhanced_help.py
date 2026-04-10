#!/usr/bin/env python3
"""
Drop D -- Enhanced Command Help Text
=====================================
Upgrades help_text on high-traffic commands to multi-line with examples.

Run from project root:  python patches/patch_enhanced_help.py
"""
import os, sys, ast, shutil, re
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def backup(path):
    bak = path + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, bak)


def _make_multiline_help(lines):
    r"""Convert a list of plain strings into a parenthesized Python help_text.

    Input:  ["Line one.", "Line two.", "", "EXAMPLES:", "  foo -- bar"]
    Output: (as a string to splice into source code)
        help_text = (
            "Line one.\n"
            "Line two.\n"
            "\n"
            "EXAMPLES:\n"
            "  foo -- bar"
        )
    """
    parts = []
    for i, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace('"', '\\"')
        if i < len(lines) - 1:
            parts.append(f'        "{escaped}\\n"')
        else:
            parts.append(f'        "{escaped}"')
    inner = "\n".join(parts)
    return f"    help_text = (\n{inner}\n    )"


def replace_help_text(src, old_help_text_value, new_lines, label):
    """Find and replace a help_text assignment in source code.

    old_help_text_value: the exact Python string value (without quotes) of
                         the current help_text. Can be a substring match if
                         the line also has surrounding quotes.
    new_lines: list of plain-text lines for the new help_text.
    """
    # Build a regex that matches the full help_text = "..." or help_text = (\n...\n    )
    # We search for the exact old value inside quotes
    escaped_old = re.escape(old_help_text_value)

    # Try single-line form first: help_text = "old value"
    pattern_single = re.compile(
        r'(    help_text = )"' + escaped_old + r'"'
    )
    m = pattern_single.search(src)
    if m:
        new_ht = _make_multiline_help(new_lines)
        src = src[:m.start()] + new_ht + src[m.end():]
        print(f"  OK: {label}")
        return src, True

    # Try multi-line form: help_text = (\n...\n    )
    # Find the start
    idx = src.find(old_help_text_value)
    if idx == -1:
        print(f"  MISS: {label} (value not found in source)")
        return src, False

    # Walk backward to find "help_text = "
    line_start = src.rfind("\n", 0, idx)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1

    prefix_text = src[line_start:idx]
    if "help_text" not in prefix_text:
        print(f"  MISS: {label} (found text but not in help_text context)")
        return src, False

    # Find the end of the assignment — look for the closing )
    # or the end of the quoted string
    ht_start = src.rfind("help_text", 0, idx)
    # Find the full extent: from "    help_text = " to end of value
    assign_start = src.rfind("\n", 0, ht_start)
    if assign_start == -1:
        assign_start = 0
    else:
        assign_start += 1

    # Find the end — either closing " on same line or closing ) for multi-line
    rest = src[ht_start:]
    if rest.startswith("help_text = ("):
        # Multi-line: find matching )
        depth = 0
        end_offset = 0
        for i, ch in enumerate(rest):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end_offset = i + 1
                    break
        assign_end = ht_start + end_offset
    else:
        # Single-line: find end of line
        nl = src.find("\n", ht_start)
        assign_end = nl if nl != -1 else len(src)

    new_ht = _make_multiline_help(new_lines)
    src = src[:assign_start] + new_ht + src[assign_end:]
    print(f"  OK: {label}")
    return src, True


def patch_file(relpath, replacements):
    """Apply a list of (old_value_substring, new_lines, label) replacements."""
    path = os.path.join(PROJECT_ROOT, relpath)
    if not os.path.isfile(path):
        print(f"  SKIP: {relpath}")
        return 0

    backup(path)
    src = open(path, "r", encoding="utf-8").read()
    count = 0

    for old_val, new_lines, label in replacements:
        src, ok = replace_help_text(src, old_val, new_lines, label)
        if ok:
            count += 1

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {relpath}: {e}")
        return 0

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"  {relpath}: {count} enhanced")
    return count


# ═══════════════════════════════════════════════════════════════════════
# Replacement definitions — plain text, no quoting gymnastics
# Each: (substring of current help_text value, [new lines], label)
# ═══════════════════════════════════════════════════════════════════════

BUILTIN_REPLACEMENTS = [
    (
        "Look at your surroundings, an object, or a character.",
        [
            "Look at your surroundings, an object, or a character.",
            "With no argument, shows the room, exits, NPCs, and players.",
            "",
            "EXAMPLES:",
            "  look            -- the current room",
            "  look bartender  -- an NPC or object",
            "  look Tundra     -- another player",
        ],
        "look",
    ),
    (
        "Say something to the room.",
        [
            "Say something aloud. Everyone in the room hears it.",
            "Shortcut: type a single-quote then your message.",
            "",
            "EXAMPLE: say Nice ship. She yours?",
            "Output:  You say, \"Nice ship. She yours?\"",
        ],
        "say",
    ),
    (
        "Perform an emote/pose.",
        [
            "Describe an action your character performs.",
            "Shows as your name followed by the text.",
            "",
            "SHORTCUTS:",
            "  :draws a blaster  -- Tundra draws a blaster",
            "  ;'s hand shakes   -- Tundra's hand shakes (semipose)",
            "",
            "Write in third person present tense.",
        ],
        "emote",
    ),
    (
        "Whisper to a specific player in the room.",
        [
            "Private message to someone in the same room.",
            "Only you and the target see it.",
            "",
            "EXAMPLE: whisper Tundra = Meet me at bay 94.",
        ],
        "whisper",
    ),
]

COMBAT_REPLACEMENTS = [
    (
        "Attack a target. Starts or joins combat.",
        [
            "Attack a target with your equipped weapon.",
            "If no combat is active, this starts one.",
            "",
            "OPTIONS:",
            "  with <skill>  -- override weapon skill",
            "  damage <dice> -- override damage dice",
            "  cp <N>        -- spend N Character Points on the roll",
            "",
            "EXAMPLES:",
            "  attack stormtrooper",
            "  attack thug with brawling",
            "  attack bounty hunter cp 2",
        ],
        "attack",
    ),
    (
        "Attempt to flee combat.",
        [
            "Attempt to escape combat. Opposed roll: your running",
            "vs. opponents. Fail = lose your action this round.",
            "",
            "TIP: Use fulldodge for a round to survive, then flee next.",
        ],
        "flee",
    ),
    (
        "Take cover (costs an action). Cover level limited by room. Attacking from cover reduces it to 1/4.",
        [
            "Take cover behind objects. Adds difficulty to ranged",
            "attacks against you. Costs an action.",
            "",
            "LEVELS: quarter (+1D), half (+2D), 3/4 (+3D),",
            "full (untargetable but cannot shoot).",
            "",
            "Attacking from cover reduces it to quarter.",
            "Max cover depends on the room environment.",
        ],
        "cover",
    ),
    (
        "Set your range to a target in combat.",
        [
            "View or change range to a target.",
            "",
            "BANDS: pointblank (5), short (10), medium (15), long (20)",
            "",
            "EXAMPLES:",
            "  range stormtrooper        -- check range",
            "  range stormtrooper short  -- set to short",
        ],
        "range",
    ),
    (
        "Spend a Force Point to double ALL dice this round. Must declare during declaration phase. Cannot be used same round as CP.",
        [
            "Spend a Force Point to DOUBLE all dice this round.",
            "Must declare during declaration phase. Cannot be",
            "used same round as CP spending.",
            "",
            "FP spent heroically may be returned at adventure end.",
            "FP spent selfishly are lost and may earn a DSP.",
        ],
        "forcepoint",
    ),
]

D6_REPLACEMENTS = [
    (
        "Roll dice. Use a pool (4D+2) or a skill name.",
        [
            "Roll dice using D6 notation. Includes the Wild Die.",
            "",
            "EXAMPLES:",
            "  +roll 4D         -- roll 4 dice",
            "  +roll 3D+2       -- roll 3 dice, add 2",
            "  +roll 5D blaster -- labeled roll",
        ],
        "roll",
    ),
    (
        "Roll a skill check against a difficulty.",
        [
            "Roll your skill against a difficulty number.",
            "Uses full skill pool (attribute + skill ranks).",
            "",
            "EXAMPLES:",
            "  +check blaster 15    -- blaster vs diff 15",
            "  +check persuasion 10 -- persuasion vs diff 10",
        ],
        "check",
    ),
]

MISSION_REPLACEMENTS = [
    (
        "View the Mission Board. Lists all available jobs.",
        [
            "Browse available missions for credits.",
            "",
            "WORKFLOW:",
            "  +missions      -- browse available jobs",
            "  accept <id>    -- take a mission",
            "  +mission       -- check active mission",
            "  complete       -- turn in at destination",
            "  abandon        -- give up (returns to board)",
        ],
        "missions",
    ),
]

CP_REPLACEMENTS = [
    (
        "Spend Character Points to advance a skill by 1 pip.",
        [
            "Spend CP to advance a skill by one pip.",
            "Cost = number of dice in total pool.",
            "",
            "EXAMPLE: train blaster",
            "  Blaster at 5D costs 5 CP per pip.",
            "  Three pips = one die: 5D > 5D+1 > 5D+2 > 6D.",
            "",
            "Type +cpstatus to check your CP balance.",
        ],
        "train",
    ),
    (
        "Give a roleplay kudos to another player in the same room.",
        [
            "Award kudos to a player for great RP. Grants 35 ticks",
            "toward their CP. You can give 3/week (7-day lockout",
            "per recipient).",
            "",
            "EXAMPLE: +kudos Tundra Great scene at the cantina!",
        ],
        "kudos",
    ),
]


def main():
    print("=" * 60)
    print("  Drop D -- Enhanced Command Help Text")
    print("=" * 60)

    total = 0
    total += patch_file("parser/builtin_commands.py", BUILTIN_REPLACEMENTS)
    total += patch_file("parser/combat_commands.py", COMBAT_REPLACEMENTS)
    total += patch_file("parser/d6_commands.py", D6_REPLACEMENTS)
    total += patch_file("parser/mission_commands.py", MISSION_REPLACEMENTS)
    total += patch_file("parser/cp_commands.py", CP_REPLACEMENTS)

    print(f"\n  Total commands enhanced: {total}")
    print("=" * 60)
    if total:
        print("  Test: +help attack, +help say, +help roll, +help train")
    print("=" * 60)


if __name__ == "__main__":
    main()
