"""Guard: Guide_26 §3 documents the dark-side CULT UPRISING player loop
(`rally` / `rally strike` -> staged location scenarios), and its facts match HEAD.

The events-as-playable-scenarios rework (2026-06-24, drops `events-playable-scenarios`
+ `events-more-scenarios`) turned the dark-side cult events from a global menace
counter into a real, fightable system: a visible menace meter, a `rally` threat
board, and for THREE cults a staged location scenario you travel to and
`investigate`.  That shipped *after* Guide_26's last pass, and §3 had treated all
dark-side beats as pure Director narration ("don't surface as a tracked number"),
while the guide corpus documented the live `rally` loop NOWHERE.

This re-verify pins the new §3 subsection + the §11 `rally` row against the live
engine — the cult roster, the staged-vs-menace split, the reputation-only reward
band, and the command resolution — so an engine revert or a guide drift fails
loudly here instead of silently misleading players.
"""
import importlib.util
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_26_Director_AI.md")
RUNTIME_PATH = os.path.join(PROJECT_ROOT, "engine",
                            "communal_objective_runtime.py")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def reg():
    # Reuse the canonical full-registry builder (mirrors GameServer.__init__),
    # exactly as the sibling Guide_26 authoritative suite does.
    spec = importlib.util.spec_from_file_location(
        "_dirreg_for_cult_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── The guide teaches the real participation surface ──────────────────────────
class TestRallySurfaceDocumented:
    def test_prose_teaches_rally_and_strike(self, guide_text):
        assert "rally" in guide_text
        assert "rally strike" in guide_text
        # the documented alias
        assert "front" in guide_text

    def test_prose_teaches_menace_meter_and_winloss(self, guide_text):
        low = guide_text.lower()
        assert "menace meter" in low
        assert "cult uprising" in low
        assert "win/lose state" in low

    @pytest.mark.parametrize("form", ["rally", "+rally", "front"])
    def test_rally_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_26 §3/§11 teaches {form!r} but it no longer resolves "
            f"against the live registry"
        )


# ── The staged-vs-menace split matches the engine ─────────────────────────────
class TestStagedVsMenaceTaught:
    def test_prose_teaches_travel_and_investigate(self, guide_text):
        # The staged-scenario gameplay is AT the site, via investigate.
        assert "investigate" in guide_text
        low = guide_text.lower()
        assert "staged operation" in low
        assert "locator" in low

    def test_investigate_resolves(self, reg):
        assert reg.get("investigate") is not None, (
            "Guide_26 §3 tells the player to `investigate` a staged cult site, "
            "but `investigate` no longer resolves"
        )

    def test_three_staged_cults_match_engine(self, guide_text):
        from engine import staged_event as SE

        assert set(SE.STAGED_CULTS.keys()) == {
            "hollow_sun", "ember_court", "ashen_hand"
        }, "STAGED_CULTS changed — reconcile Guide_26 §3"
        # Each staged cult is is_staged True; a menace cult is False.
        for key in ("hollow_sun", "ember_court", "ashen_hand"):
            assert SE.is_staged(key)
        for key in ("drowned_choir", "iron_veil"):
            assert not SE.is_staged(key)

    @pytest.mark.parametrize("name", [
        "Hollow Sun", "Ember Court", "Ashen Hand",   # staged
        "Drowned Choir", "Iron Veil",                # menace
    ])
    def test_prose_names_every_cult(self, guide_text, name):
        assert name in guide_text, (
            f"Guide_26 §3 omits the live cult {name!r}"
        )

    @pytest.mark.parametrize("planet", ["Tatooine", "Geonosis", "Coruscant",
                                        "Nar Shaddaa", "Kuat"])
    def test_prose_names_every_cult_world(self, guide_text, planet):
        assert planet in guide_text, (
            f"Guide_26 §3 omits the cult world {planet!r}"
        )


# ── The cult roster the prose leans on is exactly the live roster ─────────────
class TestCultRosterMatchesEngine:
    def test_five_cults_with_the_named_keys(self):
        from engine import communal_objective as CO

        keys = {c.key for c in CO.CULT_ROSTER}
        assert keys == {
            "hollow_sun", "ember_court", "drowned_choir",
            "iron_veil", "ashen_hand",
        }, "CULT_ROSTER changed — reconcile Guide_26 §3"
        assert set(CO.CULT_BY_KEY.keys()) == keys


# ── The reward facts the prose quotes match the engine ────────────────────────
class TestRewardFactsMatchEngine:
    def test_republic_rep_band_3_to_15(self):
        from engine import communal_objective as CO

        assert CO.REP_FACTION == "republic"
        assert CO.REP_FLOOR == 3
        assert CO.REP_MAX == 15

    def test_prose_states_rep_band_and_no_credits(self, guide_text):
        low = guide_text.lower()
        assert "republic reputation" in low
        # The guide must be explicit there is NO credit reward.
        assert "no credit" in low
        assert "3" in guide_text and "15" in guide_text

    def test_reward_distribution_is_rep_only_no_credits(self):
        # Pin the no-credits invariant at the source: the reward path must not
        # mint credits.  If a future change routes a credit faucet through the
        # cult win, the guide's "no credits" promise breaks and this fails.
        src = _read(RUNTIME_PATH)
        idx = src.find("def _distribute_rewards")
        assert idx != -1, "reward distributor renamed — re-pin Guide_26 §3"
        body = src[idx:idx + 2000]
        assert "adjust_credits" not in body, (
            "the cult-win reward path now touches credits — Guide_26 §3 says "
            "'no credit rewards'"
        )
        assert "No credits" in body  # the load-bearing docstring promise
