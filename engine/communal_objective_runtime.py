"""engine/communal_objective_runtime.py — IO orchestrator for the dark-side cult
communal objective (Drop 4b, the communal-rally villain).

engine/communal_objective.py stays PURE (roster + menace state machine + strike
deciders + reward shares + every player-facing string). This module owns the DB
writes, the broadcasts, the director-log/news posts, and the reward payout.

Callers:
  * server/tick_handlers_progression.py::communal_objective_tick — posts a new
    uprising when none is active (after a cooldown), escalates the menace each
    cadence, and resolves win/lose (distributing rewards on a win).
  * parser/communal_commands.py::RallyCommand — the player `rally` board + the
    `rally strike` participation action.

All public coroutines are best-effort: a DB hiccup logs and degrades, it never
aborts the tick or a player's command turn. Persistence is a single
`communal_objective` row per uprising (schema 43); the active one is the latest
row with state='active'. Contributions live in that row's contributions_json as
{char_id: {points, last_strike_at}} so reward payout and the per-character strike
cooldown need no extra table.
"""
from __future__ import annotations

import json
import logging
import time

import engine.communal_objective as CO

log = logging.getLogger(__name__)


# ── small helpers ────────────────────────────────────────────────────────────
def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_json(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _row_to_dict(row) -> dict:
    """aiosqlite Row / tuple / dict → plain dict (defensive across drivers)."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)  # sqlite3.Row supports dict()
    except (TypeError, ValueError):
        return {}


async def get_active(db) -> "dict | None":
    """The current active uprising row as a dict, or None."""
    try:
        row = await db.fetchone(
            "SELECT * FROM communal_objective WHERE state = ? "
            "ORDER BY id DESC LIMIT 1",
            (CO.STATE_ACTIVE,),
        )
    except Exception:
        log.debug("[communal_rt] get_active query failed", exc_info=True)
        return None
    d = _row_to_dict(row)
    return d or None


async def _latest_any(db) -> "dict | None":
    try:
        row = await db.fetchone(
            "SELECT * FROM communal_objective ORDER BY id DESC LIMIT 1"
        )
    except Exception:
        return None
    d = _row_to_dict(row)
    return d or None


# Cooldown between a resolved uprising and the next one posting (real-time).
REPOST_COOLDOWN_MS = 6 * 60 * 60 * 1000  # 6h breather between weekly-rhythm beats

# Zone-label lookup is best-effort flavor; falls back to the cult's world key.
_WORLD_LABEL = {
    "tatooine": "Tatooine",
    "geonosis": "Geonosis",
    "nar_shaddaa": "Nar Shaddaa",
    "kuat": "Kuat",
    "coruscant": "Coruscant",
}


def _zone_label(cult: "CO.CultDef") -> str:
    return _WORLD_LABEL.get(cult.world_key, cult.world_key.replace("_", " ").title())


async def _post_news(db, event_type: str, summary: str) -> None:
    """Post to director_log so the uprising surfaces in `news`. Best-effort."""
    try:
        from engine.director import get_director
        await get_director().log_event(db, event_type, summary)
    except Exception:
        log.debug("[communal_rt] news post failed (%s)", event_type, exc_info=True)


async def _broadcast(session_mgr, text: str) -> None:
    if session_mgr is None:
        return
    try:
        await session_mgr.broadcast(f"\n  {text}")
    except Exception:
        log.debug("[communal_rt] broadcast failed", exc_info=True)


# ── posting ──────────────────────────────────────────────────────────────────
async def maybe_post(db, session_mgr, now_ms: "int | None" = None) -> "dict | None":
    """If no uprising is active and the repost cooldown has elapsed, post a new one.

    Returns the new row dict if one was posted, else None.
    """
    now = int(now_ms if now_ms is not None else _now_ms())

    active = await get_active(db)
    if active:
        return None

    last = await _latest_any(db)
    rotation = 0
    if last:
        try:
            resolved = float(last.get("resolved_at") or 0)
        except (TypeError, ValueError):
            resolved = 0.0
        if resolved and (now - int(resolved)) < REPOST_COOLDOWN_MS:
            return None  # still in the breather
        try:
            rotation = int(last.get("rotation") or 0) + 1
        except (TypeError, ValueError):
            rotation = 0

    cult = CO.cult_for_index(rotation)
    label = _zone_label(cult)
    deadline = now + CO.DEADLINE_HOURS * 3600 * 1000

    try:
        await db.execute(
            "INSERT INTO communal_objective "
            "(cult_key, zone_key, zone_label, menace, state, contributions_json, "
            " rotation, started_at, deadline_at, advanced_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cult.key, cult.world_key, label, float(CO.MENACE_START),
                CO.STATE_ACTIVE, "{}", int(rotation),
                float(now), float(deadline), float(now), 0.0,
            ),
        )
        await db.commit()
    except Exception:
        log.warning("[communal_rt] failed to post uprising", exc_info=True)
        return None

    await _broadcast(session_mgr, CO.posted_broadcast(cult, label))
    await _post_news(
        db, "communal_uprising",
        f"{cult.name} has surfaced around {label}: {cult.blurb}. "
        f"Citizens are called to rally.",
    )
    log.info("[communal_rt] posted uprising: %s (rotation %d)", cult.key, rotation)
    # T3.19 telemetry: the objective funnel (catalog C) for the communal lane.
    # char_id=0 — a zone-wide uprising has no single actor; the per-contributor
    # signal rides on the per-strike event in record_strike. Emitted only after
    # the row lands, so the record reflects a real posting.
    try:
        from engine.telemetry import emit_objective as _tele_obj
        _tele_obj("communal", "start", 0, oid=cult.key, reward=0,
                  rotation=int(rotation), zone=cult.world_key)
    except Exception as _e:
        log.debug("communal objective telemetry emit failed: %s", _e)
    posted = await get_active(db)
    # events_playable_scenarios: arm the first stage's site for a staged cult so
    # the scenario is immediately playable. Best-effort; a failure leaves the
    # objective postable as the (legacy) tracker until a `rally`/tick re-arms it.
    try:
        armed = await arm_stage_site(db, session_mgr, posted, now_ms=now)
        if armed is not None:
            posted = armed
    except Exception:
        log.debug("[communal_rt] post-arm scenario failed", exc_info=True)
    return posted


# ── strikes (player participation) ─────────────────────────────────────────────
class StrikeResult:
    """Lightweight result object the parser command renders."""
    __slots__ = ("ok", "reason", "cult", "outcome", "menace", "state", "lines")

    def __init__(self, ok, reason="", cult=None, outcome=None,
                 menace=0.0, state=CO.STATE_ACTIVE, lines=None):
        self.ok = ok
        self.reason = reason            # 'no_active' | 'cooldown' | 'resolved' | ''
        self.cult = cult
        self.outcome = outcome
        self.menace = menace
        self.state = state
        self.lines = lines or []        # extra player-facing lines (cooldown msg etc.)


async def record_strike(db, session_mgr, char: dict,
                        now_ms: "int | None" = None,
                        rng=None) -> StrikeResult:
    """Resolve one player strike against the active cult.

    Rolls the character's best cross-playstyle pool (engine.dice), applies the
    pure menace reduction, persists the new menace + the contributor's points and
    cooldown, broadcasts the blow, and — if the strike routs the cult — resolves
    the win inline so the finisher sees the payoff immediately.
    """
    active = await get_active(db)
    if not active:
        return StrikeResult(False, reason="no_active")

    cult = CO.CULT_BY_KEY.get(active.get("cult_key", ""))
    if cult is None:
        return StrikeResult(False, reason="no_active")

    now = int(now_ms if now_ms is not None else _now_ms())
    contribs = _parse_json(active.get("contributions_json"), {})
    cid = str(int(char["id"]))
    mine = contribs.get(cid) or {}

    # per-character strike cooldown
    last_strike = float(mine.get("last_strike_at") or 0)
    if last_strike and (now - int(last_strike)) < CO.STRIKE_COOLDOWN_S * 1000:
        left = CO.STRIKE_COOLDOWN_S - (now - int(last_strike)) // 1000
        return StrikeResult(
            False, reason="cooldown", cult=cult,
            lines=[CO.strike_cooldown_line(int(left))],
        )

    # roll the best cross-playstyle pool
    skills = _parse_json(char.get("skills"), {})
    attrs = _parse_json(char.get("attributes"), {})
    pips = CO.best_strike_pool_pips(skills, attrs)
    # EVENT staged scenario (2026-06-23): a STAGED cult resolves the CURRENT
    # stage with THAT stage's relevant skills, so playstyle matters; its win is
    # stage-completion and the menace stays as the failure timer. The other cults
    # are untouched (the _staged guards below).
    from engine import staged_event as _SE
    _staged = _SE.is_staged(cult.key)
    _stage_state = _SE.get_stage_state(contribs) if _staged else None
    if _staged:
        pips = _SE.stage_pool_pips(cult.key, _stage_state, skills, attrs, pips)
    difficulty = CO.strike_difficulty(float(active.get("menace") or 0))

    try:
        from engine.dice import DicePool, difficulty_check
        pool = DicePool(dice=pips // 3, pips=pips % 3)
        check = difficulty_check(pool, difficulty)
        total = check.roll.total
    except Exception:
        log.debug("[communal_rt] dice roll failed; treating as miss", exc_info=True)
        total = 0

    outcome = CO.apply_strike(float(active.get("menace") or 0), total, difficulty)

    # persist the contributor's cooldown always; points only on a successful blow
    mine["last_strike_at"] = float(now)
    if outcome.success:
        mine["points"] = int(mine.get("points") or 0) + int(round(outcome.reduction))
    contribs[cid] = mine

    _all_cleared = False
    if _staged:
        # The strike advances the stage; the menace is left to the escalation
        # tick (the timer). A staged uprising is WON by clearing the stages and
        # LOST only if the timer runs out.
        _stage_state, _stage_cleared, _all_cleared = _SE.advance(
            cult.key, _stage_state, bool(outcome.success))
        _SE.set_stage_state(contribs, _stage_state)
        new_menace = float(active.get("menace") or 0)
    else:
        new_menace = outcome.menace_after
    try:
        await db.execute(
            "UPDATE communal_objective SET menace = ?, contributions_json = ? "
            "WHERE id = ?",
            (float(new_menace), json.dumps(contribs), int(active["id"])),
        )
        await db.commit()
    except Exception:
        log.warning("[communal_rt] strike persist failed", exc_info=True)

    # personal feedback
    if outcome.success:
        await _broadcast(session_mgr, CO.strike_success_line(cult, outcome))
    # (a miss gets only the direct command reply, not a room/global broadcast)

    # T3.19 telemetry: per-strike participation + difficulty signal. Strikes are
    # cooldown-gated (bounded frequency) and there is at most one active uprising,
    # so emit at full rate — the success/total/difficulty distribution is the
    # direct input to tuning strike_difficulty/DEADLINE_HOURS post-launch.
    try:
        from engine.telemetry import emit as _tele_emit
        _tele_emit("communal_strike", {
            "char_id": int(char["id"]),
            "cult": active.get("cult_key", ""),
            "success": bool(outcome.success),
            "difficulty": int(difficulty),
            "total": int(total),
            "menace_after": round(float(new_menace), 1),
            "pips": int(pips),
        })
    except Exception as _e:
        log.debug("communal_strike telemetry emit failed: %s", _e)

    if _staged:
        _t = CO.resolve_state(new_menace, now,
                              int(float(active.get("deadline_at") or 0)))
        state = CO.STATE_WON if _all_cleared else (
            CO.STATE_LOST if _t == CO.STATE_LOST else CO.STATE_ACTIVE)
    else:
        state = CO.resolve_state(new_menace, now,
                                 int(float(active.get("deadline_at") or 0)))
    if state == CO.STATE_WON:
        await _finalize(db, session_mgr, active, contribs, won=True, now_ms=now)

    return StrikeResult(
        outcome.success,
        reason="" if outcome.success else "miss",
        cult=cult, outcome=outcome, menace=new_menace, state=state,
    )


# ── staged-event scenario orchestration ──────────────────────────────────────
# events_playable_scenarios_design_v1 (2026-06-24): a STAGED cult (hollow_sun)
# is a PLAYABLE SITE SCENARIO. Instead of grinding the `rally strike` counter,
# players travel to an anchored site and `investigate` a LIVE anomaly per stage:
# a wave-combat anomaly, then a skill anomaly (slice the cistern), then a boss.
# Clearing the stage's anomaly advances the stage cursor and arms the next; the
# menace meter stays as the failure timer. All gameplay + rewards ride the
# EXISTING wilderness-anomaly machinery — no new system, no new faucet.
#
# These helpers are best-effort and guarded exactly like the rest of the
# runtime: any failure logs and degrades, never aborting a command or tick. The
# Situation-Board contract (get_active row columns) is untouched — scenario
# state lives entirely in contributions_json["_stage"].

async def _resolve_scenario_site_room(db, cult) -> "tuple[int, int | None] | None":
    """Pick the anchor room + zone for a staged cult's scenario site, reusing
    the anomaly substrate's landmark-anchor logic. Returns (room_id, zone_id)
    or None."""
    try:
        from engine import staged_event as SE
        region = SE.scenario_region(cult.key)
        if not region:
            return None
        import random as _random
        from engine.wilderness_anomalies import _pick_anchor_room
        return await _pick_anchor_room(db, region, _random.Random())
    except Exception:
        log.debug("[communal_rt] scenario site resolve failed", exc_info=True)
        return None


async def _site_label(db, room_id: "int | None") -> "str | None":
    if room_id is None:
        return None
    try:
        room = await db.get_room(int(room_id))
        return (room or {}).get("name") if room else None
    except Exception:
        return None


async def arm_stage_site(db, session_mgr, active: dict,
                         now_ms: "int | None" = None) -> "dict | None":
    """Arm the CURRENT stage of a staged cult: ensure the site room is chosen
    and the stage's live anomaly is spawned, recording the site_room_id +
    anomaly_id into contributions_json["_stage"]. Idempotent — if the current
    stage already has a live (unresolved) anomaly, this is a no-op.

    Returns the updated active row dict, or None if not staged / nothing to do.
    """
    if not active:
        return None
    try:
        from engine import staged_event as SE
        from engine import wilderness_anomalies as WA
    except Exception:
        return None

    cult = CO.CULT_BY_KEY.get(active.get("cult_key", ""))
    if cult is None or not SE.is_staged(cult.key):
        return None

    contribs = _parse_json(active.get("contributions_json"), {})
    state = SE.get_stage_state(contribs)

    spec = SE.current_stage_anomaly_spec(cult.key, state)
    if spec is None:
        return None  # all stages cleared, or no anomaly for this stage
    template_key, tier = spec

    # Already have a live anomaly for this stage?
    existing_id = state.get("anomaly_id")
    if existing_id is not None:
        anom = WA.find_anomaly_globally(int(existing_id))
        if anom is not None and not anom.resolved:
            return active  # still live — nothing to do

    # Resolve / reuse the site room.
    room_id = state.get("site_room_id")
    zone_id = None
    if room_id is None:
        site = await _resolve_scenario_site_room(db, cult)
        if site is None:
            log.debug("[communal_rt] no scenario site room for %s", cult.key)
            return None
        room_id, zone_id = site

    region = SE.scenario_region(cult.key)
    try:
        anomaly = await WA.spawn_scenario_anomaly(
            db, region, template_key, int(room_id),
            tier=int(tier), zone_id=zone_id,
            session_mgr=session_mgr,
        )
    except Exception:
        log.warning("[communal_rt] scenario anomaly spawn failed", exc_info=True)
        return None
    if anomaly is None:
        return None

    state["site_room_id"] = int(room_id)
    state["anomaly_id"] = int(anomaly.id)
    SE.set_stage_state(contribs, state)
    try:
        await db.execute(
            "UPDATE communal_objective SET contributions_json = ? WHERE id = ?",
            (json.dumps(contribs), int(active["id"])),
        )
        await db.commit()
    except Exception:
        log.warning("[communal_rt] arm_stage_site persist failed", exc_info=True)
        return None

    log.info("[communal_rt] armed stage %d (%s) for %s at room %s (anomaly #%d)",
             state["idx"] + 1, template_key, cult.key, room_id, anomaly.id)
    return await get_active(db)


async def on_scenario_progress(db, session_mgr, active: dict,
                               now_ms: "int | None" = None) -> "dict | None":
    """If a staged cult's current-stage anomaly has been RESOLVED, advance the
    stage cursor and arm the next stage's anomaly (or finalize the win on the
    last stage). Poll-driven: called from the `rally` view and the tick, so the
    scenario advances without modifying the anomaly kill hook.

    Returns the updated active row dict (or None if not staged / no change).
    """
    if not active:
        return None
    try:
        from engine import staged_event as SE
        from engine import wilderness_anomalies as WA
    except Exception:
        return None

    cult = CO.CULT_BY_KEY.get(active.get("cult_key", ""))
    if cult is None or not SE.is_staged(cult.key):
        return None

    now = int(now_ms if now_ms is not None else _now_ms())
    contribs = _parse_json(active.get("contributions_json"), {})
    state = SE.get_stage_state(contribs)

    anomaly_id = state.get("anomaly_id")
    if anomaly_id is None:
        # No live anomaly recorded — try to arm the current stage.
        return await arm_stage_site(db, session_mgr, active, now_ms=now)

    anom = WA.find_anomaly_globally(int(anomaly_id))
    if anom is not None and not anom.resolved:
        return None  # stage anomaly still in play — gameplay ongoing

    # The stage's anomaly is no longer actively in play. is_expired is purely
    # time-based, so a RESOLVED anomaly lingers (findable, resolved=True) until its
    # expiry; this poll runs every tick and reliably catches resolved=True before
    # prune. Therefore find->None means the anomaly aged out UNcleared: re-arm the
    # SAME stage rather than free-advancing on a timeout. A staged scenario must be
    # CLEARED, not won by waiting — the menace timer is the overall failure clock.
    if not (anom is not None and anom.resolved):
        return await arm_stage_site(db, session_mgr, active, now_ms=now)

    # Cleared (a real resolve) — advance the stage cursor (one clear = one stage).
    new_state, all_cleared = SE.complete_current_stage(cult.key, state)
    # Drop the consumed anomaly id; keep the site room for the next stage.
    new_state["site_room_id"] = state.get("site_room_id")
    new_state["anomaly_id"] = None
    SE.set_stage_state(contribs, new_state)
    try:
        await db.execute(
            "UPDATE communal_objective SET contributions_json = ? WHERE id = ?",
            (json.dumps(contribs), int(active["id"])),
        )
        await db.commit()
    except Exception:
        log.warning("[communal_rt] scenario advance persist failed", exc_info=True)

    log.info("[communal_rt] %s scenario advanced: stage now %d (all_cleared=%s)",
             cult.key, new_state["idx"] + 1, all_cleared)

    refreshed = await get_active(db)
    if all_cleared:
        # Final stage cleared → win the objective through the existing payout.
        await _finalize(db, session_mgr, refreshed or active, contribs,
                        won=True, now_ms=now)
        return CO.STATE_WON   # explicit win signal — the caller no longer infers
        #                       a win from get_active() returning None (which also
        #                       fires on a transient DB error: see advance_and_resolve).

    # Arm the next stage's anomaly.
    return await arm_stage_site(db, session_mgr, refreshed or active, now_ms=now)


# ── escalation + resolution (tick-driven) ────────────────────────────────────
async def advance_and_resolve(db, session_mgr,
                              now_ms: "int | None" = None) -> "str | None":
    """Escalate the active uprising and resolve win/lose. Returns the new state or None."""
    active = await get_active(db)
    if not active:
        return None

    cult = CO.CULT_BY_KEY.get(active.get("cult_key", ""))
    if cult is None:
        return None

    now = int(now_ms if now_ms is not None else _now_ms())

    # events_playable_scenarios: advance a staged cult's site scenario (poll the
    # current stage's anomaly; arm the next stage on clear, win on last clear).
    # If the scenario just won the objective, it's finalized and no longer active.
    try:
        from engine import staged_event as _SE
        if _SE.is_staged(cult.key):
            scenario_result = await on_scenario_progress(
                db, session_mgr, active, now_ms=now)
            if scenario_result == CO.STATE_WON:
                return CO.STATE_WON  # scenario cleared the final stage (explicit)
            active = await get_active(db)
            if not active:
                # No active row: a transient get_active failure OR the objective
                # ended elsewhere — do NOT infer a win (that was the old bug).
                return None
    except Exception:
        log.debug("[communal_rt] tick scenario progress failed", exc_info=True)

    advanced_at = float(active.get("advanced_at") or active.get("started_at") or now)
    minutes = max(0.0, (now - int(advanced_at)) / 60000.0)

    cur_menace = float(active.get("menace") or 0)
    deadline = int(float(active.get("deadline_at") or 0))

    # Resolve a state that's ALREADY terminal before touching menace — escalation
    # only ever raises menace, so it must never un-win a cult a strike just routed
    # (e.g. if a strike's inline finalize didn't run, the tick still closes the win).
    pre_state = CO.resolve_state(cur_menace, now, deadline)
    if pre_state != CO.STATE_ACTIVE:
        contribs = _parse_json(active.get("contributions_json"), {})
        active = dict(active)
        active["menace"] = cur_menace
        await _finalize(db, session_mgr, active, contribs,
                        won=(pre_state == CO.STATE_WON), now_ms=now)
        return pre_state

    menace = CO.advance_menace(cur_menace, minutes)
    state = CO.resolve_state(menace, now, deadline)

    if state == CO.STATE_ACTIVE:
        # just record the escalation; occasionally nudge the room/global feed
        try:
            await db.execute(
                "UPDATE communal_objective SET menace = ?, advanced_at = ? WHERE id = ?",
                (float(menace), float(now), int(active["id"])),
            )
            await db.commit()
        except Exception:
            log.debug("[communal_rt] escalation persist failed", exc_info=True)
        # nudge when the cult crosses into a worse tier
        tier_changed = CO.menace_tier(menace) != CO.menace_tier(cur_menace)
        if tier_changed:
            await _broadcast(session_mgr, CO.escalation_broadcast(cult, menace))
        # T3.19 telemetry: the menace ESCALATION leg — the uncontested climb the
        # strike + completion events can't reconstruct. Between strikes THIS tick
        # is the only record of menace rising, so it's the direct tuning signal
        # for MENACE_PER_MINUTE / DEADLINE_HOURS / strike balance: does the cult
        # outrun a small community? are losses driven by the timer or by menace
        # maxing? is the community keeping pace (contributors) with the climb?
        # One uprising at a time on a 120s cadence → low volume, full capture by
        # default (sample-tunable). Only emits on a real climb (skips a zero-
        # elapsed no-op). Fail-open: a telemetry break never disturbs escalation.
        if menace > cur_menace:
            try:
                from engine.telemetry import emit as _tele_emit
                from engine import staged_event as _SE_t
                _co = _parse_json(active.get("contributions_json"), {})
                _contribs = sum(1 for _k in _co
                                if str(_k).lstrip("-").isdigit())
                try:
                    from engine.tunables import get_tunable
                    _sample = float(get_tunable(
                        "telemetry.communal_menace_sample", 1.0))
                except Exception:
                    _sample = 1.0
                _tele_emit("communal_menace", {
                    "cult": active.get("cult_key", ""),
                    "menace_before": round(float(cur_menace), 1),
                    "menace_after": round(float(menace), 1),
                    "minutes": round(float(minutes), 2),
                    "tier_before": CO.menace_tier(cur_menace),
                    "tier_after": CO.menace_tier(menace),
                    "tier_changed": bool(tier_changed),
                    "contributors": int(_contribs),
                    "staged": bool(_SE_t.is_staged(cult.key)),
                    "rotation": int(active.get("rotation") or 0),
                }, sample=_sample)
            except Exception as _e:
                log.debug("communal_menace telemetry emit failed: %s", _e)
        return CO.STATE_ACTIVE

    # win or loss
    contribs = _parse_json(active.get("contributions_json"), {})
    # reflect the final menace on the row before finalizing
    active = dict(active)
    active["menace"] = menace
    await _finalize(db, session_mgr, active, contribs,
                    won=(state == CO.STATE_WON), now_ms=now)
    return state


async def _finalize(db, session_mgr, active: dict, contribs: dict,
                    won: bool, now_ms: int) -> None:
    """Set terminal state, broadcast, post news, and (on a win) pay rewards.

    Idempotent-ish: re-stamps state/resolved_at; reward payout only runs while the
    row is transitioning out of 'active' (guarded by the UPDATE ... WHERE state=active).
    """
    cult = CO.CULT_BY_KEY.get(active.get("cult_key", ""))
    label = active.get("zone_label") or (_zone_label(cult) if cult else "the sector")
    state = CO.STATE_WON if won else CO.STATE_LOST

    # transition the row only if it's still active (prevents double payout under
    # a tick/strike race — last_writer-wins on the menace, single-writer on state)
    try:
        cur = await db.execute(
            "UPDATE communal_objective SET state = ?, menace = ?, resolved_at = ? "
            "WHERE id = ? AND state = ?",
            (state, float(active.get("menace") or 0), float(now_ms),
             int(active["id"]), CO.STATE_ACTIVE),
        )
        await db.commit()
        changed = getattr(cur, "rowcount", 1)
    except Exception:
        log.warning("[communal_rt] finalize state write failed", exc_info=True)
        return

    if changed == 0:
        return  # someone else already resolved this uprising

    # T3.19 telemetry: the objective-funnel close for the communal lane. The
    # state UPDATE above is the single-writer race guard (rowcount==0 returns
    # early), so this emits EXACTLY once per uprising. Phase is always
    # "complete" (an uprising always resolves); the ``won`` flag carries
    # win-vs-loss and ``contributors`` measures engagement. No credits change
    # hands (rep-only payout), so reward=0.
    try:
        from engine.telemetry import emit_objective as _tele_obj
        _tele_obj("communal", "complete", 0,
                  oid=active.get("cult_key", ""), reward=0,
                  won=bool(won), contributors=len(contribs or {}),
                  menace=round(float(active.get("menace") or 0), 1),
                  rotation=int(active.get("rotation") or 0))
    except Exception as _e:
        log.debug("communal objective telemetry emit failed: %s", _e)

    if cult is not None:
        if won:
            await _broadcast(session_mgr, CO.won_broadcast(cult, label))
            await _post_news(db, "communal_resolved",
                             f"{cult.name} has been broken and scattered from {label} "
                             f"through a shared effort.")
        else:
            await _broadcast(session_mgr, CO.lost_broadcast(cult, label))
            await _post_news(db, "communal_resolved",
                             f"{cult.name} entrenched around {label}; the moment to "
                             f"rout them passed.")

    if won:
        await _distribute_rewards(db, session_mgr, cult, contribs)


async def _distribute_rewards(db, session_mgr, cult, contribs: dict) -> None:
    """Pay Republic rep + the commemorative status flag to contributors. No credits."""
    if not contribs:
        return
    total = sum(int((v or {}).get("points") or 0) for v in contribs.values())
    if total <= 0:
        return

    try:
        from engine.organizations import adjust_rep
    except Exception:
        log.debug("[communal_rt] adjust_rep unavailable; skipping rep payout",
                  exc_info=True)
        adjust_rep = None

    cult_name = cult.name if cult else "a dark-side cult"
    for cid_str, rec in contribs.items():
        pts = int((rec or {}).get("points") or 0)
        if pts <= 0:
            continue
        try:
            cid = int(cid_str)
        except (TypeError, ValueError):
            continue

        rep_delta = CO.reward_rep_for_share(pts, total, won=True)
        title = CO.earns_title(pts, total, won=True)

        # 1) faction rep (adjust_rep self-persists the character's attributes)
        if adjust_rep and rep_delta:
            try:
                char = await db.get_character(cid)
                if char:
                    await adjust_rep(
                        char, CO.REP_FACTION, db,
                        delta=int(rep_delta),
                        reason=f"Helped rout {cult_name}",
                    )
            except Exception:
                log.debug("[communal_rt] rep payout failed for %s", cid, exc_info=True)

        # 2) commemorative III.2 status flag (separate clean write)
        if title:
            try:
                char2 = await db.get_character(cid)
                if char2:
                    a = _parse_json(char2.get("attributes"), {})
                    wins = a.get("communal_objective_wins") or []
                    if not isinstance(wins, list):
                        wins = []
                    if cult and cult.key not in wins:
                        wins.append(cult.key)
                    a["communal_objective_wins"] = wins
                    await db.save_character(cid, attributes=json.dumps(a))
            except Exception:
                log.debug("[communal_rt] title flag write failed for %s", cid,
                          exc_info=True)


# ── board rendering helper (for the +rally view) ─────────────────────────────
def render_board(active: "dict | None", now_ms=None) -> list[str]:
    """Build the player-facing rally board lines from an active row (pure-ish).

    `now_ms` (defaulting to the current time) drives the deadline countdown; pass
    an explicit value in tests.
    """
    if not active:
        return [CO._DIM + "No uprising is active right now. The galaxy is "
                "uneasy, but quiet." + CO._RESET]
    cult = CO.CULT_BY_KEY.get(active.get("cult_key", ""))
    if cult is None:
        return [CO._DIM + "No uprising is active right now." + CO._RESET]

    now = int(now_ms if now_ms is not None else _now_ms())
    menace = float(active.get("menace") or 0)
    label = active.get("zone_label") or "the sector"
    deadline = int(float(active.get("deadline_at") or 0))
    contribs = _parse_json(active.get("contributions_json"), {})
    n_contrib = sum(1 for v in contribs.values() if int((v or {}).get("points") or 0) > 0)

    lines = [
        f"{CO._RED}{CO._BOLD}{cult.name}{CO._RESET} — {cult.blurb}.",
        f"  Centered on {CO._CYAN}{label}{CO._RESET}.",
        f"  Menace: {CO.menace_bar(menace)}",
        f"  {CO.time_left_line(deadline, now)}",
        f"  Rally to {cult.rally_hook}.",
        f"  {CO._DIM}{n_contrib} citizen(s) have answered the call so far. "
        f"Type 'rally strike' to make your move.{CO._RESET}",
    ]
    return lines


# ── admin / Director force-controls (operability for verification + GM beats) ──
async def force_post(db, session_mgr, cult_key=None, now_ms=None) -> "dict | None":
    """ADMIN: post a fresh uprising NOW, bypassing the repost cooldown and the
    no-active gate. Silently clears any currently-active uprising first (no
    reward, no 'entrenches' broadcast). `cult_key` optionally picks the cult;
    otherwise the rotation default is used. Mirrors maybe_post's INSERT."""
    now = int(now_ms if now_ms is not None else _now_ms())

    active = await get_active(db)
    if active:
        try:
            await db.execute(
                "UPDATE communal_objective SET state = ?, resolved_at = ? "
                "WHERE id = ? AND state = ?",
                (CO.STATE_LOST, float(now), int(active["id"]), CO.STATE_ACTIVE),
            )
            await db.commit()
        except Exception:
            log.debug("[communal_rt] force_post: clear active failed", exc_info=True)

    last = await _latest_any(db)
    rotation = 0
    if last:
        try:
            rotation = int(last.get("rotation") or 0) + 1
        except (TypeError, ValueError):
            rotation = 0

    cult = CO.CULT_BY_KEY.get((cult_key or "").strip().lower()) \
        or CO.cult_for_index(rotation)
    label = _zone_label(cult)
    deadline = now + CO.DEADLINE_HOURS * 3600 * 1000

    try:
        await db.execute(
            "INSERT INTO communal_objective "
            "(cult_key, zone_key, zone_label, menace, state, contributions_json, "
            " rotation, started_at, deadline_at, advanced_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cult.key, cult.world_key, label, float(CO.MENACE_START),
                CO.STATE_ACTIVE, "{}", int(rotation),
                float(now), float(deadline), float(now), 0.0,
            ),
        )
        await db.commit()
    except Exception:
        log.warning("[communal_rt] force_post insert failed", exc_info=True)
        return None

    await _broadcast(session_mgr, CO.posted_broadcast(cult, label))
    await _post_news(
        db, "communal_uprising",
        f"{cult.name} has surfaced around {label}: {cult.blurb}. "
        f"Citizens are called to rally.",
    )
    log.info("[communal_rt] ADMIN force_post: %s (rotation %d)", cult.key, rotation)
    posted = await get_active(db)
    try:
        armed = await arm_stage_site(db, session_mgr, posted, now_ms=now)
        if armed is not None:
            posted = armed
    except Exception:
        log.debug("[communal_rt] force_post scenario arm failed", exc_info=True)
    return posted


