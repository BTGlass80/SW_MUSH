"""Padawan-Master command layer (P-M.2).

Per padawan_master_system_design_v1.md (full design) and v45 §8.12
(MVP design calls). P-M.1 (Drop 8, May 19 2026) shipped the schema
+ DB API foundation. This module wires the launch command surface:

  +master              — Padawan: see bonded Master's status
  +padawan             — Master: see bonded Padawan(s) status
  +bond <padawan>      — Master: propose a bond to a Padawan-tier PC
                                   in the same room (player-flow path)
  +bond accept <m>     — Padawan: accept a pending bond proposal
  +bond decline <m>    — Padawan: decline a pending bond proposal
  +release [reason]    — Master: voluntarily dissolve an active bond
                                   with the chosen Padawan
  +leave-master <r>    — Padawan: voluntarily leave bond (reason req.)
  @bond <m> = <p>      — Admin/staff: directly establish a bond
                                   (skips player-flow, no consent
                                   prompt — for mediated assignments)

Design-call wiring (locked in this session):

  §8.12 #1 (+bond authorization):
      BOTH admin and player flow. Admin is `@bond`; player flow is
      `+bond <padawan>` → `+bond accept <master>` analogous to
      ChallengeCommand/AcceptCommand in combat_commands.py.

  §8.12 #2 (+release consequences):
      VOLUNTARY + Padawan-side narrative event. On release, we
      cross-write a `pc_action_log` entry on the Padawan's side
      (action_type='bond_dissolved') so the narrative-memory
      summarizer can surface it. This is the shared-memory hook
      seam; the full §5.4 shared-memory cross-write infrastructure
      is a separate future drop.

  §8.12 #3 (Master-cap enforcement):
      DB-driven via the v29 `characters.master_cap` column. Default
      1; staff/Council can raise per-character via direct SQL or a
      future @master-cap admin command.

  §8.12 #4 (look-output marker):
      Padawan = bright green [Padawan], Master = bright cyan
      [Master] (Jedi palette). Marker is appended to the player's
      name in the room listing, mirroring the [PvP] pattern from
      builtin_commands.LookCommand._look_room_contents.

Tier eligibility:

The MVP layer does NOT compute "is this PC tier-eligible to be a
Master" — that's a Trials/promotion concern (P-M.3). For launch,
ANY PC can theoretically be a Master per `+bond` (gated only by
master_cap). Staff use `@bond` for the tester-cohort assignment
(Padawans paired to tester-Knights/Masters) per
launch_strategy_v1.md §5.

The Padawan-side check IS enforced: a Padawan with an existing
active bond cannot accept a new one — `create_bond` raises
ValueError, which we catch and surface as a clean error message.
"""

from __future__ import annotations

import logging
import time as _time

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ── Marker literals (byte-grep-pinned via tests) ──────────────────────────
# Per v45 §6.2 seventh phantom-pattern: byte-grep + smoke pin both,
# so a refactor that moves the literal into a dead branch is caught
# at runtime by the smoke. The literals are public module constants
# so tests can import them rather than duplicating the strings.
PADAWAN_MARKER = "\033[1;92m[Padawan]\033[0m"  # bright green
MASTER_MARKER = "\033[1;96m[Master]\033[0m"    # bright cyan


# ── Transient bond-proposal store ─────────────────────────────────────────
# Maps (master_char_id, padawan_char_id) -> unix_ts of proposal.
# Lives in-process; survives until accept/decline/expiry. 10-minute
# TTL matches the ChallengeCommand pattern (combat_commands.py L2479).
# A process restart clears all pending proposals — acceptable for an
# opt-in handshake (Master can re-propose).
_pending_bond_proposals: dict[tuple[int, int], float] = {}
_BOND_PROPOSAL_TTL = 10 * 60  # 10 minutes


def _prune_expired_proposals(now: float | None = None) -> None:
    """Drop expired proposals from the in-process store.

    Called at the top of every +bond subcommand so the dict doesn't
    grow without bound across long uptimes.
    """
    if now is None:
        now = _time.time()
    cutoff = now - _BOND_PROPOSAL_TTL
    stale = [k for k, ts in _pending_bond_proposals.items() if ts < cutoff]
    for k in stale:
        _pending_bond_proposals.pop(k, None)


# ─── helpers ───────────────────────────────────────────────────────────────

