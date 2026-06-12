# -*- coding: utf-8 -*-
"""
tests/test_q1_2_extended_sweep.py — Q1.2 extended canonical-character
policy audit for the surfaces called out in
``sw_d6_mush_architecture_v42.md §1.5`` as "Q1.2 extended sweep."

Background
==========

Q1 (canonical Star Wars character policy) has been audited iteratively:

  * ``test_drop_*.py::TestQ1CanonicalCharacterPolicy`` — per-content-drop
    audits of NPC YAMLs.
  * ``test_q1_chains_and_traffic.py`` (May 5 Q1.1) — tutorial chain
    narrative, traffic captain-name pools, traffic_archetypes orphan
    YAML, housing-lot descriptions.
  * ``test_q1_scenes_and_planets.py`` (May 17 Q1.1.scenes) — live engine
    scenes (Path A reception, Apprentice Forge), ``path`` parser help
    text, Kamino room descriptions.

v42 §1.5 identified the remaining Q1.2 surface — content that hadn't
been swept end-to-end:

  * ``engine/missions.py`` + content YAML
  * ``engine/encounter_*.py``
  * ``engine/combat_flavor.py``
  * ``engine/spacer_quest.py``
  * ``data/worlds/<era>/director_config.yaml``
  * Tutorial chain step description/objective fields beyond the
    locked jedi_path chain

This drop's pre-flight audit found four discrete violations across the
broader content surface (the engine Python files were already clean
per AST-string-literal walk, but no test was locking them clean):

  1. ``data/worlds/clone_wars/organizations.yaml`` — Sith faction
     ``properties.description``: present-tense "Count Dooku is publicly
     a Separatist leader; privately he is Darth Tyranus, Sith Lord.
     Darth Sidious controls the Republic from within." This field is
     not surfaced by ``format_faction_list`` today, but it is loaded by
     the org bootstrapper into the SQLite ``organizations`` table; a
     future drop that adds an ``+org info`` or ``+faction info`` view
     would surface it directly. v42 §6.2 "dual-source drift" risk.
  2. ``data/worlds/clone_wars/organizations.yaml`` — Separatist Council
     ``properties.description``: present-tense list of canonical
     oligarchs (Nute Gunray, Wat Tambor, San Hill, Poggle the Lesser).
     Same status and same dual-source-drift risk.
  3. ``data/worlds/clone_wars/npcs_drop_f8c2a_chain_anchors.yaml`` L615
     — Poggle the Lesser and Sebulba in present tense in NPC knowledge.
     The existing ``test_drop_f8c2a_chain_anchors.py::TestQ1CanonicalCharacterPolicy
     ::test_canonical_mentions_have_absence_framing`` passes because the
     test aggregates description + personality + knowledge into a single
     text blob and the absence-markers from L614 (Count Dooku "is not
     present at this time", "next visit") count for L615 too. Read in
     isolation, L615 placed Poggle as currently active political senior
     with the cadre operating with his clearance — present-tense without
     the absence marker its sibling line correctly carries. Targeted
     per-line absence-framing was added.
  4. ``data/worlds/gcw/director_config.yaml`` L158 — ``hutt_takeover``
     milestone headline: "Jabba's enforcers patrol the streets. The
     Empire has lost control." Two issues: (a) Q1 — present-tense
     possessive activity attribution to a canonical figure; (b)
     chronology — GCW spans ~0 BBY to ~5 ABY and Jabba dies at ROTJ
     (4 ABY), so even a thresholded headline that fires late in the
     era can be temporally inconsistent. Replaced with the parallel
     L150 phrasing pattern ("Cartel enforcers patrol the streets
     openly"), which removes the canonical reference and matches the
     style already established for the ``underworld_rising`` headline
     at the lower threshold.

This drop locks all four fixes with targeted regression guards plus
general-sweep tests across the v42 §1.5 Q1.2 surface.

What this drop explicitly does NOT do
=====================================

  * Does NOT reframe ``data/worlds/clone_wars/lore.yaml``. The pre-flight
    audit's initial scan flagged ~80 canonical-figure references in this
    file, but on closer inspection these are *encyclopedia entries* —
    third-person factual descriptions of figures occupying their
    canonical roles (Master Yoda at the Council, Anakin Skywalker
    commanding the 501st, etc.), never put in a player-reachable scene.
    Per ``test_q1_chains_and_traffic.py`` L72–84, the existing Q1 policy
    interpretation explicitly accepts this pattern: "Loyal to General
    Skywalker" is acceptable because "Skywalker is the off-screen
    commander; the trooper NPC is on-screen." Lore encyclopedia entries
    are the same pattern at the world-building tier — they describe the
    galaxy as it is, with canonical figures elsewhere by construction.
    The ``world_lore`` table feeds NPC dialogue prompts and Director
    narration, not on-screen scenes. If a future drop changes how
    ``world_lore`` surfaces (e.g., directly rendering entry content to
    a player via an ``info <topic>`` command), that drop must reassess
    the Q1 implications and write its own targeted tests; this drop
    does not pre-emptively address that hypothetical.
  * Does NOT touch the per-drop ``TestQ1CanonicalCharacterPolicy``
    classes in the chain-anchor / Mos Eisley / Coruscant / Nar Shaddaa
    drop tests. Those continue to own their per-drop content.

Test sections
=============

  1. ``TestOrganizationsYamlSithDescription`` — targeted guard on the
     Sith faction description fix (#1)
  2. ``TestOrganizationsYamlSeparatistCouncilDescription`` — targeted
     guard on the Separatist Council description fix (#2)
  3. ``TestChainAnchorsPoggleAbsenceFraming`` — targeted guard on the
     L615 Poggle/Sebulba per-line absence-framing fix (#3)
  4. ``TestGcwDirectorConfigHuttTakeoverHeadline`` — targeted guard on
     the ``hutt_takeover`` milestone headline replacement (#4)
  5. ``TestEngineQ1_2SurfaceClean`` — general-sweep tests across the
     v42 §1.5 Q1.2 Python surface (missions, encounters, combat_flavor,
     spacer_quest). These files were already clean at pre-flight; the
     tests lock them clean against future drift.
  6. ``TestDirectorConfigYamlsClean`` — general-sweep across both
     ``data/worlds/clone_wars/director_config.yaml`` and
     ``data/worlds/gcw/director_config.yaml``
  7. ``TestCrossCuttingCwContentYamlMeta`` — meta-sweep across all
     ``data/worlds/clone_wars/*.yaml`` for canonical-figure references
     in player-facing string-value fields that lack absence-framing.
     This is the backstop that catches future authorial slips in any
     new content YAML before they ship.
"""
from __future__ import annotations

