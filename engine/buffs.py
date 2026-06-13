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
    # ── Drop 4a (2026-06-04): Affect Mind (suggestion) on a guard ────────
    # A flag-only buff (no stat modifier). While active, a city guard who
    # would otherwise engage this character looks the other way — the
    # "these aren't the droids you're looking for" effect. Consumed by
    # engine/city_guard_runtime.should_city_guard_engage. Time-boxed so
    # the suggestion fades; re-cast to refresh.
    "mind_trick_unseen": {
        "display_name": "Unseen (Mind Trick)",
        "stat_modifiers": {},  # presence-only; no roll modifier
        "duration_seconds": 300,  # 5 minutes
        "max_stacks": 1,
        "positive": True,
        "source": "force:affect_mind",
    },
    # ── SRB.1 medic stim family ──────────────────────────────────────────
    # Per support_role_buffs_design_v1.md §3.3.
    #
    # `combat_stim` (above) is the third member of this family; it
    # pre-dates SRB.1 and is left untouched.
    #
    # Substrate decisions:
    #   - All four stims (combat_stim, stimpack, adrenaline_shot,
    #     focus_stim) share the `stim:` source prefix or a `combat_stim`
    #     legacy source. The IS_STIM_TYPE set below is the authoritative
    #     list used by helpers; do not infer stim-ness from source string.
    #   - `max_stacks: 1` on every stim. Design §3.6 says "at most one
    #     active stim effect at a time" — cross-type. Within-type
    #     stacking is already prevented by max_stacks=1. Cross-type
    #     stacking is prevented by the medic parser (StimCommand) which
    #     calls has_active_stim() before applying.
    #   - Duration: design §3.3 says stimpack is "next single roll
    #     within 5 min." We model that as a 5-minute window; the
    #     consume-on-use behavior is the medic parser's responsibility
    #     (it calls remove_buff after the bonus is applied) — the buff
    #     simply provides the modifier window.
    #   - stat_modifiers: the design uses domain names ("Strength or
    #     Dexterity roll", "continuous action", "Knowledge or Technical
    #     roll"). We map each to the most representative single stat:
    #     stimpack→strength (covers brawn, brawling, climbing, lifting
    #     and is also a credible map for dexterity in WEG flavor),
    #     adrenaline_shot→strength (continuous action is typically
    #     physical), focus_stim→knowledge. Callers needing finer
    #     mapping (e.g. dexterity-specific roll) can pass an override
    #     via add_buff(..., stat_modifiers={...}).
    "stimpack": {
        "display_name": "Stimpack",
        "stat_modifiers": {"strength": 3},  # +1D
        "duration_seconds": 300,  # 5 min
        "max_stacks": 1,
        "positive": True,
        "source": "stim:stimpack",
    },
    "adrenaline_shot": {
        "display_name": "Adrenaline Shot",
        "stat_modifiers": {"strength": 6},  # +2D, mirrors Force Point
        "duration_seconds": 300,  # 5 min
        "max_stacks": 1,
        "positive": True,
        "source": "stim:adrenaline_shot",
    },
    "focus_stim": {
        "display_name": "Focus Stim",
        "stat_modifiers": {"knowledge": 3},  # +1D Knowledge/Technical
        "duration_seconds": 300,  # 5 min
        "max_stacks": 1,
        "positive": True,
        "source": "stim:focus_stim",
    },
}


# ── SRB.1 stim helpers ──────────────────────────────────────────────────────
#
# These helpers exist so callers can reason about the "stim" category
# without having to know which specific buff_types are stims. The
# canonical set lives here.

IS_STIM_TYPE: frozenset[str] = frozenset({
    "combat_stim",
    "stimpack",
    "adrenaline_shot",
    "focus_stim",
})


def is_stim_type(buff_type: str) -> bool:
    """True if ``buff_type`` is in the medic stim family.

    Per support_role_buffs_design_v1.md §3.6, only one stim of any
    type can be active per character at a time. Use this to gate
    cross-type stacking (e.g. medic parser checks before applying).
    """
    return buff_type in IS_STIM_TYPE


