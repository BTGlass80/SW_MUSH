# -*- coding: utf-8 -*-
"""
REST API for the web portal.

Mounts on the existing aiohttp server under /api/portal/.
Provides read-only data endpoints for the portal frontend:
  - /api/portal/who        — online player list
  - /api/portal/news       — recent Director events
  - /api/portal/stats      — game statistics
  - /api/portal/characters — character directory (paginated)
  - /api/portal/character/{id} — character profile
  - /api/portal/scenes     — shared scene archive (paginated)
  - /api/portal/scene/{id} — scene detail + pose log
  - /api/portal/guides     — guide index
  - /api/portal/guide/{slug} — guide content
  - /api/portal/login      — authenticate → token
  - /api/portal/me         — authenticated user data
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from db.database import Database
    from server.session import SessionManager

log = logging.getLogger(__name__)


# ── Guide loader ────────────────────────────────────────────────────────────

# Guide metadata: (slug, title, order)
_GUIDE_INDEX: list[dict] = []
_GUIDE_CONTENT: dict[str, str] = {}  # slug → markdown content


def _load_guides() -> None:
    """Load guide markdown files from data/guides/ into memory."""
    global _GUIDE_INDEX, _GUIDE_CONTENT
    guides_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "guides"
    )
    if not os.path.isdir(guides_dir):
        log.warning("Guides directory not found: %s", guides_dir)
        return

    entries = []
    for fname in sorted(os.listdir(guides_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(guides_dir, fname)
        try:
            content = open(fpath, "r", encoding="utf-8").read()
        except Exception as e:
            log.warning("Failed to read guide %s: %s", fname, e)
            continue

        # Extract title from first # heading
        title = fname.replace(".md", "").replace("_", " ").title()
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Slug from filename: Guide_01_Core_Mechanics.md → core-mechanics
        slug = fname.replace(".md", "")
        # Strip leading Guide_NN_ prefix
        parts = slug.split("_", 2)
        if len(parts) >= 3 and parts[0].lower() == "guide" and parts[1].isdigit():
            order = int(parts[1])
            slug = parts[2].lower().replace("_", "-")
        else:
            order = 99
            slug = slug.lower().replace("_", "-")

        entries.append({"slug": slug, "title": title, "order": order})
        _GUIDE_CONTENT[slug] = content

    entries.sort(key=lambda e: e["order"])
    _GUIDE_INDEX = entries
    log.info("Portal: loaded %d guides", len(entries))


# ── Reference loader ────────────────────────────────────────────────────────

# Auto-generated rules reference, sourced from data/help/topics/*.md and
# data/help/commands/*.md. Each markdown file has YAML frontmatter
# (key, title, category, summary, aliases, see_also, tags, examples).
_REFERENCE_INDEX: dict = {}      # {"tree": {...}, "flat": [...]}
_REFERENCE_CONTENT: dict = {}    # slug → full entry dict


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file. Returns (meta, body).
    On any parse error, returns (empty dict, full original content)."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 3:].strip()
    try:
        import yaml
        meta = yaml.safe_load(fm_text) or {}
        if not isinstance(meta, dict):
            return {}, content
        return meta, body
    except Exception as e:
        log.warning("Reference: YAML parse error: %s", e)
        return {}, content


def _load_reference() -> None:
    """Load reference entries from data/help/topics/ and data/help/commands/.

    Builds two artifacts:
      _REFERENCE_INDEX: {"tree": {category: {entries, subcategories}}, "flat": [...]}
      _REFERENCE_CONTENT: {slug → full entry dict including body}

    Slug is the entry's key, lowercased. Look-up by alias is supported in
    the entry handler.
    """
    global _REFERENCE_INDEX, _REFERENCE_CONTENT
    base_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "help"
    )
    sources = [
        ("topics", os.path.join(base_dir, "topics")),
        ("commands", os.path.join(base_dir, "commands")),
    ]

    flat: list[dict] = []
    by_slug: dict[str, dict] = {}

    for source_kind, src_dir in sources:
        if not os.path.isdir(src_dir):
            continue
        for fname in sorted(os.listdir(src_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(src_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                log.warning("Reference: failed to read %s: %s", fname, e)
                continue
            meta, body = _parse_frontmatter(content)
            key = meta.get("key") if meta else None
            if not key:
                continue
            slug = str(key).lower().strip()
            entry = {
                "slug": slug,
                "key": key,
                "title": meta.get("title", key),
                "category": meta.get("category", "Uncategorized"),
                "summary": meta.get("summary", ""),
                "aliases": list(meta.get("aliases") or []),
                "see_also": list(meta.get("see_also") or []),
                "tags": list(meta.get("tags") or []),
                "examples": list(meta.get("examples") or []),
                "body": body,
                "source": source_kind,
            }
            flat.append(entry)
            by_slug[slug] = entry

    # Build category tree. Splits "Parent: Child" into parent + subcategory.
    tree: dict = {}
    for entry in flat:
        cat = entry["category"] or "Uncategorized"
        # "Rules: D6" → parent="Rules", sub="D6"
        if ": " in cat:
            parent, sub = cat.split(": ", 1)
            parent = parent.strip()
            sub = sub.strip()
        else:
            parent, sub = cat, None

        if parent not in tree:
            tree[parent] = {"entries": [], "subcategories": {}}
        slim = {
            "slug": entry["slug"],
            "key": entry["key"],
            "title": entry["title"],
            "summary": entry["summary"],
            "tags": entry["tags"],
        }
        if sub:
            if sub not in tree[parent]["subcategories"]:
                tree[parent]["subcategories"][sub] = {"entries": [], "subcategories": {}}
            tree[parent]["subcategories"][sub]["entries"].append(slim)
        else:
            tree[parent]["entries"].append(slim)

    # Stable sort: entries by key within each level
    def _sort_node(node):
        node["entries"].sort(key=lambda e: e["key"].lower())
        for sub in node["subcategories"].values():
            _sort_node(sub)
    for top in tree.values():
        _sort_node(top)

    _REFERENCE_INDEX = {"tree": tree, "flat": flat}
    _REFERENCE_CONTENT = by_slug
    log.info(
        "Portal: loaded %d reference entries across %d top-level categories",
        len(flat), len(tree)
    )


# ── Portal API class ────────────────────────────────────────────────────────

class PortalAPI:
    """REST API for the web portal. Registered on the aiohttp app."""

    def __init__(self, db, session_mgr, game=None):
        self._db = db
        self._session_mgr = session_mgr
        self._game = game
        self._start_time = time.time()

        # Load guides on init
        if not _GUIDE_INDEX:
            _load_guides()
        # Load reference (topics + commands) on init
        if not _REFERENCE_INDEX:
            _load_reference()

    def register_routes(self, app: web.Application) -> None:
        """Register all portal API routes on the aiohttp app."""
        app.router.add_get("/api/portal/who", self.handle_who)
        app.router.add_get("/api/portal/news", self.handle_news)
        app.router.add_get("/api/portal/stats", self.handle_stats)
        app.router.add_get("/api/portal/characters", self.handle_characters)
        app.router.add_get(
            "/api/portal/character/{char_id}", self.handle_character
        )
        app.router.add_get("/api/portal/scenes", self.handle_scenes)
        app.router.add_get(
            "/api/portal/scene/{scene_id}", self.handle_scene_detail
        )
        app.router.add_get("/api/portal/guides", self.handle_guides)
        app.router.add_get(
            "/api/portal/guide/{slug}", self.handle_guide_content
        )
        app.router.add_post("/api/portal/login", self.handle_login)
        app.router.add_get("/api/portal/me", self.handle_me)
        app.router.add_get("/api/portal/events", self.handle_events)
        app.router.add_get("/api/portal/plots", self.handle_plots)
        app.router.add_get(
            "/api/portal/plot/{plot_id}", self.handle_plot_detail
        )
        # Reference (auto-generated from data/help/*). Order matters: the
        # /search route MUST register before {slug} or aiohttp will match
        # "search" as a slug literal.
        app.router.add_get("/api/portal/reference", self.handle_reference_index)
        app.router.add_get("/api/portal/reference/search", self.handle_reference_search)
        app.router.add_get("/api/portal/reference/{slug}", self.handle_reference_entry)
        log.info("Portal API routes registered")

    # ── Helpers ──────────────────────────────────────────────────────────

    def _json(self, data: dict, status: int = 200) -> web.Response:
        return web.Response(
            text=json.dumps(data, default=str),
            content_type="application/json",
            status=status,
        )

    async def _optional_auth(self, request) -> Optional[int]:
        """Extract account_id from Authorization header if present."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        try:
            from server.api import verify_login_token
            return verify_login_token(token)
        except Exception:
            return None

    async def _get_zone_name(self, room_id: int) -> str:
        """Get the zone name for a room (for location area display)."""
        try:
            room = await self._db.get_room(room_id)
            if room and room.get("zone_id"):
                zone = await self._db.get_zone(room["zone_id"])
                if zone:
                    return zone.get("name", "Unknown")
        except Exception as _e:
            log.debug("silent except in server/web_portal.py:160: %s", _e, exc_info=True)
        return "Unknown"

    async def _fetchone(self, sql: str, params: tuple = ()):
        """
        Fetch a single row. Returns the first row from execute_fetchall or None.

        aiosqlite does not have an execute_fetchone method, so this wraps
        execute_fetchall and takes the first row. Kept as an instance method
        so call sites read as `await self._fetchone(...)`.
        """
        rows = await self._db.fetchall(sql, params)
        return rows[0] if rows else None

    # ── Who's Online ─────────────────────────────────────────────────────

    async def handle_who(self, request) -> web.Response:
        """GET /api/portal/who — online player list."""
        players = []
        for s in self._session_mgr.all:
            if not s.is_in_game or not s.character:
                continue
            char = s.character
            idle_secs = int(time.time() - s.last_activity)

            # Get zone name for location area (not specific room)
            zone_name = await self._get_zone_name(
                char.get("room_id", 0)
            )

            # Get faction from org_memberships if available
            faction = "Neutral"
            try:
                attrs = char.get("attributes", "{}")
                if isinstance(attrs, str):
                    attrs = json.loads(attrs)
                faction = attrs.get("faction", "Neutral")
            except Exception as _e:
                log.debug("silent except in server/web_portal.py:198: %s", _e, exc_info=True)

            players.append({
                "name": char.get("name", "Unknown"),
                "species": char.get("species", "Human"),
                "location_area": zone_name,
                "idle_seconds": idle_secs,
                "faction": faction,
            })

        return self._json({
            "online": players,
            "count": len(players),
            "uptime_seconds": int(time.time() - self._start_time),
        })

    # ── News Feed ────────────────────────────────────────────────────────

    async def handle_news(self, request) -> web.Response:
        """GET /api/portal/news — recent Director events."""
        limit = min(int(request.query.get("limit", "20")), 50)
        try:
            rows = await self._db.fetchall(
                """SELECT timestamp, event_type, summary
                   FROM director_log
                   WHERE event_type IN ('news', 'era_milestone',
                                        'faction_turn', 'world_event')
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            events = []
            for r in rows:
                row = dict(r)
                events.append({
                    "text": row.get("summary", ""),
                    "timestamp": row.get("timestamp", ""),
                    "event_type": row.get("event_type", ""),
                })
            return self._json({"events": events})
        except Exception as e:
            log.warning("Portal news query failed: %s", e)
            return self._json({"events": []})

    # ── Game Stats ───────────────────────────────────────────────────────

    async def handle_stats(self, request) -> web.Response:
        """GET /api/portal/stats — game statistics."""
        online_count = sum(
            1 for s in self._session_mgr.all
            if s.is_in_game and s.character
        )
        try:
            char_count = await self._fetchone(
                "SELECT COUNT(*) as c FROM characters WHERE is_active = 1"
            )
            room_count = await self._fetchone(
                "SELECT COUNT(*) as c FROM rooms"
            )
            scene_count = await self._fetchone(
                "SELECT COUNT(*) as c FROM scenes WHERE status = 'shared'"
            )
            try:
                plot_count = await self._fetchone(
                    "SELECT COUNT(*) as c FROM plots WHERE status = 'open'"
                )
            except Exception:
                plot_count = {"c": 0}
        except Exception:
            char_count = {"c": 0}
            room_count = {"c": 0}
            scene_count = {"c": 0}
            plot_count = {"c": 0}

        return self._json({
            "online": online_count,
            "characters": dict(char_count).get("c", 0) if char_count else 0,
            "rooms": dict(room_count).get("c", 0) if room_count else 0,
            "shared_scenes": dict(scene_count).get("c", 0) if scene_count else 0,
            "open_plots": dict(plot_count).get("c", 0) if plot_count else 0,
            "uptime_seconds": int(time.time() - self._start_time),
            "planets": 4,
            "ship_templates": 19,
        })

    # ── Character Directory ──────────────────────────────────────────────

    async def handle_characters(self, request) -> web.Response:
        """GET /api/portal/characters — paginated character directory."""
        page = max(1, int(request.query.get("page", "1")))
        per_page = min(50, max(1, int(request.query.get("per_page", "20"))))
        species_filter = request.query.get("species", "").strip()
        faction_filter = request.query.get("faction", "").strip()
        search = request.query.get("q", "").strip().lower()

        offset = (page - 1) * per_page

        # Build query
        where = ["is_active = 1"]
        params = []
        if species_filter:
            where.append("species = ?")
            params.append(species_filter)
        if search:
            where.append("LOWER(name) LIKE ?")
            params.append(f"%{search}%")

        where_clause = " AND ".join(where)

        try:
            # Count total
            count_row = await self._fetchone(
                f"SELECT COUNT(*) as c FROM characters WHERE {where_clause}",
                tuple(params),
            )
            total = dict(count_row).get("c", 0) if count_row else 0

            # Fetch page
            rows = await self._db.fetchall(
                f"""SELECT id, name, species, template, description
                    FROM characters WHERE {where_clause}
                    ORDER BY name ASC LIMIT ? OFFSET ?""",
                tuple(params) + (per_page, offset),
            )

            # Check which characters are online
            online_ids = set()
            for s in self._session_mgr.all:
                if s.is_in_game and s.character:
                    online_ids.add(s.character.get("id"))

            # Get faction for each character
            characters = []
            for r in rows:
                row = dict(r)
                desc = row.get("description", "") or ""
                # Truncate description for snippet
                snippet = desc[:120] + "..." if len(desc) > 120 else desc

                # Faction from attributes
                char_faction = "Neutral"
                try:
                    full_char = await self._db.get_character(row["id"])
                    if full_char:
                        attrs = full_char.get("attributes", "{}")
                        if isinstance(attrs, str):
                            attrs = json.loads(attrs)
                        char_faction = attrs.get("faction", "Neutral")
                except Exception as _e:
                    log.debug("silent except in server/web_portal.py:346: %s", _e, exc_info=True)

                # Apply faction filter
                if faction_filter and char_faction != faction_filter:
                    continue

                characters.append({
                    "id": row["id"],
                    "name": row["name"],
                    "species": row.get("species", "Human"),
                    "template": row.get("template", ""),
                    "faction": char_faction,
                    "description_snippet": snippet,
                    "online": row["id"] in online_ids,
                })

            return self._json({
                "characters": characters,
                "total": total,
                "page": page,
                "per_page": per_page,
            })
        except Exception as e:
            log.warning("Portal characters query failed: %s", e)
            return self._json({
                "characters": [], "total": 0,
                "page": 1, "per_page": per_page,
            })

    # ── Character Profile ────────────────────────────────────────────────

    async def handle_character(self, request) -> web.Response:
        """GET /api/portal/character/{char_id} — character profile."""
        try:
            char_id = int(request.match_info["char_id"])
        except (ValueError, KeyError):
            return self._json({"error": "Invalid character ID"}, 400)

        char = await self._db.get_character(char_id)
        if not char or not char.get("is_active"):
            return self._json({"error": "Character not found"}, 404)

        # Public data
        profile = {
            "id": char["id"],
            "name": char.get("name", "Unknown"),
            "species": char.get("species", "Human"),
            "template": char.get("template", ""),
            "description": char.get("description", ""),
        }

        # Parse attributes for public fields
        attrs = char.get("attributes", "{}")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}

        profile["faction"] = attrs.get("faction", "Neutral")

        # Scars
        scars = attrs.get("scars", [])
        if isinstance(scars, list):
            profile["scars"] = [s.get("text", str(s)) if isinstance(s, dict) else str(s) for s in scars[:10]]
        else:
            profile["scars"] = []

        # Background from pc_narrative
        try:
            narrative = await self._fetchone(
                "SELECT background FROM pc_narrative WHERE character_id = ?",
                (char_id,),
            )
            if narrative:
                profile["background"] = dict(narrative).get("background", "")
            else:
                profile["background"] = ""
        except Exception:
            profile["background"] = ""

        # Faction membership
        try:
            membership = await self._fetchone(
                """SELECT o.name as org_name, r.title as rank_title
                   FROM org_memberships m
                   JOIN organizations o ON m.org_id = o.id
                   LEFT JOIN org_ranks r ON m.rank_id = r.id
                   WHERE m.character_id = ? AND o.org_type = 'faction'""",
                (char_id,),
            )
            if membership:
                m = dict(membership)
                profile["faction_membership"] = {
                    "name": m.get("org_name", ""),
                    "rank": m.get("rank_title", ""),
                }
        except Exception as _e:
            log.debug("silent except in server/web_portal.py:444: %s", _e, exc_info=True)

        # Achievement count
        try:
            ach_row = await self._fetchone(
                """SELECT COUNT(*) as c FROM character_achievements
                   WHERE character_id = ? AND completed = 1""",
                (char_id,),
            )
            profile["achievement_count"] = dict(ach_row).get("c", 0) if ach_row else 0
        except Exception:
            profile["achievement_count"] = 0

        # Scene count
        try:
            sc_row = await self._fetchone(
                """SELECT COUNT(*) as c FROM scene_participants
                   WHERE char_id = ?""",
                (char_id,),
            )
            profile["scene_count"] = dict(sc_row).get("c", 0) if sc_row else 0
        except Exception:
            profile["scene_count"] = 0

        # Online status
        online = False
        for s in self._session_mgr.all:
            if s.is_in_game and s.character and s.character.get("id") == char_id:
                online = True
                break
        profile["online"] = online

        # Private data — only if authenticated as owner
        account_id = await self._optional_auth(request)
        if account_id and char.get("account_id") == account_id:
            profile["is_own"] = True
            profile["credits"] = char.get("credits", 0)

            # Skills and attributes
            char_sheet = char.get("char_sheet_json", "{}")
            if isinstance(char_sheet, str):
                try:
                    char_sheet = json.loads(char_sheet)
                except Exception:
                    char_sheet = {}
            profile["attributes"] = char_sheet.get("attributes", {})
            profile["skills"] = char_sheet.get("skills", {})
            profile["character_points"] = char.get("character_points", 0)

            # Reputation standings
            try:
                from engine.organizations import get_all_faction_reps
                reps = await get_all_faction_reps(self._db, char_id)
                profile["reputation"] = reps
            except Exception:
                profile["reputation"] = {}

        return self._json(profile)

    # ── Scene Archive ────────────────────────────────────────────────────

    async def handle_scenes(self, request) -> web.Response:
        """GET /api/portal/scenes — shared scene archive."""
        page = max(1, int(request.query.get("page", "1")))
        per_page = min(50, max(1, int(request.query.get("per_page", "20"))))
        scene_type = request.query.get("type", "").strip()
        offset = (page - 1) * per_page

        try:
            where = ["status = 'shared'"]
            params = []
            if scene_type:
                where.append("scene_type = ?")
                params.append(scene_type)

            where_clause = " AND ".join(where)

            count_row = await self._fetchone(
                f"SELECT COUNT(*) as c FROM scenes WHERE {where_clause}",
                tuple(params),
            )
            total = dict(count_row).get("c", 0) if count_row else 0

            rows = await self._db.fetchall(
                f"""SELECT id, title, scene_type, location, started_at,
                           completed_at, summary
                    FROM scenes WHERE {where_clause}
                    ORDER BY completed_at DESC LIMIT ? OFFSET ?""",
                tuple(params) + (per_page, offset),
            )

            scenes = []
            for r in rows:
                row = dict(r)
                scene_id = row["id"]

                # Get participants
                parts = await self._db.fetchall(
                    """SELECT c.name FROM scene_participants sp
                       JOIN characters c ON sp.char_id = c.id
                       WHERE sp.scene_id = ?""",
                    (scene_id,),
                )
                participant_names = [dict(p)["name"] for p in parts]

                # Pose count
                pc_row = await self._fetchone(
                    "SELECT COUNT(*) as c FROM scene_poses WHERE scene_id = ?",
                    (scene_id,),
                )
                pose_count = dict(pc_row).get("c", 0) if pc_row else 0

                scenes.append({
                    "id": scene_id,
                    "title": row.get("title", "Untitled"),
                    "scene_type": row.get("scene_type", ""),
                    "location": row.get("location", ""),
                    "started_at": row.get("started_at", ""),
                    "completed_at": row.get("completed_at", ""),
                    "summary": row.get("summary", ""),
                    "participants": participant_names,
                    "pose_count": pose_count,
                })

            return self._json({
                "scenes": scenes,
                "total": total,
                "page": page,
                "per_page": per_page,
            })
        except Exception as e:
            log.warning("Portal scenes query failed: %s", e)
            return self._json({
                "scenes": [], "total": 0,
                "page": 1, "per_page": per_page,
            })

    async def handle_scene_detail(self, request) -> web.Response:
        """GET /api/portal/scene/{scene_id} — scene detail + pose log."""
        try:
            scene_id = int(request.match_info["scene_id"])
        except (ValueError, KeyError):
            return self._json({"error": "Invalid scene ID"}, 400)

        try:
            scene = await self._fetchone(
                """SELECT id, title, scene_type, location, summary,
                          started_at, completed_at, status
                   FROM scenes WHERE id = ?""",
                (scene_id,),
            )
            if not scene:
                return self._json({"error": "Scene not found"}, 404)

            scene = dict(scene)
            if scene.get("status") != "shared":
                return self._json({"error": "Scene not shared"}, 404)

            # Participants
            parts = await self._db.fetchall(
                """SELECT c.name FROM scene_participants sp
                   JOIN characters c ON sp.char_id = c.id
                   WHERE sp.scene_id = ?""",
                (scene_id,),
            )

            # Poses
            poses = await self._db.fetchall(
                """SELECT sp.pose_type, sp.content, sp.created_at,
                          c.name as character_name
                   FROM scene_poses sp
                   LEFT JOIN characters c ON sp.char_id = c.id
                   WHERE sp.scene_id = ?
                   ORDER BY sp.created_at ASC""",
                (scene_id,),
            )

            return self._json({
                "id": scene["id"],
                "title": scene.get("title", "Untitled"),
                "scene_type": scene.get("scene_type", ""),
                "location": scene.get("location", ""),
                "summary": scene.get("summary", ""),
                "started_at": scene.get("started_at", ""),
                "completed_at": scene.get("completed_at", ""),
                "participants": [dict(p)["name"] for p in parts],
                "poses": [
                    {
                        "character": dict(p).get("character_name", "System"),
                        "type": dict(p).get("pose_type", ""),
                        "content": dict(p).get("content", ""),
                        "timestamp": dict(p).get("created_at", ""),
                    }
                    for p in poses
                ],
            })
        except Exception as e:
            log.warning("Portal scene detail failed: %s", e)
            return self._json({"error": "Failed to load scene"}, 500)

    # ── Guides ───────────────────────────────────────────────────────────

    async def handle_guides(self, request) -> web.Response:
        """GET /api/portal/guides — guide index."""
        return self._json({"guides": _GUIDE_INDEX})

    async def handle_guide_content(self, request) -> web.Response:
        """GET /api/portal/guide/{slug} — guide markdown content."""
        slug = request.match_info.get("slug", "")
        content = _GUIDE_CONTENT.get(slug)
        if content is None:
            return self._json({"error": "Guide not found"}, 404)

        # Find title from index
        title = slug.replace("-", " ").title()
        for g in _GUIDE_INDEX:
            if g["slug"] == slug:
                title = g["title"]
                break

        return self._json({"slug": slug, "title": title, "content": content})

    # ── Reference (auto-generated rules reference) ───────────────────────

    async def handle_reference_index(self, request) -> web.Response:
        """GET /api/portal/reference — category tree of all reference entries."""
        return self._json({
            "tree": _REFERENCE_INDEX.get("tree", {}),
        })

    async def handle_reference_entry(self, request) -> web.Response:
        """GET /api/portal/reference/{slug} — full entry detail.

        Falls back to alias lookup if direct slug lookup misses, so that
        see-also chips like 'attrs' (aliased to 'attributes') resolve.
        """
        slug = (request.match_info.get("slug", "") or "").lower().strip()
        if not slug:
            return self._json({"error": "No slug specified"}, 400)
        entry = _REFERENCE_CONTENT.get(slug)
        if not entry:
            # Try alias resolution — slug might be "attrs" pointing at "attributes"
            for e in _REFERENCE_INDEX.get("flat", []):
                if any(slug == a.lower() for a in e.get("aliases", [])):
                    entry = e
                    break
        if not entry:
            return self._json({"error": "Reference entry not found"}, 404)
        return self._json(entry)

    async def handle_reference_search(self, request) -> web.Response:
        """GET /api/portal/reference/search?q=...&limit=N — keyword search.

        Scoring: key match > title match > alias match > summary > tags > body.
        Returns up to `limit` (default 20, max 100) results.
        """
        q = (request.query.get("q", "") or "").strip().lower()
        try:
            limit = int(request.query.get("limit", "20"))
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(100, limit))
        if not q:
            return self._json({"results": [], "total": 0})

        scored = []
        for e in _REFERENCE_INDEX.get("flat", []):
            score = 0
            if q in e["key"].lower():                                  score += 10
            if q in e["title"].lower():                                score += 5
            if any(q in (a or "").lower() for a in e.get("aliases", [])):  score += 4
            if q in (e.get("summary") or "").lower():                  score += 3
            if any(q in (t or "").lower() for t in e.get("tags", [])): score += 2
            if q in (e.get("body") or "").lower():                     score += 1
            if score > 0:
                scored.append((score, {
                    "slug":     e["slug"],
                    "key":      e["key"],
                    "title":    e["title"],
                    "summary":  e["summary"],
                    "category": e["category"],
                    "tags":     e["tags"],
                }))
        scored.sort(key=lambda r: -r[0])
        return self._json({
            "results": [r[1] for r in scored[:limit]],
            "total":   len(scored),
        })

    # ── Authentication ───────────────────────────────────────────────────

    async def handle_events(self, request) -> web.Response:
        """GET /api/portal/events — upcoming events list."""
        try:
            from engine.events import get_all_events, get_signup_count, format_event_time
            include_past = request.query.get("past", "0") == "1"
            events = await get_all_events(self._db, limit=30, include_past=include_past)
            result = []
            for ev in events:
                count = await get_signup_count(self._db, ev["id"])
                result.append({
                    "id": ev["id"],
                    "title": ev["title"],
                    "description": ev.get("description", ""),
                    "location": ev.get("location", ""),
                    "creator_name": ev["creator_name"],
                    "status": ev["status"],
                    "scheduled_at": ev["scheduled_at"],
                    "signup_count": count,
                })
            return self._json({"events": result, "total": len(result)})
        except Exception as e:
            log.warning("Portal /events failed: %s", e)
            return self._json({"events": [], "total": 0})

    # ── Plots ────────────────────────────────────────────────────────

    async def handle_plots(self, request) -> web.Response:
        """GET /api/portal/plots — plot/story arc list."""
        try:
            from engine.plots import get_all_plots, get_scene_count
            include_closed = request.query.get("closed", "1") == "1"
            plots = await get_all_plots(
                self._db, limit=50, include_closed=include_closed
            )
            result = []
            for p in plots:
                sc_count = await get_scene_count(self._db, p["id"])
                result.append({
                    "id": p["id"],
                    "title": p["title"],
                    "summary": p.get("summary", ""),
                    "creator_name": p["creator_name"],
                    "status": p["status"],
                    "created_at": p["created_at"],
                    "updated_at": p["updated_at"],
                    "scene_count": sc_count,
                })
            return self._json({"plots": result, "total": len(result)})
        except Exception as e:
            log.warning("Portal /plots failed: %s", e)
            return self._json({"plots": [], "total": 0})

    async def handle_plot_detail(self, request) -> web.Response:
        """GET /api/portal/plot/{plot_id} — plot detail with linked scenes."""
        try:
            plot_id = int(request.match_info["plot_id"])
        except (ValueError, KeyError):
            return self._json({"error": "Invalid plot ID"}, 400)

        try:
            from engine.plots import get_plot, get_plot_scenes
            p = await get_plot(self._db, plot_id)
            if not p:
                return self._json({"error": "Plot not found"}, 404)

            scenes = await get_plot_scenes(self._db, plot_id)
            scene_list = []
            for s in scenes:
                scene_list.append({
                    "id": s["id"],
                    "title": s.get("title", ""),
                    "scene_type": s.get("scene_type", ""),
                    "location": s.get("location", ""),
                    "status": s.get("status", ""),
                    "started_at": s.get("started_at"),
                    "completed_at": s.get("completed_at"),
                    "summary": s.get("summary", ""),
                    "participants": s.get("participants", []),
                    "pose_count": s.get("pose_count", 0),
                })

            return self._json({
                "id": p["id"],
                "title": p["title"],
                "summary": p.get("summary", ""),
                "creator_name": p["creator_name"],
                "status": p["status"],
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
                "scenes": scene_list,
            })
        except Exception as e:
            log.warning("Portal /plot/%s failed: %s", plot_id, e)
            return self._json({"error": "Failed to load plot"}, 500)

    async def handle_login(self, request) -> web.Response:
        """POST /api/portal/login — authenticate and return token."""
        try:
            body = await request.json()
        except Exception:
            return self._json({"error": "Invalid JSON"}, 400)

        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()

        if not username or not password:
            return self._json({"error": "Username and password required"}, 400)

        try:
            # Use the same bcrypt-based authenticate() as the game client
            account = await self._db.authenticate(username, password)
            if not account:
                return self._json({"error": "Invalid credentials"}, 401)

            # Generate token (24hr TTL for portal sessions)
            from server.api import create_login_token
            token = create_login_token(account["id"], ttl=86400)

            # Get account's characters
            chars = await self._db.get_characters(account["id"])
            char_list = [
                {"id": c["id"], "name": c["name"]}
                for c in chars if c.get("is_active")
            ]

            return self._json({
                "token": token,
                "account_id": account["id"],
                "characters": char_list,
            })
        except Exception as e:
            log.warning("Portal login failed: %s", e)
            return self._json({"error": "Login failed"}, 500)

    async def handle_me(self, request) -> web.Response:
        """GET /api/portal/me — authenticated user's own data."""
        account_id = await self._optional_auth(request)
        if not account_id:
            return self._json({"error": "Invalid or expired token"}, 401)

        try:
            chars = await self._db.get_characters(account_id)
            online_ids = set()
            if self._session_mgr:
                for s in self._session_mgr.all():
                    if hasattr(s, 'character') and s.character:
                        online_ids.add(s.character['id'])

            char_list = []
            for c in chars:
                faction = "Neutral"
                try:
                    memberships = await self._db.fetchall(
                        "SELECT o.name FROM org_memberships m JOIN organizations o ON m.org_id=o.id WHERE m.char_id=?",
                        (c["id"],)
                    )
                    if memberships:
                        faction = memberships[0]["name"]
                except Exception as _e:
                    log.debug("silent except in server/web_portal.py:827: %s", _e, exc_info=True)
                char_list.append({
                    "id": c["id"],
                    "name": c["name"],
                    "species": c.get("species", "Human"),
                    "template": c.get("template", "Custom"),
                    "faction": faction,
                    "credits": c.get("credits", 0),
                    "character_points": c.get("character_points", 0),
                    "online": c["id"] in online_ids,
                })
            return self._json({
                "account_id": account_id,
                "characters": char_list,
            })
        except Exception as e:
            log.warning("Portal /me failed: %s", e)
            return self._json({"error": "Failed"}, 500)
