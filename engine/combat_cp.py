# -*- coding: utf-8 -*-
"""engine/combat_cp.py — early-game combat CP faucet (fun2-combat-cp, 2026-06-25).

Brian-approved conservative design: the first N hostile NPC kills a character
ever makes each grant +1 Character Point. After the cap the faucet is dry
forever for that character.

Rationale: combat currently pays ZERO CP, so the action-oriented player has no
kill→progress signal on first session. This funds roughly one die-step early
(a visible first-session win) without touching the long-term RP-first CP
economy — the cap is low and the faucet is lifetime-sealed per character.

Architecture
------------
* **Counter field**: ``early_combat_cp`` sub-dict in the character attributes
  JSON blob (same pattern as ``hunting_log`` in hunting_rewards.py — no schema
  migration needed).
* **CP funnel**: ``get_cp_engine().award_milestone_cp()`` tagged ``"early_combat"``
  (the T3.19 telemetry hook inside award_milestone_cp automatically emits a
  cp_income event, so the faucet is visible in the balance dashboard).
* **Tunable**: ``combat.early_cp_kill_cap`` in data/tunables.yaml (default 5).
* **Kill seam**: ``_award_early_combat_cp(combat, ctx, pre_npcs)`` mirrors
  ``_award_mob_grind_rewards`` — called at both ``resolve_round`` call sites in
  parser/combat_commands.py right after the mob-grind hook.

The function is fail-open: any exception is caught and logged as a warning;
combat resolution is never interrupted by a CP-grant failure.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)

# ── Attribute blob key (sibling of hunting_log / tutorial_chain) ─────────────
EARLY_CP_KEY = "early_combat_cp"

# ── Tunable defaults (overridden by data/tunables.yaml at call site) ─────────
_DEFAULT_KILL_CAP = 5   # max lifetime CP from this faucet (== kills rewarded)

# ── CP-funnel tag — unique per faucet so telemetry can segregate it ──────────
_CP_TAG = "early_combat"


def _safe_int(v, default: int = 0) -> int:
    """Tolerant int — a corrupt attribute value must never crash the reward path."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def get_early_cp_kills(char_attrs: dict) -> int:
    """Return the number of kills already credited under the early-CP faucet."""
    d = char_attrs.get(EARLY_CP_KEY)
    if not isinstance(d, dict):
        return 0
    return _safe_int(d.get("kills"), 0)


async def award_early_combat_cp(
    db,
    killer_char: dict,
) -> dict | None:
    """Award +1 CP for a single NPC kill if the early-CP cap is not yet reached.

    Reads and writes the ``early_combat_cp`` counter from/to the character's
    attributes JSON blob (same pattern as hunting_rewards/chain_events).

    Returns a summary dict on award, None if the cap is already reached or
    the award was dropped. Never raises.

    Parameters
    ----------
    db:
        The active database handle (must support ``save_character`` and expose
        ``cp_add_character_points`` via ``get_cp_engine().award_milestone_cp``).
    killer_char:
        The mutable PC character dict (``id``, ``attributes``, ...).
    """
    try:
        from engine.tunables import get_tunable
        kill_cap = _safe_int(
            get_tunable("combat.early_cp_kill_cap", _DEFAULT_KILL_CAP),
            _DEFAULT_KILL_CAP,
        )

        from engine.chain_events import _load_attrs, _persist_attrs

        attrs = _load_attrs(killer_char)
        blob = attrs.get(EARLY_CP_KEY)
        if not isinstance(blob, dict):
            blob = {"kills": 0}

        kills_so_far = _safe_int(blob.get("kills"), 0)
        if kills_so_far >= kill_cap:
            return None  # faucet dry — nothing to do

        # Award exactly +1 CP through the canonical milestone funnel.
        from engine.cp_engine import get_cp_engine
        result = await get_cp_engine().award_milestone_cp(
            db, killer_char["id"], 1, reason=_CP_TAG,
        )
        if result.get("dropped"):
            log.warning(
                "[combat_cp] award_milestone_cp dropped for char %d "
                "(early_cp kill #%d)",
                killer_char.get("id"), kills_so_far + 1,
            )
            # Do NOT increment the counter — the CP wasn't awarded.
            return None

        # Persist the updated counter.
        new_kills = kills_so_far + 1
        blob["kills"] = new_kills
        attrs[EARLY_CP_KEY] = blob
        await _persist_attrs(db, killer_char, attrs)

        log.info(
            "[combat_cp] char %d early_combat_cp kill %d/%d (+1 CP)",
            killer_char.get("id"), new_kills, kill_cap,
        )
        return {
            "cp_awarded": 1,
            "kills_credited": new_kills,
            "cap": kill_cap,
            "faucet_sealed": new_kills >= kill_cap,
        }

    except Exception:
        log.warning(
            "[combat_cp] award_early_combat_cp failed for char %d",
            (killer_char or {}).get("id"), exc_info=True,
        )
        return None
