# -*- coding: utf-8 -*-
"""
engine/scenes.py — Scene Logging & Archive for SW_MUSH.

Inspired by AresMUSH scene management (see hspace_ares_integration_design_v1.md §3.2).

Lifecycle:
  +scene/start  → status='active',  room auto-locked to scene
  posing/saying → poses captured automatically via say/emote/ooc hooks
  +scene/stop   → status='completed', pose count tallied per participant
  +scene/share  → status='shared', visible in future web portal archive

Commands (parser/scene_commands.py):
  +scene/start [title]   Start a scene in the current room
  +scene/stop            End the active scene (creator or any participant)
  +scene/title <text>    Rename the scene
  +scene/type <type>     Set type: Social / Action / Plot / Vignette
  +scene/summary <text>  Add a brief summary (shown in archive)
  +scene/share           Make completed scene public
  +scene/unshare         Revert shared scene to private
  +scenes                List your recent scenes
  +scene [id]            View scene info / pose log

Integration hooks:
  capture_pose()         Called from SayCommand, EmoteCommand, OocCommand
  complete_scene()       Called from +scene/stop; fires scenebonus
  get_active_scene()     Returns active scene dict for a room_id or None
"""

import logging
import time

log = logging.getLogger(__name__)

# ── Scene type constants ───────────────────────────────────────────────────────
SCENE_TYPES = ("Social", "Action", "Plot", "Vignette")
DEFAULT_TYPE = "Social"

# ── In-memory cache of active scenes: {room_id: scene_id} ────────────────────
# Populated on startup by _warm_cache() and kept in sync.
_active_scenes: dict[int, int] = {}

# ── Pose Order Tracker ───────────────────────────────────────────────────────
# Tracks whose turn it is in multi-player scenes.
# Keyed by scene_id. Only active when 3+ participants.

POSE_MODE_ROUNDROBIN = "round-robin"
POSE_MODE_THREEPOSE = "3-per"
POSE_MODES = (POSE_MODE_ROUNDROBIN, POSE_MODE_THREEPOSE)

class PoseOrder:
    """Tracks pose rotation for a scene."""
    __slots__ = ("scene_id", "mode", "order", "current_idx",
                 "cycle_poses", "max_per_cycle")

    def __init__(self, scene_id: int, participants: list[int],
                 mode: str = POSE_MODE_ROUNDROBIN):
        self.scene_id = scene_id
        self.mode = mode
        self.order = list(participants)  # list of char_ids
        self.current_idx = 0
        # 3-per mode: {char_id: poses_used_this_cycle}
        self.cycle_poses: dict[int, int] = {cid: 0 for cid in self.order}
        self.max_per_cycle = 3

    def record_pose(self, char_id: int) -> list[int]:
        """Record a pose and return list of char_ids who are 'up next'.

        Round-robin: returns [next_char_id].
        3-per: returns list of char_ids who haven't used all poses this cycle.
        """
        if char_id not in self.order:
            return []

        if self.mode == POSE_MODE_ROUNDROBIN:
            # Advance to the poser's position, then move to next
            try:
                self.current_idx = self.order.index(char_id)
            except ValueError as _e:
                log.debug("silent except in engine/scenes.py:79: %s", _e, exc_info=True)
            self.current_idx = (self.current_idx + 1) % len(self.order)
            return [self.order[self.current_idx]]

        else:  # 3-per
            self.cycle_poses[char_id] = self.cycle_poses.get(char_id, 0) + 1
            # Check if everyone has used their poses — reset cycle
            if all(self.cycle_poses.get(cid, 0) >= self.max_per_cycle
                   for cid in self.order):
                self.cycle_poses = {cid: 0 for cid in self.order}
            # Return who still has poses left
            return [cid for cid in self.order
                    if self.cycle_poses.get(cid, 0) < self.max_per_cycle
                    and cid != char_id]

    def add_participant(self, char_id: int) -> None:
        if char_id not in self.order:
            self.order.append(char_id)
            self.cycle_poses[char_id] = 0

    def remove_participant(self, char_id: int) -> None:
        if char_id in self.order:
            idx = self.order.index(char_id)
            self.order.remove(char_id)
            self.cycle_poses.pop(char_id, None)
            if self.current_idx >= len(self.order) and self.order:
                self.current_idx = 0

    def get_next_names(self, name_map: dict[int, str]) -> list[str]:
        """Get names of who's up next, using a {char_id: name} map."""
        if self.mode == POSE_MODE_ROUNDROBIN:
            if self.order:
                cid = self.order[self.current_idx % len(self.order)]
                return [name_map.get(cid, f"#{cid}")]
            return []
        else:
            return [name_map.get(cid, f"#{cid}") for cid in self.order
                    if self.cycle_poses.get(cid, 0) < self.max_per_cycle]

    def get_status(self, name_map: dict[int, str]) -> str:
        """Return a formatted status string."""
        lines = [f"Mode: {self.mode}"]
        for i, cid in enumerate(self.order):
            name = name_map.get(cid, f"#{cid}")
            marker = ""
            if self.mode == POSE_MODE_ROUNDROBIN:
                if i == self.current_idx % len(self.order):
                    marker = " \x1b[92m<-- UP NEXT\x1b[0m"
            else:
                used = self.cycle_poses.get(cid, 0)
                remaining = self.max_per_cycle - used
                if remaining > 0:
                    marker = f" ({remaining} remaining)"
                else:
                    marker = " \x1b[2m(done this cycle)\x1b[0m"
            lines.append(f"  {i+1}. {name}{marker}")
        return "\n".join(lines)


