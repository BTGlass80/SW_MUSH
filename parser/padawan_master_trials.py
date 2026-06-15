"""Padawan-Master Trials + Knight Promotion commands (P-M.3).

Per padawan_master_system_design_v1.md §6 (Trials), §6.4 (Knight
Promotion Ceremony), §10 (Commands Summary), and the May 20 2026
P-M.3 design calls:

  +trials [padawan]            Either: view Trial progress for the
                                bonded Padawan (Master) or self
                                (Padawan, no arg).
  +endorse trials <padawan>    Master: endorse Padawan's next Trial
                                attempt. Per §6.3, without Master
                                endorsement attempts auto-fail.
  +trial <name> [<padawan>]    Master: attest a Trial pass.
                                The Master records that their
                                Padawan has passed the named Trial.
                                Idempotent via db.record_trial_passed.
  @trial <name> = <padawan>    Staff: same record action with
                                cross-Master scope (Council mediation).
  +knight <padawan>            Master: invoke Knight promotion
                                ceremony. Hard-gates on all 5 Trials
                                recorded. Calls db.knight_bond +
                                grants +1 Force Point (per §6.4).
  @knight <padawan>            Staff: override gate; promote even
                                without the full 5 Trials (Council
                                fiat, e.g. battlefield knighting).

Design calls locked (P-M.3 session, May 20 2026):

  #1 Scope: All four command surfaces (+trials, +endorse trials,
     +trial / @trial, +knight / @knight) ship in this drop.

  #2 +trial authorization: BOTH staff @trial admin command + Master
     +trial (Master attests). Per §11 MVP, Trial adjudication is
     staff-run at launch; the Master command is the player-facing
     mechanism for narrating a passed Trial in-character. Staff
     can override or correct via @trial.

  #3 +knight Trials gate: SOFT gate. +knight requires all 5 Trials
     recorded (hard NO if any missing). Staff can override via
     @knight, which skips the gate (used for Council fiat
     promotions: e.g. mid-Clone-Wars battlefield knightings per
     canon precedent).

Tier eligibility (cross-cutting):

Tier is derived state, not a column on `characters`:
  - Padawan: an active bond exists where char.id == padawan_char_id.
  - Knight: a knighted bond exists where char.id == padawan_char_id
            (their old Master bond closed via knighting).
  - Master: tier-eligible to take a Padawan (P-M.2 +bond surface
            does not enforce this yet; tested-cohort use case at
            launch via @bond).

Per §6.4 #5, "New Knight is now eligible (but not automatically
authorized) to take a Padawan in the future." The post-Knight
+bond flow uses the existing P-M.2 surface; nothing in this
module changes Master eligibility logic.

Knight ceremony side-effects implemented here (per §6.4):
  - bond_status → knighted (via db.knight_bond)
  - knight_promotion_at timestamp (via db.knight_bond)
  - Force Points +1 (per §6.4 point 3)
  - pc_action_log cross-write on both sides (narrative-memory
    seam, mirrors P-M.2 §8.12 #2 pattern)

Knight ceremony NOT implemented here (deferred per §11 MVP):
  - Padawan braid item removal (content asset doesn't exist yet)
  - Force skills adjust per Knight norms (+1D-2D funded by stored
    CP) — needs a "Knight skills package" content decision
  - Director AI-narrated ceremony event (Director integration
    work, separate lane)
  - Auto-notify other online Jedi PCs (faction-broadcast work)

The deferred items are content/integration concerns layered on
the engine action this drop provides; they can ship incrementally
without re-touching the +knight command.
"""

from __future__ import annotations

import json
import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ── Five Trials canonical name set (per design §6.2) ──────────────────────
# Lowercase canonical names. Aliases (case-insensitive, hyphenless) map
# back to these via _canon_trial_name. Authoring chains.yaml or
# Director-AI narration can use either casing; storage and
# comparison use the lowercase canonical.
FIVE_TRIALS = (
    "skill",      # Trial of Skill — combat / Force-power demonstration
    "courage",    # Trial of Courage — solo mission in hostile zone
    "flesh",      # Trial of Flesh — endurance / injury survival
    "spirit",     # Trial of Spirit — dark-side temptation refusal
    "insight",    # Trial of Insight — perception / puzzle event
)
FIVE_TRIALS_SET = frozenset(FIVE_TRIALS)


# ── Master pre-authorization categories (P5 approval-weight, §5.3) ─────────
# A Master can pre-authorize a Padawan for a category of otherwise
# approval-gated action via +authorize, so routine activity doesn't need
# per-action sign-off. Resolved design fork PM.approval_pending_store =
# OPTION C (pre-authorization only at launch): this ships the STORE +
# display surface; the per-action +approve/+deny block-and-wait flow is
# deferred post-launch. The gated actions read these standing
# pre-authorizations when/where they are built (offworld travel, field
# Force-power use) — no cross-cutting action-interception layer at launch.
#
# The three categories map to the §5.3 approval-gated actions:
#   offworld — leaving Coruscant for a non-Council-sanctioned mission
#   powers   — using a Force power not authorized for field use
#   trials   — attempting a formal Trial (a STANDING endorsement, the
#              persistent complement to the one-shot +endorse)
#
# Storage mirrors +endorse: a JSON key (`master_authorizations`, a sorted
# list of canonical category strings) on the Padawan's chargen_notes. No
# schema change, per-Padawan, granted-by audit via `..._by_id`.
AUTHORIZE_CATEGORIES = {
    "offworld": "leave Coruscant for non-sanctioned missions",
    "powers": "use Force powers in the field",
    "trials": "attempt the Trials without a fresh +endorse",
}
# Convenience aliases → canonical category.
_AUTHORIZE_ALIASES = {
    "travel": "offworld", "mission": "offworld", "off-world": "offworld",
    "force": "powers", "power": "powers", "field": "powers",
    "trial": "trials",
}


def _normalize_category(raw: str) -> str | None:
    """Normalize a user-typed authorization category to canonical, or
    None if unrecognized. Case-insensitive; accepts a few aliases."""
    if not raw:
        return None
    n = raw.strip().lower()
    if n in AUTHORIZE_CATEGORIES:
        return n
    return _AUTHORIZE_ALIASES.get(n)


