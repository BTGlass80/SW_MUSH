# -*- coding: utf-8 -*-
"""
engine/creature_special_attacks.py — Sourcebook Enrichment **Lane A tail**:
WEG R&E creature special-attack mechanics (poison DoT + grapple/constriction
restraint).

PURE module (no DB, no IO, no dice rolled here). It owns:

  * the structured specs (``PoisonSpec`` / ``RestraintSpec``),
  * the parsers that read a creature dict's ``special_attack`` block (with a
    prose-inference fallback over ``natural_attack``), and turn it into the
    spawn-sheet-injectable shape,
  * the small *deciders* the combat round-tick needs (break-free outcome,
    damage-string → pool resolution helper), and
  * every player-facing string (all B3/Q1-clean creature language).

WHY THIS EXISTS
---------------
Lane A Phase A/B shipped the faithful creature **library** + the encounter→
spawner bridge + faithful *base* natural-attack damage. But the source stat
blocks carry riders the engine never honored:

  * **Poison** — spor crawler ``Poison 5D``; hitcher crab ``Poison 2D+2``
    (slow-acting). Recorded as prose; mechanically inert (the creature did its
    bare-STR contact and nothing more).
  * **Restraint** — glim worm ``Grapple (opposed brawling)``; voroos
    ``grasp``; stalker lizard ``Constriction STR+2D+2``; somago ``Choking
    attack +3D/round``. Likewise inert — a constrictor squeezed once for its
    base hit, then behaved like any other creature.

Per the WEG-R&E-D6-only approval (2026-06-06), this models exactly two
mechanics, both faithful to R&E:

  * **Poison = damage-over-time.** Each round the venom rolls its damage vs the
    victim's Strength (poison is internal — no armor soak) and applies the
    wound margin on the normal R&E ladder, for a bounded number of rounds.
  * **Restraint = a hold.** A grab pins the victim: they take an attack-pool
    penalty, cannot flee, and struggle (an opposed break-free roll) each round
    until they win or the grappler is gone. *Constriction/choke* restraints
    additionally squeeze for per-round Strength-based damage.

SCOPE / NON-GOALS (deliberate, keeps the drop atomic + schema-free)
  * **In-combat only.** Conditions live on the in-combat Combatant (process
    state), not the persisted Character — matching the codebase's
    restart-clears-combat convention. The source's *out-of-combat* poison
    cadence (spor crawler "every 5 min for 1 hr") is noted in the data but is
    a separate persistence+world-tick feature, not built here.
  * **No WotC mechanics.** Numbers/forms come straight from the WEG creature
    extractions (CotG / Geonosis / Wretched Hive).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────
# Tunable constants (T3.19 will lift these into the tunables file)
# ──────────────────────────────────────────────────────────────────────────

# Default number of in-combat ticks a poison runs if the data omits ``rounds``.
POISON_DEFAULT_ROUNDS = 3
# A restrained combatant attacks at this many fewer dice while held (R&E: a
# grabbed character is badly hampered). Applied to their attack pool only.
GRAPPLE_ATTACK_PENALTY_DICE = 2
# Restraint kinds that squeeze for per-round damage (vs a plain hold).
ESCALATING_KINDS = ("constriction", "choke")


# ──────────────────────────────────────────────────────────────────────────
# Specs (the static, creature-template description)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class PoisonSpec:
    """A creature's poison rider, as a structured spec."""
    damage: str = "0D"          # dice rolled vs the victim's STR each tick
    rounds: int = POISON_DEFAULT_ROUNDS
    onset: int = 0              # rounds before the first tick (slow-acting → 1)
    note: str = ""              # source cadence / flavor

    def to_dict(self) -> dict:
        return {"damage": self.damage, "rounds": int(self.rounds),
                "onset": int(self.onset), "note": self.note}


@dataclass
class RestraintSpec:
    """A creature's grab/constriction rider, as a structured spec."""
    kind: str = "grapple"       # grapple | constriction | choke
    hold_damage: str = ""       # per-round dmg for escalating kinds, e.g. "STR+2D+2"
    note: str = ""

    @property
    def is_escalating(self) -> bool:
        return self.kind.lower() in ESCALATING_KINDS

    def to_dict(self) -> dict:
        return {"kind": self.kind, "hold_damage": self.hold_damage,
                "note": self.note}