# Pose order instances: {scene_id: PoseOrder}
_pose_orders: dict[int, PoseOrder] = {}


# ── Schema initialisation (called from ensure_scene_schema in db init) ─────────

SCENE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scenes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    DEFAULT '',
    summary         TEXT    DEFAULT '',
    scene_type      TEXT    DEFAULT 'Social',
    location        TEXT    DEFAULT '',
    room_id         INTEGER,
    creator_id      INTEGER NOT NULL REFERENCES characters(id),
    status          TEXT    DEFAULT 'active',
    started_at      REAL    NOT NULL,
    completed_at    REAL,
    shared_at       REAL
);

CREATE TABLE IF NOT EXISTS scene_poses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id        INTEGER NOT NULL REFERENCES scenes(id),
    char_id         INTEGER,
    char_name       TEXT    NOT NULL,
    pose_text       TEXT    NOT NULL,
    pose_type       TEXT    DEFAULT 'pose',
    is_ooc          INTEGER DEFAULT 0,
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS scene_participants (
    scene_id        INTEGER NOT NULL REFERENCES scenes(id),
    char_id         INTEGER NOT NULL REFERENCES characters(id),
    PRIMARY KEY (scene_id, char_id)
);

CREATE INDEX IF NOT EXISTS idx_scene_poses_scene
    ON scene_poses(scene_id, created_at);
CREATE INDEX IF NOT EXISTS idx_scenes_status
    ON scenes(status, started_at);
CREATE INDEX IF NOT EXISTS idx_scene_participants
    ON scene_participants(char_id);
CREATE INDEX IF NOT EXISTS idx_scenes_room
    ON scenes(room_id, status);
