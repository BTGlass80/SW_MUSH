"""PC Bounty commands — session 1 (PG.2.bounty player surface).

Per progression_gates_and_consequences_design_v1.md §4 (PC
bounty system) and the May 20 2026 PG.2 session 1 design calls:

  +bounty post <player> <amount> <reason>
                                — Post a PC bounty (or stack onto
                                  an existing active bounty on the
                                  target).
  +bounty cancel                — Cancel your active outgoing
                                  bounty (25% fee, proportional
                                  refund to secondaries).
  +bounty board                 — View active bounties (BH Guild
                                  only).
  +bounty list                  — Alias for `+bounty board`.
  +bounty status                — View your outgoing/incoming
                                  bounties.
  +bounty mine                  — Alias for `+bounty status`.

NOT in session 1 (session 2 lane):
  +bounty claim / +bounty release — BH Guild workflow
  +bounty pay / +bounty debt      — Insurance debt management
  @bounty void / @bounty review   — Admin commands
  insurance hit on PvP death      — engine integration
  expiry tick handler             — server tick

Design calls locked (PG.2 session 1, May 20 2026):

  #1 Scope:           posting + cancel + board + status this session
  #2 Stacking:        second posting MERGES into existing bounty;
                      primary stays the original poster; contributors
                      tracked in v30 contributors_json sidecar
  #3 Notifications:   BOTH narrative-memory log (pc_action_log)
                      AND in-game mail to the target on post
  #4 Cancel refunds:  Proportional 75% refund to ALL contributors
                      on primary cancel (each refunded their fair
                      stake share; the 25% cancel fee splits
                      proportionally too)

Economy constants (per design §4.2-§4.3):

  MIN_BOUNTY               =  1,000 cr
  MAX_BOUNTY               = 50,000 cr  (anti-escalation cap)
  POSTING_FEE_PCT          =     10%    (non-refundable)
  CANCEL_FEE_PCT           =     25%    (of total escrow)
  BOUNTY_DURATION_DAYS     =     30     (until auto-expire)
  COOLDOWN_DAYS            =     30     (after expire/cancel, same
                                          poster cannot re-post on
                                          same target)

The cancel-refund math: when a primary cancels, each contributor
gets their pro-rata 75% of their original stake back. The 10%
posting fees were non-refundable and stay sunk. Concretely:

  contributor stake: 5000 cr (paid 5500 cr inc. fee)
  on cancel:         3750 cr back (75% of 5000); 1750 cr net loss
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime, timezone

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ── Economy constants (per design §4.2-§4.3) ─────────────────────────────
MIN_BOUNTY = 1000
MAX_BOUNTY = 50000
POSTING_FEE_PCT = 10
CANCEL_FEE_PCT = 25
BOUNTY_DURATION_DAYS = 30
COOLDOWN_DAYS = 30

# Derived constants
_SECONDS_PER_DAY = 86400
BOUNTY_DURATION_SECONDS = BOUNTY_DURATION_DAYS * _SECONDS_PER_DAY
COOLDOWN_SECONDS = COOLDOWN_DAYS * _SECONDS_PER_DAY

# PG.2 session 2: BH claim timer (per design §4.3).
# When a BH claims a bounty, they have 7 days to fulfill before
# the contract reverts to active.
CLAIM_TIMER_DAYS = 7
CLAIM_TIMER_SECONDS = CLAIM_TIMER_DAYS * _SECONDS_PER_DAY

# BH Guild faction ids (both GCW and CW canonical codes accepted,
# per the precedent in parser/combat_commands.py:1373).
_BH_GUILD_FACTION_IDS = frozenset(("bh_guild", "bounty_hunters_guild"))


# ── PG2.PL.C (May 22 2026): stale-claim warning state ────────────────────
#
# Per-process set tracking which bounty IDs we've already sent a
# "claim expiring soon" mail for. Resets on server restart, which
# is acceptable: a duplicate warning per restart is a much smaller
# bug than spamming the BH on every hourly tick.
_PG2PL_WARNED_CLAIMS: set[int] = set()


def _reset_pg2pl_warned_claims_for_test() -> None:
    """Clear the warned-claims set. Test-only — production never calls this."""
    _PG2PL_WARNED_CLAIMS.clear()



def _posting_fee(amount: int) -> int:
    """Return the absolute posting fee (in credits) for a given
    bounty amount. Integer arithmetic, rounded up for safety."""
    return (amount * POSTING_FEE_PCT + 99) // 100


def _cancel_refund_total(amount: int) -> int:
    """Return the total refund pool (in credits) on primary cancel.

    75% of the total current escrow is refunded; the 25% cancel
    fee is sunk. Integer arithmetic — fee rounds up (favors the
    system over the poster, matches the posting-fee rounding).
    """
    fee = (amount * CANCEL_FEE_PCT + 99) // 100
    return amount - fee


def _proportional_refunds(
    contributors: list, refund_pool: int,
) -> list:
    """Split `refund_pool` across contributors proportional to
    each contributor's stake. Returns a list of {poster_id, refund}
    dicts. Integer arithmetic; rounding error (1-N cr) lands on
    the primary contributor for determinism.
    """
    if not contributors or refund_pool <= 0:
        return []
    total_stake = sum(int(c.get("amount") or 0) for c in contributors)
    if total_stake <= 0:
        return []
    out = []
    distributed = 0
    for i, c in enumerate(contributors):
        stake = int(c.get("amount") or 0)
        if i == 0:
            # Primary contributor absorbs rounding residue at the
            # end — placeholder, fixed in the loop below.
            refund = 0
        else:
            refund = (refund_pool * stake) // total_stake
            distributed += refund
        out.append({
            "poster_id": int(c.get("poster_id") or 0),
            "refund": refund,
        })
    # Primary gets the remainder.
    if out:
        out[0]["refund"] = refund_pool - distributed
    return out


# ─── helpers ──────────────────────────────────────────────────────────────


async def _find_pc_by_name(ctx, name: str) -> dict | None:
    """Look up an active character by name (case-insensitive,
    global). Returns None if not found."""
    if not name:
        return None
    return await ctx.db.get_character_by_name(name.strip())


async def _is_bh_guild(char: dict) -> bool:
    """True iff the character belongs to the BH Guild faction
    (either GCW or CW canonical code)."""
    return (char.get("faction_id") or "") in _BH_GUILD_FACTION_IDS


async def _debit_credits(
    ctx: CommandContext, char_id: int, amount: int, source: str,
) -> bool:
    """Debit `amount` credits from `char_id`. Returns False if the
    character lacks credits (or does not exist); True on successful debit.

    Routes through ``db.adjust_credits`` (the credit chokepoint) so the
    debit is atomic and recorded in credit_log for the economy audit. The
    ``allow_negative=False`` guard performs the affordability check and
    refuses (returns None) when funds are short or the character is gone.
    """
    if amount <= 0:
        return True  # No-op
    new_balance = await ctx.db.adjust_credits(
        char_id, -amount, source, allow_negative=False
    )
    return new_balance is not None


async def _credit_credits(
    ctx: CommandContext, char_id: int, amount: int, source: str,
) -> None:
    """Add `amount` credits to `char_id`. Routes through
    ``db.adjust_credits`` so the award is recorded in credit_log."""
    if amount <= 0:
        return
    # Preserve the original no-op-if-missing behaviour.
    if not await ctx.db.get_character(char_id):
        return
    await ctx.db.adjust_credits(char_id, amount, source)


async def _log_event(
    ctx: CommandContext, char_id: int, action_type: str,
    summary: str, details: str = "{}",
) -> None:
    """Cross-write to pc_action_log. Failure-tolerant."""
    try:
        await ctx.db.log_action(char_id, action_type, summary, details)
    except Exception:
        log.warning(
            "_log_event: log_action failed for char %s action %s",
            char_id, action_type, exc_info=True,
        )


async def _send_system_mail(
    ctx: CommandContext, *, sender_id: int, recipient_id: int,
    subject: str, body: str,
) -> bool:
    """Send an in-game mail. Per the PG.2 §3 design call (option
    'both'): a target who's been bountied gets a mail in addition
    to the pc_action_log narrative-memory entry. The sender_id
    here is the posting PC (not a synthetic system character —
    the mail surface schema requires NOT NULL FK to characters).

    Failure-tolerant: mail delivery failure must not block the
    bounty state mutation.
    """
    try:
        # naive-UTC ISO (byte-identical to the stored format); no deprecated utcnow().
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        cur = await ctx.db._db.execute(
            "INSERT INTO mail (sender_id, subject, body, sent_at) "
            "VALUES (?, ?, ?, ?)",
            (sender_id, subject, body, now),
        )
        mail_id = cur.lastrowid
        await ctx.db._db.execute(
            "INSERT INTO mail_recipients "
            "(mail_id, char_id, is_read, is_deleted) "
            "VALUES (?, ?, 0, 0)",
            (mail_id, recipient_id),
        )
        await ctx.db._db.commit()
        return True
    except Exception:
        log.warning(
            "_send_system_mail: delivery to char %s failed",
            recipient_id, exc_info=True,
        )
        return False


def _format_credits(n: int) -> str:
    """Render credits with thousands separators."""
    return f"{n:,} cr"


def _format_remaining(expires_at: float, now: float | None = None) -> str:
    """Render a 'time remaining' string for a bounty expiry."""
    if now is None:
        now = _time.time()
    remaining = expires_at - now
    if remaining <= 0:
        return "expired"
    days = int(remaining // _SECONDS_PER_DAY)
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''} left"
    hours = int(remaining // 3600)
    if hours >= 1:
        return f"{hours} hour{'s' if hours != 1 else ''} left"
    minutes = int(remaining // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''} left"


# ─── +bounty (top-level dispatcher) ───────────────────────────────────────


class BountyCommand(BaseCommand):
    """``+bounty`` — PC bounty system entry point.

    Subcommands:
      post <player> <amount> <reason>   Post (or stack) a bounty
      cancel                            Cancel your active bounty
      board                             View active bounties (BH only)
      list                              Alias for `board`
      status                            View your outgoing/incoming
      mine                              Alias for `status`
    """
    # Bare `+pcbounty` defaults to `status`. Uses `+pcbounty` rather
    # than `+bounty` to avoid the namespace collision with the
    # existing NPC bounty board surface in parser/bounty_commands.py
    # (which is `+bounty` for the GG6 NPC contract system). The two
    # systems are intentionally separate per design §4.1 + the
    # `pc_bounties` schema comment.
    key = "+pcbounty"
    aliases = ["+pb"]
    help_text = (
        "PC bounty system. Post a bounty against another player, "
        "view the BH Guild\nboard, or check your active bounty "
        "status.\n"
        "\n"
        "(For the NPC bounty board / Guild contracts, use +bounty "
        "instead — that's a\nseparate system.)\n"
        "\n"
        "USAGE:\n"
        "  +pcbounty post <player> <amount> <reason>\n"
        "      Post a bounty against <player>. Minimum 1,000 cr; "
        "max 50,000 cr.\n"
        "      Costs amount + 10% posting fee. If <player> already "
        "has an active\n"
        "      bounty, your contribution stacks onto it.\n"
        "\n"
        "  +pcbounty cancel\n"
        "      Cancel your active outgoing bounty. 25% cancel fee; "
        "remaining 75%\n"
        "      refunded proportionally to all contributors.\n"
        "\n"
        "  +pcbounty board        (BH Guild only) View active "
        "PC bounties.\n"
        "  +pcbounty list         Alias for board.\n"
        "\n"
        "  +pcbounty status       View your outgoing/incoming bounties.\n"
        "  +pcbounty mine         Alias for status.\n"
        "\n"
        "  +pb …                  Short alias for +pcbounty.\n"
        "\n"
        "BH Guild members:\n"
        "  +pcbounty claim <id>     Claim an active bounty. 7 days "
        "to fulfill.\n"
        "  +pcbounty release <id>   Release a claimed bounty back "
        "to the board.\n"
        "\n"
        "Insurance debt (if you've been bountied + killed by a BH):\n"
        "  +pcbounty debt           View your current insurance "
        "debt.\n"
        "  +pcbounty pay [amount]   Pay down your debt. Default: "
        "pay full balance.\n"
    )
    usage = (
        "+pcbounty <post|cancel|board|status|claim|release|pay|debt>"
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +bounty.")
            return

        args = (ctx.args or "").strip()
        if not args:
            args = "status"
        parts = args.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "post":
            await self._handle_post(ctx, char, rest)
            return
        if sub == "cancel":
            await self._handle_cancel(ctx, char, rest)
            return
        if sub in ("board", "list"):
            await self._handle_board(ctx, char)
            return
        if sub in ("status", "mine"):
            await self._handle_status(ctx, char)
            return
        # PG.2 session 2 subcommands.
        if sub == "claim":
            await self._handle_claim(ctx, char, rest)
            return
        if sub == "release":
            await self._handle_release(ctx, char, rest)
            return
        if sub == "pay":
            await self._handle_pay(ctx, char, rest)
            return
        if sub == "debt":
            await self._handle_debt(ctx, char)
            return

        await ctx.session.send_line(
            f"  Unknown +pcbounty subcommand: {sub!r}\n"
            f"  Usage: {self.usage}"
        )

    # ─── +bounty post ─────────────────────────────────────────────────────

    async def _handle_post(
        self, ctx: CommandContext, poster: dict, args: str,
    ) -> None:
        # PG.2.PL.1 (May 22 2026): block bounty post while insurance debt
        # outstanding. Per design §4.4. Same gate helper as guild join.
        from engine.insurance_debt import check_debt_gate, BOUNTY_POST
        allowed, refusal = await check_debt_gate(
            ctx.db, poster["id"], BOUNTY_POST,
        )
        if not allowed:
            await ctx.session.send_line(f"  {refusal}")
            return

        # Parse: <player> <amount> <reason>
        parts = args.split(None, 2)
        if len(parts) < 3:
            await ctx.session.send_line(
                "  Usage: +pcbounty post <player> <amount> <reason>"
            )
            await ctx.session.send_line(
                f"  Amount: {MIN_BOUNTY:,}-{MAX_BOUNTY:,} cr. "
                f"Reason is mandatory and visible on the board."
            )
            return

        target_name, amount_raw, reason = parts
        reason = reason.strip()
        if not reason:
            await ctx.session.send_line(
                "  Reason is mandatory. Bounties without a reason "
                "can be voided by staff.")
            return

        # Amount parse + range check.
        try:
            amount = int(amount_raw.replace(",", ""))
        except ValueError:
            await ctx.session.send_line(
                f"  '{amount_raw}' isn't a valid amount.")
            return
        if amount < MIN_BOUNTY:
            await ctx.session.send_line(
                f"  Minimum bounty is {_format_credits(MIN_BOUNTY)}."
            )
            return
        if amount > MAX_BOUNTY:
            await ctx.session.send_line(
                f"  Maximum bounty is {_format_credits(MAX_BOUNTY)} "
                f"(anti-escalation cap)."
            )
            return

        # Target resolution.
        target = await _find_pc_by_name(ctx, target_name)
        if target is None:
            await ctx.session.send_line(
                f"  No active character named '{target_name}'.")
            return
        if target["id"] == poster["id"]:
            await ctx.session.send_line(
                "  You cannot post a bounty on yourself.")
            return

        # Cooldown check.
        cd_until = await ctx.db.get_bounty_cooldown(
            poster["id"], target["id"]
        )
        now = _time.time()
        if cd_until > now:
            days_left = max(1, int((cd_until - now) // _SECONDS_PER_DAY))
            await ctx.session.send_line(
                f"  You are on cooldown for posting against "
                f"{target['name']} for {days_left} more day"
                f"{'s' if days_left != 1 else ''}. (Anti-harassment.)"
            )
            return

        fee = _posting_fee(amount)
        total_debit = amount + fee

        # Existing-bounties checks.
        existing_incoming = await ctx.db.get_active_incoming_for_target(
            target["id"]
        )

        # Path A: stack onto existing bounty (target already has one).
        if existing_incoming is not None:
            # Cannot stack onto your own active bounty (it'd just be
            # a +amount via cancel-and-repost; cleaner to refuse).
            if existing_incoming["poster_id"] == poster["id"]:
                await ctx.session.send_line(
                    f"  You are already the primary poster on a "
                    f"bounty against {target['name']}. To increase "
                    f"the amount, cancel and repost (you'll forfeit "
                    f"the cancel fee)."
                )
                return
            # Check if poster is already a secondary contributor — if
            # so, allow re-stacking (each contribution is independent).
            await self._do_stack(
                ctx, poster, target, existing_incoming,
                amount=amount, fee=fee, total_debit=total_debit,
                reason=reason,
            )
            return

        # Path B: new bounty. Poster's own outgoing limit applies.
        existing_outgoing = await ctx.db.get_active_outgoing_for_poster(
            poster["id"]
        )
        if existing_outgoing is not None:
            await ctx.session.send_line(
                "  You already have an active outgoing bounty. "
                "Only one active outgoing bounty per primary poster."
            )
            await ctx.session.send_line(
                "  Use '+pcbounty cancel' to cancel it first, or "
                "wait for it to be claimed/expire."
            )
            return

        await self._do_new_post(
            ctx, poster, target,
            amount=amount, fee=fee, total_debit=total_debit,
            reason=reason,
        )

    async def _do_new_post(
        self, ctx: CommandContext, poster: dict, target: dict, *,
        amount: int, fee: int, total_debit: int, reason: str,
    ) -> None:
        # Debit poster.
        if not await _debit_credits(
            ctx, poster["id"], total_debit, "bounty_post",
        ):
            await ctx.session.send_line(
                f"  You don't have enough credits. Need "
                f"{_format_credits(total_debit)} "
                f"({_format_credits(amount)} escrow + "
                f"{_format_credits(fee)} fee)."
            )
            return

        # Create the bounty.
        try:
            bounty_id = await ctx.db.post_pc_bounty(
                poster_id=poster["id"],
                target_id=target["id"],
                amount=amount,
                reason=reason,
                fee=fee,
                duration_seconds=BOUNTY_DURATION_SECONDS,
            )
        except Exception:
            log.warning(
                "post_pc_bounty raised", exc_info=True,
            )
            # Refund.
            await _credit_credits(
                ctx, poster["id"], total_debit, "bounty_post_refund",
            )
            await ctx.session.send_line(
                "  The bounty could not be posted. "
                "Your credits have been refunded. Please notify staff."
            )
            return

        # ── Player Cities Phase 4 (May 22 2026): city tax ───────────
        # Per design v1.2 §5.1: "Bounty board postings within city —
        # Tax % of posting fee." The poster's debit doesn't change;
        # the city's slice is carved out of the `fee` sink that
        # would otherwise be system-absorbed.
        city_tax_msg = ""
        try:
            from engine.player_cities import apply_city_tax
            city_take, _, city_name = await apply_city_tax(
                ctx.db, poster["room_id"], fee,
            )
            if city_take > 0:
                city_tax_msg = (
                    f" ({_format_credits(city_take)} city tax to "
                    f"{city_name})"
                )
        except Exception:
            log.warning(
                "[pc_bounty] city tax hook failed", exc_info=True,
            )

        # Poster-side echo.
        await ctx.session.send_line(
            f"  {ansi.green('Bounty posted:')} "
            f"{_format_credits(amount)} on "
            f"{ansi.bold(target['name'])} "
            f"({_format_credits(fee)} fee). Expires in "
            f"{BOUNTY_DURATION_DAYS} days.{city_tax_msg}"
        )

        # Target notification (per design call: pc_action_log + mail).
        await _log_event(
            ctx, poster["id"], "bounty_posted",
            f"Posted bounty: {_format_credits(amount)} on "
            f"{target['name']} (reason: {reason})",
        )
        await _log_event(
            ctx, target["id"], "bounty_received",
            f"Bountied by {poster['name']} for "
            f"{_format_credits(amount)} (reason: {reason})",
        )
        await self._notify_target_via_mail(
            ctx, poster, target, amount=amount, reason=reason,
            is_stack=False,
        )

    async def _do_stack(
        self, ctx: CommandContext, poster: dict, target: dict,
        existing: dict, *, amount: int, fee: int, total_debit: int,
        reason: str,
    ) -> None:
        # Debit poster.
        if not await _debit_credits(
            ctx, poster["id"], total_debit, "bounty_stack",
        ):
            await ctx.session.send_line(
                f"  You don't have enough credits. Need "
                f"{_format_credits(total_debit)} "
                f"({_format_credits(amount)} contribution + "
                f"{_format_credits(fee)} fee)."
            )
            return

        ok = await ctx.db.stack_pc_bounty(
            bounty_id=existing["id"],
            poster_id=poster["id"],
            amount=amount, fee=fee,
        )
        if not ok:
            await _credit_credits(
                ctx, poster["id"], total_debit,
                "bounty_stack_refund",
            )
            await ctx.session.send_line(
                "  The contribution could not be added. The bounty "
                "may have been resolved. Your credits have been "
                "refunded."
            )
            return

        # ── Player Cities Phase 4 (May 22 2026): city tax on stack ──
        # Same model as _do_new_post: the city's slice is carved from
        # the `fee` sink. Stacks contribute their own posting fee, so
        # each stack independently gets taxed.
        city_tax_msg = ""
        try:
            from engine.player_cities import apply_city_tax
            city_take, _, city_name = await apply_city_tax(
                ctx.db, poster["room_id"], fee,
            )
            if city_take > 0:
                city_tax_msg = (
                    f" ({_format_credits(city_take)} city tax to "
                    f"{city_name})"
                )
        except Exception:
            log.warning(
                "[pc_bounty] city tax hook failed", exc_info=True,
            )

        new_total = existing["amount"] + amount
        await ctx.session.send_line(
            f"  {ansi.green('Bounty stacked:')} you added "
            f"{_format_credits(amount)} "
            f"({_format_credits(fee)} fee) to the bounty on "
            f"{ansi.bold(target['name'])}. New total: "
            f"{ansi.bold(_format_credits(new_total))}.{city_tax_msg}"
        )

        # Log all sides + mail.
        await _log_event(
            ctx, poster["id"], "bounty_stacked",
            f"Stacked {_format_credits(amount)} on bounty against "
            f"{target['name']} (reason: {reason})",
        )
        await _log_event(
            ctx, target["id"], "bounty_received",
            f"Additional {_format_credits(amount)} stacked on "
            f"your bounty by {poster['name']} (reason: {reason}). "
            f"New total: {_format_credits(new_total)}.",
        )
        # Notify the PRIMARY poster (informational; they didn't act).
        primary = await ctx.db.get_character(existing["poster_id"])
        if primary and primary["id"] != poster["id"]:
            await _log_event(
                ctx, primary["id"], "bounty_stacked_on_yours",
                f"{poster['name']} added "
                f"{_format_credits(amount)} to your bounty on "
                f"{target['name']}. New total: "
                f"{_format_credits(new_total)}.",
            )
        await self._notify_target_via_mail(
            ctx, poster, target, amount=amount, reason=reason,
            is_stack=True, new_total=new_total,
        )

    async def _notify_target_via_mail(
        self, ctx, poster: dict, target: dict, *,
        amount: int, reason: str, is_stack: bool,
        new_total: int = 0,
    ) -> None:
        verb = ("stacked an additional" if is_stack
                else "posted")
        subject = (
            f"[BOUNTY] {poster['name']} has {verb} a bounty "
            f"on you"
        )
        if is_stack:
            body_total = f"New total: {_format_credits(new_total)}\n"
        else:
            body_total = ""
        body = (
            f"NOTICE OF PC BOUNTY\n"
            f"\n"
            f"{poster['name']} has {verb} a bounty against you.\n"
            f"\n"
            f"Amount this posting: {_format_credits(amount)}\n"
            f"{body_total}"
            f"Reason: {reason}\n"
            f"\n"
            f"You will be hunted by BH Guild members until the "
            f"bounty is resolved.\n"
            f"This notice was sent automatically by the bounty "
            f"system. Do not reply.\n"
        )
        await _send_system_mail(
            ctx, sender_id=poster["id"],
            recipient_id=target["id"],
            subject=subject, body=body,
        )

    # ─── +bounty cancel ───────────────────────────────────────────────────

    async def _handle_cancel(
        self, ctx: CommandContext, poster: dict, _args: str,
    ) -> None:
        bounty = await ctx.db.get_active_outgoing_for_poster(
            poster["id"]
        )
        if bounty is None:
            await ctx.session.send_line(
                "  You have no active outgoing bounty to cancel."
            )
            return

        # Snapshot for refund math + cancel.
        snapshot = await ctx.db.cancel_pc_bounty(bounty["id"])
        if snapshot is None:
            await ctx.session.send_line(
                "  Cancel failed — the bounty may have already "
                "been resolved. Please notify staff."
            )
            return

        # Refund math. The cancel fee is 25% of the TOTAL escrow.
        total_amount = int(snapshot["amount"])
        refund_pool = _cancel_refund_total(total_amount)
        try:
            contributors = json.loads(
                snapshot.get("contributors_json") or "[]"
            )
            if not isinstance(contributors, list):
                contributors = []
        except (ValueError, TypeError):
            contributors = []

        refunds = _proportional_refunds(contributors, refund_pool)

        # Issue refunds.
        for entry in refunds:
            pid = entry["poster_id"]
            refund = entry["refund"]
            if pid and refund > 0:
                await _credit_credits(
                    ctx, pid, refund, "bounty_cancel_refund",
                )

        target = await ctx.db.get_character(snapshot["target_id"])
        target_name = target["name"] if target else "?"
        cancel_fee = total_amount - refund_pool

        # Poster-side echo. Primary contributor is the cancel actor.
        primary_refund = refunds[0]["refund"] if refunds else 0
        await ctx.session.send_line(
            f"  {ansi.yellow('Bounty canceled.')} "
            f"Total escrow: {_format_credits(total_amount)}; "
            f"cancel fee: {_format_credits(cancel_fee)}; "
            f"your refund: {_format_credits(primary_refund)}."
        )
        if len(refunds) > 1:
            n_secondaries = len(refunds) - 1
            await ctx.session.send_line(
                f"  {n_secondaries} secondary contributor"
                f"{'s' if n_secondaries != 1 else ''} "
                f"refunded proportionally."
            )

        # Log + notify all sides.
        await _log_event(
            ctx, poster["id"], "bounty_canceled",
            f"Canceled bounty on {target_name} "
            f"(total escrow {_format_credits(total_amount)}, "
            f"cancel fee {_format_credits(cancel_fee)}).",
        )
        if target:
            await _log_event(
                ctx, target["id"], "bounty_canceled",
                f"Bounty by {poster['name']} canceled "
                f"(total had been {_format_credits(total_amount)}).",
            )
        # Notify secondary contributors (they need to know they
        # got partial refunds).
        for entry in refunds[1:]:
            pid = entry["poster_id"]
            refund = entry["refund"]
            if pid:
                await _log_event(
                    ctx, pid, "bounty_canceled",
                    f"Bounty on {target_name} canceled by primary "
                    f"poster. Your refund: "
                    f"{_format_credits(refund)}.",
                )

        # Set cooldown for the poster (anti-harassment).
        await ctx.db.set_bounty_cooldown(
            poster["id"], snapshot["target_id"],
            _time.time() + COOLDOWN_SECONDS,
        )

    # ─── +bounty board ────────────────────────────────────────────────────

    async def _handle_board(
        self, ctx: CommandContext, char: dict,
    ) -> None:
        if not await _is_bh_guild(char):
            await ctx.session.send_line(
                "  The bounty board is BH Guild members only."
            )
            return

        bounties = await ctx.db.list_active_pc_bounties(limit=50)

        # Drop 4b: dark-side notoriety section — derived from DSP, no rows.
        notoriety_lines = []
        try:
            from engine.bounty_board import (
                DSP_BOUNTY_THRESHOLD, format_dsp_notoriety_section,
            )
            wanted = await ctx.db.get_dsp_wanted_characters(DSP_BOUNTY_THRESHOLD)
            # hunter.1: annotate each wanted line with its live pursuit state.
            pursuits = {}
            try:
                pursuits = {p["char_id"]: p
                            for p in await ctx.db.get_all_dsp_pursuits()}
            except Exception:
                log.debug("[pcbounty] dsp pursuits fetch failed", exc_info=True)
            notoriety_lines = format_dsp_notoriety_section(wanted, pursuits)
        except Exception:
            log.debug("[pcbounty] dsp notoriety section failed", exc_info=True)

        if not bounties and not notoriety_lines:
            await ctx.session.send_line(
                "  No active bounties on the board."
            )
            return

        if bounties:
            await ctx.session.send_line(
                f"  {ansi.cyan('Active PC Bounties')} "
                f"({len(bounties)}):"
            )
            for b in bounties:
                target = await ctx.db.get_character(b["target_id"])
                t_name = target["name"] if target else "?"
                remaining = _format_remaining(float(b["expires_at"]))
                await ctx.session.send_line(
                    f"  [{b['id']:>4}] "
                    f"{ansi.bold(_format_credits(int(b['amount']))):>20s} "
                    f"on {ansi.bold(t_name):<20s} ({remaining})"
                )
                # Show reason on the next line, indented + dimmed.
                await ctx.session.send_line(
                    f"         {ansi.DIM}reason: {b['reason']}"
                    f"{ansi.RESET}"
                )

        # Dark-side notoriety (auto-posted, prestige-only) below the credit
        # bounties.
        if notoriety_lines:
            if bounties:
                await ctx.session.send_line("")
            for line in notoriety_lines:
                await ctx.session.send_line(line)

    # ─── +bounty status ───────────────────────────────────────────────────

    async def _handle_status(
        self, ctx: CommandContext, char: dict,
    ) -> None:
        outgoing = await ctx.db.get_active_outgoing_for_poster(
            char["id"]
        )
        incoming = await ctx.db.get_active_incoming_for_target(
            char["id"]
        )

        if outgoing is None and incoming is None:
            await ctx.session.send_line(
                "  You have no active outgoing or incoming "
                "bounties."
            )
            return

        if outgoing is not None:
            target = await ctx.db.get_character(outgoing["target_id"])
            t_name = target["name"] if target else "?"
            remaining = _format_remaining(
                float(outgoing["expires_at"])
            )
            await ctx.session.send_line(
                f"  {ansi.cyan('Outgoing bounty:')} "
                f"{_format_credits(int(outgoing['amount']))} on "
                f"{ansi.bold(t_name)} ({remaining})"
            )
            await ctx.session.send_line(
                f"    reason: {outgoing['reason']}"
            )

        if incoming is not None:
            poster = await ctx.db.get_character(incoming["poster_id"])
            p_name = poster["name"] if poster else "?"
            remaining = _format_remaining(
                float(incoming["expires_at"])
            )
            await ctx.session.send_line(
                f"  {ansi.red('Incoming bounty:')} "
                f"{_format_credits(int(incoming['amount']))} "
                f"from {ansi.bold(p_name)} ({remaining})"
            )
            await ctx.session.send_line(
                f"    reason: {incoming['reason']}"
            )

    # ─── +pcbounty claim ──────────────────────────────────────────────────

    async def _handle_claim(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        if not await _is_bh_guild(char):
            await ctx.session.send_line(
                "  Only BH Guild members can claim bounties."
            )
            return
        bounty_id = self._parse_id(args)
        if bounty_id is None:
            await ctx.session.send_line(
                "  Usage: +pcbounty claim <id>")
            return
        bounty = await ctx.db.get_pc_bounty(bounty_id)
        if bounty is None:
            await ctx.session.send_line(
                f"  No bounty with id {bounty_id}.")
            return
        if bounty["state"] != "active":
            await ctx.session.send_line(
                f"  Bounty {bounty_id} is not available to claim "
                f"(state: {bounty['state']})."
            )
            return
        # Can't claim a bounty against yourself.
        if bounty["target_id"] == char["id"]:
            await ctx.session.send_line(
                "  You cannot claim a bounty against yourself."
            )
            return

        ok = await ctx.db.claim_pc_bounty(
            bounty_id=bounty_id, bh_char_id=char["id"],
            timer_seconds=CLAIM_TIMER_SECONDS,
        )
        if not ok:
            await ctx.session.send_line(
                "  Claim failed — the bounty may have been "
                "resolved. Please refresh +pcbounty board."
            )
            return

        target = await ctx.db.get_character(bounty["target_id"])
        t_name = target["name"] if target else "?"
        await ctx.session.send_line(
            f"  {ansi.green('Bounty claimed:')} "
            f"{_format_credits(int(bounty['amount']))} on "
            f"{ansi.bold(t_name)}. "
            f"You have {CLAIM_TIMER_DAYS} days to fulfill."
        )
        await _log_event(
            ctx, char["id"], "bounty_claimed",
            f"Claimed bounty #{bounty_id} "
            f"({_format_credits(int(bounty['amount']))} on "
            f"{t_name})",
        )
        # Notify target (warns them they're being actively hunted).
        await _log_event(
            ctx, bounty["target_id"], "bounty_claimed_by_bh",
            f"BH {char['name']} has claimed the bounty against "
            f"you ({_format_credits(int(bounty['amount']))}).",
        )

    # ─── +pcbounty release ────────────────────────────────────────────────

    async def _handle_release(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        if not await _is_bh_guild(char):
            await ctx.session.send_line(
                "  Only BH Guild members can release bounties."
            )
            return
        bounty_id = self._parse_id(args)
        if bounty_id is None:
            await ctx.session.send_line(
                "  Usage: +pcbounty release <id>")
            return
        bounty = await ctx.db.get_pc_bounty(bounty_id)
        if bounty is None:
            await ctx.session.send_line(
                f"  No bounty with id {bounty_id}.")
            return
        if bounty["state"] != "claimed":
            await ctx.session.send_line(
                f"  Bounty {bounty_id} is not currently claimed."
            )
            return
        if bounty.get("claimed_by") != char["id"]:
            await ctx.session.send_line(
                "  You are not the BH on this bounty. Only the "
                "claiming BH can release it."
            )
            return
        ok = await ctx.db.release_pc_bounty(bounty_id)
        if not ok:
            await ctx.session.send_line(
                "  Release failed — the bounty may have already "
                "been resolved. Please notify staff."
            )
            return
        await ctx.session.send_line(
            f"  {ansi.yellow('Bounty released')} back to the board."
        )
        await _log_event(
            ctx, char["id"], "bounty_released",
            f"Released bounty #{bounty_id}",
        )

    # ─── +pcbounty debt ───────────────────────────────────────────────────

    async def _handle_debt(
        self, ctx: CommandContext, char: dict,
    ) -> None:
        debt = await ctx.db.get_insurance_debt(char["id"])
        if debt <= 0:
            await ctx.session.send_line(
                "  You have no insurance debt."
            )
            return
        await ctx.session.send_line(
            f"  {ansi.red('Insurance debt:')} "
            f"{ansi.bold(_format_credits(debt))}"
        )
        await ctx.session.send_line(
            f"  {ansi.dim('Use +pcbounty pay [amount] to pay it '\
'down. While non-zero, Guild')}"
        )
        await ctx.session.send_line(
            f"  {ansi.dim('services and some BH-tier vendors are '\
'restricted.')}"
        )

    # ─── +pcbounty pay ────────────────────────────────────────────────────

    async def _handle_pay(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        debt = await ctx.db.get_insurance_debt(char["id"])
        if debt <= 0:
            await ctx.session.send_line(
                "  You have no insurance debt to pay."
            )
            return

        # Parse amount; default = pay full debt.
        args = args.strip()
        if not args:
            requested = debt
        else:
            try:
                requested = int(args.replace(",", ""))
            except ValueError:
                await ctx.session.send_line(
                    f"  '{args}' isn't a valid amount.")
                return
            if requested <= 0:
                await ctx.session.send_line(
                    "  Amount must be positive.")
                return

        # Can't pay more than you owe.
        to_pay = min(requested, debt)

        # Debit from credits.
        reloaded = await ctx.db.get_character(char["id"])
        current = int(reloaded.get("credits") or 0)
        if current < to_pay:
            await ctx.session.send_line(
                f"  You only have {_format_credits(current)}. "
                f"You owe {_format_credits(debt)}."
            )
            return

        new_balance = await ctx.db.adjust_credits(
            char["id"], -to_pay, "bh_insurance_pay"
        )
        remaining = await ctx.db.pay_insurance_debt(
            char["id"], to_pay
        )
        if remaining <= 0:
            await ctx.session.send_line(
                f"  {ansi.green('Debt paid in full.')} "
                f"({_format_credits(to_pay)} paid.)"
            )
        else:
            await ctx.session.send_line(
                f"  {ansi.yellow('Paid')} "
                f"{_format_credits(to_pay)} toward debt. "
                f"Remaining: {_format_credits(remaining)}."
            )
        await _log_event(
            ctx, char["id"], "insurance_debt_paid",
            f"Paid {_format_credits(to_pay)} toward insurance "
            f"debt (remaining: {_format_credits(remaining)}).",
        )

    # ─── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_id(args: str) -> int | None:
        """Parse a numeric bounty id from args. Returns None on
        any parse failure."""
        try:
            return int((args or "").strip())
        except (ValueError, TypeError):
            return None


# ─── Admin commands: @pcbounty void/review/fulfill ────────────────────────


class AdminBountyCommand(BaseCommand):
    """``@pcbounty`` — staff commands for PC bounty moderation.

    Subcommands:
      @pcbounty void <id> [reason]   Void a bounty (full refund,
                                      no fee taken; for griefing
                                      reports per design §4.2).
      @pcbounty review <id>          Show detailed bounty info
                                      (contributors, claim history,
                                      raw reason text).
      @pcbounty fulfill <id> <bh>    Manually fulfill a bounty
                                      (out-of-game kill resolution;
                                      mid-combat claim disputes).

    Per progression_gates_and_consequences_design_v1.md §4.2 +
    §4.8 admin column.
    """
    key = "@pcbounty"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin: PC bounty moderation.\n"
        "\n"
        "USAGE:\n"
        "  @pcbounty void <id> [reason]    Void a bounty (full "
        "refund, no fee).\n"
        "  @pcbounty review <id>           Detailed bounty info.\n"
        "  @pcbounty fulfill <id> <bh>     Manually fulfill a "
        "bounty (assign to BH).\n"
    )
    usage = "@pcbounty <void|review|fulfill> <id> [...]"

    async def execute(self, ctx: CommandContext):
        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return
        parts = args.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if sub == "void":
            await self._handle_void(ctx, rest)
            return
        if sub == "review":
            await self._handle_review(ctx, rest)
            return
        if sub == "fulfill":
            await self._handle_fulfill(ctx, rest)
            return
        await ctx.session.send_line(
            f"  Unknown @pcbounty subcommand: {sub!r}\n"
            f"  Usage: {self.usage}"
        )

    async def _handle_void(
        self, ctx: CommandContext, args: str,
    ) -> None:
        parts = args.split(None, 1)
        try:
            bounty_id = int(parts[0])
        except (IndexError, ValueError):
            await ctx.session.send_line(
                "  Usage: @pcbounty void <id> [reason]")
            return
        reason = parts[1].strip() if len(parts) > 1 else ""

        snap = await ctx.db.void_pc_bounty(
            bounty_id=bounty_id, reason=reason,
        )
        if snap is None:
            await ctx.session.send_line(
                f"  Bounty {bounty_id} cannot be voided "
                f"(not found or already resolved)."
            )
            return

        # Full refund (no fee taken) to all contributors.
        try:
            contributors = json.loads(
                snap.get("contributors_json") or "[]"
            )
            if not isinstance(contributors, list):
                contributors = []
        except (ValueError, TypeError):
            contributors = []

        total_refund = 0
        for c in contributors:
            pid = int(c.get("poster_id") or 0)
            stake = int(c.get("amount") or 0)
            fee = int(c.get("fee") or 0)
            full_refund = stake + fee  # void = no fee
            if pid > 0 and full_refund > 0:
                await _credit_credits(
                    ctx, pid, full_refund, "bounty_void_refund",
                )
                total_refund += full_refund
                await _log_event(
                    ctx, pid, "bounty_voided",
                    f"Bounty #{bounty_id} voided by staff "
                    f"(reason: {reason or 'none'}). "
                    f"Refunded: {_format_credits(full_refund)}.",
                )

        target = await ctx.db.get_character(snap["target_id"])
        t_name = target["name"] if target else "?"
        if target:
            await _log_event(
                ctx, snap["target_id"], "bounty_voided",
                f"The bounty against you was voided by staff "
                f"(reason: {reason or 'none'}).",
            )

        await ctx.session.send_line(
            f"  {ansi.green('Voided:')} bounty #{bounty_id} on "
            f"{t_name}. Total refunded: "
            f"{_format_credits(total_refund)} across "
            f"{len(contributors)} contributor"
            f"{'s' if len(contributors) != 1 else ''}."
        )

    async def _handle_review(
        self, ctx: CommandContext, args: str,
    ) -> None:
        try:
            bounty_id = int(args.strip())
        except ValueError:
            await ctx.session.send_line(
                "  Usage: @pcbounty review <id>")
            return
        bounty = await ctx.db.get_pc_bounty(bounty_id)
        if bounty is None:
            await ctx.session.send_line(
                f"  No bounty with id {bounty_id}.")
            return

        target = await ctx.db.get_character(bounty["target_id"])
        primary = await ctx.db.get_character(bounty["poster_id"])
        await ctx.session.send_line(
            f"  {ansi.cyan('Bounty')} #{bounty_id}  "
            f"state={ansi.bold(bounty['state'])}"
        )
        await ctx.session.send_line(
            f"    target:  {target['name'] if target else '?'} "
            f"(id={bounty['target_id']})"
        )
        await ctx.session.send_line(
            f"    primary: {primary['name'] if primary else '?'} "
            f"(id={bounty['poster_id']})"
        )
        await ctx.session.send_line(
            f"    amount:  {_format_credits(int(bounty['amount']))}"
        )
        await ctx.session.send_line(
            f"    reason:  {bounty['reason']}"
        )
        if bounty.get("claimed_by"):
            claimer = await ctx.db.get_character(bounty["claimed_by"])
            c_name = claimer["name"] if claimer else "?"
            await ctx.session.send_line(
                f"    claimer: {c_name} "
                f"(at {bounty.get('claimed_at')})"
            )
        try:
            contributors = json.loads(
                bounty.get("contributors_json") or "[]"
            )
            if isinstance(contributors, list) and contributors:
                await ctx.session.send_line(
                    f"    contributors ({len(contributors)}):"
                )
                for c in contributors:
                    pid = c.get("poster_id")
                    pchar = await ctx.db.get_character(pid) if pid else None
                    p_name = pchar["name"] if pchar else f"id={pid}"
                    await ctx.session.send_line(
                        f"      {p_name}: "
                        f"{_format_credits(int(c.get('amount') or 0))} "
                        f"(+{_format_credits(int(c.get('fee') or 0))} fee)"
                    )
        except (ValueError, TypeError):
            await ctx.session.send_line(
                "    contributors: <malformed sidecar>"
            )

    async def _handle_fulfill(
        self, ctx: CommandContext, args: str,
    ) -> None:
        parts = args.split(None, 1)
        if len(parts) < 2:
            await ctx.session.send_line(
                "  Usage: @pcbounty fulfill <id> <bh_name>")
            return
        try:
            bounty_id = int(parts[0])
        except ValueError:
            await ctx.session.send_line(
                f"  '{parts[0]}' isn't a valid bounty id.")
            return
        bh_name = parts[1].strip()
        bh = await _find_pc_by_name(ctx, bh_name)
        if bh is None:
            await ctx.session.send_line(
                f"  No active character named '{bh_name}'.")
            return
        if not await _is_bh_guild(bh):
            await ctx.session.send_line(
                f"  {bh['name']} is not a BH Guild member.")
            return

        snap = await ctx.db.fulfill_pc_bounty(
            bounty_id=bounty_id, bh_char_id=bh["id"],
        )
        if snap is None:
            await ctx.session.send_line(
                f"  Bounty {bounty_id} cannot be fulfilled "
                f"(not found or already resolved)."
            )
            return

        # Payout to BH. 80% to BH, 20% sunk to Guild treasury.
        amount = int(snap["amount"])
        payout = (amount * 80) // 100
        await _credit_credits(
            ctx, bh["id"], payout, "bh_bounty_payout",
        )
        target = await ctx.db.get_character(snap["target_id"])
        t_name = target["name"] if target else "?"
        await ctx.session.send_line(
            f"  {ansi.green('Fulfilled:')} bounty #{bounty_id} "
            f"on {t_name}. {bh['name']} paid "
            f"{_format_credits(payout)} (80%); "
            f"{_format_credits(amount - payout)} sunk to Guild "
            f"treasury."
        )
        await _log_event(
            ctx, bh["id"], "bounty_fulfilled",
            f"Staff-fulfilled bounty #{bounty_id} "
            f"({_format_credits(payout)} paid).",
        )
        if target:
            await _log_event(
                ctx, snap["target_id"], "bounty_fulfilled",
                f"Bounty against you fulfilled by {bh['name']} "
                f"(via staff resolution).",
            )


# ─── Tick handler ─────────────────────────────────────────────────────────


async def run_pc_bounty_expiry_tick(db) -> dict:
    """Server tick: auto-expire active bounties past their 30-day
    window, and revert claimed bounties whose 7-day BH claim
    timer has elapsed.

    Returns a summary dict: {
      'expired': int,  # bounties moved to 'expired' state
      'reverted': int, # claims reverted to 'active'
      'refunded_total': int,  # total cr refunded across expiries
    }. Failure-tolerant per row.

    Should be called from the server's existing periodic tick loop.
    Cheap to call frequently — does nothing if no rows match.
    """
    summary = {"expired": 0, "reverted": 0, "refunded_total": 0}

    # ── 1. Auto-expire active bounties past their window ──
    try:
        expired_rows = await db.list_expired_active_bounties()
    except Exception:
        log.warning("[PG.2 tick] list_expired_active_bounties "
                    "failed", exc_info=True)
        expired_rows = []

    for row in expired_rows:
        try:
            snap = await db.expire_pc_bounty(int(row["id"]))
            if snap is None:
                continue
            summary["expired"] += 1
            # Per design §4.3: escrow returns to contributors
            # minus the 10% posting fee (which was non-refundable
            # at post time). Concretely: refund each contributor
            # their gross stake (the fee was sunk up front).
            try:
                contributors = json.loads(
                    snap.get("contributors_json") or "[]"
                )
                if not isinstance(contributors, list):
                    contributors = []
            except (ValueError, TypeError):
                contributors = []
            for c in contributors:
                pid = int(c.get("poster_id") or 0)
                stake = int(c.get("amount") or 0)
                if pid > 0 and stake > 0:
                    try:
                        target_char = await db.get_character(pid)
                        if target_char:
                            await db.adjust_credits(
                                pid, stake, "bounty_expire_refund",
                            )
                            summary["refunded_total"] += stake
                    except Exception:
                        log.warning(
                            "[PG.2 tick] expire-refund failed "
                            "for poster %d on bounty %d",
                            pid, row["id"], exc_info=True,
                        )
        except Exception:
            log.warning(
                "[PG.2 tick] expire path failed for bounty %d",
                row.get("id"), exc_info=True,
            )

    # ── 2. Revert stale claims (7-day claim timer elapsed) ──
    try:
        stale_claims = await db.list_expired_claims(
            CLAIM_TIMER_SECONDS,
        )
    except Exception:
        log.warning("[PG.2 tick] list_expired_claims failed",
                    exc_info=True)
        stale_claims = []

    for row in stale_claims:
        try:
            ok = await db.revert_expired_claim(int(row["id"]))
            if ok:
                summary["reverted"] += 1
        except Exception:
            log.warning(
                "[PG.2 tick] revert path failed for bounty %d",
                row.get("id"), exc_info=True,
            )

    # ── 3. Warn BHs about claims nearing expiry (PG2.PL.C, May 22) ──
    # Per HANDOFF_MAY21 §"What's NOT in PG.2 session 2": when a claim
    # is 6 days old (1 day to go), send a courtesy mail to the BH.
    # We use a per-process set to avoid spamming on every tick — the
    # set resets on server restart, which is acceptable (one duplicate
    # warning per restart is not a problem).
    try:
        warning_lower = (CLAIM_TIMER_DAYS - 1) * _SECONDS_PER_DAY
        warning_upper = CLAIM_TIMER_DAYS * _SECONDS_PER_DAY
        nearing = await db.list_claims_in_warning_window(
            warning_lower_seconds=warning_lower,
            warning_upper_seconds=warning_upper,
        )
    except Exception:
        log.warning(
            "[PG.2 tick] list_claims_in_warning_window failed",
            exc_info=True,
        )
        nearing = []

    for row in nearing:
        bounty_id = int(row["id"])
        if bounty_id in _PG2PL_WARNED_CLAIMS:
            continue
        bh_id = int(row.get("claimed_by") or 0)
        if bh_id <= 0:
            _PG2PL_WARNED_CLAIMS.add(bounty_id)
            continue
        try:
            from engine.mail_utils import send_system_mail
            target_id = int(row.get("target_id") or 0)
            target_name = "the target"
            if target_id > 0:
                tgt = await db.get_character(target_id)
                if tgt:
                    target_name = tgt.get("name") or target_name
            amount = int(row.get("amount") or 0)
            await send_system_mail(
                db,
                recipient_id=bh_id,
                subject=(
                    f"Bounty claim expiring soon: {target_name}"
                ),
                body=(
                    f"Your claim on bounty #{bounty_id} against "
                    f"{target_name} ({amount:,} cr) is approaching "
                    f"the {CLAIM_TIMER_DAYS}-day claim window.\n\n"
                    f"You have less than 1 day remaining to "
                    f"fulfill or release this claim. After expiry, "
                    f"the claim is automatically released and the "
                    f"bounty returns to the open board for other "
                    f"BH Guild members to claim.\n\n"
                    f"Use +pcbounty release {bounty_id} to release "
                    f"voluntarily, or fulfill the contract before "
                    f"the timer elapses."
                ),
            )
            _PG2PL_WARNED_CLAIMS.add(bounty_id)
            summary["warned"] = summary.get("warned", 0) + 1
        except Exception:
            log.warning(
                "[PG2.PL.C] stale-claim warning failed for bounty %d",
                bounty_id, exc_info=True,
            )

    return summary


# ─── registration ─────────────────────────────────────────────────────────


def register_pc_bounty_commands(registry) -> None:
    """Register PG.2 session 1 + 2 commands with the given
    CommandRegistry. Called from server/game_server.py."""
    registry.register(BountyCommand())
    registry.register(AdminBountyCommand())
