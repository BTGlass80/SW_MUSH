"""tools/mapgen — automated map-painting framework (batch generate -> screen ->
rank -> select), built per docs/design/map_automation_framework_v1.md.

Runs fully OFFLINE today on Mock/NoOp collaborators; the live Gemini client,
Claude-vision screener, and real coordinate scorer drop in behind fixed seams
when keys / frozen coordinates are available. Adding this package does not
affect the existing path-inserted sibling scripts under tools/ (tools/ has no
__init__.py of its own).
"""
from .nano_client import (
    NanoClient, MockNanoClient, GenResult, create_nano_client,
)
from .term_substitutions import (
    TERM_LADDERS, apply_term_substitutions, terms_present, phrase_for,
    starting_rungs, load_boundaries, record_boundary,
)
from .screen import (
    screen_image, MockScreener, ScreeningVerdict, parse_area_brief,
)
from .scorer import (
    CoordinateScorer, NoOpCoordinateScorer, CompositeRanker, screen_to_score,
)
from .batch import (
    BatchOrchestrator, BatchResult, CandidateArtifact, select_painting,
)

__all__ = [
    "NanoClient", "MockNanoClient", "GenResult", "create_nano_client",
    "TERM_LADDERS", "apply_term_substitutions", "terms_present", "phrase_for",
    "starting_rungs", "load_boundaries", "record_boundary",
    "screen_image", "MockScreener", "ScreeningVerdict", "parse_area_brief",
    "CoordinateScorer", "NoOpCoordinateScorer", "CompositeRanker",
    "screen_to_score",
    "BatchOrchestrator", "BatchResult", "CandidateArtifact", "select_painting",
]
