# -*- coding: utf-8 -*-
"""
tests/test_laneb_era_cleanness.py — Sourcebook-enrichment Lane B (2026-06-06)

B3 era-cleanness sweep of the **Clone Wars-reachable production strings** that
still carried Galactic-Civil-War residue (Imperial / Empire / TIE / X-wing /
stormtrooper) in player-facing surfaces: parser command help/examples, combat
gates, the NPC boarding/customs broadcasts, security refusal messages, the
chargen prompt, a smuggling milestone, and the Telnet login banner.

These checks are deliberately **surgical**, not a blanket file scan: several of
the touched modules (npc_commands, space_commands, housing, security) still
legitimately contain GCW-era *config* content that is reachable only via
``--era gcw`` and is owned by the separate ``T2.CW.gcw_retirement`` work item.
A naive ``"Imperial" not in source`` assertion would false-positive on that
config. So instead we assert, per fix, that the **specific** retired fragment
is gone and the **specific** era-clean replacement is present — plus two
runtime/structural checks for the boarding broadcast and the security gate.

Sibling harnesses: test_drop0a_patrol_era_cleanness.py (the encounter_patrol
boarding fix this sweep is the parser/engine sequel to),
test_e2_texture_encounter_era_cleanness.py.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# GCW tokens that must not appear in *production* (CW-reachable) strings.
_BANNED = (
    "Imperial", "IMPERIAL", "imperial",
    "Stormtrooper", "stormtrooper",
    "Empire", "Rebel", "rebel",
    "TIE fighter", "TIE-", "X-Wing", "x-wing",
)


def _read(relpath):
    with open(os.path.join(PROJECT_ROOT, relpath), encoding="utf-8") as fh:
        return fh.read()


# ══════════════════════════════════════════════════════════════════════════
# 1. Per-fix surgical pairs: (relpath, retired_fragment, replacement_or_None)
#    retired_fragment MUST be gone; replacement (if given) MUST be present.
# ══════════════════════════════════════════════════════════════════════════

_FIX_PAIRS = [
    # parser/combat_commands.py
    ("parser/combat_commands.py", "attack stormtrooper", "attack pirate"),
    ("parser/combat_commands.py", "range stormtrooper", "range pirate"),
    ("parser/combat_commands.py", "shots at the stormtrooper",
     "shots at the pirate"),
    ("parser/combat_commands.py", "Imperial law prohibits",
     "Local law prohibits unprovoked assault here."),
    ("parser/combat_commands.py", "where Imperial law doesn't reach",
     "where local law doesn't reach"),
    ("parser/combat_commands.py", "Imperial security would immediately stop",
     "Local security would immediately stop"),
    # parser/npc_commands.py
    ("parser/npc_commands.py", "the imperial garrison", "the local garrison"),
    # parser/builtin_commands.py
    ("parser/builtin_commands.py", "(Imperial security seals)",
     "(heavy security seals)"),
    # parser/crew_commands.py
    ("parser/crew_commands.py", "fire TIE-Alpha", "fire Raider-2"),
    # parser/space_commands.py
    ("parser/space_commands.py", "+ship/info x-wing", "+ship/info z95"),
    ("parser/space_commands.py", "[IMPERIAL CUSTOMS]", "[CUSTOMS]"),
    # parser/narrative_commands.py
    ("parser/narrative_commands.py", "Imperial TIE pilot",
     "cargo pilot who walked away"),
    # parser/encounter_commands.py
    ("parser/encounter_commands.py", "(Imperial patrol, pirate demand",
     "(customs patrol, pirate demand"),
    # engine/housing.py
    ("engine/housing.py", "Imperial security seals on this door",
     "Heavy security seals on this door"),
    ("engine/housing.py", "Imperial surveillance makes theft",
     "Constant surveillance makes theft"),
    # engine/security.py
    ("engine/security.py", "Imperial security patrols this area",
     "Heavy security patrols this area"),
    ("engine/security.py", "Imperial security is too heavy here",
     "Security here is too heavy"),
    # engine/creation_wizard.py
    ("engine/creation_wizard.py", "Hiding from the Empire",
     "Hiding from a syndicate"),
    # engine/ships_log.py
    ("engine/ships_log.py", "under Imperial noses",
     "under the noses of the law"),
    # server/config.py — Telnet login banner
    ("server/config.py", "and Imperial patrols", "and cartel enforcers"),
]


class TestLaneBFixPairs(unittest.TestCase):
    def test_retired_fragment_gone_and_replacement_present(self):
        # Cache file reads so we hit disk once per file.
        cache = {}
        for relpath, retired, replacement in _FIX_PAIRS:
            src = cache.setdefault(relpath, _read(relpath))
            self.assertNotIn(
                retired, src,
                f"{relpath}: retired GCW fragment {retired!r} still present")
            if replacement is not None:
                self.assertIn(
                    replacement, src,
                    f"{relpath}: era-clean replacement {replacement!r} missing")


# ══════════════════════════════════════════════════════════════════════════
# 2. Behavioral — engine.security.security_refuse_msg(SECURED, ...)
#    The SECURED-zone combat refusal is keyed on SecurityLevel, not faction;
#    drive the real function and assert it emits no GCW token, plus the new
#    era-neutral wording, for both the NPC- and PC-target branches.
# ══════════════════════════════════════════════════════════════════════════

class TestSecurityRefuseMsgEraClean(unittest.TestCase):
    def setUp(self):
        from engine.security import security_refuse_msg, SecurityLevel
        self.fn = security_refuse_msg
        self.SL = SecurityLevel

    def test_secured_npc_branch_era_clean(self):
        msg = self.fn(self.SL.SECURED, True)
        for banned in _BANNED:
            self.assertNotIn(banned, msg, f"{banned!r} leaked in NPC branch")
        self.assertIn("Heavy security patrols this area", msg)

    def test_secured_pc_branch_era_clean(self):
        msg = self.fn(self.SL.SECURED, False)
        for banned in _BANNED:
            self.assertNotIn(banned, msg, f"{banned!r} leaked in PC branch")
        self.assertIn("Security here is too heavy", msg)

    def test_non_secured_generic(self):
        # Sanity: a non-SECURED level returns the generic refusal (also clean).
        for lvl in (self.SL.CONTESTED, self.SL.LAWLESS):
            msg = self.fn(lvl, True)
            for banned in _BANNED:
                self.assertNotIn(banned, msg)


# ══════════════════════════════════════════════════════════════════════════
# 3. Structural — engine/npc_space_traffic.py boarding/customs broadcast
#    Same bug class as the encounter_patrol fix: the detain + withdraw lines
#    hardcoded "[IMPERIAL CUSTOMS]" / "[IMPERIAL BOARDING]" while the method
#    already computed era-aware customs_tag / board_tag from the _BOARD table.
#    Assert the literals are gone, the era-var concatenations are used, and
#    the (method-local) _BOARD table values are themselves era-clean.
# ══════════════════════════════════════════════════════════════════════════

class TestBoardingBroadcastEraRouting(unittest.TestCase):
    def setUp(self):
        self.src = _read("engine/npc_space_traffic.py")

    def test_no_hardcoded_imperial_tags(self):
        self.assertNotIn("[IMPERIAL CUSTOMS]", self.src)
        self.assertNotIn("[IMPERIAL BOARDING]", self.src)

    def test_detain_and_withdraw_use_era_vars(self):
        # The fixed lines route the tag through the zone-authority variables.
        self.assertIn('"[" + customs_tag + "]"', self.src)
        self.assertIn('"[" + board_tag + "]"', self.src)

    def test_board_table_values_era_clean(self):
        # The authority->label table the tags resolve from is CW-clean.
        for token in ("Clone troopers", "B1 battle droids", "Cartel enforcers",
                      "REPUBLIC CUSTOMS", "CIS CUSTOMS", "HUTT CUSTOMS"):
            self.assertIn(token, self.src,
                          f"_BOARD era-clean token {token!r} missing")
        for banned in ("Stormtrooper", "stormtrooper", "IMPERIAL"):
            # Scoped to the _BOARD literal region to avoid GCW-config noise.
            board_region = self.src[self.src.index("_BOARD = {"):
                                    self.src.index("_BOARD = {") + 700]
            self.assertNotIn(banned, board_region)


if __name__ == "__main__":
    unittest.main(verbosity=2)
