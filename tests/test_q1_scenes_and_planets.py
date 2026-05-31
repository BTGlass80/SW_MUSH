# -*- coding: utf-8 -*-
"""
tests/test_q1_scenes_and_planets.py — Q1 canonical-character policy
audit for live engine scenes and planet room descriptions.

Background
==========

The May 5 Q1-AUDIT drop closed Q1 coverage on tutorial chain
narrative, traffic captain pools, the orphan traffic_archetypes
YAML, and housing-lot descriptions. Two more surfaces remained
unscrubbed at that time:

  1. **Live engine scenes** — Path A graduation narration in
     ``engine/village_choice.py`` and the lightsaber-forge scene in
     ``engine/lightsaber_construction.py`` named "Master Mace Windu"
     as an interactive on-screen character. Every Force-sensitive
     Village quest graduate hit this. Also surfaced in the
     ``path`` command help text in
     ``parser/village_trial_commands.py``, and in the NPC
     authoring stub at
     ``data/worlds/clone_wars/quests/jedi_village.yaml::npcs``.

  2. **Planet room descriptions** — the Tipoca City administrative
     office description in
     ``data/worlds/clone_wars/planets/kamino.yaml`` named "Taun We"
     as the current senior administrator. Every player who entered
     the room saw this.

Both were HARD Q1 violations (canonical figures as on-screen,
present-tense, reachable characters — not absence-framed).

This file locks the fix with both a general sweep and targeted
regression-guards naming the specific cases that were broken
pre-fix. The targeted-guard pattern (per Q1-AUDIT drop test design
notes) survives a future author re-introducing a canonical name
"with absence framing elsewhere in the file" — the targeted check
asserts the specific scrub unconditionally.

The replacement NPC is Master Tova Resh (original, non-canonical
Iktotchi Master serving as the Order's intake-archives liaison).
A separate sanity test asserts she is referenced where the old
Mace Windu lines were so a future revert that silently strips the
narration without re-adding canonical names will still fail.

Test sections
=============

  1. TestEngineScenes_NoCanonicalNPCs
       - village_choice.py: no Mace Windu / Master Windu / standalone
         Windu in any string literal
       - lightsaber_construction.py: same
       - both files reference Master Tova Resh

  2. TestParserHelpText_NoCanonicalNPCs
       - village_trial_commands.py: ``path`` help text is clean

  3. TestJediVillageYaml_NoMaceWinduNpc
       - the npcs roster does not contain a master_mace_windu entry
         with display_name "Master Mace Windu"
       - the npcs roster contains a master_tova_resh entry

  4. TestKaminoYaml_NoTaunWeNamed
       - kamino.yaml administrative_office description does not name
         "Taun We" as current administrator
       - the general planet-yaml sweep finds no other canonical
         Kaminoans named in present tense
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


# ─────────────────────────────────────────────────────────────────────
# Shared canonical-figure list. Mirrors test_q1_chains_and_traffic.py
# (per audit policy — duplication is deliberate; each Q1 test class
# tunes its list to its scope). If you add canonical figures here,
# add them to test_q1_chains_and_traffic.py and the per-drop test
# classes too.
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
    # CW-canonical Kaminoans (relevant to kamino.yaml)
    "Lama Su", "Taun We", "Nala Se",
    # CW-canonical Senators
    "Padmé", "Padmé Amidala", "Bail Organa", "Mon Mothma",
    # CW-canonical clones
    "Captain Rex", "Commander Cody",
    # CW-canonical bounty hunters
    "Boba Fett", "Jango Fett", "Cad Bane", "The Mandalorian",
}


# Bare word checks for narrower variants we want to catch in scene
# text. (Mace Windu is the highest-value catch — the scene context
# is where the violation lived.)
WINDU_VARIANTS = ("Mace Windu", "Master Windu")


def _has_word(text: str, word: str) -> bool:
    """Whole-word case-sensitive search.

    Mirrors test_q1_chains_and_traffic.py's helper. Case sensitivity
    matters: "maul" (the verb) must not trip the "Maul" check; we
    use word boundaries so "Anakin" doesn't false-match a partial.
    """
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text))


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ═════════════════════════════════════════════════════════════════════
# 1. Live engine scenes — village_choice.py + lightsaber_construction.py
# ═════════════════════════════════════════════════════════════════════
#
# Approach: read the file as text, strip docstrings and comments
# heuristically (we want to test string-literal CONTENT but allow
# explanatory comments to reference canonical names — e.g. the
# "previously Mace Windu" Q1 policy comment is acceptable). The
# heuristic is "test code outside of triple-quote and # blocks."
#
# For the targeted-guard pattern we don't need the heuristic — we
# just assert the live scene strings are clean by walking each
# string literal via the ``ast`` module.


import ast


def _engine_string_literals(path: Path) -> list[str]:
    """Walk the AST of a python source file and collect every
    string-literal node's value EXCEPT docstrings on Module /
    FunctionDef / ClassDef.

    This isolates strings that are user-facing scene narration
    from docstrings (which are allowed to contain Q1 policy text
    explaining what canonical name was replaced).
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=str(path))

    # Identify docstring nodes to skip.
    docstring_node_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                docstring_node_ids.add(id(node.body[0].value))

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_node_ids:
                continue
            out.append(node.value)
    return out


