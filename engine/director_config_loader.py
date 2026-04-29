# -*- coding: utf-8 -*-
"""
engine/director_config_loader.py — Era-aware Director config seam.

Drop F.6a.3 (seam-only). This module is the production-safe seam between
the F.6a.1 YAML loader (`engine/world_loader.py::load_director_config`)
and the live Director engine (`engine/director.py`). It is INTENTIONALLY
small — it does not modify `engine/director.py` itself; that is the work
of a future drop ("F.6a.3 integration") which Brian must validate at the
PC because it touches the live faction system.

What this module provides
-------------------------
A single function `get_director_runtime_config(era)` returns a small
dataclass `DirectorRuntimeConfig` containing the four runtime knobs the
Director needs:

    valid_factions:    frozenset[str]
    zone_baselines:    dict[str, dict[str, int]]
    system_prompt:     str
    rewicker_factions: dict[str, str]   # {"imperial": "republic", ...}

When `era` is None or the YAML can't be loaded, this falls back to the
hardcoded constants currently defined in engine/director.py
(`VALID_FACTIONS`, `DEFAULT_INFLUENCE`, the inline system_prompt
literal). The fallback is bytes-equivalent to current behavior — there
is no functional change unless the caller explicitly passes an era.

Why a seam, not a refactor
--------------------------
Per `clone_wars_director_lore_pivot_design_v1.md` §3.2: Director's
`VALID_FACTIONS` and `DEFAULT_INFLUENCE` and `system_prompt` are
referenced from ~30 sites across `engine/director.py`. A direct refactor
risks breaking the live faction system in subtle ways (e.g. a frozenset
literal at line 817 is a SECOND copy that needs to be updated separately;
several `for faction in VALID_FACTIONS:` loops inside class methods
would need the per-instance value injected; etc.). That's a session of
work AND a session of validation against a real DB. Not safe to ship
unattended.

The seam ships now. The integration ("read the seam from inside
DirectorAI.__init__") happens later in a single targeted PR.

Tested by tests/test_f6a3_director_config_loader.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# Hardcoded fallbacks. These MUST remain byte-equivalent to the constants
# currently defined at the top of engine/director.py until the integration
# PR removes the duplication. See the design doc §3.2 rollback path.

_LEGACY_VALID_FACTIONS = frozenset({
    "imperial", "rebel", "criminal", "independent",
})

_LEGACY_DEFAULT_INFLUENCE = {
    "spaceport":  {"imperial": 65, "rebel": 8,  "criminal": 45, "independent": 25},
    "streets":    {"imperial": 55, "rebel": 12, "criminal": 50, "independent": 35},
    "cantina":    {"imperial": 40, "rebel": 15, "criminal": 65, "independent": 40},
    "shops":      {"imperial": 50, "rebel": 10, "criminal": 55, "independent": 40},
    "jabba":      {"imperial": 20, "rebel": 5,  "criminal": 85, "independent": 10},
    "government": {"imperial": 80, "rebel": 5,  "criminal": 20, "independent": 20},
}

# The legacy system prompt — lifted verbatim from engine/director.py
# (L678-751 at the time of F.6a.3 integration). After F.6a.3-int wires
# `DirectorAI._call_claude` to read `cfg.system_prompt` instead of the
# inline literal, this constant becomes the single source of truth for
# the GCW-era prompt. Era YAMLs (e.g. data/worlds/clone_wars/
# director_config.yaml) override it via the seam's yaml-<era> path.
_LEGACY_SYSTEM_PROMPT = (
    "You are the Director AI for a Star Wars MUSH set in Mos Eisley, Tatooine.\n"
    "Your role is to evaluate the current state of the galaxy and decide what\n"
    "happens next at the MACRO level. You never narrate player actions or\n"
    "describe what individual characters do. You move the unseen pieces:\n"
    "faction responses, economic shifts, atmospheric changes, and emerging\n"
    "threats.\n\n"
    "You are guided by these principles:\n"
    "- The Empire reacts to resistance with escalation, not retreat.\n"
    "- The criminal underworld fills any vacuum the Empire leaves.\n"
    "- The Rebel Alliance operates in shadows; their influence is felt\n"
    "  through sabotage and propaganda, not open warfare on Tatooine.\n"
    "- Tatooine is a backwater. The Empire cares about order, not ideology.\n"
    "  The Hutts care about profit. Neither wants open war here.\n"
    "- Events should create OPPORTUNITIES for players, never OBLIGATIONS.\n"
    "- Consequences should feel proportional and narratively logical.\n\n"
    "FACTION MANAGEMENT:\n"
    "If the digest includes 'faction_status', you manage those factions.\n"
    "You may issue up to 3 faction_orders total per turn. Guidelines:\n"
    "- Promote conservatively. Players must EARN rank.\n"
    "- Post missions that reflect current world state, not random jobs.\n"
    "- Discipline escalates: warn → probation → expel. Never skip steps.\n"
    "- Approve requisitions unless the member negligently caused the loss.\n"
    "- Never promote past pending_promotions list — only promote listed chars.\n\n"
    "PC HOOKS:\n"
    "If the digest includes 'online_pcs', you may generate up to 2\n"
    "personalised story hooks for specific players based on their short_record.\n"
    "Hooks must be brief (1-2 sentences), in-universe, and create opportunity\n"
    "not obligation. Deliver via comlink_message unless NPC context warrants whisper.\n\n"
    "FACTION STANDINGS:\n"
    "If the digest includes 'player_faction_standings', use them to target\n"
    "hooks and events appropriately. A player who is Revered with the Rebel\n"
    "Alliance should receive Rebel-themed opportunities. A player who is\n"
    "Hostile with the Empire might attract Imperial attention or bounty hunters.\n"
    "Never target faction content at players with Unknown/Wary standing.\n\n"
    "Respond with ONLY a JSON object in this exact format:\n"
    "{\n"
    "  \"influence_adjustments\": [\n"
    "    {\"zone\": \"...\", \"faction\": \"...\", \"delta\": <int>}\n"
    "  ],\n"
    "  \"narrative_event\": {\n"
    "    \"type\": \"...\",\n"
    "    \"headline\": \"...\",\n"
    "    \"duration_minutes\": <int>,\n"
    "    \"zones_affected\": [\"...\"],\n"
    "    \"mechanical_effects\": {\"...\": \"...\"}\n"
    "  } OR null,\n"
    "  \"ambient_pool\": [\"line1\", \"line2\", \"line3\"] OR null,\n"
    "  \"news_headline\": \"One-sentence summary for the world events board.\",\n"
    "  \"faction_orders\": [\n"
    "    {\n"
    "      \"faction\": \"empire\" | \"rebel\" | \"cartel\" | \"bhg\" | \"traders\",\n"
    "      \"action\": \"promote\" | \"warn\" | \"probation\" | \"expel\" | \"pardon\"\n"
    "               | \"post_mission\" | \"faction_announcement\",\n"
    "      \"target_char_id\": <int> | null,\n"
    "      \"new_rank\": <int> | null,\n"
    "      \"reason\": \"...\",\n"
    "      \"mission_type\": \"patrol\" | \"delivery\" | \"combat\" | \"investigation\" | null,\n"
    "      \"zone\": \"...\" | null,\n"
    "      \"reward\": <int 100-5000> | null,\n"
    "      \"description\": \"...\" | null,\n"
    "      \"message\": \"...\" | null\n"
    "    }\n"
    "  ] OR null,\n"
    "  \"pc_hooks\": [\n"
    "    {\n"
    "      \"char_id\": <int>,\n"
    "      \"hook_type\": \"rumor\" | \"opportunity\" | \"encounter\",\n"
    "      \"content\": \"Brief in-universe message (1-2 sentences max)\",\n"
    "      \"delivery\": \"comlink_message\" | \"npc_whisper\" | \"news_item\" | \"ambient\"\n"
    "    }\n"
    "  ] OR null\n"
    "}"
)


@dataclass
class DirectorRuntimeConfig:
    """Frozen view of the Director's runtime knobs.

    `source` is "yaml-<era>" when the values came from
    data/worlds/<era>/director_config.yaml, "legacy" when the fallback
    was used. Useful for logging / debugging which path resolved.

    `valid_factions` is a frozenset for hashability (matches the
    DirectorAI's existing `VALID_FACTIONS` semantics — used in `if x in
    VALID_FACTIONS`).
    """
    valid_factions: frozenset
    zone_baselines: dict
    system_prompt: str
    rewicker_factions: dict
    rewicker_zones: dict
    source: str = "legacy"
    _yaml_config: Optional["DirectorConfig"] = None  # type: ignore[name-defined]
    raw_meta: dict = field(default_factory=dict)


def get_director_runtime_config(
    era: Optional[str] = None,
    *,
    worlds_root: Optional[Path] = None,
) -> DirectorRuntimeConfig:
    """Resolve Director runtime config for the given era.

    `era` is the directory name under data/worlds/ — usually "gcw" or
    "clone_wars". When None, returns the legacy hardcoded values
    immediately without touching the filesystem.

    `worlds_root` overrides the default `data/worlds` path; tests use
    this to point at a temp directory.

    Never raises. On any failure, logs a warning and returns the legacy
    fallback so the Director can still boot.
    """
    if era is None:
        return _legacy()

    try:
        from engine.world_loader import (
            load_era_manifest, load_director_config as _load_dc,
        )
    except Exception as e:
        log.warning(
            "[director_config_loader] world_loader import failed (%s); "
            "falling back to legacy.", e,
        )
        return _legacy()

    root = worlds_root or (Path("data") / "worlds")
    era_dir = Path(root) / era
    try:
        manifest = load_era_manifest(era_dir)
        dc = _load_dc(manifest)
    except Exception as e:
        log.warning(
            "[director_config_loader] Era %r director_config load failed "
            "(%s); falling back to legacy.", era, e,
        )
        return _legacy()

    if dc is None:
        log.info(
            "[director_config_loader] Era %r has no director_config "
            "content_ref; falling back to legacy.", era,
        )
        return _legacy()

    if dc.report.errors:
        log.warning(
            "[director_config_loader] Era %r director_config has %d "
            "validation error(s); falling back to legacy. First: %s",
            era, len(dc.report.errors), dc.report.errors[0],
        )
        return _legacy()

    return DirectorRuntimeConfig(
        valid_factions=frozenset(dc.valid_factions),
        zone_baselines=dict(dc.zone_baselines),
        system_prompt=dc.system_prompt,
        rewicker_factions=dict(dc.rewicker_faction_codes),
        rewicker_zones=dict(dc.rewicker_zone_keys),
        source=f"yaml-{era}",
        _yaml_config=dc,
        raw_meta={
            "era": era,
            "schema_version": dc.schema_version,
            "milestone_count": len(dc.milestone_events),
            "holonet_pool_size": len(dc.holonet_news_pool),
        },
    )


def _legacy() -> DirectorRuntimeConfig:
    return DirectorRuntimeConfig(
        valid_factions=_LEGACY_VALID_FACTIONS,
        zone_baselines={k: dict(v) for k, v in _LEGACY_DEFAULT_INFLUENCE.items()},
        system_prompt=_LEGACY_SYSTEM_PROMPT,
        rewicker_factions={},
        rewicker_zones={},
        source="legacy",
        raw_meta={"era": None},
    )


def apply_rewicker(
    cfg: DirectorRuntimeConfig,
    legacy_faction: str,
) -> str:
    """Translate a legacy GCW faction code to the current era's code.

    Returns the rewicked code if the rewicker map covers it, otherwise
    returns the input unchanged. Use at boundaries between legacy code
    paths (which still construct `imperial`/`rebel`/`criminal` literals)
    and the era's faction set.

    When the runtime is on the legacy path (no era YAML), the rewicker
    map is empty and this is a no-op.
    """
    return cfg.rewicker_factions.get(legacy_faction, legacy_faction)


def apply_zone_rewicker(
    cfg: DirectorRuntimeConfig,
    legacy_zone_key: str,
) -> str:
    """Translate a legacy GCW zone key to the current era's zone key.

    Returns the rewicked key if the rewicker map covers it, otherwise
    returns the input unchanged.
    """
    return cfg.rewicker_zones.get(legacy_zone_key, legacy_zone_key)
