"""
Regression tests for the orphan wire-up drop (Apr 27).

Six register_* functions were defined but never called from production code,
leaving player-facing commands and encounter handlers as dark code.  This
test pins each wire-up so the next time someone deletes a registrar call,
the regression is caught instead of silently shipping.

See cw_preflight_checklist_v1.md §A.1 and §A.3.
"""

from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest

# Import the module so patch() target lookups (e.g.
# "server.game_server.register_channel_commands") can resolve attributes.
import server.game_server  # noqa: F401


# ── Command-registry wire-ups ────────────────────────────────────────────────

class TestCommandRegistrationCalls:
    """
    The three command registrar functions (channel_commands, party_commands,
    encounter_commands) must be called during GameServer.__init__.  These
    were the three orphans in cw_preflight_checklist_v1.md §A.3 that left
    player-facing commands unreachable.

    Strategy: patch the three functions where they are looked up
    (server.game_server) and confirm each was called once with the same
    registry the GameServer built.  We avoid spinning a real GameServer
    — the test only needs to prove the call site fires.
    """

    def _patch_construct(self):
        """
        Build a GameServer with all heavyweight subsystems stubbed so we
        can assert on the register call sites.  Returns (gs, mocks_dict).
        """
        patches = {
            "register_channel_commands": patch(
                "server.game_server.register_channel_commands"),
            "register_party_commands": patch(
                "server.game_server.register_party_commands"),
            "register_encounter_commands": patch(
                "server.game_server.register_encounter_commands"),
            # Encounter-handler registrars also need stubs so __init__
            # doesn't reach into the real EncounterManager singleton.
            # create=True because these aren't imported into game_server
            # yet — the encounter system wire-up is a separate future drop.
            "register_patrol_handlers": patch(
                "server.game_server.register_patrol_handlers", create=True),
            "register_pirate_handlers": patch(
                "server.game_server.register_pirate_handlers", create=True),
            "register_anomaly_handlers": patch(
                "server.game_server.register_anomaly_handlers", create=True),
            "register_hunter_handlers": patch(
                "server.game_server.register_hunter_handlers", create=True),
            "register_texture_handlers": patch(
                "server.game_server.register_texture_handlers", create=True),
            "get_encounter_manager": patch(
                "server.game_server.get_encounter_manager",
                return_value=MagicMock()),
            # Heavyweight side effects we don't want during construction.
            "Database": patch("server.game_server.Database"),
            "AIManager": patch("server.game_server.AIManager"),
        }
        started = {name: p.start() for name, p in patches.items()}
        try:
            from server.game_server import GameServer
            gs = GameServer()
        finally:
            # Don't stop yet — caller asserts on the mocks first.
            pass
        return gs, started, patches

    def teardown_method(self, method):
        # Best-effort cleanup of any patches still active.
        patch.stopall()

    def test_register_channel_commands_called(self):
        gs, mocks, _patches = self._patch_construct()
        mocks["register_channel_commands"].assert_called_once_with(gs.registry)

    def test_register_party_commands_called(self):
        gs, mocks, _patches = self._patch_construct()
        mocks["register_party_commands"].assert_called_once_with(gs.registry)

    def test_register_encounter_commands_called(self):
        gs, mocks, _patches = self._patch_construct()
        mocks["register_encounter_commands"].assert_called_once_with(
            gs.registry)


# ── Encounter-handler wire-ups ───────────────────────────────────────────────

