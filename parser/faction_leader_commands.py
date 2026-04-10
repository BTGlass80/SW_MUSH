# -*- coding: utf-8 -*-
"""
parser/faction_leader_commands.py — Faction leader commands for SW_MUSH.

These commands extend FactionCommand with sub-commands available to rank 5+
members and the designated faction leader. Registered as aliases on the
FactionCommand key so they dispatch via 'faction <sub-command>'.

Commands (rank 5+ only, or admin):
  faction promote <member>            -- promote one rank
  faction demote <member>             -- demote one rank
  faction warn <member> <reason>      -- issue a formal warning (logged)
  faction probation <member> [reason] -- place on probation
  faction pardon <member>             -- lift probation
  faction expel <member> [reason]     -- expel a member (gear reclaimed)
  faction announce <message>          -- broadcast on faction channel
  faction treasury                    -- view treasury balance
  faction motd <message>              -- set message of the day (stored in props)
  faction log [n]                     -- view recent faction activity log
  faction mission create <type> <reward> <desc>  -- post a faction mission

Admin only:
  @faction leader <code> <player>     -- hand off leadership to a PC
"""
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel

log = logging.getLogger(__name__)

_MIN_LEADER_RANK = 5  # Minimum rank to use leader commands


async def _require_leader(ctx: CommandContext, org=None) -> tuple[bool, dict, dict]:
    """
    Verify the invoking character is rank 5+ in their faction (or admin).
    Returns (ok, char, membership_dict). Sends error and returns (False, ...)
    on failure.
    """
    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    if faction_id == "independent":
        await ctx.session.send_line(
            "  You must be a faction member to use leader commands."
        )
        return False, char, {}

    if org is None:
        org = await ctx.db.get_organization(faction_id)
    if not org:
        await ctx.session.send_line("  Faction data unavailable.")
        return False, char, {}

    mem = await ctx.db.get_membership(char["id"], org["id"])
    if not mem or mem["rank_level"] < _MIN_LEADER_RANK:
        rank = mem["rank_level"] if mem else 0
        await ctx.session.send_line(
            f"  Leader commands require rank {_MIN_LEADER_RANK}. "
            f"(Your rank: {rank})"
        )
        return False, char, {}

    return True, char, mem


async def _resolve_target(ctx: CommandContext, org_id: int,
                           name_arg: str) -> dict | None:
    """
    Find a faction member by name (case-insensitive prefix match).
    Sends an error message and returns None on failure.
    """
    if not name_arg:
        await ctx.session.send_line("  Specify a member name.")
        return None

    members = await ctx.db.get_org_members(org_id)
    name_lower = name_arg.lower()
    match = next(
        (m for m in members
         if m["char_name"].lower().startswith(name_lower)),
        None,
    )
    if not match:
        await ctx.session.send_line(
            f"  No faction member matching '{name_arg}'."
        )
        return None
    return match


class FactionLeaderCommand(BaseCommand):
    """
    Umbrella command for all 'faction <leader-sub>' dispatches.
    Registered under 'faction' namespace so FactionCommand.execute()
    falls through to this when sub == known leader sub-commands.

    This is intentionally NOT registered as a standalone key — it is
    called directly from FactionCommand.execute() via the dispatch helper
    in faction_commands.py.
    """
    key = "_faction_leader_internal"  # Not registered directly
    aliases = []

    @staticmethod
    async def dispatch(ctx: CommandContext, sub: str, rest: str) -> bool:
        """
        Try to handle 'faction <sub> <rest>' as a leader command.
        Returns True if handled, False if not a leader command.
        """
        handlers = {
            "promote":    _handle_promote,
            "demote":     _handle_demote,
            "warn":       _handle_warn,
            "probation":  _handle_probation,
            "pardon":     _handle_pardon,
            "expel":      _handle_expel,
            "announce":   _handle_announce,
            "treasury":   _handle_treasury,
            "motd":       _handle_motd,
            "log":        _handle_log,
            "mission":    _handle_mission,
        }
        fn = handlers.get(sub)
        if fn is None:
            return False
        await fn(ctx, rest)
        return True

    async def execute(self, ctx: CommandContext):
        pass  # Never called directly


# ── Individual leader sub-command handlers ────────────────────────────────────

