# -*- coding: utf-8 -*-
"""
tests/test_questline_foil_winnability_band.py — balance-integrity guard for the
T3.24 freelance-questline COMBAT foils (OpusLoop quality lane, 2026-06-27).

WHAT GAP THIS CLOSES
--------------------
Most freelance accessible questlines (`npcs_drop_generalized_questline_*.yaml`)
end on a `combat_won` step against a single hand-authored antagonist NPC tagged
`ai_config.chain_enemy_template`. Across the eleven combat arcs those foils were
deliberately stat-matched to one tight "antagonist band" — blaster ~4D, dodge
~3D+2, brawling ~4D+1, Strength ~3D+1, a pistol sidearm — so a fresh
`chargen_complete` character with a blaster can always win the confrontation
beat. But NOTHING pinned that band. Each per-arc slice test only walks its own
combat step to completion in the harness (which auto-resolves the fight); none
asserts the foil is actually WINNABLE for a real player. The loop adds a
freelance arc most fires, each authored from a sibling, so a single fat-fingered
foil — a `blaster: 6D`, a `dodge: 5D`, a `blaster_rifle` instead of a pistol —
would ship a combat step a new player physically cannot beat: a SOFT-LOCK in the
open world, the exact failure class the tutorial combat-sim drive spent days
fixing (the sim was unwinnable; see CHANGELOG 2026-06-27 "sim drill is now
WINNABLE"). The unit suite is blind to it because the harness never rolls dice.
This guard makes that drift fail loudly, at build time, on data alone.

THE WINNABILITY CONTRACT (absolute ceilings — the real protection)
------------------------------------------------------------------
A foil is winnable for a competent fresh character with a blaster when its
to-hit, defense, melee, and toughness all sit under a "fair fight" ceiling and
it carries a sidearm, not a heavy weapon that one-shots a starting character.
The ceilings below sit a comfortable margin ABOVE the shipped band (which all
passes with headroom) and well below "unwinnable", so a future foil authored to
match the band passes, while a gross outlier fails:

  to-hit (blaster)   <= 5D     (shipped max 4D+1; +2 headroom)
  defense (dodge)    <= 4D+1   (shipped max 3D+2; +2 headroom)
  melee (brawling)   <= 5D     (shipped max 4D+2; +1 headroom)
  toughness (Str)    <= 4D     (shipped max 3D+2; +1 headroom)
  sidearm in {blaster_pistol, heavy_blaster_pistol}

ASYMMETRY VS THE REWARD GUARD (intentional)
-------------------------------------------
test_questline_reward_tier_consistency is self-calibrating: a deliberate reward
rebalance of a whole tier passes untouched, because rewards drifting up together
is harmless. Combat difficulty is different — a ceiling is a WINNABILITY CLIFF,
so the ceilings here are hard absolutes. A deliberate galaxy-wide difficulty
rebalance SHOULD trip this and require a conscious one-line edit to the ceiling;
that sign-off is the point, not a nuisance. A light to-hit FLOOR keeps the fight
non-vacuous (a `combat_won` beat should be a real fight, not a 1D pushover); it
mirrors the corpus-wide anti-vacuous-combat reachability invariant.

CLUSTER CONSISTENCY (self-calibrating, softer)
----------------------------------------------
Beyond the absolute ceilings, the foils should stay clustered: the per-stat
spread across the corpus stays small, so a foil that is technically under the
ceiling but wildly off its peers (e.g. everyone at 4D, one at 5D) also surfaces.
This reads the spread FROM the corpus, so a coordinated band shift passes.

Pure data/test guard: no engine, parser, data, or client change.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

QUESTLINE_NPC_GLOB = "npcs_drop_generalized_questline_*.yaml"
NPC_DIR = PROJECT_ROOT / "data" / "worlds" / "clone_wars"

# --- dice helpers ---------------------------------------------------------
_DICE_RE = re.compile(r"\s*(\d+)D(?:\+(\d+))?\s*\Z")


def _pips(code) -> int:
    """'4D+1' -> 13, '3D' -> 9 (pips = 3*dice + pips). Total order on D6 codes."""
    m = _DICE_RE.match(str(code))
    if not m:
        raise ValueError(f"un-parseable D6 code: {code!r}")
    return int(m.group(1)) * 3 + int(m.group(2) or 0)


def _code(pips: int) -> str:
    """Render pips back to a readable 'ND+P' for failure messages."""
    return f"{pips // 3}D" + (f"+{pips % 3}" if pips % 3 else "")


# --- the winnability contract (in pips) -----------------------------------
TO_HIT_CEIL = _pips("5D")      # 15
TO_HIT_FLOOR = _pips("3D+1")   # 10 — anti-vacuous, generous
DODGE_CEIL = _pips("4D+1")     # 13
BRAWL_CEIL = _pips("5D")       # 15
STRENGTH_CEIL = _pips("4D")    # 12
CLUSTER_SPREAD_MAX = 4         # pips; shipped max spread is 2

ALLOWED_SIDEARMS = {"blaster_pistol", "heavy_blaster_pistol"}


def _load_foils():
    """Every freelance-questline foil: the NPCs carrying a chain_enemy_template.

    Returns a list of (arc, name, char_sheet, ai_config) tuples.
    """
    foils = []
    for path in sorted(NPC_DIR.glob(QUESTLINE_NPC_GLOB)):
        arc = path.name.split("questline_", 1)[1].replace(".yaml", "")
        for doc in yaml.safe_load_all(open(path, encoding="utf-8")):
            if not isinstance(doc, dict):
                continue
            for npc in doc.get("npcs") or []:
                ai = npc.get("ai_config") or {}
                if not ai.get("chain_enemy_template"):
                    continue
                foils.append((arc, npc.get("name"),
                              npc.get("char_sheet") or {}, ai))
    return foils


class _Corpus(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.foils = _load_foils()

    @staticmethod
    def _attr(cs, key):
        return (cs.get("attributes") or {}).get(key)

    @staticmethod
    def _skill(cs, key):
        return (cs.get("skills") or {}).get(key)


class TestCorpusIsReal(_Corpus):

    def test_foil_corpus_non_vacuous(self):
        # Eleven combat arcs ship today (Sealed Ledger #9 is deliberately
        # combat-free). Guard against the glob/marker silently matching nothing.
        self.assertGreaterEqual(
            len(self.foils), 10,
            "expected the freelance-questline combat foils; the glob or the "
            "chain_enemy_template marker may have drifted")

    def test_every_foil_is_a_hostile_combatant(self):
        # A combat-step foil that is not hostile would never engage — the step
        # could not be won the intended way. Cheap producer-sanity.
        for arc, name, _cs, ai in self.foils:
            self.assertTrue(
                ai.get("hostile") is True,
                f"{arc}: foil {name!r} is tagged chain_enemy_template but is "
                "not ai_config.hostile — the combat step cannot resolve")


class TestWinnabilityCeilings(_Corpus):
    """Absolute 'a fresh character can win this' ceilings — the real guard."""

    def test_to_hit_under_ceiling_and_non_vacuous(self):
        for arc, name, cs, _ai in self.foils:
            blaster = self._skill(cs, "blaster")
            self.assertIsNotNone(
                blaster, f"{arc}: foil {name!r} has no blaster skill")
            p = _pips(blaster)
            self.assertLessEqual(
                p, TO_HIT_CEIL,
                f"{arc}: foil {name!r} blaster {blaster} ({_code(p)}) exceeds "
                f"the winnable to-hit ceiling {_code(TO_HIT_CEIL)} — a fresh "
                "character would be hit nearly every round (unwinnable). If "
                "this is a deliberate galaxy-wide difficulty rebalance, raise "
                "TO_HIT_CEIL consciously.")
            self.assertGreaterEqual(
                p, TO_HIT_FLOOR,
                f"{arc}: foil {name!r} blaster {blaster} ({_code(p)}) is below "
                f"the anti-vacuous floor {_code(TO_HIT_FLOOR)} — the combat "
                "beat would be a pushover, not a real fight")

    def test_dodge_under_ceiling(self):
        for arc, name, cs, _ai in self.foils:
            dodge = self._skill(cs, "dodge")
            if dodge is None:
                continue  # no dodge = easier, never a winnability problem
            p = _pips(dodge)
            self.assertLessEqual(
                p, DODGE_CEIL,
                f"{arc}: foil {name!r} dodge {dodge} ({_code(p)}) exceeds the "
                f"winnable defense ceiling {_code(DODGE_CEIL)} — a fresh "
                "character could rarely land a hit (stalemate / loss)")

    def test_brawling_under_ceiling(self):
        for arc, name, cs, _ai in self.foils:
            brawl = self._skill(cs, "brawling")
            if brawl is None:
                continue
            p = _pips(brawl)
            self.assertLessEqual(
                p, BRAWL_CEIL,
                f"{arc}: foil {name!r} brawling {brawl} ({_code(p)}) exceeds "
                f"the winnable melee ceiling {_code(BRAWL_CEIL)}")

    def test_strength_soak_under_ceiling(self):
        for arc, name, cs, _ai in self.foils:
            strength = self._attr(cs, "strength")
            if strength is None:
                continue
            p = _pips(strength)
            self.assertLessEqual(
                p, STRENGTH_CEIL,
                f"{arc}: foil {name!r} Strength {strength} ({_code(p)}) exceeds "
                f"the soak ceiling {_code(STRENGTH_CEIL)} — a starting blaster "
                "could barely register a wound on it")

    def test_weapon_is_a_winnable_sidearm(self):
        for arc, name, cs, _ai in self.foils:
            weapon = cs.get("weapon")
            self.assertIn(
                weapon, ALLOWED_SIDEARMS,
                f"{arc}: foil {name!r} carries {weapon!r}, outside the winnable "
                f"sidearm set {sorted(ALLOWED_SIDEARMS)} — a heavy weapon or "
                "rifle can one-shot a fresh character (unwinnable confrontation)")


class TestClusterConsistency(_Corpus):
    """Self-calibrating: the foils stay a tight band (a coordinated shift OK)."""

    def _spread(self, getter):
        vals = []
        for _arc, _name, cs, _ai in self.foils:
            raw = getter(cs)
            if raw is not None:
                vals.append(_pips(raw))
        return (min(vals), max(vals)) if vals else (0, 0)

    def test_to_hit_cluster_is_tight(self):
        lo, hi = self._spread(lambda cs: self._skill(cs, "blaster"))
        self.assertLessEqual(
            hi - lo, CLUSTER_SPREAD_MAX,
            f"foil blaster spread {_code(lo)}..{_code(hi)} exceeds "
            f"{CLUSTER_SPREAD_MAX} pips — one foil is an outlier from the band")

    def test_strength_cluster_is_tight(self):
        lo, hi = self._spread(lambda cs: self._attr(cs, "strength"))
        self.assertLessEqual(
            hi - lo, CLUSTER_SPREAD_MAX,
            f"foil Strength spread {_code(lo)}..{_code(hi)} exceeds "
            f"{CLUSTER_SPREAD_MAX} pips — one foil is an outlier from the band")


class TestContractSanity(unittest.TestCase):
    """The ceilings must actually sit above the shipped band (no false pass)."""

    def test_ceilings_clear_the_shipped_maxima(self):
        foils = _load_foils()
        def mx(getter):
            return max((_pips(v) for v in (getter(cs) for _a, _n, cs, _ai
                       in foils) if v is not None), default=0)
        self.assertLess(mx(lambda cs: (cs.get("skills") or {}).get("blaster")),
                        TO_HIT_CEIL)
        self.assertLessEqual(
            mx(lambda cs: (cs.get("skills") or {}).get("dodge")), DODGE_CEIL)
        self.assertLessEqual(
            mx(lambda cs: (cs.get("attributes") or {}).get("strength")),
            STRENGTH_CEIL)


if __name__ == "__main__":
    unittest.main()
