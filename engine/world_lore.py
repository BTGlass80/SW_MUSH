# -*- coding: utf-8 -*-
"""
engine/world_lore.py — World Lore System (Lorebook Pattern) for SW_MUSH.

Keyword-triggered context injection for Director AI and NPC dialogue.
Instead of carrying the entire world state in every prompt, relevant
lore entries are dynamically loaded based on current game context.

Design source: competitive_analysis_feature_designs_v1.md §C
Expanded: sourcebook_mining_crafting_exp_design_v1.md §2

Schema: world_lore table with keyword matching + zone scope filtering.
Cache: In-memory, refreshed every 5 minutes from DB.
"""

from __future__ import annotations
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────

WORLD_LORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_lore (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    keywords    TEXT NOT NULL,
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    zone_scope  TEXT,
    priority    INTEGER DEFAULT 5,
    active      INTEGER DEFAULT 1,
    created_at  REAL NOT NULL,
    updated_at  REAL
);

CREATE INDEX IF NOT EXISTS idx_world_lore_active ON world_lore(active);
"""


async def ensure_lore_schema(db) -> None:
    """Create world_lore table if it doesn't exist. Idempotent."""
    try:
        for stmt in WORLD_LORE_SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
        log.info("[world_lore] Schema ensured.")
    except Exception as e:
        log.warning("[world_lore] Schema creation failed: %s", e)


# ── Cache ─────────────────────────────────────────────────────────────────────

_lore_cache: list[dict] = []
_cache_ts: float = 0.0
_CACHE_TTL = 300.0  # 5 minutes


async def _refresh_cache(db) -> list[dict]:
    """Load all active lore entries from DB into memory cache."""
    global _lore_cache, _cache_ts
    try:
        rows = await db.fetchall(
            "SELECT * FROM world_lore WHERE active = 1 ORDER BY priority DESC"
        )
        _lore_cache = [dict(r) for r in rows]
        _cache_ts = time.time()
        log.debug("[world_lore] Cache refreshed: %d entries", len(_lore_cache))
    except Exception as e:
        log.warning("[world_lore] Cache refresh failed: %s", e)
        if not _lore_cache:
            _lore_cache = []
    return _lore_cache


async def _get_entries(db) -> list[dict]:
    """Get cached lore entries, refreshing if stale."""
    if time.time() - _cache_ts > _CACHE_TTL or not _lore_cache:
        return await _refresh_cache(db)
    return _lore_cache


def clear_cache() -> None:
    """Force cache refresh on next access."""
    global _cache_ts
    _cache_ts = 0.0


# ── Keyword Matching ──────────────────────────────────────────────────────────

async def get_relevant_lore(
    db,
    context_text: str,
    zone_id: str = "",
    max_entries: int = 5,
    max_chars: int = 1200,
) -> list[dict]:
    """Find lore entries whose keywords match the context text.

    Args:
        db: Database instance.
        context_text: Text to scan for keyword matches (player dialogue,
                      zone names, faction names, recent events).
        zone_id: Current zone for scope filtering. Entries with zone_scope
                 only match if zone_id is in their scope list.
        max_entries: Maximum number of entries to return.
        max_chars: Maximum total content characters (rough token proxy).

    Returns:
        List of matched lore entry dicts, sorted by priority (highest first).
    """
    entries = await _get_entries(db)
    if not entries or not context_text:
        return []

    context_lower = context_text.lower()
    matches = []

    for entry in entries:
        # Zone scope check
        scope = entry.get("zone_scope", "")
        if scope:
            scope_zones = [z.strip().lower() for z in scope.split(",")]
            if zone_id and zone_id.lower() not in scope_zones:
                continue
            elif not zone_id:
                # If no zone_id provided, skip zone-scoped entries
                continue

        # Keyword match — any keyword present in context
        raw_kw = entry.get("keywords", "")
        keywords = [k.strip().lower() for k in raw_kw.split(",") if k.strip()]
        match_count = sum(1 for kw in keywords if kw in context_lower)
        if match_count > 0:
            matches.append((match_count, entry))

    # Sort by priority (desc), then match count (desc)
    matches.sort(key=lambda x: (x[1].get("priority", 5), x[0]), reverse=True)

    # Fit within character budget
    result = []
    total_chars = 0
    for _mc, entry in matches:
        content_len = len(entry.get("content", ""))
        if total_chars + content_len > max_chars:
            if result:
                break  # Already have some entries, stop
            # First entry — include even if over budget (truncated)
        result.append(entry)
        total_chars += content_len
        if len(result) >= max_entries:
            break

    return result


