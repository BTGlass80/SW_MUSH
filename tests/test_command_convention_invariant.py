# -*- coding: utf-8 -*-
"""
tests/test_command_convention_invariant.py
Command-syntax rework — Drop 0 enforcement guard (the FOUNDATION drop).

Per docs/design/command_syntax_rework_design_v2.md §"Enforcement guard": a
standing CI invariant that builds the full live command registry and FAILS on
any NEW command-convention violation, so future commands can't silently drift
while Drops 1-5 canonicalize the surface.

What this guards (Drop 0 scope — NO command renames yet, pure safety net):

  1. **Registry collision ratchet.** CommandRegistry.register() now records
     every key/alias collision (a name already bound to a *different* command)
     in ``registry._collisions``. This test asserts the LIVE registry
     introduces NOTHING beyond the frozen baseline
     (tests/data/command_convention_baseline.json). The baseline ONLY shrinks
     — regenerate it with tools/gen_command_convention_baseline.py as the
     canonicalization drops delete redundant forms. A brand-new collision
     (e.g. a fresh command claiming a contested name) fails the gate.

  2. **Run-on regression ratchet.** The 9 run-on "smash" stems (bountyclaim,
     questaccept, …) that Drop 2 converts to verb/switch forms are tracked;
     once a drop deletes one (removing it from the baseline) it must not
     reappear, and no NEW smash may be introduced.

  3. **Collision-detection mechanism.** A synthetic unit check proves the
     instrumentation actually records collisions, so a future refactor can't
     silently make the ratchet vacuous (which matters once the live baseline
     reaches zero).

The prefix↔access half of the enforcement guard (every @-key is BUILDER+ save
the {@desc,@mail} allowlist) already ships as
tests/test_t321_admin_command_access_invariant.py — composed here, not
duplicated (a tripwire below guards against its deletion).
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.commands import BaseCommand, CommandRegistry  # noqa: E402
# Single authoritative full-registry builder (shared with the @-access guard
# and the baseline generator — never a third copy of the registration list).
from tests.test_t321_admin_command_access_invariant import (  # noqa: E402
    _build_full_registry,
)
from tools.gen_command_convention_baseline import (  # noqa: E402
    RUN_ON_BLOCKLIST,
)

BASELINE_PATH = os.path.join(PROJECT_ROOT, "tests", "data",
                             "command_convention_baseline.json")


def _load_baseline() -> dict:
    with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ══════════════════════════════════════════════════════════════════════════
# 1. The collision ratchet — no NEW key/alias collision beyond the baseline
# ══════════════════════════════════════════════════════════════════════════
class TestCollisionRatchet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = _build_full_registry()
        cls.baseline = _load_baseline()

    def test_registry_built_substantially(self):
        # A broken import would silently shrink the registry and hide
        # collisions, making the ratchet pass vacuously.
        self.assertGreaterEqual(len(self.reg.all_commands), 300)

    def test_baseline_is_wellformed(self):
        self.assertEqual(self.baseline.get("schema_version"), 1)
        self.assertIsInstance(self.baseline.get("collisions"), list)
        self.assertIsInstance(self.baseline.get("run_on_keys"), list)

    def test_no_new_key_or_alias_collisions(self):
        live = set(self.reg.collision_signatures)
        allowed = set(self.baseline["collisions"])
        introduced = sorted(live - allowed)
        self.assertEqual(
            introduced, [],
            "New command key/alias collision(s) not in the baseline. A command "
            "is silently clobbering another's key/alias. Fix the offending "
            "command (rename/scope its key or alias) — do NOT add these to "
            "tests/data/command_convention_baseline.json. New collisions:\n  "
            + "\n  ".join(introduced))

    def test_no_new_run_on_commands(self):
        live = {n for n in RUN_ON_BLOCKLIST if self.reg.has_exact(n)}
        allowed = set(self.baseline["run_on_keys"])
        introduced = sorted(live - allowed)
        self.assertEqual(
            introduced, [],
            "Run-on 'smash' command(s) reappeared or were newly introduced. "
            "New family verbs must use the verb/switch form (e.g. bounty/claim "
            "not bountyclaim). Offenders:\n  " + "\n  ".join(introduced))


# ══════════════════════════════════════════════════════════════════════════
# 2. The collision-detection MECHANISM (synthetic — independent of live count)
# ══════════════════════════════════════════════════════════════════════════
class _Fake(BaseCommand):
    """Minimal command with configurable key/aliases for mechanism tests."""
    def __init__(self, key, aliases=None):
        self.key = key
        self.aliases = aliases or []


class TestCollisionDetectionMechanism(unittest.TestCase):
    def test_duplicate_primary_key_recorded(self):
        reg = CommandRegistry()
        reg.register(_Fake("foo"))
        reg.register(_Fake("foo"))  # second hides the first
        self.assertIn("key:foo", reg.collision_signatures)

    def test_duplicate_alias_recorded(self):
        reg = CommandRegistry()
        reg.register(_Fake("alpha", ["x"]))
        reg.register(_Fake("beta", ["x"]))  # alias x re-claimed
        self.assertIn("alias:x", reg.collision_signatures)

    def test_alias_shadowed_by_primary_key_recorded(self):
        reg = CommandRegistry()
        reg.register(_Fake("board"))           # primary key 'board'
        reg.register(_Fake("ship", ["board"]))  # alias dead — primary wins
        self.assertIn("alias:board", reg.collision_signatures)

    def test_distinct_names_produce_no_collision(self):
        reg = CommandRegistry()
        reg.register(_Fake("one", ["a"]))
        reg.register(_Fake("two", ["b"]))
        self.assertEqual(reg.collision_signatures, [])

    def test_same_command_reregister_is_not_a_collision(self):
        # Re-registering the *same instance* (idempotent) must not flag.
        reg = CommandRegistry()
        cmd = _Fake("same", ["s"])
        reg.register(cmd)
        reg.register(cmd)
        self.assertEqual(reg.collision_signatures, [])

    def test_signatures_are_sorted_and_unique(self):
        reg = CommandRegistry()
        reg.register(_Fake("k"))
        reg.register(_Fake("k"))
        reg.register(_Fake("k"))  # two collisions on same name -> one signature
        sigs = reg.collision_signatures
        self.assertEqual(sigs, sorted(set(sigs)))
        self.assertEqual(sigs.count("key:k"), 1)

    def test_has_exact_no_prefix_matching(self):
        reg = CommandRegistry()
        reg.register(_Fake("bounty"))
        self.assertTrue(reg.has_exact("bounty"))
        self.assertTrue(reg.has_exact("BOUNTY"))    # case-insensitive
        self.assertFalse(reg.has_exact("boun"))     # not a prefix match


# ══════════════════════════════════════════════════════════════════════════
# 3. Compose (don't duplicate) the @-namespace access invariant
# ══════════════════════════════════════════════════════════════════════════
class TestAtAccessInvariantComposed(unittest.TestCase):
    def test_at_access_coverage_present(self):
        """Tripwire: the authoritative @-key↔access guard must still exist.

        The prefix↔access half of the convention is enforced by
        tests/test_t321_admin_command_access_invariant.py. We compose with it
        rather than re-implement; this asserts that coverage hasn't been
        deleted out from under the convention story.
        """
        import tests.test_t321_admin_command_access_invariant as m
        self.assertTrue(hasattr(m, "TestAtCommandPrivilegeInvariant"))
        self.assertEqual(m.PLAYER_AT_COMMAND_ALLOWLIST, {"@desc", "@mail"})


if __name__ == "__main__":
    unittest.main()