"""


async def ensure_scene_schema(db) -> None:
    """Create scene tables if absent. Idempotent."""
    try:
        for stmt in SCENE_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
        log.debug("[scenes] schema verified")
    except Exception as e:
        log.warning("[scenes] schema init error: %s", e)


# ── Cache warm-up ──────────────────────────────────────────────────────────────

async def warm_cache(db) -> None:
    """Load active scenes from DB into memory cache on startup."""
    global _active_scenes
    try:
        rows = await db.fetchall(
            "SELECT id, room_id FROM scenes WHERE status = 'active'"
        )
        _active_scenes = {r["room_id"]: r["id"] for r in rows if r["room_id"]}
        log.info("[scenes] cache warmed: %d active scene(s)", len(_active_scenes))
    except Exception as e:
        log.warning("[scenes] cache warm error: %s", e)


# ── Core API ───────────────────────────────────────────────────────────────────

def get_active_scene_id(room_id: int) -> int | None:
    """Return the active scene_id for a room, or None."""
    return _active_scenes.get(room_id)


async def get_active_scene(db, room_id: int) -> dict | None:
    """Return the active scene row dict for a room, or None."""
    scene_id = _active_scenes.get(room_id)
    if scene_id is None:
        return None
    try:
        rows = await db.fetchall(
            "SELECT * FROM scenes WHERE id = ?", (scene_id,)
        )
        return dict(rows[0]) if rows else None
    except Exception as e:
        log.warning("[scenes] get_active_scene error: %s", e)
        return None


async def start_scene(db, char: dict, room_id: int,
                      title: str = "", location: str = "") -> dict:
    """
    Start a new scene in room_id.
    Returns {ok, scene_id, msg}.
    """
    char_id = char["id"]

    # Only one active scene per room
    if room_id in _active_scenes:
        existing = await get_active_scene(db, room_id)
        if existing:
            creator_rows = await db.fetchall(
                "SELECT name FROM characters WHERE id = ?",
                (existing["creator_id"],)
            )
            creator_name = creator_rows[0]["name"] if creator_rows else "Someone"
            return {
                "ok": False,
                "msg": f"A scene is already active here (started by {creator_name}). "
                       f"Use +scene to see it.",
            }

    title = title.strip() or ""
    now = time.time()
    try:
        cursor = await db.execute(
            """INSERT INTO scenes
               (title, scene_type, location, room_id, creator_id, status, started_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)""",
            (title, DEFAULT_TYPE, location, room_id, char_id, now),
        )
        scene_id = cursor.lastrowid
        await db.commit()

        # Update cache
        _active_scenes[room_id] = scene_id

        # Auto-add creator as participant
        await _add_participant(db, scene_id, char_id)

        # Log a system pose
        display_title = f' — "{title}"' if title else ""
        await _log_system_pose(
            db, scene_id,
            f"Scene started by {char['name']}{display_title}.",
        )

        log.info("[scenes] scene %d started by char %d in room %d (%s)",
                 scene_id, char_id, room_id, title or "<untitled>")
        return {"ok": True, "scene_id": scene_id,
                "msg": f"Scene started{display_title}. Posing is now being logged."}
    except Exception as e:
        log.warning("[scenes] start_scene error: %s", e, exc_info=True)
        return {"ok": False, "msg": "Failed to start scene (database error)."}


async def capture_pose(db, scene_id: int, char_id: int | None,
                       char_name: str, pose_text: str,
                       pose_type: str = "pose", is_ooc: bool = False,
                       session_mgr=None) -> None:
    """
    Record a single pose into scene_poses.
    Called from SayCommand, EmoteCommand, OocCommand.
    Non-blocking: errors are logged, never raised.

    If session_mgr is provided and pose order is active, notifies next poser(s).
    """
    try:
        await db.execute(
            """INSERT INTO scene_poses
               (scene_id, char_id, char_name, pose_text, pose_type, is_ooc, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (scene_id, char_id, char_name, pose_text,
             pose_type, 1 if is_ooc else 0, time.time()),
        )
        await db.commit()

        # Add participant if not already tracked
        if char_id is not None:
            await _add_participant(db, scene_id, char_id)

        # Pose order notification (IC poses only)
        if char_id is not None and not is_ooc and session_mgr is not None:
            po = _pose_orders.get(scene_id)
            if po and char_id in po.order:
                next_ids = po.record_pose(char_id)
                if next_ids:
                    # Build name map from sessions in room
                    for room_id, sid in _active_scenes.items():
                        if sid == scene_id:
                            _notify_pose_order(session_mgr, room_id,
                                               next_ids, po.mode)
                            break
    except Exception as e:
        log.warning("[scenes] capture_pose error: %s", e)


