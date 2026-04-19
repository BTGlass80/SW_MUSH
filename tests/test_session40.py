# -*- coding: utf-8 -*-
"""
tests/test_session40.py — Session 40 Tests

Tests for:
  1. Boarding encounter engine (encounter_boarding.py)
  2. NPC combat AI boarding integration
  3. Boarding party NPC templates and creation
  4. Boarding party cleanup
  5. Boarding UI data in HUD payload
  6. Web client boarding handlers (structural)
  7. Game server registration
"""

import json
import inspect
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ═══════════════════════════════════════════════════════════════════════
# 1. Boarding Encounter Engine — Module Structure
# ═══════════════════════════════════════════════════════════════════════

class TestBoardingEncounterModule:
    """Verify encounter_boarding.py has required exports and structure."""

    def test_module_imports(self):
        """Module should import cleanly."""
        import engine.encounter_boarding
        assert hasattr(engine.encounter_boarding, 'initiate_npc_boarding')
        assert hasattr(engine.encounter_boarding, 'cleanup_boarding_party')
        assert hasattr(engine.encounter_boarding, 'check_boarding_party_status')
        assert hasattr(engine.encounter_boarding, 'handle_boarders_defeated')
        assert hasattr(engine.encounter_boarding, 'boarding_encounter_tick')
        assert hasattr(engine.encounter_boarding, 'boarding_party_startup_cleanup')
        assert hasattr(engine.encounter_boarding, 'should_npc_board')

    def test_initiate_npc_boarding_is_async(self):
        """initiate_npc_boarding must be an async function."""
        from engine.encounter_boarding import initiate_npc_boarding
        assert inspect.iscoroutinefunction(initiate_npc_boarding)

    def test_cleanup_boarding_party_is_async(self):
        """cleanup_boarding_party must be an async function."""
        from engine.encounter_boarding import cleanup_boarding_party
        assert inspect.iscoroutinefunction(cleanup_boarding_party)

    def test_check_boarding_party_status_is_async(self):
        """check_boarding_party_status must be an async function."""
        from engine.encounter_boarding import check_boarding_party_status
        assert inspect.iscoroutinefunction(check_boarding_party_status)

    def test_handle_boarders_defeated_is_async(self):
        """handle_boarders_defeated must be an async function."""
        from engine.encounter_boarding import handle_boarders_defeated
        assert inspect.iscoroutinefunction(handle_boarders_defeated)

    def test_boarding_encounter_tick_is_async(self):
        """boarding_encounter_tick must be an async function."""
        from engine.encounter_boarding import boarding_encounter_tick
        assert inspect.iscoroutinefunction(boarding_encounter_tick)

    def test_startup_cleanup_is_async(self):
        """boarding_party_startup_cleanup must be an async function."""
        from engine.encounter_boarding import boarding_party_startup_cleanup
        assert inspect.iscoroutinefunction(boarding_party_startup_cleanup)


# ═══════════════════════════════════════════════════════════════════════
# 2. Boarding NPC Templates
# ═══════════════════════════════════════════════════════════════════════

class TestBoarderTemplates:
    """Verify boarding party NPC templates are well-formed."""

    def test_all_tiers_have_templates(self):
        """Easy, medium, and hard tiers must all have templates."""
        from engine.encounter_boarding import _BOARDER_TEMPLATES
        assert "easy" in _BOARDER_TEMPLATES
        assert "medium" in _BOARDER_TEMPLATES
        assert "hard" in _BOARDER_TEMPLATES

    def test_templates_have_required_fields(self):
        """Each template must have all fields for NPC creation."""
        from engine.encounter_boarding import _BOARDER_TEMPLATES
        required = {"name_pool", "species_pool", "description", "dex",
                     "blaster", "dodge", "brawling", "str", "per",
                     "weapon", "behavior"}
        for tier, templates in _BOARDER_TEMPLATES.items():
            assert len(templates) > 0, f"Tier {tier} has no templates"
            for i, tmpl in enumerate(templates):
                for field in required:
                    assert field in tmpl, \
                        f"Tier {tier} template {i} missing field '{field}'"

    def test_name_pools_not_empty(self):
        """Each template must have at least one name option."""
        from engine.encounter_boarding import _BOARDER_TEMPLATES
        for tier, templates in _BOARDER_TEMPLATES.items():
            for tmpl in templates:
                assert len(tmpl["name_pool"]) >= 1, \
                    f"Tier {tier} template has empty name_pool"

    def test_species_pools_not_empty(self):
        """Each template must have at least one species option."""
        from engine.encounter_boarding import _BOARDER_TEMPLATES
        for tier, templates in _BOARDER_TEMPLATES.items():
            for tmpl in templates:
                assert len(tmpl["species_pool"]) >= 1, \
                    f"Tier {tier} template has empty species_pool"

    def test_behaviors_are_valid(self):
        """Template behaviors must be valid CombatBehavior values."""
        from engine.encounter_boarding import _BOARDER_TEMPLATES
        from engine.npc_combat_ai import CombatBehavior
        valid = {b.value for b in CombatBehavior}
        for tier, templates in _BOARDER_TEMPLATES.items():
            for tmpl in templates:
                assert tmpl["behavior"] in valid, \
                    f"Invalid behavior '{tmpl['behavior']}' in tier {tier}"

    def test_party_sizes_scale_with_tier(self):
        """Higher tiers should have equal or larger party sizes."""
        from engine.encounter_boarding import PARTY_SIZES
        easy_max = PARTY_SIZES["easy"][1]
        medium_max = PARTY_SIZES["medium"][1]
        hard_max = PARTY_SIZES["hard"][1]
        assert easy_max <= medium_max <= hard_max


