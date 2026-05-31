"""
test_world_time.py — Phase-1 environment substrate (time-of-day + weather).

engine/world_time.py is the single source of truth for the two scalars the SPA
map renderer consumes (time ∈ {day,dusk,night}, weather ∈ {clear,sandstorm,…}).
Resolution: authored room→zone override, else a deterministic global day cycle
(time) / 'clear' (weather). The clock is injectable so these tests are exact.
"""
from __future__ import annotations

from engine import world_time as wt

DL = wt.DAY_LENGTH_SECONDS


def _at(frac: float) -> str:
    return wt.global_time_of_day(now=frac * DL)


class TestGlobalDayCycle:
    def test_phase_bands(self):
        assert _at(0.00) == "night"   # pre-dawn dark
        assert _at(0.25) == "dusk"    # dawn twilight (rendered as dusk)
        assert _at(0.50) == "day"
        assert _at(0.74) == "dusk"    # evening twilight
        assert _at(0.90) == "night"

    def test_cycle_wraps_across_days(self):
        assert wt.global_time_of_day(now=DL * 3 + 0.50 * DL) == "day"

    def test_custom_day_length_honored(self):
        assert wt.global_time_of_day(now=0.50 * 100, day_length_seconds=100) == "day"

    def test_every_phase_is_supported(self):
        for i in range(48):
            assert wt.global_time_of_day(now=(i / 48) * DL) in wt.TIMES_OF_DAY


class TestAuthoredOverride:
    def test_room_override_beats_cycle(self):
        # midday cycle, but the room pins night (e.g. an interior)
        assert wt.resolve_time_of_day({"time_of_day": "night"}, None, now=0.50 * DL) == "night"

    def test_zone_override_when_room_absent(self):
        assert wt.resolve_time_of_day(None, {"time_of_day": "dusk"}, now=0.50 * DL) == "dusk"

    def test_room_beats_zone(self):
        assert wt.resolve_time_of_day({"time_of_day": "day"}, {"time_of_day": "night"},
                                      now=0.90 * DL) == "day"

    def test_case_insensitive(self):
        assert wt.resolve_time_of_day({"time_of_day": "DAY"}, None, now=0.90 * DL) == "day"

    def test_invalid_override_falls_through_to_cycle(self):
        assert wt.resolve_time_of_day({"time_of_day": "banana"}, None, now=0.50 * DL) == "day"

    def test_unsupported_dawn_ignored(self):
        # client has no 'dawn' treatment yet → ignored, cycle wins
        assert wt.resolve_time_of_day({"time_of_day": "dawn"}, None, now=0.90 * DL) == "night"


class TestWeather:
    def test_default_clear(self):
        assert wt.resolve_weather(None, None) == "clear"

    def test_override(self):
        assert wt.resolve_weather({"weather": "sandstorm"}) == "sandstorm"

    def test_zone_override(self):
        assert wt.resolve_weather(None, {"weather": "overcast"}) == "overcast"

    def test_invalid_ignored(self):
        assert wt.resolve_weather({"weather": "meteors"}) == "clear"


class TestEnvironmentBlock:
    def test_shape(self):
        e = wt.resolve_environment({"time_of_day": "night", "weather": "sandstorm"})
        assert e == {"time_of_day": "night", "weather": "sandstorm"}

    def test_keys_always_present(self):
        e = wt.resolve_environment(None, None, now=0.5 * DL)
        assert set(e.keys()) == {"time_of_day", "weather"}
        assert e["time_of_day"] in wt.TIMES_OF_DAY
        assert e["weather"] in wt.WEATHERS

    def test_junk_props_are_safe(self):
        assert wt.resolve_environment("not a dict", 12345, now=0.5 * DL) == {
            "time_of_day": "day", "weather": "clear"}
