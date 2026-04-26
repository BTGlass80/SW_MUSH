"""Field Kit Drop E — Space Cockpit.

Per `field_kit_design_decomposition_v2.md` §7. Three F-findings covered:

  · F9   — shield-pool capacity is exposed by the server payload AND the
           client renders {cur}D/{max}D per arc (was {cur}D only). The
           "hardcoded 3" the prototype flagged was a v1 client bug — the
           live client never had it, but it also never surfaced capacity
           to the player. Drop E closes that gap with a static client
           change + payload field.

  · F11  — target/hull condition rendered with a color matching
  · F13     CONDITION_COLORS lookup (Drop A primitives). Drop A's
           conditionColor() is now consumed by the player's own ship
           hull-condition label so severity is communicated at a glance.

  · F15  — no references to ship "wound levels" anywhere in client.html
           (ships use conditions, not wound levels — Star Warriors p17).

These are static-content + payload-shape tests. Behavior tests for
the cockpit's full render path live in higher-level integration tests.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CLIENT_HTML = ROOT / "static" / "client.html"
SPACE_COMMANDS_PY = ROOT / "parser" / "space_commands.py"


@pytest.fixture(scope="module")
def client_html_text() -> str:
    assert CLIENT_HTML.exists(), f"missing {CLIENT_HTML}"
    return CLIENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def space_commands_text() -> str:
    assert SPACE_COMMANDS_PY.exists(), f"missing {SPACE_COMMANDS_PY}"
    return SPACE_COMMANDS_PY.read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────────────────
# F9 — Shield pool capacity (server + client)
# ───────────────────────────────────────────────────────────────────────


class TestF9ShieldPoolCapacity:

    def test_server_payload_exposes_pool_dice(self, space_commands_text: str):
        """build_space_state must include shield_arcs.pool_dice so the
        client can render {cur}D/{max}D. If this regresses, every shield
        cell silently drops back to {cur}D and players lose capacity
        visibility."""
        # Find the shield_arcs dict literal and assert pool_dice is in it.
        assert '"pool_dice"' in space_commands_text, (
            "shield_arcs payload missing pool_dice field — F9 regression"
        )

    def test_server_payload_exposes_pool_pips(self, space_commands_text: str):
        """Pips must also be surfaced — starfighter shields like 1D+2 are
        common and the cur/max display loses fidelity if pips are dropped."""
        assert '"pool_pips"' in space_commands_text, (
            "shield_arcs payload missing pool_pips field — F9 regression"
        )

    def test_pool_dice_uses_shield_pool_value(self, space_commands_text: str):
        """The pool_dice value must be sourced from shield_pool.dice
        (the parsed total ship shield DicePool), not a hardcoded number."""
        m = re.search(
            r'"pool_dice":\s*shield_pool\.dice', space_commands_text
        )
        assert m is not None, (
            "pool_dice must derive from shield_pool.dice, not a literal"
        )

    def test_client_setshield_signature_accepts_pool_max(
        self, client_html_text: str
    ):
        """setShield's signature must take a poolMax/max parameter, not
        just (id, val). Three accepted parameter names for forward-compat:
        poolMax, max, capacity."""
        m = re.search(
            r'function\s+setShield\s*\(\s*id\s*,\s*val\s*,\s*'
            r'(poolMax|max|capacity)\s*\)',
            client_html_text,
        )
        assert m is not None, (
            "setShield must accept a third param for shield-pool capacity"
        )

    def test_client_setshield_renders_cur_over_max(
        self, client_html_text: str
    ):
        """When pool capacity is provided, render must include the
        '{N}D/{M}D' format. The literal 'D/' substring inside the
        textContent assignment is the marker."""
        # Look for 'D/' inside the setShield function body. That's not a
        # CSS selector or comment — it's the rendered text.
        # Extract the function body (best-effort, between function header
        # and the next top-level function or end of file segment).
        idx = client_html_text.find("function setShield")
        assert idx >= 0
        # Search a bounded region after the function start for the format.
        body = client_html_text[idx:idx + 1500]
        assert "'D/'" in body or '"D/"' in body or "+ 'D/' +" in body, (
            "setShield doesn't render {cur}D/{max}D format — F9 regression"
        )

    def test_client_call_sites_pass_pool_max(self, client_html_text: str):
        """Every setShield call site must pass the third argument
        (pool_dice from shield_arcs). If any call drops back to the
        2-arg form, that arc loses capacity display."""
        # Fore/aft/port/stbd should each call setShield with 3 args.
        # Pattern: setShield('id', data.shield_arcs.X, ...third_arg)
        pattern = re.compile(
            r"setShield\(\s*'s-shield-(?:fore|aft|port|stbd)'\s*,\s*"
            r"data\.shield_arcs\.\w+\s*,\s*\w+",
            re.MULTILINE,
        )
        matches = pattern.findall(client_html_text)
        assert len(matches) >= 4, (
            f"expected >= 4 setShield calls with pool capacity arg, "
            f"got {len(matches)} — F9 regression"
        )


# ───────────────────────────────────────────────────────────────────────
# F11 / F13 — Hull condition rendered with color
# ───────────────────────────────────────────────────────────────────────


class TestF11F13HullConditionColor:

    def test_conditioncolor_consumed_for_hull_cond(
        self, client_html_text: str
    ):
        """The hull-condition rendering block must invoke conditionColor()
        on the data.hull_condition value. Bare textContent assignment
        without color application is the regression case."""
        idx = client_html_text.find("'s-hull-cond'")
        assert idx >= 0, "s-hull-cond render site not found"
        # Look in a bounded window around the assignment site.
        # The conditionColor() call should appear within ~600 chars.
        # (The block contains the textContent + the color application.)
        window = client_html_text[max(0, idx - 100):idx + 800]
        assert "conditionColor(" in window, (
            "hull-condition not colored via conditionColor() — F11/F13 regression"
        )

    def test_color_applied_via_inline_style(self, client_html_text: str):
        """Apply color via .style.color rather than rebuilding CSS classes
        per condition (cheaper, theme-friendly, doesn't fight existing
        .hull-condition CSS)."""
        idx = client_html_text.find("'s-hull-cond'")
        window = client_html_text[max(0, idx - 100):idx + 800]
        assert ".style.color" in window, (
            "hull-condition color must be applied inline (.style.color)"
        )

    def test_text_shadow_paired_with_color(self, client_html_text: str):
        """A subtle text-shadow paired with the color matches the
        prototype's emphasis treatment for severity."""
        idx = client_html_text.find("'s-hull-cond'")
        window = client_html_text[max(0, idx - 100):idx + 800]
        assert "textShadow" in window, (
            "hull-condition should pair color with textShadow for emphasis"
        )

    def test_conditioncolor_helper_exists_globally(
        self, client_html_text: str
    ):
        """Drop A primitive: conditionColor must be available in client
        global scope. Drop E depends on Drop A — guard against any
        accidental re-scoping."""
        assert "function conditionColor(" in client_html_text
        assert "window.conditionColor = conditionColor" in client_html_text