def _load_authorizations(char: dict) -> list:
    """Return the canonical categories the Padawan's Master has
    pre-authorized, decoded from chargen_notes. Defensive against
    malformed JSON / unknown categories. Returns a fresh list."""
    raw = char.get("chargen_notes") or "{}"
    try:
        notes = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(notes, dict):
        return []
    stored = notes.get("master_authorizations")
    if not isinstance(stored, list):
        return []
    out = []
    for c in stored:
        if (isinstance(c, str) and c in AUTHORIZE_CATEGORIES
                and c not in out):
            out.append(c)
    return out


def _has_oneshot_endorsement(char: dict) -> bool:
    """True if the Padawan currently holds a one-shot +endorse flag
    (consumed on the next recorded Trial)."""
    raw = char.get("chargen_notes") or "{}"
    try:
        notes = json.loads(raw)
    except (ValueError, TypeError):
        return False
    return bool(isinstance(notes, dict)
                and notes.get("trial_endorsement_active"))


def _canon_trial_name(raw: str) -> str | None:
    """Normalize a user-typed Trial name to its canonical form, or
    None if not recognized.

    Accepts: "skill", "Skill", "TRIAL_OF_SKILL", "trial of skill",
    "Trial-of-Skill". Trims whitespace and lowercases. Strips a
    leading "trial of " / "trial_of_" / "trial-of-" prefix. Returns
    one of FIVE_TRIALS or None.
    """
    if not raw:
        return None
    n = raw.strip().lower()
    # Strip "trial of " / "trial_of_" / "trial-of-" prefix.
    for prefix in ("trial of ", "trial_of_", "trial-of-"):
        if n.startswith(prefix):
            n = n[len(prefix):]
            break
    n = n.strip()
    if n in FIVE_TRIALS_SET:
        return n
    return None


# ── Force Point grant on knighting (per design §6.4 #3) ──────────────────
# "Force Points grant +1." Capped at a reasonable launch ceiling so a
# staff @knight loop doesn't compound. Cap is generous (well above
# any normal Padawan's FP count) and only applies in the +1 path.
KNIGHT_FP_GRANT = 1
KNIGHT_FP_CAP = 50


# ─── helpers ───────────────────────────────────────────────────────────────


async def _notify_char_if_online(
    ctx: CommandContext, target_char_id: int, line: str,
) -> bool:
    """Push a line to a character's session if online. Returns
    True on delivery, False on offline / failure. Mirrors the
    helper in parser/padawan_master_commands.py — duplicated
    here so the trials module has no circular import on the
    bond module."""
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


async def _log_event(
    ctx: CommandContext, char_id: int, action_type: str, summary: str,
    details: str = "{}",
) -> None:
    """Cross-write a P-M event to pc_action_log. Failure-tolerant —
    the underlying state change MUST NOT block on log failure."""
    try:
        await ctx.db.log_action(char_id, action_type, summary, details)
    except Exception:
        log.warning(
            "_log_event: log_action failed for char %s action %s",
            char_id, action_type, exc_info=True,
        )


def _passed_trials_from_bond(bond: dict) -> list:
    """Decode trials_passed_json into a list of canonical names.

    Defensive: malformed JSON / non-list / unknown names are
    silently dropped (the matching invariant is: only canonical
    Trial names can be in the list). Returns a fresh list.
    """
    raw = bond.get("trials_passed_json") or "[]"
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        decoded = []
    if not isinstance(decoded, list):
        return []
    out = []
    for x in decoded:
        if isinstance(x, str):
            canon = _canon_trial_name(x)
            if canon is not None and canon not in out:
                out.append(canon)
    return out


def _format_trials_display(passed: list) -> list:
    """Return rendered lines showing each Trial with passed/pending
    status. Used by +trials display."""
    lines = []
    for t in FIVE_TRIALS:
        if t in passed:
            mark = f"{ansi.GREEN}✓{ansi.RESET}"
            status = ansi.green("PASSED")
        else:
            mark = f"{ansi.YELLOW}·{ansi.RESET}"
            status = ansi.yellow("pending")
        title = "Trial of " + t.capitalize()
        lines.append(f"    {mark}  {title:<22} {status}")
    return lines


async def _find_pc_by_name_anywhere(ctx, name: str) -> dict | None:
    """Helper: find an active character by name globally (no room
    constraint). Used by +trial / +knight / +endorse where the
    Master may target an offline Padawan."""
    if not name:
        return None
    return await ctx.db.get_character_by_name(name.strip())


# ─── +trials ──────────────────────────────────────────────────────────────


