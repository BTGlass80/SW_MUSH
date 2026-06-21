"""
tests/test_help_guide_browser_plots_scenes_filters.py

Help-corpus entries for:
  - +guide / guide browser (drop help-guide-browser-plots-scenes)
  - +plots closed / +plots all filters
  - +scenes shared / +scenes <player> filters
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


class TestGuideBrowserHelp:
    def test_plus_guide_covered(self, mgr):
        assert mgr.get("+guide") is not None

    def test_guide_alias(self, mgr):
        assert mgr.get("guide") is not None

    def test_guides_alias(self, mgr):
        assert mgr.get("guides") is not None

    def test_plus_guides_alias(self, mgr):
        assert mgr.get("+guides") is not None

    def test_guide_body_mentions_browser(self, mgr):
        body = mgr.get("+guide").body.lower()
        assert "browser" in body

    def test_guide_body_mentions_categories(self, mgr):
        body = mgr.get("+guide").body.lower()
        assert "category" in body or "categories" in body

    def test_guide_see_also_includes_help(self, mgr):
        entry = mgr.get("+guide")
        see_also_lower = [s.lower() for s in entry.see_also]
        assert "+help" in see_also_lower


class TestHelpEntryMentionsGuideBrowser:
    def test_help_entry_tip_line(self, mgr):
        body = mgr.get("+help").body.lower()
        assert "guide browser" in body or "guide" in body

    def test_help_see_also_includes_guide(self, mgr):
        entry = mgr.get("+help")
        see_also_lower = [s.lower() for s in entry.see_also]
        assert "+guide" in see_also_lower


class TestPlotsFiltersHelp:
    def test_plots_entry_exists(self, mgr):
        assert mgr.get("+plots") is not None

    def test_plots_body_mentions_closed(self, mgr):
        body = mgr.get("+plots").body.lower()
        assert "closed" in body

    def test_plots_body_mentions_all(self, mgr):
        body = mgr.get("+plots").body.lower()
        assert "+plots all" in body or "plots all" in body

    def test_plots_closed_syntax_line(self, mgr):
        body = mgr.get("+plots").body
        assert "+plots closed" in body

    def test_plots_cheat_sheet_has_closed(self, mgr):
        body = mgr.get("+plots").body
        # Cheat sheet near end should reference closed filter
        assert "closed" in body[-500:]


class TestScenesFiltersHelp:
    def test_scenes_entry_exists(self, mgr):
        assert mgr.get("+scenes") is not None

    def test_scenes_body_mentions_shared(self, mgr):
        body = mgr.get("+scenes").body.lower()
        assert "shared" in body

    def test_scenes_body_mentions_player_arg(self, mgr):
        body = mgr.get("+scenes").body.lower()
        assert "<player>" in body

    def test_scenes_shared_syntax_line(self, mgr):
        body = mgr.get("+scenes").body
        assert "+scenes shared" in body

    def test_scenes_privacy_note(self, mgr):
        body = mgr.get("+scenes").body.lower()
        assert "privacy" in body or "private" in body

    def test_scenes_cheat_sheet_has_shared(self, mgr):
        body = mgr.get("+scenes").body
        assert "shared" in body[-500:]
