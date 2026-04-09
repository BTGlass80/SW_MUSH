#!/usr/bin/env python3
"""
Combat UX Drop 7 — Verb variety, margin flavor, wound escalation drama
Target: engine/combat.py

CRLF-safe: normalizes Windows line endings on read, writes LF on output.

Changes:
  1. Add _VERB_POOLS dict and _pick_verb() helper after _wound_color()
  2. Add _miss_flavor() and _wound_drama() helpers
  3. Replace 'verb = "fires at"...' in _apply_damage with _pick_verb()
  4. Add margin flavor to ranged miss narrative
  5. Add margin flavor to melee miss narrative
  6. Add wound escalation drama line in _apply_damage for Wounded Twice+
"""

import ast, shutil
from pathlib import Path

TARGET = Path("engine/combat.py")
BACKUP = Path("engine/combat.py.bak_drop7")


def load(p):
    """Read file and normalize CRLF -> LF."""
    text = p.read_bytes().decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def save(p, t):
    """Write file with LF line endings."""
    p.write_bytes(t.encode("utf-8"))


def validate(text, label):
    try:
        ast.parse(text)
        print(f"  [OK] AST valid: {label}")
    except SyntaxError as e:
        raise SystemExit(f"  [FAIL] Syntax error in {label}: {e}")


def apply(src, old, new, label):
    if old not in src:
        raise SystemExit(f"  [FAIL] Anchor not found: {label!r}")
    count = src.count(old)
    if count > 1:
        raise SystemExit(f"  [FAIL] Anchor matched {count} times: {label!r}")
    print(f"  [PATCH] {label}")
    return src.replace(old, new, 1)


# ── 1. Verb + flavor helpers ─────────────────────────────────────────────────
# Insert between _wound_color's closing line and class CombatPhase

HELPERS_OLD = (
    '        return _ansi.BOLD + _ansi.color(wound_text, _ansi.BRIGHT_RED) + _ansi.RESET\n'
    '    return wound_text\n'
    '\n'
    '\n'
    'class CombatPhase(Enum):'
)

