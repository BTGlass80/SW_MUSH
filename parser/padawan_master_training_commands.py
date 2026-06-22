# -*- coding: utf-8 -*-
"""
parser/padawan_master_training_commands.py — P-M.3 (May 22 2026)

Padawan-Master training commands per
`padawan_master_system_design_v1.md` §5.2.

Three commands:

  +teach <power>           Master: teach the Padawan a Force power
                           (or `+teach <padawan> <power>` if the
                           Master has multiple active bonds — though
                           launch cap is 1 bond per Master so usually
                           the form `+teach <power>` is what gets used).

  +learn <power> from <master>
                           Padawan: request instruction. Sets an
                           in-memory pending request that the
                           Master's `+teach <power>` will accept.

  +spar                    Either: initiate a training duel between
                           bonded pair. Launch-MVP scope: validates
                           bond + same-room + 24h cooldown, awards
                           1 CP to both PCs, logs in training_log.
                           Does NOT yet enter a full combat loop
                           (deferred follow-up).

State substrates:
  - Pending learn-requests: per-process in-memory dict
    `_LEARN_REQUESTS: dict[int, _LearnRequest]` keyed on
    padawan_char_id. 5-minute expiry. Same pattern as SRB.3's
    `_LEAD_OFFERS`.
  - Persistent training events: `training_log` table (schema v34).
  - Spar cooldown: derived from training_log's last 'spar' row
    for this bond.

The `+teach` action spends Padawan's CP if the Padawan's Force
skill is below 1D — bringing it up to 1D minimum so they can
attempt the power. If already at 1D+, the teach is a free
narrative/audit-only event (per design: "Padawan gains the power
at 1D if they meet prerequisites").
"""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

# Per design §5.2: 1 CP-granting spar per in-game day per pair.
# We use real-time 24h for "1 in-game day" since no in-game-time
# system exists at HEAD.
SPAR_COOLDOWN_SECS = 24 * 3600
SPAR_CP_REWARD = 1

# Pending `+learn` request expiry. 5 minutes lets a Padawan request,
# then ping the Master via OOC channel, then have the Master `+teach`.
LEARN_REQUEST_TTL_SECS = 300


# ── In-memory state ──────────────────────────────────────────────────────


