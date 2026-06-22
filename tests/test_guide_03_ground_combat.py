"""Guard: Guide_03 Ground Combat teaches commands that actually RESOLVE against
the live registry, and its mechanics tables match the engine constants.

The Opus-owned guides quality pass.  Two test-INVISIBLE breakages were found in
the post-command-syntax-rework guide (the convention-invariant test guards the
registry, not free-text guide prose):

1. **§14 posing** taught ``> pose <text>`` to submit a combat pose.  But bare
   ``pose`` is the generic room-emote alias (``EmoteCommand`` key ``emote``,
   aliases ``:``/``pose``/``em``) — it broadcasts an ordinary emote and never
   registers as the round's combat pose.  The real command is ``cpose``
   (``CombatPoseCommand``, alias ``combatpose``).  A player following the guide
   would emit a stray room pose and silently get the auto-pose instead.

2. **§17 quick reference** listed ``force-point`` (hyphenated).  The registered
   key is ``forcepoint`` (aliases ``fp``/``+fp``); no hyphenated alias exists,
   so ``force-point`` resolves to nothing.

This test resolves every combat command the guide teaches against the SAME
registry ``GameServer.__init__`` builds, pins the two fixes, and cross-checks
the §4/§5/§7/§9/§11/§15 mechanics tables against the live engine constants so a
future engine retune that desyncs the guide fails loudly here.  The §12
mob-grind reward section's hunter-title labels are pinned against
``engine.titles.EARNED_TITLES`` so an engine rename desyncs the guide loudly.
"""
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_03_Ground_Combat.md")


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
        "_combatreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every combat command Guide_03 teaches must resolve against HEAD ───────────
# The canonical forms presented in the §3 action table, §16 quick reference,
# and the worked-example prose.  Modifiers (`with <skill>`, `cp <n>`) ride on
# `attack`; they are not separate commands.
_COMBAT_FORMS = [
    "attack",          # §3/§16 — and `attack <target> with <skill> cp <n>`
    "dodge", "fulldodge",
    "parry", "fullparry",
    "aim",
    "cover",           # `cover [quarter|half|3/4|full]`
    "flee",
    "pass",
    "cpose",           # §13 combat-pose (the FIX — was bare `pose`)
    "combat",          # §15/§16 status
    "crolls",          # §16 detailed dice (alias `combat rolls`)
    "range",
    "challenge", "accept", "decline",
    "soak",            # alias of `+soak`
    "forcepoint",      # §17 (the FIX — was `force-point`)
    "disengage",
    "look",            # §7 "the room's `look` description"
    "+hunting",        # §12/§17 — the solo-PvE mob-grind log
]


class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", _COMBAT_FORMS)
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_03 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )

    def test_forcepoint_aliases(self, reg):
        """The §16 quick ref teaches `forcepoint` / `fp` — both must resolve."""
        for form in ("forcepoint", "fp"):
            assert reg.get(form) is not None
        # The deleted hyphenated form must NOT resolve (it never did).
        assert reg.get("force-point") is None

    def test_cpose_is_the_pose_command(self, reg):
        """`cpose` submits the combat pose; bare `pose` is the room emote."""
        cpose = reg.get("cpose")
        assert cpose is not None and cpose.key == "cpose"
        pose = reg.get("pose")
        assert pose is not None and pose.key != "cpose", (
            "bare `pose` should be the generic emote, not the combat pose"
        )


# ── The two fixed breakages must not regress in the guide prose ───────────────
def test_no_hyphenated_forcepoint(guide_text):
    assert "force-point" not in guide_text, (
        "Guide_03 must teach `forcepoint`/`fp`, never the unresolvable "
        "hyphenated `force-point`"
    )


def test_no_bare_pose_command_instruction(guide_text):
    # A code-block / prompt line instructing `pose <text>` is the broken form;
    # `cpose` is fine.  Match `> pose ` and a backticked bare `pose ` command.
    assert not re.search(r"^>\s*pose\b", guide_text, re.MULTILINE), (
        "Guide_03 §13 must instruct `cpose <text>`, not bare `pose`"
    )
    assert "`cpose`" in guide_text, "Guide_03 §13 must teach the `cpose` command"


