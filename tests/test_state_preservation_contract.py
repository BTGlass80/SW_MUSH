# -*- coding: utf-8 -*-
"""tests/test_state_preservation_contract.py — T3.20 state-preservation (scope_notes f).

Makes the written state-preservation contract
(docs/design/state_preservation_contract_v1.md) SELF-ENFORCING. It fails the build
when the code drifts from invariant I1 ("every persisted entity round-trips"):

  * a NEW deserializer (from_dict / from_db_dict / from_json) shipped without a
    registered reload-round-trip test;
  * a serializer pair that became asymmetric (a from_* with no matching to_*);
  * a registered round-trip test file that was deleted;
  * the contract doc gone, or referencing an artifact that does not exist.

Discovery is a static AST scan of engine/ai/db/server/parser (no imports, no
execution), so it is robust and side-effect-free.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_SCAN_ROOTS = ("engine", "ai", "db", "server", "parser")
_DESER_METHODS = {"from_dict", "from_db_dict", "from_json"}

# Every persisted-entity deserializer in the tree -> the test that proves its
# reload round-trip. Adding a deserializer REQUIRES adding a round-trip test and
# an entry here (that is the contract — see the contract doc, invariant I1).
_DESERIALIZER_REGISTRY = {
    "Character.from_db_dict":   "test_character_reload_roundtrip.py",
    "ItemInstance.from_dict":   "test_persisted_entity_roundtrip.py",
    "Mission.from_dict":        "test_persisted_entity_roundtrip.py",
    "BountyContract.from_dict": "test_persisted_entity_roundtrip.py",
    "SmugglingJob.from_dict":   "test_persisted_entity_roundtrip.py",
    "Buff.from_dict":           "test_persisted_entity_roundtrip.py",
    "TrafficShip.from_json":    "test_serializer_roundtrip_extra.py",
    "NPCConfig.from_dict":      "test_serializer_roundtrip_extra.py",
}

_CONTRACT_DOC = "docs/design/state_preservation_contract_v1.md"


def _scan_serializers():
    """Static AST scan. Returns (deserializers, class_methods):
      deserializers: {"Class.method": "repo/rel/path.py"} for every from_* method.
      class_methods: {class_name: set(all method names)} (for symmetry checks).
    """
    deserializers: dict[str, str] = {}
    class_methods: dict[str, set] = {}
    for root in _SCAN_ROOTS:
        rootp = PROJECT_ROOT / root
        if not rootp.is_dir():
            continue
        for p in rootp.rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = {
                        it.name for it in node.body
                        if isinstance(it, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
                    class_methods.setdefault(node.name, set()).update(methods)
                    for m in methods & _DESER_METHODS:
                        deserializers[f"{node.name}.{m}"] = rel
    return deserializers, class_methods


class TestStatePreservationContract(unittest.TestCase):
    def test_no_unregistered_deserializer(self):
        deser, _ = _scan_serializers()
        discovered = set(deser)
        registered = set(_DESERIALIZER_REGISTRY)

        unregistered = discovered - registered
        self.assertEqual(
            unregistered, set(),
            "New persisted deserializer(s) shipped with no registered reload-round-"
            "trip test (contract I1). Add a round-trip test, then register it in "
            "_DESERIALIZER_REGISTRY. Offenders: "
            + ", ".join(f"{k} ({deser[k]})" for k in sorted(unregistered)))

        missing = registered - discovered
        self.assertEqual(
            missing, set(),
            "Registered deserializer(s) no longer found in the tree (renamed/"
            "removed?) — update the registry + the round-trip test: "
            + ", ".join(sorted(missing)))

    def test_serializer_pairs_are_symmetric(self):
        _, class_methods = _scan_serializers()
        for key in _DESERIALIZER_REGISTRY:
            cls, from_m = key.split(".")
            to_m = from_m.replace("from_", "to_", 1)
            self.assertIn(
                to_m, class_methods.get(cls, set()),
                f"{cls} has {from_m} but no matching {to_m} — an asymmetric "
                f"serializer pair cannot round-trip (contract I1).")

    def test_round_trip_test_files_exist(self):
        tests_dir = PROJECT_ROOT / "tests"
        for key, test_file in _DESERIALIZER_REGISTRY.items():
            self.assertTrue(
                (tests_dir / test_file).is_file(),
                f"round-trip test {test_file} for {key} is missing")

    def test_contract_doc_exists_and_references_real_artifacts(self):
        doc = PROJECT_ROOT / _CONTRACT_DOC
        self.assertTrue(doc.is_file(), f"{_CONTRACT_DOC} is missing")
        text = doc.read_text(encoding="utf-8")
        referenced = [
            "tests/test_character_reload_roundtrip.py",
            "tests/test_persisted_entity_roundtrip.py",
            "tests/test_serializer_roundtrip_extra.py",
            "tests/test_migration_framework_integrity.py",
            "db/integrity.py", "tools/check_db_integrity.py",
            "db/backup.py", "tools/backup_db.py",
            "docs/design/backup_restore_runbook_v1.md",
        ]
        for rel in referenced:
            self.assertIn(rel, text, f"contract doc should reference {rel}")
            self.assertTrue(
                (PROJECT_ROOT / rel).exists(),
                f"contract doc references {rel}, which does not exist (phantom pointer)")

    def test_referenced_tools_importable(self):
        from db.integrity import scan_integrity
        from db.backup import backup_database
        self.assertTrue(callable(scan_integrity))
        self.assertTrue(callable(backup_database))


if __name__ == "__main__":
    unittest.main()