async def _find_pc_by_name_in_room(
    ctx: CommandContext, name: str, room_id: int,
) -> dict | None:
    """Return the first active PC in the room matching `name`
    (case-insensitive), or None. Used for player-flow bond proposals.

    Uses get_characters_in_room (not match_in_room) deliberately:
    bond proposals are co-located only, no wilderness filtering
    needed (Master and Padawan must be in the same room to bond per
    the design's mutual-selection narrative).
    """
    name_norm = name.strip().lower()
    if not name_norm:
        return None
    others = await ctx.db.get_characters_in_room(room_id)
    for o in others:
        if (o.get("name") or "").lower() == name_norm:
            return o
    return None


async def _notify_char_if_online(
    ctx: CommandContext, target_char_id: int, line: str,
) -> bool:
    """Push a line to the target character's session if online.
    Returns True if delivered, False if offline.

    Failure-tolerant: any exception during delivery is logged and
    swallowed (returns False). We never block the caller's command
    on delivery failure.
    """
    try:
        sess = ctx.session_mgr.find_by_character(target_char_id)
        if sess is None:
            return False
        await sess.send_line(line)
        return True
    except Exception:
        log.warning(
            "_notify_char_if_online: delivery to char %s failed",
            target_char_id, exc_info=True,
        )
        return False


def _format_bond_age(bond: dict, now: float | None = None) -> str:
    """Return a friendly age string for a bond's established_at.

    Best-effort: bond_established_at is stored as a SQLite datetime
    string. If parsing fails, fall back to "recently".
    """
    raw = bond.get("bond_established_at") or ""
    if not raw:
        return "recently"
    try:
        # SQLite datetime('now') format: 'YYYY-MM-DD HH:MM:SS'
        from datetime import datetime, timezone
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days >= 1:
            return f"{days} day{'s' if days != 1 else ''} ago"
        hours = delta.seconds // 3600
        if hours >= 1:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        minutes = (delta.seconds % 3600) // 60
        if minutes >= 1:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        return "moments ago"
    except (ValueError, TypeError):
        return "recently"


async def _log_bond_event(
    ctx: CommandContext, char_id: int, action_type: str, summary: str,
    details: str = "{}",
) -> None:
    """Cross-write a bond-related event to pc_action_log.

    Per design §8.12 #2 (+release shared-memory hook): the
    pc_action_log table is the narrative-memory substrate. The
    nightly summarizer (per pc_narrative_memory_design_v1.md §2.2)
    will fold these entries into the long_record so the Director
    AI sees them.

    Failure-tolerant: a log_action exception MUST NOT block the
    underlying bond mutation. We swallow + warn.
    """
    try:
        await ctx.db.log_action(char_id, action_type, summary, details)
    except Exception:
        log.warning(
            "_log_bond_event: log_action failed for char %s action %s",
            char_id, action_type, exc_info=True,
        )


# ─── +master ──────────────────────────────────────────────────────────────

class MasterCommand(BaseCommand):
    """``+master`` — Padawan-side bond status.

    Shows the bonded Master's name, last-seen status, and bond age.
    If the caller has no active bond, says so. If the caller IS a
    Master themselves (no Padawan-side bond), suggests +padawan.
    """
    key = "+master"
    aliases = ["master"]
    help_text = (
        "View your bonded Master's status.\n"
        "\n"
        "USAGE:\n"
        "  +master    Show your current Master, bond age, and "
        "their online status.\n"
        "\n"
        "If you have no active Master bond, the command will say so.\n"
        "Masters: use +padawan to see your Padawan(s).\n"
    )
    usage = "+master"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +master.")
            return

        bond = await ctx.db.get_active_bond_for_padawan(char["id"])
        if not bond:
            await ctx.session.send_line(
                "  You have no active Master bond.\n"
                "  (Masters: see +padawan instead.)"
            )
            return

        master = await ctx.db.get_character(bond["master_char_id"])
        if not master:
            # Should not happen (FK cascade prevents orphaned bonds),
            # but be defensive.
            await ctx.session.send_line(
                "  Your bond is recorded but the Master's character "
                "record is missing. Please notify staff."
            )
            return

        master_sess = ctx.session_mgr.find_by_character(master["id"])
        online_str = (ansi.green("online") if master_sess
                      else ansi.yellow("offline"))
        age = _format_bond_age(bond)

        await ctx.session.send_line(
            f"  {ansi.cyan('Master:')} "
            f"{ansi.bold(master['name'])}  ({online_str})"
        )
        await ctx.session.send_line(
            f"  {ansi.cyan('Bonded:')} {age}"
        )
        # WoW.4 (May 24 2026): Weight-of-War sense through the
        # bond. Per weight_of_war_design_v1.md §7.4, bonded
        # partners can sense each other's Weight state. We piggy-
        # back on +master rather than building a separate
        # +forcebond surface — the bond IS the sensing. Shows
        # the tier name with the substrate's descriptor sentence
        # so the Padawan reads "their Master feels Burdened: ..."
        # rather than seeing a raw number.
        try:
            from engine.weight_of_war import (
                get_tier_for_char, get_descriptor_for_char,
                is_jedi_pc,
            )
            if is_jedi_pc(master):
                tier = get_tier_for_char(master)
                descriptor = get_descriptor_for_char(master)
                await ctx.session.send_line(
                    f"  {ansi.cyan('Through the bond:')} "
                    f"{ansi.bold(tier.replace('_', ' ').title())} "
                    f"— {descriptor}"
                )
        except Exception:
            # Fail soft: a Weight-read failure shouldn't break
            # the rest of the +master output. Logged at debug
            # so silent-except invariants don't flag this site
            # and so any production breakage shows up in logs.
            log.debug(
                "[WoW.4] +master Weight-sense read failed for "
                "master=%s",
                master.get("id"), exc_info=True,
            )
        # Trials surface: count how many of the five Trials are passed.
        # This is informational; the full +trials command is P-M.3.
        import json as _json
        try:
            passed = _json.loads(bond.get("trials_passed_json") or "[]")
            if isinstance(passed, list):
                await ctx.session.send_line(
                    f"  {ansi.cyan('Trials passed:')} "
                    f"{len(passed)} of 5"
                )
        except (ValueError, TypeError):
            pass


