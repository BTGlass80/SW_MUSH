"""
Item Instance System — Star Wars D6 MUSH

Tracks weapon condition, quality, and crafting provenance.
Equipment is stored as a JSON blob on the character row.

Condition degrades with use (attacks) and can be repaired at a cost
of credits plus a permanent max-condition reduction (-5 per repair).
Quality reflects craftsmanship: vendor items are 50, player-crafted
items range 0-100 depending on the Technical roll + experiments.
"""

import json
from dataclasses import dataclass, field
from typing import Optional


# ── Condition display ──

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


# ── ItemInstance ──

@dataclass
class ItemInstance:
    """A specific instance of an item (usually a weapon) carried by a character."""

    key: str                         # weapon registry key, e.g. "blaster_pistol"
    condition: int = 100             # current condition (0 = broken)
    max_condition: int = 100         # ceiling — drops by 5 per repair
    quality: int = 50                # 0-100; vendor = 50, crafted varies
    crafter: Optional[str] = None    # character name who crafted it, if any

    # ── Properties ──

    @property
    def is_broken(self) -> bool:
        return self.condition <= 0

    @property
    def condition_bar(self) -> str:
        return _condition_bar(self.condition, self.max_condition)

    @property
    def condition_label(self) -> str:
        return _condition_label(self.condition, self.max_condition)

    # ── Wear & Repair ──

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

    # ── Constructors ──

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

    # ── Serialization ──

    def to_dict(self) -> dict:
        d = {
            "key": self.key,
            "condition": self.condition,
            "max_condition": self.max_condition,
            "quality": self.quality,
        }
        if self.crafter:
            d["crafter"] = self.crafter
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ItemInstance":
        return cls(
            key=d["key"],
            condition=d.get("condition", 100),
            max_condition=d.get("max_condition", 100),
            quality=d.get("quality", 50),
            crafter=d.get("crafter"),
        )


# ── Module-level helpers ──

def parse_equipment_json(raw: str) -> Optional[ItemInstance]:
    """Parse a character's equipment JSON into an ItemInstance, or None."""
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
    """Serialize an ItemInstance (or None) to a JSON string for DB storage."""
    if item is None:
        return "{}"
    return json.dumps(item.to_dict())
