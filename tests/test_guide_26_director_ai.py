"""Guard: Guide_26 Director AI teaches commands that actually RESOLVE against the
live registry, and its quantified claims match the engine.

The Opus-owned guides quality pass.  Before this pass Guide_26 carried a dense
layer of **phantoms** the prose had drifted into:

* **§11 taught `+zone-status`, `+bounty list`, `+history rep`, and `+news
  <count>`** — none of which exist.  The real surfaces are `+news` (no count
  arg), `+missions`, `+bounties`, `+reputation`, `+weather`, and `look`.  `+events`
  is the player *social calendar*, not the world-event feed.
* **§7 described a Claude "Roleplay Evaluator" that scores your poses** — there
  is no such producer.  Roleplay is rewarded by the player/engine `+scenebonus`
  and `+kudos` paths.  (cp_engine has a dormant ``award_ai_trickle`` seam with no
  production caller — pinned below so §7 stays true until something wires it.)
* **§3 claimed 12 standard / 5 milestone events** — the engine has 17 EventType
  defs and 7 ERA_MILESTONES.
* **§8 described a scripted 3-phase Order-66 arc** — only the influence-driven
  milestone tide exists.

This test resolves every command the guide teaches against the SAME registry
``GameServer.__init__`` builds, pins the phantom removals, and cross-checks the
event roster, milestone count, influence/alert/security constants, and the RP
reward numbers against the live engine so a future retune that desyncs the guide
fails loudly here instead of silently misleading players.
"""
import glob
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_26_Director_AI.md")


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
        "_dirreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every command Guide_26 §11 teaches must resolve against HEAD ──────────────
_TAUGHT_FORMS = [
    "+news",          # §5/§11 — HoloNet feed
    "news",           # alias
    "+missions",      # §11 — mission board
    "+bounties",      # §11 — the real bounty-board key (NOT "+bounty list")
    "+reputation",    # §11 — faction standing the Director targets by
    "+rep",           # alias
    "+weather",       # §11 — active weather world events
    "look",           # §11 — the room shows the zone security tier
    "+scenebonus",    # §7 — scene-completion RP reward
    "+kudos",         # §7 — peer RP reward
]


class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", _TAUGHT_FORMS)
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_26 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )


# ── The phantom commands must stay dead ───────────────────────────────────────
class TestNoPhantomCommands:
    def test_phantom_forms_not_taught(self, guide_text):
        # These were the drifted commands; none exist.
        for phantom in ("+zone-status", "+bounty list", "+history rep",
                        "+news <count>", "+news <n>"):
            assert phantom not in guide_text, (
                f"Guide_26 must not teach {phantom!r} — no such command exists"
            )

    def test_zone_status_does_not_resolve(self, reg):
        for form in ("+zone-status", "+zonestatus", "zone-status"):
            assert reg.get(form) is None, (
                f"{form!r} unexpectedly resolves — re-check Guide_26 §11"
            )

    def test_direct_control_commands_absent(self, reg, guide_text):
        # The guide promises the player CANNOT command the Director directly.
        for form in ("+petition", "+request-event", "+ask-director"):
            assert reg.get(form) is None, (
                f"{form!r} now resolves — Guide_26 §11 says it must not exist"
            )
        # And the prose still tells players these do not exist.
        assert "+petition" in guide_text and "+ask-director" in guide_text

    def test_events_is_not_sold_as_world_event_feed(self, guide_text):
        # +events is the social calendar; the guide must clarify that, not list
        # it as a Director world-event command.
        assert "social calendar" in guide_text.lower()


# ── §3 world-event roster must match the EventType enum ───────────────────────
class TestWorldEventRoster:
    def test_seventeen_event_types(self):
        from engine.world_events import EventType, EVENT_DEFS

        assert len(list(EventType)) == 17, (
            "EventType count changed — update Guide_26 §3 and §12"
        )
        # Every enum member has a real EventDef (no phantom rows in the table).
        assert set(EVENT_DEFS.keys()) == set(EventType)

    def test_guide_states_seventeen(self, guide_text):
        assert "seventeen" in guide_text.lower()
        assert "17 types" in guide_text
        # The old miscount must be gone.
        assert "Twelve standard event types" not in guide_text
        assert "12 standard" not in guide_text

    @pytest.mark.parametrize("name", [
        "Gravel storm", "Sandwhirl", "Intelligence thaw", "Spice demand",
        "E'Y-Akh flood", "Separatist agitation", "Security crackdown",
    ])
    def test_real_events_present(self, guide_text, name):
        assert name in guide_text, (
            f"Guide_26 §3 omits the real event {name!r}"
        )


# ── §3 milestone headlines must match ERA_MILESTONES ──────────────────────────
class TestMilestones:
    def test_seven_era_milestones(self):
        from engine.director import ERA_MILESTONES

        assert len(ERA_MILESTONES) == 7, (
            "ERA_MILESTONES count changed — update Guide_26 §3 and §12"
        )

    def test_guide_states_seven(self, guide_text):
        assert "Seven are authored" in guide_text
        assert "Milestone headlines | 7" in guide_text


