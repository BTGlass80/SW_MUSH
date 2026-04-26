"""Field Kit Drop D-client.1 — Foundation.

Per `field_kit_design_decomposition_v2.md` §6 and the v34 §16F roadmap.
This sub-drop lands the foundation for the full combat HUD rebuild:

  · F1   — Canonical 7-rung wound ladder consumed by handleCombatState.
           Replaces the legacy 3-bucket healthy/hurt/bad classification
           that lost fidelity at WOUNDED ×2, INCAP, MORTAL, and DEAD.

  · F6   — Theatre-aware combat strip styling. The engine's
           combat_state.theatre field (delivered by D-prereq) now drives
           the strip's color palette via a data-theatre attribute, so a
           ground brawl in a starport stays datapad-amber even when the
           broader app surface is rendering space mode.

  · F14  — Phase-pill pulse + every-phase visual treatment. Initiative,
           declaration, and posing pulse to communicate "awaiting input";
           resolution and ended do not. All five engine phases now have
           a CSS class with explicit color (was: only declaration and
           resolution were styled).

These are static-content + payload-shape tests. The full PosingPanel
UX surface and the DODGE/FULL DODGE declaration buttons land in
D-client.2 and D-client.3 respectively.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"
COMBAT_PY = ROOT / "engine" / "combat.py"


@pytest.fixture(scope="module")
def client_html_text() -> str:
    assert CLIENT_HTML.exists(), f"missing {CLIENT_HTML}"
    return CLIENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def combat_py_text() -> str:
    assert COMBAT_PY.exists(), f"missing {COMBAT_PY}"
    return COMBAT_PY.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────────────
# Server payload contract — guards what the client now relies on
# ───────────────────────────────────────────────────────────────────────


class TestServerPayloadContract:
    """The client's render path now reads `data.theatre` to pick its
    palette. If the server stops emitting that field, every combat strip
    silently falls back to ground-amber. These tests are a regression
    boundary for the cross-tier contract."""

    def test_to_hud_dict_includes_theatre(self, combat_py_text: str):
        """to_hud_dict() must surface combat_state.theatre in the payload."""
        m = re.search(r'"theatre"\s*:\s*self\.theatre', combat_py_text)
        assert m is not None, (
            "engine/combat.py to_hud_dict() must include "
            '\'"theatre": self.theatre\' — Drop D-prereq regression'
        )

    def test_combat_instance_has_theatre_attribute(self, combat_py_text: str):
        """CombatInstance must store a theatre attribute (default 'ground')
        so to_hud_dict() can read it."""
        # Constructor accepts theatre kwarg with default
        m_ctor = re.search(
            r'theatre\s*:\s*str\s*=\s*[\'"]ground[\'"]', combat_py_text
        )
        assert m_ctor is not None, (
            "CombatInstance.__init__ must accept theatre: str = 'ground'"
        )
        # Attribute is stored
        m_set = re.search(r'self\.theatre\s*=\s*theatre', combat_py_text)
        assert m_set is not None, (
            "CombatInstance must store self.theatre = theatre"
        )


# ───────────────────────────────────────────────────────────────────────
# F1 — Canonical wound ladder consumed in handleCombatState
# ───────────────────────────────────────────────────────────────────────


class TestF1CanonicalWoundLadder:

    def test_handle_combat_state_calls_wound_rung(self, client_html_text: str):
        """handleCombatState must derive its wound label/color from
        woundRung(), not the legacy 3-bucket healthy/hurt/bad mapping."""
        # Find the handleCombatState body and assert woundRung is referenced
        # *inside* it (not just defined elsewhere in the file).
        m = re.search(
            r'function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}',
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None, "handleCombatState function not found"
        body = m.group(1)
        assert 'woundRung(' in body, (
            "handleCombatState must call woundRung() — F1 canonical ladder. "
            "If you see this fail, the render is back on the legacy 3-bucket "
            "wound classification which loses WOUNDED ×2/INCAP/MORTAL/DEAD."
        )

    def test_handle_combat_state_calls_wound_color(self, client_html_text: str):
        """handleCombatState must call woundColor(sev, theme) so the pip
        color comes from the canonical severity → theme palette mapping."""
        m = re.search(
            r'function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}',
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'woundColor(' in body, (
            "handleCombatState must call woundColor() — F1 canonical palette"
        )

    def test_legacy_three_bucket_classification_removed(
        self, client_html_text: str
    ):
        """The render path must NOT add the legacy .healthy/.hurt/.bad
        modifier classes any more. The old conditional
        'c.wound_level === 0 ? healthy : c.wound_level <= 2 ? hurt : bad'
        is the canary; if it returns, the canonical ladder is masked."""
        # The legacy ternary used three exact tokens together.
        legacy = re.search(
            r"'healthy'.*?'hurt'.*?'bad'",
            client_html_text,
            re.DOTALL,
        )
        assert legacy is None, (
            "legacy three-bucket healthy/hurt/bad ternary is back — "
            "F1 canonical ladder is being masked"
        )

    def test_canonical_wound_ladder_definition_present(
        self, client_html_text: str
    ):
        """WOUND_RUNGS must still define all 7 levels (Drop A regression)."""
        # Just verify it exists — Drop A's own tests cover the 7-rung shape.
        assert 'var WOUND_RUNGS' in client_html_text, (
            "WOUND_RUNGS array missing — Drop A regression"
        )
        # And the rung labels we depend on are still there.
        for label in ('HEALTHY', 'STUNNED', 'WOUNDED', 'INCAP',
                      'MORTAL', 'DEAD'):
            assert label in client_html_text, (
                f"WOUND_RUNGS label {label!r} missing — Drop A regression"
            )


# ───────────────────────────────────────────────────────────────────────
# F6 — Theatre-aware combat strip
# ───────────────────────────────────────────────────────────────────────


class TestF6TheatreAwareStrip:

    def test_combat_strip_sets_data_theatre_attribute(
        self, client_html_text: str
    ):
        """handleCombatState must call strip.setAttribute('data-theatre', ...)
        based on data.theatre. Without this, every combat strip styles
        identically regardless of theatre."""
        m = re.search(
            r"strip\.setAttribute\(\s*['\"]data-theatre['\"]",
            client_html_text,
        )
        assert m is not None, (
            "handleCombatState must set data-theatre on the combat-strip — "
            "F6 theatre-aware tinting regression"
        )

    def test_combat_strip_clears_data_theatre_when_inactive(
        self, client_html_text: str
    ):
        """When combat ends, the strip must shed the data-theatre attr
        so the next combat picks up its own theatre cleanly."""
        m = re.search(
            r"strip\.removeAttribute\(\s*['\"]data-theatre['\"]",
            client_html_text,
        )
        assert m is not None, (
            "handleCombatState must clear data-theatre when combat is "
            "inactive — F6 theatre-aware tinting regression"
        )

    def test_data_theatre_default_is_ground(self, client_html_text: str):
        """If data.theatre is missing or unrecognized, the client must
        default to 'ground' (matching the engine's CombatInstance default).
        Without a default, a missing field leaves the strip un-tinted."""
        # Find the theatre-derivation line and assert ground is the fallback.
        m = re.search(
            r"theatre\s*=\s*\(data\.theatre\s*===\s*['\"]space['\"]\)\s*"
            r"\?\s*['\"]space['\"]\s*:\s*['\"]ground['\"]",
            client_html_text,
        )
        assert m is not None, (
            "client.html must derive theatre with 'ground' fallback — "
            "default mismatch with engine CombatInstance"
        )

    def test_css_defines_theatre_overrides(self, client_html_text: str):
        """CSS must define both data-theatre selectors so the attribute
        actually changes the visual treatment."""
        for theatre in ('space', 'ground'):
            sel = f'.combat-strip[data-theatre="{theatre}"]'
            assert sel in client_html_text, (
                f'CSS selector {sel!r} missing — F6 styling cannot apply'
            )


# ───────────────────────────────────────────────────────────────────────
# F14 prereq — Phase pill pulse + per-phase visual treatment
# ───────────────────────────────────────────────────────────────────────


class TestF14PhasePillPulse:

    def test_fkpulse_keyframes_defined(self, client_html_text: str):
        """The pulse animation used by the phase pill must be defined."""
        assert '@keyframes fkpulse' in client_html_text, (
            "@keyframes fkpulse missing — phase pulse will not animate"
        )

    def test_data_pulse_attribute_drives_animation(
        self, client_html_text: str
    ):
        """CSS must wire data-pulse='1' to the fkpulse animation."""
        m = re.search(
            r'\.ch-phase\[data-pulse="1"\][^{]*\{[^}]*animation:\s*fkpulse',
            client_html_text,
        )
        assert m is not None, (
            ".ch-phase[data-pulse=\"1\"] selector must apply fkpulse animation"
        )

    def test_handle_combat_state_sets_data_pulse_for_active_phases(
        self, client_html_text: str
    ):
        """Initiative, declaration, and posing must pulse; resolution and
        ended must not. The test asserts the pulse-set logic exists."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        # Active-phase pulse trio
        assert "phase === 'initiative'" in body, (
            "initiative phase must be in the pulse trio"
        )
        assert "phase === 'declaration'" in body, (
            "declaration phase must be in the pulse trio"
        )
        assert "phase === 'posing'" in body, (
            "posing phase must be in the pulse trio"
        )
        # And the pulse attribute is actually set
        assert "setAttribute('data-pulse'" in body, (
            "handleCombatState must set data-pulse attribute"
        )

    def test_all_engine_phases_have_css_class(self, client_html_text: str):
        """Every engine phase must have a .ch-phase.<phase> CSS rule.
        Before D-client.1 only declaration and resolution were styled;
        initiative/posing/ended fell through to the default color, which
        made phase changes hard to read at a glance."""
        for phase in ('declaration', 'resolution',
                      'initiative', 'posing', 'ended'):
            sel = f'.ch-phase.{phase}'
            assert sel in client_html_text, (
                f"CSS selector {sel!r} missing — phase {phase} has no "
                f"distinct visual treatment"
            )


# ───────────────────────────────────────────────────────────────────────
# Regression — adjacent surfaces still compile
# ───────────────────────────────────────────────────────────────────────


class TestRegression:

    def test_handle_combat_state_still_renders_pose_deadline(
        self, client_html_text: str
    ):
        """The pre-existing pose_deadline countdown must still fire.
        D-client.1 doesn't change this behavior, but the rebuild touched
        adjacent code so we assert the countdown still wires up."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'pose_deadline' in body, (
            "pose_deadline countdown must still be rendered"
        )
        assert 'TO POSE' in body, (
            "TO POSE label must still render in countdown"
        )

    def test_handle_combat_state_still_renders_waiting_block(
        self, client_html_text: str
    ):
        """waiting_for block must still render."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert "waiting_for" in body, (
            "waiting_for block must still render"
        )

    def test_drop_a_primitives_still_exported(self, client_html_text: str):
        """woundRung / woundColor / WOUND_RUNGS exported on window so the
        debug console (and any future module that needs them) can reach
        them. Drop A regression."""
        for sym in ('window.WOUND_RUNGS', 'window.woundRung',
                    'window.woundColor'):
            assert sym in client_html_text, (
                f"{sym} export missing — Drop A regression"
            )