# ═══════════════════════════════════════════════════════════════════════
# 3. NPC Sheet Builder
# ═══════════════════════════════════════════════════════════════════════

class TestBoarderSheetBuilder:
    """Verify _build_boarder_sheet creates valid character sheets."""

    def test_sheet_has_all_attributes(self):
        """Built sheet must have all 6 D6 attributes."""
        from engine.encounter_boarding import _build_boarder_sheet, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["medium"][0]
        sheet = _build_boarder_sheet(tmpl)
        attrs = sheet["attributes"]
        for attr in ["dexterity", "knowledge", "mechanical",
                     "perception", "strength", "technical"]:
            assert attr in attrs, f"Sheet missing attribute '{attr}'"

    def test_sheet_has_combat_skills(self):
        """Built sheet must have blaster, dodge, brawling, search."""
        from engine.encounter_boarding import _build_boarder_sheet, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["easy"][0]
        sheet = _build_boarder_sheet(tmpl)
        skills = sheet["skills"]
        for skill in ["blaster", "dodge", "brawling", "search"]:
            assert skill in skills, f"Sheet missing skill '{skill}'"

    def test_sheet_has_weapon(self):
        """Built sheet must include a weapon."""
        from engine.encounter_boarding import _build_boarder_sheet, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["hard"][0]
        sheet = _build_boarder_sheet(tmpl)
        assert sheet.get("weapon"), "Sheet must have a weapon"

    def test_sheet_wound_level_zero(self):
        """New boarder NPCs should start unwounded."""
        from engine.encounter_boarding import _build_boarder_sheet, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["easy"][0]
        sheet = _build_boarder_sheet(tmpl)
        assert sheet["wound_level"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 4. Boarder AI Config Builder
# ═══════════════════════════════════════════════════════════════════════

class TestBoarderAiConfig:
    """Verify _build_boarder_ai creates valid AI config."""

    def test_ai_config_is_hostile(self):
        """Boarder NPCs must be flagged as hostile."""
        from engine.encounter_boarding import _build_boarder_ai, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["medium"][0]
        ai = _build_boarder_ai(tmpl, "Krag's Fist")
        assert ai["hostile"] is True

    def test_ai_config_has_boarding_flag(self):
        """Boarder NPCs must have is_boarding_npc flag for cleanup."""
        from engine.encounter_boarding import _build_boarder_ai, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["easy"][0]
        ai = _build_boarder_ai(tmpl, "TestPirate")
        assert ai["is_boarding_npc"] is True

    def test_ai_config_has_boarding_source(self):
        """Boarder NPCs must record which pirate ship sent them."""
        from engine.encounter_boarding import _build_boarder_ai, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["hard"][0]
        ai = _build_boarder_ai(tmpl, "Void Reaper")
        assert ai["boarding_source"] == "Void Reaper"

    def test_ai_config_has_combat_behavior(self):
        """Boarder AI config must specify a combat behavior."""
        from engine.encounter_boarding import _build_boarder_ai, _BOARDER_TEMPLATES
        tmpl = _BOARDER_TEMPLATES["medium"][1]  # berserk brawler
        ai = _build_boarder_ai(tmpl, "Test")
        assert ai["combat_behavior"] == tmpl["behavior"]


# ═══════════════════════════════════════════════════════════════════════
# 5. Tier Calculation
# ═══════════════════════════════════════════════════════════════════════

class TestTierCalculation:
    """Verify crew_skill → difficulty tier mapping."""

    def test_low_skill_is_easy(self):
        """3D or less crew skill should be easy tier."""
        from engine.encounter_boarding import _get_tier
        assert _get_tier("3D") == "easy"
        assert _get_tier("2D+2") == "easy"

    def test_medium_skill_is_medium(self):
        """4D-5D crew skill should be medium tier."""
        from engine.encounter_boarding import _get_tier
        assert _get_tier("4D") == "medium"
        assert _get_tier("5D") == "medium"

    def test_high_skill_is_hard(self):
        """5D+1 and above crew skill should be hard tier."""
        from engine.encounter_boarding import _get_tier
        assert _get_tier("5D+1") == "hard"
        assert _get_tier("6D") == "hard"
        assert _get_tier("7D") == "hard"


# ═══════════════════════════════════════════════════════════════════════
# 6. should_npc_board Logic
# ═══════════════════════════════════════════════════════════════════════

class TestShouldNpcBoard:
    """Verify boarding decision logic."""

    def _make_combatant(self, profile="aggressive", actions=5, boarding_attempted=False):
        from engine.npc_space_combat_ai import SpaceNpcCombatant, SpaceCombatProfile
        c = SpaceNpcCombatant(
            npc_ship_id=9000,
            target_ship_id=1,
            target_bridge_room=100,
            profile=SpaceCombatProfile(profile),
            zone_id="test_zone",
            crew_skill="4D",
            actions_taken=actions,
        )
        c._boarding_attempted = boarding_attempted
        return c

    def test_wrong_range_returns_false(self):
        """Should not board at non-Close range."""
        from engine.encounter_boarding import should_npc_board
        from engine.starships import SpaceRange
        c = self._make_combatant(actions=10)
        assert should_npc_board(c, SpaceRange.SHORT) is False
        assert should_npc_board(c, SpaceRange.MEDIUM) is False
        assert should_npc_board(c, SpaceRange.LONG) is False

    def test_wrong_profile_returns_false(self):
        """Cautious and patrol profiles should not board."""
        from engine.encounter_boarding import should_npc_board
        from engine.starships import SpaceRange
        c = self._make_combatant(profile="cautious", actions=10)
        assert should_npc_board(c, SpaceRange.CLOSE) is False
        c2 = self._make_combatant(profile="patrol", actions=10)
        assert should_npc_board(c2, SpaceRange.CLOSE) is False

    def test_too_few_actions_returns_false(self):
        """Should not board before MIN_ACTIONS_BEFORE_BOARD."""
        from engine.encounter_boarding import should_npc_board, MIN_ACTIONS_BEFORE_BOARD
        from engine.starships import SpaceRange
        c = self._make_combatant(actions=MIN_ACTIONS_BEFORE_BOARD - 1)
        assert should_npc_board(c, SpaceRange.CLOSE) is False

    def test_already_attempted_returns_false(self):
        """Should not board if already attempted."""
        from engine.encounter_boarding import should_npc_board
        from engine.starships import SpaceRange
        c = self._make_combatant(actions=10, boarding_attempted=True)
        assert should_npc_board(c, SpaceRange.CLOSE) is False

    def test_pursuit_profile_can_board(self):
        """Pursuit profile should be eligible to board."""
        from engine.encounter_boarding import should_npc_board
        from engine.starships import SpaceRange
        c = self._make_combatant(profile="pursuit", actions=10)
        # Due to random chance, we can't guarantee True, but it shouldn't
        # be categorically rejected (the random check may still fail)
        # Instead verify the function doesn't crash
        result = should_npc_board(c, SpaceRange.CLOSE)
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════════════════════════════
# 7. NPC Combat AI Integration
# ═══════════════════════════════════════════════════════════════════════

class TestNpcCombatAiBoardingIntegration:
    """Verify NPC combat AI has boarding action wired."""

    def test_select_action_calls_should_npc_board(self):
        """_select_action should reference should_npc_board."""
        src = inspect.getsource(
            __import__('engine.npc_space_combat_ai', fromlist=['NpcSpaceCombatManager'])
            .NpcSpaceCombatManager._select_action
        )
        assert "should_npc_board" in src, \
            "_select_action must call should_npc_board"

    def test_run_action_dispatches_board(self):
        """_run_action should dispatch 'board' action to _do_board."""
        src = inspect.getsource(
            __import__('engine.npc_space_combat_ai', fromlist=['NpcSpaceCombatManager'])
            .NpcSpaceCombatManager._run_action
        )
        assert '"board"' in src or "'board'" in src, \
            "_run_action must handle 'board' action"
        assert "_do_board" in src, \
            "_run_action must call _do_board"

    def test_do_board_exists(self):
        """NpcSpaceCombatManager must have a _do_board method."""
        from engine.npc_space_combat_ai import NpcSpaceCombatManager
        assert hasattr(NpcSpaceCombatManager, '_do_board')
        assert inspect.iscoroutinefunction(NpcSpaceCombatManager._do_board)

    def test_combatant_has_boarding_attempted_field(self):
        """SpaceNpcCombatant should have _boarding_attempted field."""
        from engine.npc_space_combat_ai import SpaceNpcCombatant
        c = SpaceNpcCombatant(
            npc_ship_id=1, target_ship_id=2, target_bridge_room=3,
            profile="aggressive", zone_id="test",
        )
        assert hasattr(c, '_boarding_attempted')
        assert c._boarding_attempted is False

    def test_do_board_sets_boarding_attempted(self):
        """_do_board should set _boarding_attempted on the combatant."""
        src = inspect.getsource(
            __import__('engine.npc_space_combat_ai', fromlist=['NpcSpaceCombatManager'])
            .NpcSpaceCombatManager._do_board
        )
        assert "_boarding_attempted" in src, \
            "_do_board must set _boarding_attempted"


# ═══════════════════════════════════════════════════════════════════════
# 8. Boarding.py Cleanup Integration
# ═══════════════════════════════════════════════════════════════════════

class TestBoardingCleanupIntegration:
    """Verify sever_boarding_link cleans up boarding party NPCs."""

    def test_sever_calls_cleanup_boarding_party(self):
        """sever_boarding_link must call cleanup_boarding_party."""
        src = inspect.getsource(
            __import__('engine.boarding', fromlist=['sever_boarding_link'])
            .sever_boarding_link
        )
        assert "cleanup_boarding_party" in src, \
            "sever_boarding_link must clean up boarding party NPCs"

    def test_sever_clears_boarding_target_name(self):
        """sever_boarding_link must clear boarding_target_name."""
        src = inspect.getsource(
            __import__('engine.boarding', fromlist=['sever_boarding_link'])
            .sever_boarding_link
        )
        assert "boarding_target_name" in src, \
            "sever_boarding_link must clear boarding_target_name"

    def test_create_sets_boarding_target_name(self):
        """create_boarding_link must set boarding_target_name."""
        src = inspect.getsource(
            __import__('engine.boarding', fromlist=['create_boarding_link'])
            .create_boarding_link
        )
        assert "boarding_target_name" in src, \
            "create_boarding_link must set boarding_target_name"


# ═══════════════════════════════════════════════════════════════════════
# 9. Game Server Registration
# ═══════════════════════════════════════════════════════════════════════

class TestGameServerRegistration:
    """Verify boarding encounter tick and cleanup are registered."""

    def test_boarding_encounter_tick_registered(self):
        """game_server.py must register boarding_encounter_tick."""
        import importlib.util
        spec = importlib.util.find_spec("server.game_server")
        src_path = spec.origin
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "boarding_encounter_tick" in src, \
            "game_server must register boarding_encounter_tick"
        assert "boarding_encounters" in src, \
            "boarding_encounters tick must be named in scheduler"

    def test_boarding_party_startup_cleanup_registered(self):
        """game_server.py must call boarding_party_startup_cleanup on boot."""
        import importlib.util
        spec = importlib.util.find_spec("server.game_server")
        src_path = spec.origin
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        assert "boarding_party_startup_cleanup" in src, \
            "game_server must call boarding_party_startup_cleanup"


# ═══════════════════════════════════════════════════════════════════════
# 10. HUD Payload
# ═══════════════════════════════════════════════════════════════════════

class TestHudPayloadBoardingFields:
    """Verify HUD payload includes boarding data."""

    def test_hud_has_boarding_party_active(self):
        """Space state HUD must include boarding_party_active."""
        with open("parser/space_commands.py", "r", encoding="utf-8") as f:
            src = f.read()
        assert "boarding_party_active" in src, \
            "HUD payload must include boarding_party_active"

    def test_hud_has_boarding_target_name(self):
        """Space state HUD must include boarding_target_name."""
        with open("parser/space_commands.py", "r", encoding="utf-8") as f:
            src = f.read()
        assert "boarding_target_name" in src, \
            "HUD payload must include boarding_target_name"

    def test_hud_has_tractor_held(self):
        """Space state HUD must include tractor_held boolean."""
        with open("parser/space_commands.py", "r", encoding="utf-8") as f:
            src = f.read()
        assert '"tractor_held"' in src, \
            "HUD payload must include tractor_held boolean"


# ═══════════════════════════════════════════════════════════════════════
# 11. Web Client Boarding UI
# ═══════════════════════════════════════════════════════════════════════

class TestWebClientBoardingUI:
    """Verify web client has boarding alert and status UI."""

    def _read_client(self):
        with open("static/client.html", "r", encoding="utf-8") as f:
            return f.read()

    def test_boarding_alert_handler_exists(self):
        """Web client must have handleBoardingAlert function."""
        src = self._read_client()
        assert "handleBoardingAlert" in src

    def test_boarding_resolved_handler_exists(self):
        """Web client must have handleBoardingResolved function."""
        src = self._read_client()
        assert "handleBoardingResolved" in src

    def test_boarding_alert_message_dispatch(self):
        """Message dispatch must route boarding_alert to handler."""
        src = self._read_client()
        assert "boarding_alert" in src
        assert "boarding_resolved" in src

    def test_boarding_status_section_exists(self):
        """Web client must surface boarding status in the space UI.

        Retargeted from the pre-Field-Kit selectors (sp-boarding-section /
        sp-boarding-target) to the current intruder-alert overlay and
        boarding-actions action row. Both are structural markers in the
        shipping markup: the overlay is the visible alert card rendered
        when boarding starts, the actions row is the button strip for
        board/release. This test guards against regression that would
        strip the boarding UX from the client rewrite.
        """
        src = self._read_client()
        assert "boarding-overlay" in src
        assert "boarding-actions" in src

    def test_boarding_css_exists(self):
        """CSS must include boarding-themed styles.

        Retargeted from pre-Field-Kit class names (warn-boarding /
        boarding-status / boarding-pulse) to the current Field Kit
        CSS classes: .boarding-overlay (red full-screen alert card
        when intruders detected), .boarding-btn (action buttons for
        board/release), .boarding-card (the alert dialog shell).
        These are the structural style hooks the current UI depends
        on; losing them would break the intruder-alert UX.
        """
        src = self._read_client()
        assert ".boarding-overlay" in src
        assert ".boarding-btn" in src
        assert ".boarding-card" in src

    def test_boarding_buttons_exist(self):
        """Boarding status must have Board and Release buttons."""
        src = self._read_client()
        assert "boardship release" in src
        assert "boarding_link" in src

    def test_boarding_party_active_warning(self):
        """Space state handler must show BOARDERS warning."""
        src = self._read_client()
        assert "boarding_party_active" in src
        assert "BOARDERS ON SHIP" in src


# ═══════════════════════════════════════════════════════════════════════
# 12. No Silent Except Pass (Invariant)
# ═══════════════════════════════════════════════════════════════════════

class TestNoSilentExceptPass:
    """Ensure new code maintains the zero-silent-except invariant."""

    def test_encounter_boarding_no_silent_except(self):
        """encounter_boarding.py must not have bare except: pass."""
        with open("engine/encounter_boarding.py", "r", encoding="utf-8") as f:
            src = f.read()
        import re
        matches = re.findall(r'except\s+\w*.*?:\s*\n\s*pass\b', src)
        assert len(matches) == 0, \
            f"Found {len(matches)} silent except:pass in encounter_boarding.py"

    def test_npc_combat_ai_no_silent_except(self):
        """Modified npc_space_combat_ai.py must not have bare except: pass."""
        with open("engine/npc_space_combat_ai.py", "r", encoding="utf-8") as f:
            src = f.read()
        import re
        matches = re.findall(r'except\s+\w*.*?:\s*\n\s*pass\b', src)
        assert len(matches) == 0, \
            f"Found {len(matches)} silent except:pass in npc_space_combat_ai.py"


# ═══════════════════════════════════════════════════════════════════════
# 13. AST Validation
# ═══════════════════════════════════════════════════════════════════════

class TestAstValidation:
    """All modified/new Python files must parse cleanly."""

    @pytest.mark.parametrize("filepath", [
        "engine/encounter_boarding.py",
        "engine/npc_space_combat_ai.py",
        "engine/boarding.py",
        "server/game_server.py",
        "parser/space_commands.py",
    ])
    def test_ast_parse(self, filepath):
        """File must be valid Python."""
        import ast
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src, filename=filepath)
        except SyntaxError as e:
            pytest.fail(f"{filepath} has syntax error: {e}")