def get_active_stim(char: dict) -> Optional[Buff]:
    """Return the character's currently active stim Buff, or None.

    Filters by IS_STIM_TYPE. If for some reason multiple stims are
    present (shouldn't happen given the parser-side gate, but defensive
    against direct add_buff callers), returns the first match.
    """
    for buff in get_active_buffs(char):
        if is_stim_type(buff.buff_type):
            return buff
    return None


def has_active_stim(char: dict) -> bool:
    """True if the character has any stim from the IS_STIM_TYPE family
    active. Convenience wrapper around get_active_stim."""
    return get_active_stim(char) is not None


# ── SRB.1 (b) consumable inventory helpers ──────────────────────────────────
#
# Per T2.10.b (SRB.1 follow-up): stims must be present in the medic's
# kit before they can be administered. Consumables are stored in
# ``attributes.consumables`` as a dict ``{output_key: count}``, written
# by the crafting layer (parser/crafting_commands.py for
# ``output_type: consumable``).
#
# Storage-model note: this is one of two parallel consumable-storage
# models in the codebase (the other is ``inventory.items`` with the
# ``consumable: true`` flag, used by UseCommand for bacta packs etc.).
# The bifurcation is documented as tech debt in TODO.json under
# the "consumable_storage_unification" item. Until that unification
# drop lands, stims live in the ``attributes.consumables`` model
# because that's where the crafting layer writes them.
#
# These helpers operate on the in-memory char dict; callers must
# persist ``attributes`` via save_character(..., attributes=...)
# after a consume_consumable() call to durably record the deduction.


def _normalize_consumable_entry(v) -> dict:
    """Coerce one consumables[key] value to the canonical ``{"count", "quality"}``
    shape, tolerating BOTH storage generations (CRAFT.consumable_quality_potency).

    - legacy bare int  → ``{"count": v, "quality": 50}``  (vendor baseline —
      pre-migration stims keep working at q50 potency, no DB migration needed)
    - new dict         → ``{"count": int(...), "quality": int(...)}``  (defaults
      a missing/garbled quality to 50)
    - anything else    → ``{"count": 0, "quality": 50}``

    Quality is per-KEY (stims are fungible); the delivery write takes the max on
    re-craft so a better craft always upgrades the stack. See
    docs/design/consumable_quality_potency_v1.md §4.
    """
    if isinstance(v, bool):  # guard: bool is an int subclass
        return {"count": 0, "quality": 50}
    if isinstance(v, int):
        return {"count": v if v >= 0 else 0, "quality": 50}
    if isinstance(v, dict):
        try:
            cnt = int(v.get("count", 0))
        except (TypeError, ValueError):
            cnt = 0
        try:
            q = int(v.get("quality", 50))
        except (TypeError, ValueError):
            q = 50
        return {"count": cnt if cnt >= 0 else 0, "quality": q}
    return {"count": 0, "quality": 50}


def _read_consumables_dict(char: dict) -> dict:
    """Return the consumables dict from char attributes, or {}.

    Tolerates attributes stored as either a JSON string (DB shape)
    or a dict (in-memory shape). Returns a *new* dict on each call
    when the underlying attributes are a string — callers wanting
    to mutate must use ``_write_consumables_dict``.

    The per-key VALUES are returned as-stored (legacy bare int OR the new
    ``{"count", "quality"}`` dict) — use ``_normalize_consumable_entry`` to read
    a value uniformly.
    """
    attrs = char.get("attributes")
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(attrs, dict):
        return {}
    consumables = attrs.get("consumables", {})
    if not isinstance(consumables, dict):
        return {}
    return consumables