# ─── +padawan ─────────────────────────────────────────────────────────────

class PadawanCommand(BaseCommand):
    """``+padawan`` — Master-side bond status.

    Shows the bonded Padawan(s) (plural-by-design, see P-M.1 §4.20)
    along with online status and bond age for each. If the caller
    has no active bonds (as a Master), says so. If the caller has
    only a Padawan-side bond, suggests +master.
    """
    key = "+padawan"
    aliases = ["padawan"]
    help_text = (
        "View your bonded Padawan(s) status.\n"
        "\n"
        "USAGE:\n"
        "  +padawan   Show your current Padawan(s) and their "
        "online status.\n"
        "\n"
        "At launch, a Master has at most 1 active Padawan (cap "
        "settable per-Master by staff).\n"
        "Padawans: use +master to see your Master.\n"
    )
    usage = "+padawan"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +padawan.")
            return

        bonds = await ctx.db.get_active_bonds_for_master(char["id"])
        if not bonds:
            # Soft-help: tell them how to get one.
            cap = int(char.get("master_cap") or 1)
            await ctx.session.send_line(
                "  You have no active Padawan bond."
            )
            await ctx.session.send_line(
                f"  (Your Master-cap is {cap}. To take a Padawan, "
                f"use '+bond <padawan name>' in the same room.)"
            )
            return

        await ctx.session.send_line(
            f"  {ansi.cyan('Active Padawan bond(s):')}"
        )
        # Late imports for the WoW.4 sense-line. See MasterCommand
        # above for the design rationale: the bond IS the sensing,
        # no separate +forcebond command needed.
        try:
            from engine.weight_of_war import (
                get_tier_for_char, get_descriptor_for_char,
                is_jedi_pc,
            )
            _wow_imports_ok = True
        except Exception:
            _wow_imports_ok = False
        for bond in bonds:
            padawan = await ctx.db.get_character(bond["padawan_char_id"])
            if not padawan:
                continue
            sess = ctx.session_mgr.find_by_character(padawan["id"])
            online_str = (ansi.green("online") if sess
                          else ansi.yellow("offline"))
            age = _format_bond_age(bond)
            await ctx.session.send_line(
                f"    {ansi.bold(padawan['name'])}  "
                f"({online_str}, bonded {age})"
            )
            # WoW.4: Weight-of-War sense through the bond.
            if _wow_imports_ok:
                try:
                    if is_jedi_pc(padawan):
                        tier = get_tier_for_char(padawan)
                        descriptor = get_descriptor_for_char(padawan)
                        await ctx.session.send_line(
                            f"      {ansi.cyan('Through the bond:')} "
                            f"{ansi.bold(tier.replace('_', ' ').title())} "
                            f"— {descriptor}"
                        )
                except Exception:
                    # Fail soft: a Weight-read failure shouldn't
                    # break the rest of the +padawan output. Logged
                    # at debug so silent-except invariants don't
                    # flag this site.
                    log.debug(
                        "[WoW.4] +padawan Weight-sense read "
                        "failed for padawan=%s",
                        padawan.get("id"), exc_info=True,
                    )
            # Trials parity: mirror the MasterCommand trials block.
            # A Padawan's Trials progress is written on the bond row
            # (trials_passed_json); Masters see it here per §8.12.
            import json as _json
            try:
                passed = _json.loads(
                    bond.get("trials_passed_json") or "[]"
                )
                if isinstance(passed, list):
                    await ctx.session.send_line(
                        f"      {ansi.cyan('Trials passed:')} "
                        f"{len(passed)} of 5"
                    )
            except (ValueError, TypeError):
                pass


