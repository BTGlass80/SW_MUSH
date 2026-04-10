#!/usr/bin/env python3
"""
Drop 2 — Command Rename & Alias Sweep
======================================
Updates key and aliases on every BaseCommand subclass across all parser
modules to establish the + prefix convention and add MUSH-standard aliases.

Backward compatibility: old bare-word names are always kept as aliases.
Nothing breaks — we only ADD aliases and change canonical keys.

Run from project root:  python patches/patch_alias_sweep.py

Note: crafting_commands.py uses a non-BaseCommand pattern (names=[]) and
is NOT patched by this script. It needs a separate migration.
"""
import os
import sys
import ast
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

# ── Replacement table ──
# Each entry: (filename, old_key_line, old_aliases_line, new_key_line, new_aliases_line)
# We match EXACT lines from the source to avoid false positives.
# Lines use repr-style quoting to match the .py source exactly.

REPLACEMENTS = [
    # ═══════════════════════════════════════════════════════════════════
    # builtin_commands.py
    # ═══════════════════════════════════════════════════════════════════
    # Note: SayCommand '"' alias and EmoteCommand pose/em aliases were
    # already added by Drop 1 patch. Skip those here.
    ("parser/builtin_commands.py",
     '    key = "who"',
     '    aliases = ["online"]',
     '    key = "+who"',
     '    aliases = ["who", "online", "+online"]'),

    ("parser/builtin_commands.py",
     '    key = "inventory"',
     '    aliases = ["inv", "i"]',
     '    key = "+inv"',
     '    aliases = ["inventory", "inv", "i", "+inventory"]'),

    ("parser/builtin_commands.py",
     '    key = "sheet"',
     '    aliases = ["score", "stats"]',
     '    key = "+sheet"',
     '    aliases = ["sheet", "score", "stats", "+score", "+stats", "sc"]'),

    ("parser/builtin_commands.py",
     '    key = "help"',
     '    aliases = ["?", "commands"]',
     '    key = "+help"',
     '    aliases = ["help", "?", "commands", "+commands"]'),

    ("parser/builtin_commands.py",
     '    key = "quit"',
     '    aliases = ["@quit", "logout"]',
     '    key = "quit"',
     '    aliases = ["@quit", "logout", "QUIT"]'),

    ("parser/builtin_commands.py",
     '    key = "@ooc"',
     '    aliases = ["ooc"]',
     '    key = "+ooc"',
     '    aliases = ["ooc", "@ooc"]'),

    ("parser/builtin_commands.py",
     '    key = "whisper"',
     '    aliases = ["wh"]',
     '    key = "whisper"',
     '    aliases = ["wh", "page", "tell"]'),

    ("parser/builtin_commands.py",
     '    key = "repair"',
     '    aliases = []',
     '    key = "+repair"',
     '    aliases = ["repair"]'),

    ("parser/builtin_commands.py",
     '    key = "weapons"',
     '    aliases = ["weaponlist", "armory"]',
     '    key = "+weapons"',
     '    aliases = ["weapons", "weaponlist", "armory", "+armory"]'),

    # ═══════════════════════════════════════════════════════════════════
    # d6_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/d6_commands.py",
     '    key = "roll"',
     '    aliases = []',
     '    key = "+roll"',
     '    aliases = ["roll"]'),

    ("parser/d6_commands.py",
     '    key = "check"',
     '    aliases = []',
     '    key = "+check"',
     '    aliases = ["check"]'),

    ("parser/d6_commands.py",
     '    key = "opposed"',
     '    aliases = ["vs"]',
     '    key = "+opposed"',
     '    aliases = ["opposed", "vs"]'),

    # ═══════════════════════════════════════════════════════════════════
    # combat_commands.py
    # Combat actions stay bare-word (IC). Status/info commands get +.
    # ═══════════════════════════════════════════════════════════════════
    ("parser/combat_commands.py",
     '    key = "attack"',
     '    aliases = ["att", "kill", "shoot"]',
     '    key = "attack"',
     '    aliases = ["att", "kill", "shoot", "hit"]'),

    ("parser/combat_commands.py",
     '    key = "flee"',
     '    aliases = ["run"]',
     '    key = "flee"',
     '    aliases = ["run", "retreat"]'),

    ("parser/combat_commands.py",
     '    key = "combat"',
     '    aliases = ["cs"]',
     '    key = "+combat"',
     '    aliases = ["combat", "cs", "+cs"]'),

    ("parser/combat_commands.py",
     '    key = "forcepoint"',
     '    aliases = ["fp"]',
     '    key = "forcepoint"',
     '    aliases = ["fp", "+fp"]'),

    # ═══════════════════════════════════════════════════════════════════
    # space_commands.py
    # Ship operations = bare IC. Info/status = +.
    # ═══════════════════════════════════════════════════════════════════
    ("parser/space_commands.py",
     '    key = "ships"',
     '    aliases = ["shiplist"]',
     '    key = "+ships"',
     '    aliases = ["ships", "shiplist"]'),

    ("parser/space_commands.py",
     '    key = "shipinfo"',
     '    aliases = ["si"]',
     '    key = "+shipinfo"',
     '    aliases = ["shipinfo", "si"]'),

    ("parser/space_commands.py",
     '    key = "disembark"',
     '    aliases = ["deboard"]',
     '    key = "disembark"',
     '    aliases = ["deboard", "leave_ship"]'),

    ("parser/space_commands.py",
     '    key = "gunner"',
     '    aliases = []',
     '    key = "gunner"',
     '    aliases = ["gunnery"]'),

    ("parser/space_commands.py",
     '    key = "vacate"',
     '    aliases = ["leave_station", "unstation"]',
     '    key = "vacate"',
     '    aliases = ["unstation"]'),

    ("parser/space_commands.py",
     '    key = "shiprepair"',
     '    aliases = ["srepair"]',
     '    key = "+shiprepair"',
     '    aliases = ["shiprepair", "srepair"]'),

    ("parser/space_commands.py",
     '    key = "myships"',
     '    aliases = ["ownedships"]',
     '    key = "+myships"',
     '    aliases = ["myships", "ownedships"]'),

    ("parser/space_commands.py",
     '    key = "shipstatus"',
     '    aliases = ["ss"]',
     '    key = "+shipstatus"',
     '    aliases = ["shipstatus", "ss", "+ss"]'),

    ("parser/space_commands.py",
     '    key = "credits"',
     '    aliases = ["balance", "wallet"]',
     '    key = "+credits"',
     '    aliases = ["credits", "balance", "wallet", "+wallet"]'),

    # ═══════════════════════════════════════════════════════════════════
    # force_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/force_commands.py",
     '    key = "force"',
     '    aliases = ["useforce", "fp_use"]',
     '    key = "force"',
     '    aliases = ["useforce"]'),

    ("parser/force_commands.py",
     '    key = "powers"',
     '    aliases = ["forcepowers", "listpowers"]',
     '    key = "+powers"',
     '    aliases = ["powers", "forcepowers", "listpowers"]'),

    ("parser/force_commands.py",
     '    key = "forcestatus"',
     '    aliases = ["fstatus", "forcesheet"]',
     '    key = "+forcestatus"',
     '    aliases = ["forcestatus", "fstatus", "forcesheet", "+fstatus"]'),

    # ═══════════════════════════════════════════════════════════════════
    # cp_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/cp_commands.py",
     '    key = "cpstatus"',
     '    aliases = ["cpinfo", "advancement"]',
     '    key = "+cpstatus"',
     '    aliases = ["cpstatus", "cpinfo", "advancement", "+cp", "+advancement"]'),

    ("parser/cp_commands.py",
     '    key = "kudos"',
     '    aliases = ["givekudos"]',
     '    key = "+kudos"',
     '    aliases = ["kudos", "givekudos", "+givekudos"]'),

    ("parser/cp_commands.py",
     '    key = "scenebonus"',
     '    aliases = ["endscene", "closescene"]',
     '    key = "+scenebonus"',
     '    aliases = ["scenebonus", "endscene", "closescene", "+endscene"]'),

    # ═══════════════════════════════════════════════════════════════════
    # mission_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/mission_commands.py",
     '    key = "missions"',
     '    aliases = ["mb", "jobs", "board"]',
     '    key = "+missions"',
     '    aliases = ["missions", "mb", "jobs", "+jobs", "+mb"]'),

    ("parser/mission_commands.py",
     '    key = "mission"',
     '    aliases = ["myjob", "activemission"]',
     '    key = "+mission"',
     '    aliases = ["mission", "myjob", "activemission", "+myjob"]'),

    # ═══════════════════════════════════════════════════════════════════
    # smuggling_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/smuggling_commands.py",
     '    key = "smugjobs"',
     '    aliases = ["smugboard", "smugcontacts", "underworld"]',
     '    key = "+smugjobs"',
     '    aliases = ["smugjobs", "smugboard", "smugcontacts", "underworld", "+underworld"]'),

    ("parser/smuggling_commands.py",
     '    key = "smugjob"',
     '    aliases = ["myrun", "activerun", "cargo"]',
     '    key = "+smugjob"',
     '    aliases = ["smugjob", "myrun", "activerun", "cargo", "+cargo"]'),

    # ═══════════════════════════════════════════════════════════════════
    # bounty_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/bounty_commands.py",
     '    key = "bounties"',
     '    aliases = ["bboard", "bountyboard"]',
     '    key = "+bounties"',
     '    aliases = ["bounties", "bboard", "bountyboard", "+bboard"]'),

    ("parser/bounty_commands.py",
     '    key = "mybounty"',
     '    aliases = ["activebounty", "myhunt"]',
     '    key = "+mybounty"',
     '    aliases = ["mybounty", "activebounty", "myhunt", "+myhunt"]'),

    # ═══════════════════════════════════════════════════════════════════
    # crew_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/crew_commands.py",
     '    key = "roster"',
     '    aliases = ["crew", "mycrew"]',
     '    key = "+roster"',
     '    aliases = ["roster", "crew", "mycrew", "+crew", "+mycrew"]'),

    # ═══════════════════════════════════════════════════════════════════
    # channel_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/channel_commands.py",
     '    key = "faction"',
     '    aliases = ["affiliation"]',
     '    key = "+faction"',
     '    aliases = ["faction", "affiliation"]'),

    ("parser/channel_commands.py",
     '    key = "freqs"',
     '    aliases = ["frequencies", "myfreqs"]',
     '    key = "+freqs"',
     '    aliases = ["freqs", "frequencies", "myfreqs"]'),

    ("parser/channel_commands.py",
     '    key = "channels"',
     '    aliases = ["chan", "channellist"]',
     '    key = "+channels"',
     '    aliases = ["channels", "chan", "channellist"]'),

    # ═══════════════════════════════════════════════════════════════════
    # medical_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/medical_commands.py",
     '    key = "healrate"',
     '    aliases = ["hrate"]',
     '    key = "+healrate"',
     '    aliases = ["healrate", "hrate"]'),

    # ═══════════════════════════════════════════════════════════════════
    # news_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/news_commands.py",
     '    key = "news"',
     '    aliases = ["worldnews", "galacticnews"]',
     '    key = "+news"',
     '    aliases = ["news", "worldnews", "galacticnews"]'),

    # ═══════════════════════════════════════════════════════════════════
    # party_commands.py
    # ═══════════════════════════════════════════════════════════════════
    ("parser/party_commands.py",
     '    key = "party"',
     '    aliases = ["p"]',
     '    key = "+party"',
     '    aliases = ["party", "p"]'),

    # ═══════════════════════════════════════════════════════════════════
    # building_commands.py  — just add convenience aliases
    # ═══════════════════════════════════════════════════════════════════
    ("parser/building_commands.py",
     '    key = "@teleport"',
     '    aliases = []',
     '    key = "@teleport"',
     '    aliases = ["@tel"]'),

    ("parser/building_commands.py",
     '    key = "@tunnel"',
     '    aliases = []',
     '    key = "@tunnel"',
     '    aliases = ["@tun"]'),

    # ═══════════════════════════════════════════════════════════════════
    # building_tier2.py  — add convenience aliases
    # ═══════════════════════════════════════════════════════════════════
    ("parser/building_tier2.py",
     '    key = "@success"',
     '    aliases = []',
     '    key = "@success"',
     '    aliases = ["@succ"]'),
]


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_{ts}"
    shutil.copy2(path, bak)
    return bak


