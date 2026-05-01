# -*- coding: utf-8 -*-
"""
engine/housing.py — Player Housing & Homesteads system.  [v21 Drops 1-4]

Architecture
============
Housing state lives in two new DB tables (player_housing, housing_lots) plus
a housing_id column on rooms.  Housing rooms are ordinary rooms; housing_id
is the only thing that marks them as player-owned.

All rent deductions go through process_housing_rent() — no shortcuts.
See player_housing_design_v1.md for full specification.

Drop 1: Tier 1 rented rooms (rent/checkout/storage/sethome/home)
Drop 2: Description editor, trophies, room naming
Drop 3: Tier 2 faction quarters (auto-assign on rank, revoke on leave/demote)
Drop 4: Tier 3 private residences (purchase/sell, multi-room, guest list)
"""

from __future__ import annotations
import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


def _safe_json_loads(value, default=None):
    """
    Parse JSON from a string, returning `default` on malformed input.

    Handles the common housing pattern where a DB column may be either a
    JSON string or already-parsed (from upstream callers that pre-parse).
    Logs a warning on malformed JSON but does not raise.
    """
    if value is None:
        return default
    if not isinstance(value, str):
        return value if value != "" else default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError) as _e:
        log.warning("Malformed housing JSON: %s", _e)
        return default


# ── Constants ─────────────────────────────────────────────────────────────────

TIER1_DEPOSIT      = 500     # credits; returned on checkout
TIER1_WEEKLY_RENT  = 50      # credits/week
TIER1_STORAGE_MAX  = 20      # item slots
TIER1_RENT_GRACE   = 2       # weeks of missed rent before eviction warning
TIER1_EVICT_WEEKS  = 4       # weeks of missed rent before eviction

RENT_TICK_INTERVAL = 604_800  # game ticks per week (1 tick = 1 second)

# ── Drop 3: Faction Quarter definitions ──────────────────────────────────────
# tier=2, housing_type='faction_quarters', weekly_rent=0
#
# FACTION_QUARTER_TIERS maps (faction_code, min_rank) -> tier config.
# Checked in descending rank order so highest qualifying tier wins.
#
# F.5b.1 (Apr 29 2026): the in-Python literal below was renamed to
# _LEGACY_FACTION_QUARTER_TIERS and wrapped by `_resolve_faction_quarter_tiers()`,
# which loads from data/worlds/<active_era>/housing_lots.yaml on import
# and falls back to the legacy literal on YAML load failure. The
# byte-equivalence gate (tests/test_f5a1_housing_lots_loader.py
# TestGCWByteEquivalence and TestCWByteEquivalence) proves the YAML
# matches the literal exactly. Module-level binding `FACTION_QUARTER_TIERS`
# at line ~360 is what consumers see — same name, same shape, same data,
# different source.

_LEGACY_FACTION_QUARTER_TIERS = {
    # ── Empire ──
    ("empire", 0): {
        "label": "Imperial Barracks — Shared Bunk",
        "storage_max": 10,
        "room_name": "{name}'s Bunk",
        "room_desc": (
            "A narrow bunk in the Imperial garrison barracks. A thin mattress sits on "
            "a durasteel frame, with a locker bolted to the wall. The steady hum of "
            "the garrison's power generator vibrates through the floor. Stormtrooper "
            "boots echo in the corridor outside."
        ),
    },
    ("empire", 2): {
        "label": "Imperial Garrison — Private Quarters",
        "storage_max": 30,
        "room_name": "{name}'s Quarters",
        "room_desc": (
            "A private room in the Imperial garrison's officer wing. A proper bed, "
            "a desk with a holoterminal, and a reinforced locker. The door has a "
            "coded lock. A viewport shows {planet_view}."
        ),
    },
    ("empire", 4): {
        "label": "Imperial Garrison — Officer's Suite",
        "storage_max": 50,
        "room_name": "{name}'s Officer Suite",
        "room_desc": (
            "A spacious officer's suite in the garrison command level. A large desk "
            "dominates one wall, flanked by a personal holoterminal and a weapons rack. "
            "The bed is military-neat with Imperial-issue sheets. A viewport offers "
            "a commanding view of {planet_view}. A private refresher adjoins."
        ),
    },
    ("empire", 6): {
        "label": "Imperial Garrison — Commander's Quarters",
        "storage_max": 100,
        "room_name": "Commander {name}'s Quarters",
        "room_desc": (
            "The garrison commander's private quarters. Spartan Imperial efficiency "
            "meets the privileges of rank: a full-size desk with encrypted terminal, "
            "a conference table for four, personal weapons vault, and a viewport "
            "spanning the entire wall showing {planet_view}. A private meeting room "
            "adjoins through a blast-rated door."
        ),
    },
    # ── Rebel ──
    ("rebel", 1): {
        "label": "Rebel Safehouse — Shared Bunk",
        "storage_max": 20,
        "room_name": "Safehouse Bunk",
        "room_desc": (
            "A cramped bunk in a hidden Rebel safehouse. The walls are bare ferrocrete, "
            "the lighting dim and powered by a tapped junction. Cargo crates serve as "
            "furniture. A small locker is bolted under the bunk. The air tastes of "
            "recycled atmosphere and quiet defiance."
        ),
    },
    ("rebel", 3): {
        "label": "Rebel Safehouse — Private Cell",
        "storage_max": 40,
        "room_name": "{name}'s Cell",
        "room_desc": (
            "A private room in the safehouse's inner section. A bunk, a secured locker, "
            "and a small desk with an encrypted datapad. Alliance propaganda posters "
            "line one wall — hand-painted Starbird symbols. The door has an old-fashioned "
            "mechanical lock, harder to slice than electronic ones."
        ),
    },
    ("rebel", 5): {
        "label": "Rebel Command Quarters",
        "storage_max": 80,
        "room_name": "Commander {name}'s Quarters",
        "room_desc": (
            "The cell commander's quarters deep in the safehouse. A planning table "
            "covered in holographic terrain maps, an encrypted terminal with a "
            "direct HoloNet relay, and a weapons cache behind a false wall. The "
            "spartan furnishings can't hide the weight of responsibility that "
            "fills this room."
        ),
    },
    # ── Hutt Cartel ──
    ("hutt", 2): {
        "label": "Hutt Cartel — Enforcer's Safehouse",
        "storage_max": 30,
        "room_name": "Enforcer's Room",
        "room_desc": (
            "A functional safehouse room in the Hutt-controlled undercity. The door "
            "is reinforced durasteel with three separate locks. A weapons rack, a bunk, "
            "and a hidden floor compartment for 'special deliveries.' The walls are "
            "covered in cheap soundproofing material. Comfort was never the point."
        ),
    },
    ("hutt", 3): {
        "label": "Hutt Cartel — Lieutenant's Suite",
        "storage_max": 50,
        "room_name": "{name}'s Suite",
        "room_desc": (
            "A well-appointed suite in a Hutt-controlled building. The decor is "
            "gaudy — gold trim, velvet cushions, a bubbling hookah stand. A heavy "
            "curtain hides a hidden compartment large enough to hold a small arsenal. "
            "A viewport shows {planet_view}. The Hutts take care of their own."
        ),
    },
    ("hutt", 5): {
        "label": "Hutt Vigo — Luxury Penthouse",
        "storage_max": 100,
        "room_name": "Vigo {name}'s Penthouse",
        "room_desc": (
            "A luxury penthouse dripping with Hutt-style opulence. Gold-plated fixtures, "
            "a sunken conversation pit with plush cushions, a fully stocked bar of "
            "exotic spirits, and a panoramic viewport showing {planet_view}. A private "
            "turbolift connects to the street below. Armed guards patrol the corridor "
            "outside. This is what power looks like in the Outer Rim."
        ),
    },
    # ── B.1.d.1 (Apr 29 2026) — CW faction quarter tiers ─────────────────────────────
    # Per cw_housing_design_v1.md §5. Republic on Coruscant Coco Town,
    # CIS in Stalgasin Deep Hive on Geonosis, Jedi Order in Coruscant
    # Jedi Temple, Hutt Cartel identical to GCW Hutt with renamed key.
    # Bounty Hunters' Guild has no faction quarters per design §5.5.
    ("republic", 0): {
        "label": "Republic Guard Barracks — Shared Bunk",
        "storage_max": 10,
        "room_name": "{name}'s Bunk",
        "room_desc": (
            "A bunk in the Coruscant Coco Town Republic Guard barracks. Crisp "
            "white-and-blue walls, a sealed footlocker, and a holosched display "
            "showing rotation orders. The hum of the barracks ventilation is a "
            "constant white noise. A view through the slit window shows {planet_view}."
        ),
    },
    ("republic", 2): {
        "label": "Republic Guard — Private Cell",
        "storage_max": 30,
        "room_name": "{name}'s Quarters",
        "room_desc": (
            "A functional officer's cell in the Republic Guard barracks. A proper "
            "bed, a desk with an encrypted terminal, and a wall locker with a "
            "biometric lock. The Republic crest is etched above the desk. "
            "A viewport shows {planet_view}."
        ),
    },
    ("republic", 4): {
        "label": "Republic Officer Wing — Suite",
        "storage_max": 50,
        "room_name": "{name}'s Officer Suite",
        "room_desc": (
            "An officer's suite in the Republic Guard's command wing. A bedroom "
            "and an adjoining briefing room with a holotable for tactical reviews. "
            "The walls carry framed Republic battle citations. A viewport offers "
            "a commanding view of {planet_view}. A private refresher adjoins."
        ),
    },
    ("republic", 5): {
        "label": "Republic Commander — Senate-Adjacent Compound",
        "storage_max": 100,
        "room_name": "Commander {name}'s Quarters",
        "room_desc": (
            "A commander's compound on the edge of the Senate District, three rooms "
            "deep — bedchamber, war room with secure subspace comms, and a private "
            "antechamber for visiting senators or generals. The Judicial Forces "
            "insignia is woven into the carpet. A panoramic viewport spans the wall, "
            "showing {planet_view}. Guard patrols rotate past the corridor outside."
        ),
    },
    ("cis", 0): {
        "label": "Stalgasin Hive — Recruit Dormitory",
        "storage_max": 10,
        "room_name": "{name}'s Bedroll",
        "room_desc": (
            "A spartan dormitory carved into the chitinous walls of the Stalgasin "
            "Deep Hive. Low orange light pulses from glow-grubs in the ceiling. "
            "A bedroll, a stone shelf, and a single locking footlocker. The air "
            "tastes of damp resin and ozone from distant droid foundries."
        ),
    },
    ("cis", 2): {
        "label": "Stalgasin Hive — Private Alcove",
        "storage_max": 40,
        "room_name": "{name}'s Alcove",
        "room_desc": (
            "A private vaulted alcove deep in the hive. Carved chitin curves "
            "overhead. An encrypted comms station tied to the Separatist network "
            "sits beside the bedroll. Spare battle-droid parts are stacked in a "
            "corner. The Geonosian guards outside know your scent."
        ),
    },
    ("cis", 4): {
        "label": "Stalgasin Hive — Officer's Chamber",
        "storage_max": 80,
        "room_name": "{name}'s Chamber",
        "room_desc": (
            "An officer's chamber in the upper levels of the deep hive — two "
            "rooms, with a war-planning slate showing current Separatist front "
            "lines and a droid-courier dock for sending orders to droid foundries "
            "across the system. The vaulted ceiling is studded with trophy plaques."
        ),
    },
    ("cis", 5): {
        "label": "Stalgasin Hive — Council Suite",
        "storage_max": 100,
        "room_name": "Marshal {name}'s Suite",
        "room_desc": (
            "A council suite at the Stalgasin Deep Hive's restricted Council "
            "approach — three chambers, a holotable showing live tactical data "
            "from every Separatist battlefront, and a private antechamber where "
            "Count Dooku's emissaries are received. Geonosian sentinels stand "
            "watch in the outer hall. Few non-Geonosians have ever stood here."
        ),
    },
    ("jedi_order", 0): {
        "label": "Jedi Temple — Initiate Cluster",
        "storage_max": 10,
        "room_name": "Initiate {name}'s Cot",
        "room_desc": (
            "A communal sleeping arrangement in the Jedi Temple's Initiate "
            "Cluster. A simple cot among many, separated by hanging cloth "
            "partitions. Robed initiates move quietly between the rows. The "
            "room smells faintly of old books and the polished stone of the "
            "Temple. Through the high arched window, {planet_view}."
        ),
    },
    ("jedi_order", 1): {
        "label": "Jedi Temple — Padawan Cell",
        "storage_max": 30,
        "room_name": "Padawan {name}'s Cell",
        "room_desc": (
            "A small private room in the Padawan Wing, adjacent to one's "
            "Master's quarters. A pallet, a desk with study datapads, a "
            "shelf of spare robes, and a small meditation corner. The "
            "Temple's Force-presence is thick here. Through the slit window, {planet_view}."
        ),
    },
    ("jedi_order", 3): {
        "label": "Jedi Temple — Knight Quarters",
        "storage_max": 80,
        "room_name": "Knight {name}'s Quarters",
        "room_desc": (
            "A Jedi Knight's quarters in the Knight Wing — two rooms. A "
            "meditation chamber with a smooth stone floor and a single "
            "candle, and a private cell with a proper bed and a writing "
            "desk. A high arched viewport shows {planet_view}. The "
            "lightsaber rack on the wall is empty when its owner is in residence."
        ),
    },
    ("jedi_order", 5): {
        "label": "Jedi Temple — Master Suite",
        "storage_max": 100,
        "room_name": "Master {name}'s Suite",
        "room_desc": (
            "A Jedi Master's suite in the Master Wing — three rooms. A "
            "meditation hall large enough for kata practice, a Padawan "
            "teaching alcove with floor cushions and a holocron projector, "
            "and a private chamber. Carved kyber crystals are set into the "
            "walls, faintly luminous. Through the master viewport, "
            "{planet_view}. Few rooms in the galaxy carry this much "
            "accumulated Force-presence."
        ),
    },
    ("hutt_cartel", 2): {
        "label": "Hutt Cartel — Enforcer's Safehouse",
        "storage_max": 30,
        "room_name": "Enforcer's Room",
        "room_desc": (
            "A functional safehouse room in the Nar Shaddaa undercity. The door "
            "is reinforced durasteel with three separate locks. A weapons rack, a bunk, "
            "and a hidden floor compartment for 'special deliveries.' The walls are "
            "covered in cheap soundproofing material. Comfort was never the point."
        ),
    },
    ("hutt_cartel", 3): {
        "label": "Hutt Cartel — Lieutenant's Suite",
        "storage_max": 50,
        "room_name": "{name}'s Suite",
        "room_desc": (
            "A well-appointed suite in a Hutt-controlled building. The decor is "
            "gaudy — gold trim, velvet cushions, a bubbling hookah stand. A heavy "
            "curtain hides a hidden compartment large enough to hold a small arsenal. "
            "A viewport shows {planet_view}. The Hutts take care of their own."
        ),
    },
    ("hutt_cartel", 5): {
        "label": "Hutt Vigo — Luxury Penthouse",
        "storage_max": 100,
        "room_name": "Vigo {name}'s Penthouse",
        "room_desc": (
            "A luxury penthouse dripping with Hutt-style opulence. Gold-plated fixtures, "
            "a sunken conversation pit with plush cushions, a fully stocked bar of "
            "exotic spirits, and a panoramic viewport showing {planet_view}. A private "
            "turbolift connects to the street below. Armed guards patrol the corridor "
            "outside. This is what power looks like in the Outer Rim."
        ),
    },
}


# ── F.5b.1 (Apr 29 2026) — FACTION_QUARTER_TIERS data-fy ─────────────────────
# Build the (faction_code, rank) -> cfg dict from the active era's
# data/worlds/<era>/housing_lots.yaml via the F.5a.1 loader. Falls back
# to the in-Python _LEGACY_FACTION_QUARTER_TIERS literal above if the
# YAML can't be loaded (missing file, parse error, validation error,
# or world_loader import failure).
#
# The fallback is byte-equivalent to the live data because both YAMLs
# (data/worlds/{gcw,clone_wars}/housing_lots.yaml) were authored as
# byte-equivalent extractions of the in-Python literal — proven by
# tests/test_f5a1_housing_lots_loader.py's byte-equivalence test classes.
#
# Why "load on import" not "lazy"? FACTION_QUARTER_TIERS is consumed at
# module-load time by the existing helpers `_faction_min_rank` and
# `_best_tier_for_rank`, which iterate `.items()` directly. A lazy
# resolver would require either changing those callers or wrapping in a
# property — both are bigger surface-area changes than the seam needs.
# Module-level resolution captures the active era at import time, same
# pattern as engine/director.py's `_resolve_director_runtime_config()`.

def _resolve_faction_quarter_tiers() -> dict:
    """Resolve FACTION_QUARTER_TIERS from BOTH GCW and CW housing_lots.yaml,
    merged into a single (faction_code, rank) -> cfg dict.

    Pre-F.5b.1 the in-Python literal mashed both eras' faction data
    into one dict (B.1.d.1 added CW factions inline alongside GCW
    ones). The YAML split (F.5a.1) stores them per-era, but consumer
    code in this module (`_faction_min_rank`, `_best_tier_for_rank`)
    expects faction-level coverage regardless of active era — a CW PC
    in GCW DB still needs a recognizable faction code, and the
    soft-bail in B.1.d.2 only fires when the faction IS in the dict
    but its (faction, planet) lot ID isn't built yet.

    Falls back to _LEGACY_FACTION_QUARTER_TIERS on any failure
    (logs WARNING). The fallback is byte-equivalent to the merged
    YAML output because both YAMLs were authored as byte-equivalent
    extractions of the legacy literal — proven by
    tests/test_f5a1_housing_lots_loader.py's byte-equivalence tests.
    """
    try:
        from engine.world_loader import (
            load_era_manifest, load_housing_lots,
        )
        from pathlib import Path
    except Exception as e:
        log.warning(
            "[housing] world_loader import failed (%s); "
            "using legacy FACTION_QUARTER_TIERS literal.", e,
        )
        return dict(_LEGACY_FACTION_QUARTER_TIERS)

    out: dict = {}
    eras_loaded: list = []
    eras_failed: list = []
    for era in ("gcw", "clone_wars"):
        try:
            era_dir = Path("data") / "worlds" / era
            if not era_dir.is_dir():
                eras_failed.append(f"{era}:no-dir")
                continue
            manifest = load_era_manifest(era_dir)
            corpus = load_housing_lots(manifest)
        except Exception as e:
            eras_failed.append(f"{era}:{type(e).__name__}")
            log.warning(
                "[housing] %r housing_lots load failed (%s); "
                "skipping era.", era, e,
            )
            continue

        if corpus is None:
            eras_failed.append(f"{era}:no-content")
            continue

        if corpus.report.errors:
            eras_failed.append(
                f"{era}:{len(corpus.report.errors)} validation-errors"
            )
            continue

        # Merge this era's tiers into the output dict.
        era_entries = 0
        for fc, fcfg in corpus.tier2_faction_quarters.items():
            if not fcfg.tiers:
                # Faction explicitly has no quarters (e.g. BHG=null in CW).
                continue
            for tier in fcfg.tiers:
                key = (fc, tier.rank_min)
                if key in out:
                    log.warning(
                        "[housing] (faction=%r, rank=%d) appears in "
                        "multiple era YAMLs; %r entry wins.",
                        fc, tier.rank_min, era,
                    )
                out[key] = {
                    "label": tier.label,
                    "storage_max": tier.storage_max,
                    "room_name": tier.room_name,
                    "room_desc": tier.room_desc,
                }
                era_entries += 1
        eras_loaded.append(f"{era}:{era_entries}")

    if not out:
        log.warning(
            "[housing] No era YAML produced tier entries (failed: %s); "
            "using legacy FACTION_QUARTER_TIERS literal.",
            ", ".join(eras_failed) or "none",
        )
        return dict(_LEGACY_FACTION_QUARTER_TIERS)

    log.info(
        "[housing] FACTION_QUARTER_TIERS resolved from YAML "
        "(loaded: %s; failed: %s; total tier-entries=%d)",
        ", ".join(eras_loaded) or "none",
        ", ".join(eras_failed) or "none",
        len(out),
    )
    return out