import ast
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
# Shared canonical-figure list.
#
# This list mirrors the union of the per-drop test classes and the
# Q1.1 test classes. If you add canonical figures here, mirror the
# addition in ``test_q1_chains_and_traffic.py``,
# ``test_q1_scenes_and_planets.py``, and the per-drop test files. See
# the discussion in ``test_q1_chains_and_traffic.py`` §"Shared
# canonical-figure list" for why duplication is deliberate.
# ─────────────────────────────────────────────────────────────────────


CANONICAL_FORBIDDEN = {
    # CW-canonical Jedi
    "Anakin Skywalker", "Anakin", "Skywalker",
    "Obi-Wan Kenobi", "Obi-Wan", "Kenobi",
    "Yoda", "Mace Windu", "Master Windu", "Windu",
    "Plo Koon", "Ki-Adi-Mundi", "Kit Fisto", "Saesee Tiin",
    "Shaak Ti", "Jocasta Nu", "Aayla Secura",
    "Ahsoka Tano", "Ahsoka", "Luminara Unduli", "Barriss Offee",
    "Quinlan Vos", "Qui-Gon Jinn", "Qui-Gon",
    # CW-canonical Sith / CIS leadership
    "Dooku", "Count Dooku", "Darth Tyranus",
    "Sidious", "Darth Sidious",
    "Palpatine", "Chancellor Palpatine", "Sheev Palpatine",
    "Grievous", "General Grievous",
    "Ventress", "Asajj Ventress",
    "Maul", "Darth Maul", "Savage Opress",
    # CW-canonical Separatist Council figures
    "Nute Gunray", "Wat Tambor", "San Hill",
    "Poggle the Lesser", "Poggle", "Passel Argente",
    "Po Nudo", "Shu Mai",
    # CW-canonical Kaminoans
    "Lama Su", "Taun We", "Nala Se",
    # CW-canonical Senators
    "Padmé", "Padmé Amidala", "Padme", "Padme Amidala",
    "Bail Organa", "Mon Mothma", "Mina Bonteri",
    # CW-canonical clones
    "Captain Rex", "Commander Cody", "Commander Fox",
    "Commander Bly", "Commander Gree", "Commander Wolffe",
    # CW-canonical bounty hunters
    "Boba Fett", "Jango Fett", "Cad Bane", "The Mandalorian",
    "Aurra Sing", "Embo", "Bossk", "Sugi", "Dengar",
    "Hondo Ohnaka",
    # Tatooine canonical
    "Sebulba", "Watto",
    # Post-Order-66 / GCW leakage we still want to flag
    "Vader", "Darth Vader", "Tarkin",
    # Coruscant canonical fixtures
    "Dexter Jettster",
    # Mandalorian / Black Sun canonical
    "Satine Kryze", "Pre Vizsla", "Xizor", "Prince Xizor",
}