HELPERS_NEW = (
    '        return _ansi.BOLD + _ansi.color(wound_text, _ansi.BRIGHT_RED) + _ansi.RESET\n'
    '    return wound_text\n'
    '\n'
    '\n'
    '# \u2500\u2500 Narrative variety pools \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '\n'
    '_VERB_POOLS: dict[str, list[str]] = {\n'
    '    # ranged\n'
    '    "blaster":          ["fires at", "shoots at", "blasts at", "takes a shot at"],\n'
    '    "bowcaster":        ["fires at", "looses a bolt at", "shoots at"],\n'
    '    "firearms":         ["fires at", "shoots at", "squeezes off a shot at"],\n'
    '    "blaster artillery":["fires at", "unleashes a barrage at"],\n'
    '    "missile weapons":  ["fires a missile at", "launches at"],\n'
    '    "grenade":          ["hurls a grenade at", "lobs at"],\n'
    '    # melee\n'
    '    "melee combat":     ["swings at", "slashes at", "thrusts at", "jabs at"],\n'
    '    "brawling":         ["punches at", "throws a fist at", "swings at", "lunges at"],\n'
    '    "lightsaber":       ["slashes at", "swings at", "lunges at", "strikes at"],\n'
    '}\n'
    '_VERB_RANGED_DEFAULT = ["fires at", "shoots at"]\n'
    '_VERB_MELEE_DEFAULT  = ["swings at", "strikes at"]\n'
    '\n'
    '_MISS_FLAVOR_CLOSE = [\n'
    '    "barely misses!", "the shot goes just wide!",\n'
    '    "grazes the air!", "skims past!",\n'
    ']\n'
    '_MISS_FLAVOR_WIDE = [\n'
    '    "misses wildly!", "the shot sails well past!",\n'
    '    "goes wide by a mile!", "fails to connect!",\n'
    ']\n'
    '_MISS_FLAVOR_MELEE_CLOSE = [\n'
    '    "barely misses!", "the strike glances off!",\n'
    '    "almost connects!", "scrapes past!",\n'
    ']\n'
    '_MISS_FLAVOR_MELEE_WIDE = [\n'
    '    "misses badly!", "the blow falls short!",\n'
    '    "swings wide!", "fails to connect!",\n'
    ']\n'
    '\n'
    '_WOUND_DRAMA: dict[str, list[str]] = {\n'
    '    "wounded twice":    [\n'
    '        "staggers, struggling to stay on their feet.",\n'
    '        "is badly hurt \u2014 still fighting but barely.",\n'
    '        "grits through the pain and keeps going.",\n'
    '    ],\n'
    '    "incapacitated":    [\n'
    '        "collapses, unable to continue.",\n'
    '        "goes down hard.",\n'
    '        "is out of the fight.",\n'
    '    ],\n'
    '    "mortally wounded": [\n'
    '        "crumples, clinging to life by a thread.",\n'
    '        "falls \u2014 it does not look good.",\n'
    '        "is mortally wounded and fading fast.",\n'
    '    ],\n'
    '}\n'
    '\n'
    '\n'
    'def _pick_verb(skill: str, seed: int) -> str:\n'
    '    """Pick an attack verb for a skill, seeded for reproducibility."""\n'
    '    pool = _VERB_POOLS.get(skill.lower())\n'
    '    if pool is None:\n'
    '        pool = _VERB_RANGED_DEFAULT if is_ranged_skill(skill) else _VERB_MELEE_DEFAULT\n'
    '    return pool[seed % len(pool)]\n'
    '\n'
    '\n'
    'def _miss_flavor(margin: int, ranged: bool) -> str:\n'
    '    """Return a short miss descriptor based on how badly the roll missed."""\n'
    '    if ranged:\n'
    '        pool = _MISS_FLAVOR_CLOSE if margin <= 3 else _MISS_FLAVOR_WIDE\n'
    '    else:\n'
    '        pool = _MISS_FLAVOR_MELEE_CLOSE if margin <= 3 else _MISS_FLAVOR_MELEE_WIDE\n'
    '    return pool[margin % len(pool)]\n'
    '\n'
    '\n'
    'def _wound_drama(wound_text: str, target_name: str, seed: int) -> str:\n'
    '    """Return an optional drama beat for severe wounds, or empty string."""\n'
    '    pool = _WOUND_DRAMA.get(wound_text.lower())\n'
    '    if not pool:\n'
    '        return ""\n'
    '    return f"  {target_name} {pool[seed % len(pool)]}"\n'
    '\n'
    '\n'
    'class CombatPhase(Enum):'
)

# ── 2. Replace verb= line and add drama in _apply_damage ─────────────────────

APPLY_VERB_OLD = (
    '        verb = "fires at" if is_ranged_skill(action.skill) else "strikes"\n'
    '        fp_tag = " [FORCE POINT]" if actor.force_point_active else ""\n'
    '\n'
    '        # 2-line narrative: story (bold) + mechanics (dim)\n'
    '        colored_wound = _wound_color(wound_text)\n'
    '        outcome_tag = "HIT \u2014 " + colored_wound + "!"\n'
    '\n'
    '        story_line = (\n'
    '            _ansi.BOLD\n'
    '            + f"  \u25b8 {actor.name} {verb} {target_c.name}"\n'
    '            + f" with {action.skill} \u2014 {outcome_tag}"\n'
    '            + fp_tag\n'
    '            + _ansi.RESET\n'
    '        )\n'
    '        mech_line = _ansi.color(\n'
    '            f"    (Roll: {attack_total}{cp_text} vs {defense_display}"\n'
    '            f" \u00b7 Damage {damage_roll.total} vs Soak {soak_roll.total}"\n'
    '            f" \u2192 {wound_text})",\n'
    '            _ansi.DIM,\n'
    '        )\n'
    '        narrative = story_line + "\\n" + mech_line\n'
    '\n'
    '        if not target.wound_level.can_act:\n'
    '            incap_line = (\n'
    '                _ansi.BOLD + _ansi.BRIGHT_RED\n'
    '                + f"  {target_c.name} is {wound.display_name.upper()}!"\n'
    '                + _ansi.RESET\n'
    '            )\n'
    '            narrative += "\\n" + incap_line'
)

