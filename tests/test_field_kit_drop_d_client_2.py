"""Field Kit Drop D-client.2 — Declaration Panel.

Per `field_kit_design_decomposition_v2.md` §6 and the v34 §16F roadmap.
This sub-drop adds the action button row to the combat HUD:

  · F2  — DODGE / FULL DODGE rendered as separate buttons. Both dodge
          and fulldodge are real R&E mechanics with materially different
          consequences (reactive vs whole-round), so collapsing them
          loses player information.

  · F4  — `fullDefense` action removed from the client. It was never a
          parser command — the client used to ship a button that
          would dispatch a verb the server couldn't resolve. Documented
          comments referencing the removal are allowed (they help future
          readers); a usable button or quoted command string is not.

  · F6  — Theatre-conditional action sets: space (fire/dodge/fulldodge/
          evade/aim/flee/pass) vs ground (attack/dodge/fulldodge/parry/
          cover/move/aim/pass). The set switches based on the theatre
          field surfaced from CombatInstance.

The panel hides outside of declaration phase or after the viewer has
already declared (the existing `cs-actions-block` shows what was
declared; reshowing buttons would be confusing).

These are static-content + parser-availability tests. The full
PosingPanel surface lands in D-client.3.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"
COMBAT_COMMANDS_PY = ROOT / "parser" / "combat_commands.py"
SPACE_COMMANDS_PY = ROOT / "parser" / "space_commands.py"


@pytest.fixture(scope="module")
def client_html_text() -> str:
    assert CLIENT_HTML.exists(), f"missing {CLIENT_HTML}"
    return CLIENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def combat_commands_text() -> str:
    assert COMBAT_COMMANDS_PY.exists(), f"missing {COMBAT_COMMANDS_PY}"
    return COMBAT_COMMANDS_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def space_commands_text() -> str:
    assert SPACE_COMMANDS_PY.exists(), f"missing {SPACE_COMMANDS_PY}"
    return SPACE_COMMANDS_PY.read_text(encoding="utf-8")


# Helper — extract the RE_DECL_ACTIONS object literal and parse out
# the per-theatre command strings for cross-checks against the parser.
def _extract_action_cmds(client_html_text: str, theatre: str) -> set[str]:
    """Return the set of cmd strings under RE_DECL_ACTIONS[theatre].

    The naive pattern RE_DECL_ACTIONS\\s*=\\s*\\{[^}]*? trips on the
    nested action object literals. We find the theatre key directly,
    then read forward to the matching close-bracket of its array.
    """
    # Find the theatre key after a `RE_DECL_ACTIONS = {` opener.
    head = re.search(r'var\s+RE_DECL_ACTIONS\s*=', client_html_text)
    if not head:
        return set()
    tail = client_html_text[head.start():]
    key = re.search(rf'\b{re.escape(theatre)}\s*:\s*\[', tail)
    if not key:
        return set()
    body_start = key.end()
    # Read forward, matching brackets until the array closes.
    depth = 1
    i = body_start
    while i < len(tail) and depth > 0:
        ch = tail[i]
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = tail[body_start:i]
    return set(re.findall(r"cmd\s*:\s*'([^']+)'", body))


# ───────────────────────────────────────────────────────────────────────
# F2 — DODGE / FULL DODGE split
# ───────────────────────────────────────────────────────────────────────


class TestF2DodgeFullDodgeSplit:

    def test_both_dodge_and_fulldodge_in_space_action_set(
        self, client_html_text: str
    ):
        cmds = _extract_action_cmds(client_html_text, 'space')
        assert 'dodge' in cmds, (
            "space action set must include 'dodge' — F2 split"
        )
        assert 'fulldodge' in cmds, (
            "space action set must include 'fulldodge' — F2 split"
        )

    def test_both_dodge_and_fulldodge_in_ground_action_set(
        self, client_html_text: str
    ):
        cmds = _extract_action_cmds(client_html_text, 'ground')
        assert 'dodge' in cmds, (
            "ground action set must include 'dodge' — F2 split"
        )
        assert 'fulldodge' in cmds, (
            "ground action set must include 'fulldodge' — F2 split"
        )

    def test_full_dodge_button_label_distinct_from_dodge(
        self, client_html_text: str
    ):
        """Both buttons must render with distinguishable labels."""
        # The visible label for fulldodge is 'FULL DODGE' (with space)
        assert "label: 'FULL DODGE'" in client_html_text, (
            "FULL DODGE button label missing — F2 split"
        )
        # And plain DODGE must also be present as a separate label
        assert re.search(
            r"id:\s*'dodge'\s*,\s*label:\s*'DODGE'", client_html_text
        ), "DODGE button label missing — F2 split"

    def test_fulldodge_parser_command_exists(
        self, combat_commands_text: str
    ):
        """The client button is only useful if the parser accepts the
        verb. Guard the cross-tier contract."""
        assert 'class FullDodgeCommand' in combat_commands_text, (
            "FullDodgeCommand class missing in parser — F2 contract broken"
        )
        # And its key matches what the button sends
        m = re.search(
            r"class\s+FullDodgeCommand[^}]*?key\s*=\s*['\"]fulldodge['\"]",
            combat_commands_text,
            re.DOTALL,
        )
        assert m is not None, (
            "FullDodgeCommand.key must equal 'fulldodge' to match button cmd"
        )


# ───────────────────────────────────────────────────────────────────────
# F4 — fullDefense removed
# ───────────────────────────────────────────────────────────────────────


class TestF4FullDefenseRemoved:

    def test_no_full_defense_action_in_action_sets(
        self, client_html_text: str
    ):
        """The action sets must not contain a fullDefense command. Only
        flag actual usages — comments documenting the removal are OK."""
        # Look for it as a value of cmd: or id: — that's the failure mode.
        patterns = [
            r"cmd\s*:\s*['\"]fullDefense['\"]",
            r"cmd\s*:\s*['\"]fulldefense['\"]",
            r"cmd\s*:\s*['\"]full_defense['\"]",
            r"id\s*:\s*['\"]fullDefense['\"]",
            r"id\s*:\s*['\"]fulldefense['\"]",
            r"id\s*:\s*['\"]full_defense['\"]",
        ]
        for pat in patterns:
            assert not re.search(pat, client_html_text), (
                f"forbidden fullDefense reference matched {pat!r} — F4 violated"
            )

    def test_no_full_defense_button_label(
        self, client_html_text: str
    ):
        """A 'FULL DEFENSE' visible label would still mislead even if
        it's wired to dodge under the hood. F2 already named the
        canonical labels (DODGE / FULL DODGE)."""
        assert "FULL DEFENSE" not in client_html_text, (
            "'FULL DEFENSE' button label present — F4 violated"
        )

    def test_no_full_defense_parser_class(
        self, combat_commands_text: str
    ):
        """The parser must also have no FullDefense command — sanity
        check that the legacy verb didn't sneak in elsewhere."""
        assert 'class FullDefenseCommand' not in combat_commands_text, (
            "FullDefenseCommand class exists in parser — F4 violated"
        )


