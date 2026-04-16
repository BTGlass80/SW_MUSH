# -*- coding: utf-8 -*-
"""
parser/scene_commands.py — Scene Logging commands for SW_MUSH.

Commands:
  +scene/start [title]   Start a scene in the current room
  +scene/stop            End the active scene
  +scene/title <text>    Rename the active scene
  +scene/type <type>     Set type: Social / Action / Plot / Vignette
  +scene/summary <text>  Set a brief summary for the archive
  +scene/share           Make the most recent completed scene public
  +scene/share <id>      Share a specific scene by ID
  +scene/unshare [id]    Revert a shared scene to private
  +scenes                List your recent scenes
  +scene [id]            View scene info or a specific scene's log
"""

import logging
import time

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)

# Achievement hooks (graceful-drop)
async def _ach_scene_hook(db, char_id, event, session=None):
    try:
        from engine.achievements import check_achievement
        await check_achievement(db, char_id, event, session=session)
    except Exception as _e:
        log.debug("silent except in parser/scene_commands.py:31: %s", _e, exc_info=True)


_SUBS = ("start", "stop", "title", "type", "summary", "share", "unshare")

# ── Formatting helpers ─────────────────────────────────────────────────────────

_STATUS_COLOR = {
    "active":    "\033[1;32m",   # bright green
    "completed": "\033[0;33m",   # amber
    "shared":    "\033[1;36m",   # cyan
}
_STATUS_LABEL = {
    "active":    "ACTIVE",
    "completed": "COMPLETED",
    "shared":    "SHARED",
}