async def stop_scene(db, char: dict, room_id: int) -> dict:
    """
    End the active scene in this room.
    Any participant (or admin) may stop it.
    Returns {ok, scene_id, msg, pose_counts: {char_id: int}}.
    """
    scene_id = _active_scenes.get(room_id)
    if scene_id is None:
        return {"ok": False, "msg": "No active scene in this room."}

    char_id = char["id"]
    is_admin = char.get("is_admin", 0)

    try:
        rows = await db.fetchall(
            "SELECT * FROM scenes WHERE id = ?", (scene_id,)
        )
        if not rows:
            _active_scenes.pop(room_id, None)
            return {"ok": False, "msg": "Scene not found."}
        scene = dict(rows[0])

        # Permission: creator, admin, or any participant
        if scene["creator_id"] != char_id and not is_admin:
            part = await db.fetchall(
                "SELECT 1 FROM scene_participants WHERE scene_id=? AND char_id=?",
                (scene_id, char_id)
            )
            if not part:
                return {"ok": False,
                        "msg": "Only the scene creator or a participant can stop it."}

        now = time.time()
        await db.execute(
            "UPDATE scenes SET status='completed', completed_at=? WHERE id=?",
            (now, scene_id)
        )
        await _log_system_pose(db, scene_id,
                               f"Scene ended by {char['name']}.")
        await db.commit()

        # Remove from cache
        _active_scenes.pop(room_id, None)
        # Clean up pose order
        stop_pose_order(scene_id)

        # Count IC poses per participant (exclude system/ooc)
        pose_rows = await db.fetchall(
            """SELECT char_id, COUNT(*) as cnt
               FROM scene_poses
               WHERE scene_id=? AND is_ooc=0 AND char_id IS NOT NULL
               GROUP BY char_id""",
            (scene_id,)
        )
        pose_counts = {r["char_id"]: r["cnt"] for r in pose_rows}
        total_poses = sum(pose_counts.values())

        log.info("[scenes] scene %d stopped in room %d. %d total IC poses.",
                 scene_id, room_id, total_poses)
        return {
            "ok": True,
            "scene_id": scene_id,
            "pose_counts": pose_counts,
            "total_poses": total_poses,
            "msg": f"Scene ended. {total_poses} IC pose(s) logged across "
                   f"{len(pose_counts)} participant(s). Use +scene/share to publish it.",
        }
    except Exception as e:
        log.warning("[scenes] stop_scene error: %s", e, exc_info=True)
        return {"ok": False, "msg": "Failed to stop scene (database error)."}


async def set_scene_title(db, char: dict, room_id: int, title: str) -> dict:
    """Set/rename the active scene's title."""
    return await _update_active_field(db, char, room_id, "title", title.strip(),
                                      f'Scene title set to "{title.strip()}".')


async def set_scene_type(db, char: dict, room_id: int, scene_type: str) -> dict:
    """Set the scene type (Social/Action/Plot/Vignette)."""
    normalized = scene_type.strip().capitalize()
    if normalized not in SCENE_TYPES:
        return {"ok": False,
                "msg": f"Unknown type. Choose: {', '.join(SCENE_TYPES)}"}
    return await _update_active_field(db, char, room_id, "scene_type", normalized,
                                      f"Scene type set to {normalized}.")


async def set_scene_summary(db, char: dict, room_id: int, summary: str) -> dict:
    """Set the scene summary (shown in archive)."""
    return await _update_active_field(db, char, room_id, "summary", summary.strip(),
                                      "Scene summary saved.")


async def share_scene(db, char: dict, scene_id: int) -> dict:
    """Mark a completed scene as shared (public)."""
    char_id = char["id"]
    is_admin = char.get("is_admin", 0)
    try:
        rows = await db.fetchall(
            "SELECT * FROM scenes WHERE id=?", (scene_id,)
        )
        if not rows:
            return {"ok": False, "msg": f"Scene #{scene_id} not found."}
        scene = dict(rows[0])

        if scene["creator_id"] != char_id and not is_admin:
            return {"ok": False, "msg": "Only the scene creator can share it."}
        if scene["status"] == "active":
            return {"ok": False, "msg": "End the scene first (+scene/stop)."}
        if scene["status"] == "shared":
            return {"ok": False, "msg": "Scene is already shared."}

        await db.execute(
            "UPDATE scenes SET status='shared', shared_at=? WHERE id=?",
            (time.time(), scene_id)
        )
        await db.commit()
        title_str = f' "{scene["title"]}"' if scene["title"] else ""
        return {"ok": True, "msg": f"Scene #{scene_id}{title_str} is now public."}
    except Exception as e:
        log.warning("[scenes] share_scene error: %s", e, exc_info=True)
        return {"ok": False, "msg": "Failed to share scene."}