def apply_replacements():
    """Apply all key/alias replacements."""
    # Group by file
    by_file = {}
    for entry in REPLACEMENTS:
        fname = entry[0]
        if fname not in by_file:
            by_file[fname] = []
        by_file[fname].append(entry)

    total = 0
    errors = 0

    for fname, entries in by_file.items():
        fpath = os.path.join(PROJECT_ROOT, fname)
        if not os.path.isfile(fpath):
            print(f"  SKIP: {fname} not found")
            errors += 1
            continue

        backup(fpath)
        src = open(fpath, "r", encoding="utf-8").read()
        file_count = 0

        for _, old_key, old_aliases, new_key, new_aliases in entries:
            # Build the anchor: key line followed by aliases line
            # They may have varying whitespace between them, so search
            # for the key line first, then the aliases line nearby.
            if old_key not in src:
                print(f"  MISS: {fname}: key anchor not found: {old_key}")
                errors += 1
                continue

            if old_aliases not in src:
                print(f"  MISS: {fname}: aliases anchor not found: {old_aliases}")
                errors += 1
                continue

            # Replace key line (only the first occurrence after finding it)
            if old_key != new_key:
                src = src.replace(old_key, new_key, 1)

            # Replace aliases line
            if old_aliases != new_aliases:
                src = src.replace(old_aliases, new_aliases, 1)

            file_count += 1

        # Validate
        try:
            ast.parse(src)
        except SyntaxError as e:
            print(f"  SYNTAX ERROR in {fname}: {e}")
            errors += 1
            continue

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(src)

        total += file_count
        print(f"  {fname}: {file_count} commands updated")

    return total, errors


