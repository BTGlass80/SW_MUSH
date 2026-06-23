# -*- coding: utf-8 -*-
"""
engine/chain_rewards.py — F.8.c.2.d chain graduation reward delivery.

When a tutorial chain graduates, the chain's
``graduation`` block carries up to five reward fields:

  * ``credits: int``           — credits to award
  * ``faction_rep: dict``       — {faction_code: int delta}
  * ``items: list[str]``        — item keys to grant
  * ``achievements: list[str]`` — achievement keys to mark
  * ``follow_up_hint: str``     — one-line narrative hint shown
                                  to the player after graduation

Pre-F.8.c.2.d the dataclass exposed all five fields but no engine
consumer read them — graduating a chain teleported the player but
did not deliver any of the authored rewards.

This module closes the gap. Called from
``chain_events._try_advance`` after ``apply_graduation`` persists
the room change, BEFORE ``_persist_attrs`` saves the chain state.

Why this runs after the teleport persist
----------------------------------------
``apply_graduation`` mutates ``char["room_id"]``. Reward delivery
calls ``adjust_rep`` which reads ``char["id"]``, and
``add_to_inventory`` / ``adjust_credits`` which
read fresh DB state. None of these need the room change to be in
the DB first, but running rewards AFTER the teleport persist
gives the player a single coherent save chain:

  1. ``save_character(room_id=...)``   (apply_graduation)
  2. ``adjust_credits``               (this module, credit award via the F1 ledger chokepoint)
  3. ``adjust_rep`` per faction        (this module, rep awards)
  4. ``add_to_inventory`` per item     (this module, item grants)
  5. ``_persist_attrs`` (chain state with pending_drop_room_id +
                         graduation_summary)                  (chain_events)

If any step fails, prior steps remain. The chain stays
``graduated`` regardless. A reward delivery failure leaves the
player teleported, possibly with partial rewards. The
graduation_summary stamped onto chargen_notes records what was
attempted; downstream tooling can audit and re-deliver if needed.

Why item_acquired chain hook is safe to re-fire here
----------------------------------------------------
``db.add_to_inventory`` fires ``on_item_acquired_by_char_id``
unconditionally. That hook calls ``_get_active_step`` which
checks ``completion_state == "active"``. By the time
``apply_graduation_rewards`` runs, the chain has already
graduated (state is "graduated"), so the hook returns False
without firing the dispatcher. No infinite loop, no spurious
chain advance.

Tested by tests/test_f8c2d_chain_rewards.py.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional, Mapping

log = logging.getLogger(__name__)


_TUTORIAL_CHAIN_KEY = "tutorial_chain"
_GRADUATION_SUMMARY_KEY = "graduation_summary"
_GRADUATION_ACHIEVEMENTS_KEY = "graduation_achievements"


# ── chargen_notes accessors ─────────────────────────────────────────


def _read_chargen_notes(char: Mapping) -> dict:
    """Read chargen_notes JSON defensively. Returns {} on any
    anomaly. Mirrors lightsaber_construction._read_chargen_notes."""
    raw = char.get("chargen_notes") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


# ── Item key humanization ──────────────────────────────────────────


_ITEM_NAME_OVERRIDES = {
    # Hand-tuned names for items that don't humanize cleanly from
    # their snake_case keys. Fall back to title-case otherwise.
    "dc15_blaster_rifle":     "DC-15 Blaster Rifle",
    "e5_blaster_rifle":       "E-5 Blaster Rifle",
    "kdy_apprentice_pass":    "KDY Apprentice Pass",
    "bhg_license_card":       "BHG License Card",
    "smugglers_baffle_kit":   "Smuggler's Baffle Kit",
    "fake_republic_id":       "Fake Republic ID",
    # F.8.c.2.b₄: tutorial step-reward items
    "sealed_data_packet":     "Sealed Data Packet",
}


# Per-key special properties for step-reward items. Each entry is a
# dict that gets shallow-merged onto the base item shape; lets us
# mark items consumable, give them custom use_message flavor, etc.
_STEP_ITEM_PROPERTIES = {
    "sealed_data_packet": {
        "consumable": True,
        "use_message": (
            "The packet flickers as it reads your bio-sig. Lines of "
            "text scroll past — a handler ID, a comm frequency, and "
            "an address: Coruscant Works, locker 144. Memorize. "
            "Destroy. The packet dissolves into ash."
        ),
        "description": (
            "A small black packet, sealed with bio-sig encryption. "
            "Use it to read the contents within."
        ),
    },
}


def _humanize_item_key(key: str) -> str:
    """Turn an item key like ``dc15_blaster_rifle`` into a
    display name. Uses the overrides map first; otherwise
    converts ``snake_case`` to ``Title Case``."""
    if not key:
        return ""
    if key in _ITEM_NAME_OVERRIDES:
        return _ITEM_NAME_OVERRIDES[key]
    # snake_case → Title Case
    return key.replace("_", " ").title()


def _build_graduation_item(item_key: str, chain_id: str,
                           chain_label: str) -> dict:
    """Build an item dict for a graduation reward.

    H1 fix (2026-06-17): prefer registry name/slot for weapon/armor keys
    so find_carried_gear can match the item after it's in inventory.
    Fall back to _humanize_item_key for narrative props that are
    legitimately registry-less (comlink_basic, fake_republic_id, etc.).

    Marking each gift with `chain_grad: <chain_id>` lets a future
    item-rebalance pass identify graduation-gift items vs. items
    obtained through play.
    """
    from engine.weapons import get_weapon_registry
    wr = get_weapon_registry()
    reg_entry = wr.get(item_key)
    if reg_entry is not None:
        item_name = reg_entry.name
        item_slot = "armor" if reg_entry.is_armor else "weapon"
    else:
        item_name = _humanize_item_key(item_key)
        item_slot = "misc"
    return {
        "key": item_key,
        "name": item_name,
        "slot": item_slot,
        "description": (
            f"A graduation gift from your {chain_label} training. "
            "Standard issue."
        ),
        "chain_grad": chain_id,
        "acquired_at": time.time(),
    }


def _build_step_item(item_key: str, chain_id: str, step: int) -> dict:
    """Build an item dict for a per-step chain reward (F.8.c.2.b₄).

    H1 fix (2026-06-17): prefer registry name/slot for weapon/armor keys
    so find_carried_gear can match the item after it's in inventory.
    Fall back to _humanize_item_key for narrative props that are
    legitimately registry-less.

    Per-key overrides from ``_STEP_ITEM_PROPERTIES`` get shallow-merged
    onto the base shape — that's where ``consumable: true``,
    ``use_message: ...``, narrative ``description`` overrides land.
    The override's ``name`` field (if any) takes precedence over the
    registry name, preserving existing narrative-prop behaviour.
    """
    from engine.weapons import get_weapon_registry
    wr = get_weapon_registry()
    reg_entry = wr.get(item_key)
    if reg_entry is not None:
        item_name = reg_entry.name
        item_slot = "armor" if reg_entry.is_armor else "weapon"
    else:
        item_name = _humanize_item_key(item_key)
        item_slot = "misc"
    base = {
        "key": item_key,
        "name": item_name,
        "slot": item_slot,
        "description": (
            f"Acquired during your tutorial training "
            f"({chain_id}, step {step})."
        ),
        "chain_step": f"{chain_id}:{step}",
        "acquired_at": time.time(),
    }
    # Apply per-key overrides (consumable, use_message, etc.)
    overrides = _STEP_ITEM_PROPERTIES.get(item_key, {})
    if overrides:
        base.update(overrides)
    return base


# ── Step reward delivery ───────────────────────────────────────────


async def apply_step_rewards(db, char: dict, step,
                             chain_id: str) -> dict:
    """Deliver per-step rewards on chain advancement.

    Called from ``chain_events._try_advance`` after a step
    successfully advances. Reads ``step.reward`` (a dict on the
    Step dataclass) and delivers any rewards declared:

      * ``items: list[str]`` — item keys to grant (narrative props
        the next step uses/examines)
      * ``credits: int`` — credits via the metered ``adjust_credits``
        faucet (tag ``chain_step_reward``)
      * ``faction_rep: {code: delta}`` — rep via the ``adjust_rep``
        funnel

    T5-questline arc (2026-06-13): credits + faction_rep are now
    CONSUMED (previously items-only — authored per-step credits/rep
    were silently dropped, a phantom-producer gap). The richer
    master-trainer questlines award incremental rep across their
    steps, so per-step rep delivery is load-bearing for them; the
    onboarding chains that carried per-step rep now deliver it too
    (latent debt closed). All movement goes through the same funnels
    graduation uses — no raw credit/rep writes.

    Per-step rewards are simpler than graduation rewards — most
    chain steps have no rewards (``reward: {}``).

    Idempotent at the chain dispatcher level — ``_try_advance``
    only fires this once per step transition. Failure-tolerant:
    each reward slot's errors are logged and swallowed; the chain
    advancement itself never blocks on reward delivery.

    Returns a small report dict:
        {
          "items_granted": [item_key, ...],
          "items_failed":  [item_key, ...],
          "credits_awarded": int,
          "rep_awarded":   {code: new_score, ...},
          "errors":        [error_str, ...],
        }
    """
    report = {
        "items_granted": [],
        "items_failed": [],
        "credits_awarded": 0,
        "rep_awarded": {},
        "errors": [],
    }

    if step is None:
        return report

    rewards = getattr(step, "reward", None) or {}
    if not isinstance(rewards, dict):
        return report

    step_num = int(getattr(step, "step", 0) or 0)

    # ── Credits (metered faucet) ────────────────────────────────────
    credits_amount = int(rewards.get("credits", 0) or 0)
    if credits_amount > 0:
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], credits_amount, "chain_step_reward")
            report["credits_awarded"] = credits_amount
            log.info("[chain_rewards] step +%d credits to char %s "
                     "(chain=%s, step=%d)",
                     credits_amount, char.get("id"), chain_id, step_num)
        except Exception as e:
            log.warning("[chain_rewards] step credits award failed "
                        "for char %s: %s", char.get("id"), e,
                        exc_info=True)
            report["errors"].append(f"credits: {e}")

    # ── Faction rep (funnel) ────────────────────────────────────────
    rep_block = rewards.get("faction_rep") or {}
    if isinstance(rep_block, dict) and rep_block:
        try:
            from engine.organizations import adjust_rep
        except Exception:
            adjust_rep = None
            report["errors"].append("faction_rep: adjust_rep unavailable")
        if adjust_rep is not None:
            for faction_code, delta in rep_block.items():
                try:
                    delta_int = int(delta)
                    if delta_int == 0:
                        continue
                    new_score = await adjust_rep(
                        char, faction_code, db,
                        delta=delta_int,
                        reason=f"chain_step:{chain_id}:{step_num}",
                    )
                    report["rep_awarded"][faction_code] = new_score
                    log.info("[chain_rewards] step char %s rep %s %+d "
                             "(new=%s, chain=%s, step=%d)",
                             char.get("id"), faction_code, delta_int,
                             new_score, chain_id, step_num)
                except Exception as e:
                    log.warning("[chain_rewards] step rep adjust failed "
                                "for %s/%s: %s", char.get("id"),
                                faction_code, e, exc_info=True)
                    report["errors"].append(f"rep[{faction_code}]: {e}")

    # ── Items ───────────────────────────────────────────────────────
    items_list = rewards.get("items") or []
    if isinstance(items_list, list):
        for item_key in items_list:
            if not item_key or not isinstance(item_key, str):
                continue
            try:
                item_dict = _build_step_item(
                    item_key, chain_id, step_num)
                await db.add_to_inventory(char["id"], item_dict)
                report["items_granted"].append(item_key)
                log.info("[chain_rewards] step item %s granted to char %s "
                         "(chain=%s, step=%d)",
                         item_key, char.get("id"), chain_id, step_num)
            except Exception as e:
                log.warning("[chain_rewards] step item grant failed "
                            "for %s: %s", item_key, e, exc_info=True)
                report["items_failed"].append(item_key)
                report["errors"].append(f"item[{item_key}]: {e}")

    # ── Telemetry (T3.19, onboarding-economy funnel) ────────────────
    # Emit ONLY when a reward was actually delivered — most chain steps
    # carry ``reward: {}`` and would otherwise spam empty events. The
    # single ``chain_reward`` event type (phase="step"|"graduation",
    # mirroring the ``objective`` funnel) lets the offline funnel measure
    # how much credit/item/rep flow the onboarding pipeline injects per
    # chain. Buffer-only + offline-flushed → zero gameplay behaviour; it
    # can never disturb the chain advance it observes.
    if (report["credits_awarded"] or report["items_granted"]
            or report["rep_awarded"]):
        try:
            from engine.telemetry import emit as _tele_emit
            _tele_emit("chain_reward", {
                "phase": "step",
                "chain_id": chain_id,
                "step": step_num,
                "char_id": int(char.get("id") or 0),
                "credits": int(report["credits_awarded"]),
                "items": len(report["items_granted"]),
                "rep": len(report["rep_awarded"]),
            })
        except Exception as _e:
            log.debug("chain_reward step telemetry emit failed: %s", _e)

    return report


# ── Public entry point ─────────────────────────────────────────────


async def apply_graduation_rewards(db, char: dict, attrs: dict,
                                   graduation, chain_id: str,
                                   chain_label: str = "") -> dict:
    """Engine-layer chain graduation reward delivery.

    Awards credits, faction rep, items, achievements; stamps a
    ``graduation_summary`` block onto ``chargen_notes`` for the
    parser-side summary line delivery (via
    ``chain_graduation.execute_pending_teleport`` reading the
    summary back) and for later audit / display.

    Pure DB-side: takes no session. The parser-layer finisher
    handles player-visible summary delivery.

    Mutates ``attrs`` in place — caller (chain_events._try_advance)
    will re-persist the chain state. ``chargen_notes`` is also
    mutated and re-saved here in a single ``save_character`` call.

    Returns a report dict (same shape across success/partial/failure):
        {
          "credits_awarded": int,
          "rep_awarded":     {faction_code: new_score | error_str},
          "items_granted":   [item_key, ...],
          "items_failed":    [item_key, ...],
          "achievements":    [ach_key, ...],
          "follow_up_hint":  str,
          "errors":          [error_str, ...],
        }

    Failure-tolerant: each reward type is in its own try/except.
    A failure in one slot doesn't block the others. Errors are
    logged + recorded in the report; the function never raises.
    """
    report = {
        "credits_awarded": 0,
        "rep_awarded": {},
        "items_granted": [],
        "items_failed": [],
        "achievements": [],
        "follow_up_hint": "",
        "errors": [],
    }

    if graduation is None:
        return report

    # ── Credits ─────────────────────────────────────────────────────
    credits_amount = int(getattr(graduation, "credits", 0) or 0)
    if credits_amount > 0:
        try:
            char["credits"] = await db.adjust_credits(char["id"], credits_amount, "chain_reward")
            report["credits_awarded"] = credits_amount
            log.info("[chain_rewards] char %s +%d credits (chain=%s)",
                     char.get("id"), credits_amount, chain_id)
        except Exception as e:
            log.warning("[chain_rewards] credits award failed for "
                        "char %s: %s", char.get("id"), e, exc_info=True)
            report["errors"].append(f"credits: {e}")

    # ── Faction rep ─────────────────────────────────────────────────
    rep_block = getattr(graduation, "faction_rep", None) or {}
    if isinstance(rep_block, dict):
        try:
            from engine.organizations import adjust_rep
        except Exception:
            adjust_rep = None
            report["errors"].append("faction_rep: adjust_rep unavailable")

        if adjust_rep is not None:
            for faction_code, delta in rep_block.items():
                try:
                    delta_int = int(delta)
                    if delta_int == 0:
                        continue
                    new_score = await adjust_rep(
                        char, faction_code, db,
                        delta=delta_int,
                        reason=f"chain_graduation:{chain_id}",
                    )
                    report["rep_awarded"][faction_code] = new_score
                    log.info("[chain_rewards] char %s rep %s %+d "
                             "(new=%s, chain=%s)",
                             char.get("id"), faction_code, delta_int,
                             new_score, chain_id)
                except Exception as e:
                    log.warning("[chain_rewards] rep adjust failed "
                                "for %s/%s: %s", char.get("id"),
                                faction_code, e, exc_info=True)
                    report["rep_awarded"][faction_code] = f"error: {e}"
                    report["errors"].append(
                        f"rep[{faction_code}]: {e}")

    # ── Items ───────────────────────────────────────────────────────
    items_list = getattr(graduation, "items", None) or []
    if isinstance(items_list, list):
        for item_key in items_list:
            if not item_key or not isinstance(item_key, str):
                continue
            try:
                item_dict = _build_graduation_item(
                    item_key, chain_id, chain_label)
                await db.add_to_inventory(char["id"], item_dict)
                report["items_granted"].append(item_key)
                log.info("[chain_rewards] char %s +item %s (chain=%s)",
                         char.get("id"), item_key, chain_id)
            except Exception as e:
                log.warning("[chain_rewards] item grant failed for "
                            "%s: %s", item_key, e, exc_info=True)
                report["items_failed"].append(item_key)
                report["errors"].append(f"item[{item_key}]: {e}")

    # ── Achievements ────────────────────────────────────────────────
    ach_list = getattr(graduation, "achievements", None) or []
    notes = _read_chargen_notes(char)
    if isinstance(ach_list, list):
        existing = list(notes.get(_GRADUATION_ACHIEVEMENTS_KEY, []) or [])
        added_ach = []

        try:
            from engine.achievements import (
                get_achievement, _complete_achievement,
            )
        except Exception:
            get_achievement = None
            _complete_achievement = None

        for ach_key in ach_list:
            if not ach_key or not isinstance(ach_key, str):
                continue
            # Always stamp the chargen_notes fallback so the data
            # is preserved even if the achievement catalog hasn't
            # caught up.
            if ach_key not in existing and ach_key not in added_ach:
                added_ach.append(ach_key)
                report["achievements"].append(ach_key)

            # Try the catalog path. If the achievement is
            # registered, mark it via the system's standard path.
            if get_achievement is not None:
                try:
                    ach = get_achievement(ach_key)
                    if ach is not None and _complete_achievement is not None:
                        await _complete_achievement(
                            db, char["id"], ach,
                            final_progress=ach.get(
                                "trigger", {}).get("count", 1) or 1,
                        )
                except Exception as e:
                    log.debug("[chain_rewards] catalog mark failed "
                              "for ach %s: %s", ach_key, e,
                              exc_info=True)

        if added_ach:
            existing.extend(added_ach)
            notes[_GRADUATION_ACHIEVEMENTS_KEY] = existing

    # ── Follow-up hint ──────────────────────────────────────────────
    hint = getattr(graduation, "follow_up_hint", "") or ""
    report["follow_up_hint"] = hint

    # ── Stamp graduation_summary onto chargen_notes ─────────────────
    # The parser-layer finisher (chain_graduation.execute_pending_teleport)
    # reads this back to deliver the player-visible summary lines.
    notes[_GRADUATION_SUMMARY_KEY] = {
        "chain_id": chain_id,
        "chain_label": chain_label,
        "graduated_at": time.time(),
        "credits_awarded": report["credits_awarded"],
        "rep_awarded": {
            k: v for k, v in report["rep_awarded"].items()
            if not isinstance(v, str) or not v.startswith("error")
        },
        "items_granted": list(report["items_granted"]),
        "achievements": list(report["achievements"]),
        "follow_up_hint": hint,
    }

    try:
        await db.save_character(
            char["id"],
            chargen_notes=json.dumps(notes),
        )
        char["chargen_notes"] = json.dumps(notes)
    except Exception as e:
        log.warning("[chain_rewards] chargen_notes save failed: %s",
                    e, exc_info=True)
        report["errors"].append(f"chargen_notes: {e}")

    # ── Telemetry (T3.19, onboarding-completion funnel) ─────────────
    # ALWAYS emit on graduation — the completion event itself is the
    # high-value, low-frequency signal (chain completion rate per
    # chain_id = an NPE health metric) even when credits == 0. Same
    # ``chain_reward`` event type as the per-step emit, phase tagging the
    # lifecycle transition so the offline funnel is count(step) vs
    # count(graduation) per chain plus the reward distribution.
    try:
        from engine.telemetry import emit as _tele_emit
        _tele_emit("chain_reward", {
            "phase": "graduation",
            "chain_id": chain_id,
            "chain_label": chain_label,
            "char_id": int(char.get("id") or 0),
            "credits": int(report["credits_awarded"]),
            "items": len(report["items_granted"]),
            "achievements": len(report["achievements"]),
            "rep": len([v for v in report["rep_awarded"].values()
                        if not (isinstance(v, str) and v.startswith("error"))]),
            "errors": len(report["errors"]),
        })
    except Exception as _e:
        log.debug("chain_reward graduation telemetry emit failed: %s", _e)

    return report


# ── Parser-layer summary delivery ──────────────────────────────────


async def send_graduation_summary(session, char) -> bool:
    """Send the multi-line graduation summary to the session.
    Reads the ``graduation_summary`` block stamped on
    ``chargen_notes`` by ``apply_graduation_rewards``.

    Called from ``chain_graduation.execute_pending_teleport`` after
    the teleport flavor + look output. No-op if no summary block
    is present.

    Returns True iff a summary was sent.
    """
    notes = _read_chargen_notes(char)
    summary = notes.get(_GRADUATION_SUMMARY_KEY)
    if not summary or not isinstance(summary, dict):
        return False

    lines = []
    lines.append("")
    lines.append("  \033[1;33m═══ Graduation Rewards ═══\033[0m")

    credits = int(summary.get("credits_awarded", 0) or 0)
    if credits > 0:
        lines.append(
            f"  \033[1;32m+{credits:,}\033[0m credits"
        )

    rep_block = summary.get("rep_awarded") or {}
    if isinstance(rep_block, dict) and rep_block:
        for faction, new_score in rep_block.items():
            lines.append(
                f"  \033[1;36m{faction}\033[0m reputation: "
                f"\033[1;32m{new_score}\033[0m"
            )

    items = summary.get("items_granted") or []
    if isinstance(items, list) and items:
        lines.append("  \033[1;37mNew items:\033[0m")
        for item_key in items:
            lines.append(
                f"    \033[0;37m• {_humanize_item_key(item_key)}\033[0m"
            )

    achievements = summary.get("achievements") or []
    if isinstance(achievements, list) and achievements:
        for ach_key in achievements:
            lines.append(
                f"  \033[1;33m★ Achievement: "
                f"{_humanize_item_key(ach_key)}\033[0m"
            )

    hint = summary.get("follow_up_hint") or ""
    if hint:
        lines.append("")
        lines.append(f"  \033[0;37m{hint}\033[0m")

    lines.append("")

    sent = False
    for line in lines:
        try:
            await session.send_line(line)
            sent = True
        except Exception:
            log.debug("[chain_rewards] send_line failed",
                      exc_info=True)

    return sent