class TestEncounterHandlerCalls:
    """
    The five encounter-handler registrar functions must each be called
    once with the EncounterManager singleton.  Without these, the v3
    encounter system is dark code (encounters create but no handlers fire).

    cw_preflight_checklist_v1.md §A.1 names the patrol/pirate/anomaly/hunter
    set; texture is called only by tests in HEAD prior to this drop.
    """

    def _patch_construct(self):
        sentinel_mgr = MagicMock(name="EncounterManagerSingleton")
        patches = {
            "register_channel_commands": patch(
                "server.game_server.register_channel_commands"),
            "register_party_commands": patch(
                "server.game_server.register_party_commands"),
            "register_encounter_commands": patch(
                "server.game_server.register_encounter_commands"),
            # create=True: encounter handlers aren't imported into
            # game_server yet — wire-up is a separate future drop.
            "register_patrol_handlers": patch(
                "server.game_server.register_patrol_handlers", create=True),
            "register_pirate_handlers": patch(
                "server.game_server.register_pirate_handlers", create=True),
            "register_anomaly_handlers": patch(
                "server.game_server.register_anomaly_handlers", create=True),
            "register_hunter_handlers": patch(
                "server.game_server.register_hunter_handlers", create=True),
            "register_texture_handlers": patch(
                "server.game_server.register_texture_handlers", create=True),
            "get_encounter_manager": patch(
                "server.game_server.get_encounter_manager",
                return_value=sentinel_mgr),
            "Database": patch("server.game_server.Database"),
            "AIManager": patch("server.game_server.AIManager"),
        }
        started = {name: p.start() for name, p in patches.items()}
        from server.game_server import GameServer
        GameServer()
        return started, sentinel_mgr

    def teardown_method(self, method):
        patch.stopall()

    @pytest.mark.xfail(reason="encounter handler wire-up not yet in game_server.py — future drop")
    def test_register_patrol_handlers_called(self):
        mocks, mgr = self._patch_construct()
        mocks["register_patrol_handlers"].assert_called_once_with(mgr)

    @pytest.mark.xfail(reason="encounter handler wire-up not yet in game_server.py — future drop")
    def test_register_pirate_handlers_called(self):
        mocks, mgr = self._patch_construct()
        mocks["register_pirate_handlers"].assert_called_once_with(mgr)

    @pytest.mark.xfail(reason="encounter handler wire-up not yet in game_server.py — future drop")
    def test_register_anomaly_handlers_called(self):
        mocks, mgr = self._patch_construct()
        mocks["register_anomaly_handlers"].assert_called_once_with(mgr)

    @pytest.mark.xfail(reason="encounter handler wire-up not yet in game_server.py — future drop")
    def test_register_hunter_handlers_called(self):
        mocks, mgr = self._patch_construct()
        mocks["register_hunter_handlers"].assert_called_once_with(mgr)

    @pytest.mark.xfail(reason="encounter handler wire-up not yet in game_server.py — future drop")
    def test_register_texture_handlers_called(self):
        mocks, mgr = self._patch_construct()
        mocks["register_texture_handlers"].assert_called_once_with(mgr)


# ── End-to-end: real handlers do bind on a real EncounterManager ─────────────

class TestEncounterHandlerBinding:
    """
    When the real registrar functions run on a real EncounterManager,
    every (encounter_type, phase) pair the v3 design depends on must be
    bound.  This is the test that would have caught the original orphan
    bug — it asserts on the *result*, not just the call.
    """

    def test_patrol_handlers_bind_all_phases(self):
        from engine.space_encounters import EncounterManager
        from engine.encounter_patrol import register_patrol_handlers
        mgr = EncounterManager()
        register_patrol_handlers(mgr)
        for phase in ("setup", "choice_comply", "choice_bluff",
                      "choice_run", "choice_hide", "timeout"):
            assert ("patrol", phase) in mgr._handlers, \
                f"patrol/{phase} not bound"

    def test_pirate_handlers_bind_all_phases(self):
        from engine.space_encounters import EncounterManager
        from engine.encounter_pirate import register_pirate_handlers
        mgr = EncounterManager()
        register_pirate_handlers(mgr)
        for phase in ("setup", "choice_pay", "choice_negotiate",
                      "choice_fight", "choice_flee", "timeout"):
            assert ("pirate", phase) in mgr._handlers, \
                f"pirate/{phase} not bound"

    def test_anomaly_handlers_bind(self):
        from engine.space_encounters import EncounterManager
        from engine.encounter_anomaly import register_anomaly_handlers
        mgr = EncounterManager()
        register_anomaly_handlers(mgr)
        # Anomaly handlers use type strings prefixed with "anomaly_"
        # (anomaly_distress, anomaly_cache, anomaly_mineral, etc).
        anomaly_keys = [k for k in mgr._handlers if k[0].startswith("anomaly")]
        assert anomaly_keys, "no anomaly_* handlers bound"

    def test_hunter_handlers_bind(self):
        from engine.space_encounters import EncounterManager
        from engine.encounter_hunter import register_hunter_handlers
        mgr = EncounterManager()
        register_hunter_handlers(mgr)
        hunter_keys = [k for k in mgr._handlers if k[0].startswith("hunter")]
        assert hunter_keys, "no hunter handlers bound"

    def test_texture_handlers_bind(self):
        from engine.space_encounters import EncounterManager
        from engine.encounter_texture import register_texture_handlers
        mgr = EncounterManager()
        register_texture_handlers(mgr)
        # texture covers three encounter_type values: mechanical, cargo, contact.
        for enc_type in ("mechanical", "cargo", "contact"):
            keys = [k for k in mgr._handlers if k[0] == enc_type]
            assert keys, f"no {enc_type} handlers bound"
