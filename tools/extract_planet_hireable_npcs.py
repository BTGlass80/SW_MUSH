"""One-shot extractor: convert HIREABLE_CREW and PLANET_NPCS Python literals
in build_mos_eisley.py into YAML files.

Run from project root:
    python tools/extract_planet_hireable_npcs.py

Output:
    data/worlds/gcw/npcs_hireable.yaml
    data/worlds/gcw/npcs_planet.yaml

Each output file matches the data/npcs_gg7.yaml schema, with `room` resolved
from yaml_id integer to room name string via the world bundle.
"""
import os
import sys
import yaml
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build_mos_eisley import HIREABLE_CREW, PLANET_NPCS  # noqa: E402
from engine.world_loader import load_world_dry_run  # noqa: E402


# Skills that map ai_config _ai() helper produced. _ai signature:
# personality, knowledge, faction, style, fallbacks, hostile,
# behavior, model_tier, temperature, max_tokens, space_skills,
# trainer, train_skills


def _emit_npc(name, room_idx, species, desc, sheet, ai_cfg, room_name_by_id):
    """Convert a single NPC tuple into a YAML-serializable dict."""
    room_name = room_name_by_id[room_idx]

    # Pull standard char_sheet fields
    cs_out = {}
    cs_out["attributes"] = dict(sheet.get("attributes", {}))
    if sheet.get("skills"):
        cs_out["skills"] = dict(sheet["skills"])
    if sheet.get("weapon"):
        cs_out["weapon"] = sheet["weapon"]
    if sheet.get("move", 10) != 10:
        cs_out["move"] = sheet["move"]
    else:
        cs_out["move"] = 10
    # Always include scoring fields if present
    for k in ("force_points", "character_points", "dark_side_points"):
        if k in sheet:
            cs_out[k] = sheet[k]
    if sheet.get("force_sensitive"):
        cs_out["force_sensitive"] = True
    if sheet.get("force_skills"):
        cs_out["force_skills"] = sheet["force_skills"]
    if sheet.get("wound_level", 0):
        cs_out["wound_level"] = sheet["wound_level"]

    # ai_config — strip None / defaults
    ai_out = {}
    if ai_cfg.get("personality"):
        ai_out["personality"] = ai_cfg["personality"]
    if ai_cfg.get("knowledge"):
        ai_out["knowledge"] = list(ai_cfg["knowledge"])
    if ai_cfg.get("faction") and ai_cfg["faction"] != "Neutral":
        ai_out["faction"] = ai_cfg["faction"]
    if ai_cfg.get("dialogue_style"):
        ai_out["dialogue_style"] = ai_cfg["dialogue_style"]
    if ai_cfg.get("fallback_lines"):
        ai_out["fallback_lines"] = list(ai_cfg["fallback_lines"])
    if ai_cfg.get("hostile"):
        ai_out["hostile"] = True
    if ai_cfg.get("combat_behavior") and ai_cfg["combat_behavior"] != "defensive":
        ai_out["combat_behavior"] = ai_cfg["combat_behavior"]
    if ai_cfg.get("model_tier", 1) != 1:
        ai_out["model_tier"] = ai_cfg["model_tier"]
    if ai_cfg.get("temperature", 0.7) != 0.7:
        ai_out["temperature"] = ai_cfg["temperature"]
    if ai_cfg.get("max_tokens", 120) != 120:
        ai_out["max_tokens"] = ai_cfg["max_tokens"]
    # Pass-through for trainer fields and space-skills (extra _ai keys).
    # Note: _ai() stores space_skills under the "skills" key, not "space_skills".
    if ai_cfg.get("skills"):
        ai_out["skills"] = dict(ai_cfg["skills"])
    if ai_cfg.get("trainer"):
        ai_out["trainer"] = True
        ai_out["train_skills"] = list(ai_cfg.get("train_skills") or [])

    entry = {
        "name": name,
        "room": room_name,
        "species": species,
        "description": desc,
        "char_sheet": cs_out,
        "ai_config": ai_out,
    }
    return entry


def main():
    bundle = load_world_dry_run("gcw")
    room_name_by_id = {r.id: r.name for r in bundle.rooms.values()}

    # HIREABLE — file location alone identifies role; no is_hireable flag needed
    hireable_entries = []
    for tup in HIREABLE_CREW:
        name, room_idx, species, desc, sheet, ai_cfg = tup
        e = _emit_npc(name, room_idx, species, desc, sheet, ai_cfg, room_name_by_id)
        hireable_entries.append(e)

    # PLANET
    planet_entries = []
    for tup in PLANET_NPCS:
        name, room_idx, species, desc, sheet, ai_cfg = tup
        e = _emit_npc(name, room_idx, species, desc, sheet, ai_cfg, room_name_by_id)
        planet_entries.append(e)

    # Custom dumper to keep multi-line strings readable
    class LiteralStr(str): pass
    def repr_str(dumper, data):
        if "\n" in data or len(data) > 80:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=">")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)
    yaml.SafeDumper.add_representer(str, repr_str)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "worlds", "gcw")

    h_path = os.path.join(out_dir, "npcs_hireable.yaml")
    with open(h_path, "w", encoding="utf-8") as f:
        f.write("# data/worlds/gcw/npcs_hireable.yaml\n")
        f.write("# GCW Era — Hireable Crew NPCs (extracted from build_mos_eisley.py F.1a)\n")
        f.write("# Schema: name, room, species, description, char_sheet, ai_config\n")
        f.write("# Loaded by engine/npc_loader.py via era.yaml's content_refs.npcs_hireable.\n")
        f.write("# The hireable role is signaled by file location, not a per-entry flag.\n#\n")
        f.write("schema_version: 1\n\n")
        yaml.safe_dump({"npcs": hireable_entries}, f, sort_keys=False,
                       default_flow_style=False, width=100, allow_unicode=True)
    print(f"Wrote {h_path}: {len(hireable_entries)} entries")

    p_path = os.path.join(out_dir, "npcs_planet.yaml")
    with open(p_path, "w", encoding="utf-8") as f:
        f.write("# data/worlds/gcw/npcs_planet.yaml\n")
        f.write("# GCW Era — Planet-Specific NPCs (extracted from build_mos_eisley.py F.1a)\n")
        f.write("# Covers Tatooine outskirts/wastes, Nar Shaddaa, Kessel, Corellia.\n")
        f.write("# Schema: name, room, species, description, char_sheet, ai_config\n#\n")
        f.write("schema_version: 1\n\n")
        yaml.safe_dump({"npcs": planet_entries}, f, sort_keys=False,
                       default_flow_style=False, width=100, allow_unicode=True)
    print(f"Wrote {p_path}: {len(planet_entries)} entries")


if __name__ == "__main__":
    main()
