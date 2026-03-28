"""
D6 Dice Engine - Star Wars D6 Revised & Expanded

Core mechanics:
  - Dice pools: roll XD+Y (X six-sided dice plus Y pips)
  - Wild Die: one die per pool explodes on 6, complicates on 1
  - Difficulty checks: roll vs target number
  - Opposed rolls: two pools head-to-head
  - Scale modifiers: for vehicle/space combat cross-scale engagements
"""
import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


# ── Dice Pool Representation ──

@dataclass
class DicePool:
    """
    Represents a D6 dice pool like '4D+2'.
    dice = number of dice, pips = bonus (0-2).
    """
    dice: int = 0
    pips: int = 0

    def __post_init__(self):
        if self.pips >= 3:
            self.dice += self.pips // 3
            self.pips = self.pips % 3
        self.dice = max(0, self.dice)
        self.pips = max(0, self.pips)

    @classmethod
    def parse(cls, text: str) -> "DicePool":
        """Parse '4D+2', '3D', '2d+1', '5D-1', etc."""
        text = text.strip().upper().replace(" ", "")
        if not text:
            return cls(0, 0)
        dice = 0
        pips = 0
        if "D" in text:
            parts = text.split("D", 1)
            dice = int(parts[0]) if parts[0] else 0
            remainder = parts[1]
            if remainder:
                if remainder.startswith("+"):
                    pips = int(remainder[1:])
                elif remainder.startswith("-"):
                    pips = -int(remainder[1:])
                else:
                    pips = int(remainder)
        else:
            pips = int(text)
        return cls(dice, pips)

    def __str__(self) -> str:
        if self.pips > 0:
            return f"{self.dice}D+{self.pips}"
        elif self.pips < 0:
            return f"{self.dice}D{self.pips}"
        return f"{self.dice}D"

    def __repr__(self) -> str:
        return f"DicePool({self.dice}, {self.pips})"

    def __add__(self, other):
        if isinstance(other, DicePool):
            return DicePool(self.dice + other.dice, self.pips + other.pips)
        if isinstance(other, int):
            return DicePool(self.dice, self.pips + other)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, DicePool):
            return DicePool(self.dice - other.dice, self.pips - other.pips)
        if isinstance(other, int):
            return DicePool(self.dice, self.pips - other)
        return NotImplemented

    def is_zero(self) -> bool:
        return self.dice <= 0 and self.pips <= 0

    def total_pips(self) -> int:
        """Convert to pips for comparison. 1D = 3 pips."""
        return (self.dice * 3) + self.pips


# ── Roll Results ──

@dataclass
class WildDieResult:
    """Tracks the Wild Die specifically."""
    rolls: list[int] = field(default_factory=list)
    total: int = 0
    exploded: bool = False
    complication: bool = False

    @property
    def first_roll(self) -> int:
        return self.rolls[0] if self.rolls else 0


@dataclass
class RollResult:
    """Complete result of a dice pool roll."""
    pool: DicePool
    normal_dice: list[int] = field(default_factory=list)
    wild_die: Optional[WildDieResult] = None
    pips: int = 0
    total: int = 0
    complication: bool = False
    exploded: bool = False
    removed_die: Optional[int] = None

    def display(self) -> str:
        """Formatted: '[4D+2] 3, 5, 2, W:6→4 (+2) = 22'"""
        parts = [str(d) for d in self.normal_dice]
        if self.wild_die:
            if self.wild_die.exploded:
                chain = "\u2192".join(str(r) for r in self.wild_die.rolls)
                parts.append(f"W:{chain}")
            elif self.wild_die.complication:
                parts.append("W:1!")
            else:
                parts.append(f"W:{self.wild_die.total}")
        dice_str = ", ".join(parts)
        pip_str = f" (+{self.pips})" if self.pips > 0 else (f" ({self.pips})" if self.pips < 0 else "")
        comp_str = f" [Complication! Removed {self.removed_die}]" if self.complication and self.removed_die is not None else ""
        return f"[{self.pool}] {dice_str}{pip_str} = {self.total}{comp_str}"


@dataclass
class CheckResult:
    """Result of a roll vs. difficulty number."""
    roll: RollResult
    target: int
    success: bool = False
    margin: int = 0

    def display(self) -> str:
        outcome = "SUCCESS" if self.success else "FAILURE"
        return f"{self.roll.display()} vs {self.target} \u2192 {outcome} (margin: {self.margin:+d})"


@dataclass
class OpposedResult:
    """Result of two opposed rolls."""
    attacker_roll: RollResult
    defender_roll: RollResult
    attacker_wins: bool = False
    margin: int = 0

    def display(self) -> str:
        winner = "ATTACKER wins" if self.attacker_wins else "DEFENDER wins"
        return (
            f"Attacker: {self.attacker_roll.display()}\n"
            f"Defender: {self.defender_roll.display()}\n"
            f"\u2192 {winner} by {abs(self.margin)}"
        )


# ── Difficulty Levels ──

class Difficulty(IntEnum):
    VERY_EASY = 5
    EASY = 10
    MODERATE = 15
    DIFFICULT = 20
    VERY_DIFFICULT = 25
    HEROIC = 30

    @classmethod
    def from_name(cls, name: str) -> "Difficulty":
        name = name.upper().replace(" ", "_").replace("-", "_")
        return cls[name]

    @classmethod
    def describe(cls, target: int) -> str:
        for diff in sorted(cls, reverse=True):
            if target >= diff.value:
                return diff.name.replace("_", " ").title()
        return "Trivial"


