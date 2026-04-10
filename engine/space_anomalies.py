# -*- coding: utf-8 -*-
"""
Space Anomaly Scanning & Salvage engine — Space Expansion v2, Phase 3.5a
Drop 6 of 14

Provides:
  - Anomaly dataclass + module-level state dict
  - spawn_anomalies_for_zone()  — called from game_server tick (every 300 ticks)
  - get_anomalies_for_zone()    — used by DeepScanCommand
  - tick_anomaly_expiry()       — prune stale derelict/salvage entries
  - get_scan_result_text()      — formats scan output by resolution level

No DB tables. All state is transient (module-level dict, intentional).
Restarts wipe anomalies, exactly like SpaceGrid.
"""

import random
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ── Anomaly type catalogue ───────────────────────────────────────────────────

ANOMALY_TYPES = [
    # (weight, type_key, display_name, scans_needed, description_vague,
    #  description_partial, description_full)
    (30, "derelict",     "Derelict Ship",          3,
     "Unknown metallic mass. Power signature absent.",
     "Derelict vessel — unpowered, adrift. Salvageable.",
     "Derelict Ship — dark freighter drifting silently. Cargo bay doors buckled open. "
     "Salvageable components detected. Type 'course anomaly {id}' to investigate."),

    (20, "distress",     "Distress Signal",         2,
     "Irregular subspace pulse. Could be equipment malfunction.",
     "Distress beacon — emergency frequency. Origin point resolving.",
     "Distress Signal — mayday broadcast from a damaged vessel. "
     "Commander station can attempt Perception check to detect ambush before committing. "
     "Type 'course anomaly {id}' to respond."),

    (15, "cache",        "Hidden Cache",            3,
     "Low-emission contact. Not a vessel signature.",
     "Concealed object — metal composite, small. Not a ship.",
     "Hidden Cache — armored container, cold and dark. "
     "Requires close approach (pilot) and security bypass (engineer). "
     "Type 'course anomaly {id}' to investigate."),

    (15, "pirates",      "Pirate Nest",             2,
     "Intermittent drive emissions. Multiple small contacts.",
     "Pirate camp — 2-3 vessels running silent, watching traffic.",
     "Pirate Nest — a pack waiting for prey. "
     "Expect 2-3 hostiles at Short range on arrival. Salvage available on victory. "
     "Type 'course anomaly {id}' to engage."),

    (10, "mineral_vein", "Asteroid Mineral Vein",   2,
     "High-density rock formation. Unusual mass-to-volume ratio.",
     "Mineral-rich asteroid — elevated metal content detected.",
     "Asteroid Mineral Vein — high-grade ore exposed by recent collision impact. "
     "Engineer or crew can extract resources (Technical check, Moderate). "
     "Type 'course anomaly {id}' to move into extraction range."),

    (5,  "imperial",     "Imperial Dead Drop",      4,
     "Encrypted tight-beam burst. Source: unknown.",
     "Encrypted data package — Imperial cipher signature.",
     "Imperial Dead Drop — a dead-letter container with encrypted intelligence data. "
     "Slicing check (Difficult, diff 20) to decode. Failure triggers an Imperial patrol. "
     "Type 'course anomaly {id}' to retrieve."),

    (5,  "mynock",       "Mynock Colony",            1,
     "Biological mass reading. Small, numerous.",
     "Mynock colony — hull parasites. They will attach if you approach.",
     "Mynock Colony — a swarm clinging to the nearest rock face. "
     "They will attach to your hull on proximity (1 system damage, Easy piloting to detach). "
     "Type 'course anomaly {id}' to approach (or avoid)."),
]

# Weights only, for random.choices()
_ATYPE_WEIGHTS   = [t[0] for t in ANOMALY_TYPES]
_ATYPE_KEYS      = [t[1] for t in ANOMALY_TYPES]
_ATYPE_META      = {t[1]: t for t in ANOMALY_TYPES}  # key → full tuple

# ── Spawn rate config ─────────────────────────────────────────────────────────