# Absence-framing markers. Mirrors the union of the equivalent lists in
# the existing Q1 test suite. A canonical reference in player-facing
# text is acceptable iff one of these markers appears in the same string
# (the "same-string scope" rule, intentionally stricter than the
# per-drop chain-anchor test's "same NPC blob" scope, because content
# YAML fields don't bundle related fields into one logical NPC blob).
ABSENCE_FRAMING_MARKERS = (
    "off-world", "off-screen", "off-stage", "off world", "off screen",
    "off stage", "off the planet", "off the safehouse",
    "absent", "not here", "not present", "not in attendance",
    "canonical-reference", "canonical reference",
    "currently", "elsewhere", "out today", "supply run",
    "killed by", "death of", "after his death", "after her death",
    "decades ago", "years ago", "a year ago", "three years ago",
    "during the", "remembered", "the late",
    "loyal to", "commands the", "serves under",
    "knew", "served under",
    "off-world at", "off-world on", "off-world in",
    "remains at", "stays at", "at his palace", "at her palace",
    "at the palace", "at the Dune Sea", "at the upper-hive",
    "does not visit", "does not come", "does not descend",
    "does not attend",
    "rather than", "by design", "remain off-screen", "remains off-screen",
    "next visit",
    "in a former life", "in the past",
    "historical", "historically",
    "rarely descends", "rarely seen",
    # Historical-template framing (mirrors test_q1_scenes_and_planets
    # test_jango_fett_reference_is_historical_only). A canonical name
    # used as a genetic/historical template marker — e.g. "the original
    # Jango Fett template" — is absence-framed by construction.
    "template", "genetic template", "donor", "source",
    "ten years", "modifications", "before the war",
    # LLM-prompt-directive framing. When a canonical name appears
    # inside a director_prompt_template's CONSTRAINTS section as part
    # of an instruction telling the LLM not to name canonical figures
    # ("No real galaxy figures named (no Palpatine, Vader, etc.)"),
    # the name is in an *instruction to the LLM*, not in player-
    # facing content. The instruction itself enforces Q1.
    "no real galaxy figures", "no canonical",
    "do not name", "avoid naming", "must not name",
    "no real galaxy", "no disney-canon",
)


def _has_word(text: str, word: str) -> bool:
    """Whole-word case-sensitive match. Mirrors the existing Q1 tests.

    Case sensitivity is intentional: "maul" the verb should not match
    "Maul" the canonical character. Word boundaries are intentional:
    "Anakin" should not match a partial of another word.
    """
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text))


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _engine_string_literals(path: Path) -> list[tuple[int, str]]:
    """Walk the AST of a python source file and collect every
    string-literal node's value EXCEPT docstrings on Module /
    FunctionDef / ClassDef.

    Same pattern as ``test_q1_scenes_and_planets.py``. The point is
    that docstrings are allowed to contain Q1 policy text explaining
    what was replaced, while user-facing string literals must be clean.
    Returns ``(lineno, value)`` tuples for diagnostic locality.
    """
    src = _read_text(path)
    tree = ast.parse(src, filename=str(path))
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                docstring_ids.add(id(node.body[0].value))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            out.append((node.lineno, node.value))
    return out


# ═════════════════════════════════════════════════════════════════════
# 1. Targeted guard — organizations.yaml::sith.properties.description
# ═════════════════════════════════════════════════════════════════════


CW_ORGS_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                / "organizations.yaml")


def _find_org(orgs_corpus, code: str):
    """Locate an organization entry by its ``code`` field. The CW
    organizations.yaml top-level shape is ``{factions: [...],
    guilds: [...]}``; we search both lists for the code."""
    if not orgs_corpus:
        return None
    for top_key in ("factions", "guilds", "organizations"):
        for entry in orgs_corpus.get(top_key, []) or []:
            if isinstance(entry, dict) and entry.get("code") == code:
                return entry
    return None


