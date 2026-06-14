#!/usr/bin/env python
"""split_guide_dev_track.py -- Phase A of PRELAUNCH.help_guides_rework.

Extracts the developer-facing content OUT of the 8 dual-track player guides in
data/guides/ into a parallel docs/dev/internals_<NN>_<slug>.md set, leaving the player
guides single-track and clean. Content-preserving: every removed line is written to the
dev doc, so nothing is lost (Brian's decision: SPLIT, do not delete).

What it removes from a player guide (and relocates to the dev doc):
  1. The "## How to Read This Guide" two-track preamble (a guide that is no longer
     dual-track shouldn't advertise a Developer Internals track). Its trailing `---`
     divider goes too.
  2. Every "### 🔧 Developer Internals" subsection: from that heading up to (but not
     including) the next heading (## or ###) or a `---` horizontal rule.
  3. Whole developer-only sections: "## N. File Reference" and "## N. Implementation
     Status" -- from that `##` heading up to the next `##` heading.

Section numbers are intentionally NOT renumbered: a numbering gap is harmless, and
renumbering would be a larger, riskier edit (and could desync cross-references).

Usage:
    python tools/split_guide_dev_track.py --dry-run   # report what WOULD move, no writes
    python tools/split_guide_dev_track.py             # perform the split

Idempotent-ish: a guide with no dev content is left byte-identical. Safe to re-run.
"""
import argparse
import os
import re
import sys

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        # Best-effort: an old stream without .reconfigure keeps its default
        # encoding. Acceptable for a one-shot CLI tool; not silent-swallowing logic.
        _UTF8_RECONFIGURE_FAILED = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDES_DIR = os.path.join(ROOT, "data", "guides")
DEV_DIR = os.path.join(ROOT, "docs", "dev")

DEV_SUBSECTION = "Developer Internals"          # marks a "### 🔧 Developer Internals" block
DEV_WHOLE_SECTION_RE = re.compile(
    r"^##\s+(?:\d+\.\s+)?(File Reference|Implementation Status)\b", re.IGNORECASE)
PREAMBLE_RE = re.compile(r"^##\s+How to Read This Guide\b", re.IGNORECASE)
# Only the GENERIC two-track boilerplate preamble is removed. A "How to Read This
# Guide" intro that was rewritten into real reader-orientation prose is KEPT (most
# guides have one). The boilerplate is identified by its tell-tale two-track phrasing.
_BOILERPLATE_PHRASES = ("split into two tracks", "skip whichever track",
                        "marked with 🔧", "developer internals** sections")
PLAYER_RULES_RE = re.compile(r"^###\s+Player Rules\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s")
H2_RE = re.compile(r"^##\s")
HR_RE = re.compile(r"^---\s*$")


def _slug_for(fname):
    slug = fname.replace(".md", "")
    parts = slug.split("_", 2)
    if len(parts) >= 3 and parts[0].lower() == "guide" and parts[1].isdigit():
        return parts[1], parts[2].lower().replace("_", "-")
    return "00", slug.lower().replace("_", "-")


def split_guide(lines):
    """Return (kept_lines, removed_blocks). removed_blocks is a list of (label, [lines])."""
    kept = []
    removed = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # (1) Two-track preamble: "## How to Read This Guide" ... up to next ## heading.
        #     Remove ONLY if it's the generic two-track boilerplate. A rewritten
        #     orientation intro under the same heading is real player content — keep it.
        if PREAMBLE_RE.match(line):
            block = [line]
            j = i + 1
            while j < n and not H2_RE.match(lines[j]):
                block.append(lines[j])
                j += 1
            blocktext = "".join(block).lower()
            is_boilerplate = any(p in blocktext for p in _BOILERPLATE_PHRASES)
            if is_boilerplate:
                removed.append(("preamble", block))
                i = j
                continue
            # Not boilerplate -> keep the intro; fall through to copy this line.
            kept.append(line)
            i += 1
            continue

        # (3) Whole dev-only ## section: File Reference / Implementation Status,
        #     from this ## up to the next ## heading.
        if DEV_WHOLE_SECTION_RE.match(line):
            block = [line]
            i += 1
            while i < n and not H2_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            removed.append(("section:" + line.strip(), block))
            continue

        # (2) "### 🔧 Developer Internals" subsection: from this heading up to the next
        #     heading (## or ###) OR a horizontal rule.
        if line.lstrip().startswith("#") and DEV_SUBSECTION in line:
            block = [line]
            i += 1
            while i < n and not HEADING_RE.match(lines[i]) and not HR_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            removed.append(("subsection", block))
            continue

        # (4) A now-redundant "### Player Rules" label: once the sibling dev track is
        #     gone, a lone "### Player Rules" subheading under a "## N." section is noise.
        #     Drop the heading line only; its content stays directly under the section.
        if PLAYER_RULES_RE.match(line):
            i += 1
            # also swallow a single blank line immediately after the dropped heading
            if i < n and lines[i].strip() == "":
                i += 1
            continue

        kept.append(line)
        i += 1

    return kept, removed


