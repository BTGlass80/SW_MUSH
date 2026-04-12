# -*- coding: utf-8 -*-
"""
engine/ships_log.py — Ship's Log & Discovery System (Drop 19)

Persistent per-character record of space accomplishments.
Stored in character attributes JSON under "ships_log" key.

Milestone rewards use existing CPEngine tick system.
Titles are stored in ships_log["titles_earned"] and displayed
on +sheet and who list.
"""

from __future__ import annotations
import json
import logging

log = logging.getLogger(__name__)

# ── Log structure ─────────────────────────────────────────────────────────────

DEFAULT_LOG: dict = {
    "zones_visited":       [],   # zone IDs visited
    "ships_scanned":       [],   # ship template keys scanned
    "anomalies_resolved":  [],   # anomaly type strings resolved
    "planets_landed":      [],   # planet keys docked at
    "pirate_kills":        0,
    "smuggling_runs":      0,
    "trade_runs":          0,
    "bounties_collected":  0,   # profession chain entry gate
    "missions_complete":   0,   # profession chain entry gate
    "crafting_complete":   0,   # profession chain entry gate
    "titles_earned":       [],
}

# ── Milestone definitions ─────────────────────────────────────────────────────

MILESTONES: list[dict] = [
    # Zones visited
    {"category": "zones_visited",      "threshold": 5,  "cp": 10, "title": None,              "msg": "Visited 5 space zones."},
    {"category": "zones_visited",      "threshold": 10, "cp": 25, "title": None,              "msg": "Veteran spacer — 10 zones explored."},
    {"category": "zones_visited",      "threshold": 16, "cp": 50, "title": "Explorer",        "msg": "All 16 zones charted. The galaxy is yours."},
    # Ships scanned
    {"category": "ships_scanned",      "threshold": 5,  "cp": 10, "title": None,              "msg": "Identified 5 ship types."},
    {"category": "ships_scanned",      "threshold": 10, "cp": 10, "title": None,              "msg": "10 ship classes in the log."},
    {"category": "ships_scanned",      "threshold": 19, "cp": 30, "title": "Spotter",         "msg": "All 19 ship types identified. Nothing surprises you."},
    # Anomalies resolved
    {"category": "anomalies_resolved", "threshold": 4,  "cp": 15, "title": None,              "msg": "4 anomaly types resolved."},
    {"category": "anomalies_resolved", "threshold": 7,  "cp": 30, "title": "Archaeologist",   "msg": "All 7 anomaly types catalogued."},
    # Planets landed
    {"category": "planets_landed",     "threshold": 4,  "cp": 20, "title": "Galactic Traveler","msg": "Touched down on all 4 planets."},
    # Pirate kills
    {"category": "pirate_kills",       "threshold": 10, "cp": 10, "title": None,              "msg": "10 pirates eliminated."},
    {"category": "pirate_kills",       "threshold": 50, "cp": 25, "title": None,              "msg": "50 pirates destroyed."},
    {"category": "pirate_kills",       "threshold": 100,"cp": 50, "title": "Pirate Hunter",   "msg": "100 pirates down. The spacelanes breathe easier."},
    # Smuggling runs
    {"category": "smuggling_runs",     "threshold": 5,  "cp": 10, "title": None,              "msg": "5 smuggling runs completed."},
    {"category": "smuggling_runs",     "threshold": 20, "cp": 25, "title": None,              "msg": "20 runs under Imperial noses."},
    {"category": "smuggling_runs",     "threshold": 50, "cp": 50, "title": "Ace Smuggler",    "msg": "50 runs. You're a legend in the underworld."},
    # Trade runs
    {"category": "trade_runs",         "threshold": 10, "cp": 10, "title": None,              "msg": "10 profitable cargo runs."},
    {"category": "trade_runs",         "threshold": 50, "cp": 30, "title": "Merchant Prince", "msg": "50 profitable trade runs."},
]


# ── Log access helpers ────────────────────────────────────────────────────────

def get_ships_log(char: dict) -> dict:
    """Parse and return the character's ships_log, filling defaults."""
    attrs = char.get("attributes", {})
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except Exception:
            attrs = {}
    raw = attrs.get("ships_log", {})
    if not isinstance(raw, dict):
        raw = {}
    result = dict(DEFAULT_LOG)
    result.update(raw)
    # Ensure list fields are lists
    for k in ("zones_visited", "ships_scanned", "anomalies_resolved",
              "planets_landed", "titles_earned"):
        if not isinstance(result[k], list):
            result[k] = []
    return result


def _save_ships_log(attrs: dict, ships_log: dict) -> dict:
    """Store updated ships_log back into attrs dict and return attrs."""
    attrs["ships_log"] = ships_log
    return attrs


def _count(ships_log: dict, category: str) -> int:
    val = ships_log.get(category, 0)
    if isinstance(val, list):
        return len(val)
    return int(val)


# ── Core log event ────────────────────────────────────────────────────────────