class TestEngineScenes_NoCanonicalNPCs(unittest.TestCase):
    """Live engine scenes must not name canonical figures as on-
    screen, present-tense, interactive characters."""

    VILLAGE_CHOICE = PROJECT_ROOT / "engine" / "village_choice.py"
    LIGHTSABER_CONSTRUCTION = (
        PROJECT_ROOT / "engine" / "lightsaber_construction.py")

    def test_village_choice_string_literals_no_windu(self):
        """No string literal in village_choice.py mentions Mace
        Windu / Master Windu / standalone 'Windu'. Docstrings are
        skipped (they may explain the Q1 policy that replaced the
        canonical reference)."""
        for s in _engine_string_literals(self.VILLAGE_CHOICE):
            for variant in WINDU_VARIANTS:
                self.assertFalse(
                    _has_word(s, variant),
                    f"village_choice.py string literal contains "
                    f"forbidden canonical reference {variant!r}: "
                    f"{s[:200]!r}",
                )
            # Standalone Windu — catches "Windu nods" or "Tell Windu"
            # phrasings that drop the title/forename.
            self.assertFalse(
                _has_word(s, "Windu"),
                f"village_choice.py string literal contains "
                f"standalone 'Windu': {s[:200]!r}",
            )

    def test_lightsaber_construction_string_literals_no_windu(self):
        """No string literal in lightsaber_construction.py mentions
        Mace Windu / Master Windu / standalone 'Windu'."""
        for s in _engine_string_literals(self.LIGHTSABER_CONSTRUCTION):
            for variant in WINDU_VARIANTS:
                self.assertFalse(
                    _has_word(s, variant),
                    f"lightsaber_construction.py string literal "
                    f"contains forbidden canonical reference "
                    f"{variant!r}: {s[:200]!r}",
                )
            self.assertFalse(
                _has_word(s, "Windu"),
                f"lightsaber_construction.py string literal contains "
                f"standalone 'Windu': {s[:200]!r}",
            )

    def test_village_choice_references_replacement_master(self):
        """Sanity-guard: the Path A reception scene narration in
        village_choice.py must reference Master Tova Resh (or a
        future renamed equivalent). If a refactor strips the
        narration entirely without a Q1-compliant replacement,
        this test catches it.

        We accept either 'Tova Resh' or 'Master Tova' so the
        narration retains some named-NPC framing.
        """
        text = _read(self.VILLAGE_CHOICE)
        self.assertTrue(
            _has_word(text, "Tova Resh") or _has_word(text, "Master Tova"),
            "village_choice.py has lost its Path A reception NPC "
            "reference. Expected 'Tova Resh' or 'Master Tova' in "
            "the narration. If renaming, update this test.",
        )

    def test_lightsaber_construction_references_replacement_master(self):
        """Sanity-guard: forge scene must reference Master Tova
        (full name or short) so a silent strip is caught."""
        text = _read(self.LIGHTSABER_CONSTRUCTION)
        self.assertTrue(
            _has_word(text, "Tova Resh") or _has_word(text, "Master Tova"),
            "lightsaber_construction.py has lost its forge NPC "
            "reference. Expected 'Tova Resh' or 'Master Tova'. "
            "If renaming, update this test.",
        )


# ═════════════════════════════════════════════════════════════════════
# 2. Parser help text — village_trial_commands.py::PathCommand
# ═════════════════════════════════════════════════════════════════════


