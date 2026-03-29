"""
Lock Expression System -- Inspired by TinyMUX boolexp.cpp

Composable boolean lock expressions for exits, objects, and rooms.
Supports AND/OR/NOT operations and various check types.

Lock syntax:
  Simple:      @lock exit = admin          (require admin flag)
               @lock exit = builder        (require builder flag)
               @lock exit = species:wookiee (require species match)
               @lock exit = skill:blaster:4D (require skill at level)
               @lock exit = has:keycard     (require carrying object)
               @lock exit = #42            (require specific character ID)

  Compound:    @lock exit = has:keycard & !is_npc
               @lock exit = admin | builder
               @lock exit = species:wookiee | has:disguise
               @lock exit = (has:red_key | has:blue_key) & !wounded

  Special:     @lock exit = open           (always passes)
               @lock exit = locked         (always fails)

Evaluation:
  eval_lock(lock_str, character_dict, db) -> (bool, reason_str)
"""
import json
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


# -- Lock Token Types --

class LockNode:
    """Base class for lock expression AST nodes."""
    def evaluate(self, char: dict, context: dict = None) -> bool:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class LockTrue(LockNode):
    """Always passes (unlocked)."""
    def evaluate(self, char, context=None):
        return True
    def describe(self):
        return "open"


class LockFalse(LockNode):
    """Always fails (locked)."""
    def evaluate(self, char, context=None):
        return False
    def describe(self):
        return "locked"


class LockFlag(LockNode):
    """Check a character flag (admin, builder, force_sensitive)."""
    def __init__(self, flag: str):
        self.flag = flag.lower()

    def evaluate(self, char, context=None):
        if self.flag == "admin":
            # Check via account data if available in context
            return bool(context and context.get("is_admin"))
        elif self.flag == "builder":
            return bool(context and context.get("is_builder"))
        elif self.flag == "force_sensitive":
            return bool(char.get("force_sensitive"))
        elif self.flag == "is_npc":
            return bool(char.get("is_npc"))
        return False

    def describe(self):
        return self.flag


class LockSpecies(LockNode):
    """Check character species."""
    def __init__(self, species: str):
        self.species = species.lower()

    def evaluate(self, char, context=None):
        return char.get("species", "").lower() == self.species

    def describe(self):
        return f"species:{self.species}"


class LockSkill(LockNode):
    """Check that character has minimum skill level."""
    def __init__(self, skill: str, min_dice: int = 1):
        self.skill = skill.lower()
        self.min_dice = min_dice

    def evaluate(self, char, context=None):
        skills = char.get("skills", "{}")
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except (json.JSONDecodeError, TypeError):
                return False
        skill_val = skills.get(self.skill, "")
        if not skill_val:
            return False
        # Parse dice value (e.g. "3D+1" -> 3 dice)
        try:
            dice = int(skill_val.upper().split("D")[0])
            return dice >= self.min_dice
        except (ValueError, IndexError):
            return False

    def describe(self):
        return f"skill:{self.skill}:{self.min_dice}D"


class LockHasObject(LockNode):
    """Check that character is carrying a named object."""
    def __init__(self, object_name: str):
        self.object_name = object_name.lower()

    def evaluate(self, char, context=None):
        # Check inventory
        inventory = char.get("inventory", "[]")
        if isinstance(inventory, str):
            try:
                inventory = json.loads(inventory)
            except (json.JSONDecodeError, TypeError):
                inventory = []
        # Check object names in inventory
        for item in inventory:
            if isinstance(item, dict):
                if item.get("name", "").lower() == self.object_name:
                    return True
            elif isinstance(item, str):
                if item.lower() == self.object_name:
                    return True

        # Check equipped weapon
        equipment = char.get("equipment", "{}")
        if isinstance(equipment, str):
            try:
                equipment = json.loads(equipment)
            except (json.JSONDecodeError, TypeError):
                equipment = {}
        if isinstance(equipment, dict):
            if equipment.get("weapon", "").lower() == self.object_name:
                return True

        return False

    def describe(self):
        return f"has:{self.object_name}"


class LockCharId(LockNode):
    """Check specific character ID."""
    def __init__(self, char_id: int):
        self.char_id = char_id

    def evaluate(self, char, context=None):
        return char.get("id") == self.char_id

    def describe(self):
        return f"#{self.char_id}"


class LockWounded(LockNode):
    """Check if character is wounded (any wound level > 0)."""
    def __init__(self, inverted: bool = False):
        self.inverted = inverted

    def evaluate(self, char, context=None):
        wounded = char.get("wound_level", 0) > 0
        return not wounded if self.inverted else wounded

    def describe(self):
        return "!wounded" if self.inverted else "wounded"


class LockAnd(LockNode):
    """Boolean AND of two lock expressions."""
    def __init__(self, left: LockNode, right: LockNode):
        self.left = left
        self.right = right

    def evaluate(self, char, context=None):
        return self.left.evaluate(char, context) and self.right.evaluate(char, context)

    def describe(self):
        return f"({self.left.describe()} & {self.right.describe()})"


