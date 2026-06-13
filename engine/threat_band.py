# -*- coding: utf-8 -*-
"""
engine/threat_band.py — zoned difficulty / threat bands (DIFF.1).

Per difficulty_tiers_design_v1.md. The threat band is an axis ORTHOGONAL
to the security level (engine/security.py): security answers "is
combat/PvP allowed here?", threat band answers "how dangerous are the
things you fight here?". A room has BOTH.

Four bands, with a backing numeric rating so code compares by number and
content can interpolate / add a band without renaming:

    FRONTIER (1)          — brand-new characters; the onboarding-chain
                            starting zones live here.
    SETTLED (2)           — the default mid-game band; an unmarked zone
                            resolves here (a missing tag fails toward
                            MORE caution-surfacing, not less).
    CONTESTED_MARCHES (3) — seasoned; real risk, real reward.
    WILDS (4)             — end-game; world-boss / Tier-3 anomaly country.

Storage + resolution mirror security exactly: the band lives in
``zone.properties.threat_band`` with a ``room.properties.threat_band``
override, read through the SAME ``db.get_room_property`` zone-inheritance
chain security uses. This module does NOT touch ``get_effective_security``
— it is a parallel, additive read.

DIFF.1 ships the engine axis with the default = SETTLED everywhere, so
until zones are labeled (DIFF.2) there is ZERO behavior change.
"""
from __future__ import annotations

import enum
import logging
from typing import Optional

log = logging.getLogger(__name__)


class ThreatBand(enum.Enum):
    """Zoned difficulty band. ``.rating`` is the numeric backing (1..4);
    ``.value`` is the canonical lowercase key used in YAML
    ``properties.threat_band``."""
    FRONTIER = "frontier"
    SETTLED = "settled"
    CONTESTED_MARCHES = "contested_marches"
    WILDS = "wilds"

    @property
    def rating(self) -> int:
        return _BAND_RATING[self]

    @classmethod
    def from_key(cls, key: Optional[str]) -> Optional["ThreatBand"]:
        """Parse a YAML key (case-insensitive) to a band, or None if the
        key is empty / unrecognized. Callers decide the default."""
        if not key:
            return None
        try:
            return cls(str(key).strip().lower())
        except ValueError:
            return None


_BAND_RATING: dict[ThreatBand, int] = {
    ThreatBand.FRONTIER: 1,
    ThreatBand.SETTLED: 2,
    ThreatBand.CONTESTED_MARCHES: 3,
    ThreatBand.WILDS: 4,
}

# An unmarked room/zone resolves here. SETTLED (not FRONTIER): a missing
# tag should read as "normal mid-game", so a forgotten tag on a
# dangerous zone fails toward surfacing caution rather than lulling a
# player into thinking it's a newbie area.
DEFAULT_BAND = ThreatBand.SETTLED


# ── Player-facing display ─────────────────────────────────────────────

_LABELS: dict[ThreatBand, str] = {
    ThreatBand.FRONTIER: "Frontier",
    ThreatBand.SETTLED: "Settled",
    ThreatBand.CONTESTED_MARCHES: "Contested Marches",
    ThreatBand.WILDS: "Deep Wilds",
}

# ANSI color per band (green → yellow → orange → red), mirroring the
# security_label helper's tagged style.
_ANSI: dict[ThreatBand, str] = {
    ThreatBand.FRONTIER: "\033[1;32m",          # green
    ThreatBand.SETTLED: "\033[1;33m",           # yellow
    ThreatBand.CONTESTED_MARCHES: "\033[0;33m",  # orange-ish
    ThreatBand.WILDS: "\033[1;31m",             # red
}
_RESET = "\033[0m"

# One-line "what this means" blurb for `look` / `+threat`.
_BLURBS: dict[ThreatBand, str] = {
    ThreatBand.FRONTIER:
        "Safe waters. Hostiles here are weak — a good place to learn.",
    ThreatBand.SETTLED:
        "Ordinary risk. Most of the galaxy's working life happens here.",
    ThreatBand.CONTESTED_MARCHES:
        "Seasoned country. Hostiles are dangerous and the pay reflects it.",
    ThreatBand.WILDS:
        "End-game country. The Deep Wilds will kill an unprepared hunter.",
}


def threat_label(band: ThreatBand) -> str:
    """Short ANSI-coloured tag for room/zone headers, e.g.
    ``[CONTESTED MARCHES]``."""
    return f"{_ANSI[band]}[{_LABELS[band].upper()}]{_RESET}"


def threat_name(band: ThreatBand) -> str:
    """Plain (no-ANSI) display name, e.g. 'Contested Marches'."""
    return _LABELS[band]


def threat_blurb(band: ThreatBand) -> str:
    """One-line description for `look` / `+threat`."""
    return _BLURBS[band]


def threat_color_code(band: ThreatBand) -> str:
    """Raw ANSI color prefix for the band (no reset). Consumed by the
    map renderer's overlay tint (DIFF.5)."""
    return _ANSI[band]


# ── Core resolution ───────────────────────────────────────────────────

async def get_effective_threat(room_id: int, db) -> ThreatBand:
    """Return the effective threat band for a room.

    Resolution (mirrors security's zone-inheritance via the shared
    ``get_room_property`` resolver):
      1. room.properties.threat_band
      2. zone.properties.threat_band  (and parent zones)
      3. DEFAULT_BAND (SETTLED)

    Never raises — a malformed value or missing room resolves to the
    default. Failure-tolerant by design: a difficulty read must never
    break movement / look.
    """
    try:
        raw = await db.get_room_property(room_id, "threat_band")
    except Exception as e:
        log.debug("[threat_band] get_room_property failed for room %s: "
                  "%s", room_id, e)
        return DEFAULT_BAND
    band = ThreatBand.from_key(raw)
    return band if band is not None else DEFAULT_BAND


# ── Cross-axis validation (the one coupling to security) ──────────────

def frontier_lawless_conflict(threat_key: Optional[str],
                              security_key: Optional[str]) -> bool:
    """True iff a zone/room declares BOTH the FRONTIER band AND the
    LAWLESS security level — a forbidden combination (a newbie zone must
    not be a free-fire open-PvP zone). Per design §7 this is the ONLY
    hard constraint coupling the threat and security axes; the world
    loader treats a True here as a load error.

    Both args are the raw YAML key strings (``properties.threat_band`` /
    ``properties.security``). Case-insensitive; empty/unset never
    conflicts (the band/level then resolve to their safe defaults)."""
    band = ThreatBand.from_key(threat_key)
    if band is not ThreatBand.FRONTIER:
        return False
    return (security_key or "").strip().lower() == "lawless"


# ── Reward scaling (DIFF.4 consumes this; defined here so the band ↔
#    multiplier mapping lives with the bands) ──────────────────────────

# Per design §7 — first-guess tunables; the post-launch tuning LOOP
# adjusts from telemetry. Applied through the existing adjust_credits
# faucet at reward sites (no new faucet).
_REWARD_MULTIPLIER: dict[ThreatBand, float] = {
    ThreatBand.FRONTIER: 0.6,
    ThreatBand.SETTLED: 1.0,
    ThreatBand.CONTESTED_MARCHES: 1.4,
    ThreatBand.WILDS: 2.0,
}


def reward_multiplier(band: ThreatBand) -> float:
    """Credit/rep reward multiplier for the band. A veteran farming a
    Frontier zone earns 0.6×; pushing into the Wilds earns 2.0× — so
    there's no incentive to camp newbie content, and higher bands are
    the natural income gradient."""
    return _REWARD_MULTIPLIER.get(band, 1.0)