def _write_consumables_dict(char: dict, new_dict: dict) -> None:
    """Write the consumables dict back into char['attributes'].

    Preserves the storage shape — if attributes was a JSON string,
    it stays a JSON string; if a dict, stays a dict. Callers are
    responsible for persisting via save_character(..., attributes=...).
    """
    attrs = char.get("attributes")
    was_string = isinstance(attrs, str)
    if was_string:
        try:
            attrs = json.loads(attrs or "{}")
        except (json.JSONDecodeError, TypeError):
            attrs = {}
    if not isinstance(attrs, dict):
        attrs = {}
    attrs["consumables"] = new_dict
    char["attributes"] = json.dumps(attrs) if was_string else attrs


def has_consumable(char: dict, key: str) -> bool:
    """True if ``char`` has at least one consumable with the given
    ``output_key`` in their attributes.consumables dict.

    Crafting layer writes here under output_key (see
    parser/crafting_commands.py::elif output_type == "consumable").
    The ``key`` argument is the same output_key (e.g. "stimpack",
    "combat_stim", "adrenaline_shot", "focus_stim").
    """
    consumables = _read_consumables_dict(char)
    return _normalize_consumable_entry(consumables.get(key, 0))["count"] >= 1


def get_consumable_count(char: dict, key: str) -> int:
    """Return the count of ``key`` consumables on ``char`` (0 if none
    or if the consumables dict is malformed)."""
    consumables = _read_consumables_dict(char)
    return _normalize_consumable_entry(consumables.get(key, 0))["count"]


def get_consumable_quality(char: dict, key: str) -> int:
    """Return the per-key crafted quality of ``char``'s ``key`` consumables.

    Vendor baseline (50) when absent, legacy bare-int (no stored quality), or
    malformed (CRAFT.consumable_quality_potency). The potency consumer reads this
    BEFORE consume_consumable to scale the buff/roll — quality is per-key, so the
    read order doesn't matter, but reading first keeps consume_consumable a clean
    bool and avoids a signature ripple across its callers."""
    consumables = _read_consumables_dict(char)
    return _normalize_consumable_entry(consumables.get(key, 0))["quality"]


def consume_consumable(char: dict, key: str) -> bool:
    """Decrement ``char``'s count of ``key`` consumables by 1.

    Returns True if a consumable was consumed (count was ≥1 before
    the call), False if none was available. On True, the in-memory
    char['attributes'] is mutated; callers MUST persist via
    save_character(..., attributes=char['attributes']) to durably
    record the deduction.

    On False, no mutation occurs.

    Migration-tolerant (CRAFT.consumable_quality_potency): reads legacy bare-int
    AND the new ``{"count", "quality"}`` shape; on decrement it PRESERVES the
    per-key quality (a partly-used stack keeps its quality) and REWRITES the entry
    in the canonical dict shape. If the count drops to 0, the key is removed
    entirely (avoids accumulating zero-count entries on long-lived characters) —
    quality is moot once the stack is empty.

    Quality of the consumed unit is available via get_consumable_quality(); this
    stays a bool so its callers (engine/breaching.py, parser/medical_commands.py)
    keep their truthiness contract.
    """
    consumables = _read_consumables_dict(char)
    entry = _normalize_consumable_entry(consumables.get(key, 0))
    if entry["count"] < 1:
        return False
    new_count = entry["count"] - 1
    # Copy the dict so we mutate our own version, not a shared one
    new_dict = dict(consumables)
    if new_count <= 0:
        new_dict.pop(key, None)
    else:
        new_dict[key] = {"count": new_count, "quality": entry["quality"]}
    _write_consumables_dict(char, new_dict)
    return True


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
        # CRAFT.consumable_quality_potency: when the re-application carries an
        # EXPLICIT stat_modifiers override (a higher-quality crafted stim), apply
        # it to the existing buff — otherwise refreshing a max-stacks buff would
        # silently keep the OLD (lower-quality) magnitude and discard the new
        # craft's potency. Only honor an explicitly-passed override (not the
        # template default), so a plain re-apply doesn't reset to template.
        if "stat_modifiers" in overrides:
            existing.stat_modifiers = overrides["stat_modifiers"]
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
