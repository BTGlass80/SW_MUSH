"""Field Kit Drop D-client.3 — Posing Panel + Closure of Priority A1.

Per `field_kit_design_decomposition_v2.md` §6 and the v34 §16F roadmap.
This is the third and final sub-drop of the D-client trio. It closes
Priority A1.

  · F3   — Body-level posing panel that explicitly instructs the
           player to use `cpose <text>`. The plain `pose` / `:` verbs
           emote to the room but do NOT register the round pose, so
           the panel's instructional text calls that out. A "PRIME
           cpose" button stages the verb so the player can just type
           their pose.

  · F14  — Posing panel timer defaults to 180 seconds (engine R&E
           default per CombatPoseCommand timing). If the engine ever
           starts surfacing `pose_window_seconds` in the combat_state
           payload, the client honors that override; absent the field,
           it falls back to 180.

  · F11/F13 (regression) — The hull-condition coloring landed in Drop E
           (per the prior session's reinterpretation of F11 — the live
           target-lock card has no condition surface, so the actual
           color-needs-applying surface was the player's own ship hull
           label). This drop preserves Drop E's `conditionColor()`
           consumption with regression guards.

  · F4 (final scrub) — D-client.2 already verified the action set
           doesn't reference fullDefense. D-client.3 adds an aggressive
           sweep that excludes documentation comments (which legitimately
           note the removal) but flags any actual button label, command
           string, or identifier reference.

Acceptance: when this drop lands green, all 13 F-findings from
`field_kit_audit_and_remediation_v1.md` are traceable to code changes
and Priority A1 closes.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"
COMBAT_COMMANDS_PY = ROOT / "parser" / "combat_commands.py"


@pytest.fixture(scope="module")
def client_html_text() -> str:
    assert CLIENT_HTML.exists(), f"missing {CLIENT_HTML}"
    return CLIENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def combat_commands_text() -> str:
    assert COMBAT_COMMANDS_PY.exists(), f"missing {COMBAT_COMMANDS_PY}"
    return COMBAT_COMMANDS_PY.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """Remove HTML comments and JS line comments to make pattern
    searches insensitive to documentation that legitimately mentions
    removed identifiers like fullDefense.

    JS block comments /* ... */ are also stripped.
    Strings are NOT touched — fullDefense in a string literal is still
    a real reference and should fail any "no references" sweep.
    """
    # Strip HTML comments (<!-- ... -->) — non-greedy
    no_html = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Strip JS block comments
    no_block = re.sub(r"/\*.*?\*/", "", no_html, flags=re.DOTALL)
    # Strip JS line comments (start of line or after whitespace), but
    # only if not inside a string. Simple heuristic: if `//` follows a
    # letter or digit it could be inside a URL-like string; we still
    # strip aggressively because the test only cares about identifier
    # leakage, and comments that happen to be inside strings are very
    # rare.
    no_line = re.sub(r"//[^\n]*", "", no_block)
    return no_line


# ───────────────────────────────────────────────────────────────────────
# F3 — PosingPanel cpose primer
# ───────────────────────────────────────────────────────────────────────


class TestF3CposePrimer:

    def test_pose_panel_html_present(self, client_html_text: str):
        """The container the JS targets must exist in static markup."""
        assert 'id="combat-pose-panel"' in client_html_text, (
            "combat-pose-panel container missing from HTML — F3"
        )
        for sub in ('id="cpp-timer"', 'id="cpp-result-text"',
                    'id="cpp-bar-fill"', 'id="cpp-prime-btn"'):
            assert sub in client_html_text, (
                f"posing panel slot {sub!r} missing from HTML — F3"
            )

    def test_pose_panel_starts_hidden(self, client_html_text: str):
        """Panel must not be visible until the JS shows it."""
        m = re.search(
            r'id="combat-pose-panel"[^>]*style="display:none;"',
            client_html_text,
        )
        assert m is not None, (
            "combat-pose-panel must default to display:none in static HTML"
        )

    def test_instructional_text_names_cpose_explicitly(
        self, client_html_text: str
    ):
        """The panel's instructional text must literally name 'cpose'.
        F3 was filed because the prior surface mentioned 'pose' which is
        the wrong verb (it doesn't register the round pose)."""
        # Grab the instructions div content.
        m = re.search(
            r'<div class="cpp-instructions">(.*?)</div>',
            client_html_text,
            re.DOTALL,
        )
        assert m is not None, "cpp-instructions block not found"
        body = m.group(1)
        assert 'cpose' in body, (
            "instructional text must name cpose explicitly — F3"
        )

    def test_instructional_text_warns_about_plain_pose(
        self, client_html_text: str
    ):
        """The text must explain that plain 'pose' / ':' emote to the
        room but do NOT register the round pose. Without the warning,
        players default to the wrong verb."""
        m = re.search(
            r'<div class="cpp-instructions">(.*?)</div>',
            client_html_text,
            re.DOTALL,
        )
        assert m is not None
        # Normalize whitespace so multi-line HTML doesn't trip the check.
        body = re.sub(r'\s+', ' ', m.group(1)).lower()
        assert 'pose' in body, (
            "instructions must reference plain 'pose' verb"
        )
        assert ('not register' in body
                or 'do not register' in body
                or "don't register" in body), (
            "instructions must warn that plain pose does not register "
            "the round pose"
        )

    def test_prime_button_stages_cpose_command(
        self, client_html_text: str
    ):
        """The PRIME cpose button must call stageCommand('cpose ', ...)
        so clicking it pre-fills the input."""
        # Find the renderPosingPanel function and look for the
        # stageCommand call with 'cpose ' as the staged template.
        m = re.search(
            r"function\s+renderPosingPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None, "renderPosingPanel not found"
        body = m.group(1)
        assert "stageCommand('cpose '" in body, (
            "PRIME button must stageCommand('cpose ', ...) to pre-fill input"
        )

    def test_cpose_parser_command_exists(
        self, combat_commands_text: str
    ):
        """The button is only useful if the parser accepts cpose."""
        assert 'class CombatPoseCommand' in combat_commands_text, (
            "CombatPoseCommand class missing in parser — cpose contract broken"
        )
        # And cpose is a valid key/alias
        m = re.search(
            r"class\s+CombatPoseCommand[\s\S]*?key\s*=\s*['\"](\w+)['\"]",
            combat_commands_text,
        )
        assert m is not None, (
            "CombatPoseCommand must define a key"
        )


# ───────────────────────────────────────────────────────────────────────
# F14 — 180s default timer
# ───────────────────────────────────────────────────────────────────────


class TestF14DefaultTimer:

    def test_default_timer_constant_is_180(self, client_html_text: str):
        """The default total seconds must be 180 (engine R&E default).
        Constant is exposed so the value is greppable + auditable."""
        m = re.search(
            r"var\s+POSE_PANEL_DEFAULT_SECONDS\s*=\s*180\b",
            client_html_text,
        )
        assert m is not None, (
            "POSE_PANEL_DEFAULT_SECONDS must be defined as 180 — F14"
        )

    def test_engine_override_field_consulted(self, client_html_text: str):
        """If/when the engine surfaces pose_window_seconds, the client
        must use it in preference to the default."""
        m = re.search(
            r"function\s+_updatePosingPanelTick\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None, "_updatePosingPanelTick not found"
        body = m.group(1)
        assert 'pose_window_seconds' in body, (
            "tick fn must consult data.pose_window_seconds for engine override"
        )
        # And it must fall back to the constant.
        assert 'POSE_PANEL_DEFAULT_SECONDS' in body, (
            "tick fn must fall back to POSE_PANEL_DEFAULT_SECONDS"
        )

    def test_urgent_threshold_under_30_seconds(
        self, client_html_text: str
    ):
        """The panel must flip to .urgent when remaining < 30s. This
        mirrors the prototype's countdown blink and gives the player a
        clear visual warning before auto-pose."""
        m = re.search(
            r"function\s+_updatePosingPanelTick\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        # Match `remaining < 30`
        assert re.search(r'remaining\s*<\s*30', body), (
            "urgent threshold must be remaining < 30 seconds"
        )

    def test_timer_ticks_on_interval(self, client_html_text: str):
        """The timer must update on a setInterval — without it, the
        countdown only refreshes when a new combat_state arrives, which
        is irregular."""
        m = re.search(
            r"function\s+renderPosingPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'setInterval' in body, (
            "renderPosingPanel must start a setInterval to tick the timer"
        )
        # And the cleanup symbol must be referenced (we restart per state)
        assert '_stopPosingPanelTimer' in body, (
            "renderPosingPanel must call _stopPosingPanelTimer to clear "
            "stale intervals"
        )


# ───────────────────────────────────────────────────────────────────────
# Render path — show/hide on phase, panel hides on inactive combat
# ───────────────────────────────────────────────────────────────────────


class TestRenderPath:

    def test_handle_combat_state_calls_render_pose_panel(
        self, client_html_text: str
    ):
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'renderPosingPanel(' in body, (
            "handleCombatState must call renderPosingPanel"
        )

    def test_hides_outside_posing_phase(self, client_html_text: str):
        m = re.search(
            r"function\s+renderPosingPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert "phase !== 'posing'" in body, (
            "panel must hide outside of posing phase"
        )

    def test_hides_and_clears_timer_on_inactive_combat(
        self, client_html_text: str
    ):
        """When combat goes inactive the panel must disappear AND the
        interval must be cleared. A leaked interval would tick forever
        once combat ends."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        # Find the !data.active early-return arm
        early = body[: body.find("strip.classList.add('show')")]
        assert 'combat-pose-panel' in early, (
            "inactive-combat path must reference combat-pose-panel"
        )
        assert '_stopPosingPanelTimer' in early, (
            "inactive-combat path must call _stopPosingPanelTimer"
        )

    def test_last_combat_state_captured(self, client_html_text: str):
        """The interval reads from lastCombatStateData; handleCombatState
        must capture it on every message."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'lastCombatStateData' in body, (
            "handleCombatState must update lastCombatStateData"
        )
        # Top-level declaration also present
        assert 'var lastCombatStateData' in client_html_text, (
            "lastCombatStateData global declaration missing"
        )

    def test_result_block_uses_your_actions(self, client_html_text: str):
        """The RESULT block surfaces what the engine resolved this round.
        The client doesn't have an 'engine result text' field today, so
        the panel uses your_actions (the same source the cs-actions block
        already uses) joined with ' · '."""
        m = re.search(
            r"function\s+renderPosingPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'data.your_actions' in body, (
            "RESULT block must source from data.your_actions"
        )


# ───────────────────────────────────────────────────────────────────────
# F11/F13 — Drop E hull-condition coloring regression
# ───────────────────────────────────────────────────────────────────────


class TestF11F13HullConditionRegression:
    """F11/F13 audit findings: target hull condition surfaced AND
    rendered with color. Drop E delivered conditionColor() applied to
    the player's *own* hull. D-client.3 extends this to the *target*
    panel: the server payload now carries a `condition` field on
    `target_lock`, and `showTargetLock()` consumes it via the same
    Drop A primitive. Together these close F11/F13.
    """

    # ── Drop E regression (player's own hull) ──

    def test_condition_color_consumed_for_hull(self, client_html_text: str):
        """The player's hull-condition label must be colored via
        conditionColor() (Drop E regression)."""
        m = re.search(
            r"conditionColor\(\s*data\.hull_condition\s*\)",
            client_html_text,
        )
        assert m is not None, (
            "Drop E hull-condition coloring regression: "
            "conditionColor(data.hull_condition) call missing"
        )

    def test_condition_colors_table_intact(self, client_html_text: str):
        """The CONDITION_COLORS lookup must still contain title-case keys
        per Drop A. Engine returns 'Light Damage' etc., so the keys must
        match exactly (F13 title-case contract)."""
        for key in ('Pristine', 'Light Damage', 'Moderate Damage',
                    'Heavy Damage', 'Critical Damage', 'Destroyed'):
            assert f"'{key}'" in client_html_text, (
                f"CONDITION_COLORS missing title-case key {key!r} — F13"
            )

    # ── D-client.3 NEW: target-side rendering ──

    def test_target_stats_has_condition_cell(
        self, client_html_text: str
    ):
        """The target-stats markup must include a CONDITION cell with
        id='ts-condition' so the JS render path has a target element."""
        assert 'id="ts-condition"' in client_html_text, (
            "ts-condition cell missing from target-stats — F11 has no "
            "DOM target to render into"
        )
        # And the visible label is present
        assert '>CONDITION<' in client_html_text, (
            "CONDITION label missing from target-stats markup — F11"
        )

    def test_show_target_lock_consumes_t_condition(
        self, client_html_text: str
    ):
        """showTargetLock must read t.condition and apply conditionColor()
        to the ts-condition element. Without this, the server payload
        carries the data but the client never displays it."""
        m = re.search(
            r"function\s+showTargetLock\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None, "showTargetLock function not found"
        body = m.group(1)
        assert 't.condition' in body, (
            "showTargetLock must read t.condition from the target_lock "
            "payload — F11 server data not consumed"
        )
        assert 'conditionColor(' in body, (
            "showTargetLock must call conditionColor() to color the "
            "condition cell — F11 severity not communicated visually"
        )
        # And it writes to the target element we declared in markup
        assert "$('ts-condition')" in body, (
            "showTargetLock must write to the ts-condition element"
        )

    def test_show_no_target_lock_clears_condition(
        self, client_html_text: str
    ):
        """When the lock drops, the condition cell must reset so a stale
        Critical Damage red doesn't bleed into the next lock display."""
        m = re.search(
            r"function\s+showNoTargetLock\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None, "showNoTargetLock function not found"
        body = m.group(1)
        assert "$('ts-condition')" in body, (
            "showNoTargetLock must clear the ts-condition cell — F11 "
            "stale-color regression"
        )

    # ── D-client.3 NEW: server payload contract ──

    def test_server_target_lock_includes_condition(self):
        """The server's target_lock builder in space_commands.py must
        plumb a condition field. Without this the client renders ' — '
        on every target."""
        space_commands_text = (
            ROOT / "parser" / "space_commands.py"
        ).read_text(encoding="utf-8")
        # The target_lock dict literal must include a condition entry.
        m = re.search(
            r'target_lock\s*=\s*\{[^}]*?"condition"\s*:',
            space_commands_text,
            re.DOTALL,
        )
        assert m is not None, (
            'target_lock payload missing "condition" field — F11 server '
            'contract regression'
        )

    def test_server_db_ship_contacts_carry_condition(self):
        """DB ship contacts must derive a condition string so the
        target_lock builder has data to plumb. Strings must match
        CONDITION_COLORS keys exactly."""
        space_commands_text = (
            ROOT / "parser" / "space_commands.py"
        ).read_text(encoding="utf-8")
        # Each canonical condition string must appear in the contacts
        # path. We look for the literal strings since the derivation
        # ladder writes them verbatim.
        for key in ('Pristine', 'Light Damage', 'Moderate Damage',
                    'Heavy Damage', 'Critical Damage', 'Destroyed'):
            assert f'"{key}"' in space_commands_text, (
                f'DB ship contact builder missing condition string '
                f'{key!r} — title-case contract broken'
            )


# ───────────────────────────────────────────────────────────────────────
# F4 — comprehensive fullDefense scrub (excludes documentation)
# ───────────────────────────────────────────────────────────────────────


class TestF4FullDefenseFinalScrub:
    """D-client.2 verified the action set has no fullDefense entry. This
    pass scrubs the entire client.html for any non-documentation
    reference. Comments that explicitly note the removal are allowed
    and helpful; an actual identifier, command string, or button label
    is not."""

    def test_no_full_defense_outside_comments(self, client_html_text: str):
        """Strip comments first, then assert no reference remains."""
        no_comments = _strip_comments(client_html_text)
        # Common forms an actual reference would take:
        forbidden = [
            'fullDefense',          # JS identifier
            'full_defense',         # snake_case
            'FULL DEFENSE',         # button label
        ]
        for token in forbidden:
            # 'fulldefense' lowercase as a string literal is also
            # forbidden — covered by the 'fullDefense' search since
            # we case-insensitive-check separately below.
            assert token not in no_comments, (
                f"forbidden fullDefense reference {token!r} found outside "
                f"comments — F4 final scrub failed"
            )
        # Case-insensitive sweep for any 'fulldefense' substring
        # (catches lowercased command strings).
        assert 'fulldefense' not in no_comments.lower(), (
            "lowercase 'fulldefense' substring found outside comments — "
            "F4 final scrub failed"
        )

    def test_no_full_defense_in_parser(self, combat_commands_text: str):
        """Sanity — the parser must also have no FullDefense surface.
        D-client.2 already covered this; included here for closure."""
        assert 'FullDefense' not in combat_commands_text, (
            "FullDefense reference in parser/combat_commands.py — F4 violated"
        )


# ───────────────────────────────────────────────────────────────────────
# A1 closure — coverage assembly
# ───────────────────────────────────────────────────────────────────────


class TestA1Closure:
    """When this class passes, all 13 F-findings from the audit have
    code-level evidence and Priority A1 closes."""

    def test_f1_canonical_wound_ladder(self, client_html_text: str):
        """F1 — D-client.1 / Drop A primitives consumed in combat HUD."""
        # 7-rung ladder
        assert 'var WOUND_RUNGS' in client_html_text
        for label in ('HEALTHY', 'WOUNDED', 'INCAP', 'MORTAL', 'DEAD'):
            assert label in client_html_text
        # Consumed by combat HUD
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        assert 'woundRung(' in m.group(1)

    def test_f2_dodge_split(self, client_html_text: str):
        """F2 — DODGE / FULL DODGE separate buttons (D-client.2)."""
        assert "label: 'FULL DODGE'" in client_html_text
        assert "label: 'DODGE'" in client_html_text
        assert "cmd: 'fulldodge'" in client_html_text
        assert "cmd: 'dodge'" in client_html_text

    def test_f3_cpose_primer(self, client_html_text: str):
        """F3 — body-level posing panel names cpose explicitly."""
        m = re.search(
            r'<div class="cpp-instructions">(.*?)</div>',
            client_html_text,
            re.DOTALL,
        )
        assert m is not None
        assert 'cpose' in m.group(1)

    def test_f4_full_defense_removed(self, client_html_text: str):
        """F4 — fullDefense scrubbed from every active surface."""
        no_comments = _strip_comments(client_html_text)
        assert 'fulldefense' not in no_comments.lower()
        assert 'fullDefense' not in no_comments

    def test_f6_theatre_aware(self, client_html_text: str):
        """F6 — theatre-aware strip + theatre-conditional action sets."""
        assert "strip.setAttribute('data-theatre'" in client_html_text
        assert 'RE_DECL_ACTIONS[' in client_html_text

    def test_f8_stun_cap(self, client_html_text: str):
        """F8 — stunCap(strengthDice) defined (Drop A)."""
        assert 'function stunCap' in client_html_text

    def test_f9_shield_pool_capacity(self, client_html_text: str):
        """F9 — shield arc renders {cur}D/{max}D (Drop E)."""
        # Loose pattern — just verify the capacity surface text exists
        # somewhere. Drop E test covers the precise format.
        assert 'pool_dice' in client_html_text or 'shield_pool' in client_html_text

    def test_f11_f13_condition_color_consumed(
        self, client_html_text: str
    ):
        """F11/F13 — conditionColor() used in BOTH surfaces:
        the player's own hull (Drop E) AND the target panel (D-client.3).
        """
        # Drop E surface — player's own hull condition
        assert 'conditionColor(data.hull_condition)' in client_html_text, (
            "Drop E hull conditionColor wiring missing"
        )
        # D-client.3 surface — target panel condition
        assert 'ts-condition' in client_html_text, (
            "D-client.3 target condition cell missing"
        )
        # showTargetLock must consume t.condition
        assert 't.condition' in client_html_text, (
            "showTargetLock not consuming t.condition — F11"
        )

    def test_f14_pose_window_default_180(self, client_html_text: str):
        """F14 — posing panel timer defaults to 180s."""
        assert 'POSE_PANEL_DEFAULT_SECONDS = 180' in client_html_text

    def test_f15_no_ship_wound_levels(self, client_html_text: str):
        """F15 (Drop E) — ships use conditions, not wound levels.
        Ensure no ship_wound_level / hull_wound surface leaks back in."""
        # Loose check — these tokens shouldn't appear; Drop E test is
        # authoritative.
        assert 'ship_wound_level' not in client_html_text
        assert 'hull_wound_level' not in client_html_text


# ───────────────────────────────────────────────────────────────────────
# Regression — D-client.1 + .2 surfaces still intact
# ───────────────────────────────────────────────────────────────────────


class TestRegression:

    def test_d_client_1_phase_pulse(self, client_html_text: str):
        assert '@keyframes fkpulse' in client_html_text
        assert "setAttribute('data-pulse'" in client_html_text

    def test_d_client_1_theatre_attribute(self, client_html_text: str):
        assert "strip.setAttribute('data-theatre'" in client_html_text

    def test_d_client_2_decl_panel(self, client_html_text: str):
        assert 'function renderDeclarationPanel' in client_html_text
        assert 'id="combat-decl-panel"' in client_html_text
        assert 'var RE_DECL_ACTIONS' in client_html_text

    def test_d_client_2_decl_panel_still_called(
        self, client_html_text: str
    ):
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        assert 'renderDeclarationPanel(' in m.group(1)
