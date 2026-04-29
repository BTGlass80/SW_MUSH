# -*- coding: utf-8 -*-
"""
tests/test_b1d1_housing_constants_era_aware.py — B.1.d.1 tests.

Per `b1_audit_v1.md` §3 row B.1.d and architecture v38 §19.7, B.1.d
is the extension of `engine/housing.py` constants to support both
eras. Split into two sub-drops:

  - **B.1.d.1 (this drop):** Pure data-table extensions. No code-flow
    changes. Four constants:
      1. `FACTION_QUARTER_TIERS` — extended with 5 CW factions × ranks
         (republic / cis / jedi_order / hutt_cartel; bounty_hunters_guild
         intentionally absent per CW design §5.5)
      2. `FACTION_HOME_PLANET`   — extended with 4 CW factions
      3. `_TIER5_ROOM_DESCS`     — extended with 5 CW factions for org-HQ rooms
      4. `_planet_view`          — extended with 4 CW planets

  - **B.1.d.2 (next drop):** Code-flow changes:
      - `FACTION_QUARTER_LOTS` extended with safe-fallback CW entries
      - `is_rebel`/insurgent-hide block generalized to is_insurgent_faction
      - integration with `assign_faction_quarters` for CW PCs
      - end-to-end test that a CW Republic PC reaching rank 1 cleanly
        gets a "no entry room available" log path (until F.5a builds
        Coruscant Coco Town)

CW data per `cw_housing_design_v1.md` §5 (Republic Coruscant Coco
Town, CIS Stalgasin Deep Hive, Jedi Coruscant Temple, Hutt Cartel
identical to GCW).

All extensions are additive; existing GCW entries are byte-equivalent
to pre-B.1.d.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. FACTION_QUARTER_TIERS
# ──────────────────────────────────────────────────────────────────────

class TestFactionQuarterTiersByteEquivalence(unittest.TestCase):
    """All GCW (faction_code, rank) entries must be byte-identical."""

    def test_empire_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        for rank in (0, 2, 4, 6):
            self.assertIn(("empire", rank), FACTION_QUARTER_TIERS)

    def test_rebel_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        for rank in (1, 3, 5):
            self.assertIn(("rebel", rank), FACTION_QUARTER_TIERS)

    def test_hutt_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        for rank in (2, 3, 5):
            self.assertIn(("hutt", rank), FACTION_QUARTER_TIERS)

    def test_empire_rank0_unchanged(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("empire", 0)]
        self.assertEqual(cfg["label"], "Imperial Barracks — Shared Bunk")
        self.assertEqual(cfg["storage_max"], 10)
        # Description is the GCW Imperial barracks text.
        self.assertIn("Imperial garrison", cfg["room_desc"])

    def test_empire_rank6_unchanged(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("empire", 6)]
        self.assertEqual(cfg["label"], "Imperial Garrison — Commander's Quarters")
        self.assertEqual(cfg["storage_max"], 100)

    def test_rebel_rank5_unchanged(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("rebel", 5)]
        self.assertEqual(cfg["label"], "Rebel Command Quarters")

    def test_hutt_rank5_unchanged(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("hutt", 5)]
        self.assertEqual(cfg["label"], "Hutt Vigo — Luxury Penthouse")
        self.assertEqual(cfg["storage_max"], 100)


class TestFactionQuarterTiersCWAdditions(unittest.TestCase):
    """CW factions present with sensible tier ladders."""

    # ── Republic ──

    def test_republic_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        # Per CW design §5.1: ranks 0, 2, 4, 5 (analog to empire 0/2/4/6).
        for rank in (0, 2, 4, 5):
            self.assertIn(("republic", rank), FACTION_QUARTER_TIERS)

    def test_republic_rank0_is_barracks_bunk(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("republic", 0)]
        self.assertIn("Bunk", cfg["label"])
        self.assertEqual(cfg["storage_max"], 10)
        # Should mention Coruscant Coco Town per CW design §5.1.
        self.assertIn("Coruscant", cfg["room_desc"])
        self.assertIn("Coco Town", cfg["room_desc"])

    def test_republic_rank5_is_commander_compound(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("republic", 5)]
        self.assertIn("Commander", cfg["label"])
        self.assertEqual(cfg["storage_max"], 100)
        # Senate-adjacent compound per CW design §5.1.
        self.assertIn("Senate", cfg["room_desc"])

    def test_republic_storage_caps_increase_by_rank(self):
        from engine.housing import FACTION_QUARTER_TIERS
        caps = [FACTION_QUARTER_TIERS[("republic", r)]["storage_max"]
                for r in (0, 2, 4, 5)]
        self.assertEqual(caps, sorted(caps))

    # ── CIS ──

    def test_cis_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        # Per CW design §5.2: ranks 0, 2, 4, 5.
        for rank in (0, 2, 4, 5):
            self.assertIn(("cis", rank), FACTION_QUARTER_TIERS)

    def test_cis_rank0_is_hive_dormitory(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("cis", 0)]
        # Stalgasin Deep Hive on Geonosis per CW design §5.2.
        self.assertIn("Stalgasin", cfg["label"])
        # Mentions hive in description.
        self.assertIn("hive", cfg["room_desc"].lower())

    def test_cis_rank5_is_council_suite(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("cis", 5)]
        self.assertIn("Council", cfg["label"])
        self.assertEqual(cfg["storage_max"], 100)

    # ── Jedi Order ──

    def test_jedi_order_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        # Per CW design §5.3: ranks 0 (Initiate), 1 (Padawan), 3 (Knight),
        # 5 (Master). Rank 2 and rank 4 are explicitly NOT in the table —
        # promotions don't always come with quarter changes for Jedi.
        for rank in (0, 1, 3, 5):
            self.assertIn(("jedi_order", rank), FACTION_QUARTER_TIERS)

    def test_jedi_order_rank0_is_initiate_cluster(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("jedi_order", 0)]
        self.assertIn("Initiate", cfg["label"])
        self.assertIn("Temple", cfg["label"])

    def test_jedi_order_rank1_is_padawan_cell(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("jedi_order", 1)]
        self.assertIn("Padawan", cfg["label"])

    def test_jedi_order_rank3_is_knight_quarters(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("jedi_order", 3)]
        self.assertIn("Knight", cfg["label"])

    def test_jedi_order_rank5_is_master_suite(self):
        from engine.housing import FACTION_QUARTER_TIERS
        cfg = FACTION_QUARTER_TIERS[("jedi_order", 5)]
        self.assertIn("Master", cfg["label"])
        self.assertEqual(cfg["storage_max"], 100)

    def test_jedi_order_no_rank2_or_rank4(self):
        # Per CW design §5.3 ladder: only 0 / 1 / 3 / 5.
        from engine.housing import FACTION_QUARTER_TIERS
        self.assertNotIn(("jedi_order", 2), FACTION_QUARTER_TIERS)
        self.assertNotIn(("jedi_order", 4), FACTION_QUARTER_TIERS)

    # ── Hutt Cartel (renamed twin of GCW hutt) ──

    def test_hutt_cartel_ranks_present(self):
        from engine.housing import FACTION_QUARTER_TIERS
        # Per CW design §5.4: identical to GCW hutt — ranks 2, 3, 5.
        for rank in (2, 3, 5):
            self.assertIn(("hutt_cartel", rank), FACTION_QUARTER_TIERS)

    def test_hutt_cartel_rank5_storage_matches_hutt(self):
        from engine.housing import FACTION_QUARTER_TIERS
        # Same numerical ladder as GCW hutt.
        for rank in (2, 3, 5):
            self.assertEqual(
                FACTION_QUARTER_TIERS[("hutt_cartel", rank)]["storage_max"],
                FACTION_QUARTER_TIERS[("hutt", rank)]["storage_max"],
            )

    # ── Bounty Hunters' Guild absent ──

    def test_bounty_hunters_guild_no_quarters(self):
        # Per CW design §5.5: BHG is housing-agnostic. No (bhg, *) entries.
        from engine.housing import FACTION_QUARTER_TIERS
        bhg_keys = [(fc, r) for (fc, r) in FACTION_QUARTER_TIERS
                    if fc == "bounty_hunters_guild"]
        self.assertEqual(bhg_keys, [])

    # ── All CW entries: shape consistency ──

    def test_all_cw_entries_have_required_keys(self):
        from engine.housing import FACTION_QUARTER_TIERS
        REQUIRED = {"label", "storage_max", "room_name", "room_desc"}
        cw_factions = ("republic", "cis", "jedi_order", "hutt_cartel")
        for (fc, rank), cfg in FACTION_QUARTER_TIERS.items():
            if fc not in cw_factions:
                continue
            missing = REQUIRED - set(cfg.keys())
            self.assertEqual(missing, set(),
                             f"{fc!r} rank {rank} missing keys: {missing}")
            self.assertIsInstance(cfg["storage_max"], int)
            self.assertGreater(cfg["storage_max"], 0)

    def test_planet_view_placeholder_used_consistently(self):
        # Most descs reference "{planet_view}" — assert that any desc
        # that does is for a faction with a known home planet, so the
        # substitution call site (assign_faction_quarters) can resolve
        # it without falling back to "the street outside".
        from engine.housing import (
            FACTION_QUARTER_TIERS, FACTION_HOME_PLANET, _planet_view,
        )
        cw_factions = ("republic", "cis", "jedi_order", "hutt_cartel")
        for (fc, rank), cfg in FACTION_QUARTER_TIERS.items():
            if fc not in cw_factions:
                continue
            if "{planet_view}" not in cfg["room_desc"]:
                continue
            # Faction must have a home planet
            self.assertIn(fc, FACTION_HOME_PLANET,
                          f"{fc} desc uses {{planet_view}} but no FACTION_HOME_PLANET entry")
            # And that planet must have a real view (not the default fallback)
            planet = FACTION_HOME_PLANET[fc]
            self.assertNotEqual(_planet_view(planet), "the street outside",
                                f"{fc}'s home planet {planet} has no _planet_view entry")


# ──────────────────────────────────────────────────────────────────────
# 2. FACTION_HOME_PLANET
# ──────────────────────────────────────────────────────────────────────

class TestFactionHomePlanetByteEquivalence(unittest.TestCase):

    def test_empire_unchanged(self):
        from engine.housing import FACTION_HOME_PLANET
        self.assertEqual(FACTION_HOME_PLANET["empire"], "tatooine")

    def test_rebel_unchanged(self):
        from engine.housing import FACTION_HOME_PLANET
        self.assertEqual(FACTION_HOME_PLANET["rebel"], "tatooine")

    def test_hutt_unchanged(self):
        from engine.housing import FACTION_HOME_PLANET
        self.assertEqual(FACTION_HOME_PLANET["hutt"], "nar_shaddaa")


class TestFactionHomePlanetCWAdditions(unittest.TestCase):

    def test_republic_on_coruscant(self):
        from engine.housing import FACTION_HOME_PLANET
        # Per CW design §5.1: Republic Guard barracks on Coruscant Coco Town.
        self.assertEqual(FACTION_HOME_PLANET["republic"], "coruscant")

    def test_cis_on_geonosis(self):
        from engine.housing import FACTION_HOME_PLANET
        # Per CW design §5.2: Stalgasin Deep Hive on Geonosis.
        self.assertEqual(FACTION_HOME_PLANET["cis"], "geonosis")

    def test_jedi_order_on_coruscant(self):
        from engine.housing import FACTION_HOME_PLANET
        # Jedi Temple is on Coruscant.
        self.assertEqual(FACTION_HOME_PLANET["jedi_order"], "coruscant")

    def test_hutt_cartel_on_nar_shaddaa(self):
        from engine.housing import FACTION_HOME_PLANET
        # Per CW design §5.4: identical to GCW hutt (Nar Shaddaa).
        self.assertEqual(FACTION_HOME_PLANET["hutt_cartel"], "nar_shaddaa")

    def test_bounty_hunters_guild_absent(self):
        # Per CW design §5.5: no faction quarters → no home planet either.
        from engine.housing import FACTION_HOME_PLANET
        self.assertNotIn("bounty_hunters_guild", FACTION_HOME_PLANET)

    def test_planet_for_faction_default_fallback_unchanged(self):
        # `_planet_for_faction` uses .get(faction_code, "tatooine"). The
        # default must still be "tatooine" so a brand-new unknown faction
        # gets a deterministic default (matches GCW pre-drop semantics).
        from engine.housing import _planet_for_faction
        self.assertEqual(_planet_for_faction("brand_new_faction"), "tatooine")
        # BHG is intentionally absent so it lands on the default.
        self.assertEqual(_planet_for_faction("bounty_hunters_guild"), "tatooine")


# ──────────────────────────────────────────────────────────────────────
# 3. _TIER5_ROOM_DESCS
# ──────────────────────────────────────────────────────────────────────

class TestTier5RoomDescsByteEquivalence(unittest.TestCase):

    GCW_FACTIONS = ("empire", "rebel", "hutt", "default")

    def test_all_gcw_keys_present(self):
        from engine.housing import _TIER5_ROOM_DESCS
        for code in self.GCW_FACTIONS:
            self.assertIn(code, _TIER5_ROOM_DESCS)

    def test_empire_entrance_unchanged(self):
        from engine.housing import _TIER5_ROOM_DESCS
        name, desc = _TIER5_ROOM_DESCS["empire"]["entrance"]
        self.assertEqual(name, "Imperial Outpost — Entry")
        self.assertIn("Imperial insignia", desc)

    def test_rebel_meeting_unchanged(self):
        from engine.housing import _TIER5_ROOM_DESCS
        name, _ = _TIER5_ROOM_DESCS["rebel"]["meeting"]
        self.assertEqual(name, "Command Center")

    def test_hutt_quarters_unchanged(self):
        from engine.housing import _TIER5_ROOM_DESCS
        name, _ = _TIER5_ROOM_DESCS["hutt"]["quarters"]
        self.assertEqual(name, "Boss's Suite")


class TestTier5RoomDescsCWAdditions(unittest.TestCase):

    CW_FACTIONS = ("republic", "cis", "jedi_order", "hutt_cartel",
                   "bounty_hunters_guild")

    REQUIRED_KEYS = ("entrance", "meeting", "armory", "barracks",
                     "barracks2", "comm", "quarters", "cell", "hangar")

    def test_all_cw_factions_present(self):
        from engine.housing import _TIER5_ROOM_DESCS
        for code in self.CW_FACTIONS:
            self.assertIn(code, _TIER5_ROOM_DESCS)

    def test_each_cw_faction_has_all_room_keys(self):
        from engine.housing import _TIER5_ROOM_DESCS
        for code in self.CW_FACTIONS:
            descs = _TIER5_ROOM_DESCS[code]
            missing = set(self.REQUIRED_KEYS) - set(descs.keys())
            self.assertEqual(missing, set(),
                             f"{code} HQ descs missing rooms: {missing}")

    def test_each_room_is_name_desc_tuple(self):
        from engine.housing import _TIER5_ROOM_DESCS
        for code in self.CW_FACTIONS:
            for rk, val in _TIER5_ROOM_DESCS[code].items():
                self.assertIsInstance(val, tuple,
                                      f"{code}.{rk} should be (name,desc) tuple")
                self.assertEqual(len(val), 2,
                                 f"{code}.{rk} should be 2-tuple")
                name, desc = val
                self.assertIsInstance(name, str)
                self.assertIsInstance(desc, str)
                self.assertGreater(len(desc), 20)

    def test_republic_descriptions_are_era_themed(self):
        from engine.housing import _TIER5_ROOM_DESCS
        # Spot-check thematic words specific to Republic.
        descs = _TIER5_ROOM_DESCS["republic"]
        self.assertIn("Republic", descs["entrance"][0])
        self.assertIn("clone trooper", descs["entrance"][1].lower())

    def test_cis_descriptions_are_era_themed(self):
        from engine.housing import _TIER5_ROOM_DESCS
        descs = _TIER5_ROOM_DESCS["cis"]
        self.assertIn("Separatist", descs["entrance"][0])
        # B1 battle droid guards the entry per CW iconography.
        joined = " ".join(d[1] for d in descs.values())
        self.assertIn("battle droid", joined.lower())

    def test_jedi_order_descriptions_are_era_themed(self):
        from engine.housing import _TIER5_ROOM_DESCS
        descs = _TIER5_ROOM_DESCS["jedi_order"]
        joined = " ".join(d[1] for d in descs.values())
        self.assertIn("kyber", joined.lower())
        self.assertIn("lightsaber", joined.lower())

    def test_hutt_cartel_uses_same_text_as_gcw_hutt(self):
        # Per CW design §5.4 ("Identical to GCW") — text is shared
        # (same descriptions). Future content drops can diverge if
        # needed.
        from engine.housing import _TIER5_ROOM_DESCS
        for rk in self.REQUIRED_KEYS:
            self.assertEqual(
                _TIER5_ROOM_DESCS["hutt_cartel"][rk],
                _TIER5_ROOM_DESCS["hutt"][rk],
                f"hutt_cartel.{rk} should match hutt.{rk}",
            )

    def test_bounty_hunters_guild_descriptions_chapter_house(self):
        # BHG has no faction quarters but DOES have an org-HQ
        # ("chapter house") for territory control — distinct
        # design point from FACTION_QUARTER_TIERS.
        from engine.housing import _TIER5_ROOM_DESCS
        descs = _TIER5_ROOM_DESCS["bounty_hunters_guild"]
        joined = " ".join(d[1] for d in descs.values())
        self.assertIn("Guild", descs["entrance"][0])
        self.assertIn("bounty", joined.lower())

    def test_get_hq_room_desc_routes_correctly(self):
        # The consumer function `_get_hq_room_desc(org_code, room_key)`
        # uses .get(org_code, _TIER5_ROOM_DESCS["default"]). CW factions
        # should land on their own descs, not the default.
        from engine.housing import _get_hq_room_desc, _TIER5_ROOM_DESCS
        for code in self.CW_FACTIONS:
            name, desc = _get_hq_room_desc(code, "entrance")
            default_name, default_desc = _TIER5_ROOM_DESCS["default"]["entrance"]
            self.assertNotEqual(name, default_name,
                                f"{code} entrance fell through to default")

    def test_unknown_faction_falls_through_to_default(self):
        from engine.housing import _get_hq_room_desc, _TIER5_ROOM_DESCS
        name, desc = _get_hq_room_desc("nonexistent_faction", "entrance")
        self.assertEqual(
            (name, desc),
            _TIER5_ROOM_DESCS["default"]["entrance"],
        )


# ──────────────────────────────────────────────────────────────────────
# 4. _planet_view
# ──────────────────────────────────────────────────────────────────────

class TestPlanetViewByteEquivalence(unittest.TestCase):

    def test_tatooine_unchanged(self):
        from engine.housing import _planet_view
        self.assertEqual(_planet_view("tatooine"),
                         "twin suns baking the dusty street below")

    def test_nar_shaddaa_unchanged(self):
        from engine.housing import _planet_view
        self.assertEqual(_planet_view("nar_shaddaa"),
                         "neon-lit Nar Shaddaa skyline")

    def test_kessel_unchanged(self):
        from engine.housing import _planet_view
        self.assertEqual(_planet_view("kessel"),
                         "grey mine exhaust drifting past the porthole")

    def test_corellia_unchanged(self):
        from engine.housing import _planet_view
        self.assertEqual(_planet_view("corellia"),
                         "Coronet City spires glinting in the morning light")

    def test_unknown_default_unchanged(self):
        from engine.housing import _planet_view
        self.assertEqual(_planet_view("nonexistent_planet"),
                         "the street outside")


class TestPlanetViewCWAdditions(unittest.TestCase):

    def test_coruscant_has_view(self):
        from engine.housing import _planet_view
        view = _planet_view("coruscant")
        self.assertIn("Coruscant", view)
        # Must not be the default fallback.
        self.assertNotEqual(view, "the street outside")

    def test_kuat_has_view(self):
        from engine.housing import _planet_view
        view = _planet_view("kuat")
        self.assertIn("Kuat", view)

    def test_kamino_has_view(self):
        from engine.housing import _planet_view
        view = _planet_view("kamino")
        # Kamino's defining feature is rain.
        self.assertTrue("rain" in view or "ocean" in view,
                        f"Kamino view should mention rain/ocean: {view!r}")

    def test_geonosis_has_view(self):
        from engine.housing import _planet_view
        view = _planet_view("geonosis")
        # Geonosis's defining feature is the rust-red wastes.
        self.assertIn("Geonosian", view)


# ──────────────────────────────────────────────────────────────────────
# 5. Cross-table consistency
# ──────────────────────────────────────────────────────────────────────

class TestCrossTableConsistency(unittest.TestCase):
    """Cross-checks between the four tables to catch inconsistencies."""

    def test_every_quarter_faction_has_home_planet(self):
        """Every faction with a quarter tier ladder must have a home
        planet; otherwise `assign_faction_quarters` falls through to
        the "tatooine" default which would be wrong for CW factions."""
        from engine.housing import (
            FACTION_QUARTER_TIERS, FACTION_HOME_PLANET,
        )
        factions_with_tiers = {fc for (fc, r) in FACTION_QUARTER_TIERS}
        # GCW factions and CW factions that have quarters must all be
        # in FACTION_HOME_PLANET. (BHG is NOT in either, by design.)
        for fc in factions_with_tiers:
            self.assertIn(fc, FACTION_HOME_PLANET,
                          f"{fc} has FACTION_QUARTER_TIERS entries but no FACTION_HOME_PLANET")

    def test_existing_consumer_helpers_work_on_cw_factions(self):
        # `_faction_min_rank` and `_best_tier_for_rank` are the consumer
        # helpers; they iterate over FACTION_QUARTER_TIERS items. They
        # must work cleanly for CW factions without any code changes
        # (the whole point of B.1.d.1 = data-only).
        from engine.housing import (
            _faction_min_rank, _best_tier_for_rank,
        )
        # Republic: min rank is 0; rank 0 → bunk; rank 5 → commander
        self.assertEqual(_faction_min_rank("republic"), 0)
        rank0 = _best_tier_for_rank("republic", 0)
        self.assertIsNotNone(rank0)
        self.assertIn("Bunk", rank0["label"])
        rank5 = _best_tier_for_rank("republic", 5)
        self.assertIsNotNone(rank5)
        self.assertIn("Commander", rank5["label"])

        # CIS: min rank is 0; rank 5 → council
        self.assertEqual(_faction_min_rank("cis"), 0)
        cis5 = _best_tier_for_rank("cis", 5)
        self.assertIn("Council", cis5["label"])

        # Jedi: min rank 0 → Initiate, rank 5 → Master
        self.assertEqual(_faction_min_rank("jedi_order"), 0)
        jedi5 = _best_tier_for_rank("jedi_order", 5)
        self.assertIn("Master", jedi5["label"])

        # Jedi rank 2 (between cells) — should fall back to rank 1 (Padawan)
        # since 1 ≤ 2 < 3 and 1 is the highest min_rank ≤ 2.
        jedi2 = _best_tier_for_rank("jedi_order", 2)
        self.assertIn("Padawan", jedi2["label"])

        # Hutt Cartel min rank 2; rank 1 → None
        self.assertEqual(_faction_min_rank("hutt_cartel"), 2)
        hc1 = _best_tier_for_rank("hutt_cartel", 1)
        self.assertIsNone(hc1)
        # Rank 4 → falls back to rank 3 (Lieutenant's Suite)
        hc4 = _best_tier_for_rank("hutt_cartel", 4)
        self.assertIn("Lieutenant", hc4["label"])

        # BHG has no quarters → min rank None
        self.assertIsNone(_faction_min_rank("bounty_hunters_guild"))
        bhg5 = _best_tier_for_rank("bounty_hunters_guild", 5)
        self.assertIsNone(bhg5)

    def test_existing_helpers_still_work_for_gcw(self):
        # GCW byte-equivalence: same inputs → same outputs as pre-drop.
        from engine.housing import (
            _faction_min_rank, _best_tier_for_rank, _planet_for_faction,
        )
        self.assertEqual(_faction_min_rank("empire"), 0)
        self.assertEqual(_faction_min_rank("rebel"), 1)
        self.assertEqual(_faction_min_rank("hutt"), 2)
        # Empire rank 6 returns the Commander tier
        e6 = _best_tier_for_rank("empire", 6)
        self.assertIn("Commander", e6["label"])
        # Rebel rank 0 (below min 1) returns None
        self.assertIsNone(_best_tier_for_rank("rebel", 0))
        # Planet defaults
        self.assertEqual(_planet_for_faction("empire"), "tatooine")
        self.assertEqual(_planet_for_faction("hutt"), "nar_shaddaa")


if __name__ == "__main__":
    unittest.main()