# ───────────────────────────────────────────────────────────────────────
# F6 — Theatre-conditional action sets
# ───────────────────────────────────────────────────────────────────────


class TestF6TheatreConditionalActions:

    def test_re_decl_actions_object_defined(self, client_html_text: str):
        assert 'var RE_DECL_ACTIONS' in client_html_text, (
            "RE_DECL_ACTIONS object must be defined — F6 action set source"
        )

    def test_space_action_set_complete(self, client_html_text: str):
        """Space declaration must offer fire/dodge/fulldodge/evade/aim/
        flee/pass per the prototype's space DeclarationPanel."""
        cmds = _extract_action_cmds(client_html_text, 'space')
        expected = {'fire', 'dodge', 'fulldodge', 'evade',
                    'aim', 'flee', 'pass'}
        missing = expected - cmds
        assert not missing, (
            f"space action set missing commands: {sorted(missing)}"
        )

    def test_ground_action_set_complete(self, client_html_text: str):
        """Ground declaration must offer attack/dodge/fulldodge/parry/
        cover/move/aim/pass per the prototype's GroundDeclarationPanel."""
        cmds = _extract_action_cmds(client_html_text, 'ground')
        expected = {'attack', 'dodge', 'fulldodge', 'parry',
                    'cover', 'move', 'aim', 'pass'}
        missing = expected - cmds
        assert not missing, (
            f"ground action set missing commands: {sorted(missing)}"
        )

    def test_render_function_picks_set_by_theatre(
        self, client_html_text: str
    ):
        """renderDeclarationPanel must select RE_DECL_ACTIONS[theatre]
        with a ground fallback. Without this, the theatre arg is ignored."""
        m = re.search(
            r"RE_DECL_ACTIONS\[\s*theatre\s*\]\s*\|\|\s*"
            r"RE_DECL_ACTIONS\.ground",
            client_html_text,
        )
        assert m is not None, (
            "renderDeclarationPanel must pick action set by theatre with "
            "a ground fallback — F6 routing regression"
        )

    def test_space_parser_commands_exist(
        self, space_commands_text: str, combat_commands_text: str
    ):
        """Every space action's cmd must map to a real parser command."""
        # FIRE — space_commands.py
        assert 'class FireCommand' in space_commands_text, (
            "FireCommand parser class missing — space FIRE button broken"
        )
        # EVADE — space_commands.py
        assert 'class EvadeCommand' in space_commands_text, (
            "EvadeCommand parser class missing — space EVADE button broken"
        )
        # dodge / fulldodge / aim / flee / pass — combat_commands.py
        for cls in ('DodgeCommand', 'FullDodgeCommand', 'AimCommand',
                    'FleeCommand', 'PassCommand'):
            assert f'class {cls}' in combat_commands_text, (
                f"{cls} parser class missing — space action button broken"
            )

    def test_ground_parser_commands_exist(
        self, combat_commands_text: str
    ):
        """Every ground action's cmd must map to a real parser command."""
        for cls in ('AttackCommand', 'DodgeCommand', 'FullDodgeCommand',
                    'ParryCommand', 'CoverCommand', 'AimCommand',
                    'PassCommand'):
            assert f'class {cls}' in combat_commands_text, (
                f"{cls} parser class missing — ground action button broken"
            )
        # MoveCommand lives in builtin_commands; verify separately
        builtin = (ROOT / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        assert 'class MoveCommand' in builtin, (
            "MoveCommand parser class missing — ground MOVE button broken"
        )


# ───────────────────────────────────────────────────────────────────────
# Render path — show/hide rules + DOM wiring
# ───────────────────────────────────────────────────────────────────────


class TestRenderPath:

    def test_combat_decl_panel_html_present(self, client_html_text: str):
        """The container the JS targets must exist in the static markup."""
        assert 'id="combat-decl-panel"' in client_html_text, (
            "combat-decl-panel container missing from HTML"
        )
        assert 'id="cdp-actions"' in client_html_text, (
            "cdp-actions populate target missing from HTML"
        )

    def test_panel_starts_hidden(self, client_html_text: str):
        """The panel ships hidden — only the JS render path should show
        it. Without this, players see action buttons before combat
        starts."""
        m = re.search(
            r'id="combat-decl-panel"[^>]*style="display:none;"',
            client_html_text,
        )
        assert m is not None, (
            "combat-decl-panel must default to display:none in static HTML"
        )

    def test_render_fn_hides_outside_declaration_phase(
        self, client_html_text: str
    ):
        """The render fn must hide the panel when phase !== 'declaration'."""
        m = re.search(
            r"function\s+renderDeclarationPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None, "renderDeclarationPanel function not found"
        body = m.group(1)
        assert "phase !== 'declaration'" in body, (
            "panel must hide outside of declaration phase"
        )
        assert "panel.style.display = 'none'" in body, (
            "panel.style.display must be set to 'none' for hide path"
        )

    def test_render_fn_hides_after_declaration(
        self, client_html_text: str
    ):
        """If viewer has declared, the cs-actions-block already shows
        their declared actions — the button row must hide so we don't
        offer a re-declare path the engine won't accept."""
        m = re.search(
            r"function\s+renderDeclarationPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        # The render fn checks data.your_actions length to decide if the
        # viewer has declared.
        assert 'your_actions' in body, (
            "render fn must consult your_actions to detect prior declaration"
        )

    def test_handle_combat_state_calls_render_decl_panel(
        self, client_html_text: str
    ):
        """The new render fn must be wired into handleCombatState."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'renderDeclarationPanel(' in body, (
            "handleCombatState must call renderDeclarationPanel"
        )

    def test_handle_combat_state_hides_panel_when_inactive(
        self, client_html_text: str
    ):
        """When combat ends, the declaration panel must be hidden so it
        doesn't linger when the strip itself is removed."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        # When data.active is false, look for the explicit hide on the
        # decl panel.
        # The branch starts with the !data.active check; we want a
        # display:none assignment somewhere in that early-return arm.
        early_return = body[: body.find("strip.classList.add('show')")]
        assert (
            'combat-decl-panel' in early_return
            and "style.display = 'none'" in early_return
        ), (
            "handleCombatState must explicitly hide the decl panel on "
            "the inactive-combat path"
        )

    def test_buttons_have_tone_classes(self, client_html_text: str):
        """Each button gets a .tone-{red,amber,green,dim} class so the
        CSS palette can apply. Without this, all buttons look identical."""
        m = re.search(
            r"function\s+renderDeclarationPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert "'cdp-btn tone-' + " in body, (
            "renderDeclarationPanel must compose the tone-* class from "
            "the action's tone field"
        )

    def test_send_vs_stage_dispatch(self, client_html_text: str):
        """Button click must dispatch via sendCmd (immediate fire) or
        stageCommand (target-required) based on action.kind. This is
        the difference between 'dodge' (no arg) and 'attack' (needs
        target)."""
        m = re.search(
            r"function\s+renderDeclarationPanel\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'sendCmd(' in body, (
            "renderDeclarationPanel must dispatch via sendCmd for kind=='send'"
        )
        assert 'stageCommand(' in body, (
            "renderDeclarationPanel must dispatch via stageCommand for "
            "kind=='stage'"
        )


# ───────────────────────────────────────────────────────────────────────
# CSS — tone palette + theatre-aware styling
# ───────────────────────────────────────────────────────────────────────


class TestCSS:

    def test_tone_classes_defined(self, client_html_text: str):
        """All four tones must have corresponding .cdp-btn.tone-* rules.
        The render path emits these classes; if the CSS is missing them,
        every button looks like the default."""
        for tone in ('red', 'amber', 'green', 'dim'):
            sel = f'.cdp-btn.tone-{tone}'
            assert sel in client_html_text, (
                f"CSS rule {sel!r} missing — button tone palette broken"
            )

    def test_panel_inherits_theatre_color(self, client_html_text: str):
        """The panel's top border must pick up the theatre tint so it
        visually belongs to the combat strip."""
        for theatre in ('space', 'ground'):
            sel = (
                f'.combat-strip[data-theatre="{theatre}"] '
                '.combat-decl-panel'
            )
            assert sel in client_html_text, (
                f"theatre-aware decl panel border for {theatre!r} missing"
            )


# ───────────────────────────────────────────────────────────────────────
# Regression — D-client.1 surface still intact
# ───────────────────────────────────────────────────────────────────────


class TestRegression:

    def test_drop_d_client_1_phase_pulse_intact(
        self, client_html_text: str
    ):
        """D-client.1's pulse machinery must still be in place."""
        assert '@keyframes fkpulse' in client_html_text
        assert "setAttribute('data-pulse'" in client_html_text

    def test_drop_d_client_1_theatre_attribute_intact(
        self, client_html_text: str
    ):
        """D-client.1's theatre wiring must still be in place."""
        assert "strip.setAttribute('data-theatre'" in client_html_text

    def test_drop_d_client_1_canonical_wound_ladder_intact(
        self, client_html_text: str
    ):
        """D-client.1's canonical ladder consumer must still be in place."""
        m = re.search(
            r"function\s+handleCombatState\s*\([^)]*\)\s*\{(.*?)^\}",
            client_html_text,
            re.DOTALL | re.MULTILINE,
        )
        assert m is not None
        body = m.group(1)
        assert 'woundRung(' in body
        assert 'woundColor(' in body