def _fmt_status(status: str) -> str:
    col = _STATUS_COLOR.get(status, "")
    label = _STATUS_LABEL.get(status, status.upper())
    return f"{col}{label}\033[0m"


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "—"
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _fmt_duration(started: float, ended: float | None) -> str:
    end = ended or time.time()
    secs = int(end - started)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    h, m = divmod(secs // 60, 60)
    return f"{h}h {m}m"


# ── +scene (info/log viewer) ───────────────────────────────────────────────────

class SceneCommand(BaseCommand):
    key = "+scene"
    aliases = ["scene"]
    help_text = (
        "View scene info or a scene log.\n\n"
        "  +scene          — Show active scene in current room\n"
        "  +scene <id>     — Show log for scene #id\n\n"
        "SCENE SUBCOMMANDS:\n"
        "  +scene/start [title]   Start a scene here\n"
        "  +scene/stop            End the active scene\n"
        "  +scene/title <text>    Rename the scene\n"
        "  +scene/type <type>     Social / Action / Plot / Vignette\n"
        "  +scene/summary <text>  Set a brief summary\n"
        "  +scene/share [id]      Make scene public\n"
        "  +scene/unshare [id]    Make scene private again\n"
        "  +scene/poseorder       Start/view pose order tracker\n"
        "  +scene/drop <name>     Remove someone from pose rotation\n"
        "  +scene/mode <mode>     Set mode: round-robin / 3-per\n"
        "  +scenes                List your recent scenes"
    )
    usage = "+scene [id]"

    async def execute(self, ctx: CommandContext):
        from engine import scenes as sm

        # Parser populates ctx.switches from "+scene/start" → switches=["start"]
        sub = ctx.switches[0] if ctx.switches else ""
        sub_arg = ctx.args.strip()

        if sub == "start":
            await _cmd_scene_start(ctx, sub_arg)
            return
        if sub == "stop":
            await _cmd_scene_stop(ctx)
            return
        if sub == "title":
            await _cmd_scene_field(ctx, "title", sub_arg)
            return
        if sub == "type":
            await _cmd_scene_field(ctx, "type", sub_arg)
            return
        if sub == "summary":
            await _cmd_scene_field(ctx, "summary", sub_arg)
            return
        if sub == "share":
            await _cmd_scene_share(ctx, sub_arg, share=True)
            return
        if sub == "unshare":
            await _cmd_scene_share(ctx, sub_arg, share=False)
            return
        if sub == "poseorder" or sub == "po":
            await _cmd_pose_order(ctx)
            return
        if sub == "drop":
            await _cmd_pose_drop(ctx, sub_arg)
            return
        if sub == "mode":
            await _cmd_pose_mode(ctx, sub_arg)
            return

        # +scene <id> — show scene log
        if ctx.args and ctx.args.strip().isdigit():
            await _show_scene_log(ctx, int(ctx.args.strip()))
            return

        # +scene — show active scene in current room
        char = ctx.session.character
        room_id = char["room_id"]
        scene = await sm.get_active_scene(ctx.db, room_id)
        if not scene:
            await ctx.session.send_line(
                ansi.dim("No active scene here. Use +scene/start to begin one.")
            )
            return
        await _show_scene_info(ctx, scene)


# ── +scenes (list) ─────────────────────────────────────────────────────────────

class ScenesListCommand(BaseCommand):
    key = "+scenes"
    aliases = ["scenes"]
    help_text = "List your recent scenes."
    usage = "+scenes"

    async def execute(self, ctx: CommandContext):
        from engine import scenes as sm
        char = ctx.session.character
        scene_list = await sm.get_char_scenes(ctx.db, char["id"])

        await ctx.session.send_line(ansi.header("=== Your Recent Scenes ==="))
        if not scene_list:
            await ctx.session.send_line(
                ansi.dim("  No scenes found. Use +scene/start to begin one.")
            )
            await ctx.session.send_line("")
            return

        for s in scene_list:
            sid = s["id"]
            title = s["title"] or ansi.dim("<untitled>")
            stype = s["scene_type"] or "Social"
            loc = s["location"] or "Unknown"
            status = _fmt_status(s["status"])
            started = _fmt_ts(s["started_at"])
            dur = _fmt_duration(s["started_at"], s.get("completed_at"))
            await ctx.session.send_line(
                f"  \033[1;37m#{sid:>4}\033[0m  {status}  "
                f"\033[1;36m{stype:10}\033[0m  {title}"
            )
            await ctx.session.send_line(
                f"         {ansi.dim(loc)}  {ansi.dim(started)}  "
                f"{ansi.dim(dur)}"
            )
        await ctx.session.send_line("")
        await ctx.session.send_line(
            ansi.dim("  +scene <id> to view log · +scene/share <id> to publish")
        )
        await ctx.session.send_line("")


# ── Subcommand handlers ────────────────────────────────────────────────────────

async def _cmd_scene_start(ctx: CommandContext, title: str):
    from engine import scenes as sm
    char = ctx.session.character
    room_id = char["room_id"]

    # Get room name for location field
    room_rows = await ctx.db.fetchall(
        "SELECT name FROM rooms WHERE id=?", (room_id,)
    )
    location = room_rows[0]["name"] if room_rows else "Unknown"

    result = await sm.start_scene(ctx.db, char, room_id,
                                  title=title, location=location)
    if result["ok"]:
        await ctx.session.send_line(ansi.success(result["msg"]))
        # Broadcast to room
        scene_id = result["scene_id"]
        title_str = f' — "{title}"' if title else ""
        notice = (
            f'\033[1;35m[SCENE]\033[0m '
            f'{ansi.player_name(char["name"])} has started a scene{title_str}. '
            f'Poses are being logged (#\033[1;37m{scene_id}\033[0m).'
        )
        await ctx.session_mgr.broadcast_to_room(
            room_id, notice, exclude=ctx.session
        )
    else:
        await ctx.session.send_line(ansi.error(result["msg"]))


async def _cmd_scene_stop(ctx: CommandContext):
    from engine import scenes as sm
    from engine.cp_engine import get_cp_engine

    char = ctx.session.character
    room_id = char["room_id"]

    result = await sm.stop_scene(ctx.db, char, room_id)
    if not result["ok"]:
        await ctx.session.send_line(ansi.error(result["msg"]))
        return

    # Broadcast to room
    await ctx.session.send_line(ansi.success(result["msg"]))
    await ctx.session_mgr.broadcast_to_room(
        room_id,
        f'\033[1;35m[SCENE]\033[0m '
        f'{ansi.player_name(char["name"])} has ended the scene. '
        f'{result["total_poses"]} IC pose(s) logged.',
        exclude=ctx.session,
    )

    # Award scene CP bonuses to all participants who posed
    pose_counts = result.get("pose_counts", {})
    if not pose_counts:
        return

    cp_engine = get_cp_engine()
    # Resolve online sessions for notifications
    online_by_char = {}
    for s in ctx.session_mgr.all:
        if s.is_in_game and s.character:
            online_by_char[s.character["id"]] = s

    for cid, pose_count in pose_counts.items():
        cp_result = await cp_engine.award_scene_bonus(ctx.db, cid, pose_count)
        if cp_result["ticks"] > 0:
            sess = online_by_char.get(cid)
            if sess:
                await sess.send_line(
                    f'\033[1;35m[SCENE CP]\033[0m {cp_result["message"]}'
                )
            log.info("[scenes] scene CP: char %d +%d ticks (%d poses)",
                     cid, cp_result["ticks"], pose_count)

    # Queue async scene summary via idle queue (Ollama/Mistral)
    try:
        _iq = getattr(ctx.session_mgr, '_idle_queue', None)
        scene_id = result.get("scene_id", 0)
        if _iq and scene_id:
            room = await ctx.db.get_room(room_id)
            _rn = room.get("name", "") if room else ""
            # Gather participant names
            _pnames = []
            for _cid in pose_counts:
                _crow = await ctx.db.fetchall(
                    "SELECT name FROM characters WHERE id = ?", (_cid,))
                if _crow:
                    _pnames.append(_crow[0]["name"])
            # Gather last 30 poses
            _poses = await ctx.db.fetchall(
                "SELECT character_name, content FROM scene_poses "
                "WHERE scene_id = ? ORDER BY posed_at DESC LIMIT 30",
                (scene_id,))
            _poses.reverse()
            _ptxt = "\n".join(
                f"{p['character_name']}: {p['content']}" for p in _poses
            )
            _iq.enqueue_scene_summary(
                scene_id=scene_id,
                room_name=_rn,
                participants=", ".join(_pnames),
                poses_text=_ptxt,
            )
    except Exception:
        pass  # Non-critical


async def _cmd_scene_field(ctx: CommandContext, field: str, value: str):
    from engine import scenes as sm

    if not value:
        await ctx.session.send_line(
            ansi.error(f"Usage: +scene/{field} <value>")
        )
        return

    char = ctx.session.character
    room_id = char["room_id"]

    if field == "title":
        result = await sm.set_scene_title(ctx.db, char, room_id, value)
    elif field == "type":
        result = await sm.set_scene_type(ctx.db, char, room_id, value)
    elif field == "summary":
        result = await sm.set_scene_summary(ctx.db, char, room_id, value)
    else:
        result = {"ok": False, "msg": "Unknown field."}

    if result["ok"]:
        await ctx.session.send_line(ansi.success(result["msg"]))
    else:
        await ctx.session.send_line(ansi.error(result["msg"]))


async def _cmd_scene_share(ctx: CommandContext, arg: str, share: bool):
    from engine import scenes as sm
    char = ctx.session.character

    # Determine scene_id: explicit arg, or most recent completed
    if arg and arg.isdigit():
        scene_id = int(arg)
    else:
        # Find most recent completed/shared scene for this char
        scene_list = await sm.get_char_scenes(ctx.db, char["id"], limit=5)
        eligible = [s for s in scene_list
                    if s["status"] in ("completed", "shared")]
        if not eligible:
            action = "share" if share else "unshare"
            await ctx.session.send_line(
                ansi.error(
                    f"No completed scenes found. "
                    f"Use +scene/{action} <id> to specify one."
                )
            )
            return
        scene_id = eligible[0]["id"]

    if share:
        result = await sm.share_scene(ctx.db, char, scene_id)
    else:
        result = await sm.unshare_scene(ctx.db, char, scene_id)

    if result["ok"]:
        await ctx.session.send_line(ansi.success(result["msg"]))
    else:
        await ctx.session.send_line(ansi.error(result["msg"]))


# ── Scene info / log display ───────────────────────────────────────────────────

async def _show_scene_info(ctx: CommandContext, scene: dict):
    sid = scene["id"]
    title = scene["title"] or ansi.dim("<untitled>")
    stype = scene["scene_type"] or "Social"
    location = scene["location"] or "Unknown"
    status = _fmt_status(scene["status"])
    started = _fmt_ts(scene["started_at"])
    dur = _fmt_duration(scene["started_at"], scene.get("completed_at"))
    summary = scene.get("summary", "") or ""

    await ctx.session.send_line(ansi.header(f"=== Scene #{sid} ==="))
    await ctx.session.send_line(
        f"  \033[1;37mTitle:\033[0m  {title}"
    )
    await ctx.session.send_line(
        f"  \033[1;37mType:\033[0m   {stype}  "
        f"  \033[1;37mStatus:\033[0m {status}"
    )
    await ctx.session.send_line(
        f"  \033[1;37mWhere:\033[0m  {location}"
    )
    await ctx.session.send_line(
        f"  \033[1;37mWhen:\033[0m   {started}  ({dur})"
    )
    if summary:
        await ctx.session.send_line(
            f"  \033[1;37mSummary:\033[0m {summary}"
        )

    # Participant list
    from engine import scenes as sm
    detail = await sm.get_scene_detail(ctx.db, sid)
    if detail and detail.get("participants"):
        names = ", ".join(detail["participants"])
        await ctx.session.send_line(
            f"  \033[1;37mCast:\033[0m   {names}"
        )

    # Pose count
    if detail:
        ic_poses = [p for p in detail["poses"] if not p["is_ooc"] and p["pose_type"] != "system"]
        await ctx.session.send_line(
            f"  \033[1;37mPoses:\033[0m  {len(ic_poses)} IC poses logged"
        )

    await ctx.session.send_line("")
    await ctx.session.send_line(
        ansi.dim(f"  +scene {sid} to read the full log · "
                 f"+scene/stop to end · +scene/share {sid} to publish")
    )
    await ctx.session.send_line("")


async def _show_scene_log(ctx: CommandContext, scene_id: int):
    from engine import scenes as sm
    detail = await sm.get_scene_detail(ctx.db, scene_id)

    if not detail:
        await ctx.session.send_line(ansi.error(f"Scene #{scene_id} not found."))
        return

    # Permission: non-shared scenes only visible to participants + admins
    char = ctx.session.character
    is_admin = char.get("is_admin", 0)
    is_participant = char["name"] in detail.get("participants", [])
    if detail["status"] not in ("shared",) and not is_admin and not is_participant:
        await ctx.session.send_line(
            ansi.error("That scene is private. Only participants can view it.")
        )
        return

    title = detail["title"] or "<Untitled>"
    stype = detail["scene_type"] or "Social"
    location = detail["location"] or "Unknown"
    started = _fmt_ts(detail["started_at"])

    await ctx.session.send_line(
        f"\n\033[1;35m{'─' * 60}\033[0m"
    )
    await ctx.session.send_line(
        f"\033[1;37m  {title}\033[0m  "
        f"\033[0;36m[{stype}]\033[0m  "
        f"{_fmt_status(detail['status'])}"
    )
    await ctx.session.send_line(
        f"  {ansi.dim(location)}  ·  {ansi.dim(started)}"
    )
    if detail.get("summary"):
        await ctx.session.send_line(
            f"  \033[3m{detail['summary']}\033[0m"
        )
    await ctx.session.send_line(
        f"\033[1;35m{'─' * 60}\033[0m\n"
    )

    # Render poses — skip OOC, style system poses differently
    for pose in detail["poses"]:
        if pose["is_ooc"]:
            continue
        if pose["pose_type"] == "system":
            await ctx.session.send_line(
                f"\033[2m  -- {pose['pose_text']} --\033[0m"
            )
        else:
            await ctx.session.send_line(pose["pose_text"])
            await ctx.session.send_line("")

    await ctx.session.send_line(
        f"\033[1;35m{'─' * 60}\033[0m"
    )
    parts = ", ".join(detail.get("participants", []))
    await ctx.session.send_line(
        ansi.dim(f"  Cast: {parts}")
    )
    await ctx.session.send_line("")


# ── Pose Order Commands ────────────────────────────────────────────────────────

async def _cmd_pose_order(ctx):
    """Start or view pose order tracking."""
    from engine import scenes as sm
    char = ctx.session.character
    room_id = char["room_id"]
    scene_id = sm.get_active_scene_id(room_id)
    if scene_id is None:
        await ctx.session.send_line(
            ansi.dim("No active scene here. Start one with +scene/start."))
        return

    po = sm.get_pose_order(scene_id)
    if po is not None:
        # Show existing pose order
        # Build name map from participants in room
        name_map = {}
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character:
                name_map[s.character["id"]] = s.character["name"]
        # Also get names from DB for offline participants
        try:
            parts = await ctx.db.fetchall(
                """SELECT sp.char_id, c.name FROM scene_participants sp
                   JOIN characters c ON c.id = sp.char_id
                   WHERE sp.scene_id=?""", (scene_id,))
            for r in parts:
                name_map[r["char_id"]] = r["name"]
        except Exception as _e:
            log.debug("silent except in parser/scene_commands.py:516: %s", _e, exc_info=True)

        status = po.get_status(name_map)
        await ctx.session.send_line("\x1b[33m═══ POSE ORDER ═══\x1b[0m")
        await ctx.session.send_line(status)
        await ctx.session.send_line("")
        await ctx.session.send_line(
            ansi.dim("+scene/mode <round-robin|3-per>  Change mode"))
        await ctx.session.send_line(
            ansi.dim("+scene/drop <name>               Remove from rotation"))
        return

    # Start pose order
    result = await sm.start_pose_order(ctx.db, scene_id)
    if result["ok"]:
        await ctx.session.send_line(f"\x1b[92m{result['msg']}\x1b[0m")
        # Notify room
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character and s.character["id"] != char["id"]:
                await s.send(
                    ansi.dim(f"[Pose Order] {char['name']} enabled pose order tracking."))
    else:
        await ctx.session.send_line(result["msg"])


async def _cmd_pose_drop(ctx, name: str):
    """Remove a participant from pose rotation."""
    from engine import scenes as sm
    char = ctx.session.character
    room_id = char["room_id"]
    scene_id = sm.get_active_scene_id(room_id)
    if scene_id is None:
        await ctx.session.send_line(
            ansi.dim("No active scene here."))
        return

    po = sm.get_pose_order(scene_id)
    if po is None:
        await ctx.session.send_line(
            ansi.dim("No pose order active. Use +scene/poseorder to start one."))
        return

    if not name:
        await ctx.session.send_line("Usage: +scene/drop <name>")
        return

    # Find char_id by name
    name_lower = name.lower()
    target_id = None
    target_name = None

    # Check online sessions first
    for s in ctx.session_mgr.sessions_in_room(room_id):
        if s.character and s.character["name"].lower().startswith(name_lower):
            target_id = s.character["id"]
            target_name = s.character["name"]
            break

    # Fall back to participant list
    if target_id is None:
        try:
            parts = await ctx.db.fetchall(
                """SELECT sp.char_id, c.name FROM scene_participants sp
                   JOIN characters c ON c.id = sp.char_id
                   WHERE sp.scene_id=?""", (scene_id,))
            for r in parts:
                if r["name"].lower().startswith(name_lower):
                    target_id = r["char_id"]
                    target_name = r["name"]
                    break
        except Exception as _e:
            log.debug("silent except in parser/scene_commands.py:587: %s", _e, exc_info=True)

    if target_id is None:
        await ctx.session.send_line(f"No participant matching '{name}' found.")
        return

    ok = sm.remove_from_pose_order(scene_id, target_id)
    if ok:
        await ctx.session.send_line(
            f"\x1b[92m{target_name} removed from pose rotation.\x1b[0m")
        if sm.get_pose_order(scene_id) is None:
            await ctx.session.send_line(
                ansi.dim("Pose order disabled (fewer than 2 remaining)."))
    else:
        await ctx.session.send_line("No pose order active.")


async def _cmd_pose_mode(ctx, mode: str):
    """Change pose order mode."""
    from engine import scenes as sm
    char = ctx.session.character
    room_id = char["room_id"]
    scene_id = sm.get_active_scene_id(room_id)
    if scene_id is None:
        await ctx.session.send_line(ansi.dim("No active scene here."))
        return

    if not mode:
        await ctx.session.send_line("Usage: +scene/mode <round-robin|3-per>")
        return

    result = sm.set_pose_order_mode(scene_id, mode.strip().lower())
    if result["ok"]:
        await ctx.session.send_line(f"\x1b[92m{result['msg']}\x1b[0m")
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character and s.character["id"] != char["id"]:
                await s.send(
                    ansi.dim(f"[Pose Order] Mode changed to {mode.strip().lower()}."))
    else:
        await ctx.session.send_line(result["msg"])


# ── Registration ───────────────────────────────────────────────────────────────

def register_scene_commands(registry) -> None:
    registry.register(SceneCommand())
    registry.register(ScenesListCommand())
    log.info("[scenes] scene commands registered")