# ── Mechanics tables must match the live engine constants ─────────────────────
class TestMechanicsMatchEngine:
    def test_wound_thresholds(self, guide_text):
        """§5 damage-margin → wound table must match WoundLevel.from_damage_margin."""
        from engine.character import WoundLevel as WL

        # Engine is the source of truth at every band boundary.
        cases = {
            0: "HEALTHY", 3: "STUNNED", 4: "WOUNDED", 8: "WOUNDED",
            9: "INCAPACITATED", 12: "INCAPACITATED",
            13: "MORTALLY_WOUNDED", 15: "MORTALLY_WOUNDED", 16: "DEAD",
        }
        for margin, name in cases.items():
            assert WL.from_damage_margin(margin).name == name, (
                f"engine maps margin {margin} → "
                f"{WL.from_damage_margin(margin).name}, guide assumes {name}"
            )
        # The guide table prose must carry the matching bands.
        for band in ("1–3", "4–8", "9–12", "13–15", "16+"):
            assert band in guide_text, (
                f"§5 wound table missing the {band!r} damage-margin band"
            )

    def test_cover_dice(self, guide_text):
        from engine.combat import (
            COVER_QUARTER, COVER_HALF, COVER_THREE_QUARTER,
        )

        assert (COVER_QUARTER, COVER_HALF, COVER_THREE_QUARTER) == (1, 2, 3)
        # §4/§7 teach +1D/+2D/+3D for 1/4, 1/2, 3/4 cover.
        assert "+1D for quarter cover, +2D for half, +3D" in guide_text
        assert "| 1/4 Cover | +1D" in guide_text
        assert "| 1/2 Cover | +2D" in guide_text
        assert "| 3/4 Cover | +3D" in guide_text

    def test_npc_ai_profiles(self, guide_text):
        """§11 must list exactly the five live CombatBehavior profiles."""
        from engine.npc_combat_ai import CombatBehavior

        profiles = {p.value for p in CombatBehavior}
        assert profiles == {
            "aggressive", "defensive", "cowardly", "berserk", "sniper",
        }
        for name in profiles:
            assert name.title() in guide_text, (
                f"§11 NPC-AI table missing the {name!r} behavior profile"
            )

    def test_aim_cap(self, guide_text):
        """§9 aim cap (+3D) — pinned vs the engine cap in CombatAction.apply."""
        import inspect
        from engine import combat as combat_mod

        src = inspect.getsource(combat_mod)
        # Engine caps the accumulating aim bonus at 3 (min(... + 1, 3)).
        assert "min(actor.aim_bonus + 1, 3)" in src, (
            "aim cap moved in engine/combat.py — re-check Guide_03 §9 (+3D)"
        )
        assert "stackable up to **+3D**" in guide_text

    def test_mortal_wound_death_roll(self, guide_text):
        """§15 death roll: 2D, die if total < rounds mortally wounded."""
        import inspect
        from engine import combat as combat_mod

        src = inspect.getsource(combat_mod)
        assert "DicePool(2, 0)" in src and "death_roll.total < rounds_mw" in src, (
            "mortal-wound death-roll math changed — re-check Guide_03 §15"
        )
        assert "rolls 2D" in guide_text


# ── §12 mob-grind reward section: pinned vs the live hunting subsystem ─────────
class TestMobGrindRewardSection:
    """The §12 'Rewards for Defeating NPCs' section was added when the solo-PvE
    mob-grind faucet shipped (2026-06-21) — after Guide_03's prior quality pass.
    It documents the combat-side view of the hunting reward and points to
    Guide_06 Economy for the numbers. Guard the claims that matter."""

    def test_section_exists_and_teaches_hunting(self, guide_text):
        assert "## 12. Rewards for Defeating NPCs" in guide_text
        # The read-only log command the section teaches.
        assert "`+hunting`" in guide_text

    def test_zero_cp_advancement_neutral_claim(self, guide_text):
        """The defining design contract: hunting pays ZERO Character Points so it
        can never touch advancement. If this prose drops, the guide misleads."""
        assert "zero Character Points" in guide_text
        assert "can *never* buy skill growth" in guide_text

    def test_hunter_titles_match_engine(self, guide_text):
        """The four milestone title LABELS must match engine.titles.EARNED_TITLES
        so an engine rename desyncs the guide loudly here."""
        from engine.titles import EARNED_TITLES

        labels = {t["label"] for t in EARNED_TITLES}
        for expected in ("the Hunter", "the Seasoned Hunter",
                         "the Master Hunter", "the Apex Hunter"):
            assert expected in labels, (
                f"engine.titles no longer defines the {expected!r} earned "
                f"title — re-check Guide_03 §12"
            )
            assert expected in guide_text, (
                f"§12 mob-grind section missing the {expected!r} hunter title"
            )

    def test_cross_references_economy_for_numbers(self, guide_text):
        """§12 is the combat-side summary; the per-kill reward / cap / thresholds
        live in Guide_06 Economy. The section must link there, not duplicate."""
        assert "(#/guide/economy)" in guide_text
