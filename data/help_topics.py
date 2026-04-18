# -*- coding: utf-8 -*-
"""
data/help_topics.py — Help system for SW_MUSH

Provides:
  - HelpEntry: a single help entry (command or topic), enriched with
    web-portal-friendly fields (summary, examples, tags, updated_at)
  - HelpManager: registry, lookup, search, auto-registration from
    commands, and markdown-file loading
  - TOPIC_HELP: legacy in-Python topic entries (kept empty by default
    — all topics now live in data/help/topics/*.md — but the hook
    remains so any entry declared here still registers)

Loading order at boot (orchestrated by HelpManager.load_all):
  1. auto_register_commands(registry) — one HelpEntry per BaseCommand,
     built from cmd.help_text/usage/aliases. Category derived from key
     prefix: ``@`` → Admin/Building, ``+`` → System, else Commands.
  2. register_topics() — any HelpEntry in TOPIC_HELP (legacy path)
  3. load_markdown_files() — scans data/help/ for *.md files with YAML
     frontmatter. Markdown entries OVERRIDE earlier registrations with
     the same key, which is how you enrich a command's help beyond the
     thin auto-registered version.

This override order is deliberate. A bare command with no markdown
file gets a usable (if minimal) help entry from its class attributes.
Authoring a ``data/help/commands/<key>.md`` file for that command
upgrades the entry with a real summary, examples, and rich body — no
code change needed. When you later refactor commands into the
``+command/argument`` form, the filenames and in-file ``key:`` values
track the rename; the portal reflects it automatically.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class HelpEntry:
    """A single help entry — covers both commands and topics.

    The first seven fields are the original shape and are what the
    in-game CLI reads. The tail of the dataclass (``summary``,
    ``examples``, ``tags``, ``updated_at``) is additive: older code
    that only looks at ``body``/``see_also``/``access_level`` keeps
    working unchanged. New surfaces (the web portal, future tag-based
    filters) consume the richer fields.
    """

    key: str                                   # Lookup key ("+sheet", "combat")
    title: str                                 # Display title
    category: str                              # Grouping ("Rules · Combat")
    body: str                                  # Markdown body. CLI renders
                                               #   as plaintext; web renders
                                               #   as HTML.
    aliases: list[str] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)
    access_level: int = 0                      # 0=anyone, 3=admin

    # ── Enriched fields (portal / future filtering) ─────────────────────
    summary: str = ""                          # 1–2 sentence blurb, shown
                                               #   in category tiles and
                                               #   search results
    examples: list[dict] = field(default_factory=list)
                                               #   Each dict: {cmd, description}
    tags: list[str] = field(default_factory=list)
                                               #   Free-form facets: ["combat",
                                               #   "newbie", "dangerous"]
    updated_at: str = ""                       # ISO-8601 string; empty when
                                               #   unknown


class HelpManager:
    """Registry for all help entries — commands and topics."""

    def __init__(self):
        self._entries: dict[str, HelpEntry] = {}   # key → HelpEntry
        self._alias_map: dict[str, str] = {}        # alias → key

        # Remember how the manager was configured so reload() can replay
        # the same source mix without the caller having to thread it
        # back through.
        self._registry = None                       # set by auto_register_commands
        self._markdown_roots: list[str] = []

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, entry: HelpEntry) -> None:
        """Register or overwrite a help entry.

        Overwrites are intentional — markdown files override the thin
        auto-registered version of a command, and hot-reload replays
        every registration.
        """
        k = entry.key.lower()
        # If we're overwriting, clear the old aliases first so stale
        # alias mappings don't linger.
        if k in self._entries:
            for old_alias in self._entries[k].aliases:
                self._alias_map.pop(old_alias.lower(), None)
        self._entries[k] = entry
        for alias in entry.aliases:
            self._alias_map[alias.lower()] = k

    # ── Lookup ───────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[HelpEntry]:
        """Resolve a name (key or alias) to an entry, or None."""
        name = name.lower().strip()
        if not name:
            return None
        if name in self._entries:
            return self._entries[name]
        if name in self._alias_map:
            return self._entries.get(self._alias_map[name])
        # Try with/without + prefix — a user typing ``+help sheet``
        # should find ``+sheet``.
        if not name.startswith("+"):
            alt = "+" + name
            if alt in self._entries:
                return self._entries[alt]
            if alt in self._alias_map:
                return self._entries.get(self._alias_map[alt])
        return None

    def search(self, keyword: str) -> list[HelpEntry]:
        """Search all entries for keyword matches, ranked.

        Rank (highest first): key exact, title match, alias match,
        tag match, summary match, body match. Within a rank tier the
        order is the insertion order of the registry — which is
        deterministic because markdown files are loaded in sorted
        order.
        """
        keyword = keyword.lower().strip()
        if not keyword:
            return []

        buckets: list[list[HelpEntry]] = [[] for _ in range(6)]
        seen: set[str] = set()

        for entry in self._entries.values():
            if entry.key in seen:
                continue
            k = entry.key.lower()
            t = entry.title.lower()
            als = [a.lower() for a in entry.aliases]
            tgs = [g.lower() for g in entry.tags]
            s = entry.summary.lower()
            b = entry.body.lower()

            if k == keyword:
                buckets[0].append(entry)
            elif keyword in t:
                buckets[1].append(entry)
            elif any(keyword == a or keyword in a for a in als):
                buckets[2].append(entry)
            elif any(keyword == g or keyword in g for g in tgs):
                buckets[3].append(entry)
            elif keyword in s:
                buckets[4].append(entry)
            elif keyword in b or keyword in k:
                buckets[5].append(entry)
            else:
                continue
            seen.add(entry.key)

        results: list[HelpEntry] = []
        for bucket in buckets:
            results.extend(bucket)
        return results

    # ── Introspection ────────────────────────────────────────────────────

    def categories(self) -> dict[str, list[HelpEntry]]:
        """Flat mapping: category name → list of entries in that category.

        Order preserved by insertion (Python 3.7+ dict semantics).
        Entries within a category are sorted by title for display
        stability.
        """
        cats: dict[str, list[HelpEntry]] = {}
        for entry in self._entries.values():
            cats.setdefault(entry.category, []).append(entry)
        for lst in cats.values():
            lst.sort(key=lambda e: e.title.lower())
        return cats

    def get_categories_tree(self) -> dict[str, dict]:
        """Hierarchical category tree.

        Categories may contain a separator (``·`` or ``/`` or ``:``) to
        express nesting — e.g. ``Rules · Combat`` becomes
        ``Rules → Combat``. Entries attach to the leaf node.

        Returned shape::

            {
              "Rules": {
                "_entries": [],                       # entries at this level
                "_subcategories": {
                  "Combat": {
                    "_entries": [HelpEntry, ...],
                    "_subcategories": {},
                  },
                  "D6": {...},
                },
              },
              "Character": {
                "_entries": [HelpEntry, ...],
                "_subcategories": {},
              },
              ...
            }

        The portal uses this for the left-hand nav. The CLI doesn't —
        its category view is flat.
        """
        def _blank() -> dict:
            return {"_entries": [], "_subcategories": {}}

        tree: dict[str, dict] = {}
        for entry in self._entries.values():
            parts = _split_category(entry.category)
            cursor = tree
            path: list[str] = []
            for i, part in enumerate(parts):
                path.append(part)
                if part not in cursor:
                    cursor[part] = _blank()
                if i == len(parts) - 1:
                    cursor[part]["_entries"].append(entry)
                cursor = cursor[part]["_subcategories"]

        # Sort each level's entries by title for display stability.
        def _sort_level(level: dict) -> None:
            for node in level.values():
                node["_entries"].sort(key=lambda e: e.title.lower())
                _sort_level(node["_subcategories"])
        _sort_level(tree)
        return tree

    def all_entries(self) -> list[HelpEntry]:
        """Flat list of every registered entry, in insertion order."""
        return list(self._entries.values())

    def by_tag(self, tag: str) -> list[HelpEntry]:
        """Every entry whose ``tags`` list contains ``tag`` (case-insensitive)."""
        tag = tag.lower().strip()
        if not tag:
            return []
        return [e for e in self._entries.values()
                if any(t.lower() == tag for t in e.tags)]

    # ── Loading ──────────────────────────────────────────────────────────

    def auto_register_commands(self, registry) -> None:
        """Create help entries from all registered BaseCommand instances.

        Called after all command modules are loaded. These are the
        thin, auto-generated entries — a command with a
        corresponding ``data/help/commands/<key>.md`` file will have
        this entry overwritten by the markdown version when
        ``load_markdown_files()`` runs.
        """
        self._registry = registry  # remembered so reload() can replay
        for cmd in registry.all_commands:
            if not cmd.key:
                continue
            parts = []
            if cmd.help_text:
                parts.append(cmd.help_text)
            if cmd.usage:
                parts.append(f"\nUSAGE: {cmd.usage}")
            if getattr(cmd, "valid_switches", None):
                sw_lines = ", ".join("/" + s for s in cmd.valid_switches)
                parts.append(f"\nSWITCHES: {sw_lines}")
            if cmd.aliases:
                parts.append(f"\nALIASES: {', '.join(cmd.aliases)}")

            body = "\n".join(parts) if parts else "No detailed help available."

            if cmd.key.startswith("@"):
                cat = "Admin/Building"
            elif cmd.key.startswith("+"):
                cat = "System"
            else:
                cat = "Commands"

            entry = HelpEntry(
                key=cmd.key.lower(),
                title=cmd.key,
                category=cat,
                body=body,
                aliases=[a.lower() for a in cmd.aliases],
                access_level=cmd.access_level,
                summary=(cmd.help_text or "").strip().split("\n", 1)[0][:200],
            )
            self.register(entry)

    def register_topics(self) -> None:
        """Register any HelpEntry objects still declared in TOPIC_HELP.

        With the move to markdown-backed topics this list is usually
        empty — but the hook stays so a quick-and-dirty in-Python
        entry is still possible during development.
        """
        for entry in TOPIC_HELP:
            self.register(entry)

    def load_markdown_files(self, root: Optional[str] = None) -> int:
        """Load every ``.md`` file under ``root`` into the registry.

        If ``root`` is None, defaults to ``<project>/data/help``.

        Returns the number of entries loaded. Markdown entries
        override earlier same-key registrations — that's the whole
        point of the precedence order.
        """
        if root is None:
            root = _default_markdown_root()
        if not os.path.isdir(root):
            log.info("Help loader: no markdown root at %s (skipping)", root)
            return 0
        if root not in self._markdown_roots:
            self._markdown_roots.append(root)

        # Imported here to sidestep an import cycle at module load time —
        # engine/help_loader.py imports HelpEntry from this module.
        from engine.help_loader import load_help_directory
        entries = load_help_directory(root, HelpEntry)
        for entry in entries:
            self.register(entry)
        return len(entries)

    def load_all(self, registry) -> None:
        """Full boot-time load in the correct precedence order.

        Equivalent to calling the three loaders in sequence — useful
        so the server doesn't need to know the order.
        """
        self.auto_register_commands(registry)
        self.register_topics()
        self.load_markdown_files()

    def reload(self) -> int:
        """Rebuild the registry from scratch using remembered sources.

        Intended for admin hot-reload: author edits a markdown help
        file, hits a reload endpoint, new content is live without a
        server restart.

        Returns the total entry count after reload.
        """
        self._entries.clear()
        self._alias_map.clear()
        if self._registry is not None:
            self.auto_register_commands(self._registry)
        self.register_topics()
        # Re-scan every previously-seen markdown root
        for root in list(self._markdown_roots):
            from engine.help_loader import load_help_directory
            for entry in load_help_directory(root, HelpEntry):
                self.register(entry)
        return len(self._entries)


# ── Helpers ────────────────────────────────────────────────────────────────

def _split_category(category: str) -> list[str]:
    """Split a nested category string into path parts.

    Accepts ``·`` (middle-dot), ``/``, and ``:`` as separators.
    Whitespace around each part is stripped.
    """
    # Normalise all separators to ``·`` first, then split.
    s = category.replace("/", "·").replace(":", "·")
    parts = [p.strip() for p in s.split("·")]
    return [p for p in parts if p]


def _default_markdown_root() -> str:
    """Return the absolute path to ``<project>/data/help``."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "help")


# ═══════════════════════════════════════════════════════════════════════
# Legacy topic list — populated historically by hand. All entries have
# been migrated to data/help/topics/*.md; the list remains empty as a
# live extension point. Declare a HelpEntry here during development
# for a quick-and-dirty entry without touching the filesystem.
# ═══════════════════════════════════════════════════════════════════════

TOPIC_HELP: list[HelpEntry] = []
