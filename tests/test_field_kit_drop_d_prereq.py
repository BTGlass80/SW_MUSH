"""Field Kit Drop D — server-side prerequisite tests.

Per `field_kit_design_decomposition_v2.md` §6 ("Server-side dependencies")
and `field_kit_open_questions_v1_1.md` §D2, before the ground-combat HUD
client work can land we need:

  · `combat_state.theatre` field present in the payload from
    `engine/combat.py:CombatInstance.to_hud_dict()`
  · Default theatre is `'ground'` (matches current sole call site,
    parser/combat_commands.py)
  · `theatre` is configurable at construction time so a future space
    combat path that adopts CombatInstance can report `'space'`
  · Allowed values are `'ground'` and `'space'` (anything else will
    fail to activate either HUD overlay on the client)

The client uses this field to decide between the amber datapad combat
HUD (Drop D ground) and the cyan cockpit HUD (Drop E space). Until
this field exists, the client cannot route to the correct overlay.
"""
from __future__ import annotations

import pytest

from engine.character import SkillRegistry
from engine.combat import CombatInstance


@pytest.fixture
def empty_combat() -> CombatInstance:
    """A bare CombatInstance with no combatants, used for HUD shape tests."""
    return CombatInstance(room_id=1, skill_reg=SkillRegistry())


# ───────────────────────────────────────────────────────────────────────
# Constructor accepts and stores theatre
# ───────────────────────────────────────────────────────────────────────


class TestTheatreConstructor:

    def test_default_theatre_is_ground(self, empty_combat: CombatInstance):
        """Default matches sole call site (parser/combat_commands.py is
        ground-only today). If this regresses, ground combat will start
        reporting empty/None theatre and the client overlay will not
        activate."""
        assert empty_combat.theatre == "ground"

    def test_explicit_ground_theatre(self):
        c = CombatInstance(room_id=1, skill_reg=SkillRegistry(),
                           theatre="ground")
        assert c.theatre == "ground"

    def test_explicit_space_theatre(self):
        """Future-proofing: if/when space combat migrates to CombatInstance,
        it must be able to mark itself 'space' so the client can route to
        the cockpit HUD instead of the datapad."""
        c = CombatInstance(room_id=1, skill_reg=SkillRegistry(),
                           theatre="space")
        assert c.theatre == "space"

    def test_theatre_is_keyword_only_friendly(self):
        """The constructor signature should accept theatre as a kwarg
        without conflicting with existing keyword args (default_range,
        cover_max). This guards against accidental positional collisions
        when adding theatre."""
        from engine.combat import RangeBand
        c = CombatInstance(
            room_id=1,
            skill_reg=SkillRegistry(),
            default_range=RangeBand.MEDIUM,
            cover_max=2,
            theatre="space",
        )
        assert c.theatre == "space"
        assert c.cover_max == 2
        assert c.default_range == RangeBand.MEDIUM


# ───────────────────────────────────────────────────────────────────────
# to_hud_dict() exposes theatre to the client
# ───────────────────────────────────────────────────────────────────────


class TestTheatreInHudDict:

    def test_theatre_key_present_in_hud(self, empty_combat: CombatInstance):
        """Drop D client will read combat_state.theatre. If the key is
        missing the client cannot route between datapad and cockpit
        overlays."""
        hud = empty_combat.to_hud_dict()
        assert "theatre" in hud, (
            "combat_state payload missing 'theatre' field — "
            "Field Kit Drop D server-side prereq has regressed"
        )

    def test_default_hud_theatre_is_ground(self, empty_combat: CombatInstance):
        hud = empty_combat.to_hud_dict()
        assert hud["theatre"] == "ground"

    def test_space_theatre_in_hud(self):
        c = CombatInstance(room_id=1, skill_reg=SkillRegistry(),
                           theatre="space")
        hud = c.to_hud_dict()
        assert hud["theatre"] == "space"

    def test_theatre_present_alongside_existing_fields(
        self, empty_combat: CombatInstance
    ):
        """Adding theatre must not displace any existing HUD field. The
        client already consumes round, phase, combatants, your_actions,
        waiting_for, pose_deadline — all must remain."""
        hud = empty_combat.to_hud_dict()
        for required in (
            "active", "round", "phase", "theatre", "combatants",
            "your_actions", "waiting_for", "pose_deadline",
        ):
            assert required in hud, (
                f"to_hud_dict() lost required field '{required}'"
            )

    def test_theatre_with_viewer_id(self, empty_combat: CombatInstance):
        """Viewer-id branch must still surface theatre."""
        hud = empty_combat.to_hud_dict(viewer_id=42)
        assert hud["theatre"] == "ground"


# ───────────────────────────────────────────────────────────────────────
# Existing call site still works (regression guard)
# ───────────────────────────────────────────────────────────────────────


class TestExistingCallSiteUnchanged:

    def test_combat_commands_construction_pattern(self):
        """parser/combat_commands.py constructs CombatInstance with
        positional room_id + skill_reg and a cover_max kwarg. That
        signature must still work — adding theatre as a trailing
        kwarg with a default cannot break it."""
        c = CombatInstance(1, SkillRegistry(), cover_max=2)
        assert c.theatre == "ground"
        assert c.cover_max == 2