@dataclass
class _LearnRequest:
    """Padawan's pending `+learn <power> from <master>` request."""
    padawan_id: int
    master_id: int
    power_key: str
    created_at: float = field(default_factory=time.time)

    def is_expired(self, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.time()
        return (now - self.created_at) >= LEARN_REQUEST_TTL_SECS


# Keyed by padawan_id. A Padawan has at most one pending request.
_LEARN_REQUESTS: dict[int, _LearnRequest] = {}


def _reset_for_test() -> None:
    """Wipe in-memory state. Test-only."""
    _LEARN_REQUESTS.clear()


def _get_pending_learn(
    padawan_id: int, master_id: int, power_key: str,
    now: Optional[float] = None,
) -> Optional[_LearnRequest]:
    """Return the Padawan's pending request matching this Master +
    power, or None. Cleans up expired entries inline."""
    if now is None:
        now = time.time()
    req = _LEARN_REQUESTS.get(padawan_id)
    if req is None:
        return None
    if req.is_expired(now):
        _LEARN_REQUESTS.pop(padawan_id, None)
        return None
    if req.master_id != master_id or req.power_key != power_key:
        return None
    return req


# ── Force-power lookup ────────────────────────────────────────────────────


def _normalize_power_key(raw: str) -> str:
    """User input → POWERS key. Accepts both 'Telekinesis' and
    'telekinesis' and 'tele kinesis' (spaces collapse)."""
    return raw.strip().lower().replace(" ", "_")


def _lookup_power(raw: str):
    """Return a ForcePower (from engine.force_powers.POWERS) or None."""
    from engine.force_powers import POWERS
    key = _normalize_power_key(raw)
    return POWERS.get(key)


# ── +learn command ───────────────────────────────────────────────────────


class LearnCommand(BaseCommand):
    key = "+learn"
    aliases: list[str] = []
    help_text = (
        "Request training in a Force power from your Master.\n"
        "Usage: +learn <power> from <master>"
    )
    usage = "+learn <power> from <master>"
    valid_switches: list[str] = []

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("  You can't learn while not in-game.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await session.send_line("  Usage: +learn <power> from <master>")
            return

        # Parse "<power> from <master>"
        lowered = args.lower()
        idx = lowered.rfind(" from ")
        if idx == -1:
            await session.send_line("  Usage: +learn <power> from <master>")
            return
        power_raw = args[:idx].strip()
        master_name = args[idx + len(" from "):].strip()
        if not power_raw or not master_name:
            await session.send_line("  Usage: +learn <power> from <master>")
            return

        # Validate power exists
        power = _lookup_power(power_raw)
        if power is None:
            await session.send_line(
                f"  '{power_raw}' is not a recognized Force power."
            )
            return

        # Resolve master char
        try:
            master = await ctx.db.get_character_by_name(master_name)
        except Exception:
            log.warning("+learn: DB lookup failed", exc_info=True)
            master = None
        if not master:
            await session.send_line(
                f"  No character named '{master_name}'."
            )
            return

        # Verify bond exists with this master, as Padawan
        try:
            bond = await ctx.db.get_active_bond_for_padawan(char["id"])
        except Exception:
            log.warning("+learn: bond lookup failed", exc_info=True)
            bond = None
        if not bond:
            await session.send_line(
                "  You don't have an active Padawan bond."
            )
            return
        if int(bond["master_char_id"]) != int(master["id"]):
            await session.send_line(
                f"  {master['name']} is not your Master."
            )
            return

        # Stage the request
        _LEARN_REQUESTS[char["id"]] = _LearnRequest(
            padawan_id=char["id"],
            master_id=master["id"],
            power_key=power.key,
        )

        await session.send_line(
            f"  {ansi.BRIGHT_GREEN}[LEARN]{ansi.RESET} "
            f"You request instruction in "
            f"{ansi.BRIGHT_CYAN}{power.name}{ansi.RESET} from "
            f"{ansi.player_name(master['name'])}. "
            f"They have {LEARN_REQUEST_TTL_SECS // 60} minutes to "
            f"respond with +teach."
        )
        # Notify the master if online
        master_sess = ctx.session_mgr.find_by_character(master["id"])
        if master_sess is not None:
            await master_sess.send_line(
                f"  {ansi.BRIGHT_YELLOW}[LEARN REQUEST]{ansi.RESET} "
                f"{ansi.player_name(char['name'])} requests instruction "
                f"in {ansi.BRIGHT_CYAN}{power.name}{ansi.RESET}. "
                f"Use {ansi.BRIGHT_WHITE}+teach {power.key}{ansi.RESET} "
                f"to accept."
            )


# ── +teach command ───────────────────────────────────────────────────────


class TeachPowerCommand(BaseCommand):
    """Master command. Teaches the Padawan a Force power.

    Naming note: this lives at command key `+teach` to match design
    §5.2. The schematics-teach command in parser/crafting_commands.py
    uses bare `teach` (no `+`), so the namespaces don't collide.
    """
    key = "+teach"
    aliases: list[str] = []
    help_text = (
        "Teach your Padawan a Force power.\n"
        "Usage: +teach <power>\n"
        "       +teach <padawan> <power>\n"
        "\n"
        "You must have an active bond with the Padawan and both must\n"
        "be in the same room. If the Padawan's underlying Force skill\n"
        "is below 1D, this spends the Padawan's CP to bring it up to\n"
        "1D minimum. Otherwise the teaching is narrative-only and\n"
        "logged for audit."
    )
    usage = "+teach <power>  |  +teach <padawan> <power>"
    valid_switches: list[str] = []

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("  You can't teach while not in-game.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await session.send_line(
                f"  Usage: {self.usage}"
            )
            return

        # Determine Padawan + power: support `+teach <power>` (single
        # bond) and `+teach <padawan> <power>` (multi-bond Masters,
        # post-launch case).
        parts = args.split(None, 1)
        padawan_arg = None
        power_arg = None

        # Strategy: try as `<power>` first (single token or known
        # power); if it doesn't resolve as a power, treat as
        # `<padawan> <power>`.
        if len(parts) == 1:
            # Single token: must be a power, and Master needs exactly
            # one active bond.
            power = _lookup_power(parts[0])
            if power is None:
                # Maybe it's a padawan name with no power — error.
                await session.send_line(
                    f"  '{parts[0]}' is not a recognized Force power."
                )
                return
            power_arg = parts[0]
        else:
            # Two+ tokens. Try the WHOLE thing as a power name first
            # (multi-word power like "telekinesis kill" doesn't exist
            # but "lightsaber combat" style might).
            power = _lookup_power(args)
            if power is not None:
                power_arg = args
            else:
                # Treat first token as padawan name, rest as power.
                padawan_arg = parts[0]
                power_arg = parts[1]
                power = _lookup_power(power_arg)
                if power is None:
                    await session.send_line(
                        f"  '{power_arg}' is not a recognized Force power."
                    )
                    return

        # Resolve bond(s).
        try:
            bonds = await ctx.db.get_active_bonds_for_master(char["id"])
        except Exception:
            log.warning("+teach: bonds lookup failed", exc_info=True)
            bonds = []
        if not bonds:
            await session.send_line(
                "  You don't have any active Padawans to teach."
            )
            return

        # Pick the bond + padawan.
        target_bond = None
        if padawan_arg is not None:
            # Explicit padawan name
            padawan_arg_l = padawan_arg.lower()
            for b in bonds:
                try:
                    pad = await ctx.db.get_character(b["padawan_char_id"])
                    if pad and pad["name"].lower() == padawan_arg_l:
                        target_bond = b
                        target_padawan = pad
                        break
                except Exception:
                    continue
            if target_bond is None:
                await session.send_line(
                    f"  '{padawan_arg}' is not one of your Padawans."
                )
                return
        else:
            # No explicit padawan: must have exactly one bond
            if len(bonds) > 1:
                await session.send_line(
                    "  You have multiple active Padawans — specify which:"
                    " +teach <padawan> <power>"
                )
                return
            target_bond = bonds[0]
            target_padawan = await ctx.db.get_character(
                target_bond["padawan_char_id"]
            )
            if target_padawan is None:
                await session.send_line(
                    "  Your Padawan's character record is missing."
                )
                return

        # Same-room check (§5.2)
        if int(target_padawan.get("room_id") or 0) != int(char.get("room_id") or 0):
            await session.send_line(
                f"  {target_padawan['name']} is not in this room."
            )
            return

        # Master must be able to attempt the power (have the Force skills).
        master_can_attempt = await _master_can_attempt_power(
            ctx, char, power,
        )
        if not master_can_attempt:
            await session.send_line(
                f"  You don't know {power.name} well enough to teach it. "
                "Master a power before passing it on."
            )
            return

        # Check for pending +learn request (consumes if matched)
        pending = _get_pending_learn(
            padawan_id=target_padawan["id"],
            master_id=char["id"],
            power_key=power.key,
        )
        if pending is not None:
            # Consume the request
            _LEARN_REQUESTS.pop(target_padawan["id"], None)

        # Bring Padawan's relevant skill to 1D if needed.
        # Per design: "Padawan gains the power at 1D if they meet
        # prerequisites; ... Uses CP from Padawan."
        # We pick the FIRST skill in power.skills as the primary
        # gate (e.g. control for Accelerate Healing, sense for
        # Life Detection). If all required skills already at 1D+,
        # the teach is free.

        result = await _ensure_padawan_skills_one_die(
            ctx, target_padawan, power,
        )
        if result.get("error"):
            await session.send_line(f"  {result['error']}")
            return

        cp_spent = int(result.get("cp_spent", 0))
        skills_raised = result.get("skills_raised", [])

        # Append training_log entry
        try:
            await ctx.db.insert_training_log(
                bond_id=int(target_bond["id"]),
                master_id=int(char["id"]),
                padawan_id=int(target_padawan["id"]),
                event_type="teach",
                payload={
                    "power_key": power.key,
                    "power_name": power.name,
                    "cp_spent": cp_spent,
                    "skills_raised": skills_raised,
                    "had_pending_request": pending is not None,
                },
            )
        except Exception:
            log.warning("+teach: training_log insert failed",
                        exc_info=True)

        # Surface to both sides.
        if skills_raised:
            raised_str = ", ".join(
                f"{s.title()}" for s in skills_raised
            )
            detail = (
                f"  {ansi.DIM}({target_padawan['name']} spent {cp_spent} CP "
                f"to bring {raised_str} to 1D minimum.){ansi.RESET}"
            )
        else:
            detail = (
                f"  {ansi.DIM}({target_padawan['name']} already had "
                f"the prerequisite Force skills.){ansi.RESET}"
            )

        await session.send_line(
            f"  {ansi.BRIGHT_GREEN}[TEACH]{ansi.RESET} "
            f"You teach {ansi.player_name(target_padawan['name'])} "
            f"the discipline of {ansi.BRIGHT_CYAN}{power.name}{ansi.RESET}."
        )
        await session.send_line(detail)

        # Notify Padawan if online
        pad_sess = ctx.session_mgr.find_by_character(target_padawan["id"])
        if pad_sess is not None:
            await pad_sess.send_line(
                f"  {ansi.BRIGHT_GREEN}[TAUGHT]{ansi.RESET} "
                f"{ansi.player_name(char['name'])} teaches you "
                f"{ansi.BRIGHT_CYAN}{power.name}{ansi.RESET}."
            )
            if cp_spent:
                await pad_sess.send_line(
                    f"  {ansi.DIM}({cp_spent} CP spent to learn this "
                    f"discipline.){ansi.RESET}"
                )

        # Broadcast quietly to the room
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {ansi.player_name(char['name'])} guides "
            f"{ansi.player_name(target_padawan['name'])} through a "
            f"lesson in {power.name}.",
            exclude=session,
            source_char=char,
        )


async def _master_can_attempt_power(
    ctx, master_char_row: dict, power,
) -> bool:
    """True if the Master has at least 1D in every required Force skill."""
    # Load skills as dice pools
    try:
        skills = json.loads(master_char_row.get("skills") or "{}")
    except Exception:
        skills = {}
    try:
        attrs = json.loads(master_char_row.get("attributes") or "{}")
    except Exception:
        attrs = {}

    for skill_key in power.skills:
        # Master must have 1D in this skill (either in attributes or
        # in skills JSON — both are stored as dice strings).
        if _has_one_die(skills.get(skill_key)) or _has_one_die(attrs.get(skill_key)):
            continue
        return False
    return True


def _has_one_die(value) -> bool:
    """True if the dice string represents at least 1D."""
    if value is None:
        return False
    try:
        s = str(value).strip().upper()
        if not s:
            return False
        # Parse "3D", "3D+2", "1D" etc.
        if "D" in s:
            dice_part = s.split("D", 1)[0].strip()
            if not dice_part:
                return False
            return int(dice_part) >= 1
        # Bare integer — pips, not enough
        return False
    except (ValueError, TypeError):
        return False


async def _ensure_padawan_skills_one_die(
    ctx, padawan_row: dict, power,
) -> dict:
    """Bring the Padawan's required Force skills to 1D if any are
    below. Spends CP from the Padawan's pool.

    Returns: {cp_spent, skills_raised, error}.

    Skills are stored in the `skills` JSON column. The cost per skill
    is the attribute's dice count (matches the train command's
    cost-per-pip model). Bringing a 0D skill to 1D costs 3 pips, so
    cost = 3 * attr_dice. If the Padawan can't afford, returns an
    error string.
    """
    try:
        skills = json.loads(padawan_row.get("skills") or "{}")
    except Exception:
        skills = {}
    try:
        attrs = json.loads(padawan_row.get("attributes") or "{}")
    except Exception:
        attrs = {}

    skills_raised = []
    cp_spent = 0
    cp_available = int(padawan_row.get("character_points") or 0)

    for skill_key in power.skills:
        if _has_one_die(skills.get(skill_key)) or _has_one_die(attrs.get(skill_key)):
            continue
        # Need to bring this skill from 0 → 1D.
        # Look up cost: each pip costs `attr_dice` CP per the
        # train command. To go 0 → 1D = 3 pips, so cost = 3 * attr_dice.
        attr_value = attrs.get(skill_key)
        attr_dice = _dice_count_from_str(attr_value) or 2  # default 2D
        per_pip = max(1, attr_dice)
        cost = per_pip * 3

        if cp_available < cost:
            return {
                "error": (
                    f"{padawan_row['name']} needs {cost} CP to learn "
                    f"{skill_key.title()} (has {cp_available} CP)."
                ),
            }

        cp_available -= cost
        cp_spent += cost
        # Force skills (control/sense/alter) are ATTRIBUTES, not entries in
        # the skills blob. from_db_dict derives force_sensitive=True from
        # non-zero control/sense/alter in the attributes JSON; writing them
        # into the skills dict creates a phantom that the derivation never
        # reads. Write to attrs and persist via attributes=.
        attrs[skill_key] = "1D"
        skills_raised.append(skill_key)

    if skills_raised:
        try:
            await ctx.db.save_character(
                padawan_row["id"],
                attributes=json.dumps(attrs),
                character_points=cp_available,
            )
        except Exception:
            log.warning("_ensure_padawan_skills: save_character failed",
                        exc_info=True)
            return {
                "error": "Failed to persist Padawan's training.",
            }

    return {
        "cp_spent": cp_spent,
        "skills_raised": skills_raised,
    }


def _dice_count_from_str(value) -> int:
    if value is None:
        return 0
    try:
        s = str(value).strip().upper()
        if "D" in s:
            return int(s.split("D", 1)[0].strip() or "0")
        return 0
    except (ValueError, TypeError):
        return 0


# ── +spar command ────────────────────────────────────────────────────────


class SparCommand(BaseCommand):
    key = "+spar"
    aliases: list[str] = []
    help_text = (
        "Initiate a training lightsaber duel with your bonded\n"
        "Master or Padawan. Grants 1 CP to both PCs.\n"
        "\n"
        "Cooldown: 1 CP-granting spar per 24h per bonded pair.\n"
        "\n"
        "Launch-MVP scope: a narrative spar awarding CP. The full\n"
        "combat-loop integration (non-lethal training mode in\n"
        "engine/combat.py) is a follow-up drop."
    )
    usage = "+spar"
    valid_switches: list[str] = []

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("  You can't spar while not in-game.")
            return

        # Find an active bond as either Master or Padawan.
        bond = None
        partner = None
        try:
            # Check Padawan side first (typical use)
            bond = await ctx.db.get_active_bond_for_padawan(char["id"])
            if bond is not None:
                partner_id = int(bond["master_char_id"])
            else:
                bonds = await ctx.db.get_active_bonds_for_master(char["id"])
                if len(bonds) == 0:
                    await session.send_line(
                        "  You're not in an active Master-Padawan bond."
                    )
                    return
                if len(bonds) > 1:
                    # Multi-bond Master case — for launch-MVP we just
                    # pick the first; future: +spar <padawan>
                    pass
                bond = bonds[0]
                partner_id = int(bond["padawan_char_id"])
            partner = await ctx.db.get_character(partner_id)
        except Exception:
            log.warning("+spar: bond lookup failed", exc_info=True)
            partner = None

        if partner is None:
            await session.send_line(
                "  Your bond-partner's character record is missing."
            )
            return

        # Same-room check
        if int(partner.get("room_id") or 0) != int(char.get("room_id") or 0):
            await session.send_line(
                f"  {partner['name']} is not in this room."
            )
            return

        # Cooldown check (24h per pair)
        try:
            last_spar = await ctx.db.get_last_spar_for_bond(int(bond["id"]))
        except Exception:
            log.warning("+spar: last_spar lookup failed", exc_info=True)
            last_spar = None
        now = time.time()
        if last_spar is not None:
            elapsed = now - float(last_spar.get("created_at") or 0)
            if elapsed < SPAR_COOLDOWN_SECS:
                remaining = SPAR_COOLDOWN_SECS - elapsed
                hours = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                await session.send_line(
                    f"  You sparred too recently to gain training value. "
                    f"({hours}h {mins}m before next CP-awarding spar.)"
                )
                return

        # Award CP to both — launch-MVP scope per design §11
        try:
            await ctx.db.cp_add_character_points(
                char["id"], SPAR_CP_REWARD,
            )
            await ctx.db.cp_add_character_points(
                partner["id"], SPAR_CP_REWARD,
            )
            # T3.19 telemetry: spar-training CP (direct, bypasses the tick cap).
            # One cp_income event per recipient; fail-open never blocks +spar.
            try:
                from engine.telemetry import emit_cp_income
                emit_cp_income("padawan_training", char["id"],
                               cp_gained=SPAR_CP_REWARD)
                emit_cp_income("padawan_training", partner["id"],
                               cp_gained=SPAR_CP_REWARD)
            except Exception:
                log.debug("cp_income telemetry emit failed", exc_info=True)
        except Exception:
            log.warning("+spar: CP award failed", exc_info=True)
            await session.send_line(
                "  The spar happened, but CP could not be awarded."
            )
            return

        # Log to training_log
        try:
            await ctx.db.insert_training_log(
                bond_id=int(bond["id"]),
                master_id=int(bond["master_char_id"]),
                padawan_id=int(bond["padawan_char_id"]),
                event_type="spar",
                payload={
                    "initiator_id": int(char["id"]),
                    "cp_each": SPAR_CP_REWARD,
                },
            )
        except Exception:
            log.warning("+spar: training_log insert failed", exc_info=True)

        # Refresh local cache
        try:
            char["character_points"] = int(char.get("character_points") or 0) + SPAR_CP_REWARD
        except Exception:
            log.debug(
                "+spar: local CP cache refresh failed (cosmetic; "
                "DB write already succeeded)",
                exc_info=True,
            )

        # Surfacing
        await session.send_line(
            f"  {ansi.BRIGHT_GREEN}[SPAR]{ansi.RESET} "
            f"You spar with {ansi.player_name(partner['name'])}. "
            f"Both of you gain {ansi.BRIGHT_CYAN}+{SPAR_CP_REWARD} CP{ansi.RESET}."
        )
        partner_sess = ctx.session_mgr.find_by_character(partner["id"])
        if partner_sess is not None:
            await partner_sess.send_line(
                f"  {ansi.BRIGHT_GREEN}[SPAR]{ansi.RESET} "
                f"{ansi.player_name(char['name'])} spars with you. "
                f"You gain {ansi.BRIGHT_CYAN}+{SPAR_CP_REWARD} CP{ansi.RESET}."
            )
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {ansi.player_name(char['name'])} and "
            f"{ansi.player_name(partner['name'])} square off in a "
            f"training duel, blades flashing in measured arcs.",
            exclude=session,
            source_char=char,
        )


# ── Registration ─────────────────────────────────────────────────────────


def register_padawan_master_training_commands(registry):
    """Register +teach, +learn, +spar with the command registry."""
    for cmd in [TeachPowerCommand(), LearnCommand(), SparCommand()]:
        registry.register(cmd)