# Zone type string → spawn probability per check interval
ANOMALY_SPAWN_RATES = {
    "deep_space":       0.15,
    "hyperspace_lane":  0.05,
    "orbit":            0.10,
    "dock":             0.00,
}
ANOMALY_CHECK_INTERVAL = 300   # ticks between spawn checks
MAX_ANOMALIES_PER_ZONE = 2
DERELICT_EXPIRY        = 1800  # seconds (30 minutes) — derelict/cache/imperial
WRECK_EXPIRY           = 120   # seconds (2 minutes)  — combat debris wrecks

# ── Module-level state ────────────────────────────────────────────────────────

_anomalies: dict[str, list] = {}       # zone_id → list[Anomaly]
_anomaly_counter: int = 0              # global incrementing ID
_scan_cooldowns: dict[str, float] = {} # "char_id:zone_id" → expiry timestamp


@dataclass
class Anomaly:
    id: int
    zone_id: str
    anomaly_type: str             # key from ANOMALY_TYPES
    resolution: int = 0           # 0=none, 1=vague, 2=partial, 3=full
    spawned_at: float = field(default_factory=time.time)
    expiry: float = field(default_factory=lambda: time.time() + DERELICT_EXPIRY)
    resolved: bool = False        # True once crew has arrived and encounter played
    is_wreck: bool = False        # True for post-combat salvage opportunities
    wreck_ship_name: str = ""     # Display name for wreck anomalies

    @property
    def display_name(self) -> str:
        meta = _ATYPE_META.get(self.anomaly_type)
        return meta[2] if meta else self.anomaly_type.replace("_", " ").title()

    @property
    def scans_needed(self) -> int:
        meta = _ATYPE_META.get(self.anomaly_type)
        return meta[3] if meta else 3

    def description(self) -> str:
        meta = _ATYPE_META.get(self.anomaly_type)
        if not meta:
            return "Unclassified anomaly."
        if self.resolution == 0:
            return meta[4]
        elif self.resolution == 1:
            return meta[5]
        else:
            return meta[6].replace("{id}", str(self.id))

    def resolution_pct(self) -> int:
        needed = max(1, self.scans_needed)
        return min(100, int((self.resolution / needed) * 100))


# ── Public API ─────────────────────────────────────────────────────────────────

def get_anomalies_for_zone(zone_id: str) -> list:
    """Return list of Anomaly objects currently in zone_id."""
    _prune_expired(zone_id)
    return list(_anomalies.get(zone_id, []))


def spawn_anomalies_for_zone(zone_id: str, zone_type: str) -> Optional[object]:
    """
    Attempt to spawn a new anomaly in zone_id (call every ANOMALY_CHECK_INTERVAL ticks).
    Returns the new Anomaly if spawned, None otherwise.
    """
    global _anomaly_counter

    _prune_expired(zone_id)
    existing = _anomalies.get(zone_id, [])
    if len(existing) >= MAX_ANOMALIES_PER_ZONE:
        return None

    rate = ANOMALY_SPAWN_RATES.get(zone_type, 0.0)
    if rate <= 0.0 or random.random() > rate:
        return None

    atype = random.choices(_ATYPE_KEYS, weights=_ATYPE_WEIGHTS, k=1)[0]
    _anomaly_counter += 1
    a = Anomaly(
        id=_anomaly_counter,
        zone_id=zone_id,
        anomaly_type=atype,
    )
    _anomalies.setdefault(zone_id, []).append(a)
    log.debug("Anomaly #%d (%s) spawned in %s", a.id, atype, zone_id)
    return a


def add_wreck_anomaly(zone_id: str, ship_name: str) -> object:
    """
    Create a salvageable wreck anomaly after an NPC ship is destroyed.
    Returns the Anomaly object.
    """
    global _anomaly_counter
    _anomaly_counter += 1
    a = Anomaly(
        id=_anomaly_counter,
        zone_id=zone_id,
        anomaly_type="derelict",
        resolution=3,             # Fully resolved — visible immediately
        expiry=time.time() + WRECK_EXPIRY,
        is_wreck=True,
        wreck_ship_name=ship_name,
    )
    _anomalies.setdefault(zone_id, []).append(a)
    log.debug("Wreck anomaly #%d (%s) created in %s", a.id, ship_name, zone_id)
    return a


def get_anomaly_by_id(zone_id: str, anomaly_id: int) -> Optional[object]:
    """Fetch a specific Anomaly by ID within a zone."""
    for a in _anomalies.get(zone_id, []):
        if a.id == anomaly_id:
            return a
    return None