APPLY_VERB_NEW = (
    '        # Verb variety seeded on round + actor id for reproducibility\n'
    '        _seed = (getattr(self, "round_num", 0) * 31 + actor.id) & 0xFFFF\n'
    '        verb = _pick_verb(action.skill, _seed)\n'
    '        fp_tag = " [FORCE POINT]" if actor.force_point_active else ""\n'
    '\n'
    '        # 2-line narrative: story (bold) + mechanics (dim)\n'
    '        colored_wound = _wound_color(wound_text)\n'
    '        outcome_tag = "HIT \u2014 " + colored_wound + "!"\n'
    '\n'
    '        story_line = (\n'
    '            _ansi.BOLD\n'
    '            + f"  \u25b8 {actor.name} {verb} {target_c.name}"\n'
    '            + f" with {action.skill} \u2014 {outcome_tag}"\n'
    '            + fp_tag\n'
    '            + _ansi.RESET\n'
    '        )\n'
    '        mech_line = _ansi.color(\n'
    '            f"    (Roll: {attack_total}{cp_text} vs {defense_display}"\n'
    '            f" \u00b7 Damage {damage_roll.total} vs Soak {soak_roll.total}"\n'
    '            f" \u2192 {wound_text})",\n'
    '            _ansi.DIM,\n'
    '        )\n'
    '        narrative = story_line + "\\n" + mech_line\n'
    '\n'
    '        # Wound escalation drama for severe wounds\n'
    '        drama = _wound_drama(wound_text, target_c.name, _seed)\n'
    '        if drama:\n'
    '            narrative += "\\n" + _ansi.color(drama, _ansi.DIM)\n'
    '\n'
    '        if not target.wound_level.can_act:\n'
    '            incap_line = (\n'
    '                _ansi.BOLD + _ansi.BRIGHT_RED\n'
    '                + f"  {target_c.name} is {wound.display_name.upper()}!"\n'
    '                + _ansi.RESET\n'
    '            )\n'
    '            narrative += "\\n" + incap_line'
)

# ── 3. Add margin flavor to ranged miss ───────────────────────────────────────

RANGED_MISS_OLD = (
    '        if not hit:\n'
    '            fp_tag = " [FORCE POINT]" if actor.force_point_active else ""\n'
    '            story = (\n'
    '                _ansi.DIM\n'
    '                + f"  {actor.name} fires at {target_c.name}"\n'
    '                + f" with {action.skill} \u2014 miss{fp_tag}"\n'
    '                + _ansi.RESET\n'
    '            )\n'
    '            mech = _ansi.color(\n'
    '                f"    (Roll: {attack_total}{cp_text} vs Diff: {diff_display})",\n'
    '                _ansi.DIM,\n'
    '            )\n'
    '            return ActionResult(\n'
    '                actor_id=actor.id, action=action, success=False,\n'
    '                roll_display=attack_roll.display(),\n'
    '                defense_display=diff_display,\n'
    '                margin=total_difficulty - attack_total,\n'
    '                narrative=story + "\\n" + mech,\n'
    '            )'
)

RANGED_MISS_NEW = (
    '        if not hit:\n'
    '            _miss_margin = total_difficulty - attack_total\n'
    '            _rseed = (getattr(self, "round_num", 0) * 31 + actor.id) & 0xFFFF\n'
    '            _rverb = _pick_verb(action.skill, _rseed)\n'
    '            fp_tag = " [FORCE POINT]" if actor.force_point_active else ""\n'
    '            flavor = _miss_flavor(_miss_margin, ranged=True)\n'
    '            story = (\n'
    '                _ansi.DIM\n'
    '                + f"  {actor.name} {_rverb} {target_c.name}"\n'
    '                + f" with {action.skill} \u2014 {flavor}{fp_tag}"\n'
    '                + _ansi.RESET\n'
    '            )\n'
    '            mech = _ansi.color(\n'
    '                f"    (Roll: {attack_total}{cp_text} vs Diff: {diff_display})",\n'
    '                _ansi.DIM,\n'
    '            )\n'
    '            return ActionResult(\n'
    '                actor_id=actor.id, action=action, success=False,\n'
    '                roll_display=attack_roll.display(),\n'
    '                defense_display=diff_display,\n'
    '                margin=_miss_margin,\n'
    '                narrative=story + "\\n" + mech,\n'
    '            )'
)

