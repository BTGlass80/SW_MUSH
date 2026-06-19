"""Guard: Guide_04 Security Zones teaches commands that actually RESOLVE against
the live registry, and its security-resolution numbers match the engine.

The Opus-owned guides quality pass.  Guide_04 makes a dense set of *quantified*
mechanical claims (PvP timers, influence thresholds, the space-tier mapping, the
territory citadel upgrade) plus one **phantom** the prose carried before this
pass:

* **§6 + §9 taught a "+25% CP tick-rate bonus while in a lawless zone."**  No
  such modifier exists.  ``engine/cp_engine`` has exactly four income sources
  (passive trickle / scene bonus / kudos / AI evaluator) and is entirely
  zone-blind — standing in a lawless room earns no CP at all.  The claim was a
  phantom producer; this pass removed it.

This test resolves every command the guide teaches against the SAME registry
``GameServer.__init__`` builds, pins the phantom removal, and cross-checks the
§2/§3/§5/§7 numbers against the live engine constants so a future engine retune
that desyncs the guide fails loudly here instead of silently misleading players.
"""
import inspect
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_04_Security_Zones.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__).
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_secreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every command Guide_04 teaches must resolve against HEAD ──────────────────
# §1 look · §3 challenge/accept/decline + +pvp · §4 +bounty/claim · §5 fire ·
# §8 @security.  (Movement "move in" is generic directional input, not a key.)
_TAUGHT_FORMS = [
    "look",                       # §1 — the tier label appears on `look`
    "attack",                     # §1/§3 — the gated action
    "challenge", "accept", "decline",   # §3 PvP consent flow
    "+pvp",                       # §3 self-flag (newly documented)
    "fire",                       # §5 — space combat gate
    "@security",                  # §8 admin command
]


class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", _TAUGHT_FORMS)
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_04 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )

    def test_pvp_flag_aliases(self, reg):
        """§3 teaches `+pvp on|off|status` — both `+pvp` and `pvp` resolve."""
        for form in ("+pvp", "pvp"):
            assert reg.get(form) is not None

    def test_bounty_claim_switch(self, reg):
        """§4 teaches `+bounty/claim` — the `+bounty` umbrella exists and
        `claim` is one of its valid switches (it is switch-impl-only)."""
        bounty = reg.get("+bounty")
        assert bounty is not None, "Guide_04 §4 teaches +bounty/claim"
        assert "claim" in getattr(bounty, "valid_switches", []), (
            "`claim` must be a valid +bounty switch (command-syntax rework)"
        )

    def test_security_admin_subforms(self, guide_text):
        """§8 must teach the real four-form @security surface: the two zone
        forms AND the `override <room> = <faction>` set form (not just clear)."""
        assert "@security <zone> = <level>" in guide_text
        assert "@security override <room> = <faction>" in guide_text
        assert "@security override <room> = none" in guide_text


# ── The phantom must stay dead ────────────────────────────────────────────────
class TestNoCpLawlessPhantom:
    def test_guide_has_no_plus25_cp_claim(self, guide_text):
        # The phantom was phrased "+25% bonus"/"+25% CP bonus".  Forbid the
        # whole "+25%" token in this guide — there is no such mechanic to cite.
        assert "+25%" not in guide_text, (
            "Guide_04 must not promise a +25% lawless CP/credit bonus — "
            "no such modifier exists in engine/cp_engine"
        )
        assert "25% bonus" not in guide_text

    def test_cp_engine_is_zone_blind(self):
        """Pin the fact the phantom relied on: the CP engine has NO security /
        zone / lawless awareness.  If a real lawless CP bonus is ever wired,
        this fails — update Guide_04 §6 and this test together."""
        from engine import cp_engine

        src = inspect.getsource(cp_engine).lower()
        for token in ("lawless", "get_effective_security", "securitylevel"):
            assert token not in src, (
                f"engine/cp_engine now references {token!r} — CP may have gained "
                f"a zone modifier; re-check Guide_04 §6 (which states CP is "
                f"earned by play, not by standing in a lawless zone)"
            )


# ── §3 PvP timers must match the engine constants ─────────────────────────────
class TestPvpTimers:
    def test_challenge_ttl_is_ten_minutes(self, guide_text):
        from parser.combat_commands import _PVP_CHALLENGE_TTL

        assert _PVP_CHALLENGE_TTL == 600, "challenge TTL moved off 10 minutes"
        assert "ten minutes" in guide_text or "10 minutes" in guide_text

    def test_pvp_unflag_cooldown_is_five_minutes(self, guide_text):
        from engine.cooldowns import PVP_UNFLAG_COOLDOWN_S

        assert PVP_UNFLAG_COOLDOWN_S == 300, "+pvp unflag cooldown moved off 5m"
        assert "five minutes" in guide_text or "five-minute" in guide_text


