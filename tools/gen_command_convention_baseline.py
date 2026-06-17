"""
Regenerate tests/data/command_convention_baseline.json from the live command
registry.

This is the ratchet baseline for the command-syntax rework (Drop 0; see
docs/design/command_syntax_rework_design_v2.md). It records the key/alias
collisions and run-on smash commands present at HEAD. The convention-invariant
test (tests/test_command_convention_invariant.py) asserts the live registry
introduces NOTHING beyond this baseline.

The baseline ONLY SHRINKS: run this after a canonicalization drop deletes
redundant forms / resolves collisions, review the (smaller) diff, and commit
it together with the canonicalization change. Do NOT regenerate to silence a
NEW collision introduced by a fresh command — fix the command instead.

Run:  python tools/gen_command_convention_baseline.py
"""
from __future__ import annotations

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# The run-on "smash" stems the rework deletes in favour of verb/switch forms
# (command_syntax_rework_design_v2.md §"Enforcement guard" #3). The baseline
# records which are CURRENTLY present; the invariant fails if a new one (or a
# reintroduced one, after a drop removes it from the baseline) appears.
RUN_ON_BLOCKLIST = [
    "bountyclaim", "questaccept", "smugdeliver", "buyresources",
    "questabandon", "questcomplete", "bountycollect", "bountytrack",
    "spacerquest",
]

BASELINE_PATH = os.path.join(ROOT, "tests", "data",
                             "command_convention_baseline.json")

_COMMENT = (
    "Command-syntax rework Drop 0 convention ratchet "
    "(command_syntax_rework_design_v2.md). These are the command-convention "
    "violations present at HEAD that canonicalization Drops 1-5 will remove. "
    "tests/test_command_convention_invariant.py asserts the LIVE registry "
    "introduces NOTHING beyond this set. This baseline ONLY SHRINKS: "
    "regenerate it with tools/gen_command_convention_baseline.py after a "
    "canonicalization drop removes violations. Do NOT add entries to silence "
    "a failing test -- fix the command instead."
)


def build() -> dict:
    # Reuse the single authoritative full-registry builder so this never
    # drifts from the audited command set.
    from tests.test_t321_admin_command_access_invariant import (
        _build_full_registry,
    )

    reg = _build_full_registry()
    collisions = reg.collision_signatures
    run_ons = sorted(n for n in RUN_ON_BLOCKLIST if reg.has_exact(n))
    return {
        "_comment": _COMMENT,
        "schema_version": 1,
        "collisions": collisions,
        "run_on_keys": run_ons,
    }


def main() -> None:
    doc = build()
    with io.open(BASELINE_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(
        f"Wrote {BASELINE_PATH}: "
        f"{len(doc['collisions'])} collisions, "
        f"{len(doc['run_on_keys'])} run-on key(s)."
    )


if __name__ == "__main__":
    main()