async def log_event(
    db,
    char: dict,
    category: str,
    value: str | int | None = None,
) -> list[dict]:
    """
    Record a log event and check milestones.

    category: one of the DEFAULT_LOG keys
    value: for list categories (zones_visited etc.) — the item to add.
           For counter categories (pirate_kills etc.) — ignored (increments by 1).

    Returns list of newly triggered milestone dicts (may be empty).
    """
    try:
        attrs = char.get("attributes", {})
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        if not isinstance(attrs, dict):
            attrs = {}

        ships_log = get_ships_log(char)

        changed = False
        if category in ("pirate_kills", "smuggling_runs", "trade_runs"):
            ships_log[category] = ships_log.get(category, 0) + 1
            changed = True
        elif category in ("zones_visited", "ships_scanned",
                          "anomalies_resolved", "planets_landed"):
            if value and value not in ships_log[category]:
                ships_log[category].append(value)
                changed = True

        if not changed:
            return []

        triggered = _check_milestones(ships_log, category)

        # Apply titles
        for m in triggered:
            if m.get("title") and m["title"] not in ships_log["titles_earned"]:
                ships_log["titles_earned"].append(m["title"])

        # Save
        attrs = _save_ships_log(attrs, ships_log)
        char["attributes"] = json.dumps(attrs)
        await db.save_character(
            char["id"],
            attributes=char["attributes"],
        )

        # Award CP ticks for each milestone
        for m in triggered:
            if m.get("cp", 0) > 0:
                try:
                    from engine.cp_engine import get_cp_engine
                    await get_cp_engine().award_ticks(
                        char["id"], m["cp"], db,
                        reason=f"Ship's Log milestone: {m['msg']}",
                    )
                except Exception:
                    log.warning("log_event: unhandled exception", exc_info=True)
                    pass

        return triggered

    except Exception as e:
        log.debug("ships_log log_event error: %s", e)
        return []


def _check_milestones(ships_log: dict, category: str) -> list[dict]:
    """Return list of newly crossed milestones for this category."""
    triggered = []
    titles = ships_log.get("titles_earned", [])
    count = _count(ships_log, category)

    for m in MILESTONES:
        if m["category"] != category:
            continue
        if count < m["threshold"]:
            continue
        # Already awarded? Check by title (unique) or msg (no title)
        if m.get("title"):
            if m["title"] in titles:
                continue
        else:
            # Use (category, threshold) as key stored in a sentinel list
            sentinel_key = f"_done_{m['category']}_{m['threshold']}"
            if sentinel_key in titles:
                continue
            titles.append(sentinel_key)
            ships_log["titles_earned"] = titles
        triggered.append(m)

    return triggered


# ── Display helper ────────────────────────────────────────────────────────────

def format_ships_log(ships_log: dict, ansi_mod=None) -> list[str]:
    """Return ANSI-formatted lines for +ship/log display."""
    try:
        from server import ansi as _a
    except ImportError:
        _a = None
    ha = ansi_mod or _a

    BOLD  = ha.BOLD        if ha else "\033[1m"
    CYAN  = ha.BRIGHT_CYAN if ha else "\033[1;36m"
    WHITE = ha.BRIGHT_WHITE if ha else "\033[1m"
    DIM   = ha.DIM         if ha else "\033[2m"
    GREEN = ha.BRIGHT_GREEN if ha else "\033[1;32m"
    AMBER = ha.BRIGHT_YELLOW if ha else "\033[1;33m"
    RESET = ha.RESET       if ha else "\033[0m"

    lines = [
        f"  {CYAN}Ship's Log{RESET}",
        "",
    ]

    def _section(label, items, max_show=6):
        if not items:
            return [f"  {WHITE}{label:<22}{RESET}  {DIM}none{RESET}"]
        shown = items[:max_show]
        more = len(items) - max_show
        entry = ", ".join(str(x).replace("_", " ").title() for x in shown)
        if more > 0:
            entry += f" {DIM}+{more} more{RESET}"
        return [f"  {WHITE}{label:<22}{RESET}  {entry}"]

    def _counter(label, val, milestones_for_cat):
        next_ms = next(
            (m for m in MILESTONES
             if m["category"] == label.lower().replace(" ", "_").replace("'", "")
             and _count(ships_log, m["category"]) < m["threshold"]),
            None,
        )
        progress = ""
        if next_ms:
            progress = f"  {DIM}(next: {next_ms['threshold']} — {next_ms['cp']} CP){RESET}"
        return [f"  {WHITE}{label:<22}{RESET}  {val}{progress}"]

    lines += _section("Zones Visited",      ships_log.get("zones_visited", []))
    lines += _section("Ships Scanned",      ships_log.get("ships_scanned", []))
    lines += _section("Anomalies Resolved", ships_log.get("anomalies_resolved", []))
    lines += _section("Planets Landed",     ships_log.get("planets_landed", []))
    lines.append("")
    lines += _counter("Pirate Kills",   ships_log.get("pirate_kills", 0),   [])
    lines += _counter("Smuggling Runs", ships_log.get("smuggling_runs", 0), [])
    lines += _counter("Trade Runs",     ships_log.get("trade_runs", 0),     [])

    titles = [t for t in ships_log.get("titles_earned", [])
              if not t.startswith("_done_")]
    if titles:
        lines.append("")
        lines.append(
            f"  {AMBER}Titles:{RESET}  " +
            f"  ".join(f"{GREEN}{t}{RESET}" for t in titles)
        )

    return lines