async def _handle_promote(ctx: CommandContext, rest: str):
    from engine.organizations import promote

    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, my_mem = await _require_leader(ctx, org)
    if not ok:
        return

    # Resolve target member
    target = await _resolve_target(ctx, org["id"], rest)
    if not target:
        return

    # Leader can promote up to their own rank - 1
    if target["rank_level"] + 1 >= my_mem["rank_level"]:
        await ctx.session.send_line(
            f"  You cannot promote {target['char_name']} to your own rank or higher."
        )
        return

    # Load the target character dict (needed by promote())
    rows = await ctx.db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (target["char_id"],)
    )
    if not rows:
        await ctx.session.send_line("  Character data not found.")
        return
    target_char = dict(rows[0])

    ok2, msg = await promote(target_char, faction_id, ctx.db, promoter_char=char)
    await ctx.session.send_line(f"  {msg}")

    # Notify target if online
    if ok2:
        sess = ctx.session_mgr.find_by_character(target["char_id"])
        if sess and sess is not ctx.session:
            await sess.send_line(
                f"  \033[1;36m[FACTION]\033[0m {char['name']} has promoted you "
                f"in {org['name']}."
            )


async def _handle_demote(ctx: CommandContext, rest: str):
    from engine.organizations import demote

    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, my_mem = await _require_leader(ctx, org)
    if not ok:
        return

    parts = rest.split(None, 1)
    name_arg = parts[0] if parts else ""
    target = await _resolve_target(ctx, org["id"], name_arg)
    if not target:
        return

    rows = await ctx.db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (target["char_id"],)
    )
    if not rows:
        return
    target_char = dict(rows[0])

    ok2, msg = await demote(target_char, faction_id, ctx.db, promoter_char=char)
    await ctx.session.send_line(f"  {msg}")

    if ok2:
        sess = ctx.session_mgr.find_by_character(target["char_id"])
        if sess and sess is not ctx.session:
            await sess.send_line(
                f"  \033[1;33m[FACTION]\033[0m {char['name']} has demoted you "
                f"in {org['name']}."
            )


async def _handle_warn(ctx: CommandContext, rest: str):
    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    parts = rest.split(None, 1)
    name_arg = parts[0] if parts else ""
    reason   = parts[1].strip() if len(parts) > 1 else "Conduct unbecoming."
    target = await _resolve_target(ctx, org["id"], name_arg)
    if not target:
        return

    await ctx.db.log_faction_action(
        target["char_id"], org["id"], "warn",
        f"Warned by {char['name']}: {reason}"
    )
    await ctx.session.send_line(
        f"  Warning issued to {target['char_name']}: {reason}"
    )
    sess = ctx.session_mgr.find_by_character(target["char_id"])
    if sess:
        await sess.send_line(
            f"  \033[1;33m[FACTION WARNING]\033[0m {org['name']}: "
            f"{char['name']} has issued a formal warning. {reason}"
        )


async def _handle_probation(ctx: CommandContext, rest: str):
    from engine.organizations import set_standing

    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    parts = rest.split(None, 1)
    name_arg = parts[0] if parts else ""
    reason   = parts[1].strip() if len(parts) > 1 else ""
    target = await _resolve_target(ctx, org["id"], name_arg)
    if not target:
        return

    rows = await ctx.db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (target["char_id"],)
    )
    if not rows:
        return
    target_char = dict(rows[0])

    ok2, msg = await set_standing(
        target_char, faction_id, "probation", ctx.db,
        actor_char=char, reason=reason
    )
    await ctx.session.send_line(f"  {msg}")

    if ok2:
        sess = ctx.session_mgr.find_by_character(target["char_id"])
        if sess:
            await sess.send_line(
                f"  \033[1;31m[FACTION]\033[0m {org['name']}: "
                f"You have been placed on probation. {reason}"
            )


async def _handle_pardon(ctx: CommandContext, rest: str):
    from engine.organizations import set_standing

    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    target = await _resolve_target(ctx, org["id"], rest.strip())
    if not target:
        return

    rows = await ctx.db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (target["char_id"],)
    )
    if not rows:
        return
    target_char = dict(rows[0])

    ok2, msg = await set_standing(
        target_char, faction_id, "good", ctx.db, actor_char=char
    )
    await ctx.session.send_line(f"  {msg}")

    if ok2:
        sess = ctx.session_mgr.find_by_character(target["char_id"])
        if sess:
            await sess.send_line(
                f"  \033[1;32m[FACTION]\033[0m {org['name']}: "
                f"Your probation has been lifted by {char['name']}."
            )