class LockOr(LockNode):
    """Boolean OR of two lock expressions."""
    def __init__(self, left: LockNode, right: LockNode):
        self.left = left
        self.right = right

    def evaluate(self, char, context=None):
        return self.left.evaluate(char, context) or self.right.evaluate(char, context)

    def describe(self):
        return f"({self.left.describe()} | {self.right.describe()})"


class LockNot(LockNode):
    """Boolean NOT of a lock expression."""
    def __init__(self, child: LockNode):
        self.child = child

    def evaluate(self, char, context=None):
        return not self.child.evaluate(char, context)

    def describe(self):
        return f"!{self.child.describe()}"


# -- Parser --

def parse_lock(expr: str) -> LockNode:
    """
    Parse a lock expression string into an AST.

    Grammar (simplified):
      expr     = or_expr
      or_expr  = and_expr ('|' and_expr)*
      and_expr = unary ('&' unary)*
      unary    = '!' unary | atom | '(' expr ')'
      atom     = 'open' | 'locked' | 'admin' | 'builder'
               | 'species:X' | 'skill:X:ND' | 'has:X'
               | '#N' | 'wounded' | 'force_sensitive' | 'is_npc'
    """
    expr = expr.strip()
    if not expr:
        return LockTrue()

    tokens = _tokenize(expr)
    if not tokens:
        return LockTrue()

    pos = [0]  # mutable index for recursive descent
    result = _parse_or(tokens, pos)

    return result


def _tokenize(expr: str) -> list[str]:
    """Split lock expression into tokens."""
    tokens = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c in ' \t':
            i += 1
            continue
        if c in '&|!()':
            tokens.append(c)
            i += 1
            continue
        # Accumulate a word token (may contain : # digits)
        start = i
        while i < len(expr) and expr[i] not in ' \t&|!()':
            i += 1
        tokens.append(expr[start:i])
    return tokens


def _parse_or(tokens: list[str], pos: list[int]) -> LockNode:
    left = _parse_and(tokens, pos)
    while pos[0] < len(tokens) and tokens[pos[0]] == '|':
        pos[0] += 1
        right = _parse_and(tokens, pos)
        left = LockOr(left, right)
    return left


def _parse_and(tokens: list[str], pos: list[int]) -> LockNode:
    left = _parse_unary(tokens, pos)
    while pos[0] < len(tokens) and tokens[pos[0]] == '&':
        pos[0] += 1
        right = _parse_unary(tokens, pos)
        left = LockAnd(left, right)
    return left


def _parse_unary(tokens: list[str], pos: list[int]) -> LockNode:
    if pos[0] >= len(tokens):
        return LockTrue()

    if tokens[pos[0]] == '!':
        pos[0] += 1
        child = _parse_unary(tokens, pos)
        return LockNot(child)

    if tokens[pos[0]] == '(':
        pos[0] += 1
        node = _parse_or(tokens, pos)
        if pos[0] < len(tokens) and tokens[pos[0]] == ')':
            pos[0] += 1
        return node

    return _parse_atom(tokens, pos)


def _parse_atom(tokens: list[str], pos: list[int]) -> LockNode:
    if pos[0] >= len(tokens):
        return LockTrue()

    token = tokens[pos[0]]
    pos[0] += 1

    t = token.lower()

    # Simple keywords
    if t == "open":
        return LockTrue()
    if t == "locked":
        return LockFalse()
    if t in ("admin", "builder"):
        return LockFlag(t)
    if t in ("force_sensitive", "is_npc"):
        return LockFlag(t)
    if t == "wounded":
        return LockWounded()

    # species:X
    if t.startswith("species:"):
        species = token[8:]
        return LockSpecies(species)

    # skill:X:ND
    if t.startswith("skill:"):
        parts = token[6:].split(":")
        skill = parts[0]
        min_dice = 1
        if len(parts) > 1:
            try:
                min_dice = int(parts[1].upper().replace("D", ""))
            except ValueError:
                pass
        return LockSkill(skill, min_dice)

    # has:X
    if t.startswith("has:"):
        return LockHasObject(token[4:])

    # #N (character ID)
    if t.startswith("#"):
        try:
            return LockCharId(int(t[1:]))
        except ValueError:
            pass

    # Unknown token -- treat as a flag check
    return LockFlag(t)


# -- Public API --

def eval_lock(lock_str: str, char: dict, context: dict = None) -> tuple[bool, str]:
    """
    Evaluate a lock expression against a character.

    Args:
        lock_str: The lock expression (e.g. "has:keycard & !wounded")
        char: Character dict (from DB row)
        context: Additional context (is_admin, is_builder, etc.)

    Returns:
        (passed: bool, reason: str)
    """
    if not lock_str or lock_str.strip().lower() == "open":
        return True, ""

    try:
        lock = parse_lock(lock_str)
    except Exception as e:
        log.warning("Failed to parse lock '%s': %s", lock_str, e)
        return False, f"Lock error: {e}"

    passed = lock.evaluate(char, context or {})
    if not passed:
        return False, f"Locked: requires {lock.describe()}"
    return True, ""


def describe_lock(lock_str: str) -> str:
    """Get a human-readable description of a lock expression."""
    if not lock_str or lock_str.strip().lower() == "open":
        return "Open (unlocked)"
    try:
        lock = parse_lock(lock_str)
        return lock.describe()
    except Exception:
        return lock_str
