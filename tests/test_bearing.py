"""
test_bearing.py — Phase-1 bearing substrate (engine/bearing.py).

The map chevron is rotated by ``bearing`` degrees; the renderer's 0° points up
and SVG rotate() is clockwise, and the adapter reflects y-up world data into
screen space so north renders up. Hence bearing is screen-space degrees
clockwise from up: north 0, east 90, south 180, west 270 (diagonals at 45s).
Non-planar moves (up/down/in/out/named) return None so the caller keeps the
previous facing.
"""
from __future__ import annotations

from engine.bearing import bearing_for_direction, is_planar_direction


class TestCompassDegrees:
    def test_cardinals(self):
        assert bearing_for_direction("north") == 0
        assert bearing_for_direction("east") == 90
        assert bearing_for_direction("south") == 180
        assert bearing_for_direction("west") == 270

    def test_diagonals(self):
        assert bearing_for_direction("northeast") == 45
        assert bearing_for_direction("southeast") == 135
        assert bearing_for_direction("southwest") == 225
        assert bearing_for_direction("northwest") == 315

    def test_clockwise_from_up(self):
        # going clockwise the degrees strictly increase N<E<S<W
        order = [bearing_for_direction(d) for d in ("north", "east", "south", "west")]
        assert order == sorted(order) == [0, 90, 180, 270]

    def test_north_is_zero_not_dropped(self):
        # 0 is falsy — make sure it's a real value, never coerced to None
        assert bearing_for_direction("north") == 0
        assert bearing_for_direction("north") is not None


class TestInputTolerance:
    def test_abbreviations(self):
        assert bearing_for_direction("n") == 0
        assert bearing_for_direction("ne") == 45
        assert bearing_for_direction("se") == 135
        assert bearing_for_direction("w") == 270

    def test_case_and_whitespace(self):
        assert bearing_for_direction("  NORTH ") == 0
        assert bearing_for_direction("EaSt") == 90


class TestNonPlanar:
    def test_vertical_and_interior_return_none(self):
        for d in ("up", "down", "in", "out", "enter", "exit", "leave", "back"):
            assert bearing_for_direction(d) is None, d

    def test_named_exit_returns_none(self):
        assert bearing_for_direction("wreckage") is None
        assert bearing_for_direction("workshop") is None

    def test_empty_and_none(self):
        assert bearing_for_direction("") is None
        assert bearing_for_direction(None) is None

    def test_is_planar(self):
        assert is_planar_direction("west")
        assert is_planar_direction("northeast")
        assert not is_planar_direction("up")
        assert not is_planar_direction(None)