class TestOrganizationsYamlSithDescription(unittest.TestCase):
    """Q1.2 fix #1: the Sith faction description must not name Count
    Dooku, Darth Sidious, Darth Tyranus, or Palpatine in present tense.

    Pre-fix wording (~May 2026): "The Sith operate in secret. Count
    Dooku is publicly a Separatist leader; privately he is Darth
    Tyranus, Sith Lord. Darth Sidious controls the Republic from
    within." Three canonical figures named, each present-tense.

    The property is currently inert at the ``format_faction_list``
    render path, but the row is bootstrapped into the SQLite
    ``organizations`` table at boot. A future ``+faction info`` view
    would surface this string directly. Locking the fix now per the
    v42 §6.2 dual-source-drift discipline.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus = _read_yaml(CW_ORGS_YAML)
        cls.sith = _find_org(cls.corpus, "sith")

    def test_sith_entry_exists(self):
        self.assertIsNotNone(
            self.sith,
            "organizations.yaml is missing the 'sith' org entry. "
            "Without it, the Director can't track sith-axis influence."
        )

    def test_sith_description_present(self):
        desc = (self.sith.get("properties") or {}).get("description", "")
        self.assertTrue(
            desc.strip(),
            "organizations.yaml::sith.properties.description is empty. "
            "An empty description is a regression; the entry should "
            "still describe the institution without naming canonical "
            "figures."
        )

    def test_sith_description_no_named_canonical_figures(self):
        desc = (self.sith.get("properties") or {}).get("description", "")
        for forbidden in ("Count Dooku", "Dooku", "Darth Tyranus",
                          "Darth Sidious", "Sidious", "Palpatine",
                          "Sheev Palpatine"):
            self.assertFalse(
                _has_word(desc, forbidden),
                f"organizations.yaml::sith.properties.description "
                f"names canonical figure {forbidden!r}. Reverting to "
                f"the pre-fix wording would re-open the Q1 violation. "
                f"Description: {desc[:200]!r}"
            )

    def test_sith_description_retains_institutional_substance(self):
        """Sanity: the replacement description must still convey the
        Sith are secret, ancient, operating from off-stage, influencing
        the war from the shadows. If a future revision strips it down
        to "Sith." we want this test to catch the substance loss."""
        desc = (self.sith.get("properties") or {}).get("description", "")
        desc_low = desc.lower()
        # We assert presence of any of several institutional markers
        # rather than a single specific phrase, to allow future
        # rewording without breaking this test on cosmetic edits.
        markers = ("secret", "shadow", "thousand", "extinct",
                   "off-stage", "ancient", "hidden")
        self.assertTrue(
            any(m in desc_low for m in markers),
            f"organizations.yaml::sith.properties.description lacks "
            f"the institutional descriptors that establish Sith as a "
            f"covert/historical/off-stage force. Description: "
            f"{desc[:200]!r}"
        )


# ═════════════════════════════════════════════════════════════════════
# 2. Targeted guard — organizations.yaml::separatist_council.description
# ═════════════════════════════════════════════════════════════════════


class TestOrganizationsYamlSeparatistCouncilDescription(unittest.TestCase):
    """Q1.2 fix #2: the Separatist Council description must not list
    Nute Gunray, Wat Tambor, San Hill, Poggle the Lesser, or other
    canonical Council members by name.

    Pre-fix wording: "The corporate leaders of the CIS: Nute Gunray,
    Wat Tambor, San Hill, Poggle the Lesser. They funded the war for
    profit and are increasingly aware they are pawns."

    Same property-render status as the Sith description (currently
    inert in ``format_faction_list``, loaded into SQLite at boot,
    dual-source-drift risk). Locked alongside Q1.2 fix #1.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus = _read_yaml(CW_ORGS_YAML)
        cls.council = _find_org(cls.corpus, "separatist_council")

    def test_separatist_council_entry_exists(self):
        self.assertIsNotNone(
            self.council,
            "organizations.yaml is missing the 'separatist_council' "
            "org entry."
        )

    def test_separatist_council_description_present(self):
        desc = (self.council.get("properties") or {}).get(
            "description", "")
        self.assertTrue(
            desc.strip(),
            "organizations.yaml::separatist_council.properties."
            "description is empty."
        )

    def test_separatist_council_description_no_named_oligarchs(self):
        desc = (self.council.get("properties") or {}).get(
            "description", "")
        forbidden_names = (
            "Nute Gunray", "Wat Tambor", "San Hill",
            "Poggle the Lesser", "Poggle",
            "Passel Argente", "Po Nudo", "Shu Mai",
            "Count Dooku", "Dooku",
        )
        for forbidden in forbidden_names:
            self.assertFalse(
                _has_word(desc, forbidden),
                f"organizations.yaml::separatist_council.properties."
                f"description names canonical Council figure "
                f"{forbidden!r}. Reverting to the pre-fix wording "
                f"would re-open the Q1 violation. Description: "
                f"{desc[:200]!r}"
            )

    def test_separatist_council_description_names_institutions(self):
        """Sanity: the corporate-bloc institutions can still be named
        (they're trade-organization names, not individuals). The
        replacement description should name Trade Federation, Techno
        Union, etc. to retain its informational substance."""
        desc = (self.council.get("properties") or {}).get(
            "description", "")
        # At least three of these institution names must be present.
        institutions = ("Trade Federation", "Techno Union",
                        "Banking Clan", "Corporate Alliance",
                        "Commerce Guild")
        present = sum(1 for inst in institutions
                      if inst in desc)
        self.assertGreaterEqual(
            present, 3,
            f"organizations.yaml::separatist_council.properties."
            f"description should name the corporate-bloc institutions "
            f"to retain informational substance. Present: {present} of "
            f"5. Description: {desc[:300]!r}"
        )


# ═════════════════════════════════════════════════════════════════════
# 3. Targeted guard — chain-anchor L615 Poggle/Sebulba per-line absence
# ═════════════════════════════════════════════════════════════════════


CHAIN_ANCHORS_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                      / "npcs_drop_f8c2a_chain_anchors.yaml")


