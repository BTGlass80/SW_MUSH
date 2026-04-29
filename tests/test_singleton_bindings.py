"""
Regression tests for the singleton manager bindings on GameServer
(cw_preflight_checklist_v1.md §A.2).

Without these bindings, any portal handler doing
`getattr(self._game, "<mgr>", None)` against an unbound singleton silently
returns None and the route 503s — the exact bug class that broke the
portal Reference page on Apr 27.

These tests pin:
  1. The expected attribute exists on a constructed GameServer
  2. It is non-None
  3. It is the same instance the module-level getter returns
     (so the singleton invariant isn't accidentally broken).
"""

from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest

# Materialize server.game_server so patch() target lookups resolve.
import server.game_server  # noqa: F401


# Each entry: (GameServer attribute, getter module, getter function)
SINGLETON_BINDINGS = [
    ("encounter_mgr",     "engine.space_encounters",     "get_encounter_manager"),
    ("bounty_board",      "engine.bounty_board",         "get_bounty_board"),
    ("mission_board",     "engine.missions",             "get_mission_board"),
    ("smuggling_board",   "engine.smuggling",            "get_smuggling_board"),
    ("party_mgr",         "engine.party",                "get_party_manager"),
    ("ambient_mgr",       "engine.ambient_events",       "get_ambient_manager"),
    ("world_event_mgr",   "engine.world_events",         "get_world_event_manager"),
    ("director",          "engine.director",             "get_director"),
    ("traffic_mgr",       "engine.npc_space_traffic",    "get_traffic_manager"),
    ("npc_combat_mgr",    "engine.npc_space_combat_ai",  "get_npc_combat_manager"),
    ("space_grid",        "engine.starships",            "get_space_grid"),
    ("ship_registry",     "engine.starships",            "get_ship_registry"),
    ("weapon_registry",   "engine.weapons",              "get_weapon_registry"),
]


def _construct_gameserver():
    """
    Build a GameServer with the heavyweight DB/AI side effects stubbed.
    Encounter-handler registrars are also stubbed so __init__ doesn't
    bind handlers on the real singleton — the binding itself is what
    we want to test, not the handler registration.
    """
    patches = [
        patch("server.game_server.Database"),
        patch("server.game_server.AIManager"),
        # Encounter-handler registrar stubs — keep the singletons clean.
        patch("server.game_server.register_channel_commands"),
        patch("server.game_server.register_party_commands"),
        patch("server.game_server.register_encounter_commands"),
        # Encounter-handler stubs: these will be wired into game_server.py
        # when the encounter system integration lands. Until then, create=True
        # lets the mock stand in for an attribute that doesn't exist yet.
        patch("server.game_server.register_patrol_handlers", create=True),
        patch("server.game_server.register_pirate_handlers", create=True),
        patch("server.game_server.register_anomaly_handlers", create=True),
        patch("server.game_server.register_hunter_handlers", create=True),
        patch("server.game_server.register_texture_handlers", create=True),
    ]
    for p in patches:
        p.start()
    from server.game_server import GameServer
    return GameServer()


@pytest.fixture
def gameserver():
    gs = _construct_gameserver()
    yield gs
    patch.stopall()


# ── 1. Each binding exists and is non-None ──────────────────────────────────

@pytest.mark.parametrize("attr,_module,_getter", SINGLETON_BINDINGS)
def test_binding_exists_on_gameserver(gameserver, attr, _module, _getter):
    """
    `getattr(gs, attr, None)` must return a non-None value.  This is the
    exact accessor the portal uses, so passing here means the portal
    won't 503 on this manager.
    """
    bound = getattr(gameserver, attr, None)
    assert bound is not None, (
        f"GameServer.{attr} is unbound — portal calls "
        f"getattr(self._game, '{attr}', None) will silently return None "
        f"and the route will return HTTP 503."
    )


# ── 2. Each binding is the singleton instance ───────────────────────────────

@pytest.mark.parametrize("attr,module_path,getter_name", SINGLETON_BINDINGS)
def test_binding_is_singleton_instance(gameserver, attr, module_path,
                                       getter_name):
    """
    The bound attribute must be the *same object* the module-level getter
    returns.  If a future change accidentally constructs a fresh manager
    rather than calling the getter, two divergent instances exist
    (one bound, one used by the rest of the codebase) — a subtle bug
    where state lives in two places.
    """
    import importlib
    mod = importlib.import_module(module_path)
    getter = getattr(mod, getter_name)
    bound = getattr(gameserver, attr)
    assert bound is getter(), (
        f"GameServer.{attr} is not the same instance as "
        f"{module_path}.{getter_name}() — binding diverged from singleton."
    )


# ── 3. Existing pre-A.2 bindings still present (no regressions) ─────────────

PRE_EXISTING_BINDINGS = [
    "session_mgr",
    "species_reg",
    "skill_reg",
    "registry",
    "help_mgr",
    "ai_manager",
    "tutorial",
]


@pytest.mark.parametrize("attr", PRE_EXISTING_BINDINGS)
def test_pre_existing_bindings_preserved(gameserver, attr):
    """The bindings that existed before this drop must still be present."""
    assert getattr(gameserver, attr, None) is not None, (
        f"Pre-existing GameServer.{attr} binding was lost in this drop."
    )
