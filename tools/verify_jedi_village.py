"""
verify_jedi_village.py — schema + cross-reference validation for
data/worlds/clone_wars/quests/jedi_village.yaml.

Validates:
  1. File parses as YAML.
  2. Top-level shape: {schema_version: 1, quest: {...}}.
  3. Quest has the required schema fields.
  4. force_sign_seeds list — every trigger has type + at least 1 message.
  5. NPC roster — every NPC has id, display_name, species, role, home_room.
  6. NPC home_rooms resolve either to rooms_to_build OR to known
     pre-existing room slugs (jedi_council_chamber_lobby, etc.).
  7. Rooms_to_build — every room has id, name, adjacency.
  8. Step structure — same as chains.yaml schema, plus `act` field.
  9. Step locations resolve to rooms_to_build OR known pre-existing rooms.
 10. Step NPCs resolve to NPC roster (or are explicit "(none)" / "(unknown sender)").
 11. Step completion.type is from the allowed set (chains.yaml types
     plus the 5 Village extensions).
 12. Act 3 step uses path_choice completion type.
 13. Path branches all have at least: id, label, consequences.
 14. fail_states section is present and valid.
 15. All faction_rep references resolve to organizations.yaml.
 16. force_sensitive flag is in prerequisites.

Usage:
    python3 verify_jedi_village.py
or:
    SW_MUSH_REPO=/path/to/SW_MUSH python3 verify_jedi_village.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


REPO = Path(os.environ.get("SW_MUSH_REPO", os.getcwd()))
QUEST = REPO / "data" / "worlds" / "clone_wars" / "quests" / "jedi_village.yaml"
ZONES = REPO / "data" / "worlds" / "clone_wars" / "zones.yaml"
ORGS = REPO / "data" / "worlds" / "clone_wars" / "organizations.yaml"


# Allowed step completion types: union of chains.yaml types and the
# 5 Village extensions per design doc §9.

ALLOWED_COMPLETION_TYPES = {
    # Inherited from chains.yaml schema:
    "command_executed",
    "talk_to_npc",
    "combat_won",
    "skill_check_passed",
    "mission_accepted",
    "mission_completed",
    "bounty_accepted",
    "item_acquired",
    "item_used",
    "room_entered",
    "prerequisite",
    # Village extensions:
    "dialogue_completion",
    "timed_room_dwell",
    "multi_turn_dialogue_completion",
    "targeted_choice",
    "path_choice",
}

ALLOWED_NPC_ROLES = {"instructor", "contact", "antagonist"}

# Pre-existing room slugs that the Village quest references but
# doesn't build. These should resolve to either tutorial chains'
# room space, the wilderness coordinate grid, or zones.yaml.
KNOWN_PRE_EXISTING_ROOMS = {
    "jedi_council_chamber_lobby",      # Coruscant Temple — design doc lists
    "jedi_temple_gates",                # tutorial chain Path A drop_room
    "dune_sea_anchor_stones",           # wilderness landmark, pre-quest
    "dune_sea_open_grid",                # generic wilderness coordinate tile
    "dune_sea_ruined_obelisk",          # wilderness landmark
    "forgotten_jedi_shrine",            # Coruscant Underworld
    "bantha_graveyard",                 # Tatooine wilderness landmark
    "any",                               # special: step delivered cross-zone
}


# ── Test harness ──────────────────────────────────────────────────────────────

PASS, FAIL = 0, 0
errors: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        msg = label + (f": {detail}" if detail else "")
        errors.append(msg)
        print(f"  ✗ {msg}")


# ── Reference data loaders ────────────────────────────────────────────────────

def load_faction_codes() -> set[str]:
    data = yaml.safe_load(ORGS.read_text())
    codes = {f["code"] for f in data.get("factions", [])}
    codes |= {g["code"] for g in data.get("guilds", [])}
    return codes


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_top_level(data):
    print("\n[1] Top-level shape")
    check("schema_version present", "schema_version" in data)
    check("schema_version == 1", data.get("schema_version") == 1)
    check("'quest' key present", "quest" in data)
    quest = data.get("quest", {})
    check("quest_id == 'jedi_village'",
          quest.get("quest_id") == "jedi_village",
          f"got {quest.get('quest_id')}")


def test_quest_shape(data, faction_codes):
    print("\n[2] Quest top-level fields")
    quest = data.get("quest", {})
    required = {
        "quest_id", "quest_name", "description", "archetype_label",
        "faction_alignment", "starting_zone", "starting_room",
        "prerequisites", "duration_minutes", "locked", "graduation",
        "force_sign_seeds", "npcs", "rooms_to_build", "steps",
        "fail_states",
    }
    keys = set(quest.keys())
    missing = required - keys
    check("all required quest fields present", not missing,
          f"missing: {sorted(missing)}" if missing else "")

    # faction_alignment is null per design (Village is faction-neutral)
    check("faction_alignment is null (Village is faction-neutral)",
          quest.get("faction_alignment") is None,
          f"got {quest.get('faction_alignment')!r}")

    # prerequisites must include force_sensitive
    prereqs = quest.get("prerequisites", [])
    check("prerequisites includes 'force_sensitive'",
          "force_sensitive" in prereqs)
    check("prerequisites includes 'chargen_complete'",
          "chargen_complete" in prereqs)


def test_force_sign_seeds(data):
    print("\n[3] Force-sign seeds (Track B triggers)")
    quest = data["quest"]
    seeds = quest.get("force_sign_seeds", [])
    check("at least 1 force_sign_seed defined", len(seeds) >= 1,
          f"got {len(seeds)}")
    for i, seed in enumerate(seeds):
        sid = seed.get("id", f"<#{i}>")
        check(f"seed[{sid}] has type", "type" in seed)
        check(f"seed[{sid}] has flavor_messages",
              "flavor_messages" in seed and len(seed["flavor_messages"]) >= 1)


def test_npc_roster(data):
    print("\n[4] NPC roster")
    quest = data["quest"]
    npcs = quest.get("npcs", [])
    check("at least 5 NPCs in roster",
          len(npcs) >= 5,
          f"got {len(npcs)}")

    seen_ids = set()
    for npc in npcs:
        nid = npc.get("id", "<unknown>")
        check(f"npc[{nid}] has display_name", bool(npc.get("display_name")))
        check(f"npc[{nid}] has species", bool(npc.get("species")))
        check(f"npc[{nid}] has role", bool(npc.get("role")))
        check(f"npc[{nid}] has home_room", bool(npc.get("home_room")))
        check(f"npc[{nid}] has combat_flagged",
              "combat_flagged" in npc)
        check(f"npc[{nid}] is non-combat",
              npc.get("combat_flagged") is False,
              "Village NPCs must be non-combat per design §4.4")
        check(f"npc[{nid}] id is unique",
              nid not in seen_ids,
              f"duplicate id: {nid}")
        seen_ids.add(nid)


def test_rooms_to_build(data):
    print("\n[5] Rooms to build")
    quest = data["quest"]
    rooms = quest.get("rooms_to_build", [])
    check("at least 9 Village rooms", len(rooms) >= 9,
          f"got {len(rooms)}")

    seen_ids = set()
    for room in rooms:
        rid = room.get("id", "<unknown>")
        check(f"room[{rid}] has id starting with 'village_'",
              rid.startswith("village_"),
              f"got {rid}")
        check(f"room[{rid}] has name", bool(room.get("name")))
        check(f"room[{rid}] has adjacency",
              isinstance(room.get("adjacency"), list))
        check(f"room[{rid}] id is unique",
              rid not in seen_ids,
              f"duplicate id: {rid}")
        seen_ids.add(rid)

    # Sealed Sanctum has special properties
    sanctum = next((r for r in rooms if r["id"] == "village_sealed_sanctum"),
                   None)
    if sanctum:
        check("sealed_sanctum has locked_until_flag property",
              sanctum.get("properties", {}).get("locked_until_flag")
              == "spirit_trial_in_progress")


def test_npc_room_resolution(data):
    print("\n[6] NPC home_rooms resolve")
    quest = data["quest"]
    village_room_ids = {r["id"] for r in quest.get("rooms_to_build", [])}
    all_resolvable = village_room_ids | KNOWN_PRE_EXISTING_ROOMS

    for npc in quest.get("npcs", []):
        nid = npc.get("id", "<unknown>")
        home = npc.get("home_room")
        check(f"npc[{nid}] home_room '{home}' resolves",
              home in all_resolvable,
              f"not in known rooms")


def test_steps(data, faction_codes):
    print("\n[7] Step structure")
    quest = data["quest"]
    steps = quest.get("steps", [])
    village_room_ids = {r["id"] for r in quest.get("rooms_to_build", [])}
    npc_display_names = {n["display_name"] for n in quest.get("npcs", [])}

    check("at least 10 steps in chain", len(steps) >= 10,
          f"got {len(steps)}")

    # 1-indexed contiguous step numbers
    if steps:
        nums = [s.get("step") for s in steps]
        expected = list(range(1, len(steps) + 1))
        check(f"step numbers are 1..{len(steps)}",
              nums == expected,
              f"got {nums}")

    # Per-step
    for step in steps:
        sn = step.get("step", "?")
        prefix = f"  step[{sn}] {step.get('title', '?')}"

        # Required fields
        required = {
            "step", "act", "title", "location", "npc", "npc_role",
            "teaches", "objective", "npc_intro", "completion",
            "npc_complete", "reward", "next_hint",
        }
        missing = required - set(step.keys())
        if missing:
            check(f"{prefix} required fields", False,
                  f"missing: {sorted(missing)}")
            continue

        # act in {1, 2, 3}
        check(f"{prefix} act in [1,2,3]",
              step["act"] in [1, 2, 3])

        # location resolves
        loc = step["location"]
        check(f"{prefix} location '{loc}' resolves",
              loc in village_room_ids or loc in KNOWN_PRE_EXISTING_ROOMS,
              f"unknown room/zone")

        # npc_role
        check(f"{prefix} npc_role allowed",
              step["npc_role"] in ALLOWED_NPC_ROLES)

        # NPC reference resolves OR is explicit literal
        npc = step["npc"]
        npc_ok = (npc in npc_display_names
                  or npc.startswith("(")
                  or npc == "(none — wilderness navigation)")
        check(f"{prefix} npc '{npc}' resolves to roster or literal",
              npc_ok)

        # completion.type
        ct = step["completion"].get("type")
        check(f"{prefix} completion.type allowed",
              ct in ALLOWED_COMPLETION_TYPES,
              f"got '{ct}'")


def test_act3_path_choice(data, faction_codes):
    print("\n[8] Act 3 path_choice step")
    quest = data["quest"]
    act3_steps = [s for s in quest.get("steps", []) if s.get("act") == 3]
    check("at least 1 Act 3 step", len(act3_steps) >= 1,
          f"got {len(act3_steps)}")

    if not act3_steps:
        return

    choice_step = act3_steps[0]
    comp = choice_step.get("completion", {})
    check("Act 3 step uses path_choice completion type",
          comp.get("type") == "path_choice")

    branches = comp.get("branches", [])
    check("3 path branches defined", len(branches) == 3,
          f"got {len(branches)}")

    branch_ids = {b.get("id") for b in branches}
    check("branch a_jedi_order present", "a_jedi_order" in branch_ids)
    check("branch b_independent present", "b_independent" in branch_ids)
    check("branch c_dark present", "c_dark" in branch_ids)

    for b in branches:
        bid = b.get("id", "<unknown>")
        check(f"branch[{bid}] has label", bool(b.get("label")))
        check(f"branch[{bid}] has consequences",
              isinstance(b.get("consequences"), dict))

    # Path A and B set jedi_path_unlocked; Path C does NOT
    a = next((b for b in branches if b["id"] == "a_jedi_order"), {})
    b_branch = next((b for b in branches if b["id"] == "b_independent"), {})
    c = next((b for b in branches if b["id"] == "c_dark"), {})

    a_flags = a.get("consequences", {}).get("flags_set", [])
    b_flags = b_branch.get("consequences", {}).get("flags_set", [])
    c_flags = c.get("consequences", {}).get("flags_set", [])

    check("Path A sets jedi_path_unlocked",
          "jedi_path_unlocked" in a_flags)
    check("Path B sets jedi_path_unlocked",
          "jedi_path_unlocked" in b_flags)
    check("Path C does NOT set jedi_path_unlocked",
          "jedi_path_unlocked" not in c_flags)
    check("Path C sets dark_path_unlocked",
          "dark_path_unlocked" in c_flags)

    # Faction rep faction codes resolve
    for branch in branches:
        bid = branch.get("id", "<unknown>")
        rep = branch.get("consequences", {}).get("faction_rep", {})
        for fac in rep:
            check(f"branch[{bid}] faction_rep '{fac}' resolves",
                  fac in faction_codes,
                  f"unknown faction code")


def test_fail_states(data):
    print("\n[9] Permanent-fail state")
    quest = data["quest"]
    fail_states = quest.get("fail_states", [])
    check("fail_states defined", len(fail_states) >= 1,
          f"got {len(fail_states)}")

    if not fail_states:
        return

    attacked = next((f for f in fail_states if f.get("id") == "attacked_village"),
                    None)
    check("attacked_village fail state present", attacked is not None)
    if attacked:
        cons = attacked.get("consequences", {})
        cs = cons.get("chain_state", {})
        check("attacked_village marks permanent_fail",
              cs.get("permanent_fail") is True)
        check("attacked_village unsets jedi_path_unlocked",
              "jedi_path_unlocked" in cons.get("flags_unset", []))
        check("attacked_village keeps force_sensitive",
              "force_sensitive" in cons.get("flags_kept", []))


def main():
    if not QUEST.is_file():
        print(f"ERROR: {QUEST} not found")
        sys.exit(2)

    data = yaml.safe_load(QUEST.read_text())
    faction_codes = load_faction_codes()

    print(f"Loaded jedi_village.yaml")
    print(f"Loaded organizations.yaml with {len(faction_codes)} faction codes")

    test_top_level(data)
    test_quest_shape(data, faction_codes)
    test_force_sign_seeds(data)
    test_npc_roster(data)
    test_rooms_to_build(data)
    test_npc_room_resolution(data)
    test_steps(data, faction_codes)
    test_act3_path_choice(data, faction_codes)
    test_fail_states(data)

    print()
    print("─" * 60)
    print(f"PASS: {PASS}    FAIL: {FAIL}")
    if FAIL:
        print()
        print("Failures:")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ...and {len(errors) - 20} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