# ─── +bond (with subcommands) ─────────────────────────────────────────────

class BondCommand(BaseCommand):
    """``+bond`` — propose, accept, or decline a Padawan-Master bond.

    Player-flow path per design §8.12 #1:

      +bond <padawan>           Master: propose a bond. Padawan must
                                be in the same room.
      +bond accept <master>     Padawan: accept a pending proposal.
      +bond decline <master>    Padawan: decline a pending proposal.

    Admin path uses the separate `@bond` command (AdminBondCommand
    below) which skips the consent dance.

    Master-cap enforcement (per design §8.12 #3) consults the
    `characters.master_cap` column (v29). Default 1.
    """
    key = "+bond"
    aliases = ["bond"]
    help_text = (
        "Propose, accept, or decline a Padawan-Master bond.\n"
        "\n"
        "USAGE (Master):\n"
        "  +bond <padawan>          Propose a bond. Padawan must be "
        "in the same room.\n"
        "                           Subject to your master_cap "
        "(default 1).\n"
        "\n"
        "USAGE (Padawan):\n"
        "  +bond accept <master>    Accept a pending bond proposal.\n"
        "  +bond decline <master>   Decline a pending bond proposal.\n"
        "\n"
        "Proposals expire 10 minutes after they are made. Staff use "
        "@bond instead.\n"
    )
    usage = "+bond <padawan> | +bond accept <master> | +bond decline <master>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +bond.")
            return

        _prune_expired_proposals()

        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return

        # Subcommand dispatch
        parts = args.split(None, 1)
        first = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if first == "accept":
            if not rest:
                await ctx.session.send_line(
                    "  Usage: +bond accept <master name>")
                return
            await self._handle_accept(ctx, char, rest)
            return
        if first == "decline":
            if not rest:
                await ctx.session.send_line(
                    "  Usage: +bond decline <master name>")
                return
            await self._handle_decline(ctx, char, rest)
            return

        # Default: propose (Master-side).
        # `args` here is the full padawan name (may contain spaces).
        await self._handle_propose(ctx, char, args)

    async def _handle_propose(
        self, ctx: CommandContext, master: dict, padawan_name: str,
    ) -> None:
        # 1. Master-cap check.
        cap = int(master.get("master_cap") or 1)
        existing = await ctx.db.get_active_bonds_for_master(master["id"])
        if len(existing) >= cap:
            await ctx.session.send_line(
                f"  You already have {len(existing)} active "
                f"Padawan bond(s); your master_cap is {cap}."
            )
            await ctx.session.send_line(
                "  Use '+release <padawan>' to dissolve an existing "
                "bond first, or ask staff to raise your cap."
            )
            return

        # 2. Target must be in the same room (co-located bonding).
        padawan = await _find_pc_by_name_in_room(
            ctx, padawan_name, master["room_id"]
        )
        if padawan is None:
            await ctx.session.send_line(
                f"  No player named '{padawan_name}' is here."
            )
            return
        if padawan["id"] == master["id"]:
            await ctx.session.send_line(
                "  You cannot bond with yourself.")
            return

        # 3. Padawan must not already have an active bond.
        existing_p = await ctx.db.get_active_bond_for_padawan(padawan["id"])
        if existing_p is not None:
            await ctx.session.send_line(
                f"  {padawan['name']} already has an active Master "
                f"bond. They must be released or knighted first."
            )
            return

        # 4. Stale-proposal dedup.
        key = (master["id"], padawan["id"])
        existing_prop = _pending_bond_proposals.get(key)
        now = _time.time()
        if existing_prop is not None and (now - existing_prop) < _BOND_PROPOSAL_TTL:
            await ctx.session.send_line(
                f"  You already have a pending bond proposal to "
                f"{padawan['name']} (expires in "
                f"{int(_BOND_PROPOSAL_TTL - (now - existing_prop))}s)."
            )
            return

        # 5. Record + notify.
        _pending_bond_proposals[key] = now
        await ctx.session.send_line(
            f"  {ansi.cyan('You offer to take')} "
            f"{ansi.bold(padawan['name'])} "
            f"{ansi.cyan('as your Padawan.')}"
        )
        await ctx.session.send_line(
            f"  They must type '"
            f"{ansi.yellow('+bond accept ' + master['name'])}"
            f"' to accept (or '+bond decline {master['name']}'). "
            f"Proposal expires in 10 minutes."
        )

        delivered = await _notify_char_if_online(
            ctx, padawan["id"],
            f"\n  {ansi.bold(master['name'])} "
            f"{ansi.cyan('offers to take you as their Padawan.')}\n"
            f"  Type '{ansi.yellow('+bond accept ' + master['name'])}' "
            f"to accept, or '+bond decline {master['name']}' to "
            f"refuse. (Expires in 10 minutes.)\n"
        )
        if not delivered:
            await ctx.session.send_line(
                f"  ({padawan['name']} is offline; they'll be notified "
                f"on next login if the proposal hasn't expired.)"
            )

    async def _handle_accept(
        self, ctx: CommandContext, padawan: dict, master_name: str,
    ) -> None:
        master_name_norm = master_name.strip().lower()
        # Find any pending proposal from a master with this name to
        # this padawan. Master need NOT be in the same room as the
        # Padawan at accept-time (Master may have moved on; that's OK).
        match_key: tuple[int, int] | None = None
        for key in list(_pending_bond_proposals.keys()):
            m_id, p_id = key
            if p_id != padawan["id"]:
                continue
            m = await ctx.db.get_character(m_id)
            if m and (m.get("name") or "").lower() == master_name_norm:
                match_key = key
                break

        if match_key is None:
            await ctx.session.send_line(
                f"  No pending bond proposal from '{master_name}' "
                f"found. (Proposals expire after 10 minutes.)"
            )
            return

        master_id, padawan_id = match_key
        # Re-check Padawan-side and Master-cap (state may have changed
        # since proposal).
        existing_p = await ctx.db.get_active_bond_for_padawan(padawan_id)
        if existing_p is not None:
            _pending_bond_proposals.pop(match_key, None)
            await ctx.session.send_line(
                "  You already have an active Master bond. "
                "The pending proposal is now void."
            )
            return

        master = await ctx.db.get_character(master_id)
        if master is None:
            _pending_bond_proposals.pop(match_key, None)
            await ctx.session.send_line(
                "  The proposing Master's character is no longer "
                "available. The pending proposal is now void."
            )
            return
        cap = int(master.get("master_cap") or 1)
        existing_m = await ctx.db.get_active_bonds_for_master(master_id)
        if len(existing_m) >= cap:
            _pending_bond_proposals.pop(match_key, None)
            await ctx.session.send_line(
                f"  {master['name']} has reached their Master-cap "
                f"since proposing. The proposal is now void."
            )
            return

        # Create the bond.
        try:
            bond_id = await ctx.db.create_bond(master_id, padawan_id)
        except ValueError as e:
            log.warning("BondCommand.accept: create_bond failed: %s", e)
            _pending_bond_proposals.pop(match_key, None)
            await ctx.session.send_line(
                "  Bond could not be created (you may already have an "
                "active bond). The pending proposal is now void."
            )
            return

        _pending_bond_proposals.pop(match_key, None)

        # Notify both sides.
        await ctx.session.send_line(
            f"  {ansi.cyan('You accept the bond.')} "
            f"{ansi.bold(master['name'])} is now your Master."
        )
        await _notify_char_if_online(
            ctx, master_id,
            f"\n  {ansi.bold(padawan['name'])} "
            f"{ansi.cyan('has accepted your bond proposal.')} "
            f"They are now your Padawan.\n"
        )

        # Audit log on both sides (narrative-memory cross-write).
        await _log_bond_event(
            ctx, master_id, "bond_established",
            f"Took {padawan['name']} as Padawan (bond #{bond_id}).",
        )
        await _log_bond_event(
            ctx, padawan_id, "bond_established",
            f"Accepted {master['name']} as Master (bond #{bond_id}).",
        )

    async def _handle_decline(
        self, ctx: CommandContext, padawan: dict, master_name: str,
    ) -> None:
        master_name_norm = master_name.strip().lower()
        match_key: tuple[int, int] | None = None
        master_obj = None
        for key in list(_pending_bond_proposals.keys()):
            m_id, p_id = key
            if p_id != padawan["id"]:
                continue
            m = await ctx.db.get_character(m_id)
            if m and (m.get("name") or "").lower() == master_name_norm:
                match_key = key
                master_obj = m
                break

        if match_key is None:
            await ctx.session.send_line(
                f"  No pending bond proposal from '{master_name}' "
                f"to decline."
            )
            return

        _pending_bond_proposals.pop(match_key, None)
        master_id = match_key[0]

        await ctx.session.send_line(
            f"  You decline the bond proposal from "
            f"{master_obj['name'] if master_obj else master_name}."
        )
        await _notify_char_if_online(
            ctx, master_id,
            f"\n  {ansi.yellow(padawan['name'])} has declined "
            f"your bond proposal.\n"
        )


