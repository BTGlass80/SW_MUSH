"""Guard: Guide_08 Force Powers teaches the powers, difficulties, dark-side
flags and commands that actually exist in the live engine.

The Opus-owned guides quality pass.  Guide_08 had drifted badly from HEAD:

* It documented **8 powers**; the engine ``POWERS`` roster has **13** (the
  Drop 4a / 4a.2 expansion of 2026-06-04 added Telepathy, Sense Deception,
  Farseeing, Danger Sense, and split the old mind trick into a light
  **Affect Mind** + a dark **Dominate Mind**).
* It marked **Affect Mind** as a dark-side power that "always earns 1 Dark
  Side Point."  That is now **wrong** — ``affect_mind.dark_side is False``.
  The two dark powers are ``injure_kill`` and ``dominate_mind``.  Teaching a
  player that the Jedi mind trick corrupts them is a real, safety-relevant
  error the green suite never caught (the convention-invariant test guards the
  command *registry*, not guide prose).
* Its DSP warning tiers were off by one against ``_dsp_warning``.
* §7 claimed Force attributes advance via the ``train`` command (with a
  1 / 6 / 15 CP table).  ``train`` only advances ``skills.yaml`` skills;
  Control/Sense/Alter are not skills there, so ``train control`` is rejected.
  The real path is the Master–Padawan ``+teach`` bond (Guide #14).

This test resolves every command the guide teaches against the SAME registry
``GameServer.__init__`` builds, and cross-checks the power roster, difficulties,
dark-side flags, DSP threshold and the telekinesis disarm margin against the
live ``engine.force_powers`` constants — so a future engine retune that desyncs
the guide fails loudly here instead of silently misleading players.
"""
import inspect
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_08_Force_Powers.md")


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
        "_forcereg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── The guide's claims, expressed as a table the test cross-checks vs engine ──
# (engine key, guide-facing display name, difficulty label, base diff, dark?)
DIFF_LABELS = {5: "Very Easy", 10: "Easy", 15: "Moderate",
               20: "Difficult", 25: "Very Difficult", 30: "Heroic"}

GUIDE_POWERS = [
    ("accelerate_healing", "Accelerate Healing", 15, False),
    ("control_pain",       "Control Pain",       10, False),
    ("remain_conscious",   "Remain Conscious",   20, False),
    ("life_sense",         "Life Sense",         10, False),
    ("sense_force",        "Sense Force",         10, False),
    ("telepathy",          "Telepathy",          15, False),
    ("sense_lie",          "Sense Deception",    15, False),
    ("farseeing",          "Farseeing",          20, False),
    ("danger_sense",       "Danger Sense",       15, False),
    ("telekinesis",        "Telekinesis",        10, False),
    ("injure_kill",        "Injure/Kill",        10, True),
    ("affect_mind",        "Affect Mind",        15, False),
    ("dominate_mind",      "Dominate Mind",      20, True),
]


# ── Every command Guide_08 teaches must resolve against HEAD ──────────────────
_TAUGHT_FORMS = [
    "force",          # §3/§8 — use a power
    "+powers",        # §3/§8 — canonical list (A1: OOC/query gets +)
    "+forcestatus",   # §3/§8 — canonical status
]


class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", _TAUGHT_FORMS)
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_08 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )

    def test_legacy_aliases_still_live(self, reg):
        """The bare ``powers``/``forcestatus`` survive as aliases (the engine
        kept them); the in-game ``force`` help still points at them."""
        for form in ("powers", "forcestatus"):
            assert reg.get(form) is not None


class TestPowerRosterMatchesEngine:
    def test_engine_has_exactly_the_documented_powers(self):
        """If a 14th power is ever added to the engine, this fails so the guide
        (and this table) get updated alongside it."""
        from engine.force_powers import POWERS
        assert set(POWERS) == {k for k, _, _, _ in GUIDE_POWERS}, (
            "engine.force_powers.POWERS roster diverged from Guide_08's table"
        )

    @pytest.mark.parametrize("key,name,diff,dark", GUIDE_POWERS)
    def test_engine_difficulty_and_dark_flag(self, key, name, diff, dark):
        from engine.force_powers import POWERS
        p = POWERS[key]
        assert p.base_diff == diff, (
            f"{key}: engine base_diff={p.base_diff}, guide table says {diff}"
        )
        assert p.dark_side is dark, (
            f"{key}: engine dark_side={p.dark_side}, guide table says {dark}"
        )

    @pytest.mark.parametrize("key,name,diff,dark", GUIDE_POWERS)
    def test_power_named_in_guide(self, guide_text, key, name, diff, dark):
        assert name in guide_text, f"{name} is not documented in Guide_08"

    @pytest.mark.parametrize("key,name,diff,dark", GUIDE_POWERS)
    def test_difficulty_label_present(self, guide_text, key, name, diff, dark):
        token = f"{DIFF_LABELS[diff]} ({diff})"
        assert token in guide_text, (
            f"Guide_08 should state {token!r} for {name}"
        )

    def test_thirteen_powers_claim(self, guide_text):
        low = guide_text.lower()
        assert "13 powers" in low, "Guide_08 must state the 13-power roster"
        assert "eight powers" not in low, "stale '8 powers' framing must be gone"
        assert "8 powers" not in low