FACTION_QUARTER_TIERS = _resolve_faction_quarter_tiers()


# Faction housing attachment points: (faction_code, planet) -> room_id
#
# ── F.5d (Apr 30 2026) — Jedi Temple anchor wired ────────────────────────────
# The CW jedi_order ladder (rank 0 Initiate / 1 Padawan / 3 Knight /
# 5 Master) was authored in data/worlds/clone_wars/housing_lots.yaml and
# loaded into FACTION_QUARTER_TIERS by F.5b.1, but the entry-room mapping
# below was not. Net effect pre-F.5d: a Jedi PC promoted to any rank hit
# `_faction_quarters_locatable("jedi_order") == False` and silently no-op'd.
#
# Anchor room: 211 (jedi_temple_entrance_hall, coruscant_temple zone). The
# entrance hall is the right anchor — it's the inside-the-Temple analogue
# of Jabba's Audience Chamber for hutt or the Tatooine Militia HQ for
# empire. The main gate (210) is a public outdoor concourse and would be
# wrong (you don't put your bedroom door on the front lawn).
#
# ── B.1.d.3 (Apr 30 2026) — Remaining CW faction anchors wired ───────────────
# F.5d explicitly flagged that republic/cis/hutt_cartel CW entries were
# also missing. B.1.d.3 closes that gap. The three anchors below were
# selected by reading each faction's ladder narrative in
# data/worlds/clone_wars/housing_lots.yaml and choosing the interior
# room from which the described quarters would naturally branch:
#
#   republic    → 259 coco_town_civic_block. The republic ladder describes
#                 the "Coruscant Coco Town Republic Guard barracks";
#                 room 259 is Coco Town's civic block, which the YAML
#                 explicitly tags as "host to small organizations and
#                 chapter halls" — including a clone trooper veterans'
#                 lodge already canonically present in the room. The
#                 Republic Guard chapter house lives on this block.
#
#   cis         → 418 geonosis_deep_tunnel. The cis ladder anchors at
#                 "Stalgasin Deep Hive" — vaulted alcoves, officer's
#                 chambers, council suites all carved off the deep
#                 hive's tunnel backbone. Room 418 is that backbone:
#                 the deep hive tunnel that descends from the main
#                 chamber to the foundry levels. Insurgent exit hiding
#                 (cis is in INSURGENT_FACTIONS) reads naturally from
#                 a reinforced backbone tunnel rather than the public
#                 main chamber (411).
#
#   hutt_cartel → 71 hutt_emissary_tower_audience. Direct CW analog of
#                 the GCW (hutt, "tatooine"): 19 ("Jabba's Townhouse -
#                 Audience Chamber") and (hutt, "nar_shaddaa"): 72
#                 entries — the audience chamber is the interior room
#                 where Hutt business is conducted, and the suites/
#                 penthouses described in the ladder branch from there.
FACTION_QUARTER_LOTS = {
    ("empire", "tatooine"):    22,   # Tatooine Militia HQ / Garrison
    ("empire", "corellia"):    107,  # CorSec HQ (Imperial liaison)
    ("rebel", "tatooine"):     47,   # Outskirts - Abandoned Compound
    ("rebel", "nar_shaddaa"):  69,   # Undercity - Deep Warrens access
    ("hutt", "tatooine"):      19,   # Jabba's Townhouse - Audience Chamber
    ("hutt", "nar_shaddaa"):   72,   # Hutt Emissary Tower area
    # ── F.5d (Apr 30 2026): CW jedi_order anchor ─────────────────────────────
    ("jedi_order", "coruscant"): 211,  # Jedi Temple - Entrance Hall
    # ── B.1.d.3 (Apr 30 2026): remaining CW faction anchors ──────────────────
    ("republic", "coruscant"):    259,  # Coco Town - Civic Block
    ("cis", "geonosis"):          418,  # Geonosis - Deep Hive Tunnel
    ("hutt_cartel", "nar_shaddaa"): 71,  # Hutt Emissary Tower - Audience Chamber
}

FACTION_HOME_PLANET = {
    "empire": "tatooine",
    "rebel":  "tatooine",
    "hutt":   "nar_shaddaa",
    # ── B.1.d.1 (Apr 29 2026) — CW faction home planets ────────────────────────────
    # Per cw_housing_design_v1.md §5: Republic on Coruscant, CIS on
    # Geonosis, Jedi Order on Coruscant, Hutt Cartel on Nar Shaddaa
    # (rename of GCW hutt). Bounty Hunters' Guild has no faction
    # quarters per design §5.5 and is intentionally absent — it lands
    # on the "tatooine" default via _planet_for_faction's .get fallback.
    "republic":    "coruscant",
    "cis":         "geonosis",
    "jedi_order":  "coruscant",
    "hutt_cartel": "nar_shaddaa",
}

# ── Lot definitions ──────────────────────────────────────────────────────────
# F.5b.3.c (Apr 30 2026) DELETED the legacy in-Python constants
# `HOUSING_LOTS_DROP1`, `HOUSING_LOTS_TIER3`, `HOUSING_LOTS_TIER4`,
# `HOUSING_LOTS_TIER5`. They are now sourced from
# data/worlds/<era>/housing_lots.yaml via engine/housing_lots_provider.
#
# Pre-F.5b.3.c, these constants:
#   - Lived in this file as Python literals
#   - Referenced room IDs that had drifted from the live world build
#     (e.g. "Spaceport Hotel" claimed room 29; actually room 25)
#   - Were the seed source for the housing_lots SQL table
#   - Were the soft-fallback path in housing_lots_provider when YAML
#     loading failed
#
# Post-F.5b.3.c:
#   - YAML is the only source of truth for both GCW and CW
#   - housing_lots_provider has no fallback — a YAML load failure now
#     produces zero lots and an ERROR log (fail-loud per F.6a.7
#     pattern, §18.19 seam-vs-integration discipline)
#   - The legacy values are preserved in
#     tests/test_f5b3c_legacy_constants_deleted.py as static snapshots
#     for byte-equivalence regression testing
#
# Tier 3 type catalog (purchase costs, room counts, etc.) below was
# NOT part of this deletion — it's in-Python config, not lot inventory.

# ── Drop 4: Tier 3 Private Residence definitions ────────────────────────────
# tier=3, housing_type='private_residence'

TIER3_TYPES = {
    "small": {
        "label": "Small Dwelling",
        "rooms": 1,
        "cost": 5_000,
        "weekly_rent": 100,
        "storage_max": 40,
        "has_guest_list": False,
        "vendor_slots": 0,
    },
    "standard": {
        "label": "Standard Home",
        "rooms": 2,
        "cost": 12_000,
        "weekly_rent": 175,
        "storage_max": 80,
        "has_guest_list": True,
        "vendor_slots": 0,
    },
    "large": {
        "label": "Large Home",
        "rooms": 3,
        "cost": 25_000,
        "weekly_rent": 250,
        "storage_max": 120,
        "has_guest_list": True,
        "vendor_slots": 1,
    },
}

# Per-planet room descriptions for generated Tier 3 rooms
_TIER3_ROOM_DESCS = {
    "tatooine": [
        ("Main Room", "A whitewashed adobe chamber, cool despite the twin suns outside. "
         "Moisture farming equipment hangs from hooks on the wall. A bunk sits against "
         "the curved wall, and filtered light enters through a narrow slit window."),
        ("Back Room", "A smaller chamber carved deeper into the pourstone, naturally "
         "cooler than the main room. Storage crates line the walls. A faint smell of "
         "spice lingers from a previous tenant."),
        ("Cellar", "A subterranean room below the dwelling, dug into the sandstone. "
         "It's dark, quiet, and pleasantly cool. Perfect for storage, meditation, "
         "or hiding from unwanted visitors."),
    ],
    "nar_shaddaa": [
        ("Main Room", "A converted cargo bay with surprisingly high ceilings. Neon light "
         "from the promenade seeps through plasteel shutters. The walls are bare "
         "duracrete, patched and repainted by a succession of tenants."),
        ("Side Room", "A secondary chamber, originally part of the building's ductwork. "
         "Someone has widened it into a livable space. The hum of the city's infrastructure "
         "is a constant background presence."),
        ("Storage Bay", "A sealed compartment with its own door lock. The walls are "
         "insulated — sounds don't carry in or out. Previous owners clearly valued "
         "privacy over comfort."),
    ],
    "kessel": [
        ("Main Module", "A pressurized habitation module, standard Imperial mining colony "
         "issue. Functional gray walls, a fold-out bunk, and a small viewport showing "
         "the barren surface of Kessel."),
        ("Secondary Module", "An adjoining module connected by a sealed corridor. "
         "Climate control hums steadily. The air tastes of recycled atmosphere "
         "and distant spice processing."),
        ("Utility Pod", "A cramped utility pod adapted for storage. Environmental "
         "seals keep the contents safe from Kessel's unpredictable atmosphere."),
    ],
    "corellia": [
        ("Living Room", "A proper Corellian townhouse room with real wooden floors "
         "and plastered walls. Light streams through tall windows. A fireplace — real "
         "fire, not holographic — occupies one wall."),
        ("Bedroom", "An upstairs room with a proper bed, not a bunk. Corellian "
         "craftsmanship shows in the woodwork around the windows and doorframe. "
         "A small balcony overlooks the street."),
        ("Study", "A cozy room lined with shelves. A desk faces the window, with "
         "enough space for a holoterminal and personal effects. The door has a "
         "mechanical lock — Corellians trust old technology."),
    ],
}

# F.5b.3.c (Apr 30 2026): HOUSING_LOTS_TIER3 deleted. T3 lot inventory
# is now sourced from data/worlds/<era>/housing_lots.yaml::tier3_lots
# via engine/housing_lots_provider.get_tier3_lots(). See the F.5b.3.c
# header comment above for context.

# Max homes a player can own per planet (prevents monopoly)
MAX_TIER3_PER_PLANET = 1
MAX_TIER3_TOTAL      = 4

_HOUSING_DIRS = ["northwest", "northeast", "southwest", "southeast",
                 "up", "down", "enter", "in"]

# ── Schema ────────────────────────────────────────────────────────────────────

HOUSING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS player_housing (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    tier            INTEGER NOT NULL DEFAULT 1,
    housing_type    TEXT    NOT NULL DEFAULT 'rented_room',
    entry_room_id   INTEGER NOT NULL,
    room_ids        TEXT    NOT NULL DEFAULT '[]',
    storage         TEXT    NOT NULL DEFAULT '[]',
    storage_max     INTEGER NOT NULL DEFAULT 20,
    trophies        TEXT    NOT NULL DEFAULT '[]',
    guest_list      TEXT    NOT NULL DEFAULT '[]',
    purchase_price  INTEGER DEFAULT 0,
    weekly_rent     INTEGER DEFAULT 50,
    deposit         INTEGER DEFAULT 500,
    rent_paid_until REAL    DEFAULT 0,
    rent_overdue    INTEGER DEFAULT 0,
    door_direction  TEXT    NOT NULL DEFAULT 'northwest',
    exit_id_in      INTEGER DEFAULT NULL,
    exit_id_out     INTEGER DEFAULT NULL,
    faction_code    TEXT    DEFAULT NULL,
    created_at      REAL    NOT NULL,
    last_activity   REAL    DEFAULT 0,
    FOREIGN KEY (char_id)      REFERENCES characters(id),
    FOREIGN KEY (entry_room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS housing_lots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id       INTEGER NOT NULL UNIQUE,
    planet        TEXT    NOT NULL,
    label         TEXT    NOT NULL,
    security      TEXT    NOT NULL DEFAULT 'contested',
    max_homes     INTEGER NOT NULL DEFAULT 5,
    current_homes INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);
"""

ROOMS_HOUSING_ID_SQL = "ALTER TABLE rooms ADD COLUMN housing_id INTEGER DEFAULT NULL REFERENCES player_housing(id);"
CHARACTERS_HOME_SQL  = "ALTER TABLE characters ADD COLUMN home_room_id INTEGER DEFAULT NULL REFERENCES rooms(id);"
_FACTION_CODE_COL    = "ALTER TABLE player_housing ADD COLUMN faction_code TEXT DEFAULT NULL;"
_HIDDEN_EXIT_COL     = "ALTER TABLE exits ADD COLUMN hidden_faction TEXT DEFAULT NULL;"


async def ensure_schema(db) -> None:
    """Create housing tables and columns if they don't exist. Idempotent."""
    try:
        for stmt in HOUSING_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
    except Exception as e:
        log.warning("[housing] schema create error: %s", e)

    for sql in (ROOMS_HOUSING_ID_SQL, CHARACTERS_HOME_SQL,
                _FACTION_CODE_COL, _HIDDEN_EXIT_COL):
        try:
            await db.execute(sql)
            await db.commit()
        except Exception:
            pass  # Column already exists
    # Drop 7: intrusion log table
    await ensure_intrusion_schema(db)


async def seed_lots(db) -> None:
    """Insert the Drop 1 + Drop 4 housing lots if they don't exist yet.

    F.5b.2 (Apr 30 2026): switched from direct HOUSING_LOTS_* constants
    to the era-aware provider. GCW boots see byte-equivalent behavior
    (the provider returns the legacy constants verbatim). CW boots see
    the YAML-derived lot inventory from data/worlds/clone_wars/housing_lots.yaml.
    """
    from engine.housing_lots_provider import (
        get_tier1_lots, get_tier3_lots, get_tier4_lots, get_tier5_lots,
    )
    all_lots = (
        get_tier1_lots() + get_tier3_lots()
        + get_tier4_lots() + get_tier5_lots()
    )
    for room_id, planet, label, security, max_homes in all_lots:
        existing = await db.fetchall(
            "SELECT id FROM housing_lots WHERE room_id = ?", (room_id,)
        )
        if not existing:
            try:
                await db.execute(
                    """INSERT INTO housing_lots
                       (room_id, planet, label, security, max_homes, current_homes)
                       VALUES (?, ?, ?, ?, ?, 0)""",
                    (room_id, planet, label, security, max_homes),
                )
            except Exception as e:
                log.warning("[housing] seed lot room %d: %s", room_id, e)
    await db.commit()
    log.info("[housing] Lots seeded.")


# ── Housing record helpers ────────────────────────────────────────────────────

async def get_housing(db, char_id: int) -> Optional[dict]:
    rows = await db.fetchall(
        "SELECT * FROM player_housing WHERE char_id = ? ORDER BY id DESC LIMIT 1",
        (char_id,),
    )
    return dict(rows[0]) if rows else None


async def get_housing_by_id(db, housing_id: int) -> Optional[dict]:
    rows = await db.fetchall(
        "SELECT * FROM player_housing WHERE id = ?", (housing_id,)
    )
    return dict(rows[0]) if rows else None


async def get_housing_for_room(db, room_id: int) -> Optional[dict]:
    rows = await db.fetchall(
        "SELECT * FROM player_housing WHERE room_ids LIKE ?",
        (f'%{room_id}%',),
    )
    for r in rows:
        ids = _safe_json_loads(r["room_ids"], default=[])
        if room_id in ids:
            return dict(r)
    return None


def _storage(h: dict) -> list:
    return _safe_json_loads(h.get("storage", "[]"), default=[])

def _room_ids(h: dict) -> list:
    return _safe_json_loads(h.get("room_ids", "[]"), default=[])

def _trophies(h: dict) -> list:
    return _safe_json_loads(h.get("trophies", "[]"), default=[])


# ── Lot helpers ───────────────────────────────────────────────────────────────

async def get_available_lots(db) -> list[dict]:
    rows = await db.fetchall(
        "SELECT * FROM housing_lots WHERE current_homes < max_homes ORDER BY planet, id"
    )
    return [dict(r) for r in rows]

async def get_lot(db, lot_id: int) -> Optional[dict]:
    rows = await db.fetchall(
        "SELECT * FROM housing_lots WHERE id = ?", (lot_id,)
    )
    return dict(rows[0]) if rows else None

async def get_lot_by_room(db, room_id: int) -> Optional[dict]:
    rows = await db.fetchall(
        "SELECT * FROM housing_lots WHERE room_id = ?", (room_id,)
    )
    return dict(rows[0]) if rows else None

async def _pick_door_direction(db, entry_room_id: int) -> str:
    rows = await db.fetchall(
        "SELECT direction FROM exits WHERE from_room_id = ?", (entry_room_id,)
    )
    used = {r["direction"] for r in rows}
    for d in _HOUSING_DIRS:
        if d not in used:
            return d
    for i in range(1, 100):
        d = f"door{i}"
        if d not in used:
            return d
    return "enter"


# ── Rent / Checkout ───────────────────────────────────────────────────────────

async def rent_room(db, char: dict, lot_id: int) -> dict:
    char_id = char["id"]
    existing = await get_housing(db, char_id)
    if existing:
        return {"ok": False, "msg": "You already have a place to stay. Use 'housing checkout' first."}

    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": "Invalid location."}
    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full. Try another location."}

    total_cost = TIER1_DEPOSIT + TIER1_WEEKLY_RENT
    if char.get("credits", 0) < total_cost:
        return {"ok": False,
                "msg": f"You need {total_cost:,}cr ({TIER1_DEPOSIT:,}cr deposit + {TIER1_WEEKLY_RENT:,}cr first week)."}

    entry_room = lot["room_id"]
    planet_label = lot["label"]
    room_name = f"{char['name']}'s Room"
    desc = (f"A modest rented room in {planet_label}. "
            f"A bunk, a small locker, and a view of {_planet_view(lot['planet'])}.")

    new_room_id = await db.create_room(
        name=room_name, desc_short=desc, desc_long=desc, zone_id=None,
        properties=json.dumps({"security": lot["security"], "private": True}),
    )

    door_dir = await _pick_door_direction(db, entry_room)
    exit_in_id  = await db.create_exit(entry_room, new_room_id, door_dir,
                                        f"{char['name']}'s room")
    exit_out_id = await db.create_exit(new_room_id, entry_room, "out", "Exit")

    char["credits"] = char.get("credits", 0) - total_cost
    await db.save_character(char_id, credits=char["credits"])

    now = time.time()
    cursor = await db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, rent_paid_until, door_direction,
            exit_id_in, exit_id_out, created_at, last_activity)
           VALUES (?, 1, 'rented_room', ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (char_id, entry_room, json.dumps([new_room_id]), TIER1_STORAGE_MAX,
         TIER1_WEEKLY_RENT, TIER1_DEPOSIT,
         now + RENT_TICK_INTERVAL, door_dir, exit_in_id, exit_out_id, now, now),
    )
    housing_id = cursor.lastrowid

    await db.execute(
        "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, new_room_id)
    )
    await db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,),
    )
    await db.commit()

    try:
        await db.execute(
            "UPDATE characters SET home_room_id = ? WHERE id = ?",
            (new_room_id, char_id),
        )
        await db.commit()
    except Exception:
        log.warning("rent_room: unhandled exception", exc_info=True)
        pass

    log.info("[housing] char %d rented room %d at lot %d (%s)",
             char_id, new_room_id, lot_id, lot["label"])

    return {
        "ok": True,
        "msg": (f"Room rented at {planet_label}! "
                f"Deposit: {TIER1_DEPOSIT:,}cr. "
                f"Rent: {TIER1_WEEKLY_RENT:,}cr/week. "
                f"Direction from lobby: {door_dir}."),
        "housing_id": housing_id, "room_id": new_room_id, "direction": door_dir,
    }


