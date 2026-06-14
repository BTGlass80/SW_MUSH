#!/usr/bin/env python
"""guide_lint.py -- read-only checker for the player-facing guide/help content.

Supports PRELAUNCH.help_guides_rework (see docs/design/help_guides_rework_plan_v1.md).
Measures the current state and guards against backslide during the rework. It NEVER
edits and NEVER blocks -- advisory output only.

Checks, per file under data/guides/ (and optionally data/help/):
  1. DEV-NOTE LEAK  -- developer-facing vocabulary in player-facing prose
                       ("not yet implemented", "placeholder", "WIP", "TODO/FIXME",
                       "Not live yet", bare file paths, function-name(), design-doc refs).
  2. DEV-TRACK      -- a "### 🔧 Developer Internals" heading still present in a guide
                       (post-split regression guard; the dev track is being extracted to
                       docs/dev/). Reported as INFO pre-split, WARN once a guide is meant
                       to be single-track.
  3. DEAD LINK      -- a [label](#/guide/<slug>) whose <slug> matches no guide on disk.
                       Slug derivation MIRRORS server/web_portal.py::_load_guides exactly.
  4. ERA            -- Imperial/Empire/Rebel/TIE in guide prose (CW era-cleanness).

Usage:
    python tools/guide_lint.py                # lint data/guides/
    python tools/guide_lint.py --help-content # also lint data/help/{topics,commands}
    python tools/guide_lint.py --json         # machine-readable output

Exit code is ALWAYS 0 (advisory). The count of findings is printed; parse --json if you
want to gate on it yourself.
"""
import argparse
import json
import os
import re
import sys

# Windows consoles default to cp1252; guide prose contains em-dashes / ≤ / 🔧. Force
# UTF-8 on our own streams so printing findings never crashes on a stray glyph.
for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8")
    except Exception:
        # Best-effort: an old stream without .reconfigure (or a non-tty) just
        # keeps its default encoding; printing may then drop a stray glyph, which
        # is acceptable for a CLI lint tool. Not silent-swallowing real logic.
        _UTF8_RECONFIGURE_FAILED = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDES_DIR = os.path.join(ROOT, "data", "guides")
HELP_DIRS = [
    os.path.join(ROOT, "data", "help", "topics"),
    os.path.join(ROOT, "data", "help", "commands"),
]

DEV_TRACK_MARKER = "Developer Internals"

# Developer-facing phrasing that must not appear in player prose. Word-boundary or
# phrase matches, case-insensitive. Kept deliberately tight to avoid false positives on
# legitimate in-world prose (e.g. "place holder" the noun is fine; "placeholder for a
# future feature" is the leak).
_DEV_NOTE_PATTERNS = [
    r"not yet implemented",
    r"not live yet",
    r"placeholder for (?:now|a future|the)",
    r"\bWIP\b",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"coming soon",
    r"to be implemented",
    r"design doc",
    r"design-doc",
    r"see\s+\w+_v\d",            # design-doc citation like "see economy_design_v2"
]
_DEV_NOTE_RE = re.compile("|".join(_DEV_NOTE_PATTERNS), re.IGNORECASE)

# A bare function-or-file reference in prose: foo_bar.py, engine/x.py, some_func().
_CODE_REF_RE = re.compile(
    r"\b[a-zA-Z_][\w/]*\.py\b"          # file paths ending .py
    r"|\b[a-z_][a-z0-9_]+\([^)]*\)"     # function_call(...) lowercase snake
)

# Era tokens (CW cleanness). Whole-word; TIE only as a standalone word, not "TIER".
_ERA_RE = re.compile(r"\bImperial\b|\bEmpire\b|\bRebel\b|\bTIE\b")
# A line carrying this marker is a SANCTIONED era reference (deliberate CW-vantage
# foreshadowing flavor, e.g. "the reach the Empire will eventually claim"). The lint
# skips era checks on such a line — the guide author signed off on it. Mirror of the
# CLAUDE.md era exemptions for village_trials.py etc.
_ERA_OK_MARKER = "lint-era-ok"

# Guide cross-link: [label](#/guide/slug)
_LINK_RE = re.compile(r"\]\(#/guide/([a-z0-9\-]+)\)")


