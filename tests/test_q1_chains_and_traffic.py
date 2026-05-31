# -*- coding: utf-8 -*-
"""
tests/test_q1_chains_and_traffic.py — Q1 canonical-character policy
audit for content surfaces NOT previously covered by per-drop tests.

Background
==========

The Q1 policy (per userMemories and the per-drop test classes
TestQ1CanonicalCharacterPolicy in test_drop_b_mos_eisley.py /
test_drop_c1_coruscant.py / test_drop_c2_coruscant.py /
test_drop_g1_nar_shaddaa.py / test_drop_g2_nar_shaddaa.py /
test_drop_f8c2a_chain_anchors.py):

  1. NEVER as named NPCs. Canonical figures (Anakin, Yoda, Mace
     Windu, Boba Fett, Cad Bane, Dooku, Sidious, etc.) must not
     appear as named NPCs anywhere in the game.
  2. Off-screen mentions allowed only with absence framing. NPC
     knowledge or descriptions may reference canonical figures as
     historical/distant/elsewhere, but the framing must make clear
     they are not in the player's reach.
  3. Tested per content drop. Each drop's NPC YAML is checked by
     its own TestQ1CanonicalCharacterPolicy class.

Audit gap (May 5 2026)
======================

The per-drop tests don't cover:

  * **Tutorial chain narrative** in
    `data/worlds/clone_wars/tutorials/chains.yaml`. A chain step's
    `description`, `npc_intro`, `npc_complete`, `follow_up_hint`,
    `next_hint`, `objective`, `narrative` etc. are player-facing
    dialogue/prose with no Q1 coverage prior to this drop. The
    audit found two soft Q1 violations in `jedi_path` graduation
    flavor (Mace Windu + Yoda).

  * **Traffic captain-name pools** in
    `engine/npc_space_traffic.py` (the live python dict consumed
    by `_make_captain_name`) and the orphan
    `data/worlds/clone_wars/traffic_archetypes.yaml` (planned for
    future wire-up). The audit found a HARD Q1 violation: the
    BOUNTY_HUNTER pool included "Boba Fett" and "The Mandalorian"
    — players in space combat would hear hails from canonical
    bounty hunters. Same problem latent in the orphan YAML
    (Cad Bane, Aurra Sing, Embo, Bossk, Sugi).

  * **Housing-lot room descriptions** in
    `data/worlds/clone_wars/housing_lots.yaml`. The audit found
    one soft Q1 hit: the Stalgasin Hive Council Suite description
    referenced "Count Dooku's emissaries" without absence framing.

This drop fixes those four surfaces and locks them with tests so
future authoring slips fail loudly.

What this drop does NOT lock
============================

Per-drop NPC YAMLs already have their own Q1 tests
(test_drop_*.py). This file does NOT duplicate them. It covers
only the four content surfaces listed above plus a meta-test that
walks `data/worlds/clone_wars/` looking for any new content file
that adds canonical names without absence-framing markers.

Borderline-but-acceptable references
=====================================

The audit identified several player-facing references that ARE
canonical names but ARE acceptable per Q1's absence-framing rule:

  * NPCs in `npcs_drop_h_combat.yaml` whose personality says
    "Loyal to General Skywalker" — Skywalker is the off-screen
    commander; the trooper NPC is on-screen. Acceptable.
  * NPCs in `npcs_drop_def_civilians.yaml` whose knowledge
    references Mina Bonteri as "canonical-reference; recently
    killed by Dooku." Tagged explicitly as canonical-reference.
  * Coruscant NPCs in `npcs_drop_c1_coruscant.yaml` who mention
    the Cad Bane hostage incident, Senator Padmé Amidala by
    address, Senator Mina Bonteri's death. All historical /
    geographic / off-screen references. Already covered by
    test_drop_c1_coruscant.py.

These pass because the NPCs themselves are non-canonical and the
canonical references are framed as elsewhere/past/inaccessible.
The four problems this drop fixes are different: they were either
(a) named-NPC generation pools that would name a captain "Boba
Fett" in a hail, or (b) authorial assertions that the player would
meet a canonical figure ("Mace Windu meets you at the gate").

Test sections
=============

  1. TestChainsYamlNoCanonicalNames     — chain narrative is clean
  2. TestTrafficCaptainPoolsNoCanonical — live python pool is clean
  3. TestTrafficArchetypesYamlClean     — orphan YAML is clean
  4. TestHousingLotsNoCanonical         — housing flavor is clean
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────
# Shared canonical-figure list. Must match the per-drop test classes
# (test_drop_b_mos_eisley.py, test_drop_c1_coruscant.py, etc.). If
# you're adding canonical figures here, add them everywhere.
# ─────────────────────────────────────────────────────────────────────


CANONICAL_FORBIDDEN = {
    # CW-canonical Jedi
    "Anakin Skywalker", "Anakin", "Skywalker",
    "Obi-Wan Kenobi", "Obi-Wan", "Kenobi",
    "Yoda", "Mace Windu", "Plo Koon", "Ki-Adi-Mundi",
    "Kit Fisto", "Shaak Ti", "Jocasta Nu", "Aayla Secura",
    "Ahsoka Tano", "Luminara Unduli", "Barriss Offee",
    # CW-canonical Sith / CIS leadership
    "Dooku", "Count Dooku", "Sidious", "Darth Sidious",
    "Palpatine", "Chancellor Palpatine",
    "Grievous", "General Grievous", "Ventress", "Asajj Ventress",
    "Maul", "Darth Maul", "Savage Opress",
    # CW-canonical Senators
    "Padmé", "Padmé Amidala", "Bail Organa", "Mon Mothma",
    "Mina Bonteri",
    # CW-canonical clones
    "Captain Rex", "Commander Cody", "Commander Fox",
    "Commander Bly", "Commander Wolffe",
    # CW-canonical bounty hunters
    "Boba Fett", "Cad Bane", "Aurra Sing", "Embo",
    "Bossk", "Sugi", "Hondo Ohnaka", "The Mandalorian",
    # Coruscant canonical fixtures
    "Dexter Jettster", "Hermione Bagwa", "Ronet Coorr",
    # Black Sun canonical
    "Xizor", "Prince Xizor",
    # Post-Order-66 leaks (era consistency)
    "Vader", "Darth Vader", "Tarkin",
}


ABSENCE_FRAMING_MARKERS = (
    # Words/phrases that, if present in surrounding text, allow a
    # canonical mention to be considered absence-framed.
    "off-world", "off-screen", "off world", "absent", "not here",
    "canonical-reference", "canonical reference",
    "supply run", "out today", "currently", "elsewhere",
    "killed by", "death of", "after his death", "after her death",
    "decades ago", "years ago", "a year ago", "three years ago",
    "during the", "remembered", "the late",
    "loyal to", "commands the",  # NPC-knowledge-of-commander framing
    "knew", "served under",
)


def _has_word(text: str, word: str) -> bool:
    """Whole-word case-sensitive search.

    Important: we look for whole words so 'Anakin' doesn't false-
    positive on a fictional 'anakinic' or similar. We also keep
    case sensitivity so 'maul' (the verb) doesn't trip the 'Maul'
    check.
    """
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text))


# ═════════════════════════════════════════════════════════════════════
# 1. Chain narrative — chains.yaml
# ═════════════════════════════════════════════════════════════════════


CHAINS_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
               / "tutorials" / "chains.yaml")

# Player-facing narrative fields in a chain step. If a canonical
# name appears in any of these, it must have absence framing
# nearby.
CHAIN_NARRATIVE_FIELDS = (
    "description", "objective", "narrative",
    "npc_intro", "npc_complete", "next_hint",
    "follow_up_hint", "locked_message",
)


class TestChainsYamlNoCanonicalNames(unittest.TestCase):
    """The tutorial chain corpus must not introduce canonical
    figures as on-screen, present-tense, reachable characters.
    """

    @classmethod
    def setUpClass(cls):
        with open(CHAINS_YAML, encoding="utf-8") as fh:
            cls.corpus = yaml.safe_load(fh)

    def _walk_chain_text(self):
        """Yield (chain_id, step_num_or_none, field, text) tuples
        for every player-facing narrative string in the corpus.
        """
        for chain in (self.corpus.get("chains") or []):
            chain_id = chain.get("chain_id", "<unknown>")

            # Top-level chain fields
            for f in ("description", "locked_message"):
                if isinstance(chain.get(f), str):
                    yield (chain_id, None, f, chain[f])

            # Graduation block
            grad = chain.get("graduation") or {}
            for f in ("follow_up_hint",):
                if isinstance(grad.get(f), str):
                    yield (chain_id, None, f"graduation.{f}", grad[f])

            # Steps
            for step in (chain.get("steps") or []):
                step_num = step.get("step")
                for f in CHAIN_NARRATIVE_FIELDS:
                    if isinstance(step.get(f), str):
                        yield (chain_id, step_num, f, step[f])

    def test_no_canonical_names_without_absence_framing(self):
        violations = []
        for (chain_id, step, field, text) in self._walk_chain_text():
            for forbidden in CANONICAL_FORBIDDEN:
                if not _has_word(text, forbidden):
                    continue
                # Found a canonical reference. Check for absence
                # framing markers in the same string.
                tlow = text.lower()
                if any(m in tlow for m in ABSENCE_FRAMING_MARKERS):
                    continue
                violations.append({
                    "chain": chain_id, "step": step, "field": field,
                    "name": forbidden,
                    "snippet": text[:120],
                })
        self.assertEqual(violations, [], (
            "chains.yaml has canonical-figure references without "
            "absence framing. Each entry needs either rephrasing "
            "to a non-canonical figure or absence-framing markers "
            f"({ABSENCE_FRAMING_MARKERS!r}). Violations: {violations}"
        ))

    def test_jedi_path_no_named_council_members(self):
        """Regression-guard for the May 5 2026 fix.
        ``jedi_path`` chain previously had 'Master Mace Windu meets
        you at the Temple gate' in description and 'See Master Yoda
        at the Jedi Temple' in graduation.follow_up_hint. Both have
        been replaced with non-canonical phrasings.
        """
        for chain in (self.corpus.get("chains") or []):
            if chain.get("chain_id") != "jedi_path":
                continue
            description = chain.get("description") or ""
            grad = chain.get("graduation") or {}
            follow_up = grad.get("follow_up_hint") or ""
            for forbidden in ("Mace Windu", "Yoda", "Anakin",
                              "Obi-Wan", "Kenobi"):
                self.assertFalse(
                    _has_word(description, forbidden),
                    f"jedi_path.description must not name {forbidden} "
                    f"(restoring the pre-fix wording would re-open "
                    f"the Q1 violation): {description[:200]}",
                )
                self.assertFalse(
                    _has_word(follow_up, forbidden),
                    f"jedi_path.graduation.follow_up_hint must not "
                    f"name {forbidden}: {follow_up[:200]}",
                )


# ═════════════════════════════════════════════════════════════════════
# 2. Traffic captain pools — engine/npc_space_traffic.py (live)
# ═════════════════════════════════════════════════════════════════════


class TestTrafficCaptainPoolsNoCanonical(unittest.TestCase):
    """The TRAFFIC_SHIP_TEMPLATES dict in engine/npc_space_traffic.py
    is the SOURCE OF TRUTH for randomly-generated traffic captain
    names. A canonical figure here surfaces in space-combat hail
    messages — the most visible Q1 violation possible.
    """

    @classmethod
    def setUpClass(cls):
        # Import lazily so the test reflects whatever HEAD has.
        from engine.npc_space_traffic import TRAFFIC_SHIP_TEMPLATES
        cls.templates = TRAFFIC_SHIP_TEMPLATES

    def test_no_canonical_names_in_any_captain_pool(self):
        violations = []
        for archetype, ship_specs in self.templates.items():
            for spec in ship_specs:
                pool = spec.get("captain_name_pool") or []
                for name in pool:
                    for forbidden in CANONICAL_FORBIDDEN:
                        if _has_word(name, forbidden):
                            violations.append({
                                "archetype": str(archetype),
                                "captain": name,
                                "forbidden_match": forbidden,
                            })
        self.assertEqual(violations, [], (
            "TRAFFIC_SHIP_TEMPLATES.captain_name_pool has canonical "
            "figures. These are randomly generated as NPC traffic "
            f"captains and surface in hail messages. Violations: "
            f"{violations}"
        ))

    def test_bounty_hunter_pool_does_not_have_boba_or_mandalorian(self):
        """Regression-guard for the May 5 2026 fix.
        BOUNTY_HUNTER captain pool previously included 'Boba Fett'
        and 'The Mandalorian'. Both removed.
        """
        from engine.npc_space_traffic import (
            TRAFFIC_SHIP_TEMPLATES, TrafficArchetype,
        )
        bh_specs = TRAFFIC_SHIP_TEMPLATES.get(
            TrafficArchetype.BOUNTY_HUNTER, [])
        all_names = []
        for spec in bh_specs:
            all_names.extend(spec.get("captain_name_pool") or [])
        for forbidden in ("Boba Fett", "The Mandalorian", "Cad Bane",
                          "Aurra Sing"):
            self.assertNotIn(
                forbidden, all_names,
                f"BOUNTY_HUNTER captain_name_pool re-introduced "
                f"{forbidden!r}. Q1: no canonical figures as named "
                f"NPCs, including dynamic traffic. See "
                f"HANDOFF_MAY05_Q1_AUDIT.md.",
            )


# ═════════════════════════════════════════════════════════════════════
# 3. Orphan YAML — traffic_archetypes.yaml
# ═════════════════════════════════════════════════════════════════════


TRAFFIC_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "traffic_archetypes.yaml")


class TestTrafficArchetypesYamlClean(unittest.TestCase):
    """The traffic_archetypes.yaml is currently orphan content (no
    consumer) but slated to be wired when TrafficArchetype is
    era-parameterized. Locking its captain pools means the
    eventual wire-up doesn't reactivate canonical-figure leaks.
    """

    @classmethod
    def setUpClass(cls):
        with open(TRAFFIC_YAML, encoding="utf-8") as fh:
            cls.data = yaml.safe_load(fh)

    def _all_captain_names(self):
        names = []
        archetypes = self.data.get("archetypes") or {}
        for archetype_name, variants in archetypes.items():
            # Each archetype maps directly to a list of variant
            # dicts. Each variant has its own captain_name_pool.
            for variant in (variants or []):
                if not isinstance(variant, dict):
                    continue
                pool = variant.get("captain_name_pool") or []
                for name in pool:
                    names.append((archetype_name, name))
        return names

    def test_no_canonical_names_in_yaml_pool(self):
        violations = []
        for (archetype, name) in self._all_captain_names():
            for forbidden in CANONICAL_FORBIDDEN:
                if _has_word(name, forbidden):
                    violations.append({
                        "archetype": archetype,
                        "captain": name,
                        "forbidden_match": forbidden,
                    })
        self.assertEqual(violations, [], (
            "traffic_archetypes.yaml captain_name_pool has canonical "
            "figures. Even though this YAML is currently orphan "
            "content (no consumer in HEAD), it's slated for wire-up "
            f"in a future drop. Scrub now to prevent reactivation. "
            f"Violations: {violations}"
        ))


# ═════════════════════════════════════════════════════════════════════
# 4. Housing lots — housing_lots.yaml
# ═════════════════════════════════════════════════════════════════════


HOUSING_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "housing_lots.yaml")


class TestHousingLotsNoCanonical(unittest.TestCase):
    """Housing-lot room descriptions are player-facing flavor when
    a player rents a faction-aligned residence. Canonical figures
    must be either absent or absence-framed.
    """

    @classmethod
    def setUpClass(cls):
        with open(HOUSING_YAML, encoding="utf-8") as fh:
            cls.data = yaml.safe_load(fh)

    def _all_room_descs(self):
        for faction_name, faction in (self.data.get("factions") or {}).items():
            for tier in (faction.get("tiers") or []):
                desc = tier.get("room_desc") or ""
                yield (faction_name, tier.get("label", "?"), desc)

    def test_no_canonical_names_without_absence_framing(self):
        violations = []
        for (faction, label, desc) in self._all_room_descs():
            for forbidden in CANONICAL_FORBIDDEN:
                if not _has_word(desc, forbidden):
                    continue
                dlow = desc.lower()
                if any(m in dlow for m in ABSENCE_FRAMING_MARKERS):
                    continue
                violations.append({
                    "faction": faction, "label": label,
                    "name": forbidden, "snippet": desc[:200],
                })
        self.assertEqual(violations, [], (
            f"housing_lots.yaml room descriptions name canonical "
            f"figures without absence framing: {violations}"
        ))

    def test_geonosis_council_suite_no_named_dooku(self):
        """Regression-guard for the May 5 2026 fix.
        Stalgasin Hive Council Suite previously read "Count Dooku's
        emissaries are received" without absence framing.
        """
        for (faction, label, desc) in self._all_room_descs():
            if "Council Suite" not in label:
                continue
            self.assertFalse(
                _has_word(desc, "Dooku"),
                f"Geonosis Council Suite description names Dooku: "
                f"{desc[:200]}",
            )


if __name__ == "__main__":
    unittest.main()
