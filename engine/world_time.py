"""
engine/world_time.py — Phase-1 world-environment substrate
===========================================================
Single source of truth for the two environment scalars the SPA map renderer
consumes: ``time_of_day`` and ``weather``. The composition engine already
threads ``time`` (``day`` | ``dusk`` | ``night``) and ``weather``
(``clear`` | ``sandstorm``) into ``Tier1aBody`` and friends, but the client
hardcoded them (``time:'day', weather:'clear'`` with "derive from server"
TODOs). This module supplies the real values; the server emits them on every
HUD push as ``hud["environment"]`` and the client reads them at render time.

This is the *substrate* (the seam + a minimal living source), not the whole
weather/clock simulation. Furniture and player-bearing are separate later
substrate drops; this one covers time-of-day + weather only.

Resolution order — time_of_day
-------------------------------
  1. Authored override on the room ``properties.time_of_day`` (then the zone's),
     so enclosed/underground spaces can pin ``night`` and a fixed-lit set can
     pin ``day``. World data carries these as plain strings.
  2. A global wall-clock day cycle — a living ``day → dusk → night`` loop. The
     real-seconds-per-in-game-day is configurable (``DAY_LENGTH_SECONDS``); the
     clock is injectable (``now``) so tests are fully deterministic.

Resolution order — weather
---------------------------
  1. Authored override (room ``properties.weather`` → zone).
  2. ``clear`` — there is no dynamic weather system yet (a future drop). This
     establishes the protocol field so that drop needs NO client/protocol
     change, only a new source behind ``resolve_weather``.

Both results are clamped to the renderer's supported sets, so a typo in world
data can never push an unknown token to the SVG layers (it falls through to the
cycle / default instead).
"""
from __future__ import annotations

import time as _time
from typing import Optional

# The client renderer supports exactly these tokens today (see
# m3_composition_engine.OV_TimeOfDay / OV_TwinSunShadows and
# m3_assets_landmarks). 'dawn' is intentionally folded into 'dusk' by the cycle
# below until the renderer grows a distinct dawn treatment.
TIMES_OF_DAY = ("day", "dusk", "night")
# 'clear' + 'sandstorm' are rendered today (OV_Sandstorm); the rest are reserved
# so authored data can use them ahead of the renderer without being dropped.
WEATHERS = ("clear", "sandstorm", "overcast", "rain")

# One full in-game day in real seconds. Default: 2 real hours per game-day.
DAY_LENGTH_SECONDS = 2 * 60 * 60

# Day-cycle phase bands as fractions of the cycle [0.0, 1.0). Two twilight
# bands (morning + evening) both render as 'dusk' until the client has 'dawn'.
#   night  [0.00, 0.22)   pre-dawn dark
#   dusk   [0.22, 0.30)   dawn twilight
#   day    [0.30, 0.70)   full day
#   dusk   [0.70, 0.78)   evening twilight
#   night  [0.78, 1.00)   night
_CYCLE_BANDS = (
    (0.22, "night"),
    (0.30, "dusk"),
    (0.70, "day"),
    (0.78, "dusk"),
    (1.00, "night"),
)


def global_time_of_day(now: Optional[float] = None,
                        day_length_seconds: Optional[float] = None) -> str:
    """The global day-cycle phase for ``now`` (epoch seconds; defaults to
    wall-clock). Deterministic for a given ``now`` — pass it in tests."""
    if now is None:
        now = _time.time()
    span = day_length_seconds if day_length_seconds and day_length_seconds > 0 else DAY_LENGTH_SECONDS
    frac = (now % span) / span
    for upper, name in _CYCLE_BANDS:
        if frac < upper:
            return name
    return "night"


def _authored(props_chain, key: str, valid) -> Optional[str]:
    """First valid string value of ``key`` across the props dicts in order."""
    for props in props_chain:
        if isinstance(props, dict):
            v = props.get(key)
            if isinstance(v, str) and v.strip().lower() in valid:
                return v.strip().lower()
    return None


def resolve_time_of_day(room_props: Optional[dict] = None,
                        zone_props: Optional[dict] = None,
                        now: Optional[float] = None,
                        day_length_seconds: Optional[float] = None) -> str:
    """Authored room→zone override, else the global day cycle. Always one of
    ``TIMES_OF_DAY``."""
    authored = _authored((room_props, zone_props), "time_of_day", TIMES_OF_DAY)
    if authored is not None:
        return authored
    return global_time_of_day(now, day_length_seconds)


def resolve_weather(room_props: Optional[dict] = None,
                    zone_props: Optional[dict] = None) -> str:
    """Authored room→zone override, else ``clear`` (no dynamic system yet).
    Always one of ``WEATHERS``."""
    authored = _authored((room_props, zone_props), "weather", WEATHERS)
    return authored if authored is not None else "clear"


def resolve_environment(room_props: Optional[dict] = None,
                        zone_props: Optional[dict] = None,
                        now: Optional[float] = None,
                        day_length_seconds: Optional[float] = None) -> dict:
    """The full environment block emitted on the HUD:
    ``{"time_of_day": ..., "weather": ...}``. Never raises on bad input."""
    return {
        "time_of_day": resolve_time_of_day(room_props, zone_props, now, day_length_seconds),
        "weather": resolve_weather(room_props, zone_props),
    }