class TestChainAnchorsPoggleAbsenceFraming(unittest.TestCase):
    """Q1.2 fix #3: every NPC knowledge line that names Poggle the
    Lesser or Sebulba must carry per-line absence-framing.

    Pre-fix: the line at L615 read "Archduke Poggle the Lesser is the
    political senior on Geonosis; the cadre operates with his clearance
    but reports tactically through Sebulba (not the Boonta Eve racer;
    the CIS coordinator with the same hatched-out name) to the
    Confederate war council." The same-NPC L614 line correctly marked
    Dooku as "not present at this time"; L615 inherited that absence
    by sharing the knowledge blob, but read in isolation, L615 was
    present-tense without an absence marker. The existing chain-anchor
    Q1 test passes because of the blob-level scope; this targeted test
    asserts per-line absence-framing for Poggle/Sebulba specifically.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus = _read_yaml(CHAIN_ANCHORS_YAML)

    def _every_knowledge_line(self):
        """Yield (npc_name, line_idx, knowledge_line) for every knowledge
        entry across every NPC in the file."""
        for npc in (self.corpus.get("npcs") or []):
            ai = npc.get("ai_config") or {}
            for idx, line in enumerate(ai.get("knowledge") or []):
                if isinstance(line, str):
                    yield (npc.get("name", "<unknown>"), idx, line)

    def test_poggle_lines_carry_per_line_absence_marker(self):
        """Every knowledge line that names Poggle must include an
        absence-framing marker in that same line."""
        violations = []
        for (npc_name, idx, line) in self._every_knowledge_line():
            if not (_has_word(line, "Poggle the Lesser")
                    or _has_word(line, "Poggle")):
                continue
            line_low = line.lower()
            if not any(m in line_low for m in ABSENCE_FRAMING_MARKERS):
                violations.append(
                    {"npc": npc_name, "idx": idx, "line": line[:200]})
        self.assertEqual(
            violations, [],
            f"Knowledge lines naming Poggle/Poggle the Lesser without "
            f"per-line absence-framing: {violations}. Reverting to "
            f"the pre-fix wording would re-open this soft Q1 hit."
        )

    def test_sebulba_lines_carry_per_line_absence_marker(self):
        """Every knowledge line that names Sebulba must carry per-line
        absence-framing. The CIS-coordinator-named-Sebulba parenthetical
        does the disambiguation, but the line still needs to mark the
        coordinator as off-screen so the canonical podracer reference
        can't be construed as on-stage either."""
        violations = []
        for (npc_name, idx, line) in self._every_knowledge_line():
            if not _has_word(line, "Sebulba"):
                continue
            line_low = line.lower()
            if not any(m in line_low for m in ABSENCE_FRAMING_MARKERS):
                violations.append(
                    {"npc": npc_name, "idx": idx, "line": line[:200]})
        self.assertEqual(
            violations, [],
            f"Knowledge lines naming Sebulba without per-line "
            f"absence-framing: {violations}."
        )

    def test_existing_dooku_jabba_lines_unchanged(self):
        """Sanity: the well-formed L408 / L614 / L1200 / L1215 lines
        that established the absence-framing pattern remain in the
        file. If a refactor accidentally strips them, the surrounding
        knowledge will lose its blob-level cover and the broader
        chain-anchor Q1 test (test_drop_f8c2a_chain_anchors.py) might
        regress."""
        text = _read_text(CHAIN_ANCHORS_YAML)
        # Each of these is a substring lifted from a known
        # absence-framed knowledge line; the assertion is stable
        # against minor word-order edits because each substring is
        # unique enough that a substantive edit would break it
        # deliberately.
        anchors = (
            "Dooku himself is off-world",
            "is not present at this time",
            "remains at his palace at the Dune Sea",
            "Jabba is at his palace",
        )
        for anchor in anchors:
            self.assertIn(
                anchor, text,
                f"Expected absence-framing anchor {anchor!r} no longer "
                f"present in chain_anchors yaml. The absence-framing "
                f"pattern this file established must remain intact."
            )


# ═════════════════════════════════════════════════════════════════════
# 5. General-sweep — engine/missions.py + encounter_*.py +
#    combat_flavor.py + spacer_quest.py
# ═════════════════════════════════════════════════════════════════════
#
# Per v42 §1.5, these are the Python surfaces under the Q1.2 scope.
# Pre-flight audit confirmed they are already clean at the AST-string-
# literal level. This test class locks them clean against future
# drift — a future contributor adding "Mace Windu lectures here" to
# a mission description will fail this test on the next pytest run.


