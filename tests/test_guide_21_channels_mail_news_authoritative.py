"""Guide_21 AUTHORITATIVE pass tests — Channels, Mail & News (Opus quality lane).

Complements the earlier draft guard (test_guide_21_channels_mail_news.py).
This file pins the *mechanical* claims the authoritative pass reconciled against
HEAD — the ones the draft did not cover — and guards the phantoms it removed.

Drifts fixed in the authoritative pass (all test-invisible before this file):
1. `comlink` was "planet-wide" — broadcast_comlink has NO planet filter; it
   reaches every online character (server/channels.py).
2. Custom frequencies were shown as decimals (`12.7`) — they are whole numbers
   1..9999 (parser/channel_commands.py TuneCommand/CommFreqCommand).
3. `page` syntax was `page <player> <message>` with a phantom `page #<id>` form —
   real syntax requires `=`; multiple targets are space-separated; alias `p`.
4. Mail multiple-recipients were shown comma-separated — compose splits on
   whitespace (`to_part.split()`), so recipients are space-separated.
5. The 8,000-char mail body cap (MAX_MAIL_BODY_LEN) was undocumented.
6. World-event effects were wrong: cantina_brawl claimed "sabacc payouts may
   double" (real effect is brawl_active); trade_boom is +25% (sell_price_mult
   1.25), not +50%; distress_signal drives a mission-board bonus, not an
   anomaly spawn; sandstorm is -3 Perception/ranged.
7. Era: `Coronet` (Corellia — removed from the playable galaxy in Guide_05's
   pass) replaced with a Clone Wars-era port.
"""
import inspect
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_21_Channels_Mail_News.md")


def _read_guide() -> str:
    with open(GUIDE_PATH, encoding="utf-8") as fh:
        return fh.read()


# ── World-event mechanical effects (pinned to EVENT_DEFS) ───────────────────────

def test_trade_boom_is_25_percent():
    """Guide §5/§6 say trade boom is +25% sell prices — pin to sell_price_mult."""
    from engine.world_events import EVENT_DEFS, EventType
    eff = EVENT_DEFS[EventType.TRADE_BOOM].mechanical_effects
    assert eff.get("sell_price_mult") == 1.25, (
        f"TRADE_BOOM sell_price_mult is {eff.get('sell_price_mult')}, not 1.25. "
        "Guide §5/§6/Scenario 5 state '+25%' / 8,000->10,000 — update both together."
    )


def test_cantina_brawl_effect_is_brawl_active_only():
    """Guide must NOT claim 'sabacc payouts may double' — effect is brawl_active."""
    from engine.world_events import EVENT_DEFS, EventType
    eff = EVENT_DEFS[EventType.CANTINA_BRAWL].mechanical_effects
    assert eff.get("brawl_active") is True, "CANTINA_BRAWL no longer sets brawl_active"
    assert not any("sabacc" in str(k).lower() for k in eff), (
        "CANTINA_BRAWL gained a sabacc effect — re-add the §5 sabacc claim if so."
    )


def test_distress_signal_drives_mission_bonus():
    """Guide §5 says distress -> mission-board bonus; pin the flag + its consumer."""
    from engine.world_events import EVENT_DEFS, EventType
    eff = EVENT_DEFS[EventType.DISTRESS_SIGNAL].mechanical_effects
    assert eff.get("distress_active") is True, "DISTRESS_SIGNAL no longer sets distress_active"
    from engine import missions
    assert hasattr(missions, "distress_mission_bonus"), (
        "engine.missions.distress_mission_bonus gone — the §5 'mission-board distress "
        "bonus' claim has no consumer; revisit the guide."
    )


def test_sandstorm_perception_and_ranged_penalty():
    """Guide §5/§6 state sandstorm = -3 Perception/-3 ranged."""
    from engine.world_events import EVENT_DEFS, EventType
    eff = EVENT_DEFS[EventType.SANDSTORM].mechanical_effects
    assert eff.get("perception_penalty") == -3 and eff.get("ranged_penalty") == -3, (
        f"SANDSTORM effects changed to {eff} — update the guide's -3/-3 claim."
    )


def test_gravel_and_sandwhirl_escalate():
    """Guide §5 says gravel storm = -2D, sandwhirl = -3D (i.e. -6 / -9 pips)."""
    from engine.world_events import EVENT_DEFS, EventType
    assert EVENT_DEFS[EventType.GRAVEL_STORM].mechanical_effects.get("perception_penalty") == -6
    assert EVENT_DEFS[EventType.SANDWHIRL].mechanical_effects.get("perception_penalty") == -9


def test_pirate_surge_triples_spawns():
    """Guide §5 says pirate surge ~3x spawns — pin pirate_spawn_mult."""
    from engine.world_events import EVENT_DEFS, EventType
    assert EVENT_DEFS[EventType.PIRATE_SURGE].mechanical_effects.get("pirate_spawn_mult") == 3.0


# ── Comlink is all-online, not planet-scoped ────────────────────────────────────

