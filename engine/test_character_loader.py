# -*- coding: utf-8 -*-
"""
Test Character Loader — Reads dev/admin test character definitions from era YAML.

Loads the test character spec (testuser/testpass account + Test Jedi character)
that was previously hardcoded inline in build_mos_eisley.py. Keeping this in
YAML lets each era flavor its test character appropriately:
  - GCW: Jedi Knight (era says Jedi are hunted; the dev character is a
         fugitive god-mode account).
  - CW:  Padawan/Knight (canon era for Jedi). CW's era.yaml already
         declares both content_refs.test_character and content_refs.test_jedi
         slots — F.1c populates the GCW side; CW will follow with its own
         YAML.

Schema (per data/worlds/<era>/test_character.yaml):
    schema_version: 1
    account:
      username: testuser
      password: testpass         # PLAINTEXT here; bcrypt'd at write time
      is_admin: true
      is_builder: true
    character:
      name: ...
      species: ...
      template: ...
      faction_id: ...
      starting_room: "Docking Bay 94 - Entrance"   # name, not yaml_id
      description: ...
      credits / character_points / force_points / etc.
      attributes: { dexterity: 5D, ..., force_sensitive: true, ... }
      skills: { blaster: 8D+2, ... }
      equipment: { key: lightsaber, ... }
      inventory: { items: [...], resources: [...] }

Usage in build_mos_eisley.py:
    from engine.test_character_loader import load_era_test_character

    spec = load_era_test_character(era_dir, room_name_map)
    if spec:
        await create_test_character(db, spec)

Returns None if no test_character ref exists or the file is missing — the
caller can then decide whether to skip silently or warn.
"""
import logging
import os
from typing import Optional

import yaml

log = logging.getLogger(__name__)


def load_era_test_character(
    era_dir: str,
    room_name_map: dict[str, int],
) -> Optional[dict]:
    """
    Load and resolve the test character spec for an era.

    Reads <era_dir>/era.yaml::content_refs.test_character (single filename).
    Resolves the `starting_room` field from a room name string to the
    yaml_id integer using room_name_map.

    Returns:
        Dict with shape:
            {
              "account": {"username", "password", "is_admin", "is_builder"},
              "character": {
                "name", "species", "template", "faction_id",
                "starting_room", "starting_room_idx",  # <-- both forms
                "description", "credits", "character_points",
                "force_points", "dark_side_points", "wound_level",
                "attributes", "skills", "equipment", "inventory",
              },
            }
        Or None if no spec is configured.
    """
    era_yaml_path = os.path.join(era_dir, "era.yaml")
    if not os.path.exists(era_yaml_path):
        log.warning("era.yaml not found at %s", era_yaml_path)
        return None

    with open(era_yaml_path, "r", encoding="utf-8") as f:
        era = yaml.safe_load(f) or {}

    refs = era.get("content_refs") or {}
    test_char_file = refs.get("test_character")
    if not test_char_file:
        log.info("No test_character ref in era.yaml (era_dir=%s)", era_dir)
        return None

    spec_path = os.path.normpath(os.path.join(era_dir, test_char_file))
    if not os.path.exists(spec_path):
        log.warning("test_character YAML not found at %s", spec_path)
        return None

    with open(spec_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    account = data.get("account") or {}
    character = data.get("character") or {}

    # Validate required fields
    if not account.get("username") or not account.get("password"):
        log.warning("test_character missing account.username/password: %s", spec_path)
        return None
    if not character.get("name") or not character.get("starting_room"):
        log.warning("test_character missing character.name/starting_room: %s", spec_path)
        return None

    # Resolve starting room
    starting_room = character["starting_room"]
    starting_room_idx = room_name_map.get(starting_room)
    if starting_room_idx is None:
        # Case-insensitive fallback
        for rn, ri in room_name_map.items():
            if rn.lower() == starting_room.lower():
                starting_room_idx = ri
                break
    if starting_room_idx is None:
        log.warning(
            "test_character '%s': starting_room %r not found in room_name_map",
            character["name"], starting_room,
        )
        return None

    # Normalize description whitespace
    desc = character.get("description") or ""
    if isinstance(desc, str):
        desc = " ".join(desc.split())

    return {
        "account": {
            "username": account["username"],
            "password": account["password"],  # plaintext; caller bcrypts
            "is_admin": bool(account.get("is_admin", False)),
            "is_builder": bool(account.get("is_builder", False)),
        },
        "character": {
            "name": character["name"],
            "species": character.get("species", "Human"),
            "template": character.get("template", "scout"),
            "faction_id": character.get("faction_id", "independent"),
            "starting_room": starting_room,
            "starting_room_idx": starting_room_idx,
            "description": desc,
            "credits": int(character.get("credits", 500)),
            "character_points": int(character.get("character_points", 5)),
            "force_points": int(character.get("force_points", 1)),
            "dark_side_points": int(character.get("dark_side_points", 0)),
            "wound_level": int(character.get("wound_level", 0)),
            "attributes": dict(character.get("attributes") or {}),
            "skills": dict(character.get("skills") or {}),
            "equipment": dict(character.get("equipment") or {}),
            "inventory": dict(character.get("inventory") or {}),
        },
    }
