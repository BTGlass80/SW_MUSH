# -*- coding: utf-8 -*-
"""
engine/plots.py — Plot / Story Arc Tracker for SW_MUSH.

Groups related scenes into named story arcs. Players create plots,
link scenes to them, and track ongoing narratives across sessions.

Commands (parser/plot_commands.py):
  +plots                          List open plots
  +plot <id>                      View plot details + linked scenes
  +plot/create <title>=<summary>  Create a new plot
  +plot/summary <id>=<text>       Update plot summary
  +plot/link <plot_id>=<scene_id> Link a scene to a plot
  +plot/unlink <plot_id>=<scene_id> Unlink a scene from a plot
  +plot/close <id>                Close a completed plot
  +plot/reopen <id>               Reopen a closed plot

Schema (v16 migration):
  plots        — plot records
  plot_scenes  — junction table linking plots to scenes
"""

import logging
import time

log = logging.getLogger(__name__)

# ── Status constants ───────────────────────────────────────────────────────────
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"


async def create_plot(db, creator_id: int, creator_name: str,
                      title: str, summary: str = "") -> dict:
    """Create a new plot. Returns the plot dict."""
    now = time.time()
    await db.execute(
        """INSERT INTO plots
           (title, summary, creator_id, creator_name, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, summary, creator_id, creator_name, STATUS_OPEN, now, now)
    )
    await db.commit()
    rows = await db.fetchall(
        "SELECT * FROM plots WHERE creator_id=? ORDER BY id DESC LIMIT 1",
        (creator_id,)
    )
    row = rows[0] if rows else None
    log.info("Plot #%d created by %s: %s", row["id"], creator_name, title)
    return dict(row)


async def get_plot(db, plot_id: int) -> dict:
    """Get plot by ID. Returns dict or None."""
    rows = await db.fetchall(
        "SELECT * FROM plots WHERE id=?", (plot_id,)
    )
    return dict(rows[0]) if rows else None


async def get_open_plots(db, limit: int = 30) -> list:
    """Get open plots, most recently updated first."""
    rows = await db.fetchall(
        """SELECT * FROM plots
           WHERE status = ?
           ORDER BY updated_at DESC
           LIMIT ?""",
        (STATUS_OPEN, limit)
    )
    return [dict(r) for r in rows]


async def get_all_plots(db, limit: int = 50, include_closed: bool = True) -> list:
    """Get all plots for portal display."""
    if include_closed:
        rows = await db.fetchall(
            "SELECT * FROM plots ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        )
    else:
        rows = await db.fetchall(
            "SELECT * FROM plots WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (STATUS_OPEN, limit)
        )
    return [dict(r) for r in rows]


async def get_my_plots(db, char_id: int, limit: int = 30) -> list:
    """Get plots a character created or participates in."""
    # Plots they created
    created = await db.fetchall(
        "SELECT * FROM plots WHERE creator_id = ? ORDER BY updated_at DESC LIMIT ?",
        (char_id, limit)
    )
    # Plots they have scenes linked to
    linked = await db.fetchall(
        """SELECT DISTINCT p.* FROM plots p
           JOIN plot_scenes ps ON ps.plot_id = p.id
           JOIN scene_participants sp ON sp.scene_id = ps.scene_id
           WHERE sp.char_id = ?
           ORDER BY p.updated_at DESC
           LIMIT ?""",
        (char_id, limit)
    )
    # Merge, deduplicate, sort by updated_at desc
    seen = set()
    result = []
    for row in list(created) + list(linked):
        d = dict(row)
        if d["id"] not in seen:
            seen.add(d["id"])
            result.append(d)
    result.sort(key=lambda p: p.get("updated_at", 0), reverse=True)
    return result[:limit]


async def update_plot(db, plot_id: int, **fields) -> bool:
    """Update plot fields. Returns True on success."""
    if not fields:
        return False
    fields["updated_at"] = time.time()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [plot_id]
    await db.execute(
        f"UPDATE plots SET {set_clause} WHERE id = ?", vals
    )
    await db.commit()
    return True


async def close_plot(db, plot_id: int) -> bool:
    """Close a plot (mark complete)."""
    return await update_plot(db, plot_id, status=STATUS_CLOSED)


async def reopen_plot(db, plot_id: int) -> bool:
    """Reopen a closed plot."""
    return await update_plot(db, plot_id, status=STATUS_OPEN)


async def link_scene(db, plot_id: int, scene_id: int) -> bool:
    """Link a scene to a plot. Returns True if newly linked, False if already linked."""
    existing = await db.fetchall(
        "SELECT 1 FROM plot_scenes WHERE plot_id=? AND scene_id=?",
        (plot_id, scene_id)
    )
    if existing:
        return False
    now = time.time()
    await db.execute(
        "INSERT INTO plot_scenes (plot_id, scene_id, linked_at) VALUES (?, ?, ?)",
        (plot_id, scene_id, now)
    )
    # Touch plot updated_at
    await db.execute(
        "UPDATE plots SET updated_at = ? WHERE id = ?", (now, plot_id)
    )
    await db.commit()
    log.info("Scene #%d linked to plot #%d", scene_id, plot_id)
    return True


async def unlink_scene(db, plot_id: int, scene_id: int) -> bool:
    """Unlink a scene from a plot. Returns True if removed, False if not found."""
    existing = await db.fetchall(
        "SELECT 1 FROM plot_scenes WHERE plot_id=? AND scene_id=?",
        (plot_id, scene_id)
    )
    if not existing:
        return False
    await db.execute(
        "DELETE FROM plot_scenes WHERE plot_id=? AND scene_id=?",
        (plot_id, scene_id)
    )
    await db.execute(
        "UPDATE plots SET updated_at = ? WHERE id = ?", (time.time(), plot_id)
    )
    await db.commit()
    log.info("Scene #%d unlinked from plot #%d", scene_id, plot_id)
    return True


async def get_plot_scenes(db, plot_id: int) -> list:
    """Get all scenes linked to a plot, with basic info."""
    rows = await db.fetchall(
        """SELECT s.id, s.title, s.scene_type, s.location, s.status,
                  s.started_at, s.completed_at, s.summary
           FROM scenes s
           JOIN plot_scenes ps ON ps.scene_id = s.id
           WHERE ps.plot_id = ?
           ORDER BY s.started_at ASC""",
        (plot_id,)
    )
    result = []
    for r in rows:
        d = dict(r)
        # Get participant names
        parts = await db.fetchall(
            """SELECT c.name FROM scene_participants sp
               JOIN characters c ON c.id = sp.char_id
               WHERE sp.scene_id = ?""",
            (d["id"],)
        )
        d["participants"] = [p["name"] for p in parts]
        # Get pose count
        pc = await db.fetchall(
            "SELECT COUNT(*) as c FROM scene_poses WHERE scene_id = ?",
            (d["id"],)
        )
        d["pose_count"] = pc[0]["c"] if pc else 0
        result.append(d)
    return result


async def get_scene_count(db, plot_id: int) -> int:
    """Get number of scenes linked to a plot."""
    rows = await db.fetchall(
        "SELECT COUNT(*) as c FROM plot_scenes WHERE plot_id = ?",
        (plot_id,)
    )
    return rows[0]["c"] if rows else 0