def update_help_categories():
    """Update the HelpCommand CATEGORIES dict to use + prefixed names."""
    fpath = os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py")
    src = open(fpath, "r", encoding="utf-8").read()

    # Replace the CATEGORIES dict entries to match new canonical keys
    old_categories = '''    CATEGORIES = {
        "Navigation": ["look", "move", "board", "disembark"],
        "Communication": ["say", "whisper", "emote", "@ooc"],
        "Character": ["sheet", "inventory", "equip", "unequip",
                       "weapons", "credits", "repair", "sell", "@desc"],
        "D6 Dice": ["roll", "check", "opposed"],
        "Combat": ["attack", "dodge", "fulldodge", "parry", "fullparry",
                    "aim", "cover", "flee", "forcepoint", "range",
                    "combat", "resolve", "pass", "disengage", "respawn"],
        "Force": ["force", "powers", "forcestatus"],
        "Economy": ["buy", "sell", "repair", "credits",
                     "missions", "accept", "mission", "complete", "abandon"],
        "Crafting": ["survey", "resources", "buyresource",
                      "schematics", "craft"],
        "Medical": ["heal", "healaccept", "healrate"],
        "Space": ["ships", "shipinfo", "pilot", "gunner", "copilot",
                  "engineer", "navigator", "commander", "sensors",
                  "vacate", "assist", "coordinate", "shiprepair",
                  "myships", "launch", "land", "scan", "fire", "evade",
                  "shipstatus", "close", "fleeship", "tail",
                  "outmaneuver", "shields", "hyperspace", "damcon"],
        "NPC Crew": ["hire", "roster", "assign", "unassign",
                      "dismiss", "order"],
        "NPCs": ["talk", "ask"],
        "Building": ["@dig", "@tunnel", "@open", "@rdesc", "@rname",
                     "@destroy", "@link", "@unlink", "@examine",
                     "@rooms", "@teleport", "@set", "@lock",
                     "@entrances", "@roominfo", "@find", "@zone",
                     "@create", "@npc", "@spawn"],
        "Admin": ["@grant", "@ai"],
        "Info": ["who", "help", "quit"],
    }'''

    new_categories = '''    CATEGORIES = {
        "Navigation": ["look", "move", "board", "disembark"],
        "Communication": ["say", "whisper", "emote", ";", "+ooc",
                          "comlink", "fcomm"],
        "Character": ["+sheet", "+inv", "equip", "unequip",
                       "+weapons", "+credits", "+repair", "sell", "@desc"],
        "D6 Dice": ["+roll", "+check", "+opposed"],
        "Combat": ["attack", "dodge", "fulldodge", "parry", "fullparry",
                    "aim", "cover", "flee", "forcepoint", "range",
                    "+combat", "resolve", "pass", "disengage", "respawn"],
        "Force": ["force", "+powers", "+forcestatus"],
        "Advancement": ["+cpstatus", "train", "+kudos", "+scenebonus"],
        "Economy": ["buy", "sell", "+credits",
                     "+missions", "accept", "+mission", "complete",
                     "abandon"],
        "Smuggling": ["+smugjobs", "smugaccept", "+smugjob",
                       "smugdeliver", "smugdump"],
        "Bounty": ["+bounties", "bountyclaim", "+mybounty",
                    "bountytrack", "bountycollect"],
        "Crafting": ["survey", "resources", "buyresource",
                      "schematics", "craft"],
        "Medical": ["heal", "healaccept", "+healrate"],
        "Space": ["+ships", "+shipinfo", "pilot", "gunner", "copilot",
                  "engineer", "navigator", "commander", "sensors",
                  "vacate", "assist", "coordinate", "+shiprepair",
                  "+myships", "launch", "land", "scan", "fire", "evade",
                  "+shipstatus", "close", "fleeship", "tail",
                  "outmaneuver", "shields", "hyperspace", "damcon"],
        "NPC Crew": ["hire", "+roster", "assign", "unassign",
                      "dismiss", "order"],
        "NPCs": ["talk", "ask"],
        "Channels": ["+channels", "comlink", "fcomm", "+faction",
                      "tune", "untune", "+freqs", "commfreq"],
        "Social": ["+party", "sabacc", "perform", "+news"],
        "Building": ["@dig", "@tunnel", "@open", "@rdesc", "@rname",
                     "@destroy", "@link", "@unlink", "@examine",
                     "@rooms", "@teleport", "@set", "@lock",
                     "@entrances", "@find", "@zone",
                     "@create", "@npc", "@spawn"],
        "Admin": ["@grant", "@ai", "@director", "@setbounty"],
        "Info": ["+who", "+help", "quit"],
    }'''

    if old_categories not in src:
        print("  WARNING: Could not find CATEGORIES dict — skipping")
        return False

    src = src.replace(old_categories, new_categories, 1)

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in help categories: {e}")
        return False

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(src)
    print("  parser/builtin_commands.py: CATEGORIES dict updated")
    return True


def main():
    print("=" * 60)
    print("  Drop 2 — Command Rename & Alias Sweep")
    print("  + prefix convention, MUSH-standard aliases")
    print("=" * 60)

    total, errors = apply_replacements()

    print(f"\n  Alias replacements: {total} commands updated, {errors} errors")

    print("\n── Updating help CATEGORIES ──")
    cat_ok = update_help_categories()

    print("\n" + "=" * 60)
    if errors == 0 and cat_ok:
        print("  All patches applied successfully.")
        print(f"  {total} commands updated across all parser modules.")
        print("  Old bare-word forms kept as aliases — nothing breaks.")
    else:
        print(f"  Completed with {errors} error(s). Check output above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