async def force_resolve(db, session_mgr, won: bool,
                        now_ms=None) -> "str | None":
    """ADMIN: resolve the active uprising immediately as won/lost. A forced win
    pays the normal rewards from whatever contributions exist. Returns the new
    state, or None if nothing was active."""
    now = int(now_ms if now_ms is not None else _now_ms())
    active = await get_active(db)
    if not active:
        return None
    contribs = _parse_json(active.get("contributions_json"), {})
    await _finalize(db, session_mgr, dict(active), contribs,
                    won=bool(won), now_ms=now)
    return CO.STATE_WON if won else CO.STATE_LOST


async def force_clear(db, session_mgr=None, now_ms=None) -> bool:
    """ADMIN: silently cancel the active uprising (no reward, no broadcast).
    Returns True if one was cleared."""
    now = int(now_ms if now_ms is not None else _now_ms())
    active = await get_active(db)
    if not active:
        return False
    try:
        cur = await db.execute(
            "UPDATE communal_objective SET state = ?, resolved_at = ? "
            "WHERE id = ? AND state = ?",
            (CO.STATE_LOST, float(now), int(active["id"]), CO.STATE_ACTIVE),
        )
        await db.commit()
        return getattr(cur, "rowcount", 1) != 0
    except Exception:
        log.debug("[communal_rt] force_clear failed", exc_info=True)
        return False