async def _handle_expel(ctx: CommandContext, rest: str):
    from engine.organizations import set_standing

    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, my_mem = await _require_leader(ctx, org)
    if not ok:
        return

    parts = rest.split(None, 1)
    name_arg = parts[0] if parts else ""
    reason   = parts[1].strip() if len(parts) > 1 else ""
    target = await _resolve_target(ctx, org["id"], name_arg)
    if not target:
        return

    # Cannot expel same-rank or higher
    if target["rank_level"] >= my_mem["rank_level"]:
        await ctx.session.send_line(
            f"  You cannot expel {target['char_name']} — equal or higher rank."
        )
        return

    rows = await ctx.db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (target["char_id"],)
    )
    if not rows:
        return
    target_char = dict(rows[0])

    ok2, msg = await set_standing(
        target_char, faction_id, "expelled", ctx.db,
        actor_char=char, reason=reason
    )
    await ctx.session.send_line(f"  {msg}")

    if ok2:
        sess = ctx.session_mgr.find_by_character(target["char_id"])
        if sess:
            await sess.send_line(
                f"  \033[1;31m[FACTION]\033[0m You have been expelled from "
                f"{org['name']}. All issued equipment has been reclaimed. {reason}"
            )


async def _handle_announce(ctx: CommandContext, rest: str):
    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    if not rest:
        await ctx.session.send_line("  Usage: faction announce <message>")
        return

    try:
        from server.channels import get_channel_manager
        cm = get_channel_manager()
        sender = f"{org['name']} Command"
        await cm.broadcast_fcomm(ctx.session_mgr, sender, faction_id, rest)
    except Exception as e:
        log.warning("[leader] announce failed: %s", e)
        await ctx.session.send_line("  Faction comms unavailable.")


async def _handle_treasury(ctx: CommandContext, rest: str):
    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    # Refresh org to get current treasury
    org = await ctx.db.get_organization(faction_id)
    treasury = org.get("treasury", 0) if org else 0
    await ctx.session.send_line(
        f"\n  \033[1;33m{org['name']} Treasury:\033[0m "
        f"\033[1;37m{treasury:,} credits\033[0m\n"
        f"  (Funded by stipends, dues, mission completion, and Director allocation.)\n"
        f"  Treasury pays member stipends and issues equipment automatically."
    )


async def _handle_motd(ctx: CommandContext, rest: str):
    from engine.organizations import update_org
    import json as _json

    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    if not rest:
        # Show current MOTD
        props = org.get("properties", "{}")
        if isinstance(props, str):
            try:
                props = _json.loads(props)
            except Exception:
                props = {}
        motd = props.get("motd", "(none set)")
        await ctx.session.send_line(f"  \033[1;33mFaction MOTD:\033[0m {motd}")
        return

    props = org.get("properties", "{}")
    if isinstance(props, str):
        try:
            props = _json.loads(props)
        except Exception:
            props = {}
    props["motd"] = rest[:200]
    await update_org(faction_id, ctx.db, properties=_json.dumps(props))
    await ctx.session.send_line(f"  \033[1;32mFaction MOTD updated.\033[0m")


async def _handle_log(ctx: CommandContext, rest: str):
    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    limit = 15
    if rest.isdigit():
        limit = min(50, max(1, int(rest)))

    rows = await ctx.db._db.execute_fetchall(
        """SELECT fl.logged_at, fl.action_type, fl.details,
                  COALESCE(c.name, 'System') AS char_name
           FROM faction_log fl
           LEFT JOIN characters c ON c.id = fl.char_id
           WHERE fl.org_id = ?
           ORDER BY fl.id DESC LIMIT ?""",
        (org["id"], limit),
    )
    if not rows:
        await ctx.session.send_line("  No faction log entries yet.")
        return

    lines = [
        f"\033[1;36m══════════════════════════════════════════\033[0m",
        f"  \033[1;37m{org['name'].upper()} — FACTION LOG (last {limit})\033[0m",
        f"\033[1;36m──────────────────────────────────────────\033[0m",
    ]
    for r in rows:
        ts = str(r["logged_at"])[:16]
        lines.append(
            f"  \033[2m{ts}\033[0m  "
            f"\033[1;33m{r['action_type']:<18}\033[0m  "
            f"\033[1;37m{r['char_name']}\033[0m  "
            f"\033[2m{r['details'][:60]}\033[0m"
        )
    lines.append(f"\033[1;36m══════════════════════════════════════════\033[0m")
    await ctx.session.send_line("\n".join(lines))


