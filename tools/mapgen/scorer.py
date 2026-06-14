"""tools/mapgen/scorer.py — scoring + ranking seams.

Two score sources feed the rank:
  · ai_screen_score  — from the screener (live today via Mock/Claude)
  · coord_fit_score  — how well the painting's features land on the room grid
                       (FROZEN FOR LATER — depends on coordinate exports Brian
                       is deferring; NoOpCoordinateScorer returns a neutral 50)

The CoordinateScorer PROTOCOL is final; only the real implementing class is
absent. When coord exports freeze, drop in a RealCoordinateScorer satisfying
the protocol and inject it — the harness calls only score_coordinate_fit(), so
nothing else changes.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .screen import ScreeningVerdict


@runtime_checkable
class CoordinateScorer(Protocol):
    """Score how well a painting's depicted features align with the projected
    room grid for an area. 0 = no alignment, 100 = perfect. `area_manifest` is
    the existing static/tools/manifests/<area>.json shape (bounds +
    landmarks[].fx/fy)."""

    def score_coordinate_fit(self, image_bytes: bytes,
                             area_manifest: dict) -> float:
        ...


class NoOpCoordinateScorer:
    """The deliberate freeze-for-later stub. Returns a constant neutral score so
    ranking runs on the AI-screen score alone today. Swap for a real
    implementation once coordinate exports are frozen — zero harness change."""

    NEUTRAL = 50.0

    def score_coordinate_fit(self, image_bytes: bytes,
                             area_manifest: dict) -> float:
        return self.NEUTRAL


def screen_to_score(verdict: ScreeningVerdict) -> float:
    """Map a screening verdict to a 0-100 paint-quality score. A hard fail
    (text present or off-theme) is floored low regardless of the raw score."""
    if verdict.get("has_text") or not verdict.get("on_theme", True):
        return min(float(verdict.get("score", 0.0)), 20.0)
    return float(verdict.get("score", 0.0))


class CompositeRanker:
    """Combines screen + coord scores into one rank. Weights live here, in one
    place. Default leans on screen (0.7) over coord-fit (0.3); while the coord
    scorer is the NoOp constant, screen effectively drives the ranking."""

    def __init__(self, screen_weight: float = 0.7, coord_weight: float = 0.3):
        total = screen_weight + coord_weight
        self.screen_weight = screen_weight / total
        self.coord_weight = coord_weight / total

    def composite(self, screen_score: float, coord_score: float) -> float:
        return round(
            self.screen_weight * screen_score + self.coord_weight * coord_score, 1
        )