class TrialsCommand(BaseCommand):
    """``+trials`` — view Trial progress.

    Subcommands / forms:
      +trials                  Padawan: show your own Trial progress.
                                Master with 1 bonded Padawan: show
                                that Padawan's progress (convenience).
      +trials <padawan>        Master: show the named Padawan's
                                progress. Padawan: refused (use
                                bare `+trials`).
    """
    key = "+trials"
    aliases = ["trials"]
    help_text = (
        "View Trial progress for a Padawan-Master bond.\n"
        "\n"
        "USAGE (Padawan):\n"
        "  +trials                   Show your own Trial progress.\n"
        "\n"
        "USAGE (Master):\n"
        "  +trials                   With 1 bonded Padawan, show "
        "their progress.\n"
        "  +trials <padawan name>    Show that Padawan's progress.\n"
        "\n"
        "Trials must be passed in order to be knighted. There are "
        "5 in total:\n"
        "  Skill, Courage, Flesh, Spirit, Insight (any order).\n"
    )
    usage = "+trials [<padawan>]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +trials.")
            return

        target_name = (ctx.args or "").strip()

        # Padawan path: bare +trials shows own bond.
        if not target_name:
            await self._show_self_or_single_bond(ctx, char)
            return

        # Master path: +trials <padawan>.
        await self._show_named_padawan(ctx, char, target_name)

    async def _show_self_or_single_bond(
        self, ctx: CommandContext, char: dict,
    ) -> None:
        # First: if char IS a Padawan (active bond as padawan), show
        # their own Trials.
        own_bond = await ctx.db.get_active_bond_for_padawan(char["id"])
        if own_bond is not None:
            await self._render_bond(ctx, own_bond, padawan_view=True)
            return

        # Otherwise: if char is a Master with exactly 1 active bond,
        # show that Padawan's Trials.
        master_bonds = await ctx.db.get_active_bonds_for_master(
            char["id"]
        )
        if not master_bonds:
            await ctx.session.send_line(
                "  You have no active bond. Padawans use +trials "
                "to see their own progress; Masters use "
                "+trials <padawan> to see a specific Padawan."
            )
            return
        if len(master_bonds) > 1:
            await ctx.session.send_line(
                f"  You have {len(master_bonds)} active Padawan "
                f"bonds. Specify which: +trials <padawan name>."
            )
            return
        await self._render_bond(ctx, master_bonds[0], padawan_view=False)

    async def _show_named_padawan(
        self, ctx: CommandContext, char: dict, target_name: str,
    ) -> None:
        target = await _find_pc_by_name_anywhere(ctx, target_name)
        if target is None:
            await ctx.session.send_line(
                f"  No active character named '{target_name}'.")
            return

        # Get the Padawan's active OR knighted bond. Knighted bonds
        # are still queryable — a former Padawan and their former
        # Master can both review the historical Trial record.
        bond = await ctx.db.get_active_bond_for_padawan(target["id"])
        if bond is None:
            # Look for a knighted bond (post-promotion historical view).
            bond = await self._find_recent_bond(ctx, target["id"])
            if bond is None:
                await ctx.session.send_line(
                    f"  {target['name']} has no Padawan-Master "
                    f"bond on record."
                )
                return

        # Authorization: the caller must be either the Padawan
        # themselves OR the Master on this bond. Staff (admins)
        # can view any.
        is_admin = bool(
            ctx.session.account
            and ctx.session.account.get("is_admin", 0)
        )
        is_padawan = (target["id"] == char["id"])
        is_master = (bond["master_char_id"] == char["id"])
        if not (is_admin or is_padawan or is_master):
            await ctx.session.send_line(
                "  You aren't part of that bond. Only the Padawan, "
                "their Master, or staff can view Trial progress."
            )
            return

        await self._render_bond(ctx, bond, padawan_view=is_padawan)

    async def _find_recent_bond(self, ctx, padawan_id: int) -> dict | None:
        """Find the most recent bond (any status) for a Padawan id.
        Used by the historical view path when the Padawan is no
        longer active-bonded but the caller wants the record."""
        try:
            rows = await ctx.db._db.execute_fetchall(
                """SELECT * FROM master_padawan_bond
                   WHERE padawan_char_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (padawan_id,),
            )
            return dict(rows[0]) if rows else None
        except Exception:
            return None

    async def _render_bond(
        self, ctx, bond: dict, *, padawan_view: bool,
    ) -> None:
        passed = _passed_trials_from_bond(bond)
        master = await ctx.db.get_character(bond["master_char_id"])
        padawan = await ctx.db.get_character(bond["padawan_char_id"])

        # Header
        if bond.get("bond_status") == "knighted":
            status_str = f" {ansi.green('[KNIGHTED]')}"
        elif bond.get("bond_status") == "fallen":
            status_str = f" {ansi.red('[FALLEN]')}"
        elif bond.get("bond_status") == "dissolved":
            status_str = f" {ansi.yellow('[DISSOLVED]')}"
        else:
            status_str = ""

        if padawan_view and padawan:
            await ctx.session.send_line(
                f"  {ansi.cyan('Your Trials')} "
                f"(Master: {ansi.bold(master['name'] if master else '?')})"
                f"{status_str}"
            )
        else:
            await ctx.session.send_line(
                f"  {ansi.cyan('Trials of')} "
                f"{ansi.bold(padawan['name'] if padawan else '?')}{status_str}"
            )

        for line in _format_trials_display(passed):
            await ctx.session.send_line(line)

        await ctx.session.send_line(
            f"  {ansi.cyan('Passed:')} "
            f"{ansi.bold(str(len(passed)))} of 5"
        )
        # Endorsement / pre-authorization status (P5 approval-weight,
        # §5.3/§6.3). A standing `trials` pre-authorization (+authorize)
        # is the persistent complement to the one-shot +endorse; this
        # line is the player-facing consumer of both.
        if bond.get("bond_status") == "active" and padawan:
            if "trials" in _load_authorizations(padawan):
                await ctx.session.send_line(
                    f"  {ansi.cyan('Endorsement:')} "
                    f"{ansi.green('standing')} — Master has pre-authorized "
                    f"Trial attempts ({ansi.yellow('+authorize')})."
                )
            elif _has_oneshot_endorsement(padawan):
                await ctx.session.send_line(
                    f"  {ansi.cyan('Endorsement:')} "
                    f"{ansi.green('ready')} — Master endorsed your next "
                    f"attempt."
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.cyan('Endorsement:')} "
                    f"{ansi.yellow('none')} — Master must "
                    f"{ansi.yellow('+endorse')} (or "
                    f"{ansi.yellow('+authorize')}) before a Trial attempt."
                )
        if len(passed) == 5 and bond.get("bond_status") == "active":
            await ctx.session.send_line(
                f"  {ansi.green('Eligible for knighting.')} "
                f"Master: invoke "
                f"{ansi.yellow('+knight ' + (padawan['name'] if padawan else '<padawan>'))}."
            )


# ─── +endorse trials ──────────────────────────────────────────────────────


class EndorseCommand(BaseCommand):
    """``+endorse trials <padawan>`` — Master endorses Padawan's
    next Trial attempt.

    Per design §6.3, without Master endorsement, Trial attempts
    auto-fail. This is the Master's approval-weight surfacing
    concretely. The endorsement is recorded in chargen_notes
    JSON on the Padawan's character (key:
    `trial_endorsement_active`). The Padawan-side mechanical
    consumption (where Trial attempts read this and gate)
    is content / future-drop concern; this command ships the
    write surface.

    Endorsement is consumed (cleared) on the next +trial /
    @trial that records a Trial pass for this Padawan. The
    Master can re-endorse for the next attempt.
    """
    key = "+endorse"
    aliases = []
    help_text = (
        "Endorse a Padawan's Trial attempt (Master).\n"
        "\n"
        "USAGE:\n"
        "  +endorse trials <padawan>   Endorse your Padawan's "
        "next Trial attempt.\n"
        "\n"
        "Without endorsement, Trial attempts auto-fail (per design "
        "§6.3). Endorsement\nis consumed on the next +trial record.\n"
    )
    usage = "+endorse trials <padawan>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +endorse.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return
        parts = args.split(None, 1)
        if len(parts) < 2 or parts[0].lower() != "trials":
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return
        padawan_name = parts[1].strip()
        if not padawan_name:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return

        padawan = await _find_pc_by_name_anywhere(ctx, padawan_name)
        if padawan is None:
            await ctx.session.send_line(
                f"  No active character named '{padawan_name}'.")
            return

        bond = await ctx.db.get_active_bond_for_padawan(padawan["id"])
        if bond is None:
            await ctx.session.send_line(
                f"  {padawan['name']} has no active Padawan-Master "
                f"bond. Endorsement requires an active bond."
            )
            return
        if bond["master_char_id"] != char["id"]:
            await ctx.session.send_line(
                f"  You are not {padawan['name']}'s Master."
            )
            return

        # Write the endorsement flag into the Padawan's chargen_notes.
        notes_raw = padawan.get("chargen_notes") or "{}"
        try:
            notes = json.loads(notes_raw)
            if not isinstance(notes, dict):
                notes = {}
        except (ValueError, TypeError):
            notes = {}
        notes["trial_endorsement_active"] = True
        notes["trial_endorsement_by_master_id"] = char["id"]
        serialized = json.dumps(notes)
        await ctx.db.save_character(
            padawan["id"], chargen_notes=serialized,
        )

        # Notify both sides.
        await ctx.session.send_line(
            f"  {ansi.cyan('You endorse')} "
            f"{ansi.bold(padawan['name'])} "
            f"{ansi.cyan('for their next Trial attempt.')}"
        )
        await _notify_char_if_online(
            ctx, padawan["id"],
            f"\n  {ansi.bold(char['name'])} "
            f"{ansi.cyan('has endorsed your next Trial attempt.')}\n"
            f"  Without endorsement, Trial attempts auto-fail. "
            f"You may now attempt a Trial.\n"
        )
        await _log_event(
            ctx, padawan["id"], "trial_endorsement",
            f"Endorsed for Trial attempt by Master {char['name']}.",
        )


# ─── +authorize — Master pre-authorization (P5 approval-weight, OPT C) ─────


class AuthorizeCommand(BaseCommand):
    """``+authorize <padawan> <category> [off]`` — Master pre-authorizes
    a Padawan for a category of otherwise approval-gated action.

    Per design §5.3, several Padawan actions are gated by Master
    approval. Rather than a per-action block-and-wait flow (deferred
    post-launch — resolved fork PM.approval_pending_store = OPTION C),
    launch ships the standing pre-authorization surface: a Master grants
    a category once and routine activity in that category no longer needs
    per-action sign-off.

    Categories (design §5.3): offworld, powers, trials.

    Forms::

      +authorize <padawan> <category>       Grant a category.
      +authorize <padawan> <category> off   Revoke a category.
      +authorize <category> [off]           Sole-bond Master shorthand.
      +authorize <padawan>                  List a Padawan's grants.
      +authorize                            Context list (your sole
                                            Padawan's grants, or — as a
                                            Padawan — what your Master
                                            has pre-authorized for you).

    The grants are stored on the Padawan's chargen_notes
    (`master_authorizations`), mirroring +endorse. The `trials` category
    is a standing endorsement: it surfaces in +trials as
    "Endorsement: standing", complementing the one-shot +endorse.
    """
    key = "+authorize"
    aliases = ["authorise"]
    help_text = (
        "Pre-authorize a Padawan for approval-gated actions (Master).\n"
        "\n"
        "USAGE:\n"
        "  +authorize <padawan> <category>       Grant a category.\n"
        "  +authorize <padawan> <category> off   Revoke a category.\n"
        "  +authorize <category> [off]           If you have 1 Padawan.\n"
        "  +authorize <padawan>                  List a Padawan's grants.\n"
        "  +authorize                            Show standing grants.\n"
        "\n"
        "CATEGORIES:\n"
        "  offworld   Leave Coruscant for non-sanctioned missions.\n"
        "  powers     Use Force powers in the field.\n"
        "  trials     Attempt the Trials without a fresh +endorse.\n"
        "\n"
        "Pre-authorization avoids needing per-action approval for "
        "routine activity\n(design §5.3). Padawans: use bare +authorize "
        "to see what you're cleared for.\n"
    )
    usage = "+authorize <padawan> <category> [off]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +authorize.")
            return

        parts = (ctx.args or "").split()

        # Strip a trailing on/off toggle word, if present.
        toggle = None
        if parts and parts[-1].lower() in (
            "on", "off", "grant", "revoke", "remove", "clear",
        ):
            toggle = ("off" if parts[-1].lower() in
                      ("off", "revoke", "remove", "clear") else "on")
            parts = parts[:-1]

        # 0 tokens → context list.
        if not parts:
            if toggle is not None:
                await ctx.session.send_line(f"  Usage: {self.usage}")
                return
            await self._list_context(ctx, char)
            return

        # 1 token → category (sole-bond grant) or padawan name (list).
        if len(parts) == 1:
            cat = _normalize_category(parts[0])
            if cat is not None:
                await self._grant_sole_bond(
                    ctx, char, cat, toggle or "on")
                return
            if toggle is not None:
                await ctx.session.send_line(
                    "  Specify a category: "
                    "+authorize <padawan> <category> [off]")
                return
            await self._list_for_padawan_name(ctx, char, parts[0])
            return

        # 2+ tokens → <padawan> <category>.
        padawan_name = parts[0]
        cat = _normalize_category(parts[1])
        if cat is None:
            await ctx.session.send_line(
                f"  '{parts[1]}' isn't an authorization category.\n"
                f"  Valid: {', '.join(sorted(AUTHORIZE_CATEGORIES))}"
            )
            return
        await self._grant_named(
            ctx, char, padawan_name, cat, toggle or "on")

    # ── grant / revoke ────────────────────────────────────────────────

    async def _grant_sole_bond(self, ctx, master, cat, toggle):
        bonds = await ctx.db.get_active_bonds_for_master(master["id"])
        if not bonds:
            await ctx.session.send_line(
                "  You have no active Padawan bond. "
                "Use +authorize <padawan> <category>."
            )
            return
        if len(bonds) > 1:
            await ctx.session.send_line(
                f"  You have {len(bonds)} active Padawan bonds. "
                f"Specify which: +authorize <padawan> {cat}."
            )
            return
        padawan = await ctx.db.get_character(bonds[0]["padawan_char_id"])
        if padawan is None:
            await ctx.session.send_line(
                "  Bond character record is missing. Notify staff.")
            return
        await self._apply_authorization(ctx, master, padawan, cat, toggle)

    async def _grant_named(self, ctx, master, padawan_name, cat, toggle):
        padawan = await _find_pc_by_name_anywhere(ctx, padawan_name)
        if padawan is None:
            await ctx.session.send_line(
                f"  No active character named '{padawan_name}'.")
            return
        bond = await ctx.db.get_active_bond_for_padawan(padawan["id"])
        if bond is None:
            await ctx.session.send_line(
                f"  {padawan['name']} has no active Padawan-Master "
                f"bond. Pre-authorization requires an active bond."
            )
            return
        is_admin = bool(
            ctx.session.account
            and ctx.session.account.get("is_admin", 0)
        )
        if bond["master_char_id"] != master["id"] and not is_admin:
            await ctx.session.send_line(
                f"  You are not {padawan['name']}'s Master.")
            return
        await self._apply_authorization(ctx, master, padawan, cat, toggle)

    async def _apply_authorization(self, ctx, master, padawan, cat, toggle):
        notes_raw = padawan.get("chargen_notes") or "{}"
        try:
            notes = json.loads(notes_raw)
            if not isinstance(notes, dict):
                notes = {}
        except (ValueError, TypeError):
            notes = {}
        current = notes.get("master_authorizations")
        if not isinstance(current, list):
            current = []
        current = [c for c in current
                   if isinstance(c, str) and c in AUTHORIZE_CATEGORIES]

        if toggle == "off":
            if cat not in current:
                await ctx.session.send_line(
                    f"  {padawan['name']} is not pre-authorized for "
                    f"'{cat}'. Nothing to revoke."
                )
                return
            current = [c for c in current if c != cat]
            past = "revoked"
        else:
            if cat in current:
                await ctx.session.send_line(
                    f"  {padawan['name']} is already pre-authorized "
                    f"for '{cat}'."
                )
                return
            current.append(cat)
            past = "granted"

        notes["master_authorizations"] = sorted(set(current))
        notes["master_authorizations_by_id"] = master["id"]
        await ctx.db.save_character(
            padawan["id"], chargen_notes=json.dumps(notes),
        )

        desc = AUTHORIZE_CATEGORIES[cat]
        if past == "granted":
            head = ansi.green("Pre-authorization granted:")
            body = f"{ansi.bold(padawan['name'])} may {ansi.cyan(desc)}"
        else:
            head = ansi.yellow("Pre-authorization revoked:")
            body = (f"{ansi.bold(padawan['name'])} no longer cleared to "
                    f"{ansi.cyan(desc)}")
        await ctx.session.send_line(
            f"  {head} {body} ({ansi.bold(cat)}).")
        notify_verb = past
        await _notify_char_if_online(
            ctx, padawan["id"],
            f"\n  {ansi.bold(master['name'])} has {notify_verb} your "
            f"pre-authorization to {ansi.cyan(desc)} "
            f"({ansi.bold(cat)}).\n"
        )
        await _log_event(
            ctx, padawan["id"], "pm_authorization",
            f"Master {master['name']} {past} pre-authorization "
            f"'{cat}'.",
        )
        await _log_event(
            ctx, master["id"], "pm_authorization",
            f"{past.capitalize()} '{cat}' pre-authorization for "
            f"Padawan {padawan['name']}.",
        )

    # ── list / display (consumers) ────────────────────────────────────

    async def _list_context(self, ctx, char):
        # Padawan path: bare +authorize shows what your Master cleared.
        own_bond = await ctx.db.get_active_bond_for_padawan(char["id"])
        if own_bond is not None:
            await self._render_authorizations(
                ctx, char, padawan_view=True)
            return
        # Master path: sole bond convenience.
        bonds = await ctx.db.get_active_bonds_for_master(char["id"])
        if not bonds:
            await ctx.session.send_line(
                "  You have no active bond. Masters: "
                "+authorize <padawan> <category>. Padawans: bare "
                "+authorize shows what you're cleared for."
            )
            return
        if len(bonds) > 1:
            await ctx.session.send_line(
                f"  You have {len(bonds)} active Padawan bonds. "
                f"Specify which: +authorize <padawan>."
            )
            return
        padawan = await ctx.db.get_character(bonds[0]["padawan_char_id"])
        if padawan is None:
            await ctx.session.send_line(
                "  Bond character record is missing. Notify staff.")
            return
        await self._render_authorizations(ctx, padawan, padawan_view=False)

    async def _list_for_padawan_name(self, ctx, char, padawan_name):
        padawan = await _find_pc_by_name_anywhere(ctx, padawan_name)
        if padawan is None:
            await ctx.session.send_line(
                f"  No active character named '{padawan_name}'.")
            return
        bond = await ctx.db.get_active_bond_for_padawan(padawan["id"])
        if bond is None:
            await ctx.session.send_line(
                f"  {padawan['name']} has no active Padawan-Master bond.")
            return
        is_admin = bool(
            ctx.session.account
            and ctx.session.account.get("is_admin", 0)
        )
        is_padawan = (padawan["id"] == char["id"])
        is_master = (bond["master_char_id"] == char["id"])
        if not (is_admin or is_padawan or is_master):
            await ctx.session.send_line(
                "  You aren't part of that bond. Only the Padawan, "
                "their Master, or staff can view pre-authorizations."
            )
            return
        await self._render_authorizations(
            ctx, padawan, padawan_view=is_padawan)

    async def _render_authorizations(self, ctx, padawan, *, padawan_view):
        granted = _load_authorizations(padawan)
        if padawan_view:
            await ctx.session.send_line(
                f"  {ansi.cyan('Your Master has pre-authorized:')}")
        else:
            await ctx.session.send_line(
                f"  {ansi.cyan('Pre-authorizations for')} "
                f"{ansi.bold(padawan['name'])}{ansi.cyan(':')}")
        for cat in sorted(AUTHORIZE_CATEGORIES):
            desc = AUTHORIZE_CATEGORIES[cat]
            if cat in granted:
                mark = f"{ansi.GREEN}✓{ansi.RESET}"
                state = ansi.green("CLEARED")
            else:
                mark = f"{ansi.YELLOW}·{ansi.RESET}"
                state = ansi.yellow("needs approval")
            await ctx.session.send_line(
                f"    {mark}  {cat:<10} {state}  "
                f"{ansi.cyan('(' + desc + ')')}")


# ─── +trial / @trial — record a Trial pass ────────────────────────────────


class TrialCommand(BaseCommand):
    """``+trial <name> [<padawan>]`` — Master attests a Trial pass.

    Per the May 20 2026 P-M.3 design call (#2): BOTH Master
    `+trial` and staff `@trial`. Per §11 MVP Trial adjudication is
    staff-run at launch; the Master command is the player-facing
    mechanism for the Master attesting in-character that their
    Padawan has passed the named Trial. Staff can override or
    correct via @trial.

    The 5 canonical Trial names (case-insensitive, "Trial of "
    prefix accepted):
      skill, courage, flesh, spirit, insight

    Idempotent: recording an already-passed Trial is a no-op
    (the underlying db.record_trial_passed returns False without
    modifying). The command surfaces the no-op cleanly so the
    Master sees "already recorded" rather than a confusing
    silent success.
    """
    key = "+trial"
    aliases = []
    help_text = (
        "Record that your Padawan has passed a Trial.\n"
        "\n"
        "USAGE:\n"
        "  +trial <name>                With 1 bonded Padawan, "
        "record the named Trial.\n"
        "  +trial <name> <padawan>      Record the named Trial "
        "for a specific Padawan.\n"
        "\n"
        "TRIALS: skill, courage, flesh, spirit, insight (any "
        "order; case-insensitive).\n"
        "Both bare names and 'Trial of X' forms are accepted.\n"
        "\n"
        "Staff use @trial <name> = <padawan> instead — see help "
        "@trial.\n"
    )
    usage = "+trial <name> [<padawan>]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +trial.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(f"  Usage: {self.usage}")
            return

        parts = args.split(None, 1)
        trial_raw = parts[0]
        padawan_name = parts[1].strip() if len(parts) > 1 else ""

        # Normalize "Trial of X" — if the first token is "Trial" or
        # "trial_of_X" etc., re-parse.
        if trial_raw.lower() in ("trial",) and padawan_name:
            # Form: "+trial Trial of Skill <padawan>"
            sub_parts = padawan_name.split(None, 2)
            if len(sub_parts) >= 2 and sub_parts[0].lower() == "of":
                trial_raw = "trial of " + sub_parts[1]
                padawan_name = sub_parts[2].strip() if len(sub_parts) > 2 else ""

        canon = _canon_trial_name(trial_raw)
        if canon is None:
            await ctx.session.send_line(
                f"  '{trial_raw}' isn't one of the five Trials.\n"
                f"  Valid: {', '.join(FIVE_TRIALS)}"
            )
            return

        # Resolve target Padawan. Bare +trial <name>: use the
        # Master's single active bond.
        target_bond = None
        if not padawan_name:
            bonds = await ctx.db.get_active_bonds_for_master(char["id"])
            if not bonds:
                await ctx.session.send_line(
                    "  You have no active Padawan bond. Trials can "
                    "only be recorded against an active bond."
                )
                return
            if len(bonds) > 1:
                await ctx.session.send_line(
                    f"  You have {len(bonds)} active Padawan bonds. "
                    f"Specify which: +trial {canon} <padawan name>."
                )
                return
            target_bond = bonds[0]
        else:
            padawan = await _find_pc_by_name_anywhere(ctx, padawan_name)
            if padawan is None:
                await ctx.session.send_line(
                    f"  No active character named '{padawan_name}'.")
                return
            bond = await ctx.db.get_active_bond_for_padawan(padawan["id"])
            if bond is None:
                await ctx.session.send_line(
                    f"  {padawan['name']} has no active "
                    f"Padawan-Master bond."
                )
                return
            if bond["master_char_id"] != char["id"]:
                await ctx.session.send_line(
                    f"  You are not {padawan['name']}'s Master."
                )
                return
            target_bond = bond

        await _record_trial_and_render(
            ctx, char, target_bond, canon, via_admin=False,
        )


class AdminTrialCommand(BaseCommand):
    """``@trial <name> = <padawan>`` — staff direct Trial record.

    Skips the Master-attestation step. Used for staff-adjudicated
    Trials and post-fact corrections per §11 MVP.
    """
    key = "@trial"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin: directly record a Trial pass for a Padawan.\n"
        "\n"
        "USAGE:\n"
        "  @trial <name> = <padawan>\n"
        "\n"
        "Bypasses the Master-attestation step. Used for "
        "staff-adjudicated Trials and\npost-fact corrections. "
        "Idempotent: re-recording is a no-op.\n"
    )
    usage = "@trial <name> = <padawan>"

    async def execute(self, ctx: CommandContext):
        args = (ctx.args or "").strip()
        if "=" not in args:
            await ctx.session.send_line(
                f"  Usage: {self.usage}")
            return
        name_part, _, padawan_part = args.partition("=")
        trial_raw = name_part.strip()
        padawan_name = padawan_part.strip()
        if not trial_raw or not padawan_name:
            await ctx.session.send_line(
                "  Both Trial name and Padawan name are required.")
            return

        canon = _canon_trial_name(trial_raw)
        if canon is None:
            await ctx.session.send_line(
                f"  '{trial_raw}' isn't one of the five Trials.\n"
                f"  Valid: {', '.join(FIVE_TRIALS)}"
            )
            return

        padawan = await _find_pc_by_name_anywhere(ctx, padawan_name)
        if padawan is None:
            await ctx.session.send_line(
                f"  No active character named '{padawan_name}'.")
            return
        bond = await ctx.db.get_active_bond_for_padawan(padawan["id"])
        if bond is None:
            await ctx.session.send_line(
                f"  {padawan['name']} has no active "
                f"Padawan-Master bond."
            )
            return

        await _record_trial_and_render(
            ctx, ctx.session.character, bond, canon, via_admin=True,
        )


async def _record_trial_and_render(
    ctx: CommandContext, actor: dict, bond: dict,
    trial_canon: str, *, via_admin: bool,
) -> None:
    """Shared core for +trial and @trial.

    `actor` is the session character (Master or staff). `bond` is
    the target active bond. `trial_canon` is the canonical
    lowercase trial name. `via_admin` toggles narrative phrasing.
    """
    bond_id = bond["id"]
    padawan = await ctx.db.get_character(bond["padawan_char_id"])
    master = await ctx.db.get_character(bond["master_char_id"])

    if padawan is None or master is None:
        await ctx.session.send_line(
            "  Bond character records are incomplete. "
            "Please notify staff."
        )
        return

    # Record the pass.
    try:
        newly_recorded = await ctx.db.record_trial_passed(
            bond_id, trial_canon,
        )
    except Exception:
        log.warning(
            "record_trial_passed raised for bond=%s trial=%s",
            bond_id, trial_canon, exc_info=True,
        )
        await ctx.session.send_line(
            "  The Trial could not be recorded. "
            "Please notify staff."
        )
        return

    title = "Trial of " + trial_canon.capitalize()

    if not newly_recorded:
        await ctx.session.send_line(
            f"  {ansi.yellow('Already recorded:')} "
            f"{padawan['name']} has previously passed the "
            f"{title}."
        )
        return

    # Consume the endorsement flag if active. The Master gets
    # one endorsement per Trial attempt per design §6.3 — and
    # since adjudication is staff-run at launch, the meaningful
    # semantic is "the Master endorsed; the Padawan made the
    # attempt; staff/Master attested the pass; endorsement
    # is now consumed for the next Trial."
    try:
        p_notes_raw = padawan.get("chargen_notes") or "{}"
        p_notes = json.loads(p_notes_raw)
        if isinstance(p_notes, dict) and p_notes.get(
            "trial_endorsement_active"
        ):
            p_notes.pop("trial_endorsement_active", None)
            p_notes.pop("trial_endorsement_by_master_id", None)
            await ctx.db.save_character(
                padawan["id"], chargen_notes=json.dumps(p_notes),
            )
    except (ValueError, TypeError):
        # Malformed notes — non-fatal.
        pass

    # Re-fetch the bond for the updated passed-count.
    reloaded = await ctx.db.get_bond(bond_id)
    passed_count = len(_passed_trials_from_bond(reloaded or bond))

    actor_kind = (
        "Staff" if via_admin else "Master " + (master["name"])
    )
    await ctx.session.send_line(
        f"  {ansi.green('Recorded:')} {padawan['name']} has "
        f"passed the {ansi.bold(title)}. "
        f"({passed_count}/5 Trials passed)"
    )

    # Notify the Padawan if online.
    await _notify_char_if_online(
        ctx, padawan["id"],
        f"\n  {ansi.cyan(actor_kind + ' has recorded your passage of the')} "
        f"{ansi.bold(title)}{ansi.cyan('.')}\n"
        f"  {ansi.cyan('You have passed')} "
        f"{ansi.bold(str(passed_count))}{ansi.cyan(' of 5 Trials.')}\n"
    )

    # Also notify the Master if @trial was used (i.e. staff recorded
    # while Master wasn't the actor).
    if via_admin and master["id"] != actor.get("id"):
        await _notify_char_if_online(
            ctx, master["id"],
            f"\n  {ansi.cyan('Staff has recorded your Padawan ')} "
            f"{ansi.bold(padawan['name'])}"
            f"{ansi.cyan(' passing the ')}"
            f"{ansi.bold(title)}{ansi.cyan('.')}\n"
        )

    # Log on both sides.
    summary_master = (
        f"Recorded {padawan['name']} passing {title} "
        f"({passed_count}/5){' [staff]' if via_admin else ''}."
    )
    summary_padawan = (
        f"Passed {title} ({passed_count}/5)"
    )
    if via_admin:
        summary_padawan += " (recorded by staff)."
    else:
        summary_padawan += f" (recorded by Master {master['name']})."

    await _log_event(
        ctx, master["id"], "trial_recorded", summary_master,
    )
    await _log_event(
        ctx, padawan["id"], "trial_recorded", summary_padawan,
    )

    # If all 5 are passed, surface the next step.
    if passed_count == 5:
        await ctx.session.send_line(
            f"  {ansi.green('All five Trials passed.')} "
            f"{padawan['name']} is now eligible for knighting."
        )
        if not via_admin:
            await ctx.session.send_line(
                f"  Master: when ready, invoke "
                f"{ansi.yellow('+knight ' + padawan['name'])}."
            )
        await _notify_char_if_online(
            ctx, padawan["id"],
            f"\n  {ansi.green('You have passed all five Trials.')}\n"
            f"  Await your Master's invocation of +knight.\n"
        )


# ─── +knight / @knight — Knight promotion ceremony ────────────────────────


class KnightCommand(BaseCommand):
    """``+knight <padawan>`` — Master invokes Knight promotion.

    Per design §6.4. Soft-gate (P-M.3 design call #3): all five
    Trials must be recorded. Staff can override via @knight (e.g.
    Council fiat / battlefield knighting per Clone Wars canon).

    Side-effects on success:
      - bond.bond_status → 'knighted' via db.knight_bond
      - bond.knight_promotion_at timestamp via db.knight_bond
      - Padawan: Force Points +1 (per §6.4 #3)
      - pc_action_log cross-write on both characters
      - Notify Padawan if online with the ceremonial line

    NOT done in this drop (deferred per design §11 MVP):
      - Braid item removal (no asset)
      - Force skills adjust (+1D-2D funded by CP) — needs Knight
        skills package content
      - Director AI-narrated ceremony event
      - Auto-notify other online Jedi PCs (faction broadcast)
    """
    key = "+knight"
    aliases = []
    help_text = (
        "Invoke the Knight promotion ceremony for your Padawan.\n"
        "\n"
        "USAGE:\n"
        "  +knight <padawan>      Promote your Padawan to Knight.\n"
        "\n"
        "REQUIREMENTS:\n"
        "  * You must be the Padawan's Master (active bond).\n"
        "  * All five Trials must be recorded as passed (see "
        "+trials).\n"
        "\n"
        "EFFECTS:\n"
        "  * Bond status flips to 'knighted'.\n"
        "  * Padawan gains +1 Force Point.\n"
        "  * Both parties get a narrative-memory entry.\n"
        "\n"
        "Staff can use @knight to override the Trials gate (e.g. "
        "Council fiat).\n"
    )
    usage = "+knight <padawan>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +knight.")
            return
        await _knight_handler(
            ctx, char, ctx.args or "", via_admin=False,
        )


class AdminKnightCommand(BaseCommand):
    """``@knight <padawan>`` — staff promotion override.

    Bypasses the all-5-Trials gate. Used for Council-fiat
    promotions (battlefield knighting per CW canon; emergency
    field elevations).
    """
    key = "@knight"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin: promote a Padawan to Knight, bypassing the "
        "Trials gate.\n"
        "\n"
        "USAGE:\n"
        "  @knight <padawan>\n"
        "\n"
        "Used for staff-mediated promotions where the canonical "
        "all-5-Trials gate\nshould not apply (Council fiat, "
        "battlefield knighting).\n"
    )
    usage = "@knight <padawan>"

    async def execute(self, ctx: CommandContext):
        await _knight_handler(
            ctx, ctx.session.character, ctx.args or "", via_admin=True,
        )


async def _knight_handler(
    ctx: CommandContext, actor: dict, args: str, *, via_admin: bool,
) -> None:
    """Shared core for +knight and @knight."""
    padawan_name = args.strip()
    if not padawan_name:
        await ctx.session.send_line(
            f"  Usage: {('@knight' if via_admin else '+knight')} "
            f"<padawan name>"
        )
        return

    padawan = await _find_pc_by_name_anywhere(ctx, padawan_name)
    if padawan is None:
        await ctx.session.send_line(
            f"  No active character named '{padawan_name}'.")
        return

    bond = await ctx.db.get_active_bond_for_padawan(padawan["id"])
    if bond is None:
        await ctx.session.send_line(
            f"  {padawan['name']} has no active "
            f"Padawan-Master bond. Knight promotion requires an "
            f"active bond."
        )
        return

    # Master-authorization check (not enforced for staff).
    if not via_admin:
        if bond["master_char_id"] != actor["id"]:
            await ctx.session.send_line(
                f"  You are not {padawan['name']}'s Master."
            )
            return

    # Trials gate. Soft for staff (override), hard for Masters.
    passed = _passed_trials_from_bond(bond)
    if not via_admin and len(passed) < 5:
        missing = [t for t in FIVE_TRIALS if t not in passed]
        await ctx.session.send_line(
            f"  {padawan['name']} has not passed all five Trials "
            f"({len(passed)}/5)."
        )
        await ctx.session.send_line(
            f"  Pending: {', '.join('Trial of ' + t.capitalize() for t in missing)}."
        )
        await ctx.session.send_line(
            f"  Use {ansi.yellow('+trial <name> ' + padawan['name'])}"
            f" to record passes."
        )
        return

    # Promote.
    try:
        ok = await ctx.db.knight_bond(bond["id"], trials_passed=None)
    except Exception:
        log.warning(
            "knight_bond raised for bond=%s", bond["id"], exc_info=True,
        )
        await ctx.session.send_line(
            "  The promotion could not be recorded. Please notify "
            "staff."
        )
        return
    if not ok:
        await ctx.session.send_line(
            "  The bond is no longer active and cannot be promoted. "
            "Please notify staff."
        )
        return

    # Force Points +1 (per §6.4 #3), capped.
    # WoW.3c (May 24 2026): apply the Weight-of-War FP-award
    # reduction per design §7.2. For the standard KNIGHT_FP_GRANT
    # of +1, the substrate's minimum-1 floor means the reduction
    # is a no-op at every Weight tier — a Knight at Weight 200
    # still gets +1. But pinning the call here makes the grant
    # site Weight-aware so a future multi-FP variant (e.g. a
    # "+3 for a particularly meritorious knighting") would scale
    # correctly without rediscovery.
    try:
        current_fp = int(padawan.get("force_points") or 1)
        from engine.weight_of_war import (
            fp_award_after_weight, get_weight, is_jedi_pc,
        )
        # The padawan is, by construction at this point in the
        # ceremony, a Jedi — the bond schema gates it. But the
        # is_jedi_pc check stays here as defense in depth and as
        # a no-op for any future non-bond grant path.
        if is_jedi_pc(padawan):
            adjusted_grant = fp_award_after_weight(
                KNIGHT_FP_GRANT, get_weight(padawan),
            )
        else:
            adjusted_grant = KNIGHT_FP_GRANT
        new_fp = min(current_fp + adjusted_grant, KNIGHT_FP_CAP)
        await ctx.db.save_character(padawan["id"], force_points=new_fp)
    except Exception:
        log.warning(
            "Force Point grant failed for char=%s",
            padawan["id"], exc_info=True,
        )

    master = await ctx.db.get_character(bond["master_char_id"])
    master_name = master["name"] if master else "their Master"

    # Caller render.
    if via_admin:
        await ctx.session.send_line(
            f"  {ansi.green('@knight:')} "
            f"{ansi.bold(padawan['name'])} "
            f"{ansi.cyan('is now a Knight.')} "
            f"(staff override; Trials gate bypassed)"
        )
    else:
        await ctx.session.send_line(
            f"  {ansi.cyan('You complete the Knight promotion ceremony for')} "
            f"{ansi.bold(padawan['name'])}{ansi.cyan('.')}"
        )
        await ctx.session.send_line(
            f"  {ansi.green('Rise, Knight ' + padawan['name'] + '.')}"
        )

    # Padawan notification.
    if via_admin:
        ceremony_line = (
            f"\n  {ansi.cyan('Staff has elevated you to Knight.')}\n"
            f"  {ansi.green('Rise, Knight ' + padawan['name'] + '.')}\n"
        )
    else:
        ceremony_line = (
            f"\n  {ansi.bold(master_name)} "
            f"{ansi.cyan('completes the Knight promotion ceremony.')}\n"
            f"  {ansi.green('Rise, Knight ' + padawan['name'] + '.')}\n"
            f"  {ansi.dim('(You gain +1 Force Point.)')}\n"
        )
    await _notify_char_if_online(ctx, padawan["id"], ceremony_line)

    # Notify the Master if @knight was used.
    if via_admin and master and master["id"] != actor.get("id"):
        await _notify_char_if_online(
            ctx, master["id"],
            f"\n  {ansi.cyan('Staff has elevated your Padawan ')} "
            f"{ansi.bold(padawan['name'])} "
            f"{ansi.cyan('to Knight.')}\n"
        )

    # Cross-write narrative log.
    master_summary = (
        f"Knighted Padawan {padawan['name']} "
        f"(bond #{bond['id']}"
        + (", staff override" if via_admin else "")
        + ")."
    )
    padawan_summary = (
        f"Promoted to Knight by "
        + ("staff" if via_admin else f"Master {master_name}")
        + f" (bond #{bond['id']})."
    )
    if master:
        await _log_event(
            ctx, master["id"], "knight_promotion", master_summary,
        )
    await _log_event(
        ctx, padawan["id"], "knight_promotion", padawan_summary,
    )


# ─── registration ─────────────────────────────────────────────────────────


def register_padawan_master_trials(registry) -> None:
    """Register P-M.3 commands with the given CommandRegistry."""
    for cmd in (
        TrialsCommand(),
        EndorseCommand(),
        AuthorizeCommand(),
        TrialCommand(),
        AdminTrialCommand(),
        KnightCommand(),
        AdminKnightCommand(),
    ):
        registry.register(cmd)