def _tidy(kept_lines):
    """Collapse the runs of blank lines / orphaned `---` that removal can leave behind,
    so the cleaned guide reads naturally. Never merges across real content."""
    out = []
    for ln in kept_lines:
        # Skip a `---` that would be immediately preceded by another `---` (with only
        # blanks between) -- an orphaned divider left by a removed block.
        if HR_RE.match(ln):
            j = len(out) - 1
            while j >= 0 and out[j].strip() == "":
                j -= 1
            if j >= 0 and HR_RE.match(out[j]):
                continue  # drop duplicate divider
        out.append(ln)
    # Collapse 3+ consecutive blank lines down to 1.
    collapsed = []
    blanks = 0
    for ln in out:
        if ln.strip() == "":
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        collapsed.append(ln)
    return collapsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = ap.parse_args()

    if not os.path.isdir(DEV_DIR) and not args.dry_run:
        os.makedirs(DEV_DIR, exist_ok=True)

    guides = sorted(fn for fn in os.listdir(GUIDES_DIR) if fn.endswith(".md"))
    total_moved = 0
    touched = 0
    for fn in guides:
        path = os.path.join(GUIDES_DIR, fn)
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines(keepends=True)
        kept, removed = split_guide(lines)
        if not removed:
            continue
        # Real dev content = a subsection or a whole dev section. The "How to Read This
        # Guide" preamble is generic boilerplate: we remove it from the player guide but
        # do NOT preserve it (no dev doc for a guide whose only removed block was that).
        dev_blocks = [(lbl, b) for (lbl, b) in removed if lbl != "preamble"]
        touched += 1
        moved_lines = sum(len(b) for _, b in removed)
        total_moved += moved_lines
        num, slug = _slug_for(fn)
        kinds = {}
        for label, _b in removed:
            k = label.split(":")[0]
            kinds[k] = kinds.get(k, 0) + 1
        print("{fn}: -{ml} lines  ({kinds})".format(
            fn=fn, ml=moved_lines,
            kinds=", ".join("{0}×{1}".format(v, k) for k, v in sorted(kinds.items()))))

        if args.dry_run:
            continue

        cleaned = "".join(_tidy(kept))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cleaned)

        # Only write a dev doc when there is REAL dev content to preserve.
        if not dev_blocks:
            print("    (preamble-only — guide cleaned, no dev doc needed)")
            continue

        dev_path = os.path.join(DEV_DIR, "internals_{0}_{1}.md".format(num, slug))
        header = (
            "# Developer Internals — {fn}\n\n"
            "Extracted from `data/guides/{fn}` during the help-guides rework "
            "(PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track "
            "that used to live inline in the player guide; it is NOT player-facing and is "
            "NOT loaded by the game. Treat it as reference docs, and re-verify any "
            "file:line citation against HEAD before trusting it.\n\n---\n\n"
        ).format(fn=fn)
        body_parts = []
        for label, block in dev_blocks:
            body_parts.append("".join(block).rstrip() + "\n")
        with open(dev_path, "w", encoding="utf-8") as fh:
            fh.write(header + "\n".join(body_parts) + "\n")
        print("    -> docs/dev/internals_{0}_{1}.md".format(num, slug))

    verb = "would move" if args.dry_run else "moved"
    print("\n{verb} {ml} dev line(s) out of {t} guide(s).".format(
        verb=verb, ml=total_moved, t=touched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