class TestEngineQ1_2SurfaceClean(unittest.TestCase):
    """All Q1.2 Python surfaces must be free of canonical-figure
    references in their user-facing string literals.

    Docstrings are excluded (they're allowed to document Q1 policy
    using canonical figure names as examples). Module/function/class
    docstrings only — inline docstring-style comments inside function
    bodies are still walked, but Python parser doesn't recognize those
    as docstrings so they appear as regular string literals which is
    correct (those WOULD be player-facing if a function returned them).
    """

    ENGINE_FILES = [
        PROJECT_ROOT / "engine" / "missions.py",
        PROJECT_ROOT / "engine" / "encounter_anomaly.py",
        PROJECT_ROOT / "engine" / "encounter_boarding.py",
        PROJECT_ROOT / "engine" / "encounter_hunter.py",
        PROJECT_ROOT / "engine" / "encounter_patrol.py",
        PROJECT_ROOT / "engine" / "encounter_pirate.py",
        PROJECT_ROOT / "engine" / "encounter_texture.py",
        PROJECT_ROOT / "engine" / "combat_flavor.py",
        PROJECT_ROOT / "engine" / "spacer_quest.py",
    ]

    def test_engine_files_exist(self):
        for path in self.ENGINE_FILES:
            self.assertTrue(
                path.exists(),
                f"Expected Q1.2 Python surface file missing: {path}. "
                f"If the file was deliberately renamed or removed, "
                f"update the ENGINE_FILES list in this test."
            )

    def test_no_canonical_names_in_string_literals(self):
        """Walk each file's AST. For every string literal that isn't
        a module/func/class docstring, check it against the canonical-
        forbidden set, allowing references only when an absence-framing
        marker is present in the same string."""
        violations = []
        for path in self.ENGINE_FILES:
            for (lineno, lit) in _engine_string_literals(path):
                for forbidden in CANONICAL_FORBIDDEN:
                    if not _has_word(lit, forbidden):
                        continue
                    if any(m in lit.lower()
                           for m in ABSENCE_FRAMING_MARKERS):
                        continue
                    violations.append(
                        {"file": path.name, "lineno": lineno,
                         "name": forbidden,
                         "snippet": lit[:160]})
                    break
        self.assertEqual(
            violations, [],
            f"Q1.2 Python surfaces contain canonical-figure references "
            f"without absence framing in user-facing string literals: "
            f"{violations}"
        )


# ═════════════════════════════════════════════════════════════════════
# 6. General-sweep — director_config.yaml (both CW and GCW eras)
# ═════════════════════════════════════════════════════════════════════


CW_DIRECTOR_YAML = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                    / "director_config.yaml")


def _yaml_string_values(node, path_prefix: str = ""):
    """Recursively yield (yaml_path, string_value) tuples for every
    string-valued leaf in a parsed YAML structure. Used by the meta-
    sweep tests to walk player-facing fields without enumerating each
    schema shape."""
    if isinstance(node, str):
        yield (path_prefix or "<root>", node)
    elif isinstance(node, dict):
        for k, v in node.items():
            kp = f"{path_prefix}.{k}" if path_prefix else str(k)
            yield from _yaml_string_values(v, kp)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            kp = f"{path_prefix}[{i}]"
            yield from _yaml_string_values(v, kp)


# Field-name keys whose values are NOT player-facing (color codes,
# enum slugs, IDs, internal references). Skipped by the meta-sweep so
# we don't false-positive on faction codes like "dooku_axis" or zone
# slugs that incorporate canonical references purely as namespace.
NON_PLAYER_FACING_KEYS = {
    "color", "axis", "id", "code", "icon", "css",
    "rrule", "calendar_id", "event_id", "kind",
}


def _is_player_facing_path(yaml_path: str) -> bool:
    """Heuristic: a yaml path is non-player-facing iff its last
    component is one of the metadata keys above, OR the path contains
    a non-player-facing key segment anywhere."""
    parts = re.split(r"\.|\[\d+\]", yaml_path)
    for part in parts:
        if part in NON_PLAYER_FACING_KEYS:
            return False
    return True


class TestDirectorConfigYamlsClean(unittest.TestCase):
    """Both era director_config.yaml files must be clean of canonical-
    figure references in player-facing string values. Headlines,
    narrative event prompts, and any other string that surfaces to a
    player or to the Director's LLM prompt counts as player-facing."""

    YAMLS = [
        ("clone_wars", CW_DIRECTOR_YAML),
    ]

    def test_each_director_config_clean(self):
        violations = []
        for (era, path) in self.YAMLS:
            corpus = _read_yaml(path)
            for (yp, val) in _yaml_string_values(corpus):
                if not _is_player_facing_path(yp):
                    continue
                for forbidden in CANONICAL_FORBIDDEN:
                    if not _has_word(val, forbidden):
                        continue
                    if any(m in val.lower()
                           for m in ABSENCE_FRAMING_MARKERS):
                        continue
                    violations.append({
                        "era": era,
                        "yaml_path": yp,
                        "name": forbidden,
                        "value": val[:200],
                    })
                    break
        self.assertEqual(
            violations, [],
            f"director_config.yaml files contain canonical-figure "
            f"references without absence framing: {violations}"
        )


