#!/usr/bin/env python
"""tools/append_lore.py — fold reviewed lore into the live lorebook, safely.

Takes one or more REVIEW yamls (the output of ingest_lore.py / harvest_extractions.py)
and appends their CLEAN keeper entries to data/worlds/clone_wars/lore.yaml:
  - ADDITIVE + comment-preserving: text-append only, never a yaml round-trip rewrite
    (honors the map-safety / world-YAML invariant).
  - DEDUPED by exact title (case-insensitive) against the live file AND within the batch,
    so re-runs are idempotent.
  - RE-VALIDATED: the whole file is re-parsed + every entry checked against the loader's
    hard rules AFTER appending; on any failure the live file is restored from backup and the
    tool exits non-zero. A malformed append can never block seeding.
  - ERA-RECHECKED: every keeper is re-run through ingest_lore.validate(); an entry that
    fails (e.g. a human un-commented a flagged one) is skipped with a warning, not appended.

USAGE:
  python tools/append_lore.py harvested_lore_review.yaml --dry-run
  python tools/append_lore.py review_a.yaml review_b.yaml review_c.yaml
  python tools/append_lore.py review.yaml --target data/worlds/clone_wars/lore.yaml
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_lore import LoreEntry, validate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "lore.yaml"

_FLAGGED_RE = re.compile(r"^#.*FLAGGED", re.M)


def parse_review(path: Path) -> list[dict]:
    """Return the CLEAN keeper entry dicts from a review file.

    Keepers live above the '# ─── FLAGGED ───' marker; flagged entries below it
    are all comment lines. yaml.safe_load ignores the '#' header comments, so the
    keeper region loads directly as a YAML sequence.
    """
    text = path.read_text(encoding="utf-8")
    m = _FLAGGED_RE.search(text)
    keeper_text = text[: m.start()] if m else text
    data = yaml.safe_load(keeper_text)
    if data is None:
        return []
    if not isinstance(data, list):
        raise SystemExit(f"{path}: keeper region did not parse as a list "
                         f"(got {type(data).__name__}) — is this a review file?")
    return [d for d in data if isinstance(d, dict)]


def to_entry(d: dict) -> LoreEntry:
    return LoreEntry(
        title=str(d.get("title", "")).strip(),
        keywords=str(d.get("keywords", "") or ""),
        content=str(d.get("content", "") or ""),
        category=str(d.get("category", "concept") or "concept"),
        zone_scope=(d.get("zone_scope") or None),
        priority=int(d.get("priority", 5) or 5),
        planet=str(d.get("planet", "all") or "all"),
        surface_affinity=str(d.get("surface_affinity", "general") or "general"),
    )


def existing_titles(target: Path) -> set[str]:
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return {str(e.get("title", "")).strip().lower()
            for e in (raw.get("entries") or []) if isinstance(e, dict)}


def hard_check(target: Path) -> list[str]:
    """Replicate engine.world_loader.load_lore's HARD rules — the ones that abort
    the whole seed. Returns a list of error strings ([] == clean)."""
    errs: list[str] = []
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return [f"YAML parse failed: {e}"]
    if not isinstance(raw, dict):
        return ["top-level is not a mapping"]
    for i, e in enumerate(raw.get("entries") or []):
        if not isinstance(e, dict):
            errs.append(f"entries[{i}] is not a mapping"); continue
        t = e.get("title")
        if not t or not isinstance(t, str):
            errs.append(f"entries[{i}] missing/invalid title"); continue
        if not isinstance(e.get("keywords") or "", str):
            errs.append(f"entries[{i}] {t!r}: keywords not a string"); continue
        c = e.get("content") or ""
        if not isinstance(c, str) or not c.strip():
            errs.append(f"entries[{i}] {t!r}: empty/invalid content"); continue
        try:
            int(e.get("priority", 5))
        except (TypeError, ValueError):
            errs.append(f"entries[{i}] {t!r}: priority not an int"); continue
        zs = e.get("zone_scope")
        if zs is not None and not isinstance(zs, str):
            errs.append(f"entries[{i}] {t!r}: zone_scope not a string/null")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Append reviewed lore keepers to the live lorebook.")
    ap.add_argument("reviews", nargs="+", help="one or more review yaml files")
    ap.add_argument("--target", default=str(DEFAULT_TARGET), help="lore.yaml to append to")
    ap.add_argument("--dry-run", action="store_true", help="report only; no write")
    ap.add_argument("--min-priority", type=int, default=0,
                    help="skip entries below this priority (default 0 = keep all)")
    ap.add_argument("--exclude-file", default=None,
                    help="file with one title per line to skip (e.g. quality-gate drops)")
    args = ap.parse_args(argv)

    target = Path(args.target)
    if not target.is_file():
        print(f"[append] target not found: {target}", file=sys.stderr)
        return 2

    have = existing_titles(target)
    exclude: set[str] = set()
    if args.exclude_file and Path(args.exclude_file).is_file():
        for ln in Path(args.exclude_file).read_text(encoding="utf-8").splitlines():
            t = ln.strip()
            if t and not t.startswith("#"):
                exclude.add(t.lower())
    batch_seen: set[str] = set()
    queued: list[LoreEntry] = []
    skipped_dup, skipped_dirty, skipped_lowpri, skipped_excl = [], [], [], []

    for rv in args.reviews:
        rvp = Path(rv)
        if not rvp.is_file():
            print(f"[append] review not found: {rvp}", file=sys.stderr); return 2
        for d in parse_review(rvp):
            e = validate(to_entry(d))          # belt-and-suspenders era re-check
            key = e.title.lower()
            if not e.title:
                continue
            if key in have or key in batch_seen:
                skipped_dup.append(e.title); continue
            if e._rejects:
                skipped_dirty.append(f"{e.title} [{', '.join(e._rejects)}]"); continue
            if key in exclude:
                skipped_excl.append(e.title); continue
            if e.priority < args.min_priority:
                skipped_lowpri.append(e.title); continue
            batch_seen.add(key)
            queued.append(e)

    print(f"[append] {len(queued)} new, {len(skipped_dup)} dup(s) skipped, "
          f"{len(skipped_dirty)} era-dirty skipped, {len(skipped_excl)} quality-dropped, "
          f"{len(skipped_lowpri)} below-priority skipped  (live file has {len(have)} entries)")
    if skipped_dirty:
        print("[append] DIRTY (not appended — fix era/canon first):")
        for s in skipped_dirty:
            print(f"          - {s}")
    if not queued:
        print("[append] nothing to append.")
        return 0

    if args.dry_run:
        print("[append] DRY RUN — would append:")
        for e in queued:
            print(f"          + {e.title}  (planet={e.planet}, {e.category}, p{e.priority})")
        return 0

    # ---- write: backup, text-append, re-validate, rollback on failure ----
    backup = target.with_suffix(target.suffix + ".bak")
    shutil.copy2(target, backup)

    old = target.read_text(encoding="utf-8")
    sources = ", ".join(Path(r).name for r in args.reviews)
    block = [old.rstrip("\n"),
             "",
             f"  # ─── appended {date.today().isoformat()} from {sources} "
             f"({len(queued)} entries) ───"]
    for e in queued:
        block.append("")
        block.append(e.as_yaml_block())
    block.append("")
    target.write_text("\n".join(block) + "\n", encoding="utf-8")

    errs = hard_check(target)
    if errs:
        shutil.copy2(backup, target)
        print(f"[append] VALIDATION FAILED — restored {target.name} from backup. Errors:",
              file=sys.stderr)
        for er in errs[:20]:
            print(f"          ! {er}", file=sys.stderr)
        return 1

    print(f"[append] OK — appended {len(queued)} entries. Live file now has "
          f"{len(have) + len(queued)} entries. Backup: {backup.name}")
    print("[append] NOTE: entries are INERT until you restart the game server "
          "(seed_lore re-reads lore.yaml at boot; insert-only by title).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
