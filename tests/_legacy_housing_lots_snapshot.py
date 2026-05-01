# -*- coding: utf-8 -*-
"""
tests/_legacy_housing_lots_snapshot.py — Frozen snapshot of the
legacy `HOUSING_LOTS_*` constants from engine/housing.py prior to
their F.5b.3.c (Apr 30 2026) deletion.

Why this snapshot exists
------------------------
Several regression tests assert byte-equivalence between the
YAML-driven housing inventory (post-F.5b.3.b) and the original
in-Python constants (pre-F.5b.3.c). After F.5b.3.c deletes the
constants, those tests still need a reference point.

This module IS that reference point. It captures the exact values
that lived in `engine/housing.py` at HEAD just before F.5b.3.c
shipped, frozen in static literals.

Subsequent housing-content drops (e.g. F.5b.3.d adding a sixth GCW
T1 host) will eventually invalidate these snapshots. When that
happens, the byte-equivalence tests should be retired with a
deprecation note rather than the snapshot updated — the snapshot's
role is "frozen reference to the pre-F.5b.3.c state," not "live
spec." Update is fine for one-off corrections; deletion is the
right move when the invariant no longer applies.

This file is NOT a test module — it has no test_ functions. It's
a data-only helper imported by other test files.
"""
from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────
# T1 rentals (HOUSING_LOTS_DROP1) — 5 entries
# ──────────────────────────────────────────────────────────────────────
LEGACY_HOUSING_LOTS_DROP1 = [
    (29,  "tatooine",    "Spaceport Hotel",                "secured",   5),
    (21,  "tatooine",    "Mos Eisley Inn",                 "secured",   5),
    (60,  "nar_shaddaa", "Nar Shaddaa Promenade Hostel",   "contested", 5),
    (93,  "kessel",      "Kessel Station Barracks",        "contested", 5),
    (103, "corellia",    "Coronet City Spacers' Rest",     "secured",   5),
]

# ──────────────────────────────────────────────────────────────────────
# T3 private residences (HOUSING_LOTS_TIER3) — 7 entries
# ──────────────────────────────────────────────────────────────────────
LEGACY_HOUSING_LOTS_TIER3 = [
    (11,  "tatooine",    "South End Residences",             "secured",   4),
    (42,  "tatooine",    "Outskirts Homesteads",             "contested", 3),
    (61,  "nar_shaddaa", "Corellian Sector Apartments",      "contested", 4),
    (69,  "nar_shaddaa", "Undercity Hab-Block",              "lawless",   3),
    (86,  "kessel",      "Station Habitat Ring",             "contested", 2),
    (104, "corellia",    "Residential Quarter",              "secured",   4),
    (114, "corellia",    "Old Quarter Townhouses",           "contested", 3),
]

# ──────────────────────────────────────────────────────────────────────
# T4 shopfronts (HOUSING_LOTS_TIER4) — 6 entries
# ──────────────────────────────────────────────────────────────────────
LEGACY_HOUSING_LOTS_TIER4 = [
    (8,   "tatooine",    "Market Row Stalls",          "contested", 4),
    (11,  "tatooine",    "Spaceport Commercial Strip", "secured",   3),
    (46,  "nar_shaddaa", "Promenade Market",           "contested", 4),
    (69,  "nar_shaddaa", "Undercity Black Market",     "lawless",   2),
    (86,  "kessel",      "Station Bazaar",             "contested", 2),
    (104, "corellia",    "Commercial Quarter",         "secured",   4),
]

# ──────────────────────────────────────────────────────────────────────
# T5 organization HQs (HOUSING_LOTS_TIER5) — 6 entries
# ──────────────────────────────────────────────────────────────────────
LEGACY_HOUSING_LOTS_TIER5 = [
    (42,  "tatooine",    "Outskirts Compound",      "contested", 2),
    (47,  "tatooine",    "Abandoned Compound",      "lawless",   1),
    (61,  "nar_shaddaa", "Corellian Sector Block",  "contested", 2),
    (69,  "nar_shaddaa", "Undercity Stronghold",    "lawless",   2),
    (86,  "kessel",      "Station Industrial Ring", "contested", 1),
    (114, "corellia",    "Old Quarter Compound",    "contested", 2),
]