# ═════════════════════════════════════════════════════════════════════
# 7. Cross-cutting meta-sweep — all data/worlds/<era>/*.yaml
# ═════════════════════════════════════════════════════════════════════
#
# This is the backstop. Per the v42 §6.2 dual-source-drift discipline,
# when a Q1 scrub ships, the matching test must also be broad enough to
# catch future authorial slips in unrelated files.
#
# We walk every YAML under data/worlds/clone_wars/ and data/worlds/gcw/.
# For each string-leaf, if it names a canonical figure and lacks an
# absence-framing marker in the same string, that's a violation.
#
# Two important scope exclusions:
#
#   (a) Files already locked by their own per-drop Q1 test classes.
#       These tests use the more permissive "same-NPC-blob" scope (the
#       chain-anchor Q1 test aggregates description + personality +
#       knowledge into one text blob before checking absence-framing).
#       The meta-sweep here uses the stricter "same-string" scope,
#       which would false-positive on NPC knowledge lines that are
#       individually compliant under the per-drop tests' scope. We
#       skip these files to avoid the cross-test contradiction.
#
#   (b) lore.yaml. The pre-flight audit determined lore.yaml is the
#       world-encyclopedia tier — third-person factual descriptions of
#       canonical figures occupying canonical roles, never put in
#       player-reachable scenes. Per the existing test_q1_chains_and_
#       traffic.py §"Borderline-but-acceptable references" commentary,
#       this pattern is accepted by the Q1 policy as currently
#       interpreted. If a future drop changes how world_lore surfaces,
#       that drop should reassess and add its own targeted tests.


META_SWEEP_EXCLUSIONS = {
    # Per-drop NPC YAMLs — owned by per-drop test_drop_*.py classes.
    "npcs_drop_f8c2a_chain_anchors.yaml",
    "npcs_drop_b_mos_eisley.yaml",
    "npcs_drop_c1_coruscant.yaml",
    "npcs_drop_c2_coruscant.yaml",
    "npcs_drop_g1_nar_shaddaa.yaml",
    "npcs_drop_g2_nar_shaddaa.yaml",
    "npcs_drop_def_civilians.yaml",
    "npcs_drop_h_combat.yaml",
    "npcs_drop_f8c2b2_combat_templates.yaml",
    "npcs_gg7.yaml",
    # World-encyclopedia tier — per-class Q1 interpretation accepted.
    "lore.yaml",
}


# Per-path deferred-by-design exclusions. Each entry is a
# (filename, yaml_path_substring) pair. The meta-sweep skips any
# string-leaf whose yaml_path *contains* the substring. Used when a
# specific room / entry / object has a known Q1 issue awaiting a
# design call but the file as a whole should still be swept for new
# violations.
#
# Removing an entry from this set should be paired with the
# corresponding content fix in the same drop — otherwise the
# meta_sweep will fail loudly. See TestKnownDeferredCanonicalSurfaces
# below for the locked-in xfail surface that mirrors this set.
#
# Q1.3 (May 18 2026): the legacy Xizor's Castle District entry was
# removed from this set when room 230 was rewritten as the Falleen
# Syndicate Tower (Vigo Sethel Vask, original character). The
# accompanying xfail test below is also promoted to positive
# regression-guard. This set is now empty by design — every prior
# deferred-by-design canonical surface has been scrubbed.
META_SWEEP_KNOWN_DEFERRED: set[tuple[str, str]] = set()


