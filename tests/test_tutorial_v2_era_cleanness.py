# -*- coding: utf-8 -*-
"""
tests/test_tutorial_v2_era_cleanness.py — era-cleanness guard for the legacy
profession-chain system (drop tutorial-v2-era-remediation).

engine/tutorial_v2.py predates this deployment settling on the Clone Wars era.
Its REBEL_CELL + IMPERIAL_SERVICE profession chains are wholesale Galactic Civil
War content (Rebel Alliance recruitment / Imperial Service) and several other
chains carried scattered off-era flavor ("The Empire controls the spice mines",
"officially Imperial territory", "evading an Imperial patrol", ...). The
profession-chain dispatch (check_profession_chains) is LIVE — wired into the
mission/npc/smuggling/space command paths — so this was a reachable, uncaught
violation of the B3 era-cleanness invariant. The pre-existing era-cleanness test
is deliberately surgical (a curated (file, string) list) and never scanned this
file — the same partial-coverage blind spot the wilderness/chain drops hit.

Remediation: REBEL_CELL + IMPERIAL_SERVICE are held DORMANT (unstartable +
hidden from the status display via _GCW_PROFESSION_CHAINS_ENABLED), and the
scattered barks were reworded to CW-clean flavor. These tests pin both halves so
the gap cannot reopen — and (crucially) scan the LIVE chain data objects with a
NO-allow-list walk so any future off-era addition to a reachable chain fails.
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
# Wars deployment. REBEL_CELL + IMPERIAL_SERVICE are deliberately excluded — they
# are dormant GCW content (see TestGcwChainsDormant). New live chains added here
# are automatically era-scanned.
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


class TestGcwChainsDormant(unittest.TestCase):
    """REBEL_CELL + IMPERIAL_SERVICE must be unreachable in the CW deployment."""

    def _maxed_char(self):
        # Far exceeds every prior requirement (missions_complete >= 2).
        return {"ships_log": {"missions_complete": 99, "smuggling_runs": 99,
                              "bounties_collected": 99},
                "attributes": {}}

    def test_flag_is_off(self):
        self.assertFalse(T._GCW_PROFESSION_CHAINS_ENABLED,
                         "GCW profession chains must stay disabled in the CW era")

    def test_rebel_cell_unstartable(self):
        self.assertFalse(T._can_start_rebel_cell(self._maxed_char()),
                         "Rebel Cell (GCW) must be unstartable in Clone Wars")

    def test_imperial_service_unstartable(self):
        self.assertFalse(T._can_start_imperial_service(self._maxed_char()),
                         "Imperial Service (GCW) must be unstartable in Clone Wars")

    def test_status_display_is_era_clean_and_omits_gcw_chains(self):
        out = "\n".join(T.get_chain_status_lines(self._maxed_char()))
        self.assertEqual(era_violations(out), [],
                         f"chain status display leaked off-era tokens: {era_violations(out)}")
        self.assertNotIn("Rebel Cell", out)
        self.assertNotIn("Imperial Service", out)
        # the live chains still render (sanity: we hid only the GCW rows)
        self.assertIn("Smuggler's Run", out)


if __name__ == "__main__":
    unittest.main()
