# -*- coding: utf-8 -*-
"""
tests/test_help_at_desc.py

Verify the @desc help entry is present and accurate.
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


class TestAtDescHelp:
    def test_at_desc_exists(self, mgr):
        assert mgr.get("@desc") is not None

    def test_at_describe_alias(self, mgr):
        e = mgr.get("@describe")
        assert e is not None
        assert e.key == "@desc"

    def test_desc_bare_not_aliased(self, mgr):
        # bare 'desc' is NOT a registered command alias for @desc
        e = mgr.get("desc")
        assert e is None or e.key != "@desc"

    def test_access_level_player(self, mgr):
        e = mgr.get("@desc")
        assert e.access_level <= 1

    def test_summary_non_empty(self, mgr):
        e = mgr.get("@desc")
        assert len(e.summary) > 10

    def test_body_mentions_description(self, mgr):
        e = mgr.get("@desc")
        assert "description" in e.body.lower()

    def test_body_mentions_2000_limit(self, mgr):
        e = mgr.get("@desc")
        assert "2000" in e.body