async def unshare_scene(db, char: dict, scene_id: int) -> dict:
    """Revert a shared scene back to completed (private)."""
    char_id = char["id"]
    is_admin = char.get("is_admin", 0)
    try:
        rows = await db.fetchall(
            "SELECT * FROM scenes WHERE id=?", (scene_id,)
        )
        if not rows:
            return {"ok": False, "msg": f"Scene #{scene_id} not found."}
        scene = dict(rows[0])

        if scene["creator_id"] != char_id and not is_admin:
            return {"ok": False, "msg": "Only the scene creator can unshare it."}
        if scene["status"] != "shared":
            return {"ok": False, "msg": "Scene is not currently shared."}

        await db.execute(
            "UPDATE scenes SET status='completed', shared_at=NULL WHERE id=?",
            (scene_id,)
        )
        await db.commit()
        return {"ok": True, "msg": f"Scene #{scene_id} is now private."}
    except Exception as e:
        log.warning("[scenes] unshare_scene error: %s", e, exc_info=True)
        return {"ok": False, "msg": "Failed to unshare scene."}


async def get_char_scenes(db, char_id: int, limit: int = 15) -> list[dict]:
    """Return recent scenes the character participated in."""
    try:
        rows = await db.fetchall(
            """SELECT s.id, s.title, s.scene_type, s.location,
                      s.status, s.started_at, s.completed_at
               FROM scenes s
               JOIN scene_participants sp ON sp.scene_id = s.id
               WHERE sp.char_id = ?
               ORDER BY s.started_at DESC
               LIMIT ?""",
            (char_id, limit)
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("[scenes] get_char_scenes error: %s", e)
        return []


async def get_scene_detail(db, scene_id: int) -> dict | None:
    """Return scene dict with pose log and participant list."""
    try:
        rows = await db.fetchall(
            "SELECT * FROM scenes WHERE id=?", (scene_id,)
        )
        if not rows:
            return None
        scene = dict(rows[0])

        poses = await db.fetchall(
            """SELECT char_name, pose_text, pose_type, is_ooc, created_at
               FROM scene_poses WHERE scene_id=? ORDER BY created_at ASC""",
            (scene_id,)
        )
        scene["poses"] = [dict(p) for p in poses]

        parts = await db.fetchall(
            """SELECT c.name FROM scene_participants sp
               JOIN characters c ON c.id = sp.char_id
               WHERE sp.scene_id=?""",
            (scene_id,)
        )
        scene["participants"] = [r["name"] for r in parts]
        return scene
    except Exception as e:
        log.warning("[scenes] get_scene_detail error: %s", e)
        return None


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _add_participant(db, scene_id: int, char_id: int) -> None:
    try:
        await db.execute(
            """INSERT OR IGNORE INTO scene_participants (scene_id, char_id)
               VALUES (?, ?)""",
            (scene_id, char_id)
        )
        await db.commit()
    except Exception as e:
        log.warning("[scenes] _add_participant error: %s", e)


async def _log_system_pose(db, scene_id: int, text: str) -> None:
    try:
        await db.execute(
            """INSERT INTO scene_poses
               (scene_id, char_id, char_name, pose_text, pose_type, is_ooc, created_at)
               VALUES (?, NULL, '-- System --', ?, 'system', 0, ?)""",
            (scene_id, text, time.time())
        )
        await db.commit()
    except Exception as e:
        log.warning("[scenes] _log_system_pose error: %s", e)


async def _update_active_field(db, char: dict, room_id: int,
                                field: str, value: str, success_msg: str) -> dict:
    """Generic helper: update one field on the active scene for a room."""
    scene_id = _active_scenes.get(room_id)
    if scene_id is None:
        return {"ok": False, "msg": "No active scene in this room."}

    char_id = char["id"]
    is_admin = char.get("is_admin", 0)
    try:
        rows = await db.fetchall(
            "SELECT creator_id FROM scenes WHERE id=?", (scene_id,)
        )
        if not rows:
            return {"ok": False, "msg": "Scene not found."}
        if rows[0]["creator_id"] != char_id and not is_admin:
            return {"ok": False,
                    "msg": "Only the scene creator can change scene settings."}

        await db.execute(
            f"UPDATE scenes SET {field}=? WHERE id=?", (value, scene_id)
        )
        await db.commit()
        return {"ok": True, "msg": success_msg}
    except Exception as e:
        log.warning("[scenes] _update_active_field(%s) error: %s", field, e)
        return {"ok": False, "msg": "Database error."}


# ── Pose Order Management ──────────────────────────────────────────────────────

def _notify_pose_order(session_mgr, room_id: int,
                       next_ids: list[int], mode: str) -> None:
    """Send private pose-order notification to next poser(s)."""
    try:
        sessions = session_mgr.sessions_in_room(room_id)
        for s in sessions:
            if s.character and s.character["id"] in next_ids:
                import asyncio
                if mode == POSE_MODE_ROUNDROBIN:
                    msg = "\x1b[2m[Pose Order] It's your turn to pose.\x1b[0m"
                else:
                    msg = "\x1b[2m[Pose Order] You have poses remaining this cycle.\x1b[0m"
                asyncio.create_task(s.send(msg))
    except Exception as e:
        log.warning("[scenes] _notify_pose_order error: %s", e)


async def start_pose_order(db, scene_id: int, mode: str = POSE_MODE_ROUNDROBIN) -> dict:
    """Initialize pose order tracking for a scene."""
    if mode not in POSE_MODES:
        return {"ok": False,
                "msg": f"Unknown mode. Choose: {', '.join(POSE_MODES)}"}

    try:
        parts = await db.fetchall(
            "SELECT char_id FROM scene_participants WHERE scene_id=?",
            (scene_id,)
        )
        participant_ids = [r["char_id"] for r in parts]
        if len(participant_ids) < 2:
            return {"ok": False,
                    "msg": "Need at least 2 participants for pose order tracking."}

        po = PoseOrder(scene_id, participant_ids, mode=mode)
        _pose_orders[scene_id] = po
        log.info("[scenes] pose order started for scene %d (%s, %d participants)",
                 scene_id, mode, len(participant_ids))
        return {"ok": True, "participants": len(participant_ids),
                "msg": f"Pose order tracking enabled ({mode}). "
                       f"{len(participant_ids)} participants in rotation."}
    except Exception as e:
        log.warning("[scenes] start_pose_order error: %s", e)
        return {"ok": False, "msg": "Failed to start pose order."}


def stop_pose_order(scene_id: int) -> None:
    """Remove pose order tracking for a scene."""
    _pose_orders.pop(scene_id, None)


def get_pose_order(scene_id: int) -> PoseOrder | None:
    """Return the PoseOrder for a scene, or None."""
    return _pose_orders.get(scene_id)


def add_to_pose_order(scene_id: int, char_id: int) -> bool:
    """Add a participant to pose order. Returns False if no order active."""
    po = _pose_orders.get(scene_id)
    if po is None:
        return False
    po.add_participant(char_id)
    return True


def remove_from_pose_order(scene_id: int, char_id: int) -> bool:
    """Remove a participant from pose order. Returns False if not found."""
    po = _pose_orders.get(scene_id)
    if po is None:
        return False
    po.remove_participant(char_id)
    # Auto-disable if fewer than 2 remain
    if len(po.order) < 2:
        _pose_orders.pop(scene_id, None)
    return True


def set_pose_order_mode(scene_id: int, mode: str) -> dict:
    """Change pose order mode for an active scene."""
    if mode not in POSE_MODES:
        return {"ok": False,
                "msg": f"Unknown mode. Choose: {', '.join(POSE_MODES)}"}
    po = _pose_orders.get(scene_id)
    if po is None:
        return {"ok": False, "msg": "No pose order active for this scene."}
    po.mode = mode
    po.current_idx = 0
    po.cycle_poses = {cid: 0 for cid in po.order}
    return {"ok": True, "msg": f"Pose order mode changed to {mode}."}