def remove_anomaly(zone_id: str, anomaly_id: int) -> bool:
    """Remove an anomaly (e.g. after salvage or resolution). Returns True if found."""
    zone_list = _anomalies.get(zone_id, [])
    before = len(zone_list)
    _anomalies[zone_id] = [a for a in zone_list if a.id != anomaly_id]
    return len(_anomalies[zone_id]) < before


def tick_anomaly_expiry(zone_id: str) -> None:
    """Prune expired anomalies for a zone — call periodically from game_server."""
    _prune_expired(zone_id)


def check_scan_cooldown(char_id: int, zone_id: str) -> Optional[float]:
    """
    Returns seconds remaining on fumble cooldown, or None if clear to scan.
    """
    key = f"{char_id}:{zone_id}"
    expiry = _scan_cooldowns.get(key)
    if expiry is None:
        return None
    remaining = expiry - time.time()
    if remaining <= 0:
        del _scan_cooldowns[key]
        return None
    return remaining


def set_scan_cooldown(char_id: int, zone_id: str, duration: float = 60.0) -> None:
    """Set a fumble scan cooldown for char in zone."""
    key = f"{char_id}:{zone_id}"
    _scan_cooldowns[key] = time.time() + duration


def advance_scan(anomaly: object, critical: bool = False) -> str:
    """
    Advance the resolution of an anomaly by one step (or two on critical).
    Returns a status string for output.
    """
    needed = anomaly.scans_needed
    steps = 2 if critical else 1
    anomaly.resolution = min(needed, anomaly.resolution + steps)

    if anomaly.resolution >= needed:
        return "resolved"
    elif anomaly.resolution == 1:
        return "vague"
    else:
        return "partial"


def get_scan_output(anomaly: object, status: str, ha) -> str:
    """
    Build the [DEEP SCAN] telnet output string for a given scan result.
    ha = server.ansi module (passed in to avoid circular import).
    """
    C  = ha.BRIGHT_CYAN
    Y  = ha.BRIGHT_YELLOW
    G  = ha.BRIGHT_GREEN
    W  = ha.WHITE
    R  = ha.RESET
    BR = ha.BRIGHT_RED

    pct = anomaly.resolution_pct()
    desc = anomaly.description()

    if status == "resolved":
        header = f"{G}[DEEP SCAN] Anomaly #{anomaly.id} fully resolved!{R}"
        pct_str = f"{G}100% — fully resolved.{R}"
    elif status == "partial":
        header = f"{Y}[DEEP SCAN] Anomaly #{anomaly.id} resolving...{R}"
        pct_str = f"{Y}{pct}% — scan again to fully resolve.{R}"
    else:  # vague
        header = f"{C}[DEEP SCAN] Anomaly detected in sector {anomaly.id}.{R}"
        pct_str = f"{C}{pct}% — scan again to narrow.{R}"

    name_str = anomaly.display_name if status == "resolved" else "Unknown"
    if status == "partial":
        name_str = anomaly.display_name

    lines = [
        f"  {header}",
        f"    Signal type: {W}{name_str}{R}",
        f"    {desc}",
        f"    Resolution: {pct_str}",
    ]
    return "\n".join(lines)


def list_zone_anomalies_text(zone_id: str, ha) -> str:
    """
    One-line summary of anomalies in zone for the scan command sidebar.
    Returns empty string if none.
    """
    anomalies = get_anomalies_for_zone(zone_id)
    visible = [a for a in anomalies if a.resolution > 0]
    if not visible:
        return ""
    C = ha.BRIGHT_CYAN
    Y = ha.BRIGHT_YELLOW
    R = ha.RESET
    lines = [f"  {C}[ANOMALIES DETECTED]{R}"]
    for a in visible:
        if a.resolution >= a.scans_needed:
            tag = f"{Y}RESOLVED{R}"
        else:
            tag = f"{C}{a.resolution_pct()}%{R}"
        lines.append(f"    #{a.id} {a.display_name} [{tag}]")
    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _prune_expired(zone_id: str) -> None:
    now = time.time()
    zone_list = _anomalies.get(zone_id, [])
    _anomalies[zone_id] = [a for a in zone_list if a.expiry > now]