def format_lore_block(entries: list[dict], label: str = "WORLD CONTEXT") -> str:
    """Format matched lore entries into a prompt injection block.

    Returns an empty string if no entries.
    """
    if not entries:
        return ""
    lines = [f"\n{label}:"]
    for e in entries:
        cat = e.get("category", "general").upper()
        title = e.get("title", "")
        content = e.get("content", "")
        lines.append(f"  [{cat}] {title}: {content}")
    return "\n".join(lines)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def add_lore(
    db,
    title: str,
    keywords: str,
    content: str,
    category: str = "general",
    zone_scope: str = "",
    priority: int = 5,
) -> dict:
    """Add a new lore entry. Returns {ok, msg, id}."""
    if not title or not keywords or not content:
        return {"ok": False, "msg": "Title, keywords, and content are required."}
    if len(content) > 1000:
        return {"ok": False, "msg": "Content must be under 1000 characters."}
    if len(title) > 100:
        return {"ok": False, "msg": "Title must be under 100 characters."}

    now = time.time()
    try:
        cursor = await db.execute(
            "INSERT INTO world_lore (title, keywords, content, category, "
            "zone_scope, priority, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (title, keywords.lower(), content, category.lower(),
             zone_scope or None, priority, now, now),
        )
        await db.commit()
        clear_cache()
        return {"ok": True, "msg": f"Lore '{title}' added.", "id": cursor.lastrowid}
    except Exception as e:
        log.warning("[world_lore] add_lore failed: %s", e)
        return {"ok": False, "msg": f"Database error: {e}"}