# ── Scale System ──

class Scale(IntEnum):
    CHARACTER = 0
    SPEEDER = 2
    WALKER = 4
    STARFIGHTER = 6
    CORVETTE = 9
    CAPITAL = 12
    DEATH_STAR = 18

    @classmethod
    def from_name(cls, name: str) -> "Scale":
        return cls[name.upper().replace(" ", "_")]

    @classmethod
    def difference(cls, attacker_scale: "Scale", defender_scale: "Scale") -> int:
        return defender_scale.value - attacker_scale.value


# ── Core Dice Functions ──

def roll_die() -> int:
    """Roll a single d6."""
    return random.randint(1, 6)


def roll_wild_die() -> WildDieResult:
    """Roll the Wild Die with explosion and complication rules."""
    result = WildDieResult()
    first = roll_die()
    result.rolls.append(first)

    if first == 1:
        result.complication = True
        result.total = 0
        return result

    if first == 6:
        result.exploded = True
        total = 6
        while True:
            reroll = roll_die()
            result.rolls.append(reroll)
            if reroll == 6:
                total += 6
            else:
                total += reroll
                break
        result.total = total
        return result

    result.total = first
    return result


def roll_d6_pool(pool: DicePool) -> RollResult:
    """
    Roll a full D6 dice pool. One die is always the Wild Die.
    On complication (Wild Die = 1): Wild Die = 0 AND highest
    normal die is removed.
    """
    if pool.dice <= 0:
        return RollResult(pool=pool, pips=pool.pips, total=max(0, pool.pips))

    normal_dice = sorted([roll_die() for _ in range(pool.dice - 1)], reverse=True)
    wild = roll_wild_die()

    normal_total = sum(normal_dice)
    removed_die = None

    if wild.complication and normal_dice:
        removed_die = normal_dice[0]
        normal_total -= removed_die

    total = max(1, normal_total + wild.total + pool.pips)

    return RollResult(
        pool=pool,
        normal_dice=normal_dice,
        wild_die=wild,
        pips=pool.pips,
        total=total,
        complication=wild.complication,
        exploded=wild.exploded,
        removed_die=removed_die,
    )


def roll_pool_str(pool_str: str) -> RollResult:
    """Convenience: roll from a string like '4D+2'."""
    return roll_d6_pool(DicePool.parse(pool_str))


# ── Check Functions ──

def difficulty_check(pool: DicePool, target: int) -> CheckResult:
    """Roll a pool against a fixed difficulty number."""
    roll = roll_d6_pool(pool)
    margin = roll.total - target
    return CheckResult(roll=roll, target=target, success=margin >= 0, margin=margin)


def opposed_roll(attacker_pool: DicePool, defender_pool: DicePool) -> OpposedResult:
    """Opposed roll. Ties go to the defender."""
    att_roll = roll_d6_pool(attacker_pool)
    def_roll = roll_d6_pool(defender_pool)
    margin = att_roll.total - def_roll.total
    return OpposedResult(
        attacker_roll=att_roll,
        defender_roll=def_roll,
        attacker_wins=margin > 0,
        margin=margin,
    )


# ── Modifier Helpers ──

def apply_multi_action_penalty(base_pool: DicePool, num_actions: int) -> DicePool:
    """Each action beyond the first = -1D to ALL actions that round."""
    penalty = max(0, num_actions - 1)
    new_dice = max(0, base_pool.dice - penalty)
    return DicePool(new_dice, base_pool.pips if new_dice > 0 else 0)


def apply_wound_penalty(base_pool: DicePool, wound_dice: int) -> DicePool:
    """Apply -XD wound penalty."""
    new_dice = max(0, base_pool.dice - wound_dice)
    return DicePool(new_dice, base_pool.pips if new_dice > 0 else 0)


def apply_scale_modifier(
    base_pool: DicePool,
    attacker_scale: Scale,
    defender_scale: Scale,
) -> DicePool:
    """Add scale difference dice to a pool (for to-hit or damage)."""
    diff = abs(Scale.difference(attacker_scale, defender_scale))
    return DicePool(base_pool.dice + diff, base_pool.pips)


# ── Character Point Dice (R&E p55) ──

def roll_cp_die() -> int:
    """
    Roll one Character Point die.

    Per R&E p55:
      - Roll 1d6 and add to total
      - On 6: add 6 and roll again (exploding, like Wild Die)
      - On 1: just 1 (NO mishap, unlike Wild Die)
    """
    total = 0
    while True:
        r = roll_die()
        total += r
        if r != 6:
            break
    return total


def roll_cp_dice(count: int) -> tuple[int, list[int]]:
    """
    Roll multiple Character Point dice.

    Returns (total_bonus, individual_rolls).
    Each die explodes on 6, no mishap on 1.
    """
    rolls = []
    total = 0
    for _ in range(count):
        r = roll_cp_die()
        rolls.append(r)
        total += r
    return total, rolls


# ── Force Point Pool Doubling (R&E p52) ──

def apply_force_point(pool: DicePool) -> DicePool:
    """
    Double a dice pool for Force Point usage.

    Per R&E p52: "When a character spends a Force Point, they
    double all skill and attribute die codes for that round."

    Note for melee damage: double Strength but NOT the weapon
    bonus (R&E p52 example with vibroaxe).
    """
    return DicePool(pool.dice * 2, pool.pips * 2)
