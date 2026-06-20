"""Guide_21 quality-pass tests — Channels, Mail & News.

Cross-checks every quantified/mechanical claim in data/guides/Guide_21_Channels_Mail_News.md
against HEAD (engine/world_events.py, server/channels.py, parser/channel_commands.py,
parser/mail_commands.py, parser/news_commands.py, parser/builtin_commands.py).

Drifts fixed in this pass (all test-invisible prior to these tests):
1. OOC display format was `<OOC>` — real format is `[OOC]` (fmt_ooc in server/channels.py).
2. Comlink display format was `<COMLINK>` — real format is `[Comlink]`.
3. Fcomm display format was `<FCOMM Republic>` — real format is `[Republic]` (label from FACTION_LABELS).
4. Event-type count was "12" — is 17 (GRAVEL_STORM/SANDWHIRL/INTELLIGENCE_THAW/SPICE_DEMAND/FLOOD
   added in Lane E2a/D since guide was authored).
5. Guide named a type "CIS propaganda" — the enum is `SEPARATIST_AGITATION` / label "Separatist".
6. §10 faction prefix list said "Republic / CIS / Hutt" — CIS label is "Separatist" per FACTION_LABELS.
"""
import importlib.util
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_21_Channels_Mail_News.md")


def _read_guide() -> str:
    with open(GUIDE_PATH, encoding="utf-8") as fh:
        return fh.read()


