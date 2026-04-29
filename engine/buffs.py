# -*- coding: utf-8 -*-
"""
engine/buffs.py — Buff/Debuff Handler for SW_MUSH.

Centralized system for managing timed status effects on characters.
Buffs are stored in character attributes JSON under "active_buffs".

Design source: competitive_analysis_feature_designs_v1.md §H

Key invariant: buff modifiers are always expressed in PIPS (not dice).
  +3 pips = +1D.  -1 pip = -1 pip.  The skill check engine converts
  pips ↔ dice as needed.

Integration points:
  - engine/skill_checks.py  — get_buff_modifier() before rolling
  - engine/combat.py        — clear_all() on death/respawn
  - parser/builtin_commands.py — +buffs display command
  - server/tick_handlers_economy.py — buff_expiry_tick every 60s
"""

from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ── Buff Data ─────────────────────────────────────────────────────────────────

@dataclass
class Buff:
    buff_type: str                # "combat_stim", "dehydration", etc.
    source: str                   # "item:stimpack", "env:extreme_heat"
    stat_modifiers: dict          # {"dexterity": 3}  — values in PIPS
    duration_seconds: int         # 0 = permanent (until removed)
    started_at: float = 0.0
    stacks: int = 1
    max_stacks: int = 1
    display_name: str = ""
    positive: bool = True         # True = buff (green), False = debuff (red)

    def to_dict(self) -> dict:
        return {
            "buff_type": self.buff_type,
            "source": self.source,
            "stat_modifiers": self.stat_modifiers,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "stacks": self.stacks,
            "max_stacks": self.max_stacks,
            "display_name": self.display_name or self.buff_type.replace("_", " ").title(),
            "positive": self.positive,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Buff":
        return cls(
            buff_type=d.get("buff_type", ""),
            source=d.get("source", ""),
            stat_modifiers=d.get("stat_modifiers", {}),
            duration_seconds=d.get("duration_seconds", 0),
            started_at=d.get("started_at", 0.0),
            stacks=d.get("stacks", 1),
            max_stacks=d.get("max_stacks", 1),
            display_name=d.get("display_name", ""),
            positive=d.get("positive", True),
        )

    def is_expired(self) -> bool:
        if self.duration_seconds <= 0:
            return False  # Permanent
        return time.time() > self.started_at + self.duration_seconds

    def remaining_seconds(self) -> float:
        if self.duration_seconds <= 0:
            return -1.0  # Permanent
        return max(0.0, (self.started_at + self.duration_seconds) - time.time())


# ── Predefined Buff Types ─────────────────────────────────────────────────────

BUFF_TEMPLATES: dict[str, dict] = {
    "combat_stim": {
        "display_name": "Combat Stimulant",
        "stat_modifiers": {"dexterity": 3},  # +1D DEX
        "duration_seconds": 300,  # 5 minutes
        "max_stacks": 1,
        "positive": True,
        "source": "item:stimpack",
    },
    "bacta_healing": {
        "display_name": "Bacta Treatment",
        "stat_modifiers": {"strength": 6},  # +2D to healing (STR-based)
        "duration_seconds": 3600,  # 1 hour
        "max_stacks": 1,
        "positive": True,
        "source": "item:bacta",
    },
    "cantina_drink": {
        "display_name": "Cantina Buzz",
        "stat_modifiers": {"perception": -1, "con": 1},
        "duration_seconds": 1800,  # 30 minutes
        "max_stacks": 3,
        "positive": True,
        "source": "item:drink",
    },
    "inspired": {
        "display_name": "Inspired",
        "stat_modifiers": {"perception": 1, "knowledge": 1},
        "duration_seconds": 3600,  # 1 hour
        "max_stacks": 1,
        "positive": True,
        "source": "social:kudos",
    },
    "intimidated": {
        "display_name": "Intimidated",
        "stat_modifiers": {"dexterity": -1, "perception": -1},
        "duration_seconds": 600,  # 10 minutes
        "max_stacks": 1,
        "positive": False,
        "source": "social:intimidation",
    },
    "dehydration": {
        "display_name": "Dehydration",
        "stat_modifiers": {"strength": -1, "dexterity": -1},
        "duration_seconds": 0,  # Permanent until mitigated
        "max_stacks": 3,
        "positive": False,
        "source": "env:extreme_heat",
    },
    "toxic_exposure": {
        "display_name": "Toxic Exposure",
        "stat_modifiers": {"strength": -3},  # -1D STR
        "duration_seconds": 0,  # Until breath mask
        "max_stacks": 1,
        "positive": False,
        "source": "env:toxic_air",
    },
    "spice_high": {
        "display_name": "Spice Rush",
        "stat_modifiers": {"perception": 3, "knowledge": -2},
        "duration_seconds": 900,  # 15 minutes
        "max_stacks": 1,
        "positive": True,
        "source": "item:spice",
    },
    "force_control_pain": {
        "display_name": "Control Pain",
        "stat_modifiers": {},  # Special: ignores wound penalties
        "duration_seconds": 0,  # Concentration / scene
        "max_stacks": 1,
        "positive": True,
        "source": "force:control_pain",
    },
    "force_enhance_attribute": {
        "display_name": "Enhanced Attribute",
        "stat_modifiers": {},  # Set dynamically by Force power
        "duration_seconds": 0,  # Concentration
        "max_stacks": 1,
        "positive": True,
        "source": "force:enhance_attribute",
    },
}


# ── Character Buff Access ─────────────────────────────────────────────────────

def _get_buffs(char: dict) -> list[Buff]:
    """Extract active buffs from character attributes JSON."""
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        raw = attrs.get("active_buffs", [])
        return [Buff.from_dict(b) for b in raw if isinstance(b, dict)]
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        # Per code_review_session32.md D5: narrow guard. JSONDecodeError
        # for malformed JSON; TypeError/ValueError for shape errors from
        # Buff.from_dict on a corrupt buff dict. Log so corruption is
        # visible instead of silently dropping all buffs.
        log.warning(
            "[buffs] _get_buffs failed for char %s: %s",
            char.get("id"), e,
        )
        return []


def _set_buffs(char: dict, buffs: list[Buff]) -> None:
    """Write buffs back to character attributes JSON (mutates char)."""
    try:
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        attrs["active_buffs"] = [b.to_dict() for b in buffs]
        char["attributes"] = json.dumps(attrs)
    except Exception as e:
        log.warning("[buffs] _set_buffs failed: %s", e)


def get_active_buffs(char: dict) -> list[Buff]:
    """Return all active (non-expired) buffs for a character."""
    return [b for b in _get_buffs(char) if not b.is_expired()]


def get_buff_modifier(char: dict, stat: str) -> int:
    """Sum all active buff modifiers for a stat (in pips).

    This is the primary integration point for skill_checks.py.
    Call this before rolling to get the total buff/debuff adjustment.

    Args:
        char: Character dict.
        stat: Attribute name (e.g. "dexterity", "strength").

    Returns:
        Total pip modifier (positive = buff, negative = debuff).
    """
    total = 0
    for b in get_active_buffs(char):
        mod = b.stat_modifiers.get(stat.lower(), 0)
        total += mod * b.stacks
    return total


def has_buff(char: dict, buff_type: str) -> bool:
    """Check if character has an active buff of the given type."""
    return any(b.buff_type == buff_type for b in get_active_buffs(char))


# ── Buff Management ───────────────────────────────────────────────────────────

def add_buff(char: dict, buff_type: str, **overrides) -> dict:
    """Add or stack a buff on a character. Returns {ok, msg, buff}.

    Uses BUFF_TEMPLATES for defaults, with overrides for custom values.
    If the buff already exists and can stack, increments stacks.
    If at max stacks, refreshes duration.
    """
    template = BUFF_TEMPLATES.get(buff_type, {})
    if not template and not overrides:
        return {"ok": False, "msg": f"Unknown buff type '{buff_type}'."}

    # Merge template + overrides
    cfg = {**template, **overrides}
    cfg["buff_type"] = buff_type

    buffs = get_active_buffs(char)

    # Check for existing buff of same type
    existing = None
    for b in buffs:
        if b.buff_type == buff_type:
            existing = b
            break

    if existing:
        if existing.stacks < existing.max_stacks:
            existing.stacks += 1
            existing.started_at = time.time()  # Refresh duration
            _set_buffs(char, buffs)
            return {
                "ok": True,
                "msg": f"{existing.display_name} stacked to {existing.stacks}×.",
                "buff": existing,
            }
        else:
            # Refresh duration at max stacks
            existing.started_at = time.time()
            _set_buffs(char, buffs)
            return {
                "ok": True,
                "msg": f"{existing.display_name} refreshed (max stacks).",
                "buff": existing,
            }

    # Create new buff
    new_buff = Buff(
        buff_type=buff_type,
        source=cfg.get("source", "unknown"),
        stat_modifiers=cfg.get("stat_modifiers", {}),
        duration_seconds=cfg.get("duration_seconds", 300),
        started_at=time.time(),
        stacks=1,
        max_stacks=cfg.get("max_stacks", 1),
        display_name=cfg.get("display_name", buff_type.replace("_", " ").title()),
        positive=cfg.get("positive", True),
    )
    buffs.append(new_buff)
    _set_buffs(char, buffs)
    return {"ok": True, "msg": f"{new_buff.display_name} applied.", "buff": new_buff}


def remove_buff(char: dict, buff_type: str) -> dict:
    """Remove a buff by type. Returns {ok, msg}."""
    buffs = get_active_buffs(char)
    before = len(buffs)
    buffs = [b for b in buffs if b.buff_type != buff_type]
    if len(buffs) == before:
        return {"ok": False, "msg": f"No active '{buff_type}' buff to remove."}
    _set_buffs(char, buffs)
    return {"ok": True, "msg": f"Buff '{buff_type}' removed."}


def clear_all_buffs(char: dict) -> int:
    """Remove all buffs (used on death/respawn). Returns count removed."""
    buffs = _get_buffs(char)
    count = len(buffs)
    _set_buffs(char, [])
    return count


def expire_buffs(char: dict) -> list[str]:
    """Remove expired buffs. Returns list of expired buff display names.

    Called by the buff tick handler. Also prunes on any get_active_buffs call.
    """
    all_buffs = _get_buffs(char)
    active = []
    expired_names = []
    for b in all_buffs:
        if b.is_expired():
            expired_names.append(b.display_name or b.buff_type)
        else:
            active.append(b)
    if expired_names:
        _set_buffs(char, active)
    return expired_names


# ── Display ───────────────────────────────────────────────────────────────────

def format_buffs_display(char: dict) -> list[str]:
    """Format active buffs for +buffs command output."""
    buffs = get_active_buffs(char)
    if not buffs:
        return [
            "  \033[1;37m── Active Effects ──\033[0m",
            "  \033[2mNo active buffs or debuffs.\033[0m",
        ]

    lines = ["  \033[1;37m── Active Effects ──\033[0m"]
    for b in buffs:
        arrow = "\033[1;32m▲\033[0m" if b.positive else "\033[1;31m▼\033[0m"
        name = b.display_name or b.buff_type.replace("_", " ").title()
        if b.stacks > 1:
            name += f" ×{b.stacks}"

        # Format modifiers
        mod_parts = []
        for stat, pips in b.stat_modifiers.items():
            total_pips = pips * b.stacks
            if total_pips == 0:
                continue
            dice = abs(total_pips) // 3
            rem = abs(total_pips) % 3
            sign = "+" if total_pips > 0 else "-"
            if dice > 0 and rem > 0:
                mod_parts.append(f"{sign}{dice}D+{rem} {stat[:3].upper()}")
            elif dice > 0:
                mod_parts.append(f"{sign}{dice}D {stat[:3].upper()}")
            else:
                mod_parts.append(f"{sign}{rem} pip {stat[:3].upper()}")
        mod_str = ", ".join(mod_parts) if mod_parts else "special"

        # Duration
        rem_s = b.remaining_seconds()
        if rem_s < 0:
            dur_str = "until removed"
        elif rem_s < 60:
            dur_str = f"{int(rem_s)}s remaining"
        elif rem_s < 3600:
            dur_str = f"{int(rem_s // 60)}m {int(rem_s % 60):02d}s remaining"
        else:
            dur_str = f"{int(rem_s // 3600)}h {int((rem_s % 3600) // 60):02d}m remaining"

        dots = "." * max(1, 28 - len(name))
        lines.append(f"  {arrow} {name} {dots} {mod_str} · {dur_str}")

    return lines


def format_buffs_for_hud(char: dict) -> list[dict]:
    """Return buff data for web client HUD. Returns list of dicts."""
    buffs = get_active_buffs(char)
    result = []
    for b in buffs:
        result.append({
            "name": b.display_name or b.buff_type.replace("_", " ").title(),
            "positive": b.positive,
            "stacks": b.stacks,
            "remaining": int(b.remaining_seconds()),
        })
    return result