async def edit_lore(
    db,
    lore_id: int,
    **kwargs,
) -> dict:
    """Update fields on an existing lore entry."""
    allowed = {"title", "keywords", "content", "category", "zone_scope",
               "priority", "active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"ok": False, "msg": "No valid fields to update."}

    updates["updated_at"] = time.time()
    if "keywords" in updates:
        updates["keywords"] = updates["keywords"].lower()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [lore_id]

    try:
        await db.execute(
            f"UPDATE world_lore SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
        clear_cache()
        return {"ok": True, "msg": f"Lore #{lore_id} updated."}
    except Exception as e:
        log.warning("[world_lore] edit_lore failed: %s", e)
        return {"ok": False, "msg": f"Database error: {e}"}


async def disable_lore(db, lore_id: int) -> dict:
    """Deactivate a lore entry (soft delete)."""
    return await edit_lore(db, lore_id, active=0)


async def search_lore(db, query: str, include_inactive: bool = False) -> list[dict]:
    """Search lore by title or keywords."""
    where = "" if include_inactive else "AND active = 1"
    try:
        rows = await db.fetchall(
            f"SELECT * FROM world_lore WHERE "
            f"(LOWER(title) LIKE ? OR LOWER(keywords) LIKE ?) {where} "
            f"ORDER BY priority DESC LIMIT 20",
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("[world_lore] search failed: %s", e)
        return []


async def get_all_lore(db, include_inactive: bool = False) -> list[dict]:
    """Get all lore entries."""
    where = "WHERE active = 1" if not include_inactive else ""
    try:
        rows = await db.fetchall(
            f"SELECT * FROM world_lore {where} ORDER BY priority DESC, id ASC"
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("[world_lore] get_all failed: %s", e)
        return []




async def seed_lore(db, era: Optional[str] = None) -> int:
    """Insert seed lore entries from `data/worlds/<era>/lore.yaml`,
    skipping any whose title already exists. Idempotent: safe to
    re-run after adding new lore entries to the YAML.

    Returns the count of newly inserted entries.

    F.6a.7 Phase 2 (Apr 29 2026) deleted the SEED_ENTRIES literal
    (~490 lines, 61 entries) — GCW lore now lives exclusively in
    `data/worlds/gcw/lore.yaml`. The literal had been retained as
    a transitional fallback during F.6a.{1-6}; once the byte-equivalence
    tests proved the YAML matches the literal exactly and Phase 1
    wired production boot to pass an explicit era, the literal
    became dead code.

    Backward-compat: when `era` is None, defaults to "gcw" so any
    existing caller that doesn't pass an era still seeds GCW lore.
    The F.6a.{2,3}-int byte-equivalence test fixtures that pass
    `era=None` continue to exercise the same data path they always
    did — sourced from YAML now instead of an in-Python literal,
    but with byte-equivalent results.

    On YAML load failure (missing file, parse error, validation
    error), this function logs an ERROR and returns 0 — there is no
    longer an in-Python fallback. A real boot expects the YAML to
    be present; if it isn't, the lore system stays empty rather
    than silently shipping outdated literal data.
    """
    if era is None:
        # F.6a.7 Phase 2: era=None defaults to GCW (was the legacy
        # SEED_ENTRIES path pre-Phase-2).
        era = "gcw"

    try:
        from pathlib import Path
        from engine.world_loader import load_era_manifest, load_lore as _load_lore
        manifest = load_era_manifest(Path("data") / "worlds" / era)
        corpus = _load_lore(manifest)
    except Exception as e:
        log.error(
            "[world_lore] Era-aware seed for %r failed at load (%s); "
            "no in-Python fallback exists post-F.6a.7 Phase 2. "
            "Lore table will be empty until the YAML loads cleanly.",
            era, e,
        )
        return 0

    if corpus is None:
        log.error(
            "[world_lore] Era %r has no lore content_ref; "
            "lore table will be empty until the era manifest is fixed.",
            era,
        )
        return 0

    if corpus.report.errors:
        log.error(
            "[world_lore] Era %r lore.yaml has %d validation error(s); "
            "lore table will be empty until the YAML is fixed. First: %s",
            era, len(corpus.report.errors), corpus.report.errors[0],
        )
        return 0

    return await seed_lore_from_corpus(db, corpus)


async def seed_lore_from_corpus(db, corpus) -> int:
    """Seed the world_lore table from a LoreCorpus produced by F.6a.1.

    Idempotent: skips any entry whose title already exists. Returns the
    count of newly inserted entries. The corpus's `.report.errors` is
    NOT re-checked here — caller is responsible for deciding whether
    to seed a corpus with errors. (`seed_lore(db, era=...)` falls back
    to SEED_ENTRIES rather than seeding a broken corpus; tools that
    want to force-seed a partial corpus can call this function directly.)
    """
    entries = [
        {
            "title":      e.title,
            "keywords":   e.keywords,
            "content":    e.content,
            "category":   e.category or "general",
            "zone_scope": e.zone_scope,
            "priority":   e.priority,
        }
        for e in corpus.entries
    ]
    return await _seed_from_entries(db, entries)


async def _seed_from_entries(db, entries: list[dict]) -> int:
    """Insert each entry whose title isn't already in world_lore.

    Shared insertion path for both `seed_lore` (legacy SEED_ENTRIES) and
    `seed_lore_from_corpus` (F.6a.1 LoreCorpus). Idempotent. Returns
    the count of newly inserted entries.
    """
    try:
        rows = await db.fetchall("SELECT title FROM world_lore")
        existing_titles = {r["title"] for r in (rows or [])}

        count = 0
        now = time.time()
        for entry in entries:
            if entry["title"] in existing_titles:
                continue  # Already present, skip
            await db.execute(
                "INSERT INTO world_lore (title, keywords, content, category, "
                "zone_scope, priority, active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (entry["title"], entry["keywords"], entry["content"],
                 entry.get("category", "general"),
                 entry.get("zone_scope", None),
                 entry.get("priority", 5), now),
            )
            count += 1
        if count > 0:
            await db.commit()
            clear_cache()
        log.info("[world_lore] Seeded %d new lore entries (%d already existed).",
                 count, len(existing_titles))
        return count
    except Exception as e:
        log.warning("[world_lore] Seed failed: %s", e)
        return 0