def test_comlink_has_no_planet_filter():
    """broadcast_comlink iterates every in-game session with no planet/zone filter,
    so the guide must NOT claim comlink is 'planet-wide'."""
    from server.channels import ChannelManager
    src = inspect.getsource(ChannelManager.broadcast_comlink)
    assert "session_mgr.all" in src, "broadcast_comlink no longer iterates session_mgr.all"
    # Scan the CODE only — the method docstring legitimately says "planet-wide".
    parts = src.split('"""')
    body = parts[2] if len(parts) >= 3 else src
    for token in ("planet", "zone", "room_id", "current_zone"):
        assert token not in body, (
            f"broadcast_comlink now filters on '{token}' — comlink may be planet-scoped; "
            "the guide's 'all online characters' claim may need revisiting."
        )


# ── Custom frequencies are whole numbers 1..9999 ────────────────────────────────

def test_frequency_range_1_to_9999():
    from parser.channel_commands import TuneCommand, CommFreqCommand
    for cls in (TuneCommand, CommFreqCommand):
        src = inspect.getsource(cls.execute)
        assert "9999" in src and "int(" in src, (
            f"{cls.__name__} no longer enforces an integer 1..9999 frequency — "
            "the guide teaches whole numbers 1-9999."
        )


# ── page: requires '=', alias p, no #id form ────────────────────────────────────

def test_page_requires_equals_and_alias_p():
    from parser.mux_commands import PageCommand
    assert PageCommand.key == "page"
    assert "p" in PageCommand.aliases, "page lost its `p` alias (guide §9)"
    src = inspect.getsource(PageCommand.execute)
    assert '"=" in args' in src, (
        "PageCommand no longer keys on the `=` separator — guide teaches "
        "`page <player> = <message>`."
    )


# ── Mail recipients are space-separated; body cap is 8000 ────────────────────────

def test_mail_recipients_space_separated():
    """Compose splits the to-part on whitespace, NOT commas — guide example must
    use spaces (`@mail Mara Garth = ...`)."""
    from parser.mail_commands import MailCommand
    src = inspect.getsource(MailCommand._compose_start)
    assert "to_part.split()" in src, (
        "compose no longer splits recipients on whitespace — re-check the guide's "
        "space-separated multiple-recipients claim."
    )
    assert 'split(",")' not in src, "compose now splits on commas — guide must match."


def test_mail_body_cap_is_8000():
    from parser.mail_commands import MAX_MAIL_BODY_LEN
    assert MAX_MAIL_BODY_LEN == 8000, (
        f"MAX_MAIL_BODY_LEN is {MAX_MAIL_BODY_LEN}, not 8000 — update the guide's "
        "§4/§10 body-cap figure."
    )


def test_inbox_and_sent_display_limits():
    from parser.mail_commands import MailCommand
    inbox = inspect.getsource(MailCommand._list_inbox)
    sent = inspect.getsource(MailCommand._sent)
    assert "LIMIT 30" in inbox, "inbox display cap changed from 30 — update §10"
    assert "LIMIT 20" in sent, "sent display cap changed from 20 — update §10"


# ── Guide-text phantom guards ───────────────────────────────────────────────────

def test_guide_no_decimal_frequency():
    text = _read_guide()
    assert "12.7" not in text, (
        "Guide_21 still shows the invalid decimal frequency '12.7' — "
        "frequencies are whole numbers 1-9999."
    )
    assert "1 to 9999" in text, "Guide_21 must state the 1-9999 frequency range"


def test_guide_no_phantom_page_id_form():
    text = _read_guide()
    assert "page #" not in text, (
        "Guide_21 still teaches the phantom `page #<player_id>` form — "
        "PageCommand resolves targets by name only."
    )
    assert "page <player> = <message>" in text, (
        "Guide_21 must teach `page <player> = <message>` (the `=` is required)."
    )


def test_guide_no_comma_recipients_example():
    text = _read_guide()
    assert "Mara,Garth" not in text, (
        "Guide_21 still shows comma-separated mail recipients — compose splits on "
        "whitespace; recipients are space-separated."
    )


def test_guide_no_sabacc_brawl_claim():
    text = _read_guide()
    assert "sabacc payouts may double" not in text, (
        "Guide_21 still claims a cantina brawl doubles sabacc payouts — phantom; "
        "the effect is brawl_active (more brawl encounters)."
    )


def test_guide_no_planet_wide_comlink():
    text = _read_guide()
    assert "Planet-wide IC" not in text, (
        "Guide_21 still labels comlink 'Planet-wide IC' — it reaches all online "
        "characters (galaxy-wide)."
    )


def test_guide_documents_body_cap():
    text = _read_guide()
    assert "8,000 characters" in text, (
        "Guide_21 must document the 8,000-character mail body cap (§4/§10)."
    )


def test_guide_era_clean_no_coronet():
    text = _read_guide()
    assert "Coronet" not in text, (
        "Guide_21 still references 'Coronet' (Corellia — removed from the playable "
        "galaxy in Guide_05's pass); use a Clone Wars-era port."
    )


def test_guide_version_bumped():
    text = _read_guide()
    assert "Guide Version 1.1" in text, "Guide_21 version should be 1.1 after this pass"