# ── §2/§6/§12 influence constants must match the engine ───────────────────────
class TestInfluenceConstants:
    def test_constants(self):
        from engine import director

        assert director.MAX_DELTA == 5
        assert director.MIN_INFLUENCE == 0
        assert director.MAX_INFLUENCE == 100
        assert director.FACTION_TURN_INTERVAL == 1800
        assert len(director.VALID_FACTIONS) == 6

    def test_guide_states_the_numbers(self, guide_text):
        assert "30 game-minutes" in guide_text
        assert "5 points" in guide_text
        assert "0 to 100" in guide_text or "0–100" in guide_text
        assert "Player-joinable factions | 6" in guide_text


# ── §12 security-tier overlay thresholds must match _apply_director_overlay ────
class TestSecurityOverlayThresholds:
    def _overlay(self, base, **axes):
        from engine.director import ALERT_AXIS
        from engine.security import _apply_director_overlay

        by_key = {ALERT_AXIS[role]: val for role, val in axes.items()}

        class _StubZS:
            def get_faction(self, key):
                return by_key.get(key, 0)

        return _apply_director_overlay(base, _StubZS())

    def test_authority_75_upgrades_one_tier(self):
        from engine.security import SecurityLevel as SL
        assert self._overlay(SL.CONTESTED, authority=75) == SL.SECURED
        assert self._overlay(SL.CONTESTED, authority=74) == SL.CONTESTED

    def test_underworld_80_downgrades_one_tier(self):
        from engine.security import SecurityLevel as SL
        assert self._overlay(SL.CONTESTED, underworld=80) == SL.LAWLESS
        assert self._overlay(SL.CONTESTED, underworld=79) == SL.CONTESTED

    def test_authority_90_forces_secured(self):
        from engine.security import SecurityLevel as SL
        assert self._overlay(SL.LAWLESS, authority=90) == SL.SECURED

    def test_guide_states_thresholds(self, guide_text):
        assert "Authority (Republic) ≥ 75" in guide_text
        assert "Authority (Republic) ≥ 90" in guide_text
        assert "Underworld (Hutt) ≥ 80" in guide_text


# ── §12 director alert level must match ZoneState.compute_alert ────────────────
class TestAlertThresholds:
    def _alert(self, **axes):
        from engine.director import ALERT_AXIS, ZoneState

        scores = {ALERT_AXIS[role]: val for role, val in axes.items()}
        return ZoneState(zone_key="z", scores=scores).compute_alert()

    def test_lockdown_at_authority_70(self):
        from engine.director import AlertLevel
        assert self._alert(authority=70) == AlertLevel.LOCKDOWN

    def test_underworld_at_70(self):
        from engine.director import AlertLevel
        assert self._alert(underworld=70) == AlertLevel.UNDERWORLD

    def test_unrest_at_warfront_40(self):
        from engine.director import AlertLevel
        assert self._alert(warfront=40) == AlertLevel.UNREST

    def test_high_alert_at_authority_50(self):
        from engine.director import AlertLevel
        assert self._alert(authority=50) == AlertLevel.HIGH_ALERT

    def test_lax_at_low_authority(self):
        from engine.director import AlertLevel
        assert self._alert(authority=10) == AlertLevel.LAX


# ── §7 roleplay-reward numbers must match cp_engine ───────────────────────────
class TestRpRewardFacts:
    def test_kudos_constants(self, guide_text):
        from engine import cp_engine

        assert cp_engine.KUDOS_TICKS == 35
        assert cp_engine.KUDOS_PER_WEEK == 3
        assert "35 ticks" in guide_text
        assert "3 per week" in guide_text

    def test_scene_bonus_min_poses(self, guide_text):
        from engine import cp_engine
        assert cp_engine.SCENE_MIN_POSES == 3
        # Guide §7 table opens its scaling at 1-3 poses.
        assert "1–3" in guide_text

    def test_ai_evaluator_seam_is_dormant(self):
        """§7 says no AI currently grades your prose for rewards.  That is only
        true while ``award_ai_trickle`` has NO production caller.  If any
        engine/parser module ever calls it, the live RP-scoring claim must be
        revisited — fail here so Guide_26 §7 is updated in the same change."""
        import engine.cp_engine as _ce
        assert _ce.is_cp_ai_trickle_enabled() is False, (
            "the CP AI trickle must default DORMANT")
        callers = []
        for d in ("engine", "parser"):
            for path in glob.glob(os.path.join(PROJECT_ROOT, d, "*.py")):
                if os.path.basename(path) == "cp_engine.py":
                    continue  # the definition lives here
                if "award_ai_trickle" in _read(path):
                    callers.append(os.path.basename(path))
        # §7 still holds: the only caller is the MANUAL @director admin grant
        # (a human Director's discretion), NOT an AI scoring poses, and it is
        # dormant by default. (CP fork 2026-06-23.)
        assert callers == ["director_commands.py"], (
            "award_ai_trickle must only be called by the @director admin grant "
            "(not an auto/AI prose scorer); got %r" % (callers,))


# ── §2 NPC-only narrative factions must match director_config.yaml ────────────
class TestNpcOnlyFactions:
    def test_config_lists_the_four(self):
        import yaml

        cfg_path = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                                "director_config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        assert set(cfg["npc_only_factions"]) == {
            "sith", "separatist_council", "stalgasin", "gehenbar",
        }

    def test_guide_names_them(self, guide_text):
        for name in ("Sith", "Separatist Council", "Stalgasin", "Gehenbar"):
            assert name in guide_text, (
                f"Guide_26 §2 omits NPC-only faction {name!r}"
            )
        assert "NPC-only narrative factions | 4" in guide_text
