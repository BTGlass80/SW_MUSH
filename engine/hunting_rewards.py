# -*- coding: utf-8 -*-
"""engine/hunting_rewards.py — solo-PvE mob-grind reward trickle (v1).

Brian (2026-06-21): players who want to "grind out some NPCs and zone out"
when friends aren't on should get a small, satisfying reward — an EXTREME
trickle — without breaking the advancement flow (RP stays the primary axis).

The EVE-economist framing: grinding rats pays ISK + loot + standings, NEVER
skillpoints (those are time-gated). Our CP is the skillpoint analog (RP/time-
gated, 400-tick/week hard cap). So this system pays **credits + prestige and
deliberately ZERO CP** — it structurally cannot touch advancement.

What fires today: nothing. Generic roaming hostile NPCs (a guard, a thug, a
pirate) that aren't a bounty target / anomaly spawn / wilderness creature /
chain enemy give NO reward on defeat. This fills that gap.

v1 design (conservative — the exact numbers are a `T2.ECON.review` knob):
  * **Credits:** a small flat reward per huntable kill (BASE_REWARD), bounded
    by a per-day SOFT CAP (DAILY_SOFT_CAP). Past the cap, the reward drops to a
    token floor (OVER_CAP_FLOOR) — the "extreme trickle" tail, so a marathon
    grinder isn't farming a real income, just collecting prestige.
  * **Self-sink:** the loop pays for itself. A real fight costs medical (50-1,000
    cr) + gear repair, which for any non-trivial mob exceeds the 15 cr reward —
    so the FAUCET is bounded AND the activity is net-negative-to-break-even for
    hard fights (the harder the quarry, the more you spend healing relative to
    the trickle). The paired SINKS are the existing combat-cost loop.
  * **Prestige (the real "feel rewarded"):** a per-character hunting log
    (lifetime kill count) and earned milestone TITLES (engine/titles.py) — like
    EVE killmails/standings, zero economy impact.
  * **No toughness scaling in v1** (flat per kill) — deferred to the economist
    pass; the cap + prestige carry v1.

The reward fires from the post-combat NPC-defeat seam (parser/combat_commands.py
_apply_combat_wear), gated by is_huntable_mob() so it never double-rewards a
special NPC that already has its own payout.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

# ── Per-character attribute key (sibling of tutorial_chain / seen_hints) ──
HUNT_LOG_KEY = "hunting_log"

# ── Tunable economy knobs (T2.ECON.review owns the final values) ──────────
BASE_REWARD = 15          # cr per huntable kill, while under the daily cap
DAILY_SOFT_CAP = 400      # cr/day from grinding before the reward drops to floor
OVER_CAP_FLOOR = 3        # cr per kill once past the daily cap (the trickle tail)
CREDIT_TAG = "mob_grind"  # ledger source tag for the faucet

# Lifetime-kill -> earned title key (engine/titles.EARNED_TITLES). Ascending.
TITLE_THRESHOLDS = [
    (25,   "hunter"),
    (100,  "seasoned_hunter"),
    (500,  "master_hunter"),
    (2500, "apex_hunter"),
]

# ai_config_json markers that mean "this NPC already has its own reward system";
# a huntable generic hostile has NONE of these. Each is verified set in engine
# code (bounty_board / wilderness_anomalies / creature_library / dsp_hunter /
# housing+intel_handlers / npc_loader). New special-NPC types MUST be added here.
_SPECIAL_MARKERS = (
    "is_bounty_target",
    "is_anomaly_target",
    "is_wilderness_encounter",
    "is_dsp_hunter",
    "is_intel_handler",
    "chain_enemy_template",
    "vendor",
)


def _safe_int(v, default: int = 0) -> int:
    """Tolerant int — a corrupt hunting_log value (str/None) must never crash
    +hunting or the reward path (it self-heals on the next normal kill)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _ai_config(npc_row: dict) -> dict:
    raw = (npc_row or {}).get("ai_config_json", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        d = json.loads(raw or "{}")
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def is_huntable_mob(npc_row: dict) -> bool:
    """True iff this defeated NPC is an ORDINARY roaming hostile that currently
    rewards nothing — i.e. hostile AND carrying none of the special-reward
    markers. Whitelist-inversion: if any existing reward hook claims this NPC,
    this returns False, so there is no double-reward."""
    ai = _ai_config(npc_row)
    if not ai.get("hostile", False):
        return False
    return not any(ai.get(m) for m in _SPECIAL_MARKERS)


def _load_log(attrs: dict, day_stamp: str) -> dict:
    """Fetch (and day-roll) the hunting log sub-dict."""
    log_d = attrs.get(HUNT_LOG_KEY)
    if not isinstance(log_d, dict):
        log_d = {}
    log_d.setdefault("kills", 0)
    log_d.setdefault("daily_credits", 0)
    log_d.setdefault("day", None)
    if log_d.get("day") != day_stamp:        # new day → reset the soft-cap meter
        log_d["day"] = day_stamp
        log_d["daily_credits"] = 0
    return log_d


def _reward_for(daily_credits: int) -> int:
    """The per-kill reward given how much grind income today already is."""
    return BASE_REWARD if daily_credits < DAILY_SOFT_CAP else OVER_CAP_FLOOR


def newly_earned_title(prev_kills: int, new_kills: int):
    """Return the title key whose threshold the kill count just crossed, or None.
    (At most one milestone per kill given the spread of thresholds.)"""
    for thresh, key in TITLE_THRESHOLDS:
        if prev_kills < thresh <= new_kills:
            return key
    return None


async def on_huntable_kill(db, killer_char: dict, npc_row: dict, *,
                           day_stamp: str) -> dict | None:
    """Apply the mob-grind reward for `killer_char` defeating `npc_row`.

    Pure of any session/notification concern (the caller handles that). Returns
    a summary dict, or None if the NPC isn't huntable / the award failed. Never
    raises (best-effort: a reward must never break combat).

    `day_stamp` is supplied by the caller (e.g. today's UTC date) so this stays
    deterministic + testable.
    """
    try:
        if not is_huntable_mob(npc_row):
            return None

        from engine.chain_events import _load_attrs, _persist_attrs

        attrs = _load_attrs(killer_char)
        log_d = _load_log(attrs, day_stamp)

        daily_before = _safe_int(log_d.get("daily_credits"))
        reward = _reward_for(daily_before)

        # Credits via the funnel chokepoint (a real, bounded faucet).
        new_balance = await db.adjust_credits(
            killer_char["id"], reward, CREDIT_TAG)
        if isinstance(new_balance, int):
            killer_char["credits"] = new_balance

        prev_kills = _safe_int(log_d.get("kills"))
        new_kills = prev_kills + 1
        log_d["kills"] = new_kills
        log_d["daily_credits"] = daily_before + reward
        attrs[HUNT_LOG_KEY] = log_d
        await _persist_attrs(db, killer_char, attrs)

        # Prestige: grant a milestone title if a threshold was just crossed.
        title_key = newly_earned_title(prev_kills, new_kills)
        title_label = None
        if title_key:
            try:
                from engine.titles import grant_earned_title, title_by_key
                if await grant_earned_title(db, killer_char, title_key):
                    t = title_by_key(title_key)
                    title_label = t["label"] if t else title_key
                else:
                    title_key = None
            except Exception:
                log.debug("hunting: title grant failed", exc_info=True)
                title_key = None

        # Telemetry: join the grind OUTCOME to the already-ledgered credit leg
        # (T3.19 breadth — grind/rewards). Fail-open + zero extra I/O (cheap
        # in-memory npc_row/killer_char fields only; offline resolves
        # room_id->zone->threat-band). NEVER let it disturb the reward path.
        try:
            from engine import telemetry as _tlm
            ai = _ai_config(npc_row)
            _tlm.emit_grind_kill(
                killer_char.get("id"),
                reward=reward,
                daily_credits=log_d["daily_credits"],
                at_cap=log_d["daily_credits"] >= DAILY_SOFT_CAP,
                over_cap=daily_before >= DAILY_SOFT_CAP,
                total_kills=new_kills,
                npc_name=npc_row.get("name", ""),
                room_id=killer_char.get("room_id"),
                species=npc_row.get("species"),
                faction=ai.get("faction"),
                behavior=ai.get("combat_behavior"),
                title_key=title_key,
            )
        except Exception:
            log.debug("hunting: grind telemetry emit failed", exc_info=True)

        return {
            "reward": reward,
            "total_kills": new_kills,
            "daily_credits": log_d["daily_credits"],
            "at_cap": log_d["daily_credits"] >= DAILY_SOFT_CAP,
            "new_balance": new_balance if isinstance(new_balance, int) else None,
            "title_key": title_key,
            "title_label": title_label,
        }
    except Exception:
        log.debug("hunting: on_huntable_kill failed", exc_info=True)
        return None


def hunting_log_view(char: dict, *, day_stamp: str | None = None) -> dict:
    """Read-only snapshot of a character's hunting log for the +hunting command.

    The daily-credit meter is DAY-ROLLED for display (read-only, not persisted)
    so the command never shows yesterday's total / a stale "cap reached" after
    midnight. `day_stamp` defaults to today (UTC); tests pass it explicitly.
    """
    from engine.chain_events import _load_attrs
    attrs = _load_attrs(char)
    log_d = attrs.get(HUNT_LOG_KEY)
    if not isinstance(log_d, dict):
        log_d = {}
    kills = _safe_int(log_d.get("kills"))
    if day_stamp is None:
        from datetime import datetime as _d, timezone as _t
        day_stamp = _d.now(_t.utc).date().isoformat()
    daily = _safe_int(log_d.get("daily_credits")) if log_d.get("day") == day_stamp else 0
    next_thresh = next(((t, k) for t, k in TITLE_THRESHOLDS if kills < t), None)
    return {
        "kills": kills,
        "daily_credits": daily,
        "daily_cap": DAILY_SOFT_CAP,
        "next_threshold": next_thresh[0] if next_thresh else None,
        "next_title_key": next_thresh[1] if next_thresh else None,
    }