def _power_header(guide_text, name):
    """Return the `**Name**` header line for a power, or None."""
    for line in guide_text.splitlines():
        s = line.strip()
        if s.startswith(f"**{name}**"):
            return s
    return None


class TestDarkSideAccuracy:
    def test_engine_dark_set_is_injure_and_dominate(self):
        from engine.force_powers import POWERS
        engine_dark = {k for k, p in POWERS.items() if p.dark_side}
        assert engine_dark == {"injure_kill", "dominate_mind"}

    def test_affect_mind_is_light_not_dark(self):
        from engine.force_powers import POWERS
        assert POWERS["affect_mind"].dark_side is False
        assert POWERS["dominate_mind"].dark_side is True

    @pytest.mark.parametrize("key,name,diff,dark", GUIDE_POWERS)
    def test_dark_marker_bound_to_correct_power(self, guide_text,
                                                key, name, diff, dark):
        """The ⚠️ DARK SIDE marker must sit on exactly the dark powers'
        header lines — not on Affect Mind."""
        header = _power_header(guide_text, name)
        assert header is not None, f"no `**{name}**` header in Guide_08"
        has_marker = "DARK SIDE" in header
        assert has_marker is dark, (
            f"{name}: guide header dark-marker={has_marker} but engine "
            f"dark_side={dark}"
        )

    def test_no_affect_mind_dsp_phantom(self, guide_text):
        """The old guide claimed Affect Mind 'Always earns 1 Dark Side Point';
        explicitly state it costs no DSP / is light-side instead."""
        header = _power_header(guide_text, "Affect Mind")
        assert "DARK SIDE" not in header
        assert "light-side" in guide_text


class TestDspMechanics:
    def test_fall_threshold(self, guide_text):
        from engine.force_powers import DSP_FALL_THRESHOLD
        assert DSP_FALL_THRESHOLD == 6
        assert "6+ DSP" in guide_text
        assert "DSP × 3" in guide_text  # "DSP × 3"

    def test_fall_difficulties(self, guide_text):
        # At 6 DSP the diff is 6*3=18; at 8 DSP it is 24.
        assert "the difficulty is 18" in guide_text
        assert "the difficulty is 24" in guide_text

    def test_warning_tiers_match_engine(self, guide_text):
        """§5's tier descriptions must match _dsp_warning's actual bands:
        1-3 generic, 4-5 'grows within you', 6+ 'consuming you'."""
        from engine import force_powers
        src = inspect.getsource(force_powers._dsp_warning)
        assert "grows within you" in src and "grows within you" in guide_text
        assert "consuming you" in src and "consuming you" in guide_text
        # The old guide put "consuming you" at 4-5; ensure 6+ now owns it.
        assert "6+ DSP: Fall check triggered" in guide_text


class TestAdvancementNoTrainPhantom:
    def test_train_does_not_raise_force_attributes(self, guide_text):
        # §7 must direct players to the +teach bond, not the train command.
        assert "+teach" in guide_text
        assert "Guide #14" in guide_text
        # the discredited train-table claims must be gone
        assert "first die costs 1 CP" not in guide_text
        assert "1+2+3 = 6 CP" not in guide_text

    def test_force_attrs_are_not_trainable_skills(self):
        """Pin the fact §7 now relies on: Control/Sense/Alter are not in
        skills.yaml, so the `train` command genuinely cannot advance them."""
        from engine.character import SkillRegistry
        sr = SkillRegistry()
        sr.load_file(os.path.join(PROJECT_ROOT, "data", "skills.yaml"))
        for fa in ("control", "sense", "alter"):
            assert sr.get(fa) is None, (
                f"{fa} is now a skills.yaml skill — `train {fa}` would work; "
                f"update Guide_08 §7 and this test together"
            )


class TestMechanicsCrossChecks:
    def test_combination_powers_need_all_three(self, guide_text):
        from engine.force_powers import POWERS
        for key in ("affect_mind", "dominate_mind"):
            assert POWERS[key].skills == ["control", "sense", "alter"]
        assert "weakest" in guide_text.lower()

    def test_telekinesis_disarm_margin(self, guide_text):
        """The guide states a margin of 3+ disarms; pin it to the engine
        constant so a retune of DISARM_MARGIN flags the guide."""
        from engine import force_powers
        src = inspect.getsource(force_powers._resolve_telekinesis)
        assert "DISARM_MARGIN = 3" in src
        assert "margin of 3 or more" in guide_text