class TestParserHelpText_NoCanonicalNPCs(unittest.TestCase):
    """The ``path`` command help text is player-facing (every player
    who types ``help path``). It must not name canonical figures."""

    PATH = (PROJECT_ROOT / "parser" / "village_trial_commands.py")

    def test_path_command_help_text_no_windu(self):
        text = _read(self.PATH)

        # We could AST-walk but the help text is a single
        # well-formed string-literal block; a substring check on
        # the source is fine and survives reformatting.
        self.assertNotIn(
            "Mace Windu", text,
            "parser/village_trial_commands.py contains 'Mace Windu' "
            "— the path help text was a Q1 violation surface. "
            "Replace with non-canonical phrasing (e.g. 'the Order's "
            "intake liaison').",
        )
        self.assertNotIn(
            "Master Windu", text,
            "parser/village_trial_commands.py contains 'Master "
            "Windu' — see test above.",
        )


# ═════════════════════════════════════════════════════════════════════
# 3. jedi_village.yaml — NPC roster authoring spec
# ═════════════════════════════════════════════════════════════════════


class TestJediVillageYaml_NoMaceWinduNpc(unittest.TestCase):
    """The jedi_village.yaml design spec must not declare a
    master_mace_windu NPC stub. The replacement is master_tova_resh.

    This file is documentation/design-spec, not directly engine-
    consumed, but it is the single source of truth for what NPCs
    the Village quest builds — a future engine pass that auto-
    builds NPCs from this roster MUST NOT spawn Mace Windu.
    """

    YAML_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                 / "quests" / "jedi_village.yaml")

    @classmethod
    def setUpClass(cls):
        with open(cls.YAML_PATH, encoding="utf-8") as fh:
            cls.spec = yaml.safe_load(fh)

    def _npcs(self) -> list[dict]:
        """The npcs list lives under the top-level quest entry. The
        file is a single-quest YAML so we grab the npcs key from
        wherever it appears (preserves robustness against schema
        edits)."""
        # The spec is a dict with the quest content at top level;
        # walk it depth-1 to find an 'npcs' list.
        if isinstance(self.spec, dict):
            for v in self.spec.values():
                if isinstance(v, dict) and isinstance(v.get("npcs"), list):
                    return v["npcs"]
            if isinstance(self.spec.get("npcs"), list):
                return self.spec["npcs"]
        return []

    def test_no_master_mace_windu_id_in_npcs(self):
        npcs = self._npcs()
        ids = {n.get("id") for n in npcs if isinstance(n, dict)}
        self.assertNotIn(
            "master_mace_windu", ids,
            "jedi_village.yaml::npcs still has a 'master_mace_windu' "
            "entry. The Path A reception NPC must not be a canonical "
            "figure.",
        )

    def test_no_master_mace_windu_display_name(self):
        npcs = self._npcs()
        display_names = {n.get("display_name") for n in npcs
                         if isinstance(n, dict)}
        for name in ("Master Mace Windu", "Mace Windu"):
            self.assertNotIn(
                name, display_names,
                f"jedi_village.yaml::npcs contains an NPC with "
                f"display_name {name!r}.",
            )

    def test_master_tova_resh_present(self):
        """Replacement NPC must be present in the roster."""
        npcs = self._npcs()
        ids = {n.get("id") for n in npcs if isinstance(n, dict)}
        self.assertIn(
            "master_tova_resh", ids,
            "jedi_village.yaml::npcs is missing the 'master_tova_resh' "
            "replacement entry. The Path A reception NPC must be "
            "declared in the design spec.",
        )


# ═════════════════════════════════════════════════════════════════════
# 4. kamino.yaml — Tipoca administrative office
# ═════════════════════════════════════════════════════════════════════


