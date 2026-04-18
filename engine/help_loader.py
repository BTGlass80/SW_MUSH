# -*- coding: utf-8 -*-
"""
engine/help_loader.py — load help entries from markdown files on disk.

Each help entry is a single file under ``data/help/`` with YAML
frontmatter for metadata and markdown for body content::

    ---
    key: combat
    title: Combat Basics
    category: Rules · Combat
    summary: How attacks, dodges, wounds, and rounds work.
    aliases: [fight, fighting, battle]
    see_also: [ranged, melee, wounds, dodge]
    tags: [combat, core]
    access_level: 0
    examples:
      - cmd: attack greedo
        description: Make a basic ranged attack at the default range.
      - cmd: dodge
        description: Declare a reactive dodge for the round.
    ---

    Star Wars D6 combat runs in **rounds**. Each round every combatant
    declares actions, then the game resolves them in initiative order.

    ## Multiple actions
    ...

Design notes
------------

* **Filesystem-safe key encoding.** The canonical key may contain ``+``
  or ``/`` (e.g. a future ``+combat/attack``). We encode slashes as
  ``__`` in filenames so filenames remain portable. The loader decodes
  back to the canonical key when building the ``HelpEntry``.

* **Frontmatter vs body.** Frontmatter is YAML, terminated by ``---``
  lines. Everything after the closing fence is the body. If the ``key``
  field is missing, we derive it from the filename. If ``title`` is
  missing we use the first ``#`` heading in the body, or fall back to
  the key.

* **Degradation.** A malformed file logs a warning and is skipped — it
  never raises. The server keeps booting even if one help file is
  broken. Missing ``key``/``title`` are tolerated (derived).

* **``updated_at``.** If the frontmatter supplies it, we use that
  string as-is. Otherwise we stamp the file's mtime in ISO-8601 form,
  which gives the portal a "last updated" value for free.

This loader is pure — it only reads files and builds ``HelpEntry``
instances. It does not touch the ``HelpManager`` itself; wiring is
done in ``data/help_topics.py::HelpManager.load_markdown_files``.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import TYPE_CHECKING, Iterable, Optional

import yaml

if TYPE_CHECKING:
    from data.help_topics import HelpEntry  # noqa: F401 — type-only

log = logging.getLogger(__name__)


# ── Filename ↔ key encoding ─────────────────────────────────────────────────
# Keys may legally contain ``/`` (nested sub-command help entries, e.g.
# ``+combat/attack``). Filenames cannot. The encoding is symmetrical so a
# round-trip is lossless.

def encode_key_to_filename(key: str) -> str:
    """Convert a help-entry key into a safe filename stem.

    ``+combat/attack`` → ``+combat__attack``
    ``+sheet``         → ``+sheet``
    ``combat``         → ``combat``
    """
    return key.replace("/", "__")


def decode_filename_to_key(stem: str) -> str:
    """Reverse ``encode_key_to_filename``.

    ``+combat__attack`` → ``+combat/attack``
    """
    return stem.replace("__", "/")


# ── Frontmatter parsing ─────────────────────────────────────────────────────

_FENCE = "---"


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """Split a raw markdown file into (frontmatter_dict, body_text).

    The file is expected to start with a ``---`` fence on line 1. If it
    does not, we treat the entire file as body with an empty
    frontmatter — this lets a hand-written file without metadata still
    be loaded (with all fields derived).

    If the frontmatter YAML fails to parse, we log a warning and
    return ``({}, raw)`` so the caller can at least render the body.
    """
    lines = raw.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}, raw

    # Find the closing fence.
    end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            end_idx = i
            break
    if end_idx is None:
        # Opened but never closed — treat whole thing as body to avoid
        # silently swallowing content.
        log.warning("Help loader: unterminated frontmatter fence")
        return {}, raw

    yaml_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])
    try:
        meta = yaml.safe_load(yaml_text) or {}
        if not isinstance(meta, dict):
            log.warning("Help loader: frontmatter is not a mapping, ignoring")
            meta = {}
    except yaml.YAMLError as e:
        log.warning("Help loader: YAML parse error — %s", e)
        meta = {}

    return meta, body.lstrip("\n")


def _derive_title(body: str, fallback: str) -> str:
    """Pull the first ``# Heading`` out of a markdown body, or fall back."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# ") and len(s) > 2:
            return s[2:].strip()
    return fallback