# ── §2 influence thresholds must match _apply_director_overlay ────────────────
class TestInfluenceThresholds:
    def _overlay(self, base, **axes):
        from engine.director import ALERT_AXIS
        from engine.security import _apply_director_overlay, SecurityLevel

        by_key = {ALERT_AXIS[role]: val for role, val in axes.items()}

        class _StubZS:
            def get_faction(self, key):
                return by_key.get(key, 0)

        return _apply_director_overlay(base, _StubZS())

    def test_underworld_surge_at_80_downgrades(self):
        from engine.security import SecurityLevel as SL
        assert self._overlay(SL.CONTESTED, underworld=80) == SL.LAWLESS
        # Just below the line: no downgrade.
        assert self._overlay(SL.CONTESTED, underworld=79) == SL.CONTESTED

    def test_authority_crackdown_at_75_upgrades(self):
        from engine.security import SecurityLevel as SL
        assert self._overlay(SL.LAWLESS, authority=75) == SL.CONTESTED
        assert self._overlay(SL.LAWLESS, authority=74) == SL.LAWLESS

    def test_martial_law_at_90_forces_secured(self):
        from engine.security import SecurityLevel as SL
        assert self._overlay(SL.LAWLESS, authority=90) == SL.SECURED

    def test_guide_states_the_numbers(self, guide_text):
        # §2 #2 must carry the 75 / 80 / 90 thresholds the engine uses.
        assert "75" in guide_text and "80" in guide_text and "90" in guide_text


# ── §5 space-tier mapping must match _SPACE_SECURITY_BY_TYPE ───────────────────
class TestSpaceTierMapping:
    def test_mapping_matches_engine(self):
        from engine.npc_space_traffic import _SPACE_SECURITY_BY_TYPE, ZoneType

        assert _SPACE_SECURITY_BY_TYPE == {
            ZoneType.DOCK:            "secured",
            ZoneType.ORBIT:           "contested",
            ZoneType.HYPERSPACE_LANE: "contested",
            ZoneType.DEEP_SPACE:      "lawless",
        }

    def test_guide_table_matches(self, guide_text):
        # §5 table rows.
        assert re.search(r"\*\*Dock\*\*\s*\|\s*Secured", guide_text)
        assert re.search(r"\*\*Orbit\*\*\s*\|\s*Contested", guide_text)
        assert re.search(r"\*\*Hyperspace Lane\*\*\s*\|\s*Contested", guide_text)
        assert re.search(r"\*\*Deep Space\*\*\s*\|\s*Lawless", guide_text)


# ── §7 wilderness citadel upgrade must match _apply_wilderness_ownership ───────
class TestCitadelUpgrade:
    def _state(self, owner):
        from engine.security import SecurityLevel as SL
        return {"slug": "r", "default_security": SL.LAWLESS, "owner_org": owner}

    def test_member_gets_lawless_to_contested(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel as SL
        char = {"faction_id": "falleen"}
        assert _apply_wilderness_ownership(
            SL.LAWLESS, char, self._state("falleen")) == SL.CONTESTED

    def test_non_member_sees_base(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel as SL
        char = {"faction_id": "black_sun"}
        assert _apply_wilderness_ownership(
            SL.LAWLESS, char, self._state("falleen")) == SL.LAWLESS

    def test_independent_gets_no_upgrade(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel as SL
        char = {"faction_id": "independent"}
        assert _apply_wilderness_ownership(
            SL.LAWLESS, char, self._state("falleen")) == SL.LAWLESS

    def test_ceiling_is_contested_not_secured(self):
        """The guide states wilderness never becomes fully SECURED."""
        from engine.security import _apply_wilderness_ownership, SecurityLevel as SL
        char = {"faction_id": "falleen"}
        # A contested base stays contested (no further promotion to SECURED).
        assert _apply_wilderness_ownership(
            SL.CONTESTED, char, self._state("falleen")) == SL.CONTESTED


# ── §2 #5 faction-override + §2 #6 city-upgrade direction (source-pinned) ──────
class TestFinalizeModifierDirections:
    def test_faction_override_only_downgrades_secured_to_lawless(self):
        from engine import security
        src = inspect.getsource(security._apply_faction_override)
        # SECURED-only gate + Hostile/Unfriendly (rep <= -25) → LAWLESS.
        assert "if base != SecurityLevel.SECURED" in src
        assert "rep <= -25" in src
        assert "return SecurityLevel.LAWLESS" in src

    def test_city_upgrade_directions(self):
        from engine import security
        src = inspect.getsource(security._apply_city_upgrade)
        # CONTESTED → SECURED and LAWLESS → CONTESTED for citizens.
        assert "return SecurityLevel.SECURED" in src
        assert "return SecurityLevel.CONTESTED" in src
        assert "is_citizen" in src