async def _handle_mission(ctx: CommandContext, rest: str):
    """faction mission create <type> <reward> <description>"""
    char = ctx.session.character
    faction_id = char.get("faction_id", "independent")
    org = await ctx.db.get_organization(faction_id)
    ok, char, _ = await _require_leader(ctx, org)
    if not ok:
        return

    parts = rest.split(None, 1)
    sub = parts[0].lower() if parts else ""
    args = parts[1].strip() if len(parts) > 1 else ""

    if sub != "create":
        await ctx.session.send_line(
            "  Usage: faction mission create <type> <reward> <description>\n"
            "  Types: patrol, delivery, combat, investigation, social"
        )
        return

    # Parse: <type> <reward> <rest is description>
    aparts = args.split(None, 2)
    if len(aparts) < 3:
        await ctx.session.send_line(
            "  Usage: faction mission create <type> <reward> <description>"
        )
        return

    mission_type = aparts[0].lower()
    VALID_TYPES = {"patrol", "delivery", "combat", "investigation", "social",
                   "bounty", "smuggling"}
    if mission_type not in VALID_TYPES:
        await ctx.session.send_line(
            f"  Unknown mission type '{mission_type}'.\n"
            f"  Valid: patrol, delivery, combat, investigation, social"
        )
        return

    if not aparts[1].isdigit():
        await ctx.session.send_line("  Reward must be a number of credits.")
        return
    reward = max(100, min(5000, int(aparts[1])))
    description = aparts[2]
    title = f"{org['name']}: {mission_type.title()} Mission"

    mission_id = await ctx.db.post_faction_mission(
        faction_id,
        mission_type=mission_type,
        title=title,
        description=description,
        reward=reward,
        difficulty="moderate",
        skill_required="",
    )
    await ctx.db.log_faction_action(
        char["id"], org["id"], "post_mission",
        f"Posted mission #{mission_id}: {title} ({reward}cr)"
    )
    await ctx.session.send_line(
        f"  \033[1;32mMission #{mission_id} posted.\033[0m\n"
        f"  {title} — {reward:,} credits\n"
        f"  Members can accept it via \033[1;33mfaction missions\033[0m."
    )


# ── Admin: @faction leader <code> <player> ────────────────────────────────────

class AdminFactionLeaderCommand(BaseCommand):
    key = "@faction"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin faction management.\n"
        "\n"
        "USAGE:\n"
        "  @faction leader <code> <player> -- hand off faction leadership to a PC\n"
        "  @faction director enable <code>  -- re-enable Director management\n"
        "  @faction director disable <code> -- disable Director management\n"
        "  @faction treasury add <code> <amount>\n"
        "  @faction treasury remove <code> <amount>"
    )
    usage = "@faction <sub> [args]"

    async def execute(self, ctx: CommandContext):
        from engine.organizations import handoff_faction_leadership, update_org

        parts = (ctx.args or "").split(None, 2)
        sub   = parts[0].lower() if parts else ""
        rest1 = parts[1] if len(parts) > 1 else ""
        rest2 = parts[2] if len(parts) > 2 else ""

        # ── @faction leader <code> <player> ──
        if sub == "leader":
            if not rest1 or not rest2:
                await ctx.session.send_line(
                    "  Usage: @faction leader <code> <player>"
                )
                return
            rows = await ctx.db._db.execute_fetchall(
                "SELECT * FROM characters WHERE LOWER(name) = LOWER(?)", (rest2,)
            )
            if not rows:
                await ctx.session.send_line(f"  Player '{rest2}' not found.")
                return
            new_leader = dict(rows[0])
            ok, msg = await handoff_faction_leadership(
                rest1, new_leader, ctx.db, ctx.session_mgr
            )
            await ctx.session.send_line(f"  {msg}")
            return

        # ── @faction director enable/disable <code> ──
        if sub == "director":
            action = rest1.lower()
            code   = rest2
            if action not in ("enable", "disable") or not code:
                await ctx.session.send_line(
                    "  Usage: @faction director <enable|disable> <code>"
                )
                return
            value = 1 if action == "enable" else 0
            await update_org(code, ctx.db, director_managed=value)
            await ctx.session.send_line(
                f"  Director management for '{code}' "
                f"{'ENABLED' if value else 'DISABLED'}."
            )
            return

        # ── @faction treasury add/remove <code> <amount> ──
        if sub == "treasury":
            action = rest1.lower()
            c_parts = rest2.split(None, 1)
            code    = c_parts[0] if c_parts else ""
            amount_str = c_parts[1] if len(c_parts) > 1 else ""
            if action not in ("add", "remove") or not code or not amount_str.isdigit():
                await ctx.session.send_line(
                    "  Usage: @faction treasury <add|remove> <code> <amount>"
                )
                return
            delta = int(amount_str)
            if action == "remove":
                delta = -delta
            new_bal = await ctx.db.adjust_org_treasury(
                (await ctx.db.get_organization(code) or {}).get("id", 0), delta
            )
            await ctx.session.send_line(
                f"  Treasury for '{code}' adjusted. New balance: {new_bal:,} cr."
            )
            return

        await ctx.session.send_line(
            f"  Unknown @faction sub-command '{sub}'.\n"
            f"  Try: leader, director, treasury"
        )


def register_faction_leader_commands(registry):
    registry.register(AdminFactionLeaderCommand())
