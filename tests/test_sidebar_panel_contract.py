# -*- coding: utf-8 -*-
"""Contract test: the SPA sidebar-panel CONSUMERS (static/client.html) must read
the same keys the server PRODUCERS emit for the mail / achievements / places HUD
sidebar messages.

Why this exists
---------------
The M3 client rewrite regressed ``handleMailStatus`` and ``handleAchievementsStatus``
to read ``data.recent`` / ``data.unlocked`` (keys the producers never send), so the
mail message-list and the *entire* achievements panel rendered empty on real data —
invisible to every other test because the panels just self-hid. The legacy client
(``static/client_legacy.html``) and both producers use ``messages`` / ``achievements``;
the M3 consumer now matches. This test pins BOTH ends of each producer/consumer
contract so a future divergence fails loudly instead of silently blanking a panel.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _slice(src, marker, length=1800):
    """Return the source window starting at ``marker`` (a function/block start)."""
    i = src.index(marker)
    return src[i:i + length]


CLIENT = _read("static", "client.html")
SESSION = _read("server", "session.py")
ACH_CMD = _read("parser", "achievement_commands.py")


# ── Mail ────────────────────────────────────────────────────────────────────
def test_mail_producer_emits_messages_with_from_name():
    body = _slice(SESSION, "async def _hud_sidebar_mail")
    assert '"type": "mail_status"' in body
    assert '"messages"' in body
    assert '"from_name"' in body
    assert '"unread"' in body


def test_mail_consumer_reads_messages_and_from_name():
    body = _slice(CLIENT, "function handleMailStatus")
    assert "data.messages" in body, "mail consumer must read the producer's `messages` key"
    assert "from_name" in body, "mail consumer must read the producer's `from_name` field"


# ── Achievements ────────────────────────────────────────────────────────────
def test_achievements_session_producer_emits_achievements_array():
    body = _slice(SESSION, "async def _hud_sidebar_achievements")
    assert '"type": "achievements_status"' in body
    assert '"achievements"' in body


def test_achievements_command_producer_emits_achievements_array():
    body = _slice(ACH_CMD, '"type": "achievements_status"')
    assert '"achievements"' in body


def test_achievements_consumer_reads_achievements_key():
    body = _slice(CLIENT, "function handleAchievementsStatus")
    assert "data.achievements" in body, (
        "achievements consumer must read the producer's `achievements` key "
        "(it previously read the never-sent `unlocked`, blanking the panel)"
    )


# ── Places ──────────────────────────────────────────────────────────────────
def test_places_producer_emits_places_with_occupants():
    body = _slice(SESSION, "async def _hud_sidebar_places")
    assert '"places"' in body
    assert '"occupants"' in body


def test_places_consumer_reads_places_and_occupants():
    body = _slice(CLIENT, "function handlePlacesStatus")
    assert "data.places" in body
    assert "occupants" in body, "places consumer should surface the producer's `occupants`"
