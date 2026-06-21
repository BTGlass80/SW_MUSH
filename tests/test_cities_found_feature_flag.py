"""
tests/test_cities_found_feature_flag.py — cities.found_enabled tunable gate.

Brian decision #7 (2026-06-16): `+city found` is gated off at launch via
``get_tunable("cities.found_enabled", False)``.  Only the founding step is
blocked; all other +city subcommands remain operational.

Tests
=====
1. TestFoundDisabledByDefault  — bare get_tunable returns False (no YAML load)
2. TestFoundBlockedWhenFalse   — _handle_found returns "not available" message
3. TestFoundUnblockedWhenTrue  — _handle_found passes through (no block message)
4. TestOtherSubcmdsUnaffected  — +city info / +city list / bare +city unaffected
5. TestTunableInFile           — data/tunables.yaml contains cities.found_enabled: false
"""

import asyncio
import unittest
import engine.tunables as _tunables_mod
from engine.tunables import get_tunable, reset_tunables


# ── helpers ──────────────────────────────────────────────────────────────────

def _set_tunable(**kw):
    _tunables_mod._TUNABLES.update(kw)


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent: list[str] = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def find_by_character(self, char_id):
        return None


def _make_ctx(session, args: str):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=f"+city {args}".strip(),
        command="+city",
        args=args,
        args_list=args.split() if args else [],
        db=None,
        session_mgr=_FakeSessionManager(),
    )


def _run(coro):
    return asyncio.run(coro)


# ── 1. TestFoundDisabledByDefault ────────────────────────────────────────────

class TestFoundDisabledByDefault(unittest.TestCase):
    def setUp(self):
        reset_tunables()

    def tearDown(self):
        reset_tunables()

    def test_default_is_false(self):
        self.assertFalse(get_tunable("cities.found_enabled", False))

    def test_explicit_false(self):
        _set_tunable(**{"cities.found_enabled": False})
        self.assertFalse(get_tunable("cities.found_enabled", False))

    def test_explicit_true(self):
        _set_tunable(**{"cities.found_enabled": True})
        self.assertTrue(get_tunable("cities.found_enabled", False))


# ── 2. TestFoundBlockedWhenFalse ─────────────────────────────────────────────

class TestFoundBlockedWhenFalse(unittest.TestCase):
    def setUp(self):
        reset_tunables()
        # Default is False — no explicit set needed.

    def tearDown(self):
        reset_tunables()

    def test_found_blocked_shows_message(self):
        from parser.city_commands import CityCommand
        char = {"id": 1, "name": "TestChar"}
        session = _FakeSession(character=char)
        ctx = _make_ctx(session, "found TestCity")

        _run(CityCommand().execute(ctx))

        self.assertTrue(
            any("not available" in line for line in session.sent),
            f"Expected 'not available' in sent lines; got: {session.sent}",
        )

    def test_found_blocked_no_args_still_blocked(self):
        from parser.city_commands import CityCommand
        char = {"id": 1, "name": "TestChar"}
        session = _FakeSession(character=char)
        ctx = _make_ctx(session, "found")

        _run(CityCommand().execute(ctx))

        self.assertTrue(
            any("not available" in line for line in session.sent),
            f"Expected 'not available' in sent; got: {session.sent}",
        )


# ── 3. TestFoundUnblockedWhenTrue ────────────────────────────────────────────

class TestFoundUnblockedWhenTrue(unittest.TestCase):
    def setUp(self):
        reset_tunables()
        _set_tunable(**{"cities.found_enabled": True})

    def tearDown(self):
        reset_tunables()

    def test_found_passes_through_when_enabled(self):
        """When enabled, _handle_found must NOT show the launch-block message."""
        from parser.city_commands import CityCommand
        char = {"id": 1, "name": "TestChar", "faction_id": "republic"}
        session = _FakeSession(character=char)
        ctx = _make_ctx(session, "found TestCity")

        # db=None means this will hit an error in the engine, but the
        # important check is that the launch-gate message is absent.
        _run(CityCommand().execute(ctx))

        self.assertFalse(
            any("not available at launch" in line for line in session.sent),
            f"Launch-gate message appeared even when enabled: {session.sent}",
        )


# ── 4. TestOtherSubcmdsUnaffected ────────────────────────────────────────────

class TestOtherSubcmdsUnaffected(unittest.TestCase):
    def setUp(self):
        reset_tunables()
        # cities.found_enabled = False (default); other subcommands must still work.

    def tearDown(self):
        reset_tunables()

    def _check_subcommand_does_not_block(self, sub: str):
        from parser.city_commands import CityCommand
        char = {"id": 1, "name": "TestChar", "faction_id": "republic"}
        session = _FakeSession(character=char)
        ctx = _make_ctx(session, sub)
        try:
            _run(CityCommand().execute(ctx))
        except Exception:
            # Non-gate errors (db=None, etc.) are acceptable here;
            # we only care that the launch-gate message was NOT sent.
            pass
        self.assertFalse(
            any("not available at launch" in line for line in session.sent),
            f"+city {sub} showed the launch-gate message: {session.sent}",
        )

    def test_info_unaffected(self):
        self._check_subcommand_does_not_block("info")

    def test_list_unaffected(self):
        self._check_subcommand_does_not_block("list")

    def test_bare_city_help_unaffected(self):
        from parser.city_commands import CityCommand
        char = {"id": 1, "name": "TestChar"}
        session = _FakeSession(character=char)
        ctx = _make_ctx(session, "")
        _run(CityCommand().execute(ctx))
        self.assertFalse(
            any("not available at launch" in line for line in session.sent),
            f"Bare +city help showed launch-gate message: {session.sent}",
        )


# ── 5. TestTunableInFile ─────────────────────────────────────────────────────

class TestTunableInFile(unittest.TestCase):
    def test_tunables_yaml_contains_cities_found_enabled_false(self):
        with open("data/tunables.yaml", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("cities.found_enabled", content, "Key not in tunables.yaml")
        self.assertIn("cities.found_enabled: false", content,
                      "cities.found_enabled should be 'false' at launch")

    def test_load_tunables_sets_false(self):
        from engine.tunables import load_tunables
        reset_tunables()
        load_tunables("data/tunables.yaml")
        self.assertFalse(
            get_tunable("cities.found_enabled", False),
            "cities.found_enabled should be False after loading tunables.yaml",
        )
        reset_tunables()


if __name__ == "__main__":
    unittest.main()