# ──────────────────────────────────────────────────────────────────────────
# Prose-inference fallbacks (so a creature authored with *only* prose still
# gets a mechanic; the structured ``special_attack`` block is preferred).
# ──────────────────────────────────────────────────────────────────────────
_POISON_PROSE = re.compile(r"\bpoison\b\s*(\d+\s*D(?:\s*\+\s*\d+)?)", re.I)
_VENOM_PROSE = re.compile(r"\bvenom\b\s*(\d+\s*D(?:\s*\+\s*\d+)?)", re.I)
_GRAPPLE_WORDS = re.compile(r"grapple|grasp|\bweb\b|adhesive|wraps?\b", re.I)
_CONSTRICT_WORDS = re.compile(r"constrict", re.I)
_CHOKE_WORDS = re.compile(r"chok", re.I)


def _na_blob(creature: dict) -> str:
    """All the natural-attack + special text, lower-cased, for prose sniffing."""
    na = creature.get("natural_attack") or {}
    parts = [str(na.get("name") or ""), str(na.get("damage") or "")]
    sp = creature.get("special")
    if isinstance(sp, (list, tuple)):
        parts.extend(str(s) for s in sp)
    elif sp:
        parts.append(str(sp))
    return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# Parsers
# ──────────────────────────────────────────────────────────────────────────
def parse_poison(creature: dict) -> Optional[PoisonSpec]:
    """Return a ``PoisonSpec`` for a creature, or None.

    Structured ``special_attack.poison`` wins; otherwise infer from the
    ``Poison ND`` / ``venom ND`` prose in natural_attack/special.
    """
    sa = creature.get("special_attack") or {}
    p = sa.get("poison")
    if isinstance(p, dict) and p.get("damage"):
        return PoisonSpec(
            damage=str(p.get("damage")),
            rounds=int(p.get("rounds", POISON_DEFAULT_ROUNDS) or POISON_DEFAULT_ROUNDS),
            onset=int(p.get("onset", 0) or 0),
            note=str(p.get("note", "") or ""),
        )
    blob = _na_blob(creature)
    m = _POISON_PROSE.search(blob) or _VENOM_PROSE.search(blob)
    if m:
        dmg = re.sub(r"\s+", "", m.group(1)).upper()
        return PoisonSpec(damage=dmg, rounds=POISON_DEFAULT_ROUNDS, onset=0,
                          note="inferred from source prose")
    return None


def parse_restraint(creature: dict) -> Optional[RestraintSpec]:
    """Return a ``RestraintSpec`` for a creature, or None.

    Structured ``special_attack.restraint`` wins; otherwise infer the kind
    (constriction/choke/grapple) from the natural_attack/special prose.
    """
    sa = creature.get("special_attack") or {}
    r = sa.get("restraint")
    if isinstance(r, dict) and r.get("kind"):
        return RestraintSpec(
            kind=str(r.get("kind")).lower(),
            hold_damage=str(r.get("hold_damage", "") or ""),
            note=str(r.get("note", "") or ""),
        )
    blob = _na_blob(creature)
    if _CONSTRICT_WORDS.search(blob):
        # base damage IS the per-round squeeze for a listed constrictor
        hold = str((creature.get("natural_attack") or {}).get("damage") or "")
        hold = hold if re.match(r"^\s*STR", hold, re.I) else ""
        return RestraintSpec(kind="constriction", hold_damage=hold,
                             note="inferred from source prose")
    if _CHOKE_WORDS.search(blob):
        return RestraintSpec(kind="choke", hold_damage="",
                             note="inferred from source prose")
    if _GRAPPLE_WORDS.search(blob):
        return RestraintSpec(kind="grapple", hold_damage="",
                             note="inferred from source prose")
    return None


def parse_special_attacks(creature: dict) -> dict:
    """Build the sheet-injectable ``special_attack`` dict for a creature.

    Shape (omits absent riders): ``{"poison": {...}, "restraint": {...}}``.
    Consumed by ``creature_library.build_creature_char_sheet`` and rehydrated
    onto ``Character`` by ``from_npc_sheet``.
    """
    out: dict = {}
    p = parse_poison(creature)
    if p:
        out["poison"] = p.to_dict()
    r = parse_restraint(creature)
    if r:
        out["restraint"] = r.to_dict()
    return out


def has_special_attack(creature: dict) -> bool:
    return bool(parse_special_attacks(creature))


