#!/usr/bin/env python
"""tools/ingest_batch.py - run ingest_lore.py over a curated set of sourcebooks.

Sequential by design (avoids Tesseract OCR CPU-thrash from parallel jobs). Continues
past a per-book error, but STOPS on a fatal API error (no credits / bad key / SSL),
since that fails identically for every book. One review yaml per book into --out-dir.

When it's done, fold every keeper into the lorebook in ONE step:
    python tools/append_lore.py ingest_review/*.yaml
    # then restart the server so seed_lore picks them up.

USAGE:
  python tools/ingest_batch.py                       # the default grounding-priority set
  python tools/ingest_batch.py docs/sourcebooks/WEG40087.pdf docs/sourcebooks/WEG40150.pdf
"""
from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCEBOOKS = PROJECT_ROOT / "docs" / "sourcebooks"
INGEST = PROJECT_ROOT / "tools" / "ingest_lore.py"

# The grounding-priority set (per sourcebook_grounding_reprioritization_v1.md):
# fills the under-grounded planets first, skips low-grounding rules/GCW books.
# (label, source-name, [glob patterns tried in order])
DEFAULT_SET = [
    ("stock_ships",       "Stock Ships (WEG40150) - Kuat/space-traffic",        ["*40150*"]),
    ("gg12_aliens",       "Galaxy Guide 12: Aliens (WEG40087) - species",       ["WEG40087*"]),
    ("coruscant",         "Coruscant and the Core Worlds - Coruscant gap",      ["Coruscant*", "coruscant*"]),
    ("black_sands",       "Black Sands of Socorro (40154) - Nar Shaddaa",       ["*40154*", "*ocorro*"]),
    ("galladiniums_gear", "Galladinium's Guns & Gear (40025) - gear",           ["*40025*", "*alladin*"]),
    ("scouts_40061",      "WEG40061 - survey/scout (tentative)",                ["*40061*"]),
]


def _resolve(patterns: list[str]) -> Path | None:
    for pat in patterns:
        cands = sorted(glob.glob(str(SOURCEBOOKS / pat)))
        if cands:
            plain = [c for c in cands if "_compressed" not in c.lower() and "(1)" not in c]
            return Path((plain or cands)[0])
    return None


def _entry_count(review: Path) -> int:
    if not review.is_file():
        return 0
    return sum(1 for ln in review.read_text(encoding="utf-8").splitlines()
               if ln.lstrip().startswith("- title:"))


def main(argv=None) -> int:
    try:    # Windows cp1252 consoles crash on unicode in book/entry text
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass  # reconfigure is best-effort; older/non-Windows streams keep default
    ap = argparse.ArgumentParser(description="Batch-ingest sourcebooks into review yamls.")
    ap.add_argument("pdfs", nargs="*", help="explicit PDF paths (default: curated set)")
    ap.add_argument("--out-dir", default=str(PROJECT_ROOT / "ingest_review"))
    ap.add_argument("--ocr", default="auto", choices=["auto", "tesseract", "off"])
    ap.add_argument("--concurrency", type=int, default=1,
                    help="parallel OCR pages + API chunks per book (default 1)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build the worklist: (label, source, pdf_path)
    work: list[tuple[str, str, Path]] = []
    if args.pdfs:
        for p in args.pdfs:
            pp = Path(p)
            if pp.is_file():
                work.append((pp.stem, pp.stem, pp))
            else:
                print(f"[batch] SKIP (not found): {p}")
    else:
        for label, source, pats in DEFAULT_SET:
            pdf = _resolve(pats)
            if pdf:
                work.append((label, source, pdf))
            else:
                print(f"[batch] SKIP (no match in docs/sourcebooks): {source}")

    if not work:
        print("[batch] nothing to ingest.")
        return 0

    print(f"[batch] {len(work)} book(s) -> {out_dir}\n")
    done, failed = [], []
    for label, source, pdf in work:
        review = out_dir / f"{label}.yaml"
        print(f"[batch] -- {source}\n[batch]    {pdf.name} -> {review.name}")
        rc = subprocess.call([sys.executable, str(INGEST), str(pdf),
                              "--out", str(review), "--ocr", args.ocr, "--source", source,
                              "--concurrency", str(args.concurrency)])
        if rc == 3:
            print(f"\n[batch] STOP - fatal API error on '{label}' (would fail for every book).")
            print("[batch] Add credits at console.anthropic.com -> Plans & Billing, then re-run.")
            failed.append(label)
            break
        if rc == 0 and review.is_file():
            n = _entry_count(review)
            print(f"[batch]    OK: {n} clean entr(ies)\n")
            done.append((label, n))
        else:
            print(f"[batch]    book failed (exit {rc}) - skipping\n")
            failed.append(label)

    print("[batch] --------- SUMMARY ---------")
    for label, n in done:
        print(f"[batch]   {label}: {n} entries -> {out_dir / (label + '.yaml')}")
    if failed:
        print(f"[batch]   failed/skipped: {', '.join(failed)}")
    if done:
        print(f"\n[batch] NEXT: python tools/append_lore.py {out_dir.name}/*.yaml")
        print("[batch]       then restart the server so seed_lore picks them up.")
    return 1 if (failed and not done) else 0


if __name__ == "__main__":
    sys.exit(main())