async def checkout_room(db, char: dict) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have a rented room."}
    if h["housing_type"] not in ("rented_room", "faction_quarters", "private_residence"):
        return {"ok": False, "msg": "Use 'housing sell' to sell a purchased home."}

    room_ids = _room_ids(h)
    storage  = _storage(h)
    trophies = _trophies(h)

    # Return all items to inventory
    returned_count = 0
    all_items = storage + trophies
    if all_items:
        try:
            inv_raw = char.get("inventory", "{}")
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
            items = inv.get("items", [])
            items.extend(all_items)
            inv["items"] = items
            await db.save_character(char_id, inventory=json.dumps(inv))
            returned_count = len(all_items)
        except Exception as e:
            log.warning("[housing] checkout item return error: %s", e)

    # Refund deposit (faction quarters have 0)
    refund = h["deposit"] if h["rent_overdue"] == 0 else 0
    if refund > 0:
        char["credits"] = char.get("credits", 0) + refund
        await db.save_character(char_id, credits=char["credits"])

    # Remove exits
    try:
        if h.get("exit_id_in"):
            await db.delete_exit(h["exit_id_in"])
        if h.get("exit_id_out"):
            await db.delete_exit(h["exit_id_out"])
    except Exception as e:
        log.warning("[housing] checkout exit removal error: %s", e)

    # Delete rooms
    for rid in room_ids:
        try:
            await db.execute("DELETE FROM rooms WHERE id = ?", (rid,))
        except Exception as e:
            log.warning("[housing] checkout room delete error: %s", e)

    # Decrement lot occupancy (Tier 1 only)
    if h["housing_type"] == "rented_room":
        lot = await get_lot_by_room(db, h["entry_room_id"])
        if lot:
            await db.execute(
                "UPDATE housing_lots SET current_homes = MAX(0, current_homes - 1) WHERE id = ?",
                (lot["id"],),
            )

    await db.execute("DELETE FROM player_housing WHERE id = ?", (h["id"],))

    try:
        await db.execute(
            "UPDATE characters SET home_room_id = NULL WHERE id = ?", (char_id,)
        )
    except Exception:
        log.warning("checkout_room: unhandled exception", exc_info=True)
        pass

    await db.commit()
    log.info("[housing] char %d checked out of housing %d", char_id, h["id"])

    msg = "Room vacated."
    if refund > 0:
        msg += f" Deposit refunded: {refund:,}cr."
    if returned_count:
        msg += f" {returned_count} item(s) returned to your inventory."
    if h["rent_overdue"] > 0:
        msg += " Deposit forfeited due to overdue rent."
    return {"ok": True, "msg": msg}


# ── Storage operations ────────────────────────────────────────────────────────