# ─── +release ─────────────────────────────────────────────────────────────

class ReleaseCommand(BaseCommand):
    """``+release`` — Master-initiated voluntary bond dissolution.

    Per design §8.12 #2 (locked): voluntary + Padawan-side narrative
    event. We mark the bond dissolved via dissolve_bond, notify the
    Padawan if online, and cross-write a pc_action_log entry on
    BOTH sides so the narrative-memory summarizer surfaces it.

    Usage:
      +release <padawan>            Dissolve bond with named Padawan.
      +release <padawan> = <reason> Same, with a recorded reason.

    If the Master has exactly one active bond and supplies no
    padawan name, we'll target that one (convenience). With
    multiple bonds (Council-authorized), the name is required.
    """
    key = "+release"
    aliases = ["release-padawan"]
    help_text = (
        "Dissolve an active Padawan-Master bond (Master-side).\n"
        "\n"
        "USAGE:\n"
        "  +release <padawan>             Dissolve bond. The Padawan "
        "is notified.\n"
        "  +release <padawan> = <reason>  Same, with a recorded "
        "reason.\n"
        "  +release                       (With 1 active bond only) "
        "release that bond.\n"
        "\n"
        "The dissolution is logged on BOTH characters' narrative "
        "records. To regain a\nPadawan, use '+bond <padawan>' again "
        "later.\n"
    )
    usage = "+release [<padawan> [= <reason>]]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +release.")
            return

        bonds = await ctx.db.get_active_bonds_for_master(char["id"])
        if not bonds:
            await ctx.session.send_line(
                "  You have no active Padawan bonds to release.")
            return

        args = (ctx.args or "").strip()
        target_name = ""
        reason = ""

        if "=" in args:
            name_part, _, reason_part = args.partition("=")
            target_name = name_part.strip()
            reason = reason_part.strip()
        else:
            target_name = args.strip()

        # Resolve target bond
        target_bond = None
        if not target_name:
            if len(bonds) == 1:
                target_bond = bonds[0]
            else:
                await ctx.session.send_line(
                    f"  You have {len(bonds)} active bonds. Specify "
                    f"which Padawan: '+release <name>'."
                )
                return
        else:
            tn_norm = target_name.lower()
            for b in bonds:
                p = await ctx.db.get_character(b["padawan_char_id"])
                if p and (p.get("name") or "").lower() == tn_norm:
                    target_bond = b
                    break
            if target_bond is None:
                await ctx.session.send_line(
                    f"  You have no active bond with a Padawan "
                    f"named '{target_name}'."
                )
                return

        padawan = await ctx.db.get_character(target_bond["padawan_char_id"])
        if padawan is None:
            await ctx.session.send_line(
                "  Padawan record missing. Please notify staff.")
            return

        dissolved = await ctx.db.dissolve_bond(
            target_bond["id"], reason=reason or "master_voluntary",
        )
        if not dissolved:
            await ctx.session.send_line(
                "  Bond could not be dissolved (may already be "
                "inactive). Please notify staff."
            )
            return

        # Master-side echo
        reason_str = f" ({reason})" if reason else ""
        await ctx.session.send_line(
            f"  {ansi.cyan('You release')} "
            f"{ansi.bold(padawan['name'])} "
            f"{ansi.cyan('from your guidance.')}{reason_str}"
        )

        # Padawan-side notification (online) — design §8.12 #2.
        # The narrative "Force-bond loss" line is the player-visible
        # cross-write seam. The richer Force-vision payload is a
        # future drop on top of the shared-memory subsystem (§5.4).
        delivered = await _notify_char_if_online(
            ctx, padawan["id"],
            f"\n  {ansi.dim('You feel the bond with')} "
            f"{ansi.bold(char['name'])} "
            f"{ansi.dim('go quiet. They have released you.')}"
            + (f"\n  Reason given: {reason}" if reason else "")
            + "\n",
        )

        # Audit log on BOTH sides — narrative-memory cross-write.
        master_summary = (
            f"Released Padawan {padawan['name']}"
            + (f" (reason: {reason})" if reason else "")
            + "."
        )
        padawan_summary = (
            f"Released from bond with Master {char['name']}"
            + (f" (reason: {reason})" if reason else "")
            + "."
        )
        await _log_bond_event(
            ctx, char["id"], "bond_dissolved", master_summary,
        )
        await _log_bond_event(
            ctx, padawan["id"], "bond_dissolved", padawan_summary,
        )

        if not delivered:
            # Tell the Master the Padawan was offline; they'll find
            # out next login when their +master shows "no active bond".
            await ctx.session.send_line(
                f"  ({padawan['name']} is offline; the dissolution "
                f"is recorded.)"
            )


