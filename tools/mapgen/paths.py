"""tools/mapgen/paths.py — single source for the map-automation output layout.

No other mapgen module hardcodes a path; they all resolve through here. Keeps
the directory contract in one place so a relocation is a one-file edit.
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root = two levels up from this file (tools/mapgen/paths.py -> repo root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Existing, read-only inputs (produced by the gen_*_paint_brief tools + seeds).
SEEDS_DIR = PROJECT_ROOT / "static" / "tools" / "seeds"
MANIFESTS_DIR = PROJECT_ROOT / "static" / "tools" / "manifests"

# Where a SELECTED painting lands (the area_loader substrate_image seam).
MAPS_DIR = PROJECT_ROOT / "static" / "maps"

# NEW output tree: per-area, per-run batches of generated candidates + verdicts.
BATCHES_DIR = PROJECT_ROOT / "static" / "tools" / "batches"

# The committed toe-the-line boundary memory (known-good boldest phrasing per term).
TERM_BOUNDARIES_FILE = PROJECT_ROOT / "tools" / "mapgen" / "term_boundaries.json"


def seed_for(area_key: str) -> Path:
    """The tight seed PNG fed to Nano. area_key like 'tatooine.mos_eisley'."""
    return SEEDS_DIR / f"{area_key.replace('.', '_')}_tight_seed.png"


def brief_for(area_key: str) -> Path:
    """The generated paint brief (ready-to-paste Nano prompt)."""
    return SEEDS_DIR / f"{area_key.replace('.', '_')}_paint_brief.md"


def manifest_for(area_key: str) -> Path:
    """The projected-geometry manifest (bounds + landmarks[].fx/fy) the
    coordinate scorer reads once coord exports are frozen."""
    return MANIFESTS_DIR / f"{area_key}.json"


def batch_dir(area_key: str, timestamp: str) -> Path:
    """static/tools/batches/<area_key>/<timestamp>/ for one batch run."""
    return BATCHES_DIR / area_key / timestamp


def substrate_dest(slug: str) -> Path:
    """Where a chosen painting is copied: static/maps/<slug>_substrate.png."""
    return MAPS_DIR / f"{slug}_substrate.png"


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def has_google_key() -> bool:
    return bool(
        os.environ.get("GOOGLE_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
    )
