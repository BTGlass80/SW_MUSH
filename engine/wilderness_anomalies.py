# -*- coding: utf-8 -*-
"""
engine/wilderness_anomalies.py — wilderness anomaly substrate
(SYN.7.a + SYN.7.a.fix, May 25 2026).

Ground-side equivalent of ``engine/space_anomalies.py``: a transient
encounter spawns in a wilderness region for a defined window. Broadcast in
the news channel, listed by the ``anomalies`` command, resolved by
``investigate <id>`` while standing at the anomaly's anchor room.

Tier 1 substrate scope:
  * Module-level transient state keyed by region_slug. Restart wipes.
  * Each region rolls every CADENCE_INTERVAL seconds. The roll respects
    a per-region cap and a SPAWN_CHANCE_PER_TICK probability.
  * Each anomaly has an anchor room (one of the region's landmarks),
    an expiry timestamp, a template_key, and (after fix) a resolution
    mode (``skill`` or ``combat``).
  * Templates are region-tagged. ``regions=["tatooine_dune_sea"]`` only spawns
    in Dune Sea; ``regions=["coruscant_underworld"]`` only in the
    underworld; ``regions=["*"]`` is universal.
  * ``investigate <id>`` resolves the anomaly. ``skill`` templates roll
    one skill check vs DC 13 (one-shot, success → full reward, fail →
    partial). ``combat`` templates spawn real NPCs and award the
    reward when the player kills them (via a hook in
    ``parser/combat_commands.py``).

Influence delta: +5 per design §2.8. The resolver's faction gets
the delta in the region's zone_id. Independent characters get no
influence (no faction to credit).

Cadence: per-region per-tick check. Hourly tick wrapper in
``server/tick_handlers_economy.py``. Per-region 2.5h average cadence
shaped by SPAWN_CHANCE_PER_TICK + tick interval.

─── Templates by region ────────────────────────────────────────────
  Dune Sea (Tatooine):
    stranded_clone_scout   (skill: medicine)
    salvage_cache          (skill: technical)
    wounded_animal         (combat: bantha pack / krayt juvenile)
    tusken_party           (combat: 3 Tusken raiders)
    crashed_cis_probe      (skill: technical)

  Coruscant Underworld:
    black_sun_courier      (combat: 2 Black Sun thugs)
    factory_cache          (skill: technical)
    maze_rogue             (combat: 1 Maze creature — underworld
                            equivalent of wounded_animal)
    cis_sleeper_cell       (combat: 2 B1 droids)
    bounty_hunter_rival    (combat: 1 rival bounty hunter)

─── Combat resolution wiring ───────────────────────────────────────
  When a player runs ``investigate <id>`` on a combat anomaly:
    * The engine spawns N NPCs in the player's room via
      ``db.create_npc``.
    * Each NPC's ``ai_config_json`` gets ``is_anomaly_target: true``
      and ``anomaly_id: <id>``.
    * The anomaly object's ``spawned_npc_ids`` list records them.
    * The player engages with normal ``attack`` flow.
    * When the LAST tagged NPC dies, ``combat_commands._handle_npc_death``
      calls ``award_combat_anomaly_reward(...)`` which fires the
      reward (credits + resources + influence + mark resolved).
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Design §2.8: Tier 1 cadence "every 2-3 hours per region". Midpoint
# is ~150 min = 9000s. Implemented as: hourly tick (3600s) with
# per-region per-tick spawn-chance of 0.4. Expected interval between
# spawns: 3600/0.4 = 9000s = 2.5h. ✓
#
# TUNING: SPAWN_CHANCE_PER_TICK and CADENCE_TICK_INTERVAL together
# define cadence. Logged in tunable_open_questions.
CADENCE_TICK_INTERVAL = 3600                # 1 hour
SPAWN_CHANCE_PER_TICK = 0.4                 # → ~2.5h avg interval

# Per-region cap. Design says "temporary landmarks" plural is fine,
# but we shouldn't let an inactive region accumulate dozens of
# anomalies overnight.
MAX_PER_REGION = 2

# Duration: design §2.8 says ~30 min for Tier 1. Stored as expiry
# timestamp on the Anomaly.
TIER1_DURATION_SECS = 30 * 60               # 30 min

# Reward: design §2.8 says "+5 influence" delta for Tier 1.
TIER1_INFLUENCE_DELTA = 5

# Resolution skill DC. Moderate-Difficult band per WEG R&E ladder.
# Tier 1 anomalies should resolve for a competent character but not
# auto-succeed for a starter.
TIER1_RESOLUTION_DC = 13

# Universal region tag (template spawns in any wilderness region).
REGION_ANY = "*"


# ── Tier 2 constants ─────────────────────────────────────────────────────────
#
# Tier 2 anomalies are rarer, longer, harder, more rewarding.
# Design §2.8: ~2 hour duration; every 24-48 hours per region; +15-25
# influence; 3-5 coordinating players; multi-phase combat.
#
# Implementation:
#   * Separate tick (TIER2_CADENCE_TICK_INTERVAL = 6h) with lower
#     spawn-chance per tick (0.20 → 30h avg ≈ midpoint of 24-48h).
#   * Lower per-region cap (1) — Tier 2 is the headline event in a
#     region; multiple concurrent dilutes the feel.
#   * Longer duration (2h) — players need travel + coordination time.
#   * +20 influence (mid of 15-25 band) per design.
#   * Phase-based combat: each template declares `phases: [...]` with
#     its own combat_npcs per phase. Killing the last hostile of
#     phase N advances to phase N+1 (more NPCs spawn). Killing the
#     last hostile of the FINAL phase fires the reward.
TIER2_CADENCE_TICK_INTERVAL = 6 * 3600         # 6 hours
TIER2_SPAWN_CHANCE_PER_TICK = 0.20             # → ~30h avg interval
TIER2_MAX_PER_REGION = 1                       # 1 concurrent T2 per region
TIER2_DURATION_SECS = 2 * 60 * 60              # 2 hours
TIER2_INFLUENCE_DELTA = 20                     # mid of design's 15-25 band
TIER2_T5_MAT_QUALITY = 70.0                    # named-loot T5 mat quality


# ── Tier 3 constants (SYN.8) ─────────────────────────────────────────────────
#
# Tier 3 anomalies are the world-boss events. Per design §2.8:
#   * Cadence: every 7-14 days per region (2× during active contests).
#   * Duration: ~6-12 hours (huge window for 8-16 players to coordinate).
#   * Player count: 8-16, hour+long fights.
#   * Influence: +50 to the killing-blow faction.
#   * Loot:
#       - Every participant gets a unique trophy item (housing display).
#       - Credit pot (split among participants).
#       - "N pearls scaled to participation" — floor(N/4) T5 mat
#         pieces distributed to top participants by kill count.
#
# Implementation:
#   * Daily tick (TIER3_CADENCE_TICK_INTERVAL = 24h) with 0.10
#     spawn-chance → ~10-day avg per region (midpoint of 7-14d).
#   * Per-region cap 1.
#   * 8-hour duration window.
#   * +50 influence (design literal).
#   * T5 mat quality q80 (above Tier 2's q70).
#   * Participation tracked via kill counts on the anomaly object
#     (incremented in the kill hook). Trophy distribution uses
#     all unique killers; scaled T5 mat goes to top floor(N/4)
#     by kill count.
#
# TUNING: see economy_tuning_open_questions_v1.md::SYN.8 section.
TIER3_CADENCE_TICK_INTERVAL = 24 * 3600        # 24 hours (daily)
TIER3_SPAWN_CHANCE_PER_TICK = 0.10             # → ~10-day avg per region
TIER3_MAX_PER_REGION = 1                       # 1 concurrent T3 per region
TIER3_DURATION_SECS = 8 * 60 * 60              # 8 hours (mid of 6-12h)
TIER3_INFLUENCE_DELTA = 50                     # design literal
TIER3_T5_MAT_QUALITY = 80.0                    # T3 quality > T2 q70


# ── Tier 1 template catalogue ────────────────────────────────────────────────
#
# Each template defines:
#   regions          — list of region_slugs the template can spawn in.
#                      Use REGION_ANY for "any wilderness region".
#   resolution       — "skill" or "combat".
#   display_name     — UI string.
#   short_desc       — one-line list-view description.
#   long_desc        — narrative on resolution.
#   primary_skill /  — only used when resolution == "skill".
#     secondary_skill
#   combat_npcs      — only used when resolution == "combat". List of
#                      dicts: {archetype, tier, species, name_pool}.
#                      One NPC is spawned per entry; the kill hook
#                      awards reward when the LAST one dies.
#   success_reward / — reward dicts. Shape:
#     fail_reward      {"credits": (min, max), "resources": [...], "influence": int}
#                      For combat templates, only success_reward is used
#                      (you killed them → full reward; you fled → nothing).
#   news_text        — broadcast on spawn; substitutes {region}.
#
# CW-CORRECT: no Imperial/Empire/Stormtrooper residue. The CW grep test
# (`test_cw_correct_no_imperial`) guards this.

TIER1_TEMPLATES = {

    # ════════════════════════════════════════════════════════════════
    # Dune Sea (Tatooine) — open desert templates
    # ════════════════════════════════════════════════════════════════

    "stranded_clone_scout": {
        "regions": ["tatooine_dune_sea"],
        "resolution": "skill",
        "display_name": "Stranded Clone Scout Patrol",
        "short_desc": "A Republic clone patrol separated from their unit, low on water.",
        "long_desc": (
            "A small patrol of Republic clone troopers — three of them, "
            "armor scorched, blasters powered down to conserve charge — "
            "huddle in the shade of a rocky outcrop. Their sergeant raises "
            "a gloved hand as you approach. \"We got cut off from our LAAT "
            "two days back. We need water, comms, or a ride out — and we "
            "won't be picky.\""
        ),
        "primary_skill": "medicine",
        "secondary_skill": "survival",
        "success_reward": {
            "credits": (200, 400),
            "resources": [
                ("organic", 2, 50),
                ("metal", 1, 55),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (50, 100),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Comms chatter: a Republic clone patrol has been reported "
            "stranded in {region}. Their position is fading; the Republic "
            "asks for any assistance."
        ),
    },

    "salvage_cache": {
        "regions": ["tatooine_dune_sea"],
        "resolution": "skill",
        "display_name": "Recently-Uncovered Salvage Cache",
        "short_desc": "A weathered cache, exposed by recent storm or cave-in.",
        "long_desc": (
            "Partly buried in the soft ground: a sealed metal container, "
            "its anti-theft markings worn but legible. Whoever stashed it "
            "didn't expect the recent weather to expose it. The lock looks "
            "salvageable; the contents are anyone's guess."
        ),
        "primary_skill": "technical",
        "secondary_skill": "survival",
        "success_reward": {
            "credits": (150, 350),
            "resources": [
                ("metal", 3, 55),
                ("composite", 2, 50),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (30, 80),
            "resources": [
                ("metal", 1, 30),
            ],
            "influence": 0,
        },
        "news_text": (
            "A salvage cache has been uncovered in {region}. Local "
            "scavengers are converging — first to reach it gets the haul."
        ),
    },

    "wounded_animal": {
        "regions": ["tatooine_dune_sea"],
        "resolution": "combat",
        "display_name": "Wounded Beast",
        "short_desc": "Tracks lead to a desperate, wounded creature — it will attack on sight.",
        "long_desc": (
            "Heavy tracks gouge the sand here, marked with dark drops of "
            "blood. The creature that made them — a hide-scarred bantha "
            "bull, separated from its herd — is still moving. Wounded, "
            "desperate, and dangerous. It will not flee."
        ),
        "combat_npcs": [
            {
                "archetype": "creature",
                "tier": "average",
                "species": "Bantha",
                "name_pool": ["Wounded Bantha Bull", "Maddened Bantha"],
                "weapon": "natural",
                "behavior": "aggressive",
                "personality": "An animal in pain, attacking anything that approaches.",
            },
        ],
        "success_reward": {
            "credits": (100, 250),
            "resources": [
                ("organic", 4, 55),
                ("composite", 1, 45),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (0, 0),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Trackers report a maddened, wounded beast moving through "
            "{region}. Hunters are advised — this one will not be taken "
            "with a clean shot."
        ),
    },

    "tusken_party": {
        "regions": ["tatooine_dune_sea"],
        "resolution": "combat",
        "display_name": "Roving Tusken Hunting Party",
        "short_desc": "Three Tusken raiders, gaderffii ready — they have seen you.",
        "long_desc": (
            "Sand-cloaked figures rise from behind a low ridge: three "
            "Tusken raiders, their gaderffii at the ready, eyes hidden "
            "behind goggle lenses. They have seen you. The lead raider "
            "lets out a long, ululating cry. They are not asking you "
            "to leave."
        ),
        "combat_npcs": [
            {
                "archetype": "thug",
                "tier": "average",
                "species": "Tusken Raider",
                "name_pool": ["Tusken Raider", "Sand Person Hunter"],
                "weapon": "gaderffii",
                "behavior": "aggressive",
                "personality": "A Tusken raider, defending the herd's hunting ground.",
            },
            {
                "archetype": "thug",
                "tier": "average",
                "species": "Tusken Raider",
                "name_pool": ["Tusken Raider", "Sand Person Hunter"],
                "weapon": "gaderffii",
                "behavior": "aggressive",
                "personality": "A Tusken raider, defending the herd's hunting ground.",
            },
            {
                "archetype": "thug",
                "tier": "novice",
                "species": "Tusken Raider",
                "name_pool": ["Young Tusken", "Sand Person Initiate"],
                "weapon": "gaderffii",
                "behavior": "aggressive",
                "personality": "A young Tusken raider, eager to prove herself.",
            },
        ],
        "success_reward": {
            "credits": (180, 380),
            "resources": [
                ("composite", 2, 55),
                ("metal", 2, 50),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (0, 0),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "A Tusken raiding party has been sighted in {region}. The "
            "raiders are armed and moving with intent."
        ),
    },

    "crashed_cis_probe": {
        "regions": ["tatooine_dune_sea"],
        "resolution": "skill",
        "display_name": "Crashed CIS Probe Droid",
        "short_desc": "A Separatist probe droid, smashed but partly intact.",
        "long_desc": (
            "A CIS reconnaissance droid lies half-buried where it impacted, "
            "its primary sensor cluster cracked open. The casing is "
            "Confederate manufacture — Geonosian foundry markings on the "
            "torn plating. Salvageable components inside, if you know how "
            "to safely defuse the self-destruct relay."
        ),
        "primary_skill": "technical",
        "secondary_skill": "knowledge",
        "success_reward": {
            "credits": (250, 500),
            "resources": [
                ("metal", 2, 60),
                ("energy", 2, 55),
                ("composite", 1, 60),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (50, 100),
            "resources": [
                ("metal", 1, 30),
            ],
            "influence": 0,
        },
        "news_text": (
            "A CIS probe droid has been confirmed down in {region}. "
            "Separatist tech is sought by the Republic and brokers alike."
        ),
    },

    # ════════════════════════════════════════════════════════════════
    # Coruscant Underworld — urban underworld templates
    # ════════════════════════════════════════════════════════════════

    "black_sun_courier": {
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "Black Sun Courier Ambush",
        "short_desc": "Black Sun thugs guarding a courier — a credit chip in play.",
        "long_desc": (
            "Two Black Sun enforcers flank a third figure — a courier, by "
            "the cut of the coat and the grip on a worn shoulder satchel. "
            "Whatever's in the satchel is worth the muscle. The enforcers "
            "turn at your approach, hands moving toward holstered weapons "
            "with the casual confidence of professionals."
        ),
        "combat_npcs": [
            {
                "archetype": "thug",
                "tier": "average",
                "species": "Human",
                "name_pool": ["Black Sun Enforcer", "Sun Soldier", "Sigil Bearer"],
                "weapon": "blaster_pistol",
                "behavior": "aggressive",
                "personality": "A Black Sun enforcer protecting the courier — paid to fight.",
            },
            {
                "archetype": "thug",
                "tier": "average",
                "species": "Human",
                "name_pool": ["Black Sun Enforcer", "Sun Soldier", "Sigil Bearer"],
                "weapon": "vibroblade",
                "behavior": "aggressive",
                "personality": "A Black Sun enforcer protecting the courier — paid to fight.",
            },
        ],
        "success_reward": {
            "credits": (300, 550),   # the courier's chip + the enforcers' gear
            "resources": [
                ("metal", 1, 55),
                ("composite", 1, 55),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (0, 0),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Comm chatter: a Black Sun courier is moving through {region} "
            "under armed escort. The chip they're carrying is the prize."
        ),
    },

    "factory_cache": {
        "regions": ["coruscant_underworld"],
        "resolution": "skill",
        "display_name": "Sealed Factory Cache",
        "short_desc": "A sealed contraband crate in an abandoned assembly bay.",
        "long_desc": (
            "Down a side corridor, behind a stack of rusted assembly arms, "
            "a sealed durasteel crate sits half-covered in factory dust. "
            "The lock-plate is recent, the markings smuggler-syndicate. "
            "Whoever cached this here forgot to come back for it — or "
            "didn't make it back."
        ),
        "primary_skill": "technical",
        "secondary_skill": "knowledge",
        "success_reward": {
            "credits": (200, 400),
            "resources": [
                ("metal", 2, 55),
                ("composite", 2, 55),
                ("energy", 1, 50),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (40, 90),   # cracked a panel, grabbed what was loose
            "resources": [
                ("metal", 1, 35),
            ],
            "influence": 0,
        },
        "news_text": (
            "A sealed factory cache has been spotted in {region}. The "
            "first slicer to crack it walks away rich."
        ),
    },

    "maze_rogue": {
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "Maze Rogue",
        "short_desc": "A predator from deeper levels has come up hunting.",
        "long_desc": (
            "A long shape detaches from the shadow of a support pillar — "
            "low, sinew-thin, and wrong in a way that suggests it has "
            "climbed up from a deeper level where things grow differently. "
            "It does not retreat. The Maze produces hunters, and one has "
            "come up to feed."
        ),
        "combat_npcs": [
            {
                "archetype": "creature",
                "tier": "veteran",
                "species": "Maze Predator",
                "name_pool": ["Maze Rogue", "Reaper Spawn", "Pale Hunter"],
                "weapon": "natural",
                "behavior": "aggressive",
                "personality": "A Maze predator — fast, silent, and willing to die for the kill.",
            },
        ],
        "success_reward": {
            "credits": (150, 350),
            "resources": [
                ("organic", 4, 60),
                ("composite", 2, 55),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (0, 0),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Sightings in {region}: something from the deeper levels has "
            "come up hunting. The locals are clearing the corridors."
        ),
    },

    "cis_sleeper_cell": {
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "CIS Sleeper Cell",
        "short_desc": "Two B1 battle droids hidden in the underworld — recently activated.",
        "long_desc": (
            "Tucked behind a maintenance hatch, the telltale gleam of "
            "Geonosian alloy: two B1 battle droids, recently uncrated, "
            "their optical bands cycling green-to-amber as they finish "
            "their cold-boot. Someone smuggled them down here for an "
            "operation in the upper city. They have just woken up."
        ),
        "combat_npcs": [
            {
                "archetype": "b1_battle_droid",
                "tier": "average",
                "species": "B1 Battle Droid",
                "name_pool": ["B1 Battle Droid", "CIS Infantry Unit"],
                "weapon": "blaster_rifle",
                "behavior": "aggressive",
                "personality": "A B1 battle droid following last-issued orders: engage non-CIS targets.",
            },
            {
                "archetype": "b1_battle_droid",
                "tier": "average",
                "species": "B1 Battle Droid",
                "name_pool": ["B1 Battle Droid", "CIS Infantry Unit"],
                "weapon": "blaster_rifle",
                "behavior": "aggressive",
                "personality": "A B1 battle droid following last-issued orders: engage non-CIS targets.",
            },
        ],
        "success_reward": {
            "credits": (220, 450),
            "resources": [
                ("metal", 3, 60),
                ("energy", 1, 55),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (0, 0),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Republic intelligence flags a CIS sleeper cell active in "
            "{region}. Any citizens with combat capability are asked to "
            "report — or engage."
        ),
    },

    "bounty_hunter_rival": {
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "Rival Bounty Hunter",
        "short_desc": "A hunter on the same contract as you — and willing to shoot first.",
        "long_desc": (
            "A figure in scarred armor stands across the corridor, "
            "rifle across the back, eyes tracking yours through the "
            "T-visor. \"This contract was mine,\" the hunter says, "
            "voice modulated through the helmet. \"I don't share.\" "
            "The hand moves to the rifle's strap. The Guild won't ask "
            "questions about whichever of us walks out."
        ),
        "combat_npcs": [
            {
                "archetype": "bounty_hunter",
                "tier": "veteran",
                "species": "Human",
                "name_pool": ["Rival Hunter", "Guild Contractor", "T-Visor"],
                "weapon": "blaster_rifle",
                "behavior": "tactical",
                "personality": "A bounty hunter on the same contract — professional, lethal, here to win.",
            },
        ],
        "success_reward": {
            "credits": (350, 600),
            "resources": [
                ("metal", 2, 60),
                ("composite", 1, 60),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (0, 0),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Guild watch reports a rival hunter in {region} working a "
            "contract that crosses several others. Hunters working the "
            "same job — be ready."
        ),
    },
}


# ── Tier 2 template catalogue (SYN.7.b) ──────────────────────────────────────
#
# Each Tier 2 template extends the Tier 1 schema with:
#   tier: 2                    — explicit; Tier 1 templates default to 1
#   phases: [                  — list of waves; each is a dict with
#     {                          its own combat_npcs spec list
#       "name": str,             — phase narrative title
#       "intro": str,            — surfaced when phase begins
#       "combat_npcs": [...],    — same shape as Tier 1 combat_npcs
#     },
#     ...
#   ]
#   named_loot: {              — optional; granted to the killing-blow
#     "type": "resource"|"item", participant at final-phase clear
#     "key": str,
#     "qty": int,
#     "quality": float,        — for resource type only
#     "name": str,             — for item type only
#     "description": str,      — flavor for both types
#   }
#
# Resolution flow (multi-phase):
#   investigate <id> → spawn phase 0 NPCs.
#   Kill last NPC of phase N → phase N+1 spawns (or final reward fires).
#   Reward distribution (final phase clear):
#     - All characters in the anchor room split credits/resources.
#     - Influence delta goes to killing-blow killer's faction.
#     - Named loot goes to killing-blow killer alone.
#     - If no characters remain in the room at final clear, no payout.
#
# CW-correctness: same grep (no imperial/empire/stormtrooper/tie) applies
# automatically via the extended test_cw_correct_no_imperial.

TIER2_TEMPLATES = {

    # ════════════════════════════════════════════════════════════════
    # Dune Sea (Tatooine) — 3 templates
    # ════════════════════════════════════════════════════════════════

    "downed_republic_acclamator": {
        "tier": 2,
        "regions": ["tatooine_dune_sea"],
        "resolution": "combat",
        "display_name": "Downed Republic Acclamator",
        "short_desc": (
            "A Republic Acclamator has crash-landed; CIS scavengers "
            "are inbound."
        ),
        "long_desc": (
            "The Acclamator's prow has plowed a half-kilometer scar "
            "through the dunes. Smoke rises from a ruptured plasma "
            "manifold. Republic survivors are pinned at the breached "
            "boarding hatch, and CIS scouts have already begun working "
            "their way toward the wreck. Whoever clears the site first "
            "owns whatever the Acclamator was carrying."
        ),
        "phases": [
            {
                "name": "CIS Scout Element",
                "intro": (
                    "A CIS scout element converges on the wreck — they "
                    "got here first. Three B1 droids and a tactical "
                    "lead break from cover."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "average",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Battle Droid", "CIS Scout Unit"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A CIS scout droid, advance element.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "average",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Battle Droid", "CIS Scout Unit"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A CIS scout droid, advance element.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["CIS Tactical Officer", "Confederate Lead"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A CIS tactical officer coordinating the scout element.",
                    },
                ],
            },
            {
                "name": "CIS Heavy Response",
                "intro": (
                    "The scouts called for backup. A heavier element "
                    "arrives: a Super Battle Droid and two B1s with "
                    "elevated weapons."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B2 Super Battle Droid",
                        "name_pool": ["B2 Super Battle Droid", "Heavy Confederate Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B2 super battle droid — heavy combat platform.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "average",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Battle Droid", "CIS Heavy Support"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B1 battle droid, heavy support.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "average",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Battle Droid", "CIS Heavy Support"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B1 battle droid, heavy support.",
                    },
                ],
            },
            {
                "name": "Salvage-Team Commander",
                "intro": (
                    "From the wreck's far side, a CIS commando team "
                    "lead steps clear of cover — the salvage "
                    "commander, here to collect what the Republic "
                    "left behind."
                ),
                "combat_npcs": [
                    {
                        "archetype": "bounty_hunter", "tier": "superior",
                        "species": "Human",
                        "name_pool": ["CIS Salvage Commander", "Confederate Field Lead"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A CIS salvage commander — elite, decorated, here to win.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (1200, 2400),
            "resources": [
                ("metal", 6, 65),
                ("composite", 4, 65),
                ("energy", 3, 60),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "named_loot": {
            "type": "resource",
            "key": "weapons_capacitor_core",
            "qty": 1,
            "quality": TIER2_T5_MAT_QUALITY,
            "description": "A salvaged T5 weapons capacitor core from the Acclamator's main armament.",
        },
        "news_text": (
            "Comms chatter: a Republic Acclamator has gone down in "
            "{region}. CIS scavengers are already converging on the "
            "wreck. The Republic asks for any available assistance — "
            "this fight is not a small one."
        ),
    },

    "hutt_smuggling_convoy": {
        "tier": 2,
        "regions": ["tatooine_dune_sea"],
        "resolution": "combat",
        "display_name": "Hutt Smuggling Convoy",
        "short_desc": (
            "A Hutt convoy moves through the dunes; armed escort "
            "rides heavy."
        ),
        "long_desc": (
            "A line of speeder freighters in the distance, hauling "
            "Hutt-marked cargo. The escort is professional — Nikto "
            "muscle on swoops, an outrider scout, and at least one "
            "Hutt fixer riding the lead freighter. Whatever the "
            "convoy is carrying, the Cartels paid premium for the "
            "muscle. Take it from them or earn passage."
        ),
        "phases": [
            {
                "name": "Outrider Pickets",
                "intro": (
                    "Two Nikto outriders break from the convoy line, "
                    "weapons up — they spotted you first."
                ),
                "combat_npcs": [
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Nikto",
                        "name_pool": ["Nikto Outrider", "Cartel Escort"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Nikto outrider in the Hutt cartels' employ.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Nikto",
                        "name_pool": ["Nikto Outrider", "Cartel Escort"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Nikto outrider in the Hutt cartels' employ.",
                    },
                ],
            },
            {
                "name": "Convoy Heavies",
                "intro": (
                    "The convoy halts. Three more guns drop from the "
                    "freighters — a Trandoshan enforcer leads them."
                ),
                "combat_npcs": [
                    {
                        "archetype": "bounty_hunter", "tier": "veteran",
                        "species": "Trandoshan",
                        "name_pool": ["Trandoshan Enforcer", "Cartel Heavy"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Trandoshan enforcer leading the Hutt cartel escort.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Weequay",
                        "name_pool": ["Weequay Gunhand", "Cartel Heavy"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Weequay gun-for-hire, Hutt cartel escort.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Weequay",
                        "name_pool": ["Weequay Gunhand", "Cartel Heavy"],
                        "weapon": "vibroblade", "behavior": "aggressive",
                        "personality": "A Weequay gun-for-hire, Hutt cartel escort.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (1000, 2000),
            "resources": [
                ("metal", 4, 60),
                ("composite", 3, 60),
                ("organic", 2, 55),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "named_loot": {
            "type": "resource",
            "key": "weapons_capacitor_core",
            "qty": 1,
            "quality": TIER2_T5_MAT_QUALITY,
            "description": "A T5 weapons capacitor core — Hutt cartel smuggled goods from a corporate manifest.",
        },
        "news_text": (
            "A Hutt cartel convoy is moving through {region} under "
            "heavy escort. Whatever they're carrying is worth the "
            "muscle. Interception or escort — pick a side, fast."
        ),
    },

    "cis_commando_deployment": {
        "tier": 2,
        "regions": ["tatooine_dune_sea"],
        "resolution": "combat",
        "display_name": "CIS Commando Deployment",
        "short_desc": (
            "A CIS strike team has landed; a Republic outpost is at "
            "risk."
        ),
        "long_desc": (
            "Engine-glow scoring on the dune face marks where the CIS "
            "drop pod came down. The strike team has fanned out — a "
            "BX commando element, with a tactical droid running the "
            "operation. Their objective is unclear, but they're "
            "moving toward a Republic forward observation post less "
            "than a kilometer away. Stop them."
        ),
        "phases": [
            {
                "name": "BX Commando Vanguard",
                "intro": (
                    "Two BX commando droids materialize from the "
                    "dune shadow — fast, precise, lethal."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "BX Commando Droid",
                        "name_pool": ["BX Commando Droid", "CIS Special Forces Unit"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A BX commando droid — elite CIS infiltrator.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "BX Commando Droid",
                        "name_pool": ["BX Commando Droid", "CIS Special Forces Unit"],
                        "weapon": "vibroblade", "behavior": "tactical",
                        "personality": "A BX commando droid — close-quarters specialist.",
                    },
                ],
            },
            {
                "name": "Heavy Support",
                "intro": (
                    "Heavier weight enters the fight — a Super "
                    "Battle Droid breaches cover, two B1s flanking."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B2 Super Battle Droid",
                        "name_pool": ["B2 Super Battle Droid", "CIS Heavy Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B2 super battle droid in heavy-support role.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "average",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Battle Droid", "CIS Support Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B1 battle droid in support role.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "average",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Battle Droid", "CIS Support Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B1 battle droid in support role.",
                    },
                ],
            },
            {
                "name": "Tactical Droid Command",
                "intro": (
                    "The tactical droid commanding the operation "
                    "advances — its photoreceptor focused, its "
                    "personal-defense array online."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "T-Series Tactical Droid",
                        "name_pool": ["CIS Tactical Droid", "T-Series Command Unit"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A T-series tactical droid — the strike team's commander.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (1100, 2200),
            "resources": [
                ("metal", 5, 65),
                ("energy", 3, 60),
                ("composite", 3, 60),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "named_loot": {
            "type": "item",
            "key": "tactical_droid_command_module",
            "qty": 1,
            "name": "T-Series Tactical Droid Command Module",
            "description": (
                "A salvaged command module from a CIS tactical "
                "droid. Republic intelligence will pay for this — "
                "or a collector will."
            ),
        },
        "news_text": (
            "Republic Intelligence reports a CIS commando deployment "
            "in {region}. A Republic forward observation post is the "
            "likely target. Combat-capable citizens are asked to "
            "intervene immediately."
        ),
    },

    # ════════════════════════════════════════════════════════════════
    # Coruscant Underworld — 2 templates (region parity from SYN.7.a.fix)
    # ════════════════════════════════════════════════════════════════

    "maze_predator_outbreak": {
        "tier": 2,
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "Maze Predator Outbreak",
        "short_desc": (
            "A pack of Maze predators has come up from the deep "
            "levels — escalating waves."
        ),
        "long_desc": (
            "The corridor stinks of musk and ozone. Whatever broke "
            "open the lower-level habitat gate let multiple Maze "
            "predators come up at once. They're hunting in pack — "
            "and the pack is hungry. Sightings indicate at least "
            "three waves moving in fast succession."
        ),
        "phases": [
            {
                "name": "Scout Pack",
                "intro": (
                    "The first wave breaks cover — two Maze "
                    "predators, smaller scouts running ahead of "
                    "the pack."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "average",
                        "species": "Maze Predator (scout)",
                        "name_pool": ["Maze Scout", "Pack Outrunner"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A Maze predator scout, fast and lethal.",
                    },
                    {
                        "archetype": "creature", "tier": "average",
                        "species": "Maze Predator (scout)",
                        "name_pool": ["Maze Scout", "Pack Outrunner"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A Maze predator scout, fast and lethal.",
                    },
                ],
            },
            {
                "name": "Pack Main",
                "intro": (
                    "The main pack arrives — three Maze predators "
                    "at full size, jaws working."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Maze Predator",
                        "name_pool": ["Maze Predator", "Reaper Spawn"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A full-grown Maze predator.",
                    },
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Maze Predator",
                        "name_pool": ["Maze Predator", "Reaper Spawn"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A full-grown Maze predator.",
                    },
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Maze Predator",
                        "name_pool": ["Maze Predator", "Reaper Spawn"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A full-grown Maze predator.",
                    },
                ],
            },
            {
                "name": "Alpha",
                "intro": (
                    "Last comes the alpha — half again the size of "
                    "the pack, scarred from previous hunts."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "superior",
                        "species": "Maze Predator Alpha",
                        "name_pool": ["Maze Pack Alpha", "Reaper Patriarch"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "The pack alpha — the largest, the oldest, the most dangerous.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (900, 1800),
            "resources": [
                ("organic", 8, 65),
                ("composite", 4, 60),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "named_loot": {
            "type": "resource",
            "key": "composite_chitin",
            "qty": 1,
            "quality": TIER2_T5_MAT_QUALITY,
            "description": "Hardened chitin plates from the pack alpha — a T5 armor material.",
        },
        "news_text": (
            "A Maze predator pack has broken into {region}. Multiple "
            "waves reported. The corridors are clearing themselves "
            "of locals — the only thing left will be hunters or prey."
        ),
    },

    "coruscant_gang_war": {
        "tier": 2,
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "Coruscant Gang War Flashpoint",
        "short_desc": (
            "Black Sun and Pyke gangs erupted into open combat — "
            "step in or get caught."
        ),
        "long_desc": (
            "Whatever truce was holding has broken. Black Sun "
            "muscle holds the south end of the corridor; Pyke "
            "Syndicate enforcers move on them from the north. The "
            "first volley shattered the lighting strip — the rest "
            "will shatter heads. Any side that walks away from this "
            "owes whoever helped them, badly."
        ),
        "phases": [
            {
                "name": "First Volley",
                "intro": (
                    "Three Black Sun and two Pyke enforcers — "
                    "they're shooting at each other, and at you "
                    "if you make yourself a target."
                ),
                "combat_npcs": [
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["Black Sun Enforcer", "Sun Captain"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Black Sun enforcer in the middle of a turf war.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["Black Sun Enforcer", "Sun Captain"],
                        "weapon": "blaster_pistol", "behavior": "aggressive",
                        "personality": "A Black Sun enforcer in the middle of a turf war.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Pyke",
                        "name_pool": ["Pyke Enforcer", "Syndicate Soldier"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Pyke Syndicate enforcer, here to push Black Sun off the block.",
                    },
                    {
                        "archetype": "thug", "tier": "average",
                        "species": "Pyke",
                        "name_pool": ["Pyke Enforcer", "Syndicate Soldier"],
                        "weapon": "blaster_pistol", "behavior": "aggressive",
                        "personality": "A Pyke Syndicate enforcer in the turf war.",
                    },
                ],
            },
            {
                "name": "Boss Engagement",
                "intro": (
                    "Both gang leaders pull up to the corridor — "
                    "a Black Sun Vigo lieutenant and a Pyke "
                    "subaltern. Their professional escorts move with them."
                ),
                "combat_npcs": [
                    {
                        "archetype": "bounty_hunter", "tier": "superior",
                        "species": "Human",
                        "name_pool": ["Black Sun Vigo Lieutenant", "Sun Field Commander"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A Black Sun Vigo's field lieutenant — elite, paid well, here to win.",
                    },
                    {
                        "archetype": "bounty_hunter", "tier": "veteran",
                        "species": "Pyke",
                        "name_pool": ["Pyke Subaltern", "Syndicate Field Lead"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A Pyke Syndicate field lead — veteran fighter, here to take ground.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (800, 1600),
            "resources": [
                ("metal", 3, 60),
                ("composite", 3, 60),
                ("energy", 2, 55),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "named_loot": {
            "type": "item",
            "key": "black_sun_signet",
            "qty": 1,
            "name": "Black Sun Vigo Signet Ring",
            "description": (
                "A heavy signet ring marking the bearer as a "
                "lieutenant in a Black Sun Vigo's organization. "
                "Worth money on the black market — or face on the "
                "street."
            ),
        },
        "news_text": (
            "Underworld watch reports an open gang war flashpoint "
            "in {region} — Black Sun and Pyke Syndicate trading "
            "fire. The block is going to belong to whoever walks "
            "out."
        ),
    },
}


# ── Tier 3 template catalogue (SYN.8) ────────────────────────────────────────
#
# Tier 3 templates extend the Tier 2 schema with TWO additional fields:
#   trophy_per_participant: {key, name, description}
#     Granted to every char who killed at least 1 anomaly NPC during
#     the encounter. is_trophy=True so housing.trophy_mount can
#     pick it up.
#   scaled_t5_mat: {key, quality, per_4_participants}
#     The pearls-style drop. floor(N_participants / 4) pieces total,
#     distributed to top participants by kill count (descending).
#     Killer wins ties.
#
# Resolution: same multi-phase machinery as Tier 2 — phase
# advancement on last-NPC-of-phase death, final payout on last-NPC-
# of-final-phase death. The payout function (_payout_combat_anomaly)
# branches on tier=3 to add the trophy + scaled T5 mat distribution.
#
# Participant tracking: WildernessAnomaly.kill_counts is a
# dict[int, int] mapping char_id → number of anomaly NPCs they
# killed. The kill hook in parser/combat_commands.py increments
# this for every anomaly-tagged NPC kill.
#
# CW-correctness: same grep applies. No imperial/empire residue
# in the templates below (the Separatist Capital Ship is the
# CW-correct counterpart to the design's hypothetical wreck).

TIER3_TEMPLATES = {

    # ════════════════════════════════════════════════════════════════
    # Dune Sea (Tatooine)
    # ════════════════════════════════════════════════════════════════

    "krayt_dragon": {
        "tier": 3,
        "regions": ["tatooine_dune_sea"],
        "resolution": "combat",
        "display_name": "Krayt Dragon",
        "short_desc": (
            "A canyon krayt dragon has emerged — the deep desert "
            "has answered."
        ),
        "long_desc": (
            "The ground itself shakes. From a fissure beneath a "
            "weathered rock shelf rises something the size of a "
            "small starship — armored hide pitted with the scars "
            "of centuries, eyes the color of polished durasteel. "
            "The canyon krayt has scented blood, or fear, or both, "
            "and it is here. Only a coordinated war-band has any "
            "chance of bringing one down."
        ),
        "phases": [
            {
                "name": "Approach: Guardian Pack",
                "intro": (
                    "Two juvenile krayts flank the elder, defending "
                    "the territory. Bring them down to reach the "
                    "dragon."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Krayt Dragon (juvenile)",
                        "name_pool": ["Juvenile Krayt", "Krayt Outrider"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A juvenile canyon krayt — vicious, fast, defending the elder.",
                    },
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Krayt Dragon (juvenile)",
                        "name_pool": ["Juvenile Krayt", "Krayt Outrider"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A juvenile canyon krayt — vicious, fast, defending the elder.",
                    },
                ],
            },
            {
                "name": "The Elder",
                "intro": (
                    "The canyon krayt itself enters the fight. Its "
                    "hide turns most blaster bolts; its tail-strike "
                    "can fell a bantha in one blow. Bring everything."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "superior",
                        "species": "Canyon Krayt Dragon",
                        "name_pool": ["Canyon Krayt", "Elder Dragon"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "The canyon krayt — apex predator of the Dune Sea.",
                    },
                ],
            },
            {
                "name": "Enraged",
                "intro": (
                    "Half its hide hangs in tatters. The krayt "
                    "withdraws, circles, and re-emerges from beneath "
                    "the sand — enraged now, no longer hunting but "
                    "killing."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "superior",
                        "species": "Canyon Krayt Dragon (enraged)",
                        "name_pool": ["Enraged Krayt", "Death Dragon"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "The wounded krayt, now operating on pure rage. It will kill or be killed.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (8000, 16000),       # split across participants
            "resources": [
                ("organic", 12, 70),
                ("composite", 8, 70),
                ("metal", 6, 65),
            ],
            "influence": TIER3_INFLUENCE_DELTA,
        },
        "trophy_per_participant": {
            "key": "krayt_dragon_scale",
            "name": "Krayt Dragon Scale",
            "description": (
                "A polished scale from a canyon krayt dragon, "
                "scored with the marks of the kill. A trophy worth "
                "displaying."
            ),
        },
        "scaled_t5_mat": {
            "key": "deep_dune_iron",
            "quality": TIER3_T5_MAT_QUALITY,
            "per_4_participants": 1,
        },
        "news_text": (
            "Long-range scanners and dune-runner reports converge: a "
            "canyon krayt dragon has emerged in {region}. Every "
            "hunter in the sector is converging. Coordinate or stay "
            "clear."
        ),
    },

    # ════════════════════════════════════════════════════════════════
    # Coruscant Underworld
    # ════════════════════════════════════════════════════════════════

    "maze_predator_apex": {
        "tier": 3,
        "regions": ["coruscant_underworld"],
        "resolution": "combat",
        "display_name": "Maze Predator Apex",
        "short_desc": (
            "The Maze has produced something larger than has been "
            "seen in a generation."
        ),
        "long_desc": (
            "The deep-level habitats are silent. Whatever broke "
            "through the bulkhead is the apex of its food chain — "
            "twice the size of the Maze rogues seen on the upper "
            "levels, with the patience of something that has been "
            "growing in the dark for decades. It does not chase. "
            "It waits, lets the hunters come to it, and then it "
            "tears."
        ),
        "phases": [
            {
                "name": "Pack Vanguard",
                "intro": (
                    "Three veteran Maze predators move into the "
                    "corridor first — pack outriders covering the "
                    "apex's approach."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Maze Predator (apex pack)",
                        "name_pool": ["Apex Outrider", "Reaper Vanguard"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A Maze predator in the apex's hunting pack.",
                    },
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Maze Predator (apex pack)",
                        "name_pool": ["Apex Outrider", "Reaper Vanguard"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A Maze predator in the apex's hunting pack.",
                    },
                    {
                        "archetype": "creature", "tier": "veteran",
                        "species": "Maze Predator (apex pack)",
                        "name_pool": ["Apex Outrider", "Reaper Vanguard"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "A Maze predator in the apex's hunting pack.",
                    },
                ],
            },
            {
                "name": "The Apex",
                "intro": (
                    "The corridor lights fail. From the dark steps "
                    "the apex — twice the height of the pack, "
                    "scarred with the marks of countless kills."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "superior",
                        "species": "Maze Predator Apex",
                        "name_pool": ["The Apex", "Reaper Patriarch"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "The apex Maze predator — apex of its food chain, here to feed.",
                    },
                ],
            },
            {
                "name": "Frenzy",
                "intro": (
                    "Wounded badly, the apex withdraws into the "
                    "service shafts — and re-emerges in a frenzy, "
                    "abandoning its predator's patience for raw "
                    "aggression."
                ),
                "combat_npcs": [
                    {
                        "archetype": "creature", "tier": "superior",
                        "species": "Maze Predator Apex (frenzied)",
                        "name_pool": ["Frenzied Apex", "Death-Bringer"],
                        "weapon": "natural", "behavior": "aggressive",
                        "personality": "The wounded apex, abandoning hunting for killing.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (7000, 14000),
            "resources": [
                ("organic", 14, 70),
                ("composite", 8, 70),
            ],
            "influence": TIER3_INFLUENCE_DELTA,
        },
        "trophy_per_participant": {
            "key": "maze_apex_fang",
            "name": "Maze Apex Fang",
            "description": (
                "A curved fang from the apex predator of Coruscant's "
                "lower levels. Mounted, it is a clear statement: "
                "you went down there, and you came back."
            ),
        },
        "scaled_t5_mat": {
            "key": "composite_chitin",
            "quality": TIER3_T5_MAT_QUALITY,
            "per_4_participants": 1,
        },
        "news_text": (
            "Reports converge from {region}: the lower levels are "
            "silent. Something large, slow, and patient has come up. "
            "The Underworld watch advises armed teams only."
        ),
    },

    # ════════════════════════════════════════════════════════════════
    # Any region (REGION_ANY — spawns wherever)
    # ════════════════════════════════════════════════════════════════

    "crashed_separatist_capital_ship": {
        "tier": 3,
        "regions": [REGION_ANY],
        "resolution": "combat",
        "display_name": "Crashed Separatist Capital Ship",
        "short_desc": (
            "A Separatist capital ship has come down — the salvage "
            "is contested."
        ),
        "long_desc": (
            "The wreck is enormous — a kilometer of Confederate "
            "warship plowed into the ground, its keel split open. "
            "Security droids — the ship's automated defense network — "
            "are still operational, moving through the debris in "
            "tight formation. They will not abandon the wreck. "
            "Whoever takes the site takes whatever the CIS was "
            "carrying."
        ),
        "phases": [
            {
                "name": "Perimeter Security",
                "intro": (
                    "Outer perimeter security: four B1s patrol the "
                    "wreck's edge with crisp tactical formation."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Perimeter Unit", "CIS Security"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 perimeter security unit defending the wreck.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Perimeter Unit", "CIS Security"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 perimeter security unit defending the wreck.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Perimeter Unit", "CIS Security"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 perimeter security unit defending the wreck.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Perimeter Unit", "CIS Security"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 perimeter security unit defending the wreck.",
                    },
                ],
            },
            {
                "name": "Heavy Response",
                "intro": (
                    "Two B2 Super Battle Droids breach a sealed "
                    "compartment — the ship's heavy reserves are "
                    "online and hostile."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "B2 Super Battle Droid",
                        "name_pool": ["B2 Super Battle Droid", "CIS Heavy Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B2 super battle droid — heavy combat platform from the wreck's reserves.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "B2 Super Battle Droid",
                        "name_pool": ["B2 Super Battle Droid", "CIS Heavy Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B2 super battle droid — heavy combat platform from the wreck's reserves.",
                    },
                ],
            },
            {
                "name": "Tactical Command",
                "intro": (
                    "From the bridge wreckage: the ship's commanding "
                    "tactical droid emerges, escorted by two BX "
                    "commandos. The final stand."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "T-Series Tactical Droid",
                        "name_pool": ["CIS Ship Commander", "T-Series Battle-Mind"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "The ship's tactical command droid — coordinating the final defense.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "BX Commando Droid",
                        "name_pool": ["BX Bridge Guard", "CIS Special Forces"],
                        "weapon": "vibroblade", "behavior": "tactical",
                        "personality": "A BX commando droid bridging the ship's bridge.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "BX Commando Droid",
                        "name_pool": ["BX Bridge Guard", "CIS Special Forces"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A BX commando droid bridging the ship's bridge.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (6000, 12000),
            "resources": [
                ("metal", 10, 70),
                ("composite", 8, 70),
                ("energy", 5, 65),
            ],
            "influence": TIER3_INFLUENCE_DELTA,
        },
        "trophy_per_participant": {
            "key": "separatist_hull_plate",
            "name": "Salvaged Separatist Hull Plate",
            "description": (
                "A scorched, blast-marked hull plate from a "
                "Confederate capital ship. Republic loyalists will "
                "pay for one mounted on the wall; collectors will "
                "pay more."
            ),
        },
        "scaled_t5_mat": {
            "key": "weapons_capacitor_core",
            "quality": TIER3_T5_MAT_QUALITY,
            "per_4_participants": 1,
        },
        "news_text": (
            "Republic Intelligence reports a CIS capital ship "
            "downed in {region}. The wreck is still defended by "
            "automated security. Every salvager in the sector is "
            "converging."
        ),
    },

    "republic_lost_patrol": {
        "tier": 3,
        "regions": [REGION_ANY],
        "resolution": "combat",
        "display_name": "Republic Lost Patrol — Captured",
        "short_desc": (
            "A Republic patrol has been captured by CIS forces — "
            "rescue them, fast."
        ),
        "long_desc": (
            "Surveillance contact: a Republic patrol — multiple "
            "clone troopers and at least one Jedi — has been "
            "ambushed and captured by a CIS holding force. The "
            "captors are holding them at a temporary outpost. "
            "Rescue is the priority; the CIS is rumored to want to "
            "interrogate the Jedi. Every hour matters."
        ),
        "phases": [
            {
                "name": "CIS Holding Force — Outer Picket",
                "intro": (
                    "The outer picket: four B1s and a tactical "
                    "officer. Drop them before they can call inside."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Holding Force", "CIS Patrol"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 battle droid on the holding force perimeter.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Holding Force", "CIS Patrol"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 battle droid on the holding force perimeter.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Holding Force", "CIS Patrol"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 battle droid on the holding force perimeter.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "B1 Battle Droid",
                        "name_pool": ["B1 Holding Force", "CIS Patrol"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A B1 battle droid on the holding force perimeter.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["CIS Tactical Officer", "Confederate Patrol Lead"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A CIS tactical officer coordinating the holding force.",
                    },
                ],
            },
            {
                "name": "Interrogation Detail",
                "intro": (
                    "The interrogation detail moves to silence the "
                    "prisoners — two BX commandos and a Magnaguard."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "IG-100 MagnaGuard",
                        "name_pool": ["IG-100 MagnaGuard", "Elite Bodyguard Droid"],
                        "weapon": "vibroblade", "behavior": "aggressive",
                        "personality": "An IG-100 MagnaGuard — elite CIS bodyguard, here to silence the prisoners.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "BX Commando Droid",
                        "name_pool": ["BX Interrogator", "CIS Special Forces"],
                        "weapon": "vibroblade", "behavior": "tactical",
                        "personality": "A BX commando droid attached to the interrogation detail.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "veteran",
                        "species": "BX Commando Droid",
                        "name_pool": ["BX Interrogator", "CIS Special Forces"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A BX commando droid attached to the interrogation detail.",
                    },
                ],
            },
            {
                "name": "Final Reinforcements",
                "intro": (
                    "A final wave: two more B2 Super Battle Droids "
                    "and a tactical droid — the holding force's "
                    "last stand."
                ),
                "combat_npcs": [
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "T-Series Tactical Droid",
                        "name_pool": ["CIS Tactical Commander", "T-Series Battle-Mind"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "The CIS tactical commander, here to ensure no prisoners are freed.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "B2 Super Battle Droid",
                        "name_pool": ["B2 Super Battle Droid", "CIS Heavy Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B2 super battle droid, last-stand reinforcement.",
                    },
                    {
                        "archetype": "b1_battle_droid", "tier": "superior",
                        "species": "B2 Super Battle Droid",
                        "name_pool": ["B2 Super Battle Droid", "CIS Heavy Unit"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A B2 super battle droid, last-stand reinforcement.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (7500, 15000),
            "resources": [
                ("metal", 8, 70),
                ("composite", 6, 70),
                ("energy", 4, 65),
            ],
            "influence": TIER3_INFLUENCE_DELTA,
        },
        "trophy_per_participant": {
            "key": "republic_patrol_insignia",
            "name": "Republic Patrol Insignia",
            "description": (
                "A unit insignia from the rescued Republic patrol — "
                "presented in thanks. A symbol of service worth "
                "displaying."
            ),
        },
        "scaled_t5_mat": {
            "key": "weapons_capacitor_core",
            "quality": TIER3_T5_MAT_QUALITY,
            "per_4_participants": 1,
        },
        "news_text": (
            "Republic Intelligence reports a captured Republic "
            "patrol in {region} — Jedi escort confirmed. The CIS "
            "holding force is preparing to relocate the prisoners. "
            "Time is short. Coordinate rescue."
        ),
    },
}


# ── Staged-event scenario templates (events_playable_scenarios_design_v1) ─────
#
# 2026-06-24: communal events become PLAYABLE SITE SCENARIOS. A staged cult
# (engine.staged_event) anchors a site room and walks through these authored
# anomalies, one per stage: a multi-phase combat wave, a skill gate (slice the
# cistern), and a boss. These reuse the EXISTING anomaly schema + resolver +
# reward funnels verbatim — they are NOT spawned by the random tick (their
# `regions` is empty), only by the scenario orchestrator via
# `spawn_scenario_anomaly`, which names the template + anchor room explicitly.
#
# NPC specs route through the same `generate_npc(tier, archetype, species)` path
# every other template uses, so the cult NPCs are statted by the live WEG-D6
# archetype/tier engine (provenance: invented Clone-Wars-era dark-side cult; B3
# era-clean — sun-cult zealots / Hierophant, no Imperial/Rebel strings, no canon
# figures). Reward bands mirror the same-tier Dune-Sea templates above.
#
# The skill stage uses resolution:"skill" — the LIVE, tested one-shot skill-check
# path, deliberately NOT the inert per-phase party-challenge seam (which is
# guarded post-launch by the T3.23 inertness tests).

SCENARIO_TEMPLATES = {

    # ── Stage 1: wave combat — Break the Shrines ──────────────────────────────
    "hollow_sun_shrine_assault": {
        "tier": 2,
        "scenario": "hollow_sun",
        "regions": [],                       # orchestrator-spawned only
        "resolution": "combat",
        "display_name": "Hollow Sun Shrine Assault",
        "short_desc": (
            "Sun-maddened zealots ring the desert shrines, raving as you "
            "approach."
        ),
        "long_desc": (
            "A ring of crude sun-shrines crowns the dune, daubed with the "
            "Hollow Sun's bleached sigil. Zealots in sun-bleached rags rise "
            "from behind the stones, eyes burned half-blind from staring at "
            "the twin suns. They do not parley. They throw themselves at you "
            "to defend the shrines."
        ),
        "phases": [
            {
                "name": "Shrine Wardens",
                "intro": (
                    "The first ring of zealots breaks toward you — three "
                    "of them, screaming hymns to the dying suns."
                ),
                "combat_npcs": [
                    {
                        "archetype": "thug", "tier": "average",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Zealot", "Sun-Maddened Acolyte"],
                        "weapon": "vibroblade", "behavior": "aggressive",
                        "personality": "A Hollow Sun zealot, defending the shrines in a sun-struck fervor.",
                    },
                    {
                        "archetype": "thug", "tier": "average",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Zealot", "Sun-Maddened Acolyte"],
                        "weapon": "blaster_pistol", "behavior": "aggressive",
                        "personality": "A Hollow Sun zealot, defending the shrines in a sun-struck fervor.",
                    },
                    {
                        "archetype": "thug", "tier": "novice",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Initiate", "Sun-Touched Penitent"],
                        "weapon": "vibroblade", "behavior": "aggressive",
                        "personality": "A young Hollow Sun initiate, throwing herself at the unbelievers.",
                    },
                ],
            },
            {
                "name": "The Sun-Speaker",
                "intro": (
                    "From the largest shrine steps a Sun-Speaker, flanked "
                    "by two armed faithful — louder, surer, deadlier."
                ),
                "combat_npcs": [
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Sun-Speaker", "Shrine Warden"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A Hollow Sun Sun-Speaker — a zealot-leader rallying the faithful at the shrine.",
                    },
                    {
                        "archetype": "thug", "tier": "average",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Zealot", "Shrine Guard"],
                        "weapon": "blaster_rifle", "behavior": "aggressive",
                        "personality": "A Hollow Sun zealot guarding the Sun-Speaker.",
                    },
                    {
                        "archetype": "thug", "tier": "average",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Zealot", "Shrine Guard"],
                        "weapon": "vibroblade", "behavior": "aggressive",
                        "personality": "A Hollow Sun zealot guarding the Sun-Speaker.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (400, 800),
            "resources": [
                ("composite", 2, 55),
                ("metal", 2, 50),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "news_text": (
            "The Cult of the Hollow Sun has fortified its desert shrines in "
            "{region}. Their zealots are turning back anyone who approaches."
        ),
    },

    # ── Stage 2: skill gate — Cut the Water Tithes ────────────────────────────
    "hollow_sun_cistern_slice": {
        "tier": 1,
        "scenario": "hollow_sun",
        "regions": [],
        "resolution": "skill",
        "display_name": "Hollow Sun Water Tithe",
        "short_desc": (
            "The cult's cistern controls bleed the moisture farms dry — "
            "slice them, or turn the farmers."
        ),
        "long_desc": (
            "The Hollow Sun taps the local moisture farms through a bank of "
            "seized cistern controllers, siphoning the water as 'tithes' to "
            "the dying suns. A slicer can lock them out of the controllers; a "
            "smooth talker can convince the cowed farmers to cut the cult off "
            "themselves. Either way, the tithes stop here."
        ),
        "primary_skill": "security",
        "secondary_skill": "computer_programming",
        "success_reward": {
            "credits": (250, 500),
            "resources": [
                ("energy", 2, 55),
                ("metal", 1, 50),
            ],
            "influence": TIER1_INFLUENCE_DELTA,
        },
        "fail_reward": {
            "credits": (60, 120),
            "resources": [],
            "influence": 0,
        },
        "news_text": (
            "Moisture farmers in {region} report the Hollow Sun is bleeding "
            "their cisterns dry. Slicers and negotiators are needed to cut "
            "the cult's water tithes."
        ),
    },

    # ── Stage 3: boss — Confront the Hierophant ───────────────────────────────
    "hollow_sun_hierophant": {
        "tier": 2,
        "scenario": "hollow_sun",
        "regions": [],
        "resolution": "combat",
        "display_name": "The Hollow Sun's Hierophant",
        "short_desc": (
            "The Hierophant of the Hollow Sun makes a last stand amid the "
            "faithful."
        ),
        "long_desc": (
            "At the heart of the shrine-ring stands the Hierophant of the "
            "Hollow Sun — gaunt, sun-scarred, robed in bleached cloth, a "
            "ritual blade in one hand and a heavy blaster in the other. The "
            "last of the faithful close ranks around their prophet. Break the "
            "Hierophant and the cult scatters."
        ),
        "phases": [
            {
                "name": "The Faithful Close Ranks",
                "intro": (
                    "The Hierophant's honor guard moves first — two armed "
                    "zealots buying their prophet time."
                ),
                "combat_npcs": [
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Faithful", "Hierophant's Guard"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "A Hollow Sun honor guard, shielding the Hierophant with their life.",
                    },
                    {
                        "archetype": "thug", "tier": "veteran",
                        "species": "Human",
                        "name_pool": ["Hollow Sun Faithful", "Hierophant's Guard"],
                        "weapon": "vibroblade", "behavior": "aggressive",
                        "personality": "A Hollow Sun honor guard, shielding the Hierophant with their life.",
                    },
                ],
            },
            {
                "name": "The Hierophant",
                "intro": (
                    "The honor guard falls and the Hierophant steps forward "
                    "alone, blade raised to the dying light. This is the end "
                    "of the cult — or of you."
                ),
                "combat_npcs": [
                    {
                        "archetype": "bounty_hunter", "tier": "superior",
                        "species": "Human",
                        "name_pool": ["Hierophant of the Hollow Sun", "The Sun-Prophet"],
                        "weapon": "blaster_rifle", "behavior": "tactical",
                        "personality": "The Hierophant of the Hollow Sun — the cult's prophet, fanatical and lethal, making a last stand.",
                    },
                ],
            },
        ],
        "success_reward": {
            "credits": (700, 1400),
            "resources": [
                ("composite", 3, 60),
                ("metal", 2, 55),
                ("energy", 1, 55),
            ],
            "influence": TIER2_INFLUENCE_DELTA,
        },
        "news_text": (
            "The Hierophant of the Hollow Sun has been cornered at the cult's "
            "shrine in {region}. End the prophet and the cult breaks."
        ),
    },
}


# ── Anomaly dataclass + module-level transient state ─────────────────────────

@dataclass
class WildernessAnomaly:
    id: int
    region_slug: str
    zone_id: Optional[int]
    template_key: str
    anchor_room_id: int
    spawned_at: float = field(default_factory=time.time)
    expiry: float = field(default_factory=lambda: time.time() + TIER1_DURATION_SECS)
    resolved: bool = False
    resolved_by: Optional[int] = None     # char_id of resolver
    resolved_faction: Optional[str] = None  # faction_id of resolver
    # SYN.7.a.fix: combat-resolution support.
    # When resolution == "combat", investigate() spawns NPCs in the
    # anchor room and stores their npc_ids here. The kill hook in
    # parser/combat_commands.py awards the reward when the LAST one
    # dies. Empty list for skill-resolution anomalies.
    spawned_npc_ids: list = field(default_factory=list)
    # The character who triggered the combat (used to attribute the
    # reward if attribution from last_attacker_id is somehow missing).
    engaged_by: Optional[int] = None
    engaged_faction: Optional[str] = None
    # SYN.7.b: multi-phase combat support.
    # tier defaults to 1 for backward compat with SYN.7.a templates.
    # current_phase is 0-indexed; reflects the active phase of a
    # multi-phase combat anomaly. Tier 1 anomalies always have
    # current_phase=0 and a phase list of length 1.
    tier: int = 1
    current_phase: int = 0
    # SYN.8: Tier 3 participation tracking.
    # kill_counts maps char_id → number of anomaly NPCs that char
    # killed during the encounter. Populated by the kill hook in
    # parser/combat_commands.py. Used by Tier 3 payout to (1)
    # enumerate participants (anyone with kill_counts > 0) and (2)
    # rank them for the scaled T5 mat distribution (top floor(N/4)
    # by kill count).
    kill_counts: dict = field(default_factory=dict)

    @property
    def template(self) -> dict:
        # Look in all three tier catalogs + the staged-event scenario catalog.
        return (
            TIER1_TEMPLATES.get(self.template_key)
            or TIER2_TEMPLATES.get(self.template_key)
            or TIER3_TEMPLATES.get(self.template_key)
            or SCENARIO_TEMPLATES.get(self.template_key)
            or {}
        )

    @property
    def display_name(self) -> str:
        return self.template.get("display_name", self.template_key)

    @property
    def resolution_mode(self) -> str:
        """``skill`` or ``combat`` — defaults to skill if unset."""
        return self.template.get("resolution", "skill")

    @property
    def phases(self) -> list:
        """List of phase dicts for Tier 2 templates. Empty list for
        Tier 1 (single-phase / skill resolution)."""
        return self.template.get("phases", []) or []

    @property
    def total_phases(self) -> int:
        """1 for Tier 1 templates (legacy); len(phases) for T2/T3."""
        if self.tier >= 2 and self.phases:
            return len(self.phases)
        return 1

    @property
    def is_final_phase(self) -> bool:
        """True if the active phase is the last one."""
        return self.current_phase >= self.total_phases - 1

    def phase_skill_gate(self, phase_idx: int) -> "dict | None":
        """Return the skill_gate dict for a phase, or None if absent.

        T3.23 pre-launch seam: the ``skill_gate`` field is INERT until
        the post-launch engine build (Phase 1) wires the skill-check
        resolution. Existing combat-only phases are unaffected (no
        ``skill_gate`` key → this returns None). Callers must NOT act
        on the returned dict until Phase 1 ships.
        """
        phases = self.phases
        if not phases or phase_idx < 0 or phase_idx >= len(phases):
            return None
        return phases[phase_idx].get("skill_gate") or None

    def is_expired(self, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.time()
        return now >= self.expiry


# region_slug -> list[WildernessAnomaly]
_anomalies: dict[str, list[WildernessAnomaly]] = {}
# Global incrementing ID counter
_anomaly_counter: int = 0


def _next_id() -> int:
    """Allocate the next anomaly ID."""
    global _anomaly_counter
    _anomaly_counter += 1
    return _anomaly_counter


def _reset_state_for_tests() -> None:
    """Test helper: wipe all anomalies and reset the ID counter.

    Used by SYN.7.a tests to get a clean slate. NOT called in
    production paths.
    """
    global _anomaly_counter
    _anomalies.clear()
    _anomaly_counter = 0


# ── Pure helpers ─────────────────────────────────────────────────────────────

def _prune_expired_region(region_slug: str, now: Optional[float] = None) -> int:
    """Remove expired (or resolved-and-aged-out) anomalies from a region.

    Returns the count removed. Resolved anomalies linger briefly so
    the resolver's screen still shows them, then go away on the
    next prune pass.

    SYN.7.a.fix: when pruning an expired combat anomaly that still
    has live spawned NPCs, those NPCs are NOT deleted here — that's
    a DB-touching operation and this is a pure helper. The tick
    wrapper (``_prune_expired_region_with_cleanup``) handles NPC
    cleanup.
    """
    if now is None:
        now = time.time()
    existing = _anomalies.get(region_slug, [])
    fresh = [a for a in existing if not a.is_expired(now)]
    removed = len(existing) - len(fresh)
    _anomalies[region_slug] = fresh
    return removed


async def _prune_expired_region_with_cleanup(
    db, region_slug: str, now: Optional[float] = None,
) -> int:
    """DB-touching variant of ``_prune_expired_region`` that also
    deletes any still-alive NPCs from expired combat anomalies.

    Returns the count of anomalies removed (same shape as the pure
    helper). NPC deletion errors are logged but don't propagate.
    """
    if now is None:
        now = time.time()
    existing = _anomalies.get(region_slug, [])
    expired = [a for a in existing if a.is_expired(now)]
    # Pure prune first (mutates _anomalies).
    removed = _prune_expired_region(region_slug, now)
    # Then NPC cleanup for expired combat anomalies whose NPCs are
    # still alive in the world (player walked away, anomaly aged out).
    for a in expired:
        if not a.spawned_npc_ids:
            continue
        for npc_id in a.spawned_npc_ids:
            try:
                npc_row = await db.get_npc(int(npc_id))
                if npc_row is None:
                    continue  # already deleted (e.g. killed in combat)
                # Don't delete if the NPC is mid-combat with a player —
                # let the kill resolve naturally. We detect this by
                # checking that no character is in the same room.
                # Simpler: just delete. Combat substrate handles
                # missing NPCs gracefully (they fall out of the
                # combat dict on next tick).
                await db.delete_npc(int(npc_id))
                log.info(
                    "[anomaly] cleaned up NPC %s from expired anomaly #%d",
                    npc_id, a.id,
                )
            except Exception:
                log.warning(
                    "[anomaly] NPC cleanup failed for npc=%s anomaly=#%s",
                    npc_id, a.id, exc_info=True,
                )
    return removed


def _pick_template(rng: random.Random,
                   region_slug: Optional[str] = None,
                   tier: int = 1) -> Optional[str]:
    """Choose a template key uniformly at random, filtered to
    templates compatible with ``region_slug`` AND ``tier``.

    A template is compatible if ``region_slug`` is in its
    ``regions`` list, OR if its ``regions`` list contains the
    universal ``REGION_ANY`` token.

    SYN.7.b: ``tier`` selects between Tier 1 templates
    (TIER1_TEMPLATES, tier defaults to 1) and Tier 2 templates
    (TIER2_TEMPLATES, tier=2). Tiers do not mix — the Tier 1 tick
    only picks Tier 1 templates, and vice versa.

    SYN.8: extended to tier=3 (TIER3_TEMPLATES). Same disjoint
    selection — Tier 3 templates are world-boss events, picked only
    by the Tier 3 tick.

    Returns None if no template matches the region (which should not
    happen if every wilderness region has at least one tagged
    template — see SYN.7.a.fix test_every_known_region_has_templates).
    """
    if tier == 3:
        catalog = TIER3_TEMPLATES
    elif tier == 2:
        catalog = TIER2_TEMPLATES
    else:
        catalog = TIER1_TEMPLATES
    candidates = []
    for key, tmpl in catalog.items():
        regions = tmpl.get("regions", [])
        if region_slug is None:
            # Region-agnostic caller (e.g. legacy tests).
            candidates.append(key)
            continue
        if REGION_ANY in regions or region_slug in regions:
            candidates.append(key)
    if not candidates:
        return None
    return rng.choice(candidates)


def _format_news(template_key: str, region_slug: str) -> str:
    """Build the news-broadcast line for a fresh anomaly."""
    tmpl = (TIER1_TEMPLATES.get(template_key)
            or TIER2_TEMPLATES.get(template_key)
            or TIER3_TEMPLATES.get(template_key)
            or SCENARIO_TEMPLATES.get(template_key)
            or {})
    base = tmpl.get("news_text", "An anomaly has been reported in {region}.")
    region_label = region_slug.replace("_", " ").title()
    return base.replace("{region}", region_label)


def _sample_credits(rng: random.Random, band: tuple) -> int:
    """Sample an int from a (min, max) band uniformly."""
    lo, hi = band
    if hi <= lo:
        return int(lo)
    return rng.randint(int(lo), int(hi))


# ── Region enumeration + DB-touching helpers ─────────────────────────────────

async def _iter_wilderness_regions(db) -> list[str]:
    """Enumerate every distinct wilderness_region_id present in rooms.

    Mirrors engine.region_quality._iter_wilderness_regions. Used by
    the spawn tick to know which regions to roll for.
    """
    try:
        rows = await db.fetchall(
            "SELECT DISTINCT wilderness_region_id FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL "
            "  AND wilderness_region_id != ''"
        )
        return sorted({
            r["wilderness_region_id"] for r in rows
            if r["wilderness_region_id"]
        })
    except Exception:
        log.warning("[anomaly] region enumeration failed", exc_info=True)
        return []


async def _pick_anchor_room(
    db, region_slug: str, rng: random.Random,
) -> Optional[tuple[int, Optional[int]]]:
    """Pick a random room within ``region_slug`` to anchor a fresh
    anomaly. Returns ``(room_id, zone_id)`` or None if no rooms.

    Prefers landmark rooms (per ``engine.territory._get_region_landmarks``)
    so anomalies anchor at named locations rather than random tiles.
    Falls back to any room with the region_id if no landmark rooms.
    """
    try:
        from engine.territory import _get_region_landmarks
        landmark_ids = await _get_region_landmarks(db, region_slug)
    except Exception:
        log.warning("[anomaly] _get_region_landmarks failed",
                    exc_info=True)
        landmark_ids = []

    if not landmark_ids:
        # Fallback: any room with this wilderness_region_id
        try:
            rows = await db.fetchall(
                "SELECT id FROM rooms WHERE wilderness_region_id = ? "
                "ORDER BY id LIMIT 50",
                (region_slug,),
            )
            landmark_ids = [int(r["id"]) for r in rows]
        except Exception:
            log.warning("[anomaly] fallback room scan failed",
                        exc_info=True)
            return None

    if not landmark_ids:
        return None

    room_id = rng.choice(landmark_ids)

    # Look up zone_id for influence routing
    try:
        room = await db.get_room(room_id)
        zone_id = int(room["zone_id"]) if room and room.get("zone_id") else None
    except Exception:
        zone_id = None

    return (int(room_id), zone_id)


# ── Spawn + tick ─────────────────────────────────────────────────────────────

async def spawn_anomaly_for_region(
    db, region_slug: str, *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
    session_mgr=None,
    force: bool = False,
    tier: int = 1,
) -> Optional[WildernessAnomaly]:
    """Attempt to spawn a single anomaly of the requested ``tier`` in
    ``region_slug``.

    Returns the WildernessAnomaly on success, None on no-spawn
    (capped out, rolled below threshold, no anchor room, or no
    template matches the region).

    SYN.7.b: ``tier`` selects between Tier 1 (default) and Tier 2.
    Tier 1 uses MAX_PER_REGION / SPAWN_CHANCE_PER_TICK /
    TIER1_DURATION_SECS. Tier 2 uses TIER2_MAX_PER_REGION /
    TIER2_SPAWN_CHANCE_PER_TICK / TIER2_DURATION_SECS. The tier
    cap is counted separately — a region can hold Tier 1 anomalies
    AND a Tier 2 anomaly at the same time without conflict.

    SYN.8: ``tier=3`` extends with TIER3_* constants (daily tick,
    0.10 chance → ~10-day avg per region; 8h duration; cap 1).
    All three tiers' caps are counted separately.

    ``force=True`` bypasses the spawn-chance check (used by tests
    + admin tools).
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    if tier == 3:
        per_region_cap = TIER3_MAX_PER_REGION
        spawn_chance = TIER3_SPAWN_CHANCE_PER_TICK
        duration = TIER3_DURATION_SECS
    elif tier == 2:
        per_region_cap = TIER2_MAX_PER_REGION
        spawn_chance = TIER2_SPAWN_CHANCE_PER_TICK
        duration = TIER2_DURATION_SECS
    else:
        per_region_cap = MAX_PER_REGION
        spawn_chance = SPAWN_CHANCE_PER_TICK
        duration = TIER1_DURATION_SECS

    _prune_expired_region(region_slug, now)
    existing_same_tier = [
        a for a in _anomalies.get(region_slug, []) if a.tier == tier
    ]
    if len(existing_same_tier) >= per_region_cap:
        return None

    if not force and rng.random() > spawn_chance:
        return None

    template_key = _pick_template(rng, region_slug=region_slug, tier=tier)
    if template_key is None:
        # No template tagged for this region + tier. Log once at
        # info; not an error.
        log.info(
            "[anomaly] no tier-%d templates registered for region '%s'",
            tier, region_slug,
        )
        return None

    anchor = await _pick_anchor_room(db, region_slug, rng)
    if not anchor:
        return None
    room_id, zone_id = anchor

    anomaly = WildernessAnomaly(
        id=_next_id(),
        region_slug=region_slug,
        zone_id=zone_id,
        template_key=template_key,
        anchor_room_id=room_id,
        spawned_at=now,
        expiry=now + duration,
        tier=tier,
    )
    _anomalies.setdefault(region_slug, []).append(anomaly)

    log.info("[anomaly] spawned T%d #%d (%s) in %s at room %d",
             tier, anomaly.id, template_key, region_slug, room_id)

    # Broadcast news (best-effort)
    if session_mgr is not None:
        try:
            news = _format_news(template_key, region_slug)
            await session_mgr.broadcast(f"\n  \033[1;33m[News] {news}\033[0m")
        except Exception:
            log.warning("[anomaly] news broadcast failed", exc_info=True)

    return anomaly


