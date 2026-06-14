"""tools/mapgen/term_substitutions.py — IP-safe term mapping with a "toe the line"
ladder, single source for both the brief generators and the batch driver.

THE PROBLEM
-----------
Nano/Gemini filters franchise terms and OCRs the input image, so a brief that
says "Tatooine landspeeder" gets refused or silently drifts off-theme (the
canonical failure: ocean-type ships painted into a desert because a blocked
term fell back to whatever the model free-associated). The fix is a CONTROLLED
substitution: replace each franchise term with a deliberate, on-theme,
IP-neutral phrase.

TOE THE LINE (Brian, 2026-06-13)
--------------------------------
We want the painting as close to Star Wars authenticity as the content filter
allows. So each term is not a single phrase but a LADDER of phrasings, rung 0
= boldest (most SW-authentic), rising rung index = safer/more generic. The
batch driver starts BOLD (rung 0) and steps DOWN on a refusal or an off-theme
screen ("start bold, auto-back-off"), recording the boldest rung that worked.

That known-good boundary persists in a committed JSON file
(`term_boundaries.json`) so a later map starts from the line instead of
re-discovering it. This module owns the ladder, the substitution application,
and the boundary read/write. The loop that DRIVES it lives in batch.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths


# ── The substitution ladders ──────────────────────────────────────────────
# Each franchise term maps to a list of phrasings, BOLDEST FIRST. Rung 0 is the
# most Star-Wars-authentic phrasing we'd try; the last rung is the safe floor
# (what the current briefs already use). The batch loop walks down on refusal.
#
# Seeded from the IP-safe vocab already living in the brief generators
# (gen_city_paint_brief ICON_VISUAL, paint_brief_common MASTER_PROMPT). Expand
# this data freely — adding terms/rungs is data-only, no interface change.
TERM_LADDERS: dict[str, list[str]] = {
    "landspeeder": [
        "repulsorlift speeder, desert-worn",            # rung 0 — boldest
        "open-cockpit hovercraft, hot-rod styling",
        "open-cockpit desert hovercraft",               # safe floor
    ],
    "speeder bike": [
        "single-rider repulsor bike",
        "open-frame hovercycle",
        "small open hovercraft",
    ],
    "moisture vaporator": [
        "moisture-condenser tower, desert farmstead",
        "tall thin condenser spire",
        "slender utility tower",
    ],
    "cantina": [
        "spacers' cantina, low and shadowed",
        "rough offworld tavern",
        "low windowless drinking hall",
    ],
    "Hutt palace": [
        "crime-lord's fortified desert palace",
        "warlord's walled compound",
        "large fortified stone compound",
    ],
    "moisture farm": [
        "desert moisture farmstead, sunken homestead",
        "sunken desert homestead",
        "low desert dwelling cluster",
    ],
    "starship": [
        "battered freighter hull",
        "weathered cargo craft",
        "large weathered vessel",
    ],
    "droid": [
        "worn utility automaton",
        "battered service machine",
        "small mechanical unit",
    ],
    "Coruscant": [
        "endless planet-wide city, canyon streets",
        "vast layered megacity",
        "dense planet-spanning urban sprawl",
    ],
    # Era-clean guards (these must NEVER reach the painting prompt).
    "Imperial": ["authoritarian garrison", "hard military", "stern official"],
    "Empire": ["the central authority", "the ruling power", "the governing state"],
    "Rebel": ["insurgent", "irregular", "underground"],
    "TIE fighter": ["wedge-winged patrol craft", "angular patrol flyer", "small patrol craft"],
    "stormtrooper": ["armored trooper", "uniformed guard", "patrol soldier"],
    "lightsaber": ["glowing energy blade", "luminous blade", "bright energy weapon"],
    "Jedi": ["robed warrior-monk", "robed adept", "robed wanderer"],
}


def boldest_rung_count(term: str) -> int:
    """How many rungs a term's ladder has (1 if not laddered)."""
    return len(TERM_LADDERS.get(term, [term]))


def phrase_for(term: str, rung: int) -> str:
    """The phrasing for `term` at ladder `rung` (clamped to the safe floor)."""
    ladder = TERM_LADDERS.get(term)
    if not ladder:
        return term
    rung = max(0, min(rung, len(ladder) - 1))
    return ladder[rung]


# Whole-word, case-insensitive, longest-term-first so "speeder bike" beats
# "speeder". Idempotent: we replace the FRANCHISE term, never the neutral
# phrase, so re-running on substituted text is a no-op.
def _compiled_terms() -> list[str]:
    return sorted(TERM_LADDERS.keys(), key=len, reverse=True)


def apply_term_substitutions(brief_text: str,
                             rungs: dict[str, int] | None = None) -> str:
    """Replace every franchise term in `brief_text` with its on-theme phrasing.

    `rungs` selects the ladder rung per term (default: the safe floor, i.e. the
    last rung — matching today's conservative brief behavior). The batch
    toe-the-line loop passes bolder rungs and steps them down on refusal.
    """
    out = brief_text
    for term in _compiled_terms():
        ladder = TERM_LADDERS[term]
        if rungs is not None and term in rungs:
            rung = rungs[term]
        else:
            rung = len(ladder) - 1  # safe floor by default
        replacement = phrase_for(term, rung)
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        out = pattern.sub(replacement, out)
    return out


def terms_present(brief_text: str) -> list[str]:
    """Which laddered franchise terms actually appear in this brief (so the
    loop only iterates the terms that matter for this area)."""
    present = []
    for term in _compiled_terms():
        if re.search(r"\b" + re.escape(term) + r"\b", brief_text, re.IGNORECASE):
            present.append(term)
    return present


# ── Toe-the-line boundary memory (committed term_boundaries.json) ──────────
# Records the known-good BOLDEST rung per term + the screen score that
# justified it, so later maps start from the line.

def load_boundaries(path: Path | None = None) -> dict:
    p = path or paths.TERM_BOUNDARIES_FILE
    if not p.exists():
        return {"_schema": 1, "terms": {}}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("terms", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"_schema": 1, "terms": {}}


def starting_rungs(brief_text: str, path: Path | None = None) -> dict[str, int]:
    """The rung to START each present term at. If a term has a recorded
    boundary, start there (the known line); otherwise start BOLD (rung 0) per
    the 'start bold, auto-back-off' policy."""
    boundaries = load_boundaries(path).get("terms", {})
    rungs = {}
    for term in terms_present(brief_text):
        rec = boundaries.get(term)
        rungs[term] = int(rec["rung"]) if rec and "rung" in rec else 0
    return rungs


def record_boundary(term: str, rung: int, score: float, *,
                    verified: str = "", path: Path | None = None) -> None:
    """Persist that `term` at `rung` is the boldest that cleared the filter +
    screened on-theme (score). Only tightens toward bolder (lower rung) when a
    new bolder rung is proven, or updates the score for the same rung.

    `verified` is a caller-supplied stamp (e.g. a date) — this module never
    calls Date.now()-style nondeterminism itself.
    """
    p = path or paths.TERM_BOUNDARIES_FILE
    data = load_boundaries(p)
    rec = data["terms"].get(term)
    if rec is None or int(rung) <= int(rec.get("rung", 99)):
        data["terms"][term] = {
            "rung": int(rung),
            "phrase": phrase_for(term, rung),
            "last_score": round(float(score), 1),
            "verified": verified,
        }
        paths.ensure_dir(p.parent)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
