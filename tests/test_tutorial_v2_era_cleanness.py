# -*- coding: utf-8 -*-
"""
tests/test_tutorial_v2_era_cleanness.py — era-cleanness guard for the legacy
profession-chain system.

engine/tutorial_v2.py predates this deployment settling on the Clone Wars era.
Its REBEL_CELL + IMPERIAL_SERVICE profession chains were wholesale Galactic Civil
War content (Rebel Alliance recruitment / Imperial Service) and several other
chains carried scattered off-era flavor. The profession-chain dispatch
(check_profession_chains) is LIVE — wired into the mission/npc/smuggling/space
command paths — so this was a reachable B3 era-cleanness risk that the surgical
(file, string) era-cleanness test never scanned.

Resolution (Brian, 2026-06-14, BRIAN_ROADMAP_DECISIONS.2026-06-14 decision 1 =
OPTION A DELETE): the two off-era GCW arcs (REBEL_CELL + IMPERIAL_SERVICE) were
DELETED outright — definitions, dispatch, status rows, _can_start_* gates, and the
_GCW_PROFESSION_CHAINS_ENABLED dormancy flag. The rest of the profession-chain
system (Smuggler's Run, Hunter's Mark, Artisan's Forge, Underworld) STAYS.

These tests pin both halves: the GCW arcs are GONE (no module attrs, nothing in
the status display), and the LIVE chain data objects are scanned with a NO-allow-
list walk so any future off-era addition to a reachable chain fails.
"""
import unittest

import engine.tutorial_v2 as T
from engine.era_validator import era_violations


def _walk_strings(obj):
    """Yield every str leaf in a nested list/dict/tuple structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


# Every player-facing profession/discovery chain that is REACHABLE in the Clone
# Wars deployment. The GCW arcs (REBEL_CELL/IMPERIAL_SERVICE) were deleted (see
# TestGcwChainsDeleted). New live chains added here are automatically era-scanned.
LIVE_CHAIN_ATTRS = [
    "DISCOVERY_QUESTS", "SMUGGLERS_RUN", "HUNTERS_MARK", "ARTISANS_FORGE",
    "UNDERWORLD", "ELECTIVES", "ELECTIVE_STEPS", "ELECTIVE_FINAL_STEPS",
    "ELECTIVE_LABELS", "ELECTIVE_REWARDS", "STARTER_QUEST_STEPS",
    "CORE_ROOM_MESSAGES", "ROOM_HINTS",
]


class TestLiveChainsEraClean(unittest.TestCase):
    def test_live_profession_chain_strings_are_era_clean(self):
        offenders = []
        for attr in LIVE_CHAIN_ATTRS:
            obj = getattr(T, attr, None)
            self.assertIsNotNone(obj, f"{attr} missing from tutorial_v2 — update LIVE_CHAIN_ATTRS")
            for s in _walk_strings(obj):
                v = era_violations(s)
                if v:
                    offenders.append((attr, sorted(set(v)), s.replace("\n", " ")[:120]))
        self.assertEqual(
            offenders, [],
            "Off-era tokens in REACHABLE tutorial_v2 chain content "
            "(B3 era-cleanness invariant):\n  " +
            "\n  ".join(f"{a}: {toks} :: {snip}" for a, toks, snip in offenders))


class TestGcwChainsDeleted(unittest.TestCase):
    """The off-era REBEL_CELL + IMPERIAL_SERVICE arcs were DELETED (decision 1)."""

    def _maxed_char(self):
        # Far exceeds every prior requirement (missions_complete >= 2).
        return {"ships_log": {"missions_complete": 99, "smuggling_runs": 99,
                              "bounties_collected": 99},
                "attributes": {}}

    def test_gcw_chain_symbols_are_gone(self):
        # The definitions, totals, gates and the dormancy flag must no longer
        # exist as module attributes — the arcs are deleted, not merely disabled.
        for name in ("REBEL_CELL", "IMPERIAL_SERVICE",
                     "REBEL_CELL_TOTAL", "IMPERIAL_SERVICE_TOTAL",
                     "_can_start_rebel_cell", "_can_start_imperial_service",
                     "_GCW_PROFESSION_CHAINS_ENABLED"):
            self.assertFalse(
                hasattr(T, name),
                f"engine.tutorial_v2.{name} should be DELETED (GCW arc removed)")

    def test_status_display_omits_gcw_and_renders_live_chains(self):
        out = "\n".join(T.get_chain_status_lines(self._maxed_char()))
        self.assertEqual(era_violations(out), [],
                         f"chain status display leaked off-era tokens: {era_violations(out)}")
        self.assertNotIn("Rebel Cell", out)
        self.assertNotIn("Imperial Service", out)
        # the surviving live chains still render:
        self.assertIn("Smuggler's Run", out)
        self.assertIn("Underworld", out)

    def test_dispatch_does_not_reference_gcw_chains(self):
        # The dispatch must not advance a deleted chain on any of its old triggers.
        import inspect
        src = inspect.getsource(T.check_profession_chains)
        for tok in ("rebel_cell", "imperial_service", "talk_rebel_contact", "talk_kreel"):
            self.assertNotIn(tok, src,
                             f"check_profession_chains still references deleted {tok!r}")


if __name__ == "__main__":
    unittest.main()