async def housing_store(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have a home to store things in."}

    storage = _storage(h)
    if len(storage) >= h["storage_max"]:
        return {"ok": False, "msg": f"Storage full ({h['storage_max']} items max)."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        match = None
        for i, it in enumerate(items):
            name = (it.get("name") or it.get("key") or "").lower()
            if item_key.lower() in name:
                match = items.pop(i)
                break
        if not match:
            return {"ok": False, "msg": f"You don't have '{item_key}' in your inventory."}

        inv["items"] = items
        storage.append(match)
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db.execute(
            "UPDATE player_housing SET storage = ?, last_activity = ? WHERE id = ?",
            (json.dumps(storage), time.time(), h["id"]),
        )
        await db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Stored: {item_name}. ({len(storage)}/{h['storage_max']} slots used)"}
    except Exception as e:
        log.warning("[housing] store error: %s", e)
        return {"ok": False, "msg": "Error storing item."}


async def housing_retrieve(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have any storage."}

    storage = _storage(h)
    match = None
    for i, it in enumerate(storage):
        name = (it.get("name") or it.get("key") or "").lower()
        if item_key.lower() in name:
            match = storage.pop(i)
            break
    if not match:
        return {"ok": False, "msg": f"'{item_key}' not found in storage."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        items.append(match)
        inv["items"] = items
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db.execute(
            "UPDATE player_housing SET storage = ?, last_activity = ? WHERE id = ?",
            (json.dumps(storage), time.time(), h["id"]),
        )
        await db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Retrieved: {item_name}. ({len(storage)}/{h['storage_max']} slots used)"}
    except Exception as e:
        log.warning("[housing] retrieve error: %s", e)
        return {"ok": False, "msg": "Error retrieving item."}


# ── Rent tick ─────────────────────────────────────────────────────────────────

async def tick_housing_rent(db, session_mgr) -> None:
    """Weekly rent collection. Handles Tier 1 and Tier 3 (faction quarters are free)."""
    try:
        now = time.time()
        rows = await db.fetchall(
            "SELECT * FROM player_housing WHERE weekly_rent > 0"
        )
        for row in rows:
            h = dict(row)
            if now < h["rent_paid_until"]:
                continue

            char_rows = await db.fetchall(
                "SELECT * FROM characters WHERE id = ?", (h["char_id"],)
            )
            if not char_rows:
                continue
            char = dict(char_rows[0])

            if char.get("credits", 0) >= h["weekly_rent"]:
                new_credits = char["credits"] - h["weekly_rent"]
                await db.save_character(char["id"], credits=new_credits)
                await db.execute(
                    "UPDATE player_housing SET rent_paid_until = ?, rent_overdue = 0, last_activity = ? WHERE id = ?",
                    (now + RENT_TICK_INTERVAL, now, h["id"]),
                )
                log.info("[housing] Rent collected: char %d paid %dcr", char["id"], h["weekly_rent"])
                sess = session_mgr.find_by_character(char["id"])
                if sess:
                    await sess.send_line(
                        f"  \033[2m[HOUSING] Weekly rent of {h['weekly_rent']:,}cr collected. "
                        f"Balance: {new_credits:,}cr.\033[0m"
                    )
            else:
                overdue = h["rent_overdue"] + 1
                await db.execute(
                    "UPDATE player_housing SET rent_overdue = ? WHERE id = ?",
                    (overdue, h["id"]),
                )
                log.warning("[housing] Rent overdue: char %d week %d", char["id"], overdue)
                sess = session_mgr.find_by_character(char["id"])
                if sess:
                    if overdue >= TIER1_EVICT_WEEKS:
                        await sess.send_line(
                            f"  \033[1;31m[HOUSING] EVICTION: Rent overdue {overdue} weeks. "
                            f"Your room has been reclaimed.\033[0m"
                        )
                    else:
                        await sess.send_line(
                            f"  \033[1;33m[HOUSING] Rent overdue ({overdue} week(s)). "
                            f"Pay {h['weekly_rent']:,}cr or vacate within "
                            f"{TIER1_EVICT_WEEKS - overdue} week(s).\033[0m"
                        )
                if overdue >= TIER1_EVICT_WEEKS:
                    await checkout_room(db, dict(char_rows[0]))

        await db.commit()
    except Exception as e:
        log.warning("[housing] rent tick error: %s", e)


# ── Status display ────────────────────────────────────────────────────────────

_TIER_LABELS = {
    1: "Tier 1 Rented Room",
    2: "Tier 2 Faction Quarters",
    3: "Tier 3 Private Residence",
    4: "Tier 4 Shopfront",
    5: "Tier 5 Organization HQ",
}


async def get_housing_status_lines(db, char: dict) -> list[str]:
    h = await get_housing(db, char["id"])
    if not h:
        lots = await get_available_lots(db)
        lines = [
            "\033[1;37m── Housing ──\033[0m",
            "  You don't have a home.",
            "",
            "  Available locations:",
        ]
        for lot in lots:
            avail = lot["max_homes"] - lot["current_homes"]
            sec = lot["security"].upper()
            lines.append(
                f"    [{lot['id']}] {lot['label']:<40} "
                f"{avail} slots  [{sec}]"
            )
        lines.append("")
        lines.append("  Use \033[1;37mhousing rent <id>\033[0m to rent a room.")
        # Hint about faction quarters
        faction_id = char.get("faction_id", "independent")
        if faction_id and faction_id != "independent":
            min_rank = _faction_min_rank(faction_id)
            if min_rank is not None:
                lines.append(f"  \033[2mFaction quarters available at rank {min_rank}+.\033[0m")
        return lines

    room_ids = _room_ids(h)
    storage  = _storage(h)
    overdue  = h.get("rent_overdue", 0)
    paid_until = h.get("rent_paid_until", 0)
    days_left = max(0, int((paid_until - time.time()) / 86400))
    tier_label = _TIER_LABELS.get(h["tier"], f"Tier {h['tier']}")

    lines = [
        "\033[1;37m── Your Housing ──\033[0m",
        f"  Type:     {tier_label}",
        f"  Location: {_lot_label_for_housing(h)}",
        f"  Room(s):  {len(room_ids)} room",
    ]
    if h["housing_type"] == "faction_quarters":
        fc = h.get("faction_code", "")
        lines.append(f"  Faction:  {fc.title() if fc else 'Unknown'}")
        lines.append("  Rent:     Free (faction membership)")
    else:
        lines.append(
            f"  Rent:     {h['weekly_rent']:,}cr/week  "
            f"({'overdue ' + str(overdue) + ' week(s)' if overdue else str(days_left) + ' days until next payment'})"
        )
    lines.append(f"  Storage:  {len(storage)}/{h['storage_max']} slots used")
    tlist = _trophies(h)
    if tlist:
        lines.append(f"  Trophies: {len(tlist)}/10 mounted")
    if overdue > 0:
        lines.append(f"  \033[1;31mWARNING: Rent {overdue} week(s) overdue. "
                     f"Eviction in {TIER1_EVICT_WEEKS - overdue} week(s).\033[0m")
    lines.append("")
    lines.append("  Commands: \033[1;37mhousing storage  housing store <item>  housing retrieve <item>  housing checkout\033[0m")
    return lines


async def get_housing_hud_info(db, char: dict, room_id: int) -> Optional[dict]:
    """Return a JSON-serialisable dict for the web client housing panel.

    Called by session.py when the character is in a housing room.
    Returns info whether the character owns the room or is a visitor.
    """
    from engine.housing import get_housing_for_room
    h = await get_housing_for_room(db, room_id)
    if not h:
        return None

    is_owner = (h.get("char_id") == char.get("id"))
    tier = h.get("tier", 1)
    tier_label = _TIER_LABELS.get(tier, f"Tier {tier}")
    housing_type = h.get("housing_type", "rented_room")
    storage = _storage(h)
    trophies = _trophies(h)
    room_ids = _room_ids(h)

    # Owner name
    owner_name = "You"
    if not is_owner:
        try:
            rows = await db.fetchall(
                "SELECT name FROM characters WHERE id = ?", (h["char_id"],)
            )
            owner_name = rows[0]["name"] if rows else "Unknown"
        except Exception:
            owner_name = "Unknown"

    info: dict = {
        "is_owner": is_owner,
        "owner_name": owner_name,
        "tier": tier,
        "tier_label": tier_label,
        "housing_type": housing_type,
        "rooms": len(room_ids),
        "storage_used": len(storage),
        "storage_max": h.get("storage_max", 0),
        "trophy_count": len(trophies),
    }

    if is_owner:
        # Rent / overdue info (not for faction quarters)
        if housing_type == "faction_quarters":
            info["rent_label"] = "Free (faction)"
            info["overdue"] = 0
        elif tier == 5:
            # HQ — maintenance from treasury
            hq_data = {}
            try:
                raw = h.get("guest_list", "{}")
                hq_data = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(hq_data, list):
                    hq_data = {}
            except Exception as _e:
                log.debug("silent except in engine/housing.py:881: %s", _e, exc_info=True)
            info["rent_label"] = f"{h.get('weekly_rent', 0):,}cr/wk"
            info["overdue"] = hq_data.get("maint_overdue", 0)
            info["guard_slots"] = hq_data.get("guard_slots", 0)
        else:
            rent = h.get("weekly_rent", 0)
            overdue = h.get("rent_overdue", 0)
            paid_until = h.get("rent_paid_until", 0)
            days_left = max(0, int((paid_until - time.time()) / 86400))
            info["rent_label"] = f"{rent:,}cr/wk"
            info["overdue"] = overdue
            info["days_left"] = days_left

        # Guest list count (tiers 3+)
        if tier >= 3 and housing_type != "org_hq":
            guests = _guest_list(h)
            info["guest_count"] = len(guests)

    return info


def _lot_label_for_housing(h: dict) -> str:
    return f"Room #{h['entry_room_id']}"

def _planet_view(planet: str) -> str:
    views = {
        "tatooine":    "twin suns baking the dusty street below",
        "nar_shaddaa": "neon-lit Nar Shaddaa skyline",
        "kessel":      "grey mine exhaust drifting past the porthole",
        "corellia":    "Coronet City spires glinting in the morning light",
        # ── B.1.d.1 (Apr 29 2026) — CW planet views ────────────────────────────────
        # Used by faction-quarter and HQ description "{planet_view}"
        # placeholder substitutions. CW planets per cw_housing_design_v1.md §4.
        "coruscant":   "the endless skyline of upper Coruscant, traffic lanes streaking between the spires",
        "kuat":        "the orbital ring of Kuat Drive Yards arcing across the void, half-built ships in slow rotation",
        "kamino":      "the storm-lashed ocean stretching to the grey horizon, rain sheeting against the platform",
        "geonosis":    "the rust-red expanse of the Geonosian wastes, hive towers rising in the distance",
    }
    return views.get(planet, "the street outside")


# ── Drop 2: Description editor + Trophies + Room naming ──────────────────────

DESC_MAX_LEN     = 2000
DESC_MIN_LEN     = 10
DESC_RENAME_COST = 1000
DESC_REDESC_COST = 0


async def set_room_name(db, char: dict, housing_id: int, new_name: str) -> dict:
    h = await get_housing_by_id(db, housing_id)
    if not h or h["char_id"] != char["id"]:
        return {"ok": False, "msg": "You don't own that room."}
    new_name = new_name.strip()[:80]
    if len(new_name) < 3:
        return {"ok": False, "msg": "Room name must be at least 3 characters."}

    room_ids = _room_ids(h)
    if not room_ids:
        return {"ok": False, "msg": "No rooms found."}
    room_id = room_ids[0]
    room_row = await db.get_room(room_id)
    if not room_row:
        return {"ok": False, "msg": "Room not found."}

    props = {}
    try:
        raw = room_row.get("properties", "{}")
        props = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        log.warning("set_room_name: unhandled exception", exc_info=True)
        pass

    rename_count = props.get("rename_count", 0)
    if rename_count > 0 and DESC_RENAME_COST > 0:
        if char.get("credits", 0) < DESC_RENAME_COST:
            return {"ok": False,
                    "msg": f"Renaming again costs {DESC_RENAME_COST:,}cr. "
                           f"You have {char.get('credits', 0):,}cr."}
        char["credits"] -= DESC_RENAME_COST
        await db.save_character(char["id"], credits=char["credits"])

    props["rename_count"] = rename_count + 1
    old_name = room_row.get("name", "your room")
    await db.update_room(room_id, name=new_name, properties=json.dumps(props))
    return {"ok": True, "msg": f"Room renamed: '{old_name}' → '{new_name}'."}


async def set_room_description(db, char: dict, housing_id: int,
                                description: str) -> dict:
    h = await get_housing_by_id(db, housing_id)
    if not h or h["char_id"] != char["id"]:
        return {"ok": False, "msg": "You don't own that room."}

    desc = description.strip()
    if len(desc) < DESC_MIN_LEN:
        return {"ok": False, "msg": f"Description too short (minimum {DESC_MIN_LEN} characters)."}
    if len(desc) > DESC_MAX_LEN:
        desc = desc[:DESC_MAX_LEN]

    room_ids = _room_ids(h)
    if not room_ids:
        return {"ok": False, "msg": "No rooms found."}
    room_id = room_ids[0]

    await db.update_room(room_id, desc_short=desc, desc_long=desc)
    await db.execute(
        "UPDATE player_housing SET last_activity = ? WHERE id = ?",
        (time.time(), housing_id),
    )
    await db.commit()
    return {"ok": True, "msg": f"Description saved. ({len(desc)}/{DESC_MAX_LEN} characters)"}


async def trophy_mount(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have a home to display trophies in."}

    trophies = _trophies(h)
    if len(trophies) >= 10:
        return {"ok": False, "msg": "Trophy wall is full (10 items maximum)."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        match = None
        for i, it in enumerate(items):
            name = (it.get("name") or it.get("key") or "").lower()
            if item_key.lower() in name:
                match = items.pop(i)
                break
        if not match:
            return {"ok": False, "msg": f"You don't have '{item_key}' in your inventory."}

        inv["items"] = items
        trophies.append(match)
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db.execute(
            "UPDATE player_housing SET trophies = ?, last_activity = ? WHERE id = ?",
            (json.dumps(trophies), time.time(), h["id"]),
        )
        await db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Mounted: {item_name} ({len(trophies)}/10 trophy slots used)."}
    except Exception as e:
        log.warning("[housing] trophy_mount error: %s", e)
        return {"ok": False, "msg": "Error mounting trophy."}


async def trophy_unmount(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have any trophies."}

    trophies = _trophies(h)
    match = None
    for i, it in enumerate(trophies):
        name = (it.get("name") or it.get("key") or "").lower()
        if item_key.lower() in name:
            match = trophies.pop(i)
            break
    if not match:
        return {"ok": False, "msg": f"No trophy matching '{item_key}' found."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        items.append(match)
        inv["items"] = items
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db.execute(
            "UPDATE player_housing SET trophies = ?, last_activity = ? WHERE id = ?",
            (json.dumps(trophies), time.time(), h["id"]),
        )
        await db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Unmounted: {item_name}. Returned to inventory."}
    except Exception as e:
        log.warning("[housing] trophy_unmount error: %s", e)
        return {"ok": False, "msg": "Error unmounting trophy."}


async def get_room_housing_display(db, room_id: int) -> Optional[dict]:
    """Return housing display data for a room (used by look command)."""
    try:
        rows = await db.fetchall(
            "SELECT housing_id FROM rooms WHERE id = ?", (room_id,)
        )
        if not rows or not rows[0]["housing_id"]:
            return None
        housing_id = rows[0]["housing_id"]
        h = await get_housing_by_id(db, housing_id)
        if not h:
            return None

        char_rows = await db.fetchall(
            "SELECT name FROM characters WHERE id = ?", (h["char_id"],)
        )
        owner_name = char_rows[0]["name"] if char_rows else "Unknown"
        trophies = _trophies(h)
        return {
            "owner_name": owner_name,
            "trophies":   trophies,
            "housing_id": housing_id,
            "tier":       h.get("tier", 1),
            "faction_code": h.get("faction_code"),
        }
    except Exception as e:
        log.warning("[housing] get_room_housing_display error: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DROP 3: Faction Quarters (Tier 2)
# ══════════════════════════════════════════════════════════════════════════════

def _faction_min_rank(faction_code: str) -> Optional[int]:
    """Return the minimum rank that qualifies for ANY faction quarter."""
    min_r = None
    for (fc, rank), _ in FACTION_QUARTER_TIERS.items():
        if fc == faction_code:
            if min_r is None or rank < min_r:
                min_r = rank
    return min_r


def _best_tier_for_rank(faction_code: str, rank_level: int) -> Optional[dict]:
    """Return the best faction quarter config for this rank, or None."""
    best = None
    best_rank = -1
    for (fc, min_rank), cfg in FACTION_QUARTER_TIERS.items():
        if fc == faction_code and rank_level >= min_rank and min_rank > best_rank:
            best = cfg
            best_rank = min_rank
    return best


def _planet_for_faction(faction_code: str) -> str:
    return FACTION_HOME_PLANET.get(faction_code, "tatooine")


def _entry_room_for_faction(faction_code: str, planet: str = None) -> Optional[int]:
    if planet is None:
        planet = _planet_for_faction(faction_code)
    return FACTION_QUARTER_LOTS.get((faction_code, planet))


# ── B.1.d.2 (Apr 29 2026) — Insurgent-faction generalization ─────────────────
# The pre-B.1.d.2 code hardcoded `is_rebel = faction_code == "rebel"`
# to decide whether a faction-quarter entry exit should be hidden from
# non-members. The semantic is "this faction is the era's insurgent
# challenger; their safehouses shouldn't be discoverable by walking
# down the hall." Generalizing it to a module-level set lets CW's
# CIS quarters use the same insurgent-quarter pattern as GCW Rebel
# safehouses without further code changes.
#
# Mapping rationale:
#   GCW: `rebel` is the insurgent (the empire is the lawful state)
#   CW:  `cis` is the insurgent (the republic is the lawful state)
#
# Republic, Empire, Jedi Order, Hutt Cartel, BHG quarters are all
# either lawful-state or independent-criminal — overt enough to not
# need exit hiding. Adding a faction here is opt-in; a faction not
# in this set keeps its exits visible (the GCW pre-drop default for
# all non-rebel factions).
INSURGENT_FACTIONS = frozenset({"rebel", "cis"})


def is_insurgent_faction(faction_code: str) -> bool:
    """True iff this faction's quarters should have hidden entry exits.

    Used by `assign_faction_quarters` to decide whether to mark the
    new exit with `hidden_faction = faction_code`. The semantic is
    "insurgent safehouse" — the exit is invisible to anyone outside
    the faction, mirroring how Rebel safehouses worked in GCW.
    """
    return faction_code in INSURGENT_FACTIONS


def _faction_quarters_locatable(faction_code: str) -> bool:
    """True iff this faction has a built entry room — i.e., quarters
    can actually be created right now, not just modeled in the data.

    Returns True for any (faction, planet) pair that has both a
    FACTION_HOME_PLANET entry AND a corresponding FACTION_QUARTER_LOTS
    entry. Returns False for CW factions whose home-planet rooms
    haven't been built yet (Coruscant Coco Town, Stalgasin Hive,
    Coruscant Jedi Temple) — F.5a builds those.

    Used by `assign_faction_quarters` to distinguish:
      - "real bug": entry-room ID set but the room is missing → log error
      - "expected, era rooms not built yet": no entry-room ID for a
        valid (faction, planet) pair → log info + advise the player
    """
    planet = _planet_for_faction(faction_code)
    return (faction_code, planet) in FACTION_QUARTER_LOTS


async def assign_faction_quarters(db, char: dict, faction_code: str,
                                   rank_level: int,
                                   session=None) -> Optional[dict]:
    """
    Assign or upgrade faction quarters for a character.
    Called from promote(), join_faction() etc.
    If they have non-faction housing, notifies but does not evict.
    """
    tier_cfg = _best_tier_for_rank(faction_code, rank_level)
    if not tier_cfg:
        return None

    char_id = char["id"]
    existing = await get_housing(db, char_id)

    # Upgrade in-place if already has quarters for this faction
    if existing and existing.get("housing_type") == "faction_quarters" \
       and existing.get("faction_code") == faction_code:
        if existing["storage_max"] < tier_cfg["storage_max"]:
            room_ids = _room_ids(existing)
            if room_ids:
                planet = _planet_for_faction(faction_code)
                new_desc = tier_cfg["room_desc"].replace(
                    "{planet_view}", _planet_view(planet))
                new_name = tier_cfg["room_name"].replace(
                    "{name}", char.get("name", "Unknown"))
                await db.update_room(room_ids[0], name=new_name,
                                     desc_short=new_desc, desc_long=new_desc)
            await db.execute(
                "UPDATE player_housing SET storage_max = ?, last_activity = ? WHERE id = ?",
                (tier_cfg["storage_max"], time.time(), existing["id"]),
            )
            await db.commit()
            msg = (f"Quarters upgraded: {tier_cfg['label']}. "
                   f"Storage expanded to {tier_cfg['storage_max']} slots.")
            log.info("[housing] Faction quarters upgraded: char %d, %s rank %d",
                     char_id, faction_code, rank_level)
            if session:
                await session.send_line(f"  \033[1;36m[HOUSING] {msg}\033[0m")
            return {"ok": True, "msg": msg}
        return None  # Already at/above tier

    # Don't evict existing non-faction housing
    if existing and existing.get("housing_type") != "faction_quarters":
        if session:
            await session.send_line(
                f"  \033[2m[HOUSING] You qualify for {tier_cfg['label']}, "
                f"but you already have housing. Use 'housing checkout' first "
                f"if you want faction quarters instead.\033[0m")
        return None

    # Create new faction quarters
    planet = _planet_for_faction(faction_code)
    entry_room_id = _entry_room_for_faction(faction_code, planet)
    if entry_room_id is None:
        # ── B.1.d.2 (Apr 29 2026) — distinguish bail paths ─────────────
        # Two reasons we hit None here:
        #   1. CW faction whose home-planet rooms haven't been built
        #      yet (republic/cis/jedi_order — F.5a builds these).
        #      Expected during the era pivot. Soft-log + tell the player
        #      so they don't think their rank-up was a no-op.
        #   2. Faction has both home-planet AND quarter-lots entries
        #      but the (faction, planet) tuple is somehow missing.
        #      Real bug or DB drift — log a warning.
        if not _faction_quarters_locatable(faction_code):
            log.info("[housing] Faction quarters not yet built for %s on %s",
                     faction_code, planet)
            if session:
                await session.send_line(
                    f"  \033[2m[HOUSING] Faction quarters for "
                    f"\033[1;36m{faction_code}\033[2m are not yet established "
                    f"in this era. Your rank promotion stands; quarters will "
                    f"be assigned automatically when the faction's home "
                    f"location ({planet}) opens.\033[0m"
                )
        else:
            log.warning("[housing] No entry room for faction %s on %s",
                        faction_code, planet)
        return None

    entry_room = await db.get_room(entry_room_id)
    if not entry_room:
        log.warning("[housing] Entry room %d for faction %s does not exist",
                    entry_room_id, faction_code)
        return None

    char_name = char.get("name", "Unknown")
    room_name = tier_cfg["room_name"].replace("{name}", char_name)
    room_desc = tier_cfg["room_desc"].replace("{planet_view}", _planet_view(planet))

    entry_security = "secured"
    try:
        props_raw = entry_room.get("properties", "{}")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        entry_security = props.get("security", "secured")
    except Exception:
        log.warning("assign_faction_quarters: unhandled exception", exc_info=True)
        pass

    new_room_id = await db.create_room(
        name=room_name, desc_short=room_desc, desc_long=room_desc,
        zone_id=None,
        properties=json.dumps({
            "security": entry_security, "private": True,
            "faction_quarters": faction_code,
        }),
    )

    door_dir = await _pick_door_direction(db, entry_room_id)

    exit_in_id = await db.create_exit(entry_room_id, new_room_id, door_dir,
                                       room_name)
    # ── B.1.d.2 (Apr 29 2026) — Generalized insurgent-exit hiding ──────
    # Insurgent factions (rebel in GCW, cis in CW) get hidden entry
    # exits — only members can see the way in. Lawful-state and
    # independent factions get visible exits (the GCW pre-drop default
    # for all non-rebel factions).
    #
    # The hidden_faction column stores the actual faction_code, so a
    # CIS PC entering a CIS safehouse will see the exit while a
    # Republic PC walking past the same intersection will not.
    if is_insurgent_faction(faction_code):
        try:
            await db.execute(
                "UPDATE exits SET hidden_faction = ? WHERE id = ?",
                (faction_code, exit_in_id),
            )
        except Exception as e:
            log.warning("[housing] hidden exit set error: %s", e)

    exit_out_id = await db.create_exit(new_room_id, entry_room_id, "out",
                                        entry_room.get("name", "Exit"))

    now = time.time()
    cursor = await db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, rent_paid_until, door_direction,
            exit_id_in, exit_id_out, faction_code, created_at, last_activity)
           VALUES (?, 2, 'faction_quarters', ?, ?, '[]', ?,
                   0, 0, 0, ?, ?, ?, ?, ?, ?)""",
        (char_id, entry_room_id, json.dumps([new_room_id]),
         tier_cfg["storage_max"], door_dir, exit_in_id, exit_out_id,
         faction_code, now, now),
    )
    housing_id = cursor.lastrowid

    await db.execute(
        "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, new_room_id)
    )

    # Set as home if none set
    try:
        rows = await db.fetchall(
            "SELECT home_room_id FROM characters WHERE id = ?", (char_id,)
        )
        if not rows or not rows[0]["home_room_id"]:
            await db.execute(
                "UPDATE characters SET home_room_id = ? WHERE id = ?",
                (new_room_id, char_id),
            )
    except Exception:
        log.warning("assign_faction_quarters: unhandled exception", exc_info=True)
        pass

    await db.commit()

    msg = (f"Assigned: {tier_cfg['label']}. "
           f"Storage: {tier_cfg['storage_max']} slots. "
           f"Direction from {entry_room.get('name', 'lobby')}: {door_dir}.")
    log.info("[housing] Faction quarters assigned: char %d, %s rank %d, room %d",
             char_id, faction_code, rank_level, new_room_id)

    if session:
        await session.send_line(f"  \033[1;36m[HOUSING] {msg}\033[0m")

    return {"ok": True, "msg": msg, "housing_id": housing_id,
            "room_id": new_room_id}


async def revoke_faction_quarters(db, char: dict, faction_code: str,
                                    session=None) -> Optional[dict]:
    """Revoke faction quarters on leave/expulsion. Contents returned."""
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return None
    if h.get("housing_type") != "faction_quarters":
        return None
    if h.get("faction_code") != faction_code:
        return None

    result = await checkout_room(db, char)
    if session:
        await session.send_line(
            f"  \033[1;33m[HOUSING] Your faction quarters have been revoked. "
            f"{result.get('msg', '')}\033[0m")
    log.info("[housing] Faction quarters revoked: char %d, %s", char_id, faction_code)
    return result


async def check_faction_quarters_on_rank_change(
        db, char: dict, faction_code: str, new_rank: int,
        session=None) -> None:
    """Called after promotion or demotion. Upgrades or revokes quarters."""
    min_rank = _faction_min_rank(faction_code)
    if min_rank is None:
        return
    if new_rank < min_rank:
        await revoke_faction_quarters(db, char, faction_code, session=session)
        return
    await assign_faction_quarters(db, char, faction_code, new_rank,
                                   session=session)


async def is_exit_visible(db, exit_row: dict, char: dict) -> bool:
    """Check if an exit is visible to a character (hidden faction exits)."""
    hidden = exit_row.get("hidden_faction")
    if not hidden:
        return True
    return char.get("faction_id", "independent") == hidden


# ══════════════════════════════════════════════════════════════════════════════
# DROP 4: Private Residences (Tier 3)
# ══════════════════════════════════════════════════════════════════════════════

def _guest_list(h: dict) -> list:
    return _safe_json_loads(h.get("guest_list", "[]"), default=[])


async def _get_char_rep_flat(db, char: Optional[dict]) -> dict:
    """F.5b.2.x: Return a flat {faction_code: int_rep} dict for a character.

    The DB API `get_all_faction_reps(char, db)` returns
    `{code: {rep, tier_key, ...}}` — but `housing_lots_provider.is_lot_rep_visible`
    expects a flat {code: int} dict. This helper converts.

    Returns an empty dict on any failure (missing char, DB error, etc.) —
    a no-rep character should see only non-gated lots, which is the
    correct behavior for an unaligned PC. Logs at DEBUG since this is
    expected for fresh characters.
    """
    if not char or not char.get("id"):
        return {}
    try:
        from engine.organizations import get_all_faction_reps
        rep_map = await get_all_faction_reps(char, db)
    except Exception as e:
        log.debug("[housing] _get_char_rep_flat failed: %s", e, exc_info=True)
        return {}
    flat: dict = {}
    for fc, info in (rep_map or {}).items():
        try:
            flat[fc] = int(info.get("rep", 0)) if isinstance(info, dict) else int(info)
        except Exception:
            flat[fc] = 0
    return flat


async def get_tier3_available_lots(db, char: Optional[dict] = None) -> list[dict]:
    """Return Tier 3 lots with open slots.

    F.5b.2: era-aware via housing_lots_provider.
    F.5b.2.x: when `char` is provided, filter rep-gated lots that the
    character can't see per `cw_housing_design_v1.md` §7.1. When `char`
    is None (callers that want the full inventory regardless), no
    filtering is applied — preserves backward compatibility for any
    pre-F.5b.2.x caller.
    """
    from engine.housing_lots_provider import get_tier3_lots, is_lot_rep_visible
    all_t3 = get_tier3_lots()
    all_lot_ids = [r for r, *_ in all_t3]
    rows = await db.fetchall(
        "SELECT * FROM housing_lots WHERE current_homes < max_homes ORDER BY planet, id"
    )
    base = [dict(r) for r in rows if r["room_id"] in all_lot_ids]
    if char is None:
        return base
    # Apply rep_gate filter
    char_rep = await _get_char_rep_flat(db, char)
    return [
        row for row in base
        if is_lot_rep_visible(row["room_id"], char_rep)
    ]


async def purchase_home(db, char: dict, lot_id: int, home_type: str) -> dict:
    """
    Purchase a Tier 3 private residence.
    Returns {"ok": bool, "msg": str, ...}.
    """
    char_id = char["id"]

    # Validate type
    cfg = TIER3_TYPES.get(home_type)
    if not cfg:
        types_str = ", ".join(f"'{k}' ({v['label']}, {v['cost']:,}cr)" for k, v in TIER3_TYPES.items())
        return {"ok": False, "msg": f"Unknown home type '{home_type}'. Options: {types_str}"}

    # Check existing housing — allow if they have Tier 1 or Tier 2 (upgrade path)
    existing = await get_housing(db, char_id)
    if existing and existing["tier"] >= 3:
        return {"ok": False,
                "msg": "You already own a home. Use 'housing sell' first."}

    # Check per-planet limit
    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": "Invalid lot."}

    # F.5b.2.x: rep_gate enforcement (cw_housing_design_v1.md §7.1).
    # If the character can't see this lot, return the same "Invalid lot."
    # message rather than leaking the rep gate's existence. Per design,
    # an unaligned PC shouldn't even know about Kuat-side properties.
    from engine.housing_lots_provider import is_lot_rep_visible
    char_rep = await _get_char_rep_flat(db, char)
    if not is_lot_rep_visible(lot["room_id"], char_rep):
        return {"ok": False, "msg": "Invalid lot."}

    lot_planet = lot["planet"]
    existing_on_planet = await db.fetchall(
        "SELECT COUNT(*) as cnt FROM player_housing WHERE char_id = ? AND tier = 3",
        (char_id,),
    )
    if existing_on_planet and existing_on_planet[0]["cnt"] >= MAX_TIER3_PER_PLANET:
        return {"ok": False, "msg": f"You already own a home on this planet (max {MAX_TIER3_PER_PLANET})."}

    # Check lot availability
    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full. Try another location."}

    # Credit check
    if char.get("credits", 0) < cfg["cost"]:
        return {"ok": False,
                "msg": f"A {cfg['label']} costs {cfg['cost']:,}cr. You have {char.get('credits', 0):,}cr."}

    entry_room_id = lot["room_id"]
    entry_room = await db.get_room(entry_room_id)
    if not entry_room:
        return {"ok": False, "msg": "Lot room not found."}

    # Get security from entry room
    entry_security = "contested"
    try:
        props_raw = entry_room.get("properties", "{}")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        entry_security = props.get("security", "contested")
    except Exception:
        log.warning("purchase_home: unhandled exception", exc_info=True)
        pass

    # Get planet room descs
    planet_descs = _TIER3_ROOM_DESCS.get(lot_planet, _TIER3_ROOM_DESCS["tatooine"])
    char_name = char.get("name", "Unknown")

    # Create rooms
    room_ids = []
    for i in range(cfg["rooms"]):
        r_name, r_desc = planet_descs[min(i, len(planet_descs) - 1)]
        if i == 0:
            r_name = f"{char_name}'s {cfg['label']}"
        else:
            r_name = f"{char_name}'s {r_name}"

        rid = await db.create_room(
            name=r_name, desc_short=r_desc, desc_long=r_desc,
            zone_id=None,
            properties=json.dumps({
                "security": entry_security, "private": True,
                "owned_home": True,
            }),
        )
        room_ids.append(rid)

    # Link rooms: entry → room 0, then chain room 0 → room 1 → room 2
    door_dir = await _pick_door_direction(db, entry_room_id)
    exit_in_id = await db.create_exit(
        entry_room_id, room_ids[0], door_dir, f"{char_name}'s {cfg['label']}")
    exit_out_id = await db.create_exit(
        room_ids[0], entry_room_id, "out", entry_room.get("name", "Exit"))

    # Internal room exits
    for i in range(len(room_ids) - 1):
        r_name_next = planet_descs[min(i + 1, len(planet_descs) - 1)][0]
        await db.create_exit(room_ids[i], room_ids[i + 1], "in",
                             r_name_next)
        await db.create_exit(room_ids[i + 1], room_ids[i], "out",
                             planet_descs[min(i, len(planet_descs) - 1)][0])

    # Charge credits
    char["credits"] = char.get("credits", 0) - cfg["cost"]
    await db.save_character(char_id, credits=char["credits"])

    # If they have existing Tier 1/2 housing, evict it first
    if existing:
        await checkout_room(db, char)

    # Create housing record
    now = time.time()
    cursor = await db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, purchase_price,
            rent_paid_until, door_direction,
            exit_id_in, exit_id_out, created_at, last_activity)
           VALUES (?, 3, 'private_residence', ?, ?, '[]', ?,
                   ?, 0, ?, ?, ?, ?, ?, ?, ?)""",
        (char_id, entry_room_id, json.dumps(room_ids), cfg["storage_max"],
         cfg["weekly_rent"], cfg["cost"],
         now + RENT_TICK_INTERVAL, door_dir,
         exit_in_id, exit_out_id, now, now),
    )
    housing_id = cursor.lastrowid

    # Mark all rooms as housing-owned
    for rid in room_ids:
        await db.execute(
            "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, rid)
        )

    # Update lot occupancy
    await db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,),
    )

    # Set as home
    try:
        await db.execute(
            "UPDATE characters SET home_room_id = ? WHERE id = ?",
            (room_ids[0], char_id),
        )
    except Exception:
        log.warning("purchase_home: unhandled exception", exc_info=True)
        pass

    await db.commit()

    log.info("[housing] char %d purchased %s at lot %d (%s), rooms %s",
             char_id, home_type, lot_id, lot["label"], room_ids)

    return {
        "ok": True,
        "msg": (f"Purchased: {cfg['label']} at {lot['label']}! "
                f"Cost: {cfg['cost']:,}cr. "
                f"Rent: {cfg['weekly_rent']:,}cr/week. "
                f"{cfg['rooms']} room(s), {cfg['storage_max']} storage slots. "
                f"Direction from {entry_room.get('name', 'lobby')}: {door_dir}."),
        "housing_id": housing_id,
        "room_ids": room_ids,
        "direction": door_dir,
    }


async def sell_home(db, char: dict) -> dict:
    """Sell a Tier 3 private residence. 50% refund, contents returned."""
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't own a home."}
    if h["housing_type"] != "private_residence":
        return {"ok": False,
                "msg": "Only purchased homes can be sold. "
                       "Use 'housing checkout' for rented rooms."}

    refund = h.get("purchase_price", 0) // 2

    # Checkout returns items and deletes rooms
    result = await checkout_room(db, char)
    if not result["ok"]:
        return result

    # Add refund
    if refund > 0:
        char_row = await db.fetchall(
            "SELECT credits FROM characters WHERE id = ?", (char_id,)
        )
        if char_row:
            new_credits = char_row[0]["credits"] + refund
            await db.save_character(char_id, credits=new_credits)
            await db.commit()

    msg = f"Home sold. Refund: {refund:,}cr (50% of purchase price)."
    if "item(s)" in result.get("msg", ""):
        msg += f" {result['msg']}"

    log.info("[housing] char %d sold home, refund %dcr", char_id, refund)
    return {"ok": True, "msg": msg}


# ── Guest list management ────────────────────────────────────────────────────

async def guest_add(db, char: dict, guest_name: str) -> dict:
    """Add a player to the housing guest list."""
    h = await get_housing(db, char["id"])
    if not h:
        return {"ok": False, "msg": "You don't have a home."}
    if h["tier"] < 3 and h["housing_type"] != "faction_quarters":
        return {"ok": False,
                "msg": "Guest lists are available for Standard Homes and above."}

    guests = _guest_list(h)
    if len(guests) >= 10:
        return {"ok": False, "msg": "Guest list is full (10 maximum)."}

    # Find the guest character
    rows = await db.fetchall(
        "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
        (guest_name.strip(),),
    )
    if not rows:
        return {"ok": False, "msg": f"Player '{guest_name}' not found."}
    guest = dict(rows[0])

    if guest["id"] == char["id"]:
        return {"ok": False, "msg": "You can't add yourself to your own guest list."}

    # Check for duplicates
    for g in guests:
        if g.get("id") == guest["id"]:
            return {"ok": False, "msg": f"{guest['name']} is already on your guest list."}

    guests.append({"id": guest["id"], "name": guest["name"]})
    await db.execute(
        "UPDATE player_housing SET guest_list = ?, last_activity = ? WHERE id = ?",
        (json.dumps(guests), time.time(), h["id"]),
    )
    await db.commit()
    return {"ok": True, "msg": f"Added {guest['name']} to your guest list."}


async def guest_remove(db, char: dict, guest_name: str) -> dict:
    """Remove a player from the housing guest list."""
    h = await get_housing(db, char["id"])
    if not h:
        return {"ok": False, "msg": "You don't have a home."}

    guests = _guest_list(h)
    match_idx = None
    for i, g in enumerate(guests):
        if g.get("name", "").lower() == guest_name.strip().lower():
            match_idx = i
            break
    if match_idx is None:
        return {"ok": False, "msg": f"'{guest_name}' is not on your guest list."}

    removed = guests.pop(match_idx)
    await db.execute(
        "UPDATE player_housing SET guest_list = ?, last_activity = ? WHERE id = ?",
        (json.dumps(guests), time.time(), h["id"]),
    )
    await db.commit()
    return {"ok": True, "msg": f"Removed {removed.get('name', guest_name)} from your guest list."}


async def get_guest_list_display(db, char: dict) -> list[str]:
    """Return formatted guest list lines."""
    h = await get_housing(db, char["id"])
    if not h:
        return ["  You don't have a home."]
    guests = _guest_list(h)
    if not guests:
        return ["  Guest list is empty.", "  Use 'housing guest add <player>' to add someone."]
    lines = [f"  \033[1;37mGuest List ({len(guests)}/10):\033[0m"]
    for g in guests:
        lines.append(f"    - {g.get('name', 'Unknown')}")
    return lines


async def get_tier3_listing_lines(db, char: dict) -> list[str]:
    """Return formatted Tier 3 lot listing for the buy command.

    F.5b.2.x: passes `char` to get_tier3_available_lots so rep-gated
    lots are hidden from listings per cw_housing_design_v1.md §7.1.
    """
    lots = await get_tier3_available_lots(db, char=char)
    if not lots:
        return ["  No lots available for private residences."]

    lines = [
        "\033[1;37m── Available Lots ──\033[0m",
        "",
    ]
    for lot in lots:
        avail = lot["max_homes"] - lot["current_homes"]
        sec = lot["security"].upper()
        discount = ""
        if lot["security"] == "lawless":
            discount = " \033[1;33m(-50% rent)\033[0m"
        elif lot["security"] == "contested":
            discount = " \033[2m(-25% rent)\033[0m"
        lines.append(
            f"    [{lot['id']}] {lot['label']:<40} "
            f"{avail} slots  [{sec}]{discount}"
        )

    lines.append("")
    lines.append("  \033[1;37mHome Types:\033[0m")
    for key, cfg in TIER3_TYPES.items():
        lines.append(
            f"    {key:<10} {cfg['label']:<20} "
            f"{cfg['rooms']} room(s)  {cfg['cost']:>7,}cr  "
            f"{cfg['weekly_rent']:>3}cr/wk  {cfg['storage_max']} storage"
        )
    lines.append("")
    lines.append("  Use \033[1;37mhousing buy <type> <lot_id>\033[0m to purchase.")
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# DROP 5: Shopfront Residences (Tier 4)
# ══════════════════════════════════════════════════════════════════════════════
"""
Tier 4 shopfronts: a home with a public-facing shop room integrated.
The shop room is freely accessible by all; private rooms behind it are
owner/guest-only.  Vendor droids in the shop room appear in the planet-wide
`market search` directory and bypass the per-room droid cap (since the room
IS a dedicated shop).  Shopfront owners get +1 to their personal droid cap.

From design doc §2.5:
  Market Stall:    1 shop + 1 private,  15,000cr, 200cr/wk, 2 droids
  Merchant's Shop: 1 shop + 2 private,  28,000cr, 300cr/wk, 3 droids
  Trading House:   2 shop + 3 private,  40,000cr, 400cr/wk, 4 droids
"""

TIER4_TYPES = {
    "stall": {
        "label":        "Market Stall",
        "shop_rooms":   1,
        "private_rooms": 1,
        "cost":         15_000,
        "weekly_rent":  200,
        "storage_max":  60,
        "droid_slots":  2,    # vendor droids allowed in shop room(s)
    },
    "shop": {
        "label":        "Merchant's Shop",
        "shop_rooms":   1,
        "private_rooms": 2,
        "cost":         28_000,
        "weekly_rent":  300,
        "storage_max":  100,
        "droid_slots":  3,
    },
    "trading_house": {
        "label":        "Trading House",
        "shop_rooms":   2,
        "private_rooms": 3,
        "cost":         40_000,
        "weekly_rent":  400,
        "storage_max":  150,
        "droid_slots":  4,
    },
}

# Security discount multipliers for Tier 4 rent (mirrors Tier 3 pattern)
_TIER4_SECURITY_DISCOUNT = {"lawless": 0.50, "contested": 0.75, "secured": 1.0}

MAX_TIER4_PER_CHAR  = 2   # can own multiple shopfronts (different planets)
MAX_TIER4_PER_PLANET = 1

# F.5b.3.c (Apr 30 2026): HOUSING_LOTS_TIER4 deleted. T4 lot inventory
# is now sourced from data/worlds/<era>/housing_lots.yaml::tier4_lots
# via engine/housing_lots_provider.get_tier4_lots().

# Shop room descriptions — publicly accessible front rooms
_TIER4_SHOP_DESCS = {
    "tatooine": [
        ("Shop Floor", "A sun-bleached commerce space opening onto Market Row. "
         "Display racks line the walls; a worn counter runs the width of the room. "
         "The smell of dust and machine oil mingles with spice from neighbouring stalls."),
        ("Front Showroom", "A larger front room with arched doorways opening to the street. "
         "Good light for displaying wares. A rolled-up security shutter hangs above the entrance."),
    ],
    "nar_shaddaa": [
        ("Shop Front", "A converted hab unit repurposed as a storefront. Neon from the Promenade "
         "casts colored light across the display shelves. The floor is polished durasteel, "
         "and a security camera covers the entrance."),
        ("Display Floor", "A wide commercial space with vaulted ceilings typical of the "
         "Promenade's older architecture. Track lighting illuminates display cases. "
         "The place smells faintly of coolant and freshly minted credit chips."),
    ],
    "kessel": [
        ("Station Kiosk", "A pressurized commercial module mounted to the station ring. "
         "Viewport shows the pocked surface of Kessel. Display panels glow with inventory "
         "listings. Climate-controlled and professionally maintained."),
    ],
    "corellia": [
        ("Shopfront", "A proper Corellian commercial space with wide display windows facing "
         "the street. Hardwood floors, plastered walls, and a hand-lettered sign space above "
         "the doorway. Smells like lacquer and honest commerce."),
        ("Trade Floor", "A two-storey commercial space with a mezzanine viewing gallery. "
         "CorSec-approved safety seals are visible on the exits. Good bones."),
    ],
}

# Private room descriptions (back rooms, owner-only)
_TIER4_PRIVATE_DESCS = {
    "tatooine": [
        ("Back Room", "The private quarters behind the shop. A bunk, storage shelves, "
         "and a small workbench. Access is locked from the shop floor."),
        ("Storage Room", "A sealed storage room with reinforced shelving. "
         "No windows. The door lock looks recently upgraded."),
        ("Owner's Suite", "A comfortable back room furnished with a proper bed "
         "and a personal terminal. Considerably nicer than the shop floor suggests."),
    ],
    "nar_shaddaa": [
        ("Owner's Quarters", "A private back room sealed from the shop floor. "
         "Sound-dampened walls, a bunk, and a mini-refrigeration unit. Cozy in the Nar Shaddaa sense."),
        ("Storage Bay", "A locked bay behind the shop. Reinforced door with "
         "a biometric reader. Whatever's in here, it stays in here."),
        ("Private Office", "A small office with a desk, a secure comms terminal, "
         "and a view of the building's internal corridors. No windows — intentional."),
    ],
    "kessel": [
        ("Hab Module", "A standard-issue habitat pod adjoining the commercial kiosk. "
         "Bunk, storage, and a sealed airlock connecting to the shop side."),
        ("Supply Room", "A pressurized storage compartment. Cold, quiet, and very locked."),
    ],
    "corellia": [
        ("Living Quarters", "Upstairs from the shop, a proper apartment. "
         "Wooden floors, tall windows, and a kitchen alcove. Smells like home."),
        ("Storeroom", "A ground-floor back room with reinforced shelving and a "
         "loading door to the alley. Good for bulk goods."),
        ("Upstairs Office", "A private office above the shop floor. A desk faces "
         "a window overlooking the commercial quarter. Lockable from inside."),
    ],
}


async def get_tier4_listing_lines(db, char: dict) -> list[str]:
    """Return formatted Tier 4 shopfront lot listing for a character.

    F.5b.2: era-aware via housing_lots_provider.
    """
    from engine.housing_lots_provider import get_tier4_lots
    lines = [
        "\033[1;37m── Shopfront Residences (Tier 4) ──\033[0m",
        "  A home with an integrated public shop room and vendor droid directory listing.",
        "",
        "  \033[1;36mAvailable Lots:\033[0m",
        f"  {'ID':<5} {'Location':<35} {'Planet':<12} {'Security':<12} {'Slots'}",
        "  " + "─" * 72,
    ]
    for room_id, planet, label, security, max_sf in get_tier4_lots():
        lot = await db.fetchall(
            "SELECT current_homes, max_homes FROM housing_lots WHERE room_id = ?",
            (room_id,),
        )
        current = lot[0]["current_homes"] if lot else 0
        max_h   = lot[0]["max_homes"]     if lot else max_sf
        avail   = max_h - current
        sec_color = {
            "secured":   "\033[1;34m",
            "contested": "\033[1;33m",
            "lawless":   "\033[1;31m",
        }.get(security, "\033[0m")
        discount = " (−50% rent)" if security == "lawless" else " (−25% rent)" if security == "contested" else ""
        lines.append(
            f"  {room_id:<5} {label:<35} {planet.title():<12} "
            f"{sec_color}{security:<12}\033[0m {avail}/{max_h}{discount}"
        )

    lines += [
        "",
        "  \033[1;37mShopfront Types:\033[0m",
    ]
    for key, cfg in TIER4_TYPES.items():
        total_rooms = cfg["shop_rooms"] + cfg["private_rooms"]
        lines.append(
            f"    {key:<14} {cfg['label']:<22} "
            f"{cfg['shop_rooms']} shop + {cfg['private_rooms']} private  "
            f"{cfg['cost']:>8,}cr  {cfg['weekly_rent']:>3}cr/wk  "
            f"{cfg['droid_slots']} droids"
        )
    lines += [
        "",
        "  Shop rooms are publicly accessible. Private rooms are owner/guest-only.",
        "  Vendor droids in shop rooms appear in the planet-wide 'market search' directory.",
        "",
        "  Use \033[1;37mhousing shopfront <type> <lot_id>\033[0m to purchase.",
    ]
    return lines


async def purchase_shopfront(db, char: dict, lot_id: int,
                              sf_type: str) -> dict:
    """
    Purchase a Tier 4 shopfront residence.
    Returns {\"ok\": bool, \"msg\": str, ...}.
    """
    char_id = char["id"]
    cfg = TIER4_TYPES.get(sf_type)
    if not cfg:
        type_str = ", ".join(f"'{k}'" for k in TIER4_TYPES)
        return {"ok": False, "msg": f"Unknown shopfront type '{sf_type}'. Options: {type_str}"}

    # Can't already own a Tier 4 on this planet
    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": "Invalid lot ID."}
    from engine.housing_lots_provider import get_tier4_lots
    if lot["room_id"] not in [r for r, *_ in get_tier4_lots()]:
        return {"ok": False, "msg": "That lot is not a shopfront location."}

    lot_planet = lot["planet"]

    existing_t4_planet = await db.fetchall(
        """SELECT COUNT(*) as cnt FROM player_housing
           WHERE char_id = ? AND tier = 4
           AND entry_room_id IN (
               SELECT room_id FROM housing_lots WHERE planet = ?
           )""",
        (char_id, lot_planet),
    )
    if existing_t4_planet and existing_t4_planet[0]["cnt"] >= MAX_TIER4_PER_PLANET:
        return {"ok": False,
                "msg": f"You already own a shopfront on {lot_planet.title()} (max {MAX_TIER4_PER_PLANET})."}

    total_t4 = await db.fetchall(
        "SELECT COUNT(*) as cnt FROM player_housing WHERE char_id = ? AND tier = 4",
        (char_id,),
    )
    if total_t4 and total_t4[0]["cnt"] >= MAX_TIER4_PER_CHAR:
        return {"ok": False,
                "msg": f"You already own {MAX_TIER4_PER_CHAR} shopfronts (maximum)."}

    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full. Try another location."}

    if char.get("credits", 0) < cfg["cost"]:
        return {"ok": False,
                "msg": f"A {cfg['label']} costs {cfg['cost']:,}cr. "
                       f"You have {char.get('credits', 0):,}cr."}

    entry_room = await db.get_room(lot["room_id"])
    if not entry_room:
        return {"ok": False, "msg": "Lot room not found."}

    # Determine effective security + rent discount
    try:
        props_raw = entry_room.get("properties", "{}")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        entry_security = props.get("security", "contested")
    except Exception:
        entry_security = "contested"
    discount = _TIER4_SECURITY_DISCOUNT.get(entry_security, 1.0)
    effective_rent = max(50, int(cfg["weekly_rent"] * discount))

    char_name = char.get("name", "Unknown")
    shop_descs    = _TIER4_SHOP_DESCS.get(lot_planet, _TIER4_SHOP_DESCS["tatooine"])
    private_descs = _TIER4_PRIVATE_DESCS.get(lot_planet, _TIER4_PRIVATE_DESCS["tatooine"])

    all_room_ids = []
    shop_room_ids    = []
    private_room_ids = []

    # Create shop rooms (publicly accessible)
    for i in range(cfg["shop_rooms"]):
        desc_pair = shop_descs[min(i, len(shop_descs) - 1)]
        r_name = f"{char_name}'s {desc_pair[0]}"
        rid = await db.create_room(
            name=r_name, desc_short=desc_pair[1], desc_long=desc_pair[1],
            zone_id=None,
            properties=json.dumps({
                "security": entry_security,
                "private": False,        # shop rooms are PUBLIC
                "owned_home": True,
                "is_shopfront": True,
                "shopfront_owner_id": char_id,
                "droid_slots": cfg["droid_slots"],
            }),
        )
        all_room_ids.append(rid)
        shop_room_ids.append(rid)

    # Create private rooms (owner/guest-only)
    for i in range(cfg["private_rooms"]):
        desc_pair = private_descs[min(i, len(private_descs) - 1)]
        r_name = f"{char_name}'s {desc_pair[0]}"
        rid = await db.create_room(
            name=r_name, desc_short=desc_pair[1], desc_long=desc_pair[1],
            zone_id=None,
            properties=json.dumps({
                "security": entry_security,
                "private": True,
                "owned_home": True,
                "is_shopfront": False,
            }),
        )
        all_room_ids.append(rid)
        private_room_ids.append(rid)

    # Wire exits: public street → first shop room
    door_dir = await _pick_door_direction(db, lot["room_id"])
    exit_in_id = await db.create_exit(
        lot["room_id"], shop_room_ids[0], door_dir,
        f"{char_name}'s {cfg['label']}"
    )
    exit_out_id = await db.create_exit(
        shop_room_ids[0], lot["room_id"], "out",
        entry_room.get("name", "Exit")
    )

    # Chain shop rooms together (if Trading House with 2 shop rooms)
    for i in range(len(shop_room_ids) - 1):
        await db.create_exit(shop_room_ids[i], shop_room_ids[i + 1],
                              "in", "Back of Shop")
        await db.create_exit(shop_room_ids[i + 1], shop_room_ids[i],
                              "out", "Shop Floor")

    # Shop → private transition (locked private door)
    if private_room_ids:
        last_shop = shop_room_ids[-1]
        await db.create_exit(last_shop, private_room_ids[0],
                              "northwest", "Private Quarters")
        await db.create_exit(private_room_ids[0], last_shop,
                              "out", "Shop Floor")

    # Chain private rooms together
    for i in range(len(private_room_ids) - 1):
        pdesc_a = private_descs[min(i,     len(private_descs) - 1)][0]
        pdesc_b = private_descs[min(i + 1, len(private_descs) - 1)][0]
        await db.create_exit(private_room_ids[i],     private_room_ids[i + 1],
                              "in",  pdesc_b)
        await db.create_exit(private_room_ids[i + 1], private_room_ids[i],
                              "out", pdesc_a)

    # Charge credits
    char["credits"] = char.get("credits", 0) - cfg["cost"]
    await db.save_character(char_id, credits=char["credits"])

    # Create housing record
    now = time.time()
    cursor = await db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, purchase_price,
            rent_paid_until, door_direction,
            exit_id_in, exit_id_out, created_at, last_activity)
           VALUES (?, 4, 'shopfront', ?, ?, '[]', ?,
                   ?, 0, ?, ?, ?, ?, ?, ?, ?)""",
        (char_id, lot["room_id"], json.dumps(all_room_ids),
         cfg["storage_max"], effective_rent, cfg["cost"],
         now + RENT_TICK_INTERVAL, door_dir,
         exit_in_id, exit_out_id, now, now),
    )
    housing_id = cursor.lastrowid

    # Mark all rooms as housing-owned
    for rid in all_room_ids:
        await db.execute(
            "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, rid)
        )

    # Update lot occupancy
    await db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,),
    )

    # Set as home if they don't have one
    try:
        char_row = await db.fetchall(
            "SELECT home_room_id FROM characters WHERE id = ?", (char_id,)
        )
        if char_row and not char_row[0]["home_room_id"]:
            await db.execute(
                "UPDATE characters SET home_room_id = ? WHERE id = ?",
                (private_room_ids[0] if private_room_ids else shop_room_ids[0], char_id),
            )
    except Exception:
        log.warning("purchase_shopfront: unhandled exception", exc_info=True)
        pass

    await db.commit()

    log.info("[housing] char %d purchased shopfront '%s' at lot %d (%s), rooms %s",
             char_id, sf_type, lot_id, lot["label"], all_room_ids)

    rent_note = (f" (−{int((1 - discount)*100)}% discount for {entry_security} zone)"
                 if discount < 1.0 else "")
    return {
        "ok":          True,
        "msg":         (f"Purchased: {cfg['label']} at {lot['label']}! "
                        f"Cost: {cfg['cost']:,}cr. "
                        f"Rent: {effective_rent:,}cr/week{rent_note}. "
                        f"{cfg['shop_rooms']} shop room(s) + {cfg['private_rooms']} private. "
                        f"Up to {cfg['droid_slots']} vendor droids in shop. "
                        f"Direction from street: {door_dir}."),
        "housing_id":  housing_id,
        "room_ids":    all_room_ids,
        "shop_room_ids": shop_room_ids,
        "private_room_ids": private_room_ids,
        "direction":   door_dir,
    }


async def sell_shopfront(db, char: dict) -> dict:
    """Sell a Tier 4 shopfront. 50% refund, vendor droids recalled first."""
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't own a shopfront."}
    if h["housing_type"] != "shopfront":
        return {"ok": False,
                "msg": "You don't own a shopfront. Use 'housing sell' for residences."}

    room_ids = _safe_json_loads(h["room_ids"], default=[]) or []

    # Recall any vendor droids from shop rooms first
    recalled = 0
    for rid in room_ids:
        try:
            droids = await db.get_objects_in_room(rid, "vendor_droid")
            for d in droids:
                await db.execute(
                    "UPDATE objects SET room_id = NULL WHERE id = ?", (d["id"],)
                )
                recalled += 1
        except Exception:
            log.warning("sell_shopfront: unhandled exception", exc_info=True)
            pass

    # Return storage items to character inventory
    storage = _safe_json_loads(h["storage"], default=[]) or []
    if storage:
        try:
            inv_raw = char.get("inventory", "{}")
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
            inv.setdefault("items", []).extend(storage)
            await db.save_character(char_id, inventory=json.dumps(inv))
        except Exception:
            log.warning("sell_shopfront: unhandled exception", exc_info=True)
            pass

    # Refund
    refund = h.get("purchase_price", 0) // 2
    if refund > 0:
        char["credits"] = char.get("credits", 0) + refund
        await db.save_character(char_id, credits=char["credits"])

    # Remove exits
    for exit_id in (h.get("exit_id_in"), h.get("exit_id_out")):
        if exit_id:
            try:
                await db.execute("DELETE FROM exits WHERE id = ?", (exit_id,))
            except Exception:
                log.warning("sell_shopfront: unhandled exception", exc_info=True)
                pass

    # Remove all housing rooms
    for rid in room_ids:
        try:
            await db.execute("DELETE FROM exits WHERE from_room = ? OR to_room = ?",
                                  (rid, rid))
            await db.execute("DELETE FROM rooms WHERE id = ?", (rid,))
        except Exception:
            log.warning("sell_shopfront: unhandled exception", exc_info=True)
            pass

    # Update lot occupancy
    try:
        await db.execute(
            "UPDATE housing_lots SET current_homes = MAX(0, current_homes - 1) "
            "WHERE room_id = ?",
            (h["entry_room_id"],),
        )
    except Exception:
        log.warning("sell_shopfront: unhandled exception", exc_info=True)
        pass

    # Delete housing record
    await db.execute("DELETE FROM player_housing WHERE id = ?", (h["id"],))

    # Clear home_room_id if it pointed here
    try:
        await db.execute(
            "UPDATE characters SET home_room_id = NULL "
            "WHERE id = ? AND home_room_id IN (%s)" % ",".join("?" * len(room_ids)),
            [char_id] + room_ids,
        )
    except Exception:
        log.warning("sell_shopfront: unhandled exception", exc_info=True)
        pass

    await db.commit()
    log.info("[housing] char %d sold shopfront, refund %dcr, %d droids recalled",
             char_id, refund, recalled)

    recall_note = f" {recalled} vendor droid(s) recalled." if recalled else ""
    return {
        "ok": True,
        "msg": (f"Shopfront sold. Refund: {refund:,}cr.{recall_note} "
                f"Storage items returned to inventory."),
    }


async def get_shopfront_info(db, char: dict) -> Optional[dict]:
    """Return Tier 4 housing record for character, or None."""
    char_id = char["id"]
    try:
        rows = await db.fetchall(
            "SELECT * FROM player_housing WHERE char_id = ? AND tier = 4",
            (char_id,),
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_shopfront_info: unhandled exception", exc_info=True)
        return None


async def get_market_directory(db, planet: Optional[str] = None) -> list[dict]:
    """
    Return a list of all shopfront vendor droids across all planets
    (or filtered to a specific planet) for the `market search` command.

    Each entry: {shop_name, owner_name, room_name, planet, droid_id,
                 item_count, tier_key}
    """
    results = []
    try:
        # Find all shopfront rooms
        query = (
            "SELECT r.id as room_id, r.name as room_name, r.properties "
            "FROM rooms r "
            "WHERE r.properties LIKE '%is_shopfront%true%'"
        )
        shop_rooms = await db.fetchall(query)

        for sr in shop_rooms:
            props_raw = sr.get("properties", "{}")
            try:
                props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
            except Exception:
                props = {}
            if not props.get("is_shopfront"):
                continue

            # Get planet from lot
            room_id = sr["room_id"]
            lot_rows = await db.fetchall(
                """SELECT hl.planet FROM housing_lots hl
                   JOIN player_housing ph ON ph.entry_room_id = hl.room_id
                   WHERE ? = ANY(
                       SELECT value FROM json_each(ph.room_ids)
                   )""",
                (room_id,),
            )
            # Fallback: walk up through housing record
            if not lot_rows:
                ph_rows = await db.fetchall(
                    "SELECT * FROM player_housing WHERE room_ids LIKE ?",
                    (f"%{room_id}%",),
                )
                if ph_rows:
                    entry_room = ph_rows[0]["entry_room_id"]
                    lot_row2 = await db.fetchall(
                        "SELECT planet FROM housing_lots WHERE room_id = ?",
                        (entry_room,),
                    )
                    room_planet = lot_row2[0]["planet"] if lot_row2 else "unknown"
                else:
                    room_planet = "unknown"
            else:
                room_planet = lot_rows[0]["planet"]

            if planet and room_planet != planet.lower():
                continue

            # Get vendor droids in this room
            droids = await db.get_objects_in_room(room_id, "vendor_droid")
            for d in droids:
                try:
                    from engine.vendor_droids import _load_data
                    data = _load_data(d)
                    if not data.get("shop_name"):
                        continue
                    inventory = data.get("inventory", [])
                    item_count = sum(
                        1 for slot in inventory if slot.get("quantity", 0) > 0
                    )
                    results.append({
                        "droid_id":   d["id"],
                        "shop_name":  data.get("shop_name", "Unknown Shop"),
                        "shop_desc":  data.get("shop_desc", ""),
                        "owner_name": data.get("owner_name", "Unknown"),
                        "room_id":    room_id,
                        "room_name":  sr.get("room_name", "Unknown Location"),
                        "planet":     room_planet,
                        "tier_key":   data.get("tier_key", "gn4"),
                        "item_count": item_count,
                    })
                except Exception:
                    log.warning("get_market_directory: unhandled exception", exc_info=True)
                    pass
    except Exception as e:
        log.warning("[housing] market directory error: %s", e)

    return results


def is_shopfront_room_props(props_raw) -> bool:
    """Quick check: is this room a shopfront shop room?"""
    try:
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        return bool(props.get("is_shopfront"))
    except Exception:
        log.warning("is_shopfront_room_props: unhandled exception", exc_info=True)
        return False


def get_effective_droid_cap(char: dict, owned_shopfronts: int) -> int:
    """
    Return effective vendor droid cap for a character.
    Base cap is MAX_DROIDS_PER_OWNER (3).
    Each shopfront owned adds +1 (capped at 6 total per design doc §2.5).
    """
    from engine.vendor_droids import MAX_DROIDS_PER_OWNER
    return min(6, MAX_DROIDS_PER_OWNER + owned_shopfronts)


# ══════════════════════════════════════════════════════════════════════════════
# DROP 7: Security & Intrusion
# ══════════════════════════════════════════════════════════════════════════════
"""
Housing security gates and intrusion mechanics.

Design doc §6:
  Secured zone housing  — locked, unpickable, no combat inside
  Contested zone housing — Security skill check difficulty 25 to pick
  Lawless zone housing   — Security difficulty 20 to pick, Strength 15 to force

  Theft:
    Contested: Heroic Sneak + Security combined (difficulty 30+)
    Lawless:   Moderate Sneak (difficulty 15) for main room items

  All intrusion attempts logged to `housing_intrusions` table.
  Owner alerted if online.

Architecture: all rolls go through perform_skill_check(). No direct dice rolls here.
"""

HOUSING_INTRUSIONS_SQL = """
CREATE TABLE IF NOT EXISTS housing_intrusions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    housing_id  INTEGER NOT NULL REFERENCES player_housing(id),
    intruder_id INTEGER NOT NULL REFERENCES characters(id),
    action      TEXT    NOT NULL,   -- 'lockpick', 'force', 'theft'
    success     INTEGER NOT NULL DEFAULT 0,
    details     TEXT    DEFAULT '',
    timestamp   REAL    NOT NULL
);
"""

# Difficulty constants (from design doc §6)
LOCKPICK_DIFFICULTY = {
    "secured":   999,   # impossible
    "contested": 25,    # Very Difficult
    "lawless":   20,    # Difficult
}
FORCE_DIFFICULTY = {
    "secured":   999,
    "contested": 999,   # can't force in contested — need pick
    "lawless":   15,    # Moderate Strength check
}
THEFT_DIFFICULTY = {
    "contested": 30,    # Heroic combined check
    "lawless":   15,    # Moderate Sneak
}
THEFT_STORAGE_DIFFICULTY = 30   # Very Difficult Security+Slicing for storage locker


async def ensure_intrusion_schema(db) -> None:
    """Create housing_intrusions table if absent. Idempotent."""
    try:
        await db.execute(HOUSING_INTRUSIONS_SQL.strip())
        await db.commit()
    except Exception as e:
        log.warning("[housing] intrusion schema error: %s", e)


async def get_housing_for_private_room(db, room_id: int) -> Optional[dict]:
    """
    Return the housing record that owns this room as a PRIVATE room, or None.
    A shopfront shop room is public and returns None.
    Used by MoveCommand to gate entry to private housing rooms.
    """
    try:
        room = await db.get_room(room_id)
        if not room:
            return None
        # Check room properties for private flag
        props_raw = room.get("properties", "{}")
        try:
            props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        except Exception:
            props = {}
        if not props.get("private"):
            return None
        # It's private — find the housing record
        housing_id = room.get("housing_id")
        if housing_id:
            return await get_housing_by_id(db, housing_id)
        # Fallback: search by room_ids JSON
        rows = await db.fetchall(
            "SELECT * FROM player_housing WHERE room_ids LIKE ?",
            (f"%{room_id}%",),
        )
        for r in rows:
            rids = json.loads(r["room_ids"]) if isinstance(r["room_ids"], str) else (r["room_ids"] or [])
            if room_id in rids:
                return dict(r)
        return None
    except Exception:
        log.warning("get_housing_for_private_room: unhandled exception", exc_info=True)
        return None


def is_on_guest_list(h: dict, char_id: int) -> bool:
    """Check if a character is on a housing record's guest list."""
    guests = _guest_list(h)
    return char_id in guests


async def can_enter_housing_room(db, char: dict, room_id: int) -> tuple[bool, str]:
    """
    Check if a character can enter a private housing room.
    Returns (allowed: bool, reason: str).
    Shopfront shop rooms (public) always return (True, "").
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return True, ""   # not a private housing room

    char_id = char.get("id")
    # Owner always allowed
    if h["char_id"] == char_id:
        return True, ""
    # Admin/builder always allowed
    if char.get("is_admin") or char.get("is_builder"):
        return True, ""
    # Guest list
    if is_on_guest_list(h, char_id):
        return True, ""

    return False, "The door is locked."


async def _log_intrusion(db, housing_id: int, intruder_id: int,
                          action: str, success: bool, details: str = "") -> None:
    """Record an intrusion attempt to the housing_intrusions table."""
    try:
        now = time.time()
        await db.execute(
            """INSERT INTO housing_intrusions
               (housing_id, intruder_id, action, success, details, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (housing_id, intruder_id, action, 1 if success else 0, details[:200], now),
        )
        await db.commit()
    except Exception as e:
        log.warning("[housing] intrusion log error: %s", e)


async def _notify_owner(db, session_mgr, h: dict, msg: str) -> None:
    """Alert the housing owner if they are online."""
    try:
        owner_id = h["char_id"]
        for sess in session_mgr.all:
            if sess.is_in_game and sess.character and sess.character.get("id") == owner_id:
                await sess.send_line(msg)
    except Exception:
        log.warning("_notify_owner: unhandled exception", exc_info=True)
        pass


async def attempt_lockpick(db, char: dict, room_id: int,
                            session_mgr=None) -> dict:
    """
    Attempt to pick the lock on a private housing room door.
    Uses Security skill. All rolls through perform_skill_check().
    Returns {\"ok\": bool, \"msg\": str, \"entered\": bool}.
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return {"ok": False, "msg": "There's no locked door here to pick.", "entered": False}

    if h["char_id"] == char.get("id"):
        return {"ok": False, "msg": "It's your own door.", "entered": False}

    # Get zone security
    entry_room = await db.get_room(h["entry_room_id"])
    try:
        props_raw = entry_room.get("properties", "{}") if entry_room else "{}"
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        zone_sec = props.get("security", "contested")
    except Exception:
        zone_sec = "contested"

    difficulty = LOCKPICK_DIFFICULTY.get(zone_sec, 999)
    if difficulty >= 999:
        return {"ok": False,
                "msg": "Imperial security seals on this door cannot be picked.",
                "entered": False}

    # Skill check via perform_skill_check()
    from engine.skill_checks import perform_skill_check
    result = perform_skill_check(char, "security", difficulty)

    success = result.success
    margin  = result.margin
    fumble  = result.fumble

    await _log_intrusion(db, h["id"], char["id"], "lockpick", success,
                          f"roll={result.roll} diff={difficulty} zone={zone_sec}")

    if fumble:
        msg = (f"  \033[1;31m[LOCKPICK]\033[0m Critical failure! "
               f"Your pick breaks in the lock. The owner has been alerted.\n"
               f"  Security: {result.pool_str} → {result.roll} vs {difficulty}")
        if session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;31m[SECURITY ALERT]\033[0m Someone attempted "
                                 f"to break into your home and fumbled — the lock is jammed.")
        return {"ok": False, "msg": msg, "entered": False}

    if success:
        flavor = "with ease" if margin >= 10 else "after careful work"
        msg = (f"  \033[1;32m[LOCKPICK]\033[0m You bypass the lock {flavor}.\n"
               f"  Security: {result.pool_str} → {result.roll} vs {difficulty}")
        if session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;33m[SECURITY ALERT]\033[0m Someone has picked "
                                 f"the lock to your home!")
        return {"ok": True, "msg": msg, "entered": True}
    else:
        # Failed but not fumble — alert only if margin is terrible (≤ −10)
        msg = (f"  \033[1;31m[LOCKPICK]\033[0m The lock doesn't give. "
               f"({result.pool_str} → {result.roll} vs {difficulty})")
        if margin <= -10 and session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[2m[SECURITY]\033[0m Something rattled your door lock.")
        return {"ok": False, "msg": msg, "entered": False}


async def attempt_force_door(db, char: dict, room_id: int,
                              session_mgr=None) -> dict:
    """
    Attempt to force a housing door with Strength.
    Only possible in lawless zones. Very loud — always alerts owner.
    Returns {\"ok\": bool, \"msg\": str, \"entered\": bool}.
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return {"ok": False, "msg": "There's no door to force here.", "entered": False}

    if h["char_id"] == char.get("id"):
        return {"ok": False, "msg": "You don't need to break down your own door.", "entered": False}

    entry_room = await db.get_room(h["entry_room_id"])
    try:
        props_raw = entry_room.get("properties", "{}") if entry_room else "{}"
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        zone_sec = props.get("security", "contested")
    except Exception:
        zone_sec = "contested"

    difficulty = FORCE_DIFFICULTY.get(zone_sec, 999)
    if difficulty >= 999:
        return {"ok": False,
                "msg": "The door is reinforced. Forcing it isn't an option here.",
                "entered": False}

    from engine.skill_checks import perform_skill_check
    result = perform_skill_check(char, "brawling", difficulty)

    success = result.success
    await _log_intrusion(db, h["id"], char["id"], "force", success,
                          f"roll={result.roll} diff={difficulty}")

    # Always alert owner for forced entry — it's loud
    if session_mgr:
        if success:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;31m[BREAK-IN]\033[0m Someone has forced the door "
                                 f"to your home!")
        else:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;33m[SECURITY ALERT]\033[0m Someone is trying to "
                                 f"force your door!")

    if success:
        msg = (f"  \033[1;31m[FORCE]\033[0m You wrench the door open with brute force.\n"
               f"  Strength: {result.pool_str} → {result.roll} vs {difficulty}")
        return {"ok": True, "msg": msg, "entered": True}
    else:
        msg = (f"  \033[1;31m[FORCE]\033[0m The door holds. "
               f"({result.pool_str} → {result.roll} vs {difficulty})")
        return {"ok": False, "msg": msg, "entered": False}


async def attempt_theft(db, char: dict, room_id: int,
                         target_item: str, session_mgr=None) -> dict:
    """
    Attempt to steal an item from the main room of occupied housing.
    Storage lockers require a separate, harder check.
    Returns {\"ok\": bool, \"msg\": str, \"item\": dict|None}.
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return {"ok": False, "msg": "Nothing to steal here.", "item": None}

    if h["char_id"] == char.get("id"):
        return {"ok": False, "msg": "You can't steal from yourself.", "item": None}

    entry_room = await db.get_room(h["entry_room_id"])
    try:
        props_raw = entry_room.get("properties", "{}") if entry_room else "{}"
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        zone_sec = props.get("security", "contested")
    except Exception:
        zone_sec = "contested"

    if zone_sec == "secured":
        return {"ok": False,
                "msg": "Imperial surveillance makes theft impossible here.", "item": None}

    difficulty = THEFT_DIFFICULTY.get(zone_sec, 999)
    if difficulty >= 999:
        return {"ok": False, "msg": "You can't steal here.", "item": None}

    # For contested zones: combined Sneak+Security average (use Sneak as primary)
    # For lawless zones: Sneak only
    from engine.skill_checks import perform_skill_check
    if zone_sec == "contested":
        sneak_r = perform_skill_check(char, "sneak",    difficulty)
        sec_r   = perform_skill_check(char, "security", difficulty)
        # Average margin — both must succeed
        success = sneak_r.success and sec_r.success
        roll_str = (f"Sneak {sneak_r.pool_str}→{sneak_r.roll}, "
                    f"Security {sec_r.pool_str}→{sec_r.roll} vs {difficulty}")
        fumble = sneak_r.fumble or sec_r.fumble
    else:
        sneak_r = perform_skill_check(char, "sneak", difficulty)
        success = sneak_r.success
        roll_str = f"Sneak {sneak_r.pool_str}→{sneak_r.roll} vs {difficulty}"
        fumble = sneak_r.fumble

    # Find the item in trophies (room display)
    trophies = _trophies(h)
    target_trophy = None
    target_idx = -1
    for i, t in enumerate(trophies):
        if target_item.lower() in t.get("name", "").lower():
            target_trophy = t
            target_idx = i
            break

    if target_trophy is None:
        return {"ok": False,
                "msg": f"You don't see '{target_item}' to steal here.", "item": None}

    await _log_intrusion(db, h["id"], char["id"], "theft", success,
                          f"item={target_item} roll={roll_str}")

    if fumble:
        if session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;31m[INTRUDER ALERT]\033[0m Someone botched a theft "
                                 f"attempt in your home!")
        msg = (f"  \033[1;31m[THEFT FAILED]\033[0m You fumble noisily — the owner will know.\n"
               f"  {roll_str}")
        return {"ok": False, "msg": msg, "item": None}

    if not success:
        msg = f"  \033[1;31m[THEFT FAILED]\033[0m You can't get away with it unseen.\n  {roll_str}"
        if zone_sec == "contested" and session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[2m[SECURITY]\033[0m Something feels disturbed in your home.")
        return {"ok": False, "msg": msg, "item": None}

    # Success — remove from trophies, give to thief
    trophies.pop(target_idx)
    await db.execute(
        "UPDATE player_housing SET trophies = ?, last_activity = ? WHERE id = ?",
        (json.dumps(trophies), time.time(), h["id"]),
    )
    # Add to thief inventory
    inv_raw = char.get("inventory", "{}")
    try:
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
    except Exception:
        inv = {}
    inv.setdefault("items", []).append(target_trophy)
    await db.update_character(char["id"], inventory=json.dumps(inv))
    await db.commit()

    if session_mgr:
        await _notify_owner(db, session_mgr, h,
                             f"\033[1;31m[THEFT ALERT]\033[0m "
                             f"{target_trophy.get('name', 'an item')} has been stolen from your home!")

    msg = (f"  \033[1;32m[THEFT SUCCEEDED]\033[0m You pocket "
           f"{target_trophy.get('name', 'the item')} unseen.\n  {roll_str}")
    return {"ok": True, "msg": msg, "item": target_trophy}


async def get_intrusion_log(db, char: dict) -> list[str]:
    """Return formatted intrusion log for the character's housing."""
    char_id = char.get("id")
    h = await get_housing(db, char_id)
    if not h:
        return ["  You don't have housing."]

    try:
        rows = await db.fetchall(
            """SELECT hi.*, c.name as intruder_name
               FROM housing_intrusions hi
               LEFT JOIN characters c ON c.id = hi.intruder_id
               WHERE hi.housing_id = ?
               ORDER BY hi.timestamp DESC LIMIT 20""",
            (h["id"],),
        )
    except Exception:
        log.warning("intrusion log query failed", exc_info=True)
        return ["  Intrusion log unavailable."]

    if not rows:
        return [
            "\033[1;37m── Intrusion Log ──\033[0m",
            "  No intrusion attempts recorded.",
        ]

    import datetime
    lines = ["\033[1;37m── Intrusion Log ──\033[0m"]
    action_labels = {
        "lockpick": "\033[1;33mLOCKPICK\033[0m",
        "force":    "\033[1;31mFORCE   \033[0m",
        "theft":    "\033[1;31mTHEFT   \033[0m",
    }
    for r in rows:
        ts = datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%m/%d %H:%M")
        outcome = "\033[1;32mSUCCESS\033[0m" if r["success"] else "\033[2mFAILED \033[0m"
        action_str = action_labels.get(r["action"], r["action"].upper())
        intruder = r["intruder_name"] or f"Unknown (#{r['intruder_id']})"
        lines.append(f"  {ts}  {action_str}  {outcome}  {intruder:<20}  \033[2m{r['details'][:50]}\033[0m")

    return lines


# ══════════════════════════════════════════════════════════════════════════════
# DROP 6: Organization Headquarters (Tier 5)
# ══════════════════════════════════════════════════════════════════════════════
"""
Tier 5 HQs: multi-room complex owned by an organization, purchased from org
treasury by the leader.  Members can enter freely; non-members are blocked.

Architecture: reuses player_housing table with tier=5, housing_type='org_hq',
faction_code=<org_code>.  HQ metadata stored in guest_list column (JSON).
"""

TIER5_TYPES = {
    "outpost": {
        "label": "Small Outpost", "total_rooms": 4, "cost": 50_000,
        "weekly_maint": 500, "storage_max": 100, "guard_slots": 2,
        "room_plan": [
            ("entrance", "Entrance Hall"), ("meeting", "Meeting Room"),
            ("armory", "Armory"), ("barracks", "Barracks"),
        ],
    },
    "chapter_house": {
        "label": "Chapter House", "total_rooms": 6, "cost": 100_000,
        "weekly_maint": 1_000, "storage_max": 200, "guard_slots": 4,
        "room_plan": [
            ("entrance", "Entrance Hall"), ("meeting", "Meeting Room"),
            ("armory", "Armory"), ("barracks", "Barracks"),
            ("comm", "Comm Center"), ("quarters", "Officer Quarters"),
        ],
    },
    "fortress": {
        "label": "Fortress", "total_rooms": 9, "cost": 150_000,
        "weekly_maint": 1_500, "storage_max": 400, "guard_slots": 6,
        "room_plan": [
            ("entrance", "Entrance Hall"), ("meeting", "War Room"),
            ("armory", "Armory"), ("barracks", "Barracks"),
            ("barracks2", "Crew Quarters"), ("comm", "Comm Center"),
            ("quarters", "Commander's Suite"), ("cell", "Holding Cell"),
            ("hangar", "Hangar Access"),
        ],
    },
}

# F.5b.3.c (Apr 30 2026): HOUSING_LOTS_TIER5 deleted. T5 lot inventory
# is now sourced from data/worlds/<era>/housing_lots.yaml::tier5_lots
# via engine/housing_lots_provider.get_tier5_lots().

_TIER5_ROOM_DESCS = {
    "empire": {
        "entrance": ("Imperial Outpost — Entry",
            "A reinforced blast door opens into a stark, well-lit entry hall. The Imperial "
            "insignia is painted on the far wall. Security cameras track every corner."),
        "meeting":  ("Briefing Room",
            "A circular table with a holographic projector dominates this windowless room. "
            "Star charts and tactical overlays glow on the walls."),
        "armory":   ("Imperial Armory",
            "Racks of blaster rifles in regulation rows. A locked durasteel cage holds "
            "heavier ordnance. The air smells of weapon lubricant and ozone."),
        "barracks": ("Garrison Barracks",
            "Double-stacked bunks in regulation configuration with sealed footlockers. "
            "Everything is spotlessly clean."),
        "barracks2":("Personnel Quarters",
            "Individual sleeping compartments. A shared common area has a holotable "
            "and beverage dispenser."),
        "comm":     ("Communications Station",
            "Banks of encrypted military-band transceivers, a subspace relay, and "
            "monitoring screens showing local sensor feeds."),
        "quarters": ("Commander's Quarters",
            "A spacious private suite. Proper bed, secure holoterminal, weapons rack, "
            "and viewport. Dual-lock door — code and biometric."),
        "cell":     ("Detention Block",
            "A reinforced cell with a ray-shielded door. Metal slab bench. "
            "Surveillance cameras cover every angle."),
        "hangar":   ("Vehicle Bay",
            "A cavernous bay with durasteel floor plating scored by repulsor wash. "
            "Maintenance gantries line the walls."),
    },
    "rebel": {
        "entrance": ("Rebel Safehouse — Entry",
            "A concealed entrance into a cramped, dimly-lit foyer. A handwritten sign "
            "reads 'HOPE.' Someone has added 'and blasters.'"),
        "meeting":  ("Command Center",
            "A makeshift war room with a salvaged holotable displaying Alliance-coded "
            "star maps. Mismatched chairs. The air is thick with caf."),
        "armory":   ("Supply Cache",
            "Weapons in crates, wall racks, even a hollowed-out cargo pod. Nothing "
            "matches, but everything works."),
        "barracks": ("Rebel Quarters",
            "Bunks and hammocks wherever space permits. It's cramped, messy, and "
            "feels like home."),
        "barracks2":("Crew Bunks",
            "A secondary sleeping area. Someone hung a Rebel Alliance banner on the "
            "wall. A repair droid trundles between the bunks."),
        "comm":     ("Comm Shack",
            "Jury-rigged from salvaged components. Despite appearances, the "
            "encryption is military-grade. Cold caf on the console."),
        "quarters": ("Cell Leader's Room",
            "The only private room. A cot, datapads, and a locked strongbox. A "
            "blaster hangs within arm's reach of the pillow."),
        "cell":     ("Secure Room",
            "Reinforced room — brig or panic room. Door locks from both sides."),
        "hangar":   ("Hidden Dock",
            "Camouflaged landing pad. Room for a small freighter. Fuel drums and "
            "spare parts fill the corners."),
    },
    "hutt": {
        "entrance": ("Hutt Stronghold — Entry",
            "An opulent entryway designed to intimidate. Heavy curtains, garish "
            "trophies, and two guard alcoves flanking the door."),
        "meeting":  ("Audience Chamber",
            "A lavish chamber with a raised dais. Plush cushions, hookah pipes, "
            "and a sunken pit for 'entertainment.' Sound-dampened walls."),
        "armory":   ("Weapons Vault",
            "Reinforced vault crammed with weapons. Everything has a price tag — "
            "the Hutts never give anything away."),
        "barracks": ("Enforcers' Den",
            "Rough dormitory for cartel muscle. Bunks with weapon racks underneath. "
            "A sabacc table occupies the center."),
        "barracks2":("Crew Quarters",
            "Actual mattresses and personal lockers. Reserved for trusted operatives."),
        "comm":     ("Operations Center",
            "Surprisingly sophisticated. Encrypted channels, slicing terminals, and "
            "a live feed of local law enforcement comms."),
        "quarters": ("Boss's Suite",
            "Obscenely luxurious. Massive bed, private refresher with actual water, "
            "and a safe the size of a speeder."),
        "cell":     ("Prisoner Cell",
            "Bare cell. Chains bolted to the wall. A drain in the floor."),
        "hangar":   ("Smuggling Bay",
            "Concealed loading dock with hidden compartments and false walls."),
    },
    # ── B.1.d.1 (Apr 29 2026) — CW org-HQ room descriptions ──────────────────────────
    # Per architecture v38 §19 territory-control: any org with an HQ
    # gets per-room flavor when built. Adds 5 CW factions; falls
    # through to "default" for any unmapped code.
    "republic": {
        "entrance": ("Republic Forward Compound — Entry",
            "A reinforced compound entry with a wide blast door. The Republic "
            "crest is set into the lintel above. Two clone trooper sentries "
            "flank the entry, weapons holstered but visibly ready."),
        "meeting":  ("Strategy Hall",
            "A wide round room with a holotable in the center, ringed by "
            "tactical screens showing the current Republic order of battle. "
            "The Republic crest is stenciled on the floor."),
        "armory":   ("Republic Armory",
            "Racks of DC-15A blaster rifles and ordered crates of supplies. "
            "A locked vault holds heavy weapons. Inventory is logged on a "
            "datapad mounted to the wall."),
        "barracks": ("Trooper Barracks",
            "Identical bunks in regulation rows. Lockers stenciled with rank "
            "and serial number. The barracks smells of clean kit and gun oil."),
        "barracks2":("Officer Quarters",
            "Smaller two-bunk rooms reserved for non-clone officers and "
            "specialists. A shared common area has a holotable and a caf urn "
            "that is never empty."),
        "comm":     ("Comms Station",
            "Encrypted Republic-band transceivers and a subspace relay tied "
            "into the Coruscant command net. Live sensor feeds tile every "
            "available wall."),
        "quarters": ("Commander's Quarters",
            "A private suite for the compound's commanding officer. A proper "
            "bed, a secure terminal, a weapons rack, and a viewport. The "
            "door takes a code and a biometric."),
        "cell":     ("Holding Block",
            "A small detention cell with a ray-shielded door. A metal slab "
            "bench. Surveillance cameras cover every angle."),
        "hangar":   ("Vehicle Bay",
            "A wide repulsorlift bay scored by recent traffic. A LAAT/i "
            "gunship sits on the pad, technicians swarming over its engines."),
    },
    "cis": {
        "entrance": ("Separatist Outpost — Entry",
            "A camouflaged entry concealed against the surrounding architecture. "
            "The Confederacy hex is painted small and weathered above the door. "
            "A B1 battle droid stands sentry, its photoreceptors tracking new arrivals."),
        "meeting":  ("Cell Planning Room",
            "A windowless chamber with a battered holotable and mismatched chairs. "
            "Star maps marked with Republic supply lines cover one wall. The air "
            "smells faintly of droid lubricant."),
        "armory":   ("Cell Armory",
            "Crates of E-5 blasters and battle-droid parts stacked along one wall. "
            "Anything that needs a permit, the cartel got via Geonosian foundries."),
        "barracks": ("Operatives' Bunkroom",
            "Spartan bunks for Separatist operatives between missions. Personal "
            "kit is stowed in lockers stenciled with cell-internal callsigns, "
            "never real names."),
        "barracks2":("Sympathizer Quarters",
            "A smaller dormitory for civilian sympathizers and visiting agents. "
            "Less spartan; reading material from Confederacy presses fills a shelf."),
        "comm":     ("Encrypted Comms",
            "A hardened transceiver suite with rotating frequency hops. The "
            "encryption is good enough to make Republic Intelligence work for "
            "every intercept."),
        "quarters": ("Cell Leader's Room",
            "The only private room. A cot, datapads, a locked strongbox, and "
            "a secondary blaster within arm's reach of the bed. The walls carry "
            "no insignia — the cell leader's identity stays compartmented."),
        "cell":     ("Holding Cell",
            "A reinforced room. Captured Republic personnel get one chance at "
            "talking before being moved deeper into Separatist territory."),
        "hangar":   ("Concealed Bay",
            "A camouflaged landing pad. Room for a small freighter and a B2 "
            "battle droid honor guard. Fuel cells and droid parts fill the corners."),
    },
    "jedi_order": {
        "entrance": ("Temple Annex — Entry",
            "A quiet stone-flagged hall lit by sconces of carved kyber. The "
            "Jedi crest is inlaid into the floor — not displayed loudly, just "
            "present. The air feels slower here."),
        "meeting":  ("Council Chamber",
            "A circular chamber with curved benches in carved wood, surrounding "
            "a meditation focus on a low plinth. No holographic displays — "
            "discussions here are deliberate, unrushed."),
        "armory":   ("Practice Salle",
            "Less an armory than a training hall. Practice droids stand in "
            "alcoves; training sabers hang on a rack. The Jedi Order does "
            "not stockpile weapons. A few rare lightsaber crystals rest in a "
            "shielded case."),
        "barracks": ("Padawan Wing",
            "A long hall of small private cells where Padawans sleep beside "
            "their Masters' rooms. The hall is quiet at all hours; Jedi rest "
            "lightly."),
        "barracks2":("Initiate Cluster",
            "A communal dormitory for Initiates not yet selected as Padawans. "
            "Robed children and youths move through quietly, carrying datapads "
            "and meditation cushions."),
        "comm":     ("Communications Sanctum",
            "A small chamber with a single secure subspace relay tied to the "
            "Coruscant Temple. The Jedi Order does not flood the airwaves; "
            "what is sent from here matters."),
        "quarters": ("Master's Chamber",
            "A modest private chamber for the senior Jedi in residence. A "
            "meditation mat, a writing desk, a bed, and one small shelf of "
            "personal mementos. The lightsaber rack is empty whenever the "
            "owner is in residence."),
        "cell":     ("Reflection Room",
            "A quiet shielded room used for prisoner interview or for "
            "Jedi-internal contemplation in the wake of difficult decisions. "
            "Force-dampening crystals are set into the walls."),
        "hangar":   ("Starfighter Bay",
            "A small bay holding two or three Delta-7 Aethersprite Jedi "
            "starfighters and their astromech docking stations."),
    },
    "hutt_cartel": {
        # Identical to GCW hutt per CW design §5.4 ("Identical to GCW").
        "entrance": ("Hutt Stronghold — Entry",
            "An opulent entryway designed to intimidate. Heavy curtains, garish "
            "trophies, and two guard alcoves flanking the door."),
        "meeting":  ("Audience Chamber",
            "A lavish chamber with a raised dais. Plush cushions, hookah pipes, "
            "and a sunken pit for 'entertainment.' Sound-dampened walls."),
        "armory":   ("Weapons Vault",
            "Reinforced vault crammed with weapons. Everything has a price tag — "
            "the Hutts never give anything away."),
        "barracks": ("Enforcers' Den",
            "Rough dormitory for cartel muscle. Bunks with weapon racks underneath. "
            "A sabacc table occupies the center."),
        "barracks2":("Crew Quarters",
            "Actual mattresses and personal lockers. Reserved for trusted operatives."),
        "comm":     ("Operations Center",
            "Surprisingly sophisticated. Encrypted channels, slicing terminals, and "
            "a live feed of local law enforcement comms."),
        "quarters": ("Boss's Suite",
            "Obscenely luxurious. Massive bed, private refresher with actual water, "
            "and a safe the size of a speeder."),
        "cell":     ("Prisoner Cell",
            "Bare cell. Chains bolted to the wall. A drain in the floor."),
        "hangar":   ("Smuggling Bay",
            "Concealed loading dock with hidden compartments and false walls."),
    },
    "bounty_hunters_guild": {
        "entrance": ("Guild Chapter House — Entry",
            "A sturdy unadorned entry with a single Guild sigil etched into the "
            "stone above the door. A bounty board hangs in the foyer, its "
            "postings updated nightly."),
        "meeting":  ("Contract Hall",
            "A long room dominated by a central table where contract details are "
            "negotiated. Holos of current high-priority marks rotate above "
            "the table. Guild members come and go without ceremony."),
        "armory":   ("Hunter's Armory",
            "Personal weapons lockers line the walls. Members store gear they "
            "don't want to carry on a particular hunt — and trust the Guild's "
            "reputation to keep their lockers untouched."),
        "barracks": ("Bunkroom",
            "Plain bunks for visiting Guild members between contracts. No "
            "long-term occupancy; rotation by Guild rank."),
        "barracks2":("Senior Quarters",
            "Slightly nicer bunks for Senior Hunter and above. Each has a "
            "personal locker and a small privacy curtain."),
        "comm":     ("Bounty Board Office",
            "The encrypted core of the chapter house's operations — the secure "
            "feed from Guild central, the contract verification terminals, and "
            "the bounty payout cashier."),
        "quarters": ("Guildmaster's Office",
            "The chapter Guildmaster's office and quarters in one — desk, bed, "
            "and a bank of monitors showing every active hunt the chapter is "
            "running. The Guildmaster sleeps when the work is done."),
        "cell":     ("Holding Pen",
            "A hardened cell where live bounties await transport. Stun-grid "
            "floor, no sharp edges, ray-shielded door."),
        "hangar":   ("Tracker Bay",
            "A bay holding two or three Guild speeder bikes and a small "
            "transport for moving live captures."),
    },
    "default": {
        "entrance": ("Headquarters — Entry", "The entrance to the headquarters."),
        "meeting":  ("Meeting Room", "A conference room with a table and holodisplay."),
        "armory":   ("Armory", "Secure room for weapons and equipment storage."),
        "barracks": ("Barracks", "Shared sleeping quarters with bunks."),
        "barracks2":("Crew Quarters", "Additional sleeping quarters for members."),
        "comm":     ("Communications Room", "Communications equipment and consoles."),
        "quarters": ("Leader's Quarters", "Private quarters for the leader."),
        "cell":     ("Holding Room", "A reinforced room with a locking door."),
        "hangar":   ("Vehicle Storage", "A bay for vehicles and equipment."),
    },
}


def _get_hq_room_desc(org_code: str, room_key: str) -> tuple[str, str]:
    """Return (name, description) for an HQ room, themed per faction."""
    descs = _TIER5_ROOM_DESCS.get(org_code, _TIER5_ROOM_DESCS["default"])
    entry = descs.get(room_key, _TIER5_ROOM_DESCS["default"].get(room_key))
    if entry:
        return entry
    return (room_key.replace("_", " ").title(), "A room in the headquarters.")


async def get_org_hq(db, org_code: str) -> Optional[dict]:
    """Find the HQ housing record for an organization, or None."""
    rows = await db.fetchall(
        "SELECT * FROM player_housing WHERE housing_type = 'org_hq' AND faction_code = ? "
        "ORDER BY id DESC LIMIT 1", (org_code,))
    return dict(rows[0]) if rows else None


async def purchase_hq(db, char: dict, org_code: str, hq_type: str,
                       lot_id: int) -> dict:
    """Purchase a Tier 5 Organization HQ from org treasury."""
    cfg = TIER5_TYPES.get(hq_type)
    if not cfg:
        types_str = ", ".join(f"'{k}' ({v['label']}, {v['cost']:,}cr)"
                              for k, v in TIER5_TYPES.items())
        return {"ok": False, "msg": f"Unknown HQ type. Options: {types_str}"}

    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": f"Organization '{org_code}' not found."}
    if org.get("leader_id") and org["leader_id"] != char["id"]:
        return {"ok": False, "msg": "Only the organization leader can purchase an HQ."}

    existing = await get_org_hq(db, org_code)
    if existing:
        return {"ok": False, "msg": "Your org already has an HQ. Sell it first."}

    treasury = org.get("treasury", 0)
    if treasury < cfg["cost"]:
        return {"ok": False, "msg": (
            f"{cfg['label']} costs {cfg['cost']:,}cr. Treasury: {treasury:,}cr.")}

    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": f"Invalid lot ID '{lot_id}'."}
    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full."}

    entry_room_id = lot["room_id"]
    entry_room = await db.get_room(entry_room_id)
    if not entry_room:
        return {"ok": False, "msg": "Lot room not found."}

    entry_security = "contested"
    try:
        props = json.loads(entry_room.get("properties", "{}") or "{}")
        entry_security = props.get("security", "contested")
    except Exception as _e:
        log.debug("silent except in engine/housing.py:2898: %s", _e, exc_info=True)

    org_name = org.get("name", org_code.title())

    # Create rooms
    room_ids = []
    room_plan = cfg["room_plan"]
    for room_key, _label in room_plan:
        r_name, r_desc = _get_hq_room_desc(org_code, room_key)
        room_props = {"security": entry_security, "private": True,
                      "org_hq": True, "org_code": org_code, "hq_room_type": room_key}
        if room_key == "armory":
            room_props["is_armory"] = True
        rid = await db.create_room(
            name=f"{org_name} — {r_name}", desc_short=r_desc, desc_long=r_desc,
            zone_id=None, properties=json.dumps(room_props))
        room_ids.append(rid)

    # Link: entry → entrance, then hub-and-spoke from entrance
    door_dir = await _pick_door_direction(db, entry_room_id)
    exit_in_id = await db.create_exit(
        entry_room_id, room_ids[0], door_dir, f"{org_name} HQ")
    exit_out_id = await db.create_exit(
        room_ids[0], entry_room_id, "out", entry_room.get("name", "Exit"))
    for i in range(1, len(room_ids)):
        r_name, _ = _get_hq_room_desc(org_code, room_plan[i][0])
        inner_dir = _HOUSING_DIRS[i % len(_HOUSING_DIRS)]
        await db.create_exit(room_ids[0], room_ids[i], inner_dir, r_name)
        await db.create_exit(room_ids[i], room_ids[0], "out", "Entrance Hall")

    new_treasury = await db.adjust_org_treasury(org["id"], -cfg["cost"])

    now = time.time()
    hq_meta = json.dumps({"guard_slots": cfg["guard_slots"],
                           "guard_npcs": [], "maint_overdue": 0})
    cursor = await db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, purchase_price,
            rent_paid_until, door_direction,
            exit_id_in, exit_id_out, faction_code, guest_list,
            created_at, last_activity)
           VALUES (?, 5, 'org_hq', ?, ?, '[]', ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (char["id"], entry_room_id, json.dumps(room_ids), cfg["storage_max"],
         cfg["weekly_maint"], cfg["cost"],
         now + RENT_TICK_INTERVAL, door_dir,
         exit_in_id, exit_out_id, org_code, hq_meta, now, now))
    housing_id = cursor.lastrowid

    for rid in room_ids:
        await db.execute("UPDATE rooms SET housing_id = ? WHERE id = ?",
                             (housing_id, rid))
    await db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,))
    await db.execute(
        "UPDATE organizations SET hq_room_id = ? WHERE id = ?",
        (room_ids[0], org["id"]))
    await db.commit()

    log.info("[housing] org %s purchased %s HQ at lot %d, rooms %s",
             org_code, hq_type, lot_id, room_ids)
    return {
        "ok": True,
        "msg": (f"Established: {org_name} {cfg['label']} at {lot['label']}! "
                f"Cost: {cfg['cost']:,}cr (treasury: {new_treasury:,}cr). "
                f"{cfg['total_rooms']} rooms, {cfg['guard_slots']} guard slots. "
                f"Enter: {door_dir} from {entry_room.get('name', 'lobby')}."),
        "housing_id": housing_id, "room_ids": room_ids, "direction": door_dir,
    }


async def sell_hq(db, char: dict, org_code: str) -> dict:
    """Sell/disband org HQ.  25% refund to treasury.  Leader only."""
    org = await db.get_organization(org_code)
    if not org:
        return {"ok": False, "msg": f"Organization '{org_code}' not found."}
    if org.get("leader_id") and org["leader_id"] != char["id"]:
        return {"ok": False, "msg": "Only the leader can sell the HQ."}
    h = await get_org_hq(db, org_code)
    if not h:
        return {"ok": False, "msg": "Your org doesn't have an HQ."}

    # Return storage to armory
    storage = _storage(h)
    if storage:
        try:
            from engine.territory import _get_armory, _save_armory
            armory = await _get_armory(db, org_code)
            armory.extend(storage)
            await _save_armory(db, org_code, armory)
        except Exception:
            log.warning("[housing] HQ sell: armory return failed", exc_info=True)

    # Remove guards + delete rooms
    room_ids = _room_ids(h)
    for rid in room_ids:
        try:
            from engine.territory import remove_guard_npc
            await remove_guard_npc(db, org_code, rid, force=True)
        except Exception as _e:
            log.debug("silent except in engine/housing.py:2999: %s", _e, exc_info=True)
        await db.delete_room(rid)

    await db.execute("DELETE FROM player_housing WHERE id = ?", (h["id"],))
    await db.execute(
        "UPDATE housing_lots SET current_homes = MAX(0, current_homes - 1) "
        "WHERE room_id = ?", (h["entry_room_id"],))
    await db.execute(
        "UPDATE organizations SET hq_room_id = NULL WHERE id = ?", (org["id"],))

    refund = h.get("purchase_price", 0) // 4
    new_treasury = await db.adjust_org_treasury(org["id"], refund)
    await db.commit()

    org_name = org.get("name", org_code.title())
    log.info("[housing] org %s sold HQ (refund %d)", org_code, refund)
    return {"ok": True, "msg": (
        f"{org_name} HQ disbanded. Refund: {refund:,}cr (treasury: {new_treasury:,}cr). "
        f"Storage returned to faction armory.")}


async def can_enter_hq_room(db, char: dict, room_id: int) -> tuple[bool, str]:
    """Check if a character can enter an org HQ room.  Members enter freely."""
    room = await db.get_room(room_id)
    if not room:
        return True, ""
    try:
        props = json.loads(room.get("properties", "{}") or "{}")
    except Exception:
        return True, ""
    if not props.get("org_hq"):
        return True, ""
    org_code = props.get("org_code", "")
    if not org_code:
        return True, ""
    org = await db.get_organization(org_code)
    if not org:
        return True, ""
    membership = await db.get_membership(char["id"], org["id"])
    if membership:
        return True, ""
    return False, f"This is {org.get('name', org_code)} territory. Members only."


async def get_hq_status_lines(db, org_code: str) -> list[str]:
    """Format HQ status for 'faction hq' display."""
    h = await get_org_hq(db, org_code)
    org = await db.get_organization(org_code)
    org_name = org.get("name", org_code.title()) if org else org_code.title()
    B, DIM, CYAN = "\033[1m", "\033[2m", "\033[1;36m"
    YELLOW, RED, RESET = "\033[1;33m", "\033[1;31m", "\033[0m"
    w = 60

    if not h:
        return [
            f"{CYAN}{'═' * w}{RESET}", f"  {YELLOW}{org_name} — Headquarters{RESET}",
            f"{CYAN}{'═' * w}{RESET}", f"  {DIM}No headquarters established.{RESET}",
            f"  {DIM}Use 'faction hq purchase <type> <lot>' to establish one.{RESET}",
            f"  {DIM}Types: outpost (50Kcr), chapter_house (100Kcr), fortress (150Kcr){RESET}",
            f"  {DIM}Use 'faction hq locations' to see lots.{RESET}",
            f"{CYAN}{'═' * w}{RESET}",
        ]

    hq_data = {}
    try:
        raw = h.get("guest_list", "{}")
        hq_data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(hq_data, list):
            hq_data = {}
    except Exception as _e:
        log.debug("silent except in engine/housing.py:3069: %s", _e, exc_info=True)

    room_ids = _room_ids(h)
    storage = _storage(h)
    guard_slots = hq_data.get("guard_slots", 2)
    maint_overdue = hq_data.get("maint_overdue", 0)

    type_label = "HQ"
    for _k, v in TIER5_TYPES.items():
        if v["total_rooms"] == len(room_ids):
            type_label = v["label"]
            break

    entry_room = await db.get_room(h["entry_room_id"])
    entry_name = entry_room.get("name", "Unknown") if entry_room else "Unknown"

    lines = [
        f"{CYAN}{'═' * w}{RESET}", f"  {YELLOW}{org_name} — {type_label}{RESET}",
        f"{CYAN}{'─' * w}{RESET}",
        f"  {B}Location:{RESET}    {entry_name} ({h.get('door_direction', '?')})",
        f"  {B}Rooms:{RESET}       {len(room_ids)}",
        f"  {B}Storage:{RESET}     {len(storage)}/{h.get('storage_max', 0)} items",
        f"  {B}Guards:{RESET}      {guard_slots} slots",
        f"  {B}Maintenance:{RESET} {h.get('weekly_rent', 0):,}cr/week",
    ]
    if maint_overdue >= 4:
        lines.append(f"  {RED}{B}STATUS: ABANDONED{RESET}")
    elif maint_overdue >= 2:
        lines.append(f"  {RED}WARNING: Overdue {maint_overdue} weeks — doors unlocked!{RESET}")
    elif maint_overdue == 1:
        lines.append(f"  {YELLOW}Maintenance overdue 1 week{RESET}")
    else:
        treasury = org.get("treasury", 0) if org else 0
        lines.append(f"  {B}Treasury:{RESET}    {treasury:,}cr")

    lines.append(f"{CYAN}{'─' * w}{RESET}")
    lines.append(f"  {YELLOW}Rooms:{RESET}")
    for rid in room_ids:
        rm = await db.get_room(rid)
        lines.append(f"    {DIM}•{RESET} {rm.get('name', f'Room #{rid}') if rm else f'Room #{rid}'}")
    lines.append(f"{CYAN}{'═' * w}{RESET}")
    return lines


async def get_tier5_listing_lines(db, org_code: str) -> list[str]:
    """Show available HQ lots for purchase.

    F.5b.2: era-aware via housing_lots_provider.
    """
    from engine.housing_lots_provider import get_tier5_lots
    B, DIM, CYAN = "\033[1m", "\033[2m", "\033[1;36m"
    YELLOW, GREEN, RESET = "\033[1;33m", "\033[1;32m", "\033[0m"
    lines = [f"{CYAN}{'═' * 60}{RESET}", f"  {YELLOW}Available HQ Locations{RESET}",
             f"{CYAN}{'─' * 60}{RESET}"]
    for room_id, planet, label, security, max_hqs in get_tier5_lots():
        lot_row = await db.fetchall(
            "SELECT current_homes FROM housing_lots WHERE room_id = ?", (room_id,))
        current = lot_row[0]["current_homes"] if lot_row else 0
        avail = max_hqs - current
        sec_c = GREEN if security == "secured" else (YELLOW if security == "contested" else "\033[1;31m")
        lines.append(f"  {B}Lot {room_id}{RESET}  {label}")
        lines.append(f"    {DIM}{planet.replace('_',' ').title()}{RESET}  "
                     f"{sec_c}{security.title()}{RESET}  {DIM}({avail}/{max_hqs} avail){RESET}")
    lines.append(f"{CYAN}{'─' * 60}{RESET}")
    lines.append(f"  {YELLOW}HQ Types:{RESET}")
    for key, cfg in TIER5_TYPES.items():
        lines.append(f"    {B}{key}{RESET}: {cfg['label']} — {cfg['cost']:,}cr, "
                     f"{cfg['total_rooms']} rooms, {cfg['guard_slots']} guards, "
                     f"{cfg['weekly_maint']:,}cr/wk")
    lines.append(f"{CYAN}{'═' * 60}{RESET}")
    lines.append(f"  {DIM}Usage: faction hq purchase <type> <lot_id>{RESET}")
    return lines


async def tick_hq_maintenance(db, session_mgr) -> None:
    """Weekly HQ maintenance.  Degradation: 1wk=guards off, 2wk=doors open, 4wk=abandoned."""
    rows = await db.fetchall(
        "SELECT * FROM player_housing WHERE housing_type = 'org_hq' AND rent_paid_until < ?",
        (time.time(),))
    for row in rows:
        h = dict(row)
        org_code = h.get("faction_code", "")
        if not org_code:
            continue
        org = await db.get_organization(org_code)
        if not org:
            continue
        maint_cost = h.get("weekly_rent", 500)
        treasury = org.get("treasury", 0)
        hq_data = {}
        try:
            raw = h.get("guest_list", "{}")
            hq_data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(hq_data, list):
                hq_data = {}
        except Exception as _e:
            log.debug("silent except in engine/housing.py:3161: %s", _e, exc_info=True)

        if treasury >= maint_cost:
            await db.adjust_org_treasury(org["id"], -maint_cost)
            hq_data["maint_overdue"] = 0
            await db.execute(
                "UPDATE player_housing SET rent_paid_until = ?, guest_list = ? WHERE id = ?",
                (time.time() + RENT_TICK_INTERVAL, json.dumps(hq_data), h["id"]))
            await db.commit()
        else:
            overdue = hq_data.get("maint_overdue", 0) + 1
            hq_data["maint_overdue"] = overdue
            await db.execute(
                "UPDATE player_housing SET rent_paid_until = ?, guest_list = ? WHERE id = ?",
                (time.time() + RENT_TICK_INTERVAL, json.dumps(hq_data), h["id"]))
            await db.commit()
            org_name = org.get("name", org_code.title())
            if overdue >= 4:
                log.info("[housing] HQ for %s abandoned (%d wk overdue)", org_code, overdue)
                try:
                    await db.execute("UPDATE organizations SET leader_id = ? WHERE id = ?",
                                         (h["char_id"], org["id"]))
                    await sell_hq(db, {"id": h["char_id"]}, org_code)
                except Exception:
                    log.warning("[housing] HQ abandonment failed: %s", org_code, exc_info=True)
            elif org.get("leader_id") and session_mgr:
                sess = session_mgr.find_by_character(org["leader_id"])
                if sess:
                    warn = (f"  \033[1;31m[HQ]\033[0m {org_name} HQ overdue {overdue}wk! "
                            f"Doors unlocked. Fund treasury or lose HQ." if overdue >= 2
                            else f"  \033[1;33m[HQ]\033[0m {org_name} HQ maintenance overdue. "
                            f"Guards offline. Cost: {maint_cost:,}cr/wk.")
                    await sess.send_line(warn)