# ──────────────────────────────────────────────────────────────────────────
# Active-condition factories (the per-victim, in-combat instances)
# ──────────────────────────────────────────────────────────────────────────
def make_active_poison(spec: dict, source: str = "") -> dict:
    """Turn a poison spec-dict into a live combat condition for a victim."""
    return {
        "damage": str(spec.get("damage", "0D") or "0D"),
        "rounds_left": int(spec.get("rounds", POISON_DEFAULT_ROUNDS) or POISON_DEFAULT_ROUNDS),
        "onset_left": int(spec.get("onset", 0) or 0),
        "source": source or "venom",
    }


def make_active_restraint(spec: dict, grappler_id: int, source: str = "") -> dict:
    """Turn a restraint spec-dict into a live combat condition for a victim."""
    return {
        "grappler_id": int(grappler_id),
        "kind": str(spec.get("kind", "grapple") or "grapple").lower(),
        "hold_damage": str(spec.get("hold_damage", "") or ""),
        "source": source or "the creature",
    }


def restraint_is_escalating(restraint: dict) -> bool:
    return str((restraint or {}).get("kind", "")).lower() in ESCALATING_KINDS


# ──────────────────────────────────────────────────────────────────────────
# Deciders (pure; the runtime supplies the rolled totals)
# ──────────────────────────────────────────────────────────────────────────
def break_free_succeeds(victim_total: int, grappler_total: int) -> bool:
    """Opposed break-free outcome. The holder wins ties (R&E: the grappler
    keeps the hold unless the victim *beats* them)."""
    return int(victim_total) > int(grappler_total)


def resolve_damage_pool(damage_str: str, str_pool):
    """Resolve a ``STR(+ND)(+N)`` / absolute ``ND(+N)`` damage string to a
    ``DicePool``, using ``str_pool`` for the STR component.

    Mirrors the melee STR+bonus grammar in combat._apply_damage so hold-damage
    (e.g. a constrictor's ``STR+2D+2``) resolves identically. Returns the
    DicePool (caller rolls it).
    """
    from engine.dice import DicePool
    raw = str(damage_str or "").strip()
    if not raw:
        return DicePool(0, 0)
    up = raw.upper()
    if up.startswith("STR"):
        bonus = up.replace("STR", "", 1).strip()
        if bonus.startswith("+"):
            bonus = bonus[1:].strip()
        if bonus:
            try:
                bp = DicePool.parse(bonus)
            except Exception:
                bp = DicePool(0, 0)
            return DicePool(str_pool.dice + bp.dice, str_pool.pips + bp.pips)
        return DicePool(str_pool.dice, str_pool.pips)
    try:
        return DicePool.parse(up)
    except Exception:
        return DicePool(0, 0)


# ──────────────────────────────────────────────────────────────────────────
# Player-facing strings (all B3/Q1-clean — generic creature language)
# ──────────────────────────────────────────────────────────────────────────
def poison_inflicted_line(victim_name: str, source: str) -> str:
    return f"  {victim_name} is envenomed by the {source.lower()} — the toxin starts to work."


def poison_tick_line(victim_name: str, wound_text: str) -> str:
    if wound_text.lower() in ("no damage", "stunned"):
        return f"  The venom burns through {victim_name} ({wound_text})."
    return f"  The venom courses through {victim_name} — {wound_text}!"


def poison_faded_line(victim_name: str) -> str:
    return f"  The venom in {victim_name}'s blood finally runs its course."


_GRAB_VERB = {
    "grapple": "seizes and pins",
    "constriction": "coils around and crushes",
    "choke": "latches onto and chokes",
}


def grabbed_line(victim_name: str, grappler_name: str, kind: str) -> str:
    verb = _GRAB_VERB.get(kind.lower(), "seizes and pins")
    return f"  {grappler_name} {verb} {victim_name} — they are caught fast!"


def squeeze_tick_line(victim_name: str, kind: str, wound_text: str) -> str:
    word = "constriction" if kind.lower() == "constriction" else "choke-hold"
    if wound_text.lower() in ("no damage", "stunned"):
        return f"  The {word} tightens on {victim_name} ({wound_text})."
    return f"  The {word} crushes {victim_name} — {wound_text}!"


def break_free_success_line(victim_name: str) -> str:
    return f"  {victim_name} wrenches free of the hold!"


def break_free_fail_line(victim_name: str) -> str:
    return f"  {victim_name} struggles but cannot break the hold."


def restraint_released_line(victim_name: str) -> str:
    return f"  The hold on {victim_name} goes slack."


def cannot_flee_grappled_line(actor_name: str) -> str:
    return f"  {actor_name} cannot break away — they are held fast! (break free first)"
