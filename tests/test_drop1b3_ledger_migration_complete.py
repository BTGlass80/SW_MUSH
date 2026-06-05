# -*- coding: utf-8 -*-
"""
tests/test_drop1b3_ledger_migration_complete.py -- Drop 1.b.3 (finish the migration)

Completes the bulk migration of every credit movement onto the
``Database.adjust_credits`` chokepoint (Drop 1.a). This drop converted the
remaining ~30 credit-write sites in one consolidated sweep across the
encounter, housing, space, smuggling, tutorial, anomaly, intel, chain,
sleeping, traffic, building, hazard, spacer-quest, p2p, bacta, bounty and
crafting paths — plus the ``mission_commands`` failed-check no-op tail — and
added a ``city_tax`` system sink so the city's slice is legible on the
``@economy`` dashboard.

The headline pin is **structural and tree-wide**: no ``save_character(... credits
...)`` call may exist anywhere under ``engine/`` or ``parser/`` (the lone
allowed matches are two rST docstring mentions in ``chain_rewards.py``). That
single invariant guards the *entire* migration (1.a + 1.b.1 + 1.b.2 + 1.b.3)
against regressions, not just this drop's files.

Behaviour is covered by the existing suites that exercise these paths; this
file is the structural-negative migration pin.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_CREDIT_SAVE_RE = re.compile(r"save_character\([^)]*credits")
_SCAN_DIRS = ["engine", "parser"]


def _iter_py(rel_dir):
    base = os.path.join(PROJECT_ROOT, rel_dir)
    for root, _dirs, files in os.walk(base):
        if "__pycache__" in root:
            continue
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def _is_doc_mention(line):
    """A match inside rST/markdown code-quotes (backticks) is a docstring
    mention, not a real call. Real calls look like `await x.save_character(...)`."""
    return "`" in line


class TestLedgerMigrationComplete(unittest.TestCase):
    def test_no_credit_writing_save_character_anywhere(self):
        """Tree-wide invariant: every credit movement goes through
        adjust_credits; no save_character(credits=...) bypass survives."""
        offenders = []
        for rel_dir in _SCAN_DIRS:
            for path in _iter_py(rel_dir):
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if _CREDIT_SAVE_RE.search(line) and not _is_doc_mention(line):
                            rel = os.path.relpath(path, PROJECT_ROOT)
                            offenders.append(f"{rel}:{i}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "Credit movements must route through Database.adjust_credits. "
            "Found save_character(credits=...) bypass(es):\n  "
            + "\n  ".join(offenders),
        )

    def test_no_manual_log_credit_in_engine_or_parser(self):
        """All credit logging now happens inside adjust_credits; no engine/parser
        call site should invoke log_credit directly anymore."""
        pat = re.compile(r"\.log_credit\(")
        offenders = []
        for rel_dir in _SCAN_DIRS:
            for path in _iter_py(rel_dir):
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if pat.search(line) and "`" not in line:
                            rel = os.path.relpath(path, PROJECT_ROOT)
                            offenders.append(f"{rel}:{i}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "log_credit should only be called from inside adjust_credits now. "
            "Stray call site(s):\n  " + "\n  ".join(offenders),
        )


class TestDrop1b3SourceTags(unittest.TestCase):
    """Spot-check that this drop's new source tags landed in their files."""
    _EXPECTED = {
        "engine/encounter_texture.py": "space_encounter_reward",
        "engine/encounter_patrol.py": "space_patrol_fine",
        "engine/encounter_pirate.py": "space_pirate_extortion",
        "engine/encounter_hunter.py": "space_hunter_settlement",
        "engine/housing.py": "housing_rent",
        "engine/buildings.py": "player_building_construct",
        "engine/hazards.py": "hazard_theft",
        "engine/sleeping.py": "theft_loss",
        "engine/chain_rewards.py": "chain_reward",
        "engine/intel_handlers.py": "intel_handover",
        "engine/npc_space_traffic.py": "npc_pirate_bounty",
        "engine/tutorial_v2.py": "tutorial_reward",
        "engine/wilderness_anomalies.py": "wilderness_anomaly_reward",
        "engine/spacer_quest.py": "spacer_quest",
        "engine/player_cities.py": "city_tax",
        "parser/space_commands.py": "ship_refuel",
        "parser/builtin_commands.py": "bacta_tank",
        "parser/smuggling_commands.py": "smuggling_fine",
        "parser/crafting_commands.py": "resource_vendor",
    }

    def test_expected_tags_present(self):
        for rel, tag in self._EXPECTED.items():
            with open(os.path.join(PROJECT_ROOT, rel), "r", encoding="utf-8") as f:
                src = f.read()
            self.assertIn(f'"{tag}"', src,
                          f"{rel} should carry the '{tag}' credit source tag")


class TestAdjustCreditsChokepointExists(unittest.TestCase):
    def test_adjust_credits_defined(self):
        with open(os.path.join(PROJECT_ROOT, "db/database.py"), "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("async def adjust_credits(", src,
                      "the adjust_credits chokepoint must exist in db/database.py")


if __name__ == "__main__":
    unittest.main()
