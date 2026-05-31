# -*- coding: utf-8 -*-
"""
engine/death.py — PG.1.death engine consumer module.

Bridges combat's `WoundLevel.DEAD` transition to the corpse + respawn-
Wounded persistence model defined in
`progression_gates_and_consequences_design_v1.md` §3.

Design summary (the locked spec, paraphrased):
  - PC dies in non-secured zone:
      * Body becomes a `corpses` row at the death location.
      * Inventory is snapshotted onto the corpse; char inventory cleared.
      * Credits stay on the character (NOT moved to corpse, per §3.2:
        "Credits and bank untouched").
      * Char respawns at nearest safe location after a blackout.
      * Char gets wound_state='wounded' (the −1D debuff) for the
        recovery window (default 1 hour real-time).
  - PC dies in secured zone:
      * Instant respawn-with-gear. NO corpse created. NO wound_state.
      * (Edge case; combat normally can't happen in secured zones at
        all per engine/security.py::is_combat_allowed.)

Decay windows per §3.4 / §3.5:
  - contested: 2 hours
  - lawless:   4 hours
  - secured:   no corpse (instant respawn)

This module is the engine-consumer half. The companion DB methods on
`Database` (create_corpse, set_wound_state, etc.) landed in the same
drop. The PC-side `respawn` command consumes both ends; the
`loot <corpse>` parser command and the periodic decay tick land in
PG.1.death.b.

Wound-state debuff (−1D) is applied via
`character.Character.total_penalty_dice`, which now includes a
+1 contribution when `self.wound_state == 'wounded'`. Combat's
existing `apply_wound_penalty(pool, total_penalty_dice)` call sites
need no further plumbing.

Thread safety / async: all public functions are `async` because they
touch the DB. Callers from combat (see engine/combat.py death-roll
site) must `await` them.

Errors are logged but not raised: a corpse failing to create must
not prevent the dead character from being removed from combat.
That would deadlock the encounter. The respawn flow is the user-
visible recovery; corpse-creation is supplementary.

—— Drop 2c (May 19 2026 evening — PG.1.death.a foundation).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Recovery clock + decay windows ──────────────────────────────────────
#
# All values in seconds. The design doc gives wall-clock hours; we
# expose them here as named constants so tests can monkeypatch without
# touching string config.

WOUND_RECOVERY_SECONDS: float = 3600.0      # 1 real-time hour (§3.3)

CORPSE_DECAY_SECONDS_CONTESTED: float = 7200.0   # 2 hours (§3.4)
CORPSE_DECAY_SECONDS_LAWLESS:   float = 14400.0  # 4 hours (§3.5)

# Sentinel for secured-zone deaths: no corpse. We don't use a "0
# seconds" decay because that would create-then-immediately-delete,
# burning DB write churn for the same observable outcome.
NO_CORPSE = None


# ── Security-level → decay window resolver ──────────────────────────────

def decay_seconds_for_security(security_level: str) -> Optional[float]:
    """Return the corpse decay window (seconds) for the given security
    level string, or `NO_CORPSE` (None) for secured zones.

    Accepts the str-valued enum values from engine.security.SecurityLevel
    ('secured', 'contested', 'lawless') — passing the actual enum is
    also fine (str() coercion handles either).
    """
    raw = str(security_level).lower().strip()
    # The SecurityLevel enum stringifies as e.g. 'SecurityLevel.SECURED';
    # tolerate that form too.
    if "." in raw:
        raw = raw.split(".")[-1]
    if raw == "secured":
        return NO_CORPSE
    if raw == "lawless":
        return CORPSE_DECAY_SECONDS_LAWLESS
    # Default: contested (also the design-doc fallback).
    return CORPSE_DECAY_SECONDS_CONTESTED


# ── Inventory snapshot helper ───────────────────────────────────────────

async def _snapshot_and_clear_inventory(db, char_id: int) -> list:
    """Read the character's full inventory item list, then clear it
    (replace with an empty items list). Resources also clear — they
    represent currently-held crafting materials, which the design
    treats as part of the gear that drops on death.

    Returns the items list (list[dict]). Resources are dropped to
    the corpse too, but the corpse stores them in the same 'items'
    JSON for simplicity (PG.1.death.b's `loot` command will pull
    both back out).

    No-throw: any DB exception is logged and the snapshot returns
    empty so the death flow continues.
    """
    try:
        raw = await db._get_inventory_raw(char_id)  # noqa: SLF001
    except Exception:
        log.warning("Could not read inventory for char %d on death",
                    char_id, exc_info=True)
        return []

    items = list(raw.get("items") or [])
    resources = list(raw.get("resources") or [])
    # We snapshot both onto the corpse. The corpse's `inventory`
    # column is the items-list shape; resources tag themselves with
    # a "kind": "resource" marker so loot can re-route them on
    # retrieval.
    snapshot = list(items)
    for r in resources:
        if isinstance(r, dict):
            tagged = dict(r)
            tagged.setdefault("kind", "resource")
            snapshot.append(tagged)

    # Wipe live inventory + resources.
    try:
        import json as _j
        await db._db.execute(  # noqa: SLF001
            "UPDATE characters SET inventory = ? WHERE id = ?",
            (_j.dumps({"items": [], "resources": []}), char_id),
        )
        await db._db.commit()  # noqa: SLF001
    except Exception:
        log.warning("Could not clear inventory for char %d on death",
                    char_id, exc_info=True)

    return snapshot


# ── Public: on_pc_death ─────────────────────────────────────────────────

async def on_pc_death(
    db,
    *,
    char_id: int,
    room_id: int,
    security_level: Optional[str] = None,
    killer_id: Optional[int] = None,
    killer_is_bh: bool = False,
) -> Optional[int]:
    """Run the post-death side-effects for a PC.

    Side-effects (in order):
      1. Determine corpse decay window from security_level. Secured →
         no corpse, no wound_state, no inventory drop. This is the
         "edge case from environmental hazard / admin action" path.
      2. Snapshot the character's inventory + resources onto a new
         corpses row, then clear the character's inventory.
      3. Set wound_state='wounded' + wound_clear_at = now + 1 hour.
         The Character class's total_penalty_dice property reads
         these to add −1D to all rolls until the clock expires (or
         until a med-droid clears it; PG.1.death.b).

    Returns the new corpse id (or None if no corpse was created).
    Failure-tolerant: each step is wrapped; a failure logs and moves
    on. The respawn command is the user-visible recovery and runs
    independently from this.

    NPCs are NOT routed through this function — they use the existing
    corpse-loot path in engine/encounter_*.py. Callers MUST gate on
    'is this a PC' before calling.
    """
    decay_window = decay_seconds_for_security(
        security_level or "contested"
    )

    corpse_id: Optional[int] = None

    if decay_window is NO_CORPSE:
        # Secured zone or equivalent: no corpse, no wound_state, no
        # inventory drop. Caller will respawn the PC with full gear.
        log.info(
            "[PG.1.death] PC %d died in secured zone; no corpse + no "
            "wound_state penalty (security_level=%s).",
            char_id, security_level,
        )
        return None

    # ── 1. Snapshot + clear inventory ──
    inv_snapshot = await _snapshot_and_clear_inventory(db, char_id)

    # ── 2. Create corpse ──
    try:
        corpse_id = await db.create_corpse(
            char_id=char_id,
            room_id=room_id,
            inventory=inv_snapshot,
            credits=0,  # Credits stay on the char per §3.2.
            killer_id=killer_id,
            killer_is_bh=killer_is_bh,
            decay_seconds=decay_window,
        )
        log.info(
            "[PG.1.death] PC %d → corpse %d in room %d (decay in %.0fs)",
            char_id, corpse_id, room_id, decay_window,
        )
    except Exception:
        log.error(
            "[PG.1.death] Failed to create corpse for char %d in "
            "room %d; gear may be lost.",
            char_id, room_id, exc_info=True,
        )

    # ── 3. Set wound_state ──
    try:
        clear_at = time.time() + WOUND_RECOVERY_SECONDS
        await db.set_wound_state(
            char_id, state="wounded", clear_at=clear_at,
        )
    except Exception:
        log.error(
            "[PG.1.death] Failed to apply wound_state to char %d; "
            "the −1D debuff will be skipped this death.",
            char_id, exc_info=True,
        )

    # ── 4. PG.2 session 2 (May 21 2026): insurance hook ──
    # If the target had an active PC bounty AND the killer is a
    # BH Guild member, fire the insurance hit per
    # progression_gates_and_consequences_design_v1.md §4.4-§4.5.
    # The hit is 10% of the bounty amount, debited from credits;
    # any shortfall accrues as insurance debt.
    #
    # This ALSO fulfills the bounty (state → 'fulfilled') so the
    # BH gets paid out from escrow on their side. Per design §4.3:
    # Fulfilled → 80% of escrow to BH, 20% to Guild treasury.
    #
    # Failure-tolerant: any error here is logged and swallowed;
    # the death still completes, the corpse still drops.
    try:
        await _fire_insurance_and_fulfill(
            db,
            target_id=char_id,
            killer_id=killer_id,
            killer_is_bh=killer_is_bh,
        )
    except Exception:
        log.warning(
            "[PG.2] insurance/fulfill hook failed for target %d "
            "killer %s (is_bh=%s)",
            char_id, killer_id, killer_is_bh, exc_info=True,
        )

    return corpse_id


# ── PG.2 session 2 (May 21 2026): insurance + fulfillment helper ────────

# Insurance hit = INSURANCE_PCT% of bounty amount.
# Per design §4.4 — kept here (not in pc_bounty_commands) because
# this fires from the engine death path, not the parser layer.
INSURANCE_PCT = 10

# Payout split per design §4.3.
# BH gets BH_PAYOUT_PCT% of escrow; rest to Guild treasury sink.
BH_PAYOUT_PCT = 80


async def _fire_insurance_and_fulfill(
    db, *, target_id: int, killer_id: Optional[int],
    killer_is_bh: bool,
) -> None:
    """If target has an active PC bounty and killer is a BH,
    fire the insurance hit on the target and fulfill the bounty
    (paying the BH).

    Per progression_gates_and_consequences_design_v1.md:
      §4.4 — insurance hit = 10% of bounty amount; debited from
             target credits; shortfall accrues as debt.
      §4.5 — insurance ONLY applies when killer is a BH Guild
             member. If killer is None or non-BH, the bounty
             stays active.
      §4.3 — Fulfilled state: 80% of escrow to BH, 20% sunk to
             Guild treasury.

    No-op if any precondition fails. Failure-tolerant.
    """
    # Gate: only on confirmed BH kills.
    if not killer_is_bh or killer_id is None:
        return

    bounty = await db.get_active_incoming_for_target(target_id)
    if bounty is None or bounty.get("state") not in (
        "active", "claimed"
    ):
        return

    bounty_id = int(bounty["id"])
    amount = int(bounty["amount"])

    # ── Insurance hit on target ──
    hit_amount = (amount * INSURANCE_PCT + 99) // 100
    try:
        target = await db.get_character(target_id)
        if target:
            current_cr = int(target.get("credits") or 0)
            if current_cr >= hit_amount:
                new_balance = current_cr - hit_amount
                await db.save_character(
                    target_id, credits=new_balance,
                )
                try:
                    await db.log_credit(
                        target_id, -hit_amount,
                        "bh_insurance_hit", new_balance,
                    )
                except Exception:
                    log.debug(
                        "[PG.2] log_credit failed for "
                        "insurance hit on %s",
                        target_id, exc_info=True,
                    )
                log.info(
                    "[PG.2] insurance hit: target %d paid "
                    "%d cr (bounty %d, %d%% of %d)",
                    target_id, hit_amount, bounty_id,
                    INSURANCE_PCT, amount,
                )
            else:
                # Partial pay, rest to debt.
                paid_cash = current_cr
                debt_added = hit_amount - paid_cash
                if paid_cash > 0:
                    await db.save_character(
                        target_id, credits=0,
                    )
                    try:
                        await db.log_credit(
                            target_id, -paid_cash,
                            "bh_insurance_hit_partial", 0,
                        )
                    except Exception:
                        log.debug(
                            "[PG.2] log_credit failed for "
                            "partial insurance hit",
                            exc_info=True,
                        )
                new_debt = await db.add_insurance_debt(
                    target_id, debt_added,
                )
                log.info(
                    "[PG.2] insurance hit partial: target %d "
                    "paid %d cr cash + %d cr debt (new total: %d)",
                    target_id, paid_cash, debt_added, new_debt,
                )
    except Exception:
        log.warning(
            "[PG.2] insurance hit application failed for "
            "target %d", target_id, exc_info=True,
        )

    # ── Fulfill bounty (pay the BH) ──
    snapshot = await db.fulfill_pc_bounty(
        bounty_id=bounty_id, bh_char_id=killer_id,
    )
    if snapshot is None:
        # Race: bounty was resolved between our read and the
        # fulfill. Nothing to pay; bail.
        return

    payout = (amount * BH_PAYOUT_PCT) // 100
    # Remainder is sunk to Guild treasury (system sink — no
    # credit movement, just absent from the BH payout).

    try:
        bh = await db.get_character(killer_id)
        if bh:
            new_bh_balance = int(
                bh.get("credits") or 0
            ) + payout
            await db.save_character(
                killer_id, credits=new_bh_balance,
            )
            try:
                await db.log_credit(
                    killer_id, payout,
                    "bh_bounty_payout", new_bh_balance,
                )
            except Exception:
                log.debug(
                    "[PG.2] log_credit failed for BH payout",
                    exc_info=True,
                )
            # Guild treasury sink — log as system sink to
            # make the economy audit see the destroyed credits.
            sunk = amount - payout
            if sunk > 0:
                try:
                    await db.log_credit(
                        0, -sunk, "bh_guild_treasury_sink", 0,
                    )
                except Exception:
                    log.debug(
                        "[PG.2] log_credit failed for "
                        "Guild sink", exc_info=True,
                    )
            log.info(
                "[PG.2] bounty %d fulfilled: BH %d paid %d cr; "
                "Guild treasury sink %d cr",
                bounty_id, killer_id, payout, sunk,
            )

            # PG2.PL.B (May 22 2026): mail the BH on auto-fulfill.
            # Per HANDOFF_MAY21 §"What's NOT in PG.2 session 2".
            # The BH's credits already jumped, but a clearer audit
            # trail helps especially when multiple kills resolve
            # over time. Mail is best-effort — failure here doesn't
            # affect the payout.
            try:
                from engine.mail_utils import send_system_mail
                # Look up the target's name for the mail body.
                target_name = "the target"
                try:
                    tgt = await db.get_character(target_id)
                    if tgt:
                        target_name = tgt.get("name") or target_name
                except Exception:
                    log.debug(
                        "[PG.2] BH mail: target-name lookup failed "
                        "(best-effort; falling back to 'the target')",
                        exc_info=True,
                    )
                await send_system_mail(
                    db,
                    recipient_id=killer_id,
                    subject=f"Bounty fulfilled: {target_name}",
                    body=(
                        f"The Bounty Hunters' Guild confirms "
                        f"the fulfillment of bounty #{bounty_id} "
                        f"against {target_name}.\n\n"
                        f"Posted amount: {amount:,} cr\n"
                        f"Your payout: {payout:,} cr "
                        f"({BH_PAYOUT_PCT}% of posted)\n"
                        f"Guild treasury share: {sunk:,} cr\n\n"
                        f"The credits have been deposited to your "
                        f"account."
                    ),
                )
            except Exception:
                log.debug(
                    "[PG2.PL.B] BH fulfill mail failed "
                    "(best-effort)", exc_info=True,
                )
    except Exception:
        log.warning(
            "[PG.2] BH payout failed for bounty %d to BH %d",
            bounty_id, killer_id, exc_info=True,
        )


# ── Public: wound_state recovery tick ───────────────────────────────────

async def tick_wound_recovery(db, char_id: int) -> bool:
    """If the character's wound_clear_at has passed, transition them
    back to wound_state='healthy'.

    Returns True if a transition was made (caller can surface a "you
    feel your wounds knit" message), False otherwise. Intended to be
    called opportunistically — e.g. on heartbeat or on look — rather
    than from a global timer loop, to keep the change locally
    observable.
    """
    try:
        state, clear_at = await db.get_wound_state(char_id)
    except Exception:
        log.debug("tick_wound_recovery: get_wound_state failed",
                  exc_info=True)
        return False

    if state != "wounded":
        return False
    if clear_at <= 0:
        return False
    if time.time() < clear_at:
        return False

    try:
        await db.set_wound_state(
            char_id, state="healthy", clear_at=0.0,
        )
    except Exception:
        log.warning("tick_wound_recovery: set_wound_state failed for "
                    "char %d", char_id, exc_info=True)
        return False
    return True


# ── Public: respawn destination ─────────────────────────────────────────
#
# Per §3.2: "PC respawns at nearest safe location after 30-second
# blackout." The "nearest" half is design-doc-aspirational; in this
# drop we keep the existing RespawnCommand's choice of room 1
# (Mos Eisley Landing Pad) as the canonical respawn. A future drop
# can compute "nearest secured zone" properly. The chokepoint exists
# so PG.1.death.b can swap implementations without command-layer
# changes.

DEFAULT_RESPAWN_ROOM_ID: int = 1   # Mos Eisley Landing Pad


async def respawn_destination(db, char_id: int) -> int:
    """Pick the respawn room for the given character. Today: a
    constant. Tomorrow: nearest secured/contested room with a
    med-droid object. The signature is async so the future
    implementation can issue queries without breaking callers."""
    return DEFAULT_RESPAWN_ROOM_ID


# ─── PG.1.death.b (Drop 2d, May 19 2026 evening) ────────────────────────
#
# Loot + recovery + decay processing. These finish the loop:
#   - `loot_corpse_take_item(db, corpse_id, owner_id, item_key)` —
#     pull one item from a corpse into a character's inventory.
#     Used by the LootCommand parser. Anyone can loot (per §3.4).
#   - `loot_all_from_corpse(db, corpse_id, owner_id)` — bulk variant
#     for the owner returning to their own corpse.
#   - `consume_bacta_pack(db, char_id)` / `apply_bacta_tank(db, char_id)` —
#     both clear wound_state immediately. The pack is the 150cr
#     consumable; the tank is the 500cr med-droid service. Same
#     effect, different delivery.
#   - `decay_corpse(db, corpse_row, deliver_bound_to_owner=True)` —
#     process one corpse past its decay_at. Bound items return to
#     owner inventory (per §3.4 "auto-mailed" — see handoff for the
#     deferred-mail design decision); rest are destroyed; row is
#     deleted.
#   - `run_decay_tick(db)` — periodic sweep: process all decayed
#     corpses. Wired by server/tick_handlers_death.py into the
#     existing TickScheduler.


# Bacta-pack item template. Used by the BactaPackCommand to verify
# what's in the player's inventory; matches what the buy command
# will insert.
BACTA_PACK_KEY: str = "bacta_pack"
BACTA_PACK_PRICE: int = 150          # design §3.3
BACTA_TANK_PRICE: int = 500          # design §3.3


# Items with this flag survive corpse decay and return to the owner.
# Pre-Drop-2d nothing in the game sets it; a future drop adds it to
# signature lightsabers and faction-issued gear per design §3.4.
# Today it's an extension point — present, documented, untouched in
# any item YAML — so we can add it without re-wiring decay later.
_BOUND_FLAG_KEY: str = "bound"


def _item_is_bound(item: dict) -> bool:
    """Return True if the item should survive corpse decay and
    return to its owner. Tolerates either bool or truthy values."""
    if not isinstance(item, dict):
        return False
    return bool(item.get(_BOUND_FLAG_KEY, False))


# ─── Loot helpers ──────────────────────────────────────────────────────

async def loot_corpse_take_item(
    db,
    *,
    corpse_id: int,
    looter_id: int,
    item_key: str,
) -> Optional[dict]:
    """Remove the first item matching `item_key` from the corpse
    and add it to the looter's inventory. Returns the looted item
    dict, or None if no match.

    Used by the `loot <corpse> <item>` parser command. Anyone can
    loot — there's no owner check by design (§3.4 says
    "anyone can `loot <corpse>` while it persists"). The decision
    of "should I let them" lives in security/zone gating, not here.
    """
    row = await db.get_corpse(corpse_id)
    if row is None:
        return None
    import json as _j
    try:
        items = _j.loads(row.get("inventory") or "[]")
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []

    taken = None
    remaining = []
    for it in items:
        if taken is None and isinstance(it, dict) and it.get("key") == item_key:
            taken = it
        else:
            remaining.append(it)

    if taken is None:
        return None

    # Resources are routed back to the resources blob on the looter,
    # not their items list — they were tagged on the corpse by
    # _snapshot_and_clear_inventory.
    if taken.get("kind") == "resource":
        try:
            inv = await db._get_inventory_raw(looter_id)  # noqa: SLF001
            inv.setdefault("resources", [])
            r = dict(taken)
            r.pop("kind", None)
            inv["resources"].append(r)
            await db._db.execute(   # noqa: SLF001
                "UPDATE characters SET inventory = ? WHERE id = ?",
                (_j.dumps(inv), looter_id),
            )
            await db._db.commit()  # noqa: SLF001
        except Exception:
            log.warning("loot: resource re-route failed for "
                        "looter=%d corpse=%d", looter_id, corpse_id,
                        exc_info=True)
            return None
    else:
        try:
            await db.add_to_inventory(looter_id, taken)
        except Exception:
            log.warning("loot: add_to_inventory failed for "
                        "looter=%d corpse=%d", looter_id, corpse_id,
                        exc_info=True)
            return None

    # Update corpse — keep the row even if empty so the player can
    # still see "you find nothing" until decay. PG.1.death.c may
    # remove empty corpses on the next tick.
    try:
        await db.update_corpse_inventory(corpse_id, remaining)
    except Exception:
        log.warning("loot: corpse update failed corpse=%d",
                    corpse_id, exc_info=True)

    return taken


async def loot_all_from_corpse(db, *, corpse_id: int,
                                looter_id: int) -> list:
    """Take every item from a corpse. Returns the list of items
    moved (or an empty list if the corpse was empty / missing).

    Convenience wrapper for `loot <corpse>` with no item argument
    (the owner returning to their own body).
    """
    row = await db.get_corpse(corpse_id)
    if row is None:
        return []
    import json as _j
    try:
        items = _j.loads(row.get("inventory") or "[]")
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []

    moved: list = []
    for it in list(items):
        if not isinstance(it, dict):
            continue
        try:
            if it.get("kind") == "resource":
                inv = await db._get_inventory_raw(looter_id)  # noqa: SLF001
                inv.setdefault("resources", [])
                r = dict(it)
                r.pop("kind", None)
                inv["resources"].append(r)
                await db._db.execute(  # noqa: SLF001
                    "UPDATE characters SET inventory = ? WHERE id = ?",
                    (_j.dumps(inv), looter_id),
                )
                await db._db.commit()  # noqa: SLF001
            else:
                await db.add_to_inventory(looter_id, it)
            moved.append(it)
        except Exception:
            log.warning("loot_all: per-item failed corpse=%d looter=%d",
                        corpse_id, looter_id, exc_info=True)

    # Empty the corpse but keep credits for the room-drop path on decay.
    try:
        await db.update_corpse_inventory(corpse_id, [])
    except Exception:
        log.warning("loot_all: corpse empty failed corpse=%d",
                    corpse_id, exc_info=True)
    return moved


# ─── Bacta (recovery from wound_state) ─────────────────────────────────

async def apply_bacta_tank(db, char_id: int) -> bool:
    """500cr med-droid service: clear wound_state immediately.
    Credit deduction is the caller's job (the parser command handles
    it so the user sees the cost line up with the cost message).

    Returns True if the character was actually wounded and got
    cleared; False if they were already healthy.
    """
    state, _ = await db.get_wound_state(char_id)
    if state != "wounded":
        return False
    try:
        await db.set_wound_state(char_id, state="healthy", clear_at=0.0)
        return True
    except Exception:
        log.warning("apply_bacta_tank: set_wound_state failed for "
                    "char %d", char_id, exc_info=True)
        return False


async def consume_bacta_pack(db, char_id: int) -> bool:
    """150cr inventory consumable: clear wound_state immediately.
    Same effect as the tank; different delivery (in-place vs at a
    med-droid). The caller is expected to have already removed one
    bacta_pack from the character's inventory.

    Returns True if the pack actually did something (i.e. the char
    was wounded); False otherwise. Callers can use the return to
    decide whether to refund the pack ("you're already healthy").
    """
    return await apply_bacta_tank(db, char_id)


# ─── Decay processing ──────────────────────────────────────────────────

async def decay_corpse(
    db,
    corpse_row: dict,
    *,
    deliver_bound_to_owner: bool = True,
) -> dict:
    """Process one decayed corpse:
      - Bound items (item.get('bound') truthy) are added to the
        owner's inventory if deliver_bound_to_owner is True.
        (See handoff for the deferred-mail design call: the design
        says "auto-mailed", but no mail system exists yet, so we
        deliver-to-inventory as the closest available semantic.
        A future mail drop can swap the implementation without
        touching the call site.)
      - All other items are destroyed.
      - Credits on the corpse: per §3.4 "dropped to the room
        (lootable until cleared)." No room-credit-drop scaffold
        exists yet either; for now corpse credits are also
        delivered to the owner's wallet. Documented in the handoff.
      - The corpse row is deleted.

    Returns a small summary dict for logging/testing:
        {"corpse_id": int, "owner_id": int, "bound_delivered": int,
         "destroyed": int, "credits_returned": int}
    """
    import json as _j
    corpse_id = corpse_row.get("id")
    owner_id = corpse_row.get("char_id")
    try:
        items = _j.loads(corpse_row.get("inventory") or "[]")
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []

    bound_delivered = 0
    destroyed = 0
    for it in items:
        if _item_is_bound(it) and deliver_bound_to_owner and owner_id:
            try:
                if it.get("kind") == "resource":
                    inv = await db._get_inventory_raw(owner_id)  # noqa: SLF001
                    inv.setdefault("resources", [])
                    r = dict(it)
                    r.pop("kind", None)
                    inv["resources"].append(r)
                    await db._db.execute(  # noqa: SLF001
                        "UPDATE characters SET inventory = ? "
                        "WHERE id = ?",
                        (_j.dumps(inv), owner_id),
                    )
                    await db._db.commit()  # noqa: SLF001
                else:
                    await db.add_to_inventory(owner_id, it)
                bound_delivered += 1
            except Exception:
                log.warning(
                    "decay: bound-deliver failed for owner=%d "
                    "corpse=%d", owner_id, corpse_id, exc_info=True,
                )
                destroyed += 1
        else:
            destroyed += 1

    credits_returned = int(corpse_row.get("credits") or 0)
    if credits_returned > 0 and owner_id:
        # Standin for the design's "drop to room (lootable until
        # cleared)" — no room-drop scaffold yet. Document in handoff.
        try:
            char_row = await db._db.execute_fetchall(  # noqa: SLF001
                "SELECT credits FROM characters WHERE id = ?",
                (owner_id,),
            )
            if char_row:
                new_credits = int(char_row[0]["credits"] or 0) + credits_returned
                await db.save_character(owner_id, credits=new_credits)
        except Exception:
            log.warning(
                "decay: credits-return failed for owner=%d corpse=%d",
                owner_id, corpse_id, exc_info=True,
            )

    try:
        await db.delete_corpse(corpse_id)
    except Exception:
        log.warning(
            "decay: delete_corpse failed for id=%d",
            corpse_id, exc_info=True,
        )

    return {
        "corpse_id": corpse_id,
        "owner_id": owner_id,
        "bound_delivered": bound_delivered,
        "destroyed": destroyed,
        "credits_returned": credits_returned,
    }


async def run_decay_tick(db) -> list:
    """Process every corpse whose decay_at has passed.
    Returns a list of summary dicts (see decay_corpse).

    Called by server/tick_handlers_death.py at the configured
    cadence. Per-corpse failures are logged but don't stop the
    sweep — one bad row mustn't block the rest.
    """
    try:
        rows = await db.get_decayed_corpses()
    except Exception:
        log.warning("run_decay_tick: get_decayed_corpses failed",
                    exc_info=True)
        return []
    summaries: list = []
    for r in rows:
        try:
            summary = await decay_corpse(db, r)
            summaries.append(summary)
        except Exception:
            log.warning(
                "run_decay_tick: decay_corpse failed for row %r",
                r, exc_info=True,
            )
    if summaries:
        log.info("[PG.1.death.b] Decayed %d corpse(s) this tick.",
                 len(summaries))
    return summaries