def _strip_frontmatter(text):
    """Return (frontmatter_str, body_str). Frontmatter is the first --- ... --- block."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[3:end], text[nl + 1:] if nl != -1 else ""
    return "", text


def _slug_for(fname):
    """Mirror server/web_portal.py::_load_guides slug logic exactly."""
    slug = fname.replace(".md", "")
    parts = slug.split("_", 2)
    if len(parts) >= 3 and parts[0].lower() == "guide" and parts[1].isdigit():
        return parts[2].lower().replace("_", "-")
    return slug.lower().replace("_", "-")


def _known_guide_slugs():
    slugs = set()
    if os.path.isdir(GUIDES_DIR):
        for fn in os.listdir(GUIDES_DIR):
            if fn.endswith(".md"):
                slugs.add(_slug_for(fn))
    return slugs


def _frontmatter_access_level(fm):
    m = re.search(r"^access_level:\s*(\d+)", fm, re.MULTILINE)
    return int(m.group(1)) if m else 0


def lint_file(path, known_slugs, treat_dev_track_as_warn):
    """Return a list of finding dicts for one file."""
    findings = []
    fname = os.path.basename(path)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    fm, body = _strip_frontmatter(text)
    access = _frontmatter_access_level(fm)
    # Admin content (access_level >= 2) is allowed dev-ish vocabulary and code refs.
    player_facing = access < 2

    in_dev_track = False   # inside a "### 🔧 Developer Internals" section
    in_fence = False       # inside a ``` code fence
    for i, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()

        # Track section + fence state so we don't flag code refs that live in the
        # dev track (those get EXTRACTED in Phase A — expected, not a player leak).
        if stripped.startswith("```"):
            in_fence = not in_fence
        if stripped.startswith("#"):
            in_dev_track = DEV_TRACK_MARKER in stripped  # a new heading resets the section

        if not stripped:
            continue

        if player_facing:
            m = _DEV_NOTE_RE.search(line)
            if m:
                findings.append({"file": fname, "line": i, "kind": "DEV-NOTE",
                                 "evidence": m.group(0), "text": stripped[:120]})
            # CODE-REF only counts as a player-prose leak OUTSIDE the dev track and
            # outside fenced code; inside the dev track it's expected content awaiting
            # extraction, so don't add noise.
            if not in_dev_track and not in_fence:
                cm = _CODE_REF_RE.search(line)
                if cm and "](" not in line and not stripped.startswith("|"):
                    findings.append({"file": fname, "line": i, "kind": "CODE-REF",
                                     "evidence": cm.group(0), "text": stripped[:120]})

        if DEV_TRACK_MARKER in line and line.lstrip().startswith("#"):
            findings.append({
                "file": fname, "line": i,
                "kind": "DEV-TRACK" if treat_dev_track_as_warn else "DEV-TRACK-INFO",
                "evidence": DEV_TRACK_MARKER, "text": stripped[:120]})

        em = _ERA_RE.search(line)
        if em and _ERA_OK_MARKER not in line:
            findings.append({"file": fname, "line": i, "kind": "ERA",
                             "evidence": em.group(0), "text": stripped[:120]})

        for lm in _LINK_RE.finditer(line):
            slug = lm.group(1)
            if slug not in known_slugs:
                findings.append({"file": fname, "line": i, "kind": "DEAD-LINK",
                                 "evidence": "#/guide/" + slug, "text": stripped[:120]})
    return findings


def main():
    ap = argparse.ArgumentParser(description="Read-only guide/help content linter.")
    ap.add_argument("--help-content", action="store_true",
                    help="also lint data/help/{topics,commands}")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--warn-dev-track", action="store_true",
                    help="treat a remaining Developer Internals heading as WARN "
                         "(use after the Phase-A split; default reports it as INFO)")
    args = ap.parse_args()

    known = _known_guide_slugs()
    targets = []
    if os.path.isdir(GUIDES_DIR):
        targets += [os.path.join(GUIDES_DIR, fn)
                    for fn in sorted(os.listdir(GUIDES_DIR)) if fn.endswith(".md")]
    if args.help_content:
        for d in HELP_DIRS:
            if os.path.isdir(d):
                targets += [os.path.join(d, fn)
                            for fn in sorted(os.listdir(d)) if fn.endswith(".md")]

    all_findings = []
    for path in targets:
        all_findings.extend(lint_file(path, known, args.warn_dev_track))

    if args.json:
        print(json.dumps({"files_scanned": len(targets),
                          "findings": all_findings}, indent=2))
        return 0

    by_kind = {}
    for f in all_findings:
        by_kind.setdefault(f["kind"], []).append(f)

    print("guide_lint: scanned {n} file(s)".format(n=len(targets)))
    order = ["DEV-NOTE", "DEAD-LINK", "ERA", "DEV-TRACK", "CODE-REF", "DEV-TRACK-INFO"]
    for kind in order:
        items = by_kind.get(kind, [])
        if not items:
            continue
        print("\n=== {kind} ({c}) ===".format(kind=kind, c=len(items)))
        for f in items:
            print("  {file}:{line}  [{ev}]  {txt}".format(
                file=f["file"], line=f["line"], ev=f["evidence"], txt=f["text"]))
    # Summary line: count only the actionable kinds (INFO kinds excluded).
    actionable = sum(len(by_kind.get(k, []))
                     for k in ("DEV-NOTE", "DEAD-LINK", "ERA", "DEV-TRACK"))
    print("\n{a} actionable finding(s) "
          "(+{i} CODE-REF/INFO for review).".format(
              a=actionable,
              i=len(by_kind.get("CODE-REF", [])) + len(by_kind.get("DEV-TRACK-INFO", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