# ─── @bond (admin) ────────────────────────────────────────────────────────

class AdminBondCommand(BaseCommand):
    """``@bond`` — staff/admin direct bond establishment.

    Per design §8.12 #1: admin path that skips the player-flow
    consent dance. Used for tester-cohort assignment and
    staff-mediated pairings.

    Usage:
      @bond <master> = <padawan>

    Both characters must exist. The Master's master_cap is still
    enforced — to override, staff should raise the cap first via
    direct SQL or a future admin command.
    """
    key = "@bond"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin: directly establish a Master-Padawan bond.\n"
        "\n"
        "USAGE:\n"
        "  @bond <master> = <padawan>\n"
        "\n"
        "Bypasses the player-flow consent prompt. The Master's "
        "master_cap is still enforced.\n"
        "To raise an individual Master's cap, edit "
        "characters.master_cap directly.\n"
    )
    usage = "@bond <master> = <padawan>"

    async def execute(self, ctx: CommandContext):
        args = (ctx.args or "").strip()
        if "=" not in args:
            await ctx.session.send_line(
                "  Usage: @bond <master name> = <padawan name>")
            return

        m_part, _, p_part = args.partition("=")
        m_name = m_part.strip()
        p_name = p_part.strip()
        if not m_name or not p_name:
            await ctx.session.send_line(
                "  Both master and padawan names are required.")
            return

        master = await ctx.db.get_character_by_name(m_name)
        if master is None:
            await ctx.session.send_line(
                f"  No active character named '{m_name}'.")
            return
        padawan = await ctx.db.get_character_by_name(p_name)
        if padawan is None:
            await ctx.session.send_line(
                f"  No active character named '{p_name}'.")
            return
        if master["id"] == padawan["id"]:
            await ctx.session.send_line(
                "  A character cannot bond with themselves.")
            return

        # Master-cap check (DB-driven, per design §8.12 #3).
        cap = int(master.get("master_cap") or 1)
        existing_m = await ctx.db.get_active_bonds_for_master(master["id"])
        if len(existing_m) >= cap:
            await ctx.session.send_line(
                f"  {master['name']} has {len(existing_m)} active "
                f"bond(s); master_cap is {cap}. Raise the cap first."
            )
            return

        # Padawan-side single-bond invariant.
        existing_p = await ctx.db.get_active_bond_for_padawan(padawan["id"])
        if existing_p is not None:
            await ctx.session.send_line(
                f"  {padawan['name']} already has an active Master "
                f"bond. Dissolve it first."
            )
            return

        try:
            bond_id = await ctx.db.create_bond(master["id"], padawan["id"])
        except ValueError as e:
            await ctx.session.send_line(
                f"  create_bond rejected: {e}")
            return

        await ctx.session.send_line(
            f"  {ansi.green('@bond:')} bond #{bond_id} established: "
            f"{master['name']} → {padawan['name']}"
        )

        # Notify both parties if online.
        await _notify_char_if_online(
            ctx, master["id"],
            f"\n  {ansi.cyan('Staff has bonded you to')} "
            f"{ansi.bold(padawan['name'])} "
            f"{ansi.cyan('as your Padawan.')}\n"
        )
        await _notify_char_if_online(
            ctx, padawan["id"],
            f"\n  {ansi.cyan('Staff has bonded you to')} "
            f"{ansi.bold(master['name'])} "
            f"{ansi.cyan('as your Master.')}\n"
        )

        # Audit log on both sides.
        await _log_bond_event(
            ctx, master["id"], "bond_established",
            f"Staff-bonded to Padawan {padawan['name']} "
            f"(bond #{bond_id}, @bond).",
        )
        await _log_bond_event(
            ctx, padawan["id"], "bond_established",
            f"Staff-bonded to Master {master['name']} "
            f"(bond #{bond_id}, @bond).",
        )