def _coerce_list(val) -> list[str]:
    """Accept either a YAML list or a comma-separated string."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return []


def _coerce_examples(val) -> list[dict]:
    """Accept a list of ``{cmd, description}`` dicts, or a plain list of strings.

    A string like ``"attack greedo"`` becomes
    ``{"cmd": "attack greedo", "description": ""}``.
    """
    if val is None:
        return []
    if not isinstance(val, list):
        return []
    out = []
    for item in val:
        if isinstance(item, dict):
            cmd = str(item.get("cmd", "")).strip()
            desc = str(item.get("description", "")).strip()
            if cmd:
                out.append({"cmd": cmd, "description": desc})
        elif isinstance(item, str) and item.strip():
            out.append({"cmd": item.strip(), "description": ""})
    return out


# ── Main entry point ────────────────────────────────────────────────────────

def load_help_file(path: str, HelpEntryCls) -> Optional["HelpEntry"]:
    """Load a single markdown help file, returning a ``HelpEntry`` or None.

    Returns ``None`` and logs a warning on any failure — callers should
    treat missing entries as "this file was broken, skip it" rather
    than stopping the boot.

    ``HelpEntryCls`` is passed in to avoid a circular import between
    this module and ``data/help_topics.py``.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        log.warning("Help loader: cannot read %s — %s", path, e)
        return None

    meta, body = _split_frontmatter(raw)

    stem = os.path.splitext(os.path.basename(path))[0]
    key = str(meta.get("key") or decode_filename_to_key(stem)).strip().lower()
    if not key:
        log.warning("Help loader: empty key for %s, skipping", path)
        return None

    title = str(meta.get("title") or _derive_title(body, key)).strip()
    category = str(meta.get("category") or "Uncategorized").strip()
    summary = str(meta.get("summary") or "").strip()
    aliases = [a.lower() for a in _coerce_list(meta.get("aliases"))]
    see_also = [s.lower() for s in _coerce_list(meta.get("see_also"))]
    tags = [t.lower() for t in _coerce_list(meta.get("tags"))]
    examples = _coerce_examples(meta.get("examples"))
    try:
        access_level = int(meta.get("access_level", 0) or 0)
    except (TypeError, ValueError):
        log.warning(
            "Help loader: non-integer access_level in %s, defaulting to 0", path
        )
        access_level = 0

    # updated_at: frontmatter wins, else file mtime
    updated_at = str(meta.get("updated_at") or "").strip()
    if not updated_at:
        try:
            mtime = os.path.getmtime(path)
            updated_at = _dt.datetime.fromtimestamp(
                mtime, tz=_dt.timezone.utc
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
        except OSError:
            updated_at = ""

    # Body stays markdown; CLI consumes it as-is (markdown degrades to
    # readable plaintext), portal renders it through its markdown pipe.
    body = body.rstrip() + "\n"  # normalise trailing newline

    return HelpEntryCls(
        key=key,
        title=title,
        category=category,
        body=body,
        aliases=aliases,
        see_also=see_also,
        access_level=access_level,
        summary=summary,
        examples=examples,
        tags=tags,
        updated_at=updated_at,
    )


def iter_help_files(root: str) -> Iterable[str]:
    """Yield every ``.md`` file under ``root``, recursively, sorted.

    ``README.md`` files are skipped — they're conventional directory
    notes, not help entries. Any other markdown file is fair game.

    Deterministic order is useful for reproducible boots and for the
    portal's category listing being stable.
    """
    if not os.path.isdir(root):
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in sorted(filenames):
            if not fname.endswith(".md"):
                continue
            if fname.lower() == "readme.md":
                continue
            yield os.path.join(dirpath, fname)


def load_help_directory(root: str, HelpEntryCls) -> list["HelpEntry"]:
    """Load every markdown help file under ``root`` into ``HelpEntry`` objects.

    Broken files are skipped (with a warning). Duplicate keys across
    files: the last one wins and a warning is emitted — this is
    almost always an authoring mistake, not an intentional override.
    """
    entries: dict[str, "HelpEntry"] = {}
    count_loaded = 0
    count_skipped = 0
    for path in iter_help_files(root):
        entry = load_help_file(path, HelpEntryCls)
        if entry is None:
            count_skipped += 1
            continue
        if entry.key in entries:
            log.warning(
                "Help loader: duplicate key %r — later file %s overrides earlier",
                entry.key, path,
            )
        entries[entry.key] = entry
        count_loaded += 1
    if count_skipped:
        log.warning(
            "Help loader: loaded %d entries, skipped %d broken files from %s",
            count_loaded, count_skipped, root,
        )
    else:
        log.info(
            "Help loader: loaded %d entries from %s", count_loaded, root
        )
    return list(entries.values())