class TestKaminoYaml_NoTaunWeNamed(unittest.TestCase):
    """The kamino.yaml room descriptions are player-facing (every
    player who walks into the room reads the description). Canonical
    Kaminoans (Taun We, Lama Su, Nala Se) must not appear as named
    present-tense administrators.

    Absence framing (e.g. "the Kaminoans who greeted Republic
    representatives a decade ago") would be acceptable per Q1 — but
    the original violation was present-tense ("the current senior
    administrator is Taun We") which is exactly the on-screen-as-
    named-NPC pattern Q1 forbids.
    """

    YAML_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                 / "planets" / "kamino.yaml")

    @classmethod
    def setUpClass(cls):
        with open(cls.YAML_PATH, encoding="utf-8") as fh:
            cls.text = fh.read()
        with open(cls.YAML_PATH, encoding="utf-8") as fh:
            cls.data = yaml.safe_load(fh)

    def test_admin_office_description_does_not_name_taun_we(self):
        """Targeted regression-guard: the administrative_office
        description was the specific HARD violation in HEAD prior to
        the fix. Even if a future author adds 'a decade ago' or
        'historically' elsewhere in the description, the name
        'Taun We' should not appear as the current administrator.

        This test asserts 'Taun We' absent from the entire
        kamino.yaml file. If a future drop adds a Taun We reference
        WITH proper absence framing (e.g. an NPC's knowledge text
        mentioning her as a historical figure), this test will need
        to be loosened. The point of the targeted guard is to make
        that loosening a deliberate code change, not an accident.
        """
        self.assertFalse(
            _has_word(self.text, "Taun We"),
            "kamino.yaml contains 'Taun We'. This was a HARD Q1 "
            "violation in the Tipoca admin-office description. If "
            "a future drop adds Taun We with absence framing, this "
            "targeted guard must be loosened deliberately.",
        )

    def test_no_canonical_kaminoans_in_present_tense_admin_role(self):
        """General sweep: no canonical Kaminoan name appears as a
        room-description named administrator.

        Jango Fett is intentionally excluded from this check — he
        is dead in-era (Geonosis, ~22 BBY) and references to him as
        the genetic-source for the clone template are unambiguously
        historical/forensic (the "original Jango Fett template" with
        "thousands of modifications over ten years" pattern is
        absence-framed by construction). If a future drop introduces
        a present-tense Jango reference (e.g. as a live NPC), that
        belongs to its own per-drop Q1 test, not this general sweep.
        """
        for name in ("Lama Su", "Taun We", "Nala Se"):
            self.assertFalse(
                _has_word(self.text, name),
                f"kamino.yaml contains canonical-figure name "
                f"{name!r}. Even off-screen references need explicit "
                f"absence framing — and the cleaner path is to omit "
                f"the name entirely. If you need a historical "
                f"reference, loosen this test deliberately.",
            )

    def test_jango_fett_reference_is_historical_only(self):
        """Jango Fett is dead in-era. The kamino.yaml reference is
        the genetic-source template, not a live NPC. Verify the
        reference appears only with absence-framing markers (the
        word 'original', 'template', or 'modifications since' near
        the name).

        If a future drop introduces a present-tense Jango reference
        (live NPC, dialogue, etc.), this test fails and forces a
        deliberate review.
        """
        # Locate every "Jango Fett" occurrence; for each, check a
        # ±100-char window for absence-framing markers.
        ABSENCE_MARKERS = (
            "original", "template", "donor", "source",
            "ten years", "modifications", "before the war",
        )
        for match in re.finditer(r"\bJango Fett\b", self.text):
            start = max(0, match.start() - 100)
            end = min(len(self.text), match.end() + 100)
            window = self.text[start:end].lower()
            self.assertTrue(
                any(marker in window for marker in ABSENCE_MARKERS),
                f"Jango Fett reference at offset {match.start()} "
                f"lacks absence-framing marker. Window: "
                f"{self.text[start:end]!r}",
            )


# ═════════════════════════════════════════════════════════════════════
# 5. Cross-cutting general sweep — engine + parser scene files
# ═════════════════════════════════════════════════════════════════════
#
# This is a backstop. If any of the per-surface tests above gets
# accidentally weakened, this will still catch any of the Mace-Windu
# variants in any of the three files at once.


class TestCanonicalCharacterPolicy_AllSceneFiles(unittest.TestCase):
    """Cross-cutting backstop — every scene-bearing file at once."""

    SCENE_FILES = [
        PROJECT_ROOT / "engine" / "village_choice.py",
        PROJECT_ROOT / "engine" / "lightsaber_construction.py",
        PROJECT_ROOT / "parser" / "village_trial_commands.py",
    ]

    def test_no_mace_windu_in_scene_file_string_literals(self):
        for path in self.SCENE_FILES:
            for s in _engine_string_literals(path):
                self.assertFalse(
                    _has_word(s, "Mace Windu"),
                    f"{path.name} string literal: {s[:200]!r}",
                )
                self.assertFalse(
                    _has_word(s, "Master Windu"),
                    f"{path.name} string literal: {s[:200]!r}",
                )


if __name__ == "__main__":
    unittest.main()
