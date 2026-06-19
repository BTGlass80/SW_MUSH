"""
Guard: spacer quest in-game hint strings + travel command destinations.

Verifies the Guide_25 quality-pass deferred fixes:
1. engine/spacer_quest.py quest-start hint uses '+spacerquest' (not stale '+quest')
2. parser/spacer_quest_commands.py abandon confirmation uses '+spacerquest abandon confirm'
3. TravelCommand destinations are kuat/coruscant (not removed kessel/corellia)
"""
import re


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestSpacerQuestHintStrings:
    """In-game Type '...' hints must route to the live +spacerquest command."""

    def test_quest_start_hint_is_spacerquest(self):
        src = _read("engine/spacer_quest.py")
        # Quest-start message must say +spacerquest, not +quest
        assert "'+spacerquest'" in src or '"+spacerquest"' in src, (
            "engine/spacer_quest.py quest-start hint still says '+quest' "
            "instead of '+spacerquest'"
        )

    def test_no_stale_plus_quest_start_hint(self):
        src = _read("engine/spacer_quest.py")
        # The stale form must be gone (comments are OK; only live strings matter)
        code_lines = [
            ln for ln in src.splitlines()
            if not ln.strip().startswith("#")
        ]
        stale = [
            ln for ln in code_lines
            if "Type '+quest'" in ln and "+spacerquest" not in ln
        ]
        assert not stale, (
            f"Stale \"Type '+quest'\" hint still in engine/spacer_quest.py: "
            f"{stale}"
        )

    def test_abandon_confirm_hint_is_spacerquest(self):
        src = _read("parser/spacer_quest_commands.py")
        assert "+spacerquest abandon confirm" in src, (
            "Abandon-confirm hint in spacer_quest_commands.py does not say "
            "'+spacerquest abandon confirm'"
        )

    def test_no_stale_quest_abandon_hint(self):
        src = _read("parser/spacer_quest_commands.py")
        code_lines = [
            ln for ln in src.splitlines()
            if not ln.strip().startswith("#")
        ]
        stale = [
            ln for ln in code_lines
            if "+quest abandon confirm" in ln and "+spacerquest" not in ln
        ]
        assert not stale, (
            f"Stale '+quest abandon confirm' hint still present: {stale}"
        )


class TestTravelCommandDestinations:
    """TravelCommand must advertise kuat/coruscant, not removed kessel/corellia."""

    def _src(self):
        return _read("parser/spacer_quest_commands.py")

    def test_usage_string_has_kuat(self):
        assert "kuat" in self._src(), (
            "TravelCommand usage/destinations does not mention 'kuat'"
        )

    def test_usage_string_has_coruscant(self):
        assert "coruscant" in self._src(), (
            "TravelCommand usage/destinations does not mention 'coruscant'"
        )

    def test_no_kessel_in_player_facing_strings(self):
        src = self._src()
        # kessel must not appear in destination lists or usage strings
        # (it may appear in comments, but not in the dict keys or usage strings)
        for match in re.finditer(r'"kessel"', src):
            start = src.rfind("\n", 0, match.start()) + 1
            end = src.find("\n", match.end())
            line = src[start:end].strip()
            # Only flag if it's in a live string context (dict/usage), not a comment
            if not line.startswith("#"):
                raise AssertionError(
                    f"'kessel' still appears in non-comment context of "
                    f"spacer_quest_commands.py: {line!r}"
                )

    def test_no_corellia_in_player_facing_strings(self):
        src = self._src()
        for match in re.finditer(r'"corellia"', src):
            start = src.rfind("\n", 0, match.start()) + 1
            end = src.find("\n", match.end())
            line = src[start:end].strip()
            if not line.startswith("#"):
                raise AssertionError(
                    f"'corellia' still appears in non-comment context of "
                    f"spacer_quest_commands.py: {line!r}"
                )

    def test_landing_fragments_has_kuat(self):
        src = self._src()
        assert "Kuat - Main Spaceport Arrivals" in src, (
            "_LANDING_NAME_FRAGMENTS missing Kuat landing room fragment"
        )

    def test_landing_fragments_has_coruscant(self):
        src = self._src()
        assert "Coruscant - Westport Spaceport" in src, (
            "_LANDING_NAME_FRAGMENTS missing Coruscant landing room fragment"
        )

    def test_docking_fragments_has_kuat(self):
        src = self._src()
        assert "Kuat - Spaceport" in src, (
            "_DOCKING_NAME_FRAGMENTS missing Kuat spaceport fragment"
        )

    def test_docking_fragments_has_coruscant(self):
        src = self._src()
        assert "Coruscant - Westport" in src, (
            "_DOCKING_NAME_FRAGMENTS missing Coruscant Westport fragment"
        )
