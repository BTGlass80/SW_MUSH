# -*- coding: utf-8 -*-
"""
tests/test_director_event_dispatch.py — repair of the Director's world-event
dispatch (pre-existing latent bugs found during Lane E2a).

Two guaranteed-TypeError/AttributeError call sites in engine/director.py meant
EVERY Director-fired narrative event was silently dead (the only working path was
the world-event timer):

  1. _run_api_turn (~860) awaited a 6-arg async form
        wem.activate_event(db, session_mgr, event_type=..., zones_affected=...,
                            duration_minutes=..., headline=..., source="director")
     but activate_event is SYNC (event_type, zones, duration_minutes, headline)
     and does NOT broadcast.
  2. the era-milestone path (~1422) called a NON-EXISTENT wem.create_event(...).

Plus the broadcast bug they shared:
  3. _broadcast_activation referenced edef.effect_text, not a field on EventDef
     -> swallowed AttributeError -> the web-client structured "effects" payload
     never sent (Telnet worked).

This suite proves the corrected call CONTRACT (the exact call the Director now
makes) + the effect_text field + a real broadcast, and structurally pins that the
broken forms are gone. The full Director Faction Turn is integration/Windows-gated
(it needs the AI provider + populated DB; its suites don't run in the bare sandbox).
"""
from __future__ import annotations
import os
import json
import pytest

from engine.world_events import (
    get_world_event_manager, EventType, EVENT_DEFS, ActiveEvent,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _src(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _reset(wem):
    """Clear the world-event singleton so cooldowns don't block a test activation."""
    wem._active = []
    wem._last_event_time = 0.0
    wem._type_last_fired = {}


# ── EventDef.effect_text (root of bug #3) ───────────────────────────────────

def test_eventdef_has_effect_text_field_with_default():
    # Trailing defaulted field: events that don't set it get "".
    assert EVENT_DEFS[EventType.SECURITY_CRACKDOWN].effect_text == ""
    # Storms carry a player-facing summary.
    assert EVENT_DEFS[EventType.SANDSTORM].effect_text == "Perception \u22121D, ranged fire \u22121D"
    assert EVENT_DEFS[EventType.GRAVEL_STORM].effect_text == "Perception \u22122D, ranged fire \u22122D"
    assert EVENT_DEFS[EventType.SANDWHIRL].effect_text == "Perception \u22123D, ranged fire \u22123D"


# ── The corrected call CONTRACT the Director now uses ───────────────────────

def test_activate_event_accepts_keyword_signature_director_uses():
    """director.py now calls activate_event(evt_type, zones=, duration_minutes=,
    headline=) synchronously. Prove that exact form returns an ActiveEvent."""
    wem = get_world_event_manager()
    saved = list(wem._active)
    try:
        _reset(wem)
        ev = wem.activate_event(
            "sandstorm",
            zones=["streets"],
            duration_minutes=30,
            headline="Test Storm",
        )
        assert isinstance(ev, ActiveEvent)
        assert ev.event_type == EventType.SANDSTORM
        assert ev.headline == "Test Storm"
        # the old broken forms would have raised TypeError before returning
    finally:
        wem._active = saved


@pytest.mark.asyncio
async def test_broadcast_activation_sends_web_effects_without_swallowing():
    """bug #3 fixed: _broadcast_activation reads edef.effect_text (now a real
    field) and the web 'effects' payload sends; Telnet broadcast still fires."""
    wem = get_world_event_manager()
    saved = list(wem._active)

    class _WS:
        is_in_game = True
        class _P:
            value = "websocket"
        protocol = _P()
        def __init__(self):
            self.sent = []
        async def _send(self, s):
            self.sent.append(json.loads(s))

    class _Mgr:
        def __init__(self):
            self.ws = _WS()
            self.broadcasts = []
        @property
        def all(self):
            return [self.ws]
        async def broadcast(self, text):
            self.broadcasts.append(text)

    try:
        _reset(wem)
        ev = wem.activate_event("sandwhirl", zones=["streets"],
                                duration_minutes=5, headline="Sandwhirl")
        mgr = _Mgr()
        await wem._broadcast_activation(ev, mgr)
        assert mgr.broadcasts, "Telnet broadcast did not fire"
        assert mgr.ws.sent, "web structured event did not send (effect_text swallowed?)"
        payload = mgr.ws.sent[0]
        assert payload["type"] == "world_event" and payload["action"] == "start"
        assert payload["effects"] == "Perception \u22123D, ranged fire \u22123D"
    finally:
        wem._active = saved


# ── Structural pins: the broken forms are gone, the correct forms present ────

def test_director_narrative_call_site_fixed():
    src = _src("engine/director.py")
    # broken forms must be gone (each specific to the broken activate_event call)
    assert "await wem.activate_event(" not in src, "still awaiting a sync method"
    assert "event_type=evt_type" not in src, "still passing event_type= kwarg"
    assert "zones_affected=zones" not in src, "still passing zones_affected= kwarg"
    assert "wem.create_event(" not in src, "still calling non-existent create_event"
    # the broken call passed db/session_mgr positionally to activate_event
    assert "activate_event(\n                        db, session_mgr" not in src, \
        "still passing db/session_mgr to activate_event"
    # corrected forms present
    assert "wem.activate_event(" in src
    assert "zones=zones," in src
    assert "_broadcast_activation(activated, session_mgr)" in src, \
        "Director-fired events must broadcast (timer path does)"


def test_director_era_call_site_fixed():
    src = _src("engine/director.py")
    assert "zones=list(VALID_ZONES)" in src, "era milestone path not converted to activate_event"
