"""
Audit script — boots a CommandRegistry exactly the way GameServer does and
reports every key/alias collision. No DB, no sessions, no network. Read-only.

Run:  python3 tools/audit_cmd_registry.py
"""
from __future__ import annotations

import sys
import os

# Make the project root importable regardless of cwd.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Patch CommandRegistry.register to track collisions BEFORE importing the
# command modules so every register() call passes through our recorder.
from parser.commands import CommandRegistry  # noqa: E402

_orig_register = CommandRegistry.register
_log: list[dict] = []


def _tracking_register(self, cmd):
    cls = cmd.__class__
    file = sys.modules.get(cls.__module__).__file__ if cls.__module__ else "?"
    file = os.path.basename(file or "?")
    key = cmd.key.lower()

    prior_key = self._commands.get(key)
    prior_aliases = {a: self._aliases[a] for a in cmd.aliases
                     if a.lower() in self._aliases}

    if prior_key is not None and prior_key.__class__ is not cls:
        _log.append({
            "kind": "key_clobber",
            "key": key,
            "winner": f"{cls.__name__} ({file})",
            "loser":  f"{prior_key.__class__.__name__} "
                      f"({os.path.basename(sys.modules[prior_key.__class__.__module__].__file__)})",
        })
    for alias, owner_key in prior_aliases.items():
        owner = self._commands[owner_key]
        if owner.__class__ is not cls:
            _log.append({
                "kind": "alias_clobber",
                "alias": alias,
                "now_routes_to": f"{cls.__name__} (key={key}, {file})",
                "previously_routed_to": f"{owner.__class__.__name__} "
                                        f"(key={owner_key}, "
                                        f"{os.path.basename(sys.modules[owner.__class__.__module__].__file__)})",
            })

    return _orig_register(self, cmd)


CommandRegistry.register = _tracking_register

# Now import every register_* the GameServer imports (mirror game_server.py).
from parser.builtin_commands import register_all                                 # noqa: E402
from parser.d6_commands import register_d6_commands                              # noqa: E402
from parser.building_commands import register_building_commands                  # noqa: E402
from parser.building_tier2 import register_building_tier2                        # noqa: E402
from parser.combat_commands import register_combat_commands                      # noqa: E402
from parser.force_commands import register_force_commands                        # noqa: E402
from parser.npc_commands import register_npc_commands                            # noqa: E402
from parser.space_commands import register_space_commands                        # noqa: E402
from parser.crew_commands import register_crew_commands                          # noqa: E402
from parser.mission_commands import register_mission_commands                    # noqa: E402
from parser.bounty_commands import register_bounty_commands                      # noqa: E402
from parser.director_commands import register_director_commands                  # noqa: E402
from parser.news_commands import register_news_commands                          # noqa: E402
from parser.smuggling_commands import register_smuggling_commands                # noqa: E402
from parser.medical_commands import register_medical_commands                    # noqa: E402
from parser.entertainer_commands import register_entertainer_commands            # noqa: E402
from parser.cp_commands import register_cp_commands                              # noqa: E402
from parser.sabacc_commands import register_sabacc_commands                      # noqa: E402
from parser.crafting_commands import register_crafting_commands                  # noqa: E402
from parser.tutorial_commands import register_tutorial_commands                  # noqa: E402
from parser.faction_commands import register_faction_commands                    # noqa: E402
from parser.faction_leader_commands import register_faction_leader_commands      # noqa: E402
from parser.narrative_commands import register_narrative_commands                # noqa: E402
from parser.shop_commands import register_shop_commands                          # noqa: E402
from parser.housing_commands import register_housing_commands                    # noqa: E402
from parser.spacer_quest_commands import register_spacer_quest_commands          # noqa: E402
from parser.mux_commands import register_mux_commands                            # noqa: E402
from parser.places_commands import register_places_commands                      # noqa: E402
from parser.attr_commands import register_attr_commands                          # noqa: E402
from parser.char_commands import register_char_commands                          # noqa: E402
from parser.scene_commands import register_scene_commands                        # noqa: E402
from parser.espionage_commands import register_espionage_commands                # noqa: E402
from parser.achievement_commands import register_achievement_commands            # noqa: E402
from parser.event_commands import register_event_commands                        # noqa: E402
from parser.plot_commands import register_plot_commands                          # noqa: E402
from parser.channel_commands import register_channel_commands                    # noqa: E402
from parser.party_commands import register_party_commands                        # noqa: E402
from parser.encounter_commands import register_encounter_commands                # noqa: E402
from parser.mail_commands import register_mail_commands                          # noqa: E402

reg = CommandRegistry()
register_all(reg)
register_d6_commands(reg)
register_building_commands(reg)
register_building_tier2(reg)
register_combat_commands(reg)
register_npc_commands(reg)
register_space_commands(reg)
register_crew_commands(reg)
register_mission_commands(reg)
register_bounty_commands(reg)
register_director_commands(reg)
register_news_commands(reg)
register_smuggling_commands(reg)
register_force_commands(reg)
register_medical_commands(reg)
register_entertainer_commands(reg)
register_cp_commands(reg)
register_sabacc_commands(reg)
register_crafting_commands(reg)
register_tutorial_commands(reg)
register_faction_commands(reg)
register_faction_leader_commands(reg)
register_narrative_commands(reg)
register_shop_commands(reg)
register_housing_commands(reg)
register_spacer_quest_commands(reg)
register_mux_commands(reg)
register_places_commands(reg)
register_attr_commands(reg)
register_char_commands(reg)
register_scene_commands(reg)
register_mail_commands(reg)
register_espionage_commands(reg)
register_achievement_commands(reg)
register_event_commands(reg)
register_plot_commands(reg)
register_channel_commands(reg)
register_party_commands(reg)
register_encounter_commands(reg)

print(f"\n=== Registry boot complete: {len(reg._commands)} keys, "
      f"{len(reg._aliases)} aliases ===\n")

key_clobbers   = [e for e in _log if e["kind"] == "key_clobber"]
alias_clobbers = [e for e in _log if e["kind"] == "alias_clobber"]

print(f"{'─' * 60}")
print(f"KEY CLOBBERS: {len(key_clobbers)}")
print(f"  (same key registered twice — 2nd hides the 1st entirely)")
print(f"{'─' * 60}")
for e in key_clobbers:
    print(f"  key={e['key']!r}")
    print(f"    winner:  {e['winner']}")
    print(f"    LOSER:   {e['loser']}  ← dead code")

print(f"\n{'─' * 60}")
print(f"ALIAS CLOBBERS: {len(alias_clobbers)}")
print(f"  (alias re-claimed by a different command — input routes")
print(f"   to a different handler than the original command's owner)")
print(f"{'─' * 60}")
for e in alias_clobbers:
    print(f"  alias={e['alias']!r}")
    print(f"    now routes to:    {e['now_routes_to']}")
    print(f"    previously owned: {e['previously_routed_to']}")