# ── 4. Add margin flavor to melee miss ───────────────────────────────────────

MELEE_MISS_OLD = (
    '        if not attacker_wins:\n'
    '            fp_tag = " [FORCE POINT]" if actor.force_point_active else ""\n'
    '            story = (\n'
    '                _ansi.DIM\n'
    '                + f"  {actor.name} strikes at {target_c.name}"\n'
    '                + f" with {action.skill} \u2014 miss{fp_tag}"\n'
    '                + _ansi.RESET\n'
    '            )\n'
    '            mech = _ansi.color(\n'
    '                f"    (Attack: {attack_total}{cp_text} vs"\n'
    '                f" {def_label}: {result.defender_roll.total})",\n'
    '                _ansi.DIM,\n'
    '            )\n'
    '            return ActionResult(\n'
    '                actor_id=actor.id, action=action, success=False,\n'
    '                roll_display=result.attacker_roll.display(),\n'
    '                defense_display=result.defender_roll.display(),\n'
    '                margin=result.defender_roll.total - attack_total,\n'
    '                narrative=story + "\\n" + mech,\n'
    '            )'
)

MELEE_MISS_NEW = (
    '        if not attacker_wins:\n'
    '            _miss_margin = result.defender_roll.total - attack_total\n'
    '            _mseed = (getattr(self, "round_num", 0) * 31 + actor.id) & 0xFFFF\n'
    '            _mverb = _pick_verb(action.skill, _mseed)\n'
    '            fp_tag = " [FORCE POINT]" if actor.force_point_active else ""\n'
    '            flavor = _miss_flavor(_miss_margin, ranged=False)\n'
    '            story = (\n'
    '                _ansi.DIM\n'
    '                + f"  {actor.name} {_mverb} {target_c.name}"\n'
    '                + f" with {action.skill} \u2014 {flavor}{fp_tag}"\n'
    '                + _ansi.RESET\n'
    '            )\n'
    '            mech = _ansi.color(\n'
    '                f"    (Attack: {attack_total}{cp_text} vs"\n'
    '                f" {def_label}: {result.defender_roll.total})",\n'
    '                _ansi.DIM,\n'
    '            )\n'
    '            return ActionResult(\n'
    '                actor_id=actor.id, action=action, success=False,\n'
    '                roll_display=result.attacker_roll.display(),\n'
    '                defense_display=result.defender_roll.display(),\n'
    '                margin=_miss_margin,\n'
    '                narrative=story + "\\n" + mech,\n'
    '            )'
)


def main():
    if not TARGET.exists():
        raise SystemExit(f"Target not found: {TARGET}")
    print(f"Backing up {TARGET} -> {BACKUP}")
    shutil.copy2(TARGET, BACKUP)

    src = load(TARGET)   # CRLF normalized to LF here
    src = apply(src, HELPERS_OLD,     HELPERS_NEW,     "verb/flavor/drama helpers")
    src = apply(src, APPLY_VERB_OLD,  APPLY_VERB_NEW,  "_apply_damage verb + drama")
    src = apply(src, RANGED_MISS_OLD, RANGED_MISS_NEW, "ranged miss flavor")
    src = apply(src, MELEE_MISS_OLD,  MELEE_MISS_NEW,  "melee miss flavor")

    validate(src, "patched engine/combat.py")
    save(TARGET, src)    # Written as LF — Python handles this fine on Windows
    print(f"\nDrop 7 complete -> {TARGET}")


if __name__ == "__main__":
    main()