async def spawn_scenario_anomaly(
    db, region_slug: str, template_key: str, anchor_room_id: int,
    *,
    tier: int = 1,
    zone_id: Optional[int] = None,
    duration_secs: Optional[float] = None,
    now: Optional[float] = None,
    session_mgr=None,
) -> Optional[WildernessAnomaly]:
    """Spawn a SPECIFIC authored anomaly at a SPECIFIC room — the
    deterministic counterpart to ``spawn_anomaly_for_region``.

    Used by the staged-event scenario orchestrator
    (engine.communal_objective_runtime) to arm one stage's anomaly at the
    scenario site. Unlike the random tick spawner, the caller names the
    template + anchor room explicitly, so a cult scenario walks a curated
    sequence (wave → skill → boss) rather than a random roll. The resulting
    WildernessAnomaly is identical in every other respect — it resolves through
    the SAME ``investigate`` → ``_resolve_anomaly_*`` paths and pays through the
    SAME reward funnels as any other anomaly (no new faucet/sink).

    Returns the WildernessAnomaly, or None if the template is unknown. Does NOT
    enforce per-region caps or spawn-chance (scenarios are orchestrator-driven,
    not tick-rolled).
    """
    if now is None:
        now = time.time()

    tmpl = (
        SCENARIO_TEMPLATES.get(template_key)
        or TIER1_TEMPLATES.get(template_key)
        or TIER2_TEMPLATES.get(template_key)
        or TIER3_TEMPLATES.get(template_key)
    )
    if tmpl is None:
        log.warning("[anomaly] spawn_scenario_anomaly: unknown template '%s'",
                    template_key)
        return None

    if zone_id is None:
        try:
            room = await db.get_room(int(anchor_room_id))
            zone_id = int(room["zone_id"]) if room and room.get("zone_id") else None
        except Exception:
            zone_id = None

    if duration_secs is None:
        # Scenario stages get a generous window so a small group can travel +
        # coordinate; mirror the Tier-2 duration band for the multi-phase
        # stages, the Tier-1 band for the one-shot skill stage.
        duration_secs = TIER2_DURATION_SECS if tier >= 2 else TIER1_DURATION_SECS

    anomaly = WildernessAnomaly(
        id=_next_id(),
        region_slug=region_slug,
        zone_id=zone_id,
        template_key=template_key,
        anchor_room_id=int(anchor_room_id),
        spawned_at=now,
        expiry=now + float(duration_secs),
        tier=int(tier),
    )
    _anomalies.setdefault(region_slug, []).append(anomaly)

    log.info(
        "[anomaly] spawned SCENARIO T%d #%d (%s) in %s at room %d",
        tier, anomaly.id, template_key, region_slug, anchor_room_id,
    )

    if session_mgr is not None:
        try:
            news = _format_news(template_key, region_slug)
            await session_mgr.broadcast(f"\n  \033[1;33m[News] {news}\033[0m")
        except Exception:
            log.warning("[anomaly] scenario news broadcast failed",
                        exc_info=True)

    return anomaly


