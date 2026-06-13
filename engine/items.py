"""
Item Instance System -- Star Wars D6 MUSH

Tracks weapon condition, quality, and crafting provenance.
Equipment is stored as a JSON blob on the character row.

Condition degrades with use (attacks) and can be repaired at a cost
of credits plus a permanent max-condition reduction (-5 per repair).
Quality reflects craftsmanship: vendor items are 50, player-crafted
items range 0-100 depending on the Technical roll + experiments.

Experimentation (Cracken's Jury-Rigging):
  Items can be experimentally modified post-craft. Each experiment
  picks a stat axis (damage, accuracy, durability for weapons) and
  rolls a skill check. Success boosts the axis with a tradeoff on
  another axis. Each experiment adds a breakdown die — rolled on
  every combat use, with a 1 triggering the breakdown table.
"""

import json
import random
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# -- Condition display --

_BAR_WIDTH = 10  # characters in the visual bar


def _condition_bar(current: int, maximum: int) -> str:
    """Render a visual condition bar like [████████░░] 80/100."""
    if maximum <= 0:
        return "[BROKEN] 0/0"
    ratio = max(0.0, min(1.0, current / maximum))
    filled = round(ratio * _BAR_WIDTH)
    empty = _BAR_WIDTH - filled

    # Color the bar based on ratio
    if ratio > 0.6:
        color = "\033[1;32m"   # bright green
    elif ratio > 0.25:
        color = "\033[1;33m"   # bright yellow
    else:
        color = "\033[1;31m"   # bright red
    reset = "\033[0m"

    bar = "█" * filled + "░" * empty
    return f"{color}[{bar}]{reset} {current}/{maximum}"


def _condition_label(current: int, maximum: int) -> str:
    """Return a text label: Pristine / Good / Worn / Damaged / Broken."""
    if maximum <= 0 or current <= 0:
        return "Broken"
    ratio = current / maximum
    if ratio >= 0.95:
        return "Pristine"
    if ratio >= 0.7:
        return "Good"
    if ratio >= 0.4:
        return "Worn"
    if ratio > 0:
        return "Damaged"
    return "Broken"


# -- ItemInstance --