class TestCrossCuttingCwContentYamlMeta(unittest.TestCase):
    """Meta-sweep across data/worlds/<era>/*.yaml for canonical-figure
    references without absence framing in player-facing string values.

    Files already locked by per-drop Q1 tests are excluded (see
    META_SWEEP_EXCLUSIONS). The point is to catch any NEW content YAML
    that ships without per-drop test coverage and contains an
    unframed canonical reference.
    """

    ERAS = ("clone_wars",)

    def _yaml_files_in_era(self, era: str):
        era_root = PROJECT_ROOT / "data" / "worlds" / era
        for root, _dirs, files in os.walk(era_root):
            for fname in files:
                if not fname.endswith((".yaml", ".yml")):
                    continue
                if fname in META_SWEEP_EXCLUSIONS:
                    continue
                yield Path(root) / fname

    def test_meta_sweep_clean(self):
        violations = []
        for era in self.ERAS:
            for path in self._yaml_files_in_era(era):
                try:
                    corpus = _read_yaml(path)
                except yaml.YAMLError as e:
                    self.fail(
                        f"Failed to parse {path}: {e}. The meta-sweep "
                        f"requires every content YAML to parse "
                        f"cleanly."
                    )
                if corpus is None:
                    continue
                for (yp, val) in _yaml_string_values(corpus):
                    if not _is_player_facing_path(yp):
                        continue
                    # Skip known-deferred entries (see
                    # META_SWEEP_KNOWN_DEFERRED). These are tracked
                    # separately by TestKnownDeferredCanonicalSurfaces
                    # so removal of an entry triggers its content fix
                    # to ship in the same drop.
                    deferred_hit = False
                    for (def_file, def_pathsub) in (
                            META_SWEEP_KNOWN_DEFERRED):
                        if (path.name == def_file
                                and def_pathsub in yp):
                            deferred_hit = True
                            break
                    if deferred_hit:
                        continue
                    for forbidden in CANONICAL_FORBIDDEN:
                        if not _has_word(val, forbidden):
                            continue
                        if any(m in val.lower()
                               for m in ABSENCE_FRAMING_MARKERS):
                            continue
                        violations.append({
                            "era": era,
                            "file": path.name,
                            "yaml_path": yp,
                            "name": forbidden,
                            "value": val[:160],
                        })
                        break
        self.assertEqual(
            violations, [],
            f"Meta-sweep found canonical-figure references without "
            f"absence framing in content YAMLs outside per-drop test "
            f"coverage: {violations}. Fix each violation by adding an "
            f"absence-framing phrase to the same string (e.g., "
            f"'off-world', 'remains at', 'historical', 'not present "
            f"at this time') or by rewording to remove the canonical "
            f"name. If you believe a file should be excluded from "
            f"this sweep, add it to META_SWEEP_EXCLUSIONS with a "
            f"comment explaining why; if a specific path is deferred-"
            f"by-design pending a future drop, add it to "
            f"META_SWEEP_KNOWN_DEFERRED instead."
        )


# ═════════════════════════════════════════════════════════════════════
# 8. Deferred-by-design canonical surfaces — xfail registry
# ═════════════════════════════════════════════════════════════════════
#
# Each test here corresponds to an entry in META_SWEEP_KNOWN_DEFERRED.
# The tests are decorated @unittest.expectedFailure because the
# canonical-figure reference is still present in HEAD pending a
# design call. When the design call lands and the content is
# scrubbed:
#
#   1. Remove the entry from META_SWEEP_KNOWN_DEFERRED.
#   2. Remove the corresponding xfail decorator from the test here.
#   3. The test becomes a positive regression-guard locking the fix.
#
# This pattern (xfail → asserted-pass after fix) is the standard way
# this codebase encodes "known to be broken, design call pending"
# without letting the broader meta-sweep go red. The xfail status is
# visible in `pytest -v` output and is the audit trail for what's
# deferred.


class TestKnownDeferredCanonicalSurfaces(unittest.TestCase):
    """Locked-in xfail surface for deferred-by-design Q1 violations.
    Mirrors META_SWEEP_KNOWN_DEFERRED. Each test asserts the canonical
    reference is GONE; while it's still in HEAD the test xfails (the
    expected state pending design call).
    """

    def test_coruscant_xizor_district_scrubbed(self):
        """Coruscant ``rooms[30]`` was historically Xizor's Castle
        District (Prince Xizor, GCW Black Sun canonical figure).

        Q1.3 (May 18 2026) rewrote this room as the Falleen
        Syndicate Tower, occupied by an original character (Vigo
        Sethel Vask, backed in
        ``data/worlds/clone_wars/npcs_drop_i_falleen_syndicate.yaml``).
        Xizor is now only referenced off-stage in lore.yaml.

        This test pins the scrub: room 230 must not contain "Xizor"
        in any player-facing string. The xfail decorator was
        removed in the same drop that did the rewrite — if the
        canonical name comes back, this test goes red.
        """
        cor_yaml = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                    / "planets" / "coruscant.yaml")
        corpus = _read_yaml(cor_yaml)
        # Find the room by id=230 (the slot historically held by
        # Xizor's district). This used to be rooms[30] by index, but
        # Q1.3's rewrite preserved the integer id rather than the
        # list position; lookup by id is more durable across future
        # room-list insertions.
        rooms = corpus.get("rooms") or []
        room = None
        for r in rooms:
            if isinstance(r, dict) and r.get("id") == 230:
                room = r
                break
        self.assertIsNotNone(
            room,
            "coruscant.yaml has no room with id=230. Q1.3 preserved "
            "this id when rewriting the Xizor district as the "
            "Falleen Syndicate Tower; if the id was changed, this "
            "test needs to be updated."
        )
        combined_text = " ".join(filter(None, [
            room.get("name", ""),
            room.get("short_desc", ""),
            room.get("description", ""),
        ]))
        # The positive assertion: Xizor is absent.
        self.assertFalse(
            _has_word(combined_text, "Xizor"),
            f"coruscant.yaml id=230 still names Xizor. Q1.3 rewrote "
            f"this room as the Falleen Syndicate Tower; any "
            f"reintroduction of the canonical name is a Q1 "
            f"regression. Current room name: {room.get('name')!r}"
        )


if __name__ == "__main__":
    unittest.main()