async def tick_wilderness_anomalies(
    db, session_mgr=None,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict:
    """Periodic tick: prune expired anomalies + roll spawn for each
    wilderness region.

    Returns a stats dict ``{"pruned": int, "spawned": int}`` for
    observability + tests.

    Called every CADENCE_TICK_INTERVAL seconds from the scheduler.

    SYN.7.a.fix: the prune step now uses the DB-touching variant
    that also cleans up surviving NPCs from expired combat anomalies.
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    regions = await _iter_wilderness_regions(db)
    pruned_total = 0
    spawned_total = 0

    for slug in regions:
        try:
            pruned_total += await _prune_expired_region_with_cleanup(
                db, slug, now,
            )
        except Exception:
            log.warning("[anomaly] prune failed for %s", slug, exc_info=True)
            continue
        try:
            result = await spawn_anomaly_for_region(
                db, slug, rng=rng, now=now, session_mgr=session_mgr,
            )
            if result is not None:
                spawned_total += 1
        except Exception:
            log.warning("[anomaly] spawn failed for %s", slug, exc_info=True)
            continue

    if spawned_total > 0 or pruned_total > 0:
        log.info("[anomaly] tick: pruned %d, spawned %d",
                 pruned_total, spawned_total)

    return {"pruned": pruned_total, "spawned": spawned_total}


async def tick_tier2_wilderness_anomalies(
    db, session_mgr=None,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict:
    """Periodic Tier 2 tick: roll spawn for each wilderness region
    at the Tier 2 cadence.

    Separate tick from Tier 1 because:
      * Tier 2 has its own cadence (TIER2_CADENCE_TICK_INTERVAL =
        6h vs Tier 1's 1h).
      * Tier 2 has its own per-region cap (1 vs Tier 1's 2).
      * Tier 2 has its own duration (2h vs Tier 1's 30 min).

    Both ticks share the prune helper (`_prune_expired_region_with_cleanup`)
    which handles all anomalies regardless of tier.

    SYN.7.b: registered alongside Tier 1 tick in
    `server/game_server.py` with offset so they don't collide.
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    regions = await _iter_wilderness_regions(db)
    pruned_total = 0
    spawned_total = 0

    for slug in regions:
        try:
            pruned_total += await _prune_expired_region_with_cleanup(
                db, slug, now,
            )
        except Exception:
            log.warning(
                "[anomaly t2] prune failed for %s", slug, exc_info=True,
            )
            continue
        try:
            result = await spawn_anomaly_for_region(
                db, slug, rng=rng, now=now, session_mgr=session_mgr,
                tier=2,
            )
            if result is not None:
                spawned_total += 1
        except Exception:
            log.warning(
                "[anomaly t2] spawn failed for %s", slug, exc_info=True,
            )
            continue

    if spawned_total > 0 or pruned_total > 0:
        log.info("[anomaly t2] tick: pruned %d, spawned %d",
                 pruned_total, spawned_total)

    return {"pruned": pruned_total, "spawned": spawned_total}


async def tick_tier3_wilderness_anomalies(
    db, session_mgr=None,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict:
    """Periodic Tier 3 tick: roll spawn for each wilderness region
    at the Tier 3 cadence (world-boss events).

    Separate tick from Tier 1 and Tier 2:
      * Daily check (TIER3_CADENCE_TICK_INTERVAL = 24h) with 0.10
        spawn-chance → ~10-day avg per region (midpoint of design's
        7-14d).
      * Per-region cap 1 (Tier 3 is THE world event).
      * 8-hour duration (mid of design's 6-12h band).
      * Three tiers' caps are independent — a region can have a T1 +
        T2 + T3 anomaly all active.

    SYN.8: registered in `server/game_server.py` with interval=86400
    (24h), offset=7200 to avoid collision with T1 (offset=1500) +
    T2 (offset=3300).

    Future: during-contest 2× cadence is a design call deferred to
    a post-launch polish drop — needs a way to ask "is this region
    actively contested?" without coupling to engine.contest internals.
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    regions = await _iter_wilderness_regions(db)
    pruned_total = 0
    spawned_total = 0

    for slug in regions:
        try:
            pruned_total += await _prune_expired_region_with_cleanup(
                db, slug, now,
            )
        except Exception:
            log.warning(
                "[anomaly t3] prune failed for %s", slug, exc_info=True,
            )
            continue
        try:
            result = await spawn_anomaly_for_region(
                db, slug, rng=rng, now=now, session_mgr=session_mgr,
                tier=3,
            )
            if result is not None:
                spawned_total += 1
        except Exception:
            log.warning(
                "[anomaly t3] spawn failed for %s", slug, exc_info=True,
            )
            continue

    if spawned_total > 0 or pruned_total > 0:
        log.info("[anomaly t3] tick: pruned %d, spawned %d",
                 pruned_total, spawned_total)

    return {"pruned": pruned_total, "spawned": spawned_total}


# ── Listing + resolution ─────────────────────────────────────────────────────

def get_anomalies_for_region(
    region_slug: str, *, now: Optional[float] = None,
) -> list[WildernessAnomaly]:
    """Return active (non-expired, non-resolved) anomalies in a region."""
    _prune_expired_region(region_slug, now)
    return [a for a in _anomalies.get(region_slug, [])
            if not a.resolved]


def get_anomaly_by_id(
    region_slug: str, anomaly_id: int,
) -> Optional[WildernessAnomaly]:
    """Look up a specific anomaly by ID within a region."""
    for a in _anomalies.get(region_slug, []):
        if a.id == anomaly_id:
            return a
    return None


def find_anomaly_globally(anomaly_id: int) -> Optional[WildernessAnomaly]:
    """Look up an anomaly by ID without knowing its region.

    Used by the combat-death hook in ``parser/combat_commands.py``:
    we know the ``anomaly_id`` from the dying NPC's ai_config_json,
    but the player might have wandered out of the region by the
    time the killing blow lands.
    """
    for region_anomalies in _anomalies.values():
        for a in region_anomalies:
            if a.id == int(anomaly_id):
                return a
    return None


async def resolve_anomaly(
    db, char: dict, anomaly_id: int,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict:
    """Player runs ``investigate <id>``.

    Dispatches to ``_resolve_anomaly_skill`` or ``_resolve_anomaly_combat``
    based on the template's ``resolution`` mode.

    Returns the same result dict shape as before for both paths;
    combat-mode results have ``mode="combat"`` and indicate that
    NPCs were spawned (the reward fires later, on kill).
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    # ── Common gating: room/region/anomaly lookup + anchor match ─────────
    gate = await _gate_investigate(db, char, anomaly_id)
    if "fail_result" in gate:
        return gate["fail_result"]
    anomaly = gate["anomaly"]
    region_slug = gate["region_slug"]

    # Dispatch on resolution mode
    if anomaly.resolution_mode == "combat":
        return await _resolve_anomaly_combat(
            db, char, anomaly, region_slug, now=now,
        )
    else:
        return await _resolve_anomaly_skill(
            db, char, anomaly, region_slug, rng=rng, now=now,
        )


async def _gate_investigate(db, char: dict, anomaly_id) -> dict:
    """Common pre-resolution checks. Returns either
    ``{"fail_result": ...}`` or ``{"anomaly": ..., "region_slug": ...}``.
    """
    room_id = char.get("room_id")
    if not room_id:
        return {"fail_result": _fail_result(
            "You are nowhere any anomaly could be."
        )}
    try:
        from engine.territory import _resolve_room_region
        region_slug, _zid = await _resolve_room_region(db, int(room_id))
    except Exception:
        log.warning("[anomaly] _resolve_room_region failed", exc_info=True)
        region_slug = None
    if not region_slug:
        return {"fail_result": _fail_result(
            "You aren't in a wilderness region. Anomalies appear in the wild."
        )}

    try:
        anomaly_id_int = int(anomaly_id)
    except (ValueError, TypeError):
        return {"fail_result": _fail_result(
            f"'{anomaly_id}' is not a valid anomaly id."
        )}

    anomaly = get_anomaly_by_id(region_slug, anomaly_id_int)
    if anomaly is None:
        return {"fail_result": _fail_result(
            f"No anomaly #{anomaly_id_int} active in this region. "
            f"(Check 'anomalies' for the current list.)"
        )}

    if anomaly.resolved:
        return {"fail_result": _fail_result(
            "That anomaly was already resolved by another character."
        )}

    if int(room_id) != int(anomaly.anchor_room_id):
        return {"fail_result": _fail_result(
            f"You can see the {anomaly.display_name} from here, but you "
            f"need to be at the site itself to act on it."
        )}

    return {"anomaly": anomaly, "region_slug": region_slug}


async def _resolve_anomaly_skill(
    db, char: dict, anomaly: "WildernessAnomaly",
    region_slug: str,
    *,
    rng: random.Random,
    now: float,
) -> dict:
    """Skill-check resolution path. One-shot: success → full reward,
    failure → partial reward. Anomaly resolved either way."""
    tmpl = anomaly.template
    primary = tmpl.get("primary_skill", "survival")
    secondary = tmpl.get("secondary_skill")
    skill_to_use = _pick_better_skill(char, primary, secondary)

    from engine.skill_checks import perform_skill_check
    try:
        sc = perform_skill_check(char, skill_to_use, TIER1_RESOLUTION_DC)
    except Exception:
        log.warning("[anomaly] skill check raised", exc_info=True)
        return _fail_result("Something disrupts your effort. Try again.")

    reward = (tmpl.get("success_reward") if sc.success
              else tmpl.get("fail_reward")) or {}
    credits, granted_stacks, influence_delta = await _apply_reward_to_char(
        db, char, anomaly, region_slug, reward, rng,
    )

    # Mark resolved
    anomaly.resolved = True
    anomaly.resolved_by = int(char.get("id", 0))
    anomaly.resolved_faction = char.get("faction_id") or "independent"
    anomaly.expiry = min(anomaly.expiry, now + 30)

    if sc.success:
        msg = (f"You resolve the {anomaly.display_name}. "
                f"{credits:,}cr earned"
                + (f", +{influence_delta} inf to your faction."
                   if influence_delta and anomaly.resolved_faction != "independent"
                   else "."))
    else:
        msg = (f"You only partially succeed at the {anomaly.display_name}. "
                f"{credits:,}cr earned.")

    log.info(
        "[anomaly] resolved #%d (%s, skill) by char %s — %s, %dcr",
        anomaly.id, anomaly.template_key, char.get("name", "?"),
        "success" if sc.success else "partial", credits,
    )

    return {
        "ok": True,
        "mode": "skill",
        "msg": msg,
        "credits": credits,
        "resources": granted_stacks,
        "influence": (influence_delta
                      if (sc.success and anomaly.resolved_faction != "independent")
                      else 0),
        "skill_used": skill_to_use,
        "skill_roll": sc.roll,
        "margin": sc.margin,
        "success": sc.success,
    }


async def _resolve_anomaly_combat(
    db, char: dict, anomaly: "WildernessAnomaly",
    region_slug: str,
    *,
    now: float,
) -> dict:
    """Combat resolution path. Spawn NPCs in the anchor room and
    record their ids on the anomaly. The reward fires later, via
    ``award_combat_anomaly_reward``, when the LAST tagged NPC dies.

    SYN.7.b: For Tier 2 multi-phase templates, spawns ONLY the
    first phase's NPCs. Subsequent phases spawn from the kill
    hook (`_advance_to_next_phase`) when the previous phase's
    last hostile dies.
    """
    if anomaly.spawned_npc_ids:
        # Player already triggered this anomaly. Surface a hint
        # rather than re-spawning.
        return {
            "ok": False,
            "mode": "combat",
            "msg": (f"You've already engaged the {anomaly.display_name}. "
                    f"Finish what you started."),
            "credits": 0,
            "resources": [],
            "influence": 0,
            "skill_used": "",
            "skill_roll": 0,
            "margin": 0,
            "success": False,
        }

    tmpl = anomaly.template

    # SYN.7.b: pick the right NPC spec list based on tier.
    # SYN.8: tier 3 uses the same multi-phase mechanism.
    if anomaly.tier >= 2 and anomaly.phases:
        # Multi-phase (T2 or T3): spawn phase 0 only.
        npc_specs = anomaly.phases[0].get("combat_npcs", []) or []
        phase_intro = anomaly.phases[0].get("intro", "")
    else:
        # Tier 1 (single phase, single combat_npcs list).
        npc_specs = tmpl.get("combat_npcs", []) or []
        phase_intro = ""

    if not npc_specs:
        log.warning(
            "[anomaly] combat template '%s' has no combat_npcs / phases[0]",
            anomaly.template_key,
        )
        return _fail_result(
            f"The {anomaly.display_name} is not properly configured."
        )

    spawned_ids = await _spawn_combat_npcs(
        db, anomaly, npc_specs,
    )

    if not spawned_ids:
        return _fail_result(
            f"The hostiles for the {anomaly.display_name} did not "
            f"materialize. Try again, or check the server logs."
        )

    # Record on the anomaly.
    anomaly.spawned_npc_ids = spawned_ids
    anomaly.engaged_by = int(char.get("id", 0))
    anomaly.engaged_faction = char.get("faction_id") or "independent"
    anomaly.current_phase = 0

    npc_count = len(spawned_ids)
    if anomaly.tier >= 2:
        tier_label = "Tier 3 world boss" if anomaly.tier == 3 else f"Phase 1 of {anomaly.total_phases}"
        if anomaly.tier == 3:
            msg = (f"You engage the {anomaly.display_name} — "
                   f"a {tier_label}, Phase 1 of {anomaly.total_phases}. "
                   f"{npc_count} {'hostile' if npc_count == 1 else 'hostiles'} "
                   f"on you. This is going to take a war-band.")
        else:
            msg = (f"You engage the {anomaly.display_name} — "
                   f"{tier_label}. "
                   f"{npc_count} {'hostile' if npc_count == 1 else 'hostiles'} "
                   f"on you.")
    else:
        msg = (f"You move on the {anomaly.display_name}. "
               f"{npc_count} {'hostile' if npc_count == 1 else 'hostiles'} "
               f"engage. Reward will be paid out when the threat is down.")

    log.info(
        "[anomaly] combat engaged for T%d #%d (%s) by char %s — "
        "phase %d spawned %d NPCs",
        anomaly.tier, anomaly.id, anomaly.template_key,
        char.get("name", "?"), anomaly.current_phase + 1, npc_count,
    )

    return {
        "ok": True,
        "mode": "combat",
        "msg": msg,
        "credits": 0,
        "resources": [],
        "influence": 0,
        "skill_used": "",
        "skill_roll": 0,
        "margin": 0,
        "success": False,    # not yet
        "spawned_npc_ids": list(spawned_ids),
        "long_desc": tmpl.get("long_desc", ""),
        "phase_intro": phase_intro,
        "tier": anomaly.tier,
        "phase": 1,                       # human-1-indexed for display
        "total_phases": anomaly.total_phases,
    }


async def _spawn_combat_npcs(
    db, anomaly: "WildernessAnomaly", npc_specs: list,
) -> list:
    """Spawn the given list of NPC specs in the anomaly's anchor
    room, tagging each with is_anomaly_target + anomaly_id. Returns
    the list of created NPC ids.

    Extracted as a helper so both `_resolve_anomaly_combat` (initial
    engagement / phase 0) and `_advance_to_next_phase` (later phases
    in Tier 2 multi-phase combat) use the same code path.
    """
    try:
        from engine.npc_generator import generate_npc
        from engine.npc_combat_ai import (
            DEFAULT_ARCHETYPE_WEAPONS,
            DEFAULT_ARCHETYPE_BEHAVIOR,
        )
        from ai.npc_brain import NPCConfig
    except Exception:
        log.exception("[anomaly] failed to import NPC generator + AI helpers")
        return []

    spawned_ids = []
    for idx, spec in enumerate(npc_specs):
        archetype = spec.get("archetype", "thug")
        tier_str = spec.get("tier", "average")
        species = spec.get("species", "Human")
        name_pool = spec.get("name_pool", [None])
        name = name_pool[idx % len(name_pool)] or f"Hostile {idx+1}"
        weapon_key = spec.get("weapon") or DEFAULT_ARCHETYPE_WEAPONS.get(
            archetype, "blaster_pistol"
        )
        behavior = spec.get("behavior") or DEFAULT_ARCHETYPE_BEHAVIOR.get(
            archetype, "aggressive"
        )
        personality = spec.get("personality", "")

        try:
            npc_data = generate_npc(tier_str, archetype, species=species,
                                    name=name)
        except Exception:
            log.warning(
                "[anomaly] generate_npc failed (archetype=%s tier=%s)",
                archetype, tier_str, exc_info=True,
            )
            continue

        npc_data["weapon"] = weapon_key

        try:
            ai_cfg = NPCConfig(
                personality=personality,
                fallback_lines=[
                    f"{name} watches you, weapon ready.",
                    f"{name} circles, looking for an opening.",
                    f"{name} says nothing.",
                ],
            ).to_dict()
        except Exception:
            ai_cfg = {"personality": personality, "fallback_lines": []}

        ai_cfg["hostile"] = True
        ai_cfg["combat_behavior"] = behavior
        ai_cfg["weapon"] = weapon_key
        ai_cfg["is_anomaly_target"] = True
        ai_cfg["anomaly_id"] = anomaly.id

        try:
            npc_id = await db.create_npc(
                name=name,
                room_id=int(anomaly.anchor_room_id),
                species=species,
                description=spec.get("description", ""),
                char_sheet_json=json.dumps(npc_data),
                ai_config_json=json.dumps(ai_cfg),
            )
            spawned_ids.append(int(npc_id))
        except Exception:
            log.warning(
                "[anomaly] create_npc failed for spec %d", idx,
                exc_info=True,
            )
            continue
    return spawned_ids


async def _advance_to_next_phase(
    db, anomaly: "WildernessAnomaly", session_mgr=None,
) -> bool:
    """Tier 2/3 only: advance the anomaly to the next phase.

    Spawns the next phase's NPCs and records them on the anomaly.
    Returns True if a phase was advanced, False if this was already
    the final phase (caller should fire reward instead).

    Best-effort: if NPC spawn fails for the next phase, the anomaly
    is marked resolved (we can't soft-fail the encounter mid-flight).

    SYN.8: tier=3 reuses the same machinery. The narrative
    "relocation" between phases (e.g. krayt withdraws and re-emerges)
    is conveyed via the phase intro string broadcast to the room.
    """
    if anomaly.tier < 2:
        return False
    if anomaly.is_final_phase:
        return False
    next_idx = anomaly.current_phase + 1
    if next_idx >= len(anomaly.phases):
        return False

    next_phase = anomaly.phases[next_idx]
    npc_specs = next_phase.get("combat_npcs", []) or []
    if not npc_specs:
        if next_phase.get("skill_gate"):
            # T3.23 pre-launch: skill_gate phases are INERT; the post-launch
            # engine build (Phase 1) will wire skill-check resolution here.
            log.info(
                "[anomaly] phase %d of '%s' has skill_gate (T3.23 inert seam) "
                "— no combat_npcs; skipping phase advance",
                next_idx, anomaly.template_key,
            )
        else:
            log.warning(
                "[anomaly] phase %d of '%s' has no combat_npcs",
                next_idx, anomaly.template_key,
            )
        return False

    spawned = await _spawn_combat_npcs(db, anomaly, npc_specs)
    if not spawned:
        log.warning(
            "[anomaly] phase %d of '%s' failed to spawn NPCs — "
            "marking anomaly resolved to avoid stuck state",
            next_idx, anomaly.template_key,
        )
        return False

    anomaly.spawned_npc_ids = spawned
    anomaly.current_phase = next_idx

    log.info(
        "[anomaly] T2 #%d advanced to phase %d/%d (%s) — %d NPCs",
        anomaly.id, next_idx + 1, anomaly.total_phases,
        next_phase.get("name", "?"), len(spawned),
    )

    # Surface the phase intro to anyone in the anchor room.
    if session_mgr is not None:
        try:
            intro = next_phase.get("intro", "")
            if intro:
                from engine.session_manager import (
                    notify_room as _notify_room,
                )
            notify = getattr(session_mgr, "broadcast_to_room", None)
            if notify and intro:
                await notify(
                    int(anomaly.anchor_room_id),
                    f"\n  \033[1;33m[Phase {next_idx + 1}/{anomaly.total_phases}]\033[0m "
                    f"{intro}",
                )
        except Exception:
            log.warning("[anomaly] phase-intro broadcast failed",
                        exc_info=True)
    return True


async def _apply_reward_to_char(
    db, char: dict, anomaly: "WildernessAnomaly",
    region_slug: str, reward: dict, rng: random.Random,
) -> tuple[int, list, int]:
    """Apply a reward dict to a character. Returns
    ``(credits_awarded, granted_resource_stacks, influence_delta_applied)``.

    Influence is +5 only if the character has a faction AND the
    reward dict says so AND the anomaly has a zone_id.
    """
    credits = _sample_credits(rng, reward.get("credits", (0, 0)))
    resource_grants = reward.get("resources", []) or []
    influence_delta = int(reward.get("influence", 0))

    if credits > 0:
        try:
            char["credits"] = await db.adjust_credits(char["id"], credits, "wilderness_anomaly_reward")
        except Exception:
            log.warning("[anomaly] credits save failed", exc_info=True)

    granted_stacks = []
    if resource_grants:
        try:
            from engine.crafting import add_resource
            for (rtype, qty, qual) in resource_grants:
                add_resource(char, rtype, qty, float(qual))
                granted_stacks.append({
                    "type": rtype, "quantity": qty, "quality": float(qual),
                })
            await db.save_character(char["id"], inventory=char["inventory"])
        except Exception:
            log.warning("[anomaly] resource grant failed", exc_info=True)

    faction_id = char.get("faction_id") or "independent"
    if (influence_delta > 0
            and faction_id != "independent"
            and anomaly.zone_id is not None):
        try:
            from engine.territory import adjust_territory_influence
            await adjust_territory_influence(
                db, faction_id, anomaly.zone_id,
                influence_delta,
                reason=f"anomaly:{anomaly.template_key}",
                region_slug=region_slug,
            )
        except Exception:
            log.warning("[anomaly] influence adjust failed", exc_info=True)
            influence_delta = 0
    else:
        # No faction or no zone or no delta requested.
        influence_delta = (influence_delta
                           if faction_id != "independent"
                              and anomaly.zone_id is not None
                           else 0)

    return credits, granted_stacks, influence_delta


# ── Combat-anomaly kill hook ─────────────────────────────────────────────────

async def award_combat_anomaly_reward(
    db, killer_char_id: int, npc_id: int,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
    session_mgr=None,
) -> Optional[dict]:
    """Called from ``parser/combat_commands.py`` when an NPC tagged
    with ``is_anomaly_target`` dies.

    Tier 1 (single-phase): when the LAST tagged NPC dies, award
    full reward to the killer + mark resolved.

    Tier 2 (multi-phase): when the last NPC of the CURRENT phase
    dies, check for a next phase. If yes, advance to it (spawn next
    wave) and return None (no payout yet). If no, pay all room
    occupants (credits/resources) + the killer gets influence +
    named loot.

    Returns the reward summary dict on payout (final clear), None if
    the kill was for a non-final NPC (still hostiles up, or phase
    advanced).
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    # Look up the dying NPC to read ai_config_json.
    try:
        npc_row = await db.get_npc(int(npc_id))
    except Exception:
        log.warning("[anomaly] get_npc failed in kill hook", exc_info=True)
        return None
    if npc_row is None:
        return None

    try:
        ai_cfg = json.loads(npc_row.get("ai_config_json") or "{}")
    except Exception:
        ai_cfg = {}
    if not ai_cfg.get("is_anomaly_target"):
        return None

    anomaly_id = ai_cfg.get("anomaly_id")
    if anomaly_id is None:
        return None
    anomaly = find_anomaly_globally(int(anomaly_id))
    if anomaly is None:
        # Anomaly aged out before the kill. Don't pay.
        log.info(
            "[anomaly] kill hook fired but anomaly #%s no longer active",
            anomaly_id,
        )
        return None
    if anomaly.resolved:
        return None

    # SYN.8: track per-character kill counts for Tier 3
    # participation-scaled rewards. Cheap to maintain for all tiers;
    # only consumed by the Tier 3 payout branch.
    try:
        kid = int(killer_char_id)
        anomaly.kill_counts[kid] = (
            int(anomaly.kill_counts.get(kid, 0)) + 1
        )
    except Exception:
        log.warning("[anomaly] kill_counts update failed", exc_info=True)

    # Decrement the live-NPC list.
    try:
        anomaly.spawned_npc_ids = [
            n for n in anomaly.spawned_npc_ids if int(n) != int(npc_id)
        ]
    except Exception:
        log.warning("[anomaly] npc list update failed", exc_info=True)

    # Hostiles remain in the current phase?
    if anomaly.spawned_npc_ids:
        log.info(
            "[anomaly] partial clear on T%d #%d phase %d (%d hostiles remain)",
            anomaly.tier, anomaly.id, anomaly.current_phase + 1,
            len(anomaly.spawned_npc_ids),
        )
        return None

    # ── Phase cleared. Tier 2/3: advance to next phase if not final. ──
    if anomaly.tier >= 2 and not anomaly.is_final_phase:
        advanced = await _advance_to_next_phase(
            db, anomaly, session_mgr=session_mgr,
        )
        if advanced:
            return None  # No payout yet — next phase active.
        # advance failed; fall through and treat as final clear so
        # players don't get stuck without a payout.

    # ── Final phase cleared. Pay out. ──
    return await _payout_combat_anomaly(
        db, anomaly, killer_char_id, rng, now,
        session_mgr=session_mgr,
    )


async def _payout_combat_anomaly(
    db, anomaly: "WildernessAnomaly", killer_char_id: int,
    rng: random.Random, now: float,
    *,
    session_mgr=None,
) -> Optional[dict]:
    """Final-clear payout for a combat anomaly.

    Tier 1: pay killer credits + resources + influence (no named loot).
    Tier 2: pay all room occupants credits/resources; killer alone
            gets influence + named loot.
    Tier 3: pay all participants (anyone who killed an anomaly NPC
            during the encounter) credits/resources + a per-participant
            trophy item; killer's faction gets influence; top-
            floor(N/4) participants by kill count get scaled T5 mat
            pieces.

    Returns the payout summary dict.
    """
    try:
        killer = await db.get_character(int(killer_char_id))
    except Exception:
        log.warning("[anomaly] killer lookup failed", exc_info=True)
        return None
    if killer is None:
        return None

    tmpl = anomaly.template
    reward = tmpl.get("success_reward") or {}

    # Tier 1: simple — single-character payout.
    if anomaly.tier == 1:
        credits, granted_stacks, influence_delta = (
            await _apply_reward_to_char(
                db, killer, anomaly, anomaly.region_slug, reward, rng,
            )
        )
        anomaly.resolved = True
        anomaly.resolved_by = int(killer_char_id)
        anomaly.resolved_faction = killer.get("faction_id") or "independent"
        anomaly.expiry = min(anomaly.expiry, now + 30)

        log.info(
            "[anomaly] T1 combat reward paid for #%d (%s) to char %s — "
            "%dcr, %d stacks, %d inf",
            anomaly.id, anomaly.template_key, killer_char_id,
            credits, len(granted_stacks), influence_delta,
        )

        # SYN.10 (May 25 2026): defeat news broadcast per design §2.6.
        await _broadcast_anomaly_defeat(
            anomaly, killer.get("faction_id"), session_mgr,
        )

        return {
            "anomaly_id": anomaly.id,
            "template_key": anomaly.template_key,
            "display_name": anomaly.display_name,
            "tier": 1,
            "credits": credits,
            "resources": granted_stacks,
            "influence": influence_delta,
            "named_loot": None,
            "participants": [int(killer_char_id)],
        }

    # ── Tier 2 + Tier 3: multi-participant payout. ──
    # SYN.8: Tier 3 uses anomaly.kill_counts.keys() as participants
    # (anyone who killed an anomaly NPC). Tier 2 uses room occupants
    # at clear time (legacy behavior — kill_counts not consulted).
    if anomaly.tier == 3:
        # Tier 3 participants: union of anyone who got a kill.
        participant_ids = list(anomaly.kill_counts.keys())
        # Defensive: the killer should always be in this set (they
        # just landed the killing blow), but include them if somehow
        # not.
        if int(killer_char_id) not in participant_ids:
            participant_ids.append(int(killer_char_id))
        participants = []
        for cid in participant_ids:
            try:
                c = await db.get_character(int(cid))
            except Exception:
                c = None
            if c:
                participants.append(dict(c))
    else:
        # Tier 2: enumerate room at clear time.
        try:
            room_chars = await db.get_characters_in_room(
                int(anomaly.anchor_room_id)
            )
        except Exception:
            log.warning(
                "[anomaly] get_characters_in_room failed for T2 payout",
                exc_info=True,
            )
            room_chars = []

        participants = []
        seen = set()
        for c in (room_chars or []):
            cid = int(c.get("id", 0))
            if cid == 0 or cid in seen:
                continue
            seen.add(cid)
            participants.append(dict(c))
        if int(killer_char_id) not in seen:
            participants.append(dict(killer))

    # Sample one credits + resources reward to split across
    # participants (each participant gets their share).
    base_credits = _sample_credits(rng, reward.get("credits", (0, 0)))
    base_resources = reward.get("resources", []) or []
    influence_delta = int(reward.get("influence", 0))
    named_loot = tmpl.get("named_loot")
    trophy_def = tmpl.get("trophy_per_participant")     # T3 only
    scaled_t5_def = tmpl.get("scaled_t5_mat")           # T3 only

    n_participants = max(1, len(participants))
    per_credits = base_credits // n_participants

    payouts_per_char = []
    for p in participants:
        granted_stacks = []
        granted_trophy = None
        # Credits — equal split.
        try:
            p["credits"] = await db.adjust_credits(p["id"], per_credits, "wilderness_anomaly_reward")
        except Exception:
            log.warning("[anomaly] credits save failed (char %s)",
                        p.get("id"), exc_info=True)

        # Resources — each participant gets the full resource list.
        if base_resources:
            try:
                from engine.crafting import add_resource
                for (rtype, qty, qual) in base_resources:
                    add_resource(p, rtype, qty, float(qual))
                    granted_stacks.append({
                        "type": rtype, "quantity": qty,
                        "quality": float(qual),
                    })
                await db.save_character(p["id"], inventory=p["inventory"])
            except Exception:
                log.warning("[anomaly] resource grant failed (char %s)",
                            p.get("id"), exc_info=True)

        # SYN.8: Tier 3 trophy — every participant gets one.
        if anomaly.tier == 3 and trophy_def:
            try:
                granted_trophy = await _grant_trophy(
                    db, p, trophy_def,
                )
            except Exception:
                log.warning(
                    "[anomaly] T3 trophy grant failed (char %s)",
                    p.get("id"), exc_info=True,
                )

        payouts_per_char.append({
            "char_id": int(p["id"]),
            "credits": per_credits,
            "resources": granted_stacks,
            "trophy": granted_trophy,
        })

    # Influence — killer's faction only.
    killer_faction = killer.get("faction_id") or "independent"
    actual_inf = 0
    if (influence_delta > 0
            and killer_faction != "independent"
            and anomaly.zone_id is not None):
        try:
            from engine.territory import adjust_territory_influence
            await adjust_territory_influence(
                db, killer_faction, anomaly.zone_id,
                influence_delta,
                reason=f"anomaly:{anomaly.template_key}",
                region_slug=anomaly.region_slug,
            )
            actual_inf = influence_delta
        except Exception:
            log.warning("[anomaly] T%d influence adjust failed",
                        anomaly.tier, exc_info=True)

    # Named loot — Tier 2 only — killer alone.
    granted_named_loot = None
    if anomaly.tier == 2 and named_loot:
        granted_named_loot = await _grant_named_loot(db, killer, named_loot)

    # SYN.8: Tier 3 scaled T5 mat distribution.
    # floor(N/4) pieces to top participants by kill count
    # (descending), with the killer winning ties.
    scaled_t5_grants = []
    if anomaly.tier == 3 and scaled_t5_def:
        scaled_t5_grants = await _distribute_scaled_t5_mat(
            db, anomaly, scaled_t5_def, killer_char_id,
            n_participants,
        )

    anomaly.resolved = True
    anomaly.resolved_by = int(killer_char_id)
    anomaly.resolved_faction = killer_faction
    anomaly.expiry = min(anomaly.expiry, now + 30)

    log.info(
        "[anomaly] T%d combat reward paid for #%d (%s); killer=%s, "
        "participants=%d, per-credits=%d, inf=%d, "
        "named_loot=%s, trophy=%s, scaled_t5_count=%d",
        anomaly.tier, anomaly.id, anomaly.template_key, killer_char_id,
        n_participants, per_credits, actual_inf,
        bool(granted_named_loot), bool(trophy_def),
        len(scaled_t5_grants),
    )

    # SYN.10 (May 25 2026): defeat news broadcast per design §2.6.
    await _broadcast_anomaly_defeat(
        anomaly, killer_faction, session_mgr,
    )

    return {
        "anomaly_id": anomaly.id,
        "template_key": anomaly.template_key,
        "display_name": anomaly.display_name,
        "tier": anomaly.tier,
        "credits": per_credits,                # per participant
        "total_credits_pool": base_credits,    # total before split
        "resources": payouts_per_char[0]["resources"]
                     if payouts_per_char else [],
        "influence": actual_inf,
        "named_loot": granted_named_loot,
        "trophy": (payouts_per_char[0].get("trophy")
                   if payouts_per_char and anomaly.tier == 3
                   else None),
        "scaled_t5_grants": scaled_t5_grants,
        "participants": [p["char_id"] for p in payouts_per_char],
        "payouts_per_char": payouts_per_char,
    }


async def _grant_trophy(
    db, recipient: dict, trophy_def: dict,
) -> Optional[dict]:
    """SYN.8: Grant a Tier 3 trophy item to a participant.

    Trophy items are added to inventory["items"] with `is_trophy: True`
    so housing.trophy_mount can detect them. Each participant who
    contributed a kill gets exactly one trophy.
    """
    try:
        tkey = trophy_def.get("key")
        tname = trophy_def.get("name", tkey)
        tdesc = trophy_def.get("description", "")
        if not tkey:
            return None
        inv_raw = recipient.get("inventory", "{}")
        try:
            inv = (json.loads(inv_raw)
                   if isinstance(inv_raw, str) else inv_raw)
        except Exception:
            inv = {}
        inv.setdefault("items", []).append({
            "key": tkey,
            "name": tname,
            "qty": 1,
            "description": tdesc,
            "is_trophy": True,
            "is_anomaly_loot": True,
        })
        recipient["inventory"] = json.dumps(inv)
        await db.save_character(recipient["id"],
                                inventory=recipient["inventory"])
        log.info(
            "[anomaly] T3 trophy granted: %s to char %s",
            tname, recipient.get("id"),
        )
        return {
            "key": tkey,
            "name": tname,
            "description": tdesc,
        }
    except Exception:
        log.warning("[anomaly] _grant_trophy failed", exc_info=True)
        return None


async def _distribute_scaled_t5_mat(
    db, anomaly: "WildernessAnomaly", scaled_def: dict,
    killer_char_id: int, n_participants: int,
) -> list:
    """SYN.8: Distribute the scaled T5 mat pieces.

    Per design: floor(N/4) pieces total, distributed to top
    participants by kill count descending. Killer wins ties (always
    gets a piece if any are dropped, even if their kill count is
    not in the top floor(N/4)).

    Returns a list of grant dicts: [{"char_id": int, "key": str,
    "quantity": int, "quality": float}, ...].
    """
    pieces_per_4 = int(scaled_def.get("per_4_participants", 1))
    n_pieces = (n_participants // 4) * pieces_per_4
    # Floor of N/4 can be 0 (e.g. 3 participants). Design rule: in
    # that case, the killer alone gets 1 piece as the consolation
    # for the kill effort. Avoids the "all-this-effort, no T5 mat"
    # outcome for small teams.
    if n_pieces == 0:
        n_pieces = 1

    # Rank participants by kill count (descending). Ties broken by
    # killer-first, then arbitrary order.
    ranked = sorted(
        anomaly.kill_counts.items(),
        key=lambda kv: (-kv[1], 0 if kv[0] == int(killer_char_id) else 1),
    )
    # Defensive: ensure killer is in the list even if kill_counts
    # somehow lost track of them.
    if int(killer_char_id) not in {cid for cid, _ in ranked}:
        ranked.insert(0, (int(killer_char_id), 0))

    rkey = scaled_def.get("key")
    quality = float(scaled_def.get("quality", TIER3_T5_MAT_QUALITY))
    if not rkey:
        return []

    grants = []
    from engine.crafting import add_resource
    for (cid, kill_count) in ranked[:n_pieces]:
        try:
            recipient = await db.get_character(int(cid))
        except Exception:
            recipient = None
        if not recipient:
            continue
        recipient = dict(recipient)
        try:
            add_resource(recipient, rkey, 1, quality)
            await db.save_character(
                recipient["id"], inventory=recipient["inventory"],
            )
            grants.append({
                "char_id": int(cid),
                "key": rkey,
                "quantity": 1,
                "quality": quality,
                "kill_count": int(kill_count),
            })
            log.info(
                "[anomaly] T3 scaled T5 mat granted: 1x %s (q%.0f) "
                "to char %s (kill_count=%d)",
                rkey, quality, cid, kill_count,
            )
        except Exception:
            log.warning(
                "[anomaly] T3 scaled T5 grant failed (char %s)",
                cid, exc_info=True,
            )
    return grants


async def _grant_named_loot(
    db, killer: dict, named_loot: dict,
) -> Optional[dict]:
    """Grant a named-loot piece to the killer.

    Two named_loot shapes:
      type="resource" — adds to crafting resources via add_resource.
        Key fields: key, qty, quality.
      type="item" — adds to inventory["items"] list.
        Key fields: key, qty, name, description.

    Returns a summary dict, or None on failure.
    """
    try:
        loot_type = named_loot.get("type")
        if loot_type == "resource":
            rkey = named_loot.get("key")
            qty = int(named_loot.get("qty", 1))
            quality = float(named_loot.get("quality", 60.0))
            if not rkey:
                return None
            from engine.crafting import add_resource
            add_resource(killer, rkey, qty, quality)
            await db.save_character(killer["id"], inventory=killer["inventory"])
            log.info(
                "[anomaly] named-loot resource: %dx %s (q%.0f) to char %s",
                qty, rkey, quality, killer.get("id"),
            )
            return {
                "type": "resource",
                "key": rkey,
                "qty": qty,
                "quality": quality,
                "description": named_loot.get("description", ""),
            }
        elif loot_type == "item":
            ikey = named_loot.get("key")
            iname = named_loot.get("name", ikey)
            qty = int(named_loot.get("qty", 1))
            if not ikey:
                return None
            inv_raw = killer.get("inventory", "{}")
            try:
                inv = (json.loads(inv_raw)
                       if isinstance(inv_raw, str) else inv_raw)
            except Exception:
                inv = {}
            inv.setdefault("items", []).append({
                "key": ikey,
                "name": iname,
                "qty": qty,
                "description": named_loot.get("description", ""),
                "is_anomaly_loot": True,
            })
            killer["inventory"] = json.dumps(inv)
            await db.save_character(killer["id"], inventory=killer["inventory"])
            log.info(
                "[anomaly] named-loot item: %s to char %s",
                iname, killer.get("id"),
            )
            return {
                "type": "item",
                "key": ikey,
                "name": iname,
                "qty": qty,
                "description": named_loot.get("description", ""),
            }
        else:
            log.warning(
                "[anomaly] unknown named_loot type: %r", loot_type,
            )
            return None
    except Exception:
        log.warning("[anomaly] _grant_named_loot failed", exc_info=True)
        return None


# ── Result helpers ───────────────────────────────────────────────────────────

def _fail_result(msg: str) -> dict:
    """Build a uniform failure-result dict for resolve_anomaly."""
    return {
        "ok": False,
        "mode": "skill",   # fail-fast results before dispatch default skill
        "msg": msg,
        "credits": 0,
        "resources": [],
        "influence": 0,
        "skill_used": "",
        "skill_roll": 0,
        "margin": 0,
        "success": False,
    }


def _pick_better_skill(char: dict, primary: str,
                       secondary: Optional[str]) -> str:
    """Pick whichever of primary/secondary the character has trained;
    fall back to primary if neither is trained."""
    if not secondary:
        return primary
    skills_raw = char.get("skills", "{}")
    if isinstance(skills_raw, str):
        try:
            skills = json.loads(skills_raw)
        except (json.JSONDecodeError, TypeError):
            skills = {}
    elif isinstance(skills_raw, dict):
        skills = skills_raw
    else:
        skills = {}
    if skills.get(primary):
        return primary
    if skills.get(secondary):
        return secondary
    return primary


# ── SYN.10 news-broadcast helper ─────────────────────────────────────────────

async def _broadcast_anomaly_defeat(
    anomaly, killer_faction: Optional[str], session_mgr,
) -> None:
    """Broadcast the anomaly-defeat news line per design §2.6.

    Best-effort: any failure (no session_mgr, no resolve_org_name)
    silently no-ops so the payout return value is never blocked.

    Called from _payout_combat_anomaly at the end of every payout
    path (T1, T2, T3). Mirrors the spawn-time broadcast pattern.
    """
    if session_mgr is None:
        return
    try:
        from engine.territory_display import format_anomaly_defeat_news
        org_name = killer_faction
        if killer_faction and killer_faction != "independent":
            try:
                rows = await session_mgr.db.fetchall(
                    "SELECT name FROM organizations WHERE code = ?",
                    (killer_faction,),
                ) if hasattr(session_mgr, "db") else None
                if rows:
                    org_name = dict(rows[0]).get("name") or killer_faction
            except Exception:
                log.debug(
                    "[wilderness_anomalies] org name lookup for "
                    "killer_faction=%s failed; falling back to code",
                    killer_faction, exc_info=True,
                )
        news = format_anomaly_defeat_news(
            anomaly.region_slug,
            anomaly_name=anomaly.display_name,
            killer_org=org_name if org_name and org_name != "independent" else None,
        )
        await session_mgr.broadcast(f"\n  \033[1;33m[News] {news}\033[0m")
    except Exception:
        log.warning("[anomaly] defeat broadcast failed", exc_info=True)