@dataclass
class ItemInstance:
    """A specific instance of an item (usually a weapon) carried by a character."""

    key: str                         # weapon registry key, e.g. "blaster_pistol"
    condition: int = 100             # current condition (0 = broken)
    max_condition: int = 100         # ceiling -- drops by 5 per repair
    quality: int = 50                # 0-100; vendor = 50, crafted varies
    crafter: Optional[str] = None    # character name who crafted it, if any

    # -- Experimentation fields (Cracken's jury-rigging) --
    experiment_count: int = 0        # how many experiments performed on this item
    breakdown_dice: int = 0          # how many breakdown dice to roll on use
    experiment_log: list = field(default_factory=list)
    # Each entry: {"axis": "damage", "boost": 3.2, "tradeoff": {"durability": -0.96}}
    effective_mods: dict = field(default_factory=dict)
    # Accumulated stat modifiers: {"damage_mod": 2.24, "accuracy_mod": 1.8, ...}

    # -- Properties --

    @property
    def is_broken(self) -> bool:
        return self.condition <= 0

    @property
    def is_modified(self) -> bool:
        """True if this item has been experimentally modified."""
        return self.experiment_count > 0

    @property
    def condition_bar(self) -> str:
        return _condition_bar(self.condition, self.max_condition)

    @property
    def condition_label(self) -> str:
        return _condition_label(self.condition, self.max_condition)

    @property
    def mod_label(self) -> str:
        """Short label indicating modification status."""
        if self.experiment_count == 0:
            return ""
        return f" [Modified ×{self.experiment_count}]"

    # -- Wear & Repair --

    def apply_wear(self, amount: int = 1) -> None:
        """Reduce condition by *amount* (clamped to 0)."""
        self.condition = max(0, self.condition - amount)

    def repair(self) -> None:
        """Repair to max, but permanently reduce max by 5."""
        self.max_condition = max(0, self.max_condition - 5)
        self.condition = self.max_condition

    def repair_cost(self, base_cost: int) -> int:
        """Calculate credit cost to repair based on how damaged it is.

        Scales from ~10% of base_cost at minor damage to ~50% at broken.
        Minimum cost is 50 credits.
        """
        if self.max_condition <= 0:
            return 0
        damage_ratio = 1.0 - (self.condition / self.max_condition)
        cost = int(base_cost * (0.1 + damage_ratio * 0.4))
        return max(50, cost)

    # -- Experimentation --

    def add_experiment(self, axis: str, boost: float,
                       tradeoff: Optional[dict] = None) -> None:
        """Record a successful experiment on this item."""
        entry = {"axis": axis, "boost": round(boost, 2)}
        if tradeoff:
            entry["tradeoff"] = {k: round(v, 2) for k, v in tradeoff.items()}
        self.experiment_log.append(entry)
        self.experiment_count += 1
        self.breakdown_dice += 1
        # Update accumulated modifiers
        mod_key = f"{axis}_mod"
        self.effective_mods[mod_key] = round(
            self.effective_mods.get(mod_key, 0.0) + boost, 2
        )
        if tradeoff:
            for taxis, tval in tradeoff.items():
                tmod_key = f"{taxis}_mod"
                self.effective_mods[tmod_key] = round(
                    self.effective_mods.get(tmod_key, 0.0) + tval, 2
                )

    def get_mod(self, axis: str) -> float:
        """Return the accumulated modifier for an axis (e.g. 'damage')."""
        return self.effective_mods.get(f"{axis}_mod", 0.0)

    def roll_breakdown_check(self) -> str:
        """
        Roll breakdown dice after combat use.
        Returns: 'fine' | 'jammed' | 'broken' | 'exploded'

        Cracken's rules: roll one die per experiment. If ANY die shows 1,
        roll on the breakdown table (1d6):
          1 = exploded (destroyed + damage to wielder)
          2 = broken (destroyed, no damage)
          3 = jammed (loses 25% max_condition, still usable)
          4-6 = fine (close call)
        """
        if self.breakdown_dice <= 0:
            return "fine"

        # Roll breakdown dice
        rolls = [random.randint(1, 6) for _ in range(self.breakdown_dice)]
        if 1 not in rolls:
            return "fine"

        # A 1 was rolled — check the breakdown table
        table_roll = random.randint(1, 6)
        if table_roll == 1:
            return "exploded"
        elif table_roll == 2:
            return "broken"
        elif table_roll == 3:
            return "jammed"
        else:
            return "fine"

    def apply_jam(self) -> None:
        """Apply a jam result — lose 25% of max_condition."""
        loss = max(1, self.max_condition // 4)
        self.max_condition = max(0, self.max_condition - loss)
        self.condition = min(self.condition, self.max_condition)

    # -- Constructors --

    @classmethod
    def new_from_vendor(cls, key: str) -> "ItemInstance":
        """Create a brand-new item purchased from an NPC vendor."""
        return cls(key=key, condition=100, max_condition=100, quality=50)

    @classmethod
    def new_crafted(cls, key: str, quality: int,
                    crafter: str, max_condition: int = 100) -> "ItemInstance":
        """Create a player-crafted item with variable quality."""
        return cls(
            key=key,
            condition=max_condition,
            max_condition=max_condition,
            quality=max(0, min(100, quality)),
            crafter=crafter,
        )

    # -- Serialization --

    def to_dict(self) -> dict:
        d = {
            "key": self.key,
            "condition": self.condition,
            "max_condition": self.max_condition,
            "quality": self.quality,
        }
        if self.crafter:
            d["crafter"] = self.crafter
        # Only serialize experiment fields if modified (backward compat)
        if self.experiment_count > 0:
            d["experiment_count"] = self.experiment_count
            d["breakdown_dice"] = self.breakdown_dice
            d["experiment_log"] = self.experiment_log
            d["effective_mods"] = self.effective_mods
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ItemInstance":
        return cls(
            key=d["key"],
            condition=d.get("condition", 100),
            max_condition=d.get("max_condition", 100),
            quality=d.get("quality", 50),
            crafter=d.get("crafter"),
            experiment_count=d.get("experiment_count", 0),
            breakdown_dice=d.get("breakdown_dice", 0),
            experiment_log=d.get("experiment_log", []),
            effective_mods=d.get("effective_mods", {}),
        )


# -- Module-level helpers --

def parse_equipment_json(raw: str) -> Optional[ItemInstance]:
    """LEGACY (shape-2 only) — do NOT use in new code; use ``read_equipment``.

    Parses ONLY the legacy top-level single-instance shape and returns None
    for the canonical per-slot shape. Retained for test fixtures that
    exercise legacy-shape tolerance."""
    if not raw:
        return None
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not d or not isinstance(d, dict) or "key" not in d:
        return None
    return ItemInstance.from_dict(d)


def serialize_equipment(item: Optional[ItemInstance]) -> str:
    """LEGACY (writes shape 2; clobbers the armor slot) — do NOT use in new
    code; use ``write_equipment``. Retained for test fixtures only."""
    if item is None:
        return "{}"
    return json.dumps(item.to_dict())


# ── Canonical per-slot equipment helpers (equipment-instance untangle) ──────
#
# Historically the character ``equipment`` column has been written in THREE
# mutually-incompatible shapes that silently corrupted each other:
#   1. flat key strings        {"weapon": "blaster_pistol", "armor": "..."}
#   2. top-level single inst.   {"key": "blaster_pistol", "condition": ...}  (weapon-only)
#   3. per-slot ItemInstance    {"weapon": {<inst>}, "armor": {<inst>}}      (CANONICAL)
# (e.g. `equip` wrote shape 2 and clobbered armor; `wear` wrote shape 1; the
# sheet read only shape 2.) These helpers make shape 3 canonical, give every
# reader a single tolerant entry point that accepts all three, and provide one
# writer that preserves both slots. Note: the Character object still holds
# equipped_weapon/worn_armor as bare KEY strings, so Character.to_dict() can't
# carry instance condition/quality — but to_dict() is NOT an equipment
# persistence path (every durable write goes through save_character(equipment=)),
# so the DB JSON written by the equip/wear/craft commands remains the source of
# truth for instance data. (A Character-object-holds-instances refactor is a
# separate, larger pass — flagged in TODO.)

def read_equipment(raw) -> dict:
    """Tolerant reader → ``{"weapon": ItemInstance|None, "armor": ItemInstance|None}``.

    Normalizes all three historical shapes (and empty/list/None) so consumers
    read one structure regardless of which writer last touched the column.
    Read-only and exception-tolerant: a malformed column yields two None slots
    rather than raising.
    """
    out = {"weapon": None, "armor": None}
    if not raw:
        return out
    d = raw
    if isinstance(d, str):
        try:
            d = json.loads(d or "{}")
        except (json.JSONDecodeError, TypeError):
            return out
    if not isinstance(d, dict):
        return out  # legacy list/other → empty
    # Shape 2: top-level single instance (legacy weapon-only) — has "key" but
    # no slot wrappers.
    if "key" in d and "weapon" not in d and "armor" not in d:
        try:
            out["weapon"] = ItemInstance.from_dict(d)
        except Exception:
            out["weapon"] = None
        return out
    for slot in ("weapon", "armor"):
        v = d.get(slot)
        if not v:
            continue
        if isinstance(v, str):
            out[slot] = ItemInstance(key=v)          # shape 1: flat key → default inst
        elif isinstance(v, dict) and v.get("key"):
            try:
                out[slot] = ItemInstance.from_dict(v)  # shape 3
            except Exception:
                out[slot] = None
    return out


def equipment_keys(raw) -> dict:
    """Tolerant key-only view → ``{"weapon": str, "armor": str}`` ("" when empty).

    Drop-in for display/lookup sites that only need the registry key (sheet,
    locks, HUD); they get the right key from ANY stored shape.
    """
    slots = read_equipment(raw)
    return {
        "weapon": slots["weapon"].key if slots["weapon"] else "",
        "armor":  slots["armor"].key  if slots["armor"]  else "",
    }


def write_equipment(weapon: Optional[ItemInstance] = None,
                    armor: Optional[ItemInstance] = None) -> str:
    """The one true writer: canonical per-slot JSON. Empty slots are omitted;
    both-empty yields ``"{}"``. Always round-trips through ``read_equipment``."""
    out = {}
    if weapon is not None:
        out["weapon"] = weapon.to_dict()
    if armor is not None:
        out["armor"] = armor.to_dict()
    return json.dumps(out)


# ── Carried-gear helpers (CRAFT.P0.9 — inventory-aware equip/wear) ──────────
#
# Pre-P0.9, the gear surface leaked in three directions: `equip <name>` and
# `wear <name>` MINTED a fresh vendor-grade ItemInstance from the registry
# with no ownership check or credit cost (an unlogged faucet that also made
# crafted/modified instances unequippable — equip conjured a pristine copy
# instead); `unequip`/`remove` DESTROYED the slotted instance; and `buy`
# destroyed whatever the new purchase displaced. These helpers give the verb
# layer one matching + conversion surface so instances ROUND-TRIP between the
# carried list (db inventory `items`) and the equipment slots, preserving
# condition/quality/crafter/experiment state. Acquisition is now exclusively
# buy (credits-charged), craft, loot, or trade.

def instance_to_carried(item: "ItemInstance", name: str = None,
                        gear_type: str = "weapon") -> dict:
    """ItemInstance → carried-inventory dict (db.add_to_inventory shape)."""
    d = item.to_dict()
    d["type"] = gear_type
    if name:
        d["name"] = name
    return d


def carried_to_instance(d: dict) -> Optional["ItemInstance"]:
    """Carried-inventory dict → ItemInstance (None if not instance-shaped)."""
    if not isinstance(d, dict) or not d.get("key"):
        return None
    try:
        return ItemInstance.from_dict(d)
    except Exception:
        return None


def find_carried_gear(carried: list, name_arg: str, registry,
                      want_armor: bool = False):
    """Find a weapon/armor item in the carried list by name.

    Matches case-insensitive substring against the registry display name,
    the item dict's own name, and the registry key. Skips non-gear entries
    (ship components, survival gear, etc.) and entries whose key doesn't
    resolve in the registry. Returns (index, item_dict, weapon_data) or
    (None, None, None).
    """
    needle = (name_arg or "").strip().lower()
    if not needle:
        return None, None, None
    for i, d in enumerate(carried or []):
        if not isinstance(d, dict):
            continue
        if d.get("type") in ("ship_component", "survival_gear", "equipment"):
            continue
        key = d.get("key", "")
        if not key:
            continue
        w = registry.get(key)
        if not w or bool(getattr(w, "is_armor", False)) != want_armor:
            continue
        names = (w.name.lower(), str(d.get("name", "")).lower(), key.lower())
        if any(needle in n for n in names if n):
            return i, d, w
    return None, None, None


# ── inventory_state payload (Webify UI-4a inventory panel) ──────────────────
#
# Assembles the structured push the web inventory modal renders. The registry
# (engine.weapons.get_weapon_registry) is the producer for name / slot / value
# (WeaponData.cost) / comparable stats; per-item condition/quality/crafter come
# from the stored ItemInstance (equipped) or carried item dict. No container /
# carry-weight: there is no encumbrance model at HEAD, so the panel omits the
# weight bar rather than render a field with no producer.

def _inv_item_slot(w) -> str:
    """Slot for a registry entry: 'weapon' | 'armor' (None → 'misc')."""
    if w is None:
        return "misc"
    return "armor" if w.is_armor else "weapon"


def _inv_item_stats(w) -> dict:
    """Comparable stat axes for the delta preview, from a WeaponData.

    Weapons expose ``damage`` (dice string) and, when ranged, a display-only
    ``range`` triple. Armor exposes ``energy`` / ``physical`` protection dice
    and any ``dex_penalty``. Values are the raw dice/strings; the client turns
    dice into D6 pips (1D=3) for the from→to arrows.
    """
    if w is None:
        return {}
    if w.is_armor:
        s = {}
        if w.protection_energy:
            s["energy"] = w.protection_energy
        if w.protection_physical:
            s["physical"] = w.protection_physical
        if w.dexterity_penalty:
            s["dex_penalty"] = w.dexterity_penalty
        return s
    s = {}
    if w.damage:
        s["damage"] = w.damage
    if getattr(w, "is_ranged", False) and w.ranges and len(w.ranges) == 4:
        s["range"] = f"{w.ranges[1]}/{w.ranges[2]}/{w.ranges[3]}"
    return s


def _resolve_inv_item(src, registry) -> dict:
    """Build one inventory_state item entry.

    ``src`` is an ItemInstance (equipped slot) OR a carried item dict
    (db.get_inventory). Name / slot / value / stats resolve from the registry
    by key; condition / quality / crafter / experiment_count / quantity come
    from the instance or dict (with safe defaults).
    """
    if isinstance(src, ItemInstance):
        key = src.key
        quality, condition = src.quality, src.condition
        max_condition = src.max_condition
        crafter = src.crafter
        experiment_count = src.experiment_count
        quantity = 1
        d = {}
    else:
        d = src or {}
        key = d.get("key", "")
        quality = d.get("quality", 50)
        condition = d.get("condition", d.get("max_condition", 100))
        max_condition = d.get("max_condition", 100)
        crafter = d.get("crafter")
        experiment_count = d.get("experiment_count", 0)
        quantity = d.get("quantity", d.get("qty", 1))
    w = registry.get(key) if (registry and key) else None
    name = (w.name if w else None) or d.get("name") or key or "Unknown item"
    slot = _inv_item_slot(w) if w else d.get("slot", "misc")
    value = (w.cost if w else 0) or d.get("value", 0) or 0
    return {
        "key": key,
        "name": name,
        "slot": slot,
        "quality": quality,
        "condition": condition,
        "max_condition": max_condition,
        "quantity": quantity,
        "crafter": crafter or "",
        "experiment_count": experiment_count,
        "stats": _inv_item_stats(w),
        "value": value,
    }


def build_inventory_state(equipment_raw, carried, registry=None) -> dict:
    """Assemble the ``inventory_state`` push for the web inventory panel.

    ``equipment_raw`` — the char['equipment'] column (any shape; read via the
    tolerant ``read_equipment``). ``carried`` — db.get_inventory() (list of
    item dicts). ``registry`` defaults to engine.weapons.get_weapon_registry().
    Returns ``{"equipped": {"weapon": item|None, "armor": item|None},
    "carried": [item, ...]}`` (no container — see module note).
    """
    if registry is None:
        from engine.weapons import get_weapon_registry
        registry = get_weapon_registry()
    slots = read_equipment(equipment_raw)
    equipped = {
        "weapon": _resolve_inv_item(slots["weapon"], registry) if slots["weapon"] else None,
        "armor":  _resolve_inv_item(slots["armor"], registry) if slots["armor"] else None,
    }
    carried_out = [
        _resolve_inv_item(it, registry)
        for it in (carried or []) if isinstance(it, dict)
    ]
    return {"equipped": equipped, "carried": carried_out}


# ── NPC buyback policy (economy audit §1.3) ─────────────────────────────────
# NPC vendors must not price-support the player crafted-goods market: a
# well-made player craft is "too good for scrap," so the NPC refuses it and the
# player must list it on a vendor droid (where the market discovers its own
# floor). Low-quality crafts and all factory/vendor items still sell to NPCs as
# salvage. Tunable: raise to refuse fewer crafts, lower to refuse more.
CRAFTED_NPC_BUYBACK_MAX_QUALITY = 50


def npc_refuses_buyback(item) -> bool:
    """True if an NPC vendor should refuse to buy ``item`` back.

    Scoped to PLAYER-CRAFTED items (``crafter`` set) at or above the quality
    threshold; factory/vendor items (no crafter) and low-quality crafts are
    unaffected. Closes the craft -> NPC-sell price-support loop (economy
    audit v2 §1.3) by pushing good crafts to the player vendor-droid market.
    """
    return bool(getattr(item, "crafter", None)) and \
        getattr(item, "quality", 0) >= CRAFTED_NPC_BUYBACK_MAX_QUALITY


# ── Crafted-weapon combat pip helpers (Drop 19 — OBS.quality_and_boosts_not_combat_read, Option B) ──
#
# These are the ONLY places where quality/experiment data translates to combat
# numbers. All call sites must go through crafted_combat_pips / apply_damage_pips
# — never inline the math at the call site (funnel discipline).

def _quality_band_pips(quality: int) -> int:
    """Crafted-quality → damage pip delta. Vendor (q50) = 0; shoddy = -1; fine = +1/+2."""
    try:
        q = int(quality)
    except (TypeError, ValueError):
        return 0
    if q <= 49:
        return -1
    if q <= 69:
        return 0
    if q <= 89:
        return 1
    return 2  # 90-100


def crafted_combat_pips(inst) -> tuple:
    """(damage_pips, accuracy_pips) a crafted weapon instance contributes to combat.

    WEG-faithful, hard-capped to avoid power creep (max +1D damage / +1 pip
    to-hit over a vendor weapon). Returns (0, 0) for None / non-instances
    (fail-open). Vendor/legacy weapons (q50, no mods) yield (0, 0).

    Quality band → damage pips: ≤49=-1, 50-69=0, 70-89=+1, 90-100=+2.
    Damage-mod boost: every full +2.0 damage_mod = +1 pip, capped +1, never
    negative. Combined damage cap: +3 pips (= +1D), floor -1.
    Accuracy-mod boost: every full +2.0 accuracy_mod = +1 pip, floor 0, cap +1.
    """
    if inst is None:
        return 0, 0
    try:
        q_pips = _quality_band_pips(getattr(inst, "quality", 50))
        # experiment damage boost: every full +2.0 damage_mod = +1 pip, capped +1, never negative
        boost_pips = max(0, min(1, int(inst.get_mod("damage") // 2.0)))
        dmg_pips = max(-1, min(3, q_pips + boost_pips))   # combined cap +3 (=+1D), floor -1
        acc_pips = max(0, min(1, int(inst.get_mod("accuracy") // 2.0)))  # floor 0, cap +1
        return dmg_pips, acc_pips
    except Exception:
        return 0, 0


def apply_damage_pips(damage_str: str, pips: int) -> str:
    """Add `pips` to a D6 damage code, preserving a leading attribute token (STR+...).

    ``str(DicePool.parse(code) + pips)`` carries/borrows automatically (3 pips = 1D).
    For 'STR+2D' (melee), parse() rejects the STR token, so add to the bonus portion
    only and re-emit 'STR+'. Fail-open: a malformed code returns unchanged.
    """
    if not pips:
        return damage_str
    from engine.dice import DicePool
    s = (damage_str or "").strip()
    up = s.upper()
    try:
        if up.startswith("STR"):
            bonus = up[3:].lstrip("+").strip() or "0D"
            return f"STR+{DicePool.parse(bonus) + pips}"
        return str(DicePool.parse(s) + pips)
    except Exception:
        return damage_str