# ─── +leave-master ────────────────────────────────────────────────────────

class LeaveMasterCommand(BaseCommand):
    """``+leave-master`` — Padawan-initiated voluntary bond dissolution.

    Per design §8: a Padawan may voluntarily leave their Master. A
    reason is REQUIRED to discourage impulsive breaks. The dissolution
    is logged on both sides (narrative-memory cross-write, same seam
    as ReleaseCommand) and the Master is notified if online. No
    staff-approval gate in this drop (noted: staff can review logs).

    Usage:
      +leave-master <reason>    Dissolve active bond. Reason required.
    """
    key = "+leave-master"
    aliases = ["leavemaster"]
    help_text = (
        "Voluntarily leave your Master-Padawan bond (Padawan-side).\n"
        "\n"
        "USAGE:\n"
        "  +leave-master <reason>   Dissolve your bond. A reason is "
        "required.\n"
        "\n"
        "The dissolution is logged on both characters' narrative records\n"
        "and your Master is notified. Masters: use +release instead.\n"
    )
    usage = "+leave-master <reason>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +leave-master.")
            return

        bond = await ctx.db.get_active_bond_for_padawan(char["id"])
        if not bond:
            await ctx.session.send_line(
                "  You have no active Master bond.\n"
                "  (Masters: use +release.)"
            )
            return

        reason = (ctx.args or "").strip()
        if not reason:
            await ctx.session.send_line(
                "  A reason is required to leave your Master.\n"
                f"  Usage: {self.usage}"
            )
            return

        master = await ctx.db.get_character(bond["master_char_id"])
        if master is None:
            await ctx.session.send_line(
                "  Master record missing. Please notify staff.")
            return

        # Incorporate the player's reason into the dissolved_reason
        # column using the same pattern as ReleaseCommand: we pass
        # a prefixed string so staff audit logs show initiative.
        dissolved = await ctx.db.dissolve_bond(
            bond["id"], reason=f"padawan_voluntary: {reason}",
        )
        if not dissolved:
            await ctx.session.send_line(
                "  Bond could not be dissolved (may already be "
                "inactive). Please notify staff."
            )
            return

        # Padawan-side echo
        await ctx.session.send_line(
            f"  {ansi.cyan('You step back from the bond with')} "
            f"{ansi.bold(master['name'])}"
            f"{ansi.cyan('.')}\n"
            f"  Reason recorded: {reason}"
        )

        # Master notification (online delivery, best-effort).
        delivered = await _notify_char_if_online(
            ctx, master["id"],
            f"\n  {ansi.dim('You feel the bond with')} "
            f"{ansi.bold(char['name'])} "
            f"{ansi.dim('release. They have stepped back.')}\n"
            f"  Reason given: {reason}\n",
        )

        # Audit log on BOTH sides — narrative-memory cross-write,
        # mirrors the two _log_bond_event calls in ReleaseCommand.
        padawan_summary = (
            f"Left bond with Master {master['name']} "
            f"(reason: {reason})."
        )
        master_summary = (
            f"Padawan {char['name']} left bond "
            f"(reason: {reason})."
        )
        await _log_bond_event(
            ctx, char["id"], "bond_dissolved", padawan_summary,
        )
        await _log_bond_event(
            ctx, master["id"], "bond_dissolved", master_summary,
        )

        if not delivered:
            await ctx.session.send_line(
                f"  ({master['name']} is offline; the dissolution "
                f"is recorded.)"
            )


# ─── registration ─────────────────────────────────────────────────────────

def register_padawan_master_commands(registry) -> None:
    """Register all P-M.2 commands with the given CommandRegistry.

    Called from server/game_server.py during registry init, after
    register_all (builtin_commands). The order is irrelevant
    because none of these commands collide with existing keys
    (verified: +master, +padawan, +bond, +release, @bond,
    +leave-master are all new).
    """
    for cmd in (
        MasterCommand(),
        PadawanCommand(),
        BondCommand(),
        ReleaseCommand(),
        AdminBondCommand(),
        LeaveMasterCommand(),
    ):
        registry.register(cmd)