# ── Registry fixture ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def reg():
    spec = importlib.util.spec_from_file_location(
        "_reg_for_g21",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Channel commands resolve in registry ──────────────────────────────────────

@pytest.mark.parametrize("form", [
    "+who",
    "ooc",
    "newbie",
    "oocsay",
    "comlink",
    "cl",
    "fcomm",
    "fc",
    "commfreq",
    "cf",
    "tune",
    "untune",
    "+freqs",
    "freqs",
    "+channels",
    "channels",
    "+news",
    "news",
])
def test_guide21_channel_command_resolves(reg, form):
    """Every command form Guide_21 teaches must resolve in the live registry."""
    cmd = reg.get(form)
    assert cmd is not None, (
        f"Guide_21 teaches `{form}` but it does not resolve in the live registry. "
        "Either the command was renamed or the guide is teaching a phantom."
    )


# ── @mail switches ─────────────────────────────────────────────────────────────

def test_mail_command_switches():
    """All @mail switches the guide documents must be live in MailCommand.valid_switches."""
    from parser.mail_commands import MailCommand
    live = set(MailCommand.valid_switches)
    guide_switches = {"read", "reply", "forward", "delete", "purge",
                      "send", "unread", "sent", "quick"}
    missing = guide_switches - live
    assert not missing, (
        f"Guide_21 documents @mail/{missing} but these switches are not in "
        "MailCommand.valid_switches — guide teaches phantom switches."
    )


# ── +news implementation ───────────────────────────────────────────────────────

def test_news_command_key():
    from parser.news_commands import NewsCommand
    assert NewsCommand.key == "+news", "NewsCommand key changed — guide teaches `+news`"


def test_news_alias_news():
    from parser.news_commands import NewsCommand
    assert "news" in NewsCommand.aliases, (
        "Guide_21 teaches `news` as a +news alias but it is absent from NewsCommand.aliases"
    )


def test_news_bulletin_limit_is_10():
    """Guide says 'the 10 most recent world events' — confirmed against limit= in NewsCommand."""
    import inspect
    from parser.news_commands import NewsCommand
    src = inspect.getsource(NewsCommand.execute)
    assert "limit=10" in src, (
        "NewsCommand.execute no longer uses limit=10 — guide's '10 most recent events' claim "
        "may be wrong. Verify and update the guide and this test."
    )


def test_news_header_text():
    """Guide shows the '=== Mos Eisley Galactic News Network ===' header."""
    from parser import news_commands
    src = open(os.path.join(PROJECT_ROOT, "parser", "news_commands.py"),
               encoding="utf-8").read()
    assert "Mos Eisley Galactic News Network" in src, (
        "News header no longer contains 'Mos Eisley Galactic News Network' — "
        "update the guide's worked example in §5."
    )


# ── World event types ──────────────────────────────────────────────────────────

def test_event_type_count_is_17():
    """Guide now says '17 standard event types' — must match VALID_EVENT_TYPES count."""
    from engine.world_events import VALID_EVENT_TYPES
    assert len(VALID_EVENT_TYPES) == 17, (
        f"VALID_EVENT_TYPES has {len(VALID_EVENT_TYPES)} entries but guide says 17. "
        "Update the guide's event-type list and this assertion."
    )


@pytest.mark.parametrize("event_type", [
    "security_crackdown",
    "security_checkpoint",
    "bounty_surge",
    "merchant_arrival",
    "sandstorm",
    "gravel_storm",
    "sandwhirl",
    "cantina_brawl",
    "distress_signal",
    "pirate_surge",
    "hutt_auction",
    "krayt_sighting",
    "separatist_agitation",
    "trade_boom",
    "intelligence_thaw",
    "spice_demand",
    "flood",
])
def test_event_type_exists(event_type):
    from engine.world_events import VALID_EVENT_TYPES
    assert event_type in VALID_EVENT_TYPES, (
        f"Event type '{event_type}' listed in guide is not in VALID_EVENT_TYPES — "
        "either a rename happened or the guide list is wrong."
    )


def test_no_cis_propaganda_event_type():
    """Guide used to say 'CIS propaganda'; the real type is separatist_agitation."""
    from engine.world_events import VALID_EVENT_TYPES
    assert "cis_propaganda" not in VALID_EVENT_TYPES, (
        "'cis_propaganda' appeared in VALID_EVENT_TYPES — the guide still references "
        "this phantom name; update to 'separatist_agitation'."
    )


# ── Display format correctness ─────────────────────────────────────────────────

def test_ooc_display_format():
    """Guide shows '[OOC] Name: msg' — must match fmt_ooc output (no angle brackets)."""
    from server.channels import fmt_ooc
    rendered = fmt_ooc("Trill", "test")
    assert "[OOC]" in rendered, "fmt_ooc no longer renders '[OOC]' prefix"
    assert "<OOC>" not in rendered, "fmt_ooc reverted to angle-bracket style"


def test_comlink_display_format():
    """Guide shows '[Comlink] Name: msg' — must match fmt_comlink."""
    from server.channels import fmt_comlink
    rendered = fmt_comlink("Trill", "test")
    assert "[Comlink]" in rendered, "fmt_comlink no longer renders '[Comlink]' prefix"
    assert "<COMLINK>" not in rendered, "fmt_comlink reverted to angle-bracket style"


def test_fcomm_display_format_republic():
    """Guide shows '[Republic] Name: msg' for republic fcomm — must match fmt_fcomm."""
    from server.channels import fmt_fcomm
    rendered = fmt_fcomm("Trill", "republic", "test")
    assert "[Republic]" in rendered, (
        "fmt_fcomm('republic') no longer renders '[Republic]' — guide example is wrong"
    )
    assert "<FCOMM" not in rendered, "fmt_fcomm reverted to angle-bracket style"


def test_fcomm_cis_label_is_separatist():
    """Guide §10 says CIS fcomm label is 'Separatist' (not 'CIS')."""
    from server.channels import FACTION_LABELS
    label = FACTION_LABELS.get("cis")
    assert label == "Separatist", (
        f"FACTION_LABELS['cis'] is {label!r}, expected 'Separatist'. "
        "Guide §10 faction-prefix table must reflect the live label."
    )


# ── Guide text correctness ─────────────────────────────────────────────────────

def test_guide_uses_square_bracket_ooc():
    """Guide display example must use [OOC] not <OOC>."""
    text = _read_guide()
    assert "<OOC>" not in text, (
        "Guide_21 still shows '<OOC>' display format (old style). "
        "Should be '[OOC]' to match fmt_ooc."
    )
    assert "[OOC] Trill" in text, (
        "Guide_21 worked example should use '[OOC] Trill:' format"
    )


def test_guide_uses_square_bracket_comlink():
    """Guide display example must use [Comlink] not <COMLINK>."""
    text = _read_guide()
    assert "<COMLINK>" not in text, (
        "Guide_21 still shows '<COMLINK>' display format (old style). "
        "Should be '[Comlink]' to match fmt_comlink."
    )


def test_guide_uses_square_bracket_fcomm():
    """Guide display example must use [Republic] not <FCOMM Republic>."""
    text = _read_guide()
    assert "<FCOMM" not in text, (
        "Guide_21 still shows '<FCOMM ...>' display format (old style). "
        "Should be '[Republic]' etc. to match fmt_fcomm."
    )
    assert "[Republic] Trill" in text, (
        "Guide_21 fcomm example should use '[Republic] Trill:' format"
    )


def test_guide_event_count_says_17():
    """Guide §5 must say '17 standard event types' after the count update."""
    text = _read_guide()
    assert "17 standard event types" in text, (
        "Guide_21 §5 must state '17 standard event types' — "
        "was '12' before this quality pass."
    )


def test_guide_says_separatist_not_cis_propaganda():
    """Guide must use 'separatist agitation' not 'CIS propaganda' for that event type."""
    text = _read_guide()
    assert "CIS propaganda" not in text, (
        "Guide_21 still says 'CIS propaganda' — the enum is 'separatist_agitation'"
    )
    assert "separatist agitation" in text, (
        "Guide_21 must use 'separatist agitation' after the CIS-propaganda rename fix"
    )


def test_guide_faction_prefix_says_separatist():
    """Guide §10 faction-prefix row must say 'Separatist' not 'CIS'."""
    text = _read_guide()
    assert "Republic / CIS / Hutt" not in text, (
        "Guide_21 §10 still says 'Republic / CIS / Hutt' — "
        "CIS fcomm label is 'Separatist', not 'CIS'"
    )
    assert "Separatist" in text, (
        "Guide_21 §10 should include 'Separatist' in the faction prefix list"
    )


def test_guide_teaches_plus_who():
    """Guide must teach `+who` (canonical post-rework form), not bare `who`."""
    text = _read_guide()
    assert "`+who`" in text, "Guide_21 must teach the canonical `+who` command"
    # Bare `who` should NOT appear as a command form (only as prose "who's online" etc.)
    bare_who = re.compile(r"`who\b")
    assert not bare_who.search(text), (
        "Guide_21 still contains bare `who` command form — "
        "deprecated in DROP 1 (command_syntax_rework); canonical is `+who`"
    )


def test_guide_layer_count_says_nine():
    """Guide §1 and §10 both claim 9 communication layers."""
    text = _read_guide()
    assert "Nine communication layers" in text, (
        "Guide_21 §1 should say 'Nine communication layers'"
    )
    assert "Communication layers | 9" in text, (
        "Guide_21 §10 Numbers At A Glance should show '9' for Communication layers"
    )


def test_plus_scene_start_is_real():
    """Guide Scenario 1 mentions +scene/start — must be a real switch."""
    from parser.scene_commands import SceneCommand
    import inspect
    src = inspect.getsource(SceneCommand.execute)
    assert "start" in src, (
        "`+scene/start` referenced in Guide_21 Scenario 1 appears to be a phantom switch. "
        "Verify SceneCommand handles the 'start' switch."
    )