# ───────────────────────────────────────────────────────────────────────
# F15 — No ship "wound levels" anywhere in the client
# ───────────────────────────────────────────────────────────────────────


class TestF15NoShipWoundLevels:

    def test_no_ship_wound_phrasing(self, client_html_text: str):
        """Ships have CONDITION (Star Warriors p17), not wound levels.
        Any 'ship.*wound' or 'wound.*ship' phrasing in the client is
        a category error — ground combat has wound levels, ships have
        conditions. Regression guard."""
        # Use case-insensitive matching to catch any drift.
        offending = re.compile(
            r"ship[\w\s]*wound|wound[\w\s]*ship", re.IGNORECASE
        )
        hits = offending.findall(client_html_text)
        # Allow zero hits. Filter out false positives if any natural
        # phrase like "ship_wound" or "shipwound" sneaks in via comments
        # discussing the design rule itself.
        # (We want zero hits, period. The whole point of F15 is that the
        # phrase shouldn't appear at all.)
        assert hits == [], (
            f"F15 regression: found ship-wound phrasing in client.html: "
            f"{hits[:5]}"
        )

    def test_no_ship_wound_level_identifier(self, client_html_text: str):
        """Specifically, no `ship_wound_level` symbol or similar."""
        for forbidden in (
            "ship_wound_level",
            "shipWoundLevel",
            "ship-wound-level",
        ):
            assert forbidden not in client_html_text, (
                f"F15 regression: forbidden identifier '{forbidden}'"
            )
