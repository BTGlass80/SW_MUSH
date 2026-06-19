"""
tests/test_help_misc_command_gaps.py

Verify that all remaining player-command gaps are now covered by the help system.
Covers:
  - New files: quit, semipose, examine, encounter, trade, pay, refine, mail,
               training, use, restrain, allowrestrain, accuse, gate, path
  - Alias fixes: +factions/factions (via +faction), anom (via anomalies topics),
                 mu (via +place), boardship/boardlink (via board),
                 full dodge/full parry/combat rolls (via +combat), pc (via +party),
                 useforce (via force topics)
  - &/@setattr (BUILDER-level; intentionally not player-facing, excluded from coverage check)
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data"))

from help_topics import HelpManager


@pytest.fixture(scope="module")
def mgr():
    m = HelpManager()
    m.load_markdown_files("data/help")
    return m


# ── New files ──────────────────────────────────────────────────────────────────

class TestQuitHelp:
    def test_quit_covered(self, mgr):
        assert mgr.get("quit") is not None

    def test_logout_alias(self, mgr):
        assert mgr.get("logout") is not None

    def test_QUIT_alias(self, mgr):
        assert mgr.get("QUIT") is not None

    def test_quit_content(self, mgr):
        body = mgr.get("quit").body
        assert "sleep" in body.lower() or "disconnect" in body.lower()


class TestSemiposeHelp:
    def test_semicolon_covered(self, mgr):
        assert mgr.get(";") is not None

    def test_semipose_alias(self, mgr):
        assert mgr.get("semipose") is not None

    def test_semipose_content(self, mgr):
        body = mgr.get(";").body
        assert "name" in body.lower()


class TestExamineHelp:
    def test_examine_covered(self, mgr):
        assert mgr.get("examine") is not None

    def test_examine_mentions_fragment(self, mgr):
        body = mgr.get("examine").body
        assert "fragment" in body.lower()


class TestEncounterHelp:
    def test_encounter_covered(self, mgr):
        assert mgr.get("encounter") is not None

    def test_enc_alias(self, mgr):
        assert mgr.get("enc") is not None

    def test_respond_alias(self, mgr):
        assert mgr.get("respond") is not None

    def test_resp_alias(self, mgr):
        assert mgr.get("resp") is not None

    def test_stationact_alias(self, mgr):
        assert mgr.get("stationact") is not None

    def test_sa_alias(self, mgr):
        assert mgr.get("sa") is not None

    def test_encounter_content(self, mgr):
        body = mgr.get("encounter").body
        assert "respond" in body.lower()


class TestTradeHelp:
    def test_trade_covered(self, mgr):
        assert mgr.get("trade") is not None

    def test_plus_trade_alias(self, mgr):
        assert mgr.get("+trade") is not None

    def test_offer_alias(self, mgr):
        assert mgr.get("offer") is not None

    def test_trade_content(self, mgr):
        body = mgr.get("trade").body
        assert "5%" in body or "tax" in body.lower()


class TestPayHelp:
    def test_pay_covered(self, mgr):
        assert mgr.get("pay") is not None

    def test_pay_content(self, mgr):
        body = mgr.get("pay").body
        assert "pirate" in body.lower()


class TestRefineHelp:
    def test_refine_covered(self, mgr):
        assert mgr.get("refine") is not None

    def test_refine_mentions_refinery(self, mgr):
        body = mgr.get("refine").body
        assert "refinery" in body.lower() or "2:1" in body or "raw" in body.lower()


class TestMailHelp:
    def test_mail_covered(self, mgr):
        assert mgr.get("mail") is not None

    def test_plus_mail_alias(self, mgr):
        assert mgr.get("+mail") is not None

    def test_mail_content(self, mgr):
        body = mgr.get("mail").body
        assert "@mail" in body


class TestTrainingHelp:
    def test_training_covered(self, mgr):
        assert mgr.get("training") is not None

    def test_plus_training_alias(self, mgr):
        assert mgr.get("+training") is not None

    def test_training_content(self, mgr):
        body = mgr.get("training").body
        assert "module" in body.lower() or "grounds" in body.lower()

    def test_training_not_same_as_train(self, mgr):
        train_entry = mgr.get("train")
        training_entry = mgr.get("training")
        assert train_entry is not None
        assert training_entry is not None
        assert train_entry.key != training_entry.key


class TestUseHelp:
    def test_use_covered(self, mgr):
        assert mgr.get("use") is not None

    def test_use_content(self, mgr):
        body = mgr.get("use").body
        assert "inventory" in body.lower() or "item" in body.lower()


class TestRestrainHelp:
    def test_cuff_covered(self, mgr):
        assert mgr.get("cuff") is not None

    def test_restrain_alias(self, mgr):
        assert mgr.get("restrain") is not None

    def test_bind_alias(self, mgr):
        assert mgr.get("bind") is not None

    def test_uncuff_alias(self, mgr):
        assert mgr.get("uncuff") is not None

    def test_unbind_alias(self, mgr):
        assert mgr.get("unbind") is not None

    def test_restrain_content(self, mgr):
        body = mgr.get("restrain").body
        assert "binder" in body.lower() or "defeated" in body.lower()


class TestAllowRestrainHelp:
    def test_allowrestrain_covered(self, mgr):
        assert mgr.get("allowrestrain") is not None

    def test_consentrestrain_alias(self, mgr):
        assert mgr.get("consentrestrain") is not None

    def test_allowrestrain_content(self, mgr):
        body = mgr.get("allowrestrain").body
        assert "on" in body.lower() and "off" in body.lower()


class TestVillageTrialCommandsHelp:
    def test_accuse_covered(self, mgr):
        assert mgr.get("accuse") is not None

    def test_accuse_content(self, mgr):
        body = mgr.get("accuse").body
        assert "fragment" in body.lower()

    def test_gate_covered(self, mgr):
        assert mgr.get("gate") is not None

    def test_gate_content(self, mgr):
        body = mgr.get("gate").body
        assert "vitha" in body.lower() or "gate" in body.lower()

    def test_path_covered(self, mgr):
        assert mgr.get("path") is not None

    def test_path_content(self, mgr):
        body = mgr.get("path").body
        assert "jedi" in body.lower() or "village" in body.lower()


# ── Alias fixes ────────────────────────────────────────────────────────────────

class TestAliasFixesMiscGaps:
    def test_plus_factions_covered(self, mgr):
        assert mgr.get("+factions") is not None

    def test_anom_covered(self, mgr):
        assert mgr.get("anom") is not None

    def test_mu_covered(self, mgr):
        assert mgr.get("mu") is not None

    def test_boardship_covered(self, mgr):
        assert mgr.get("boardship") is not None

    def test_boardlink_covered(self, mgr):
        assert mgr.get("boardlink") is not None

    def test_full_dodge_covered(self, mgr):
        assert mgr.get("full dodge") is not None

    def test_full_parry_covered(self, mgr):
        assert mgr.get("full parry") is not None

    def test_combat_rolls_covered(self, mgr):
        assert mgr.get("combat rolls") is not None

    def test_pc_covered(self, mgr):
        assert mgr.get("pc") is not None

    def test_useforce_covered(self, mgr):
        assert mgr.get("useforce") is not None


# ── Coverage regression: all player commands have help ─────────────────────────

class TestPlayerCommandCoverageRegression:
    """
    Checks that all player-facing commands (non-@, non-__) have help entries.
    Only & (@setattr BUILDER shorthand) is intentionally excluded.
    """

    BUILDER_ONLY = {"&"}

    def test_no_new_player_command_gaps(self, mgr):
        sys.path.insert(0, ".")
        from tests.test_command_convention_invariant import _build_full_registry
        reg = _build_full_registry()

        all_names = set()
        for cmd in reg._commands.values():
            all_names.add(cmd.key)
            for alias in (cmd.aliases or []):
                all_names.add(alias)

        player_cmds = [
            k for k in all_names
            if not k.startswith("@") and not k.startswith("__")
            and k not in self.BUILDER_ONLY
        ]

        uncovered = [c for c in player_cmds if mgr.get(c) is None]
        assert uncovered == [], (
            f"Player commands with no help entry: {uncovered}\n"
            f"Add help files or extend aliases in data/help/commands/ "
            f"or data/help/topics/ to cover them."
        )
