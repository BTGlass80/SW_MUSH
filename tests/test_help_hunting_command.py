"""
tests/test_help_hunting_command.py

Help-corpus entry for the +hunting solo-PvE mob-grind log command
(shipped in the solo-pve-mob-grind drop, 2026-06-21).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data"))

import pytest
from help_topics import HelpManager


@pytest.fixture(scope="module")
def mgr():
    m = HelpManager()
    m.load_markdown_files("data/help")
    return m


class TestHuntingHelp:
    def test_plus_hunting_covered(self, mgr):
        assert mgr.get("+hunting") is not None

    def test_hunting_alias(self, mgr):
        assert mgr.get("hunting") is not None

    def test_huntlog_alias(self, mgr):
        assert mgr.get("+huntlog") is not None

    def test_bare_huntlog_alias(self, mgr):
        assert mgr.get("huntlog") is not None

    def test_body_mentions_kills(self, mgr):
        body = mgr.get("+hunting").body.lower()
        assert "kill" in body

    def test_body_mentions_daily_cap(self, mgr):
        body = mgr.get("+hunting").body.lower()
        assert "daily" in body and ("cap" in body or "400" in body)

    def test_body_mentions_titles(self, mgr):
        body = mgr.get("+hunting").body.lower()
        assert "title" in body or "milestone" in body

    def test_body_no_cp(self, mgr):
        body = mgr.get("+hunting").body.lower()
        # The help must clarify that hunting grants no Character Points
        assert "cp" in body or "character point" in body or "no cp" in body or "zero" in body

    def test_body_mentions_milestone_thresholds(self, mgr):
        body = mgr.get("+hunting").body
        assert "25" in body and "100" in body

    def test_see_also_includes_bounty(self, mgr):
        entry = mgr.get("+hunting")
        see_also_lower = [s.lower() for s in entry.see_also]
        assert "+bounty" in see_also_lower or "bounty" in see_also_lower

    def test_see_also_includes_title(self, mgr):
        entry = mgr.get("+hunting")
        see_also_lower = [s.lower() for s in entry.see_also]
        assert "+title" in see_also_lower or "title" in see_also_lower
